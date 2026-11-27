# Spring Boot, Binder, and Binding Configuration Precedence Order

A Spring Cloud Stream application using Pulsar can receive configuration from Spring Boot, from the Pulsar binder, and from individual input/output bindings. When the same option appears in multiple places, the application must know which value takes effect. Without distinguishing these scopes, a change in a configuration file may appear to have no effect, or one binding may accidentally share a timeout, schema, or subscription with other bindings.

For the Pulsar binder, the Spring Cloud Stream documentation clearly states the precedence order for the same Pulsar option as **extended binding properties → binder properties → Spring Boot properties** (from highest to lowest priority). In addition, Spring Boot has a separate precedence order across configuration sources such as YAML files, environment variables, system properties, and command-line arguments. These two precedence orders answer two different questions and should not be collapsed into a single list.

This lesson uses an application with `Supplier`/`Function`/`Consumer` beans to illustrate how to place shared settings, binder settings, and binding-specific settings. The examples focus on the Spring Cloud Stream Pulsar binder; the common Spring Cloud Stream configuration parts apply to other binders as well, though the names and semantics of extended properties depend on each binder.

Reference links in this lesson correspond to Spring Cloud Stream 5.1.0 and Spring Boot 4.2.0. If your project uses a different release train, re-check the configuration metadata and reference docs for your exact version, as properties can be renamed or bind differently.

## 1. Four Common Configuration Scopes

First, distinguish the prefix groups:

| Scope | Example prefix | Purpose |
|---|---|---|
| Spring Boot / Spring for Apache Pulsar | `spring.pulsar.*` | Shared client, producer, consumer, and administration settings across the application |
| Application-level Pulsar binder | `spring.cloud.stream.pulsar.binder.*` | Shared Pulsar settings applied through the binder to bindings |
| Spring Cloud Stream common binding | `spring.cloud.stream.bindings.<bindingName>.*` | Destination, group, content type, binder, and common producer/consumer properties for one binding |
| Pulsar extended binding | `spring.cloud.stream.pulsar.bindings.<bindingName>.*` | Settings specific to one binding supported by the Pulsar binder, such as schema type, message type, or producer/consumer options |

Beyond these prefixes, Spring Cloud Stream also provides default prefixes:

- `spring.cloud.stream.default.*` applies common defaults to bindings.
- `spring.cloud.stream.pulsar.default.<producer|consumer>.*` applies shared extended defaults to Pulsar bindings when supported by the binder.
- Binding-specific configuration can override the corresponding default values.

Do not confuse `spring.cloud.stream.pulsar.binder` with `spring.cloud.stream.binders.<configurationName>`. The first prefix configures the Pulsar binder type. The second prefix declares a named binder configuration instance, commonly used when an application has multiple binders or multiple broker connections.

## 2. Pulsar Binder Precedence Diagram

When the same Pulsar option is declared at all three levels, the binder applies them in this order:

~~~mermaid
flowchart TD
    A[Extended binding properties<br/>spring.cloud.stream.pulsar.bindings.name.*] -->|Highest priority| D[Effective value for binding]
    B[Binder properties<br/>spring.cloud.stream.pulsar.binder.*] -->|Fallback if not set on binding| D
    C[Spring Boot Pulsar properties<br/>spring.pulsar.*] -->|Lower fallback| D
~~~

Example with the same `send-timeout` property:

| Level | Configuration key | Value |
|---|---|---:|
| Spring Boot | `spring.pulsar.producer.send-timeout` | `30s` |
| Pulsar binder | `spring.cloud.stream.pulsar.binder.producer.send-timeout` | `20s` |
| Binding `publishOrder-out-0` | `spring.cloud.stream.pulsar.bindings.publishOrder-out-0.producer.send-timeout` | `5s` |

Result: binding `publishOrder-out-0` uses `5s`. Other producer bindings without their own value use the binder setting `20s`; if the binder also omits it, they fall back to Spring Boot's `30s`.

This order governs precedence **across Pulsar binder scopes for the same option**. It does not mean every key under `spring.cloud.stream.bindings` always overrides every key under `spring.pulsar`. Compare the exact property type and exact prefix defined by the binder documentation.

## 3. Spring Boot Property-Source Precedence Is an Orthogonal Axis

Spring Boot reads values from multiple sources. When the **exact same key** appears in multiple sources, the higher-precedence source wins. For a standard running application, common sources from lowest to highest precedence include:

1. Default properties set via `SpringApplication.setDefaultProperties`.
2. `@PropertySource` annotations on configuration classes.
3. Config data, including `application.yml` and profile-specific files.
4. Random value property source.
5. OS/container environment variables.
6. Java system properties (`-D...`).
7. JNDI and servlet context/config init parameters if used by the environment.
8. `SPRING_APPLICATION_JSON`.
9. Command-line arguments such as `--spring.pulsar.producer.send-timeout=...`.

Test sources such as `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, and `@TestPropertySource` follow their own rules within test contexts. Consult the reference for your exact Spring Boot version when exact test precedence matters.

Within Config Data, the typical order is:

| File source | Precedence |
|---|---|
| `application.yml` packaged inside JAR | Lower |
| `application-{profile}.yml` packaged inside JAR | Higher than packaged base file |
| `application.yml` outside JAR | Higher than packaged files |
| `application-{profile}.yml` outside JAR | Higher than external base file |

Command-line arguments override the same key in configuration files by default. Environment variables and system properties can also override files; the exact order follows Spring Boot's property source hierarchy.

## 4. Why the Two Orders Cannot Be Merged Into One

Suppose there are two keys:

~~~text
spring.pulsar.producer.send-timeout
spring.cloud.stream.pulsar.bindings.publishOrder-out-0.producer.send-timeout
~~~

These are **two different keys**. If the command line overrides the first key, it changes only the Spring Boot-level value. If the second, binding-level key is still declared, the Pulsar binder still applies the binding-level value because the extended binding scope has higher precedence than binder/Boot for the same option.

Example:

~~~bash
java -jar order-app.jar \
  --spring.pulsar.producer.send-timeout=45s
~~~

If the configuration file still contains:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
~~~

Then binding `publishOrder-out-0` still uses `5s`. The command-line argument changed the value of the Spring Boot-level key, but did not remove or override the distinct binding-level key.

This is the most important takeaway when debugging: **property-source precedence selects the value for the same key; binder-scope precedence selects which configuration scope applies to the binding**.

## 5. Default Configuration for Spring Cloud Stream

Spring Cloud Stream provides common binding properties and default properties. Example setting shared consumer retries, then overriding a single binding:

~~~yaml
spring:
  cloud:
    stream:
      default:
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1s
          back-off-max-interval: 10s
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-service
          consumer:
            max-attempts: 5
        auditOrder-in-0:
          destination: order-audit
          group: audit-service
~~~

In this example:

- `max-attempts: 3` is the default for consumer bindings that do not declare their own value.
- `processOrder-in-0` sets `max-attempts: 5`, so it uses 5 attempts (including the initial attempt).
- `auditOrder-in-0` does not override it, so it uses the default of 3.
- `destination` and `group` are declared per binding because they describe specific targets and consumer groups.

Binding names are derived from function bean names. For example, a `Consumer<T>` bean named `processOrder` has default binding `processOrder-in-0`. If you rename the function or use an alias via `spring.cloud.stream.function.bindings`, update the binding name in configuration accordingly.

Do not place `destination` under `spring.cloud.stream.default` expecting every binding to share one topic automatically. Destination is a per-stream choice and should be configured per binding.

## 6. Pulsar Configuration at the Spring Boot Level

`spring.pulsar.*` properties come from Spring for Apache Pulsar and Spring Boot auto-configuration. They provide baseline values for the application:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    admin:
      service-url: http://pulsar-admin:8080
    producer:
      send-timeout: 30s
      batching-enabled: true
    consumer:
      subscription:
        type: Shared
~~~

Exact properties depend on the Spring Boot/Spring for Apache Pulsar version. This example illustrates where client URL, admin URL, producer, and consumer settings live; verify property names in the configuration properties appendix for your exact version before deploying.

These settings are normally shared across the application context. If an application has multiple functions and multiple Pulsar bindings, they are not the right way to set two different timeouts or subscriptions per binding. When per-binding differences are needed, use extended binding properties.

## 7. Pulsar Configuration at the Binder Level

The Pulsar binder allows setting certain Spring for Apache Pulsar properties at the binder level:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            send-timeout: 20s
            batching-enabled: true
          consumer:
            subscription:
              type: Shared
~~~

These properties apply generally across the Pulsar binder in the application. According to the binder documentation, they take precedence over corresponding properties under `spring.pulsar.*` while having lower precedence than per-binding extended properties.

For example, if `spring.pulsar.producer.send-timeout` is `30s` and the binder-level `send-timeout` is `20s`, producer bindings that do not set their own timeout receive `20s`.

Do not confuse this binder level with configuring connections for multiple binder instances. `spring.cloud.stream.pulsar.binder.*` configures the Pulsar binder type; `spring.cloud.stream.binders.<configurationName>.*` declares a named binder configuration and can contain its own environment.

## 8. Pulsar Extended Binding Configuration per Stream

When two output bindings need different schemas or producer options, set extended properties by binding name:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
              schema-type: JSON
              message-type: com.example.events.OrderCreated
          publishAudit-out-0:
            producer:
              send-timeout: 15s
              schema-type: AVRO
              message-type: com.example.events.AuditRecord
~~~

Here:

- `publishOrder-out-0` has a 5-second timeout and JSON schema.
- `publishAudit-out-0` has a 15-second timeout and Avro schema.
- These values apply only to their respective bindings.
- Other bindings without specific settings use extended defaults or appropriate binder/Boot-level fallbacks.

Binding names must match the function bean and message direction exactly. `Supplier` has an output binding; `Consumer` has an input binding; `Function` typically has both input and output bindings. Do not put the topic name in place of the binding name in the configuration prefix.

## 9. Combining Core Binding Properties with Pulsar Extended Properties

Some options belong to Spring Cloud Stream core, while others belong to the Pulsar binder. When using native Pulsar schemas, these two groups are usually declared together:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://public/default/orders
          producer:
            use-native-encoding: true
        processOrder-in-0:
          destination: persistent://public/default/orders
          group: order-service
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.example.events.OrderCreated
          processOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.example.events.OrderCreated
~~~

`use-native-encoding` and `use-native-decoding` are core Spring Cloud Stream binding properties. `schema-type` and `message-type` are Pulsar extended binding properties. Both groups must be consistent: producer native encoding and consumer native decoding must use compatible schemas and types.

If native encoding/decoding is not enabled, Spring Cloud Stream defaults to framework content types and message conversion. In that case, do not add schema types just because Pulsar is being used; choose one consistent serialization model and verify actual bytes on the topic.

## 10. Configuring Extended Defaults for Pulsar Bindings

When multiple bindings share the same Pulsar producer or consumer settings, you can use binder-type extended defaults:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        default:
          producer:
            send-timeout: 10s
          consumer:
            subscription:
              type: Shared
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
~~~

`spring.cloud.stream.pulsar.default.producer` and `...default.consumer` set extended defaults for the binder type. Binding `publishOrder-out-0` sets an explicit value, overriding the corresponding default.

Use only properties actually supported by the Pulsar extended configuration classes. A key that does not exist in the binder's metadata does not become valid simply by placing it under the `default` prefix. Check configuration metadata or the reference for your exact version.

## 11. Selecting a Binder for a Binding

In addition to choosing property values, Spring Cloud Stream must determine which binder creates each binding. If only one binder is on the classpath, it is usually selected automatically. When multiple binders exist, you can set a default or specify a binder per binding:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: pulsar
      bindings:
        publishOrder-out-0:
          binder: pulsar
          destination: orders
        audit-out-0:
          binder: rabbit
          destination: order-audit
~~~

`binder` is a common binding property selecting the binder for a specific binding. `default-binder` is the fallback when a binding does not specify a binder. These two properties are not Pulsar producer/consumer options; they determine which binder a binding uses.

If a binding is assigned to the RabbitMQ binder, Pulsar extended properties are not applied to that binding. Use the extended configuration belonging to the respective binder.

## 12. Distinguishing Binder Type from Binder Configuration Instance

When connecting to multiple Pulsar clusters, you can declare two binder configuration instances of the same type:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        pulsarWest:
          type: pulsar
          environment:
            spring:
              pulsar:
                client:
                  service-url: pulsar://pulsar-west:6650
        pulsarEast:
          type: pulsar
          environment:
            spring:
              pulsar:
                client:
                  service-url: pulsar://pulsar-east:6650
      bindings:
        publishWest-out-0:
          binder: pulsarWest
          destination: orders
        publishEast-out-0:
          binder: pulsarEast
          destination: orders
~~~

`pulsarWest` and `pulsarEast` are configuration names; `type: pulsar` selects the binder implementation. Both use the Pulsar binder while pointing to different clusters.

This is Spring Cloud Stream's multi-binder mechanism, distinct from `spring.cloud.stream.pulsar.binder.*`. When configuring a separate `environment`, understand `inheritEnvironment` and binder contexts: properties inside a binder environment can be isolated from the main application context depending on configuration. Do not assume every application variable or bean automatically exists in the binder context when environments are separated.

## 13. Complete Example: An Application with Producer and Consumer

Application with two functions:

~~~java
package com.example;

import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderCreated(String orderId, String status) {}

@Configuration
class OrderFunctions {

    @Bean
    Supplier<OrderCreated> publishOrder() {
        return () -> new OrderCreated("O-100", "CREATED");
    }

    @Bean
    Consumer<OrderCreated> processOrder() {
        return event -> System.out.println(
                "Processing order " + event.orderId());
    }
}
~~~

This example only illustrates binding names; the supplier returns the same event on every poll and is not meant for direct production use. A real source must generate distinct events with stable event IDs and handle redelivery safely.

Configuration:

~~~yaml
spring:
  application:
    name: order-pulsar-app
  pulsar:
    client:
      service-url: pulsar://pulsar:6650
    producer:
      send-timeout: 30s
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      default:
        consumer:
          max-attempts: 3
      bindings:
        publishOrder-out-0:
          destination: persistent://public/default/orders
          producer:
            use-native-encoding: true
        processOrder-in-0:
          destination: persistent://public/default/orders
          group: order-service
          consumer:
            max-attempts: 5
            use-native-decoding: true
      pulsar:
        binder:
          producer:
            send-timeout: 20s
        default:
          producer:
            send-timeout: 10s
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
              schema-type: JSON
              message-type: com.example.OrderCreated
          processOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.example.OrderCreated
~~~

Explanation of results:

- The producer on binding `publishOrder-out-0` uses a 5-second timeout because the specific extended binding beats the binder-level 20 seconds, extended default 10 seconds, and Spring Boot 30 seconds.
- Other Pulsar producer bindings without a specific timeout can use the extended default of 10 seconds; if no extended default is present, they use the binder-level 20 seconds, and finally Spring Boot's 30 seconds.
- Consumer `processOrder-in-0` uses `max-attempts: 5` because the specific common binding overrides the common default of 3.
- Native encoding/decoding is enabled at the core binding level; schema/type settings are placed at the Pulsar extended binding level.
- Both bindings declare explicit destinations; the consumer group is declared on the input binding.

When applying this, ensure the Pulsar binder dependency and message type classes in the right package are on the classpath. If using default framework conversion instead of Pulsar native schemas, remove the corresponding native encoding/decoding and schema/message type settings.

## 14. How Spring Boot Overrides the Same Key

Suppose the packaged file contains:

~~~yaml
spring:
  pulsar:
    producer:
      send-timeout: 30s
~~~

An external file outside the JAR contains:

~~~yaml
spring:
  pulsar:
    producer:
      send-timeout: 40s
~~~

For the same key, the external file takes precedence over the packaged file in Spring Boot's default configuration. If an environment variable sets another value, it can override further:

~~~bash
SPRING_PULSAR_PRODUCER_SENDTIMEOUT=50s
~~~

If launched with:

~~~bash
java -jar order-app.jar --spring.pulsar.producer.send-timeout=60s
~~~

then the Spring Boot-level value for that key becomes 60 seconds because command-line arguments take precedence over configuration files. However, if the binding-specific extended property remains 5 seconds, that binding continues using 5 seconds per Pulsar binder precedence.

Environment variables use relaxed binding rules: dots become underscores, hyphens are removed, and characters are uppercased. For deeply nested keys, verify the exact environment variable name bound by Spring Boot to avoid typos.

## 15. Profiles and External Configuration

You can use profiles to supply environment-specific configuration:

~~~yaml
# application.yml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-dev:6650
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            send-timeout: 20s
~~~

~~~yaml
# application-prod.yml
spring:
  pulsar:
    client:
      service-url: pulsar-prod.internal:6650
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            send-timeout: 30s
~~~

When the `prod` profile is active, the profile file is loaded per config data rules and can override base file values. Per-binding values can still override binder-level values if declared.

If `spring.config.location` is used, Spring Boot replaces default search locations with the specified ones. If you only want to add external config files while keeping default locations, use `spring.config.additional-location`. A file imported via `spring.config.import` is processed as additional config data and can override the importing file.

Avoid creating too many profile files containing the same keys without clear conventions. Document configuration sources per environment so investigations can immediately tell whether a value comes from a file inside the image, a mounted file, an environment variable, or startup flags.

## 16. Defaults Are Not Always Overridable Properties

Some values are framework/binder-computed defaults when a property is omitted:

- Default binding names are generated from function bean names and input/output direction.
- Default destinations may fall back to binding names if no destination is specified.
- The Pulsar binder may apply default schema mappings when no schema type is specified.
- Certain producer/consumer options inherit defaults from Spring for Apache Pulsar or the Pulsar client.

Not every default can be set under the `spring.cloud.stream.default` prefix. That prefix applies only to common binding properties supported by Spring Cloud Stream. For extended properties, use the binder-type default prefix or binding-specific prefix. For Pulsar client defaults, consult Spring for Apache Pulsar configuration properties.

For example, `spring.cloud.stream.default.consumer.max-attempts` is a common binding default; it does not automatically set `schema-type` for Pulsar. Conversely, `spring.cloud.stream.pulsar.default.consumer.schema-type` makes sense only if the Pulsar binder exposes that property on extended consumer properties.

## 17. Properties That Should Not Be Placed at the Wrong Level

| Need | Appropriate placement | Reason |
|---|---|---|
| Shared Pulsar service URL | `spring.pulsar.client.service-url` | Spring Boot-level client configuration |
| Shared producer send timeout via Pulsar binder | `spring.cloud.stream.pulsar.binder.producer.send-timeout` | Applies broadly to producer bindings |
| Send timeout for one specific output | `spring.cloud.stream.pulsar.bindings.<name>.producer.send-timeout` | Only that binding uses the specific value |
| Default consumer retries | `spring.cloud.stream.default.consumer.max-attempts` | Common binding default |
| Specific consumer retries | `spring.cloud.stream.bindings.<name>.consumer.max-attempts` | Core binding property |
| JSON schema for a specific Pulsar output | `spring.cloud.stream.pulsar.bindings.<name>.producer.schema-type` | Pulsar extended property |
| Native encoding for an output | `spring.cloud.stream.bindings.<name>.producer.use-native-encoding` | Core Spring Cloud Stream property |
| Selecting a binder for an input | `spring.cloud.stream.bindings.<name>.binder` | Chooses the binding's binder implementation |
| Configuring a named Pulsar cluster | `spring.cloud.stream.binders.<configurationName>` | Declares a binder configuration instance |

If a key does not exist in the property metadata for the exact module/version, check whether it belongs under a different prefix. Do not move properties across prefixes merely because the trailing key name looks similar.

## 18. Checking Which Configuration Is Actually Effective

When an application uses an unexpected value, follow this sequence:

1. Write down the exact key to inspect, such as `send-timeout` or `max-attempts`.
2. Identify whether the key belongs to Spring Boot Pulsar, Pulsar binder, core binding, or Pulsar extended binding.
3. List every location declaring that key: application YAML, profile YAML, mounted files, environment variables, system properties, and command line.
4. Verify the exact binding name, including `-in-0`/`-out-0` suffixes.
5. Apply binder-scope precedence for the same Pulsar option.
6. Then inspect Spring Boot `PropertySource` precedence to see which source supplied each key's value.
7. Verify via logs and integration tests whether the binder translated the config into actual producers/consumers.

Actuator's `env` and `configprops` endpoints can help identify property sources and values bound into configuration objects. Expose them only in administrative environments, protect them with authentication/authorization, and verify sanitization because broker configurations can contain secrets. Never paste raw outputs containing credentials into tickets or public logs.

In code, you can inspect values through `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class PulsarConfigDiagnostic {

    PulsarConfigDiagnostic(Environment environment) {
        String bootSendTimeout = environment.getProperty(
                "spring.pulsar.producer.send-timeout");
        String binderSendTimeout = environment.getProperty(
                "spring.cloud.stream.pulsar.binder.producer.send-timeout");
        String bindingSendTimeout = environment.getProperty(
                "spring.cloud.stream.pulsar.bindings.publishOrder-out-0.producer.send-timeout");

        // Log only non-sensitive values in test environments.
    }
}
~~~

`Environment` shows values by key in the Spring `Environment`; it does not compute the final merged value after the Pulsar binder resolves scopes. To confirm the effective value, inspect the bound configuration objects or consumer/producer bindings after the binder applies configuration, or observe actual behavior with tests.

## 19. Testing Precedence Rather Than Just Checking YAML Files

A good configuration test proves the effective value at runtime rather than simply checking that a file contains expected strings.

Example test matrix:

| Test | Boot-level | Binder-level | Binding-level | Expected result |
|---|---:|---:|---:|---:|
| Boot only | 30s | — | — | 30s |
| With binder | 30s | 20s | — | 20s |
| With binding | 30s | 20s | 5s | 5s |
| Another binding | 30s | 20s | — | 20s |
| CLI changes Boot key | 60s | 20s | 5s | 5s for the specified binding |

In integration tests:

- Use isolated contexts to avoid beans/configs from previous tests affecting results.
- Supply properties via test property sources or dynamic property sources with explicit keys.
- Inspect the bound configuration objects.
- For critical producer/consumer options, spin up a Pulsar test broker or integration environment and verify actual behavior.
- Verify at least one binding without an override to confirm fallback behavior.
- Verify a specific binding does not accidentally inherit another binding's settings.

Spring Cloud Stream's Test Binder is helpful for testing function logic and bindings, but it does not automatically verify every native Pulsar producer/consumer option. For schemas, partition counts, subscriptions, or send timeouts, run integration tests using the real Pulsar binder.

## 20. Pulsar Topic Partition Count Also Has Two Levels

The Pulsar binder supports setting partition counts when provisioning topics:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 8
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 16
          publishAudit-out-0:
            producer:
              partition-count: 4
~~~

Binder-level `partition-count: 8` is the shared default for topics created by the application. Binding `publishOrder-out-0` requests 16 partitions, while `publishAudit-out-0` requests 4 partitions.

This illustrates choosing settings according to each stream's needs. An already-existing topic may not have its partition count altered merely by changing application configuration; check topic state and Pulsar administrative procedures before expecting the provisioner to modify existing resources.

The Pulsar binder provisioner can create basic topics if they do not exist. Partitioned topics require configuring partition count and appropriate admin permissions. The administration service URL must also be configured when not using the default endpoint.

## 21. Common Configuration Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Changed `spring.pulsar.producer.send-timeout` but binding did not change | Binder-level or extended binding-level override exists | Check all three Pulsar scopes in order |
| Command-line flag does not change binding value | CLI changed the Boot-level key, while binding-level is a separate key with higher binder precedence | Override the exact binding key or remove the binding override if unneeded |
| All functions use the same subscription/timeout | Property set only at Spring Boot or application-wide binder scope | Set extended binding properties per binding |
| One binding does not inherit default retries | A specific common binding property overrides it | Check `spring.cloud.stream.default` and `bindings.<name>` |
| Native schema does not work | Only native encoding enabled without schema/message type, or consumer mismatch | Configure both producer and consumer on extended bindings |
| Property has no effect | Wrong prefix or wrong binding name | Verify property metadata and binding name |
| Wrong Pulsar cluster | Confused binder type with named binder instance | Check `spring.cloud.stream.binders.<name>` and `binding.binder` |
| Runtime value differs from YAML | Environment, system property, or command line overrode the same key | Use secured `env`/`configprops` to inspect sources |
| Topic lacks expected partition count | Topic already existed or property placed at wrong level | Check provisioner and per-binding partition count |

## 22. Pre-Deployment Checklist

- Distinguished Spring Boot properties, Pulsar binder properties, common binding properties, and Pulsar extended binding properties.
- Identified the exact binding name for every `Supplier`/`Function`/`Consumer`.
- Placed shared values in default/binder scope and overridden only when a binding has specific requirements.
- Applied Pulsar precedence correctly: extended binding → binder → Spring Boot.
- Checked Spring Boot `PropertySource` precedence separately for the same key.
- Did not assume a command-line argument automatically overrides a key in another scope.
- Selected the right binder via `default-binder` or `bindings.<name>.binder`.
- Distinguished Pulsar binder type from binder configuration instances.
- Configured native encoding/decoding alongside compatible schema/message types.
- Verified topic provisioning, partition counts, and administration service URL.
- Verified environment/profile/secret injection from the deployment platform.
- Verified effective values via secured configuration inspection.
- Added integration tests for critical bindings using the real Pulsar binder.

## Summary

To determine which Pulsar configuration takes effect, first identify **the property's scope**. For the same Pulsar option, extended binding properties have the highest precedence, followed by binder properties, and then Spring Boot Pulsar properties. Common Spring Cloud Stream properties follow their own default and per-binding mechanism. Next, evaluate Spring Boot `PropertySource` precedence to see whether a file, environment variable, system property, or command-line argument supplies the value for each individual key.

Do not merge these two mechanisms into a single order. A command-line flag overrides only the same key in `Environment`; it does not automatically discard an extended binding key in a higher scope. Place shared configuration at the right level, add per-binding overrides only when needed, and verify effective results with integration tests to prevent functions in the same application from accidentally sharing unsuitable timeouts, schemas, or subscriptions.

## References

- [Spring Cloud Stream 5.1 — Pulsar Binder: Using Pulsar Properties in the Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream 5.1 — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream 5.1 — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
- [Spring Boot 4.2 — Externalized Configuration and PropertySource Ordering](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot 4.2 — Application Properties for Pulsar](https://docs.spring.io/spring-boot/4.2/appendix/application-properties/)
- [Spring for Apache Pulsar — Reference Documentation](https://docs.spring.io/spring-pulsar/reference/)
