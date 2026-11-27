# Comparing in-place updates with immutable machine replacement

When deploying a new application version in the cloud, operations teams typically choose between two approaches: updating software directly on running machines, or creating new machines from a prepared configuration, shifting traffic to the new machines, and removing the old ones. The first approach is commonly called *in-place update*; the second is *immutable infrastructure deployment*.

Both approaches can work well when suited to the application and release workflow. In-place updates reuse existing resources and can be straightforward for small systems. The immutable model produces clearly versioned deployment units that are easy to test and replace, reducing divergence across environments. The choice should be based on availability requirements, rollback capability, data state, release velocity, cost, and automation maturity.

This lesson compares both approaches side by side in the context of cloud compute deployment, from virtual machines to containers and serverless. After this lesson, you will be able to:

- Explain how in-place updates and immutable replacement work along with their respective risks.
- Compare the impact of each approach on availability, recoverability, security, cost, and operations.
- Select a release strategy—such as recreate, rolling, blue-green, or canary—fit for a service's requirements.
- Design a workflow for producing versioned artifacts, running health checks, shifting traffic, and rolling back.
- Handle configuration, secrets, and persistent data when replacing machines or application versions.

## 1. Where do the two deployment approaches differ?

### In-place update

With an in-place update, the system retains the existing virtual machine, server, or container and modifies the contents inside it. For example, a workflow may connect to a VM, download a new software package, replace application files, update libraries, edit configuration, and restart services.

An in-place update workflow on a VM typically includes:

1. Selecting target machines and confirming they still meet operational requirements.
2. Backing up or recording the current version.
3. Uploading or downloading the new release package onto the machine.
4. Installing or replacing files, and updating configuration and permissions.
5. Restarting the process or service.
6. Verifying health checks, logs, and request-serving behavior.
7. Proceeding to remaining machines or restoring the previous version if an error occurs.

The advantage is avoiding creating a whole new fleet of machines. This approach can fit standalone hosts, legacy systems not yet packaged cleanly, applications with specialized upgrade steps, or development environments. For small systems, it can also serve as a simple first step toward release automation.

However, every update mutates the state of an existing machine. If one release installs an extra system package and another edits a config file manually, machines gradually diverge. This accumulated divergence is called *configuration drift*. A machine may work only because of a past manual tweak and cannot be reproduced accurately when replacement is needed.

Updates can also fail mid-flight. For instance, new files may be copied while the service fails to start; or a library is upgraded while another process still depends on the old version. Rolling back requires knowing exactly what changed and having a way to restore both software packages and matching configuration.

### Immutable machine replacement

With the immutable model, operations does not mutate a live serving machine into the new version. Instead, the team builds a versioned artifact or image, provisions new compute units from it, verifies the new units, and shifts traffic to them. Once the new units run stably, old machines or versions are taken out of service.

The artifact can be:

- A machine image with the OS, runtime, and required application components installed.
- A container image tagged immutably or referenced by digest.
- A built application package deployed onto a fresh group of machines with managed configuration.
- A new function version or revision on a serverless platform.

Typical workflow:

1. Build the artifact from source code and pinned dependencies.
2. Scan for vulnerabilities, run tests, and store the artifact in a versioned repository.
3. Provision new machines, containers, or revisions from that exact artifact.
4. Load environment configuration and secrets from managed sources outside the artifact.
5. Run startup checks, readiness checks, and smoke tests.
6. Shift part or all traffic to the new version.
7. Monitor metrics and logs; if healthy, drain and decommission the old version.
8. On failure, route traffic back to the known-good version and investigate the new one.

A running machine is treated as a unit with a clear lifecycle. When OS or base library patches are needed, the team builds a new image and replaces machines through the same workflow. This makes deployment state easier to reproduce and audit.

Immutable does not mean the system never changes. Source code, images, declarative configuration, and infrastructure still evolve across versions. The core principle is that live serving units are not arbitrarily mutated into hard-to-reproduce states; changes are packaged into a new version and swapped in safely.

## 2. Comparing across operational criteria

| Criterion | In-place update | Immutable replacement |
|---|---|---|
| How changes happen | Modify software or config on existing machines | Provision new units from versioned artifacts/images |
| Resources during release | Usually reuses existing machines | May require running old and new machines concurrently |
| Environment reproducibility | Depends on change tracking and machine state | Easier when builds and configuration are automated |
| Configuration drift | Easily accumulates across edits | Reduced since new machines always come from a canonical source |
| Release risk | Machines may end up half-updated or running mismatched versions | Risk centers on the new artifact and traffic cutover |
| Rollback | May require undoing multiple changes on the machine | Can route back to the previous version or fleet if still retained |
| Deployment duration | Can be fast for small edits, but scales per machine | Requires build and provisioning time; can roll out in parallel |
| Horizontal scaling | Must ensure newly added machines also receive all updates | Can launch additional machines from the same tested artifact |
| OS patching | Usually patched directly per machine | Build a new image and roll out replacement machines |
| Automation requirements | Can start with scripts; hard to govern at scale | Requires pipelines for building, storing artifacts, provisioning, and orchestration |
| Best suited for | Small, legacy, low-churn systems or specialized hosts needing controlled updates | Distributed services, autoscaling, frequent releases, and consistent reproducibility |

Neither approach automatically guarantees zero downtime. Machine replacement can still cause outages if old machines are stopped before new ones are ready, if load balancers have not updated, or if applications mishandle open connections. Conversely, in-place updates can maintain continuous availability if rolled sequentially while preserving sufficient healthy capacity. What decides availability is the rollout strategy, application architecture, and health checking.

## 3. Common release strategies

In-place versus immutable describes how deployment units are changed. Recreate, rolling, blue-green, and canary describe how a new version is introduced into service. These rollout strategies are commonly paired with immutable deployments, though several can also apply to in-place updates.

### Recreate

Recreate stops old units and then creates new ones. This is simple and avoids parallel resource overhead, but causes downtime during initialization and verification. Use it only when service interruption is acceptable, during maintenance windows, or when other failover mechanisms exist.

### Rolling update

Rolling update replaces small batches of machines or containers at a time. The system keeps part of the old version serving while new units boot and pass checks. Once the new batch is healthy, the next batch is replaced.

For example, a 6-instance service might replace 2 instances per wave while keeping at least 4 healthy instances available. Actual numbers depend on traffic load, startup time, and headroom capacity. Set explicit minimum/maximum instance bounds during rollouts to avoid capacity shortages or budget spikes.

Rolling updates use fewer resources than blue-green, but two versions serve concurrently for a window. APIs, data schemas, and inter-version protocols must remain compatible during this overlap.

### Blue-green deployment

Blue-green maintains two environment groups: the active serving group (blue) and the new group (green). Green is provisioned and tested separately. When ready, the router or load balancer shifts traffic from blue to green. Blue can be retained briefly for rapid rollback.

Switchover diagram:

~~~mermaid
flowchart LR
    U["Users"] --> R["Load balancer / router"]
    R --> B["Blue: currently serving version"]
    R -. "after verification" .-> G["Green: new version"]
    B --> D[("Shared data service")]
    G --> D
~~~

Blue-green provides a clean cutover point and convenient routing-level rollback. In return, it requires enough capacity for two environments during release. Be extra careful with shared data: rolling back the application cannot automatically undo a breaking database migration.

### Canary deployment

Canary exposes the new version to a small slice of traffic or a subset of users first. Operations compares errors, latency, throughput, and business metrics between the new version and the baseline version. If metrics stay within thresholds, traffic share increases gradually; if metrics degrade, traffic reverts to the stable version.

Canary helps catch issues that surface only under production load or with specific data patterns. It requires consistent traffic splitting, sufficient sample volume for evaluation, and automated rollout abort thresholds. A tiny traffic slice is meaningless if it receives only a handful of requests or fails to represent real users.

| Strategy | Switchover granularity | Parallel resource demand | Key watchouts |
|---|---|---|---|
| Recreate | Full replacement after stopping old version | Low | Potential downtime |
| Rolling | Batch by batch | Moderate | Two versions coexist during transition |
| Blue-green | Switch between two environments | High, often nearly 2x at the compute tier | Must manage routing and shared data |
| Canary | Gradual traffic percentage ramp | Depends on setup | Requires reliable metrics and abort criteria |

## 4. Artifacts, images, and configuration must be versioned

The immutable model is reproducible only when you know exactly what produced a machine or revision. Therefore, artifacts must be managed as first-class release products.

### Build once, deploy to many environments

Pipelines should build and test an artifact once, then promote that exact verified artifact through testing, staging, and production. Rebuilding separately for production risks differing dependencies or image contents from what was tested.

For containers, mutable tags like latest do not uniquely identify image contents because the tag can be moved to another image. Deployments should reference immutable versions or digests, for example:

~~~text
registry.example.com/orders-api@sha256:abc123...
~~~

The digest above only illustrates the reference format; use the actual digest returned by the registry. For machine images, record the image ID or image version alongside build metadata. For application packages, record checksums and release versions.

### Separate configuration from the artifact

The artifact should contain the application and required dependencies. Environment-varying values such as service URLs, cluster names, feature flags, connection limits, and credentials are supplied at runtime from a configuration system or secret manager.

Never put passwords, tokens, private keys, or credentials inside images, repositories, or build logs. Secret read permissions must follow least privilege for the workload identity or machine role. When replacing versions, new units receive the target environment's exact configuration and permissions.

Separating configuration does not mean letting configuration change uncontrollably. Track versions, approvers, and change history for critical configurations, and define how synchronization works across instances.

### Building reproducible images

A VM or container image should be built from inspectable definitions in source control. Minimal Dockerfile example:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/orders-api.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example demonstrates packaging a Java application into a container using a specific runtime and running as a non-root user. In production systems, pin base image versions or digests, scan for vulnerabilities, control dependencies, avoid copying secret files into images, and ensure durable data is written to an appropriate storage service. EXPOSE merely documents the container's intended port; it does not configure firewalls or open cloud ports automatically.

## 5. Data and state during machine replacement

Machines can be replaced easily only when data that must persist is not trapped on the machine's ephemeral disk. Before adopting immutability, classify state:

- **Ephemeral state:** local caches, temp files, regenerable data. Safe to lose on machine replacement when the application is designed properly.
- **Session state:** login sessions or active shopping carts. Store in a shared session store or use appropriate tokens rather than relying on a single instance's memory.
- **Durable business data:** orders, accounts, transactions, user files. Store in databases or object storage whose lifecycle is independent of application hosts.
- **Local data that must persist:** if an application has special volume requirements, implement attach/detach, snapshots, backups, and consistency checks before replacing the machine.

With stateless machine fleets, instances can be created or terminated on demand. Load balancers distribute requests to healthy instances while critical data lives in external systems. This design simplifies autoscaling and instance replacement.

### Database migrations must be backward-compatible

During rolling or blue-green deployments, old and new application versions may run simultaneously. Therefore, migrations should follow the *expand-contract* pattern:

1. **Expand:** add new columns, tables, or APIs in a way that does not break the old version.
2. Deploy the new application capable of reading/writing the new structure while still supporting the old structure during the transition.
3. Migrate or backfill data, verifying completeness and consistency.
4. **Contract:** drop old columns, tables, or compatibility paths only after confirming no running version still depends on them.

Do not bundle a breaking migration into the same traffic-cutover step without a data recovery plan. Binary rollback does not revert written data or altered schemas. Backups, restore drills, and data recovery plans must be designed separately.

## 6. Health checks and safe traffic shifting

A newly started machine that has booted is not guaranteed ready to serve. Distinguish:

- **Startup check:** whether the application has finished initialization, loaded configuration, and connected required components.
- **Readiness check:** whether the instance can accept new requests. Unready instances must not receive traffic.
- **Liveness check:** whether the process is still functional or needs a restart. Liveness should not fail merely because an external dependency is temporarily slow.
- **Smoke test:** representative requests confirming critical workflows operate properly after deployment.

When removing old machines from a load balancer, stop sending new requests first, wait for or drain in-flight connections, and only then stop the process. This is commonly called *connection draining* or graceful shutdown. Applications should handle stop signals, finish active transactions within an allowed window, and close resources cleanly.

A safe rollout requires explicit thresholds—for example, error rate stays within limits, p95 latency stays within acceptable bounds, ready instance count remains sufficient for load, and critical business checks pass. Thresholds should derive from the service's SLO rather than arbitrary guesses.

## 7. Applying across VMs, containers, and serverless

| Platform | In-place update | Immutable approach |
|---|---|---|
| Virtual machines | Connect to VM, install new packages, edit files, and restart service | Build new machine image, launch new VMs, verify, shift load balancer traffic, then terminate old VMs |
| Containers | Exec into running container or mutate files in writable layer | Build new image, deploy new tasks/pods from pinned digest, wait for readiness, then replace old replicas |
| Serverless | Edit configuration or code on an active deployment via platform mechanisms | Publish new version/revision, test, and shift alias or traffic percentage to that revision |

For VMs, immutability yields major benefits once an image pipeline and managed instance groups exist. Logging in to patch individual VMs undermines reproducibility and rollback.

For containers, immutable images are the natural packaging unit: image contents do not change after build. When a new version is needed, launch new containers from a new image. Never rely on live edits inside running containers as a release workflow, since those edits are absent from the image and vanish when containers are recreated.

For serverless, the provider manages most underlying servers. Teams can still apply the same principles by publishing new versions or revisions, attaching explicit configuration, and shifting traffic in a controlled way. Provider-driven platform updates should be reviewed against runtime policies, deprecation schedules, and compatibility guarantees.

## 8. Reference CI/CD workflow

An immutable deployment pipeline can be structured into the following stages:

~~~mermaid
flowchart TD
    A["Commit source code"] --> B["Build versioned artifact"]
    B --> C["Unit tests, integration tests, security scans"]
    C --> D["Push artifact to registry"]
    D --> E["Provision new compute group"]
    E --> F["Startup, readiness, and smoke tests"]
    F --> G{"Meets release thresholds?"}
    G -- "No" --> H["Abort rollout and retain stable version"]
    G -- "Yes" --> I["Canary or traffic cutover"]
    I --> J{"Post-cutover metrics healthy?"}
    J -- "No" --> K["Roll back routing to previous version"]
    J -- "Yes" --> L["Drain and remove old group"]
~~~

The pipeline must record commit hashes, artifact versions, digests/image IDs, deployment configurations, test results, and release approvers. During an incident, this lets teams identify the exact running version and reproduce the environment for investigation.

A reference release sequence:

~~~text
1. Build artifact from the selected commit.
2. Run tests and security scans.
3. Assign an immutable version; record checksum or digest.
4. Provision new compute group from that artifact.
5. Inject configuration and secrets via runtime mechanisms.
6. Wait for readiness and run smoke tests.
7. Shift a portion of traffic; observe errors, latency, and throughput.
8. Ramp traffic gradually if thresholds hold.
9. Drain and delete old compute after the observation window.
10. Record release status and outcomes in the tracking system.
~~~

In practice, these steps run through CI/CD tools, image builders, configuration management systems, container orchestrators, load balancers, or platform serverless services. Tool names differ, but the control gates remain similar.

## 9. Rollback and recovery

Rollback must be prepared before releasing. With immutability, if the old version still exists and data remains compatible, traffic can be routed back to the previous version or a known-good artifact can be redeployed. This is typically faster and more deterministic than reversing multiple edits on individual machines.

A rollback plan should answer:

- Which artifact is the latest stable version? Can it be retrieved by ID or digest?
- How long is the old compute group retained? When is it safe to delete?
- Who or what condition is authorized to halt a rollout?
- How fast can traffic be shifted back?
- Are schemas and data compatible with the previous version?
- If an issue involves configuration or secrets, how are settings restored and permissions revoked?
- Are backups restorable and has recovery time been tested?

Application rollback and data rollback are separate problems. Once a new version writes data in a new format, reverting to the old binary may leave the application unable to read that data. Always favor backward-compatible migrations and prepare controlled data-remediation procedures.

Do not delete the old fleet immediately after cutover for critical services when the cost of keeping standby capacity is acceptable. Retention duration depends on fault detection time, traffic characteristics, and recovery requirements. After the observation period, terminate old resources to avoid unnecessary spend.

## 10. Security and configuration governance

Immutability helps establish provenance for software and images, but does not secure a system automatically. Combine it with these controls:

- Use maintained base images, apply patches, and rebuild images on a schedule or upon critical vulnerabilities.
- Scan images, dependencies, and artifacts; sign or verify artifact provenance when required by policy.
- Run applications with least privilege, avoid root where unnecessary, and assign dedicated workload identities.
- Fetch secrets at runtime from a secret manager, scope access tightly, and rotate credentials.
- Record who built, approved, and deployed artifacts; maintain audit logs for configuration changes.
- Restrict direct administrative access to production hosts; if emergency intervention occurs, record the change and feed fixes back into canonical image or config code.
- Track image age and runtime versions so old serving hosts are not left behind.

For in-place updates, add controls around execution ordering, shell access, pre-change backups, and per-machine state tracking. If a machine fails to update, remove it from the pool or prevent it from serving with a mismatched version.

## 11. Cost and operational capacity

Immutable deployments may run old and new groups concurrently during releases, temporarily increasing compute spend. Blue-green typically requires more headroom than rolling; canary can start with a small slice. Beyond compute, account for image storage, build pipelines, log retention, and orchestration tooling.

In-place updates may consume fewer parallel resources during releases, but hidden costs arise from hard-to-reproduce incidents, drift remediation time, downtime, manual rollbacks, and per-host verification.

For a fair comparison, measure:

- Resource cost per release, including parallel-run windows.
- Elapsed time from deployment start until the new version stabilizes.
- Release failure count, rollback rate, and mean time to recovery.
- Operational time spent resolving differences between machines.
- CPU, memory, network, and storage utilization during rollout.
- Ability to scale out and scale in automatically after release completion.

For services with many instances, autoscaling, and frequent releases, the cost of provisioning new machines is usually predictable and automatable. For specialized hosts with high startup overhead or hard-to-move local data, carefully evaluate replaceability and cutover duration.

## 12. Choosing the right approach

Favor in-place updates when the system is small, uses specialized hosts, changes infrequently, or cannot yet be packaged into reproducible environments. In those cases, automate steps, track versions, update sequentially, check health, and prepare explicit rollbacks.

Favor immutability when applications can be packaged cleanly, require horizontal scaling, release frequently, demand environment consistency, or need fast rollbacks. This fits managed VM groups, containers, and serverless revisions particularly well.

Teams can adopt immutability in phases:

1. Standardize builds and artifact management.
2. Automate configuration so fresh machines can be provisioned consistently.
3. Decouple persistent data and secrets from application hosts.
4. Spin up a parallel group of fresh machines and validate before routing traffic.
5. Transition to rolling or blue-green; add canary once observability metrics are mature.
6. Eliminate direct host edits once the replacement workflow stabilizes.

If a hybrid model is unavoidable, clearly define which components update in place and which are replaced immutably. For example, a legacy system might continue updating a specialized controller host in place while using immutable images for stateless web fleets. Avoid letting the same machine be managed by pipelines sometimes and edited manually at other times without synchronization.

## 13. Example: releasing a new version of an ordering service

Suppose orders-api runs on 6 virtual machines behind a load balancer. The current version is v1.4.2; the team needs to release v1.5.0, which adds an order-processing status field.

**With in-place updates**, the pipeline connects sequentially to each VM, downloads the v1.5.0 package, replaces application files, and restarts the service. If the third VM fails mid-update, the team must track that the first two VMs are on the new version, determine the third VM's state, and remember which version the remaining three run. If the database schema already changed in a way the old version cannot read, rolling back the application may fail.

**With immutable deployment**, the team builds artifact v1.5.0, tests it, and provisions a new VM group from a standardized image. The new group loads configuration and secrets at startup, connects to the shared database, and passes readiness checks. The load balancer then routes a small percentage of requests to the new group. Once error rate and p95 latency stay within thresholds, traffic ramps up and the old group is drained.

To preserve rollback capability, the team runs an expand-first migration: adding the new field in a way v1.4.2 still tolerates. Only after every instance moves to v1.5.0 and data is verified does the team consider dropping old compatibility paths in a separate release.

In this example, immutability makes running versions unambiguous and lets traffic switch back to the old group on error. In exchange, the team needs parallel capacity headroom, an image pipeline, and compatible migration discipline.

## 14. Common mistakes

1. **Assuming immutable automatically means zero downtime:** stopping old machines before new ones are ready still disrupts service.
2. **Using mutable tags:** identical image tags pointing to different contents break exact reproducibility.
3. **Baking secrets into images:** images may be retained long-term or shared widely, making secrets hard to revoke.
4. **Storing business data on ephemeral instance disks:** machine replacement can wipe data.
5. **Rolling back binaries while forgetting schemas:** old versions may be incompatible with data written by the new version.
6. **Failing to preserve capacity during rolling updates:** ready instance counts drop below required minimums or autoscalers cannot replenish fast enough.
7. **Missing proper health checks:** new machines receive traffic before initialization finishes, or old machines restart repeatedly due to overly sensitive liveness checks.
8. **Hotfixing production hosts without updating canonical sources:** the next machine replacement erases the fix and reintroduces the bug.
9. **Deleting the old fleet too early:** when bugs surface only under real traffic, no stable fallback version remains to route traffic back to.

## 15. Pre-release checklist

- [ ] Artifact has a unique version, with checksum or digest recorded.
- [ ] Builds and tests ran against the exact artifact being deployed.
- [ ] Base image, dependencies, and runtime passed security scanning.
- [ ] Environment configuration and secrets come from appropriate managed sources.
- [ ] Persistent data lives outside instance lifecycles or has explicit protection workflows.
- [ ] Migrations are compatible with all versions that may coexist during rollout.
- [ ] Startup, readiness, liveness, and smoke tests are in place.
- [ ] Sufficient capacity exists for the chosen rollout strategy.
- [ ] Monitoring thresholds exist for errors, latency, throughput, and automatic abort triggers.
- [ ] Plan exists to shift traffic back to a stable version.
- [ ] Plan exists to drain connections and terminate old instances.
- [ ] Owners, release history, and post-deploy observation windows are defined.

## 16. Practice exercise

An API service runs across 8 containers, each serving a share of traffic. The team is preparing to release a new image updating a JSON processing library. Requirements are keeping at least 6 ready replicas at all times, keeping p95 latency within SLO, and enabling rollback within minutes.

1. Recommend rolling, blue-green, or canary deployment and explain why.
2. If using a rolling update, how should limits on extra containers created and containers stopped be configured to keep at least 6 ready replicas?
3. Which checks must pass before a new container receives traffic?
4. If the new version writes an extra field to the database, in what order should migrations be deployed so old and new versions both operate?
5. What details must the team retain to roll back to the exact image and configuration?

Hint: start from minimum capacity requirements and rollback time. With rolling, stop old replicas only after new replicas are ready and total healthy replicas remain compliant. With canary, shift a small share of traffic and watch errors and latency before increasing the percentage. Migrations should add compatible structures first, transition the application, verify data, and only then remove old structures.

## Conclusion

In-place updates modify the state of existing machines, making them convenient for some small or specialized systems while demanding strict drift and rollback controls. The immutable model builds new versions and replaces old units, supporting reproducibility, scaling, and controlled releases when artifacts, configuration, and data are managed properly. The final decision should weigh rollout strategy, availability requirements, data compatibility, parallel-run costs, and system observability.
