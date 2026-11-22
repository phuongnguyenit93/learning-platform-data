# Dependency declaration and corresponding requires

In Java applications using the Java Platform Module System (JPMS), the same library often appears in two places: **a dependency declaration in the build tool** (Maven or Gradle) and **a `requires` declaration in `module-info.java`**. These two declarations are closely related, yet not synonymous.

- The build tool decides **which artifact, which version, and from which repository** is placed on the compile classpath, module path, runtime, or test path.
- The module descriptor decides **which named module reads which named module**, which packages are exported or opened for reflection, and which modules consume or provide services.
- The compile or run command must supply artifacts with the right module name, version, and path so the module resolution system can verify that contract.

When migrating a project from the classpath to the module path, merely adding a dependency to `pom.xml` or `build.gradle` is often insufficient. Conversely, merely adding `requires` without having the corresponding artifact on the module path will cause a `module not found` error.

## 1. Two declaration layers answer different questions

Suppose an application uses a library named `acme-json`. In Maven, a dependency can be declared as:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-json</artifactId>
    <version>2.4.0</version>
</dependency>
```

Here, `com.acme:acme-json:2.4.0` is the **artifact coordinate**. It enables Maven to download the right JAR file and its associated dependencies.

In the application's `module-info.java`:

```java
module com.acme.app {
    requires com.acme.json;
}
```

`com.acme.json` is the **JPMS module name**, not the Maven `groupId`, `artifactId`, or JAR filename. If the artifact has a `module-info.class` descriptor, the module name comes from that descriptor. For automatic modules, the name may come from the manifest or be derived from the JAR filename.

A build works when both configuration layers align: the build tool supplies the JAR containing module `com.acme.json`, and the application descriptor declares a readability relationship to that module.

| Question | Responsible configuration |
|---|---|
| Which library version is used? | Maven/Gradle dependency declaration |
| Which repository is the library fetched from? | Maven/Gradle repositories and dependency resolution |
| Which compile/module path does the artifact go on? | Compiler plugin or build configuration |
| Which modules does the application's named module read? | `requires` in `module-info.java` |
| Which packages can consumer modules import? | `exports` of the providing module |
| Which packages can frameworks reflect deeply into? | `opens` of the module containing the package |
| Which service providers can be discovered? | `uses`, `provides`, and the module graph |

**Core rule:** dependency declarations select **artifacts**; `requires` declares **readability** in the module graph.

## 2. Minimal example with an application module and a library module

Suppose there is a library module:

```java
// module-info.java of the library
module com.acme.greeting {
    exports com.acme.greeting.api;
}
```

Public class:

```java
package com.acme.greeting.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
```

Application using the library:

```java
package com.acme.app;

import com.acme.greeting.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.hello("JPMS"));
    }
}
```

Application descriptor:

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

Maven or Gradle still needs to fetch the right JAR for `com.acme.greeting`. When compiling module `com.acme.app`, `javac` inspects the descriptor and verifies:

1. Does module `com.acme.greeting` exist in the observable set of modules?
2. Does module `com.acme.app` have permission to read it via `requires`?
3. Has package `com.acme.greeting.api` been exported to the consumer?
4. Do the referenced class and method have valid visibility?

Having a build dependency present while missing `requires` can still cause a package not visible error. Conversely, having a valid `requires` while missing the JAR leads to a module not found error.

## 3. Declaring dependencies in Maven

With a standard Maven structure:

```text
app/
├── pom.xml
└── src/main/java/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Minimal `pom.xml` example:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>app</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeting</artifactId>
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

Maven handles fetching `com.acme:greeting:1.0.0`; `module-info.java` in the application still needs `requires com.acme.greeting;` if source code accesses APIs of this named module.

The Java release version and plugin version in the example are illustrative configurations only. Real projects should use plugin versions compatible with the JDK/toolchain and organizational build policies.

Common Maven scopes:

| Maven scope | Normal build meaning | Notes when designing for JPMS |
|---|---|---|
| `compile` (default) | Dependency needed during compile; typically also in the runtime dependency set | If named module sources reference that module, usually declare `requires` |
| `provided` | Present at compile/test time, expected to be supplied by the runtime environment | May correspond to `requires static` in certain optional designs; not an automatic mapping |
| `runtime` | Needed at runtime, not necessarily needed to compile main sources directly | Do not add `requires` solely because a JAR is a runtime dependency; check how it is used |
| `test` | Serves tests | Usually does not belong in the production descriptor |
| `system` | Depends on a specific local file, generally discouraged | Does not alter JPMS rules |

A Maven scope is not a JPMS directive. A `runtime` dependency may be a driver discovered by `ServiceLoader`; the application does not necessarily have a `requires` on the implementation module.

## 4. Declaring dependencies in Gradle

With the Gradle Java plugin or Java Library plugin, a Groovy DSL example:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    modularity.inferModulePath = true
}

dependencies {
    implementation 'com.acme:greeting:1.0.0'
}
```

If sources contain `module-info.java`, the build must use the proper module path for modular dependencies. Gradle can infer the module path in supported configurations when `inferModulePath` is enabled; inspect the actual compile command when non-modular JARs or custom configurations are involved.

The descriptor remains:

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

Common Gradle configurations:

| Configuration | Role | Typical relationship with descriptor |
|---|---|---|
| `implementation` | API/implementation used by the project to compile and run | `requires` when module code directly needs the named module |
| `api` (Java Library plugin) | Dependency that is part of the API consumers compile against | May accompany `requires transitive` if the public API actually exposes types from that module |
| `compileOnly` | Dependency needed only at compile time | May use `requires static` if runtime permits the module to be absent |
| `runtimeOnly` | Dependency needed only at runtime | Common for service providers or dynamically loaded implementations |
| `annotationProcessor` | Library containing annotation processors run at compile time | Separate configuration; does not automatically need `requires` in the application module |
| `testImplementation` | Library serving tests | Not synonymous with production application module dependencies |

**Do not mechanically equate** `api` with `requires transitive` or `compileOnly` with `requires static`. The two systems categorize dependencies for different purposes; alignment still depends on the public API and runtime behavior.

## 5. How does requires differ from requires transitive?

Suppose `com.acme.service` provides a public API using the `Customer` type from `com.acme.model`:

```java
// In com.acme.model
package com.acme.model;

public record Customer(String id) {
}
```

```java
// In com.acme.service
package com.acme.service.api;

import com.acme.model.Customer;

public interface CustomerService {
    Customer findById(String id);
}
```

Model module descriptor:

```java
module com.acme.model {
    exports com.acme.model;
}
```

Service module descriptor:

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

Application:

```java
module com.acme.app {
    requires com.acme.service;
}
```

`requires transitive com.acme.model` makes modules that read `com.acme.service` also read `com.acme.model`. This is useful because `CustomerService`'s public signature contains the `Customer` type from the model module.

When publishing a library, the Gradle Java Library plugin typically declares the model dependency under `api` rather than `implementation` so consumers have that dependency in their compile graph:

```groovy
dependencies {
    api 'com.acme:model:1.0.0'
}
```

However, you still must write `requires transitive` in the descriptor if you want JPMS to propagate readability as shown above. Gradle `api` does not automatically replace directives in `module-info.java`.

When the public API does **not** expose types from another module, preferring regular `requires` is usually sufficient. Overusing `requires transitive` exposes unnecessary dependencies to consumers as part of the API contract.

## 6. requires static and compile-only dependencies

`requires static` expresses a dependency that is mandatory at compile time but optional at runtime for the current module to resolve.

For example, an application using annotations only at compile time:

```java
module com.acme.app {
    requires static com.acme.annotations;
}
```

Gradle:

```groovy
dependencies {
    compileOnly 'com.acme:annotations:1.0.0'
}
```

Maven may use `provided` when a dependency is supplied externally by the runtime environment, yet the semantics of Maven `provided` and `requires static` are not identical. Maven `provided` may still require the library at runtime via a container, whereas `requires static` lets JPMS resolve the module even when the depended-on module is absent.

**Important:** `requires static` does not make the library's classes appear automatically at runtime. If a runtime code path attempts to load a class from an absent optional module, the application can still fail to load the class. Use this form only when the architecture genuinely tolerates the dependency being absent at runtime.

You should also avoid using `requires static` merely to shrink the graph if the library is always needed for runtime logic.

## 7. Runtime-only dependencies and ServiceLoader

Some implementations are used only through the Java Service Provider Interface (SPI). The consumer knows the service interface, without importing the implementation class.

SPI module:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Consumer:

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.ReportExporter;
}
```

Provider:

```java
module com.acme.export.csv {
    requires com.acme.spi;
    provides com.acme.spi.ReportExporter
        with com.acme.export.csv.CsvReportExporter;
}
```

In Gradle, the provider implementation can be a `runtimeOnly` dependency at the build layer:

```groovy
dependencies {
    implementation 'com.acme:spi:1.0.0'
    runtimeOnly 'com.acme:export-csv:1.0.0'
}
```

However, `runtimeOnly` alone **does not guarantee** the provider module is resolved by JPMS. The provider must be on the module path and included in the graph appropriately, such as by selecting it as a root with `--add-modules`, choosing roots when creating a `ModuleLayer`, or performing service binding.

Example launch command requesting the provider module:

```shell
java --module-path mods \
  --add-modules com.acme.export.csv \
  -m com.acme.app/com.acme.app.Main
```

Do not add `requires com.acme.export.csv;` to the consumer merely so ServiceLoader knows the provider; consumers should depend on the service interface, not couple directly to an implementation.

## 8. Annotation processors are not application runtime dependencies

An application module may use annotations and an annotation processor during the build. These two components should be distinguished:

- Annotation API: sources may import annotation types; this is a compile dependency.
- Annotation processor: a tool loaded by `javac` to generate sources/code; this is a **compilation-phase** dependency.

Gradle:

```groovy
dependencies {
    compileOnly 'com.acme:annotations:1.0.0'
    annotationProcessor 'com.acme:codegen-processor:1.0.0'
}
```

If the annotation API is a named module and sources import it, the descriptor may contain `requires static com.acme.annotations;`. However, the application module **does not need `requires` on the processor module merely because the processor runs at build time**.

For the Maven Compiler Plugin, processor path configuration can be declared explicitly (depending on plugin version) in `annotationProcessorPaths`. For modular processors, there is also the `--processor-module-path` mechanism.

Do not ship processors along with dependencies like template engines or JavaPoet into production runtime if the application does not actually need to invoke them.

## 9. Maven/Gradle artifact names are not necessarily module names

This is one of the most common sources of errors when creating `module-info.java`.

Maven example:

```text
groupId    = org.example
artifactId = useful-utils
version    = 3.2
```

The actual JPMS module name might be:

```text
org.example.utilities
```

rather than `useful.utils`, `org.example.useful.utils`, or a string derived from `artifactId`.

Sources determining the module name in practical precedence order:

1. `module-info.class` of an explicit module.
2. `Automatic-Module-Name` in the manifest for an automatic module.
3. A name derived from the JAR filename if neither of the two sources above exists and the JAR is used as an automatic module.

You can check with:

```shell
jar --describe-module --file libs/useful-utils-3.2.jar
```

The output may indicate either an automatic module or an explicit module descriptor. Use the exact name displayed in `requires`.

To view modules actually present in the current environment:

```shell
java --module-path libs --list-modules
```

However, the list of **observable** modules does not mean all of them are resolved in a given application run. Use `--show-module-resolution` when diagnosing the graph of a specific run.

## 10. Automatic modules assist migration but have limitations

A JAR without a descriptor placed on the module path is typically treated as an automatic module. An application's named module can declare `requires` on an automatic module if the module name can be determined and packages do not conflict.

Example:

```java
module com.acme.app {
    requires legacy.utilities;
}
```

During a transition period, automatic modules allow using legacy libraries without creating descriptors for them yourself. Yet there are limitations:

- The module name can be unstable if derived from the JAR filename.
- Every package of an automatic module is broadly exported, making encapsulation weak.
- Multiple JARs from the classpath era may contain split packages and conflict when moved together onto the module path.
- `jlink` does not support linking automatic modules the way it links explicit modules.

Therefore, do not assume a dependency declared in Maven/Gradle always has a stable module name. When selecting dependencies for long-term modular applications, prefer artifacts with explicit descriptors or clear module name metadata.

## 11. When the dependency is present yet javac reports package is not visible

A typical scenario:

```java
module com.acme.app {
    requires com.acme.library;
}
```

The compiler reports:

```text
package com.acme.library.internal is not visible
(package ... is declared in module com.acme.library,
 which does not export it)
```

This is not a failure of Maven/Gradle to download the artifact. The module was found, but the package in the library has not been exported to the application.

A descriptor such as:

```java
module com.acme.library {
    exports com.acme.library.api;
}
```

only exposes the package `com.acme.library.api`. Adding dependencies in the build file or adding another `requires` will not expose `com.acme.library.internal`.

Use public APIs in exported packages or ask the library to expose a proper API. `--add-exports` can assist temporary migration, but creates reliance on the library's internal structure.

Similarly, `opens` is for deep reflection at runtime, not a replacement for `exports` when importing and calling APIs directly.

## 12. When requires is valid yet the build reports module not found

Example:

```text
error: module not found: com.acme.greeting
```

Common causes:

1. The build tool has not downloaded or supplied the right JAR to the compiler input.
2. The JAR is on `--class-path` instead of `--module-path`.
3. The module name in `requires` does not match the descriptor/automatic module name.
4. The dependency version was overridden, excluded, or resolved to a different artifact.
5. The dependency is an optional module, yet the compile configuration does not provide it.
6. The package/module path is configured differently between the IDE and CI.

Diagnosis:

```shell
jar --describe-module --file libs/com.acme.greeting.jar
```

```shell
javac --module-path mods:libs -d out \
  src/module-info.java \
  src/com/acme/app/Main.java
```

The example above uses a colon for Linux/macOS; Windows uses a semicolon. In an IDE or build tool, inspect the actual `javac` arguments generated rather than looking only at the dependency declaration.

## 13. Test dependencies and the module descriptor

Test libraries such as JUnit, mocking frameworks, or test utilities are typically declared with Maven `test` scope or Gradle `testImplementation`.

That **does not mean** you should add `requires` for them in `com.acme.app`'s production descriptor. If test code is compiled in a separate module, use an appropriate test module descriptor. If test code is patched into the production module, the test runner configuration may need `--patch-module`, `--add-reads`, or `--add-opens` to execute tests.

Gradle example:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
```

The dependency above serves tests; the application's module descriptor does not automatically need `requires org.junit.jupiter.api;` just because test sources import JUnit.

The goal is to keep the production module reflecting production dependencies rather than pulling in the entire suite of development tools.

## 14. Dependency resolution, module resolution, and runtime images

Three types of “resolution” are easily confused:

**Build dependency resolution** by Maven/Gradle: selects specific artifacts and versions from the dependency graph.

**JPMS module resolution**: starts from root modules, resolves `requires`, validates module graph constraints, and may add providers via service binding when requested.

**Runtime image linking** by `jlink`: creates an image containing a selected set of modules and required dependencies.

A dependency downloaded by Maven/Gradle does not guarantee that module is resolved at runtime. A module declaring `requires` also does not guarantee the corresponding JAR is present if deployment omitted the artifact.

When packaging with `jlink`, check that the application and dependencies have suitable module descriptors. Automatic modules or classpath-only dependencies may require a different packaging strategy.

You can inspect the runtime graph:

```shell
java --show-module-resolution \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
```

If using a custom runtime image, run the executable inside the image and check `--list-modules` to verify which modules are actually packaged.

## 15. Process for reconciling dependencies with requires

A practical workflow for each application or library module:

1. **List imports and public APIs** of the module: identify which module each type belongs to.
2. **Check build dependencies**: the exact artifacts and versions declared in Maven/Gradle.
3. **Read module names from artifacts** using `jar --describe-module`.
4. **Choose the right requires**: `requires` for normal dependencies; `requires transitive` when readability must propagate due to exposed APIs; `requires static` if a compile-time dependency is genuinely optional at runtime.
5. **Review special cases**: service providers, annotation processors, test libraries, and reflection-only dependencies.
6. **Verify actual module paths** passed to `javac` and `java` commands.
7. **Compile and test** with the exact artifact/dependency versions that will be deployed.
8. **Use `jdeps` and resolution output** to catch mismatches between code, descriptors, and the graph.

Do not force every build-tool dependency into a `requires` directive. Some libraries exist only for testing, code generation, service providing, or resource delivery. What matters is identifying each dependency's **intended usage**.

## 16. Summary table of typical cases

| Case | Common build dependency | Corresponding JPMS |
|---|---|---|
| Source uses public API from module X | Maven compile / Gradle implementation | `requires X;` |
| Library exposes API containing types from module X | Maven compile or Gradle api | `requires transitive X;` when readability must propagate |
| Source uses annotations needed only at compile time | Maven provided / Gradle compileOnly | `requires static X;` if X is a named module needed for compile |
| Implementation loaded via ServiceLoader | Maven runtime / Gradle runtimeOnly | Consumer `uses` service type; provider `provides` and must be resolved |
| Annotation processor running at build time | Maven compiler processor config / Gradle annotationProcessor | Does not automatically need `requires` on processor in application module |
| Library used only in tests | Maven test / Gradle testImplementation | Do not put in production descriptor solely for tests |
| Framework reads private fields via reflection | Usually runtime/implementation dependency | `opens package to framework.module;` when deep reflection is needed |
| Java SE APIs in `java.sql` or `java.logging` | Provided by JDK, no separate Maven artifact | `requires java.sql;` or `requires java.logging;` |

Remember that the table describes **typical** relationships rather than automatic 1-to-1 conversions. JPMS declarations must be grounded in the actual modules containing the APIs and how the code uses them.

## 17. Common errors and troubleshooting

| Symptom | Possible cause | How to fix |
|---|---|---|
| `module not found` | Artifact not placed on module path or wrong module name | Determine actual module name, check compiler/runtime paths |
| `package ... is not visible` | Missing `requires` or package not exported | Check consumer and provider descriptors |
| `reads package ... from both ...` | Split package / conflict between modules | Remove duplicate dependency, relocate package, or merge modules |
| Compiles yet missing classes at runtime | Build and runtime dependency sets differ | Synchronize artifact/runtime graph, check `requires static` |
| ServiceLoader finds no provider | Provider not resolved or missing `provides` | Check `uses`, `provides`, root modules, and service binding |
| Reflection fails | Package not opened to the framework | Use appropriate `opens`, avoid over-exporting |
| Runs in IDE yet fails in CI | IDE and build tool classify classpath/module path differently | Check toolchain, compiler args, and dependency resolution |
| Jlink rejects a dependency | Dependency is an automatic module or incompatible with linking | Use an explicit modular artifact or change packaging strategy |

## 18. Key principles to remember

- Maven/Gradle manage **artifacts and versions**; JPMS manages **module readability and encapsulation**.
- Do not derive a module name directly from Maven `groupId`, `artifactId`, or filename.
- Use `requires transitive` only when readability must propagate to consumer modules.
- `requires static` permits a dependency to be absent at runtime resolution, yet runtime code must still avoid referencing absent classes.
- `runtimeOnly` dependencies do not automatically guarantee providers are resolved in JPMS.
- Annotation processors and test libraries are generally not production dependencies of the application module.
- `requires` does not replace `exports`; `opens` addresses deep reflection needs.
- Inspect the actual module path, JAR descriptors, `jdeps`, and `--show-module-resolution` when build and runtime disagree.

**Conclusion:** Declaring dependencies accurately in a modular application requires combining two perspectives. The build tool answers “which JAR files are supplied at build/run time”, while `module-info.java` answers “which modules are read and which APIs are exposed under the JPMS contract”. When both layers are reconciled using real module names and actual usage, projects compile more predictably, eliminate redundant dependencies, and avoid many classpath-to-module-path migration errors.