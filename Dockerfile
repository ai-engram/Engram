# Engram Miner — Docker image for Akash Network deployment
FROM python:3.11-slim

WORKDIR /app

# Rust toolchain (needed for maturin / engram-core) + runtime libs for faiss/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential pkg-config libssl-dev git \
    libgomp1 libgmp-dev && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build and install engram-core Rust extension
COPY engram-core/ engram-core/
COPY Cargo.toml Cargo.lock ./
RUN pip install maturin && \
    maturin build --manifest-path engram-core/Cargo.toml --release --out /dist && \
    pip install /dist/*.whl

# Copy source
COPY engram/ engram/
COPY neurons/miner.py neurons/miner.py

RUN mkdir -p data

ENV MINER_PORT=8091
ENV QDRANT_HOST=localhost
ENV QDRANT_PORT=6333
ENV NETUID=450
ENV SUBTENSOR_ENDPOINT=wss://test.finney.opentensor.ai:443

EXPOSE 8091

CMD ["sh", "-c", "python neurons/miner.py --port ${MINER_PORT} --netuid ${NETUID} --subtensor.chain_endpoint ${SUBTENSOR_ENDPOINT}"]
