# Runtime Binding: How a Facade Connects to a Logging Backend in Java

## 1. What Is Runtime Binding?

In Java's logging architecture, a **facade** provides a common API for applications to emit log events, while a **backend** handles filtering, formatting, and writing those events to the console, a file, or a collection system. **Runtime binding** is the step at runtime when the facade connects to the backend implementation available in the execution environment.

For example, an application calls only the SLF4J API:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

void createOrder(String orderId) {
    LOG.info("event=order.created orderId={}", orderId);
}
```

This is an **illustrative snippet in the `OrderService` class**, not a standalone program. The exact same code can log using Logback or Log4j 2 if the runtime has the compatible provider and corresponding backend configuration. Business code does not need to switch from `LOG.info` to a backend-specific API.

Mental model:

```text
Java source code
    |
    |  import org.slf4j.Logger; LoggerFactory.getLogger(...)
    v
SLF4J API (compile time)
    |
    |  finds binding/provider in runtime classpath
    v
One connected backend (runtime)
    |
    +-- Logback   -> ConsoleAppender / RollingFileAppender / ...
    +-- Log4j 2   -> Appender / Layout / ...
    +-- JUL       -> java.util.logging Handler / Formatter / ...
    +-- Simple    -> simple output
    +-- NOP       -> intentionally discards logs
```

The backend options in the diagram **are mutually exclusive alternatives**, not a list of JARs to install simultaneously. Best practice is for the **running application** to choose one provider/backend, while shared libraries depend only on the facade/API.

### When Is This Knowledge Useful?

- Running an application where logs disappear even though the code calls `logger.info()`.
- A build uses Logback, but upon deployment you see SimpleLogger formatting.
- The console reports `multiple bindings`, `multiple providers`, or `No SLF4J providers were found`.
- One module uses SLF4J while another framework logs to JUL or the Log4j API.
- Wanting to swap backends without modifying hundreds of classes containing log statements.
- Encountering different errors between `gradle run`, Maven tests, IDE runs, packaged JARs, and Docker images.

**Terminology note:** In SLF4J 1.7 and earlier, a "binding" was typically a special class; in SLF4J 2.x, the proper technical term is a **provider** loaded by Java `ServiceLoader`. Both are sometimes referred to collectively as "runtime binding," but you must diagnose the exact version properly.

## 2. Distinguishing API, Facade, Binding, Provider, and Backend

| Concept | Responsibility | Example |
| --- | --- | --- |
| Logging facade/API | Defines backend-independent logging calls | `org.slf4j.Logger`, `LoggerFactory` |
| Legacy binding | Connects the SLF4J 1.7 API to an implementation | JAR containing `org.slf4j.impl.StaticLoggerBinder` |
| Modern provider | Connects the SLF4J 2.x API to an implementation | `SLF4JServiceProvider` discovered by ServiceLoader |
| Logging backend | Handles logger hierarchy, levels, filters, appenders, encoders, and output destinations | Logback, Log4j 2, JUL, slf4j-simple |
| Bridge/adapter | Routes calls from another logging API to the target API/backend | `jul-to-slf4j`, `log4j-to-slf4j` |
| Runtime classpath | The classes and resources actually visible to the JVM/runtime classloader | JARs loaded in Gradle/Maven/IDE/deployed JAR |

A library with `slf4j-api` can still **compile successfully** yet print no logs at runtime due to a missing provider. Conversely, having a backend on the classpath with a version incompatible with the facade can also prevent the application from connecting.

**Connection time and configuration time are different:**

1. **Build/compile:** Code compiles against the API's methods and types.
2. **Runtime initialization:** SLF4J locates an appropriate binding/provider and initializes `ILoggerFactory`.
3. **Event emission:** The facade forwards calls to the active backend.
4. **Backend decides output:** Levels, filters, appenders/handlers, and encoders/layouts determine whether an event reaches the destination.

A well-written configuration file alone is not enough: if the runtime does not select the backend that the file targets, the configuration file may have no effect. For example, `logback.xml` cannot control `slf4j-simple` if SimpleLogger is the backend actually selected.

## 3. Bindings in SLF4J 1.7 and Providers in SLF4J 2.x

### 3.1. SLF4J 1.7: `StaticLoggerBinder`

In SLF4J 1.7.x and older, the binding JAR provides a class named:

```text
org/slf4j/impl/StaticLoggerBinder.class
```

During initialization, SLF4J 1.7's `LoggerFactory` uses this mechanism to locate an implementation. For example, 1.7-generation artifacts can connect to Logback or another backend.

Typical scenarios:

- **No valid binding:** SLF4J may warn that it failed to load `StaticLoggerBinder` and fall back to NOP.
- **One binding of the right generation:** Calls are forwarded to the corresponding backend.
- **Multiple bindings:** Prints a warning like `Class path contains multiple SLF4J bindings`; one binding is chosen, but you should not rely on discovery order.
- **Incompatible API/binding:** Having matching artifact names is not proof of a valid connection.

Sample message:

```text
SLF4J: Class path contains multiple SLF4J bindings.
SLF4J: Found binding in [...]
SLF4J: Actual binding is of type [...]
```

This is only an **abbreviated sample**. Actual paths, binding types, and warning prefixes depend on the version and classpath.

### 3.2. SLF4J 2.x: `SLF4JServiceProvider`

SLF4J 2.x switched to Java `ServiceLoader` and the SPI:

```java
org.slf4j.spi.SLF4JServiceProvider
```

Providers implement this SPI and register via a ServiceLoader-compatible mechanism, typically through the resource:

```text
META-INF/services/org.slf4j.spi.SLF4JServiceProvider
```

When `LoggerFactory` is initialized, the facade searches for providers, checks compatibility, and connects to one implementation to create Loggers.

For example, compatible `slf4j-api:2.0.x` and `logback-classic:1.5.x` can use Logback. `slf4j-simple:2.0.x` is a different backend/provider meant for simple environments. You **should not include both** in the same runtime just as a "fallback."

Several different outcomes:

```text
API 2.x + compatible 2.x provider:
    -> one backend is connected

API 2.x + no provider:
    -> no providers warning, NOP fallback

API 2.x + two providers:
    -> multiple providers warning, one provider is selected

API 2.x + 1.7 binding only:
    -> legacy binding is ignored; does not become a 2.x provider
```

Warnings for `multiple providers` and `no providers` are **two different issues**. In the first case, you typically need to remove the extra provider; in the second case, you need to add a provider of the matching generation or fix the classpath.

### 3.3. Comparing the Two Generations

| Comparison Axis | SLF4J 1.7.x | SLF4J 2.x |
| --- | --- | --- |
| Connection mechanism | `StaticLoggerBinder` | `ServiceLoader` and `SLF4JServiceProvider` |
| Multiple implementations warning | Multiple bindings | Multiple providers |
| No valid implementation | May fall back to NOP | Warns no providers and uses NOP |
| Legacy `StaticLoggerBinder` binding | Can be used when compatible | Ignored; not a valid provider |
| Provider/binding contract | Depends on API generation | Provider must be compatible with API 2.x SPI |

Do not mix `slf4j-api` 2.x with a 1.7.x binding and expect it to work as before. Likewise, do not just look at the name `logback-classic` while ignoring the Logback and SLF4J API versions managed by your framework.

## 4. How Does the Runtime Decide the Backend?

To make this concrete, assume application code is compiled against `slf4j-api` without importing any Logback classes.

```text
Successful compilation:
  MyService.java
       |
       v
  slf4j-api.jar
       |
       v
  MyService.class

At runtime:
  MyService.class + slf4j-api.jar + exactly one provider/backend
                                             |
                                             v
                                     LoggerFactory is initialized
                                             |
                                             v
                                       Actual ILoggerFactory
                                             |
                                             v
                                         log event
```

**Runtime binding is not an "unlimited hot-swap of backends while the application is running."** In the standard SLF4J model, `LoggerFactory` initialization and provider selection happen during runtime initialization, after which Loggers use the selected provider. Replacing JARs on disk while the application is running does not mean the running process automatically switches backends; switching backends is normally applied upon **restarting with the appropriate classpath and configuration**.

In addition, the actual Java classloader can be affected by an app server, plugin system, fat JAR, module path, or launcher. A dependency appearing in a build file does not guarantee it is packaged into the **runtime classpath used by the running process**.

### 4.1. Compile Classpath Differs from Runtime Classpath

With Gradle:

```groovy
dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}
```

This is a **Gradle configuration snippet**. `implementation` places the API on the application's compile and runtime classpaths, while `runtimeOnly` puts Logback on the runtime classpath without letting Java source code depend on Logback classes. This separation clarifies intent: **code depends on the facade, runtime depends on the implementation**.

A Java library published for others typically only needs to depend on the API; it should not force a provider/backend onto every consuming application. Depending on the build setup, use Gradle's `api` or `implementation` as appropriate for exposed public API types, but **do not bundle `logback-classic` into a library just to make logs work during tests**. Tests can have their own backend via test configuration.

### 4.2. Choosing a Different Backend While Keeping Java Source

To switch an application from Logback to `slf4j-simple` in a Gradle demo, replace the Logback runtime dependency:

```groovy
runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
```

with:

```groovy
runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
```

Do not keep both providers at the same time. Code calling `LoggerFactory` and `logger.info` can stay identical; **formatting, output destination, and configuration** do not stay identical because they depend on the backend. `logback.xml` is not a configuration file for `slf4j-simple`.

## 5. Common Backends and Providers

| Artifact | Role at Runtime | Notes |
| --- | --- | --- |
| `org.slf4j:slf4j-api` | API/facade | Not a provider |
| `ch.qos.logback:logback-classic` | Logback backend/provider | For matching SLF4J version |
| `org.slf4j:slf4j-simple` | Simple backend/provider | Suitable for demos/small CLIs |
| `org.slf4j:slf4j-nop` | No-op provider (discards logs) | NOP is an intentional choice; can "lose logs" if picked by mistake |
| `org.slf4j:slf4j-jdk14` | Forwards SLF4J calls to JUL | Do not confuse direction with `jul-to-slf4j` |
| `org.slf4j:slf4j-reload4j` | Forwards SLF4J calls to reload4j | Requires compatible version management |
| `org.apache.logging.log4j:log4j-slf4j2-impl` | SLF4J 2.x provider targeting Log4j 2 | Do not install alongside the reverse bridge `log4j-to-slf4j` |
| `org.apache.logging.log4j:log4j-slf4j-impl` | SLF4J 1.7 binding targeting Log4j 2 | Not a drop-in replacement for the 2.x provider |
| `org.slf4j:jul-to-slf4j` | Bridge JUL → SLF4J | Not a provider |
| `org.apache.logging.log4j:log4j-to-slf4j` | Bridge Log4j API → SLF4J | Not a provider |

**Only one provider should be selected in the application's runtime.** Multiple JARs using the SLF4J API simultaneously is completely normal. The issue is never "multiple libraries logging," but rather **multiple backends competing as the destination for one API**.

## 6. Complete Java 17 Example: Compile with Facade, Bind Logback at Runtime

The following hands-on example uses Java 17, Gradle, and SLF4J 2.x. The Java source **imports only `org.slf4j.*`**, with no Logback imports. At runtime, the `logback-classic` dependency becomes the provider, and `logback.xml` defines how messages are output.

We configure a simple pattern without timestamps so **stdout can be compared precisely**. In real applications, include timestamps, service/instance identifiers, `traceId`, and necessary context fields.

Directory structure:

```text
runtime-binding-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          BindingRuntimeDemo.java
      resources/
        logback.xml
```

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'runtime-binding-demo'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.BindingRuntimeDemo'
}
```

**Dependency explanation:** `slf4j-api` is what the Java code needs to compile. `logback-classic` supplies the runtime implementation and pulls in its required transitive dependencies. The version numbers above are **fixed pins for reproducibility**, not a claim that they are the latest versions. In real projects, use compatible dependency management/BOMs, update to security-vetted versions, and avoid adding a second provider.

### 6.3. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This configuration is for **Logback**. `ConsoleAppender` writes to stdout; `%level %msg%n` prints the level, the formatted message, and a newline. The root level `INFO` suppresses `DEBUG` output. When switching to another provider, you need the format and configuration file for that provider.

### 6.4. `src/main/java/demo/BindingRuntimeDemo.java`

```java
package demo;

import org.slf4j.ILoggerFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class BindingRuntimeDemo {
    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        System.out.println("factory=" + factory.getClass().getName());

        Logger log = LoggerFactory.getLogger(BindingRuntimeDemo.class);
        log.info("event=invoice.created invoiceId={}", "inv-9");
        log.debug("event=diagnostic.hidden");
        log.warn("event=payment.retry attempt={}", 2);
    }
}
```

Here `getILoggerFactory()` reveals **the factory actually chosen by the provider**. When using Logback Classic, the typical class name is `ch.qos.logback.classic.LoggerContext`. The code does not import a single Logback class. If you swap in another SLF4J API-compatible provider, the Java code continues calling the same methods unchanged.

### 6.5. Compiling and Running

From the `runtime-binding-demo` directory, with JDK 17 and a Gradle version supporting Java 17, run:

```bash
gradle run --quiet
```

If your project already includes a Gradle Wrapper, you can use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. The example does not generate a Wrapper; you need Gradle and access to the dependency repository on the first build.

**Program stdout when the runtime has only the Logback provider and uses the exact `logback.xml` above:**

```text
factory=ch.qos.logback.classic.LoggerContext
INFO event=invoice.created invoiceId=inv-9
WARN event=payment.retry attempt=2
```

**Why only three lines?** The first line prints the factory class. The `INFO` and `WARN` lines are accepted by the root Logger; the `{}` placeholders are formatted by the API/backend with the passed arguments. The `DEBUG` line is not printed because the root level is `INFO`. There are no timestamps, thread names, or Gradle log levels in the pattern above, making **program stdout** easy to verify; any Gradle build/download messages or platform warnings are external to the program.

### 6.6. Try Switching the Backend While Keeping Java Source

**In the same demo project**, replace Logback under `runtimeOnly` with:

```groovy
runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
```

Then run the same program again. Expected factory output for SimpleLogger:

```text
factory=org.slf4j.simple.SimpleLoggerFactory
```

This is the **stdout line from `System.out.println`**, not the entire output of the run; `slf4j-simple` writes logs to **stderr** by default and uses its own pattern. Do not treat `logback.xml` as SimpleLogger's configuration. Observing the backend change **without modifying `BindingRuntimeDemo.java`** is the goal of this exercise.

If the runtime has only `slf4j-api` 2.x and no provider, SLF4J may warn `No SLF4J providers were found` and use the NOP fallback. In that case, `INFO`/`WARN` calls emitted via SLF4J never reach a logging backend, even though business code still executes the calls.

## 7. Runtime Classpath: Where Errors Actually Happen

### 7.1. Gradle

In the application's runnable module, inspect the runtime classpath dependencies:

```bash
gradle dependencies --configuration runtimeClasspath
```

For multi-module applications, select the appropriate task and entry-point module. For example, in a project with an `app` module (illustrative name only):

```bash
gradle :app:dependencies --configuration runtimeClasspath
```

To find which dependency pulls in an unwanted provider:

```bash
gradle dependencyInsight --configuration runtimeClasspath --dependency slf4j-simple
gradle dependencyInsight --configuration runtimeClasspath --dependency logback-classic
```

Note that `testRuntimeClasspath` differs from `runtimeClasspath`; tests may use their own provider or pull in an extra backend from a test dependency.

```bash
gradle dependencies --configuration testRuntimeClasspath
```

With a Gradle Wrapper available, replace `gradle` with `./gradlew` on Unix or `gradlew.bat` on Windows.

### 7.2. Maven

A Maven application can depend on the API at compile time and add the backend at runtime scope. Example **`pom.xml` snippet**, not a standalone POM:

```xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.17</version>
    </dependency>
    <dependency>
        <groupId>ch.qos.logback</groupId>
        <artifactId>logback-classic</artifactId>
        <version>1.5.18</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

To identify whether a provider comes from a direct or transitive dependency:

```bash
mvn dependency:tree
```

If a library transitively pulls in `slf4j-simple`, `slf4j-nop`, or another backend, fix the dependency or add an exclusion on the **correct dependency path**. Do not fix it by deleting JAR files from the Maven/Gradle cache: a rebuild can re-download them and the conflict will return.

### 7.3. The Packaged Artifact Is the Final Proof

A build may look clean in the IDE, yet an executable JAR, container image, application server, or framework launcher can have a different classpath. When investigating, verify all of the following:

- Dependency graph of the **entry-point module**.
- Runtime/test classpath where the warning appears.
- Dependencies packaged inside the fat JAR or final distribution.
- JARs added by the server/container/runtime.
- Whether service provider descriptor resources are preserved during shading/packaging.

With SLF4J 2.x, an improperly packaged fat JAR can drop or overwrite `META-INF/services` and prevent `ServiceLoader` from finding the provider. Projects using shading tools must preserve/merge service descriptors properly. This is a form of **runtime packaging error** even though the build succeeds.

## 8. Diagnosing Which Backend Was Selected

When running code has SLF4J on the classpath, you can print:

```java
System.out.println(
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName()
);
```

This is a **code snippet**, not a standalone runnable program. Common class names:

| Detected Factory | Interpretation |
| --- | --- |
| `ch.qos.logback.classic.LoggerContext` | Using Logback Classic |
| `org.slf4j.simple.SimpleLoggerFactory` | Using SimpleLogger |
| `org.slf4j.helpers.NOPLoggerFactory` | Not emitting logs through a normal backend |
| Log4j 2 backend factory | SLF4J is connected to the Log4j 2 provider |

The factory name is evidence of **which implementation SLF4J is using**, not that every event is reaching your file or console. If logs are still missing despite the right factory, check logger levels, filters, appenders, encoders, and log collection targets next.

### 8.1. Step-by-Step Investigation Workflow

1. Identify the **actual `slf4j-api` version** at runtime.
2. If 1.7, look for a `StaticLoggerBinder` binding; if 2.x, look for an `SLF4JServiceProvider` provider.
3. Read SLF4J's initialization messages, distinguishing **missing**, **multiple**, and **incompatible**.
4. Inspect the dependency graph, exclude unwanted providers, and verify compatible versions.
5. Check the actual `ILoggerFactory`, then inspect the configuration for that specific backend.
6. Emit a test `INFO`, `WARN`, and exception event per the desired configuration.
7. Verify stdout, stderr, files, or collectors receive the events; also check deployed/test artifacts if they differ from local.

### 8.2. Common Messages

```text
SLF4J: Class path contains multiple SLF4J bindings.
```

This pattern belongs to 1.7 and multiple bindings. In 2.x, the equivalent message typically contains `multiple SLF4J providers`. If you see:

```text
SLF4J(W): No SLF4J providers were found.
```

you need to check for a **missing 2.x provider**, not "too many." The messages above are **representative lines**, not the full stdout/stderr of a run; prefixes may vary by version.

When a provider is missing, do not add both `slf4j-simple` and `logback-classic` "just to be safe"; that easily causes multiple providers. Choose the one backend that fits your needs.

## 9. Binding vs. Bridge: Avoiding Log Forwarding Loops

A **binding/provider** answers "which backend will SLF4J calls go to?" A **bridge** forwards calls **from another logging API** into SLF4J or vice versa. Artifacts with very similar names but opposite directions are a common source of errors.

### 9.1. JUL and SLF4J

```text
JUL API --jul-to-slf4j--> SLF4J API --Logback provider--> Logback
```

`jul-to-slf4j` routes logs from JUL to SLF4J when its bridge/handler is properly installed, but it is **not an SLF4J provider**. Conversely:

```text
SLF4J API --slf4j-jdk14--> java.util.logging (JUL)
```

This is a provider that sends SLF4J calls to JUL. If you configure **both directions simultaneously** with the corresponding bridge installed, a forwarding loop `SLF4J → JUL → SLF4J → ...` can occur. Never add a bridge just because its name contains "slf4j"; always verify the source → target arrow.

### 9.2. Log4j 2 and SLF4J

```text
SLF4J API --log4j-slf4j2-impl--> Log4j 2 backend
```

In contrast to:

```text
Log4j API --log4j-to-slf4j--> SLF4J API
```

**Do not install `log4j-slf4j2-impl` together with `log4j-to-slf4j` on the same execution path**, as bidirectional routing can cause loops or conflicts that the backend cannot handle properly. Similarly, `log4j-slf4j-impl` targets the SLF4J 1.7 API generation and is not a full equivalent for 2.x.

Just because a bridge is not a provider does not mean it is harmless: changing a bridge can redirect logs from libraries using JUL or the Log4j API elsewhere or stop them from being collected.

## 10. Frameworks, Multi-Module Apps, and Deployment Environments

### 10.1. Spring Boot and Frameworks That Manage the Backend

Many Spring Boot applications use the default logging starter based on Logback. In that setup:

- You do not need to manually add a second provider just to call `LoggerFactory.getLogger()`.
- Whether `logback.xml` or `logback-spring.xml` takes effect depends on the configuration mechanism and Spring Boot version.
- If switching to Log4j 2, adjust the proper **starter/dependency/provider** and exclude the old backend; do not just add Log4j 2 JARs alongside Logback.
- Transitive dependencies from libraries can bring in extra providers, producing warnings that appear only at runtime.

Identify the actual backend before editing config files. A completely valid `logback.xml` will not control the application if SLF4J is actually bound to SimpleLogger or Log4j 2.

### 10.2. Libraries and Applications Have Different Responsibilities

**Library:** Should log only through an API that the consuming application can control, such as SLF4J, and generally should not force a provider into its users' runtime dependencies.

**Application:** Chooses a suitable provider, configures log levels, encoders/formatters, appenders, and governance policies. This is the right place to declare a `runtimeOnly` backend and audit the dependency tree.

**Test:** May need a backend for test output, but `testRuntimeClasspath` can differ from the real runtime environment. Passing tests do not prove production runtime binding is correct.

### 10.3. Classloaders and Module Systems

In plugin systems or application servers, different classloaders can see different dependencies. An isolated module may bind to a different provider than the host application if class loading differs. With the Java Module System, module visibility and `provides`/`uses` declarations or service descriptors also affect `ServiceLoader`. Therefore, investigate the exact classloader and runtime the application uses rather than inferring solely from build files in the source directory.

## 11. Common Errors and Fixes

| Symptom | Possible Cause | Appropriate Action |
| --- | --- | --- |
| Builds fine, no logs emitted | Only API present, no provider; NOP selected; or level/filter blocks it | Check warnings, factory, and runtime provider before tweaking levels |
| `logback.xml` exists, formatting differs | Actual provider is not Logback | Print factory class, inspect transitive dependencies |
| SLF4J 1.7 reports multiple bindings | Two JARs both contain `StaticLoggerBinder` | Exclude the extra binding on the right dependency branch |
| SLF4J 2.x reports multiple providers | Two providers via ServiceLoader | Keep only one appropriate provider |
| API 2.x with 1.7 binding JAR still uses NOP | Legacy binding is ignored | Use a compatible 2.x provider |
| `getILoggerFactory()` returns NOP | No valid implementation or `slf4j-nop` intentionally used | Add or select the provider you need |
| CLI works, fat JAR loses logs | Provider dropped or descriptor lost during packaging | Inspect artifact, ServiceLoader descriptors, and launcher |
| Tests log, deployed app does not | Different classpath or environment configuration | Compare runtime, test, and deployed artifacts |
| Duplicate log entries | Appenders at multiple levels, additivity, multiple routing paths | Check backend config and bridges; do not blame everything on multiple providers |
| Log4j/JUL routing errors | Bridge points opposite to the selected provider | Redraw log flow arrows, remove bidirectional loop |
| Want to swap provider without restart | `LoggerFactory` is already initialized | Update runtime dependencies/config and redeploy/restart |
| Some messages on stderr instead of stdout | Backend defaults to stderr, or SLF4J internal warnings | Check the provider's output target; do not mistake stderr for lost logs |

### Avoid Fixes That Only Mask Symptoms

- Do not add `slf4j-nop` to silence warnings if you still want logs.
- Do not exclude `slf4j-api` just because you see SLF4J in the dependency tree; the API is still required.
- Do not rely on JAR ordering to pick a provider when multiple implementations exist.
- Do not assume initialization warnings are log events going through your appenders. SLF4J startup warnings may be printed directly to stderr.
- Do not mix API/binding generations without checking compatibility documentation.
- Do not manually edit the dependency cache; update build config and re-verify the runtime artifact.

## 12. Practice Exercises

**Exercise A — Identify the backend:** Keep `BindingRuntimeDemo.java` unchanged, run with Logback as in Section 6, and record the factory name and output. Replace only the runtime provider with SimpleLogger and run again. Explain why the Java source did not change yet the factory and log formatting differ.

**Exercise B — Reproduce a missing provider:** Remove the `runtimeOnly` line from the demo in your practice environment. Predict SLF4J 2.x's missing-provider warning and NOP fallback. Verify by printing the factory. Then restore a single compatible provider. This is an experiment; never intentionally deploy to production without a backend.

**Exercise C — Multiple providers:** In your local demo, add both `slf4j-simple` and `logback-classic` at runtime. Predict the multiple-providers warning. **Do not predict which backend wins**; observe the factory and explain why the extra provider must be removed. After testing, restore the single-backend configuration.

**Exercise D — Bidirectional bridge:** Draw arrow diagrams for `jul-to-slf4j`, `slf4j-jdk14`, `log4j-to-slf4j`, and `log4j-slf4j2-impl`. Identify which pairs create a routing loop risk when used together; there is no need to actually run a dangerous loop configuration.

## 13. Runtime Binding Architecture Checklist

- [ ] Source code depends on the chosen facade/API, without importing backends across business logic.
- [ ] The **runtime** SLF4J API version is verified.
- [ ] For SLF4J 1.7, a compatible `StaticLoggerBinder` binding is used; for SLF4J 2.x, an `SLF4JServiceProvider` provider is used.
- [ ] Only **one** intentional binding/provider exists in the application's runtime.
- [ ] `ILoggerFactory` resolves to the expected backend and its corresponding config file.
- [ ] Logger levels, filters, appenders/handlers, and formatters/encoders produce the expected output.
- [ ] No reverse-direction bridge exists that could cause a forwarding loop.
- [ ] `runtimeClasspath`, `testRuntimeClasspath`, and deployed artifacts have been checked where environments differ.
- [ ] Service descriptors are properly preserved during packaging/shading if using SLF4J 2.x.
- [ ] Shared libraries do not force a provider onto consuming applications.
- [ ] Startup warnings, INFO/WARN/ERROR output, and log destinations have been verified.
- [ ] Backend-switching plans include dependency updates, config updates, and a restart, rather than expecting arbitrary hot-swaps.

### References

- [SLF4J Manual](https://www.slf4j.org/manual.html): Facade API and runtime providers.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): Differences between SLF4J 1.7 and 2.x.
- [SLF4J Error Codes](https://www.slf4j.org/codes.html): No providers, multiple providers, ignored bindings, and related warnings.
- [Logback Manual](https://logback.qos.ch/manual/index.html): Logback backend, Appenders, levels, and configuration.
- [Apache Log4j components](https://logging.apache.org/log4j/2.x/components.html): API, providers, and bridges in Log4j 2.

**Conclusion:** **Runtime binding** is the link connecting the facade to the backend when the application initializes. In SLF4J 1.7, this link relies on `StaticLoggerBinder`; in SLF4J 2.x, it relies on `SLF4JServiceProvider` and `ServiceLoader`. Designing code to depend on the API, keeping only one compatible provider at runtime, checking the actual factory, and avoiding bidirectional bridges will help you swap backends safely, avoid lost logs, and keep business logic decoupled from any specific implementation.