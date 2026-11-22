# Compiling modules in a multi-project build

In a Java project with multiple subprojects, each project can produce a separate JAR. When using the Java Platform Module System (JPMS), each subproject can simultaneously be a **named module** with its own `module-info.java`, dependencies, and public API. During compilation, the build tool must order the projects properly, place input artifacts on the **module path**, and ensure that `requires`/`exports` directives align with the build system's dependencies.

A common point of confusion: a Maven or Gradle **multi-project build** is a structure for managing build tasks; the JPMS **module graph** is the dependency structure that `javac` and the JVM verify. The two structures are related, but they do not automatically synchronize with each other. A dependency declared in `pom.xml` or `build.gradle` does not automatically generate a `requires` directive; conversely, declaring `requires` does not cause Maven or Gradle to automatically download an artifact absent from the dependency configuration.

This lesson uses the same Java example, then compiles it with `javac`, organizes it as a **Maven multi-module reactor**, and organizes it as a **Gradle multi-project build**.

## Objectives

After this lesson, you will be able to:

- Distinguish a build project/module from a JPMS named module.
- Split source code into subprojects with separate `module-info.java` files.
- Determine the build order and module path for each compilation step.
- Write `requires`, `requires transitive`, and `exports` accurately according to the actual API.
- Configure a Maven reactor to compile interdependent projects.
- Configure a Gradle multi-project build with `java-library` and `modularity.inferModulePath`.
- Diagnose `module not found`, `package is not visible`, incorrect classpath/module path, split packages, and errors caused by dependencies not being propagated to consumers.
- Inspect results from JARs and run the application using `java -m`.

## 1. Two graphs to understand

Suppose the system has three projects:

~~~text
api        -> contains public data model
service    -> implements business logic, uses api
app        -> entry point, uses service
~~~

At the build level, the relationships are described as follows:

~~~text
app (build project)
  └── depends on service (build project)
        └── depends on api (build project)
~~~

At the JPMS level, the application has the modules:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.service
    |
    | requires transitive
    v
com.acme.api
~~~

Both graphs may point in the same direction, but they are declared in **two different places**:

| Layer | Configuration source | Purpose |
|---|---|---|
| Maven | `pom.xml` in each project | Downloads artifacts, sets up compile/test/runtime classpath, determines reactor order |
| Gradle | `settings.gradle`, `build.gradle` | Declares subprojects, dependency configurations, task graph |
| JPMS | `module-info.java` | Module name, readability, exports, opens, and service declarations |

If the service build lacks a dependency on api, the compiler typically cannot find the `com.acme.api` module. If the service build has the dependency but the descriptor lacks `requires com.acme.api;`, the compiler may see the JAR yet refuse to use the types because the service module cannot read api.

## 2. Unified project structure

We use the standard Maven/Gradle layout:

~~~text
jpms-multi-project/
├── api/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/api/Message.java
├── service/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/service/GreetingService.java
└── app/
    └── src/main/java/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

When using Maven, `pom.xml` files will be added at the root and in the subprojects. When using Gradle, `settings.gradle`, root `build.gradle`, and subproject configurations will be added. The two build variants are presented separately; **you do not need to apply both Maven and Gradle for the same build**.

### 2.1. API module

`api/src/main/java/module-info.java`:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

`api/src/main/java/com/acme/api/Message.java`:

~~~java
package com.acme.api;

public record Message(String text) {
}
~~~

This module exports the package containing the data type that other modules are permitted to use. The example uses Java 17 or later to use `record` without requiring preview feature configuration.

### 2.2. Service module

`service/src/main/java/module-info.java`:

~~~java
module com.acme.service {
    requires transitive com.acme.api;
    exports com.acme.service;
}
~~~

`service/src/main/java/com/acme/service/GreetingService.java`:

~~~java
package com.acme.service;

import com.acme.api.Message;

public final class GreetingService {
    public Message greet(String name) {
        return new Message("Hello, " + name);
    }
}
~~~

Here `GreetingService.greet()` returns `Message`, a public type belonging to the api module. Because a type from api is part of service's public API, using `requires transitive com.acme.api;` is an appropriate design: consumers reading service can read api transitively.

If api were only an internal implementation dependency not appearing in the public API, service would typically only need:

~~~java
requires com.acme.api;
~~~

### 2.3. App module

`app/src/main/java/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

`app/src/main/java/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.api.Message;
import com.acme.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        Message result = new GreetingService().greet("JPMS");
        System.out.println(result.text());
    }
}
~~~

App directly declares `requires com.acme.service;`; the api module is read indirectly thanks to service's `requires transitive`. This does not mean every dependency should be transitive: use transitive only when the downstream module belongs to the intermediate module's public API contract.

Expected output when running:

~~~text
Hello, JPMS
~~~

## 3. Manual compilation to understand the module path

Before using a build tool, you can compile each module with `javac`. This clarifies what Maven/Gradle need to automate.

Create three output directories:

~~~text
out/
├── api/
├── service/
└── app/
~~~

### 3.1. Compile api first

~~~bash
javac -d out/api \
    api/src/main/java/module-info.java \
    api/src/main/java/com/acme/api/Message.java
~~~

The output looks like:

~~~text
out/api/
├── module-info.class
└── com/acme/api/Message.class
~~~

`out/api` is the root of the compiled module: `module-info.class` sits directly at that root.

### 3.2. Compile service with the module path pointing to api

~~~bash
javac --module-path out/api -d out/service \
    service/src/main/java/module-info.java \
    service/src/main/java/com/acme/service/GreetingService.java
~~~

`javac` reads service's descriptor, sees `requires transitive com.acme.api;`, and uses the module path to locate the compiled api module.

If `--module-path out/api` is omitted, the compiler may report:

~~~text
module not found: com.acme.api
~~~

### 3.3. Compile app with the required modules

Linux/macOS:

~~~bash
javac --module-path "out/api:out/service" -d out/app \
    app/src/main/java/module-info.java \
    app/src/main/java/com/acme/app/Main.java
~~~

On Windows, the module path uses a semicolon:

~~~powershell
javac --module-path "out/api;out/service" -d out/app app/src/main/java/module-info.java app/src/main/java/com/acme/app/Main.java
~~~

App needs both service and api on the module path because app uses the `Message` type from api in its source code. `requires transitive` establishes readability, but **the compiler still needs to locate the actual module** via the module path or corresponding module source.

### 3.4. Run the application

Linux/macOS:

~~~bash
java --module-path "out/api:out/service:out/app" \
    -m com.acme.app/com.acme.app.Main
~~~

Windows:

~~~powershell
java --module-path "out/api;out/service;out/app" -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, JPMS
~~~

Build order:

~~~text
compile(api) -> compile(service) -> compile(app) -> run(app)
~~~

This is precisely the order that a build tool needs to organize based on the project's dependency graph.

## 4. Module source path differs from multi-project layout

Some JPMS examples use:

~~~bash
javac --module-source-path src -d out -m com.acme.api,com.acme.service,com.acme.app
~~~

This command is suitable when sources are organized by module under a single module source path such as:

~~~text
src/
├── com.acme.api/
├── com.acme.service/
└── com.acme.app/
~~~

However, Maven/Gradle projects typically place each project's sources at `api/src/main/java`, `service/src/main/java`, `app/src/main/java`. In that case, **do not mechanically copy `--module-source-path src` from the earlier example**, because the layout does not match.

Build tools usually compile each project from its own source set, combining compiled artifacts of dependencies on the module path. This approach fits multi-project builds that have separate lifecycles and outputs per project.

## 5. Maven multi-module reactor

Maven uses a root aggregator POM to list the Maven modules to build. In this example, we set up one Maven project per JPMS module.

Structure:

~~~text
jpms-multi-project/
├── pom.xml
├── api/
│   ├── pom.xml
│   └── src/main/java/...
├── service/
│   ├── pom.xml
│   └── src/main/java/...
└── app/
    ├── pom.xml
    └── src/main/java/...
~~~

### 5.1. Root pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>jpms-multi-project</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>

  <modules>
    <module>api</module>
    <module>service</module>
    <module>app</module>
  </modules>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

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
~~~

`<modules>` informs Maven that there are three subprojects in the reactor. Maven uses dependency relationships between projects to compute the required build order; you should not rely on the ordering of `<module>` lines as a substitute for dependency declarations.

The `maven.compiler.release=17` property provides consistent compilation targeting Java 17. In this example, Maven Compiler Plugin 3.13.0 is used to illustrate configuration; it does not mean every system must use that exact version.

### 5.2. api/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.acme</groupId>
    <artifactId>jpms-multi-project</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>api</artifactId>
  <packaging>jar</packaging>
</project>
~~~

The artifact is named `api`, whereas the JPMS module is named `com.acme.api` in the descriptor. Maven artifactId and JPMS module name do not have to match.

### 5.3. service/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.acme</groupId>
    <artifactId>jpms-multi-project</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>service</artifactId>

  <dependencies>
    <dependency>
      <groupId>com.acme</groupId>
      <artifactId>api</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
~~~

The Maven dependency tells the reactor that service must be built after api and provides the api artifact for compiling service. The service descriptor **must still** contain:

~~~java
requires transitive com.acme.api;
~~~

A Maven dependency entry and a JPMS directive solve two different tasks.

### 5.4. app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.acme</groupId>
    <artifactId>jpms-multi-project</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>app</artifactId>

  <dependencies>
    <dependency>
      <groupId>com.acme</groupId>
      <artifactId>service</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
~~~

App declares a direct Maven dependency only on service. Because service's api dependency has the default compile scope, standard Maven dependency transitivity brings the api artifact into app's compile graph. This helps the compiler find the api module, while JPMS's `requires transitive` lets the app module read api through service.

In systems requiring strict direct dependency control or using different scope configurations, declaring an explicit dependency on api in app may be necessary to ensure the artifact is present. Do not change descriptors blindly: examine the public API and the actual dependency graph.

### 5.5. Building with the Maven reactor

Run from the root directory:

~~~bash
mvn clean package
~~~

Maven builds the Maven modules in the appropriate dependency order. For the example, the logical order is:

~~~text
api -> service -> app
~~~

Build only app and the projects it depends on:

~~~bash
mvn -pl app -am clean package
~~~

Where:

- `-pl app` selects the app project in the reactor.
- `-am` (*also make*) includes projects that app depends on so Maven builds them together.
- `clean package` deletes old outputs and builds the JARs.

If you run only `mvn -pl app package` when app's dependencies have not yet been installed in the local repository, the build can fail because the artifacts are unavailable. `-am` is the explicit way to have Maven pull upstream projects into the reactor run.

### 5.6. Inspecting JARs and running the Java module

After packaging, the JARs look like:

~~~text
api/target/api-1.0.0.jar
service/target/service-1.0.0.jar
app/target/app-1.0.0.jar
~~~

View the module descriptors:

~~~bash
jar --describe-module --file api/target/api-1.0.0.jar
jar --describe-module --file service/target/service-1.0.0.jar
jar --describe-module --file app/target/app-1.0.0.jar
~~~

On Linux/macOS:

~~~bash
java --module-path "api/target/api-1.0.0.jar:service/target/service-1.0.0.jar:app/target/app-1.0.0.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

On Windows PowerShell:

~~~powershell
java --module-path "api/target/api-1.0.0.jar;service/target/service-1.0.0.jar;app/target/app-1.0.0.jar" -m com.acme.app/com.acme.app.Main
~~~

Expected output:

~~~text
Hello, JPMS
~~~

The JARs must have `module-info.class` directly at the root. Merely having Maven package a `jar` is not enough to confirm it is an explicit named module.

## 6. Gradle multi-project build

Gradle organizes subprojects via `settings.gradle`. Each project has its own dependency configurations; Gradle executes the necessary tasks according to project dependencies.

Structure:

~~~text
jpms-multi-project/
├── settings.gradle
├── build.gradle
├── api/
│   ├── build.gradle
│   └── src/main/java/...
├── service/
│   ├── build.gradle
│   └── src/main/java/...
└── app/
    ├── build.gradle
    └── src/main/java/...
~~~

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'jpms-multi-project'

include 'api', 'service', 'app'
~~~

This declaration tells Gradle there are three projects. It does not automatically create dependency relationships between them.

### 6.2. Root build.gradle

~~~groovy
subprojects {
    apply plugin: 'java'

    java {
        modularity.inferModulePath = true
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
        options.encoding = 'UTF-8'
    }
}
~~~

`modularity.inferModulePath = true` instructs the Java plugin to infer the module path for compilation based on dependencies with appropriate module identification. This property helps the build tool place compiled modules/JARs onto the proper path instead of only the classpath.

When a project has `module-info.java` while a library dependency lacks a stable module name, you need to check how the dependency is classified. Not every JAR listed in `dependencies` is handled identically by the resolver across all Gradle versions/configurations.

### 6.3. api/build.gradle

With the root configuration above, `api/build.gradle` can remain empty:

~~~groovy
// api has no project dependencies yet.
~~~

The api project still uses the Java plugin applied from root, creating `compileJava` and `jar` tasks for the default source set.

### 6.4. service/build.gradle

Because service's public API returns `Message` from api, apply the Java Library plugin and declare the dependency as `api`:

~~~groovy
apply plugin: 'java-library'

dependencies {
    api project(':api')
}
~~~

Here, two concepts must be distinguished:

- Gradle `api project(':api')`: service's dependency is exposed to the consumer compilation graph.
- JPMS `requires transitive com.acme.api;`: any module reading service also reads the api module.

They are related but not equivalent. A Gradle `api` configuration does not automatically generate `requires transitive` in `module-info.java`, and `requires transitive` does not automatically add a project dependency in Gradle.

If the api type were used only internally within service, you could switch the Gradle dependency to:

~~~groovy
dependencies {
    implementation project(':api')
}
~~~

and change the service descriptor to `requires com.acme.api;`. Choosing between `api` and `implementation` depends on the public API contract and how Gradle separates compile and runtime dependencies.

### 6.5. app/build.gradle

The application needs the Application plugin to provide the `run` task:

~~~groovy
apply plugin: 'application'

dependencies {
    implementation project(':service')
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

`mainModule` is the JPMS module name, while `mainClass` is the fully qualified Java class name. They do not necessarily equal the Gradle project name.

### 6.6. Building and running with Gradle

From root:

~~~bash
./gradlew :app:build
~~~

On Windows:

~~~powershell
.\gradlew.bat :app:build
~~~

Gradle computes the required task dependencies to compile api, then service, then app. To run:

~~~bash
./gradlew :app:run
~~~

On Windows:

~~~powershell
.\gradlew.bat :app:run
~~~

Expected output:

~~~text
Hello, JPMS
~~~

Inspect the project graph:

~~~bash
./gradlew projects
~~~

Inspect app's compile dependencies:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

Inspect runtime dependencies:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Dependency configurations show which artifacts Gradle passes to each task. When debugging the module path, combine them with descriptors and the actual compiler arguments.

## 7. Why is a build dependency not enough to compile a module?

A very common mistake in multi-project builds is thinking that:

~~~groovy
dependencies {
    implementation project(':api')
}
~~~

or:

~~~xml
<dependency>
  <groupId>com.acme</groupId>
  <artifactId>api</artifactId>
  <version>1.0.0</version>
</dependency>
~~~

already creates a module readability relationship.

In JPMS, if service imports from api, then service's `module-info.java` must contain `requires com.acme.api;` or `requires transitive com.acme.api;` according to the contract.

The complete relationship:

~~~text
Build configuration:
  service -> artifact api
  (supplies compiled JAR to javac)

JPMS descriptor:
  com.acme.service -> com.acme.api
  (declares readability in the module graph)
~~~

Missing either layer can cause compilation errors. Therefore, when migrating a classpath project to JPMS, update **both the build graph and the module graph**, rather than merely adding `module-info.java`.

## 8. Three common compilation error patterns

### 8.1. Module not found

Example:

~~~text
error: module not found: com.acme.api
~~~

This can happen when:

- The service project has not declared a dependency on the api project in Maven/Gradle.
- The api artifact has not been built or is absent from the compiler module path.
- The module name in `requires` does not match the actual name of the artifact.
- The compiler is using the wrong source/output directory or build profile.

How to fix:

1. Confirm `api/src/main/java/module-info.java` defines `module com.acme.api`.
2. Confirm the service project declares a build dependency on api.
3. Check the module path that `javac` actually receives.
4. Build reactor/project dependencies together rather than compiling a lone subproject when upstream artifacts are not ready.

### 8.2. Package not visible due to missing requires

A message may say:

~~~text
package com.acme.api is not visible
(package com.acme.api is declared in module com.acme.api,
 but module com.acme.service does not read it)
~~~

Here the compiler already sees the module containing the package, but the consuming module lacks readability. Fix `requires` in the **consuming** module's descriptor.

### 8.3. Package not exported

Example:

~~~text
package com.acme.api is not visible
(package com.acme.api is declared in module com.acme.api,
 which does not export it)
~~~

Add `exports com.acme.api;` in the **providing** module's descriptor, if that package is genuinely meant to be exposed to consumers.

Do not use `--add-exports` as the default solution for an internal package. If the application is importing an implementation class outside the public API, review the design.

## 9. requires transitive and API dependencies in Maven/Gradle

Suppose service has a public method:

~~~java
public Message greet(String name)
~~~

Where `Message` comes from the api module. App uses the `Message` type at compile time.

To ensure the entire pipeline works:

| Layer | Service declares | Meaning |
|---|---|---|
| JPMS | `requires transitive com.acme.api;` | App reading service inherits readability to api |
| Maven | Dependency on artifact `api` | Maven reactor and compiler have the api module |
| Gradle | `api project(':api')` | Service's public API dependency is exposed to the consumer's compile graph |

Not every project needs all three lines configured identically. Depending on the build tool and design, both **JPMS readability** and **the compiler's ability to locate the artifact** must be satisfied.

### 9.1. If requires transitive is changed to requires

When service changes:

~~~java
requires transitive com.acme.api;
~~~

to:

~~~java
requires com.acme.api;
~~~

an app that only declares `requires com.acme.service;` will no longer automatically read the api module through service. If app still directly uses `Message`, declare the direct dependency in app:

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.api;
}
~~~

The build graph must also ensure the api artifact is present for app's compilation. Do not assume a transitive dependency in the build tool replaces a JPMS readability relationship.

### 9.2. requires static

`requires static` is used when a module dependency is required at compile time but is allowed to be absent at runtime by design. It does not replace Maven/Gradle dependency configuration and does not automatically put classes/JARs onto the compiler module path.

For an annotation API used only at compile time:

~~~java
module com.acme.service {
    requires static com.acme.annotations;
}
~~~

The build tool still needs to provide the annotation artifact during compilation. Annotation processors also have their own processor path/plugin configuration, which cannot be inferred solely from a `requires static` line.

## 10. Compiling with source modules vs. compiled module JARs

Each subproject can depend on one of two sources:

- Compiled output of a project dependency (class directory containing `module-info.class`).
- A packaged modular JAR.

During development, build tools often reuse compiled classes across projects to avoid repackaging JARs after every change. At release time, the JAR is the standard artifact used on the module path.

The core point: the compiler must see the module descriptor and corresponding classes via the module path, regardless of whether the module comes from a directory or a JAR.

To verify a JAR has a descriptor:

~~~bash
jar --describe-module --file api/target/api-1.0.0.jar
~~~

To list class files inside:

~~~bash
jar tf api/target/api-1.0.0.jar
~~~

The output should contain:

~~~text
module-info.class
com/acme/api/Message.class
~~~

A Maven artifact name is not a JPMS module name. Always trust the actual descriptor rather than guessing from the filename.

## 11. Differences between compile classpath and module path

In traditional Java projects, dependencies typically sit on the classpath. With explicit named modules, the compiler needs to recognize named modules to verify `requires` and `exports`.

Some common pitfalls:

**JAR on the classpath while the descriptor requires the module name**

~~~text
module com.acme.service {
    requires com.acme.api;
}
~~~

If the api artifact is only supplied on the classpath, the compiler cannot find it under the expected named module name. Ensure the build tool places the artifact properly on the module path.

**Libraries lacking module-info.class**

A JAR placed on the module path can act as an automatic module. The module name may come from `Automatic-Module-Name` or the filename. Use:

~~~bash
jar --describe-module --file libs/legacy.jar
~~~

to determine the exact name that `requires` must use.

**Keeping the same library on both the classpath and module path**

This can cause version confusion, class identity issues, or confusing diagnostics. Do not include the same artifact twice in a single compile/run invocation unless there is a clearly controlled technical reason.

## 12. Split package errors in a multi-project build

Two subprojects can inadvertently contain classes belonging to the same package:

~~~text
api/src/main/java/com/acme/shared/Model.java

service/src/main/java/com/acme/shared/Helper.java
~~~

If api and service become two different named modules both containing `com.acme.shared`, that is a split package.

The consequence depends on how modules are resolved and how the compiler/linker views the package. A typical error may look like:

~~~text
module com.acme.app reads package com.acme.shared
from both com.acme.api and com.acme.service
~~~

A sustainable fix is to:

- Move shared API classes into a single owning module.
- Rename service's implementation package to a namespace such as `com.acme.service.internal`.
- Update `exports`, `requires`, and imports.
- Perform a clean build to eliminate old package bytecode.

Do not add `--add-exports` to work around a split package: export flags alter accessibility, not which module owns a package.

## 13. Checking compilation order and dependency resolution

### 13.1. With Maven

Run the full reactor:

~~~bash
mvn clean verify
~~~

Or build app along with its dependencies:

~~~bash
mvn -pl app -am package
~~~

If an error occurs only when running Maven inside the standalone app directory, the cause may be that upstream artifacts have not been installed or the version in the repository does not match the reactor.

Inspect the Maven dependency tree:

~~~bash
mvn -pl app dependency:tree
~~~

### 13.2. With Gradle

~~~bash
./gradlew :app:build
~~~

View the task graph and more detailed logs when needed:

~~~bash
./gradlew :app:compileJava --info
~~~

Inspect dependency configurations:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

If app compilation cannot see `com.acme.api`, check:

- Does `service/build.gradle` have `api project(':api')` or only `implementation`?
- Does `service/module-info.java` have `requires transitive com.acme.api;`?
- Does app need a direct dependency on api?
- Is the compile task placing named modules properly on the module path?

These are two different configuration layers, so cross-check both the build tool and the JPMS descriptors.

## 14. Unit tests in a multi-project modular build

Having `module-info.java` in a project does not mean test frameworks will automatically run on the module path like the production application.

Common scenarios:

- Test frameworks need reflection to discover/run test classes.
- Unit tests reside in `src/test/java`, while the main module is strongly encapsulated.
- Test frameworks or build plugins use different strategies for `--patch-module`, module path, and classpath.
- Tests using mocking or reflection into private members may require `opens`/`--add-opens` within test scope.

How to verify:

1. Build main code successfully first.
2. Run unit tests for each project.
3. Run integration tests for the app project with real dependencies.
4. Inspect the actual test runner and compiler arguments when accessibility errors appear.
5. Avoid opening the entire production module merely because a test framework needs reflection; prefer configuring the test plugin appropriately.

Maven:

~~~bash
mvn test
~~~

Gradle:

~~~bash
./gradlew test
~~~

Worth noting: `compileJava` succeeding does not guarantee `test` runs properly, and tests passing on the classpath do not prove that production runtime on the module path is also right.

## 15. Compiling modules requiring service providers

If a system separates SPI and implementation into different subprojects:

~~~text
spi -> provider -> app
~~~

Descriptors might look like:

SPI module:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Provider module:

~~~java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingProvider
        with com.acme.provider.DefaultGreetingProvider;
}
~~~

App module:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingProvider;
}
~~~

In the build tool, the provider project must be packaged and supplied in the appropriate runtime configuration/module path. Merely declaring `provides` in the descriptor without distributing the provider module or adding it to the right configuration can prevent `ServiceLoader` from finding the provider at runtime.

This illustrates why the compile graph and runtime graph can differ: app can compile with only the SPI, while the provider must appear at runtime.

## 16. Integrating with CI/CD

A common pipeline might consist of:

~~~text
Checkout source
      |
      v
Resolve build dependencies
      |
      v
Compile api
      |
      v
Compile service
      |
      v
Compile app
      |
      v
Unit + integration tests
      |
      v
Package modular JARs
      |
      v
Run module-resolution smoke test
      |
      v
Publish artifacts
~~~

Ensure that:

- CI uses the right JDK/toolchain, for example Java 17 if sources use records.
- The build tool uses dependency locking or consistent version constraints.
- Artifact module descriptors are not stripped from JARs during packaging.
- Production launch commands use a module path containing all required modules.
- CI does not accidentally run the app on the classpath while production runs on the module path.
- The module path is constructed appropriately for the operating system and build profiles.

A minimal post-packaging smoke test:

~~~bash
java --module-path "api/target/api-1.0.0.jar:service/target/service-1.0.0.jar:app/target/app-1.0.0.jar" \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

On Windows, change `:` to `;`. Using `--show-module-resolution` clearly shows which modules were resolved, while the app output confirms basic functionality works.

## 17. Mistakes to avoid

**Configuring only requires and omitting build tool dependencies.** The compiler does not automatically download module JARs from names in `module-info.java`.

**Configuring only build tool dependencies and omitting requires.** An artifact existing does not mean the consuming module is allowed to read it.

**Equating Gradle project name / Maven artifactId with JPMS module name.** JPMS names come from descriptors or automatic module rules.

**Using requires transitive for every dependency.** Transitivity should reflect the part of the API consumers need to read, not expand the graph uncontrollably.

**Putting all libraries on the classpath to bypass compile errors.** This defeats modular control and can hide package/accessibility issues.

**Moving implementation packages of multiple projects into one shared namespace.** This can create split packages when those projects become named modules.

**Assuming the module path separator is the same on Windows and Linux.** Use `;` on Windows and `:` on Linux/macOS.

**Skipping a clean build after renaming packages.** Old bytecode can linger in outputs and leak into artifacts.

**Running Maven on a subproject without bringing upstream dependencies into the reactor.** Use `-am` when dependent projects need to be built together.

## 18. Recommended workflow

When migrating an existing multi-project build to JPMS, follow this sequence:

1. List all Maven/Gradle subprojects and their dependency relationships.
2. Assign stable JPMS module names to each project you genuinely want to modularize.
3. Place `module-info.java` in the right source root of each project.
4. Migrate lower-level projects first, such as API/model projects with few dependencies.
5. Author `requires`/`exports` according to actual public API usage.
6. Update Maven/Gradle project dependencies so the compiler finds all artifacts.
7. Verify module-path inference or configure the module path explicitly.
8. Compile from the root using the reactor/task graph rather than building random modules alone.
9. Use `jar --describe-module` to confirm modular JARs.
10. Run the app on the module path and inspect `--show-module-resolution`.
11. Test frameworks, reflection, providers, and CI.
12. Proceed to migrate additional projects/libraries only once earlier milestones are stable.

## 19. Self-check questions

**Question 1.** A Maven reactor has three modules `api`, `service`, `app`. Are their JPMS names necessarily `api`, `service`, and `app` respectively?

**Answer:** Not necessarily. Maven artifactId/build module names differ from JPMS module names. In the example, the JPMS names are `com.acme.api`, `com.acme.service`, and `com.acme.app`.

**Question 2.** Service declares the Gradle dependency `implementation project(':api')`, but `module-info.java` lacks `requires com.acme.api;`. Does the compiler infer the readability relationship automatically?

**Answer:** No. The build dependency makes the artifact discoverable, whereas JPMS requires readability from the descriptor.

**Question 3.** Why can app in the example write only `requires com.acme.service;` and still use `Message` from api?

**Answer:** Because service declares `requires transitive com.acme.api;` and api exports the package containing `Message`; the build tool must also supply the api artifact to the compiler.

**Question 4.** Why does service in Gradle use `api project(':api')` instead of `implementation`?

**Answer:** Because service's public API uses the `Message` type from api. Gradle `api` propagates the dependency to the consumer's compile graph, independently of JPMS `requires transitive`.

**Question 5.** The app POM already declares service, but running Maven inside the app directory reports it cannot find the service artifact. What should be done?

**Answer:** Run the reactor from root with `mvn -pl app -am package` or ensure the appropriate upstream artifact has been installed/published. Also verify artifact version and dependency scope.

**Question 6.** A project has `module-info.java`, yet `javac` reports `module not found: com.acme.api`. What should be checked first?

**Answer:** Check the actual module name, build dependency, and compiler module path. If api was just compiled into a directory/JAR, confirm that output is supplied to the failing compile step.

**Question 7.** In a multi-project build, can a single project contain multiple JPMS modules?

**Answer:** More complex build designs are possible, but the simplest, most maintainable setup is typically one JPMS named module per Java subproject with its own descriptor and artifact.

**Question 8.** An app runs on the classpath, yet moving to the module path reports package is not visible. Why?

**Answer:** JPMS enforces readability/exports rules; public classes in unexported packages, or modules without corresponding requires in the consuming module, cannot be accessed automatically.

**Question 9.** A test framework cannot use reflection into a package of the app module. Should you automatically switch to `open module` for production?

**Answer:** Do not do so by default. Check the test runner configuration first, open only the needed package to the right framework/module, and avoid widening permissions unnecessarily in production.

**Question 10.** How can you tell whether a JAR after `mvn package` is truly an explicit module?

**Answer:** Run `jar --describe-module --file path/to/app.jar` or check for `module-info.class` at the JAR root. Do not infer solely from the `.jar` file extension.

## Summary

Compiling Java modules in a multi-project build requires coordinating **two dependency systems**:

- Maven/Gradle determine artifacts, compile classpath/module path, and build order.
- JPMS determines module readability, package exports, and compile/runtime constraints.

A stable design declares accurate project dependencies in the build tool, accurate `requires`/`requires transitive` in descriptors, and accurate `exports` for genuinely public API packages. After building, inspect the modular JARs and run via `java --module-path ... -m ...` to ensure both compile time and runtime operate on a consistent module graph.