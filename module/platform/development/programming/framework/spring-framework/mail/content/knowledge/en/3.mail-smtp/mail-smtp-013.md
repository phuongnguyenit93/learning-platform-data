# Connection Timeout, Read Timeout, and Write Timeout in Spring Framework Mail

Sending email over SMTP is a network operation. Even though a Spring application has just one `mailSender.send(...)` call, many steps occur underneath: hostname resolution, TCP setup, receiving the SMTP greeting, TLS negotiation, authentication, transferring message content, and waiting for replies. When one step stalls, the mail-sending thread can block for a very long time without proper bounds.

Spring Framework Mail uses `JavaMailSender` and typically relies on Jakarta Mail to talk SMTP. The three most important timeouts are:

- **Connection timeout** — `mail.smtp.connectiontimeout`: limits how long to wait to establish the **socket connection** to the SMTP server.
- **Read timeout** — `mail.smtp.timeout`: limits how long a **socket read operation** waits for data.
- **Write timeout** — `mail.smtp.writetimeout`: limits how long a **socket write operation** can block.

All three properties use **milliseconds (ms)** and must be configured separately. They are not a single "total timeout" covering the entire email-sending lifecycle.

## 1. Viewing the Three Timeouts on the SMTP Timeline

An SMTP session with STARTTLS typically unfolds in these high-level steps:

```text
Java Application                            SMTP server
     |                                           |
     | -- DNS: smtp.example.com ---------------- |
     |                                           |
     | -- TCP connect -------------------------> |
     |      [connectiontimeout]                  |
     | <---------------------------- 220 ------- |
     |      [timeout: read]                      |
     | -- EHLO --------------------------------> |
     |      [writetimeout: write]                |
     | <----------------------------- 250 ------ |
     |      [timeout: read]                      |
     | -- STARTTLS ----------------------------> |
     | <----------------------------- 220 ------ |
     | -- TLS handshake -----------------------> |
     | -- EHLO / AUTH -------------------------> |
     | <----------------------------- 235 ------ |
     | -- MAIL FROM / RCPT TO -----------------> |
     | <----------------------------- 250 ------ |
     | -- DATA --------------------------------> |
     | <----------------------------- 354 ------ |
     | -- headers, body, attachments ----------> |
     |      [writetimeout: write]                |
     | -- "." ending DATA ---------------------> |
     | <----------------------------- 250 ------ |
     |      [timeout: read]                      |
     | -- QUIT --------------------------------> |
```

This is a simplified diagram; a real SMTP session can involve more commands/responses, multiple recipients, and different TLS modes. One send consists of **many alternating read and write operations**. Sometimes TCP opens very fast yet waiting for `250` after `DATA` takes a long time; other times the server replies quickly yet transferring an attachment over the network stalls.

| Jakarta Mail property | Applies when | Example incident | Does not represent |
| --- | --- | --- | --- |
| `mail.smtp.connectiontimeout` | Waiting to open the TCP connection | Firewall drops packets or server does not answer connect | The entire send after connection succeeds |
| `mail.smtp.timeout` | Waiting to read data from the socket | Waiting for `220`, `250`, `354`, `235` banners/replies | Time spent writing data to the network |
| `mail.smtp.writetimeout` | Writing data onto the socket | Sending body or attachment when server stops reading | Time waiting for a reply after writing finishes |

## 2. Connection Timeout — Bound When Opening a Connection

`mail.smtp.connectiontimeout` is the maximum time allowed to **establish a socket connection** to the SMTP endpoint. Example:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
```

A value of `5000` corresponds to **5 seconds**. When the app connects to `smtp.example.com:587`, the OS must complete the TCP handshake. If the network path or firewall silently drops packets, the connect call can block; connection timeout lets it break out of that state.

Situations commonly tied to connection timeout:

- SMTP server is unreachable from the app's runtime environment.
- Firewall or network policy blocks outbound TCP without sending an explicit refusal error.
- Network trouble prevents the TCP handshake from finishing in time.
- SMTP endpoint is so overloaded it cannot accept connections on time.

However, **connect timeout does not cover every step prior to receiving the email**:

- DNS lookup can happen before the connect call. A very slow DNS resolver is not necessarily bounded by `connectiontimeout`.
- Server accepted TCP yet never sends the `220` greeting: the client is **reading**, so `mail.smtp.timeout` applies instead.
- Server responds slowly after `AUTH` or `DATA`: the connection already exists, no longer in the connect phase.
- Sending an attachment stalls: that is a data-writing issue, usually not solved by connect timeout.

If the hostname is wrong, `UnknownHostException` may occur; if the port is explicitly refused, `ConnectException: Connection refused` may appear. Neither error necessarily consumes the full connect timeout milliseconds: the client can fail immediately.

**Illustrative scenario:** TCP connect finishes in 100 ms, yet the SMTP server sends no banner for 30 seconds. Even with `connectiontimeout=3000`, waiting for the banner can still drag on if `mail.smtp.timeout` is unset. Configuring connect timeout does not automatically bound everything happening after TCP opens.

## 3. Read Timeout — Bound When Waiting for a Reply

`mail.smtp.timeout` is Jakarta Mail's **socket read timeout**, typically applied via the `SO_TIMEOUT` option. Example:

```properties
spring.mail.properties.mail.smtp.timeout=10000
```

A value of `10000` means **10 seconds** for a blocked read operation while no data arrives.

SMTP is a command–response protocol: the client sends a command and usually waits for server confirmation. If a connected server becomes overloaded or unresponsive, a read call can stall for a long time.

| Stage | Data awaited | Example issue |
| --- | --- | --- |
| After TCP connect | `220` banner | Server holds connection open without greeting |
| After `EHLO` | `250` and capability info | SMTP relay responds sluggishly |
| After `STARTTLS` | Reply and TLS exchange data | TLS upgrade stalls |
| After `AUTH` | Authentication result | SMTP auth backend is slow |
| After `RCPT TO` | Recipient confirmation | Server policy checks take a long time |
| After `.` ending `DATA` | Message acceptance reply | Server takes long to scan/queue content |

At the final step, read timeout has special significance. The client may have already transmitted all content and merely be waiting for the `250` reply. If the reply fails to arrive in time, **you cannot automatically conclude the server never accepted the mail**. The server may have accepted the message while the reply was lost or delayed.

### Read Timeout Is Not a Deadline for the Entire Send

A read timeout normally bounds waiting on **a single read operation** with no data arriving. If an SMTP session performs multiple reads, total elapsed time can substantially exceed that threshold.

```text
mail.smtp.timeout = 10000 ms

Wait for banner:      8 seconds → read succeeded
Wait for EHLO:        7 seconds → read succeeded
Wait after AUTH:      9 seconds → read succeeded
------------------------------------------------
Total read time:     24 seconds
```

Even though every step was under 10 seconds, the total reached 24 seconds. A response arriving piecemeal can also stretch total duration beyond a single wait limit. Thus `mail.smtp.timeout` does not mean "the whole `send()` must finish in 10 seconds".

## 4. Write Timeout — Bound When Transmitting Data

`mail.smtp.writetimeout` limits how long a write to the SMTP socket can block:

```properties
spring.mail.properties.mail.smtp.writetimeout=10000
```

When sending an email with HTML or a PDF attachment, the library must push MIME data across the connection. If the server stops reading or network throughput drops until the socket buffer fills up, the write operation can block.

```text
Client                                         SMTP server
  |                                                |
  | -- DATA -------------------------------------> |
  | <--------------------------------- 354 ------- |
  | -- body chunk 1 ----------------------------> |
  | -- body chunk 2 ----------------------------> |
  | -- body chunk 3 ------- [blocked] -----------> |
  |                                                |
  |       writetimeout may trigger                 |
```

In this case, raising `mail.smtp.timeout` does not address the slow operation. The library is blocked **writing**, not **reading**.

In common versions of Jakarta Mail/Angus Mail, write timeout is implemented by scheduling socket closure if a write takes too long. Some implementations allocate extra scheduling/thread resources per connection, so high-volume sending systems must watch concurrent connection counts.

Write timeout is also **not** a maximum total time to upload the whole email: the body can be written in many chunks, and the OS also buffers sockets. Continuous small successful writes can let total upload time exceed `writetimeout`.

### When Does Write Timeout Commonly Occur?

- Sending large files via an SMTP relay on a distant network.
- SMTP server connects yet drains data very slowly.
- Network path or TCP flow control prevents the socket from accepting more outbound data.
- High load where many concurrent emails compete for bandwidth.

If the SMTP server explicitly returns an error because the message exceeds allowed size, that is a server protocol/policy error; increasing write timeout will not make an oversized file valid.

## 5. Spring Boot Configuration for All Three Timeouts

If the app uses `spring-boot-starter-mail` and lets Spring Boot auto-create `JavaMailSender`, add configuration to `src/main/resources/application.properties`:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

# Unit: milliseconds
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Explanation table:

| Property | Example value | Meaning |
| --- | ---: | --- |
| `mail.smtp.connectiontimeout` | 5000 ms | Wait up to ~5 seconds for TCP connect |
| `mail.smtp.timeout` | 10000 ms | Wait up to ~10 seconds for a socket read |
| `mail.smtp.writetimeout` | 10000 ms | Bound a blocked socket write to ~10 seconds |

These values are **only initial examples**, not a universal standard for every service. Tune them to network latency, SMTP provider, message sizes, and business requirements.

Specifically, Spring Boot forwards `spring.mail.properties.*` keys into the JavaMail Session. Use the exact names `mail.smtp.connectiontimeout`, `mail.smtp.timeout`, and `mail.smtp.writetimeout`; there is no single standard `spring.mail.timeout` property replacing all three.

### Equivalent in application.yml

To keep dotted Jakarta Mail property names intact inside a map, use bracketed keys:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Configuring port `587` with STARTTLS is a common case. If the provider uses **implicit TLS** on port `465`, adjust the configuration accordingly:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.auth=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Do not pick a port or TLS mode by guesswork; follow the SMTP provider's documentation. The TLS handshake can trigger socket reads/writes, yet these three properties should not be assumed to act as an absolute deadline for the entire TLS flow across all libraries/JDKs.

### If the Application Uses the smtps Protocol

Jakarta Mail property names follow the **protocol prefix**. For standard `smtp` transport config (even with SSL/TLS enabled on `smtp`), use `mail.smtp.*` as above. If the application **explicitly configures the `smtps` protocol**, the corresponding properties use the `mail.smtps.*` prefix, such as `mail.smtps.timeout`. Verify the actual protocol of `JavaMailSenderImpl` to avoid setting right values under the wrong prefix.

## 6. Configuring JavaMailSenderImpl Without Spring Boot

In a plain Spring Framework app or when configuring `JavaMailSender` manually:

```java
package example.mail;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(properties);
        return sender;
    }
}
```

These settings belong to Jakarta Mail, passed via `Properties`. If using Spring Boot auto-configuration, it is usually better to configure `spring.mail.*` rather than defining a manual bean; defining your own bean can alter Boot's auto-configuration behavior.

Timeout keys usually have **infinite defaults** in Jakarta Mail when left unconfigured, even though OS/JDK and network layers still have their own limits. Never expect the system to have three sensible bounds automatically if you leave them blank.

## 7. Timeouts in the Context of Sending Mail from a Spring Service

Example of an email-sending service:

```java
package example.mail;

import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotification(String recipient, String content) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Notification");
        message.setText(content);

        try {
            mailSender.send(message);
            // SMTP submission succeeded at the configured boundary.
        } catch (MailException ex) {
            // Record attempt and classify error at the operational layer.
            throw ex;
        }
    }
}
```

If a timeout occurs, `JavaMailSender` may throw a Spring Mail exception such as `MailSendException`; the deeper cause can come from Jakarta Mail, the TCP socket, or TLS. Never assume every timeout is wrapped in the exact same exception class or message text across versions.

| Symptom / cause | Suspected stage | Interpretation |
| --- | --- | --- |
| `SocketTimeoutException: connect timed out` | Connect | Failed to establish TCP connection within limit |
| `SocketTimeoutException: Read timed out` | Read | Waiting for data/reply over the socket |
| Socket closed or error while writing | Write | Possibly stalled sending data; server-side state unknown |
| `ConnectException: Connection refused` | Connect | Endpoint refused fast; did not necessarily exhaust connect timeout |
| `UnknownHostException` | DNS | Failed to resolve hostname |
| `SSLHandshakeException` | TLS | Wrong cert/protocol, trust issue, or TLS failure |
| SMTP response `4xx` or `5xx` | SMTP protocol | Server replied with error; not necessarily a timeout |

**Note:** A `mailSender.send(message)` call returning normally only shows that mail handoff at the SMTP hop the app connects to succeeded within that scope. It does not prove the email reached the inbox or was read.

## 8. Why Is a Read Timeout After DATA a Special Case?

Consider the scenario:

```text
Application                            SMTP relay
   |                                       |
   | -- DATA, full content, "." ---------> |
   |                                       | accepted and stored?
   | <----- 250 reply delayed/lost ------- |
   |                                       |
   | -- read timeout ------------------X   |
```

The application knows it did not receive confirmation in time, yet does not necessarily know whether the server accepted the mail. If the backend retries right away without reconciliation, the recipient may get duplicates.

A write timeout near the end of transmission can also yield an **indeterminate outcome**. A socket reporting a write error does not prove exactly how much data the server received, especially when buffers, proxies, or earlier chunks already crossed the wire.

Therefore, distinguish:

- `failed_before_submission`: evidence shows message content was not sent yet.
- `outcome_unknown`: insufficient info to know whether the SMTP server received it completely.
- `submitted_to_relay`: application received success confirmation at the SMTP hop.
- `delivered`: if the ESP provides delivery events to the receiving system, this is a **different** milestone from `submitted_to_relay`.

Standard SMTP does not give end-to-end exactly-once guarantees under all network failures. If the ESP supports **idempotency keys**, webhooks, and provider message ID lookups, combine them to curb duplicate retries. With plain SMTP, use correlation IDs, attempt history, retry policies, and business-appropriate reconciliation.

## 9. Individual Bounds Differ from Total `send()` Timeout

Suppose the configuration is:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

One send could take:

```text
TCP connect                       2 seconds
Read 220 greeting                 3 seconds
Read EHLO result                  4 seconds
TLS / AUTH                        6 seconds
Write MIME content                7 seconds
Read result after DATA            8 seconds
-------------------------------------------
Total send time                  30 seconds
```

Each individual operation stays below its respective threshold, yet the total is 30 seconds. **Never simply add `5 + 10 + 10 = 25 seconds` and treat that as a maximum SLA** for `send()`.

Beyond network operations, total job duration can also include:

- DNS resolution, TLS handshake, and proxy hops.
- Rendering HTML templates, building MIME bodies, reading attachments from disk/object storage.
- Waiting for an executor or queue to assign a thread to begin sending.
- Retrying, backoff waits, and ESP outages.

If there is a requirement that "the whole task takes no more than 20 seconds", the app needs a **job-level overall deadline/budget** alongside the three socket timeouts. Merely calling `CompletableFuture#orTimeout(...)` or `Future#get(timeout)` is not enough to guarantee the underlying socket stopped: lower-level I/O may keep running if cancellation/interruption cannot abort it. Manage threads, sockets, concurrency limits, and real cancellation together.

## 10. Choosing Appropriate Values

No fixed set of timeouts fits every system. An internal SMTP relay on a LAN, an email service over the Internet, an OTP service, and a PDF report sender have very different profiles.

| Example scenario | Connection | Read | Write | Notes |
| --- | ---: | ---: | ---: | --- |
| Stable relay near the app | 3–5 sec | 5–10 sec | 5–10 sec | Observe actual response speeds |
| ESP over the Internet | 5–10 sec | 10–20 sec | 10–30 sec | Accounts for latency and provider behavior |
| Message with large attachments | 5–10 sec | 10–30 sec | 20–60 sec | Needs separate size limits |

These ranges **illustrate starting choices only**, not SLAs or mandatory recommendations. Too-low timeouts trigger false failures during brief network slowdowns; too-high timeouts tie up threads and hurt throughput.

How to tune in practice:

1. Measure actual send latency by provider, message type, and email size; inspect p50, p95, p99.
2. Set connect timeout just high enough to detect unreachable endpoints without hanging unnecessarily.
3. Set read timeout based on actual server reply times, including post-`DATA` scanning and queuing.
4. Set write timeout accounting for network speed and the **encoded MIME message size**, which is usually larger than the raw attachment file.
5. Monitor error rates by category and tune once operational data accumulates.
6. Set concurrency limits, retry counts, and send deadlines according to content urgency.

For instance, an 8 MB PDF attachment produces a MIME message larger than the raw file once base64-encoded with headers. Hence write timeout for emails with attachments may need to differ from single-line OTP emails. Still, prioritize checking ESP size caps and avoid sending overly large files via email.

## 11. Retrying on Timeouts

Not every mail send failure should be retried the same way. A connect timeout before sending any message and a read timeout after finishing `DATA` carry very different certainty levels.

| Incident | Generally sensible handling |
| --- | --- |
| Connect timeout before transmission | Bounded retry possible; check network, firewall, host, port |
| Read timeout before `DATA` | Consider stage-aware retry; handle config errors separately |
| Read timeout after sending all `DATA` | Uncertain state; avoid blind automatic retries |
| Write timeout while sending body | Partial data may have transferred; log attempt, weigh duplicate risk |
| SMTP `4xx` | Usually temporary; retry per error code and provider policy |
| SMTP `5xx` | Usually permanent; do not retry unchanged if address/policy needs fixing |
| Wrong username/password | Fix secret/configuration; continuous retries will not resolve it |

A sound retry policy typically uses **exponential backoff with jitter**, a maximum attempt count, a reasonable delivery deadline, and an ID linking attempts. For instance, for an OTP expiring in a few minutes, the system should not retry for hours; for daily summary reports, longer delays are acceptable.

```text
notification_id = n-101
delivery_id     = d-202
attempt 1       = timeout_after_data
attempt 2       = pending_policy_or_reconciliation
delivery_result = outcome_unknown
```

For critical transactional emails, use an outbox and an ESP with event tracking to avoid dropping send requests or creating endless retries. If the server accepted the mail without the app receiving `250`, duplicates can still happen; retry policies must acknowledge that reality.

## 12. Combining Timeouts with Asynchronous Mail-Sending Architecture

If a user sends an HTTP request to place an order and the backend calls SMTP synchronously, the request can be held until the mail server replies or times out. Many requests hitting an outage together will tie up HTTP threads and degrade system responsiveness.

```text
HTTP Request
    |
    v
Order Service
    | Save order + email request record (outbox)
    v
HTTP Response
    |
    +------------------------------+
                                   |
                                   v
                           Outbox / Queue
                                   |
                                   v
                             Email Worker
                            /    |      \
                     timeout  retry   concurrency limit
                                   |
                                   v
                               SMTP / ESP
                                   |
                                   v
                      Delivery/Bounce Webhook (if available)
```

Moving email sending to a worker decouples SMTP latency from HTTP requests. Yet the worker still needs the three network timeouts:

- Limit worker/concurrency counts to avoid opening too many SMTP connections, especially since write timeouts carry per-connection thread/scheduler overhead.
- Keep the backlog bounded and monitor the age of queued jobs.
- Persist `delivery_id`, `attempt_id`, and each attempt's result for reconciliation.
- Retry in a controlled way on temporary failures; mark `outcome_unknown` if uncertain whether the server received it.
- Track `delivered` or `bounced` separately if the provider offers webhooks.

Asynchronous sending does not solve every problem on its own. If SMTP constantly times out, queues will grow rapidly without circuit breakers, backoff, retry caps, and operational alerts.

## 13. Identifying the Timeout Type During Incidents

### Scenario A — Unable to Connect to SMTP

**Symptom:** Waits roughly the connection timeout duration, then reports `connect timed out`.

**Possible causes:** Bad routing, firewall blocking port 587, Kubernetes network policy, unreachable SMTP endpoint.

**Remediation:** Check host/port, DNS, outbound firewall, and connectivity from the actual app runtime environment. Raising read timeout will not help establish TCP.

### Scenario B — Connected Successfully Yet No Banner

**Symptom:** TCP connect completes, but the app never receives `220`.

**Possible causes:** Overloaded server, stalled SMTP proxy, wrong port/TLS mode.

**Remediation:** Check read timeout and actual SMTP/TLS protocol; separate connection failures from response failures.

### Scenario C — Short Emails Work, Large Attachments Stall

**Symptom:** Sending a few lines of text works fine, while large PDF files frequently hit write timeouts.

**Possible causes:** Slow link, server stopping reads, or message size limits.

**Remediation:** Check MIME size, bandwidth, provider limits, and write timeout. If the server returns an SMTP rejection for exceeding size, do not raise write timeout as a "fix".

### Scenario D — Timeout After Finishing DATA

**Symptom:** Client finishes transmitting the email yet does not receive `250` in time.

**Possible causes:** Server processing/queuing, delayed reply, or dropped connection.

**Remediation:** Check read timeout, SMTP logs, and reconciliation data from the ESP. Treat as an **uncertain outcome** instead of assuming the email was not sent.

### Scenario E — No Exception Yet `send()` Is Very Slow

**Symptom:** Every operation stays under its individual timeout, yet total latency is 30–60 seconds.

**Possible causes:** Accumulated reads/writes, slow DNS/TLS, attachment preparation time, or thread waiting.

**Remediation:** Measure total attempt duration and each observable phase. When an overall SLA is needed, build deadlines and job management rather than tweaking a single timeout.

## 14. Logging, Metrics, and Information Boundaries

For evidence-based operations, log at the level of a **send attempt**:

| Field | Purpose |
| --- | --- |
| `delivery_id`, `attempt_id` | Correlate events and attempts |
| `smtp_host`, `smtp_port`, `provider` | Identify the failing endpoint |
| `started_at`, `elapsed_ms` | Measure total duration |
| `error_category` | Classify connect/read/write/TLS/auth/SMTP |
| `message_size_bytes` | Spot correlation between size and write timeouts |
| `retry_count`, `next_retry_at` | Monitor retry backlog |
| `submission_outcome` | Distinguish success, failed, and unknown |

Track `mail_send_duration` (p50/p95/p99), `mail_send_timeout_total` by error category, busy mail worker count, queue depth, and delivered/bounced events from the ESP if available.

Never log SMTP usernames/passwords, OTPs, tokens, full message bodies, or sensitive personal info. SMTP debug logs can aid troubleshooting, yet must be enabled narrowly with strict access control and retention limits because credentials or contents could leak depending on configuration.

Mistakes to avoid:

- Increasing `connectiontimeout` when the server already connected yet responds slowly after `AUTH`.
- Increasing `mail.smtp.timeout` when the socket is actually blocked writing an attachment.
- Setting timeouts below normal network latency, causing continuous retries and extra load.
- Assuming `timeout=10000` means the entire `send()` lasts at most 10 seconds.
- Retrying every failure immediately without accounting for the server possibly having accepted the mail after `DATA`.
- Treating a successful `JavaMailSender.send()` call as proof the email reached the inbox.

## 15. Summary Through Three Diagnostic Questions

**Has the app failed to open a TCP path to SMTP?** Check `mail.smtp.connectiontimeout`, host/port config, and network path.

**Is it connected yet receiving no reply from the SMTP server?** Check `mail.smtp.timeout`, the SMTP command stage waiting, and server responses.

**Is it transferring content when the socket stops writing?** Check `mail.smtp.writetimeout`, MIME size, link speed, and server state.

A starting point in Spring Boot could be:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Then tune using real metrics. **Connection timeout** guards opening TCP; **read timeout** guards waiting for data; **write timeout** guards transferring data. All three reduce the risk of hung I/O, while keeping an email system reliable still requires overall job time budgets, controlled retries, resource management, and send-outcome reconciliation.
