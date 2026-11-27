# Integrating Logging, Email Delivery, and On-Demand Function Invocation

Spring Boot on Oracle Cloud Infrastructure (OCI) often needs three capabilities beyond databases, storage, and messaging: sending application logs to a central searchable location; sending transactional emails through Email Delivery infrastructure; and invoking serverless tasks when independent processing or on-demand scaling is needed. OCI provides the corresponding managed services: Logging, Email Delivery, and Functions. Spring Cloud Oracle 2.0.4 includes dedicated starters to bring them into your application through familiar Spring APIs.

These three integrations address three distinct flows:

- **Logging** sends diagnostic records from the application into a log created in OCI Logging. The service also collects service logs and audit logs from OCI.
- **Email Delivery** accepts emails over SMTP or HTTPS, verifies sender and domain settings, and relays them to recipient mail servers.
- **Functions** accepts authenticated invocations, runs a deployed function inside a Functions application, and returns a synchronous result or continues running in detached mode.

Do not treat the three starters as an all-automatic system. The Logging starter does not automatically convert every SLF4J line into a custom log; Email Delivery does not guarantee inbox placement simply because SMTP accepted the message; detached Functions are not synchronous transactions with Spring Boot's database. Applications must still design buffering/retries, identities, permissions, idempotency, auditing, and result handling.

This lesson uses `document-service` as the running example: the service emits business and technical logs, sends contract status emails, and invokes a function to generate thumbnails or scan files. Examples use Spring Cloud Oracle 2.0.4; when selecting a different version, verify the compatibility matrix against your project's Spring Boot, Java, and OCI SDK versions.

## 1. Learning Objectives and Architecture

After this lesson, you can:

1. Distinguish OCI Audit Logs, Service Logs, and Custom Logs.
2. Create log groups/log objects and configure the Spring Cloud Oracle Logging starter.
3. Use `LogService` to send custom logs and understand the API's boundaries.
4. Grant separate IAM permissions for writers, readers, and logging administrators.
5. Design structured logs, correlation IDs, and rules for stripping secrets/PII.
6. Understand retention, search, archiving, Connector Hub, and ingestion costs.
7. Provision Email Domains, SPF, DKIM, and Approved Senders per region.
8. Create dedicated SMTP credentials, store secrets, and configure Spring Mail.
9. Use `MailSender`/`JavaMailSender` to send plain text, HTML, and attachments.
10. Handle bounces, suppressions, quotas, retries, and email delivery status.
11. Integrate the OCI Functions starter and invoke functions through a Spring bean.
12. Distinguish Sync vs. Detached invocations, timeouts, and result destinations.
13. Grant `fn-invocation` permissions scoped to specific applications/functions.
14. Design outbox, idempotency, timeouts, and observability for all three integrations.
15. Write unit/integration tests and error-handling runbooks.

~~~mermaid
flowchart TD
    A["Spring Boot document-service"] --> B["Application logging"]
    A --> C["Email notification service"]
    A --> D["Function invocation service"]
    B --> E["Spring Cloud OCI LogService"]
    E --> F["OCI Logging custom log"]
    F --> G["Search / alert / Connector Hub"]
    C --> H["Spring MailSender / JavaMailSender"]
    H --> I["OCI Email Delivery SMTP"]
    I --> J["Approved sender + SPF/DKIM"]
    J --> K["Recipient mail server"]
    D --> L["Spring Cloud OCI Function"]
    L --> M["OCI Functions invoke endpoint"]
    M --> N["Function application"]
    N --> O["Sync response or detached result"]
~~~

The three services use different identities and permissions. Spring Boot's OCI workload identity authenticates Logging and Functions API calls; Email Delivery SMTP uses an Oracle-generated SMTP username/password. Therefore, a single credential cannot serve all three flows.

## 2. Distinguishing the Three Services and Data Flows

| Service | Input | Output | Used For |
| --- | --- | --- | --- |
| OCI Logging | Audit/service/custom log entries | Search, alerts, archive, export | Diagnostics, operations, and investigations |
| OCI Email Delivery | SMTP message or HTTPS submission | Outbound email queue, delivery/bounce/suppression logs | Transactional emails and notifications |
| OCI Functions | Signed invocation with function OCID and payload | Sync response or Detached status | Independent processing, event-driven tasks, and serverless compute |

### 2.1. Logging Does Not Replace Business Auditing

The OCI Audit service records API calls made to public tenancy endpoints. OCI Service Logs record activity emitted by supported OCI services. Custom Logs accept data sent by applications or agents. A log line in Spring Boot does not automatically become an OCI Audit event.

When you need to prove which user downloaded a contract, record an application-level audit event in the business layer and link it with the request ID/trace ID. Cloud Audit Logs complement this with the OCI principal, operation, and resource; both sources serve complementary roles.

### 2.2. Accepted Email Does Not Guarantee Delivery

An SMTP server can return success once it enqueues a message. Afterward, the recipient's mail server may reject it, the mailbox may bounce, or the address may enter the suppression list. Monitor Email Delivery logs, bounces, and suppression lists; never mark a business step as "email received by user" purely based on an error-free SMTP send.

### 2.3. Detached Functions Do Not Return Immediate Business Outcomes

A Sync invocation waits for the function to complete and returns its response. A Detached invocation returns once execution starts; the function continues running independently. If the application needs the final outcome, configure success/failure destinations or another status channel. HTTP 202 does not mean the business task succeeded.

## 3. OCI Logging: Log Types, Log Groups, and Log Objects

### 3.1. Three Log Types

OCI Logging provides three primary categories:

| Type | Emitter | Examples |
| --- | --- | --- |
| Audit Logs | OCI Audit service | User creates bucket, edits IAM policy, calls API |
| Service Logs | OCI native services | API Gateway, Functions, Load Balancer, Object Storage, VCN Flow Logs |
| Custom Logs | Applications, agents, or external sources | Spring Boot events, application diagnostics, VM logs |

All log types are organized and queried via Logging Search. Service log categories vary per service; enabling Object Storage read/write access logs does not automatically enable Functions logs.

### 3.2. Log Groups and Log Objects

A log group is a logical container inside a compartment. A log is an individual resource with its own OCID residing inside a log group. Every custom log or service log must belong to a log group.

Organize log groups by purpose and sensitivity, for example:

~~~text
Compartment Observability
├── app-runtime-logs
│   ├── document-service-prod
│   └── document-worker-prod
├── security-logs
│   ├── privileged-access
│   └── sensitive-document-access
└── platform-service-logs
    ├── functions-invocation
    └── object-storage-access
~~~

Log groups let you apply IAM policies per data category. You can place logs containing PII into a separate log group and allow only security/auditor roles to read them. You do not need to create a new compartment for every log category when log groups already provide the required access boundary.

### 3.3. Create the Custom Log Before Sending

Standard workflow:

1. Select the compartment for logs.
2. Create a log group.
3. Create a custom log inside the log group.
4. Save the log OCID.
5. Grant push permissions to the workload principal.
6. Configure the log OCID in Spring Boot.
7. Send a test event and verify it in Logging Search.

The Spring Cloud Oracle Logging starter requires the destination log ID via property:

~~~yaml
spring:
  cloud:
    oci:
      logging:
        enabled: true
        logId: REPLACE_WITH_CUSTOM_LOG_OCID
~~~

The property name in Spring Cloud Oracle is `spring.cloud.oci.logging.logId`. The log must already exist in a compartment where the principal has write permission. Never pass a display name instead of an OCID.

### 3.4. Service Logs and Custom Logs

To enable Service Logs, open the target resource in the OCI Console, navigate to Logs, and enable the desired category. Some newer resources have logs enabled by default or during provisioning; always verify actual status.

Custom Logs can be sent directly via the Logging Ingestion API or via the Unified Monitoring Agent. The agent is based on Fluentd and runs on OCI Compute to collect logs from machines. For containers/Kubernetes, use an architecture-appropriate agent/collector and route logs to a custom log.

### 3.5. Encoding and Content

OCI Logging accepts UTF-8 text. For structured logging, the application can serialize JSON into a UTF-8 string before sending. Keep schemas stable for querying by timestamp, level, service, environment, `traceId`, `eventType`, and outcome.

Never write to logs:

- Passwords, SMTP credentials, OAuth tokens, private keys, or wallets.
- `Authorization` headers, cookies, or signed URLs/PAR URLs.
- Full contents of contracts, uploaded files, or sensitive request bodies.
- Full emails/phone numbers/personal identifiers unless strictly necessary.
- SQL bind parameters containing personal data.
- Stack traces containing connection strings or secrets.

Use opaque identifiers, reason codes, and pseudonymized fields. Archived logs are also sensitive data requiring dedicated IAM, retention, and auditing.

## 4. Spring Cloud Oracle Logging Starter

### 4.1. Dependency

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-logging</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-logging")
}
~~~

Manage versions via the Spring Cloud Oracle BOM/version catalog matching your Spring Boot baseline. Do not mix starter 2.0.4 with incompatible Spring Framework/Boot versions.

Spring Cloud Oracle 2.0.4 announced an upgrade to Spring Boot 4.1.1. If your project uses Spring Boot 3.x or a different Java baseline, inspect release notes and compatibility before adding the starter; never force transitive dependencies onto unsupported versions.

### 4.2. Authentication and Region

The starter uses OCI Core authentication/configuration. Example on OCI Compute:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      logging:
        enabled: true
        logId: REPLACE_WITH_CUSTOM_LOG_OCID
~~~

Local development can use a `FILE` profile:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: C:/Users/developer/.oci/config
      region:
        static: ap-singapore-1
      logging:
        enabled: true
        logId: REPLACE_WITH_TEST_LOG_OCID
~~~

On an OKE enhanced cluster, select `WORKLOAD_IDENTITY` if supported by the starter/SDK version and cluster. Never fall back automatically from instance/workload identity to an API key if authentication fails; that masks policy errors and can cause the workload to run under a stronger identity than intended.

### 4.3. The `LogService` Bean

The starter auto-configures a `LogService` bean. Basic API per Spring Cloud Oracle docs:

~~~java
import com.oracle.cloud.spring.logging.LogService;
import org.springframework.stereotype.Service;

@Service
public class OciLogPublisher {

    private final LogService logService;

    public OciLogPublisher(LogService logService) {
        this.logService = logService;
    }

    public void publish(String logText) {
        logService.putLog(logText);
    }
}
~~~

`putLog` accepts a log string and returns a `PutLogsResponse`. The minimal example above ignores the response; production code should handle exceptions, metrics, and backpressure according to reliability requirements.

### 4.4. Sending Structured JSON Logs

The basic `LogService` API takes a string. You can serialize a record to JSON:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oracle.cloud.spring.logging.LogService;
import java.time.Instant;
import org.springframework.stereotype.Service;

public record ApplicationLogEvent(
        Instant timestamp,
        String level,
        String service,
        String environment,
        String eventType,
        String traceId,
        String requestId,
        String outcome,
        String message) {
}

@Service
public class StructuredOciLogPublisher {

    private final LogService logService;
    private final ObjectMapper objectMapper;

    public StructuredOciLogPublisher(
            LogService logService,
            ObjectMapper objectMapper) {
        this.logService = logService;
        this.objectMapper = objectMapper;
    }

    public void publish(ApplicationLogEvent event)
            throws JsonProcessingException {
        String json = objectMapper.writeValueAsString(event);
        logService.putLog(json);
    }
}
~~~

This record holds only necessary metadata. Never put raw user input or sensitive payloads inside `message`. You can add exception class/code, but redact stack traces and avoid leaking secrets.

### 4.5. The Logging Starter Does Not Automatically Capture Every SLF4J Event

`LogService` is an explicit API for pushing logs. Simply adding the starter does not automatically ship every `logger.info`/`logger.error` statement in your application to OCI Logging.

There are two approaches:

- Call `LogService` at specific points where custom events must be sent.
- Keep your logging backend/SLF4J writing to stdout or files, then use the Unified Monitoring Agent/collector to ship logs to OCI Logging.

Avoid calling the Logging API synchronously for every debug line on high-traffic hot paths. At high volume, use batch ingestion, an agent, or an asynchronous pipeline. Define queue capacity, retries, drop policies, and alerting when the sink is unavailable.

### 4.6. IAM Permissions for Logging

A principal pushing custom logs needs permission on `log-content` in the compartment holding the log:

~~~text
Allow dynamic-group DocumentService to use log-content in compartment Observability
~~~

A log-reading group needs permissions to read content and metadata:

~~~text
Allow group LogReaders to read log-content in compartment Observability
Allow group LogReaders to read log-groups in compartment Observability
~~~

Administrators managing log groups/log objects may need:

~~~text
Allow group LoggingAdmins to manage log-groups in compartment Observability
~~~

Never grant `manage log-groups` to an application runtime just to emit logs. Once log groups/log objects are provisioned, the workload only needs permission to push `log-content`. Depending on policy scope, restrict permissions to a specific log group using `target.loggroup.id`.

### 4.7. Search and Query

Logs can be searched via Console, API, and CLI. When debugging, filter by:

- Timestamp/time range.
- Service/environment.
- Log group/log OCID.
- Trace ID/request ID.
- Event type and outcome.
- OCI principal/resource for service/audit logs.

Use correlation IDs across logs and function invocations to trace a single request across API, database, Object Storage, Email Delivery, and Functions.

## 5. Logging Retention, Archiving, and Cost

### 5.1. Retention

Retention for a log can be set in 30-day increments up to 180 days. Lowering retention from six months to one month makes data older than one month unsearchable in that log. Verify retention requirements before making changes.

If investigation/compliance mandates exceed 180 days, do not treat Logging Search as your sole long-term archive.

### 5.2. Connector Hub Archiving

Connector Hub can route logs to Object Storage for archiving, or forward them to Streaming or other supported targets. Example:

~~~mermaid
flowchart LR
    A["OCI Logging"] --> B["Connector Hub"]
    B --> C["Object Storage archive"]
    B --> D["OCI Streaming"]
    B --> E["Monitoring / downstream processor"]
~~~

Object Storage archives require their own lifecycle, encryption, IAM, and retention settings. When using immutable buckets, design legal holds and retention periods carefully before locking policies.

### 5.3. Cost and Volume

Cost/usage depends on ingested bytes, storage, queries, and connected services. Control spend by:

- Enabling only service log categories genuinely needed.
- Never logging large request/response bodies.
- Choosing appropriate log levels per environment.
- Sampling debug/trace logs under high load.
- Avoiding logging the same event at multiple layers without reason.
- Using log groups by classification to govern retention/access.
- Setting alerts on anomalous spikes in ingested bytes.
- Archiving older logs instead of extending search retention on every log.

## 6. OCI Email Delivery: Architecture and Preparation

### 6.1. SMTP and HTTPS Submission

OCI Email Delivery supports sending email via SMTP or HTTPS API. The Spring Cloud Oracle Email starter integrates with Spring Mail over SMTP, providing `MailSender` and `JavaMailSender`.

SMTP fits applications already using JavaMail/Spring Mail. HTTPS submission fits direct Email Delivery API calls via OCI SDK/authentication. Do not confuse Email Delivery with OCI Notifications: Notifications publishes alerts to topics/subscribers, whereas Email Delivery handles transactional and marketing emails.

### 6.2. Provisioning Steps

Before sending email:

1. Create a dedicated IAM user for SMTP sending.
2. Create groups/policies for Email Delivery.
3. Generate SMTP credentials for that user.
4. Create an Email Domain for an organization-owned domain.
5. Configure SPF in DNS.
6. Configure DKIM and publish OCI-generated records.
7. Create an Approved Sender in the sending region.
8. Retrieve the region's SMTP endpoint/port.
9. Configure TLS and secrets in Spring Boot.
10. Send a test email to a controlled address and inspect delivery logs.

The sending domain must have DNS owned/controlled by your organization. Never use Gmail, Yahoo, Hotmail, or public mailbox domains as sender domains in Email Delivery.

### 6.3. Approved Sender

Every address in the `From` header sent through OCI Email Delivery must be an Approved Sender; otherwise the message is rejected. An Approved Sender:

- Belongs to a compartment.
- Exists only in the region where it was created.
- Must be created separately in each region from which the application sends mail.
- Should be created in an application/email compartment rather than the root compartment.
- Should align the SMTP envelope `From` with the `From` header.

Sending with multiple addresses in the `From` header complicates DMARC alignment and sender verification. Use one approved `From` address per email category.

### 6.4. Approved Domain

Once DKIM on an Email Domain is active, you can create an approved sender like `@domain.com` to cover addresses in that domain as supported by the service. A DKIM key signs only senders whose domain matches exactly, including subdomains. For example, a key for `sub.example.com` does not automatically sign senders at `example.com`.

### 6.5. SPF

SPF is a TXT record allowing mail receivers to verify which infrastructure is authorized to send on behalf of a domain. For Asia/Pacific commercial regions, OCI publishes this sample record:

~~~text
v=spf1 include:ap.rp.oracleemaildelivery.com ~all
~~~

For Americas and Europe, include the corresponding domain. Pick the exact value for your sending region from the OCI Console/docs. If the domain already has an SPF record, merge the `include` into a single valid SPF TXT record; never create multiple standalone SPF records for the same domain.

### 6.6. DKIM

DKIM signs emails with a private key and publishes the public key via DNS. OCI generates a selector and CNAME record (or realm-specific record type), and the domain owner adds the record in their authoritative DNS provider.

- Create DKIM only for domains the organization controls.
- Verify the record is published under the exact `selector._domainkey`.
- Wait for DNS propagation and run OCI's verification check.
- Email Delivery supports up to two DKIM keys per email domain, with only one active at a time.
- Oracle recommends rotating DKIM keys periodically; current documentation cites a six-month cycle.

SPF/DKIM authenticate the sender and improve deliverability; DMARC lets domain owners specify policies for emails failing alignment. Configure DMARC per organizational domain policy.

## 7. SMTP Credentials, IAM, and Regional Endpoints

### 7.1. SMTP Credentials

SMTP credentials are an Oracle-generated username/password pair. You cannot supply custom values. An IAM user can have at most two active SMTP credentials at once; credentials do not expire automatically.

Best practices:

- Create a dedicated IAM user solely for SMTP.
- Never use a developer's Console/admin credentials.
- Store username/password in OCI Vault or a secret manager.
- Never commit them to `application.yml`, Docker images, or CI logs.
- Rotate by creating a second credential, updating the application, verifying delivery, and deleting the old credential.
- If the user already has two active credentials, delete one before generating another.
- Never expose SMTP passwords in exceptions, logs, or metrics.

### 7.2. IAM Policies

A principal sending email needs permission to use Approved Senders in the compartment:

~~~text
Allow group EmailSenders to use approved-senders in compartment EmailDelivery
~~~

Sender administrators may need permission to manage Approved Senders:

~~~text
Allow group EmailAdmins to manage approved-senders in compartment EmailDelivery
~~~

Managing suppression lists is tenancy-scoped per service policy:

~~~text
Allow group EmailAdmins to manage suppressions in tenancy
~~~

Separate `EmailSenders` from `EmailAdmins`. Runtime services only send mail; they do not need to create/delete senders or edit suppression lists. OCI docs include dedicated policy templates for SMTP credentials and `email-family`; verify exact policies for your identity domain and compartment.

### 7.3. Global SMTP Credentials, Regional Senders

SMTP credentials belong to an IAM user and work across regions. Approved Senders and suppression lists are regional resources. When expanding to a new region:

1. Create Approved Senders in the new region.
2. Verify SPF/DKIM for the domain and region.
3. Use that region's SMTP endpoint.
4. Consider creating a separate SMTP user per region to isolate credentials/permissions.
5. Monitor suppression lists and delivery logs in the corresponding region.

Never send through the Phoenix endpoint using an Approved Sender created only in Singapore.

### 7.4. SMTP Endpoints and TLS

SMTP endpoints follow a regional format, for example:

~~~text
smtp.email.ap-singapore-1.oci.oraclecloud.com
~~~

OCI supports SMTP ports 25, 587, and 465. Port 465 uses TLS from the start of the connection (implicit TLS). Port 587 typically uses STARTTLS; port 25 may also be supported depending on network path. Prefer TLS and use the endpoint/port shown on your region's Configuration page.

Port 465 configuration example:

~~~yaml
spring:
  mail:
    host: smtp.email.ap-singapore-1.oci.oraclecloud.com
    port: 465
    username: SMTP_USERNAME_FROM_SECRET
    password: SMTP_PASSWORD_FROM_SECRET
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          starttls:
            enable: false
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

If choosing port 587, enable STARTTLS and require TLS:

~~~yaml
spring:
  mail:
    port: 587
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: false
          starttls:
            enable: true
            required: true
~~~

Never enable implicit SSL and STARTTLS simultaneously. Never disable certificate/hostname verification to silence TLS errors; inspect JavaMail version, JDK truststore, endpoint, and TLS settings instead.

## 8. Spring Cloud Oracle Email Delivery Starter

### 8.1. Dependency

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-email</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-email")
}
~~~

The starter provides Spring Mail integration. Configure SMTP using standard Spring Boot properties pointing to the OCI Email Delivery endpoint and credentials.

### 8.2. `MailSender`

The starter auto-configures `MailSender` with the qualifier `ociMailSender`. Example:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class ContractEmailService {

    private final MailSender mailSender;

    public ContractEmailService(
            @Qualifier("ociMailSender") MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendStatus(
            String from,
            String recipient,
            String subject,
            String text) {

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(text);

        mailSender.send(message);
    }
}
~~~

`From` must be an Approved Sender in the region. `Recipient` must be validated against business rules and consent/policy. Never accept arbitrary `From` addresses from request bodies to avoid open relays or spoofing.

### 8.3. `JavaMailSender` for HTML and Attachments

The starter also provides `JavaMailSender` with the qualifier `ociJavaMailSender`. Use it when MIME multipart, HTML, or attachments are needed:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RichEmailService {

    private final JavaMailSender mailSender;

    public RichEmailService(
            @Qualifier("ociJavaMailSender") JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendHtml(
            String from,
            String recipient,
            String subject,
            String html) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(html, true);

        mailSender.send(message);
    }

    public void sendAttachment(
            String from,
            String recipient,
            String subject,
            String text,
            byte[] fileBytes,
            String safeFileName) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(text, false);
        helper.addAttachment(
                safeFileName,
                new ByteArrayResource(fileBytes),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

The attachment example uses `byte[]`, so it fits only small files. OCI Email Delivery caps total message size after Base64 encoding and headers; the current limit is 2 MB. For larger files, store them in Object Storage and send a controlled time-limited link instead of attaching.

### 8.4. Email Templates

Never concatenate HTML from arbitrary input. Use a template engine, escape variables, and validate links. Transactional emails should include:

- A clear subject.
- An approved `From`.
- A verified recipient.
- A plain-text fallback when sending HTML.
- A non-sensitive request/correlation ID.
- Application links gated by authentication.
- Support details or unsubscribe links where applicable.
- Content that does not expose sensitive contracts or private data if misdirected.

### 8.5. Email Is Not Part of a Database Transaction

Never call SMTP while holding a database transaction open. If the database commits while SMTP times out, the application does not know whether the email was received. If SMTP succeeds while the transaction rolls back, the recipient receives a notification for a change that never occurred.

Use a transactional outbox:

1. Inside the business transaction, update data and write a notification outbox row.
2. A worker reads the outbox after commit.
3. The worker sends the email.
4. Persist status `ACCEPTED`/`FAILED`/`RETRYING` along with the message ID if available.
5. Retry transient errors with backoff.
6. Route permanent failures to manual intervention.

SMTP does not provide exactly-once delivery at the application layer. Retrying after a timeout can produce duplicates. Use notification IDs, idempotency, and carefully worded templates to minimize duplicate impact.

## 9. Suppression, Bounces, and Deliverability

### 9.1. Suppression List

OCI Email Delivery maintains a regional suppression list. Addresses generating hard bounces or complaints may be added to suppressions to protect sender reputation. Do not repeatedly retry sending to suppressed addresses.

Workflow:

- Check suppressions before bulk campaigns if needed.
- Process bounces/complaints from logs or events.
- Update email delivery state in the application database.
- Restrict suppression removal strictly to authorized roles.
- Never auto-delete suppressions to force retries.
- Check the suppression list in the exact sending region.

### 9.2. Important SMTP Responses

| SMTP Code | Common Meaning | Resolution |
| --- | --- | --- |
| `421` | Timeout, too many connections, or auth failures | Backoff, verify credentials and concurrency |
| `455` | Exceeded send rate/daily quota | Queue, throttle, request quota increase if justified |
| `535` | Invalid credentials or unauthorized sender | Check SMTP credentials, IAM, and Approved Sender |
| `553` | Invalid email address | Validate recipient |
| `554` | Malformed message format | Inspect MIME/headers/content |
| `552` | Message exceeds byte limit | Shrink attachment or send a link |

A successful SMTP response only confirms the service accepted the message for processing. Inspect Email Delivery logs and delivery status to determine final outcomes.

### 9.3. Sender Reputation

- Use a dedicated domain and verify SPF/DKIM.
- Configure DMARC per domain policy.
- Never send to purchased lists or unconsented addresses.
- Handle hard bounces and complaints promptly.
- Avoid rotating across many unrelated `From` domains.
- Warm up volume gradually on new senders.
- Monitor quotas and suppressions.
- Never retry hard bounces or suppressed addresses.

## 10. OCI Functions and Invocation Models

### 10.1. Function Applications and Functions

OCI Functions is a Functions-as-a-Service platform. A Function is deployed inside a Functions Application, runs on OCI Functions infrastructure, and exposes an invoke endpoint.

Spring Boot can invoke functions to:

- Generate thumbnails after a document upload.
- Scan files or validate formats.
- Render PDFs/reports.
- Transform data.
- Execute independent tasks without tying up main API HTTP threads.
- Run event-driven or scheduled processing.

A Function is not a local Spring method. Invocations go through the OCI API, requiring identity/signatures, a function OCID, an endpoint, and IAM permissions.

### 10.2. Sync vs. Detached

| Invocation Type | Behavior | HTTP Response | When to Use |
| --- | --- | --- | --- |
| Sync | Caller waits for the function to finish | 200 on success | Fast results needed immediately |
| Detached | Caller returns once the function starts; function keeps running | 202 | Long-running tasks or background processing |

Sync invocations depend on client read timeouts and function execution timeouts. Detached invocations use a separate `detachedModeTimeoutInSeconds`, configurable from 5 seconds to 3600 seconds per current documentation.

Detached invocations can configure success destinations and failure destinations to Notifications, Queue, or Streaming. OCI Functions then emits an invocation record to the configured destination upon completion.

### 10.3. Function Endpoints

Every function has an invoke endpoint. With the OCI SDK, clients take the base endpoint, for example:

~~~text
https://<function-endpoint-id>.<region>.functions.oci.oraclecloud.com
~~~

Do not pass the full `/20181201/functions/<function-ocid>/actions/invoke` path into an SDK client expecting the base endpoint. The SDK appends the function OCID and resource path automatically.

If sending signed HTTP requests manually, requests must carry OCI request signatures and the compartment OCID. Using the OCI SDK/Spring starter avoids writing a custom request signer.

The Fn Project CLI is handy for terminal development and testing, but Oracle does not recommend it as a production invocation mechanism. In production Spring Boot applications, use the OCI SDK/Spring starter or managed OCI CLI/APIs with proper identities and policies.

## 11. Spring Cloud Oracle Functions Starter

### 11.1. Dependency

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-function</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-function")
}
~~~

The starter auto-configures a `Function` bean to call OCI Functions. `spring.cloud.oci.function.enabled` controls enabling the module; defaults to `true`.

### 11.2. Authentication and Region

Example for a workload running on Compute:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      function:
        enabled: true
~~~

Local development can use a `FILE` profile. Production should use instance principal or OKE workload identity matching the runtime. Never bake API private keys into images just to invoke functions.

### 11.3. Sync Invocation from Spring Boot

The Spring Cloud Oracle `Function` bean provides `invokeFunction`, taking function OCID, base endpoint, invocation mode, and request body `InputStream`.

~~~java
import com.oracle.bmc.functions.requests.InvokeFunctionRequest;
import com.oracle.bmc.functions.responses.InvokeFunctionResponse;
import com.oracle.cloud.spring.function.Function;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailFunctionInvoker {

    private final Function function;

    public ThumbnailFunctionInvoker(Function function) {
        this.function = function;
    }

    public InvokeFunctionResponse createThumbnail(
            String functionOcid,
            String functionBaseEndpoint,
            byte[] jsonPayload) {

        try (InputStream body =
                     new ByteArrayInputStream(jsonPayload)) {

            return function.invokeFunction(
                    functionOcid,
                    functionBaseEndpoint,
                    InvokeFunctionRequest.FnInvokeType.Sync,
                    body);
        } catch (java.io.IOException exception) {
            throw new java.io.UncheckedIOException(exception);
        }
    }
}
~~~

Payloads should be JSON containing schema version, event ID, document ID, object key reference, verified tenant reference, and trace/correlation IDs. Avoid passing passwords, wallets, SMTP credentials, or large file payloads in the invocation body when an object reference suffices.

### 11.4. Detached Invocation

For long-running tasks, use Detached mode:

~~~java
public InvokeFunctionResponse startBackgroundScan(
        String functionOcid,
        String functionBaseEndpoint,
        byte[] jsonPayload) {

    try (InputStream body =
                 new ByteArrayInputStream(jsonPayload)) {

        return function.invokeFunction(
                functionOcid,
                functionBaseEndpoint,
                InvokeFunctionRequest.FnInvokeType.Detached,
                body);
    } catch (java.io.IOException exception) {
        throw new java.io.UncheckedIOException(exception);
    }
}
~~~

Upon receiving 202, persist the invocation/request reference and `PENDING` status. The final outcome must be sent by the function to a Queue/Streaming/Notifications destination or written to a datastore monitored by the application. Never mark a document as `SCANNED` merely because the invocation returned 202.

### 11.5. IAM Policy Scoped to Specific Function Invocations

The `fn-invocation` resource type grants permission to invoke functions. Example granting `document-service`'s dynamic group permission to invoke a single function:

~~~text
Allow dynamic-group DocumentService to use fn-invocation in compartment AppFunctions
where target.function.id = '<FUNCTION_OCID>'
~~~

Or scoped by application:

~~~text
Allow dynamic-group DocumentService to use fn-invocation in compartment AppFunctions
where target.app.id = '<FUNCTION_APPLICATION_OCID>'
~~~

Never grant `manage functions-family` to runtime workloads that only invoke functions. `manage functions-family` encompasses both management and invocation rights. Separate deployers from invokers:

~~~text
Allow group FunctionDeployers to manage fn-app in compartment AppFunctions
Allow group FunctionDeployers to manage fn-function in compartment AppFunctions
~~~

These management statements alone do not grant invoke permission. Grant `fn-invocation` separately to principals that actually call functions.

### 11.6. Private Subnets Do Not Replace IAM

Placing a Function Application in a private subnet does not automatically block public internet access to its invoke endpoint. Control who can invoke via IAM policies and conditions. Network placement/routing and IAM authorization are two separate layers.

### 11.7. Detached Success/Failure Destinations

If a function runs detached and sends invocation records to Queue, Notifications, or Streaming, OCI Functions needs permission to write to that destination. Sample policy for Queue:

~~~text
Allow any-user to use queues in compartment Processing
where all {
  request.principal.type = 'fnapp',
  target.queue.id = '<QUEUE_OCID>',
  request.principal.compartment.id = '<FUNCTION_APP_COMPARTMENT_OCID>'
}
~~~

Similar policies apply to ONS topics or streams using the corresponding resource type and target ID. Grant write permission strictly to the exact destination, rather than opening the entire compartment unnecessarily.

## 12. Designing Workflows Combining Logging, Email, and Functions

### 12.1. `document-service` Flow

Example after a user uploads a contract:

1. API authenticates user and tenant.
2. Saves metadata/document state in the database.
3. Saves the object in Object Storage.
4. Writes an outbox event inside the same database transaction.
5. Worker emits logs/metrics and invokes a thumbnail or scan function.
6. Function returns a result or emits a detached invocation record to Queue.
7. Worker updates processing state.
8. Notification worker sends an email to the user.
9. Steps are logged with the same trace ID and event ID.

~~~mermaid
sequenceDiagram
    participant API as Spring Boot API
    participant DB as Autonomous Database
    participant OS as Object Storage
    participant Q as Queue / Outbox Worker
    participant FN as OCI Functions
    participant LOG as OCI Logging
    participant MAIL as Email Delivery

    API->>OS: Upload contract
    API->>DB: Save document + outbox
    DB-->>API: Commit
    API->>LOG: Log accepted event
    Q->>FN: Invoke scan/thumbnail
    FN-->>Q: Result or detached status
    Q->>DB: Update document state
    Q->>MAIL: Send status email
    MAIL-->>Q: SMTP accepted/rejected
    Q->>LOG: Log outcome and correlation ID
~~~

### 12.2. Correlation and Idempotency

Use identifiers:

- `requestId`: single HTTP request.
- `traceId`: distributed trace across services.
- `eventId`: unique business event.
- `functionInvocationId`/`requestId`: invocation reference.
- `notificationId`: a specific email notification.

Never use email addresses or document contents as correlation IDs. When retrying function calls or emails, reuse the same event/notification ID to deduplicate in the database and avoid duplicate business side effects.

### 12.3. Outbox for Email and Function Invocations

Never call Email Delivery or Functions before the business transaction commits when the operation relies on newly written data. An outbox guarantees the intent to notify/invoke is persisted atomically with the transaction.

Workers can retry on timeouts. However, a timeout does not prove the request was never received. Before retrying, use idempotency keys or check event status. Functions must be idempotent because callers may resend the same event.

### 12.4. Error Classification and Retries

| Error | Logging | Email | Functions |
| --- | --- | --- | --- |
| `401`/`403` | Check principal/policy; do not retry indefinitely | Check SMTP credentials/approved sender | Check `fn-invocation` permission |
| `429`/quota | Reduce ingestion or batch | Queue and throttle per quota | Backoff when service throttles |
| Timeout | Check sink; avoid losing critical events | SMTP may have accepted; check delivery logs before retry | Invocation may have started; use idempotency |
| `5xx`/transient | Bounded retry | Retry with backoff/jitter | Bounded retry; check SDK policy |
| Invalid payload | Fix schema/encoding | Fix MIME/headers/recipient | Fix function input contract |
| Permanent reject | Do not retry bad payloads | Process bounce/suppression | Route event to failure path/DLQ |

Never retry `401`/`403` like network errors. Retry with exponential backoff and jitter; cap retry attempts, record attempt counts, and route persistent failures to a DLQ/manual review.

## 13. Security, Secrets, and Sensitive Data

### 13.1. Separating Credentials per Service

| Credential / Identity | Used For | Where Stored |
| --- | --- | --- |
| OCI workload identity | Logging API and Functions invoke | OCI runtime identity; no long-lived private keys stored |
| SMTP username/password | Email Delivery SMTP | OCI Vault/secret manager |
| Log OCID | Target log selection | Application configuration |
| Function OCID/base endpoint | Target function selection | Application configuration |
| Approved Sender | `From` identity | OCI Email Delivery configuration |

Never use a single admin IAM user to emit logs, send emails, and invoke functions. Separate principals and permissions by service.

### 13.2. Email Security

- SMTP credentials should only permit sending for required senders.
- Never log SMTP AUTH usernames/passwords.
- Use TLS and verify certificates.
- Approved Senders must belong to organization-controlled domains.
- Never accept `From` from end users.
- Avoid putting secrets or PII into subjects/bodies unnecessarily.
- Limit attachments and use time-limited links for large files.
- Process suppression lists so hard-bounced/complained addresses are never retried.

### 13.3. Function Security

- Grant `fn-invocation` strictly to the exact function/application.
- Validate payloads and schema versions.
- Never trust tenant IDs or object keys without verifying permissions at caller/function boundaries.
- Use resource principal/workload identity inside functions to access OCI resources.
- Keep function runtime policies separate from caller policies.
- Never write sensitive payloads into Function logs.
- Set appropriate timeouts/memory/concurrency and restrict egress where needed.

### 13.4. Logging Security

- Separate writers from readers.
- Use dedicated log groups for sensitive data.
- Redact secrets before calling `LogService`.
- Restrict search/export permissions.
- Configure retention and archiving according to data classification.
- Audit changes to log destinations/retention.
- Never treat custom application logs as immutable audit evidence without additional controls.

## 14. Observability and Operations

### 14.1. Logging Metrics

Monitor:

- Bytes ingested.
- Log event counts and send errors.
- Latency from event emission to searchability.
- Log search success.
- Queue backlog if using async logging.
- Archive/export failures.
- Retention and storage usage.

### 14.2. Email Metrics

Monitor:

- Emails accepted/sent per region.
- SMTP `4xx`/`5xx` counts.
- Bounces and complaints.
- Suppression counts.
- Daily quota and send rate.
- TLS/auth failures.
- Send duration and delivery status.

Never record full email addresses in metric labels. Use domains or hashed/pseudonymous recipient IDs when breakdown is needed.

### 14.3. Functions Metrics

Monitor:

- Invocation counts per function.
- Sync successes/errors/timeouts.
- Detached accepted/completed/failed counts.
- Execution duration.
- Cold starts and resource utilization.
- Retry counts and duplicate events.
- Success/failure destination delivery.
- Queue backlog or event age.

### 14.4. Runbooks and Lifecycles

Clearly assign owners for:

- Creating log groups/log OCIDs and retention.
- Updating IAM policies.
- Rotating SMTP credentials.
- Updating Approved Senders/SPF/DKIM.
- Onboarding new email sending regions.
- Deploying functions and updating OCIDs/endpoints.
- Tuning detached timeouts/destinations.
- Handling bounces/suppressions and DLQs.

Never store log OCIDs/Function OCIDs/SMTP usernames alongside raw secrets in public operational docs.

## 15. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `LogService` `404`/NotFound | Wrong log OCID or log not created | Check `logId`, region, and log group |
| `LogService` `403` | Principal lacks `use log-content` or wrong compartment | Check workload identity and policy |
| Log sent successfully yet not visible | Wrong log destination, ingestion delay, or query filter | Check log OCID, timestamp, and Logging Search |
| Log lacks JSON fields | Sent text is not valid JSON | Check serializer and UTF-8 encoding |
| Logging cost spike | Excessive debug volume or duplicate events | Lower log level, sample, and batch |
| SMTP `535` | Wrong SMTP credentials or unauthorized sender | Rotate credentials, check IAM and Approved Sender |
| SMTP `535` address not authorized | `From` not approved or missing policy | Check regional sender and `use approved-senders` |
| SMTP `421` | Timeout, too many connections/auth failures | Reduce concurrency, fix credentials, backoff |
| SMTP `455` | Exceeded send quota | Throttle, queue, and check current limits |
| SMTP `552` | Message exceeds size limit | Shrink attachment or send a link |
| Email accepted yet missing from inbox | Bounce, suppression, SPF/DKIM/DMARC, or recipient policy | Inspect Email Delivery logs and suppressions |
| DKIM inactive | Wrong CNAME selector/zone or DNS not propagated | Verify DNS record name/value |
| Email sender valid in region A yet rejected in B | Approved Sender is regional | Create sender in region B |
| Function `404` | Wrong function OCID or endpoint | Use function base endpoint for the exact region |
| Function `401`/`403` | Request signature/identity or missing `fn-invocation` policy | Check OCI auth and IAM |
| Function Sync timeout | Long-running function or low client read timeout | Switch to Detached or adjust timeouts |
| Detached returns 202 yet no outcome | Missing destination config or function didn't publish state | Check success/failure destinations and function logs |
| Function invokes yet storage access fails | Function runtime lacks resource principal policy | Grant permissions to the Function's principal |
| Duplicate function execution | Caller retried after timeout or event redelivery | Use event ID/idempotency and deduplicate |
| Function invoke endpoint called from internet | Private subnet does not block public invoke endpoint | Restrict IAM `fn-invocation` and policy conditions |

## 16. Integration Testing

### 16.1. Logging Tests

- Send a structured JSON custom log and verify it appears under the exact log OCID.
- Verify the runtime principal can push logs but cannot delete the log group.
- Verify `LogReader` can read contents but cannot alter configuration.
- Confirm log payloads contain no tokens, passwords, or PII.
- Verify retention and archiving pipelines.
- Verify the application handles Logging API unavailability without losing business transactions.

### 16.2. Email Tests

- Verify SMTP credentials and successful TLS handshake.
- Verify Approved Sender matches region/compartment.
- Verify SPF/DKIM checks pass.
- Send plain text and HTML emails.
- Send an attachment under the size limit.
- Send to a suppressed recipient and confirm no infinite retries occur.
- Test invalid credentials, unapproved senders, and quota exceeded responses.
- Test SMTP timeout after server acceptance to validate duplicate protection.

### 16.3. Functions Tests

- Invoke a Sync function and verify the response.
- Invoke Detached and verify the caller receives accepted status.
- Verify the function accepts invocations only from authorized principals.
- Test wrong function OCID/endpoint.
- Test invalid payloads and timeouts.
- Verify the function runtime reads Object Storage/Queue under its own identity.
- Test success/failure destinations.
- Send the same event ID twice and confirm function idempotency.

### 16.4. End-to-End Tests

Simulate a contract upload:

1. API saves metadata/object and outbox.
2. Worker emits a log event.
3. Worker invokes the scan function.
4. Function returns a result or detached result.
5. Worker updates document state.
6. Email worker sends a notification.
7. Inspect Logging Search, Email Delivery logs, and Function logs.
8. Trace correlation/event ID end-to-end.
9. Verify retries do not produce duplicate emails or side effects.
10. Verify out-of-scope principals are denied.

Never run bulk email tests or resource-heavy function invocations against production. Use dedicated test compartments, logs, senders, and test functions.

## 17. Comprehensive Practice Exercise

You are tasked with deploying `document-service` on OCI. The application must send centralized logs, email customers when contracts are processed, and invoke a function to generate thumbnails.

**Tasks:**

1. Create the `Observability` compartment and `app-runtime-logs` log group.
2. Create a custom log, record the log OCID, and configure the Logging starter.
3. Grant `log-content` permissions to the workload and read permissions to `LogReaders`.
4. Implement `StructuredOciLogPublisher` including trace ID and event ID.
5. Enable service logs for Functions/Object Storage needed for investigation.
6. Configure retention and Connector Hub archiving if retention beyond 180 days is needed.
7. Create an Email Domain for an organization-owned domain.
8. Configure SPF/DKIM and verify DNS.
9. Create an SMTP-only IAM user, SMTP credentials, and an Approved Sender in the sending region.
10. Configure the Email Delivery starter, `MailSender`, and `JavaMailSender`.
11. Build a transactional outbox for email notifications.
12. Create an OCI Functions Application and thumbnail generation function.
13. Grant `fn-invocation` scoped strictly to the function OCID.
14. Integrate the `Function` bean and test Sync/Detached modes.
15. Configure detached success/failure destinations if needed.
16. Write unit/integration/negative tests for IAM, logging, SMTP, and function invocation.
17. Build dashboards/alerts and runbooks for bounces, quotas, function timeouts, and log ingestion failures.

**Self-Assessment Questions:**

- How do OCI Audit Logs, Service Logs, and Custom Logs differ?
- Why doesn't the Spring Cloud Logging starter automatically ship all SLF4J events?
- How do log groups help control permissions?
- Why does Logging's 180-day maximum retention require separate archiving for longer requirements?
- Which IAM permission does a log-writing principal need?
- How do SMTP credentials differ from OCI API signing keys?
- Why must Approved Senders be created separately in each region?
- What problems do SPF and DKIM solve?
- Why should SMTP credentials belong to a dedicated IAM user?
- How do ports 465 and 587 differ in TLS setup?
- Why doesn't SMTP success guarantee inbox delivery?
- What role does the suppression list play?
- For which use cases do `MailSender` and `JavaMailSender` differ?
- Why should emails be sent via an outbox after transaction commit?
- How do Sync and Detached function invocations differ?
- Why is a Detached 202 not a successful business outcome?
- Why does the OCI SDK expect the base invoke endpoint rather than the full path?
- How does `fn-invocation` differ from `manage functions-family`?
- Why doesn't a private subnet replace IAM policies for invoke endpoints?
- How do you handle duplicates when a caller retries after a timeout?
- Why does a function runtime need a separate policy from its caller?
- Which fields must never be put into logs or emails?

**Guided Answers:** Audit logs capture OCI Audit API calls; service logs are emitted by OCI services; custom logs are pushed by apps/agents; the starter only provides the explicit `LogService` API; log groups act as IAM boundaries for logs; search retention maxes at 180 days so use Connector Hub archiving; writers need `use log-content`; SMTP credentials are Oracle-generated SMTP username/password pairs distinct from API signing keys; Approved Senders and suppression lists are regional; SPF verifies sending infrastructure while DKIM cryptographically signs the domain; SMTP-only users shrink blast radius; port 465 uses implicit TLS while 587 uses STARTTLS; SMTP acceptance does not guarantee recipient delivery; suppressions prevent retrying hard-bounced/complained addresses; `MailSender` fits plain text while `JavaMailSender` supports MIME/HTML/attachments; outbox prevents sending mail before commit; Sync waits for output while Detached returns 202; 202 only indicates execution started; the SDK takes the base endpoint and appends paths; `fn-invocation` grants only invoke rights while `manage functions-family` is broader; private subnets do not close public invoke endpoints; use idempotency/event IDs; function runtimes have their own principals; logs/emails must exclude tokens, secrets, or sensitive payloads.

## 18. Official References

### Spring Cloud Oracle 2.0.4

- [OCI Logging Integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/logging/): dependency, `LogService` bean, `putLog`, and `logId` property.
- [OCI Email Delivery Integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/email-delivery/): `MailSender`, `JavaMailSender`, SMTP configuration, and samples.
- [OCI Functions Integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/functions/): `Function` bean, `invokeFunction`, and starter configuration.
- [OCI Core](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/): OCI authentication, region, and compartment configuration.
- [Spring Cloud Oracle Release Notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/): versions and compatibility.

### OCI Logging

- [Logging Overview](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm): Audit/Service/Custom Logs, log groups, search, Connector Hub, and encryption.
- [Logs and Log Groups](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/managinglogs.htm): log groups, IAM boundaries, and policies.
- [Ingesting Custom Logs](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/using_the_api_customlogs.htm): `PutLogs` Logging Ingestion API.
- [Getting a Log's Details](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/get-logging-log.htm): 30-day retention increments and 180-day maximum.
- [Details for Logging IAM Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/loggingpolicyreference.htm): `log-content` and `log-groups` permissions.

### OCI Email Delivery

- [Email Delivery Getting Started](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted.htm): sequence for configuring domain, SPF, DKIM, sender, and SMTP.
- [Overview of Email Delivery](https://docs.oracle.com/en-us/iaas/Content/Email/Concepts/overview.htm): regional assets, SMTP credentials, and endpoints.
- [Creating an Approved Sender](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted_topic-Create_an_approved_sender.htm): senders by compartment/region.
- [Managing Approved Senders](https://docs.oracle.com/en-us/iaas/Content/Email/Tasks/managingapprovedsenders.htm): domain ownership and `From` alignment.
- [Configuring SPF](https://docs.oracle.com/en-us/iaas/Content/Email/Tasks/configurespf.htm): TXT records per region.
- [Configuring DKIM](https://docs.oracle.com/en-us/iaas/Content/Email/Tasks/configure-dkim-using-the-console.htm): DKIM CNAME, key rotation, and verification.
- [Configuring SMTP Connection](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted_topic-Configure_the_SMTP_connection.htm): endpoints, ports, and TLS.
- [Working with SMTP Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/access/working-with-smtp-credentials.htm): SMTP credential lifecycle and limits.
- [Securing Email Delivery](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/email_security.htm): SMTP-only users, IAM, and secret protection.
- [Troubleshooting Email Delivery](https://docs.oracle.com/en-us/iaas/Content/Email/Concepts/troubleshooting.htm): SMTP status codes, quotas, suppressions, and TLS.
- [Email Delivery IAM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/emailpolicyreference.htm): `approved-senders` and `suppressions` permissions.

### OCI Functions

- [Invoking Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsinvokingfunctions.htm): signed invocations, SDK, Sync/Detached, timeouts, and result destinations.
- [Controlling Access to Invoke and Manage Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsrestrictinguseraccess.htm): `fn-invocation` policies and scope.
- [Functions IAM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/functionspolicyreference.htm): `fn-app`, `fn-function`, and `fn-invocation` permissions.
- [OCI Java SDK FunctionsInvoke](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/functions/FunctionsInvoke.html): invoke API, endpoints, and request handling.

**Key Takeaways:** The Logging starter ships custom logs via `LogService`; the Email Delivery starter uses Spring Mail with SMTP credentials and regional Approved Senders; the Functions starter uses OCI identities to invoke functions by OCID and base endpoint. Separate permissions and credentials per service, use outbox/idempotency for asynchronous flows, protect logs/emails from secrets and PII, and track final outcomes rather than relying solely on HTTP/SMTP acceptance.
