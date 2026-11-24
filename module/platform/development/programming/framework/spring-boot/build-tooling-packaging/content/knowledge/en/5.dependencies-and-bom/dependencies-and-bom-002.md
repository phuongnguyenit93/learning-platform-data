# `compile`, `runtime`, `provided`, and `test` Scopes in Maven

## 1. Goal and Context

In Maven, **dependency scope** determines which **classpaths** a library is placed on at each build stage and affects how Maven handles *transitive dependencies*. This is a crucial concept when building Java/Spring Boot applications: an application can compile cleanly yet miss a library at runtime, or bundle test-only libraries if the wrong scope is declared.

After this lesson, you will be able to:

- Accurately distinguish the four scopes: `compile`, `runtime`, `provided`, and `test`.
- Explain whether a dependency is present when **compiling main code**, **running the application**, or **compiling/running tests**.
- Choose the right scope in `pom.xml` for starters, JDBC drivers, container-provided libraries, and testing tools.
- Distinguish standard Maven scopes from packaging behavior for **standard JARs/WARs** and **Spring Boot executable JARs/WARs**.
- Understand how scopes combine when Maven resolves transitive dependencies and the role of `dependencyManagement`/BOMs.
- Use Maven Wrapper and `dependency:tree` to verify results instead of guessing from library names.

**Lesson scope:** dependencies declared by a **Maven project**, in the context of a Spring Boot application using `pom.xml`. Gradle has different configurations such as `implementation`, `runtimeOnly`, `compileOnly`, and `testImplementation`; they should not be equated one-to-one with Maven's four scopes.

## 2. What Is a Dependency Scope?

A Maven dependency typically has `groupId`, `artifactId`, `version` (sometimes managed by a BOM or parent POM), and an optional `scope`. For example, placed directly inside the `<dependencies>` element of `pom.xml`:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <scope>compile</scope>
</dependency>
~~~

The XML snippet above is a **POM fragment**, not a standalone runnable `pom.xml`. The version of `slf4j-api` must come from `dependencyManagement`/BOM or a separately declared `<version>` tag. In a Spring Boot project generated from Spring Initializr, many library versions are already managed by Spring Boot.

If **`<scope>` is omitted**, Maven defaults to **`compile`**:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
</dependency>
~~~

In this example, assuming no dependency management configuration overrides the scope, the classpath semantics are the same as `compile`. Scope is not simply "whether the library gets downloaded": Maven usually has to download artifacts before compiling/testing; **scope controls which artifacts participate in each classpath and how dependencies propagate**, not an on/off download switch.

### 2.1. Three Classpaths to Distinguish

1. **Compile classpath:** used to compile main application code in `src/main/java`.
2. **Runtime classpath:** used when running the application in a standard Maven runtime environment.
3. **Test classpath:** used to compile and run code in `src/test/java`; usually includes both main code dependencies and test-only dependencies.

A classpath can contain both direct and transitive dependencies after Maven resolves conflicts and scopes. A non-web project still has a runtime classpath; runtime is not synonymous with an HTTP server.

## 3. Overview Table of the Four Scopes

For a dependency **declared directly** in the project, the table below shows how Maven uses it across standard classpaths:

| Scope | Compile `src/main/java` | Run application | Compile/run tests | Practical meaning |
| --- | :---: | :---: | :---: | --- |
| **`compile`** | Yes | Yes | Yes | Main code needs the library to compile and uses it at runtime |
| **`runtime`** | No | Yes | Yes | Main code does not need the library's API to compile, but needs its implementation at runtime |
| **`provided`** | Yes | No | Yes | Compiles against the API, but expects the JDK/container or runtime environment to supply it |
| **`test`** | No | No | Yes | Serves only test code and test tooling |

**Two notes:**

- "No at runtime" in the table refers to **Maven's standard runtime classpath**, and does not determine whether the library appears in a **Spring Boot repackaged JAR/WAR**. Packaging plugins have their own rules—see section 8.
- "Yes on test classpath" does not guarantee tests will automatically pass: tests still need matching data, configuration, databases, JVM, and other dependencies.

You can remember this using three questions:

1. **Does main code import/directly use types from this library?** Usually needs `compile`; if supplied at runtime by a container, consider `provided`.
2. **Does main code only need an implementation at runtime (while the API is already in the JDK or another library)?** Consider `runtime`.
3. **Do only test code/testing tools need the library?** Use `test`.

Whenever unsure, inspect the code, classpath, and actual deployment target; never assign a scope based solely on the dependency's name.

## 4. `compile`: Dependencies Used by Main Code

`compile` is the **default** scope and is placed on all three classpaths. Examples: application code directly calls types in `slf4j-api`, or a Spring Boot starter declares dependencies so you can write controllers/services.

Example dependency snippet in `pom.xml` for a project using Spring Boot dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <!-- No scope specified: Maven uses compile -->
    </dependency>
</dependencies>
~~~

A standalone Java class in `src/main/java/com/example/scopes/CompileExample.java` illustrating main code importing and using the library's API:

~~~java
package com.example.scopes;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CompileExample {
    private static final Logger LOG =
            LoggerFactory.getLogger(CompileExample.class);

    private CompileExample() {}

    public static void main(String[] args) {
        LOG.info("Maven compile scope works");
    }
}
~~~

This class **has a complete `main` method** and compiles on Java 17+ if the project has a valid `slf4j-api` on the compile classpath. At runtime, a suitable SLF4J provider is needed to actually write logs as configured; log lines, format, and even whether logs appear depend on the provider/log level, so do not assume fixed stdout. In a Spring Boot application, a logging provider is normally supplied via the appropriate starter.

If you change the dependency containing `org.slf4j.Logger` from `compile` to `runtime` while main code still imports those types, compiling main code can fail with "package org.slf4j does not exist" or "cannot find symbol", **unless another dependency still brings that API onto the compile classpath**.

**Transitivity:** a library's `compile` dependencies usually propagate to downstream projects depending on that library, subject to Maven's scope matrix and conflict rules. For libraries whose public code exposes types from another dependency, declaring `compile` accurately is vital for consumers.

## 5. `runtime`: Needed When Running, Not to Compile Main Code

`runtime` is used for artifacts supplying an implementation that main code does not need to import at compile time. A clear example is a **JDBC driver**, where code uses the JDK or framework JDBC API while the driver is selected and loaded at runtime.

In a Spring Boot project using Boot dependency management and connecting to PostgreSQL, an illustrative declaration is:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Application Java code can use types from **`java.sql`**, which are built into the JDK:

~~~java
package com.example.scopes;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public final class JdbcExample {
    private JdbcExample() {}

    public static void main(String[] args) throws SQLException {
        try (Connection connection = DriverManager.getConnection(
                "jdbc:postgresql://localhost:5432/demo",
                "demo_user",
                "demo_password")) {
            System.out.println(connection.isValid(2));
        }
    }
}
~~~

This is a syntactically valid Java 17+ program, but running it successfully requires the PostgreSQL JDBC driver **on the runtime classpath**, a running PostgreSQL server at the example URL, an actual database and credentials, and network access. **There is no fixed stdout** in an environment without a configured database; when connection fails, `DriverManager.getConnection` throws `SQLException`. The example illustrates code compiling against `java.sql` without directly importing `org.postgresql.Driver`.

When using Spring Boot DataSource/JPA, runtime dependency selection also depends on how Spring Boot auto-configuration detects the driver, connection URL, connection pool dependencies, and `spring.datasource.*` properties.

**Not every JDBC driver only ever needs `runtime`:** if main code directly imports a driver-specific class (for example `org.postgresql.PGConnection`) to call vendor-specific APIs, it needs that API on the **compile classpath**, so `runtime` may not be appropriate.

A very common mistake is accidentally moving a runtime-required library to `test`: the test suite can pass while production fails to start due to a missing driver or provider.

## 6. `provided`: Compilable, but Supplied by the Environment

`provided` behaves like `compile` when **compiling main code** and **running tests**, but is **omitted from Maven's standard runtime classpath**. Design intent: the library/API will be supplied by the **JDK or target container/environment** at runtime.

Typical example: a WAR application deployed to an **external Servlet container**, where the container supplies servlet/runtime components under the deployment contract. Illustrative POM snippet:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
~~~

The `jakarta.servlet-api` version must match the servlet container platform and can be managed by a BOM/parent. The snippet above is **not an instruction to manually add the servlet API to every Spring Boot application**: with Spring Boot starters, the relevant APIs may already be managed/included appropriately.

**Example directly related to Spring Boot WAR:** if deploying to an external Tomcat, configure WAR packaging and mark the embedded Tomcat dependency as `provided` according to the deployment guide for your Spring Boot line:

~~~xml
<packaging>war</packaging>

<!-- Example inside <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

These are **POM fragments**, not a full project XML. Depending on your Spring Boot version and chosen starters, the artifact/container name depends on version and setup. The goal of `provided` here is to avoid conflicts between the embedded container and external container when deploying a WAR; check the documentation for your actual Boot version.

**Warning about packaging behavior:** Maven scope `provided` does not guarantee a dependency is excluded from **every** generated JAR/WAR file. **The Spring Boot Maven Plugin `repackage` goal can still include `provided` dependencies in the executable archive by default**. For executable WARs, `provided` libraries are placed in `WEB-INF/lib-provided` to support `java -jar` without colliding with external container libraries upon deployment. See section 8 and official documentation.

**Scope `provided` does not mean "unimportant library"**: if the actual runtime environment fails to supply the required implementation, the application can encounter `ClassNotFoundException`, `NoClassDefFoundError`, or bean/classloader initialization failures. Because this scope **remains on the test classpath**, passing tests on a developer machine does not prove the external runtime supplies the right library.

## 7. `test`: Dependencies Only for Testing

`test` appears on the classpath to **compile and run tests**, and is absent from standard main compile/runtime classpaths. Use it for JUnit, Mockito, AssertJ, and other test tools only needed in `src/test/java`.

In a Spring Boot project with a BOM/parent managing versions, for example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The file `src/test/java/com/example/scopes/ArithmeticTest.java` illustrates JUnit Jupiter:

~~~java
package com.example.scopes;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ArithmeticTest {

    @Test
    void twoPlusTwoEqualsFour() {
        assertEquals(4, 2 + 2);
    }
}
~~~

The test code is a valid Java class for Java 17+, using the JUnit Jupiter API supplied by starter/test dependencies. In a typical Spring Boot Maven project with tests configured, run:

~~~bash
./mvnw test
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

When the environment has downloaded dependencies and has a compatible test engine/compiler plugin, this test should pass; it prints no fixed stdout line, and Maven may display test counts or summaries differently across versions. If `@Test` or `Assertions` is not recognized inside `src/main/java`, that is **consistent with the `test` scope**: production code is not meant to depend on JUnit.

**Common trap:** tests have full runtime, compile, provided, and test dependencies, so tests can occasionally mask a production shortage. For example, main code calls an implementation placed only in `test`, while other test injection/configuration supplies the classpath; verify the runtime artifact and actual execution path.

## 8. How Scopes Affect JAR/WAR Packaging

You must distinguish three layers:

1. **Maven scope:** determines Maven classpaths and dependency propagation.
2. **Standard archive plugins:** determine which files are packed into a JAR/WAR per plugin rules.
3. **Spring Boot Maven Plugin `repackage`:** converts a JAR/WAR into an executable archive with its own dependency placement rules.

### 8.1. Standard Maven JAR

Under standard configuration, `maven-jar-plugin` primarily packages **the project's own classes/resources**, and **does not automatically embed all dependency JARs** inside the JAR. Thus, "scope `compile` means it will be inside every JAR file" is false. Running a standard JAR requires configuring the classpath or deploying dependencies alongside the JAR.

### 8.2. Traditional Maven WAR

When building a standard WAR for deployment to a servlet container, dependencies needed by the application at runtime (typically compile/runtime) are placed in `WEB-INF/lib` according to packaging configuration. `provided` dependencies are omitted from `WEB-INF/lib` because the container is expected to supply them; test dependencies do not belong in a production WAR.

### 8.3. Spring Boot Executable JAR/WAR

When the Spring Boot Maven Plugin runs **`repackage`**, the executable archive contains application classes, the Spring Boot loader, and the dependencies selected by the plugin for packaging. Per plugin documentation, **`provided` dependencies declared in the project are also included by default**, unless excluded or changed via configuration. Specifically:

| Archive | Typical Locations | Meaning |
| --- | --- | --- |
| Spring Boot executable JAR | `BOOT-INF/classes` and `BOOT-INF/lib` | Contains application classes and libraries for running via `java -jar` |
| Spring Boot executable WAR | `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` | Separates WAR runtime libraries from provided dependencies so it can deploy to an external container or run as an executable WAR |
| Traditional WAR (not repackaged) | `WEB-INF/classes` and `WEB-INF/lib` | Provided dependencies are not placed in `WEB-INF/lib` per standard WAR conventions |

**Key point:** `provided` is not equivalent to an instruction to "exclude from the Spring Boot executable artifact." If you want to exclude a dependency from Boot's executable JAR/WAR, look into **Spring Boot Maven Plugin exclusions** such as `<excludes>` or appropriate options, while ensuring runtime still has the needed classes. Inspect the final artifact rather than just reading `pom.xml`.

For example, in a project with `spring-boot-maven-plugin` configured and `repackage` bound via the Spring Boot parent or `<executions>`:

~~~bash
./mvnw clean package
~~~

When using the appropriate parent/generator, `package` creates an executable archive in `target/`. **Do not assume every Maven project automatically has the `repackage` goal**: without the Spring Boot plugin/binding, `package` follows standard Maven configuration only.

To inspect the contents of an already-packaged, real JAR (for example, an actual file named `scope-demo-0.0.1-SNAPSHOT.jar`):

~~~bash
jar tf target/scope-demo-0.0.1-SNAPSHOT.jar
~~~

`jar tf` lists entries; look for `BOOT-INF/lib`, driver names, API JARs, or `WEB-INF/lib-provided` if checking a WAR. If your artifact has another name, **use the exact filename in `target/`**; do not rely on assumptions about `version` or classifier. You can filter lines with `grep` on Linux/macOS or `Select-String` on PowerShell, though seeing a class in the archive does not by itself prove every runtime path will succeed.

Official sources: https://docs.spring.io/spring-boot/maven-plugin/packaging.html and https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html

## 9. Scopes and Transitive Dependencies

Maven reads the POMs of direct dependencies and deeper dependencies, then computes their effective scopes. For example:

~~~text
Application A
  └── Library B (compile)
        └── Library C (runtime)
~~~

For A, C usually ends up with effective scope **`runtime`**, not the default `compile`; A's main code does not automatically get C on its compile classpath merely because A depends on B.

Typical combination rules per Maven documentation:

| Direct Scope of B in A | Scope of C in B's POM | Effective Scope of C in A |
| --- | --- | --- |
| `compile` | `compile` | `compile` |
| `compile` | `runtime` | `runtime` |
| `compile` | `provided` or `test` | Omitted along that dependency path |
| `runtime` | `compile` | `runtime` |
| `runtime` | `runtime` | `runtime` |
| `provided` | `compile` | `provided` |
| `test` | `compile` | `test` |

This table describes a **single dependency path**, without factoring in other paths to the same artifact, explicit declarations, exclusions, optional flags, or dependency mediation. Maven uses a "nearest definition" rule for version selection in the dependency tree; effective scope and version are related but distinct issues.

### 9.1. Properly Understanding "Provided/Test Are Not Transitive"

Maven describes `provided` and `test` as scopes that **do not propagate to consumer projects as compile/runtime**: for instance, if library X declares a `test` dependency, project Y using X does not automatically inherit that test dependency for its production code. However, indirect dependencies behind **a direct `provided`/`test` dependency of the current project itself** can still enter that project's classpath according to the scope combination table. So do not interpret "non-transitive" as "Maven never reads any child dependencies."

### 9.2. Scope vs. `optional` and `exclusions`

- `scope` is the mechanism for placing dependencies on classpaths and determining how scope propagates across the graph.
- `<optional>true</optional>` on a library's dependency indicates that consumers of that library **do not automatically inherit the optional dependency along that transitive path**; consumers can declare it directly if needed.
- `<exclusions>` on a dependency path removes a transitive artifact along that path; another path can still bring the artifact into the graph.

Do not use `test` or `provided` as a "workaround" for version conflicts. Analyze the dependency tree and fix the root cause.

## 10. Scope vs. Version Management: `dependencyManagement` and BOM

This is a common point of confusion in Spring Boot: **BOMs and parent POMs primarily help select a compatible set of dependency versions**, whereas `<dependencies>` decides which dependencies the project actually uses. Scope can be managed in dependency management if declared there, yet having a BOM list an artifact **does not automatically make that artifact a project dependency**.

In Spring Boot, most starters/artifacts have their versions controlled by Spring Boot dependency management. For example, declaring the PostgreSQL driver as `runtime` without specifying a version when the BOM manages that artifact:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

If the project lacks dependency management for the PostgreSQL driver, you must provide a valid `<version>`. Maven does not infer versions from `groupId` and `artifactId` alone.

A BOM imported into `dependencyManagement` uses `<type>pom</type>` and **`<scope>import</scope>`**, concise example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**`4.0.0` here is only a syntax example, not a version recommendation.** Use the Spring Boot version chosen by your project or team. `import` is **not** one of the four classpath scopes in this lesson: it has a special meaning only for **dependencies of type `pom` inside `dependencyManagement`** to import managed dependency lists from a BOM. Never put `import` on a regular JAR dependency.

**If using `spring-boot-starter-parent`**, the parent already configures dependency/plugin management accordingly; do not mechanically add the BOM again. When using a different parent, you can import the Spring Boot BOM to get Boot's managed versions, though plugin management and other Boot parent settings are not automatically inherited identically.

## 11. Hands-On Verification of Scopes Using Maven Wrapper

This walkthrough is for **an existing Spring Boot Maven project from Spring Initializr** with `mvnw`/`mvnw.cmd`, `pom.xml`, and a compatible JDK. The XML snippets from earlier sections go directly inside `<dependencies>` of the existing POM; do not concatenate them into multiple duplicate `<dependencies>` root elements.

### Step 1 — Verify Maven Is Running

On Linux/macOS:

~~~bash
java -version
./mvnw --version
~~~

On Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd --version
~~~

Maven Wrapper pins the Maven version per project configuration, but does not automatically guarantee the right JDK version. Verify the JDK used to compile and the Java version supported by Spring Boot.

### Step 2 — Inspect the Dependency Tree and Scopes

Linux/macOS:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree
.\mvnw.cmd dependency:tree "-Dincludes=org.postgresql:postgresql"
~~~

The second command filters dependencies by `groupId:artifactId` if present in the tree. The `maven-dependency-plugin` may be resolved/downloaded automatically on first run; network and repository access are required if not cached.

Example **simulated line format** (this is not guaranteed output for every project/version):

~~~text
[INFO] +- org.slf4j:slf4j-api:jar:2.x.y:compile
[INFO] +- org.postgresql:postgresql:jar:42.x.y:runtime
[INFO] \- org.junit.jupiter:junit-jupiter:jar:5.x.y:test
~~~

In real output, versions and dependency tree contents depend on `pom.xml`/BOM. Look at the **scope at the end** of each line to see Maven's resolved effective scope. If there are multiple dependency paths or conflicting versions, do not draw conclusions from a single isolated declaration.

### Step 3 — Build and Run Tests

Linux/macOS:

~~~bash
./mvnw clean test
./mvnw package
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd package
~~~

`test` compiles and runs tests per lifecycle/configuration. `package` executes earlier lifecycle phases (usually including tests), then builds the artifact. Command success does not prove an external container, database, or production server provides all `provided` dependencies at the right versions.

### Step 4 — Inspect Dependencies Managed by Parent/BOM

When you need to determine the **effective version/scope** after inheritance and dependency management:

~~~bash
./mvnw help:effective-pom
~~~

The output can be very long; search for the relevant artifact coordinates in the effective POM and cross-check with `dependency:tree`. `dependencyManagement` explains the source of managed versions/defaults; `dependency:tree` shows the dependencies actually resolved in the graph. Never treat either one as a complete substitute for the other.

### Step 5 — Inspect What Gets Shipped

With the Spring Boot Maven Plugin, verify `repackage` ran, then use `jar tf` to inspect the actual executable JAR/WAR. For services deploying a WAR to external Tomcat, check **both WAR deployment behavior** and the **contents of `WEB-INF/lib` and `WEB-INF/lib-provided`** if the archive is Boot-repackaged. That is the test tied to the real deployment environment.

## 12. Rules for Choosing Scopes by Scenario

| Scenario | Usually Appropriate Scope | Why |
| --- | --- | --- |
| Application code imports types from the library (e.g., SLF4J API) | `compile` | Compiler needs the API, and runtime usually needs the library too |
| PostgreSQL driver loaded by framework/JDBC at runtime; main code does not import the driver | `runtime` | Implementation needed when running, not when compiling main code |
| Servlet API/container genuinely supplied by an external Servlet container | `provided` | Compile against the API; container is responsible at runtime |
| Embedded Tomcat when packaging a traditional WAR to deploy on external Tomcat | `provided` (per Boot/WAR guide) | Avoid bundling the embedded container into external deployment's `WEB-INF/lib` |
| JUnit Jupiter, Mockito, AssertJ used only in tests | `test` | Keep test APIs off the main code classpath |
| Library both imported by main code and required when running standalone | Usually `compile` | `runtime` will be missing from main compile classpath; `provided` is valid only if the environment supplies it |
| Library present only in Docker/test profile, while production runtime uses a different setup | Must evaluate against actual runtime | Scope does not replace profile configuration and deployment processes |

There is no "best scope for every project." An artifact might be declared `compile` in one application and `test` in another, because **usage** dictates the required classpaths.

## 13. Common Mistakes and How to Fix Them

### Mistake 1 — Making Every Dependency `compile`

Consequence: unnecessary dependencies can appear on multiple classpaths and propagate to consumers, increasing complexity and sometimes attack surface or packaging overhead. **Fix:** evaluate which dependencies are only for testing, runtime, or provided by containers; assign scopes according to the actual contract.

### Mistake 2 — Using `runtime` for a Library Imported by Main Code

Symptom: Maven cannot find the package/class during the compile phase. **Fix:** when `src/main/java` directly needs types from an artifact, use `compile` (or `provided` when supplied at runtime); verify you declared the exact artifact providing those types.

### Mistake 3 — Using `provided` to "Shrink a Spring Boot Executable JAR"

Symptom: the dependency still appears in the executable JAR/WAR or runtime behaves unexpectedly. **Fix:** review `spring-boot-maven-plugin` configuration, `repackage` rules, and exclusion options. In Spring Boot, `provided` dependencies are often still packaged per executable archive rules; do not rely on Maven scope alone.

### Mistake 4 — Using `test` for a Production Implementation

Symptom: tests pass, yet `java -jar` fails with a missing driver/class/provider when run for real. **Fix:** check the dependency's role; if the production app needs it at runtime, use `runtime` or `compile` as appropriate, then inspect the packaged artifact.

### Mistake 5 — Using `provided` Without a Container Actually Supplying the Library

Symptom: local tests via Maven pass, but deploying to a server fails with `NoClassDefFoundError`, `ClassNotFoundException`, or classloading conflicts. **Fix:** verify the container, API version, deployment contract, and classpath; avoid assuming the JDK contains libraries formerly in Java EE/Jakarta EE.

### Mistake 6 — Confusing `dependencyManagement` with `dependencies`

Symptom: the POM imported a BOM, yet `dependency:tree` does not show the desired artifact. **Fix:** if you actually need the artifact, declare the dependency under `<dependencies>`. A BOM mainly supplies version management and declared defaults; by itself it does not add all artifacts to the classpath.

### Mistake 7 — Guessing the Scope of Transitive Dependencies

Symptom: dependency C shows up as `runtime` even though direct library B is `compile`. **Fix:** trace A -> B -> C in `dependency:tree`, check the scope combination matrix, other paths to C, dependency mediation/management, exclusions, and optional flags.

## 14. Practice Exercises

**Exercise 1.** Main code uses `java.sql.Connection` and `DriverManager`, while the PostgreSQL driver is only loaded via the JDBC URL at runtime. Which scope should you choose for the driver?  
**Answer:** usually `runtime`, because main code compiles against the `java.sql` API built into the JDK, while runtime needs the driver. If code directly imports PostgreSQL driver-specific APIs, reconsider `compile`.

**Exercise 2.** A project uses Mockito only in `src/test/java`. Which scope?  
**Answer:** `test`, because production code does not need Mockito APIs.

**Exercise 3.** A library has `provided` scope. Do passing tests prove the production runtime will have it?  
**Answer:** **No**. The test classpath includes `provided` dependencies, whereas Maven's standard runtime classpath does not. You must verify what the container/runtime supplies and inspect the specific packaged artifact.

**Exercise 4.** For a Spring Boot executable WAR after `repackage` has run, where can a `provided` embedded Tomcat dependency reside?  
**Answer:** `WEB-INF/lib-provided` per the Spring Boot Maven Plugin WAR layout rules; this allows the WAR to still run via `java -jar` when needed while avoiding conflicts with an external container.

**Exercise 5.** A `compile` dependency pulls in a `runtime` child dependency. What effective scope does the child dependency get along that path?  
**Answer:** `runtime`; it does not automatically become `compile` just because the parent is `compile`.

**Exercise 6.** A POM imports the Spring Boot BOM but does not declare a specific driver in `<dependencies>`. Will the driver automatically be on the classpath?  
**Answer:** **Not just from importing the BOM**; the dependency must be declared directly or pulled in via a valid transitive path.

## 15. Checklist Before Finalizing `pom.xml`

- [ ] For each dependency, identify **which source set uses it**: `src/main` or `src/test`.
- [ ] Determine whether the dependency's types are needed to compile main code or only its implementation is needed at runtime.
- [ ] If using `provided`, know **what supplies it at runtime**, at the exact version and environment.
- [ ] For Spring Boot executable artifacts, verify `repackage` rules before concluding which dependencies will be packaged.
- [ ] For WARs deployed to external containers, verify the servlet API and embedded container do not conflict.
- [ ] Distinguish actually declared dependencies from dependencies that only appear in a BOM/`dependencyManagement`.
- [ ] Check `dependency:tree` to verify effective scopes and transitive dependency paths when in doubt.
- [ ] Run tests, build, and a production-like execution path to catch missing runtime dependencies.

## Official Documentation

- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven — POM Reference (`dependencies` and `dependencyManagement`): https://maven.apache.org/pom.html
- Maven — Maven Dependencies and Scope: https://maven.apache.org/repositories/dependencies.html
- Apache Maven Dependency Plugin — dependency tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Traditional Deployment: https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html

**Key takeaway:** `compile` is for main code and runtime, `runtime` is for implementations needed only at runtime, `provided` is for APIs supplied by the target environment, and `test` is for testing. Always cross-check **Maven's resolved classpaths** against **the artifact contents packaged by the Spring Boot plugin** before concluding a library will be present or absent at deployment.