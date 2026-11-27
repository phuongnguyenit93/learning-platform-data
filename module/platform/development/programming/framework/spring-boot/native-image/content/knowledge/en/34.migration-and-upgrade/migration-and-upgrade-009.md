# Acceptance Criteria, Maintenance Cost, and When to Stay on the JVM

## 1. Why Not Every Spring Boot App Should Move to Native Image

GraalVM Native Image can help Spring Boot start faster, shrink memory footprint in certain workloads, and fit scale-to-zero or short-lived process environments. In exchange, teams must invest in the native build toolchain, Spring AOT, reachability metadata, native testing, dependency compatibility, container runtimes, and separate diagnostic workflows.

The migration decision must therefore rest on measurable acceptance criteria and ongoing lifecycle maintenance costs. If native does not improve business goals or SLOs enough to offset CI, migration, and support overhead, staying on the JVM is a sound decision.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson helps define acceptance conditions for a native application, calculate recurring maintenance costs, and recognize when to keep the JVM. The goal is not migration at all costs, but choosing the runtime suited to your workload, dependencies, team capability, and operational requirements.

## 2. Set Objectives Before Starting Migration

Before producing a native executable, clearly articulate the problem being solved. Objectives may include:

- Reducing time-to-ready for scale-to-zero workloads.
- Lowering memory requests to increase replica density per node.
- Reducing scale-out time during traffic bursts.
- Cutting runtime costs for high-replica-count services.
- Producing a compact executable for short-lived jobs.
- Meeting specific platform or deployment environment requirements.

Tie each objective to a baseline and an acceptance threshold. For instance, "faster startup" must specify measuring from process launch to readiness under identical image pull/cache conditions and resource limits.

Without a concrete pain point or target metric, native migration easily turns into expensive engineering effort with no clear operational value.

## 3. Acceptance Criteria Should Span Multiple Categories

A production-ready decision must evaluate at least these categories:

| Category | Acceptance question |
|---|---|
| Functional correctness | Does native preserve exact behavior and contracts? |
| Compatibility | Do dependencies, reflection, resources, proxies, and JNI all work? |
| Performance | Do startup, latency, throughput, and memory meet targets? |
| Reliability | Are restarts, shutdowns, scaling, and failure recovery stable? |
| Security | Do SBOM, CVE scans, secret handling, and provenance meet policy? |
| Observability | Are logs, metrics, tracing, and crash diagnostics sufficient? |
| Build/release | Is CI reproducible, with enough runner capacity and rollback? |
| Economics | Is TCO better or does it meet strategic requirements? |
| Ownership | Is there a team accountable for upgrades and incident response? |

A strong score in one area does not offset a hard blocker in another. For example, fast startup cannot compensate for serialization bugs corrupting responses or missing crash investigation procedures.

## 4. Functional Correctness Is Mandatory

The native executable must preserve exact business contracts relative to the JVM baseline. Verify:

- API request/response schemas.
- Validation and error mapping.
- Authentication/authorization.
- Transaction and persistence behavior.
- Serialization/deserialization, subtypes, and custom converters.
- Resources/templates/message bundles.
- Scheduled jobs and message consumers.
- Retries, timeouts, and idempotency.
- Business side effects.

Select tests by capability and risk. Most unit tests can stay on the JVM; the native suite must cover paths likely to diverge in Native Image alongside critical business flows.

Never accept a migration with skipped tests lacking justification and compensating evidence. A native smoke test only proves the process boots—it does not prove business correctness.

## 5. Compatibility Gate for Dependencies

Inventory dependencies and classify each:

- Frameworks/starters with official native support.
- Libraries with actively maintained reachability metadata.
- Libraries using reflection/resources/proxies.
- Libraries generating bytecode or loading classes dynamically.
- Native libraries/JNI/JNA.
- Libraries scoped strictly to tests.
- Dependencies without clear support.

For each risky dependency, record version, features used, native tests, and owner. When a dependency is incompatible, establish a plan: upgrade version, enable AOT mode, replace it, isolate the module, or stay on the JVM.

Do not apply a blanket "dependency compatible" label to an entire library if only one feature was checked. Compatibility must be tied to exact versions and usage patterns.

## 6. Performance Gates Must Rest on Equivalent Workloads

Compare JVM and native using identical:
- Source revision and dependencies.
- Request mix, dataset, and concurrency.
- CPU/memory limits.
- Base image/runtime environment.
- Warm-up policy and measurement duration.
- Observability overhead.
- External dependencies and network conditions.

Measure at least:

| Metric | How it informs the decision |
|---|---|
| Time-to-ready p50/p95/p99 | Evaluates startup and scale-out |
| RSS/cgroup peak | Evaluates memory budget |
| CPU/request | Evaluates compute efficiency |
| Throughput | Evaluates overall capacity |
| p95/p99 latency | Evaluates tail latency |
| Error/restart/OOM rate | Evaluates stability |
| Build duration/peak RAM | Evaluates CI cost |
| Image size/pull time | Evaluates artifact/deployment speed |

Set thresholds against real SLOs and baselines. Never decide based on a single isolated startup benchmark.

## 7. Examples of Testable Acceptance Criteria

A team can structure criteria as follows:

| Criterion | Example passing condition |
|---|---|
| Functional tests | All contract and critical business tests pass |
| Native-specific tests | All high-risk scenarios pass |
| Startup | p95 time-to-ready beats agreed target |
| Memory | Peak cgroup memory stays within budget with headroom |
| Latency | p95/p99 shows no regression beyond SLO thresholds |
| Throughput | Meets target capacity at intended resource limits |
| Stability | Zero unexpected OOMs/restarts during soak tests |
| Security | Zero unresolved policy-violating findings |
| Observability | On-call has adequate logs/metrics/traces and crash evidence |
| Deployment | Final image passes probes, runs non-root, handles graceful shutdown |
| Rollback | Can revert to a known-good JVM artifact |
| Maintenance | Designated owner and budget for toolchain/metadata upkeep |

Specific numerical thresholds must be set by service owners/SRE/product for the system. Never impose a fixed percentage memory reduction or startup improvement target across every Spring Boot application.

## 8. Hard Gates vs. Acceptable Trade-Offs

Distinguish between:

**Hard gates** are mandatory conditions:
- Accurate functional behavior.
- Zero security/authorization regressions.
- Critical native paths tested.
- SLOs and resource limits met.
- Zero unaccepted CVEs/blockers per policy.
- Observability, rollback, and ownership in place.

**Trade-offs** can be weighed via TCO:
- Longer CI builds.
- Higher-RAM native build runners.
- Larger or smaller binary/image sizes depending on configuration.
- Additional metadata/test maintenance.
- Diagnostics differing from the JVM.
- Extra regression testing during toolchain upgrades.

Do not turn a trade-off into a hard gate without a product justification. Conversely, never relax a hard gate just because native benchmark numbers look attractive.

## 9. Initial Migration Costs

Migration costs typically include:
- Inventorying dependencies and dynamic behavior.
- Upgrading Spring Boot/dependencies.
- Refactoring incompatible code.
- Writing `RuntimeHints` or configuring metadata.
- Adjusting class initialization.
- Building native integration tests.
- Provisioning toolchain and CI runners.
- Updating Dockerfiles/buildpacks.
- Establishing observability/incident workflows.
- Training developers and on-call engineers.

Track effort in engineer-hours or sprints broken down by capability. This helps forecast costs when expanding to similar services.

Do not estimate migration by compiler runtime hours. Most effort goes into investigating dependencies, fixing integrations, and designing tests.

## 10. Recurring Post-Migration Maintenance Costs

After native release, ongoing costs continue:

| Activity | Maintenance work |
|---|---|
| Spring Boot upgrades | Re-running AOT/native compatibility and regression suites |
| GraalVM upgrades | Auditing options, toolchain, and compiler behavior |
| Dependency updates | Verifying metadata and native integrations |
| `RuntimeHints` | Reviewing, pruning stale hints, and adding new hints |
| Native tests | Maintaining coverage for high-risk capabilities |
| CI/build | Pinning runners, caches, capacity, and plugins |
| Containers | Updating base images/libc/native libraries |
| Security | SBOMs, rescans, and CVE remediation |
| Observability | Maintaining symbols, JFR/heap dump support, and runbooks |
| Incident response | Investigating native crashes, OOMs, and compatibility issues |

Every framework or dependency release can alter metadata and behavior. Never assume one passing build means all future upgrades are safe.

## 11. `RuntimeHints` Require Ownership Too

`RuntimeHints` may live in source or dependency metadata. As dependencies evolve, manual hints can become:
- Obsolete.
- Registered for the wrong members/types.
- Incomplete for new features.
- Broader in reachability than necessary.
- Duplicated against library-provided metadata.

Assign owners to hints by module/dependency, document rationale, and write tests. Review hint changes like production code. When upgrading dependencies, re-run native tests and prune obsolete metadata backed by evidence.

Never allow a sprawling hints file that nobody understands or can trace back to a feature. The harder metadata is to audit, the higher upgrade costs climb.

## 12. Toolchain and CI Capacity Costs

Native builds can demand high CPU/RAM and longer durations than JVM packaging. Teams must maintain:
- GraalVM distributions/versions.
- JDKs and Native Build Tools.
- C compilers/linkers/SDKs.
- Builder images.
- Caches and artifact stores.
- Runner capacity and timeouts.
- Build logs/provenance.
- Native test execution environments.

Pin versions for reproducibility, while maintaining a security upgrade cadence. Pinning an old GraalVM version indefinitely accumulates technical debt and misses patches.

Calculate CI cost across build frequency, runner minutes, peak memory, native test duration, and cache storage. Running native builds only at release time without regular change validation lets compatibility failures pile up until urgent releases are blocked.

## 13. Container and Platform Compatibility Costs

Native executables bind to a specific OS/architecture and ABI. Multi-platform deployments may require building separate binaries/images for:
- Linux amd64.
- Linux arm64.
- `glibc` or `musl` environments.
- Different base images.
- Vendor native libraries.

Each target may need dedicated builds and tests. Teams must maintain matrices, artifact digests, image scans, and runtime tests. If the deployment platform changes node architecture or base images, native artifacts must be re-verified.

If an application requires broad portability and its workload sees little native benefit, a JVM JAR may be simpler because it runs across many environments with a compatible JRE.

## 14. Observability and Incident Response Costs

Native executables require tailored diagnostic workflows:
- Structured logs and correlation.
- Actuator/Micrometer metrics.
- Distributed tracing.
- Exit codes, signals, and OOM events.
- Debug symbols tied to binary digests.
- Core dumps/heap dumps where supported.
- JFR/JMX depending on GraalVM version.
- Debug tooling/containers for distroless images.

On-call engineers must practice collecting evidence and reading native stack traces. If incident workflows rely exclusively on HotSpot heap dumps/JMX without native equivalents, MTTR can increase.

Include these costs in pre-production acceptance criteria. Do not wait for the first production crash to figure out how to capture symbols or core dumps.

## 15. When Should You Stay on the JVM?

The JVM is usually the right choice when one or more of the following hold:

- The service runs continuously with rare cold starts, and startup is not a bottleneck.
- The workload is CPU-bound and native fails to improve throughput/latency.
- The application requires loading arbitrary plugin JARs or classes post-deploy.
- Core dependencies generate dynamic bytecode without a native-compatible mode.
- Script engines require unsupported runtime compilers/classloaders.
- Multiple JNI/native libraries are incompatible with the target.
- Build runners lack RAM/CPU, or CI costs outweigh runtime savings.
- The team lacks capacity to maintain metadata, toolchains, and native diagnostics.
- Deployment spans multiple OS/architectures without a native build matrix.
- SLOs are already comfortably met on the JVM at lower cost.

This is not a sign of poor architecture. The JVM is a mature runtime with a vast ecosystem well suited to many production workloads.

## 16. When Is Native Image Worth the Investment?

Native Image can be worth investing in when:
- Cold start/time-to-ready is a clearly measured business problem.
- Services scale to zero or spawn many short-lived processes.
- Memory footprint is a significant capacity constraint.
- Lower memory requests enable higher replica density and cost savings.
- Dependencies/frameworks have stable native support.
- Native-specific tests can cover critical capabilities.
- The build pipeline has adequate runners and caching.
- The team has clear ownership, observability, and an upgrade process.

Benefits must materialize in production-like workloads and TCO. Microbenchmarks or local runs alone do not represent deployment economics.

## 17. When to Use a Hybrid Model

Not every service in a system must run on the same runtime. You can:
- Keep plugin hosts or scripting engines on the JVM.
- Run stateless APIs with high startup/memory pressure natively.
- Split short-lived workers/jobs into native executables.
- Keep modules with unsupported JNI or dependencies on the JVM.
- Extract dynamic extensions into a separate service.
- Use shared contracts/APIs for cross-runtime communication.

A hybrid approach can optimize per workload while increasing artifact, deployment, and operational surface area. Choose it only when gains outweigh maintaining two pipelines/runtimes.

Do not split a service just to dodge a minor hint. Split only along sensible domain/deployment/ownership boundaries with independent operability.

## 18. Making Decisions via TCO

Calculate costs over a consistent period, such as monthly:

`TCO = CI + artifact + deployment + runtime + observability + engineering + risk`

Convert components consistently:
- CI runner-hours and memory capacity.
- Registry storage and image transfer.
- Production CPU/GiB-hours.
- Replica-hours and scale-out overhead.
- Observability storage/processing.
- Migration/maintenance engineer-hours.
- Incident costs and availability impact.

Compare JVM and native across low, expected, and high workloads. Include release frequency, replica count, cold starts, compute pricing, and maintenance effort in sensitivity analysis.

If native only wins in a rare traffic edge case or by ignoring engineering costs, revisit the decision. If native cuts compute significantly under realistic workloads while clearing all hard gates, higher build costs can be justified.

## 19. Migration Review and Approval Process

A decision can be reviewed in sequence:

1. Document pain points and JVM baseline.
2. Select a representative vertical slice.
3. Identify dependency/native risks.
4. Define acceptance criteria and SLO gates.
5. Run AOT/native builds and native tests.
6. Verify final container/observability/security.
7. Run canary or production-like workloads.
8. Calculate TCO and maintenance effort.
9. Assign owners and an upgrade calendar.
10. Approve expansion, hybrid, or staying on the JVM.

Store evidence and assumptions alongside the decision. If workload, dependencies, or platform shift significantly, re-evaluate the runtime choice.

## 20. Example Decision Matrix for Three Service Types

| Service type | Characteristics | Initial selection direction |
|---|---|---|
| Scale-to-zero API | Frequent cold starts, bursty traffic, native-compatible dependencies | Prioritize Native Image pilot |
| Continuously running backend | Rare restarts, steady throughput, JVM already meets SLOs | Stay on JVM unless memory/TCO favors native |
| Plugin/script platform | Post-deploy code loading, runtime bytecode generation | Prefer JVM or isolate the dynamic engine |

These are evaluation starting points, not blanket verdicts for every service of that type. For instance, a continuously running backend might still benefit from native if memory density drives major cost; a scale-to-zero API might still be unsuitable if dependencies are incompatible.

## 21. Hands-on Exercise: Building an Acceptance and Maintenance Plan for Order API

**Context:** Order API currently runs on the JVM with Spring Data, JSON serialization, HTTP clients, and optional integrations. The team is evaluating native for production.

**Step 1 — Write objectives.** Pick a measurable pain point such as time-to-ready or memory per replica.

**Step 2 — Capture JVM baseline.** Collect startup/readiness, RSS, CPU, throughput, latency, CI time, image size, and error rate.

**Step 3 — Build dependency inventory.** Record versions, native support, reflection/proxy/resource/JNI behavior, and owners.

**Step 4 — Pick a slice.** Take one vertical flow through AOT/native and the final container image.

**Step 5 — Write hard gates.** Define functional, compatibility, security, SLO, observability, and rollback criteria.

**Step 6 — Estimate maintenance.** Forecast engineer-hours for hints, native tests, toolchain upgrades, CVE rebuilds, and incident support.

**Step 7 — Benchmark.** Compare JVM and native under identical workloads, resource limits, and environments.

**Step 8 — Calculate TCO.** Convert CI, registry, runtime, observability, and engineering costs per month/quarter.

**Step 9 — Review decision.** Choose native, JVM, or hybrid; document assumptions, risks, owners, and a re-evaluation date.

Completion criteria: acceptance criteria are verifiable; baseline and native evidence share identical conditions; maintenance owner is assigned; TCO includes engineering costs; runtime decision and rollback plan are documented.

## 22. Conclusion

Accept Spring Boot Native Image only when functional behavior is accurate, dependencies are compatible, native and final image tests pass, SLOs are met, security/observability are complete, and ownership is clear. Fast startup is one benefit—not the sole criterion.

Native Image carries ongoing maintenance across GraalVM/toolchains, AOT, `RuntimeHints`, dependency upgrades, native tests, container ABIs, SBOMs, and incident diagnostics. When a service rarely cold-starts, the JVM already meets SLOs, or the application relies on unsupported dynamic class loading/bytecode generation, staying on the JVM is often the better decision. Choose your runtime using TCO and real requirements; use a hybrid model when workloads differ and operational boundaries are clear.
