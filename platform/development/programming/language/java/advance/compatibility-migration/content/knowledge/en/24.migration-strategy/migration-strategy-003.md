# Choosing Small, Verifiable, and Reversible Migration Steps

Upgrading a long-lived Java system from JDK 8 or 11 to JDK 17, 21, or newer generations is not just changing `JAVA_HOME` and fixing a few compilation errors. A **Java Advance Compatibility Migration** effort can simultaneously touch dependencies, Gradle/Maven, application servers, the module system, reflection, security providers, TLS, garbage collectors, logging, Java EE/Jakarta EE, deployment mechanisms, and data formats. If all changes are bundled into a single release, when an error occurs it is very hard to pinpoint the root cause; rolling back to the old version may also no longer be safe.

A more practical strategy is to break the migration down into **small steps with clear verification criteria and pre-prepared rollback paths**. “Small” does not mean only a few lines of code. A step is considered small when its blast radius is bounded, the number of hypotheses to test is manageable, results are observable, and the change can be reversed or disabled within an acceptable timeframe.

This lesson walks through how to define the boundaries of a migration step, classify reversible versus irreversible changes, organize tests/CI/CD, use feature flags and canaries, maintain data compatibility when running two versions side by side, set rollback conditions, and build a JDK upgrade roadmap without turning every deploy into a gamble.

## 1. What does a “small step” mean?

A good migration step does more than change one component; it must answer five questions:

1. **Goal:** after this step, in what way is the system better or ready for the target JDK?
2. **Scope:** which modules, services, APIs, jobs, user groups, or resources are affected?
3. **Evidence:** which tests, benchmarks, logs, metrics, or comparisons prove the change works?
4. **Stop conditions:** when must rollout stop advancing or release halt?
5. **Rollback path:** if it fails, how do we redeploy the old artifact, turn off a flag, shift traffic, or recover data?

Example of a reasonable step:

> Upgrade a background worker from JDK 11 to JDK 17 while keeping source, dependencies, and message formats unchanged; run contract tests against the message broker, deploy a 5% workload canary, monitor error rate/lag, and be able to switch the worker back to the JDK 11 image as long as the message format has not changed.

Example of a step that is too large:

> Simultaneously upgrade JDK 11 to 21, migrate Spring Boot 2 to 3, change `javax.*` to `jakarta.*`, replace the ORM, alter the database schema, enable virtual threads, and upgrade all logging/tracing agents.

If the latter rollout causes `NoSuchMethodError`, `SSLHandshakeException`, or higher p99 latency, too many variables have changed, making isolation difficult.

### 1.1. Small by independent variables, not only by file count

A pull request changing imports across 300 files due to a namespace rename can be a well-bounded step, provided it only changes namespaces, preserves logic, and verifies contracts. Conversely, a single-line dependency version bump can alter dozens of transitive dependencies and framework behavior.

Therefore you must analyze the **impact graph**, rather than using lines of code as the sole risk metric.

### 1.2. Verifiable means having an independent signal

A “green build” step does not necessarily verify runtime behavior. For example:

- `JavaCompile` succeeds, but the container still uses the old JDK.
- Tests run on JDK 21 while production runs on JDK 17.
- HTTP 200 is returned, but the response schema has changed.
- Startup succeeds, but `ServiceLoader` fails to find a provider.
- The UI still renders, but transactions are committed twice.
- The app runs, but latency or heap grows past the SLO.

Evidence must match the **hypothesis of the migration step**, not just a generic indicator.

### 1.3. Reversible means restoring operational state

`git revert` only undoes source code. It does not restore:

- A database schema whose column has been dropped.
- Data re-encrypted with a key the old version cannot read.
- Messages/events already emitted in a new format.
- An old certificate that has already been revoked.
- An external API whose contract has changed.
- Data written using a new enum or serialization format.
- A desktop client that auto-updated and does not support downgrades.

**Rollback must cover code, runtime, configuration, dependencies, traffic, data, and external side effects.** For changes that cannot be directly reversed, the design must be adapted to create a backward-compatibility window or a controlled recovery plan.

## 2. Dimensions of change in a Java migration

A project has many compatibility layers, so they do not all have to move at once.

| Dimension of change | Example | Risk if combined together |
|---|---|---|
| JVM running build tool | Gradle daemon JDK 11 → 17 | Plugins/build scripts fail to start |
| Compiler toolchain | `javac` 11 → 17 | Annotation processors, bytecode tools fail |
| Source/bytecode target | `--release 11` → 17 | Older runtime cannot load classes |
| Runtime JDK | Container JDK 11 → 17 | Reflection/TLS/GC/charset/providers differ |
| Dependencies | Frameworks, JDBC, ASM, Byte Buddy | Binary incompatibility and new behaviors |
| Application server | Servlet container Javax → Jakarta | Namespaces and lifecycles differ |
| JPMS | Classpath → module path | `requires`, `exports`, `opens`, split packages |
| Security | Certificates, TLS policies, signers | Connections or signatures rejected |
| Execution model | Fixed pool → virtual threads | Concurrency and resource saturation change |
| Deployment | JAR → runtime image/native package | Launchers, config, and updates differ |
| Data contract | DB schema, JSON schema, event version | Old version cannot read new data |

An often beneficial strategy is to **keep as many dimensions stable as possible in each step**, then measure the difference.

For instance, upgrade the JDK while staying on the traditional classpath before adopting JPMS; or upgrade ASM/Byte Buddy libraries to read new bytecode before enabling a new compiler target.

## 3. Classifying steps by reversibility

Not all changes have the same rollback path.

| Step type | Example | Reversibility | Preparation needed |
|---|---|---|---|
| Toggleable configuration change | Feature flag, executor strategy | Usually high | Disable quickly, verify state is unchanged |
| Artifact/runtime swap without data change | JDK 11 → 17 image | Usually high if contracts stay intact | Old artifact, image digest, traffic switch |
| Internal dependency upgrade without public API change | JDBC client, parser | Depends on behavior | Regression and integration tests |
| Backward-compatible contract change | Add an optional JSON field | Medium–high if consumers ignore unknown fields | Consumer-driven contracts |
| Additive database change | Add a nullable column/index | Usually reversible at application level without dropping DB objects | Expand-contract, controlled migration |
| Changing persisted data format | New serialization/encryption | Low if old version cannot read it | Dual read, versioning, backup/recovery |
| Public namespace/framework change | Javax → Jakarta | Low without an intermediate compatibility layer | Service boundaries, separate artifacts, coordinated rollout |
| Dropping columns / changing data semantics | Drop legacy column | Low | Delayed contract phase, backup, tested restore |
| Updating external system side effects | Sending money, sending emails, revoking certificates | Not directly reversible | Idempotency, compensating actions, runbook |

**Reversibility must be confirmed by testing**, not assumed based on a “config-only” or “minor version” label.

## 4. Mapping dependencies and defining transition boundaries

Before choosing the first step, you need to know which components are coupled and which can be separated.

Example:

```text
Web client
    |
    v
API Gateway
    |
    +--> Order Service (JDK 11)
    |       |
    |       +--> PostgreSQL
    |       +--> Payment API
    |       +--> Kafka: order-events.v1
    |
    +--> Inventory Service (JDK 11)
            |
            +--> PostgreSQL
            +--> Inventory SDK
```

If Order Service has stable HTTP/event contracts and does not share Java objects across a classloader with Inventory Service, each service can be upgraded independently. However, if two services share a database schema and perform breaking migrations, separating their rollouts remains constrained.

### 4.1. Ways to slice boundaries

- **By service:** an independent microservice.
- **By deployment group:** a group of pods/instances.
- **By request cohort:** a user segment or traffic percentage.
- **By endpoint:** a single API flow.
- **By job:** a scheduled/batch/consumer worker.
- **By dependency boundary:** a client library or integration adapter.
- **By artifact:** a separate plugin or command-line tool.
- **By data contract:** a schema version or an event type.

Choosing boundaries depends on deployability, data consistency, and observability, not necessarily Java package structure.

### 4.2. Distinguishing technical dependencies from operational dependencies

A service may be independent at the code level yet operationally coupled by:

- Shared database and transactions.
- Shared queue with unversioned messages.
- Shared authentication/certificates.
- Shared file formats over storage.
- Application server hosting multiple WARs.
- Cache with an unstable serialization format.
- Desktop clients not upgraded simultaneously.

These points must appear in the impact map; otherwise, “upgrading one service” may in practice mean changing the entire system.

## 5. Prioritizing steps by value and risk

Do not start with the largest step or the part that is “easiest to rename imports”. Pick steps that can **reduce uncertainty** without expanding the blast radius excessively.

A decision table you can use:

| Candidate step | Value gained | Risk | Ease of verification | Ease of rollback |
|---|---|---|---|---|
| Pin Gradle wrapper and compiler toolchain | Reproducible builds | Low–Medium | High | High |
| Add CI job running tests on target JDK | Early error detection | Low | High | High |
| Upgrade ASM/Byte Buddy and test agents | Support new classfiles | Medium | High | Medium–High |
| Upgrade runtime for a stateless worker | Validate production JVM | Medium | High | High if data contract is stable |
| Migrate all of JPA/Hibernate + Jakarta | Prepare new framework stack | High | Medium | Medium–Low |
| Breaking schema change | Simplify data | High | Medium | Low |
| Enable virtual threads system-wide | Potential I/O concurrency boost | High | Needs load testing | Medium if side-by-side config exists |

This is a qualitative example, not a default scoring rubric for every organization. A library whose security support has ended may need priority despite a complex migration; in that case, **split it into smaller steps** instead of postponing indefinitely.

### 5.1. Illustrative scoring formula

You can evaluate on a 1–5 scale:

```text
Priority =
    (Business value + Risk reduction + Learning value)
    / (Implementation effort + Blast radius + Rollback difficulty)
```

Do not treat the formula as an exact quantitative model. It serves to force the team to discuss the value, risk, and reversibility of each step.

### 5.2. Starting with steps that build observability

Before upgrading the runtime, adding tests/metrics can be a high-value first step:

- Run the test suite on the old and new JDK in parallel.
- Capture baseline throughput/latency/heap.
- Save the dependency tree and versions.
- Enable alerts for handshake/PKIX errors.
- Log runtime version at startup.
- Identify artifact/container digests and rollback procedures.

These steps do not upgrade the JDK directly, yet they **reduce risk for every subsequent step**.

## 6. Defining a “migration step” like an experiment

Each step should have a consistent specification.

| Field | What to record |
|---|---|
| Goal | Desired technical or business outcome |
| Hypothesis | Why this change is expected to work |
| Scope | Service, module, endpoint, user cohort, environment |
| Variables changed | Which JDK, dependency, or configuration changes |
| Preconditions | Tests/backups/compatibility prepared |
| Evidence | Unit/integration/contract/load tests, metrics |
| Pass criteria | Conditions to increase rollout |
| Stop criteria | Conditions under which rollout does not advance |
| Rollback | How to disable/revert the change and its limitations |
| Owner | Responsible person/team |
| Decision point | When to review data and decide next action |
| Artifact | Image digest, JAR hash, feature flag, manifest version |

Short example:

```yaml
step: migrate-order-worker-runtime
change:
  from: JDK 11 runtime image
  to: JDK 17 runtime image
  code_changes: none
scope:
  deployment: order-worker
  canary_fraction: "5%"
preconditions:
  - Can read and write message schema v1
  - Old image digest retained
  - Contract tests passing
evidence:
  - Message processing success
  - Queue lag
  - p95 processing latency
  - DLQ count
rollback:
  - Stop new canary consumers
  - Switch traffic/partition assignment to previous image
  - Confirm offsets and idempotency
```

This is an illustrative template, not a CI/CD schema automatically understood by a specific tool. Thresholds and operational commands must be filled in according to the real system.

## 7. Separating build JDK, compiler, and runtime into distinct steps

A common strategic mistake is changing the JDK running Gradle, the compiler target, and the production runtime all at once.

### 7.1. Step A: make builds reproducible

Pin a supported Gradle wrapper or Maven version/plugins. Record the build JVM and toolchain. Check dependency locks/versions and avoid uncontrolled dynamic versions.

With Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

This is an example of **JDK 17 compiler, Java 11 target bytecode/API**. It does not force the Gradle daemon to run on JDK 17, and it does not by itself prove runtime dependency compatibility with Java 11.

### 7.2. Step B: run tests on the target JDK

You can add a CI job using the JDK 17 runtime while production remains on JDK 11. Keep code and dependencies unchanged to isolate runtime errors: blocked reflection, TLS, classloaders, charsets, native libraries, or agents.

When new-JDK tests fail, the error is isolated to the runtime change rather than mixed with framework upgrades.

### 7.3. Step C: upgrade incompatible dependencies one group at a time

For example:

- ASM/Byte Buddy/JaCoCo must be able to read the target class files.
- JDBC drivers and ORMs must support the target JDK.
- Logging/tracing agents must support the JVM version.
- Libraries using JDK internal APIs must be updated.
- Security providers must support new TLS/certificate policies.

Upgrade clearly related groups one by one, save the dependency tree, and run the regression suite.

### 7.4. Step D: replace the production runtime of one deployment unit

Once the artifact passes on the new JDK in test environments, choose a worker or service that shares no internal state to run as a canary.

### 7.5. Step E: raise source/release target if needed

Only after the runtime is stable should you consider adopting new language features and Java APIs. If a library must still run on Java 11, continue releasing classfile target 11 for that library even after the build process and other applications have moved to JDK 17.

### 7.6. Step F: architectural transitions after the baseline is stable

Adopting JPMS, moving `javax.*` to `jakarta.*`, or enabling virtual threads are architectural/contract changes that can be independent of the runtime upgrade. Make them separate steps if possible.

## 8. Maven and Gradle: building a test matrix without changing production immediately

### 8.1. Maven Compiler Plugin and `release`

Maven example:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

The compiler must be new enough to support `--release 11` and the plugin must be compatible; this parameter only constrains Java platform APIs/bytecode in your compilation and does not automatically downgrade bytecode inside dependencies.

### 8.2. Gradle tests with a specific runtime toolchain

Example:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

You can run a separate test job with a Java 17 launcher in CI. What matters is reporting the **actual JDK of the test worker**, not merely `java -version` in the shell.

### 8.3. Conceptual matrix configuration

```text
Job 1:
  Gradle daemon JDK: 17
  Compiler:           17
  --release:          11
  Test runtime:       11

Job 2:
  Gradle daemon JDK: 17
  Compiler:           17
  --release:          11
  Test runtime:       17
```

If Job 1 passes while Job 2 fails, there is likely a behavioral or runtime compatibility change. If Job 1 fails due to classfile version, check the compiler release setting or dependencies. Isolating variables shortens investigation.

### 8.4. Do not treat the test matrix as absolute proof

An integration path not exercised in tests can still fail on the new JDK. Combine functional testing, staging, canary, observability, and runtime compatibility checks for system dependencies.

## 9. Choosing verification points for each step

Do not use the same set of criteria for every change. For example:

| Migration step | Valuable evidence |
|---|---|
| Upgrade JDK runtime | Startup, smoke, TLS/PKIX, reflection, integration, JVM metrics |
| Upgrade logging agent | Agent active, complete traces/metrics, no spike in overhead |
| Upgrade ORM | Transaction semantics, lazy loading, SQL behavior, database integration |
| Switch Javax/Jakarta | Servlet/filter/listener lifecycle, injection, JPA, Validation, REST |
| Upgrade Byte Buddy | Mocks/proxies, instrumentation, classfile parser, runtime agents |
| Enable virtual threads | Load tests, DB waiters, CPU, p99, pinning/cancellation |
| Change JSON schema | Backward/forward contract tests and consumer compatibility |
| Change DB schema | Both-version read/write tests, migration correctness, index performance |
| Change TLS/certificate | Handshake with all client classes and rollback/cert chain |
| Change container image | Startup, health, configuration, native libraries, data paths |

### 9.1. Test pyramid for migration

A system usually needs multiple layers:

```text
           Production canary metrics
                 /        \
           End-to-end critical flows
             /            \
      Integration & contract tests
           /               \
     Unit tests & static checks
```

Fast tests should run on every commit. End-to-end and canary verify assumptions that cannot be fully reproduced in unit tests, but they do not replace a fast test base.

### 9.2. Negative testing matters as much as happy paths

After upgrading Validation or a security provider, the application still returns HTTP 200 for valid data. But if invalid data is also accepted, the migration has introduced a dangerous regression.

You need to test expected failure scenarios:

- Input missing required fields.
- Expired/invalid certificates.
- Unsupported event schema versions.
- Downstream API timeouts.
- Refused database connections.
- Retries not creating duplicate side effects.
- Consumers receiving out-of-order messages.
- Authorization properly denied.

### 9.3. Checking binary compatibility

When changing library versions, `NoSuchMethodError`, `NoSuchFieldError`, or classloader conflicts may appear only at runtime. API/binary diff tools and smoke tests with actual artifacts can supplement source compilation.

## 10. Setting pass/fail criteria before deploying

A canary without thresholds is an uncontrolled deployment. Criteria should be defined before looking at data to avoid redefining success to match results.

Illustrative example for a stateless service:

| Metric | Baseline | Illustrative threshold to continue |
|---|---|---|
| HTTP 5xx rate | 0.2% | Does not exceed baseline beyond an agreed deviation |
| p95 latency | 180 ms | Increases no more than 15% after normalizing traffic mix |
| p99 latency | 450 ms | Increases no more than 20% across sufficient requests |
| CPU utilization | 45% | No abnormal increase under identical traffic |
| Heap/GC pause | Stable | Does not breach memory/GC SLO |
| Payment failure | 0.1% | No increase relative to the control group |
| Queue lag | < 30 seconds | No sustained increase relative to baseline |

**The numbers above are examples only, not industry standards or preset SLOs for a system.** Real thresholds must reflect risk tolerance, seasonality, sample size, and business objectives.

### 10.1. Avoid comparing non-equivalent traffic

If the canary receives simple requests while the old version processes heavy ones, a lower p95 does not prove the change is better.

Compare across:

- Same endpoint types.
- Same region/tenant if applicable.
- Same time window or with a control cohort.
- Same data sizes and retry mix.
- Same authentication/TLS requirements.
- Sufficient sample size so conclusions are not drawn from a handful of requests.

### 10.2. Health checks alone are not enough

`/health` returning 200 may prove the process is alive, but does not prove business flows are correct. You also need readiness/liveness, downstream dependency health, event lag, and domain-level success metrics.

### 10.3. Setting hard stops and soft warnings

For example:

- **Hard stop:** data corruption, payment failures exceeding limit, broken authentication, or message duplication causing business impact.
- **Soft warning:** slightly higher GC or CPU over a short observation window, needing more samples.
- **Insufficient data:** hold at the current canary level; do not ramp up traffic just because no error has been seen yet.

## 11. Canary releases: increasing blast radius step by step

Canaries let you deploy a new version to a portion of the workload before expanding.

Example progression:

```text
0% (staging)
    |
    v
1% or one canary instance
    |
    v
5% traffic
    |
    v
20% traffic
    |
    v
50% traffic
    |
    v
100% traffic
```

Percentages and observation windows must be determined by the system based on request volume, risk, and error detectability. For a low-traffic worker, rolling out by consumer count or queue partition can be more meaningful than HTTP request percentages.

### 11.1. A good canary is representative

Select a group representative across:

- Endpoints and data.
- Authentication/tenants.
- Regions and dependencies.
- Peak and off-peak traffic.
- Retry, failure, and fallback paths.
- Rare batch jobs or message flows.

If a canary only exercises a low-importance endpoint, its result cannot be used to declare the entire application compatible.

### 11.2. Reversible traffic routing is required

When using a reverse proxy, gateway, or service mesh, there must be a way to shift traffic back to the old release. For queue workers, inspect offsets, consumer groups, partition assignments, and handling of in-flight tasks.

Canary rollback is not just “delete the new pod”; you must know whether in-progress requests/messages will finish, retry, or be rerouted.

### 11.3. Blue-green deployment

Blue-green keeps two production environments capable of running side by side:

```text
           Traffic router
             /       \
      Blue (old)    Green (new)
```

Only switch traffic to green after verification. On failure, you can switch back to blue **when data contracts and state remain compatible**.

Blue-green does not guarantee data rollback. If green has already run a migration dropping a column or writing a format blue cannot read, switching traffic back is still unsafe.

## 12. Feature flags to decouple deployment from activation

A feature flag can keep new code in the same artifact without applying it to every request right away.

Abstract example:

```java
public final class PricingService {
    private final FeatureFlags flags;
    private final LegacyPricing legacy;
    private final NewPricing modern;

    public PricingService(
            FeatureFlags flags,
            LegacyPricing legacy,
            NewPricing modern) {
        this.flags = flags;
        this.legacy = legacy;
        this.modern = modern;
    }

    public Price quote(Order order) {
        if (flags.enabled("pricing-v2", order.customerId())) {
            return modern.quote(order);
        }
        return legacy.quote(order);
    }
}
```

The types `FeatureFlags`, `LegacyPricing`, `NewPricing`, `Price`, and `Order` are illustrative application models. The idea is **selecting behavior at a controllable boundary**, not using a specific flag framework.

### 12.1. When are flags suitable?

- Two implementations can coexist in a single artifact release.
- Both implementations can operate on shared data.
- Selecting the code path does not violate business invariants.
- Outcomes of the new version can be measured separately.
- Disabling the flag is fast enough relative to incident detection time.

For instance, toggling two implementations of a pure computation algorithm is usually much simpler than toggling two data-write schemas.

### 12.2. What flags do not solve

A feature flag does not automatically roll back:

- Dropped database schemas.
- Library APIs removed from the artifact.
- Replaced runtime images where the old image is no longer present.
- Revoked certificates.
- Messages already published in an incompatible format.
- Side effects already executed against external systems.

Some changes require a **deployment rollback**, and some require **data recovery or compensating workflows**, rather than merely flipping a flag.

### 12.3. Setting an expiration date for flags

Migration flags are transitional tools and should not live indefinitely. After the new version is stable and the old path is retired, remove the legacy code/flag in a dedicated, verified step.

## 13. Shadow traffic and parallel comparison

To verify new code without letting it determine user outcomes, you can **run the new logic in parallel** as a shadow branch.

Example:

```text
Request
   |
   +--> Old implementation ---> Real response
   |
   +--> New implementation ---> Shadow result for comparison
```

This suits pure calculation algorithms, parsers, response formatting, or recommendation engines.

### 13.1. Do not blindly shadow side effects

Never duplicate order-placement, fund-transfer, email-sending, or data-writing requests into a shadow branch if it executes real side effects. Use a sandbox/test endpoint or isolate pure computation completely.

### 13.2. Compare by semantics, not necessarily byte-for-byte

Two JSON responses may differ in field order or timestamps while being logically identical. Canonicalize and ignore insignificant fields before flagging a mismatch.

### 13.3. Protect user data

Shadow payloads may contain personal information or secrets. They must comply with privacy, auditing, access control, and retention policies. Do not log raw request bodies just for migration comparison.

## 14. Database migration: the expand–migrate–contract principle

One of the hardest parts to roll back is a data schema change.

### 14.1. Dangerous pattern: changing schema simultaneously with code

Suppose the old application reads:

```sql
SELECT full_name FROM customer;
```

The new version wants to use `first_name` and `last_name`. If you deploy the migration:

```sql
ALTER TABLE customer DROP COLUMN full_name;
```

before all old instances stop using `full_name`, the old version can break immediately. If the new release must be rolled back, the old version can no longer run as before either.

### 14.2. Expand: add compatible schema

Start by only adding new columns:

```sql
ALTER TABLE customer ADD COLUMN first_name VARCHAR(100);
ALTER TABLE customer ADD COLUMN last_name VARCHAR(100);
```

The old schema still exists, so the old application can continue running. Note that schema changes can lock tables or impact performance depending on the database; evaluate real DDL impact.

### 14.3. Migrate: support both data representations

A transition phase can:

1. Backfill old data into the new columns.
2. Have new code read from the new columns, falling back to the old column if not yet populated.
3. Write both formats when compatibility must be maintained.
4. Track backfill progress and verify data consistency.
5. Update all consumers/workers before retiring the old column.

**Dual-write is not trivial**: if one transaction writes one side successfully and the other fails, data can drift. Use appropriate transactions, an outbox/event pattern, or a well-designed synchronization strategy rather than copying “write twice” into every method.

### 14.4. Contract: remove old schema after the rollback window closes

Only when all supported application versions have dropped their dependency on `full_name`, backfill is complete, and the rollback plan no longer needs the old version should you consider dropping the column:

```sql
ALTER TABLE customer DROP COLUMN full_name;
```

This must be **a separate gated step with backup/recovery**, never combined with enabling the new version.

### 14.5. Code rollback does not equate to schema rollback

With an expand-only schema, you can often roll back the application while **keeping the new columns**. Immediately trying to drop newly added columns may be unnecessary and increase risk.

Conversely, once data has been written in a format the old version cannot read, keeping the new columns may not be enough. Both read and write paths must be tested for two-way compatibility.

## 15. Event and message schemas when running two versions

In systems with Kafka, RabbitMQ, or other message brokers, canaries often mean old and new consumers coexist concurrently.

Example event version:

```json
{
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "orderId": "O-1001",
  "currency": "VND",
  "totalMinorUnits": 250000
}
```

If old consumers only understand version 1, having the new producer emit v2 can cause consumer rollback to fail. Design a compatibility window.

### 15.1. Suitable approaches

- Add optional fields that old consumers ignore.
- Keep wire schema v1 until all consumers can read v2.
- Use a schema registry and an appropriate compatibility policy.
- Publish parallel explicitly versioned topics/event types if transitioning.
- Place format conversion adapters/gateways at boundaries.
- Test deserialization across both versions.

### 15.2. Test rollback with real messages

Do not rely solely on contract tests with mocked JSON. In a test environment, have the new producer write messages and have the old consumer read them back. If the old consumer cannot handle them, the production rollback plan must constrain producer scope or redesign the format.

### 15.3. Idempotency and in-flight tasks

When switching consumers between versions, messages may be reprocessed. Migration steps must account for:

- At-least-once delivery.
- Deduplication keys or idempotency tokens.
- Retry policies and dead-letter queues.
- Offset commits and transaction semantics.
- Downstream side effects.

A rollback that increases duplicate processing can be more dangerous than the error that stopped the canary.

## 16. API backward/forward compatibility

During mixed-version rollouts, distinguish:

- **Backward compatibility:** the new component understands data/contracts produced by the old component.
- **Forward compatibility:** the old component can still process data/contracts produced by the new component, within the designed scope.

Exact definitions can vary by schema system/tooling, so specify **which producer, which consumer, and which version** when testing.

### 16.1. Two-way compatibility matrix

| Producer | Consumer | What to verify |
|---|---|---|
| Old | Old | Current baseline |
| Old | New | New version reads old data |
| New | New | New functionality |
| New | Old | Ability to roll back consumers or run mixed rollout |

The **New → Old** cell is often overlooked. It determines whether reverting to the old version after the new version has written data is safe.

### 16.2. Avoid breaking changes during runtime migration steps

When the goal is strictly upgrading the JDK runtime, keep API schemas, event schemas, and persistence formats unchanged. If changes are needed, split them into subsequent steps with separate contract tests and rollouts.

## 17. Migrating Java EE to Jakarta EE: a hard-to-roll-back case

Switching from `javax.servlet.*` to `jakarta.servlet.*` may require simultaneously upgrading frameworks, the Servlet container, and provider libraries. This is a type-contract change, not merely a source target change.

### 17.1. Splitting preparation steps

A possible roadmap:

1. Update tests and dependency inventory.
2. Upgrade to the latest framework version that still uses Javax and supports the target JDK, if appropriate.
3. Remove/replace unmaintained libraries.
4. Decouple business logic from Servlet/JPA boundaries.
5. Prepare an independent Jakarta deployment artifact.
6. Run contract tests over the same wire protocol.
7. Canary via a gateway or blue-green separate container environments.
8. Retire Javax container support only after the rollback window closes.

### 17.2. Do not drop a Javax WAR into a Jakarta container to canary

A Jakarta container does not automatically treat `javax.servlet.Filter` as `jakarta.servlet.Filter`. If both generations must run concurrently, use the matching environment/container for each artifact, or a proven migration/transformer solution.

### 17.3. Rollback may mean routing traffic back to the old environment

If the HTTP API and database schema are compatible, you can keep the blue environment on the Javax stack and the green environment on the Jakarta stack. However, verify session affinity, session serialization, authentication cookies, and in-flight requests.

Do not assume a stable HTTP contract means session state can be shared.

## 18. JDK security migration and rollback

Changing the JDK can also change accepted TLS algorithms/certificates, keystore behavior, security providers, and signature policies.

### 18.1. Security upgrades should not roll back by re-enabling weak algorithms

If the new JDK rejects TLS 1.0, overly short RSA keys, or non-compliant certificate chains, the right path is to upgrade the server/certificates/providers.

Reverting to an old JDK solely to keep an insecure protocol alive can violate security policies. If a temporary transition is needed, define an approved risk exception, isolation scope, and remediation deadline.

### 18.2. Certificate rotation also has an ordering

A server certificate change step must consider:

- Which clients trust the new CA/chain?
- If switching back to the old server, is the old certificate still valid?
- Has the old key been revoked/removed from the HSM?
- Is there an overlap period supporting both chains/certificates?
- Do mTLS client certificates need batched rotation?

If the old key has already been revoked, rollback cannot simply be “re-enable the old config”. Rollback must be designed under the new trust policy or via a suitable re-issuance plan.

## 19. Runtime images and artifacts must be reproducible

A rollback plan can fail if the system stores only branch names instead of the previously running artifacts.

Record:

- JAR/WAR versions and SHA-256 checksums.
- Container image digests, not merely mutable tags like `latest`.
- JDK vendor/full update/build.
- Build tool and dependency versions.
- Database migration version.
- Configuration/feature flag snapshot.
- Agent/native library versions.
- Approved deployment manifest or release artifact.

Example release metadata record:

```yaml
release: order-service-2026.11.12-01
applicationArtifact: order-service.jar
applicationSha256: "<calculated-sha256>"
runtime:
  javaVendor: "Example JDK Vendor"
  javaVersion: "17.0.x"
container:
  imageDigest: "sha256:<digest>"
databaseSchemaVersion: "V042"
featureFlags:
  newOrderParser: false
```

Values are placeholders. In real systems, exact digests/versions automatically recorded by CI should be used.

### 19.1. Rollback by immutable artifact

When failures occur, redeploy the **exact verified artifact/image digest**. Rebuilding from old source can yield different results due to dynamic dependencies, changed base image tags, or newer toolchains.

### 19.2. Separating release artifact and activation

You can deploy an artifact containing both old and new logic while only enabling the new feature for a canary after deployment stabilizes. This separates two questions:

1. Does the new artifact/runtime run stably?
2. Is the new logic correct and effective?

However, not every runtime change can be placed behind a feature flag; switching the JDK image requires an actual deployment strategy.

## 20. Rollback in Kubernetes or similar deployment platforms

Example of a command that may be used when deployment is managed by Kubernetes:

```bash
kubectl rollout status deployment/order-service -n production
```

If the previous revision is retained and compatible:

```bash
kubectl rollout undo deployment/order-service -n production
```

This command is an **example of deployment rollback**; it does not guarantee:

- Database reverting to the old schema.
- Already-published messages being recalled.
- Cache/session formats reverting.
- Old certificates being restored.
- In-flight requests causing no side effects.
- The old container image still existing in the registry.

Do not run production commands just because an example appears in documentation; follow your system's runbook, access permissions, and operational decision process.

### 20.1. For jobs and batch processing

Worker rollout differs from web services:

- Is a job currently processing a batch?
- Are there checkpoints or resume markers?
- Can work be safely replayed?
- Are there open transactions/locks?
- When are message acknowledgments committed?
- Can old and new consumers run concurrently?

During rollback, you may need to stop accepting new work, wait for or gracefully cancel running tasks, and only then switch the image.

### 20.2. For desktop Java clients

When upgrading a Java runtime bundled with a desktop installer, some clients may already be updated and others may be offline. Downgrades must check:

- Can the old version still read new file/config formats?
- Has a local database already been migrated?
- Does the updater support reinstalling an older version?
- Does the server API still serve old clients?
- Are installer signatures and the update/rollback workflow valid?

Desktop rollback usually requires a **multi-client-version support window**, not just changing a server-side deployment.

## 21. Roll-forward vs. rollback: choosing based on failure nature

Rollback is not always the best option.

| Situation | Path commonly considered |
|---|---|
| New-JDK canary shows clear regression, data contract unchanged | Roll back to old runtime image |
| Minor config mistake, no side effects yet | Disable flag/roll back config or quick fix-forward, based on risk |
| New DB schema already wrote data the old version cannot read | Avoid blind code rollback; restore compatibility or roll forward |
| Security error due to weak certificate | Prefer fixing the certificate/endpoint rather than lowering policy |
| Event v2 already widely published | Keep consumers able to read v2 or use an adapter; do not revert to unsupported old consumers |
| Slight CPU increase with insufficient samples | Hold canary and collect more data; do not rush expanding rollout |
| Wrong monetary amounts / authorization | Halt rollout immediately, contain impact, and follow incident response process |

A good **rollback plan** must be able to say “cannot safely auto-roll back past point X”. Past that point, a roll-forward or specialized recovery plan is required.

## 22. The point of no return concept

Some systems have a **point of no return**: once changes or written data cross a threshold, the old artifact is no longer compatible.

Example:

```text
T0: Add new column (old still runs)
T1: New code reads both formats
T2: Backfill and support compatible writes
T3: All clients/consumers upgraded
T4: Stop writing old format
T5: Drop old column (old cannot run)
```

From T0 until before T5, rolling back the application can remain relatively safe if contracts are preserved. From T5 onward, merely redeploying old code is no longer sufficient.

### 22.1. Rules before crossing this point

- Confirm all old consumers have stopped.
- Have a tested backup and restore procedure.
- Have post-migration reconciliation data.
- Have formal approval for the contract phase.
- Have a plan for offline clients or pending batches.
- Communicate clear compatibility details in release notes.

Explicitly recording the point of no return prevents the team from promising a “5-minute rollback” when reality requires hours of database restoration.

## 23. Observability: prerequisite for deciding whether to expand rollout

Changing the JDK can alter GC behavior, logging, TLS, thread scheduling, and JNI/native calls. Without metrics, a canary only creates an illusion of safety.

### 23.1. Technical metrics

- Startup time, readiness failures, crashes/restarts.
- CPU, memory, heap allocation, and GC pauses.
- Thread states, and virtual threads if used.
- p50/p95/p99 latency per endpoint.
- Error rate by exception type.
- Database pool utilization, waiters, and timeouts.
- Queue lag, dead-letter messages, and retries.
- Outbound HTTP/TLS failures.
- Logging/tracing agent health.
- Container throttling and OOM kills.

### 23.2. Business metrics

- Payment success rate.
- Orders recorded/completed.
- Authorization failure rate.
- Number of duplicate-processed events.
- Inventory sync lag.
- Discrepancies in monetary totals or reconciliation data.

An application with lower CPU and more HTTP 200 responses that still writes wrong orders must be rolled back or fixed.

### 23.3. Cohort-separable logs

Logs should include release version, deployment group, correlation ID, and relevant dependency/service identifiers. Do not log tokens, private keys, or sensitive data for debugging convenience.

For canaries, clearly distinguish logs/metrics between old and new releases so data is not conflated.

### 23.4. Controlled JFR and profiling

Java Flight Recorder and appropriate profilers can help investigate changes in allocation, CPU, blocking, or GC. However, these are supplementary observability tools, not replacements for SLOs and functional correctness.

## 24. Comprehensive scenario: upgrading Order Service from Java 11 to Java 17

Suppose Order Service has:

```text
Java 11
Spring-based application
PostgreSQL via JDBC pool
HTTP call to Payment Gateway
Kafka order-events.v1
Container deployment
```

The goal is running on the JDK 17 runtime without changing frameworks or message schemas yet.

### Step 0 — Baseline

- Pin the currently running Java 11 image by digest.
- Record startup/health, p95/p99 latency, error rate, DB waiters, Kafka lag.
- Run current regression/contract tests.
- Record JDK vendor/update, dependency graph, and agent versions.

### Step 1 — Prepare JDK 17 CI

Keep production on Java 11. Run unit/integration tests with the JDK 17 runtime. Uncover issues such as blocked reflection, certificate constraints, or incompatible dependencies.

**Rollback:** no production change. If tests fail, stop at this step and fix in development.

### Step 2 — Upgrade incompatible dependencies

For example, if an old bytecode agent does not support new class files/JDKs, upgrade the agent in a separate commit/release. Keep Java 11 runtime in production if the new agent version still supports it, or verify only in CI if it does not.

**Evidence:** instrumentation still produces traces, tests pass, and overhead stays within limits.

### Step 3 — Build the JDK 17 runtime image

Use the same verified source and dependencies. Check startup, keystore, truststore, resource paths, native libraries, and JVM flags.

**Rollback:** keep the Java 11 image and matching config.

### Step 4 — Canary a subset of instances

Route a fraction of traffic to the new image without altering event schemas or DB schemas.

**Observe:** request success, payment errors, timeouts, GC, CPU, latency, Kafka lag, and business metrics.

### Step 5 — Gated rollout expansion

Only advance to 20%, 50%, 100% when sufficient data exists and stop conditions are not breached. Percentages are illustrative; real schedules depend on load.

### Step 6 — Keep a rollback window

Retain the old image, manifests, and ability to shift traffic back for an agreed period. Watch for delayed effects such as batch jobs, certificate renewals, and scheduled tasks.

### Step 7 — Clean up legacy configuration

Once stable, remove obsolete JVM flags, update runbooks, and delete unneeded workarounds. Only then start independent steps to upgrade frameworks or migrate to Jakarta if on the roadmap.

**Strength of this roadmap:** when a failure occurs at Step 4, investigation can focus mainly on the JDK runtime and deployment environment rather than dozens of simultaneous framework and data changes.

## 25. Comprehensive scenario: switching from a thread pool to virtual threads

Changing the execution model alters concurrency behavior, so rollback capability requires special attention.

Previous code example:

```java
ExecutorService executor =
        Executors.newFixedThreadPool(64);
```

JDK 21 candidate:

```java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
```

This is not just swapping executor types: a fixed pool may have been implicitly bounding concurrent database or HTTP calls. Virtual threads can allow thousands of tasks to hit resources simultaneously.

### 25.1. Reasonable step breakdown

1. Measure baseline active workers, queue depth, DB pool waiters, and p99 latency.
2. Add semaphores/rate limiters for scarce downstream resources.
3. Write timeout/cancellation tests and load/overload tests.
4. Enable the virtual thread executor for one I/O-bound endpoint via config/flag if possible.
5. Observe pinning/ThreadLocal/context propagation on the actual JDK.
6. Canary and compare under an equivalent traffic mix.
7. If regression occurs, switch the endpoint back to the old executor without touching the database schema.

### 25.2. Rollback limitations

If during testing tasks write data in a different format or create duplicate side effects, turning off the new executor cannot undo those changes. Therefore the executor swap step should **keep the data contract and idempotency logic unchanged**.

## 26. Comprehensive scenario: migrating Javax to Jakarta across two environments

Suppose the old application:

```text
Java 11 + Javax Servlet container
   |
   v
Orders API v1
   |
   v
Current database schema
```

New version:

```text
Java 17 + Jakarta Servlet container
   |
   v
Orders API v1 (preserve wire contract)
   |
   v
Compatible database schema
```

### 26.1. A small step does not mean converting a single servlet

Inside a single container, `javax.servlet.Filter` is not equivalent to `jakarta.servlet.Filter`. Some type boundaries must move together. Thus the **minimum viable unit** may be an entire WAR/service with a unified Servlet contract, rather than an individual class.

### 26.2. Using container-level blue-green

Keep the old Javax application on Blue and the Jakarta application on Green. Route traffic through a gateway while both expose the same HTTP API.

Test sessions/auth/cookies and other integrations. If sessions are serialized using Java classes across different packages, state may not be shareable; use a suitable session migration or affinity strategy.

### 26.3. Defer database schema changes

To make rollback easy, keep the data contract consistent during the container switch step. Major DB changes belong in prior/subsequent expand-contract steps with clear compatibility windows.

## 27. Mistakes that stop steps from being small

### 27.1. Bundling upgrades “while we are at it”

A developer upgrades the JDK and casually bumps frameworks, database drivers, JSON serializers, and logging libraries at the same time. Each component brings its own behavioral changes, multiplying the hypotheses to check.

How to mitigate: explicitly document the scope of every pull request/release and justify why any dependencies must move together.

### 27.2. Using only “build passes” as the gate

Compile time does not prove runtime compatibility, classloaders, TLS, DB transactions, message schemas, or performance. Targeted verification is required.

### 27.3. Not keeping the old artifact

The container tag was overwritten or the old image deleted from the registry. As a result, deployment rollback cannot run immediately when needed.

Store immutable artifacts/digests and verify access rights before rollout.

### 27.4. Having an untested runbook

A single line saying “run rollout undo” is not enough if the data schema changed. Rehearse rollback in staging or an environment with representative data/traffic characteristics.

### 27.5. Calling a breaking database change “minor”

Adding a nullable column can be additive. Dropping a column, renaming directly, or changing enum semantics can break the old version. Impact scope matters more than the size of the migration script.

### 27.6. Non-representative canary

The canary only receives light requests and never triggers payment or batch paths. Its results cannot validate untested flows.

### 27.7. Stopping monitoring too early

Some bugs surface only when daily/weekly scheduled jobs run, TLS certificates renew, or accounting period-end arrives. Match the observation window to business cycles.

### 27.8. Confusing platform errors with business outages

During a canary, a downstream service suffers an outage affecting both old and new cohorts. Looking solely at the new release's error rate can trigger a false rollback. Compare against the control cohort and isolate the cause.

### 27.9. Adding flags without knowing who turns them off

A flag lacking an owner, audit trail, or runbook diminishes rollback value. Define control permissions and trigger conditions clearly.

### 27.10. Removing support for the old version before the rollback window ends

Deleting old dependencies, schemas, or APIs too early turns rollback from a deployment action into a data recovery project. The contract phase must be a separate final step.

## 28. Pre-approval checklist for a migration step

### Before starting

- [ ] One primary goal and a testable hypothesis are defined.
- [ ] All changing variables are listed accurately.
- [ ] Service/module/traffic cohort scope is identified.
- [ ] Related API, event, database, and file-format contracts are checked.
- [ ] Classified whether the step is reversible, conditionally reversible, or irreversible.
- [ ] Baseline metrics and appropriate tests are ready.
- [ ] Specific JDK/toolchain/framework/container versions are recorded.
- [ ] Pre-change artifact/image digest and config are saved.
- [ ] Pass, stop, and rollback criteria are defined.
- [ ] Owner, approver, and decision checkpoint are assigned.

### Before expanding rollout

- [ ] Unit/integration/contract tests ran on the exact target runtime.
- [ ] Both happy paths and negative paths were checked.
- [ ] Data schema is compatible with old/new within the rollback window.
- [ ] Canary receives sufficiently representative traffic.
- [ ] Control cohort and baseline were compared.
- [ ] No critical security issues or data loss occurred.
- [ ] Latency, throughput, GC, CPU, and downstream saturation are within thresholds.
- [ ] Ability to pause new work intake and handle in-flight tasks exists.
- [ ] Rollback path has been rehearsed or has feasibility evidence.

### Before closing the rollback window

- [ ] Sufficient observation time elapsed for batch/cron and rare flows.
- [ ] Old/new producer-consumer compatibility is confirmed.
- [ ] No offline clients/old workers remain needing to read new data, or support is in place.
- [ ] Backup/recovery plan is verified.
- [ ] No remaining rollback dependency on schemas/artifacts slated for deletion.
- [ ] Release outcome, metrics, and canary lessons are recorded.
- [ ] Separate tickets exist for the contract phase and flag removal.
- [ ] Runbooks, owners, and monitoring are updated accordingly.

## 29. Template for a step outcome report

A concise report should let operations decide whether to proceed or stop:

```text
STEP:
  order-worker-runtime-jdk17

CHANGE:
  Runtime JDK 11 -> 17
  Source/dependencies/message schema: unchanged

SCOPE:
  5% worker workload, one region

EVIDENCE:
  Contract tests: passed
  Integration tests: passed
  Processing success: stable vs control
  Queue lag: within SLO
  p95 latency: within pre-agreed limit
  TLS/DB failures: no regression detected

ROLLBACK READINESS:
  Old image digest: retained
  Message format old/new compatible: checked
  In-flight processing runbook: available
  Rollback rehearsal: completed in staging

DECISION:
  Proceed to next canary level, or hold/rollback based on gates

OWNER:
  Assigned migration owner and on-call team
```

This is an illustrative template, not measured results from a specific system. Every “passed”, “stable”, or “completed” conclusion in a real report must rest on matching evidence.

## 30. Principles for picking the next step

After each successful step, ask:

1. Which risk was just eliminated?
2. What remains unknown?
3. Can the next step keep what was just verified unchanged?
4. If the next step fails, can we return to the current state?
5. Have we crossed a point of no return?
6. Is more observation or testing needed before widening scope?
7. Must a dependency/framework change together, or is it merely convenient for deployment?
8. Has the rollback procedure been tested with matching artifacts and data?

A sensible order usually prioritizes steps that **build failure detection** (tests, metrics, reproducible builds), followed by steps that **reduce legacy coupling** (dependency updates, adapter boundaries), and finally steps with major runtime, framework, and data-contract changes.

No single fixed sequence fits every organization. Urgent security requirements or end-of-support deadlines may force prioritizing a riskier change; when that happens, bounding scope and setting clear stop conditions becomes even more critical.

## 31. Conclusion

A successful Java upgrade is not necessarily the one with the largest changes; it is a sequence of changes where **each step solves one problem, produces new evidence, and preserves decision-making control for the next step**. To achieve this, separate the different dimensions of migration—JDK build/compiler/runtime, dependencies, containers, JPMS, Jakarta, execution models, and data—into clearly bounded deployment units.

Before each step, write down the hypothesis and verification criteria, retain the old artifact, define the blast radius, and prepare a realistic rollback. For DBs, events, and persisted data, design backward/forward compatibility with an expand–migrate–contract window; **do not promise a code rollback once the old version can no longer read new data**. For rollouts, combine automated tests, canary/blue-green strategies, observability, and stop conditions.

The core principle of migration strategy is: **change the fewest variables necessary, measure what matters, bound damage when wrong, and always know how to return to a safe operational state**. When every step is verifiable and reversible within its stated scope, upgrading the JDK becomes a controlled engineering process rather than an unpredictable “big bang”.
