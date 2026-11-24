# Correlating Diagnostic Endpoints with Logs, Profiles, and Environment Configuration

## 1. Why combine multiple sources of evidence?

An application works properly on a personal machine yet uses a different timeout when deployed. A configuration file says a feature is enabled, yet the bean still does not appear. A missing DEBUG line in logs makes an operator suspect a code branch never ran.

All three situations require correlation, because each tool answers only part of the question:

| Observation source | Primary question |
| --- | --- |
| Startup logs and application logs | What happened during which run? |
| Active profiles | Which environment-specific configuration slices were selected? |
| `env` endpoint | From which configuration source is the value currently being resolved? |
| `configprops` endpoint | What data did the `@ConfigurationProperties` object receive? |
| `conditions` endpoint | Which conditions were recorded as matched or not matched? |
| `beans` endpoint | Which bean definitions exist in the context under inspection? |
| `loggers` endpoint | What configured level and effective level does a logger have? |

The destination is not collecting every JSON document or turning on every log category. The destination is explaining a behavior using evidence from the same application and the same run.

For example, saying "the timeout is 9 seconds" is insufficient. A more useful statement is:

> On the run under review, the `sandbox` profile is active; the timeout property comes from an environment variable; the configuration object received 9 seconds; the test bean was created with that value. The profile file specifies 2 seconds, but it is not the winning source.

Actuator endpoints provide complementary perspectives, not interchangeable duplicates of one another. [Spring Boot 3.3 — built-in endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 2. The mental model to hold before diagnosing

You can picture the configuration loading pipeline as follows:

~~~text
Configuration sources and startup arguments
        ↓
Active profiles + selected configuration documents
        ↓
Environment resolves properties by precedence
        ↓
Bind to Java types and evaluate conditions at appropriate stages
        ↓
Register / instantiate beans
        ↓
Application code uses configuration and emits behavior and logs
~~~

This is a model for asking questions, not a claim that every binding step and every condition happens in a single linear order inside Spring.

Three concepts are frequently conflated:

- **Declared value:** content inside one source, e.g., `application-sandbox.properties` specifies `2s`.
- **Effective value:** the result `Environment` resolves after considering sources.
- **Bound value:** data converted into Java types on a configuration object, e.g., a `Duration` corresponding to 9,000 milliseconds.

There is one further layer: **the value code actually uses**. A component may hold a copy created at startup, use a constant, or read a different object. Seeing a value in `env` does not prove every component used that value.

Therefore, move from a specific question to the appropriate layer of evidence; advance to the next layer only when something remains unexplained.

## 3. Lock down the right run before comparing

Before diving into endpoints, record:

1. The application, version, and instance or pod under review.
2. Process start time, log capture time, and endpoint query time.
3. Actual management address and port; does the endpoint pass through a load balancer?
4. Expected profiles and actually active profiles.
5. The specific property or bean to inspect.

If logs come from pod A while the HTTP request is routed to pod B, the two pieces of evidence can differ without any configuration resolution bug. If a restart happened, logs from before the restart do not describe the new state.

When comparing multiple instances, prefer instance identifiers already available in the platform and logs; there is no need to expose extra internal data just to tell processes apart.

An endpoint report is a snapshot at read time, whereas logs describe events at the time they occurred. A startup configuration log does not update itself if the system later applies a configuration refresh mechanism.

## 4. Preparing read access and understanding masked values

In a Spring Boot 3.3.x web application with the Actuator dependency, expose only the endpoints needed for authorized verification. The lab example below runs on loopback and keeps value masking enabled:

~~~properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,env,configprops,conditions,beans,loggers
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

`enabled` and HTTP exposure are separate controls. If an endpoint was disabled or listed in `exposure.exclude`, adding its name to `exposure.include` alone is not enough. When Spring Security is present, authentication and authorization rules must also be satisfied.

`env` and `configprops` mask values as `******` by default in Spring Boot 3.3. Asterisks do not mean a property is missing, empty, or failed to bind. Source and declaration location information can still be useful for tracing origin.

This lab does not require setting `show-values=always`. The verification lines in the program print only fields known to be non-sensitive dummy data. Never apply full-configuration printing to passwords, tokens, URLs containing credentials, or personal data.

[Spring Boot 3.3 — sanitizing values in endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

## 5. Two rules on precedence and profiles

### 5.1. A loaded file is not necessarily the winning source

Among the commonly used sources of a typical run, you can start checking along this relationship:

~~~text
Command-line arguments
    can override Java system properties (-D...)
        can override process environment variables
            can override data from application.properties / YAML
~~~

This is a slice for investigation, not Spring Boot's complete `PropertySource` list. JSON configuration, test environments, containers, and other sources may participate; inspect the actual reported sources instead of deducing from a simplified diagram.

At the same loading location, a profile-specific file can override a general file. However, activating a profile does not elevate a profile file above all environment variables or command-line arguments.

Example of setting a system property and an application argument:

~~~shell
java -Ddemo.client.timeout=5s -jar app.jar --demo.client.timeout=700ms
~~~

`-D...` precedes `-jar`; `--demo.client.timeout=...` is an application argument. In this default Spring Boot execution, the application argument wins. Do not place `-D...` after the JAR name and assume it acts as a system property.

The environment variable name corresponding to `demo.client.timeout` is `DEMO_CLIENT_TIMEOUT`. For names containing hyphens, follow Spring Boot's mapping rules rather than mechanically replacing every character with underscores.

[Spring Boot 3.3 — configuration sources and precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 5.2. A profile is a configuration selector, not an inferred environment name

Cross-check active profiles from startup logs and the `activeProfiles` list on the `env` endpoint. A variable in a deployment tool reading "production" does not by itself prove Spring activated a profile named `production`.

If no profile is explicitly activated, `activeProfiles` can be an empty array while the default profile is still used. Additionally, profile includes or groups can make the active profile set larger than the single name passed in.

`@Profile("sandbox")` restricts Java configuration by profile. `application-sandbox.properties` is a property document selected by profile. The two mechanisms are related but not identical: having matching properties does not automatically cause a Java class with a different profile to be loaded.

Activation keys such as `spring.profiles.active` must not be placed inside profile-specific configuration files themselves. Choose profiles from valid sources and verify the result after startup. [Spring Boot 3.3 — profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

## 6. Hands-on project: one property flowing through multiple sources

Use JDK 21 and Gradle 8.5. The example pins Spring Boot 3.3.0 to reproduce behavior within the 3.3 line; this is not an instruction to change the version of a running production system.

File structure to create:

~~~text
actuator-correlation-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/DiagnosticCorrelationApplication.java
    └── resources/
        ├── application.properties
        └── application-sandbox.properties
~~~

### 6.1. Build and two property sources

`settings.gradle`:

~~~groovy
rootProject.name = 'actuator-correlation-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,env,configprops,conditions,beans,loggers
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
logging.level.demo=INFO
demo.client.enabled=false
demo.client.timeout=1s
~~~

`src/main/resources/application-sandbox.properties`:

~~~properties
demo.client.enabled=true
demo.client.timeout=2s
~~~

In the shared file, the feature is disabled and timeout is 1 second. The sandbox file switches to enabling the feature and 2 seconds. There is no configuration to send data to external services.

### 6.2. Complete program

`src/main/java/demo/DiagnosticCorrelationApplication.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.Arrays;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
@EnableConfigurationProperties(DiagnosticCorrelationApplication.ClientProperties.class)
@Import(DiagnosticCorrelationApplication.SandboxClientConfiguration.class)
public class DiagnosticCorrelationApplication {

    private static final Logger LOG =
        LoggerFactory.getLogger(DiagnosticCorrelationApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticCorrelationApplication.class, args);
    }

    @Bean
    ApplicationRunner diagnosticSnapshot(
            Environment environment,
            ClientProperties properties,
            ObjectProvider<DemoClient> clients) {
        return args -> {
            String status = clients.getIfAvailable() == null ? "absent" : "present";
            System.out.printf(
                "DIAG profiles=%s enabled=%s timeoutMs=%d client=%s%n",
                Arrays.toString(environment.getActiveProfiles()),
                properties.enabled(),
                properties.timeout().toMillis(),
                status
            );
            LOG.debug("DIAG_DETAIL snapshotCompleted=true");
        };
    }

    @ConfigurationProperties(prefix = "demo.client")
    public record ClientProperties(boolean enabled, Duration timeout) {
    }

    public record DemoClient(Duration timeout) {
    }

    @Configuration(proxyBeanMethods = false)
    @Profile("sandbox")
    public static class SandboxClientConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.client", name = "enabled", havingValue = "true"
        )
        DemoClient demoClient(ClientProperties properties) {
            return new DemoClient(properties.timeout());
        }
    }
}
~~~

Role of each part in the code:

- `ClientProperties` holds typed configuration data; `Duration` distinguishes a time value from a unitless number.
- `SandboxClientConfiguration` is loaded only when the `sandbox` profile is active.
- `demoClient` additionally requires `demo.client.enabled=true`.
- `DemoClient` is a mock object storing the timeout, making no network calls.
- The runner prints one stdout line with profiles, enable flag, bound timeout, and client presence.
- A separate DEBUG message lets you check the effect of log levels.

The `DIAG` line uses `System.out`, so it is not filtered by logger level. The `DIAG_DETAIL` line goes through SLF4J and depends on logging configuration. The two channels are intentionally separated to provide a verification marker even when DEBUG is hidden.

The example uses `@SpringBootConfiguration` + `@EnableAutoConfiguration` and imports the specific Java configuration with `@Import`. There is no implicit component scanning to guess about.

### 6.3. Packaging and terminal preparation

In the project directory, generate the wrapper with Gradle 8.5 if not present:

~~~shell
gradle wrapper --gradle-version 8.5
~~~

Then in PowerShell:

~~~powershell
java -version
.\gradlew.bat bootJar
~~~

The `java` command used to run the JAR must point to JDK 21. The first build needs access to the plugin repository and Maven Central. Spring classes require project dependencies, so do not compile this Java file with a classpath-less `javac` command.

In the dedicated test terminal, clear any timeout variable from prior experiments:

~~~powershell
Remove-Item -LiteralPath Env:DEMO_CLIENT_TIMEOUT -ErrorAction SilentlyContinue
~~~

An empty environment variable and a nonexistent variable are two different states; do not set `$env:DEMO_CLIENT_TIMEOUT=""` to simulate the variable not being declared at all.

Each experiment below requires stopping the previous process with Ctrl+C. Call endpoints from a second terminal after the application finishes starting.

## 7. Collecting a compact evidence bundle for each run

The examples use port 8080 and the default management path. If a system uses a different management port, base path, or proxy, use the actual address of the identified instance.

### 7.1. Reading a single property from env

~~~powershell
$base = 'http://127.0.0.1:8080/actuator'
$timeoutReport = Invoke-RestMethod "$base/env/demo.client.timeout"

$timeoutReport.activeProfiles
$timeoutReport.defaultProfiles
$timeoutReport.property | Format-List

$timeoutReport.propertySources |
    Where-Object { $null -ne $_.property } |
    Select-Object name, @{
        Name = 'origin'
        Expression = { $_.property.origin }
    }
~~~

In a **single-property** response:

- `property.source` is the source of the resolved result.
- `property.value` may be masked.
- `propertySources` lists relevant sources in precedence order; read `origin` as well if present.
- Do not confuse the `propertySources[].property` structure of this response with `propertySources[].properties` when reading all of `/env`.

Not every source has a file and line number. Environment variables or command-line arguments may be described by source name or variable name. [Spring Boot 3.3 — querying a single property](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

### 7.2. Inspecting the bound configuration object

~~~powershell
$boundReport = Invoke-RestMethod "$base/configprops/demo.client"
$boundReport.contexts.PSObject.Properties.Name

$boundReport.contexts.application.beans.PSObject.Properties |
    Where-Object { $_.Value.prefix -eq 'demo.client' } |
    ForEach-Object {
        $_.Name
        $_.Value | ConvertTo-Json -Depth 10
    }
~~~

Subsequent commands use the `application` context of the lab project. For applications with a different ID or multiple contexts, select the exact ID just listed rather than hardcoding that name.

Read `prefix`, `properties`, and `inputs`. `inputs` can preserve the origin of data used during binding; `properties` reflects the Java object's property form. Bean names often contain both prefix and type name, so filter by `prefix` instead of hardcoding the full bean name.

With the lesson's value-masking setting, you may see:

~~~json
{
  "prefix": "demo.client",
  "properties": {
    "enabled": "******",
    "timeout": "******"
  },
  "inputs": {
    "timeout": {
      "value": "******",
      "origin": "System Environment Property \"DEMO_CLIENT_TIMEOUT\""
    }
  }
}
~~~

The JSON snippet omits outer fields; this origin corresponds to the environment-variable scenario below. Masked values do not prevent identifying which data source participated in binding. The program's `DIAG` line provides a reference marker for non-sensitive fields in the example.

`configprops` is not a report of every field, every `@Value`, or every constant in code. [Spring Boot 3.3 — configprops by prefix](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

### 7.3. Cross-checking bean definitions and conditions

~~~powershell
$beanReport = Invoke-RestMethod "$base/beans"
$beanReport.contexts.application.beans.demoClient

$conditionReport = Invoke-RestMethod "$base/conditions"
foreach ($side in @('positiveMatches', 'negativeMatches')) {
    $conditionReport.contexts.application.$side.PSObject.Properties |
        Where-Object { $_.Name -like '*SandboxClientConfiguration*' } |
        ForEach-Object {
            $side
            $_.Name
            $_.Value | ConvertTo-Json -Depth 10
        }
}
~~~

`beans` helps cross-check the bean's name, type, scope, and reported dependencies. It does not replace a behavioral test; in particular, do not infer an external service is healthy just because a client definition exists.

In `conditions`, read the message on the exact class or method. For negative matches, look for reasons in `notMatched`; conditions that matched may still be listed alongside. Do not use the count of negative matches as a metric for application errors.

There is an important limit for this lesson: do not assume every `@Profile` outcome appears as an easily searchable line in Spring Boot's condition evaluation report. If a class is excluded by profile, verify `@Profile` itself, the active profile set, and bean evidence; do not demand a negative match entry for an inner method.

[Spring Boot 3.3 — beans structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html), [conditions report](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html).

### 7.4. Checking the effective log level

~~~powershell
Invoke-RestMethod "$base/loggers/demo.DiagnosticCorrelationApplication"
~~~

`configuredLevel` is the level explicitly set on that logger, if any; `effectiveLevel` is the level actually in effect. `configuredLevel=null` does not mean logging is disabled: the logger can inherit from a parent logger.

The `loggers` endpoint describes log-level configuration; it does not return emitted log lines. When a message is missing, you must still verify execution timing, exact logger name, appenders, filters, and the log collection system.

The lab uses only GET for observation. [Spring Boot 3.3 — reading a single logger level](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 8. Seven scenarios to connect the evidence

### A. Running without activating a profile

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar
~~~

Stdout line produced by the runner:

~~~text
DIAG profiles=[] enabled=false timeoutMs=1000 client=absent
~~~

Correlate:

- Startup logs state no profile was explicitly selected and the default profile is used.
- `env` shows timeout comes from `application.properties`.
- `configprops` contains the configuration bean with prefix `demo.client`.
- `DemoClient` does not appear because the Java configuration requiring `sandbox` was not selected.
- The example's DEBUG line does not appear because the effective level is INFO.

The empty profile array in stdout is produced by `getActiveProfiles()`; do not use it to conclude Spring has no concept of a default profile.

### B. Selecting sandbox to load profile configuration

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox
~~~

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=2000 client=present
~~~

Evidence to match:

- Endpoint profiles and startup logs both include `sandbox`.
- Timeout source is `application-sandbox.properties`.
- `inputs.timeout.origin` on the bound configuration points to the profile file.
- Method `SandboxClientConfiguration#demoClient` has a matching property condition.
- The `beans` endpoint lists `demoClient`, and the runner received that object.

`2s` and `2000` in the `timeoutMs` field are not two different settings: one is the unit-bearing input string, and the other is the bound representation converted to milliseconds.

### C. Environment variable overrides the timeout in the profile file

In the terminal running the application, set the variable and restart:

~~~powershell
$env:DEMO_CLIENT_TIMEOUT = '9s'
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox
~~~

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=9000 client=present
~~~

The sandbox file still specifies 2 seconds. Being loaded does not make 2 seconds beat the environment variable.

In this run:

- `env/demo.client.timeout` reports source `systemEnvironment`.
- `configprops` can report an origin naming `DEMO_CLIENT_TIMEOUT`.
- The runner receives a `Duration` corresponding to 9,000 milliseconds.
- Profiles and client creation conditions are unchanged compared to B.

If you merely open the file on disk and edit 2 seconds to 3 seconds, you are editing a source with lower precedence than the current winning source.

### D. Command-line argument overrides the environment variable

Keep the 9-second environment variable from C, stop the application, and run:

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox --demo.client.timeout=700ms
~~~

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=700 client=present
~~~

Now the winning source is `commandLineArgs`. The environment variable still exists, yet no longer determines the timeout. Correlate the source in `env`, the origin used for binding, and the verification line together.

A source appearing in the list does not mean that source wins; nor can you remove the cause simply by editing the profile file.

### E. Disabling the property while the profile remains right

Keep the 9-second timeout variable and rerun:

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox --demo.client.enabled=false
~~~

~~~text
DIAG profiles=[sandbox] enabled=false timeoutMs=9000 client=absent
~~~

This time the missing client is not caused by the wrong profile. Query the enable flag as well:

~~~powershell
Invoke-RestMethod "$base/env/demo.client.enabled"
~~~

Connect the chain:

1. `sandbox` is active.
2. The effective enable flag comes from `commandLineArgs`.
3. The configuration object receives `enabled=false`.
4. `OnPropertyCondition` on the `demoClient` method does not match.
5. The client bean is absent, consistent with stdout.

Timeout still binds to 9 seconds even though the client is not created. Having the configuration object does not guarantee every bean using that object exists.

### F. Right property, but unsuitable profile

Clear the timeout variable in the test terminal:

~~~powershell
Remove-Item -LiteralPath Env:DEMO_CLIENT_TIMEOUT -ErrorAction SilentlyContinue
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=prod --demo.client.enabled=true
~~~

~~~text
DIAG profiles=[prod] enabled=true timeoutMs=1000 client=absent
~~~

The project has no `application-prod.properties` file; the shared property still supplies a 1-second timeout. The command-line enable flag is true, yet the Java configuration applies only to `sandbox`, so there is still no client.

This situation cannot be explained by a single `env/demo.client.enabled` query. You must add the actually active profile and the `@Profile` condition in code. The `demoClient` method source may not even be recorded in the `conditions` report because its enclosing configuration did not participate.

Do not "fix" this by turning on a flag that is already true. First confirm which configuration the application is supposed to run, then select the profile or design conditions to match requirements.

### G. Changing only log level to observe DEBUG

After F, the timeout variable is already cleared. Rerun with `sandbox` and enable DEBUG for the example's package:

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox --logging.level.demo=DEBUG
~~~

The stdout line remains:

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=2000 client=present
~~~

In addition, the message portion of a DEBUG log line is:

~~~text
DIAG_DETAIL snapshotCompleted=true
~~~

Full log formatting includes timestamp, PID, and other fields depending on configuration; the snippet above is only the message emitted by the program.

A GET on the class's own logger shows `effectiveLevel=DEBUG`. The class's direct `configuredLevel` can still be null because the setting was placed on the parent `demo` logger.

Changing observability does not change timeout, profiles, or bean creation conditions. The message appearing only after enabling DEBUG does not prove the runner only started executing then; the earlier stdout line was already proof the runner executed.

[Spring Boot 3.3 — configuring log levels](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.log-levels).

### Run comparison table

| Run | Active profile | Winning timeout source | Bound timeout, ms | Client | Key point to explain |
| --- | --- | --- | ---: | --- | --- |
| A | None explicitly selected | Shared file | 1000 | absent | Sandbox-scoped Java configuration did not participate |
| B | sandbox | Sandbox file | 2000 | present | Profile file and property condition matched |
| C | sandbox | systemEnvironment | 9000 | present | Environment variable overrode the file |
| D | sandbox | commandLineArgs | 700 | present | Command line overrode the environment variable |
| E | sandbox | systemEnvironment | 9000 | absent | Command line changed enabled flag to false |
| F | prod | Shared file | 1000 | absent | Enable flag matched, but Java profile did not |
| G | sandbox | Sandbox file | 2000 | present | DEBUG changed visibility of log message |

The table assumes only the stated sources exist and variable-cleanup steps were followed properly. If results differ, that is a reason to inspect the effective source rather than editing the table before finding the root cause.

## 9. Applying this as a workflow to diagnose a real incident

Suppose the requirement is "the client must have a 2-second timeout", yet verification logs show 9 seconds.

Proceed in order:

1. **Lock down the comparison target.** Confirm endpoints and logs belong to the same version, instance, and run.
2. **Verify profiles.** Cross-check startup logs, `activeProfiles`, and Java configurations with relevant `@Profile`.
3. **Look up one key.** Use `env/<property-name>` to locate the winning source and competing origins.
4. **Verify binding.** Find the right prefix in `configprops`; distinguish input data, Java types, and masked values.
5. **Inspect components.** Read relevant conditions and cross-check bean names/types in the context.
6. **Verify behavior and logs.** Confirm whether the component uses that configuration object; check timestamps, log levels, and appropriate tests.
7. **Change one factor and re-verify.** For instance, remove the unintended overriding source via the deployment process, restart if required, and gather the same evidence bundle again.

A solid diagnostic note for scenario C might read:

> The instance under review is running `sandbox`. The profile file declares 2 seconds, yet `env` reports `systemEnvironment` as the winning timeout source; `configprops` records input from `DEMO_CLIENT_TIMEOUT`, and the verification line shows 9,000 ms. The client bean exists. The cause of the discrepancy is an overriding environment variable source, with no evidence of a profile-file reading error.

There is no need to paste the entire environment or secrets verbatim into reports. Record only key names, sources, authorized non-sensitive values, and required evidence.

In the example, the client is merely a record. Its presence does not prove a remote server responds within the timeout; that requirement calls for a separate connectivity and behavioral test.

## 10. When pieces of evidence appear to contradict each other

| Observation | Investigation direction |
| --- | --- |
| File was edited, yet `env` did not change | Did the process reload; is there a higher-precedence source; are you reading the right file and instance |
| `env` is right, yet config object differs from expectation | Prefix, data type, unit, origin used at bind time, default value, copy retained since startup |
| `configprops` has data, yet functional bean is missing | Profiles, class/method conditions, configuration registration, and context |
| `conditions` matched, yet feature fails | Bean creation error, lazy init, external dependency, or runtime failure; read exceptions and behavior |
| A source is missing from `conditions` | Was the config processed; outer class condition; do not assume every Spring condition is reported |
| DEBUG is missing, yet runner stdout appears | Effective logger level, parent loggers, appenders/filters, and log collector |
| `env`/`configprops` shows only asterisks | Data sanitization mechanism; continue tracing source/origin or use authorized non-sensitive evidence |
| Endpoint returns 404/401/403 | Path, port, endpoint enablement/exposure, and access permissions before reasoning about business config |

Do not assume calling GET again rebinds a record or rebuilds a bean. In a typical Spring Boot application without an added refresh mechanism, modifying files or terminal environment variables does not reconfigure a running process. Restart per the application's workflow and fetch fresh data.

If the application fails before the HTTP server becomes ready, endpoints are not yet reachable observation sources. Read startup logs, binding errors, and the exception cause chain. You can use `--debug` to add the condition evaluation report to logs; do not confuse it with setting all application loggers to DEBUG or opening endpoint access permissions.

When you need to trace which configuration documents were loaded, you can temporarily enable narrow-scoped logging for `org.springframework.boot.context.config` at TRACE in an authorized environment. Control how long it stays enabled and what gets logged; do not use system-wide verbose logging as the first step for every incident.

## 11. Self-check

**Question 1:** The `sandbox` profile is active, the sandbox file says 2 seconds, yet the bound timeout is 9 seconds. Is there sufficient evidence to conclude the sandbox file was not loaded?

Not yet. Check the winning source and origin. The file may still have been loaded and overridden by an environment variable.

**Question 2:** `enabled=true` appears in configuration data, so the client is definitely present?

No. Scenario F shows that a Java configuration's profile can still exclude the bean.

**Question 3:** A logger's `configuredLevel` is null, so DEBUG is definitely disabled?

No. You must read `effectiveLevel` because a logger can inherit its level from a parent.

**Question 4:** `configprops` displays timeout as `******`, so you must set `show-values=always` to diagnose?

No. Sources, origins, profiles, logger settings, and non-sensitive verification markers may already suffice. Viewing real values must follow system policy.

**Question 5:** After changing an environment variable in the terminal, the running application still keeps the old value. Is that abnormal?

Not necessarily. A process that has already started has its own environment; configuration objects and beans were also created during that startup load.

**Exercise:** Rerun C, D, and F. For each, write one explanatory paragraph containing profiles, property source, bound data, bean status, and log evidence. Point out what has been proven and what still requires a behavioral test. The goal is a verifiable chain of reasoning rather than an isolated endpoint snapshot.
