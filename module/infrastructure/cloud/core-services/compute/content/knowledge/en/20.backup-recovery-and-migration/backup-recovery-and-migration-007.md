# Evaluating Compatibility Before Changing CPU Architecture or Cloud Provider

Moving a workload from x86-64 to Arm64, switching CPU generations, or migrating VMs from one cloud provider to another can reduce costs and broaden infrastructure choices. However, an image that boots does not guarantee the application runs correctly, meets performance targets, or preserves current security and operational properties.

Compatibility must be evaluated across multiple layers: CPU instruction sets, ABIs, binaries and native libraries, operating systems, kernels, firmware, images/containers, runtimes, drivers, cloud services, data, licensing, and operational workflows. When changing cloud providers, you must also examine differences in networking, storage, identity, secrets, load balancers, monitoring, and management APIs.

This lesson provides a pre-migration assessment workflow, from building an inventory and compatibility matrix to benchmarking, backup/restore, cutover, and rollback. The goal is to spot incompatible components early, quantify risk, and migrate workloads only when evidence confirms functional, performance, security, RTO/RPO, and cost requirements are met.

## 1. Define the Exact Change Being Made

Before checking compatibility, clearly state the scope of the change. The cases below carry different risk profiles.

| Change Type | Example | Primary Risks |
|---|---|---|
| Switching CPU generation or vendor within the same ISA | Intel x86-64 to AMD x86-64 | CPU feature flags, microcode, performance, NUMA, and licensing |
| Switching CPU architecture | x86-64 to Arm64 | Binaries, native libraries, kernel modules, runtimes, and images |
| Switching cloud providers | Provider A to Provider B | APIs, IAM, networking, storage, managed services, images, and data |
| Combined architecture and provider switch | x86-64 VM on Provider A to Arm64 on Provider B | All layers above plus data and operational migration risks |

Changing CPU vendors within the same ISA is usually simpler than switching ISAs. Still, two x86-64 CPUs can differ in instruction extensions, single-core performance, memory bandwidth, NUMA topology, or instance limits.

Switching cloud providers does not require changing CPU architecture at the same time. You can migrate an x86-64 workload between providers first to decouple service dependencies, then evaluate Arm64 in a separate phase. Isolating changes makes root-cause analysis far easier if benchmarks or tests fail.

### Document Before-and-After States Explicitly

A migration specification should state:

- Source and target architecture: x86-64, Arm64, or specific CPU family.
- Source and target OS and version.
- VM type or container runtime.
- Cloud provider, region, and zone.
- Managed services in use.
- Data and replication model.
- SLOs, RTO, RPO, and downtime windows.
- Security, compliance, and licensing constraints.
- Success criteria and rollback conditions.

Never start with "move to an equivalent new machine." Equivalence must be defined by workload capability and behavior, not merely vCPU count or RAM size.

## 2. Distinguishing ISA, Microarchitecture, and ABI

### Instruction Set Architecture (ISA)

An ISA defines the instruction set and execution model available to machine software. Examples:

- x86-64 or AMD64.
- AArch64, commonly called Arm64.

Binaries compiled for x86-64 normally cannot execute natively on Arm64 CPUs, and vice versa, unless an emulation or binary translation layer is present. Emulation may run certain applications, but does not automatically guarantee production performance, stability, or vendor support.

### Microarchitecture

Microarchitecture is how a specific CPU implements an ISA: pipelines, caches, branch prediction, core counts, vector units, memory controllers, and related traits.

Two CPUs sharing the same ISA can still deliver vastly different performance. Workloads sensitive to single-thread latency, memory bandwidth, cache size, or vector instructions must be benchmarked on the target machine type.

### ABI (Application Binary Interface)

An ABI governs how binaries interact with the OS and libraries: calling conventions, register usage, data types, alignment, system call interfaces, and binary formats.

A program matching the ISA can still fail to execute if the ABI, dynamic loader, or system libraries are incompatible.

### CPU Features and Extensions

Beyond the base ISA, CPUs support optional extensions, such as:

- SIMD/vector instructions like SSE, AVX, or AVX-512 on certain x86 CPUs.
- NEON or SVE on corresponding Arm platforms.
- Extensions for cryptography or atomic operations.

Binaries built requiring extensions absent on the target CPU can crash at runtime—for instance, with an illegal instruction fault. Builds should target baseline features supported across all target machine types, or detect capabilities at runtime and dispatch appropriate code paths.

Never infer extensions solely from an architecture name. Check CPU feature flags on target instances and provider instance-family documentation.

## 3. Inspecting Source CPU Architecture and OS

### Linux

Inspection commands:

~~~sh
uname -m
lscpu
cat /proc/cpuinfo
getconf LONG_BIT
cat /etc/os-release
uname -r
~~~

Meaning:

- `uname -m` reports the machine architecture reported by the running kernel.
- `lscpu` displays CPU architecture, model, sockets, cores, threads, and flags.
- `/proc/cpuinfo` presents CPU details as exposed by the kernel.
- `getconf LONG_BIT` indicates whether user space runs in 32-bit or 64-bit mode.
- `/etc/os-release` identifies the distribution and version.
- `uname -r` shows the running kernel release.

VMs may expose virtualized CPU models. Combine guest inspection with the provider's instance-type metadata.

### Windows

PowerShell commands:

~~~powershell
Get-CimInstance Win32_Processor |
  Select-Object Name, Manufacturer, Architecture, AddressWidth, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, OSArchitecture

systeminfo
~~~

Architecture codes in WMI may differ from common naming; cross-reference Windows Management Instrumentation documentation and OS version details.

### Inspecting Applications and Binaries

Linux:

~~~sh
file /opt/app/bin/service
readelf -h /opt/app/bin/service
readelf -A /opt/app/bin/service
~~~

These commands reveal ELF type, machine architecture, and certain ABI attributes. For native libraries, inspect every critical shared object, not just the main executable.

On Windows, tools like `dumpbin /headers` in the Visual Studio Developer Command Prompt show the machine type of PE binaries. Inspect native DLLs loaded by the application as well.

Never execute or load untrusted binaries merely to inspect them. Use static analysis tools and appropriate sandboxed environments.

## 4. Inventorying Binaries, Libraries, and Native Components

This step usually surfaces the most issues when switching from x86-64 to Arm64.

### Components to Inventory

- In-house compiled executables.
- Shared libraries such as .so, .dll, or .dylib files.
- Language native extensions.
- Database drivers and client libraries.
- Security, monitoring, and backup agents.
- Kernel modules and device drivers.
- Runtime launchers and JIT compilers.
- Packages installed from OS repositories.
- Vendor tools or commercial software.
- Scripts invoking external binaries.

A Java application using JVM bytecode generally migrates architectures more easily than C/C++ binaries statically built for x86-64. However, if Java uses JNI, Netty native transports, compression libraries, cryptographic providers, or native agents, those pieces still need Arm64-compatible builds.

Pure Python code is generally portable, whereas packages with C/C++ extensions need wheels matching the platform tag. Node.js native addons likewise require matching binaries. Go binaries must compile for the target GOARCH along with any cgo native dependencies.

### Checking Dynamic Dependencies

On Linux, use `readelf -d` or `objdump -p` to inspect dynamic dependencies. `ldd` is convenient for trusted binaries in controlled environments, but avoid running it on untrusted executables because some implementations can execute code during inspection.

Verify:
- Whether libraries exist for the target architecture.
- Whether versions and SONAMEs are compatible.
- Whether the dynamic loader path matches.
- Whether glibc or musl versions meet requirements.
- Whether any dependency is published exclusively for x86-64.
- Whether licenses restrict CPU model, socket, or core count.

### Native Dependency Matrix

| Component | Source Architecture | Target Artifact | Status to Record |
|---|---|---|---|
| Application binary | x86-64 | Arm64 build | Supported / rebuild / unsupported |
| Native library | x86-64 | Arm64 package | Version and ABI |
| Database driver | x86-64 | Arm64 package | Vendor support |
| Monitoring agent | x86-64 | Arm64 agent | Feature parity |
| Security agent | x86-64 | Arm64 agent | Vendor certification |
| Kernel module | Source kernel/arch | Target module | Build and signing |
| Backup agent | x86-64 | Arm64 package | Restore compatibility |

A component lacking an Arm64 build does not necessarily block the whole migration if it can be replaced or removed. However, document an explicit decision and test it—never ignore it simply because the main binary starts up.

## 5. Checking OS, Kernel, and Firmware

### OS Releases and Support Lifecycle

Confirm the target OS supports the new architecture and remains within vendor support windows. Check:

- Distribution release and repositories.
- Kernel version and configuration.
- glibc/musl and dynamic loader.
- Package availability per architecture.
- Security updates and patch cadence.
- Init system and service manager.
- BIOS/UEFI boot mode.
- Secure Boot and kernel module signing.
- TPM/vTPM if depended upon by the application.
- Drivers and guest tools.

An x86-64 image cannot boot natively on Arm64. You must build or select an architecture-specific image.

### Kernel Modules and Drivers

Kernel modules depend on both architecture and kernel ABI. Modules for filesystems, networking, storage, GPUs, security monitoring, or backups may need separate builds.

Check:
- Whether module source or packages exist for the target architecture.
- Whether the target kernel version is supported.
- Whether module signing and Secure Boot succeed.
- Whether drivers offer feature parity.
- Whether the vendor certifies that instance family and OS combination.

### Firmware and Virtual Devices

VMs may expose different virtual devices across providers or instance families. Check drivers for:
- Block storage and NVMe.
- Virtual network interfaces.
- Consoles and boot devices.
- Entropy/random sources.
- GPUs or accelerators.
- TPM/vTPM.
- Timekeeping and clock sources.

Different providers may use different firmware, device models, and guest agents. Test images on actual target VM types, not solely inside emulators.

### Cloud-Init and Bootstrapping

Initialization scripts often bake in assumptions:
- Device names like `/dev/sda`.
- Packages available on only one architecture.
- Repositories or URLs downloading x86-64 binaries.
- Hardcoded network interface names.
- Provider-specific metadata endpoints.
- Provider-specific user-data syntax or agents.

Changing providers requires auditing bootstrap scripts, cloud-init, startup scripts, and configuration management.

## 6. Runtime and Programming Language Compatibility

### Java/JVM

Java bytecode is generally portable across architectures given a compatible JDK/JRE. Check:
- Whether the JDK vendor and version support the target architecture.
- Whether native/JNI libraries have matching builds.
- JVM flags and JIT behavior.
- Garbage collector and CPU feature support.
- Container awareness and effective CPU count.
- APM, profiler, security, and monitoring agents.

Never assume identical JVM performance simply because bytecode stays unchanged. The JIT emits architecture-specific machine code, requiring benchmarks for warm-up, throughput, GC, and tail latency.

### .NET

Check runtime versions, architecture packages, native dependencies, globalization libraries, profiler/diagnostic agents, and vendor support matrices. Some workloads use framework-dependent deployments, yet the target host runtime must still match.

### Python

Check:
- Python interpreter architecture.
- Wheel availability for the platform tag.
- Native extensions and system libraries.
- Source-only packages requiring compilers.
- C/C++/Fortran dependencies.
- Runtime performance and numerical library support.

If building wheels from source, verify CI toolchains and system dependencies.

### Node.js

Check:
- Node runtime architecture and version.
- Native addons such as node-gyp modules.
- Prebuilt binary availability.
- OpenSSL and system library compatibility.
- Build scripts and package postinstall steps.
- Instrumentation agents.

### Go, Rust, C/C++

Go and Rust generally offer strong cross-compilation support, though targets, cgo, and native dependencies must be verified. C/C++ requires matching toolchains, sysroots, compiler flags, ABIs, and CPU baselines.

Cross-compiling cleanly is not enough. Test runtime behavior, concurrency, memory ordering, cryptography, SIMD paths, and execution on the target CPU.

## 7. Container Images and Multi-Architecture

### Image Manifest Lists

OCI images can publish as multi-platform image indexes containing per-architecture manifests such as linux/amd64 and linux/arm64. Container runtimes pull the manifest matching the node.

Sharing the same tag does not guarantee multi-arch support. If a registry only holds an amd64 manifest, pods scheduled onto Arm64 nodes will fail to pull or crash.

### Inspecting Images

Commands:

~~~sh
docker buildx imagetools inspect registry.example.com/team/api:1.4
docker manifest inspect registry.example.com/team/api:1.4
~~~

Exact tooling and output depend on Docker/Buildx versions. Verify the manifest includes target platforms, valid digests, and provenance.

### Multi-Architecture Builds

Example using Buildx:

~~~sh
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/team/api:1.4 \
  --push .
~~~

The Dockerfile must use base images supporting both architectures. Every package installed during build stages and binaries copied into runtime stages must match the target platform.

### Cross-Builds vs. Native Builds

Cross-builds can produce binaries for another architecture, though certain packages need to run tests or code generation natively on the target. Use native builders per architecture or emulation in CI.

QEMU/emulation helps for builds and smoke tests, but does not accurately represent native hardware performance, timing, or behavior. Production benchmarks must run on real target CPUs.

### Kubernetes Scheduling

When a cluster mixes node architectures:
- Apply accurate architecture and OS labels to nodes.
- Use nodeSelector or node affinity if workloads require specific binaries.
- Verify image manifests.
- Confirm DaemonSet agents have architecture-compatible images.
- Verify CSI/CNI and device plugins.
- Prevent pods from scheduling onto incompatible nodes.

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-arm64
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-arm64
  template:
    metadata:
      labels:
        app: api-arm64
    spec:
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
        - name: api
          image: registry.example.com/team/api:1.4
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "1Gi"
~~~

This example constrains the workload to Arm64 nodes. The image still needs an Arm64 manifest, and cluster dependencies must support that node architecture.

## 8. Evaluating CPU Features and Application Performance

Functional compatibility does not equal identical performance.

### Contributing Factors

- Core and thread counts.
- Single-thread performance.
- Clock behavior and sustained frequencies.
- Cache size and hierarchy.
- Memory bandwidth and latency.
- NUMA topology.
- SIMD/vector support.
- CPU credits or burst behavior.
- Thermal/power policies.
- Hypervisor scheduling and CPU quotas.
- Compiler/JIT optimizations.
- Hardware encryption/compression instructions.
- GPU or accelerator attachment.

An 8-vCPU instance on Provider A is not inherently equivalent to an 8-vCPU instance on Provider B. A vCPU may represent a hardware thread or a distinct scheduling unit depending on machine family.

### Realistic Workload Benchmarking

Use representative workloads rather than synthetic CPU microbenchmarks alone. Measure:
- Throughput.
- p50/p95/p99 latency.
- CPU time and per-core utilization.
- Memory footprint and allocation rates.
- GC pauses or runtime pauses.
- Disk IOPS/throughput/latency.
- Network throughput/latency.
- Queue depth and concurrency.
- Error rates and timeouts.
- Cost per request or transaction.

### Load Testing Methodology

Execute sequentially:
1. Warm up runtimes and caches.
2. Run baseline load.
3. Ramp up to target load.
4. Run burst tests.
5. Sustain load long enough to expose throttling or leaks.
6. Test with one replica/site unavailable.
7. Compare against source baselines.
8. Repeat enough times to reduce measurement noise.

Establish pass thresholds before testing—for example, p95 latency degrades by no more than 10% at target load and cost per request drops by at least an agreed percentage. Concrete thresholds must reflect SLOs and business goals rather than universal defaults.

## 9. Checking Commercial Software and Licensing

Licenses may depend on:
- Physical core or vCPU count.
- Socket or host count.
- CPU vendor/model.
- Cloud provider or authorized environments.
- Instance families and dedicated hosts.
- Architecture.
- Region or deployment environment.
- Node or concurrent instance count.

A license valid on x86-64 at the current provider does not automatically carry over to Arm64 or a new provider. Contact vendors and retain written confirmation whenever platform-bound license terms exist.

Audit:
- Database engines and extensions.
- Backup/restore agents.
- Security/EDR tools.
- Monitoring/APM tools.
- Middleware and message brokers.
- Commercial runtimes.
- GPU software stacks and drivers.

Include licensing in TCO. A cheaper Arm64 instance may not lower total cost if an agent or database license lacks support or forces maintaining a separate x86-64 pool.

## 10. Evaluating Compatibility When Switching Cloud Providers

Changing providers changes the platform contract. Applications often depend on numerous APIs and services absent from core business code.

### Compute and Images

Check:
- Instance families and CPU architectures.
- Image formats, boot modes, and guest drivers.
- Metadata services and instance identities.
- Startup/user-data mechanisms.
- Autoscaling and lifecycle hooks.
- Consoles, serial access, and rescue workflows.
- Quotas, regions, AZs, and capacity reservations.

Provider image snapshots are rarely directly portable artifacts. You may need to export, convert, import, or rebuild images from standardized pipelines. Verify licensing, encryption, and boot settings throughout the transfer.

### Networking

Check mappings across:
- VPC/VNet and subnets.
- Route tables and route propagation.
- Security groups/firewalls/NACLs.
- Private endpoints and service endpoints.
- NAT gateways and egress.
- L4/L7 load balancers.
- DNS, private DNS, and service discovery.
- Static IPs, floating IPs, and public IPs.
- Peering, VPNs, Direct Connect/ExpressRoute/Interconnect.
- Kubernetes network policies.

Never translate rules by name without checking semantics. One provider may enforce stateful firewalls while another uses stateless NACLs or different rule evaluation orders.

### Storage and Data

Check:
- Block volume types, IOPS, and throughput.
- Snapshot formats and export/import support.
- Filesystems and device naming.
- Shared file services and protocols.
- Object storage APIs, lifecycles, and versioning.
- Encryption key ownership and portability.
- Backup formats and restore tooling.
- Replication and consistency.
- Data egress costs and transfer times.

Snapshots encrypted with provider-managed keys often cannot move directly to another provider. Decrypt/export via sanctioned workflows or create logical backups and re-encrypt using target keys.

### Identity and Security

Check:
- IAM roles/policies and service accounts.
- Federated identity and workload identity.
- KMS/key vaults/HSMs.
- Secret managers and rotation.
- Certificate issuance and trust chains.
- Audit logs and retention.
- Security posture, policy-as-code, and compliance.
- Private registries and image signing.

Never transfer secrets by embedding them in user-data or image files. Use target-provider secret bootstrap channels and workload identities.

### Managed Services

Inventory dependent services:

- Managed databases.
- Caches.
- Message queues/streams.
- Object storage.
- Search services.
- API gateways.
- Schedulers.
- Monitoring/logging/tracing.
- Backup services.
- Container registries and orchestration.

If the target provider lacks an exact equivalent, decide between substituting a different managed service, self-hosting the software, or re-architecting. Each option carries distinct operational cost and risk.

## 11. Application and Infrastructure-as-Code Portability

### Provider-Specific APIs

Application code may call provider SDKs directly to:
- Read instance metadata.
- Upload objects.
- Publish messages.
- Fetch secrets.
- Call managed databases or queues.
- Generate signed URLs.
- Control autoscaling.

Abstraction layers help only when they preserve required semantics. Not every object store or queue offers identical consistency, ordering, retention, or transactional behavior.

### Infrastructure as Code

Terraform, Pulumi, or similar tools help recreate infrastructure, but resource types and provider schemas differ. Shared modules may need separate interfaces for:
- Networking.
- VMs/instance groups.
- Load balancers.
- Databases.
- Storage.
- IAM.
- Monitoring.
- Secrets.
- DNS.

Never assume changing providers is as simple as swapping a provider block. Account for state migration, resource replacement, imports, dependency graphs, and accidental resource destruction.

### Configuration and Policies

Standardizing configuration reduces lock-in:
- Image build pipelines.
- Ansible/cloud-init or configuration management.
- Policy-as-code.
- Secret references.
- Monitoring instrumentation.
- Deployment artifacts.
- Service discovery contracts.

Keep configuration decoupled from images and source code so rebuilds on new architectures/providers remain straightforward.

## 12. Data Compatibility and Storage Formats

### Binary Format vs. Data Format Are Separate Problems

Changing CPU architecture may require recompiling executables without necessarily converting business data. Still, database engines, storage engines, or extensions may have architecture or version constraints.

Switching providers may require migrating data between different services. Check:
- Database versions and supported upgrade paths.
- Collations, encodings, and timezones.
- Extensions, stored procedures, and plugins.
- Transaction isolation and consistency.
- Index formats and query behavior.
- Backup formats and restore tooling.
- CDC/replication support.
- Large objects, binary files, and metadata.

### Logical Backups vs. Physical Backups

- **Logical backups:** export schemas and records in logical formats such as SQL dumps or application exports. Typically more portable, though slower for large datasets.
- **Physical backups:** copy data files, snapshots, or storage-level backups. Usually faster within the same engine/platform, though tied to versions, architectures, or providers.
- **Snapshots:** point-in-time volume/service captures. Do not automatically guarantee application consistency during active writes.

Verify whether backup tools run on the target architecture and whether formats are supported for restoration on the new provider.

### Application-Level Compatibility

Beyond databases, inspect:
- File serialization formats.
- Message schemas and versions.
- Encryption envelopes and key IDs.
- Timestamp precision.
- Numeric representations.
- Endianness if architecture-dependent binary data exists.
- Compression codecs.
- Object metadata and ACLs.

Standard versioned formats reduce coupling, though real testing against years of historical data remains essential.

## 13. Compatibility Assessment Matrix

Build a matrix tracking owners and evidence for every component.

| Layer | Assessment Question | Required Evidence | Outcome |
|---|---|---|---|
| CPU/ISA | Do binaries run on target architecture? | Build targets, ELF/PE headers, CPU flags | Pass / rebuild / blocker |
| ABI/runtime | Are runtimes and loaders compatible? | Vendor support matrix, integration tests | Pass / rebuild / blocker |
| Native libraries | Do target-architecture packages exist? | Package manifests, dependency scans | Pass / replace / blocker |
| OS/kernel | Are OS, kernel, and drivers supported? | Support lifecycle, module tests | Pass / upgrade / blocker |
| Containers | Do images include target platform manifests? | OCI manifests, pull/run tests | Pass / rebuild / blocker |
| Cloud services | Do network, storage, IAM, LB, and managed services align? | Architecture mapping, POC | Pass / redesign / blocker |
| Data | Are backup/restore and consistency guaranteed? | Restore tests, reconciliation | Pass / transform / blocker |
| Performance | Are throughput and latency targets met? | Benchmarks/load tests | Pass / tune / blocker |
| Licensing | Does vendor permit running on new platform? | Contract/vendor confirmation | Pass / renew / blocker |
| Security | Are agents, keys, certs, and policies equivalent? | Security validation | Pass / remediate / blocker |
| Operations | Do monitoring, backups, patching, and runbooks work? | Operational rehearsals | Pass / adapt / blocker |
| Cost | Does TCO meet targets? | Cost model and measured usage | Pass / revise / blocker |

Outcomes must go beyond a "supported" checkbox. Document exact versions, architectures, providers, instance types, sign-off owners, test dates, and links to evidence.

## 14. Safe Migration Workflow

~~~mermaid
flowchart TD
    I["Inventory workloads and dependencies"] --> M["Compatibility matrix"]
    M --> G{"Any blockers?"}
    G -->|Yes| R["Rebuild / replace / redesign"]
    R --> M
    G -->|No| P["Build target images and environment"]
    P --> T["Functional, security, and performance tests"]
    T --> V{"Meets criteria?"}
    V -->|No| R
    V -->|Yes| B["Backup and restore rehearsal"]
    B --> D["Data replication / migration rehearsal"]
    D --> C["Canary and cutover"]
    C --> H{"SLOs and data intact?"}
    H -->|No| RB["Rollback per runbook"]
    H -->|Yes| F["Expand traffic and complete migration"]
~~~

### Phase 1: Inventory and Classification

Gather:
- VM/instance types and CPU architectures.
- OS, kernels, images, and agents.
- Binary/native dependencies.
- Container images and manifests.
- Dependent cloud services and APIs.
- Databases, files, objects, and queues.
- Licenses, security policies, and monitoring.
- SLOs, RTO/RPO, and baseline/peak loads.

Classify workloads:
- Directly portable.
- Requires rebuild/repackaging.
- Requires dependency replacement.
- Requires redesign.
- Currently unsupported and must stay on the existing platform.

### Phase 2: Build Target Environment

- Select supported instance families and OS images.
- Build binaries for the target architecture.
- Create multi-arch container images if needed.
- Install agents, drivers, and security tooling.
- Recreate networking/IAM/secrets.
- Configure monitoring and backups.
- Standardize deployment and bootstrapping.

### Phase 3: Testing

Execute:
- Unit/integration tests.
- End-to-end tests.
- Data correctness and reconciliation checks.
- Load/stress/soak tests.
- Failover and recovery tests.
- Security scans and policy validation.
- Backup/restore tests.
- License validation.
- Cost measurements.

### Phase 4: Data Rehearsal

Dry-run the full backup, transfer, import, replication, and validation pipeline with near-production data volume. Measure duration, throughput, egress, replication lag, and the delta requiring sync during cutover.

### Phase 5: Canary and Cutover

Shift a small traffic slice or non-critical workload first. Compare:
- Error rates.
- p95/p99 latency.
- Throughput.
- Data correctness.
- CPU/memory/storage/network utilization.
- Dependency errors.
- Cost per request.
- Alerts and operational events.

Scale up traffic only once all metrics pass. Writable data cutovers require a quiesce or CDC/final-sync plan to prevent lost or duplicate writes.

## 15. Backup, Restore, and Rollback Before Switching

### Backups Must Be Independent of the Fault Source

Before changing architectures or providers:
- Create application/database-consistent backups.
- Store copies in an independent failure domain.
- Protect with encryption and least-privilege permissions.
- Verify retention and immutability if required.
- Preserve key material or valid key-access workflows.
- Record backup tool versions and formats.
- Test restoring into the target environment.

Volume snapshots taken during active writes may be only crash-consistent. Databases need native backups, quiescing, or application-consistent snapshot mechanisms where required.

### Restore Testing Is a Mandatory Gate

A backup is useful only once proven restorable. Verify:
- Can the backup be decrypted?
- Can the format be read on the target architecture/provider?
- Does the database open and recover cleanly?
- Do file/object checksums match?
- Can the application read restored data?
- Are RTO/RPO met?
- Are required permissions and keys available in the recovery environment?

### Post-Cutover Rollback

Rollback is simplest before the target accepts production writes. Once new data exists, determine how to return those writes to the source.

Strategies:
- Keep the source read-only after cutover and permit rollback only before new writes occur.
- Use supported bidirectional replication with conflict controls.
- Use CDC or event logs for reverse synchronization.
- Use application dual-writes only with explicit transaction/idempotency design.

Never enable dual-writes casually. One side may succeed while the other fails, creating divergent state.

Set a rollback expiration boundary. Once the target processes substantial writes and the source diverges, rolling back becomes a separate reverse migration.

## 16. Testing Cutover and Abort Triggers

Before cutover, define:
- Schema/config freeze timestamp.
- How writes are paused or throttled.
- How the final data delta is synced.
- Criteria confirming replication lag is zero or within RPO.
- How DNS/load balancers/service discovery switch over.
- How in-flight connections are drained.
- How post-switch transactions are verified.
- Who holds go/rollback decision authority.

### Example Abort Triggers

- Error rate exceeds threshold over a defined window.
- p95/p99 latency breaches SLO.
- Database replication lag exceeds RPO.
- Data reconciliation detects missing or duplicate records.
- Security agents or auditing fail to operate.
- Licensing or vendor support remains unconfirmed.
- Backup/restore remains unproven.
- Target capacity cannot sustain failover load.

Triggers must be quantitative and agreed beforehand. Never relax thresholds mid-cutover merely to push migration forward.

## 17. Example: Moving a Java Application from x86-64 to Arm64

A Java service on x86-64 VMs aims to migrate to Arm64 VMs for cost optimization.

### Inventory

- Java 21 runtime.
- Spring Boot JAR application.
- JDBC driver.
- JNI library used for data compression.
- APM agent and endpoint security agent.
- Container base image.
- External database and object storage.

### Evaluation

| Component | Inspection Result |
|---|---|
| Java bytecode | Reusable if target JDK supports Arm64 |
| JDK | Select a vendor-supported Arm64 distribution/version |
| JDBC driver | Check JAR and any native dependencies |
| JNI compression library | Requires Arm64 binary or portable replacement |
| APM/security agents | Verify Arm64 agents and feature parity |
| Container image | Build linux/amd64 and linux/arm64 manifests |
| Runtime flags | Tune CPU counts, heap, and GC on target instance |
| Database connections | Measure latency, pooling, and total connections |
| Performance | Benchmark p95/p99, throughput, GC, and cost/request |

### Rehearsal

1. Build multi-arch images.
2. Deploy Arm64 builds to staging.
3. Run integration and data correctness tests.
4. Run load tests matching production workload.
5. Compare latency, throughput, and memory.
6. Verify APM, security agents, and backups.
7. Run a small-traffic canary.
8. Ramp traffic incrementally.

If the JNI library lacks an Arm64 build, replace it or keep that workload on x86-64. Never treat emulation as a long-term production solution without vendor support and benchmarking.

## 18. Example: Moving VMs Between Two Cloud Providers

A web application uses VMs, a managed database, object storage, and a load balancer. Moving providers involves far more than copying disk images.

### Service Mapping

| Source Component | Target Component to Evaluate |
|---|---|
| VM image | New image or tested convert/import |
| Security group | Equivalent firewall/network policy |
| Load balancer | Listeners, health checks, TLS, and draining |
| Managed database | Engine/version, replication, backup/restore |
| Object storage | APIs, metadata, versioning, lifecycle, and ACLs |
| IAM role | Workload identity and least-privilege policies |
| Secret manager/KMS | Secret bootstrap, key migration, and rotation |
| Monitoring | Metrics, logs, traces, alerts, and audits |
| Autoscaling | Min/max/desired, health replacement, and lifecycle |
| DNS | TTLs, cutover, private zones, and service discovery |

### Data

The team tests logical database exports and object transfers on a representative dataset. They measure export/import duration, egress, checksums, schema compatibility, and application query behavior.

If the target provider runs a different database service, test transaction isolation, collations, extensions, stored procedures, and replication strategies. Never assume two databases sharing the same engine name behave identically.

### Cutover

- Provision target infrastructure and run smoke tests.
- Continuously replicate data or sync per plan.
- Throttle writes or enter a maintenance window.
- Sync the final delta.
- Verify row counts/checksums and business invariants.
- Shift traffic.
- Monitor SLOs and audit trails.
- Retire the source only after the rollback window closes and sign-off is granted.

## 19. Common Risks

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Binary throws illegal instruction | Build requires CPU extensions missing on target host | Compile for appropriate baseline or dispatch by CPU features |
| Container fails on Arm64 | Image only provides amd64 manifest or misses native deps | Build/publish platform manifests and test native deps |
| Java starts then crashes | JNI, agent, or native library exists only for x86-64 | Audit dependencies and vendor support |
| VM fails to boot post-import | Differing firmware, boot mode, disk drivers, or image format | Rebuild image or adjust and test boot config |
| Kernel module fails to load | Wrong architecture/kernel ABI or unsigned module | Build for exact kernel/arch and sign per policy |
| Severe performance drop | CPU quotas, single-thread speed, memory bandwidth, or JIT | Profile benchmarks and choose suitable instance families |
| Pods stuck Pending on new nodes | Images/DaemonSets/CSI/CNI lack architecture support | Check manifests, scheduler constraints, and add-ons |
| Database restore fails | Incompatible backup format, version, or extensions | Use logical migration or supported upgrade paths |
| Objects copied yet app errors | Differing metadata, ACLs, versioning, or API semantics | Check checksums, metadata, and authorization |
| Secrets fail to decrypt | Old KMS keys or missing policies on target provider | Plan key migration and re-encryption |
| Invalid licensing | Licenses tied to cores, architecture, or provider | Confirm with vendor and update licenses |
| Rollback loses data | Source missed post-cutover writes | Design reverse CDC/replication or cap rollback window |

## 20. Pre-Migration Go/No-Go Criteria

Proceed only when every critical category has verified evidence:

### Functional Compatibility
- Binaries and native dependencies run cleanly on the target architecture.
- Runtimes, OS, kernels, and drivers are supported.
- Container images include matching platform manifests.
- Managed services/APIs have verified mappings and behavior.

### Performance and Capacity
- Throughput and p95/p99 meet SLOs.
- CPU/RAM/storage/network retain headroom.
- Dependencies are not overloaded.
- Capacity holds under required replica/AZ loss.
- Cost per request/transaction meets goals.

### Data and Recovery
- Backups complete and restore tests pass.
- Replication lag stays within RPO.
- Cutover and final sync are rehearsed.
- Reverse handling exists for new writes if rolling back.
- Data reconciliation shows zero discrepancies.

### Security and Operations
- IAM, secrets, keys, certificates, and audits operate properly.
- Security/monitoring/backup agents are supported.
- Patching and support lifecycles are clear.
- Alerts, dashboards, and runbooks are ready.
- Licensing and compliance are approved.

### Organization and Governance
- Owners assigned for every dependent system.
- Go/no-go decision-maker designated.
- Maintenance window scheduled and communicated.
- Abort triggers and rollback plans defined.
- Rollback window expiration timestamp established.

## 21. Compatibility Assessment Checklist

- [ ] Documented source/target CPU architecture, provider, OS, and instance types.
- [ ] Distinguished CPU vendor change, ISA change, and cloud provider change.
- [ ] Inventoried executables, shared libraries, native extensions, and kernel modules.
- [ ] Checked ISA, ABI, CPU features, and compiler baselines.
- [ ] Verified OS, kernel, firmware, Secure Boot, and drivers.
- [ ] Verified JDK/runtime and agent support on target architecture.
- [ ] Checked container image manifests across all target architectures.
- [ ] Verified Kubernetes node labels, scheduler rules, CNI, CSI, and DaemonSets.
- [ ] Mapped networking, storage, IAM, KMS, secrets, DNS, and load balancers.
- [ ] Checked managed services and provider-specific API dependencies.
- [ ] Verified licensing, vendor support, and compliance.
- [ ] Checked backup formats, restore tools, and data portability.
- [ ] Rehearsed replication, final sync, and cutover.
- [ ] Benchmarked throughput, p95/p99, resource utilization, and cost.
- [ ] Tested security, failover, and operational monitoring.
- [ ] Defined go/no-go criteria and rollback triggers.
- [ ] Executed test restores into the target environment.
- [ ] Assigned owners, runbooks, and rollback expiration windows.

## Conclusion

Evaluating compatibility before changing CPU architectures or cloud providers must span binaries, ABIs, native libraries, OS, kernels, firmware, containers, runtimes, drivers, cloud services, data, licensing, and operational workflows. Sharing an ISA does not guarantee identical performance; sharing a programming language does not guarantee every native dependency is portable; and sharing a managed service name does not guarantee identical APIs or consistency semantics. Build an inventory, construct a compatibility matrix, stand up the target environment, benchmark, and test restores before cutover. Approve migration only once functionality, SLOs, data integrity, security, RTO/RPO, and rollback are all verified on the target configuration.
