#!/usr/bin/env bash
set -eo pipefail

define HTTP_PROXY='http://10.24.221.149:911'
define HTTPS_PROXY='http://10.24.221.149:911'
define MODEL_CACHE_PATH_LOACL='/root/.cache/huggingface/hub'
define CODE_CHECKOUT_PATH_LOCAL='/root/llm-on-ray'

build_and_prune() {
    # Set TARGET and DF-SUFFIX using the passed in parameters
    local TARGET="$1"
    local DF_SUFFIX="$2"
    local PYTHON_V="$3"
    local USE_PROXY="$4"
    
    docker_args=()
    docker_args+=("--build-arg=CACHEBUST=1")
    if [ -n "$PYTHON_V" ]; then
        docker_args+=("--build-arg=python_v=${PYTHON_V}")
    fi
    if [ -n "$USE_PROXY" ]; then
        docker_args+=("--build-arg=http_proxy=${HTTP_PROXY}")
        docker_args+=("--build-arg=https_proxy=${HTTPS_PROXY}")
    fi
    
    # Build Docker image and perform cleaning operation
    docker build ./ "${docker_args[@]}" -f dev/docker/Dockerfile${DF_SUFFIX} -t ${TARGET}:latest && yes | docker container prune && yes 
    docker image prune -f
}

clean_docker(){
    local TARGET="$1"

    cid=$(docker ps -q --filter "name=${TARGET}")
    if [[ ! -z "$cid" ]]; then docker stop $cid && docker rm $cid; fi
    # check and remove exited container
    cid=$(docker ps -a -q --filter "name=${TARGET}")
    if [[ ! -z "$cid" ]]; then docker rm $cid; fi
    docker ps -a
}

run_docker() {
    local TARGET="$1"
    local DF_SUFFIX="$2"
    local PYTHON_V="$3"
    local USE_PROXY="$4"
    local model_cache_path="$5"
    local code_checkout_path="$6"

    docker_args=()
    docker_args+=("--name="${TARGET}"" )
    docker_args+=("--hostname="${TARGET}-container"")

    if [ -n "$PYTHON_V" ]; then
        docker_args+=("--build-arg=python_v=${PYTHON_V}")
    fi
    if [ -n "$USE_PROXY" ]; then
        docker_args+=("--build-arg=http_proxy=${HTTP_PROXY}")
        docker_args+=("--build-arg=https_proxy=${HTTPS_PROXY}")
    fi

    docker run -tid \
        -v "${{model_cache_path }}:${MODEL_CACHE_PATH_LOACL}" \  
        -v "${{code_checkout_path }}:${CODE_CHECKOUT_PATH_LOCAL}" \
        -e http_proxy="${{HTTP_PROXY }}" \
        -e https_proxy="${{HTTPs_PROXY }}" \
        --name="${TARGET}${DF_SUFFIX}" \
        --hostname="${TARGET}-container" \
        "${TARGET}:latest"
}

docker_bash(){
    local TARGET="$1" 
    local bash_command="$2"

    docker exec "${TARGET}" bash -c "${bash_command}"
}