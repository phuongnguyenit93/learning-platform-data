# Sender Identities, Sandbox, and Handling Delivery Failures

## 1. Context and Learning Objectives

A Spring Boot application sends order confirmation emails via **Amazon Simple Email Service (Amazon SES)**. The send call from the application succeeds yet the recipient never sees the email; or SES rejects the request because the From address is unverified, the account is still in sandbox mode, quotas were exceeded, or sending was paused. To operate reliably, you must understand the email lifecycle from **sender identity → domain authentication → sending permissions → SES acceptance → receiving mail server → bounce/complaint**.

This lesson belongs to the **Amazon SNS and SES** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module guides integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/access permissions, messaging, storage, data, secret protection, testing, and comparing cloud providers. The focus of this lesson is **sender identities, sandbox, and handling delivery failures** when using SES.

After this lesson, you will be able to:

1. Distinguish email identity, domain identity, **From** address, **MAIL FROM** domain, and SES region.
2. Configure domain/email verification, DKIM, SPF, DMARC, and a custom MAIL FROM domain.
3. Understand **sandbox** limits, how to request production access, and per-region quotas.
4. Configure IAM permissions so Spring Boot sends from the exact intended identity.
5. Classify pre-send errors, bounces, complaints, rejects, delivery delays, and suppression.
6. Set up event publishing to observe delivery status and process feedback in the system.
7. Test safely with the SES mailbox simulator and establish a repeatable failure-handling workflow.

## 2. Sender Identities in Amazon SES

### 2.1. Email Identity and Domain Identity

A **verified identity** is an email address or domain for which the AWS account has proven ownership/control. SES requires verifying an identity before sending email from it.

| Identity Type | Example | How to Verify | Best Fit |
| --- | --- | --- | --- |
| **Email identity** | **no-reply@example.com** | SES sends a verification email to the mailbox | Quick experiments, few sender addresses |
| **Domain identity** | **example.com** | Add DNS records provided by SES | Production apps with multiple sender addresses |
| **Subdomain identity** | **mail.example.com** | Verify a dedicated domain/subdomain per configuration | Separating sending streams, reputation, and DNS as needed |

A domain identity fits applications with multiple addresses such as **no-reply@example.com**, **billing@example.com**, and **support@example.com**. Domain verification proves control over the domain; it does not automatically create a mailbox to receive messages. If incoming reply handling is needed, a separate mail receiving service or SES email receiving setup is required.

**Identities are scoped to an AWS Region.** Verifying **example.com** in **ap-southeast-1** does not mean the identity is automatically verified in another region. The application, SES identity, configuration set, and quotas must all be checked in the same region targeted by the send request.

### 2.2. Domain Verification and DKIM

Basic setup flow:

1. Open the Amazon SES Console in the target sending region.
2. Create a **domain identity** for a domain controlled by your organization.
3. Enable **Easy DKIM** or configure an SES-supported DKIM method.
4. Add the DKIM **CNAME records** provided by SES to DNS.
5. Wait for DNS propagation, then confirm the identity shows **Verified** and DKIM is enabled/verified.
6. Promote the domain into production sending configuration only after verifying both the domain and From address.

**DKIM (DomainKeys Identified Mail)** signs messages with a key belonging to the sending domain. Receiving mail servers verify the signature against the public key published in DNS. SES Easy DKIM generates the required DNS records and manages signing keys automatically.

Illustrative DNS configuration example:

~~~text
Name:  <token-1>._domainkey.example.com
Type:  CNAME
Value: <token-1>.dkim.amazonses.com

Name:  <token-2>._domainkey.example.com
Type:  CNAME
Value: <token-2>.dkim.amazonses.com
~~~

Actual tokens and record counts must come from the SES Console/API; never fabricate tokens from examples. After updating DNS, verify both identity status and DKIM status inside SES rather than relying solely on the DNS provider reporting that records were saved.

### 2.3. SPF, DMARC, and MAIL FROM

These three concepts are often confused with the display **From** address:

- **From header:** the address recipients see in their email client, e.g., **no-reply@example.com**.
- **MAIL FROM / envelope sender:** the SMTP-layer address used for bounce notifications and part of SPF checks; end users typically do not see it directly like the From header.
- **SPF:** declares which systems are authorized to send mail on behalf of a domain.
- **DKIM:** authenticates the email content's signature against the signing domain.
- **DMARC:** requires alignment between the From header domain and the domain authenticated by SPF or DKIM; also lets the domain publish enforcement policies and receive reports.

SES can use a default MAIL FROM domain under **amazonses.com**. To use your organization's subdomain instead, configure a **custom MAIL FROM domain**, such as **bounce.example.com**. SES requires matching DNS records, including:

~~~text
Name:  bounce.example.com
Type:  MX
Value: <region-feedback-endpoint>.amazonses.com

Name:  bounce.example.com
Type:  TXT
Value: "v=spf1 include:amazonses.com ~all"
~~~

The exact MX value must match your SES region and Console instructions. This record points to SES's feedback endpoint, not an MX record for delivering user mail to a mailbox. A custom MAIL FROM domain must be a subdomain meeting SES's requirements; do not arbitrarily reuse a subdomain already handling regular inbound/outbound mail.

**DMARC** can be published at **_dmarc.example.com**. Example initial monitoring-only policy:

~~~text
Name:  _dmarc.example.com
Type:  TXT
Value: "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
~~~

**p=none** requests monitoring only without instructing receivers to quarantine or reject mail. Once all legitimate sending sources are accounted for, the organization can consider moving to **quarantine** or **reject** along a domain governance roadmap. Never set a strict DMARC policy before auditing every legitimate sending system in the organization; doing so can disrupt non-SES mail as well.

**Note:** DMARC passes when either SPF or DKIM achieves alignment under DMARC rules. Custom MAIL FROM supports SPF alignment; Easy DKIM can support DKIM alignment when the signing domain matches properly. Having an SPF record alone does not automatically prove the From header is authenticated.

## 3. Sandbox and Production Access

### 3.1. Sandbox Limitations

New SES accounts typically start in the **sandbox**, and sandbox status is managed **per AWS Region**. In the sandbox, an account can use many SES features but faces recipient and sending-rate restrictions.

Per AWS documentation, default sandbox limits are typically:

- Send only to **verified email addresses/domains** or the **SES mailbox simulator**.
- Maximum **200 recipients per 24 hours** under default sandbox limits.
- Maximum sending rate of **1 email/second**.

Limits and quotas can vary by account/region; always inspect **Sending limits** in the SES Console or API. Overall quotas count **recipients**, not just API call count; a single email addressed to multiple recipients consumes multiple quota units.

In the sandbox, an unverified address like **customer@example.net** will be rejected even if **no-reply@example.com** is a verified identity. Therefore, testing should use verified recipient addresses or the mailbox simulator.

### 3.2. Requesting Production Access

When an application needs to email general recipients, request SES **production access** in each region you intend to use. Prepare accurate information covering:

- Website or application sending emails.
- Mail type: **TRANSACTIONAL** for order confirmations, invoices, password resets; **MARKETING** for newsletters/promotions.
- How consent is collected and how unsubscribes are handled if sending marketing mail.
- Processes for handling bounces, complaints, suppression, and opt-out requests.
- Contact addresses able to receive AWS responses.

You can submit the request via the AWS CLI SES v2:

~~~bash
aws sesv2 put-account-details \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url "https://app.example.com" \
  --contact-language EN \
  --additional-contact-email-addresses "ops@example.com" \
  --region ap-southeast-1
~~~

This is an example for a transactional email application. Replace website/contact details with real values and target the right region. Submitting the request does not grant production access immediately; inspect account status after AWS reviews the request.

Check status:

~~~bash
aws sesv2 get-account \
  --region ap-southeast-1 \
  --query '{ProductionAccess:ProductionAccessEnabled,SendingEnabled:SendingEnabled,Quota:SendQuota}'
~~~

**ProductionAccessEnabled** and **SendingEnabled** are two separate flags to observe. An account with production access whose sending capability is paused still cannot send.

### 3.3. Quotas and Sending Rate

Quotas are **per region**. Do not assume switching from **ap-southeast-1** to another region preserves the same limits. SES also enforces sending rate limits; exceeding them triggers throttling or quota errors.

In the application:

- Use queues/workers to pace sending rather than emitting large bursts.
- Track recipient counts per email, 24-hour quota, and sending rate.
- Retry throttling with **exponential backoff + jitter**, with a bounded retry limit.
- Do not retry identity, recipient, or permission failures as if they were transient errors.
- If higher quotas are needed, submit a limit-increase request through AWS Support backed by solid operational metrics.

## 4. Configuring Identity and Permissions for Spring Boot

The previous SES integration lesson introduced **MailSender**, **JavaMailSender**, SES API, and SMTP. This section focuses on the conditions ensuring the sender is authorized to use the right identity.

### 4.1. Region and From Address

Example **application.yml** for Spring Cloud AWS 3.x:

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
    from: ${MAIL_FROM:no-reply@example.com}
~~~

- **spring.cloud.aws.region.static** sets the default region for the AWS SDK.
- **spring.cloud.aws.ses.region** specifies the SES region explicitly if separate from other AWS clients' default region.
- **app.email.from** is an application-defined property; its value must belong to an authorized verified identity in the configured SES region.

On AWS, prefer an **IAM role** on the ECS task, EC2 instance, or EKS workload identity. Development machines can use an AWS CLI profile. Never hardcode AWS access keys or secrets in the repository, committed YAML files, or logs.

### 4.2. IAM Policy Scoped to Identity

Example where the application role may only send from domain identity **example.com** in account **123456789012**, region **ap-southeast-1**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendFromVerifiedExampleDomain",
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

- **ses:SendEmail** covers standard email sending APIs.
- **ses:SendRawEmail** is needed for MIME/raw email paths in Spring Mail integration.
- **Resource** scopes access to the SES identity.
- **ses:FromAddress** restricts which From address is allowed.

This illustrates a policy for a sender in the same account as the identity. When using **sending authorization** to send on behalf of an identity-owning account, both the identity owner's policy and the delegate sender's permissions are required. Do not copy cross-account policies without understanding the actual principals.

### 4.3. Test Send with Spring Mail

Short example with **MailSender**:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class SesMailService {
    private final MailSender mailSender;
    private final String from;

    public SesMailService(
            MailSender mailSender,
            @Value("${app.email.from}") String from) {
        this.mailSender = mailSender;
        this.from = from;
    }

    public void send(String recipient, String orderId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Order confirmation " + orderId);
        message.setText("Order " + orderId + " has been received.");
        mailSender.send(message);
    }
}
~~~

When using the Spring Cloud AWS SES starter, requests go via the SES API and the application's IAM role is evaluated. When using SMTP, replace the auth mechanism with region-matched **SES SMTP credentials**; SMTP username/password are not AWS SDK access key/secret key pairs. In both cases, verified identity, sandbox, quotas, and suppression still govern deliverability.

## 5. Classifying Failures by Stage

Do not lump all email errors into a single **send failed** bucket. Distinguish failures before SES accepts the request from failures after SES has accepted it.

~~~mermaid
flowchart TD
    A["Spring Boot sends email"] --> B{"Did SES accept request?"}
    B -->|"No"| C["API/SMTP error<br/>IAM, identity, sandbox, quota"]
    B -->|"Yes"| D["SES MessageId"]
    D --> E{"Recipient mail server?"}
    E -->|"Accepted"| F["Delivery event"]
    E -->|"Permanently rejected"| G["Hard bounce"]
    E -->|"Temporary error"| H["Soft bounce / delay"]
    D --> I["Recipient reports spam"]
    I --> J["Complaint event"]
~~~

### 5.1. Failures Before SES Acceptance

| Error / Symptom | Common Causes | Resolution |
| --- | --- | --- |
| **MessageRejected / identity not verified** | Unverified From/recipient in sandbox, or identity in a different region | Verify identity, From address, and region |
| **AccessDenied** | IAM role missing **ses:SendEmail/ses:SendRawEmail**, wrong resource or condition | Identify runtime principal; compare action, identity ARN, and From |
| **Throttling / maximum sending rate exceeded** | Sending faster than allowed rate | Queuing, rate limiter, backoff with jitter |
| **Daily message quota exceeded** | 24-hour quota exhausted | Check per-region quota, slow down, or request a limit increase |
| **AccountSendingPaused / SendingEnabled=false** | AWS paused account sending | Inspect account status and resolve root cause with AWS |
| **Configuration set does not exist** | Request references wrong configuration set name or set not created | Check SES configuration set in the exact region |
| **SMTP 535 authentication failed** | Wrong SES SMTP username/password or confused with AWS access key | Generate/configure region-matched SES SMTP credentials |
| **SMTP timeout/TLS failure** | Wrong endpoint, port, TLS, or network egress rule | Check endpoint, STARTTLS/SSL, firewall, and timeouts |

A pre-acceptance error usually throws an exception or returns an SMTP response code for the application to classify. Do not infinitely retry **AccessDenied**, **MessageRejected**, or unverified-identity errors; fix the configuration or data first.

### 5.2. Failures After SES Accepts the Email

After SES accepts a request, the recipient's mail server decides whether to accept or reject the message. Common statuses:

| Event | Meaning | Business Handling |
| --- | --- | --- |
| **Send** | SES recorded the send request | Record accepted status at the SES layer |
| **Delivery** | Destination mail server accepted the email | Mark delivered; does not mean the recipient read it |
| **Bounce** | Email could not be delivered to the destination address | Classify permanent/transient and update address status |
| **Complaint** | Recipient flagged the email as spam | Stop emailing that address per policy; review consent and content |
| **Reject** | SES rejected the message due to content/policy checks | Inspect content, virus scan, or SES policy triggers |
| **DeliveryDelay** | SES hit a temporary issue delivering to destination mail server | Monitor retries and subsequent events |
| **RenderingFailure** | Failed to render an SES template | Check template data and template version |

A **hard bounce/permanent bounce** usually indicates the address does not exist or is permanently undeliverable. A **soft bounce/transient bounce** can result from a full mailbox, temporarily unavailable server, or receiving limits. Never keep retrying a hard bounce as though it were a transient network glitch.

**Delivery** means the receiving mail server accepted the message. SES cannot guarantee that the message landed in the primary inbox, escaped later spam filtering, or was opened by the recipient.

## 6. Bounces, Complaints, and the Suppression List

### 6.1. Why Must Bounces and Complaints Be Handled?

Repeatedly sending to invalid addresses drives up bounce rates and harms sending domain/IP reputation. Emailing recipients who reported spam increases complaint rates, which can trigger SES account review or sending suspension.

A production system must:

- Stop sending to hard-bounced addresses.
- Treat complaints as serious opt-out signals.
- Separate transactional and marketing mail by consent, purpose, and unsubscribe policy.
- Record timestamp, bounce/complaint type, message ID, and event source.
- Never automatically re-enable suppressed addresses merely because a list import ran.

### 6.2. Account-Level Suppression List

SES provides an **account-level suppression list** per AWS Region. Depending on configuration, SES can automatically add addresses causing **hard bounces** or **complaints** to the account's suppression list. Suppressed addresses are checked before sending.

Key behaviors to remember:

- If an address is on the suppression list for an enabled reason, SES may **accept the request without actually performing delivery**; the application must monitor bounce/events and suppression rather than relying solely on API success.
- Addresses on the account suppression list stay there until managed/removed via your workflow; do not auto-retry the same recipient.
- Enable only needed reasons (**BOUNCE**, **COMPLAINT**) and maintain a process for suppression records.
- The account suppression list is region-specific; check the right region when investigating.
- The AWS global suppression list and account-level suppression list are distinct concepts. Do not assume you can directly query every address on the global list.

Inspect and enable the account-level suppression list:

~~~bash
aws sesv2 get-account-suppression-attributes \
  --region ap-southeast-1

aws sesv2 put-account-suppression-attributes \
  --suppressed-reasons BOUNCE COMPLAINT \
  --region ap-southeast-1
~~~

Before enabling or changing account-wide settings, evaluate the impact on other applications sharing SES in that region. Do not treat the suppression list as a substitute for consent verification or recipient list hygiene.

### 6.3. Feedback Processing Workflow

A straightforward workflow:

1. Receive bounce/complaint events from SES.
2. Extract **recipient**, **bounceType**, **bounceSubType**, **complaintFeedbackType**, **mail.messageId**, and related send metadata.
3. Correlate the event with the email/order/notification record in the DB.
4. For hard bounces, mark the address invalid or suppressed; halt automated sends.
5. For complaints, update preference/consent and block further sends per policy.
6. For soft bounces, retry only when the reason permits and within bounded backoff limits.
7. Log carefully, avoiding storing full email bodies or unnecessary personal data.

Do not apply the same retry policy to every event. For example, **mailbox full** may be transient, whereas **no such user** requires stopping sends.

## 7. Tracking Status with Configuration Sets and Event Publishing

### 7.1. Configuration Sets and Event Destinations

A **Configuration set** is a group of SES settings attached to a send call, routing events and applying tracking options. Events can be published to SES-supported destinations such as:

- **Amazon SNS**: publish bounce/complaint/delivery events to subscribers.
- **Amazon EventBridge**: send events to an event bus for multi-target routing.
- **Amazon CloudWatch**: monitor metrics and trigger alarms.
- **Amazon Kinesis Data Firehose**: stream event records to analytics/storage when configured.

To enable event publishing:

1. Create a configuration set in the exact SES region.
2. Add an event destination and select the event types to track.
3. Configure permissions for SES to publish to the chosen destination.
4. Ensure each send specifies that configuration set, or attach a default configuration set to the identity where supported.
5. Send a test email and confirm events arrive at the destination.

With SES API v2, send requests can specify **ConfigurationSetName**. Illustrative example using AWS SDK for Java v2:

Add the **software.amazon.awssdk:sesv2** module (version managed by the AWS SDK BOM) if not already in the project:

~~~groovy
dependencies {
    implementation("software.amazon.awssdk:sesv2")
}
~~~

~~~java
import software.amazon.awssdk.services.sesv2.SesV2Client;
import software.amazon.awssdk.services.sesv2.model.Destination;
import software.amazon.awssdk.services.sesv2.model.EmailContent;
import software.amazon.awssdk.services.sesv2.model.Message;
import software.amazon.awssdk.services.sesv2.model.SendEmailRequest;

public class SesV2Sender {
    private final SesV2Client sesClient;

    public SesV2Sender(SesV2Client sesClient) {
        this.sesClient = sesClient;
    }

    public String send(String from, String to, String subject, String body) {
        SendEmailRequest request = SendEmailRequest.builder()
                .fromEmailAddress(from)
                .destination(Destination.builder()
                        .toAddresses(to)
                        .build())
                .content(EmailContent.builder()
                        .simple(Message.builder()
                                .subject(software.amazon.awssdk.services.sesv2.model.Content.builder()
                                        .data(subject).build())
                                .body(software.amazon.awssdk.services.sesv2.model.Body.builder()
                                        .text(software.amazon.awssdk.services.sesv2.model.Content.builder()
                                                .data(body).build())
                                        .build())
                                .build())
                        .build())
                .configurationSetName("transactional-events")
                .build();

        return sesClient.sendEmail(request).messageId();
    }
}
~~~

The example above demonstrates **SES API v2** attaching a configuration set to a request. When using **Spring Cloud AWS MailSender**, verify how configuration sets are configured in your library version; if fine-grained request control is needed, build an adapter around **SesV2Client**. Do not assume every MailSender method automatically passes a configuration set.

### 7.2. Bounce Event Example

A bounce event may contain these conceptual fields (actual payload depends on event schema and destination):

~~~json
{
  "eventType": "Bounce",
  "mail": {
    "messageId": "0100018example",
    "source": "no-reply@example.com"
  },
  "bounce": {
    "bounceType": "Permanent",
    "bounceSubType": "General",
    "bouncedRecipients": [
      {
        "emailAddress": "invalid-recipient@example.net",
        "status": "5.1.1",
        "action": "failed"
      }
    ]
  }
}
~~~

Workers receiving events must process idempotently because events may be redelivered depending on the destination. Deduplication keys can combine message ID + event type + recipient or a stable event ID from the receiving system. Persist processing state so notifications or preference updates are not applied repeatedly.

### 7.3. SNS Feedback Queue

A common architecture:

~~~mermaid
flowchart LR
    A["Spring Boot<br/>Email sender"] --> SES(("Amazon SES"))
    SES -->|"Bounce / Complaint"| SNS(("SNS feedback topic"))
    SNS --> Q["SQS feedback queue"]
    Q --> W["Spring Boot<br/>Feedback worker"]
    W --> DB[("DB<br/>suppression / consent")]
~~~

If using SNS as an event destination, configure the **SNS topic policy** to let SES publish. If the topic fans out to SQS, the queue policy must allow the SNS service to send messages conditioned on **aws:SourceArn**. This is the feedback path; its permissions are independent of the sender's **ses:SendEmail** permission.

## 8. Safe Testing with the SES Mailbox Simulator

SES provides a **mailbox simulator** to test specific delivery outcomes without creating real mailboxes or emailing real users. Common simulator addresses:

| Address | Purpose |
| --- | --- |
| **success@simulator.amazonses.com** | Test successful delivery flow |
| **bounce@simulator.amazonses.com** | Generate a bounce event |
| **complaint@simulator.amazonses.com** | Generate a complaint event |
| **suppressionlist@simulator.amazonses.com** | Test suppression list behavior |
| **ooto@simulator.amazonses.com** | Test out-of-office responses where supported |

The mailbox simulator works in both sandbox and production; follow current SES documentation for specific simulator quotas and rules. Use the simulator instead of inducing bounces with random invalid addresses or spamming domains you do not control.

### 8.1. Test Matrix

| Test | Setup | Expected Outcome |
| --- | --- | --- |
| Valid identity | From belongs to verified domain, matching region | SES accepts request if permissions/quotas are valid |
| Identity in wrong region | Domain verified only in another region | SES rejects because identity is unverified in target region |
| Unverified sandbox recipient | Send to regular unverified email | Blocked by sandbox restrictions |
| Sandbox simulator | Send to mailbox simulator | Simulates outcome matching the simulator address |
| IAM missing **ses:SendEmail** | Remove action from test role | API call denied |
| IAM missing **ses:SendRawEmail** | Send MIME using role with only SendEmail | Raw email path denied |
| Bounce simulator | Enable event destination, send to bounce simulator | Bounce event received, worker updates status |
| Complaint simulator | Enable event destination, send to complaint simulator | Complaint event received, blocks future sends per policy |
| Account suppression | Add test address to suppression list | SES does not deliver when matching suppression reason is enabled |
| Throttling | Send requests exceeding test rate | Rate-limit error and backoff observed |
| Sending paused | Inspect paused test account if applicable | Cannot send; diagnose account state |

**Never** alter the state of a production account serving live users just to test failures. Use a sandbox account/region or isolated environment, dedicated policies, and simulator addresses.

## 9. Delivery Failure Troubleshooting Runbook

When a user reports "I did not receive the email", follow these steps in order:

### Step 1: Verify Whether SES Accepted the Request

- Check Spring Mail/API logs, exceptions, SMTP response codes, and request timestamps.
- If using the SDK directly, record the SES **MessageId** from the response.
- If using MailSender, log a correlation ID and request status; do not fabricate a fake MessageId.

If the request was rejected before SES acceptance, check IAM, verified identity, region, sandbox, quotas, account sending status, and SES configuration.

### Step 2: Check Identity and DNS

- Is the identity **Verified** in the exact region?
- Does the From address belong to a verified/authorized identity?
- Are DKIM records showing valid status?
- Do SPF/DMARC align with the sending domain?
- Does custom MAIL FROM have valid MX and SPF records?
- If DNS was recently updated, wait for propagation and re-verify in SES.

### Step 3: Check Account Status and Quotas

~~~bash
aws sesv2 get-account \
  --region ap-southeast-1 \
  --query '{ProductionAccess:ProductionAccessEnabled,SendingEnabled:SendingEnabled,SendQuota:SendQuota}'
~~~

If the account is paused, quota is exhausted, or rate is exceeded, fix the root cause instead of immediately increasing retries.

### Step 4: Inspect Delivery Events

- Locate **mail.messageId**, recipient, and timestamp.
- If **Delivery** exists, the destination mail server accepted the message; check recipient-side spam/quarantine/mailbox rules.
- If **Bounce**, inspect bounce type/subtype and halt sends on hard bounces.
- If **Complaint**, update preferences/suppression and stop sending per policy.
- If **DeliveryDelay**, monitor subsequent events and avoid creating unnecessary duplicate sends.

### Step 5: Check Suppression

Inspect the account-level suppression list in the exact region and the reason the address was added. If a valid address has been fixed, remove it from suppression only with supporting evidence and an approved business process; never bulk-delete entries automatically to boost delivery metrics.

### Step 6: Reconcile Retries and Duplicates

Use the business event ID to verify whether SES had already accepted the email earlier. A client timeout does not mean SES never received the request. If a worker retries without persisting state, a single email can be sent multiple times.

## 10. Security and Sending Quality

- **Least privilege:** IAM roles only grant required SES actions on specific identity ARNs.
- **No secret leaks:** never log sensitive bodies, SMTP passwords, access keys, or tokens; use a secret manager when needed.
- **Consent:** send emails only to recipients with a valid basis; marketing mail must include unsubscribe and preference workflows.
- **List hygiene:** remove non-existent addresses, hard bounces, and complaints; never buy or import lists of unknown origin.
- **Stream separation:** consider separate domains/subdomains, configuration sets, or accounts for transactional vs. marketing mail to isolate reputation.
- **Rate control:** use queues, rate limiting, and backoff; avoid bursts exceeding quotas.
- **Monitoring:** dashboards for bounce/complaint/delivery rates, alerts on metric spikes; evaluate trends rather than single requests.
- **Testing:** use the mailbox simulator, test identities, and sandbox; promote to production only after feedback and suppression workflows are ready.

A valid sender identity is necessary, not a guarantee of inbox placement. Domain/IP reputation, content, recipient engagement, SPF/DKIM/DMARC authentication, and mail provider policies all affect the final outcome.

## 11. Exercise and Review Questions

**Exercise:** Configure a dedicated domain identity for a test environment in **ap-southeast-1**, enable Easy DKIM, publish a monitoring DMARC policy, and verify a From address. Use Spring Boot to send emails via the SES API in sandbox mode, test simulator recipients, and then enable an event destination to handle bounces/complaints. Write an idempotent worker that updates email status and suppression state.

Tasks:

1. Record identity, region, DKIM status, MAIL FROM status, and sending status.
2. Send messages to the success, bounce, and complaint simulator addresses.
3. Capture events and correlate message IDs with send records in the DB.
4. Test a request rejected due to IAM permissions or an unverified identity.
5. Implement backoff retries for throttling, while never retrying hard bounces.
6. Write unit tests for the event classifier and integration tests for the SES event destination.
7. Compare sending via the SES API vs. SMTP: authentication, secrets, errors, and observability.

**Questions:**

1. Why does verifying a domain in one region not guarantee sending from another region?
2. How does the From header differ from the MAIL FROM domain?
3. How do DKIM, SPF, and DMARC support domain authentication?
4. Which recipients can a sandbox account send to?
5. How does production access differ from sending quotas and **SendingEnabled**?
6. In what case can SES accept a request without delivering the email?
7. How should hard bounces, soft bounces, and complaints be handled differently?
8. Why should message IDs/correlation IDs be stored and feedback processed idempotently?
9. Why is the mailbox simulator better than intentionally sending mail to invalid addresses?
10. When an email already has a Delivery event yet the recipient still does not see it in their inbox, where should you check next?

## 12. References

- [Amazon SES — Getting started with sending email](https://docs.aws.amazon.com/ses/latest/dg/getting-started-sending.html): identity workflow, sandbox, production access, and sending setup.
- [Amazon SES — Verifying identities](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html): email/domain identities and verification.
- [Amazon SES — Easy DKIM](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dkim-easy.html): DKIM setup and DNS records.
- [Amazon SES — SPF and DMARC](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-spf.html): SPF authentication, DKIM alignment, and DMARC.
- [Amazon SES — Custom MAIL FROM domain](https://docs.aws.amazon.com/ses/latest/dg/mail-from.html): MAIL FROM, MX, and SPF.
- [Amazon SES — Request production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html): sandbox restrictions and requesting production access.
- [Amazon SES — Sending quotas](https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html): per-region quotas and sending rates.
- [Amazon SES — Account-level suppression list](https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html): bounces, complaints, and suppression.
- [Amazon SES — Event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html): configuration sets and event destinations.
- [Amazon SES — Mailbox simulator](https://docs.aws.amazon.com/ses/latest/dg/send-an-email-from-console.html): testing delivery/bounce/complaint with the simulator.
- [Spring Cloud AWS — SES Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html#ses-integration): integrating SES with Spring Mail.

**Expected outcome:** learners can configure verified sender identities, understand sandbox vs. production access, integrate Spring Boot with SES using the right region and permissions, classify pre-send and post-send failures, and handle bounces/complaints/suppression based on real events.
