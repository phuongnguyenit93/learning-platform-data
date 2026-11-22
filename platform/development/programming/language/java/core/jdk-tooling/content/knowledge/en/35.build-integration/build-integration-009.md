# Building Modular Java Applications

**Module build** is the process of compiling, checking dependencies, packaging, and running Java applications using the Java Platform Module System (JPMS). A modular project divides code into named modules; each module declares its dependencies and accessible API packages in a **module-info.java** file.

When built with the proper structure, the compiler detects missing dependencies or unexported packages; the JAR retains the module descriptor; the runtime resolves the module graph on the module path; and **jlink** can create a runtime image containing only the required modules.

This article walks through source layout, module descriptors, and `javac`/`jar` commands to `jdeps`, `jlink`, Maven, Gradle, CI, and common errors. Examples are built for Java 17+ and verified on OpenJDK 24.0.2, Maven 3.9.12, and Gradle 9.2.1.

## 1. What is a Java module?

A module is a unit of packaging and dependency management at a higher level than a package. A module has:

- A unique name in the module graph.
- A module descriptor, typically `module-info.java`.
- Exported packages for other modules to access.
- Dependencies declared with `requires`.
- Optional declarations of services used or provided.
- Clear access boundaries and encapsulation.

Example of an application with two modules:

~~~text
com.acme.greeter
    exports com.acme.greeter

com.acme.app
    requires com.acme.greeter
~~~

The `com.acme.app` module uses the public API of `com.acme.greeter`. Both the compiler and runtime enforce this relationship.

### How does a module differ from a package?

A package groups classes by namespace and organizes source code. A module groups multiple packages, controlling which packages are exported and which modules are read.

A public package is not automatically accessible to other modules if that package is not exported by the module that owns it.

### How does a module differ from a Maven/Gradle project?

A JPMS module is a concept at the Java runtime and module descriptor level. A Maven module or Gradle subproject is a build unit.

A Maven project can produce a modular JAR; multiple Maven projects can form a modular application. Similarly, a Gradle subproject can contain a JPMS module.

The Maven `artifactId`, Gradle project name, and JPMS module name do not have to be identical. When building, you need to manage all three names consistently.

## 2. Source structure of a multi-module project

A project with two modules can use this structure:

~~~text
modular-app/
├── src/
│   ├── com.acme.greeter/
│   │   ├── module-info.java
│   │   └── com/acme/greeter/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
├── out/
└── mods/
~~~

In this layout, the directory name directly under `src` is the module name. Inside each module directory, packages are placed according to their corresponding paths.

Modern build tools also support their own multi-project structures, for example Maven using individual module folders with `pom.xml` and Gradle using subprojects. The key requirement is that each JPMS module has a `module-info.java` matching its module name.

## 3. Writing module-info.java

The module descriptor declares the module name and dependency/access rules.

### requires

Declare a module dependency:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

The `com.acme.app` module can read public types located in packages exported by `com.acme.greeter`.

### exports

Export a package so other modules can use its public API:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

Only exported packages are accessible to other modules under JPMS rules. All remaining packages remain encapsulated.

### requires transitive

Used when a module's public API depends on types from another module and downstream modules need to read that dependency:

~~~java
module com.acme.api {
    requires transitive com.acme.model;
}
~~~

Modules that read `com.acme.api` also gain readability of `com.acme.model` through the module graph. Only use `transitive` when the dependency is part of the exposed API.

### requires static

Used for dependencies needed at compile time but not required to be present during runtime resolution in all scenarios:

~~~java
module com.acme.app {
    requires static com.acme.optionaltool;
}
~~~

If the code actually needs classes from the dependency at runtime, the application must still provide that module in the appropriate runtime environment. `requires static` does not make calling a non-existent class safe.

### Qualified exports

You can export a package only to specific modules:

~~~java
module com.acme.internal {
    exports com.acme.internal.spi to com.acme.plugin;
}
~~~

This is a qualified export. Other modules cannot access that package via a standard export.

### opens and open module

`exports` is for normal type access to public APIs. `opens` allows deeper reflective access to a package at runtime.

~~~java
module com.acme.model {
    opens com.acme.model.dto to com.fasterxml.jackson.databind;
}
~~~

This is commonly required for serialization, dependency injection, or ORM frameworks that use reflection.

You can open all packages with:

~~~java
open module com.acme.legacy {
    requires com.acme.common;
}
~~~

Only use `open module` when truly necessary. Opening too broadly reduces module encapsulation.

### uses and provides

Service loaders can be declared in the module descriptor:

~~~java
module com.acme.app {
    uses com.acme.spi.Formatter;
}
~~~

Module providing the implementation:

~~~java
module com.acme.json {
    requires com.acme.spi;
    provides com.acme.spi.Formatter
        with com.acme.json.JsonFormatter;
}
~~~

When building and linking, service provider modules can be included in the runtime image using the `jlink --bind-services` option.

## 4. Complete two-module application example

The `greeter` module provides a simple API; the `app` module calls that API.

### Greeter module

File **src/com.acme.greeter/module-info.java**:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

File **src/com.acme.greeter/com/acme/greeter/Greeter.java**:

~~~java
package com.acme.greeter;

public final class Greeter {
    public String message() {
        return "Hello from modular Java";
    }
}
~~~

### App module

File **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

File **src/com.acme.app/com/acme/app/Main.java**:

~~~java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().message());
    }
}
~~~

The `app` module can only use `Greeter` because `greeter` exports the `com.acme.greeter` package and `app` declares `requires com.acme.greeter`.

## 5. Compiling multiple modules with javac

From the `modular-app` directory:

~~~bash
javac --release 17 --module-source-path src -d out -m com.acme.greeter,com.acme.app
~~~

Explanation:

- `--release 17`: compiles against the Java SE 17 API and corresponding class file version.
- `--module-source-path src`: specifies the directory containing sources for multiple modules.
- `-d out`: output directory.
- `-m`: selects the modules to compile.

The compiler automatically resolves the `requires` relationship between the two modules. Since `app` depends on `greeter`, the compiler locates `greeter`'s source in `module-source-path`.

The output looks like this:

~~~text
out/
├── com.acme.greeter/
│   ├── module-info.class
│   └── com/acme/greeter/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

These are **exploded modules**: each module is compiled into its own directory, with `module-info.class` at the root of the module directory.

### Running exploded modules

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Where:

- `--module-path out`: where the runtime locates modules.
- `-m com.acme.app/com.acme.app.Main`: selects the module and main class.

Exact stdout:

~~~text
Hello from modular Java
~~~

### Compiling a module when dependencies are already built

In larger projects, modules can be built separately. When dependencies are already on the module path:

~~~bash
javac --release 17 --module-path mods -d out/app app-src/module-info.java app-src/com/acme/app/Main.java
~~~

The module path must contain the modules required by the module being compiled. If a dependency has not been built or lacks a valid module descriptor, the compiler will report that the module cannot be resolved.

## 6. Packaging modular JARs with jar

After compiling, you can package each module into a JAR.

Create the `mods` directory:

~~~bash
mkdir mods
~~~

On Windows PowerShell you can use:

~~~powershell
New-Item -ItemType Directory -Path mods -Force
~~~

Package `greeter`:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
~~~

Package `app` and declare the main class:

~~~bash
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

A modular JAR contains `module-info.class` at the archive root. Main class metadata tells tools the application's entry point.

### Inspecting the module descriptor in a JAR

~~~bash
jar --describe-module --file mods/com.acme.greeter.jar
jar --describe-module --file mods/com.acme.app.jar
~~~

Representative output:

~~~text
com.acme.greeter
exports com.acme.greeter
requires java.base mandated

com.acme.app
requires com.acme.greeter
requires java.base mandated
contains com.acme.app
main-class com.acme.app.Main
~~~

`java.base` is the foundational module implicitly required by every normal module.

### Running from modular JARs

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Hello from modular Java
~~~

You can specify the module path as a list of JARs. On Windows use a semicolon; on Linux/macOS use a colon. Using a `mods` directory is usually simpler when there are many modules.

## 7. Module path and classpath

Module path and classpath have different resolution rules.

| Classpath | Module path |
|---|---|
| Collection of classes and JARs on the class loader | Collection of named modules |
| Runs even without a module descriptor | Modular JAR or automatic module |
| No package control via exports/requires | Has module graph and strong encapsulation |
| Dependencies may have duplicate classes | Module names and split packages are strictly checked |
| Suitable for legacy apps or non-modular libraries | Suitable for JPMS applications |

### Automatic module

A JAR without `module-info.class` placed on the module path can become an automatic module. The module name can be taken from `Automatic-Module-Name` in the manifest or derived from the JAR filename.

An automatic module exports all its packages and reads other modules under broader rules than a standard named module. This acts as a bridge for non-modular libraries, though without the same level of encapsulation.

If maintaining a library long-term, ensure a stable module name and consider creating an explicit module descriptor when appropriate.

### Unnamed module

Code running on the classpath belongs to the unnamed module. Named modules do not automatically read the unnamed module. When migrating a legacy application to JPMS, you may need to modularize incrementally or use flags like `--add-reads` during the transition phase.

Do not use `--add-exports` or `--add-opens` as a permanent solution if you can fix the module descriptor or dependencies properly.

## 8. Checking dependencies with jdeps

`jdeps` analyzes dependencies at the package, class, or module level. It is useful for inspecting the module graph before packaging or creating a runtime image.

### Viewing a dependency summary

~~~bash
jdeps -summary mods/com.acme.app.jar
~~~

### Checking the module graph

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

This command checks the module's descriptor and dependency relationships.

### Printing the list of modules needed for runtime

~~~bash
jdeps --module-path mods --print-module-deps mods/com.acme.app.jar
~~~

Representative output:

~~~text
com.acme.greeter,java.base
~~~

This list can be used as input to `jlink --add-modules`. `jdeps` does not include the root `app` module itself in the printed dependency list.

### Finding dependencies on JDK internal APIs

~~~bash
jdeps --jdk-internals mods/com.acme.app.jar
~~~

If code depends on JDK internal APIs, replace them with supported public APIs. Internal APIs may change or be encapsulated in newer JDKs.

### Generating module descriptor suggestions for legacy JARs

~~~bash
jdeps --generate-module-info generated-modules legacy-library.jar
~~~

`jdeps` can generate a suggested `module-info.java` for non-modular libraries. The generated file should be reviewed manually, especially regarding `exports`, `requires`, and reflective access.

Do not treat tool-generated descriptors as a complete module design.

## 9. Creating a custom runtime with jlink

A modular application can be packaged with a runtime image containing only the necessary modules instead of requiring users to install a full JDK.

`jlink` takes modules from JDK `jmods` and the application module path, resolves the dependency closure, and creates a runtime image.

Example on Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

On Windows PowerShell, the module path uses a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

Explanation:

- `--module-path`: JDK `jmods` and application modules.
- `--add-modules com.acme.app`: root module to link.
- `--launcher`: creates an `app` command to launch the main class.
- `--output`: runtime image directory.

`jlink` automatically includes required dependencies of `com.acme.app` in the image, such as `com.acme.greeter` and `java.base`.

### Running the runtime image

Linux/macOS:

~~~bash
./runtime-image/bin/app
~~~

Windows:

~~~powershell
.\runtime-image\bin\app.bat
~~~

Or run the module directly using the linked runtime:

~~~bash
runtime-image/bin/java -m com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Hello from modular Java
~~~

### Limitations of jlink

- `jlink` requires explicit modules or linkable JMODs.
- Automatic modules and classpath-only JARs are not standard linking inputs.
- The runtime image is tied to the OS/architecture of the JDK used to create it.
- `jlink` from the current JDK creates a runtime based on that JDK version; `--release` during compilation does not make `jlink` produce a runtime for an older release.
- Service providers may require `--bind-services` to include provider modules in the image.
- You must verify native libraries, charsets, security providers, and resources loaded dynamically by the application.

If an application needs a Java 17 runtime image, use JDK 17's `jlink` to create the corresponding image, even if the source was built with a newer JDK using `--release 17`.

### Optimizing the image

You can strip debug symbols, header files, and man pages:

~~~bash
jlink --strip-debug --no-header-files --no-man-pages --compress=zip-6 --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-image
~~~

Measure the image size and run a smoke test after linking. A smaller image does not guarantee the application has been thoroughly tested on every operating system.

## 10. Integrating module builds with Maven

A Maven multi-module project uses a parent POM as an aggregator, and each JPMS module is a Maven child project.

Structure:

~~~text
modular-maven/
├── pom.xml
├── greeter/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/greeter/Greeter.java
└── app/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

### Parent pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>modular-parent</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeter</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

The parent POM declares the child modules and configures the compiler release. The Maven reactor determines build order based on inter-project dependencies.

### greeter/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>modular-parent</artifactId>
        <version>1.0-SNAPSHOT</version>
    </parent>

    <artifactId>greeter</artifactId>
</project>
~~~

The `module-info.java` file in `greeter` source declares:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

### app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>modular-parent</artifactId>
        <version>1.0-SNAPSHOT</version>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeter</artifactId>
            <version>1.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
~~~

The `app` module descriptor declares the JPMS dependency:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Note the two types of dependencies:

- Maven dependency determines the artifacts needed on the build classpath/module path.
- `requires` determines module readability at runtime and compile time in JPMS.

Both must align. Declaring only a Maven dependency without `requires` prevents the source module from reading the required module.

### Building with the Maven reactor

From the root directory:

~~~bash
mvn clean verify
~~~

Build only `app` along with its required dependency projects:

~~~bash
mvn -pl app -am clean verify
~~~

- `-pl app`: selects the `app` Maven project.
- `-am`: builds projects that `app` depends on.
- `clean verify`: cleans previous output, builds, runs verification/test phases, and confirms the build completes.

The Maven compiler plugin recognizes `module-info.java` and can use the module path for modular projects. Keep the compiler plugin version modern and set `maven.compiler.release` to avoid older default source/target settings.

### Running Maven modular JARs

Windows PowerShell:

~~~powershell
java --module-path "greeter/target/greeter-1.0-SNAPSHOT.jar;app/target/app-1.0-SNAPSHOT.jar" -m com.acme.app/com.acme.app.Main
~~~

Linux/macOS:

~~~bash
java --module-path "greeter/target/greeter-1.0-SNAPSHOT.jar:app/target/app-1.0-SNAPSHOT.jar" -m com.acme.app/com.acme.app.Main
~~~

## 11. Integrating module builds with Gradle

A Gradle multi-project build typically maps one JPMS module to one Gradle subproject.

Structure:

~~~text
modular-gradle/
├── settings.gradle
├── build.gradle
├── greeter/
│   ├── build.gradle
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/greeter/Greeter.java
└── app/
    ├── build.gradle
    └── src/main/java/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'modular-app'
include 'greeter', 'app'
~~~

### Root build.gradle

~~~groovy
allprojects {
    group = 'com.acme'
    version = '1.0.0'
}

subprojects {
    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
~~~

### greeter/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    modularity.inferModulePath = true
}
~~~

Module descriptor:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

### app/build.gradle

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':greeter')
}

java {
    modularity.inferModulePath = true
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

`implementation project(':greeter')` is a dependency in the Gradle project graph. `requires com.acme.greeter` is a dependency in the JPMS module graph. Both declarations must describe the same relationship used by the source code.

`modularity.inferModulePath = true` instructs Gradle to infer the module path from module descriptors and dependencies. This is an explicit and helpful configuration when building modular projects.

### Building and running with Gradle

Use the project's Gradle Wrapper.

Windows:

~~~powershell
.\gradlew.bat :app:build
.\gradlew.bat :app:run
~~~

Linux/macOS:

~~~bash
./gradlew :app:build
./gradlew :app:run
~~~

Build the entire project:

~~~bash
./gradlew clean build
~~~

Create an application distribution:

~~~bash
./gradlew :app:installDist
~~~

The Gradle Application Plugin generates launch scripts and distributions. When `mainModule` and `mainClass` are declared, Gradle can run the application on the module path according to the modularity configuration.

### Java Library: api and implementation

For library modules, use the `java-library` plugin to distinguish between public API dependencies and implementation dependencies:

- `api`: a dependency that is part of the public compile API that consumers need to read.
- `implementation`: an internal implementation dependency that is not exposed as a public API dependency to consumers.

The choice between `api` and `implementation` should match the module descriptor and exported public types. Do not declare `api` just to work around module-path errors without reviewing API boundaries.

## 12. Annotation processors, tests, and resources

### Annotation processors

Annotation processors can run on a separate classpath or module path. `javac` provides these options:

~~~bash
--processor-path
--processor-module-path
-processor
-proc
~~~

With Maven/Gradle, declare annotation processors in the compiler plugin configuration or `annotationProcessor` dependency configuration rather than placing the processor in the application's runtime modules.

If a processor needs access to module internals, check `exports`/`opens` and compiler options in the appropriate build phase.

### Tests in modular projects

Test code may need access to internal packages or use reflection. In such cases, test frameworks and build plugins can use module patching or `add-reads`/`add-opens` mechanisms.

Do not open production packages more broadly just to make tests pass. Prefer testing through exported APIs; only use scoped compiler/runtime test flags for tests that need internal inspection.

### Resources

Resources placed in each module's source/resource directory are packaged into artifacts by the build tool according to its rules.

With JPMS, code inside a module can access resources via the module/class API. If a framework needs reflection or accesses resources across different packages, check `opens` and how the framework locates resources.

## 13. Checking dependencies and the module graph in CI

A modular build pipeline should perform these steps:

1. Check out the source and select the pinned JDK version.
2. Run a clean build.
3. Run unit/integration tests.
4. Verify the module descriptor in the JAR.
5. Run `jdeps --check`.
6. Check for missing dependencies and JDK internal APIs.
7. Create a runtime image with `jlink` if the product distributes its own runtime.
8. Run a smoke test on the runtime image.
9. Archive artifacts and build metadata.

Example JAR checks:

~~~bash
jar --describe-module --file app.jar
jdeps --module-path mods --check com.acme.app
jdeps --module-path mods --print-module-deps app.jar
~~~

If the pipeline includes a `jlink` step, use the exact JDK version and target OS/architecture. Runtime images are generally not portable across Windows, Linux, and macOS.

### Pinning the JDK and build tools

Use the Maven Wrapper or Gradle Wrapper to lock build tool versions. Use toolchains or release configurations to select the Java API/classfile target. Record:

- JDK vendor/version.
- Maven/Gradle version.
- Plugin versions.
- Dependency versions.
- Build flags.
- OS/architecture.
- Runtime image options.

A reproducible build helps distinguish source changes from toolchain changes.

## 14. Troubleshooting module build errors

### Module not found

The message may look like:

~~~text
error: module not found: com.acme.greeter
~~~

Check:

- Does `module-info.java` have the correct module name?
- Has the dependency been built/packaged?
- Does `--module-path` point to the right directory/JAR?
- Does the JAR have `module-info.class` or `Automatic-Module-Name`?
- Is the Maven/Gradle dependency declared?
- Does the module path use the correct OS separator?

### Package is not visible

This may happen because the module dependency is missing `requires` or the package is not exported.

Check the module descriptors of both modules. Ensure the provider exports the API package and the consumer requires the corresponding module.

### Package is declared in module but module does not export it

The package exists but is not exported to the consumer. Add `exports` for the right package if it is intended to be public API. Do not export every package just to silence compiler errors.

### Module name does not match artifact name

The Maven `artifactId` or JAR filename can differ from the JPMS module name. Use `jar --describe-module` to inspect the actual module name; do not infer the module name solely from the filename.

### Split package

Two modules containing a package with the same name can cause a split-package conflict when resolving the module graph. Move the package into a single module or redesign ownership.

### Illegal reflective access or InaccessibleObjectException

A framework may need reflective access to an unopened package. Check the package and module named in the exception. Prefer updating the framework or declaring scoped `opens`. Only use `--add-opens` for compatibility after evaluating the risks.

### JAR runs on classpath but fails on module path

The code may be relying on the unnamed module, unopened reflection, split packages, or dependencies without stable module names. Run `jdeps` and `jar --describe-module` to inspect the module graph.

### jlink reports automatic module not supported

Check all dependencies on the module path. `jlink` requires explicit modules or JMODs; replace automatic module libraries with modular versions, create an appropriate explicit module descriptor, or adjust the packaging architecture.

### jlink image runs on the build machine but fails on another machine

Runtime images are built for a specific OS/architecture. Check native libraries, architecture, runtime environment, and platform dependencies. Build separate images for each target platform.

### Maven/Gradle compiles successfully but runtime reports module not found

Compile dependencies and the runtime module path may differ. Check dependency scopes/configurations, artifact packaging, module descriptors, and launch commands. Ensure the runtime distribution contains all required modules.

## 15. Module design principles for maintainable builds

- Choose stable module names, typically using reverse-domain naming.
- Export as few packages as possible.
- Separate public API from implementation packages.
- Only declare `requires` for dependencies that are actually needed.
- Use `requires transitive` when a dependency is part of the public API.
- Use `opens` for scoped reflective access.
- Avoid split packages.
- Avoid depending on JDK internal APIs.
- Check automatic modules before passing them to `jlink`.
- Keep module names stable across artifact renames.
- Manage the module graph alongside the Maven/Gradle dependency graph.
- Build and test on the exact target JDK release.
- Test the runtime image on each distribution platform.

## 16. Module build workflow from source to runtime image

~~~text
Source modules
    |
    v
module-info.java + Java source
    |
    v
javac / Maven / Gradle
    |
    v
Exploded modules
    |
    v
jar -> modular JARs
    |
    +----> jdeps --check / --print-module-deps
    |
    v
jlink
    |
    v
Custom runtime image
    |
    v
Smoke test / package / distribution
~~~

Each step validates a different layer:

- The compiler checks syntax and module dependencies.
- JARs preserve the module descriptor and classes/resources.
- `jdeps` checks the dependency graph and JDK internal APIs.
- `jlink` resolves the module closure and creates the runtime image.
- Smoke tests confirm the application runs on the final artifact.

Do not stop at a successful compile; always test running the exact modular JAR or runtime image that will be distributed.

## 17. Module build checklist

- `module-info.java` exists for each explicit module.
- Module names are unique and stable.
- `requires` matches actual dependencies.
- `exports` only exposes necessary public packages.
- `opens` is used only when reflection requires it.
- No split packages exist.
- Compiles cleanly with `--module-source-path` or the build tool.
- JAR contains `module-info.class` at the root.
- `jar --describe-module` shows the expected descriptor.
- `java --module-path` runs the main module.
- `jdeps --check` reports no unresolved issues.
- `jdeps --print-module-deps` identifies the runtime module closure.
- `jlink` creates an image for the target JDK/OS/architecture.
- Maven/Gradle dependency graph aligns with the JPMS graph.
- Tests and resources are packaged properly.
- CI pins JDK, plugin, and build tool versions.
- Runtime image passes a smoke test before release.

## 18. Key terminology

| Term | Meaning |
|---|---|
| JPMS | Java Platform Module System |
| Module descriptor | `module-info.java` or `module-info.class` file |
| Named module | A module with a name and descriptor |
| Exploded module | A module compiled into a directory |
| Modular JAR | A JAR containing `module-info.class` at its root |
| Module path | Path containing modules for the compiler/runtime to resolve |
| Classpath | Path of classes/JARs belonging to the unnamed module |
| requires | Declares a module dependency |
| requires transitive | Propagates dependency readability to consumers |
| requires static | Compile-time dependency that can be optional at runtime |
| exports | Exposes a package to other modules |
| opens | Allows reflective access to a package |
| Automatic module | A JAR without a descriptor inferred as a module on the module path |
| jdeps | Dependency analysis tool |
| jlink | Custom runtime image creation tool |
| jmod | JDK module archive format |
| Maven reactor | Mechanism for building multiple Maven projects according to their dependency graph |
| Gradle subproject | A build unit in a multi-project Gradle build |
| Toolchain | JDK configuration used to compile/test/run |
| Runtime image | Custom runtime bundle containing required modules |

Building modular applications requires aligning module descriptors, source layout, build dependencies, and the runtime module path. Start with `javac` to understand the module graph, package modular JARs, use `jdeps` to verify dependencies, and then integrate Maven/Gradle and `jlink` for distribution pipelines. Always run a smoke test on the final artifact rather than only verifying that compilation succeeds.

## References

- Oracle Java SE 24 — The Java Module System: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/package-summary.html
- Oracle JDK 24 — javac Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle JDK 24 — jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle JDK 24 — jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Apache Maven — Maven Multi-Module Projects: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle — Building Java Modules: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Gradle — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
