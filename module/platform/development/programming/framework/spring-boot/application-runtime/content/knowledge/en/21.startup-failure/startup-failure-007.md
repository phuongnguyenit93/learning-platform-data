# Writing AbstractFailureAnalyzer and Registering via META-INF/spring.factories in Spring Boot

## 1. Goal: turn hard-to-read startup errors into clear remediation steps

When a Spring Boot application starts up, an exception can be wrapped across many layers:

```text
SpringApplication.run(...)
  -> ApplicationContext.refresh()
     -> BeanCreationException
        -> BeanInstantiationException
           -> MissingWarehouseEndpointException
              "Required property warehouse.endpoint is missing"
```

Operators new to the service sometimes see only a long stack trace and do not know **which property is missing, where to configure it, and what to do next**. Spring Boot provides **`FailureAnalyzer`** to translate a **recognized startup error type** into a `FailureAnalysis` containing:

- **Description:** briefly explains the failing condition in operator-friendly language.
- **Action:** suggests concrete remediation steps that can be taken immediately.
- **Cause:** the related exception, preserving technical context for diagnostics.

A familiar banner on startup failure:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

A required configuration property for WarehouseGateway is missing:
warehouse.endpoint

Action:

Configure warehouse.endpoint in application.properties or supply
--warehouse.endpoint=https://example.invalid/api
```

This is an **illustrative simulation of the expected message**. Line wrapping, log levels, ANSI colors, and surrounding lines may vary by version, logger, and runtime environment. Content provided by the analyzer appears in the Description/Action area when the corresponding reporter handles the failure.

**Direct topic of this lesson:** create a class extending `AbstractFailureAnalyzer<T>`, properly implement `analyze(Throwable rootFailure, T cause)`, and declare its fully qualified class name in `src/main/resources/META-INF/spring.factories` under the key **`org.springframework.boot.diagnostics.FailureAnalyzer`**.

There is no need to create a controller, add a REST endpoint, or **annotate the analyzer with `@Component`**. This is a **bootstrap/startup** diagnostic mechanism discovered by Spring Boot through factory registration.

## 2. Where does FailureAnalyzer sit in the startup lifecycle?

Typical handling flow on startup failure:

```text
JVM invokes main(String[] args)
           |
           v
SpringApplication.run(args)
           |
Prepare Environment, create ApplicationContext
           |
Load config / register bean definitions
           |
refresh() -> create beans or run initialization
           |
      Exception occurs
           |
           v
Spring Boot handles startup failure
           |
Discover registered FailureAnalyzers from
META-INF/spring.factories
           |
  +--------+----------------------------+
  |                                     |
  v                                     v
Analyzer recognizes error             Does not recognize
  |                                     |
  v                                     v
Returns FailureAnalysis               Returns null
  |                                     |
  +--------> A matching analyzer yields a result
                      |
                      v
     FailureAnalysisReporter displays
        Description / Action
                      |
                      v
     Startup fails, context is cleaned up
     via Boot's startup failure mechanism
```

The diagram is simplified for learning. Boot includes multiple built-in `FailureAnalyzer`s, and failure reporting also involves logging, exception reporters, and context cleanup. **An analyzer is not a mechanism to "catch every error and let the app keep running".** It is invoked while **handling a startup failure that has already occurred**.

### Things to distinguish

1. `FailureAnalyzer` produces **diagnostic information**; it does not auto-fix properties or create missing beans.
2. `FailureAnalysisReporter` is responsible for **reporting analysis results**; by default Boot ships a logging reporter.
3. `AbstractFailureAnalyzer<T>` is a **convenience base class** for analyzers targeting a specific `Throwable` type in the cause chain.
4. `ApplicationFailedEvent` is the event tied to a failed startup. Event listeners have a different purpose from building Description/Action.
5. `@ControllerAdvice` / `@ExceptionHandler` apply to handling exceptions in Web request flows after startup, **not as the primary way to explain BeanCreationException at startup**.
6. A `try/catch` outside `SpringApplication.run` can handle or record custom data, but does not replace Boot's `FailureAnalyzer` registry mechanism.

Most importantly, **startup still fails** after the analyzer reports the error. If mandatory configuration is missing, printing a friendly message does not make the application ready to serve traffic.

## 3. Three API concepts: FailureAnalyzer, AbstractFailureAnalyzer, and FailureAnalysis

### 3.1. FailureAnalyzer is an interface

Core signature:

```java
package org.springframework.boot.diagnostics;

// Abbreviated API outline for explanation, do not redeclare in project:
@FunctionalInterface
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
```

An analyzer can return:

- **`new FailureAnalysis(description, action, cause)`** when enough information exists to explain accurately.
- **`null`** when unable to analyze or inapplicable to that exception. Spring Boot can then try other analyzers.

Do not produce a generic `FailureAnalysis` for every exception. If you match the wrong failure, your business message may mask a more accurate built-in Spring Boot diagnosis.

### 3.2. AbstractFailureAnalyzer<T extends Throwable> filters by exception type

Instead of manually walking `Throwable.getCause()` repeatedly, extend:

```java
public final class MyFailureAnalyzer
        extends AbstractFailureAnalyzer<MyDomainException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, MyDomainException cause) {
        // Build appropriate Description, Action, Cause.
    }
}
```

This is an **illustrative skeleton**, lacking `MyDomainException` or imports.

The signature **must match exactly**:

```java
protected FailureAnalysis analyze(Throwable rootFailure, T cause)
```

`rootFailure` is the original throwable passed to the analyzer (typically the outer bootstrap exception). `cause` is the throwable **of exact generic type T** that the base class found in the cause chain. If a `BeanCreationException` wraps a `MissingWarehouseEndpointException` underneath, you receive `cause` already unwrapped to that exact type.

The base class invokes this method **once a matching exception type is found**. Do not override the interface's `analyze(Throwable failure)` method just to reimplement cause traversal unnecessarily.

### 3.3. FailureAnalysis is the report payload

Spring Boot 3.3 constructor:

```java
new FailureAnalysis(
        "Description of why startup failed",
        "Action the operator needs to take",
        cause
);
```

This is an API usage snippet requiring `org.springframework.boot.diagnostics.FailureAnalysis` imported and a real `cause` variable.

| Parameter | Meaning | Notes |
|---|---|---|
| `description` | What is wrong, in which component | Name exact keys/resources, avoid vague phrasing |
| `action` | Concrete remediation steps | Name property, file/CLI, valid condition |
| `cause` | Related underlying exception | Preserves traceability; do not fabricate dummy exceptions |
| Returning `null` | Analyzer declines handling | Gives other analyzers a chance to analyze |

Never return just `new FailureAnalysis(cause.toString(), "Contact admin", cause)` if you can state **which property is missing** and **how to pass its value**. The real value of an analyzer lies in turning a complex failure into a clear action, not echoing the raw stack trace.

## 4. Why create a dedicated business exception?

There are two options:

**Option A — match a framework exception**, such as `BeanCreationException` or `IllegalArgumentException`. Convenient for a very specific error, yet easy to over-match: an application can have dozens of unrelated `IllegalArgumentException`s.

**Option B — create a dedicated exception**, such as `MissingWarehouseEndpointException`. This is the approach used in the lab.

```java
public final class MissingWarehouseEndpointException
        extends RuntimeException {

    private final String propertyName;

    public MissingWarehouseEndpointException(String propertyName) {
        super("Required property is missing: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return propertyName;
    }
}
```

Above is the body of **one Java class**; in the project it has its own package and file path in Section 7.

When a bean requires a mandatory property, it throws this dedicated exception. Spring may wrap it in `BeanInstantiationException` or `BeanCreationException`, yet `AbstractFailureAnalyzer<MissingWarehouseEndpointException>` locates the right-typed object in the cause chain.

**Benefits:**

- The analyzer handles only cases it clearly understands.
- Description/Action can read the property name stored on the exception without parsing stack trace text.
- You can unit-test the analyzer without starting a Spring context.
- Does not override Boot's built-in analyzer messages for unrelated failures.
- Extensible across multiple properties/cases of the same kind when the contract is explicit.

Never put passwords or access tokens into exception messages or fields. If an exception holds secret values, reporters or other stack traces may expose them.

## 5. Registration rules via spring.factories

### 5.1. Correct file location

Place the file on the **runtime classpath**:

```text
src/main/resources/META-INF/spring.factories
```

Do not confuse with:

```text
src/main/java/META-INF/spring.factories
src/test/resources/META-INF/spring.factories
application.properties
spring.properties
```

`src/test/resources` only serves the test runtime; for the analyzer to work when running the real JAR, put registration in **main resources** or inside a dependency JAR carrying that resource.

When Gradle builds, resource files are placed on the classpath; when packaging a Spring Boot fat JAR, the main JAR contains the entry:

```text
BOOT-INF/classes/META-INF/spring.factories
```

### 5.2. Exact key and class name

A valid single-line entry:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

**On the left** is the full name of the extension point interface fixed by Spring Boot; **on the right** is the fully qualified class name of the example implementation.

Multiple analyzers syntax:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.first.FirstFailureAnalyzer,\
com.example.second.SecondFailureAnalyzer
```

Trailing `\` in Java properties allows line continuation; commas separate multiple implementations. **In Section 7's full project**, we register only one analyzer on **a single line**, avoiding line-continuation and whitespace mistakes.

**Do not write**:

```properties
# Wrong: key is not Boot's standard interface name
FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

**Do not use**:

```properties
# Wrong for this purpose: this is the auto-configuration extension point name
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

### 5.3. spring.factories vs the auto-configuration import mechanism

Spring Boot 3.x registers auto-configurations via:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

However, **that does not replace `FailureAnalyzer` registration**. For custom failure analyzers in Spring Boot 3.3, continue using:

```text
META-INF/spring.factories
org.springframework.boot.diagnostics.FailureAnalyzer=...
```

Moving your custom analyzer entry into `AutoConfiguration.imports` can prevent it from being invoked during failure analysis. These are two distinct extension-point groups: normal Boot auto-configuration is imported into the bean context, whereas failure analyzers are loaded to **diagnose errors when the context may have failed to initialize**.

### 5.4. Does the analyzer need @Component or @Bean?

**No.** An analyzer declared in `spring.factories` can be instantiated by Spring Boot's factory loading mechanism without Spring component scanning.

Putting `@Component` on the analyzer class **is not a reliable substitute** for this stage; when the context fails to refresh, normal bean creation may not have completed. In the example, the analyzer has **no `@Component`** and **no `@Bean` method**.

The analyzer must be an implementation that the loader can instantiate. The simplest pattern is a **public concrete class with a public no-argument constructor**. If no constructor is declared, a public Java class has a default constructor matching the class visibility; in the demo we either write an explicit constructor or leave a plain public class with no declared constructors.

## 6. Types of failures to handle vs avoid

### 6.1. High-diagnostic-value failures

Examples:

- A required property `warehouse.endpoint` is missing.
- Two business flags conflict and removing one can be recommended.
- An internal schema file has an unsupported version with a specific upgrade action.
- A custom startup validation exception exposes a field naming the violated rule.
- An internal service URL configuration violates the published contract.

Common trait: **the analyzer has concrete enough information** to write an unambiguous action.

### 6.2. Failures you should not match too broadly

Do not write an analyzer like:

```java
public final class CatchEverythingAnalyzer
        extends AbstractFailureAnalyzer<RuntimeException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, RuntimeException cause) {
        return new FailureAnalysis(
                "Application failed due to a runtime exception.",
                "Check configuration.",
                cause);
    }
}
```

This is an **illustrative anti-pattern**. Because `RuntimeException` covers so many errors, the analyzer can catch exceptions outside what you understand, masking Boot's built-in analysis. Use a dedicated exception instead and return `FailureAnalysis` only when you have a reliable action.

Even a dedicated analyzer can return `null` when that exception type lacks sufficient data, such as a blank property name or missing cause details. This gives another analyzer a chance to handle it.

## 7. Runnable project: Spring Boot 3.3.5, Java 17, and Gradle

This project uses the package name:

```text
com.example.failureanalysis
```

Startup scenarios:

- If `warehouse.endpoint` is **missing**, Spring fails creating bean `WarehouseGateway`, throwing `MissingWarehouseEndpointException`; Boot loads the custom analyzer and prints Description/Action.
- If `warehouse.endpoint` is provided, the bean is built normally, and `ApplicationRunner` prints a line proving the app passed startup.
- No real URL is called. The example merely **stores and prints the configuration value**, avoiding network dependencies.

### 7.1. Directory structure

```text
failure-analyzer-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/failureanalysis/
    │   │   ├── FailureAnalyzerDemoApplication.java
    │   │   ├── MissingWarehouseEndpointException.java
    │   │   └── MissingWarehouseEndpointFailureAnalyzer.java
    │   └── resources/
    │       ├── application.properties
    │       └── META-INF/
    │           └── spring.factories
    └── test/
        └── java/com/example/failureanalysis/
            └── MissingWarehouseEndpointFailureAnalyzerTest.java
```

Classes, packages, and paths in the example must **match exactly**. If you rename the package, update both `spring.factories` and package declarations in source files.

### 7.2. settings.gradle

**`settings.gradle`**:

```groovy
rootProject.name = 'failure-analyzer-demo'
```

### 7.3. build.gradle

**`build.gradle`** (Gradle Groovy DSL):

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3 uses Java 17+. `spring-boot-starter` suffices for this non-web demo. `spring-boot-starter-test` provides JUnit Jupiter and testing tools. If the project lacks a Gradle Wrapper yet, generate one with a compatible Gradle installation or obtain a skeleton from Spring Initializr before running `./gradlew`; `build.gradle` itself does not generate the Wrapper.

### 7.4. application.properties

**`src/main/resources/application.properties`**:

```properties
spring.application.name=failure-analyzer-demo

# Intentionally DO NOT set warehouse.endpoint here to test startup failure.
```

Do not automatically add the endpoint to the file upfront, or you will not see the failure branch. In the success run we pass the property via the command line.

### 7.5. Business exception

**`src/main/java/com/example/failureanalysis/MissingWarehouseEndpointException.java`**:

```java
package com.example.failureanalysis;

public final class MissingWarehouseEndpointException
        extends RuntimeException {

    private final String propertyName;

    public MissingWarehouseEndpointException(String propertyName) {
        super("Required property is missing: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return propertyName;
    }
}
```

This exception has a clear name and field. Throwing it during bean construction causes bootstrap to fail. Avoid placing secret values into exception messages; here we use only the **property name**.

### 7.6. Application and bean requiring configuration

**`src/main/java/com/example/failureanalysis/FailureAnalyzerDemoApplication.java`**:

```java
package com.example.failureanalysis;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class FailureAnalyzerDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(FailureAnalyzerDemoApplication.class);

        // Demo does not use an HTTP server.
        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    WarehouseGateway warehouseGateway(Environment environment) {
        String endpoint =
                environment.getProperty("warehouse.endpoint");

        if (endpoint == null || endpoint.isBlank()) {
            throw new MissingWarehouseEndpointException(
                    "warehouse.endpoint");
        }

        return new WarehouseGateway(endpoint);
    }

    @Bean
    ApplicationRunner printConfiguredGateway(
            WarehouseGateway gateway) {
        return arguments -> System.out.println(
                "READY: warehouse.endpoint = " + gateway.endpoint());
    }

    public record WarehouseGateway(String endpoint) {
    }
}
```

**Line-by-line explanation:**

1. `@SpringBootApplication` creates the entry point for component scanning and auto-configuration in the project.
2. `WebApplicationType.NONE` avoids needing a server or running into port 8080 conflicts.
3. `@Bean WarehouseGateway` instructs Spring to create a singleton during default context refresh (with global lazy off).
4. `Environment.getProperty("warehouse.endpoint")` reads the effective configuration. It can come from files, environment variables, Java system properties, or CLI options per Boot's precedence rules.
5. If the property is missing or blank, the bean factory **throws the custom exception**. Spring may wrap it in one or more bean creation exceptions.
6. If the property has a value, it returns a Java `record`; the record holds a single endpoint field used in the example.
7. `ApplicationRunner` runs **after context refresh**. It only executes when startup reaches the runner stage. In the missing-property case, the runner **does not print `READY`**.
8. The example treats the URL purely as a string, **creates no HTTP client**, and sends no requests; a dummy endpoint works for testing.
9. `WarehouseGateway` is nested inside the application class to keep file count small, while the exception and analyzer are public classes in separate files.

**Boundary:** if `spring.main.lazy-initialization=true` is enabled and no eager bean requests `WarehouseGateway` before Ready, when the error surfaces can shift. This lab keeps the non-lazy default to guarantee a startup failure is observed.

### 7.7. Dedicated AbstractFailureAnalyzer

**`src/main/java/com/example/failureanalysis/MissingWarehouseEndpointFailureAnalyzer.java`**:

```java
package com.example.failureanalysis;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class MissingWarehouseEndpointFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingWarehouseEndpointException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingWarehouseEndpointException cause) {

        String propertyName = cause.getPropertyName();

        if (propertyName == null || propertyName.isBlank()) {
            return null;
        }

        String description =
                "A required configuration property for "
                + "WarehouseGateway is missing: " + propertyName;

        String action =
                "Configure " + propertyName
                + " in application.properties or supply "
                + "--" + propertyName
                + "=https://example.invalid/api";

        return new FailureAnalysis(description, action, cause);
    }
}
```

**Technical breakdown:**

- The class has **no `@Component`** and **no `@Bean`**. It is discovered via `spring.factories`.
- `AbstractFailureAnalyzer<MissingWarehouseEndpointException>` specifies the **exception type to find**.
- `@Override` targets the exact **two-parameter** overload; a signature mismatch fails to compile as an override.
- `rootFailure` is the outer exception sent to the analyzer. Here we do not need to print all of it; operators only need the property name and action.
- `cause` holds the exact exception to analyze, carrying the `propertyName` field.
- If `propertyName` is invalid, it returns `null` to avoid reporting a bogus action. That avoids **hijacking** handling when details are lacking.
- `new FailureAnalysis(description, action, cause)` retains a relevant throwable as cause.
- Never attempt to auto-fix or write new properties inside the analyzer; startup has already failed and no new side effects should occur.
- Never log the entire `Environment` in an analyzer; configuration may contain secrets.

### 7.8. Registration in META-INF/spring.factories

**`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

**This is a mandatory step of the lesson.** If the file is missing, in the wrong directory, has the wrong key, or misspells the class name, Boot will not load the custom analyzer even though the Java class compiled cleanly.

During build:

```text
src/main/resources/META-INF/spring.factories
    -> build/resources/main/META-INF/spring.factories
    -> BOOT-INF/classes/META-INF/spring.factories inside bootJar
```

Verify file contents under main resources rather than only checking that `MissingWarehouseEndpointFailureAnalyzer` appears in the IDE.

## 8. Running and verifying both branches

### 8.1. Failure branch — missing property

On Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Without an external config source supplying `warehouse.endpoint`, Spring cannot create `WarehouseGateway`. The console should show an analysis similar to:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

A required configuration property for WarehouseGateway is missing:
warehouse.endpoint

Action:

Configure warehouse.endpoint in application.properties or supply
--warehouse.endpoint=https://example.invalid/api
```

Note that this **illustrates message structure**, not a guarantee that every log line wraps identically. Gradle `bootRun` may report task failure and the Java process exits non-zero; that is the **expected result for the missing-configuration test case**, not a broken analyzer.

**There is no `READY: warehouse.endpoint = ...` line** in this scenario, because the context never refreshed successfully to invoke the runner.

### 8.2. Success branch — passing CLI property

Linux/macOS:

```bash
./gradlew bootRun --args='--warehouse.endpoint=https://example.invalid/api'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--warehouse.endpoint=https://example.invalid/api"
```

Ignoring Spring/Gradle logs, the line printed by the runner is:

```text
READY: warehouse.endpoint = https://example.invalid/api
```

On this branch:

1. The CLI option enters `Environment` by Spring Boot default.
2. The bean factory sees a non-blank property and builds `WarehouseGateway`.
3. No exception occurs for the custom analyzer to handle.
4. The runner executes and prints the success message.
5. Because this is a non-web app with no other non-daemon background workers, the program normally exits after startup/runner completion.

Do not hardcode assertions on log line counts, banner colors, or exact startup timings.

### 8.3. Running the packaged JAR

Build:

```bash
./gradlew bootJar
```

Without passing the property:

```bash
java -jar build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar
```

Passing the property:

```bash
java -jar build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar --warehouse.endpoint=https://example.invalid/api
```

The value here is an `example.invalid` documentation URL and **is never connected to by the program**. In real apps, do not treat "property present" as proof the endpoint is reachable; add appropriate validation and health checks.

### 8.4. Verifying packaged resources

After `bootJar`:

Linux/macOS:

```bash
jar tf build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar | grep 'META-INF/spring.factories'
```

Windows PowerShell:

```powershell
jar tf build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar | Select-String 'META-INF/spring.factories'
```

You should see:

```text
BOOT-INF/classes/META-INF/spring.factories
```

If the entry is absent, check `src/main/resources`, `processResources` config, and the build command. If the entry exists yet the analyzer still does not run, inspect the **file contents** and class name, not just the path.

## 9. Unit testing the analyzer without starting ApplicationContext

**`src/test/java/com/example/failureanalysis/MissingWarehouseEndpointFailureAnalyzerTest.java`**:

```java
package com.example.failureanalysis;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MissingWarehouseEndpointFailureAnalyzerTest {

    private final MissingWarehouseEndpointFailureAnalyzer analyzer =
            new MissingWarehouseEndpointFailureAnalyzer();

    @Test
    void recognizesCauseInsideWrapper() {
        MissingWarehouseEndpointException cause =
                new MissingWarehouseEndpointException(
                        "warehouse.endpoint");

        Throwable wrapped = new IllegalStateException(
                "Bean creation failed", cause);

        FailureAnalysis analysis = analyzer.analyze(wrapped);

        assertNotNull(analysis);
        assertTrue(analysis.getDescription()
                .contains("warehouse.endpoint"));
        assertTrue(analysis.getAction()
                .contains("--warehouse.endpoint="));
        assertSame(cause, analysis.getCause());
    }

    @Test
    void doesNotClaimUnrelatedFailure() {
        FailureAnalysis analysis =
                analyzer.analyze(new IllegalArgumentException(
                        "Some other startup problem"));

        assertNull(analysis);
    }

    @Test
    void missingPropertyNameDoesNotProduceMisleadingAdvice() {
        MissingWarehouseEndpointException cause =
                new MissingWarehouseEndpointException("");

        FailureAnalysis analysis = analyzer.analyze(cause);

        assertNull(analysis);
    }
}
```

In the first test:

- `rootFailure` is `IllegalStateException`, not the custom exception.
- The base class locates `MissingWarehouseEndpointException` in the cause chain.
- The test verifies description and action contain the property name, and `getCause()` is that exact exception.
- The second test confirms the analyzer **does not claim out-of-scope errors**.
- The third test confirms the `return null` branch when the property name is blank.

This is a **direct** unit test of the analyzer class; it **does not verify that `spring.factories` is loaded**. To verify wiring, write an integration test or run the real application as in Section 8 to observe the startup banner.

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

With proper project configuration, all tests above should pass. Do not claim unit tests alone prove factory registration works.

## 10. Checking spring.factories registration in tests

A lighter-weight way to verify registration than booting the whole app is Spring Framework's `SpringFactoriesLoader`. For instance, in an appropriate test:

```java
List<FailureAnalyzer> analyzers =
        SpringFactoriesLoader.loadFactories(
                FailureAnalyzer.class,
                getClass().getClassLoader());

boolean found = analyzers.stream().anyMatch(
        analyzer -> analyzer instanceof
                MissingWarehouseEndpointFailureAnalyzer);

assertTrue(found);
```

This is an **integration snippet** requiring `java.util.List`, `SpringFactoriesLoader`, and `FailureAnalyzer` imports inside a JUnit test method. In Spring Boot 3.3 / Spring Framework 6.1, `SpringFactoriesLoader.loadFactories` loads implementations instantiable with a suitable constructor.

Note: Boot-loaded `FailureAnalyzer`s may have special constructors/dependencies; a test loading **all analyzers from the classpath** this way may not be completely identical to Boot's `FailureAnalyzers` when passing `BeanFactory` or `Environment`. To reliably check registration of *one specific analyzer*, inspect `META-INF/spring.factories`, use version-appropriate registry helpers, or run an end-to-end startup test.

**Do not label a test "integration"** if it merely `new`s an analyzer in Java without checking factory registration.

## 11. Analyzers are not regular Spring beans: consequences

### 11.1. Why not inject with @Autowired like a service?

Analyzers may need to run **when the context fails during creation**. Never assume `@Autowired` fields/setters are processed like a normal bean. Specifically, field injection such as:

```java
@Autowired
private Environment environment;
```

inside a class loaded only via `spring.factories` may not go through the standard bean lifecycle, leaving the dependency `null`.

In this lesson, the analyzer only needs a field on the exception, so it **does not need Environment access**.

Spring Boot docs note that if a `FailureAnalyzer` genuinely needs `BeanFactory` or `Environment`, it can declare them as **constructor arguments** so Boot's analyzer loader supplies them when available. Still, in very early startup failures, context/Environment may be incomplete. Read the bare minimum, handle missing dependencies gracefully, and avoid calling beans/services that may themselves be why startup failed.

### 11.2. Do not use analyzers to modify the system

Avoid:

- Rewriting `application.properties` when an analyzer spots a missing property.
- Creating DB schemas, calling external APIs, or retrying network calls inside `analyze`.
- Initializing services that depend on a failed context.
- Swallowing exceptions and returning process success.
- Printing the entire `Environment` or secret values.

A good analyzer should be **lightweight, deterministic, free of significant side effects**, and provide clear actions. It is a tool to **explain why Boot failed**, not an automated remediation workflow.

### 11.3. Do not match overly broad error types

If a custom analyzer extends `AbstractFailureAnalyzer<Exception>` or `<RuntimeException>` and always returns `FailureAnalysis`, it can give wrong advice for unrelated failures.

Define a specific exception such as `MissingWarehouseEndpointException` or check sufficient conditions before returning an analysis. When unsure, **`return null`**. This is especially vital because many bean initialization errors are wrapped in common Spring runtime exceptions.

## 12. Distinguishing failure analyzers from related mechanisms

| Mechanism | When it runs | Used for | Not for |
|---|---|---|---|
| `FailureAnalyzer` | During startup failure handling when Boot checks analyzers | Producing Description/Action with clear cause | REST exception handler |
| `AbstractFailureAnalyzer<T>` | Base class for specialized analyzers | Finding cause of type T, reducing boilerplate | Bean that auto-fixes config |
| `FailureAnalysisReporter` | Reporting `FailureAnalysis` results | Printing logs/reports in custom formats | Finding the root cause |
| `ApplicationFailedEvent` | When `SpringApplication` startup fails | Listener reacting to startup failure | Auto-generating Description/Action like an analyzer |
| `ApplicationRunner` | After context refresh, before Ready | Startup tasks once beans exist | Analyzing failures before context is ready |
| `@PostConstruct` | During bean initialization | Preparing/validating bean state | Catch-all fix for all startup failures |
| `@ConfigurationProperties` validation | During property binding/validation | Catching wrong types, missing keys, constraint violations | Replacing custom domain analyzers when custom logic exists |
| `@ExceptionHandler` / `@ControllerAdvice` | During Web request handling | Returning responses on request errors | Catching `BeanCreationException` when `run` fails |
| `ConditionEvaluationReport` | Auto-configuration condition data | Diagnosing why auto-config matched/skipped | Always pinpointing business missing-property errors |

If you only need to report a standard Spring Boot property having the wrong type, built-in analyzers may already suffice. Custom analyzers shine when failures carry **custom domain semantics** needing specific remediation actions the framework cannot guess.

## 13. Multi-layered wrapped causes

A startup failure often has a chain:

```text
IllegalStateException
  -> BeanCreationException
       -> BeanInstantiationException
            -> MissingWarehouseEndpointException
```

The analyzer's generic type **does not require the custom exception to be outermost**. `AbstractFailureAnalyzer<T>` uses cause-chain lookup to locate the matching throwable. That is why the unit test `new IllegalStateException("...", cause)` in Section 9 works.

### Yet there are limits

- If an error is **swallowed** and no exception reaches the startup failure handler, the analyzer is never called.
- If the custom exception appears only in log text and **not in the cause chain** of the reported throwable, `AbstractFailureAnalyzer<CustomException>` will not find it in those logs.
- If an exception is attached as a **suppressed exception** rather than chained via `getCause()`, do not assume the base class finds it.
- If another analyzer produces a `FailureAnalysis` first and Boot uses that result, your custom analyzer's message may not be displayed.
- If the error happens **after startup succeeds** in a background task or request, failure analyzers do not handle those runtime errors.

When you need to match multiple unrelated error types without a clean generic hierarchy, implement `FailureAnalyzer` directly and inspect `Throwable` within tight bounds instead of forcing everything under an overly broad generic type.

## 14. Why didn't a compiled analyzer get called?

When you see a familiar startup failure with **no custom Description/Action**, check in order:

### 14.1. Wrong resource path

Needs:

```text
src/main/resources/META-INF/spring.factories
```

Not `src/main/java/META-INF`. In a fat JAR, verify `BOOT-INF/classes/META-INF/spring.factories`. In a Gradle multi-module build, the file must live in a **module included on the application's runtime classpath**.

### 14.2. Wrong key

`spring.factories` must use:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

Do not shorten to `FailureAnalyzer=...`, substitute `FailureAnalysisReporter=...`, or move to `AutoConfiguration.imports`.

### 14.3. Wrong package or class name

`spring.factories` uses the **fully qualified class name**. If the Java package is `com.example.failureanalysis` while the file says `com.example.failureAnalysis`, the classloader will not find the class (package names are case-sensitive).

### 14.4. Analyzer cannot be instantiated

The class must be concrete, accessible, have an appropriate constructor, and have all required dependencies on the classpath. If the constructor requires a service unavailable during startup failure, the analyzer may fail to instantiate.

**Simplest and most reliable pattern for your first analyzer:** public class, no constructor parameters, no Spring bean dependencies.

### 14.5. Wrong generic type

`AbstractFailureAnalyzer<MissingWarehouseEndpointException>` triggers only when the cause chain contains an exception of that type. If a bean throws a plain `IllegalArgumentException` without the custom exception, the two-argument method is not called.

Do not "fix" this by changing the generic type to `RuntimeException` and returning an analysis for everything.

### 14.6. Exception never reaches the startup handler

If code handles it like:

```java
try {
    validateConfig();
} catch (MissingWarehouseEndpointException ex) {
    log.warn("Invalid config; continuing", ex);
}
```

then startup may continue normally. There is no failure for the analyzer to explain. This is **illustrative pseudocode** requiring real `validateConfig` and `log` members. When configuration is mandatory, deliberately let startup fail with a clear exception.

### 14.7. Error occurs too late

If an exception is only thrown inside an endpoint when the first request arrives, that is a **runtime failure**, outside `SpringApplication.run(...)`'s startup pipeline. For fail-fast requirements, ensure validation runs during initialization or inside a runner before Ready.

### 14.8. Analyzer returns null

Even when the cause type matches, your method may return `null` if required data is missing. Check conditional branches and unit tests. `return null` is valid behavior, yet you should know why it happened.

### 14.9. Reporter or logging differs from expectations

Boot ships `LoggingFailureAnalysisReporter`. Depending on logging configuration, formatting or destination may differ from the example's stdout. Check stderr, log files, and log collectors. Never hardcode tests around ANSI color sequences.

### 14.10. Another analyzer handled the exception

Boot has many built-in analyzers. If you try to match a generic exception like `BeanCreationException`, a built-in analyzer may report before yours. Use domain-specific custom exceptions and keep matching narrow to reduce conflicts.

### 14.11. Resource overwritten when packaging multiple libraries

Multiple JARs can carry their own `META-INF/spring.factories`; the loader reads multiple resources on the classpath. However, if a build creates a **non-Boot shaded/uber JAR** and merges resources improperly, one `spring.factories` can overwrite another. Inspect the actual runtime artifact's classpath, not only the original source file.

### 14.12. Multi-module runs the wrong artifact

The module defining the analyzer may compile and pass tests while the application launches a different JAR omitting that module. Inspect the runtime dependency graph and final packaged contents.

## 15. Testing registration and end-to-end startup failure

Test layers should stay separated:

| Test level | What to do | What it proves |
|---|---|---|
| Analyzer unit test | Call `analyzer.analyze(exception)` | Analysis logic, Description/Action, returning null |
| Resource test | Check `META-INF/spring.factories` and class name | Registration file exists with right key |
| Startup integration | Launch app missing property, check banner/action and exit status | Boot discovers analyzer during failure |
| Success integration | Launch with valid property, verify runner | Does not falsely match or block valid startup |
| Packaged JAR smoke test | Run `java -jar` on actual artifact | Resources and classes packaged properly |
| Negative test | Throw unrelated error, verify analyzer declines | Prevents misreporting out-of-scope types |

### Output testing rules

**Do not assert the entire console output as one long verbatim string**, because logs vary in timestamps, colors, banners, stack traces, Gradle task progress, or built-in analyzer output. Assert on criteria instead:

- `APPLICATION FAILED TO START` header appears when the reporter renders the analysis.
- `warehouse.endpoint` appears in Description.
- `--warehouse.endpoint=` appears in Action.
- `READY: warehouse.endpoint` is absent when the property is missing.
- The process/application genuinely fails rather than swallowing the error.
- With a valid property, `READY: warehouse.endpoint = ...` appears and exits normally.

In unit tests, inspecting `FailureAnalysis` getters directly as in Section 9 is fast, resilient, and avoids logging setup.

### Stronger tests for multi-module setups

When the analyzer module is a shared library, add an integration test creating a minimal app using that library **without manually declaring the analyzer**. If startup failure still produces the custom Description/Action, you verify the library's `META-INF/spring.factories` truly loads via the classpath.

## 16. Should FailureAnalyzer read Environment or BeanFactory?

An early analyzer might want the active profile, application name, or configured properties. Keep these distinctions in mind:

- `Environment` may be prepared at certain stages, yet not all startup failures occur after the same milestone.
- `BeanFactory` may be incomplete or itself in a broken state.
- Calling additional beans/services "just to fetch info" can trigger a secondary failure and mask the root cause.

Boot documentation allows constructor injection specifically on `FailureAnalyzer` for `BeanFactory`/`Environment` when appropriate. When unnecessary, **store the data needed for analysis directly on the custom exception**, like `propertyName` in the example. That lets the analyzer work even when the context is unready for regular dependency injection.

For secret properties, store only the key name, status code, or sanitized description in the exception; never pass credential values into `FailureAnalysis`.

## 17. Extended practice exercises

### Exercise A — rewrite the analyzer class yourself

Do not copy the sample analyzer mechanically. Write `AbstractFailureAnalyzer<MissingWarehouseEndpointException>`, define a Description under 200 characters and an Action offering at least one fix via `application.properties` or CLI. Keep `return null` when information is insufficient.

### Exercise B — misnamed spring.factories

Try renaming the file to `spring-factories.properties` on a practice branch, run the app without config, and observe the custom Description/Action disappearing; then restore `META-INF/spring.factories`.

### Exercise C — wrong registry key

Try changing `org.springframework.boot.diagnostics.FailureAnalyzer` to `FailureAnalyzer`, rebuild, and run the failure case. Explain why the class still compiles yet the loader does not pick it up at the right extension point.

### Exercise D — wrong package/class spelling

Try altering uppercase/lowercase in the fully qualified class name in `spring.factories`, observe the class-loading/registration failure signs, and restore it. In production systems, CI/tests must catch registration typos before release.

### Exercise E — successful startup

Run `--warehouse.endpoint=https://example.invalid/api`, verify `WarehouseGateway` is created, the runner prints `READY`, and no custom `FailureAnalysis` triggers.

### Exercise F — returning null on unrelated failures

In a unit test, invoke the analyzer with `new IllegalArgumentException("different")`. Expect `null`. Explain why you should not return a generic action for unrelated exceptions.

### Exercise G — exception wrapped two levels deep

Use `new IllegalStateException("outer", new RuntimeException("middle", new MissingWarehouseEndpointException("warehouse.endpoint")))`. Verify the base class still finds the target cause type without requiring it to be the innermost or outermost throwable.

### Exercise H — using properties file instead of CLI

Add `warehouse.endpoint=https://example.invalid/api` to `application.properties` and run without `--warehouse.endpoint`. The analyzer has nothing to report. Then remove that line to restore the failure scenario.

### Exercise I — testing a configuration error with different domain semantics

Create `UnsupportedWarehouseProtocolException` with a `protocol` field, thrown when the endpoint starts with a disallowed scheme, and write a dedicated analyzer guiding users to `https`. Do not catch every `IllegalArgumentException` with an endpoint action.

### Exercise J — registering multiple analyzers

Add two specialized analyzers to `spring.factories` using properties comma syntax. Ensure they match distinct exceptions and test that neither hijacks the other's errors.

### Exercise K — packaging an analyzer library

Move the custom exception and analyzer into a library module (keeping `spring.factories`), and declare the module dependency from the app. Build the Boot JAR and verify the analysis appears on startup failure without copying registration into the app.

### Exercise L — keeping sensitive data secure

Assume the app lacks `warehouse.api-token`. The analyzer prints only the **key name** and instructions to supply it via secrets management, without logging any token value or dumping the `Environment`.

### Self-check questions

1. Is `FailureAnalyzer` used to recover an app after failure or to explain startup errors?
2. What does `AbstractFailureAnalyzer<T>` locate in the cause chain?
3. What method signature must you override in the subclass?
4. When should an analyzer return `null`?
5. Why can't `@Component` replace registration via `spring.factories`?
6. What are the exact resource path and full key name for registering an analyzer?
7. Is `AutoConfiguration.imports` used to register `FailureAnalyzer` in Spring Boot 3.3?
8. Which pieces of information does `FailureAnalysis` hold?
9. If your exception is wrapped in `BeanCreationException`, how does the analyzer still recognize it?
10. Which test verifies analyze logic works yet **does not prove** factory wiring works?
11. In the demo, why is `READY` absent when the endpoint is missing?
12. Why shouldn't an API token value be printed in Description/Action?

## 18. Common technical pitfalls when writing analyzers

| Symptom | Cause | Fix |
|---|---|---|
| IDE compiles cleanly yet startup shows no custom analysis | Missing `spring.factories` or wrong classpath | Check main resources file and `bootJar` contents |
| `@Component` analyzer does not run when refresh fails | Analyzer not loaded as a bootstrap extension | Register under `org.springframework.boot.diagnostics.FailureAnalyzer` |
| Method override fails to compile | Confused `analyze(Throwable)` with `analyze(Throwable,T)` overload | Use the exact protected two-parameter override |
| Analyzer is never called | Cause chain lacks exception type T | Use a domain-specific exception and preserve causes when wrapping |
| Analyzer runs yet prints no banner | Method returns `null` or reporter/logging differs | Test logic branches; inspect logging/reporter |
| `ClassNotFoundException` loading factories | Wrong package, class name, or missing runtime dependency | Sync fully qualified name and inspect artifact |
| Test creating analyzer via `new` passes yet app fails to load it | Registration was never tested | Add resource and startup integration tests |
| Analyzer misreports port/database failures | Generic type too broad, e.g., `RuntimeException` | Narrow exception type and conditions |
| Confusing Action | Only echoed `cause.getMessage()` | Name property, config location, concrete fix steps |
| `FailureAnalysis` leaks secrets | Printed config object or token value | Print only key names and safe metadata |
| Analyzer triggers additional errors | Called unready services/`BeanFactory` | Keep analyzer side-effect-free |
| Placed entry in `AutoConfiguration.imports` | Confused auto-config mechanism with factory registration | Use `META-INF/spring.factories` |
| Startup fails yet analyzer does not appear | Exception was swallowed or occurred post-startup | Verify exact timing and propagation path |
| Full-log tests fail on another machine | ANSI/timestamps/Gradle output vary | Assert stable content fragments |
| Two analyzers match one exception | Overlapping scopes, unexpected ordering | Pick specific exceptions and distinct conditions |
| Runs in a different JAR | Multi-module dependency/resource misconfigured | Inspect runtime classpath and packaged JAR |

## 19. Pre-production checklist

- [ ] Specific enough exception type carrying safe diagnostic data.
- [ ] Public class extending `AbstractFailureAnalyzer<CustomException>`.
- [ ] Exact override of `protected FailureAnalysis analyze(Throwable rootFailure, CustomException cause)`.
- [ ] Description clearly states the error and affected component.
- [ ] Action offers feasible remediation without secrets.
- [ ] Returns `null` when evidence is insufficient rather than misreporting.
- [ ] No service, DB, or network calls inside the analyzer.
- [ ] `META-INF/spring.factories` located in main runtime resources.
- [ ] Registration key is `org.springframework.boot.diagnostics.FailureAnalyzer`.
- [ ] Implementation name in the file is the exact fully qualified class name.
- [ ] Analyzer has a suitable constructor for factory-loader instantiation.
- [ ] Tested direct, wrapped, and unrelated exceptions.
- [ ] Executed at least one real startup failure to inspect the banner.
- [ ] Executed a successful startup to ensure no false positives.
- [ ] Verified the packaged `bootJar` retains `spring.factories`.
- [ ] Distinguished `FailureAnalyzer` from runtime `ControllerAdvice`/`ExceptionHandler`.
- [ ] Verified the error is thrown before Ready if fail-fast startup is desired.
- [ ] Reviewed security: no secrets in logs or actions.
- [ ] Documented fallback for unanalyzed failures and stack trace investigation.

## 20. Summary

**`AbstractFailureAnalyzer` does not fix startup failures; it makes startup failures understandable and actionable.** To add an analyzer in Spring Boot 3.3:

1. Define a **specific exception type**, ideally carrying safe error metadata.
2. Write a class `extends AbstractFailureAnalyzer<YourException>`.
3. Override `analyze(Throwable rootFailure, YourException cause)` to return `FailureAnalysis(description, action, cause)`, or `null` when evidence is insufficient.
4. Register the class under `org.springframework.boot.diagnostics.FailureAnalyzer` in `src/main/resources/META-INF/spring.factories`.
5. Trigger a real startup failure, verify Description/Action, then launch with valid config to confirm the success path.

This is a **bootstrap extension mechanism** independent of Spring MVC controllers and auto-configuration imports. The key lesson goes beyond syntax: **choose a narrow error scope, give accurate remediation steps, and avoid introducing new side effects while the application is failing**.

### Official references

- Spring Boot — *Create Your Own FailureAnalyzer*: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Boot 3.3 — `AbstractFailureAnalyzer` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html
- Spring Boot 3.3 — `FailureAnalyzer` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html
- Spring Boot 3.3 — `FailureAnalysis` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html
- Spring Boot 3.3 — `SpringApplication` and Startup Failure: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — `SpringFactoriesLoader` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html