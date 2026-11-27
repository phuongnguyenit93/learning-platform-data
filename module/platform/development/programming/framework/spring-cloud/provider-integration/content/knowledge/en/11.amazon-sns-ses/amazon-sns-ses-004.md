# Signature Verification, Subscription Confirmation, and HTTP Notification Handling

## 1. Why Must an HTTP Endpoint Verify SNS Messages?

In an architecture integrating Spring Boot with cloud managed services, a publisher sends a notification to **Amazon Simple Notification Service (SNS)**, and SNS then dispatches an HTTP POST to a registered **HTTPS endpoint**. The endpoint can be a Java service inside AWS or an external system outside AWS. This is how applications are connected when consumers do not pull directly from Amazon SQS.

Crucial point: any Internet client that knows the webhook URL can attempt to send an HTTP POST to it. **A header named x-amz-sns-message-type, JSON containing a TopicArn field, or an SNS-like User-Agent is not proof of authenticity.** An endpoint should process a notification only after **verifying the digital signature**, checking the **allowed topic ARN**, and confirming that the message came from SNS.

This lesson belongs to the **Amazon SNS and SES** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on hands-on integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via Spring Cloud libraries, while covering identity, permissions, messaging, secret management, integration testing, and provider comparisons. The focus of this lesson is **receiving SNS notifications over HTTP/S, verifying signatures, confirming subscriptions, and handling messages safely**. SES is a separate transactional email service; an application may receive an SNS event and then call SES in a subsequent business step.

**Learning objectives:**

- Describe the HTTP/S subscription lifecycle: creating, receiving **SubscriptionConfirmation**, confirming, receiving **Notification**, and reacting to **UnsubscribeConfirmation**.
- Properly parse the SNS JSON envelope and HTTP headers, including the optional **Subject** field.
- Understand SNS **SignatureVersion 1/2** verification, canonical strings, SigningCertURL, and rules preventing spoofing/SSRF.
- Build a Spring Boot REST endpoint accepting the default **text/plain** content type, handling each message type, and returning appropriate HTTP status codes.
- Distinguish webhook acknowledgment of message receipt from business processing, implementing an **idempotent inbox** and retries on failure.
- Test invalid signatures, disallowed topics, invalid confirmations, retries, duplicates, and terminal failures.

## 2. HTTPS Subscription Lifecycle

~~~mermaid
sequenceDiagram
    participant A as Operator / IaC
    participant S as Amazon SNS
    participant W as Spring Boot HTTPS webhook
    participant D as Durable inbox
    participant C as Consumer

    A->>S: Subscribe(topic, https endpoint)
    S->>W: POST SubscriptionConfirmation
    W->>W: Validate body, topic, signer URL and signature
    W->>S: ConfirmSubscription(topicArn, token)
    S-->>W: SubscriptionArn
    W-->>S: HTTP 2xx
    A->>S: Publish event
    S->>W: POST Notification
    W->>W: Verify SNS signature and allowed topic
    W->>D: Persist message once
    D-->>W: Commit successful
    W-->>S: HTTP 204
    C->>D: Read and process event
~~~

**Three SNS HTTP/S message types:**

| Type Value | When Does It Appear? | Appropriate Action |
| --- | --- | --- |
| **SubscriptionConfirmation** | When a new HTTP/S endpoint is subscribed | Validate signature, allowed topic, and token, then call **ConfirmSubscription** or follow the approved confirmation workflow |
| **Notification** | After the subscription is confirmed, when a message is published and matched for delivery | Verify signature, then write the event to a durable inbox/queue; return 2xx upon durable acceptance |
| **UnsubscribeConfirmation** | When the subscription is unsubscribed | Verify; record and alert operations; only restore the subscription via an approved process |

The endpoint **does not receive Notifications** until the subscription is confirmed. A pending subscribe request may remain in **PendingConfirmation** status. If auto-confirming, the application must strictly bind to an approved **TopicArn**; if implementing manual confirmation, store the token in a protected store and confirm before it expires.

### 2.1. What Does the HTTP Request Look Like?

By default, SNS sends POST requests to HTTP/S endpoints with **Content-Type: text/plain; charset=UTF-8** even though the body is a JSON document. Consequently, a controller that only declares **application/json** may return **415 Unsupported Media Type** before even reading the message.

Abbreviated example:

~~~http
POST /webhooks/sns HTTP/1.1
Content-Type: text/plain; charset=UTF-8
x-amz-sns-message-type: Notification
x-amz-sns-message-id: 55ee4dbe-1111-4444-9999-123456789abc
x-amz-sns-topic-arn: arn:aws:sns:ap-southeast-1:123456789012:order-events

{
  "Type": "Notification",
  "MessageId": "55ee4dbe-1111-4444-9999-123456789abc",
  "TopicArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events",
  "Message": "{\"eventId\":\"evt-1001\",\"eventType\":\"ORDER_CREATED\"}",
  "Timestamp": "2026-11-24T08:00:00.000Z",
  "SignatureVersion": "2",
  "Signature": "<base64-rsa-signature>",
  "SigningCertURL": "https://sns.ap-southeast-1.amazonaws.com/SimpleNotificationService-example.pem"
}
~~~

The snippet above is a **structural illustration** and does not contain a valid signature for direct positive testing. Alongside the JSON body, SNS sends headers such as **x-amz-sns-message-type**, **x-amz-sns-message-id**, **x-amz-sns-topic-arn**, and potentially **x-amz-sns-subscription-arn**. Headers are useful for routing/observability, but **do not replace signature verification** of the body.

For a **Notification**, key fields typically include **Type**, **MessageId**, **TopicArn**, **Message**, **Timestamp**, **SignatureVersion**, **Signature**, **SigningCertURL**, along with **Subject**, **MessageAttributes**, and **UnsubscribeURL** when present. The **Message** field may be an escaped JSON string: parse the *envelope* first, then parse the **Message** string into the business event.

For **SubscriptionConfirmation** and **UnsubscribeConfirmation**, fields used for confirmation/resubscription include **Token** and **SubscribeURL**. Never access SubscribeURL before verifying the entire message.

## 3. Amazon SNS Signature Mechanism

SNS signs a fixed set of fields in the message. The endpoint retrieves the public key from the certificate published at **SigningCertURL** under a trusted AWS SNS domain, reconstructs the canonical string in exact order, Base64-decodes **Signature**, and verifies the RSA signature.

### 3.1. SignatureVersion 1 and 2

| Version | Java/JCA Algorithm | Notes |
| --- | --- | --- |
| **1** | **SHA1withRSA** | Compatible with legacy SNS configuration; AWS default for topics unless changed |
| **2** | **SHA256withRSA** | Recommended by AWS for new systems |

Configure a topic to use the stronger signature version:

~~~bash
aws sns set-topic-attributes \
  --topic-arn "$TOPIC_ARN" \
  --attribute-name SignatureVersion \
  --attribute-value 2 \
  --region ap-southeast-1
~~~

When an application accepts only version 2, ensure the topic is actually configured to 2 and the transition does not disrupt endpoints. The examples below handle both versions to explain the protocol; for fully controlled topics, **SignatureVersion=2** can be enforced in application policy.

### 3.2. Building the Exact Canonical String

SNS uses **field name + LF newline + value + LF** in a **fixed order**. You must preserve the JSON-decoded content verbatim, including literal newlines inside **Message/Subject**. Do not re-sign the entire JSON, do not sort by request key order, and do not insert arbitrary whitespace.

| Type | Field Order in Canonical String |
| --- | --- |
| **Notification** | Message, MessageId, **Subject if present**, Timestamp, TopicArn, Type |
| **SubscriptionConfirmation** | Message, MessageId, SubscribeURL, Timestamp, Token, TopicArn, Type |
| **UnsubscribeConfirmation** | Message, MessageId, SubscribeURL, Timestamp, Token, TopicArn, Type |

Example canonical string structure for a Notification **without Subject**:

~~~text
Message
{"eventId":"evt-1001","eventType":"ORDER_CREATED"}
MessageId
55ee4dbe-1111-4444-9999-123456789abc
Timestamp
2026-11-24T08:00:00.000Z
TopicArn
arn:aws:sns:ap-southeast-1:123456789012:order-events
Type
Notification
~~~

After the final **Notification** line there is **one trailing LF character**. In Java code, use UTF-8 and explicitly append **\n** after each name and value.

### 3.3. Restricting SigningCertURL to Prevent SSRF

**SigningCertURL comes from untrusted input**. Directly fetching any URL in the body could let an attacker force the server to request internal addresses, cloud metadata endpoints, or attacker-controlled certificates. Before downloading the certificate, you must:

1. Allow only **https** and the **SNS hostname for the approved region/partition** (here **sns.ap-southeast-1.amazonaws.com**).
2. Perform an **exact hostname comparison**, not a **contains("amazonaws.com")** rule or string suffix check that can be bypassed.
3. Reject userinfo, arbitrary ports, queries/fragments, and paths that do not match the expected SNS certificate pattern.
4. Disable automatic redirect following; enable TLS hostname verification and default CA trust when fetching from the AWS endpoint.
5. Validate certificate validity window, trust chain/issuer per security policy, and verify the RSA signature; do not treat **checkValidity()** alone as a trust chain check.
6. Bound download size, connection, and response timeouts; cache verified certificates with an appropriate TTL under high traffic.

**Important:** A signature can be valid for a different topic you do not trust. You must match **TopicArn against the exact allowed ARN**, while restricting region and AWS account per configuration. Signatures verify message origin and integrity; **idempotency** and replay policies are still required at the business layer.

## 4. Creating a Topic and Subscribing an HTTPS Endpoint

Suppose Spring Boot exposes **https://api.example.com/webhooks/sns** with a valid HTTPS certificate. The endpoint must be running before calling Subscribe so it can receive the confirmation message.

~~~bash
aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol https \
  --notification-endpoint "https://api.example.com/webhooks/sns" \
  --region ap-southeast-1
~~~

The Subscribe command creates a subscription awaiting confirmation. When SNS POSTs **SubscriptionConfirmation**, the application has two options:

- **Controlled and automatic:** After verifying signature and TopicArn, call **ConfirmSubscription** with **Token**; record the SubscriptionArn.
- **With an approval step:** Save request details to an internal store, notify an authorized approver, and call ConfirmSubscription only after approval. Do not log tokens/SubscribeURLs to public logs.

AWS also allows visiting the signed **SubscribeURL** to confirm. For Java applications with AWS permissions and control over the topic, calling the **ConfirmSubscription API** with the token is usually easier to manage and avoids issuing HTTP GET requests to a URL supplied in the request.

After confirmation, inspect the subscription status:

~~~bash
aws sns list-subscriptions-by-topic \
  --topic-arn "$TOPIC_ARN" \
  --region ap-southeast-1
~~~

The subscription must show a real **SubscriptionArn**, no longer PendingConfirmation. In commercial AWS environments, configure HTTPS endpoints, DNS, and a valid certificate signed by a CA trusted by SNS.

### 4.1. Do Not Enable Raw Delivery for Envelope-Verifying Webhooks

With **RawMessageDelivery=false** (default), the HTTP/S body contains the SNS envelope with Signature, SigningCertURL, and fields needed for verification. If **RawMessageDelivery=true** is enabled, SNS sends the raw message body and strips the SNS envelope: handlers using this lesson's envelope verification algorithm will **no longer have the fields required to verify the SNS signature**. Therefore, this example keeps **RawMessageDelivery=false**.

This differs from SNS → SQS where raw delivery is often enabled so workers can read domain JSON directly.

## 5. Configuring Spring Boot

Examples use **Spring Boot 3.x**, **Java 17+**, **AWS SDK for Java v2**, and **Spring Cloud AWS 3.x**. Choose a Spring Cloud AWS BOM version compatible with your project's Spring Boot version.

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

**application.yml** (sensitive values come from environment/secret manager):

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}

app:
  sns:
    expected-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
    expected-signing-cert-host: sns.ap-southeast-1.amazonaws.com
~~~

Do not commit AWS credentials or database passwords to Git. In AWS, prefer an **IAM role** attached to the workload; on local machines use an AWS profile/credentials provider chain. The SNS client must target the topic's region. Grant permissions by least privilege; **ConfirmSubscription** may depend on SNS topic authentication/permission conditions and subscription settings.

## 6. Building the Signature Verifier Class

The following Java snippet illustrates **the verification algorithm and URL restrictions**. It assumes the endpoint is in the commercial AWS partition and the SNS host is configured for the right region. For production use, adopt a battle-tested verifier or add PKIX/issuer checks and your organization's trust policy for the signing certificate itself; **TLS on the download connection and certificate.checkValidity() do not replace full trust-chain verification**.

~~~java
package demo.sns;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.Signature;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.Base64;
import java.util.List;

@Component
public class SnsSignatureVerifier {
    private static final int MAX_CERT_BYTES = 65536;

    private final String expectedTopicArn;
    private final String expectedCertHost;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public SnsSignatureVerifier(
            @Value("${app.sns.expected-topic-arn}") String expectedTopicArn,
            @Value("${app.sns.expected-signing-cert-host}") String expectedCertHost) {
        this.expectedTopicArn = expectedTopicArn;
        this.expectedCertHost = expectedCertHost;
    }

    public boolean verify(JsonNode sns) throws Exception {
        if (!expectedTopicArn.equals(value(sns, "TopicArn"))) {
            return false;
        }

        String type = value(sns, "Type");
        String version = value(sns, "SignatureVersion");
        if (!version.equals("1") && !version.equals("2")) {
            return false;
        }

        List<String> fields = switch (type) {
            case "Notification" -> List.of(
                    "Message", "MessageId", "Subject",
                    "Timestamp", "TopicArn", "Type");
            case "SubscriptionConfirmation", "UnsubscribeConfirmation" ->
                    List.of("Message", "MessageId", "SubscribeURL",
                            "Timestamp", "Token", "TopicArn", "Type");
            default -> List.of();
        };
        if (fields.isEmpty()) {
            return false;
        }

        StringBuilder canonical = new StringBuilder();
        for (String field : fields) {
            if (field.equals("Subject") && !sns.has("Subject")) {
                continue; // Subject is an optional Notification field
            }
            canonical.append(field).append('\n')
                    .append(value(sns, field)).append('\n');
        }

        URI certificateUri = URI.create(value(sns, "SigningCertURL"));
        if (!trustedSignerUri(certificateUri)) {
            return false;
        }

        X509Certificate certificate = fetchSigningCertificate(certificateUri);
        certificate.checkValidity();

        Signature verifier = Signature.getInstance(
                version.equals("2") ? "SHA256withRSA" : "SHA1withRSA");
        verifier.initVerify(certificate.getPublicKey());
        verifier.update(canonical.toString().getBytes(StandardCharsets.UTF_8));

        byte[] decodedSignature = Base64.getDecoder()
                .decode(value(sns, "Signature"));
        return verifier.verify(decodedSignature);
    }

    private boolean trustedSignerUri(URI uri) {
        return "https".equalsIgnoreCase(uri.getScheme())
                && expectedCertHost.equalsIgnoreCase(uri.getHost())
                && uri.getPort() == -1
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getRawPath() != null
                && uri.getRawPath().matches(
                        "/SimpleNotificationService-[A-Za-z0-9-]+\\.pem");
    }

    private X509Certificate fetchSigningCertificate(URI uri)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(6))
                .GET()
                .build();

        HttpResponse<InputStream> response = http.send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream stream = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("SNS signing certificate unavailable");
            }

            byte[] data = stream.readNBytes(MAX_CERT_BYTES + 1);
            if (data.length > MAX_CERT_BYTES) {
                throw new IOException("SNS certificate too large");
            }
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(new ByteArrayInputStream(data));
        }
    }

    private static String value(JsonNode json, String field) {
        JsonNode node = json.get(field);
        if (node == null || !node.isTextual() || node.asText().isBlank()) {
            throw new IllegalArgumentException("Missing or invalid " + field);
        }
        return node.asText();
    }
}
~~~

**Design choices explained:**

- Exact **TopicArn**, signature version, and **Type** are validated before verification.
- **Subject** is included in the canonical string only if present.
- **SubscribeURL** and **Token** are part of the canonical string for confirmation/unsubscribe, so they cannot be altered while keeping a valid signature.
- **URI** must use HTTPS and an **exact hostname match**. Redirects are not followed; timeouts and certificate size limits reduce the impact of malicious requests.
- **Signature.verify** uses the signing certificate's public key; the input string is joined with **LF** and UTF-8 encoded.
- **Never compare the Signature string directly to a hash**: an SNS signature is a Base64-encoded RSA signature.
- The example does not implement certificate caching or standalone PKIX trust-chain validation; add those in production deployments and test against real SNS certificates/signatures.

**Distinguishing errors:** invalid signatures, malformed fields, or disallowed certificate URLs must be rejected. If the AWS certificate endpoint temporarily fails or the network is unreachable, returning a 5xx server error allows SNS to retry, but timeouts must be bounded and error logs concise without printing tokens/signatures.

## 7. REST Controller Receiving and Handling Three Message Types

The controller accepts **@RequestBody String** and does not lock **consumes=application/json**, because SNS may send **text/plain**. Compare the header and body Type, then invoke the verifier **before any business side effects or confirmation**.

The example below uses **SnsClient** from AWS SDK v2 along with **SnsInboxRepository** introduced in section 8. It assumes the verifier is configured and all requests to the endpoint pass through trusted TLS termination.

~~~java
package demo.sns;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.ConfirmSubscriptionRequest;

import java.security.GeneralSecurityException;

@RestController
@RequestMapping("/webhooks/sns")
public class SnsWebhookController {
    private static final Logger log =
            LoggerFactory.getLogger(SnsWebhookController.class);

    private final ObjectMapper mapper;
    private final SnsSignatureVerifier verifier;
    private final SnsClient sns;
    private final SnsInboxRepository inbox;
    private final String allowedTopicArn;

    public SnsWebhookController(
            ObjectMapper mapper,
            SnsSignatureVerifier verifier,
            SnsClient sns,
            SnsInboxRepository inbox,
            @Value("${app.sns.expected-topic-arn}") String allowedTopicArn) {
        this.mapper = mapper;
        this.verifier = verifier;
        this.sns = sns;
        this.inbox = inbox;
        this.allowedTopicArn = allowedTopicArn;
    }

    @PostMapping
    public ResponseEntity<Void> accept(
            @RequestHeader(value = "x-amz-sns-message-type",
                    required = false) String headerType,
            @RequestBody String rawBody) throws Exception {

        final JsonNode body;
        try {
            body = mapper.readTree(rawBody);
        } catch (JsonProcessingException e) {
            return ResponseEntity.badRequest().build();
        }

        if (body == null || !body.isObject()) {
            return ResponseEntity.badRequest().build();
        }

        String messageType = body.path("Type").asText("");
        if (!messageType.equals(headerType)) {
            return ResponseEntity.badRequest().build();
        }

        if (!messageType.equals("Notification")
                && !messageType.equals("SubscriptionConfirmation")
                && !messageType.equals("UnsubscribeConfirmation")) {
            return ResponseEntity.badRequest().build();
        }

        try {
            if (!verifier.verify(body)) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
            }
        } catch (IllegalArgumentException | GeneralSecurityException e) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }
        // Network/certificate download and infrastructure errors return 5xx so SNS retries.

        switch (messageType) {
            case "SubscriptionConfirmation" -> {
                sns.confirmSubscription(ConfirmSubscriptionRequest.builder()
                        .topicArn(allowedTopicArn)
                        .token(body.path("Token").asText())
                        .build());
                log.info("Confirmed subscription for {}", allowedTopicArn);
                return ResponseEntity.noContent().build();
            }
            case "Notification" -> {
                inbox.saveOnce(
                        body.path("MessageId").asText(),
                        allowedTopicArn,
                        body.path("Message").asText()
                );
                return ResponseEntity.noContent().build();
            }
            case "UnsubscribeConfirmation" -> {
                log.warn("SNS subscription removed for topic {}", allowedTopicArn);
                // Alert operations; do not automatically resubscribe.
                return ResponseEntity.noContent().build();
            }
            default -> {
                return ResponseEntity.badRequest().build();
            }
        }
    }
}
~~~

**Flow explanation:**

1. Parse the JSON envelope using Jackson, checking that **Type** in the body matches the header.
2. Call **SnsSignatureVerifier.verify**. If it fails, return 403, do not process the body, and do not confirm the subscription.
3. For **SubscriptionConfirmation**, use the **Token already inside the signed payload** to call **ConfirmSubscription** on the allowed topic. Do not issue an HTTP GET to an arbitrary client-supplied **SubscribeURL**.
4. For **Notification**, persist the verified message to a durable store **before returning HTTP 204**. A worker executes business logic afterward.
5. For **UnsubscribeConfirmation**, raise an alert to investigate the cause; do not silently re-subscribe to the topic when an administrator may have intentionally unsubscribed.

This auto-confirmation example fits when the endpoint allows only **one pre-configured, approved topic**. If your organization requires per-subscription approval, replace the confirmation branch with saving a **pending request** to a secure store and calling ConfirmSubscription only in a separate approval flow.

**Operational note:** 400/403 codes for malformed or invalid-signature requests are client errors typically not retried by SNS; 5xx or 429 codes suit transient failures needing retries. Failures during confirmation, inbox writes, or AWS calls can cause the endpoint to return 5xx and receive the same message again, so handlers must be idempotent.

## 8. Handling Notifications with a Durable Inbox

### 8.1. Why Not Return 200 Before Persisting Data?

If an endpoint returns 200 immediately upon reading the HTTP POST and then processes on an **ephemeral** background thread, the process could terminate right after returning 200; SNS considers delivery successful, while the event is lost. The **durable inbox** pattern persists the message to a database or queue before returning 2xx.

Example with PostgreSQL (illustrating one option; an equivalent SQS queue/stream/event store can be used):

~~~sql
CREATE TABLE sns_inbox (
    message_id VARCHAR(100) PRIMARY KEY,
    topic_arn VARCHAR(350) NOT NULL,
    event_payload TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
~~~

Idempotent repository keyed by SNS **MessageId**:

~~~java
package demo.sns;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SnsInboxRepository {
    private final JdbcTemplate jdbc;

    public SnsInboxRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void saveOnce(String messageId, String topicArn, String payload) {
        jdbc.update("""
                INSERT INTO sns_inbox(message_id, topic_arn, event_payload)
                VALUES (?, ?, ?)
                ON CONFLICT (message_id) DO NOTHING
                """, messageId, topicArn, payload);
    }
}
~~~

The SQL **ON CONFLICT DO NOTHING** prevents SNS retries with the same **MessageId** from creating duplicate rows. Afterward, a worker reads rows with **processed_at IS NULL**, applies business logic inside an appropriate transaction, and updates the status. If the application receives from multiple topics, a composite key **(topic_arn, message_id)** can serve as the idempotency key.

**This does not mean every business effect is automatically exactly-once.** If the worker performs side effects outside the database (sending email, calling APIs, transferring funds), idempotency is required on those side effects using **eventId**, transaction/outbox, or an appropriate business key. **MessageId** is stable across SNS retries of the same message; publisher-generated **eventId** may be more suitable when the same event is republished in a new request.

### 8.2. Parsing Message Content After Verification

Once the envelope has passed the verifier:

~~~java
String messageJson = verifiedEnvelope.path("Message").asText();
OrderCreated event = objectMapper.readValue(messageJson, OrderCreated.class);
~~~

Here **OrderCreated** is the application DTO. If the subscriber receives plain-text notifications without JSON, define the corresponding data contract. Never use an unverified **Message** string to execute SQL, call internal endpoints, or make business decisions.

## 9. HTTP Responses, Retries, and Dead-Letter Queues

SNS treats HTTP **2xx** status codes as successful delivery. For HTTP/S, SNS considers **5xx** and **429** as retryable errors under the delivery policy; other **4xx** errors are generally treated as permanent failures and not retried under standard policies. Check your active delivery policy because retry counts and timings can be customized.

| Scenario | Suggested Status Code | Effect |
| --- | --- | --- |
| Invalid signature or disallowed topic | **403** | Rejected; not processed |
| Invalid JSON envelope, missing Type, or header mismatch | **400** | Invalid data is not processed |
| Notification saved to durable inbox or duplicate already received | **204** | Accepted; SNS stops retrying |
| Confirmation processed successfully | **204** | Subscription confirmed |
| Temporary database/inbox error | **500/503** | SNS may retry per policy |
| Controlled server overload | **429** | SNS may retry per policy |

Although an HTTP endpoint should not do lengthy processing, you must still ensure durable persistence **before** returning 2xx. AWS documents an HTTP endpoint delivery timeout around **15 seconds** per delivery attempt; keep processing fast, with timeouts on certificate fetches and database calls. Under high message volume, cache verified certificates for a reasonable duration instead of re-fetching indefinitely.

Configure a **DeliveryPolicy** on the topic or subscription to adjust retries/backoff/throttling. Example policy for a subscription in a high-load environment:

~~~json
{
  "healthyRetryPolicy": {
    "minDelayTarget": 1,
    "maxDelayTarget": 60,
    "numRetries": 8,
    "numNoDelayRetries": 0,
    "numMinDelayRetries": 2,
    "numMaxDelayRetries": 2,
    "backoffFunction": "exponential"
  },
  "throttlePolicy": {
    "maxReceivesPerSecond": 20
  },
  "requestPolicy": {
    "headerContentType": "text/plain"
  }
}
~~~

This is a sample policy and should be balanced against actual SLAs and load scale. To avoid losing messages that fail permanently after retries, configure an **SNS subscription DLQ** as an SQS queue to store failed deliveries, along with permissions for SNS to send to the DLQ. A **Subscription DLQ** handles failed HTTP deliveries, unlike an **SQS consumer DLQ** when a worker receives a message but fails to process it.

## 10. Testing Signatures and Webhooks

Testing should distinguish **unit tests verifying the security filter** from **integration tests of real delivery**. Unit tests can use a standard set of messages and test certificates with a controlled trust chain; integration tests using SNS in an AWS sandbox better reflect real signatures, TLS, domains, and retries.

| Test Case | Input / Mutation | Expected Outcome |
| --- | --- | --- |
| **Valid Notification** | Real SNS message from allowed topic | Signature valid; single inbox record; HTTP 204 |
| **Wrong TopicArn** | Possibly valid signature but topic outside allowlist | HTTP 403; not saved |
| **Tampered Message** | Modify eventType/orderId after SNS signed it | Invalid signature; HTTP 403 |
| **Invalid Signature** | Flip one byte in Base64 signature | HTTP 403; not saved |
| **Spoofed SigningCertURL** | HTTP URL, attacker domain, userinfo, or redirect | Rejected; never fetch unknown host |
| **Type/header mismatch** | Header Notification but body SubscriptionConfirmation | HTTP 400 |
| **Subject absent** | Notification without Subject | Canonical string omits Subject, verification still succeeds |
| **Subject present** | Notification with Subject | Canonical string includes Subject in the right position |
| **Unsupported SignatureVersion** | Version other than 1 or 2 | Rejected |
| **Valid Confirmation** | Token and SubscribeURL from real SNS | Verify before calling ConfirmSubscription |
| **Fake Confirmation** | Forged token or disallowed topic | Do not call ConfirmSubscription |
| **Notification retry** | Resend same MessageId | Single inbox record, safely returns 2xx |
| **Broken Inbox** | Database temporarily unavailable | Returns 5xx, SNS can retry |
| **UnsubscribeConfirmation** | Signed message from SNS | Log alert, do not auto-resubscribe |

**Note:** Sample JSON with **Signature="EXAMPLE"** from documentation cannot be used as a positive test because the signature is invalid. To test the verification layer in isolation, you can inject a **certificate loader/trust policy** for a test signer and construct canonical strings following the exact algorithm; production must maintain strict SNS allowlists and trust chains.

### 10.1. Integration Testing Procedure

1. Deploy the HTTPS application with a valid certificate; verify Internet reachability and a suitable health endpoint.
2. Create the topic in the desired region, enable SignatureVersion 2, and set up the workload's IAM role.
3. Call Subscribe; observe the **SubscriptionConfirmation** POST and verify the subscription leaves pending status.
4. Publish a JSON event via SNS, verify HTTP 204, the inbox record, and eventId.
5. Simulate a database outage so the webhook returns 5xx, and verify retries keep **MessageId** unchanged on redelivery.
6. Verify 403/400 cases, **NumberOfNotificationsFailed** metrics, and delivery into the subscription DLQ.
7. Interrupt the system mid-processing to ensure persistence occurs before returning 2xx and the inbox prevents duplicate processing.

CLI command to publish a notification:

~~~bash
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"eventId":"evt-1001","eventType":"ORDER_CREATED","orderId":"ord-1001"}' \
  --region ap-southeast-1
~~~

**Do not** send an HTTP POST directly with fake JSON expecting the verifier to return 204; to verify the end-to-end flow, publish through real SNS or use a test signer configured specifically for tests.

## 11. Security and Operations: Common Pitfalls

### 11.1. Security Mistakes to Avoid

- **Trusting unsigned headers:** an attacker-crafted request can also include **x-amz-sns-message-type: Notification**.
- **Fetching certificates from arbitrary URLs:** opens the door to SSRF and forged keys.
- **Calling only checkValidity():** X.509 expiration checks do not prove the CA chain or SNS origin; proper trust checks are needed.
- **Checking only that Signature is valid:** a message from another topic can still be validly signed by SNS; enforcing a TopicArn allowlist is mandatory.
- **Visiting unverified SubscribeURL/UnsubscribeURL:** can accidentally confirm an unwanted subscription or trigger an unsafe HTTP GET.
- **Auto-confirming all topics:** easily abused to push messages from unintended topics into your webhook.
- **Enabling RawMessageDelivery** for envelope-dependent handlers: drops the signature fields needed for verification.
- **Logging full body/Token/SubscribeURL:** can leak sensitive data and customer information.
- **Returning 2xx before saving:** loses events if the process crashes right after responding.
- **Not being idempotent:** message retries can cause emails, database writes, or API calls to happen twice.

### 11.2. Operational Troubleshooting

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| Subscription stuck in PendingConfirmation | Endpoint unreachable, TLS failure, handler did not confirm, confirmation returned 4xx | Logs, HTTP responses, subscription list |
| Endpoint returns 415 | Controller only accepts application/json, SNS sends text/plain | Remove consumes constraint or configure delivery policy |
| Signature verification fails on real messages | Wrong canonical order, Subject mishandled, un-decoded JSON escaped newlines, wrong version | Compare original fields, rebuild exact canonical string |
| SigningCertURL rejected | Host/region differs from config or missing from allowlist | Check topic region and cert host allowlist |
| Receives HTTP POSTs yet no inbox record | Verifier rejected or database failed | Response codes, concise error logs, metrics |
| Same event processed multiple times | SNS retry or worker retry | Idempotency keys and MessageId/eventId |
| No retries observed | Webhook returned 400/403 instead of transient 5xx/429 | Delivery policy and HTTP status codes |
| SNS reports delivery success yet business logic failed | Handler returned 2xx before saving or downstream consumer failed | Durable inbox, worker retries/DLQ |

Enforce body size limits at the gateway, sensible rate limiting, mandatory HTTPS, request timeouts, and metrics for signature failure rates. For additional protection, restrict traffic sources using appropriate network/WAF controls, though **network allowlists do not replace signature verification**.

## 12. Self-Check Questions and References

**Exercise:** Build a Spring Boot webhook receiving **SubscriptionConfirmation**, **Notification**, and **UnsubscribeConfirmation** for the **order-events** SNS topic. Enable SignatureVersion 2, write a verifier with topic/cert-host allowlists, persist messages into a PostgreSQL inbox, use SQL duplicate prevention, and simulate a database failure to observe retries. Explain why a webhook should not execute long-running work directly inside the request.

**Questions to answer:**

1. Why can relying solely on the x-amz-sns-message-type header be spoofed?
2. How does the canonical string of a Notification with Subject differ from one without Subject?
3. What algorithms do SignatureVersion 1 and 2 use? Why prefer 2?
4. Why must both **SigningCertURL** and **TopicArn** be verified?
5. Why must the signature be verified before calling **ConfirmSubscription** with the token?
6. How does RawMessageDelivery=true affect a handler that verifies the JSON envelope?
7. When should 204, 403, 429, or 503 be returned? In which scenarios will SNS retry?
8. Distinguish SNS **MessageId** from event **eventId**; why are both needed for idempotent processing?

**Official documentation:**

- [Amazon SNS — Verifying the signatures of SNS messages](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)
- [Amazon SNS — Canonical string and verifying a message signature](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-verify-message-signature.html)
- [Amazon SNS — Configure SignatureVersion](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-configure-message-signature.html)
- [Amazon SNS — HTTP/S subscription confirmation JSON](https://docs.aws.amazon.com/sns/latest/dg/http-subscription-confirmation-json.html)
- [Amazon SNS — HTTP/S notification JSON](https://docs.aws.amazon.com/sns/latest/dg/http-notification-json.html)
- [Amazon SNS — Unsubscribe confirmation JSON](https://docs.aws.amazon.com/sns/latest/dg/http-unsubscribe-confirmation-json.html)
- [Amazon SNS — HTTP/S endpoint preparation](https://docs.aws.amazon.com/sns/latest/dg/SendMessageToHttp.prepare.html)
- [Amazon SNS — Delivery retry policy](https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html)
- [Amazon SNS — Raw message delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [AWS API — ConfirmSubscription](https://docs.aws.amazon.com/sns/latest/api/API_ConfirmSubscription.html)

**Expected outcome:** Learners can implement a Spring Boot HTTPS webhook supporting all three SNS message types, confirm subscriptions and process notifications **only after signature verification**, enforce trust restrictions on SigningCertURL, persist durably before returning 2xx, and verify retry/duplicate behavior in AWS managed messaging integration.
