# Assigning a Stable id for Each @JmsListener Endpoint

> **Module:** Spring Framework – JMS  
> **Knowledge Area:** `@JmsListener`  
> **Focus:** Assigning a clear, stable, and unique `id` for each **listener endpoint within each Spring application context** for lifecycle management, testing, and system observability.

## Learning Objectives

After this lesson, you will be able to:

1. Explain that `@JmsListener(id = "...")` actually sets the **identifier of the listener container** managed by Spring—not the queue name, message ID, JMS client ID, or durable subscription name.
2. Understand why you should not rely on auto-generated IDs if the application needs `JmsListenerEndpointRegistry` to look up or control the exact endpoint across deployments.
3. Establish a stable naming convention, unique within a registry's scope, clear enough on service/business/role to use in code, logs, tests, and dashboards.
4. Inspect the ID list via `getListenerContainerIds()`, retrieve containers via `getListenerContainer(id)`, and perform `start()`/`stop()` on the right **application instance**.
5. Explain why the same ID can appear on **two different replicas**, yet two endpoints cannot be registered with duplicate IDs in the same `JmsListenerEndpointRegistry`.
6. Distinguish endpoint ID from `destination`, `containerFactory`, bean name, `subscription`, `clientId`, and `JMSMessageID`.
7. Handle cases such as multiple `@JmsListener` annotations on one method, configuration placeholders, programmatic endpoint registration, and changing an ID while the system is running.
8. Write tests verifying registered IDs and design safe start/stop/diagnostics runbooks without mistaking `isRunning()` for healthy broker communication.

## 1. What Does a @JmsListener Method Create?

Consider a simple listener:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceJobListener {

    @JmsListener(destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        System.out.println("Invoice job: " + invoiceId);
    }
}
```

On the Spring side:

1. `@EnableJms` (or equivalent infrastructure configured by the application) enables annotation processing.
2. `JmsListenerAnnotationBeanPostProcessor` finds methods annotated with `@JmsListener` on Spring-managed beans.
3. Spring creates a **`JmsListenerEndpoint`** describing the method, destination, and annotation attributes.
4. The selected `JmsListenerContainerFactory` creates a **`MessageListenerContainer`** responsible for connecting, fetching messages, converting payloads, and invoking the method.
5. `JmsListenerEndpointRegistry` manages the listener containers by **endpoint ID** and handles their lifecycle.

```text
@Component InvoiceJobListener
         |
         | @JmsListener(...)
         v
JmsListenerAnnotationBeanPostProcessor
         |
         v
JmsListenerEndpoint (id + destination + method + options)
         |
         v
JmsListenerContainerFactory
         |
         v
MessageListenerContainer -----> Queue / Topic on JMS provider
         |
         +---- JmsListenerEndpointRegistry
                  |
                  +-- id -> container
                  +-- getListenerContainer(id)
                  +-- getListenerContainerIds()
```

**The ID in `@JmsListener` is tied to the container created by Spring**, not to a message's primary key on the broker. The same destination can be served by multiple listener containers (each with its own ID), but they follow Queue/Topic semantics and do not automatically become independent business groups just because their IDs differ.

The listener containers created by the registry from annotated endpoints **are not ordinary Spring beans to `@Autowired` by container name**. Use the registry to manage them; the handler `@Component` itself remains a separate bean.

### 1.1. Assigning an Explicit ID

```java
@Component
public class InvoiceJobListener {

    @JmsListener(
            id = "billing.invoice.worker.v1",
            destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        // Process invoice.
    }
}
```

Here:

- `billing.invoice.worker.v1` = **endpoint ID in the Spring registry**.
- `billing.invoice.jobs` = **destination name** resolved by the listener container into a Queue/Topic.
- `consume` = Java handler method.
- `InvoiceJobListener` = Spring bean (by default has a name derived from the class, not used as the endpoint ID).

**There is no JMS rule forcing IDs into the format above.** This is an application convention. The meaning of `id` is a **unique String within the registry**, while stability across releases is the development team's responsibility.

### 1.2. Auto-Generated ID When Omitted

The `@JmsListener.id()` Javadoc specifies: if `id` is omitted, Spring provides an **auto-generated identifier**.

In some implementation versions, the auto-generated ID looks roughly like:

```text
org.springframework.jms.JmsListenerEndpointContainer#0
org.springframework.jms.JmsListenerEndpointContainer#1
...
```

That is an **implementation detail** and should not be treated as an immutable API format or order-stable across changes. When adding new listeners, changing registration order, modifying component scanning, changing configuration, or upgrading versions, the association between an auto-generated ID and a method can change.

Use auto-IDs when you do not need to reference endpoints by a fixed name. Whenever you have operational scripts, endpoint health checks, lifecycle controls, or ID-based tests, declare `id` explicitly.

## 2. "Stable" and "Unique" Are Two Different Requirements

A good ID needs both properties:

**Stable over time:** the same logical listener keeps the same ID across restarts, redeploys, Java method renames, or class/package moves when business semantics have not changed.

**Unique within one registry:** two distinct endpoints in the same Spring application context must not register the same ID.

Suppose the Billing service has two listeners:

```java
@JmsListener(
        id = "billing.invoice.worker.v1",
        destination = "billing.invoice.jobs")
public void processInvoice(String payload) { ... }

@JmsListener(
        id = "billing.reconcile.worker.v1",
        destination = "billing.reconcile.jobs")
public void reconcile(String payload) { ... }
```

Both use the convention `<service>.<domain>.<role>.<contractVersion>`, which is only a **naming suggestion**, not syntax enforced by Spring.

Why can versioning be useful? If a new version genuinely introduces **a separate logical endpoint** with a different contract (e.g., running in parallel during a migration), `.v2` avoids collisions. If you only rename a Java class or change logging, **you do not need to change the endpoint ID**.

### 2.1. Recommended Convention

| Segment | Purpose | Example |
| --- | --- | --- |
| Service/owner | Identifies the responsible team/system | `billing` |
| Domain/feature | Identifies the business area | `invoice` |
| Role | Distinguishes worker, audit, notification... | `worker` |
| Contract version (if needed) | Coexistence of multiple endpoints with different contracts | `v1` |
| Full ID | Readable, deterministic, rarely changes | `billing.invoice.worker.v1` |

**Do not** use a startup-generated UUID as the endpoint ID if the goal is stable lookup.

```java
// Strategic ANTI-PATTERN: do not use a runtime-generated ID
// for an endpoint that dashboards/scripts must look up reliably.
String ephemeral = java.util.UUID.randomUUID().toString();
```

The snippet above only illustrates a UUID changing across runs; it is not how annotation values are written, since Java annotation values must be compile-time constants (unless using Spring-supported placeholder/SpEL mechanisms).

### 2.2. Must IDs Differ Across Replicas?

**Not required** if two replicas are two **separate application contexts** running the same logical endpoint. For example:

```text
Pod A / Spring Context A              Pod B / Spring Context B
  Registry A                            Registry B
  id = billing.invoice.worker.v1        id = billing.invoice.worker.v1
      |                                      |
      v                                      v
  container A                            container B
      |                                      |
      +-------- Queue billing.invoice.jobs --+
                 competing consumers
```

Each registry has its own ID namespace. Two containers on two replicas can share the same ID because they are not registered into **the same** registry. On a Queue, they compete to receive messages via the broker; having the same ID does not cause a Queue to duplicate messages.

**However, in centralized telemetry**, the `endpointId` tag alone is not enough to identify a unique runtime container. Combine it with `service`, `environment`, and `instance/pod` in observability data. Do not stuff a pod UUID into `@JmsListener.id` just to get a cluster-unique tag if the application needs management by a stable logical ID.

### 2.3. Duplicate IDs in the Same Registry Are Rejected

`JmsListenerEndpointRegistry` checks IDs when registering listener containers. Two endpoints with the same ID in **one registry** is a configuration error, not "Spring automatically merging listeners".

```java
// INVALID EXAMPLE: two endpoints in the same application context.
@JmsListener(id = "billing.worker.v1",
             destination = "billing.invoice.jobs")
public void invoice(String value) { /* ... */ }

@JmsListener(id = "billing.worker.v1",
             destination = "billing.reconcile.jobs")
public void reconcile(String value) { /* ... */ }
```

When Spring registers the second endpoint, the registry can throw an `IllegalStateException` with a message like `Another endpoint is already registered with id 'billing.worker.v1'`. This is an error to fix in configuration/code, **not an error saying the broker has not created the queue**.

Note: this error does not mean each application replica must generate a different ID. The uniqueness boundary is **the registry instance holding the endpoints**.

## 3. Do Not Confuse Endpoint id with Other Types of IDs

There are many uses of the word "id" in JMS/Spring. They solve different problems.

| Identifier | Where does it live? | Scope/meaning | Example |
| --- | --- | --- | --- |
| `@JmsListener(id=...)` | Spring annotation/registry | Name of the endpoint container **in the Spring registry** | `billing.invoice.worker.v1` |
| `destination` | Spring annotation/JMS provider | Name of Queue or Topic to receive messages from | `billing.invoice.jobs` |
| `containerFactory` | Spring annotation | Spring bean name of the factory that creates containers | `invoiceListenerFactory` |
| `@Component("...")` | Spring BeanFactory | Bean name of the handler object | `invoiceJobListener` |
| `subscription` | `@JmsListener` / JMS Topic | Subscription name when configuring durable/shared | `billing-audit-v1` |
| JMS `clientId` | JMS Connection/Container | Client connection identifier for certain subscription use cases; has its own uniqueness rules | `billing-audit-client` |
| `JMSMessageID` | Header of **each message** | Provider-assigned ID on send, unique per message | `ID:...` (provider-specific) |
| `JMSCorrelationID` | Message header | Matches request/reply per application contract | `req-42` |
| `businessId` | Application body/property | Business identifier and idempotency | `invoice-42` |

**Never infer that**:

- `@JmsListener(id="x")` sets JMS `Connection.setClientID("x")`.
- `@JmsListener(id="x")` creates a durable subscription named `x`.
- `@JmsListener(id="x")` makes the broker create a queue named `x`.
- `@JmsListener(id="x")` forces received messages to have `JMSMessageID="x"`.
- `@Component("x")` automatically uses `x` as the endpoint id.

Each field has its own API and lifecycle. A service may need **both a fixed endpoint ID and a fixed subscription name**, and setting one does not substitute for the other.

### 3.1. Queue Example: Endpoint ID Is Not JMS Group ID

JMS has the standard header/property `JMSXGroupID` to group related messages when the provider supports message grouping. The endpoint ID is **not** `JMSXGroupID` and does not instruct the broker to pin a partition to a specific endpoint.

If sequential processing per invoiceId is required, design message grouping/ordering and concurrency according to the provider, rather than naming the listener id after invoiceId.

### 3.2. Durable Topic Example: Three Separate IDs

```java
@JmsListener(
        id = "billing.audit.topic.consumer.v1",
        destination = "billing.events",
        subscription = "billing-audit-v1",
        containerFactory = "billingDurableTopicFactory")
public void onEvent(String payload) { /* ... */ }
```

This is an illustrative method inside a Spring-managed component with a properly configured durable Topic factory. `id` is for the registry; `subscription` is for the durable JMS subscription. `clientId` may need to be configured via `ConnectionFactory`/listener factory depending on shared/unshared semantics and provider version.

Changing the **endpoint ID** for operational tooling does not automatically delete a broker subscription. Changing the **subscription name/client identity** can create a new subscription and severely affect the backlog. Therefore, manage both kinds of names independently.

With multiple replicas, **do not assign the same unshared durable JMS clientId** to active connections assuming identical endpoint IDs will load-balance them. Decide whether to use a shared durable subscription or design distinct identities per the JMS/provider contract.

## 4. Complete Spring JMS Configuration Example with Stable IDs

The example below uses **Spring Framework 6.x or 7.x, Java 17+, Jakarta Messaging**. It requires the `spring-jms` dependency, a JMS provider, a broker, and a real `ConnectionFactory`. The files are shown as **classes within one Spring project**; they cannot be run via `javac` with only the JDK.

Assume the broker has two Queues:

- `billing.invoice.jobs`: processes invoice generation.
- `billing.reconcile.jobs`: reconciliation.

### 4.1. Declaring the Listener Container Factory

**File `BillingJmsConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class BillingJmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);       // Queue.
        factory.setSessionTransacted(true);    // Local JMS transaction.
        factory.setConcurrency("1-3");
        return factory;
    }
}
```

- `@EnableJms` enables annotation-driven JMS endpoints.
- The default factory bean named `jmsListenerContainerFactory` is looked up by Spring when an annotation does not specify its own factory.
- `setSessionTransacted(true)` is an option for listeners needing redelivery on processing errors; it is not a prerequisite for setting an ID.
- `concurrency="1-3"` can create multiple consumer sessions for one endpoint; it **does not mean three endpoint IDs are created**.
- Broker config, authentication, resource provisioning, and connection recovery are managed by the project/provider. Queues may need to be pre-created.

### 4.2. Two Handlers with Different IDs

**File `InvoiceJobListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceJobListener {

    @JmsListener(
            id = "billing.invoice.worker.v1",
            destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        System.out.println("Invoice: " + invoiceId);
    }
}
```

**File `ReconciliationListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationListener {

    @JmsListener(
            id = "billing.reconcile.worker.v1",
            destination = "billing.reconcile.jobs")
    public void consume(String batchId) {
        System.out.println("Reconcile: " + batchId);
    }
}
```

These two endpoints have stable IDs even if Java class names change (provided the annotation IDs are preserved). One bean can have multiple listener methods as long as each endpoint has its own ID.

If a `TextMessage` containing `INV-42` is sent to `billing.invoice.jobs`, the first listener **can** print `Invoice: INV-42` if the broker is running, the queue is valid, and the message is processed by the consumer. No fixed stdout is promised for the integration snippet because timing, concurrency, redelivery, number of replicas, and broker state are runtime-dependent.

### 4.3. Do Not Blindly Set id Equal to the Queue Name

Nothing prevents writing:

```java
@JmsListener(
        id = "billing.invoice.jobs",
        destination = "billing.invoice.jobs")
```

However, this is **not a good general rule**. When **two different endpoints listen to the same destination** (e.g., different selectors or different listener methods), using the queue name as the ID causes a registry collision. Choose the ID by **logical consumer role** instead of copying the destination verbatim.

## 5. Finding a Container by id: JmsListenerEndpointRegistry

Spring provides:

```text
org.springframework.jms.config.JmsListenerEndpointRegistry
```

Two key methods:

```java
Set<String> getListenerContainerIds();

@Nullable
MessageListenerContainer getListenerContainer(String id);
```

`getListenerContainerIds()` returns the set of IDs of listener containers managed by the registry. `getListenerContainer(id)` returns the matching container or **`null`** when not found.

Containers expose lifecycle methods:

```java
boolean isRunning();
void start();
void stop();
```

Do not call `registry.getListenerContainer(id).stop()` without checking for null; if the key is wrong, you will get a `NullPointerException` and no container will be stopped.

### 5.1. Safe Lookup Service

**File `BillingListenerControl.java`:**

```java
import java.util.Set;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public final class BillingListenerControl {

    public static final String INVOICE_ID =
            "billing.invoice.worker.v1";
    public static final String RECONCILE_ID =
            "billing.reconcile.worker.v1";

    private final JmsListenerEndpointRegistry registry;

    public BillingListenerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public Set<String> registeredIds() {
        return Set.copyOf(registry.getListenerContainerIds());
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);

        if (container == null) {
            throw new IllegalArgumentException(
                    "Unknown JMS endpoint id: " + id);
        }
        return container;
    }

    public boolean invoiceContainerRunning() {
        return requireContainer(INVOICE_ID).isRunning();
    }

    public void stopInvoiceListenerLocally() {
        requireContainer(INVOICE_ID).stop();
    }

    public void startInvoiceListenerLocally() {
        requireContainer(INVOICE_ID).start();
    }
}
```

This is a complete class for use in a Spring project with `@EnableJms` enabled; it is not runnable with plain JDK. Lifecycle calls must be protected by **authorization/operational procedures**. Never expose `stop()`/`start()` directly as an HTTP endpoint without authentication, role checks, auditing, and safety controls.

**One crucial sentence:** Stopping a container on **one application instance** does not mean stopping all replicas in the cluster. The registry lives inside one context/JVM, not as a broker-wide registry.

### 5.2. Comparing getListenerContainers with Autowiring Beans

Spring reference/Javadoc states clearly: listener containers created by the endpoint registry **are not necessarily individual beans in the `ApplicationContext`**. Therefore:

```java
// Do not rely on @Qualifier("billing.invoice.worker.v1")
// to autowire a MessageListenerContainer like an ordinary @Bean.
```

Instead:

```java
MessageListenerContainer container =
        registry.getListenerContainer("billing.invoice.worker.v1");
```

If the application has a container you created manually via `@Bean`, it belongs to a different mechanism and may not appear in the registry of annotated endpoints. Do not assume `getListenerContainerIds()` lists every `MessageListenerContainer` that might exist anywhere in the ApplicationContext.

### 5.3. The ID List Is a Set, Not an Ordered List

`getListenerContainerIds()` returns a `Set<String>`. Do not rely on iteration order or startup order to decide which endpoint is "#0" or "#1". If stable display is needed:

```java
var sorted = registry.getListenerContainerIds()
        .stream().sorted().toList();
System.out.println(sorted);
```

The print line only illustrates sorting; the actual list depends on listener configuration in the application context. Stable IDs can be used in tests or metrics systems without depending on return order.

### 5.4. isRunning Is Not a Complete Health Check

`container.isRunning() == true` shows that the container lifecycle **is in the running state according to Spring**. It does not prove:

- That the broker connection is currently healthy and all consumers subscribed successfully.
- That the destination exists/has the right type and the principal has receive permissions.
- That messages are being delivered and handlers are committing business work.
- That there are no retry/recovery loops, flaky connections, or poison messages.
- That queue backlog and oldest message age are within SLA.

A listener container with recovery logic during temporary broker downtime can remain in the started state while delivery is ineffective. Health/observability must cover **broker connectivity, consumer counts, queue/topic subscription backlog, processing latency, error logs, and business outcomes**, not just `isRunning`.

## 6. Starting/Stopping by id: Uses and Limits

A stable ID lets operations teams:

- Temporarily pause consumption for **one logical listener** on an instance during maintenance.
- Restart only the right listener instead of stopping the entire JMS subsystem.
- Verify endpoint presence after a rollout/refactor.
- Attach a consistent endpoint name to diagnostics and logs.
- Write safe automation using an **allowlist** of controllable endpoints.

### 6.1. What Does Start/Stop Change?

```text
Spring Context A
  Registry A
    billing.invoice.worker.v1
         |
         +-- stop() --> local listener container stops consuming
         |
         +-- start() -> local listener container starts again

JMS Broker
  Queue billing.invoice.jobs
    still exists, governed by persistence/TTL/retention policies
```

Calling `stop()` on a container **does not delete the Queue** and does not purge messages. Pending messages can remain on the broker per configuration. In-flight messages, session transactions, and when stop completes must be understood per container/provider implementation; do not claim every `stop()` immediately cancels/rolls back all running handlers.

`start()` reactivates the container lifecycle, but does not guarantee the broker is healthy or new messages will immediately be processed. Check logs/metrics.

### 6.2. Multiple Replicas Must Be Controlled Per Instance

If two replicas share ID `billing.invoice.worker.v1` and you call `stop()` on **Replica A**:

- A stops receiving (per local container lifecycle).
- B **can still continue receiving** from the same queue.
- If the goal is global maintenance, you need a workflow acting across the whole fleet, or to pause producers/consumers via appropriate deployment/broker controls.
- Operational commands should log both `logical endpoint ID` and `instance identity` to avoid misinterpreting scope.

**Assigning the same ID on two replicas does not turn `JmsListenerEndpointRegistry` into a distributed registry.**

### 6.3. Caution When a Listener Consumes a Topic

On a non-durable Topic, stopping can leave the subscription/consumer inactive depending on container lifecycle; messages published while no subscriber is active **may not be retained**. With durable subscriptions, retention depends on durable identity configuration, delivery mode, expiration, and broker policy. Never claim "stop is always safe for every message" merely because the endpoint ID is stable.

If you want maintenance without losing topic events, design proper durable/shared subscriptions **before** relying on stop/start.

## 7. Setting IDs via Property Placeholders

Some systems prefer centralized configuration:

```java
@Component
public class InvoiceJobListener {

    @JmsListener(
            id = "${app.jms.invoice.endpoint-id:billing.invoice.worker.v1}",
            destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        // ...
    }
}
```

The `id` annotation attribute declares a String with a **Spring property placeholder**, not an ordinary Java runtime expression. `JmsListenerAnnotationBeanPostProcessor` resolves the value using an embedded value resolver before registering the endpoint. If the property is not supplied, the part after the colon is the default `billing.invoice.worker.v1`.

**Prerequisite:** the final resolved value must be **nonblank and unique within the registry**. If configuration changes the value on every deployment, the ID is no longer stable as intended.

### 7.1. When Should Placeholders Be Used?

Suitable when:

- The same codebase deploys different logical listener roles under different profiles, yet **each role has a fixed, controlled ID**.
- An organization enforces ID conventions in config validated at startup.
- Planned migrations from an old ID to a new ID need to be controlled via environment config.

Unsuitable when:

- Each pod uses a random UUID as `endpoint-id`.
- IDs are generated from timestamps or build numbers, changing on every deployment.
- IDs contain secrets, customer PII, or tokens.
- IDs are entered arbitrarily by external users and could collide with another endpoint ID.

**Reminder:** the same logical listener running across multiple replicas can use the same endpoint ID because each replica has its own registry. Do not use placeholders to invent pod-specific values just out of fear of "cluster-wide ID collisions".

### 7.2. If Changing the Config Namespace

Moving from:

```text
billing.invoice.worker.v1
```

to:

```text
billing.invoice.consumer
```

should be treated as changing **a Spring administrative address**, not automatically migrating a broker resource. Update all `registry.getListenerContainer(...)` calls, dashboards, runbooks, startup assertions, alert labels, and automation scripts. Do not change it merely for a method refactor with no operational reason.

## 8. Multiple @JmsListener Annotations on One Method: One ID per Endpoint

`@JmsListener` is a **repeatable annotation** in Spring. One method can listen to two destinations:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class SharedInvoiceHandler {

    @JmsListener(
            id = "billing.invoice.primary.v1",
            destination = "billing.invoice.primary")
    @JmsListener(
            id = "billing.invoice.retry.v1",
            destination = "billing.invoice.retry")
    public void handle(String invoiceId) {
        // One Java method, two independent listener endpoints.
    }
}
```

Two annotations create **two endpoints**, so they require **two unique IDs**. Sharing a Java method does not mean only one container is created.

Even though both endpoints call the same handler, they may have:

- Different destinations and selectors.
- Different factories/concurrency.
- Different retry histories, DLQs, and backlogs on the broker.
- Separate lifecycle states when retrieved from the registry.

Having one method handle two streams **does not automatically make** the Java method or shared dependencies thread-safe. With concurrency, manage mutable state, idempotency, and transactions carefully.

### 8.1. Avoid Turning IDs into Method Names

If you set an ID like `com.example.billing.InvoiceHandler.processInvoice`, renaming the package/class/method changes the ID even when the logical endpoint has not changed. If the goal is stability across refactors, use a **business-facing ID** independent of Java structure.

The same applies to default durable subscription names (Spring may derive them from class/method if unspecified). However, **subscription name** is a broker-side identity; manage it separately, and do not assume an explicit endpoint ID replaces the default subscription name.

## 9. Registering Listener Endpoints Programmatically

When endpoints are not written with annotations, Spring also supports `JmsListenerConfigurer` and `JmsListenerEndpointRegistrar`.

**File `DynamicBillingListenerConfig.java`:**

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration
@EnableJms
public class DynamicBillingListenerConfig
        implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        SimpleJmsListenerEndpoint endpoint =
                new SimpleJmsListenerEndpoint();

        endpoint.setId("billing.manual.worker.v1");
        endpoint.setDestination("billing.manual.jobs");
        endpoint.setMessageListener(message -> {
            // Process raw jakarta.jms.Message.
        });

        registrar.registerEndpoint(endpoint);
    }
}
```

This is a **Spring JMS configuration class**, not standalone JDK-runnable code. It assumes the application already has a **default listener container factory** or the registrar is configured with an appropriate factory, along with a broker/provider/destination. `SimpleJmsListenerEndpoint` describes the endpoint and does not automatically ensure physical Queue creation.

Key points to remember:

- `endpoint.setId(...)` follows **the same ID contract** as `@JmsListener(id=...)`.
- The registry uses that ID for lifecycle management and lookup.
- If code registers two endpoints with the same ID in one registry, it will be rejected.
- For dynamic runtime endpoints generated from configuration, enforce a deterministic strategy and allowlist so IDs do not become unbounded random combinations.

### 9.1. Explicit Factory When Registering Programmatically

If the application has multiple factories:

```java
// Inside configureJmsListeners(...) with an injected factory:
registrar.registerEndpoint(endpoint, specificJmsListenerContainerFactory);
```

This illustrates the contract; `specificJmsListenerContainerFactory` must be a valid `JmsListenerContainerFactory<?>` bean in scope, not created out of thin air. Factory/bean names are not endpoint IDs; a factory can be shared across many endpoints.

### 9.2. If You Need to Create Hundreds of Per-Tenant Endpoints

Consider carefully:

- Do you truly need **a separate JMS listener container and ID per tenant**, or should you use queues/selectors/different routing?
- What are the broker's max connections/sessions/consumers?
- Is there an endpoint count limit and cleanup when a tenant is deleted?
- Are IDs reassigned using a stable mapping rather than database retrieval order?
- If tenant names contain characters unsuitable for metrics/logs or sensitive info, are they normalized/anonymized?
- Does restarting produce **the exact same set of logical IDs**?
- If using per-tenant durable topics, are subscription identity and retention managed separately?

Stable IDs **solve manageability**, not resource explosion, data isolation, or JMS ordering.

## 10. Testing the ID Contract at Application Startup

You do not need to wait for real messages to be processed to know whether Spring registered the right IDs.

### 10.1. Basic Assertions

In an **integration test with a Spring ApplicationContext** and JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jms.config.JmsListenerEndpointRegistry;

class BillingListenerIdsTest {

    @Autowired
    JmsListenerEndpointRegistry registry;

    @Test
    void expectedEndpointsAreRegistered() {
        assertTrue(registry.getListenerContainerIds()
                .contains("billing.invoice.worker.v1"));

        assertTrue(registry.getListenerContainerIds()
                .contains("billing.reconcile.worker.v1"));

        assertNotNull(registry.getListenerContainer(
                "billing.invoice.worker.v1"));
    }
}
```

This is a **test class fragment**, requiring a test runner that creates the Spring context and performs dependency injection (e.g., Spring Test/Boot test configuration). Writing `@Autowired` in a plain JUnit class not managed by Spring leaves the field null. In test environments without a broker, you can configure the listener factory with **`setAutoStartup(false)`** to test the registry without starting consumption, then run dedicated integration tests against a real provider.

Do not assert an exact ID count if the project contains many other valid endpoints, unless the test isolates a minimal context. Assert the expected ID contract.

### 10.2. Negative Test: Duplicate IDs

In a dedicated test application context, attempt to register two endpoints with the same ID (via annotations or programmatically). The test should verify that **startup/registration fails** rather than silently renaming duplicates to a temporary name.

This is a configuration error, so fail-fast is good behavior. Do not swallow `IllegalStateException` and continue running an uncontrolled listener.

### 10.3. Testing Stability Across Refactors

Before renaming a handler class/method, record the expected ID list contract. After refactoring:

1. Boot the test context and retrieve `getListenerContainerIds()`.
2. Compare **business-critical IDs** against the expected set.
3. Verify destination/selector/factory are correct; checking ID alone is not enough.
4. Ensure operational scripts still use the old keys.
5. For durable topics, also verify **subscription name/client ID** did not change unintentionally.

If the annotation already specifies `id` explicitly, Java code refactors normally do not need to change the ID. That is the main benefit of explicit stable IDs.

### 10.4. Checking Absence Clearly

`registry.getListenerContainer("billing.invoice.worker.v1") == null` can happen because:

- `@EnableJms`/annotation post-processing is not enabled.
- The handler is not a Spring-managed bean or lies outside component scan.
- The annotation is on a class/method not detected by Spring under the current structure.
- The endpoint id changed due to a config placeholder/profile.
- The container/endpoint was registered via **a different registry** from the bean you injected.
- The test app context does not include the configuration containing the listener.

Do not conclude "the queue vanished" solely from a null return value. Null here means **the current registry has no endpoint with that ID**, not a broker state.

## 11. Standalone Runnable Java 17: Simulating Stable Registry and Instance Scope

To reinforce registry uniqueness and scope without starting a broker, the following example runs **with JDK 17 alone**. It simulates an `endpoint ID -> running state` mapping, does not implement Spring JMS, does not send/receive messages, and does not replace provider testing.

Create file **`EndpointIdScopeDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public final class EndpointIdScopeDemo {

    static final class Registry {
        private final Map<String, Boolean> states = new LinkedHashMap<>();

        void register(String endpointId) {
            if (states.putIfAbsent(endpointId, true) != null) {
                throw new IllegalStateException(
                        "Duplicate endpoint: " + endpointId);
            }
        }

        void stop(String endpointId) {
            if (!states.containsKey(endpointId)) {
                throw new IllegalArgumentException(
                        "Unknown endpoint: " + endpointId);
            }
            states.put(endpointId, false);
        }

        boolean running(String endpointId) {
            return Boolean.TRUE.equals(states.get(endpointId));
        }

        Set<String> ids() {
            return states.keySet();
        }
    }

    public static void main(String[] args) {
        String invoice = "billing.invoice.worker.v1";

        Registry podA = new Registry();
        podA.register(invoice);
        podA.register("billing.reconcile.worker.v1");

        Registry podB = new Registry();
        podB.register(invoice); // Same ID as A is allowed because it is a different registry.

        podA.stop(invoice);      // Only changes state in pod A.

        boolean duplicateRejected = false;
        try {
            podA.register(invoice);
        } catch (IllegalStateException ex) {
            duplicateRejected = true;
        }

        System.out.println("A ids: " + podA.ids());
        System.out.println("A invoice running: " + podA.running(invoice));
        System.out.println("B invoice running: " + podB.running(invoice));
        System.out.println("Duplicate in A rejected: " + duplicateRejected);
    }
}
```

Compile and run:

```bash
javac EndpointIdScopeDemo.java
java EndpointIdScopeDemo
```

**Exact stdout:**

```text
A ids: [billing.invoice.worker.v1, billing.reconcile.worker.v1]
A invoice running: false
B invoice running: true
Duplicate in A rejected: true
```

Explanation:

- `LinkedHashMap` preserves insertion order so `ids()` output is deterministic in the demo program.
- Two Registry objects can hold **the same ID** without conflict, analogous to two separate Spring contexts.
- Within the same Registry, registering the ID a second time is rejected.
- Stopping A does not stop B.
- The demo does not simulate JMS `@JmsListener`, Spring lifecycle, broker queues, transactions, connection recovery, or delivery semantics. Therefore, do not treat its stdout as a promise about timing or broker state in a real application.

## 12. Observability and Logging: How to Use Stable IDs?

A stable endpoint ID is very helpful as a **logical label** in metrics/tracing/logging, though Spring does not guarantee every telemetry system automatically tags by ID unless you instrument it.

### 12.1. A Diagnostic Record Should Distinguish Two Dimensions

Example log structure:

```text
service=billing
environment=prod
instance=pod-a
endpointId=billing.invoice.worker.v1
destination=billing.invoice.jobs
state=RUNNING
pendingMessages=...
lastProcessedBusinessId=...
```

Fields like `pendingMessages` and actual state must come from **broker/application metrics**, not be inferred from the endpoint registry. Attaching a stable `endpointId` lets dashboards trace the exact logical listener across deployments; `instance` distinguishes replicas.

### 12.2. Avoid Uncontrolled Label Cardinality

Do not use:

```text
endpointId=billing.invoice.worker.<random-uuid>
endpointId=billing.invoice.worker.<timestamp>
endpointId=billing.invoice.worker.<every-request-id>
```

Those are illustrative strings, **not annotation syntax**. Random/time/request-specific IDs flood dashboards with new labels, make trend comparisons across runs impossible, and incur high metric costs.

Endpoint IDs should be a **managed finite set** (one ID per logical consumer role), while `requestId`/`JMSMessageID` belong in trace/event fields.

### 12.3. Lifecycle Metrics Alone Are Not Enough

A quality dashboard should combine:

- Registry ID count and presence: is the listener registered?
- Container lifecycle: is it running?
- Broker consumer count/connection status: did the container actually obtain consume access?
- Queue depth or durable subscription backlog: are messages piling up?
- Oldest message age: is SLA being breached?
- Processed rate, failure/retry/DLQ counts: is the business handler working effectively?
- Application instance: which replica is missing/stopped?
- Business IDs/idempotency: processing does not cause duplicate effects on rollback.

**An ID is an observability key; it does not create a health guarantee by itself.**

## 13. Multi-Environment Deployment and Avoiding Name Collisions

### 13.1. Dev/staging/prod

You can keep the same logical endpoint ID `billing.invoice.worker.v1` across dev/staging/prod because they are separate Spring contexts. Centralized logging/metrics must include an `environment` label to separate data.

Do not change IDs per environment if shared scripts expect a stable logical name and an environment label already exists. If an organization mandates namespacing IDs by environment, stay consistent and test that environment's resolver/registry; understand that is a governance choice, not a Spring requirement.

### 13.2. Two services sharing broker destination

The Billing service and Audit service can listen to the same queue, while still needing endpoint IDs expressing different roles, such as `billing.invoice.worker.v1` and `audit.invoice.worker.v1`. **However**, on a queue, the two services compete for messages—each service does not receive a copy. If Audit needs every event, design a Topic/subscriptions or dedicated fan-out routing.

Stable IDs do not change queue/topic delivery semantics.

### 13.3. Blue/green or canary deployment

Two application versions running concurrently:

- Each version has its own registry, so both can use the same logical endpoint ID.
- If both listen to one queue, they **both participate as competing consumers**, unless isolated by selectors/routing.
- If a canary targets 5% traffic, endpoint IDs do not split traffic automatically; use appropriate routing/deployment/broker mechanisms.
- With durable Topics, sharing the same `clientId`/subscription across two versions can violate unshared subscription identity; plan for shared durable or separate subscriptions.

Do not try to solve canary routing by randomizing IDs.

## 14. Process for Changing an ID Already Used in Production

Changing an ID is like changing **an internal operations API**.

### Before changing

1. Find all places calling `getListenerContainer("old-id")`, start/stop automation, test assertions, health checks, dashboard filters, and log correlations.
2. Determine whether the logical endpoint truly changed its contract or is only a refactor.
3. Confirm you are not confusing it with changing `subscription`, `destination`, or `clientId`.
4. Check whether multiple application contexts/profiles deploy the endpoint.
5. Choose the new ID per convention and verify uniqueness against all remaining endpoints.

### During deployment

1. Ship code/config changes and ID consumers in the same release plan.
2. Test startup that the registry contains the new ID with no duplicates.
3. Update management scripts to look up the right ID before invoking lifecycle operations.
4. During rolling deployments, remember both old and new versions run briefly, so dashboards must track both logical IDs.
5. Do not delete the queue/durable subscription just because the Spring endpoint changed its ID.

### After deployment

1. Check `getListenerContainerIds()` on each instance.
2. Check broker consumer count and processing rate.
3. Verify errors/retries/backlog/DLQ do not spike abnormally.
4. Confirm all legacy automation has stopped using the old key.
5. Document the reason for the change in the runbook to prevent unintended ID changes in future refactors.

### When you **should not** change it

If you only rename the class from `InvoiceJobListener` to `InvoiceProcessor` or rename the method from `consume` to `process`, while the logical consumer remains the worker processing invoice jobs, **keep** `billing.invoice.worker.v1`. That is the whole purpose of a stable endpoint ID.

## 15. Common Mistakes and How to Fix Them

**Mistake 1 — "Leave id blank; Spring still gives an ID, so it's always fixed."**

False. An auto-generated ID exists, but it has no stability contract across refactors or registration order changes. For operational needs, declare `id` explicitly.

**Mistake 2 — "id is the queue name."**

False. `id` is the Spring registry key; `destination` determines the Queue/Topic. The strings can match, but they are two distinct concepts.

**Mistake 3 — "Two methods with the same id make Spring share load on one container."**

False. The registry rejects duplicate IDs within the same context. For concurrency, configure container `concurrency`; for multiple endpoints, use multiple IDs.

**Mistake 4 — "Every Kubernetes pod must have a different id so the broker won't reject it."**

False regarding `@JmsListener.id`. The registry is local to each pod; sharing the logical ID is proper. Broker-side `clientId`/durable subscription identity has separate rules.

**Mistake 5 — "@Component bean name is automatically used as id."**

Do not assume that. Handler beans and listener containers live in different object spaces/namespaces.

**Mistake 6 — "Changing id clears the queue backlog."**

False. Backlog is broker/destination state. Changing Spring's id does not purge, redrive, or reset a Queue.

**Mistake 7 — "Changing id and changing durable subscription name are the same operation."**

False. `subscription` and `clientId` are broker-facing; changing them wrongly can leave a new subscription unable to read old pending messages.

**Mistake 8 — "getListenerContainer(id) always returns a container."**

False. It can return `null` if the ID does not exist in the current registry; always check.

**Mistake 9 — "stop(id) stops the entire system."**

False. `stop()` on a local container only affects the instance being operated on; other replicas can keep consuming.

**Mistake 10 — "isRunning=true means the broker is healthy."**

Insufficient. You need metrics on connectivity, backlog, actual deliveries, failures, and recovery.

**Mistake 11 — "The ID must include the build hash so we know which version is running."**

Unsuitable for stable IDs. Build version belongs in separate metadata/deployment labels; endpoint ID represents a long-lived logical role.

**Mistake 12 — "Two @JmsListener annotations on the same method only need one id."**

False. Each annotation registers a separate endpoint and needs its own ID.

**Mistake 13 — "Setting id equal to the factory name makes Spring pick that factory."**

False. `containerFactory` is the bean name used to select the factory and is unrelated to `id`.

**Mistake 14 — "Renaming a method/class changes nothing when explicit id is missing."**

Uncertain. Auto-ID can depend on registration order; default subscription names can also be derived from the fully qualified class/method. Set explicit endpoint IDs and subscription identities when stability is required.

**Mistake 15 — "Having a stable ID means messages are processed exactly once."**

False. Delivery, ack/transactions, idempotency, retries, and business correctness are separate concerns.

**Mistake 16 — "Any HTTP client can pass an id to stop a listener."**

Dangerous. Start/stop operations are privileged operational actions; restrict the endpoint allowlist, enforce authentication/authorization, audit calls, and ensure rollback paths.

## 16. Code Review and Operations Checklist

Before merging a new `@JmsListener`:

- [ ] Does the endpoint have an explicit, readable, and **stable** `id` across deployments?
- [ ] Is the ID unique across all annotated/programmatic endpoints in that registry?
- [ ] Does the ID represent the logical listener role rather than registration order, UUIDs, or timestamps?
- [ ] If there are multiple replicas, do monitoring dashboards distinguish logical ID from instance identity?
- [ ] Is `id` kept distinct from `destination`, `containerFactory`, `subscription`, and JMS `clientId`?
- [ ] Does the listener have proper Queue/Topic semantics and broker resources?
- [ ] Are multiple listeners on the same Queue intended to be competing consumers?
- [ ] If multiple annotations are on one method, does each annotation have its own ID?
- [ ] If the ID comes from a placeholder, is the resolved value across all profiles nonblank and non-colliding?
- [ ] Does a startup integration test verify the registry contains the critical IDs?
- [ ] Are there negative unit/integration tests for duplicate id and missing id lookup?
- [ ] Is there a clear registry lookup point for lifecycle management instead of injecting containers as regular beans?
- [ ] Are administrative start/stop APIs (if any) protected and audited?
- [ ] Before stopping a Topic listener, have non-durable/durable subscription and retention behaviors been reviewed?
- [ ] Do health checks rely on broker/app metrics rather than only `isRunning`?
- [ ] Does every ID change have a migration plan for scripts, alerts, dashboards, and runbooks?
- [ ] Does changing an ID avoid accidentally altering durable subscription names/clientIds?
- [ ] Are endpoint IDs never mixed up with JMSMessageID/JMSCorrelationID/idempotency keys?

## 17. Self-Check Questions

**Question 1.** `@JmsListener(id="billing.worker", destination="billing.jobs")`: what do the two Strings describe?

**Answer:** `id` is the endpoint container name in the Spring registry; `destination` is the JMS Queue/Topic address from which the listener receives.

**Question 2.** Why should you avoid writing scripts calling `getListenerContainer("org.springframework.jms.JmsListenerEndpointContainer#0")`?

**Answer:** That ID can be implementation-generated and registration order can change across code/deployments; there is no stability contract for the logical method.

**Question 3.** Are two listener methods with the same ID in one ApplicationContext valid?

**Answer:** No. The registry rejects duplicate IDs because each ID must point to exactly one container in that registry.

**Question 4.** Do two separate Spring replicas both declaring `id="billing.invoice.worker.v1"` conflict in the registry?

**Answer:** No, if they are two independent registries. However, JMS clientId/durable identity has separate rules.

**Question 5.** Must the endpoint ID match the `@Component` bean name?

**Answer:** No. The handler bean and the container endpoint have different namespaces and responsibilities.

**Question 6.** To stop a listener with a known ID, which API is appropriate?

**Answer:** `JmsListenerEndpointRegistry.getListenerContainer(id)`, then check for null and call `stop()` on the local container.

**Question 7.** Does stopping listener A stop the listener on pod B?

**Answer:** No. The registry only knows about containers in its own ApplicationContext.

**Question 8.** Does `getListenerContainer(id)` returning null prove the broker queue does not exist?

**Answer:** No. It only means the registry has no endpoint with that ID.

**Question 9.** Does `isRunning() == true` prove the service has processed messages?

**Answer:** No. You need broker connectivity, consumer metrics, error logs, and business completion evidence.

**Question 10.** One method has two `@JmsListener` annotations targeting two destinations; how many IDs are needed?

**Answer:** Two distinct endpoint IDs for clear management and to avoid collisions.

**Question 11.** Does changing the ID from `invoice.worker.v1` to `invoice.worker.v2` automatically move pending queue messages?

**Answer:** No. That changes an administrative key in Spring; queue state on the broker is separate.

**Question 12.** A durable topic consumer has `id="audit.v1"` without proper subscription identity configured. Does that ID automatically make it a durable subscriber?

**Answer:** No. It needs appropriate factory settings, subscription name, and JMS connection identity, separate from the endpoint ID.

**Question 13.** Why should you avoid adding a build number to `id`?

**Answer:** It changes the key on every deployment, breaking scripts/dashboards/tests that rely on a stable logical ID. Build numbers belong in separate metadata labels.

**Question 14.** When an endpoint's Java class/method changes while keeping the same contract, what should be done with the ID?

**Answer:** Keep the explicit ID unchanged so operational tools do not lose their key.

**Question 15.** If you want to view all IDs of annotated containers in the registry, which API do you use?

**Answer:** `registry.getListenerContainerIds()`; the Set guarantees no ordering, so sort if display order matters.

**Question 16.** Why is a stable ID alone not enough to safely manage multiple replicas?

**Answer:** The ID is a local registry key; you must specify the target instance and ensure administrative authorization/fleet orchestration.

**Question 17.** Is `JMSMessageID` used to look up a listener container?

**Answer:** No. It identifies a message sent by the JMS provider, not a listener.

**Question 18.** When adding a listener in code, what should you check before deciding on its ID?

**Answer:** Logical role, uniqueness in the registry, destination semantics, compatibility with runbooks/scripts, and risk of changing subscription identity if it is a durable Topic.

## Conclusion

**`@JmsListener(id = "...")` identifies a Spring JMS listener endpoint/container**, used as a key in `JmsListenerEndpointRegistry`. If an application needs to operate, monitor, or test by endpoint name, **assign an explicit, role-stable ID that is unique within each registry** rather than relying on auto-generated IDs.

Keep three boundaries clear:

1. **Spring endpoint identity:** `id` → container lookup, lifecycle, code/tests/observability.
2. **JMS transport identity:** `destination`, `subscription`, JMS `clientId` → broker address and permission to receive messages.
3. **Message/business identity:** `JMSMessageID`, `JMSCorrelationID`, business request ID → tracing, request/reply, and idempotency.

A stable endpoint ID enables **better manageability**, but it does not replace queue/topic design, durable subscriptions, transactions, broker monitoring, or securing administrative operations.

### Official References

1. [Spring Framework – @JmsListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html) — `id()` is a unique container identifier, auto-generated ID if omitted; `destination`/`subscription`/`containerFactory` are separate attributes.
2. [Spring Framework – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@EnableJms`, annotated listener infrastructure, repeatable `@JmsListener`, and programmatic endpoint registration.
3. [Spring Framework – JmsListenerEndpointRegistry API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html) — `getListenerContainer(id)`, `getListenerContainerIds()`, registration/lifecycle, and container management.
4. [Spring Framework – MessageListenerContainer API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/MessageListenerContainer.html) — `start()`/`stop()`/`isRunning()` lifecycle and JMS container abstraction.
5. [Spring Framework – JmsListenerAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListenerAnnotationBeanPostProcessor.html) — annotation discovery, endpoint registration, and embedded value resolution.
6. [Spring Framework – DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html) — connection factory, concurrency, transactions, and container creation.
7. [Spring Framework – JmsListenerConfigurer API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html) — configuration hook to register endpoints programmatically.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — JMS client identifiers, queue/topic semantics, durable/shared subscriptions, message headers; these identifiers **differ from** Spring's endpoint ID.
