# Defining Completion Criteria and Removing Transitional Configurations

In a **Java Advance Compatibility Migration** project, getting the application to start on the new JDK or having a single passing unit test run is not enough to declare the migration complete. The system may still require `--add-opens` for an old reflection library, retain a JSON V1 reader branch, have an auxiliary application running on Java 8, have never tested the month-end batch job, or carry a flag disabling security checks to keep a legacy client working. These items constitute **transitional debt** and can turn into incidents after the project team disbands.

To conclude a migration in a controlled way, the team needs to do two things: **define evidence-backed exit criteria** (*exit criteria*, *Definition of Done*) and **remove transitional configurations in a safe sequence**. The two tasks are related but not identical. It is possible to achieve the new-JDK deployment goal first, while continuing to maintain a compatibility window to serve legacy data/consumers. Only when these dependencies have ended or been converted into formal exceptions is there a basis to close the program.

This lesson walks through building an acceptance criteria set, defining lifespans and owners for compatibility flags, handling dual-read/dual-write, adapters, legacy JDK/Jakarta settings, organizing canaries and rollbacks, and retaining operational evidence before marking a migration complete.

## 1. Distinguishing “running” from “fully migrated”

Suppose a service switched from JDK 8 to JDK 17. The CI build is green, the API returns HTTP 200, and the container starts cleanly. However:
- Startup still passes `--add-opens=java.base/java.lang=ALL-UNNAMED`.
- `order-worker`, which runs once a month, still uses Java 8.
- Old JSON records can still only be read by the legacy deserializer.
- A build plugin uses a dependency override no longer supported by its vendor.
- Production and DR run two different JDKs.
- Rollback of the new version has not been tested against data it has just written.
- TLS is allowed to downgrade so an old partner can continue connecting.

You cannot declare “migration completed” solely because the main service started up. There are four milestones to report separately:

| Milestone | Meaning | Illustrative evidence |
|---|---|---|
| **Build migrated** | Code and dependencies compile with the selected toolchain/target. | Artifact provenance, compile/test build logs. |
| **Runtime migrated** | Workloads actually run on the target runtime. | Java version telemetry of APIs, batches, consumers, DR. |
| **Compatibility proven** | API/data/behavioral contracts are verified during the mixed window. | Golden fixtures, contract/integration tests, canary results. |
| **Migration closed** | Transitional debt has been removed or placed under formal exceptions; operations and handoff are complete. | Cleanup PRs, metrics, ADRs, owner sign-off. |

A unit can reach Milestone 2 while the system as a whole has not reached Milestone 4.

## 2. Exit criteria are a verification contract

A good completion criterion must answer:
1. **Subject:** component, service, client, database, CI job, or entire program?
2. **Scope:** which environments, releases, runtimes, tenants, regions, traffic, and data?
3. **Condition:** what state or threshold is acceptable?
4. **Method:** tests, metrics, queries, artifact audits, or manual verification?
5. **Evidence:** build/deployment links, test reports, dashboards, diffs, issues, approval signatures?
6. **Owner:** who checks it and who handles non-compliance?
7. **Duration:** how long must we observe to cover rare tasks and long-lived data?
8. **Exceptions:** what has not been met yet is granted time-bounded approval with an expiry?

A statement like “no significant errors remain” is unmeasurable. Better:

> During an observation window approved by SRE and the business owner, all instances within scope run the target JDK; error rates and latencies of primary transactions meet the defined thresholds; no untriaged compatibility errors remain; every case still dependent on the old runtime has an exception ticket and an owner.

Specific numbers, observation duration, and traffic scope must be decided by the project. No single percentage or day count fits every system.

## 3. Define completion scope before starting cleanup

A JDK/framework upgrade program may cover:

```text
Migration Program
    |
    +-- Source + build + dependency
    |
    +-- Runtime + packaging + CI
    |
    +-- Business behavior + security
    |
    +-- API + data + protocol
    |
    +-- Operations + performance + DR
    |
    +-- Transitional configuration cleanup
    |
    +-- Evidence + ownership + closure
```

The inventory must also list:
- API services, CLIs, schedulers, batches, message consumers, and offline workers.
- Toolchains, compiler runtimes, test JVMs, and container runtimes.
- Regions, environments, failover/DR, and running images.
- Frameworks/BOMs, plugins, and **actually resolved** dependency versions.
- HTTP, database, queue, cache, file, and backup contracts.
- Temporary settings introduced to run legacy/new concurrently.
- Owners, deadlines, review dates, and rollback dependencies.

A workload that runs only during a DR failover can still determine whether the program qualifies for closure.

## 4. Acceptance criteria matrix

| Group | Condition to prove | Suitable evidence |
|---|---|---|
| Source/build | All modules in scope build against the right baseline. | CI reports, compiler/toolchain configuration. |
| Dependency | No unsupported combinations or unowned overrides remain. | Resolved dependency tree, BOM audit. |
| Runtime | Workloads actually run the committed JDK. | Process/deployment inventory, JVM runtime metrics. |
| Binary/linkage | No missing class/method/module errors on real execution paths. | Integration tests, release-scoped logs/alerts. |
| Behavior | Business contracts and error handling remain accurate. | Regression, E2E, business comparisons. |
| Data | V1/V2 records and schemas satisfy contracts. | Golden fixtures, reconciliation, restore drills. |
| Security | No security exceptions remain outside the approved whitelist. | Security tests, flags/advisory reviews. |
| Performance | Throughput, latency, memory, and GC stay within budget. | Load tests and production dashboards. |
| Operations | Alerts, runbooks, backups, and rollback or forward-fix have been practiced. | Incident rehearsals, SRE sign-off. |
| Cleanup | Flags/adapters/legacy writers have no remaining dependencies. | Metrics, code/config diffs, deployment audits. |
| Governance | Residual risks have owners, decisions, and expiries. | ADRs, change records, sign-offs. |

Separate gates into the **deployment gate** (safe enough for production), **compatibility window exit gate**, and **program closure gate**. Do not force the team to strip out the V1 decoder on V2 deploy day if legacy data still exists.

## 5. What is a transitional configuration?

A *transitional configuration* is a mechanism added or kept **temporarily** to bridge two generations of runtimes, code, data, or deployments.

Examples:
- JVM `--add-opens`, `--add-exports` for libraries not yet JPMS-compatible.
- Workarounds for JAXB/Java EE modules removed from the JDK.
- Parsers/serializers reading both old and new JSON/XML.
- Legacy field aliases, database or queue dual-read/dual-write.
- Feature flags selecting V1/V2 producer formats.
- Adapters between `javax.servlet.*` and `jakarta.servlet.*`.
- Legacy compatibility HTTP routes or endpoints.
- Temporary Maven/Gradle dependency pins, profiles/overrides.
- Dockerfiles containing fallback branches for old Java 8/JRE layouts.
- TLS security exceptions for partners not yet upgraded.
- Traffic mirroring/canary routing used for comparison.

**Not every configuration named `legacy` has to be deleted.** It might represent functionality with a long-term support contract. Understand the rationale, users, and product policy before treating it as temporary debt.

## 6. Grouping configurations by removal condition

| Type | Example | Removal condition |
|---|---|---|
| **Temporary workaround** | `--add-opens` for reflection plugin. | Plugin fixed/upgraded; tests and canary no longer need the flag. |
| **Compatibility reader** | Reads V1/V2 schemas. | No V1 data left to read, including archives/restores. |
| **Rollout switch** | `newSerializerEnabled`. | All producers stable on V2; rollback does not need to re-enable branch. |
| **Operational bridge** | Proxy translating V1 endpoints to V2. | Valid clients migrated; V1 contract support expired. |
| **Dependency override** | Pinning old transitive library. | New framework/library combination tested and supported. |
| **Security exception** | Accepting weak ciphers/TLS versions. | Clients migrated; security owner approves removing the exception. |
| **Dual-write scaffold** | Writing both old and new DB columns. | Data reconciled; no remaining old readers/rollback dependency. |

A criterion like “V1 traffic is 0 for 24 hours” may be inappropriate if a batch runs once per quarter. You must understand the **actual usage cadence** and data retention period.

## 7. Creating a record for each flag or adapter

A record should contain an ID, location, default value, rationale, owner, risks if kept/removed, removal criteria, observed signals, recovery path, and review date.

Example:

```yaml
id: MIG-TEMP-014
component: order-api
kind: jvm-flag
setting: "--add-opens=java.base/java.lang=ALL-UNNAMED"
reason: "Mapper legacy still uses deep reflection"
introducedIn: "jdk17-migration"
owner: "order-platform"
securityOwner: "security-team"
riskIfKept: "Unnecessary reflective access"
riskIfRemovedEarly: "Mapper startup/runtime failure"
removalGate:
  - "Upgrade mapper to a supported version"
  - "Run integration suite without flag"
  - "Canary under representative workload"
telemetry:
  - "Reflection errors by release"
rollback:
  - "Redeploy previously approved JVM configuration"
reviewBy: "Next migration checkpoint"
status: "temporary"
```

This is an internal tracking example, not built-in Java/Maven/Gradle metadata. Each setting should have a **person responsible for deleting it**; without an owner, temporary configurations easily become permanent dependencies.

## 8. Source code and dependency criteria

Verify:
1. Every module in scope compiles with a valid toolchain.
2. Compiler targets such as `--release 17` match the committed minimum runtime.
3. No imports of JDK internals or removed APIs remain outside the exception list.
4. BOM/dependency graphs contain no unsupported combinations.
5. Annotation processors, plugins, and bytecode libraries support the target runtime.
6. Generated code does not regenerate legacy APIs on every build.
7. All build artifacts have version, commit, and provenance.

Maven example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Gradle Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

`--release` does not choose the JVM executing unit tests and does not guarantee dependency JARs are also compatible with runtime 17. Test separately on the target runtime.

## 9. Runtime and deployment criteria

A project may have APIs, background jobs, schedulers, event consumers, CLIs, and DR images. Measure the JDK of the **running process**, not just the JDK on the CI agent.

Example:

```java
public final class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println("Java version: "
            + System.getProperty("java.version"));
        System.out.println("Java home: "
            + System.getProperty("java.home"));
        System.out.println("Java vendor: "
            + System.getProperty("java.vendor"));
    }
}
```

When using Maven Toolchains or Gradle Test `javaLauncher`, the test JVM may differ from the JVM running the build tool. If production has rolling deployments and standby regions, inspect **every workload in scope**, not just the majority of instances.

A criterion saying “no more JDK 8” must state its scope explicitly; if a legacy out-of-scope batch remains, record it as a time-bounded dependency/exclusion or place it into a separate plan.

## 10. Behavioral and protocol criteria

An application can compile yet change in:
- Encoding, locale, timezone, and date formatting.
- TLS/truststore/security providers.
- Reflection, JPMS, module loading.
- JSON/XML serialization, null inclusion, numeric precision.
- Database schemas, JDBC drivers, transaction semantics.
- Retries, timeouts, HTTP headers, and error handling.
- Logging, GC, thread scheduling, performance.

You need contract tests verified against **what is promised**, not just incidental outputs of an old library. For example, two JSON numbers with the same semantic value but different raw bytes can still differ if the payload is signed.

Verify compatibility directions:
- V2 consumer reads V1 producer data.
- V1 consumer reads V2 if rolling deployment/rollback still requires it.
- Long-retained stored data can still be decoded/restored as needed.
- Offline clients or scheduled jobs that have not run during the observation window are accounted for.

## 11. Security criteria

A migration must not be completed merely by disabling validation or setting every request to `permitAll`. Check:
- Are module-opening JVM flags still needed?
- Have TLS protocols/ciphers/hostname verification been weakened?
- Do parsers/deserializers accept unsafe input?
- Are authentication, authorization, CSRF, CORS, and session policies still intact?
- Have dependency security advisories been triaged/remediated?
- Do remaining security exceptions have owners, expiries, and mitigations?

If a workaround must remain, **do not call it cleaned up**. A scope may close with a formal exception if the organization permits, but the report must explicitly list residual debt, risks, and follow-up plans. Never silently turn exceptions into defaults.

## 12. Performance and stability criteria

Upgrading the JDK can affect GC, JIT, memory layout, TLS handshakes, concurrency, and container ergonomics.

Agree upfront on:
- Throughput of business flows.
- P50/P95/P99 latency.
- Error rate and retry rate.
- CPU, heap/RSS, GC pauses, thread count.
- Connection pools, queue lag, restarts/OOMs.
- SLOs and infrastructure cost budget.
- Matching load tests and required production observation window.

**Illustrative-only** example:

| Metric | Baseline | Example acceptance threshold |
|---|---:|---:|
| P99 latency | 400 ms | Does not exceed 450 ms under comparable load. |
| Error rate | 0.2% | Increases by no more than 0.1 percentage points. |
| Queue lag | 30 s | Does not breach the approved SLO threshold. |
| Container memory | 1.2 GiB | Has headroom and zero OOMs. |

Do not adopt these example thresholds as policy for every application. SREs, business teams, and release owners must finalize them based on criticality and workload characteristics.
## 13. Long-lived stored data needs dedicated exit criteria

Some V1 data persists long after producers stop writing V1:
- Database records, serialized columns, and audit events.
- Object storage or archives.
- Queues, delayed messages, and dead-letter queues.
- Long-TTL caches or snapshots.
- Backups that may need restoration years later.
- Offline clients syncing periodically.
- Reports/batch jobs running only monthly or quarterly.

When can the V1 decoder be deleted? Not simply when production V1 traffic hits 0, but when **every supported V1 data reading path** has been addressed:
1. Existing data has been converted, or an independent restore/migration tool exists.
2. The required retention period has elapsed, or an announced end-of-support decision is in place.
3. Queues/dead-letter queues have been drained/converted per policy.
4. Valid clients no longer emit V1 payloads, including offline consumers.
5. Standby regions and backup restore paths have been verified.
6. Reconciliation evidence exists for record counts, values, error cases, and data integrity.

If a backup from last year can only be read by the V1 decoder, removing the decoder from the main runtime can still make sense **if** a separately maintained and tested restore tool exists. The exit criterion must clearly state the recovery mechanism rather than vaguely claiming “old data is no longer needed”.

## 14. Backward compatibility and forward compatibility

Suppose producer/consumer versions V1 and V2:

```text
                     Consumer V1      Consumer V2
Producer V1          Baseline         Backward read
Producer V2          Forward read*    Target operation

* Required when V1 consumers remain or rollback demands it.
```

**Backward compatibility**: new consumers read old data. **Forward compatibility**: old consumers read new data within the specified contract scope. Two-way compatibility matters in rolling deployments, asynchronous messaging, and rollbacks.

A completion goal should state:
- Which client versions are currently supported?
- When does V1 support end?
- May new producers emit fields/enums old consumers do not understand?
- After a rollback, can old code read V2 records already written?
- Which V1 data must remain readable after the legacy API removal date?

If the answer is “forward compatibility is not needed”, ensure no deployment path forces old consumers to read new data.

## 15. Compatibility windows have a start and an end

A typical roadmap looks like:

```text
V1 baseline
     |
     v
Expand: deploy reader supporting V1 + V2
     |
     v
Migrate: shift producers V1 -> V2 incrementally
     |
     v
Observe: measure remaining V1 traffic/data
     |
     v
Contract: remove V1 writer, V1 adapter/reader gate by gate
     |
     v
Close: clean up flags, docs, and handoff
```

The **compatibility window** is the period during which both generations coexist. It depends on:
- Rolling rollout/canary duration.
- Client update cadence, mobile/offline clients.
- Queue retention, retries/poison messages.
- Database/archive/backup retention.
- DR environments and failover readiness.
- Rare events such as year-end reporting.
- How long the organization commits to supporting code rollback to V1.

For example, if offline devices are allowed to submit data after 90 days, seven days with zero V1 traffic may not be enough to claim the reader can be retired. If a consumer only runs at the start of every quarter, the observation window must cover that run or have proactively triggered tests.

## 16. Rollout flags differ from compatibility flags

Two common flag categories:

- **Rollout flag:** selects the percentage of traffic/tenants experiencing new processing, e.g., `useNewSerializerWriter`.
- **Compatibility flag:** allows handling legacy input/behavior during the transition, e.g., `acceptV1Payload`.

Example:

```yaml
migration:
  useNewSerializerWriter: false
  acceptV1Payload: true
  routeLegacyApi: true
```

A proper sequence:
1. Deploy consumers reading both V1/V2 first.
2. Enable the V2 writer gradually.
3. Monitor parse errors and metrics for both schemas.
4. Once all producers are stable on V2, remove the V1 writer.
5. Only remove the V1 reader after V1 data/consumers have ceased within the approved scope.
6. Finally delete unneeded flags and code branches.

Do not flip all three flags to `false` at once just because they share the `migration` prefix. Each has different acceptance gates and deadlines.

## 17. Dual-write requires reconciliation before removal

Dual-write writes to both the old and new schemas/stores:

```text
                   Application
                    /       \
                   v         v
               V1 store    V2 store
```

The risks:
- V1 write succeeds while V2 fails, or vice versa.
- Retries create duplicate records.
- Event ordering diverges.
- Both stores drift out of sync over time.
- Backfills and real-time writes overlap.
- Transactions are non-atomic across two storage systems.

Stopping dual-write requires:
- Reconciliation by primary keys, checksums/semantic values, or suitable checks.
- Conflict resolution rules and failed-record handling.
- Monitoring for partial writes and retries.
- Primary readers/consumers already migrated to V2.
- No valid consumers still requiring the V1 writer.
- A rollback plan that does not depend on continuing V1 writes.

If writing to two stores over the network without distributed transactions, define an eventual-consistency/outbox/idempotency contract; matching record counts alone do not prove zero data loss.

## 18. Dual-read and fallback signals

Dual-read can use different mechanisms:
- Try V2, fall back to V1 when missing.
- Read both V1 and V2 and compare results in shadow mode.
- Allow deserializing both V1/V2 schemas based on a version marker.

If you only measure HTTP 200, you cannot tell how many requests still take the V1 path. Observe:
- `legacy_reader_invocations`.
- `legacy_reader_success`.
- `legacy_reader_fallback`.
- `new_reader_success`.
- `unknown_format_rejections`.
- `schema_version_by_source`.

Metric names are examples only. Do not put user IDs, tokens, or raw payloads in metric labels. Measure by service/tenant class/client version at controllable cardinality without leaking sensitive data.

Only remove the V1 reader once edge cases such as archive restores, delayed messages, offline clients, and rollbacks are handled. If a separate restore tool retains V1 support, assign long-term maintenance ownership for it.

## 19. Controlled removal of temporary JVM flags

During Java 8 → Java 17+, some old libraries need flags such as:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED
```

These two serve different purposes: `--add-opens` grants deep reflection; `--add-exports` grants access to exported packages of a module to a target. They do not substitute for one another and may serve different libraries.

Removal workflow:
1. Identify the exact library or call stack requiring the flag.
2. Upgrade/refactor the library to use supported APIs.
3. Remove one exact flag in test/staging configuration.
4. Run integration tests exercising real reflection paths, not just startup.
5. Canary with the flag-free configuration.
6. Monitor for `InaccessibleObjectException`, `IllegalAccessError`, serialization/binding failures.
7. Remove the flag everywhere it is declared: `JAVA_TOOL_OPTIONS`, CLI, Dockerfiles, Helm/config maps, IDE runs, Maven Surefire, Gradle test JVM args.
8. Record evidence of the changed library version and configuration.

**Warning:** `--illegal-access` options from the JDK 9–16 era underwent lifecycle changes; do not use them as a long-term solution for JDK 17+. Meanwhile, `--add-opens` is not inherently a bug in every case: there can be a valid need for an evaluated library or tool. Distinguish temporary settings from formally managed exceptions.

## 20. Removing unneeded JDK 8 build/config settings

Once raising the minimum supported JDK is approved:
- Remove Java-8-only build profiles when no consumers remain.
- Remove `-source 8 -target 8` / `--release 8` if the target is genuinely raised.
- Remove Maven `systemPath` pointing to `tools.jar`, `rt.jar`.
- Replace scripts copying `jdk/jre/` with an appropriate runtime image.
- Remove unsupported `lib/ext`/endorsed mechanisms.
- Upgrade Maven/Gradle plugins and annotation processors.
- Remove dependency overrides used to work around old bugs once fixed.
- Update IDEs, CI matrices, Docker base images, and release documentation.

Maven example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Gradle Kotlin DSL example:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Do not change `--release 8` to 17 if the product still commits to supporting Java 8. Dropping an old JDK must follow a support-policy decision, not a desire to make build scripts shorter.

## 21. Removing Java EE / Jakarta compatibility in cohesive groups

When transitioning from the Java EE namespace `javax.*` to Jakarta EE `jakarta.*`, adapters may be kept to support both generations:

```text
Old javax web adapter --> Domain contract <-- New jakarta web adapter
```

Before deleting the old adapter:
1. No valid runtime/container still needs to load the corresponding `javax.servlet.*` interfaces.
2. Frameworks, ORMs, validation, and CDI/JMS providers belong to the target generation.
3. Third-party plugins/extensions have been upgraded or replaced.
4. No source/generated code regenerates old imports.
5. Public API contracts do not expose legacy types at boundaries.
6. Integration tests run on real containers with zero `ClassNotFoundException`/`NoClassDefFoundError`.
7. If separate legacy services remain, HTTP/queue boundaries still honor their contracts or have an independent plan.

**Do not replace every `javax.*` with `jakarta.*`.** Packages such as `javax.sql`, `javax.naming`, `javax.crypto`, and `javax.tools` still belong to Java SE in their respective contexts. Cleanup must classify API ownership accurately.

## 22. Removing dependency pins and plugin compatibility overrides

A temporary dependency override may be added during a framework upgrade—for instance forcing a transitive library onto an older version to keep an old plugin working. Over time, this can cause:
- Mismatch with the BOM/framework.
- `NoSuchMethodError` or linkage failures when the framework calls new APIs.
- Unpatched security advisories.
- Dependency graph complexity making the next upgrade harder.

A pin-removal plan:
1. Inspect the actually resolved version, not just the declared version.
2. Read the support matrix of the framework/plugin with the newer dependency.
3. Remove the pin on a test branch.
4. Compare the dependency tree before and after.
5. Run compilation, integration, binary linkage, and runtime tests.
6. Canary if the dependency touches critical paths.
7. Delete the pin along with outdated notes/documentation.

If the pin is still needed, document the target version, owner, and specific rationale; do not leave unexplained entries in `pom.xml` or `build.gradle`.

## 23. Retiring legacy endpoints requires evaluating both consumers and data

An old endpoint may still be used by:
- Unupdated mobile apps.
- Partner integrations with long release cycles.
- Infrequently executed scheduled tasks or webhooks.
- DR systems activated only on failover.
- Offline clients replaying old requests.
- Monitoring or synthetic probes running in separate environments.

To retire an endpoint:
- Define the API contract, notice period, and end-of-support date.
- Collect traffic metrics by client/version under appropriate privacy policies.
- Verify consumers have migrated or reached formal end of support.
- Run tests covering routing, authentication, authorization, and error behavior.
- Ensure gateways/caches/ingresses contain no hidden routes to the old version.
- Clean up docs, API specs, SDKs, and monitoring after removal.

“The endpoint has zero traffic today” is insufficient if contracts allow seasonal calls. Some systems require long deprecation windows and partner notices before shutdown.

## 24. Removing compatibility modes for encoding, locale, and timestamps

Upgrading the JDK can expose dependencies on charset/timezone/locale defaults—for example since JDK 18 under JEP 400, the default charset was standardized to UTF-8 within the specified scope.

Sometimes applications add:
- `-Dfile.encoding=...` to mimic the old environment.
- Legacy formatters for dates/times.
- Fallback parsers accepting local-timezone timestamps.
- Custom decimal/coercion modes.
- A data conversion layer from old encodings.

Remove these layers only when:
1. Input/output contracts specify explicit charsets/timezones/formats.
2. Historical data has been migrated or has an independently owned decoder.
3. Clients depending on the old format have migrated.
4. Tests cover multi-timezone, DST, locale, and large-number cases.
5. Business data does not silently change due to implicit defaults.

Do not view deleting the `file.encoding` flag as progress if code still relies on `Charset.defaultCharset()` for a protocol requiring stability. The sustainable approach is using explicit charsets at data boundaries.

## 25. When should a workaround stay as an official configuration?

Temporary debt cannot always all be cleared in the same release. For example, a third-party library may not yet ship a Jakarta-compatible version, or a partner still sends a contracted format.

A **governed exception** can be approved if:
- There is a concrete business or contractual reason.
- Risk is assessed and approved by an authorized stakeholder.
- Blast radius is bounded.
- Monitoring and mitigations exist.
- An accountable owner is assigned.
- A specific review date and expiry/trigger are set.
- It is not mislabeled as “fully removed”.

A useful status report format:

```text
Cleanup:
  removed: 18
  approved_exceptions: 2
  unresolved_blockers: 0
  unowned_items: 0
```

Numbers are illustrative. Approved exceptions can allow concluding **a phase** of the program, but must remain visible and tracked; they must not be treated as proof of zero risk.

## 26. Do not delete the rollback path before the rollback window closes

A common trap:
- V2 deployment works.
- The team deletes the V1 reader and old schema after one day.
- The next day a serious regression surfaces in V2.
- Rollback to V1 fails because V2 already wrote incompatible data.

Distinguish:
- **Code rollback:** redeploying old artifacts/configs.
- **Runtime rollback:** returning to old JDK/container images.
- **Data rollback:** restoring/converting schema-altered data.
- **Forward-fix:** keeping the current runtime and deploying a fix without rolling back data.

Sometimes data rollback is too risky, so forward-fix plus an appropriate recovery plan is chosen. Either way, exit criteria must specify an **approved recovery path**, not just say “backups exist”.

A generally safer sequence:
1. V2 producers are stable.
2. The V1 rollback window expires per a documented decision.
3. No V1 consumers remain.
4. Legacy data/schemas are handled.
5. Compatibility code is removed and restore capability is reconciled.
6. Legacy schemas/infra are torn down via a separate decision if hard to reverse.

## 27. Canarying when disabling flags and adapters

Do not delete multiple independent workarounds in the same batch if regressions would become impossible to attribute.

A workflow:
1. **Prepare:** have tests/metrics covering the feature affected by the flag.
2. **Disable in nonproduction:** remove the flag in test/staging and run the matching suite.
3. **Canary:** apply to a controlled subset of traffic/instances.
4. **Observe:** compare against baselines and related rare flows.
5. **Expand:** raise instance/tenant share.
6. **Remove:** delete the flag, code branch, and old config documentation.
7. **Close:** verify the new release no longer carries the flag in real deployments.

Example:

```text
100% legacy flag enabled
           |
           v
     Canary: flag off
           |
     Metrics/contracts OK?
           |
     +-----+-----+
     |           |
    No          Yes
     |           |
Restore        Expand rollout
configuration     |
                   v
             Remove flag/code
```

**Disabling a runtime flag** and **deleting flag-supporting code** happen at different times. If rollback requires re-enabling the flag, do not delete the corresponding branch yet. On the other hand, do not leave dead code branches around indefinitely after the rollback window ends.

## 28. Pre-removal gate checklist for a configuration

A minimal gate for each item:
- [ ] Configuration owner and purpose are documented.
- [ ] Evidence confirms no consumers/execution paths still need the configuration.
- [ ] Historical data and retention are handled.
- [ ] Rollback/forward-fix path is identified.
- [ ] Key positive and negative tests pass via the new path.
- [ ] Metrics, alerts, and an appropriate observation window exist.
- [ ] Removal has been tested in staging/canary.
- [ ] Dependencies/runtime work cleanly without the flag.
- [ ] Security reviewer examined the setting if access control is affected.
- [ ] The change PR references the tracking ticket/decision.

An unverified item must not be deleted simply because the overall program faces pressure to close a milestone. If removal is impossible right now, record the blocker and assignee instead of leaving it untracked.
## 29. “No longer used” must be proved from multiple sources

Claiming a “flag is no longer used” easily fails if backed by only one data source:
- Code search only inspects source, missing deployment environment variables.
- Runtime telemetry only shows environments where logging is enabled.
- Traffic metrics miss offline clients that have not sent requests yet.
- Dependency reports miss code loaded via reflection.
- Test coverage misses quarterly scheduled jobs.
- “0 errors” does not prove the legacy code path went unexecuted.

Better is evidence triangulation:

```text
       Static evidence
       (source/config)
             /   \
            /     \
           v       v
 Runtime telemetry ---- Contract/integration testing
     (production)           (behavior)
```

For data migration, add **storage inventory and reconciliation**. For API retirement, add **client contract/support policy**. For JDK runtime retirement, add **process/deployment inventory** across every environment in scope.

There is no absolute proof covering every possible future request. Exit criteria are an engineering decision grounded in support scope, observable data, and risk accepted by accountable stakeholders.

## 30. Do not remove logging and metrics too early

Some telemetry is added temporarily for migration:
- Running Java version per instance.
- Fallback counts into the V1 parser.
- Legacy API usage counts.
- Unknown enum/schema warnings.
- Authentication failures after changing security frameworks.
- Queue lag, dual-write divergence, and cleanup errors.
- JPMS/reflection errors.
- New JDK P99 latency versus baseline.

Even after removing compatibility code, keep an appropriate observation window for critical metrics. Deleting logging/alerts alongside the flag can blind the team to regressions.

You can separate:
- **Temporary telemetry:** metrics measuring only a soon-to-be-deleted branch; once proven absent past the rollback window, they can be removed.
- **Long-term operational telemetry:** API errors, security, data integrity, and latency; these must be maintained continuously.

Metrics have lifecycles too: delete obsolete dashboards, alerts, or SLO references after updating official monitoring. Just do not clean them up before visibility into the new version is established.

## 31. A phased decision table

| Phase | Mandatory condition | Decision |
|---|---|---|
| **Go-live target** | Build/runtime/critical tests pass; rollback plan executable. | Authorize rollout of new JDK/framework. |
| **Promote canary** | No API/security regressions; metrics within budget. | Expand traffic/instances. |
| **End compatibility window** | Producers/consumers migrated; data and retention handled. | Authorize ordered removal of legacy writers/adapters/readers. |
| **Remove transitional flags** | New dependencies run stably without flags; rollback defined. | Remove temporary code/config branches. |
| **Close program** | Every item removed or a tracked exception with owner/expiry; docs and handoff done. | Mark program complete. |

Do not collapse everything into a single “Done” state, because it obscures why closure is blocked. For example, migrated code waiting on an un-upgraded partner client is an external dependency issue, not an implementer failure.

## 32. Sample Definition of Done for a service

Below is an adaptable template:

```yaml
migrationId: JAVA-COMPAT-2026-ORDER
component: order-api
source:
  jdk: "8"
  framework: "legacy-baseline"
target:
  jdk: "17"
  framework: "approved-supported-release"
scope:
  environments: [ci, staging, production, disaster-recovery]
  workloads: [api, consumer, nightly-batch]
build:
  compilerRelease: 17
  dependencyGraphReviewed: true
runtime:
  allInstancesTargetJdk: true
  scheduledJobsVerified: true
contracts:
  http: "passed"
  messaging: "passed"
  storedData: "reconciled"
security:
  negativeTests: "passed"
  exceptions: []
operations:
  rollbackDrill: "passed"
  dashboardsUpdated: true
cleanup:
  jvmReflectionFlagsRemoved: true
  legacyCodecWriterRemoved: true
  legacyCodecReaderRemoved: false
  oldReaderException:
    reason: "Archived data still within retention"
    owner: "data-platform"
    reviewTrigger: "Archive conversion complete"
evidence:
  ciBuild: "link-to-verified-ci-run"
  deployment: "link-to-production-release"
  compatibility: "link-to-contract-test-report"
  rollback: "link-to-drill-record"
decision:
  releaseGate: "passed"
  programClosure: "pending-exception-approval"
```

This is an **illustrative governance record**, not configuration read by the JVM. In a real project, populate verified versions, evidence IDs, and validated states instead of manually marking fields `true` without supporting data.

Notably: a migration can pass the release gate yet remain in `programClosure: "pending..."` because a compatibility reader must live longer. Transparent reporting like this is far better than premature closure.

## 33. Using quantitative criteria without creating perverse targets

Useful indicators include:
- Percentage of workloads in scope running the target JDK.
- Number of deployments still on old JDK images.
- Number of compatibility flags still active.
- Count of legacy code paths still executed.
- Number of unmigrated V1 records/messages.
- Deserialization failure rate, dual-write mismatch rate.
- Number of open security exceptions.
- Test coverage across critical integration paths.
- Count of unowned or overdue blockers.
- Number of passed/failed rollback drills.

Do not make “0 flags” the sole target if deleting a flag breaks committed backward compatibility. Likewise, do not chase “100% workloads on JDK 17” while skipping DR images, manually launched processes, or data migration tooling.

A good metric pairs a **scope definition** with an **absolute count**. For example, “100% (35/35 inventoried workloads)” is far clearer than a context-free “100%”.

## 34. Documentation and ownership completion criteria

Once code/config stabilizes, update:
- README/build instructions for the target JDK and toolchain.
- Local development guides.
- Base image and container build documentation.
- Supported API/schema versions and client matrix.
- Startup/shutdown/rollback runbooks.
- Debugging guides for JPMS, classpath, serializer, and TLS errors.
- Dashboards/alerts and alert ownership.
- Updated architecture/dependency diagrams.
- On-call handoff and JDK patching cadence.
- Active exceptions list and review schedule.

Removing a workaround from source without updating the runbook can cause an on-call engineer to re-enable the old flag during an incident. “Completed” must include **operational knowledge**.

Additionally, when the migration project ends, transfer open exceptions to official operational backlogs/teams rather than leaving them assigned to a disbanded project group.

## 35. RACI and closing-gate approvers

A sample breakdown:

| Role | Core responsibility |
|---|---|
| Service owner | Ensures business behavior and compatibility. |
| Platform/JDK owner | JDK distribution, modules, container/build toolchains. |
| Data owner | Reconciliation, retention, schema/backup/restore. |
| Security owner | Reviews security flags, TLS, authentication, and exceptions. |
| QA/test owner | Evidence of regression/contract coverage. |
| SRE/operations | Canaries, metrics, alerts, disaster recovery, rollback drills. |
| Release manager | Coordinates go-live, compatibility window, and closeout gates. |
| External client/partner owner | Upgrade schedules and deprecation notices. |

Not every organization has this many distinct roles; one person may hold several hats. What matters is that every acceptance gate has an **accountable owner**, and risk acceptance decisions are never made implicitly.

## 36. Complete example: upgrading Java 8 to 17 and removing workarounds

Suppose an order application consists of an API, a Kafka consumer, a month-end batch, and a DB with JSON columns.

### 36.1. Initial state

```text
API: JDK 8
Consumer: JDK 8
Monthly Batch: JDK 8
JSON V1: all producers and readers
JVM flags: old JDK profile
Database: old schema
CI: Java 8
```

### 36.2. After deploying the first V2 release

```text
API: JDK 17
Consumer: JDK 17
Monthly Batch: still JDK 8
JSON writer: V2 behind feature flag
JSON reader: V1 + V2
Database: expanded schema
CI: build 17, tests 17
--add-opens: enabled for old mapper
```

Clear progress has been made here, yet it **does not qualify for closure**.

### 36.3. Path to completion

1. Upgrade the mapper to a JDK-17-supported version.
2. Remove `--add-opens` in staging, then canary.
3. Run the month-end batch on JDK 17 against representative data/fixtures.
4. Cut all JSON producers over to V2.
5. Measure and resolve any V1 payloads in queues, DBs, and archives.
6. Wait out the planned V1 rollback window; execute a restore drill.
7. Delete the V1 writer first, then the V1 reader once eligible.
8. Retire Java 8 images and CI profiles from all in-scope workloads.
9. Update docs/runbooks, dashboards, and the security exception inventory.
10. Business/data/security/SRE leads sign off on their respective gates.

### 36.4. Intermediate status report format

| Item | Status | Missing |
|---|---|---|
| API | Runtime migrated | Reflective access flag not yet removed. |
| Consumer | Runtime migrated | Needs V1 fallback measurement. |
| Monthly batch | Pending | Not yet run on JDK 17. |
| JSON writer | Partially migrated | V1 feature flag still present. |
| JSON reader | Dual support | Depends on archive retention. |
| DB schema | Expanded | Reconciliation and rollback window remaining. |

Closure is marked only once items are finished or formally excepted. Clear intermediate status reporting keeps Prime/release owners from equating coding progress with production readiness.

## 37. Common mistakes

**“Green build means finished.”** Fails to confirm runtime, data, security, performance, and rollout.

**“Ran one day error-free, so drop backward compatibility.”** May miss batch jobs, offline clients, delayed queues, and backup restores.

**“Removing the flag caused no startup error, so the flag was useless.”** Reflection errors may appear only on rare code paths.

**“Remove V1 writer and reader at the same time.”** Long-lived V1 data or code rollback may still need the reader.

**“Turn off dual-write when record counts match.”** Fails to prove values, ordering, idempotency, and partial-failure correctness.

**“Loosen TLS/authorization temporarily without recording it.”** Security exceptions require an owner, scope, expiry, and approved decision.

**“Delete every flag named legacy.”** Some flags may back official support contracts and must be classified first.

**“The sooner rollback mechanisms are deleted, the cleaner.”** Premature cleanup can render the system unrecoverable after a regression.

**“Zero requests on the dashboard means all clients upgraded.”** Telemetry may be missing or clients may connect infrequently.

**“Delete metrics as soon as the flag is deleted.”** Removes visibility into regressions during the following window.

**“No more Java 8 in primary production.”** DR, command-line jobs, or plugin runtimes may still use Java 8.

**“Move everything unfinished into permanent exceptions.”** Exceptions without expiries/owners are ungoverned technical debt, not trustworthy closure.

## 38. Migration program closure checklist

- [ ] Complete inventory of workloads, environments, and runtimes within scope exists.
- [ ] Definition of Done includes scope, thresholds, evidence, owners, and observation window.
- [ ] Build/compile uses a supported toolchain and target.
- [ ] Runtime version is verified across all relevant deployments and jobs.
- [ ] Dependency graph/BOM/plugins and generated code are inventoried.
- [ ] API/data/protocol contract tests run on the target runtime.
- [ ] Negative/security cases and invalid inputs are tested.
- [ ] Performance/SLOs meet agreed criteria under representative load.
- [ ] Backup/restore and rollback/forward-fix have been reviewed and practiced.
- [ ] Data exists on V1 clients, payloads, queues, and archive retention.
- [ ] Old readers/adapters are not deleted before the support/rollback window ends.
- [ ] Dual-writes are reconciled and partial failures are addressed.
- [ ] All temporary `--add-opens`/`--add-exports` are removed or tracked as exceptions.
- [ ] No `rt.jar`/`tools.jar` scripts or unapproved out-of-scope Java 8 images remain.
- [ ] Temporary dependency pins/profiles/feature flags are removed or owned.
- [ ] No unowned or overdue security exceptions exist.
- [ ] Canary/rollout is observable and introduces no new regressions.
- [ ] No dead code branches, broken dashboards/alerts, or stale docs remain.
- [ ] Every blocker has an owner; residual exceptions are approved with review dates.
- [ ] Accountable stakeholders signed off per organizational policy.

## 39. References

- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module path, and compatibility context when upgrading to Java 9+.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): context on access to internal APIs.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation policy in modern JDKs.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change in JDK 18 and its impact on legacy data.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): example of removing dependencies that assumed modules were provided by the JDK.
- [Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/21/migrate/): changes across JDK generations and migration guidance.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): determining the resolved dependency graph.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): inspecting dependencies and version resolution.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): example of framework security policies that need testing during migration.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): reference when retiring adapters migrating from Java EE to Jakarta.
- [Semantic Versioning](https://semver.org/): evaluating version upgrade scope; does not replace release notes/compatibility matrices.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): access control and negative testing principles.
- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): defining signals/monitoring for operations and releases.
- [The Site Reliability Workbook](https://sre.google/workbook/): practical SLOs, rollouts, monitoring, and operations.

## Conclusion

A Java migration program is truly **complete** only when scope is defined, runtime and behavior are verified, legacy data/consumers have a handling roadmap, security risks are controlled, operations have evidence, and all transitional configurations are either removed or placed on an accountable exception list. Deleting flags is not an end in itself: removing them too early can break rollback and historical data, while keeping them too long makes the system complex and unsafe. The sustainable way to close is setting measurable acceptance gates, sequencing expand–migrate–contract phases, testing each flag's impact, canarying and observing before deleting code/config, and documenting evidence and ownership. That way, the “DONE” state reflects a system genuinely ready for ongoing maintenance and future upgrades, rather than a single successful build.
