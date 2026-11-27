# HeaderMapper for Outbound Messages in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Explain **outbound header mapping**: transferring metadata from Spring `MessageHeaders` into HTTP request headers, JMS headers/properties, AMQP `MessageProperties`, or Kafka record headers when a message leaves Spring Integration.
- Recall the exact **direction of `HeaderMapper<T>`**: `fromHeaders(MessageHeaders source, T target)` is outbound, while `toHeaders(T source)` is inbound. In particular, an **outbound gateway** may need *both* directions: from Spring headers to the request and from response headers back to the Spring message.
- Distinguish header mapping from payload conversion, endpoint routing, HTTP/JMS/AMQP/Kafka QoS, write acknowledgements, and downstream business commits.
- Configure `DefaultHttpHeaderMapper.outboundMapper()`, `setOutboundHeaderNames(...)`, HTTP Java DSL `headerMapper(...)` or `mappedRequestHeaders(...)`, and XML `mapped-request-headers`.
- Use `DefaultJmsHeaderMapper` in a JMS outbound adapter, choose valid custom JMS properties, and understand `JMSCorrelationID`, TTL, priority, delivery mode, and the role of `JmsTemplate`.
- Configure `DefaultAmqpHeaderMapper` and `setRequestHeaderNames(...)` for AMQP outbound, avoiding re-sending `x-*` broker-internal headers or metadata from a previous delivery.
- Distinguish **Spring for Apache Kafka**'s `KafkaHeaderMapper` from Spring Integration's `HeaderMapper<T>` interface; control wire-format `byte[]`, JSON type hints, Kafka record topic/key, and multi-value headers.
- Recognize that File/SFTP/FTP, TCP/UDP, MongoDB, and SMTP/WebSocket have **protocol-specific outbound fields/headers**, and not every adapter has a generic `HeaderMapper`.
- Design policies for **outbound allowlisting, type validation, secret minimization, correlation/idempotency contracts, per-destination mapping, and preventing internal leaks**.
- Build unit tests for mappers, integration tests for HTTP/broker endpoints, and handle retries/ACKs/error channels/connection lifecycles.

This lesson belongs to the **Message Headers** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module's scope is connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database integrations; and handling message contracts, errors, and connection lifecycles. For outbound flows, the challenge is not just “sending headers”, but **selecting the right metadata to send to the right system, with the right types and the right ACK contract**.

> **Version Scope:** examples are based on Java 17+, Spring Boot 3.x, Spring Integration 6.x, and Spring Data/Spring Kafka managed by the application's BOM. With Spring Integration 7.x or Spring Kafka 4.x, some API names, defaults, and mapper implementations may change. Check the exact Javadoc for your version before deploying to production. URIs/brokers in the examples are lab environments and contain no production credentials.

## 1. Problem Statement: One Spring Message Sent to Three Systems

Suppose an upstream HTTP/Kafka/JMS source sends an order event into Spring Integration. After validation, the message looks like:

~~~text
Message<String>
  payload = {"eventId":"evt-1001","orderId":"ord-101","status":"PAID"}
  headers:
    businessEventId  = "evt-1001"
    appTraceId       = "trace-5e1"
    trustedTenantId  = "tenant-a"
    sourceSystem     = "order-service"
    internalRole     = "ROLE_OPERATOR"
    replyChannel     = <Spring MessageChannel object>
    id               = <Spring Message UUID>
    timestamp        = <Spring timestamp>
~~~

The application wants to:

1. Send an HTTP POST to a partner API with `Content-Type` and `X-Event-Id`.
2. Send a JMS message to a legacy consumer with the JMS string property `businessEventId`.
3. Send a Kafka record keyed by `orderId` with a custom header `businessEventId`.

**You must never copy all Spring headers verbatim** across all three protocols. For example, `replyChannel` of type `MessageChannel` cannot be HTTP/JMS/Kafka wire metadata; `internalRole` and `trustedTenantId` can leak data/privileges; Kafka offset/AMQP `deliveryTag` make no sense on the target system.

~~~mermaid
flowchart LR
    M["Spring Message<br/>payload + app headers"] --> V["Validate + allowlist"]
    V --> R["Route by trusted destination"]
    R --> HTTP["HTTP HeaderMapper<br/>Spring → HttpHeaders"]
    R --> JMS["JmsHeaderMapper<br/>Spring → JMS"]
    R --> AMQP["AmqpHeaderMapper<br/>Spring → MessageProperties"]
    R --> K["KafkaHeaderMapper<br/>Spring → Kafka Headers"]
    HTTP --> H["Partner HTTP API"]
    JMS --> J["JMS Broker"]
    AMQP --> A["RabbitMQ"]
    K --> B["Kafka Broker"]
~~~

**One source message, multiple outbound contracts.** Here, `HeaderMapper` is the component that selects and transfers *metadata*; it does not perform JSON payload encoding, destination selection, or cross-system transaction commits.

## 2. HeaderMapper<T>: API and Outbound Direction

Spring Integration defines:

~~~java
package org.springframework.integration.mapping;

import java.util.Map;
import org.springframework.messaging.MessageHeaders;

public interface HeaderMapper<T> {

    void fromHeaders(MessageHeaders headers, T target);

    Map<String, Object> toHeaders(T source);
}
~~~

| Method | Source | Target | When Is It Used? |
|---|---|---|---|
| **`fromHeaders(headers, target)`** | Spring `MessageHeaders` | HTTP `HttpHeaders` / JMS message / AMQP properties | **Outbound** Spring → external |
| **`toHeaders(source)`** | External metadata | `Map<String,Object>` to create Spring headers | **Inbound** external → Spring |
| `MessageConverter` | Spring payload | JSON, JMS TextMessage, AMQP body, Kafka bytes... | Payload conversion |
| Destination expression | Spring Message / config | URI, queue, exchange/routing key, Kafka topic... | Choosing where to send |
| Endpoint handler | Spring Message | I/O operation | Sending and handling transport errors/ACK |

**Rule of thumb:** `fromHeaders` = *take headers from the Spring Message and put them onto the external object*. It does not do the reverse.

### 2.1. A Pure Mapper Example

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

DefaultHttpHeaderMapper mapper =
        DefaultHttpHeaderMapper.outboundMapper();

mapper.setOutboundHeaderNames(
    "Content-Type", "X-Event-Id", "X-Trace-Id");

Message<String> message =
    MessageBuilder.withPayload("{\"orderId\":\"ord-101\"}")
        .setHeader("X-Event-Id", "evt-1001")
        .setHeader("X-Trace-Id", "trace-5e1")
        .setHeader("internalRole", "ROLE_OPERATOR")
        .build();

HttpHeaders target = new HttpHeaders();
mapper.fromHeaders(message.getHeaders(), target);

// target contains only the approved HTTP headers;
// internalRole is not mapped because it is not in the allowlist.
~~~

This is an example of **mapping**; it makes no HTTP call and does not prove network delivery succeeded.

### 2.2. An “Outbound Gateway” Uses Both Directions

An HTTP **outbound channel adapter** sends a request and returns no Spring reply message. An HTTP **outbound gateway** sends a request and receives a response:

~~~mermaid
sequenceDiagram
    participant F as Spring Integration flow
    participant HM as HeaderMapper
    participant HTTP as HTTP server
    F->>HM: fromHeaders(Spring MessageHeaders, HttpHeaders)
    HM-->>F: outgoing request headers
    F->>HTTP: HTTP request (body + headers)
    HTTP-->>F: HTTP response (status + response headers + body)
    F->>HM: toHeaders(HttpHeaders response)
    HM-->>F: inbound Spring response headers
    Note over F: Response payload is handled by message converter
~~~

Therefore, **`DefaultHttpHeaderMapper.outboundMapper()`** can simultaneously configure **`outboundHeaderNames` for the request** and **`inboundHeaderNames` for the response**. Do not confuse inbound/outbound here with the direction of the entire endpoint.

## 3. Which Headers Should and Should Not Be Exported?

| Group | Example Spring Header | Outbound Policy |
|---|---|---|
| Business ID | `businessEventId` | Map if the partner contract needs idempotency |
| Tracing | `appTraceId`, trace context | Map per W3C/partner tracing format, validate |
| Content metadata | `contentType`, `schemaVersion` | Map/convert per protocol, do not cast blindly |
| Tenant | `trustedTenantId` | Send only if downstream is authorized; typically translate to a partner-scoped identifier |
| Spring core | `id`, `timestamp` | Do not treat as a business ID; typically omit |
| Spring routing | `replyChannel`, `errorChannel` | **Never send** to external systems |
| Internal security | `internalRole`, internal JWT, API token | **Never copy**; generate separate outbound authentication |
| HTTP request metadata | `http_requestMethod`, `http_requestUrl` | Do not blindly re-map into partner requests |
| Kafka received metadata | received topic/partition/offset/ack object | Do not copy as arbitrary Kafka/JMS headers |
| AMQP received metadata | deliveryTag, receivedExchange, receivedRoutingKey | Do not reuse as outbound QoS |
| JMS received metadata | JMSMessageID, redelivered, expiration | Do not reuse provider-managed fields |
| File/SFTP source metadata | remote file/directory | Use only for authorized routing, do not auto-forward |
| Retry counters | `deliveryAttempt`, custom retry metadata | Export only if the business contract actually requires it |

### 3.1. Mapping, Enrichment, and Filtering

There are three distinct layers:

- **HeaderEnricher** (in-flow): adds/canonicalizes application headers.
- **HeaderFilter** (in-flow): removes internal/untrusted headers.
- **HeaderMapper** (at outbound adapter/gateway): maps **allowed** headers to the target protocol.

A resilient flow typically uses all three, without copying the exact same set of headers to every destination.

### 3.2. Spring Message ID Is Not eventId

Spring `MessageHeaders.ID` can change when rebuilding a message, on redelivery, or across systems. Kafka record keys, `JMSMessageID`, AMQP `messageId`, and HTTP `X-Request-Id` also have different scopes/generation rules. When deduplication is needed, maintain a **stable business event ID** with tenant/source scope across all retries.

## 4. HTTP Outbound: DefaultHttpHeaderMapper

Class:

~~~java
org.springframework.integration.http.support.DefaultHttpHeaderMapper
~~~

Factories:

~~~java
DefaultHttpHeaderMapper.outboundMapper();
DefaultHttpHeaderMapper.inboundMapper();
~~~

For an **HTTP outbound adapter/gateway**, use **`outboundMapper()`**.

### 4.1. Both Directions in an HTTP Outbound Gateway

| API | Meaning for an HTTP Outbound Gateway |
|---|---|
| `outboundMapper()` | Factory for HTTP outbound endpoints |
| `setOutboundHeaderNames(...)` | **Spring request headers → HTTP request headers** |
| `setInboundHeaderNames(...)` | **HTTP response headers → Spring reply headers** |
| `fromHeaders(MessageHeaders, HttpHeaders)` | Builds HTTP request metadata |
| `toHeaders(HttpHeaders response)` | Reads HTTP response metadata |
| `HTTP_REQUEST_HEADERS` | Pattern token for standard HTTP request fields |
| `HTTP_RESPONSE_HEADERS` | Pattern token for standard HTTP response fields |

Do not call `setInboundHeaderNames("X-Event-Id")` expecting the HTTP request to send `X-Event-Id`: that property controls **headers received from the response**, not outgoing request headers.

### 4.2. Request and Response Allowlist Bean

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
public class PartnerHttpMapperConfig {

    @Bean("partnerHttpHeaderMapper")
    public DefaultHttpHeaderMapper partnerHttpHeaderMapper() {

        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.outboundMapper();

        mapper.setOutboundHeaderNames(
            "Content-Type",
            "Accept",
            "X-Event-Id",
            "X-Trace-Id");

        mapper.setInboundHeaderNames(
            "Content-Type",
            "X-Partner-Request-Id");

        return mapper;
    }
}
~~~

- An explicit allowlist **overrides the default list**. If you need the full set of standard headers, use the tokens `HTTP_REQUEST_HEADERS`/`HTTP_RESPONSE_HEADERS` or list the exact names required.
- The mapper is not the place to generate/refresh OAuth access tokens; outbound tokens should be attached by a security-aware client component from a trusted source, never mirroring raw inbound `Authorization`.
- HTTP header names are **case-insensitive**, whereas Spring `MessageHeaders` key lookups follow Java map/mapper rules. Use canonical names and test casing.
- HTTP headers can be multi-valued; do not blindly cast every value to `String`.

### 4.3. Java DSL: HTTP Outbound Gateway

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
@EnableIntegration
public class PartnerHttpOutboundFlow {

    @Bean
    public IntegrationFlow partnerHttpOutbound(
            DefaultHttpHeaderMapper partnerHttpHeaderMapper) {

        return IntegrationFlow.from("sendToPartner")
            .handle(Http.outboundGateway(
                    "http://localhost:8091/api/orders/events")
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(String.class)
                .headerMapper(partnerHttpHeaderMapper))
            .channel("partnerReplies")
            .get();
    }
}
~~~

Explanation:

1. `sendToPartner` receives a Spring Message whose payload and headers are already validated.
2. `Http.outboundGateway(...)` sends an HTTP request to the fixed lab URL.
3. `.headerMapper(...)` uses `fromHeaders(...)` to attach allowlisted request headers.
4. The body is serialized by the HTTP converter; `HeaderMapper` is not a JSON serializer.
5. The response comes back as a Spring Message; the mapper uses `toHeaders(...)` for selected response fields.
6. `partnerReplies` needs a downstream consumer; otherwise the flow may fail to dispatch depending on channel topology.
7. This is a **request/reply** gateway; if you only need a one-way send, use `Http.outboundChannelAdapter(...)`.

**Never pass a URL from a raw user request header into an outbound expression**: it can cause SSRF. Use server-configured URL/host allowlists and verify TLS/timeouts.

### 4.4. DSL mappedRequestHeaders Without a Custom Mapper Bean

You can use a simple DSL configuration:

~~~java
Http.outboundGateway("http://localhost:8091/api/orders/events")
    .httpMethod(HttpMethod.POST)
    .mappedRequestHeaders(
        "HTTP_REQUEST_HEADERS",
        "X-Event-Id",
        "X-Trace-Id")
    .mappedResponseHeaders(
        "X-Partner-Request-Id",
        "HTTP_RESPONSE_HEADERS");
~~~

This is a **builder fragment**, which must be attached to `IntegrationFlow.handle(...)`. For complex custom rules, choose `.headerMapper(partnerHttpHeaderMapper)` **instead of simultaneously** configuring mapped lists and a custom mapper when the API does not define clear precedence.

### 4.5. XML Outbound Adapter/Gateway

~~~xml
<!-- Requires namespaces int, int-http; bean partnerHttpHeaderMapper
     and channels must exist. -->
<int-http:outbound-gateway
    id="partnerHttpGateway"
    url="http://localhost:8091/api/orders/events"
    http-method="POST"
    request-channel="sendToPartner"
    reply-channel="partnerReplies"
    header-mapper="partnerHttpHeaderMapper"/>
~~~

Or a one-way XML outbound adapter without replies:

~~~xml
<int-http:outbound-channel-adapter
    id="partnerHttpFireAndForget"
    url="http://localhost:8091/api/orders/events"
    http-method="POST"
    channel="sendToPartner"
    mapped-request-headers="Content-Type,X-Event-Id,X-Trace-Id"/>
~~~

These are **two independent alternatives**: do not register both on the same outgoing channel unless you intentionally want multicast/competing consumers. An HTTP “one-way” adapter does not mean the client call proves the downstream DB transaction finished; HTTP response status and business ACK have two different meanings.

### 4.6. Testing fromHeaders Without Network Calls

~~~java
package example.headersout;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class HttpOutboundMapperTest {

    @Test
    void onlyApprovedHeadersLeaveService() {
        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.outboundMapper();

        mapper.setOutboundHeaderNames(
            "X-Event-Id", "X-Trace-Id");

        Message<String> source =
            MessageBuilder.withPayload("hello")
                .setHeader("X-Event-Id", "evt-1001")
                .setHeader("X-Trace-Id", "trace-5e1")
                .setHeader("internalRole", "admin")
                .setHeader("Authorization", "internal-secret")
                .build();

        HttpHeaders requestHeaders = new HttpHeaders();
        mapper.fromHeaders(source.getHeaders(), requestHeaders);

        assertEquals(
            "evt-1001",
            requestHeaders.getFirst("X-Event-Id"));

        assertEquals(
            "trace-5e1",
            requestHeaders.getFirst("X-Trace-Id"));

        assertFalse(requestHeaders.containsKey("internalRole"));
        assertFalse(requestHeaders.containsKey("Authorization"));
    }
}
~~~

This is a **policy unit test**; it does not yet verify that the real HTTP gateway uses this mapper bean. Integration tests need a mock HTTP server and must capture the actual request (including header names, values, body, and timeout).
## 5. HTTP Authentication, Tracing, and Response Headers

### 5.1. Do Not Copy Raw Inbound Authorization

If an HTTP inbound request contains:

~~~http
Authorization: Bearer external-client-token
X-Partner-Event-Id: evt-1001
~~~

do not let an **outbound HTTP** mapper automatically forward that same `Authorization` to another partner. The source token has the caller's **audience, scope, tenant, and expiration**, not the service's credentials for calling downstream.

Better policy:

1. HTTP ingress validates the source token and tenant.
2. The business flow carries **minimal verified identity**, not the raw secret.
3. The outbound HTTP client obtains a token **scoped to the target audience** from a credential provider/authorized client.
4. `HeaderMapper` only exports allowed metadata, or a client interceptor sets the new `Authorization`.
5. Never log/trace raw tokens; test that no source token ever reaches the target server.

When using `RestTemplate`/Spring `WebClient` with an HTTP outbound gateway, choose a client security interceptor/filter appropriate for your stack and version; do not fetch access tokens directly inside `HeaderMapper.fromHeaders` if it requires network I/O, because mappers must be deterministic/bounded.

### 5.2. Correlation and W3C Trace Context

Suppose the application has `appTraceId` and wants partners to see W3C-standard `traceparent`. **Do not just rename** `appTraceId` to `traceparent`: the W3C format has version, trace-id, parent-id, and trace-flags. Use the official Spring Observability/OpenTelemetry tracing instrumentation/propagator whenever possible.

When you must map a custom header:

~~~java
Message<?> outbound = MessageBuilder.fromMessage(inbound)
    .setHeader("X-Event-Id", verifiedEventId)
    .setHeader("X-Trace-Id", validatedTraceHint)
    .removeHeader("X-External-Tenant-Role")
    .build();
~~~

This fragment requires `verifiedEventId` to be bound to the payload and tenant; `validatedTraceHint` has controlled size/charset. Even if the HTTP server returns 2xx, that **does not prove downstream Kafka/JMS committed** if the HTTP API is async.

### 5.3. Reading Response Headers in an Outbound Gateway

After an HTTP outbound request, the gateway can populate the Spring reply from:

~~~text
HTTP/1.1 202 Accepted
X-Partner-Request-Id: r-889
Retry-After: 4
Content-Type: application/json
~~~

If configured with `mapper.setInboundHeaderNames("X-Partner-Request-Id","Retry-After","Content-Type")`, `toHeaders(HttpHeaders)` converts **HTTP response metadata → Spring reply headers**.

**Notes:**

- Status 202 means the server **accepted the request**, not necessarily that the business effect is complete.
- `Retry-After` can inform a retry policy, but it must be parsed/validated and capped; never blindly sleep for a duration from an untrusted header.
- Reply message headers may also contain the HTTP status code/additional platform metadata outside the mapper.
- Never choose a routing/reply channel directly from an untrusted HTTP response header.

### 5.4. Mapping Does Not Make the Request Body Schema-Valid

HTTP `Content-Type: application/json` does not by itself turn a `String` payload into a valid DTO. The HTTP message converter handles the body; business validation handles the schema; the mapper handles headers. If the upstream payload is raw file bytes while `Content-Type` says JSON, the request may be rejected or misinterpreted downstream. Test both **headers and body at the wire level**.

## 6. JMS Outbound: DefaultJmsHeaderMapper

Key classes and dependencies in Spring Integration 6.x:

~~~java
org.springframework.integration.jms.DefaultJmsHeaderMapper
org.springframework.integration.jms.JmsHeaderMapper
org.springframework.integration.jms.JmsHeaders
org.springframework.integration.jms.outbound.JmsSendingMessageHandler
org.springframework.integration.jms.dsl.Jms
jakarta.jms.ConnectionFactory
jakarta.jms.Message
~~~

`DefaultJmsHeaderMapper` maps Spring `MessageHeaders` to standard JMS headers and custom JMS properties **when supported**. Some JMS fields are set by the provider or producer send API, so they cannot be “arbitrarily assigned” via a property mapper.

### 6.1. JMS Headers Table

| Spring Header | JMS Metadata | Outbound Rule |
|---|---|---|
| `JmsHeaders.CORRELATION_ID` / `jms_correlationId` | `JMSCorrelationID` | Used for request/reply, proper String format |
| `correlationId` | Custom JMS property (String) per mapper | Different from `JMSCorrelationID`; typically for aggregators |
| `JmsHeaders.TYPE` / `jms_type` | `JMSType` | Only when partner uses a type contract |
| `JmsHeaders.REPLY_TO` / `jms_replyTo` | `JMSReplyTo` | Valid JMS `Destination`; do not trust arbitrary input |
| `businessEventId` | Custom JMS String property | Business idempotency |
| `appTraceId` | Custom JMS String property | Tracing |
| `priority` | JMS producer send QoS | Do not expect the mapper alone to decide `JMSPriority` |
| `jms_deliveryMode` | JMS producer QoS | Must use `JmsTemplate`/endpoint QoS |
| `jms_expiration` | Expiration/TTL semantics | TTL is computed at send time; do not copy an old expiry |
| `jms_messageId` | `JMSMessageID` assigned by provider | Do not set it to Spring Message ID |
| `jms_redelivered` | `JMSRedelivered` managed by provider | Do not carry over from received messages to fake redelivery |

### 6.2. Why Priority, TTL, and Delivery Mode Differ from Regular JMS Properties

Spring Integration `JmsSendingMessageHandler` uses `JmsTemplate`/`DynamicJmsTemplate` and the JMS producer send API to apply QoS; fields like `JMSPriority`/deliveryMode/expiration are calculated and set by the broker/provider at **send time**.

An XML example from the Spring Integration JMS docs shows:

~~~xml
<int-jms:outbound-channel-adapter
    id="jmsOut"
    channel="outgoingJms"
    destination-name="orders.out"
    delivery-mode-expression="headers.jms_deliveryMode"
    time-to-live-expression="headers.jms_expiration - T(System).currentTimeMillis()"/>
~~~

This is an illustrative fragment; the TTL expression can be negative once a message expires, so **production must clamp TTL to an allowed range** and account for clock skew. When using dynamic JMS QoS, `explicitQosEnabled` must be enabled on `JmsTemplate`/producer as appropriately configured.

Do not take an old `JMSExpiration` from an inbound message, forward the raw number as a property into outbound JMS, and expect the broker to interpret it as a new expiry.

### 6.3. Java DSL JMS Outbound Adapter

~~~java
package example.headersout;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class JmsOrderOutboundConfig {

    @Bean
    public DefaultJmsHeaderMapper jmsOutboundHeaderMapper() {
        return new DefaultJmsHeaderMapper();
    }

    @Bean
    public IntegrationFlow jmsOrdersOut(
            ConnectionFactory connectionFactory,
            DefaultJmsHeaderMapper jmsOutboundHeaderMapper) {

        return IntegrationFlow.from("sendToJms")
            .handle(Jms.outboundAdapter(connectionFactory)
                .destination("orders.events")
                .headerMapper(jmsOutboundHeaderMapper))
            .get();
    }
}
~~~

Explanation:

1. `sendToJms` is the Spring input `MessageChannel`.
2. `Jms.outboundAdapter(...)` creates a one-way JMS sending handler.
3. `.headerMapper(...)` uses `fromHeaders(...)` to set JMS-compatible headers/properties.
4. `MessageConverter` converts the payload into a JMS `TextMessage`/`BytesMessage`/corresponding type; **do not** expect `HeaderMapper` to serialize the payload.
5. `ConnectionFactory`, destination, producer credentials, timeout, transaction, and broker ACK must be configured separately.
6. Do not assume `send()==true` on an upstream async `QueueChannel` proves broker receipt/commit.

In production, consider **building a clean outbound message** before the adapter so the mapper never encounters arbitrary object headers from other inbound sources.

### 6.4. Sending a Business Event with JMS-Friendly Property Types

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> orderEvent =
    MessageBuilder.withPayload(
            "{\"eventId\":\"evt-1001\",\"status\":\"PAID\"}")
        .setHeader("businessEventId", "evt-1001")
        .setHeader("appTraceId", "trace-5e1")
        .setHeader("schemaVersion", "1")
        .build();
~~~

Provider-supported JMS property types include primitives/wrappers/`String` per the JMS specification; a `Map<String,Object>`, `MessageChannel`, `Instant`, `BigDecimal`, or Kafka acknowledgment object **is not automatically a valid JMS property**. Convert them to `String`/primitives per schema or filter them out.

### 6.5. JMS Correlation Differs from Application Correlation

When using an outbound **JMS gateway** for request/reply, `JMSCorrelationID` may be generated/managed by the gateway to match replies. Putting `jms_correlationId` into `MessageHeaders` can alter behavior depending on `correlation-key` and configuration. Do not overwrite the correlation property on every request just to carry `appTraceId`.

- Put the business event ID in `businessEventId` for deduplication.
- Put the tracing ID in `appTraceId`.
- Let the JMS gateway manage request/reply correlation per its configured contract.
- When you genuinely need an app-supplied `JMSCorrelationID`, enable the matching configuration and test with the JMS broker/provider.

### 6.6. JMS XML Outbound Adapter

~~~xml
<!-- Requires int-jms namespace, ConnectionFactory and destination. -->
<int-jms:outbound-channel-adapter
    id="outJms"
    channel="sendToJms"
    connection-factory="jmsConnectionFactory"
    destination-name="orders.events"
    header-mapper="jmsOutboundHeaderMapper"/>
~~~

This is an alternative configuration to Java DSL; do not register both on the same consumer channel unless you intentionally want competing consumers or broadcast.

### 6.7. JMS One-Way vs. Gateway

| Endpoint | Function | HeaderMapper |
|---|---|---|
| JMS outbound channel adapter | Sends a message, usually with no reply message | Spring → JMS via `fromHeaders(...)` |
| JMS outbound gateway | Sends a request and awaits/receives a JMS reply | Both `fromHeaders(...)` on send and `toHeaders(...)` on reply |
| JMS inbound gateway | Receives a JMS request and returns a JMS reply | Reversed per request/reply direction |
| JMS message-driven inbound adapter | Receives a JMS message | JMS → Spring via `toHeaders(...)` |

`HeaderMapper` does **not** replace `JmsTemplate`/session transactions or broker ACK. You must test the message listener, timeouts, redelivery, and reply correlation end-to-end.

## 7. AMQP Outbound: DefaultAmqpHeaderMapper and MessageProperties

AMQP/RabbitMQ stores metadata in `org.springframework.amqp.core.MessageProperties`, mapped from `MessageHeaders` by Spring Integration via:

~~~java
org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper
org.springframework.integration.amqp.support.AmqpHeaderMapper
org.springframework.amqp.core.MessageProperties
org.springframework.amqp.support.AmqpHeaders
~~~

### 7.1. What Do Request Headers Mean in AMQP Outbound?

`DefaultAmqpHeaderMapper` has two common policy sets:

- **`requestHeaderNames`**: maps **Spring `MessageHeaders` ↔ AMQP request metadata**, including outbound adapter/gateway requests.
- **`replyHeaderNames`**: maps in the reply direction when using an AMQP gateway.

For a **one-way** AMQP outbound adapter, focus on **`setRequestHeaderNames(...)`** to allow the custom headers you intentionally send.

Example table:

| Spring Header | AMQP Field/Properties | What to Watch For |
|---|---|---|
| `contentType` | `MessageProperties.contentType` | Does not use `amqp_` prefix |
| `amqp_messageId` | AMQP messageId | Producer/application ID per policy |
| `amqp_correlationId` | AMQP correlationId | Request/reply, not automatically a business event ID |
| `businessEventId` | Custom AMQP header | Should be a valid stable String/bytes |
| `appTraceId` | Custom AMQP header | Verify charset/length |
| `amqp_receivedExchange` | Inbound broker metadata | **Do not export verbatim** as the new exchange |
| `amqp_receivedRoutingKey` | Inbound received routing | Outbound routing must be decided by the endpoint |
| `amqp_deliveryTag` | Delivery tag of the previous receive | **Do not forward** onto a new delivery |
| `amqp_redelivered` | Received flag | A producer must not “re-set” it to fake redelivery |
| `x-received-from` | RabbitMQ federation metadata | **Do not copy** when sending/replying |

### 7.2. Configuring an Outbound Allowlist

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

@Configuration
public class PartnerAmqpMapperConfig {

    @Bean
    public DefaultAmqpHeaderMapper outboundAmqpHeaderMapper() {
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

**Version note:** the Spring Integration reference and some older Javadocs differ in describing **default mapping of custom AMQP headers**; the modern reference states many custom properties are copied automatically while excluding `x-*` by default on outbound, whereas some versions' Javadocs mention only standard fields. **Do not rely on ambiguous defaults:** specify an allowlist and test against your exact artifacts/version.

When using the `STANDARD_REQUEST_HEADERS` pattern, you preserve valid standard AMQP fields per the mapper; other headers should not be exported unless listed. Negated patterns like `!x-*` take precedence and block broker-internal metadata.

### 7.3. Java DSL AMQP Outbound Adapter

~~~java
package example.headersout;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class RabbitOutboundConfig {

    @Bean
    public IntegrationFlow orderEventsToRabbit(
            RabbitTemplate rabbitTemplate,
            DefaultAmqpHeaderMapper outboundAmqpHeaderMapper) {

        return IntegrationFlow.from("sendToRabbit")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName("partner.events")
                .routingKey("orders.paid")
                .headerMapper(outboundAmqpHeaderMapper))
            .get();
    }
}
~~~

- The exchange/routing key in the demo are **trusted application configuration**, not raw inbound headers.
- `HeaderMapper` copies allowed standard/custom metadata into `MessageProperties`.
- The payload/body is handled by the Spring AMQP `MessageConverter`.
- Broker exchange/queue/binding, connections/credentials, and publisher confirm/return policies must be configured separately.
- For dynamic routing, use `routingKeyExpression` or `routingKeyFunction` **on a validated/allowlisted header**, never an arbitrary client-supplied exchange name.

### 7.4. Unit Test from Spring Headers to AMQP Properties

~~~java
package example.headersout;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class AmqpOutboundMapperTest {

    @Test
    void exportsApprovedBusinessMetadataOnly() {
        DefaultAmqpHeaderMapper mapper =
                new DefaultAmqpHeaderMapper();

        mapper.setRequestHeaderNames(
            "STANDARD_REQUEST_HEADERS",
            "businessEventId",
            "!x-*");

        Message<String> message =
            MessageBuilder.withPayload("hello")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("x-received-from", "internal-broker")
                .setHeader("internalRole", "admin")
                .build();

        MessageProperties target = new MessageProperties();
        mapper.fromHeaders(message.getHeaders(), target);

        assertEquals(
            "evt-1001",
            target.getHeaders().get("businessEventId"));

        assertFalse(target.getHeaders()
            .containsKey("x-received-from"));

        assertFalse(target.getHeaders()
            .containsKey("internalRole"));
    }
}
~~~

If this test fails because a specific version uses different tokens/naming rules, check the Javadoc rather than loosening the policy to `*` to make the test pass.

### 7.5. AMQP Publisher Confirms and Returns Differ from Mapping

Sending to RabbitMQ involves multiple checkpoints:

1. The Spring Integration handler accepts/transforms the message.
2. `RabbitTemplate` sends the AMQP message to the broker.
3. The broker may send a **publisher confirm** ACK/NACK if enabled on the connection/channel.
4. The message may be **returned** if unroutable and mandatory/return callbacks are configured.
5. A consumer may receive/redeliver/ACK later.

**Successfully mapping `MessageHeaders` does not prove (3), (4), or (5).** The Spring Integration AMQP outbound adapter provides options such as `confirmAckChannel`, `confirmNackChannel`, `returnChannel`, and `waitForConfirm` depending on version/endpoint. Test positive, unroutable, and negative confirm cases.

### 7.6. Why Not Forward x-* from the Broker?

RabbitMQ federation can attach `x-received-from` or other broker-specific `x-*` headers. If an inbound AMQP message carries that metadata into an outbound/reply message, federation may mistake it for a message loop and drop it. Never use wildcard `*` indiscriminately across sources. If you need a plugin header like `x-delay`, **define a dedicated policy for that exact broker/plugin** and validate the TTL/delay; do not open up all `x-*`.

### 7.7. AMQP XML Outbound

~~~xml
<!-- Requires int-amqp namespace, RabbitTemplate, exchange, channels. -->
<int-amqp:outbound-channel-adapter
    id="rabbitOut"
    channel="sendToRabbit"
    amqp-template="rabbitTemplate"
    exchange-name="partner.events"
    routing-key="orders.paid"
    header-mapper="outboundAmqpHeaderMapper"/>
~~~

Another XML endpoint might use `mapped-request-headers` instead of `header-mapper`; the two can be mutually exclusive. Check the schema for your exact version and avoid configuring conflicting directions/mappers.
## 8. Kafka Outbound: KafkaHeaderMapper in Spring Kafka

A Kafka producer record consists of **topic, partition, key, timestamp, value, and headers**. Kafka wire-level headers are a collection of entries:

~~~java
package org.apache.kafka.common.header;

public interface Header {
    String key();
    byte[] value();
}
~~~

Spring Kafka provides a **different** interface from Spring Integration's generic `HeaderMapper`:

~~~java
package org.springframework.kafka.support;

import org.apache.kafka.common.header.Headers;
import org.springframework.messaging.MessageHeaders;
import java.util.Map;

public interface KafkaHeaderMapper {
    void fromHeaders(MessageHeaders headers, Headers target);
    void toHeaders(Headers source, Map<String, Object> target);
}
~~~

Here `fromHeaders(...)` is still outbound, but its **generic type and signature differ** from `org.springframework.integration.mapping.HeaderMapper<T>`. Never inject a `DefaultHttpHeaderMapper` into a Kafka producer converter.

### 8.1. Implementations and Version Differences

| Choice | Behavior | When to Choose? |
|---|---|---|
| `SimpleKafkaHeaderMapper` | Primarily maps raw header values as `byte[]`, supports raw String config | Contracts with non-Spring consumers, minimal type metadata |
| `DefaultKafkaHeaderMapper` (Spring Kafka 3.x) | JSON-serializes Java values and type hints | Both sides use Spring Kafka and want type round-tripping |
| `JsonKafkaHeaderMapper` (Spring Kafka 4.x docs) | Similar JSON mapping, adds versioned multi-value policy | Spring Kafka 4.x / complex typed headers with schema |
| Custom `KafkaHeaderMapper` | Full control over serialization/patterns | Legacy wire formats or special security requirements |

**Important:** classes like `DefaultKafkaHeaderMapper`/`JsonKafkaHeaderMapper` and their defaults can vary by Spring Kafka version. This lesson uses `SimpleKafkaHeaderMapper` for widely compatible raw-byte examples; check the Javadoc/BOM before renaming classes or enabling JSON typed headers.

### 8.2. Why Not Copy id/timestamp/received Metadata?

`KafkaHeaderMapper` typically excludes Spring `id`, `timestamp`, and Kafka headers representing **record metadata**, such as received topic/partition/offset. That metadata is managed by `ConsumerRecord`/`ProducerRecord` or the producer endpoint, not as arbitrary custom Kafka headers to forward.

| Spring Header | Kafka Record | Should It Be Mapped as a Custom Header? |
|---|---|---|
| `KafkaHeaders.TOPIC` | `ProducerRecord.topic` | No; it is destination control |
| `KafkaHeaders.KEY` | `ProducerRecord.key` | No; the key affects partitioning/ordering |
| `KafkaHeaders.PARTITION` | `ProducerRecord.partition` | No; explicit partitioning needs a policy |
| `KafkaHeaders.RECEIVED_TOPIC` | Metadata from source consumer | Do not carry over as a new topic |
| `KafkaHeaders.OFFSET` | Received Kafka offset | Do not turn into a business ID |
| `KafkaHeaders.ACKNOWLEDGMENT` | Listener ACK object | Do not serialize to the broker |
| `businessEventId` | Kafka custom header | Yes, in an agreed format |
| `schemaVersion` | Kafka custom header | Yes, as bytes/String/JSON with schema |
| `appTraceId` | Kafka custom header | Yes, if required by the tracing contract |

A Kafka record key can help with per-aggregate ordering, but **does not by itself guarantee deduplication across retries**: the application needs a business event ID and an idempotent consumer/outbox.

### 8.3. Raw Byte Policy with SimpleKafkaHeaderMapper

~~~java
package example.headersout;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class KafkaHeaderMappingDemo {

    public static RecordHeaders encodeEventId() {
        SimpleKafkaHeaderMapper mapper =
            new SimpleKafkaHeaderMapper(
                "businessEventId",
                "!id",
                "!timestamp");

        Message<byte[]> message =
            MessageBuilder.withPayload(new byte[] {1, 2, 3})
                .setHeader(
                    "businessEventId",
                    "evt-1001".getBytes(StandardCharsets.UTF_8))
                .setHeader("internalRole", "operator")
                .build();

        RecordHeaders kafkaHeaders = new RecordHeaders();
        mapper.fromHeaders(
            message.getHeaders(), kafkaHeaders);

        return kafkaHeaders;
    }
}
~~~

**Why use `byte[]`:** `SimpleKafkaHeaderMapper` primarily preserves raw bytes. In non-Spring consumers, decode as UTF-8 and validate length/charset/schema. If you pass a Java `String` directly with a JSON mapper, the wire representation may **not look like plain text bytes** and will include added type metadata.

### 8.4. Unit Testing Kafka Record Headers

~~~java
package example.headersout;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class KafkaOutboundMapperTest {

    @Test
    void onlyApprovedHeaderBecomesKafkaWireBytes() {
        RecordHeaders headers =
                KafkaHeaderMappingDemo.encodeEventId();

        assertArrayEquals(
            "evt-1001".getBytes(StandardCharsets.UTF_8),
            headers.lastHeader("businessEventId").value());

        assertNull(headers.lastHeader("internalRole"));
        assertNull(headers.lastHeader("id"));
    }
}
~~~

This is a **mapper unit test**; it sends no Kafka record and does not prove producer ACK. You need a Kafka broker test to verify topic/key/partition, wire bytes, headers, and retry/error channels under real configuration.

### 8.5. Configuring the Kafka Converter per Spring Kafka 3.x

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

MessagingMessageConverter converter =
        new MessagingMessageConverter();

converter.setHeaderMapper(
    new SimpleKafkaHeaderMapper(
        "businessEventId",
        "appTraceId",
        "!id",
        "!timestamp"));
~~~

**This is a fragment**; you must attach `converter` to the producer `KafkaTemplate`/handler per your version's API. The Kafka adapter handles outbound Spring `Message → ProducerRecord`, while `KafkaHeaderMapper` transfers **custom headers** into `RecordHeaders`.

If using `DefaultKafkaHeaderMapper` (Spring Kafka 3.x) or `JsonKafkaHeaderMapper` (Spring Kafka 4.x), restrict trusted classes/packages on the inbound side and remember header contents will be JSON-serialized; never let clients specify arbitrary classes.

### 8.6. Spring Integration Kafka Outbound Flow

Spring Integration Kafka provides the DSL `Kafka.outboundChannelAdapter(kafkaTemplate)`:

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.kafka.dsl.Kafka;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;

@Configuration
@EnableIntegration
public class KafkaOrderOutboundConfig {

    @Bean
    public IntegrationFlow kafkaOrderEvents(
            KafkaTemplate<String, String> kafkaTemplate) {

        return IntegrationFlow.from("sendToKafka")
            .enrichHeaders(h -> h
                .header(KafkaHeaders.TOPIC, "orders.events"))
            .handle(Kafka.outboundChannelAdapter(kafkaTemplate))
            .get();
    }
}
~~~

The application needs producer factory/serializers, Kafka brokers, ACLs, failure channels, and a `KafkaTemplate` converter with the policy above. The topic is set **server-side** via `HeaderEnricher`; the key/order ID must be derived from validated business state. **Never accept a raw `KafkaHeaders.TOPIC` from an untrusted client** allowing a producer to write to arbitrary topics.

### 8.7. Why Do Multi-Value Headers Need Separate Testing?

Kafka records allow multiple entries with the same key. Spring Kafka 4.x has opt-in multi-value header mapping with the JSON mapper; by default it may serialize a collection into a single header or expose only the last value on read. Spring Kafka 3.x behaves differently.

Example:

~~~text
Kafka Headers:
  tracing-hop: byte[]{A}
  tracing-hop: byte[]{B}
~~~

You cannot assume `MessageHeaders.get("tracing-hop")` returns `List<byte[]>` or that passing a `List` outbound produces 2 Kafka headers. When multiple values are needed:

1. Pick a version that supports it.
2. Configure multi-value header patterns.
3. Test the wire-level record for the exact entry count/key/order.
4. Check compatibility with non-Spring Kafka consumers.
5. Do not use multi-value for a business event ID if the contract requires a singleton.

### 8.8. Kafka Broker ACK Differs from Header Mapping

- Kafka producer `acks`, `retries`, and idempotence belong to producer configuration, not `KafkaHeaderMapper`.
- `send()==true` on a `QueueChannel` does not prove the Kafka record was ACKed by the broker.
- The Spring Integration Kafka outbound handler supports sync/async modes and success/failure channels; the application must choose the matching ACK contract.
- A producer timeout can create an **unknown result**; retries keep the same `businessEventId`, and downstream deduplicates.
- Kafka producer idempotence reduces duplicates within producer protocol scope, but **does not replace idempotency across MongoDB/HTTP/JMS**.

## 9. File Outbound: FileHeaders.FILENAME and FileNameGenerator

The File adapter is an important example of **a header affecting an outbound operation without needing a generic `HeaderMapper`**. Spring Integration `FileWritingMessageHandler` uses `FileNameGenerator` to pick the filename.

Spring Integration provides:

~~~java
org.springframework.integration.file.FileHeaders
org.springframework.integration.file.DefaultFileNameGenerator
org.springframework.integration.file.FileWritingMessageHandler
~~~

### 9.1. Filename Contract

When writing files, the default file-name generator typically:

1. Uses Spring header `FileHeaders.FILENAME` if present and valid.
2. If the payload is `java.io.File`, may use the payload file's name.
3. Otherwise falls back to the Spring Message ID with `.msg`.

**Never rely on the Spring Message ID fallback when replay/idempotency is required**: after a restart or redelivery, a new ID can generate a different file for the same business event.

### 9.2. Normalizing Outbound Filenames

~~~java
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

String verifiedEventId = "evt-1001";

Message<String> document =
    MessageBuilder.withPayload(
            "{\"eventId\":\"evt-1001\",\"status\":\"PAID\"}")
        .setHeader(
            FileHeaders.FILENAME,
            verifiedEventId + ".json")
        .setHeader("businessEventId", verifiedEventId)
        .build();
~~~

**`verifiedEventId`** must have a charset/length free of slashes, backslashes, `..`, or control characters, and should come from the domain contract. When configuration allows filenames to be child paths, path traversal can happen if an unchecked header is used. Restrict filenames to a server-controlled root directory.

### 9.3. File Output Is Not HTTP/JMS Header Mapping

~~~text
Spring Message
  payload         = JSON bytes / String / File
  file_name       = evt-1001.json
      ↓
FileWritingMessageHandler / FileNameGenerator
      ↓
/var/app/outgoing/evt-1001.json
~~~

You do not need `DefaultHttpHeaderMapper` for local file writes. This header is an **input to the naming policy** of `FileWritingMessageHandler`; it is not written into the file body unless the app explicitly serializes it.

### 9.4. Overwrite, Append, and Temporary-File Strategy

A valid filename alone is not enough. If an event redelivers:

- `FileExistsMode.REPLACE` can overwrite the old file.
- `APPEND` can introduce duplicate data.
- `IGNORE` can skip a file whose old content does not match.
- `FAIL` fails the flow, requiring distinct duplicate handling.
- Temporary-file suffix/atomic rename (when supported by the adapter/FS) reduces the risk of a consumer reading an incomplete file.

Do not treat a file naming header as a transaction; you need a write-complete policy, checksum/reconciliation, and source/destination idempotency.

## 10. FTP/SFTP/SMB Outbound: Remote Paths Are Not Arbitrary Headers

Remote file outbound adapters usually use `FileNameGenerator`, `remoteDirectory`, or expressions to choose where to place a file; they can read Spring Message headers such as `FileHeaders.FILENAME`. This is **not** a generic cross-protocol `HeaderMapper<T>`.

### 10.1. Example of Allowlisted Per-Tenant Routing

~~~java
public String remoteDirectoryForTenant(String trustedTenantId) {
    return switch (trustedTenantId) {
        case "tenant-a" -> "/partners/a/inbox";
        case "tenant-b" -> "/partners/b/inbox";
        default -> throw new IllegalArgumentException(
            "Unauthorized outbound tenant");
    };
}
~~~

This is a service/helper, not a fully configured adapter. In Spring Integration DSL, wire this logic into `remoteDirectoryExpression`/function per version; use only a server-validated `trustedTenantId`, never a raw HTTP `X-Tenant-Id` or partner-supplied path.

### 10.2. Example of SFTP Header-Based Naming (Fragment)

~~~java
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;

// A filename generator can use:
String safeName = (String) message.getHeaders()
    .get(FileHeaders.FILENAME);

// Then validate the name and use it in the
// SFTP outbound adapter/FileNameGenerator config.
~~~

**Never use `REMOTE_DIRECTORY` from another SFTP inbound message as an outbound directory** without authorization. Remote paths can have different slash/backslash conventions, case sensitivity, and permission models. `SessionFactory` needs security/host-key verification, timeouts, and retries.

### 10.3. Transfer Completion, ACK, and Lifecycle

SFTP/FTP outbound is a stateful network operation:

1. Select remote path/filename.
2. Connect/authenticate.
3. Upload/write file, optionally using a temporary remote filename.
4. Rename/finalize.
5. Return result or exception.

A timeout can occur after the server received the file but before the client received the ACK. Retrying with the same filename can overwrite or conflict; verify size/checksum and define an idempotent destination policy rather than generating a new name on retry for the same event.

`FileHeaders` only helps specify filename/metadata; **it does not replace transactions/remote ACKs, host key verification, or a durable retry queue**.

## 11. TCP/UDP/IP Outbound: IpHeaders and Destination

Spring Integration IP provides `IpHeaders` for network metadata (source address/port, connection ID, packet address...). Some TCP/UDP outbound adapters or gateways can use headers/destination configuration to pick a host/port or connection, depending on the endpoint and connection factory.

### 11.1. Never Use Inbound Source IP as an Outbound Destination

Suppose a UDP inbound message has a source IP header. **Do not copy it verbatim** to let an outbound sender dispatch responses to any IP/port advertised by the client, especially on a public server. Risks: SSRF/UDP reflection, probing internal networks, or amplification.

Choose destinations from a server allowlist or authenticated connections, with rate limits and authorization checks.

### 11.2. TCP Connection IDs Have Their Own Lifecycle

TCP inbound can attach a connection ID for request/reply over an existing connection. It is not a globally unique business ID and becomes invalid when the connection closes or restarts. Use the appropriate connection factory/adapter API, and test reconnect/stale-connection handling. Never serialize a `TcpConnection` object into a Kafka/JMS header.

### 11.3. UDP Metadata Does Not Create Reliability

UDP does not guarantee delivery, ordering, retransmission, or sender authentication. Attaching `businessEventId` on outbound can help the app deduplicate if the payload protocol carries the ID, but it does not turn UDP into a guaranteed delivery protocol. Implement application-level ACKs/retries if the business actually requires them.

## 12. Database and MongoDB Outbound: Headers Do Not Automatically Become Columns/Documents

In **SPRING_INTEGRATION_ADAPTERS**, JDBC/MongoDB outbound handlers typically write the **payload** according to repository/template mappings. For example:

- A MongoDB storing handler persists a document from the payload via `MongoOperations`; the `businessEventId` header does not automatically become a BSON field.
- A JDBC outbound adapter can use SpEL expressions to bind header values as SQL parameters if the developer configures them; it does not dump all `MessageHeaders` into a row by default.
- Kafka/JMS/AMQP headers that need auditing must be **deliberately selected/serialized** into the payload/columns.

If a unique business key exists only in a Spring header and not in the DB payload, retries/redeliveries may not deduplicate properly. Before persisting, copy the verified ID into the domain model or SQL bindings per policy.

### 12.1. Example Before Writing to MongoDB

~~~java
public record AuditRecord(
    String id,
    String tenantId,
    String type,
    String payloadHash) {
}

// Fragment: build domain record from verified input
AuditRecord audit = new AuditRecord(
    verifiedEventId,
    authorizedTenantId,
    "ORDER_PAID",
    canonicalPayloadHash);
~~~

Do not assume `AuditRecord.id` has MongoDB `@Id` mapping unless annotated/configured in the schema; when using templates and unique keys, configure the mapping explicitly. This is an example of transferring business metadata into **domain data**, not a generic MongoDB `HeaderMapper`.
## 13. Custom Outbound HeaderMapper: Renaming and Validating Headers

`DefaultHttpHeaderMapper` fits when the Spring header and HTTP header **share the same name**. If Spring uses `businessEventId` while the partner expects `X-Event-Id`, you can:

- Use `HeaderEnricher` to add `X-Event-Id` before the mapper.
- Or implement `HeaderMapper<HttpHeaders>`, validating and renaming at the outbound boundary.

### 13.1. Implementing HeaderMapper<HttpHeaders>

~~~java
package example.headersout;

import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.integration.mapping.HeaderMapper;
import org.springframework.messaging.MessageHeaders;

public final class PartnerEventHeaderMapper
        implements HeaderMapper<HttpHeaders> {

    private static final Pattern EVENT =
            Pattern.compile("[A-Za-z0-9_-]{1,128}");
    private static final Pattern TRACE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public void fromHeaders(
            MessageHeaders spring,
            HttpHeaders request) {

        String eventId =
            spring.get("businessEventId", String.class);
        String traceId =
            spring.get("appTraceId", String.class);

        if (eventId == null ||
                !EVENT.matcher(eventId).matches()) {
            throw new IllegalArgumentException(
                "Invalid businessEventId");
        }

        request.set("X-Event-Id", eventId);

        if (traceId != null &&
                TRACE.matcher(traceId).matches()) {
            request.set("X-Trace-Id", traceId);
        }

        // Do not forward Authorization, internalRole,
        // replyChannel, errorChannel, or arbitrary metadata.
    }

    @Override
    public Map<String, Object> toHeaders(
            HttpHeaders response) {

        Map<String, Object> mapped = new HashMap<>();
        String requestId =
                response.getFirst("X-Partner-Request-Id");

        if (requestId != null &&
                TRACE.matcher(requestId).matches()) {
            mapped.put("partnerRequestId", requestId);
        }

        return mapped;
    }
}
~~~

**Key takeaways:**

1. `fromHeaders` takes Spring headers and builds request headers for the external system.
2. `toHeaders` is used when an HTTP outbound gateway receives an **HTTP response**, mapping only approved response metadata.
3. `businessEventId` is mandatory; if invalid, **fail fast before sending** rather than sending without an idempotency key.
4. The optional trace ID is dropped if invalid; if the partner requires a trace ID, you may choose to reject instead.
5. Never forward Spring reserved objects and secrets.
6. This example does not map `Content-Type/Accept` itself. If you need standard HTTP mappings, combine with `DefaultHttpHeaderMapper` or build a complete policy and test the message converter.
7. `getFirst` may ignore other multi-values. For critical correlation headers, reject conflicting multi-value cases.

### 13.2. Unit Testing the Custom Mapper

~~~java
package example.headersout;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class PartnerEventHeaderMapperTest {

    private final PartnerEventHeaderMapper mapper =
            new PartnerEventHeaderMapper();

    @Test
    void mapsOnlyApprovedBusinessFields() {
        Message<String> source =
            MessageBuilder.withPayload("event-data")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("appTraceId", "trace-5e1")
                .setHeader("Authorization", "do-not-send")
                .build();

        HttpHeaders request = new HttpHeaders();
        mapper.fromHeaders(source.getHeaders(), request);

        assertEquals(
            "evt-1001", request.getFirst("X-Event-Id"));
        assertEquals(
            "trace-5e1", request.getFirst("X-Trace-Id"));
        assertNull(request.getFirst("Authorization"));
    }

    @Test
    void invalidEventIdFailsBeforeSend() {
        Message<String> source =
            MessageBuilder.withPayload("payload")
                .setHeader("businessEventId", "../../bad")
                .build();

        assertThrows(
            IllegalArgumentException.class,
            () -> mapper.fromHeaders(
                source.getHeaders(), new HttpHeaders()));
    }

    @Test
    void mapsOnlyApprovedPartnerResponseId() {
        HttpHeaders response = new HttpHeaders();
        response.set("X-Partner-Request-Id", "r-889");
        response.set("Set-Cookie", "secret");

        Map<String, Object> mapped =
                mapper.toHeaders(response);

        assertEquals("r-889", mapped.get("partnerRequestId"));
        assertFalse(mapped.containsKey("Set-Cookie"));
    }
}
~~~

This is a **mapper unit test**; it does not prove the HTTP gateway injected this bean. Capture actual requests using an HTTP test server and test response mapping separately.

## 14. Per-Destination Outbound Policy: Allowlist Both Keys and Values

A business event may be sent to multiple targets, but each target has a **different wire contract and data-visibility permissions**:

| Destination | Headers to Send | Headers to Omit |
|---|---|---|
| Public Partner HTTP | `X-Event-Id`, `X-Trace-Id`, `Content-Type` | raw inbound `Authorization`, `internalRole`, `replyChannel` |
| Internal JMS Queue | `businessEventId`, `schemaVersion`, `appTraceId` | Kafka ACK/offset, HTTP cookies, AMQP `deliveryTag` |
| RabbitMQ Exchange | `businessEventId`, `appTraceId`, `contentType` | `receivedRoutingKey`, `receivedExchange`, `x-received-from` |
| Kafka Topic | `businessEventId` raw bytes, `schemaVersion` | Spring ID/timestamp, arbitrary objects, listener ACK |
| SFTP | sanitized filename, approved remote dir | user-controlled path, raw internal paths |
| MongoDB | verified `eventId` in domain object | Spring `MessageChannel` or HTTP `Authorization` in document |

### 14.1. There Is No Safe Generic All-Protocol Serializer

A helper that checks only the name:

~~~java
package example.headersout;

import java.util.Set;

public final class CommonOutboundPolicy {

    private static final Set<String> SAFE =
        Set.of(
            "businessEventId",
            "appTraceId",
            "schemaVersion");

    private CommonOutboundPolicy() {}

    public static boolean approved(String name) {
        return SAFE.contains(name);
    }
}
~~~

is not enough to serialize safely across all transports: Kafka needs byte encoding/JSON schemas; JMS property types are restricted; HTTP header values are textual/multi-valued; AMQP metadata has broker-specific fields. Apply a **destination-specific mapper**, validate size/type, and reject unsupported values.

### 14.2. Required vs. Optional and Multi-Value Handling

- `businessEventId` is usually required for idempotency: absent, blank, invalid length, or multi-value conflict → reject.
- `appTraceId` may be optional, but if sent it must match the format.
- `schemaVersion` must be in an allowed set, never an arbitrary Java class name.
- `Content-Type` must match the payload codec.
- `trustedTenantId` may be sent only if the destination is authorized; it can be mapped to a partner-scoped ID.
- Header names/values containing CR/LF/control chars → reject to prevent header injection.
- `replyChannel`, `errorChannel`, and `id`/`timestamp` must not be mirrored arbitrarily.
- Kafka topic, JMS destination, AMQP routing key, and SFTP remote path must come from **trusted route config**.

## 15. When Mapping Fails: Classify Errors Before Retrying

| Error Type | Example | Handling |
|---|---|---|
| Missing required header | No `businessEventId` | Reject/quarantine, do not send without ID |
| Invalid header | Event ID too long, CR/LF | Reject, fix producer/schema |
| Unsupported header type | JMS property contains `MessageChannel` | Filter/convert, do not retry repeatedly |
| Forbidden header | `X-Internal-Role` or inbound `Authorization` | Strip and raise security alert if anomalous |
| Unauthorized destination | User-chosen raw topic/URL/path | Reject, do not retry |
| Payload conversion error | JSON/JMS serializer cannot map | Fix schema, do not retry infinitely |
| Network/connection failure | HTTP timeout, JMS broker down | Retry with transport-appropriate budget |
| Ambiguous ACK | Target received it, response lost | Reconcile using the same business ID |
| Partner business rejection | HTTP 409/422, validation error | Distinguish conflict vs. permanent failure |
| AMQP returned message | Exchange accepted, could not route to queue | Recover via return channel |
| Kafka producer failure | Future/callback error | Keep event ID, retry/outbox if safe |

### 15.1. Do Not Swallow Errors on Required Metadata

~~~java
// BAD pattern: loses the idempotency key yet still sends.
try {
    validateBusinessEventId(message);
} catch (Exception ignored) {
    // Do nothing.
}
sendToPartner(message);
~~~

If downstream requires the ID for deduplication, a missing ID must cause a **controlled send failure**, never letting the mapper silently drop the value and send anyway. An optional trace can be dropped per policy; required vs. optional must be clearly separated.

### 15.2. Mapping Failures Differ from Transport Failures

- Mapping failures usually happen **before the network send** and are deterministic.
- Transport failures can occur **before or after the target receives the data**.
- A timeout does not prove the target failed to commit.
- A gateway reply business rejection differs from a broker negative publisher confirm.
- When an error flow only logs and returns, upstream may falsely ACK; define explicit error policies and durable recovery.

## 16. Sync/Async MessageChannels Change ACK Timing

### 16.1. DirectChannel

~~~text
Caller.send(Spring Message)
  -> DirectChannel
  -> mapper.fromHeaders()
  -> transport handler
  -> success/exception in caller stack
  -> send() returns
~~~

With synchronous handlers, mapping/conversion/transport exceptions can propagate on the caller thread. However, a Kafka producer or AMQP confirms may report results **asynchronously after the method returns**.

### 16.2. QueueChannel/ExecutorChannel

~~~text
Thread A:
  send(message) -> accepted into RAM queue -> return

Thread B:
  read queued message
  mapper.fromHeaders()
  network send / broker result
~~~

If the source HTTP/JMS/Kafka ACKs as soon as `QueueChannel` accepts the message into RAM, a crash can lose unsent events. Use a durable source, durable queue, or outbox, or defer ACK until the proper stage.

### 16.3. Reactive Flows

With `FluxMessageChannel` and reactive endpoints, creating a publisher does not mean I/O has executed; a publisher typically needs a subscription and terminal signal. Avoid fire-and-forget `subscribe()` inside handlers if the caller needs confirmation of delivery. `HeaderMapper` only builds metadata; it does not manage backpressure or subscriptions.

## 17. Outbound Retries, Idempotency, and Transaction Boundaries

An HTTP POST can succeed at the destination and then lose its response:

~~~mermaid
sequenceDiagram
    participant S as Spring Integration
    participant H as Partner API
    S->>H: POST eventId=evt-1001
    H->>H: commit event
    H--xS: response lost
    S->>H: retry same eventId=evt-1001
    H-->>S: ALREADY_ACCEPTED
~~~

If a retry creates a new `eventId`, downstream sees a brand-new event. Therefore:

1. Keep **`businessEventId` and payload** stable across retries.
2. Downstream compares the same ID against canonical content, flagging a conflict if they differ.
3. Separate permanent HTTP 4xx from transient 429/503/network errors.
4. Cap attempts, use exponential backoff + jitter, and apply deadlines/circuit breakers.
5. Never retry non-idempotent payment/write APIs without protocol deduplication.
6. Never retry mapping/schema errors as if they were network outages.
7. When the outcome is unknown, reconcile instead of assuming failure.
8. With brokers, distinguish a producer ACK from a consumer's business ACK.

### 17.1. Retry Layers Do Not Replace Each Other

| Layer | Retry | What to Watch For |
|---|---|---|
| HTTP client | HTTP 429/503/timeouts | `Idempotency-Key` and status-specific policy |
| JMS producer/session | Send exception/transaction | Broker receive/commit ACK per session |
| AMQP publisher | Confirm/NACK/return | Unroutable differs from publish failed |
| Kafka producer | Idempotent producer/retries | Application event ID is still needed for downstream dedup |
| SFTP upload | Reconnect/reupload | Same filename, checksum, and remote completion |
| MongoDB writer | Driver retryable writes | Unique business key and unknown-ACK reconciliation |

### 17.2. Transactional Outbox

A `@Transactional("mongoTransactionManager")` can commit business state and an outbox entry within the **same MongoDB transaction**, but it **cannot commit a Kafka/HTTP/JMS/AMQP send**. The outbox worker replays after crashes and keeps `eventId` in the outbound header; the target consumer still needs idempotency.

**`HeaderMapper` is a tool for carrying the metadata of an idempotency contract**, not an exactly-once engine.
## 18. Outbound Security: Data Leakage, SSRF, Injection, and Trust Boundaries

An outbound mapper is the **gate where metadata leaves the application boundary**. If it copies all headers from an inbound message by default, the application can accidentally send internal details to an unauthorized partner.

### 18.1. Information That Must Never Be Forwarded Verbatim

| Header/Metadata | Risk | Policy |
|---|---|---|
| Inbound `Authorization`/cookie | Leaks tokens with the wrong audience | Separate outbound credentials per destination |
| `trustedTenantId` | Leaks tenancy / allows impersonation | Export only a partner-scoped ID if authorized |
| `internalRole` / ACL | Leaks user/server privileges | Do not export |
| `replyChannel` / `errorChannel` | Internal routing objects, non-serializable | Drop |
| Spring `id`/`timestamp` | Not a business identity | Do not use for idempotency |
| Kafka received offset/topic | Leaks topology and wrong destination | Drop |
| AMQP delivery tag/channel | Confuses provider delivery context | Drop |
| JMS `messageId`/`redelivered` | Confuses provider-managed fields | Do not copy raw |
| SFTP internal absolute path | Leaks file system layout | Normalize or drop |
| Inbound HTTP `X-Forwarded-*` | Spoofs client/proxy identity | Do not mirror to partners arbitrarily |
| Java type header / class name | Implementation details, type injection | Trusted schema/type allowlist |

### 18.2. Do Not Let Clients Choose the Outbound Destination

If an inbound HTTP header `X-Target-Url` or `X-Routing-Key` is copied and used as the outbound URL/topic/queue/exchange, a caller can trigger SSRF, probe internal resources, or publish messages to unauthorized destinations.

Safe model:

~~~java
public String endpointFor(String partnerId) {
    return switch (partnerId) {
        case "partner-a" ->
            "https://api.partner-a.example/v1/events";
        case "partner-b" ->
            "https://api.partner-b.example/v1/events";
        default -> throw new IllegalArgumentException(
            "Unknown partner");
    };
}
~~~

This is an illustrative helper; it still needs an authenticated `partnerId`, TLS/egress/network policies, and separate secrets. Do not implement “allow any URL starting with https”, as it can still point to unintended resources.

### 18.3. Preventing HTTP Response Splitting and Oversized Headers

Header values from untrusted payloads can contain `\r`/`\n` control characters or excessive lengths. Check:

- Header name allowlist.
- Maximum header count / aggregate bytes.
- Maximum value length and allowed characters.
- Multiple values for singleton keys like `businessEventId`.
- Encoding/charset; Kafka `String`/`byte[]`, HTTP textual headers.
- Never log raw sensitive values.
- Never create dynamic header names taken directly from input.

Even though HTTP client libraries may reject CR/LF themselves, the application still needs clear validation/business contracts to treat them as input errors rather than triggering network retries.

### 18.4. Kafka/AMQP Typed Headers and RCE Risk

In Spring Kafka JSON type headers, a producer can attach class/type metadata. The receiver must never deserialize arbitrary Java class names sent by an external producer; use trusted packages/a schema registry. Avoid configuring `addTrustedPackages("*")` on untrusted consumers.

AMQP custom headers can contain nested maps/arrays; bound size, typed values, and serialization. JMS properties generally support only primitives/`String`; do not try to pass arbitrary Java objects.

## 19. Testing Outbound HeaderMapper Across Layers

### 19.1. Minimum Test Matrix

| Case | Level | Assertion |
|---|---|---|
| HTTP allowlist | Unit | `X-Event-Id` sent; `Authorization`/`internalRole` absent |
| HTTP rename | Unit | `businessEventId → X-Event-Id` |
| HTTP invalid ID | Unit | Mapper rejects before send |
| HTTP response header | Unit | `X-Partner-Request-Id → partnerRequestId` |
| HTTP gateway | Integration | Wire-level request headers/body, reply/status/timeout |
| HTTP wrong URL | Security integration | Destination allowlist blocks SSRF |
| JMS property mapping | Broker integration | `businessEventId` is a JMS `String` property |
| JMS correlation | Broker integration | `JMSCorrelationID`/reply matches contract |
| JMS QoS | Broker integration | Priority/TTL/delivery mode match producer settings |
| AMQP `fromHeaders` | Unit | `businessEventId` present, `x-received-from` absent |
| AMQP exchange/routing | Broker integration | Message routes to the right queue |
| AMQP unroutable return | Broker integration | Return/NACK channel and recovery |
| Kafka simple mapper | Unit | `businessEventId` exported as raw UTF-8 bytes |
| Kafka producer record | Broker integration | Topic/key/headers and ACK |
| Kafka multi-value | Converter unit | Entry count and typed serialization match version |
| File outbound | Filesystem integration | Clean filename and right content |
| SFTP outbound | Remote test | Remote directory/filename, temp rename, retry |
| Header redaction | Security | No raw secrets in broker/logs/ErrorMessage |
| Async ACK | Integration | Source does not ACK when only `QueueChannel` buffers in RAM |
| Redelivery/idempotency | E2E | Resending `eventId` → no second business effect |

### 19.2. Unit Tests Do Not Replace Integration Tests

For example, `HttpOutboundMapperTest` in Section 4 verifies `mapper.fromHeaders(...)`. It **does not prove** the HTTP outbound gateway is actually configured to use that mapper bean.

When testing outbound HTTP, use an HTTP server stub like WireMock/`MockWebServer` or an embedded test HTTP server:

1. Replace the demo URL with a base URL from test configuration.
2. Producer sends a Spring Message to `sendToPartner`.
3. Stub records the raw request.
4. Assert method/path, `Content-Type`, `X-Event-Id`, and `X-Trace-Id`.
5. Assert **absence** of source `Authorization`, `internalRole`, or Spring internal headers.
6. Stub returns 202 and `X-Partner-Request-Id`; assert gateway reply mapping.
7. Stub 400/409/429/503/timeout to verify error/retry policies.
8. Test that a malformed `eventId` is rejected **before any HTTP request reaches the stub**.

### 19.3. Mocking an HTTP Server Instead of Calling Production Partners

Example test fragment with OkHttp `MockWebServer` **if the corresponding test dependency is added**:

~~~java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import static org.junit.jupiter.api.Assertions.*;

try (MockWebServer server = new MockWebServer()) {
    server.enqueue(
        new MockResponse()
            .setResponseCode(202)
            .addHeader(
                "X-Partner-Request-Id", "r-889")
            .setBody("{\"accepted\":true}"));

    server.start();

    String url = server.url("/api/orders/events")
            .toString();

    // Wire an HTTP outbound gateway to this dynamic test URL,
    // send a Message with X-Event-Id, await the reply.
    // The exact wiring depends on the app's test configuration.

    // After the gateway has sent:
    // RecordedRequest request = server.takeRequest();
    // assertEquals("evt-1001", request.getHeader("X-Event-Id"));
}
~~~

**This is an illustrative fragment**, not a complete JUnit test: you need to initialize a Spring Integration flow using the dynamic `url`, actually send a `Message`, and use a bounded timeout with `takeRequest(timeout, TimeUnit)` in production test code. Never hit real production partners to test errors/timeouts.

### 19.4. JMS Broker Integration Tests

You cannot prove JMS properties are accepted by the provider using only a `MessageHeaders` map. On a JMS test broker:

1. Send a Spring message with `businessEventId`/`appTraceId`/`schemaVersion`.
2. Test JMS listener reads the `TextMessage`/`BytesMessage`.
3. Assert `getStringProperty("businessEventId")` is correct.
4. Assert provider-generated `JMSMessageID` is present, not forced from Spring Message ID.
5. When using a gateway, test `JMSCorrelationID` and reply routing.
6. Test TTL/priority via JMS producer settings/`explicitQoS`, not just the mapper.
7. Simulate JMS broker down and test exceptions/retries/transaction ACK.

### 19.5. AMQP Broker Integration Tests

With a RabbitMQ test broker:

1. Send a Spring Message to the outbound adapter.
2. Bind a queue to the configured exchange/routing key.
3. Consume the Rabbit message and inspect properties/headers.
4. Assert `businessEventId` is present and `x-received-from` is absent.
5. Send to a routing key with no bindings (with mandatory/returns enabled); verify return channel/recovery.
6. Test publisher confirm ACK/NACK per broker config.
7. Assert the inbound message's `deliveryTag` was not copied as producer metadata.

### 19.6. Kafka Broker Integration Tests

On a Kafka test broker:

1. Use a test topic and explicitly configured serializers.
2. Configure the producer converter/header mapper (raw or JSON).
3. Send a message with `businessEventId`/trace.
4. Test consumer reads `ConsumerRecord.headers()`.
5. Assert Kafka wire bytes, topic, key, and partition semantics.
6. Assert Spring ID, `internalRole`, and listener ACK were not exported.
7. Test duplicate record IDs and consumer idempotency separately.
8. Test the producer failure channel/unknown results.

### 19.7. You Do Not Need a Broker to Test Everything

Unit tests for `DefaultHttpHeaderMapper`, custom `PartnerEventHeaderMapper`, AMQP `HeaderMapper`, and `KafkaHeaderMapper` can run without a broker. Broker integration is needed only when testing transport delivery/ACK/replication/consumer behavior.

Separate fast unit tests from slower integration tests, and run broker fault injection only in isolated environments.

## 20. Observability and Outbound Operations

### 20.1. Measure at the Right Checkpoints

| Suggested Metric | Meaning |
|---|---|
| `outbound_headers_mapped_total` | Messages processed by the mapper |
| `outbound_header_validation_error_total` | Required/type/format errors |
| `outbound_header_dropped_total` | Optional/forbidden headers dropped |
| `outbound_header_map_latency_seconds` | Metadata mapping duration |
| `outbound_transport_send_attempt_total` | Outbound send attempts |
| `outbound_transport_send_error_total` | Send exceptions |
| `outbound_delivery_confirm_total` | Broker/transport confirms per policy |
| `outbound_delivery_unknown_total` | Timeouts/ambiguous results |
| `outbound_retry_attempt_total` | Application retry count |
| `outbound_dlq_total` | Durable-quarantined events |
| `outbound_business_committed_total` | Target confirmed business completion |

Metric names are **suggestions**, not emitted by the framework by default. Never use per-event `eventId`, `userId`, tokens, or dynamic URLs as high-cardinality metric labels.

### 20.2. Logging Without Raw Headers

~~~text
outbound_received    destination=partner-a eventType=ORDER_PAID
header_validation_ok mappedHeaderCount=3
transport_send       protocol=http
transport_ack        status=202
business_pending     partnerRequestId=r-889
reconciliation_done  outcome=ALREADY_ACCEPTED
~~~

Never log raw `Authorization`/`Cookie`, JMS connection secrets, sensitive Kafka type hints, or full payloads. Correlation IDs can go into traces/logs with appropriate retention and access controls.

### 20.3. Lifecycle and In-Flight Sends

- **HTTP outbound:** connection pool, socket/connect timeouts, retries, HTTP status mapping.
- **JMS outbound:** `ConnectionFactory`, `JmsTemplate`/session transactions, connection recovery.
- **AMQP outbound:** `RabbitTemplate`, publisher confirms/returns, exchanges/bindings, broker reconnect.
- **Kafka outbound:** `ProducerFactory`/`KafkaTemplate`, async send futures, flush/close, and producer retries.
- **SFTP outbound:** `SessionFactory`, host key verification, upload/temp rename, remote connection recovery.
- **File outbound:** disk space, directory permissions, temp file suffix, move/rename.
- **MongoDB outbound:** transactions/unique keys/write concern.
- **FluxMessageChannel:** subscriptions/terminal signals/backpressure per reactive contract.

During shutdown, stop accepting new data, wait for **in-flight writes/publishes** up to a deadline, and durably persist unfinished state so a new instance can retry. `HeaderMapper` does not perform graceful drain or replay on its own.

## 21. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| HTTP `X-Event-Id` missing | Used `setInboundHeaderNames` instead of outbound | Use `setOutboundHeaderNames` |
| Outbound gateway missing response header | `setInboundHeaderNames` not set | Configure response allowlist |
| HTTP `Content-Type` lost | Explicit allowlist overrode defaults | Add `Content-Type`/`HTTP_REQUEST_HEADERS` |
| HTTP request contains source `Authorization` | Wildcard copy | Strip raw token, use target-specific auth |
| HTTP 202 treated as business DONE | Confused accepted vs. committed | Poll/reconcile business state |
| HTTP response header used as `replyChannel` | Trusted untrusted data | Server policy/routing |
| JMS `businessEventId` lost | Unsupported type/name, mapper/converter | Use JMS-friendly `String` property |
| JMS TTL not applied | Mapped header only without setting producer QoS | `JmsTemplate` explicit QoS/TTL |
| `JMSCorrelationID` mismatch | Overwrote gateway correlation | Check `correlation-key`/config |
| `JMSMessageID` changes on republish | Mistook provider ID for business ID | Stable `businessEventId` |
| AMQP `x-received-from` forwarded | Wildcard/included broker metadata | Negate `x-*` and test |
| AMQP publisher sends but doesn't route | Missing binding/mandatory return | Return channel and confirm policy |
| AMQP `deliveryTag` serialized | Copied inbound runtime state | Exclude received metadata |
| Kafka String header turns into JSON bytes | Used JSON mapper not matching wire contract | Raw mapping/schema policy |
| Kafka consumer doesn't recognize class type | Type-hint/deserialization mismatch | Trusted packages/schema evolution |
| Wrong Kafka topic/key | Taken from unvalidated raw header | Trusted topic/key policy |
| Kafka duplicate values lost | Version-dependent multi-value policy | Wire-level test, enable option if available |
| File written under multiple names on retry | Fallback to Spring Message ID | Stable filename from business ID |
| SFTP remote path traversal | Path from untrusted header | Directory allowlist/sanitize |
| Stale TCP connection ID | Reconnect lost context | Lifecycle-aware connection factory |
| UDP send has no ACK | Best-effort protocol | Application-level ACK if required |
| MongoDB lacks `eventId` | ID only in Spring header | Bind ID into domain payload |
| Mapping passes but `QueueChannel` loses event | RAM queue followed by crash | Durable outbox/ACK at right stage |
| Infinite retries on invalid header | Retried all exceptions | Separate validation vs. transient |
| Mapper tests pass but broker fails | Did not test at transport level | Integration test |
| Metrics cardinality spikes | Labeled by per-message ID/header value | Low-cardinality dimensions |

### 21.1. Diagnostic Workflow

~~~text
1. Upstream Spring Message: payload, headers, and origin trust
2. HeaderEnricher/HeaderFilter: canonical keys/values
3. Outbound endpoint configuration: target URL/destination/topic
4. HeaderMapper.fromHeaders: selected names, types, patterns
5. MessageConverter: payload/wire encoding
6. Actual HTTP/JMS/AMQP/Kafka/file/SFTP request/record
7. Transport send/ACK/confirm/return
8. Downstream business commit and idempotency
9. Retry/recovery after timeout or crash
~~~

If the mapper unit test passes yet the actual outbound request is missing headers, verify that **the bean is injected into the right endpoint**, check whether the converter overwrites headers, and check for any header filter running after the mapper.

## 22. Comprehensive Practice Exercise

Build a pipeline: **HTTP/JMS/Kafka inbound → normalize headers → outbound HTTP/JMS/AMQP/Kafka/SFTP**. Each protocol can be run with its own profile; you do not need all brokers running at once.

### Part A — HeaderMapper Contract

1. Create a table contrasting `HeaderMapper<T>.fromHeaders` and `toHeaders`.
2. Take a Spring message with `businessEventId`/`appTraceId`/`internalRole`.
3. Write an allowlist for a partner HTTP endpoint.
4. Unit test `fromHeaders` so only approved custom headers are sent.
5. Test an HTTP outbound gateway receiving a response header and mapping it back with `toHeaders`.
6. Test missing/invalid `businessEventId` and assert failure before the network call.
7. Implement `PartnerEventHeaderMapper` renaming `businessEventId` to `X-Event-Id`.

### Part B — HTTP Outbound Gateway

1. Use `DefaultHttpHeaderMapper.outboundMapper()`.
2. `setOutboundHeaderNames("Content-Type","X-Event-Id","X-Trace-Id")`.
3. `setInboundHeaderNames("X-Partner-Request-Id","Content-Type")`.
4. Build `Http.outboundGateway(...)` against a mock HTTP server.
5. Verify request method, headers, body, and response headers.
6. Simulate 202/409/429/503/timeout and classify each.
7. Prevent SSRF if the partner URL is chosen dynamically; test the allowlist.

### Part C — JMS/AMQP

1. Create a JMS outbound adapter with `DefaultJmsHeaderMapper`.
2. Send custom `String` property `businessEventId` and test broker receipt.
3. Compare `JMSCorrelationID` with Spring `correlationId` and `businessEventId`.
4. Configure producer TTL/priority/deliveryMode via QoS API.
5. Configure AMQP `DefaultAmqpHeaderMapper` `requestHeaderNames`.
6. Test that `x-received-from`/`internalRole` do not reach the broker.
7. Test AMQP publisher confirm/return when routing fails.
8. Simulate broker down/reconnect and durable retry.

### Part D — Kafka/SFTP/File

1. Choose `SimpleKafkaHeaderMapper` raw bytes or JSON mapper per version.
2. Test record header `businessEventId` has valid UTF-8 bytes.
3. Verify topic/key come from trusted server config, not raw client headers.
4. Test Kafka multi-value semantics per version.
5. Use `FileHeaders.FILENAME` derived from a stable business ID.
6. Send via SFTP to an allowlisted remote dir; verify filename/temp rename.
7. Test retry with the same ID/filename when an ACK is lost.
8. Write the MongoDB payload with a unique event ID rather than relying on headers alone.

### Part E — Reliability and Hardening

1. Strip `Authorization`, `replyChannel`, `errorChannel`, and raw tenant roles.
2. Specify max header bytes/values and type schemas.
3. Compare `DirectChannel` vs. `QueueChannel` regarding send/ACK timing.
4. Use an outbox to publish events from MongoDB to Kafka/RabbitMQ.
5. Simulate a crash after broker ACK before marking SENT, and test redelivery.
6. Implement an idempotent consumer at the destination using `businessEventId`.
7. Add metrics for mapper errors, transport ACKs, unknown results, retries, and DLQ.
8. Write a shutdown/restart runbook to avoid losing in-flight events.

**Self-Assessment Questions:**

- Why is `fromHeaders` the outbound direction of `HeaderMapper<T>`?
- When must an outbound gateway use both `fromHeaders` and `toHeaders`?
- How does `setOutboundHeaderNames` differ from `setInboundHeaderNames` in HTTP?
- Why is mapping inbound `Authorization` to a partner HTTP call dangerous?
- How does a JMS property differ from producer QoS TTL/priority/deliveryMode?
- Why shouldn't `JMSMessageID` serve as `businessEventId`?
- What role does AMQP `requestHeaderNames` play in outbound?
- Why shouldn't you copy `x-received-from` or `amqp_deliveryTag`?
- How does `KafkaHeaderMapper` differ from `org.springframework.integration.mapping.HeaderMapper<T>`?
- When is `SimpleKafkaHeaderMapper` preferable to a JSON mapper?
- Are Kafka `TOPIC`/`KEY` record metadata or custom header bytes?
- What version-specific considerations apply to multi-value Kafka headers?
- Why must `FileHeaders.FILENAME` stay stable across retries?
- What risk arises from taking SFTP `remoteDirectory` from an untrusted header?
- Why doesn't the MongoDB storing adapter automatically save all `MessageHeaders`?
- When `QueueChannel.send()==true`, has the broker ACKed?
- Does HTTP 202 mean the business operation is finished?
- How does a mapping error differ from a network timeout/unknown outcome?
- Why doesn't `HeaderMapper` provide cross-system exactly-once delivery?

## 23. References

- [Spring Integration API — HeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/mapping/HeaderMapper.html): `fromHeaders` and `toHeaders`.
- [Spring Integration API — AbstractHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/mapping/AbstractHeaderMapper.html): header patterns, request/reply.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): `outboundMapper`, `mapped-request-headers`, `mapped-response-headers`.
- [Spring Integration API — BaseHttpMessageHandlerSpec](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/http/dsl/BaseHttpMessageHandlerSpec.html): `headerMapper`, `mappedRequestHeaders`.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): outbound JMS, `DefaultJmsHeaderMapper`, QoS, and gateway correlation.
- [Spring Integration API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): `headerMapper(JmsHeaderMapper)`, destination, TTL.
- [Spring Integration Reference — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html): request/reply name patterns, `x-*` exclusions.
- [Spring Integration API — AmqpBaseOutboundEndpointSpec](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec.html): `headerMapper`, `mappedRequestHeaders`, confirms/returns.
- [Spring Integration Reference — AMQP Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/amqp/outbound-channel-adapter.html): broker routing, publisher confirms, returns.
- [Spring Kafka Reference — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html): `KafkaHeaderMapper`, Simple/JSON mappers, typed/multi-value headers.
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaHeaders.TOPIC`/`KEY`, producer messages.
- [Spring Integration Reference — Apache Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): outbound Kafka adapter/gateway and response/failure channels.
- [Spring Integration Reference — Writing Files](https://docs.spring.io/spring-integration/reference/file/writing.html): `FileHeaders.FILENAME`, `FileNameGenerator`, temporary suffix.
- [Spring Integration Reference — FTP Outbound](https://docs.spring.io/spring-integration/reference/ftp/outbound.html): remote directory, filename expressions, and file exists modes.
- [Spring Integration Reference — SFTP Support](https://docs.spring.io/spring-integration/reference/sftp.html): outbound remote transfer/session lifecycle.
- [Spring Integration Reference — IP Support](https://docs.spring.io/spring-integration/reference/ip.html): TCP/UDP metadata.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): synchronous vs. async channel behavior.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channel and delivery failures.

## Conclusion

**HeaderMapper for outbound messages** turns controlled metadata in **Spring `MessageHeaders`** into headers/properties of the target protocol. In Spring Integration, **`fromHeaders(MessageHeaders, target)` is the outbound direction**; an outbound gateway can also call `toHeaders(externalResponse)` to map the response back into a Spring Message. HTTP typically uses `DefaultHttpHeaderMapper.outboundMapper()`; JMS and AMQP use their own mappers; Kafka uses Spring Kafka's `KafkaHeaderMapper`; File/SFTP/IP/DB have adapter-specific header usage rather than a single shared `HeaderMapper`.

In **SPRING_INTEGRATION_ADAPTERS**, treat outbound header mapping as a **controlled data egress boundary**: allowlist per destination, validate names/types/lengths, avoid leaking tokens/roles/internal routing, keep `businessEventId` stable, test wire-level requests/broker messages, and separate header mapping from payload conversion, ACK/transactions/retries, and recovery. **Successful header mapping does not mean the data was durably delivered, downstream finished processing, or the system achieved exactly-once delivery.**
