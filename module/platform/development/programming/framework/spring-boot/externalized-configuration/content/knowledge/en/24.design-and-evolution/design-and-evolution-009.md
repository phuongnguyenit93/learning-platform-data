# Pre-Release Configuration Review with Metadata, Testing, and Operator Documentation

## Purpose

A Spring Boot application may work flawlessly on a developer laptop yet fail immediately upon reaching staging or production because property names differ, a profile was not activated, an environment variable was misnamed, a value is missing, a type failed to convert, or a property was renamed between releases without notifying operators.

In **Spring Boot Externalized Configuration**, "shipping software" is not merely building a JAR file. Properties exposed to application operators or library consumers form a **public configuration contract** with names, types, defaults, constraints, override rules, units, deprecation status, and security policies.

A solid pre-release configuration review combines three layers of evidence:

1. **Metadata** tells IDEs, build tooling, and config authors which keys are supported, their types, descriptions, hints, defaults, and deprecation status.
2. **Tests** prove that Binder, validation, bean conditions, profiles, Config Data imports, and startup actually behave according to contract.
3. **Operator documentation** tells developers, DevOps/SREs, and library consumers what to declare, where, how to override, how missing/invalid values behave, and what changed since the prior release.

These three layers complement one another. **Metadata is not a runtime validator**, a green test suite alone does not make documentation complete, and a README with valid examples does not prove the shipped JAR actually packaged metadata or boots cleanly.

This lesson outlines a pre-release review workflow applicable to a Spring Boot service or library. Examples primarily follow **Spring Boot 3.x**, Java 17+, Maven/Gradle, and Jakarta Validation. For Boot 4.x, check dependencies, packages, and modularized/updated APIs for your project's version.

### Expected Outcomes

After reading, you will be able to:

- Inventory configuration properties by prefix, owner, and lifecycle.
- Define a Java schema with **@ConfigurationProperties** instead of scattered `@Value` fields where appropriate.
- Generate and inspect **META-INF/spring-configuration-metadata.json**.
- Supplement descriptions, hints, and deprecations via **additional-spring-configuration-metadata.json**.
- Distinguish advisory metadata from active runtime binding and validation.
- Write tests spanning Java objects, Binder, `ApplicationContextRunner`, and full `SpringApplication`.
- Verify profiles, precedence, Config Data imports, env vars, CLI, and required settings.
- Write operator documentation without leaking secrets.
- Establish a release checklist, release blockers, and a migration process for renamed keys.
- Diagnose mismatches when metadata, tests, and documentation describe conflicting contracts.

---

## 1. Why Is Configuration an API?

Consider an HTTP client library configured via:

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    connect-timeout: 2s
    retry:
      max-attempts: 3
      backoff: 300ms
~~~

When other services rely on these keys, they are consuming an API even without importing the corresponding Java class.

A change like:

~~~text
acme.gateway.connect-timeout
           ->
acme.gateway.connection-timeout
~~~

can break existing deployments' overrides unless the library supports an alias or publishes migration instructions. Similarly, changing units from milliseconds to seconds without notice can multiply or divide timeouts by a thousandfold.

Components of a configuration contract:

| Component | Question to Answer |
| --- | --- |
| Canonical name | What is the supported property name? |
| Prefix | Which module owns this group? |
| Java type | String, URI, Duration, DataSize, boolean, List, or Map? |
| Required | Is omitting the key valid? |
| Default | What value is used when omitted? |
| Range/invariant | Which values are rejected? |
| Environment mapping | What is the canonical env variable name? |
| Precedence | How do files, profiles, env, JVM, and CLI override each other? |
| Secret classification | May values be logged or shown in docs? |
| Deprecated/replacement | Is the old key still accepted, and until when? |
| Owner | Which team governs the schema and incidents? |
| Observability | How can we tell which source won without printing raw values? |

**Pre-release review** means confirming the relevant contract components are documented and verified appropriately—not attempting to print every property in `Environment`.

---

## 2. Classifying Configuration by Impact

Not every property carries equal risk. Categories include:

**Bootstrap-critical**: affects how the app reads Config Data, profiles, logging, or early initialization. Wrong load timing can stop subsequent edits from taking effect as expected.

**Operational-critical**: database URLs, pool sizes, service endpoints, retries, timeouts, message brokers, storage locations. Wrong values can fail startup or misroute production traffic.

**Security-sensitive**: passwords, tokens, private keys, trust store passwords, OAuth client secrets. Requires stricter handling than ordinary configuration docs.

**Feature/optional**: module toggles, secondary batch sizes, module debug logging. Often permits defaults or absence depending on design.

**Internal-only**: implementation details that should stay out of the public contract whenever possible.

### 2.1. Risk-Based Release Matrix

| Category | Metadata | Required Tests | Required Docs |
| --- | --- | --- | --- |
| Bootstrap-critical | Description and timing notes | SpringApplication / Config Data | Early sources, profiles/imports, restarts |
| Operational-critical | Type, default, range | Binder, validation, startup | Examples, units, impact, rollback |
| Security-sensitive | Never include raw secrets | Missing/invalid, redaction | Safe secret delivery, permissions, rotation |
| Feature/optional | Defaults, value hints | Conditional beans, enabled/disabled | Behavioral impact when toggled |
| Internal-only | Only if genuinely public | Tests in owning module | Avoid accidentally publishing unstable keys |

Targeting tests by risk is far more effective than writing one giant `@SpringBootTest` for every key.

---

## 3. Starting from a Single Schema

A sample Java record for gateway configuration:

~~~java
package example.gateway;

import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

/**
 * Connection and retry settings for the outbound gateway.
 *
 * @param baseUrl Base URL of the upstream gateway.
 * @param connectTimeout Maximum time for establishing a connection.
 * @param retry Retry settings for failed requests.
 * @param endpoints Endpoint definitions that the gateway may use.
 */
@Validated
@ConfigurationProperties(prefix = "acme.gateway")
public record GatewayProperties(
        @NotBlank String baseUrl,
        @NotNull @DefaultValue("2s") Duration connectTimeout,
        @Valid @NotNull Retry retry,
        @NotEmpty List<@NotNull @Valid Endpoint> endpoints
) {

    /**
     * Retry policy.
     *
     * @param maxAttempts Maximum number of attempts, at least one.
     * @param backoff Delay between attempts.
     */
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {}

    /**
     * A target endpoint.
     *
     * @param name Name of the endpoint.
     * @param host DNS host name.
     * @param port TCP port of the endpoint.
     */
    public record Endpoint(
            @NotBlank String name,
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Valid configuration example:

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    connect-timeout: 3s
    retry:
      max-attempts: 3
      backoff: 300ms
    endpoints:
      - name: primary
        host: edge-a.example.test
        port: 8080
~~~

### 3.1. Canonical Property Paths

~~~text
acme.gateway.base-url
acme.gateway.connect-timeout
acme.gateway.retry.max-attempts
acme.gateway.retry.backoff
acme.gateway.endpoints[0].name
acme.gateway.endpoints[0].host
acme.gateway.endpoints[0].port
~~~

Canonical names use lowercase with dots separating groups and hyphens separating words. For instance, **connect-timeout** binds to Java component **connectTimeout**.

### 3.2. Why Use `@ConfigurationProperties`?

Compared to declaring scattered fields:

~~~java
@Value("...") String baseUrl;
@Value("...") Duration timeout;
~~~

a clearly named configuration class centralizes the schema, validation, defaults, Javadoc documentation, and IDE metadata.

However, **defining the class alone does not register it as a bean**. Register it with **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties(GatewayProperties.class)** in your application setup.

### 3.3. `@Validated`, `@Valid`, and `@NotNull`

**@Validated** on the configuration properties bean instructs Spring Boot to trigger validation during binding when a compatible provider is present.

**@Valid** on `Retry` and `Endpoint` elements cascades validation into nested types.

**@NotNull** on `Retry` ensures the `retry` branch is present. **@Valid alone does not reject null**.

**@NotEmpty** on the `List` ensures at least one element; **@Valid** on the element validates each `Endpoint`.

These are runtime rules; generated metadata does not enforce constraints at deployment time.

---

## 4. What Is Spring Boot Metadata?

Spring Boot documents configuration properties through JSON metadata at:

~~~text
META-INF/spring-configuration-metadata.json
~~~

It appears in build outputs and is packaged into the JAR. IDEs read this metadata from dependencies to suggest property names, types, descriptions, defaults, value options, and deprecation warnings.

Typical top-level sections:

~~~json
{
  "groups": [],
  "properties": [],
  "hints": []
}
~~~

Versions and formats supporting additional metadata can also include **ignored**.

**Metadata is not a running `application.yml`.** It describes what a module can accept, not what an operator configured in a given environment.

### 4.1. `groups`

A group represents a prefix or property group, for example:

~~~json
{
  "name": "acme.gateway",
  "type": "example.gateway.GatewayProperties",
  "sourceType": "example.gateway.GatewayProperties"
}
~~~

Groups help tooling organize completions; they are not keys requiring values.

### 4.2. `properties`

A property entry describes one key:

~~~json
{
  "name": "acme.gateway.connect-timeout",
  "type": "java.time.Duration",
  "description": "Maximum time for establishing a connection.",
  "defaultValue": "2s",
  "sourceType": "example.gateway.GatewayProperties"
}
~~~

This is an illustrative example of valid metadata concepts. The processor may emit slightly different fields/details depending on target types and Boot version; inspect real output when reviewing rather than expecting an invariant JSON order.

### 4.3. `hints`

Hints provide value suggestions or value providers to IDEs:

~~~json
{
  "name": "acme.gateway.mode",
  "values": [
    {
      "value": "strict",
      "description": "Reject requests if the upstream is unavailable."
    },
    {
      "value": "best-effort",
      "description": "Allow degraded behavior when configured."
    }
  ]
}
~~~

**Hints are not validation constraints.** An IDE may suggest `strict`/`best-effort`, yet if the app binds an unconstrained `String`, use a Java enum, converter, or validator to reject invalid values at runtime.

### 4.4. `deprecated`

Metadata can flag replaced properties:

~~~json
{
  "name": "acme.gateway.old-timeout",
  "deprecation": {
    "level": "warning",
    "reason": "Use the new connection timeout property.",
    "replacement": "acme.gateway.connect-timeout",
    "since": "2.1.0"
  }
}
~~~

Deprecation signals users and tooling. Never treat it as a runtime mechanism that automatically translates old keys to new keys.

### 4.5. Metadata Does Not Hold Current Runtime Values

Even if production supplies:

~~~text
ACME_GATEWAY_CONNECTTIMEOUT=12s
~~~

metadata still documents the default 2s. It never reads production `Environment` or reflects runtime values.

To inspect which source won in a live process, use authorized diagnostics; **never write actual secrets into metadata**.

---

## 5. Generating Metadata with the Annotation Processor

Spring Boot provides **spring-boot-configuration-processor**. When configured for annotation processing at compile time, it scans **@ConfigurationProperties** types/methods and generates metadata.

### 5.1. Maven

With Maven Compiler Plugin and Spring Boot dependency management, an example setup:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.12.1</version>
      <configuration>
        <annotationProcessorPaths>
          <path>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

**Version and dependency management note:** the snippet above reflects Spring Boot 3.5 docs with Maven Compiler Plugin 3.12+; on other toolchains—especially newer Maven Compiler Plugins or Boot 4.x—verify the matching annotation processor configuration. Do not paste a plugin version into a parent-managed build if it conflicts with project policy.

### 5.2. Gradle

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

For Kotlin sources, configure the processor for the Kotlin toolchain (such as `kapt` where needed) rather than assuming Java `annotationProcessor` processes Kotlin classes.

### 5.3. When Using Lombok

Projects using Lombok to generate getters/setters/constructors must ensure Lombok's annotation processor runs in the right order relative to Boot's configuration processor.

If a build omits metadata for a field that Binder binds at runtime, check:

- Did Lombok run during compilation?
- Is Boot's processor configured?
- Are processors ordered properly?
- Is the field discoverable via JavaBean getters/setters or constructor?
- Is the build processing source classes vs precompiled dependencies?

A metadata artifact verification test catches this type of build issue before release.

### 5.4. Do Not Substitute a Runtime Dependency for Annotation Processing

Merely placing the artifact on the runtime classpath does not invoke the annotation processor during compilation. Verify the compile configuration actually triggers annotation processing.

For released libraries, what matters is that **the final JAR contains accurate metadata**, not just having a nice line in `pom.xml` or `build.gradle`.

---

## 6. Javadoc and Property Descriptions

A public schema needs clear descriptions, not only names and types.

For JavaBeans:

~~~java
/**
 * Maximum time allowed to establish a TCP connection.
 * This does not include the full response time.
 */
private Duration connectTimeout = Duration.ofSeconds(2);
~~~

The processor extracts field Javadoc to populate `description` when source is available at compile time.

For Java records, Spring Boot docs recommend **class-level Javadoc with `@param` tags** to document record components.

Example:

~~~java
/**
 * Retry behavior for the outbound client.
 *
 * @param maxAttempts Number of attempts, including the first call.
 * @param backoff Delay between successive attempts.
 */
public record Retry(
        int maxAttempts,
        Duration backoff
) {}
~~~

### 6.1. What Should a Good Description Answer?

Instead of just:

~~~text
Timeout value.
~~~

write:

~~~text
Maximum time allowed to establish a connection to the upstream.
Use an explicit unit such as 2s or 250ms.
~~~

When documenting retries, state **whether `maxAttempts` includes the initial call**. For `DataSize`, state units and defaults; for boolean flags, describe what `true` and `false` each do.

### 6.2. Never Put Secrets in Descriptions

Never write:

~~~text
Production API key is abc-123-...
~~~

Descriptions should explain how **secrets are supplied** and where policies live—never put real values in source, Javadoc, or build artifacts.

### 6.3. Never Claim a Non-Existent Default in Javadoc

Stating "Default is 2s" in a description when runtime has no default misleads operators. Cross-check **@DefaultValue**, field initializers, base config files, or actual fallback logic.

---

## 7. Inspecting Generated Metadata in the Build

After compiling, metadata is typically located at:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

for standard Maven layouts, or:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

for standard Gradle Java layouts. Exact paths vary by plugin and toolchain.

Example commands:

~~~bash
./mvnw clean compile
~~~

or:

~~~bash
./gradlew clean compileJava
~~~

Then inspect the packaged artifact:

~~~bash
jar tf target/my-library.jar
~~~

or:

~~~bash
jar tf build/libs/my-library.jar
~~~

In a standard library JAR, metadata lives at **META-INF/spring-configuration-metadata.json**. In an executable Spring Boot JAR, classes typically live under **BOOT-INF/classes/META-INF/**.

### 7.1. What to Verify in Metadata

- Are all public supported keys present?
- Are prefixes spelled correctly?
- Do types match the Java model?
- Are descriptions clear?
- Do default values match runtime?
- Do hints reference exact property names?
- Do deprecated properties include `reason` and `replacement` where needed?
- Were any internal/secret details accidentally exposed?
- Do stale properties removed from code still linger via manual metadata?
- Is metadata actually packaged into the artifact consumers download?

Do not assert **array ordering** across JSON elements, as the format does not require source-order preservation. Check by key name and relevant attributes.

### 7.2. Metadata Is Not an Enforced Schema

The JSON file can list a property no longer bound at runtime if manual metadata is stale. Conversely, Binder may accept keys unrecognized by the processor due to dynamic prefixes or manual binding.

**Cross-check metadata with runtime tests**; never treat metadata alone as proof a property works.

---

## 8. Adding Manual Metadata

Sometimes the processor cannot infer a description/default, or a project reads keys manually via `Environment`/`Binder`.

Create:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Example:

~~~json
{
  "properties": [
    {
      "name": "acme.gateway.connect-timeout",
      "description": "Maximum time to establish an upstream connection.",
      "defaultValue": "2s"
    },
    {
      "name": "acme.gateway.mode",
      "type": "java.lang.String",
      "description": "Gateway behavior when the upstream is unavailable."
    }
  ],
  "hints": [
    {
      "name": "acme.gateway.mode",
      "values": [
        {
          "value": "strict",
          "description": "Reject requests if the upstream cannot be used."
        },
        {
          "value": "best-effort",
          "description": "Continue with the configured degraded path."
        }
      ]
    }
  ]
}
~~~

Here `connect-timeout` declares default `2s` **because the Java model has `@DefaultValue("2s")`** in the earlier example. If code supplies no `2s` default, fix the manual metadata rather than hoping IDE hints create runtime defaults.

### 8.1. Processor Merging

The annotation processor merges `additional-spring-configuration-metadata.json` into the generated file. When a key matches an auto-detected property, attributes such as description/default/deprecation are supplemented or overridden per the processor version's rules.

If manual metadata declares a key undetected by the processor, it is included in the combined metadata as a standalone property.

### 8.2. Gradle Task Ordering Note

For additional metadata files, Spring Boot docs note `compileJava` needs resources available when the annotation processor runs. A common snippet:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

If your build uses custom task dependencies, configure them appropriately for your Gradle version and plugins, then inspect generated metadata. **Never assume a file in `src/main/resources` merges into output under every build order.**

### 8.3. Manual Metadata Does Not Create Runtime Properties

If Java never reads **acme.gateway.mode**, adding it to `additional-spring-configuration-metadata.json` only gives IDEs autocomplete—**it does not make Spring Boot create beans or run mode logic**.

At release review, every manual property must have a clear runtime owner: Java field, `Binder` call, `Environment` lookup, or extension.

---

## 9. Hints for Enums, Maps, and Paths

Metadata hints improve authoring experience, especially when a `String` accepts a known set of values.

Example:

~~~json
{
  "hints": [
    {
      "name": "acme.gateway.mode",
      "values": [
        { "value": "strict", "description": "Fail closed." },
        { "value": "best-effort", "description": "Allow degraded mode." }
      ]
    }
  ]
}
~~~

### 9.1. Hints Are Not a Runtime Allowlist

If the target field is:

~~~java
String mode
~~~

without validation, Binder still accepts arbitrary strings.

To genuinely restrict values, consider an enum:

~~~java
public enum GatewayMode {
    STRICT,
    BEST_EFFORT
}
~~~

and declare:

~~~java
GatewayMode mode
~~~

or apply properly integrated custom validation.

### 9.2. Map Key and Map Value Hints

For `Map` properties, the metadata format supports hints on paths ending in **.keys** or **.values** where appropriate.

For instance, if a `Map<String, String>` uses standardized keys, IDEs can suggest them. Conversely, if keys are dynamic per tenant or module, avoid publishing a rigid list that becomes misleading.

### 9.3. Do Not Make Hints Your Sole Documentation

An IDE may ignore hints, or operators may edit YAML in tools lacking Spring Boot metadata support. Important allowed values still belong in the README and deployment docs.

---

## 10. Deprecated Properties and Pre-Release Migration

Renaming a key changes the contract.

Old name:

~~~text
acme.gateway.connection-timeout-ms
~~~

New name:

~~~text
acme.gateway.connect-timeout
~~~

Release documentation must define:

- Does the old key still work?
- If so, how is it converted?
- If both keys are present, which wins?
- Do old and new units match?
- Is there a minimum version and a scheduled removal version for the old key?
- How do operators detect deployments still using the old name without logging values?

### 10.1. `@DeprecatedConfigurationProperty`

A JavaBean getter can carry:

~~~java
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@Deprecated
@DeprecatedConfigurationProperty(
        replacement = "acme.gateway.connect-timeout",
        since = "2.1.0"
)
public Duration getOldTimeout() {
    return this.connectTimeout;
}
~~~

This illustrates deprecation metadata on an accessor, not a complete JavaBean design. If the old key must continue binding, code must retain the corresponding binding/accessor/alias during the migration window.

### 10.2. Deprecated Metadata Is Not an Automatic Alias

Merely writing:

~~~json
{
  "deprecation": {
    "replacement": "acme.gateway.connect-timeout"
  }
}
~~~

does not cause Binder to map the old key onto the new key when supplied by an operator.

You must keep compatibility in the JavaBean, add an explicit mapping layer, or require users to upgrade configs per release policy.

### 10.3. `warning` and `error`

Deprecation metadata supports **warning** or **error** levels. `error` indicates to tooling that the property is no longer managed/bound, yet that is a tooling signal—ensure runtime behavior actually matches.

Never keep a deprecated key in metadata while code silently executes completely different behavior.

### 10.4. Sample Migration Table

| Version | Property Name | Policy |
| --- | --- | --- |
| 2.0.x | `connection-timeout-ms` | Legacy name |
| 2.1.x | `connect-timeout` | New name introduced; old name deprecated |
| 2.2.x | `connect-timeout` | Old name still supported per contract |
| 3.0.x | `connect-timeout` | Old name may be removed after breaking-change notice |

Version numbers in the table are **examples**, not the history of a real library. In real projects, publish exact versions and timelines.

---

## 11. Runtime Defaults vs Metadata Defaults

One of the easiest release bugs to miss is metadata claiming one default while runtime uses another.

Common default sources:

1. Values in `application.yml` packaged with the app.
2. `@DefaultValue` on record components / constructor binding.
3. Field initializers in JavaBeans.
4. Defaults injected in constructors or factories.
5. `SpringApplication` `defaultProperties`.
6. Low-priority `PropertySources` added by libraries.
7. Fallbacks in services when Binder leaves a field unbound.

### 11.1. Cross-Checking One Default

With Java:

~~~java
@DefaultValue("2s") Duration connectTimeout
~~~

and manual metadata:

~~~json
{
  "name": "acme.gateway.connect-timeout",
  "defaultValue": "2s"
}
~~~

both sides match.

If `application-prod.yml` supplies `5s`, metadata defaults do not change; operators still get `5s` at runtime.

### 11.2. `@DefaultValue` Does Not Guarantee Nested Objects Always Exist

A record with a nested component is not necessarily instantiated if the entire branch is absent. Behavior depends on constructor binding, defaults, and Boot version. When a nested object is mandatory, combine `@NotNull` and `@Valid` or an explicit initialization policy.

### 11.3. Code Defaults Can Be Hard to Infer Automatically

The annotation processor detects some defaults via source heuristics. It cannot evaluate arbitrary expressions, constants from other classes, or dynamically built collections.

If metadata omits a default the processor couldn't infer, supplement it via manual metadata—**only when you are certain of the exact runtime default**.

### 11.4. Never Put "Fake Valid Defaults" on Secrets

Avoid:

~~~yaml
acme:
  credentials:
    api-key: "placeholder-key-for-production"
~~~

because it lets the application start even when an operator forgets to configure the real secret.

For required sensitive values, let absence fail in a controlled way, and keep only instructional placeholders in documentation—never usable values.

---

## 12. Validation Is a Runtime Contract, Not a JSON Attribute

A record with:

~~~java
@Validated
@ConfigurationProperties(prefix = "acme.gateway")
public record GatewayProperties(
        @NotBlank String baseUrl,
        @Min(1) int maxAttempts
) {}
~~~

Metadata may show String/int and describe meaning, yet never assume metadata enforces `@NotBlank`/`@Min` at runtime.

For validation to execute during bean binding, ensure:

- A compatible Jakarta Bean Validation provider is present.
- The `@ConfigurationProperties` bean is properly registered.
- `@Validated` is placed where integration requires it.
- `@Valid` is present on nested branches needing cascade.
- Constraints match the field's data type.
- Invalid startup tests verify validation actually fires.

### 12.1. Validation Dependency

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

On Spring Boot 3, import constraints from **jakarta.validation**, rather than blindly copying **javax.validation** from Boot 2 projects without checking compatibility.

### 12.2. `@Valid` Does Not Mean `@NotNull`

~~~java
@Valid Retry retry
~~~

cascades validation only when the object is non-null.

If `retry` is required:

~~~java
@Valid @NotNull Retry retry
~~~

Tests should include a case omitting the `retry` branch altogether, not only `retry.maxAttempts=0`.

### 12.3. `Duration` and `DataSize` Require Type-Appropriate Constraints

Do not put **@Min(1)** directly on `Duration` expecting Jakarta Validation to treat it as milliseconds. Use a custom constraint or an appropriate invariant to require a positive `Duration`.

For `int maxAttempts`, `@Min(1)` fits well. For `String baseUrl`, `@NotBlank` catches empty strings yet does not guarantee a reachable URL.

### 12.4. Right Type Does Not Mean Business-Valid

**max-attempts=0** converts to `int` cleanly yet violates `@Min(1)`.

**max-attempts=many** fails during conversion before validation even runs.

Test both failure modes separately rather than lumping everything into "validation failed."

---

## 13. Four Pre-Release Configuration Testing Levels

A layered testing strategy:

| Level | Mechanism Tested | Strength | Limit |
| --- | --- | --- | --- |
| Java object | Constructor/invariant/manual validator | Fast, clear errors | Does not test binding |
| Binder | `MapConfigurationPropertySource` + `Binder` | Names, types, nesting, List/Map | Does not test bean lifecycle |
| `ApplicationContextRunner` | Small context, bean registration, validation, conditions | Tests local Spring Boot mechanics | Does not simulate full bootstrap |
| Full `SpringApplication` / `@SpringBootTest` | Config Data, profiles, imports, EPP, wiring | Verifies real deployment path | Heavyweight, many moving parts |

**Pick the lowest level that proves the behavior under test.** A green `Binder` test does not prove `spring.config.import` works; a green `@SpringBootTest` with property overrides does not prove the production file holds that value.

### 13.1. Object Tests

If a record has a compact constructor normalizing a `List`:

~~~java
public record EndpointGroup(List<String> hosts) {
    public EndpointGroup {
        hosts = hosts == null ? List.of() : List.copyOf(hosts);
    }
}
~~~

Plain JUnit tests verify defensive copying without Spring.

### 13.2. Binder Tests

Verify Spring Boot converts strings into Java types and maps nested paths.

### 13.3. `ApplicationContextRunner` Tests

Verify `@EnableConfigurationProperties`, `@Validated`, `@ConditionalOnProperty`, and auto-configuration inside a context.

### 13.4. Full App Tests

Verify `application.yml`, profiles, external locations, EPP discovery, Config Data imports, and target-deployment wiring.

---

## 14. Binder Tests: Canonical Names and Type Conversion

Condensed test example:

~~~java
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayBinderTest {

    @Test
    void bindsNestedSettings() {
        Map<String, Object> values = Map.of(
            "acme.gateway.base-url", "https://api.example.test",
            "acme.gateway.connect-timeout", "4s",
            "acme.gateway.retry.max-attempts", "3",
            "acme.gateway.retry.backoff", "250ms",
            "acme.gateway.endpoints[0].name", "primary",
            "acme.gateway.endpoints[0].host", "edge.example.test",
            "acme.gateway.endpoints[0].port", "8080"
        );

        Binder binder = new Binder(
            new MapConfigurationPropertySource(values)
        );

        GatewayProperties result = binder
            .bind("acme.gateway", GatewayProperties.class)
            .orElseThrow();

        assertThat(result.connectTimeout())
            .isEqualTo(Duration.ofSeconds(4));
        assertThat(result.retry().maxAttempts())
            .isEqualTo(3);
        assertThat(result.endpoints()).hasSize(1);
    }
}
~~~

This verifies `Binder`, `Duration` conversion, and nested `List` binding on test data. It does not check YAML parsing or `@Validated` execution in a Spring `ApplicationContext`.

### 14.1. Testing Conversion Errors

Another test supplies:

~~~text
acme.gateway.retry.max-attempts=many
~~~

and asserts binding fails appropriately. `"many"` is not an `int`, so do not confuse this with `@Min(1)`.

### 14.2. Testing Wrong Prefixes

Supply:

~~~text
acme.gateway.max-attempts=3
~~~

instead of:

~~~text
acme.gateway.retry.max-attempts=3
~~~

and inspect the binding result. This catches indentation/structural errors once keys are flattened.

### 14.3. Scoped Relaxed Binding Tests

Canonical:

~~~text
acme.gateway.connect-timeout
~~~

Java:

~~~text
connectTimeout
~~~

Standard env variable:

~~~text
ACME_GATEWAY_CONNECTTIMEOUT
~~~

A `Binder` test on a `Map` does not test real OS environment variable handling; process-level tests or system-environment property sources fit better when proving env mapping.

---

## 15. `ApplicationContextRunner` Tests: Beans and Validation

Minimal configuration test:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesContextTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class
            ))
            .withUserConfiguration(Config.class);

    @Test
    void acceptsValidGateway() {
        runner.withPropertyValues(
            "acme.gateway.base-url=https://api.example.test",
            "acme.gateway.connect-timeout=2s",
            "acme.gateway.retry.max-attempts=3",
            "acme.gateway.retry.backoff=250ms",
            "acme.gateway.endpoints[0].name=primary",
            "acme.gateway.endpoints[0].host=edge.example.test",
            "acme.gateway.endpoints[0].port=8080"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GatewayProperties.class);
        });
    }

    @Test
    void rejectsInvalidNestedRetry() {
        runner.withPropertyValues(
            "acme.gateway.base-url=https://api.example.test",
            "acme.gateway.connect-timeout=2s",
            "acme.gateway.retry.max-attempts=0",
            "acme.gateway.retry.backoff=250ms",
            "acme.gateway.endpoints[0].name=primary",
            "acme.gateway.endpoints[0].host=edge.example.test",
            "acme.gateway.endpoints[0].port=8080"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class Config {}
}
~~~

JUnit Jupiter/Test imports and assertions above are trimmed for clarity. Projects need **spring-boot-starter-test**, a validation provider, and dependencies matching their Spring Boot version.

### 15.1. Do Not Assert Only `hasFailed`

A context might fail due to a missing bean or classpath issue. When testing `@Min(1)`, assert that the failure cause is specifically `Retry` validation via supported APIs/cause chains, while avoiding brittle exact-text assertions on error messages across versions.

### 15.2. Test Missing Branches

Add a case supplying `base-url` and `endpoints` while omitting `retry` completely. With `@NotNull Retry`, the context must fail if the binder supplies no default `Retry`.

### 15.3. Test Conditional Beans

If the library uses:

~~~java
@ConditionalOnProperty(
    prefix = "acme.gateway",
    name = "enabled",
    havingValue = "true"
)
~~~

test true, false, and absent with `ApplicationContextRunner`. No need to boot a web server just to test a local condition.

---

## 16. Full Application Tests for Config Data and Profiles

These behaviors depend on `SpringApplication` bootstrap:

- `application.yml` and `application-prod.yml`.
- Config Data imports and locations.
- Profile activation and profile-specific documents.
- External locations or configtrees.
- `EnvironmentPostProcessor` discovered via `spring.factories`.
- JVM system properties, command-line overrides, and early lifecycle events.
- Wiring across multiple auto-configurations/modules.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("release-smoke")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ReleaseConfigurationSmokeTest {

    @Autowired
    GatewayProperties gateway;

    @Test
    void gatewayIsBoundAfterBootstrap() {
        assertThat(gateway.baseUrl()).isNotBlank();
        assertThat(gateway.retry().maxAttempts())
            .isGreaterThanOrEqualTo(1);
    }
}
~~~

Create a safe test profile file with all required properties—such as `application-release-smoke.yml` in test resources. Never let tests read production credentials or call live endpoints.

### 16.1. Verifying Precedence

Suppose `application.yml` sets 2s, `release-smoke` sets 5s, and the test adds no overrides. Asserting `gateway.connectTimeout()` equals 5s confirms profile-specific Config Data loaded.

If the test uses:

~~~java
@SpringBootTest(properties = "acme.gateway.connect-timeout=7s")
~~~

then getting 7s proves the test override worked—not that the profile file contains 7s.

### 16.2. Config Data Imports

If the app uses:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway-extra.yml"
~~~

test the location using a temporary/test-controlled directory, never pointing to a personal file on a developer machine. For required files, test missing-resource failure too.

### 16.3. EPP Discovery

A unit test calling an `EnvironmentPostProcessor` directly does not verify **META-INF/spring.factories** is valid. When changing bootstrap extensions or upgrading Boot major versions, run a `SpringApplication` test proving the `PropertySource` is added as intended.

---

## 17. Minimum Pre-Release Test Matrix

A matrix keeps teams from missing cases or duplicating tests:

| Case | Input | Expectation | Appropriate Level |
| --- | --- | --- | --- |
| Happy path | Complete config | Bean binds cleanly | Binder/Runner |
| Missing `base-url` | Omitted | `@NotBlank` fails | Runner |
| Blank `base-url` | Empty string | Validation fails | Runner |
| Missing `retry` | No `retry` block | `@NotNull` fails | Runner |
| Invalid attempts | `max-attempts=0` | `@Min` fails | Runner |
| Wrong type | `max-attempts=many` | Conversion fails | Binder |
| Duration units | `connect-timeout=250ms` | Exact `Duration` | Binder |
| Nested endpoint | Blank `host` | Cascaded validation fails | Runner |
| Empty list | Empty `endpoints` | `@NotEmpty` fails | Runner |
| Kebab/camel | `connect-timeout` -> `connectTimeout` | Binds properly | Binder |
| Canonical env | `ACME_GATEWAY_CONNECTTIMEOUT` | Overrides properly | Process/env integration |
| Profile override | Base 2s, prod 5s | Final value 5s | Full app |
| Optional import | File missing | Boots per policy | Full app |
| Required import | File missing | Fails fast | Full app |
| Disabled feature | `enabled=false` | Related bean absent | Runner |
| Deprecated key | Only old key supplied | Follows compatibility policy | Runner/full app |
| Both old/new | Both keys present | Follows published precedence | Full app |
| Metadata packaging | Build artifact | JSON lists public keys | Artifact verification |
| Secret redaction | Fake value | Never leaked in logs/Actuator | Security integration |

Adapt this matrix to actual risk. If a service has no deprecated keys or dynamic sources, skip creating pointless tests just to fill cells.

---

## 18. Testing Metadata Is a Separate Step

Runtime tests will not catch a build bug like annotation processing disabled in CI.

A JAR can execute properly yet lack **META-INF/spring-configuration-metadata.json**, leaving consumers without autocomplete or deprecation warnings.

Add a build-artifact verification step:

1. Build the library/app via the real release flow.
2. Verify the metadata file exists in the final artifact.
3. Parse the JSON cleanly.
4. Assert required public property names exist.
5. Assert critical descriptions and deprecation replacements.
6. Flag stale manual metadata advertising removed keys.
7. Avoid asserting raw JSON array order.

### 18.1. Assertions to Include

~~~text
META-INF/spring-configuration-metadata.json exists
properties contains acme.gateway.base-url
properties contains acme.gateway.connect-timeout
properties contains acme.gateway.retry.max-attempts
properties contains acme.gateway.retry.backoff
property connect-timeout documents expected runtime default
removed/deprecated keys follow release contract
~~~

### 18.2. Do Not Rely Solely on `ClassLoader.getResource`

When multiple test-classpath dependencies contain **spring-configuration-metadata.json**, fetching the "first resource" may inspect a completely different library's metadata.

To verify your module's release artifact, inspect the **build output or exact built JAR**, not an arbitrary file found on the classloader.

### 18.3. Generated Metadata May Miss Dynamic Keys

If code uses:

~~~java
Binder.get(environment).bind(dynamicPrefix, SomeType.class)
~~~

the annotation processor cannot know every runtime-selected prefix. If that forms part of the public contract, provide manual metadata or clear schema docs and tests for permitted prefixes.

---

## 19. Configuration Documentation for Users and Operators

A good README lets operators configure properties without reading Java source.

Recommended outline:

~~~text
Configuration Reference
├── Purpose and module ownership
├── Supported Spring Boot versions
├── Quick start (minimal YAML)
├── Properties table
├── Environment variable names
├── Defaults and required fields
├── Nested List/Map examples
├── Profiles and override order
├── Secret handling
├── Validation and startup errors
├── Deprecated keys and migration
├── Production checklist
└── Troubleshooting
~~~

### 19.1. Sample Properties Table

| Property | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `acme.gateway.base-url` | String | Yes | None | Upstream base URL |
| `acme.gateway.connect-timeout` | Duration | No | 2s | Connection establishment limit |
| `acme.gateway.retry.max-attempts` | int | Yes | None | Attempt count, at least 1 |
| `acme.gateway.retry.backoff` | Duration | Yes | None | Wait time between attempts |
| `acme.gateway.endpoints` | List | Yes | None | Non-empty endpoint list |

This table reflects the **example schema** above; if your project enforces extra rules (such as positive backoff), document them and verify with validators/tests.

### 19.2. Requiredness Is a Business Rule, Not a Java Type

A Java `int` field does not imply "operators must supply this." Depending on binding paths, `int` may stay `0` when absent. To distinguish missing from `0`, use `Integer` with `@NotNull`/`@Min` or an invariant.

Your Required column must reflect actual application behavior, not guesses from variable types.

### 19.3. Defaults Should Include Units

Never write:

~~~text
connect-timeout default = 2000
~~~

leaving readers guessing milliseconds vs seconds. Write **2s** or **2000ms** and match actual `Duration` conversion.

### 19.4. Documentation Samples Must Contain Zero Real Credentials

Use **example.test** domains and safe placeholders in YAML samples. Never copy internal addresses, production hostnames, tokens, or real passwords into READMEs.

---

## 20. Minimal and Full YAML Examples

### 20.1. Minimal Sample

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    retry:
      max-attempts: 3
      backoff: 300ms
    endpoints:
      - name: primary
        host: edge.example.test
        port: 8080
~~~

Here **connect-timeout** is omitted because the record defines `@DefaultValue("2s")`.

### 20.2. Full Sample

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    connect-timeout: 5s
    retry:
      max-attempts: 5
      backoff: 500ms
    endpoints:
      - name: primary
        host: edge-a.example.test
        port: 8080
      - name: secondary
        host: edge-b.example.test
        port: 8081
~~~

Provide distinct examples showing "minimal" vs "customized." Never omit a required field in the minimal example, or users copying it will hit confusing startup errors.

### 20.3. Do Not Cram Every Profile Combination into One Snippet

If local, staging, and prod exist, show one base example plus separate override guidance. Pasting too many YAML blocks together confuses readers about which block actually runs.

---

## 21. Environment Variable and CLI Reference Tables

Canonical path:

~~~text
acme.gateway.connect-timeout
~~~

Canonical environment variable:

~~~text
ACME_GATEWAY_CONNECTTIMEOUT
~~~

Spring Boot's canonical-to-env conversion rule:

1. Dots become underscores.
2. Hyphens are removed.
3. Letters become uppercase.

Similarly:

| Canonical | Environment Variable |
| --- | --- |
| `acme.gateway.base-url` | `ACME_GATEWAY_BASEURL` |
| `acme.gateway.connect-timeout` | `ACME_GATEWAY_CONNECTTIMEOUT` |
| `acme.gateway.retry.max-attempts` | `ACME_GATEWAY_RETRY_MAXATTEMPTS` |
| `acme.gateway.retry.backoff` | `ACME_GATEWAY_RETRY_BACKOFF` |

For List indices, verify exact index syntax across your actual sources rather than assuming a naive conversion without testing.

### 21.1. CLI Override

~~~bash
java -jar gateway.jar \
  --acme.gateway.connect-timeout=7s
~~~

### 21.2. JVM System Property

~~~bash
java -Dacme.gateway.connect-timeout=7s \
  -jar gateway.jar
~~~

### 21.3. Environment Variable

~~~bash
ACME_GATEWAY_CONNECTTIMEOUT=7s java -jar gateway.jar
~~~

These use different source mechanisms. Clearly document precedence among sources permitted by your deployment rather than handing operators copy-paste commands and leaving them guessing which wins.

### 21.4. Never Pass Raw Secrets via CLI

Command-line arguments can appear in shell history, process listings, or logs. For secrets, rely on platform-protected secret injection—never instruct users to paste real tokens into shell commands.

---

## 22. Documenting Precedence and Profiles

Common configuration sources:

- `application.yml` inside the JAR.
- `application-{profile}.yml`.
- Files outside the JAR.
- OS environment variables.
- JVM system properties.
- Command-line arguments.
- Config Data imports.
- Custom sources such as `EnvironmentPostProcessor`, `TestPropertySource`, or `DynamicPropertySource`.

**Spring Boot specifies precedence by source category**, and extensions or test overrides can alter the effective order. Your README should list supported sources and link to the externalized-configuration reference for your exact Boot version.

### 22.1. Profile Override Illustration

~~~yaml
# application.yml
acme:
  gateway:
    connect-timeout: 2s
~~~

~~~yaml
# application-prod.yml
acme:
  gateway:
    connect-timeout: 5s
~~~

When `prod` is active, profile-specific config overrides the base value under Config Data precedence.

### 22.2. Do Not Assume Lists Concatenate Automatically

If the base file defines two endpoints and prod defines a one-element List, Spring Boot normally uses the higher-precedence List instead of concatenating them. Document and test this whenever endpoint lists are critical.

### 22.3. Maps Can Merge Keys

Maps typically merge keys across `PropertySources`, resolving collisions by precedence. If Map keys contain dots or special characters, bracket notation may be needed to preserve keys verbatim.

### 22.4. Switching Profiles Can Change Required Values

A passing local test does not prove `prod` passes. Before release, run smoke tests across supported profiles using safe test data.

---

## 23. Config Data Imports and External Locations

User docs may need to explain loading external files:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway-extra.yml"
~~~

The **`optional:`** prefix allows the location to be absent under Config Data rules.

If a file is mandatory, use a non-optional location and document fail-fast behavior. Never describe a file as optional in the README if code or Config Data requires it.

### 23.1. Relative Paths

Paths like `./config` depend on the process working directory at startup. For containers/deployments, specify the exact mount path and working directory or use platform-managed absolute paths.

### 23.2. Do Not Confuse `spring.config.import` with `location`

**`spring.config.import`** imports configuration documents within Config Data processing. **`spring.config.location`** and **`spring.config.additional-location`** alter location search paths via their own rules.

When docs explain changing locations, state that Config Data-controlling properties must be supplied very early (e.g., env/system/CLI), not after loading has already completed.

### 23.3. Files from Untrusted Sources

Never automatically import or parse arbitrary files supplied by end-user requests without strict controls. Guard paths, permissions, and formats per application security policy.

---

## 24. Documenting Secrets

Every sensitive key needs an explicit policy:

- Who or which system may supply it?
- Are allowed sources a secret store, Kubernetes Secret, mounted file, or environment injection?
- Are special file permissions required?
- Can it rotate at runtime or does it require a restart?
- When missing, does the app fail fast or disable a module?
- When validation fails, what may logs contain?
- Who may inspect Actuator endpoint metadata?
- May the secret appear in startup diagnostics?

### 24.1. Safe Documentation Example

~~~text
ACME_GATEWAY_APIKEY

Purpose:
  Credential used to authenticate with the upstream provider.

Required:
  Only when upstream authentication is enabled.

Supply:
  Through the organization's secret delivery mechanism.

Do not:
  Commit the actual value to application.yml, README, screenshots,
  CI job logs or incident tickets.

Rotation:
  Follow the deployment's restart/refresh policy.
~~~

Never record real values or provide a "default secret" in source code.

### 24.2. Do Not Expose Actuator `env`/`configprops` Publicly

These endpoints aid diagnostics yet demand access control and sanitization. Never set **`show-values=always`** in production just to verify a timeout. Even metadata like source names and file paths can be sensitive.

### 24.3. Leak-Free Tests

Use fake secrets like **dummy-test-key** and assert logs and error responses exclude them. Never bring real tokens into test fixtures just to verify masking.

---

## 25. Designing Configuration Error Messages

When configuration is missing or invalid, clear startup failure cuts diagnosis time.

Example:

~~~text
acme.gateway.retry.max-attempts
~~~

is set to `0`.

Semantically helpful message:

~~~text
Configuration validation failed.
Property: acme.gateway.retry.max-attempts
Constraint: must be greater than or equal to 1
~~~

This illustrates useful message content, not verbatim log text across all versions.

### 25.1. Never Log Rejected Values That Could Be Secrets

Parser/conversion exceptions can embed raw input inside the exception chain. Control how bootstrap exceptions reach logs/tickets, and never construct messages like:

~~~java
"Invalid property " + key + "=" + value
~~~

because `key` and `value` might hold a secret.

### 25.2. Error Classification

| Error Type | Symptom | Where to Investigate |
| --- | --- | --- |
| Missing | Required property absent | Prefix / source / validation |
| Type conversion | Cannot convert String to Java type | Binder & target type |
| Bean Validation | Right type yet violates constraint | `@Validated` / `@Valid` |
| Wrong profile | Expected profile file did not load | Config Data |
| Precedence | Another source overrode the key | `PropertySource` order |
| Metadata missing | IDE lacks hints though code runs | Annotation processor / JAR |
| Bean registration | Cannot inject properties bean | Scan / `@EnableConfigurationProperties` |
| Deprecated key | Deployment uses old name | Migration policy |

Before release, docs should tell operators where to find safe diagnostics without dumping `Environment`.

---

## 26. Pre-Release Review Workflow: Code Changes

For a pull request touching configuration:

1. Identify the prefix and all added, modified, or removed public properties.
2. Identify the owning module.
3. Inspect Java types, constructors/defaults, and nested models.
4. Check required/optional constraints.
5. Evaluate backward compatibility impact.
6. Verify conversion units, list/map semantics, and source precedence.
7. Add Javadoc or manual metadata.
8. Add tests at the lowest level proving behavior.
9. Add integration tests if profiles, Config Data, or bootstrap changed.
10. Update README, deployment samples, and migration guides.
11. Review secret classification and logging.
12. Verify the final artifact packages matching metadata.

This is the **engineering workflow of a release**, not a bureaucratic box-ticking exercise.

### 26.1. A New Property Does Not Always Need Every Test Level

Adding a simple boolean feature flag may need only an `ApplicationContextRunner` bean-condition test. Adding an external Config Data import needs a startup integration test. Adding a record with a nested `List` needs `Binder` and validation tests.

Match tests to the actual change.

---

## 27. Pre-Release Review Workflow: Build Changes

Build pipelines must confirm:

- The annotation processor runs on the right version.
- Metadata generates cleanly and is not empty due to disabled annotation processing.
- Manual metadata merges per processor rules.
- The released JAR contains the metadata.
- Module and Spring Boot dependency versions are compatible.
- Tests execute in an isolated environment.
- Libraries supporting multiple Boot major versions have a matching compatibility matrix.
- No secrets appear in resources, packages, or test reports.
- Release notes cover breaking changes.

### 27.1. Gradle and Maven Do Not Share Identical Task Names

Do not copy Gradle commands into Maven pipelines or vice versa. Document supported build tools and JDK targets clearly.

### 27.2. Local Builds Do Not Replace CI Artifacts

If local builds generate metadata while release artifacts build under different profiles or plugins, verify the **actual released artifact**, not just local build directories.

### 27.3. Library JARs vs Executable JARs

In library JARs, metadata normally lives under `META-INF`. In Spring Boot executable JARs, app metadata sits under `BOOT-INF/classes/META-INF`, while nested libraries under `BOOT-INF/lib` carry their own metadata inside child JARs.

Check archive paths appropriate to your packaging mode rather than applying one path check blindly.

---

## 28. Pre-Release Review Workflow: Documentation

Documentation must serve both developers and operators:

**Developer view:** which class/record binds, needed dependencies, test profiles, YAML and Java examples.

**Operator view:** minimum required keys, env/CLI overrides, defaults and units, when restarts are needed, missing/invalid behavior, secret delivery.

**Upgrader view:** renamed keys, changed defaults, breaking behaviors, aliases, removal timelines.

**Support view:** how to identify the winning source, safe diagnostic info for tickets, how startup errors classify.

### 28.1. Do Not Leave Docs Without an Owner

Every configuration group needs an owner to answer questions about defaults, compatibility contracts, and risks. Unowned keys linger for years because nobody dares remove them.

### 28.2. Docs and Metadata Must Share Canonical Names

If the README writes **acme.gateway.connectTimeout** while metadata uses **acme.gateway.connect-timeout**, operators may use inconsistent names. Stick to canonical kebab-case in doc tables and examples.

### 28.3. Keep Examples Runnable

Minimal examples must include all required branches. If `endpoints` carries `@NotEmpty`, the minimal README snippet must not omit `endpoints` and call itself runnable.

---

## 29. Release Blocking Criteria

A release process needs clear severity tiers rather than treating every issue equally.

### 29.1. Blockers

Issues that should block release:

- A supported application profile fails startup due to missing required config.
- A critical property was renamed without migration or communication.
- A real secret appears in source, metadata, test fixtures, or artifacts.
- Critical validation does not execute or gets bypassed.
- Source precedence prevents safe operator overrides from working.
- A new default shifts production behavior dangerously.
- Schema docs claim a key works yet runtime ignores it.
- A required Config Data import fails in the target environment.
- Bootstrap changes lack tests proving they take effect.

### 29.2. Fix Before Release per Team Policy

- Metadata lacks descriptions for new public properties.
- Hints or deprecation replacements are out of date.
- Env var examples in the README have wrong names.
- A default omits its unit.
- Tests omit invalid cases for an important property.
- Release notes miss behavior changes.

### 29.3. Track Follow-Up If Accepted

- Polishing IDE descriptions for rarely used properties.
- Improving examples for options with no behavioral impact.
- Reorganizing docs when the contract itself is unchanged.

**Final thresholds depend on your organization's risk policy**, yet criteria must be concrete—not just "all tests green."

---

## 30. Using CI as Release Evidence

A reference pipeline:

~~~text
SOURCE CHECKOUT
    |
    v
COMPILE + ANNOTATION PROCESSING
    |
    v
METADATA ARTIFACT VERIFICATION
    |
    v
UNIT + BINDER TESTS
    |
    v
APPLICATIONCONTEXT RUNNER TESTS
    |
    v
PROFILE / CONFIG DATA SMOKE TESTS
    |
    v
SECURITY / SECRET SCANNING
    |
    v
PACKAGE ARTIFACT
    |
    v
VERIFY PACKAGED METADATA
    |
    v
RELEASE NOTES + DEPLOYMENT DOCUMENTATION
    |
    v
RELEASE
~~~

This is an example workflow. Independent steps can be parallelized for speed, yet checks covering the final artifact must inspect the exact artifact being released.

### 30.1. Example Maven Command

~~~bash
./mvnw -B clean verify
~~~

### 30.2. Example Gradle Command

~~~bash
./gradlew clean test build
~~~

Passing commands alone do not prove all production environments are valid. CI also needs representative inputs and profiles, not just compilation.

### 30.3. Metadata Gate Criteria

~~~text
- JSON parses successfully
- Required public property names are present
- No duplicate conflicting contract names without intention
- Deprecated/replacement mappings follow the release plan
- Metadata is inside the final library/JAR
- No raw secrets or production credentials are embedded
~~~

If metadata fails to generate because annotation processing was turned off, this gate must fail before publishing the artifact.

### 30.4. Do Not Commit Generated Files Carelessly

Metadata is normally generated during build. If a repo policy tracks generated files, ensure they stay synced with sources and the processor. Never edit generated JSON in the build directory as a sole fix; edit the Java source or additional metadata.

---

## 31. Release Notes for Configuration Changes

Sample release notes section:

~~~text
Configuration changes

Added:
- acme.gateway.connect-timeout (Duration; default 2s)

Changed:
- acme.gateway.retry.max-attempts now requires >= 1

Deprecated:
- acme.gateway.connection-timeout-ms
  Replacement: acme.gateway.connect-timeout
  Compatibility: supported during the announced migration window

Deployment action:
- Rename the old property in environment variables and YAML.
- Verify that production profile loads the intended override.
- Restart the service if the deployed configuration is read at startup.
~~~

Do not cite these examples as actual release history of a real library; plug in your exact version numbers and policies.

### 31.1. Default Changes Can Be Breaking

Even with an unchanged key name, raising default retries from 3 to 10 can spike request volume and overload upstreams. Release notes must describe impact, not only renames.

### 31.2. Data Type Changes Can Also Be Breaking

Switching `String` to enum, `Duration` to bare milliseconds, or `List` to `Map` can break binding for existing configs. Test compatibility and publish migration steps.

---

## 32. Rollout and Rollback Plan

A configuration contract change should roll out systematically:

1. Publish documentation and change notices.
2. Update deployment templates, Helm values, CI vars, and secret mappings.
3. Enable configuration in staging with test data or staging secrets.
4. Verify startup, validation, and winning property sources.
5. Roll out to a canary or representative service group.
6. Monitor health and non-secret metrics.
7. Expand rollout once error-free.
8. Keep a rollback path compatible with updated configs.

### 32.1. Rolling Back Code Without Rolling Back Configuration

If a new release renames a key and deployment templates switch strictly to the new name, rolling back the JAR to the older release can fail because the older code does not recognize the new key.

Therefore plan migrations **in both forward and rollback directions**. Retaining both keys over a transition period—with clear precedence to prevent conflicts—keeps rollbacks safe.

### 32.2. Never Debug Rollbacks by Dumping Secrets to Logs

If a service fails to boot due to a missing credential, do not enable raw `Environment` dumps to fix it. Inspect secret injection and source presence via authorized tooling without leaking values.

---

## 33. Rules for Shared Libraries

A Spring Boot starter library may serve dozens of consuming apps, making metadata and compatibility even more critical.

### 33.1. Prefixes Need Clear Namespaces

Good:

~~~text
acme.gateway.*
acme.storage.*
acme.audit.*
~~~

Collision-prone:

~~~text
config.*
service.*
settings.*
~~~

Distinct namespaces prevent clashes across multiple libraries and help IDEs group metadata.

### 33.2. Do Not Expose Unstable Internals as Public Properties

If an implementation detail changes frequently, keep it an internal constant or derive it from high-level settings instead of locking down 15 public keys prematurely.

### 33.3. Register Beans Properly

In starters/auto-configurations, **`@EnableConfigurationProperties`** on auto-configuration classes fits better than relying on consuming apps' component scans.

### 33.4. Metadata Must Ship Inside the Library Artifact

Consuming services' IDEs read metadata from the dependency JAR. Do not generate metadata only in a demo app and forget to package it with the library itself.

### 33.5. Test Compatibility Across Declared Boot Versions

If a library claims support for multiple Spring Boot major/minor versions, verify both build and runtime against your published compatibility matrix. Compiling on one version does not guarantee all target versions work, especially when extension points or packages shift.

---

## 34. Reviewing During a Spring Boot Upgrade

When upgrading Boot versions, your configuration contract can be affected by:

- Renamed or deprecated Spring Boot properties.
- Changed auto-configuration defaults.
- Changed starter dependencies.
- Jakarta/Javax package migrations in relevant releases.
- Constructor binding and annotation processing changes.
- Config Data, bootstrap, or profile rule changes.
- Module/package moves for extensions like `EnvironmentPostProcessor`.
- Actuator access/exposure changes.
- Classpath changes for custom converters and Bean Validation providers.

### 34.1. Never Upgrade by Bumping Only Dependency Versions

Read target release notes and migration guides, and run representative configuration tests. Deprecated-property metadata catches some keys, yet tooling cannot catch every behavioral shift.

### 34.2. `@Value` vs `@ConfigurationProperties`

Some `@Value` properties using camelCase placeholders do not enjoy the same relaxed binding as canonical kebab-case. During upgrades or refactors, verify environment variables and property files still bind as intended.

### 34.3. Manual Metadata Can Go Stale

If a property moves to a new class, changes type, or becomes internal, update manual metadata accordingly. Presence in JSON does not prove the new release still reads it.

---

## 35. Pull Request Reviewer Checklist

- [ ] Canonical names and prefixes of new properties are clear.
- [ ] New properties belong to a defined module/owner.
- [ ] Java types and conversions have been tested.
- [ ] Requiredness and defaults match runtime behavior.
- [ ] `@Validated`/`@Valid`/`@NotNull` and constraints fit their purpose.
- [ ] List/Map missing, empty, and key rules are clear.
- [ ] Env variable names in docs follow canonical rules.
- [ ] Profile/env/CLI overrides are not masked by defaults.
- [ ] Public keys are not renamed without a migration contract.
- [ ] Additional metadata does not advertise unused properties.
- [ ] Deprecation/replacement metadata is accurate.
- [ ] No raw credentials exist in Javadoc, JSON, or samples.
- [ ] Binder or Runner tests cover both happy and invalid paths.
- [ ] Bootstrap changes have matching `SpringApplication` integration tests.
- [ ] README and deployment templates are updated.
- [ ] Release notes call out breaking changes and operator actions.
- [ ] Final build packages generated metadata cleanly.

Apply this checklist to **configuration changes**, not as an excuse to touch unrelated modules in the same pull request.

---

## 36. SRE/DevOps Pre-Deploy Checklist

- [ ] Verified Spring Boot version and build artifact to deploy.
- [ ] Verified active profiles.
- [ ] Verified Config Data files, imports, and locations used.
- [ ] Verified required properties have valid sources.
- [ ] Verified secrets use secure delivery, never public files.
- [ ] Verified env variable names match canonical properties.
- [ ] Confirmed precedence policy when file/env/CLI overlap.
- [ ] Reviewed and approved critical defaults.
- [ ] Verified timeouts, retries, and pool sizes have explicit units and bounds.
- [ ] Confirmed no unaddressed deprecated properties remain.
- [ ] Ran staging smoke tests / startup checks.
- [ ] Prepared a rollback plan covering both code and deployment config.
- [ ] Verified diagnostics exist to identify winning sources without printing raw values.
- [ ] Verified sensitive Actuator endpoints are secured.
- [ ] Confirmed debug logging never dumps full `Environment`.
- [ ] Confirmed owner/support contacts and escalation docs are clear.

A good operator checklist must be usable **without requiring operators to read Java source**.

---

## 37. Runbook: IDE Does Not Suggest a Property

Symptom: typing **acme.gateway.connect-timeout** in `application.yml` yields no IDE autocomplete.

Investigate in order:

1. Does the module have `@ConfigurationProperties` properly applied?
2. Does the build include `spring-boot-configuration-processor`?
3. Did annotation processing actually run?
4. Does the generated JSON include the key?
5. Does the final JAR contain the metadata file?
6. Does the consuming service pull the dependency version containing metadata?
7. Did the IDE index metadata from that dependency properly (try refreshing caches)?
8. Is manual metadata valid and properly merged?
9. Is the key dynamic and therefore uninferable by the processor?

**Never conclude runtime binding fails just because the IDE lacks autocomplete.** Metadata and Binder have separate responsibilities.

### 37.1. JSON Has the Key, Yet the IDE Misses It

Inspect dependency artifacts, IDE caches, indexing, and resource packaging. Never rewrite binding code when the issue is purely tooling.

### 37.2. Metadata Lacks the Key

Check processor config, record Javadoc, getter/constructor visibility, Lombok processor order, or manual metadata. Adding keys manually helps once you understand why runtime accepts them.

---

## 38. Runbook: Property Set in YAML, Yet Bean Receives Default

Likely causes:

- Wrong prefix or YAML indentation.
- Non-canonical property name.
- Profile loaded another file that overrode it.
- Higher-precedence environment variable, JVM property, or CLI argument.
- Constructor default hid "operator omitted key."
- Bean instantiated without constructor binding.
- Custom converter or `BindHandler` altered binding.
- List replacement wiped out base-file entries.
- Object was bound before runtime updates and did not refresh.

Steps:

1. Verify canonical key spelling and nested path.
2. Check active profiles and source names in a protected environment.
3. Identify the winning source via `PropertySource`/`ConfigurationPropertySource` safely.
4. Check type conversion.
5. Check bean registration.
6. Check defaults and validation.
7. Reproduce in a Binder/Runner test using fake data.
8. Fix config or code at the right layer without enabling raw `Environment` dumps.

### 38.1. Never Print Secrets

If a key may hold a password/token, log only status, source category, and failure category. Never paste values into issues or pipeline logs.

---

## 39. Runbook: One Profile Starts, Another Fails

Example: local passes, prod fails startup.

Investigate:

- Is the `prod` profile actually active?
- Is `application-prod.yml` in the right location?
- Is a required Config Data import present?
- Did a prod List override drop a required property?
- Does a new value have the wrong type or unit?
- Are prod secret injections complete?
- Did `@ConditionalOnProperty` activate an extra bean needing new config?
- Is the deployment platform injecting an env/CLI override?

### 39.1. Pick the Right Test to Reproduce

If `"many"` fails converting to `int`, a Binder test reproduces it.

If `prod` fails to load a Config Data file, use a `SpringApplication`/bootstrap test.

If a bean activates only when a flag is true, `ApplicationContextRunner` tests the condition.

---

## 40. Runbook: Legacy Key Stopped Working After Upgrade

A deployment still passes:

~~~text
acme.gateway.connection-timeout-ms
~~~

yet new code binds only:

~~~text
acme.gateway.connect-timeout
~~~

Without a migration alias, the old key is ignored and the new default applies.

### 40.1. Check Release Info

- Do release notes document the rename?
- Does metadata list a deprecation replacement?
- Does JavaBean/alias logic actually support the old name?
- Are there legacy-only tests?
- Are there tests with both old and new present?
- What is the precedence policy when both coexist?
- Were environment variables updated in deployment templates?

### 40.2. Never Fix by Adding a Hardcoded Default

If the root cause is an unbound legacy key, adding a default just so the app starts masks compatibility breakage. Fix the mapping or update deployments per contract.

---

## 41. Exercise 1: Identify What Is Missing

A project defines:

~~~java
@ConfigurationProperties(prefix = "acme.worker")
public record WorkerProperties(int concurrency) {}
~~~

Runtime binds and runs fine, yet the IDE does not suggest `acme.worker.concurrency`.

List the steps:

1. Check whether the annotation processor ran.
2. Check whether the build artifact contains `spring-configuration-metadata.json`.
3. Check whether the JSON lists the exact property name.
4. If missing, check processor configuration and source discovery.
5. If present, check IDE indexing, dependency version, and packaging.

**No need to add `@SpringBootTest` just to prove IDE autocomplete**, since that is a metadata/tooling contract concern.

## 42. Exercise 2: Metadata or Validation?

Metadata:

~~~json
{
  "properties": [
    {
      "name": "acme.pool.max-connections",
      "type": "java.lang.Integer",
      "defaultValue": 20
    }
  ]
}
~~~

A user passes `max-connections=0`.

Does metadata reject it automatically? **No.** Metadata describes types and defaults; it does not replace Bean Validation. If at least 1 connection is required, add a runtime constraint/invariant and a test proving enforcement.

## 43. Exercise 3: Testing at the Right Level

Match each case:

- Java object test for defensive copying.
- Binder test for **read-timeout=250ms**.
- `ApplicationContextRunner` for `@Validated` nested object failure.
- Full app test for `application-prod.yml`, Config Data imports, and `EnvironmentPostProcessor` discovery.

**Bonus exercise:** if a `@SpringBootTest` takes several seconds just to assert String → `Duration`, move it to a `Binder` test while keeping representative integration smoke tests.

## 44. Exercise 4: Inconsistent Defaults

Runtime:

~~~java
@DefaultValue("5s") Duration timeout
~~~

Manual metadata:

~~~json
{
  "name": "acme.gateway.timeout",
  "defaultValue": "2s"
}
~~~

Problem: IDEs and docs advertise `2s` while runtime uses `5s` when the key is missing.

Fix: establish the **true default**, align Java, manual metadata, and docs, and add a missing-key startup test verifying the value. Never casually change runtime defaults just to match JSON if doing so would be an unapproved breaking change.

## 45. Exercise 5: Deprecated Metadata Is Not Automatic Compatibility

An `old-timeout` key has metadata:

~~~json
{
  "deprecation": {
    "replacement": "acme.gateway.connect-timeout"
  }
}
~~~

Does that automatically map `old-timeout` to `connect-timeout`? **No.** Implement a runtime alias/legacy binding or require explicit migration. Test old-only and both-present if continuing support.

## 46. Exercise 6: Environment Variable Names

Canonical:

~~~text
acme.gateway.retry.max-attempts
~~~

Standard env name:

~~~text
ACME_GATEWAY_RETRY_MAXATTEMPTS
~~~

Do not insert an underscore at the hyphen to write **MAX_ATTEMPTS** when following Spring Boot's canonical-to-env rules.

To verify real OS env behavior, test with env-source semantics or launch the process with the actual environment variable set.

## 47. Exercise 7: Should Source Metadata Be Exposed Publicly?

An internal helper proposes returning all `PropertySource` names and values via a public API for error reporting.

Major risk: leaks secrets, infrastructure paths, or tenant names.

Sound solution: authenticate and authorize diagnostic endpoints, allowlist keys, return only source categories and classified error codes—never raw values or the full `Environment`.

---

## 48. Configuration Release Ticket Template

Use this template in pull requests or release tickets:

~~~text
Configuration change summary
----------------------------
Module/prefix:
Owner:
Spring Boot target versions:

Added properties:
Changed properties:
Deprecated properties:
Removed properties:

Defaults before:
Defaults after:
Required fields:
Validation constraints:
Data types and units:

Migration policy:
Old/new precedence:
Compatibility window:
Rollback requirements:

Metadata:
- Processor configured:
- Generated JSON verified:
- Packaged metadata verified:

Tests:
- Object/Binder:
- ApplicationContextRunner:
- Full application/profile/import:
- Security/redaction:

Documentation:
- Properties table:
- YAML sample:
- Environment variable examples:
- Secret handling:
- Troubleshooting:
- Release notes:

Deployment:
- Staging profile test:
- Canary/rollback plan:
- Owner approval:
~~~

The goal is making configuration changes evidence-backed decisions instead of leaving teams guessing how to use new keys.

---

## 49. Official Documentation to Cross-Check by Version

Reference links:

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Configuration Metadata Format: https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html
- Spring Boot — Generating Your Own Metadata: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 — Annotation Processor Details: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/
- Spring Boot — Test Utilities: https://docs.spring.io/spring-boot/reference/testing/test-utilities.html
- Spring Boot — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html

Projects upgrading from Boot 3 to Boot 4 must read documentation for the **target version**, rather than relying on older snippets. Annotation processing, module packaging, startup extensions, and actuator settings can change across versions.

---

## 50. Summary

Pre-release configuration review is a structured process for verifying the **configuration contract** of a Spring Boot application or library.

**Metadata** lets users and IDEs discover keys, types, descriptions, defaults, hints, and deprecation status. It is generated by **spring-boot-configuration-processor** and supplemented via **additional-spring-configuration-metadata.json**. Always verify metadata **inside the final artifact**.

**Testing** verifies real behavior: Java object tests for invariants, `Binder` tests for names/conversions/nested binding, `ApplicationContextRunner` for beans/validation/conditions, and full `SpringApplication` tests for profiles, Config Data, bootstrap, and integration. Not every field needs every test level, yet never use a lower-level test to claim an untested mechanism works.

**Operator documentation** must explain canonical names, defaults, required fields, units, env var mappings, source precedence, profiles/imports, secret handling, startup errors, deprecations, and migration. Minimal examples must be runnable and contain zero real credentials.

A release is ready when all three layers reflect **one unified contract**: which properties are supported, how they are supplied, how runtime consumes them, what inputs are rejected, and what operators must do during upgrades or rollbacks.

The final question for reviewers is not just "Did the JAR build cleanly?", but: **"Can users discover, configure, verify, and upgrade this application without guessing or exposing secrets?"**
