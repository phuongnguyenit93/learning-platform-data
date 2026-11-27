# Attribute expressions and type conversion with JMX adapters in Spring Integration

## 1. Problem: reading an attribute is not enough to process data correctly

**JMX (Java Management Extensions)** lets a Java application expose **managed attributes** on an MBean so management systems can read state such as pending message count, connection count, memory usage, or component health. Spring Integration provides the **JMX attribute-polling inbound channel adapter** to periodically read an attribute and build a `Message<?>` carrying that value. In the **`SPRING_INTEGRATION_ADAPTERS`** module, the result can be forwarded to `MessageChannel`s, filters, transformers, routers, or adapters connecting file, SFTP, HTTP, JMS, AMQP, Kafka, and databases.

The practical problem is that **JMX values do not always have the type, unit, and structure required by the next step**. For example, an MBean exposes pending message count as the string `"125"`, while the system's filter needs to compare against the numeric threshold `100`. If an expression evaluates `payload > 100` on a string, the result may be wrong or fail due to inconsistent type comparison. Some MBeans also return `CompositeData` or `TabularData` instead of simple Java beans.

This lesson focuses on **attribute expressions and type conversion**: distinguishing how JMX selects an attribute from how **SpEL** evaluates expressions on the payload, how to determine the actual JMX type, and how to normalize data before applying business rules.

```mermaid
flowchart LR
    A[MBean: PendingCountText = "125"] --> B[JMX attribute-polling adapter]
    B -->|String "125"| C[MessageChannel raw]
    C --> D[SpEL transformer: String to Long]
    D -->|Long 125| E[SpEL filter: >= 100]
    E -->|Meets threshold| F[Alert / HTTP / Kafka / JMS]
```

## 2. Three layers to distinguish: attribute name, expression, and type conversion

In an integration configuration, these three concepts are easily confused:

| Layer | Question answered | Example | When applied |
| --- | --- | --- | --- |
| **JMX attribute selection** | Which attribute on which MBean to read? | `object-name="demo.integration:type=Queue,name=Orders"`, `attribute-name="PendingCountText"` | When the poller accesses JMX |
| **Attribute value expression** | How to compute/decide using the read value? | SpEL `payload >= 100` on a numeric payload | When a transformer/filter/router processes the message |
| **Type conversion** | How to convert the value to the type and unit the flow expects? | String `"125"` to `Long 125` | Before computation, comparison, serialization, or forwarding |

In the JMX namespace documented by Spring Integration, `<int-jmx:attribute-polling-channel-adapter>` uses **`attribute-name`** (attribute name) and **`object-name`** (MBean name). Do not invent an XML attribute `attribute-expression` assuming it runs SpEL on each poll; use Spring Integration transformers/filters to evaluate expressions on the data after it is read.

Source configuration example:

```xml
<int-jmx:attribute-polling-channel-adapter
    id="ordersPendingSource"
    channel="rawPendingCount"
    mbean-server="mbeanServer"
    object-name="demo.integration:type=Queue,name=Orders"
    attribute-name="PendingCountText">
    <int:poller fixed-delay="5000" max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
```

Suppose the MBean returns the string `"125"`; the adapter creates a message with that `payload`. A separate normalization step:

```xml
<int:transformer
    input-channel="rawPendingCount"
    output-channel="numericPendingCount"
    expression="T(java.lang.Long).valueOf(payload.trim())"/>
```

Here `payload` is the payload of **the message received by the transformer**, `T(java.lang.Long)` is a Java type reference in SpEL, and `valueOf(...)` performs an explicit conversion. If JMX returns a `Long` or `Integer` from the start, you can omit string parsing and compare numbers directly.

## 3. Where does a JMX attribute's data type come from?

JMX publishes metadata for each attribute in `MBeanInfo` and `MBeanAttributeInfo`. A getter like `int getPendingCount()` on a Standard MBean creates attribute `PendingCount`, typically returning `Integer` when calling `MBeanServerConnection.getAttribute(...)`. With Spring JMX annotations, a getter annotated with `@ManagedAttribute` likewise exposes the corresponding attribute.

Never guess data types solely from the attribute name. Inspect both metadata **and the actual runtime value**:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

// server is a preconfigured MBeanServerConnection.
ObjectName name = new ObjectName(
    "demo.integration:type=Queue,name=Orders");

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf("%s : %s, readable=%s%n",
        attribute.getName(), attribute.getType(), attribute.isReadable());
}

Object value = server.getAttribute(name, "PendingCountText");
System.out.println(value == null ? "null" : value.getClass().getName());
```

| Declared attribute | Likely type returned by `getAttribute` | Recommended handling |
| --- | --- | --- |
| `int PendingCount` | `Integer` | Compare numerically directly or normalize to `long` |
| `long ProcessedTotal` | `Long` | Keep as 64-bit integer |
| `boolean Ready` | `Boolean` | Compare `payload == true` or handle `Boolean` directly |
| `String PendingCountText` | `String` | Parse explicitly to `Long`/`Integer` before comparing |
| `double LoadRatio` | `Double` | Verify range, special values, and unit before comparing |
| `CompositeData HeapMemoryUsage` | `CompositeData` | Extract fields and inspect `CompositeType` |
| `TabularData` from a management table | `TabularData` | Map rows/keys into an explicit DTO or collection |

MBeans from other JVMs may use **JMX Open Types**. For instance, `java.lang:type=Memory` exposes `HeapMemoryUsage` as `CompositeData` over JMX. Avoid casting directly to `Map<String,Object>` or a POJO without an appropriate converter.

## 4. Complete example: turning a string JMX value into a numeric alert

Let's build a metric source with two managed attributes: `PendingCount` (integer) and `PendingCountText` (string). The pipeline reads the string form to demonstrate type conversion:

**JMX → `rawPendingCount` → Transformer (String → Long) → Filter (`>= 100`) → Logging adapter**.

### 4.1. Dependency

With Maven and the Spring Integration BOM or Spring Boot managing versions:

```xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jmx</artifactId>
</dependency>
```

Without dependency management, declare a version compatible with your project's Spring Integration version. The example uses the Spring Framework JMX exporter and Spring Integration XML namespace.

### 4.2. MBean simulating pending message count

File `src/main/java/demo/jmx/OrdersQueueMetrics.java`:

```java
package demo.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(objectName = "demo.integration:type=Queue,name=Orders")
public class OrdersQueueMetrics {
    private final AtomicInteger pending = new AtomicInteger(125);

    @ManagedAttribute(description = "Number of pending messages")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedAttribute(description = "Number of pending messages formatted as string")
    public String getPendingCountText() {
        return Integer.toString(pending.get());
    }

    @ManagedAttribute(description = "Whether the queue is ready to accept messages")
    public boolean isReady() {
        return pending.get() < 500;
    }
}
```

These getters expose three attributes: `PendingCount`, `PendingCountText`, and `Ready`. The initial value `125` triggers a test alert on the very first poll. In a real application, getters should read live metrics from the corresponding queue/client; attribute names have no automatic link to Kafka topics or JMS destinations.

### 4.3. XML configuration for reading, conversion, and threshold checking

File `src/main/resources/jmx-attribute-expression.xml`:

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

    <context:mbean-server/>
    <context:mbean-export server="mbeanServer"/>
    <bean id="ordersQueueMetrics" class="demo.jmx.OrdersQueueMetrics"/>

    <int:channel id="rawPendingCount"/>
    <int:channel id="numericPendingCount"/>
    <int:channel id="criticalPendingCount"/>

    <!-- JMX value is a String, e.g. "125". -->
    <int-jmx:attribute-polling-channel-adapter
        id="ordersPendingSource"
        channel="rawPendingCount"
        mbean-server="mbeanServer"
        object-name="demo.integration:type=Queue,name=Orders"
        attribute-name="PendingCountText">
        <int:poller fixed-delay="5000" max-messages-per-poll="1"/>
    </int-jmx:attribute-polling-channel-adapter>

    <!-- Convert String to Long for numeric comparison. -->
    <int:transformer
        input-channel="rawPendingCount"
        output-channel="numericPendingCount"
        expression="T(java.lang.Long).valueOf(payload.trim())"/>

    <!-- Values less than 100 are filtered out of the alert branch. -->
    <int:filter
        input-channel="numericPendingCount"
        output-channel="criticalPendingCount"
        expression="payload >= 100"/>

    <int:logging-channel-adapter
        channel="criticalPendingCount"
        level="WARN"
        expression="'Orders queue pending: ' + payload"/>
</beans>
```

On each poll, the adapter reads `PendingCountText` and sends `"125"` to `rawPendingCount`. The transformer produces `Long 125`; the filter evaluates `125 >= 100` and therefore forwards the message to the logging adapter. If the source returns `"42"`, the filter rejects the message and no alert is logged under this configuration. `DirectChannel` (created by `<int:channel/>`) runs the transformer/filter/logging steps synchronously on the poller's processing thread.

To try it out, start the context:

```java
package demo.jmx;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class RunAttributeFlow {
    public static void main(String[] args) throws Exception {
        try (var context = new ClassPathXmlApplicationContext(
                "jmx-attribute-expression.xml")) {
            // Keep the demo app alive long enough for the poller to read the attribute.
            Thread.sleep(12_000L);
        }
    }
}
```

In a real server application, lifecycle is managed by Spring Boot or the container—never use `Thread.sleep(...)` as a business orchestration mechanism. Expected output is a WARN log `Orders queue pending: 125` per poll cycle (depending on logging configuration and scheduler timing).

### 4.4. When the attribute is already numeric: skip the parsing step

The MBean above also exposes `PendingCount` of type `int`. You can replace the pipeline by having the adapter read `attribute-name="PendingCount"` directly, returning `Integer`, and wiring it straight into the numeric filter:

```xml
<!-- This is an alternative configuration; do not declare alongside an adapter with the same id. -->
<int-jmx:attribute-polling-channel-adapter
    id="ordersPendingSource"
    channel="numericPendingCount"
    object-name="demo.integration:type=Queue,name=Orders"
    attribute-name="PendingCount">
    <int:poller fixed-delay="5000" max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
```

With this variant, **remove the transformer** reading from `rawPendingCount`, keeping the filter and logging adapter. Because `Integer` is numeric, SpEL can compare it directly against literal `100`. If downstream strictly requires `Long`, normalize explicitly with `payload.longValue()` in a transformer, rather than converting every number to a string and parsing it back.

## 5. Understanding the SpEL evaluation context in Spring Integration

SpEL is Spring's expression language used in transformers, filters, routers, and many other endpoints. Examples when the payload is a value read from JMX:

| Input payload | Expression on message-processing endpoint | Meaning and result |
| --- | --- | --- |
| `Integer 125` | `payload >= 100` | `true` |
| `Long 42` | `payload >= 100` | `false` |
| `String "125"` | `T(java.lang.Long).valueOf(payload.trim())` | Produces `Long 125` |
| `Boolean true` | `payload == true` | `true` |
| `String "WARM"` | `payload.equalsIgnoreCase('WARM')` | `true` |
| `CompositeData` containing key `used` | `payload.get('used')` | Returns the value of field `used`; validate its type |

### 5.1. `expression`, `${...}`, and `#{...}` serve different purposes

- `attribute-name="PendingCountText"` is the **JMX attribute name**, configured on the source.
- `attribute-name="${jmx.queue.attribute}"` is a **property placeholder**, resolved when creating the Spring context if corresponding properties are loaded. It helps pick a name per environment; it does not make the attribute dynamic per message.
- `object-name="#{@jmxTargetName}"` is an example of a **Spring bean expression** resolving configuration when creating the bean (assuming `jmxTargetName` is a suitable bean). Do not think of it as an expression re-evaluated against a payload on every poll.
- `expression="payload >= 100"` on `<int:filter>` is **per-message SpEL** evaluated after the adapter has read the JMX value.

For an inbound poller, there is no upstream request message yet at read time, so you cannot expect `headers.customerId` or `payload.queueName` to pick a JMX attribute the way an in-flight message processor does. If you need to read different attributes per request, build a request/reply flow or a `MessageSource` with an explicit target-selection contract instead of assuming `attribute-name` receives a request payload.

### 5.2. Configurable thresholds instead of hardcoding

A bean can supply control thresholds:

```java
package demo.jmx;

public class QueueThresholds {
    public long getCriticalPendingCount() {
        return 100L;
    }
}
```

With `<bean id="queueThresholds" class="demo.jmx.QueueThresholds"/>`, the filter can use:

```xml
<int:filter
    input-channel="numericPendingCount"
    output-channel="criticalPendingCount"
    expression="payload >= @queueThresholds.criticalPendingCount"/>
```

SpEL `@queueThresholds` accesses an allowed bean in the evaluation context, while `criticalPendingCount` reads the JavaBean property (`getCriticalPendingCount()`). For thresholds that change over time, consider caching, thread safety, and testing that updated values are read as designed. Never pass untrusted data into a SpEL expression with access to beans or Java classes.

## 6. Type conversion: from JMX to business payload

**Type conversion** should sit right at the boundary after the JMX source, before filters or routers execute. This is where types, units, and structures are normalized so downstream components never have to guess.

### 6.1. Explicit conversion with SpEL

```xml
<!-- String "125" -> Long 125 -->
<int:transformer input-channel="rawPendingCount"
                 output-channel="numericPendingCount"
                 expression="T(java.lang.Long).valueOf(payload.trim())"/>
```

When the returned value is already a `Number`, a transformer can use `payload.longValue()` to normalize `Integer` to `Long`. Watch for overflow, rounding, and precision loss when converting `Double` or `BigDecimal` to integer types.

### 6.2. Conversion using Spring's `ConversionService`

Across multiple JMX sources, centralize conversion rules in a reusable Java component:

```java
package demo.jmx;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public final class PendingCountNormalizer {
    private final ConversionService conversions = new DefaultConversionService();

    public Long normalize(Object raw) {
        if (raw == null) {
            throw new IllegalArgumentException("JMX PendingCount is null");
        }

        Long result = conversions.convert(raw, Long.class);
        if (result == null || result < 0) {
            throw new IllegalArgumentException(
                "Invalid pending count from JMX: " + raw);
        }
        return result;
    }
}
```

Wire it into a Spring Integration transformer:

```xml
<bean id="pendingCountNormalizer"
      class="demo.jmx.PendingCountNormalizer"/>

<int:transformer input-channel="rawPendingCount"
                 output-channel="numericPendingCount"
                 ref="pendingCountNormalizer"
                 method="normalize"/>
```

This is an **alternative configuration** to the SpEL transformer with the same `input-channel`/`output-channel`; do not declare both consuming from the same `DirectChannel`. `DefaultConversionService` supports common conversions such as `String` → `Long`; for DTOs, enums, or custom formats, register a custom `Converter` or write explicit parsing and validation logic.

**Important distinction:** `ConversionService` converts Java value types. It does not know whether a metric is *milliseconds* or *seconds*, does not determine timezones, and does not guarantee a reading makes business sense. When data has units, make the schema explicit—such as `latencyMillis`—and convert with `Duration.ofMillis(value)` in the normalization layer.

### 6.3. JMX Open Types: `CompositeData` and `TabularData`

For complex metrics, JMX can return `CompositeData` instead of `Map`. Example accessing JVM `HeapMemoryUsage`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName memory = new ObjectName("java.lang:type=Memory");
CompositeData usage = (CompositeData) server.getAttribute(
    memory, "HeapMemoryUsage");

long usedBytes = ((Number) usage.get("used")).longValue();
long maxBytes = ((Number) usage.get("max")).longValue();
System.out.println("Heap used bytes = " + usedBytes);
```

When reading `HeapMemoryUsage` via the JMX polling adapter, the payload is typically `CompositeData`; a transformer can extract the `used` field with `payload.get('used')`. Inspect metadata (`CompositeType`) and handle `max = -1`, which indicates an undefined maximum limit. Never divide by `maxBytes` when `maxBytes <= 0`, and never assume `CompositeData` always has identical keys across MBeans.

For the **tree-polling JMX adapter**, Spring Integration provides `MBeanObjectConverter` (such as `DefaultMBeanObjectConverter`) to convert an MBean tree structure into simpler data forms alongside an attribute filter. That converter mechanism serves **tree polling** and differs from an **attribute-polling adapter** reading a single attribute whose payload is then processed by a transformer.

### 6.4. Null, empty strings, and invalid data

Do not treat the following values as equivalent:

| JMX value | Correct interpretation | Suggested policy |
| --- | --- | --- |
| `0` | Valid measurement of zero | Keep and process normally |
| `"0"` | String representation of zero | Parse if contract allows |
| `""` or whitespace-only string | Missing numeric data | Mark invalid; alert or route to error flow |
| `null` | No attribute value | Polling source may emit no message; monitor successful poll count |
| `"N/A"` | Business sentinel marker | Define an explicit rule; never coerce to 0 |
| Out-of-range negative number | Invalid measurement or sentinel | Validate contract before raising an alert |

A SpEL transformer `Long.valueOf(...)` fails on `"N/A"` or `""`; parsing failures must be observed through poller/flow errors. If you want invalid readings emitted as structured messages, write a Java transformer returning a status DTO (for example `MetricReading(valid, value, reason)`) instead of silently substituting 0. For continuous telemetry, explicitly state whether to **keep the last-known value**, **alert on missing data**, or **halt processing**.

## 7. Common expression and conversion pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Adapter fails to start because attribute not found | Wrong `attribute-name`, wrong `ObjectName`, unregistered MBean, or wrong server | Check `MBeanInfo.getAttributes()`, exact names, and `mbeanServer` |
| `AttributeNotFoundException` | Getter not exposed or wrong capitalization | Remember `PendingCount` vs. `pendingCount`; for `getX()`, JMX name is usually `X` |
| SpEL fails calling `.trim()` | Payload is not a `String`, or is `null` | Inspect actual type via JMX; normalize with `instanceof`/converter |
| `NumberFormatException` | Invalid numeric string, thousands separators, or units attached | Sanitize and validate before parsing; enforce explicit format |
| Filter compares incorrectly | Comparing strings, or threshold has wrong type/unit | Convert to `Number` and normalize units before comparing |
| `ClassCastException` with Open Types | Casting `CompositeData` directly to `Map`/DTO | Extract via `CompositeData.get(key)` or write a dedicated converter |
| No message produced after a poll | Attribute is `null`, source failed, or value could not be read | Monitor poller logs/error channel/metrics; distinguish 0 from missing data |
| Poller falls behind or slows down | Slow remote JMX MBean call or slow transformer | Configure sensible polling cadence, connection timeouts, and error strategy |
| Numeric precision lost | Truncating `double`/`BigDecimal` to integer or wrong unit | Choose an appropriate type, preserve precision, and test boundary values |

### Notes on pollers and error handling

The JMX attribute-polling adapter is **inbound and poller-scheduled**. On each poll, it queries JMX and emits a message when a value is obtained. With `fixed-delay="5000"`, the pause is a **fixed delay** after the previous run finishes—not a promise that the metric is read strictly every 5 seconds. If processing or JMX connectivity takes time, the effective cycle lengthens.

With `DirectChannel`, transformers and filters typically execute synchronously on the poller thread. When conversion throws an exception, monitor poller errors and the error channel; never assume failed messages reached the destination. When switching to an async channel, design a dedicated error flow and retry policy so parse errors are not silently lost. JMX operations with side effects must manage retries differently from read-only attribute polling.

## 8. Hands-on exercise and verification checklist

### Practice

1. Start `RunAttributeFlow` and verify MBean `demo.integration:type=Queue,name=Orders` appears in JConsole/VisualVM with attribute `PendingCountText`.
2. Read directly with `MBeanServerConnection.getAttribute(...)` to confirm the value `"125"` and type `String` before it enters a message.
3. Observe the WARN log; verify the transformer produces `Long 125` and the filter `payload >= 100` lets it pass.
4. Change the demo's `pending` value to 42 and confirm the filter no longer forwards messages to the alert branch.
5. Change `attribute-name="PendingCountText"` to `PendingCount`, remove the string-parsing transformer, and filter directly on the integer.
6. Test an invalid string such as `"N/A"` on a test MBean; observe the parse error and design an appropriate handling path.
7. Read `java.lang:type=Memory`/`HeapMemoryUsage`, extract `used` and `max`, and test the `max <= 0` case.

### Self-check questions

1. Why is `attribute-name="PendingCountText"` fundamentally different from `expression="payload >= 100"`?
2. When is `${...}` resolved, and when is SpEL evaluated in a transformer?
3. If an MBean exposes `int getPendingCount()`, why is parsing the received value into a `Long` not always necessary?
4. Why shouldn't `"125"` be compared directly like an integer in a filter?
5. How does `CompositeData` differ from `Map`, and what is the safe way to retrieve the `used` field?
6. If a JMX attribute returns `null` or `"N/A"`, how should a monitoring system distinguish those states from `0`?
7. How does `DefaultMBeanObjectConverter` in tree polling differ from `ConversionService` used in a transformer?

## References

- [Spring Integration Reference — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): attribute-polling adapter, attribute/MBean names, poller, and tree-polling converters.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): transformers and SpEL expressions for payloads.
- [Spring Integration Reference — Filter](https://docs.spring.io/spring-integration/reference/filter.html): SpEL message-filtering conditions and handling rejected messages.
- [Spring Framework Reference — JMX Exporting](https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html): `@ManagedAttribute`, `MBeanExporter`, and exposed attributes.
- [Spring Framework Reference — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService` and custom converters.
- [Java SE API — `MBeanServerConnection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html): querying metadata and reading attributes.
- [Java SE API — `CompositeData`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html): representing complex attributes in JMX Open Types.
