# Webhook Signature Verification, Event Tokens, and Replay Protection

Webhooks and event callbacks allow Spring Boot to receive notifications from payment gateways, CRMs, object storage, message brokers, or cloud services. A single request may instruct the application to update an order, issue an invoice, grant file download access, or trigger a workflow. If an endpoint merely accepts JSON and processes it immediately, attackers can forge requests, tamper with payloads, or replay valid notifications repeatedly.

A secure webhook must answer three independent questions:

1. **Is the sender trustworthy?** Verify the signature, MAC, or authentication token provided by the sender.
2. **Is the message intact?** The signature must bind to the exact payload bytes and critical metadata.
3. **Has the message already been processed?** Use timestamps, event IDs, nonces, and idempotency to prevent replay or duplicate processing.

Checking the signature alone does not prevent replay attacks. Checking the timestamp alone is also insufficient because attackers can replay requests within the valid time window. Applications must combine cryptographic verification with persistent event state tracking.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, covering identity/permissions, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. The focus of this lesson is verifying webhook signatures, validating event tokens, preventing replays, handling retries/duplicates, and designing secure event receiver endpoints.

## 1. Learning Objectives and Running Scenario

After this lesson, you will be able to:

1. Distinguish among webhook authentication, payload integrity, freshness, and idempotency.
2. Explain what HMAC, asymmetric signatures, JWTs, and TLS each protect.
3. Verify signatures against raw request body bytes before parsing JSON.
4. Use timestamps, event IDs, and nonces to detect stale or repeated requests.
5. Design an inbox/idempotency store with unique constraints and handle concurrent requests.
6. Rotate webhook secrets without disrupting senders still using the previous key.
7. Integrate webhook verification with AWS SNS/EventBridge, Azure Event Grid, and Google Cloud Pub/Sub.
8. Handle at-least-once delivery, retries, duplicates, out-of-order events, and dead-letter queues.
9. Test spoofing, payload tampering, replay, key rotation, and duplicate side effects.
10. Emit sufficient audit logs for investigation without leaking secrets, signatures, or sensitive data.

Running scenario: **order-service** receives payment notifications from a payment provider. Upon receiving a payment-succeeded event, the service marks the order as paid and emits an invoice-creation command. A forged request or a replayed event could corrupt order state or issue duplicate invoices.

~~~mermaid
flowchart TD
    A["Webhook / event request"] --> B["Size limit + HTTPS"]
    B --> C["Verify source: HMAC / RSA / JWT"]
    C --> D["Check timestamp and key version"]
    D --> E["Check event ID / nonce"]
    E --> F["Insert into inbox with unique constraint"]
    F --> G["Idempotent business processing"]
    G --> H["Write outbox in same transaction"]
    H --> I["ACK 2xx after durable persistence"]
    C -->|Invalid| X["Reject + security audit"]
    F -->|Duplicate| Y["Skip repeated side effects; ACK per contract"]
~~~

**Request authentication and duplicate prevention are two separate layers.** Signatures prove the request came from a party holding the secret/private key; idempotency ensures the same event never triggers business actions twice.

## 2. Risks of Webhooks and Event Endpoints

### 2.1. Sender spoofing

If an endpoint relies solely on a secret URL or a client-supplied header, anyone who learns the endpoint can send forged payloads.

For example, an attacker sends:

~~~http
POST /webhooks/payment HTTP/1.1
Content-Type: application/json

{"event":"payment.succeeded","orderId":"ORD-1001","amount":990000}
~~~

If the service updates orders solely based on JSON, forged requests can trigger business actions. IP allowlists or hard-to-guess URLs do not replace cryptographic signatures/tokens.

### 2.2. Payload tampering in transit or at intermediaries

TLS protects the transport connection to the endpoint, yet payloads can be altered prior to signing, after decryption at a proxy, or by a privileged internal component. A signature/MAC bound to the payload detects whether content no longer matches what the sender signed.

If only a few fields are signed while omitting amount, currency, event ID, or critical resource IDs, attackers can modify unprotected fields. Explicitly define the canonical message and which metadata fields are signed.

### 2.3. Replay attacks

Replay happens when a valid request is captured and resent:

- A payment-succeeded webhook is replayed to generate multiple invoices.
- An email-change callback is replayed after the user already changed their password.
- A permission-grant event is resent after access was revoked.
- An older message is resent to overwrite newer state.

A valid signature stays valid if the signed payload and metadata remain unchanged. Therefore, **signature verification alone does not prevent replay**.

### 2.4. Duplicate deliveries from normal retries

Not every duplicate is an attack. Event systems usually deliver at-least-once. A sender may miss an ACK even though the receiver finished processing, prompting a retry. Network timeouts, process restarts, or failed ACKs also produce duplicates.

Applications must handle duplicates safely rather than assuming every event arrives only once.

### 2.5. Out-of-order delivery

Two related events can arrive out of chronological order:

- An order is created and then updated, yet the update event arrives first.
- Inventory receives a reserve event after a release event.
- A subscription receives an older active status after already receiving a newer cancelled status.

Never use request arrival time as business ordering. When order matters, use aggregate sequences/versions or read current state from the authoritative source.

## 3. HMAC, Digital Signatures, and JWTs

### 3.1. What is HMAC?

HMAC (Hash-based Message Authentication Code) uses a shared secret and a cryptographic hash function—typically SHA-256—to produce an authentication tag:

\[
\operatorname{HMAC}_{SHA256}(K, M)
\]

Where:

- `K` is the shared secret known only to sender and receiver.
- `M` is the signed message bytes.
- The output is the MAC, commonly encoded as hex or Base64.

The sender computes the MAC and sends it with the request. The receiver recomputes it with the same secret and compares. If the payload or signed metadata changes, the outputs will not match.

**HMAC does not encrypt the payload.** Recipients can still read the JSON. HMAC provides authentication and integrity, while TLS protects data in transit.

### 3.2. Asymmetric signatures

With RSA or ECDSA signatures:

- The sender holds the private key to sign.
- The receiver uses the corresponding public key to verify.
- The receiver never holds the private signing key.
- A single public key can be distributed to many consumers.

This fits when a provider signs events with its private key and receivers verify with the public key—for instance, Amazon SNS signing notifications with RSA. Asymmetric signatures do not encrypt messages and do not prevent replay on their own.

### 3.3. What is a JWT?

JWT is a token format containing a header, claims, and signature/MAC. For push webhooks, tokens typically authenticate the sending service:

- Issuer (`iss`): the party issuing the token.
- Subject (`sub`): the represented principal.
- Audience (`aud`): the endpoint/resource server permitted to accept the token.
- Expiration (`exp`): expiration timestamp.
- Issued-at (`iat`): issuance timestamp.
- Signature: verifies the token was not modified and was signed by the issuer.

Never treat successfully decoding a JWT as authentication. The receiver must verify the signature, issuer, audience, timestamps, and required claims per provider specification. Never accept algorithms or keys declared by the token itself outside trusted configuration.

### 3.4. Comparison

| Mechanism | Where does the secret live? | What does it verify? | How is replay prevented? |
| --- | --- | --- | --- |
| HMAC-SHA256 | Shared secret at sender and receiver | Payload/metadata signed by both parties | Timestamp + event ID/nonce store |
| RSA/ECDSA signature | Private key at sender; public key at receiver | Payload signed by the private key | Timestamp + event ID/nonce store |
| JWT bearer token | Signing key at issuer; verifier holds matching public key/secret | Identity, audience, claims, and token integrity | Token expiry, `jti`/revocation if available; event ID still needed for duplicates |
| TLS/mTLS | Certificates/private keys and session keys | Connection channel; can authenticate client | Does not prevent business-layer replay by itself |
| API key | Static shared secret/token | Key-based access if validated by server | Requires separate rotation, TTL, nonce/idempotency |

### 3.5. Never rely on one mechanism for everything

- TLS is mandatory for internet-facing webhooks.
- HMAC/RSA verifies the message or provider.
- JWT authenticates service identity and audience when supported by the provider.
- Timestamps check freshness.
- Event IDs/nonces and inboxes prevent duplicates/replays.
- Authorization checks whether the event is permitted to modify that specific resource/tenant.

A validly signed request might still lack authorization to update an order belonging to a different tenant.

## 4. Signing and Verifying Payloads Properly

### 4.1. Sign raw body bytes

JSON has many equivalent representations:

~~~json
{"amount":1000,"currency":"USD"}
~~~

~~~json
{
  "currency": "USD",
  "amount": 1000
}
~~~

Both payloads parse to the same object yet differ byte-for-byte. If the sender signs the original JSON bytes while the receiver parses and re-serializes before computing HMAC, verification can fail. If the receiver relies on a custom canonical representation, sender and receiver may disagree on whitespace, Unicode, number formatting, or escaping.

Safe rules:

1. Read the raw request body as `byte[]`.
2. Verify the signature over the exact bytes and metadata specified by the sender.
3. Parse JSON only after verification succeeds.
4. Never re-use a normalized or re-serialized request body for signature verification.
5. Never omit fields just because the application ignores them; the sender likely signed the entire payload.

Some providers define a specific canonical string instead of signing raw body bytes. Follow the provider's exact specification without altering field order or encoding.

### 4.2. Sign both timestamp and event ID

An example format for a custom HMAC webhook:

~~~text
X-Webhook-Key-Id: key-2026-02
X-Webhook-Timestamp: 1795512000
X-Webhook-Event-Id: evt_8f2a9c
X-Webhook-Signature: v1=<hex-mac>
~~~

Canonical message:

~~~text
v1
key-2026-02
1795512000
evt_8f2a9c
<raw-body-bytes>
~~~

Sender and receiver must agree on encoding, separators, newlines, and byte handling. Timestamp, key ID, and event ID are all covered by the signature; attackers cannot alter them while keeping a valid MAC.

This is an **illustrative application-defined protocol**, not a standard shared header format across AWS, Azure, Google, or Stripe. When integrating a provider, use their official headers and signing format.

### 4.3. Choosing algorithms and secret lengths

- Prefer HMAC-SHA256 or stronger for new shared-secret webhooks.
- Use high-entropy random secrets, at least 32 bytes for HMAC-SHA256 per internal policy.
- Never use human-chosen passwords as webhook secrets.
- Never use MD5 or plain SHA-1 for message authentication.
- Never concatenate a secret with SHA-256 directly; use a proper HMAC API.
- For digital signatures, use algorithms/key types matching the provider and maintained libraries.
- Never hand-roll RSA/ECDSA math or custom signature parsers.

### 4.4. Safe signature comparison

When comparing MACs, never use ordinary string comparison if it short-circuits on the first differing byte. Use a constant-time comparison function, such as Java's `MessageDigest.isEqual` on byte arrays of valid length.

Before comparing:

- Check the signature version/prefix.
- Validate hex/Base64 encoding.
- Reject signatures of invalid length.
- Never log signature values or secrets.
- Return a generic error to callers; keep details in controlled security metrics/audits.

Constant-time comparison reduces timing leakage during MAC comparison; it does not replace rate limiting, TLS, or safe error handling.

## 5. Timestamps, Nonces, and Event IDs for Replay Protection

### 5.1. Timestamp window

The receiver checks that the timestamp lies within an accepted window, such as ±5 minutes:

\[
|t_{request} - t_{server}| \leq \Delta
\]

Five minutes is just an example. Choose tolerance based on clock skew, retry policies, and provider network latency. The timestamp must be included in the signed data; otherwise attackers can swap an old timestamp for a fresh one.

Use UTC and NTP-synchronized clocks. Reject timestamps too far in the future or too old. Never trust a timestamp taken from an unverified body to decide freshness.

### 5.2. Timestamps alone do not prevent replay

An attacker capturing a valid request at 10:00 can replay it at 10:01 if the tolerance is 5 minutes. The signature remains valid and the timestamp falls inside the window.

Timestamps only narrow the window during which a stolen request can be replayed. You still need stored event IDs or nonces checked for uniqueness.

### 5.3. Event IDs and nonces

- **Event ID:** a stable identifier for a business event; the sender keeps the same ID across retries.
- **Nonce:** a unique random value for a single message/request transmission.
- **Idempotency key:** a key enabling the receiver to recognize a logical operation already accepted/processed.

For event deliveries with retries, prefer the provider's stable event ID. A fresh nonce per retry would prevent deduplicating the same event. In a custom protocol, you can embed a fixed nonce inside the original message and preserve it across retries.

### 5.4. Persisting received markers in the database

Do not store event IDs solely in memory or local caches; multiple Spring Boot instances can receive the same event concurrently. Use a unique constraint in the database:

~~~sql
CREATE TABLE webhook_inbox (
    provider VARCHAR(80) NOT NULL,
    endpoint_id VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    payload_sha256 BYTEA NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ,
    status VARCHAR(24) NOT NULL,
    PRIMARY KEY (provider, endpoint_id, event_id)
);
~~~

The unique key should be scoped by provider/endpoint/tenant according to the identity contract. Never assume every provider's event IDs are globally unique across all systems.

### 5.5. Same event ID with a different payload

If the event ID already exists:

- Same payload hash: duplicate delivery; do not re-run side effects.
- Different payload hash: possible sender bug, event ID collision, or spoofing attempt; never overwrite the existing event—route to security review/quarantine.

Never leak internal details to callers. Emit a security event recording provider, endpoint, event ID, hash, and timestamp; never log sensitive raw payloads.

### 5.6. Inbox retention

Retain event IDs long enough to cover:

- The accepted timestamp tolerance window.
- The provider's maximum retry span.
- The plausible replay window per your threat model.
- Operational window required for investigation and controlled replays.

Deleting inbox records too early allows older events to be reprocessed. You can retain lightweight tombstone/idempotency records longer than detailed payloads. There is no need to retain raw bodies indefinitely just for duplicate detection.

## 6. HMAC Verification Pattern in Java and Spring Boot

### 6.1. Verified model

~~~java
package com.example.webhook;

import java.time.Instant;

public record VerifiedWebhook(
        String keyId,
        String eventId,
        Instant timestamp,
        byte[] rawBody) {
}
~~~

In production, records should defensively copy byte arrays or use immutable value objects. Never allow callers to mutate `rawBody` after verification.

### 6.2. HMAC utility

~~~java
package com.example.webhook;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.nio.charset.StandardCharsets;

public final class WebhookMac {
    private WebhookMac() {
    }

    public static byte[] hmacSha256(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    public static byte[] canonicalMessage(
            String version,
            String keyId,
            String timestamp,
            String eventId,
            byte[] rawBody) throws IOException {

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write((version + "\n" + keyId + "\n" + timestamp
                + "\n" + eventId + "\n").getBytes(StandardCharsets.UTF_8));
        output.write(rawBody);
        return output.toByteArray();
    }
}
~~~

This is an illustrative protocol. Senders must produce the exact same canonical bytes. For large bodies, avoid unnecessary copies; enforce request size limits before loading everything into memory or use streaming MACs if the protocol supports them.

### 6.3. Verifier with timestamp and constant-time compare

~~~java
package com.example.webhook;

import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;

import org.springframework.stereotype.Component;

@Component
public class WebhookVerifier {
    private final Map<String, byte[]> activeSecrets;
    private final Clock clock;
    private final Duration tolerance;

    public WebhookVerifier(
            WebhookSecretProvider secretProvider,
            Clock clock) {
        this.activeSecrets = secretProvider.currentAndPreviousSecrets();
        this.clock = clock;
        this.tolerance = Duration.ofMinutes(5);
    }

    public VerifiedWebhook verify(
            String keyId,
            String timestampHeader,
            String eventId,
            String signatureHeader,
            byte[] rawBody) {

        if (rawBody == null || rawBody.length == 0
                || rawBody.length > 1_048_576) {
            throw new InvalidWebhookException();
        }

        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,200}")) {
            throw new InvalidWebhookException();
        }

        Instant timestamp;
        try {
            timestamp = Instant.ofEpochSecond(
                    Long.parseLong(timestampHeader));
        } catch (RuntimeException ex) {
            throw new InvalidWebhookException();
        }

        if (Duration.between(timestamp, clock.instant()).abs()
                .compareTo(tolerance) > 0) {
            throw new StaleWebhookException();
        }

        if (signatureHeader == null
                || !signatureHeader.startsWith("v1=")) {
            throw new InvalidWebhookException();
        }

        byte[] supplied;
        try {
            supplied = HexFormat.of().parseHex(
                    signatureHeader.substring(3));
        } catch (IllegalArgumentException ex) {
            throw new InvalidWebhookException();
        }

        if (supplied.length != 32) {
            throw new InvalidWebhookException();
        }

        byte[] secret = activeSecrets.get(keyId);
        if (secret == null) {
            throw new InvalidWebhookException();
        }

        byte[] message;
        byte[] expected;
        try {
            message = WebhookMac.canonicalMessage(
                    "v1", keyId, timestampHeader, eventId, rawBody);
            expected = WebhookMac.hmacSha256(secret, message);
        } catch (GeneralSecurityException | IOException ex) {
            throw new WebhookVerificationUnavailableException();
        }

        if (!MessageDigest.isEqual(expected, supplied)) {
            throw new InvalidWebhookException();
        }

        return new VerifiedWebhook(keyId, eventId, timestamp, rawBody);
    }
}
~~~

The example requires the remaining imports such as `GeneralSecurityException`, `IOException`, `Map`, and `ByteArrayOutputStream`. In real applications, the secret provider reads keys from a secret manager/KMS-backed configuration and returns key material by key ID. Never hardcode secret maps in source code or commit secrets to Git.

The verifier checks the timestamp before HMAC to reject stale requests early. If you need to avoid observable differences between timestamp and signature failures, normalize response codes/bodies and apply rate limiting. Never tell callers which key IDs are active.

### 6.4. Receiving raw body in the controller

~~~java
@RestController
@RequestMapping("/webhooks/payment")
public class PaymentWebhookController {
    private final WebhookVerifier verifier;
    private final ObjectMapper objectMapper;
    private final PaymentEventService eventService;

    public PaymentWebhookController(
            WebhookVerifier verifier,
            ObjectMapper objectMapper,
            PaymentEventService eventService) {
        this.verifier = verifier;
        this.objectMapper = objectMapper;
        this.eventService = eventService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> receive(
            @RequestHeader("X-Webhook-Key-Id") String keyId,
            @RequestHeader("X-Webhook-Timestamp") String timestamp,
            @RequestHeader("X-Webhook-Event-Id") String eventId,
            @RequestHeader("X-Webhook-Signature") String signature,
            @RequestBody byte[] rawBody) throws IOException {

        VerifiedWebhook verified = verifier.verify(
                keyId, timestamp, eventId, signature, rawBody);

        PaymentEvent event = objectMapper.readValue(
                verified.rawBody(), PaymentEvent.class);

        eventService.accept(verified, event);
        return ResponseEntity.accepted().build();
    }
}
~~~

The controller parses JSON only after verification succeeds. Configure body size limits at the reverse proxy/container; controller annotations or checks do not replace network-layer limits. If using a filter that reads the body, ensure the body remains readable or use a proper caching wrapper.

### 6.5. Notes on secret providers

- Retrieve secrets from AWS Secrets Manager/Parameter Store, Azure Key Vault, or Google Secret Manager using the workload's identity.
- Use non-secret key IDs to select secret versions.
- Never share the same secret across multiple tenants or webhook providers when they can be separated.
- Keep current and previous secrets during an overlap window for key rotation.
- Restrict secret read access strictly to services performing verification.
- Never log secrets, MACs, full authorization headers, or raw bodies.
- Cache secrets in memory with a TTL and refresh policy; avoid calling the secret manager on every request if latency/availability does not permit it.
- When a key is compromised, revoke/rotate it and monitor requests using the old key.

## 7. Duplicate Prevention and Idempotent Business Processing

### 7.1. Inbox pattern

A common implementation:

1. Verify signature and timestamp.
2. Parse the event.
3. Compute the payload hash.
4. Insert the event ID into the inbox with a unique constraint.
5. If a duplicate with the same payload, skip running business logic again.
6. If a new event, update domain state.
7. Write an outbox event if downstream messages must be published.
8. Commit the transaction.
9. ACK the sender after durable persistence.

Pseudo-code example:

~~~java
@Transactional
public AcceptResult accept(
        VerifiedWebhook verified,
        PaymentEvent event) {

    byte[] payloadHash = sha256(verified.rawBody());

    boolean inserted = inboxRepository.insertIfAbsent(
            "payment-provider",
            "payment-endpoint",
            verified.eventId(),
            payloadHash);

    if (!inserted) {
        InboxRecord existing = inboxRepository.findRequired(
                "payment-provider",
                "payment-endpoint",
                verified.eventId());

        if (!MessageDigest.isEqual(
                existing.payloadHash(), payloadHash)) {
            throw new EventIdCollisionException();
        }

        return AcceptResult.DUPLICATE;
    }

    orderService.markPaidIdempotently(
            event.orderId(), event.paymentId(), event.amount());

    outboxRepository.save(
            OutboxEvent.invoiceRequested(event.orderId(), event.paymentId()));

    inboxRepository.markProcessed(
            "payment-provider", "payment-endpoint", verified.eventId());

    return AcceptResult.ACCEPTED;
}
~~~

`insertIfAbsent` must be executed via an `INSERT` with a unique constraint handling conflicts at the database level. Checking existence with `SELECT` followed by `INSERT` is unsafe when two instances receive the same event concurrently.

### 7.2. Transactions and external side effects

If you update a database and publish a message to a broker in the same method without a distributed transaction, failures can cause:

- DB commits while publish fails.
- Publish succeeds while DB rolls back.
- Retries produce duplicate side effects.

Use the **Transactional Outbox**: write business state and the outbox record in the same database transaction; a separate worker publishes outbox rows and marks them sent. Downstream consumers must remain idempotent because publishing can still repeat.

When calling payment providers, email APIs, or external services, pass an idempotency key to the target API when supported. Never assume a database transaction wraps HTTP calls.

### 7.3. When should you ACK?

Only return 2xx after:

- The signature/token is verified.
- The event is durably persisted in the inbox or transactionally processed.
- The system can resume processing after a restart.

Returning 2xx before persistence risks losing events if the process crashes while the sender assumes success. For heavy processing, persist the inbox record and return 202/204 per contract; let a background worker process asynchronously.

If the database is temporarily unavailable, return a retriable status per contract so the sender retries. Never ACK and drop an event.

### 7.4. Idempotency at the domain layer

The inbox blocks repeated event IDs, yet the same business action may arrive under different event IDs. Domain operations should also be idempotent:

- Unique constraints on payment IDs/transaction references.
- Valid state-machine transitions.
- Never create an invoice if one already exists for the payment.
- Never credit balances twice; record ledger transactions with unique business keys.
- Never rely on event IDs alone to protect financial invariants.

### 7.5. Retain idempotency records long enough

Inbox retention must span the sender's retry window and audit requirements. If a provider can retry for hours or days, do not purge records after minutes. Partition by day or archive older payloads while keeping event ID/hash tombstones.

## 8. Handling Retries and Event Ordering

### 8.1. HTTP status codes and retries

Each provider has its own rules. Typically:

- 2xx: acknowledges receipt.
- 4xx: may be treated as a configuration error or non-retriable depending on the provider.
- 5xx/timeouts: typically retried with backoff.
- Responses must be fast; offload heavy work to background workers after persistence.

Do not assume 401/403 is always retried. Some services treat those as misconfigurations and halt delivery or dead-letter events.

### 8.2. Out-of-order events

Use resource versions/sequences:

~~~text
orderId=ORD-1001, version=12, status=PAID
orderId=ORD-1001, version=13, status=REFUNDED
~~~

If version 13 arrives before version 12, the service can store state at version 13 and ignore the stale version 12 event. If gaps occur, fetch current state from the source API or buffer events waiting for missing versions depending on business rules.

Event timestamps do not always define strict order: sender clocks can drift, events may come from multiple services, or replays can occur. Prefer monotonic versions/sequences issued by the domain owner.

### 8.3. Dead-letter queues

DLQs hold events that fail after retry limits or TTL expiration. Require:

- Classification of transient vs. permanent errors.
- Alerting when DLQ depth grows.
- Preserving original event IDs and metadata for investigation.
- Controlled replay procedures.
- Replays still passing signature/authentication checks or an audited internal replay path.
- Never bypassing idempotency during replay.
- Never putting secrets or restricted payloads into tickets/logs.

## 9. AWS: SNS Signatures and EventBridge Delivery

### 9.1. Amazon SNS HTTP/S notifications

Amazon SNS signs notifications and includes the signature alongside `SigningCertURL`:

- `SignatureVersion` 1 uses SHA-1 with RSA.
- `SignatureVersion` 2 uses SHA-256 with RSA and is recommended.
- The signature covers message fields depending on notification type, including `Message`, `MessageId`, `Subject` if present, `Type`, `Timestamp`, and `TopicArn`.
- Receivers must validate the certificate chain and signature before processing.
- Accept only expected `TopicArn` values; never accept arbitrary topics merely because their signature is valid.

Use AWS SDK SNS verification helpers rather than building canonical strings manually. If handling `SigningCertURL` directly, fetch certificates only over HTTPS from allowed regional AWS SNS domains; verify the chain/issuer and never fetch arbitrary URLs from payloads to prevent SSRF.

Subscription confirmation/unsubscribe notifications must also be verified by message type. Never automatically visit `UnsubscribeURL` merely because it appears in a payload.

### 9.2. EventBridge

EventBridge delivers events to targets per retry policies and can deliver at-least-once. When the target is an API destination, configure a Connection to manage API key, Basic, or OAuth authorization per service capabilities. HTTPS and authentication at the endpoint must still be configured.

- EventBridge does not turn every HTTP target into an HMAC webhook.
- API destination authentication is the layer authenticating requests to your endpoint.
- Event IDs and idempotency are still required to handle duplicates.
- Configure retry policies and DLQs on targets.
- Never assume events always arrive in order.

Service event delivery into EventBridge can be best-effort or durable depending on the source service; durable implies attempting at-least-once delivery. Distinguish delivery into EventBridge from delivery from EventBridge to targets.

### 9.3. Handling in Spring Boot

For SNS, the endpoint verifies signatures using the appropriate AWS SNS/SDK library and checks `TopicArn` and message type before parsing business messages. For EventBridge API destinations, verify the API key/OAuth token per the configured Connection, then validate the event envelope, `source`, `detail-type`, and event ID.

Never apply a custom HMAC verifier to SNS when the provider uses its own RSA signature format.

## 10. Azure Event Grid

### 10.1. Endpoint validation handshake

When registering a webhook endpoint, Event Grid requires proving endpoint ownership. With the Event Grid event schema, the endpoint receives a validation event and must return a validation response matching the contract. This is an ownership handshake; it is not a per-event payload signature.

Handle validation events separately and never pass them into order business logic. Validation URLs expire; complete the handshake within the provider's window.

### 10.2. Delivery authentication with Microsoft Entra ID

Event Grid can secure webhook deliveries using Microsoft Entra ID:

- Configure the target application/identity and audience/resource.
- Assign the appropriate role to the service principal used by Event Grid.
- The endpoint validates the bearer token, issuer, audience, expiry, and permissions.
- Never merely check that a token is present in the `Authorization` header.

This authenticates the sending service. If the application requires additional payload integrity verification under a separate contract, use a separate signature/MAC; never confuse the endpoint validation handshake with a payload signature.

### 10.3. Delivery, duplicates, and ordering

Event Grid delivers events at-least-once and does not guarantee ordering. Endpoints may receive duplicates even after returning success in certain scenarios. Use the Event Grid event ID as an idempotency key, scoped by subscription/provider.

Configure retries, TTLs, and dead-letter destinations. Per current documentation, certain webhook errors such as 400, 401, 403, or 413 may not be retried; choose appropriate status codes to avoid dropping events due to misconfiguration. Never return 2xx before persisting the event.

## 11. Google Cloud Pub/Sub Push Subscriptions

### 11.1. JWT authentication

When a push subscription enables authentication, Pub/Sub signs an OIDC JWT and sends it in the `Authorization` header. The receiver must verify:

- The JWT signature using the issuer's trusted public keys.
- The issuer per Pub/Sub/OIDC configuration.
- The audience matching the exact configured audience for the push endpoint.
- `exp` and time-based claims.
- The email/service account claim matching the configured service account, with `email_verified` true when required by contract.

Never simply decode the token or check the email claim while skipping signature verification. Never use an overly broad default audience if the endpoint has a specific audience.

### 11.2. Message ID and duplicates

Pub/Sub push envelopes include a message ID and subscription metadata. Use the message ID combined with subscription/provider scope as the idempotency key. Pub/Sub may redeliver if the endpoint returns a negative acknowledgment or the acknowledgment deadline expires.

Pub/Sub's exactly-once delivery supports pull subscriptions only, not push subscriptions. Even with pull exactly-once, a publisher can still emit two messages with different IDs for the same business intent; domain idempotency remains necessary.

### 11.3. ACK and processing

For push, return a successful HTTP status per the Pub/Sub contract to ACK. Returning an error status or failing to respond can trigger redelivery. Persist the event before ACKing; process long-running work asynchronously via an inbox/worker.

Never confuse the JWT authenticating the push request with a signature on each individual message payload. The JWT verifies Pub/Sub's service identity; event ID/idempotency controls duplicate processing.

## 12. Comparing the Three Cloud Providers

| Criterion | AWS SNS / EventBridge | Azure Event Grid | Google Cloud Pub/Sub push |
| --- | --- | --- | --- |
| Typical auth mechanism | SNS RSA signature; EventBridge API destination Connection | Endpoint validation handshake; Microsoft Entra ID delivery auth | OIDC JWT in `Authorization` header |
| Payload verification | SNS signature over message-type fields; EventBridge envelope + endpoint auth | Entra authenticates service; handshake is not a payload signature | JWT authenticates publisher service; body is a Pub/Sub envelope |
| Duplicate prevention | `MessageId`/event ID + inbox | Event ID + inbox | Message ID + subscription + inbox |
| Delivery semantics | Durable service events have at-least-once; targets have retries | At-least-once | Push redelivery on NACK/ack deadline |
| Ordering | Do not assume ordering | Ordering not guaranteed | Ordering not guaranteed by default |
| Exactly-once | Not default on HTTP targets | No | Supported on pull subscriptions only; not push |
| Recovery | Retry policy + DLQ | Retry policy + dead-letter | Retry/redelivery + dead-letter topic |
| App responsibilities | Verify provider auth, validate source, idempotency | Validate endpoint setup, token, event ID, idempotency | Verify JWT claims, event ID, idempotency |

Provider capabilities vary by API, region, and configuration. Check documentation for the exact service and endpoint type in use; never generalize a feature from SNS to EventBridge or from Pub/Sub pull to push.

## 13. Secret Rotation and Verification Key Management

### 13.1. Rotation must not break retries

When changing a webhook secret:

1. Generate a new secret and a new key ID.
2. Configure the receiver to accept both the new and old keys during an overlap window.
3. Update the sender to sign with the new key.
4. Monitor requests by key ID.
5. Wait until the retry window and transition period complete.
6. Revoke the old key.
7. Verify requests signed with the old key are rejected once the overlap ends.

If the provider supports two concurrent signing secrets, use the provider's rotation mechanism. Never store raw secrets in the database alongside event payloads.

### 13.2. Key ID is not a secret

The key ID helps the receiver select the right secret/public key. It can appear in headers or metadata. Never treat a key ID as proof of authentication; the signature must validate against the corresponding key.

### 13.3. Managing public keys and certificates

For RSA/ECDSA signatures:

- Pin the issuer/host and trust chain per provider.
- Cache certificates/public keys per provider guidance, with TTLs and refresh logic.
- Support key rotation via key IDs or certificate metadata.
- Never fetch arbitrary certificate URLs from incoming requests.
- Validate permitted algorithms and key types.
- When a key is revoked, handle older requests according to policy and audit them.

### 13.4. Protecting secrets and observability

Never log:

- HMAC secrets or private keys.
- `Authorization` headers, full JWTs, or refresh tokens.
- Full signatures.
- Raw webhook bodies if they contain PII/secrets.
- Unfiltered certificate URLs if they might contain untrusted data.

You may log event ID, provider, key ID, timestamp, verification outcome, body hash, latency, and correlation ID. Restrict audit log read access and retention based on classification.

## 14. Common Implementation Mistakes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Parsing JSON then re-serializing to compute HMAC | Byte representation changes | Verify raw body bytes per spec |
| Checking only sender IP | IPs can change, use shared egress, or be spoofed in headers | Signatures/JWTs + network restrictions as defense-in-depth |
| Checking only timestamp | Replay still succeeds inside the tolerance window | Persistent event ID/nonce store with unique constraint |
| Keeping event IDs only in memory | Multiple instances/restarts lose state | Durable inbox table in database |
| Using `SELECT` then `INSERT` | Race condition on concurrent duplicates | Unique constraint with insert-if-absent |
| Using `String.equals` for MACs | Can introduce timing leakage | Constant-time byte comparison |
| Not signing timestamp/event ID | Metadata can be tampered with | Sign canonical metadata alongside body |
| ACKing before persistence | Events can be lost if the process crashes | Persist inbox first, then ACK |
| Side effects outside transaction | Retries can trigger duplicate actions | Outbox pattern and idempotency at domain/target APIs |
| Purging inbox too early | Old replays get reprocessed | Retain records across retry and replay windows |
| Assuming ordered delivery | Stale state overwrites newer state | Aggregate versions/sequences |
| Trusting a JWT just because it decodes | Skips signature/issuer/audience checks | Use a standard JWT verifier and validate claims |
| Fetching arbitrary certificate URLs | SSRF and trusting attacker certificates | Allowlist hosts, HTTPS, chain/issuer validation |
| Logging raw bodies/signatures | Exposes sensitive data and credentials | Redact, hash, and emit structured audits |

## 15. Testing Webhooks and Event Endpoints

### 15.1. Signature tests

- Valid payloads with valid signatures are accepted.
- Modifying a single body byte causes verification to fail.
- Modifying timestamp/event ID/key ID causes signature verification to fail.
- Wrong signature version or encoding is rejected.
- Truncated or oversized signatures are rejected.
- Bodies with Unicode, whitespace, newlines, and escaped characters verify against exact raw bytes.
- Unknown key IDs are rejected.
- Old keys are accepted only during the rotation overlap window.

### 15.2. Freshness and replay tests

- Overly old timestamps are rejected.
- Future timestamps beyond tolerance are rejected.
- A valid request arriving the first time is processed.
- Resending the same event ID with the same payload causes no duplicate side effects.
- Same event ID with a different payload triggers security handling.
- Two concurrent requests with the same event ID result in only one claiming the inbox record.
- Reused nonces are rejected per protocol.
- Inbox records persist throughout the full retry window.

### 15.3. Business logic tests

- Payment events never create two invoices.
- Stale event versions never overwrite newer state.
- DB transaction rollbacks never leave events falsely marked processed.
- Outbox worker retries never emit non-idempotent side effects.
- DLQ replays still pass controls and auditing.
- Tenants/resources referenced in events are authorized before mutating data.

### 15.4. Provider integration tests

- SNS signature version 2, certificate chain, and matching `TopicArn`.
- SNS certificate URLs outside AWS domains are rejected.
- Event Grid validation events return the right response without triggering business logic.
- Event Grid Entra JWTs with wrong audience/issuer/expiry are rejected.
- Pub/Sub push JWTs with wrong audience or service account are rejected.
- Pub/Sub push duplicates with the same message ID are not reprocessed.
- EventBridge retries/DLQs are exercised in a test environment.
- HTTP ACK/NACK codes follow provider contracts.

### 15.5. Operational security tests

- Oversized request bodies are rejected before consuming excessive memory.
- Rate limiting engages on repeated invalid signatures.
- Logs contain no raw secrets, JWTs, signatures, or PII.
- Error responses do not leak key ID or secret validity details.
- Certificate fetching cannot be abused for SSRF.
- Endpoints accept HTTPS only with appropriate network policies.
- Replays after service restarts remain blocked by the inbox database.

## 16. Comprehensive Hands-On Exercise

`order-service` receives payment webhooks from a provider. On payment success, the service updates the order, writes a payment ledger entry, and emits an invoice-creation event. The provider delivers webhooks at-least-once and may retry for hours.

**Tasks:**

1. Design an HMAC-SHA256 protocol covering key ID, timestamp, event ID, and raw body.
2. Write a sender test helper producing signatures over exact canonical bytes.
3. Write a Spring Boot verifier using `MessageDigest.isEqual` and timestamp tolerance.
4. Store webhook secrets in a secret manager and support current/previous key rotation.
5. Create a webhook inbox with a unique key scoped by provider, endpoint, and event ID.
6. Handle same-payload duplicates as safe ACKs; treat same-ID different-payload as security incidents.
7. Update orders and payment ledgers idempotently inside a transaction.
8. Use a transactional outbox to emit invoice requests.
9. Handle out-of-order events using aggregate versions or sequences.
10. Simulate tampered requests, stale requests, replays, race conditions, process restarts, and DLQ replays.
11. Compare authentication mechanisms across SNS, Event Grid, and Pub/Sub push.
12. Draft a runbook for compromised signing secrets or provider signing keys.

**Self-assessment questions:**

- What does HMAC verify and what does it not provide?
- Why must the raw request body be verified before parsing JSON?
- Why is a timestamp insufficient to stop replays?
- How do event ID, nonce, and idempotency key differ?
- Why does an inbox need a database unique constraint?
- Why can returning 2xx before persisting an event cause data loss?
- What problem does the transactional outbox solve?
- Why is a duplicate delivery not necessarily an attack?
- Which algorithm does AWS SNS `SignatureVersion` 2 use?
- Is the Event Grid endpoint validation handshake a payload signature?
- Which claims must be checked on a Pub/Sub push JWT?
- Does Pub/Sub exactly-once delivery apply to push subscriptions?
- Why should you never assume events arrive in order?
- When rotating secrets, why is an overlap window needed?

**Guided answers:** HMAC verifies authenticity/integrity without encrypting; raw bytes must stay untouched to match the sender's signature; timestamps only bound freshness while an event ID/nonce store blocks replays of previously seen events; event ID identifies an event, nonce identifies a transmission, and idempotency key identifies a logical operation; unique constraints resolve multi-instance races; ACKing before persistence risks losing events; outbox aligns DB commits with publishing intent; duplicates commonly stem from at-least-once retries; SNS v2 uses `SHA256withRSA`; Event Grid's handshake proves endpoint ownership; Pub/Sub push requires verifying JWT signature, issuer, audience, expiry, and service account; exactly-once supports pull only; versions/sequences resolve out-of-order arrivals; overlap lets senders transition keys without breaking legitimate retries.

## 17. Official References

- [Amazon SNS – Verifying message signatures](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html): SignatureVersion 1/2, certificate validation, `TopicArn`, and best practices.
- [Amazon SNS – Verifying message signature details](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-verify-message-signature.html): canonical fields, `SigningCertURL`, and trusted AWS domains.
- [Amazon SNS – HTTP/S notification JSON format](https://docs.aws.amazon.com/sns/latest/dg/http-notification-json.html): `SignatureVersion`, `Signature`, `SigningCertURL`, and `MessageId`.
- [Amazon EventBridge – Event delivery levels](https://docs.aws.amazon.com/eventbridge/latest/ref/event-delivery-level.html): best-effort and durable at-least-once delivery.
- [Amazon EventBridge – Retry policy](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html): retry attempts, exponential backoff, and dead-letter queues.
- [Microsoft Learn – Event Grid endpoint validation](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-event-grid-events-schema): validation handshake for webhook endpoints.
- [Microsoft Learn – Secure Event Grid webhook delivery with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/event-grid/secure-webhook-delivery): service-to-service authentication with Entra ID.
- [Microsoft Learn – Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry): at-least-once, ordering, retries, and dead-lettering.
- [Google Cloud – Authenticate Pub/Sub push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions): OIDC JWTs, `Authorization` header, audience, and service account claims.
- [Google Cloud – Pub/Sub push subscriptions](https://docs.cloud.google.com/pubsub/docs/push): ACK/NACK, push delivery, and redelivery.
- [Google Cloud – Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery): scope of exactly-once to pull subscriptions and duplicate semantics.
- [RFC 2104 – HMAC](https://www.rfc-editor.org/rfc/rfc2104): definition of HMAC and combining hash functions with shared secrets.
- [RFC 7519 – JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and claims.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): endpoint protection principles, authentication, validation, and transport security.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to omit from logs, sanitization, read access, and audit log retention.

**Remember:** the signature answers "who created the request and was the payload altered"; the timestamp answers "is the request still fresh"; the event ID/inbox answers "has this event already been received"; and domain idempotency answers "has the business operation already been executed." For a secure webhook endpoint, Spring Boot must combine all four layers and adhere to each provider's retry and authentication contract.
