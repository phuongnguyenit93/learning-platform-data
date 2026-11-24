# Gradle `implementation`, `api`, `runtimeOnly`, `compileOnly`, and `testImplementation` Configurations

## 1. Why Does Gradle Need Multiple Dependency Configurations?

A Spring Boot application typically uses many libraries: Spring Web for writing HTTP APIs, a JDBC driver for connecting to a database, Lombok for compile-time assistance, JUnit for testing, and internal libraries written by the team. These libraries **do not all need to appear at the same time or on the same classpath**.

In Gradle, a **dependency configuration** specifies the intended usage of a dependency. When declaring:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

we are stating three different things:

- **implementation**: the library is needed to compile and run application code.
- **runtimeOnly**: the library is only needed when the application runs; Java sources do not directly import that library at compile time.
- **testImplementation**: the library is only needed for test code/tasks, not as a production application dependency.

In a **library module** using the **java-library** plugin, Gradle also provides **api** to expose dependencies containing types that appear in the library's public interface. **compileOnly** is for libraries needed only during compilation.

**Lesson scope:** the five configurations **implementation**, **api**, **runtimeOnly**, **compileOnly**, and **testImplementation** in Gradle Java/Spring Boot projects. They relate to BOMs and transitive dependencies, but are not ways of defining a REST API, Java versions, or Gradle task commands.

## 2. Comparison Table: Which Classpaths Contain the Dependency?

The following table describes **a dependency declared in a library module using `java-library`**, which is then referenced by another Java module via **`implementation project(':core')`**.

| Configuration | When compiling **declaring module's main code** | When running **declaring module's main code** | On **consuming module's compileClasspath** | On **consuming module's runtimeClasspath** | When compiling/running declaring module's tests |
| --- | --- | --- | --- | --- | --- |
| **implementation** | Yes | Yes | Not exported directly as API | Yes | Yes, via main code classpath |
| **api** | Yes | Yes | Yes | Yes | Yes |
| **runtimeOnly** | No | Yes | No | Yes | Yes at test runtime, not at test compile |
| **compileOnly** | Yes | No | No | No | Not automatically placed on test classpath |
| **testImplementation** | No | No | No | No | Yes, for test compile and test runtime |

**Reading the table accurately:** "No" indicates what *this configuration provides by contract*, which does not rule out a library happening to be present via another dependency path. Gradle has **variant-aware dependency resolution**; for a project using `java-library`, consumers typically select **apiElements** at compile time and **runtimeElements** at runtime. Thus a library's **implementation** dependency still appears at the consumer's runtime, even though it is hidden from the consumer's compile classpath.

A quick mental diagram:

~~~text
                  module declaring dependency                  module consuming library
              compile main       runtime main               compile       runtime
api                ✓                  ✓                        ✓             ✓
implementation     ✓                  ✓                        —             ✓
compileOnly        ✓                  —                        —             —
runtimeOnly        —                  ✓                        —             ✓
testImplementation is only for internal test compile/run; not published to consumers
~~~

"—" means not provided by that configuration. This is a scope diagram, not a diagram of all dependency relationships in Gradle.

## 3. Apply the Right Plugin Before Declaring Dependencies

A Spring Boot application's **build.gradle** commonly declares:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

In this module, **implementation**, **runtimeOnly**, **compileOnly**, and **testImplementation** are available courtesy of the Java plugin. However, **api is not a default configuration of the `java` plugin**. Trying to write **`api '...'`** in a module that only applies **java** can fail with "Could not find method api()".

For a **Java library module** whose public API is used by other projects, use:

~~~groovy
plugins {
    id 'java-library'
}
~~~

**`java-library` extends the `java` plugin**, adding **api**, **compileOnlyApi**, and outgoing variants for consumers. There is no need to apply both **java** and **java-library**: applying `java-library` already includes the capabilities of the `java` plugin.

In a multi-module project, each module can use different plugins. A **:core** module typically produces a library JAR and uses **java-library**; an **:app** module runs Spring Boot and uses **java + org.springframework.boot**. Avoid applying the Spring Boot plugin to every plain library merely because they live in the same repository.

## 4. implementation: Dependencies for a Module's Internal Code

Suppose module `:core` uses Google Guava inside a method:

~~~groovy
dependencies {
    implementation 'com.google.guava:guava:33.3.1-jre'
}
~~~

Gradle adds Guava and its dependencies to `:core`'s **compileClasspath** and **runtimeClasspath**. Inside `:core`'s Java classes, you can use **com.google.common.base.CharMatcher**.

When module `:app` depends on `:core`:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

then **app code can call public classes defined by core**; however, Guava declared as **implementation** in core is **not exported to app's compiler as part of the API**. If app wants to import Guava directly, app should declare its own Guava dependency or receive it via a clearly designed API.

**Why default to `implementation`?**

1. **Proper encapsulation**: helper libraries internal to `:core` do not automatically become API commitments to users of `:core`.
2. **Smaller consumer compile classpath**: app's compiler does not have to see every internal detail of core, often improving build performance.
3. **Fewer unnecessary rebuilds**: changing an implementation dependency unrelated to core's binary API may avoid forcing dependent modules to recompile.
4. **Easier maintenance**: you can swap internal libraries in core without forcing consumers to fix imports just because they misused a transitive dependency.

**Note:** "Hidden from the consumer's compile classpath" **does not mean** an implementation dependency is omitted at runtime. If core uses Guava when running, Guava must still exist in app's runtime graph.

## 5. api: Dependencies Belonging to a Library's Public Contract

Suppose `:core` exposes a public method returning **org.apache.commons.lang3.tuple.Pair**, a type from Apache Commons Lang:

~~~groovy
dependencies {
    api 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

This is the right choice because **Pair is part of the public signature**. Code in `:app` needs to know **Pair** to compile calls or declare variables of type Pair:

~~~java
Pair<String, String> result = LabelMaker.describe("  java  ");
~~~

If `:core` declares Commons Lang with **implementation**, `:core` itself compiles, but Gradle **does not guarantee** Commons Lang appears on `:app`'s compile classpath. Declaring with **api** lets consumers compile directly against that public type.

**When to use `api`?** When a dependency contains types appearing in a **public/protected method return type, parameter, generic signature, superclass, implemented interface, public field**, or public annotation that consumers must see at compile time. Gradle documentation calls this part of the **ABI — Application Binary Interface**.

**When not to use `api`?** When a dependency only serves algorithms, logging, database adapters, internal mappers, or helpers that do not appear in the public contract. Using `implementation` keeps library boundaries clean.

Distinguish **api** in Gradle from an "HTTP API": the **api** configuration does not create REST endpoints, grant access permissions, or control Spring Security.

### A Special Case: compileOnlyApi

The **java-library** plugin also provides **compileOnlyApi**. It allows exposing types needed by consumers **at compile time**, without **requiring their presence at runtime**. Use it for annotation types or specialized APIs guaranteed to be provided by another environment, after verifying the runtime contract. Do not carelessly move runtime-required dependencies to `compileOnlyApi`.

## 6. runtimeOnly: Adding Dependencies Only at Runtime

A classic example is a **JDBC driver**. A Spring Boot application writes code against **java.sql**, **javax.sql**, or **JdbcTemplate**, while the concrete database driver implementation is loaded when connecting:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

- **spring-boot-starter-jdbc** contains the APIs/classes the application needs to code with Spring JDBC, declared with `implementation`.
- **com.h2database:h2** is the database driver/engine used at runtime; a typical example does not need to import H2 classes directly at compile time.
- On startup with H2 on the classpath and no external database configured, Spring Boot can auto-configure an in-memory H2 database for the application using JDBC.

**runtimeOnly is not on compileClasspath**. If main source code writes **`import org.h2.Driver;`**, the compiler will not find the H2 class through `runtimeOnly`; either remove the import depending on a concrete implementation, or declare the dependency according to actual compile needs.

With a Spring Boot executable JAR, **bootJar** uses the runtime classpath to collect libraries needed when running. A `runtimeOnly` dependency is usually placed into `BOOT-INF/lib` of the executable JAR if it is in the runtime graph; at deployment, still check the actual artifact and packaging policy.

**Note on switching drivers:** You can use the PostgreSQL driver at runtime when you have configured a real URL, credentials, and database; merely swapping H2 for PostgreSQL does **not** guarantee the app starts without a database or matching connection properties. That is why H2 is better suited for a standalone lab.

`runtimeOnly` is also useful for **SPI implementations**, plugins, or logger backends loaded at runtime. Do not use `runtimeOnly` for libraries whose types source code must call directly at compile time.

## 7. compileOnly: Dependencies Only for Compilation

**compileOnly** adds classes to main **compileClasspath**, without adding them to main **runtimeClasspath** or exposing them to consumers like `api`. Commonly used when:

- An API is supplied by the runtime container/host and is **genuinely guaranteed to be present** in the corresponding runtime environment.
- An annotation only assists the IDE/compiler and **does not need to exist at runtime**.
- Lombok annotations are needed for the compiler to recognize symbols, while Lombok itself should not be shipped in the runtime application libraries.

Example with Lombok in **build.gradle** (illustrative dependency snippet):

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.34'
    annotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

**Why are two lines needed?** `compileOnly` supplies annotations like **@Getter** and **@RequiredArgsConstructor** to the compiler. However, for Lombok to **actually generate code**, the processor must be placed on the **annotationProcessor** configuration, because Gradle uses a separate processor path. Declaring Lombok only in `compileOnly` **does not ensure** code generation is enabled.

If **test code** also uses Lombok annotations, you may need:

~~~groovy
dependencies {
    testCompileOnly 'org.projectlombok:lombok:1.18.34'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

This is an **additional configuration for tests**, not a replacement for the two main lines. Main's `compileOnly` does not automatically flow into **testCompileClasspath**. Other annotation processors can also use `annotationProcessor`; never equate **compileOnly** with **annotationProcessor**.

**Serious mistake:** Moving a library actually called by the application at runtime (such as Jackson Databind, Spring Web, or a driver when app code directly uses driver classes) to `compileOnly` can cause the app to compile cleanly and then crash with **NoClassDefFoundError** or **ClassNotFoundException** when running. `compileOnly` is only appropriate when the dependency is unneeded at runtime *or* another environment guarantees it will be provided.

## 8. testImplementation: Dependencies for Tests

In the Java plugin, **src/main/java** holds application sources; **src/test/java** holds test sources. **testImplementation** supplies dependencies for both **compiling tests** and **running tests**, without putting test dependencies into main runtime or public artifacts.

Spring Boot example:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The test starter brings in test libraries managed by Spring Boot, typically JUnit Jupiter, AssertJ, and Spring testing utilities. In a plain Java `:core` module without Spring Boot dependency management, you can declare explicit test versions:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**testRuntimeOnly** appears only when running tests; **testCompileOnly** appears only when compiling tests. These configurations differ from `testImplementation`, even though all belong to the test scope.

Note that the Java plugin's **testImplementation** configuration inherits appropriate dependencies from main's **implementation**: test code can call application classes and the libraries used to implement the application. However, **testImplementation dependencies do not flow back into src/main/java**. Putting **`import org.junit.jupiter.api.Test;`** in main code while declaring JUnit only in `testImplementation` means `compileJava` will not find that type by contract.

## 9. Complete Lab: One Core Library and One Spring Boot Application

The following lab demonstrates **all five configurations** in a Gradle Groovy DSL repository. There are two modules: **:core** exposes a public type from Commons Lang and uses Guava internally; **:app** is a Spring Boot application consuming core, using H2 at runtime and Spring Boot Starter Test for testing.

### 9.1. Directory Structure

~~~text
scope-demo/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/
│       ├── main/java/com/example/core/LabelMaker.java
│       └── test/java/com/example/core/LabelMakerTest.java
└── app/
    ├── build.gradle
    └── src/main/java/com/example/app/DemoApplication.java
~~~

A real project should have the Gradle Wrapper (**gradlew**, **gradlew.bat**, **gradle/wrapper/**) generated/provided with a Gradle version compatible with Spring Boot 3.3.x and JDK 17. The commands below use the wrapper; if creating the skeleton manually without a wrapper, generate the wrapper using an installed Gradle before invoking **./gradlew**.

**settings.gradle** at the root:

~~~groovy
rootProject.name = 'scope-demo'
include 'core', 'app'
~~~

A root `build.gradle` is not required in this example because each module declares its own plugins, repositories, and Java toolchain; in larger projects, shared configuration can be consolidated via convention plugins.

### 9.2. File core/build.gradle: java-library, api, implementation, compileOnly, testImplementation

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    api 'org.apache.commons:commons-lang3:3.14.0'
    implementation 'com.google.guava:guava:33.3.1-jre'
    compileOnly 'org.jetbrains:annotations:24.1.0'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Because **Commons Lang Pair** appears in the public return type, it belongs in `api`. **Guava** is only used inside the `normalize` helper, so it belongs in `implementation`. JetBrains **@NotNull** only annotates a private helper for compile-time static analysis, so it goes into `compileOnly`. **JUnit** is only for tests.

**core/src/main/java/com/example/core/LabelMaker.java**:

~~~java
package com.example.core;

import com.google.common.base.CharMatcher;
import org.apache.commons.lang3.tuple.Pair;
import org.jetbrains.annotations.NotNull;

import java.util.Locale;

public final class LabelMaker {
    private LabelMaker() {
    }

    public static Pair<String, String> describe(String input) {
        return Pair.of("normalized", normalize(input));
    }

    @NotNull
    private static String normalize(String input) {
        return CharMatcher.whitespace()
                .trimFrom(input)
                .toUpperCase(Locale.ROOT);
    }
}
~~~

This is a **complete Java file**. `LabelMaker`'s public API exposes **Pair**. Its internal implementation uses **CharMatcher** and a compile-time annotation; consumers do not need to import Guava or JetBrains annotations to call **describe**.

**core/src/test/java/com/example/core/LabelMakerTest.java**:

~~~java
package com.example.core;

import org.apache.commons.lang3.tuple.Pair;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LabelMakerTest {
    @Test
    void normalizesWhitespaceAndUppercase() {
        Pair<String, String> actual = LabelMaker.describe("  java  ");
        assertEquals(Pair.of("normalized", "JAVA"), actual);
    }
}
~~~

JUnit exists only in `testImplementation`/`testRuntimeClasspath`; `LabelMaker.java` has no JUnit imports. The test passes when Java 17, Gradle plugins, and dependencies are downloadable.

### 9.3. File app/build.gradle: Spring Boot, implementation, runtimeOnly, testImplementation

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**The BOM from Spring Boot** manages versions for Spring Boot-supported dependencies, because app applies both the Spring Boot plugin and **io.spring.dependency-management**. Therefore, the example can omit versions on **spring-boot-starter-web**, **spring-boot-starter-jdbc**, **h2**, and **spring-boot-starter-test**. Do not assume every dependency on Maven Central is in the BOM; other libraries may require explicit versions just as core did.

**app/src/main/java/com/example/app/DemoApplication.java**:

~~~java
package com.example.app;

import com.example.core.LabelMaker;
import org.apache.commons.lang3.tuple.Pair;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class LabelController {
        @GetMapping("/label")
        String label() {
            Pair<String, String> result = LabelMaker.describe("  java  ");
            return result.getRight();
        }
    }
}
~~~

This is a **complete** Java file for the Spring Boot application. App directly uses the **Pair** type even though app does not declare Commons Lang, because core exported that dependency via **api**. App can call **LabelMaker.describe** thanks to **`implementation project(':core')`**. **Guava** is not exposed as compile API to app, yet it is present at runtime so core can execute `normalize`.

When Spring Boot starts, the H2 driver is on `runtimeClasspath`, so `starter-jdbc` can initialize an embedded datasource. This application does not run SQL queries; H2 simply illustrates `runtimeOnly` and avoids requiring an external database server.

### 9.4. Build, Run the Application, and Verify Output

From the root directory **scope-demo** (with Gradle Wrapper and compatible JDK). Run:

~~~bash
./gradlew :core:test :app:bootJar
./gradlew :app:bootRun
~~~

- **:core:test** compiles core, compiles tests, and runs core's JUnit tests.
- **:app:bootJar** compiles app and creates an executable Spring Boot JAR with required runtime dependencies.
- **:app:bootRun** starts Spring Boot in the foreground; keep the process running in this terminal.
- On Windows, use **gradlew.bat** instead of **./gradlew**.

Open a **second terminal** and call:

~~~bash
curl http://localhost:8080/label
~~~

**Exact HTTP response body** of the endpoint:

~~~text
JAVA
~~~

The `curl` command may also show extra info depending on flags and environment, while Spring Boot prints its own logs in the `bootRun` terminal. The endpoint response body is the plain string **JAVA**, with no wrapping JSON object.

**Execution prerequisites:** Gradle/Spring Boot compatible with Java 17, plugins/dependencies downloadable, port 8080 free, and H2 on the runtime classpath. The example is designed to build/run standalone, though Gradle/Spring Boot log formatting is not guaranteed identical across every machine.

### 9.5. Swap api for implementation to See the Boundary

In **core/build.gradle**, temporarily try changing:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

This is a **replacement for the Commons Lang `api` line**, not core's entire `dependencies` block. When app compiles **DemoApplication.java** and references **Pair**, app's compiler can fail with **package org.apache.commons.lang3.tuple does not exist** or **cannot access Pair**, because core no longer exports Commons Lang via `apiElements`. If another dependency happened to bring Commons Lang onto app's `compileClasspath`, the error might be masked; in that case inspect the graph using the commands in section 11.

Change that line back to **api** so `LabelMaker`'s public contract is properly published. **Do not move Guava to `api`** just so app can import Guava, because `LabelMaker` does not expose Guava in its public signature.

## 10. Configurations and BOMs: Scope vs. Version

A **BOM (Bill of Materials)** supplies a set of managed versions/constraints; **implementation/api/runtimeOnly/testImplementation** decides **where a dependency is used on classpaths and how it propagates to consumers**. The two concepts solve two different problems.

With Spring Boot Gradle, there are two common approaches:

**Approach A — `io.spring.dependency-management`:** When the app applies the Spring Boot plugin and the **io.spring.dependency-management** plugin, the **spring-boot-dependencies** BOM matching the Spring Boot plugin version is imported automatically. The app example above uses this approach.

**Approach B — Native Gradle platform:** Do not apply `io.spring.dependency-management`, and instead declare the BOM directly in `dependencies`. Example **fragment in the application's `build.gradle`**:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Using **platform** applies the BOM's version constraints to classpaths containing the platform. This snippet is an **alternative way to manage versions**, not meant to be used alongside `io.spring.dependency-management`. If using a native platform, ensure the Spring Boot plugin is still declared if you want **bootJar/bootRun**.

**Common misconceptions:**

- Putting a dependency in `runtimeOnly` **does not automatically pick the latest version**.
- Putting a dependency in `api` **does not exempt it from version conflicts**.
- A BOM **does not automatically move** a dependency from `testImplementation` to `implementation`.
- Gradle can pick a version different from the BOM's "recommended" version due to other constraints/conflicts in the graph. **platform** and **enforcedPlatform** have different meanings; `enforcedPlatform` forces versions and can affect consumers, so only use it intentionally.
- For a **java-library** module, if you want the library's public API to carry version constraints to consumers, design how platforms/constraints are exposed through the appropriate API variant; a platform only on `implementation` is not always an API commitment to publish.

## 11. Inspect with Gradle Commands Instead of Guessing Classpaths

From the `scope-demo` root, the following commands display the **resolved dependency graphs**:

~~~bash
./gradlew :core:dependencies --configuration compileClasspath
./gradlew :core:dependencies --configuration runtimeClasspath

./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath

./gradlew :core:dependencies --configuration testCompileClasspath
./gradlew :core:dependencies --configuration testRuntimeClasspath
~~~

In **:core:compileClasspath** output, expect to see Commons Lang, Guava, and JetBrains annotations. In **:core:runtimeClasspath**, Commons Lang and Guava are present, while **JetBrains annotations** from `compileOnly` are not included via this configuration.

In **:app:compileClasspath**, through **`project(':core')`**, the compiler can see Commons Lang as an `api` dependency, while **core does not export Guava as compile API**. In **:app:runtimeClasspath**, core, runtime dependencies including Guava, Spring starters, and H2 are present. **Core's JUnit** is not exported as an app runtime dependency.

To understand **why a particular library was selected at that version**, run:

~~~bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency h2 --configuration runtimeClasspath
./gradlew :core:dependencyInsight --dependency guava --configuration runtimeClasspath
~~~

**dependencyInsight** shows dependency paths/versions involved in the specified configuration. If Gradle reports the dependency was not found, verify the project name, artifact name, and queried classpath; a dependency might only exist at runtime and therefore not appear when checking `compileClasspath`.

**Query `compileClasspath`/`runtimeClasspath`**, because **implementation**, **api**, and **runtimeOnly** are "buckets" for *declaring dependencies*, not always configurations used directly to resolve files for tasks. The classpaths reflect what the compiler and runtime actually see.

### Tests and Executable JAR

You can verify the tasks:

~~~bash
./gradlew :core:test
./gradlew :app:test
./gradlew :app:bootJar
~~~

With **bootJar**, dependencies in app's **runtimeClasspath** are normally packaged into the executable Boot JAR. Do not assume **testImplementation** gets packaged into the production JAR. You can inspect the JAR structure following the **`BOOT-INF/lib/`** convention; whether a specific class/library is present still depends on dependency resolution, plugins, and configured exclusions.

## 12. Common Mistakes

**Mistake 1 — Using `api` in a module that only declares the `java` plugin.** **api** is added by the Java Library plugin. If the module is truly a library with consumers, use **java-library**; if it is a Spring Boot application not exporting public types for other modules to compile against, **implementation** is usually better.

**Mistake 2 — Moving all dependencies to `api` for convenience.** That leaks internal details onto consumers' compile classpaths and increases coupling between modules. Only dependencies in the public ABI need **api**.

**Mistake 3 — Thinking `implementation` does not appear when consumers run.** With `java-library`, `implementation` is hidden from consumers' compile APIs, yet still belongs to `runtimeElements`. If core code calls Guava at runtime, app must have Guava in its runtime graph.

**Mistake 4 — Leaving an `implementation` type in a public signature.** Core's public method returns **Pair**, yet Commons Lang is declared as `implementation`, leaving consumers missing the type at compile time. Change it to **api** or redesign the public API so it does not expose that library.

**Mistake 5 — Importing a JDBC driver class when only `runtimeOnly` is declared.** `runtimeOnly` is not on `compileClasspath`. If code genuinely needs types from the dependency at compile time, `runtimeOnly` cannot be the sole source.

**Mistake 6 — Putting a Spring Boot starter/web into `compileOnly`.** Spring classes used by the application at runtime will be missing unless another environment supplies them completely. The result can be `ClassNotFoundException`/`NoClassDefFoundError`. For ordinary Boot applications, use `implementation` for starters.

**Mistake 7 — Adding Lombok only via `compileOnly`.** The annotation processor must be declared via **annotationProcessor**; if Lombok is used in tests, consider **testCompileOnly** and **testAnnotationProcessor** separately.

**Mistake 8 — Using `testImplementation` for `src/main/java` dependencies.** Test dependencies exist only on the test classpath; main code will not compile using test dependencies. Move the dependency into `implementation`/`api`/`compileOnly` as actually needed.

**Mistake 9 — Thinking `testImplementation` goes into the executable JAR.** `testImplementation` is not a main runtime dependency and is not shared with consumers. Test tools normally should not be in production artifacts.

**Mistake 10 — Blaming `implementation`/`runtimeOnly` when a version shifts.** Configurations determine classpaths; versions are determined by constraints, BOMs, direct/transitive dependencies, and conflict resolution. Use **dependencies** and **dependencyInsight** to inspect the graph.

**Mistake 11 — Believing a `runtimeOnly` driver guarantees database connection success.** Having the driver present is one condition; URL, credentials, network, permissions, schema, and database server must still be valid.

**Mistake 12 — Trying to use Gradle's old `compile` or `runtime` configurations.** Those legacy configurations were removed in Gradle 7.0 for the Java Library plugin. Use the current names and check the documentation for your repository's exact Gradle version.

## 13. Choosing Configurations in Practice

When adding a new dependency, answer in order:

1. **Are its types needed to compile main code?** If **no** yet needed at runtime, use **runtimeOnly**. If only for tests, consider `testImplementation`/`testRuntimeOnly`.
2. **If needed to compile main code, is it needed at runtime?** If **no**, and you know for certain another environment supplies it or types are compile-only, use **compileOnly**; if it is a processor, use **annotationProcessor**.
3. **If needed at both compile and runtime, does the module expose a public API to consumers?** If not, or if the dependency is strictly internal, use **implementation**.
4. **If the library's public API genuinely uses types from the dependency**, the module uses **java-library** and declares it with **api** (or `compileOnlyApi` in the special case where runtime is not needed).
5. **If only tests use the dependency**, use **testImplementation** and configure test runtime separately if needed.
6. **If using a Spring Boot BOM**, keep version management consistent, then verify the resolved classpaths.

| Scenario | Common Choice |
| --- | --- |
| Spring MVC/REST starter in a Boot app | **implementation** |
| String-processing library called only internally by core | **implementation** |
| External Pair/DTO type appearing in core's public API | **api** (with `java-library`) |
| H2/PostgreSQL JDBC driver loaded only at runtime | **runtimeOnly** |
| Lombok annotations in main source | **compileOnly** + **annotationProcessor** |
| JUnit/Spring Boot test support in `src/test` | **testImplementation** |
| Library needed only when running tests without test sources importing its types | **testRuntimeOnly** |

## 14. Official Documentation

- [Gradle — Java Library Plugin: API/implementation separation and configurations](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Spring Boot Gradle Plugin — Managing Dependencies and BOM](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Conclusion:** **implementation** keeps dependencies for compile/runtime internal to the module; **api** exposes dependencies belonging to the public ABI so consumers can compile; **runtimeOnly** participates only at runtime; **compileOnly** assists compilation only; **testImplementation** serves tests only. In Spring Boot, choose scopes by classpath need first, then use BOMs/dependency constraints to manage versions.