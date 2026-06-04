# seedemu-solana base image
#
# Ships the Agave validator toolchain (the production Solana client maintained by
# Anza, successor to the original solana-labs validator) so that SolanaService
# nodes can run a real, self-contained Solana cluster inside the emulator.
#
# Design note (PRINCIPLES.md P5 "real production software, pinned version"):
# we install the official pre-built Agave release binaries rather than building
# from source, and pin both the version and the archive SHA-256 for
# reproducibility.
#
# Build it (run once before compiling a Solana emulation):
#   docker build -t seedemu-solana docker_images/seedemu-solana
#
# The SolanaService maps BaseSystem.SEEDEMU_SOLANA to this image, so every
# Solana node shares it and the ~290 MB download happens a single time.
#
# NOTE: Agave only publishes pre-built Linux binaries for x86_64 (amd64).
#       Solana emulations therefore target the AMD64 platform.

FROM handsonsecurity/seedemu-base:2.0

ARG DEBIAN_FRONTEND=noninteractive

# Pin the Agave release to keep the emulator reproducible.
ENV SOLANA_VERSION=v2.2.14 \
    SOLANA_SHA256_AMD64=b5dadeb39ab7f31062c599ead459b9d809dd9d709365df6cb5943828b7693b36

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl bzip2 jq; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/solana

# Download, verify, and unpack the official Agave release bundle.
RUN set -eux; \
    archive="solana-release-x86_64-unknown-linux-gnu.tar.bz2"; \
    url="https://github.com/anza-xyz/agave/releases/download/${SOLANA_VERSION}/${archive}"; \
    curl -L --fail --retry 3 "$url" -o "/tmp/${archive}"; \
    echo "${SOLANA_SHA256_AMD64}  /tmp/${archive}" | sha256sum -c -; \
    tar -xf "/tmp/${archive}" --strip-components=1 -C /opt/solana; \
    rm "/tmp/${archive}"; \
    for bin in solana solana-keygen solana-genesis solana-faucet agave-validator solana-test-validator; do \
        ln -sf "/opt/solana/bin/${bin}" "/usr/local/bin/${bin}"; \
    done; \
    /usr/local/bin/solana --version

# Reset the working directory to '/'. seedemu's generated start.sh and
# interface_setup run from the container's WORKDIR and read helper files such as
# ifinfo.txt by relative path (they live at '/'). Leaving WORKDIR at /opt/solana
# would break interface renaming and routing on every node.
WORKDIR /

CMD ["/bin/bash"]
