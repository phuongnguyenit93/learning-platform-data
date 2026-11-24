# Reading the conditions Endpoint to Explain Matching and Non-Matching Auto-Configuration

## 1. From "why is this bean present or missing?" to the condition evaluation report

An application has the required library yet still fails to create the bean you expected. In another application, the default bean disappears after you declare your own bean. Looking only at dependencies or configuration files is not enough to explain either situation.

Spring Boot auto-configurations are conditional configurations. A configuration may require a class to be present, a property to hold a suitable value, the application to run under a specific web model, or no replacement bean to exist yet. The `conditions` endpoint reports which evaluated conditions matched or did not match along with the accompanying reasons.

The goal of this lesson is to read a report so you can reason clearly:

> In which context was which configuration or method's conditions evaluated, what was the outcome, and what evidence should be checked next?

Three layers of evidence must be distinguished:

| Question | Appropriate evidence |
| --- | --- |
| Why could a configuration participate or have to back off? | `conditions` and condition messages |
| Which beans were actually registered? | Bean list in the context, cross-checkable with the `beans` endpoint |
| Does the feature work properly when used? | Actual calls, tests, logs, or appropriate health checks |

A positive match line in the report does not prove a database connection succeeds, does not prove every child bean exists, and does not prove the application can serve all requests.

[Spring Boot 3.3 — meaning of the conditions endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 2. Obtaining the report before reading its contents

In a Spring Boot 3.3.x web application that already includes `spring-boot-starter-actuator`, the minimal configuration for this local lab is:

~~~properties
server.address=127.0.0.1
management.endpoint.conditions.enabled=true
management.endpoints.web.exposure.include=health,conditions
~~~

The two management properties handle two separate concerns:

- `enabled` allows the endpoint to exist.
- `exposure.include` exposes the endpoint over HTTP.

Enabling an endpoint is not equivalent to exposing it over HTTP. In Spring Boot 3.3, only `health` is exposed by default. If `exposure.exclude` also includes `conditions`, the exclusion takes precedence. These settings do not grant access through Spring Security on their own.

With the default port and path:

~~~shell
curl -i http://127.0.0.1:8080/actuator/conditions
~~~

In Windows PowerShell, you can use `curl.exe` to invoke the real curl binary. Classify the outcome before drawing conclusions:

| Result | Check first |
| --- | --- |
| HTTP 200 and JSON containing `contexts` | Begin reading the report |
| HTTP 404 | Actuator dependency, endpoint enablement/exposure, path, port, and proxy |
| HTTP 401 or 403 | Authentication, authorization, and access control layers |
| Connection failure | Process, listening port, bind address, protocol, and network |

HTTP 404 is not a `negativeMatches` entry. HTTP 403 likewise does not prove an auto-configuration failed to match.

If the application uses `management.server.port`, `management.endpoints.web.base-path`, or a custom context path, call the actual address. The example in this lesson uses a local application without Spring Security and without a proxy. When applying to other systems, keep that system's endpoint protection policy; the report can disclose class names, beans, and internal properties.

[Spring Boot 3.3 — enabling, exposing, and securing endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 3. Reading the JSON structure accurately

Start from `contexts`. Each key underneath is the ID of an application context. Do not assume every application only has a context named `application`.

| Component | How to read |
| --- | --- |
| `contexts.<id>.positiveMatches` | Configuration sources or methods whose recorded conditions matched |
| `positiveMatches.<source>[]` | List of `condition` / `message` pairs for that source |
| `contexts.<id>.negativeMatches` | Sources with non-matching conditions |
| `negativeMatches.<source>.notMatched[]` | Conditions recorded as not matching; this is where to look for blocking causes |
| `negativeMatches.<source>.matched[]` | Conditions that matched on the same source, even though the source still had a non-matching condition |
| `contexts.<id>.unconditionalClasses` | Auto-configuration classes reported as unconditional |
| `contexts.<id>.parentId` | Parent context ID, if any |

`condition` is the evaluator name, such as `OnPropertyCondition`. `message` describes the specific property, class, or bean that caused the condition to match or fail. Merely counting positive/negative entries discards critical diagnostic information.

Source names typically take two forms:

~~~text
ReportAutoConfiguration
ReportAutoConfiguration#defaultReportClient
~~~

The first form refers to the configuration class; the second refers to a method inside the class. The `#` symbol is not an HTTP fragment path. Full names, nested class names, and shortening styles may vary across sources or versions; search by the stable portion of the name and read the actual key.

The report may include ordinary configuration classes using Spring Boot conditions, not only classes ending in `AutoConfiguration`. Nor is it an exhaustive list of every bean or every Spring conditional annotation.

[Spring Boot 3.3 — conditions response structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html#actuator.conditions.retrieving.response-structure).

## 4. A JSON example and evidence-based interpretation

This is an abbreviated illustrative JSON for learning how to read the report, not an entire application response:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "ReportAutoConfiguration#defaultReportClient": [
          {
            "condition": "OnBeanCondition",
            "message": "No ReportClient bean was found"
          }
        ]
      },
      "negativeMatches": {
        "AuditAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "demo.audit.enabled does not have the required value true"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "Required AuditClient class was found"
            }
          ]
        }
      },
      "unconditionalClasses": []
    }
  }
}
~~~

The sentences in `message` in this example are rephrased for readability; do not use them as exact string-matching assertions against Spring Boot.

You can conclude:

1. The missing-bean condition on method `defaultReportClient` matched: at evaluation time, no bean meeting the criteria was found.
2. `AuditAutoConfiguration` had its class condition match.
3. The property-value condition on `AuditAutoConfiguration` did not match, so finding the class was not enough for this configuration to participate.
4. To find out where the effective property value came from, you must inspect the configuration environment; this report does not answer which source overrode it.

Do not conclude "the application is broken because there are negatives". A healthy application naturally excludes many configurations that do not apply to its current dependencies, web model, or feature choices.

### Reading outcomes of negated conditions

Pay special attention to `@ConditionalOnMissingBean`:

| Observation | Condition outcome |
| --- | --- |
| No bean meeting criteria was found | The "missing bean" condition matched |
| A bean meeting criteria already existed | The "missing bean" condition did not match |

Thus, `did not find any beans` can appear in positive matches. Conversely, a message saying a bean was found can appear in negative matches. Always read according to the annotation's semantics instead of guessing from the words "found" or "missing".

For auto-configuration, skipping creation of a default bean because the user already supplied an appropriate bean is typically intended back-off behavior. The condition inspects bean definitions already processed at evaluation time, along with the declared type, name, and search scope; do not interpret it as an evaluation independent of configuration ordering.

[Spring Boot 3.3 — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

## 5. Controlled practice: change one factor and re-read the report

The following example creates a small auto-configuration to observe three phenomena:

- Missing property causing no match.
- Matching property with no existing bean causing the default configuration to participate.
- Existing custom bean causing the default factory method to back off.

This is a standalone lab project using Java 21, Gradle 8.5, and Spring Boot 3.3.0. Versions are pinned for reproducibility, not as a recommendation to upgrade or downgrade other projects. The Java examples cannot be run with `javac ConditionsLab.java` alone because they require Spring dependencies.

### 5.1. Two Gradle files

Create `settings.gradle`:

~~~groovy
rootProject.name = 'conditions-lab'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
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

Use Gradle 8.5 to generate the wrapper if not yet present:

~~~shell
gradle wrapper --gradle-version 8.5
~~~

Preparing dependencies the first time requires connectivity to the plugin repository and Maven Central.

### 5.2. Application configuration

Create `src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
management.endpoint.conditions.enabled=true
management.endpoints.web.exposure.include=health,conditions
demo.report.custom=false
~~~

Intentionally omit `demo.report.enabled`. Do not add a Security dependency in this lab project.

### 5.3. Complete Java program

Create `src/main/java/demo/ConditionsLab.java`:

~~~java
package demo;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
@Import(ConditionsLab.UserConfiguration.class)
@ImportAutoConfiguration(ConditionsLab.ReportAutoConfiguration.class)
public class ConditionsLab {

    public static void main(String[] args) {
        var context = SpringApplication.run(ConditionsLab.class, args);
        var client = context.getBeanProvider(ReportClient.class).getIfAvailable();
        System.out.println("REPORT_CLIENT=" + (client == null ? "none" : client.owner()));
    }

    public record ReportClient(String owner) {
    }

    @AutoConfiguration
    @ConditionalOnClass(Clock.class)
    @ConditionalOnProperty(
        prefix = "demo.report", name = "enabled", havingValue = "true"
    )
    public static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportClient.class)
        ReportClient defaultReportClient() {
            return new ReportClient("auto");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class UserConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.report", name = "custom", havingValue = "true"
        )
        ReportClient customReportClient() {
            return new ReportClient("custom");
        }
    }
}
~~~

`ReportClient` merely holds a label identifying the bean creation source; the example makes no network calls and sends no external reports.

How the experiment is structured:

- `@SpringBootConfiguration` and `@EnableAutoConfiguration` bootstrap Spring Boot configuration; the example intentionally avoids component scanning.
- `@Import` brings the user's custom bean configuration into the application.
- `@ImportAutoConfiguration` feeds the exact auto-configuration under test into auto-configuration processing.
- `@ConditionalOnClass(Clock.class)` creates a class condition that always matches in the lesson's Java 21 environment.
- `@ConditionalOnProperty` on the class requires `demo.report.enabled=true`.
- `@ConditionalOnMissingBean` on the method permits creating the default bean only when no `ReportClient` exists yet.
- The custom bean has an independent toggle `demo.report.custom`.

Importing configurations directly here keeps the example in a single file. This is not a guide for packaging starters. When writing reusable libraries, declaring auto-configuration candidates and ordering must follow the auto-configuration contract.

[Spring Boot 3.3 — ImportAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html), [Developing Auto-configuration guide](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

### 5.4. Case A — feature-enabling property absent

Run in the project directory with JDK 21:

~~~shell
./gradlew bootRun
~~~

In PowerShell, use `.\gradlew.bat bootRun`.

After startup log lines, the line printed by the program is:

~~~text
REPORT_CLIENT=none
~~~

Open another terminal and fetch the report:

~~~powershell
$report = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/conditions'
$report.contexts.PSObject.Properties.Name
~~~

If the actual ID list includes `application`, select that context:

~~~powershell
$ctx = $report.contexts.application
$ctx.negativeMatches.PSObject.Properties |
    Where-Object { $_.Name -like '*ReportAutoConfiguration*' } |
    ForEach-Object {
        $_.Name
        $_.Value.notMatched | Format-Table condition, message -Wrap
        $_.Value.matched | Format-Table condition, message -Wrap
    }
~~~

If the ID differs, pick the ID you just read, such as `$report.contexts.'actual-context-name'`; do not assume the name `application` is immutable.

Under the `ReportAutoConfiguration` class entry, find `OnPropertyCondition` in `notMatched` and read the message about the missing `enabled` property. At the same time, you can see `OnClassCondition` matched under `matched`.

Explanation: having class `Clock` is not enough; the class-level property gate still blocks the configuration. Because `matchIfMissing` defaults to `false`, omitting the property is not interpreted as opting in.

[Spring Boot 3.3 — ConditionalOnProperty and matchIfMissing](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).

### 5.5. Case B — feature enabled, no custom bean

Stop Run A with Ctrl+C, then run:

~~~shell
./gradlew bootRun --args="--demo.report.enabled=true"
~~~

In PowerShell, replace `./gradlew` with `.\gradlew.bat`.

The line printed by the program:

~~~text
REPORT_CLIENT=auto
~~~

Call the endpoint again to fetch a fresh report; the old `$report` variable does not update automatically:

~~~powershell
$report = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/conditions'
$ctx = $report.contexts.application
$ctx.positiveMatches.PSObject.Properties |
    Where-Object { $_.Name -like '*ReportAutoConfiguration*' } |
    ForEach-Object {
        $_.Name
        $_.Value | Format-Table condition, message -Wrap
    }
~~~

Read the two sources separately:

1. Class-level source: both class and property conditions matched.
2. `#defaultReportClient` source: `OnBeanCondition` matched because no matching `ReportClient` was found yet.

Combined with `REPORT_CLIENT=auto`, you have evidence that the example is using the default bean. JSON entry ordering and exact message wording are not stable test criteria; rely on source, condition, and reason.

### 5.6. Case C — feature enabled and custom bean provided

Stop Run B, then run:

~~~shell
./gradlew bootRun --args="--demo.report.enabled=true --demo.report.custom=true"
~~~

The line printed by the program:

~~~text
REPORT_CLIENT=custom
~~~

Fetch a fresh report and filter for the default method:

~~~powershell
$report = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/conditions'
$ctx = $report.contexts.application
$ctx.negativeMatches.PSObject.Properties |
    Where-Object { $_.Name -like '*ReportAutoConfiguration#defaultReportClient' } |
    ForEach-Object {
        $_.Name
        $_.Value.notMatched | Format-Table condition, message -Wrap
    }
~~~

The class-level source remains in positive matches, whereas `#defaultReportClient` is in negative matches. `OnBeanCondition` reports that the custom bean `customReportClient` was found.

Complete reasoning:

- The feature toggle satisfied the class-level condition.
- The user supplied a `ReportClient` bean.
- The "no ReportClient yet" condition on the default method no longer holds.
- No default bean is registered from this method; the custom bean is used.
- This is the back-off mechanism, not a missing-dependency error and not two beans with identical names overriding each other.

Do not "fix" this situation with `spring.main.allow-bean-definition-overriding=true`. The two concepts—"not registering due to conditions" and "allowing bean definition overriding"—solve different problems.

### 5.7. Case D — explicitly set to false

Stop Run C, then run:

~~~shell
./gradlew bootRun --args="--demo.report.enabled=false"
~~~

`demo.report.custom` reverts to `false` from the configuration file. Output:

~~~text
REPORT_CLIENT=none
~~~

This time `OnPropertyCondition` fails to match because the property exists with a value other than `true`. The cause differs from A, even though both result in no default bean being created.

| Run | enabled | custom | Bean label | Primary evidence |
| --- | --- | --- | --- | --- |
| A | Undeclared | false | none | Class-level condition failed due to missing property |
| B | true | false | auto | Both class condition and missing-bean condition matched |
| C | true | true | custom | Class matched; default method failed because custom bean exists |
| D | false | false | none | Class-level condition failed due to non-matching value |

The `REPORT_CLIENT=...` lines are stdout generated by the example code, not the full Spring Boot log. For each run, stop the previous process and fetch a fresh report to avoid reading stale state.

## 6. Turning messages into next diagnostic checks

A diagnostic conclusion should take the form:

> Context → configuration source/method → condition → observed message → hypothesis → confirming evidence.

| Condition/message group | Next question | What not to infer |
| --- | --- | --- |
| `OnClassCondition` missing class | Is that class on the runtime classpath? Is the dependency version right? | Compile-time dependency alone is enough |
| `OnPropertyCondition` missing property | Are the key name, profile, and effective config source right? | Adding a key to any YAML file will fix it |
| `OnPropertyCondition` mismatched value | Is an environment variable, CLI argument, or other config overriding it? | Value seen in Git is always the running value |
| `OnBeanCondition` for missing bean | Which bean already exists, under what type/name, and in which context scope? | Having a custom bean is an error |
| Web model condition mismatch | Does the application need Servlet, Reactive, or no web? | Every web configuration must match |
| Class condition matched, method did not | What is the method's own condition? | Positive on the class guarantees every bean in the class |

These are investigation directions, not conclusions about a specific system. From the report, take the exact class, property, or bean name and inspect the corresponding source. `env` traces property sources, `configprops` shows bound configuration, and `beans` verifies beans; access only endpoints permitted for exposure and reading.

When you need to prove a bean exists, verify the exact type and context. When you need to prove a feature works, perform a representative action of that feature. Do not substitute counting positive lines for behavioral verification.

## 7. Limits to remember when the report does not explain enough

### Source does not appear at all

Not finding a configuration name does not imply its conditions matched or failed to match. Check in order:

1. Are you inspecting the right application, version, profile, and context?
2. Were the dependency and configuration class actually included in the application?
3. Was the configuration registered via the appropriate mechanism?
4. Is it excluded via `@SpringBootApplication(exclude=...)` or `spring.autoconfigure.exclude`?
5. Did an outer class-level condition prevent inner configuration from being processed?

Do not assume the endpoint has a JSON field named `exclusions`. For the Spring Boot 3.3 response contract used in this lesson, exclusions must be checked from configuration and appropriate log reports. Excluded configurations should not be interpreted as ordinary negative match lines.

[Spring Boot 3.3 — replacing and excluding auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### The report is not a complete history of every condition

Conditions are ordered and evaluation may short-circuit once enough grounds exist to exclude a configuration. The list you read contains recorded outcomes and does not guarantee every subsequent condition was evaluated. A missing entry or empty `matched` array does not justify inferring the result of unrecorded conditions.

`unconditionalClasses` likewise does not mean "every bean factory method inside the class is unconditional". Always inspect conditions at the exact class or method level of interest.

### Editing files does not automatically reconfigure the application

The report reflects the evaluation results of the current context; calling GET does not ask Spring Boot to rebuild all beans from edited files. In typical lab projects, edit the property, restart the application, and fetch a fresh report.

### Application failed to start

If startup fails, the HTTP endpoint may not exist yet. Use error logs and enable the condition evaluation report at startup:

~~~shell
./gradlew bootRun --args="--debug"
~~~

Or with an actual executable JAR:

~~~shell
java -jar application.jar --debug
~~~

`application.jar` here is an illustrative name for the application's JAR. `--debug` enables viewing the report in logs; it does not expose `/actuator/conditions`. When the error lies in bean creation or resource connectivity, read the relevant exception cause; positive matches do not rule out such failures.

[Spring Boot 3.3 — viewing the report with debug at startup](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html#using.auto-configuration.replacing).

## 8. Self-check on reasoning

**Scenario 1:** `OnClassCondition` matched while `OnPropertyCondition` did not match on the same class. Should you immediately add the library again?

No. Current evidence points to the property. Read the key name, the condition's requirement, and the effective value first.

**Scenario 2:** The class is in positive matches, while the default method is in negative matches because a custom bean exists. Is there a contradiction?

No. These are two sources at two different levels. The result shows the class configuration was accepted while the default method had to back off.

**Scenario 3:** A positive `OnBeanCondition` says "did not find any beans". Why is it positive?

Because the condition is checking for the absence of a bean. Identify the specific annotation rather than reading outcomes by impressions of wording.

**Scenario 4:** You enabled the toggle in YAML, called the endpoint again, and the result did not change. Does that prove Spring Boot ignored YAML?

Not yet. Check whether the process loaded the new configuration, profiles, and overriding sources, then restart according to the application's configuration management workflow.

**Further practice:** Rerun B and C, writing for each a single explanatory sentence containing context, source, condition, reason, and the `REPORT_CLIENT` label. Then compare A with D: same missing-bean outcome yet different root causes. If you can explain this difference from the report, you are using `conditions` for diagnostics rather than just keyword searching.
