# Multi-Module Projects and Aligning Bytecode Levels Across Artifacts

In a multi-module Java project, upgrading the JDK is not simply replacing the `java` and `javac` versions in CI. One module may be compiled for Java 17 and another for Java 21, while the final application is still deployed on Java 17. The overall build may pass several compilation steps yet fail when the JVM loads a class from an artifact with bytecode that is too new.

For example, a library `common-api.jar` is built with JDK 21 at class-file version 65, while a service uses JDK 17, which only supports class files up to version 61. When the service begins using a class from the library, it can encounter `UnsupportedClassVersionError`. Having both modules in the same Maven reactor or Gradle multi-project build **does not automatically make their bytecode compatible**.

Therefore, in Java Advance Compatibility Migration, three factors must be clearly managed:

1. **Build JDK / toolchain:** Which JDK provides the compiler and build tools?
2. **Target bytecode and Java platform APIs:** Which version's language features, bytecode, and Java APIs is the artifact permitted to use?
3. **Consumer minimum runtime:** Which JVM must actually load and run that artifact?

This lesson walks through defining a bytecode policy for modules, configuring Maven and Gradle, inspecting transitive dependencies, handling JPMS and multi-release JARs, and building a release pipeline that verifies the final artifact is compatible with the target JDK.

## 1. What boundaries exist in a multi-module project?

### 1.1. Module in the build-tool sense

In Maven, a parent/root project can contain multiple child modules:

```text
shop-platform/
  pom.xml
  common-model/
    pom.xml
  pricing-core/
    pom.xml
  payment-adapter/
    pom.xml
  order-service/
    pom.xml
```

In Gradle, a multi-project build can have a similar structure:

```text
shop-platform/
  settings.gradle
  build.gradle
  common-model/
    build.gradle
  pricing-core/
    build.gradle
  payment-adapter/
    build.gradle
  order-service/
    build.gradle
```

Each child module can produce one or more artifacts: main JAR, test fixtures JAR, sources JAR, generated-code JAR, shadow/fat JAR, or container image.

### 1.2. A Java module (JPMS) is not synonymous with a build module

Since Java 9, the Java Platform Module System (JPMS) allows a JAR to contain `module-info.class`, declaring `requires`, `exports`, and other access permissions. A Maven/Gradle subproject is not required to be a JPMS named module; it may simply produce a JAR on the classpath.

Two concepts must be distinguished:

| Concept | Meaning | Example |
|---|---|---|
| Maven/Gradle module | Unit of sources, tasks, dependencies, and artifacts in the build | `:common-model` or `<module>common-model</module>` |
| JPMS module | Unit in the runtime module graph with a descriptor | `module com.example.common { ... }` |
| JAR artifact | Distributed file containing classes/resources | `common-model-1.4.0.jar` |
| Deployment unit | Application/release using multiple artifacts | Service JAR + `lib/*.jar` |

A project can produce multiple JARs, of which only a subset uses JPMS. When defining a bytecode policy, you need to check **every class actually loaded by the JVM**, not just the module names in the build configuration.

### 1.3. Inter-module dependency example

```text
common-model  (Java 17 target)
    |
    +----> pricing-core (Java 17 target)
    |            |
    |            v
    |       order-service (runs on Java 17)
    |
    +----> payment-adapter (Java 21 target)
                 |
                 v
            billing-worker (runs on Java 21)
```

If `order-service` only depends on `common-model` and `pricing-core`, it can still stay on Java 17 while `billing-worker` uses Java 21. However, if `order-service` accidentally acquires a dependency on `payment-adapter` built for Java 21, the graph becomes incompatible with the Java 17 runtime.

This is one reason to separate shared libraries from adapters or implementations specific to a newer JDK.

## 2. What is a class-file version?

### 2.1. The JVM reads the class file, not a "compiled on JDK X" label

A `.class` file contains a header including the magic number `CAFEBABE` and a minor/major version pair. The **major version** indicates the class-file format level that the JVM must support.

Common milestones:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

For example, when a Java 17 runtime attempts to load a class with major version 65, it cannot execute that class under the JVM contract and may report:

```text
java.lang.UnsupportedClassVersionError:
  com/example/pricing/NewCalculator has been compiled by
  a more recent version of the Java Runtime
  (class file version 65.0),
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
```

The exact message depends on the JDK. The general meaning is that the artifact contains classes compiled for a newer JVM than the one currently running.

### 2.2. A new compiler can still produce older bytecode

Using JDK 21 to compile does not mean class files must have major version 65. If you use `javac --release 17`, the JDK 21 compiler can produce major 61 bytecode and restrict usage to the Java SE APIs corresponding to Java 17.

Example:

```shell
javac --release 17 -d out src/com/example/App.java
```

On the other hand, if you only run:

```shell
javac -d out src/com/example/App.java
```

on JDK 21, by default the language level and class-file target follow the JDK running the compiler. A module that accidentally omits `--release` configuration can produce bytecode newer than the rest of the repository.

### 2.3. Compatibility is one-way

For standard class bytecode, a newer JVM generally supports older class-file versions within its supported range. However, the reverse is not true:

```text
Java 21 runtime
   |
   +-- Load Java 17 bytecode: usually supported
   +-- Load Java 21 bytecode: supported
   +-- Load Java 25 bytecode: not supported

Java 17 runtime
   |
   +-- Load Java 17 bytecode: supported
   +-- Load Java 21 bytecode: not supported
```

This is only a condition at the **class-file level**. A major 61 class can still fail to run on JDK 17 if it requires another missing library, has a mismatched native ABI, has blocked reflection, or has an invalid runtime configuration.

### 2.4. Preview features are an additional case

Class files compiled with preview features can carry the special minor version `65535` and require a runtime supporting preview features for that **exact release**, along with `--enable-preview` when needed.

An artifact using Java 21 preview features should not be advertised as an ordinary Java 17 library or as an artifact portable across all newer JDKs. For shared libraries and long-lived releases, prefer finalized features unless product policy explicitly accepts preview constraints.

## 3. What does "aligning bytecode" actually need to align?

Not every module in the repository needs to have the same major version. What is mandatory is that **every artifact that can enter a runtime's classpath/module path must satisfy that runtime's threshold**.

A policy could look like:

```text
common-model        <= Java 17
business-api        <= Java 17
pricing-core        <= Java 17
legacy-adapter      <= Java 17
nextgen-adapter     <= Java 21
order-service       runs on Java 17
billing-worker      runs on Java 21
```

For `order-service`, the entire dependency closure loadable by the JVM must fit Java 17. For `billing-worker`, Java 21 can load modules built for both Java 17 and Java 21.

### 3.1. Inspect the dependency closure, not just direct modules

Suppose:

```text
order-service (Java 17)
    |
    v
payment-sdk (major 61)
    |
    v
crypto-provider (major 65)
```

Even though `payment-sdk` was compiled for Java 17, it pulls in a transitive dependency requiring Java 21. If `order-service` needs a class inside `crypto-provider`, the Java 17 JVM can still fail.

One rule of thumb:

> The minimum Java level of a deployable artifact must be greater than or equal to the minimum Java level of every class that can actually be loaded from its dependency closure.

Be cautious with lazy loading: startup may succeed while a specific request or lazily activated plugin later touches an incompatible class. Therefore, startup smoke tests are necessary but insufficient.

### 3.2. Bytecode alignment differs from API alignment

A major 61 library may contain a public API requiring another JDK or another dependency. For instance, code compiled with `-source 17 -target 17` under a JDK 21 compiler can accidentally reference Java APIs introduced only in Java 21 if bootclasspath/platform APIs are not properly constrained.

Hence, policy must check two things:

1. Class files match the target.
2. Referenced Java platform APIs exist on the minimum runtime.

`--release` solves both goals better than setting `source` and `target` alone when using a modern `javac`.

## 4. Three commonly confused parameters: source, target, and release

### 4.1. `--source`

`--source 17` instructs the compiler to check Java syntax/features at the Java 17 source level. It does not by itself prove that the called Java APIs already existed in Java 17.

### 4.2. `--target`

`--target 17` instructs javac to produce class files matching the chosen target version. This controls the bytecode format, but does not necessarily enforce platform API boundaries if the compiler uses a newer JDK's class library.

### 4.3. `--release`

`--release 17` in modern javac combines restrictions on source language, class-file target, and Java SE APIs available for release 17.

Example:

```shell
javac --release 17 -d build/classes src/com/example/Entry.java
```

This is typically the recommended choice for Java-only modules when the goal is to produce an artifact compatible with a specific Java release.

| Configuration | Controls syntax | Controls class major | Restricts Java SE API |
|---|---|---|---|
| `--source` alone | Yes | Depends on other settings/defaults | Incomplete |
| `--target` alone | Not primary goal | Yes | Incomplete |
| `--source` + `--target` | Yes | Yes | Incomplete if compiling with a newer JDK |
| `--release` | Yes | Yes | Yes, within Java SE platform APIs |

`--release` does not check the APIs of **third-party dependencies** selected in the graph, nor does it automatically check native libraries, reflection, or runtime behavior.

### 4.4. Build JDK differs from runtime JDK

For example, a project uses JDK 21 as its toolchain yet intends to release a Java 17-compatible library:

```text
Build JDK                 : 21
javac --release           : 17
Artifact class major      : 61
Supported runtime floor   : 17
CI test runtimes          : 17 and 21
```

A successful build on JDK 21 does not prove the library runs on JDK 17; you must run at least a suitable test suite on Java 17 to confirm the dependency/runtime closure.

## 5. Building a repository-wide bytecode matrix

A matrix helps prevent each module from deciding its target arbitrarily:

| Module | Artifact type | Build JDK | Target release | Minimum runtime | Consumer |
|---|---|---:|---:|---:|---|
| `common-model` | Library JAR | 21 | 17 | 17 | Old and new services |
| `pricing-api` | Library JAR | 21 | 17 | 17 | Pricing service, order service |
| `pricing-core` | Library JAR | 21 | 17 | 17 | Order service |
| `nextgen-payment` | Adapter JAR | 21 | 21 | 21 | Billing worker |
| `order-service` | Application JAR | 21 | 17 | 17 | Production Java 17 |
| `billing-worker` | Application JAR | 21 | 21 | 21 | Production Java 21 |

The numbers are design examples, not data from a specific repository.

### 5.1. Rules for public libraries

If `common-model` is shared by consumers still on Java 17, keep its class-file target and dependencies compatible with Java 17. Do not bump the target to Java 21 just because all developers have JDK 21 installed.

A library can be compiled with a newer compiler yet published with older bytecode. The key is avoiding sources/APIs available only in higher releases in the parts of the library that must support older runtimes.

### 5.2. Rules for applications

A deployable application can set its target equal to its production runtime. If a service only runs on Java 21, its own implementation modules can use Java 21. However, libraries shared with Java 17 still need to keep the older target or split artifacts.

### 5.3. Rules for test code

Test sources do not necessarily share the same target as main sources. A build may compile the main library for Java 17 while the test framework runs on Java 21. That can be valid, yet it is **insufficient to prove Java 17 compatibility**.

You need at least one job executing the library's tests on the lowest committed runtime, or a dedicated test suite verifying the API and runtime closure. Test fixtures published to other consumers also need a bytecode policy just like regular libraries.

## 6. Maven multi-module: centralizing configuration in the parent POM

### 6.1. Parent aggregator and child modules

An example root `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example.shop</groupId>
  <artifactId>shop-platform</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>

  <modules>
    <module>common-model</module>
    <module>pricing-core</module>
    <module>order-service</module>
  </modules>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>
</project>
```

When child modules declare the corresponding parent, properties and plugin configurations are inherited under Maven rules. If the root is merely an aggregator and a child **does not inherit** from the root as its parent, these properties do not automatically take effect in the child.

### 6.2. Centralized compiler plugin management

In the parent POM:

```xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
```

This example illustrates pinning the compiler plugin and release target; a project must choose a plugin version compatible with the Maven/JDK in use.

Note that `pluginManagement` defines the version/configuration for a plugin when used; it does not necessarily add an execution of every plugin to the lifecycle. For `jar` packaging, the compiler plugin is normally invoked by the Maven lifecycle, though inheritance and overrides must be verified using the actual effective POM.

### 6.3. Child module inheriting from parent

`common-model/pom.xml` can declare:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.example.shop</groupId>
    <artifactId>shop-platform</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>common-model</artifactId>
</project>
```

With the parent configuration above, this module is expected to be compiled for Java 17. If a child uses custom plugin executions, Kotlin/Scala compilers, custom annotation processors, or another build setup, the actual output must still be confirmed.

### 6.4. Intentional override for a Java 21 module

If `billing-worker` only runs on Java 21, the child can override the property:

```xml
<properties>
  <maven.compiler.release>21</maven.compiler.release>
</properties>
```

However, if the parent's compiler plugin configuration **hard-codes** `<release>17</release>`, this property override will not work as expected. A more controllable approach is for the parent to reference a property:

```xml
<properties>
  <java.release>17</java.release>
</properties>

<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>${java.release}</release>
        </configuration>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
```

Then a child can set `<java.release>21</java.release>`. In real POMs, ensure only one source determines the effective `release`, avoiding conflicting settings between properties and plugin executions.

### 6.5. Maven reactor does not standardize bytecode automatically

Running from root:

```shell
./mvnw clean verify
```

builds modules following the Maven reactor dependency graph, yet **does not mean every module uses the same `--release`**. A child can override compiler configuration or use a different compiler plugin/version.

Items to verify:

- Effective POM of each child.
- Actual build JDK and Maven Toolchains.
- Final compiler plugin version and `release`.
- Main and test compile configurations.
- Generated classes produced by processors or plugins.
- Nested/shaded JARs packaged into deployable artifacts.

### 6.6. Checking the effective POM

```shell
./mvnw -pl common-model help:effective-pom
```

Or inspect the configuration for an individual module in the CI workflow. The report helps determine the inherited configuration after combining parent, profiles, and plugins.

Maven profiles activated by JDK, OS, or properties can change the compiler target. Record active profiles and the actual release command; do not only read the parent POM.

## 7. Maven Toolchains and the compilation environment

### 7.1. Pinning the compiler JDK

Java toolchains let Maven use a specific JDK for toolchain-aware tools instead of always using the JDK running Maven.

Scenario:

```text
Maven process runs on JDK 21
Java compiler is selected from JDK 21
--release 17
Output main JAR has major 61
```

This works if the build tool and plugins support JDK 21. Still, to confirm Java 17 runtime behavior, tests on Java 17 are required, not compilation alone.

### 7.2. Example Toolchains Plugin configuration

One implementation in the parent POM:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.2.0</version>
  <executions>
    <execution>
      <goals>
        <goal>toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <toolchains>
      <jdk>
        <version>21</version>
      </jdk>
    </toolchains>
  </configuration>
</plugin>
```

This example assumes an environment where JDK 21 is already declared in the corresponding toolchains configuration. Check syntax against the Maven Toolchains Plugin version in use and ensure the actual JDK path can be discovered. Do not confuse selecting a compiler JDK with setting the bytecode target.

### 7.3. Java 8 target does not mean compiling with JDK 8

A newer JDK compiler can use `--release 8` to produce Java 8 code within supported limits. However, the Java 8 compiler itself does not support `--release`, and language features such as records or sealed classes cannot be compiled down to Java 8 merely by changing the target.

If a library must support Java 8, the library source must avoid post-Java 8 syntax and APIs (unless a multi-release layout or separate source set is properly designed). You must then test on a Java 8 JVM to verify the dependency closure.

## 8. Gradle multi-project: unified configuration from root

### 8.1. Declaring modules in settings

`settings.gradle`:

```groovy
rootProject.name = 'shop-platform'

include 'common-model'
include 'pricing-core'
include 'order-service'
include 'billing-worker'
```

This declaration defines a multi-project build, though by itself it does not force subprojects to share the same Java toolchain or target release.

### 8.2. A shared configuration for Java subprojects

Groovy DSL root `build.gradle` example:

```groovy
subprojects {
    plugins.withId('java') {
        java {
            toolchain {
                languageVersion = JavaLanguageVersion.of(21)
            }
        }

        tasks.withType(JavaCompile).configureEach {
            options.release = 17
            options.encoding = 'UTF-8'
        }
    }
}
```

Idea:

- Configure only when the Java plugin is applied.
- Use a Java 21 toolchain as the compiler.
- Produce Java classes at release 17.
- Apply to `JavaCompile` tasks in the appropriate scope.

In large systems, a **convention plugin** is usually easier to extend and test than direct `subprojects` configuration in the root. Choose according to the specific repository structure and Gradle version.

### 8.3. Child modules applying Java plugins

`common-model/build.gradle`:

```groovy
plugins {
    id 'java-library'
}
```

`pricing-core/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':common-model')
}
```

`order-service/build.gradle`:

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':pricing-core')
}

application {
    mainClass = 'com.example.order.Main'
}
```

When shared configuration applies properly, `JavaCompile` tasks target 17. However, if a Gradle build also includes Kotlin/Scala/Groovy or custom tasks, separate compiler policies are required.

### 8.4. Overriding the target level for a specific module

If a subproject is only used on Java 21:

```groovy
plugins {
    id 'java-library'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

**Watch out for evaluation order and configuration conflicts.** If the root or convention plugin subsequently overwrites `options.release`, the final value may not be what you intended. In large repositories, design a single property/convention for modules to declare their target instead of letting multiple places mutate the task.

A convention plugin can read a uniform property such as `javaRelease=17` or `javaRelease=21` through a governed mechanism. What matters is that the policy is published and task outputs are verified.

### 8.5. Toolchain is not the bytecode target

In Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

specifies the toolchain JDK without forcing the artifact to have major 61. Without `options.release = 17` or equivalent source/target settings, `JavaCompile` can produce Java 21 bytecode.

Likewise, the JDK running the Gradle daemon may differ from the JDK used by `JavaCompile` and `Test`. Distinguish these four items when debugging:

```text
Gradle daemon JVM     : ?
JavaCompile toolchain : ?
JavaCompile release   : ?
Test JVM              : ?
```

## 9. Build logic and convention plugins instead of scattered configuration

A multi-module repository easily develops "configuration drift":

```text
common-model  release=17
pricing-core  release=17
order-service release=17
payment-api   release=21  <-- accidental
billing-worker release=21
```

To curb this, create build logic conventions:

- Define a shared default release.
- Allow intentional per-module overrides.
- Maintain a list of modules authorized to target Java 21.
- Configure encoding and compiler flags consistently.
- Configure test runtimes according to policy.
- Generate a report of each artifact's target release.
- Avoid custom compile tasks bypassing policy.

### 9.1. Module names do not determine targets

A module named `legacy-*` does not necessarily target Java 8; a `nextgen-*` module is not automatically permitted to target Java 21. Policy must be explicitly declared and reviewed in build configuration.

### 9.2. Do not look only at `sourceCompatibility` and `targetCompatibility`

Some older Gradle builds use:

```groovy
sourceCompatibility = JavaVersion.VERSION_17
targetCompatibility = JavaVersion.VERSION_17
```

These two properties can control language and bytecode levels, yet they are not fully equivalent to `javac --release 17` for restricting Java SE APIs when the compiler runs on a newer JDK.

For `JavaCompile` on JDKs supporting `--release`, prefer `options.release` when supporting an older runtime. Then test against the real older JDK to uncover dependency and runtime behavior issues.

## 10. Java modules, JPMS, and module-info.class

### 10.1. Module descriptors have their own bytecode level

`module-info.java` is Java 9+ syntax, so you cannot turn a plain Java 8 JAR into a standard JPMS named module merely by placing a module descriptor at the root with Java 8 bytecode.

A module using:

```java
module com.example.pricing {
    requires com.example.common;
    exports com.example.pricing.api;
}
```

must be built under JPMS rules on a module-supporting JDK. If Java 17 is the minimum runtime, compiling both the module descriptor and classes with `--release 17` is a standard choice.

### 10.2. A named module does not make old dependencies compatible automatically

JPMS describes readability and exports, but does not rewrite the class-file version of transitive dependencies. If the module graph contains a major 65 artifact and the runtime is Java 17, that class still cannot be loaded.

You must verify all of the following:

- Module graph/`requires`.
- Package exports and opens.
- Java class major versions.
- Runtime dependencies and service providers.
- Classpath versus module path placement.

### 10.3. Using a JAR on the classpath does not imply JDK 8-only

A JAR without `module-info.class` can contain major 65 classes. Conversely, a JAR with a JPMS descriptor can contain components compiled for different releases under multi-release JAR rules.

Inspect the **files inside the artifact**, not just the presence or absence of a module descriptor.

## 11. Multi-release JARs: intentionally using different bytecode

### 11.1. Purpose of a multi-release JAR

Multi-release JARs (MR-JARs, since Java 9) allow a single JAR to carry base classes for older JDKs alongside alternative class versions for newer JDKs.

Example structure:

```text
library.jar
  META-INF/MANIFEST.MF
  com/example/codec/Codec.class
  META-INF/versions/17/com/example/codec/Codec.class
  META-INF/versions/21/com/example/codec/Codec.class
```

The manifest contains:

```text
Multi-Release: true
```

A runtime supporting multi-release JARs can select the class variant matching its version. For example, Java 17 uses the Java 17 variant; Java 21 can use the Java 21 variant; Java 8 uses the base class.

This mechanism is **designed for multiple class-file versions to coexist inside one artifact**. Consequently, a checker asserting "every class in the JAR must have major <= 52" will falsely reject a valid MR-JAR whose base is Java 8 and whose version-specific classes are properly placed.

### 11.2. MR-JAR verification rules

Confirm:

1. Manifest has `Multi-Release: true`.
2. Base classes use the target for the lowest supported runtime.
3. Classes in `META-INF/versions/N` only use bytecode/APIs appropriate for release N per MR-JAR rules.
4. Newer variants do not unexpectedly alter the public API relative to the base contract.
5. The artifact runs on every runtime in the support matrix.
6. Build/packaging plugins preserve entry layout and the manifest.

Do not assume putting a Java 21 class into `META-INF/versions/21` is enough to guarantee validity. Verify layout, API consistency, and behavior when the JVM selects variants.

### 11.3. `module-info.class` in a multi-release JAR

Some libraries supporting Java 8 while wanting to expose a Java 9+ module descriptor place an appropriate `module-info.class` in versioned entries. This requires a specialized build setup.

Do not simply place a major 53 `module-info.class` at the root of the JAR and claim the artifact still supports Java 8 normally. Use packaging and module metadata supported by an appropriate plugin, check with `jar --describe-module`, and test on the target JDKs.

### 11.4. Limitations of MR-JARs

MR-JARs do not solve all differences:

- Native dependencies may still differ by OS/architecture.
- Module readability or reflective access still depends on the runtime.
- The dependency closure for the Java 21 variant may differ from Java 17.
- Older classpath scanners or bytecode analysis tools may misread versioned entries.
- Shading/relocation can break MR-JAR layouts if the plugin does not support them.

Use MR-JARs only when optimizing a single library across multiple JDKs and when matching test infrastructure exists. If the Java 21 version changes the public API or major semantics, publishing a separate clearly versioned artifact is sometimes easier to maintain.

## 12. External dependencies also dictate the runtime floor

### 12.1. New versions can require a higher JDK

Suppose a new version of a serialization library moves its compiler target from Java 11 to Java 17. If consumers still run Java 11, even a "minor" version bump can fail during class loading.

During JDK/multi-module upgrades, check:

- Minimum supported Java version of every library.
- Actual class-file major versions inside the JAR.
- Variant metadata or module-specific dependencies.
- Release notes regarding removed APIs.
- Target JDK of annotation processors, codegen plugins, and Java agents.
- Native library classifiers by OS/architecture.

### 12.2. Gradle variant matching can assist library selection

Gradle Module Metadata can publish attributes such as `org.gradle.jvm.version`, helping consumers choose variants compatible with the target JVM under Gradle configuration and rules.

However:

- Not every JAR publishes this metadata.
- Maven POMs carry a different metadata level than Gradle Module Metadata.
- A library can publish incorrect or missing metadata.
- A fat JAR or custom-built artifact can contain class versions unreflected in metadata.
- Actual runtimes must still be tested.

Do not treat variant selection as certification that the entire graph has been bytecode-scanned and verified compatible.

### 12.3. Maven dependency tree does not inspect class major versions

`mvn dependency:tree` is useful for seeing selected versions, yet by itself it does not analyze all bytecode. A dependency selected cleanly according to POMs can still contain classes that are too new.

Therefore, two independent steps are needed:

1. **Dependency resolution inspection:** identify the actual artifacts.
2. **Artifact bytecode inspection:** identify major versions and special characteristics such as multi-release.

## 13. Shading, fat JARs, and executable distributions

### 13.1. The final artifact can differ from the source module JAR

An `order-service` module may compile with `--release 17`, yet a `shadowJar` or Spring Boot packaging task bundles a dependency targeting Java 21.

Example:

```text
order-service classes      major 61
common-model classes       major 61
payment-provider classes   major 65
          |
          v
application-all.jar        contains both major 61 and 65
```

If deployed on Java 17, the problem remains even though the main module compiled cleanly.

Hence, final artifact verification must include:

- Main module classes.
- Shaded/relocated class entries.
- Nested dependency JARs when packaged in a nested layout.
- Runtime `lib/*.jar` in an application distribution.
- Dynamically loaded plugin JARs.
- Java agents or native launcher libraries if part of deployment.

### 13.2. Nested JARs and fat JARs need dedicated inspection

Some executable JARs do not unpack dependency classes to the root, containing nested archives instead:

```text
BOOT-INF/classes/...
BOOT-INF/lib/library-a.jar
BOOT-INF/lib/library-b.jar
```

A tool that only scans `*.class` directly at the root can miss every nested dependency. List or extract nested archives into an inspection area, or use a tool that supports that packaging format.

Do not merely run `javap` on the application's main class and conclude the complete artifact is compatible.

### 13.3. Bytecode transformers also have an impact

Shading, relocation, weaving, obfuscation, bytecode enhancement, and instrumentation can:

- Generate new class files.
- Preserve dependency bytecode major versions.
- Fail when processing newer class versions an older transformer does not understand.
- Modify `module-info.class` or multi-release entries.
- Create runtime proxies/adapters at a different bytecode level.

For example, outdated ASM, Byte Buddy, or Javassist libraries may not support new class-file versions. Update transformers/agents appropriately for the target JDK, check post-transform outputs, and test on the actual runtime.

### 13.4. Generated code and annotation processors

Some code generators emit **Java source** and hand it off to `javac`, allowing the compile task's `--release` to govern the resulting class output. Other tools, however, can write bytecode directly or copy precompiled JARs.

For every generated artifact, ask:

- Is source or bytecode generated?
- Which task is responsible?
- Which compiler/toolchain is used?
- Does it run under the main Gradle/Maven configuration?
- Is the artifact packaged into the release?

Do not assume generated classes follow `options.release` solely because the main `JavaCompile` task is configured properly.

## 14. Kotlin, Groovy, Scala, and polyglot builds

A multi-module repository often contains more than one JVM language. Each language has its own compiler options and plugin versions.

### 14.1. Kotlin JVM target

Kotlin Gradle DSL example using compiler options per a Kotlin Gradle Plugin version supporting this API:

```kotlin
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

kotlin {
    jvmToolchain(21)

    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}
```

`jvmToolchain(21)` selects the toolchain, whereas `jvmTarget` affects Kotlin bytecode. Check that Java source compilation targets and Kotlin targets align, and test on Java 17 if consumers must support it.

Syntax depends on the Kotlin Gradle Plugin version; do not copy into older projects without checking the installed plugin.

### 14.2. Groovy and Scala

Groovy/Scala have their own compilers and target options depending on plugins/versions. Classes they emit also carry class-file major versions and must match the consuming runtime.

Do not rely solely on Maven Compiler Plugin or Gradle `JavaCompile` targets to conclude Groovy/Scala bytecode is aligned. Identify the corresponding compile tasks and inspect class output.

### 14.3. Test fixtures and codegen

If a module publishes test fixtures, stubs, or generated clients, they may be loaded by another project running older Java. Thus, "test-only" is not enough to skip bytecode control if the artifact is distributed.

General principle: **any JVM artifact with independent consumers must declare its target and have its output verified**.

## 15. Inspecting class-file versions in artifacts

### 15.1. Viewing class major version with javap

Example after building:

```shell
javap -verbose -classpath path/to/common-model.jar \
    com.example.common.CustomerId
```

In the output, look for:

```text
major version: 61
```

This line shows the inspected class has major version 61, corresponding to Java 17. However, it does not confirm that every class in the JAR is at that level.

On Windows PowerShell, you can run on one line:

```powershell
javap -verbose -classpath "path/to/common-model.jar" com.example.common.CustomerId
```

If a class resides in a nested JAR, point to an appropriate classpath or extract the section to inspect first.

### 15.2. Inspecting JAR contents

```shell
jar --list --file path/to/common-model.jar
```

Check:

- `.class` files at root or in package directories.
- `module-info.class`.
- `META-INF/versions/...`.
- Nested JARs.
- Manifest and the `Multi-Release` attribute.

If you see `META-INF/versions/21`, do not automatically conclude the JAR is Java 17-incompatible before checking the manifest and base/versioned class selection.

### 15.3. Inspecting module descriptors

```shell
jar --describe-module --file path/to/library.jar
```

This command helps identify module metadata when present or automatic module status depending on the artifact. It is not a tool to check the class-file version of an entire JAR.

### 15.4. Using jdeps to inspect dependencies

```shell
jdeps --jdk-internals path/to/library.jar
```

`jdeps` helps check usage of JDK internal APIs that may break after migration. For MR-JARs, you can use the `--multi-release` option in supported analysis modes:

```shell
jdeps --multi-release 17 path/to/library.jar
```

`jdeps` does not replace a bytecode-major scan, nor does it see dependencies loaded dynamically via reflection or plugins.

## 16. Scanning major versions with Java

To check a non-MR-JAR, you can write a small program reading the header of `.class` entries:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class ClassVersionScanner {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ClassVersionScanner <jar> <maxMajor>"
            );
        }

        String path = args[0];
        int maxMajor = Integer.parseInt(args[1]);

        boolean failed = false;

        try (JarFile jar = new JarFile(path)) {
            var entries = jar.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();

                if (!entry.getName().endsWith(".class")) {
                    continue;
                }

                try (DataInputStream input =
                         new DataInputStream(jar.getInputStream(entry))) {

                    int magic = input.readInt();
                    int minor = input.readUnsignedShort();
                    int major = input.readUnsignedShort();

                    if (magic != 0xCAFEBABE) {
                        throw new IOException(
                            "Invalid class file: " + entry.getName()
                        );
                    }

                    if (major > maxMajor) {
                        failed = true;
                        System.err.printf(
                            "%s: major=%d minor=%d exceeds %d%n",
                            entry.getName(), major, minor, maxMajor
                        );
                    }
                }
            }
        }

        if (failed) {
            System.exit(1);
        }
    }
}
```

Example usage:

```shell
java ClassVersionScanner path/to/common-model.jar 61
```

If any class has a major version greater than 61, the program reports an error and returns exit code 1. This snippet is suitable for illustrating the header-inspection principle, yet has important limitations:

1. It does not handle MR-JAR semantics for `META-INF/versions/N`.
2. It does not scan nested JARs.
3. It does not distinguish preview classes with minor version 65535.
4. It does not evaluate Java platform APIs or third-party dependencies.
5. It does not verify signatures or test runtime behavior.

For production CI, use a governed plugin/tool or extend the scanner for the actual artifact format. **Do not apply the result of this simple scanner as a final verdict on MR-JARs.**

## 17. How to read a class file's version

If you want to understand the header directly:

```text
Offset    Bytes     Meaning
0         4         magic: CAFEBABE
4         2         minor_version
6         2         major_version
8         ...       constant pool and other sections
```

For example, major 61 is Java 17; major 65 is Java 21.

A class with a valid major version can still contain instructions or metadata not expected by the compiler/runtime if bytecode was improperly modified. Reading the header directly only answers the format-version question, not whether the class file is valid. JVM verification or full bytecode analysis tools are separate verification layers.

## 18. Bytecode compatibility in Maven: control mechanisms

### 18.1. Controlling at the compiler

Use a parent POM with a single source of truth for `maven.compiler.release` or a dedicated property referenced by the compiler plugin.

### 18.2. Controlling dependencies and artifacts

Use `dependencyManagement`/BOMs to choose dependency versions with appropriate Java support. Pin plugin versions and inspect the graph.

### 18.3. Controlling with Maven Enforcer or specialized plugins

The Maven Enforcer Plugin has rules supporting Maven/JDK version governance and the dependency graph. Certain bytecode-version checking rules for dependencies, such as `enforceBytecodeVersion`, come from **extra-enforcer-rules** or supplemental tools—not all belong to Maven Enforcer's default built-in rule set.

When configuring, check:

- Exact plugin and rule dependency versions.
- Include/exclude scopes.
- Test artifacts and optional dependencies.
- Multi-release JAR support.
- Nested archives or shaded outputs.
- Published minimum runtime.
- Handling rules for OS/architecture-specific dependencies.

Do not add a rule name to a POM without confirming which plugin dependency supplies that rule.

### 18.4. Maven profiles for multiple targets

Multiple profiles or module-specific properties may be needed when one repository releases both Java 17 and Java 21 artifacts. However, profiles increase cross-environment divergence risks if auto-activated by JDK/OS.

Prefer readable per-module target configuration tracked in version control. When using profiles, the release pipeline must record which profile was active and verify outputs for each variant.

## 19. Bytecode compatibility in Gradle: control mechanisms

### 19.1. Controlling JavaCompile

Use `java.toolchain` and `tasks.withType(JavaCompile).configureEach { options.release = ... }` per defined policy.

### 19.2. Controlling the dependency graph

With Gradle Module Metadata, variant selection via `org.gradle.jvm.version` can help avoid certain incompatible dependencies. Also use version constraints/BOM/dependency locking to keep the graph traceable.

Do not treat dependency locking as bytecode scanning: a lockfile stores selected versions, not guarantees about the class major versions of every JAR.

### 19.3. Controlling after packaging

Gradle can produce JARs, Shadow JARs, distribution ZIPs, or container images. Artifact verification must check the final output, not merely the `classes` task.

Example common Gradle tasks:

```shell
./gradlew :common-model:jar
./gradlew :order-service:distZip
```

These commands only illustrate build outputs and do not imply a default scanner is enabled. Attach artifact inspection steps to the pipeline if the product requires bytecode-level certification.

### 19.4. Metadata when publishing libraries

When published, a Gradle `java-library` module can carry target JVM information via Gradle Module Metadata. This helps Gradle consumers select compatible variants in supported scenarios.

However, Maven users may only receive the POM/JAR without consuming full Gradle metadata. Thus, explicitly documenting the minimum Java version in release notes and inspecting the actual JAR remain necessary.

## 20. Cases easily overlooked

### 20.1. Java agents

An application may use `-javaagent:agent.jar`. An agent is a separate JVM artifact loaded very early during startup. If the agent has too new a major version or its internal ASM library does not understand the application's bytecode, the runtime can fail before the main class runs.

### 20.2. Annotation processors

Processors run during compilation and generally need compatibility with the **compiler's JDK**, not necessarily the same target release as the output classes.

For instance, a processor running on JDK 21 can use Java 21 APIs to analyze the AST, yet must ensure the sources/classes it generates remain valid under `--release 17` if targeting a Java 17 library.

### 20.3. Test runners and mocking frameworks

JUnit, Mockito, Byte Buddy, or code coverage agents may require a different minimum JDK from the main library. They are not necessarily published in the runtime artifact, yet they govern whether tests can run on JDK 17 in CI.

Separate "test tool fails to run on Java 17" from "library fails to run on Java 17". If a library commits to Java 17 support while the modern test stack requires Java 21, a dedicated compatibility test suite running on Java 17 is needed.

### 20.4. Generated clients and stubs

OpenAPI/GraphQL/gRPC generators can emit Java source or bytecode. If a generation step switches framework output to code using Java 21 APIs, `--release 17` usually catches incompatible source APIs. However, if a precompiled major 65 generated JAR is placed directly into the distribution, the issue may surface only at runtime.

### 20.5. Runtime plugin loading

An application may run fine until loading plugins via `ServiceLoader`, `ClassLoader`, or a script engine. Plugin artifacts have their own lifecycles and compatibility matrices; they must be included in the application's dependency closure.

### 20.6. JNI and native dependencies

Bytecode major versions say nothing about native library loadability. A major 61 JAR can rely on a JNI library built only for Linux x86_64 or an incompatible native API. When migrating JDK and OS simultaneously, native compatibility is an independent test axis.

### 20.7. Serialized data and schemas

Two modules having the same bytecode target do not guarantee compatibility for Java Object Serialization, JSON, Avro, or Protocol Buffers. If records/enums/domain models change, consumers may fail to read new data even when both runtimes are Java 17.

Distinguish **bytecode compatibility** from **data protocol compatibility**.

## 21. "Same major level" can still fail to run together

For example, two artifacts are both major 61, yet one module changed its public API:

```text
library A v1:
  public int calculate(int value);

library A v2:
  public long calculate(long value);
```

A consumer compiled against v1 may throw `NoSuchMethodError` when run against v2 if the method signature changed in a binary-incompatible way. Both can still use Java 17 bytecode.

Similarly:

- `NoClassDefFoundError` when a dependency is missing at runtime.
- `IllegalAccessError` when access modifiers change.
- `InaccessibleObjectException` when reflective access is blocked by JPMS.
- `ServiceConfigurationError` when an SPI provider is invalid.
- `ClassCastException` when class identity differs across loaders.
- `UnsatisfiedLinkError` when a native library is missing/incorrect.

Therefore, a solid pipeline inspects class major versions **and** runs integration tests on the real dependency graph.

## 22. Organizing a multi-runtime test matrix

### 22.1. Common model: Java 17 base libraries, Java 21 services

| Artifact | Compiler JDK | Target release | Test runtime |
|---|---:|---:|---|
| `common-model.jar` | 21 | 17 | Java 17 and 21 |
| `pricing-core.jar` | 21 | 17 | Java 17 and 21 |
| `payment-adapter.jar` | 21 | 21 | Java 21 |
| `order-service.jar` | 21 | 17 | Java 17 |
| `billing-worker.jar` | 21 | 21 | Java 21 |

This is an illustrative matrix. If the product runs Java 25, add appropriate JDK 25 tests and verify dependency support.

### 22.2. Testing the minimum runtime is most critical

If a library advertises Java 17 as its minimum, running tests only on Java 21 is not enough. Java 21 supports more APIs/class versions and can mask errors.

A worthwhile job flow:

```text
Compile with JDK 21 + --release 17
          |
          v
Assemble JAR and dependencies
          |
          v
Run compatibility tests on JDK 17
          |
          v
Run regression tests on JDK 21
```

If a project must run on Java 17 while the current test framework only supports Java 21, consider a smoke/compatibility suite using a Java 17-compatible test framework rather than skipping minimum-runtime testing.

### 22.3. Building with every JDK is not strictly required

`--release` and toolchains enable a newer compiler to produce artifacts targeting older releases. Still, running tests on actual runtimes remains essential. You can choose a strategy:

- One pinned compiler toolchain for building.
- Multiple runtime JDKs for testing the artifact.
- An OS/architecture matrix if native dependencies exist.
- A job inspecting artifact bytecode and published metadata.

Avoid creating unnecessary combinations; base the matrix on the versions the product commits to support.

## 23. Migrating from Java 8/11/17 to Java 21/25 in a multi-module build

### Phase 1: Inventory modules and consumers

List:

- Name and type of each Maven/Gradle module.
- Published artifacts.
- Applications consuming each artifact.
- Minimum runtime JDK of each consumer.
- Build JDK, compiler plugin, Gradle/Maven version.
- Transitive dependencies and native artifacts.
- Modules containing JPMS descriptors or MR-JARs.
- Dynamically loaded plugins and published test fixtures.

Do not start by bumping every module to the same highest `release` simply because the CI JDK was upgraded.

### Phase 2: Establish target policy

Define:

```text
Shared libraries for old consumers -> Java 17
New service-only implementation    -> Java 21
Application running on Java 17     -> Java 17 closure
Application running on Java 21     -> Java 21 closure
```

If a single library needs Java 21 APIs while still having Java 17 consumers, consider:

- Splitting a Java 17 base API from a Java 21 implementation.
- Creating separate artifacts.
- Using an MR-JAR if genuinely suitable and tested.
- Raising consumer runtime requirements according to a release plan.

Do not assume the compiler can "back-translate" Java 21 APIs down to Java 17 without design changes.

### Phase 3: Standardize build configuration

For Maven:

- Ensure child modules genuinely inherit the parent.
- Pin `maven-compiler-plugin`.
- Centralize `release` via a property/convention.
- Allow only documented overrides.
- Manage toolchains and profiles.

For Gradle:

- Pin the Gradle Wrapper.
- Use toolchains.
- Use `options.release` for Java compilation.
- Apply a convention plugin or controlled shared configuration.
- Align Kotlin/Groovy/Scala compiler targets.
- Manage variants and dependency locks.

### Phase 4: Upgrade dependencies intentionally

Pay special attention to frameworks, bytecode libraries, JNI, annotation processors, test runners, and Java agents.

If a new dependency requires Java 21 while a shared library must support Java 17, pick another version or isolate the dependency/module. Never work around it by leaving `--release 17` in the main module while ignoring the dependency's major 65 classes.

### Phase 5: Build and inspect artifacts

For each published module:

1. Build with the pinned toolchain.
2. Inspect the base artifact's class major version.
3. Check JPMS/MR-JAR metadata if applicable.
4. Check transitive dependencies.
5. Check fat/nested/shaded artifacts if those are the actual outputs.
6. Confirm module/variant metadata advertises the right minimum JVM.
7. Record checksums and versions of inspected artifacts.

### Phase 6: Test on target runtimes

Run:

- Module unit tests.
- Cross-module integration tests.
- Service startup smoke tests.
- Runtime tests on the lowest supported JDK.
- Dynamic plugin/SPI tests.
- Serialization, reflection, and native integration tests where applicable.
- Tests inside the actual deployment container or OS.

### Phase 7: Release, canary, and rollback

Ensure published module versions are unambiguous, dependency graphs are controlled, and artifacts are never overwritten. When rolling back, reselect the exact tested set of artifacts rather than rolling back only the main application JAR.

If the new version changed data schemas or protocols, rolling back bytecode is insufficient; a separate data compatibility plan is required.

## 24. Common failures and remediation

### 24.1. `UnsupportedClassVersionError` occurs only in production

**Symptom:** CI running Java 21 passes, production Java 17 reports class-file major 65.

**Possible cause:** a module or dependency was compiled targeting 21; CI did not run on the minimum runtime.

**Resolution:** identify the JAR containing the class, inspect major versions and the resolved dependency graph, lower the target if valid or upgrade runtime/change dependencies per policy, and add tests on Java 17.

### 24.2. Parent POM sets release 17 yet a child outputs major 65

**Cause:** the child does not inherit the parent, overrides plugin configuration, activates a different profile, or uses a plugin/custom compiler ignoring shared configuration.

**Resolution:** inspect the effective POM, confirm the toolchain and actual compiler command, update the source of truth, and scan JAR outputs.

### 24.3. Gradle toolchain 21 produces JARs incompatible with Java 17

**Cause:** `java.toolchain` specifies the compiler, yet `JavaCompile.options.release` is unset or overridden.

**Resolution:** set `options.release = 17` in the appropriate convention, verify bytecode output, and test on Java 17.

### 24.4. Gradle build reports inability to select a dependency variant

**Symptom:** dependency resolution reports that an artifact requires a higher JVM than the consumer's target.

**Cause:** Gradle Module Metadata declares an incompatible JVM target or other variant attributes mismatch.

**Resolution:** read the library's variant information and minimum Java requirement, pick a compatible version/artifact, and do not disable compatibility checks just to "turn the build green" when production actually runs an older JDK.

### 24.5. Maven build succeeds yet runtime fails with missing method

**Cause:** despite the same major version, compile and runtime resolved different API versions, or a dependency changed its ABI.

**Resolution:** compare the dependency tree, binary compatibility, and runtime graph. Do not rely on class major versions alone.

### 24.6. MR-JAR flagged for containing classes with overly new major versions

**Cause:** the scanner does not understand versioned entries or the JAR was packaged improperly.

**Resolution:** inspect manifest `Multi-Release: true`, base entries, `META-INF/versions/N`, and per-N target rules. Test on the JDKs the artifact supports.

### 24.7. Fat JAR contains newer bytecode despite an older target on the main module

**Cause:** shading/nested dependencies contain classes with a higher major version.

**Resolution:** scan the final artifact and all nested JARs, replace the dependency or upgrade the runtime. Do not inspect only `build/classes/java/main`.

### 24.8. Tests fail on JDK 17 while the runtime library remains compatible

**Possible cause:** the test runner, mocking/coverage agent, or test-only dependency requires Java 21.

**Resolution:** separate test-tool compatibility from main-artifact compatibility, and use a JDK 17-compatible test suite to verify the library contract.

### 24.9. `module-info.class` causes errors when running older Java

**Cause:** the JPMS descriptor or classes were packaged improperly for the baseline JDK.

**Resolution:** determine whether the application runs on classpath or module path; if Java 8 support is required, consider a compliant MR-JAR or a separate artifact and check layout on the lowest JDK.

### 24.10. Dependency lock pins a release that no longer supports the target JDK

**Cause:** a lockfile only freezes versions; it does not make an artifact compatible.

**Resolution:** select and test a supported dependency version, update the lock under control, and save diffs and compatibility test results.

## 25. Recommended CI gates for multi-module repositories

A pipeline can be structured as follows:

```text
Checkout immutable commit
       |
       v
Pin Maven/Gradle + compiler JDK
       |
       v
Resolve/verify dependencies
       |
       v
Compile every module with declared target
       |
       v
Package normal/shaded/nested artifacts
       |
       v
Inspect class-file major + MR-JAR rules
       |
       v
Check dependency closure of each deployable
       |
       v
Test on minimum supported JDK
       |
       v
Integration test on target JDK/OS
       |
       v
Publish immutable artifacts with metadata
       |
       v
Canary + monitoring + rollback readiness
```

### 25.1. Per-module gate

A machine-readable table or CI report may record:

| Module | Policy target | Observed major | Dependency exceeds threshold? | Result |
|---|---:|---:|---|---|
| `common-model` | 17 | 61 | No | Pass |
| `pricing-core` | 17 | 61 | No | Pass |
| `nextgen-payment` | 21 | 65 | No | Pass |
| `order-service` | 17 | 61 | Yes (depends on major 65) | Fail |

The table only illustrates verification results. For MR-JARs, reports must distinguish base and versioned classes rather than keeping only a single maximum major across the entire archive.

### 25.2. Gate on deployed artifacts

If a product publishes container images, inspect the image contents or at least the set of JARs and entrypoint packaged into the image—not solely the JARs in `build/libs` prior to packaging.

If using an application distribution, check every JAR in `lib` and ensure executable startup scripts point to the right JDK. If using dynamic plugins, add a plugin compatibility gate.

### 25.3. Keeping reports for traceability

Save with each release:

- Compiler JDK vendor/version.
- Gradle/Maven version.
- Target release per module.
- Dependency graph/lock state.
- Artifact checksums.
- Class-file major reports.
- Test matrix and runtime versions.
- Source revision and provenance.

This information helps determine whether a production error stems from incompatible bytecode or from another API/dependency change.

## 26. Practice exercises

### Exercise 1: Analyze a bytecode matrix

Given the structure:

```text
shared-api        major 61
reporting-core    major 65
order-service     major 61
billing-worker    major 65

order-service -> shared-api -> reporting-core
billing-worker -> shared-api
```

The first service runs on Java 17; the second runs on Java 21.

Identify which module can trigger `UnsupportedClassVersionError` in `order-service`, and why `order-service` having major 61 is not enough to prove compatibility.

### Exercise 2: Fix Maven configuration

A parent POM sets `maven.compiler.release=17`, yet `payment-adapter` requires Java 21. Design a `java.release` property referenced by the compiler plugin, allowing the child to override it to 21 while other children remain on 17. Then describe how to use the effective POM and `javap -verbose` to verify the outcome.

### Exercise 3: Fix Gradle configuration

A multi-project Gradle build uses `java.toolchain = 21` at the root. All modules are expected to support Java 17 except `billing-worker`. Add shared `JavaCompile.options.release` configuration and a controlled override mechanism, then propose how to verify artifacts.

### Exercise 4: Inspect a shaded JAR

Module `order-service` compiles at major 61, yet its fat JAR bundles a transitive dependency at major 65. Describe how to:

1. Identify the dependency bringing in that library.
2. Determine whether the dependency is actually needed at runtime.
3. Try a Java 17-compatible version or split the module.
4. Scan the shaded/nested artifact after building.
5. Run the service on Java 17 in CI.

### Exercise 5: Multi-release JAR

A library supporting Java 8, 17, and 21 wants to optimize implementations on newer runtimes.

Sketch out the base entries, `META-INF/versions/17`, and `META-INF/versions/21`, along with the build/test rules required so Java 8 still uses the base classes.

## 27. Checklist before completing migration

### Architectural policy

- [ ] Every module has an owner and a declared target Java version.
- [ ] Minimum runtime of each deployable artifact is defined.
- [ ] Shared libraries do not raise their target beyond older consumers' requirements.
- [ ] Dependency graphs do not introduce artifacts with overly new major versions into lower runtimes.
- [ ] Explicit decisions are documented where Java 17 and Java 21 modules must coexist.

### Maven

- [ ] Child modules inherit the parent POM properly.
- [ ] `maven-compiler-plugin` has an explicit version and release.
- [ ] Property overrides are not shadowed by hard-coded plugin configuration.
- [ ] Toolchains/JDKs and Maven profiles are governed.
- [ ] Effective POMs for critical modules are verified.
- [ ] BOM/`dependencyManagement` does not introduce libraries exceeding the runtime floor.

### Gradle

- [ ] Wrapper and JDK toolchains are pinned.
- [ ] `JavaCompile.options.release` is configured per policy.
- [ ] Modules with special targets are declared intentionally.
- [ ] Java, Kotlin, Groovy, Scala, and generated bytecode are verified separately.
- [ ] Gradle variants/dependency metadata match the minimum JVM.
- [ ] Lockfiles, transitive graphs, and runtime configurations are reviewed.

### Artifacts and runtime

- [ ] Major versions inside released JARs are verified.
- [ ] Shaded/nested archives and runtime `lib/*.jar` are scanned.
- [ ] `module-info.class` and MR-JARs are handled in proper context.
- [ ] Java agents, plugins, and native dependencies are accounted for in deployment.
- [ ] Artifacts are tested on the lowest committed JVM.
- [ ] Integration tests verify API/binary/behavior compatibility, not just class major versions.
- [ ] Artifact reports and checksums are stored with build metadata.
- [ ] A rollout/rollback plan matching runtime and dependency versions is in place.

## Conclusion

In a multi-module Maven or Gradle project, **aligning bytecode levels** does not mean forcing every module onto the same JDK or the same class-file major version. What matters is that each artifact declares a clear minimum runtime and the application's entire dependency closure is compatible with that runtime. A library built with JDK 21 can still release Java 17 bytecode via `--release 17`; conversely, a major 61 main module can still fail on Java 17 if its fat JAR or a transitive dependency contains major 65 classes.

To migrate safely, manage release targets centrally in a Maven parent POM or Gradle convention plugin, distinguish toolchains from target bytecode, inspect actual outputs and dependencies, handle JPMS/multi-release JARs separately, and run tests on the lowest supported JDK. Combining bytecode inspection, dependency management, and runtime integration tests catches errors before deployment, letting old and new modules evolve along a roadmap without breaking consumers.
