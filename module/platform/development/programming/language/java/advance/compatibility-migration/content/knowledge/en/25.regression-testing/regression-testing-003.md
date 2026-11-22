# Source Compatibility Testing by Recompiling Consumers

When upgrading a JDK, upgrading a library version, or modifying the public API of a Java module, the crucial question is not merely **"does the new library compile?"** but also **"can the source code of applications consuming that library recompile without modification?"**. This is the core of **source compatibility testing** by recompiling downstream users, commonly known as *consumer recompilation* or *downstream compilation testing*.

A library can build cleanly on its own and pass every internal unit test while still breaking dozens of other applications. For instance, library authors might change a return type from `String` to `Optional<String>`, add an overload that renders existing call sites ambiguous, tighten generic bounds, or stop exporting a package in `module-info.java`. Such breakages often surface only when **the compiler processes real consumer source code** against the new artifact.

This lesson belongs to the **Regression Testing** chapter of the **Java Advance Compatibility Migration** module. It covers scoping consumers, constructing controlled compilation experiments between old and new versions, pinning JDKs/toolchains/dependency graphs, classifying failures, automating checks in CI, and pairing compilation tests with binary/runtime testing to reach well-founded compatibility conclusions.

## 1. Learning objectives

After completing this lesson, you will be able to:

- Distinguish **source compatibility**, **binary compatibility**, and **behavioral compatibility**.
- Explain why a passing library build does not prove consumer source remains compatible.
- Design experiments that keep consumer source unchanged and swap only the library artifact to detect upgrade-induced compilation errors.
- Identify API change patterns that commonly break source: method signatures, return types, visibility, overloads, generics, checked exceptions, interfaces, and JPMS.
- Use Maven or Gradle to compile consumers against old and new artifacts under identical test conditions.
- Separate API breakages from errors caused by the JDK, compiler, transitive dependencies, annotation processors, and build configuration.
- Organize a **consumer corpus**, test fixtures, a JDK matrix, and regression reports.
- Recognize the limitations of recompilation testing and the additional verification required prior to release.

## 2. Source compatibility differs from binary and behavioral compatibility

### 2.1. Source compatibility

**Source compatibility** answers the question:

> Keeping the consumer's source code unchanged, can it compile under the selected compiler/toolchain against the new library version?

Example consumer:

```java
package com.example.consumer;

import com.example.api.UserDirectory;

public final class UserScreen {
    public String display(long id) {
        UserDirectory directory = new UserDirectory();
        String name = directory.findName(id);
        return "Xin chào " + name;
    }
}
```

In the older library version, `findName(long)` returned `String`. The new version returns `Optional<String>`:

```java
// Old API
public String findName(long id);

// New API
public Optional<String> findName(long id);
```

With consumer source left intact, assigning the result to `String` fails compilation against the new library. This is a directly observable **source compatibility break**.

### 2.2. Binary compatibility

**Binary compatibility** answers a different question:

> If a consumer was already compiled against the older library, do its class files still link and run against the new library without recompiling?

A compiled consumer JAR embeds specific bytecode references to classes, methods, and fields. If the new library removes a method or alters its descriptor incompatibly, runtime failures can occur:

```text
java.lang.NoSuchMethodError
java.lang.NoClassDefFoundError
java.lang.IncompatibleClassChangeError
java.lang.IllegalAccessError
```

These errors generally appear at runtime rather than when recompiling consumer source.

**Never conclude "binary compatible" solely because consumer source recompiles cleanly.** A change can let new source compile while breaking linkage for previously compiled class files. Conversely, some changes preserve binary compatibility while breaking source compatibility.

### 2.3. Behavioral compatibility

**Behavioral compatibility** asks:

> After upgrading, does the consumer continue to satisfy its contract regarding outputs, exceptions, transactions, serialization, and operational behavior?

For example, a library may preserve the signature:

```java
public int calculateDiscount(int amount);
```

yet alter rounding rules or return a different value when `amount = 0`. Source compilation and bytecode linking both succeed, yet business logic breaks.

Catching this class of failures requires regression, integration, contract, or property-based tests.

### 2.4. Three-layer compatibility matrix

| Compatibility type | Target under test | Verification test | What it does NOT prove |
| --- | --- | --- | --- |
| Source | Consumer source unchanged | Recompile against new API | Precompiled binaries keep running; behavior stays correct |
| Binary | Consumer classes/JARs built before upgrade | Run or analyze ABI against new library | Fresh consumer source necessarily compiles |
| Behavioral | Business flows and contracts | Unit/integration/contract/load tests | All other consumers' call sites compile |
| Configuration/deployment | Actual build and runtime | Start/test with real toolchains/containers | Correctness of all business outputs |

In Java compatibility migration, these testing layers **complement** rather than replace one another.

## 3. Why compile the actual consumers?

### 3.1. A library's unit tests cover only cases the author wrote

A library may have high test coverage yet omit usage patterns relied upon by real consumers:

- Consumers passing `null` to an overloaded method.
- Consumers defining classes that implement library interfaces.
- Consumers subclassing or overriding protected methods.
- Consumers depending on highly specific generic type inference.
- Consumers using method references, lambdas, or annotation processors.
- Consumers inside named modules referencing exported packages.
- Consumers importing public types not intended as officially supported APIs.

Such patterns rarely appear in the library vendor's own test suite. **Recompiling consumer source** puts the compiler through the exact call sites applications depend on.

### 3.2. API diff analysis is necessary but insufficient

API/ABI diff tools can flag removed methods, changed visibility, or altered generic signatures. However, actual source impact depends on **how consumers use the API**.

For instance, adding an overload looks additive yet can turn an existing call site ambiguous. Conversely, removing an API breaks no specific consumer if that consumer never calls it.

Therefore, combine:

1. API diffs to spot risky changes.
2. Consumer recompilation to measure **real impact on active source code**.
3. Runtime tests to confirm behavioral and binary compatibility.

### 3.3. When is recompilation testing especially valuable?

It is particularly valuable when:

- Bumping major/minor versions of shared libraries across a monorepo or multiple repositories.
- Changing the public API of an internal SDK.
- Migrating from JDK 8 to 11/17/21 alongside dependency upgrades.
- Upgrading framework cores/BOMs and extension APIs.
- Moving `javax.*` to `jakarta.*`.
- Moving a library from the classpath onto the module path.
- Upgrading compilers or changing the Java source level.
- Altering generic bounds, overloads, or interface methods.
- Publishing a library with many downstream consumers, especially under source compatibility commitments.

## 4. Test scope: who counts as a "consumer"?

### 4.1. Direct consumers

Direct consumers declare a dependency on the library and reference its public types in source code.

```text
library-api
     |
     +----> web-service
     +----> batch-job
     +----> desktop-client
```

When upgrading `library-api`, at minimum compile the source of these critical consumers against the new artifact.

### 4.2. Indirect consumers

A module may never import a library's classes directly yet still break because a transitive dependency changed version or an intermediate module's public API exposes types from that library.

```text
shared-model
    |
    v
business-sdk
    |
    v
order-service
```

If `business-sdk` exposes methods returning types from `shared-model`, upgrading `shared-model` can force `order-service` to recompile and update its source.

Do not scope solely by direct imports; examine public API exposure and the full transitive dependency graph.

### 4.3. External consumers

For libraries distributed to partners, not all consumer source lives inside the vendor's repository.

You can assemble a **consumer corpus** containing:

- Official sample applications.
- Integration tests contributed with customer consent.
- Key partner adapters or SDKs.
- Public API examples from documentation.
- Representative open-source downstream projects with compatible licenses and access rights.
- Compatibility fixtures capturing patterns behind past regressions.

Results prove compilation only for the **tested corpus**, not compatibility for every external consumer in existence.

### 4.4. Consumers of generated code

Consumer code is not limited to hand-written source:

- Java source generated from OpenAPI/Protobuf/gRPC.
- MapStruct and other annotation processors.
- JPA metamodels.
- Framework code generation.
- Kotlin/Groovy/Scala modules calling Java libraries.
- Bytecode generation or runtime proxies.

For generated code, regenerate from the **actual generator version and schemas**, then compile the generated output. A fixture holding stale pre-generated code can miss cases where the generator itself no longer understands the target API.

## 5. Designing a clean controlled experiment

### 5.1. Hold consumer source fixed

The golden rule: to isolate the impact of a library upgrade, **keep the consumer source snapshot identical** and swap only the dependency artifact.

```text
                        Consumer source S (fixed)
                                   |
                     +-------------+-------------+
                     |                           |
                     v                           v
          Library v1 + env E             Library v2 + env E
                     |                           |
                     v                           v
              Compile baseline             Compile candidate
                     |                           |
                     +-------------+-------------+
                                   |
                                   v
                          Compare diagnostics
```

Environment E comprises the JDK/compiler, source level, build tool, plugins, other dependencies, annotation processors, and classpath/module-path settings.

If you alter consumer source, JDK, and library in the same run, you cannot attribute failures to a single cause.

### 5.2. Read both outcomes together

| Baseline v1 | Candidate v2 | Interpretation |
| --- | --- | --- |
| PASS | PASS | No source break detected within the chosen corpus and environment. |
| PASS | FAIL | **Source compatibility regression** likely caused by candidate; classify errors. |
| FAIL | PASS | Source failed to compile on baseline; new API may fix it, but baseline failure needs explanation. |
| FAIL | FAIL | Experiment lacks a valid baseline or source was already broken; cannot blame candidate for regression. |

In strict experiments, treat only `PASS→FAIL` as a regression signal after confirming artifacts and environments differ strictly on the tested variable.

### 5.3. Separate the two experiment types

**Experiment A – library compatibility:** hold the JDK/toolchain fixed and change only the library version. Goal: uncover library-induced source breaks.

**Experiment B – Java migration compatibility:** hold consumer source and a supported library version fixed while varying the JDK/`--release`. Goal: uncover Java source/API/module-system breaks.

Only afterward test the **target combination of new JDK + new library**. Splitting experiments speeds up root-cause isolation.

### 5.4. Do not trust mutable local cache artifacts as proof

Record full artifact provenance:

- Group ID, artifact ID, version.
- Internal/public repository URL and checksum.
- Build commit or release tag for snapshots.
- Packaging/classifier.
- Actual resolved transitive dependencies.
- Module name/descriptor if placed on the module path.

If `1.0-SNAPSHOT` gets overwritten between builds, tests labeled "same version" may compile against different bytecode. Use immutable artifacts or publish to an isolated test repository.

## 6. Basic example: library changes a return type

### 6.1. Library API before upgrade

Suppose `com.example:directory-api:1.0.0` exposes:

```java
package com.example.directory;

public final class UserDirectory {
    public String findName(long userId) {
        return "User-" + userId;
    }
}
```

Consumer code:

```java
package com.example.consumer;

import com.example.directory.UserDirectory;

public final class UserPage {
    private final UserDirectory directory = new UserDirectory();

    public String title(long id) {
        String name = directory.findName(id);
        return "Welcome, " + name;
    }
}
```

Compiled against the old API: valid.

### 6.2. Candidate API after change

Library `2.0.0` updates the method to:

```java
package com.example.directory;

import java.util.Optional;

public final class UserDirectory {
    public Optional<String> findName(long userId) {
        return Optional.of("User-" + userId);
    }
}
```

Compiling **that exact existing `UserPage` source** against the new library reports:

```text
incompatible types:
java.util.Optional<java.lang.String> cannot be converted to java.lang.String
```

This provides direct evidence that the new API breaks source compatibility for existing consumers.

### 6.3. Two remediation strategies

**Strategy 1 – Preserve compatibility in the library:** retain `String findName(long)` during a transition period and introduce a distinct method name such as `Optional<String> findNameOptional(long)`, deprecating the old method on a planned schedule.

**Strategy 2 – Intentional migration:** accept the breaking change and update consumer source:

```java
public String title(long id) {
    String name = directory.findName(id).orElse("Unknown");
    return "Welcome, " + name;
}
```

Document clearly that **edited** consumer code compiling measures migration readiness, which is **distinct** from claiming the new API is source-compatible with untouched consumers.

## 7. API changes prone to causing source breaks

### 7.1. Removing or renaming classes, methods, or fields

```java
// v1
public void registerUser(String id);

// v2
public void createUser(String id);
```

Consumers calling `registerUser` fail to compile unless an adapter or old method remains.

The same holds when removing public constructors, renaming types, stopping package exports, or reducing class/constructor visibility.

### 7.2. Changing parameter types

```java
// v1
public void send(String destination);

// v2
public void send(Endpoint destination);
```

Calls such as `send("queue-A")` cease to compile. Even if `Endpoint` has a `String` constructor, the compiler **does not implicitly convert** a `String` into an `Endpoint` unless language rules permit conversion.

If the target API preserves a compatible overload, consumers may still compile; outcomes depend on exact signatures.

### 7.3. Changing return types

```java
// v1
public List<Order> findOrders();

// v2
public Stream<Order> findOrders();
```

Consumers assigning directly to `List<Order>` or invoking `size()` fail compilation.

Altering return types also impacts binary linking. Check source and binary compatibility separately; never assume identical method names imply unchanged ABIs.

### 7.4. Adding checked exceptions

```java
// v1
public void flush();

// v2
public void flush() throws java.io.IOException;
```

If consumers call `flush()` from methods neither declaring nor catching `IOException`, compilation fails with an unhandled exception error.

Conversely, altering unchecked exceptions or throwing behavior may leave compilation intact while still introducing a behavioral regression.

### 7.5. Changing visibility

```java
// v1
public class Validator {
    public boolean check(String input) { return true; }
}

// v2 - example breaking API change
public class Validator {
    protected boolean check(String input) { return true; }
}
```

Consumers outside the package that are not valid subclasses can no longer invoke `check` as before.

Do not inspect only whether a class is public; methods are governed by **package visibility, subclass context, module exports, and Java access rules**.

### 7.6. Changing generics

Example:

```java
// v1
public List<Number> numbers();

// v2
public List<Integer> numbers();
```

Although `Integer` is a subtype of `Number`, `List<Integer>` is **not** a subtype of `List<Number>` due to Java generics invariance. Consumer code:

```java
List<Number> values = api.numbers();
```

compiles against v1 yet fails against v2.

Audit:

- Generic type parameters.
- Bounds such as `<T extends Number>`.
- `? extends` and `? super` wildcards.
- Return types of fluent APIs.
- Generic inheritance and type inference.
- Raw types, warnings, and unchecked conversions.

A signature change after type erasure can break source without altering the JVM descriptor identically. Source and binary compatibility must still be evaluated separately.

### 7.7. Adding ambiguous overloads

Adding a new method appears **non-breaking**, yet can break overload resolution at existing call sites.

Example v1:

```java
public void register(CharSequence value);
```

v2 adds:

```java
public void register(java.io.Serializable value);
```

Consumer keeps calling:

```java
api.register("alice");
```

`String` implements both `CharSequence` and `Serializable`. Because neither parameter type is a subtype of the other, compilation can fail with **reference to register is ambiguous**.

This illustrates why an API diff reporting only "new method added" cannot guarantee source compatibility.

### 7.8. Method references and lambdas

Consumers may write:

```java
Function<String, Result> operation = service::process;
```

Adding overloads, tweaking generics, or changing functional interface targets can shift type inference or trigger ambiguity even when source calls look simple.

Consumer recompilation is especially effective at catching impacts difficult to spot from flat method lists.

### 7.9. Interfaces and default methods

Adding an abstract method to an interface breaks concrete consumer implementations that do not yet implement it.

Adding a **default method** keeps many consumers compiling, yet is not unconditionally source-compatible: if a class implements two interfaces that now both supply default methods with matching signatures, the compiler requires an explicit override to resolve the conflict.

Conceptual example:

```java
interface A {
    default String label() { return "A"; }
}

interface B {
    // v1: label() does not exist yet
    // v2: added default String label() { return "B"; }
}

class ConsumerType implements A, B {
    // v1 compiles; v2 may require overriding label()
}
```

Compile consumer classes that **implement or extend APIs**, not merely code calling API methods.

### 7.10. `static`, instance members, and constructors

Switching a method between `static` and instance breaks existing call syntax. Replacing a public constructor with a static factory breaks `new Type(...)`.

Also inspect inheritable APIs: adding `final` methods or altering superclasses can break consumer subclasses.

### 7.11. Enums, sealed types, and records

As libraries evolve alongside Java, changes may include:

- Adding enum constants: source usually still compiles, though exhaustive switches or business logic may need updates.
- Sealed hierarchies: consumer classes previously extending/implementing a type may become forbidden by `permits` or module/package rules.
- Record/class conversions: constructors, accessors, inheritance, or reflection contracts can change.
- Pattern matching/switch constructs tied to Java source level: consumer source may fail to compile under an older `--release`.

Conclusions must reflect **both language level and how consumers use the API**.

### 7.12. Annotation APIs and generated code

Consumers may apply library annotations directly or rely on annotation processors generating code against library APIs.

Renaming annotation elements, changing retention/targets, adding required elements, or altering generator outputs can fail compilation either directly or during annotation processing.

Running tests that compile pre-generated source without running processors can miss such issues. Run the same code-generation pipeline consumers use in practice.

## 8. Java versions: identical source across different compilers and `--release`

### 8.1. Source compatibility is always contextual

Never declare "the library is source-compatible" without recording:

- JDK vendor/version and compiler used.
- `--release` or source/target compatibility settings.
- Dependency set and classpath vs. module path.
- Compiler flags, annotation processors, and warnings policy.
- Consumer source characteristics (Java/Kotlin/Groovy...).
- Candidate module/JAR version.

Source using `var`, records, or newer language features compiles at one Java level and fails at a lower level regardless of library changes.

### 8.2. `--release` governs the Java API level

Example:

```bash
javac --release 11 \
  -cp libs/directory-api-2.0.0.jar \
  -d out \
  src/com/example/consumer/UserPage.java
```

`--release 11` constrains Java SE source and API surface to release 11. However, it does **not automatically check** whether third-party dependencies on the classpath use bytecode and APIs compatible with a Java 11 runtime.

Verify the Java baseline of dependencies and test compiled artifacts on the target JVM.

### 8.3. Do not swap the JDK while isolating library API breaks

When comparing library v1 vs. v2, execute both compiles on the **exact same JDK and compiler flags**. If upgrading the JDK is also a goal, run separate JDK comparison steps first or afterward so causes do not blur together.

Example matrix:

| Consumer source | Library | Compiler/`--release` | Purpose |
| --- | --- | --- | --- |
| S0 | v1 | JDK 17 / release 11 | Baseline |
| S0 | v2 | JDK 17 / release 11 | Source compatibility |
| S0 | v1 | JDK 21 / release 11 | Isolate JDK/compiler impact |
| S0 | v2 | JDK 21 / release 11 | Target application configuration |

This is illustrative. If v1 does not support building/running on JDK 21, explicitly mark that cell invalid and test supported steps.

### 8.4. Newer JDKs can expose internal API usage

Consumers touching `sun.*` or `jdk.internal.*` may trigger compile/access errors as newer JDKs tighten module encapsulation. Those errors differ from library API breakages even though both surface during recompilation.

When classifying failures, identify whether classes/methods belong to JDK modules or the candidate library, and inspect `exports`/`requires` alongside compiler flags rather than reflexively adding `--add-exports`.

## 9. Maven: setting up a consumer recompilation test

### 9.1. Standalone consumer fixture

Suppose two library artifacts exist:

```text
com.example:directory-api:1.0.0
com.example:directory-api:2.0.0
```

Alongside a consumer project:

```text
consumer-compat/
├── pom.xml
└── src/
    └── main/java/com/example/consumer/UserPage.java
```

`pom.xml` exposes a version property so artifact versions switch without modifying source:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example.testing</groupId>
  <artifactId>consumer-compat</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <api.version>1.0.0</api.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>directory-api</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

In the illustrative configuration above, the `api.version` property does not yet drive the dependency because the version is hardcoded. To run controlled comparisons, edit **only** the dependency `<version>` line to use a Maven property expression:

```xml
<version>&#36;{api.version}</version>
```

Using the `&#36;` entity in the text snippet above simply renders the dollar sign in documentation; in an actual `pom.xml`, write the Maven expression with a literal `$` immediately preceding the brace—never put an XML entity inside a real POM.

With this in place, CI can select artifact versions from the command line without editing source code.

### 9.2. Compiling the consumer against both versions

Maven commands:

```bash
# Baseline
mvn -Dapi.version=1.0.0 clean test-compile

# Candidate: identical source, changing only the API dependency version
mvn -Dapi.version=2.0.0 clean test-compile
```

`test-compile` compiles both main and test sources **without executing** tests. To compile only `src/main/java`, use `clean compile`. After checking compilation, still run regression tests separately.

In practice, many consumers inherit a BOM/parent where dependency management dictates versions rather than a direct property. In that case, apply a reproducible override mechanism and confirm **the resolved artifact is genuinely v1/v2** in dependency resolution output.

### 9.3. Why run `clean`?

Incremental builds or stale classes in `target/classes` can prevent output from reflecting the updated source or artifact cleanly. Recompiling from a clean directory minimizes cache noise.

However, `clean` does not guarantee local repository caches are valid or immutable. Verify resolved versions and checksums on every run.

### 9.4. Inspecting the consumer dependency tree

Inspect resolved graphs with:

```bash
mvn -Dapi.version=2.0.0 dependency:tree
```

If the candidate pulls in an incompatible transitive dependency version, compiler errors may originate from that transitive dependency rather than direct library API changes.

To support accurate conclusions, record:

- Direct candidate dependency.
- Changed transitive dependency versions.
- Parent/BOM versions.
- Dependency scopes and optional dependencies.
- Plugin and annotation processor dependencies.

Never assume changing one property leaves the rest of the graph untouched.

### 9.5. Multi-module Maven builds and reactors

If the candidate library and consumer share a Maven reactor, `-am` may cause Maven to build the artifact **from reactor sources** instead of resolving the published JAR you intend to test.

That is valid when testing integration against candidate sources, yet **not equivalent** to testing an immutable released artifact.

Isolate the consumer fixture into a separate project or point to a local/remote test repository holding published artifacts. Document whether an experiment tests source checkouts, snapshot builds, or released JARs.

## 10. Gradle: controlled consumer compilation

### 10.1. Selecting dependency version via project property

Example `build.gradle` in Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

def apiVersion = providers.gradleProperty('apiVersion')
        .orElse('1.0.0')
        .get()

dependencies {
    implementation 'com.example:directory-api:' + apiVersion
}
```

This keeps source untouched while switching dependencies via a property. The Java 17 toolchain is an example; pick the project's actually supported Java release and configure `options.release` when targeting lower Java levels.

### 10.2. Compiling against both artifacts

```bash
# Baseline
./gradlew -PapiVersion=1.0.0 clean compileJava compileTestJava

# Candidate
./gradlew -PapiVersion=2.0.0 clean compileJava compileTestJava
```

Always invoke the repository-managed Gradle Wrapper (`gradlew.bat` on Windows).

For Kotlin/Scala codebases or generated sources, include the corresponding compilation tasks and language toolchains.

### 10.3. Verifying the resolved version

```bash
./gradlew -PapiVersion=2.0.0 \
  dependencies --configuration compileClasspath

./gradlew -PapiVersion=2.0.0 \
  dependencyInsight \
  --dependency directory-api \
  --configuration compileClasspath
```

Version catalogs, constraints, platforms, dependency locking, and resolution rules can all alter chosen versions. Never infer resolved artifacts from the `implementation` declaration while ignoring resolution logs.

### 10.4. Compile classpath and runtime classpath can differ

A library might expose public API types belonging to artifacts supplied only in runtime scope or mistakenly declared `compileOnly`.

Recompiling consumers exposes "missing type in public API" failures missed by the library's own unit tests, especially when the library built under a broader classpath than consumers receive.

Test using **published metadata** (Maven POM, Gradle Module Metadata) and the dependency-resolution rules used by production consumers.

## 11. Keeping experiments clean and reproducible

### 11.1. Conditions to hold fixed

| Condition | Control mechanism |
| --- | --- |
| Consumer source | Pin commit/tag; make no edits between compiles. |
| Compiler | Identical JDK vendor/version and `--release` during API checks. |
| Build tool | Pin Maven/Gradle Wrapper versions. |
| Plugins | Pin compiler, annotation processor, and language plugin versions. |
| Other dependencies | Lock/BOM or log full graphs to isolate changes. |
| Candidate artifact | Immutable coordinates/checksums; do not overwrite snapshots arbitrarily. |
| Classpath/module path | Identical mode and setup except the intentionally varied target. |
| Cache/outputs | Run clean builds or ensure tasks avoid stale outputs. |
| Environment | Record OS, architecture, env vars, and profiles affecting compilation. |

### 11.2. Appropriate isolation levels

Execute both runs in separate workspaces or containers, each backed by strictly controlled repository caches. This prevents candidate artifacts from overwriting baseline caches or incremental compiler caches polluting comparisons.

Separate repositories aren't mandatory for every small run, yet for releases impacting many consumers or requiring audits, **reproducibility outweighs saving a few minutes of cache warmup**.

### 11.3. Which consumer source snapshot to test?

Generally maintain at least two corpora:

- **Current consumer source (S0):** code currently deployed in production at a pinned commit.
- **Migrated consumer source (S1):** code updated to adopt the candidate.

Test S0 + new library to measure **source compatibility**. Test S1 + new library to prove **migration readiness**.

Testing S1 alone shows the upgraded app builds, but tells you nothing about whether the new library breaks untouched consumers.

## 12. Testing JPMS and classpath vs. module path

### 12.1. `module-info.java` is part of the contract

An explicit named-module consumer may declare:

```java
module com.example.consumer {
    requires com.example.directory;
}
```

If the library renames its module, stops exporting a package, or relocates JARs, consumer compilation fails even when every Java class and method remains intact.

This constitutes **source compatibility under modular builds**, which classpath-only library tests can miss.

### 12.2. `requires transitive` and API exposure

Suppose module A exposes public methods returning a type from module B. A consumer C declaring only `requires A` may depend on whether A specifies `requires transitive B` in the module graph.

If the new release drops `requires transitive` to plain `requires`, consumer C can lose readability of B and fail compilation at certain call sites.

When testing JPMS, preserve consumers' module descriptors and module paths rather than silently falling back to the classpath to "turn tests green".

### 12.3. Automatic modules and unnamed modules

A JAR without a module descriptor becomes an automatic module on the module path, deriving its name from `Automatic-Module-Name` or its filename. Changing that module name breaks consumers' `requires` clauses.

Placed on the classpath, that same JAR joins the unnamed module with different visibility rules from explicit named modules. Hence classpath compilation never proves module-path compatibility and vice versa.

### 12.4. `exports` differs from `opens`

Consumer source importing types from a named module requires the package to be properly exported (`exports`). `opens` grants reflective access only under JPMS rules and does not replace regular compile-time source access.

If the compiler reports a package as "not visible", inspect `requires`, `exports`, and module resolution instead of reflexively adding `--add-exports` or `--add-opens`.

### 12.5. Multi-release JARs

Libraries may ship JDK-specific classes under `META-INF/versions/...`. Different JDK compilers/runtimes resolve distinct views under multi-release JAR rules.

When supporting multiple JDK releases, execute actual matrix builds against published artifacts. Passing compilation on JDK 21 does not prove a JDK 11 consumer sees the same API surface.

## 13. Transitive dependency and BOM impacts

### 13.1. Libraries are never upgraded in a vacuum

Library v2 may upgrade transitive dependencies:

```text
Consumer
  |
  +-- directory-api v1 -> json-core v1
  |
  +-- directory-api v2 -> json-core v2
```

A consumer compiler error may originate from public types of `json-core` re-exported through the library rather than classes inside `directory-api` itself.

Record dependency graphs for **both runs**; when evaluating overall real-world upgrade impact, transitive breaks still matter. Add isolated experiments when root-cause separation is needed.

### 13.2. BOMs can mask version overrides

Applications importing Spring Boot or platform BOMs often omit direct dependency versions. Overriding a version property in a consumer may fail to override BOM constraints.

After switching candidate versions, verify via `dependency:tree` or `dependencyInsight` that the resolved classpath genuinely uses the target artifact.

### 13.3. Exclusions and scopes

An artifact omitting a compile-scope dependency can break consumer imports of exposed API types, even though the library itself compiled fine locally against broader test/build dependencies.

Compiling consumers against published artifacts catches mismatches between published `pom.xml`/Gradle metadata and the dependency graph used during library builds.

### 13.4. Shading and relocation

When a library relocates a dependency, public API or annotation types can change packages/namespaces. Consumer recompilation surfaces broken imports, generics, and type assignability.

However, `Class.forName`, `ServiceLoader`, and `META-INF/services` entries often fail only at runtime. Always follow compilation gates with provider discovery and integration tests.

## 14. Annotation processors and polyglot consumers

### 14.1. Processors are part of the consumer build environment

Consumers frequently rely on Lombok, MapStruct, Dagger, AutoService, JPA metamodels, or custom annotation processors generating classes/methods required for downstream source to compile.

If a library upgrade prevents a processor from understanding annotations or type signatures, errors appear in **generated source** rather than hand-written code.

Compile with the production annotation processors enabled—never disable processing solely to push a test build through.

### 14.2. Changing annotations and generation contracts

Example library annotation:

```java
@GenerateAdapter(target = OldType.class)
public interface AccountMapper { }
```

Renaming `OldType` or changing required processor annotation elements can break builds during annotation processing.

When fixing breaks, update the source annotations, templates, or generators—never hand-edit generated `.java` files and declare migration complete, since subsequent builds overwrite them.

### 14.3. Kotlin, Scala, or Groovy consumers

Java libraries are often consumed from Kotlin, Scala, or Groovy, each having distinct type inference, nullability handling, overload resolution, and compiler versions.

A Java-only corpus cannot guarantee polyglot compatibility. Maintain representative consumer builds using the **actual compilers and build plugins** of every supported JVM language.

### 14.4. Generated source differs from hand-published source

When SDKs are generated from OpenAPI, gRPC, or schemas, three checks may be necessary:

1. Old generator + old schema produces baseline source.
2. New generator/SDK + target schema generates clean source.
3. Unchanged or migrated consumer source compiles against the target generated API.

Compiling a pre-saved directory of generated code alone does not prove the generator functions under the new dependency or JDK.

## 15. Consumer compilation does not replace runtime binary tests

### 15.1. Testing against precompiled consumer binaries

Alongside `S0 + library v2 -> compile`, add a binary compatibility test:

```text
Consumer binary B0 (compiled against library v1)
                  |
                  v
        Runtime classpath uses library v2
                  |
                  v
       Link + execute critical functionality
```

This catches failures triggered solely by previously compiled bytecode.

### 15.2. Why recompilation can mask binary breaks

Compilers can emit different bytecode when seeing API v2 directly. A freshly recompiled client may run cleanly while an older compiled client carries v1 method descriptors and crashes with `NoSuchMethodError` at runtime.

For example, widening a return type or relocating a method up a hierarchy changes bytecode resolution. Library maintainers must know clearly whether they commit to **source compatibility, binary compatibility, or both**.

### 15.3. API compatibility tools

Popular Java API/ABI diff tools include **japicmp**, **Revapi**, **Clirr**, as well as targeted `javap`/`jdeps` inspection.

They excel at screening public API changes and many binary/source incompatibilities, yet cannot replicate every real compiler edge case—especially overload resolution, generic inference, annotation processors, and specific JDK flags.

Pair API diff analysis with consumer recompilation for broader coverage.

### 15.4. Runtime tests must use the exact artifact that passed compilation

A recurring pipeline bug occurs when compilation tests run against candidate artifact A, yet integration tests or production deploy artifact B due to overwritten SNAPSHOTs, stale caches, or BOM overrides.

Preserve identical artifact coordinates/checksums across build, test, packaging, and deployment. When running binary compatibility tests, hold the consumer binary fixed and swap only the planned runtime library.

## 16. Avoiding false positives during recompilation

### 16.1. Mismatched compilers or toolchains

If baseline builds use JDK 11 and candidate builds use JDK 21, warnings or errors may reflect Java language changes or differing flags rather than library edits.

Mitigation: compare libraries under identical compilers, and use a dedicated matrix for JDK migrations.

### 16.2. Out-of-scope dependency graph drift

A new BOM might simultaneously upgrade JSON, logging, or validation dependencies. When consumer compilation fails, report that the **combined new dependency set fails** first, then isolate the culprit component.

Never blame the candidate library's API directly before auditing the resolved graph.

### 16.3. Baselines that were already red

If consumer source fails to compile on v1 due to broken code, bad config, or missing artifacts, a v2 compilation failure cannot count as a regression.

Resolve or document baseline blockers up front, classifying failures against historical state.

### 16.4. Leftover outputs or caches

Incremental builds may retain generated classes or stale compile outputs. Run clean builds or isolated environments appropriately.

Avoid mutable caches holding distinct artifacts under the same version string—matching version strings never guarantee identical bytecode.

### 16.5. Divergent profiles or feature flags

Source sets, Maven profiles, Gradle configurations, conditional compilation, and optional modules can cause two builds to compile different source subsets.

Record effective profiles/configurations; otherwise comparing runs across differing source sets proves nothing.

### 16.6. Network and repository outages

A build failing due to artifact download timeouts is not a source compatibility break. Classify failures separately:

- Artifact unavailable.
- Repository/authentication/network error.
- Dependency resolution conflict.
- Plugin/toolchain crash.
- Java compilation diagnostic.
- Annotation processing failure.

Include only true source/API failures in source-break statistics.

## 17. Classifying compiler diagnostics by root cause

| Symptom | Likely cause | Investigation |
| --- | --- | --- |
| `cannot find symbol` on method/type | API removed/renamed; missing dependency. | Compare API diff, call site source, and graph. |
| `incompatible types` | Changed return type, generics, or parameter. | Compare v1/v2 signatures and type inference. |
| `reference to ... is ambiguous` | New overload or altered generic inference. | Inspect candidate overloads and argument types. |
| `unreported exception ... must be caught` | Method added a checked exception. | Inspect `throws` clause and call site. |
| `has private access` / not visible | Visibility or JPMS `exports` changed. | Inspect modifiers, module graph, and packages. |
| `does not override abstract method` | Interface added an abstract method. | Inspect consumer implementers. |
| `inherits unrelated defaults` | Conflicting interface default methods. | Inspect all superinterfaces. |
| `class file has wrong version` | Compiler/JDK older than dependency bytecode. | Compare Java baseline and test/compiler JVMs. |
| `package ... does not exist` | Dependency scope, module path, or namespace changed. | Inspect classpath, Jakarta migration, and BOM. |
| Annotation processing error | Incompatible processor or code generator. | Compare processor versions, generated code, JDK. |
| `module not found` | Module name/path/resolution shifted. | Inspect `module-info.java` and JAR descriptor. |
| Repository resolution failure | Unpublished artifact or permission error. | Check repository/checksum; do not blame API. |

A single compiler diagnostic rarely explains root cause alone. Always inspect **call-site locations and resolved dependencies** to pinpoint the exact API change involved.

## 18. Measuring impact across multiple consumers

### 18.1. Do not count raw compiler errors alone

A single API change can trigger hundreds of cascading diagnostics—for example, altering `findName` causes downstream variables to fail type checks throughout a class.

Rather than reporting only "320 compile errors", aggregate by:

- Number of impacted consumer projects.
- Number of affected source files and call sites.
- Number of **root API changes** causing breaks.
- Business criticality and SLA impact.
- Availability of compatibility adapters.
- Estimated migration effort for priority consumers.

### 18.2. Risk-level classification

| Level | Description | Action |
| --- | --- | --- |
| Blocker | Critical production consumer fails compilation with no approved migration. | Block release or supply compatibility shim. |
| High | Multiple consumers need API/toolchain edits likely to impact rollout schedules. | Schedule migration and verify per consumer. |
| Medium | Low-usage consumers or straightforward mechanical migrations. | Publish migration guide/recipe and tests. |
| Low | Deprecated APIs still compile; future updates needed eventually. | Record deprecation roadmap and warnings. |

Never substitute generic "High" labels for business assessment—breaking a small consumer handling financial data can still be severe.

### 18.3. Guarding against silent coverage drops

If a corpus holds 40 consumers yet a candidate run tests only 12 due to skipped CI jobs, a green build cannot be trusted.

Track explicitly:

- Expected consumers.
- Actually compiled consumers.
- Skipped consumers and reasons.
- Baseline PASS/FAIL.
- Candidate PASS/FAIL.
- Artifact versions and environments.

Quality gates must fail or require explicit sign-off whenever **test coverage shrinks unexpectedly**.

## 19. Building a valuable consumer corpus

### 19.1. Choosing representative consumers

You do not need every project on day one; prioritize:

- Consumers exercising broad public API surfaces.
- Production-critical applications.
- Consumers subclassing or implementing library interfaces.
- Java/Kotlin/Scala consumers across distinct contexts.
- Consumers spanning every supported Java source level.
- Modular and classpath-based builds.
- Consumers using annotation processors, framework integrations, or generated SDKs.
- Consumers touching deprecated or scheduled-for-change APIs.

### 19.2. Recording snapshots and ownership

Each corpus entry should track:

```text
Consumer ID:
Repository/project:
Commit/tag:
Primary language:
JDK/compiler/--release:
Build tool/version:
Framework/BOM:
Dependency coordinates:
Classpath/module path:
Owner:
Critical APIs used:
Baseline compile result:
Candidate compile result:
Evidence link/log:
```

For external repositories, document exact revisions alongside licensing/usage terms before mirroring source into internal test fixtures.

### 19.3. Targeted fixtures for subtle API edges

Alongside full consumer apps, build focused **minimal source fixtures** covering:

- Overload ambiguity with `null`, lambdas, or method references.
- Generic bounds and wildcards.
- Interface implementations and default-method conflicts.
- Subclass overrides and protected APIs.
- Checked exceptions.
- Named-module `requires`/`exports`.
- Annotation-processor generated clients.
- Public APIs exposing transitive dependency types.

Minimal fixtures run fast and pinpoint breaks cleanly, while full consumer corpora expose real-world integration and configuration interactions.

## 20. CI/CD integration

### 20.1. Minimal pipeline flow

A candidate verification pipeline typically follows:

```text
Build library candidate
       |
       v
Publish immutable candidate artifact to test repository
       |
       v
Fetch pinned consumer source snapshots
       |
       +--> Compile against baseline library v1
       |
       +--> Compile against candidate library v2
       |
       v
Compare pass/fail and compiler diagnostics
       |
       v
Aggregate impacted APIs / consumer owners
       |
       v
Release gate / migration plan
```

When library candidate and consumers live in the same repository, guard against accidentally resolving local project sources instead of the published candidate artifact. Document dependency resolution explicitly.

### 20.2. Parallelism and isolation

Compile multiple consumers in parallel to keep turnaround short, while ensuring jobs never share mutable output directories or writable local Maven caches in ways that race or mutate snapshots.

Every job must log its artifact identity, compiler version, and isolated report so one consumer's PASS never overwrites another's output.

### 20.3. Explicit job status codes

```text
BASELINE_PASS
CANDIDATE_PASS
SOURCE_BREAK
BASELINE_BROKEN
ENVIRONMENT_ERROR
DEPENDENCY_RESOLUTION_ERROR
SKIPPED_APPROVED
SKIPPED_UNEXPECTED
```

Never lump every non-zero exit code under `SOURCE_BREAK`. Missing artifacts or compiler crashes represent infrastructure or tooling errors requiring separate triage.

### 20.4. Governing exceptions and waivers

Breaking changes may be approved for major releases. Release records should document:

- Altered APIs and rationale.
- List of impacted consumers.
- Migration guides or compatibility shims.
- Owners and rollout timelines.
- Verification that **updated** consumers compile and run cleanly.
- Rollback conditions or deprecation windows for old versions.

A waiver does not mean "source compatibility passed"—it means the break was identified, reviewed, and accepted under release policy.

## 21. End-to-end monorepo scenario

### 21.1. Structure

```text
enterprise-platform/
├── billing-api/
├── billing-client/
├── order-service/
├── reporting-batch/
└── compatibility-fixtures/
```

`billing-api` is a shared library. `billing-client` and both services consume its API directly or transitively.

### 21.2. Candidate changes

In `billing-api` v2, developers:

- Changed `createInvoice(String)` to `createInvoice(CustomerId)`.
- Added a `send(CharSequence)` overload alongside another `send(Serializable)` overload.
- Added a checked exception on `flush()`.
- Changed a generic DTO return from `List<Number>` to `List<Integer>`.
- Stopped exporting a package in `module-info.java`.

These changes threaten different consumers in distinct ways.

### 21.3. Execution roadmap

**Phase A:** compile consumer snapshots against v1 to establish baseline results; segregate pre-existing baseline blockers.

**Phase B:** compile identical snapshots against v2 under controlled JDK/compiler and dependency-graph bounds.

**Phase C:** group compiler errors by root API change rather than dumping hundreds of raw diagnostics.

**Phase D:** decide which APIs receive compatibility shims and which proceed as documented breaking changes with migration guides.

**Phase E:** open migrated consumer branches, compile against v2, and execute unit/integration/security/contract tests.

**Phase F:** test precompiled legacy consumer binaries against runtime v2 whenever released ABI compatibility is promised.

### 21.4. Example summary table

| Consumer | v1 source compile | v2 source compile | Root-cause group | Decision |
| --- | --- | --- | --- | --- |
| billing-client | PASS | FAIL | `CustomerId` signature | Add adapter or update client |
| order-service | PASS | FAIL | Overload ambiguity | Adjust API or call site |
| reporting-batch | PASS | PASS | Changed API unused | Proceed to runtime regression tests |
| modular-consumer | PASS | FAIL | Package no longer exported | Review module API contract |

These rows are illustrative. Real reports must attach compiler diagnostics, exact artifact versions, and commit hashes.

### 21.5. Release sign-off criteria

Never claim "all consumers are compatible" when only part of a corpus passes. Controlled release notes must specify:

- Whether source compatibility held or approved breaks exist.
- Which consumers have already migrated.
- Which consumers remain pending.
- Scope of binary compatibility verification.
- Executed runtime and behavioral test suites.
- Version-support commitments and rollback plans.

## 22. Practice: three distinct compiler failures

### Exercise A: adding an overload

Old library:

```java
public final class Formatter {
    public void format(CharSequence value) { }
}
```

New library adds:

```java
public void format(java.io.Serializable value) { }
```

Consumer:

```java
formatter.format("hello");
```

Question: Is this a runtime or compile-time error? Why can adding a new method break source compatibility?

**Hint:** `String` implements two unrelated interfaces; overload resolution becomes ambiguous during recompilation.

### Exercise B: adding a checked exception

V1:

```java
void write() { }
```

V2:

```java
void write() throws java.io.IOException { }
```

Consumer:

```java
public void process() {
    writer.write();
}
```

Question: Why does the consumer fail compilation on v2? Should the library or consumer be edited, or should the old method stay per API policy?

**Hint:** The compiler enforces checked exceptions in method signatures; remediation depends on compatibility commitments and migration policy.

### Exercise C: source compiles yet precompiled binaries may break

V1:

```java
public String status() { return "OK"; }
```

V2 changes to:

```java
public Object status() { return "OK"; }
```

New consumer:

```java
Object result = api.status();
```

Question: Does fresh consumer source compiling cleanly against v2 prove an older consumer JAR compiled against the `String` signature still links cleanly?

**Guided answer:** No. Test the old binary directly and/or run an ABI diff; bytecode method descriptors change when return types change.

## 23. Checklist for a consumer recompilation pass

### Scope

- [ ] Identified source and target library names and versions.
- [ ] Confirmed which consumers fall under source compatibility commitments.
- [ ] Gathered pinned source snapshots of critical direct and indirect consumers.
- [ ] Covered supported language levels, named modules, and build configurations.
- [ ] Included targeted fixtures for generics, overloads, subclasses, interfaces, and processors where relevant.

### Test conditions

- [ ] Held consumer source identical between baseline and candidate compiles.
- [ ] Controlled JDK, compiler, `--release`, plugins, and dependency graphs.
- [ ] Resolved exact immutable artifacts and verified versions/checksums.
- [ ] Verified classpath vs. module path and dependency scopes.
- [ ] Cleaned build outputs or isolated caches to prevent stale classes.
- [ ] Verified main, test, and generated sources per test scope.

### Reporting

- [ ] Baseline v1 compiles cleanly or known blockers are documented.
- [ ] Candidate v2 runs with full compiler diagnostics captured.
- [ ] Separated source/API breaks from infrastructure, toolchain, and resolution failures.
- [ ] Recorded affected call sites and consumer owners.
- [ ] Deduplicated cascading diagnostics into root API changes.
- [ ] Logged skipped consumers without unapproved coverage shrinkage.

### Follow-up checks

- [ ] Reviewed API diffs and binary compatibility implications.
- [ ] Tested precompiled consumer binaries where ABI commitments apply.
- [ ] Executed unit, integration, and contract tests for migrated consumers.
- [ ] Verified Java/JDK support matrices and target runtimes.
- [ ] Checked reflection, SPI, serialization, and service metadata where relevant.
- [ ] Prepared migration guides, adapters, or waivers for accepted breaks.
- [ ] Updated CI quality gates and archived release evidence.

## 24. Common misconceptions

**"If the library builds cleanly, every consumer will build too."** No. Library builds rarely exercise all consumer call sites, subclasses, and annotations.

**"If ABI diff shows no issues, source is definitely compatible."** No. Adding overloads or changing generic signatures can break compilation without breaking raw binary descriptors cleanly.

**"Consumer recompilation passing means the new library has no bugs."** No. It proves only that the tested source corpus compiles in the selected environment; behavioral and runtime tests remain mandatory.

**"Changing both the JDK and dependency in one job failed, so the new dependency is broken."** Cannot conclude that. Isolate compiler/JDK effects from library changes.

**"Searching for `import` statements finds all affected consumers."** Insufficient. Consumers can depend via inheritance, generics, annotation processors, reflection, or transitive public APIs.

**"Compiling modified consumer source against v2 proves source compatibility."** No. That measures migration readiness; source compatibility tests **unmodified source**.

**"Testing monorepo apps covers every customer."** No. External consumers may call APIs differently; document tested scope and limits clearly.

**"If consumer source compiles cleanly, older consumer JARs will definitely run on the new library."** No. Check binary compatibility and runtime linkage separately.

**"`Tests run: 0` with `BUILD SUCCESS` means migration is tested."** No. Compilation gates, test discovery, and runtime regression suites are independent checks.

## 25. Conclusion

**Source compatibility testing by recompiling consumers** is a high-leverage regression technique when upgrading Java, frameworks, and shared libraries: it turns abstract API diffs into concrete answers about whether **existing consumer source still compiles**. Well-designed tests lock source snapshots, hold compilers/toolchains and unrelated dependencies steady, and compare baseline v1 against candidate v2.

Even so, clean recompilation proves neither that precompiled client binaries keep linking nor that business behavior stays intact. In Java Advance Compatibility Migration, combine **consumer recompilation, API/ABI analysis, runtime binary tests, and regression/contract suites**, archive exact artifact/commit/JDK evidence, and govern every breaking change via deliberate migration guides or adapters—ensuring compatibility conclusions hold true for both library authors and dependent systems.
