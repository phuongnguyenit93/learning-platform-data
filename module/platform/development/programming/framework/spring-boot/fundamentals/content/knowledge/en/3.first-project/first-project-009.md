# Distinguishing Compile Errors, Dependency Errors, and Startup Errors

When working on your **first Spring Boot project**, the three complaints “the project won't build,” “a library is missing,” and “the application won't run” often get lumped together as *Spring Boot errors*. In reality, they can occur in different phases, stem from different components, and require different fixes.

This lesson helps you look at the **command being run**, the **failing stage**, and the **first meaningful error line** so you can distinguish:

1. **Compile errors**: source code cannot be translated into valid bytecode.
2. **Dependency errors**: required libraries cannot be found, downloaded, selected at compatible versions, or placed on the appropriate classpath.
3. **Startup errors**: code compiled well enough to launch, yet the JVM or Spring Boot cannot complete application initialization.

The three groups are interconnected. A missing dependency can surface as a compile error; a mismatched dependency version might only fail at startup. Therefore, beyond the *stage*, you also need to identify the *root cause*.

## 1. What stages does a Spring Boot application pass through?

Consider a Gradle project with the Spring Boot plugin, Java, and Spring Boot libraries. Execution can be pictured as:

```text
Java source + build.gradle / pom.xml
                  │
                  ▼
       Read build configuration
                  │
                  ▼
       Resolve dependencies
      (select, download, check JARs)
                  │
                  ▼
            Compile Java
          (.java → .class)
                  │
                  ▼
         Package / launch JVM
                  │
                  ▼
       Load classes and start
        SpringApplication.run()
                  │
                  ▼
      Create ApplicationContext
      Beans, config, wiring
                  │
                  ▼
     Web server listens on port
        APPLICATION READY
```

The diagram represents the primary flow, not every task in every project. For example, Gradle's `bootRun` task triggers compilation before launching the JVM; a packaging task may also process resources and dependencies. A failure on `bootRun` alone is not enough to call it a startup error: the application may not have reached runtime yet.

| Error Group | Where Does It Fail? | Common Signals | Where to Start Investigating |
|---|---|---|---|
| **Compile** | Java compiler checks syntax, names, and data types | `error: ';' expected`, `cannot find symbol`, `incompatible types`; Gradle may report `:compileJava FAILED` | `.java` file, reported line number, and method/type signatures |
| **Dependency** | Resolving, downloading, or selecting libraries; sometimes surfaces when linking/loading classes at runtime | `Could not resolve`, `Could not find`, `Could not GET`, `NoClassDefFoundError`, `NoSuchMethodError` | `build.gradle`/`pom.xml`, repositories, versions, compile/runtime classpath |
| **Startup** | JVM has started running, yet Spring cannot finish initialization | `APPLICATION FAILED TO START`, `BeanCreationException`, `Port ... was already in use` | Stack trace, `Caused by`, bean configuration, ports, environment |

**Rule of thumb:** *Compile* answers “Can Java understand and produce runnable code?”; *dependency* answers “Are the required classes/libraries available and compatible?”; *startup* answers “Can the application set up its actual runtime environment?”.

## 2. Compile errors: Java could not generate bytecode

Compile errors appear when `javac` (directly or via Maven/Gradle) cannot turn Java code into valid `.class` files. The compiler checks syntax, class/method/variable resolution, type compatibility, and many Java language rules.

### 2.1. Syntax error example

A simple controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot"
    }
}
```

The error is the missing `;` after the `return` statement. During compilation, the message may look like:

```text
HelloController.java:11: error: ';' expected
        return "Hello Spring Boot"
                                  ^
```

Fix:

```java
return "Hello Spring Boot";
```

At this stage Spring Boot has not needed to instantiate any controller, open any port, or start a web server. Changing `server.port` or adding database configuration will not fix a missing semicolon.

### 2.2. Cannot-find-symbol example

```java
public String hello() {
    return greetingService.message();
}
```

If `greetingService` has not been declared, the compiler may report:

```text
error: cannot find symbol
    return greetingService.message();
           ^
  symbol:   variable greetingService
```

This is a compile error about a **variable name in source code**. By contrast, if you declared a field of type `GreetingService` and compiled successfully, yet Spring cannot find a bean of that type, the error happens during **`ApplicationContext` startup**. They are two different problems even though both mention the service name.

Other common compile failures:

- Unmatched brackets, semicolons, or quotes.
- Type mismatch, such as returning `String` when a method declares `int`.
- Calling a nonexistent method or passing wrong argument types.
- Duplicate class names or invalid duplicate method signatures.
- Wrong package/import name, or the compiler cannot see a required class.
- Incompatible Java version configuration, such as a compiler too old for the language features used.

### 2.3. Commands to observe compile errors

With Gradle Wrapper:

```bash
# Linux / macOS
./gradlew compileJava
```

```powershell
# Windows PowerShell
.\gradlew.bat compileJava
```

With Maven Wrapper:

```bash
# Linux / macOS
./mvnw compile
```

```powershell
# Windows PowerShell
.\mvnw.cmd compile
```

Wrappers only exist if the project includes those files. If there is no wrapper, run an installed `gradle` or `mvn` command. In a multi-module project, you may need to specify a particular task/module.

Focus first on compiler messages shaped like `<FileName>.java:<line>: error: ...`; the `BUILD FAILED` line is only the final summary. Do not guess fixes based solely on that summary line.

## 3. Dependency errors: missing, undownloadable, or incompatible libraries

A **dependency** is a library or module that an application needs to compile or run. In Spring Boot, you declare dependencies in `build.gradle` / `build.gradle.kts` or `pom.xml`. Gradle/Maven resolves those artifacts along with *transitive dependencies*.

Gradle Groovy DSL example, assuming the project already configured the Spring Boot plugin and repositories:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This snippet mainly illustrates dependencies, not a full build file. In a Spring Boot project with proper dependency management, starter versions are managed centrally. Avoid pinning scattered individual versions when the project already uses consistent version management.

### 3.1. Artifact not found or failed to download

Illustrative Gradle log:

```text
Execution failed for task ':compileJava'.
> Could not resolve all files for configuration ':compileClasspath'.
   > Could not find com.example:missing-library:1.0.0.
     Searched in the following locations: ...
```

This is a dependency-resolution failure, even though the failing task reported is `compileJava`. The Java compiler simply did not receive all required libraries to do its job.

Common causes:

| Log Signal | Possible Cause | What to Check |
|---|---|---|
| `Could not find group:artifact:version` | Misspelled coordinates or version not published in declared repositories | `group/artifact/version` spelling and repository list |
| `Could not resolve ...` | Gradle/Maven could not resolve a dependency or hit a conflict/policy rule | Accompanying detail error and dependency tree |
| `Could not GET ...`, `Read timed out` | Cannot reach artifact download source | Network, proxy, DNS, repository URL |
| `401 Unauthorized`, `403 Forbidden` | Private repository requires credentials or account lacks permissions | Environment authentication configuration |
| `PKIX path building failed` | HTTPS connection failed certificate chain validation | Certificate chain, corporate proxy, truststore |
| `No cached version ... available for offline mode` | Offline mode active, yet artifact is not in local cache | Disable offline mode or populate cache |

Do not assume every `Could not resolve` error is a network glitch. If a version was mistyped or a repository does not host that artifact, retrying downloads repeatedly will not fix the cause.

### 3.2. Library is declared, yet compilation still reports missing package

Suppose a Java file has:

```java
import org.springframework.web.bind.annotation.RestController;
```

And the compiler reports:

```text
error: package org.springframework.web.bind.annotation does not exist
```

The **symptom** is a compile error, yet the **root cause may be a dependency**: the project has not declared the starter or library containing that annotation on the compile classpath. The package name could also be misspelled.

Right diagnostic steps:

1. Check whether the import name is spelled correctly.
2. Check whether the dependency is declared in the right module.
3. Check whether the library is present on `compileClasspath`.
4. Once the classpath is right, recompile to confirm the symptom disappears.

Do not work around this by manually copying `.class` files into the source tree.

### 3.3. Compilation succeeds, yet runtime is missing a class

Some dependencies are compile-only and omitted from runtime, or a transitive dependency was improperly excluded. When execution reaches a class that needs it, the JVM may report:

```text
java.lang.NoClassDefFoundError: com/example/library/Parser
Caused by: java.lang.ClassNotFoundException:
    com.example.library.Parser
```

This is a **runtime** error whose root cause lies in **dependencies/classpath**. It can happen during Spring Boot startup or only when handling the first request.

With the Gradle Java plugin, common configurations include:

| Configuration | Common Meaning |
|---|---|
| `implementation` | Libraries for application code, typically present on both compile and runtime classpaths of the module |
| `compileOnly` | Needed at compile time, usually not included as a runtime dependency |
| `runtimeOnly` | Needed at runtime; main code does not compile directly against types in this library |
| `testImplementation` | Libraries for compiling/running tests; does not become a main runtime dependency |

Common example: a JDBC driver can be declared as `runtimeOnly` if application code does not directly reference driver classes at compile time; annotations like `@RestController` must be visible at compile time.

Maven uses its own scope names and semantics (`compile`, `runtime`, `provided`, `test`). Do not copy Gradle configuration names mechanically into Maven.

### 3.4. Wrong library version or conflict

An application may download dependencies and compile cleanly, yet throw at runtime:

```text
java.lang.NoSuchMethodError: '...'
```

This usually indicates bytecode is calling a method that the actually loaded version of the class **does not have**. A classic cause is the compiler seeing one version of a library while runtime loads a different version.

A related error is `UnsupportedClassVersionError`: a class file was compiled for a newer Java version than the current JVM supports. This is a bytecode/runtime compatibility issue; it can originate in your own code or inside a library.

How to handle:

- Inspect the dependency tree instead of guessing which version is active.
- Read the full class and method name in the stack trace.
- Check JDK versions used at build time and runtime.
- Prefer Spring Boot's version management and an appropriate BOM.
- Avoid forcing versions or excluding transitive dependencies without understanding the consequences.

### 3.5. Tools to inspect the dependency graph

With Gradle:

```bash
# Linux / macOS
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

```powershell
# Windows PowerShell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

With Maven:

```bash
./mvnw dependency:tree
```

```powershell
.\mvnw.cmd dependency:tree
```

Run commands for the active project/module. In multi-module Gradle builds, target the appropriate project path; in multi-module Maven builds, select a module with `-pl`. When debugging dependency-related compile errors, inspect `compileClasspath` instead of or alongside `runtimeClasspath`.

Depending on the situation, Gradle's `--refresh-dependencies` can force re-checking metadata/cache, though it will not fix wrong artifact coordinates or missing repository config. Do not treat wiping the entire cache as your first troubleshooting step.

## 4. Startup errors: application launches, yet Spring Boot is not ready

Once code compiles, the JVM can execute `main`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`SpringApplication.run(...)` sets up the application: reads configuration, creates `ApplicationContext`, registers and initializes beans, applies auto-configuration, and initializes connections or a web server depending on dependencies and configuration.

When a required step fails, startup halts and returns a non-zero exit code, even though `.class` files were built successfully.

### 4.1. Spring Boot reports an error, so read the specific cause

Illustrative log:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Web server failed to start. Port 8080 was already in use.

Action:

Identify and stop the process that's listening on port 8080
or configure this application to listen on another port.
```

This is a startup error due to an **occupied port**, not a missing `;` and not automatically a missing dependency. One way to run on a different port is setting:

```yaml
# src/main/resources/application.yml
server:
  port: 8081
```

Or passing an argument when running the artifact:

```bash
java -jar build/libs/demo.jar --server.port=8081
```

`demo.jar` above is illustrative: replace it with your actual JAR name. If you change the port, test URLs must use the new port too.

### 4.2. Failed to create a bean

Consider:

```java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet() {
        return service.greet();
    }
}
```

If `GreetingService` is a validly declared interface with no registered implementing bean, the code **compiles fine**. When Spring attempts to construct `GreetingController`, startup fails with a message similar to:

```text
Parameter 0 of constructor in com.example.demo.web.GreetingController
required a bean of type 'com.example.demo.service.GreetingService'
that could not be found.
```

One fix is registering a matching implementation:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet() {
        return "Hello!";
    }
}
```

At the same time, ensure the class falls within component scan scope or is registered via proper configuration. `@SpringBootApplication` normally scans its own package and subpackages. Adding `@Service` only resolves a missing-bean issue when the class is scanned and has no other configuration problems.

**Important distinction:**

- `cannot find symbol: GreetingService` at compile time: the compiler does not recognize the type.
- `required a bean of type GreetingService that could not be found` at startup: the JVM knows the type, yet Spring has no matching bean to inject.

### 4.3. Configuration and environment errors

Several familiar cases in a first project:

| Situation | Log Clue | Cause Group |
|---|---|---|
| Web port already used by a process | `Port 8080 was already in use` | Environment resource |
| Missing required bean | `No qualifying bean`, `UnsatisfiedDependencyException` | Spring context, component scan, conditional configuration |
| Bean initialization failed | `BeanCreationException`; check `Caused by` next | Bean, bean dependencies, or initialization code |
| Cannot connect to database | `Connection refused`, `Access denied`, timeout; possibly with DataSource/JPA errors | Database configuration or service |
| Missing required property | `Could not resolve placeholder` | Missing environment variable, property, or profile |
| Configuration value cannot convert to Java type | `BindException` or `ConversionFailedException` | Wrong value or configuration type |
| Profile configuration confusion | `No active profile set` is normal informational output, **not an error by itself** | Investigate only if accompanied by a related failure |

For instance, if you activate the `dev` profile without supplying an environment variable needed by datasource configuration, startup can fail even though compilation and dependency resolution succeeded. Check which `application.yml` is loaded, which profile is active, and where configuration values come from.

### 4.4. Web server up vs. request succeeding

When logs show something like:

```text
Started DemoApplication in ... seconds
```

the application has normally completed startup. Calling `GET /hello` and getting `404 Not Found` is usually a URL mapping or routing issue. Receiving `500 Internal Server Error` due to an exception inside a controller is a **request-handling error**, even if the stack trace mentions Spring classes.

Separating phases keeps you from debugging startup bean wiring when you mistyped a URL, or debugging routes when the web server never opened a port.

## 5. The same launch command can fail in three different phases

Suppose you run:

```bash
./gradlew bootRun
```

or on Windows:

```powershell
.\gradlew.bat bootRun
```

The command name is `bootRun`, yet Gradle usually resolves dependencies and compiles source before actually launching Spring Boot. Thus, all three examples below can make this command fail:

**Case A — Source syntax error**

```text
> Task :compileJava FAILED
DemoApplication.java:...: error: ';' expected
```

Direct cause: source code. Action: fix the reported Java line and recompile.

**Case B — Failed to download a library**

```text
> Could not resolve all files for configuration ':compileClasspath'
> Could not find org.example:sample-library:9.9.9
```

Direct cause: dependency resolution failed. Action: check artifact declaration, repositories, and connectivity. Do not hunt for missing braces in a controller when the compiler has not even received its dependencies.

**Case C — Application launched, yet Spring startup failed**

```text
APPLICATION FAILED TO START
...
Port 8080 was already in use.
```

Direct cause: startup environment. Action: free the occupied port or change the port setting.

A summary line like `Execution failed for task ':bootRun'` or `BUILD FAILED` does not distinguish the three cases. The evidence lives in the logs **above** and the specific cause chain.

## 6. Reading logs to find the root error

When running Spring Boot for the first time, the terminal may print many INFO, WARN, and ERROR lines. Not every WARN line is a fatal problem. Start from the failure point and trace the cause.

### 6.1. Stack trace reading example

Abbreviated illustrative log:

```text
org.springframework.beans.factory.BeanCreationException:
  Error creating bean with name 'dataSource'
Caused by: org.springframework.jdbc.CannotGetJdbcConnectionException:
  Failed to obtain JDBC Connection
Caused by: java.sql.SQLException:
  Access denied for user 'demo_user'
```

Read top to bottom:

- Spring could not create the `dataSource` bean.
- The intermediate cause was failing to obtain a JDBC connection.
- The concrete cause here is that database credentials were rejected.

If you only glance at `BeanCreationException` and slap `@Component` onto an existing class, you are editing the wrong place. Inspect credentials, host/database, and permissions matching the actual message. In real work environments, avoid pasting passwords, tokens, or connection strings containing secrets into public places.

### 6.2. Helpful search landmarks in the terminal

| String to Look For | How to Read It |
|---|---|
| `.java:...: error:` | Specific compiler error tied to a source location |
| `> Task :compileJava FAILED` | Gradle compile task failed; read further for cause, as it may stem from dependencies |
| `Could not resolve`, `Could not find` | Inspect accompanying dependency/repository details |
| `Caused by:` | Follow the cause chain; the deepest causes usually hold the most specific details |
| `APPLICATION FAILED TO START` | Spring Boot failure analysis output for startup failures |
| `Description:` and `Action:` | Guidance printed by certain Spring Boot failure analyzers |
| `Started ... in ... seconds` | Sign that startup finished; later failures likely belong to requests/runtime |

Not every error has `APPLICATION FAILED TO START`. For example, the JVM failing to locate the main class halts before Spring runs, or a class-loading error may occur right when invoking `main`.

### 6.3. Gathering more details when needed

Gradle:

```bash
./gradlew bootRun --stacktrace
./gradlew bootRun --info
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --stacktrace
.\gradlew.bat bootRun --info
```

Maven:

```bash
./mvnw spring-boot:run -e
```

`--stacktrace` and `-e` give extra details on build-tool failures. If the problem happens inside the application, inspect **Spring Boot logs** and the application's `Caused by` chain as well.

When you want to understand Spring Boot's auto-configuration decisions, you can run with Spring Boot's `--debug` flag, for example:

```bash
java -jar build/libs/demo.jar --debug
```

This flag prints a very long auto-configuration condition evaluation report; it is mainly useful when suspecting auto-configuration or conditional bean issues. Do not turn on every debug flag and then read only the last line.

## 7. Step-by-step troubleshooting workflow

You can follow this workflow whenever your “first project won't run.”

### Step 1 — Record the failing action

Which command did you run: `compileJava`, `test`, `bootJar`, `bootRun`, `java -jar`, or an HTTP request? Different commands trigger different stages.

Alongside the command, note the change you just made: editing Java code, adding a starter, changing Java version, updating application properties, or starting a database.

### Step 2 — Find the earliest meaningful failure point

Read specific lines *before* `BUILD FAILED` or `Application run failed`. Ask:

- Is there a compiler message with a `.java` file and line number?
- Is there a repository or dependency resolution error?
- Did the JVM invoke `main` and did Spring begin building the `ApplicationContext`?
- Did the web server report started, or did the failure happen later when calling an endpoint?

### Step 3 — Classify both symptom and cause

Common symptom-cause pairs:

| Symptom | Stage Observed | Root Cause to Consider |
|---|---|---|
| `';' expected` | Compile | Java syntax |
| `package ... does not exist` | Compile | Wrong import **or** missing compile dependency |
| `Could not find ...:...:...` | Dependency resolution | Artifact/repository/version |
| `NoClassDefFoundError` | Runtime class loading | Missing class, wrong runtime classpath, or class linkage/init error |
| `NoSuchMethodError` | Runtime | Binary version incompatibility |
| `required a bean ... could not be found` | Spring startup | Bean not registered, not scanned, or condition unmet |
| `Port ... was already in use` | Web server startup | Another process holds the port |
| HTTP `404` or `500` after successful startup | Request handling | Route mapping or business/runtime processing error |

The second row illustrates why you should not hard-classify errors by a few keywords alone. `package ... does not exist` is emitted by the compiler, yet the fix may live in the build file.

### Step 4 — Make the smallest change addressing the right cause

If the compiler points to a missing semicolon, fix the source code. If an artifact does not exist, fix dependency coordinates/repositories. If the server port is occupied, identify the process or pick another port. If a bean is missing, inspect wiring and component scanning.

Do not change the JDK, all libraries, database settings, and source code at the same time to “see if it works.” Changing too many variables at once destroys evidence of the root cause.

### Step 5 — Re-run the right stage

- Fixed syntax/types: run `compileJava` or `mvn compile`.
- Fixed dependencies: re-run the failing task; inspect compile/runtime classpaths accordingly.
- Fixed startup: re-run `bootRun` or `java -jar` and watch startup logs.
- Once the app has started: send a request to the target endpoint to verify behavior.

The criterion for considering a bug fixed is that **the previously failing step now succeeds**. In projects with tests, test execution can be a separate subsequent stage that fails for test reasons; do not lump test failures into compile/startup failures.

## 8. Practice: three intentional errors in your first Spring Boot project

Use a working Spring Boot project with `@SpringBootApplication` and `spring-boot-starter-web`. Keep a clean revertible state before experimenting. Make only one change per experiment, inspect the logs, revert/fix it, and then move to the next.

### Experiment 1 — Introduce a compile error

Create a controller with a statement missing `;`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/demo")
    public String demo() {
        return "demo"
    }
}
```

Run:

```bash
./gradlew compileJava
```

Expect a compiler message on the `return` line. Fix it to `return "demo";` and recompile. What you just observed is an error occurring before the JVM ever runs the application.

### Experiment 2 — Introduce a dependency resolution error

In a Gradle Groovy DSL project declaring `repositories { mavenCentral() }`, temporarily add a fake dependency in the `dependencies` block:

```groovy
implementation 'com.example.nonexistent:training-artifact:9999.0'
```

Run:

```bash
./gradlew compileJava
```

Because this dependency does not exist in configured repositories or cache, Gradle reports it cannot resolve the artifact. No Java line needs fixing here. After reading the error, **remove the fake dependency line** and re-run.

This exercise uses intentionally nonexistent coordinates; exact error phrasing depends on repository setup and Gradle version.

### Experiment 3 — Introduce a port startup error

Start one successfully built web application on the default port, then try starting a second instance using the same port. When both attempt to bind the same address/port, the second instance cannot open its listener and Spring Boot reports that the port is already in use.

You can try setting a different port via command-line argument for the second instance:

```bash
./gradlew bootRun --args='--server.port=8081'
```

The syntax above applies to Gradle `bootRun` supporting `--args`. For an executable JAR, you can run `java -jar <jar-path> --server.port=8081`. If another process already uses port 8081, choose an available port.

In this experiment, the compiler and dependencies remain completely valid. The failure is a web server runtime condition.

### Log analysis drill

Identify the *stage* and *likely cause* of each message before looking at the right columns:

| Short Log | Stage | Likely Cause |
|---|---|---|
| `error: incompatible types: String cannot be converted to int` | Compile | Type mismatch in Java code |
| `Could not GET 'https://.../artifact.pom'` | Dependency resolution | Repository access failed; check accompanying HTTP/TLS/network details |
| `NoClassDefFoundError: org/example/LibraryClass` when calling `java -jar` | Runtime | Missing class or unable to load/link a dependent class |
| `UnsatisfiedDependencyException` while refreshing `ApplicationContext` | Spring startup | An unsatisfied bean dependency; inspect `Caused by` entries |
| `Started DemoApplication...` then `GET /missing` returns `404` | Request | App is running; URL has no matching route |

## 9. Common misconceptions

**“The `bootRun` command failed, so it must be a Spring startup error.”** Not necessarily. `bootRun` can stop during dependency resolution or Java compilation. Read the failing task and cause in the logs.

**“Seeing `ClassNotFoundException` means add `@Component`.”** `@Component` only registers a bean once the class can already be loaded and scanned. It does not add a missing JAR to the classpath.

**“A successful build guarantees startup will succeed.”** Building checks certain source, dependency, and packaging conditions. It does not guarantee a database is ready, ports are free, environment config is valid, or beans instantiate under every profile.

**“The first ERROR line or last WARN line is always the root cause.”** One failure can emit a cascade of messages. Inspect context, the `Caused by` chain, and failure analysis. Ordinary WARN lines do not necessarily fail the app.

**“Upgrading one library to its newest version fixes every error.”** A newer release may be incompatible with Spring Boot or other parts of the app. Inspect the dependency tree and choose a consistent set of versions.

**“The application returned 404, meaning it failed to start.”** False when the web server is already up. A 404 can simply come from sending a request to an undefined path.

## 10. Diagnostic mindset to carry into upcoming Spring Boot lessons

Whenever you hit an error, describe the incident in one accurate sentence:

- “`javac` failed to compile `HelloController.java` because of a missing `;`.”
- “Gradle could not resolve `group:artifact:version` from the configured repositories.”
- “The JVM could not load a library class when running the artifact.”
- “Spring could not create `GreetingController` because no matching `GreetingService` bean existed.”
- “Spring created the web application, yet could not open the port because it was already in use.”
- “The application started, yet `/hello` returned 404 because the endpoint was not mapped as expected.”

Those sentences pinpoint **which component failed**, **when it failed**, and **what evidence to check**. That is the foundation for moving into Dependency Injection, auto-configuration, profiles, databases, and HTTP handling in Spring Boot without confusing source, library, and runtime environment errors.
