# Integrating Amazon SES with Spring's Email Sending Mechanism

## 1. Problem Statement and Learning Outcomes

An ordering application written in **Spring Boot** needs to send order confirmation emails, PDF receipts, and status update notifications. The application already has a business layer calling **MailSender** or **JavaMailSender**, but needs to send emails through AWS's managed service instead of operating its own SMTP server.

**Amazon Simple Email Service (Amazon SES)** is AWS's email sending service. **Spring Cloud AWS** can directly implement Spring's mail abstractions using the SES API. Alternatively, **Spring Boot Mail** can connect to the **SES SMTP endpoint** without changing code that uses JavaMailSender. These two paths use different authentication and communication mechanisms.

This lesson belongs to the **Amazon SNS and SES** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module's goal is hands-on Spring Boot integration with managed services from AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, covering identity/permissions, storage, messaging, data, secret management, testing, and evaluating differences between providers. Specifically, this lesson focuses on **how to integrate SES with Spring Mail**, from plain text to HTML/attachments, access permissions, and troubleshooting mail delivery.

After this lesson, learners will:

1. Choose appropriately between **SES API via Spring Cloud AWS** and **SES SMTP via Spring Boot Mail**.
2. Configure SES identity, region, sandbox/production access, and appropriate sending permissions.
3. Send plain-text emails with **MailSender**, and HTML emails or attachments with **JavaMailSender**.
4. Distinguish **IAM role/AWS SDK credentials** from **SES SMTP username/password**, keeping secrets out of the repository.
5. Test email sending, observe bounces/complaints, and understand why a successful send call does not guarantee delivery into the recipient's inbox.

## 2. From Spring Mail to Amazon SES

~~~mermaid
flowchart LR
    A["Spring Boot<br/>Order Email Service"] --> B["Spring Mail<br/>MailSender / JavaMailSender"]
    B -->|"Option A: SES API"| C["Spring Cloud AWS<br/>SES starter"]
    B -->|"Option B: SMTP"| D["Spring Boot Mail<br/>JavaMailSenderImpl"]
    C --> E(("Amazon SES"))
    D --> E
    E --> F["Recipient's<br/>email provider"]
    E -->|"Delivery / Bounce / Complaint"| G["SES event destination<br/>SNS / EventBridge / CloudWatch"]
~~~

**Spring Mail** abstracts email sending in Java rather than forcing business code to build HTTP or SMTP requests manually. Two common abstractions:

| Spring Abstraction | Mail Format | Message Type | Example |
| --- | --- | --- | --- |
| **MailSender** | Plain text | **SimpleMailMessage** | OTP, short notifications |
| **JavaMailSender** (extends MailSender) | MIME: text, HTML, multipart, attachments | **MimeMessage**, **MimeMessageHelper** | HTML and PDF receipts |
| AWS SDK **SesClient/SesV2Client** | Direct AWS SES request | AWS SDK request | Need SES-specific operations or responses |

In **Spring Cloud AWS 3.x**, the **spring-cloud-aws-starter-ses** starter creates a sender backed by the **SES API**. When only sending **SimpleMailMessage**, it can provide **MailSender**. When **Jakarta Mail API + implementation** are on the classpath, Spring Cloud AWS can provide a MIME-capable **JavaMailSender**; the underlying send operation still goes over the **SES API**, with no need to configure an SMTP host/password.

With **Spring Boot starter-mail**, a **JavaMailSenderImpl** sends mail over SMTP. To send via SES, configure SES's SMTP host, TLS port, and a region-specific pair of **SES SMTP credentials**.

### 2.1. Comparing the Two Integration Approaches

| Criterion | **Spring Cloud AWS SES (API)** | **Spring Boot Mail (SMTP)** |
| --- | --- | --- |
| Primary dependency | **spring-cloud-aws-starter-ses** | **spring-boot-starter-mail** |
| Transport | AWS SDK **SesClient**, calling SES API | SMTP to SES regional endpoint |
| Authentication | AWS credentials provider chain, preferring workload **IAM role** | SES **SMTP username/password** |
| Static secret stored in AWS app | Not needed when workload uses an IAM role | Must protect SMTP password when choosing password-based SMTP |
| Business Spring API | **MailSender/JavaMailSender** | **MailSender/JavaMailSender** |
| Benefits | Seamless IAM role integration, avoids extra SMTP handshakes | Easy switch from existing SMTP-configured JavaMailSender systems |
| Key difference | HTML/MIME uses SES raw email operation | Must manage connections, TLS, timeouts, and SMTP authentication |

**Rule of thumb:** for Spring Boot workloads running on AWS that can use an IAM role, **Spring Cloud AWS SES API** is usually a better fit. For systems standardized on SMTP or needing to swap SMTP providers via configuration, **SES SMTP** is also a valid choice. Avoid unknowingly enabling both sender auto-configurations at once; explicitly decide which **MailSender/JavaMailSender** bean will be injected.

## 3. Preparing SES Before Writing Code

### 3.1. Choosing a Region and Verifying Sender Identity

SES stores **verified identities** per **AWS Region**. Before sending, open the Amazon SES Console in the target region (e.g., **ap-southeast-1**) and verify an email address or sending domain.

- **Email identity:** suitable for quick testing, e.g., **no-reply@example.com** once the mailbox owner confirms.
- **Domain identity:** suitable for production, e.g., **example.com**, typically requiring DNS domain ownership verification and DKIM configuration.
- **SPF**, **DKIM**, and **DMARC:** should be reviewed to authenticate sender origin and improve deliverability; manage DNS records according to SES documentation and domain policy.
- **From address:** must be authorized to send based on a verified identity or an appropriate sending authorization mechanism. Examples use **no-reply@example.com** on a verified domain.

Addresses/domains in examples are **illustrative data**, not addresses usable for real emails without verification. Across different regions, do not assume an identity's verification status carries over from the original region.

### 3.2. SES Sandbox and Production Access

New SES accounts typically start in a **per-region sandbox**. Inside the sandbox, you can only send to **verified addresses/domains** or the **SES mailbox simulator**. Under AWS-published sandbox limits, defaults are up to **200 emails/24 hours** and **1 email/second**; actual sending quotas vary by account/region.

Once **production access** is approved, you can send to unverified recipients, though the **From identity must still be verified**. Production access does not guarantee inbox placement; reputation, suppression lists, spam filtering, bounces/complaints, and quotas continue to matter.

Check SES status via AWS CLI:

~~~bash
aws sesv2 get-account \
  --region ap-southeast-1 \
  --query '{Production:ProductionAccessEnabled,Quota:SendQuota}'
~~~

Check a configured identity:

~~~bash
aws sesv2 get-email-identity \
  --email-identity example.com \
  --region ap-southeast-1
~~~

Select the right region and IAM read permissions for configuration checks. For testing purposes, prefer the **SES mailbox simulator** and avoid sending bulk test emails to real users.

### 3.3. SES, SNS, and SQS Serve Three Distinct Roles

**SES** sends the actual emails. **SNS** distributes events to multiple subscribers. **SQS** holds tasks so workers send emails asynchronously.

~~~mermaid
flowchart LR
    O["Order Service"] -->|"Publish ORDER_CREATED"| N(("SNS topic"))
    N --> Q["SQS<br/>email-jobs"]
    Q --> W["Spring Boot<br/>Email Worker"]
    W -->|"MailSender / SES"| S(("Amazon SES"))
    S --> R["Recipient"]
    S -->|"Bounce / Complaint"| V["SNS/EventBridge<br/>feedback handler"]
~~~

An **SNS email subscription** can send topic notifications to a confirmed email endpoint, but it does not fully replace **SES** for transactional email workflows with custom bodies, templates, receipts, and identity management.

## 4. Option A — Spring Cloud AWS SES API with MailSender

### 4.1. Dependencies

Example **Gradle Groovy DSL**, using Spring Boot and **Spring Cloud AWS 3.x**:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-ses")
}
~~~

**springCloudAwsVersion** is the BOM version declared by the project per the Spring Cloud AWS and Spring Boot compatibility table. With Maven, import the **spring-cloud-aws-dependencies** BOM in **dependencyManagement**, then add the SES starter dependency. The Java examples below use **Spring Boot 3 / Jakarta Mail**, so do not copy legacy **javax.mail** imports from Spring Boot 2 applications directly.

### 4.2. Region and From Address

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
      ses:
        region: ${SES_REGION:ap-southeast-1}

app:
  email:
    from: ${MAIL_FROM}
~~~

- **spring.cloud.aws.ses.region** selects the **SesClient** region, which can differ from where the application runs.
- **app.email.from** is an application-defined property mapping to a verified sender in SES.
- To apply a **configuration set** to all emails from the sender, Spring Cloud AWS supports **spring.cloud.aws.ses.configuration-set-name**, configured once that set exists.
- Advanced properties such as **spring.cloud.aws.ses.source-arn** and **spring.cloud.aws.ses.from-arn** are mainly for **SES sending authorization**; they are not required by default when sending with the account's own identity.

When running on AWS, configure the workload's IAM role (ECS task role, EC2 instance profile, EKS workload identity). The AWS SDK uses the **credentials provider chain**. On development machines, use an AWS CLI profile and verify the region; never put access keys into source code.

### 4.3. Sending a SimpleMailMessage

~~~java
package demo.mail;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class OrderTextMailService {
    private final MailSender mailSender;
    private final String fromAddress;

    public OrderTextMailService(
            MailSender mailSender,
            @Value("${app.email.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendConfirmation(String recipient, String orderId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(recipient);
        message.setSubject("Order confirmation " + orderId);
        message.setText(
                "Order " + orderId + " has been received.\n"
                        + "Thank you for using our service."
        );

        mailSender.send(message);
    }
}
~~~

**Key points:**

1. Business code only depends on **org.springframework.mail.MailSender**.
2. **SimpleMailMessage** specifies from/to/subject/text; there is no need to instantiate an AWS HTTP client or SMTP session object.
3. With the SES starter, Spring Cloud AWS invokes the SES API at the infrastructure layer when executing **send**.
4. **mailSender.send** can throw **MailException** if sending fails. The return does not provide proof that the recipient read the message.

This method fits plain-text emails without attachments. If you need HTML, inline images, or PDF files, use **JavaMailSender + MimeMessage**.

## 5. Sending HTML Emails and Attachments with JavaMailSender

### 5.1. Enabling Jakarta Mail for the SES Starter

In Spring Cloud AWS 3.x, add **Jakarta Mail API and implementation**. Example:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-ses")

    implementation("jakarta.mail:jakarta.mail-api")
    runtimeOnly("org.eclipse.angus:jakarta.mail")
    implementation("org.springframework:spring-web") // uses HtmlUtils in the example below
}
~~~

When the required components are on the classpath, the SES starter auto-configures a MIME-capable **JavaMailSender**. **The transport layer is still the SES API**, not SMTP. Spring Cloud AWS uses **ses:SendEmail** for plain text and **ses:SendRawEmail** for MIME/raw email depending on the send call. The **spring-web** dependency is only needed if the application does not already include it; the example below uses **HtmlUtils** to escape dynamic content inside HTML.

If dependency resolution requires explicit versions for Jakarta Mail/Angus, manage versions via the BOM matching your Spring Boot platform. Avoid mixing **javax.mail** (older generation) with **jakarta.mail** in the same Spring Boot 3 application.

### 5.2. Creating Mail with Text, HTML, and PDF Parts

~~~java
package demo.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

@Service
public class ReceiptMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public ReceiptMailService(
            JavaMailSender mailSender,
            @Value("${app.email.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendReceipt(
            String recipient, String orderId, byte[] receiptPdf)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Order receipt " + orderId);

        String safeOrderId = HtmlUtils.htmlEscape(orderId);
        String plainText = "Receipt for order " + orderId;
        String htmlText = "<p>Receipt for order <strong>"
                + safeOrderId + "</strong>.</p>";

        helper.setText(plainText, htmlText);
        helper.addAttachment(
                "receipt.pdf",
                new ByteArrayResource(receiptPdf),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

**Explanation:**

- **createMimeMessage** creates a MIME message; **MimeMessageHelper** populates header/body fields and attachments.
- **setText(plainText, htmlText)** produces both text/plain and text/html alternatives; the email client picks the suitable version.
- **ByteArrayResource** here holds pre-generated PDF bytes; in practice avoid loading huge files into memory and validate attachment types/sizes.
- **HtmlUtils.htmlEscape** is used when embedding dynamic content in HTML; with a template engine, rely on default escaping and avoid concatenating raw HTML from user input.
- **MessagingException** relates to MIME construction; **MailException** relates to send failures and is typically a runtime exception.
- Validate the **recipient** address at the application boundary, and never use untrusted input to inject arbitrary SMTP headers.

Although this code uses **JavaMailSender**, Spring Cloud AWS's implementation converts the MIME message into a raw email request to SES. **spring.mail.host** does not need to be configured for Option A.

## 6. IAM for the SES API: Sending Text and Raw Emails

When using the SES API starter, the application's IAM role must be permitted to send mail through a **verified identity**. Suppose identity **example.com** is verified in account **123456789012**, region **ap-southeast-1**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendOnlyFromVerifiedDomain",
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "arn:aws:ses:ap-southeast-1:123456789012:identity/example.com",
      "Condition": {
        "StringEquals": {
          "ses:FromAddress": "no-reply@example.com"
        }
      }
    }
  ]
}
~~~

**Meaning:**

- **ses:SendEmail** covers simple emails sent via SES by the starter.
- **ses:SendRawEmail** covers MIME/raw emails, required when sending HTML and attachments through the illustrated abstraction.
- **Resource** restricts access to the verified SES identity rather than granting **Resource: "*"** across all identities.
- **ses:FromAddress** further restricts which From address may be used.
- This policy attaches to the Spring Boot application's **runtime IAM role**, not necessarily to individual end users.

If using **sending authorization** to send on behalf of an identity-owning account, policies and conditions differ; check permissions of both the delegate sender and the identity owner. Default examples send using the account's own identity.

**Do not widen permissions to work around sending errors:** when plain text works but MIME fails, first check **ses:SendRawEmail**, verified identity status, region, and the From condition. If all operations are denied, inspect the credentials provider, IAM permissions, SCP/permission boundaries, and account policies.

## 7. Option B — Spring Boot JavaMailSender via SES SMTP

If the application already uses SMTP or needs to swap SMTP providers via configuration, replace Option A with **spring-boot-starter-mail** and point it to the SES SMTP endpoint.

### 7.1. Dependency and Configuration

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-mail")
}
~~~

Example **application.yml**:

~~~yaml
spring:
  mail:
    host: email-smtp.ap-southeast-1.amazonaws.com
    port: 587
    username: ${SES_SMTP_USERNAME}
    password: ${SES_SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000

app:
  email:
    from: ${MAIL_FROM}
~~~

The configuration above uses **SMTP port 587 + mandatory STARTTLS**. Port **465 (TLS Wrapper)** can be used with corresponding SSL/TLS settings, but do not mix SMTPS settings with STARTTLS. Port **25** is often restricted/throttled in some environments, especially EC2; prefer the ports recommended by SES.

**The SMTP endpoint and SMTP username/password are region-scoped.** For example, **email-smtp.ap-southeast-1.amazonaws.com** targets the chosen region; verify the AWS-supported endpoint when changing regions.

### 7.2. SMTP Credentials Differ from AWS Credentials

**SES SMTP credentials** are obtained from the SES Console (SMTP settings) or an appropriate SMTP credential management workflow. They are **not** the **AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY** pair used by the AWS SDK to call APIs; the SMTP password is not the same as an AWS secret access key. Some SES workflows support IAM-derived SMTP credentials and/or SES Mail Manager depending on setup.

| | **SES API** | **SES SMTP** |
| --- | --- | --- |
| Authentication | AWS SDK credentials provider chain, potentially a short-lived IAM role | SES-issued SMTP username/password |
| In Spring Boot | Spring Cloud AWS SES starter | Spring Boot starter-mail |
| Core configuration | **spring.cloud.aws.ses.region**, IAM role | **spring.mail.host**, port, username/password, and TLS |
| Secret management | No static access key needed when running with an IAM role | Store SMTP password in Secrets Manager or a managed secret store |
| Related permissions | **ses:SendEmail / ses:SendRawEmail** on the identity | SMTP credential/identity must be authorized by SES to send |

**Never put the SMTP password directly in Git**, example configs, or logs. In AWS environments, fetch the secret from **AWS Secrets Manager**/Parameter Store with least-privilege read access; in local dev use environment variables or a managed secret mechanism. If email fails with authentication error **535**, do not try to fix it by putting a regular AWS access key into **spring.mail.password**.

### 7.3. Does Business Code Need Changes?

When using SMTP, Spring Boot configures **JavaMailSenderImpl**, which implements both **JavaMailSender** and **MailSender**. Therefore, **OrderTextMailService** and **ReceiptMailService** from sections 4–5 can still be reused via constructor injection.

The changes sit mainly in **dependencies, transport configuration, and credential sources**. Avoid enabling both the SES starter and SMTP auto-configuration simultaneously without explicit bean qualification; having multiple MailSender beans can make injection by type ambiguous.

**Operational difference:** SMTP involves multiple protocol steps (connect, EHLO, STARTTLS, AUTH, MAIL FROM, RCPT TO, DATA). Consequently, you must configure timeouts and monitor sockets, firewalls, TLS, and SMTP response codes; direct SES API usage is usually simpler when the workload already has an IAM role.

## 8. Successful Send Status vs. Successful Delivery Status

A call to **mailSender.send(message)** returning without an exception means the request succeeded at the corresponding sending layer. With SES, this usually means SES **accepted the email for processing**, **not** that the recipient sees the message in their inbox.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant SES as Amazon SES
    participant Mailbox as Receiving mail server
    participant Events as Event destination

    App->>SES: Send email
    SES-->>App: Accepted / API success
    Note over App,SES: Does not prove delivery or read status
    SES->>Mailbox: Attempt delivery
    alt Accepted by mail server
        Mailbox-->>SES: Accepted
        SES-->>Events: Delivery event (if configured)
    else Rejected / bounced
        Mailbox-->>SES: Bounce / reject
        SES-->>Events: Bounce event (if configured)
    end
~~~

### 8.1. SES Event Publishing

Use an **SES configuration set** and **event destination** to track SES-supported events, such as:

| Event | Interpretation | Application Action |
| --- | --- | --- |
| **Send** | SES recorded the send attempt | Log send-layer acceptance |
| **Delivery** | Receiving server accepted the email | Update status to delivered; still does not mean the recipient read it |
| **Bounce** | Email was rejected by receiving server or undeliverable | Classify hard/soft bounce, adjust sending strategy |
| **Complaint** | Recipient marked as spam | Update preferences/suppression, review content and sending authorization |
| **Reject** | SES rejected the email based on content/policy checks | Inspect rejection reason and sending conditions |
| **Open/Click** | Observed only when tracking features are configured | Comply with privacy and consent requirements |

Event destinations can target **SNS**, **EventBridge**, or **CloudWatch** depending on the integration. To process bounces/complaints asynchronously, one pattern is **SES → SNS topic → SQS → Spring Boot feedback worker**. Configure SNS/SQS policies and DLQs on the feedback path independently of the sender's **ses:SendEmail** permissions.

### 8.2. Retries and Preventing Duplicate Emails

A request can time out on the application side after SES has already accepted the email; retrying immediately can send the recipient **two emails**. Therefore:

1. Assign a stable **business message/event ID** per email to send, e.g., keyed by **orderId + notificationType + version**.
2. Persist send state in a DB/outbox and control state transitions instead of blindly retrying without state tracking.
3. Use **backoff** and bounded retry counts for transient/throttling errors; never blindly retry invalid addresses or permission errors.
4. When consuming SQS, enforce **idempotency** before triggering email side effects.
5. Handle uncertain states (**timeouts** or worker crashes post-send) with appropriate reconciliation/tracking, since SES does not share an atomic transaction with your database.

If sending an email is a consequence of an order transaction in the DB, consider the **transactional outbox** pattern: write the event record in the same transaction as the order, then have a worker dispatch and send via SES. This reduces the risk of committing an order while failing to send its email when a process crashes.

## 9. Testing Spring Mail and SES

### 9.1. Unit Tests Without Connecting to AWS

An advantage of Spring **MailSender** is that you can mock/fake the interface to verify constructed message data. Example JUnit 5 + Mockito test for **OrderTextMailService**:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class OrderTextMailServiceTest {
    @Test
    void sendsOrderConfirmationWithExpectedFields() {
        MailSender mailSender = mock(MailSender.class);
        OrderTextMailService service =
                new OrderTextMailService(mailSender, "no-reply@example.com");

        service.sendConfirmation("customer@example.net", "ord-42");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(mailSender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("no-reply@example.com", sent.getFrom());
        assertArrayEquals(new String[]{"customer@example.net"}, sent.getTo());
        assertEquals("Order confirmation ord-42", sent.getSubject());
        assertTrue(sent.getText().contains("ord-42"));
    }
}
~~~

This test needs no AWS account, verified SES identity, or SMTP credentials. It verifies **content and recipient addressing**, without proving the payload actually went through AWS SES.

With **JavaMailSender**, you can mock the sender, return an in-memory **MimeMessage**, and inspect the subject, text/html parts, and attachments. Also unit-test HTML special characters, invalid recipients, and empty/oversized attachments according to application policy.

### 9.2. Realistic Integration Testing

Use an **AWS sandbox** and a dedicated verified identity for the test environment. The **SES mailbox simulator** can emulate mail delivery paths without emailing personal inboxes.

| Step | Action | Expected Result |
| --- | --- | --- |
| 1 | Verify **example.com** or From address in the test region | Identity shows verified status |
| 2 | Grant IAM role **ses:SendEmail** | **SimpleMailMessage** sends successfully |
| 3 | Add **ses:SendRawEmail**, send MIME with PDF | HTML/text and attachment accepted by SES |
| 4 | Test an unverified sender or wrong region | Receive error from SES, do not treat as success |
| 5 | Test sandbox behavior: send to unverified recipient | Restricted except for mailbox simulator |
| 6 | Send to success/bounce/complaint simulator addresses per SES docs | Observe expected SES events if event publishing is configured |
| 7 | Remove **ses:SendRawEmail** permission in sandbox | MIME send fails with a permission error |
| 8 | Send bursts up to test rate limits | Observe throttling and backoff retries |

Common mailbox simulator addresses include **success@simulator.amazonses.com** and **bounce@simulator.amazonses.com**; verify the latest simulator rules in SES documentation before running. Never send test messages to other people's email addresses without permission.

**Note:** Local mocks/emulators can test SDK calls or the SMTP interface, but cannot fully replace real DNS identity verification, delivery, spam filtering, and event pipelines. For IAM/permission testing, the AWS sandbox gives much more realistic results.

## 10. Troubleshooting Common Errors

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| SES starter fails to inject **MailSender** | Missing starter, auto-configuration disabled, or multiple beans of same type | Check dependencies, **spring.cloud.aws.ses.enabled**, beans, and profiles |
| Cannot inject **JavaMailSender** | Jakarta Mail API/implementation missing from classpath | Add Jakarta Mail + Angus, keep versions consistent |
| **AccessDenied** via API | IAM role lacks **ses:SendEmail** or **ses:SendRawEmail**, wrong identity ARN/From | Verify actual role, region, policy, and conditions |
| **MessageRejectedException** | Unverified From/sandbox recipient, suppression list, or other SES rule | Check SES identity, sandbox status, and error details |
| SMTP returns **535 Authentication Credentials Invalid** | Wrong SMTP username/password or mistakenly using AWS access keys | Generate/retrieve region-matched SES SMTP credentials, verify secret |
| SMTP timeout / TLS handshake error | Firewall, wrong endpoint/port, missing STARTTLS, or certificate issue | Verify host, TLS, and mail.smtp timeouts |
| Plain text succeeds, MIME/attachment fails | Missing **ses:SendRawEmail**, malformed MIME, or invalid attachment | Check raw permission, MIME builder, and size limits |
| API send succeeds yet recipient sees no email | Email bounced, suppressed, spam-filtered, or delayed delivery | Check SES event publishing/metrics and receiver status |
| Duplicate emails after retry | Prior request was accepted before client timeout | Idempotency, outbox, and event ID logging |
| Multi-recipient email leaks address list | Putting multiple recipients in To/Cc inappropriately | Enforce privacy rules; use Bcc or send individually as required |

### 10.1. Structured Diagnosis Order

1. **Is the app using SES API or SMTP?** Determine from dependencies and runtime beans, as authentication mechanisms differ.
2. **Are the From identity and region correct?** Verify identity status and account sandbox/production access.
3. **Are the AWS principal or SMTP credentials valid?** Check the IAM role for API; check the separate SMTP credential pair for SMTP.
4. **Did SES accept the request?** Separate pre-send Spring errors, API/SMTP errors, and acceptance responses.
5. **What is the delivery status?** Check SES event destinations, bounces/complaints, suppression lists, and logs.
6. **Were there retries or duplicate events?** Cross-reference the business event ID with send attempts and consumer acknowledgments.

If a direct SDK call to **SES API SendEmail** returns a **MessageId**, that is the ID of the accepted SES message, not proof that the recipient opened it. Spring's **MailSender.send** methods do not return this MessageId by default.

## 11. When to Use the SDK Directly?

**Spring Mail** fits well when business services simply want to send email content. Certain SES-specific needs may warrant calling **AWS SDK for Java v2** directly, such as capturing **SendEmailResponse.messageId**, using newer SES features not yet exposed by the adapter, or attaching per-request tags/configuration sets.

Two common SDK clients:

- **SesClient**: classic SES API used under the hood by the Spring Cloud AWS SES sender in the illustrated branch.
- **SesV2Client**: SES API v2, supporting its own operations and request types.

When using the SDK directly, an application adapter can implement a business interface such as **TransactionalEmailGateway** so order-processing code stays decoupled from the AWS SDK. Both sending paths still require managing region, verified identities, IAM, and delivery tracking properly.

**Do not build a JavaMailSender implementation from scratch** when you only need standard text or MIME emails; Spring Cloud AWS's SES adapter and Spring Boot's SMTP integration already provide two testable paths.

## 12. Self-Guided Exercise

**Requirement:** build a Spring Boot service that sends order confirmation emails via SES. Start with the **Spring Cloud AWS SES starter** and an IAM role in the sandbox.

1. Verify a domain/From email in the chosen SES region. Check sandbox status, quotas, and sending permissions.
2. Add **spring-cloud-aws-starter-ses**, configure region and **app.email.from**.
3. Write **OrderTextMailService** with **MailSender** and **SimpleMailMessage**.
4. Add Jakarta Mail/Angus and write **ReceiptMailService** sending HTML + text fallback + PDF via **JavaMailSender**.
5. Create an IAM policy permitting only **ses:SendEmail** and **ses:SendRawEmail** from the intended verified identity.
6. Write unit tests verifying content and recipients without AWS.
7. Run integration tests using the SES mailbox simulator and observe delivery/bounce events.
8. Switch dependencies/configuration to **spring-boot-starter-mail**, generate SES SMTP credentials, and repeat using the same service code.
9. *Advanced:* enqueue email tasks in SQS, implement idempotency, and route feedback events via SES configuration set → SNS/EventBridge.

### Review Questions

1. Why can Spring Cloud AWS send emails via **MailSender** without needing an SMTP host/password?
2. How do **MailSender** and **JavaMailSender** differ in message types and SES IAM actions?
3. Why is **ses:SendEmail** insufficient for MIME emails under the Spring Cloud AWS adapter?
4. Can an AWS IAM role be used directly as the SES SMTP username/password?
5. Can an SES account in sandbox mode immediately email unverified recipients?
6. How do **send success**, **delivery success**, and **recipient reading the email** differ?
7. What can happen if a client retries after a timeout even though SES already accepted the email?
8. Why is routing SES feedback through SNS/SQS useful for bounces and complaints?

## 13. References

- [Spring Cloud AWS 3.3.1 — SES Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html#ses-integration): SES starter, MailSender/JavaMailSender, MIME, region configuration, and IAM.
- [Spring Cloud AWS — SimpleEmailServiceJavaMailSender API](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/apidocs/io/awspring/cloud/ses/SimpleEmailServiceJavaMailSender.html): JavaMailSender adapter backed by the SES API.
- [Amazon SES — Getting started with sending email](https://docs.aws.amazon.com/ses/latest/dg/getting-started-sending.html): verified identities and sending permissions.
- [Amazon SES — Production access and sandbox](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html): per-region recipient/quota restrictions.
- [Amazon SES — Obtaining SMTP credentials](https://docs.aws.amazon.com/ses/latest/dg/smtp-credentials.html): how SMTP credentials differ from AWS access keys.
- [Amazon SES — Sending via SMTP](https://docs.aws.amazon.com/ses/latest/dg/send-using-smtp-programmatically.html): SMTP endpoints, ports, and STARTTLS.
- [Amazon SES — Troubleshoot SMTP](https://docs.aws.amazon.com/ses/latest/dg/troubleshoot-smtp.html): authentication, network, and message error codes.
- [Amazon SES — Event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html): configuration sets, deliveries, bounces, and complaints.
- [AWS SDK for Java v2 — SES examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sesv2_code_examples.html): email sending APIs and reading MessageId.

**Expected outcome:** learners can integrate **Amazon SES with Spring's mail mechanism**, understand both SES API and SMTP modes, send both plain text and MIME emails, grant proper permissions, protect credentials, test safely, and track the email lifecycle from send through receiving-server feedback.
