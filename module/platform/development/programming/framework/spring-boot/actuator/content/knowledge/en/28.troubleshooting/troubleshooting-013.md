# Cross-Checking Symptoms with Conditions, Effective Configuration, and Library Versions

## 1. Why Are Three Sources of Evidence Needed?

An Actuator endpoint returning `404` can be caused by not being created, not being exposed over HTTP, hitting the wrong port, or a proxy rewriting the path. A registry exporting no data can stem from an unmatched auto-configuration condition, an overridden property, or actual runtime libraries differing from what the author thought was in use.

Therefore, troubleshooting does not start by adding a random property. Cross-check three sources:

| Evidence source | Question it answers | What it does not prove by itself |
| --- | --- | --- |
| Conditions evaluation report | Why was/wasn't an auto-configuration or bean applied in the application context? | Does not prove requests reach the endpoint, pass security, or business logic works |
| Effective configuration | Which values is the process reading, from which sources, after precedence and binding? | Does not prove every config is used to create a bean, or libraries are compatible |
| Actual library version set | Which classes and versions are present, packaged, and loaded at runtime? | Does not prove properties are right or the endpoint is exposed |

**Conditions** here are Spring Boot's conditions, such as class presence, bean presence, missing bean, or property values. They are not service health statuses.

**Effective configuration** is the final result the app uses after combining configuration sources. `application.yml` in source code is only one of the inputs.

**Library version set** is the coordinated set of versions: Spring Boot, Spring Framework, Micrometer, registries, clients, and related dependencies. A single library having a newer version does not make the whole set more compatible.

The examples below use Spring Boot 3.3.x as the baseline. For another version, check its matching configuration contract; do not mix property names and mechanisms across multiple Spring Boot generations.

## 2. Place the Three Sources in the Startup Lifecycle

You can picture the relevant steps as follows:

```text
Configuration sources and profiles
             |
             v
Environment is prepared
             |
             v
Evaluate conditions, register bean definitions
             |
             v
Instantiate beans, bind config beans, set up endpoints
             |
             v
Expose HTTP/JMX, apply security and networking
             |
             v
Actual requests and runtime behavior
```

This diagram illustrates diagnostic relationships and does not mean every condition type is evaluated at one single instant. Some conditions are processed while parsing configuration; some depend on bean metadata at registration time.

Four important consequences follow:

1. An auto-configuration matching conditions can still fail during bean instantiation.
2. An existing bean can still lack an exposed HTTP path.
3. An exposed endpoint can still return `401` or `403` due to security.
4. A working endpoint can still report `DOWN` because an external resource actually failed.

The conditions report primarily explains application context configuration decisions. It does not continuously re-evaluate every condition on each request. Changing a configuration source in a deployment platform does not automatically make an already running process pick up new values or recreate every bean. Dynamic refresh mechanisms, if any, must be verified separately.

## 3. Normalize the Symptom Before Reading the Report

Record a verifiable description:

```text
Instance: service-a, startup run under investigation
Operation: GET to the verified management address
Expected: metric response returned
Actual: HTTP 404
Timestamp: after the latest deployment
Scope: only one replica is failing
```

This is a template for describing a situation, not real data from a specific system. When applying it, record observed values from the exact instance under investigation.

Include deployment build ID, startup time, Java runtime, active profile, app port, and management port. With multiple replicas, collect logs, configuration, and HTTP responses from **the exact same process**. When requests pass through a load balancer, you may be alternating across different instances.

### Classifying to Pick the First Evidence

| Symptom | Priority evidence | Why? |
| --- | --- | --- |
| App fails to start | Root exception, runtime classpath, related config | Management HTTP may not even exist to query yet |
| HTTP 404 | URL/port/base path, conditions, enablement, and exposure | Need to separate uncreated endpoint from unexposed endpoint |
| HTTP 401/403 | Security chain, identity, and access permissions | Conditions are not a per-request authorization trace |
| HTTP 500 or class linkage errors | Stack trace, dependencies, and loaded classes | The bean may exist yet invoke an incompatible binary |
| Health returns DOWN | Contributor details and the resource it probes | Matching contributor conditions does not guarantee the resource is healthy |
| Registry exists yet expected meter is missing | Actual registry, filters, config, and meter-creating activity | Not every metric issue is caused by auto-configuration |

Do not interpret `404` as definitive proof the bean does not exist. A proxy or security layer can also alter responses. Cross-check against the actual request path.

## 4. First Source: Reading Conditions Properly

### 4.1. Getting the Report from Startup Logs

For an application packaged as an executable JAR, adding `--debug` when running instructs Spring Boot to print the conditions evaluation report:

```bash
java -jar build/libs/conditions-lab.jar --debug
```

This JAR name will be used in the lab below. For another application, use the actual artifact of the deployment under investigation.

If starting via Gradle in a project that already has the Boot plugin:

```bash
./gradlew bootRun --args='--debug'
```

On Windows, you can use `gradlew.bat`; quoting rules depend on your shell. In a multi-project build, use the task path of the exact application.

Spring Boot's `--debug` enables a selected set of diagnostic loggers; it does not mean every logger of every library switches to DEBUG level. If the app fails too early, before reaching the relevant context creation phase, the report may be incomplete. In that case, the root exception and logs prior to failure matter more than trying to hit an endpoint that never started.

### 4.2. Getting the Report via Actuator When the Process Is Running

In a diagnostic environment with controlled access, you can expose the `conditions` endpoint. Example using a separate management server listening only on loopback:

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,conditions
```

Assuming no changed base path and no other exclusion rules:

```bash
curl -i http://127.0.0.1:9091/actuator/conditions
```

This is configuration for a local diagnostic session, not guidance to enable the endpoint across all environments. If the process runs inside a container, loopback is the container's loopback; requests from the host will not reach that port automatically. If Spring Security is present, requests must still satisfy active security rules.

The `conditions` endpoint is also subject to enablement and exposure rules. Being unable to read this endpoint itself does not prove all auto-configuration is broken. You can use startup logs instead without changing the HTTP surface.

### 4.3. Reading Results by Configuration Class and Context

The report typically organizes results per application context, with sections such as:

- `positiveMatches`: configuration classes or methods matching all evaluated conditions.
- `negativeMatches`: unmatched configurations; inside them, there can be both matched and unmatched conditions.
- `unconditionalClasses`: configurations not listed as conditional in the groups above.

The log format differs in presentation from the endpoint's JSON. Do not rely on a JSON path copied from another version while ignoring the actual structure received.

With a separate management server or multi-context system, read the right context and parent/child relationship. A condition searching for a bean may depend on that condition's search scope; do not infer a bean in any context satisfies the condition.

Start from the configuration closest to the symptom, then read the condition message verbatim. There is no need to read the entire negative matches list as a list of errors.

### 4.4. Common Condition Types

| Condition | What to check | Common misconception |
| --- | --- | --- |
| `@ConditionalOnClass` | Is the required class on the right classpath? | Having the dependency name in source is enough |
| `@ConditionalOnMissingBean` | Is a bean causing default configuration to back off? | Every negative match is an error |
| `@ConditionalOnBean` | Does the prerequisite bean exist within scope and evaluation phase? | Having the bean's class equals having the bean |
| `@ConditionalOnProperty` | Property name, effective value, `havingValue`, `matchIfMissing` | Any non-empty string has the same meaning |
| Web application conditions | Servlet, reactive, or non-web runtime? | Having Actuator implies Servlet by default |
| Endpoint conditions | Does the endpoint satisfy relevant availability rules? | Matching conditions means requests always return 200 |

A negative match can be completely valid behavior. For example, the app provides a custom bean and auto-configuration uses `@ConditionalOnMissingBean` to avoid creating an extra default bean. This is typically how Spring Boot backs off for application config, not a Spring Boot bug.

Conversely, having a class on the classpath does not prove its binary is compatible with every caller. `@ConditionalOnClass` is not a comprehensive verifier for every method the app may subsequently invoke.

### 4.5. Trace Down to the Root Cause Instead of Fixing Every Negative Match

Example where a feature requires a prerequisite bean that was not created:

```text
Target feature is not configured
        |
        v
Missing prerequisite bean
        |
        v
Configuration creating prerequisite bean did not match
        |
        v
Missing class / wrong property / custom bean present / wrong app type
```

Follow through to the verifiable root condition. Stopping at "bean not found" usually only describes an intermediate link.

Do not reason backward that manually adding a `@Bean` of the missing type fixes the root cause. Doing so may mask a dependency error, alter behavior, or cause default configuration to keep backing off.

## 5. Second Source: Determining Effective Configuration

### 5.1. Separate Source File, Environment, and Bound Object

These three are related but not identical:

1. The YAML/properties line written in source or a deployment file.
2. The value looked up in Spring `Environment`.
3. The value bound into a `@ConfigurationProperties` bean.

A configuration bean may have Java default values, type conversion, or validation. If a property is absent from Environment, the bean can still take its default value. If the bean is not registered or not bound, having the right key in a file does not make the object exist.

`@Value` and `@ConfigurationProperties` are not completely identical mechanisms either. When investigating a binding issue on a specific bean, inspect that exact bean type and the mechanism it uses.

### 5.2. Check Overrides and Profiles

Sources commonly worth cross-checking:

- Default configuration packaged inside the JAR.
- External configuration files and profile-specific files.
- Sources loaded via `spring.config.import`.
- Process environment variables.
- Java system properties.
- Command-line arguments.
- Sources added by tests or framework extensions, when running in those environments.

In typical Spring Boot examples, an argument `--property-name=value` can override values in config files and environment variables. However, do not turn that observation into an absolute precedence table for every custom PropertySource. When in doubt, inspect the actual property source order and bound values.

Check specifically:

- Does the active profile match the failing instance?
- Are multiple profiles active, and does their order matter?
- Did the container pick up new environment variables after redeploying?
- Do command-line arguments still hold values from an older run?
- Is an external file placed in a location Spring Boot actually loads?
- Did `spring.config.location` replace the default locations, or does `spring.config.additional-location` only add locations?
- Is a key written using an old property name no longer used by the current version?

Do not assume a file named `.env` is automatically read by Spring Boot in every environment. It only takes effect when the deployment tool or integration code actually loads and passes values to the app.

### 5.3. Use env and configprops Purposefully

If endpoints are authorized for a diagnostic session, `env` helps cross-check PropertySources and value origins when that metadata is available. `configprops` helps inspect bound configuration beans.

Example strictly for a controlled local environment:

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,conditions,env,configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Look up the specific property instead of dumping the entire configuration:

```bash
curl -i http://127.0.0.1:9091/actuator/env/management.endpoints.web.exposure.include
curl -i http://127.0.0.1:9091/actuator/configprops
```

The `show-values: never` mode keeps values masked. A masked value does not mean it is empty or absent. You can still use source names and origin info when returned; if you need to confirm a specific value, prefer scoped in-process diagnostics for non-sensitive keys.

Do not flip to showing all values just for convenience. Even when some values are masked, source names, file paths, or configuration structure can still be internal information.

The `configprops` endpoint is not an inventory of every key the application can read. Properties accessed only via `Environment` or `@Value` do not automatically appear as a `@ConfigurationProperties` bean in that report.

If exposing diagnostic endpoints is not permitted, use selective logs or a local run with the same non-sensitive configuration. There is no need to enable endpoints just to complete the reasoning process.

### 5.4. Do Not Confuse Querying One Key with Binding an Entire Collection

A YAML list can be represented as indexed keys, for example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
```

In that case, looking up a string at the parent key `management.endpoints.web.exposure.include` does not always yield the same result as binding the list. A single-key lookup returning no string is not enough to conclude the list is empty.

To verify binding in diagnostic code, you can use Spring Boot's Binder:

```java
List<String> exposed = Binder.get(environment)
        .bind("management.endpoints.web.exposure.include",
                Bindable.listOf(String.class))
        .orElseGet(List::of);
```

This is an illustrative snippet inside a Spring Boot application, requiring `Environment environment` and imports `java.util.List`, `org.springframework.boot.context.properties.bind.Binder`, `org.springframework.boot.context.properties.bind.Bindable`.

This binding result shows the list values for the inspected key. It does not yet cover other decisions such as the exclude list or whether the endpoint exists.

### 5.5. Separate Enablement, Exposure, and Authorization

For Actuator under Spring Boot 3.3.x's configuration model:

| Question | Relevant configuration/evidence |
| --- | --- |
| Is the endpoint disabled? | `management.endpoint.<id>.enabled`, default endpoint config, and matching conditions |
| Is the endpoint exposed over HTTP? | `management.endpoints.web.exposure.include/exclude` |
| Is the request allowed to read the endpoint? | Spring Security, proxy security, and request identity |
| Does the request reach the right place? | Port, base path, path mapping, context path, and routing |

The exclude list takes precedence over include. Thus, seeing `prometheus` in include is not enough if another source places it in exclude.

Also distinguish `management.endpoint.<id>.enabled` from the configuration of the subsystem backing the endpoint. For example, Boot 3.3.x's property enabling the Prometheus exporter is `management.prometheus.metrics.export.enabled`; this is not the same switch as HTTP exposure.

Do not copy `access` properties or endpoint rules from another Spring Boot generation and assume they work on 3.3.x. Identify the version first, then interpret key names.

## 6. Third Source: Determining the Library Version Set Actually Running

### 6.1. Distinguish Declaration, Resolution, Packaging, and Class Loading

There are at least four levels of evidence:

```text
build.gradle declares dependency
                 |
                 v
Gradle resolves runtimeClasspath
                 |
                 v
Libraries actually packaged inside deployed artifact
                 |
                 v
Classes actually loaded by JVM in running process
```

Reading only the build file tells you declared intent. Transitive dependencies, constraints, platforms, `force` rules, dependency substitutions, or packaging config can alter the outcome.

Building successfully on a laptop does not prove the server is running the JAR you just built. With multiple replicas, they may be running different artifact generations during a rollout.

### 6.2. Inspect the Resolved Dependency Graph

With Gradle, run tasks on the exact application project:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-actuator-autoconfigure --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
```

On Windows, use `gradlew.bat`. In a multi-project build, prepend the appropriate project path to the task name.

In the output, read all of:

- The final selected version.
- Which dependency path brought the library in.
- Which constraint or rule decided the version.
- Whether an older dependency was replaced by another version.
- Whether the library is on the runtime classpath or only in a test/compile configuration.

Do not just search for a line containing the artifact name. Two people both saying "Micrometer is present" may be looking at different configurations.

Spring Boot provides coordinated dependency sets through dependency management/BOM. Verify that management mechanism is actually applied and not overridden. The Boot Gradle plugin, dependency-management plugin, and importing a platform/BOM serve different roles; do not treat merely having a plugin named Spring Boot as sufficient proof all versions are managed properly.

### 6.3. Inspect the Artifact and Deployed Build

For a standard Spring Boot executable JAR, you can list entries with the JDK tool:

```bash
jar tf build/libs/conditions-lab.jar
```

Dependencies normally sit under `BOOT-INF/lib/`. Cross-check relevant JARs against the resolved dependency graph.

When deploying with containers, layered JARs, or another classpath layout, inspect the actual structure of that artifact/image; do not assume every app uses the same executable JAR layout.

Compare checksums or build IDs between the built artifact and the deployed one. You do not need to print all environment variables to prove this. Also check:

- Did the process launch from the right artifact?
- Does the container tag point to the right image digest?
- Do `bootRun`, IDE runs, and `java -jar` use the same dependency/config set?
- Is an old JAR still on the classpath due to a launch script or external lib directory?
- Do replicas share the same build ID and expected rollout state?

### 6.4. When Needed, Verify the Origin of Loaded Classes

For elusive binary errors, the source of the class the JVM is actually using is worth more than a dependency name in a build file.

The snippet below illustrates retrieving info for a loaded class in internal diagnostic code:

```java
static void printClassOrigin(Class<?> type) {
    var domain = type.getProtectionDomain();
    var source = domain == null ? null : domain.getCodeSource();
    var location = source == null
            ? "unavailable"
            : source.getLocation().toExternalForm();

    System.out.println("class=" + type.getName());
    System.out.println("source=" + location);
    System.out.println("version="
            + type.getPackage().getImplementationVersion());
}
```

For example, call `printClassOrigin(io.micrometer.core.instrument.MeterRegistry.class)` in a project that has Micrometer.

This is a helper method, not a standalone program. Location and version depend on packaging; version may be `null`. Do not invent a guessed version when metadata is absent. Do not expose internal server paths publicly.

With special classloading schemes, CodeSource alone may be inconclusive. Combine classloader info and JVM class-loading logging in an appropriate diagnostic session.

### 6.5. Read Version Error Categories Properly

| Error | Diagnostic direction | What to compare |
| --- | --- | --- |
| `ClassNotFoundException` | Classloader could not find the requested class | Class name, runtime dependencies, classloading mechanism |
| `NoClassDefFoundError` | JVM lacked a usable class definition when needed | Missing dependency or earlier class initialization failure; read the cause |
| `NoSuchMethodError` | Caller invoked a method absent from the loaded target binary | Calling class, target class, method signature, and JAR source of both |
| `AbstractMethodError` | Method contract unsatisfied during linking/execution | Coordinated interface/implementation binaries |
| `UnsupportedClassVersionError` | Bytecode requires a newer Java than the current runtime | Java used to compile, toolchain, and JVM used to run |

`NoClassDefFoundError` does not always mean "just add a JAR." If an earlier static initialization failed, find the initial exception.

`NoSuchMethodError` is rarely fixed by changing endpoint exposure values. Conditions may have matched because the class existed, yet method signatures between binaries remained incompatible.

Java 21 produces class file version 65; Java 17 uses version 61. An app compiled targeting Java 21 will not run on a Java 17 JVM merely because Spring Boot 3.3 supports Java 17 as its minimum.

Do not upgrade a random library to the latest version to try your luck. First identify the Boot-managed version set, any overrides, and why those overrides exist; then fix toward a verifiable compatible set.

## 7. Combining the Three Sources into One Causal Chain

A convincing conclusion should connect:

```text
Observed symptom
          |
          v
Mechanism capable of producing that symptom
          |
          v
Conditions / configuration / binaries confirm the mechanism
          |
          v
Smallest change grounded in evidence
          |
          v
Re-verify on the same deployment type
```

### 7.1. Scenario A: Conditions Match, Yet the Endpoint Returns 404

Suppose you already confirmed calling the right management port and path. The report shows the relevant endpoint configuration was applied. In source, include contains `prometheus`, yet an external config source sets:

```properties
management.endpoints.web.exposure.exclude=prometheus
```

Reasoning chain:

1. Having an endpoint/bean does not imply HTTP exposure.
2. Effective configuration contains exclude for the queried endpoint.
3. Exclude takes precedence over include.
4. Therefore, editing include in the default file cannot remove the winning exclude.

The evidence-based fix is editing the exact exclude source per operational requirements, restarting/redeploying via the system's mechanism, and checking both the URL and effective configuration. There is no need to add a manual endpoint bean or expose all endpoints.

If 404 persists after ruling out exposure, continue checking mappings and proxies. Do not cling to a conclusion just because it once fit another instance.

### 7.2. Scenario B: Expected Registry Is Missing

The app expects a Prometheus exporter, yet the relevant condition shows a prerequisite was unmet.

Branches to distinguish:

- Missing class: check runtimeClasspath and whether the registry artifact is present.
- Property disabling the exporter: find the winning value in Environment.
- Default config backed off due to a custom bean: determine whether that bean is intentional.
- Wrong app type or another unmatched condition: read the condition verbatim; do not blame dependencies for every negative match.

With Boot 3.3.x, the standard Prometheus exporter uses `micrometer-registry-prometheus` for the new Prometheus Java client branch; the registry class is in package `io.micrometer.prometheusmetrics`. The legacy client compatibility branch uses artifact `micrometer-registry-prometheus-simpleclient` and package `io.micrometer.prometheus`.

If custom code, dependencies, and auto-configuration target two different client families, "Prometheus library is present" is too broad a claim. Identify the exact artifact, package, and registry used by the endpoint.

Also separate the case where the exporter exists yet meters are recorded into a separate registry. Exporter conditions do not prove every meter in the app was registered into it.

### 7.3. Scenario C: Startup Fails with NoSuchMethodError After Adding a Library

Suppose the stack trace points to a call between an extension and a base library:

1. Identify the calling class and target class from the stack trace.
2. Use dependencyInsight to find the resolved versions of both sides.
3. Check the packaged JAR and actually deployed artifact.
4. If still in doubt, check loaded class origins.
5. Cross-check binary contracts and Boot's version management mechanism.
6. Remove/adjust the override or replace the extension with a compatible version.
7. Rebuild and restart the exact artifact to be deployed.

Do not claim that because the conditions report looks "right," all dependencies must be compatible. That report does not replace binary linkage checks.

If the app has not started yet, do not require calling `/actuator/conditions` as a prerequisite to proceed. Logs and artifacts are the available evidence at that stage.

### 7.4. Scenario D: Endpoint Returns 401 While Having Many Negative Matches

A report containing many unmatched configurations is normal: a Servlet app need not match every reactive configuration; if a database is unused, its database configuration may not apply.

For HTTP `401`, check identity, authentication type, and the security chain applied to the request. If the request reaches the right endpoint and requires authentication, trying to turn every negative match into a positive one will not authorize the request.

Conditions can help identify which security bean was created or which default config backed off. It is not a per-HTTP-request authorization decision trace.

### 7.5. Scenario E: Health Contributor Exists, Yet Status Is DOWN

A successfully auto-configured datasource or health contributor only proves the prerequisites to create it were satisfied. The database, broker, or external service can still be unreachable during health checks.

Read permitted error details, compare effective connection settings, and check resource state. Do not force health to UP or delete the contributor just to make the report look better.

## 8. Hands-On: One Property, Three Pieces of Evidence

The following lab clarifies the relationship among:

- Value in Environment.
- Value bound into a configuration bean.
- Bean creation decision via `@ConditionalOnProperty`.

### 8.1. Prerequisites

Use a Spring Boot 3.3.x project with Gradle wrapper, Java 17+, and Boot dependency management. Required dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'conditions-lab.jar'
}
```

This is an addition to a project that already has the Boot plugin, not a complete build file. In repositories using custom orchestration, apply via the repository's build conventions rather than duplicating configuration.

To keep results uncluttered, the minimal lab omits Spring Security, custom PropertySources, and configs with the same prefix from other sources.

### 8.2. Java Code

File `src/main/java/demo/conditions/ConditionalLabApplication.java`:

```java
package demo.conditions;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(
        ConditionalLabApplication.SampleProperties.class)
public class ConditionalLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConditionalLabApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "diagnostics.sample",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    SampleMarker sampleMarker() {
        return new SampleMarker();
    }

    @Bean
    ApplicationRunner printEvidence(
            Environment environment,
            SampleProperties properties,
            ApplicationContext context) {
        return args -> {
            System.out.println("environment.enabled="
                    + environment.getProperty("diagnostics.sample.enabled"));
            System.out.println("bound.enabled=" + properties.isEnabled());
            System.out.println("sampleMarker.present="
                    + context.containsBean("sampleMarker"));
        };
    }

    static final class SampleMarker {
    }

    @ConfigurationProperties(prefix = "diagnostics.sample")
    public static class SampleProperties {
        private boolean enabled;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
```

File `src/main/resources/application.yml`:

```yaml
diagnostics:
  sample:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,conditions
```

This is a Spring Boot app requiring full dependencies; do not compile the file alone with `javac` lacking the framework classpath.

### 8.3. Run One: Using Only File Configuration

```bash
./gradlew bootJar
java -jar build/libs/conditions-lab.jar --debug
```

On Windows, replace the Gradle command with `gradlew.bat bootJar`.

Among the other Spring Boot logs, the three lines printed by the example's runner are:

```text
environment.enabled=true
bound.enabled=true
sampleMarker.present=true
```

Conditions will show the `sampleMarker` configuration method matched the property condition. Exact message wording may vary by version; what to compare is the property name, required value `true`, and match outcome.

If reading over HTTP in this lab without Security on the default port:

```bash
curl -i http://localhost:8080/actuator/conditions
```

Do not treat the entire JSON or log timestamps as fixed exercise stdout.

### 8.4. Run Two: Overriding via Command Line

Stop the process from run one and run the same JAR:

```bash
java -jar build/libs/conditions-lab.jar --debug --diagnostics.sample.enabled=false
```

Three lines printed by the runner:

```text
environment.enabled=false
bound.enabled=false
sampleMarker.present=false
```

`enabled: true` in the file did not change, yet the command-line argument won. Conditions report the condition creating `sampleMarker` did not match. There is no need to touch dependencies to explain this difference.

This is an example of a negative match that is completely accurate for the requested configuration.

### 8.5. Run Three: Removing the Property from the File Completely

In a separate test edit, remove `diagnostics.sample.enabled`, rebuild the JAR, and run without passing that property:

```bash
./gradlew bootJar
java -jar build/libs/conditions-lab.jar --debug
```

Three lines printed by the runner:

```text
environment.enabled=null
bound.enabled=false
sampleMarker.present=false
```

Explanation:

- `Environment.getProperty(...)` cannot find the key and returns `null`.
- The boolean field in `SampleProperties` keeps Java's default value `false`.
- `matchIfMissing=false` prevents the bean from being created when the key is missing.

Therefore, a `false` value in a configuration bean is not enough to conclude Environment holds a key with string `"false"`. You must compare both missing-key state and default values.

### 8.6. Checking Placement of JVM System Properties

This is the syntax for passing a Java system property:

```bash
java -Ddiagnostics.sample.enabled=false -jar build/libs/conditions-lab.jar
```

And this is the syntax for a Spring Boot application argument:

```bash
java -jar build/libs/conditions-lab.jar --diagnostics.sample.enabled=false
```

`-D...` must appear in the JVM arguments before `-jar`. Placing it after the JAR filename does not make it a Java system property.

To keep each test to one clear hypothesis, do not pass multiple overriding sources for the same key at once. When testing precedence between two sources, record those exact two sources and the observed Environment result.

## 9. Repeatable Investigation Procedure

### Step 1: Pin the Exact Deployment and Symptom

Record the instance, artifact/image digest or build ID, startup time, request, and response. Choose a concrete incident, such as "metrics endpoint returns 404 on replica B," instead of "Actuator doesn't work."

### Step 2: Identify the Layer Needing Explanation

Separate networking, HTTP mapping, security, bean creation, binding, binaries, and external resources. Pick the first evidence per the symptom classification table; do not query an endpoint that cannot exist yet in a crashing process.

### Step 3: Gather Relevant Conditions

Read the target configuration, unmatched conditions, and prerequisite chain. Distinguish intentional negative matches from unintended missing conditions. If the configuration does not appear in the report, check dependencies, exclusions, and report scope; a missing name is not enough to conclude a single reason.

### Step 4: Trace Effective Configuration

Confirm version-accurate key names, active profiles, winning source, and bound values if applicable. For collections, inspect collection binding. For masked values, do not assume they are empty and do not demand dumping all secrets.

### Step 5: Verify Actual Libraries

Dig into dependencies only when symptoms or conditions point to a classpath/binary hypothesis. Compare the resolved graph, artifact, and runtime. Do not turn every `401` error into a library upgrade.

### Step 6: Change One Evidence-Backed Root Cause

For example, fix the exact exclude source, remove a conflicting version override, or adjust authorization rules for the scrape identity. Keep the edit scope tied to the hypothesis being verified.

### Step 7: Re-verify from the Start of the Observation Path

Rebuild/redeploy when needed, confirm the exact artifact, read effective values, and retry each failing behavior. With multiple replicas, check the full affected scope. Remove temporary diagnostic config/logs according to your environment's operational practices.

## 10. Writing Conclusions from Evidence

A concise report should answer:

| Item | Example entry |
| --- | --- |
| Symptom | Endpoint returns 404 on the verified instance's exact management port |
| Expected | Endpoint is exposed to authorized monitoring consumers |
| Conditions | Relevant configuration was applied; no prerequisite missing for the bean in question |
| Effective configuration | Exclude from an external config source removes the endpoint from HTTP exposure |
| Version set | Graph and artifact contain no related changes explaining this symptom |
| Root cause | Effective exclude configuration, not a missing dependency |
| Fix | Update the exact exclude source per deployment requirements |
| Verification | After redeploying, URL responds properly and is verifiable from the monitoring side |

This table is an example for one specific cause; do not use it as a template conclusion for every incident.

If evidence is still insufficient, record the hypothesis and next test. For example, "suspected binary conflict; need to verify loaded class origin" is far more accurate than calling every startup failure "wrong version."

Three questions should be answered with evidence from the same process: **What did Spring Boot decide to create, which configuration is the process actually reading, and which library set is the JVM running?** Only when all three answers align with the symptom does the fix have a sound basis and become verifiable.
