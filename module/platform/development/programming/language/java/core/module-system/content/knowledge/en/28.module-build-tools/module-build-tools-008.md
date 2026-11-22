# Packaging modular JARs in builds

An application using the Java Platform Module System (JPMS) needs more than a `module-info.java` file in its source tree. During the build, the system must **compile the descriptor into `module-info.class` and package that class at the right location inside the JAR**. The resulting artifact is called a **modular JAR** (often also called an explicit modular JAR).

Proper packaging allows `java`, `javac`, `jdeps`, and `jlink` to recognize the module name, dependencies, exported/opened packages, and service declarations. Conversely, if `module-info.class` is omitted or placed in the wrong location, the JAR may become an automatic module when placed on the module path, causing boundaries and dependency verification to diverge sharply from the original design.

This article walks through artifact structure, building with JDK commands, configuring Maven/Gradle, packaging resources and service providers, verifying outputs, and troubleshooting common issues.

## 1. How does a modular JAR differ from a regular JAR?

In the standard layout, an explicit modular JAR has the structure:

~~~text
org.example.greeter.jar
├── module-info.class
├── org/
│   └── example/
│       └── greeter/
│           ├── api/
│           │   └── GreetingService.class
│           └── internal/
│               └── DefaultGreetingService.class
└── META-INF/
    └── MANIFEST.MF
~~~

`module-info.class` sits **directly at the root of the JAR**, not beneath a package name and not inside a `classes/` subdirectory in a standard JAR.

The descriptor can originate from source:

~~~java
module org.example.greeter {
    exports org.example.greeter.api;
}
~~~

At compile time, `javac` produces `module-info.class` containing the `Module` attribute. When the JAR is placed on the module path, the module system reads this descriptor to establish module relationships.

Comparison:

| Artifact type | Indicator | Behavior when placed on the module path |
| --- | --- | --- |
| Explicit modular JAR | Has a valid `module-info.class` descriptor | JPMS strictly applies `requires`, `exports`, `opens`, `uses`, `provides` |
| Non-modular JAR | No descriptor | May become an automatic module with a name derived or declared via manifest |
| JAR on the classpath | Whether it has a descriptor or not, used via classpath | JAR classes are loaded in the unnamed module of the corresponding class loader |
| JMOD | `.jmod` format with distinct sections | Primarily a compile/link-time input, not a direct runtime JAR |

Merely putting `Automatic-Module-Name` into the manifest does not create an explicit modular JAR. It only supplies a stable name for an automatic module when an artifact lacking a descriptor is used in a module path configuration.

## 2. Complete example with two modules

We build an API module and a CLI module that uses that API.

Source structure:

~~~text
project/
└── src/
    ├── org.example.greeter/
    │   ├── module-info.java
    │   └── org/example/greeter/api/
    │       └── GreetingService.java
    └── org.example.cli/
        ├── module-info.java
        └── org/example/cli/
            └── Main.java
~~~

Descriptor for API:

~~~java
// src/org.example.greeter/module-info.java
module org.example.greeter {
    exports org.example.greeter.api;
}
~~~

API class:

~~~java
// src/org.example.greeter/org/example/greeter/api/GreetingService.java
package org.example.greeter.api;

public final class GreetingService {
    private GreetingService() {}

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Descriptor for CLI:

~~~java
// src/org.example.cli/module-info.java
module org.example.cli {
    requires org.example.greeter;
}
~~~

Main class:

~~~java
// src/org.example.cli/org/example/cli/Main.java
package org.example.cli;

import org.example.greeter.api.GreetingService;

public final class Main {
    public static void main(String[] args) {
        System.out.println(GreetingService.greet("JPMS"));
    }
}
~~~

The following sections compile, package, and run both modules from actual modular JARs.

## 3. Compiling with javac before packaging

From the `project` directory, run:

~~~bash
javac \
  --module-source-path src \
  -d out \
  -m org.example.greeter,org.example.cli
~~~

Where:

- `--module-source-path src` specifies the directory containing sources organized by module name.
- `-d out` specifies the output directory for compiled classes.
- `-m` lists the root modules to compile.

After successful compilation, the output has the structure:

~~~text
out/
├── org.example.greeter/
│   ├── module-info.class
│   └── org/example/greeter/api/GreetingService.class
└── org.example.cli/
    ├── module-info.class
    └── org/example/cli/Main.class
~~~

Each module has an independent output directory with `module-info.class` at the root of that module's directory.

Do not use `-C out .` to create one combined JAR containing two module descriptors in two subdirectories. With per-module packaging, each explicit module needs its own artifact or matching output root so JPMS tools find the right descriptor.

When using Maven/Gradle, the build tool replaces the manual `javac` step, yet the principle of the descriptor residing at the artifact root remains the same.

## 4. Packaging with jar --create

Create a distribution directory:

~~~bash
mkdir dist
~~~

Package the API module:

~~~bash
jar --create \
  --file dist/org.example.greeter.jar \
  -C out/org.example.greeter .
~~~

Package the CLI module:

~~~bash
jar --create \
  --file dist/org.example.cli.jar \
  -C out/org.example.cli .
~~~

The `-C directory .` option instructs the tool to change context to the module directory and place all contents from inside it at the JAR root. This is why `module-info.class` appears directly at the root of the artifact.

Inspect contents:

~~~bash
jar --list --file dist/org.example.greeter.jar
jar --list --file dist/org.example.cli.jar
~~~

Abbreviated output:

~~~text
META-INF/
META-INF/MANIFEST.MF
module-info.class
org/example/greeter/api/GreetingService.class
~~~

You can configure the main class when packaging CLI:

~~~bash
jar --create \
  --file dist/org.example.cli.jar \
  --main-class org.example.cli.Main \
  -C out/org.example.cli .
~~~

If main-class metadata is not embedded, you can still run with the `-m MODULE/MAIN_CLASS` syntax specifying the full main class name.

## 5. Running the packaged modular JARs

Put both JARs on the module path:

~~~bash
java \
  --module-path dist \
  --module org.example.cli/org.example.cli.Main
~~~

Output:

~~~text
Hello, JPMS!
~~~

JPMS locates `org.example.cli` in `dist`, reads the descriptor `requires org.example.greeter`, and resolves the dependency module.

You can use the short flags:

~~~bash
java -p dist -m org.example.cli/org.example.cli.Main
~~~

If main-class metadata was stored in the modular JAR, you can use the module-name-only form under supported configurations:

~~~bash
java -p dist -m org.example.cli
~~~

What to avoid is running:

~~~bash
java -cp dist/org.example.cli.jar org.example.cli.Main
~~~

This classpath launch does not use the JAR as an explicit named module. Having `module-info.class` in the JAR does not turn a classpath launch into a modular launch.

## 6. Inspecting descriptors inside artifacts

Do not rely on `.jar` filenames to assume packaging is right. Inspect the actual artifact.

The most useful command:

~~~bash
jar --describe-module \
  --file dist/org.example.greeter.jar
~~~

The output displays the module name and directives in the descriptor, for example:

~~~text
org.example.greeter
exports org.example.greeter.api
requires java.base mandated
~~~

`requires java.base mandated` is the implicit dependency enforced by the module system, even though the source did not write `requires java.base;`.

Inspect the CLI module:

~~~bash
jar --describe-module \
  --file dist/org.example.cli.jar
~~~

Output may include:

~~~text
org.example.cli
requires java.base mandated
requires org.example.greeter
~~~

The next command checks whether the Java launcher can recognize both modules from the distribution directory:

~~~bash
java --module-path dist --list-modules
~~~

The observable module set includes system modules and valid modules in the `dist` directory.

To view actual dependencies at the module level:

~~~bash
jdeps --module-path dist --check org.example.cli
~~~

`jdeps` is useful for inspecting the dependency graph and checking module constraints. It does not replace launching and testing the application, especially if reflection or dynamically loaded service providers are involved.

## 7. Building modular JARs with Maven

In Maven, each Maven module typically produces a separate artifact. Distinguish a **Maven module** (a project/artifact in a multi-module build) from a **JPMS module** (defined by `module-info.java`).

Suppose the layout is:

~~~text
workspace/
├── pom.xml
├── greeter-api/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── org/example/greeter/api/GreetingService.java
└── greeter-cli/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── org/example/cli/Main.java
~~~

The parent POM specifies the two subprojects:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>org.example</groupId>
  <artifactId>workspace</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>

  <modules>
    <module>greeter-api</module>
    <module>greeter-cli</module>
  </modules>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <pluginManagement>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-compiler-plugin</artifactId>
          <version>3.14.1</version>
        </plugin>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-jar-plugin</artifactId>
          <version>3.4.2</version>
        </plugin>
      </plugins>
    </pluginManagement>
  </build>
</project>
~~~

In `greeter-api/pom.xml`, the project has `groupId=org.example`, `artifactId=greeter-api`, `version=1.0.0`, `packaging=jar`, and references parent. In `greeter-cli/pom.xml`, declare the Maven dependency:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.example</groupId>
    <artifactId>greeter-api</artifactId>
    <version>1.0.0</version>
  </dependency>
</dependencies>
~~~

And the Java descriptor in the CLI project:

~~~java
module org.example.cli {
    requires org.example.greeter;
}
~~~

These two declarations serve different purposes:

- `<dependency>` in the POM lets Maven fetch the artifact and include the dependency in the build.
- `requires` in `module-info.java` establishes readability at the JPMS level.

When dependencies are explicit named modules and toolchains/plugins are configured properly, the Maven Compiler Plugin compiles modules via the module path. The Maven JAR Plugin packages output from `target/classes`, including `module-info.class`.

Build from the root directory:

~~~bash
mvn clean package
~~~

Output typically looks like:

~~~text
greeter-api/target/greeter-api-1.0.0.jar
greeter-cli/target/greeter-cli-1.0.0.jar
~~~

The JAR filename is the Maven artifact name, which does not have to match the JPMS module name. **The actual module name is determined by the descriptor**, not the `artifactId`.

Verify:

~~~bash
jar --describe-module \
  --file greeter-api/target/greeter-api-1.0.0.jar
~~~

When using different Maven plugins or versions, verify JPMS support and compiler configuration rather than assuming every generated JAR is automatically modular.

## 8. Building modular JARs with Gradle

With the Gradle Java Plugin, a Kotlin DSL configuration for a project with `module-info.java`:

~~~kotlin
plugins {
    java
}

java {
    modularity.inferModulePath.set(true)

    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Standard source layout:

~~~text
greeter-api/
├── build.gradle.kts
└── src/main/java/
    ├── module-info.java
    └── org/example/greeter/api/GreetingService.java
~~~

In the CLI project, declare the dependency on the API project:

~~~kotlin
dependencies {
    implementation(project(":greeter-api"))
}
~~~

And CLI's `src/main/java/module-info.java`:

~~~java
module org.example.cli {
    requires org.example.greeter;
}
~~~

Just like Maven, `implementation(project(":greeter-api"))` tells Gradle to supply the artifact for compilation, whereas `requires org.example.greeter` is the module relationship verified by `javac`.

Build:

~~~bash
./gradlew clean jar
~~~

Or on Windows:

~~~powershell
.\gradlew.bat clean jar
~~~

JARs typically reside in:

~~~text
greeter-api/build/libs/
greeter-cli/build/libs/
~~~

Use `jar --describe-module --file ...` to confirm the descriptor was actually packaged. If Gradle is compiling on the classpath, inspect `modularity.inferModulePath`, the toolchain, and how dependencies are recognized as named/automatic modules.

## 9. Choosing a consistent Java release and toolchain

Module descriptors were introduced in Java 9. Therefore:

- Building explicit modular JARs generally requires a JPMS-capable compiler.
- `--release` must be compatible with used APIs and class-file targets.
- The Java runtime executing the code must support reading the compiled class files and module descriptor.
- CI, local, and release environments should use managed, consistent toolchain versions.

Example `javac`:

~~~bash
javac --release 21 \
  --module-source-path src \
  -d out \
  -m org.example.greeter,org.example.cli
~~~

In Maven:

~~~xml
<properties>
  <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

In Gradle, use Java toolchains to manage the compiler. If the application must run on Java 17, compiling with `--release 21` creates incompatible class files. Select the Java release according to the minimum supported runtime.

Some libraries wanting to support Java 8 while providing a descriptor for Java 9+ may use a **multi-release JAR**: regular classes target Java 8, while `module-info.class` is placed in `META-INF/versions/9/` alongside `Multi-Release: true` in the manifest. This is an advanced packaging workflow requiring dedicated build configuration and testing across both runtime groups; do not merely move `module-info.class` manually and assume every tool handles it properly.

## 10. Packaging resources without breaking module structure

A modular JAR can still contain resource files:

~~~text
org.example.greeter.jar
├── module-info.class
├── org/example/greeter/api/GreetingService.class
├── org/example/greeter/messages.properties
└── META-INF/MANIFEST.MF
~~~

With Maven or Gradle, resources in `src/main/resources` are typically copied into the output and packaged into the JAR.

Example:

~~~text
greeter-api/
├── src/main/java/module-info.java
├── src/main/java/org/example/greeter/api/GreetingService.java
└── src/main/resources/org/example/greeter/messages.properties
~~~

Do not place `module-info.class` into `src/main/resources` as a standalone unmanaged file. The descriptor should be compiled from `module-info.java`.

A resource existing inside a JAR does not guarantee every other module can read it freely. Resources in named modules are subject to the corresponding module/resource access rules; for resources encapsulated inside packages, whether packages are opened and which API is used to load resources can affect external readability.

When using frameworks that read resources or perform reflection, inspect package `opens` and class loader behavior instead of placing sources into the resources directory to “bypass” module boundaries.

## 11. Packaging service providers

If a module provides an implementation for an SPI, declare `provides ... with ...` in the descriptor:

~~~java
module org.example.greeter.provider {
    requires org.example.greeter.api;

    provides org.example.greeter.api.Greeter
        with org.example.greeter.provider.DefaultGreeter;
}
~~~

The consumer module declares:

~~~java
module org.example.greeter.client {
    requires org.example.greeter.api;
    uses org.example.greeter.api.Greeter;
}
~~~

When packaging the JAR, `module-info.class` contains the appropriate service metadata. When using explicit named modules on the module path, `ServiceLoader` reads provider information from the module descriptor.

Legacy libraries typically use the file:

~~~text
META-INF/services/org.example.greeter.api.Greeter
~~~

This mechanism works for providers discovered on the classpath or in compatibility scenarios. With explicit named modules, define `provides` properly in `module-info.java`; do not merely copy `META-INF/services` files expecting the module system to treat them as module declarations automatically.

Merely having the provider JAR on the module path does not guarantee it is resolved into an application's runtime graph. You may need to add the provider module to the root set, configure service binding, or use an appropriate plugin layer. Check `java --show-module-resolution` and how the application invokes `ServiceLoader` if a provider is not found.

## 12. Multiple dependencies: do not package across module boundaries

In a modular build, each module has its own descriptor and set of packages. Do not create a fat JAR by arbitrarily merging classes from multiple explicit modules into one JAR while keeping one random descriptor.

Risks:

- Only one `module-info.class` survives, discarding module information of other dependencies.
- Merged packages cause split packages or namespace collisions.
- `requires`, `exports`, `opens`, and service declarations no longer reflect actual contents.
- Module analysis tools can produce misleading results compared to the original build.

If the application needs a single deployable artifact, consider:

1. Keeping each explicit module as a modular JAR and distributing with the module path.
2. Using `jlink` to link required modules into a runtime image.
3. Using `jpackage` when platform installers bundling the application and runtime are needed.
4. Creating a fat JAR only when intentionally abandoning or redesigning module boundaries, with proper packaging configuration and thorough testing.

For legacy dependencies without descriptors, Maven/Gradle can place them on the module path as automatic modules in certain configurations. An automatic module's name may derive from `Automatic-Module-Name` or the JAR filename. Do not make module descriptors rely on fragile derived names if the library can be converted into an explicit modular JAR.

## 13. Checking stable module names

A module is identified by the name in `module-info.java`, for example:

~~~java
module org.example.greeter {
    exports org.example.greeter.api;
}
~~~

The artifact can be published under the filename:

~~~text
greeter-api-1.0.0.jar
~~~

This is completely normal: Maven/Gradle manage artifact coordinates, while JPMS manages module names.

If an artifact does not yet have a descriptor, you can use the manifest entry:

~~~text
Automatic-Module-Name: org.example.greeter
~~~

to provide a stable module name when the JAR is placed on the module path. However, that artifact remains an **automatic module** until it has an explicit descriptor.

Once a real `module-info.java` is added, keep the module name stable if consumers already reference that name in `requires`. Renaming a module is a breaking change to the module-level contract and may require all downstream consumers to update their descriptors.

## 14. Verifying build artifacts in CI

A passing build does not guarantee JPMS packaging is accurate. Artifact verification steps can be added to the pipeline.

**Check the descriptor:**

~~~bash
jar --describe-module --file dist/org.example.greeter.jar
~~~

**List root entries:**

~~~bash
jar --list --file dist/org.example.greeter.jar
~~~

Ensure `module-info.class` is at the JAR root (except in intentionally designed multi-release JARs).

**List modules visible to the launcher:**

~~~bash
java --module-path dist --list-modules
~~~

**Run the modular application:**

~~~bash
java -p dist -m org.example.cli/org.example.cli.Main
~~~

**Display module resolution:**

~~~bash
java --show-module-resolution \
  --module-path dist \
  -m org.example.cli/org.example.cli.Main
~~~

If CI must ensure an artifact did not accidentally degrade into an automatic module, verify that `jar --describe-module` output reports an explicit descriptor and expected directives. Many workflows also assert module names, exports, and requires via tests or small scripts to prevent build plugins from stripping `module-info.class`.

Checking only that the JAR “runs” with `java -cp ...` is insufficient: the classpath can bypass module boundaries and mask packaging mistakes.

## 15. Using modular JARs as jlink inputs

One benefit of explicit modular JARs is that they can participate in runtime image linking with `jlink` when all dependencies are compatible.

Example:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:dist" \
  --add-modules org.example.cli \
  --launcher greeter=org.example.cli/org.example.cli.Main \
  --output runtime-image
~~~

After linking succeeds:

~~~bash
./runtime-image/bin/greeter
~~~

Output:

~~~text
Hello, JPMS!
~~~

Windows uses a semicolon instead of a colon when joining multiple paths in `--module-path`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;dist" --add-modules org.example.cli --launcher greeter=org.example.cli/org.example.cli.Main --output runtime-image
~~~

`jlink` requires a suitable linkable set of modules. Automatic modules are not supported as explicit modules during standard linking. If a dependency exists only as an automatic module, consider modularizing the library or adjusting architecture before asking `jlink` to build an image.

If the application does not need a custom runtime image, distributing modular JARs with a compatible JDK/runtime and an explicit module path remains a valid option.

## 16. Common errors and troubleshooting

| Symptom | Possible cause | How to check or fix |
| --- | --- | --- |
| `jar --describe-module` reports automatic module | `module-info.class` was not packaged properly | Check compiler output and JAR contents |
| `module not found: org.example.greeter` | Artifact missing from module path or module name mismatches | Check `--module-path`, descriptor, and actual JARs |
| `package ... is not visible` | Consuming module lacks readability or dependency has not exported the package | Check `requires`, `exports`, and compiler module path |
| `ClassNotFoundException` at runtime | Difference between classpath and module path, or missing artifact/resource | Check launch command and artifact contents |
| Duplicate module name | Two artifacts define or advertise the same module name | Clean up module path and dependency resolution |
| Split package causes resolution error | Two named modules share a package in an invalid graph | Separate packages and adjust module boundaries |
| `java -cp` works but `java -m` fails | Build does not actually satisfy module boundaries | Check modular launch, `requires`, `exports`, `opens` |
| Service provider not found | Missing `provides`, `uses`, or provider not resolved | Check descriptor, root modules, and service binding |
| `jlink` rejects an automatic module | Dependency lacks an explicit module descriptor | Modularize dependency or choose another distribution form |
| CI produces class-file version incompatible with runtime | Compiler toolchain or `--release` higher than target runtime | Lock JDK/toolchain and test on lowest supported runtime |

## 17. Recommended packaging workflow

For a new modular project, a practical workflow can follow this order:

1. **Design module names:** choose stable, clear names independent of artifact versions.
2. **Write descriptors:** declare necessary `requires`, `exports`, `opens`, `uses`, and `provides`.
3. **Configure the build tool:** select JDK toolchain and Java release; configure Maven/Gradle to recognize the module path.
4. **Compile:** ensure `module-info.java` is compiled into `module-info.class`.
5. **Package each module:** keep the descriptor at the root of each modular JAR alongside classes/resources.
6. **Inspect artifacts:** use `jar --list` and `jar --describe-module`.
7. **Run via the module path:** use `java -p ... -m ...` instead of testing only on the classpath.
8. **Verify resolution:** use `--show-module-resolution` and `jdeps` where needed.
9. **Verify services/reflective access:** confirm service providers resolve and packages open to the right modules.
10. **Distribute:** choose modular JARs + module path or a `jlink` image according to deployment requirements.

This checklist should be automated in build/CI so adding dependencies or changing plugins cannot silently drop module metadata.

## Conclusion

**Packaging modular JARs** means preserving JPMS boundaries from source code through distributable artifacts. An explicit modular JAR must carry a valid `module-info.class` in the right place while containing classes, resources, and metadata consistent with the descriptor.

`javac` produces descriptors and classes; `jar` packages each module; Maven/Gradle automate those steps when configured properly. After building, use `jar --describe-module`, `java --module-path ... --list-modules`, and modular launches to verify artifacts. Do not rely on a JAR running on the classpath to conclude that module configuration is right. For systems requiring compact, easy-to-distribute runtime images, valid modular JARs are also the essential foundation for linking with `jlink`.