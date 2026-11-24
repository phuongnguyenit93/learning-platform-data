# Testing Multiple Recipients and Failing Recipients

Sending an email to multiple recipients is very common in Spring Framework Mail applications: a message with multiple `To`, `Cc`, `Bcc` addresses, or a batch of multiple distinct `MimeMessage` objects. The tricky part is that **one address can be accepted by the SMTP server while another address is rejected**. If a test only checks whether `JavaMailSender.send(...)` throws an exception, we do not know which recipients the server accepted, whether the message payload was transmitted, or whether retrying will cause duplicates.

**Integration testing multiple recipients and failing recipients** must observe both the **SMTP envelope and `RCPT TO` command replies**, not merely inspect the `To` header of `MimeMessage`. A test SMTP server can be scripted to return `250` for valid addresses, `450` for temporary failures, and `550` for rejected addresses. That way, tests reproduce the real behavior of Jakarta Mail transport and the exceptions wrapped by Spring Mail.

This guide walks from basic to advanced testing: constructing MIME messages for `To/Cc/Bcc`, distinguishing headers from the envelope, verifying `mail.smtp.sendpartial` policies, inspecting `MailSendException` and `SendFailedException`, building a test SMTP server with scripted per-recipient rejections, and designing duplicate-free retries. All examples use fake emails and loopback SMTP without sending real mail to customers.

## 1. Integration Testing Objectives

After this guide, a strong test suite should prove:

1. The application populates the expected `To`, `Cc`, and `Bcc` addresses in the message.
2. The SMTP transport attempts to deliver to the exact expected recipient set via `RCPT TO` commands.
3. The test server can accept or reject individual recipients with controlled reply codes.
4. When one recipient is rejected, the application exhibits the exact behavior configured by `mail.smtp.sendpartial`.
5. Jakarta Mail failures are observed and correlated with `MailSendException`/`SendFailedException` as appropriate.
6. The application does not confuse **one failed message** with **every recipient failing**.
7. Workers do not automatically retry recipients that the server may already have accepted.
8. Status is never labeled `DELIVERED` solely because the test SMTP server returned `250` after `DATA`.

### What Lies Outside Test Scope?

A test SMTP server only proves the application interacts with **that test server** as scripted. It does not guarantee Gmail, Microsoft 365, or another production provider enforces identical policies, nor does it prove the email will land in Inbox, avoid spam filters, or avoid bouncing hours later.

## 2. Distinguishing Notification, Message, and SMTP Envelope

Three levels frequently get conflated:

| Level | Example | Meaning |
| --- | --- | --- |
| **Notification** | `notificationId=N-100` | One sending request managed by the application |
| **Message** | One `MimeMessage` with `To: a, b` | Content and headers of a single email |
| **SMTP recipient** | Two `RCPT TO` commands for `a` and `b` | Recipient address in the SMTP envelope |

One notification may produce one message, yet one message can still carry multiple recipients. One batch may contain multiple messages, each with multiple recipients. Thus, at least three distinct counts exist:

- Number of notifications.
- Number of `MimeMessage` objects attempted.
- Number of SMTP recipient addresses accepted/rejected.

Never use a single `failedMessages.size()` counter to conclude how many email addresses were rejected.

## 3. To, Cc, Bcc, and SMTP Envelope Recipients

With Spring Mail:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setTo(new String[] {
        "primary-a@example.net",
        "primary-b@example.net"
});
helper.setCc("manager@example.net");
helper.setBcc("audit@example.net");
```

The application populates recipient details inside `MimeMessage`. During transport send, Jakarta Mail uses those addresses to build SMTP envelope `RCPT TO` commands.

An illustrative SMTP session:

```text
S: 220 localhost ESMTP test server
C: EHLO application.test
S: 250-localhost
S: 250 SIZE 10000000
C: MAIL FROM:<notice@example.org>
S: 250 2.1.0 Sender OK
C: RCPT TO:<primary-a@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<primary-b@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<manager@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<audit@example.net>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: [MIME message bytes]
C: .
S: 250 2.0.0 Message accepted for relay
```

This is a **simulated** SMTP session. The line `250 2.0.0` after `DATA` only means that server accepted the message for further processing, not confirmation that recipients read the email.

### Why Test Bcc Separately?

`Bcc` is an envelope recipient that must not be publicly displayed like `To/Cc` in the copy seen by other recipients. Tests should separate:

- **Envelope test:** was the Bcc address included in `RCPT TO`?
- **Recipient-visible header test:** did the data seen by recipient mail clients expose `Bcc`?

Do not infer SMTP behavior solely from `message.getRecipients(...)`, and do not treat pre-send `message.writeTo(...)` as final proof that `Bcc` was stripped from transmitted data. Inspect the message received by the test SMTP server and/or the corresponding transport step.

## 4. An Invalid-Policy Recipient Differs from Invalid Syntax

There are two kinds of "invalid recipient":

| Kind | Example | When Detected |
| --- | --- | --- |
| Syntax error | `not-an-email` or invalid address per parser/validation | Typically blocked while building the message |
| Valid syntax yet server-rejected | `blocked@example.net` | Typically at the SMTP `RCPT TO` command |

To test an **SMTP-rejected recipient**, use a **syntactically valid** address configured on the test server to return an error code. If you pass a syntactically invalid address into `MimeMessageHelper` and it throws `AddressException` before connecting, the test never exercises SMTP rejection behavior.

`InternetAddress.validate()` checks syntax only; it cannot verify whether a mailbox exists or whether a provider will accept mail. Never send to real addresses just to watch them bounce.

## 5. How Does SMTP Reply per Recipient?

Common reply codes at `RCPT TO`:

| Reply | General Interpretation | Suggested Test Policy |
| --- | --- | --- |
| `250 2.1.5` | Recipient accepted at `RCPT` step | Allow proceeding |
| `450 4.2.0` | Temporary rejection | Record retryable error |
| `451 4.3.0` | Temporary server error | Verify backoff |
| `550 5.1.1` | Explicit recipient rejection | Do not retry the same address blindly |
| `553` | Address error per server policy | Inspect cause and input data |

SMTP codes vary by server, command, and enhanced status code. Never turn an example table into rigid rules for every provider. Some servers return `550` for relay policies, while others reject addresses only after receiving the message.

### Distinguishing RCPT TO from DATA

```text
MAIL FROM -> server learns sender
RCPT TO   -> server accepts or rejects each recipient
DATA      -> client sends MIME bytes if transport continues
250 DATA  -> server accepts the message in that transaction
```

A server returning `250` for a `RCPT TO` does not mean it received the content. If the client never sends `DATA`, that recipient has not had a message submitted successfully in that transaction.

## 6. Default Behavior When a Recipient Is Rejected

Jakarta Mail SMTP transport has the `mail.smtp.sendpartial` property. When it is `false` (the default in common setups), if one or more recipients are rejected, the transport typically **does not send `DATA` for the entire message**; it reports an error rather than continuing only with accepted recipients.

Example:

```text
RCPT TO:<a@example.net>       -> 250
RCPT TO:<blocked@example.net> -> 550
RCPT TO:<c@example.net>       -> 250
                                      |
                                      v
                       sendpartial=false
                       Do not send DATA for message
                       Throw SendFailedException
```

What to check in integration tests is **whether the server received `DATA`**, not merely which `RCPT TO` commands returned `250`. A recipient that received `250` at `RCPT` without `DATA` still received no message content in that transaction.

### What Test Fits?

Given a message with:

- `accepted-a@example.net`: server returns `250`.
- `blocked@example.net`: server returns `550`.
- `accepted-c@example.net`: server returns `250`.

With `sendpartial=false`, the test expects:

1. The server observes `RCPT` commands for the recipients per transport behavior.
2. A rejection response for `blocked@example.net` occurs.
3. The server **accepts no `DATA`** for that message.
4. `JavaMailSender` reports a send failure.
5. The application preserves correlation to handle each case.

Never claim `accepted-a` succeeded merely because it received `250` at the `RCPT` step.

## 7. Behavior When mail.smtp.sendpartial Is Enabled

When `mail.smtp.sendpartial=true`, Jakarta Mail SMTP transport can proceed to send the message to accepted recipients even when other addresses are rejected. Afterwards, the transport **may still throw `SendFailedException`** to report partial failure.

```text
RCPT TO:<accepted-a@example.net> -> 250
RCPT TO:<blocked@example.net>    -> 550
RCPT TO:<accepted-c@example.net> -> 250
                                         |
                                         v
                            sendpartial=true
                            DATA -> 250 accepted
                            Record partial failure
```

This creates a major difference for retries:

- `accepted-a` and `accepted-c` were reported as submitted to the SMTP server in that test transaction.
- `blocked` was rejected at `RCPT`.
- Retrying the exact same message to all three would send duplicates to the already-accepted recipients.

**Never infer that `sendpartial=true` makes `send(...)` return cleanly with full success.** Callers must still observe exceptions and partition recipients.

## 8. Configuring JavaMailSenderImpl for Integration Tests

You can create a sender pointing to a local SMTP server on a test-allocated port:

```java
import org.springframework.mail.javamail.JavaMailSenderImpl;

static JavaMailSenderImpl testSender(
        int smtpPort,
        boolean allowPartial
) {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(smtpPort);
    sender.setProtocol("smtp");
    sender.setDefaultEncoding("UTF-8");

    var properties = sender.getJavaMailProperties();
    properties.setProperty("mail.smtp.auth", "false");
    properties.setProperty(
            "mail.smtp.connectiontimeout", "3000");
    properties.setProperty("mail.smtp.timeout", "3000");
    properties.setProperty("mail.smtp.writetimeout", "3000");
    properties.setProperty(
            "mail.smtp.sendpartial",
            Boolean.toString(allowPartial));

    return sender;
}
```

In this test:

- Host `127.0.0.1` guarantees we never accidentally call production SMTP.
- Port is dynamically allocated by the test server to reduce collisions across tests.
- AUTH/TLS are disabled because the minimal test server does not support them.
- Finite timeouts prevent tests from hanging forever if a protocol handler stalls.
- `sendpartial` is set explicitly in each scenario.

Testing TLS, credentials, and SMTP AUTH requires a test SMTP server supporting those features; never use a plaintext fake server to conclude production security is valid.

## 9. Building a Message with Multiple To/Cc/Bcc Recipients

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

static MimeMessage buildMultiRecipientMessage(
        JavaMailSenderImpl sender
) throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("notice@example.org");
    helper.setTo(new String[] {
            "accepted-a@example.net",
            "blocked@example.net"
    });
    helper.setCc("accepted-c@example.net");
    helper.setBcc("private-copy@example.net");
    helper.setSubject("Recipient test notification");
    helper.setText(
            "This is an internal test email, never sent to the Internet.",
            false
    );

    return message;
}
```

For notifications without attachments, `multipart=false` suffices for recipient tests. Verifying `RCPT TO` envelopes does not depend on whether the email is plain text or `multipart/alternative`. Start with plain text to isolate recipient behavior, then add multipart if business logic requires it.

### setTo Differs from addTo

`helper.setTo(...)` replaces the `To` recipient set, while `helper.addTo(...)` appends addresses. If the application builds the list across multiple steps, verify the final set has no missing or duplicate addresses. Never assume repeated `setTo` calls accumulate recipients.

## 10. Inspecting Recipients in the Message Before Sending

Reading recipient details from the message verifies the composer before transport runs:

```java
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;

static List<String> addresses(
        MimeMessage message,
        Message.RecipientType type
) throws MessagingException {
    Address[] result = message.getRecipients(type);
    if (result == null) {
        return List.of();
    }
    List<String> emails = new ArrayList<>();
    for (Address address : result) {
        emails.add(((InternetAddress) address)
                .getAddress()
                .toLowerCase(Locale.ROOT));
    }
    return emails;
}
```

Example assertions:

```java
assertEquals(
        Set.of("accepted-a@example.net", "blocked@example.net"),
        Set.copyOf(addresses(message, Message.RecipientType.TO))
);
assertEquals(
        List.of("accepted-c@example.net"),
        addresses(message, Message.RecipientType.CC)
);
assertEquals(
        List.of("private-copy@example.net"),
        addresses(message, Message.RecipientType.BCC)
);
```

These assertions check **MIME recipient field construction**, not that the server received those addresses. Next, verify the SMTP conversation against a local server.

## 11. Choosing a Test SMTP Server for Each Goal

Not every test SMTP server makes it easy to **reject one specific recipient**:

| Tool / Approach | Strengths | Known Limitations |
| --- | --- | --- |
| **GreenMail** | In-JVM test SMTP server, stores received messages, supports send/receive tests | `RCPT TO` rejection scripting depends on scenario/API; requires suitable setup |
| **Mailpit / MailHog** | Very convenient for capturing and viewing test emails | Not designed out-of-the-box to script every per-recipient error code |
| **Custom scripted SMTP server** | Specifies exact replies per `RCPT TO` command | Only an SMTP subset, never replaces a production provider |
| **Provider sandbox** | Closest to a specific vendor's rules | May not emit exact deterministic error scenarios |
| **Mockito mock `JavaMailSender`** | Fast checks of application exception branches | Does not test real protocol over sockets |

For inspecting received message content, GreenMail/Mailpit fit very well. For testing **per-recipient failures and `sendpartial`**, a test SMTP server that actively replies `250`, `450`, `550` at `RCPT TO` yields clear, repeatable results.

In the following examples, we use a minimal Java server on `127.0.0.1`, started fresh per test. It performs no auth, no TLS, and no Internet relaying.

## 12. Building a Simple Scripted SMTP Server for Integration Tests

The following server implements the minimal protocol subset needed for tests: banner, `EHLO`/`HELO`, `MAIL FROM`, `RCPT TO`, `DATA`, `RSET`, and `QUIT`. Each recipient can be assigned a reply code via a `Map`; unconfigured recipients are accepted.

### 12.1. The Test Server Class

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public final class ScriptedSmtpServer implements AutoCloseable {

    private final ServerSocket listener;
    private final ExecutorService executor;
    private final Map<String, Integer> replies;
    private final List<String> observedRecipients =
            new CopyOnWriteArrayList<>();
    private final List<String> acceptedRecipients =
            new CopyOnWriteArrayList<>();
    private final List<String> rejectedRecipients =
            new CopyOnWriteArrayList<>();
    private final List<String> receivedMime =
            new CopyOnWriteArrayList<>();
    private final AtomicInteger dataAccepted = new AtomicInteger();
    private volatile IOException serverFailure;

    public ScriptedSmtpServer(Map<String, Integer> replies)
            throws IOException {

        this.replies = replies;
        this.listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress());

        this.executor = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "test-smtp");
            t.setDaemon(true);
            return t;
        });
        executor.submit(this::serveOneConnection);
    }

    public int port() {
        return listener.getLocalPort();
    }

    public List<String> observedRecipients() {
        return List.copyOf(observedRecipients);
    }

    public List<String> acceptedRecipients() {
        return List.copyOf(acceptedRecipients);
    }

    public List<String> rejectedRecipients() {
        return List.copyOf(rejectedRecipients);
    }

    public int acceptedDataCount() {
        return dataAccepted.get();
    }

    public List<String> capturedMime() {
        return List.copyOf(receivedMime);
    }

    public IOException serverFailure() {
        return serverFailure;
    }

    private void serveOneConnection() {
        try (Socket client = listener.accept()) {
            client.setSoTimeout(5000);

            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));

            PrintWriter output = new PrintWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.US_ASCII),
                    true);

            output.print("220 localhost ESMTP test server\r\n");
            output.flush();

            String line;
            boolean readingData = false;
            int currentAccepted = 0;
            StringBuilder mime = new StringBuilder();

            while ((line = input.readLine()) != null) {
                if (readingData) {
                    if (".".equals(line)) {
                        receivedMime.add(mime.toString());
                        dataAccepted.incrementAndGet();
                        mime.setLength(0);
                        readingData = false;
                        currentAccepted = 0;
                        reply(output, "250 2.0.0 Message queued");
                    } else {
                        // Store test fixtures only; never use this server
                        // to receive real emails containing PII.
                        mime.append(line).append("\r\n");
                    }
                    continue;
                }

                String upper = line.toUpperCase(Locale.ROOT);

                if (upper.startsWith("EHLO ")) {
                    output.print("250-localhost\r\n");
                    output.print("250 SIZE 10000000\r\n");
                    output.flush();
                } else if (upper.startsWith("HELO ")) {
                    reply(output, "250 localhost");
                } else if (upper.startsWith("MAIL FROM:")) {
                    currentAccepted = 0;
                    reply(output, "250 2.1.0 Sender OK");
                } else if (upper.startsWith("RCPT TO:")) {
                    int start = line.indexOf('<');
                    int end = line.indexOf('>', start + 1);

                    String address = (start >= 0 && end > start)
                            ? line.substring(start + 1, end)
                            : line.substring(8).trim();

                    address = address.toLowerCase(Locale.ROOT);
                    observedRecipients.add(address);

                    int code = replies.getOrDefault(address, 250);
                    if (code == 250) {
                        acceptedRecipients.add(address);
                        currentAccepted++;
                        reply(output, "250 2.1.5 Recipient OK");
                    } else {
                        rejectedRecipients.add(address);
                        if (code >= 400 && code < 500) {
                            reply(output,
                                    code + " 4.2.0 Temporary rejection");
                        } else {
                            reply(output,
                                    code + " 5.1.1 Recipient rejected");
                        }
                    }
                } else if (upper.equals("DATA")) {
                    if (currentAccepted == 0) {
                        reply(output,
                                "554 5.5.1 No accepted recipient");
                    } else {
                        reply(output, "354 End data with <CRLF>.<CRLF>");
                        readingData = true;
                    }
                } else if (upper.equals("RSET")) {
                    currentAccepted = 0;
                    reply(output, "250 2.0.0 Reset");
                } else if (upper.equals("NOOP")) {
                    reply(output, "250 2.0.0 OK");
                } else if (upper.equals("QUIT")) {
                    reply(output, "221 2.0.0 Bye");
                    break;
                } else {
                    reply(output, "502 5.5.2 Command not supported");
                }
            }
        } catch (IOException ex) {
            // If the test closes the listener while waiting on accept,
            // shutdown failures can be expected.
            if (!listener.isClosed()) {
                serverFailure = ex;
            }
        }
    }

    private static void reply(PrintWriter out, String response) {
        out.print(response);
        out.print("\r\n");
        out.flush();
    }

    @Override
    public void close() throws IOException {
        listener.close();
        executor.shutdownNow();
    }
}
```

### What Can This Test Server Do?

- OS-assigned random port so tests do not share a fixed port.
- Listens for **one** SMTP connection; each test starts its own server.
- Accepts and rejects recipients with specific reply codes.
- Records which recipients the transport attempted at `RCPT TO`.
- Distinguishes recipients receiving `250` at `RCPT` from **actually accepted `DATA`**.
- Retains MIME **for fake fixtures only** to inspect headers if needed.
- Enforces timeouts and closes sockets automatically in `try-with-resources`.

### What Can This Server Not Do?

It does not implement the full SMTP RFC, STARTTLS, AUTH, ESMTP extensions, message size limits, real queues, delivery, or bounces. Notably, `receivedMime` is built from lines read using the ASCII charset and is **not a true byte-level capture for arbitrary 8-bit messages**. In these tests we only use synthetic content and fake addresses; to test binary fidelity or MIME encoding, use GreenMail or a standard SMTP capture server.

Because the server accepts only one connection and simple test transactions, never use it in production or complex multi-session tests. You can extend it to accept multiple connections if testing connection pooling and concurrency, though that is a separate topic.

## 13. Test 1: All Recipients Accepted

The first integration test verifies `JavaMailSenderImpl` communicates with the server over a socket and sends `DATA` when all recipients receive `250`:

```java
import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

@Test
void submitsMessageWhenAllRecipientsAccepted() throws Exception {
    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(Map.of())) {

        var sender = testSender(smtp.port(), false);
        var message = buildMultiRecipientMessage(sender);

        // Server defaults to 250 for all RCPTs in this test.
        assertDoesNotThrow(() -> sender.send(message));

        assertEquals(1, smtp.acceptedDataCount());
        assertEquals(
                Set.of(
                        "accepted-a@example.net",
                        "blocked@example.net",
                        "accepted-c@example.net",
                        "private-copy@example.net"
                ),
                Set.copyOf(smtp.observedRecipients())
        );
        assertTrue(smtp.rejectedRecipients().isEmpty());
    }
}
```

What this test proves:

1. Spring Mail established an SMTP session with the local server.
2. Transport sent the exact expected `RCPT TO` set.
3. The server received one `DATA` phase and returned accepted.

It does **not** prove the emails reached Inboxes; the fake server merely stores `DATA` in memory.

### Checking Bcc

In this test, `private-copy@example.net` appears in `observedRecipients()`, proving `Bcc` went through the SMTP envelope. To confirm the transport omitted the `Bcc` header from the message received by the server, inspect `smtp.capturedMime()` in the test environment:

```java
String captured = smtp.capturedMime().get(0);

String headerBlock = captured.split("\\r?\\n\\r?\\n", 2)[0];

assertTrue(headerBlock.lines()
        .noneMatch(line ->
                line.regionMatches(true, 0, "Bcc:", 0, 4)));
```

The test splits **the header block before the blank line** and verifies no line starts with `Bcc:` regardless of casing. Never search for `"bcc:"` across the entire body, as the body might happen to contain that text. With real messages, never log raw `DATA` just to check `Bcc`.

## 14. Test 2: One Recipient Gets 550, sendpartial=false

Suppose `blocked@example.net` receives `550` from the server while the other three addresses receive `250`.

```java
import org.springframework.mail.MailSendException;

@Test
void rejectsWholeMessageWhenOneRecipientInvalidAndPartialOff()
        throws Exception {

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(
                         Map.of("blocked@example.net", 550))) {

        var sender = testSender(smtp.port(), false);
        var message = buildMultiRecipientMessage(sender);

        MailSendException exception = assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertTrue(
                smtp.rejectedRecipients()
                        .contains("blocked@example.net")
        );

        assertEquals(
                0,
                smtp.acceptedDataCount(),
                "No DATA should be accepted with sendpartial=false"
        );

        assertFalse(
                exception.getFailedMessages().isEmpty(),
                "Spring should report the failed MimeMessage"
        );
    }
}
```

This is a central scenario: recipients receiving `250` at `RCPT` **do not imply** the message was sent to them. Because `sendpartial=false`, the transport may decline to send `DATA` for the whole message upon seeing one failing recipient.

Test conditions are tightly defined: one connection, one message, server actively returns `550` at `RCPT`, and Jakarta Mail SMTP transport uses the default non-partial configuration. If behavior differs in another library version, inspect the transcript and cause before adjusting expectations.

### Do Not Assert Accepted Recipient Count Equals Sent Message Count

`smtp.acceptedRecipients().size()` counts addresses that got `250` at `RCPT`. `smtp.acceptedDataCount()` counts completed `DATA` submissions at the test server. These are two metrics with **different units** and must never be used interchangeably.

## 15. Test 3: One Recipient Gets 550, sendpartial=true

When partial sends are permitted, the message can be submitted to accepted recipients even though the transport still reports one or more failing addresses.

```java
@Test
void submitsToAcceptedRecipientsWhenPartialEnabled()
        throws Exception {

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(
                         Map.of("blocked@example.net", 550))) {

        var sender = testSender(smtp.port(), true);
        var message = buildMultiRecipientMessage(sender);

        MailSendException failure = assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertTrue(smtp.rejectedRecipients()
                .contains("blocked@example.net"));
        assertTrue(smtp.acceptedRecipients()
                .contains("accepted-a@example.net"));
        assertTrue(smtp.acceptedRecipients()
                .contains("accepted-c@example.net"));
        assertTrue(smtp.acceptedRecipients()
                .contains("private-copy@example.net"));

        assertEquals(
                1,
                smtp.acceptedDataCount(),
                "Valid recipients should receive DATA submission"
        );

        assertFalse(failure.getFailedMessages().isEmpty());
    }
}
```

This is the scenario most prone to duplicates. The caller sees `MailSendException`, yet the test SMTP server already returned `250` after `DATA`. If the application retries **the exact message to all recipients**, already-accepted recipients may receive a duplicate copy.

Never treat `sendpartial=true` as a way to "ignore recipient errors"; it is a **partial-delivery policy choice** that introduces responsibility for tracking per-recipient outcomes.

## 16. Test 4: Recipient Gets 450 (Temporary Error)

To distinguish temporary errors from permanent ones, the scripted server can return `450`:

```java
@Test
void recordsTemporaryRecipientRejection()
        throws Exception {

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(
                         Map.of("blocked@example.net", 450))) {

        var sender = testSender(smtp.port(), false);
        var message = buildMultiRecipientMessage(sender);

        assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertTrue(smtp.rejectedRecipients()
                .contains("blocked@example.net"));
        assertEquals(0, smtp.acceptedDataCount());
    }
}
```

With `sendpartial=false`, transport tests may still skip sending `DATA` for the entire message. The difference between `450` and `550` lies in **root cause and post-failure handling policy**:

- `450` is normally a candidate for bounded retries with backoff.
- `550` normally requires fixing the recipient, policy, or mailing list.

Never test "450 auto-retries" solely via `JavaMailSenderImpl.send(...)` because `JavaMailSender` does not provide a per-recipient retry workflow itself. Retry logic belongs in the application service, worker, or notification state machine and must be tested separately.

## 17. Reading MailSendException and Jakarta Mail Recipient Errors

When `JavaMailSenderImpl` executes SMTP transport, Spring Mail typically translates send failures into `MailSendException`. For a `MimeMessage` with multiple recipients, distinguish:

- `MailSendException.getFailedMessages()`: map of **message object -> exception**.
- `MailSendException.getMessageExceptions()`: message-level exceptions.
- `jakarta.mail.SendFailedException`: can expose valid/invalid recipient details reported by transport.
- Implementation-specific SMTP exceptions: may carry reply codes, SMTP commands, or failing addresses.

**One entry in the failed-messages map does not represent one recipient.** One `MimeMessage` with four recipients where one is rejected may still create **one** failed-message entry.

### Example Reading the Map

```java
try {
    sender.send(message);
} catch (MailSendException ex) {
    Map<Object, Exception> failures =
            ex.getFailedMessages();

    for (Map.Entry<Object, Exception> failure :
            failures.entrySet()) {
        Object messageObject = failure.getKey();
        Exception cause = failure.getValue();

        // Correlate messageObject with notificationId
        // then analyze cause at the Jakarta Mail layer.
    }

    if (failures.isEmpty()) {
        // Empty map does NOT prove send succeeded.
        // May be a general transport error or missing
        // per-message failure details.
    }
}
```

If code only writes `catch (MailSendException)` and ignores `MailAuthenticationException`, it may miss authentication failures. Additionally, MIME construction errors can arise prior to `send` as `MessagingException` or `MailPreparationException` depending on the call path.

## 18. SendFailedException and Three Address Groups

`jakarta.mail.SendFailedException` provides:

```java
Address[] invalid = error.getInvalidAddresses();
Address[] validSent = error.getValidSentAddresses();
Address[] validUnsent = error.getValidUnsentAddresses();
```

Interpretation:

| Group | General Meaning per Transport Report |
| --- | --- |
| `invalidAddresses` | Addresses considered invalid or rejected |
| `validSentAddresses` | Addresses the transport reported as sent at the time of failure |
| `validUnsentAddresses` | Valid addresses not yet sent |

**Warning:** arrays may be `null` or empty depending on the error/implementation; never assume every `SendFailedException` populates all three groups. `validSent` does not prove emails reached Inboxes, and `validUnsent` does not mean addresses have syntax errors.

### Why Do Groups Change with sendpartial?

With `sendpartial=false`, one rejected recipient can stop the transport from sending `DATA` to anyone. Recipients that got `250` at `RCPT` may appear in **validUnsent** because the message was never submitted.

With `sendpartial=true`, the transport can submit `DATA` to accepted recipients and report them as **validSent**, while the rejected address appears in **invalid**. Verify this behavior against the test server and exceptions rather than hard-coding assumptions across all providers.

## 19. Traversing Cause Chains and MessagingException.nextException

Jakarta Mail can chain exceptions through both:

- `Throwable.getCause()`.
- `MessagingException.getNextException()`.

Therefore, calling `ex.getCause()` once may miss a deeper `SendFailedException`.

A test utility:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Queue;
import java.util.Set;

static List<Throwable> causesIncludingNext(Throwable root) {
    Set<Throwable> seen =
            Collections.newSetFromMap(new IdentityHashMap<>());
    Queue<Throwable> pending = new ArrayDeque<>();
    List<Throwable> result = new ArrayList<>();
    pending.add(root);

    while (!pending.isEmpty()) {
        Throwable current = pending.remove();
        if (!seen.add(current)) {
            continue;
        }

        result.add(current);

        if (current.getCause() != null) {
            pending.add(current.getCause());
        }

        if (current instanceof MessagingException messaging) {
            Exception next = messaging.getNextException();
            if (next != null) {
                pending.add(next);
            }
        }
    }

    return result;
}

static List<SendFailedException> findRecipientFailures(
        Throwable root
) {
    List<SendFailedException> result = new ArrayList<>();
    for (Throwable error : causesIncludingNext(root)) {
        if (error instanceof SendFailedException sendFailure) {
            result.add(sendFailure);
        }
    }
    return result;
}
```

The utility uses an identity set to avoid infinite loops on complex cause/next-exception chains. It locates address-level failures without coupling to an implementation-specific exception package.

In production applications, never log full messages or unsanitized exception text: many SMTP errors embed recipient addresses, hosts, or potentially sensitive data.

## 20. Assertions for Recipient Groups

Example converting `Address[]` into an address set while handling `null`:

```java
import jakarta.mail.Address;
import jakarta.mail.internet.InternetAddress;

static Set<String> toAddressSet(Address[] addresses) {
    if (addresses == null) {
        return Set.of();
    }
    Set<String> result = new HashSet<>();
    for (Address address : addresses) {
        result.add(((InternetAddress) address)
                .getAddress()
                .toLowerCase(Locale.ROOT));
    }
    return result;
}
```

Combined with the partial test:

```java
MailSendException exception = assertThrows(
        MailSendException.class,
        () -> sender.send(message)
);

List<SendFailedException> reports =
        findRecipientFailures(exception);

assertFalse(reports.isEmpty());

Set<String> invalid = new HashSet<>();
Set<String> validSent = new HashSet<>();
Set<String> validUnsent = new HashSet<>();

for (SendFailedException report : reports) {
    invalid.addAll(
            toAddressSet(report.getInvalidAddresses()));
    validSent.addAll(
            toAddressSet(report.getValidSentAddresses()));
    validUnsent.addAll(
            toAddressSet(report.getValidUnsentAddresses()));
}

assertTrue(invalid.contains("blocked@example.net"));
```

Stricter assertions like `validSent` equaling all three exact addresses must rely on verified output from your Jakarta Mail implementation and SMTP scenario. If a different exception or empty arrays occur because the transport provided insufficient details, tests should not guess recipient state just to pass.

### Also Test Cases Without Recipient Details

Not every `MailSendException` contains a `SendFailedException`, such as a connection failure before the SMTP handshake. The application must handle `findRecipientFailures(ex)` returning an empty list. Never substitute missing details with "all recipients were sent" or "none were definitely sent" without evidence.

## 21. Test 5: Every Recipient Rejected

An important scenario is when zero recipients get `250`:

```java
@Test
void doesNotSendDataWhenEveryRecipientRejected()
        throws Exception {

    Map<String, Integer> replies = Map.of(
            "accepted-a@example.net", 550,
            "blocked@example.net", 550,
            "accepted-c@example.net", 550,
            "private-copy@example.net", 550
    );

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(replies)) {

        var sender = testSender(smtp.port(), true);
        var message = buildMultiRecipientMessage(sender);

        assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertEquals(0, smtp.acceptedRecipients().size());
        assertEquals(0, smtp.acceptedDataCount());
    }
}
```

Even with `sendpartial=true`, if zero recipients are accepted there is no valid group to send `DATA` to. Test servers help prove the transport sends no payload when all `RCPT` commands are rejected.

## 22. Test 6: Sending Multiple Distinct MimeMessages

Do not confuse **one message with multiple recipients** with **a batch of multiple messages**:

```java
MimeMessage messageA = buildMessage(
        "a@example.net", "A");
MimeMessage messageB = buildMessage(
        "b@example.net", "B");
MimeMessage messageC = buildMessage(
        "c@example.net", "C");

mailSender.send(messageA, messageB, messageC);
```

In a batch, `MailSendException.getFailedMessages()` may contain entries for the failing **message objects**. Successful messages do not necessarily have entries.

### Correlating Messages with Notification IDs

```java
Map<Object, UUID> notificationIds =
        new IdentityHashMap<>();

notificationIds.put(messageA, notificationA.id());
notificationIds.put(messageB, notificationB.id());
notificationIds.put(messageC, notificationC.id());

try {
    mailSender.send(messageA, messageB, messageC);
} catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        UUID id = notificationIds.get(entry.getKey());
        Exception cause = entry.getValue();

        recordFailure(id, cause.getClass().getSimpleName());
    }
}
```

`IdentityHashMap` only correlates identical object instances within a single send call. For retries after restarts, the durable identifier must be the database-persisted `notificationId`, not Java object identity.

### Why Need a Multi-Transaction Test SMTP Server?

A `JavaMailSenderImpl.send(messageA, messageB, messageC)` call may execute multiple `MAIL FROM`/`RCPT TO`/`DATA` transactions on the transport. The minimal scripted server above supports multiple transactions within **one connection**, yet if the implementation reconnects on error or drops mid-way, a single-connection server is insufficient. To test batches and multi-session transport recovery, use GreenMail or extend the test harness for multiple connections.

Never write a batch test that only checks `getFailedMessages()` size and assumes individual email contents were verified. Observe `DATA` counts, `RCPT` replies, and notification outcomes.

## 23. Sending One Message per Recipient: Pros and Cons

One way to avoid complex partial states is having each notification target a single SMTP recipient:

```text
Notification N1 -> MimeMessage -> recipient A
Notification N2 -> MimeMessage -> recipient B
Notification N3 -> MimeMessage -> recipient C
```

Pros:

- Easy to map SMTP status to each notification/recipient.
- Easy to retry a single address independently.
- Lower risk of accidentally resending to already-succeeded addresses.
- Prevents exposing `To/Cc` lists among recipients who should not see one another.

Cons:

- More messages, potentially increasing cost or provider resource usage.
- If content is genuinely meant for a shared group, splitting sends alters `Reply All` semantics.
- Requires deciding how to persist a single business event linked to multiple notifications.

**There is no universal rule forcing every email to be sent individually.** Still, for personalized notifications or exact per-recipient retries, a one-recipient-per-notification model is usually simpler to operate.

## 24. Testing Bcc and Avoiding Recipient Exposure

When sending to multiple recipients, privacy is an important business requirement:

- `To`: primary visible recipients.
- `Cc`: carbon-copy recipients, typically visible.
- `Bcc`: blind recipients, must not appear in visible headers of copies delivered to others.

An integration test should check **both sides**:

```text
Is the Bcc recipient in SMTP RCPT TO?
             |
             +-- Yes: transport received the blind recipient

Raw message received at the SMTP test server
             |
             +-- No Bcc: header in transmitted data
```

Test `Bcc` using fake fixtures and a local server, since raw MIME may carry private data. Never log full production messages in CI.

### When Resending Only to Failed Recipients

If a message has `To: a, b` and `b` fails, resending **the exact same message object** without updating the recipient list can cause `a` to receive a duplicate.

For per-recipient retries, construct a **new message** from notification data, reselect envelope recipients, and consider header semantics:

- Do not keep `To/Cc/Bcc` addresses of recipients who do not need the retry if doing so causes duplicates or leaks lists.
- If group recipient history must be preserved, separate business metadata from outbound headers.
- For personalized emails, having a single recipient per message keeps retries straightforward.

Never apply a "quick fix" by changing `Bcc` to `To` without evaluating privacy policies.

## 25. Testing Duplicate Addresses and Empty Lists

Beyond SMTP errors, applications should test recipient-list validation:

| Case | Expectation per Application Policy |
| --- | --- |
| Same address appears twice in `To` | Deduplicate or raise validation error |
| Same address in both `To` and `Cc` | Decide display precedence |
| Same address in both `To` and `Bcc` | Avoid listing one recipient both publicly and blindly |
| Empty recipient list | Reject notification/send creation |
| `Bcc` only | Accept or reject per policy; test transport behavior |
| Blank/null string in list | Normalize/validate with clear feedback |
| Address with Unicode display name | Parse/encode properly and keep accurate SMTP envelope |
| Same address with differing letter case | Avoid naive deduplication unless policy is certain |

### Separating Business Validation from SMTP Behavior

For duplicate recipient lists, `MimeMessageHelper` does not automatically enforce your business rules. You may need to normalize/deduplicate before constructing `MimeMessage`.

Email addresses have nuanced rules for local-parts and domains. Never treat lowercasing every local-part as universally safe across all providers. In test environments with fixed fake addresses, lowercasing works for set comparisons; in production, normalization/deduplication must follow a clearly defined policy.

## 26. Critical Scenario: DATA Rejected After RCPTs Accepted

Not all recipient or delivery errors happen at `RCPT TO`. A server may accept every recipient at `RCPT TO` yet fail at the `DATA` command or final post-payload reply:

```text
RCPT TO:<a@example.net> -> 250
RCPT TO:<b@example.net> -> 250
DATA                    -> 354
[MIME bytes + terminator]
                         <- 554 5.7.1 Message rejected
```

Here:

- `RCPT TO` succeeded earlier in the session.
- **Final message submission was rejected** at `DATA`.
- Neither recipient can be marked `SUBMITTED` solely from `250` replies at `RCPT`.

To test this, extend the scripted SMTP server to configure the final `DATA` reply. In the `"."` terminator branch, replace the final `250` with `554` when scripted. Assert:

1. The client sent `DATA`.
2. The server returned final `554`.
3. Spring Mail reported an error.
4. The application did not mark `SUBMITTED` for that attempt.
5. Retry policy relies on the reply code and cause, not the number of `RCPT`s that returned `250`.

This differs from `sendpartial=false`, where the transport may **never start `DATA`** when a recipient is rejected.

## 27. Timeout After DATA: Uncertain Outcomes

A harder case:

```text
Client                                  SMTP server
  |                                         |
  |-------- RCPT TO ----------------------->|
  |<------- 250 ----------------------------|
  |-------- DATA + MIME + "." ------------>|
  |                                         | processes message
  X  never receives final reply            |
  |                                         |
  | MailSendException / timeout            |
```

If the server received the message yet the `250` response was lost, the client may treat the send as failed. Resending immediately to those recipients can deliver duplicates.

**The MIME message may be completely valid; the fault lies in the SMTP transport outcome.** An integration test simulating this must make the test server drop the connection or withhold its reply **after reading the DATA terminator**, and assert that the application records an uncertain state.

Never write assertions stating "timeout means the server definitely did not receive the message". For failures at other stages such as failing to open a TCP connection, certainty differs; classify by protocol phase.

### The UNKNOWN State

The application can use:

- `PENDING`: notification awaiting processing.
- `PROCESSING`: worker is attempting to send.
- `SUBMITTED`: SMTP/provider accepted per application-observed evidence.
- `RETRY_WAIT`: failure eligible for retry policy.
- `FAILED`: will not retry further per policy.
- `UNKNOWN`: uncertain whether SMTP accepted the message.

When `UNKNOWN`, tests must verify **no blind retries occur**. Reconcile via provider events, logs keyed by message/notification ID, or operational procedures. Plain SMTP provides no universal idempotency key across all relays; `Message-ID` headers do not automatically guarantee deduplication.

## 28. Testing Bounces After SMTP Acceptance

An SMTP relay may return `250` for `RCPT TO` and `DATA` and only discover later that a mailbox does not exist. That produces an **asynchronous bounce**.

```text
Application
     |
     +-- SMTP 250 after DATA --> SUBMITTED
     |
     v
Provider tries downstream delivery
     |
     +-- mailbox rejected --> BOUNCED event
```

A test using only a scripted SMTP server at the transport layer **cannot prove** downstream bounces. If the application handles webhooks or DSNs:

1. Test that the application records `SUBMITTED` after SMTP acceptance.
2. Simulate a provider callback/bounce for recipient B.
3. Verify recipient B's status transitions to `BOUNCED`.
4. Verify recipient A is not automatically marked `BOUNCED`.
5. Verify webhook authorization, deduplication, and event ordering.

Never delete or misflag all recipients simply because one recipient in a group email bounced downstream. With personalized notifications, storing per-recipient status keeps this much simpler.

## 29. Testing SMTP Accepted Is Not Testing Delivered

Key milestones:

| Milestone | Available Evidence | Appropriate Status Name |
| --- | --- | --- |
| Notification created | Database committed | `PENDING` |
| Worker picks up notification | Claim/lease | `PROCESSING` |
| Server returns `250` at `RCPT TO` | Recipient accepted at `RCPT` step | Not yet `SUBMITTED` |
| Server returns `250` at end of `DATA` | SMTP accepted message for further processing | `SUBMITTED` |
| Provider emits delivery event | Provider reports delivery to destination server | `DELIVERED` if semantics match |
| Provider emits bounce | Delivery attempt failed | `BOUNCED` |
| Lost final reply after `DATA` | Uncertain whether message was received | `UNKNOWN` |

Notably, `JavaMailSender.send(...)` returns `void`. Returning without an exception does not mean "the user read the email". Tests should say `submitted` rather than `delivered` when observing SMTP only.

## 30. A Per-Recipient Outcome Tracking Flow

When an application allows partial sending, a tracking table might look like:

```text
notification_id
recipient_id
recipient_role       TO / CC / BCC
smtp_attempt
smtp_status          PENDING / PROCESSING / SUBMITTED /
                     RETRY_WAIT / FAILED / UNKNOWN
smtp_reply_code
last_attempt_at
next_attempt_at
```

You do not have to store raw email addresses in every table/log; you can reference a `recipientId` per data policy. Define shared-message semantics clearly: `DATA` is sent once to the SMTP-accepted subset, yet retry states may diverge per recipient.

### Example After a Partial Send

Suppose a message has three recipients and `sendpartial=true`:

| Recipient | RCPT | DATA | Status After Attempt |
| --- | --- | --- | --- |
| A | `250` | shared `250` | `SUBMITTED` |
| B | `550` | excluded from accepted set | `FAILED` per policy |
| C | `250` | shared `250` | `SUBMITTED` |

Never retry A and C merely because Spring threw a `MailSendException` for the message where B was rejected. If B's address is fixed or a resend is requested, create a **new attempt with a targeted recipient list**.

### Avoid Confusing One Status for the Entire Message

A single `message.status=FAILED` column loses the fact that A and C were accepted by SMTP. If precise handling matters, persist outcomes per recipient or model one notification per recipient from the start.

## 31. Retrying 4xx Needs Backoff, Not a Tight Loop

Example policy:

```text
Attempt 1: initial send
Attempt 2: after 30 seconds
Attempt 3: after 2 minutes
Attempt 4: after 10 minutes
Attempt 5: after 30 minutes
```

This is an illustrative schedule only. In practice:

- Apply backoff by failure type.
- Add jitter so workers do not retry simultaneously.
- Cap attempts and maximum age.
- Respect rate limits, quotas, and provider policies.
- Never retry `550` errors that waiting cannot fix.
- Never auto-retry `UNKNOWN` outcomes without evaluating duplicate risk.

### Testing the Retry Scheduler

You do not need `Thread.sleep(...)` for minutes in tests. Inject `Clock` or a time abstraction into the service and assert:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-12T08:00:00Z"),
        ZoneOffset.UTC
);

RetryDecision decision = retryPolicy.classify(
        SmtpFailure.temporary(450),
        2,
        fixedClock.instant()
);

assertEquals(RetryDecision.Kind.RETRY_WAIT,
        decision.kind());
assertTrue(decision.nextAttemptAt()
        .isAfter(fixedClock.instant()));
```

`RetryDecision`, `RetryPolicy`, and `SmtpFailure` are **application-defined abstractions**. SMTP transport integration tests supply evidence of error codes; retry policy unit tests verify states and next retry timestamps.

## 32. Do Not Enable mail.smtp.reportsuccess Carelessly

Jakarta Mail SMTP has properties that alter exception details. One example is `mail.smtp.reportsuccess`, which reports accepted recipients in detail and can cause success-carrying exceptions depending on the implementation.

If enabled in tests when disabled in production, exception behavior and callbacks will differ. Therefore:

1. Explicitly configure critical SMTP properties in tests.
2. Note the exact Jakarta Mail/Angus Mail version managed by Spring Boot.
3. Test `SendFailedException` groups under the actual runtime configuration.
4. Never treat the presence of a specific exception class as proof of delivery.

Provider-specific SMTP exception classes vary in name and package across implementations. Depend only on standard Jakarta Mail interfaces/exceptions unless provider-specific details are needed; if exact reply codes are required, verify against the real runtime library.

## 33. Integrating with Spring Boot and Test Configuration

In a Spring Boot application, real configuration typically comes from:

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
```

**Never let integration tests accidentally read production variables.** For localhost tests, override host/port and disable AUTH/STARTTLS when the scripted server does not support them.

A `@SpringBootTest` can use `@DynamicPropertySource` to inject the dynamic port into the Spring context:

```java
@DynamicPropertySource
static void mailProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.mail.host", () -> "127.0.0.1");
    registry.add("spring.mail.port", () -> smtp.port());
    registry.add("spring.mail.properties.mail.smtp.auth",
            () -> "false");
    registry.add("spring.mail.properties.mail.smtp.starttls.enable",
            () -> "false");
    registry.add("spring.mail.properties.mail.smtp.sendpartial",
            () -> "true");
}
```

This snippet illustrates property binding; `smtp` must be initialized **before the Spring context reads properties** (e.g., via a JUnit lifecycle extension or controlled static fixture) and closed afterwards. Never place setup in `@BeforeAll` too late if the context already started and read `smtp.port()`.

When a test class varies `sendpartial` across tests, avoid inadvertently reusing a cached context/sender with stale settings. Use distinct test instances/configs or build `JavaMailSenderImpl` per scenario.

## 34. GreenMail When All Recipients Are Accepted

For tests that need to inspect the actual received MIME, GreenMail is more convenient than a hand-rolled SMTP server. Example skeleton:

```java
GreenMail greenMail = new GreenMail(
        new ServerSetup(0, "127.0.0.1", "smtp")
);

greenMail.start();
try {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(greenMail.getSmtp().getPort());

    MimeMessage mail = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mail, true, "UTF-8");
    helper.setFrom("test-sender@example.org");
    helper.setTo(new String[] {
            "first@example.net", "second@example.net"
    });
    helper.setText("Plain text", "<p>HTML test</p>");

    sender.send(mail);

    assertTrue(greenMail.waitForIncomingEmail(5000, 1));
    MimeMessage[] received = greenMail.getReceivedMessages();
    assertTrue(received.length >= 1);

    // Verify received message contents/recipients
    // per your GreenMail version's API and semantics.
} finally {
    greenMail.stop();
}
```

This uses common GreenMail APIs; add test dependencies, imports, and adapt to your actual library version. With multiple recipients, verify how your GreenMail version stores per-mailbox messages and aggregates `getReceivedMessages()`. To assert per-mailbox delivery accurately, use per-user message retrieval APIs where appropriate; do not equate mailbox count with SMTP `DATA` transaction count.

**To test per-RCPT rejections**, use a scripted SMTP server or a tool configurable with per-recipient rejection replies. Never assume an SMTP capture server supports returning `550` for one specific address out of the box.

## 35. Writing Meaningful Assertions by SMTP Stage

When verifying integration test outcomes, clearly distinguish **event types**:

| Observed Data | Question It Answers |
| --- | --- |
| `observedRecipients()` | Which addresses did the transport send `RCPT TO` for? |
| `acceptedRecipients()` | Which `RCPT`s did the test server return `250` for? |
| `rejectedRecipients()` | Which `RCPT`s did the test server return `4xx/5xx` for? |
| `acceptedDataCount()` | How many times did the test server receive `DATA` and reply accepted? |
| `MailSendException` | Did the Spring sender report a send failure? |
| `SendFailedException` address groups | How did transport categorize the addresses? |
| `capturedMime()` | What MIME bytes/lines did the test server see in `DATA`? |

**Sample assertions:**

```java
assertEquals(
        Set.of("accepted-a@example.net", "blocked@example.net"),
        Set.copyOf(addresses(
                message, Message.RecipientType.TO))
);

assertTrue(smtp.observedRecipients()
        .contains("blocked@example.net"));

assertTrue(smtp.rejectedRecipients()
        .contains("blocked@example.net"));

assertEquals(0, smtp.acceptedDataCount());
```

This checks distinct layers: the composer set the right `To`, SMTP attempted the blocked address, the server rejected it, and **zero `DATA` was accepted**. Never turn a "got `RCPT 250`" assertion into "email delivered".

## 36. Testing Application Partial-Success Handling

At the business layer, a service receives transport outcomes and updates notification/recipient state. Test this logic with **realistic outcomes produced by SMTP tests**, without assuming a send exception always carries complete per-recipient details.

An illustrative policy:

```text
SMTP attempt
    |
    v
Extract per-message + per-recipient outcome when evidence exists
    |
    +-- Confirmed RCPT 550 -> FAILED / INVALID_RECIPIENT
    |
    +-- Confirmed RCPT 450 -> RETRY_WAIT
    |
    +-- DATA 250 and recipient accepted -> SUBMITTED
    |
    +-- Lost final DATA reply -> UNKNOWN
    |
    +-- Insufficient details -> REVIEW / UNKNOWN
```

A complete test should assert two dimensions:

1. **Transport behavior:** which commands the test SMTP server received and which codes it returned.
2. **Application policy:** what states were persisted in the database/repository, whether a retry was scheduled, and whether already-submitted recipients are excluded from the next attempt.

In layered testing, unit-test classification via `RecipientSendOutcome` objects produced by a transport adapter, and integration-test that the adapter interprets `SendFailedException` accurately. There is no need to cram all logic into one giant `catch` block.

## 37. Anti-Pattern Example: Retrying the Whole Message When One Recipient Fails

```java
try {
    sender.send(message);
} catch (MailSendException ex) {
    // Wrong with sendpartial=true: valid recipients
    // may already have been accepted by SMTP.
    sender.send(message);
}
```

If A and C received `250` after `DATA` on the first try, a second send can deliver duplicates to A/C. A safer approach:

1. Parse failures per recipient when evidence exists.
2. Record accepted recipients as `SUBMITTED`.
3. Schedule retries only for eligible failing recipients.
4. On retry, construct a new message/notification or targeted send with the exact remaining recipient set.
5. Never auto-retry `UNKNOWN` outcomes without duplicate-control policies.

### Do Not Use Message-ID as a Deduplication Key

Keeping a stable `Message-ID` header helps correlation, yet SMTP has no universal rule deduplicating by this header. Therefore, a message sent twice with the same `Message-ID` **can still be delivered twice**.

If your provider offers an official idempotency-key API, follow that provider's documentation and scope. Plain SMTP generally requires business-layer idempotency paired with recovery policies.

## 38. Multi-Recipient Single Message vs. Multi-Message Batch: Test Separately

Two flows example:

```text
Flow A
-------
send(MimeMessage X)
  To: A, B
  Cc: C
  Bcc: D
  --> one SMTP message, multiple RCPTs

Flow B
-------
send(MimeMessage X, MimeMessage Y, MimeMessage Z)
  X --> RCPT A
  Y --> RCPT B
  Z --> RCPT C
  --> multiple SMTP messages, each with its own RCPT
```

When the application encounters `MailSendException`:

- Flow A needs per-recipient outcomes within **one message**.
- Flow B needs outcomes per **message** and potentially down to recipients.

Do not apply the same expectations to both batch shapes. For instance, `getFailedMessages().size()==1` in Flow A does not mean only one address failed; it can simply reflect one failed message object.

## 39. Testing Duplicate Recipients Across To/Cc/Bcc

An application sending to multiple recipients should define a duplicate-handling policy:

```text
To:  alice@example.net
Cc:  alice@example.net
Bcc: alice@example.net
```

Questions to answer:

1. Does the composer allow the same address in multiple roles?
2. If so, does the recipient get sent to multiple times or does transport deduplicate?
3. Which role appears in headers when an address appears in both `To` and `Bcc`?
4. Should the application deduplicate before calling the helper?

Do not delegate business-policy decisions to the SMTP provider. Write validation/composer tests verifying the normalized list, then test transport with that list.

**Caution on address comparison:** domains are case-insensitive per DNS, yet local-parts have provider-dependent semantics. Never apply heuristics like stripping dots, dropping `+tag`, or lowercasing local-parts globally without an explicit policy.

## 40. Testing Errors Before Connecting to SMTP

If the application passes:

```text
recipient = "invalid address"
```

into an API requiring a valid `InternetAddress`, syntax errors can occur before opening an SMTP connection. This is a **validation/message-preparation** test, not an `RCPT TO` rejection test.

A suite should have two distinct tests:

- **Invalid input:** ensure malformed addresses are rejected early without creating notifications/sends.
- **SMTP recipient rejection:** use syntactically valid `blocked@example.net` with the test server returning `550`.

If tests fail to distinguish them, an early `AddressException` could be mistaken for handling a server rejection.

## 41. Auth Failure Tests Differ from Recipient Failure Tests

`MailAuthenticationException` is typically an SMTP AUTH error affecting login prior to sending messages. It is not a per-recipient rejection report.

Tests should classify:

| Error | Phase | Policy |
| --- | --- | --- |
| Invalid address syntax | Build/validation | Fix input, do not send |
| Authentication failed | AUTH | Fix credentials/provider policy |
| Recipient 450 | `RCPT TO` | Retry with backoff |
| Recipient 550 | `RCPT TO` | Usually recipient/policy error |
| Message 554 | `DATA` | Check policy/content |
| Timeout after DATA | `DATA` outcome | `UNKNOWN`/reconciliation |

Never use one `catch (MailSendException)` to handle all mail errors and retry everything identically. `MailPreparationException`, `MailAuthenticationException`, and `MailSendException` carry different meanings.

## 42. CI and Test Determinism

For an SMTP integration test to run reliably in CI:

- Bind servers only to `127.0.0.1` or loopback.
- Use random ephemeral ports instead of collision-prone fixed ports.
- Never read SMTP credentials from production environments.
- Configure finite connect/read/write timeouts.
- Close servers and sockets after each test.
- Never share a mutable `JavaMailSenderImpl` across scenarios with differing `sendpartial` settings.
- Never rely on test execution order or long `Thread.sleep` calls.
- For parallel runs, give each test its own server/port and fixtures.
- Never log full MIME containing real addresses or tokens.
- Document exact Spring Mail/Jakarta Mail versions when tests verify exception-specific behavior.

### Avoid Internet-Dependent Tests

Never test failing recipients by emailing non-existent addresses on the Internet. Providers may accept at `RCPT` and bounce later, enforce rate limits, or flag the test account. A local SMTP server with deterministic replies keeps tests fast and side-effect-free.

### Avoid Unbounded Waits

Test servers should enforce socket timeouts. When waiting on async events, use latches/futures with finite timeouts or test-framework wait APIs. Never add arbitrary `Thread.sleep(5000)` assuming the server must have received the mail.

## 43. Recommended Test Matrix Table

| ID | RCPT A | RCPT B | Partial | DATA | Expected Observation |
| --- | --- | --- | --- | --- | --- |
| T01 | 250 | 250 | false | 250 | No error, `DATA` accepted |
| T02 | 250 | 550 | false | Not sent | Message failed, zero `DATA` |
| T03 | 250 | 550 | true | 250 | Partial submit, recipient failure recorded |
| T04 | 250 | 450 | false | Not sent | Temporary recipient failure, retry policy |
| T05 | 550 | 550 | true | Not sent | Zero recipients accepted |
| T06 | 250 | 250 | false | 554 | `DATA` rejected by server |
| T07 | 250 | 250 | true | Lost final reply | `UNKNOWN`, no blind retry |
| T08 | To/Cc/Bcc 250 | - | false | 250 | All `RCPT`s present, `Bcc` absent from received headers |
| T09 | One message | Another failing message | - | Per message | Failed-message correlation in batch |
| T10 | 250 then downstream bounce | - | false | 250 | `SUBMITTED` then `BOUNCED` via event |

This is a test-planning table, not a claim that every SMTP implementation shares identical outcomes in all situations. Each test needs matching server scripts, transport properties, and assertions. For uncertain final `DATA` errors, never force a "definitely failed" state when no reply arrived.

## 44. Logging and Data Protection in Tests

Even in tests, use synthetic addresses:

```text
accepted-a@example.net
blocked@example.net
private-copy@example.net
notice@example.org
```

Never pull real user addresses from production databases into test fixtures or console output. In real applications, logs typically only need:

```text
notificationId=N-341-01
recipientId=R-02
recipientRole=BCC
smtpStage=RCPT_TO
smtpReplyCode=550
failureClass=SendFailedException
classification=PERMANENT_REJECTION
attempt=1
```

Avoid:

- Logging full `MimeMessage`, `To/Cc/Bcc`, or custom headers.
- Putting raw SMTP exception messages into metric labels.
- Putting subjects, bodies, or attachments into CI reports.
- Storing raw `Bcc` or tokens in test screenshots.

A `MailSendException` may embed address details inside nested exceptions; if stack traces must be persisted, apply strict handling policies to sensitive diagnostic data.

## 45. Common Mistakes When Writing Integration Tests

| Mistake | Why Is It Wrong? | Right Approach |
| --- | --- | --- |
| Mocking `JavaMailSender.send` and calling it an integration test | No SMTP protocol exercised | Use a real test server on sockets |
| Testing syntax errors and calling it `RCPT` rejection | Error occurs before SMTP | Use valid syntax with server returning `550` |
| Asserting `250` at `RCPT` means email sent | No `DATA` occurred yet | Assert final `DATA` reply |
| Assuming `sendpartial=true` throws no errors | Partial failures can still throw | Assert both exception and `DATA` |
| Assuming `sendpartial=false` sends to `250`-accepted RCPTs | Transport can abort the whole message | Check `DATA` count |
| Using `failedMessages.size()` to count failing recipients | Map is keyed by message object | Use `SendFailedException` groups / SMTP evidence |
| Retrying the entire message after partial send | Sends duplicates to succeeded recipients | Retry only eligible recipients |
| Testing against public SMTP | Uncontrolled with real side effects | Local scripted SMTP |
| Hard-coding port 2525 for all tests | Collisions in parallel runs | Ephemeral ports |
| Using `Thread.sleep` to wait for server | Flaky under scheduling variance | Events/latches/timeouts |
| Treating `250 DATA` as delivered | SMTP acceptance differs from mailbox delivery | `SUBMITTED`; separate provider events |
| Skipping `Bcc` tests | Risks leaking blind recipient lists | Verify `RCPT` + captured headers |
| Skipping `4xx` tests | Fails to separate transient vs. permanent | Script `450` and `550` separately |
| Ignoring outcomes after `DATA` timeout | Risks duplicate sends | `UNKNOWN`/reconciliation |
| Enabling `reportsuccess` carelessly | Alters exception behavior | Explicit test configuration |

## 46. Multi-Recipient Test Implementation Checklist

### Preparation

- [ ] Tests use localhost SMTP and synthetic addresses.
- [ ] `To`, `Cc`, and `Bcc` test data represent all roles.
- [ ] Server scripts return `250`, `450`, and `550` per recipient.
- [ ] `mail.smtp.sendpartial` is configured explicitly.
- [ ] Timeouts and server cleanup mechanisms are in place.

### Transport Verification

- [ ] Assert the recipient set observed at `RCPT TO`.
- [ ] Assert recipients accepted/rejected by the server.
- [ ] Assert presence or absence of `DATA` per scenario.
- [ ] Assert exceptions at the proper message/transport layer.
- [ ] Never confuse `RCPT 250` with `DATA 250`.

### Application Verification

- [ ] Correlate message/recipient/notification IDs.
- [ ] Never retry an entire batch when part of it succeeded.
- [ ] Distinguish `4xx`, `5xx`, and ambiguous outcomes.
- [ ] `Bcc` is absent from displayed message headers.
- [ ] Assign `SUBMITTED`, `RETRY_WAIT`, `FAILED`, `UNKNOWN` statuses properly.
- [ ] Test bounce/delivery events separately if supported by the application.

### Operations

- [ ] Tests never send to production SMTP.
- [ ] Real user data is never stored in CI.
- [ ] No unbounded waits or test-order dependencies.
- [ ] No hard-coded boundaries, `Message-ID`s, or untested provider assumptions.
- [ ] Failures report clear notification IDs and stages.

## 47. Self-Practice Scenarios

### Scenario A - One Recipient Gets 550

A message is sent to A, B, C. A and C get `250`, B gets `550`. `sendpartial=false`.

**Question:** have A and C been submitted?

**Hint:** you cannot conclude that from `RCPT`. Under typical transport behavior when partial sending is off, no `DATA` is sent. Tests must assert final `DATA` count and exception.

### Scenario B - Partial Enabled

Same recipient list, yet `sendpartial=true`. The server returns `250` after `DATA`; Spring throws `MailSendException`.

**Question:** can we call `sender.send(message)` again immediately?

**Hint:** do not. A/C could receive duplicates. Correlate per recipient, record submitted state, and handle B per policy.

### Scenario C - Syntactically Invalid Recipient

The test passes `"not-an-email"` to `setTo` and gets an exception before the SMTP server sees `RCPT TO`.

**Question:** did this test check recipient rejection?

**Hint:** no. This is a validation/parsing test. For SMTP rejection, use a syntactically valid address and script a `550` reply.

### Scenario D - Bcc Appeared at RCPT

Server logs show `RCPT TO:<audit@example.net>`, yet the primary recipient complains the `Bcc` list was exposed.

**Question:** what else must be checked?

**Hint:** inspect the headers of the test message received by the server, not just the recipient envelope. Avoid investigating with raw production mail.

### Scenario E - Server Returns DATA 554

All `RCPT TO` commands return `250`, then the server rejects the message with `554` at the end of `DATA`.

**Question:** can the recipients be marked submitted?

**Hint:** no. Classify the failure at `DATA`; `RCPT` acceptance is not message submission.

### Scenario F - Timeout After DATA

The worker transmitted all MIME bytes yet never received the final reply.

**Question:** which status should be used?

**Hint:** `UNKNOWN` when lacking deterministic proof; avoid blind retries and look for provider events when available.

### Scenario G - Batch of Three MimeMessages

An exception holds one failed-message entry for the second message.

**Question:** is that guaranteed to be a single failing recipient?

**Hint:** not necessarily. The map is keyed by message object; that message may carry multiple recipients. Read the cause and correlation.

### Scenario H - Recipient Bounces Hours Later

SMTP tests prove the message reached `SUBMITTED`. The provider later emits a bounce for one recipient.

**Question:** what should the integration test cover?

**Hint:** test webhook/event processing separately to transition that recipient's status appropriately; never alter other recipients' statuses without evidence.

## 48. Conclusion

Testing multiple recipients and failing recipients in Spring Framework Mail requires observing the **SMTP protocol**, not merely checking `To/Cc/Bcc` headers or looking at a `MailSendException`. When one recipient is rejected, `mail.smtp.sendpartial=false` typically prevents `DATA` from being sent for the entire message; `sendpartial=true` can submit to accepted recipients while still reporting partial failure. These two cases lead to **completely different retry policies**.

A reliable integration test suite should use a local test SMTP server scripted with per-recipient `250/450/550` replies, assert the `RCPT TO` set, verify `DATA` submission counts, inspect `SendFailedException`, and map messages/recipients to durable notification IDs. Also test `Bcc`, message batches, post-`DATA` errors, and uncertain timeout outcomes. When partial success occurs, **never blindly retry the whole message or the entire batch**.

Finally, maintain a clear boundary between `RCPT TO` acceptance, SMTP `DATA` acceptance, and actual mailbox delivery. SMTP tests provide evidence of **submission at the test server**; delivery, bounces, and client rendering require separate testing layers. This approach helps applications reach the right recipients, handle per-address errors cleanly, and dramatically reduce duplicate sends or misleading delivery reports.
