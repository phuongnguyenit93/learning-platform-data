# Mocking JavaMailSender and Concluding Deliverability: A Common Mistake in Spring Framework Mail

When testing email sending with **Spring Framework Mail**, a unit test can run very quickly:

~~~java
verify(javaMailSender).send(any(SimpleMailMessage.class));
~~~

A green result shows the application **called the `send(...)` method on the mock object as expected**. However, it **does not prove** there was a connection to an SMTP server, that the relay accepted the message, that the recipient address exists, that the email reached the mailbox, cleared spam filters, or appeared in the recipient’s **Inbox**.

This is a common reasoning error: **taking evidence from one layer of the system and drawing conclusions about layers the test never observed**.

This lesson precisely distinguishes mock unit tests, SMTP integration tests, real provider testing, delivery, and inbox placement; presents JUnit/Mockito, MIME, and SMTP examples; shows how to design application states; measures deliverability with sufficiently reliable data; covers false-success scenarios; and lays out a production test suite.

> **Core rule:** `verify(sender).send(...)` proves an interaction with a mock. A final SMTP `250` reply proves the relay at the point of observation accepted the submission. A provider `delivered` event usually reflects a delivery milestone under the provider’s definition. None of those three pieces of evidence, on its own, proves the message landed in the **Inbox** or was read by the recipient.

## 1. Starting with definitions: where is “send succeeded”?

In business language, the following phrases are often used interchangeably:

- “The send-mail function ran without error.”
- “The email was sent.”
- “The provider accepted the email.”
- “The email reached the recipient’s mailbox.”
- “The email landed in the Inbox.”
- “The recipient read the email.”

They are **different milestones**. A simple diagram:

~~~mermaid
flowchart LR
    A["Business service"] --> B["JavaMailSender"]
    B --> C["SMTP relay / provider"]
    C --> D["Recipient mail server"]
    D --> E["Mailbox or spam filtering"]
    E --> F["Inbox / other folder"]
    F --> G["Human recipient"]
~~~

Mocking `JavaMailSender` usually observes only **the arrow from the business service to the sender abstraction**. It does not execute any downstream steps.

### Milestones that need clear names

| Milestone | Observable evidence | What is **NOT** yet proven |
| --- | --- | --- |
| **Intent recorded** | Outbox record committed | SMTP was called |
| **Sender invoked** | Mock `verify(send)`, spy, or application instrumentation | Real SMTP connection occurred |
| **Transport attempted** | Client opened socket/sent SMTP commands to server | Relay accepted the message |
| **Submission accepted** | Relay returned final success after DATA, or provider API returned contracted acceptance | Remote mail server delivered the message |
| **Recipient server accepted** | Reliable DSN/provider event on next-hop acceptance | Message was sorted into Inbox |
| **Provider delivered** | `delivered` event per provider definition | Recipient saw it in Inbox or read it |
| **Inbox placement** | Specific mailbox/seed account check sees message in Inbox | All other recipients get the same result |
| **Human engagement** | Meaningful action by the recipient | Cannot be inferred reliably from an open pixel alone |

Not every SMTP provider exposes every milestone clearly. If the data source only supports `accepted` and `bounced`, APIs and dashboards must reflect that exact level of evidence.

## 2. What does mocking JavaMailSender actually do?

With Mockito:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
~~~

Mockito creates a stand-in object implementing the interface. By default, void calls like `send(SimpleMailMessage)` **do not perform any real mail sending**; the test can configure exceptions, answers, or record invocations.

A call:

~~~java
sender.send(message);
~~~

on a normal mock opens no SMTP socket, performs no EHLO/STARTTLS/AUTH, sends no MAIL FROM/RCPT TO/DATA, and receives no real reply code from a relay.

### What does a passing test prove?

~~~java
verify(sender, times(1))
        .send(any(SimpleMailMessage.class));
~~~

It proves that, during the observed test execution, a call to the matching method/overload occurred **exactly once** on the mock. With an argument captor, the test can also prove the passed object held the asserted fields.

### What does a passing test **NOT** prove?

It does not verify:

- Correct SMTP host, port, and DNS.
- Valid TLS, STARTTLS, hostname verification, or certificates.
- Valid username/password/OAuth token.
- `MAIL FROM` and `RCPT TO` acceptance by the relay.
- Proper real MIME serialization on the wire.
- Provider quota, rate limiting, or sending policy allowance.
- Proper SPF/DKIM/DMARC alignment on the sending domain.
- Whether the recipient mailbox exists and does not bounce.
- Whether the email goes to spam/quarantine.
- Inbox placement or whether the recipient read it.

**No error in a mock** simply means no error was simulated at the mock layer.

## 3. An example that easily creates a false sense of safety

Suppose an application has a receipt-sending service:

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public final class ReceiptMailService {

    private final JavaMailSender sender;

    public ReceiptMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendReceipt(String destination, String orderId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("billing@example.test");
        message.setTo(destination);
        message.setSubject("Receipt for order " + orderId);
        message.setText("Your order has been recorded.");

        sender.send(message);
    }
}
~~~

`example.test` is a domain used in the example, **not a verified sender address allowed to send email onto the Internet**. The service can still pass a mock unit test completely because the test never touches infrastructure.

### Mockito test

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.any;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class ReceiptMailServiceTest {

    @Mock
    JavaMailSender sender;

    @InjectMocks
    ReceiptMailService service;

    @Captor
    ArgumentCaptor<SimpleMailMessage> messageCaptor;

    @Test
    void createsAndSubmitsReceiptToMailSender() {
        service.sendReceipt("buyer@example.test", "order-184");

        verify(sender).send(messageCaptor.capture());
        verifyNoMoreInteractions(sender);

        SimpleMailMessage actual = messageCaptor.getValue();
        assertEquals("billing@example.test", actual.getFrom());
        assertEquals("buyer@example.test", actual.getTo()[0]);
        assertEquals("Receipt for order order-184",
                actual.getSubject());
        assertEquals("Your order has been recorded.",
                actual.getText());
    }
}
~~~

The test is useful: it verifies the application follows the receipt-creation branch and sets address, subject, and body. However, an **accurate test name** is `createsAndSubmitsReceiptToMailSender`, not `emailWasDeliveredSuccessfully`.

If production SMTP configuration is wrong, this test still passes. If the recipient mailbox does not exist, this test still passes. If the email lands in Spam, the test has no way to observe it.

### A wrong conclusion

~~~text
Given: JavaMailSender is mocked
When:  receipt service calls send()
Then:  Mockito verifies the invocation

Wrong conclusion:
  "Deliverability = 100%, email reaches user"

Correct conclusion:
  "Service attempts to send via JavaMailSender
   with the asserted message fields"
~~~

## 4. Mocks are hugely useful when given the right goal

The problem is not Mockito, but **what we claim based on test results**. Unit tests are the right place to verify:

- Which business event triggers a send request.
- Whether recipient, sender, subject, and template key are correct.
- Whether suppressed/opted-out emails are skipped.
- Whether plain text or HTML is used as required.
- Whether the service method calls send at most once.
- Whether `MailException` is caught/thrown/translated per policy.
- Whether it writes to an outbox instead of calling SMTP inside a database transaction.
- Whether expiry, retry budget, category, and permissions are respected.
- Whether sender is never invoked when validation fails.

Importantly: in an application using an outbox, **unit tests of a business service may need to verify the repository/event publisher**, not `JavaMailSender` directly inside an HTTP request. `JavaMailSender` is only invoked by a worker after the outbox commits.

### Examples of good assertion names and meanings

| Test name | Meaning |
| --- | --- |
| `sendsReceiptUsingExpectedRecipient` | Verifies recipient passed to mock |
| `doesNotInvokeSenderWhenRecipientSuppressed` | Verifies business guard |
| `propagatesMailSendException` | Verifies error handling |
| `persistsNotificationAfterPaymentCommit` | Verifies outbox boundary |
| `formatsMimeMessageWithPlainTextAndHtml` | Verifies MIME composition |
| `smtpRelayAcceptsMessage` | Needs SMTP integration, not just mock |
| `providerReportsRecipientDelivery` | Needs provider event/result |
| `mailAppearsInSeedInbox` | Needs appropriate real-mailbox check |

Naming tests to reflect the exact **observation layer** prevents reviewers from misinterpreting the guarantee scope.

## 5. Why `send()` does not equal `deliver()`

In a typical SMTP connection:

~~~text
Application                    SMTP relay
    |                               |
    |---- TCP + optional TLS ------>|
    |---- EHLO -------------------->|
    |<--- 250 capabilities ---------|
    |---- AUTH (if required) ------>|
    |<--- authentication outcome ---|
    |---- MAIL FROM:<...> --------->|
    |<--- 250 ----------------------|
    |---- RCPT TO:<...> ----------->|
    |<--- 250 ----------------------|
    |---- DATA -------------------->|
    |<--- 354 ----------------------|
    |---- headers + body + "." ---->|
    |<--- 250 queued/accepted ------|
    |                               |
    v                               v
Application submission ends     Relay may deliver later
~~~

This is a simplified sequence example: TLS may be implicit TLS, STARTTLS, or another mechanism depending on the provider; multiple recipients may issue multiple `RCPT TO` commands. The server can reject at different phases.

### Meaning of the final SMTP 250

A success response after DATA states that **the relay at the observation point has accepted responsibility for processing the message** under SMTP. Afterward, the relay may:

- Queue it to send to the recipient’s MX.
- Retry when the remote MX returns 4xx.
- Be rejected with 5xx by the destination server.
- Generate a DSN/bounce.
- Hit quota/reputation policies downstream.
- Deliver the message, yet have it filtered into Spam, Promotions, Quarantine, or hidden from Inbox.

Hence you cannot infer **Inbox placement** from an SMTP relay’s final 250.

### Seeing no exception is not enough either

`JavaMailSender.send()` may return normally when transport submission succeeds. Yet the message’s status beyond the relay remains an asynchronous outcome. Software that only writes `try { send(); } catch (...) { ... }` usually **lacks any data source for delivered/bounced or placement**.

## 6. Distinguishing submission, delivery, deliverability, and inbox placement

Common terminology:

**Submission:** the application sends an email to a relay/provider and it is accepted for processing.

**Delivery:** the email is transferred to the destination as defined by the measurement source (e.g., provider reports remote server accepted); not necessarily Inbox.

**Deliverability:** the ability of legitimate mail to pass sending barriers and be accepted in the live environment. In marketing reports, the term is sometimes used broadly to include reaching the Inbox; therefore **define the exact metric** instead of using a vague term without a denominator.

**Inbox placement:** the message is classified and appears in the receiving mailbox’s Inbox rather than Spam/Other/Quarantine. Measuring it requires mailbox/seed observation or a trustworthy source with an equivalent definition.

**Engagement:** recipient interaction such as clicking or taking action in the app. Open tracking pixels do not prove a human opened the message due to image-loading proxies, image prefetching, privacy settings, and blocking.

### Do not collapse every layer into a boolean `sent=true`

A clearer model:

~~~text
requestStatus:  PENDING / PROCESSING / TERMINAL
submitStatus:   NOT_ATTEMPTED / ACCEPTED / REJECTED / UNKNOWN
deliveryStatus: NOT_KNOWN / DEFERRED / DELIVERED / BOUNCED
placement:      NOT_OBSERVED / INBOX / SPAM / OTHER / UNKNOWN
engagement:     optional, independent and privacy-scoped
~~~

These are **application enums**, not types built into Spring Mail. Not every product must implement every state; the minimum bar is never labeling a mock or SMTP submission result as `DELIVERED`.

## 7. A table of valid vs invalid evidence

| Available evidence | Valid conclusion | Invalid conclusion |
| --- | --- | --- |
| Mockito verify sender.send | Service called right method/arguments | SMTP connection succeeded |
| `SimpleMailMessage` fields match | Application constructed data properly | Remote relay accepted |
| MimeMessage parses cleanly | Internal MIME matches test | Provider/domain authentication passed |
| Fake SMTP received DATA | Local transport submitted to fake server | Internet delivery succeeded |
| Provider API returns “accepted” | Provider accepted request per contract | Recipient received the email |
| Provider delivered webhook | Provider reports delivered per its definition | Inbox, read, or genuine engagement |
| Remote MX returned 250, if measured | Destination system accepted transfer | Message sits in Inbox |
| Seed account shows Inbox | Inbox placement on that seed at measurement time | All real-world mailboxes behave identically |
| No bounce after 5 minutes | No bounce recorded in that window | Will never bounce |
| Tracking pixel loaded | Image in email was fetched in some environment | User definitely opened/read it |

Every claim must specify its **evidence source, timestamp, and measurement scope**. If data is missing, record `UNKNOWN` rather than filling in `DELIVERED`.

## 8. Failure categories Mockito mocks routinely miss

A default mock sender does not check:

| Failure group | Example | Where to test |
| --- | --- | --- |
| DNS/egress | Hostname unresolvable or blocked by firewall | SMTP integration/environment |
| TCP/TLS | Wrong port, bad certificate, STARTTLS refused | SMTP integration/staging |
| Authentication | Wrong password/token, disabled account | Staging/provider smoke test |
| Sender policy | `MAIL FROM` or `From:` disallowed | Provider integration |
| Recipient rejection | SMTP `550 5.1.1` at RCPT TO | Scripted SMTP + real provider evidence |
| Temporary refusal | `421`/`451`/throttling | Scripted SMTP + retry integration |
| MIME encoding | Broken HTML/attachment, wrong charset | MIME parse + local SMTP capture |
| Size limits | Message larger than provider allows | Provider-specific integration |
| Authentication DNS | Unaligned SPF/DKIM/DMARC | DNS inspection and real authentication results |
| Sender reputation | Restricted domain/IP or poor signals | Production analytics/provider reports |
| Recipient filtering | Spam/Promotions/Quarantine | Seed mailboxes and operational evidence |
| Compliance/consent | Recipient unsubscribed or complained | Business policy + suppression integration |
| Delayed bounce | Relay accepted, MX rejected later | Provider event/DSN processing |

Do not “fix” this limitation by writing a Mockito stub returning `true` or `Optional<Delivered>`: that is still fake data and does not turn a unit test into a deliverability measurement.

## 9. Choose a multi-layer strategy instead of abandoning mocks

A balanced strategy:

~~~mermaid
flowchart TD
    A["Unit tests with Mockito"] --> B["MIME composition tests"]
    B --> C["Local SMTP integration tests"]
    C --> D["Provider staging / sandbox validation"]
    D --> E["Controlled real-mailbox observations"]
    E --> F["Production event + reputation monitoring"]
~~~

**Later layers do not replace earlier layers.** Mock tests are fast, cheap, and pinpoint business bugs. Local SMTP checks protocol/MIME. Provider tests check account/config. Seed mailbox checks observe specific real placement cases. Production monitoring tracks shifts by domain, mail kind, list quality, and reputation.

### Scope of each layer

| Layer | What is measured? | Needs Internet access? |
| --- | --- | --- |
| Unit mock | Calls, arguments, guards, error decisions | No |
| MIME unit/contract | Serialized structure, encoding, multipart | No |
| Local SMTP | Connect/auth simulation, SMTP conversation, received message | No, if server runs locally |
| Provider sandbox | Provider API/schema/config in provisioned environment | Depends on environment |
| Controlled real provider | Real account auth/acceptance/events | Yes |
| Seed inbox | Placement on specific sample mailboxes | Yes |
| Production monitoring | Outcomes across real traffic, by measurement source | Yes |

A provider “sandbox” may intentionally **not deliver real mail**; it is helpful for testing API contracts, not proving external delivery.

## 10. When to mock, and when not to?

**Mock** when the question to answer is:

- Did the application make the right decision to send mail?
- Did the message builder set the expected properties?
- How many times did the retry policy invoke the sender?
- Did suppression block the call?
- Did the service persist/publish the notification to the outbox at the right transaction boundary?

**Do not rely solely on mocks** when the question is:

- Do `spring.mail.host`, `port`, and STARTTLS settings actually work?
- Does `JavaMailSenderImpl` genuinely transmit MIME over SMTP?
- Are attachments/inline resources serialized properly?
- Does the provider accept credentials, sender domain, quota, and content?
- Do remote mailboxes see the mail in Inbox, Spam, or at all?

Clarifying the **testing question** before picking the tool prevents replacing an entire Mockito suite with slow, flaky, hard-to-control Internet tests.

## 11. Testing `MailException` failures with mocks: the right scope

One benefit of mocks is simulating failures **independent of whether SMTP is healthy**. For instance, forcing the sender to throw `MailSendException`:

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptMailFailureTest {

    @Test
    void propagatesSimulatedSenderFailure() {
        JavaMailSender sender = mock(JavaMailSender.class);
        ReceiptMailService service = new ReceiptMailService(sender);

        doThrow(new MailSendException("Simulated transport failure"))
                .when(sender).send(any(SimpleMailMessage.class));

        assertThrows(MailSendException.class,
                () -> service.sendReceipt(
                        "buyer@example.test", "order-184"));

        verify(sender, times(1))
                .send(any(SimpleMailMessage.class));
    }
}
~~~

The test verifies the service **handles a pre-built exception** as expected. It does not check which exception class a real SMTP server generates in each phase or how Jakarta Mail wraps nested exceptions.

### Can simulate errors without simulating real causes

For example:

~~~java
doThrow(new MailSendException("550 Invalid recipient"))
        .when(sender).send(any(SimpleMailMessage.class));
~~~

This is merely a test-created error string. It **does not prove** the application parsed a real SMTP 550 code, knows the failure happened at `RCPT TO`, or distinguishes a hard bounce from an account error. To verify a classifier driven by SMTP replies/phases, test against an adapter carrying error metadata or a programmable SMTP server returning real replies.

### Separation of responsibilities

A suite should include:

1. **Policy unit tests:** input `INVALID_RECIPIENT` → stop, input `PROVIDER_TEMPORARY` → retry if within deadline.
2. **Adapter integration tests:** real SMTP reply/exception → matching `NormalizedMailFailure`.
3. **End-to-end workflow tests:** outbox state, retry budget, and physical attempt count update properly.

If you only have step 1 with mocked data, the system can still fail when mapping real exceptions into categories.

## 12. Verifying non-sending is also a valuable unit test

For transactional/marketing mail apps, the **must-not-send** condition is sometimes more critical than verifying sender was called:

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class MarketingMailService {

    private final JavaMailSender sender;
    private final RecipientPreference preference;

    public MarketingMailService(
            JavaMailSender sender,
            RecipientPreference preference) {
        this.sender = sender;
        this.preference = preference;
    }

    public void sendOffer(String recipient) {
        if (!preference.mayReceiveMarketing(recipient)) {
            return;
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(recipient);
        message.setSubject("Product update");
        message.setText("News from our service.");
        sender.send(message);
    }
}

interface RecipientPreference {
    boolean mayReceiveMarketing(String recipient);
}
~~~

Testing:

~~~java
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.any;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class MarketingMailServiceTest {

    @Test
    void suppressedRecipientNeverCallsSender() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPreference preference =
                mock(RecipientPreference.class);
        when(preference.mayReceiveMarketing(
                "blocked@example.test")).thenReturn(false);

        MarketingMailService service =
                new MarketingMailService(sender, preference);

        service.sendOffer("blocked@example.test");

        verify(sender, never())
                .send(any(SimpleMailMessage.class));
    }
}
~~~

This is solid evidence of a business guard **within the scope of the unit under test**. It still does not prove the same suppression check exists in an async retry worker, provider fallback, or manual replay. Other send paths require integration tests to avoid bypasses.

## 13. Do not mock `createMimeMessage()` and forget a real MIME object

A mistake in HTML/attachment unit tests is:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
MimeMessage mimeMessage = sender.createMimeMessage();
// With a default mock, the return value may be null.
~~~

If production code runs:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(sender.createMimeMessage(), true);
~~~

a mock that did not stub `createMimeMessage()` can fail with null, even though production code works fine with a real sender.

### Proper way to test MIME composition

Create a real `MimeMessage` from a Jakarta Mail `Session` in the test and only mock the send call:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSender;
import static org.mockito.Mockito.*;

JavaMailSender sender = mock(JavaMailSender.class);
Session session = Session.getInstance(new Properties());

when(sender.createMimeMessage())
        .thenAnswer(invocation -> new MimeMessage(session));
~~~

Or use a local `JavaMailSenderImpl` as a **MIME factory**, without configuring an SMTP connection, and inspect message structure. Having a real `MimeMessage` lets you test headers, multipart structure, charsets, and attachments, though it still does not verify transport/delivery.

### Do not mock `MimeMessage` too when testing MIME structure

If `MimeMessage`, `MimeMessageHelper`, and `JavaMailSender` are all mocks, the test may only prove a sequence of method calls without knowing whether the resulting MIME is actually valid. For HTML/multipart content, use real Jakarta Mail to parse/serialize messages at the corresponding test layer.

## 14. Writing a service composing MIME with two content variants

Example of a receipt email with plain text and HTML:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class HtmlReceiptMailService {

    private final JavaMailSender sender;

    public HtmlReceiptMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String to, String orderId)
            throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime, true, "UTF-8");

        helper.setFrom("billing@example.test");
        helper.setTo(to);
        helper.setSubject("Your receipt " + orderId);
        helper.setText(
                "Your receipt is ready.",
                "<html><body><p>Your receipt is ready.</p></body></html>"
        );

        sender.send(mime);
    }
}
~~~

This class has no template engine, suppression, or auditing; it is an **example scoped strictly to MIME composition**. In production, HTML must come from a template/rendering pipeline with safe escaping. Mocking the sender does not verify TLS, SPF/DKIM/DMARC, or inbox placement.

### Unit test with real MIME, mocked sender

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class HtmlReceiptMailServiceTest {

    @Test
    void buildsMimeMessageWithExpectedHeaders()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        when(sender.createMimeMessage()).thenAnswer(
                invocation -> new MimeMessage(
                        Session.getInstance(new Properties())));

        HtmlReceiptMailService service =
                new HtmlReceiptMailService(sender);
        service.send("buyer@example.test", "ord-184");

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        assertEquals("Your receipt ord-184",
                actual.getSubject());
        assertEquals("buyer@example.test",
                actual.getRecipients(Message.RecipientType.TO)[0]
                        .toString());
        assertTrue(actual.isMimeType("multipart/*"));
    }
}
~~~

The test above verifies core headers and multipart type, without checking every body part in full. To assert **plain-text alternative and HTML have the right content/charset**, traverse the real MIME part tree, locate `text/plain` and `text/html`, and inspect decoded content. **Never hardcode that HTML is always part index 1**: a `multipart/mixed` can nest a `multipart/alternative`, and ordering can shift when inline images/attachments are added.

## 15. MIME tests catch more bugs than verifying send

A solid MIME test should check:

| What to inspect | Why |
| --- | --- |
| `From`, `To`, `Reply-To` | Addresses/headers built correctly |
| Subject and charset | Unicode is not corrupted |
| `text/plain` | Users not viewing HTML can still read it |
| `text/html` | Layout/template is correct |
| `multipart/alternative` | Plain and HTML are content alternatives |
| Attachment disposition/name | Attachments declared properly |
| Content type | MIME metadata matches file |
| `Content-ID` and `cid:` references | Inline resources resolve cleanly |
| Total MIME size | Within product/provider limits |
| Header injection | Untrusted input cannot forge extra headers |
| Bcc/envelope behavior | Bcc is not leaked in delivered headers |

Mock tests observing only `helper.addAttachment(...)` or `sender.send(...)` **do not reliably reflect encoding when MIME is serialized**. Testing structure with Jakarta Mail followed by transport testing with fake SMTP provides far broader evidence.

### Content tests also have limits

A valid multipart message does not guarantee provider acceptance due to size policies, DKIM signing, domain reputation, or recipient-specific filtering. MIME composition is a **necessary condition**, not proof of deliverability.

## 16. Distinguishing SMTP envelope from message headers

A message can have:

~~~text
SMTP envelope:
  MAIL FROM: bounce@example.org
  RCPT TO: recipient@example.net
  RCPT TO: hidden@example.net

Message headers:
  From: billing@example.org
  To: recipient@example.net
  Subject: Invoice
  (Bcc not displayed as delivered header)
~~~

This matters when testing Bcc:

- A unit test can prove code invoked `helper.setBcc(...)`.
- An SMTP integration test must verify the hidden recipient was included in **envelope recipients**.
- Never take the absence of `Bcc:` in a captured raw message as proof the hidden recipient did not receive it; Bcc normally does not appear in delivered headers.
- Never allow Bcc addresses to leak into `To` or the HTML body by mistake.

With fake SMTP servers, observe **RCPT TO commands** and MIME headers at separate layers. Some fake server libraries only expose `receivedMessages` without all envelope details; when asserting envelopes, choose a server/transport instrumentation exposing the needed API.

## 17. Local SMTP integration tests: real sockets, yet still not measuring Internet delivery

To verify `JavaMailSenderImpl` genuinely connects and transmits MIME, use a local SMTP test server such as **GreenMail**, **SubEthaSMTP/Wiser**, or an equivalent tool. Mailpit/MailHog can also serve as SMTP capture in development environments.

Here is an example using GreenMail with an SMTP test port. Test dependencies might include:

~~~gradle
dependencies {
    testImplementation("com.icegreen:greenmail-junit5:<compatible-version>")
}
~~~

`<compatible-version>` is a placeholder to choose according to your project’s Java/Jakarta Mail/Spring versions; it is not a copy-pasteable build version as-is. If using GreenMail test server core instead of the JUnit extension, add the matching artifact per your project’s dependency management.

### Example running an SMTP test server on loopback

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class ReceiptSmtpIntegrationTest {

    private GreenMail smtpServer;

    @BeforeEach
    void startServer() {
        smtpServer = new GreenMail(ServerSetupTest.SMTP);
        smtpServer.setUser(
                "buyer@example.test", "buyer", "test-password");
        smtpServer.start();
    }

    @AfterEach
    void stopServer() {
        if (smtpServer != null) {
            smtpServer.stop();
        }
    }

    @Test
    void submitsMessageToLocalSmtpServer() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(ServerSetupTest.SMTP.getPort());

        ReceiptMailService service = new ReceiptMailService(sender);
        service.sendReceipt("buyer@example.test", "ord-184");

        MimeMessage[] received = smtpServer.getReceivedMessages();
        assertEquals(1, received.length);
        assertEquals("Receipt for order ord-184",
                received[0].getSubject());
    }
}
~~~

This example uses the GreenMail test SMTP server and `ServerSetupTest.SMTP` port; in CI, pick an available port or isolated configuration to avoid port collisions between test processes. In the example `ReceiptMailService` sends simple text without TLS/auth because the local server is configured for the test. Across different GreenMail versions, choose compatible artifacts and APIs.

### Evidence obtained

If the test passes, we know:

1. `JavaMailSenderImpl` used the test configuration to execute an SMTP submission.
2. The local SMTP test server received the message.
3. The Subject could be parsed from the message on the test server.

However, we do not know whether the production host, TLS, account credentials, DNS records, and real recipient MX work. **A local SMTP integration test upgrades evidence from method invocation to protocol submission—it does not jump straight to Internet deliverability.**

## 18. Testing local SMTP with multiple configurations and intentional faults

A local test server can be configured to simulate:

- Failure to connect socket.
- Timeout before/during SMTP.
- Relay returning `421` temporarily unavailable.
- `550 5.1.1` rejecting a recipient.
- `535` authentication failure.
- `554` content/policy rejection.
- Connection drop after DATA.
- Size limits or multiple recipients.

Not every test tool supports **scripted SMTP replies per phase**. With GreenMail or Mailpit, failure injection may be limited; when exact `RCPT TO`/final DATA replies are required, use a programmable fake SMTP server or custom test fixture with phase verification.

### Example testing a connection failure

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SmtpConnectionFailureTest {

    @Test
    void reportsTransportFailureWithoutAListeningServer() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(1); // Assume no SMTP service is listening

        sender.getJavaMailProperties().put(
                "mail.smtp.connectiontimeout", "500");
        sender.getJavaMailProperties().put(
                "mail.smtp.timeout", "500");

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo("buyer@example.test");
        message.setSubject("Probe");
        message.setText("Test content");

        assertThrows(MailException.class,
                () -> sender.send(message));
    }
}
~~~

Note: tests relying on port 1 can behave differently across environments; in production CI, allocate a local port **guaranteed to have no listener** or use a controlled fake network boundary to avoid flakiness. Never point this test at a real SMTP account or real recipient.

### Why test failure paths?

An app might work fine when the relay returns 250, yet fail catastrophically when:

- `550` is treated as retryable and retried forever.
- `451` is treated as permanent, dropping mail.
- Account error `535` triggers a system-wide reconnect storm.
- A timeout after DATA is assumed definitely unsent, causing duplicates.

Mocks can check policy once handed a failure category, while SMTP integration tests verify **real error classification** from transport.

## 19. Testing STARTTLS and SMTP authentication is not inside mocks

A Spring Boot system might configure:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: application-identity
    password: FROM_SECRET_MANAGER
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

These values are Spring Boot SMTP configuration examples, not working credentials; `FROM_SECRET_MANAGER` is merely a placeholder that must never be committed as a real password. Depending on the provider, you may use implicit TLS on port 465 instead of STARTTLS, OAuth2, or a dedicated API. Consult provider/protocol documentation.

A green Mockito test **cannot** verify that STARTTLS negotiates, the certificate chain is valid, or AUTH is accepted. To check:

- Use a TLS test relay with an explicitly configured certificate/truststore.
- Use a staging environment or an authorized test provider account.
- Check hostname verification, TLS mode, port, and timeouts.
- Separate credential validation from sending emails to real recipients.

### Never trust-all just to make a test green

If a real SMTP test fails certificate verification, never fix it by turning off hostname verification or trusting every certificate in production. Tests must surface TLS misconfiguration, not hide it.

## 20. Testing with a real SMTP provider is still not end-to-end deliverability

Suppose staging submits to a provider and receives final SMTP 250. Outcome:

~~~text
Application -> provider SMTP: ACCEPTED
Provider queue: QUEUED
Remote MX: TEMPORARILY DEFERRED
Later: BOUNCED
~~~

Looking only at the app log `Mail send succeeded`, the team may report “sent successfully” even though the recipient has no mail. To know what happened next, observe:

- Provider dashboard or message status API.
- Delivery/bounce/deferral events.
- SMTP DSN if integrated, subject to its limitations and reliability.
- Correlation between application notification ID and provider message ID.
- Per-recipient timestamps and states.

Provider success is **evidence of provider-side handling**, not confirmation of inbox placement. A provider can accept a message and later drop, reject, defer, or forward it through multiple relays under its contract.

## 21. Delivery events are asynchronous data, not mock results

To track what happens after an SMTP provider accepts a message, some services provide webhooks or status APIs. A flow might look like:

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant SMTP as SMTP provider
    participant MX as Recipient domain
    participant Hook as Webhook consumer
    App->>SMTP: SMTP submission
    SMTP-->>App: Accepted / queued
    SMTP->>MX: Delivery attempt
    MX-->>SMTP: Temporary / accept / reject
    SMTP-->>Hook: Delivered / bounced / deferred event
    Hook->>App: Update status projection
~~~

The `sender.send(...)` call only participates in the first step; webhooks may arrive seconds, minutes, or longer afterward. Events can even arrive **out of order**, duplicated, lost, or delayed by the webhook consumer system.

### An illustrative payload

~~~json
{
  "providerMessageId": "provider-msg-184",
  "recipient": "recipient@example.test",
  "eventType": "delivered",
  "occurredAt": "2026-11-12T10:05:10Z",
  "providerEventId": "evt-2048"
}
~~~

This is **illustrative JSON**, not a universal schema across all providers. Names like `delivered`, `processed`, `deferred`, `dropped`, `bounce`, and `complaint` carry provider-specific semantics. Adapters must normalize while still retaining necessary provider reasons.

### What the webhook consumer must do

1. Verify signature/origin per provider rules.
2. Check timestamp/replay protection if supported by the contract.
3. Correlate the right provider account, message ID, attempt ID, and recipient.
4. Deduplicate event IDs within the right scope.
5. Persist the event durably before returning success ACK.
6. Update status using rules that never regress the lifecycle.
7. Retain reconciliation capability when events are delayed or missing.
8. Never auto-resend solely because `delivered` has not appeared yet.

**Webhook tests with mock payloads** are valuable for checking the consumer, yet still do not prove the live provider will send all events or that messages will land in the Inbox.

## 22. Checking provider events with appropriate tests

A webhook-receiving test can use fixture data:

~~~text
Given:
  notification N submitted through provider P
  providerMessageId = m-184
  recipient = r-42

When:
  signed event delivered(m-184, r-42) arrives

Then:
  event is verified
  deduplicated by provider event identity
  status projection becomes DELIVERED
  no new SMTP submission is scheduled
~~~

Negative control:

~~~text
When:
  event with invalid signature arrives

Then:
  do not change delivery status
  do not expose raw event to business handler
  log sanitized security error
~~~

And:

~~~text
When:
  same delivered event arrives twice

Then:
  one logical event is processed
  counters and user notifications are not doubled
~~~

### Evidence gained

This is **consumer integration/contract evidence**, not proof a real email reached a recipient. If a provider sandbox emits a simulated `delivered`, the test only proves your system handles the event according to the simulated contract.

To measure reality, check what the provider actually observed and cross-check against real mail data in a controlled environment.

## 23. Sending one email to multiple recipients: do not merge results

One MIME message can target multiple `RCPT TO` addresses:

~~~text
MAIL FROM: billing@example.org
RCPT TO: alice@example.net -> 250 accepted
RCPT TO: bob@example.net   -> 550 rejected
RCPT TO: carol@example.net -> 250 accepted
~~~

Depending on client/protocol/provider and partial-send configuration, some recipients may be accepted while others are rejected. If the application only persists:

~~~text
notification.status = SENT
~~~

it cannot tell who failed. If retries resend the entire list without tracking recipient-level outcomes, Alice and Carol may receive duplicates.

### Per-recipient model

~~~text
notificationId: notice-184
  |
  +-- recipient Alice: SUBMITTED
  +-- recipient Bob:   REJECTED_PERMANENT
  +-- recipient Carol: SUBMITTED
~~~

For critical or high-volume mail, it is usually better to create **one notification/recipient record per recipient** so idempotency, suppression, retries, and metrics stay clear.

### Tests must measure multiple levels

- Unit mock tests: the right recipients are selected.
- SMTP integration: each RCPT TO is accepted/rejected per script.
- Provider events: correlate delivery/bounce per recipient.
- Inbox tests: inspect sample mailboxes per provider/domain separately.

`MailSendException` and nested exceptions can carry useful send-failure details, yet do not assume a combined `MailSendException` exposes every recipient outcome in the exact same schema across all transports.

## 24. Reasoning error: “One email landed in a test Inbox, so all emails deliver”

Even after succeeding with one test mailbox, the outcome is not universal:

- Gmail, Outlook, Yahoo, and corporate mail servers filter differently.
- An organization might quarantine attachments or block sending domains.
- A new low-engagement mailbox may classify differently from one that trusts the sender.
- Geography, sending IP, domain reputation, and campaign characteristics all affect outcomes.
- Even on the same domain, different content, volume, or recipients can yield different outcomes.
- Providers can change policies while application code stays unchanged.

### Appropriate conclusion

“Test email X from sender Y appeared in seed mailbox Z’s Inbox at time T” is a valid observation.

“Deliverability for all emails is 100%” from that single observation is **extrapolating beyond scope**.

## 25. Seed mailbox testing: limited real-Inbox observation

**Seed testing** uses test mailboxes managed by or licensed to the team across different providers/email domains. Process:

1. Provision seed addresses across permitted providers/domains.
2. Send representative test content through the real SMTP provider, sender domain, and route.
3. Attach a unique test correlation ID in an appropriate header/body without secrets.
4. Wait for a defined bounded observation window.
5. Read seed mailboxes via authorized API/IMAP.
6. Record **Inbox**, Spam/Junk, Other/Promotions, Quarantine, Not Found, or Unknown per mailbox.
7. Correlate with provider accepted/delivered/bounce events.
8. Report timestamp, sample size, provider/domain, template/category, and test conditions.

### Example bounded report

| Seed mailbox | Observed result | Conclusion |
| --- | --- | --- |
| Gmail seed A | Inbox | Landed in seed A’s Inbox |
| Outlook seed B | Junk | Classified as Junk on seed B |
| Mail server C | Quarantined | Blocked by server C’s policy |
| Yahoo seed D | Not observed within window | No placement evidence yet |

Results in this table are **illustrative examples only**, not real measurements or predictions for the named providers.

### Avoid overclaiming

A set of seed mailboxes does not necessarily represent the entire user population. It can **detect unusual trends early**, compare template/domain/route changes, and monitor a slice of mailbox types; it is not proof that every recipient’s email lands in the Inbox.

### Test with proper authorization

Never log into customer mailboxes or send test mail to strangers to “measure deliverability” without consent. Use owned seed accounts or authorized environments, and use non-sensitive test data.

## 26. SPF, DKIM, and DMARC: unit mocks cannot check them

Domain authentication is crucial to real-world email operations. Understand it accurately:

### SPF

SPF evaluates whether the sending IP is authorized to send for a **domain identity** used in the SMTP envelope/HELO per SPF rules. It does not simply verify that the `From:` header is authorized merely because the text domain matches.

### DKIM

DKIM uses cryptographic signatures in message headers. Recipients can verify the signature via the public key published in DNS for the signing domain. Signatures can break if body/headers are altered incompatibly.

### DMARC

DMARC checks alignment between the **header From domain** and an identity authenticated by SPF or DKIM (per alignment rules), while the domain can publish policies such as `none`, `quarantine`, or `reject`.

### Easily confused cases

| Case | What does it mean? |
| --- | --- |
| SPF passes, yet envelope domain is unaligned with From | Not enough to pass DMARC via SPF |
| DKIM passes, yet `d=` differs and is unaligned with From | Not enough to pass DMARC via DKIM |
| Aligned SPF pass or aligned DKIM pass | Can satisfy DMARC alignment per configuration |
| SPF/DKIM/DMARC pass | Does not prove safe content, valid recipient, or Inbox placement |
| DMARC policy `p=none` | A monitoring policy, not proof of good domain reputation |

### Why can mocks not measure this?

Mocks do not send from real IPs, do not sign DKIM on the wire, do not query DNS on the receiving side, and do not receive `Authentication-Results` generated by a trusted ingress. A unit test like:

~~~java
assertEquals("sender@example.org", message.getFrom());
~~~

does not check SPF, DKIM, or DMARC at all.

### How to check outside mocks

- Verify the domain is configured with the provider per real documentation.
- Inspect DNS SPF, DKIM selectors/public keys, DMARC policy, and header From alignment.
- Run a controlled send to a test mailbox and inspect authentication results from a **trusted receiving path**.
- Cross-check envelope domain, DKIM `d=`, From domain, and actual verification marks.
- Monitor policy/reporting, noting that forwarding and mailing lists can complicate results.

Never trust an arbitrary `Authentication-Results` header injected by the sender in raw content. Only interpret results generated by the receiving system/trusted ingress path.

## 27. DKIM pass does not equal Inbox

An email can have:

~~~text
SPF:   PASS
DKIM:  PASS
DMARC: PASS
SMTP:  ACCEPTED
Placement: SPAM
~~~

There is no contradiction here. Domain authentication proves sender-origin/signature properties, whereas spam filtering also weighs reputation, content, interaction history, recipient desirability, sending cadence, and other signals.

Conversely, a seed mailbox might place a message in the Inbox in one specific scenario even when authentication configuration needs improvement; that does not guarantee stability or compliance with other receiving domains’ policies.

### Signals worth observing

- SPF/DKIM/DMARC authentication and alignment.
- Sender domain verification in the provider.
- IP/domain reputation when data is available.
- Bounce/deferral/complaint rates.
- Recipient list hygiene, consent, and unsubscribes.
- Content type, links, attachments, template versions.
- Send volume and ramp-up speed.
- Provider-level suppressions and quotas.

Do not rely on a single factor to claim Inbox placement rate.

## 28. Reputation and sending history: factors mocks leave blank

Real-world email deliverability varies with:

- Sending domain/IP history.
- Shared IP vs dedicated IP.
- Sudden traffic spikes.
- Spam complaints and unsubscribes.
- Invalid address/hard bounce rates.
- List freshness and verification.
- Whether recipients previously marked mail as wanted or unwanted.
- Spoofed sending domains or broken authentication configs.
- Campaigns with suspicious content/links/attachments.
- Provider throttling and receiving-domain-specific policies.

No Mockito stub can fabricate real-world reputation. Instead, rely on **operational monitoring, account/provider telemetry, and controlled experiments**, interpreted with uncertainty in mind.

### Do not try to “bypass filters”

Legitimate deliverability improvement does not mean evading spam filters or continuing to mail non-consenting recipients. Prioritize:

1. Sending to recipients with valid contact grounds and consent.
2. Handling unsubscribes/suppressions properly.
3. Authenticating the sending domain.
4. Keeping content purposeful and transparent.
5. Capping frequency, avoiding spam and retry storms.
6. Investigating bounces/complaints instead of switching providers to force resends at all costs.

## 29. Syntactically valid addresses do not prove mailboxes exist

Address validation code might look like:

~~~java
new jakarta.mail.internet.InternetAddress(
        "buyer@example.test", true);
~~~

or use another validator. Yet syntactic validity only says a string **may** follow address syntax; it does not prove:

- The domain has MX records or mail routing.
- That specific mailbox exists.
- The recipient accepts email from the current sender.
- The mailbox still has quota.
- Receiving policy allows the message.
- The email enters the Inbox.

Moreover, a domain may accept every RCPT TO and send a bounce later. Some receiving systems also refuse to reveal mailbox existence during SMTP. Never treat an SMTP “address verification probe” as absolute truth.

### What should address validation aim for?

- Reject clearly malformed input before creating a notification.
- Protect against header injection.
- Normalize according to chosen rules without breaking valid addresses.
- Never silently assume every provider canonicalizes identically.
- Handle hard bounces/suppressions using trustworthy post-send evidence.

If a recipient actively verifies an address via a link/OTP, that proves mailbox control at verification time, yet still does not guarantee all future emails reach the Inbox.

## 30. `DELIVERED` status on dashboards needs a source

A design flaw:

~~~java
sender.send(message);
notificationRepository.updateStatus(id, "DELIVERED");
~~~

Because normal method return only proves transport submission, separate them:

~~~java
sender.send(message);
notificationRepository.updateStatus(id, "SUBMITTED");
~~~

Then consume provider events (if available) to update delivery state.

### Store the source of each state too

~~~json
{
  "notificationId": "notif-184",
  "submissionStatus": "SUBMITTED",
  "submissionEvidence": "SMTP_FINAL_SUCCESS",
  "submittedAt": "2026-11-12T10:00:05Z",
  "deliveryStatus": "DELIVERED",
  "deliveryEvidence": "PROVIDER_VERIFIED_EVENT",
  "deliveryObservedAt": "2026-11-12T10:05:10Z",
  "inboxPlacement": "UNKNOWN"
}
~~~

This is an application model. Some providers emit no delivery events; in that case `deliveryStatus` must stay `UNKNOWN`, never automatically flipping after 5 minutes or absence of bounces.

### Do not overload `sent=true` for every purpose

If legacy API compatibility forces a single boolean, document clearly:

~~~text
sent = true means "SMTP submission accepted"
~~~

Never reuse that same field to compute inbox placement or engagement.

## 31. Submission success in a batch also does not prove every recipient was delivered

When calling `sender.send(SimpleMailMessage... messages)` or sending MIME to multiple recipients, errors can hit part of a batch. A `MailSendException` can hold failed messages and nested causes. Still:

- A batch method does not create an “atomic all-or-nothing delivery transaction”.
- SMTP conversation/transport/provider behavior can differ.
- An accepted message can bounce later.
- A message throwing no error is not guaranteed to be delivered either.

### How to design for production batches

Store per-notification/per-recipient state:

~~~text
notificationId
recipientId
messageCategory
attemptId
providerKey
submitStatus
deliveryStatus
normalizedFailureReason
~~~

A worker should know what was attempted, what the provider accepted, and which recipient must stop or retry. Avoid generating a “100 messages sent” metric simply because a single `send(messages)` call returned without throwing.

## 32. Unknown SMTP outcome: even an exception might still have sent

A critical case:

~~~text
Application sends SMTP DATA
Relay receives final dot and perhaps accepts message
Connection drops before client receives final reply
JavaMailSender throws MailException
~~~

From the application’s perspective, whether the relay accepted is unknown. **Never** conclude:

~~~text
Exception -> definitely not sent
~~~

or:

~~~text
No exception -> delivered to Inbox
~~~

Both inferences are wrong.

### Useful state

`SUBMISSION_UNKNOWN` preserves correlation/attempt history and enables reconciliation. If the provider allows querying message status by provider ID or event stream, cross-check before retrying. If no authoritative source exists, decide based on duplicate risk and business policy (e.g., OTPs, invoices, and marketing have different duplicate tolerances).

### Mocks cannot test the real failure window

A `doThrow(new MailSendException(...))` test does not simulate a relay receiving DATA and losing the reply. To test this branch, you need a scripted SMTP server that can:

1. Receive full DATA.
2. Close the connection before the final reply.
3. Log that the server read the body.
4. Let the client observe an error.
5. Verify the worker moves to `SUBMISSION_UNKNOWN` and **does not resend blindly**.

Even from a scripted server you cannot assume every real-world transport classifies identically; still, this test is far superior to stubbing an exception with no phase semantics.

## 33. Do not infer “read” from a tracking pixel

An email may embed a remote image for open tracking. Image fetch counts do not equal the number of humans who actually opened the mail because:

- Proxies/caches or privacy-protection systems may fetch images automatically.
- Recipients reading plain text or blocking images trigger no pixel.
- Email clients may prefetch or defer image loading.
- Security scanners may open links/images without real user interaction.

**Open rate** is therefore a limited proxy, not an exact measurement of “read”. If the product needs confirmation of an important action, use an authenticated in-app action or dedicated confirmation workflow rather than pixel tracking.

### Click tracking also has noise

Security scanners sometimes fetch links automatically. Never treat an HTTP GET on a tracking link as proof the user actively approved, paid, or accepted terms.

## 34. Do not treat absence of bounces as proof of delivery

Suppose an application sends 1,000 messages and sees no bounces after 10 minutes. Many possibilities exist:

- The provider is still queuing or retrying downstream.
- The webhook consumer failed, so events have not arrived.
- Some servers do not return expected DSNs.
- Status records have not synced yet.
- Messages were accepted, yet filtered to spam or quarantined.

Therefore:

~~~text
No bounce observed != Delivered
No error observed  != Inbox
~~~

When evidence is insufficient, keep `UNKNOWN` or `PENDING_PROVIDER_EVENT` per your system model. If a policy needs to terminate waiting, mark `OUTCOME_NOT_OBSERVED_WITHIN_WINDOW` rather than flipping to `DELIVERED`.

## 35. Always define the denominator of deliverability metrics

A report saying “delivery rate = 99%” is incomplete without specifying what sits in the denominator.

Several distinct metrics:

\[
\text{Submission acceptance rate}
= \frac{\text{Submissions accepted by relay}}
{\text{Submissions with a classified outcome}}
\]

\[
\text{Provider-reported delivery rate}
= \frac{\text{Recipient submissions reported delivered by provider}}
{\text{Recipient submissions in the eligible observation cohort}}
\]

\[
\text{Seed inbox placement rate}
= \frac{\text{Seed messages observed in Inbox}}
{\text{Seed messages with a determined placement outcome}}
\]

For seed metrics, also report **unobserved messages**, rather than quietly dropping “not found” tests to inflate percentages. For provider-reported delivery, specify the observation window, unknown/deferred handling, provider event lag, and per-recipient deduplication.

### Do not mix counting units

- One notification can have multiple recipients.
- One recipient submission can emit multiple provider events.
- One business event can retry across multiple attempts.
- One delivery event can suffer webhook redelivery.

Counting raw `delivered` event rows as emails delivered without deduplication can exceed the actual message count. Choose a **statistical unit** (notification/recipient/attempt) and keep it consistent across dashboards.

## 36. Risk of an “integration test” still actually using a mock

Some projects use `@SpringBootTest` and call it an integration test. Yet if the Spring context replaced `JavaMailSender` with a Mockito bean, the test **still performs zero SMTP I/O**, even though the full application context started.

Example in Spring versions supporting `@MockitoBean`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class MailApplicationContextTest {

    @MockitoBean
    JavaMailSender sender;

    @Autowired
    ReceiptMailService service;

    @Test
    void invokesSender() {
        service.sendReceipt("buyer@example.test", "ord-184");
        org.mockito.Mockito.verify(sender)
                .send(org.mockito.ArgumentMatchers.any(
                        org.springframework.mail.SimpleMailMessage.class));
    }
}
~~~

In older Spring Boot/Spring Framework versions, the mock-replacing annotation may be `@MockBean` or another mechanism. **Check the version in use** instead of copying an incompatible annotation.

### What does it check?

It checks wiring of `ReceiptMailService` in the Spring context and that the service calls the mock. It still **does not verify** host/port/TLS/network/SMTP relay or deliverability.

### Clarifying two kinds of integration tests

**Wiring integration test with mocks:** many real Spring beans run, yet transport is swapped for a fake. Good for orchestration and configuration boundaries.

**SMTP transport integration test:** the application uses a real `JavaMailSenderImpl` connecting to a test server or test provider. Needed to verify protocol/config.

Test names and CI reports must state the exact type. Never label a context test where transport is still a Mockito bean as “mail delivery integration passed”.

## 37. Checking Spring Boot Mail configuration also needs more than mocks

Spring Boot can create `JavaMailSenderImpl` from `spring.mail.*` when appropriate auto-configuration conditions apply. Yet a mock unit test will not check:

- Whether the right sender bean is selected when multiple beans exist.
- Environment-specific host/port settings.
- Whether `mail.smtp.auth` and `mail.smtp.starttls.required` properties pass through to Jakarta Mail as expected.
- Whether credentials fetched from the secret manager are valid.
- Whether timeouts actually apply.
- Whether the sender identity is allowed by the SMTP provider.

### Testing at the configuration layer

You can run a context test **without replacing the sender with a mock** and assert properties on `JavaMailSenderImpl` without hitting the network:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

void assertExpectedSmtpConfig(JavaMailSenderImpl sender) {
    assertEquals("smtp.example.org", sender.getHost());
    assertEquals(587, sender.getPort());
    Properties props = sender.getJavaMailProperties();
    assertEquals("true", props.getProperty(
            "mail.smtp.starttls.required"));
}
~~~

This is a **configuration assertion**, not proof the provider is operational. A subsequent test must verify connectivity to the SMTP endpoint within network/security boundaries.

### When multiple `JavaMailSender` beans exist

If the app has `primarySender` and `backupSender`, mocking one bean and verifying it does not prove the router chose the right real host. Check all of:

1. Which route business policy picks.
2. Which config dependency injection/bean qualifiers point to.
3. SMTP integration of each route.
4. Failover only for eligible errors; do not try B when recipient is invalid or A already accepted.

Do not reuse the same mock for both A and B if the test needs to confirm two independent routes.

## 38. Do not let a mock unit test flip production state to DELIVERED

A flawed example:

~~~java
public void send(Notification n) {
    sender.send(n.toMimeMessage());
    repository.markDelivered(n.id());
}
~~~

A test using `sender = mock(JavaMailSender.class)` runs past `send` error-free and invokes `markDelivered`, tempting a developer to believe the workflow works.

### Fixing the domain model

~~~java
public void submit(Notification n) {
    MimeMessage message = renderer.render(n);
    sender.send(message);
    repository.recordSubmissionAccepted(
            n.id(), clock.instant());
}
~~~

This is application pseudocode. `repository.recordSubmissionAccepted` means **transport success was received per contract**. `DELIVERED` should only be updated by a trusted delivery evidence source; `INBOX` only by a corresponding placement observation source.

### Mocks must never fabricate production delivery events

A test can feed a fake `DELIVERED` event to check the consumer, yet that is **test data**. Never treat such results as proof a real SMTP account delivered.

## 39. Designing an attempt ledger with evidence types

A helpful domain record:

~~~java
package com.example.mail.delivery;

import java.time.Instant;

public enum SubmissionOutcome {
    NOT_ATTEMPTED,
    ACCEPTED,
    EXPLICITLY_REJECTED,
    UNKNOWN
}

public enum DeliveryOutcome {
    NOT_OBSERVED,
    DEFERRED,
    DELIVERED,
    BOUNCED,
    COMPLAINED
}

public record SubmissionAttemptResult(
        String notificationId,
        String attemptId,
        String providerKey,
        SubmissionOutcome outcome,
        String normalizedError,
        Instant observedAt) {
}
~~~

These types are application-defined, not `JavaMailSender` APIs. With mock unit tests, only assert the service called the sender—do not fabricate `ACCEPTED` records into a production DB from mock fixtures.

### An illustrative database schema

~~~sql
CREATE TABLE mail_submission_attempt (
    id                  VARCHAR(120) PRIMARY KEY,
    notification_id     VARCHAR(120) NOT NULL,
    provider_key        VARCHAR(120) NOT NULL,
    attempt_number      INTEGER NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    completed_at        TIMESTAMP,
    submit_outcome      VARCHAR(40) NOT NULL,
    evidence_type       VARCHAR(60),
    smtp_phase          VARCHAR(60),
    smtp_code           VARCHAR(20),
    normalized_error    VARCHAR(100),
    UNIQUE (notification_id, attempt_number)
);

CREATE TABLE mail_recipient_delivery (
    notification_id     VARCHAR(120) NOT NULL,
    recipient_id        VARCHAR(120) NOT NULL,
    provider_key        VARCHAR(120),
    provider_message_id VARCHAR(250),
    delivery_outcome    VARCHAR(40) NOT NULL,
    observed_at         TIMESTAMP,
    evidence_source     VARCHAR(100),
    PRIMARY KEY (notification_id, recipient_id)
);
~~~

Add tenant isolation, indexes, idempotency, timestamp semantics, and appropriate retention. With multiple attempts/providers, a delivery projection table may need event history or per-attempt correlation so stale events do not overwrite a known delivery.

### Evidence types prevent false inferences

Examples:

~~~text
SMTP_FINAL_250
PROVIDER_API_ACCEPTED
PROVIDER_VERIFIED_DELIVERY_EVENT
CONTROLLED_SEED_MAILBOX_OBSERVATION
UNKNOWN
~~~

`MOCK_INVOCATION` **is not an allowed evidence type for production state**; it belongs solely in unit test reports.

## 40. Retries and deliverability: do not retry to “force Inbox”

A mistake:

~~~text
JavaMailSender.send() returns normally
No inbox evidence within 1 minute
Application retries same message
~~~

If the relay already accepted it, a new send can duplicate the email for the recipient. If the email landed in Spam, resending identical content likely helps nothing and may worsen negative signals.

### A sounder policy

- Retry when a transport error **is classified as temporary and safe to retry**.
- Do not retry permanent recipient/content rejections.
- Never auto-resend after an accepted submission.
- Never retry blindly on `SUBMISSION_UNKNOWN`.
- Respect OTP/link TTLs and consent/suppression.
- Never switch providers to evade spam complaints or recipient policies.
- When a resend is genuinely needed, create a business decision with idempotency and auditing.

### `JavaMailSender.send()` does not support distributed transactions with databases

If the relay returns 250 while the DB update fails, the worker may crash leaving the record `PROCESSING`. Automatic retries can duplicate. Transactional outboxes, attempt ledgers, and reconciliation are needed; even with them, you cannot promise end-to-end exactly-once SMTP delivery.

## 41. Practical measurement strategy by email type

Not every email type needs the same measurement depth:

| Category | Key observations | Guidance |
| --- | --- | --- |
| OTP/verification | Latency, submit errors, expired codes, bounces | Enforce token TTL, offer backup support channel when sending fails |
| Password reset | Provider acceptance and delivery result when available | Never log tokens and do not rely on open tracking |
| Receipt/invoice | Submission status, bounces, support cases | Reconcile with business transaction, never duplicate |
| Security notification | Latency, account health, missed notifications | Prefer approved routes, suitable expiry |
| Marketing | Bounces, complaints, suppressions, placement trend | Consent, list hygiene, domain authentication |
| Support reply | Delivery attempt/response correlation | Track conversation/ticket within proper scope |

### For OTPs, pair with business signals

If users repeatedly request a new code, that can hint at slow or hard-to-find mail; yet **it does not by itself prove the mail landed in Spam**. A low verification completion rate may stem from UX, app bugs, token expiry, security controls, or user drop-off. Combine multiple signals and avoid jumping to conclusions.

### For marketing, never equate open rate with deliverability

Open rates are distorted by email client privacy protections and image-loading behavior. Measure complaints, bounces, suppressions, and provider reputation/placement observations with explicit sources and confidence bounds.

## 42. Empirical evaluation when switching SMTP providers

A team can migrate from provider A to B and see all unit tests stay green. That is expected: mock tests cannot see infrastructure differences.

### Controlled migration process

1. Verify domain verification, sender identity, and authentication on B.
2. Verify config/TLS/credentials in staging.
3. Run local SMTP/MIME regression tests.
4. Send to authorized seed mailboxes with non-sensitive payloads.
5. Limit production canary traffic by authorized category/tenant.
6. Track acceptance, deferral, bounce, and complaint rates by provider.
7. Observe placement trends rather than inferring from one sample.
8. Compare identical observation windows and equivalent cohorts.
9. Verify unsubscribe/suppression is shared and never bypassed across route changes.
10. Roll back or throttle down if adverse impact is confirmed.

### Never A/B test by sending two copies to one recipient

Sending the same email simultaneously via A and B to the same recipient “to see which lands in Inbox” causes duplicates, muddies correlation, and hurts user experience. Use seed accounts, controlled cohorts, or separate send times per policy instead; never double-send to real users.

### Avoid asserting uncontrolled causal impact

If provider B shows a higher delivery rate than last week, the reason could be domain reputation, campaign type, recipient mix, seasonality, or send volume shifts. Always state cohort, sample size, timeframe, category, provider health, and confounders when comparing.

## 43. Check cleanly from sending address to receiving route

An outbound email has at least these identities/routes to observe:

~~~text
Application sender bean
  -> SMTP host/port/account
  -> envelope MAIL FROM
  -> header From
  -> DKIM signing domain
  -> provider queue
  -> recipient MX/domain
  -> mailbox filtering
~~~

Mocking `JavaMailSender` can verify `setFrom(...)` on a Java object, yet reveals nothing about:

- The actual envelope sender the provider uses.
- How Return-Path is set.
- Which domain/selector signs DKIM.
- Whether the provider rewrites headers.
- How the receiving system evaluates DMARC alignment.
- How the message is sorted into Inbox/Spam at the destination.

When investigating deliverability, trace the **entire chain** and classify evidence from every layer rather than just re-running unit tests.

## 44. Test matrix: each case has a goal and evidence limits

A strong test suite does not merely have many cases; it explicitly states **which layer is observed** and **what must not be inferred**.

| ID | Scenario | Test layer | Primary assertion | Does NOT prove |
| --- | --- | --- | --- | --- |
| M01 | Receipt service calls sender | Unit/Mockito | `send(...)` called exact count | SMTP connected |
| M02 | Address/subject/body in SimpleMailMessage | Unit/ArgumentCaptor | Message fields match | Relay accepted |
| M03 | Marketing recipient unsubscribed | Unit/Mockito | `send()` never invoked | All retry paths block it |
| M04 | Simulated MailException | Unit/Mockito | Service handles exception properly | Real exception classification |
| M05 | Sender called twice due to bug | Unit/Mockito | `times(1)` catches duplicate | System-wide exactly-once |
| M06 | Skips creation when template missing | Unit/Mockito | Sender not called | Production template repo works |
| M07 | Mock createMimeMessage returns null | Unit | Test fixture must return real MIME | Real SMTP config |
| M08 | Plain/HTML alternative | MIME unit | Both body parts valid | Inbox placement |
| M09 | Attachment filename/content type | MIME unit | Headers/structure valid | File passed malware scan |
| M10 | Unicode subject/body | MIME unit | Correct charset decoding | Provider preserves Unicode |
| M11 | Inline image CID | MIME unit | Content-ID matches HTML reference | Email client renders cleanly |
| M12 | Bcc omitted from headers | MIME/local SMTP | Headers and envelope checked | Recipient read it |
| I01 | JavaMailSenderImpl connects fake SMTP | Local integration | Test relay receives mail | Internet delivery |
| I02 | Local SMTP returns final 250 | Local integration | Submission accepted at fake relay | Real provider accepted |
| I03 | SMTP server not listening | Local integration | Transport failure handled | All network errors identical |
| I04 | STARTTLS negotiation | TLS-capable integration | TLS mode/cert work in test | Auth at other providers |
| I05 | AUTH 535 | Scripted SMTP | Account-level failure classified | Recipient invalid |
| I06 | RCPT 550 5.1.1 | Scripted SMTP | Permanent rejection stops retries | Bounce rules of all providers |
| I07 | RCPT 451 | Scripted SMTP | Temporary error handled by retry policy | Guarantee retry succeeds |
| I08 | DATA 554 | Scripted SMTP | Explicit phase-correct rejection | Overall content reputation |
| I09 | Lost final reply after DATA | Scripted SMTP | `SUBMISSION_UNKNOWN` | Certain relay acceptance/rejection |
| I10 | Multi-recipient partial rejection | Scripted SMTP | Recipient outcomes kept separate | Final delivery for accepted ones |
| I11 | DB failure after SMTP 250 | Integration + failure injection | No blind auto-resend | Absolute exactly-once delivery |
| I12 | Worker restart and broker redelivery | Integration | Idempotent enqueue/claim | Zero unknown external effects |
| I13 | Webhook invalid signature | Provider consumer integration | Delivery state unchanged | Real webhooks always arrive |
| I14 | Webhook duplicate | Provider consumer integration | Deduplicated event | Provider sends only once |
| I15 | Out-of-order events | Provider consumer integration | State projection does not regress | Inbox placement |
| I16 | Hard bounce after SMTP accepted | Provider consumer integration | Delivery status `BOUNCED` | All bounces share semantics |
| I17 | Deferred after provider accepted | Provider consumer integration | No new submission created | Message will definitely deliver |
| P01 | Real provider credentials | Authorized staging integration | Account accepted | Recipient Inbox |
| P02 | Sender domain/From policy | Authorized provider integration | Provider permits submission | DMARC/Inbox pass |
| P03 | Provider event callback | Authorized provider integration | Events arrive and correlate | No event ever dropped later |
| P04 | SPF/DKIM/DMARC on test receiver | Controlled real mail | Authentication results observed | Not flagged as spam |
| P05 | Message size/provider quota | Authorized provider test | Provider handles per quota | All future volume succeeds |
| P06 | Provider outage/rate limit | Controlled failure/canary | Backoff/circuit breaker | User receives on time |
| S01 | Gmail seed mailbox | Controlled seed | Specific placement observed | All Gmail recipients |
| S02 | Outlook seed mailbox | Controlled seed | Specific placement observed | Entire Outlook enterprise |
| S03 | Seed across different templates/content | Controlled seed | Trend spotted per template | Proven causal link |
| S04 | Seed missing message in window | Controlled seed | `UNKNOWN/NOT_OBSERVED` | Message definitely lost |
| O01 | Provider bounce/complaint rising | Production monitoring | Quality-drop signal | Single exact root cause |
| O02 | Provider accepted yet no delivered event | Production monitoring | Next milestone unobserved | Guaranteed failure |
| O03 | Open pixel fetched | Engagement telemetry | Pixel request recorded | Human read it |
| O04 | Email in Inbox without clicks | Seed/analytics | Inbox observed, no clicks | Content unread |
| O05 | Domain/IP reputation shift | Operational trend | Correlates with outcomes | Unit test has bug |
| O06 | Suppression bypassed on failover | End-to-end workflow | No send attempt created on B | No domain marks spam |

A single test case can check multiple things, yet its name and report must state the **strongest evidence actually observed**. For instance, `I02` must never show up on a CI dashboard labeled `DELIVERED_SUCCESS`.

### Never claim tests were run merely because they sit in docs

The table above is a **test plan and expected criteria**, not actual execution results from a live system. Reporting “tests passed” requires an actual test runner, environment, and run data.

## 45. Organizing the test suite to stay both fast and meaningful

A reference layout:

~~~text
src/test/java/.../mail/
  ReceiptMailServiceTest.java
  MarketingMailServiceTest.java
  MimeCompositionTest.java
  MailFailurePolicyTest.java
  SmtpLocalIntegrationTest.java
  SmtpScriptedFailureTest.java
  MailOutboxIntegrationTest.java
  ProviderWebhookContractTest.java

src/integrationTest/java/.../mail/
  ProviderStagingSmokeTest.java
  SeedMailboxObservationTest.java
~~~

This is an example structure; the `integrationTest` source set must be configured if the project lacks one. Gradle/Maven do not automatically recognize new directories without configuring tasks and dependencies.

### Execution tiers in CI

**Every pull request:**

- Unit Mockito.
- MIME composition.
- Local SMTP.
- Database/outbox integration.
- Scripted SMTP failures.
- Provider webhook consumer tests with fixtures.

**On a controlled schedule or pre-release:**

- Staging provider auth/config.
- DNS/SPF/DKIM/DMARC checks.
- Provider event API/webhook compatibility.
- Seed mailbox tests within authorized scope.

**Production:**

- Continuous delivery metrics and alerts.
- Synthetic canary using authorized accounts and test data.
- Reviews of complaint/bounce, suppression, and reputation trends.

Never require pull-request CI to send real emails to uncontrolled external recipients on every run. When provider tests require credentials, keep them in a secret store and isolate them from tests runnable by untrusted contributions.

### Controlling repeatability

An Internet test depends on DNS, provider uptime, spam filtering, and network egress; tests can flake even when application logic has not changed. Therefore:

- Unit/local integration tests must be deterministic.
- Staging/provider tests need timeouts and an `INCONCLUSIVE` state when external dependencies are unavailable.
- Never declare “good email deliverability” simply because a random seed test went green.
- Never use mocks to mask a provider outage and call it deliverability success.

## 46. A controlled synthetic canary

A canary can run periodically to catch issues unit tests cannot see:

~~~text
Canary generator
   |
   v
Create synthetic notification with unique correlation ID
   |
   v
Real application send pipeline -> approved SMTP provider
   |
   +--> provider accepted / deferred / bounce events
   |
   v
Seed mailbox reader with authorized access
   |
   v
Correlate observed folder + provider status
   |
   v
Emit scoped monitoring result
~~~

### Safety conditions

- Recipients are authorized test mailboxes.
- Payloads contain no real OTPs, customer documents, or secrets.
- Low frequency with a dedicated rate budget.
- Ability to pause the canary during provider throttling.
- Unique correlation IDs and test-data TTLs.
- Never use canaries to mail unconsented external addresses.
- Mechanism to clean up test emails in seed mailboxes per permissions/retention.

### Results should not be binary pass/fail

~~~json
{
  "testId": "canary-184",
  "applicationSubmission": "ACCEPTED",
  "providerDelivery": "DELIVERED",
  "seedPlacement": "SPAM",
  "observationWindow": "PT10M",
  "mailboxType": "CONTROLLED_SEED"
}
~~~

This is an **illustrative hypothetical result**. It shows the provider can report delivered while the seed mailbox lands in Spam: the two observations do not conflict.

### If the message is missing

`NOT_OBSERVED_WITHIN_WINDOW` differs from `BOUNCED`. Before concluding, check:

- Is the provider event still queued/deferred?
- Does the seed reader have permission for the right mailbox/folder?
- Is the mail sitting in Junk/Promotions/Quarantine?
- Was the correlation ID stripped or misformatted?
- Does the seed mailbox have indexing lag?
- Did mailbox rules automatically move the message?

Only after identifying the cause should you raise the appropriately scoped alert.

## 47. Operational metrics per layer

An understandable dashboard should split into multiple panels instead of one “email success” number:

| Group | Suggested metric | Used for |
| --- | --- | --- |
| Application intent | `mail_notifications_created_total` | Send requests created |
| Business validation | `mail_notifications_suppressed_total` | Requests validly blocked |
| Outbox | `mail_outbox_oldest_age_seconds` | Queue wait lag |
| Transport | `mail_smtp_attempts_total` | Physical attempts |
| Submission | `mail_submission_accepted_total` | Relay/provider accepted |
| Rejection | `mail_submission_rejected_total` | Failures at SMTP/API |
| Unknown | `mail_submission_unknown_total` | Needs reconciliation |
| Provider events | `mail_provider_delivery_events_total` | Delivered/deferred/bounced/complained |
| Event pipeline | `mail_provider_event_lag_seconds` | Webhook delay |
| Data quality | `mail_hard_bounces_total` | Invalid recipients and reputation |
| Suppression | `mail_suppression_actions_total` | Opt-out/complaint handling |
| Seed placement | `mail_seed_placements_total` | Inbox/Spam/Other/Unknown by seed |
| SMTP latency | `mail_smtp_submission_duration_seconds` | Transport slowness |
| API scheduling | `mail_dispatch_lateness_seconds` | Delay vs user schedule |
| Rate limiter | `mail_rate_limiter_denied_total` | Deferred before SMTP |

These are **illustrative metric names for the application to implement**, not built-in Spring Mail metrics.

### Useful dimensions

- `provider` or route.
- `category`: OTP, transactional, marketing.
- `recipientDomainGroup` or receiving provider grouped into a finite set if permitted.
- `failureKind`: auth, TLS, network, temp recipient, permanent recipient.
- `status`: accepted, deferred, bounced, unknown.
- `templateVersion` when cardinality is bounded.

**Never use full recipient email, notification UUID, raw Message-ID, subject, or token as metric labels.** Those are sensitive data and cause high cardinality.

### Meaningful alerts

| Signal | Initial interpretation |
| --- | --- |
| `mail_submission_accepted_total` drops sharply | Possible transport/provider/route failure |
| SMTP 535 spikes | Credential/account/TLS auth needs investigation |
| SMTP 550 spikes | Recipient list or sender policy needs classification |
| `mail_provider_event_lag_seconds` rises | Webhook pipeline slowed down |
| Provider delivered drops while SMTP accepted stays flat | Possible downstream delivery/provider issue |
| Seed Spam rises | Possible placement/reputation/content issue |
| Complaints rise | Inspect consent, content, and frequency |
| Unknown outcomes rise | Socket/timeout/transaction issues, duplicate risk |
| Bounce/complaint on A yet sender B still sends | Shared suppression or failover policy may be broken |

Never infer root cause from a single metric alone. Correlate message attempts, provider events, categories, and receiving domains.

## 48. Logs must state exact evidence, not assumptions

Poor log example:

~~~text
INFO Email delivered successfully to buyer@example.org
~~~

if it is logged immediately after `JavaMailSender.send()`.

Better-scoped log:

~~~json
{
  "event": "mail_submission_accepted",
  "notificationId": "notif-184",
  "providerKey": "smtp-primary",
  "evidence": "SMTP_FINAL_SUCCESS",
  "submitStatus": "SUBMITTED",
  "submittedAt": "2026-11-12T10:00:05Z"
}
~~~

Upon receiving a verified webhook:

~~~json
{
  "event": "mail_provider_delivery_status",
  "notificationId": "notif-184",
  "providerKey": "smtp-primary",
  "evidence": "VERIFIED_PROVIDER_EVENT",
  "deliveryStatus": "DELIVERED",
  "observedAt": "2026-11-12T10:05:10Z"
}
~~~

Never log raw bodies, full recipients, OTPs, reset URLs, SMTP AUTH transcripts, or whole webhooks containing PII. Correlation data still needs ACLs and retention.

### Important when using `@Async`

An async mail-sending method may return a future or finish after the HTTP request already responded. If the controller logs `Email delivered` when queuing an `@Async` task, both timing and meaning are even more wrong. Log:

- Request accepted/queued when persisted to outbox.
- Attempt started when worker calls transport.
- SMTP accepted when success is genuinely received.
- Provider delivery when a reliable event arrives.

Do not use `@Async` as a mechanism guaranteeing durable delivery; if the JVM dies before the task executes, in-memory work can be lost. A durable outbox/queue solves persistence requirements.

## 49. Runbook: unit tests pass, yet production emails never arrive

A common report:

> “CI confirms emails sent cleanly, yet customers cannot find the mail.”

Do not start by re-running the Mockito tests repeatedly. Trace **from application intent to the last observation point**, stopping wherever data disappears or an error appears.

### Step 1 — Verify the send request was actually created

- Was the right business event emitted?
- Was the outbox row committed?
- Was it blocked by validation, permissions, or suppression?
- Does the recipient belong to an allowed tenant and category?
- Was the email `CANCELLED`, `EXPIRED`, or before `scheduledAt`?

If no notification/outbox record exists, it is a business/orchestration bug, not SMTP deliverability.

### Step 2 — Verify the worker attempted transport

- Is the job `PENDING`, `RETRY_PENDING`, `PROCESSING`, or `SUBMITTED`?
- Are workers running? Is the queue congested?
- Did the rate limiter delay the job?
- Is there a log/attempt ID confirming SMTP began?
- Are there secret/auth or DNS/TLS errors?

If the worker never invoked SMTP, mock tests will not explain why production has not dispatched.

### Step 3 — Inspect the SMTP submission outcome

- Was there a final SMTP 250 after DATA or a success from the provider API?
- Was there `421`, `451`, `535`, `550`, `554`, or a timeout?
- Did the failure occur at connection, AUTH, MAIL FROM, RCPT TO, or DATA?
- If the reply was lost after DATA, is it marked `SUBMISSION_UNKNOWN`?
- Was the attempt recorded with provider key and correlation ID?

If the relay clearly rejected it, that is a submission failure; **never report delivered**. If the outcome is unknown, do not blindly resend because it may duplicate.

### Step 4 — Inspect provider queue/events

- Did the provider assign a message ID?
- Is the message queued, deferred, delivered, dropped, bounced, or complained?
- Are any webhook events unprocessed?
- Is provider event lag elevated?
- Does correlation match the recipient/provider account?
- Does the provider enforce its own suppression/complaint policy?

If the provider reports delivered under contract yet the user cannot see it in Inbox, investigate mailbox filtering/placement; do not conclude the provider is definitely wrong or the app is definitely right.

### Step 5 — Authorized mailbox/recipient inspection

- Ask the recipient to check Spam/Junk, Promotions, Other, and Quarantine if appropriate.
- Check mail rules, forwarding, aliases, and corporate gateways.
- Run a controlled seed test over the same route/domain if authorized.
- Inspect trusted authentication results on the received mail.
- Compare sender address/domain, subject, content version, and attachments.
- Never access a user’s personal mailbox without authorization.

### Step 6 — Conclude with an evidence-backed status

Example:

~~~text
Notification created: YES
SMTP attempt started: YES
Provider accepted: YES
Provider delivery event: DEFERRED
Seed Inbox observation: NOT AVAILABLE

Conclusion:
  "Provider has accepted and deferred this recipient;
   final delivery and Inbox placement not yet observed."
~~~

This is a far more responsible conclusion than “mock tests are green, email landed in Inbox”.

## 50. Runbook: SMTP accepted, yet bounce rate rises

If many messages are accepted by the provider and then hard bounces spike:

1. Identify affected receiving domains and categories.
2. Verify event signatures, deduplication, and per-recipient correlation.
3. Classify hard vs soft bounces using provider-specific evidence rather than guessing from one exception string.
4. Inspect domain list hygiene, unverified addresses, or recent imports.
5. Update suppressions for invalid recipients per policy.
6. Never retry a reliably hard-bounced mailbox via another provider.
7. Check whether any campaign mailed addresses lacking permission/consent.
8. Check whether a systemic sender account/identity policy error was misread as invalid recipient.
9. Measure accepted, bounced, deferred, and unknown separately within the same cohort/time window.
10. Once fixed, run a controlled canary instead of mass-resending every previously accepted mail.

### A mistake to avoid

When hard bounces spike, raising `maxRetries` from 3 to 100 will not fix non-existent mailboxes; it can hurt reputation and create excess traffic.

### Watch provider event types

A provider `bounce` can stem from many causes (recipient, policy, domain, mailbox full...). Never apply permanent suppression to every temporary bounce. Adapters must preserve normalized reasons and necessary evidence.

## 51. Runbook: provider reports delivered, yet seed mail lands in Spam

This is the classic scenario proving **delivery and Inbox placement differ**.

### Symptoms

~~~text
SMTP submission: ACCEPTED
Provider event: DELIVERED
Seed mailbox folder: SPAM
Unit Mockito: PASSED
~~~

There is no contradiction: mock tests check code; SMTP accepted checks the relay; provider delivered is the provider’s outcome; seed folder reflects placement on that mailbox.

### Investigation steps

1. Verify it is the exact message, sender domain, template version, and seed address.
2. Check SPF/DKIM/DMARC and alignment in trusted receiving headers.
3. Check domain/IP reputation and provider account health if telemetry exists.
4. Inspect content, links, attachments, unsubscribe handling, and sender identity.
5. Compare against other seed mailboxes to gauge scope.
6. Inspect mail server/recipient rules if authorized.
7. Assess bounce/complaint trends in the matching cohort.
8. Never try to evade filters by sending another identical copy to the same user.
9. Adjust content/configuration only with clear rationale, then run a controlled experiment.
10. Report “Spam observed on specific seed” instead of claiming all recipients are hitting Spam.

### Where Mockito remains useful

If a template might have rendered wrong or introduced an unexpected URL, Mockito/MIME unit tests help prove the application selected the right template/version. To discover why a receiving filter flagged Spam, however, you need data beyond mocks.

## 52. Runbook: CI “mail integration” passes, yet production SMTP hits AUTH 535

One likely reason is tests used:

~~~java
@MockitoBean
JavaMailSender sender;
~~~

or a `test` profile pointing to local SMTP. Those unit/integration tests never exercised real production credentials.

### Steps

1. Check test type: mock, fake SMTP, provider sandbox, or real SMTP account.
2. Check which configuration the production bean/qualifier actually uses.
3. Verify host, port, TLS mode, and AUTH mechanism.
4. Check secret rotation, account status, and provider policy/permissions.
5. Distinguish account-level AUTH 535 from recipient-level failures.
6. Stop the retry storm; do not spam logins repeatedly with wrong credentials.
7. Try a smoke submission on an approved staging/canary account.
8. Protect accounts and template categories before rolling back out.
9. Add config-contract tests and appropriate alerts.
10. Never replace mock tests with production SMTP calls that could accidentally mail real recipients on every PR.

### Do not fix by disabling TLS

If AUTH fails due to TLS configuration or provider policy, never strip STARTTLS/certificate verification to turn tests green. Fix the real configuration and permissions.

## 53. Runbook: final SMTP 250 received, yet recipient has no mail

After final 250:

1. Save provider/relay message ID and timestamp if available.
2. Check the provider activity log.
3. Check deferred, delivered, bounced, and dropped events.
4. Verify notification/recipient mapping, especially Bcc or multiple RCPT TOs.
5. If the provider has no final event yet, keep the corresponding state—do not mark Inbox.
6. If the provider reports delivered, check recipient filtering/Quarantine/Junk/Other with proper authorization.
7. If no provider event arrived, inspect webhook health and event lag before concluding.
8. Do not auto-resend, as it risks duplicates.
9. For sensitive emails/OTPs, enforce expiry and alternative support channels per policy.
10. Document the last observed milestone and what remains unknown.

### Do not treat Message-ID as an exactly-once guarantee

The Message-ID header helps correlation, yet SMTP servers/receiving mailboxes are not required to drop every duplicate sharing a Message-ID. Never trigger a resend assuming “the mailbox will deduplicate it”.

## 54. Common mistakes in code and reporting

### 54.1. Naming a unit test `emailDeliveredSuccessfully`

When the sole assertion is `verify(sender).send(...)`. Rename it to match the evidence: `invokesMailSenderWithExpectedMessage`.

### 54.2. `@SpringBootTest` + mocked transport labeled E2E

A real context does not equal real transport. Label it clearly as wiring integration with mocks.

### 54.3. Using `assertDoesNotThrow(sender.send(...))` on a mock sender

A default void mock throws nothing; the test does not exercise SMTP.

### 54.4. Stubbing `send()` to succeed and calling it provider accepted

A Mockito stub is fake data. Only a real provider or fake SMTP supplies evidence at that layer.

### 54.5. Mocking `MimeMessage` too when trying to test MIME structure

Method calls cannot prove multipart/charset/attachments serialize properly. Use a real Jakarta Mail `MimeMessage` in MIME tests.

### 54.6. Checking only Subject and To

Ignoring From, Reply-To, plain-text alternatives, MIME encoding, Bcc, and attachments when the business needs them. State scope explicitly instead of claiming the entire email was tested.

### 54.7. Treating localhost GreenMail as Internet delivery

GreenMail proves a local server accepted SMTP; it does not evaluate real DNS, reputation, or recipient filtering.

### 54.8. Testing SMTP with all TLS/auth turned off and claiming production config works

TLS/auth must be tested separately with matching configuration. Local plain SMTP only tests basic transport logic.

### 54.9. Treating final SMTP 250 as Inbox

Relay acceptance does not guarantee remote mailbox placement.

### 54.10. Treating provider `delivered` as recipient read

Usually false; the provider does not observe user reading behavior.

### 54.11. Treating an open pixel as “read”

Images may be auto-fetched or blocked. Use accurate wording and measurement goals.

### 54.12. Ignoring the Bcc envelope

Absence of a Bcc header proves nothing about whether SMTP sent to the hidden recipient. Inspect the envelope separately.

### 54.13. Merging multi-recipient outcomes into `sent=true`

Fails to separate accepted/rejected/bounced per person, causing duplicate retries.

### 54.14. Failing to store provider message IDs

Makes it hard to reconcile accepted, delivered, bounced, and late events.

### 54.15. Trusting every webhook without verification

Spoofed events can make the app falsely record `DELIVERED` or suppress the wrong recipient.

### 54.16. Counting webhook redeliveries as multiple deliveries

Event ID deduplication and per-recipient correlation are mandatory.

### 54.17. Retrying whenever `delivered` has not appeared yet

The provider may have accepted and be retrying downstream; sending more creates duplicate risk.

### 54.18. Omitting `SUBMISSION_UNKNOWN`

Losing the final reply after DATA creates an immediately unverifiable situation. Treating every exception as definitely unsent is wrong.

### 54.19. Testing one seed mailbox and claiming 100% deliverability

One result does not represent all receiving domains and user conditions.

### 54.20. Leaving deliverability denominators undefined

Event counts, recipient submissions, attempts, and notifications are distinct units. Never mix them in one ratio.

### 54.21. Treating SPF pass as DMARC pass

SPF identity must satisfy DMARC alignment with header From. DKIM domain alignment must also be checked.

### 54.22. Treating DMARC pass as guaranteed non-Spam

Authentication does not equal reputation or placement. Monitor multiple signals.

### 54.23. Sending test emails to unconsented production recipients

Testing must never spam users or violate consent. Use seed accounts or authorized canaries.

### 54.24. Keeping raw bodies/recipients in metrics and logs

Leaks PII/tokens and inflates cardinality. Use sanitized metadata, ACLs, and retention.

### 54.25. Reporting “sent successfully” immediately upon queuing an async task

Enqueue, dispatch, submit, and delivery are distinct steps. UI/logs must name states accurately.

### 54.26. Increasing retries to fix bounces or Spam

Retries do not fix invalid mailboxes, DMARC/reputation, or consent. They can cause duplicates and complaints.

### 54.27. Bypassing suppression when switching providers

Complaints/hard bounces from provider A must follow a shared policy; never route via B to evade rejections.

### 54.28. Blaming Spring Mail when recipient filters change

If SMTP/relay already accepted, investigate downstream reputation/filtering instead of tweaking the MIME builder baselessly.

### 54.29. Skipping integration tests after switching providers

Unit mocks remain green even when credentials, DKIM, From identities, and provider event schemas change. Run smoke tests and monitoring at the right layers.

### 54.30. Hiding UNKNOWN state

When evidence is lacking, letting UI assign DELIVERED/FAILED leads to bad resends and misdirected investigations. UNKNOWN is a useful, honest state.

## 55. Checklist for reviewing a PR containing JavaMailSender mocks

### Unit tests

- [ ] Tests state clearly which application behavior is verified, never using “delivered” when only mocking.
- [ ] `verify(sender.send(...))` checks the right overload and invocation count.
- [ ] `ArgumentCaptor` or matchers inspect needed recipient/from/subject/body fields.
- [ ] Suppression/validation branches never invoke the sender.
- [ ] Tests simulate exceptions and retry/stop policies.
- [ ] No Internet connectivity needed in unit tests.
- [ ] When building MIME, a real `MimeMessage` checks structure/encoding.
- [ ] Never mock MIME completely when testing serialized parts.

### Integration tests

- [ ] Tests connect `JavaMailSenderImpl` to an isolated fake SMTP server.
- [ ] Plain text/HTML, Unicode, and attachments verified as required.
- [ ] Bcc envelopes tested separately from headers when needed.
- [ ] Scripted SMTP tests cover permanent/temporary/auth/unknown outcomes.
- [ ] Local SMTP `250` is not treated as delivery to real mailboxes.
- [ ] Outbox/DB and post-crash recovery tested if using async workflows.
- [ ] Provider webhook signatures, deduplication, correlation, and out-of-order events tested.
- [ ] No test hiding a Mockito bean is labeled “real SMTP E2E”.

### Provider and domain

- [ ] Provider account/sender identity verified in appropriate staging.
- [ ] TLS/STARTTLS, DNS, and network egress verified in matching environments.
- [ ] SPF/DKIM/DMARC and alignment verified from authoritative sources.
- [ ] Provider definitions of `accepted`, `delivered`, `deferred`, and `bounced` understood.
- [ ] Correlation links notification/attempt/recipient/provider events.
- [ ] Authorized seed inbox tests exist when Inbox placement is a goal.
- [ ] Ambiguous/unknown outcomes have explicit handling.

### Production and privacy

- [ ] Dashboards separate `SUBMITTED`, `DELIVERED`, `BOUNCED`, and `UNKNOWN`.
- [ ] Every metric defines its denominator and observation window.
- [ ] Mock successes are never used as deliverability metrics.
- [ ] Monitoring covers bounces, complaints, suppressions, and provider event lag.
- [ ] No auto-resends when provider accepted or outcome is unknown.
- [ ] No OTPs, raw bodies, or full email addresses in logs/metric labels.
- [ ] Canaries mail authorized mailboxes only, never strangers.
- [ ] Runbook exists for “unit tests pass yet production mail does not arrive”.

Checklists support design and review. Ticking an item in a document does not prove tests were executed; real runs and evidence are required in each environment.

## 56. Decision tree: what are you trying to prove?

~~~mermaid
flowchart TD
    A{"What is the testing question?"}
    A -- "Does service call sender properly?" --> B["Mockito + ArgumentCaptor"]
    A -- "Is MIME structure valid?" --> C["Jakarta Mail MIME test"]
    A -- "Does SMTP client transmit data?" --> D["Local/scripted SMTP server"]
    A -- "Does provider accept submission?" --> E["Authorized provider integration"]
    A -- "Was remote recipient delivered?" --> F["Trusted provider/DSN evidence"]
    A -- "Did message land in Inbox?" --> G["Authorized seed mailbox observation"]
    A -- "Did user read it?" --> H["Explicit product interaction if available"]
~~~

Each branch answers a different question. You do not have to implement every branch for every feature; what matters is **never claiming evidence from branch B as the answer to G or H**.

### Guidelines for writing acceptance criteria

For example, the user story “When an order payment succeeds, the system must email a receipt” can split into:

1. Create notification for the right recipient after the business transaction commits.
2. Worker sends valid MIME content through the configured SMTP relay.
3. Capture submission outcome and record accurate status.
4. Track provider bounces/deliveries when available.
5. Never duplicate a notification across retries/restarts.
6. Alert if failure rates climb.

If the business requirement is “improve email Inbox placement”, add a **measurement plan** with seed mailboxes, reputation/provider signals, and an observation window; you cannot close that ticket simply because unit tests pass.

## 57. End-to-end walkthrough: tests pass, yet recipient receives no receipt

Suppose the team has a test:

~~~text
Test: ReceiptMailServiceTest
Status: PASSED
Assertion: verify(sender).send(expectedMessage)
~~~

Deployed to production, some customers report missing emails.

### Stage A: application

Inspect the outbox:

~~~text
notificationId: receipt-184
status: PROCESSING
lastAttemptAt: 2026-11-12T10:00:03Z
provider: smtp-primary
~~~

This is an example record. `PROCESSING` does not tell us the SMTP outcome yet.

### Stage B: SMTP

Normalized log:

~~~text
smtpPhase=RCPT_TO
smtpCode=550
enhancedCode=5.1.1
failureKind=INVALID_RECIPIENT
~~~

With reliable `550 5.1.1` evidence at the recipient phase, the application should stop retrying this address per policy and help verify/correct the address. **The mock test is still correct regarding “service called sender”**, yet could not test the real mailbox.

### Stage C: if the SMTP relay accepted

Another recipient:

~~~text
notificationId: receipt-185
SMTP final reply: 250 accepted
provider status: deferred
last provider event: 10:02Z
~~~

At this point it is no longer a “service failed to call send” bug. Monitor the provider/remote domain and downstream retry policy. Do not immediately send another copy because the message was already accepted.

### Stage D: if the provider delivered, yet the user sees nothing

~~~text
notificationId: receipt-186
SMTP: 250 accepted
provider: delivered
recipient feedback: "Not in Inbox"
seed mailbox observation: spam in an authorized test
~~~

This is a placement/recipient-filtering issue needing investigation. It cannot be fixed with Mockito `when(sender.send(...))` because that void method was previously mocked and transport was never exercised in unit tests.

### Lesson from the walkthrough

A green test suite is not meaningless; it proved sender invocation construction works. The mistake is **using that narrow valid result to claim a broader unmeasured outcome**.

## 58. End-to-end walkthrough: tests pass, yet UI shows the wrong status

Suppose the worker writes:

~~~java
try {
    javaMailSender.send(message);
    repository.markDelivered(notificationId);
} catch (MailException error) {
    repository.markFailed(notificationId);
}
~~~

With a mocked sender:

1. `send()` throws nothing.
2. `markDelivered()` is called.
3. The test asserts `DELIVERED` state.
4. Developers conclude “delivery pipeline works”.

In reality, the test only checked that code called `markDelivered`, while **the method name and domain state were semantically wrong from the design stage**.

An improvement:

~~~text
SMTP success -> SUBMITTED
Provider authenticated delivered event -> DELIVERED
Verified seed mailbox observation -> INBOX/OTHER/UNKNOWN
Real product action -> separate engagement/confirmation
~~~

A transactional email system is not required to know Inbox placement for every recipient. Having an UNKNOWN state is normal when external sources provide no data.

## 59. Self-check questions

**1. Does `verify(javaMailSender).send(...)` prove the email reached a mailbox?**

No. It only proves a call to a mock/spy with the arguments checked in the test.

**2. Does a default `JavaMailSender` mock open a TCP socket?**

No. Mockito void methods perform no SMTP transport unless specially configured.

**3. If `assertDoesNotThrow` passes on a mock sender, does SMTP work?**

No. Default mocks never throw, so it only proves no exception was simulated.

**4. Is `@SpringBootTest` enough to make a test an SMTP integration test?**

No. If the sender bean was replaced by a mock, the test only exercises Spring context wiring and orchestration around the mock.

**5. When should ArgumentCaptor be used?**

When verifying the exact message the service passes to the sender: recipient, subject, body, category, or relevant properties.

**6. Why is real MIME needed when testing HTML/attachments?**

To check multipart structure, headers, charsets, and layout after serialization, rather than merely verifying builder method calls.

**7. Does a local GreenMail test prove the production provider accepts mail?**

No. It tests SMTP submission to a fake/local relay under test configuration.

**8. What does a test server returning 250 after DATA prove?**

It proves **that** relay accepted the submission in the test, not remote Internet mailboxes.

**9. Does SMTP 250 after DATA mean the message is in the Inbox?**

No. The relay can queue, retry, or bounce downstream; receiving mailboxes also filter Spam/Junk.

**10. Does provider `delivered` mean the recipient read it?**

No. Provider-defined delivered usually reflects delivery/acceptance at the destination, not human reading behavior.

**11. Should open pixels be used as proof an email was read?**

Not as reliable proof. Email clients, proxies, and scanners may auto-fetch or block images.

**12. Is one seed mailbox landing in Inbox enough to report 100% Inbox rate?**

No. That is only an observation on one mailbox, one payload, and one point in time.

**13. Does SPF pass equal DMARC pass?**

Not automatically. DMARC requires authentication aligned with header From under SPF/DKIM alignment rules.

**14. Does DKIM pass equal Inbox placement?**

No. Domain authentication and spam classification are separate concerns.

**15. Can Message-ID prevent all end-to-end duplicates?**

No. That header aids correlation, yet does not guarantee receiving servers deduplicate messages.

**16. Why is `SUBMISSION_UNKNOWN` needed?**

Because losing the final SMTP reply after DATA can leave the app unsure whether the relay accepted, and blind retries risk duplicates.

**17. Should you resend after provider accepted when no delivered event has arrived?**

Not automatically. The provider may still be queuing/retrying and events may lag.

**18. If a provider delivered event arrives twice, were two emails delivered?**

No. It could be webhook redelivery; deduplicate events by provider event identity and correlation.

**19. Why store results per recipient?**

Because multiple recipients of the same message can have different outcomes; collapsing into one `sent=true` causes wrong retries.

**20. What source must be used to measure inbox placement?**

An authorized mailbox observation source, such as seed accounts or a measurement system with a clear placement definition, reported with sample size, window, and representativeness limits.

**21. Does seeing no bounce after a few minutes prove delivery?**

No. The provider may still be retrying, events may lag, or the mailbox may have accepted and filtered it.

**22. Why verify webhook signatures?**

To prevent spoofed HTTP events from making the application record false delivered/bounced states.

**23. If a user did not receive an OTP, should retries be increased infinitely?**

No. Inspect expiry, transport/provider errors, recipient state, rate limits, and UX; retries need a budget and must not emit stale useless codes.

**24. If an email lands in Spam on a seed, does it mean all recipients hit Spam?**

No. The result is scoped to that seed, content, and time. Use it to investigate trends.

**25. Why do deliverability measurements need clear denominators?**

Because attempts, notifications, recipients, and provider events are different units; missing definitions distort percentages.

**26. Should raw recipient emails be used as metric labels?**

No. That creates privacy risk and high cardinality; use permitted provider/category/domain groups.

**27. With `@Async`, does a controller returning 200 mean the email was sent?**

No. The HTTP response may only confirm scheduling an in-memory task. A durable outbox and separate transport evidence are needed.

**28. When switching SMTP providers, are green unit mocks enough?**

No. Verify credentials, TLS, verified senders, DNS authentication, quotas, provider events, and appropriate seed observations.

**29. Does a test simulating provider `delivered` prove real delivery?**

No. It only proves the consumer processes a fixture event correctly.

**30. Which sentence best describes a passing mock unit test?**

“The application invoked `JavaMailSender.send(...)` with the expected data in the test scenario.” Claiming “relay accepted”, “provider delivered”, or “Inbox” requires additional evidence at the corresponding layer.

## Conclusion

**Mocking `JavaMailSender` and concluding deliverability is a reasoning mistake about test scope, not a flaw in Mockito.** Mocks are an excellent tool for verifying business branching, recipients, subjects, templates, suppression, and error-handling decisions. Yet a `verify(send)` call opens no SMTP connection, checks no DNS/TLS/AUTH, sends no RCPT TO/DATA, and observes no provider, receiving server, or mailbox. Even when `JavaMailSenderImpl` genuinely receives a final SMTP 250, that is still only **submission accepted**, not proof the message reached the Inbox or was read.

Reliable production engineering requires **multiple layers of evidence**: Mockito unit tests; MIME composition tests with real Jakarta Mail; local/scripted SMTP integration; provider staging/real-account verification when authorized; authenticated, deduplicated, correlated delivery/bounce webhooks; controlled seed mailbox observations when Inbox placement is a goal; and long-term monitoring of bounces, complaints, authentication, reputation, and queue lag.

Finally, tie `SUBMITTED`, `DELIVERED`, `BOUNCED`, `SUBMISSION_UNKNOWN`, and `INBOX` to their **authoritative data sources**, never conflating these milestones in APIs or dashboards. Name tests for what they truly prove, define denominators and observation windows for every rate, and avoid blind retries/resends simply because delivered evidence is absent. **A green test is a good signal about the tested code slice; true deliverability can only be assessed through proper observation across the entire email journey.**
