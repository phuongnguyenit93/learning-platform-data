# Integrating SMS with Notification Templates and Handling Delivery Results

## 1. Problem Statement and Objectives

A Spring Boot application needs to send verification codes when users log in, notifications when orders are confirmed, and reminder messages. The application must select the right API for the recipient's country, use an approved signature/sender ID and template, keep credentials secure, and update message status based on carrier results.

Alibaba Cloud **Short Message Service (SMS)** provides APIs for sending messages, querying status, and receiving delivery receipts. Integration does not stop at a successful send call: the system must also manage templates, consent, quotas, billing, retries, and asynchronous callbacks.

This lesson belongs to the **Alibaba Cloud** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module teaches practical Spring Boot integration with managed services from AWS, Azure, Google Cloud, and Alibaba Cloud through their respective libraries; learners need to configure identity/permissions, access storage, messaging, and data, protect secrets, write integration tests, and evaluate differences across cloud providers.

After completing this lesson, you will be able to:

1. Distinguish between the Go China and Go Globe flows to select the right SMS API.
2. Prepare signatures, sender IDs, templates, and compliance details.
3. Call the SMS OpenAPI using Java SDK V2 from Spring Boot.
4. Manage RAM credentials/STS and permissions for sending and querying SMS.
5. Distinguish an accepted API request from an SMS delivered by the carrier.
6. Receive delivery receipts via HTTP webhooks or Simple Message Queue (SMQ).
7. Handle duplicate callbacks, missing callbacks, inconsistent statuses, retries, and QPS limits.
8. Evaluate the legacy SMS starter and decide when to use the SDK directly.

## 2. Lifecycle of an SMS

~~~mermaid
flowchart TD
    A["Business event triggered<br/>OTP / order / reminder"]
    B["Save notification intent<br/>Outbox / queue"]
    C["SMS worker<br/>Check consent, quota, template"]
    D["Alibaba Cloud SMS API"]
    E["MessageId + RequestId<br/>Submission accepted"]
    F["Carrier processes and delivers message"]
    G["SmsReport / GlobeSmsReport<br/>HTTP callback or SMQ"]
    H["Receipt processor<br/>Deduplicate + update status"]
    I["QueryMessage / reconciliation"]
    A --> B --> C --> D --> E --> F --> G --> H
    H --> I
~~~

There are three distinct points in time:

- **Application sends the request:** the SDK returns a response and request ID.
- **SMS platform accepts the request:** the response typically contains ResponseCode = OK and a MessageId. This indicates the platform accepted the request.
- **Carrier returns delivery outcome:** the delivery receipt or QueryMessage indicates whether the message is delivering, delivered, or failed.

Never treat ResponseCode = OK as proof that the phone received the SMS. Save MessageId to reconcile the delivery receipt later.

## 3. Selecting the Right API by Recipient Country

Alibaba Cloud splits the API into two main flows:

| Flow | Recipients | Send API | How Content Is Passed |
| --- | --- | --- | --- |
| **Go China** | Phone numbers in Chinese mainland | SendMessageWithTemplate | Approved signature + TemplateCode + TemplateParam |
| **Go Globe** | Hong Kong, Macao, Taiwan, and countries/regions outside Chinese mainland | SendMessageToGlobe or BatchSendMessageToGlobe | Sender ID if supported + Message text |

**Key point:** SendMessageWithTemplate only sends to Chinese mainland. When sending to Vietnam or any other country outside Chinese mainland, use SendMessageToGlobe. You can manage message templates inside your application and render them into Message text, but do not pass a Go China TemplateCode into the Go Globe API.

### 3.1. Go China: Signatures and Templates

Every message sent to Chinese mainland requires:

- **SMS signature:** the organization/application name displayed at the beginning of the message.
- **Message template:** approved message content, which may contain variables.
- **TemplateCode:** the code issued by the SMS Console after the template is approved.
- **TemplateParam:** JSON containing values for each variable in the template.

Template example:

~~~text
Your verification code is ${code}. The code is valid for ${minutes} minutes.
~~~

When calling the API, TemplateParam must contain the exact variable names, for example:

~~~json
{
  "code": "483921",
  "minutes": "5"
}
~~~

Variable names must match the approved template exactly. Missing variables, mismatched variable names, or exceeding length limits can cause the request to be rejected.

### 3.2. Go Globe: Sender ID and Content

For international SMS, verify the regulations of the destination country. Some countries require Sender ID registration or using local sender numbers. As of 08/09/2025, Alibaba Cloud documentation describes International SMS customers migrating to Sender ID mode; the international flow does not require the Go China signature/template approval workflow, though it must still comply with each country's registration rules.

The SendMessageToGlobe API accepts:

- To: phone number including country code and subscriber number.
- From: Sender ID if required/supported in the destination country.
- Message: message text rendered by the application.
- Type: OTP, NOTIFY, or MKT.

Sender IDs may contain only letters and digits; length limits depend on character types. For example, API documentation specifies up to 11 characters if letters are included and up to 15 digits if numeric-only. Certain countries enforce specific rules, such as DLT or Sender ID pre-registration before sending.

**Billing note:** for International SMS, billing is based on the message submission status. You can still be charged even if the carrier receipt later reports Failed. Therefore, classify errors and reconcile before resending; blind retries can create duplicate messages and inflate costs.

### 3.3. Account Preparation and Compliance

Before integrating:

1. Complete enterprise identity verification and activate SMS.
2. Confirm the account has sufficient balance or a resource package matching the destination.
3. For Go China, create signatures and templates and wait for Approved status.
4. For Go Globe, check sender registration and destination country regulations.
5. Identify the message category: OTP, notification, or promotional.
6. Record consent evidence and provide an unsubscribe mechanism for promotional content.

An approved SMS template cannot have its content or variables edited directly. If changes are needed, create a new template or clone it; the system issues a new TemplateCode and the application must update to that code after approval.

For promotional templates, include an opt-out option per applicable regulations and send only to recipients who have consented. Never use an OTP template to send marketing content.

## 4. Managing Signatures and Templates

### 4.1. Approval Statuses

| Status | Meaning | Action |
| --- | --- | --- |
| **Pending Approval** | Under review | Do not use for sending yet; wait for outcome |
| **Approved** | Accepted | Ready to use in API calls |
| **Failed** | Rejected | Review rejection reason, adjust qualification/content, and resubmit |

SMS getting-started documentation updated on 27/10/2026 estimates signatures are reviewed within roughly 24 hours if submitted during business hours, and templates take about 2–4 hours; Sender ID registration times vary by country. These are reference estimates, not guaranteed SLAs. Do not hardcode approval times into release pipelines.

### 4.2. Template Variable Rules

Key rules for Go China templates:

- Use the ${variable_name} variable format.
- Each variable has a length limit per template rules; current guidelines mention roughly 1–35 characters per variable.
- Do not use compound variables or two consecutive variables side by side.
- Do not create a template consisting solely of variables.
- Keeping to no more than three variables is recommended to reduce carrier rejection risk.
- Verification code variables typically use 4–6 digits or characters per the approved pattern.
- Promotional content requires unsubscribe instructions at the end.

Limits may vary by template type and carrier regulation updates. Always check the guide for your specific template type before submitting for approval.

### 4.3. Signature/Template Management APIs Have Been Updated

Per the API update announcement on 20/01/2026, legacy APIs were replaced by new APIs:

| Legacy API | New API |
| --- | --- |
| AddSmsSign | CreateSmsSign |
| ModifySmsSign | UpdateSmsSign |
| QuerySmsSign | GetSmsSign |
| AddSmsTemplate | CreateSmsTemplate |
| ModifySmsTemplate | UpdateSmsTemplate |
| QuerySmsTemplate | GetSmsTemplate |

The new APIs add qualification fields to meet SMS content governance requirements. You can manage signatures/templates through the Console rather than automating these management APIs; if automating them, use the new APIs per current documentation.

## 5. Recommended Spring Boot Architecture

Do not invoke SMS directly inside business transactions such as placing an order or registering an account. Persist the send request within the same transaction, then let a worker process it asynchronously.

~~~mermaid
flowchart LR
    API["Order / Identity API"] --> DB[("Database<br/>Business + Outbox")]
    DB --> P["Outbox publisher"]
    P --> Q["Queue / job worker"]
    Q --> W["SMS worker"]
    W --> SDK["Alibaba SMS SDK"]
    SDK --> SMS(("SMS platform"))
    SMS --> R["Receipt callback / SMQ"]
    R --> RP["Receipt processor"]
    RP --> DB
~~~

Execution flow:

1. The business service writes an outbox record containing notificationId, message type, recipient, template key, and variable data.
2. The worker reads from the outbox/queue and checks consent, template version, quota, and send attempts.
3. The worker calls the SMS API.
4. If the platform accepts it, save MessageId, RequestId, send timestamp, and status SUBMITTED.
5. The receipt processor receives callbacks or SMQ messages, matches MessageId, and updates delivery status.
6. A reconciliation job calls QueryMessage for messages that have not received a receipt or require verification.

Use a business key such as orderId + notificationType + templateVersion to prevent accidentally creating duplicate notification intents. MessageId links to the provider; notificationId is your system's business key.

## 6. Adding Alibaba Cloud SMS Java SDK V2

Current Java SDK documentation uses artifact **com.aliyun:dysmsapi20180501**. At the **24/11/2026** snapshot, Maven Central lists version **1.0.12**. To use RAM role/STS credential providers, add **credentials-java**; Maven Central lists version **1.0.8**.

~~~xml
<dependencies>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>dysmsapi20180501</artifactId>
        <version>1.0.12</version>
    </dependency>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>credentials-java</artifactId>
        <version>1.0.8</version>
    </dependency>
</dependencies>
~~~

Java SDK V2 uses package com.aliyun.dysmsapi20180501. Do not confuse it with the legacy SDK V1 artifact aliyun-java-sdk-dysmsapi or older API clients.

Inspect the Maven dependency tree when upgrading the SDK to catch conflicts with tea, tea-openapi, tea-util, or the credentials library. When the SDK already pulls in compatible shared dependencies, do not manually introduce an older version.

## 7. Configuring Credentials and the SMS Client in Spring Boot

### 7.1. Using the Default Credential Chain

Configure a singleton Credentials client and SMS client in the Spring context. The Credentials tool can load authentication details from local environment variables/profiles, an ECS RAM role, or OIDC/RRSA on ACK depending on the runtime environment.

~~~java
package demo.sms.config;

import com.aliyun.credentials.Client;
import com.aliyun.teaopenapi.models.Config;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "aliyun.sms")
record SmsProperties(String endpoint) {}

@Configuration
@EnableConfigurationProperties(SmsProperties.class)
public class SmsClientConfiguration {

    @Bean
    public Client aliyunCredentialsClient() throws Exception {
        // Default chain: profile/environment/workload role/OIDC.
        return new Client();
    }

    @Bean
    public com.aliyun.dysmsapi20180501.Client smsClient(
            Client aliyunCredentialsClient,
            SmsProperties properties) throws Exception {

        Config config = new Config();
        config.setCredential(aliyunCredentialsClient);
        config.setEndpoint(properties.endpoint());

        return new com.aliyun.dysmsapi20180501.Client(config);
    }
}
~~~

Instantiate the clients once in the Spring context to reuse connections and the credential cache. Do not create a new Credentials client or product client per request.

### 7.2. Configuring the Endpoint

Application YAML example:

~~~yaml
aliyun:
  sms:
    endpoint: dysmsapi.ap-southeast-1.aliyuncs.com
~~~

The endpoint must match the exact SMS API and region/network path. Current endpoint documentation lists Singapore dysmsapi.ap-southeast-1.aliyuncs.com, Indonesia dysmsapi.ap-southeast-5.aliyuncs.com, Frankfurt dysmsapi.eu-central-1.aliyuncs.com; many Chinese regions use dysmsapi.aliyuncs.com. For VPC access, use the published VPC endpoint for that region. Never construct endpoints manually from region names.

### 7.3. Configuring RAM Permissions

Create a dedicated RAM role or RAM user for the SMS worker. Grant only required actions, for example:

| Operation | RAM Action |
| --- | --- |
| Send Go China SMS | dysms:SendMessageWithTemplate |
| Send Go Globe SMS | dysms:SendMessageToGlobe |
| Send international batch | dysms:BatchSendMessageToGlobe |
| Query status | dysms:QueryMessage |

Send/query APIs may require Resource = "*" per each API's RAM authorization table. Do not grant signature/template administration permissions if the workload only sends messages. If a separate job manages templates, use a separate role.

In production, prefer an ECS instance RAM role or ACK RRSA/OIDC. Local development can use a test RAM user via environment variables:

~~~text
ALIBABA_CLOUD_ACCESS_KEY_ID=<RAM_USER_ACCESS_KEY_ID>
ALIBABA_CLOUD_ACCESS_KEY_SECRET=<RAM_USER_ACCESS_KEY_SECRET>
~~~

Never use the root account's AccessKey, and never commit secrets into application.yml, Docker images, or logs. If using static STS credentials, ensure a mechanism refreshes the token before expiration; long-running workloads should use a caching/auto-refreshing credential provider.

## 8. Sending Template SMS with the Java SDK

### 8.1. Sending a Notification Template to Chinese Mainland

Example service calling SendMessageWithTemplate. Both template and signature must be in Approved status; TemplateParam is serialized from a map to avoid JSON escaping mistakes.

~~~java
package demo.sms.service;

import com.aliyun.dysmsapi20180501.models.SendMessageWithTemplateRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class ChinaSmsSender {

    private final com.aliyun.dysmsapi20180501.Client smsClient;
    private final ObjectMapper objectMapper;

    public ChinaSmsSender(
            com.aliyun.dysmsapi20180501.Client smsClient,
            ObjectMapper objectMapper) {
        this.smsClient = smsClient;
        this.objectMapper = objectMapper;
    }

    public SmsSubmission sendNotification(
            String phoneNumber,
            String signature,
            String templateCode,
            Map<String, String> templateParams) throws Exception {

        String templateParamJson =
                objectMapper.writeValueAsString(templateParams);

        SendMessageWithTemplateRequest request =
                new SendMessageWithTemplateRequest()
                        .setTo(phoneNumber)
                        .setFrom(signature)
                        .setTemplateCode(templateCode)
                        .setTemplateParam(templateParamJson);

        var response = smsClient.sendMessageWithTemplate(request);
        var body = response.getBody();

        if (body == null || !"OK".equals(body.getResponseCode())) {
            throw new IllegalStateException(
                    "SMS submission rejected: "
                            + (body == null ? "empty response"
                            : body.getResponseDescription()));
        }

        return new SmsSubmission(
                body.getMessageId(),
                body.getRequestId(),
                body.getResponseCode(),
                body.getSegments());
    }

    public record SmsSubmission(
            String messageId,
            String requestId,
            String responseCode,
            String segments) {}
}
~~~

Example calling the service:

~~~java
Map<String, String> params = Map.of(
        "orderNo", "ORD-2026-001",
        "status", "confirmed");

SmsSubmission submission = sender.sendNotification(
        "8613800000000",
        "ApprovedSignature",
        "SMS_123456",
        params);
~~~

To must include the country code in the format required by the API. For example, 86 is China's country code; do not pass a raw domestic number without the country code. From is the approved signature name; TemplateCode is the approved template code.

ResponseCode = OK and MessageId only confirm that the SMS platform accepted the request. Persist MessageId immediately upon receiving the response to track the delivery receipt.

### 8.2. Sending International SMS

For countries outside Chinese mainland, use SendMessageToGlobe. The Message text can be rendered from an internal application template; the sender ID must comply with the destination's regulations.

~~~java
import com.aliyun.dysmsapi20180501.models.SendMessageToGlobeRequest;

public String sendInternationalNotification(
        com.aliyun.dysmsapi20180501.Client smsClient,
        String phoneNumber,
        String senderId,
        String message) throws Exception {

    SendMessageToGlobeRequest request =
            new SendMessageToGlobeRequest()
                    .setTo(phoneNumber)
                    .setFrom(senderId)
                    .setMessage(message)
                    .setType("NOTIFY");

    var response = smsClient.sendMessageToGlobe(request);
    var body = response.getBody();

    if (body == null || !"OK".equals(body.getResponseCode())) {
        throw new IllegalStateException(
                "SMS submission rejected: "
                        + (body == null ? "empty response"
                        : body.getResponseDescription()));
    }

    return body.getMessageId();
}
~~~

Valid Type values are OTP, NOTIFY, and MKT. Do not send promotional content under the notification type to bypass policies; the message type must accurately reflect its purpose. If the destination requires Sender ID registration, send only after the ID is approved.

## 9. Receiving Delivery Receipts and Querying Status

### 9.1. Two Ways to Receive Receipts

After sending, configure one of two mechanisms in the SMS Console:

| Mechanism | How It Works | When Suitable |
| --- | --- | --- |
| **HTTP callback** | SMS POSTs a JSON batch to a configured public URL | Application exposes a webhook endpoint |
| **SMQ queue** | SMS pushes receipts into a queue; workers pull and process them | Need buffering, consumer-paced pulling, and decoupling receipt handling from web requests |

Common message types:

- SmsReport: delivery receipt for SMS.
- GlobeSmsReport: delivery receipt for international SMS.
- SmsUp: mobile-originated replies sent back by users.

Do not confuse SmsUp with outbound delivery receipts. A callback may contain multiple records in a single POST; consumers must process them as a batch.

### 9.2. HTTP Callback Payload

Webhook documentation describes an HTTP POST request with a JSON array body. An element may contain:

~~~json
[
  {
    "To": "84901234567",
    "Status": "1",
    "MessageId": "1234567890123456",
    "SmsSize": "1",
    "SendDate": "Tue, 24 Nov 2026 10:00:00 +0800",
    "ReceiveDate": "Tue, 24 Nov 2026 10:00:30 +0800",
    "ErrorCode": "success",
    "ErrorDescription": "success"
  }
]
~~~

Key fields:

| Field | Meaning |
| --- | --- |
| To | Recipient phone number |
| Status | Status per the active callback schema |
| MessageId | ID of the sent message |
| SmsSize | Number of billed segments |
| SendDate | Timestamp sent to the carrier |
| ReceiveDate | Timestamp the receipt was received |
| ErrorCode / ErrorDescription | Outcome code and description |

Spring Boot controller example:

~~~java
package demo.sms.web;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/webhooks/aliyun/sms")
public class SmsReceiptController {

    private final SmsReceiptService receiptService;

    public SmsReceiptController(SmsReceiptService receiptService) {
        this.receiptService = receiptService;
    }

    @PostMapping(
            path = "/report",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ReceiptAck> receive(
            @RequestBody List<SmsReport> reports) {

        receiptService.persistIdempotently(reports);
        return ResponseEntity.ok(new ReceiptAck(0, "received"));
    }

    public record SmsReport(
            @JsonProperty("To") String to,
            @JsonProperty("Status") String status,
            @JsonProperty("MessageId") String messageId,
            @JsonProperty("SmsSize") String smsSize,
            @JsonProperty("SendDate") String sendDate,
            @JsonProperty("ReceiveDate") String receiveDate,
            @JsonProperty("ErrorCode") String errorCode,
            @JsonProperty("ErrorDescription") String errorDescription) {}

    public record ReceiptAck(int code, String msg) {}
}
~~~

Return HTTP 200 only after the receipt has been durably persisted (or enqueued internally). If persistence fails, return an error so the callback can be retried. The endpoint should use HTTPS, restrict network ingress, and verify that MessageId corresponds to a message sent by your application. Never treat raw JSON payloads as identity authentication; if a more private ingestion channel is needed, consider an SMQ consumer.

### 9.3. Callback Status and QueryMessage Use Different Enums

This is a common source of mapping bugs:

| Source | Value | Meaning per Documentation |
| --- | --- | --- |
| **SMS webhook receipt** | 1 | Sent / dispatched to carrier per callback schema |
| **SMS webhook receipt** | 2 | Failed |
| **SMS webhook receipt** | 6 | Expired |
| **QueryMessage API** | 1 | Delivered |
| **QueryMessage API** | 2 | Delivery failed |
| **QueryMessage API** | 3 | Delivering |

Do not share a single numeric enum across all callback/API types. Store the receipt source (SmsReport, GlobeSmsReport, QueryMessage), destination, and raw status so mappings align with the exact message type's documentation. "Sent" in a receipt does not necessarily mean the same thing as "Delivered" in a query result.

### 9.4. Querying via QueryMessage

If a callback is missing or verification is needed, call QueryMessage with MessageId. The API returns delivery status, ErrorCode, ReceiveDate, SendDate, carrier details, and RequestId.

~~~java
import com.aliyun.dysmsapi20180501.models.QueryMessageRequest;

public String queryStatus(
        com.aliyun.dysmsapi20180501.Client smsClient,
        String messageId) throws Exception {

    QueryMessageRequest request =
            new QueryMessageRequest().setMessageId(messageId);

    var response = smsClient.queryMessage(request);
    var body = response.getBody();

    if (body == null) {
        throw new IllegalStateException("Empty QueryMessage response");
    }

    return body.getStatus();
}
~~~

Per current API documentation, QueryMessage has a published limit of **300 QPS per user within the same Alibaba Cloud account**. Do not aggressively poll per message; only query messages still in an undetermined state or run a scheduled batch reconciliation job at an appropriate cadence.

## 10. Idempotency, Retries, and Load Throttling

### 10.1. Callbacks Can Be Duplicated or Missing

Alibaba Cloud warns that delivery receipts are not guaranteed to be idempotent; network issues or timeouts can cause duplicate or missing receipts. Therefore:

- Do not update business state by counting how many times a callback arrives.
- Never send another SMS just because a duplicate callback was received.
- Record receipt events in an audit table.
- Use a deduplication key built from MessageId, status, receive time, and error code or a payload hash.
- Update message state using a state machine so older statuses cannot overwrite newer ones.
- Use QueryMessage or Delivery Reports to reconcile messages missing receipts.

When using HTTP callbacks, return 200 only after persisting/enqueuing succeeds. With SMQ, acknowledge/delete the message only after durable processing; if a transient business error occurs, allow the queue to redeliver the message.

### 10.2. Never Blindly Retry on Request Timeout

If the client times out before receiving a response, you cannot conclude that the SMS API did not receive the request. The request may have reached the SMS platform while the response was lost. Resending immediately could deliver two SMS messages to the recipient and charge the account twice.

Set an intermediate state such as SUBMISSION_UNKNOWN when the outcome is unknown. Log RequestId if available, retain the business key, inspect Messaging Records or run reconciliation, and only resend when there is evidence the prior request was not accepted. For OTPs, enforce resend limits and validity windows.

### 10.3. QPS and Quotas

Current flow-control documentation lists these reference limits:

| API | Published QPS |
| --- | ---: |
| SendMessageWithTemplate | 1,500 |
| SendMessageToGlobe | 2,000 |
| BatchSendMessageToGlobe | 1 |
| QueryMessage | 300 |

Actual limits may vary by account, API, and region; check Quota Center before running large campaigns. Apply rate limiting in the application, batch using the appropriate API, use backoff with jitter when throttled, and monitor QPS_LIMIT_CONTROL.

For Go Globe, documentation notes the batch API supports up to 1,000 recipients per request. Batching can have different latency characteristics than single sends; OTPs typically need single-message sends to prioritize timeliness.

### 10.4. Recommended Application States

| Internal Status | Meaning |
| --- | --- |
| PENDING | Notification intent has been saved |
| SENDING | Worker is calling the SMS API |
| SUBMITTED | SMS platform accepted the request and issued a MessageId |
| SUBMISSION_UNKNOWN | Timeout or error makes it unclear whether the request was accepted |
| DELIVERING | QueryMessage reports delivery in progress |
| DELIVERED | Carrier confirmed delivery per the corresponding receipt source |
| FAILED | Submission or delivery failed |
| EXPIRED | Message exceeded its validity period |
| RECONCILIATION_REQUIRED | Missing receipt or conflicting callback/query data |

Store the raw status and status source alongside the internal enum. For SMS, Delivered typically reflects carrier confirmation and does not prove the recipient read the message.

## 11. Security and Operations

- Use RAM roles/STS with least privilege; never use the root AccessKey.
- Never write full phone numbers, OTPs, message contents, or tokens into standard logs.
- Generate OTP codes using a secure random generator, store hashes server-side, enforce TTLs, and limit verification attempts.
- Verify user authorization before sending an SMS to a phone number to prevent API abuse for spamming or cost inflation.
- Store consent and unsubscribe status for marketing SMS.
- Encrypt phone numbers and template parameter data at rest if required by data policies.
- Retain SMS data only for the required retention window; restrict access to delivery reports.
- Never allow public callback endpoints to accept arbitrary payloads that mutate any MessageId's status.
- Monitor request rate, sent count, billed segments, delivery success/failure, QPS throttling, callback lag, and unreconciled messages.

### 11.1. Common Errors

| Code/Error | Cause | Resolution |
| --- | --- | --- |
| SMS_SIGN_NAME_ILLEGAL | Signature does not exist, was rejected, or is misspelled | Verify signature is Approved and From matches exactly |
| SMS_CONTENT_CODE_ILLEGAL | Template does not exist, is unapproved, or was rejected | Check TemplateCode and approval status |
| CONTENT_MISSING_PARAMETERS | Missing variable or mismatched variable name | Compare TemplateParam JSON against template |
| PARAM_LENGTH_LIMIT | Variable value is too long | Shorten value to fit template limits |
| INVALID_SENDERID | Invalid or unapproved international Sender ID | Verify Sender ID for the destination |
| MOBILE_NUMBER_ILLEGAL | Malformed phone number | Normalize country code and subscriber number |
| RAM_PERMISSION_DENY | RAM principal lacks required action | Check required dysms:* policies |
| QPS_LIMIT_CONTROL | API quota exceeded | Throttle rate, back off, and check Quota Center |
| AMOUNT_NOT_ENOUGH | Resource package or account balance exhausted | Check billing/resource packages |
| SMS_SECURITY_INTERCEPTED | Blocked by risk-control policy | Review content, frequency, and SMS regulations |
| SYSTEM_ERROR | Transient platform error | Log RequestId, apply bounded retries after classification |

Do not infinitely retry permission, signature/template, phone number, risk-control, or insufficient-balance errors. Those errors require fixing configuration, content, or account state first.

## 12. Evaluating Legacy Aliyun SMS Spring Boot Starter

Alibaba provides aliyun-sms-spring-boot-starter under the aliyun-spring-boot project. The artifact on Maven Central is **1.0.0**. The starter's POM pulls in:

- aliyun-java-sdk-core
- aliyun-java-sdk-dysmsapi
- aliyun-sdk-mns
- aliyun-context-spring-boot-starter

Project samples use ISmsService, SendSmsRequest, SmsReportMessageListener, and properties alibaba.cloud.access-key, alibaba.cloud.secret-key, and alibaba.cloud.sms.report-queue-name. These are legacy APIs and configuration styles, not examples of Java OpenAPI SDK V2 dysmsapi20180501.

The repository README only declares support for Spring Boot 2 and above, without a specific matrix proving Spring Boot 3/4 compatibility. Therefore:

- **Existing applications already using the starter:** you may keep it if tested on your exact Boot/JDK, API, and MNS queue; check transitive SDK versions, credentials, and callback behavior.
- **New projects or Boot 3/4:** prefer Java OpenAPI SDK V2 directly with explicit beans/clients and adapters.
- **Need newer SMS API features:** inspect current V2 APIs first; do not assume the legacy starter wraps newer APIs such as SendMessageWithTemplate or QueryMessage.

If keeping the starter, read the samples and source for that exact version before copying properties. Do not mix legacy ISmsService with generated SDK V2 clients in the same sending flow without an adapter and version governance.

## 13. Hands-on Exercise

**Exercise:** Build a notification service that sends order-confirmation SMS messages and processes delivery receipts.

1. Set up a test SMS account and complete verification requirements.
2. For Go China, create a notification signature/template and wait for Approved; for Go Globe, verify sender ID and destination country regulations.
3. Add dysmsapi20180501 and credentials-java to Spring Boot.
4. Create singleton Credentials and SMS clients, configuring the endpoint by region.
5. Write an SmsSender adapter calling SendMessageWithTemplate for Go China or SendMessageToGlobe for international recipients.
6. Persist notification intents into an outbox and let a worker send asynchronously.
7. Save MessageId, RequestId, template version, segment count, and SUBMITTED status.
8. Configure SmsReport or GlobeSmsReport via HTTP callback/SMQ.
9. Implement an idempotent receipt processor and test duplicate callbacks, batch callbacks, and delayed callbacks.
10. Use QueryMessage to reconcile messages missing receipts.
11. Simulate timeouts, rejected templates, invalid phone numbers, exhausted quotas, and QPS throttling.
12. Compare direct SDK V2 against aliyun-sms-spring-boot-starter 1.0.0 across APIs, credentials, callbacks, and upgradability.

**Review Questions:**

1. Why do Go China and Go Globe use two different sending APIs?
2. Can SendMessageWithTemplate send to Vietnamese phone numbers? Why or why not?
3. How does ResponseCode = OK differ from Status = Delivered?
4. How must TemplateParam match the template?
5. Why can't an approved signature or template be edited directly?
6. What are MessageId and RequestId used for?
7. Why must receipt callbacks be processed idempotently?
8. Why shouldn't callback Status = 1 automatically map the same way as QueryMessage.Status = 1?
9. When the SDK times out before receiving a response, why shouldn't you resend immediately?
10. When should you use an HTTP webhook versus an SMQ queue?
11. Which actions does a RAM role need to send and query SMS?
12. Why should new projects evaluate Java OpenAPI SDK V2 instead of the legacy 1.0.0 starter?

## 14. References

- [Alibaba Cloud SMS — Integration overview](https://www.alibabacloud.com/help/en/sms/developer-reference/using-openapi): choosing APIs/SDKs, Go China, and Go Globe.
- [Alibaba Cloud SMS — Getting started](https://www.alibabacloud.com/help/en/sms/getting-started/get-started-with-sms): activation requirements, compliance, review times, and billing.
- [Alibaba Cloud SMS — Java SDK](https://www.alibabacloud.com/help/en/sms/developer-reference/using-java-openapi-example): dysmsapi20180501 dependency, credentials, and Java samples.
- [SendMessageWithTemplate](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-sendmessagewithtemplate): template API for Chinese mainland, request/response, and RAM actions.
- [SendMessageToGlobe](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-sendmessagetoglobe): international SMS API, sender ID, type, and quotas.
- [QueryMessage](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-querymessage): querying delivery status by MessageId.
- [SMS endpoints](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-endpoint): public/VPC endpoints by region.
- [Signature and template review](https://www.alibabacloud.com/help/en/sms/user-guide/approval-process): statuses and approval workflow.
- [Create SMS template](https://www.alibabacloud.com/help/en/sms/user-guide/create-message-templates): template types, variables, limits, and consent.
- [API updates for signatures and templates](https://help.aliyun.com/en/sms/announcement-on-sms-service-update-signature-template-interface): updated signature/template management APIs.
- [Configure SMS delivery receipts](https://www.alibabacloud.com/help/en/sms/developer-reference/obtain-delivery-receipt/): HTTP callbacks and SMQ queues.
- [SMS webhook](https://www.alibabacloud.com/help/en/sms/developer-reference/sms-webhook): receipt payloads, message types, and queue processing.
- [SMS flow-control information](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-quota): QPS limits per operation.
- [International SMS error codes](https://www.alibabacloud.com/help/en/sms/developer-reference/error-codes): API, sender, template, quota, and delivery errors.
- [Aliyun Spring Boot Starters](https://github.com/alibaba/aliyun-spring-boot): source and samples for the legacy SMS starter.
- [Maven Central — dysmsapi20180501](https://central.sonatype.com/artifact/com.aliyun/dysmsapi20180501): Java SDK V2 version.
- [Maven Central — aliyun-sms-spring-boot-starter](https://central.sonatype.com/artifact/com.alibaba.cloud/aliyun-sms-spring-boot-starter): POM and dependencies of the legacy starter.

**Expected Outcome:** Learners integrate SMS into Spring Boot following the proper Go China/Go Globe flow, use valid signatures/templates or sender IDs, manage RAM credentials, persist MessageId, ingest and reconcile delivery receipts, handle duplicate/missing callbacks, and control quotas, retries, and messaging costs.
