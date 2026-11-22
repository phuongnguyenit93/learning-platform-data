# Designing Named Modules for Public Libraries

## 1. Context and goals

A public Java library often needs to serve two groups of users: applications using the traditional `classpath` and applications using the Java Platform Module System (JPMS) from Java 9 onward. When published as a **named module**, the library has a stable module name, describes dependencies in `module-info.java`, and explicitly declares which packages belong to the accessible API.

The goal of the design is not merely to include `module-info.class` in the JAR. A good library needs to:

- Allow other applications to use the API via `requires <module-name>` without needing access to internal packages.
- Keep the module name, published API, and types appearing in method signatures stable across releases.
- Declare sufficient compile-time/runtime dependencies; avoid creating implicit dependencies between modules.
- Be intentional about reflection, ServiceLoader, unmodularized libraries, and running on the classpath.
- Be verified with a real consuming application and JDK tools.

**Example scope:** JDK 17+, plain Java, illustrative module name `com.example.greetings`. Rename the module and packages to your actual domain/namespace before publishing.

## 2. Properly understanding named module boundaries

For a JAR placed on `--module-path`, the `module-info.class` descriptor enables JPMS to recognize it as an **explicit named module**. The module name is a logical identifier, not identical to the JAR file name, Maven `groupId`, or Maven `artifactId`.

Relationships to distinguish:

| Element | Meaning for a public library |
| --- | --- |
| `module com.example.greetings` | Establishes a stable module name for consuming applications to declare `requires` |
| `exports com.example.greetings.api` | Publishes `public` types in the API package to other modules at compile time and runtime |
| Package without `exports` | Can contain `public` classes, but code from other modules cannot access them directly via the module path |
| `requires other.module` | The current module reads exported public APIs of the dependency |
| `requires transitive other.module` | Modules reading the current module also read that dependency |
| `opens package` | Allows deep reflection into the package at runtime; not synonymous with `exports` |
| `uses` / `provides ... with` | Declares extension points via `ServiceLoader`, avoiding forcing consumers to depend on implementations |

`public` on a class/method only addresses access level within Java; JPMS adds package/module boundaries. Therefore, a `public` class located in an unexported package is still considered an implementation detail on the side of a consumer using the module path.

### Module names and packages

Name the module using reverse DNS, such as `com.example.greetings`; typically align the prefix with packages, though there is no rule forcing them to match identically. Choose a name that can be maintained for years. Do not attach a version to the module name, such as `com.example.greetings.v2`, merely to reflect a release change: the module name is part of the consumer integration contract.

The same package must not be scattered across two modules resolved together in a single layer. This is a **split package** risk; design clear package boundaries from the start.

## 3. Designing the public surface before writing module-info.java

Divide packages by role instead of exporting the entire source tree:

- `com.example.greetings.api`: facades, interfaces, value types, and exceptions that clients need to use.
- `com.example.greetings.spi`: contracts for plugins/service providers, exported only if meant for others to implement.
- `com.example.greetings.internal`: parsers, caches, algorithms, helpers, default implementations; keep unexported.
- `com.example.greetings.model`: export only when the model is truly part of the API; do not export solely because a framework needs reflection.

Evaluate **every public/protected signature** of types in exported packages: parameters, return types, superclasses, interfaces, generic bounds, checked exceptions, and annotations meaningful to consumers. If an API returns a type located in a hidden package, consumers will struggle to compile or use the contract properly. There are two choices: publish that type intentionally or change the API to depend on a public abstraction.

Example API that consumers should call:

```java
import com.example.greetings.api.Greetings;
String message = Greetings.greet("An");
```

Consumers should not have to know about `GreetingFormatter` in the `internal` package, and should not need `--add-exports` to use the library.

**Principle:** export the minimum set of packages that carry a long-term support contract. Every exported package creates a compatibility commitment for future releases.

## 4. Complete example: library and consuming application

Sample project structure:

```text
project/
├── lib/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/greetings/
│           ├── api/Greetings.java
│           └── internal/GreetingFormatter.java
└── app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/greetings/demo/Main.java
```

### 4.1. Library descriptor

File `lib/src/main/java/module-info.java`:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

This library does not need a `requires java.base;` directive because every module reads `java.base` by default. The `internal` package is not in `exports`, so it does not become an API directly accessible from outside.

### 4.2. Public API

File `lib/src/main/java/com/example/greetings/api/Greetings.java`:

```java
package com.example.greetings.api;

import com.example.greetings.internal.GreetingFormatter;

public final class Greetings {
    private Greetings() {
    }

    public static String greet(String name) {
        return GreetingFormatter.format(name);
    }
}
```

### 4.3. Encapsulated implementation

File `lib/src/main/java/com/example/greetings/internal/GreetingFormatter.java`:

```java
package com.example.greetings.internal;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String format(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
```

`GreetingFormatter` can still be `public` so packages inside **the same module** can call it; accessibility for consumers from other modules is restricted by the descriptor.

### 4.4. Consumer as another named module

File `app/src/main/java/module-info.java`:

```java
module com.example.greetings.demo {
    requires com.example.greetings;
}
```

File `app/src/main/java/com/example/greetings/demo/Main.java`:

```java
package com.example.greetings.demo;

import com.example.greetings.api.Greetings;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greetings.greet("An"));
    }
}
```

If the consumer attempts to import `com.example.greetings.internal.GreetingFormatter`, the compiler rejects access because this package is not exported to the consuming module. That is the desired boundary-protection behavior.

### 4.5. Compiling, packaging the JAR, and running

Inside `project/`, using JDK 17+ and PowerShell:

```powershell
New-Item -ItemType Directory -Force out/lib, out/app | Out-Null
javac --release 17 -d out/lib lib/src/main/java/module-info.java lib/src/main/java/com/example/greetings/api/Greetings.java lib/src/main/java/com/example/greetings/internal/GreetingFormatter.java
jar --create --file out/com.example.greetings.jar -C out/lib .
javac --release 17 --module-path out/com.example.greetings.jar -d out/app app/src/main/java/module-info.java app/src/main/java/com/example/greetings/demo/Main.java
java --module-path "out/com.example.greetings.jar;out/app" --module com.example.greetings.demo/com.example.greetings.demo.Main
```

Expected output:

```text
Hello, An!
```

On Linux/macOS, the separator for multiple entries in the module path is `:` instead of `;`. The `javac` commands above list all Java files explicitly for easy reproduction; real projects should let Maven/Gradle handle compilation and packaging.

Verify that the descriptor is inside the JAR:

```powershell
jar --describe-module --file out/com.example.greetings.jar
```

The output should reflect module `com.example.greetings` and exported package `com.example.greetings.api`. There is no need to expose the `internal` package for the consumer to work.

## 5. Choosing requires, requires transitive, and requires static

### `requires`: direct dependency

Declare `requires com.example.parser;` when code in the library needs to read exported APIs of module `com.example.parser`. Other modules requiring your library do not automatically read the parser module through this relationship.

### `requires transitive`: dependency present in the API

Suppose the API package of `com.example.reports` exposes a method returning `java.sql.Connection`:

```java
package com.example.reports.api;

public interface ConnectionFactory {
    java.sql.Connection open() throws java.sql.SQLException;
}
```

Appropriate descriptor:

```java
module com.example.reports {
    requires transitive java.sql;
    exports com.example.reports.api;
}
```

A module with `requires com.example.reports;` then also reads `java.sql`, so the API can be used with the exact types it exposes. Only use `transitive` when the dependency is genuinely part of the public contract; overusing it makes the dependency graph wide and hard to control.

### `requires static`: dependency required only at compile time

`requires static com.example.annotations;` expresses a dependency needed for compilation but not necessarily present at runtime. This fits certain annotation APIs or optional integrations. It **does not automatically guarantee** that code will continue working when calling types absent at runtime: design execution paths and test when the dependency is omitted.

The module descriptor does not lock dependency versions with syntax equivalent to a Maven version range. Versions are handled by the build/distribution system, combined with API compatibility policies.

## 6. exports, qualified exports, and opens: choosing the right access permissions

### `exports` is static API

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Any module that reads `com.example.greetings` can use public types in the `api` package.

### Qualified exports for restricted integration

```java
module com.example.greetings {
    exports com.example.greetings.api;
    exports com.example.greetings.internal.bridge to com.example.greetings.testkit;
}
```

Only module `com.example.greetings.testkit` is allowed to access public types in `internal.bridge` via the module path. This fits controlled integrations, though it creates coupling to a specific module name; do not use it to "patch" an API with unclear boundaries.

### `opens` for deep reflection

Serialization, ORM, or dependency injection frameworks sometimes need to access non-public constructors/fields via reflection. When there is a genuine requirement, prefer opening only the right package to the right module:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    opens com.example.greetings.model to com.fasterxml.jackson.databind;
}
```

This illustrative directive is only appropriate when the project has a `model` package and the corresponding Jackson library module in the module graph. `opens` allows deep reflection at runtime, but does not allow consumers compiling code to access types like `exports` does. If both static API and reflection are needed, design both permissions according to need. Avoid `open module` (opening all packages) when only a single package requires reflection.

Also avoid long-term reliance on JVM flags such as `--add-opens` or `--add-exports` for general-purpose APIs; they are usually a sign that the descriptor, packaging, or integration approach needs adjustment.

## 7. Extension points with ServiceLoader

A library needing plugins can publish a **small SPI**, keep the default implementation in an internal package, and allow third parties to package their own providers.

Suppose there is an interface:

```java
package com.example.greetings.spi;

public interface GreetingProvider {
    String greet(String name);
}
```

Library-side descriptor when discovering providers itself and having a default provider:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    exports com.example.greetings.spi;

    uses com.example.greetings.spi.GreetingProvider;
    provides com.example.greetings.spi.GreetingProvider
        with com.example.greetings.internal.DefaultGreetingProvider;
}
```

The `DefaultGreetingProvider` implementation must fulfill the `ServiceLoader` provider contract (e.g., public class implementing the SPI with an appropriate no-arg constructor), yet the package containing it **does not need to be exported** to consumers.

Library querying the service:

```java
ServiceLoader<GreetingProvider> providers =
    ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.greet("An"));
}
```

An external plugin module can declare:

```java
module com.partner.greetings.french {
    requires com.example.greetings;

    provides com.example.greetings.spi.GreetingProvider
        with com.partner.greetings.french.FrenchGreetingProvider;
}
```

Important condition: the provider module must be in the module configuration resolved at runtime (especially in custom runtime images or module layers). Do not assume the order of providers returned by `ServiceLoader`; if the application needs priority, establish selection criteria in the SPI contract. Keep the SPI narrow and document version compatibility clearly so partners can implement it easily.

`uses` is for the module calling `ServiceLoader`. `provides` is for the module contributing an implementation. They complement `exports` and do not replace the required access to the SPI interface.

## 8. Packaging and ecosystem compatibility

### 8.1. One artifact, two ways to use it

A modular JAR containing `module-info.class` can still be placed on the traditional classpath, where module resolution/encapsulation mechanisms are not applied the same way as with named modules. Therefore, for libraries targeting broad audiences:

- Test consumers using `--module-path` and `requires` descriptors.
- Test traditional consumers using `-cp`/`--class-path`.
- Ensure required dependencies and resources are present in both modes.
- Do not rely on JPMS hiding internal packages as a data security measure; the classpath permits access under different rules.

A clean API design still benefits classpath consumers, while the strongest module protection layer is present when the application runs as named modules.

### 8.2. Maven or Gradle

Place `module-info.java` at `src/main/java/module-info.java`, with classes in their corresponding package namespaces. With Maven, you can set:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Use a compiler plugin version that supports modular projects and inspect the output JAR. With Gradle, configure the Java toolchain and Java module path appropriately. Only add `Automatic-Module-Name` to the manifest when intentionally releasing a **JAR without a descriptor** to stabilize its automatic module name; it does not replace `module-info.java` of an explicit named module.

### 8.3. Unmodularized dependencies

A JAR without a descriptor placed on the module path can be treated as an **automatic module**. The name can come from the `Automatic-Module-Name` manifest attribute or be derived from the filename; derived names can easily change depending on packaging. Use `jar --describe-module --file <dependency.jar>` to inspect the name before declaring `requires`.

If a dependency remains on the classpath, it belongs to the unnamed module; an explicit named module cannot simply write `requires` to read an unnamed module like another named module. Move appropriate dependencies onto the module path, use modularized versions, or organize an adapter/compatibility layer as needed; avoid relying on exceptional JVM flags in widely distributed APIs.

### 8.4. Java 8 and multi-release JARs

Placing `module-info.class` at the JAR root causes standard builds to require JDK 9+ to produce the descriptor. If Java 8 must be supported, you can consider a **multi-release JAR**: Java 8-compatible application bytecode at the root, the Java 9+ descriptor at `META-INF/versions/9/module-info.class`, accompanied by manifest `Multi-Release: true`. This is a specialized packaging strategy that requires real testing on both JDK 8 and supported JDK versions; do not choose it if the library only targets JDK 17+.

## 9. API evolution: decisions that are hard to reverse

Once a library has published a named module, the API contract consists of multiple layers:

| Changed element | Possible impact |
| --- | --- |
| Renaming `module` | Consumers must update `requires`, module launch, and build configurations |
| Removing `exports` or changing packages | Consumers in other modules lose source/binary access |
| Changing public methods/constructors/types | May break source compatibility or binary compatibility |
| Adding dependency types to API signatures | May require `requires transitive` and explicit runtime dependencies |
| Removing service interfaces or changing the SPI | Third-party provider plugins may fail to load/run |
| Creating a split package in the dependency graph | May cause module resolution/compilation to fail |
| Opening additional packages with `opens` | Increases reflection surface and coupling to frameworks |

A sound strategy is to keep a **stable facade/interface** in exported packages and evolve implementations in closed packages. Treat the module name and exported packages as a public contract, with appropriate versioning/release notes. Semantic Versioning can serve as a release convention, but JPMS does not resolve version selection itself or allow two versions with the same module name in a single layer.

For annotation processors, reflection frameworks, serializers, or test frameworks, check the actual compatibility of each dependency; do not decide on `opens` merely because a framework "uses reflection".

## 10. Technical verification before publishing

### 10.1. Checking descriptors and dependencies

```powershell
jar --describe-module --file out/com.example.greetings.jar
jdeps --module-path out/com.example.greetings.jar --check com.example.greetings
```

`jar --describe-module` confirms that the artifact has the expected descriptor, module name, and directives. `jdeps --check` helps inspect the dependency graph and relationships worth reviewing; it does not replace integration tests.

### 10.2. Testing consumer compilation and execution

Maintain a small consumer project independent of the library's source. On the module path, verify:

1. The consumer module only needs `requires com.example.greetings;` for the example's pure Java public API.
2. Importing `com.example.greetings.api.Greetings` compiles, runs, and prints the expected output.
3. Importing the `internal` package is rejected at compile time, demonstrating encapsulation.
4. If reflection or providers exist, actually load/instantiate them on the module path; also test execution paths when optional dependencies are absent.
5. Run classpath tests in parallel if the library commits to supporting unmodularized applications.

For JUnit, integration tests, or Mockito/Byte Buddy, configuring the module path, `--patch-module`, or `--add-opens` may be needed **in the test environment**; do not assume the same permissions need to be opened in the published artifact.

### 10.3. Common errors and how to handle them

| Symptom | Likely cause | Design-oriented resolution |
| --- | --- | --- |
| `package ... is not visible` | API is not exported or consumer does not read the right module | Check `exports` and `requires` |
| `module not found: ...` | Wrong dependency/module path or wrong automatic module name used | Inspect `jar --describe-module`, paths, and actual names |
| `java.lang.reflect.InaccessibleObjectException` | Framework needs deep reflection but the package is not open | Use qualified `opens` for the right package/module if the contract allows |
| `ServiceConfigurationError` | Invalid provider, missing class/dependency, module not resolved | Check `uses`/`provides`, constructor/provider factory, resolution |
| `package is accessible from more than one module` | Split package across resolved modules | Reorganize namespaces or dependencies |
| API compiles but runtime fails due to dependencies | Optional/automatic/module resolution paths were not sufficiently tested | Review module path and runtime execution paths |

Exact messages vary by JDK and scenario; read the root cause of the stack trace before choosing a solution.

## 11. Design checklist for library authors

Before releasing, verify:

- **Stable name:** the module name is long-term, independent of versioned JAR filenames.
- **Intentional API:** export only packages users need to call; do not force consumers to import `internal`.
- **Clean signatures:** the public API does not accidentally expose implementation types or hidden dependencies.
- **Right dependencies:** declare `requires`, `requires transitive`, and `requires static` according to the situation; avoid arbitrary `transitive`.
- **Minimal reflection:** only `opens` necessary packages; specify target modules whenever possible.
- **Contract-compliant SPI:** stable interfaces, resolved providers, and a selection strategy if multiple providers exist.
- **Verified packaging:** the modular JAR contains the right descriptor; automatic dependency names are not guessed wrongly.
- **Tested compatibility:** consumers on the module path and classpath work under the modes the library claims to support.
- **Controlled releases:** every change to module name, exports, dependencies, and public types is reviewed as an API change.

## 12. Self-practice exercise

Extend the example in three steps: (1) create a `GreetingStyle` interface in the `api` package and implement it in `internal`; (2) create a new consumer module calling the API, try importing the internal implementation directly, and observe the compile error; (3) add `GreetingProvider` in the `spi` package, declare `uses`/`provides`, and run the consumer with an external provider module. Once each step works, describe which module reads which module, which packages are exported, and which packages are only opened for reflection (if any).

**Key point to remember:** a public library's named module is an **API and dependency contract**. Design from the boundaries and consumers first, then let `module-info.java` accurately reflect that contract.