# Using --debug and the Condition Evaluation Report to Troubleshoot Spring Boot Startup Failures

## 1. Lesson objectives

When a Spring Boot application fails to start, normal logs may only show a final error such as "required a bean that could not be found", "failed to bind properties", or "Application run failed". To discover **why Spring decided to create or skip a bean**, you need to know how to enable `--debug` and read the **Condition Evaluation Report**.

This lesson belongs to the **Startup Failures** group in Spring Boot Application Runtime. After studying it, you will be able to:

1. Enable debug properly with `java -jar`, Maven, Gradle, or `debug=true`.
2. Understand where `--debug` increases logging, and why it **does not set DEBUG for the entire application**.
3. Distinguish the different roles of **FailureAnalyzer**, stack traces, `ApplicationFailedEvent`, and the Condition Evaluation Report.
4. Read the `Positive matches`, `Negative matches`, `Unconditional classes`, and `Exclusions` sections of the report.
5. Interpret `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and web-application-type conditions.
6. Trace backward from a missing bean error to a condition that **did not match**, and distinguish it from constructor, network, or property-binding failures.
7. Run a Java 17+ demo with Spring Boot 3.5.16: **the exact same JAR**, failing startup once due to a missing property and succeeding once after setting the property properly.
8. Collect logs safely, avoid leaking sensitive information during production debugging, and avoid treating debug flags as a fix.

**Main idea:** `--debug` gives you extra **evidence** for investigation; it does not fix bean definitions, add dependencies, supply profiles, or guarantee the condition report covers every possible root cause.

## 2. Four signal sources on startup failure

Distinguish these information layers:

| Signal | Question it answers | Limitation |
| --- | --- | --- |
| **Exception/cause chain** | Which error directly caused startup to fail? | The final error may not explain why a bean was never registered |
| **FailureAnalyzer** | Can Spring Boot describe the error with a clear Description/Action? | Not every exception type has an analyzer |
| **Condition Evaluation Report** | Which conditional configs/beans were accepted or rejected and why? | Not a stack trace; does not describe every I/O or runtime failure |
| **Selective DEBUG logs** | How did Boot, container, or library steps proceed? | `--debug` does not enable DEBUG for every package |

High-level execution flow:

~~~text
SpringApplication.run(args)
   |
   +-- Environment / properties / active profiles
   +-- Load configuration and auto-configuration candidates
   |     |
   |     +-- Evaluate @Conditional... (OnClass, OnBean, OnProperty...)
   |     +-- Record ConditionOutcome in ConditionEvaluationReport
   |
   +-- Register BeanDefinitions / refresh ApplicationContext
   |     +-- Create beans and inject dependencies
   |     +-- On failure: cause chain, FailureAnalyzer, report (if available)
   |
   +-- ApplicationRunner / CommandLineRunner
   |     +-- On failure: startup can still fail here
   |
   +-- ApplicationReadyEvent
         +-- Startup succeeds
~~~

If the failure happens very early—such as failing to read an essential configuration file or broken logging configuration before the context is created—**the condition report may be incomplete or absent**. In that case inspect the first meaningful exception and configuration sources instead of trying to "force" a report.

On a failure path, Spring Boot publishes `ApplicationFailedEvent` if a startup exception occurs. That event integrates logging/monitoring; it is not an equivalent to `--debug`.

## 3. Enabling --debug properly

### 3.1. Running an executable JAR

The most common and explicit way:

~~~bash
java -jar target/my-app.jar --debug
~~~

For applications accepting command-line properties by default, `--debug` is equivalent to enabling `debug=true`. Arguments formatted as `--name=value` are processed by the Spring Boot Environment during normal `SpringApplication.run(args)`.

You can configure it via a configuration file:

~~~properties
debug=true
~~~

Or explicitly pass a value:

~~~bash
java -jar target/my-app.jar --debug=true
~~~

**Do not confuse**:
- `--debug` placed **after the JAR name** is an application argument.
- `-Ddebug=true` placed **before `-jar`** is a JVM system property. Spring Environment can read system properties, yet it is a separate configuration delivery mechanism; do not treat the two syntaxes as the same kind of command-line option.
- `-agentlib:jdwp=...` is the Java Debugger (JDWP) for setting breakpoints, **not** Spring Boot `--debug`.
- `debug=true` is a **logging** property; it does not put every bean into a test mode.

### 3.2. Maven Spring Boot Plugin

When running from Maven:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

The plugin forwards `--debug` to the application. Shell quoting rules differ across Bash, PowerShell, and cmd for multiple arguments; for a single argument, the command above is straightforward.

If you run the JAR directly, `java -jar ... --debug` avoids confusion between Maven wrapper logs/exit codes and the actual Java process.

### 3.3. Gradle bootRun

With the Gradle plugin supporting passing arguments:

~~~bash
./gradlew bootRun --args='--debug'
~~~

On Windows, use the appropriate Gradle wrapper (`gradlew.bat`) and terminal quoting syntax. If the build uses an older Gradle or custom setup, verify the flag actually reaches the application rather than only the build process.

### 3.4. When you cannot alter the command line

You can configure it in `application.properties` or any Boot-supported Environment source:

~~~properties
debug=true
~~~

To enable **only the condition report logger** instead of full debug mode, see Section 8. Reading config at startup depends on property source precedence; if a higher-priority source overrides `debug=false`, check the effective configuration source.

### 3.5. Should you enable --trace?

`--trace` or `trace=true` enables trace logging for a broader **set of core loggers** (Spring portfolio and Boot-configured components), not a "better error-fixing" version of `--debug`. It can produce massive logs. Start with **stack trace + FailureAnalyzer + --debug**; only turn on TRACE selectively when genuinely needed.

## 4. What does --debug do and what does it not do?

Per the Spring Boot 3.5 Logging Reference, enabling debug:
- Changes log levels for **selected core loggers** (such as Spring Boot, embedded container, and Hibernate under default config).
- Allows displaying the **Condition Evaluation Report** at DEBUG level when the listener/report is available.
- Provides better context when investigating auto-configuration selection.

However, it **does not**:
- Set `logging.level.root=DEBUG` for every logger.
- Enable breakpoints or remote debugging.
- Activate the `dev` or `test` profile.
- Automatically expose all Actuator endpoints.
- Automatically create a missing bean.
- Fix port conflicts, DB configuration, secrets, or network issues.
- Guarantee every exception has a dedicated `FailureAnalyzer`.
- Guarantee the condition report is complete when startup dies before condition evaluation.
- Make a running app failing at runtime print a "startup report" for every request.

**Comparing settings**:

~~~properties
# Enable Spring Boot debug mode for selected loggers.
debug=true

# Enable DEBUG specifically for the application package.
logging.level.com.example=DEBUG

# Enable DEBUG for the auto-configuration report logger.
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG

# Very noisy; not the default choice for startup diagnosis.
logging.level.root=DEBUG
~~~

These properties are independent. If you only want the condition report without raising background logs, configuring the logger on the third line is worth considering.

## 5. What is the Condition Evaluation Report?

`ConditionEvaluationReport` lives in `org.springframework.boot.autoconfigure.condition`. It records **evaluation outcomes of Conditions** (along with reasons why they matched or did not match) while Spring Boot processes configuration and auto-configuration.

An auto-configuration typically participates only when matching conditions hold:

~~~java
@ConditionalOnClass(SomeLibrary.class)
@ConditionalOnProperty(prefix = "feature", name = "enabled", havingValue = "true")
@ConditionalOnMissingBean(SomeService.class)
~~~

This is an **illustrative annotation snippet**, not a complete Java class; `SomeLibrary` and `SomeService` stand for hypothetical types. Meaning:

1. The matching library/type must be on the classpath.
2. Property `feature.enabled` must equal the required value.
3. No `SomeService` bean exists yet, so auto-configuration avoids overriding a user-defined bean.

Each condition leads to:
- **Match**: configuration is allowed to proceed.
- **No match**: configuration or bean definition is skipped by design.
- **Combined conditions**: if any required condition fails, that source can be skipped.

"Not matching" is **normal auto-configuration behavior**; a high count of negative matches **does not mean the app is broken**. They are useful only when tied to a **missing bean or feature**.

### Typical sections in the report

~~~text
CONDITIONS EVALUATION REPORT
============================

Positive matches:
-----------------
  ...
  Which configs/beans matched conditions, with reasons

Negative matches:
-----------------
  ...
  Which configs/beans did not match, with reasons

Exclusions:
-----------
  ...
  Auto-configuration classes explicitly excluded

Unconditional classes:
----------------------
  ...
  Auto-configuration candidates without conditions
~~~

This is a **layout sketch**, not logs copied from a live run. Headings, class names, ordering, and line counts vary across Spring Boot versions, classpaths, dependencies, profiles, and user-defined beans.

### Positive matches

Show conditions that passed, for example:
- Required class is on the classpath.
- App is a servlet web application.
- Property is enabled.
- No custom bean exists yet, so auto-configuration may provide the default bean.

**Important:** a positive match **does not prove the bean was instantiated successfully**. The condition can pass while the constructor or `@Bean` method still throws an exception during instantiation.

### Negative matches

Show conditions that did not pass, for example:
- Class is absent from the classpath.
- `@ConditionalOnProperty` did not find the property or saw a different value.
- `@ConditionalOnMissingBean` backed off because a matching bean already exists.
- `@ConditionalOnWebApplication` did not match because the app runs non-web.

**Important:** a negative match is **not automatically an error**. For instance, in a CLI app needing no servlet server, WebMVC auto-config not matching is expected.

### Exclusions

Show auto-configurations excluded via settings such as:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

This example fits a project **intentionally needing no DataSource**. If the app actually expected Spring to create a DataSource, this exclusion explains why the bean is missing. Do not copy exclusions into production just to make logs look "cleaner".

### Unconditional classes

Lists auto-configuration candidates that have no conditions to evaluate. Appearing in this list **does not imply** every bean inside instantiated cleanly. It mainly helps give an overview of configuration selection.

## 6. Understanding key conditions when tracing

| Condition | What does it check? | What to inspect when it does not match |
| --- | --- | --- |
| `@ConditionalOnClass` | Is the class on the classpath? | Missing dependency, version, starter, packaging type |
| `@ConditionalOnMissingClass` | Is the class absent from the classpath? | Class is present, so the "missing" branch is skipped |
| `@ConditionalOnBean` | Does a bean of type/name already exist? | Bean unregistered, in another context, wrong type |
| `@ConditionalOnMissingBean` | Is no bean of type/name present yet? | Custom bean exists causing default to back off |
| `@ConditionalOnProperty` | Is property present with right value? | Wrong key, different value, property source/profile unapplied |
| `@ConditionalOnBooleanProperty` | Boolean property value matches condition? | Wrong value or missing as required |
| `@ConditionalOnWebApplication` | Is context a web app of required type? | Missing web stack or `WebApplicationType.NONE` |
| `@ConditionalOnNotWebApplication` | Is context non-web? | Servlet/Reactive context is active |
| `@ConditionalOnResource` | Does classpath/URL resource exist? | Wrong path or resource packaging |
| `@ConditionalOnExpression` | Does SpEL expression evaluate true? | Expression value or bean initialization order |

These are Boot-provided conditions, not log levels. Some conditions sit on `@Configuration` classes, others on `@Bean` methods; **the source** in the report can be either the configuration class name or the method name.

### Reading property conditions accurately

Example:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true")
GreetingService greetingService() {
    return () -> "hello";
}
~~~

This is an **illustrative method snippet**, belonging in a configuration class with `GreetingService` declared. If property `demo.greeting.enabled` is:
- Missing -> no match when `matchIfMissing` defaults to false.
- Equal to `false` -> no match.
- Equal to `true` -> match.
- Any value other than `true` when `havingValue="true"` is set -> no match.

When `havingValue` is omitted, `@ConditionalOnProperty`'s default rule generally matches if the property exists and is not the string `"false"`; **do not equate** this with strict boolean parsing if configs might contain odd strings.

### Bean conditions and registration order

`@ConditionalOnBean` and `@ConditionalOnMissingBean` depend on bean definitions already processed **at the moment the condition is evaluated**. Hence Spring Boot recommends using them specifically in auto-configuration, which runs after user-defined configurations. Do not scatter those annotations arbitrarily assuming beans declared in any file are already known during evaluation.

### Class conditions and dependencies

If the report says a library is missing:
1. Check `pom.xml` or Gradle dependencies for the required starter.
2. Check dependency scope (`test`, `provided`, `runtime`, optional...).
3. Check dependency resolution and the dependency tree.
4. Check the final packaged artifact—especially JAR/WAR or images missing a module.
5. Check the actual runtime classpath, not just the IDE's classpath.

Do not blindly add whole starters just to force a condition to match; know what feature is actually required.

## 7. Runnable demo: missing bean caused by @ConditionalOnProperty

We build a Spring Boot 3.5.16, Java 17+ application that intentionally makes a critical bean **exist only when a property is enabled**, while an `ApplicationRunner` always requires that bean. Thus the exact same JAR exhibits two clear paths:

- Property absent -> bean not registered -> startup fails.
- With `--demo.greeting.enabled=true` -> bean registered -> runner succeeds.

This example purposefully focuses on configuration tracing, without simulating network or database errors.

### 7.1. Directory structure

~~~text
condition-debug-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/conditiondebug/
                └── ConditionDebugApplication.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>condition-debug-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` provides Spring Framework, auto-configuration, and appropriate logging; no database, servlet container, Actuator, or separate profile is needed to run the demo. Conditions depend on no external environment.

### 7.3. Complete Java file

Save as `src/main/java/com/example/conditiondebug/ConditionDebugApplication.java`:

~~~java
package com.example.conditiondebug;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConditionDebugApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConditionDebugApplication.class, args);
    }

    public interface GreetingService {
        String message();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.greeting",
            name = "enabled",
            havingValue = "true")
    GreetingService greetingService() {
        return () -> "hello";
    }

    @Bean
    ApplicationRunner greetingRunner(GreetingService service) {
        return args -> System.out.println(
                "RUNNER_GREETING=" + service.message());
    }
}
~~~

This is a **complete Java program** with one `main` and two bean factory methods. `@SpringBootApplication` is meta-annotated as a configuration class; `@Bean` methods here are processed normally by Spring.

Mechanics:
1. `greetingService()` is registered as a bean only when `demo.greeting.enabled=true`.
2. `greetingRunner(GreetingService service)` always requires a `GreetingService` bean when the container builds the runner bean.
3. If the property is absent, Spring skips registering `greetingService`; creating the runner lacks its dependency and context refresh fails.
4. If the property is enabled, the container creates the service, injects it cleanly, and the runner prints a line once startup reaches the runner stage.
5. Since this is a non-web CLI, after `main`/runner finish and no non-daemon threads remain, the JVM exits normally.

### 7.4. Compile

Inside the directory containing `pom.xml`:

~~~bash
mvn package
~~~

Packaging produces the JAR:

~~~text
target/condition-debug-demo-0.0.1-SNAPSHOT.jar
~~~

Run with `java -jar` to cleanly separate the Java process from the Maven wrapper. If Maven fails to resolve dependencies, that is a **build error**, not a startup failure that Spring Boot's `--debug` can diagnose.

### 7.5. Run 1 — without property, without debug

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar
~~~

**Outcome:** startup fails; `RUNNER_GREETING=hello` is absent. A `FailureAnalyzer` typically reports a missing bean of type `GreetingService`, advising how to declare or provide an appropriate bean. Actual logs include timestamps, threads, loggers, and full class names depending on version.

**Illustrative summary** (not logs copied verbatim from a specific run):

~~~text
APPLICATION FAILED TO START

Description:
Parameter 0 of method greetingRunner ... required a bean of type
'...ConditionDebugApplication$GreetingService' that could not be found.

Action:
Consider defining a bean of type '...GreetingService'.
~~~

Reading this message reveals **a bean is missing**, yet does not explain why `greetingService()` was not registered. This is where `--debug` helps.

### 7.6. Run 2 — still fails, now with --debug enabled

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --debug
~~~

The missing bean error still happens—**debug does not fix failures**. However, the log now includes the condition report; search for keywords:

~~~text
CONDITIONS EVALUATION REPORT
Negative matches:
ConditionDebugApplication#greetingService
OnPropertyCondition
demo.greeting.enabled
~~~

This is a **list of signals to look for**, not necessarily consecutive log lines. Actual messages may state property `enabled` under the prefix was not found or did not equal the required value, and method/class names may format differently.

Evidence-based reasoning:

~~~text
Symptom:
  No GreetingService bean
        |
        v
Factory method condition:
  @ConditionalOnProperty(demo.greeting.enabled=true)
        |
        v
Negative match:
  Property missing or not equal to true
        |
        v
Consequence:
  greetingService() creates no bean
        |
        v
greetingRunner(GreetingService) cannot inject dependency
        |
        v
ApplicationContext refresh fails
~~~

This connects **exception -> missing bean -> configuration source -> unmatched condition**. Never grab a random negative match for database/web/security and blame it for the failure; locate the source directly tied to the missing dependency.

**Config-dependent extra output:** Spring Boot may print a hint to re-run with `debug` when a crash report runs without debug enabled. Once enabled, the Condition Evaluation Report can be very long due to many unrelated auto-configurations; that is normal.

### 7.7. Run 3 — fix the root cause, startup succeeds

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=true
~~~

After the banner and startup logs, the **exact line printed by the demo code** is:

~~~text
RUNNER_GREETING=hello
~~~

Why?
- The property matches `havingValue="true"`.
- Spring creates the `GreetingService` bean.
- Spring injects this bean into `greetingRunner`.
- The runner executes and prints the message.

The JVM normally returns exit status **0** when no unexpected error occurs. Being a non-web CLI program, there is no server to stop manually.

### 7.8. Run 4 — succeeds while keeping debug on to compare

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar \
  --demo.greeting.enabled=true --debug
~~~

The command above illustrates Bash/zsh line continuation with `\`. In PowerShell/cmd, keep all arguments on a single line to avoid shell differences:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=true --debug
~~~

Now:
- `RUNNER_GREETING=hello` still prints.
- The report (when logged per configuration) lists factory method `greetingService` under **positive matches** because the property matched.
- **Other** negative matches still appear because the app does not use every auto-configuration feature.

Comparing **the exact same source, exact same JAR, differing only in one property** is a powerful way to isolate the cause of an unmatched condition.

### 7.9. Testing the false value

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false --debug
~~~

Here the property exists, yet its value does not satisfy `havingValue="true"`, so the bean is still skipped and startup still fails. The difference from an absent property can show up in the `ConditionOutcome` message.

**Be careful with boolean types:** `@ConditionalOnProperty` in this example compares against the expected value string; it does not verify a Java boolean property bound cleanly in every scenario. For complex boolean configs, understand both the annotation semantics and property sources.

## 8. Printing only the condition report without enabling broad debug logging

Spring Boot documentation notes that on startup failure you can enable the `debug` property **or** set DEBUG level on `ConditionEvaluationReportLoggingListener`.

Example in `application.properties` to enable just the report logger:

~~~properties
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

Or from the command line:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

This targets the report listener's logger. It is not equivalent to enabling DEBUG on business packages, cannot replace exception stack traces, and still cannot produce a report if failure occurs too early.

### Adjusting logging for a specific subsystem

If the report reveals a bean is present or missing yet you need to see which initialization step failed, enable logging for that specific subsystem:

~~~properties
# Log the application package under investigation.
logging.level.com.example.conditiondebug=DEBUG

# Example when diagnosing web MVC in an app with MVC.
logging.level.org.springframework.web=DEBUG

# Example when diagnosing Spring JDBC transactions.
logging.level.org.springframework.jdbc=DEBUG
~~~

These settings **do not necessarily affect the CLI demo** since it has no web/JDBC. Enable loggers only for features actually present in your application. Avoid `logging.level.root=TRACE` as a first step, as logs become overwhelming, bury the cause, and risk exposing data.

### Logging must be configured early enough

Spring Boot sets up logging during very early phases. If failure occurs before Environment/property sources finish loading, changes inside an unloaded config file may have no effect. In that case pass command-line properties or JVM/system environment variables, and read the earliest config-loading failure first.

## 9. Reading reports in order: symptom -> source -> condition -> remediation

An effective tracing workflow:

**Step 1 — Capture the root failure.** Record the exception type, uninjectable method/constructor/class, failing property binding, port, file/resource, or specific message.

**Step 2 — Read FailureAnalyzer.** If `APPLICATION FAILED TO START` appears with `Description` and `Action`, read it first: it often states the actionable cause clearer than a giant stack trace.

**Step 3 — Enable --debug.** Run **the exact same artifact** keeping profiles, classpath, and arguments identical apart from the debug flag so the diagnostic environment does not drift.

**Step 4 — Search the Condition Evaluation Report.** Search for the configuration class, method, or bean type related to Step 1's error. Do not read hundreds of lines sequentially once you already know the missing bean name.

**Step 5 — Read the exact condition outcome.** E.g., missing class, missing property, property value mismatch, existing bean causing default back-off, or non-matching web context type.

**Step 6 — Verify actual configuration.** Confirm dependencies, profiles, property source precedence, env vars, bean names, and the actual runtime classpath.

**Step 7 — Form a testable hypothesis.** E.g., "the GreetingService bean was skipped because demo.greeting.enabled is missing", rather than "Spring Boot auto-configuration is broken".

**Step 8 — Fix the exact cause and re-run.** If adding a property, verify the report flips from negative to positive. If adding a dependency, verify the live classpath. If changing config code, rebuild a new artifact.

**Step 9 — Disable unnecessary debug logging.** Retain business logs and metrics needed for monitoring without leaving broad debug enabled in production.

### Short diagnostic checklist example

~~~text
[ ] Exception type/cause chain identified
[ ] Any Description/Action from FailureAnalyzer?
[ ] Same JAR and same profile before/after --debug?
[ ] Did the Condition report appear?
[ ] Located the right configuration/method source
[ ] Is the negative match a bug or normal back-off?
[ ] Verified classpath, property values, bean definitions, web type
[ ] Tested fix in the same environment
[ ] Confirmed root exception is gone
[ ] Disabled verbose logger, no secrets stored
~~~

## 10. Analyzing common real-world scenarios

### 10.1. "Required a bean of type X that could not be found"

Possibilities:
- Bean X is guarded by `@ConditionalOnProperty`, and key/value did not match.
- Bean factory method X sits in a config skipped due to `@ConditionalOnClass`.
- The `@Configuration` class sits outside component scan packages or was not imported (a scanning/import issue, **unlikely to show in the condition report**).
- A profile is missing, e.g., `@Profile("prod")` inactive; that is a Spring Framework condition whose trace depends on phase and reporting mechanism.
- The bean is registered under a different type/name.
- A `@ConditionalOnMissingBean` caused the default bean to back off due to a custom bean that does not satisfy the expected injection.

Approach: find **which bean definition ought to create X**, then inspect its conditions, scope, or scan rather than randomly adding a second `@Bean`.

### 10.2. "Property expected true but was false or missing"

Check:
- `@ConditionalOnProperty(prefix=..., name=..., havingValue=...)`.
- Does the YAML/properties key match the exact namespace?
- Were profile-specific files loaded?
- Was the property overridden by env vars, CLI, or Config Data?
- Do property name and type follow relaxed binding rules?
- Was a Config Server/Vault/secret source actually loaded before condition evaluation?

In the demo, `--demo.greeting.enabled=true` solves it. In real systems, fix the property key rather than blindly setting `matchIfMissing=true`, which could activate a feature without required dependencies.

### 10.3. "@ConditionalOnClass did not find required class"

Read this as a classpath signal. Verify Maven/Gradle dependencies and the actual executable JAR packaging. Never try to fix it merely by declaring a bean with a name similar to the missing type.

For instance, if servlet auto-configuration does not match in a CLI app, that is normal. Investigate only if the app truly expects a servlet web server to be created.

### 10.4. "@ConditionalOnMissingBean found beans of type ..."

This is usually **intended back-off behavior**: Spring Boot skips creating the default because the app already provides a custom bean. If your custom bean works properly, **this is not an error**.

If the custom bean is misconfigured or fails to satisfy the expected type/qualifier, fix the custom bean. Do not try to force default auto-configuration to run alongside it.

### 10.5. "Not a servlet web application"

If the app is configured with `WebApplicationType.NONE` or lacks a web starter, servlet-specific auto-configurations rightly do not match. If you expect Tomcat/MVC, check `spring-boot-starter-web`, `SpringApplication` web type, dependencies, and whether reactive vs servlet starters are present.

### 10.6. "Port 8080 already in use"

This is typically a web server port-binding failure, not an unmatched condition. `FailureAnalyzer` can print Description/Action. Focus on the process occupying the port, `server.port`, management port, network bind address, and permissions. The condition report can confirm web server configuration was chosen, **but it will not free the port**.

### 10.7. "Failed to bind properties under ..."

Binding errors usually stem from type mismatches, malformed values, validation, property sources, or YAML syntax. The condition report may help if a property also gates whether an auto-configuration loads, yet **the binding error message and cause chain are the primary source**.

For example, a boolean property is expected while config supplies an invalid string. Do not conclude solely from a match/no-match when binding and conditions apply different semantics.

### 10.8. Bean matched yet constructor threw an error

A positive condition only states the bean/configuration **was eligible to be registered**, not that instantiation succeeded. If the constructor calls a DB and throws `ConnectException`, inspect the exception, network, credentials, and timeouts. The report only confirms the bean was registered; the error lies **inside initialization**.

### 10.9. Profiles and differing environments

Identical code can produce different beans due to:
- `spring.profiles.active`.
- `application-dev.yml` vs `application-prod.yml`.
- Container environment variables.
- `SPRING_APPLICATION_JSON`.
- Config server / secret manager.
- CLI overrides.
- Test property sources.
- Differences in dependency scope and classpath.

When comparing two reports, record **artifact version, profiles, effective property sources, and classpath**. Never assume a fix works solely because the dev report differs from prod.

### 10.10. Configuration broken from the very start

If startup fails before auto-configuration conditions are evaluated, the report may never appear. Examples:
- Invalid YAML syntax breaks the config parser.
- Required config import is unreachable.
- Broken logging configuration prevents completing bootstrap.
- JVM fails to load the main class.
- `ClassNotFound`/`NoClassDefFoundError` occurs very early.

In these cases, **find the chronologically earliest meaningful error** and check packaging, config sources, and the command line. `--debug` aids observation once Boot progresses far enough, not as a substitute for all checks.

## 11. ConditionEvaluationReport API for structured analysis

Beyond logging, Spring Boot 3.5 exposes `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport`. Javadoc APIs include:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

var bySource = report.getConditionAndOutcomesBySource();
var exclusions = report.getExclusions();
var unconditional = report.getUnconditionalClasses();
~~~

This is an **illustrative snippet inside code holding a valid `ConfigurableApplicationContext context`**, not a standalone Java file. Import `ConditionEvaluationReport` from Spring Boot and ensure the context is still usable. `getConditionAndOutcomesBySource()` returns a map from source name to condition outcomes; `getExclusions()` and `getUnconditionalClasses()` return the respective sections.

Understand the limits:
- If startup failed before `main` received a context, you cannot simply call `context.getBeanFactory()` from `main` after `SpringApplication.run`.
- The report contains recorded conditions, not a comprehensive model of every bean and exception.
- Never dump the raw map from business code or a production endpoint for debugging, because the report reveals application structure.
- For startup failure reports, **using Boot's built-in listener/logging** is usually safer and less intrusive.

### ConditionEvaluationReportLoggingListener

`org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener` is an `ApplicationContextInitializer` that writes the report to logs. In Spring Boot 3.5, it logs at DEBUG by default; on crashes it may print a hint to enable debug.

Spring Boot provides the factory:

~~~java
ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
~~~

This is an **illustrative snippet** requiring imports; when used in appropriate contexts like `ApplicationContextRunner` tests, it lets you pick the report log level. It is not something to register indiscriminately in every app, since Boot already wires report logging for normal startup.

### Testing auto-configuration with ApplicationContextRunner

In a project with `spring-boot-starter-test` at test scope, you can test auto-configuration with `ApplicationContextRunner`:

~~~java
// Conceptual example in a JUnit test with spring-boot-starter-test dependency.
new ApplicationContextRunner()
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
    .withUserConfiguration(MyAutoConfiguration.class)
    .run(context -> {
        // Assert bean presence/absence per test property.
    });
~~~

This snippet **deliberately illustrates only the API**, not a standalone runnable test: it needs `MyAutoConfiguration` and imports. Condition tests verify behavior with/without beans, properties, and simulated classpaths far better than reading long logs.

### Do not use log reports as a business API

Condition reports exist for **diagnostics and testing**, not as runtime data for business decisions. If your app needs to know whether a feature is enabled, use configuration properties, dependency injection, or explicit feature-flag contracts instead of parsing report text.

## 12. Actuator /actuator/conditions: observing a running app

If the application started **successfully** and has Spring Boot Actuator, the `conditions` endpoint provides structured condition evaluation data. It complements debugging by answering "why was an auto-configuration chosen or skipped" in a **live application**.

In a web app with `spring-boot-starter-actuator` properly secured, for instance:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

You can then request:

~~~text
GET /actuator/conditions
~~~

Typical responses contain groups such as `positiveMatches`, `negativeMatches`, and `unconditionalClasses` structured per context. Exact field names and structure vary by Actuator version.

**Pay close attention:**
- Section 7's demo has only `spring-boot-starter`, **no Actuator and no web server**, so `/actuator/conditions` does not exist there. To try the endpoint, build a web app with Actuator.
- An app that **failed to start** has no HTTP endpoint to query. Never expect `/actuator/conditions` on a crashed instance.
- The conditions endpoint is not exposed over HTTP simply because Actuator is present; configure exposure and authorization properly.
- The endpoint can reveal class names, bean details, and application structure. **Never expose it publicly** on the Internet; prefer a dedicated management port, authentication/authorization, and network policies.
- Never set `management.endpoints.web.exposure.include=*` in production just to read one report.

When you only need to debug a startup failure, **command-line --debug** is simpler because it does not depend on the HTTP server starting.

## 13. Combining reports with logs and traces safely

When capturing an incident, keep at minimum:

~~~text
Incident ID:
Application/artifact version:
Spring Boot version:
JDK version:
Environment / active profiles:
Command line flags (secrets redacted):
Start and end timestamps:
Exception type + causal chain:
FailureAnalyzer Description/Action:
Relevant Negative/Positive matches:
Source configuration/bean:
Hypothesis:
Fix applied:
Outcome after rerun:
~~~

This is an incident worksheet template, not output printed automatically by Spring.

### Never share raw logs containing secrets

DEBUG logs and stack traces can contain:
- Environment property names/values in certain messages.
- Internal hostnames, internal URLs, bean types, classpaths, file paths.
- Usernames, connection strings, or headers if code/libraries log carelessly.
- Security and topology details inside diagnostics.

Redact passwords, tokens, API keys, secret paths, and customer data before shipping logs to external systems. Do not assume every condition report carries passwords, yet never treat debug logs as harmless public data either.

### Running debug in production

Prefer:
1. Reproduce in staging or an isolated environment with an equivalent artifact and configuration.
2. Enable **targeted, time-bounded** logging if production debugging is necessary.
3. Restrict log storage locations, access control, and retention.
4. Avoid excessive logging that spikes disk, CPU, I/O, or buries the root cause.
5. Turn off DEBUG/TRACE once sufficient evidence is collected.

Never alter `spring.main.lazy-initialization`, delete beans, add starters, or tweak conditions just to "get the app up" before understanding the impact of that change.

## 14. Distinguishing the condition report from other reports

| Tool/information | When available | Used for |
| --- | --- | --- |
| Condition Evaluation Report | When conditions were evaluated and report logging is enabled | Why conditional configs/beans matched or did not match |
| FailureAnalyzer output | When Boot has a matching analyzer for the exception | Specific root cause and corrective action |
| Java exception stack trace | When exceptions/logs are printed | Error origin and cause chain |
| `ApplicationFailedEvent` | When startup enters the corresponding failure path | Integrating listeners/monitoring |
| `/actuator/conditions` | App is running with Actuator endpoint exposed | Observing conditions on a live app |
| `ApplicationContextRunner` | In auto-configuration tests | Testing match/back-off by property/classpath |
| `ConditionEvaluationReport` API | When bean factory/report is accessible | Structured analysis, internal tooling |
| Remote JVM debugger (JDWP) | When debugger attach is configured | Inspecting call stacks/variables via breakpoints |

**Dangerous misconception:** a report stating "DataSourceAutoConfiguration did not match" is not necessarily why an app failed on an unrelated web controller. Use the report only when there is a causal link to the symptom, exception, and bean under investigation.

## 15. Sample tracing walkthroughs by scenario

### Scenario A — missing bean due to property (demo)

~~~text
Symptom:
  GreetingService bean missing
Report:
  ConditionDebugApplication#greetingService -> Negative match
  demo.greeting.enabled is not true
Remediation:
  --demo.greeting.enabled=true
Validation:
  RUNNER_GREETING=hello
~~~

In the demo, only one property changed, giving high confidence in the hypothesis. In real apps, also check remaining conditions, classpath, and bean scopes.

### Scenario B — excluded auto-configuration

~~~text
Symptom:
  No default DataSource
Report:
  Exclusions contains DataSourceAutoConfiguration
Remediation:
  Check why spring.autoconfigure.exclude is present
  Remove exclusion only if the app truly needs auto-configured DataSource
Validation:
  DataSource bean appears and connects per configuration
~~~

Do not add `DataSourceAutoConfiguration` to an app needing no DB merely because Exclusions lists it. Exclusions can be intentional and completely valid.

### Scenario C — custom bean causes auto-config back-off

~~~text
Symptom:
  Expected Spring Boot to create a default bean
Report:
  @ConditionalOnMissingBean did not match due to existing custom bean
Remediation:
  Inspect the custom bean and injection/qualifier requirements
Validation:
  Required bean has the right type and behavior
~~~

Here, not matching is part of respecting user configuration priority, not a Boot bug.

### Scenario D — missing classpath entry

~~~text
Symptom:
  Jackson/Servlet/JDBC-related bean does not appear
Report:
  @ConditionalOnClass did not find required type
Remediation:
  Inspect dependencies, scope, packaging, and actual runtime artifact
Validation:
  Type is on classpath; condition matches if remaining conditions also hold
~~~

Adding the right dependency does not guarantee completion: another `@ConditionalOnProperty` or `@ConditionalOnWebApplication` may also gate it.

### Scenario E — bean selected yet fails during creation

~~~text
Symptom:
  BeanCreationException -> SQLException/ConnectException
Report:
  Configuration may show Positive match
Remediation:
  Inspect cause chain, credentials, network, DB URL, timeouts
Validation:
  Bean is created and business health check passes
~~~

A positive outcome does not prove the system connected successfully; it reflects only the **condition evaluation round**.

### Scenario F — no report even with --debug

~~~text
Symptom:
  App stops at bootstrap/logging/config import
Report:
  CONDITIONS EVALUATION REPORT not seen
Remediation:
  Read the earliest exception; check config/packaging/JVM args
Validation:
  App passes bootstrap phase before continuing condition checks
~~~

Do not respond by blindly turning on dozens of loggers when the root error is an unparseable config file.

## 16. Common mistakes when using --debug

| Mistake | Why is it wrong? | Right approach |
| --- | --- | --- |
| "--debug enables DEBUG for all loggers" | Boot enables only selected core loggers | Use `logging.level.<package>=DEBUG` when needed |
| Using JDWP thinking it is --debug | JDWP is the JVM debugger | Distinguish log diagnostics from breakpoints |
| Treating every Negative match as an error | Auto-config intentionally skips unused features | Investigate only sources linked to the symptom |
| Treating Positive match as bean initialized | Constructors/@Bean methods can still fail | Cross-check the stack trace |
| Running debug with a different profile/classpath than the failure | Changes multiple variables at once, muddying conclusions | Keep artifact and config identical, add only debug |
| Ignoring FailureAnalyzer | Misses concrete Description/Action | Read analyzer output before the report |
| Reading only the last exception line | Misses root cause and nested causes | Follow the cause chain and config sources |
| Copying exclusions to "reduce errors" | Can accidentally exclude mandatory beans | Exclude only when you understand the feature |
| Adding `matchIfMissing=true` to force a bean | Can activate features in wrong environments | Fix the property key/value properly |
| Exposing report over public HTTP | Leaks application structure | Secure Actuator conditions |
| Calling /actuator/conditions when app crashed | Endpoint is no longer serving | Use startup logs and --debug |
| Confusing Maven wrapper with the JAR | Logs/exit status may go through wrapper layer | Run `java -jar` directly when needed |
| Leaving root TRACE on indefinitely | Huge logs, resource overhead, or data leaks | Log selectively and time-bound |
| Thinking debug fixes DB/port errors | Debug only adds diagnostic output | Fix the real root cause |
| Skipping verification after fixing | Negative match might shift to a different error | Rerun and verify startup/behavior |
| Skipping tests when upgrading Boot versions | Conditions/auto-config evolve across versions | Compare behavior and reports on target version |

## 17. Self-check questions

**Q1.** Is `java -jar app.jar --debug` equivalent to `logging.level.root=DEBUG`?

**Answer:** No. Boot's debug flag raises logging for a set of core loggers and prints the condition report without setting DEBUG for every logger.

**Q2.** What does the Condition Evaluation Report record?

**Answer:** Evaluation outcomes of `Condition`s processed by Spring Boot, grouped by configuration class/method source, along with reasons for matching or not matching.

**Q3.** If there are 200 negative matches, is the application definitely broken?

**Answer:** No. Many auto-configurations are intentionally skipped due to classpath, application type, or property mismatches.

**Q4.** The report says `@ConditionalOnMissingBean` did not match because a custom bean exists. Is this an error?

**Answer:** Usually it is intended back-off. It is a problem only if the custom bean fails to provide the behavior or type the application needs.

**Q5.** Why did Section 7's demo lack `GreetingService`?

**Answer:** `@ConditionalOnProperty` on the bean method requires `demo.greeting.enabled=true`. Without the property, the method is not registered as a bean; the runner bean requests `GreetingService`, causing injection to fail.

**Q6.** Does adding `--debug` make the demo start successfully?

**Answer:** No. It adds the report for diagnosis; to succeed, set the required property or adjust dependency design.

**Q7.** If the report shows a positive match for a bean, is `BeanCreationException` impossible?

**Answer:** False. Matching conditions only allow registration/evaluation of configuration; constructors or factory methods can still throw exceptions.

**Q8.** When the app crashes, can you call `/actuator/conditions` to inspect the report?

**Answer:** Not if the HTTP endpoint is no longer serving. Actuator conditions work on a running app with appropriate dependencies, exposure, and authorization.

**Q9.** How do you enable only the report logger?

**Answer:** Use `logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG` or enable `debug=true` for default debug mode.

**Q10.** Why doesn't the report appear if YAML breaks very early?

**Answer:** The app can terminate before reaching condition evaluation and populating the report; prioritize the first parser/config error.

**Q11.** Is `ApplicationStartedEvent` published when context refresh fails?

**Answer:** Not in the normal startup path, because Started requires context refresh to succeed. On the failure path, `ApplicationFailedEvent` fires when `SpringApplication` handles the exception.

**Q12.** Should you paste raw production DEBUG logs into a public issue?

**Answer:** No. Redact secrets, internal hosts, and sensitive data, and restrict recipients and retention.

**Q13.** Do an absent property and a property set to `false` always produce the same `ConditionOutcome` message?

**Answer:** No. Both fail a `havingValue=true` condition, yet evaluation messages can state different reasons.

**Q14.** When the report says a class is not on the classpath, what is the most important verification step?

**Answer:** Inspect dependencies and the **actual runtime artifact/classpath**, not just local build declarations.

**Q15.** Does the condition report replace stack traces or FailureAnalyzer?

**Answer:** No. It adds visibility at the conditional-configuration selection layer, while failure analyzers and exception chains describe broader startup failures.

## 18. Practice exercises

### Exercise A — identify a negative match

Run the demo **without the property** using `--debug`. Find source `ConditionDebugApplication#greetingService` or its equivalent name in the report. Record the exact `ConditionOutcome` for `demo.greeting.enabled`. Explain why the runner lacked its dependency.

### Exercise B — absent property vs false property

Run sequentially:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --debug
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false --debug
~~~

Compare the negative match messages. In both cases the bean is absent; note the difference between **missing property** and **non-matching value** if reported.

### Exercise C — positive match and runner output

Run with `--demo.greeting.enabled=true --debug`. Verify:
- The app starts successfully.
- Marker `RUNNER_GREETING=hello` appears.
- The relevant source moves to positive matches (when the report is printed).
- Other negative matches remain normally.

### Exercise D — change the havingValue specification

Try changing `havingValue="true"` to `havingValue="yes"` and rebuild. Predict behavior with `--demo.greeting.enabled=true` and `--demo.greeting.enabled=yes`; explain why this condition checks against the specified value.

### Exercise E — enable only the report logger

Without `--debug`, run the missing-bean app with:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

Compare log volume against `--debug` and confirm whether the report appears.

### Exercise F — classpath condition

Add a configuration class with `@ConditionalOnClass` for an optional type, then run with that type present vs absent on the classpath. Observe source and outcome; avoid referencing a non-existent type directly in method signatures that must load eagerly.

### Exercise G — bean back-off

Create an auto-configuration with `@ConditionalOnMissingBean` alongside a custom bean of the same type. Compare reports with and without the custom bean; explain why the negative match can be right by design.

### Exercise H — misspelled configuration key

Change `demo.greeting.enabled` to a misspelled key. Run debug and inspect the report. Then fix the property and rerun. Present the root cause along the chain "missing bean -> condition -> property".

### Exercise I — port conflict vs condition mismatch

Create a Spring MVC web app and intentionally run two processes on the same port. Compare `FailureAnalyzer` with the Condition Evaluation Report when port binding fails. Do not blame a random negative match for the port error.

### Exercise J — testing startup conditions

With `spring-boot-starter-test`, use `ApplicationContextRunner` to verify:
- Property false -> conditional bean absent.
- Property true -> conditional bean present.
- Custom bean exists -> default `@ConditionalOnMissingBean` bean backs off.

Assert bean presence and outcomes rather than **solely asserting log text**, because log formats can vary across versions.

## 19. Official documentation

- [Spring Boot 3.5 — SpringApplication: Startup Failure](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `FailureAnalyzer`, startup failure, enabling `debug` or the condition report logger.
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html): `--debug`, `debug=true`, `--trace`, selected loggers, and logging level configuration.
- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): `OnClass`, `OnBean`, `OnMissingBean`, `OnProperty` conditions and `ApplicationContextRunner`.
- [Spring Boot 3.5.16 — ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): condition outcomes by source, exclusions, unconditional classes.
- [Spring Boot 3.5.16 — ConditionEvaluationReportLoggingListener Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): DEBUG logger, `forLogLevel(LogLevel)`.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): `conditions` endpoint and exposure controls.
- [Spring Boot 3.5.16 — ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `prefix`, `name`, `havingValue`, `matchIfMissing`.

### Final takeaways

1. `--debug` supplies **tracing evidence**, without fixing startup errors.
2. It enables DEBUG only for **a selected set of core loggers**, not all loggers.
3. **Condition Evaluation Report** answers "which conditions matched/did not match and why", not a replacement for stack traces.
4. `Negative matches` are normal; only sources linked to the missing bean/feature are direct clues.
5. `Positive matches` do not guarantee a bean initialized cleanly.
6. Always combine the report with **FailureAnalyzer, exception cause chains, property sources, active profiles, and the classpath**.
7. If startup fails too early, the report may be absent; prioritize the earliest bootstrap error.
8. `/actuator/conditions` is for running apps and must be secured; it does not replace `--debug` on a crashed app.
9. The demo shows that simply changing `demo.greeting.enabled` from absent/false to true registers the conditional bean and lets the runner succeed.
10. Collect logs safely, redact secrets, disable debug after investigation, and verify fixes by rerunning the exact artifact and environment.
