# Testing Timeouts and Server Rejections in Spring Framework Mail

An application sending emails via **Spring Framework Mail** may behave fine when the SMTP server responds quickly, yet fail in hard-to-reproduce ways when connections stall, the mail server rejects a recipient address, the sending account loses permissions, or the connection drops mid-payload. In these scenarios, mocking `JavaMailSender` to throw an exception does not prove the real system reacts properly: many bugs only surface when **Jakarta Mail actually communicates over an SMTP socket** and processes responses at each protocol step.

This guide shows how to design **integration tests** for two failure categories:

1. **Timeouts:** connection cannot be established in time, SMTP responses are not read before the deadline, or writing data takes too long.
2. **Server rejections:** the SMTP server replies with a 4xx/5xx code at a specific command, such as rejecting a recipient, email payload, sender address, or authentication.

The goal is to test not only Spring Mail exceptions, but also business state, retries, wait bounds, duplicate prevention, transaction safety, logging, and recovery capacity once SMTP becomes healthy again.

> Core principle: test at the **exact SMTP stage where the failure occurs**. "SMTP failed" is not specific enough to decide whether an email can be retried, whether a recipient requires suppression, or whether the system risks sending duplicates.

## 1. Why Integration Test Against Real or Simulated SMTP?

A unit test example:

~~~java
doThrow(new MailSendException("SMTP unavailable"))
        .when(mailSender).send(any(SimpleMailMessage.class));
~~~

This test is useful for verifying how the business service handles exceptions. However, it does not prove:

- Host/port and timeout properties were actually applied by Jakarta Mail.
- The SMTP connection actually times out as expected.
- A server rejection at `RCPT TO` behaves differently from a rejection at `DATA`.
- How Spring Mail wraps transport-generated exceptions.
- Whether the mail sender hangs indefinitely when a server stops responding.
- Whether the relay could already have accepted the message before the application saw an error.
- How a multi-recipient message is handled when only one address is rejected.

An **integration test** must push the component under test across a real boundary, such as `JavaMailSenderImpl` -> Jakarta Mail -> TCP socket -> test SMTP server. That server needs the ability to script replies, pause responses, close connections, and record received commands.

### Test Levels to Combine

| Level | Real Components | Objective |
| --- | --- | --- |
| Unit test | Business service, mock sender | Error catching, business response, expected state |
| SMTP integration test | `JavaMailSenderImpl` + Jakarta Mail + test SMTP server | Verify protocol, timeouts, 4xx/5xx responses |
| Persistence integration test | Worker + database/outbox + fake SMTP | Retry schedule, transactions, leases, no lost messages |
| Multi-instance test | Multiple workers + broker/limiter + fake SMTP | Prevent double-claiming duplicates and retry storms |
| Provider staging test | Authorized test provider/account | Verify TLS, AUTH, quotas, vendor-specific permissions |

Never use production SMTP or customer mailboxes to intentionally trigger thousands of timeouts or refusals. Failure testing must run on authorized test infrastructure with bounded resources and test recipient addresses.

## 2. Understanding Phases of an SMTP Session

An SMTP submission session can unfold as follows (simplified diagram):

~~~text
Application / Jakarta Mail                 SMTP relay
            |                                  |
            |--------- TCP connect ---------->|
            |<-------- 220 greeting ----------|
            |--------- EHLO ----------------->|
            |<-------- 250 capabilities ------|
            |--------- STARTTLS ------------->|  if required
            |<-------- 220 ready -------------|
            |======= TLS handshake ===========|
            |--------- EHLO ----------------->|
            |<-------- 250 capabilities ------|
            |--------- AUTH ----------------->|  if enabled
            |<-------- 235 / 535 ------------|
            |--------- MAIL FROM ------------>|
            |<-------- 250 / 5xx ------------|
            |--------- RCPT TO -------------->|
            |<-------- 250 / 4xx / 5xx -------|
            |--------- DATA ----------------->|
            |<-------- 354 / 4xx / 5xx -------|
            |--------- headers + body ------->|
            |--------- <CRLF>.<CRLF> -------->|
            |<-------- 250 / 4xx / 5xx -------|
            |--------- QUIT ----------------->|
            |<-------- 221 -------------------|
~~~

The codes above are common examples, not exhaustive across all SMTP extensions or providers. Not every session uses STARTTLS or AUTH, though production applications must follow the security policies mandated by their provider.

### Why Does Failure Location Matter?

| Phase | What Can Happen | Consequence |
| --- | --- | --- |
| TCP connect | Connection timeout or refused | SMTP session never established |
| Greeting/EHLO | Server unresponsive; session stalls | Envelope/body transmission has not started |
| STARTTLS | Server lacks support or TLS handshake error | Must never silently downgrade security |
| AUTH | Invalid credentials, revoked permissions, or auth server error | SMTP account error, not recipient error |
| MAIL FROM | Sender address disallowed, policy rejection | No message accepted yet |
| RCPT TO | Invalid/temporarily unavailable recipient | May affect only one recipient |
| DATA before payload | Server refuses to receive data | Body has not been transferred |
| After sending DATA terminator | Server accepts or rejects; reply may be lost | Can produce an **unknown** outcome |
| After message accepted | Provider/remote MX continues processing | Bounces/deferrals do not mean initial submit failed |

A test returning 550 immediately after EHLO cannot substitute for a recipient rejected at `RCPT TO`. **Simulate the exact command and timing** so failure-classification tests are trustworthy.

## 3. Three Core Timeouts in Jakarta Mail SMTP

Commonly used SMTP properties:

| Property | General Meaning | What Does It Bound? |
| --- | --- | --- |
| `mail.smtp.connectiontimeout` | Connection timeout | Time allowed to establish the TCP connection |
| `mail.smtp.timeout` | Socket read timeout | Time waiting for reply bytes from the SMTP server |
| `mail.smtp.writetimeout` | Socket write timeout | Time allowed to write bytes to the SMTP socket |

Values are typically in milliseconds in standard Jakarta Mail SMTP implementations. When unconfigured, some environments/providers allow very long or unbounded waits at a given stage; never rely on defaults for applications with SLAs.

### 3.1. Connection Timeout

Occurs when the client cannot establish a TCP connection to the target within the configured window.

Examples:

- Network path to the SMTP server blackholes/drops packets.
- Firewall sends no response.
- Routing/network outage.

**Distinction:** if the connection is rejected immediately via TCP RST, that is usually **connection refused**, not a timeout. Both cause sending to fail, yet are distinct failure modes. Connecting to a port known to have no listener typically tests connection refused, **not connection timeout**.

### 3.2. Read Timeout

The application has connected, yet the server fails to reply to an SMTP command within the allowed window:

~~~text
Client                           Fake SMTP server
  |---------- connect ---------->|
  |<--------- 220 greeting ------|
  |---------- EHLO ------------->|
  |                              | (sends no reply)
  |   waits until read timeout   |
  |---- exception -------------->|
~~~

This scenario is easy to reproduce using a test SMTP server capable of **going silent after EHLO**. It does not require genuinely slow external networks.

### 3.3. Write Timeout

Occurs when data written to the socket cannot be flushed in time, such as when the server stops reading the body and TCP buffers fill up.

Harder to simulate deterministically than read timeout because kernel/network buffers can absorb significant data even while the server is not actively reading. A test that sends a small string and sleeps a few hundred milliseconds **is unlikely to trigger a write timeout**.

For more reliable testing, you can:

- Use a network fault injector controlling the link.
- Have the server stop reading while sending a sufficiently large MIME body within test bounds.
- Control socket buffer sizes if the test harness supports it.
- Enforce an overall test timeout and release resources if un-reproducible.

Do not treat every `IOException` during body transmission as a write timeout. Distinguish connection reset, broken pipe, and socket timeout via the actual cause.

### 3.4. Total Duration Timeout for the Entire Send

The three properties above do not necessarily establish **one global deadline for the entire `send()` call**. A session involves multiple reads, writes, and handshakes, each consuming time. If you need a cap on total job processing time, design an SLA/deadline at the worker layer and handle cancellation/resource cleanup.

Do not assume `CompletableFuture.orTimeout(...)` immediately aborts a blocking SMTP socket. A future timeout may only complete the handle exceptionally while the underlying worker keeps running. Transport timeouts, concurrency limits, and cancellation/thread-cleanup checks are all necessary.

## 4. Configuring Timeouts in Spring Boot

Example SMTP submission configuration over STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: mail-service
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Values above are illustrative only. Host, port, credential delivery, TLS mode, and timeouts must reflect your actual provider and SLA. Never commit production secrets into the repository; use a secret manager or secure environment configuration.

If using implicit TLS on port 465, align TLS settings appropriately; do not copy STARTTLS settings from port 587 and assume they suffice.

### Note on YAML Syntax

The `"[mail.smtp.timeout]"` syntax expresses a Jakarta Mail key under `spring.mail.properties` in Spring Boot configuration binding. Avoid confusing it with a direct `spring.mail.timeout` property if your version defines no such top-level key.

### Never Mutate Timeouts per Individual Email

`JavaMailSenderImpl` is typically a shared bean whose transport settings apply across many messages. If one message type needs a distinct SLA, consider:

- Separating SMTP senders/routes per email category.
- Separating worker lanes/queues and retry policies.
- Using approved timeout settings per dedicated sender.
- Ensuring a shared `JavaMailSenderImpl` is never mutated across threads mid-send.

Mutating a property on a shared bean across concurrent calls is not an atomic, reliable configuration mechanism.

## 5. SMTP Rejections: Temporary vs. Permanent Errors

SMTP reply codes are commonly grouped as:

- **4xx:** temporary failure for the current request, generally eligible for retry later.
- **5xx:** permanent failure for the current request, generally should not be blindly retried.

This is a starting heuristic, **not a complete retry policy**. Identical codes can stem from different causes depending on command and provider, especially with enhanced status codes.

| Example Code | Common Scenario | Application Strategy |
| --- | --- | --- |
| 421 | SMTP service temporarily unavailable | Backoff, optionally throttle/pause route |
| 450 | Mailbox temporarily unavailable | Bounded retry scoped by recipient/message |
| 451 | Local processing error | Temporary retry, monitor |
| 452 | Insufficient system storage/resources | Avoid load spikes, retry with backoff |
| 535 | Invalid authentication credentials at some providers | Investigate credentials/permissions; never keep retrying all emails |
| 550 | Non-existent mailbox or policy rejection, depending on context | Do not retry blindly; classify recipient vs. policy |
| 553 | Address/identity rejected due to syntax or policy | Fix address/configuration |
| 554 | Transaction/message rejected, depending on phase | Investigate content/policy/server |

Sample SMTP codes do not guarantee every server responds identically. Enhanced status codes such as `5.1.1`, `4.7.1`, `5.7.1` add context, yet applications must follow the specifications of their real provider and transport library.

### Authentication Failure Differs from Recipient Refusal

If SMTP returns an error during AUTH, that is typically a credential, relay-permission, or auth-mechanism issue. Never suppress a recipient address just because an SMTP password is wrong.

If the server returns a permanent error at `RCPT TO` for one address, the outcome applies to that recipient. Never automatically assume sender credentials leaked or trigger mandatory secret rotation.

### Server Rejections Before DATA vs. After DATA

- **RCPT TO 550:** server rejected that recipient; no body was transferred in this transaction.
- **DATA 554 before 354:** server refused to begin content transfer.
- **After DATA terminator, server replies 554:** server read the message yet rejected it per protocol; handle as a failure of that submission attempt.
- **After DATA terminator, connection drops before final reply:** client cannot be sure whether the server accepted it; consider **SUBMISSION_UNKNOWN** and duplicate risk.

Distinguishing the last two cases is critical. Never immediately retry every exception raised after transmitting the body.

## 6. Spring Mail Exceptions and Underlying Causes

At the Spring layer, `JavaMailSender.send(...)` typically surfaces failures using `MailException` subclasses depending on phase and message structure:

| Spring Exception Class | General Meaning |
| --- | --- |
| `MailSendException` | Failed to send one or more messages |
| `MailAuthenticationException` | Authentication with the mail server failed |
| `MailParseException` | Unable to construct/parse a valid message |
| `MailPreparationException` | Error preparing message via callback/preparator |
| `MailException` | Base class catchable at business boundaries |

Exceptions from Jakarta Mail, SMTP provider implementations, `IOException`, `SocketTimeoutException`, and networking errors can reside in the cause chain or failed-messages map. Exception wrapping varies across Spring/Jakarta Mail providers/versions and failure locations. **Do not write integration tests accepting only one rigid subclass/cause if the application's contract only requires safe classification.**

### What to Do When Catching Failures

1. Persist the internal notification ID and attempt ID.
2. Classify the failure in the transport adapter.
3. Distinguish permanent recipient errors, temporary service errors, AUTH failures, content rejections, and unknown outcomes.
4. Preserve exception causes for controlled diagnostics.
5. Decide retry, suppress, dead-letter, or alert for manual intervention.
6. Never log SMTP credentials, OTPs, reset tokens, or bodies containing sensitive data.

### A Failure-Classifying Adapter

~~~java
public enum TransportFailureKind {
    CONNECTION_FAILED,
    READ_TIMEOUT,
    WRITE_TIMEOUT,
    TEMPORARY_SMTP,
    PERMANENT_RECIPIENT,
    AUTHENTICATION_FAILED,
    CONTENT_REJECTED,
    SUBMISSION_UNKNOWN,
    OTHER
}

public record TransportFailure(
        TransportFailureKind kind,
        String normalizedCode,
        boolean retryable,
        boolean recipientScoped
) {
}
~~~

This is an **application-defined** model, not a Spring Mail API. Mapping must rely on evidence from SMTP phase, reply codes, and exceptions. Never infer `SUBMISSION_UNKNOWN` from a generic exception class alone; know which step lost the connection or use a gateway that records protocol phases.

## 7. Distinguishing Connection Timeouts from Active Server Rejections

A server rejecting with reply `550` is a **protocol-level refusal**: the application exchanged SMTP commands and received an answer. A `SocketTimeoutException` waiting for a reply is a **transport-level timeout**: the application received no reply at that step.

| Signal | Connection Timeout | Read Timeout | SMTP 550 |
| --- | --- | --- | --- |
| TCP connection established? | Typically no | Yes | Yes |
| Server sent SMTP rejection code? | No | Not at waiting step | Yes |
| Requires network fault injection? | Typically yes | Silent fake server suffices | Fake server returning 550 |
| Eligible for retry? | Usually with backoff, context-dependent | Phase-dependent | Generally not retried blindly |
| Requires recipient suppression? | Cannot be inferred | Cannot be inferred | Possibly, after classification |
| Unknown submission outcome? | Usually no, never connected | Depends on awaited command | Known rejected if reply is clear |

A good test must state clearly "where it timed out" or "which command the server rejected". Never catch `MailException` and label every failure an SMTP timeout.

## 8. Choosing a Test SMTP Server

Two distinct tool categories exist:

### 8.1. SMTP Capture Servers

Tools like GreenMail, MailHog/Mailpit, or an internal test SMTP server are great for verifying:

- Client connects to the test endpoint.
- Email is sent and accepted by the server.
- `From`, `To`, `Subject`, MIME, and attachments are constructed properly.
- Output never reaches real mailboxes.

However, **not every capture server offers simple APIs to return 451 or stall right after EHLO**. When deterministic fault injection is required, use a scripted server or a network proxy supporting those behaviors.

### 8.2. Scripted / Fault-Injection SMTP Servers

A test server can be programmed to:

- Send greeting 220 and then stay silent on EHLO.
- Return 450/550 on `RCPT TO`.
- Return 451/554 on `DATA`.
- Accept the body and close the connection before final 250.
- Close the connection mid-command.
- Delay the 250 reply after `DATA`.

These tests traverse real sockets without depending on public SMTP providers. They test the exact simulated scenario and run reliably in CI.

### 8.3. Network Proxies / Fault Injectors

For connection timeouts, packet loss, resets, and write timeouts, a network proxy or Testcontainers setup with network fault controls can reproduce conditions more faithfully than a fake SMTP server using plain `ServerSocket`. For instance, a proxy supporting latency/timeout toxics can simulate an unresponsive link.

Never assume a closed port causes a connect timeout. The OS may immediately return connection refused, making the test verify the wrong thing.

## 9. Configuring JavaMailSenderImpl Directly for Integration Tests

An integration test can instantiate a real sender pointing to a fake SMTP server on the loopback interface:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class TestMailSenderFactory {

    public static JavaMailSenderImpl create(
            String host,
            int port,
            int connectTimeoutMs,
            int readTimeoutMs,
            int writeTimeoutMs) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "false");
        properties.put("mail.smtp.connectiontimeout",
                Integer.toString(connectTimeoutMs));
        properties.put("mail.smtp.timeout",
                Integer.toString(readTimeoutMs));
        properties.put("mail.smtp.writetimeout",
                Integer.toString(writeTimeoutMs));
        sender.setJavaMailProperties(properties);

        return sender;
    }
}
~~~

For a fake server supporting only plaintext SMTP on loopback, this example intentionally disables AUTH/STARTTLS. **Use such settings only in isolated tests.** Production must preserve TLS and authentication per provider; never disable security just to "fix" a connection error.

### Creating a Test Message Containing No Real Data

~~~java
import org.springframework.mail.SimpleMailMessage;

public static SimpleMailMessage sampleMessage() {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("sender@example.test");
    message.setTo("receiver@example.test");
    message.setSubject("SMTP integration test");
    message.setText("No production data");
    return message;
}
~~~

The `example.test` domain in the example is purely illustrative; local test servers do not relay mail to the Internet. Never use real customer addresses when testing server rejections.

## 10. Building a Minimal Scripted SMTP Server in Java

To reproduce failures deterministically, you can write a small test SMTP server using `ServerSocket` and an executor. This server covers only basic testing: it does not support STARTTLS, SMTP AUTH, multiple messages per connection, or full SMTP extensions. Crucially, it **actually speaks the SMTP protocol over TCP**.

Example helper file in test sources:

~~~java
package com.example.mailtest;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ScriptedSmtpServer implements AutoCloseable {

    public enum Scenario {
        ACCEPT,
        SILENT_AFTER_EHLO,
        RCPT_TEMPORARY_451,
        RCPT_PERMANENT_550,
        DATA_PERMANENT_554,
        DROP_AFTER_BODY
    }

    private final ServerSocket listener;
    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();
    private final Scenario scenario;
    private final List<String> commands =
            new CopyOnWriteArrayList<>();
    private final AtomicBoolean bodyTerminated =
            new AtomicBoolean(false);
    private final Future<?> serverTask;

    public ScriptedSmtpServer(Scenario scenario) throws IOException {
        this.scenario = scenario;
        this.listener = new ServerSocket(
                0,
                1,
                InetAddress.getByName("127.0.0.1"));
        serverTask = executor.submit(this::serveOneConnection);
    }

    public int port() {
        return listener.getLocalPort();
    }

    public List<String> commands() {
        return List.copyOf(commands);
    }

    public boolean sawBodyTerminator() {
        return bodyTerminated.get();
    }

    private void serveOneConnection() {
        try (Socket client = listener.accept()) {
            client.setSoTimeout(5_000);

            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.US_ASCII));

            reply(out, "220 local.test ESMTP ready");

            String line;
            while ((line = in.readLine()) != null) {
                String upper = line.toUpperCase(Locale.ROOT);

                // Record commands only; never log DATA body
                // or AUTH contents of any future test.
                commands.add(upper.startsWith("DATA")
                        ? "DATA" : line);

                if (upper.startsWith("EHLO ")
                        || upper.startsWith("HELO ")) {
                    if (scenario == Scenario.SILENT_AFTER_EHLO) {
                        // Client must hit read timeout on its own.
                        TimeUnit.SECONDS.sleep(3);
                        return;
                    }
                    reply(out, "250-local.test Hello",
                            "250 SIZE 10485760");
                } else if (upper.startsWith("MAIL FROM:")) {
                    reply(out, "250 2.1.0 Sender OK");
                } else if (upper.startsWith("RCPT TO:")) {
                    if (scenario == Scenario.RCPT_TEMPORARY_451) {
                        reply(out, "451 4.3.0 Try again later");
                    } else if (
                            scenario == Scenario.RCPT_PERMANENT_550) {
                        reply(out, "550 5.1.1 Unknown recipient");
                    } else {
                        reply(out, "250 2.1.5 Recipient OK");
                    }
                } else if (upper.equals("DATA")) {
                    if (scenario == Scenario.DATA_PERMANENT_554) {
                        reply(out,
                                "554 5.7.1 Message rejected");
                        continue;
                    }

                    reply(out, "354 End with <CRLF>.<CRLF>");
                    while ((line = in.readLine()) != null) {
                        if (line.equals(".")) {
                            bodyTerminated.set(true);
                            break;
                        }
                    }

                    if (scenario == Scenario.DROP_AFTER_BODY) {
                        // Simulate losing final SMTP reply.
                        // Client cannot know outcome for certain.
                        return;
                    }
                    reply(out, "250 2.0.0 Queued as test-123");
                } else if (upper.equals("RSET")) {
                    reply(out, "250 2.0.0 Reset OK");
                } else if (upper.equals("NOOP")) {
                    reply(out, "250 2.0.0 OK");
                } else if (upper.equals("QUIT")) {
                    reply(out, "221 2.0.0 Bye");
                    return;
                } else {
                    reply(out, "502 5.5.2 Command not supported");
                }
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (IOException ignored) {
            // On client timeout/close or test shutdown:
            // closing the socket is expected behavior.
        }
    }

    private static void reply(
            BufferedWriter writer,
            String... lines) throws IOException {
        for (String line : lines) {
            writer.write(line);
            writer.write("\r\n");
        }
        writer.flush();
    }

    @Override
    public void close() throws IOException {
        listener.close();
        serverTask.cancel(true);
        executor.shutdownNow();
    }
}
~~~

### Scope of the Helper

- Uses dynamic port `0` so the OS assigns a free port.
- Listens only on `127.0.0.1` and handles a single connection.
- Replies 220, 250, 354, 451, 550, 554, and 221 matching the scenarios.
- Includes a silent-after-EHLO scenario to test read timeouts.
- Includes closing the connection after the client finishes sending the body yet before the final reply to simulate uncertain outcomes.
- Does not retain or print email bodies; only marks whether DATA termination was seen.
- Closes listener/executor at the end of each test to avoid thread/port leaks.

This is a **minimal fake SMTP server for learning purposes**. It is not a full RFC-compliant mail server and must never accept real traffic. To test TLS handshakes, SMTP AUTH, multi-recipient behavior, or provider-specific policies, use a test harness/relay supporting those features.

### Why Is Cleanup Necessary?

If tests leave server threads blocked on accept/read, CI can hang or accumulate threads across tests. With `try-with-resources`, `close()` runs even when assertions fail. Tests also need a runner-level overall timeout to guard against abnormal network/harness bugs.

## 11. Integration Test: Server Accepts the Message

Before testing failures, establish a passing baseline. If the happy-path test fails, failure tests might merely be exposing broken fake-server wiring rather than the target behavior.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SmtpSuccessIntegrationTest {

    @Test
    void submitsMessageWhenServerAcceptsData() throws Exception {
        try (ScriptedSmtpServer smtp =
                new ScriptedSmtpServer(
                        ScriptedSmtpServer.Scenario.ACCEPT)) {

            JavaMailSenderImpl sender =
                    TestMailSenderFactory.create(
                            "127.0.0.1",
                            smtp.port(),
                            500,
                            500,
                            500);

            assertDoesNotThrow(
                    () -> sender.send(sampleMessage()));

            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("MAIL FROM:")));
            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("RCPT TO:")));
            assertTrue(smtp.commands().contains("DATA"));
            assertTrue(smtp.sawBodyTerminator());
        }
    }
}
~~~

The helpers `sampleMessage()` and `TestMailSenderFactory` were defined in earlier sections; place them in a test utility class or import them per your project's package structure.

**Test outcome:** `JavaMailSenderImpl` submits the message and receives final success from fake SMTP. This proves **successful submission to the fake relay**, not delivery to the recipient's mailbox.

## 12. Integration Test: Read Timeout After EHLO

The most valuable timeout test because it reproduces deterministically without external network dependencies:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SmtpReadTimeoutIntegrationTest {

    @Test
    void failsWhenServerStopsReplyingAfterEhlo() throws Exception {
        try (ScriptedSmtpServer smtp =
                new ScriptedSmtpServer(
                        ScriptedSmtpServer.Scenario.SILENT_AFTER_EHLO)) {

            JavaMailSenderImpl sender =
                    TestMailSenderFactory.create(
                            "127.0.0.1",
                            smtp.port(),
                            500,
                            250,
                            500);

            assertTimeoutPreemptively(
                    Duration.ofSeconds(5),
                    () -> assertThrows(
                            MailException.class,
                            () -> sender.send(sampleMessage())));

            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("EHLO ")
                            || cmd.startsWith("HELO ")));
            assertFalse(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("MAIL FROM:")));
        }
    }
}
~~~

With `mail.smtp.timeout=250`, the client awaits the reply after EHLO and fails once the read timeout expires. `assertTimeoutPreemptively(5s)` prevents the test from hanging too long; however, if a thread must be aborted, watch socket and thread cleanup in your test environment.

### Do Not Assert Exactly 250 ms

Total elapsed time includes `JavaMailSender` initialization, socket setup, scheduling, and CI overhead. Never assert "exactly 250 ms" or overly tight bounds. Instead verify:

1. The sender failed to succeed.
2. The fake server received EHLO.
3. No envelope/body was transmitted.
4. The test completed within a reasonable upper bound.
5. The cause chain contains socket read timeout evidence when deep verification is desired.

If a test only checks `MailException` without confirming the server stalled at the exact expected step, the failure might actually come from a wrong port rather than a read timeout.

## 13. Integration Test: Server Rejects Recipient with 550

Suppose the fake SMTP server accepts `MAIL FROM` yet returns `550 5.1.1` for `RCPT TO`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailException;

class SmtpRecipientRefusalIntegrationTest {

    @Test
    void refusesInvalidRecipientBeforeData() throws Exception {
        try (ScriptedSmtpServer smtp =
                new ScriptedSmtpServer(
                        ScriptedSmtpServer.Scenario.RCPT_PERMANENT_550)) {

            var sender = TestMailSenderFactory.create(
                    "127.0.0.1",
                    smtp.port(),
                    500, 500, 500);

            assertThrows(MailException.class,
                    () -> sender.send(sampleMessage()));

            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("RCPT TO:")));
            assertFalse(smtp.commands().contains("DATA"));
            assertFalse(smtp.sawBodyTerminator());
        }
    }
}
~~~

The test verifies:

- A real SMTP session occurred.
- The server received the `RCPT TO` command.
- The server rejected the recipient before the client sent the body.
- `JavaMailSender` surfaced an exception.
- The application can classify this as a recipient-scoped error given sufficient code/response evidence.

Do not assume every SMTP 550 means "address does not exist" when providers may return 550 for policy, DNS, or sender identity reasons. This test uses **550 5.1.1 Unknown recipient** specifically to simulate an invalid-recipient rejection.

## 14. Integration Test: Server Temporarily Rejects Recipient with 451

A 451 response on `RCPT TO` can signal a temporary error. That submission attempt was not accepted for the recipient, though the business layer may decide to retry with backoff.

~~~java
@Test
void temporaryRecipientRefusalDoesNotSubmitData() throws Exception {
    try (ScriptedSmtpServer smtp =
            new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.RCPT_TEMPORARY_451)) {

        var sender = TestMailSenderFactory.create(
                "127.0.0.1",
                smtp.port(),
                500, 500, 500);

        assertThrows(MailException.class,
                () -> sender.send(sampleMessage()));

        assertTrue(smtp.commands().stream()
                .anyMatch(cmd -> cmd.startsWith("RCPT TO:")));
        assertFalse(smtp.commands().contains("DATA"));
    }
}
~~~

What to verify at the application layer:

- Do **not** mark the email `SUBMITTED`.
- Transition the outbox to `RETRY_PENDING` if the classifier identifies a temporary error.
- Increment the attempt count **once** for the submission command executed.
- Record code 451/enhanced status if readable.
- Set `nextAttemptAt` in the future rather than retrying immediately in a tight loop.
- Enforce max attempts, message age, and retry pacing.

Do not write integration tests demanding the system *always* retry 451 in every circumstance; policy may also depend on recipient validity, SLA, provider, email type, and retry budget.

## 15. Integration Test: DATA Rejected

When `RCPT TO` succeeds yet the server returns 554 on the `DATA` command, the message body has not been transferred:

~~~java
@Test
void rejectsDataCommandAfterAcceptingRecipient() throws Exception {
    try (ScriptedSmtpServer smtp =
            new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.DATA_PERMANENT_554)) {

        var sender = TestMailSenderFactory.create(
                "127.0.0.1",
                smtp.port(),
                500, 500, 500);

        assertThrows(MailException.class,
                () -> sender.send(sampleMessage()));

        assertTrue(smtp.commands().contains("DATA"));
        assertFalse(smtp.sawBodyTerminator());
    }
}
~~~

This is a **server rejection right at the DATA command**. Do not confuse it with a server reading the full email and returning 554 **after the DATA terminator**; the two differ in transferred data, logging, and outcome certainty.

### Why Test Both Locations?

If an adapter sees "554" and always treats it as a content-related permanent failure, that may match a specific provider's business policy. Still, the adapter should record the phase/recipient and not infer that the body was read if the error occurred before 354.

An additional test can have the fake server return 354, read the body until the dot terminator, and then return 554. That yields an **explicit SMTP rejection**, distinct from losing the reply entirely.

## 16. Integration Test: Disconnection After DATA

The most dangerous scenario for retries and idempotency:

~~~text
Client                              SMTP relay
  |--------- DATA ----------------->|
  |<-------- 354 -------------------|
  |--------- MIME body ------------>|
  |--------- "." ------------------>|
  |                                | May already have processed message
  |          connection closed     X
  |                                |
  | Never receives final 250 / 4xx / 5xx
~~~

The test server only simulates **losing the final response**; it does not prove a production relay accepted the message. What matters is that the application **does not know the outcome**.

~~~java
@Test
void treatsLostFinalResponseAsUncertainOutcome() throws Exception {
    try (ScriptedSmtpServer smtp =
            new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.DROP_AFTER_BODY)) {

        var sender = TestMailSenderFactory.create(
                "127.0.0.1",
                smtp.port(),
                500, 500, 500);

        assertThrows(MailException.class,
                () -> sender.send(sampleMessage()));

        assertTrue(smtp.commands().contains("DATA"));
        assertTrue(smtp.sawBodyTerminator());

        // Business assertion: when the transport adapter knows
        // the final reply was lost after DATA,
        // policy does not immediately retry blindly.
    }
}
~~~

At the service layer, use a state such as `SUBMISSION_UNKNOWN`, store attempt IDs and provider correlation, and reconcile or handle per duplicate policy. Do not mark `SUBMITTED` merely because the server read the body, and do not mark `FAILED` definitively and immediately send a new copy when the relay may already have accepted it.

**Practical limitation:** `JavaMailSenderImpl` offers no high-level API guaranteeing detection of "sent DATA terminator yet lost final reply". If strict per-phase classification is required, build a transport gateway with instrumented protocol-level results or use a provider API offering idempotency/status lookup. Policy-layer tests can inject a `SUBMISSION_UNKNOWN` outcome reliably detected by the transport adapter rather than expecting Spring Mail to infer every case itself.

## 17. Connection Refused and Connection Timeout Scenarios

### Connection refused

When no process is listening at the target, the OS may return a connection-refused error very quickly:

~~~text
Client -> 127.0.0.1:port
        <- TCP RST / connection refused
~~~

Tests can point to a controlled local port with no listener, though "pick a free port then close its socket" has a race window where another process could grab the port before the test uses it. Treat it as a useful isolated integration test, not deterministic timeout proof.

Target example:

~~~java
@Test
void reportsConnectionFailureWhenNoSmtpListenerExists() {
    int isolatedUnusedPort = getPortFromControlledTestHarness();
    var sender = TestMailSenderFactory.create(
            "127.0.0.1",
            isolatedUnusedPort,
            200, 300, 300);

    assertThrows(MailException.class,
            () -> sender.send(sampleMessage()));
}
~~~

`getPortFromControlledTestHarness()` is a helper supplied by test infrastructure, not built into JUnit. It must ensure a stable or sandboxed port environment. This case can produce **connection refused**, which does not prove `mail.smtp.connectiontimeout` worked.

### Connection Timeout

To test a genuine **connect timeout**, use a path where connection packets are dropped/blackholed without a reply before the deadline. Behavior depends on OS and network; a "non-existent" IP may immediately return `Network unreachable` instead of timing out.

Proper workflow:

1. Set up a test network environment with a fault injector.
2. Configure a proxy/route that accepts traffic without completing the connection reproducibly.
3. Set `mail.smtp.connectiontimeout` short enough for CI.
4. Verify the failure is a connect timeout (not a DNS error or refused connection).
5. Enforce an overall upper bound with the test runner timeout.
6. Clean up the proxy/network after each test.

**Never simulate a connect timeout by having a fake SMTP server accept TCP and stay silent after EHLO**; that is a read timeout.

## 18. Controlled Write Timeout Tests

Write timeouts are harder to reproduce reliably than read timeouts because written application data can sit in TCP buffers. Even if the server stops reading, writes may succeed for a while as long as bytes fit in the buffer.

### How to Build the Scenario

1. Fake SMTP accepts connection, EHLO, MAIL FROM, RCPT TO, and returns 354 for DATA.
2. After 354, the server **stops reading from the socket**.
3. The client starts sending a reasonably large MIME payload bounded for the test environment.
4. `mail.smtp.writetimeout` is configured small enough.
5. A transport/network fault injector throttles buffers or bandwidth if needed.
6. The test records the exception/cause and ensures workers release resources.

### What Not to Do

- Never send gigabytes of data just to force a socket timeout.
- Never let tests run unbounded waiting for OS buffers to fill.
- Never require millisecond-exact failure timing.
- Never confuse a `Broken pipe` from the server actively closing the connection with a write timeout.
- Never use public SMTP providers for link-congestion experiments.

A valid write timeout test needs evidence that the fault triggered and the exception came from a write operation. Without such observability, the test only proves "sending fails on a slow network", not that the timeout property took effect.

### Implementation Caveats

Some SMTP provider implementations use internal threads/timers for write timeouts. Check resource behavior across repeated write timeouts: are threads cleaned up, sockets closed, and futures/workers unblocked? Never assume cancelling a `Future` closes every blocking connection.

## 19. Testing Server Rejections at MAIL FROM

Errors at `MAIL FROM` relate to the envelope sender, relay permissions, or policy. They do not prove the recipient address is invalid.

Example SMTP script:

~~~text
220 local.test ESMTP ready
C: EHLO app.local
S: 250 local.test
C: MAIL FROM:<notifications@example.test>
S: 553 5.7.1 Sender not authorized
~~~

A test should verify:

- The client sent `MAIL FROM`.
- The server returned a rejection code at that command.
- Execution never proceeded to `DATA`.
- The service classified a sender/account policy error.
- The recipient was not suppressed.
- Alerts fire if the error affects every message sharing that SMTP identity.

To add this scenario to `ScriptedSmtpServer`, extend the enum with `MAIL_FROM_REJECT_553` and return the reply in the `MAIL FROM` branch. To test "sender address invalid" vs. "sender not authorized" separately, use provider-defined enhanced status codes and text in the fixture.

## 20. Testing SMTP AUTH Rejections

In production, SMTP authentication typically occurs after establishing a secure connection per provider configuration. When username/password are wrong or the account lacks permission, the server may return a code like `535`.

### Testing Goals

- Catch the authentication failure at the `AUTH` step.
- Classify the failure at the **SMTP account/provider level**, not per recipient.
- Do not proceed to `MAIL FROM`, `RCPT TO`, or `DATA` after an AUTH failure.
- Pause or throttle retries on that sending lane if the failure impacts many jobs.
- Never leak passwords/tokens in logs or telemetry.
- Keep transactional emails in the outbox for processing once credentials recover.
- Never downgrade from STARTTLS to plaintext to "retry".

### Why a Simple Scripted Server Is Not Enough

The earlier helper does not implement STARTTLS or SMTP AUTH. Simply returning 535 to an arbitrary command does not genuinely verify standard AUTH negotiation. When full verification is required, use a test SMTP server supporting SASL AUTH/TLS, a fake server implementing the needed protocol subset, or an authorized staging environment.

### Example Service Test Structure

~~~java
@Test
void authenticationFailureDoesNotSuppressRecipient() {
    // Transport adapter returns a pre-classified
    // result from SMTP AUTH in integration tests.
    when(transport.submit(any()))
            .thenThrow(new SmtpCredentialRejectedException(
                    "AUTH_REJECTED"));

    assertThrows(SmtpCredentialRejectedException.class,
            () -> dispatcher.dispatch(notification));

    verify(providerHealthService)
            .recordCredentialFailure("primary-smtp");
    verifyNoInteractions(recipientSuppressionRepository);
}
~~~

This is a service test using a mock adapter to **complement** SMTP protocol tests, not replace real TLS/AUTH tests. Names like `SmtpCredentialRejectedException` are application-defined.

### Distinguishing AUTH 535 from Recipient Refusal 550

If all notifications fail simultaneously due to invalid credentials, retrying each email creates an authentication storm without recovering. Pause the provider lane, alert, refresh/rotate credentials per policy, and drain the backlog after confirming AUTH works. Conversely, a 550 for one recipient address should not automatically halt all mail for that provider.

## 21. Testing TLS and Certificate Validation

Security failures can look like "unable to send email", yet must never be "resolved" by disabling TLS or enabling trust-all in production.

Integration scenarios:

| Scenario | What to Verify |
| --- | --- |
| SMTP server requires STARTTLS yet client disables it | Send rejected / misconfiguration caught |
| Client requires STARTTLS yet server does not advertise it | Never silently sends plaintext |
| Invalid certificate | Secure connection fails per trust policy |
| Hostname mismatches certificate | Hostname verification blocks connection |
| Server supports implicit TLS only | Client uses matching TLS mode and port |
| TLS handshake stalls | Transport timeout and proper resource cleanup |
| Wrong credentials after TLS | AUTH failure classified separately |

With Spring/Jakarta Mail, typically configure `mail.smtp.starttls.enable`, `mail.smtp.starttls.required`, and `mail.smtp.ssl.checkserveridentity` for STARTTLS per provider. Tests must never "fix" certificate errors by setting `mail.smtp.ssl.trust=*` in production environments.

**Real TLS tests require an SMTP server with certificates and TLS handshakes.** The earlier plaintext fake server cannot do this. Use test certificates and a dedicated test truststore when needed, rather than disabling verification and turning a security check into a plain connectivity check.

## 22. Testing Multiple Recipients and Partial Refusals

A MIME message may list multiple To/Cc/Bcc recipients. An SMTP server may respond:

~~~text
C: RCPT TO:<a@example.test>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<b@example.test>
S: 550 5.1.1 Unknown recipient
~~~

This is a **mixed acceptance** case. Send outcomes depend on the SMTP transport implementation, configuration, and partial-send policy; never assume every recipient failed merely because `send()` threw an exception.

### Related Property

Jakarta Mail SMTP provides `mail.smtp.sendpartial`. In common implementations, this setting controls whether sending proceeds to accepted recipients when a subset of recipients is rejected.

Tests should exercise the configuration variants supported by the product and observe:

- How many `RCPT TO` commands the server received.
- Whether `DATA` proceeded.
- Whether the message was accepted for valid recipients.
- How exceptions/failed address lists are surfaced.
- That the application tracks **per-recipient** statuses rather than one coarse status for the whole message.

Do not enable `sendpartial=true` globally without understanding privacy/duplicate impacts and result-handling logic. For personalized transactional emails, sending one message per recipient is usually easier to track.

### A Test Matrix

| Scenario | Expectation to Define |
| --- | --- |
| All RCPTs accepted | `DATA` and final response succeed |
| All RCPTs permanently refused | Mark zero recipients submitted |
| One RCPT accepted, one permanently refused | Follow configured partial behavior |
| One RCPT temporarily refused | Retry only the eligible recipient, if transport allows |
| Server accepts DATA yet connection drops | Do not automatically resend to all recipients on uncertain outcome |

Do not treat `MailSendException` as an "all failed" boolean if the underlying transport already delivered partially. Inspect exception/result metadata carefully and test against your exact runtime implementation.

## 23. Testing Replies After DATA vs. Lost Final Replies

Two easily confused scenarios:

**A. Server returns 554 after body:**

~~~text
C: DATA
S: 354 Continue
C: [headers and body]
C: .
S: 554 5.7.1 Message rejected
~~~

The client received an **explicit rejection** for the transaction. Under SMTP semantics, the server did not accept responsibility for delivering this message; the business service can treat it as a failure response.

**B. Server returns no final response:**

~~~text
C: DATA
S: 354 Continue
C: [headers and body]
C: .
X: Connection closes before final reply
~~~

The application **does not know** whether the relay accepted the message. This creates an uncertainty window with duplicate risk on retry.

### Separate Test Fixtures Are Needed

In the helper:

- Current scenario `DATA_PERMANENT_554` rejects **before** sending the body.
- Scenario `DROP_AFTER_BODY` simulates **after** the body with no reply.

To test A, add a scenario such as `REJECT_AFTER_BODY_554`: after reading the DATA dot terminator, return `554 5.7.1 Message rejected` instead of 250.

Never substitute B for A and conclude the errors mean the same thing. Record the **SMTP phase** or equivalent evidence in the transport adapter.

## 24. Spring Boot Integration Test with ApplicationContext

Instantiating `JavaMailSenderImpl` directly verifies real transport, yet does not prove Spring Boot auto-configuration, property binding, and bean injection work properly. For Spring Boot projects, add an integration test booting `ApplicationContext` and pointing the auto-configured bean to a fake SMTP server.

Test skeleton example:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
class BootMailConfigurationIntegrationTest {

    private static final ScriptedSmtpServer SMTP = startServer();

    @Autowired
    JavaMailSender sender;

    private static ScriptedSmtpServer startServer() {
        try {
            return new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.ACCEPT);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    @DynamicPropertySource
    static void configureMail(DynamicPropertyRegistry properties) {
        properties.add("spring.mail.host",
                () -> "127.0.0.1");
        properties.add("spring.mail.port", SMTP::port);
        properties.add("spring.mail.properties[mail.smtp.auth]",
                () -> "false");
        properties.add("spring.mail.properties[mail.smtp.timeout]",
                () -> "500");
        properties.add("spring.mail.properties[mail.smtp.connectiontimeout]",
                () -> "500");
        properties.add("spring.mail.properties[mail.smtp.writetimeout]",
                () -> "500");
    }

    @Test
    void autoConfiguredSenderSubmitsToLocalSmtp() {
        sender.send(sampleMessage());
    }

    @AfterAll
    static void closeServer() throws IOException {
        SMTP.close();
    }
}
~~~

This code illustrates the concept, assuming Spring Boot Mail starter and matching JUnit/Spring Boot test dependencies are present. Adjust helper packages/imports and verify how your Boot version binds `spring.mail.properties[...]` keys. Because the fake server accepts only one connection, this class has one test; for multiple tests, support multiple connections or isolate servers per run.

### Separating Test Layers for Easier Diagnosis

- **Transport-focused tests:** instantiate `JavaMailSenderImpl` directly, one fake server per test.
- **Boot configuration tests:** boot `ApplicationContext` to check `spring.mail.*` and bean wiring.
- **Business integration tests:** add database/outbox and mail dispatcher to test retries/transactions.

Do not restart `ApplicationContext` hundreds of times just to simulate SMTP reply codes if transport-level tests already cover them. Keep context tests focused on real configuration and component wiring.

## 25. Testing Timeouts Inside Business Transactions

A common design mistake:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailSender.send(buildConfirmation(order));
    return order;
}
~~~

If an SMTP read timeout takes several seconds, the database transaction stays open. If the relay accepted the email yet the transaction subsequently rolls back, the recipient may receive confirmation for a non-existent order.

### A More Durable Model

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    outboxRepository.save(EmailOutboxMessage.pending(
            "ORDER_CONFIRMED",
            order.getId(),
            order.getCustomerId()));
    return order;
}
~~~

After commit, the worker reads the outbox and submits via `JavaMailSender`. A database + fake SMTP test should verify:

1. The order and outbox record commit together in one transaction.
2. When SMTP times out, the order still exists.
3. The outbox record is not deleted.
4. The worker records `RETRY_PENDING` or the appropriate status.
5. `nextAttemptAt` is stored for later retry without blocking the HTTP request.
6. Once SMTP recovers, the worker submits through the rate limiter.
7. On unknown submission outcomes, it does not retry blindly.

This is an integration test **of how the application reacts to transport behavior**, complementing the earlier `JavaMailSenderImpl` tests.

## 26. Classifying Errors into Retry, Failed, and Unknown

An application may define a policy:

~~~java
public enum MailDeliveryAction {
    RETRY_LATER,
    FAIL_PERMANENT,
    HOLD_FOR_CREDENTIAL_FIX,
    RECONCILE_UNKNOWN,
    SUPPRESS_RECIPIENT,
    IGNORE_OR_DEFER
}
~~~

Example mapping:

| Evidence | Suggested Action |
| --- | --- |
| Connection timeout before connect | Retry with backoff if unexpired |
| Read timeout after EHLO | Temporary retry; body not sent yet |
| Temporary RCPT 451 | Retry per recipient/message policy |
| Permanent RCPT 550 5.1.1 | Optionally suppress recipient; do not retry blindly |
| AUTH 535 with shared credentials | Hold provider lane, fix credentials |
| `MAIL FROM` policy rejected | Hold/config fix; do not suppress recipient |
| Explicit `DATA` 554 | Investigate content/policy; possibly permanent |
| Lost final reply after `DATA` | `RECONCILE_UNKNOWN` |
| Expired email | Do not send, `EXPIRED` |
| Marketing unsubscribed | `SUPPRESSED`, do not call SMTP |
| Missing rate-limit permit | Defer without counting an SMTP attempt |

Specific policies must reflect business domain, provider semantics, and transport outcomes. Never rely solely on `instanceof MailSendException` to decide retries or suppression, because the same subclass wraps many distinct causes.

### Do Not Turn Infrastructure Failures into Address Failures

If SMTP stops responding due to network issues, never set `recipient.valid=false`. If credentials are wrong, never suppress all recipients. If 550 stems from sender policy, never record the mailbox as non-existent. **Misclassification permanently drops valid emails.**

## 27. Exponential Backoff and Retry Caps After Timeouts

Timeouts are often recoverable, yet retries must not fire immediately:

\[
\text{delay}_n = \min(\text{maximum},\,\text{initial} \times 2^{n-1}) + \text{jitter}
\]

Example test policy:

| Attempt | Illustrative Wait Window |
| --- | --- |
| 1 | Send immediately when job is claimed |
| 2 | After ~30-45 seconds |
| 3 | After ~1-2 minutes |
| 4 | After ~3-5 minutes |
| Exhausted `maxAttempts` | `DEAD_LETTER` or policy handling |

Values are illustrative only. Provider limits, OTP/reset-link TTLs, and transaction SLAs govern real schedules. Jitter should use a controllable random source in tests; never assert exact timestamps when production uses randomness.

### Invariants That Should Be Tested

- One timeout never triggers multiple immediate sends.
- `nextAttemptAt` lies in the future per backoff policy.
- `maxAttempts` is never exceeded.
- Expired messages are never retried.
- Retries also pass through rate limiters and concurrency gates.
- Worker crashes/restarts do not reset schedules or attempt counts.
- Unknown SMTP outcomes never automatically take the same "safe-retry" branch as pre-`MAIL FROM` errors.

### Avoid Nested Multi-Layer Retries

If Spring Retry tries 3 times inside the adapter and the outbox retries 5 times, a single message could trigger 15 SMTP calls. Explicitly define physical transport attempts and enforce a total budget. Tests should count **physical SMTP attempts**, not just the outbox attempt counter.

## 28. Timeout and Rejection Test Matrix

When adding or swapping an SMTP provider, maintain a minimum scenario suite. Do not simulate every scenario with one generic exception.

| ID | Injected Fault | Phase | Key Expectation |
| --- | --- | --- | --- |
| T01 | Server returns final 250 | After DATA | `JavaMailSender` submits successfully |
| T02 | TCP connection refused | Connect | Record connection error; do not treat as SMTP reply |
| T03 | TCP packets dropped | Connect | Connection timeout within threshold |
| T04 | Server sends no 220 greeting | Greeting | Read timeout |
| T05 | Server silent after EHLO | EHLO | Read timeout; body never sent |
| T06 | Server silent after MAIL FROM | Envelope | Read timeout; do not infer invalid recipient |
| T07 | Server stops reading body | DATA write | Write timeout / resource cleanup per harness capability |
| T08 | Server returns 421 | Greeting/command | Temporary service failure, backoff |
| T09 | Server returns 451 | RCPT TO | Temporary recipient refusal, retry policy |
| T10 | Server returns 550 5.1.1 | RCPT TO | Permanent recipient failure, no blind retry |
| T11 | Server returns 553 | MAIL FROM | Sender/policy error, do not suppress recipient |
| T12 | Server returns 554 | DATA before 354 | Refusal before body transfer |
| T13 | Server returns 554 | After DATA terminator | Explicit rejection after body |
| T14 | Server closes connection | After DATA terminator, before reply | Outcome unknown, do not auto-resend |
| T15 | Invalid credentials | AUTH | Provider/account-level error, pause mass retries |
| T16 | STARTTLS rejected/unsupported | TLS negotiation | Never downgrade when TLS is required |
| T17 | Certificate hostname mismatch | TLS handshake | Connection blocked per policy |
| T18 | One RCPT accepted, one 550 | Multi-recipient | Partial-send behavior measured accurately |
| T19 | Timeout then process restart | Outbox | Retry schedule/attempts preserved |
| T20 | Multiple workers handling timeouts | Worker/outbox | Concurrency/quotas respected, leased claims |
| T21 | Rate-limit token exhausted before send | Dispatch gate | Deferred without counting an SMTP attempt |
| T22 | SMTP 4xx then recovery | Retry | Backoff/jitter, no burst of thousands of jobs |
| T23 | Email already SUBMITTED and job replayed | Replay | Never arbitrarily re-sent |
| T24 | Complaint/unsubscribe while awaiting retry | Business policy | Suppressed marketing mail not sent |
| T25 | Monitoring/logging active during errors | Observability | Error codes/correlation present, no secrets/bodies leaked |
| T26 | Server very slow without timing out | Performance | Does not hold business transactions open too long |

Scenarios involving TLS, AUTH, network blackholes, and multi-recipient behavior require fixtures/servers supporting those exact faults. Never force a minimal fake server to fake everything and equate results with a production provider.

### Which Tests Should Run Where?

**Every commit / fast CI:**

- Successful sending path.
- Read timeout after EHLO.
- `RCPT` 451/550.
- `DATA` 554 and lost final reply.
- Unit tests for retry/suppression/classifier.

**Deeper integration suite:**

- TLS/AUTH via a capable SMTP test server.
- Database/outbox transactions, leases, and restarts.
- Multi-recipient / partial acceptance.
- Network proxies for connect/write timeouts.

**Controlled staging:**

- Authorized connections to a real provider.
- SMTP credentials, STARTTLS/certificates, `From` authorization.
- Quotas/rate-limits per test agreement.
- Provider-specific enhanced codes and bounce events.

Never start load testing by sending to real mailboxes or using production credentials.

## 29. Observing SMTP State in Tests

A strong test needs evidence across multiple layers:

| Layer | Evidence to Observe |
| --- | --- |
| Fake SMTP server | Did it receive connect, EHLO, MAIL FROM, RCPT TO, DATA? |
| Transport | Did `send` return normally or throw? |
| Classifier | Failure kind/code/recipient scope |
| Worker | Attempts, `nextAttemptAt`, lease owner, terminal status |
| Database | Did domain transaction commit; is outbox record intact? |
| Monitoring | Error counts, timeout latency, SMTP in-flight |
| Business | User-facing response and retry/fallback options |

For instance, a read timeout test that only asserts an SMTP error without verifying the server received EHLO might actually be failing on a wrong port. A permanent RCPT refusal test that only asserts an exception without checking recipient suppression misses operational policy.

### What Should Be Measured and Logged?

A structured log entry might contain:

~~~json
{
  "event": "mail_submission_failed",
  "notificationId": "notif-184",
  "attemptId": "attempt-3",
  "providerKey": "smtp-primary",
  "stage": "RCPT_TO",
  "failureKind": "PERMANENT_RECIPIENT",
  "smtpReplyCode": "550",
  "enhancedStatusCode": "5.1.1",
  "retryable": false
}
~~~

This JSON is illustrative and application-defined. Never log SMTP passwords, access tokens, OTPs, reset links, MIME payloads, or raw server replies containing unnecessary personal data.

### Cause Chains Are Not a Fully Stable Contract

An integration test may inspect the underlying `SocketTimeoutException`, though cause nesting can vary across Jakarta Mail versions and protocol phases. In production adapters, normalize into stable internal error codes, then test:

- Transport tests verify real timeouts against the fake server.
- Adapter tests verify the matching cause maps properly.
- Business tests assert stable policies like `RETRY_PENDING` or `SUBMISSION_UNKNOWN`.

Separating these layers lets you upgrade frameworks/SMTP providers without coupling every business test to one library's internal exception classes.

## 30. Designing Timeouts Aligned with SLAs

Overly long timeouts increase wait durations and held threads; overly short ones create false failures when a healthy server is slightly slow.

Illustrative example:

- Connection timeout: 3 seconds.
- Read timeout: 5 seconds.
- Write timeout: 5 seconds.
- Worker concurrency: 4.
- HTTP requests do not wait on transactional emails after commit; background workers handle them.

Numbers are illustrative only. When picking real settings, consider:

- SLOs for OTP or reset-link emails.
- Observed provider response times.
- Email/attachment sizes.
- Potential high-latency network conditions.
- Retry budgets and SMTP quotas.
- Worker count and max connections.
- Overall business deadlines and message expiry.

### Timeouts Are Not a Global Deadline

Suppose each read times out after 5 seconds, yet an SMTP transaction performs multiple reads. Total execution time can exceed 5 seconds. Jobs with an overall deadline must record start times and enforce clean abort/status-marking when time runs out.

Moving sending into `@Async` lets HTTP requests finish quickly, yet does not mean mail workers may hang indefinitely. Transport timeouts, bounded executors, and bounded queues remain essential.

### Retries Must Never Exceed Expiry

OTPs may have short lifetimes. If the first send times out and backoff pushes the retry past token expiration, sending an email with a stale token creates a broken user experience. Workers must check `expiresAt` immediately before each attempt.

Transactional emails may retry longer, yet should alert when breaching SLAs. Marketing emails may be cancelled once a campaign ends. Never share one retry policy across all email types.

## 31. Testing Worker Recovery After a Timeout

A timeout error can cause two problems:

1. The message is not sent.
2. Threads/connections/leases are not released, stalling subsequent messages.

Integration tests should verify **the system keeps processing other messages after one send times out**.

### Recovery Scenario

1. Job A hits a read timeout.
2. The worker records retry state for A.
3. The concurrency slot is released.
4. Job B is claimed and sent successfully over another fake SMTP session.
5. The worker keeps running with no visible thread/connection leaks.
6. When due, A is retried per policy.

If the test server supports only one connection, run two server instances or extend the fake harness to accept multiple connections with per-session scripts. Never reuse a closed fake server that only accepted once.

### Do Not Forget finally

Example dispatch with a concurrency gate:

~~~java
if (!smtpSemaphore.tryAcquire()) {
    outbox.defer(notificationId);
    return;
}

try {
    mailSender.send(message);
    outbox.markSubmitted(notificationId);
} catch (MailException exception) {
    outbox.recordTransportFailure(
            notificationId, exception);
} finally {
    smtpSemaphore.release();
}
~~~

This snippet illustrates releasing permits in `finally`. In a real system, separate outbox status-update transactions from SMTP network calls and avoid self-invocation of transactional methods inside the same bean.

### Testing for Thread Leaks

Do not count total JVM-wide threads alone, because frameworks, GC, and test runners spawn threads too. Instead measure:

- Worker thread count of the mail executor.
- Active/in-flight tasks.
- Task queue length.
- Socket connections to fake SMTP.
`PROCESSING` records held past their lease.
- Throughput recovery after a burst of timeouts.

Repeating faults a few hundred times in an isolated environment can uncover resource leaks, though cap iteration counts and durations so CI stays stable.

## 32. Preventing Duplicates When SMTP Outcomes Are Uncertain

When the client misses the final reply after `DATA`, retries can produce duplicates. Defend across layers:

- Use an internal notification ID per business event.
- Enforce a unique constraint on the idempotency key to prevent duplicate enqueues.
- Record every delivery attempt with status and timestamp.
- Claim outbox rows using leases/locking.
- When transport outcome is unknown, keep `SUBMISSION_UNKNOWN`.
- Reconcile against provider message IDs, relay logs, or event APIs if available.
- When a genuine resend is requested, create a new audited request instead of silently resetting the old record.

### Why Message-ID Does Not Guarantee Idempotency

SMTP and mailboxes have no universal rule requiring systems to deduplicate emails based on the `Message-ID` header. A stable `Message-ID` aids tracing/reconciliation, yet cannot replace application state or provider idempotency APIs.

### Testing Double-Claiming

With a lock-capable database, run two workers racing to claim one due notification. One worker must win processing, while the other skips or waits. Mock repositories cannot prove real locking; database/transaction integration tests are required.

Even when claiming is protected, duplicates can still happen if an old worker sends successfully yet crashes before updating status. That is an inherent limit of the SMTP transaction boundary, not a bug in the semaphore alone.

## 33. Testing Server Rejections and Suppression Lists

An SMTP recipient rejection can trigger suppression, provided the scope is accurate.

### Permanent Recipient Refusal

If the test server returns `550 5.1.1` for recipient A:

- Store a normalized reason for A.
- Stop repeatedly sending to A.
- Optionally suppress A per policy.
- Do not suppress B if B had no failure.
- Do not block the entire sender when only one recipient does not exist.

### Temporary Recipient Refusal

If the server returns `451`:

- Keep the email retryable if still eligible.
- Never permanently suppress after a single temporary failure.
- Use backoff and cap attempts.
- Monitor if the same recipient fails repeatedly.

### Policy Rejection

If the server returns `550`/`554` due to sender reputation or content policy, **changing the recipient will not help**. Check SPF/DKIM/DMARC, content, quotas, sending rate, and provider policies. Tests should distinguish simulated provider codes/scenarios rather than tagging every 5xx as `INVALID_ADDRESS`.

### Risk of Wrongful Suppression

Logic like:

~~~java
catch (MailException error) {
    recipientRepository.setEmailInvalid(recipientId);
}
~~~

is wrong: `MailException` could come from a timeout, bad credentials, or network outage. Recipient management should only suppress when backed by proper transport/provider evidence and explicit policy.

## 34. Security and Boundaries When Running SMTP Failure Tests

To avoid impacting real data:

- Bind fake SMTP to loopback or a test container network.
- Never use production SMTP hosts or real credentials.
- Set small yet bounded timeouts.
- Never allow fake relays to forward mail to the Internet.
- Never put personal email addresses into fixtures.
- Never enable protocol debug logs containing AUTH or MIME bodies in shared CI logs.
- Clean up sockets, threads, containers, and queues after tests.
- Isolate test databases/outboxes from production.
- Bound email counts and attachment sizes.
- Never disable TLS verification in production just because a TLS test failed.
- Never assume a fake SMTP test proves a real provider shares identical quotas, timeouts, or enhanced codes.

### When Should Protocol Debugging Be Used?

In an isolated environment, protocol traces help verify which commands were sent and how the server replied. However, traces may capture recipient addresses, subjects, bodies, or AUTH material depending on libraries/settings. Never leave `mail.debug=true` enabled in production. In tests, prefer fake servers recording **command names and phases** instead of full payloads.

### Internet Access Is Not Needed to Test Timeouts

Read timeouts, `RCPT` refusals, `DATA` rejections, and lost final replies can all be reproduced with a local scripted SMTP server. Network connect timeouts may require a fault injector, still kept inside a controlled test network. This makes tests fast, repeatable, and independent of public provider availability.

## 35. Common Mistakes When Writing Integration Tests

### 35.1. Mocking MailSender and Calling It an SMTP Integration Test

Mocks do not traverse SMTP sockets or Jakarta Mail. Use a fake SMTP server to test real transport; mocks remain valuable for unit-testing policies.

### 35.2. Disabling STARTTLS to "Make Tests Pass" and Carrying That Config to Production

Plaintext fakes on localhost are strictly for isolated tests. Production requires provider-mandated TLS.

### 35.3. Testing Connect Timeout Using a Port with No Listener

Closed ports usually cause connection refused. To test connect timeouts, simulate dropped/blackholed connections.

### 35.4. Testing Write Timeout with a Tiny Email

TCP buffers can absorb the whole body without triggering a write timeout. Use network injectors/buffer controls for deterministic results.

### 35.5. Asserting Overly Rigid Exception Classes/Causes

Transport/provider versions may wrap exceptions differently. Test stable classification at the adapter layer and socket behavior in transport tests.

### 35.6. Using Thread.sleep and Tight Timing Assertions

Slow CI, scheduling, and network stacks add jitter. Use fake clocks for retries, reasonable upper bounds, and events/latches for concurrency.

### 35.7. Not Checking Which Commands the Fake Server Received

A "read timeout" test might actually be failing on a wrong port. Measure command progression: `EHLO`, `MAIL FROM`, `RCPT TO`, `DATA`.

### 35.8. Returning One 550 Code for Every Phase

`RCPT` rejections and `MAIL FROM` rejections carry different failure scopes. Fake servers must script the exact phase.

### 35.9. Assuming Failed send() Means Definitely Not Sent

If the final reply after `DATA` is lost, the client does not know if the relay accepted it. Blind retries can duplicate emails.

### 35.10. Treating Successful send() as Delivered

A relay's final 250 confirms submission acceptance at that hop, not inbox delivery. Bounces can still occur later.

### 35.11. Not Cleaning State Between Tests

Outbox records, fake server connections, executors, or Redis limiters from an earlier test can skew later ones. Use isolation and cleanup.

### 35.12. Testing Multiple Workers with Per-JVM Limiters Only

Aggregate throughput may exceed quotas. Cluster-wide concurrency tests must use shared limiters/DB claims.

### 35.13. Letting SMTP AUTH Failures Cause Retry Storms

Bad credentials do not heal by retrying lots of emails. Pause the lane, fix the secret, then resume the backlog.

### 35.14. Retrying 4xx Immediately

An overloaded server struggles even harder to recover. Apply exponential backoff, jitter, and rate limiting.

### 35.15. Holding DB Transactions Open During SMTP Timeouts

Increases lock contention and fails to synchronize SMTP with the database. Persist the outbox alongside business writes and send after commit.

### 35.16. Not Testing That Workers Keep Running After a Timeout

One failing message can leak a concurrency slot and stall subsequent messages. Verify cleanup, release, and throughput recovery.

### 35.17. Using Real Providers for Mass Rejection Tests

This can violate quotas, damage sender reputation, or affect real recipients. Use fake servers or authorized staging.

### 35.18. Ignoring Partial Acceptance Across Multiple Recipients

When one address is rejected, never automatically assume all recipients failed or all succeeded.

### 35.19. Counting Missing Permits as SMTP Failures

If the worker never called `send` because the limiter lacked tokens, do not increment SMTP attempts or suppress recipients.

### 35.20. Marking Emails Delivered to Inbox Simply Because No Bounce Arrived

Lack of a bounce does not prove successful delivery. Distinguish submission outcomes from provider delivery events.

## 36. Runbook for Production SMTP Timeouts

When timeout rates spike abnormally, prioritize pinpointing the failing stage and reducing blast radius before increasing retries:

1. **Identify timeout type:** TCP connect, read after EHLO, TLS handshake, AUTH reply, RCPT reply, DATA write, or final reply after body.
2. **Group scope:** single pod, all workers, one SMTP account, one provider, one recipient domain, or one campaign.
3. **Check networking:** DNS, firewalls, ports, proxies, routing, packet loss, and recent network policy changes.
4. **Check provider:** service health, rate limits, quotas, response latencies, and SMTP reply codes.
5. **Inspect workers:** in-flight sends, connection counts, executor queues, oldest outbox age, and timeout rates.
6. **Shed load if needed:** pause non-essential campaigns, lower concurrency/rate; never expand threads unboundedly.
7. **Protect mandatory emails:** keep the outbox durable; never roll back committed business transactions solely because SMTP errored.
8. **Handle unknowns:** for lost final replies after `DATA`, avoid blind retries.
9. **Controlled recovery:** once SMTP recovers, drain the backlog through rate limiters and backoff to prevent retry storms.
10. **Reconcile:** compare accepted, bounced, deferred, and provider events if available; never infer inbox delivery from submission results.
11. **Postmortem:** identify root cause, tune timeouts/configs/quotas appropriately, and add a regression test.

### Never Blindly Increase Timeouts

Raising read timeout from 5 seconds to 60 seconds can mask an outage while holding workers and connections occupied longer. If the provider is overloaded, waiting longer rarely boosts throughput. Before tuning settings, understand which phase slowed down and your system's deadline budget.

### When Failing Over to Another Provider

If a backup provider exists, route only eligible messages, ensure sender identities and credentials are properly configured, isolate quotas, and never auto-retry messages with unknown outcomes. Failover does not eliminate duplicate or privacy risks; trace attempts per provider.

## 37. Runbook for Active SMTP Server Rejections

Spikes in 4xx or 5xx errors require different responses depending on code and phase:

### If 421/451/452 Spikes

- Determine whether the error comes from the provider, network, or recipients.
- If throttled, slow down and apply exponential backoff with jitter.
- Check backlog, quotas, and connection concurrency.
- Avoid firing thousands of simultaneous retries.
- Track incident duration and recovery rate.

### If 550 5.1.1 Spikes at RCPT TO

- Group by list source, recipient domain, and timestamp.
- Check whether addresses were verified.
- Suppress genuinely invalid addresses per policy.
- Do not keep retrying the same address endlessly.
- Do not misdiagnose this as an SMTP password failure.

### If 535 Spikes at AUTH

- Check credentials, SMTP AUTH permissions, account locks, and policy changes.
- Halt futile retries across that provider lane.
- Update/rotate secrets through a secure management system.
- Verify TLS, AUTH, and `From` permissions on a canary send.
- Re-enable the mail dispatcher behind rate limiters.
- Never log or paste passwords into tickets/chats.

### If 554 Spikes After DATA

- Inspect provider feedback on content, attachment sizes, spam/policy, or sender identity.
- Distinguish explicit 554 rejections from lost replies.
- Do not change recipients or resend blindly when content/policy is the cause.
- Use a test server to reproduce the exact phase if possible.
- After fixing, replay with controls and preserve attempt history.

## 38. End-to-End Integration Example: Order Placement and SMTP 451

Suppose a user completes payment. The application must send a confirmation email, yet SMTP returns 451 on `RCPT TO`.

### Expected Design

~~~text
HTTP POST /orders
       |
       v
Business transaction:
  - Save order
  - Save ORDER_CONFIRMED outbox message
       |
       v
COMMIT
       |
       v
Mail worker claims outbox
       |
       v
JavaMailSender -> fake SMTP
       |
       v
RCPT TO -> 451 4.3.0 Try later
       |
       v
Classifier: TEMPORARY_SMTP
       |
       v
Outbox RETRY_PENDING + nextAttemptAt
       |
       v
Worker retries later through limiter
       |
       v
SMTP 250 accepted -> SUBMITTED
~~~

### Business Assertions

- The order still exists after the SMTP failure.
- The outbox holds a notification ID linked to the order.
- The first attempt is recorded as a temporary error.
- Status does not jump to `SUBMITTED` or `DELIVERED` when SMTP returns 451.
- No follow-up send occurs before `nextAttemptAt`.
- After recovery, only one worker claims the record on schedule.
- Once fake SMTP returns final 250, the record can transition to `SUBMITTED`.
- Never mark `DELIVERED` without a provider delivery event.

### Test Pseudocode

~~~java
@Test
void orderSurvivesTemporarySmtpRefusal() {
    // Arrange: fake SMTP returns 451 on RCPT TO
    // and repository/outbox use the test database.
    Order order = orderService.placeOrder(command);

    // Domain transaction has committed.
    assertTrue(orderRepository.existsById(order.getId()));

    // Mail worker processes outbox in a separate transaction.
    mailWorker.dispatchDue();

    EmailOutboxRecord record = outboxRepository
            .findByBusinessKey("ORDER_CONFIRMED", order.getId())
            .orElseThrow();

    assertEquals(OutboxStatus.RETRY_PENDING,
            record.getStatus());
    assertTrue(record.getNextAttemptAt().isAfter(clock.instant()));
    assertTrue(orderRepository.existsById(order.getId()));
}
~~~

`OrderService`, `MailWorker`, `EmailOutboxRecord`, repositories, and `Clock` are project-defined components; this example illustrates required assertions and is **not a standalone runnable test without domain models**.

### Which Parts Must Be Integration-Tested?

To trust the result, you need:

- Real SMTP transport tests via a fake server returning 451.
- Policy classifier tests mapping 451 to temporary failure.
- DB/outbox tests persisting status/`nextAttemptAt` in real transactions.
- Optional end-to-end tests orchestrating the full flow with fake SMTP and a test database when high confidence is required.

Mocking all three components and verifying method calls does not prove the transaction/SMTP boundary works.

## 39. Implementation and Acceptance Checklist

Before shipping timeout and SMTP refusal handling to production, the team should verify:

| Item | What to Verify |
| --- | --- |
| Host, port, and TLS mode | Match the right provider and environment? |
| Timeouts | Are connect/read/write timeouts configured appropriately? |
| Connection refused | Distinguished from connect timeouts? |
| Read timeout | Tested with a server stalling on a specific command? |
| Write timeout | Does fault injection genuinely block socket writes? |
| 4xx | Retries use backoff, jitter, and `maxAttempts`? |
| 5xx | Classified accurately across recipient/content/auth scopes? |
| AUTH failures | Avoid retry storms and secret leaks? |
| TLS failures | Fail closed instead of downgrading? |
| Lost `DATA` reply | Covered by `SUBMISSION_UNKNOWN`/duplicate policy? |
| Multi-recipient | Partial acceptance behavior verified? |
| Outbox | Mandatory emails persisted in the same business transaction? |
| Retry state | Durable across restarts? |
| Rate/concurrency | Do retries and replays pass through the same limiter? |
| Expiry/suppression | Expired OTPs and unsubscribed marketing emails skipped? |
| Metrics/logs | Include phase, category, reason, and correlation without leaking PII? |
| Test cleanup | Sockets, threads, DB containers, and queues closed? |
| Provider events | Never confuse submitted with delivered? |

This checklist is a test-planning aid; each row is only satisfied when backed by corresponding test results or observations. If a project does not yet need multi-recipient handling or TLS AUTH in a fake server, split the suite by tier while clearly documenting verified boundaries.

## 40. Self-Check Questions

**1. Why is mocking `JavaMailSender` insufficient for testing SMTP timeouts?**

Because mocks open no TCP connections and run no Jakarta Mail SMTP protocol. They only test business logic when an exception is thrown, without verifying timeout settings or protocol phases.

**2. What is the difference between a connect timeout and connection refused?**

A connect timeout means failing to finish establishing a connection before the deadline; connection refused is typically a fast rejection from the OS or network hop. An unlistened port usually yields refused, not a timeout.

**3. What does `mail.smtp.timeout` do?**

It is the socket read timeout in common Jakarta Mail SMTP implementations, bounding how long the client waits for server response bytes.

**4. Is `mail.smtp.writetimeout` easy to test with a short body?**

No. TCP buffers can absorb the entire body even if the server stops reading. Use a network fault injector/buffer control or a bounded large payload.

**5. Do the three timeout properties create an overall deadline for `send()`?**

Not necessarily. Multiple read/write steps can accumulate; enforce an overall job deadline at a higher layer when total SLAs apply.

**6. How do SMTP 451 and SMTP 550 differ?**

451 is typically a temporary failure; 550 is a permanent rejection for the current request depending on context. Inspect phase, enhanced status, and provider rules before deciding retry vs. suppression.

**7. If 550 occurs on `MAIL FROM`, should the recipient be marked invalid?**

No. Errors on `MAIL FROM` involve the sender/envelope/policy and do not prove anything is wrong with the recipient.

**8. Why test rejections both before and after `DATA`?**

Because certainty about how far the message traveled differs. Errors before `DATA` never sent the body; after the body, explicit rejections must be separated from lost final replies.

**9. What can losing the final reply after the `DATA` dot terminator cause?**

The application does not know whether the relay received the message. Blind retries can send duplicates. `SUBMISSION_UNKNOWN` and reconciliation may be needed.

**10. Does the `Message-ID` header guarantee no duplicates are sent?**

No. It helps tracing, yet SMTP and mailboxes have no universal rule deduplicating messages by `Message-ID`.

**11. When `RCPT TO` returns 550 for one of two recipients, can we treat both as failed?**

Do not guess. Partial acceptance depends on transport configuration and server behavior; test per recipient and policy.

**12. If SMTP AUTH fails, should we retry all emails with the old password?**

No. That risks an authentication storm. Fix credentials/permissions, keep messages in the outbox, and resume dispatch under controls.

**13. Why not disable TLS when encountering certificate errors?**

That downgrades security and can expose credentials and contents. Fix trust, hostname, and TLS settings per provider requirements.

**14. What does a read timeout after EHLO prove?**

The client connected to the server, sent EHLO, and did not receive a timely reply. If the fake server received no `MAIL FROM`/`DATA`, you confirm the body was not submitted.

**15. Why use dynamic ports in SMTP tests?**

To reduce collisions across concurrent tests or processes. Close listeners cleanly to avoid leaking ports or threads.

**16. Should we assert a read timeout takes exactly 250 ms?**

No. Latencies include scheduling, startup, and overhead. Assert the failure mode and a reasonable upper bound, using deterministic fault injection.

**17. Does `JavaMailSender.send()` returning normally mean delivered?**

No. It usually proves the relay accepted the submission per its response; inbox delivery is a later stage.

**18. Why use a transactional outbox when sending email after placing an order?**

So the email-send intent commits atomically with the business transaction while SMTP runs post-commit; timeouts never roll back completed orders or lose send requests.

**19. Does a missing rate-limit token count as an SMTP attempt?**

Not if transport was never called. That is a limiter deferral; do not record an SMTP send failure.

**20. Why cap `maxAttempts` and add jitter?**

To prevent infinite retries and avoid many workers retrying simultaneously and overwhelming SMTP.

**21. How do we verify the system stays healthy after a message times out?**

Measure worker slots, socket/thread cleanup, outbox state, and ability to send the next message successfully. Catching an exception alone does not prove resources were freed.

**22. Why avoid running fault-injection tests against production SMTP?**

It can impact quotas, sender reputation, recipients, or live services. Use fake SMTP or authorized test providers.

**23. Can `@Async` solve all timeout problems?**

No. `@Async` offloads calls to an executor; sockets can still block, queues can fill, and in-memory tasks can vanish on crash. Transport timeouts, bounded executors, and outboxes remain essential.

**24. When a server returns 4xx yet the provider is already retrying an accepted message, should the application resend?**

Do not generate a fresh duplicate while the provider still owns the message and is retrying downstream. Determine whether the failure occurred before submission or as a post-acceptance deferral.

**25. What is the single most important step to avoid misclassifying SMTP errors?**

Record evidence of the protocol phase, reply/enhanced status, and transport cause; normalize at the adapter before applying retry/suppression policies.

## Conclusion

**Testing timeouts and server rejections in Spring Framework Mail must cross the real SMTP boundary and simulate failures at the exact protocol phase.** Distinguish connect, read, and write timeouts from 4xx/5xx server refusals; use `JavaMailSenderImpl` against a scripted SMTP server to exercise `EHLO`, `RCPT TO`, `DATA`, and final replies. Add TLS/AUTH, multi-recipient, network fault-injection, and Spring Boot configuration tests as needed. At the application layer, verify transactional outboxes, error classification, backoff/jitter retries, protecting recipients from wrongful suppression, preventing retry storms, and holding `SUBMISSION_UNKNOWN` when a relay may have accepted the message before the reply was lost. Finally, use metrics, correlated logs, resource cleanup, and outage-recovery scenarios to prove the system not only detects failures, but **recovers safely without losing critical emails or creating uncontrolled duplicates**.
