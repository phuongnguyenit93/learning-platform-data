# HeaderMapper for Inbound Messages in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Explain why **`HeaderMapper`** is the conversion layer for **external protocol metadata → Spring `MessageHeaders`** when an inbound adapter/gateway receives a message; distinguish header mapping from payload conversion.
- Accurately recall the direction of the `HeaderMapper<T>` API: **`toHeaders(T source)` is the inbound direction**, while **`fromHeaders(MessageHeaders headers, T target)` is the outbound/response direction**. The method names are easily confused if you only read “from/to” from the external system's perspective.
- Identify header categories: Spring core `id`, `timestamp`; application correlation/tracing/idempotency; HTTP/JMS/AMQP/Kafka/FTP/SFTP/IP protocol headers; and information that exists only at the transport level.
- Configure and test `DefaultHttpHeaderMapper.inboundMapper()` for an HTTP inbound gateway, selecting headers with `setInboundHeaderNames(...)` or the DSL `mappedRequestHeaders(...)`.
- Use `DefaultJmsHeaderMapper` with a JMS message-driven inbound adapter to read JMS API headers and properties, and understand the difference between `jms_correlationId` and Spring `correlationId`.
- Understand `DefaultAmqpHeaderMapper`, `AmqpHeaders`, and request-header-name patterns when receiving RabbitMQ/AMQP messages; avoid unbounded wildcard mapping or leaking broker-internal `x-*` headers.
- Distinguish Spring Kafka's `KafkaHeaderMapper`/`DefaultKafkaHeaderMapper`/`SimpleKafkaHeaderMapper`, which belong to **Spring for Apache Kafka**, and are not by default `org.springframework.integration.mapping.HeaderMapper<T>`.
- Know when File/SFTP/FTP/TCP/UDP adapters provide headers **internally** without needing a generic HeaderMapper to configure.
- Design policies for **allowlisting, validation, tenant authorization, correlation/idempotency keys, type conversion, and filtering sensitive headers** at ingress.
- Write mapper unit tests, test HTTP/JMS/AMQP flows against real adapters, recognize header loss/type change/duplicate-read scenarios, and check error handling and connection lifecycles.

This lesson belongs to the **Message Headers** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on connecting external systems to Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`. In those file, SFTP, HTTP, JMS, AMQP, Kafka, TCP/UDP, or database flows, **headers form the technical contract between the protocol boundary and the business flow**: they route messages, provide correlation, support tracing, and pass metadata; however, they do not by themselves guarantee authenticity, ACK, or exactly-once delivery.

> Scope: examples primarily follow Java 17+, Spring Boot 3.x, Spring Integration 6.x, and Spring Framework 6.x. With Spring Integration 7.x, some packages, DSL factories, Jakarta JMS versions, Spring Kafka, and default configurations may differ. **Always verify the Javadoc against your project's specific BOM.**

## 1. How Does an HTTP Request Become a Spring Message?

Suppose a partner system calls:

~~~http
POST /ingest/orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-Trace-Id: trace-6a1
X-Partner-Event-Id: event-101
X-Tenant-Id: tenant-a
Authorization: Bearer <TOKEN>

{"orderId":"order-1001","amount":125.00}
~~~

The Spring Integration HTTP inbound gateway creates a Spring `Message<?>` for the processing flow. The **payload** comes from the body and `HttpMessageConverter`; **headers** are extracted from the HTTP request or added by the gateway/platform itself.

~~~mermaid
flowchart LR
  H["HTTP request<br/>body + headers"] --> G["Http.inboundGateway"]
  G --> MC["HTTP MessageConverter<br/>body → payload"]
  G --> HM["DefaultHttpHeaderMapper<br/>HttpHeaders → MessageHeaders"]
  MC --> M["Spring Message<?>"]
  HM --> M
  M --> C["MessageChannel"]
  C --> S["Validate / route / transform / handle"]
~~~

Logical representation of the internal message:

~~~text
Spring Message
  payload = {"orderId":"order-1001","amount":125.00}
  headers = {
    id: <generated UUID>,
    timestamp: <generated epoch millis>,
    contentType: "application/json"  (depending on mapper/codec),
    X-Trace-Id: "trace-6a1"          (if mapped),
    X-Partner-Event-Id: "event-101" (if mapped)
  }
~~~

**Note on the example:** the actual key casing/value type of an HTTP header can be `String`, `List<String>`, `MediaType`, or a form converted by the mapper, depending on the adapter/mapper/config. Do not code assuming a single type just because you see text headers in the request; verify the actual `Message` with tests.

### 1.1. Security Question Right at Ingress

The HTTP header `X-Tenant-Id: tenant-a` **is sent by the client, not yet an authenticated tenant**. If the business handler uses it to choose a MongoDB collection, Kafka topic, or access permissions, a partner could change the header to access another tenant.

Separate:

- **External input:** request headers that are mapped, but treated as *untrusted data*.
- **Trusted context:** principal/JWT claims verified by the security filter, and tenant authorization computed by the server.
- **Internal application headers:** `trustedTenantId`/`businessEventId`/`traceId` created by the ingress validator/enricher, which the client cannot override.

## 2. HeaderMapper<T> — Contract and Correct Mapping Direction

Interface:

~~~java
package org.springframework.integration.mapping;

public interface HeaderMapper<T> {
    void fromHeaders(
            org.springframework.messaging.MessageHeaders headers,
            T target);

    java.util.Map<String, Object> toHeaders(T source);
}
~~~

The generic type `T` is the **external system**'s object type: for example, `HttpHeaders`, `jakarta.jms.Message`, or `MessageProperties` depending on the implementation.

| Method | Data Source | Target | In Inbound |
|---|---|---|---|
| **`toHeaders(T source)`** | Headers/properties of the **external** message | `Map<String,Object>` to create Spring `MessageHeaders` | **Yes, the core method** |
| **`fromHeaders(MessageHeaders headers, T target)`** | Spring `MessageHeaders` | Mutable external headers/properties | Used for **outbound** or when an **inbound gateway sends a reply** |
| `MessageConverter` | Body/bytes/JSON/XML/JMS payload | Spring Message payload or external body | A **different mechanism** from header mapping |
| Header enricher | Spring Message already in the flow | Spring Message with added/modified headers | **After** crossing the inbound boundary |
| Header filter | Spring Message already in the flow | Spring Message with certain headers removed | **After** mapping; useful for the trust boundary |

**Rule of thumb:** `toHeaders(source)` means “convert *from the external object to Spring Message headers*”, not “send headers out externally”.

### 2.1. Standalone API Example

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;
import java.util.Map;

HttpHeaders httpHeaders = new HttpHeaders();
httpHeaders.add("X-Trace-Id", "trace-6a1");
httpHeaders.set("Content-Type", "application/json");

DefaultHttpHeaderMapper mapper =
        DefaultHttpHeaderMapper.inboundMapper();
mapper.setInboundHeaderNames(
        "Content-Type", "X-Trace-Id");

Map<String, Object> inboundHeaders =
        mapper.toHeaders(httpHeaders);
~~~

Then the framework can use the entries in the map to build a `Message<?>` (with core headers generated/controlled separately). The returned value types depend on the implementation; tests should check **names and semantics**, without blindly forcing everything to `String`.

### 2.2. HeaderMapper<T> Is Not Spring MessageConverter

HTTP example:

~~~text
Content-Type: application/json
X-Trace-Id: trace-6a1

{"orderId":"o-1"}
~~~

- `HttpMessageConverter` converts the JSON body into `String`, `byte[]`, or a Java DTO, depending on `requestPayloadType`/converters.
- `HeaderMapper<HttpHeaders>` reads `Content-Type` and `X-Trace-Id` for Spring `MessageHeaders`.
- A custom `HeaderMapper` does **not** deserialize JSON on its own.
- A custom `MessageConverter` does **not** guarantee custom protocol headers are preserved.

Successful payload conversion does not prove the header mapper captured the metadata properly, and vice versa.

## 3. Headers in a Spring Message: Names, Types, and Ownership

Spring Message structure:

~~~java
org.springframework.messaging.Message<T>
org.springframework.messaging.MessageHeaders
~~~

Reading headers:

~~~java
Message<?> message = ...;

Object raw = message.getHeaders().get("X-Trace-Id");
String trace = message.getHeaders().get(
        "appTraceId", String.class);
~~~

### 3.1. Core Headers and Application Headers

| Group | Examples | Notes |
|---|---|---|
| **Spring core** | `MessageHeaders.ID`, `MessageHeaders.TIMESTAMP` | Generated/managed by the framework; do not treat as the external system's origin ID |
| **Correlation/reply flow** | `correlationId`, `replyChannel`, `errorChannel` | Meaningful to gateways/aggregators/error flows; do not let external callers control them arbitrarily |
| **HTTP metadata** | Content-Type, Accept, X-Trace-Id | Case-insensitive names in HTTP, but a Java Map is not case-insensitive by default |
| **JMS metadata** | `jms_messageId`, `jms_correlationId`, `jms_redelivered` | Broker ID/correlation differs from Spring Message ID |
| **AMQP metadata** | `amqp_receivedRoutingKey`, `amqp_receivedExchange`, `amqp_redelivered` | Delivery/routing properties from the broker |
| **Kafka metadata** | received topic/partition/offset/key | Created by converter/header mapper per Spring Kafka; types differ from HTTP |
| **File/SFTP** | file name, remote directory, original file | Generated by the adapter; does not necessarily go through a generic HeaderMapper |
| **IP/TCP/UDP** | source IP/port, connection id | Network metadata set by the IP adapter |
| **Business application** | `businessEventId`, `trustedTenantId` | Should be derived from validated identity/payload |

**`MessageHeaders.ID` is not equal to an HTTP request ID, `JMSMessageID`, Kafka record key, or business event ID.** Redelivery can create a new Spring Message with a different UUID. For idempotency/dedup, choose a stable business ID with a clear tenant/source scope.

### 3.2. Immutability and Adding Headers After Mapping

`MessageHeaders` is a managed header map under a contract of not mutating it directly from a business handler. Add/modify headers using `MessageBuilder` or the EIP `HeaderEnricher`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> normalized =
    MessageBuilder.withPayload("accepted")
        .setHeader("appTraceId", "trace-6a1")
        .setHeader("businessEventId", "event-101")
        .build();
~~~

When building a message based on an existing one:

~~~java
Message<?> sanitized =
    MessageBuilder.fromMessage(message)
        .removeHeader("Authorization")
        .removeHeader("X-Untrusted-Role")
        .setHeader("trustedTenantId", authenticatedTenantId)
        .build();
~~~

**`authenticatedTenantId` must come from an authenticated security context/server identity**, not simply copying `X-Tenant-Id` from the client. This is a fragment with `message`/`authenticatedTenantId` supplied by the caller.

### 3.3. Header Types, Nulls, and Conversion

- An HTTP header can have **multiple values**. Do not flatten `List<String>` into a comma-joined `String` when the header's semantics do not allow it.
- JMS properties restrict values to JMS-supported primitive/wrapper/`String` types; do not naively convert arbitrary Java objects into JMS properties.
- Kafka record headers have **`byte[]`** values at the wire level; Spring Kafka mapper deserialization can produce `String`/JSON types depending on policy.
- AMQP `MessageProperties` has typed fields and a custom headers map.
- Spring `@Header` injection can apply conversion; a conversion failure is a **validation/mapping error**, not simply a “header does not exist” message.
- A missing header is different from a header with an empty value, malformed value, or conflicting multiple values.

## 4. At Which Step of the Inbound Flow Does Header Mapping Occur?

Common endpoints:

~~~mermaid
sequenceDiagram
    participant E as External system
    participant A as Inbound adapter/gateway
    participant HM as HeaderMapper
    participant MC as MessageConverter
    participant C as MessageChannel
    participant H as Business handler
    E->>A: Request / broker message
    A->>HM: toHeaders(external headers)
    HM-->>A: Map<String,Object>
    A->>MC: convert body/payload
    MC-->>A: Java payload
    A->>C: Spring Message(payload, mapped headers)
    C->>H: deliver message
    H-->>C: result / reply if gateway
~~~

**Do not assume the exact internal order across every adapter**: the converter and mapper may be invoked in an implementation-specific sequence. What is guaranteed is that both contribute to building the Spring `Message` **before downstream handlers process it**.

### 4.1. Inbound Channel Adapter vs. Inbound Gateway

| Endpoint | Input | Output | Consequence for Header Mapper |
|---|---|---|---|
| **Inbound channel adapter** | HTTP/JMS/AMQP/SFTP/UDP... | One-way Spring Message | Primarily uses `toHeaders(...)` when the endpoint has a HeaderMapper |
| **Inbound gateway** | HTTP/JMS/AMQP request | Spring Message + reply | `toHeaders(...)` for the request **and** `fromHeaders(...)` for reply headers |
| **Outbound adapter** | Spring Message | External write/send | Primarily `fromHeaders(...)` |
| **Outbound gateway** | Spring Message request | External request/reply | `fromHeaders(...)` for outgoing request, `toHeaders(...)` for incoming response |

**Direction depends on the endpoint and the object being mapped.** For an HTTP inbound gateway, `DefaultHttpHeaderMapper.inboundMapper()` is configured for *inbound request and outbound response*; avoid confusing it with `outboundMapper()`, which is used for an HTTP outbound gateway/adapter.

### 4.2. A Mapper Does Not Automatically Add Security Headers

Copying HTTP `Authorization` into a Spring Message does not mean Spring Security has verified the bearer token. Copying `X-Forwarded-For` also does not prove it is the real client IP when the proxy chain is untrusted.

A HeaderMapper only **selects/transfers metadata**. Authorization, signature verification, tenant isolation, input validation, and rate limiting must have their own mechanisms.

## 5. DefaultHttpHeaderMapper: Inbound HTTP Requests

Implementation:

~~~java
org.springframework.integration.http.support.DefaultHttpHeaderMapper
~~~

It implements:

~~~java
org.springframework.integration.mapping.HeaderMapper<
    org.springframework.http.HttpHeaders>
~~~

Confirmed factories:

~~~java
DefaultHttpHeaderMapper.inboundMapper();
DefaultHttpHeaderMapper.outboundMapper();
~~~

For an **HTTP inbound gateway**, use **`inboundMapper()`** and then specify which request headers are allowed to be mapped.

### 5.1. HTTP Allowlist Mapper Bean

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
public class InboundHttpHeaderConfiguration {

    @Bean("inboundHttpHeaderMapper")
    public DefaultHttpHeaderMapper inboundHttpHeaderMapper() {

        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.inboundMapper();

        mapper.setInboundHeaderNames(
            "Content-Type",
            "Accept",
            "X-Trace-Id",
            "X-Partner-Event-Id");

        return mapper;
    }
}
~~~

- `setInboundHeaderNames(...)` configures which header names/patterns **are mapped from the HTTP request**.
- Configuring an explicit list **changes the default mapping scope**: do not assume other standard headers will still be present automatically.
- `Content-Type`/`Accept` are often needed for the application contract; in some flows, the payload converter may read `Content-Type` directly from the request before/outside the header map.
- `X-Trace-Id` is only an **external trace hint**; you must validate its format/length and distinguish it from the internal trace/span ID.
- `Authorization` is intentionally excluded from `MessageHeaders`; authentication should happen earlier at the security layer.
- `X-Tenant-Id` is intentionally not copied into trusted headers because the tenant must be derived from the authenticated principal.

### 5.2. HTTP HeaderMapper Has Potentially Confusing Inbound/Outbound Method Names

| DefaultHttpHeaderMapper API | Direction in an HTTP Inbound Gateway |
|---|---|
| `inboundMapper()` | Correct factory for an inbound endpoint |
| `setInboundHeaderNames(...)` | List of HTTP **request** headers accepted into the Spring Message |
| `setOutboundHeaderNames(...)` | List of Spring reply headers sent **out in the HTTP response** |
| `toHeaders(HttpHeaders request)` | HTTP request → Spring Message headers |
| `fromHeaders(MessageHeaders reply, HttpHeaders response)` | Spring reply headers → HTTP response |
| `HTTP_REQUEST_HEADERS` | Pattern token for standard HTTP request headers |
| `HTTP_RESPONSE_HEADERS` | Pattern token for standard HTTP response headers |

**Do not use `setOutboundHeaderNames` to control input headers of an HTTP request.** It is for the reverse direction.

### 5.3. Standalone HTTP Mapper Test

~~~java
package example.headers;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

import static org.junit.jupiter.api.Assertions.*;

class InboundHttpHeaderMapperTest {

    @Test
    void mapsOnlySelectedHeaders() {
        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.inboundMapper();

        mapper.setInboundHeaderNames(
                "X-Trace-Id", "X-Partner-Event-Id");

        HttpHeaders incoming = new HttpHeaders();
        incoming.add("X-Trace-Id", "trace-a7");
        incoming.add("X-Partner-Event-Id", "event-101");
        incoming.add("X-Untrusted-Role", "admin");

        Map<String, Object> mapped =
                mapper.toHeaders(incoming);

        assertTrue(mapped.keySet().stream()
            .anyMatch(s -> s.equalsIgnoreCase("X-Trace-Id")));

        assertTrue(mapped.keySet().stream()
            .anyMatch(s -> s.equalsIgnoreCase(
                    "X-Partner-Event-Id")));

        assertFalse(mapped.keySet().stream()
            .anyMatch(s -> s.equalsIgnoreCase(
                    "X-Untrusted-Role")));
    }
}
~~~

The test checks with `equalsIgnoreCase` because HTTP header names are case-insensitive at the protocol level, whereas a Java `Map` may store a specific name/casing depending on the implementation. This test does not assert that the value is always a `String`; if the business logic requires a validated `String`, normalize it after mapping.

### 5.4. If You Want to Keep Standard Headers Too

In mapping pattern configuration, documented shortcuts include:

~~~text
HTTP_REQUEST_HEADERS
HTTP_RESPONSE_HEADERS
~~~

For example, if you want to keep standard request headers plus custom keys:

~~~java
mapper.setInboundHeaderNames(
        "HTTP_REQUEST_HEADERS",
        "X-Trace-Id",
        "X-Partner-Event-Id");
~~~

Note: including all standard headers may bring in sensitive or unnecessary metadata; for public APIs, **a narrow allowlist is usually easier to govern**. Do not use wildcard `*` just to save a few lines of configuration.

## 6. HTTP Inbound Gateway: Java DSL Wiring

The Spring Integration HTTP module provides the Java DSL `Http.inboundGateway(...)` and `HttpInboundEndpointSupportSpec.headerMapper(...)`.

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
@EnableIntegration
public class HttpOrdersInboundFlow {

    @Bean
    public IntegrationFlow ordersHttpFlow(
            DefaultHttpHeaderMapper inboundHttpHeaderMapper) {

        return IntegrationFlow.from(
                Http.inboundGateway("/ingest/orders")
                    .requestMapping(m ->
                        m.methods(HttpMethod.POST))
                    .requestPayloadType(String.class)
                    .headerMapper(inboundHttpHeaderMapper))
            .handle(String.class, (payload, headers) -> {
                // Demo: only responds with the payload length.
                // Production needs validation, persistence/explicit ACK.
                return "accepted bytes/chars=" + payload.length();
            })
            .get();
    }
}
~~~

To run this:

- Include `spring-integration-http` and the corresponding web stack; the application runs with the appropriate Spring Boot web starter.
- The HTTP endpoint path/method must not conflict with another route.
- The HTTP request payload is `String` in this example; production should parse the schema/JSON and validate size/type.
- The `HeaderMapper` bean must be a mapper configured for the **HTTP inbound** direction.
- The gateway will receive a Spring Message from HTTP and return an HTTP response from the reply handler. Since there is no business persistence yet, the “accepted” response only proves the demo handler ran.
- Auto-generated HTTP framework headers outside the mapper can also exist; do not assert that every header in the `Message` consists solely of entries from `mapper.toHeaders()`.

### 6.1. Testing with curl

~~~bash
curl -i -X POST http://localhost:8080/ingest/orders \
  -H 'Content-Type: application/json' \
  -H 'X-Trace-Id: trace-a7' \
  -H 'X-Partner-Event-Id: event-101' \
  -H 'X-Untrusted-Role: admin' \
  -d '{"orderId":"order-1001","amount":125.00}'
~~~

The demo handler returns a `String`; in integration tests, you should **inspect the actual headers** at the handler, not just status 200. The `X-Untrusted-Role` header must not appear due to an overly permissive mapper.

### 6.2. XML Wiring (Alternative)

~~~xml
<!-- Requires XML namespaces int, int-http, and the channels declared.
     inboundHttpHeaderMapper is a registered bean. -->
<int-http:inbound-gateway
        id="ordersGateway"
        path="/ingest/orders"
        request-channel="ordersInput"
        header-mapper="inboundHttpHeaderMapper"
        request-payload-type="java.lang.String"/>
~~~

This is an **alternative configuration to Java DSL**; do not register both on the same HTTP path simultaneously. In XML, you can use `mapped-request-headers` to declare patterns instead of injecting a custom mapper, but **do not combine both configuration styles when the schema/endpoint forbids it**.

### 6.3. DSL mappedRequestHeaders or headerMapper

If you only need simple patterns, you can configure them directly on the spec:

~~~java
Http.inboundGateway("/ingest/orders")
    .mappedRequestHeaders(
        "Content-Type",
        "X-Trace-Id",
        "X-Partner-Event-Id");
~~~

This is a **builder fragment** — chain it into `IntegrationFlow.from(...)`. For custom logic, use `.headerMapper(inboundHttpHeaderMapper)` instead of trying to configure both mapped headers and a separate mapper on the same endpoint; check the API version for precedence.

## 7. Writing a Custom HeaderMapper When Special Policy Is Needed

When `DefaultHttpHeaderMapper` is not enough to normalize an external header, you can implement `HeaderMapper<HttpHeaders>`. The goal is to **map a validated trace ID** rather than copying everything from the client.

~~~java
package example.headers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.integration.mapping.HeaderMapper;
import org.springframework.messaging.MessageHeaders;

public final class SafeTraceHttpHeaderMapper
        implements HeaderMapper<HttpHeaders> {

    private static final String EXTERNAL =
            "X-External-Trace-Id";
    private static final String INTERNAL =
            "externalTraceId";

    @Override
    public Map<String, Object> toHeaders(HttpHeaders source) {
        Map<String, Object> mapped = new HashMap<>();
        String value = source.getFirst(EXTERNAL);

        if (isAllowed(value)) {
            mapped.put(INTERNAL, value);
        }
        return mapped;
    }

    @Override
    public void fromHeaders(
            MessageHeaders headers,
            HttpHeaders target) {
        Object value = headers.get(INTERNAL);

        if (value instanceof String trace
                && isAllowed(trace)) {
            target.set(EXTERNAL, trace);
        }
    }

    private static boolean isAllowed(String value) {
        return value != null
            && value.matches("[A-Za-z0-9_-]{1,64}");
    }
}
~~~

**Limitations of this custom mapper:**

- It only maps one trace field; **it does not handle standard HTTP headers like Content-Type**. If attached to an inbound gateway that uses reply content negotiation, test the entire HTTP contract or delegate allowed standard headers to `DefaultHttpHeaderMapper`.
- `fromHeaders(...)` currently writes the trace back to the HTTP response; in production you may omit this outbound part if you do not want to echo external input back to the caller.
- Regex validation is not trace authentication: a client can still send any syntactically valid trace text. Maintain a separate server-generated trace ID.
- Never return `null` instead of an empty map.
- Do not accept role/admin/tenant headers as trusted authorization merely because they match a regex.
- If a header has multiple values, `getFirst` takes only one; production should define a policy to **reject multiple values** for security-sensitive singleton headers.

### 7.1. Testing the Custom Mapper

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.MessageHeaders;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SafeTraceHttpHeaderMapperTest {

    private final SafeTraceHttpHeaderMapper mapper =
            new SafeTraceHttpHeaderMapper();

    @Test
    void acceptsValidTraceOnly() {
        HttpHeaders in = new HttpHeaders();
        in.add("X-External-Trace-Id", "trace_001");
        assertEquals("trace_001",
            mapper.toHeaders(in).get("externalTraceId"));
    }

    @Test
    void rejectsInvalidTrace() {
        HttpHeaders in = new HttpHeaders();
        in.add("X-External-Trace-Id", "../../admin");
        assertFalse(
            mapper.toHeaders(in).containsKey("externalTraceId"));
    }

    @Test
    void mapsSafeTraceToResponseWhenRequested() {
        HttpHeaders response = new HttpHeaders();
        MessageHeaders internal = new MessageHeaders(
                Map.of("externalTraceId", "trace_001"));

        mapper.fromHeaders(internal, response);

        assertEquals("trace_001",
            response.getFirst("X-External-Trace-Id"));
    }
}
~~~

This is a unit test of the mapping logic; it does not start an HTTP server or a Spring Integration endpoint. Add an integration test with the gateway to verify the mapper is actually injected and headers cross the request/response boundary per contract.
## 8. JMS Inbound: DefaultJmsHeaderMapper

JMS has its own API headers and properties. In Spring Boot 3.x, JMS types belong to `jakarta.jms`; the Spring Integration mapper is in package:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.JmsHeaderMapper;
import org.springframework.integration.jms.JmsHeaders;
~~~

`DefaultJmsHeaderMapper` transfers JMS API headers and custom JMS properties into Spring `MessageHeaders`. Mapping does **not** transform the JMS body: the body is handled by `MessageConverter`, which by default typically converts `TextMessage` to `String` and `BytesMessage` to `byte[]`.

### 8.1. JMS Headers to Understand

| JMS API Header/Property | Typical Spring Header | Meaning |
|---|---|---|
| `JMSMessageID` | `jms_messageId` | ID assigned by the JMS provider; not Spring `MessageHeaders.ID` |
| `JMSCorrelationID` | `jms_correlationId` | JMS request/reply correlation |
| `JMSReplyTo` | `jms_replyTo` | JMS reply destination |
| `JMSRedelivered` | `jms_redelivered` | Message may have been redelivered |
| `JMSDestination` | `jms_destination` | Destination used by the provider |
| `JMSPriority` | `priority` when inbound mapping is enabled on the mapper | Transport QoS |
| `JMSDeliveryMode` | `jms_deliveryMode` when option is enabled | Delivery mode |
| `JMSExpiration` | `jms_expiration` when option is enabled | Expiration timestamp |
| Custom `businessEventId` property | `businessEventId` if type/name is supported | Business ID from the producer |

Exact names, types, and mapping permissions should be checked against `JmsHeaders` for your version. `jms_correlationId` reflects **`JMSCorrelationID`**, which differs from Spring `correlationId` used in aggregators/resequencers; do not interchange them arbitrarily.

### 8.2. Registering DefaultJmsHeaderMapper

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;

@Configuration
public class InboundJmsHeaderConfig {

    @Bean("inboundJmsHeaderMapper")
    public DefaultJmsHeaderMapper inboundJmsHeaderMapper() {
        DefaultJmsHeaderMapper mapper =
                new DefaultJmsHeaderMapper();

        mapper.setMapInboundPriority(true);
        mapper.setMapInboundDeliveryMode(true);
        mapper.setMapInboundExpiration(true);
        return mapper;
    }
}
~~~

The priority/delivery mode/expiration options provide **metadata from inbound JMS** per the mapper's contract. Modifying those Spring headers on an in-flight JMS message does not change its QoS.

### 8.3. JMS Message-Driven Inbound Adapter

~~~java
package example.headers;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class JmsOrdersInboundFlow {

    @Bean
    public IntegrationFlow jmsOrdersInbound(
            ConnectionFactory jmsConnectionFactory,
            DefaultJmsHeaderMapper inboundJmsHeaderMapper) {

        return IntegrationFlow.from(
                Jms.messageDrivenChannelAdapter(
                        jmsConnectionFactory)
                    .destination("orders.in")
                    .headerMapper(inboundJmsHeaderMapper))
            .channel("ordersFromJms")
            .get();
    }
}
~~~

Requires `spring-integration-jms`, a real broker/destination, security/connection configuration, and a consumer receiving messages from `ordersFromJms`. A **message-driven adapter** receives callbacks from a JMS listener container; it is **not** a polling `Jms.inboundAdapter(...)` source requiring a poller.

### 8.4. JMS Redelivery, Correlation, and Error Channel

- `JMSMessageID` is a transport ID, not automatically a business idempotency key.
- `JMSCorrelationID` serves JMS request/reply; the business event ID should be a separate property bound to validated content.
- `JMSRedelivered=true` indicates the provider redelivered the message; it does **not** prove whether a previous side effect committed or not.
- When the mapper/converter fails, the transaction/error-channel policy decides whether the broker rolls back/redelivers or ACKs; **the mapper does not control session ACK**.
- If the error channel simply logs and returns, a transacted JMS container may commit the message depending on wiring; for data that must not be lost, there must be a durable DLQ or proper exception propagation per contract.
- JMS custom properties do not accept arbitrary Java objects; convert values to JMS-supported types before sending outbound.

### 8.5. What Should a JMS End-to-End Test Verify?

1. Producer sends a `TextMessage` with `JMSCorrelationID` and a custom `String` property `businessEventId`.
2. JMS inbound adapter receives it and the mapper produces the expected Spring headers.
3. Assert `jms_correlationId` exists and is not conflated with the Spring Message ID.
4. Assert `businessEventId` reaches the business handler with the right type.
5. Test JMS redelivery/rollback and verify `jms_redelivered` is only observational metadata.
6. Test conversion failure going to the error channel and verify transaction rollback/DLQ per policy, not just asserting that an exception was logged.

## 9. AMQP Inbound: DefaultAmqpHeaderMapper

AMQP has `MessageProperties` containing broker fields and a custom headers map. Spring Integration classes:

~~~java
org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper
org.springframework.integration.amqp.support.AmqpHeaderMapper
org.springframework.amqp.core.MessageProperties
org.springframework.amqp.support.AmqpHeaders
~~~

### 9.1. Common AMQP Headers

| Transport Metadata | Typical Spring MessageHeader | Notes |
|---|---|---|
| Received routing key | `amqp_receivedRoutingKey` | From actual received routing |
| Received exchange | `amqp_receivedExchange` | Exchange name |
| Delivery tag | `amqp_deliveryTag` | Meaningful only within that broker channel/delivery |
| Redelivered | `amqp_redelivered` | May be a redelivery |
| Consumer queue | `amqp_consumerQueue` | Queue used by the listener |
| Message ID | `amqp_messageId` | Not the Spring ID |
| Correlation ID | `amqp_correlationId` | AMQP request/reply |
| Content type | `contentType` | Special: does not use the `amqp_` prefix |
| Custom headers | `businessEventId`, `appTraceId` | Accepted only when allowed by policy |

### 9.2. Mapping Only Required Headers

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

@Configuration
public class InboundAmqpHeaderConfig {

    @Bean("inboundAmqpHeaderMapper")
    public DefaultAmqpHeaderMapper inboundAmqpHeaderMapper() {
        DefaultAmqpHeaderMapper mapper =
                new DefaultAmqpHeaderMapper();

        mapper.setRequestHeaderNames(
            "STANDARD_REQUEST_HEADERS",
            "businessEventId",
            "appTraceId",
            "!x-*",
            "!Authorization");

        return mapper;
    }
}
~~~

**Direction explanation:**

- `setRequestHeaderNames(...)` selects AMQP request headers read **into** the Spring Message.
- `STANDARD_REQUEST_HEADERS` is the token for standard AMQP properties per `AbstractHeaderMapper`.
- `businessEventId` and `appTraceId` are custom properties set by the producer.
- `!x-*` takes precedence to exclude broker/federation headers prefixed with `x-`, such as `x-received-from`.
- `setReplyHeaderNames(...)` applies to the reply/outbound direction; it **does not replace** the request policy.

Spring Integration documentation varies across versions regarding whether the default mapper automatically maps custom headers; some older Javadocs mention only standard properties, while the Reference Guide describes a broader default and explicitly warns about `x-*`. **Do not rely on implicit defaults**: declare patterns explicitly and test against your exact version/adapter.

### 9.3. AMQP XML Inbound Adapter Using header-mapper

~~~xml
<!-- Requires XML namespaces int-amqp, ConnectionFactory,
     queue orders.in, and a real downstream channel. -->
<int-amqp:inbound-channel-adapter
        id="ordersAmqpInbound"
        queue-names="orders.in"
        channel="ordersFromAmqp"
        header-mapper="inboundAmqpHeaderMapper"/>
~~~

This is an **independent XML alternative**; do not register a duplicate Java DSL listener on the same queue when testing a single pipeline. If using `mapped-request-headers` directly on the adapter, do not simultaneously use `header-mapper` when the schema defines the two options as mutually exclusive.

### 9.4. Testing the AMQP Mapper Without a RabbitMQ Server

~~~java
package example.headers;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

import static org.junit.jupiter.api.Assertions.*;

class AmqpHeaderPolicyTest {

    @Test
    void mapsBusinessHeaderButNotFederationHeader() {
        DefaultAmqpHeaderMapper mapper =
                new DefaultAmqpHeaderMapper();

        mapper.setRequestHeaderNames(
                "STANDARD_REQUEST_HEADERS",
                "businessEventId",
                "!x-*");

        MessageProperties props = new MessageProperties();
        props.setHeader("businessEventId", "evt-101");
        props.setHeader("x-received-from", "node-internal");

        Map<String, Object> mapped = mapper.toHeaders(props);

        assertEquals("evt-101", mapped.get("businessEventId"));
        assertFalse(mapped.containsKey("x-received-from"));
    }
}
~~~

This is a **mapping unit test**; it does not prove ACK behavior or RabbitMQ queue integration. Add a real test with a broker and an inbound gateway to verify the reply does not accidentally forward `x-received-from`.

### 9.5. Why Can Wildcard `*` Be Dangerous?

The Spring Integration docs warn about RabbitMQ federation: if an inbound gateway copies `x-*` headers and sends them back via reply/outbound, the broker may interpret that metadata as a loop indicator and drop the message.

~~~text
Inbound RabbitMQ header:
  businessEventId = evt-101
  x-received-from  = broker-specific federation metadata

Unsafe wildcard:
  inbound MessageHeaders includes x-received-from
      -> reply copies it back
      -> federation misinterprets / may drop reply
~~~

Use an allowlist or negative patterns; if you still accept wildcards, filter headers before outbound. **`DeliveryTag` and the broker channel** have short lifetimes and must not be serialized/forwarded to HTTP/JMS as business metadata.

### 9.6. Mapping Does Not Replace ACK

With `AcknowledgeMode.MANUAL`, the adapter can provide the delivery tag/channel for application ACK; `AcknowledgeMode.AUTO`/listener containers have different rules. `HeaderMapper` does **not** ACK the broker, does not guarantee the message is durably stored, and modifying `amqp_redelivered` does not alter redelivery policy.

## 10. Kafka: HeaderMapper Lives in Spring Kafka, Not Integration's Generic Interface

The Spring Integration Kafka inbound adapter uses a converter from **Spring for Apache Kafka**, which has its own header strategy:

~~~java
org.springframework.kafka.support.KafkaHeaderMapper
org.springframework.kafka.support.DefaultKafkaHeaderMapper
org.springframework.kafka.support.SimpleKafkaHeaderMapper
org.springframework.kafka.support.converter.MessagingMessageConverter
~~~

`KafkaHeaderMapper` is not by default the same Java generic type `org.springframework.integration.mapping.HeaderMapper<T>` used by HTTP/JMS. Kafka wire record headers have **`byte[]`** values and **can have multiple entries with the same key**.

### 10.1. Preserving Kafka Metadata with the Right Types

| Metadata | Meaning | Common Pitfall |
|---|---|---|
| Received topic | Actual topic received from | Do not let raw client headers override it |
| Received partition | Partition of the record | Not a tenant |
| Offset | Record position in the partition | Not a business event ID |
| Received record key | Kafka key deserialized by the consumer | Not necessarily globally unique |
| Timestamp/type | Broker/record metadata | Not the business commit time |
| Custom headers | Usually bytes/JSON-encoded | Must be decoded per contract/version |
| Acknowledgment object | May appear only with manual ACK | Do not serialize/forward over JMS/HTTP |

Some metadata is created by `MessagingMessageConverter` **from `ConsumerRecord` properties**, not from the raw Kafka record header map.

### 10.2. Configuring a Custom Kafka Mapper via Converter

Fragment per Spring Kafka 3.x/compatible versions:

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

MessagingMessageConverter converter =
        new MessagingMessageConverter();

converter.setHeaderMapper(
        new SimpleKafkaHeaderMapper(
                "businessEventId",
                "appTraceId"));
~~~

Then inject the converter into the Spring Integration Kafka inbound adapter via `setMessageConverter(...)` or the supported DSL in your version. **This is not a complete `IntegrationFlow`**; it needs a `ConsumerFactory`, listener container, group/topic, and error handling.

- `SimpleKafkaHeaderMapper` prefers raw byte representation and does not arbitrarily reconstruct Java objects.
- `DefaultKafkaHeaderMapper` supports JSON type mapping; for untrusted inputs you must restrict trusted packages/types.
- Multiple values with the same Kafka header name may be handled differently depending on version/multi-value-header policy; do not assume all are kept.
- Do not forward Kafka offset/ack objects as JMS properties or HTTP headers; normalize business headers separately.

### 10.3. Kafka Retry and Idempotency

If Kafka redelivers after a MongoDB commit but before the offset commit, the new Spring Message can have a different `MessageHeaders.ID`. Use a stable `businessEventId` and a business-scoped durable inbox/unique index. **The mapper does not commit offsets or provide exactly-once semantics.**
## 11. File/FTP/SFTP/SMB and TCP/UDP: Adapters Create Headers Directly

HTTP/JMS/AMQP have mappers for external headers, but **not every adapter has a generic `HeaderMapper`**. For File/FTP/SFTP/SMB/IP, the framework usually attaches protocol metadata to Spring `MessageHeaders` when constructing the message.

### 11.1. Remote File Headers

Spring Integration provides:

~~~java
org.springframework.integration.file.FileHeaders
~~~

Related constants:

| Header Constant | Purpose | Notes |
|---|---|---|
| `FileHeaders.FILENAME` | Filename for file-output naming | Not automatically present on every file inbound message |
| `FileHeaders.REMOTE_DIRECTORY` | Remote directory | Present on supporting FTP/SFTP/SMB sources |
| `FileHeaders.REMOTE_FILE` | Remote filename | Depends on operation/source |
| `FileHeaders.REMOTE_HOST_PORT` | Session `host:port` | Only when the adapter has remote session metadata |
| `FileHeaders.REMOTE_FILE_INFO` | Remote file info | JSON/object type depending on adapter/version |

Do not infer business identity or completed file transfer solely from `REMOTE_FILE`. Two partners can use the same filename, `mtime` can change, or a remote file may still be mid-upload. You need a file naming contract, checksum/business ID, persistent accept-once filter, and crash recovery.

### 11.2. Using HeaderEnricher When the Adapter Has No Generic HeaderMapper

~~~java
@Bean
public IntegrationFlow partnerFileFlow(
        org.springframework.integration.core.MessageSource<?> sftpSource) {

    return IntegrationFlow.from(sftpSource,
            e -> e.poller(Pollers.fixedDelay(5000)))
        .enrichHeaders(h ->
            h.header("sourceSystem", "partner-a-sftp"))
        .channel("partnerFiles")
        .get();
}
~~~

This is a **fragment** with the SFTP source, polling configuration, session factory, and downstream consumer provided by the application. `sourceSystem` is a server configuration value, not a name self-declared by the remote file. There is no need to attach `DefaultHttpHeaderMapper` to SFTP.

### 11.3. IpHeaders for UDP/TCP

Spring Integration IP provides:

~~~java
org.springframework.integration.ip.IpHeaders
~~~

UDP inbound can produce IP address/port/packet address headers; TCP inbound provides connection ID/related metadata depending on the adapter and connection factory.

~~~java
Message<?> incoming = ...;

Object ip = incoming.getHeaders()
    .get(org.springframework.integration.ip.IpHeaders.IP_ADDRESS);

Message<?> normalized =
    MessageBuilder.fromMessage(incoming)
        .setHeader("sourceTransport", "udp")
        .setHeader("externalSourceAddress", ip)
        .build();
~~~

This uses `MessageBuilder` after the adapter, **not a raw UDP HeaderMapper**. Source IP is not an authenticated identity due to NAT, proxies, and spoofing; UDP also has no built-in reliability/dedup.

## 12. Designing a Common Application Header Contract Across Multiple Sources

When HTTP, JMS, AMQP, Kafka, and SFTP all feed messages into the same business channel, the business handler should not have to understand every protocol-specific header name. Normalize at ingress:

| Application Header | Type | Trusted Source | Used For |
|---|---|---|---|
| `businessEventId` | String | Validated stable ID from payload/producer | Idempotency |
| `appTraceId` | String | Normalized tracing context/hint | Tracing |
| `trustedTenantId` | String | Server-side authentication/authorization | Tenant isolation |
| `sourceSystem` | String/enum | Endpoint configuration | Routing |
| `sourceProtocol` | String/enum | Adapter identity | Metrics, debugging |
| `receivedAt` | Instant | Server clock | SLA |
| `schemaVersion` | String/int | Event schema contract | Parser selection |
| `contentType` | MediaType/String | Validated converter/mapping | Decoding |

### 12.1. Multiple Ingresses, One Canonical Contract

~~~mermaid
flowchart LR
  H["HTTP Mapper"] --> N["Validate + normalize"]
  J["JMS Mapper"] --> N
  A["AMQP Mapper"] --> N
  K["Kafka converter"] --> N
  S["SFTP source"] --> N
  N --> C["canonicalInbound channel"]
  C --> B["Business handler"]
~~~

The business handler only reads validated keys, independent of the protocol source.

### 12.2. Some Metadata Must Not Be Copied Across Protocols

Example Kafka → JMS:

- `kafka_offset`, partition, and acknowledgment object are not business JMS properties.
- Kafka custom headers may be `byte[]`, whereas JMS properties have restricted types.
- HTTP `Authorization` is a secret; do not forward it to brokers/logs.
- AMQP `deliveryTag` and channel object are meaningful only in the current listener.
- Spring Integration's `replyChannel`/`errorChannel` are routing objects; do not serialize them into external headers.
- Copy only `businessEventId`/`appTraceId` and required fields after validation.

### 12.3. Immutable Contract for Values

Spring `MessageHeaders` enforces a contract of not mutating the map directly; however, values themselves can be mutable objects. Do not let a `Map`/`List` from transport be mutated concurrently across threads or retain references to sessions/sockets in durable messages. When needed, copy/convert to `String`/record/size-bounded immutable collections.

## 13. HeaderEnricher, HeaderFilter, and MessageBuilder After Mapping

`HeaderMapper` handles the **protocol boundary**. Once a Spring `Message` exists, Spring Integration provides EIPs:

- **HeaderEnricher**: attaches application metadata.
- **HeaderFilter**: removes specific headers.
- **Transformer**: changes payload/headers and builds a new message.
- **Router**: routes based on validated headers.
- **ServiceActivator**: receives payload and header values and invokes business logic.

### 13.1. XML HeaderFilter

~~~xml
<int:header-filter
        input-channel="rawInbound"
        output-channel="filteredInbound"
        header-names="Authorization,X-Untrusted-Role"/>
~~~

Requires the `int` XML namespace and channels/consumers. The filter uses **post-mapping header names**; if external `X-Trace-Id` was already normalized to `appTraceId`, removing `X-Trace-Id` does not affect `appTraceId`.

### 13.2. Java DSL Filter/Enrich

~~~java
@Bean
public IntegrationFlow normalizeInbound() {
    return IntegrationFlow.from("rawInbound")
        .headerFilter(
            "Authorization", "X-Untrusted-Role")
        .enrichHeaders(h -> h
            .header("sourceSystem", "partner-a")
            .headerExpression(
                "serverReceivedAt",
                "T(java.time.Instant).now().toString()"))
        .channel("canonicalInbound")
        .get();
}
~~~

This is a fragment inside `@Configuration` with upstream `rawInbound`/downstream `canonicalInbound`. `sourceSystem` is decided by the server; the SpEL expression is **trusted application configuration** — never let clients pass arbitrary expressions.

### 13.3. MessageBuilder Adding Trusted Tenant and Business ID

~~~java
Message<?> clean = MessageBuilder.fromMessage(incoming)
    .removeHeader("Authorization")
    .removeHeader("X-Untrusted-Role")
    .setHeader("sourceProtocol", "http")
    .setHeader("trustedTenantId", authorizedTenantId)
    .setHeader("businessEventId", verifiedEventId)
    .build();
~~~

`authorizedTenantId` must come from an authenticated principal/ACL; `verifiedEventId` must be validated and bound to the payload. Avoid taking them directly from unverified client headers.

### 13.4. @ServiceActivator Reading the Contract

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class CanonicalEventHandler {

    @ServiceActivator(inputChannel = "canonicalInbound")
    public void process(
            String payload,
            @Header("businessEventId") String eventId,
            @Header("trustedTenantId") String tenantId) {

        // Business service must verify schema and idempotency.
    }
}
~~~

If a required header is missing or has the wrong type, argument binding can throw a messaging/conversion exception. That is an input error to handle explicitly, not a valid empty header.
## 14. Securing Inbound Headers: External Data Is Not Trusted State

Any header coming from an HTTP client, JMS/AMQP/Kafka producer, SFTP filename, or UDP sender must be treated as **untrusted external input** until verified by the application.

| External Header | Dangerous Mistake | Safe Policy |
|---|---|---|
| HTTP Authorization | Forwarding bearer token to Kafka/JMS/logs | Spring Security verifies it; keep only required principal/claims |
| HTTP X-Tenant-Id | Choosing MongoDB collection from client-sent header | Derive tenant from authenticated identity/ACL |
| HTTP X-Forwarded-For | Trusting arbitrary client address | Trust only configured reverse proxy chain |
| HTTP X-Role | Mapping `role=admin` and routing | Obtain roles from server-side IAM/access control |
| JMS businessEventId | Treating as valid solely because it is a JMS property | Validate producer, schema/tenant/length |
| AMQP x-* | Reflecting broker federation headers onto reply | Filter/allowlist and test the reply |
| Kafka type header | Deserializing arbitrary Java classes | Trusted packages/schema allowlist |
| SFTP remote filename | Concatenating path without normalization | Restrict root dir and validate filename |
| UDP source IP | Using as authentication | Application-layer auth/signature |
| External reply routing | Letting client pick internal `replyChannel` bean | Gateway/server routing policy |

### 14.1. Reserved/Internal Header Collisions

An external producer could send headers named `id`, `timestamp`, `replyChannel`, `errorChannel`, `trustedTenantId`, or a header interpreted by a business router as a control command.

- The Spring framework may protect some core headers, but do not treat that as a complete security boundary.
- Do not map `*` from external headers into `MessageHeaders` unchecked.
- Separate the external hint `X-Trace-Id` from the server-generated `appTraceId` when trusted tracing is required.
- Create `trustedTenantId` **after** authentication; never let raw external headers overwrite it.
- Reply routing must go through gateway policy, never taking a raw request header as an arbitrary bean name or destination.

### 14.2. Input Size and Header Injection

Add bounds for:

1. Header count and total metadata bytes.
2. Length of each key/value and number of repeated values.
3. Charset, Unicode normalization, and CR/LF control characters.
4. JSON type hints and class names in Kafka/AMQP.
5. Log/error message contents: never accidentally log tokens, credentials, PII, or raw payloads.
6. Metric labels: never use per-request IDs/event IDs as high-cardinality labels.

For an HTTP inbound gateway, a custom mapper's `fromHeaders(...)` method can also write headers into the **HTTP response**. Never echo untrusted values containing CR/LF or secrets; allowlist and validate only the response headers truly needed.

## 15. Data Types, Casing, and Multiple Values

### 15.1. HTTP Header Names Are Case-Insensitive

HTTP `X-Trace-Id` and `x-trace-id` are the same name in the wire protocol; however, a Java `Map<String,Object>` does not guarantee case-insensitive key lookups by default.

Avoid:

~~~java
String trace = (String) message.getHeaders()
        .get("x-trace-id"); // Can be null or wrong type.
~~~

Use `HttpHeaders` extraction with an explicit contract at the boundary, normalize to a validated `String` `appTraceId`, and have business handlers read only the canonical key.

### 15.2. Multi-Value Headers and Ambiguous Identity

~~~http
X-Partner-Event-Id: event-101
X-Partner-Event-Id: event-102
~~~

If an event ID must be a **single** value, reject multiple distinct values instead of picking the first or comma-joining them. For `Accept`, multiple values have different semantics; policies must be per-header, rather than a single `String.join(",")` helper for everything.

### 15.3. Kafka Supports Repeated Record Headers

A Kafka record can contain multiple headers with the same key. The Spring Kafka converter has JSON/simple/multi-value mapping policies depending on version. Tests should confirm whether entries are preserved, merged, or collapsed to one value; do not assume a `KafkaHeaderMapper` always preserves every entry.

### 15.4. JMS Properties Have Restricted Types

JMS properties support specific primitive/string types, not arbitrary Java object maps. When bridging `Kafka → JMS`, a `byte[]`/List/Map header may be invalid for JMS. Normalize before sending; do not cast blindly.

### 15.5. Validation Scenarios Table

| State | Example | Policy |
|---|---|---|
| Missing header | No `businessEventId` | Reject if required by business logic |
| Empty header | `businessEventId=""` | Reject or generate server-side per contract |
| Malformed header | Event ID too long or contains invalid chars | Reject/quarantine |
| Multi-value conflict | Two IDs on one HTTP request | Reject |
| Header/body mismatch | External `eventId` differs from JSON `eventId` | Conflict; do not silently pick one |
| Wrong type | `byte[]` where handler expects `String` | Schema-based conversion, avoid `ClassCastException` |
| Reserved header | External `replyChannel` / `trustedTenantId` | Disallow override |
| Same name with different casing | `X-TRACE-ID` and `x-trace-id` | Normalize/reject ambiguity |

## 16. Correlation, Tracing, and Idempotency Are Not the Same ID

An inbound event may carry:

~~~text
Spring MessageHeaders.id  = <Spring Message UUID>
HTTP X-Trace-Id           = trace-006
JMS jms_messageId         = ID:provider:...
JMS jms_correlationId     = request-42
AMQP amqp_messageId       = msg-808
Kafka offset              = topic orders, partition 2, offset 1801
Business eventId          = order-accepted-1001
~~~

Distinguish them:

- **Spring Message ID:** identifies a single Spring `Message` instance; may change after rebuild/transform/redelivery.
- **Correlation ID:** links request/reply, aggregator, or trace; not automatically an idempotency ID.
- **Protocol Message ID:** identifier within the broker/protocol; may change upon republish.
- **Kafka offset:** position within a topic-partition; not globally unique at the business level.
- **Business event ID:** ID guaranteed by the domain/producer contract to remain stable across retries, typically the key for durable inbox/dedup.

### 16.1. Context-Appropriate Dedup Key Example

~~~text
External HTTP header X-Partner-Event-Id = event-101
JSON body.eventId                       = event-101
Authorized tenant                        = tenant-a
Dedup business key                       = (tenant-a, event-101)
~~~

Header and payload must match per contract; if the same ID arrives with a different payload, that is a conflict requiring reconciliation, not a valid duplicate to ACK blindly.

### 16.2. Correlation in an Inbound Gateway

A JMS gateway can use `JMSCorrelationID` to send replies back to the right request. An HTTP gateway has its transport request/response context. Do not use `MessageHeaders.ID` in place of `JMSCorrelationID` or use `appTraceId` to infer business event identity.

If you need to route based on a reply header, allow only server-configured/authorized destinations; never let clients attach `replyChannel` and control internal routing.

### 16.3. HeaderMapper Does Not Provide Exactly-Once

Properly mapping `businessEventId` enables implementing a durable inbox/idempotent consumer; **it does not commit Kafka offsets, ACK JMS/AMQP, move SFTP files, or handle UDP loss**. Transaction/ACK/retry/recovery belong to the adapter/handler/broker/service layers.

## 17. Errors During Header Mapping and Impact on ACK

A mapping error can occur here:

~~~text
External message
    -> adapter receives
    -> HeaderMapper.toHeaders / MessageConverter
    -> validation/conversion error
    -> errorChannel / listener container / upstream response
~~~

**Do not assume every error goes to a single error channel**: it depends on the adapter, asynchronous boundaries, gateway, transaction config, and where the exception is thrown.

### 17.1. HTTP Inbound Gateway

- Missing/wrongly typed/oversized header → return HTTP 400/422 per application exception mapping.
- Unauthenticated/unauthorized → 401/403 from the security filter, **without** waiting for `HeaderMapper`.
- Business handler failure → HTTP 5xx/timeout per gateway/error policy.
- A 200 status does not prove downstream Kafka/MongoDB committed if the handler is asynchronous and replies early.
- Never return raw stack traces/tokens/header values in error responses.

### 17.2. JMS Message-Driven Adapter

- Conversion/mapping errors can be sent as an `ErrorMessage` via the error channel.
- If the error flow swallows the exception, the listener transaction may commit instead of rolling back, preventing redelivery.
- For data that must not be lost, propagate the exception or use durable quarantine/DLQ before ACK per contract.
- `jms_redelivered` is observational metadata; it does not trigger retries itself.

### 17.3. AMQP Inbound Adapter

- Manual/auto broker ACK mode is controlled by the container config, not the mapper.
- Do not attempt to ACK by editing `amqp_deliveryTag`/`amqp_redelivered` headers.
- With `AcknowledgeMode.MANUAL`, the delivery tag and channel are tied to the specific listener/connection; do not forward/persist them as business metadata.
- Avoid poison-message loops when a schema is unprocessable; require a reject/DLQ/quarantine policy.

### 17.4. Kafka Inbound Adapter

- Header mapper errors in the converter/deserializer can cause the listener to fail or route to an error handler/DLT depending on container config.
- Offset commit/callback timing is determined at the Kafka listener/adapter layer.
- When retrying the same event, `businessEventId` must remain stable; Spring Message ID and offset do not replace the business key.
- Kafka record headers can contain type information; restrict classes/trusted packages to prevent arbitrary deserialization.

### 17.5. File/SFTP/IP

- File sources may use an accept-once filter/persistent `MetadataStore`; header mapping does not create a transactional checkpoint.
- An SFTP download failing before the handler differs from the handler failing after download. Recorded markers may remain, requiring recovery.
- UDP has no built-in broker ACK; payload/header parsing errors need a protocol-appropriate drop/quarantine/alert policy.
- Downstream timeouts/lost ACKs can produce unknown results; replay with the same business ID rather than generating a new one.
## 18. Dependencies and Practice Environment

Select dependencies according to the protocols you use. Maven example for an application practicing HTTP/JMS/AMQP/Kafka (Spring Boot 3.x, Spring Integration 6.x, versions managed by BOM):

~~~xml
<!-- Dependencies inside <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-http</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-amqp</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

This is an **example set**; you do not need every module if your product uses only one protocol. JMS needs a compatible Jakarta JMS broker/client, AMQP needs RabbitMQ, Kafka needs a Kafka cluster/consumer factory, and SFTP needs an SSH/SFTP session factory. For tests using Testcontainers, the CI runner needs Docker or an alternative test service.

| Protocol | Module | HeaderMapper/Metadata |
|---|---|---|
| HTTP Servlet | `spring-integration-http` | `DefaultHttpHeaderMapper` |
| WebFlux | `spring-integration-webflux` | HTTP/WebFlux endpoint mapping |
| JMS | `spring-integration-jms` | `DefaultJmsHeaderMapper` |
| RabbitMQ/AMQP | `spring-integration-amqp` | `DefaultAmqpHeaderMapper` |
| Kafka | `spring-integration-kafka` and Spring Kafka | `KafkaHeaderMapper` from Spring Kafka |
| File/FTP/SFTP | `spring-integration-file/ftp/sftp` | `FileHeaders`, source metadata |
| TCP/UDP | `spring-integration-ip` | `IpHeaders` |
| MongoDB | `spring-integration-mongodb` | MongoDB sources, does not use HTTP HeaderMapper |

## 19. Testing Header Mapping: Unit to End-to-End

### 19.1. Test Matrix

| Test | Level | Assertion |
|---|---|---|
| HTTP allowlist | Unit | `X-Trace-Id` is mapped, `X-Untrusted-Role` is excluded |
| HTTP case-insensitive | Unit | `X-Trace-Id`/`x-trace-id` share the same semantics |
| HTTP multi-value ID | Unit | Reject two event IDs on one request |
| HTTP gateway mapping | Integration | Request reaches handler with expected headers |
| HTTP reply mapping | Integration | Does not echo raw `Authorization`/Role |
| JMS correlation | Broker integration | `jms_correlationId` correct, differs from Spring ID |
| JMS custom property | Broker integration | `businessEventId` has the expected type |
| JMS rollback | Broker integration | Error flow does not falsely ACK |
| AMQP allowlist | Unit | `appTraceId` mapped, `x-received-from` blocked |
| AMQP gateway reply | Broker integration | Broker metadata is not mirrored |
| Kafka custom header | Converter unit | `bytes → application value` correct |
| Kafka duplicate header | Converter unit | Multi-value policy matches version |
| SFTP remote info | Integration | `FileHeaders` populated when adapter supports it |
| UDP sender metadata | Socket integration | `IpHeaders` reflects packet source |
| Tenant spoofing | Security integration | `X-Tenant-Id` does not alter trusted tenant |
| Missing business ID | Integration | Reject/quarantine with error policy |
| Restart/redelivery | Integration | Event ID remains stable and downstream is idempotent |

### 19.2. MockMvc with HTTP Inbound Gateway

For the HTTP flow in Section 6:

~~~java
package example.headers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HttpOrdersInboundIT {

    @Autowired
    MockMvc mvc;

    @Test
    void gatewayResponds() throws Exception {
        mvc.perform(post("/ingest/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Trace-Id", "trace-100")
                .header("X-Partner-Event-Id", "event-101")
                .header("X-Untrusted-Role", "admin")
                .content("{\"orderId\":\"o-101\"}"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.startsWith("accepted")));
    }
}
~~~

**Important:** this test only proves the route and response; to **prove the `HeaderMapper` is actually wired**, capture the Spring Message in the handler/test spy/wire tap and assert which headers were or were not copied. An HTTP 200 response alone does not prove mapping or a durable business commit.

### 19.3. QueueChannel Test Sink

A bounded test channel:

~~~java
@Bean("observedInbound")
public org.springframework.messaging.PollableChannel observedInbound() {
    return new org.springframework.integration.channel.QueueChannel(10);
}
~~~

After an inbound **one-way adapter** sends a message to the channel:

~~~java
Message<?> received = observedInbound.receive(2000);

assertNotNull(received);
assertNotNull(received.getHeaders().get("X-Partner-Event-Id"));
~~~

This is a test fragment; the wire/adapter must connect to `observedInbound`. If you send an inbound **gateway** straight into a `QueueChannel` with no reply handler, the HTTP/JMS caller may time out. For a gateway, use a side-channel capture/wire tap or a test handler that returns a reply.

### 19.4. Broker Integration Tests

Unit testing `DefaultAmqpHeaderMapper.toHeaders(...)` does not require RabbitMQ, but verifying `amqp_deliveryTag`/ACK, redelivery/reconnect, and manual/auto ACK requires a broker test. JMS is the same with a JMS provider; Kafka needs a listener/container to test received topic/partition/offset, converter, and DLT.

A mapper unit test does not prove container transaction/offset commit behavior. When mapping fails, an error-channel flow can swallow the exception and cause false ACKs; test that scenario too.

## 20. Performance, Logging, and Lifecycle

### 20.1. HeaderMapper Should Be Pure and Bounded

Avoid using a custom mapper to:

- Query a database/HTTP service on every received message.
- Deserialize arbitrary object graphs/class names from user type headers.
- Wildcard-copy all broker-specific metadata.
- Attach hundreds/megabytes of raw headers to a Spring Message.
- Log entire `MessageHeaders` containing secrets.
- Perform blocking I/O on a WebFlux/reactive event loop or broker listener thread.

A good HeaderMapper should be **deterministic, I/O-free, low-allocation, fast to validate, and size-bounded**. Authorization/database lookups belong in a stage designed with proper timeouts/caching.

### 20.2. Suggested Metrics

| Metric | Purpose |
|---|---|
| `inbound_header_mapping_total` | Mapper execution count |
| `inbound_header_mapping_error_total` | Mapper/conversion errors |
| `inbound_header_rejected_total` | Rejected headers |
| `inbound_header_type_mismatch_total` | Incorrect type conversions |
| `inbound_header_missing_event_id_total` | Missing business IDs |
| `inbound_header_validation_duration_seconds` | Validation latency |
| `inbound_authz_rejected_total` | Tenant/role conflicts |
| `inbound_dlq_total` | Durable-quarantined events |
| `inbound_business_committed_total` | Completed business effects |

These are **suggested metric names**, not automatically emitted by the framework. Do not use per-event `eventId`/`deviceId`/header values as metric labels, as this causes high cardinality.

### 20.3. Safe Logging

~~~text
ingress_received      protocol=http source=partner-a
headers_mapped        headerCount=4
header_validated      tracePresent=true eventIdPresent=true
business_dispatched   route=orders
business_committed    outcome=accepted
~~~

Never log raw tokens, cookies, passwords, PII, or full payloads. For tracing context across `ExecutorChannel`/Reactor, configure context propagation; do not assume `ThreadLocal` MDC is preserved automatically.

### 20.4. Connector Lifecycle Does Not Depend on the Mapper

- HTTP: request/response timeouts, servlet/reactive lifecycle.
- JMS/AMQP: listener connection, concurrency, broker ACK/redelivery.
- Kafka: consumer poll/rebalance/offset commit.
- SFTP/File: poller, remote/local filters, session/transfer.
- IP/UDP: datagram handling and connection state, with no broker ACK.
- MongoDB: query/poller/checkpoint/claim depending on source.

**`HeaderMapper` does not start/stop pollers, retry brokers, or drain in-flight messages.** For deployments, design durable sources, replay, and idempotency separately.
## 21. Troubleshooting: Header Present on Transport but Missing in Flow

| Symptom | Possible Cause | Resolution |
|---|---|---|
| HTTP custom header missing | `setInboundHeaderNames` did not include it | Configure allowlist and test `toHeaders` |
| Used HeaderMapper but wrong direction | Called `fromHeaders` for inbound request | Inbound uses `toHeaders(external)` |
| Mapper has header, handler loses it | `HeaderFilter`/Transformer/another flow | Capture `Message` at each channel |
| Different header casing | HTTP is case-insensitive, Java Map lookup is not | Normalize name to `appTraceId` |
| Custom mapper drops `Content-Type` | Overrode standard defaults | Explicitly add `Content-Type` or `HTTP_REQUEST_HEADERS` |
| HTTP request has two event IDs | Did not check multiple values | Reject singleton ID ambiguity |
| HTTP `Authorization` forwarded to broker | Wildcard copy | Exclude via security boundary/allowlist |
| `X-Tenant-Id` switches tenant | Client input treated as trusted | Server-side principal/ACL |
| Header throws `ClassCastException` | `String` vs `List`/`byte[]`/`MediaType` | Contract-based typed conversion |
| JMS `messageId` used for dedup | Confused protocol ID with business ID | Stable `businessEventId` |
| JMS correlation does not match reply | Confused `jms_correlationId`/`correlationId` | Check gateway correlation policy |
| JMS conversion error still ACKs | Error flow swallows exception | Transaction rollback or durable DLQ |
| AMQP `x-received-from` appears in reply | Wildcard copied federation property | Filter/negative pattern |
| AMQP custom header missing | Default mapping differs by version | Explicit `requestHeaderNames` |
| RabbitMQ `deliveryTag` invalid | Used tag after reconnect/different channel | ACK on the active channel |
| Kafka custom header is `byte[]` | Cast directly to `String` | `KafkaHeaderMapper`/codec |
| Kafka type header causes deserialization error | Untrusted class/wrong schema | Trusted package/schema policy |
| Kafka duplicate header lost | Converter's multi-value policy | Check version and test |
| SFTP remote filename header missing | Source/option does not provide it | Check `FileHeaders`/API |
| UDP IP used as identity | NAT/spoofing | App-level identity verification |
| `replyChannel` externally overridden | Copied reserved headers | Restrict external keys |
| `send()` returns true before business commit | Async channel/service | ACK after durable stage |
| `ErrorMessage` only logged then lost | No durable recovery | Re-throw/ack policy/DLQ |
| Request times out despite OK mapper | Inbound gateway lacks reply consumer | Configure reply handler/correlation |
| Tests pass but broker fails | Only unit tested mapper | Integration test with broker/container |
| Oversized headers cause memory pressure | Wildcards, unbounded size | Limit name/value/count/buffer |

### 21.1. Logical Isolation Sequence

~~~text
1. Request/broker payload + external headers
2. Inbound adapter/gateway and MessageConverter
3. HeaderMapper.toHeaders(external) or native adapter headers
4. Constructed Message<?> (type/name/values)
5. HeaderFilter/Enricher/Transformer/Router
6. Business handler (@Header and payload contract)
7. Error channel, ACK/retry, downstream commit
~~~

Log/tap each stage in a test environment without logging secrets. If the HTTP mapper unit test PASSES but the HTTP flow doesn't see the header, verify that **the mapper bean is actually injected into the right endpoint** and check whether any transform/filter replaces the message.

### 21.2. Errors to Distinguish

- **Missing header**: source did not send it or mapper did not select it.
- **Wrong type**: mapper selected it, but the value is `List<String>`/`byte[]`.
- **Invalid value**: header exists but fails validation.
- **Untrusted**: value looks valid but is not authenticated/authorized.
- **Lost along flow**: transform/filter removed or renamed it.
- **Downstream failure**: headers are fine, but broker/DB failed to commit.
- **ACK ambiguity**: source does not know if the message was persisted.

Each category requires different handling; do not infinitely retry a malformed header as if it were a transient connection error.

## 22. Comprehensive Practice Exercise

Build **HTTP/JMS/AMQP/Kafka/SFTP → HeaderMapper/Normalizer → MessageChannel → Router → business service**. Each part uses an independent profile or test broker; you do not need to enable every adapter at once.

### Part A — HTTP Inbound

1. Create `DefaultHttpHeaderMapper.inboundMapper()` and allowlist `Content-Type`, `X-Trace-Id`, `X-Partner-Event-Id`.
2. Unit test `toHeaders(HttpHeaders)` for the selected keys.
3. Assert `X-Untrusted-Role` and `Authorization` are not forwarded.
4. Use `Http.inboundGateway("/ingest/orders")`, connected to a reply-returning handler.
5. Try a curl/MockMvc request with valid `eventId`/`traceId`.
6. Capture the Spring Message and assert casing/typed headers instead of just status 200.
7. Send two event IDs in the same request and apply the reject policy.
8. Implement a custom `HeaderMapper` mapping the trace hint to `externalTraceId`.

### Part B — JMS

1. Configure `DefaultJmsHeaderMapper` with inbound delivery mode/expiration/priority as needed.
2. Use a JMS message-driven channel adapter and a test broker.
3. Send `JMSCorrelationID` and a `businessEventId` property.
4. Verify `jms_correlationId` differs from Spring `MessageHeaders.ID`.
5. Trigger rollback/redelivery; inspect `jms_redelivered` and ACK policy.
6. Trigger a conversion error; verify error channel/DLQ actually operates.

### Part C — AMQP/RabbitMQ

1. Use `DefaultAmqpHeaderMapper` with `STANDARD_REQUEST_HEADERS` and 2 custom keys.
2. Test `MessageProperties.headers` containing `x-received-from`.
3. Unit-assert that federation metadata is not mapped.
4. Configure a real inbound adapter/gateway with a test broker.
5. Verify the reply does not mirror `x-*`.
6. Try manual ACK, distinguishing `deliveryTag` from the business event ID.

### Part D — Kafka, SFTP, and IP

1. Configure Spring Kafka `MessagingMessageConverter` with an appropriate header mapper.
2. Send a Kafka raw bytes header; test decoding and duplicate names.
3. Use an SFTP inbound source with remote file metadata.
4. Check `FileHeaders.REMOTE_DIRECTORY`/`REMOTE_FILE` when supported by the source.
5. Attach `sourceSystem` via `HeaderEnricher`.
6. Try UDP inbound, read `IpHeaders.IP_ADDRESS`, and explain trust limitations.
7. Normalize all protocols to `businessEventId`/`appTraceId`/`trustedTenantId`.

### Part E — Production Hardening

1. Document an external header allowlist table per protocol.
2. Define max header count/bytes, multi-value policy, and validation regexes.
3. Catch header/body conflicts and tenant spoofing.
4. Block external overwrites of `replyChannel`, `errorChannel`, and `trustedTenantId`.
5. Test error handling so the source is not ACKed early when mapping/conversion fails.
6. Test that retries/redeliveries preserve a stable business event ID.
7. Measure mapping/reject/latency metrics, but do not log secrets/high-cardinality IDs.
8. Rehearse deploy/restart, ensuring connector lifecycle and durable recovery.

**Self-Assessment Questions:**

- What are the two methods of `HeaderMapper<T>`? Why is `toHeaders` inbound?
- How does `HeaderMapper` differ from `MessageConverter` and `HeaderEnricher`?
- Which endpoint does `DefaultHttpHeaderMapper.inboundMapper()` apply to?
- Does `setInboundHeaderNames` keep unlisted standard headers?
- Why is `X-Tenant-Id` not automatically `trustedTenantId`?
- What bug can case-insensitive HTTP header names cause when reading Spring `MessageHeaders`?
- How does `JMSCorrelationID` differ from Spring `correlationId` and `businessEventId`?
- Does `jms_redelivered` prove a business commit?
- Why can AMQP `x-received-from` cause federation reply errors?
- Does AMQP `contentType` have an `amqp_` prefix?
- How does Spring Kafka's `KafkaHeaderMapper` differ from Spring Integration's `HeaderMapper` interface?
- Why shouldn't you copy a Kafka offset/ack object to JMS properties?
- How do SFTP remote headers differ from an HTTP `HeaderMapper`?
- Can `HeaderFilter` replace an HTTP authentication filter?
- Why doesn't an HTTP 200 response automatically prove the mapper is right or the DB committed?
- How can an error-channel handler that only logs and returns affect broker ACK?
- How does a header mapper help idempotency, and what does it NOT do for exactly-once?

## 23. References

- [Spring Integration API — HeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/mapping/HeaderMapper.html): `toHeaders`/`fromHeaders` strategy interface.
- [Spring Integration API — AbstractHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/mapping/AbstractHeaderMapper.html): request/reply patterns.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): `DefaultHttpHeaderMapper` and standard/request/response headers.
- [Spring Integration API — DefaultHttpHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/http/support/DefaultHttpHeaderMapper.html): `inboundMapper`, `setInboundHeaderNames`, `toHeaders`.
- [Spring Integration API — HTTP Inbound Spec](https://docs.spring.io/spring-integration/api/org/springframework/integration/http/dsl/HttpInboundEndpointSupportSpec.html): `headerMapper`, `mappedRequestHeaders`, `requestMapping`.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS header mapping, conversion, message-driven adapter, error channel.
- [Spring Integration API — DefaultJmsHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/jms/DefaultJmsHeaderMapper.html): JMS headers and options.
- [Spring Integration API — JMS Message Driven Spec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): `headerMapper(JmsHeaderMapper)`.
- [Spring Integration Reference — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html): AMQP standard headers, custom patterns, negative patterns, and federation.
- [Spring Integration API — DefaultAmqpHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/amqp/support/DefaultAmqpHeaderMapper.html): AMQP mapper.
- [Spring Integration Reference — AMQP Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/amqp/inbound-channel-adapter.html): `header-mapper`/`mapped-request-headers`, ACK mode.
- [Spring Integration Reference — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): record to Message conversion.
- [Spring Kafka Reference — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html): `KafkaHeaderMapper`, Simple/Default implementations.
- [Spring Integration Reference — SFTP Remote File Information](https://docs.spring.io/spring-integration/reference/sftp/remote-file-info.html): `FileHeaders.REMOTE_FILE`/`REMOTE_DIRECTORY`/`REMOTE_HOST_PORT`.
- [Spring Integration Reference — TCP and UDP](https://docs.spring.io/spring-integration/reference/ip.html): source IP and connection metadata.
- [Spring Integration Reference — Header Enricher](https://docs.spring.io/spring-integration/reference/content-enrichment.html): enrichment EIP.
- [Spring Integration Reference — Header Filter](https://docs.spring.io/spring-integration/reference/header-filter.html): filter sensitive headers.

## Conclusion

**HeaderMapper for inbound messages** is the strategy for converting external protocol metadata into **Spring `MessageHeaders`**. For `HeaderMapper<T>`, **`toHeaders(externalSource)` is the inbound direction**; `fromHeaders(...)` is used for the outbound or reply direction. HTTP uses `DefaultHttpHeaderMapper`, JMS uses `DefaultJmsHeaderMapper`, AMQP uses `DefaultAmqpHeaderMapper`; Kafka has its own header mappers in Spring Kafka. File/SFTP/IP typically have adapter-generated protocol headers that are normalized afterward using `HeaderEnricher`/Transformer.

In **SPRING_INTEGRATION_ADAPTERS**, doing this right is not “copying as many headers as possible”, but **allowlisting, type/casing/multi-value validation, separating trusted and untrusted data, distinguishing message/correlation/business IDs, protecting tenant/reply routing, testing mappers and real adapters, tying errors/ACKs to the right stage, and keeping business IDs stable across retries**. **Successful header mapping does not mean the source is authenticated, the payload is valid, the broker has ACKed, or the business operation has committed.**
