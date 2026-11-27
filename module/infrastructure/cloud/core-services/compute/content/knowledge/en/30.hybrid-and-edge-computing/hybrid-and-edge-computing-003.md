# Packaging workloads for consistent multi-environment deployment

A compute workload may have to run across data centers, cloud regions, branch offices, and edge sites. These environments often differ in CPU architecture, operating system, networking, storage, access permissions, Internet connectivity, and device management. If each location is installed manually in its own way, the same application version can behave differently, become hard to update, and be difficult to recover when failures occur.

Workload packaging turns an application and its runtime dependencies into an artifact that can be verified, distributed, and deployed repeatably. Artifacts must be separated from environment-specific configuration; the deployment process must explicitly describe resources, networking, storage, secrets, health checks, and update policies. The goal is that **the same verified release can be deployed using controlled environment configurations**, while still respecting the specific constraints of cloud, on-premises, and edge.

## 1. Why consistent packaging matters

In hybrid and edge models, applications are often deployed across multiple locations:

- Cloud regions for centralized load, large datasets, or shared services.
- Data centers/on-premises to meet data requirements, legacy system integration, or internal latency needs.
- Edge sites close to devices, production lines, stores, or users for local processing.
- Gateways or industrial machines with constrained resources and unstable connectivity.

Each location may have different installation workflows, runtime versions, environment variables, certificates, ports, and storage. Without standardized packages, a common failure mode is "works in the cloud, fails at the edge" due to missing libraries, mismatched CPU architectures, misconfiguration, or dependencies unavailable on-site.

Consistent packaging delivers:

- **Reproducibility:** the same artifact and equivalent configuration yield a predictable runtime environment.
- **Traceability:** knowing the exact source commit, dependencies, image digest, and configuration version deployed.
- **Controlled distribution:** artifacts are scanned, signed, and delivered through a registry or distribution repository.
- **Updates and rollback:** versioned releases can roll out by site cohorts and revert to a prior artifact.
- **Reduced drift:** limits discrepancies caused by manual installation or direct host edits.
- **Security:** separates secrets from packages and controls artifact provenance and deployment permissions.

Packaging does not mean every environment must use identical configurations. The binary or image can remain the same, while replica counts, endpoints, storage classes, network routes, resource limits, and security policies vary by environment.

## 2. Distinguishing artifacts, configuration, and runtime state

A consistent deployment should separate three categories:

| Category | Contents | How to manage |
|---|---|---|
| Artifact | Container image, VM image, binary, package, model, or static asset | Versioned, checksummed, signed, stored in a registry/artifact repository |
| Configuration | Endpoints, feature flags, resource sizing, ports, logging, region/site profiles | Managed per environment, reviewed, and versioned |
| Runtime state | Databases, queue offsets, business files, caches, checkpoints, and user data | Stored in storage/services with matching lifecycles; separate backup/replication |

Never bake runtime data or production secrets into an image. If an image embeds environment-specific configuration, moving the same artifact between staging, cloud, and edge becomes difficult. If state lives only in a container's writable layer, replacing the container can lose data.

A key principle is that artifacts should be immutable once built. When endpoints, secrets, or resource profiles need to change, deploy new configuration or runtime parameters rather than modifying the contents of a released image directly.

## 3. Choosing a package format per workload

Not every workload should use the same package format. The choice depends on how the application runs, OS requirements, hardware, and platform capabilities at the target location.

| Format | Contents | Suitable environments | Key considerations |
|---|---|---|---|
| OCI container image | Filesystem, runtime dependencies, metadata, and entrypoint | Kubernetes, container runtimes on VMs, edge gateways | CPU architecture, base image, volumes, networking, and runtime compatibility |
| VM image | OS, system packages, agents, and baseline config | Cloud VMs, on-prem hypervisors, environments needing a dedicated OS | Image format, boot mode, drivers, machine identity, and size |
| Native package | Binaries, libraries, and install metadata such as DEB/RPM/MSI | Server/edge hosts needing OS or service manager integration | OS dependencies, package signing, and upgrade workflows |
| Binary bundle | Executable and bundled libraries | Edge devices or minimal systems | ABI, libc, CPU architecture, certificates, and system libraries |
| Helm chart/Kubernetes manifest | Workload and Kubernetes resource definitions | Kubernetes on cloud, data center, or edge | Does not include runtime images; must align with cluster and API versions |
| Model/data artifact | Versioned ML models, rules, schemas, or static datasets | AI inference, analytics, and edge processing | Size, checksums, accelerator compatibility, and data lifecycle |

An application may require several coordinated artifacts. For example, a container image holds the API, a Helm chart defines the Deployment/Service, site configuration supplies endpoints, and secrets are injected from a secret manager. Components must have explicit versions and compatibility relationships.

## 4. Container images as application distribution units

OCI images are a common choice when workloads must run across multiple container runtimes. An image contains a filesystem and metadata telling the runtime the command, user, default environment, and entrypoint.

To make an image deployable across multiple environments:

- Pick a maintained base image that supports target CPU architectures.
- Package required runtime dependencies without relying on packages installed manually on the host.
- Use explicit `ENTRYPOINT`/`CMD` and run the primary process in the foreground.
- Never bake secrets, site IPs, or production hostnames into the image.
- Write logs to stdout/stderr or a standardized logging mechanism.
- Externalize persistent data to volumes or external storage services.
- Run as a non-root user with least privilege when supported by the application.
- Pin dependencies/base images and reference images by verified digest.

Example Dockerfile for an API:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --chown=10001:10001 app.jar /app/app.jar
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This is a simplified example. Production builds should pin the base image by an approved digest, verify CA certificates/timezone/native dependencies, and align JVM/resource profiles with container limits. `EXPOSE` is purely image metadata; it does not open firewalls or publish host ports.

Build the image once in the pipeline, scan and sign the artifact, and then promote the same digest across environments. Do not rebuild a separate image per site just to change an endpoint or secret.

## 5. Multi-platform images and CPU architecture differences

Cloud regions and edge devices may use different CPUs, such as `linux/amd64` and `linux/arm64`. One image tag can reference a manifest index containing multiple platform-specific child images. The runtime pulls the child image matching the host if the manifest includes an entry for it.

Example multi-platform build using Buildx:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/plant/edge-agent:2.3.0 \
  --push .
```

The command above requires a builder and registry that support multi-platform images. Verify:

- The base image publishes manifests for every required architecture.
- Native binaries, JNI, Python wheels, Node native addons, or drivers have compatible builds.
- Minimum CPU feature sets of the target edge devices.
- Emulated builds can be slow and do not replace benchmarking on real hardware.
- The image index points to the correct digest for each platform.

Java bytecode or cross-platform source code does not guarantee every package is compatible. JNI, OpenSSL providers, agents, GPU runtimes, and native dependencies can still be architecture-dependent.

If a device does not support the desired multi-platform image format, produce architecture-specific artifacts while preserving the same release version, test suite, and provenance. Never reuse a single tag to hide non-equivalent binaries without an explicit manifest.

## 6. Packaging VM images for workloads needing a dedicated OS

Some workloads require VM images instead of containers, such as network appliances, legacy software, agents needing kernel modules, or workloads with specialized OS requirements. A VM image can bundle the OS baseline, runtime, monitoring agents, and system packages.

To make VM images reusable across environments:

- Standardize OS version, kernel, boot mode, and partition layout.
- Install guest tools/agents matching the target hypervisor.
- Never hardcode IPs, hostnames, machine IDs, or host-specific certificates.
- Use cloud-init, Ignition, or an equivalent provisioning mechanism at boot when supported by the platform.
- Reset or regenerate SSH host keys, machine identities, and agent identities upon cloning.
- Keep business data outside the image; the image itself should be replaceable.
- Record image version, package inventory, checksums, and build provenance.

VM images may require format conversion or driver adjustments across hypervisors. An image that boots in the cloud is not automatically compatible with an on-prem hypervisor or edge appliance. Test boot, networking, storage, clocks, console access, and recovery on each target platform type.

## 7. Native packages and system services for edge hosts

An edge device might not run Kubernetes or a container runtime. In those cases, a DEB/RPM/MSI package or binary bundle paired with a service manager may fit better.

Example systemd unit for a background agent:

```ini
[Unit]
Description=Edge telemetry agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=edge-agent
Group=edge-agent
ExecStart=/opt/edge-agent/bin/agent --config /etc/edge-agent/config.yaml
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/edge-agent /var/log/edge-agent

[Install]
WantedBy=multi-user.target
```

Adjust examples to match the target distribution and real permissions. `network-online.target` does not guarantee Internet or cloud services are reachable; applications still need retries with backoff. `Restart=on-failure` does not replace health monitoring or safe update mechanisms.

Packages should have minimal install/uninstall scripts, preserve business data across upgrades, verify signatures, and declare dependencies explicitly. Avoid post-install scripts that download unverified binaries from the Internet.

## 8. Separating environment configuration from artifacts

The same image may need different configurations in cloud, on-prem, and edge environments. For example:

| Attribute | Cloud | On-premises | Edge site |
|---|---|---|---|
| API endpoint | Internal load balancer/service DNS | Internal DNS or service VIP | Gateway/site-local endpoint or cloud endpoint over tunnel |
| Resource profile | High vCPU/RAM, autoscaling | Fixed cluster capacity | Limited CPU/RAM, thermal/power limits |
| Storage | Managed database/object storage | Internal SAN/NAS/database | Local buffer/cache synced centrally |
| Network | VPC/VNet, private endpoints | VLANs, firewalls, proxies | Unstable WAN, NAT, private APN, or tunnel |
| Identity | Cloud IAM/workload identity | Internal directory or PKI | Unique device identity/certificate per device |
| Update channel | CI/CD and regional rollouts | Internal change windows | Site-cohort fleet rollout, deferred when offline |

Configurations should have schemas, safe defaults, validation, and versions. Example non-sensitive configuration file:

```yaml
service:
  name: edge-telemetry
  logLevel: INFO
  requestTimeout: 5s

runtime:
  maxWorkers: 4
  queueCapacity: 500

storage:
  localBufferPath: /var/lib/edge-agent/buffer
  maxBufferBytes: 1073741824

connectivity:
  upstream: https://telemetry.example.internal
  retry:
    initialDelay: 2s
    maxDelay: 2m
```

This file illustrates only non-secret configuration. Endpoints and worker counts are site-scoped values; credentials, private keys, and tokens must be provisioned separately. Applications should validate configuration before accepting traffic and fail clearly if required fields are missing.

## 9. Configuration profiles and schema versioning

When managing many sites, avoid copying and hand-editing a massive config file for every site. Split configuration into:

- **Base profile:** shared values and safe defaults.
- **Environment profile:** settings for cloud, staging, on-prem, or edge.
- **Site profile:** site-specific endpoints, timezone, device mappings, and resource caps.
- **Secret reference:** secret name/ID in a secret manager or device keystore, never inline secrets.

Every profile should carry a schema version and compatibility rules. When adding fields, prefer meaningful defaults so older versions do not break. When removing or changing field semantics, establish a migration path and verify which versions are active across all sites.

Example repository layout:

```text
deployment/
  base/
    app-config.yaml
    resource-defaults.yaml
  environments/
    cloud-prod.yaml
    datacenter-prod.yaml
    edge-default.yaml
  sites/
    plant-001.yaml
    store-014.yaml
  schemas/
    app-config-v2.schema.json
  manifests/
    deployment.yaml
    service.yaml
```

This layout is merely illustrative. Site-specific configs must have access controls; never store private keys or passwords in a Git repository, even a private one.

## 10. Packaging deployment manifests

A container image describes the application, whereas a deployment manifest describes how to run it in the target environment. For Kubernetes, manifests can declare Deployments, DaemonSets, StatefulSets, Jobs, Services, volumes, resource requests/limits, security contexts, and probes.

Example Deployment using an image digest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: edge-telemetry
spec:
  replicas: 2
  selector:
    matchLabels:
      app: edge-telemetry
  template:
    metadata:
      labels:
        app: edge-telemetry
    spec:
      containers:
        - name: agent
          image: registry.example.com/edge/telemetry@sha256:REPLACE_WITH_VERIFIED_DIGEST
          env:
            - name: CONFIG_PATH
              value: /etc/edge-agent/config.yaml
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          volumeMounts:
            - name: config
              mountPath: /etc/edge-agent
              readOnly: true
            - name: state
              mountPath: /var/lib/edge-agent
      volumes:
        - name: config
          configMap:
            name: edge-telemetry-config
        - name: state
          persistentVolumeClaim:
            claimName: edge-telemetry-state
```

The digest in this example is a placeholder and must be replaced with a real verified digest. Manifests must be adapted to each cluster: small edge sites may run only one replica; storage classes and PVCs may differ; security contexts, service accounts, network policies, and probes must be added per application.

Never put secrets directly in manifests or ConfigMaps. Use Secrets, external secret providers, or device keystores as supported by the platform. ConfigMaps are generally suited for non-sensitive config and can be mounted read-only.

## 11. Helm, Kustomize, and per-environment configuration

Helm charts or Kustomize help reuse manifests and create environment overlays.

- **Helm:** templates manifests using values; fits when you need versioned packages, dependencies, and deployment parameters.
- **Kustomize:** patches/overlays base manifests without requiring a template engine; useful for per-site/cluster configuration.
- **Plain manifests:** suitable for small workloads or environments with few variants, provided versions and reviews are controlled.

Example Kustomize layout:

```text
k8s/
  base/
    deployment.yaml
    service.yaml
    kustomization.yaml
  overlays/
    cloud-prod/
      kustomization.yaml
      replicas-patch.yaml
    datacenter-prod/
      kustomization.yaml
      storage-patch.yaml
    edge-small/
      kustomization.yaml
      resources-patch.yaml
```

Overlays should contain only necessary differences. If one site ends up with an entirely different manifest due to excessive forks, revisit your abstractions and standardize platform capabilities. Avoid creating giant templates packed with hundreds of conditional flags that obscure the final output.

Before deploying, render the final manifest and inspect the diff. Operators should clearly see the exact image digest, replicas, resource limits, volumes, ports, service accounts, and policies actually applied.

## 12. Packaging dependencies and external services

Workloads may depend on databases, message brokers, DNS, identity providers, object storage, external APIs, or on-site devices. An application package alone cannot guarantee those dependencies exist.

Maintain a dependency manifest documenting:

- Service names and required protocol/API versions.
- DNS names, ports, and connection directions.
- Authentication mechanisms and certificate trust.
- Latency, throughput, and timeout requirements.
- Mandatory dependencies versus optional dependencies.
- Behavior when a dependency is offline: retry, buffer, degrade, or fail fast.
- Data schemas/versions and compatibility policies.

For the edge, distinguish local dependencies from cloud dependencies. For example, an edge agent can write to a local queue when the WAN drops, then sync to the cloud upon recovery. Do not let the application block indefinitely waiting for a cloud service if local operations must continue.

## 13. Packaging data and state separately from application releases

Images and manifests should not store business data. Define where state resides:

- Managed or on-prem databases.
- Persistent volumes with backup/replication.
- Object storage for large files and artifacts.
- Local disk/SSD for bounded caches, spools, or offline buffers.
- Message queues or event logs for pending work.
- Model stores for versioned and checksummed ML models.

When updating workloads, state must have a compatibility plan. For example, a new release adds a database column while older versions still run at offline edge sites. Use expand-and-contract: deploy compatible schema additions first, roll out the application, wait until the fleet updates sufficiently, and remove old fields only in a later release.

Local edge buffers need quotas, retention policies, and overflow handling. Set capacity caps, event priorities, producer backpressure, and alerts when syncing lags. Never allow logs or caches to fill the disk and prevent the device from booting.

## 14. Secrets, certificates, and device identity

Hybrid/edge environments involve multiple identity types: cloud workload identities, cluster service accounts, VM machine identities, and per-gateway device identities.

Principles:

- Never bake secrets into container images, VM images, or packages.
- Inject credentials at deploy/boot via a secret manager, workload identity, TPM, or secure keystore when available.
- Give each device/site a distinct identity; avoid sharing a single private key across the fleet.
- Set certificate lifetimes with rotation and revocation processes.
- Scope authorization by site, workload, and action type.
- Provide initial identity bootstrapping and procedures for lost/revoked devices.
- Never log private keys, tokens, or full secret responses.

Edge devices can remain offline for extended periods, so certificate rotation needs grace periods and sync mechanisms. Never embed permanent credentials in images to prevent cloned devices from sharing identities.

## 15. Packaging for air-gapped or intermittently connected environments

Edge sites may have restricted Internet access, private WANs, or hours/days of disconnection. Packaging must support distribution and operations under these conditions.

Prepare:

- OCI image archives or an internal registry mirror if sites cannot reach the central registry.
- Signed native packages and dependency bundles for direct host installation.
- Pre-rendered manifests, charts, and site configurations.
- SBOMs, signatures, checksums, and release metadata.
- Required model/data artifacts with checksums/versions.
- Offline installation, verification, rollback, and recovery runbooks.
- List of dependencies required on-site and local cache/fallback mechanisms.

Example exporting and loading an image archive:

```bash
docker save registry.example.com/edge/telemetry:2.3.0 -o telemetry-2.3.0.tar
sha256sum telemetry-2.3.0.tar > telemetry-2.3.0.tar.sha256

# At the edge site after verifying checksum and signature
sha256sum -c telemetry-2.3.0.tar.sha256
docker load -i telemetry-2.3.0.tar
```

Checksums detect tampering only if the checksum file comes from a trusted source. An attacker can replace both the archive and checksum if the distribution channel is unauthenticated. Sign release artifacts or manifests with a protected key and verify signatures at the site.

If using a container runtime other than Docker, use the corresponding OCI image export/import tooling. Archives should carry version and architecture metadata; a registry mirror is generally easier to manage when sites have stable internal connectivity.

## 16. Site release bundles

A release bundle can package everything required for an offline or phased site deployment:

```text
release-2.3.0/
  release-manifest.json
  images/
    telemetry-linux-amd64.oci.tar
    telemetry-linux-arm64.oci.tar
  deployment/
    rendered-manifest.yaml
    site-config.yaml
  packages/
    edge-agent_2.3.0_arm64.deb
  models/
    detector-v7.onnx
  security/
    sbom.spdx.json
    provenance.json
    release-signature.sig
    checksums.txt
  docs/
    install.md
    rollback.md
```

This bundle structure is an example, not a mandatory standard format. `release-manifest` should list artifacts, versions, digests, platforms, dependencies, and runtime requirements. Do not place secrets inside the bundle; provision secrets separately at the site.

A bundle needs a signed manifest so devices can verify every file. After import, record the release ID, installed digest, site ID, timestamp, health check result, and the operator/automation that performed it.

## 17. Supply chain: SBOM, provenance, and signatures

Because a package may run in many places, you need verifiable evidence of its origin and composition.

- **SBOM:** inventory of packages, libraries, and versions inside the artifact.
- **Provenance:** details on source, builder, pipeline, parameters, and build process.
- **Signature:** cryptographic proof that the artifact was signed by a trusted publisher/key.
- **Digest/checksum:** immutable content identifier and tamper detection.
- **Vulnerability scan:** checks components against known vulnerabilities.

Pipelines should generate SBOMs/provenance at build time, sign artifacts, store them with release metadata, and verify them before deployment. For offline edge sites, public keys or trust roots must be securely pre-provisioned with update/revocation procedures.

Vulnerability scanning does not prove a package is completely safe. Evaluate severity, exploitability, whether the vulnerable component is actually reachable, and whether patches are device-compatible. If immediate patching is impossible, document exceptions, affected device scope, and compensating controls.

## 18. Build-once, deploy-to-many-environments workflow

A reference pipeline:

1. Check out source at a specific commit.
2. Resolve dependencies from controlled repositories using lockfiles.
3. Run unit/integration tests and static analysis.
4. Build artifacts for all supported target platforms.
5. Package container images/VM images/native packages via standardized workflows.
6. Generate SBOM, provenance, checksums, and sign artifacts.
7. Scan for vulnerabilities and enforce policy gates before promotion.
8. Push artifacts to a registry or distribution store.
9. Generate/render per-environment configuration and validate schemas.
10. Deploy to test/staging or an edge pilot; verify health, data paths, and performance.
11. Promote the exact same digest/release ID to subsequent environments.
12. Record per-site state and monitor for drift.

Never rebuild solely to rename an environment. Rebuilding can yield different outputs from identical source due to floating dependencies, timestamps, or updated base images. If architecture-specific artifacts are needed, produce them within the same release and link them under a shared manifest/version.

## 19. Deploying configuration via Infrastructure as Code

Application artifacts and infrastructure must be versioned separately yet linked via releases. Infrastructure as Code (IaC) describes networks, compute, storage, IAM, load balancers, and platform resources so they can be reviewed and reproduced.

Example organization:

```text
platform/
  modules/
    network/
    compute/
    storage/
    identity/
  environments/
    cloud-prod/
    datacenter-prod/
    edge-fleet/
applications/
  telemetry/
    image-version.txt
    manifests/
    config-schema/
```

IaC requires state management, backend access control, secret handling, and drift detection. Never commit state files containing secrets to public repositories. For edge devices lacking a cloud control plane, use configuration management/agents and signed desired-state manifests to sync config.

Do not force every environment into a single IaC module if underlying APIs and capabilities diverge significantly. Reuse shared modules/contracts and build platform-specific adapters, provided outputs and policies are checked consistently.

## 20. Site-by-site rollout and fleet management

An edge fleet can span dozens to thousands of sites. Updating the entire fleet simultaneously creates a huge blast radius; roll out in cohorts and verify results per wave.

Rollout rings may include:

- Lab/test devices.
- Pilot sites representing diverse hardware and networks.
- Small canary cohort.
- Regional/site waves.
- Full fleet after exit criteria pass.

Each site should report back:

- Site/device identity and platform version.
- Desired release and actual release digest.
- Artifact download, installation, and startup status.
- Health/readiness, resource usage, and disk capacity.
- Last update timestamp and most recent errors.
- Cloud/control plane connectivity status.

Fleet managers must handle offline sites, interrupted updates, device replacements, and version skew. Never equate "rollout command sent" with "device updated successfully." Confirm actual reported state from each site or explicitly flag unreported devices.

## 21. Safe updates: canary, rolling, and blue-green

Deployment strategies involve distinct trade-offs:

| Strategy | Mechanism | Advantages | Risks/prerequisites |
|---|---|---|---|
| Rolling update | Replaces batches of instances/containers sequentially | Resource-efficient, gradual rollout | Requires concurrent version compatibility and spare capacity |
| Canary | Updates a small percentage of sites/replicas first | Limits blast radius and gives early signal | Requires reliable metrics/feedback and clear promotion gates |
| Blue-green | Maintains two environments, cuts traffic over to new version | Fast rollback via traffic shift | Temporarily consumes extra capacity and requires data/schema coordination |
| Staged offline update | Delivers bundles to sites during connectivity/maintenance windows | Fits connectivity-constrained edge | Sites may update slowly; needs expiry and desired/actual tracking |

Before updating, verify API, schema, message, and data compatibility. In hybrid setups, new cloud releases may communicate with older edge versions for days; protocols must remain backward-compatible throughout the rollout window.

## 22. Rollback and data compatibility

Package rollback typically means redeploying the previous artifact. However, rolling back an application does not automatically revert database, message, or local data changes.

Rollback design needs:

- Stored digests and release metadata for prior versions.
- Previous packages/images retained in the registry or site cache per retention policy.
- Checks verifying schema/API compatibility when reverting.
- Expand-and-contract for database migrations.
- Checkpoints and backups for local state requiring preservation.
- Guards preventing two versions from writing incompatible data concurrently.
- Clear criteria for which sites can auto-rollback vs. require intervention.
- Verification that the older artifact remains security-supported and free of critical known vulnerabilities.

For offline edge sites, rollback may have to run locally using a cached bundle. Retain at least one prior release compatible with current storage/schemas and verify checksums before reinstalling.

## 23. Drift and verifying actual state

Configuration drift occurs when live environments diverge from versioned desired configuration. Causes include manual host edits, out-of-band changes, incomplete updates, or sites running stale profiles.

Countermeasures:

- Store desired configuration and release IDs in a source of truth.
- Have agents/cluster controllers periodically report actual versions and config hashes.
- Compare desired vs. actual and classify allowed vs. disallowed differences.
- Restrict direct production edits; emergency changes must be logged and backported into the source of truth.
- Alert on sites failing to update or running outdated config schemas.
- Implement safe reconciliation workflows that avoid overwriting local data or causing downtime.

Not every difference is bad drift. Values like device calibration, local network routes, or physical capacity may be managed independently. Define explicitly which fields can vary per site and which must strictly match central configuration.

## 24. Example: the same telemetry workload across cloud, data center, and edge

A workload collects telemetry from industrial machines. At the edge, an agent reads device data, buffers locally during WAN disruptions, and ships to the cloud when connected. In the data center, a service processes data from internal systems. In the cloud, workers analyze and store long-term data.

Packaging design:

| Component | Cloud | Data center | Edge |
|---|---|---|---|
| Application artifact | Same release image, matching platform | Same release image or compatible package | ARM64/AMD64 image or native package per device |
| Runtime | Kubernetes/container service | On-prem Kubernetes or container runtime | Lightweight Kubernetes, container runtime, or systemd |
| Config | Cloud endpoints, autoscaling, managed storage | Internal endpoints, internal storage | Site ID, device mappings, local buffer, WAN retries |
| Identity | Workload identity/service account | Internal PKI/identity | Unique device certificate per gateway |
| Data state | Database/object storage | Internal database or message broker | Local spool/cache with quotas and sync cursors |
| Update | CI/CD rolling/canary | Change windows and staged rollouts | Signed bundles, site cohorts, offline rollback |

Release workflow:

1. Build multi-architecture images for cloud and edge targets.
2. Generate SBOM, provenance, signatures, and release manifests.
3. Test on representative edge hardware and cloud clusters.
4. Generate per-site configurations containing only non-sensitive values.
5. Provision per-device identities and secrets outside the image.
6. Deploy cloud/data center components first or in dependency order.
7. Roll out to an edge pilot group; confirm actual digests and telemetry flows.
8. Expand by site waves; offline devices receive updates upon reconnecting per policy.
9. Monitor version drift, buffer utilization, sync lag, and device errors.

In this example, the same application logic ships under one release ID while configuration, resources, and installation methods adapt per environment. This preserves software consistency while respecting each site's constraints.

## 25. Pre-rollout package testing

Testing must prove artifacts work on the exact target platforms and configurations:

1. **Artifact integrity:** valid digest, signature, and provenance.
2. **Platform compatibility:** matching CPU architecture, OS, kernel, runtime, and drivers.
3. **Configuration validation:** valid schemas, defaults, secret references, and endpoints.
4. **Dependency testing:** working DNS, ports, certificates, identities, and service contracts.
5. **Resource testing:** CPU, memory, disk, network, and accelerators stay within limits.
6. **Offline testing:** workload maintains permitted behavior when WAN/cloud disconnects.
7. **Recovery testing:** safe handling of process restarts, node reboots, disk full, and power loss.
8. **Update testing:** upgrades, interrupted updates, and rollbacks on representative hardware.
9. **Security testing:** user privileges, secret handling, image scans, and network policies.
10. **Observability testing:** logs, metrics, events, and version status are shipped or buffered locally.

Do not test solely on developer laptops. Edge hardware can differ in CPU features, storage speed, thermals, power, and networking. Maintain a test matrix representing supported hardware families.

## 26. Common mistakes

- **Building separate images per environment:** artifacts diverge over time and lose traceability. Build once, inject config per environment.
- **Embedding secrets in images or bundles:** credentials leak across every site. Provision per-device secrets/identities separately.
- **Assuming one image runs on every CPU:** native dependencies can fail across architectures. Build and test multi-platform.
- **Baking site config into images:** makes promotion and rollback painful. Separate base/environment/site profiles.
- **Not pinning image digests:** mutable tags can point to different content. Deploy by verified digest.
- **Testing only in the cloud:** overlooks offline mode, tight disk space, and edge hardware quirks. Test on representative devices.
- **Updating the entire fleet at once:** a bad release impacts every site. Use pilots, canaries, and wave rollouts.
- **Not caching prior packages at the edge:** disconnected sites cannot roll back. Retain the previous release locally and manage retention.
- **Rolling back apps without checking schema/state:** older code may fail on newer data. Use schema compatibility and checkpoints.
- **Not verifying actual state:** rollout jobs report success while devices remain un-updated. Collect desired/actual digests and health reports.
- **Leaving local buffers unbounded:** full disks crash workloads. Enforce quotas, retention, and backpressure.
- **Sharing one credential across the fleet:** one compromised device exposes every site. Use unique identities with revocation workflows.

## 27. Multi-environment packaging and deployment checklist

**Artifacts and builds**

- [ ] Artifacts have traceable version/release IDs, digests, and build provenance.
- [ ] Base images/runtimes/dependencies are pinned with an update process.
- [ ] Verified CPU architecture, OS, kernel, drivers, and native dependencies.
- [ ] Generated SBOM, provenance, signatures, and vulnerability scans per policy.
- [ ] Artifacts contain no secrets, IPs, or site-specific configuration.

**Configuration and manifests**

- [ ] Clearly separated base, environment, and site profiles.
- [ ] Configuration includes schema versions, validation, and safe defaults.
- [ ] Final manifests rendered/reviewed; resources, volumes, ports, identities, and policies verified.
- [ ] Secrets/certificates provisioned separately via secret manager, PKI, or device keystore.
- [ ] Dependencies and outage behaviors documented.

**Distribution and rollout**

- [ ] Registries/repositories or offline bundles enforce signature/checksum verification.
- [ ] Local caches/mirrors provided for sites without Internet access.
- [ ] Pilot/canary/site-wave rollouts with explicit promotion criteria.
- [ ] Package rollback, schema compatibility, and edge retention verified.
- [ ] Desired/actual releases, config hashes, and site health tracked.

**Operations**

- [ ] Local state, buffers, checkpoints, and logs enforce quotas/retention.
- [ ] Tested WAN outages, reboots, disk pressure, interrupted updates, and recovery.
- [ ] Logs/metrics/tracing and status reporting work upon reconnection.
- [ ] Rotation/revocation procedures exist for device identities and certificates.
- [ ] Owners, runbooks, and security patch schedules defined per platform type.

Packaging workloads for consistent multi-environment deployment requires separating immutable artifacts from configuration and state, selecting suitable package formats, securing the supply chain, and standardizing rollout workflows. For hybrid and edge, add multi-architecture support, offline distribution, per-device identities, site-scoped configuration, and resilient update/rollback capabilities. When these pieces are versioned, verified, and observed end-to-end, a single release can operate predictably across cloud, data center, and edge while respecting each environment's unique constraints.
