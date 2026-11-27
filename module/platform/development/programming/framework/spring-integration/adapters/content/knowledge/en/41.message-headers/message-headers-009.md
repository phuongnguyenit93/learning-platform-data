# Header Filter for Stripping Sensitive Data

## Objectives

After this lesson, you will be able to:

- Explain the role of a header filter in a Spring Integration message flow.
- Distinguish removing headers from filtering out messages or sanitizing payloads.
- Place a header filter in the right position before a message crosses a system boundary.
- Configure the list of headers to remove using Java DSL.
- Verify that sensitive headers are removed while required metadata remains intact.
- Combine header filters with header mappers, logging, and data-protection rules.

In the **SPRING_INTEGRATION_ADAPTERS** module, messages travel through adapters and gateways to communicate with files, SFTP, HTTP, JMS, AMQP, Kafka, databases, and other systems. A Spring Integration message carries a payload alongside metadata in headers. Headers can contain correlation IDs, routing info, tenant identifiers, or authentication data added by the flow. When a message is sent to an external system, an internal header can accidentally become data sent over the wire, written to a broker, or saved in a target system.

**Header filter** removes specified headers before a message continues. It is a message-level metadata sanitization step; it does not replace protecting payloads, transports, or secret stores.

## 1. Message Headers and Sensitive Data

A Spring Integration message has two parts:

- **Payload**: the primary data processed by the flow, such as a DTO, JSON string, file contents, or business command.
- **Headers**: metadata accompanying the message, such as ID, timestamp, correlation ID, reply channel, content type, and application-defined headers.

For example, an internal message may carry these headers:

| Header | Purpose | Should It Be Sent Externally? |
|---|---|---|
| `correlationId` | Track a transaction across multiple steps | Only when required by the integration contract |
| `tenantId` | Identify the processing tenant | Only when the partner is authorized to see it |
| `Authorization` | Auth token for an HTTP call | Only through a designed transport mechanism; never leak to other connectors |
| `X-Api-Key` | Partner API key | Never send to other targets or log |
| `sessionToken` | Session token | Usually must be stripped before forwarding |
| `replyChannel` | In-app reply channel reference | Never send to external systems |
| `errorChannel` | In-app error-handling channel reference | Never send to external systems |

Not every header is a secret. A correlation ID can be useful for reconciliation, whereas `replyChannel` is an internal implementation detail. Classify headers according to each flow's contract and the receiving system's permissions.

### Example of Header Leakage Risk

Suppose a flow receives a request from an internal API. An authentication step adds a token to a header to call an authorization service. Then the same message is sent to Kafka for business processing. If the adapter or header mapper forwards that header, the token can appear in the Kafka record or be read by another consumer.

~~~mermaid
flowchart LR
    A[HTTP inbound] --> B[Message with token]
    B --> C[Permission check]
    C --> D[Header filter]
    D --> E[Kafka outbound]
    E --> F[Business consumer]
    B -. if unfiltered .-> G[Token leaked]
~~~

The filter must be placed after the step that uses the header internally and before the point where the message can leave the trust boundary.

## 2. How Does HeaderFilter Work?

In Spring Integration, **`HeaderFilter`** is a transformer that removes specified headers from a message. Java DSL provides `.headerFilter(...)` to declare the header names to strip.

When the transformer runs:

1. The payload remains unchanged.
2. Headers in the exclusion list are removed from the output message.
3. Other headers are preserved per the transformer's behavior.
4. The transformed message proceeds to the next endpoint or channel.

Spring `Message` and `MessageHeaders` are immutable. Filtering produces an output message with an updated header set; never design a flow assuming the input message is mutated in place.

Header filter is a transformer, not a **`MessageFilter`**:

| Component | Behavior |
|---|---|
| `HeaderFilter` | Keeps the message and payload, removes specified headers |
| `MessageFilter` | Decides whether the message continues or is dropped based on a condition |
| Payload transformer | Transforms the payload, e.g., removes sensitive fields from a DTO or JSON |
| Header enricher | Adds or updates headers per flow rules |

If the goal is stripping a token from the message while still processing the order, use `HeaderFilter`. If the goal is blocking the entire invalid order, use `MessageFilter` or appropriate validation. If the token sits inside the payload, `HeaderFilter` cannot remove it.

## 3. Configuration with Java DSL

Suppose a flow receives messages from an internal channel and forwards them to a partner service. `Authorization`, `X-Api-Key`, and `sessionToken` were used only in earlier internal steps and are not part of the partner message contract.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class PartnerFlowConfiguration {

    @Bean
    IntegrationFlow partnerRequestFlow() {
        return IntegrationFlow.from("partnerRequests")
                .headerFilter(
                        "Authorization",
                        "X-Api-Key",
                        "sessionToken")
                .channel("partnerSanitizedRequests")
                .get();
    }

    @Bean
    QueueChannel partnerSanitizedRequests() {
        return new QueueChannel();
    }
}
~~~

In this example, messages enter `partnerRequests`, pass through the header filter, and then reach `partnerSanitizedRequests`. Endpoints downstream of this channel receive only messages stripped of those three headers.

When integrating with an outbound adapter, place the filter step in the same flow before the adapter:

~~~java
@Bean
IntegrationFlow publishPartnerEvent(PartnerEventHandler partnerEventHandler) {
    return IntegrationFlow.from("partnerEventRequests")
            .headerFilter(
                    "Authorization",
                    "X-Api-Key",
                    "sessionToken",
                    "internalUserContext")
            .handle(partnerEventHandler)
            .get();
}
~~~

`PartnerEventHandler` represents the endpoint sending data to an external system in this example. In a real application, the endpoint could be an HTTP outbound gateway, Kafka outbound adapter, AMQP outbound adapter, or a service gateway. The header list must match that endpoint's contract.

Do not place the header filter too early if upstream steps still need the token for authentication or metadata for routing. Nor place it after the outbound adapter: once the adapter sends the message, data may already have left the application.

## 4. Choosing Headers to Strip

Build the header list based on origin, intended use, and destination. Headers commonly requiring review include:

- Credentials: `Authorization`, `X-Api-Key`, `password`, `accessToken`, `refreshToken`.
- Session: `sessionToken`, `sessionId`, `Cookie`, `Set-Cookie`.
- Internal info: `replyChannel`, `errorChannel`, `internalUserContext`, security context references.
- Personal data or identifiers: email, phone number, customer ID, or tenant ID if the partner is not authorized to receive them.
- Debug headers: internal trace info, diagnostic data, or dev-only values.

Header names in Spring `MessageHeaders` are map keys. Use the exact names created in the flow; do not assume all names are case-normalized. For example, `Authorization` and `authorization` can be two distinct keys if created separately by the app.

A practical pattern is centralizing sensitive header names as constants so flows reference the same keys:

~~~java
public final class SensitiveHeaders {

    public static final String AUTHORIZATION = "Authorization";
    public static final String API_KEY = "X-Api-Key";
    public static final String SESSION_TOKEN = "sessionToken";
    public static final String INTERNAL_USER_CONTEXT = "internalUserContext";

    private SensitiveHeaders() {
    }
}
~~~

When your Java DSL version supports passing a list/array of names, centralize the list configuration to avoid repeating literals across flows. If your project has its own header naming conventions, prefer constants from a shared module.

Do not remove a header merely because its name sounds internal. For instance, a correlation ID may need to stay to trace requests from sender to receiver. Conversely, keep a correlation ID only when the partner is permitted to receive it and the contract defines how it is used.

## 5. Combining Header Filter with Header Mapper

When using HTTP, JMS, AMQP, or Kafka adapters, Spring Integration message headers can be mapped to headers or properties of the target protocol. The mapping mechanism depends on the adapter and configured header mapper.

Header filter and header mapper solve two different parts:

- Header filter removes metadata from the Spring Message before the next endpoint processes it.
- Header mapper decides which headers are converted into the external protocol's format and how they are converted.

Thus a flow may need both layers of control. For example, strip internal credentials before the adapter and configure the mapper to transmit only contract-approved headers. For sensitive data, an allowlist at the protocol boundary is far safer than accidentally forwarding every newly added application header.

~~~mermaid
flowchart TD
    A[Spring Integration Message] --> B[HeaderFilter]
    B --> C[Header mapper]
    C --> D[HTTP / JMS / AMQP / Kafka]
    D --> E[External system]
    F[Allowlist rule] -. configure mapper .-> C
~~~

For instance, a Kafka flow might keep `correlationId` for consumer reconciliation while removing `Authorization`, `X-Api-Key`, and `internalUserContext`. The Kafka header mapper then maps only contract-approved metadata. If you rely solely on a header filter while the mapper forwards all other headers, a sensitive header added in the future could leak out.

With an HTTP outbound adapter, check special HTTP headers like `Authorization` and `Cookie` alongside application-mapped headers. With JMS, check message properties and provider type limits. With AMQP and Kafka, check header mappers, supported types, and serialization rules. Exact mapping behavior depends on the Spring Integration version and adapter in use.

## 6. Header Filter Does Not Sanitize Payloads

Header filter operates only on Spring Message headers. It does not inspect or remove data inside the payload.

For example, a message has payload:

~~~json
{
  "orderId": "ORD-10025",
  "customerEmail": "customer@example.com",
  "accessToken": "secret-value"
}
~~~

If `accessToken` sits inside the JSON payload, calling `.headerFilter("accessToken")` does not alter the JSON. Use a payload transformer or design an output DTO containing only shareable fields.

Similarly, `HeaderFilter` does not automatically:

- Mask or erase data in logs already written earlier.
- Remove secrets nested inside objects within the payload.
- Remove HTTP headers already sent before the transformer ran.
- Revoke leaked tokens or credentials.
- Encrypt remaining data in the message.
- Replace authorization checks in the receiving system.

For sensitive payloads, define an explicit exchange schema, build a partner-specific DTO, or use a controlled transformer. Avoid directly serializing internal objects containing credentials, PII, or debug fields.

## 7. Processing Order and Headers to Keep

Endpoint ordering determines which headers exist at any point in time. A flow might need a token to call an authentication service, a correlation ID to tie logs together, and a tenant ID to pick an endpoint. Only after those steps should the flow strip headers forbidden from leaving the app.

Example processing order:

~~~mermaid
sequenceDiagram
    participant In as Inbound adapter
    participant Auth as Internal auth step
    participant Route as Router
    participant Filter as HeaderFilter
    participant Out as Outbound adapter

    In->>Auth: Message + token + correlationId
    Auth->>Route: Authenticated message
    Route->>Filter: Message on target route
    Note over Filter: Strip token and internal context
    Filter->>Out: Payload + allowed headers
    Out-->>In: Flow result
~~~

Principles for deciding ordering:

1. Identify which endpoints need headers for authentication, routing, reconciliation, or error handling.
2. Keep sensitive headers in the narrowest scope and for the shortest lifetime possible.
3. Filter before logging, publishing, or sending to external systems whenever those steps do not need sensitive values.
4. Check every branch of the flow. Each branch may go to a different adapter and require its own header policy.
5. Check reply flows and error flows too; error messages can carry sensitive headers from the original request.
6. Never rely on an adapter ignoring a header by default. Verify the actual adapter's mapper configuration.

Spring Integration control headers like `replyChannel` or `errorChannel` usually serve internal processing. Never send channel object references across system boundaries. Inspect the header mapper to verify framework headers are not mapped onto external protocols. A header filter can add an explicit safeguard when the flow knows the exact header names to strip.

## 8. Testing Header Filters

Tests must verify both conditions: sensitive headers are gone and required business headers remain.

Example flow test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartnerFlowConfiguration.class)
class PartnerHeaderFilterTests {

    @Autowired
    private MessageChannel partnerRequests;

    @Autowired
    private QueueChannel partnerSanitizedRequests;

    @Test
    void removesSensitiveHeadersAndKeepsCorrelationId() {
        Message<String> request = MessageBuilder
                .withPayload("{\"orderId\":\"ORD-10025\"}")
                .setHeader("Authorization", "Bearer test-token")
                .setHeader("X-Api-Key", "test-api-key")
                .setHeader("sessionToken", "test-session")
                .setHeader("correlationId", "corr-10025")
                .build();

        partnerRequests.send(request);

        Message<?> sanitized = partnerSanitizedRequests.receive(1000);

        assertThat(sanitized).isNotNull();
        assertThat(sanitized.getHeaders())
                .doesNotContainKeys(
                        "Authorization",
                        "X-Api-Key",
                        "sessionToken");
        assertThat(sanitized.getHeaders().get("correlationId"))
                .isEqualTo("corr-10025");
        assertThat(sanitized.getPayload())
                .isEqualTo(request.getPayload());
    }
}
~~~

The example assumes the flow routes output to a `QueueChannel` named `partnerSanitizedRequests`. If your project uses different channel types or bean names, adjust the test config to match. The test sends a message with three sensitive headers and a correlation ID; the received message must lack the three sensitive headers while keeping the payload and correlation ID.

Add test cases tailored to your system:

- Headers with different casing matching the exact keys created by the app.
- Sensitive headers added in an intermediate step.
- Retry branches and error flows not leaking tokens.
- Adapter header mappers sending only allowlisted metadata.
- Payloads with sensitive fields handled by a dedicated payload transformer.
- Logs and wiretaps not recording secret values.

Do not test solely by asserting the flow completes. Directly inspect the header set at the filter's output and, whenever possible, inspect the message after the adapter maps it to the target protocol.

## 9. Operations and Troubleshooting

| Symptom | Cause to Check |
|---|---|
| Header still appears in receiving system | Header filter placed after outbound adapter, wrong key name, or a flow branch bypasses the filter |
| Header disappears yet request fails | Stripped a header still needed by a downstream internal endpoint for auth or routing |
| Token still appears in logs | Logger or wiretap runs before the header filter, or logger prints the payload too |
| Unexpected header appears on Kafka/AMQP | Header mapper maps extra metadata the flow did not intend |
| Correlation ID missing in receiving system | Accidentally filtered the reconciliation header or mapper does not forward it |
| Secret still present after filtering | Value lives inside payload, nested object, or a transport header created elsewhere |

When investigating, trace messages at each channel using non-sensitive test data. Log needed header names for diagnostics without logging secret values. Check transformer order, flow branches, and adapter header mapper configs. If a leaked token is detected, follow your incident response process, including revoking or rotating credentials as needed.

Header filters must also be revisited whenever integration contracts change. A new header could carry sensitive info unknown to the existing exclusion list. Combine schema checks, mapper reviews, and protocol-boundary tests into your adapter change workflow.

## 10. Checklist Before Crossing a System Boundary

- [ ] Identified which headers contain credentials, sessions, personal data, or internal metadata.
- [ ] Header filter runs after steps using internal headers and before the outbound adapter.
- [ ] Header name list matches the exact keys generated in the flow.
- [ ] Correlation ID and required business metadata are preserved per contract.
- [ ] HTTP, JMS, AMQP, or Kafka header mapper forwards only approved data.
- [ ] `replyChannel`, `errorChannel`, and internal references are not leaked externally.
- [ ] Payload is inspected separately; do not assume `HeaderFilter` strips sensitive payload fields.
- [ ] Logging and wiretaps do not record token values or sensitive data.
- [ ] Tests confirm sensitive headers are stripped and required headers remain.
- [ ] Retry, reply, and error flow branches also comply with the filtering policy.

A header filter is a small step with a clear role in protecting messages when integrating across systems. Placing it properly, specifying the right headers to strip, and pairing it with adapter mapping rules keeps metadata crossing system boundaries under control.
