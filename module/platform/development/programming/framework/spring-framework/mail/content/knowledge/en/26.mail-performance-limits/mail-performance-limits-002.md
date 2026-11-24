# Reusing JavaMailSender and Connection Configuration

In **Spring Framework Mail**, an application might send a few emails a day or tens of thousands of notifications across multiple workers. If every email creates the entire SMTP configuration anew, instantiates `JavaMailSenderImpl`, reads secrets, configures TLS, and manages connections on its own, the system becomes difficult to manage for resource control, prone to inconsistent errors across sending threads, and hard to observe for performance.

However, "reusing JavaMailSender" is also frequently misunderstood: **reusing a `JavaMailSender` bean or Jakarta Mail `Session` does not mean every email shares a single open TCP/SMTP connection**. In standard implementations, `JavaMailSenderImpl` may open and close an SMTP `Transport` for a single `send(...)` call, whereas a call sending multiple messages may leverage one connection within the scope of that call. Connection pooling or keeping connections open across multiple calls is a separate infrastructure decision, not an automatic guarantee of Spring Mail.

This lesson explains **which objects should be reused, which objects must not be shared, where connection configuration should live, and which performance limits you need to understand**. We will distinguish MIME construction costs from SMTP connection costs, design a thread-safe singleton sender, manage multiple providers or tenants, bound concurrency/rate, measure performance, and test with an SMTP sandbox.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the roles of `JavaMailSender`, `JavaMailSenderImpl`, Jakarta Mail `Session`, `MimeMessage`, `MimeMessageHelper`, and SMTP `Transport`.
- Reuse a **Spring-managed `JavaMailSender` bean** instead of creating a new sender for every email.
- Distinguish between **sender reuse**, **session reuse**, **connection reuse**, and **batch send**.
- Configure host, port, credentials, TLS, hostname verification, and timeouts consistently.
- Understand the limitations of `send(MimeMessage...)`: it can reduce connect count, but still sends each MIME message and can encounter partial failures.
- Use a sender from multiple threads without sharing mutable `MimeMessage` objects.
- Bound concurrency, queue backlog, and send rate according to SMTP provider capacity.
- Manage multiple SMTP profiles without mutating a singleton's configuration mid-send.
- Design retry/outbox flows without unintentionally multiplying submissions.
- Verify performance and real connectivity with appropriate integration tests.

## 2. Component Diagram in Spring Mail

```text
Spring Boot application
       |
       +--> NotificationService
       |
       +--> EmailOutboxWorker
       |
       +--> Other business services
                 |
                 v
       JavaMailSender (Spring bean, shared)
                 |
                 v
       JavaMailSenderImpl
         - host / port
         - username / password
         - JavaMail properties
         - Jakarta Mail Session
                 |
                 +--> createMimeMessage()
                 |       |
                 |       v
                 |   MimeMessage (one instance per email)
                 |       |
                 |   MimeMessageHelper (tied to that message)
                 |
                 +--> send(...)
                         |
                         v
                    SMTP Transport
                         |
                    TCP / TLS / AUTH
                         |
                         v
                  SMTP relay/provider
```

Each component has a distinct lifecycle and responsibility:

| Component | Role | Typical Appropriate Usage |
|---|---|---|
| `JavaMailSender` | Spring abstraction to build and send emails | Inject and **reuse the bean**. |
| `JavaMailSenderImpl` | Sender implementation holding SMTP config and Jakarta Mail Session | Configure once at startup; share if using the same SMTP profile. |
| `jakarta.mail.Session` | Holds properties, authenticator, and JavaMail context | Can be reused by the sender; **not a TCP connection**. |
| `MimeMessage` | A specific email containing headers and MIME body | **Create a new instance per message/attempt**. |
| `MimeMessageHelper` | Helper to set From, To, Subject, HTML, inline parts, and attachments | Create a new instance tied to a `MimeMessage`. |
| SMTP `Transport` | Protocol connection to submit messages to the server | Usually managed by the sender within `send`; do not share arbitrarily across threads. |
| Outbox/queue worker | Coordinates jobs, retries, concurrency, and state | Managed independently from the sender bean's lifespan. |

**Key point:** The sender bean represents shared **configuration and sending capability**; a `MimeMessage` represents the **state of one specific email** and must not be reused or mutated by multiple threads concurrently.

## 3. Do Not Create a New JavaMailSenderImpl per Email

A common but poor pattern:

```java
public void sendNotice(String recipient, String body) {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.com");
    sender.setPort(587);
    sender.setUsername(System.getenv("SMTP_USER"));
    sender.setPassword(System.getenv("SMTP_PASSWORD"));

    Properties props = sender.getJavaMailProperties();
    props.put("mail.smtp.starttls.enable", "true");

    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(recipient);
    message.setText(body);

    sender.send(message);
}
```

Problems:
1. SMTP configuration is scattered into business code.
2. Secrets may be read and processed unnecessarily multiple times.
3. Sending paths easily diverge in TLS, hostname verification, and timeouts.
4. Tests cannot easily swap `JavaMailSenderImpl` for a mock.
5. Rotating providers/secrets has no centralized management point.
6. Readers may mistakenly think recreating the sender yields a "fresher and safer" connection, whereas a sender instance **does not directly equal** a transport connection.
7. Each sender copy may retain extra config/session objects and complicate the lifecycle without delivering real benefits.

Creating a new sender is **not necessarily** the main cause of slow SMTP; the expensive part is usually network/TLS/AUTH. However, this design introduces configuration risks and makes long-term optimization and measurement difficult.

### 3.1. The Right Way: Dependency Injection

```java
package com.example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Sending methods use the same mailSender bean.
}
```

Spring manages the sender and injects it into services/workers that need it. One SMTP profile normally only needs a single stably configured singleton bean.

### 3.2. No Need to Cache the Sender Yourself in a Static Field

Avoid:

```java
private static JavaMailSender cachedSender;
```

Static global state is usually unnecessary when you already have Spring dependency injection; it complicates testing, lifecycles, and supporting multiple profiles. Let the Spring container manage the bean and pass dependencies via constructor injection.

## 4. Lifecycle of JavaMailSenderImpl, Session, and Transport

It helps to distinguish four different actions:

```text
Application startup
      |
      v
Create JavaMailSenderImpl bean
      |
      | Configure SMTP properties once
      v
Reuse sender and its mail configuration
      |
      +--> createMimeMessage() -> message A
      +--> createMimeMessage() -> message B
      |
      v
send(message A)
      |  connect / TLS / AUTH / SMTP DATA / close*
      v
send(message B)
         connect / TLS / AUTH / SMTP DATA / close*
```

`*` Describes the typical behavior of an SMTP sender in standard implementations; verify when using custom transports or other provider APIs.

### 4.1. `Session` Is Not a Network Connection

A `jakarta.mail.Session` holds properties and configuration for Jakarta Mail. It can outlive many SMTP connections.

Therefore:
- Reusing a sender/session **does not prove** a TCP socket remains open.
- `createMimeMessage()` does not mean SMTP connect.
- `getSession()` is not a method to "borrow a connection from a pool."
- If a system observes TLS handshake counts rising with send counts, that does not contradict having only a single sender bean.

### 4.2. Each `send(...)` Is Typically One Send Cycle

In `JavaMailSenderImpl`, SMTP sending typically involves obtaining a `Transport`, connecting if not already connected, sending each MIME message, and closing the transport when the operation finishes. Exact details depend on the Jakarta Mail/Spring version and configuration.

Do not assume that:

```java
sender.send(first);
sender.send(second);
```

will reuse **the same SMTP TCP connection** across both calls.

### 4.3. Sending Multiple Messages in One Call Makes a Difference

```java
sender.send(first, second);
```

This may allow the sender implementation to reuse the `Transport` within the scope of the same multi-message send call. That can reduce connect/TLS/AUTH overhead compared to two separate calls.

However:
- `first` and `second` are still **two MIME messages**;
- each message still has its own SMTP envelope/DATA;
- the result can be partially successful;
- there is no guarantee the provider keeps the connection open throughout the entire batch;
- it does not automatically create a shared session/pool for subsequent calls.

This is an optimization that requires measurement and error-handling design, not a "batch as many messages as possible" rule.

## 5. Centralized JavaMailSender Configuration in Spring Boot

With `spring-boot-starter-mail`, Spring Boot can auto-configure `JavaMailSender` when auto-configuration conditions and SMTP properties are met.

### 5.1. STARTTLS on Port 587

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

Meaning:
- `host/port`: SMTP endpoint published by the provider.
- `username/password`: credentials loaded from configuration/secret store.
- `default-encoding`: default encoding Spring applies where appropriate.
- `starttls.enable=true`: use STARTTLS when supported by the endpoint.
- `starttls.required=true`: fail if the server cannot upgrade to TLS.
- `ssl.checkserveridentity=true`: verify hostname against the SMTP server's certificate.
- `connectiontimeout`: time limit to establish the TCP connection.
- `timeout`: time limit to read data from the socket.
- `writetimeout`: time limit to write data to the socket.

The timeouts in this example are in **milliseconds** per Jakarta Mail SMTP properties, not seconds. Illustrative numbers must be tuned for network latency, message size, and SLA.

### 5.2. Implicit TLS on Port 465

If the provider requires TLS from the start of the connection:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

STARTTLS and implicit TLS **differ in how the connection is initiated**. Do not enable `mail.smtp.ssl.enable=true` on a port expecting EHLO/STARTTLS, and do not enable only `starttls.enable` for an implicit TLS port.

### 5.3. Why Are Timeouts a Performance Issue?

An SMTP connection can hang when:
- DNS/TCP/connect encounters issues;
- the TLS handshake is slow;
- the server stops responding to SMTP commands;
- network read/write speed drops;
- sending large attachments over a slow link.

If default timeouts are too long or unbounded by infrastructure, workers can hold onto resources and fail to process other jobs. If timeouts are too short, the application generates false failures and more retries, increasing traffic and risking duplicate sends when outcomes are ambiguous.

**Timeouts must be coordinated with concurrency limits, job leases, retry policies, and email sizes.** Do not choose these values independently.

### 5.4. Do Not Allow Fallback to Plaintext

If the provider requires STARTTLS, `starttls.required=true` is a fail-closed safeguard. Do not remove `required` to "go faster" or "avoid handshake errors," because doing so can leave authentication and message contents unprotected.

Performance optimization must never trade away TLS server verification, hostname checking, or credential protection.

## 6. Manual Sender Configuration in Spring Framework

Not every application uses Boot auto-configuration. You can declare the bean explicitly:

```java
package com.example.mail;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender =
            new JavaMailSenderImpl();

        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
```

This example illustrates configuration and lifecycle. In production:
- Do not hardcode credentials.
- Inject configuration properties/secret manager values instead.
- Do not log environment variables containing secrets.
- Do not create redundant duplicate senders if Boot already configures the right one.
- If the application needs multiple senders, name each bean/profile explicitly.

### 6.1. Why Not Mutate Properties Right Before Each Send?

Avoid writing:

```java
sender.setHost(tenantSmtpHost);
sender.setUsername(tenantUsername);
sender.setPassword(tenantPassword);
sender.send(message);
```

on **a singleton shared across multiple threads**.

Two requests can interleave:
- Thread A sets tenant A's username.
- Thread B sets the username to tenant B.
- Thread A sends using B's configuration.

This both causes deliverability errors and can leak data/credentials across tenants. Configure a stable sender per profile or build a sender-selection abstraction with controlled isolation, rather than mutating a global bean mid-send.

### 6.2. Configuration Is a Snapshot

After startup, treat a shared `JavaMailSenderImpl`'s configuration as **operationally near-immutable**:
- host/port;
- username/secret;
- TLS mode;
- SMTP properties;
- default encoding.

When secrets or providers must rotate, execute a controlled refresh procedure, replace config/bean instances per lifecycle rules, and avoid concurrent mutation on a sender actively processing emails.

## 7. Create a New MimeMessage and MimeMessageHelper for Each Email

Reuse the sender, but **do not reuse message objects**.

Correct:

```java
public void sendNotice(String recipient, String body)
        throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Notification");
    helper.setText(body, false);

    mailSender.send(message);
}
```

Avoid:

```java
// Do not keep a mutable MimeMessage as a field of a singleton service.
private MimeMessage currentMessage;

// Do not share a MimeMessageHelper across multiple threads.
private MimeMessageHelper sharedHelper;
```

### 7.1. Why Is MimeMessage Unsuitable for Sharing?

`MimeMessage` holds mutable state:
- `From`, `To`, `Cc`, `Bcc`;
- subject;
- content, multipart parts;
- headers;
- encoding metadata;
- attachment/inline references.

If two threads mutate the same message, the email can be sent to the wrong recipient, with the wrong body or attachment. This is a correctness and security issue, not merely a performance one.

### 7.2. Retries Should Also Create a New Message

For retries:
- Keep an **application message key** to correlate attempts.
- Generate a **new attempt ID** for each retry attempt.
- Build a fresh `MimeMessage` from stored/frozen data according to policy.
- Do not reuse a message that was just mutated by transport or is being used by another thread.

If email content relates to a transaction, decide explicitly whether retry rendering uses a snapshot from event creation time or the latest data. That affects consistency far more than the cost of instantiating `MimeMessage`.

### 7.3. Headers and Content Should Be Added in One Clear Build Pass

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plainText, htmlText);

message.setHeader(
    "X-Application-Message-Key",
    messageKey
);

mailSender.send(message);
```

With inline resources, `setText(...)` is normally called before `addInline(...)`. The MIME structure is built per message; sharing the sender does not change this ordering.

## 8. Concurrent Sending: Sharing a Sender Bean vs. Sharing a TCP Socket

A Spring singleton sender can be injected into multiple services or background workers. In normal usage, **each send call owns its own message**, while the SMTP transport is handled by the sender/Jakarta Mail during each send cycle.

```text
Worker A --- MimeMessage A ---+
                              |
Worker B --- MimeMessage B ---+--> shared JavaMailSender bean
                              |        |
Worker C --- MimeMessage C ---+        +--> SMTP submission A
                                       +--> SMTP submission B
                                       +--> SMTP submission C
```

Do not infer that:
- the three workers definitely share one socket;
- there is only one connection because there is only one bean;
- increasing thread count increases throughput linearly;
- creating a singleton sender automatically limits concurrency.

### 8.1. Do Not Share One Transport Across All Threads

If managing low-level SMTP `Transport` manually, keeping one long-lived transport may look like a connection-pooling optimization. However, it introduces many problems:
- `connected/disconnected` state changes;
- the server may close idle connections;
- multiple threads can interleave SMTP commands;
- an error in one send affects another;
- reconnection and TLS/AUTH must be handled;
- shutdown must close the socket;
- shared `Transport` lacks general thread-safety guarantees.

Do not create a static `Transport` and share it freely across threads. If you genuinely need a separate connection-management layer, you must explicitly design ownership, synchronization, health checks, timeouts, reconnection, and test against a real server. That is a new component with maintenance cost, **not an automatic feature of JavaMailSender**.

### 8.2. A Bean Is Not a Connection Pool

`JavaMailSenderImpl` is an SMTP sender abstraction, not a generic connection pool library with parameters like `maxActive`, `maxIdle`, and `borrowTimeout` guaranteed by Spring Mail.

If pooling is needed, you must:
- verify whether the specific implementation supports it and check its contract;
- understand server/provider limits on concurrent connections;
- prove via benchmarks that handshake/connect is actually the bottleneck;
- implement stale-connection detection and reconnection;
- ensure SMTP transactions do not interleave.

In many applications, **bounded concurrency + queues + shared sender config** is simpler and safer than building a custom SMTP transport pool.

## 9. Batch Send: One Call Containing Multiple MIME Messages

Spring `JavaMailSender` provides overloads to send one or multiple messages.

```java
MimeMessage a = createMessageFor("a@example.net");
MimeMessage b = createMessageFor("b@example.net");
MimeMessage c = createMessageFor("c@example.net");

// A single send call with three messages.
mailSender.send(a, b, c);
```

`createMessageFor(...)` is an application-defined helper, not a Spring API.

### 9.1. Batching Can Reduce Connection Overhead

With common SMTP implementations of `JavaMailSenderImpl`, the sender may reuse the same `Transport` within the scope of one `send(MimeMessage...)` call, reducing the number of:
- TCP connects;
- TLS handshakes;
- SMTP EHLOs;
- AUTH rounds.

However, each message still goes through its own envelope and DATA.

```text
One transport connection
  |
  +--> MAIL FROM / RCPT TO / DATA for message A
  |
  +--> MAIL FROM / RCPT TO / DATA for message B
  |
  +--> MAIL FROM / RCPT TO / DATA for message C
  |
  +--> close
```

Whether the connection can be reused across the whole batch depends on whether the transport connection stays healthy and how the sender implementation handles errors.

### 9.2. A Batch Is Not One SMTP Message with Multiple Recipients

These two approaches are different:

**Three MIME messages:**

```java
mailSender.send(messageA, messageB, messageC);
```

Each message has its own content/recipient/Message-ID.

**One MIME message sent to multiple recipients:**

```java
helper.setTo(new String[] {
    "a@example.net",
    "b@example.net",
    "c@example.net"
});
mailSender.send(oneMessage);
```

The second approach is a single message with multiple recipients, leading to privacy issues (recipients see the To/Cc list) and partial recipient acceptance issues. For personalized emails, each recipient usually needs a separate message.

### 9.3. Do Not Make Batches Too Large

A batch of several thousand MIME messages can:
- hold large amounts of content/attachments in the heap;
- prolong a single send call, making timeouts/worker leases hard to enforce;
- make partial success classification and per-item outcome persistence difficult;
- hit mid-batch server disconnects or rate limits;
- block a test/production request for too long;
- apply backpressure at the wrong layer if the batch waits to accumulate enough items before sending.

There is no **universal optimal batch size** for all providers. Choose based on email size, connection latency, throughput, and per-message state observability.

### 9.4. When Is Batching Appropriate?

Consider it if:
- multiple messages use the **same SMTP profile**;
- payload sizes are moderate;
- partial failures can be managed;
- connect/TLS/AUTH overhead needs reduction;
- the provider does not prohibit or throttle batches by policy;
- the queue worker still persists durable per-message state.

It is not necessarily appropriate when:
- send requests differ by tenant/credentials;
- emails are very large or carry heavy attachments;
- each email has very different deadlines;
- per-job retry/tracing is needed and the batch API complicates it;
- the provider already offers a more efficient HTTP bulk API or dedicated batching mechanism.

## 10. Partial Failure in a Batch

A call like:

```java
mailSender.send(messageA, messageB, messageC);
```

does not mean all three messages succeed or fail together atomically.

For example:

```text
Message A -> SMTP_ACCEPTED
Message B -> SMTP_ACCEPTED
Message C -> rejected
```

If the worker simply catches an exception and retries **the entire batch**, A and B can be sent a second time.

### 10.1. Record Outcomes per Message

For each logical email, maintain:
- message key;
- attempt ID;
- recipient reference;
- outcome;
- timestamp;
- provider/SMTP metadata if available.

Spring's `MailSendException` can provide failed messages and nested exceptions on some sending paths. How successful/unsent recipients are retrieved also depends on Jakarta Mail and transport settings. Never assume a generic `MailException` always supplies enough data to separate all outcomes deterministically.

### 10.2. UNKNOWN Can Still Occur

If the connection drops **after the server may have received DATA** but before the application receives the response, a message's outcome can be `UNKNOWN`. An interrupted batch requires recording separate states for messages confirmed accepted, not yet attempted, and of unknown outcome.

In systems where exact per-email status matters more than handshake count, sending **one email per outbox attempt** is often easier to manage. If optimizing with batching, you must run failure-injection tests and establish a clear reconciliation policy.

### 10.3. Do Not Fabricate Fake Exactly-Once with a Message Key

A custom header like:

```java
message.setHeader("X-Application-Message-Key", messageKey);
```

helps tracing, but generic SMTP **does not automatically deduplicate** just because two messages share a header. A timeout + retry can still create duplicate emails. Server-side idempotency requires an API/provider mechanism that genuinely supports it and must obey their expiration/scope rules.

## 11. Sizing Concurrency and Backpressure

System throughput does not depend only on the number of sender objects. It is affected by:
- TCP/TLS/AUTH latency;
- SMTP command and provider latency;
- MIME/attachment sizes;
- network bandwidth;
- concurrent connections permitted by the provider;
- per-minute/per-second/daily quotas;
- template rendering and database query capacity;
- worker thread count;
- retry policies and mail backlog.

An intuitive model:

```text
Active workers
     ×
Messages/second per worker
     ≈
Maximum submission rate before limits apply
```

This is only an estimate. In practice, many workers wait on the network simultaneously; throughput hits a ceiling at provider quotas, CPU, network, or other resources.

### 11.1. More Threads Do Not Guarantee Faster Sending

For instance, suppose a provider allows a low number of concurrent SMTP connections. Raising workers from 5 to 100 can cause:
- more TCP/TLS handshakes;
- `421`, `451`, or rate limits;
- timeouts;
- retry storms;
- higher CPU/heap/socket usage;
- degraded provider reputation or exhausted quotas.

**Bound concurrency** on the worker side according to benchmark data and provider limits.

### 11.2. Bounded Queues and Bounded Executors

Never push unbounded messages directly into an unbounded `ExecutorService` hoping SMTP will keep up. Maintain:
- a durable outbox/queue;
- bounded concurrent senders;
- a rate limiter if the provider enforces rate caps;
- queue backlog monitoring;
- retry schedules and max attempts;
- a drop/dead-letter policy or alerts when backlog exceeds SLA.

```text
Business events
      |
      v
Durable outbox
      |
      v
Due-job dispatcher
      |
      v
Bounded worker concurrency
      |
      v
JavaMailSender
      |
      v
SMTP provider (quota + rate limit)
```

### 11.3. Rate Limits and Concurrency Are Different Concepts

- **Concurrency limit:** maximum sends in flight at the same moment.
- **Rate limit:** maximum submissions within a time window.
- **Retry budget:** how many times and over what window an email can be retried.

You can stay within concurrency limits and still violate rate limits if each send finishes quickly. Coordinate all three.

### 11.4. Preventing Retry Storms

If a provider is down for 2 minutes, thousands of jobs can become due for retry at once. Do not let them all open connections in the very first second the provider recovers.

Use:
- exponential backoff;
- jitter;
- concurrency limits;
- rate limiting;
- circuit breakers;
- dead-lettering after budget exhaustion or permanent failures;
- distinguishing `UNKNOWN` outcomes that must not be blindly retried.

## 12. Timeouts You Must Understand Properly

Three common properties:

| Property | Purpose | Risk If Too Low | Risk If Unreasonable |
|---|---|---|---|
| `mail.smtp.connectiontimeout` | Wait time for socket connection | False failures on slow networks | Workers hang during connect; backlog grows |
| `mail.smtp.timeout` | Wait time for socket reads | Timeouts when relay responds slowly | Workers wait too long when server stops responding |
| `mail.smtp.writetimeout` | Wait time for socket writes | Failures when transmitting large messages/attachments | Write stalls tie up resources |

Values are in milliseconds per the Jakarta Mail SMTP implementation. Write-timeout implementation details may carry auxiliary thread/timer/socket overhead depending on library/version; under very high concurrency, benchmark rather than assuming it is free.

### 12.1. Timeouts Are Not the Total Email Deadline

The three socket timeouts do not necessarily cap the **total time** across MIME construction + DNS + multiple SMTP commands + retries + callbacks. A request can traverse multiple sequential stages, each with its own timeout.

If an SLA requires processing within 30 seconds, enforce deadlines at the orchestration layer, worker claim/lease, and retry policy in addition to socket timeouts.

### 12.2. Lease Timeouts Must Match Network Behavior

Example:
- socket read timeout: 30 seconds;
- worker lease: 10 seconds;
- worker does not renew the lease;
- SMTP relay responds after 20 seconds.

A second worker can reclaim the job before the first worker finishes sending. That creates a duplicate submission risk.

Solutions can include:
- leases longer than a reasonable send limit;
- controlled heartbeat/lease renewal;
- fencing tokens when writing DB outcomes;
- `UNKNOWN` status when ownership is lost and the outcome is unclear;
- provider idempotency if available.

**A fencing token only protects database updates**; it cannot recall an email already accepted upstream.

### 12.3. Timeout Does Not Mean SMTP Rejected

If a timeout occurs after the application has sent all of `DATA` without receiving a response, you cannot assume the relay did not receive the message. Record the attempt as `UNKNOWN` and reconcile via provider logs/webhooks, especially before retrying automatically.

This is the boundary between **performance optimization** and **correctness of side effects**.

## 13. Connection Configuration for Multiple SMTP Profiles

A product might have:
- transactional emails via relay A;
- marketing emails via relay B;
- internal alert emails via relay C.

Each profile differs in:
- host/port/TLS mode;
- sender identity;
- username/secret;
- quota/concurrency;
- envelope sender and DKIM/domain authentication;
- timeout/retry rules;
- logging/monitoring.

Do not **mutate a singleton sender** before each send to switch from A to B.

### 13.1. Two Separate Beans with Qualifiers

Example profile-based configuration:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MultipleMailSenderConfig {

    @Bean("transactionalSender")
    JavaMailSender transactionalSender(
            TransactionalMailProperties config) {
        return MailSenderFactory.create(config);
    }

    @Bean("marketingSender")
    JavaMailSender marketingSender(
            MarketingMailProperties config) {
        return MailSenderFactory.create(config);
    }
}
```

`TransactionalMailProperties`, `MarketingMailProperties`, and `MailSenderFactory` are application-defined classes used to apply configuration, not built-in Spring Mail APIs. The factory must configure TLS/timeouts/credentials for each profile.

Explicit injection:

```java
@Service
public class TransactionalEmailService {

    private final JavaMailSender sender;

    public TransactionalEmailService(
        @Qualifier("transactionalSender")
        JavaMailSender sender) {
        this.sender = sender;
    }
}
```

If multiple `JavaMailSender` beans exist, use `@Qualifier` or an explicit selection convention; never let autowiring accidentally pick the wrong provider.

### 13.2. Per-Tenant Profiles

In a multi-tenant system:
- allow only pre-configured/verified sender profiles;
- isolate secrets and domain identities;
- never let a tenant specify arbitrary SMTP host/port from a request;
- prevent SSRF/credential exfiltration;
- enforce per-tenant/per-provider rate limits;
- never let a tenant send from an unverified `From` domain;
- avoid unbounded per-tenant sender caches without eviction/lifecycle policies.

In cases with thousands of tenants, one static sender bean per tenant may not scale. In that case, use a controlled profile registry/credential resolver, a bounded sender pool/cache, or switch to a provider API supporting tenant delegation. **Never sacrifice isolation by mutating a singleton shared across requests.**

### 13.3. Secret Rotation

When SMTP credentials change:
1. Provision the new secret in the secret manager.
2. Validate the new configuration with the provider.
3. Roll out the new sender/profile or refresh via a safely designed mechanism.
4. Shift traffic in a controlled manner.
5. Revoke the old secret after confirming old workers no longer need it.

If thread A is sending using the old sender, do not overwrite the sender's password field mid-handshake/AUTH. Changing credentials while active can cause hard-to-reproduce errors; define ownership and lifecycle clearly for sender instances.

## 14. Connection Configuration and Security Must Go Together

Performance optimization must not skip:
- `STARTTLS` required on endpoints requiring STARTTLS.
- Implicit TLS on the proper port.
- Hostname verification.
- Valid truststore/CA.
- Authentication mode per provider.
- Protection and rotation of secrets.
- Restricting `From`/envelope sender to authorized domains.
- Never logging AUTH commands, passwords, or raw MIME containing sensitive data.

### 14.1. Example of an Unsafe Configuration

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail:
        smtp:
          starttls:
            enable: true
          ssl:
            trust: "*"
```

`trust=*` is an option you should not use to bypass the trust chain; omitting `starttls.required` may permit non-TLS fallback depending on server/transport behavior. Never treat these as optimizations to "reduce send errors."

### 14.2. SMTP AUTH Differs from Domain Authentication

Succeeding at SMTP login does not prove the email passes SPF/DKIM/DMARC at the receiver. Those mechanisms depend on DNS, envelope sender, DKIM signing, and `From` domain. Reusing a sender bean does not change those domain authentication requirements.

### 14.3. Proximity to the Server Does Not Mean Dropping TLS

An internal SMTP relay in the same VPC may have its own transport policy, but never assume internal networks are automatically safe or skip server identity verification. Follow organizational infrastructure, certificate, and egress-control policies.

## 15. Designing an Efficient and Testable Email Sending Service

A service focused on **building a new message** and then invoking an injected sender:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReceiptMailer {

    private final JavaMailSender mailSender;

    public ReceiptMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String orderId,
            String plainText,
            String htmlText) throws MessagingException {

        MimeMessage message =
            mailSender.createMimeMessage();

        MimeMessageHelper helper =
            new MimeMessageHelper(
                message, true, "UTF-8"
            );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject(
            "Order confirmation " + orderId
        );
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }
}
```

Characteristics:
- `JavaMailSender` is a configured, shareable dependency.
- Each call creates a fresh `MimeMessage`.
- Content uses an explicit charset.
- SMTP connection lifecycle is managed by the sender/transport.
- The service does not store recipient/subject in shared mutable fields.
- The sender can be replaced with a mock in unit tests.

### 15.1. Do Not Send SMTP Directly Inside a Long Business Transaction

If SMTP is called inside an order-update transaction, a slow network call can hold database locks for a long time. If SMTP accepts the message and the transaction then rolls back, the email has still gone out while the business data was not committed.

For critical emails:
- commit the business event + outbox item in the same database transaction;
- have a worker send after commit;
- persist attempts and outcomes in short transactions;
- tune concurrency/timeouts at the worker layer.

### 15.2. Do Not Automatically Mark Delivered After Send

`mailSender.send(message)` returning without an exception only indicates that the submission action completed according to the interface/transport; it does not prove the recipient saw the email. Use `SMTP_ACCEPTED` or an equivalent state, and use provider events to track delivery if available.

## 16. Outbox Worker and Limiting Concurrent Sends

One architecture:

```text
OrderService / BillingService
            |
            v
       Database outbox
            |
            v
       Due-job dispatcher
            |
            v
       Bounded worker slots
            |
            v
       ReceiptMailer
            |
            v
       Shared JavaMailSender
            |
            v
       SMTP relay
```

The worker should:
1. Atomically claim a due job with lease/fencing.
2. Build a new MIME message.
3. Send via the injected sender.
4. Record `SMTP_ACCEPTED` when the transport reports success.
5. Classify temporary/permanent/unknown errors.
6. Retry with backoff/jitter and max attempts.
7. Move to a dead-letter queue or reconcile when needed.

A shared sender **does not replace** worker count limits. Limits belong in the executor/dispatcher, queue consumer concurrency, or rate limiter.

### 16.1. Example Concurrency Limit with Semaphore

A coordination layer can use a semaphore to bound concurrent in-flight sends:

```java
import java.util.concurrent.Semaphore;

import org.springframework.mail.javamail.JavaMailSender;

public final class BoundedMailSubmission {

    private final JavaMailSender sender;
    private final Semaphore slots;

    public BoundedMailSubmission(
            JavaMailSender sender,
            int maxConcurrentSends) {

        if (maxConcurrentSends < 1) {
            throw new IllegalArgumentException(
                "maxConcurrentSends must be positive"
            );
        }

        this.sender = sender;
        this.slots = new Semaphore(maxConcurrentSends);
    }

    public void send(MimeMessage message)
            throws InterruptedException {

        slots.acquire();
        try {
            sender.send(message);
        } finally {
            slots.release();
        }
    }
}
```

In the code above, `jakarta.mail.internet.MimeMessage` must be imported. If the thread is interrupted while waiting for a slot, the caller should preserve interrupt status or handle it appropriately so the job is not lost.

This example illustrates **concurrency limits within one process**. With multiple instances/pods, each instance has its own semaphore, so total concurrency still scales with replica count. If the provider enforces an account-wide limit, you need **distributed rate/concurrency control** or explicit quota partitioning across instances.

### 16.2. Do Not Just Block Indefinitely

`Semaphore.acquire()` can wait indefinitely if queues or the system are overloaded. For synchronous APIs, use a bounded wait or return an accepted-to-queue status; for workers, cap worker count right at the dispatcher.

Do not spawn unbounded threads just to wait on a semaphore. Limit upstream and use a durable queue.

## 17. Correctness When Multiple Workers Share a Sender

Reusing a bean is generally safer if:
- the sender is configured before startup and config is not mutated during sends;
- every request creates a fresh `MimeMessage` and helper;
- the template renderer does not retain shared mutable content;
- attachment resources have proper lifecycles;
- exception/error handling is isolated per attempt;
- rate/queue limits are enforced outside the sender;
- low-level SMTP `Transport` is not shared manually;
- callbacks/sender profiles are not swapped across tenants.

### 17.1. Is Synchronizing Every Send the Solution?

You might see:

```java
synchronized (mailSender) {
    mailSender.send(message);
}
```

Synchronizing like this **forces every call to run sequentially within the same process**, which can make throughput very low. Nor does it solve timeouts, provider quotas, retries, or multi-instance concurrency.

Only serialize sends if there is a specific, verified transport/design requirement. Normally, structured concurrency limits are far more flexible than locking the entire sender.

### 17.2. One JavaMailSender for Many Services Does Not Mean One Shared Message

Correct:

```text
BillingService -----+
AccountService -----+--> same JavaMailSender bean
AlertService -------+       |
                            +--> independent MimeMessages
```

Wrong:

```text
BillingService -----+
AccountService -----+--> same static MimeMessage
AlertService -------+       |
                            +--> fields overwritten concurrently
```

## 18. Attachments, Inline Resources, and Memory Cost

When a sender handles emails with attachments, performance risks often lie in the **MIME data**, not the sender bean.

For example:
- 100 concurrent emails, each attaching 20 MiB.
- If the application holds byte arrays in the heap, memory used by attachments can be huge, not counting MIME serialization buffers and overhead.
- Base64 transfer encoding typically expands the wire payload by roughly one third before line wrapping and MIME overhead.
- Bandwidth and write timeouts can become bottlenecks.

### 18.1. Choose a Re-readable Attachment Source

`MimeMessageHelper.addAttachment(...)` typically accepts an `InputStreamSource` or `File` depending on the overload. If the content is read during MIME serialization, the stream may need to be reopened.

For small data:

```java
byte[] bytes = createCsvBytes();

helper.addAttachment(
    "report.csv",
    new ByteArrayResource(bytes),
    "text/csv; charset=UTF-8"
);
```

`ByteArrayResource` works well when bytes are already in memory and can produce a fresh `InputStream`. For large attachments, however, retaining hundreds of `byte[]` arrays can exhaust heap; consider file/object storage references with re-readable streams, proper permissions, and explicit cleanup.

### 18.2. Do Not Share a Mutable Attachment Stream

Do not hold a single-use `InputStream` in a singleton service and attach it to multiple emails. If multiple sends read the same stream, content can be truncated, throw I/O errors, or fail to re-serialize on retry.

Choose a resource capable of opening a new stream for each read; verify the lifetime of the file or object in storage throughout the send/retry window.

### 18.3. Template Caching Differs from Sender Caching

Compiled templates can be cached if the template engine supports it and is concurrency-safe, but **do not cache rendered MIME containing personal data** for reuse across multiple recipients. Separate:
- template definition/cache;
- per-message render data;
- per-message MIME object;
- SMTP configuration bean.

## 19. Observe Performance Before Optimizing

Without measurement, it is easy to optimize the wrong bottleneck.

Stages to measure separately:

```text
enqueue time
   |
   v
queue wait
   |
   v
worker claim
   |
   v
render template
   |
   v
build MIME / attachment access
   |
   v
SMTP connect + TLS + AUTH
   |
   v
SMTP envelope + DATA
   |
   v
persist submission outcome
   |
   v
provider delivery events (if available)
```

Useful metrics:

| Metric | Meaning |
|---|---|
| `mail_outbox_backlog` | How many logical emails are waiting to be processed |
| `mail_queue_wait_seconds` | Latency from enqueue to worker claim |
| `mail_render_duration_seconds` | Time to render template/content |
| `mail_mime_build_duration_seconds` | Time to build MIME/attachments |
| `mail_smtp_submit_duration_seconds` | Time for sender to execute one submission |
| `mail_smtp_connect_failures_total` | Connection failure count |
| `mail_smtp_timeouts_total` | Timeout count by category |
| `mail_smtp_auth_failures_total` | Credential/auth failure count |
| `mail_smtp_attempts_total` | Attempt count, broken down by outcome |
| `mail_retry_wait_count` | Jobs waiting for retry |
| `mail_dead_letter_count` | Jobs stopped from automatic retries |
| `mail_unknown_outcome_count` | Jobs needing reconciliation |
| `mail_attachment_bytes` | Distribution of attachment sizes |
| `mail_active_sends` | Number of in-flight SMTP submissions |

### 19.1. Distinguish API Latency from Delivery Latency

If an API only writes to an outbox and returns `202 Accepted`, HTTP latency may be low even when the SMTP provider is slow. Therefore measure:
- API outbox commit time;
- queue wait time;
- time to SMTP accepted;
- time to provider delivered/bounced if available.

Do not treat a successful HTTP response as proof that the email has been sent or landed in the Inbox.

### 19.2. Do Not Log Raw MIME to Measure Performance

Structured logs can contain:

```json
{
  "event": "mail.smtp_submission",
  "messageKey": "msg-8c21",
  "attemptId": "att-2",
  "profile": "transactional",
  "outcome": "SMTP_ACCEPTED",
  "durationMs": 842,
  "attachmentCount": 1
}
```

Never log:
- SMTP username/password;
- bearer tokens/app passwords;
- full email bodies, attachment bytes/Base64;
- reset/verification tokens;
- unnecessary personal information.

Message key and attempt ID fields allow tracing without collecting message contents.

## 20. Benchmarking the Right Question

A useful benchmark compares options under identical conditions:
- One sender bean vs. creating a new sender each time.
- Sending one message per `send` vs. small `send(MimeMessage...)` batches.
- Worker concurrency 1, 4, 8, 16 against the same test provider.
- Small vs. large attachments.
- STARTTLS vs. implicit TLS if the provider supports both on appropriate endpoints.
- Connections close to vs. far from the application network.
- Running against a controlled test server/proxy rather than blasting unexpected load at a production provider.

### 20.1. Controlling Variables When Benchmarking

Keep fixed:
- MIME type and message size;
- SMTP host/port;
- TLS/AUTH;
- network path;
- JDK, Spring Mail/Jakarta Mail versions;
- message count;
- warmup;
- rate/provider quotas;
- memory/CPU limits;
- error and retry conditions.

Distinguish:
- throughput in submissions/second;
- p50/p95/p99 latency;
- number of connections/TLS handshakes;
- CPU, heap, and GC;
- SMTP 4xx/5xx counts;
- network bytes and bytes sent per message.

Do not extrapolate that a localhost measurement implies matching speedup over a real provider network path.

### 20.2. When Does Batching Truly Help?

If most time is spent in connect/TLS/AUTH, small batches can help. If most time is uploading large attachments or hitting provider rate limits, reducing connection count may have little effect.

Also evaluate partial failure risks and outbox correctness. Sometimes the added complexity to save a few handshakes is not worth the harder retry management.

## 21. Testing JavaMailSender Reuse Without a Real SMTP Server

Unit tests can verify the service **uses the injected sender** and creates a new message per request.

Example using Mockito:

```java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.mockito.ArgumentCaptor;

import java.util.Properties;

class ReceiptMailerTest {

    @Test
    void buildsSeparateMessagesUsingInjectedSender()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);

        MimeMessage first = new MimeMessage(
            Session.getInstance(new Properties())
        );
        MimeMessage second = new MimeMessage(
            Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage())
            .thenReturn(first, second);

        ReceiptMailer service = new ReceiptMailer(sender);

        service.send(
            "a@example.net", "ORD-A",
            "Content A", "<p>Content A</p>"
        );

        service.send(
            "b@example.net", "ORD-B",
            "Content B", "<p>Content B</p>"
        );

        ArgumentCaptor<MimeMessage> captured =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(2))
            .send(captured.capture());

        assertThat(captured.getAllValues())
            .containsExactly(first, second);

        assertThat(first).isNotSameAs(second);
    }
}
```

This test:
- does not require an SMTP server;
- checks that each call creates a separate message;
- does not prove TCP reuse or TLS handshake count;
- should not be called a connection-performance benchmark.

### 21.1. Testing Content Without Actually Sending

You can call `saveChanges()` on the captured message, then read `getSubject()`, recipients, and traverse MIME parts to verify plain/HTML/attachments.

If the goal is content verification, use a real in-memory `MimeMessage` instead of mocking the MIME object itself. Still, that remains a test at the I/O boundary and does not validate SMTP transport.

## 22. Integration Testing with an SMTP Sandbox

To test in reality:
- host/port configuration;
- TLS mode;
- connection/handshake;
- SMTP AUTH;
- send duration;
- batch behavior;
- errors when the server closes connections;
- partial failures

you need an SMTP test server or provider sandbox.

### 22.1. What Are GreenMail/Mailpit Used For?

An SMTP sandbox can receive MIME messages without forwarding them to Internet recipients. Depending on the tool, you can inspect:
- number of received messages;
- headers;
- body;
- recipients;
- timestamps;
- SMTP commands and connections to the extent supported by the tool.

GreenMail or Mailpit is useful for happy-path integration. Not every server supports returning custom faults at each SMTP phase; use a dedicated fault-injecting SMTP relay when testing reconnects, 421/451/550, or disconnects after DATA.

### 22.2. Configuring a Separate Test Sender

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();

sender.setHost("127.0.0.1");
sender.setPort(testSmtpPort);
sender.getJavaMailProperties().put(
    "mail.smtp.connectiontimeout", "3000"
);
sender.getJavaMailProperties().put(
    "mail.smtp.timeout", "3000"
);
```

`testSmtpPort` is the port provided by the test server. A test environment might omit TLS/AUTH for basic MIME submission checks, but you must have another integration test suite simulating the **exact TLS mode and certificate verification** if required in production.

### 22.3. What Should Be Verified About Connection Reuse?

Tests can record the number of TCP connections/SMTP sessions on the test server when:
1. Sending two messages via two separate `send` calls.
2. Sending the same two messages via one `send(first, second)` call.
3. Sending multiple messages concurrently from one singleton sender.
4. Forcing the server to close the connection mid-batch.
5. Having the server delay replies to test timeouts and worker leases.

Do not hardcode the assumption "using a singleton guarantees exactly one connection." Measure the actual implementation, library versions, and provider configuration your project intends to use.

### 22.4. Distinguish Transport Tests from Database Workflow Tests

- SMTP tests verify connectivity and that the server sees the message.
- Outbox integration tests verify states, transactions, retries, concurrency, and dead-lettering.
- End-to-end provider tests verify delivery/webhooks/domain authentication if needed.

Never run a test sending to localhost and conclude the production system has exactly-once email delivery.

## 23. Common Issues and How to Handle Them

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Each email opens a new SMTP connection despite singleton sender | `send` manages `Transport` per call | Measure connection lifecycle; consider small batches if appropriate. |
| Throughput does not rise when adding workers | Provider quota/rate, network, attachments, or DB bottleneck | Measure p95 latency and quotas; set sensible concurrency. |
| Shared sender sends to wrong SMTP account | Mutating username/host on singleton at runtime | Separate immutable sender profiles; do not mutate shared config. |
| Sending to wrong recipients under multithreading | Sharing mutable `MimeMessage`/helper | Create a new MIME message for each email. |
| Memory spikes when sending many attachments | Byte arrays/MIME parts held simultaneously | Bound concurrency, use re-readable streams, enforce size limits. |
| Workers time out when provider is slow | Unsuitable socket timeout or provider outage | Align with SLA, backoff, and circuit breaker. |
| Duplicate emails after timeout | SMTP may have accepted while app missed response | Record `UNKNOWN`; reconcile before retry. |
| Batch fails mid-way | Partial success without per-message outcomes | Persist per-message outcome; never blindly retry entire batch. |
| TLS handshake fails on port 587 | Using implicit TLS or wrong cert/chain | Proper STARTTLS mode, hostname verification, truststore. |
| STARTTLS not supported | Wrong host/port or relay/proxy | Verify provider capabilities, fail closed. |
| Errors spike after secret rotation | Threads interleaving old/new configs | Swap sender/profile in a controlled way, do not mutate live bean. |
| Assuming Session is a socket pool | Confusing JavaMail Session with TCP connection | Distinguish configuration from network transport. |
| Too many SMTP connections | Worker concurrency exceeds provider limits | Bounded worker pool, rate limiting, and backpressure. |
| Queue backlog grows during server errors | Aggressive retries or missing circuit breaker | Backoff + jitter, quotas, dead-letter/alerts. |
| Unit tests require real SMTP | Service instantiates `JavaMailSenderImpl` directly | Constructor injection and mock `JavaMailSender`. |
| Faster sending but retry history lost | Batch send not linked to individual outbox rows | Record per-message attempt/outcome and audit trail. |

## 24. Design and Operations Checklist

### 24.1. Sender Design

- [ ] One stably configured sender bean per SMTP profile.
- [ ] Services depend on the `JavaMailSender` interface.
- [ ] Never instantiate `JavaMailSenderImpl` inside every business method.
- [ ] Never mutate a singleton's host/credentials/properties during concurrent sends.
- [ ] Never store `MimeMessage` or `MimeMessageHelper` as shared state.
- [ ] Never share `Transport` manually without an ownership/thread-safety design.
- [ ] Distinguish sender profiles via qualifiers or a controlled registry.

### 24.2. Connection/Security

- [ ] Host/port match the provider.
- [ ] `STARTTLS` required or implicit TLS in the proper mode.
- [ ] TLS certificate chain and hostname verification enabled.
- [ ] Credentials from secret manager/env are protected.
- [ ] Connect/read/write timeouts configured explicitly.
- [ ] Leases/worker deadlines align with timeouts.
- [ ] Credential and certificate rotation procedures exist.
- [ ] Never use trust-all or plaintext fallback to "increase throughput."

### 24.3. Performance

- [ ] Measure MIME render time and SMTP submission time separately.
- [ ] Bound concurrent senders and provider rate.
- [ ] Durable queue/outbox with backlog metrics.
- [ ] Retries use backoff/jitter, budget, and dead-lettering.
- [ ] `UNKNOWN` state exists for ambiguous submission outcomes.
- [ ] Never create unbounded thread pools or in-memory queues.
- [ ] Batch sizes are measured and handle partial failures.
- [ ] Attachment sizes and memory are bounded.
- [ ] Logs include message key/attempt ID without exposing email content.

### 24.4. Testing

- [ ] Unit tests inject a mock `JavaMailSender`.
- [ ] MIME objects are created fresh per message.
- [ ] Integration tests with an SMTP sandbox verify sending configuration.
- [ ] Transport tests verify connection count and reconnect behavior if needed.
- [ ] Outbox tests verify retries, leases, idempotency, and dead-lettering.
- [ ] Concurrency tests ensure no cross-tenant/provider mix-ups.
- [ ] Tests cover provider closing connection mid-batch.
- [ ] Tests cover large attachments and write timeouts.
- [ ] Tests cover secret rotation/new config without mixing accounts.
- [ ] Tests never send real emails unintentionally.

## 25. Practice Exercises

### Exercise 1 — Refactor Sender Lifecycle

A service creates `new JavaMailSenderImpl()` inside every method. Refactor it to constructor injection of a centrally configured `JavaMailSender` bean. Explain the benefits for testing and consistency.

### Exercise 2 — Session vs. Connection

Draw the lifecycle when a singleton sender sends two messages using **two** `send` calls. Explain why the same JavaMail `Session` does not mean the same TCP socket.

### Exercise 3 — STARTTLS Configuration

Write `application.yml` for port 587 with `starttls.enable`, `starttls.required`, `ssl.checkserveridentity`, and the three timeouts. Do not hardcode secrets.

### Exercise 4 — Implicit TLS

Switch the configuration to port 465 when the provider requires implicit TLS. State the differences from STARTTLS.

### Exercise 5 — MIME Thread-Safety

Two workers concurrently send personalized emails. Design how they share the sender while creating separate `MimeMessage`/helper instances; illustrate the bug when using a shared `MimeMessage`.

### Exercise 6 — Benchmark Batching

Use an SMTP test server to measure duration and TCP connection count when sending 50 messages via 50 separate calls, then split into 10 batches × 5 messages. Keep message size and configuration identical; compare throughput and p95 latency.

### Exercise 7 — Partial Failure

A batch has 3 messages: 2 accepted and 1 failed. Design how to record outcomes per message key without retrying the already accepted messages.

### Exercise 8 — Bounded Concurrency

A provider accepts only a limited number of concurrent connections. Design a worker pool and rate limiter, and explain the difference between a concurrency limit and a rate limit.

### Exercise 9 — Multi-Tenant Sender

Two tenants use different SMTP accounts. Design a sender registry/profiles setup that does not mutate singleton config across threads and never mixes up `From`/recipients.

### Exercise 10 — Secret Rotation

Simulate credentials rotating while workers are actively sending. Propose a controlled way to swap senders/profiles instead of mutating the password on a shared bean.

### Exercise 11 — Timeouts and Leases

Socket timeout is 30 seconds while worker lease is 10 seconds. Analyze the risk of two workers sending concurrently and propose adjustments for leases/heartbeats/fencing/reconciliation.

### Exercise 12 — Attachment Memory

There are 100 concurrent emails, each with a 20 MiB attachment. Evaluate heap growth, Base64 overhead, and choosing a re-readable attachment source.

### Exercise 13 — Retrying After Timeout

The SMTP relay may have received the message, but the app lost the response. Design `UNKNOWN`, attempt history, and reconciliation before retrying.

### Exercise 14 — Unit Test Sender Reuse

Mock `JavaMailSender`, stub two `createMimeMessage()` calls returning two instances, call the service twice, and assert `send` is invoked with two distinct objects.

### Exercise 15 — Transport Integration

Use GreenMail or an SMTP test relay to test STARTTLS/implicit TLS where supported, mid-batch connection drops, and the server returning `421`. Do not use a production provider to induce bulk errors.

### Exercise 16 — Finding the Bottleneck

Given metrics: high queue wait, low MIME render, high SMTP submit p95, increasing provider 4xx responses. Propose an investigation plan before increasing worker threads.

### Exercise 17 — Event-Driven Outbox

Design an email-sending job with message key, attempt ID, `SMTP_ACCEPTED`/`UNKNOWN`, backoff, and dead-lettering. Explain why a singleton sender alone does not provide exactly-once behavior.

### Exercise 18 — Privacy and Performance Logs

Write a structured log entry for an SMTP submission containing message key, profile, duration, outcome, and attachment size; exclude full recipients, passwords, tokens, and MIME bodies.

## 26. Summary

**Reusing JavaMailSender and connection configuration** means using a **stable, Spring-managed sender bean** for each SMTP profile rather than repeatedly rebuilding configuration infrastructure in business code. The sender bean can be injected into multiple services/workers; each email must still have its **own MimeMessage and MimeMessageHelper**.

Key boundaries to remember:

1. **Reusing a sender ≠ reusing an SMTP TCP connection.** A Jakarta Mail `Session` is configuration/context, not a socket pool.
2. A `send(MimeMessage...)` call may reuse a connection within the same batch, but must handle **partial failures** and never blindly retry the whole batch.
3. Configure **host, port, TLS, hostname verification, credentials, and timeouts** centrally and consistently; never mutate a singleton while multiple threads are sending.
4. **Concurrency limits, rate limits, and retry budgets** must be designed at the worker/queue layer, not expected from the sender bean itself.
5. For multiple SMTP accounts/tenants, use **separate profiles or an isolated registry**, rather than changing username/password on a shared instance per request.
6. Optimize based on **real benchmarks**: measure queue wait, MIME build, connect/TLS/AUTH, SMTP submit, attachments, and provider limits.
7. Preserve correctness: **outbox, attempt history, idempotency, UNKNOWN reconciliation, and dead-lettering** to avoid duplicates on timeouts or partial failures.
8. Distinguish networkless unit tests, SMTP integration tests, and provider delivery/E2E tests; never use a successful `send()` return to claim an email reached the Inbox.

When bean lifecycles and MIME objects are designed properly, connection settings are centralized, concurrency is controlled, and every layer is measured, Spring Framework Mail can process emails reliably and scale smoothly without sacrificing security, traceability, or delivery correctness.
