# SMTP Relay and Sending Permission Limits

When a Spring application sends an email over SMTP, the server receiving the request may need to **forward the message to another domain**. That operation is called **SMTP relay**. However, an SMTP server should not relay mail out to the Internet for anyone who connects to it: relay permissions must be controlled by sender policies, authentication, trusted networks, destination domains, and traffic limits.

Understanding SMTP relay helps explain common situations such as `Relay access denied`, `Authentication required`, being able to send internal mail but not external mail, or sending successfully for a while before getting rate-limited. In Spring Framework Mail, configuring the connection is only part of the solution; actual sending permission is still decided by the **SMTP server**.

## 1. What Is SMTP Relay?

**SMTP (Simple Mail Transfer Protocol)** is the protocol used to send and transfer mail between email systems. **Relay** is the act of an SMTP server receiving a message and forwarding it to another system instead of delivering the message directly into a mailbox it serves.

For example, an application sends an email from `no-reply@shop.example` to `customer@example.net`:

```text
 [Spring Application]
        |
        | SMTP submission: authenticate, submit mail
        v
 [SMTP server / MSA of shop.example]
        |
        | SMTP relay: forward mail to example.net domain
        v
 [MTA at example.net]
        |
        | Local delivery
        v
 [Mailbox customer@example.net]
        |
        v
 [Customer's mail client]
```

In practice, there may be multiple intermediate MTAs. The submission-receiving server may act as both a **Mail Submission Agent (MSA)** and a **Mail Transfer Agent (MTA)**, or hand off mail to another relay.

Key point to remember: **relaying is not the same as every email receipt**. An email server can accept mail from the Internet for delivery to the mailboxes of the domain it manages, while still **refusing to relay mail to other domains** for unauthorized clients.

### Submission, Relay, and Local Delivery

| Activity | Initiator | Receiver | Goal |
| --- | --- | --- | --- |
| **Submission** | Application, mail client, or internal service | MSA/SMTP submission server | Submit a new email for the sending system to process |
| **Relay** | MTA or client granted relay permission | Next MTA | Forward the message to another destination |
| **Local delivery** | Receiving domain's email infrastructure | MDA/mail store | Deliver the message into a mailbox belonging to the receiving system |

Submission typically goes over port **587 (STARTTLS)** or **465 (TLS immediately on connect)**. MTAs on the Internet usually communicate with each other over **port 25**. Ports are deployment conventions; server-side policies determine which clients are allowed to submit or relay.

## 2. Why Must Relay Permissions Be Restricted?

Consider a company-managed SMTP server accepting connections from multiple sources:

- An application configured with valid SMTP credentials needing to send order confirmations.
- An internal server permitted by an administrator to relay without logging in because it sits inside a trusted network.
- An MTA from the Internet delivering mail to `employee@company.example`, a mailbox the company actually manages.
- An unknown machine on the Internet wanting the company's SMTP server to send thousands of emails to external domains.

The first three cases **can be valid per configuration**. The last case must be rejected. If a server lets any source relay mail to any destination domain, that is an **open relay** risk.

Open relays are frequently abused to distribute spam, phishing, and bulk junk mail. The consequences go beyond increased server load: sending IPs or domains can suffer poor reputation, legitimate transactional emails get rejected, accounts get suspended, or service costs spike rapidly.

Therefore, relay policy usually begins with the question:

> **Who is requesting to relay mail, is that party authorized to relay through this server, and where is the mail allowed to go?**

## 3. Distinguishing Legitimate Mail Receipt from Allowing Relay

Suppose `mx.company.example` is the MTA receiving email for the `company.example` domain.

| SMTP request | Connecting party | Destination | Typical decision | Reason |
| --- | --- | --- | --- | --- |
| Send mail to `alice@company.example` | External MTA | Domain managed by the server | **Allow receipt**, after policy checks | This is mail addressed **to** a mailbox the system serves |
| Send mail to `bob@example.net` | Unauthenticated Internet client | External domain | **Deny relay** | The server has no responsibility to forward outbound mail for unknown sources |
| Send mail to `bob@example.net` | App with valid SMTP AUTH | External domain | **May allow relay** | Granted outbound permission, if additional policies are met |
| Send mail to `bob@example.net` | Service from an allowlisted IP | External domain | **May allow relay** | Granted permission via trusted network |
| Send mail to `alice@company.example` | Any client | Internal domain but mailbox does not exist | **May reject** | Accepting mail for a domain does not mean accepting every address |

Do not confuse a **mailbox domain** with a **relay domain**. A server can be configured to accept and deliver mail for its own domains; intermediate domains needing forwarding are governed by separate policies. Simply adding a domain to a recipient list does not mean anyone can relay arbitrarily.

A simple decision flow:

```text
Receive SMTP RCPT TO:<recipient@domain>
                   |
                   v
      Does server manage this destination?
              /           \
            Yes            No
            |               |
      Apply internal       Client authorized to relay?
      mail receipt policy      /           \
            |                Yes            No
      Accept/reject by        |              |
      address, filters     Apply          Reject:
      and config          outbound      relay denied
                           policy
                              |
                       Accept/reject
```

The diagram only shows the principle. A real SMTP server may apply additional policies to sender, connection source, recipient, traffic volume, and content before accepting a message.

## 4. Ways to Grant SMTP Relay Permission

### 4.1. SMTP AUTH Authentication

**SMTP AUTH** lets a client prove its identity when submitting mail. A Spring application typically provides credentials to an SMTP submission server, which then checks whether the account is allowed to send.

A common flow:

1. The client connects to the submission endpoint.
2. Sends `EHLO` to receive the server's list of supported capabilities.
3. If the server and port use STARTTLS, the client upgrades the connection via `STARTTLS` and sends `EHLO` again.
4. The client authenticates via `AUTH` using a server-permitted mechanism.
5. The server applies the authenticated identity's sending permissions to subsequent mail commands.

In normal deployments, SMTP passwords should not be sent over an unprotected connection. **STARTTLS** upgrades an initial connection to TLS; port 465 typically uses **implicit TLS** (TLS from the very start).

SMTP AUTH answers **which client is making the request**. It does not automatically guarantee that account can spoof any `From` address or send without limits. The SMTP server must still enforce other permissions.

Some providers use app-specific usernames/passwords, OAuth, or tokens per their mechanism. The application must follow the actual method supported by the endpoint.

### 4.2. Allowing by IP Address or Trusted Network

An internal relay may grant permission to connections originating from an administrator-selected IP range (**IP allowlist**), such as a service deployed exclusively inside a private network.

Example of policy logic:

```text
trusted_clients:
  - IP of internal notification app
  - IP of managed batch server

relay_policy:
  - allow trusted_clients within defined sending scope
  - allow authenticated clients with sending permission
  - reject other relay requests
```

This is a **policy illustration**, not direct configuration for a specific SMTP server.

Points for caution:

- Only allowlist truly trusted IPs. Overly broad network ranges can inadvertently grant permission to uncontrolled devices.
- When using NAT, many applications may share the same public IP; granting permission by that IP can widen access beyond intent.
- IPs can change with cloud, container, or network deployments; infrastructure changes must be accompanied by policy reviews.
- Trusted IP sources can still be compromised, so rate limits, sender checks, and logging remain necessary.
- Never grant relay permission simply because a connection comes from the Internet without proper authorization.

IP-based allowlisting works well for controlled infrastructure services, but is usually less flexible than SMTP AUTH when applications run across varied environments.

### 4.3. Permissions by Account, Sending Domain, and Destination

**Successful authentication is not enough to send anything you want.** A provider can restrict an account or credential to specific scopes:

- Only allowed to use verified sender addresses, such as `notifications@company.example`.
- Only allowed to send from verified domains or authorized aliases.
- Only allowed to send to internal domains, test recipient lists, or designated external domains.
- Only allowed to send with a credential dedicated to a specific app or environment.
- Blocked from further relaying from anomalous sources, over-quota usage, or anti-abuse policy violations.

For example, account `billing-smtp` might be allowed to send from `billing@company.example` but lack permission to set `From: ceo@company.example`. This is **sender authorization** policy enforced by the server or provider.

## 5. SMTP Envelope, From Header, and Sending Permissions

When discussing "who is allowed to send on whose behalf", separate the **SMTP envelope** from **displayed headers**:

| Part | Example | Used for |
| --- | --- | --- |
| `MAIL FROM` | `bounce@company.example` | Envelope sender address, commonly used for non-delivery notices |
| `RCPT TO` | `customer@example.net` | Recipient address used in the SMTP session |
| `From:` header | `Company <notifications@company.example>` | Sender identity displayed inside the email |
| `Reply-To:` header | `support@company.example` | Suggested address when the recipient replies |

The envelope sender and `From` header **do not have to match**. For example, an email-sending provider may use a separate bounce address to receive failure reports. Server policies can inspect both the envelope address and header address to curb spoofing.

**SMTP AUTH**, **SPF**, **DKIM**, and **DMARC** are not the same mechanism:

- **SMTP AUTH:** authenticates the client to the submission server, typically used to decide submission/relay permissions.
- **SPF:** helps the receiving server evaluate whether the sending MTA's IP is authorized by the SPF-relevant domain.
- **DKIM:** provides a cryptographic signature so the receiver can verify selected signed headers and body.
- **DMARC:** applies policy based on SPF/DKIM results and domain alignment with the `From` header.

SPF/DKIM/DMARC primarily help **evaluate message identity and trustworthiness on the receiving side**. They do not replace checking relay permission at the SMTP submission server. A leaked SMTP credential can still abuse the sending service even when the domain's DNS is properly configured.

## 6. Sending Permission Limits Are Also Traffic Limits

Even legitimate clients should not have unlimited sending rights. A relay typically enforces quotas to protect the system, IP/domain reputation, and provider resources.

| Limit type | Meaning | Example enforcement |
| --- | --- | --- |
| **Messages over time** | Max emails per minute/hour/day | Per credential, tenant, or app |
| **Recipient count** | Max recipients per message or per time window | Counted across `RCPT TO` commands |
| **Message size** | Limit on total message size, including MIME/attachments | Reject oversized mail |
| **Concurrent connections** | Number of SMTP sessions open simultaneously | Limited per IP/account |
| **Command rate** | Frequency of commands or requests per connection | Block abnormal bursts |
| **Sender address scope** | Only approved senders/domains | Block internal identity spoofing |
| **Recipient scope** | Only internal or approved recipient domains | Restrict emails from staging/test |
| **Reputation and anti-abuse** | Block abnormal traffic or flagged content | Temporarily suspend credential, throttle |

Exact numbers depend on the provider, service tier, and operational config. There is no single "global SMTP limit" applicable to every server.

### Message Limit vs. Recipient Limit

An application sending **one message to 50 addresses** may count as one message submission, yet the provider may count 50 recipients toward its quota. Check carefully whether the provider limits **messages**, **recipients**, or both.

### Throttling and Retry

When hitting a temporary limit, the SMTP server may ask the client to slow down with a **4xx** reply. The client or MTA can retry later under a controlled retry mechanism. **5xx** replies usually signify a permanent failure for the current request and should not be repeated blindly.

Illustrative examples; **exact codes and messages depend on the server**:

```text
421 4.7.0 Temporary rate limit; try again later
451 4.7.1 Temporarily deferred by policy
552 5.3.4 Message size exceeds fixed maximum size
554 5.7.1 Relay access denied
```

In a Spring application, distinguish **errors before the server accepts the message** from **unknown state due to disconnection**. If the connection drops right after sending content but before the client reads the final reply, the server may have accepted the message. Retrying without deduplication can create duplicate emails.

## 7. Open Relay: A Situation to Avoid

A server is considered an **open relay** when it lets unauthorized senders use its infrastructure to forward mail to destinations it does not manage.

```text
Unauthenticated Internet client
            |
            | sends to any external domain
            v
      [Open SMTP relay]
            |
            +----> Domain A
            +----> Domain B
            +----> Domain C
```

Risks include:

1. Exhaustion of CPU, queue storage, bandwidth, and sending costs.
2. Sending IPs or domains getting placed on adverse reputation lists.
3. Legitimate transactional mail getting delayed or rejected.
4. Difficulty distinguishing legitimate email from traffic generated by unknown parties.
5. Service suspension by the provider upon detecting abuse.

A safe relay policy must **distinguish mail addressed to domains managed by the receiving server from requests to forward mail on behalf of clients to external domains**, and only allow forwarding requests from authorized identities or sources.

### Example Relay Rules in Postfix

Postfix is a widely used MTA. A snippet illustrating how unauthorized relaying is rejected:

```ini
smtpd_relay_restrictions =
    permit_mynetworks,
    permit_sasl_authenticated,
    reject_unauth_destination
```

Conceptual meaning:

- `permit_mynetworks`: allows connections from declared trusted networks.
- `permit_sasl_authenticated`: allows clients authenticated via SASL.
- `reject_unauth_destination`: rejects destinations the client lacks permission to relay to.

This is an **illustrative snippet**, not a complete Postfix configuration. Safe operation also requires properly defining `mynetworks`, `mydestination`, `relay_domains`, submission ports, TLS, SASL, recipient/sender policies, and other limits. In particular, **never set `mynetworks` to an overly broad range**, as that can turn the entire range into authorized relay sources.

## 8. Reading an SMTP Session to Understand Relay Permissions

In SMTP, the server often cannot fully decide sending permissions from the TCP connection alone. Policies are usually evaluated when the client authenticates and supplies `MAIL FROM` and `RCPT TO`.

### 8.1. Client Without Relay Permission

Illustrative exchange with a company MTA when an unauthenticated client tries to send to an external domain:

```text
S: 220 mx.company.example ESMTP ready
C: EHLO client.example.org
S: 250-mx.company.example
S: 250 SIZE 10485760
C: MAIL FROM:<someone@other.example>
S: 250 2.1.0 Ok
C: RCPT TO:<customer@example.net>
S: 554 5.7.1 Relay access denied
```

The server may accept `MAIL FROM` yet reject at `RCPT TO` because the recipient belongs to an external domain and the client lacks relay permission. The exact check order depends on server configuration; not every server returns the exact code above.

### 8.2. Client Authorized to Submit Mail

Example omitting authentication details and TLS negotiation bytes:

```text
S: 220 smtp.company.example ESMTP ready
C: EHLO spring-app.company.example
S: 250-STARTTLS
S: 250 SIZE 10485760
C: STARTTLS
S: 220 Ready to start TLS
    [TLS established successfully]
C: EHLO spring-app.company.example
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 10485760
C: AUTH ...
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<notifications@company.example>
S: 250 2.1.0 Ok
C: RCPT TO:<customer@example.net>
S: 250 2.1.5 Ok
C: DATA
S: 354 End data with <CR><LF>.<CR><LF>
C: From: notifications@company.example
C: To: customer@example.net
C: Subject: Order confirmed
C:
C: Your order has been confirmed.
C: .
S: 250 2.0.0 Queued as 12345
C: QUIT
S: 221 2.0.0 Bye
```

This is an **educational transcript**, not an instruction to send raw commands or expose credentials. The `AUTH ...` string intentionally omits authentication secrets. On real connections, such details must never appear in application logs.

The `250 ... Queued` reply shows the server accepted responsibility for further processing of the message, **not that the recipient has seen the mail in their Inbox**.

## 9. Configuring Spring Boot to Send via SMTP Relay

In Spring Framework Mail, `JavaMailSender` helps the application submit emails to the configured SMTP server. Relay permissions live on the server side, while the application must connect to the right endpoint, right port, and provide valid credentials.

### 9.1. Dependency

For a Spring Boot application using Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

`spring-boot-starter-mail` provides mail-sending integration and Spring Boot's matching auto-configuration. In plain Spring Framework, declare a `JavaMailSender` implementation and Jakarta Mail yourself.

### 9.2. SMTP Submission Configuration on Port 587

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Environment variables supply the endpoint, username, password, and sender address. The example assumes the SMTP server uses **SMTP AUTH over STARTTLS on 587**. Only set a `from` address authorized by the provider. Timeouts in milliseconds prevent hanging indefinitely when the SMTP server does not respond.

If the provider requires **implicit TLS on port 465**, the config differs:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.ssl.enable]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
```

These two examples are **two alternative connection modes**, depending on the SMTP server. Never assume every port supports both STARTTLS and implicit TLS.

### 9.3. Email-Sending Service

Example of a service sending plain-text email via `JavaMailSender`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendOrderConfirmation(String customerEmail, String orderCode) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(customerEmail);
        mail.setSubject("Order confirmation " + orderCode);
        mail.setText("Order " + orderCode + " has been recorded.");

        mailSender.send(mail);
    }
}
```

This code creates and submits the email. The SMTP server remains the party that decides whether the authenticated account has permission to send from `fromAddress` to `customerEmail`.

If the hostname, TLS, credentials, or sending permissions are misconfigured, the call may throw an exception in the `MailException` family, such as `MailAuthenticationException` on auth failure or `MailSendException` on send failure. Error details also depend on Jakarta Mail and the SMTP server. Do not treat every exception as immediately retryable.

### 9.4. Sending Permissions Must Be Configured on Both Sides

| Spring application side | SMTP server / provider side |
| --- | --- |
| Choose correct submission hostname and port | Enable matching endpoint, allow network access |
| Enable the right TLS mode | Configure TLS and authentication policy |
| Send credentials via supported method | Verify credentials, check relay permission |
| Choose valid `From` address | Enforce approved sender/domain allowlist |
| Respect send rate and message size | Enforce quotas, rate limits, content policies |
| Persist errors and business state | Provide SMTP replies, queues, delivery/bounce events if available |

No `spring.mail.*` flag can force an SMTP server that denies relaying to accept an unauthorized client.

## 10. Distinguishing Configuration Errors from Relay Policy Errors

When working with an SMTP server, **response codes and messages are indicative only; providers may use different specific codes**.

| Symptom | Possible cause | Troubleshooting approach |
| --- | --- | --- |
| `530 Authentication required` | Client did not authenticate when server required it | Check submission port, `mail.smtp.auth`, and credential config |
| `535 5.7.8 Authentication credentials invalid` | Credentials or AUTH mechanism rejected | Check account, secret, app permissions, and provider policy |
| `554 5.7.1 Relay access denied` | Client lacks permission to relay to destination domain | Check SMTP AUTH, allowlist, relay permission, and recipient domain |
| `550 5.7.1 Sender address rejected` | `MAIL FROM` or `From` not within permitted identities | Use a verified address/domain or configure sending delegation |
| `421` or `451` with limit notice | Throttled, temporary quota exceeded, or service error | Slow down, pace the queue, and retry with backoff |
| `552 Message size exceeds ...` | Message exceeds size limit | Reduce attachments or use file download links |
| Works internally, fails for external domains | Permitted for internal receipt/delivery but lacks relay permission | Check distinction between local delivery and relay policy |
| Send succeeded yet recipient sees no mail | Delivery incomplete, filtered, or landed in Spam | Inspect message ID, queue, delivery/bounce, and receiver policy |

### A Diagnostic Example

Suppose an application sends from `internal-app@company.example`:

1. Sending to `employee@company.example` is accepted.
2. Sending to `customer@example.net` returns `Relay access denied`.
3. Switch configuration to the proper SMTP submission endpoint using credentials authorized to send.
4. The server begins accepting outbound emails under the authorized identity.

The first two outcomes do not contradict each other: a server can accept mail for an **internal domain** without granting permission to **relay to external domains**. The fix is checking SMTP permissions, not editing the content of `SimpleMailMessage`.

## 11. Relay Policies for Development, Staging, and Production

A system can use different sending permission scopes across environments:

| Environment | Suggested policy | Goal |
| --- | --- | --- |
| **Local development** | Test SMTP server or mail sink that only captures test mail without Internet relay | Prevent accidentally emailing real users |
| **Staging / QA** | Dedicated credentials, restricted recipients or allowed domains | Test email workflows within a controlled scope |
| **Production** | Per-application credentials, verified senders/domains, proper quotas and logging | Send real notifications within granted permissions |

For example, if staging accidentally shares production credentials, a test script could exhaust quotas or send real mail to users. Isolating credentials and recipient policies contains the blast radius.

### Keeping Credentials Secret and Controlling Access

- Never hardcode SMTP usernames/passwords in Java or commit them to the repository.
- Inject secrets via a secrets manager or deployment platform environment configuration.
- Never put `AUTH` values, passwords, tokens, or full sensitive message bodies into logs.
- Scope each credential's permissions to only the required applications and sending domains.
- Revoke/rotate credentials upon suspected leaks; monitor for abnormal sending traffic.

### Application-Layer Rate Limiting

Beyond the SMTP server's quota, the application can maintain a **sending queue** and concurrency limits to avoid bursts. Useful principles:

1. Record send request status using a stable business identifier.
2. Decouple request creation from sending workers when resilience is needed.
3. Cap connection counts and send rates to match real quotas.
4. On temporary failures, retry with **backoff** and attempt limits.
5. Never retry infinitely on relay-permission or authentication failures.
6. Track uncertain response situations to minimize duplicate emails.

These principles do not expand the application's relay permissions; they help use granted permissions steadily.

## 12. Relay, Forwarding, Bounce, and Delivery Are Different States

All involve "moving mail", yet have distinct meanings:

- **SMTP relay:** authorized infrastructure receiving and forwarding mail to another MTA along the path.
- **Forwarding:** an address or mailbox having a rule that automatically forwards content to another address; may introduce extra SMTP hops and authentication policy checks.
- **Bounce / DSN:** failure notice when mail cannot be delivered, which may arise after an accepted submission.
- **Delivery:** the receiving system delivering mail into a mailbox or accepting downstream responsibility.
- **Read/open:** the recipient using a mail client to view content—completely distinct from the SMTP server accepting the message.

Therefore, a Spring application should distinguish:

```text
Created
   |
   v
Submitted to SMTP server
   |
   +-- Rejected now -----------------> Submission failure
   |
   v
Accepted by SMTP server
   |
   +-- Temporary relay problem ------> Queue/retry
   |
   +-- Permanent later failure ------> Bounce/DSN (if any)
   |
   v
Delivered by receiving infrastructure
   |
   v
Visible to recipient (folder/client dependent)
```

If the provider offers webhooks reflecting `delivered`, `bounced`, `deferred`, or equivalent events, use them to update business state. The result of `mailSender.send(...)` alone does not prove the email reached the destination mailbox.

## 13. Self-Practice Scenarios

### Scenario A: Why Does the MTA Accept Internal Mail but Not Forward Externally?

An unauthenticated application sends email to `staff@company.example` successfully, but sending to `friend@example.net` gets `Relay access denied`.

**Explanation:** the server may be responsible for receiving mail for `company.example`, yet not grant permission to relay to external domains for unauthenticated clients. Use the submission endpoint and an authorized identity or trusted network per configuration.

### Scenario B: Even With SMTP AUTH, Why Can't It Send From Any Address?

An application authenticates using account `service-a` successfully, but setting `From: director@company.example` gets rejected.

**Explanation:** authentication proves the client is `service-a`; policy may only allow authorized addresses/domains. Choose a valid sender or request the proper sending permission instead of disabling domain authorization policies.

### Scenario C: Sending 100 Emails Back-to-Back, the Last 20 Receive Temporary Errors

A batch job creates a spike exceeding the provider's per-minute limit.

**Explanation:** relaying may still be allowed but hit a **rate limit**. Use a queue, throttle to match quota, and retry with backoff for temporary error codes. Do not switch to an uncontrolled SMTP server just to bypass quotas.

### Scenario D: SMTP Returns `250 Queued` Yet the Recipient Reports No Mail

**Explanation:** the server only confirmed accepting the message. The MTA may still be retrying, or the mail was filtered, bounced at a later hop, or landed in Spam. Inspect infrastructure delivery info.

### Scenario E: Only Internal IPs Are Allowed to Relay, and a New Cloud Service Is Rejected

**Explanation:** the new source IP is outside the defined trusted range. You can migrate the service to SMTP AUTH or update the allowlist in a controlled way, while also reviewing IP ranges behind NAT.

## 14. Summary of Design Principles

**SMTP relay** is a server forwarding mail to another system. To relay safely, a server must identify **which destinations it serves** and **which clients are permitted to send via it to other destinations**. Relay permission can be granted via SMTP AUTH, trusted source allowlists, account/domain permissions, and recipient policies; it is further regulated by quotas, rate limits, and anti-abuse checks.

In a Spring application, `JavaMailSender` must be configured with the right host, port, TLS, credentials, and sender address. These configurations enable the client to perform **submission** properly. Relay permissions, traffic limits, and delivery outcomes remain the responsibility of the SMTP server and downstream email systems. Keeping this separation clear helps troubleshoot errors accurately without confusing "sent from the app" with "delivered to the recipient".
