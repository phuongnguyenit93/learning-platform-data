# Diagnosing a Configuration Incident Using Value-Provenance Evidence

> **Topic:** Spring Boot Externalized Configuration  
> **Category:** Integrated Practice

## 1. Opening Scenario: "YAML Says 5 Seconds, So Why Does the App Still Time Out After 800 ms?"

A team operates a Spring Boot service called `payment-gateway`. When calling an external payment service, the application keeps timing out. The engineer on call opens `src/main/resources/application.yml` and sees:

~~~yaml
payments:
  client:
    timeout: 5s
    base-url: "https://payments.example.test"
~~~

They conclude the timeout must be 5 seconds. Yet when inspecting a running configuration bean, the actual value is `PT0.8S`, equivalent to **800 milliseconds**.

In a hypothetical staging environment, configuration also includes:

~~~yaml
# src/main/resources/application-staging.yml
payments:
  client:
    timeout: 3s
~~~

~~~yaml
# ./config/application-staging.yml (outside the JAR)
payments:
  client:
    timeout: 2s
~~~

Process environment variable:

~~~text
PAYMENTS_CLIENT_TIMEOUT=1500ms
~~~

And startup arguments:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging \
  --payments.client.timeout=800ms
~~~

In Spring Boot's common default property source order, command-line arguments have higher precedence than OS environment variables, and these sources can override Config Data values. Therefore, **800 ms** is the effective value in this example.

However, the engineer's job is not merely guessing "CLI wins." They must present **value-provenance evidence**, proving:

1. Which exact artifact version is the process running?
2. Which configuration sources were actually loaded?
3. Which profiles are active, and which files sit inside vs. outside the JAR?
4. What exact key is being looked up?
5. What is the effective value?
6. Which `PropertySource` supplies the winning value?
7. Did the `@ConfigurationProperties` bean bind from that value?
8. Does the constructed HTTP client actually use the new timeout?
9. Why did the operator see `5s` in a file while runtime observed `800ms`?
10. Where should the change be made to fix **the true source**, rather than stacking another override that hides the root cause?

This lesson is a **root-cause investigation practice from symptom to root cause** using verifiable evidence. All domains, endpoints, and values shown here are illustrative examples.

### Learning Objectives

After practicing, you will be able to:

- Build a timeline from startup to runtime failure and distinguish observed facts from speculation.
- Collect information about effective properties, active profiles, property sources, and origin.
- Understand the differences among **source name**, **file/line origin**, **final value in `Environment`**, and **value used by the client**.
- Use `ConfigurableEnvironment`, Actuator `env`/`configprops`, and appropriate test tools without exposing secrets.
- Analyze precedence across CLI, Java system properties, OS environment, `SPRING_APPLICATION_JSON`, Config Data, `@PropertySource`, and default properties.
- Inspect profiles, documents, imports, relative paths, Config Trees, and late-loaded sources.
- Distinguish an unloaded source, an overridden source, an unbound field, and a client holding a stale snapshot.
- Produce an incident report containing hypotheses, evidence, root cause, remediation, and verification evidence.
- Write regression tests so the incident does not recur.

## 2. Investigation Principle: Evidence Over Guesswork

When a configuration bug appears, do not start with the question "Which file should we edit?" Start with:

> **What value is the running application actually using, which source did that value come from, and when was it applied to the component?**

A reliable workflow clearly separates three layers:

~~~text
LAYER 1 — System Data Sources
    YAML / properties files / env / JVM args / CLI
    Secret / ConfigMap / imported files / defaults
                     |
                     v
LAYER 2 — Spring Environment and Binder
    ordered PropertySources
    effective property resolution
    relaxed binding and type conversion
    @ConfigurationProperties / @Value
                     |
                     v
LAYER 3 — Resources and Runtime Behavior
    HTTP client, connection pool, scheduler
    request timeout, reconnect, retry
    metrics, traces, business outcomes
~~~

A file may hold the right value yet **never be loaded**. A loaded file may **be overridden by a higher-precedence source**. A properly bound bean may be passed to the wrong client. A client built cleanly at startup may still **retain stale config after external sources are edited**.

The root-cause conclusion must pinpoint which layer failed.

### 2.1. Observations Differ from Conclusions

Examples:

| Statement type | Example | Evidence level |
| --- | --- | --- |
| Observation | Source file `application.yml` currently shows `5s` | Proves only the contents of the file you opened |
| Observation | `Environment.getProperty(...)` returns `800ms` | Proves effective lookup at measurement time |
| Observation | `@ConfigurationProperties.timeout()` returns `PT0.8S` | Proves the bean bound `800ms` |
| Observation | HTTP request to mock server fails after ~800ms | Behavioral evidence; still must rule out network/other timeouts |
| Hypothesis | CLI overrides the config file | Needs confirmation of actual process args and property sources |
| Conclusion | Argument `--payments.client.timeout=800ms` wins and the client binds from it | Stated only once backed by a complete evidence chain |

A system can have many distinct timeouts: DNS, TCP connect, TLS handshake, read, total request, retry deadline, or load balancer timeout. "After 800ms" alone does not prove it came from `payments.client.timeout`; you still must confirm which component applied it.

### 2.2. Never Use Sensitive Data for Debugging

Inspect only non-sensitive keys such as timeouts, demo ports, or feature flags. If a key involves passwords, API tokens, JWT private keys, or connection URLs carrying credentials:

- Do not log raw values.
- Do not print the entire `Environment`.
- Do not attach screenshots containing secrets to tickets.
- Do not expose Actuator `env`/`configprops` publicly.
- You may record **property names**, **sources**, **presence/absence**, and non-sensitive version identifiers according to policy.

This practice uses only timeouts and dummy hostnames.

## 3. Setting Up a Sample Application to Reproduce the Case

The examples use Java 17+ and Spring Boot 3.x/4.x matched to your project toolchain. The lesson emphasizes how configuration flows; exact HTTP client API details may vary by version.

### 3.1. Defining Typed Configuration

~~~java
package com.example.payments.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "payments.client")
@Validated
public record PaymentClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout
) {
    public PaymentClientProperties {
        if (timeout == null || timeout.isZero()
                || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "payments.client.timeout must be positive");
        }
    }
}
~~~

Canonical properties are:

~~~text
payments.client.base-url
payments.client.timeout
~~~

With `@ConfigurationProperties`, the Spring Boot Binder supports relaxed binding where applicable, so an environment variable such as `PAYMENTS_CLIENT_TIMEOUT` can map to `payments.client.timeout`.

Do not confuse hyphens in key names with an arbitrary mechanism for changing environment variable names. Canonical rules are defined by Boot; nested maps and list indices require separate analysis.

### 3.2. Registering `@ConfigurationProperties`

~~~java
package com.example.payments;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentGatewayApplication.class, args);
    }
}
~~~

Configuration must be registered as a bean for injection to take effect. You can replace `@ConfigurationPropertiesScan` with `@EnableConfigurationProperties(PaymentClientProperties.class)` on an appropriate configuration class.

### 3.3. Creating a Component That Consumes the Value

~~~java
package com.example.payments.client;

import com.example.payments.config.PaymentClientProperties;
import java.net.http.HttpClient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PaymentHttpClientConfiguration {

    @Bean
    HttpClient paymentHttpClient(PaymentClientProperties properties) {
        return HttpClient.newBuilder()
                .connectTimeout(properties.timeout())
                .build();
    }
}
~~~

In this example, `HttpClient.newBuilder().connectTimeout(...)` sets the **connect timeout**. If the production issue is **total response wait time**, you must configure a request timeout on `HttpRequest` or the corresponding client. Never assume a custom property named `payments.client.timeout` automatically controls every HTTP timeout.

This is an important illustration: **a property name can be right and binding can succeed, yet runtime behavior is wrong because a developer wired it to the wrong kind of timeout**.

### 3.4. Configuration Files of the Case Study

File inside the JAR:

~~~yaml
# src/main/resources/application.yml
payments:
  client:
    base-url: "https://payments.example.test"
    timeout: 5s
~~~

Profile file inside the JAR:

~~~yaml
# src/main/resources/application-staging.yml
payments:
  client:
    timeout: 3s
~~~

External file in the working directory:

~~~yaml
# ./config/application-staging.yml
payments:
  client:
    timeout: 2s
~~~

Environment:

~~~text
PAYMENTS_CLIENT_TIMEOUT=1500ms
~~~

CLI:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging \
  --payments.client.timeout=800ms
~~~

Under the corresponding default file-search configuration, external config under `./config/` is picked up by Boot when launched from the right working directory. When both CLI and env are present, the effective value of `payments.client.timeout` in this case study is `800ms`.

## 4. Building an Incident Timeline

A clear timeline separates what happened from speculation.

| Time | Event | What to collect |
| --- | --- | --- |
| 09:00 | New release deployed | Image digest/JAR version, commit ID |
| 09:02 | Process starts | Process start time, redacted args, active profiles |
| 09:03 | Spring Boot reports started | Startup logs, condition report when needed |
| 09:10 | Requests to Payment API time out | Request metrics, exception types, tracing |
| 09:20 | Operator opens `application.yml` and sees `5s` | Absolute path of the file being inspected |
| 09:25 | Observes config bean holding `800ms` | Typed bean/`Environment` value, observation timestamp |
| 09:30 | Discovers CLI has `800ms` | Source precedence and actual launch command |
| 09:40 | Fixes startup config, rolls out | Change ID, artifact/config revision |
| 09:50 | Re-verifies behavior | Typed bean, effective property, HTTP behavior |

Note: timestamps are only examples. During real debugging, maintain consistent timestamps/timezones and avoid confusing an older process with a new Pod.

### 4.1. Ensuring You Are Inspecting the Right Instance

A Kubernetes service may have multiple replicas:

~~~text
payment-gateway-abc: timeout=800ms
payment-gateway-def: timeout=800ms
payment-gateway-ghi: timeout=2s
~~~

If you check logs from only one Pod or hit an endpoint through a load balancer, conclusions can be misleading when multiple config revisions coexist. Identify **instance identity**, image version, container start time, and each replica's configuration revision.

A reading from one Pod proves only that Pod's state—not that the whole deployment is uniform.

## 5. Precedence Order: Why "In the File" Does Not Guarantee the Winning Value

Spring Boot maintains an ordered list of `PropertySource` entries by priority. The table below lists only common groups in an application, ordered **from lower to higher precedence**:

| Source group | Description |
| --- | --- |
| Default properties | Defaults supplied directly to `SpringApplication` |
| `@PropertySource` | Added when processing configuration classes; relatively late timing |
| Config Data | `application.yml`, `application.properties`, profile files, imports, external files |
| `RandomValuePropertySource` | For example, `random.uuid` |
| OS environment | For example, `PAYMENTS_CLIENT_TIMEOUT` |
| Java system properties | For example, `-Dpayments.client.timeout=...` |
| `SPRING_APPLICATION_JSON` | JSON passed via env, system property, or CLI as supported by Boot |
| Command-line arguments | For example, `--payments.client.timeout=...` |
| Test-specific sources | Can be added with dedicated priority in the test runtime |

Web containers or tests can introduce additional sources such as JNDI, `ServletContext` init parameters, test properties, `DynamicPropertySource`, and DevTools settings. Do not treat this condensed table as a substitute for the official precedence list across every environment.

For our example:

~~~text
application.yml                   : 5s
application-staging.yml in JAR    : 3s
./config/application-staging.yml  : 2s
PAYMENTS_CLIENT_TIMEOUT           : 1500ms
--payments.client.timeout         : 800ms
----------------------------------------
Effective value                   : 800ms
~~~

This is an **illustrative analysis assuming all five sources exist**, not verification that they were all read on a live system.

### 5.1. Do Not Judge by File Modification Timestamp

The most recently edited file does not necessarily take higher precedence. Ordering in Spring Boot is determined by source type, location, profiles, imports, and customizations; filesystem timestamps are not an override rule.

### 5.2. One Key with Two Values

When multiple sources supply **the same property name**, the higher-precedence source wins in normal lookups. However, for collection/list binding, the environment may replace the entire list rather than merging items element by element. For `Map` properties, keys may merge according to Binder rules.

Do not apply a blanket "everything merges" rule to all config types; when an incident involves lists or maps, inspect **typed binding** rather than just a scalar key.

### 5.3. Custom Sources Can Be Added at Runtime

An `EnvironmentPostProcessor` or initializer can insert a `MapPropertySource` at the head of the list. Applications using Spring Cloud Config or a secret integration can also introduce extra sources with their own ordering.

Therefore, **documented precedence tables are a starting point**; the strongest evidence is `PropertySources` from the actual running application.

## 6. Five Questions Before Opening Code

Before adding logs or a debugger, collect:

1. **Runtime identity:** exact image digest, JAR version, commit, Pod name, or VM?
2. **Process launch:** command-line arguments, JVM options, environment variable names, working directory?
3. **Profiles:** `spring.profiles.active` or profiles injected via another supported mechanism?
4. **Config locations:** which directories/files is Boot searching, and are `spring.config.location`, `additional-location`, or `import` set?
5. **Target property:** what is the canonical name and which bean/client consumes it?

Without answering these five questions, you risk inspecting the right file in **the wrong environment or wrong process**.

### 6.1. Distinguishing Filename from Active Source

A path such as:

~~~text
./config/application-staging.yml
~~~

is a **candidate config file**. To claim it took effect, prove Boot actually loaded it, the matching profile is active, and no higher source overrode the key of interest.

### 6.2. Do Not Collect Verbatim Command Lines If They Contain Secrets

JVM/CLI arguments can carry passwords or tokens. In an incident report, write:

~~~text
--payments.client.timeout=800ms
--partner.api.token=<REDACTED>
~~~

Never circulate uncontrolled raw production arguments or logs. If an item is highly sensitive, record only the key name and presence/absence per policy.

## 7. Inspecting Effective Values from Spring `Environment`

For non-sensitive keys, you can use an `ApplicationRunner`:

~~~java
package com.example.payments.diagnostics;

import com.example.payments.config.PaymentClientProperties;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
class PaymentConfigProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;
    private final PaymentClientProperties properties;

    PaymentConfigProbe(
            ConfigurableEnvironment environment,
            PaymentClientProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "payments.client.timeout";

        System.out.println(
                "Effective Environment value: "
                        + environment.getProperty(key)
        );
        System.out.println(
                "Bound Duration: " + properties.timeout()
        );
        System.out.println(
                "Active profiles: "
                        + String.join(",", environment.getActiveProfiles())
        );
    }
}
~~~

In the case study, output looks like:

~~~text
Effective Environment value: 800ms
Bound Duration: PT0.8S
Active profiles: staging
~~~

Notes:

- `environment.getProperty` returns a string resolved from property sources at the moment of the call.
- `properties.timeout()` is an already bound `Duration`, so Java renders ISO-8601 `PT0.8S`.
- Raw `800ms` and typed `PT0.8S` are **not two different timeouts**.
- If the probe runs after `Environment` has been altered by custom logic, the effective value at probe time may differ from the snapshot captured when the bean was bound.

### 7.1. Why Not Use Only `@Value`?

You could read:

~~~java
@Value("${payments.client.timeout:5s}")
private Duration timeout;
~~~

However, `@Value` only shows what was injected into a single bean; it does not reveal which source won. For structured configuration, `@ConfigurationProperties` is usually easier to manage and validate.

### 7.2. Never Let a Probe Leak Data in Production

Never expose a public endpoint returning every `Environment` key and value. In production, probes should only be enabled under tight controls, restricted to an allowlist of non-sensitive keys, avoiding tokens/passwords and hiding unnecessary internal structure.

Remove temporary probes after an incident if they were added strictly for debugging.

## 8. Inspecting `PropertySources` Order in the Exact Process

`ConfigurableEnvironment` exposes the ordered list of `PropertySource` entries. For a non-sensitive key:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class PropertySourceInspector {

    public static void inspect(
            ConfigurableEnvironment environment,
            String key) {

        System.out.println("Effective: "
                + environment.getProperty(key));

        for (PropertySource<?> source :
                environment.getPropertySources()) {

            Object raw = source.getProperty(key);
            if (raw != null) {
                System.out.println(
                        source.getName()
                                + " -> " + raw
                );
            }
        }
    }
}
~~~

Here the loop walks the current order of `MutablePropertySources`. An earlier source can beat a later source for the same key name.

### 8.1. Source Name Is Not Necessarily File/Line Origin

A `PropertySource` name identifies a Config Data resource, command-line args, or environment. However, `source.getName()` **does not always contain** the specific file path and line number of a value. It is the source identifier, distinct from **origin tracking**.

Spring Boot loaders can attach origin metadata, yet not every source supports it. For OS env or custom sources, you may learn only the source or key name, not which deployment manifest declared the variable.

### 8.2. Limitations of `getProperty` with Raw Names

`source.getProperty("payments.client.timeout")` may not discover every OS environment variable under relaxed binding in all cases. The Boot Binder and adaptation layers can resolve canonical names and aliases differently from a raw lookup on a single source.

Therefore, if the loop prints no environment variable while the Binder still receives a value, do not jump to concluding the source does not exist. Check how the source stores keys (`PAYMENTS_CLIENT_TIMEOUT`) and review relaxed binding rules.

### 8.3. Print Only Allowlisted Keys

The snippet above illustrates with a non-sensitive timeout. Never use it to iterate over all sources and print every property. A source can hold secrets, URLs with embedded credentials, private keys, or tenant-specific data.

## 9. What Is Origin and Why Is It Stronger Than Just Seeing a Key?

In Spring Boot, origin metadata can associate a configuration value with where it was loaded from, for example:

~~~text
class path resource [application-staging.yml]
  - line 4, column 14
~~~

or:

~~~text
file [./config/application-staging.yml]
  - line 3, column 14
~~~

These strings illustrate the format only. Exact locations vary by loader, file, and version. Origin metadata does not exist for every `PropertySource`.

### 9.1. Source Name vs. Origin Location

| Artifact | Question answered |
| --- | --- |
| `PropertySource` name | "What is the source called in `Environment`?" |
| Raw property key | "Which key exists inside the source?" |
| Effective property value | "What value does the current lookup return?" |
| Origin metadata | "Which file/line/column or resource does the loader know the value came from?" |
| Bound bean value | "What value does the Java object have after conversion?" |
| Client behavior | "How does the live component actually use that value?" |

No single log line always answers all six questions. Engineers must assemble evidence along the configuration path.

### 9.2. Origin Reflects Loaded Source, Not Edit History

If origin points to `application-staging.yml:4`, it shows the loader produced the value from that spot during loading. It does **not** tell you which Git commit wrote that line, who edited it, or whether another override is winning over it.

For change history, check deployment revisions, Git history, or your configuration management system's audit logs.

### 9.3. Origin Does Not Always Report an Exact Line

For environment variables, Java system properties, dynamic property sources, or custom `PropertySource` implementations, origin may lack a line/column or appear differently. **Lack of granular origin metadata does not mean absence of a value.**

When origin metadata is unavailable, document the limitation of your evidence instead of guessing file paths.

## 10. Actuator `env` and `configprops`: Observing from a Running App

If the project includes `spring-boot-starter-actuator` with proper security configuration, two endpoints are frequently helpful:

- `/actuator/env` or `/actuator/env/{property.name}`: information about `Environment` and property sources.
- `/actuator/configprops`: information about registered `@ConfigurationProperties` beans and bound values, depending on version and exposure settings.

### 10.1. Using the `env` Endpoint for a Specific Key

For a non-sensitive key:

~~~text
GET /actuator/env/payments.client.timeout
~~~

The actual JSON payload depends on the Spring Boot version, endpoint configuration, and sanitization rules. It usually lists property sources contributing values, metadata about the source, and origin if available.

**Do not assume the response always shows raw values.** Spring Boot Actuator masks values according to `management.endpoint.env.show-values` and associated authorization/sanitization policies. By default, values may be masked.

### 10.2. Do Not Enable `show-values=ALWAYS` in Production Just to Debug

Actuator visibility options can be tuned in controlled environments. Exposing all values on a public endpoint, however, can leak secrets.

To find the winning source, observing the key name, source name, origin metadata, and safely inspected typed values is usually sufficient. Never turn a timeout incident into a credential-leak incident.

### 10.3. The `configprops` Endpoint Answers a Different Question

`env` focuses on property sources and `Environment`. `configprops` focuses on `@ConfigurationProperties` beans and binding results.

If the effective `Environment` timeout is `10s` while the bean holds `3s`, the bean may have been bound before a runtime change, or two distinct beans/config objects may exist. That points to lifecycle investigation rather than file precedence alone.

### 10.4. Actuator Must Be Secured

Expose only necessary endpoints behind proper authentication, authorization, and network controls. Never set `management.endpoints.web.exposure.include=*` indiscriminately in production. Values may be sanitized or restricted to protect sensitive data; do not disable those safeguards merely for convenience in viewing secrets.

## 11. Reading Evidence from the Case Study

After running the hypothetical application with all five sources, a safe report might state:

| Relative priority | Source | Property | Value |
| --- | --- | --- | --- |
| Highest in case | Command-line arguments | `payments.client.timeout` | `800ms` |
| Below CLI | OS environment | `PAYMENTS_CLIENT_TIMEOUT` | `1500ms` |
| Below env | External `application-staging.yml` | `payments.client.timeout` | `2s` |
| Below external | Packaged `application-staging.yml` | `payments.client.timeout` | `3s` |
| Below packaged profile | Packaged `application.yml` | `payments.client.timeout` | `5s` |

The evidence must explain **why `800ms` won**. This investigation pattern applies when the system runs with default ordering and no higher custom source.

Root cause in this example:

> The staging startup script still passes `--payments.client.timeout=800ms` left over from a previous latency experiment. CLI arguments outrank YAML files and environment variables. Therefore, even though the default application file states `5s`, the `PaymentClientProperties` bean receives `Duration=800ms` and the HTTP client reads its timeout from that bean at initialization.

### 11.1. A Strong Conclusion States Both Evidence and Scope

Do not merely write "overridden by config." Specify:

- Affected key.
- Winning source and verifiable location/identifier.
- Winning value.
- Lower-precedence sources that were overridden.
- Affected bean/client.
- When the issue started and which instances share it.
- What change triggered the incident.

### 11.2. When the Conclusion Is Still Incomplete

If `PaymentClientProperties.timeout()` returns `800ms` yet the HTTP client does not use that property, an 800ms network failure may stem from a different cause. Cross-check bean creation code and tests covering timeout behavior.

Never treat a plausible-looking configuration value as sole proof of a latency spike's cause.

## 12. Root Cause and Fixing in the Right Place

In the example, the winning source is the CLI:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging \
  --payments.client.timeout=800ms
~~~

If the deployment goal is to take the timeout from external configuration, you can remove the override:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging
~~~

Then, if `PAYMENTS_CLIENT_TIMEOUT=1500ms` still exists in the environment, the effective value shifts to **1500ms**, not necessarily `2s` or `5s`. Removing a higher source merely "exposes" the next source in line.

To end up with `5s`, align on **one canonical source** and clean up or update the other overrides according to deployment policy.

### 12.1. Do Not Fix by Adding a Sixth Override

An unsustainable reaction is adding:

~~~bash
java -jar payment-gateway.jar \
  --payments.client.timeout=5s
~~~

into a new pipeline while leaving older sources untouched elsewhere. That may mask today's symptom, yet makes configuration harder to maintain with unclear ownership.

Better fix: decide where the team owns timeouts, delete temporary overrides, document precedence, and add tests/guardrails to prevent recurrence.

### 12.2. Do Not Rewrite an Entire YAML File When Only One Key Is Wrong

If a file holds database credentials, HTTP endpoints, and unrelated toggles, never replace the whole file to "reset config." Edit only the part proven to be responsible; keeping diffs small makes rollback and review safe.

### 12.3. Rollout/Restart Is Needed for New Values to Take Effect

If the Spring Boot process has already loaded configuration and built a singleton client, editing a startup script or YAML file does not automatically update the running client. Restart or roll out through your infrastructure mechanism, or use a deliberately designed and tested refresh mechanism.

## 13. Inspect the Actual Runtime Files, Not Only the Repository Files

When a developer opens:

~~~text
src/main/resources/application.yml
~~~

that is a source resource. When running an executable JAR, Boot reads the resource packaged at build time. Editing a source file after the build does not change an existing JAR.

At the same time, Boot can read external files:

~~~text
./config/application.yml
./config/application-staging.yml
~~~

resolved relative to the **working directory**.

### 13.1. Working Directory Is a Decisive Factor

A shell launched from `/opt/payments`:

~~~bash
cd /opt/payments
java -jar payment-gateway.jar
~~~

sees a different `./config/` than a systemd service with working directory `/srv/payment-gateway` or a Docker container with `WORKDIR /app`.

Never ask "Where is `application.yml` on this machine?" without also asking "**Which paths is this process reading?**"

### 13.2. Default External Config Locations

Spring Boot commonly inspects locations such as:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

Location groups and profile-specific files add further detail to loading order. With `spring.config.location`, the default list can be replaced. With `spring.config.additional-location`, locations are added rather than replacing the default list.

### 13.3. Checking the Wrong JAR or Image Revision

In containers/GitOps, a deployment may be running a different image digest than the Git revision a developer is viewing locally. Verify the actual image running in the Pod, not just your local branch name.

If a mounted ConfigMap changed while the process has not restarted, the filesystem and `Environment` can also reflect two different versions.

## 14. When a Profile-Specific Source Wins

Suppose there is no CLI/env override, yet:

~~~yaml
# application.yml
reports:
  export:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: staging

reports:
  export:
    enabled: true
~~~

When the `staging` profile is active and no higher source overrides it, the effective value of `reports.export.enabled` can be `true` even though the default document sets `false`.

### 14.1. Reading Actual Active Profiles

In Spring:

~~~java
String[] active = environment.getActiveProfiles();
~~~

Do not infer profiles solely from filenames in the repository. Profiles may be supplied via command line, environment, Java system properties, or test setup. A staging instance might even have multiple profiles active simultaneously if configured that way.

### 14.2. Multi-Document Ordering

In YAML, `---` separates documents. You can place:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

inside a document, and only when the profile condition matches does that document contribute properties. Within a multi-document file, later active documents can override earlier keys under Config Data rules.

However, document ordering is only part of the picture. A CLI option or environment variable can still outrank the file.

### 14.3. Do Not Activate a Profile Too Late Expecting Config Reload

Setting `spring.profiles.active` in a late-processed source such as `@PropertySource` cannot be expected to make Boot rewind to the Config Data loading phase and retroactively load skipped profile files.

This is a lesson about **loading timing** in addition to precedence.

## 15. When `spring.config.location` Changes Search Locations Entirely

Suppose operations runs:

~~~bash
java -jar payment-gateway.jar \
  --spring.config.location=optional:file:/etc/payments/
~~~

`spring.config.location` can **replace** the default search locations. As a result, a `./config/application-staging.yml` file a developer just edited may not be found by Boot as intended.

Another option:

~~~bash
java -jar payment-gateway.jar \
  --spring.config.additional-location=optional:file:/etc/payments/
~~~

typically preserves default locations and adds extra ones. Still, understand location groups and profile-specific document ordering; simply adding a location does not guarantee its keys beat CLI or env.

### 15.1. `optional` Is Not Proof of Successful Loading

`optional:` allows skipping a non-existent location in scenarios supported by Boot. It does not prove the file was present or loaded.

When an important setting comes from an optional import/location, add validation so startup fails fast if the required value ultimately ends up missing.

### 15.2. A Missing Location Can Let a Default Win

If external configuration is skipped because the file does not exist, the application can fall back to values packaged inside the JAR. Operators then see the file on the host while the JVM is not reading the right path—especially common with Docker mounts.

Verify **the path inside the process/container**, not only the host filesystem.

## 16. When `spring.config.import` Contributes Another Source

Example:

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:./overrides/payment.yml"

payments:
  client:
    timeout: 5s
~~~

Imported file:

~~~yaml
# ./overrides/payment.yml
payments:
  client:
    timeout: 2s
~~~

In Spring Boot's Config Data mechanism, imported files are processed as Config Data and carry priority rules relative to the importing document. Therefore, an imported file can override keys from the base document.

### 16.1. What Needs to Be Proven

- The document declaring `spring.config.import` was genuinely loaded by Boot.
- The import location resolved from the expected context/path.
- The imported file exists, or is legitimately marked optional.
- The matching document/profile inside the import is active.
- No higher-precedence source such as CLI/env overrides it.
- The typed bean ultimately receives the expected value.

### 16.2. Do Not Rely on a Single Grep for an Entire Import Graph

An imported file can itself import further files, and location groups carry distinct semantics. When configuration uses complex imports, map dependencies across sources and pinpoint which file actually contributes each property.

Do not write a simplistic regular-expression parser for `spring.config.import` and claim it accurately mimics Boot's loader.

## 17. Environment Variables and Relaxed Binding: An Easy Source to Miss

Spring Boot supports mapping environment variable names to canonical property names via relaxed binding rules. For example:

~~~text
Canonical property : payments.client.timeout
OS environment     : PAYMENTS_CLIENT_TIMEOUT
~~~

For many keys, however, naming conversion rules must be applied accurately. Hyphens inside canonical names, nested maps, and list indices follow specific rules.

### 17.1. A CI Environment Variable Can Override YAML

If CI or a container platform already supplies:

~~~text
PAYMENTS_CLIENT_TIMEOUT=1500ms
~~~

then editing YAML to `5s` may still not change the value received by the Binder.

Inspect deployment templates, CI variables, and the environment configuration of **the running process**. Do not look only at your local shell environment if the process is launched by systemd, Docker, or Kubernetes.

### 17.2. `System.getenv` Is Not `Environment.getProperty`

~~~java
System.getenv("PAYMENTS_CLIENT_TIMEOUT");
~~~

reads the OS process environment. Meanwhile:

~~~java
environment.getProperty("payments.client.timeout");
~~~

reads according to Spring's property-source precedence order. If CLI wins, the two values can differ without any error.

### 17.3. Value Source and Binding Timing

If Java code directly calls `System.getenv` in one place while another part uses `@ConfigurationProperties`, those two paths can observe different values. Standardize configuration delivery through Spring `Environment` and typed configuration.

## 18. Java System Properties and CLI Must Also Be Inventoried

JVM property:

~~~bash
java -Dpayments.client.timeout=1200ms \
  -jar payment-gateway.jar
~~~

CLI argument:

~~~bash
java -jar payment-gateway.jar \
  --payments.client.timeout=800ms
~~~

In standard default ordering, Spring Boot command-line arguments take precedence over Java system properties. However, an application may have disabled command-line properties via `SpringApplication` settings or added a custom `EnvironmentPostProcessor`. Always inspect application startup code.

### 18.1. JVM Option Syntax Differs from Application Argument Syntax

The `-Dname=value` option must be passed to the JVM before `-jar` in typical invocations. The `--name=value` option after the JAR name is an application argument readable by Spring Boot.

Placing them in the wrong position can prevent an intended source from taking effect.

### 18.2. Do Not Assume the Test Environment Matches Production

A `@SpringBootTest(properties=...)` annotation can add a source with different precedence than production CLI/env sources. A passing test does not prove production uses the same value unless the test simulates the exact source under verification.

## 19. `SPRING_APPLICATION_JSON` Can Be the Winning Source

Spring Boot supports passing a JSON object via `SPRING_APPLICATION_JSON`, a Java system property, or a command-line argument through the corresponding mechanism.

Example:

~~~bash
export SPRING_APPLICATION_JSON='{"payments":{"client":{"timeout":"900ms"}}}'
java -jar payment-gateway.jar
~~~

If no higher CLI override exists, JSON can beat OS environment variables and Config Data in Spring Boot's default order.

### 19.1. `null` Is Not an "Unset" Command for Lower Overrides

With:

~~~json
{
  "payments": {
    "client": {
      "timeout": null
    }
  }
}
~~~

`null` from a JSON property source is not treated as an effective override over a lower-precedence value under property-resolution semantics. Never use `null` expecting it to reliably "unset" a property already supplied by `application.yml`.

### 19.2. Do Not Put Secrets Directly into Real-World JSON Examples

Environment JSON can hold API keys or passwords, and data can leak through process/container inspection tools if permissions are misconfigured. When debugging, record only the source name and non-sensitive keys rather than dumping the entire payload.

## 20. Config Trees and File Mounts: New File on Disk, Stale Bean in Memory

In Kubernetes or Docker, a secret or config item can be mounted as a file:

~~~text
/run/config/payments.client.timeout
~~~

Containing:

~~~text
2s
~~~

Spring Boot can load it via Config Data:

~~~properties
spring.config.import=optional:configtree:/run/config/
~~~

Here the filename corresponds to the property name and the file contents provide the value.

### 20.1. Filesystem Updates Do Not Equal Hot Reload

If the mounted file changes from `2s` to `5s` while the JVM is already running:

- The filesystem view may reflect the updated file.
- Config Data loaded at startup **does not automatically re-read by default**.
- An already bound `@ConfigurationProperties` bean **does not automatically rebind by default**.
- An already constructed HTTP client **does not automatically rebuild by default**.

Therefore, if an operator opens the file inside a Pod and sees `5s` while the bean still reports `2s`, it may not be a precedence bug—it may be a **lifecycle snapshot**.

### 20.2. Kubernetes ConfigMap/Secret Env Vars vs. Volumes

- Data supplied via **environment variables** is fixed when the container is created and does not auto-update in a running process when the ConfigMap/Secret changes.
- Data supplied via **standard volume mounts** may update after propagation delay, yet Spring beans still do not auto-refresh.
- Mounts using **`subPath`** have update limitations: do not expect contents to auto-update like a regular volume mount.

An incident report must specify which layer's configuration source changed and which processes/containers were newly created.

### 20.3. Never Log Secrets from a Config Tree

If a file is named `db.password` or `partner.api.token`, never put raw values into diagnostics. For secret rotation, rely on non-sensitive version IDs, audit logs, and controlled authentication checks.

## 21. A Common Source of Confusion: `@PropertySource` Runs Too Late

A `@Configuration` class can load a properties file:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy.properties")
class LegacyPropertyConfig {}
~~~

File:

~~~properties
logging.level.root=DEBUG
spring.main.banner-mode=off
payments.client.timeout=2s
~~~

Properties such as `logging.*` and `spring.main.*` are consumed by Boot very early, before that configuration class is processed during context refresh. Consequently, even though `Environment` eventually contains a key, it may have been added **after the point** when the target component already read its value.

### 21.1. Source Exists, Yet Its Effect Arrives Too Late

This failure mode differs from having a low-precedence source:

~~~text
Is the source in Environment?                  Possibly yes.
Does lookup after refresh return the value?    Possibly yes.
Was the logging system reconfigured?           Cannot assume so.
Did SpringApplication re-read main.*?          Not by default.
~~~

When encountering bootstrap properties, check **loading timing**. The usual fix is moving such values to Config Data or an appropriately early source, rather than trying to raise `@PropertySource` priority post-refresh.

### 21.2. YAML and Multi-Document Files

`@PropertySource` by default is not equivalent to Boot Config Data for YAML, profile activation, or multi-document configuration. If a legacy file is YAML with `---` and `spring.config.activate.on-profile`, using a custom `PropertySourceFactory` solves only part of parsing and does not automatically reproduce full Config Data semantics.

## 22. Distinguishing Source-Loading Errors, Source-Selection Errors, and Binding Errors

A useful matrix:

| Layer | Symptom | Check first |
| --- | --- | --- |
| Source absent | Edited file never appears in origin/source list | Path, working directory, profile, import |
| Source present but overridden | File has the key yet effective value differs | `PropertySource` order, CLI/env |
| Wrong canonical name | YAML/env var has near-match key yet bean gets nothing | Prefix, kebab-case, relaxed binding |
| Conversion failure | Timeout like `nonsense` fails startup | `Duration` type and unit |
| Missing `@ConfigurationProperties` bean | Key exists in `Environment` yet injection fails | Scan / `@EnableConfigurationProperties` |
| Bean snapshot | `Environment` changed post-startup, bean stayed the same | Rebind / restart lifecycle |
| Client snapshot | Bean reflects new value yet old client persists | Client construction, caching/rebuild |
| Wrong timeout semantics | Config says `800ms` yet proxy read timeout triggers | Distinguish connect/request/read/total |
| Multi-instance mismatch | One request uses `800ms`, another uses `2s` | Pod identity, version, rollout |
| Sensitive source masked | Actuator hides values | Use safe evidence; never disable public masking |

### 22.1. Wrong Prefix

Code:

~~~java
@ConfigurationProperties(prefix = "payments.client")
public record PaymentClientProperties(Duration timeout) {}
~~~

But YAML:

~~~yaml
payment:
  client:
    timeout: 5s
~~~

Missing the `s` in `payments`. The YAML loader still parses cleanly, yet the key differs from the bound prefix. Changing precedence will never fix this case.

### 22.2. Conversion Failure

Value:

~~~yaml
payments:
  client:
    timeout: "very slow"
~~~

is not a valid `Duration`. Boot's Binder can report a conversion failure while constructing the properties bean. In that situation, the error log and the value's file/line origin—if supplied by the loader—serve as key evidence.

### 22.3. Nulls and Defaults

A bean with primitives can have different defaults than a nullable record, and `@DefaultValue` in constructor binding can change behavior when a key is absent. When investigating "final value is 0", distinguish among:
- The property does not exist.
- The property exists yet is subject to null semantics.
- The class has a default initializer or constructor value.
- The bean was instantiated through a mechanism that bypassed the expected binding path.

## 23. Comparing `Environment` and Bean State When They Diverge

Safe log example:

~~~text
At startup:
  effective timeout = 800ms
  bound timeout     = PT0.8S

After a manual runtime override:
  effective timeout = 2s
  bound timeout     = PT0.8S
~~~

One explanation is that a component updated `Environment` after the bean was bound without rebinding the bean. Another explanation is that the two readings came from two different instances.

Record timestamps and instance identities during measurements to avoid wrong conclusions.

### 23.1. Do Not Treat `@ConfigurationProperties` as a Live View

`@ConfigurationProperties` is an object holding values supplied by the Binder during creation/binding. An immutable record does not mutate automatically after a file is edited on disk. A mutable JavaBean does not re-invoke its setters automatically without a refresh mechanism either.

### 23.2. `@Value` Is Also Typically a Snapshot

Field/constructor `@Value` injections are generally resolved when the bean is instantiated. Calling a method on the bean after editing a file does not recalculate the annotation automatically.

### 23.3. Dynamic Refresh Is an Add-On Capability

Spring Cloud offers mechanisms such as `@RefreshScope` in compatible environments, though it is **not an automatic feature of core Spring Boot** and does not guarantee every client or pool is rebuilt. When a refresh mechanism is used, verify source reload, bean rebinding/recreation, and final runtime behavior.

## 24. Writing a Small Test to Prove Precedence

`ApplicationContextRunner` fits when testing configuration beans from specific property values without starting the full service.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PaymentClientPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PaymentClientProperties.class)
    static class Config {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(Config.class);

    @Test
    void bindsDurationFromInput() {
        runner.withPropertyValues(
                "payments.client.base-url=https://payments.example.test",
                "payments.client.timeout=800ms"
        ).run(context -> {
            var props =
                    context.getBean(PaymentClientProperties.class);
            assertThat(props.timeout())
                    .isEqualTo(Duration.ofMillis(800));
        });
    }
}
~~~

This test proves **conversion and binding**. It does not prove Spring Boot in production loaded the intended external files or CLI arguments. Testing real source ordering requires an integration test exercising the true startup pipeline or inspecting process startup.

### 24.1. `MockEnvironment` for Two Controlled Sources

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment();

env.getPropertySources().addLast(
        new MapPropertySource(
                "application-config",
                Map.of("payments.client.timeout", "5s")
        )
);

env.getPropertySources().addFirst(
        new MapPropertySource(
                "command-line-example",
                Map.of("payments.client.timeout", "800ms")
        )
);

String value = env.getProperty("payments.client.timeout");
// value = "800ms"
~~~

This tests precedence modeling using sources under your control. It does not simulate all Boot Config Data rules or OS relaxed binding.

### 24.2. End-to-End Startup Test

When verifying a real command-line override:

1. Build a Spring Boot test fixture containing typed properties.
2. Supply `application.yml` with `5s`.
3. Launch the fixture with `--payments.client.timeout=800ms`.
4. Have the fixture print one **non-sensitive allowlisted key** or expose a protected test-only probe.
5. Assert the bean holds `800ms`.
6. Remove the CLI override and re-run in a controlled environment.
7. Verify which next source wins.

For real OS environment variables, use `ProcessBuilder.environment()` on a child process. Never mutate `System.getenv` inside a JVM test using reflection.

## 25. Debugging Spring Boot Configuration: Using the Right Tool for the Job

### 25.1. `--debug` and the Auto-Configuration Condition Report

Running:

~~~bash
java -jar payment-gateway.jar --debug
~~~

prints the auto-configuration condition evaluation report. It helps explain why auto-configurations were matched or skipped, yet it **does not replace origin evidence for a specific property**.

Do not read the condition report and claim to know the value of `payments.client.timeout` without inspecting the sources.

### 25.2. Logging Config Data

In test environments, you can adjust logging for Config Data components to observe loading behavior. Logger names and verbosity vary across Spring Boot versions, and logs may reveal sensitive internal path information.

Never leave `TRACE` enabled long-term in production, and never use logging to dump all property values.

### 25.3. Actuator `info`/`health`

The health endpoint can confirm an instance is ready, yet a `200` health response does not prove the HTTP client timeout changed properly. To confirm effective configuration, inspect the typed bean or observable behavior tied to that property.

### 25.4. Distributed Tracing

A trace can show which component aborted a request after `800ms`. Combining traces with bean config and source origin distinguishes config issues from network failures or intermediary timeouts.

Never send authorization headers, cookies, or tokens inside trace attributes.

## 26. Ten-Step Workflow for Resolving a Configuration Incident

### Step 1 — Define the Symptom

Write down clearly:
- Which business flow is failing?
- When did it start?
- How many requests/instances are affected?
- What is the expected behavior?
- Is there an immediate safe rollback or mitigation?

Avoid writing "broken YAML" when all you know is that requests time out.

### Step 2 — Identify the Target Property

From code and the config contract, identify the canonical key and type:

~~~text
payments.client.timeout
Type: java.time.Duration
Consumer: PaymentClientProperties -> HttpClient.connectTimeout
~~~

If multiple timeout layers exist, list every layer.

### Step 3 — Measure the Effective Value on the Right Instance

Use `Environment.getProperty` for a non-sensitive key or a secured Actuator endpoint. Record the instance ID and timestamp.

### Step 4 — Inspect Bean Value and Resource Behavior

Read `PaymentClientProperties.timeout()` and verify whether the client consumed that bean at construction time. Distinguish connect timeout from total request timeout.

### Step 5 — Locate the Winning Source

Use property-source ordering, Actuator `env`, and origin metadata when available. Do not guess from whichever source file you happen to have open.

### Step 6 — Map the Full Precedence Chain

List every source defining the same key or related alias, with safe values and relative order. Never list only the winning source; the next source down will take over once an override is removed.

### Step 7 — Check Profiles, Locations, and Imports

Confirm active profiles, working directory, loaded files, Config Data activation, and optional imports.

### Step 8 — Check Lifecycle

Was a file edited after startup? Is there a config watcher or refresh hook? Do older and newer Pods share the same revision? Was the bean or client reconstructed?

### Step 9 — Fix the True Source and Roll Out Safely

Remove temporary overrides or fix the canonical source, validate configuration, roll out cleanly with readiness/graceful shutdown, and keep a rollback revision ready.

### Step 10 — Prove the Fix and Prevent Recurrence

Verify the effective value, typed bean, runtime behavior, metrics, and logs. Add regression tests, document config ownership, and audit deployment scripts.

## 27. Sample Incident Report

### 27.1. Summary

> Staging `payment-gateway` experienced shorter connection timeouts than expected. In the repository, `application.yml` sets `payments.client.timeout=5s`, yet the running bean received `800ms`.

### 27.2. Scope

- Environment: staging.
- Component: HTTP client connecting to Payment API.
- Start time: after a hypothetical deployment rollout.
- Instances: verify against the live Pod/VM list.
- Key: `payments.client.timeout`.

### 27.3. Evidence

| ID | Evidence | Meaning |
| --- | --- | --- |
| E1 | `application.yml` inside JAR shows `5s` | Default exists in a lower source |
| E2 | `staging` profile is active | Profile-specific Config Data is evaluated |
| E3 | External `application-staging.yml` shows `2s` | External source supplies the same key |
| E4 | Environment has `PAYMENTS_CLIENT_TIMEOUT=1500ms` | OS env supplies an override |
| E5 | Process arguments contain `--payments.client.timeout=800ms` | CLI provides a high-precedence source |
| E6 | Effective lookup returns `800ms` | `Environment` value wins |
| E7 | Bound `Duration=PT0.8S` | Binder consumes that value |
| E8 | HTTP client constructed from that bean | Connects config directly to component |

### 27.4. Root Cause

The startup script left `--payments.client.timeout=800ms` behind from a previous latency experiment. Because of precedence ordering, it overrode lower-priority YAML files and env vars. Editing the repository default had no runtime effect while the override persisted.

### 27.5. Remediation

- Remove the policy-violating CLI override.
- Clarify the canonical source managing the timeout.
- Audit any remaining env overrides before rollout.
- Update startup scripts / deployment manifests.
- Restart / rolling-update affected instances.
- Test actual timeout behavior instead of checking YAML text alone.

### 27.6. Prevention

- Review process args and Helm values whenever modifying timeouts.
- Add tests covering binding and profile-specific behavior.
- Record non-sensitive config versions in deployment metadata.
- Restrict ad-hoc CLI/CI overrides.
- Provide controlled observability for allowlisted config keys.
- Never allow debug endpoints to expose secrets.

## 28. Another Case: Right File, Never Loaded

Suppose:

~~~text
Host file: /srv/payment/config/application.yml
JVM cwd:   /app
Expected:  /app/config/application.yml
~~~

An operator edits the file on the host, yet the Pod runs inside a container whose volume mount points elsewhere—or has no volume mount at all.

Evidence:

- Host file specifies `5s`.
- Container filesystem lacks a file at the location Boot checks.
- `Environment` shows no origin referencing that file.
- The bean uses the JAR default `2s`.

Root cause is not precedence between two sources. It is a **path/mount mismatch** preventing the new source from being read at all.

### Resolution

- Confirm working directory and container mount paths.
- Use `spring.config.additional-location` or an explicit import where needed.
- Ensure the file exists inside the filesystem visible to the JVM.
- Restart the instance once the source is in place.
- Confirm origin pointing to the right file/path on the new instance.

Never just bump the number inside a file located at the wrong path.

## 29. Third Case: Profile Not Active

File:

~~~yaml
# application-prod.yml
feature:
  payments:
    strict-validation: true
~~~

Yet the application runs with the `staging` profile. `strict-validation=true` from `application-prod.yml` does not take effect.

Evidence:

- `Environment.getActiveProfiles()` does not include `prod`.
- `application-prod.yml` Config Data is not activated for that profile.
- Effective value comes from defaults or another source.
- No YAML syntax error necessarily occurs.

Root cause: **editing configuration for an inactive profile**.

Fix the source/profile actually in use or activate the intended profile per deployment policy. Never casually turn on `prod` in staging just to pick up one setting, as that profile can pull in many unintended changes.

## 30. Fourth Case: `Environment` Is Right, Yet Client Keeps Old Value

Suppose:

~~~text
T0: Bean binds with timeout 2s.
T1: HTTP client is constructed with timeout 2s.
T2: Custom logic prepends a high-precedence MapPropertySource with timeout 5s.
T3: Environment.getProperty() returns 5s.
T4: Existing HTTP client still uses 2s.
~~~

The defect sits in **binding/client lifecycle**, not ordinary file-source precedence.

### Resolution

- For startup-only configuration, restart/recreate the process.
- If dynamic refresh is needed, redesign loading, validation, rebinding, and client reconstruction end to end.
- Determine whether in-flight requests continue using the old snapshot.
- Verify all replicas and rollback behavior.

Do not patch `Environment` by inserting another property source and assume the live client updated automatically.

## 31. Fifth Case: Effective Value Is Right, Yet Timeout Semantics Differ

`PaymentClientProperties.timeout()` reports `5s`. Operators still see requests fail after `800ms` because of:

- A load balancer or gateway enforcing its own timeout.
- Connect timeout differing from total request timeout.
- A different `HttpRequest.timeout` set per request.
- A shorter circuit breaker or retry budget.
- Caller cancellation or an upstream deadline.
- Socket/read timeout inside another client library.

In this case, the configuration source is already accurate; expand investigation to **the multi-layer timeout contract** and distributed traces. Simply raising `payments.client.timeout` may not resolve the failures.

This is the final check on reasoning: **provenance explains where a value came from**, while business root cause connects that value to the component actually triggering the failure.

## 32. Preserving Evidence Without Exposing Secrets

An incident may require collaboration across multiple teams. An evidence package should include:

- Non-sensitive key names.
- Instance/revision identifiers and timestamps.
- Active profiles.
- Shareable source names and origin metadata.
- Verified non-sensitive scalar values.
- Bound typed bean values if non-sensitive.
- Redacted error logs and traces.
- Diffs of startup args or deployment manifests with tokens masked.
- Change decisions, owners, and rollout verification results.

Exclude:

- Passwords and API tokens.
- Full `System.getenv()` dumps.
- Raw Secret files or `SPRING_APPLICATION_JSON` payloads carrying credentials.
- TLS private keys.
- Connection URLs containing usernames/passwords in query parameters.
- Unreviewed Actuator `env` output.

### 32.1. Often Presence Suffices Instead of the Value

For sensitive keys, instead of logging:

~~~text
partner.api.token = <raw token>
~~~

log something like:

~~~text
partner.api.token: present
source: approved secret provider
secret version: v17 (non-sensitive identifier)
~~~

Only record a secret version ID when the secret management system actually provides one and policy permits showing it.

## 33. Common Mistakes

| Mistake | Why it is wrong | Better approach |
| --- | --- | --- |
| "`application.yml` says 5s, so the app uses 5s" | Higher sources, profiles, and imports exist | Check effective value and winning source |
| "Whichever file was edited last wins" | Precedence does not follow timestamps | Inspect `PropertySource` order |
| "Checking `source.getName()` gives the line origin" | Source name and origin metadata differ | Use origin tracking when supported |
| "Actuator `env` always prints values" | Masking/sanitization policies apply | Never disable safeguards carelessly |
| "Env vars cannot match dotted keys" | Relaxed binding can map them | Verify naming rules |
| "`getProperty` null on one raw source means Binder misses it" | Canonical adaptation differs from raw lookup | Inspect effective binding |
| "External YAML outside the JAR always loads" | Working directory/location/import may mismatch | Verify actual loaded sources |
| "`optional:file:` means the file exists" | `optional` merely permits absence | Verify path and validation |
| "Adding a CLI override fixes the root cause" | It merely masks the bad source | Fix the canonical source |
| "Editing a ConfigMap updates running Pods immediately" | Env snapshots and bean lifecycle block live changes | Trigger rollout or controlled rebind |
| "Changing `Environment` changes beans and clients" | Beans and resources are usually startup snapshots | Restart or implement explicit refresh |
| "Active profile equals the CI environment label" | Check profiles inside the live process | Read `activeProfiles` |
| "`@PropertySource` controls early bootstrap settings" | Processed relatively late | Use Config Data / early sources |
| "`--debug` prints full property origins" | It mainly prints the condition report | Inspect env, sources, and origin directly |
| "Right bean value proves network timeouts come from it" | Multiple timeout layers exist | Verify runtime behavior and traces |
| "One healthy Pod means the whole deployment matches" | Replicas may run skewed revisions | Check every instance |

## 34. Hands-On Exercises

### Exercise A — Tracing `800ms`

Use all five configuration sources from Section 3. Predict the effective value. Then remove the CLI argument, environment variable, and external file one by one across separate startups. Record which next source wins in each run and explain the precedence.

### Exercise B — Collecting Provenance Evidence

Add a probe reading only `payments.client.timeout`, listing `PropertySource` names and the effective value. When Config Data sources include origin metadata, record the non-sensitive file/line. Compare against the `@ConfigurationProperties` bean.

### Exercise C — Working Directory Mismatch

Place `application.yml` under `./config`. Launch the app from two different working directories. Compare the loaded sources. Use an explicit location setting to resolve the unfound file case.

### Exercise D — Profile-Specific Documents

Set `feature.payments.strict-validation` differently across default, `staging`, and `prod`. Run with each profile. Next try adding a CLI override and explain why that source wins.

### Exercise E — `spring.config.import`

Create an imported file `./overrides/payment.yml` with timeout `2s` and an application file with timeout `5s`. Observe import precedence behavior. Try deleting the file with and without `optional:` and compare startup failures.

### Exercise F — Relaxed Binding

For `payments.client.timeout`, pass `PAYMENTS_CLIENT_TIMEOUT=1500ms` via child-process environment variables or container config. Compare `Environment.getProperty` with `System.getenv`. Never mutate the test JVM's OS environment via reflection.

### Exercise G — Runtime `Environment` Changes

Build a context with timeout `2s` and instantiate the bean/client; then prepend a `MapPropertySource` with `5s`. Compare effective lookup, bound bean, and client behavior. Explain why they can differ.

### Exercise H — Distinguishing Connect and Request Timeouts

Use Java `HttpClient` with `connectTimeout` and per-request `HttpRequest.timeout`. Build a controlled mock HTTP server with configurable delay. Verify which timeout aborts the request. Never target a public payment provider.

### Exercise I — Kubernetes ConfigMaps

Provide a ConfigMap via env var and via volume mount in a sandbox cluster. Update the ConfigMap while the Pod is running; observe the mounted filesystem, process env, bound bean, and post-rollout behavior. Never use production secrets.

### Exercise J — Writing an Incident Report

Given this evidence:
- File inside JAR shows `5s`.
- `staging` profile is active.
- External YAML shows `2s`.
- Env shows `1500ms`.
- CLI shows `800ms`.
- Bean holds `PT0.8S`.

Write a report covering symptom, evidence chain, root cause, remediation, verification, and prevention. Explicitly identify which source wins **once only the CLI flag is removed**.

## 35. Pre-Closure Incident Checklist

### Source Verification

- [ ] Exact artifact/image revision and instance identified.
- [ ] Startup args and JVM flags verified after redacting secrets.
- [ ] Active profiles, working directory, and config locations verified.
- [ ] Config Data imports and active documents checked.
- [ ] OS environment, system properties, JSON, and CLI checked for related keys.
- [ ] Canonical key name and relaxed binding rules confirmed.

### Value Verification

- [ ] Effective `Environment` value measured.
- [ ] Winning source and lower-precedence sources identified.
- [ ] Actual source name and origin metadata captured if available.
- [ ] Cross-checked against the `@ConfigurationProperties` bean.
- [ ] Verified how client, connection pool, or scheduler consumes the value.
- [ ] Checked binding timing, restart/refresh needs, and replica consistency.

### Remediation and Verification

- [ ] True source fixed rather than stacking another override.
- [ ] Relevant owners and deployment scripts updated.
- [ ] YAML/properties syntax and validation verified.
- [ ] Appropriate rollout/restart or refresh mechanism executed.
- [ ] Confirmed all instances run the intended revision.
- [ ] Measured live component behavior after the change.
- [ ] Retained rollback capability for both image and config if needed.
- [ ] Regression tests or guardrails added.
- [ ] Evidence and logs scrubbed of secrets.

## 36. Conclusion: Every Value Has a Source, Lifecycle, and Consumer

When a Spring Boot property "does not match the file," do not rush to call it a framework bug. Trace a verifiable chain:

~~~text
Source on filesystem / deployment platform
             |
             v
Config Data / OS env / JVM / CLI
             |
             v
PropertySource order and origin
             |
             v
Effective Spring Environment value
             |
             v
Binder / @ConfigurationProperties / @Value
             |
             v
Constructed bean / client and its lifecycle
             |
             v
Observed request / transaction behavior
~~~

In the case study, failure stemmed from a leftover **800ms CLI override**. The `5s` in `application.yml` was not wrong—it simply was not the highest-precedence source. Removing the CLI flag while leaving `PAYMENTS_CLIENT_TIMEOUT=1500ms` intact would shift the application to **1500ms**, not automatically back to `5s`.

A complete investigation answers four questions:

1. **Which value is effective?**
2. **Which source provided it, and does origin metadata corroborate it?**
3. **Which component actually consumed that value?**
4. **What must be changed and verified for a durable fix?**

Answering only questions 1 and 2 completes **value-provenance tracing**. Closing the incident safely also requires verifying **binding, resource lifecycle, and business behavior**.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `PropertySources` list, precedence, Config Data, profile-specific sources, and imports.
- [Spring Boot Reference — External Application Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files): classpath/external locations, profile-specific documents, and location groups.
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import`, optional imports, and Config Trees.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): Binder, relaxed binding, constructor binding, and validation.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`, `configprops`, security, exposure, and value sanitization.
- [Spring Boot API — Origin](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/Origin.html): representation of configuration origins.
- [Spring Boot API — OriginLookup](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/OriginLookup.html): querying origin metadata when supported.
- [Spring Framework API — ConfigurableEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html): managing `PropertySources` and reading `Environment`.
- [Spring Framework API — PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html): distinguishing source name, property lookup, and source order.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): env vs. mounted config, updates, and limitations.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): secret sources, volumes, and protection requirements for sensitive data.
