# Push subscriptions, token verification, and securing receiving endpoints

## Lesson Objectives

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module practices integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries. In messaging architectures, pull subscribers proactively fetch messages from Pub/Sub, whereas push subscriptions have Pub/Sub proactively send HTTP requests to your application. Push works well for webhooks, Cloud Run, and autoscaling services, provided the endpoint stays ready to accept requests and properly authenticates sender identity.

This lesson focuses on building a secure push receiver endpoint:

- Creating a push subscription pointing to an HTTPS endpoint.
- Understanding JSON envelopes, Base64 payloads, and payload unwrapping options.
- Verifying Pub/Sub-signed OIDC JWTs in the `Authorization` header.
- Configuring service accounts, audiences, and least-privilege IAM.
- Returning HTTP status codes to ACK/NACK messages.
- Securing Spring Boot endpoints, classifying errors, and preventing duplicate processing.
- Monitoring push latency, response codes, retries, and backlog.

After this lesson, you will be able to deploy a Spring Boot webhook receiving Pub/Sub messages with OIDC authentication, returning timely ACKs, and handling endpoint failures or overload cleanly.

## 1. How do push subscriptions work?

### 1.1. Pub/Sub invokes the endpoint

With push delivery, Pub/Sub dispatches each message as an HTTP POST to a configured endpoint. The endpoint must expose a public HTTPS address with a valid TLS certificate and accept traffic from the Pub/Sub service.

```mermaid
sequenceDiagram
    participant P as Publisher
    participant T as Pub/Sub topic
    participant S as Push subscription
    participant A as Spring Boot endpoint
    P->>T: Publish message
    T->>S: Message ready
    S->>A: HTTPS POST + JWT + JSON envelope
    A->>A: Verify JWT
    A->>A: Decode and process message
    A-->>S: HTTP 204
    S-->>T: ACK message
```

Pub/Sub adapts delivery rates based on success response rates and endpoint latency. Push does not require the application to run a pull loop or hold streaming subscriber connections.

### 1.2. Comparing push and pull

| Criterion | Push subscription | Pull subscription |
| --- | --- | --- |
| Delivery initiator | Pub/Sub invokes endpoint | Application invokes Pull/StreamingPull |
| Protocol | HTTPS POST | Pub/Sub API and client libraries |
| ACK | HTTP success status | `ack()`/acknowledgment API |
| NACK | Unacceptable HTTP status or timeout | `nack()` or ack deadline expiration |
| Per-message deadline extension | Cannot call `modifyAckDeadline` per push message | Can extend ack deadlines |
| Scaling | Pub/Sub scales push window via responses/latency | Application tunes pull streams, flow control, and concurrency |
| Best fit | Webhooks, HTTP services, Cloud Run | Long-running workers, batches, direct ACK response control |

Push delivery can still redeliver messages. If an application finishes processing but the response is lost en route back to Pub/Sub, Pub/Sub may resend the same message. Thus, endpoints must be idempotent.

Push subscriptions do not support Pub/Sub exactly-once delivery; delivery semantics remain at-least-once. An inbox/idempotency check keyed by event ID is mandatory when side effects must not repeat.

### 1.3. Push does not batch messages

A push subscription delivers one user message per push request. If your application needs batching, aggregate work at the application layer after receiving and durably persisting messages; never assume a single HTTP POST carries multiple messages like a pull response.

## 2. HTTP requests and the Pub/Sub message envelope

### 2.1. Default wrapped format

By default, Pub/Sub delivers messages inside a JSON envelope. The `message.data` field is Base64-encoded because the original payload is raw bytes:

```json
{
  "message": {
    "data": "eyJldmVudElkIjoiZXZ0LTEwMDEiLCJvcmRlcklkIjoib3JkLTEwMDEifQ==",
    "attributes": {
      "eventType": "OrderCreated",
      "schemaVersion": "1"
    },
    "messageId": "2070443601311540",
    "message_id": "2070443601311540",
    "publishTime": "2026-11-24T08:30:00.000Z",
    "publish_time": "2026-11-24T08:30:00.000Z"
  },
  "subscription": "projects/acme-commerce-dev/subscriptions/orders-push-sub",
  "deliveryAttempt": 2
}
```

Notable fields:

| Field | Meaning |
| --- | --- |
| `message.data` | Base64-encoded original payload |
| `message.attributes` | String metadata attached by publisher |
| `message.messageId` | Pub/Sub-assigned message ID |
| `message.publishTime` | Timestamp recorded by Pub/Sub on publish |
| `message.orderingKey` | Ordering key if present on message |
| `subscription` | Full name of the subscription sending the request |
| `deliveryAttempt` | Approximate delivery attempt count when DLQ policy is enabled |

Some fields appear in both camelCase and snake_case for compatibility. DTOs should ignore unknown fields and rely strictly on fields defined in the application contract.

### 2.2. Decoding the payload

In Java:

```java
byte[] payload = Base64.getDecoder()
        .decode(envelope.message().data());

OrderCreated event = objectMapper.readValue(
        payload,
        OrderCreated.class
);
```

Do not Base64-decode a second time if payload unwrapping is enabled. With wrapped delivery, `data` in the envelope is Base64; with unwrapped delivery, the HTTP body directly holds the raw payload.

### 2.3. Payload unwrapping

Push subscriptions offer an option to strip the JSON wrapper:

- **Wrapped:** request body is the JSON envelope, retaining `messageId`, attributes, publish time, and metadata in the body.
- **Unwrapped:** request body contains only the raw original payload.
- **Write metadata:** when enabled alongside unwrapped delivery, Pub/Sub moves selected stripped metadata into HTTP headers.

Wrapped delivery is usually easier to operate because message ID, attributes, and subscription name arrive together in the request. Enable unwrapped mode only when an endpoint expects raw payloads or integrates with a fixed-wire-format webhook. Unwrapping without Write metadata strips metadata needed for deduplication and diagnostics.

## 3. HTTP status codes act as ACK/NACK

### 3.1. Statuses confirming success

An endpoint ACKs a message by returning one of these status codes:

| HTTP status | Meaning |
| --- | --- |
| `102` | Processing |
| `200` | OK |
| `201` | Created |
| `202` | Accepted |
| `204` | No Content |

In Spring Boot webhooks, `204 No Content` is typically ideal because Pub/Sub only needs confirmation of successful intake; no response body is needed.

### 3.2. Statuses causing Pub/Sub to retry

Any status outside the list above is treated as a negative acknowledgment. Examples:

- `400`: invalid payload.
- `401`/`403`: authentication or authorization failure.
- `429`: endpoint overloaded.
- `500`/`503`: server or transient dependency error.
- Timeout/connection reset: Pub/Sub receives no success response.

Pub/Sub retries messages per its retry policy and push backoff. Therefore, do not return `400` for permanently broken messages and let them retry forever. Persist them durably to quarantine/DLQ and return an accepted success status, or configure a dead-letter topic to isolate messages after max delivery attempts.

### 3.3. Commit before returning a success status

Safe processing sequence:

1. Verify JWT.
2. Parse envelope and validate payload.
3. Write inbox/event ID and update database inside a single transaction.
4. Wait for the transaction to commit.
5. Return HTTP 204.

If you return 204 before committing, the process may crash after responding, leaving the message ACKed while business state was lost. If the commit succeeds but the response is lost, the message may be redelivered; inbox/idempotency must prevent repeated side effects.

### 3.4. Cannot extend deadlines for push messages

Push endpoints have no API to modify the ack deadline per message. Processing time must fit inside the subscription's ack deadline. For longer tasks:

- Increase the subscription ack deadline within service limits and align endpoint timeouts.
- Save a durable job record during the request, return a success status once saved, and process asynchronously.
- If per-message lease extension is required, consider a pull subscription.

Never return a success status immediately after pushing a payload onto a non-durable in-memory queue.

## 4. Authenticating push requests with OIDC JWTs

### 4.1. Pub/Sub sends a JWT in the Authorization header

When authenticated push is enabled, Pub/Sub signs an OpenID Connect JWT and attaches it in the HTTP header:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Key claims inside the JWT:

| Claim | Meaning | Endpoint check |
| --- | --- | --- |
| `iss` | Issuer, typically `https://accounts.google.com` | Must match trusted issuer |
| `aud` | Audience the token was issued for | Must match configured audience |
| `email` | Push authentication service account email | Must match the service account configured on the subscription |
| `email_verified` | Email verification status | Must be `true` |
| `exp` | Expiration timestamp | Must not be expired |
| `iat` | Issued-at timestamp | Validate normally; do not enforce a tight multi-second window |
| `sub` | Service account subject ID | Optionally logged for auditing |

Google signs the token. The endpoint must verify the signature against Google's public keys/JWKs, check validity timestamps, and validate identity/audience claims. Base64-decoding a JWT alone is not signature verification.

Google may reuse signed tokens for a window; a push request may carry a token issued up to an hour earlier. Never reject a token merely because `iat` is older than a few seconds. Rely on `exp`, signature, issuer, audience, and email.

### 4.2. Audience must match

Audience is a string configured on the subscription. If not overridden, Pub/Sub defaults audience to the endpoint URL. You can specify a dedicated audience so the endpoint checks a stable identifier:

```text
https://orders.example.com/pubsub/push
```

The JWT's audience must match what the application expects. Never infer expected audience from request headers like `Host` or `X-Forwarded-Host`; configure a trusted value from environment/config.

If the endpoint sits behind Identity-Aware Proxy (IAP), the audience may need to be the IAP Client ID rather than the endpoint URL. Check your specific IAP setup.

### 4.3. Distinguishing the two service accounts

Authenticated push involves two distinct identities:

| Identity | Role |
| --- | --- |
| Pub/Sub service agent | Service identity that signs/mints OIDC tokens |
| User-managed push auth service account | Identity appearing in the JWT `email` claim and verified by the endpoint |

The Pub/Sub service agent takes the form:

```text
service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com
```

The push auth service account is one you create, such as:

```text
pubsub-push-invoker@acme-commerce-dev.iam.gserviceaccount.com
```

The push auth service account must reside in the same project as the subscription. Never use the service agent as an application runtime identity or grant the service agent access to business databases.

## 5. Configuring IAM for authenticated push

### 5.1. Creating the push auth service account

```bash
gcloud iam service-accounts create pubsub-push-invoker \
  --project=acme-commerce-dev \
  --display-name="Pub/Sub push invoker"
```

Set variables:

```bash
PROJECT_ID="acme-commerce-dev"
PROJECT_NUMBER="123456789012"
PUSH_AUTH_SA="pubsub-push-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
PUBSUB_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
```

Project and account values here are placeholders; replace them with real environment resources.

### 5.2. Allowing the Pub/Sub service agent to mint tokens

The Pub/Sub service agent requires `iam.serviceAccounts.getOpenIdToken`, included in `roles/iam.serviceAccountTokenCreator`, on the push auth service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "${PUSH_AUTH_SA}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role="roles/iam.serviceAccountTokenCreator"
```

This lets the Pub/Sub service agent sign/mint tokens. Without it, push requests cannot be authenticated and the subscription cannot deliver messages as expected.

### 5.3. Allowing subscription creators to attach the service account

The principal creating or updating the subscription needs `iam.serviceAccounts.actAs` on the push auth service account, commonly via `roles/iam.serviceAccountUser`:

```bash
gcloud iam service-accounts add-iam-policy-binding "${PUSH_AUTH_SA}" \
  --project="${PROJECT_ID}" \
  --member="user:platform-admin@example.com" \
  --role="roles/iam.serviceAccountUser"
```

Replace `user:platform-admin@example.com` with the actual principal or authorized operations group. Do not grant this role broadly to all developers or runtime accounts.

### 5.4. Allowing the service account to invoke Cloud Run

If the endpoint is an IAM-protected Cloud Run service, the push auth service account needs `roles/run.invoker` on that exact Cloud Run service:

```bash
gcloud run services add-iam-policy-binding orders-api \
  --project="${PROJECT_ID}" \
  --region=asia-southeast1 \
  --member="serviceAccount:${PUSH_AUTH_SA}" \
  --role="roles/run.invoker"
```

Cloud Run can validate the token at the platform layer before traffic enters your container. In that model, the service IAM binding is required for Pub/Sub to invoke the endpoint. Even if you also verify JWTs inside the application, ensure no public ingress path bypasses Cloud Run IAM.

For App Engine/IAP or Cloud Functions, grant the invoker/IAP role appropriate to that endpoint type.

### 5.5. Least-privilege principles

- The Pub/Sub service agent only needs Token Creator on the push auth service account.
- The push auth service account only needs permission to invoke the endpoint.
- The Spring Boot runtime service account only needs permissions for databases, secrets, and business services the app uses.
- Subscription administrators only need `actAs` on the push auth service account plus subscription management permissions.
- Never generate and embed JSON service account keys in the app; Pub/Sub mints tokens on the service account's behalf via IAM.

## 6. Creating and updating push subscriptions

### 6.1. Creating with gcloud

Example:

```bash
PUSH_ENDPOINT="https://orders.example.com/pubsub/push"
PUSH_AUDIENCE="https://orders.example.com/pubsub/push"

gcloud pubsub subscriptions create orders-push-sub \
  --project="${PROJECT_ID}" \
  --topic=orders \
  --push-endpoint="${PUSH_ENDPOINT}" \
  --push-auth-service-account="${PUSH_AUTH_SA}" \
  --push-auth-token-audience="${PUSH_AUDIENCE}" \
  --ack-deadline=60 \
  --min-retry-delay=10s \
  --max-retry-delay=300s
```

The endpoint must be public HTTPS with a valid certificate. Audience is the string the Spring endpoint validates.

If running on Cloud Run, the audience usually needs to match the Cloud Run service URL or a configured custom audience on the service. When the endpoint URL includes a path like `/pubsub/push`, do not assume the path-suffixed URL works as the Cloud Run audience unless the service explicitly accepts that custom audience. Keep `PUSH_AUDIENCE` synchronized across Cloud Run config and the app's validator.

### 6.2. Updating push configuration

Change endpoint or identity:

```bash
gcloud pubsub subscriptions update orders-push-sub \
  --push-endpoint="https://orders-v2.example.com/pubsub/push" \
  --push-auth-service-account="${PUSH_AUTH_SA}" \
  --push-auth-token-audience="https://orders-v2.example.com/pubsub/push"
```

Verify after changing:

```bash
gcloud pubsub subscriptions describe orders-push-sub
```

Check `pushConfig.pushEndpoint`, `pushConfig.oidcToken.serviceAccountEmail`, `pushConfig.oidcToken.audience`, retry policy, and ack deadline.

### 6.3. Payload unwrapping and dead-letter

Push subscriptions also support retry policies, dead-letter topics, and payload unwrapping. If the endpoint needs a DLQ, configure a dead-letter policy and grant IAM to the Pub/Sub service agent as covered in the retry/DLQ lesson. Enabling authenticated push does not create a DLQ automatically.

### 6.4. Private network endpoints

Pub/Sub operates outside your VPC and cannot push directly to private VPC IP addresses. If a Spring Boot endpoint has only a private address, use Eventarc as a routing layer to Cloud Run/Workflows or VPC-hosted services. Never punch arbitrary firewall holes to expose private endpoints publicly; design an authenticated, network-controlled ingress path.

## 7. Verifying JWTs in Spring Boot

### 7.1. Using Spring Security OAuth2 Resource Server

For Spring Boot running on GKE, Compute Engine, or team-managed HTTP platforms, use Spring Security OAuth2 Resource Server to validate Bearer JWTs. Nimbus verifies signatures against Google's JWKs, while custom validators check issuer, audience, email, and `email_verified`.

Push deliveries arrive via an HTTP controller like a webhook. `PubSubTemplate.subscribe()` is an API for pull/streaming pull; do not use it to receive push requests. `PubSubTemplate`/`PubSubAdmin` can still be used for publishing or resource management if needed.

Dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Trusted configuration in `application.yml`:

```yaml
app:
  pubsub:
    push:
      audience: https://orders.example.com/pubsub/push
      service-account: pubsub-push-invoker@acme-commerce-dev.iam.gserviceaccount.com
```

Do not place service account keys in configuration. Here `service-account` is purely an identity email for claim matching, not a secret credential.

### 7.2. Configuring `JwtDecoder`

```java
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class PubSubPushJwtConfiguration {

    @Bean
    JwtDecoder pubSubPushJwtDecoder(
            @Value("${app.pubsub.push.audience}") String expectedAudience,
            @Value("${app.pubsub.push.service-account}") String expectedServiceAccount) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri("https://www.googleapis.com/oauth2/v3/certs")
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTimeValidator =
                JwtValidators.createDefaultWithIssuer(
                        "https://accounts.google.com");

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            boolean matches = jwt.getAudience().stream()
                    .anyMatch(value -> value.equalsIgnoreCase(expectedAudience));
            return matches
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error("invalid_token", "Invalid audience", null));
        };

        OAuth2TokenValidator<Jwt> identityValidator = jwt -> {
            String email = jwt.getClaimAsString("email");
            Boolean verified = jwt.getClaim("email_verified");
            boolean expectedIdentity = expectedServiceAccount.equalsIgnoreCase(email);
            if (expectedIdentity && Boolean.TRUE.equals(verified)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Unexpected push identity", null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                issuerAndTimeValidator,
                audienceValidator,
                identityValidator
        ));
        return decoder;
    }
}
```

`NimbusJwtDecoder` fetches public keys by `kid` from Google's JWK endpoint and handles key rotation. `JwtValidators.createDefaultWithIssuer()` checks the issuer and default timestamp claims; custom validators verify audience, email, and email verification. If the JWT is invalid, Spring Security rejects with 401 before the controller parses the body.

### 7.3. Protecting the push route

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PubSubPushSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.ignoringRequestMatchers("/pubsub/push"))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/pubsub/push").authenticated()
                        .anyRequest().permitAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

This is a minimal illustrative configuration. In applications exposing user APIs, replace `permitAll()` with real authentication/authorization policies for other routes. Exempt CSRF only for cookie-less machine-to-machine webhooks; never disable CSRF application-wide by default.

Spring Security reads `Authorization: Bearer ...`, invokes `JwtDecoder`, and lets requests reach the controller only when signature, issuer, timestamps, audience, and identity all pass. Never manually parse a JWT inside a controller and trust unverified claims.

## 8. Building the HTTP receiving endpoint

### 8.1. DTO for wrapped push requests

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubPushEnvelope(
        PushMessage message,
        String subscription,
        Integer deliveryAttempt
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record PushMessage(
            String data,
            Map<String, String> attributes,
            @JsonAlias("message_id")
            String messageId,
            @JsonAlias("publish_time")
            String publishTime,
            String orderingKey
    ) {}
}
```

The DTO ignores unknown fields for forward compatibility as Pub/Sub adds metadata. If your app may receive snake_case aliases, declare `@JsonAlias` on the corresponding fields; do not require every metadata field to be present since minimal envelopes may include only `data`, message ID, and subscription.

The DTO and controller below assume **wrapped delivery**. If unwrapped payloads are enabled, the endpoint must accept a raw body (such as `byte[]`) and read metadata from headers populated by Write metadata; do not bind raw requests to `PubSubPushEnvelope`.

### 8.2. Controller returns success only after durable persistence

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Base64;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/pubsub")
public class OrderPushController {
    private final ObjectMapper objectMapper;
    private final OrderService orderService;
    private final QuarantineService quarantineService;

    public OrderPushController(
            ObjectMapper objectMapper,
            OrderService orderService,
            QuarantineService quarantineService) {
        this.objectMapper = objectMapper;
        this.orderService = orderService;
        this.quarantineService = quarantineService;
    }

    @PostMapping("/push")
    public ResponseEntity<Void> receive(
            @RequestBody PubSubPushEnvelope envelope) {
        final OrderCreated event;
        try {
            byte[] payload = Base64.getDecoder()
                    .decode(envelope.message().data());
            event = objectMapper.readValue(payload, OrderCreated.class);
        } catch (IllegalArgumentException | JsonProcessingException invalidPayload) {
            quarantineService.store(envelope, "INVALID_PAYLOAD");
            return ResponseEntity.noContent().build();
        }

        try {
            // @Transactional method commits before returning.
            orderService.processIdempotently(
                    event, envelope.message().messageId());
            return ResponseEntity.noContent().build();
        } catch (TransientDependencyException temporaryFailure) {
            // Non-success status: Pub/Sub retries per retry policy/push backoff.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        } catch (PermanentBusinessException permanentFailure) {
            // ACK only after durable quarantine persistence succeeds.
            quarantineService.store(envelope, "PERMANENT_BUSINESS_FAILURE");
            return ResponseEntity.noContent().build();
        }
    }
}
```

`OrderService.processIdempotently()` must write the inbox record and side effects in the same transaction. When the transactional method returns normally, the transaction proxy commits before the controller returns HTTP 204. `QuarantineService.store()` must also persist durably; if quarantine storage fails, let the exception yield a 5xx response so Pub/Sub retries.

This example intentionally ACKs invalid payloads after saving them to quarantine successfully. If your policy prefers Pub/Sub forwarding to a DLQ, return a non-success status and let the dead-letter policy isolate the message. Never return a success status just because an error was logged.

If the JSON envelope itself cannot be parsed, Spring may return 400 before invoking the controller. Decide explicitly whether that is a retryable error or a poison request needing quarantine; to quarantine raw bodies, use an `HttpMessageNotReadableException` handler capable of capturing and persisting raw request bytes before returning a success status.

### 8.3. Choosing status codes by error type

| Processing outcome | HTTP response | Pub/Sub |
| --- | --- | --- |
| Transaction commits successfully | `204` | ACK |
| Event already processed in inbox | `204` | ACK |
| Transient dependency failure | `503` | NACK/retry |
| Database timeout before commit | `503` | NACK/retry |
| Invalid payload durably quarantined | `204` | ACK |
| Quarantine store fails | `500`/`503` | NACK/retry |
| Missing/invalid JWT signature or audience | `401` | Delivery fails; check auth/IAM |
| Service account unauthorized on endpoint | `403` | Delivery fails; check authorization |

Authentication errors should never be silenced by ACKing messages; fix IAM/audience configuration instead. While an endpoint keeps returning 401/403, Pub/Sub continues retrying per retry/backoff and backlog grows.

## 9. Cloud Run: platform-level authentication

If Spring Boot runs on Cloud Run and the service requires authentication, Cloud Run can verify Google-signed identity tokens before requests enter the container. In this setup:

1. Configure authenticated push with a user-managed push auth service account.
2. Grant `roles/run.invoker` to that service account on the target Cloud Run service.
3. Grant `roles/iam.serviceAccountTokenCreator` to the Pub/Sub service agent on the push auth service account.
4. Configure the audience to match the Cloud Run service URL or a custom audience accepted by Cloud Run.
5. The application must still validate/enforce body, schema, idempotency, and transactions.

Cloud Run platform authentication does not automatically populate Spring's `@AuthenticationPrincipal Jwt` inside the container. If your code needs to inspect claims, also validate the JWT with Spring Security as shown above or use an appropriate platform-provided identity mechanism. Never assume platform auth is protecting you while leaving another public ingress path open to bypass IAM.

Example IAM binding:

```bash
gcloud run services add-iam-policy-binding orders-api \
  --region=asia-southeast1 \
  --member="serviceAccount:${PUSH_AUTH_SA}" \
  --role="roles/run.invoker"
```

After changing IAM, policy propagation may take some time. During propagation, Pub/Sub may receive 403 responses from the endpoint.

## 10. Securing the HTTP receiving endpoint

### 10.1. Accept POST only and constrain requests

- Expose only required routes, such as `POST /pubsub/push`.
- Cap request body sizes at load balancers/API gateways and Spring server to match real message limits.
- Set processing timeouts below the subscription ack deadline, leaving buffer for commits and responses.
- Serve over HTTPS with valid certificates; never accept tokens over unencrypted HTTP.
- Validate `Content-Type` and JSON schema; reject oversized or malformed bodies.
- Do not trust `X-Forwarded-For`, `Host`, or query parameters as identity proof unless proxy trust boundaries are explicitly configured.

### 10.2. Never roll a naive JWT verifier

Avoid:

- Merely Base64-decoding a JWT and reading `email`/`aud`.
- Checking only that the header starts with `Bearer` without verifying signatures.
- Checking only `email` while ignoring issuer, audience, and expiration.
- Accepting any service account in the project.
- Fetching certificates/JWKs on every request without library-managed caching.
- Calling the tokeninfo endpoint on every request under high load when offline verification via Google public keys works.

Use a maintained OIDC/JWT library supporting key rotation and full claim checks. If caching keys manually, handle new `kid` values and Google's rotation schedule.

### 10.3. Token verification does not replace authorization

A valid JWT proves the request was signed by the configured identity. Applications still need authorization by subscription/topic/event type when one endpoint handles multiple streams. For example, allow only `orders-push-sub` to submit `OrderCreated`; do not derive all business permissions solely from the email claim.

If multiple push subscriptions target the same endpoint, consider an allowlist of subscription names in the envelope and a subscription-to-handler map. Remember the envelope body is trustworthy only after the JWT is verified; checking the subscription name never replaces token validation.

### 10.4. Protecting data and logs

- Never log raw JWTs or `Authorization` headers.
- Never log full payloads containing personal info, payment data, or secrets.
- Record message ID, event ID, subscription, delivery attempt, response status, and correlation ID per policy.
- Store secrets/audience configuration in Secret Manager or controlled deployment config; while audience and service account emails are not private keys, manage them under change control.
- Apply least-privilege IAM to service accounts, runtimes, and DLQ/quarantine stores.

### 10.5. Private endpoints and VPC Service Controls

Pub/Sub cannot call private VPC addresses directly. Use Eventarc to route to VPC-resident services when needed. In projects with VPC Service Controls, push endpoints are restricted by target type and URL; custom domains may be unsupported in some configurations. Consult VPC Service Controls documentation before finalizing endpoint architecture.

## 11. Retry policies and push backoff

### 11.1. Two independent mechanisms

Push subscriptions are governed by two mechanisms:

- **Subscription retry policy:** immediate redelivery or exponential backoff when a message is not ACKed.
- **Push backoff:** Pub/Sub slows or pauses requests when the endpoint returns frequent NACKs or responds slowly.

Both operate independently. When both apply, actual wait time is driven by the larger of push backoff and retry backoff. Push backoff uses an exponential algorithm ranging roughly from 100 ms to 60 seconds.

Example retry policy configuration:

```bash
gcloud pubsub subscriptions update orders-push-sub \
  --min-retry-delay=10s \
  --max-retry-delay=300s
```

Do not treat `min-retry-delay` as an exact redelivery schedule. Push backoff and endpoint health can stretch actual intervals.

### 11.2. Adaptive push window

Pub/Sub adjusts outstanding request concurrency based on response quality:

- When the endpoint ACKs over 99% of messages with average latency under one second, the push window can expand to raise throughput.
- When average latency exceeds one second or the ACK rate drops below 99%, the window shrinks to protect the endpoint.
- Beyond roughly 3,000 outstanding messages per region, the window grows linearly to avoid flooding the endpoint.

This is a service-managed adaptive mechanism, not a fixed concurrency setting in Spring Boot. Fast, consistent success responses let Pub/Sub widen the delivery window; slow or failing endpoints grow backlog.

### 11.3. Do not abuse HTTP 429 as a generic throttle

HTTP 429 is not an accepted Pub/Sub ACK status, so it acts as a NACK and triggers retry/backoff. If an endpoint is overloaded, returning 503 signals a transient failure while you pair it with capacity planning, bounded worker queues, and scaling out. Continuously returning 429 without a recovery plan simply fuels retries and backlog growth.

To pause push delivery temporarily, you can switch the subscription to pull; the change can take several minutes to take effect. Do this only with an alternate consumer plan and backlog-handling strategy ready.

## 12. Monitoring push subscriptions

### 12.1. Key metrics

| Metric | Labels/meaning | How to use |
| --- | --- | --- |
| `subscription/push_request_count` | Push count grouped by `response_code` and `response_class` | Track ACK, 4xx, 5xx, and timeout rates |
| `subscription/push_request_latencies` | Distribution of push request latencies | Monitor endpoint p50/p95/p99 |
| `subscription/num_outstanding_messages` | Currently outstanding messages | Spot an endpoint falling behind |
| `subscription/oldest_unacked_message_age_by_region` | Age of oldest unacked message | Detect stuck backlog |
| `subscription/delivery_latency_health_score` | Delivery latency health score | Identify factors slowing delivery |
| `subscription/dead_letter_message_count` | Messages forwarded to DLQ | Spot poison messages or prolonged failures |

Common `response_class` values include `ack`, `deadline_exceeded`, `internal`, `invalid`, `remote_server_4xx`, `remote_server_5xx`, and `unreachable`.

### 12.2. Required dashboards

Include at minimum:

1. ACK / response-class ratios by subscription.
2. Push request latencies (p50/p95/p99).
3. Outstanding messages and oldest unacked age.
4. DLQ counts and forwarding rate.
5. HTTP statuses/exceptions on the Spring endpoint.
6. CPU, memory, thread pools, database connection pools, and downstream latency.

Pub/Sub recommends keeping outstanding messages low in most scenarios; roughly under 1,000 is a starting reference, not a fixed cap or throughput guarantee. The service may adjust limits for high-throughput workloads.

### 12.3. Suggested alerts

- Non-`ack` `response_class` counts climbing steadily.
- Sustained `deadline_exceeded` occurrences.
- `remote_server_4xx` rising: inspect JWTs, audience, service accounts, and IAM.
- `remote_server_5xx` rising: inspect application/dependencies.
- `push_request_latencies` p95 breaching SLO.
- Outstanding messages and oldest unacked age rising together.
- Sudden spike in DLQ count.

Avoid alerting on single brief spikes. Combine error rate, latency, and backlog to distinguish short bursts from sustained incidents.

## 13. Testing push endpoints

### 13.1. Unit testing the JWT validator

Build test cases for `JwtDecoder` or validators:

| Token | Outcome |
| --- | --- |
| Valid signature, valid issuer, matching audience, matching email, email verified | Accepted |
| Tampered signature | Rejected |
| Non-Google issuer | Rejected |
| Mismatched audience | Rejected |
| Email from a different service account | Rejected |
| `email_verified=false` | Rejected |
| Expired token | Rejected |
| Missing Authorization Bearer header | Spring Security returns 401 |

Never test signature verification using fake tokens with only a Base64 payload. Use JWTs signed by a test keypair and a test JWK server for unit tests, then verify real tokens in a sandbox.

### 13.2. Unit testing the controller

Mock `OrderService` and `QuarantineService` to verify:

- Transaction/business handler succeeds → controller returns 204.
- Event already present in inbox → returns 204 with no duplicate side effects.
- Transient dependency failure → returns 503.
- Invalid payload durably quarantined → returns 204.
- Quarantine store failure → 5xx response.
- Envelope missing `message` or `data` → controlled error handling, never a fake 204.

Controller tests do not replace JWT filter tests; use `spring-security-test` to verify authenticated routes separately.

### 13.3. Local testing with MockMvc

You can test HTTP routing and controllers without Pub/Sub:

Add test dependency:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPushControllerTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsAuthenticatedPush() throws Exception {
        String body = """
                {
                  "message": {
                    "data": "eyJldmVudElkIjoiZXZ0LTEwMDEifQ==",
                    "messageId": "msg-1001"
                  },
                  "subscription": "projects/test/subscriptions/orders-push-sub"
                }
                """;

        mockMvc.perform(post("/pubsub/push")
                        .with(jwt().jwt(jwt -> jwt
                                .issuer("https://accounts.google.com")
                                .audience(List.of(
                                        "https://orders.example.com/pubsub/push"))
                                .claim("email",
                                        "pubsub-push-invoker@acme-commerce-dev.iam.gserviceaccount.com")
                                .claim("email_verified", true)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isNoContent());
    }
}
```

This example uses a mock JWT to test authorization/controller mapping. `jwt()` in `spring-security-test` injects a synthetic `Authentication` for testing; it does not verify Google signatures or prove your JWK decoder works. Keep dedicated tests for `JwtDecoder`.

### 13.4. Cloud sandbox tests with a real push subscription

In a sandbox project:

1. Deploy the HTTPS endpoint.
2. Create the push auth service account and grant IAM permissions.
3. Create a push subscription with `--push-auth-service-account` and audience.
4. Publish a test message.
5. Verify Spring Security accepts the JWT.
6. Verify the controller decodes the payload and persists the event.
7. Verify the 204 response ACKs the message.
8. Make the endpoint return 503 once then 204; observe redelivery.
9. Send a token with a mismatched audience/email to a dedicated test endpoint and verify 401.
10. Slow down a test dependency to observe push latency/backoff.

The Pub/Sub emulator can help test envelopes, payload decoding, and business handlers, but it cannot replace testing authenticated push JWTs, service agent IAM, or push windows on the real service.

### 13.5. Testing duplicates

Push delivery is at-least-once. Simulate an endpoint committing to the database and dropping the connection before returning 204. Pub/Sub may resend the message. Expected outcomes:

- The same event ID produces only one business side effect.
- The redelivered request hits the inbox and returns 204.
- No duplicate order/payment rows are created.
- Logs/metrics record the duplicate without logging sensitive payloads.

## 14. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Subscription sends no requests | Wrong endpoint URL, non-public HTTPS, or TLS certificate error | Check URL, DNS, certificate, and network |
| HTTP 401 | Missing JWT or invalid signature/issuer/exp/audience | Check Bearer header, JWKs, audience, and system clock |
| HTTP 403 | Push auth service account lacks invoker role or firewall/network blocks | Check `roles/run.invoker`, IAP, ingress, and service agent |
| `permission denied` creating subscription | Creator lacks `iam.serviceAccounts.actAs` | Grant `roles/iam.serviceAccountUser` on the push auth service account |
| Failed to mint OIDC token | Pub/Sub service agent lacks Token Creator | Grant `roles/iam.serviceAccountTokenCreator` to service agent on push auth SA |
| Valid JWT rejected by app | Audience/email configuration mismatch | Compare `aud`, `email`, `email_verified` with subscription settings |
| Endpoint receives unparseable body | App expects raw body while subscription is wrapped or vice versa | Align payload unwrapping and DTO |
| Payload decoding fails | Forgot Base64 decode or decoded twice | Decode strictly once for wrapped delivery |
| Duplicate messages | Endpoint committed but response was lost/timed out | Enforce inbox/idempotency by event ID |
| Backlog growing, high `deadline_exceeded` | Slow endpoint, timeouts, or overload | Reduce synchronous work, scale capacity, inspect downstream |
| Push latency spikes after deploy | Cold starts, exhausted thread pools, or small DB pool | Check startup times, warm capacity, and connection pools |
| Persistent 4xx/5xx | Exception handler returns wrong status | Classify permanent vs. transient errors and configure a DLQ |
| DLQ receives no messages | Missing dead-letter policy or service agent IAM | Check DLQ policy and Pub/Sub service agent permissions |

### 14.1. Ordered diagnostic steps

1. Run `gcloud pubsub subscriptions describe orders-push-sub`.
2. Verify `pushEndpoint`, `oidcToken.serviceAccountEmail`, and `oidcToken.audience`.
3. Verify the push auth service account belongs to the same project as the subscription.
4. Verify the Pub/Sub service agent holds Token Creator on the push auth service account.
5. Verify the push auth service account has permission to invoke the endpoint.
6. Verify JWT issuer, audience, email, email verification, and expiration.
7. Inspect HTTP response codes and latencies in Cloud Monitoring.
8. Inspect retry policy, push backoff, backlog, and DLQ.

## 15. Comparison with AWS and Azure

| Aspect | Google Cloud Pub/Sub push | AWS | Azure |
| --- | --- | --- | --- |
| Model | Pub/Sub POSTs to an HTTPS endpoint | SNS HTTP/S subscription or EventBridge API destination | Event Grid webhook; Service Bus normally uses receivers/processors |
| Authentication | Pub/Sub-signed OIDC JWT, service account, and audience | SNS raw delivery/signature verification or endpoint/API destination auth by service | Event Grid validation handshake and Microsoft Entra ID/webhook auth per config |
| ACK | HTTP statuses `102`, `200`, `201`, `202`, `204` | HTTP success response per SNS protocol; SQS consumers delete messages | HTTP success response per Event Grid; Service Bus completes messages via SDK |
| Retry | Subscription retry policy plus push backoff | SNS delivery retry policy or EventBridge retry policy | Event Grid retry policy and dead-letter destination |
| Per-message extension | No `modifyAckDeadline` on push | No direct equivalent to SQS pull visibility timeout | Event Grid webhooks have no lock renewal like Service Bus |
| Duplicates | At-least-once; idempotent consumer | Redelivery possible; idempotent consumer | Redelivery possible; idempotent consumer |

Do not equate push subscriptions with SQS/Service Bus receivers. AWS SNS and Azure Event Grid resemble webhook push models; SQS and Service Bus receivers resemble pull/lock models. When migrating clouds, redesign token/signature validation, HTTP acknowledgments, retries, and dead-lettering to fit the target service.

## Summary

Push subscriptions let Pub/Sub send HTTP POST requests to an HTTPS endpoint. With wrapped delivery, payloads arrive Base64-encoded in `message.data`; endpoints return an accepted success status (`102`, `200`, `201`, `202`, or `204`) to ACK. Any other status or timeout triggers redelivery; push does not allow modifying ack deadlines per message.

Authenticated push attaches a Google-signed OIDC JWT in `Authorization: Bearer`. Endpoints must verify the signature, issuer, expiration, audience, email, and `email_verified`. The Pub/Sub service agent needs Token Creator on the push auth service account; subscription creators need `actAs`; and the push auth service account needs endpoint invocation rights such as `roles/run.invoker` on Cloud Run.

Spring Boot can use Spring Security OAuth2 Resource Server with Google JWKs to verify JWTs. Controllers must return success statuses only after business transactions or quarantine records commit durably. Because push remains at-least-once, inbox/idempotency keyed by event ID is mandatory. Monitor `push_request_count`, `push_request_latencies`, outstanding messages, oldest unacked age, and DLQs to catch slow endpoints or IAM misconfigurations.

## References

- [Google Cloud Pub/Sub — Push subscriptions](https://docs.cloud.google.com/pubsub/docs/push) — workflow, wrapped/unwrapped payloads, HTTP ACK statuses, push backoff, and delivery windows.
- [Google Cloud Pub/Sub — Authentication for push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions) — OIDC JWTs, claims, service agent, Token Creator, and token validation.
- [Google Cloud Pub/Sub — Create push subscriptions](https://docs.cloud.google.com/pubsub/docs/create-push-subscription) — HTTPS endpoints, audiences, service accounts, payload unwrapping, and private VPC limitations.
- [Google Cloud Pub/Sub — Monitor Pub/Sub](https://docs.cloud.google.com/pubsub/docs/monitoring) — push response counts, latencies, outstanding messages, and delivery health.
- [Google Cloud Pub/Sub — Troubleshoot push subscriptions](https://docs.cloud.google.com/pubsub/docs/push-troubleshooting) — endpoint errors, response classes, and retries.
- [Google Cloud Run — Authenticate service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service) — `roles/run.invoker` and authenticated invocation.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `JwtDecoder`, issuer/audience validation, and JWK rotation.
