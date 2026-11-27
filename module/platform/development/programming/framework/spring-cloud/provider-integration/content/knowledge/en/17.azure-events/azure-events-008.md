# Verifying Event Endpoints and Handling Duplicate Events

An Azure Event Grid receiving webhook must solve two independent problems. First, Event Grid must verify that the endpoint consents to receive events. Second, the application must authenticate requests, validate the event source and content, and safely handle redelivery of the same event. Confusing endpoint verification with identity authentication can allow a webhook to accept spoofed requests. Relying solely on HTTP responses without idempotency can cause legitimate Event Grid retries to update data or trigger side effects multiple times.

This lesson belongs to the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with AWS, Azure, and Google Cloud managed services through the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. In this lesson, the focus is on validating Event Grid schema and CloudEvents 1.0 webhooks, securing endpoints with Microsoft Entra ID, preventing duplicates with inbox/idempotency, handling out-of-order events, and testing delivery/retries.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish endpoint validation from authentication and authorization.
- Implement synchronous or manual validation for the Event Grid schema.
- Implement the CloudEvents abuse-protection handshake using HTTP OPTIONS.
- Configure Spring Security to validate bearer tokens sent by Event Grid to webhooks.
- Validate source/topic, event type, subject, schema version, and payload before processing.
- Design appropriate deduplication keys for Event Grid schema and CloudEvents.
- Use an inbox/processed-event table with a unique constraint and transaction to prevent repeated side effects.
- Handle duplicates, out-of-order events, event identity conflicts, and batch delivery.
- Understand which response codes are retried, dead-lettered, or dropped.
- Build tests for validation handshakes, authentication, duplicates, replays, and failure recovery.

## 2. Two Distinct Problems: Endpoint Validation and Authentication

**Endpoint validation** proves that the registered webhook address consents to receive traffic from Event Grid. It protects senders from someone accidentally or maliciously pointing Event Grid at an unintended website.

**Authentication** verifies that a request genuinely comes from a trusted principal. **Authorization** determines whether that principal is allowed to invoke the endpoint or send that event type.

| Mechanism | Question Answered | Example |
|---|---|---|
| Endpoint validation | Does the endpoint agree to receive Event Grid deliveries? | Validation event or CloudEvents OPTIONS |
| Authentication | Which identity sent the request? | Microsoft Entra bearer token |
| Authorization | Is that identity allowed to call the webhook? | App role or API policy |
| Event validation | Does the event match the expected source, type, and contract? | Topic/source allow-list, event type, schema version |
| Idempotency | Has this event already caused its side effect? | Unique key `source + event ID` |

Never treat the validation handshake as proof that a request is authenticated. An external client can send HTTP OPTIONS or spoof an `Origin` header if the endpoint does not check tokens and permissions. Microsoft requires HTTPS for Event Grid webhooks.

## 3. Secure Webhook Processing Flow

~~~mermaid
flowchart TD
    EG["Azure Event Grid"] --> HTTPS["HTTPS webhook"]
    HTTPS --> AUTH["Authenticate bearer token / secret"]
    AUTH --> VALID{"Validation handshake?"}
    VALID -->|Event Grid schema| EGVAL["Check validation event and echo code"]
    VALID -->|CloudEvents| CEVAL["Check OPTIONS origin agreement"]
    EGVAL --> ACK["Return required validation response"]
    CEVAL --> ACK
    VALID -->|Normal event| SRC["Validate source, topic, type and schema"]
    SRC --> DEDUP["Insert inbox key: source + id"]
    DEDUP --> DUP{"Already processed?"}
    DUP -->|Yes, same payload| ACK2["Return 2xx without side effect"]
    DUP -->|No| TX["Commit business effect + inbox"]
    TX --> ACK2
    DUP -->|Same key, different payload| QUAR["Quarantine and alert"]
~~~

Ordering matters:
1. Authenticate the request according to the configured endpoint protection mechanism.
2. Handle the schema-appropriate handshake.
3. For business events, validate the source and contract.
4. Record the event ID and side effects in a transaction or persist to a durable inbox.
5. Return a success response only after the application has accepted durable processing responsibility.

## 4. Event Grid Schema: Synchronous Validation

When an event subscription uses the Event Grid schema and a webhook destination, Event Grid sends a POST request containing a single event with:

- Header: **aeg-event-type: SubscriptionValidation**.
- Event type: **Microsoft.EventGrid.SubscriptionValidationEvent**.
- Data: **validationCode**; on some API versions, **validationUrl** is also included.

With a **synchronous handshake**, the webhook must return HTTP **200 OK** and JSON containing **validationResponse** equal to the exact **validationCode**. The request must complete within 30 seconds. HTTP 202 Accepted is not accepted for this validation step.

Example incoming body:

~~~json
[
  {
    "id": "validation-event-id",
    "topic": "/subscriptions/example/resourceGroups/rg/providers/Microsoft.EventGrid/topics/orders",
    "subject": "",
    "data": {
      "validationCode": "random-validation-code"
    },
    "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
    "eventTime": "2026-11-24T10:00:00Z",
    "metadataVersion": "1",
    "dataVersion": "1"
  }
]
~~~

Synchronous response:

~~~json
{
  "validationResponse": "random-validation-code"
}
~~~

Validation events are sent separately, never mixed with business events. The endpoint should verify that the topic/subscription belongs to the expected allow-list before echoing the code. Never log validation codes or validation URLs.

### 4.1. Manual Validation Handshake

If an endpoint cannot return the validation code synchronously, Event Grid supports a manual handshake when the subscription is created with an appropriate API version. The validation event contains **validationUrl**. The endpoint returns HTTP 200 acknowledging receipt of the validation request; then an authorized operator or automation performs a GET to that URL within 10 minutes.

- The URL is valid for only 10 minutes.
- The subscription remains in `AwaitingManualAction` while waiting.
- If not completed in time, the subscription transitions to `Failed` and must be recreated.
- The validation URL uses port 553; firewall/network policies must allow the required flow.
- Never expose this URL to end users or log it.

For Spring Boot webhooks that can respond immediately, synchronous handshakes are generally easier to automate and test.

## 5. Spring Boot Controller for Event Grid Schema

The Azure SDK for Java provides **`EventGridEvent.fromString()`** to deserialize a single event or a JSON array into a list of events. Event Grid usually sends payloads as an array even when only one event is present.

The controller example below handles synchronous validation first, then delegates business events to a dedicated service:

~~~java
import com.azure.messaging.eventgrid.EventGridEvent;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/event-grid")
class EventGridWebhookController {
    private final OrderEventHandler handler;
    private final String expectedTopic;

    EventGridWebhookController(
            OrderEventHandler handler,
            WebhookProperties properties) {
        this.handler = handler;
        this.expectedTopic = properties.expectedTopic();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> receive(
            @RequestHeader(
                    name = "aeg-event-type",
                    required = false) String aegEventType,
            @RequestBody String body) {

        List<EventGridEvent> events = EventGridEvent.fromString(body);

        boolean validationHeader =
                "SubscriptionValidation".equalsIgnoreCase(aegEventType);
        boolean validationBody = events.size() == 1
                && "Microsoft.EventGrid.SubscriptionValidationEvent"
                        .equals(events.get(0).getEventType());

        if (validationHeader || validationBody) {
            if (!validationBody || events.get(0).getData() == null) {
                return ResponseEntity.badRequest().build();
            }

            EventGridEvent validationEvent = events.get(0);
            if (validationEvent.getTopic() != null
                    && !expectedTopic.equals(validationEvent.getTopic())) {
                return ResponseEntity.status(403).build();
            }

            Map<?, ?> data =
                    validationEvent.getData().toObject(Map.class);
            Object code = data.get("validationCode");

            if (!(code instanceof String validationCode)
                    || validationCode.isBlank()) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.ok(
                    Map.of("validationResponse", validationCode));
        }

        if (events.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        for (EventGridEvent event : events) {
            if (event.getTopic() != null
                    && !expectedTopic.equals(event.getTopic())) {
                return ResponseEntity.status(403).build();
            }

            handler.handle(event);
        }

        return ResponseEntity.ok().build();
    }
}
~~~

**WebhookProperties** is application configuration, e.g. binding **`app.webhook.expected-topic`** to the resource ID of the approved topic. For custom topics not attached to a domain, **`getTopic()`** may be null; in that case rely on identity, configured endpoint/subscription, and event type/subject allow-lists. Never accept an arbitrary topic just because the body parses.

The controller should run behind the Spring Security filter chain. If a validation event lacks the expected header/body, return an error instead of responding successfully to an unknown request. In production, bound request size, processing time, events per batch, and schema versions.

## 6. CloudEvents 1.0: OPTIONS Abuse-Protection Handshake

CloudEvents 1.0 uses its own handshake mechanism instead of **SubscriptionValidationEvent**. Event Grid sends an HTTP OPTIONS request to the exact registered URI. The request includes headers:

- **WebHook-Request-Origin**: DNS name representing the event-sending system.
- Senders may issue OPTIONS during registration or as a preflight before delivery.

If the endpoint agrees to receive events, the response must include:
- **WebHook-Allowed-Origin**: approved origin; return the exact allow-listed value.
- **WebHook-Allowed-Rate**: accepted request rate in requests/minute.
- **Allow: POST**: indicates the endpoint accepts POST deliveries.

After the handshake, each delivery request carries an **Origin** header whose value must match the agreed origin.

**The OPTIONS handshake does not authenticate identity.** It only records that the endpoint consents to receive traffic from the named origin. Never use wildcard `*` without an explicit reason; never blindly echo back any origin sent by a client.

### 6.1. Spring Boot OPTIONS Endpoint

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/cloudevents")
class CloudEventValidationController {
    private final String allowedOrigin;

    CloudEventValidationController(WebhookProperties properties) {
        this.allowedOrigin = properties.allowedOrigin();
    }

    @RequestMapping(method = RequestMethod.OPTIONS)
    ResponseEntity<Void> validate(
            @RequestHeader("WebHook-Request-Origin")
                    String requestedOrigin) {

        if (!allowedOrigin.equals(requestedOrigin)) {
            return ResponseEntity.status(403).build();
        }

        return ResponseEntity.ok()
                .header("WebHook-Allowed-Origin", allowedOrigin)
                .header("WebHook-Allowed-Rate", "300")
                .allow(HttpMethod.POST)
                .build();
    }
}
~~~

The value `300` is an example requests/minute rate and must be tuned to endpoint capacity. Allow-list configuration:

~~~yaml
app:
  webhook:
    allowed-origin: eventgrid.azure.net
~~~

Replace the illustrative value with the real origin sent by Event Grid in **WebHook-Request-Origin**. If the app receives from multiple senders, use a managed allow-list rather than accepting every origin.

### 6.2. Checking Origin on Every Delivery

~~~java
import com.azure.core.models.CloudEvent;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/cloudevents")
class CloudEventWebhookController {
    private final CloudEventHandler handler;
    private final String allowedOrigin;

    CloudEventWebhookController(
            CloudEventHandler handler,
            WebhookProperties properties) {
        this.handler = handler;
        this.allowedOrigin = properties.allowedOrigin();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> receive(
            @RequestHeader(
                    value = HttpHeaders.ORIGIN,
                    required = false) String origin,
            @RequestBody String body) {

        if (origin == null || !allowedOrigin.equals(origin)) {
            return ResponseEntity.status(403).build();
        }

        List<CloudEvent> events = CloudEvent.fromString(body);
        if (events.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        for (CloudEvent event : events) {
            handler.handle(event);
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

This only checks agreement per the CloudEvents webhook protocol. Requests must still pass Spring Security authentication and authorization. Any client can forge an **Origin** header; therefore, this header can never replace bearer tokens or other authentication mechanisms.

## 7. Securing Webhooks with Microsoft Entra ID

For production webhooks, configure Event Grid to send bearer tokens to an API protected by Microsoft Entra ID. General workflow:

1. Register an application/API representing the webhook.
2. Declare the Application ID URI or audience accepted by the API.
3. Create an app role for Event Grid deliveries, e.g. **EventGrid.Receive**.
4. Configure the event subscription to use Microsoft Entra authentication with the tenant ID and the API's application ID/URI.
5. Grant the required role/application association to the Event Grid service principal per current security guidance.
6. In Spring Security, validate signature, issuer, tenant, audience, token expiration, and role/scope.
7. Allow POST event deliveries only if the principal has the role; CloudEvents OPTIONS may be permitted separately while still enforcing the origin allow-list.

Event Grid only supports HTTPS webhooks. Validation handshakes must still run even when Entra authentication is enabled; the two mechanisms serve different purposes.

### 7.1. Dependencies and Resource Server Configuration

Spring Security OAuth2 Resource Server dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.microsoftonline.com/TENANT_ID/v2.0
~~~

Configuring the issuer lets Spring Security discover metadata and validate tokens against that issuer. The application must also verify the exact Application ID URI audience of the webhook and expected permissions/app roles; never assume a validly signed token intended for any API in the tenant is sufficient.

Example audience validation using a custom `JwtDecoder`:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.validator.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
@EnableConfigurationProperties(WebhookSecurityProperties.class)
class WebhookJwtConfiguration {

    @Bean
    JwtDecoder webhookJwtDecoder(WebhookSecurityProperties properties) {
        String issuer = properties.issuer();
        String audience = properties.audience();
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerValidator =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
                new JwtClaimValidator<List<String>>(
                        "aud",
                        values -> values != null
                                && values.contains(audience));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerValidator,
                        audienceValidator));

        return decoder;
    }
}

@ConfigurationProperties(prefix = "app.security")
record WebhookSecurityProperties(String issuer, String audience) {}
~~~

In this example, **aud** is assumed to be a list of strings matching the API's token format. Inspect real tokens from your tenant to verify claim types and audience format; adjust the validator if the format differs. Add app role checks in the authorization layer or a `JwtAuthenticationConverter`.

The `JwtDecoder` bean above is picked up automatically by the `SecurityFilterChain` below. If the API requires an app role, configure a `JwtAuthenticationConverter` to read the `roles` claim and map it to authorities; checking `authenticated()` alone is insufficient for business-level authorization.

### 7.2. SecurityFilterChain for Webhooks

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebhookSecurityConfiguration {

    @Bean
    SecurityFilterChain webhookSecurity(HttpSecurity http)
            throws Exception {
        http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/webhooks/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.OPTIONS,
                        "/webhooks/cloudevents").permitAll()
                .requestMatchers("/webhooks/**").authenticated()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

The example uses **`authenticated()`** to focus on token verification; production should add a converter/policy restricting webhook access to the designated app role. `OPTIONS` is permitted separately because CloudEvents preflight does not establish an authentication context; the controller still enforces the origin allow-list. `POST` deliveries still require a valid bearer token.

### 7.3. Shared Secrets via Query Parameters

Event Grid also supports a client secret in a webhook URL query parameter. If you must use it:
- Generate a strong random secret used for a single subscription only.
- Store the secret in a secret manager and restrict who can read the subscription endpoint.
- Never log full URLs in applications, reverse proxies, APMs, or WAFs.
- Use constant-time comparison when checking the secret.
- During rotation, temporarily accept both old and new secrets for a short overlap window; update the subscription and then revoke the old secret.
- Prefer Entra bearer tokens for production endpoints whenever architecture permits.

Never confuse a query secret or `Origin` header with the endpoint validation code. The validation code is a one-time nonce for endpoint verification, not a credential for ongoing delivery requests.

## 8. Validating Event Source and Contract

After authenticating the request, the application must still verify that the event matches the subscription and business rules.

Checks to include:

- **Source/topic:** accept only configured topics/resource IDs. For CloudEvents, check the **source** attribute; for Event Grid schema, check **topic** when present and verify against configured subscription/endpoint expectations.
- **Event type:** allow-list supported types; never dispatch arbitrary events to a catch-all handler.
- **Subject:** check prefixes/paths if the business cares only about specific resource types.
- **Schema version:** explicitly support versions; reject or quarantine incompatible versions.
- **Data:** validate required fields, data types, size limits, and invariants.
- **Business timestamp/version:** never use timestamps as dedup keys; use aggregate versions to detect stale/out-of-order events.
- **Correlation ID:** preserve to trace across producer, Event Grid, and consumer.

Event subscription filters reduce irrelevant traffic, yet consumers must still validate source/type. Filters can be misconfigured or subscriptions created incorrectly; checking at the application boundary is the final safeguard.

## 9. Identifying an Event to Prevent Duplicates

### 9.1. Event Grid Schema

Event Grid schema includes a unique **id** field generated by the publisher. During delivery retries, the same event is redelivered with the exact same ID. Applications can combine event ID, source/topic identifier, and logical consumer name as the deduplication key.

With an Event Grid domain, events carry the specific topic. With a standalone topic, configure the topic's resource ID as the source scope if the envelope lacks a topic field.

### 9.2. CloudEvents 1.0

Under CloudEvents, the pair **source + id** uniquely identifies an event. Never rely on **id** alone when consuming from multiple sources, because two sources could produce colliding ID strings.

Recommended deduplication keys:

| Schema | Deduplication Key |
|---|---|
| Event Grid schema | `consumer name + configured topic/source + event id` |
| CloudEvents | `consumer name + source + id` |

**Consumer name** distinguishes processing goals. For example, **order-projection** and **fraud-detection** may process the same event with different progress and side effects. Sharing one dedup table across all consumers without `consumer_name` could cause one consumer to skip valid events already processed by another.

## 10. Inbox Table and Unique Constraints

A standard pattern stores processed events in an inbox/processed-event table. The primary key prevents two concurrent requests from recording the same event as two new events.

PostgreSQL example:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_source varchar(500) NOT NULL,
    event_id varchar(200) NOT NULL,
    payload_sha256 char(64) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_source, event_id)
);
~~~

Idempotent insert statement:

~~~sql
INSERT INTO processed_event (
    consumer_name,
    event_source,
    event_id,
    payload_sha256
)
VALUES (
    'order-projection',
    :event_source,
    :event_id,
    :payload_sha256
)
ON CONFLICT DO NOTHING;
~~~

If the insert creates a new row, the transaction proceeds with business processing. If no row is created, the event was recorded earlier. Compare the stored payload hash with the incoming hash:
- Same `source + id` and same hash: legitimate duplicate, skip side effects.
- Same `source + id` with a different hash: identity conflict—audit/quarantine and alert; never silently ignore.

Never use an in-memory cache as the sole deduplication store. Caches vanish on restart, are not shared across replicas, and can allow two instances to process the same event concurrently.

## 11. Processing Events and Deduplicating in the Same Transaction

Key rule: write the processed-event record and update business data in the **same database transaction**. Separating them into two transactions allows a crash after recording dedup yet before updating business state; subsequent retries are treated as duplicates and side effects are lost.

PostgreSQL service example using `JdbcTemplate`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderEventHandler {
    private final JdbcTemplate jdbc;

    OrderEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean handle(
            String consumerName,
            String source,
            String eventId,
            byte[] payload,
            String orderId,
            String newStatus) {

        String hash = sha256(payload);

        int inserted = jdbc.update(
                """
                INSERT INTO processed_event
                    (consumer_name, event_source, event_id, payload_sha256)
                VALUES (?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                consumerName, source, eventId, hash);

        if (inserted == 0) {
            String storedHash = jdbc.queryForObject(
                    """
                    SELECT payload_sha256
                    FROM processed_event
                    WHERE consumer_name = ?
                      AND event_source = ?
                      AND event_id = ?
                    """,
                    String.class,
                    consumerName, source, eventId);

            if (!hash.equals(storedHash)) {
                throw new IllegalStateException(
                        "Event identity was reused with a different payload");
            }

            return false;
        }

        int updated = jdbc.update(
                """
                UPDATE order_projection
                SET status = ?
                WHERE order_id = ?
                """,
                newStatus, orderId);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected exactly one order projection to be updated");
        }

        return true;
    }

    private static String sha256(byte[] payload) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(payload);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
~~~

This example targets PostgreSQL and Spring transactions. Both `processed_event` and `order_projection` must share the same datasource/transaction. In production, validate payloads before invoking the handler, verify updated row counts, and record identity conflicts in quarantine via a separate transaction if the main transaction rolls back. Never log sensitive payloads; the hash detects content changes, not encryption.

When a controller calls a `@Transactional` service bean via a Spring proxy, the transaction commits before the service call returns. The controller can therefore safely return HTTP 2xx once the service finishes. Avoid putting the transaction directly on the controller and returning an ACK before the transaction interceptor commits.

An adapter normalizes Event Grid or CloudEvents envelopes into the same business handler. Event Grid schema falls back to the configured topic as source scope when the `topic` field is absent; CloudEvents uses its `source` attribute:

~~~java
import com.azure.core.models.CloudEvent;
import com.azure.messaging.eventgrid.EventGridEvent;
import org.springframework.stereotype.Service;

record OrderEventData(String orderId, String status) {}

@Service
class OrderEventAdapter {
    private final OrderEventHandler handler;
    private final String configuredTopic;

    OrderEventAdapter(
            OrderEventHandler handler,
            WebhookProperties properties) {
        this.handler = handler;
        this.configuredTopic = properties.expectedTopic();
    }

    void handle(EventGridEvent event) {
        if (event.getData() == null || event.getId() == null) {
            throw new IllegalArgumentException("Invalid Event Grid envelope");
        }
        OrderEventData data = event.getData().toObject(OrderEventData.class);
        String source = event.getTopic() == null
                ? configuredTopic : event.getTopic();
        handler.handle(
                "order-projection", source, event.getId(),
                event.getData().toBytes(), data.orderId(), data.status());
    }

    void handle(CloudEvent event) {
        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing CloudEvent data");
        }
        OrderEventData data = event.getData().toObject(OrderEventData.class);
        handler.handle(
                "order-projection", event.getSource(), event.getId(),
                event.getData().toBytes(), data.orderId(), data.status());
    }
}
~~~

The adapter must validate event type, source, and payload schema before invoking the handler. If an identity conflict is permanent, quarantine it in a separate transaction and ACK per policy; or let Event Grid move the event to dead-letter per configured retry policy. Never return 5xx forever for an unfixable payload.

## 12. Durable Inbox Followed by Asynchronous Processing

If business processing takes significant time, the webhook should not hold HTTP requests open for long. Use the inbox pattern:

1. Authenticate and validate the event.
2. Write payload/metadata into the inbox with unique key `source + id` and status `PENDING`.
3. Commit the transaction.
4. Return HTTP 202 Accepted to Event Grid.
5. A Spring Boot worker picks up `PENDING` inbox items and processes them transactionally/idempotently.
6. Record `DONE` or `FAILED`; move permanently failing events to quarantine.

Never push events onto an in-memory queue and return 202. If the process stops after ACKing, in-memory work is lost. Only an inbox table, Service Bus queue, or durable broker is a safe ingestion point.

The inbox also needs payload limits, encryption, retention, retry counts, and access controls. If storing raw events, store only necessary fields and enforce sensitive-data policies.

## 13. Duplicates, Retries, and Response Codes

Event Grid provides durable **at-least-once** delivery for each matching subscription. Events can be redelivered when endpoints fail to ACK, time out, or responses are lost. Event Grid does not guarantee delivery order. By default, Event Grid delivers events one by one; the payload is still a single-element JSON array. When batch delivery is enabled, one request can contain multiple events with all-or-none delivery semantics.

For webhooks, responses 200, 201, 202, 203, and 204 count as successful ACKs. Codes 400, 413, 401, and 403 are not retried under normal policy; if dead-lettering is not configured, events may be dropped. Other errors, including many 5xx responses and timeouts, are generally retried with exponential backoff.

| Scenario | Response / Action |
|---|---|
| Event processed successfully | 200 or 202 after durable commit/persistence |
| Duplicate event, identical payload | Skip side effects and return 2xx |
| Unprocessed event, temporary DB failure | Return 5xx so Event Grid retries |
| Permanently invalid request | 400; configure dead-lettering if events must be retained |
| Invalid authentication | 401/403; fix token config and configure dead-lettering |
| Payload exceeds limit | 413; adjust batch/request size |
| Identity conflict | Quarantine, alert, and handle per policy; do not ACK as a valid duplicate |

By default, Event Grid retries up to 30 times or until a TTL of 1,440 minutes (24 hours), whichever comes first. Endpoints can still receive duplicates even after returning success because removing events from retry queues is best-effort. Thus, ACKing once does not replace idempotency.

### 13.1. Dead-Lettering

Dead-lettering is not enabled by default on every subscription. Configure Blob Storage as a dead-letter destination when undeliverable events must be preserved. Ensure:
- The storage account/container exists before creating the subscription.
- Event Grid's identity has appropriate write permissions if using managed identity.
- Alerts trigger when dead-lettered events appear.
- Procedures exist to inspect payloads, fix root causes, and replay.
- Retention/lifecycle policies and separate archive read permissions are configured.

An unavailable dead-letter destination can also cause events to be dropped. Never treat dead-lettering as automatic reprocessing; it is a holding area for investigation and controlled replay.

## 14. Handling Out-of-Order Events

Event Grid does not guarantee ordering. If two events for the same order are emitted close together, version 5 may arrive before version 4. Idempotency prevents applying the same event twice, yet does not solve older events arriving after newer ones.

Include an aggregate version or sequence in the payload:

~~~json
{
  "eventId": "evt-order-1001-v5",
  "aggregateId": "order-1001",
  "aggregateVersion": 5,
  "eventType": "OrderShipped",
  "data": {
    "status": "SHIPPED"
  }
}
~~~

Consumers can:
- Ignore versions lower than the already-applied version.
- Apply only the exact next version if the business forbids gaps.
- Store early-arriving events in a pending table until missing versions arrive.
- Reconcile aggregate state if an event gap persists.
- Never use `eventTime` as an absolute ordering key because clocks and delivery delays vary.

For payments, inventory, or order lifecycles, enforce state-transition guards in the database. Idempotency and version checks solve two different problems.

## 15. External Side Effects and the Transactional Outbox

If a handler updates the database and also sends emails, charges payments, or calls partner APIs, database transactions cannot roll back external side effects. For example, the DB commit succeeds yet the partner HTTP request times out; the consumer does not know whether the external call executed.

How to handle this:
- Pass an idempotency key (`source + event ID`) to the target API if supported.
- Write the side-effect command into an outbox in the same transaction as `processed_event` and business updates.
- A separate worker dispatches outbox items and marks completion.
- If the external response is indeterminate, query status or retry with the exact same idempotency key.
- Never mint a new key per retry.

~~~mermaid
flowchart TD
    EG["Event Grid delivery"] --> IN["Webhook / inbox"]
    IN --> TX["Database transaction"]
    TX --> DEDUP["Insert processed_event"]
    TX --> STATE["Update business state"]
    TX --> OUT["Insert outbox command"]
    OUT --> WORKER["Outbox dispatcher"]
    WORKER --> API["External API with idempotency key"]
    API --> DONE["Mark outbox complete"]
~~~

An outbox does not create exactly-once across the database and external APIs. It ensures side-effect requests are not forgotten after commit; target APIs still require idempotency or reconciliation mechanisms.

## 16. Testing Batch Delivery

Event Grid delivers one event at a time by default, still wrapped in an array. When batch delivery is enabled on a subscription, a single request can contain multiple events. Batch delivery has all-or-none semantics: the endpoint must process the entire batch within Event Grid's timeout.

A safe strategy:
- Deserialize the entire batch.
- Validate each event before processing.
- Assign each event its own dedup key.
- Commit per event or commit the whole batch transactionally depending on business requirements.
- If one event fails and returns 5xx, Event Grid may redeliver the entire batch; previously committed events must be deduplicated.
- If an event fails permanently, durably quarantine it before ACKing the batch per policy.

Never return 2xx after partially processing a batch without persisting the remaining events. If independent processing is desired, inbox every event first and ACK only once all events are durably persisted.

## 17. Spring Boot Configuration and Deployment

Example application properties for the webhook:

~~~yaml
app:
  webhook:
    expected-topic: /subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP/providers/Microsoft.EventGrid/topics/orders
    allowed-origin: eventgrid.azure.net
  security:
    issuer: https://login.microsoftonline.com/TENANT_ID/v2.0
    audience: api://ORDER_WEBHOOK_APP_ID
~~~

These are illustrative environment settings. Use a secret manager or platform configuration to supply audience, issuer, and endpoints; never put real secrets in Git.

When deploying:
- Register the event subscription with the exact HTTPS webhook URL and output schema.
- Configure Entra bearer tokens or secret query parameters per policy.
- Configure the CloudEvents origin allow-list if using CloudEvents.
- Open network paths for validation requests and POST deliveries; verify WAFs do not strip validation headers/bodies.
- Configure a dead-letter destination and retry TTL/attempts.
- Grant Blob dead-letter permissions to Event Grid's identity if using managed identity.
- Monitor deployment rollouts so old and new endpoints both handle traffic safely during cutover.

When using Entra authentication, verify issuer, audience, and app role on tokens sent by Event Grid. Checking only tenant or signature is not enough to prove the token was issued for this API.

## 18. Testing Endpoint Validation and Duplicates

Use dedicated test topics, subscriptions, webhook URLs, and databases. Never send fake validation requests to production endpoints or intentionally return errors to trigger retries on live subscriptions.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Event Grid synchronous validation | POST validation event with `aeg-event-type` header | HTTP 200 and matching `validationResponse` |
| Wrong validation code | Return a code different from payload | Subscription validation fails |
| Validation returns 202 | Return 202 instead of 200 | Event Grid does not accept the handshake |
| Manual validation | Return 200, then GET `validationUrl` within 10 minutes | Subscription transitions to validated |
| Expired validation URL | Wait more than 10 minutes | Subscription fails; must be recreated |
| CloudEvents OPTIONS | Send valid `WebHook-Request-Origin` | Returns `WebHook-Allowed-Origin`/Rate and `Allow: POST` |
| Disallowed origin | Send origin outside allow-list | Consent denied |
| Wrong Origin header on POST | Send delivery with mismatched `Origin` | Request rejected |
| JWT wrong issuer/audience | Send token issued for another API | Rejected by Spring Security |
| JWT missing app role | Valid token lacking permission to receive events | Rejected by authorization |
| Duplicate same `source + id` | Send the same event twice | Only one side effect |
| Same `id`, different `source` | Two sources emit the same `id` | Both events are distinguished |
| Same `source + id`, different payload | Send an identity conflict | Quarantined/alerted, never silently ignored |
| Crash after DB commit | Stop process before HTTP ACK | Retry does not repeat side effects |
| DB unavailable | Temporarily break test database | Endpoint returns 5xx, Event Grid retries |
| Batch with one bad event | Send batch mixing valid and failing events | Unpersisted events are not lost |
| Out-of-order events | Send aggregate versions out of order | Consumer detects stale/gap |
| Dead-letter | Configure test endpoint to return non-retryable error | Event is retained in DLQ storage |

Unit tests verify validation codes, origin allow-lists, source/type allow-lists, unique constraints, and payload hashes. Integration tests verify Spring Security, PostgreSQL transactions, real Event Grid delivery retries, and dead-lettering.

## 19. Observability and Runbooks

Track at least:

| Category | Metrics |
|---|---|
| Validation | Handshake count, validation failures, OPTIONS rejections |
| Authentication | Invalid JWTs, issuer/audience mismatches, unauthorized/forbidden |
| Delivery | Request count, 2xx/4xx/5xx, latency, delivery attempts |
| Idempotency | Duplicates suppressed, identity conflicts, inbox insert conflicts |
| Business | Handler successes/failures, aggregate version gaps, transaction rollbacks |
| Persistence | Inbox backlog, outbox backlog, DB latency, connection pools |
| Dead-letter | Event count, oldest event age, reasons, replay counts |
| Security | Secret rotation, role assignments, endpoint URL changes, WAF rejections |

Runbook when validation fails:
1. Verify HTTPS endpoint and valid TLS certificate.
2. Check WAF, API Gateway, reverse proxy, and firewall.
3. Verify `aeg-event-type` header or `OPTIONS` request reaches the controller.
4. For Event Grid schema, verify exact `validationResponse` is returned within 30 seconds.
5. For manual handshakes, check `validationUrl` and port 553 within the 10-minute window.
6. For CloudEvents, verify `WebHook-Request-Origin` and both response headers.
7. Verify JWT/secret filters do not block legitimate validation requests.

Runbook when duplicates spike:
1. Check Event Grid retries, endpoint latency, and response timeouts.
2. Check whether deployments/restarts wiped deduplication state.
3. Verify unique constraints and inbox/business-state transactions.
4. Verify external non-database side effects carry idempotency keys.
5. Verify event `source`/`id` remain stable across retries.
6. Reconcile business state before replaying or resending events.

## 20. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating validation handshake as authentication | Webhook may accept spoofed requests | Authenticate JWT/secrets independently |
| Checking only `Origin` | Header can be spoofed | Use Entra bearer tokens and allow-list |
| Returning 202 for Event Grid schema validation | Subscription fails verification | Return 200 and `validationResponse` |
| Using CloudEvents OPTIONS as auth | POST requests go unauthenticated | Enforce JWT/roles on deliveries |
| Using event `id` as global key across sources | Two sources can collide | Use `source + id` |
| Deduplicating only in local memory/cache | Restarts/scale-out lose protection | Unique constraint in persistent store |
| Writing dedup first, business state later in separate transactions | Event marked done even if business commit fails | Same transaction |
| Returning 2xx before persisting | Process crash loses events | Persist inbox/outbox before ACK |
| Returning 401/403 on misconfigured JWT without DLQ | Events dropped without retries | Fix auth config and enable dead-lettering |
| Assuming events arrive in order | State can regress | Aggregate version / state-transition guard |
| Purging dedup records too early | Replays re-trigger old side effects | Retention exceeding retry TTL and replay policy |
| Enabling batching, partially processing, and ACKing | Remaining events lost | Persist every event or process batch atomically |

## 21. Pre-Production Checklist

- **Endpoint:** HTTPS, valid certificate, WAF/firewall allow validation and delivery.
- **Validation:** Event Grid schema returns exact `200 + validationResponse`; CloudEvents OPTIONS uses origin allow-list.
- **Authentication:** Entra JWT or secret verified on every POST; issuer, audience, tenant, and app role correct.
- **Authorization:** Endpoint permits only Event Grid principals and required roles.
- **Source:** Topic/source, event type, subject, and schema version allow-listed.
- **Idempotency:** Dedup key includes `consumer name + source + event ID`; unique constraint in persistent store.
- **Transactions:** Dedup and business state share one transaction; external side effects use outbox/idempotency keys.
- **Ordering:** Aggregate version and stale/gap handling policies clearly defined.
- **Responses:** ACK only after persist/commit; understand which responses Event Grid retries or drops.
- **Dead-letter:** Storage, RBAC, encryption, retention, alerts, and replay runbook configured.
- **Batching:** Payload size, timeouts, and all-or-none semantics tested.
- **Observability:** Validation, JWT failures, duplicates, identity conflicts, delivery retries, inbox, and DLQ have metrics/alerts.
- **Testing:** Sync/manual validation, CloudEvents OPTIONS, auth, duplicates, crashes, out-of-order, and DLQ tested.
- **Retention:** Dedup records kept longer than retry TTL and business replay windows.

## 22. Summary

Endpoint verification and request authentication are two separate layers. Event Grid schema uses **SubscriptionValidationEvent** with a synchronous HTTP 200 response or manual validation URL; CloudEvents uses OPTIONS with **WebHook-Request-Origin** and **WebHook-Allowed-Origin/Rate** response headers. Neither proves request identity—they only confirm the endpoint consents to receive traffic. Production webhooks require HTTPS and authentication such as Microsoft Entra bearer tokens, alongside source/topic and event contract validation.

Event Grid delivers at-least-once and does not guarantee ordering, making duplicates and out-of-order arrivals normal scenarios. For CloudEvents, use **source + id**; for Event Grid schema, use topic/source scope + id. Persist inbox records and business state in the same transaction, keep event IDs stable, guard ordering with aggregate versions, and configure dead-lettering to retain undeliverable events. When Spring Boot follows these practices, webhooks validate endpoints reliably, reject untrusted requests, and handle retries without repeating side effects.

## References

- [Endpoint validation with Event Grid event schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-event-grid-events-schema)
- [Endpoint validation with CloudEvents schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-cloud-events-schema)
- [Troubleshoot Event Grid subscription validation](https://learn.microsoft.com/en-us/azure/event-grid/troubleshoot-subscription-validation)
- [Authenticate event delivery to event handlers](https://learn.microsoft.com/en-us/azure/event-grid/security-authentication)
- [Secure webhook delivery with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/event-grid/secure-webhook-delivery)
- [Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry)
- [EventGridEvent class in Azure SDK for Java](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.eventgrid.eventgridevent?view=azure-java-stable)
- [CloudEvent class in Azure SDK for Java](https://learn.microsoft.com/en-us/java/api/com.azure.core.models.cloudevent?view=azure-java-stable)
