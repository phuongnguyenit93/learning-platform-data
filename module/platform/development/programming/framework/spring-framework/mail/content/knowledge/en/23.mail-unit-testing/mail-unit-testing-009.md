# Testing Template Rendering with Boundary Data

In a **Spring Framework Mail** application, emails are often built from an HTML or plain-text template combined with dynamic data such as recipient name, order number, item list, monetary amount, timestamps, and action links. A template may render cleanly with happy-path sample data yet fail when a name contains quotes, a list is empty, a string is very long, an amount is zero, a required field is missing, or the recipient uses a different locale.

**Testing template rendering with boundary data** (*boundary-value testing*) means intentionally feeding values near valid, invalid, and tricky edges into the rendering step, then verifying that the generated email has **accurate content, valid structure, safety, and clear error behavior**. The main subject under test is the layer transforming business data into subject, HTML, and plain-text body; no real emails need to be sent over SMTP.

A strong test does not merely ask "does the template render without throwing an exception?" It also checks whether data is lost, altered in meaning, injected unsafely into HTML, breaks URLs, formats with the wrong locale, or makes the subject/headers invalid. Moreover, emails render across diverse mail clients; unit tests verify rendered output and MIME structure, whereas client layout testing belongs to a separate layer.

This lesson uses **Thymeleaf**, **JUnit 5**, **AssertJ**, and several `MimeMessageHelper` examples for illustration. Similar principles apply to FreeMarker, Mustache, and other template engines, though escaping syntax and missing-value behavior must be tested for the specific engine in use.

## 1. Define the exact boundary of unit tests

Overall flow:

```text
Business event / notification command
            |
            v
     Validate input model
            |
            v
  Normalize / format data
     (locale, time zone)
            |
            v
  Subject template renderer
            |
            v
  HTML/plain-text renderer
            |
            v
     RenderedMail object
            |
            v
  MimeMessageHelper builder
            |
            v
  JavaMailSender.send(...)
            |
            v
       SMTP transport
```

For template unit tests, focus from the **input model to `RenderedMail`**:

- Are required fields valid?
- Are optional fields hidden/displayed according to contract?
- Does HTML escape untrusted values?
- Do links use approved schemes, hosts, and URL formats?
- Are subject and body consistent on order number, status, and locale?
- Does rendering implicitly depend on system time zone, default locale, or nondeterministic ordering?
- Does the template surface clear errors on missing keys or missing fragments?

**No SMTP connection is needed to test these requirements.** If a test must actually send an email just to check rendered content, rendering and transport are probably too tightly coupled.

### Related test types

| Test type | Must verify | Should not treat as proof of |
|---|---|---|
| Renderer unit test | Turns model into accurate, safe subject, HTML, and plain text | Does not prove SMTP accepts the email. |
| Template resource component test | Engine locates templates/fragments and resolves message bundles | Does not prove identical rendering across all clients. |
| Network-free MIME integration test | Headers, charset, `multipart/alternative`, attachments/CIDs | Does not prove inbox delivery. |
| SMTP integration test | Sender hands message to an SMTP test server | Does not prove real-world provider delivery. |
| Rendering/client preview test | Layout on Gmail, Outlook, mobile, dark mode... | Does not replace validation/XSS checks on source data. |

Most examples below belong to the first two rows. MIME checks appear near the end to ensure rendered output integrates cleanly with Spring Mail.

## 2. Define the template's data contract

Do not let templates read directly from a domain entity carrying dozens of properties and lazy-loaded associations. Use a dedicated **email view model** containing only the data the template needs.

Order confirmation email example:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderMailModel(
        String orderNumber,
        String customerName,
        List<OrderLine> lines,
        BigDecimal total,
        String currencyCode,
        Instant createdAt,
        String detailUrl,
        String optionalNote
) {
}

public record OrderLine(
        String name,
        int quantity,
        BigDecimal price
) {
}
```

The contract should document every field:

| Field | Required? | Boundary cases to test |
|---|---|---|
| `orderNumber` | Yes | `null`, empty, whitespace, Unicode, too long, CR/LF. |
| `customerName` | Per business rules | Empty, quotes, `<script>`, emojis, long strings, RTL. |
| `lines` | Yes | `null`, empty list, single item, multiple items, `null` element. |
| `total` | Yes | 0, negative, long decimals, huge values, rounding. |
| `currencyCode` | Yes | Valid code, invalid code, business mismatch. |
| `createdAt` | Yes | Near midnight, DST, leap day, `null`. |
| `detailUrl` | Yes if CTA button exists | Valid HTTPS, malicious scheme, non-allowlisted host, special query params. |
| `optionalNote` | No | `null`, empty string, whitespace, HTML chars, long string. |

A critical factor is **defining expected behavior before writing tests**. For example, when `customerName` is blank, the application may fall back to "Valued Customer" or reject rendering; either can be valid, provided it is consistent. Without a contract, tests merely mirror accidental template-engine behavior.

### Required and optional must behave differently

Missing required fields should produce a clear error **before calling SMTP**. Optional fields can omit the corresponding HTML block or use an approved fallback.

Example:

```text
orderNumber = null
    -> Reject: INVALID_ORDER_NUMBER

optionalNote = null
    -> Render without optional-note block

customerName = ""
    -> Either reject or use approved generic greeting
       (choose one policy)
```

Never let templates silently print the literal string `null`, `{0}`, or leave a critical order number blank.

## 3. Create reusable fixtures for boundary data

A test fixture should provide a minimal valid baseline and allow each test case to override **one factor**.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class OrderMailFixtures {

    private OrderMailFixtures() {}

    public static OrderMailModel validOrder() {
        return new OrderMailModel(
                "ORD-2026-001",
                "Nguyễn An",
                List.of(
                        new OrderLine(
                                "Sách Java",
                                1,
                                new BigDecimal("250000")
                        )
                ),
                new BigDecimal("250000"),
                "VND",
                Instant.parse("2026-11-12T02:15:00Z"),
                "https://shop.example.org/orders/ORD-2026-001",
                null
        );
    }
}
```

Avoid random data or `Instant.now()` in tests. Deterministic data makes failing tests reproducible down to the exact input.

### With records, copy to replace one field

Use a test-data builder or construct a new record from the baseline:

```java
OrderMailModel baseline = OrderMailFixtures.validOrder();

OrderMailModel withBlankName = new OrderMailModel(
        baseline.orderNumber(),
        " ",
        baseline.lines(),
        baseline.total(),
        baseline.currencyCode(),
        baseline.createdAt(),
        baseline.detailUrl(),
        baseline.optionalNote()
);
```

For models with many fields, builders with `withCustomerName(...)` helpers cut boilerplate and prevent swapping positional arguments. Do not use `Map.of(...)` when testing `null`, because Java's `Map.of` rejects `null` keys and values.

## 4. Thymeleaf template as the test target

Example template located at:

```text
src/main/resources/
  mail/
    order-confirmed.html
```

Contents:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body>
  <p>
    Xin chào
    <strong data-test="customer-name"
            th:text="${customerName}">Quý khách</strong>
  </p>

  <p>
    Đơn hàng
    <span data-test="order-number"
          th:text="${orderNumber}">ORD-001</span>
    đã được xác nhận.
  </p>

  <ul data-test="order-lines">
    <li class="order-line" th:each="line : ${lines}">
      <span class="line-name" th:text="${line.name}">Sản phẩm</span>
      <span class="line-quantity"
            th:text="${line.quantity}">1</span>
    </li>
  </ul>

  <p>
    Tổng cộng:
    <strong data-test="total"
            th:text="${formattedTotal}">0 đ</strong>
  </p>

  <p data-test="optional-note"
     th:if="${optionalNote != null and !#strings.isEmpty(optionalNote)}"
     th:text="${optionalNote}"></p>

  <a data-test="detail-link"
     th:href="${detailUrl}">
    Xem đơn hàng
  </a>
</body>
</html>
```

In Thymeleaf, `th:text` replaces the element body with **HTML-escaped text**. It fits untrusted data such as buyer names or product names. `th:utext` inserts unescaped HTML into output and should be used only with trusted or contextually sanitized content.

`data-test` attributes let tests select elements with stable selectors instead of coupling to styling CSS classes or DOM positions.

### Watch out for the optionalNote condition

The illustrative condition hides the note when `null` or empty. If business rules treat whitespace-only strings as blank, **trim/normalize during model preparation** or enforce and test an explicit template rule. Checking `isEmpty` alone is not equivalent to checking `isBlank`.

## 5. Initialize TemplateEngine in unit tests

Thymeleaf can be configured directly without starting the entire Spring Boot context.

```java
import org.junit.jupiter.api.BeforeEach;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

import java.util.Locale;

class OrderMailTemplateTest {

    private TemplateEngine engine;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();

        resolver.setPrefix("mail/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        engine = new TemplateEngine();
        engine.setTemplateResolver(resolver);
    }

    private String render(
            OrderMailModel order,
            Locale locale,
            String formattedTotal
    ) {
        Context context = new Context(locale);

        context.setVariable(
                "orderNumber", order.orderNumber()
        );
        context.setVariable(
                "customerName", order.customerName()
        );
        context.setVariable("lines", order.lines());
        context.setVariable(
                "formattedTotal", formattedTotal
        );
        context.setVariable(
                "optionalNote", order.optionalNote()
        );
        context.setVariable(
                "detailUrl", order.detailUrl()
        );

        return engine.process("order-confirmed", context);
    }
}
```

This snippet shows a fixture loading resources from the classpath. In real tests, test methods live inside the same class or use matching fixtures/helpers.

**Why disable caching in tests?** It prevents fixtures from serving stale template content if resources change during tests and avoids cache-dependent behavior. In production, enable caching with an appropriate versioning strategy.

If real templates use Spring bean expressions, message bundles, or `SpringTemplateEngine`, tests should configure the matching engine and dependencies or run a Spring-context component test. Never swap the production engine for a differently configured engine and treat test results as fully representative.

## 6. Test required fields with null, empty, and whitespace

The first boundary group includes:

```text
null
""
" "
"\t"
"\n"
"   \t   "
```

These values are not all identical. `null` represents absent data; an empty string exists yet contains zero characters; a whitespace-only string may render as blank space even though it is technically non-empty.

An illustrative validator:

```java
public final class MailModelValidator {

    private MailModelValidator() {}

    public static String requiredSingleLine(
            String value,
            String fieldName
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " is required"
            );
        }

        for (int i = 0; i < value.length();) {
            int codePoint = value.codePointAt(i);

            if (Character.isISOControl(codePoint)) {
                throw new IllegalArgumentException(
                        fieldName + " contains a control character"
                );
            }

            i += Character.charCount(codePoint);
        }

        return value;
    }
}
```

Parameterized test:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", " \t ", "\n"})
void rejectsMissingOrderNumber(String value) {
    assertThatThrownBy(() ->
            MailModelValidator.requiredSingleLine(
                    value, "orderNumber"
            )
    ).isInstanceOf(IllegalArgumentException.class);
}
```

When using `@ValueSource`, import AssertJ assertions and configure the `junit-jupiter-params` dependency. For full models, use `@MethodSource` to supply complete inputs.

### Where to fail fast?

Validation should sit at the boundary building `MailRenderModel` or the renderer service, before invoking the template. A template engine is not the right place to decide whether a `null` order number should be sent to a customer.

In renderer tests, confirm **no SMTP call occurs** when the model is invalid. If the renderer is decoupled from the sender, this holds by design; if an orchestrator service wraps both, use a mock `JavaMailSender` to verify `send` is never called when validation fails.

## 7. Test optional data: absent, blank, and populated

A note field may be:

| Input | Expected behavior |
|---|---|
| `null` | Note block does not appear. |
| `""` | Note block does not appear. |
| `"   "` | Does not appear if policy trims/normalizes whitespace. |
| `"Giao sau 18:00"` | Content displays once. |
| `"<b>Quan trọng</b>"` | Displays as literal text, never parsed as dynamic HTML. |

Inspecting DOM structure with **Jsoup** decouples tests from whitespace and HTML formatting:

```java
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;

@Test
void hidesOptionalNoteWhenNull() {
    OrderMailModel order = OrderMailFixtures.validOrder();

    String html = render(
            order,
            Locale.forLanguageTag("vi-VN"),
            "250.000 ₫"
    );

    Document document = Jsoup.parse(html);

    assertThat(
            document.select("[data-test=optional-note]")
    ).isEmpty();
}
```

If the product defines a specific fallback, assert that fallback rather than merely checking the element exists.

### Do not leave orphan labels

A classic real-world bug is hiding the value while leaving the label behind:

```text
Note:
```

Therefore, wrap both label and value inside the same conditional block, and test that **the entire block disappears** when the note is absent.

## 8. Test Unicode characters and Vietnamese diacritics

Email templates may be read by users across many languages. Inputs should include:

- Accented Vietnamese: `Nguyễn Thị Ánh`.
- Precomposed characters and Unicode combining marks.
- Emojis outside the Basic Multilingual Plane: `🎉`.
- CJK: `注文確定`.
- Arabic/Hebrew or right-to-left (RTL) text.
- Special characters: `&`, `"`, `'`, `<`, `>`.

Test example:

```java
@Test
void preservesUnicodeInRenderedText() {
    String name = "Nguyễn Ánh 🎉 日本語";
    OrderMailModel order = withCustomerName(
            OrderMailFixtures.validOrder(),
            name
    );

    String html = render(
            order,
            Locale.forLanguageTag("vi-VN"),
            "250.000 ₫"
    );

    Document document = Jsoup.parse(html);

    assertThat(
            document.selectFirst(
                    "[data-test=customer-name]"
            ).text()
    ).isEqualTo(name);
}
```

`withCustomerName(...)` is a test helper returning a copy of the record with one field changed. This is a conceptual snippet; define that helper/builder when adapting to a project.

### Distinguish characters from bytes

In Java, `String.length()` counts UTF-16 code units, not necessarily visible characters. Emojis or supplementary characters can occupy multiple code units.

When capping visible data lengths, consider:

- Code point count for character-limit policies.
- Grapheme clusters when avoiding splitting combining marks or emoji sequences.
- UTF-8 byte length for storage/protocol limits.
- Actual rendered width in email clients, which cannot be inferred from string length alone.

Never call `substring(0, 50)` blindly where it risks slicing a surrogate pair or combining emoji sequence.

## 9. Test HTML escaping with untrusted data

A common failure-inducing input is a user or product name containing HTML-like text:

```text
<script>alert('x')</script>
<img src=x onerror=alert(1)>
A & B < C
"quoted" & 'apostrophe'
```

When the template uses `th:text`, these values must appear as literal text and never become executable markup.

Example:

```java
@Test
void escapesUntrustedCustomerName() {
    String injected =
            "<img src=x onerror=alert(1)>";

    OrderMailModel order = withCustomerName(
            OrderMailFixtures.validOrder(),
            injected
    );

    String html = render(
            order,
            Locale.ENGLISH,
            "VND 250,000"
    );

    Document document = Jsoup.parse(html);

    assertThat(
            document.selectFirst(
                    "[data-test=customer-name]"
            ).text()
    ).isEqualTo(injected);

    assertThat(
            document.select(
                    "[data-test=customer-name] img"
            )
    ).isEmpty();

    assertThat(html).contains("&lt;img");
}
```

This test verifies both that **the text value survives HTML parsing intact** and that **no `img` element was created inside the customer field**. Using only `assertThat(html).contains(injected)` could accidentally accept unescaped output.

### th:text and th:utext

In Thymeleaf:

- `th:text`: escapes content for text context.
- `th:utext`: renders unescaped content, easily creating HTML injection if input is untrusted.

Never use `th:utext` merely to preserve line breaks or user formatting. If business requirements truly call for rich text, define an allowlist-based sanitizer policy and test it as a separate component.

**HTML escaping does not replace URL validation, filename validation, or subject/header validation.** Each output context has its own rules.

## 10. Test CTA paths and links in emails

A template may use:

```html
<a th:href="${detailUrl}">Xem đơn hàng</a>
```

`detailUrl` is navigation-sensitive data. Cases to test:

| Input | Expectation |
|---|---|
| `https://shop.example.org/orders/123` | Accept. |
| `https://shop.example.org/orders/123?lang=vi&source=mail` | Accept if constructed via URL builder with valid host. |
| `javascript:alert(1)` | Reject. |
| `data:text/html,...` | Reject. |
| `file:///etc/passwd` | Reject. |
| `http://shop.example.org/...` | Reject if CTA requires HTTPS. |
| `https://evil.example.net/phishing` | Reject if outside allowlist. |
| `https://shop.example.org.evil.net/...` | Reject; never check hosts by string prefix. |
| `""` or `null` | Error or hide CTA per contract. |

### Illustrative URL validator

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Set;

public final class MailLinkValidator {

    private static final Set<String> ALLOWED_HOSTS =
            Set.of("shop.example.org");

    public static URI requireApprovedHttpsUrl(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing URL");
        }

        final URI uri;

        try {
            uri = new URI(value);
        } catch (URISyntaxException exception) {
            throw new IllegalArgumentException(
                    "Malformed URL", exception
            );
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getUserInfo() != null
                || uri.getHost() == null
                || !ALLOWED_HOSTS.contains(
                        uri.getHost().toLowerCase(
                                java.util.Locale.ROOT
                        )
                )) {
            throw new IllegalArgumentException(
                    "URL is not approved"
            );
        }

        return uri;
    }
}
```

This is an **illustrative validator for email links**, not a comprehensive SSRF filter. If the application also fetches URLs server-side, validate redirects, DNS resolution, destination IPs, and egress networking separately.

In production, it is safer to **construct URLs from a trusted configured origin and encoded business IDs**, rather than accepting full URLs from clients.

### Test the link after rendering

```java
@Test
void rendersApprovedDetailLink() {
    OrderMailModel order = OrderMailFixtures.validOrder();

    String html = render(
            order,
            Locale.ENGLISH,
            "VND 250,000"
    );

    String href = Jsoup.parse(html)
            .selectFirst("[data-test=detail-link]")
            .attr("href");

    assertThat(href).isEqualTo(order.detailUrl());
}
```

For full safety, ensure the validator runs **before** the renderer receives `detailUrl`, or build the URL inside the renderer from trusted data.

## 11. Empty lists, single-item lists, and very large lists

Order emails can carry varying numbers of line items:

- `null`: data was not supplied or mapping failed.
- `List.of()`: empty list.
- One line: simplest case.
- Multiple lines: checks iteration and order.
- Very long list: checks business limits and email size.
- A `null` element: needs an explicit contract rather than silently skipping.

One possible rule: `lines` must be non-null, though it may be empty for an "order with no items yet" email; for a purchase confirmation email, an empty list could be a business error. Pick the right policy and test against it.

### Example testing single- and multi-item lists

```java
@Test
void rendersEveryLineOnceInOrder() {
    OrderMailModel order = withLines(
            OrderMailFixtures.validOrder(),
            List.of(
                    new OrderLine(
                            "Bút bi", 1, new BigDecimal("12000")
                    ),
                    new OrderLine(
                            "Sổ tay", 2, new BigDecimal("50000")
                    )
            )
    );

    String html = render(
            order,
            Locale.forLanguageTag("vi-VN"),
            "112.000 ₫"
    );

    var elements = Jsoup.parse(html)
            .select(".order-line .line-name");

    assertThat(elements).hasSize(2);
    assertThat(elements.get(0).text()).isEqualTo("Bút bi");
    assertThat(elements.get(1).text()).isEqualTo("Sổ tay");
}
```

`withLines(...)` is a test helper copying the record with new `lines`.

### When the list is very long

There is no need to print tens of thousands of lines to "prove" a template works. Unit tests should focus on policy:

- Is there an item-count cap?
- When exceeded, does it reject, summarize, or link to a details page?
- Does the total remain accurate?
- Is there an "and N more items" line if design permits?
- Is HTML size bounded?

Never silently truncate a list without an explicit rule, as an invoice email could omit critical items. Summarization must follow business requirements.

## 12. Long strings and content size limits

Length boundary data is often overlooked:

```text
customerName = "A" repeated 500 times
productName  = one unbroken 2000-character string
note         = 50,000 characters
subject      = a long string with emoji and combining marks
```

Risks:

- Subject gets truncated in the UI.
- HTML layout overflows horizontally.
- Email body becomes too large, rejected by providers or clipped by mail clients.
- Tests/snapshots bloat and become unreadable.
- Memory spikes when rendering many emails concurrently.
- Long URLs or product names without spaces fail to wrap.

A policy can define limits by **field** and by **rendered output**. Example:

```java
public static void requireAtMostCodePoints(
        String value,
        int maximum
) {
    int count = value.codePointCount(0, value.length());

    if (count > maximum) {
        throw new IllegalArgumentException(
                "Text length exceeds approved limit"
        );
    }
}
```

In this example, `maximum` is a policy parameter; there is no single universal limit across all Spring Mail templates. Always check `value != null` at the required or optional boundary before calling this method.

### If truncation is desired

Truncate during model preparation with clear rules: preserve critical identifiers, bound by code points/graphemes sensibly, and append an ellipsis if permitted. Never let templates silently truncate financial figures or important terms.

**Unit tests on long content do not replace visual tests**: HTML may be valid in the DOM yet still break layout in certain email clients. For products supporting multiple clients, add screenshot rendering and display tests.

## 13. Monetary amounts: zero, negative, huge values, and precision

Monetary amounts are high-impact boundary data. Use `BigDecimal` instead of `double` arithmetic for money.

Cases:

| Input | What to verify |
|---|---|
| `BigDecimal.ZERO` | Format 0 per currency, never disappear due to truthy/falsy checks. |
| `-1.00` | Rejected if business rules forbid negative, or displayed cleanly for refunds. |
| `0.01` | Not rounded to 0 against policy. |
| `999999999999.99` | No overflow, no lost digits. |
| `1.005` | Rounded per specification; never assume HALF_UP for every currency. |
| `null` | Raises error if `total` is required. |
| Different currency | Matching symbol, decimal digits, and placement. |

Formatting example in the preparation layer:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public static String formatMoney(
        BigDecimal value,
        String currencyCode,
        Locale locale
) {
    if (value == null) {
        throw new IllegalArgumentException("Missing amount");
    }

    Currency currency = Currency.getInstance(currencyCode);

    NumberFormat formatter = NumberFormat.getCurrencyInstance(
            locale
    );
    formatter.setCurrency(currency);

    return formatter.format(value);
}
```

This example shows separating formatting from the template. In production, specify decimal places and rounding according to **currency and business policy**, and never treat display formatting as a substitute for accounting arithmetic.

### Do not assert one arbitrary separator across all locales

Across different locales, the same amount can render as:

```text
250.000 ₫
VND 250,000
¥250,000
```

The actual string depends on locale, currency, JDK/CLDR version, and configuration. Tests should pin the environment or assert the agreed semantic contract. If the product requires pixel-exact formatting, use an explicitly configured formatter and versioned snapshots rather than silently relying on the CI runner's default locale.

## 14. Dates and times: time zones, DST, and boundary instants

Appointment reminders or transaction confirmations usually include timestamps. Bugs unseen with normal sample data surface at boundaries:

- An `Instant` near midnight UTC that falls on the next calendar day in Vietnam.
- Daylight Saving Time (DST) transitions in zones that observe them.
- Leap day Feb 29.
- Month-end and year-end rollovers.
- Nonexistent or repeated local times during DST shifts.
- `createdAt=null` in a template required to show a date.

**Locale and time zone are two separate things.** A customer choosing English does not mean they live in London; a transaction in USD does not prove the time zone is US Eastern.

Example:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public static String formatOrderTime(
        Instant instant,
        Locale locale,
        ZoneId zone
) {
    return DateTimeFormatter
            .ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(locale)
            .withZone(zone)
            .format(instant);
}
```

Tests should use a fixed `Instant` and explicit `ZoneId`:

```java
@Test
void formatsNearMidnightInRecipientTimeZone() {
    Instant instant =
            Instant.parse("2026-11-12T23:45:00Z");

    String result = formatOrderTime(
            instant,
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh")
    );

    // The UTC timestamp falls on 13/11 in Vietnam.
    assertThat(
            instant.atZone(
                    ZoneId.of("Asia/Ho_Chi_Minh")
            ).getDayOfMonth()
    ).isEqualTo(13);

    assertThat(result).isNotBlank();
}
```

This test verifies the zone-adjusted date boundary and that formatted output is non-blank. If exact character-by-character text is required, pin an explicit formatter pattern/locale and assert the full output.

### Avoid the system clock in renderers

Never render "Today's date" by calling `LocalDate.now()` in multiple places inside templates. A unit test running at 23:59 can differ from 00:01.

If current time is needed, pass a `Clock` or business timestamp into the renderer; use `Clock.fixed(...)` in tests:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneOffset.UTC
);
```

Keep date/time math inside the model-preparation layer while templates simply display pre-formatted values.

## 15. Locales, fallbacks, and message bundles

An application can use `MessageSource` to render localized subjects and email phrases.

Example:

```properties
# mail/subjects_vi.properties
mail.subject.order-confirmed=Xác nhận đơn hàng {0}
```

```properties
# mail/subjects_en.properties
mail.subject.order-confirmed=Order {0} confirmed
```

Test setup:

```java
import org.springframework.context.support
        .ResourceBundleMessageSource;

ResourceBundleMessageSource messages =
        new ResourceBundleMessageSource();

messages.setBasename("mail/subjects");
messages.setDefaultEncoding("UTF-8");
messages.setFallbackToSystemLocale(false);

String subject = messages.getMessage(
        "mail.subject.order-confirmed",
        new Object[] {"ORD-2026-001"},
        Locale.forLanguageTag("vi-VN")
);
```

Test cases:

| Case | Expectation |
|---|---|
| Supported locale with key present | Uses matching translation and placeholder. |
| Regional locale missing, language locale present | Falls back per configured rules. |
| Unsupported locale | Uses approved default locale or fails with error. |
| Missing message key | Never sends raw key as subject. |
| Missing/extra placeholder | Reports contract error or forbids missing critical data. |
| Single quotes in `MessageFormat` | Verify proper escaping/quoting syntax. |
| Subject with emoji/CJK | Preserves Unicode after rendering and MIME header encoding. |

### Do not assume fallback already works

`ResourceBundleMessageSource` follows bundle lookup rules, yet falling back to a specific product locale must be configured and verified properly. Tests should simulate missing locales and missing keys to check actual behavior rather than only testing the developer machine's default locale.

For legal notices or market-sensitive emails, **fallback to another translation may be forbidden**. In that case, a missing key must fail rendering to avoid sending an email in the wrong language.

### Quotes in MessageFormat

`java.text.MessageFormat` treats single quotes specially. For example, English text containing `don't` or French text with apostrophes can be parsed differently when templates format parameters.

Tests should cover:

- Apostrophes inside sentences.
- Placeholder `{0}` and multiple arguments.
- Literal curly braces.
- Different content across locales.

Do not check only "no exception thrown"; assert the final subject has the right punctuation and interpolated parameters.

## 16. Subject is an email header, not an HTML body

Subject templates have their own boundary rules. HTML escaping does not solve newline or header injection.

Example bad input:

```text
ORD-001\r\nBcc: attacker@example.net
```

If an order number is concatenated straight into the subject without validation, control characters can create invalid headers or injection risks depending on how the message is built.

Validators should reject CR, LF, and control characters in header-bound data. Unit test:

```java
@Test
void rejectsHeaderControlCharacters() {
    String input =
            "ORD-001\r\nBcc: attacker@example.net";

    assertThatThrownBy(() ->
            MailModelValidator.requiredSingleLine(
                    input, "orderNumber"
            )
    ).isInstanceOf(IllegalArgumentException.class);
}
```

If there is a subject length limit, test:

- `maximum - 1` code points.
- `maximum` code points.
- `maximum + 1` code points.
- Strings with many emojis/surrogate pairs.
- Strings with combining marks.

**Never manually convert Subject into a raw MIME header.** Use `MimeMessageHelper.setSubject(...)` or Jakarta Mail `MimeMessage.setSubject(..., "UTF-8")` so the library handles encoding/folding. Always validate input values per application policy.

## 17. Test output when numeric quantities equal zero

A subtle bug occurs when templates hide zero values because conditions are written as if 0 meant "no data." For example:

- Item quantity = 0.
- Total amount = 0.
- Discount = 0%.
- Days remaining = 0.
- Balance or fee = 0.

Distinguish:

```text
value == null  -> missing data
value == 0     -> data present with value zero
```

Discount example:

```html
<p th:if="${discount != null}">
  Discount:
  <span th:text="${discount}">0</span>
</p>
```

Tests should verify the element renders when `discount=0` if the contract requires it, and hides only when `null`.

### Boolean values

Similarly:

```text
isGift = false   -> valid value
isGift = null    -> missing state
```

If a template branches on a boolean, test true, false, and null per policy. Never treat null and false identically when "unknown" must be distinguished from "no."

## 18. Ensure consistency across subject, HTML, and plain text

Transactional emails typically carry multiple representations of the same content:

- Subject: "Xác nhận đơn hàng ORD-001".
- Plain text: content for clients without HTML support.
- HTML: version with layout, links, and images.

If the three versions use different data or format at different timestamps, recipients may see order A in the subject yet order B in the body.

A result model:

```java
public record RenderedMail(
        String subject,
        String plainText,
        String html
) {
}
```

A renderer service should take **the same model snapshot and locale** and return `RenderedMail`.

### Test semantic consistency

Example:

```java
@Test
void keepsOrderNumberConsistentAcrossAllParts() {
    RenderedMail result = renderer.render(
            OrderMailFixtures.validOrder(),
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh")
    );

    String expected = "ORD-2026-001";

    assertThat(result.subject()).contains(expected);
    assertThat(result.plainText()).contains(expected);

    assertThat(
            Jsoup.parse(result.html())
                    .selectFirst("[data-test=order-number]")
                    .text()
    ).isEqualTo(expected);
}
```

`renderer` illustrates an application component returning all three parts. Similar tests should assert totals, deadlines, and key facts match semantically even when HTML and plain text present them differently.

### Plain text should not be naively tag-stripped HTML

Simply stripping tags can break URLs, table layouts, line breaks, and separators. Use a dedicated plain-text template or a well-tested converter.

Plain-text edge cases:

- Multi-line paragraphs, blank lines, and newlines.
- Long URLs.
- Product lists.
- Unicode and emojis.
- `<`, `>`, and `&` preserved as plain text.
- No unrendered placeholders like `${name}`.
- No literal HTML entities like `&amp;` when recipients read plain text.

## 19. Test MIME after rendering yet before SMTP sending

Once you have `RenderedMail`, build a MIME message right in the test and inspect parts without opening the network.

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.util.ArrayList;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

@Test
void createsPlainTextAndHtmlMimeParts() throws Exception {
    RenderedMail content = renderer.render(
            OrderMailFixtures.validOrder(),
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh")
    );

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

    helper.setFrom("orders@example.org");
    helper.setTo("customer@example.net");
    helper.setSubject(content.subject());
    helper.setText(content.plainText(), content.html());

    message.saveChanges();

    assertThat(message.getSubject())
            .isEqualTo(content.subject());

    List<String> contentTypes = new ArrayList<>();
    collectLeafTypes(message, contentTypes);

    assertThat(contentTypes)
            .anyMatch(type -> type.startsWith("text/plain"));
    assertThat(contentTypes)
            .anyMatch(type -> type.startsWith("text/html"));
}

static void collectLeafTypes(
        Part part,
        List<String> types
) throws Exception {
    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int index = 0;
                index < multipart.getCount();
                index++) {
            collectLeafTypes(
                    multipart.getBodyPart(index),
                    types
            );
        }
    } else {
        types.add(part.getContentType().toLowerCase(
                java.util.Locale.ROOT
        ));
    }
}
```

This code checks that both `text/plain` and `text/html` exist even when MIME nests multiple `multipart` levels. Never write tests assuming "the second part is always HTML," because `MimeMessageHelper` supports multiple multipart modes and trees vary with attachments/inline resources.

`message.saveChanges()` performs in-memory MIME preparation; **`mailSender.send(message)` is never called**, so the test needs no SMTP host or credentials.

## 20. Content with attachments and inline images

Templates can reference images via CID:

```html
<img src="cid:brand-logo" alt="Logo">
```

When rendering with boundary data, check:

- CID in HTML matches the Content-ID added by the builder.
- Inline images do not go missing when optional data changes.
- `alt` text stays meaningful when images fail to load.
- Image sources never come from arbitrary user paths/URLs.
- Attachment filenames with special characters follow policy.
- Files are not oversized; streams remain readable when MIME serializes.

These checks belong primarily to **MIME builder tests** or attachment security tests rather than pure HTML escaping tests. Separating layers keeps tests readable and failures easy to localize.

### Never render user-supplied resource paths directly

If a template allows picking a logo or fragment by name, map an ID to an approved resource. Inputs like `../../secrets` must never turn into a template path or filesystem path.

Test invalid resource keys before reaching MIME construction.

## 21. Test templates for missing keys, fragments, or variables

Bugs that often appear only after deployment:

- Template file placed in the wrong folder or with the wrong suffix.
- Fragment renamed while main template still references the old name.
- Message bundle missing a key for one locale.
- Field renamed in the view model without updating the template.
- A null field throwing an exception in a property dereference expression.
- Template cache serving an older version.

### Verify that resources exist

When using `ClassLoaderTemplateResolver`, test rendering a fixed template name:

```java
@Test
void rendersExpectedTemplateResource() {
    Context context = new Context(Locale.ENGLISH);
    context.setVariable("customerName", "Ada");
    context.setVariable("orderNumber", "ORD-001");
    context.setVariable("lines", List.of());
    context.setVariable("formattedTotal", "0");
    context.setVariable("detailUrl",
            "https://shop.example.org/orders/ORD-001");

    String html = engine.process(
            "order-confirmed", context
    );

    assertThat(html).contains("ORD-001");
}
```

If the engine should only render approved templates, restrict template-name selection from external inputs. Never pass a client-supplied string as a template path in email rendering.

### Verify required variables are not dropped from the model

Do not rely solely on Thymeleaf rendering blanks when variables are missing. You can:

1. Validate the model at the input boundary.
2. Maintain a schema/contract for fields required by templates.
3. Test every notification type with a minimal valid fixture.
4. Update mappings/fixtures in the same change whenever templates change.

If a required variable is absent, fail before creating the message rather than sending an email with subtle blank gaps.

## 22. Exception tests and the rule against sending broken emails

A vital rule: if data is invalid or the renderer fails, **SMTP must never be called**.

Service orchestration example:

```java
public void sendOrderConfirmation(OrderMailModel model) {
    RenderedMail rendered = renderer.render(
            model, localePolicy.forOrder(model),
            zonePolicy.forOrder(model)
    );

    MimeMessage message = messageBuilder.build(
            model, rendered
    );

    mailSender.send(message);
}
```

Test with mock:

```java
@Test
void doesNotSendWhenRequiredDataIsMissing() {
    OrderMailModel invalid = withOrderNumber(
            OrderMailFixtures.validOrder(),
            null
    );

    assertThatThrownBy(() ->
            notificationService.sendOrderConfirmation(invalid)
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(mailSender);
}
```

The helper/model/service are illustrative components and must be initialized in the test fixture. What matters is **testing both the returned error and that side effects did not occur**.

### Distinguish render errors from SMTP errors

- Render errors: missing data, broken template, missing key, invalid URI.
- MIME builder errors: invalid headers, unreadable attachment resource.
- SMTP errors: authentication, network, server rejection.

If you catch every exception and report a generic "send failed," diagnosing root causes becomes hard. In logs and delivery records, record distinct error categories while avoiding exposing sensitive content.

## 23. Boundary data for multi-language subjects and templates

Language and encoding cases:

| Case | What to verify |
|---|---|
| Accented Vietnamese names | Unicode preserved in HTML/plain/subject. |
| Emojis in user names | Surrogate pairs not lost. |
| CJK | No replacement character `` appears. |
| Arabic/RTL | Key data order not scrambled; separate visual test. |
| Single quotes in subject bundle | `MessageFormat` handles them properly. |
| Unsupported locale | Falls back or fails per policy. |
| Locale with different number separators | Does not format using JVM default. |
| Currency differing from locale | Uses transaction currency. |
| Timestamp near midnight | Uses recipient's exact time zone. |
| Template text with `<` and `&` | HTML escaped properly, plain text not over-encoded. |

CI can run a dedicated test group with intentionally altered default locale/time zone to expose hidden dependencies. Avoid mutating global JVM settings concurrently across parallel tests without isolation.

## 24. Snapshot tests: useful when applied wisely

Some projects save sample rendered HTML outputs as **snapshots/golden files**. When a template changes, tests diff the new output against the approved output.

Benefits:

- Detects unintended edits to copy or layout fragments.
- Supports reviewing diffs of subject/HTML/plain text.
- Aids content review workflows.
- Especially helpful when multiple locales coexist.

Limitations:

- Whitespace or attribute-order shifts create noisy diffs.
- Huge snapshots are hard to read; reviewers may rubber-stamp approvals.
- Snapshots do not prove HTML safety or correct business data on their own.
- Unfixed timestamps, UUIDs, or map ordering make snapshots flaky.
- Real PII inside snapshots leaks sensitive data into the repository.

### A balanced strategy

Combine:

1. **Semantic assertions:** DOM contains right content, links, element counts.
2. **Security assertions:** injected markup never turns into DOM elements.
3. **Contract assertions:** required/optional variables, fallbacks, locales.
4. **Selective snapshots:** a few critical, stabilized cases.

Never replace all tests with snapshots or rely solely on `assertThat(html).isNotBlank()`. A template rendering a long string with the wrong order code still passes weak assertions.

## 25. Property-based testing for unpredictable inputs

Beyond hand-picked boundary values, **property-based testing** can generate diverse Unicode strings, lengths, and special character combinations.

Invariants worth checking:

- Renderer never creates `script` elements from `customerName`.
- Rendered output contains no illegal newlines in subject.
- Strings rendered via `th:text` parse back from the DOM matching the input text.
- Renderer does not depend on nondeterministic ordering when inputs are ordered.
- For valid inputs, output contains the exact notification ID/order number.
- For invalid inputs, there is no execution path reaching `JavaMailSender.send`.

Libraries like jqwik or QuickTheories can generate inputs. This is an additional layer and does not replace concrete business test cases or manual review.

### Why keep a stable seed?

When a fuzz/property test uncovers a failure, record the seed and minimal counterexample to reproduce it. Otherwise, bugs may appear once in CI and vanish on rerun, making diagnosis difficult.

## 26. Performance and resources on extreme inputs

Templates with huge lists or big notes can spike render time and memory. Relevant tests include:

- 1, 10, 100, 1,000 items (per business limits).
- Notes of several KB or near the allowed cap.
- Many repeated fragments or nested templates.
- Rendering across many locales.
- Rendering a high volume of notifications concurrently.

**Hard wall-clock unit tests** like "must render under 20 ms" are usually unstable in CI. Instead:

- Verify oversized inputs are rejected early.
- Run dedicated benchmarks/performance tests in an appropriate environment.
- Measure p95/p99 render latency in operational environments.
- Check template caching and avoid N+1 database queries in renderers.
- Never allow templates to access repositories or remote services directly.

Boundary unit tests should guard **data thresholds and contracts**, while benchmarks measure performance characteristics under controlled load.

## 27. Minimal boundary-data matrix

To design tests systematically, use this matrix:

| Group | Cases | Test expectations |
|---|---|---|
| Required text | `null`, `""`, whitespace | Fail-fast or fallback per contract. |
| Optional text | `null`, empty, whitespace | No orphan labels or empty HTML blocks. |
| HTML injection | `<script>`, `<img onerror>`, `&<>` | Text escaped, no malicious elements created. |
| Subject injection | CR/LF, control characters | Rejected before MIME builder. |
| Unicode | Vietnamese, CJK, emoji, RTL | Characters preserved, no encoding corruption. |
| Long text | Just below and above limit | Accepted/rejected per policy, no unsafe slicing. |
| Lists | `null`, 0, 1, many, null element | Exact row count, ordering, and error semantics. |
| Money | 0, negative, huge, high precision | Business-accurate formatting/rounding. |
| Time | Midnight, DST, leap day | Correct locale and time zone. |
| URLs | Valid HTTPS, `javascript:`, spoofed host | Valid links used or rejected. |
| Locales | Valid, missing bundle, missing key | Fallback/failure per rules. |
| Template resources | Missing file, wrong fragment | Observable error, no SMTP send. |
| Cross-format | Subject, plain, HTML | Key values consistent across all three. |
| MIME | UTF-8, alternative, inline/attachment | Right headers and parts without SMTP. |
| Reproducibility | Fixed clock, stable fixtures | Reruns yield identical results. |

This is a starter matrix. Each notification type may need domain-specific cases: seat count = 0, tracking code pending, expired coupon, recipient without a name, refunded order, jurisdiction-specific text, etc.

## 28. Recommended workflow when adding a new email template

A straightforward workflow to apply:

1. **Define the model:** list required/optional fields, types, limits, and sources.
2. **Lock down policies:** fallbacks, locale, time zone, money rounding, URL hosts, whitespace handling.
3. **Build a minimal valid fixture:** never use production data.
4. **Build templates:** use escaped text outputs, separate subject/HTML/plain.
5. **Write required/optional tests:** `null`, empty, and boundary values.
6. **Write dangerous-input tests:** HTML injection, URL schemes, control characters.
7. **Write semantic tests:** order codes, amounts, dates, and lists.
8. **Write multi-language tests:** Unicode, placeholders, fallbacks.
9. **Write MIME tests:** UTF-8 subject, `text/plain` + `text/html`, attachments/CIDs if any.
10. **Write failure tests:** renderer errors must block SMTP sending.
11. **Review snapshots/previews:** confirm content and layout on target email clients.
12. **When templates change:** intentionally update contracts and tests rather than blindly updating snapshots.

When a system has many email types, build **shared contract tests** for universal rules (no HTML leaks, no null required fields, no oversized data), while keeping template-specific tests for business semantics.

## 29. Common mistakes when testing templates

| Symptom | Common cause | Improvement |
|---|---|---|
| Test passes yet email shows literal `null` | Asserted only non-empty output | Validate required fields and assert DOM text. |
| `<script>` string becomes an element | Used unescaped output | Use `th:text` and security assertions. |
| Link in email points to wrong site | Trusted client URL input | Build links from trusted origin, allowlist hosts, test URLs. |
| Tests miss missing translations | Tested only default locale | Test all supported locales and missing keys. |
| Tests depend on CI machine | Relied on system clock/zone/locale | Pass Clock, ZoneId, and Locale explicitly. |
| Amounts display inconsistently | Used floating point or formatted in multiple layers | Use BigDecimal and a contracted formatter. |
| Empty list leaves broken layout | Never tested zero items | Test 0/1/n items and conditional blocks. |
| Header fails when name has newlines | No subject validation | Reject control characters before MIME. |
| MIME test checks only one part index | Multipart mode creates nested trees | Traverse MIME tree by content type. |
| Unit tests send real emails | Renderer coupled to transport | Decouple renderer from JavaMailSender; separate SMTP tests. |
| Snapshots change constantly | Unstable UUIDs/times/map ordering | Use fixed fixtures/clocks and semantic assertions. |
| Long-input tests slow down CI | No upper bound on valid inputs | Enforce size limits and benchmark separately. |
| Optional note shows label without value | Hid only text node instead of whole block | Condition on the entire block and test DOM. |
| Recipients see HTML yet plain text is wrong | Tested only HTML | Render/test plain, subject, and semantic consistency. |

## 30. Key points to remember

- **Boundary-value testing** deliberately exercises `null`, empty, whitespace, 0, extreme lists, long strings, Unicode, and malicious inputs—not just "pretty" sample data.
- Separate **required** and **optional** data; missing required fields should fail before calling SMTP.
- Test renderers **independently of `JavaMailSender.send(...)`** so failures clearly distinguish content bugs from transport bugs.
- With Thymeleaf, use `th:text` for untrusted data and verify via DOM parsing; avoid `th:utext` unless content is strictly controlled.
- URLs in HTML must be built/validated per policy; HTML escaping alone does not protect against `javascript:` or spoofed hosts.
- Subject is a header: block CR/LF, control characters, and test length limits separately.
- Build deterministic fixtures using explicit `Clock`/`ZoneId`/`Locale`, free from CI environment assumptions.
- Use `BigDecimal`, explicit currency rules, and a consistent formatter for financial data.
- Test `null`, 0, 1, and multiple elements for collections; never let templates drop valid zero values.
- Test consistency across subject, plain text, and HTML; never rely solely on "HTML is non-blank."
- Use `MimeMessageHelper` to inspect MIME structure in memory **without an SMTP connection**.
- Combine semantic assertions, security assertions, and selective snapshots; for layout, run dedicated visual tests across email clients.
- When rendering fails, log the cause and **never send a broken email** to recipients.

**Conclusion:** A high-quality email template not only renders neatly for standard inputs, it also handles the toughest edge cases at contract boundaries. Unit testing with boundary data catches content bugs, HTML/header safety issues, multi-language formatting defects, and inconsistencies before messages ever reach Spring Mail. Explicit input contracts, reproducible tests, and decoupling renderers from SMTP form the foundation for evolving an email system without wrong notifications or data leaks.
