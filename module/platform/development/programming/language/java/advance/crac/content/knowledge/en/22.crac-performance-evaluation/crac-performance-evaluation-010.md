# Calculating Total Cost of Building, Storing, Distributing, and Using Images

A CRaC checkpoint can shorten Java application startup time by saving the state of an initialized and warmed-up process and then restoring that state when a new instance is needed. However, checkpoints are not free. The pipeline pays costs to run the preparation environment, warm-up, image creation, testing, storage, and artifact distribution. Each instance also needs time and resources to restore and recreate connections, listeners, clients, and environment-dependent dependencies.

To evaluate whether CRaC is economically effective, do not compare restore time against cold-start time alone. Account for the entire image lifecycle: **building the image, storing the image, distributing the image, using the image, and operating the image lifecycle**. Then allocate costs across the number of releases, restored instances, retention duration, deployment regions, and scaling frequency.

A checkpoint reduces startup latency, yet can increase build, storage, network transfer, or memory footprint costs. For workloads with few instances, fixed costs may exceed savings. For workloads that scale out frequently, the same checkpoint can serve many instances, amortizing preparation costs across a larger number of restores.

## 1. Defining Cost Boundaries

Before calculating, identify which artifact types are being measured. In a CRaC workflow, there may be an application/container image and a checkpoint artifact. The application image contains the JDK, application JAR, native libraries, and required filesystem; the checkpoint contains process state at image creation time. Depending on the architecture, the checkpoint may reside inside the container image or be distributed separately.

For a fair comparison, separate:

- **Shared costs:** building the application JAR, building the application image, and pulling the application image if both cold start and CRaC require them.
- **Incremental CRaC costs:** running prepare/warm-up, creating the checkpoint, storing the checkpoint, distributing the checkpoint, compatibility verification, restoring, and recreating resources.
- **Savings from CRaC:** reduced initialization CPU/time, earlier serving capacity, or reduced standby capacity needed to meet startup SLAs.
- **Operational costs:** managing multiple checkpoint generations, host compatibility testing, artifact security, rollbacks, and cold-start fallback.

Do not add shared costs to only one side of the comparison. If both approaches must build and pull the application image, exclude that portion from incremental costs when calculating checkpoint break-even.

## 2. Five Main Cost Categories

| Category | Scope | Common Units |
|---|---|---|
| Building the image | Prepare runner, warm-up, CPU/RAM, checkpoint, validation, and retries | vCPU-hour, GB-RAM-hour, runner-minute, test service cost |
| Storing the image | Checkpoint size, version count, replicas, backups, retention, and storage requests | GB-month, object requests, backup cost |
| Distributing the image | Downloads, registry/object-store egress, cross-region transfer, cache misses, extraction, and checksums | GB transferred, network egress, CPU-seconds, startup delay |
| Using the image | Restore CPU/RAM, dependency recreation, health checks, and post-restore memory footprint | vCPU-seconds, GB-RAM-hours, seconds to readiness |
| Operating the image | Pipelines, compatibility tests, monitoring, security scans, rollbacks, and fallbacks | Engineer-hours, CI-minutes, incident cost |

Beyond these five categories, indirect costs may arise, such as platform team time spent handling broken checkpoints, spare capacity during rollouts, or SLO impact when an artifact fails to restore. Track these items separately so the model does not obscure root causes.

## 3. Per-Release Total Cost Model

For a release (r), total cost over an evaluation period can be modeled as:

\[
C_{r} = B_{r} + S_{r} + D_{r} + R_{r} + U_{r} + O_{r}
\]

Where:

- (B_r): cost of building and verifying the checkpoint.
- (S_r): cost of storing the checkpoint over the retention period.
- (D_r): cost of distributing the checkpoint to nodes/instances.
- (R_r): cost of CPU/RAM and dependency recreation during restore.
- (U_r): incremental runtime cost caused by restored state, such as memory footprint or GC overhead differing from baseline.
- (O_r): operational, security, compatibility testing, and release management costs.

If there are multiple releases during the period, total cost is:

\[
C_{CRaC} = \sum_{r=1}^{M} C_r + C_{fallback}
\]

`C_fallback` is the cost incurred when a checkpoint is unusable and the deployment must cold start, retry, or roll back. Incident costs can also be added when a complete TCO assessment is needed.

This is an accounting model, not a fixed CRaC formula. Each organization may merge or split items according to its cloud billing and cost allocation practices. What matters is that no item is counted twice.

## 4. Calculating Image Build Cost

Image build cost typically occurs once per checkpoint generation, but can repeat multiple times if prepare/checkpoint fails or must be regenerated due to changes in JDK, dependencies, OS image, or warm-up configuration.

Items to record:

- Runtime of the prepare container/VM or dedicated runner.
- CPU and RAM used while starting the application.
- Warm-up duration and number of requests/fixtures executed.
- Cost of databases, brokers, stub services, or sandboxes used during warm-up.
- Checkpoint creation duration and native engine resources.
- Checksum, packaging, upload, scanning, and restore smoke-test costs.
- Cost of failed attempts, including runner-minutes and test dependencies consumed.

A simple formula:

\[
B_r = T_{cpu}P_{cpu} + T_{ram}P_{ram} + C_{warmup} + C_{checkpoint} + C_{verify} + C_{retry}
\]

Where (T_{cpu}) is vCPU-hours, (P_{cpu}) is the price per vCPU-hour; (T_{ram}) is GB-RAM-hours, (P_{ram}) is the price per GB-RAM-hour. The remaining terms are directly measured service or pipeline costs.

### Example Prepare Cost Measurement

Suppose an 8-vCPU, 16 GB RAM runner runs for 12 minutes to start, warm up, and create the checkpoint. Restore verification runs for an additional 5 minutes on the same configuration.

| Stage | Duration | CPU allocation | RAM allocation |
|---|---:|---:|---:|
| Startup and warm-up | 8 minutes | 8 vCPU | 16 GB |
| Checkpoint creation | 4 minutes | 8 vCPU | 16 GB |
| Restore smoke test | 5 minutes | 8 vCPU | 16 GB |

Total CPU allocation is (8 \times 17/60 = 2.27) vCPU-hours; RAM allocation is (16 \times 17/60 = 4.53) GB-RAM-hours. This calculation is based on runner allocation. If the provider bills by minimum node-minute or VM-hour increments, use the actual billing rate instead of converting linearly.

If warm-up calls a billed test database or sandbox, add those charges to (C_{warmup}). If the checkpoint has to be rebuilt three times before succeeding, count all three attempts, not only the final attempt.

### Image Rebuild Frequency Strongly Impacts Cost

A checkpoint can be reused across many instances, yet a new generation usually must be created when:

- Application binaries or dependencies change.
- The JDK, base image, native libraries, or checkpoint engine are updated.
- Warm-up configuration changes significantly.
- Security patches require retiring old checkpoints.
- Checkpoints expire under operational policy.

If there are many small releases per month, build/checkpoint costs can rise even when the number of restored instances stays unchanged. Therefore, track both the number of generations created and the number actually deployed.

## 5. Calculating Image Storage Cost

A checkpoint typically contains the process heap and native state, so its size can be substantial. Size depends on live heap usage, retained objects, warm-up caches, native memory, threads, and the engine's image format. Do not treat `-Xmx` as the expected checkpoint size; measure the actual artifact.

Storage cost over a period can be calculated as:

\[
S_r = G_r \times P_{GB-month} \times H_r \times K_r + C_{requests} + C_{backup}
\]

Where:

- (G_r): checkpoint size in GB.
- (P_{GB-month}): price per GB stored per month.
- (H_r): retention duration converted to months.
- (K_r): equivalent number of stored copies, including replication or backups if billed.
- (C_{requests}): PUT/GET/LIST or other storage request charges.
- (C_{backup}): separate snapshot/backup charges if not already included in (K_r).

If storage pricing has multiple tiers, calculate each retention window under its corresponding tier. If the checkpoint resides in a container registry, check whether the registry bills by blob size, replication, requests, or data transfer.

### Number of Retained Versions

Suppose each release produces a 6 GB checkpoint, one release is published per week, and 8 releases are retained. If each version is stored independently, logical capacity is 48 GB before accounting for replication/backups. If the registry deduplicates layers or object chunks, billable capacity may be lower; do not assume deduplication without actual billing data.

Retention policies directly affect cost:

- Keeping many versions enables fast rollbacks but increases storage.
- Keeping the active release and one previous release may be sufficient for many systems.
- DR or multi-region environments may require additional copies.
- Artifacts revoked due to security patches may need to be quarantined for an audit period before deletion.

Do not delete checkpoints referenced by active deployments or rollback plans. Maintain a release catalog clearly marking which versions are active, rollback-eligible, revoked, or expired.

## 6. Image Compression and CPU vs. Size Trade-Offs

Compressing a checkpoint can lower storage and transfer costs, at the expense of higher CPU usage and decompression time. Effectiveness depends on heap contents and image format. Heaps with many repeated objects/strings may compress well; already-compressed, encrypted, or high-entropy native memory data may compress poorly.

Compare at least three quantities:

1. Uncompressed image size (G_{raw}).
2. Compressed size (G_{compressed}).
3. Time and CPU to compress/decompress on the runner and restore nodes.

Compression ratio:

\[
CompressionRatio = \frac{G_{compressed}}{G_{raw}}
\]

A lower ratio means a smaller artifact. However, do not optimize compression ratio in isolation. If decompression increases time-to-ready or consumes substantial CPU during scale-out, total cost may actually be higher.

Measure compression time during pipeline creation and decompression time during deployment. Also test CPU contention when many replicas download and decompress checkpoints simultaneously. On nodes with local caches, a checkpoint may be extracted once for multiple containers if the architecture and permissions allow.

## 7. Calculating Image Distribution Cost

Once a checkpoint is created, the artifact must reach the node/host that will perform the restore. Distribution cost depends on:

- Number of instances needing to download the checkpoint.
- Compressed artifact size.
- Whether the node already caches the artifact.
- Whether the repository/registry is in the same region or a different region.
- Data egress, inter-region transfer, or CDN/object-store requests.
- Number of retries caused by download failures.
- CPU and time spent verifying checksums/extracting.
- Concurrency level during scale-out.

A simple model:

\[
D_r = N_r \times G_{transfer} \times P_{GB-transfer} + C_{download-requests} + C_{unpack}
\]

Where (N_r) is the actual number of downloads, which does not necessarily equal the number of containers. If each node downloads once and shares the cache across 10 containers, downloads may equal the node count. If each container downloads independently, downloads may equal the instance count.

### Registry Pull Is Not Always Once Per Pod

The container runtime can cache image layers by digest on the node. If the checkpoint resides in an image layer and the node already holds that layer, a new container may not need to re-download all bytes. Conversely, if the checkpoint is a separate artifact fetched by an init container, each Pod may trigger an additional download.

Gather metrics from the registry, object storage, and node cache instead of mechanically multiplying checkpoint size by Pod count. Distinguish between:

- Logical bytes requested by deployments.
- Actual bytes transferred over the network.
- Bytes stored in the registry/cache.
- Bytes extracted onto local disk.

### Concurrent Scale-Out

If 100 replicas start simultaneously and each downloads a 4 GB checkpoint, the theoretical transfer volume is 400 GB without a shared cache. Such a burst can strain the registry, object storage, network, and disk I/O, increasing time-to-ready even if individual restores are fast.

Pressure can be reduced by:

- Caching checkpoints by digest on the node or in a local artifact cache.
- Pre-pulling artifacts before scaling out workloads.
- Distributing in batches instead of starting all replicas simultaneously.
- Using storage regions close to nodes and avoiding unnecessary cross-region transfers.
- Measuring bandwidth and capping download/unpack concurrency.
- Setting timeouts/retries with jitter to avoid all replicas re-downloading simultaneously after an error.

Do not use a mutable cache key like `latest`. Caches must be keyed by checkpoint digest to avoid mixing up generations.

## 8. Calculating Restore and Resource Recreation Cost

The restore engine is not the entirety of startup. After the process is restored, the application may need to:

- Read configuration and secrets from the current environment.
- Recreate database pools and validate connections.
- Create HTTP clients, broker sessions, listeners, and sockets.
- Register the new instance with the service registry.
- Refresh stale caches or static state.
- Start schedulers, consumers, and telemetry exporters.
- Run health checks and readiness gates.

Restore cost can include CPU-seconds, RAM, disk I/O, and node usage time before the instance accepts traffic. A simple model:

\[
R_r = N_r \times (C_{restore} + C_{recreate} + C_{health})
\]

Where (C_{restore}) is the engine's CPU/RAM cost, (C_{recreate}) is dependency recreation cost, and (C_{health}) is health-check cost and dependency wait time. If databases or external services bill per connection/request, add the corresponding amount to (C_{recreate}).

### Time to Readiness

Measure time-to-ready by its components:

\[
T_{ready} = T_{fetch} + T_{verify} + T_{unpack} + T_{restore} + T_{resources} + T_{health}
\]

Cold start must also be measured along the same boundaries:

\[
T_{cold-ready} = T_{JVM} + T_{framework} + T_{warmup} + T_{resources} + T_{health}
\]

Time savings:

\[
\Delta T = T_{cold-ready} - T_{ready}
\]

If the checkpoint is large, download/unpack is slow, or dependency recreation takes up most of the time, (\Delta T) can be smaller than expected. Therefore, measure p50/p95/p99 of each phase under realistic scaling conditions.

## 9. Post-Restore Runtime Cost

A warmed-up image can hold many caches/objects in the heap. This reduces initialization work, yet may increase memory footprint compared to a freshly launched cold-start process.

Compare:

- Heap used and committed immediately after restore.
- RSS/process memory, native memory, and direct buffers.
- GC frequency, pause time, and allocation rate under real workload.
- Thread count, thread stacks, and executor queues.
- Cache hit ratio before and after dependency refresh.
- Actual connection count after recreating pools.
- CPU spikes during restore and post-restore warm-up.

If CRaC causes each instance to retain an average of (\Delta M) additional GB of RAM for (H) hours at a RAM rate of (P_{ram}), the incremental memory cost is:

\[
U_{memory} = N \times \Delta M \times H \times P_{ram}
\]

Similarly, incremental CPU cost from GC, cache refresh, or reconnection can be calculated. Do not assume runtime overhead is 0 simply because the checkpoint was created beforehand.

### A Warm Cache Does Not Guarantee a Valid Cache

Cache warm-up can reduce CPU and database queries, but if data is stale or requires invalidation after restore, the application must reload it. In that case, cache refresh cost must be included in (C_{recreate}) and time-to-ready.

Retain only caches that can be reused safely, such as version-immutable metadata. Caches dependent on tenants, permissions, pricing, inventory, or runtime endpoints must be verified before serving.

## 10. Operational and Image Lifecycle Costs

Operational costs are frequently overlooked when measuring only CPU and storage. With CRaC, teams must additionally manage:

- Compatibility matrix across JDK, OS/kernel, CPU architecture, checkpoint engine, and container runtime.
- Checkpoint creation pipelines and restore smoke tests.
- Image scanning, SBOM, provenance, and checksums.
- Tracking artifact size, restore success rate, and time-to-ready.
- Retention, revocation, deletion, and rollbacks.
- Supporting cold-start fallback when restore fails.
- Handling old checkpoints after JDK or library patches.
- Investigating resource errors in callbacks and native checkpoint errors.

Engineering time can be converted into operational cost:

\[
O_r = H_{engineering}P_{hour} + C_{CI} + C_{monitoring} + C_{security}
\]

Where (H_{engineering}) is the operational/engineering hours allocated to the release, (P_{hour}) is the hourly rate, and the other terms are CI, monitoring, and security tooling costs.

It is not necessary to allocate the entire platform team's cost to a single release. Allocation can be done per release, per service, or per instance, provided the same rule is applied across all options for a meaningful comparison.

## 11. Comparing CRaC Against Cold Start

Cold start also has costs. The application must initialize the JVM, load classes, initialize the framework, warm up code paths, establish connections, and achieve readiness. If startup is slow, the system may have to:

- Keep excess capacity to absorb sudden traffic spikes.
- Scale earlier than forecasted.
- Accept queued or failed requests while instances are not yet ready.
- Slow down rollouts because instances take time to start.
- Maintain many warm instances solely to avoid cold starts.

CRaC can reduce part of these costs, while adding checkpoint creation, storage, distribution, and restore costs. Comparisons should use **incremental costs** relative to the cold-start baseline.

| Item | Cold start | CRaC |
|---|---|---|
| Release preparation | Build application image | Build application image and prepare/warm-up/checkpoint |
| Artifact storage | Application image | Application image plus checkpoint if stored separately or embedded |
| Distribution | Pull application image | Pull application image and distribute checkpoint |
| Process initialization | JVM/framework init and warm-up | Restore process image |
| Dependencies | Create connections/clients | Still must recreate or verify environment-dependent resources |
| Runtime memory | Post-startup heap | Warmed-up heap snapshot, potentially retaining extra caches/objects |
| Operations | Startup probes and scaling | Adds compatibility, artifact lifecycle, restore testing, and fallback |

Do not compare only `T_restore` against `T_JVM`. Compare full time-to-ready and costs under the same workload, same instance count, same observation window, and same SLO.

## 12. Calculating Break-Even by Instance Count

Suppose:

- (F): fixed cost of a checkpoint generation, including build, in-period storage, and operations.
- (C_{cold}): incremental startup cost per instance for cold start.
- (C_{crac}): distribution, restore, and resource recreation cost per instance.
- (N): number of instances using the checkpoint during the period.

Incremental cold-start cost:

\[
C_{cold,total} = N \times C_{cold}
\]

Incremental CRaC cost:

\[
C_{crac,total} = F + N \times C_{crac}
\]

If (C_{cold} > C_{crac}), the break-even instance count is:

\[
N_{break-even} = \frac{F}{C_{cold} - C_{crac}}
\]

If (C_{cold} \le C_{crac}), CRaC does not break even on direct startup cost alone in this model. It may still offer value by lowering latency or meeting SLOs, though that benefit must be quantified separately.

### Illustrative Numerical Example

Suppose a checkpoint generation has:

| Fixed Item | Normalized Cost |
|---|---:|
| Prepare, warm-up, and checkpoint | 80 |
| In-period storage and retention | 30 |
| Pipeline, scanning, and allocated operations | 20 |
| **Total (F)** | **130** |

Suppose per instance:

| Per-Instance Item | Normalized Cost |
|---|---:|
| Cold-start CPU/warm-up | 3.0 |
| Checkpoint download, restore, and recreate | 1.5 |
| Direct savings | 1.5 |

Break-even point:

\[
N_{break-even} = \frac{130}{3.0 - 1.5} \approx 87
\]

With 20 instances, cold start costs (20 \times 3 = 60), whereas CRaC costs (130 + 20 \times 1.5 = 160). In this example, CRaC costs 100 additional cost units.

With 120 instances, cold start costs (360), whereas CRaC costs (130 + 180 = 310). CRaC saves 50 cost units.

These figures illustrate the calculation method only, not actual cloud pricing or benchmarks. The model assumes equal runtime memory costs and other shared costs; if CRaC increases RAM, GC, or fallback, add those amounts to (F) or (C_{crac}).

## 13. Value of Fast Startup Time

Not every benefit translates directly into savings on an invoice. Reducing time-to-ready can generate value through:

- Meeting scale-out SLOs faster during sudden traffic spikes.
- Reducing queued or failed requests while instances are not yet ready.
- Shortening rollout and node-replacement times.
- Reducing the number of warm standby instances maintained purely to avoid cold starts.
- Accelerating recovery after node failures or deployments.

To quantify this, workload data is required:

- Frequency of scaling events.
- Number of additional instances needed per event.
- Seconds saved to readiness.
- Request rate during the scaling window.
- Value of delayed/failed requests or cost of spare capacity.
- SLOs and penalties for missing them.

For example, if 40 new instances are needed and CRaC reduces p95 time-to-ready by 50 seconds, the system gains 2,000 instance-seconds of capacity available sooner. Do not automatically treat 2,000 instance-seconds as monetary savings; determine the requests served earlier, standby capacity reduced, or penalties avoided.

A value model can be:

\[
V_{latency} = V_{requests\ served\ earlier} + V_{capacity\ avoided} + V_{SLO\ risk\ reduced}
\]

Keep this value component separate from direct infrastructure costs. That way, decisions can weigh both TCO and business value without conflating the two quantities.

## 14. Sensitivity Analysis

Break-even depends on assumptions. Vary one variable at a time to test whether the decision remains stable:

| Variable | When Increased | Typical Impact |
|---|---|---|
| Checkpoint size | Storage and transfer increase | Break-even requires more instances |
| Restored instance count | Distribution/restore costs increase while fixed cost is amortized over more instances | Can make CRaC more economical if per-instance cost is lower than cold start |
| Releases per month | Build, validation, and retention increase | Increases fixed cost |
| Retention duration | GB-months increase | Increases storage cost |
| Cache hit rate | Downloaded bytes decrease | Reduces distribution cost and time-to-ready |
| Better compression ratio | Transfer/storage bytes decrease | May increase CPU and unpack time |
| Dependency recreation time | Restore-to-ready increases | Reduces latency benefit |
| Post-restore memory footprint | RAM-hours increase | May increase runtime cost |
| Restore failure rate | Retries/fallbacks increase | Increases cost and reduces reliability |

Build at least three scenarios:

- **Low:** few instances, infrequent scaling events, large checkpoints, and long retention.
- **Baseline:** average release/instance counts reflecting realistic workloads.
- **High:** frequent scale-out, high cache hit rates, and checkpoints reused across many instances.

Do not use the high scenario alone to justify adoption. If CRaC is only beneficial under near-100% cache hit rates or continuous scaling, validate those assumptions using production-like data.

## 15. Measuring Size and Cost with Real Data

Do not predict checkpoint size from maximum heap. Measure on every release:

```bash
du -sh checkpoint-directory
find checkpoint-directory -type f -printf '%s %p\n'
```

If the checkpoint is compressed:

```bash
stat -c '%s %n' checkpoint.tar
sha256sum checkpoint.tar
```

Save metadata alongside the release:

- Raw size and compressed size.
- File count and actual bytes uploaded.
- Upload/download duration.
- Cache hits/misses and number of nodes actually downloading the artifact.
- Unpack and checksum duration.
- Restore duration.
- Dependency recreation and health-check duration.
- Heap/RSS/GC after restore.

The example commands above use Linux GNU tools; adjust for your OS and storage platform. For object stores/registries, rely on the service's own billing and telemetry metrics rather than relying solely on `du` in a local workspace.

## 16. Measuring Time-to-Ready Stage by Stage

Place timestamps at comparable milestones:

```text
T0  deployment requests instance
T1  artifact download starts
T2  artifact download completes
T3  checksum/verify and unpack complete
T4  process restore completes
T5  database/client/listener recreated
T6  health checks succeed
T7  readiness accepting and instance enters service
```

From there, calculate:

| Interval | Meaning |
|---|---|
| (T2-T1) | Download duration |
| (T3-T2) | Verification and unpacking |
| (T4-T3) | Process restore |
| (T5-T4) | Recreating runtime dependencies |
| (T6-T5) | Health checks |
| (T7-T0) | Total time-to-ready |

For cold start, define equivalent milestones from when the scheduler requests an instance until readiness accepts traffic. Measure repeatedly and use p50/p95/p99; a single fast restore is not representative of a scale burst or a cold-cache node.

## 17. Designing a CRaC Cost Dashboard

A useful dashboard links artifact costs to serving effectiveness:

| Dashboard Section | Metrics |
|---|---|
| Build | Prepare duration, warm-up duration, checkpoint duration, retry count, runner cost |
| Artifact | Raw/compressed size, GB-months, number of versions, retention, replication |
| Distribution | Downloaded bytes, egress cost, cache hit ratio, download/unpack duration |
| Restore | Restore duration, resource recreation duration, failure rate, time-to-ready |
| Runtime | Heap, RSS, CPU, GC, active connections, cache hit ratio |
| Business/SLO | Scale events, p95 readiness, request delays/errors during scaling, standby capacity |
| Lifecycle | Release generation, active/revoked checkpoint count, cold-start fallback count |

Associate metrics with release ID, application image digest, and checkpoint digest in logs/provenance. Avoid putting high-cardinality digests or UUIDs into every metric label; store them in log/event metadata and use more stable labels for summary dashboards.

## 18. Common Cost Calculation Mistakes

### Counting Only Storage Price

Storage may be cheap while build, transfer, restore, memory, and operations account for the largest shares. Use a model covering all five cost categories.

### Multiplying Checkpoint Size by Pod Count Without Checking Cache

Registry layer caches or node-local caches can reduce download counts. Measure actual bytes over the network and cache misses.

### Ignoring Failed Checkpoint Creation Attempts

A release may consume multiple runner attempts. Include failed attempts and retried restore smoke tests.

### Measuring Only the Restore Engine

The application still must create connection pools, listeners, telemetry exporters, and health checks. Measure from when the deployment requests an instance until readiness.

### Treating Time Saved Directly as Money Saved

Saving 50 seconds of startup has economic value only if it serves requests earlier, reduces standby capacity, or improves SLOs. State latency value and infrastructure cost separately.

### Ignoring Post-Restore RAM and GC

A warmed-up heap can be larger than baseline. Track RSS, GC, and memory-hours instead of looking only at startup CPU.

### Excluding Retention and Security Patches

Older generations may need to be retained, quarantined, or rebuilt after patches. Factor retention, revocation, and rebuilds into the model.

### Comparing Non-Equivalent Workloads

Cold start and CRaC must run the same JDK/app version, same dependencies, same host class, same request mix, and same readiness definition. Otherwise, cost/performance results are meaningless.

## 19. Service Evaluation Workflow Before Adopting CRaC

1. Measure the cold-start baseline on the same host type: CPU, RAM, startup duration, time-to-ready, and first-request latency.
2. Create an experimental checkpoint using a representative warm-up workload.
3. Measure raw/compressed checkpoint size and prepare cost.
4. Calculate storage based on expected retention and version count.
5. Measure distribution on both cold-cache and warm-cache nodes.
6. Measure restore along with dependency recreation and readiness.
7. Measure heap/RSS/GC and CPU under post-restore workload.
8. Calculate break-even across instance counts, releases, and scaling events.
9. Add fallback, security patch, and operational costs.
10. Run sensitivity analysis across low/baseline/high workloads.
11. Run a canary trial and compare actual figures against the model.
12. Expand adoption only if measured benefits meet target SLOs and TCO.

## 20. Total Cost Calculation Checklist

### Building the Image

- [ ] Runner CPU/RAM and warm-up duration are accounted for.
- [ ] Checkpoint engine, packaging, checksums, and restore smoke tests are accounted for.
- [ ] Failed/retried attempts are accounted for.
- [ ] Costs of dependencies/sandboxes used during warm-up are accounted for.

### Storing the Image

- [ ] Actual raw size and compressed size are measured.
- [ ] Generation count, retention, and GB-months are calculated.
- [ ] Replication, backups, and storage requests are accounted for.
- [ ] A policy exists to delete/quarantine revoked and expired checkpoints.

### Distributing the Image

- [ ] Actual download count and cache hit ratio are measured.
- [ ] Cross-region egress and registry/object-store requests are accounted for.
- [ ] Verification, unpacking, and disk I/O are measured.
- [ ] Concurrent scale-out is tested to detect network bottlenecks.

### Using the Image

- [ ] Restore CPU/RAM and time-to-ready are measured.
- [ ] Dependency recreation, connection pools, and health checks are accounted for.
- [ ] Post-restore heap/RSS/GC are measured.
- [ ] Fallback/retry costs when restore fails are accounted for.

### Comparison and Decision

- [ ] Cold start and CRaC use the same workload and readiness definition.
- [ ] Shared costs are excluded from the incremental comparison.
- [ ] Break-even by instance count is calculated.
- [ ] Value from reduced latency/SLOs is separated from direct infrastructure costs.
- [ ] Sensitivity analysis has been run and validated via canary.

## 21. Conclusion

Evaluating CRaC effectiveness requires accounting for the full cost of a checkpoint across the release lifecycle: preparation and warm-up, image creation, storage, distribution, restore, dependency recreation, post-restore memory/CPU, and artifact operations. Checkpoint size and restore time are only two metrics within a broader model.

Measure the fixed cost per generation, the cost per restore, and the number of instances actually using the image. Use break-even analysis to determine the scale at which cold-start savings offset build/storage/distribution costs, while quantifying time-to-ready and SLO value separately. Only by comparing under identical workloads with real data on caching, retention, resource recreation, and runtime footprint can a team decide whether CRaC delivers genuine economic value for that service.
