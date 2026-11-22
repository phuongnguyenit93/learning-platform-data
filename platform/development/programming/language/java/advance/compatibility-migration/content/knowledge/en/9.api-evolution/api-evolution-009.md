# Distinguishing release version numbers from actual compatibility evidence

In a **Java Advance Compatibility Migration** project, version numbers help identify a release, but **do not themselves prove** that an application, library, or shared platform will behave compatibly. Seeing a library change from `2.4.1` to `2.4.2`, from `2.4` to `2.5`, or seeing a JDK labeled LTS only gives us a signal about how the publisher manages the product. That is not a test result for specific consumers.

Compatibility must be confirmed by **scoped evidence**: whether consumer source code still compiles, whether old bytecode still links, whether contract behavior remains preserved, whether the runtime and dependencies match, whether data/configuration can still be read, and whether testing reflects actual deployment conditions. Reliable evidence always comes with exact versions, environment, execution steps, results, and limitations of the test.

This lesson guides how to read versioning without over-interpreting it and how to build a compatibility evidence record to decide whether upgrading is safe or requires a migration plan.

## 1. What does a release version number indicate?

A release version number primarily answers the question **“which release is this?”**. Depending on the ecosystem and vendor policy, it may also convey the expected level of change, testing status, maintenance branch, or update level.

Example with Maven/Gradle coordinates:

~~~text
com.example:customer-api:2.4.1
com.example:customer-api:2.5.0
com.example:customer-api:3.0.0
~~~

Three artifacts can share the same group and library name yet differ in version. The number does not indicate whether a specific application calls an API that has changed, has conflicting dependencies, or requires a newer JDK.

A version string also does not necessarily carry the same meaning across every product:

- A library may use Semantic Versioning (SemVer).
- Another product may use release year/month, for example `2026.11`.
- A release may carry suffixes like `-RC1`, `-beta`, or `-SNAPSHOT`.
- JDKs have their own feature releases, update releases, and build numbers.
- An internal platform may use a release train code combining versions of multiple components.

To interpret accurately, read **the versioning policy of that specific artifact**, rather than applying a rule from another project.

## 2. SemVer is a release commitment, not testing evidence

Semantic Versioning typically uses the `MAJOR.MINOR.PATCH` structure. Under the common meaning of SemVer when strictly applied to a defined public API:

| Component | Release intent | What cannot be inferred from the number alone |
|---|---|---|
| MAJOR | Contains incompatible changes to the public API | That a specific consumer will break; or that every old API was removed |
| MINOR | Adds backward-compatible features per the published contract | That every old call, overload, SPI, and behavior has been verified |
| PATCH | Backward-compatible bug fixes per the published contract | That there is no behavioral change in edge cases; or that no regression can occur |

For example, `2.4.1` → `2.4.2` is a patch release if the project applies SemVer. This expresses an **intent** that supported APIs remain compatible, yet to confirm a real system, changes still must be inspected and appropriate evidence run.

A bug fix can alter behavior that the implementation previously handled incorrectly. Consumers that inadvertently relied on that faulty behavior may be affected. Conversely, a major release can contain APIs that did not change at all; consumers using only those APIs may upgrade easily after verification.

### 2.1. Limitations when applying SemVer

- SemVer only carries full meaning if the project clearly defines its **public API** and adheres to the policy.
- At the `0.y.z` stage, projects may apply different stability rules; consult the project documentation.
- Prereleases such as `3.0.0-rc.1` should not by default be assumed to carry the same stability guarantee as official releases.
- `SNAPSHOT` or dynamic versions can represent content changing over time; the same version string may not reproduce identical binaries if the publishing process does not pin artifacts.
- Some projects do not use SemVer, so `2.5.0` cannot be assumed to be “feature-addition only”.
- Vendors can make mistakes when classifying releases. Labeling a release “patch” does not fix an API break that actually occurred.

**Principle:** versioning helps prioritize verification depth; it does not replace verification.

## 3. Java SE, JDK distributions, and libraries have separate versioning systems

During Java migrations, it is very easy to lump multiple kinds of “versions” into a single line:

| Subject | Example | Primary meaning |
|---|---|---|
| Java SE feature release | Java 17, 21, 25 | Language level, APIs, and standard Java platform |
| JDK update/build | `21.0.x+build` | A specific update/build of a JDK |
| JDK distribution/vendor | Oracle JDK, Eclipse Temurin, Amazon Corretto… | Build source, packaging, updates, and support policy |
| Framework/library | `customer-api:2.5.0` | Artifact version per library policy |
| Build tool/plugin | Gradle, Maven, or plugin version | Build execution capability, plugin APIs, and JDK support |
| Application | Release `2026.11` | Deployed bundle of code, configuration, schema, and dependencies |

Two applications using Java 21 can differ in frameworks, dependencies, GC configuration, OS, and JDK vendor. Two JDKs of the same feature release can still differ in patches, supported OS/architectures, or packaging. The **LTS** label provides information about a vendor's support policy or release branch; it does not prove an application runs properly on that JDK.

When constructing a compatibility matrix, record separately the **Java baseline**, **actual JDK used**, **distribution**, **library version**, **dependency graph**, and **deployment environment**.

## 4. Compatibility is a multi-dimensional set

A “compatible” claim is not clear enough without specifying the target and compatibility type. Key dimensions include:

| Dimension | Question that must be answered | Example evidence |
|---|---|---|
| Source compatibility | Does old consumer source compile against the new library? | Compiling consumer against the new API with specified compiler/target |
| Binary compatibility | Does old consumer bytecode link with the new JAR? | Running pre-compiled consumer on the new JAR |
| Behavioral compatibility | Do values, exceptions, ordering, and side effects still honor the contract? | Contract tests with data-present/absent, error, and edge cases |
| Runtime compatibility | Do class files, JVM, modules, and native dependencies match? | Testing on target JDK/OS/architecture/container |
| Dependency compatibility | Can direct and transitive dependencies coexist? | Dependency graph, resolution checks, integration tests |
| Build-time compatibility | Do compiler, Gradle/Maven, plugins, and annotation processors still run? | Building on target toolchain, verifying tasks/outputs |
| Data/protocol compatibility | Are schemas, JSON, serialization, events, and legacy data read properly? | Consumer/producer contract tests, schema compatibility tests |
| Configuration/operational compatibility | Do properties, defaults, logging, startup, GC, and TLS still align? | Deploy smoke tests, operating under representative configurations |

An API can be **binary compatible yet behaviorally incompatible**. An application can be **source compatible yet fail to run on the minimum JDK** because a dependency requires higher bytecode. Therefore, you should not present a single “PASS” result covering all dimensions.

### 4.1. Specify the pair of subjects before claiming compatibility

Write a verifiable statement:

> “Consumer A, compiled with customer-api 2.4.1, ran without recompilation against customer-api 2.5.0 on JDK 17, Linux x64, across contract test suite X.”

This statement is more specific than “customer-api 2.5.0 is backward compatible”. It identifies the consumer, prior version, new version, runtime, and evidence set. Do not extend conclusions beyond the tested scope.

## 5. Adding a new API can still cause source incompatibility

Suppose the old version has only one overload:

~~~java
public final class Formatter {
    public static String format(String value) {
        return value == null ? "<none>" : value;
    }
}
~~~

Old consumer uses:

~~~java
String text = Formatter.format(null);
~~~

The vendor releases a minor version, adding an overload:

~~~java
public static String format(Integer value) {
    return value == null ? "<none>" : value.toString();
}
~~~

After the change, the statement `Formatter.format(null)` can become **ambiguous** because String and Integer have no subtype relationship with each other. Previously compiled binaries may still reference the `format(String)` method and run, yet recompiling the consumer fails.

The release may be numbered MINOR under the intent of “API addition only”, yet consumer compile evidence reveals source incompatibility for this case.

API addition scenarios requiring evaluation include:

- Adding an overload affecting null, lambdas, method references, or generic inference.
- Adding an abstract method to an interface causing old implementers not to compile.
- Adding a default method creating conflicts among implemented interfaces.
- Adding a method to a superclass that can affect a same-named method in a subclass.
- Adding a public type exposing a dependency absent from the compile classpath.
- Adding an enum constant that can impact exhaustive enum-handling logic.
- Changing annotations or scanning mechanisms affecting code generation or reflection.

The MINOR number alone cannot be used to conclude that all legacy consumers are source-compatible.

## 6. Changing method signatures: version numbers do not reveal linkage errors

Suppose version 1 of a library:

~~~java
package com.example.api;

public final class CustomerApi {
    public String find(String id) {
        return id;
    }
}
~~~

Version 2 removes `find(String)` and replaces it with:

~~~java
package com.example.api;

public final class CustomerApi {
    public String lookup(String id) {
        return id;
    }
}
~~~

Consumer compiled against version 1:

~~~java
import com.example.api.CustomerApi;

public class ConsumerApp {
    public static void main(String[] args) {
        System.out.println(new CustomerApi().find("C-42"));
    }
}
~~~

If the consumer is **recompiled** against the version 2 JAR, the compiler reports that method `find` cannot be found. If the old consumer bytecode is kept and the new JAR is swapped in at runtime, the JVM may throw `NoSuchMethodError` when the call executes. These are two distinct pieces of evidence: source break and binary break.

To test with real artifacts, you can run in a test environment:

~~~bash
# Build the consumer against the old API
javac --release 17 -cp lib-v1.jar \
  -d consumer-classes src/ConsumerApp.java

# Do not recompile the consumer; swap the runtime library
java -cp "consumer-classes:lib-v2.jar" ConsumerApp
~~~

On Windows, the classpath uses semicolons instead of colons, for example `"consumer-classes;lib-v2.jar"`. JAR and source names in the example are illustrative.

Note: this test is only valid when you are certain the **new JAR has replaced the old JAR**, no old copy remains elsewhere on the classpath/module path, and the code path invoking the changed method is actually executed.

## 7. Changes not manifested in API signatures

An API diff does not detect all behavioral changes. For example, the method:

~~~java
public List<Order> findOrders(String customerId);
~~~

keeps the same signature between two versions, yet the new version returns the list ordered by descending time instead of ascending. If the previous contract promised ascending order, this is behavioral incompatibility even though source and binary may continue working.

Similar changes:

- Null previously meant “not found”, later changed to throwing an exception.
- Exception previously was `IOException`, later wrapped into `IllegalStateException`.
- Default timeout changed from 3 seconds to 30 seconds.
- An old property name was removed without an alias.
- The API changed its retry mechanism and introduces additional side effects.
- JSON added a required field or changed units from milliseconds to seconds.
- Transaction boundaries changed, affecting persisted data on errors.
- A security fix tightened certificate, cipher, or reflection checks.

Many of these changes may be completely intentional and right. What must be verified is the **committed contract** and consumer migration path, rather than assuming “unchanged signature means no breaking change”.

## 8. Distinguishing metadata, claims, and evidence

When making an upgrade decision, distinguish three layers of information.

**Metadata** describes the artifact: name, version, build number, commit, release date, JDK baseline, and repository.

Vendor **claims** describe policy or expectations: “backward compatible”, “Java 17 supported”, “LTS”, “patch release”, or “no breaking changes”.

**Evidence** shows that a specific check was actually executed and its outcome recorded: compiler output, test reports, dependency lockfiles, API diffs, runtime logs, schema compatibility results, or execution results of pre-compiled consumers.

Example:

| Information | Type | Appropriate conclusion |
|---|---|---|
| `customer-api 2.5.0` | Metadata | Identifies the artifact to inspect |
| “2.5.0 is backward-compatible” | Claim | Hypothesis/support condition to cross-check |
| API diff shows no public methods removed | Static evidence | Reduces risk on part of the API surface |
| Consumer A compiled successfully with 2.5.0 | Source evidence | A is source-compatible under the configuration used |
| Old Consumer A bytecode passed contract tests with 2.5.0 | Binary and behavioral evidence | Executed test paths showed no observed errors |
| Production canary experienced TLS errors | Negative operational evidence | Cannot conclude migration is safe even though build tests passed |

Use both vendor information and actual evidence. Release notes and support policies are important inputs, but they do not replace testing within the organization's consumer context.

## 9. Evidence must have scope and reproducible conditions

A single line “Tests passed” is not enough to assess confidence. An evidence record should answer:

1. **Subject:** which artifact, version, checksum, or commit?
2. **Consumer:** which application/module, which source revision?
3. **Goal:** verifying source, binary, behavior, runtime, build, data, or configuration?
4. **Environment:** JDK feature/update/vendor, OS, architecture, container, and dependency graph?
5. **Method:** commands, test suites, inputs, data, and trigger conditions?
6. **Result:** pass/fail, test counts, warnings, logs, and artifacts?
7. **Uncovered scope:** which APIs, data variants, consumers, code paths, or platforms?
8. **Timestamp:** when was the result recorded, before or after dependency updates?

Example of a short record:

~~~yaml
evidence:
  id: customer-api-2_5_0-consumer-a-runtime17
  provider: com.example:customer-api:2.5.0
  previousProvider: com.example:customer-api:2.4.1
  consumer: consumer-a
  consumerCommit: "example-commit-id"
  javaRuntime: "17"
  os: linux-x64
  testSuite: customer-contract-tests
  result: PASS
  limitations:
    - no-windows-run
    - no-external-plugin-consumers
~~~

This is only an illustrative template. In real usage, supplement build JDK, distribution, dependency lock state, report paths, and artifact checksums as needed for reproducibility.

Good evidence does not imply “bugs are impossible”. It makes clear exactly what has been verified and what still needs checking.

## 10. Evidence from API diff: useful but incomplete

For Java libraries, before/after API comparison helps identify changes to published classes and methods. Tools like japicmp, Revapi, or approaches based on `javap` and artifact metadata can be used.

Analysis should cover:

- Public and protected classes, interfaces, methods, fields, constructors.
- Changes in method descriptors, generic signatures, and visibility.
- Abstract/default methods, superclasses, interface hierarchies.
- Checked exceptions, annotations, constants, or enums when affecting consumers.
- Module exports/opens and APIs documented outside bytecode.
- Dependencies leaked in public signatures.

Some tools classify changes by binary/source compatibility based on specific check rules. Read the tool's configuration and inspection scope: does it analyze annotations, generics, default methods, internal APIs, or transitive dependencies?

### 10.1. Manually inspecting a method with javap

Public methods and descriptors can be observed:

~~~bash
javap -classpath customer-api-2.4.1.jar \
  -public -s com.example.api.CustomerApi

javap -classpath customer-api-2.5.0.jar \
  -public -s com.example.api.CustomerApi
~~~

Comparing outputs helps reveal certain descriptor differences. However, a method having identical descriptors does not prove behavior stayed the same. Likewise, `javap` does not replace testing in consumers.

### 10.2. Negative results do not automatically prove compatibility

“API diff found no breaking changes” only means that **under the scope and rules of that comparison**, no change classified as breaking was found. It does not rule out data errors, runtime issues, reflection, native code, or behavioral changes.

Similarly, “jdeps reported no internal APIs” does not prove there is no dynamic reflection or native access to JDK details. Each tool has specific limitations that must be documented.

## 11. Evidence from consumer compile tests

A **consumer compile test** recompiles old consumer source code against the new artifact. It is a direct test for source compatibility in the chosen environment.

Example with consumer A:

~~~bash
javac --release 17 \
  -cp customer-api-2.5.0.jar \
  -d out src/main/java/com/example/ConsumerA.java
~~~

A realistic test must include the entire required classpath or use the build tool to manage dependencies, annotation processors, and generated sources. Missing dependencies cause compilation errors to no longer isolate API changes.

Cases that should be covered:

- Callers using public methods, constructors, or fields.
- Consumer classes extending classes or implementing SPIs.
- Lambdas/method references, overloads, and generic usages.
- Annotation processors, mappers, or code generators.
- Special source set configurations and test code.
- Modules built only with older JDK/Gradle versions.

Compile tests indicate whether source is valid for the compiler, release target, and dependencies in use. They do not prove the application runs properly or that a consumer not compiled in the test remains safe.

## 12. Evidence from binary compatibility tests

A **binary compatibility test** preserves consumer bytecode compiled against the old library and runs or links it with the new library. This is an especially critical test when a library is distributed to consumers that are not recompiled simultaneously.

A minimal procedure:

1. Select artifact v1, artifact v2, and a consumer built against v1.
2. Keep consumer bytecode intact without automatically recompiling it.
3. Ensure the runtime loads only version v2 in the target replacement slot.
4. Exercise code paths using old APIs.
5. Check for errors such as `NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError`, `IllegalAccessError`.
6. Record the JDK, classpath/module path, dependency graph, logs, and results.

Example of two testing directions:

| Test | Consumer | Library at runtime | What it confirms |
|---|---|---|---|
| Baseline | Compiled with v1 | v1 | Pre-migration consumer works |
| Binary upgrade | Keeps bytecode compiled with v1 | v2 | Old consumer still links and operates properly in tested cases |
| Recompile | Compiles old source with v2 | v2 | Source compatibility |
| Migrated consumer | Source updated to v2 API | v2 | New migration path |
| Rollback (if supported) | Post-upgrade consumer | v1 | Backward compatibility toward old version when rolling back; should not be assumed by default |

Succeeding on one code path does not guarantee all classes were loaded or all branches executed. Combine static analysis, targeted testing, and runtime observation.

## 13. Verifying behavior with contract tests

A library can keep every signature while changing how it executes. **Contract tests** turn what consumers are allowed to rely on into verifiable input/output examples and rules.

For a customer lookup API:

~~~java
public interface CustomerLookup {
    Optional<Customer> findById(String customerId);
}
~~~

Conditions to test:

- ID exists: Optional contains the exact customer.
- ID does not exist: Optional.empty, without a “not found” exception.
- Invalid input: behavior per contract (e.g., IllegalArgumentException).
- Backend error: must not silently return Optional.empty if the contract requires raising an error.
- Repeated and concurrent calls: adheres to promised thread-safety/caching.
- Returned result: preserves immutability or ownership rules if specified.

Illustrative JUnit example:

~~~java
@Test
void missingCustomerProducesEmptyResult() {
    CustomerLookup lookup = fixtureWithNoCustomer();

    Optional<Customer> result = lookup.findById("C-MISSING");

    assertTrue(result.isEmpty());
}
~~~

Contract tests are most valuable when they reflect real use cases and are executed for both the new provider and representative consumers, rather than merely testing a self-written implementation under the author's own assumptions.

A shared contract test suite can be built and run against both old and new versions to uncover intentional or unintended differences. If the new API has published semantic changes, separate tests for the old contract from tests for the new contract.

## 14. Java runtime baseline must be checked separately from library version

For example, a library releases `2.5.0` yet raises its minimum requirement from Java 11 to Java 17. Even if API methods did not change, a production application running on Java 11 cannot use the new artifact if bytecode or APIs require Java 17.

Common class-file major versions:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

You can use `javap -verbose` to inspect the `major version` of a class:

~~~bash
javap -verbose -classpath customer-api.jar \
  com.example.api.CustomerApi
~~~

However, inspecting a single class only confirms which bytecode format that class was compiled for. Other classes in the same JAR, multi-release JARs, and transitive dependencies may have different requirements. Runtime testing on the minimum JDK remains necessary.

### 14.1. Compile target does not prove runtime

In Gradle Kotlin DSL, you can configure:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

In the example, the JDK 21 compiler is instructed to compile source under Java SE 17 language rules, bytecode, and APIs. This neither forces every runtime dependency to be Java 17 compatible nor automatically runs tests on JDK 17.

To claim “the library runs on Java 17”, you must test with a Java 17 runtime under the defined configuration. If supporting multiple Java feature releases, consider a CI matrix with the minimum JDK and several other supported releases.

### 14.2. JDK support claims must be conditional

“Supports Java 17 and 21” needs to specify the JDK distribution, OS/architecture, test types, and tested modules. LTS or vendor update labels do not replace runtime evidence. Native dependencies, truststores, timezones, security providers, module access, or build tools can differ even with the same Java feature number.

## 15. Dependency graph is part of the compatibility conclusion

A library version does not exist in isolation. An artifact can pull in new dependencies, change transitive versions, or expose external types in its API.

Example:

~~~kotlin
dependencies {
    implementation("com.example:customer-api:2.5.0")
}
~~~

The build tool resolves a dependency graph based on constraints, repositories, BOM/platforms, and conflict resolution rules. Another application in the same build may require different versions of a shared dependency.

Questions to record:

- What is the actually resolved version, and does it match the intended version?
- Which transitive dependencies were upgraded or replaced?
- Are there class, method, or logging/HTTP/JSON runtime conflicts?
- Does any dependency require a higher JDK than the application's baseline?
- Does any library leak implementation dependencies in public API signatures?
- Do BOMs or constraints cause upgrading one artifact to pull along many other artifacts?

With Gradle, per-module dependency reports and dependency insight can be used:

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency customer-api
~~~

The commands are examples; project/module names and configurations vary by actual build. A dependency graph report helps explain the tested environment, yet does not prove behavioral compatibility.

If reproducibility is required, manage resolved versions, dependency locking, or artifact verification according to organizational policy. Avoid relying on uncontrolled version ranges or mutable artifacts in compatibility reports.

## 16. Test matrices must reflect upgrade direction

Not every consumer/provider combination direction is supported. Explicitly document migration direction:

| Consumer / Provider | Old provider v1 | New provider v2 |
|---|---|---|
| Old consumer, old bytecode | Baseline required to work | Focus of binary compatibility verification |
| Old consumer, recompiled | Source baseline check when needed | Focus of source compatibility verification |
| Consumer migrated to new API | May not be supported | Verifies new API and behavior |
| Consumer running old runtime | Verified within supported scope | Confirms whether runtime baseline satisfies v2 |

**Upgrade** compatibility (old consumer → new provider) does not automatically imply **rollback** compatibility (new consumer → old provider). A new consumer calling APIs that only exist in v2 will not be able to use provider v1 without a fallback mechanism.

In addition, distributed systems may deploy non-simultaneously. When producer v2 and consumer v1 coexist, verify corresponding schemas, events, headers, and protocols. A “binary compatible” Java artifact is not enough to prove network protocols or database schemas are compatible.

## 17. Evaluating the strength of evidence

Not all evidence holds equal value against every risk:

| Evidence | Reasonable strength of assertion | Shortcoming |
|---|---|---|
| Merely seeing PATCH version bump | Release intent of minimal changes | No consumer testing |
| Release notes say “non-breaking” | Vendor claims compatibility preservation | May miss internal use cases |
| Clean API diff | Did not detect API break categories checked by the tool | Has not verified behavior/runtime |
| Consumer compile pass | Consumer source verified valid | Does not prove old binary or runtime |
| Old consumer bytecode passes tests | Some binary/runtime compatibility paths executed | Does not cover every class/code path |
| Contract tests pass | Behavior described in tests still holds | Does not prove test specification is complete |
| Canary on representative environment passes | A set of flows works upon deployment | Does not reflect all traffic, load, and rare events |
| Production rollout monitored stable | Operational evidence on real traffic | Must still monitor future environmental changes |

Conclusions should rest on a **complementary set of evidence**. API diff combined with compile tests, binary tests, contract tests, and staging/canary is stronger than reading release notes alone.

A FAIL finding is especially valuable: it shows a compatibility assumption failed within the test's scope. Do not exclude a failure from the report just because a version looks “safe”.

## 18. Designing an evidence record for each release decision

A go/no-go decision should have a concise record traceable to artifacts and tests. Example:

~~~yaml
migration:
  component: customer-api
  fromVersion: "2.4.1"
  toVersion: "2.5.0"
  intendedConsumers:
    - consumer-a
    - consumer-b
  javaBaseline: "17"
  runtimeMatrix:
    - jdk: "17"
      os: "linux-x64"
    - jdk: "21"
      os: "linux-x64"
  verification:
    apiDiff: PASS
    sourceCompile: PASS
    oldBinaryRun: PASS
    contractTests: PASS
    integrationTests: PASS
  limitations:
    - external-consumers-not-enumerated
    - windows-not-tested
  decision: CONDITIONAL_GO
  rationale: "Supported internal consumers passed selected checks"
~~~

This is illustrative data, not the result of an actual test run. In operations, the record must include links to reports and logs, commits, JAR/container checksums, dependency graph, test timestamp, accountable owner, and exceptions.

### 18.1. Avoid writing overly broad conclusions

Do not write:

> “2.5.0 is fully compatible with all previous versions.”

If only two internal consumers on Linux/JDK 17 were tested, write:

> “Internal consumers A and B passed compile, binary, and contract tests when migrating 2.4.1 → 2.5.0 on the recorded environment. External consumers and Windows were not tested.”

A narrower phrasing does not make the result less useful; it helps decision-makers accurately understand the remaining risk.

## 19. Evidence-based upgrade decision workflow

A practical workflow can be executed in the following stages.

### Step 1: Define the scope of change

Specify artifacts, old/new versions, JDK baseline, versioning policy, and release notes. Do not just write “upgrade library to latest version”.

### Step 2: Read vendor promises

Review versioning policy, deprecations, breaking changes, and runtime support. If the release has a MAJOR bump, review the migration guide. If PATCH, still inspect changelog and dependency changes.

### Step 3: Inventory consumers and usage

List source, deployed bytecode, SPI implementers, reflection, code generators, configuration, data formats, and critical dependencies. Prioritize high-risk consumers or slow upgrade schedules.

### Step 4: Run static analysis

Compare APIs, class-file versions, module boundaries, and dependency graphs. Record tool warnings and limitations.

### Step 5: Run source and binary tests

Recompile old consumers against the new version; simultaneously preserve old bytecode and test against the new provider. These two tests answer two different questions.

### Step 6: Run contract and integration tests

Verify committed behavior and critical error flows, especially null, exceptions, timeouts, transactions, serialization, and retries. Run on the minimum JDK and other critical environments if within support scope.

### Step 7: Controlled deployment trial

Use staging or canary with production-like configuration. Monitor JVM errors, HTTP, TLS, GC, memory, latency, and business metrics. Define a rollback strategy before wide rollout.

### Step 8: Store evidence and make the decision

Record PASS/FAIL results, uncovered scope, owner, remaining risk, and go/no-go conditions. If there is a FAIL, resolve it first or transparently accept an exception per organizational process.

## 20. Common misconceptions to avoid

**“It's a PATCH change so it's definitely non-breaking.”** PATCH indicates intended release policy, not a substitute for testing. A bug fix can affect consumers relying on uncommitted behavior.

**“A MAJOR change definitely breaks every consumer.”** Only consumers using changed parts or indirectly impacted carry corresponding risk; analysis is still required.

**“Compiling successfully means compatible.”** A compile pass does not sufficiently detect runtime, configuration, or behavioral errors.

**“API diff reports no errors so it's safe.”** API diff primarily verifies the surface the tool checks; behavior, data, and environment require other tests.

**“It ran on Java 21 on dev machines so production Java 17 will work.”** You must check class-file baseline, dependencies, platform APIs, and the actual runtime.

**“The vendor says Java 17 is supported so every distribution and OS is fine.”** Support claims must be read against the specific vendor and environment matrix.

**“One passing test result applies to every consumer.”** Every consumer has different usage, dependency graph, data, and deployment.

**“No errors in smoke tests means binary compatible.”** Smoke tests might not execute a removed method or a dynamically loaded plugin branch.

**“Once a version is pinned, the binary is always identical.”** With mutable artifacts, snapshots, or updated image tags, the same label does not guarantee identical bytes. Use checksums/digests and trusted artifact sources when reproducibility is needed.

## 21. Checklist before declaring compatibility

- [ ] Accurately identified artifacts, from/to versions, and versioning policy.
- [ ] Distinguished metadata, claims, and actual verification results.
- [ ] Identified the public API, consumers, and critical use cases.
- [ ] Evaluated source, binary, behavioral, runtime, dependency, and build-time compatibility.
- [ ] Reviewed API diff and changes in signatures, SPIs, default methods, overloads.
- [ ] Recompiled old consumers against the new provider in the defined environment.
- [ ] Ran old consumer bytecode against the new provider without recompiling.
- [ ] Checked JDK baseline, class-file targets, transitive dependencies, and module access.
- [ ] Ran contract/integration tests for success paths, error paths, and edge cases.
- [ ] Recorded JDK/vendor/build, OS, dependency graph, commits, artifact checksums, and logs.
- [ ] Explicitly documented untested consumers/platforms, exceptions, and residual risks.
- [ ] Established go/no-go decision, owner, rollback plan, and post-deployment monitoring approach.

## Conclusion

**A version number is a label and policy signal; compatibility evidence is a contextual verification result.** SemVer, MAJOR/MINOR/PATCH, LTS, or claims of “backward compatible” help guide the verification plan, yet cannot replace compile tests, binary tests, contract tests, and runtime and dependency checks on real consumers.

In Java API evolution, describe compatibility per dimension and per consumer–provider pair, specifying from which version to which version, on which JDK/environment, with which test suite and scope. An evidence-based approach keeps upgrades controlled, separates actual failures from assumptions based on version numbers, and produces traceable, verifiable, and repeatable release or migration decisions.
