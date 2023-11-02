#!/usr/bin/env python

import os
import time
import traceback
from typing import Any, Dict

import accelerate

import ray
from ray.train.torch import TorchTrainer
from ray.air.config import ScalingConfig
from raydp.torch.config import TorchConfig
from ray.air import RunConfig, FailureConfig

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import common

def train_func(config: Dict[str, Any]):
    cwd = config.get("cwd")
    if cwd:
        os.chdir(cwd)
    
    gradient_accumulation_steps = config["Training"].get("gradient_accumulation_steps", 1)
    accelerator = accelerate.Accelerator(gradient_accumulation_steps = gradient_accumulation_steps)
    common.logger.info(f"accelerator generate finish")

    seed = config["Training"].get("seed")
    if seed is not None:
        accelerate.utils.set_seed(seed)

    datasets = common.dataset.Dataset.registory.get("HuggingfaceDataset")()(config = {
        "name": config["Dataset"]["train_file"], 
        "validation_file": config["Dataset"]["validation_file"],
        "validation_split_percentage": config["Dataset"]["validation_split_percentage"]
    })

    tokenizer = common.tokenizer.Tokenizer.registory.get("HuggingFaceTokenizer")()(config = {
        "name": config["General"]["base_model"], 
        "config": config["General"]["config"]
    })

    model = common.model.Model.registory.get("HuggingFaceModelForCausalLM")()(config = {
        "name": config["General"]["base_model"],
        "config": config["General"]["config"],
        "lora_config": config["General"]["lora_config"] if config["General"].get("lora_config") else None
    })

    optimizer = common.optimizer.Optimizer.registory.get("DefaultOptimizer")()(model, config = {
        "name": config["Training"]["optimizer"],
        "config": {
            "lr": config["Training"]["learning_rate"]
        },
    })

    trainer = common.trainer.Trainer.registory.get("DefaultTrainer")(config = {
        "num_train_epochs": config["Training"]["epochs"],
        "max_train_step": config["Training"].get("max_train_steps", None),
        "output": config["General"]["output_dir"],
        "dataprocesser": {
            "type": "GeneralProcesser",
            "per_device_train_batch_size": config["Training"]["batch_size"],
            "per_device_eval_batch_size": config["Training"]["batch_size"],
            "preprocessing_num_workers": config["Dataset"].get("preprocessing_num_workers", 1),
            "shuffle": True
        },
        "lr_scheduler": {
            "enable": True,
            "max_train_steps": None,
            "lr_scheduler_type": config["Training"]["lr_scheduler"],
            "num_warmup_steps": 0,
        },
        "checkpoint": {
            "root_path": config["General"]["checkpoint_dir"],
        } if config["General"].get("checkpoint_dir") else None
    })

    try :
        common.logger.info(f"trainer prepare start")
        trainer.prepare(model, tokenizer, datasets, optimizer, accelerator)
    except Exception as e:
        common.logger.critical(e, exc_info=True)
        exit(1)
    common.logger.info(f"trainer prepare finish")

    try :
        common.logger.info(f"train start")
        trainer.train()
    except Exception as e:
        common.logger.critical(e, exc_info=True)
        exit(1)
    common.logger.info(f"train finish")

def main(external_config = None):
    config = common.Config()
    if external_config is not None:
        config.merge(external_config)

    config["cwd"] = os.getcwd()
    num_training_workers = config["Training"].get("num_training_workers")
    resources_per_worker = config["Training"].get("resources_per_worker")

    if not ray.is_initialized():
        runtime_env = {
            "env_vars": {
                "OMP_NUM_THREADS": str(resources_per_worker["CPU"]), 
                "ACCELERATE_USE_CPU": "True", 
                "ACCELERATE_USE_IPEX": "False",
                "ACCELERATE_MIXED_PRECISION": "no",
                "CCL_WORKER_COUNT": "1",
                "CCL_LOG_LEVEL": "info",
                "WORLD_SIZE": str(num_training_workers),
            }
        }
        if config["General"]["gpt_base_model"] == True:
            runtime_env["pip"] = ["transformers==4.26.0"]
        ray.init(runtime_env = runtime_env)

    scaling_config = ScalingConfig(
        num_workers = num_training_workers,
        resources_per_worker = resources_per_worker,
        placement_strategy = "SPREAD"
    )

    if config.get("torch_config", None) is None:
        torch_config = TorchConfig(backend = "ccl")
    else:
        customer_torch_config = config.get("torch_config")
        torch_config = TorchConfig(**customer_torch_config)
    
    if config.get("failure_config", None) is None:
        failure_config = FailureConfig()
    else:
        customer_failure_config = config.get("failure_config")
        failure_config = FailureConfig(**customer_failure_config)

    if config.get("run_config", None) is None:
        run_config = RunConfig(failure_config=failure_config)
    else:
        customer_run_config = config.get("run_config")
        if customer_run_config.get("failure_config", None) is None:
            customer_run_config["failure_config"] = failure_config
        run_config = RunConfig(**customer_run_config)

    trainer = TorchTrainer(
        train_func,
        train_loop_config=config,
        scaling_config=scaling_config,
        torch_config = torch_config,
        run_config = run_config
    )
    results = trainer.fit()
    return results

if __name__ == "__main__":
    main()
