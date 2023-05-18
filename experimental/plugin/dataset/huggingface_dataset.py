import datasets

from .dataset import Dataset

class HuggingfaceDataset(Dataset):
    def __call__(self, config):
        name = config.get("name")
        load_from_disk = config.get("load_from_disk", False)
        load_config = config.get("load_config", {})
        if load_from_disk:
            return datasets.load_from_disk(name, **load_config)
        else:
            return datasets.load_dataset(name, **load_config)