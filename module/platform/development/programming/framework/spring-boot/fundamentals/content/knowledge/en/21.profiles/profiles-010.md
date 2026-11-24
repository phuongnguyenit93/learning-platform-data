# Verifying the actually effective profile and avoiding environment mix-ups

A Spring Boot application can use the exact same JAR file on a developer's machine, in testing, staging, and production. Code stays almost unchanged, while databases, endpoints, credentials, logging, and integration beans can differ. **Spring Profiles** help select configuration groups and beans per environment.

However, seeing the string **prod** in application.yml or seeing **application-prod.yml** on disk **is not enough to conclude the process is actually running with the prod profile**. Conversely, an application reporting that the prod profile is active does not prove that every URL, datasource, and bean comes from production configuration either.

To avoid mixing up environments, you must verify three layers:

1. **Active profiles:** which profiles does Spring Environment actually treat as active?
2. **Effective configuration:** what are the final values of critical properties, and which source did they come from?
3. **Effective beans:** are beans guarded by @Profile or other conditions actually registered properly?

This lesson guides you through verifying all three layers, explaining default profiles, multiple simultaneous profiles, profile groups, Config Data, testing, and how to handle deployment environments that do not match expectations.

## 1. A profile is a logical name, not proof of the environment

Common names:

- **local**: personal machine.
- **dev**: shared development environment.
- **test**: testing environment or scenario.
- **staging**: pre-production environment.
- **prod**: production environment.

Names are chosen by the project. Spring does not treat **production**, **prod**, **live**, and **release** as synonyms. With @Profile("prod"), only a profile named prod matches, unless the project explicitly adds a linking mechanism like a profile group.

Spring Profiles let you:

- Load profile-conditional configuration documents.
- Enable/disable beans or configuration classes annotated with @Profile.
- Add profiles via include or group.
- Separate certain deployment decisions by environment.

Profiles do not automatically:

- Verify that a database or URL belongs to the right environment.
- Prove that secrets have been loaded and are valid.
- Prevent a bean from accidentally calling a production API.
- Replace authentication, authorization, or configuration validation.
- Automatically refresh beans when an operator edits a YAML file.

A process with active profile prod can still receive a **localhost** URL from a higher-precedence environment variable. Therefore, an active profile is a **fact to verify**, not a final guarantee.

## 2. Three levels of evidence to cross-check

Example email-sending application:

~~~text
Running process
        │
        ├── Spring Environment
        │      Active profiles: [prod]
        │
        ├── Effective configuration
        │      app.mail.host = smtp.production.internal
        │      app.mail.enabled = true
        │
        └── Actual bean
               MailSender = SmtpMailSender
~~~

If the result instead turns out to be:

~~~text
Active profiles: [prod]
app.mail.host = localhost
MailSender = LoggingMailSender
~~~

then you must find **why** the values and bean do not match expectations: configuration was overridden, the @Profile condition is wrong, there is another @ConditionalOnProperty, or the application registered a replacement bean on its own.

Rely on the **actual process in the target environment**, not merely reading files sitting in the source repository.

## 3. Activating profiles with spring.profiles.active

In application.properties:

~~~properties
spring.profiles.active=dev
~~~

Or in application.yml:

~~~yaml
spring:
  profiles:
    active: dev
~~~

When Boot uses this value, dev is activated and configurations meant for dev can be evaluated.

### 3.1. Via command line

~~~bash
java -jar app.jar --spring.profiles.active=staging
~~~

With Spring Boot's default property sources, command-line options typically have higher precedence than values in application.yml, so they can override profiles set in files.

Multiple profiles:

~~~bash
java -jar app.jar --spring.profiles.active=prod,metrics
~~~

This command does not only pick prod: metrics is activated too.

### 3.2. Via environment variable

Common variable name:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Linux shell example:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
~~~

In containers, variables can come from Docker, a Kubernetes Deployment, ConfigMap, or pipeline. **A variable in a developer's terminal does not prove the variable inside the running process on the cluster has the same value.** Inspect the exact deployment/runtime process being diagnosed.

### 3.3. Via JVM system property

~~~bash
java -Dspring.profiles.active=prod -jar app.jar
~~~

Distinguish the two forms:

~~~text
java -Dspring.profiles.active=prod -jar app.jar
     └── JVM system property before -jar

java -jar app.jar --spring.profiles.active=prod
                  └── Spring Boot application argument
~~~

If you put **-Dspring.profiles.active=prod** after the JAR name, the JVM does not process it as a system property under that syntax; it becomes an application argument.

### 3.4. Via SpringApplication API

~~~java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.setAdditionalProfiles("diagnostics");
app.run(args);
~~~

**setAdditionalProfiles** adds a profile before running; it does not erase profiles coming from other sources. This is one reason not to read just the spring.profiles.active string to conclude which profiles are in use.

## 4. The right way to read active profiles from the context

Spring provides **Environment**:

~~~java
String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
~~~

Startup logging example:

~~~java
package com.example.demo.diagnostics;

import java.util.Arrays;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileStartupLogger implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ProfileStartupLogger.class);

    private final Environment environment;

    public ProfileStartupLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles()));
        log.info("Default profiles: {}",
                Arrays.toString(environment.getDefaultProfiles()));
    }
}
~~~

ApplicationRunner executes after the ApplicationContext finishes refreshing and before ApplicationReadyEvent. This is a convenient point to record the state of a process that has started along the normal flow.

If startup fails before the runner, this log may not appear. In that case, inspect startup logs, command line, property sources, and container configuration.

### 4.1. Do not equate getProperty with getActiveProfiles

Two different APIs:

~~~java
String declared = environment.getProperty("spring.profiles.active");
String[] actual = environment.getActiveProfiles();
~~~

**declared** is the resolved value of a single property; **actual** is the set of active profiles known to Environment. Include, groups, additional profiles, and valid changes during Environment preparation can make the actual set broader than a single property string.

**Prefer getActiveProfiles() when the goal is checking which profiles are truly active.** Then inspect property sources to trace why.

### 4.2. Do not log the entire Environment or secrets

Log profile names, bean names, and selected **curated** configuration values. Never print all environment variables, datasource passwords, API tokens, or sensitive configuration into startup logs.

Especially in production, diagnostic logs are often aggregated into long-term storage systems. Printing a secret in logs once can create a larger security risk than the debugging value gained.

## 5. Active profiles and default profiles are not the same

Spring has the concept of a **default profile** used when there are no explicit active profiles. Usually its name is **default**.

If getActiveProfiles() returns an empty array, Spring can still apply **@Profile("default")** because the default profile matches.

| Active profiles | Default profiles | Matching profiles in the typical case |
|---|---|---|
| None | default | default |
| dev | default | dev |
| prod | default | prod |
| prod,metrics | default | prod and metrics |

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("default")
public class DefaultOnlyConfiguration {

    @Bean
    LocalMessageGateway localMessageGateway() {
        return new LocalMessageGateway();
    }
}
~~~

This bean belongs to the default profile, which does not mean it is always used if prod is active.

### 5.1. Default profile can be changed

~~~yaml
spring:
  profiles:
    default: local
~~~

When there is no active profile, Spring can use local as the default. If prod is active, local does not automatically become active just because it was declared default.

Spring Boot also supports **spring.profiles.default=none** to avoid using a specific default profile name.

In multi-environment systems, set the target profile **explicitly from deployment** rather than relying on a default profile that different processes might configure differently.

### 5.2. Avoid inferring "empty active array = no configuration"

Wrong:

~~~java
if (environment.getActiveProfiles().length == 0) {
    // Concluding no profile is in effect.
}
~~~

The conclusion above ignores default profiles. If you need to ask whether a profile expression matches, you can use:

~~~java
boolean localMatches =
        environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("local"));
~~~

The acceptsProfiles method with a Profiles expression checks active profiles or default profiles under Spring rules. It is suitable for asking whether **a condition** is satisfied, not a substitute for logging both active and default profiles during diagnosis.

## 6. Profile-specific configuration: file existing does not mean effective

A project can have:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
~~~

Example application.yml:

~~~yaml
app:
  gateway:
    url: https://gateway.default.internal
  audit:
    enabled: false
~~~

application-dev.yml:

~~~yaml
app:
  gateway:
    url: http://localhost:8090
~~~

application-prod.yml:

~~~yaml
app:
  gateway:
    url: https://gateway.production.internal
  audit:
    enabled: true
~~~

When prod is active, Spring Boot can load application-prod.yml to override some keys from application.yml according to Config Data precedence rules.

You must distinguish:

- A file existing does not mean it was loaded.
- A file being loaded does not mean all its keys beat other sources.
- Profile prod being active does not mean application-prod.yml necessarily exists.
- A property having a production value does not prove a bean actually used that property.

If application-prod.yml is missing, the prod profile can still be active and the application uses values from other sources. Thus you must check actual values.

### 6.1. Profile-specific documents in YAML

Besides separate files, multiple documents can be used:

~~~yaml
app:
  gateway:
    url: https://gateway.default.internal

---
spring:
  config:
    activate:
      on-profile: dev
app:
  gateway:
    url: http://localhost:8090

---
spring:
  config:
    activate:
      on-profile: prod
app:
  gateway:
    url: https://gateway.production.internal
~~~

**spring.config.activate.on-profile** is a condition for applying a document. It **does not activate** the profile written in it.

For example, on-profile: prod means "only use this document if prod matches", unlike spring.profiles.active=prod which means "set profile prod as active".

### 6.2. Do not activate profiles from a profile-only document

Do not do:

~~~yaml
spring:
  config:
    activate:
      on-profile: staging
  profiles:
    active: prod
~~~

Properties controlling profile activation such as **spring.profiles.active**, **spring.profiles.default**, **spring.profiles.include**, and **spring.profiles.group** should be placed in valid locations that are **not** profile-specific documents or documents already depending on on-profile.

Do not design a document that loads only when staging is active and then tries to enable prod itself; that creates a circular dependency and is restricted by Spring Boot configuration rules.

## 7. Multiple profiles can be active together

~~~bash
java -jar app.jar --spring.profiles.active=dev,prod
~~~

In this case:

- @Profile("dev") can match.
- @Profile("prod") can match.
- Both dev and prod profile-specific configurations can be evaluated.
- If two sources define the same key, config data precedence rules decide the final value.

Spring does not automatically treat dev and prod as mutually exclusive choices.

### 7.1. Profile order can change values

Suppose application-dev.yml and application-prod.yml both contain **app.gateway.url**. Within a profile-specific config data group at the same precedence level, **a profile listed later can win** when overriding the same key:

~~~text
spring.profiles.active=dev,prod
spring.profiles.active=prod,dev
~~~

Reversing the order can flip the resulting value. However, higher-precedence property sources, such as command-line properties, can still override them.

Therefore, a proper verification process must observe **both profile order and property values after all sources are merged**.

### 7.2. Avoid similar-looking profile names

~~~text
prod
production
live
release
~~~

These are all different names. Standardize naming conventions across source code, manifests, CI/CD, and operational documentation.

## 8. Include and profile groups

Spring Boot can add active profiles via include or groups. The actual profile set can be broader than the names entered on the command line.

### 8.1. spring.profiles.include

Example declaration in root configuration:

~~~yaml
spring:
  profiles:
    include:
      - common-observability
      - region-south
~~~

Included profiles are added to the active profiles set according to Spring Boot rules. A process selecting prod can also carry common-observability and region-south.

This is why **environment.getActiveProfiles()** is more authoritative data than inspecting spring.profiles.active alone.

### 8.2. Profile groups

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-datasource
        - prod-observability
        - prod-security
~~~

When the production profile is activated, Spring Boot can activate the group's member profiles as well.

Profile groups are useful when one environment name represents multiple configuration slices. However, when an incident occurs, inspect every member because a profile might be added indirectly.

### 8.3. Place include/group in valid locations

Properties controlling profile selection should be declared in a configuration document not conditioned by a profile. Do not place them in application-prod.yml or a YAML document with spring.config.activate.on-profile expecting them to chain-add profiles automatically.

### 8.4. Each profile does not equate to a separate environment

A profile can represent a configuration dimension such as:

- cloud.
- metrics.
- region-south.
- debug-sql.

Thus a valid production application can have multiple profiles. What to avoid are **conflicting profiles**, such as local-mock alongside prod-real, or profiles sharing keys with incompatible values.

## 9. Verifying whether @Profile selects the right beans

Spring Profiles affect both configuration and bean registration.

Interface example:

~~~java
public interface MessageGateway {
    void send(String message);
}
~~~

Two implementations:

~~~java
public class LoggingMessageGateway implements MessageGateway {
    @Override
    public void send(String message) {
        System.out.println("LOCAL: " + message);
    }
}
~~~

~~~java
public class RemoteMessageGateway implements MessageGateway {
    @Override
    public void send(String message) {
        // Send message to external service.
    }
}
~~~

Configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class MessageGatewayConfiguration {

    @Bean
    @Profile("local")
    MessageGateway localMessageGateway() {
        return new LoggingMessageGateway();
    }

    @Bean
    @Profile("prod")
    MessageGateway remoteMessageGateway() {
        return new RemoteMessageGateway();
    }
}
~~~

If local matches, the localMessageGateway bean can appear. If prod matches, the remoteMessageGateway bean can appear. However:

- If **no profile matches**, there may be no MessageGateway bean; a consumer requiring type injection will fail.
- If **both local and prod are active**, both @Bean methods can match, producing multiple MessageGateway candidates and causing ambiguity on injection.

Do not treat profile names as a guarantee that only one implementation is created. Define allowed profile combinations alongside bean selection rules.

### 9.1. @Profile on a configuration class

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionMessagingConfiguration {

    @Bean
    MessageGateway remoteMessageGateway() {
        return new RemoteMessageGateway();
    }

    @Bean
    RemoteMetrics remoteMetrics() {
        return new RemoteMetrics();
    }
}
~~~

If prod does not match, this configuration class is not applied, so the beans inside the class are not registered through that branch. A class-level condition has broader scope than a condition on a single @Bean method.

### 9.2. Profile lists and expressions

~~~java
@Profile({"dev", "staging"})
~~~

The condition above matches if **dev OR staging** matches.

~~~java
@Profile("prod & cloud")
~~~

The expression requires **prod AND cloud**.

~~~java
@Profile("!prod")
~~~

The expression requires **prod not matching**. However, **!prod does not mean dev**: it can match in staging, test, or a deployment that was not assigned a proper profile.

If a mock bean could impact real data, do not guard it with an overly broad negated condition. Explicitly select allowed profiles and add safety constraints.

### 9.3. Reading the bean registry to verify

An ApplicationRunner can inspect bean names:

~~~java
import java.util.Map;
import org.springframework.beans.factory.ListableBeanFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class GatewayInspector implements ApplicationRunner {
    private final ListableBeanFactory factory;

    public GatewayInspector(ListableBeanFactory factory) {
        this.factory = factory;
    }

    @Override
    public void run(ApplicationArguments args) {
        Map<String, MessageGateway> gateways =
                factory.getBeansOfType(MessageGateway.class);
        System.out.println("Gateway beans: " + gateways.keySet());
    }
}
~~~

In production, prefer a controlled logger. Printing bean names and implementation types is safer than printing entire objects in case a client's toString accidentally contains credentials.

Conclusions about the environment must rest on **actually registered beans**, not solely on annotations seen in source code.

## 10. Active profile and effective property value are two separate questions

Suppose application-prod.yml contains:

~~~yaml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Yet the process runs:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.payment.endpoint=http://localhost:9000
~~~

With default property sources, the app.payment.endpoint argument can override the value inside application-prod.yml. The profile is still prod, yet the effective endpoint is localhost.

Hence, the following log does not prove a production connection:

~~~text
The following 1 profile is active: "prod"
~~~

### 10.1. Reading resolved properties

~~~java
String endpoint =
        environment.getProperty("app.payment.endpoint");
~~~

Or inspect the bound object:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String endpoint,
        boolean sandboxEnabled) {
}
~~~

When the type is registered via @ConfigurationPropertiesScan or @EnableConfigurationProperties, you can inject the bean:

~~~java
@Component
public class PaymentConfigurationInspector
        implements ApplicationRunner {

    private final PaymentProperties properties;

    public PaymentConfigurationInspector(
            PaymentProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Payment endpoint: "
                + properties.endpoint());
        System.out.println("Sandbox enabled: "
                + properties.sandboxEnabled());
    }
}
~~~

Inspecting the properties bean confirms the relaxed binding and conversion results consumed by code. Still verify whether the specific service uses that bean or another configuration.

### 10.2. Properties can come from many sources

- Default values in code or property definitions.
- application.yml or application.properties.
- Profile-specific files or YAML documents.
- Config data imported via spring.config.import.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Property sources added by infrastructure or tests.

Spring Boot has precedence rules per source. You cannot deduce from a line appearing in application-prod.yml that it is the effective value.

**Check the final property and winning source inside the process.**

## 11. Tracing the PropertySource supplying a value

With **ConfigurableEnvironment**, you can iterate through PropertySources:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class PropertySourceInspector {

    public static void showCandidateSources(
            ConfigurableEnvironment env,
            String key) {

        System.out.println("Effective value: "
                + env.getProperty(key));

        for (PropertySource<?> source : env.getPropertySources()) {
            if (source.containsProperty(key)) {
                System.out.println("Candidate source: "
                        + source.getName());
            }
        }
    }
}
~~~

Example:

~~~java
PropertySourceInspector.showCandidateSources(
        environment, "app.payment.endpoint");
~~~

Normally, PropertySources are checked in precedence order and the first source supplying a suitable value determines the outcome. However, the code above is only a **candidate source observer**, not a complete origin tracer for all forms of relaxed binding, placeholders, or special property sources.

For instance, APP_PAYMENT_ENDPOINT in the environment can be mapped by Binder to app.payment.endpoint under environment variable naming rules. Calling containsProperty on an individual source does not by itself prove Boot's full binding process.

When you need to determine the exact origin, combine Effective Environment, ConfigurationProperties beans, Actuator, and Config Data logging.

### 11.1. Distinguishing three categories of errors

| Symptom | Diagnostic direction |
|---|---|
| Profile missing from getActiveProfiles() | Check launch command, environment, include, and groups. |
| Profile right yet property wrong | Check Config Data, higher-precedence property sources, imports, and prefixes. |
| Property right yet bean wrong | Check @Profile, component scan, bean conditions, @Primary/@Qualifier, and auto-configuration. |

### 11.2. Never log secrets

For keys such as datasource passwords, API tokens, or private keys, never use debug examples to print values to logs.

You can check the **presence** of a property at a non-sensitive level:

~~~java
boolean configured =
        environment.containsProperty("app.payment.api-key");
~~~

However, presence does not prove the credential is still valid. If you need to verify connectivity, use health checks or safely designed functional checks.

## 12. Using Spring Boot Actuator to observe

When Actuator is present and endpoints are enabled/exposed, the following endpoints are useful:

| Endpoint | Purpose |
|---|---|
| **/actuator/env** | Inspect active profiles and supported property sources/origins. |
| **/actuator/configprops** | Inspect configuration properties beans and binding data per Actuator rules. |
| **/actuator/beans** | View beans currently in the ApplicationContext. |
| **/actuator/conditions** | View the Condition Evaluation Report for auto-configuration. |
| **/actuator/health** | View health per configured contributors. |

Illustrative example for an **access-controlled administrative environment**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,beans,conditions
~~~

**Do not expose these sensitive endpoints publicly in production.** Configure authentication, authorization, redaction, and an administrative network appropriately. Even when Actuator masks certain values, metadata can still reveal infrastructure topology.

### 12.1. /actuator/env

Use to view the active profiles set and information about property values/origins when supported. If two sources both define a key, verify **which source actually won**, not merely that the key appears in one source.

### 12.2. /actuator/configprops

Helps observe `@ConfigurationProperties` binding. If YAML has a key yet the properties bean still uses defaults, check prefix, field names, conversion, and registration.

### 12.3. /actuator/conditions and @Profile

The conditions endpoint is useful for auto-configuration when `@ConditionalOnClass`, `@ConditionalOnBean`, or `@ConditionalOnProperty` match or do not match.

However, **do not assume this report fully explains every `@Profile` condition in your source**. To know whether a profile-specific bean exists, cross-check active profiles with the bean registry or `/actuator/beans`.

## 13. Checking Config Data via startup logs

Spring Boot normally logs active profiles at startup. For example:

~~~text
The following 1 profile is active: "prod"
~~~

Or when only the default profile applies:

~~~text
No active profile set, falling back to 1 default profile: "default"
~~~

Exact wording can vary by version. If startup fails before the runner, you might not see custom ApplicationRunner logs; inspect Spring Boot's own logs and the runtime environment.

### 13.1. Tracing configuration loading

When you need to find which files were processed:

~~~properties
logging.level.org.springframework.boot.context.config=TRACE
~~~

Or enable temporarily at launch:

~~~bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
~~~

TRACE can generate very verbose logs, so use it only while diagnosing. Do not keep TRACE enabled long-term in production without need and proper log management.

### 13.2. --debug does not prove every profile file won

~~~bash
java -jar app.jar --debug
~~~

Debug mode can display the Condition Evaluation Report and startup details. However, it does not replace reading final property values and the origin of critical keys.

## 14. Configuration outside the JAR can alter results

An application can load configuration from:

- Default search paths.
- Profile-specific files.
- spring.config.location or spring.config.additional-location.
- spring.config.import.
- Environment variables, system properties, and command line.

Example:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-app/
~~~

If a configuration file exists under the added location, Boot can use it under Config Data rules. Do not read only application-prod.yml inside the JAR when the deployment also mounts external configuration.

### 14.1. location and additional-location differ

By design:

- **spring.config.location** selects configuration locations in a way that replaces Config Data's default locations.
- **spring.config.additional-location** adds locations alongside the default locations.

Confusing these two options can stop a file inside the JAR from being loaded as expected. When troubleshooting, examine location order, location groups, and final values.

### 14.2. Config imports must also be checked

~~~yaml
spring:
  config:
    import: optional:file:/etc/my-app/extra.yml
~~~

This is an example of importing an external configuration file. When the file exists, it can add or override properties under Config Data rules. **optional:** permits skipping a missing location under supported mechanisms.

If a property unexpectedly changes value, check config imports rather than only profile-specific files.

## 15. Verifying the right process in a container or cluster

When an application runs via Docker/Kubernetes, configuration seen by developers in the repository can differ from the real process's environment.

~~~text
Repository contains application-prod.yml
                │
                ▼
Build image and deploy
                │
                ▼
Deployment mounts env, ConfigMap, Secret, volume
                │
                ▼
JVM receives args and system properties
                │
                ▼
Spring Boot builds Environment
                │
                ▼
Actual Active profiles / Effective values / Beans
~~~

A manifest file in Git does not prove the deployment rolled out. There may be old pods, different config mounts, different image digests, or replicas running two versions.

Observation process:

1. Identify the instance serving requests.
2. Check that instance's version/image digest and startup command.
3. Confirm environment variables passed into the process, especially SPRING_PROFILES_ACTIVE.
4. Check config volume paths and non-sensitive mounted files.
5. Read startup logs from the exact instance.
6. Query protected internal diagnostics to verify active profiles and effective values.
7. If there are multiple replicas, compare results across multiple instances, not just one pod.

Illustrative Kubernetes commands:

~~~bash
kubectl -n demo describe deployment demo-api
kubectl -n demo logs deployment/demo-api
~~~

Namespace and workload names are illustrative only. Never share output containing tokens, passwords, or Secret values.

### 15.1. Errors occurring on only some requests

You might have:

~~~text
pod-a: active = [prod], payment endpoint = production
pod-b: active = [prod], payment endpoint = staging
pod-c: active = [prod], payment endpoint = production
~~~

The issue is not in the profile name, but in actual configuration differences across replicas. Inspect rollout status, mounted configs, restart times, and each process's property sources.

## 16. Testing profiles with @ActiveProfiles

In Spring Test, the **@ActiveProfiles** annotation lets you specify profiles for the test ApplicationContext.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class TestProfileIntegrationTests {

    @Autowired
    Environment environment;

    @Test
    void runsWithExpectedProfile() {
        assertThat(environment.getActiveProfiles())
                .contains("test");
    }
}
~~~

In this test, Spring Test prepares the context with the test profile. However, the test verifies only part of the picture: that the test profile is enabled. It does not prove the test database or mock bean was selected.

To prove that, verify **configuration values and beans**:

~~~java
@SpringBootTest(properties = {
        "app.mail.host=smtp.test.internal"
})
@ActiveProfiles("test")
class MailEnvironmentIntegrationTests {

    @Autowired Environment environment;
    @Autowired MailSender sender;

    @Test
    void usesTestConfiguration() {
        assertThat(environment.getActiveProfiles())
                .contains("test");
        assertThat(environment.getProperty("app.mail.host"))
                .isEqualTo("smtp.test.internal");
        assertThat(sender).isInstanceOf(FakeMailSender.class);
    }
}
~~~

In the example, MailSender/FakeMailSender are illustrative types registered by the test application. If FakeMailSender does not exist in the test context, the assertion fails. Such a failure is valuable because the test verifies **real wiring**, not just profile names.

### 16.1. @ActiveProfiles does not necessarily represent production

A test with @ActiveProfiles("test") only shows how the **test context** was created. It does not prove the production process runs with the same profiles or property sources.

In addition, @SpringBootTest can trigger unwanted auto-configurations, runners, or external clients. Use mocks/stubs or appropriate test configurations to ensure tests never connect to production databases or send production requests.

### 16.2. When a test has multiple profiles

~~~java
@ActiveProfiles({"test", "cloud"})
~~~

The test uses both test and cloud. Beans conditioned on cloud can also be registered. Never assume that merely because test appears, every other configuration is disabled.

If you want to avoid inheriting profiles from parent test classes or other contexts, understand Spring Test's inheritance rules and configure @ActiveProfiles appropriately for your test class hierarchy.

## 17. Testing bean selection with ApplicationContextRunner

For most `@Profile` configurations, you do not need to start a web server or the whole application. **ApplicationContextRunner** can create a small context, explicitly set active profiles, and verify the bean registry.

Suppose the configuration class from Section 9 has two MessageGateway beans for local and prod. You can test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MessageGatewayProfileTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            MessageGatewayConfiguration.class);

    @Test
    void selectsLocalGateway() {
        runner.withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("local"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasBean("localMessageGateway");
                    assertThat(context)
                            .doesNotHaveBean("remoteMessageGateway");
                });
    }

    @Test
    void selectsProductionGateway() {
        runner.withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("prod"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasBean("remoteMessageGateway");
                    assertThat(context)
                            .doesNotHaveBean("localMessageGateway");
                });
    }
}
~~~

This example illustrates explicitly setting active profiles **before configuration is processed** in the context runner.

There is no need to run real services or connect to external APIs to test bean registration conditions. If a bean has side effects on initialization, replace it with a test implementation or design separate test configuration.

### 17.1. Testing the no-active-profile scenario

With two beans meant only for local and prod, a context without those profiles may have no MessageGateway at all.

~~~java
@Test
void registersNoGatewayWithoutMatchingProfile() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    MessageGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(MessageGateway.class);
            });
}
~~~

This test helps clarify whether you want **fail-fast**, a fallback, or operators required to pick a profile. It does not mean lacking a MessageGateway is always good design; a real application may need that service and should fail clearly when misconfigured.

### 17.2. Testing conflicting profile combinations

If local and prod are allowed to be active simultaneously:

~~~java
@Test
void revealsConflictingGatewayCandidates() {
    runner.withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("local", "prod"))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBeansOfType(
                        MessageGateway.class)).hasSize(2);
            });
}
~~~

The test above only illustrates **two definitions matching together** in a context without a consumer requiring a single instance. In a real application, a consumer injecting MessageGateway without a qualifier can cause the context to fail.

From this finding, the team can design a rule rejecting invalid profile combinations or switch to explicit property/qualifier-based bean selection.

## 18. Do not confuse Spring Profiles with build profiles

Spring profiles are decided by Spring Environment when the application runs. Some build tools also have profile or project property concepts, yet **they are not automatically equivalent** to Spring active profiles.

### 18.1. Maven build profiles

Example:

~~~bash
mvn -Pproduction package
~~~

A Maven profile can affect dependencies, plugins, or the build process. However, unless the build is specially configured to pass a value into runtime, **this command does not prove Spring Boot will start with spring.profiles.active=prod**.

Once the application is built, to run with profile prod you should still declare it explicitly:

~~~bash
java -jar target/app.jar --spring.profiles.active=prod
~~~

### 18.2. Gradle project properties

Example:

~~~bash
./gradlew build -Penv=prod
~~~

In Gradle, -Penv=prod is a build project property. It does not automatically turn into SPRING_PROFILES_ACTIVE or a Spring Boot application argument.

If a build task is configured to forward that value, verify specifically how it is forwarded and the resulting process. Without matching configuration, do not infer Spring active profiles from Gradle properties.

### 18.3. IDE run configurations

An IDE can run the application with:

- Program arguments.
- JVM options.
- Environment variables.
- A profile selection field in the UI.

These are **per-run-configuration settings**, not necessarily identical to the service launch command on a server, Docker, or pipeline.

When debugging differences between a local machine and production, compare how the IDE passes profiles against how the production process receives profiles.

## 19. Preventing environment mix-ups with fail-fast

In a critical application, detecting misconfiguration immediately at startup is usually much safer than letting the process report ready and then call the wrong external system.

For example, an application has a property representing the deployment environment supplied by infrastructure:

~~~yaml
app:
  deployment-environment: staging
~~~

If the deployment pipeline supplies an independent and trustworthy marker, you can cross-check it against the current profile.

### 19.1. Example checking marker and active profile

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentSafetyGuard
        implements ApplicationRunner {

    private final Environment environment;

    public EnvironmentSafetyGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String target = environment.getProperty(
                "app.deployment-environment", "unknown");

        boolean isProductionDeployment =
                "production".equalsIgnoreCase(target);

        boolean isProdProfile =
                environment.acceptsProfiles(Profiles.of("prod"));

        if (isProductionDeployment != isProdProfile) {
            throw new IllegalStateException(
                    "Deployment environment and Spring profile "
                    + "are inconsistent");
        }
    }
}
~~~

This example illustrates an **invariant**, not a complete production verification mechanism. A marker is only valuable when provisioned through a trusted source and cannot easily be overridden simultaneously with the Spring profile. If both come from the same misconfigured source, they can both be wrong in the same way and the check will still pass.

Therefore, when risk is high, cross-check additionally:

- Database host and database/schema identity.
- Endpoints for payment, email, or messaging systems.
- Cloud account/project/namespace IDs provisioned by infrastructure.
- Critical feature flags.
- Appropriate certificates or authentication mechanisms.

Never print secrets into exceptions or logs as evidence.

### 19.2. Fail-fast for mandatory configuration

A `@ConfigurationProperties` type can declare validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentSettings(
        @NotBlank String endpoint,
        @NotBlank String merchantId) {
}
~~~

When registered and backed by a suitable validation provider, missing a required value can cause startup to fail instead of running with empty configuration.

Validation does not prove an endpoint belongs to the right environment, yet it eliminates a class of basic configuration mistakes.

### 19.3. Do not use profiles as the sole security mechanism

Do not trust that a destructive endpoint, debug access, or data operation is safe just because it carries @Profile("dev") or @Profile("!prod").

A misconfigured deployment can enable that profile in an unintended environment. Dangerous actions still require:

- Authentication/authorization.
- Restricted permissions on database/cloud accounts.
- Feature flag configuration with clear policies.
- Operational conditions, auditing, and additional safeguards.

Profiles are a **configuration selection tool**, not a sufficiently strong security boundary.

## 20. When to use profiles vs. properties?

| Need | Usually suitable approach |
|---|---|
| Using stable configuration sets that differ between dev and prod | Spring Profiles. |
| Choosing between local mock beans and real clients | @Profile when environment list is clear, combined with safety checks. |
| Toggling a feature independently of environment | @ConditionalOnProperty or an appropriate feature flag. |
| Adjusting timeout, batch size, endpoint | @ConfigurationProperties or Environment, from suitable property sources. |
| Multiple providers in the same environment | Bean/property conditions, qualifiers, and explicit provider selection config. |
| Wanting to switch features while the app is running | Managed dynamic config/feature flag system; profiles normally do not auto-reload context. |

For example, **do not** create separate profiles for every feature:

~~~text
prod,feature-a-on,feature-b-off,feature-c-on,debug-metrics
~~~

Profile combinations can grow rapidly and become hard to predict. If a feature can be toggled in any environment, a dedicated property like app.feature-a.enabled is much clearer.

### 20.1. Changing profiles while a process is running

Changing spring.profiles.active in a YAML file after the ApplicationContext has refreshed **does not automatically** make Spring unregister old beans, register new beans, and re-bind all configuration.

Normally a restart/redeploy or a carefully designed dedicated refresh mechanism is needed. Do not build business logic assuming editing a file immediately changes active profiles.

## 21. Investigation workflow when suspecting the wrong environment

A workflow applicable to real incidents:

**Step 1 — Identify the serving instance:** record deployment, namespace, pod, image version, startup time. Do not mistakenly inspect logs from a developer machine.

**Step 2 — Read active/default profiles:** use Environment.getActiveProfiles(), getDefaultProfiles(), or protected admin endpoints. Record the **entire** list.

**Step 3 — Trace activation sources:** check command line, -D, SPRING_PROFILES_ACTIVE, application.yml, include/groups, and code-added startup mechanisms.

**Step 4 — Verify Config Data:** inspect profile-specific files, YAML documents with on-profile, config imports, locations, and mounted files.

**Step 5 — Read effective properties:** verify endpoints, database host/schema, sandbox mode, feature flags, and parameters that truly govern behavior.

**Step 6 — Inspect bean registry:** verify mock/real beans, implementations of the same type, @Profile, and auto-configuration conditions.

**Step 7 — Verify external resources:** safely verify connectivity and identity of target systems, not just DNS hostnames in config.

**Step 8 — Compare replicas:** especially when errors are intermittent or affect only part of traffic.

**Step 9 — Establish prevention:** add validation, fail-fast checks, profile matrix tests, secret-free startup diagnostics, and consistent rollout procedures.

These steps do not require changing source code upfront. Most profile mix-up incidents can be narrowed down by observing **the right process and the right effective values**.

## 22. Investigation example: prod profile yet sending to staging

Suppose a payment service has intended configuration:

~~~yaml
# application-prod.yml
app:
  payment:
    endpoint: https://payments.production.internal
    sandbox-enabled: false
~~~

Operations sees the log:

~~~text
Active profiles: [prod]
~~~

Yet requests go to staging.

Do not immediately conclude "@Profile is broken". Check:

1. Is effective app.payment.endpoint inside the process the production endpoint?
2. Is an APP_PAYMENT_ENDPOINT environment variable overriding it?
3. Does the launch command pass --app.payment.endpoint from the pipeline?
4. Are there config imports or additional locations outside the JAR?
5. Was the payment client built from the right @ConfigurationProperties bean?
6. Did a custom PaymentClient bean yield to default auto-configuration?
7. Is a proxy, service discovery, or network routing redirecting requests elsewhere?

If Environment returns the staging endpoint, the fault is in **config resolution**. If Environment returns production yet the client uses staging, inspect **bean construction or implementation**. If the client uses the production endpoint yet requests hit staging, inspect **network/routing and target services**.

Categorizing this way avoids fixing the wrong layer and reduces risk when operating in production.

## 23. Common mistakes

### 23.1. Having application-prod.yml and assuming prod is active

**Problem:** the file is packaged, yet the process never activated prod.

**Fix:** verify getActiveProfiles() and profile activation sources; file presence is not proof.

### 23.2. SPRING_PROFILES_ACTIVE is right locally yet wrong in container

**Problem:** environment variables are passed per process; a local terminal does not represent a pod.

**Fix:** read the workload configuration and logs of the target process, not the developer terminal.

### 23.3. Active profile is right yet endpoint is still local

**Problem:** another property source overrides it, config import, or bean default values.

**Fix:** inspect effective value and origin; cross-check bound @ConfigurationProperties objects.

### 23.4. @Profile("prod") does not match when deployment uses production

**Problem:** prod and production are two different names.

**Fix:** standardize naming conventions or define an explicit profile group.

### 23.5. @Profile("!prod") accidentally enables mocks in staging

**Problem:** negating prod does not mean development-only.

**Fix:** use an explicit allowlist of profiles, restrict execution privileges, and verify bean types at startup.

### 23.6. Both dev and prod are active together

**Problem:** files and beans from both profiles can participate; property overrides or multiple bean candidates occur.

**Fix:** check include/group, runtime args, profile order, define valid combinations, and fail-fast on conflicts.

### 23.7. Only default profile is present yet assuming no profile is active

**Problem:** getActiveProfiles() is empty while getDefaultProfiles() still contains default or another name.

**Fix:** inspect both active and default; use acceptsProfiles to evaluate specific expressions.

### 23.8. Putting spring.profiles.active in a YAML document with on-profile

**Problem:** confusing document activation conditions with profile activation; Spring Boot restricts profile activation settings inside profile-specific documents.

**Fix:** move profile activation to root configuration or deployment.

### 23.9. Confusing Maven/Gradle profiles with Spring profiles

**Problem:** build tool -P does not automatically become spring.profiles.active in the running process.

**Fix:** verify the runtime command and actual Environment.

### 23.10. Test uses @ActiveProfiles("test") yet accidentally calls production

**Problem:** the test profile may be active, yet an endpoint is overridden from another source or a service uses a custom client.

**Fix:** check effective URLs, bean implementations, and network permissions; do not assert only the profile name.

### 23.11. Editing config file yet process profile does not change

**Problem:** Config Data and beans were processed at startup; editing files does not rebuild the context.

**Fix:** perform a controlled restart/redeploy or use a dedicated refresh mechanism when genuinely required.

### 23.12. All pods report prod yet only one pod is wrong

**Problem:** a pod has a different config source, image version, or rollout timing.

**Fix:** compare versions, effective settings, and beans across each replica.

## 24. Misconceptions to avoid

**"Having application-prod.yml means Spring is running prod."**  
No. The file might not have been loaded.

**"getProperty('spring.profiles.active') is the complete list of all active profiles."**  
Not necessarily. Include, groups, and programmatic additional profiles can add profiles; use getActiveProfiles().

**"An empty getActiveProfiles() means no profile matches."**  
No. Default profiles can still be used.

**"@Profile({"dev", "staging"}) requires both profiles."**  
No. The list carries OR semantics.

**"@Profile("!prod") runs only in development."**  
No. It matches any situation where prod does not match.

**"The prod profile automatically excludes the dev profile."**  
No. Both profiles can be active together.

**"spring.config.activate.on-profile: prod automatically enables prod."**  
No. It only conditions the document when prod already matches.

**"Activating prod guarantees every property comes from application-prod.yml."**  
No. Higher-precedence sources or imports can override them.

**"A bean with matching @Profile guarantees that bean exists."**  
No. The configuration class may not be scanned/imported, or other conditions and dependencies may fail.

**"Maven -Pproduction or Gradle -Penv=prod automatically enables Spring prod."**  
No. Those are build settings; runtime Spring Profiles must be passed/set appropriately.

**"Actuator /conditions always explains every @Profile."**  
No. Combine with Environment and the bean registry.

**"Profiles are a strong enough safeguard for dangerous operations."**  
No. Access control, validation, and safe operational practices are also required.

## Core takeaways

To know which profiles Spring Boot is actually using, read **Environment.getActiveProfiles()** and **getDefaultProfiles()** from the target process. Do not inspect only application-prod.yml or the spring.profiles.active string, because includes, groups, additional profiles, and other config sources can change the outcome from expectations.

After verifying active profiles, inspect **final property values** from Environment or @ConfigurationProperties, and cross-check **actually registered beans**. A profile can be right while the database, endpoint, or bean is still wrong due to property overrides, other conditions, or differing deployment versions. Test using @ActiveProfiles and ApplicationContextRunner, add secret-free startup diagnostics, inspect replicas, and fail fast on unsafe configuration. The goal is not merely seeing the word prod in logs, but proving the application is using the **right configuration, right beans, and right resources** for the intended environment.
