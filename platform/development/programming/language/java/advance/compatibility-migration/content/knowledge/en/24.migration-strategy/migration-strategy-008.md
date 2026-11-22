# Separating Compatibility Fixes from Adopting New Syntax or APIs

When upgrading a Java application from an older JDK to a newer JDK, development teams often face two appealing yet distinct goals:

1. **Make the existing system run properly on the target JDK**: resolving build failures, removed APIs, incompatible libraries, module encapsulation, runtime changes, packaging, and operational configuration.
2. **Leverage new Java capabilities**: using `record`, switch expressions, pattern matching, text blocks, collection factory methods, new `java.time`/`java.nio.file` APIs, virtual threads, or refactoring code into a modern style.

The first goal is **compatibility migration**; the second goal is **modernization**. Both can be delivered within the same upgrade program, yet they should be managed as **two separate change streams** whenever technical constraints allow.

Why? If you fix compatibility bugs, restructure domain objects, change the concurrency model, and rewrite parsers all at once, when business behavior shifts the team struggles to tell whether the new JDK or the new refactor caused it. Rollbacks also become harder: reverting to the old behavior may force reverting essential compatibility patches as well.

This lesson builds a practical approach to **upgrade the JDK first without intentionally changing business behavior**, establish evidence that the system is compatible, and then modernize Java syntax/APIs in separate waves that can be tested and rolled back independently.

## 1. Distinguishing three kinds of changes in a Java migration

Not every change appearing in a Java upgrade pull request belongs to the same category.

| Category | Purpose | Examples | Acceptance criteria |
|---|---|---|---|
| Mandatory compatibility fix | Restore build or legacy behavior on the target JDK | Replace removed APIs, upgrade drivers or JVM flags | Business outcomes remain unchanged aside from approved bug fixes |
| Mandatory security/correctness fix | Meet operational policies on the new JDK | Replace weak TLS algorithms, fix unsafe deserialization | Explicit requirement, review, and impact testing |
| Optional modernization | Improve readability, maintainability, or adopt new APIs | Convert DTOs to records, use switch expressions, virtual threads | Evaluated as an independent change with proven benefits and regression tests |

A PR may include a few mandatory dependency updates so the build runs on the new JDK. That does not turn the entire change into "modernization". Conversely, converting a traditional loop into a stream is not a compatibility patch merely because the project happens to be upgrading Java.

### 1.1. Compatibility does not mean keeping every bytecode instruction identical

Compatibility aims to **preserve critical contracts**, not demand identical source or binary output:

- Public API/CLI behavior.
- Business outcomes for the same inputs.
- Database schemas and persisted data contracts.
- HTTP/event/message formats consumed by existing clients.
- Security guarantees and access permissions.
- Performance within acceptable thresholds.
- Deployment, observability, and recovery mechanisms.

When a newer JDK changes security policies, adjusting algorithms or trust configuration may be required. That remains necessary migration work, yet the changed behavior and its approver must be documented clearly.

### 1.2. Modernization is not proof of compatibility

Rewriting a class into a `record` may make it shorter, yet the system can still fail with an old JDBC driver or a Java agent that does not understand the class-file version. Using new APIs does not prove the runtime is compatible. Each goal requires separate verification.

## 2. The two-track change strategy

A clear illustration:

~~~text
Baseline running on old JDK
                |
                v
     Compatibility workstream
     - Build tool / dependency
     - Removed APIs / reflection
     - Runtime flags / security
     - Data / protocol compatibility
                |
                v
 System with same behavior on new JDK
                |
                | New baseline backed by evidence
                v
      Modernization workstream
     - New syntax / language features
     - New standard-library APIs
     - Refactor code structure
     - New concurrency / architecture
                |
                v
   Intentionally modernized system
~~~

Whenever feasible, each arrow represents a change that can be released, compared, and rolled back independently.

### 2.1. The "whenever feasible" condition

Absolute separation is not always possible. For example:

- The target framework requires a newer minimum JDK, forcing framework and JDK upgrades together.
- A removed API forces switching to an external library.
- A library incompatible with the target JDK only supports the new JDK in a version with changed APIs.
- Security policy mandates disabling weak protocols/algorithms immediately during the upgrade.
- Deployment infrastructure cannot operate two JDK versions side by side.

In such cases, explicitly record **mandatory supporting changes**, lock down boundaries, and test thoroughly. "Separation" is a principle for reducing variables, not a rule forbidding all coupling.

## 3. Setting a concrete migration target

An insufficiently specific goal:

~~~text
Upgrade Java 8 to latest Java.
~~~

A better goal:

~~~text
Phase A: Run the current application version on JDK 21.
- Do not change public REST endpoints.
- Do not change JSON/message schemas.
- Do not change database schemas unless mandatory.
- Fix compile/runtime errors caused by JDK or dependencies.
- Run regression and production-like integration tests.
- Ability to roll back runtime/artifact by design.

Phase B: Modernize selected modules.
- Separate proposal for records/switch/new APIs.
- Measure impact and test per module.
- Do not bundle unapproved architecture changes.
~~~

Version numbers in examples are illustrative; actual JDK/framework combinations must be checked against support matrices. Do not assume every legacy framework runs directly on JDK 21.

## 4. Locking in a baseline before editing code

Without a baseline, teams struggle to know whether a failure is newly introduced or pre-existing.

At minimum, record:

| Scope | Baseline evidence |
|---|---|
| Source | Running commit/tag, release branch |
| Build | Maven/Gradle Wrapper, plugins, dependency graph |
| JDK | Vendor, release, update, runtime image |
| Framework | Version, BOM, key extensions |
| Compilation | Source target, `--release` or `source/target` |
| API | HTTP, CLI, event, file, serialization contracts |
| Database | Schemas, migrations, representative historical data |
| Operations | JVM flags, GC, memory limits, TLS, agents |
| Tests | Regression, integration, contract, security, performance |
| Metrics | Error rate, p95/p99 latency, CPU, heap, startup, throughput |
| Rollback | Artifacts, configuration, data compatibility |

If the baseline already has failing tests, document them explicitly rather than attributing them to the new JDK later.

### 4.1. Characterization tests

For poorly tested legacy code, before refactoring you can add **characterization tests**: feed representative inputs into existing code and assert the currently observed outputs/behaviors. Not every legacy behavior is desirable; mark known bugs clearly so they are not inadvertently legitimized.

Example with a receipt formatter:

~~~java
public final class ReceiptFormatter {
    public String format(long amount, String currency) {
        return amount + " " + currency;
    }
}
~~~

Test:

~~~java
@Test
void existingReceiptFormatIsStable() {
    ReceiptFormatter formatter = new ReceiptFormatter();
    assertEquals("125000 VND", formatter.format(125000L, "VND"));
}
~~~

During the compatibility phase, the goal is keeping this test green as the runtime/SDK changes. Later, if you want to migrate currency handling to `BigDecimal` or localization APIs, treat that as a separately reviewed business/correctness change.

## 5. Matrix of JDK, framework, and bytecode target

At least four axes must be distinguished:

1. The JDK running Maven/Gradle.
2. The JDK used as the compiler/toolchain.
3. The artifact's Java source/API/bytecode baseline.
4. The JDK actually running the application in production.

Example:

~~~text
Build tool: Gradle using JDK 21
Compiler toolchain: JDK 21
Compile release target: Java 17
Production runtime: JDK 17 or 21 per tested matrix
~~~

Configuring `--release 17` constrains source language level, Java SE APIs visible to the compiler, and class-file target. It does **not guarantee that all third-party dependencies** run on Java 17, nor does it install a Java 17 runtime.

### 5.1. Distinguishing runtime switch from raising minimum supported Java

If the goal is solely running production on JDK 21, you can keep `--release 17` or an older release baseline if supported by the compiler. If the project decides to adopt `record` or an API added only in a newer Java release, that is a decision to **raise the minimum language/API baseline**; it must account for any consumers still running older JDKs.

Do not silently raise the bytecode target simply because CI installed a newer JDK.

### 5.2. Framework matrix

Evaluation:

| Combination | Feasible? | Must verify |
|---|---|---|
| Old framework + old JDK | Baseline | Currently operating |
| Old framework + new JDK | Only if supported | Good for isolating JDK impact |
| New framework + old JDK | Only if supported | Good for isolating framework impact |
| New framework + new JDK | Target state | Full test coverage |

If neither intermediate point is supported, introduce a bridge release (framework patch/minor or intermediate JDK) or a coordinated upgrade plan. Never run a "vendor-unsupported" combination in production merely to preserve the appearance of a two-step move.

## 6. Fixing compilation errors is compatibility work

A JDK upgrade may uncover code using removed APIs, APIs present only in older environments, or broken imports after dependency shifts.

Example of a legacy application using JAXB:

~~~java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Unmarshaller;
~~~

In older JDKs, related Java EE components were once distributed with the JDK. Starting in JDK 11, many modules such as JAXB are no longer part of the JDK distribution. Code may fail with missing package errors even though XML business logic did not change.

Compatibility approach:

1. Check the exact dependency/API the application currently uses.
2. Add the appropriate API and implementation via Maven/Gradle within a supported ecosystem.
3. Keep XML schemas, data, and serialization behavior stable.
4. Run unmarshalling/marshalling tests using legacy XML fixtures.
5. Separate any plan to move to Jakarta-generation APIs/packages (if needed) from simply resolving removed modules, unless the dependency set forces combining them.

Do not use missing JAXB as an excuse to rewrite the entire XML protocol to JSON in the same compatibility PR. That is a **data contract change** with its own consumers and rollback path.

### 6.1. JDK internal APIs

Code or dependencies may have used internal packages like `sun.*` or reflected into JDK modules. On newer JDKs, this can raise:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
~~~

Preferred resolution order:

- Find a JDK-supported public replacement API.
- Upgrade the library/agent to a version compatible with the target runtime.
- Refactor custom code performing unnecessary reflection.
- Use `--add-opens` or `--add-exports` only as a scoped transitional measure with a removal plan.

Example `--add-opens`:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

This is a syntax example, **not a recommendation to enable by default**. It does not restore removed classes, does not fix binary incompatibility, and can unintentionally weaken encapsulation.

## 7. Dependency upgrades: upgrade only as much as needed for compatibility

When a new JDK breaks a library—for example, an outdated ASM/Byte Buddy/Mockito/annotation processor/Java agent fails on the new class-file version—find a vendor-supported version.

However, upgrading the entire framework alongside dozens of unrelated dependencies in the same commit raises risk.

### 7.1. How to manage it

- Lock in the baseline dependency graph.
- Identify which artifact actually causes the error based on stack traces and resolved versions.
- Choose the minimum version satisfying support/security policy, not necessarily the very latest.
- Consult the dependency's migration guide if breaking changes exist.
- Avoid changing application-facing APIs unless necessary.
- Diff the resolved graph after the change.
- Run tests for subsystems using that dependency.
- Separate major framework upgrades when an independent support path exists.

### 7.2. When a mandatory dependency brings API changes

If a library only supports the new JDK in a release whose public API changed, updating call sites is **mandatory** compatibility work, yet you must clearly explain why. A compatibility PR need not consist exclusively of one-line edits; what matters is **not mixing optional refactoring** into the code being updated.

## 8. Maven example: keeping the release target explicit

In `pom.xml`, you can configure the appropriate Maven Compiler Plugin settings:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Or declare explicitly in the plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>VERSION_DA_XAC_MINH</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

`VERSION_DA_XAC_MINH` is a placeholder; choose an actual plugin version compatible with your Maven/JDK.

In the compatibility phase:

~~~bash
./mvnw --version
./mvnw -B clean verify
./mvnw dependency:tree
~~~

Verify the Maven runtime JVM, compiler release, and dependency tree. Upgrade Maven Wrapper/Compiler Plugin if they do not support the build JDK, yet do not convert all business sources to new Java syntax just because the compiler was upgraded.

## 9. Gradle example: separating toolchain and source target

With Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Meanings:

- The wrapper selects the Gradle distribution.
- The JVM running the Gradle daemon has its own compatibility requirements.
- The Java toolchain selects the JDK used for `JavaCompile` and related tasks.
- `options.release` controls the artifact baseline.
- Test tasks may have a separate `JavaLauncher`/toolchain or JVM runtime that must be verified.

Inspection:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
~~~

These commands are examples for learners in the lesson; they are not an instruction for a worker to run a build at STEP 4.

## 10. Fixing compatibility while preserving behavior: an example

A legacy service loads configuration from a resource:

~~~java
package com.acme.app;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ConfigLoader {

    public Properties load() throws IOException {
        Properties config = new Properties();

        try (InputStream input =
                     ConfigLoader.class.getResourceAsStream(
                             "/application.properties")) {
            if (input == null) {
                throw new IOException("Missing application.properties");
            }
            config.load(input);
        }

        return config;
    }
}
~~~

Suppose after changing packaging/JDK, the launcher uses the wrong classpath or omits the resource from the JAR. **The proper compatibility patch** may be fixing the build resource configuration or startup script so the resource is present, without rewriting `ConfigLoader` with new APIs.

An optional modernization refactor might switch to `Files.readString` and an external configuration path; however, that can change:

- Configuration source: classpath resource → filesystem.
- Charset and `Properties` parsing rules.
- Working directory assumptions.
- Error behavior and exception messages.
- Security/permission model.

Therefore, "shorter code" is not proof of equivalent behavior.

## 11. Newer Java adds new APIs: that does not mean adopting them immediately

For example, `Files.readString` (Java 11+) simplifies reading text:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

In Java 8, the corresponding code could be:

~~~java
String text = new String(
        Files.readAllBytes(path),
        StandardCharsets.UTF_8);
~~~

If a project merely needs to run on JDK 21 while a shared library still maintains a Java 8 source/API baseline, **you cannot replace it with `Files.readString`** and still expect the library to run on Java 8. API availability is a runtime contract, not purely a syntax preference.

Additionally, when reading large files or needing streaming, both whole-file memory-reading approaches have trade-offs. Adopting a new API must come with semantic/performance review rather than automatically replacing every call site.

### 11.1. List.of and Arrays.asList differ

Java 9 introduced collection factory methods:

~~~java
List<String> roles = List.of("USER", "ADMIN");
~~~

Older code may use:

~~~java
List<String> roles = Arrays.asList("USER", "ADMIN");
~~~

They are not strictly equivalent:

- `List.of` creates an unmodifiable list rejecting structural/element mutations via mutator operations and disallowing `null` elements.
- `Arrays.asList` creates a fixed-size list backed by an array; elements can be modified via `set`, though elements cannot be added/removed.
- The two APIs differ in exceptions thrown and array-aliasing behavior if the backing array is shared.

A find-and-replace refactor `Arrays.asList` → `List.of` can break logic even if immediate test outputs look identical. Treat this as a **modernization change requiring semantic review**, not a mandatory step to support a new JDK.

## 12. Record: less boilerplate, yet a different contract

Java `record` fits certain data carriers with clear component state and value-like semantics. Example of a legacy DTO class:

~~~java
public final class UserView {
    private final String id;
    private final String displayName;

    public UserView(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

It can be modernized to a record on a supporting Java release:

~~~java
public record UserView(String id, String displayName) {
}
~~~

However, it is **not an equivalent drop-in refactor across every framework**:

| Characteristic | Legacy DTO class | Record |
|---|---|---|
| Example accessor methods | `getId()`, `getDisplayName()` | `id()`, `displayName()` |
| Constructor | Arbitrary developer-defined constructors | Canonical constructor matching components |
| Inheritance | Flexible per class design | Records cannot extend user-defined classes |
| Mutability | Depends on implementation | Components are final references; deep immutability is not guaranteed |
| equals/hashCode/toString | Written by developer/IDE/Lombok | Auto-generated semantics |
| Serialization/binding | Depends on framework | Must check framework record support |
| Java language baseline | Can target Java 8 | Requires a Java release with records |

Impacts can include JSON serialization, validation, reflection, ORM, constructors, and consumer binary APIs. If a public library is consumed by Java 8 clients, converting `UserView` to a record is far more than "cleanup".

**Recommendation:** once the compatibility phase is stable, try records on new DTOs or internal modules first; use contract tests to confirm JSON and API behavior.

## 13. Switch expressions and pattern matching: new syntax also changes semantics

A legacy enum mapper:

~~~java
public String label(OrderStatus status) {
    switch (status) {
        case CREATED:
            return "Created";
        case PAID:
            return "Paid";
        case CANCELLED:
            return "Cancelled";
        default:
            throw new IllegalArgumentException("Unknown status");
    }
}
~~~

With a Java release supporting switch expressions:

~~~java
public String label(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
    };
}
~~~

This can be a useful refactor, yet requires evaluating:

- New enum values added in future releases.
- `null` handling.
- Default/fallback behavior.
- Bytecode/source baseline.
- Branches with side effects or fallthrough in the old switch.
- Public callers relying on different assumptions about the result.

Similarly, replacing traditional casts:

~~~java
if (value instanceof String) {
    String name = (String) value;
    process(name);
}
~~~

with pattern matching:

~~~java
if (value instanceof String name) {
    process(name);
}
~~~

is often cleaner to read, yet **is unnecessary for running on JDK 21**. Readability benefits should not justify modifying thousands of files in a PR meant solely to upgrade the runtime.

## 14. Text blocks and preserving output strings

Java text blocks make SQL/JSON easier to read:

~~~java
String query = """
    select o
    from OrderEntity o
    where o.status = :status
    """;
~~~

However, converting manual string concatenation into a text block can change whitespace, trailing newlines, indentation, or escape processing. For SQL this may rarely matter, whereas for digitally signed payloads, templates, regexes, formatted queries, or golden fixtures, every byte can count.

When modernizing:

- Compare output strings whenever contracts depend on byte-level representation.
- Inspect escape sequences and line endings.
- Verify compiler source release.
- Avoid changing SQL semantics at the same time as changing syntax.
- Keep migrations free of unapproved external API contract changes.

## 15. Virtual threads are concurrency modernization, not a "fix to run"

Java 21 provides virtual threads as a core feature. An application using traditional thread pools may consider this model, yet **upgrading to JDK 21 does not require switching every executor to virtual threads**.

Traditional code:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(32);
try {
    Future<String> result = pool.submit(() -> fetchDocument());
    System.out.println(result.get());
} finally {
    pool.shutdown();
}
~~~

One way to use the Java 21 virtual-thread executor API:

~~~java
try (ExecutorService pool =
             Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = pool.submit(() -> fetchDocument());
    System.out.println(result.get());
}
~~~

This can impact:

- Concurrency bounding and backpressure models.
- Database connection pools, which still hold a finite number of connections.
- Blocking I/O behavior and thread pinning in certain cases.
- `ThreadLocal` state and request context propagation.
- Monitoring, tracing, and thread-dump assumptions.
- Downstream rate limits.
- Memory/throughput/latency under load.

Do not assume virtual threads are always faster or fix every performance issue. Run an isolated pilot with load testing and operational monitoring after the JDK migration has stabilized.

## 16. Improving code does not equal fixing runtime bugs

An anti-pattern is seeing an error on a new JDK and rewriting subsystem architecture:

~~~text
Root error:
  Old Java agent does not recognize new class-file version.

Out-of-scope proposed changes:
  Convert controllers to reactive,
  replace DTOs with records,
  rewrite thread pools,
  change JSON format.

Focused change:
  Upgrade the Java agent to a version supporting the target JDK,
  preserve application behavior,
  test agent + startup + integration.
~~~

A localized failure can legitimately motivate adopting a new API when no compatible alternative exists, yet that **causal link** must be explained. The rule is to fix enough to meet the goal, not turn an upgrade into a "clean up everything at once" effort.

## 17. Major framework upgrades are a separate workstream

A major framework upgrade typically introduces breaking changes independent of the JDK:

- `javax.*` ↔ `jakarta.*` namespace.
- Annotation and dependency injection changes.
- HTTP request mapping, security defaults, CORS/CSRF.
- Persistence/Hibernate ORM behavior.
- JSON serialization and validation defaults.
- Logging/metrics/health endpoints.
- Message consumers, cache/session serializers.
- Build plugins and dependency BOMs.

In many ecosystems, a newer major framework requires a higher Java baseline, making complete separation impossible. Even then, separate clearly in the plan: **which changes enable the JDK to run, and which changes stem from the new framework contract**.

### 17.1. Example: javax to jakarta

Legacy code:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
~~~

With a provider using Jakarta Persistence:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
~~~

This is a persistence/framework ecosystem API namespace migration. It **does not happen automatically merely from installing JDK 17/21**. If the JVM migration can run on an older supported framework version, avoid migrating packages at the same time.

If the target framework mandates the Jakarta namespace with no intermediate release, split internal commits/test groups to isolate impact across build/runtime, persistence APIs, ORM mapping, and schema/data compatibility.

## 18. Do not change database or message schemas in the compatibility phase unless mandatory

A JDK deployment can coincide with times when a team wants to change:

- Database column types or timezone representations.
- Persisted enum values.
- Session serialization formats.
- Cache key namespaces.
- Kafka/AMQP event schemas.
- HTTP JSON response field names.
- JWT claims/cookie formats.

These are contracts between old and new versions. They often outlive the process that produced them.

Example:

~~~text
App v1 / old JDK  -- writes event schema v1 --> Broker
App v2 / new JDK -- reads event schema v1 --> Broker
~~~

During compatibility migration, prioritize keeping existing event schemas, verify the new app reads legacy payloads, and change serializers only when a required library forces it or a designed migration exists.

If schemas must change:

1. Define schema versions.
2. Upgrade readers before writers when mixed-version deployments are required.
3. Test W1→R2 and W2→R1 whenever rollback requires it.
4. Manage retention, retries, and DLQs.
5. Document the exact point of no rollback.
6. Separate data contract rollouts from runtime switches where feasible.

Never wipe caches/sessions/durable messages indiscriminately just to stop deserialization errors in the new application.

## 19. Establish a "behavior-preserving" principle for compatibility PRs

A compatibility PR should have a concise yet verifiable description:

~~~text
Goal:
  Run the existing application on JDK Y.

Required changes:
  - Update Maven/Gradle toolchain to support JDK Y.
  - Replace removed JDK dependencies.
  - Upgrade incompatible bytecode library and Java agent.
  - Adjust JVM flags that no longer apply.

Not in scope:
  - New REST endpoints.
  - Database schema redesign.
  - Rewrite DTOs as records.
  - Replace thread pools with virtual threads.
  - Change JSON/event schema.
  - Major logging/framework refactor.

Expected behavior:
  Existing contracts remain stable.

Validation:
  Build, regression, integration, data compatibility,
  security and rollout/rollback checks.
~~~

When a reviewer sees a `List.of` or `record` change in this PR, they should ask: what target-JDK failure does it fix? Without a reason, move it to a modernization PR.

## 20. Design small PRs/commits for bisectability

A viable commit sequence:

| Commit/PR | Content | Change axis |
|---|---|---|
| 1 | Baseline tests, golden fixtures, CI metadata | Observation |
| 2 | Maven/Gradle Wrapper and build plugins supporting the JDK | Build compatibility |
| 3 | Add dependencies replacing removed JDK modules | Compile/runtime compatibility |
| 4 | Upgrade mandatory reflection/bytecode/agent libraries | Runtime compatibility |
| 5 | Fix JVM launch flags, container runtime | Deployment compatibility |
| 6 | Run and verify the system on the target JDK | Release gate |
| 7 | Convert internal DTOs to records (with tests) | Modernization |
| 8 | Switch expressions/pattern matching | Modernization |
| 9 | API/stream refactors with semantic tests | Modernization |
| 10 | Trial virtual threads under load | Architecture/performance modernization |

Not every row needs a standalone PR in every organization. Still, grouping by cause simplifies `git bisect`, code reviews, and reverts.

### 20.1. Do not optimize by changed line count

A 20-line PR changing a system-wide serializer can be riskier than a 100-line PR updating imports removed from the JDK. Categorize by **behavioral impact and dependency scope**, not diff size.

## 21. Use branches and release trains to keep changes from colliding

In a project with ongoing feature development:

~~~text
main: feature development
  |
  +-- migration/jdk-compat
  |      |-- build/toolchain
  |      |-- runtime/dependency fixes
  |      +-- compatibility release
  |
  +-- modernization/java-features
         |-- records
         |-- switch/pattern matching
         +-- optional refactors
~~~

Coordinate cherry-picks/merges around the release schedule and prevent two branches from editing the same code without ownership. Starting a modernization branch too early can create merge conflicts with compatibility patches.

A commonly sound pattern is **locking in the compatibility baseline on the new JDK first, then branching modernization PRs from that baseline**. If multiple teams must work in parallel, prepare proposals/PoCs while gating merges to the release branch until the compatibility gate completes.

## 22. CI: each stage validates different aspects

### 22.1. Compatibility CI

A minimal pipeline should verify:

- Building with the exact Maven/Gradle Wrapper.
- Explicit Java compiler release target.
- Unit/integration tests.
- Consumer/API contract tests.
- Persistence/cache/message fixtures from the previous version.
- Bytecode/dependency compatibility checks.
- Security/TLS/keystore smoke tests.
- Production-like artifact startup.
- Performance baselines on high-risk use cases.

If the project still supports multiple JDK runtimes, run a test matrix across every committed version. Never assume testing on Java 21 proves the artifact runs on Java 17.

### 22.2. Modernization CI

Add checks for semantic changes:

- Before/after contract tests.
- Unknown/null/edge-case handling.
- Serialization/JSON differences.
- Memory/latency/throttling when changing concurrency.
- Public binary API compatibility if the library is consumed by other services.
- Branch coverage for code rewritten to switch/pattern matching.
- Benchmarks with realistic workloads when changing performance designs.

Failures stemming from modernization must be attributed to modernization PRs rather than compromising the green JDK compatibility baseline.

## 23. Two-dimensional test matrix

While upgrading the runtime, consider:

| Application/source | Runtime | Goal |
|---|---|---|
| V1 baseline | Old JDK | Evidence of current state |
| V1 compatible (after mandatory fixes) | New JDK | Prove compatibility |
| V1 compatible | Old JDK (if still supported) | Prove dual-runtime capability |
| V2 modernized | New JDK | Validate new changes on a stable baseline |
| V2 modernized | Old JDK | Required only if V2 still commits to old JDK |

Not every cell has to pass. For example, code using Java 21 virtual threads cannot be expected to run on Java 17. The right practice is to **declare the raised minimum Java baseline in the modernization release**, rather than silently mistaking it for a compatibility regression.

### 23.1. Test the runtime, not only compilation

A library may compile with a low Java release while pulling in a transitive JAR targeting a higher classfile version. A service may start yet fail only when loading a class on a rare request. Therefore tests must exercise critical runtime paths.

## 24. Runtime observability: avoid false conclusions about performance

A new JDK can change GC ergonomics, JIT behavior, container detection, TLS providers, logging, and memory consumption. Framework/modernization changes can also alter performance.

If you change the JDK and concurrency model simultaneously, it becomes hard to attribute gains or regressions.

Compare stage by stage:

~~~text
A: App V1 + JDK X
B: App V1-compatible + JDK Y
C: App V2-modernized + JDK Y
~~~

- `A→B` measures the impact of compatibility migration/JDK and mandatory patches.
- `B→C` measures the impact of source/architecture modernization.

Metrics:

- Startup/cold start and warm-up time.
- p50/p95/p99 latency and throughput.
- CPU, heap, GC pauses, and allocation rate.
- Thread counts/connection pool saturation.
- DB query counts and cache hit rate.
- Error rates, timeouts, and retries.
- Native memory/OS resource usage.

Use identical workloads, datasets, and resource limits whenever possible. Do not treat a brief microbenchmark or a single run as proof the system got faster.

## 25. Security: mandatory fixes may change behavior intentionally

Not every compatibility change should preserve legacy security behavior. If the target JDK disables a weak algorithm or an outdated TLS protocol, re-enabling that algorithm just to "preserve behavior" may violate security policy.

Approach:

1. Identify changes in the JDK/security provider.
2. Audit partner systems and existing certificates/keystores.
3. Choose supported, policy-compliant configurations/algorithms.
4. Test TLS handshakes, signing/verification, or cryptographic operations.
5. Document which legacy protocols/consumers are impacted.
6. Coordinate partner migrations prior to rollout.
7. Never bypass certificate validation or widen `--add-opens` to mask class/security failures.

This belongs to the **compatibility/security workstream**, yet may constitute an approved breaking change. Document it explicitly rather than labeling it optional refactoring.

## 26. New APIs are not the only option for addressing deprecated code

A deprecated API does not automatically mean it has been removed from the runtime. When the target JDK still supports an API alongside a recommended replacement, evaluate:

- Will the old API remain supported long enough for the migration window?
- Are there concrete warnings or security risks?
- Does the replacement change semantics or data formats?
- Do tests verify equivalent behavior?
- Do older-JDK consumers still need to run?

If replacement is forced by removal or policy, it belongs to compatibility. If it is purely for cleaner code, place it in the modernization backlog.

**Example:** moving from `java.util.Date` to `java.time` can be a great improvement, yet carries timezone, serialization, and persistence schema risks. Do not automatically convert every date type in the system just because you upgraded the JDK.

## 27. Public libraries need separate API and binary compatibility checks

In a single-process internal application, changing a method signature can be caught within the same build. For a library published to external consumers, changing source APIs in a modernization release can cause runtime failures even when the main artifact builds cleanly.

Example legacy class:

~~~java
public final class CustomerDto {
    public String getId() {
        return id;
    }
}
~~~

If replaced by a record:

~~~java
public record CustomerDto(String id) {}
~~~

clients already compiled to call `getId()` can hit `NoSuchMethodError` once that method disappears, even if JSON output looks similar. Furthermore, constructors, reflection, and Java serialization formats can change.

Evaluate:

- Source compatibility: can existing consumers recompile cleanly?
- Binary compatibility: do old class/method descriptors still exist?
- Serialization compatibility: can legacy payloads still be read?
- Runtime compatibility: minimum Java release and dependency versions?
- Semantic compatibility: do outputs and side effects remain correct?

If modernization breaks APIs, bump the major version and follow library deprecation/adapter policies. Do not bundle it into a "support JDK 21" PR.

## 28. When can new features be used directly during migration?

There are legitimate exceptions:

### 28.1. The new API is the only officially supported option

If an old API was removed and the target JDK offers an appropriate public replacement, migrating to the new API **can be mandatory compatibility work**. Preserve behavior or document unavoidable differences clearly.

### 28.2. A new framework mandates a higher Java baseline

If the target major framework requires Java 17 with no valid intermediate release, different imports/APIs may be part of mandatory framework migration. Even then, there is no reason to automatically rewrite business models into records or introduce virtual threads.

### 28.3. Security requires eliminating legacy patterns

When legacy API usage poses an actual security risk, patches may have to alter logic. This is an intentional change requiring security review and regression tests, not hidden under "code cleanup".

### 28.4. Building a compatibility adapter layer

Example of an internal facade preserving the old public API while delegating internally to a new API:

~~~java
public final class LegacyFileReader {
    public static byte[] readBytes(Path path) throws IOException {
        return Files.readAllBytes(path);
    }
}
~~~

An adapter shrinks consumer change scope, though semantics, error mapping, and Java release targets must be assessed. Use a facade when it genuinely simplifies migration rather than adding pointless abstraction layers.

## 29. Review workflow: questions for each line of change

In a compatibility PR, reviewers can ask:

1. What specific failure occurs on the target JDK?
2. Is there a log, test, stack trace, or support matrix confirming the cause?
3. Is this change necessary to fix that failure?
4. Does it alter public APIs, schemas, formats, or behavior?
5. If behavior changes, has the impact been approved and tested?
6. Is there a smaller, lower-risk alternative?
7. Do chosen dependencies/versions support both current and target environments?
8. Does it affect rollbacks or mixed-version deployments?
9. Can optional cleanup be split into a follow-up PR?
10. What tests prove the bug is fixed without introducing regressions?

In a modernization PR, questions differ:

- Is the benefit readability, maintainability, performance, or risk reduction?
- Does the new Java minimum release change?
- Have semantic differences of the new API/syntax been identified?
- Does it affect framework serializers, ORMs, or reflection?
- Has performance been compared against the compatibility baseline?
- Do tests protect public contracts and edge cases?

## 30. Avoiding IDE "shotgun modernization"

IDEs can suggest broad automated conversions:

- For-loops → streams.
- Anonymous classes → lambdas.
- Switch statements → switch expressions.
- Class DTOs → records.
- `Arrays.asList` → `List.of`.
- `StringBuilder`/concatenation → text blocks.
- Thread pools → virtual-thread executors.

A repository-wide sweep can generate massive diffs and alter semantics in poorly tested paths. During the compatibility phase, use automated rewrites only for **narrowly defined mandatory goals** backed by proper validation.

Even when a tool guarantees syntactic validity, it cannot prove business outputs and protocol contracts remain unchanged. For Java migrations, prefer module-scoped, rollback-friendly, well-tested transformations.

## 31. Controlling configuration and packaging changes

It is not only Java code whose scope must stay bounded. JVM options, container base images, Maven/Gradle Wrappers, startup scripts, Java agents, and classpaths often need updates too.

A compatibility PR might require:

~~~text
Dockerfile:
  Switch runtime base image to approved JDK.

gradle-wrapper.properties:
  Upgrade Gradle distribution to support the build JVM.

build.gradle:
  Update Java toolchain/release.

start.sh:
  Remove unsupported JVM flags; place options in the right position.

dependencies:
  Upgrade required bytecode libraries and JDBC driver.
~~~

Do not seize that opportunity to simultaneously replace the logging framework, package layout, deployment architecture, or configuration formats unless required.

### 31.1. Preserve JVM option ordering

~~~bash
java -Xmx1g -Dapp.env=production -jar app.jar --mode=worker
~~~

Notice that JVM options precede `-jar`. Placing `-Xmx1g` after the JAR turns it into an application argument. Such a launcher mistake is never solved by rewriting Java source code to new APIs.

## 32. Persisted data spanning deployments is a critical boundary

Even after source compatibility is complete, legacy state persists:

- Java-serialized objects in Redis/caches.
- HTTP sessions and authentication tokens.
- Kafka/AMQP messages, delayed retries, and DLQs.
- Database rows using old enum/timezone/UUID representations.
- Outbox/inbox/deduplication records.
- Keystores/truststores and encrypted files.
- Backups/snapshots that may be restored months later.

If modernization alters class names, record shapes, JSON serializers, enum representations, or object schemas, new readers may fail to parse legacy data. Even simple syntax shifts like `List.of` carry less risk than structural DTO changes yet still require null/mutability review.

In a Java upgrade program, add **data compatibility tests** right from the compatibility phase and keep using them to protect modernization changes.

## 33. Project example: upgrading a Java 8 service to Java 21

Suppose an order service has:

~~~text
JDK 8
Old Maven
Old Spring/framework version
JAXB used via APIs formerly bundled in JDK
Old Java agent
Old PostgreSQL JDBC driver
REST API + Kafka + Redis sessions
~~~

The goal is moving production onto JDK 21, and later improving code readability and concurrency.

### Phase 0 — Baseline

- Save running commit/build artifact.
- Capture API/event/session fixtures.
- Collect dependency tree and JDK/agent versions.
- Run regression and integration tests.
- Record startup, GC, latency, and error rates.
- Confirm the framework/JDK support matrix.

### Phase 1 — Build compatibility

- Upgrade Maven Wrapper/Compiler/Surefire plugins where mandatory.
- Pin build JDK and compiler release explicitly.
- Add dependencies for APIs no longer bundled with the JDK, such as an appropriate JAXB implementation.
- Fix incompatible annotation processors/bytecode tooling.
- Preserve REST/message/database contracts.

### Phase 2 — Runtime compatibility

- Update Java agent, JDBC driver, and required JVM flags.
- Run the application artifact on JDK 21.
- Test TLS, database, Kafka, Redis, sessions, and legacy serializers.
- Check classloading, reflection, and logs.
- Run canary if supported by framework/version compatibility.

### Phase 3 — Compatibility release

- Deploy the new JDK with unchanged business behavior apart from mandatory fixes.
- Compare production metrics against the baseline.
- Maintain a concrete rollback point.
- Confirm error rates, user sessions, and backlogs remain stable.
- Archive the manifest of artifact/JDK/dependency versions.

### Phase 4 — Modernization after stabilization

- Pick an internal DTO with minimal external contract exposure to trial `record`.
- Convert selected switch statements to switch expressions with branch tests.
- Consider new file/string APIs where semantics fit.
- Trial virtual threads for I/O-heavy workloads in an experimental branch.
- Evaluate performance/observability before rolling out to production.

### Tracking table

| Release | JDK | Source style | API/data contract | Objective |
|---|---|---|---|---|
| R0 | 8 | Legacy | V1 | Baseline |
| R1 | 21 | Mostly legacy, mandatory fixes only | V1 | Compatibility |
| R2 | 21 | Selected records/switch/modern APIs | V1 if possible | Modernization |
| R3 | 21 | Tested concurrency/architecture changes | V1 or explicit new version | Optimization |

This table does not imply every legacy framework runs on Java 21. If the framework requires a major upgrade, make it a mandatory part of R1 or add a valid bridge release.

## 34. Rollback must be defined per change type

### 34.1. Compatibility rollback

If only the JDK/runtime changed and persisted formats stayed intact, rolling back to the previous artifact/runtime is usually possible when classfile targets and data remain compatible. However:

- A new JDK may write keystores or files using algorithms unreadable by the older JDK.
- Containers and native dependencies may have changed.
- Certificate/trust policy shifts may have prompted partner configuration changes.
- A new runtime may emit bad messages or data if a mandatory library changed behavior.

Therefore, test rollback in an environment simulating post-deployment state, rather than merely checking whether the old image boots.

### 34.2. Modernization rollback

A record refactor can alter binary APIs; switching a JSON serializer can write new payloads; concurrency changes can boost concurrent request counts. Rollbacks must weigh data compatibility, caches/sessions, messages, and side effects.

If modernization writes data unreadable by the compatibility release, rollback options narrow. Design compatible readers or isolate contract migrations with transition windows.

## 35. When can legacy code be removed?

A common error is deleting all legacy adapters immediately after rolling out the new JDK. Remaining dependencies may include:

- Consumers still using older library versions.
- V1 data formats in databases/caches.
- Events sitting in DLQs or archives.
- Clients running on older Java baselines.
- Rarely executed scheduled jobs.
- Backups that may restore legacy classes/serialization formats.

Remove compatibility code only once evidence confirms those data sources/consumers have reached end-of-life or migrated. Removing an adapter is a **contract change**, not mere cleanup.

### 35.1. Signs of "readiness" to modernize

- The primary application runs stably on the target JDK.
- Build/test CI and production deployments use locked-in toolchains.
- Critical integrations pass.
- Monitoring, logging, and rollbacks are verified.
- No unresolved mandatory JVM/provider/agent errors remain.
- A performance baseline exists on the new JDK.
- The team has review/test capacity dedicated to modernization.

Not every module organization-wide must wait before independent-scope modernization begins, provided shared API/data contracts stay governed.

## 36. Anti-pattern identification table

| Anti-pattern | Why it is risky | Alternative |
|---|---|---|
| Upgrade JDK and do a huge rewrite in one PR | Hard to isolate causes, hard to revert | Separate compatibility from modernization |
| Upgrade framework major just for new syntax | Introduces unrelated breaking changes | Check support matrix; upgrade deliberately |
| "Compiles green means done" | Runtime/integration/data can still fail | Run production-like tests and legacy fixtures |
| Fix every deprecated API immediately | Can introduce unnecessary semantic shifts | Prioritize removed/mandatory APIs |
| Convert every DTO to record | Can break getters, ORM, serialization | Choose appropriate DTOs; run contract tests |
| Convert every collection to `List.of` | Null/mutability semantics differ | Evaluate per use case |
| Replace all executors with virtual threads | Backpressure and downstream resource limits differ | Run isolated pilot with load tests |
| Bump all dependencies to latest | Transitive BOMs and APIs shift wholesale | Bump mandatory ones only; handle maintenance separately |
| Scatter `--add-opens` across launchers | Masks legacy dependencies and weakens encapsulation | Upgrade libraries/agents; bound workarounds |
| Flush caches/sessions on parse errors | Can force logouts and break idempotency | Versioned schemas, compatible readers |
| Treat `--release` as runtime proof | Dependencies/runtime can still fail | Execute tests on the actual JVM |
| Assume rollback is just `git revert` | Data/messaging may not read backward | Build a data-aware rollback plan |

## 37. Checklist for a clear compatibility phase

- [ ] Target JDK, vendor/update, and supported runtimes are defined.
- [ ] Appropriate JDK/framework/build tool matrix is established.
- [ ] Baseline source/artifact/dependency versions are recorded.
- [ ] Compile JDK, toolchain, `--release`, and runtime JDK are distinguished.
- [ ] Characterization/regression/contract fixtures are in place.
- [ ] Mandatory compatibility, security, and optional modernization changes are separated.
- [ ] Required build plugins, agents, and bytecode/driver dependencies are upgraded.
- [ ] Removed JDK APIs or internal reflection are addressed with documented root causes.
- [ ] Adopting new Java features is avoided unless required for compatibility.
- [ ] REST, message, DB, and cache/session schemas stay stable where possible.
- [ ] Mandatory behavior changes and impact approvals are recorded.
- [ ] Integration tests run on the target JDK with historical data.
- [ ] GC, TLS, startup, latency, memory, and errors are measured.
- [ ] Launchers, container runtimes, and JVM flags are verified.
- [ ] Artifact/runtime/data rollback paths are prepared.
- [ ] Compatibility release stability is confirmed before broad modernization begins.

## 38. Checklist for the modernization phase

- [ ] Each proposal has clear benefits and scope.
- [ ] Any raised Java language/API minimum baseline is explicitly identified.
- [ ] Semantic differences of replacement APIs are assessed.
- [ ] Serialization, JSON, ORM, reflection, and public API contracts are verified.
- [ ] Records/switches/pattern matching/text blocks are split into reviewable changes.
- [ ] Wholesale refactors lacking test coverage are avoided.
- [ ] Benchmarks are collected if changing concurrency/streaming/data-access models.
- [ ] Consumers on older JDKs no longer depend on newly introduced binary APIs.
- [ ] Mixed-version or backward-read tests are run where needed.
- [ ] Rollback notes and data written by the new version are documented.
- [ ] Modernization bugs stay isolated from JDK compatibility baselines.
- [ ] Legacy adapter cleanup plans rely on verification evidence, not merely deploy dates.

## 39. Conclusion

**Compatibility fixes** and **adopting new Java syntax or APIs** are related yet fundamentally distinct goals. Compatibility ensures **existing system behavior and contracts continue working on the target JDK**. Modernization aims to make code cleaner, safer, more maintainable, or more performant using modern Java capabilities, and may therefore entail semantic or minimum-runtime changes.

When the support matrix permits:

1. Lock in the baseline and legacy behavior tests.
2. Fix mandatory build/runtime/dependency/API issues to run on the new JDK.
3. Verify integrations, legacy data, security, and performance.
4. Release a stable compatibility baseline.
5. Only then introduce records, switch expressions, new APIs, concurrency redesigns, or larger refactors in controlled waves.

Where frameworks and JDKs require coordinated upgrades, still separate **root-cause categories, reviews, and acceptance criteria** to avoid piling optional changes onto an already risky upgrade.

The foremost practical principle is: **first prove the system still does the right old things on the new Java platform; only then deliberately adopt the new ways**. Doing so lowers risk, keeps debugging and rollback straightforward, and establishes a reliable foundation for long-term Java modernization.
