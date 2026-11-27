# Registering a Binder via META-INF/spring.binders

Spring Cloud Stream enables Java applications to process events through the `Supplier`, `Function`, and `Consumer` model. The business logic layer usually does not need to know whether messages arrive from Kafka, RabbitMQ, or Pulsar: a **binder** attaches input/output bindings to the corresponding middleware. Beyond built-in binders, the framework provides the Binder SPI so a library can supply its own custom binder.

For Spring Cloud Stream to **discover a binder type** on the classpath, the binder library must package a `META-INF/spring.binders` resource. This file uses Java properties format, mapping a binder type name to one or more Spring configuration classes. Those configuration classes instantiate a bean implementing `org.springframework.cloud.stream.binder.Binder` along with required connection objects. When an application selects a binder for a binding, the framework uses that registration metadata to create and apply the corresponding binder.

This topic belongs to the **Scaling** chapter: registering a binder is how Spring Cloud Stream extends to new middleware or packages reusable adapters. It **does not automatically increase throughput**, create consumer groups, guarantee retry/DLQ, or replace destination/partition configuration. Those capabilities must be supplied by the binder implementation and broker; scaling replicas also depends on the actual consumer group/subscription model.

> Reference version: official Spring Cloud Stream 5.1.0 documentation. Examples use Java and illustrative class names in package `com.example.stream.binder.audit`. For Spring Cloud Stream 4.x/5.x, use a BOM compatible with your current Spring Boot/Cloud version; do not copy classes/APIs from another release without checking.

## Learning Objectives

After this lesson, you will be able to:

- Explain the relationships among `Binder`, binder type, binder configuration, binding name, and destination.
- Place `src/main/resources/META-INF/spring.binders` properly inside a binder module.
- Write a Java properties entry mapping a binder type name to a `@Configuration` class.
- Distinguish discovery via `spring.binders` from Spring Boot auto-configuration and component scanning.
- Build a custom binder skeleton using `ProvisioningProvider`, `MessageProducer`, and `MessageHandler`.
- Configure an application to choose a binder by type or configuration name.
- Run multiple binders simultaneously as well as multiple connections of the same binder type.
- Inspect JARs, classpaths, metadata, and startup order when a binder is not discovered.
- Understand duplicate binder key errors, bean conflicts, and incompatible versions.
- Design testing and operations when packaging a binder for multiple instances/clusters.

## 1. Why Does a Binder Need Registration?

Suppose you build an application:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), "ACCEPTED");
}
~~~

The function expresses business logic only. At startup, Spring Cloud Stream must:

1. Know the function's input binding is `acceptOrder-in-0` and output is `acceptOrder-out-0`.
2. Determine which binder each binding uses.
3. Establish producer/consumer connections and, when configured, provision broker destinations.
4. Route data from the broker into the function and send results back to the broker.
5. Manage start/stop lifecycles, error handling, and resources.

The binder is the adapter doing that wiring. When Kafka or RabbitMQ binder dependencies are present, the framework detects the built-in binders. To support internal middleware, a specialized event bus, or a custom transport, a custom binder library must introduce itself to Spring Cloud Stream. `META-INF/spring.binders` is that binder-type registration mechanism.

### 1.1. Two Different Scaling Directions

| Need | Approach |
|---|---|
| Just need Kafka, RabbitMQ, or Pulsar with an existing binder | Add the supported binder dependency and configure bindings |
| Same broker type but two separate clusters | Define multiple **binder configurations** of the same type |
| New middleware with no suitable Binder SPI implementation | Write a custom Binder and package `spring.binders` |
| Only need business transformation/routing | Write a `Function`/`Consumer`; usually **no** custom Binder needed |
| Need more concurrency, partitions, or instances | Configure broker/binder properties; do not edit `spring.binders` |

Never build a custom Binder merely to rename a topic, swap a serializer, or add a business handler. Extension points at the function or binding level already cover those tasks.

## 2. Distinguishing Five Easily Confused Concepts

| Concept | Example | Where is it declared? |
|---|---|---|
| **Binder type** | `kafka`, `rabbit`, `audit` | Key inside `META-INF/spring.binders` |
| **Binder configuration name** | `auditEast`, `kafkaPrimary` | Key under `spring.cloud.stream.binders` |
| **Binding name** | `acceptOrder-in-0` | Function signature or `bindings` configuration |
| **Destination** | `orders.created`, `audit.events` | `spring.cloud.stream.bindings.<name>.destination` |
| **Consumer group/subscription** | `order-processing` | Consumer binding configuration; semantics per broker |

One binder type can have multiple binder configurations. Each binder configuration can serve multiple bindings, and each binding can point to a different destination.

Example:

~~~text
META-INF/spring.binders
   audit --> com.example...AuditBinderConfiguration
                 |
                 v
spring.cloud.stream.binders
   auditEast (type=audit)
   auditWest (type=audit)
                 |
                 v
spring.cloud.stream.bindings
   acceptOrder-out-0 (binder=auditEast, destination=orders.audit)
   retryOrder-out-0  (binder=auditWest, destination=orders.retry)
~~~

`audit` is the **binder type** registered in the JAR. `auditEast` and `auditWest` are configuration instance names in the application. `orders.audit` is not a binder name—it is a destination. Keeping these distinct is key to reading multi-binder configurations.

## 3. What Does META-INF/spring.binders Contain?

`spring.binders` is a **Java properties resource**, not YAML or a Java class. It must live at the exact path:

~~~text
custom-audit-binder/
  pom.xml
  src/
    main/
      java/
        com/example/stream/binder/audit/
          AuditBinderConfiguration.java
          AuditBinder.java
          AuditProvisioningProvider.java
          ...
      resources/
        META-INF/
          spring.binders
~~~

Minimal contents of `src/main/resources/META-INF/spring.binders`:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration
~~~

In properties syntax, `=` separates key and value. Key `audit` is the binder type name you register; the value is the **fully qualified class name** of the Spring configuration creating the `Binder` bean.

Spring Cloud Stream documentation also uses line-continuation syntax:

~~~properties
audit:\
com.example.stream.binder.audit.AuditBinderConfiguration
~~~

The colon is a properties separator, and the trailing backslash means **continue the value on the next line**. Thus both forms are equivalent; never include a literal backslash in the class name.

### 3.1. Registering Multiple Binder Types

If a single library legitimately provides two distinct `Binder` implementations:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration
archive=com.example.stream.binder.archive.ArchiveBinderConfiguration
~~~

Each key represents a separate type. Never reuse the same key `audit` for two incompatible implementations.

### 3.2. Multiple Configuration Classes for One Type

The value can be a comma-separated list of configuration class names:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration,com.example.stream.binder.audit.AuditMetricsConfiguration
~~~

Add extra classes only when you understand their bean lifecycles and dependencies. Whether using one or multiple classes, the configuration set for a binder type must produce **one clear, concrete `Binder` bean**, not multiple competing `Binder` beans. If `AuditMetricsConfiguration` also defines a second `Binder` bean, initialization can become ambiguous or fail.

### 3.3. What spring.binders Does Not Do

This file does not:

- Declare topics, queues, or subscriptions.
- Choose broker URLs or credentials.
- Create consumer groups across the entire application.
- Start every function in `FunctionCatalog`.
- Register Spring beans via regular component scanning.
- Define schemas, retries, DLQs, or transactions.
- Guarantee a `Binder` works properly merely because its class was found.

The file solely tells the framework **how to load the configuration of a binder type**. Connectivity and message processing are the responsibility of the beans created by that configuration.

## 4. How Spring Cloud Stream Finds Binders on the Classpath

At startup:

~~~mermaid
flowchart TD
    A[Application with binder dependencies] --> B[ClassLoader locates META-INF/spring.binders]
    B --> C[Reads binder type keys and configurations]
    C --> D[Binder type registry]
    D --> E{Which binder does the app choose?}
    E -->|Single matching type| F[BinderFactory gets or creates Binder]
    E -->|Multiple types| G[Via defaultBinder or binding.binder]
    G --> F
    F --> H[Initialize Binder in appropriate context]
    H --> I[Bind input/output to destinations]
~~~

This is a conceptual diagram of discovery and binder creation. Internal class names like `BinderTypeRegistry` or `DefaultBinderFactory` help when reading stack traces, though ordinary applications do not instantiate them directly. Internal APIs may vary across versions.

### 4.1. Only One Binder Type Present

If only one `Binder` implementation exists on the classpath and there are no conflicting binder-selection settings, Spring Cloud Stream normally picks that binder as the default.

For example, an app with only the Kafka binder dependency may omit explicit `binder: kafka` on its bindings.

### 4.2. Multiple Binder Types Present

If both the Kafka binder and RabbitMQ binder are on the classpath, the application must specify a binder per binding or configure an appropriate `defaultBinder`. Never rely on classpath ordering to pick your intended middleware.

~~~yaml
spring:
  cloud:
    stream:
      defaultBinder: kafka
      bindings:
        acceptOrder-in-0:
          binder: kafka
          destination: orders.created
          group: order-processors
        acceptOrder-out-0:
          binder: rabbit
          destination: orders.accepted
~~~

`defaultBinder` is convenient when most bindings share one middleware, though cross-broker bridges should declare `binder` explicitly on critical bindings for readability.

### 4.3. Isolated Contexts for Binder Configurations

When `spring.cloud.stream.binders.<name>` is configured, Spring Cloud Stream can create an isolated context/environment for that binder. Properties `type`, `environment`, `inheritEnvironment`, and `defaultCandidate` control selection and initialization.

Do not assume beans from a binder configuration always live in the main application context or that every application property is inherited when `environment` is isolated. Verify dependency injection, profiles, and broker configs inside the binder context.

## 5. Relationship to the Binder SPI

The central interface is:

~~~java
public interface Binder<T, C extends ConsumerProperties, P extends ProducerProperties> {
    Binding<T> bindConsumer(
            String destinationName,
            String group,
            T inboundBindTarget,
            C consumerProperties);

    Binding<T> bindProducer(
            String destinationName,
            T outboundBindTarget,
            P producerProperties);
}
~~~

This is the condensed signature illustrating the Binder SPI contract. The binder is responsible for:

- Connecting the inbound target to the broker or transport (`bindConsumer`).
- Connecting the outbound target to the broker (`bindProducer`).
- Applying consumer groups and producer/consumer properties.
- Creating/reading destinations when permitted.
- Managing lifecycles and releasing resources via `Binding`.

Implementations normally extend `AbstractMessageChannelBinder` instead of writing everything from scratch. The binder integrates with Spring Messaging/Integration via:

| Component | Responsibility |
|---|---|
| `ProvisioningProvider` | Resolves/provisions logical destinations to transport resources |
| `ProducerDestination` | Describes the producer target; may support partitions |
| `ConsumerDestination` | Describes the consumer target |
| `MessageHandler` | Sends records to middleware on the producer side |
| `MessageProducer` | Receives records from middleware and emits to a message channel |
| `AbstractMessageChannelBinder` | Base Binder implementation for message channels |
| `@Configuration` | Instantiates the `Binder` bean and its dependencies |
| `spring.binders` | Registers the type name and configuration class on the classpath |

### 5.1. Separation of Responsibilities

~~~text
Spring Cloud Function
  Supplier / Function / Consumer
                |
                v
Spring Cloud Stream binding
                |
                v
Binder SPI implementation
  +-----------------------------+
  | ProvisioningProvider        |
  | MessageProducer / Handler   |
  | retry/ack/partition support |
  +-----------------------------+
                |
                v
Concrete middleware (Kafka, RabbitMQ, Pulsar, custom)
~~~

Not every Binder supports the exact same feature set. Kafka consumer groups and offset commits differ from RabbitMQ queues/acks and Pulsar subscriptions. A custom Binder must clearly document the semantics it implements and never use the word "Binder" as a blanket guarantee of exactly-once delivery across middleware.

## 6. Example Building a Custom Binder Skeleton

The following example assumes an internal middleware named **Acme Audit Transport**. The goal is showing clearly how Java classes, Spring `@Configuration`, and `spring.binders` fit together. The transport layer is left as an extension point because a real binder must integrate its own client, callbacks, acknowledgments, and lifecycle.

### 6.1. Binder Module Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream</artifactId>
    </dependency>
</dependencies>
~~~

Manage versions via a Spring Cloud release train BOM compatible with the application. Never mix arbitrary Spring Boot, Spring Cloud Stream, and Spring Integration versions simply because Maven resolves them.

### 6.2. ProvisioningProvider

First describe how logical destination names map to transport targets:

~~~java
package com.example.stream.binder.audit;

import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class AuditProvisioningProvider
        implements ProvisioningProvider<ConsumerProperties, ProducerProperties> {

    @Override
    public ProducerDestination provisionProducerDestination(
            String name, ProducerProperties properties) {
        return new AuditDestination(validate(name));
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name, String group, ConsumerProperties properties) {
        return new AuditDestination(validate(name));
    }

    private String validate(String name) {
        if (name == null || !name.matches("[a-zA-Z0-9._-]{1,80}")) {
            throw new IllegalArgumentException("Invalid audit destination");
        }
        return name;
    }
}

final class AuditDestination
        implements ProducerDestination, ConsumerDestination {

    private final String name;

    AuditDestination(String name) {
        this.name = name;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public String getNameForPartition(int partition) {
        return name + "-" + partition;
    }
}
~~~

This example shows how a binder can validate logical destinations. In production, the provisioner must also resolve topics/queues, verify permissions, block destinations outside an allowlist, and map groups/partitions to actual transport primitives. `getNameForPartition` here merely illustrates naming; it does not make the transport support partitions.

### 6.3. Binder Implementation Skeleton

A `MessageChannel` binder can extend `AbstractMessageChannelBinder` and implement two factory methods:

~~~java
package com.example.stream.binder.audit;

import org.springframework.cloud.stream.binder.AbstractMessageChannelBinder;
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.integration.core.MessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

public final class AuditBinder extends AbstractMessageChannelBinder<
        ConsumerProperties, ProducerProperties, AuditProvisioningProvider> {

    public AuditBinder(AuditProvisioningProvider provisioner) {
        super(null, provisioner);
    }

    @Override
    protected MessageHandler createProducerMessageHandler(
            ProducerDestination destination,
            ProducerProperties properties,
            MessageChannel errorChannel) {

        // MUST replace with Acme Audit Transport producer:
        // serialize message, send to destination, and handle confirm/error.
        return message -> {
            throw new UnsupportedOperationException(
                    "Implement Audit Transport producer before running");
        };
    }

    @Override
    protected MessageProducer createConsumerEndpoint(
            ConsumerDestination destination,
            String group,
            ConsumerProperties properties) {

        // MUST replace with MessageProducer connecting to Acme Audit Transport:
        // subscribe by group, receive messages, handle ack and lifecycle.
        throw new UnsupportedOperationException(
                "Implement Audit Transport consumer before running");
    }
}
~~~

**Important:** this is a skeleton **with no transport**. The code illustrates the SPI contract and serves as a module starting point, yet **cannot send or receive messages** and must not be deployed to production until placeholders are replaced with real producer/consumer implementations.

To build an operational binder, implement at minimum:

1. Producer client and publish/failure confirmation.
2. Consumer receiver and bridge into Spring Messaging channels.
3. Subscribe/ack/redelivery or checkpointing with clear semantics.
4. Start, stop, cleanup, reconnection, and shutdown.
5. Provisioning with ACLs, partitions, groups, retries, and resource cleanup.
6. Error handling, metrics/tracing, schemas, and integration tests.

### 6.4. Configuration Creating the Binder Bean

~~~java
package com.example.stream.binder.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditBinderConfiguration {

    @Bean
    AuditProvisioningProvider auditProvisioningProvider() {
        return new AuditProvisioningProvider();
    }

    @Bean
    AuditBinder auditBinder(AuditProvisioningProvider provisioner) {
        return new AuditBinder(provisioner);
    }
}
~~~

The configuration class is the entrypoint referenced by `spring.binders`. The framework must be able to load the class and instantiate its beans. If the middleware client needs settings or credentials, this configuration must also register the appropriate client beans or connection factories.

For a given binder type, produce **exactly one `Binder` bean** from that configuration set. If multiple `Binder` beans compete inside the same binder context, implementation selection becomes ambiguous. Also avoid directly importing custom binder configurations via component scan into the main application when the framework builds binder-specific contexts unless you understand the bean lifecycle; it can cause double initialization.

### 6.5. Registering in META-INF/spring.binders

Place the resource at:

~~~text
src/main/resources/META-INF/spring.binders
~~~

Contents:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration
~~~

This registers **binder type `audit`**. The name `audit` must match the `type` or `defaultBinder` property when applications use it. `AuditBinderConfiguration` must be packaged in the same JAR or a dependency loadable at runtime.

## 7. Distinguishing spring.binders, spring.factories, and AutoConfiguration.imports

Spring Boot and Spring projects use several distinct discovery mechanisms:

| Resource | Typical role | Replaces `spring.binders`? |
|---|---|---|
| `META-INF/spring.binders` | Declares binder type names and configuration classes for Spring Cloud Stream | This IS the Binder SPI registration mechanism |
| `META-INF/spring.factories` | `SpringFactoriesLoader`/extension metadata mechanism, historically used for auto-configurations | **No** |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Registers Spring Boot auto-configurations in modern Boot releases | **No** |
| `META-INF/services/...` | Java `ServiceLoader` for a specific interface | **Not by default** |
| `application.yml` | Declares bindings, broker properties, binder config names | **No** |

A Binder JAR may simultaneously contain `spring.binders` and other auto-configuration metadata. However, an `@AutoConfiguration` loaded by Spring Boot does not mean the key `audit` is registered in Spring Cloud Stream's Binder SPI. Likewise, a valid `spring.binders` file may only create an isolated Binder context rather than automatically placing all its beans into the main application context.

### 7.1. Do Not Rely on @ComponentScan Instead of Type Registration

A `@Configuration` class can be component-scanned by the application, yet the binder type registry will not gain key `audit` from that. Use the standard resource. If your goal is merely a custom client used directly inside a business service, you do not necessarily need to implement the Binder SPI.

### 7.2. Do Not Treat spring.binders as Broker Configuration

Never write:

~~~properties
# WRONG ROLE:
orders.created=kafka:9092
audit.events=my-queue
~~~

Keys in `spring.binders` are **Binder types**, and values are **configuration class names**. Destinations and broker endpoints belong in application configuration or binder implementation properties.

## 8. Using a Custom Binder in a Spring Cloud Stream Application

The application needs a runtime dependency on the binder JAR:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example.stream</groupId>
        <artifactId>acme-audit-binder</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

These coordinates are only an example for an internally published artifact, **not an artifact published on Maven Central**. The application also needs Spring Cloud Stream dependencies and a matching BOM.

When only binder type `audit` is on the classpath and every binding uses it:

~~~yaml
spring:
  cloud:
    function:
      definition: auditEvent
    stream:
      defaultBinder: audit
      bindings:
        auditEvent-in-0:
          destination: audit.input
          group: audit-workers
        auditEvent-out-0:
          destination: audit.output
~~~

Illustrative function:

~~~java
@Bean
Function<AuditEvent, AuditEvent> auditEvent() {
    return event -> event;
}
~~~

Note: the `AuditBinder` skeleton in section 6 intentionally omits transport wiring. The configuration above runs successfully only after the Binder implements real producer/consumer endpoints and connection properties.

### 8.1. Binder Type vs. Binder Configuration Name

When using multiple connections of the same type:

~~~yaml
spring:
  cloud:
    function:
      definition: auditEvent
    stream:
      bindings:
        auditEvent-in-0:
          binder: auditEast
          destination: audit.input
          group: audit-workers
        auditEvent-out-0:
          binder: auditWest
          destination: audit.output
      binders:
        auditEast:
          type: audit
          environment:
            audit:
              transport:
                endpoint: https://audit-east.internal
        auditWest:
          type: audit
          environment:
            audit:
              transport:
                endpoint: https://audit-west.internal
~~~

Here:

- `audit` is the type advertised by the JAR's `spring.binders`.
- `auditEast` and `auditWest` are configuration names defined by the application.
- `auditEvent-in-0.binder` must reference **configuration name** `auditEast`, not the destination name.
- The two `audit.transport.endpoint` properties only take effect if the custom Binder actually declares and reads that property.

**Warning:** when explicit binder configurations are enabled, default binder auto-configuration is bypassed; declare every binder used by the application explicitly. Never declare only `auditEast` and expect another Kafka/Rabbit binder to keep appearing automatically once configuration switches to explicit mode.

### 8.2. Four Key Properties

| Property | Meaning | Values / notes |
|---|---|---|
| `spring.cloud.stream.binders.<name>.type` | Binder type | Key from `spring.binders`; defaults to the config name |
| `spring.cloud.stream.binders.<name>.environment` | Binder environment properties | Configures endpoints, credentials, profiles, etc. |
| `spring.cloud.stream.binders.<name>.inheritEnvironment` | Whether to inherit the application environment | Defaults to `true` |
| `spring.cloud.stream.binders.<name>.defaultCandidate` | Whether eligible as default binder | Defaults to `true` |

If a framework/plugin adds a binder for a special purpose without wanting to influence default binder selection:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        auditIsolated:
          type: audit
          defaultCandidate: false
~~~

This binder is used only when explicitly referenced. With multiple binders, set `binder` explicitly on each input/output binding to avoid ambiguity.

## 9. Example: Kafka and Rabbit Binders on the Same Classpath

More common than a custom binder is combining pre-built binders:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-binder-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-binder-rabbit</artifactId>
    </dependency>
</dependencies>
~~~

Let the BOM manage versions; never pin mismatched versions across lines. Each binder artifact carries its own `spring.binders` inside its JAR.

~~~yaml
spring:
  cloud:
    function:
      definition: orderBridge
    stream:
      bindings:
        orderBridge-in-0:
          binder: kafka
          destination: orders.created
          group: order-bridge
        orderBridge-out-0:
          binder: rabbit
          destination: orders.forwarded
~~~

`spring.binders` lets the framework discover **both binder types**. `bindings.*.binder` picks the type or specific configuration for each binding. This does not give the two brokers a shared transaction: bridging Kafka to RabbitMQ still requires designing source acks, target publishes, idempotency, or outbox/inbox patterns to handle failures and duplicates.

### 9.1. When Should You Not Add spring.binders to an Application?

When using built-in Kafka/Rabbit/Pulsar binders, a normal application **does not need to create** `src/main/resources/META-INF/spring.binders`. The proper resource already lives inside the binder dependency.

Creating that file in the application with key `kafka` merely to re-point to the built-in class can cause duplicate definitions or alter resolution. Only author a new file when publishing your own **binder implementation** or following a carefully designed and tested extension requirement.

## 10. Packaging the JAR so the Resource Is Discoverable

When building a standard Maven/Gradle module, `src/main/resources` is copied to the classpath output and JAR.

The binder JAR must contain at minimum:

~~~text
META-INF/spring.binders
com/example/stream/binder/audit/AuditBinderConfiguration.class
com/example/stream/binder/audit/AuditBinder.class
com/example/stream/binder/audit/AuditProvisioningProvider.class
...
~~~

Verify using the JDK `jar` tool:

~~~bash
jar tf target/acme-audit-binder-1.0.0.jar
~~~

Check for `META-INF/spring.binders` in the listing. In PowerShell:

~~~powershell
jar tf target/acme-audit-binder-1.0.0.jar |
  Select-String 'META-INF/spring.binders|AuditBinderConfiguration.class'
~~~

For Spring Boot executable JARs using nested dependencies, the binder JAR typically lives under `BOOT-INF/lib/`. Not seeing `META-INF/spring.binders` at the **root** of the application fat JAR does not mean the file is missing; inspect the nested JAR or query the resource via the runtime classloader.

### 10.1. Maven Shade and Resource Merging

If building an uber-JAR with Maven Shade or a similar tool, multiple dependencies may contain `META-INF/spring.binders`. Never let shading accidentally **overwrite one file with another**. Configure an appropriate resource transformer/merge strategy and verify the resulting file contains all keys without duplicates.

For regular Spring Boot applications, keep binders as standard dependency JARs and let Boot repackaging handle the classpath rather than manually merging resources. Depending on your build plugin version, resource merging may need different settings; inspecting the built artifact is mandatory.

### 10.2. Key Collisions Across JARs

If two JARs both contain:

~~~properties
audit=com.vendor.a.AuditBinderConfiguration
~~~

and:

~~~properties
audit=com.vendor.b.AnotherAuditBinderConfiguration
~~~

then type `audit` collides. Discovery may fail or depend on how the registry handles duplicates. Never design around classpath order to "win" a key. Choose a sufficiently distinct key, exclude redundant dependencies, or rename the binder type before packaging.

### 10.3. Resource Must Be on the Runtime Classpath

Common mistakes:

- Placing the file in `src/test/resources`, so it exists only during test execution.
- Giving the binder dependency `test` or `provided` scope, omitting it from the runtime image.
- Resource excluded by a build plugin.
- Misspelled or wrongly cased filename, e.g., `spring.binder` instead of `spring.binders`.
- Placing `spring.binders` at the root without `META-INF/`.
- JAR contains metadata yet lacks `AuditBinderConfiguration` due to shading/exclusions.

Linux filesystems are case-sensitive; the resource path must match exact casing.

## 11. Inspecting Resources via ClassLoader

If you suspect a JAR was packaged incorrectly, you can list every `META-INF/spring.binders` resource visible to the runtime classloader:

~~~java
import java.net.URL;
import java.util.Collections;
import java.util.Enumeration;

public final class BinderResourceInspector {

    public static void printResources() throws Exception {
        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        Enumeration<URL> urls =
                loader.getResources("META-INF/spring.binders");

        for (URL url : Collections.list(urls)) {
            System.out.println("Found binder metadata: " + url);
        }
    }
}
~~~

This method **only diagnoses resources**; it does not register a new Binder. Do not turn this output into default production logging if URLs expose sensitive filesystem paths; keep it for local/test or controlled debugging.

### 11.1. Test Verifying a Specific Entry

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.net.URL;
import java.util.Collections;
import java.util.Properties;

import org.junit.jupiter.api.Test;

class BinderMetadataTest {

    @Test
    void auditBinderTypeIsVisible() throws Exception {
        var loader = getClass().getClassLoader();
        var urls = Collections.list(
                loader.getResources("META-INF/spring.binders"));

        boolean found = false;
        for (URL url : urls) {
            Properties properties = new Properties();
            try (InputStream input = url.openStream()) {
                properties.load(input);
            }
            if ("com.example.stream.binder.audit.AuditBinderConfiguration"
                    .equals(properties.getProperty("audit"))) {
                found = true;
                break;
            }
        }

        assertTrue(found, "audit binder metadata must be on classpath");
    }
}
~~~

This test only proves the resource and property key exist. It **does not prove** the `Binder` bean instantiates cleanly or the transport works. Add context startup tests and integration tests.

## 12. Binder Initialization Tests and Integration Tests

A thorough test suite spans multiple levels:

| Level | Focus | What can be concluded |
|---|---|---|
| Metadata test | `META-INF/spring.binders` exists with valid key/value | Binder type can be discovered |
| ApplicationContext test | Configuration class loads and creates exactly one `Binder` bean | Basic Spring wiring is valid |
| `BinderFactory` test | Requesting binder by name/type returns the intended implementation | Registry and selection work |
| Producer test | Output binding sends messages to transport | Producer path works |
| Consumer test | Input binding receives messages via group/subscription | Consumer path works |
| Failure test | Broker disconnect, nack, redelivery, retry, shutdown | Reliability semantics verified |
| Multi-binder test | Kafka/Rabbit/custom binder on the same classpath | No collisions and right binder picked |
| Packaged-app test | Run executable JAR / container image | Resources remain intact in final artifact |

### 12.1. Testing BinderFactory

Inside a Spring Cloud Stream application context:

~~~java
@Autowired
BinderFactory binderFactory;

@Test
void customBinderCanBeResolved() {
    Binder<?, ?, ?> binder =
            binderFactory.getBinder("audit", MessageChannel.class);

    assertNotNull(binder);
}
~~~

This snippet illustrates resolving a Binder by configuration/type name when a single `audit` binder type exists. For `auditEast` or `auditWest`, pass the corresponding **binder configuration** name. Verify the generic method/API against your project's Spring Cloud Stream version; real tests must start the context with a completed Binder, since the skeleton intentionally throws on binding startup.

### 12.2. Testing Both Producer and Consumer

To avoid false-green tests, verify with the custom transport:

1. Producer sends events with valid `eventId` and schema to the right destination.
2. Consumer uses group/subscription and processes messages per declared semantics, or handles duplicates safely.
3. Consumer stop/start does not drop unacknowledged messages.
4. Retry and DLQ work if the Binder claims to support them.
5. Partition keys/ordering work if the Binder supports partitioning.
6. Authentication, ACLs, and TLS reject invalid credentials properly.
7. Running multiple replicas simultaneously causes no races or unintended duplicate side effects.

Spring Cloud Stream Test Binder helps test function/binding logic, but **does not replace** integration tests for a new Binder implementation because it uses no real transport.

## 13. Troubleshooting: Binder Not Recognized

When application startup fails, check in this order.

### 13.1. Binder Type Not Found

Symptom: logs mention no binder found, unknown binder type, or `BinderFactory` cannot instantiate the requested name.

Check:

1. Is the binder dependency actually on the **runtimeClasspath**?
2. Does the JAR contain `META-INF/spring.binders` with exact casing?
3. Is the key inside the file literally `audit`?
4. Does `spring.cloud.stream.binders.<name>.type` point to that key?
5. Was the resource dropped during shading or shadowed by a duplicate key?

Do not "fix" this by letting all bindings fall back to another binder without understanding routing; that can send messages to the wrong middleware.

### 13.2. Configuration Class Fails to Load

Symptom: `ClassNotFoundException` or `NoClassDefFoundError` when the framework loads configuration.

Causes:

- Typo in package/class name inside `spring.binders`.
- JAR contains the properties file but is missing compiled classes.
- A required configuration/transport client dependency was excluded.
- Binder compiled against a different Spring Cloud Stream API version than runtime.

Resolution: compare the class name with the declared package, inspect the JAR, dependency tree, and release train. Never mask this with catch-all handlers that leave the Binder half-initialized.

### 13.3. Multiple Binder Beans Found

Symptom: ambiguous wiring or failure to pick a `Binder` implementation.

Cause: configuration imports another Binder, or shared configurations instantiate multiple `Binder` beans inside the binder-specific context. Separate configurations and emit only one `Binder` bean per binder type. Check whether `@ConditionalOnMissingBean` and `@ComponentScan` inadvertently widened scope too far.

### 13.4. Wrong Default Binder Selected

Symptom: binding sends to RabbitMQ instead of Kafka, or startup reports multiple binder candidates.

Resolution:

- Set `spring.cloud.stream.defaultBinder` if there is genuinely one clear default.
- Prefer explicit `bindings.<bindingName>.binder` on critical inputs/outputs.
- With explicit binder configurations, reference the configuration name (e.g., `kafkaEast`), not just the type key.
- Set `defaultCandidate: false` on binders that must not participate in default selection.

### 13.5. Binder Discovered, Broker Connection Fails

This is a **post-discovery** error, not a `spring.binders` problem. Check broker URL, DNS, TLS, credentials, topic/queue existence, ACLs, timeouts, and network reachability. A custom binder must report meaningful health/reconnection failures instead of starting "successfully" and dropping messages.

### 13.6. Runs in IDE, Fails in Fat JAR

Usually a classpath or packaging discrepancy. Check dependency scopes and resource merging; run integration tests against the actual executable JAR or container image. Never verify solely with IDE run configurations.

## 14. Common Mistakes Table

| Mistake | Consequence | Fix |
|---|---|---|
| Putting file at `resources/spring.binders` | Never discovered | Move to `META-INF/spring.binders` |
| Using YAML in `spring.binders` | Key/value misparsed | Use Java properties format |
| Value points to `Binder` class instead of configuration | No `Binder` bean created | Point to `@Configuration` |
| Using topic name as the key | Inconsistent binder type | Key must be a type such as `audit` |
| JAR omits the resource file | Runtime cannot see the binder | Check packaging/artifact |
| Type key collides with another library | Collision / ambiguity | Pick a unique type name |
| Two `Binder` beans for the same type | Bean resolution fails | Instantiate only one `Binder` bean |
| Missing client/runtime dependency | Class loading or connection error | Manage dependencies with BOM |
| Omitting `binding.binder` with multiple types | Wrong selection or ambiguity | Specify explicitly per binding |
| Confusing type and configuration name | Binder lookup fails | Check `binders.<name>.type` |
| Using skeleton custom binder with no transport | Startup/binding/send errors | Implement producer/consumer |
| Testing metadata only | Transport bugs go undetected | Add integration/failure tests |
| Merging JARs drops `spring.binders` | Binder vanishes in production image | Inspect merge config and final JAR |
| Assuming registered binder auto-scales | Multiple instances duplicate or lose messages | Design group, ack, partition, idempotency |

## 15. Connection to Scaling and Deployment

`spring.binders` is read from **each application instance's** classpath, not from a registry stored on Kafka/RabbitMQ/Pulsar brokers. When scaling from 2 to 5 Pods, all 5 images must carry the exact same binder artifact and compatible metadata.

~~~text
Image v1 + acme-audit-binder-1.0.jar
    |        |        |
  Pod A    Pod B    Pod C
    \        |        /
         Acme Audit Transport
~~~

If Pod A runs binder 1.0 while Pod B runs binder 2.0, they may interpret schemas, destinations, or acks differently. Rolling updates must verify coexistence between two versions, not just the presence of `spring.binders`.

### 15.1. Registration Does Not Replace Consumer Groups

| Platform | Scaling requirements still needed |
|---|---|
| Kafka binder | Consumer groups, partition assignment, offset commits, rebalances |
| RabbitMQ binder | Queue semantics, prefetch, consumer acks, redelivery |
| Pulsar binder | Subscription types, backlogs, ack/redelivery, partition/key ordering |
| Custom binder | Defining group/sharing, checkpointing, retries, partitioning, shutdown |

A successfully registered Binder where every replica subscribes in broadcast mode can cause every event to be processed multiple times. Conversely, a Binder acquiring a global lock can leave all other replicas idle. Real scalability depends on the middleware and how the Binder uses it.

### 15.2. Security and Operational Permissions

A Binder is a Java plugin executing inside the application JVM. An untrusted binder JAR can run code with the service account's privileges. Therefore:

- Only use binders from reviewed sources and pinned versions.
- Scan dependencies and lock artifact versions.
- Never allow end users to load arbitrary JARs at runtime.
- Grant broker ACLs following the principle of least privilege.
- Never grant blanket permissions to create all topics/queues just for "easy provisioning."
- Keep secrets out of source code, logs, and `spring.binders`.
- Monitor binder connections, destinations, retries, DLQs, and client errors.

### 15.3. Operational Signals to Monitor

- Binder startup/initialization errors.
- Consumer/producer bind latency.
- Consumer lag or queue depth per broker.
- Publish success/failure and acknowledgment rates.
- Reconnect, rebalance, retry, and dead-letter counts.
- Graceful shutdown duration and in-flight messages.
- Binder version drift across Pods.

To fix a "binder not found" error, do not increase replicas or concurrency: it is an artifact/registry issue. To fix lag or backlog, investigate throughput, broker behavior, and consumer semantics—not `spring.binders`.

## 16. Checklist for Registering a New Binder

Before release:

1. Pick a unique, meaningful, stable binder type key.
2. Implement the Binder SPI or extend `AbstractMessageChannelBinder`.
3. Provide `ProvisioningProvider` and producer/consumer endpoints.
4. Define transaction, acknowledgment, ordering, partitioning, and retry semantics.
5. Create a `@Configuration` producing exactly one `Binder` bean.
6. Place the file at `src/main/resources/META-INF/spring.binders`.
7. Map the key to the configuration's FQCN, not the `Binder` class.
8. Verify valid Java properties parsing with no key collisions.
9. Align versions with the Spring Cloud Stream/BOM in use.
10. Package the Binder JAR and verify resources/classes inside the artifact.
11. Add the JAR dependency to the consumer application's runtime classpath.
12. Declare `spring.cloud.stream.binders.<name>.type` when using explicit configurations.
13. Set `bindings.<bindingName>.binder` on every critical binding.
14. Run metadata, context, `BinderFactory`, and transport integration tests.
15. Run packaged-application, multi-binder, failover, and multi-replica tests.
16. Deploy with pinned artifact versions and monitor health and backlog.

## Conclusion

`META-INF/spring.binders` is the binder-type registration point in Spring Cloud Stream: each key declares a binder type, and the value lists Spring configuration classes responsible for creating the `Binder` bean and connectivity infrastructure. The file must sit on the binder library's runtime classpath, be packaged intact inside the JAR, and follow Java properties format.

Do not confuse keys in `spring.binders` with binder configuration names, binding names, or broker destinations. Use `spring.cloud.stream.binders.<name>.type` to point to a binder type and `spring.cloud.stream.bindings.<bindingName>.binder` to pick a configuration for a binding. When running multiple binders, configure them explicitly and verify dependencies, classpath, bean wiring, broker access, and real integration. Successful registration is only the first step of the Binder SPI; scaling, retry/DLQ, partitioning, and delivery guarantees must still be implemented and tested independently.

## References

- [Spring Cloud Stream — Binder SPI](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-api.html)
- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html)
- [Spring Cloud Stream — Binder Detection](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-detection.html)
- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
