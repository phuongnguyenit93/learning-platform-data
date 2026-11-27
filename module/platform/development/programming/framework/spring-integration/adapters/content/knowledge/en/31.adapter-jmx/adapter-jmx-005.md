# JMX operation-invoking adapter in Spring Integration

## 1. Problem and role in the integration flow

In a Java system, many management actions are exposed via **Java Management Extensions (JMX)**: refreshing a cache, forcing configuration reload, triggering statistics collection, or asking a component to perform maintenance. Those actions are called **operations** on an **MBean**. Normally, operators invoke them from JConsole/VisualVM or a JMX client. However, an integration flow sometimes needs to issue management commands immediately upon receiving an event from another system.

The **JMX operation-invoking channel adapter** solves this problem: it receives a `Message<?>` from a Spring Integration `MessageChannel` and invokes the corresponding operation on the MBean via `MBeanServer`. It is an **event-driven outbound adapter** (message-driven): when a message arrives, the adapter executes; no poller is required to query the MBean periodically.

In the **`SPRING_INTEGRATION_ADAPTERS`** module, this adapter is a way to connect Spring Integration to Java management interfaces alongside file, SFTP, HTTP, JMS, AMQP, Kafka, and database adapters. The focus of this lesson is the message contract, routing into the adapter, operation selection, error management, and JMX connection lifecycle.

Example: a flow receives a price-table update event and sends a command to clear the `pricing` cache so the management MBean prepares fresh data:

```mermaid
flowchart LR
    A[Price update event occurs] --> B[Message containing cache name]
    B --> C[MessageChannel]
    C --> D[JMX operation-invoking adapter]
    D --> E[MBeanServer]
    E --> F[CacheMaintenance MBean]
    F --> G[clearCache pricing]
```

Important point: invoking an operation over JMX can have **side effects**. Re-sending a message can re-execute the operation. Therefore, commands like clearing a cache are generally safer than non-idempotent operations such as incrementing a balance.

## 2. Components and message contract

A JMX invocation needs to know **which MBean**, **which operation**, and **what parameters** the operation takes (if any). Spring Integration obtains these values from the adapter configuration or the message:

| Component | Meaning | How to provide |
| --- | --- | --- |
| `object-name` | `ObjectName` identifying the MBean, e.g. `demo.integration:type=Maintenance,name=Cache` | XML attribute or `JmxHeaders.OBJECT_NAME` header |
| `operation-name` | Operation name exposed by the MBean, e.g. `clearCache` | XML attribute or `JmxHeaders.OPERATION_NAME` header |
| `payload` | Argument value(s) passed to the operation | Message payload; ignored for zero-argument operations |
| `mbean-server` | Bean referencing the `MBeanServer` | Defaults to looking up a bean named `mbeanServer`; a different name can be specified |
| `channel` | Input channel receiving messages for the outbound adapter | `MessageChannel` name in Spring Integration |

**Precedence order:** for MBean name and operation name, the adapter checks headers first. If a header is absent, it falls back to the default value configured on the adapter. Uncontrolled headers can cause a message to invoke the wrong MBean or operation, even when XML declares defaults.

To set headers in Java, use the constants in `org.springframework.integration.jmx.JmxHeaders` rather than typing raw strings like `jmx_operationName`.

### How is the payload mapped to parameters?

| Operation signature | Suitable payload | Notes |
| --- | --- | --- |
| `void refresh()` | Any valid payload, e.g. `"now"` | Operation takes no parameters, so the adapter ignores the payload |
| `void clearCache(String cacheName)` | `"pricing"` | Single parameter receives a single value directly |
| `void setThreshold(String cacheName, int seconds)` | `List.of("pricing", 60)` or `new Object[]{"pricing", 60}` | List/array matched by parameter position |
| `void setThreshold(String cacheName, int seconds)` | `Map.of("cacheName", "pricing", "seconds", 60)` | Relies on parameter names advertised in MBean metadata; verify actual JMX metadata |

`Map<String, ?>` uses **parameter names** as keys; `List` or arrays use **parameter positions**. If the MBean does not export parameter names as expected, prefer an ordered list. Value types must match the MBean parameter types (for example `Integer` for `int`); do not assume the adapter automatically converts a string `"60"` to an integer. For overloaded operations, check the names and signatures exposed by JMX to avoid calling the wrong overload or failing resolution.

## 3. Local runnable example: invoking a cache-clear command

The example consists of an MBean, an `MBeanServer` bean, a message channel, and an outbound adapter. The snippets below illustrate XML-namespace configuration; Java DSL applications follow the exact same JMX contract.

### Step 1: Add the JMX library

With Maven and the Spring Integration BOM or Spring Boot managing versions:

```xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jmx</artifactId>
</dependency>
```

If the project does not use a BOM or dependency management, declare a `spring-integration-jmx` version compatible with the Spring Integration version in use.

### Step 2: Create an MBean exposing the operation

```java
package demo.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(objectName = "demo.integration:type=Maintenance,name=Cache")
public class CacheMaintenance {

    @ManagedOperation(description = "Clear a cache by name")
    @ManagedOperationParameter(
        name = "cacheName", description = "Name of the cache to clear")
    public void clearCache(String cacheName) {
        if (!"pricing".equals(cacheName) && !"catalog".equals(cacheName)) {
            throw new IllegalArgumentException("Cache not allowed: " + cacheName);
        }

        // Demo: replace with the actual cache eviction logic in the application.
        System.out.println("Cleared cache: " + cacheName);
    }
}
```

`@ManagedResource` specifies the `ObjectName`; `@ManagedOperation` exposes the operation method; `@ManagedOperationParameter` describes the parameter name for JMX metadata. Simply creating the Java bean is **not enough**: the bean must also be registered with `MBeanServer` via an `MBeanExporter`.

### Step 3: Declare Spring Integration XML

Example `jmx-integration.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-jmx="http://www.springframework.org/schema/integration/jmx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd
           http://www.springframework.org/schema/integration/jmx
           https://www.springframework.org/schema/integration/jmx/spring-integration-jmx.xsd">

    <!-- Create/locate MBeanServer with default bean name mbeanServer. -->
    <context:mbean-server/>

    <!-- Export beans carrying management annotations to the same server. -->
    <context:mbean-export server="mbeanServer"/>
    <bean id="cacheMaintenance" class="demo.jmx.CacheMaintenance"/>

    <int:channel id="cacheCommands"/>

    <int-jmx:operation-invoking-channel-adapter
        id="clearCacheAdapter"
        channel="cacheCommands"
        mbean-server="mbeanServer"
        object-name="demo.integration:type=Maintenance,name=Cache"
        operation-name="clearCache"/>
</beans>
```

`<context:mbean-server/>` provides the server that the adapter looks up; `<context:mbean-export/>` registers the MBean onto that server. The two roles are distinct: **the server executes queries/commands**, while **the exporter publishes managed objects**. When integrating with an already existing MBean, exporting a new MBean is unnecessary; just ensure the adapter uses the `MBeanServer` containing that object.

`cacheCommands` is a `DirectChannel` by default. When a flow sends a message to the channel, the JMX invocation runs synchronously on the sender thread, and operation errors can propagate back to the sender.

### Step 4: Send a command via `MessageChannel`

Assuming the XML configuration has been loaded into an `ApplicationContext`:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.MessageChannel;

// context is the ApplicationContext that loaded jmx-integration.xml.
MessageChannel commands = context.getBean("cacheCommands", MessageChannel.class);

boolean accepted = commands.send(
    MessageBuilder.withPayload("pricing").build()
);

if (!accepted) {
    throw new IllegalStateException("Failed to send cache clear command");
}
```

In the example above, the adapter invokes the equivalent of:

```java
mbeanServer.invoke(
    new javax.management.ObjectName("demo.integration:type=Maintenance,name=Cache"),
    "clearCache",
    new Object[] { "pricing" },
    new String[] { "java.lang.String" }
);
```

This is an **explanatory equivalent model**, not code the application needs to call directly. If the operation succeeds, the demo prints `Cleared cache: pricing`. `send(...)` returning `true` indicates the channel accepted the message; it is **not** a business receipt confirming the cache was durably cleared in another system.

## 4. Using headers to select the MBean/operation

An outbound adapter can take target names from headers, for example when orchestrating multiple management commands. In that case, hardcoding `object-name` and `operation-name` is not required:

```xml
<int-jmx:operation-invoking-channel-adapter
    id="dynamicJmxAdapter"
    channel="jmxCommands"
    mbean-server="mbeanServer"/>
```

Send a message with both headers:

```java
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.integration.support.MessageBuilder;

var command = MessageBuilder.withPayload("catalog")
    .setHeader(JmxHeaders.OBJECT_NAME,
        "demo.integration:type=Maintenance,name=Cache")
    .setHeader(JmxHeaders.OPERATION_NAME, "clearCache")
    .build();

jmxCommands.send(command);
```

Here `jmxCommands` is a `MessageChannel` retrieved from the context, and `<int:channel id="jmxCommands"/>` must be declared before running. When a header is present, its value **takes precedence over** the corresponding default attribute. Specifying targets via headers suits a controlled internal orchestrator, but you must validate and check an **allowlist of permitted MBeans/operations** before routing messages into the adapter. Never pass user-supplied or external-event operation names straight to JMX.

## 5. Comparing the adapter with the outbound gateway and other JMX adapters

| Component | Direction and mechanism | Expected output | When to use |
| --- | --- | --- | --- |
| **Operation-invoking channel adapter** | Outbound, triggered on message arrival | Not designed for a reply flow | Sending management commands, typically `void` operations |
| **Operation-invoking outbound gateway** | Outbound request/reply | Return value wrapped in a reply message | Operation returns data needed by the next step |
| **Attribute-polling channel adapter** | Inbound, uses a poller | Message containing one JMX attribute value | Periodically reading status or metrics |
| **Notification-listening channel adapter** | Inbound, receives JMX notifications | Message built from the notification | Reacting when an MBean emits events |

For example, if you want to call `getQueueDepth()` and then decide whether to throttle processing, use an **operation-invoking outbound gateway** with a `reply-channel` instead of placing an outbound adapter in a flow expecting a response. An underlying operation might still return a value when invoked by the adapter, yet the adapter does not provide a request/reply contract for downstream steps.

## 6. Lifecycle, error handling, and safe operation

### Common errors

| Symptom | Common cause | Check / remediation |
| --- | --- | --- |
| MBean not found (`InstanceNotFoundException`) | Wrong `ObjectName`, MBean not exported yet, adapter points to wrong `MBeanServer` | Inspect MBean list in JConsole; compare exact domain, key properties, and server |
| Operation not found or signature mismatch (`ReflectionException` / invoke error) | Wrong `operation-name`, parameter order/types, MBean does not expose method | Check operation and signature in `MBeanInfo`; normalize payload before sending |
| Error inside operation (`MBeanException` or wrapped exception) | MBean failed executing the command | Log root cause; determine whether the command is safe to re-run |
| Startup error due to missing `mbeanServer` | No default-named server bean or wrong reference | Define bean with expected name or fix `mbean-server` attribute |
| Wrong target invoked despite XML defaults | Message contains `JmxHeaders.OBJECT_NAME`/`OPERATION_NAME` | Filter, strip, or govern headers at the flow boundary |
| Sender thread slows down | JMX operation takes too long on a `DirectChannel` | Measure operation latency; consider an async channel if appropriate with matching error handling |

### Deployment conventions

1. **Control target objects and invocation permissions:** maintain an allowlist of valid management commands and grant only minimal JMX permissions. For remote JMX, configure connection, authentication, and encryption appropriate for the environment. The outbound adapter does not provide authentication for arbitrary JMX servers by itself.
2. **Distinguish synchronous vs. asynchronous errors:** with `DirectChannel`, handler errors are generally thrown back to the sender; when using `ExecutorChannel` or async channels, design an `errorChannel` or dedicated error collection. Avoid interpreting `send()` completion as proof the operation succeeded when dispatching asynchronously.
3. **Be deliberate with retries:** timeouts, connection errors, or exceptions after an operation ran can leave the caller unsure whether execution occurred. Only auto-retry when the operation is idempotent or guarded against duplicate execution.
4. **Keep the flow observable:** log `ObjectName`, operation name, correlation ID, duration, and errors; strip passwords/tokens from payloads and logs. Track failure counts to detect unregistered MBeans or connection issues.
5. **Manage lifecycles:** ensure the MBean is registered on the configured `MBeanServer` before messages arrive; when managing MBeans in another JVM, configure an appropriate remote JMX connection. Shut down and close connections with bean lifecycle rather than opening a new JMX connection per message.

### Quick manual verification

1. Start the context with `CacheMaintenance`, `mbeanServer`, and the adapter; confirm no MBean registration errors occur.
2. Open JConsole/VisualVM connected to the JVM, locate `demo.integration:type=Maintenance,name=Cache`, and confirm `clearCache(java.lang.String)` exists.
3. Send payload `"pricing"` to `cacheCommands`; check logs show `Cleared cache: pricing`.
4. Send payload `"unknown"`; verify the error from the MBean is observed and the command is not marked successful.
5. Temporarily misconfigure `object-name` in a test environment; verify the MBean-not-found error is caught, then restore the configuration.

No poller is needed on `cacheCommands`: this is an event-driven command dispatch flow. If events arrive from HTTP, Kafka, JMS, or file adapters, simply transform them into messages with the appropriate payload and route them to this channel.

## 7. Self-check questions

1. Why is the operation-invoking **channel adapter** considered an outbound adapter even though it receives messages from an internal channel?
2. When `operation-name="clearCache"` is configured but a message carries header `JmxHeaders.OPERATION_NAME="refresh"`, which operation is selected?
3. For an operation with two parameters, when should you use a `List` payload vs. a `Map` payload?
4. When you need to use the return value of a JMX operation in subsequent processing, which component is more appropriate?
5. Why can retrying a management operation with side effects cause data errors, and how should this be handled?

## References

- [Spring Integration Reference — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): operation-invoking channel adapter, payload types, and outbound gateway.
- [Spring Integration API — OperationInvokingMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/jmx/OperationInvokingMessageHandler.html): resolving object/operation from message headers and defaults.
- [Spring Framework — Exporting Your Beans to JMX](https://docs.spring.io/spring-framework/docs/integration/jmx/exporting.html): `MBeanExporter` and MBean registration.
