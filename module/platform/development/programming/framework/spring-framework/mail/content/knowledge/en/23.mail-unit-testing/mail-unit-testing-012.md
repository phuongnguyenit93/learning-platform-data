# Separating Template Selection Logic Tests from Transport Tests

In a **Spring Framework Mail** application, sending an email is usually the result of many decisions and processing steps: the system identifies a business event, chooses an email type and language, selects the right template, renders the subject/body, and then builds a MIME message and sends it via `JavaMailSender`. When everything lives inside one method, testing becomes convoluted: verifying "a confirmed order picks the right Vietnamese template" forces you to spin up a fake SMTP server, while verifying "the email has a Unicode subject and valid HTML body" forces you to construct an order, create a customer, and run the whole business workflow.

A cleaner approach is **separating template selection logic tests from transport tests**. Template selection is an application decision: picking a content template based on notification type, language, business state, or an intentional variant. Transport is an infrastructure responsibility: receiving rendered content, assembling a MIME email with To/From/Subject/body/attachments, and calling the mail sender. The two parts have distinct inputs, outputs, risks, and testing techniques.

The goal is not merely faster test runs. This boundary tells you **exactly which change broke a test**, avoids sending real mail in unit tests, cuts unnecessary mocking, and prevents template-selection logic from accidentally depending on SMTP.

This lesson builds a selector → renderer → gateway architecture; walks through Java, JUnit 5, Mockito, and Spring Mail examples; and explains test data design, negative cases, HTML/Unicode, transport errors, integration, and common pitfalls.

## 1. Distinguish three responsibilities, not just two layers

An email-sending flow can involve:

1. **Template selection**: which template should this email use?
2. **Template rendering**: how is data substituted into the template to produce the subject and body?
3. **Transport**: how is the rendered content packaged and transmitted as MIME?

Suppose an application has three purposes:

- `ORDER_CONFIRMED`: order confirmation.
- `PASSWORD_RESET`: password reset instructions.
- `INVOICE_READY`: invoice ready notification.

When order `ORD-2048` is confirmed and the user wants a Vietnamese email:

~~~text
Business event: ORDER_CONFIRMED
Locale: vi-VN
    |
    v
Template selector
    -> order-confirmation/vi-VN/v1
    |
    v
Template renderer
    -> Subject: Order ORD-2048 confirmed
    -> Plain text: Hello...
    -> HTML: <p>Hello...</p>
    |
    v
Mail transport gateway
    -> To, From, Subject, MIME multipart, UTF-8
    -> JavaMailSender.send(...)
~~~

**Selector tests** should only assert that `ORDER_CONFIRMED + vi-VN` selects `order-confirmation/vi-VN/v1`. They do not need to know about SMTP hosts, MIME boundaries, or `JavaMailSender`.

**Renderer tests** assert that data is interpolated accurately into subject/plain text/HTML and untrusted data is escaped. They need no SMTP sends.

**Transport tests** assert that given complete rendered content, the gateway constructs and sends MIME properly or handles send failures appropriately. They do not need to know what state an order is in or why the selector picked a template.

## 2. Why does an all-in-one test break easily?

Suppose you have a service like:

~~~java
@Service
public class OrderMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final OrderRepository orders;

    public void sendConfirmation(UUID orderId, Locale locale) {
        Order order = orders.findById(orderId)
                .orElseThrow();

        String template = locale.getLanguage().equals("vi")
                ? "mail/order-vi"
                : "mail/order-en";

        // Render template, build MimeMessage,
        // set subject, send SMTP...
    }
}
~~~

If tests use `@SpringBootTest` and a mock SMTP server for every case, an assertion on language fallback can fail because the server isn't running, TLS config changed, or repository mocking was off. Conversely, transport tests have to set up an order and locale even though transport cares about neither.

Signs you need to split:

- Selector tests have to mock `JavaMailSender`.
- MIME tests have to construct `OrderRepository` and domain events.
- A Unicode subject bug breaks locale-fallback tests.
- Tests use real SMTP just to verify an enum maps to a template name.
- Every template variant adds another slow integration test.
- Switching SMTP providers forces edits to business/template tests.

**Principle:** Every test should have one primary reason to fail. Never force a template-selection unit test through the network, a Spring context, or MIME when the behavior under test is a pure data decision.

## 3. Recommended architecture for Spring Framework Mail

~~~mermaid
flowchart TD
    A["HTTP / Scheduler / Domain event"] --> B["Application handler"]
    B --> C["Authorization + recipient policy"]
    C --> D["Template selector"]
    D --> E["TemplateSelection"]
    E --> F["Template renderer"]
    F --> G["RenderedMail"]
    G --> H["MailGateway interface"]
    H --> I["SpringMailGateway"]
    I --> J["MimeMessageHelper"]
    J --> K["JavaMailSender"]
    K --> L["SMTP relay"]
~~~

Contracts to keep clear:

| Component | Accepts | Returns or does | Preferred test type |
| --- | --- | --- | --- |
| Application handler | Business command, actor, entity | Orchestrates use case | Interaction and policy unit test |
| Template selector | Purpose, locale, rule context | Template descriptor | **Pure unit test** |
| Template renderer | Descriptor and view model | Subject, plain text, HTML | Renderer unit/component test |
| MailGateway | `RenderedMail`, send metadata | Sends or throws classified error | **Transport unit test** |
| JavaMailSender | `MimeMessage`/transport config | SMTP send | Tested with fakes, SMTP integration |
| SMTP provider | SMTP session | Acceptance/rejection | Integration contract when needed |

Point infrastructure interfaces in the right dependency direction: the application layer depends on the `MailGateway` abstraction, never directly on host, port, or SMTP details.

### Different tests protect different contracts

- **Selector contract:** each purpose and locale maps to a valid template.
- **Renderer contract:** data renders accurately, safely, and with proper fallback content.
- **Gateway contract:** valid MIME, accurate headers/recipients/encoding, and right exception handling.
- **Wiring contract:** Spring injects the right implementation, template engine, and sender.
- **Provider contract:** SMTP/TLS/AUTH config works against a real server or sandbox.

Never use high-level tests to replace all low-level tests, and never re-test every selector rule inside SMTP tests.

## 4. Data design for template selection logic

First represent the **email purpose** using an application-controlled enum:

~~~java
public enum MailPurpose {
    ORDER_CONFIRMED,
    PASSWORD_RESET,
    INVOICE_READY
}
~~~

A key identifying a selection rule:

~~~java
public record TemplateKey(
        MailPurpose purpose,
        String localeTag) {
}
~~~

A template selection result:

~~~java
import java.util.Locale;

public record TemplateSelection(
        String templateCode,
        Locale locale,
        int version) {
}
~~~

`templateCode` is an internal code like `mail/order-confirmation`, never an arbitrary path supplied by an HTTP request. `version` identifies the template version per project conventions. `locale` is the resolved language the renderer actually uses after the selector applies fallback rules.

### Why return a descriptor instead of a bare filename?

If the selector returns only a `String`, callers may have to guess the resolved fallback locale, version, or variant. A `TemplateSelection` carries everything needed so the renderer focuses purely on rendering without repeating selection logic.

### Never let the selector send emails

A clean selector never accepts `JavaMailSender`, never creates `MimeMessage`, and never calls SMTP. Its `select(...)` method should be a pure computation over provided inputs and catalog configuration.

## 5. Pure Java TemplateSelector example

Below is a small implementation using a catalog keyed by purpose and locale. It checks the exact requested locale first, then falls back to the default language if available.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public final class MailTemplateSelector {

    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private final Map<TemplateKey, TemplateSelection> catalog;

    public MailTemplateSelector(
            Map<TemplateKey, TemplateSelection> catalog) {
        this.catalog = Map.copyOf(catalog);
    }

    public TemplateSelection select(
            MailPurpose purpose,
            Locale requestedLocale) {

        Objects.requireNonNull(purpose, "purpose");

        Locale locale = requestedLocale == null
                ? DEFAULT_LOCALE
                : requestedLocale;

        TemplateKey exact = new TemplateKey(
                purpose,
                locale.toLanguageTag()
        );

        TemplateSelection selected = catalog.get(exact);
        if (selected != null) {
            return selected;
        }

        TemplateKey fallback = new TemplateKey(
                purpose,
                DEFAULT_LOCALE.toLanguageTag()
        );

        selected = catalog.get(fallback);
        if (selected != null) {
            return selected;
        }

        throw new TemplateUnavailableException(
                "No template available for " + purpose
        );
    }
}
~~~

`TemplateUnavailableException` is an application-defined exception, for example extending `RuntimeException`. `Map.copyOf` builds an unmodifiable snapshot through this reference; the value objects inside should likewise be immutable.

The illustrative code uses only an exact locale tag and a default fallback. A real product may require richer fallback chains:

~~~text
vi-VN -> vi -> en-US
en-AU -> en -> en-US
fr-CA -> fr -> fr-FR -> en-US
~~~

Do not invent this order unless business rules specify it. Tests must mirror the application's **exact locale policy**.

### Catalog example

~~~java
Map<TemplateKey, TemplateSelection> catalog =
        Map.of(
                new TemplateKey(
                        MailPurpose.ORDER_CONFIRMED,
                        "vi-VN"
                ),
                new TemplateSelection(
                        "mail/order-confirmed",
                        Locale.forLanguageTag("vi-VN"),
                        1
                ),

                new TemplateKey(
                        MailPurpose.ORDER_CONFIRMED,
                        "en-US"
                ),
                new TemplateSelection(
                        "mail/order-confirmed",
                        Locale.forLanguageTag("en-US"),
                        1
                ),

                new TemplateKey(
                        MailPurpose.PASSWORD_RESET,
                        "vi-VN"
                ),
                new TemplateSelection(
                        "mail/password-reset",
                        Locale.forLanguageTag("vi-VN"),
                        2
                )
        );
~~~

The same `templateCode` can serve multiple locales when the renderer resolves resources by locale, or each locale can have its own code. What matters is keeping the contract between selector and renderer consistent.

## 6. Unit test the selector without starting Spring

Use JUnit 5 with direct constructor instantiation:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MailTemplateSelectorTest {

    private MailTemplateSelector selector;

    @BeforeEach
    void setUp() {
        Map<TemplateKey, TemplateSelection> catalog =
                Map.of(
                        new TemplateKey(
                                MailPurpose.ORDER_CONFIRMED,
                                "vi-VN"
                        ),
                        new TemplateSelection(
                                "mail/order-confirmed",
                                Locale.forLanguageTag("vi-VN"),
                                1
                        ),

                        new TemplateKey(
                                MailPurpose.ORDER_CONFIRMED,
                                "en-US"
                        ),
                        new TemplateSelection(
                                "mail/order-confirmed",
                                Locale.forLanguageTag("en-US"),
                                1
                        )
                );

        selector = new MailTemplateSelector(catalog);
    }

    @Test
    void selectsVietnameseForVietnameseOrder() {
        TemplateSelection result = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                Locale.forLanguageTag("vi-VN")
        );

        assertEquals(
                "mail/order-confirmed",
                result.templateCode()
        );

        assertEquals(
                "vi-VN",
                result.locale().toLanguageTag()
        );

        assertEquals(1, result.version());
    }

    @Test
    void selectsEnglishWhenEnglishRequested() {
        TemplateSelection result = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                Locale.forLanguageTag("en-US")
        );

        assertEquals(
                "en-US",
                result.locale().toLanguageTag()
        );
    }

    @Test
    void fallsBackWhenLocaleIsNotAvailable() {
        TemplateSelection result = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                Locale.forLanguageTag("ja-JP")
        );

        assertEquals(
                "vi-VN",
                result.locale().toLanguageTag()
        );
    }

    @Test
    void rejectsPurposeWithoutAnyTemplate() {
        assertThrows(
                TemplateUnavailableException.class,
                () -> selector.select(
                        MailPurpose.INVOICE_READY,
                        Locale.forLanguageTag("vi-VN")
                )
        );
    }
}
~~~

These tests:

- Need no `@SpringBootTest`.
- Need no mail server.
- Do not mock `JavaMailSender`.
- Need no Spring context or database.
- Run fast and focus cleanly on template selection rules.

**Key point:** tests assert `TemplateSelection` or business-meaningful fields; they never assert how many times `MimeMessageHelper` was called.

## 7. What cases should selector tests cover?

Common dimensions:

| Input/scenario | What to verify |
| --- | --- |
| Valid purpose, locale has template | Selects exact template |
| Locale missing translation | Falls back per policy |
| Null locale | Uses default locale or rejects per contract |
| Purpose with no template | Throws explicit error, never picks arbitrarily |
| Different template version | Selects right version per rule |
| Feature flag/variant | Selects consistent, justified variant |
| Different tenant or brand | Never picks another tenant's template |
| Security-sensitive notification type | Never falls back to marketing template |
| Catalog missing key | Fails closed or falls back by rule |
| Two close locales | Handles language and region per rule |
| Invalid event | Never picks a template merely by similar name |

There is no need for an SMTP integration test for every combination in this table. Write **parameterized unit tests** when many similar cases exist.

### Parameterized tests for locales

~~~java
@ParameterizedTest
@CsvSource({
        "vi-VN,vi-VN",
        "en-US,en-US",
        "ja-JP,vi-VN"
})
void choosesExpectedLocale(
        String requested,
        String expected) {

    TemplateSelection selection = selector.select(
            MailPurpose.ORDER_CONFIRMED,
            Locale.forLanguageTag(requested)
    );

    assertEquals(
            expected,
            selection.locale().toLanguageTag()
    );
}
~~~

No sender mock is needed here. When fallback policy changes, only selector tests and the matching catalog configuration need review.

## 8. Never let HTTP clients choose arbitrary templates

Suppose an endpoint receives:

~~~json
{
  "orderId": "ORD-2048",
  "template": "mail/password-reset"
}
~~~

If the application service trusts the `template` field directly, callers can request a template outside the use case or produce misleading content. In some systems, building template paths from input even introduces path traversal or template injection risks if resource loaders and data are unchecked.

Better approach: commands carry business intent or resource IDs:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        UUID actorId) {
}
~~~

The application service verifies the order and actor, then selects:

~~~java
TemplateSelection selection = selector.select(
        MailPurpose.ORDER_CONFIRMED,
        recipientLocale
);
~~~

**Selector tests do not replace authorization tests.** Verify separately that the caller is authorized to trigger the notification and the recipient is allowed to receive it. Yet selecting `MailPurpose` should stem from a controlled use case, never an arbitrary value altering routing or templates.

## 9. Separate rendering from selection

The selector returns a descriptor; the renderer accepts the descriptor and a view model and builds content:

~~~java
public record RenderedMail(
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

~~~java
public interface MailTemplateRenderer {
    RenderedMail render(
            TemplateSelection selection,
            OrderMailViewModel model);
}
~~~

~~~java
public record OrderMailViewModel(
        String recipient,
        String customerName,
        String orderCode) {
}
~~~

These records illustrate data for order confirmation emails. For multiple email types, design a typed view-model hierarchy for password resets, invoices, and marketing rather than forcing every template to accept an untyped map.

### What must the renderer do?

Depending on template engine and product:

- Load the template matching `templateCode`/`locale`/`version`.
- Interpolate dynamic data into subject and body.
- Escape HTML text nodes and attributes contextually.
- Produce both plain text and HTML when needed.
- Handle locale-specific date, number, and currency formatting.
- Prevent templates from accessing unprovided data.
- Report clear errors when resources or required variables are missing.

The renderer has no reason to call SMTP. It only produces content.

## 10. Renderer unit tests differ from selector unit tests

A renderer test can use real template resources and fixed data:

~~~java
@Test
void rendersOrderCodeIntoBothBodies() {
    TemplateSelection selection = new TemplateSelection(
            "mail/order-confirmed",
            Locale.forLanguageTag("vi-VN"),
            1
    );

    OrderMailViewModel model =
            new OrderMailViewModel(
                    "buyer@example.org",
                    "Minh",
                    "ORD-2048"
            );

    RenderedMail rendered =
            renderer.render(selection, model);

    assertTrue(
            rendered.subject().contains("ORD-2048")
    );

    assertTrue(
            rendered.plainText().contains("ORD-2048")
    );

    assertTrue(
            rendered.htmlText().contains("ORD-2048")
    );
}
~~~

Here `renderer` is an instance of the implementation under test using a template fixture—not a mock that merely proves the mock returns what was stubbed.

Another test protects escaping:

~~~java
@Test
void escapesUntrustedCustomerNameInHtml() {
    TemplateSelection selection = new TemplateSelection(
            "mail/order-confirmed",
            Locale.forLanguageTag("vi-VN"),
            1
    );

    OrderMailViewModel model =
            new OrderMailViewModel(
                    "buyer@example.org",
                    "<img src=x onerror=alert(1)>",
                    "ORD-2048"
            );

    RenderedMail rendered =
            renderer.render(selection, model);

    assertFalse(
            rendered.htmlText().contains(
                    "<img src=x onerror=alert(1)>"
            )
    );
}
~~~

This example checks only that the dangerous HTML string does not appear verbatim; real tests should also verify contextually escaped output such as `&lt;` and `&gt;`, while preventing untrusted data from entering URLs, JavaScript, or CSS without dedicated encoding/validation.

### Thymeleaf: th:text and th:utext

When using Thymeleaf to render HTML emails:

~~~html
<p th:text="${customerName}">Customer name</p>
~~~

`th:text` escapes data for text context. `th:utext` emits unescaped content, suitable only for trusted HTML or content sanitized per contract. `MimeMessageHelper.setText(html, true)` **is not an HTML sanitizer**.

Escaping bugs, date formatting bugs, or missing resources belong to **renderer tests**, not transport tests.

## 11. Transport receives only rendered content

Create an abstraction:

~~~java
public interface MailGateway {
    void send(RenderedMail mail);
}
~~~

A Spring Mail implementation:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringMailGateway implements MailGateway {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public SpringMailGateway(
            JavaMailSender mailSender,
            String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    @Override
    public void send(RenderedMail mail) {
        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message, true, "UTF-8"
                    );

            helper.setFrom(fromAddress);
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(
                    mail.plainText(),
                    mail.htmlText()
            );

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Unable to prepare MIME message", ex
            );
        }

        mailSender.send(message);
    }
}
~~~

`MailPreparationException` is an application-defined runtime exception. `JavaMailSender.send` can throw `MailException` such as `MailSendException`. If you want to wrap transport errors into a neutral/domain-independent exception, do so in the gateway or adapter per convention, never letting the selector handle SMTP errors.

### Why is From injected instead of placed in selection?

`From` usually ties to sender identity, account, and operational policy. Template selection decides content, not necessarily SMTP credentials. A multi-account system can have a `MailRoutingGateway` pick transport by `MailPurpose` controlled by the application service.

Never let a template file dictate SMTP usernames or passwords.

## 12. Test transport with Mockito without sending real mail

In transport tests, create an in-memory `MimeMessage` with Jakarta Mail and mock `JavaMailSender`. The goal is verifying the gateway **builds the message and calls the sender** properly without opening network connections.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.Properties;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class SpringMailGatewayTest {

    @Test
    void sendsRenderedContentAsMimeMessage()
            throws Exception {

        JavaMailSender sender =
                mock(JavaMailSender.class);

        when(sender.createMimeMessage())
                .thenAnswer(invocation ->
                        new MimeMessage(
                                Session.getInstance(
                                        new Properties()
                                )
                        )
                );

        SpringMailGateway gateway =
                new SpringMailGateway(
                        sender,
                        "orders@example.org"
                );

        RenderedMail mail = new RenderedMail(
                "buyer@example.org",
                "Order ORD-2048 confirmation",
                "Order ORD-2048 confirmed.",
                "<p>Order ORD-2048 confirmed.</p>"
        );

        gateway.send(mail);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(1)).send(captor.capture());

        MimeMessage actual = captor.getValue();

        assertEquals(
                mail.subject(),
                actual.getSubject()
        );

        InternetAddress to = (InternetAddress)
                actual.getRecipients(
                        Message.RecipientType.TO
                )[0];

        assertEquals(
                "buyer@example.org",
                to.getAddress()
        );

        InternetAddress from =
                (InternetAddress) actual.getFrom()[0];

        assertEquals(
                "orders@example.org",
                from.getAddress()
        );

        assertTrue(actual.isMimeType("multipart/*"));
    }
}
~~~

This test needs no `MailTemplateSelector`, no `OrderRepository`, no SMTP server startup, and does not care why the subject says `ORD-2048`. It verifies only the **transport adapter** contract.

### Why mock JavaMailSender while using a real MimeMessage?

If you mock `MimeMessage` and `MimeMessageHelper` with scattered stubs, tests easily end up verifying method-call choreography without proving headers or MIME contents are actually constructed properly.

Using a real in-memory `MimeMessage` brings clear benefits:

- `MimeMessageHelper` setters actually mutate the MIME object.
- Recipients, headers, and content types can be inspected directly.
- Nothing goes over the network.
- No knowledge of template selection rules is needed.

This is the right boundary for a **gateway unit test**, relying on the local Jakarta Mail library.

## 13. Test plain text and HTML in transport tests

When `MimeMessageHelper` receives both plain and HTML:

~~~java
helper.setText(
        "Order ORD-2048 has been confirmed.",
        "<p>Order <strong>ORD-2048</strong> has been confirmed.</p>"
);
~~~

Spring Mail builds an appropriate MIME structure so clients can choose between plain text and HTML. With `MimeMessageHelper(message, true, "UTF-8")`, the structure may wrap an outer `multipart/mixed` around an inner `multipart/alternative`.

Therefore, never assume:

~~~java
MimeMultipart multipart =
        (MimeMultipart) message.getContent();

// Element 0 is always plain text,
// element 1 is always HTML.
~~~

This assumption breaks if MIME nesting changes or attachments are added. Good tests inspect **parts by MIME type**, not hardcoded positions.

Use a recursive helper in tests:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

private static String findPartText(
        Part part,
        String mimeType) throws Exception {

    if (part.isMimeType(mimeType)) {
        Object content = part.getContent();

        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            String found = findPartText(
                    multipart.getBodyPart(i),
                    mimeType
            );

            if (found != null) {
                return found;
            }
        }
    }

    return null;
}
~~~

Then:

~~~java
MimeMessage message = captor.getValue();

assertEquals(
        "Order ORD-2048 has been confirmed.",
        findPartText(message, "text/plain")
);

assertTrue(
        findPartText(message, "text/html")
                .contains("<strong>ORD-2048</strong>")
);
~~~

This is a test helper for standard `text/plain` and `text/html` cases. If MIME contains embedded `message/rfc822` or special content, a more tailored extractor may be needed.

### Test Unicode

When protecting Vietnamese encoding:

~~~java
assertEquals(
        "Thông báo thanh toán – Đơn hàng số 2048",
        actual.getSubject()
);
~~~

You can verify Unicode bodies and charsets through MIME parts. It is unnecessary to assert the exact raw encoded-word string in headers, because how Jakarta Mail encodes/folds headers can vary while remaining valid. Assert **decoded** values or MIME semantics instead of byte-for-byte coupling to a library version.

## 14. Test transport errors without making the selector responsible

If `JavaMailSender` throws an error:

~~~java
@Test
void propagatesDeliveryFailure() {
    JavaMailSender sender =
            mock(JavaMailSender.class);

    when(sender.createMimeMessage())
            .thenReturn(
                    new MimeMessage(
                            Session.getInstance(
                                    new Properties()
                            )
                    )
            );

    doThrow(new MailSendException("SMTP unavailable"))
            .when(sender)
            .send(any(MimeMessage.class));

    SpringMailGateway gateway =
            new SpringMailGateway(
                    sender,
                    "orders@example.org"
            );

    RenderedMail mail = new RenderedMail(
            "buyer@example.org",
            "Notification",
            "Plain text",
            "<p>HTML</p>"
    );

    assertThrows(
            MailSendException.class,
            () -> gateway.send(mail)
    );
}
~~~

This example assumes the gateway **propagates** the `MailException` thrown by the sender. If the application intentionally translates exceptions into a dedicated `MailDeliveryException`, assertions should check the gateway's contracted exception type. Never catch and swallow all errors and report sending succeeded.

Other cases:

- `mailSender.createMimeMessage()` fails unexpectedly.
- Invalid recipient or From causes MIME preparation to fail.
- Provider rejects AUTH/TLS.
- Transient connection error.
- Partial recipient acceptance.
- SMTP timeout with uncertain outcome.
- Unreadable or oversized attachment.

These failures belong to gateway/transport or retry orchestration, not the locale → template mapping table.

### Never retry SMTP inside the selector

A `select(...)` method should know nothing about `MailSendException` and should never sleep/backoff. Retries belong to mail workers/delivery policies after transport fails. The selector should simply throw something like `TemplateUnavailableException` when no valid template can be resolved.

## 15. Unit test the application handler: verify coordination flow

An application handler may combine selector, renderer, and gateway:

~~~java
@Service
public class OrderConfirmationMailHandler {

    private final MailTemplateSelector selector;
    private final MailTemplateRenderer renderer;
    private final MailGateway gateway;

    public OrderConfirmationMailHandler(
            MailTemplateSelector selector,
            MailTemplateRenderer renderer,
            MailGateway gateway) {
        this.selector = selector;
        this.renderer = renderer;
        this.gateway = gateway;
    }

    public void send(OrderMailViewModel model, Locale locale) {
        TemplateSelection selection = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                locale
        );

        RenderedMail mail =
                renderer.render(selection, model);

        gateway.send(mail);
    }
}
~~~

In production, the handler also handles authorization, recipient policy, and trusted domain data before building the view model. The example is intentionally simplified to show the **select → render → send** flow.

Handler unit tests focus on confirming dependencies are coordinated properly:

~~~java
@Test
void coordinatesSelectionRenderingAndDelivery() {
    MailTemplateSelector selector =
            mock(MailTemplateSelector.class);
    MailTemplateRenderer renderer =
            mock(MailTemplateRenderer.class);
    MailGateway gateway =
            mock(MailGateway.class);

    TemplateSelection selection = new TemplateSelection(
            "mail/order-confirmed",
            Locale.forLanguageTag("vi-VN"),
            1
    );

    OrderMailViewModel model = new OrderMailViewModel(
            "buyer@example.org",
            "Minh",
            "ORD-2048"
    );

    RenderedMail rendered = new RenderedMail(
            model.recipient(),
            "Confirmed ORD-2048",
            "Text content",
            "<p>HTML content</p>"
    );

    when(selector.select(
            MailPurpose.ORDER_CONFIRMED,
            Locale.forLanguageTag("vi-VN")
    )).thenReturn(selection);

    when(renderer.render(selection, model))
            .thenReturn(rendered);

    OrderConfirmationMailHandler handler =
            new OrderConfirmationMailHandler(
                    selector,
                    renderer,
                    gateway
            );

    handler.send(
            model,
            Locale.forLanguageTag("vi-VN")
    );

    verify(renderer).render(selection, model);
    verify(gateway).send(rendered);
}
~~~

If `MailTemplateSelector` is `final` and the project does not configure Mockito to mock final classes, depend on a `TemplateSelector` interface instead of a concrete class. That is also an architectural benefit: abstractions should express the contract the handler needs, not implementation details.

### Test when the selector rejects

~~~java
@Test
void doesNotSendWhenTemplateIsUnavailable() {
    when(selector.select(
            any(),
            any()
    )).thenThrow(
            new TemplateUnavailableException(
                    "Missing template"
            )
    );

    assertThrows(
            TemplateUnavailableException.class,
            () -> handler.send(
                    model,
                    Locale.forLanguageTag("vi-VN")
            )
    );

    verifyNoInteractions(renderer, gateway);
}
~~~

This test proves **fail-fast**: when no template is available, the application calls neither the renderer nor SMTP. It does not need a mock SMTP server to test that logic.

## 16. Avoid over-mocking

An anti-pattern:

~~~java
when(templateEngine.process(anyString(), any()))
        .thenReturn("<p>Hello</p>");

when(mailSender.createMimeMessage())
        .thenReturn(mock(MimeMessage.class));

// Mock helper, Session, MimeMultipart, MailSender,
// controller, repository, locale resolver...
~~~

The test has loads of stubs yet really only asserts "when A returns X, B is called." It can miss real MIME/encoding bugs because every object was mocked away.

A sensible split:

- **Selector tests:** use a real in-memory catalog, no mocked dependencies unless needed.
- **Renderer tests:** use real template resources or a real template engine without sending mail.
- **Gateway tests:** use a real `MimeMessage` and mock `JavaMailSender`.
- **Handler tests:** mock selector/renderer/gateway to verify orchestration.
- **SMTP integration tests:** use a test SMTP server to test protocol when needed.

Mocking at the right boundaries keeps tests both fast and meaningful.

## 17. Fake MailGateway for workflow testing

Not every test needs Mockito. A fake gateway can record sent emails in memory:

~~~java
public final class CapturingMailGateway
        implements MailGateway {

    private final List<RenderedMail> sent =
            new ArrayList<>();

    @Override
    public void send(RenderedMail mail) {
        sent.add(mail);
    }

    public List<RenderedMail> captured() {
        return List.copyOf(sent);
    }
}
~~~

An application integration test (without SMTP) can use this fake to verify:

- Exactly one logical email was requested.
- The recipient was chosen accurately by recipient policy.
- Subject/body hold rendered data.
- No email was sent when business rules rejected.

If tests run across multiple threads/`@Async`, `ArrayList` above is not thread-safe; use a synchronized collection or proper synchronization and avoid asserting before workers finish.

### Fake gateway does not prove MIME is valid

A fake `MailGateway` receives `RenderedMail` without building MIME. It **does not test** encoding, headers, boundaries, transport exceptions, or SMTP sessions. Those belong to gateway unit tests and SMTP integration tests.

Each test double must be used strictly for what it proves.

## 18. Separate template selection from sender configuration

In an application with multiple SMTP accounts:

~~~text
ORDER_CONFIRMED → transactionalMailSender
PASSWORD_RESET  → securityMailSender
NEWSLETTER      → marketingMailSender
~~~

This is **sender routing policy**, distinct from template selection:

~~~text
ORDER_CONFIRMED + vi-VN
    → mail/order-confirmed (vi-VN)
~~~

Do not merge both maps into one hard-to-test tangle.

You can define:

~~~java
public interface MailSenderRouter {
    MailGateway route(MailPurpose purpose);
}
~~~

And:

~~~java
public interface TemplateSelector {
    TemplateSelection select(
            MailPurpose purpose,
            Locale locale);
}
~~~

Then write two unit-test groups:

- `TemplateSelectorTest`: purpose/locale/variant → descriptor.
- `MailSenderRouterTest`: purpose/tenant/environment → authorized account/gateway.

A routing test can confirm `NEWSLETTER` never uses the security sender even if the marketing account fails. That still has nothing to do with HTML rendering.

## 19. Locale fallback is a policy, not an SMTP measurement

When locale `fr-CA` lacks a translation, fallback might follow:

~~~text
fr-CA -> fr -> en-US
~~~

Or product policy may fall back to `vi-VN`. Selector tests must assert the exact order.

Never let the renderer fall back silently when the selector already returned an ostensibly valid locale, because:

- Selector tests pass while the renderer emits a different language.
- Logs cannot tell which template was rendered.
- The system can send emails in the wrong language.
- Sensitive emails such as security notices require strict control.

A clean model has `TemplateSelection` carry the **resolved locale**. The renderer uses that exact locale and throws an error if the resource is missing rather than guessing another locale.

### Language vs language-region locales

`Locale.forLanguageTag("en-US")` and `Locale.forLanguageTag("en-GB")` do not necessarily format dates/currencies identically. Decide whether the catalog uses exact tags, language-only, or multi-level fallback.

Test the selector against those defined rules; test date/number/currency formatting in renderer tests.

## 20. Template versions, variants, and A/B tests

As templates evolve, you may have:

~~~text
mail/order-confirmed / vi-VN / v1
mail/order-confirmed / vi-VN / v2
~~~

The selector decides version/variant based on feature flags, tenant, campaign, or rollout policy.

Contract example:

~~~java
public record TemplateContext(
        MailPurpose purpose,
        Locale locale,
        UUID tenantId,
        String campaignId) {
}
~~~

Avoid mixing uncontrollable random sources into selector tests. When selecting variants by deterministic bucketing:

~~~text
stableRecipientOrEventId -> variant A/B
~~~

inject an explicit strategy/seed and test:

- Same ID gets the same variant on retry.
- Two tenants with different rules never mix templates.
- Disabled flag picks the stable version.
- Unavailable template fails or falls back per policy.
- Same outbox job never emits different content unless intentional.

### Retries must not silently switch templates

A job retried after a timeout can use the same rendered snapshot or the same template version. If the selector re-picks a newer version based on current rollout state, one send intent can produce different content across attempts.

With an outbox, persist the template selection/version or rendered snapshot per policy. Test **selection idempotency** separately from SMTP retries.

## 21. Test high-value negative cases

Testing only "the right template was selected" is insufficient. Critical rejection cases:

| Error | Responsible layer | Expected test |
| --- | --- | --- |
| Purpose absent from catalog | Selector | Throws selection error |
| Unsupported locale with no fallback | Selector | Fails per rule |
| Missing template resource | Renderer | Rendering error, gateway never called |
| Unescaped HTML values | Renderer | Contains no untrusted markup |
| Invalid address during MIME build | Gateway/validation boundary | Appropriate error |
| SMTP host unreachable | Transport | Delivery/retryable error |
| Wrong SMTP username/password | Transport/provider integration | Auth failure classified |
| SMTP quota throttled | Transport/worker | Backoff, no tight-loop retries |
| Recipient unauthorized | Application policy | Never calls selector/gateway once rejected |
| Duplicate event/outbox | Application/outbox | Creates no extra send intent |

When a test fails, its name and class should pinpoint the broken boundary. For instance, `fallsBackToVietnameseWhenFrenchTemplateUnavailable` must never depend on an SMTP sandbox.

## 22. Test Unicode and MIME content at the right layer

Suppose a customer name contains Vietnamese characters:

~~~text
Nguyễn Thị Ánh
~~~

And subject:

~~~text
Hóa đơn tháng 11 – Đơn hàng ORD-2048
~~~

Questions to separate:

- Does the template engine render the name/subject properly? → **Renderer test**.
- Does `MimeMessageHelper` build valid Unicode headers and UTF-8 bodies? → **Gateway test**.
- Does the real SMTP relay accept the message? → **Integration/contract test**.

There is no need to run three identical tests through a real provider. Use one representative Unicode fixture at each boundary and assert that layer's expected outcome.

### Never assert randomly generated MIME boundaries

Multipart boundaries, header folding, `Content-Transfer-Encoding`, or `Message-ID` can vary across libraries/runtimes. In gateway tests, assert MIME semantics:

- Accurate recipients/from/subject.
- `text/plain` part exists.
- `text/html` part exists.
- Charset and Unicode content decode accurately.
- Attachments have valid filenames and content types when the use case includes attachments.

Never compare entire MIME serializations byte-for-byte unless you are explicitly testing a fixed wire-level format; doing so makes tests brittle.

## 23. Test attachments and inline images in transport, not selector

Some templates need an inline logo or a PDF invoice. The selector can pick an `"invoice-ready"` descriptor, yet it should know nothing about physical file paths or how Jakarta Mail attaches files.

The transport gateway may need to call:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes)
);
~~~

Or:

~~~java
helper.addInline(
        "brandLogo",
        logoResource,
        "image/png"
);
~~~

Transport tests should verify:

- Attachments have the right filename, MIME type, and bytes.
- Resources remain readable throughout the `send(...)` lifecycle.
- Inline content IDs match rendered HTML.
- For HTML with inline resources, `helper.setText(...)` is called before adding inline resources per `MimeMessageHelper` convention to avoid reference bugs in mail clients.
- Resource stream errors are classified properly.

Selector tests only verify picking a template that requires or omits attachments if that is part of selection metadata; they never parse PDFs or MIME.

## 24. Test the Spring context's exact responsibility

A selector unit test can instantiate the class with `new`. Yet verifying `@Configuration` creates all beans, the template resolver finds resources, and `@Qualifier` injects the right `JavaMailSender` requires a Spring-context wiring integration test.

Example test groups:

~~~text
MailTemplateSelectorTest
    pure Java, JUnit
MailTemplateRendererTest
    template engine + resource
SpringMailGatewayTest
    JavaMailSender mock + real MimeMessage
OrderConfirmationMailHandlerTest
    mocked collaborator boundaries
MailConfigurationTest
    Spring context + test properties
MailSmtpIntegrationTest
    test SMTP server / provider sandbox
~~~

**There is no need to put `@SpringBootTest` on everything.** Context startup is slow, easily couples to environment variables, and can accidentally connect to providers if test config is not isolated.

### Mail test configuration must be safe

- Never use production usernames/passwords.
- Use mock/fake `JavaMailSender` for unit/component tests.
- For SMTP integration, use a loopback/container test server or a dedicated provider sandbox.
- Disable real sending in local/CI via safe test config.
- Tests asserting outbound emails must use test recipients, never real user data.

Separating test tiers keeps suites fast and free of side effects.

## 25. When is an SMTP integration test needed?

Gateway unit tests with in-memory `MimeMessage` prove construction/calls, yet do not guarantee:

- Host/port configuration is accurate.
- TLS handshake/hostname verification works.
- SMTP AUTH succeeds against the provider.
- The server accepts the sender identity/From.
- Provider quotas/reply codes behave as expected.
- Message size is accepted by the server.
- Network/proxy connectivity works in the deployed environment.

When these guarantees are needed, add integration tests against an SMTP test server or provider sandbox. Use a controlled test SMTP server (such as MailHog, GreenMail, or an equivalent tool) if the project uses one.

Yet **never put template selection logic into SMTP integration tests**. Transport tests can use a fixed `RenderedMail` fixture:

~~~java
RenderedMail testMail = new RenderedMail(
        "test-recipient@example.org",
        "SMTP test",
        "This is the plain-text version.",
        "<p>This is the HTML version.</p>"
);

gateway.send(testMail);
~~~

Integration tests can verify the test server received the message and a few core fields; they do not need to create orders, invoices, or security tokens.

## 26. "Contract tests" between selector, renderer, and gateway

Every layer does not need the same implementation test. What matters is the **data contract**.

Example:

- Selector returns `TemplateSelection` with `templateCode`, `locale`, `version`.
- Renderer accepts that descriptor and a typed view model, returning `RenderedMail`.
- Gateway accepts `RenderedMail` containing `recipient`, `subject`, `plainText`, and `htmlText`.

Contract tests should guarantee:

1. Every descriptor advertised by the selector has a matching resource.
2. The renderer can execute all supported templates.
3. No template references required variables absent from the view-model contract.
4. The gateway needs only rendered data, never a template enum.
5. Missing resources/templates are reported clearly without sending.
6. HTML and plain text stay semantically consistent for the same content.
7. Outbox versions/locales resolve consistently.

A catalog/resource availability check can run at build time:

~~~java
for (TemplateSelection selection : catalog.all()) {
    assertTrue(
            templateRepository.exists(selection),
            "Missing template: " + selection
    );
}
~~~

`catalog.all()` and `templateRepository.exists` are illustrative APIs implemented by the application. This is a **contract/component test**, distinct from pure selector logic tests and SMTP transport tests.

## 27. Organize test data to reduce coupling

Use fixture factories with clear business names:

~~~java
public final class MailTestFixtures {

    private MailTestFixtures() {
    }

    public static OrderMailViewModel
    confirmedOrderVietnamese() {

        return new OrderMailViewModel(
                "buyer@example.org",
                "Lan",
                "ORD-2048"
        );
    }

    public static RenderedMail renderedOrderMail() {
        return new RenderedMail(
                "buyer@example.org",
                "Order ORD-2048 confirmed",
                "Plain text content ORD-2048",
                "<p>HTML content ORD-2048</p>"
        );
    }
}
~~~

Use per layer:

- Selector tests construct purpose/locale inputs directly without needing `RenderedMail`.
- Renderer tests use `TemplateSelection` and `OrderMailViewModel`.
- Gateway tests use `RenderedMail`.
- Handler tests use all three objects while mocking collaborators.

Never build one giant factory containing database entities, HTTP requests, MIME sessions, and SMTP properties just to support a template-selection assertion. Each layer's fixtures should hold only data suited to that layer.

### Do rendered outputs need snapshots?

HTML snapshots help control large layouts, yet use caution:

- Dynamic timestamps and random IDs make snapshots unstable.
- Whitespace or template-engine changes create noisy diffs.
- Passing snapshots do not prove escaping or link authorization.
- Template-selection tests never need HTML snapshots.

Combine semantic assertions for critical data, selective snapshots for intentional layouts, and separate visual/email-client checks.

## 28. Separate tests with events, outboxes, and async workers

An asynchronous sending system typically looks like:

~~~text
Domain event -> Outbox -> Worker
                           |
                           v
                    Template selector
                           |
                           v
                      Renderer
                           |
                           v
                     Mail gateway
~~~

Maintain independent tests:

- **Outbox tests:** one event creates one logical job; retries never duplicate enqueues.
- **Worker orchestration tests:** worker claims job, invokes selector/renderer/gateway, and records status.
- **Selector tests:** picks the right template by purpose/locale/version.
- **Renderer tests:** produces accurate, properly escaped content.
- **Gateway tests:** builds MIME and invokes sender.
- **Retry tests:** classifies transport errors, applies backoff, never loses jobs.

You do not need an entire SMTP workflow to test outbox job deduplication. Conversely, gateway tests do not need to know whether a worker claimed a lease.

### Idempotency does not live inside the selector

Template selection must remain consistent when retrying the same send intent if business policy requires it; yet maintaining `idempotencyKey`, leases, attempt counts, and `SENT` status belongs to the outbox/worker. Never add database state to the selector just to prevent duplicate retry sends.

## 29. Common testing mistakes

### 29.1. Template selector unit tests depending on an SMTP server

**Issue:** locale/purpose tests fail due to network or credentials.

**Fix:** instantiate the selector with an in-memory catalog; assert the descriptor.

### 29.2. Transport tests choosing templates by filename

**Issue:** the gateway takes over business decisions and rendering.

**Fix:** pass complete `RenderedMail` into the gateway.

### 29.3. Mocking everything, including the data under test

**Issue:** mocking `MimeMessage` leaves no real MIME to assert.

**Fix:** use a real Jakarta Mail `MimeMessage` while mocking `JavaMailSender`.

### 29.4. Calling real SMTP in unit tests

**Issue:** slow, flaky, risks unintended emails, depends on secrets.

**Fix:** use a fake sender or a dedicated test server for integration.

### 29.5. Selector falls back and renderer falls back again

**Issue:** impossible to know which locale the final email used.

**Fix:** selector returns the resolved locale; renderer uses it verbatim or fails.

### 29.6. Testing every locale by parsing MIME

**Issue:** slow, redundant coverage, hard to pinpoint failures.

**Fix:** test locale mapping in the selector; test representative localized content in the renderer; test MIME/UTF-8 in the gateway.

### 29.7. Asserting raw MIME byte-for-byte

**Issue:** boundaries and header folding can change validly.

**Fix:** assert decoded subject, recipients, MIME parts, and content types.

### 29.8. Checking only that email was sent while ignoring template errors

**Issue:** when a template is missing, the gateway might still receive blank or broken content.

**Fix:** test negative paths and assert `verifyNoInteractions(gateway)`.

### 29.9. Using client-supplied template names

**Issue:** can bypass business mapping or select unauthorized templates.

**Fix:** derive purpose from an authorized use case; selector reads an internal catalog.

### 29.10. Mixing sender account routing into template selector

**Issue:** changing credentials/SMTP providers breaks template tests.

**Fix:** separate `MailSenderRouter` from `TemplateSelector`.

### 29.11. Using @SpringBootTest for all unit tests

**Issue:** slow, prone to unrelated environment config errors.

**Fix:** plain JUnit for selectors; Spring context only for wiring/integration.

### 29.12. HTML tests checking a substring while ignoring escaping

**Issue:** content renders yet leaves XSS/HTML injection in mail clients.

**Fix:** test the renderer with untrusted inputs and contextual escaping.

### 29.13. Believing SMTP accepted means delivered

**Issue:** test sees `send` throw nothing and reports "customer received email."

**Fix:** distinguish submitted/accepted from delivered; provider feedback needs separate tests.

### 29.14. Async tests asserting immediately after submit

**Issue:** worker may not have finished yet, causing flaky tests.

**Fix:** use futures, latches, or invoke scheduler/worker directly with a deterministic executor instead of arbitrary `Thread.sleep`.

### 29.15. Over-specifying internal calls with Mockito verify

**Issue:** changing a helper call breaks tests even when the output contract is unchanged.

**Fix:** assert meaningful outputs on `TemplateSelection`, `RenderedMail`, and `MimeMessage`; verify call counts only when count genuinely matters.

## 30. Test case assignment table

| Question to answer | Where to test? | Needs SMTP? |
| --- | --- | --- |
| Which template does order confirmed use? | TemplateSelectorTest | No |
| How does a missing locale fall back? | TemplateSelectorTest | No |
| Is version v2 selected properly? | TemplateSelectorTest | No |
| Does subject include order code? | TemplateRendererTest | No |
| Are untrusted HTML names escaped? | TemplateRendererTest | No |
| Does the template resource actually exist? | Renderer/catalog contract test | No |
| Does the application handler pass the right model? | HandlerTest | No |
| Was the sender called once? | MailGatewayTest | No |
| Are To/From/Subject right? | MailGatewayTest | No |
| Are plain text and HTML present in MIME? | MailGatewayTest | No |
| Does a Unicode subject round-trip properly? | MailGatewayTest | No |
| Do TLS/AUTH work with a real relay? | SMTP integration test | Yes, sandbox/test |
| Retry/backoff on SMTP 4xx? | Worker/delivery policy test | No real server needed |
| Does the outbox avoid duplicates? | Outbox repository/worker test | No |
| Did the provider deliver to the inbox? | Delivery feedback/integration | Not proven by SMTP submit alone |

This table shows that **selector tests and transport tests complement rather than replace each other**. The clearer the boundary, the fewer tests drag the entire Spring application into a simple assertion.

## 31. Reasoning exercises

**Question 1.** You need to verify `PASSWORD_RESET + vi-VN` selects `mail/password-reset`. Do you need to mock `JavaMailSender`?

No. Instantiate the selector with a test catalog and assert `TemplateSelection`. SMTP plays no part in this decision.

**Question 2.** You want to verify a Unicode subject is encoded/decoded cleanly in MIME. Should you test in the selector or gateway?

In the gateway. Use a real in-memory `MimeMessage` and check that `getSubject()` returns the exact Unicode string.

**Question 3.** HTML contains raw `<img onerror=...>` from a customer's name. Which component owns this bug?

The rendering/escaping boundary, not the selector or SMTP transport. Renderer tests should catch it.

**Question 4.** Does mocking `MailGateway` and verifying `send` was called prove MIME multipart is valid?

No. A fake/mock gateway builds no MIME; you must test `SpringMailGateway` with a real `MimeMessage`.

**Question 5.** A locale-selection test fails due to bad SMTP credentials. What is wrong with the test design?

It coupled template-selection logic to transport infrastructure. Separate selector unit tests from SMTP integration.

**Question 6.** Locale `ja-JP` has no template and policy falls back to `vi-VN`. Where should the assertion live?

In selector tests, on `TemplateSelection.locale()` and the selected template descriptor.

**Question 7.** A worker retries an outbox job, yet an A/B selector picks a different variant on the second try. What is the risk?

The same send intent could emit different content. Use deterministic variant selection or persist version/snapshot and test retry consistency.

**Question 8.** `JavaMailSender.send` throws `MailSendException`. Should the selector catch and retry?

No. Error handling, retries, and backoff belong to the gateway/worker/delivery policy.

**Question 9.** Do you need `@SpringBootTest` to test pure mapping from a purpose enum to a template code?

No. JUnit 5 with a plain Java class suffices when the selector does not depend on a Spring context.

**Question 10.** A gateway test asserts all raw MIME bytes against a fixed snapshot. Why does it produce false failures?

Jakarta Mail may change boundaries, fold headers, or pick different valid encodings across versions. Assert semantic decoded content.

**Question 11.** A client sends a template name in the HTTP body. Should you trust it to build emails?

No. The application service should resolve the business purpose and the selector should pick from a trusted catalog.

**Question 12.** Does a passing SMTP sandbox test prove every locale is selected properly?

No. It tests only part of transport integration. Template-selection logic needs dedicated unit tests and catalog/resource contract tests.

## 32. Mental model summary

~~~mermaid
flowchart TD
    A["Business command"] --> B["Recipient + authorization policy"]
    B --> C["TemplateSelector"]
    C --> D["TemplateSelection: code, locale, version"]
    D --> E["TemplateRenderer"]
    E --> F["RenderedMail: To, subject, plain, HTML"]
    F --> G["MailGateway"]
    G --> H["MimeMessageHelper"]
    H --> I["JavaMailSender"]
    I --> J["SMTP relay"]

    T1["Selector unit tests"] -. "Selects right template" .-> C
    T2["Renderer tests"] -. "Content / escaping / locale" .-> E
    T3["Gateway unit tests"] -. "MIME / headers / exceptions" .-> G
    T4["SMTP integration tests"] -. "AUTH / TLS / provider" .-> J
~~~

Key principles:

1. **The template selector chooses the template** based on purpose, locale, version/variant, and business policy.
2. **The renderer turns template and view model into content**: subject, plain text, HTML, and contextual encoding.
3. **Transport accepts rendered content and sends it**: To/From/Subject/MIME/attachments/`JavaMailSender`.
4. **Selector unit tests need no SMTP, Spring context, or Mockito** when mapping is pure logic.
5. **Renderer tests need no email sending**, yet must verify resources, variables, and escaping.
6. **Gateway tests use a real `MimeMessage` and mock `JavaMailSender`**, asserting fields and MIME semantics.
7. **Selection errors differ from render errors and SMTP errors**; separate exception hierarchies and retries accordingly.
8. **Never let clients pick arbitrary templates or sender accounts**; the application layer controls business purpose.
9. **Never assert unstable MIME details** such as random boundaries when you only need decoded subject/content.
10. **Use targeted integration tests** to verify Spring wiring and SMTP providers instead of turning every unit test into an end-to-end test.
11. **With outbox/async, keep separate tests** for idempotency, worker orchestration, selection, rendering, and transport.
12. **SMTP accepted is not delivered**; delivery feedback and deliverability belong to separate test scopes.

Separating template selection logic tests from transport tests aligns your tests directly with your architecture: **the selector answers "which template," the renderer answers "what content," and the gateway answers "how to package and send."** In Spring Framework Mail, this boundary lets you evolve languages, template designs, SMTP providers, or MIME settings without breaking unrelated tests—and immediately points to the exact layer to fix when a real bug appears.
