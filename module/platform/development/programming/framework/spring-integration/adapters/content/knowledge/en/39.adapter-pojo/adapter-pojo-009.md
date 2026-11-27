# Expression adapter

In `SPRING_INTEGRATION_ADAPTERS`, inbound and outbound adapters handle exchanging data with external systems; `MessageChannel` connects endpoints inside the application. Between those steps, many tasks simply read a value, normalize a payload, check a condition, or pick a target channel. Spring Integration lets you configure these tasks using SpEL (Spring Expression Language) expressions instead of writing a dedicated POJO class for every small operation.

An **expression adapter** in the context of this lesson is an endpoint or message source configured to evaluate an expression. It is a declarative way to express integration behavior in a flow, not a new transport protocol. Expressions can read data from the message, headers, or invoke a registered Spring bean. This suits short, readable transformations and routing; complex business logic requiring state or independent unit testing still belongs in a dedicated POJO/service.

## 1. How is SpEL evaluated against a message?

A Spring message has two main parts:

- **Payload:** business data such as a string, DTO, `Map`, byte array, or object converted by an adapter.
- **Headers:** metadata such as ID, timestamp, correlation, content type, tenant, or transport information mapped by the adapter.

In Spring Integration expression endpoints, you can access the payload with `payload` and headers with `headers`. Examples:

| Expression | Meaning |
|---|---|
| `payload` | Retrieves the entire payload |
| `payload.orderId` | Reads the `orderId` property of the payload |
| `payload['status']` | Reads key `status` if the payload is a map |
| `headers['tenantId']` | Reads header `tenantId` |
| `headers['correlationId']` | Reads the correlation ID |
| `payload.amount > 1000` | Compares business values |
| `@orderService.find(payload.orderId)` | Invokes a method on the `orderService` bean |

Expressions are parsed and evaluated within the Spring Expression Language evaluation context provided by Spring Integration. That context grants access to the message, certain variables, and beans as configured by the application. Common SpEL syntax examples:

```text
payload.status == 'READY'
payload.amount >= 1000 and headers['trusted'] == true
headers['region'] ?: 'default'
payload.customer?.email
payload.type matches 'ORDER|RETURN'
```

The `?:` operator supplies a default value when the left-hand expression has no suitable value; `?.` performs safe navigation when an object may be `null`. You can use comparison, logical, and arithmetic operators, property access, map indexing, and method calls. Depending on the endpoint and evaluation context, expressions can also reference beans using `@beanName` syntax or Java types via `T(...)`.

Verify the exact payload type before writing expressions. `payload.orderId` only works when the payload actually has that property; if the payload is still an unparsed JSON string, this expression will not automatically turn the string into a DTO. Use a converter or transformer to produce the expected data type first, then access properties.

## 2. Roles of expression endpoints

An expression carries different semantics depending on which endpoint evaluates it:

| Endpoint | What is the expression result used for? | Example |
|---|---|---|
| Inbound channel adapter using expression | Produces payload for messages emitted on each poll | `@inventoryService.loadSnapshot()` |
| Transformer | Produces a new payload from the current message | `payload.trim().toUpperCase()` |
| Filter | Decides whether the message proceeds or is dropped | `payload.active == true` |
| Router | Selects destination based on expression outcome | `headers['region']` |
| Service activator | Calls a bean or evaluates processing logic and may emit a reply | `@orderService.process(payload)` |
| Header enricher | Creates or adds a header value | `'partner-api'` |

For a transformer, the expression result becomes the next payload. For a filter, the result must represent a boolean true/false condition. For a router, the result serves as a routing key to select a channel. For a service activator, the result can become a reply if the endpoint has an output channel. For a header enricher, the expression evaluates to the corresponding header value.

### Example: generating messages from an inbound expression

An internal data source can be read periodically using an inbound channel adapter. The expression calls a bean to fetch a snapshot, while the poller governs when it runs:

```xml
<int:inbound-channel-adapter id="inventorySnapshotSource"
        channel="inventorySnapshotChannel"
        expression="@inventoryService.loadSnapshot()">
    <int:poller fixed-delay="10000" />
</int:inbound-channel-adapter>
```

In this example, `inventoryService` is an application-registered bean. On each successful poll, the expression is evaluated to obtain the payload sent to `inventorySnapshotChannel`. If the method queries external data or has side effects, account for timeouts, failures, retries, and idempotency. The poller may invoke it again after a failure or on the next poll; an expression does not automatically guarantee once-only execution.

## 3. Transformer, filter, and router with SpEL

Suppose an inbound HTTP adapter received JSON and a converter turned the body into a DTO or map. The flow needs to normalize the order code, admit only valid messages, and route by region.

Endpoints can be declared in the XML namespace:

```xml
<int:channel id="rawOrders" />
<int:channel id="normalizedOrders" />
<int:channel id="acceptedOrders" />
<int:channel id="rejectedOrders" />
<int:channel id="northOrders" />
<int:channel id="southOrders" />

<int:transformer input-channel="rawOrders"
        output-channel="normalizedOrders"
        expression="payload.orderCode.trim().toUpperCase()" />

<int:filter input-channel="normalizedOrders"
        output-channel="acceptedOrders"
        discard-channel="rejectedOrders"
        expression="payload matches 'ORDER-[0-9]+'" />

<int:router input-channel="acceptedOrders"
        expression="headers['region']">
    <int:mapping value="north" channel="northOrders" />
    <int:mapping value="south" channel="southOrders" />
</int:router>
```

This illustrates expression endpoints chained together; in production applications, make sure the transformer returns the exact type expected by the filter and router. If you need to keep the entire DTO rather than only the `orderCode` string, use an expression or transformer that returns a new object containing the normalized field.

A filter has two outcomes that must be distinguished. When the expression evaluates to `false`, the message is excluded from the main flow and can be sent to `discard-channel`. When the expression throws an exception due to a wrong payload type, missing property, or failing method, that is a processing error; it follows the endpoint's error flow. Never treat an exception as a `false` filter outcome.

A router uses the expression result to look up a mapping. If the value matches no mapping, define the behavior explicitly: configure a default output channel, handle unknown routes, or raise an error when a route is mandatory. Never loop invalid messages back to the input channel for infinite retries.

### Same idea in Java DSL

Java DSL lets you write expressions directly on endpoints that provide overloads taking a SpEL string:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
IntegrationFlow orderValidationFlow() {
    return IntegrationFlow.from("rawOrders")
            .transform("payload.orderCode.trim().toUpperCase()")
            .filter("payload matches 'ORDER-[0-9]+'").channel("acceptedOrders")
            .get();
}
```

The snippet above focuses on expression syntax inside a flow. Across different Spring Integration dependency versions, verify the exact DSL overloads supported by your version; if an endpoint or overload does not accept an expression string, configure it via XML or use a lambda/POJO per that version's API.

## 4. Invoking beans and enriching headers

Expressions can invoke Spring beans when reusing an operation encapsulated in a service. For example, a service activator using an expression to delegate messages to a processing bean:

```xml
<int:service-activator input-channel="acceptedOrders"
        output-channel="processedOrders"
        expression="@orderService.process(payload, headers['tenantId'])" />
```

`orderService` must be a valid bean, and `process` must accept the actual payload type and tenant value. If the method returns an object, the result can become a reply sent to `processedOrders`. If the method returns `void` or produces no result, endpoint output behavior depends on channel and handler configuration; design request-reply contracts explicitly.

A header enricher uses expressions to add metadata to messages. Example:

```xml
<int:header-enricher input-channel="processedOrders"
        output-channel="outboundOrders">
    <int:header name="sourceSystem" expression="'order-service'" />
    <int:header name="tenantRegion" expression="headers['region'] ?: 'unknown'" />
</int:header-enricher>
```

Message headers are immutable metadata in Spring's message model; a header enricher creates the next message with headers added or updated per configuration. When a message leaves the application via HTTP, JMS, AMQP, Kafka, file, or SFTP adapters, do not assume every internal header is automatically transmitted to external systems. Inspect the header mapper and explicitly map fields belonging to the transport contract. When metadata is a mandatory part of an inter-system contract, consider placing it in the event envelope instead of relying solely on internal headers.

## 5. Using expressions in external adapter flows

Expression endpoints often sit between inbound and outbound adapters. For instance, a partner sends an HTTP webhook, the application normalizes the payload, determines the tenant, and routes to channels for an outbound Kafka adapter to publish events:

```text
HTTP inbound adapter
        |
        v
  rawPartnerEvents
        |
        v
  expression transformer
        |
        v
  expression filter
        |
        v
  expression router
        |
        +------> tenantAEvents ------> Kafka outbound adapter
        |
        +------> tenantBEvents ------> Kafka outbound adapter
```

Expressions can read metadata mapped by adapters, though header names and types depend on the transport. For example, HTTP may carry request headers; Kafka carries record keys, topics, and partition metadata; file/SFTP carries file names and paths; JMS/AMQP have protocol-specific message properties. Check the header mapper and adapter contract in use to know which fields actually exist. Do not guess headers solely from the protocol name.

Adapter-specific considerations:

- **HTTP:** use expressions to normalize payload fields or route based on mapped headers. Verify signatures, access permissions, and request structure before calling business services.
- **Kafka, JMS, and AMQP:** route by event type, tenant, or mapped headers. Preserve event IDs and correlation IDs per contract; expressions do not replace idempotency on broker redelivery.
- **File and SFTP:** classify messages using file name or directory metadata. Inspect the actual metadata fields produced by the adapter; never construct destination paths from untrusted data.
- **Database:** expressions can branch on fetched values or normalize data. Multi-step queries, transactions, and updates belong in repositories/services to control performance and consistency.

Expressions in specific adapter endpoints can also compute configuration attributes such as file names or remote directories. Supported attributes depend on the adapter type and Spring Integration version; check that specific adapter's expression attributes rather than assuming every outbound adapter shares an identical `expression` attribute.

## 6. Choosing between expressions and POJOs

Expressions shine when rules are short, declarative, and immediately clear at the endpoint—such as reading `headers['region']`, comparing `payload.status`, normalizing a string, or calling an existing service method. When expressions grow long, nest multiple conditions, require loops, perform multi-step data access, or have complex error branches, move the logic into a POJO/service.

| Use an expression when… | Use a POJO/service when… |
|---|---|
| Conditions or transformations are short and clear | Business rules span multiple steps or are hard to read on one line |
| Extracting a single payload/header field | Validating multiple fields and returning per-field errors |
| Choosing a channel from a single value | Coordinating multiple systems or ordered operations |
| Invoking an existing bean method | Needing transactions, state management, or custom retry handling |
| Keeping flow configuration concise | Needing detailed unit tests and logic reuse outside IntegrationFlow |

A good rule of thumb is keeping expressions declarative and predictable. Avoid invoking side-effecting methods inside transformers, filters, or routers. A router may be re-evaluated if a message is reprocessed; a filter may run multiple times under retries. If an expression calls a method that writes data or sends external requests, ensure the operation is idempotent with proper error handling.

## 7. Error handling and securing expressions

Expressions are evaluated while an endpoint processes a message. Common failures include `null` payloads, type mismatches, missing keys, bean method exceptions, unconvertible values, or routers failing to find a target. Treat them as observable, traceable integration failures.

- Validate payloads and message contracts before traversing deep properties in expressions.
- Use safe navigation `?.` and defaults when fields may be absent; do not use default values to mask missing required data.
- Distinguish messages intentionally dropped by a filter from exceptions thrown during expression evaluation.
- Configure error channels, bounded retries, and dead-letter/quarantine channels appropriately. Avoid routing failed messages back to the same endpoint without a stop condition.
- Record endpoint, message ID, correlation ID, and error category. Avoid logging full sensitive payloads.

Treat SpEL expressions as executable configuration inside the application. Never take raw expression text from an HTTP request, partner file, Kafka message, or user input and evaluate it directly. Depending on the evaluation context, SpEL can access beans, call methods, or reference Java types; untrusted expressions can expose unintended execution paths. Keep expressions inside developer-controlled configuration, restrict callable beans, and pass external data as payload/header values rather than concatenating them into expression code.

## 8. Testing and observability

When testing expression endpoints, cover both nominal values and boundary cases:

1. Properly typed payload with expected properties and headers: transformer returns the right payload; filter admits it; router picks the right channel.
2. Payload missing fields or containing `null` values: verify safe navigation/defaults work properly or contract validation rejects the message.
3. Wrong payload type: verify exceptions go to the error flow rather than being mistaken for a `false` filter result.
4. Header not forwarded by the transport mapper: verify the app follows the missing-metadata branch or reports a clear error.
5. Router receives an unmapped value: verify default routing or policy-defined failure.
6. Bean invoked by the expression throws an error: verify bounded retries, correlation IDs in logs, and final routing via the error channel.
7. Replaying the same message: verify business operations are protected by idempotency when retries or broker redeliveries occur.

You can use Spring Integration test support, `MockIntegration`, test channels, or mock adapters to verify flows without connecting to live external systems. For critical expressions, unit-test the expression against representative payloads/headers, then integration-test the full flow to confirm routing and error channels.

### Hands-on exercise

An HTTP inbound adapter receives messages from a partner. The deserialized payload has fields `orderCode`, `amount`, and `status`; the `tenantId` header may be absent. Build an expression-based flow to:

1. Normalize `orderCode` to uppercase with whitespace trimmed.
2. Admit only messages with `status == 'READY'` and `amount > 0`; route filtered-out messages to `rejectedOrders`.
3. Route messages by `headers['tenantId']`, with an explicit handling branch when tenant is omitted or unmapped.
4. Call `orderService` to persist the order after the message passes validation.
5. Test missing payload fields, missing headers, bean exceptions, and replayed messages.

**Completion criteria:** expressions read payload and headers accurately per contract; transformer, filter, and router behaviors remain clearly separated; evaluation errors enter the error flow; invalid messages have a terminal handling path; complex logic resides in POJOs/services; and no externally supplied expressions are ever evaluated.
