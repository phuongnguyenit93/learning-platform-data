# Localizing Email Subject and Body Content

An email sent to users in Vietnam, Japan, or France usually requires more than translating a sentence into another language. **Subject**, plain-text content, HTML, dates/times, monetary amounts, support links, and layout must all fit the recipient's language and region. In **Spring Framework Mail**, you can combine `MessageSource`, resource bundles, a template engine, and `MimeMessageHelper` to build locale-appropriate emails before sending via `JavaMailSender`.

Localization (often abbreviated l10n) is the process of adapting content and presentation for a specific locale. It encompasses translations, date/number/currency formatting, time zones, regional links, right-to-left display rules, and content requirements in the target market.

This lesson covers selecting the email locale, organizing message bundles and HTML templates, localizing subject along with plain text/HTML, formatting data by locale, handling fallbacks, propagating locale through asynchronous tasks, and testing language variants.

## 1. Why Localize Both Subject and Body?

Recipients usually see the **subject before opening the email**. If the subject is in a different language from the body, users may misunderstand the message or ignore it. Similarly, if HTML is translated while plain text remains in English, users reading on text-only clients get an inconsistent experience.

Example of the same order confirmation email:

| Component | `vi-VN` | `en-US` |
|---|---|---|
| Subject | Xác nhận đơn hàng ORD-1024 | Order confirmation ORD-1024 |
| Heading | Đơn hàng của bạn đã được xác nhận | Your order is confirmed |
| CTA | Theo dõi đơn hàng | Track your order |
| Footer | Cần hỗ trợ? Liên hệ chúng tôi. | Need help? Contact us. |
| Date | 12/11/2026 (regional convention) | Nov 12, 2026 |
| Amount | 1.250.000 ₫ | $1,250.00 (if the transaction is actually in USD) |

The date and amount examples illustrate formatting only; actual values must be based on transaction data and product policy.

Consistent localization helps recipients recognize the email's purpose from the subject, ensures subject/plain/HTML convey the same business status, matches regional date and number conventions, and allows content to be reproduced under the chosen locale during incident investigation.

**Do not translate isolated fragments by concatenating sentence pieces.** Word order, grammar, plurals, and punctuation vary across languages. Translate whole messages or use parameterized message patterns.

## 2. Distinguishing Locale, Language, Country, Time Zone, and Currency

Java represents a locale with `java.util.Locale`. A locale describes a language and may include a region or variant:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale usEnglish = Locale.forLanguageTag("en-US");
Locale britishEnglish = Locale.forLanguageTag("en-GB");
Locale japanese = Locale.forLanguageTag("ja-JP");
```

A locale can be represented by a BCP 47 language tag:

```text
vi-VN
en-US
en-GB
ja-JP
fr-FR
ar-SA
```

Related concepts must be separated:

| Concept | Example | Role |
|---|---|---|
| Language | `vi`, `en`, `ja` | Language used to select translations. |
| Region | `VN`, `US`, `GB`, `JP` | Regional conventions, spelling, and formatting. |
| Locale | `vi-VN`, `en-US` | Combination of language and region. |
| Time zone | `Asia/Ho_Chi_Minh`, `America/New_York` | Determines local time. |
| Currency | `VND`, `USD`, `JPY` | Monetary unit of the transaction. |
| Measurement system | metric, US customary | How measurement units are displayed. |

**Locale does not automatically determine all personal details.** A user may choose an English interface while living in Vietnam, using Vietnam's time zone, and paying in VND. Do not infer currency or time zone solely from locale.

### Creating a Locale from a Language Tag

Prefer `Locale.forLanguageTag(...)` when data comes from configuration, profile, or HTTP headers:

```java
Locale locale = Locale.forLanguageTag("vi-VN");

String language = locale.getLanguage(); // vi
String region = locale.getCountry();    // VN
String tag = locale.toLanguageTag();    // vi-VN
```

Do not pass underscore-separated strings like `vi_VN` into `forLanguageTag` as if they were language tags. If a legacy system stores `vi_VN`, convert per defined data conventions or normalize to BCP 47 before use.

### Locale Is Not a Time Zone

If an email says "Appointment at 9:00," the recipient needs to know 9:00 in which time zone. `Locale` is not enough to determine this. Fetch `ZoneId` from the user profile, business configuration, or event schedule.

Likewise, the `en-US` locale does not mean every amount should be displayed in USD. **Currency must come from the transaction**, while locale only determines how that amount is formatted.

## 3. Deciding Which Locale to Use for an Email

An email's locale should be selected by an explicit policy. Possible sources:

1. **User's chosen language in profile:** usually the priority source for account emails.
2. **Language of the transaction or market:** may suit invoices, purchase confirmations, or legal emails.
3. **Locale from HTTP request:** `Accept-Language` can help pick a language when the user has no saved preference.
4. **Application default locale:** used when no applicable source exists.
5. **Template default locale:** final fallback if specified by the product.

Policy example:

```text
User profile locale
       |
       | absent
       v
Business transaction locale
       |
       | absent
       v
Request Accept-Language
       |
       | absent / unsupported
       v
Application default locale
```

The order above is just a sample policy. For invoice emails, applicable law, or contract-related content, locale may have to follow the transaction's market. For account emails, the user's choice is usually more appropriate.

### Do Not Use the Server's Default Locale as Product Policy

`Locale.getDefault()` depends on the JVM/OS environment. Production servers, containers, and developer machines can have different default locales. If code implicitly relies on this value, the same email may render differently across environments.

Configure the application's default locale explicitly:

```yaml
app:
  mail:
    default-locale: vi-VN
```

Then convert to `Locale` in a locale-selection component:

```java
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MailLocalePolicy {

    private final Locale defaultLocale;

    public MailLocalePolicy(
            @Value("${app.mail.default-locale:vi-VN}") String defaultTag
    ) {
        this.defaultLocale = Locale.forLanguageTag(defaultTag);
    }

    public Locale choose(String preferredLanguageTag) {
        if (preferredLanguageTag == null
                || preferredLanguageTag.isBlank()) {
            return defaultLocale;
        }

        Locale requested =
                Locale.forLanguageTag(preferredLanguageTag);

        if (requested.getLanguage().isBlank()) {
            return defaultLocale;
        }

        return requested;
    }
}
```

The example illustrates taking a language tag and falling back when empty. A real application should check supported locales, handle invalid tags, and optionally normalize `en` to `en-US` according to the product's locale list.

### Supporting a Defined List of Locales

Not every template has every language. You can declare a supported list:

```java
import java.util.List;
import java.util.Locale;

public final class SupportedMailLocales {

    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("ja-JP")
    );

    private SupportedMailLocales() {}

    public static boolean supports(Locale candidate) {
        return SUPPORTED.contains(candidate);
    }
}
```

If a locale is unsupported, pick the fallback per policy and **record the locale actually used**. Do not silently render `en-US` while saving metadata `ja-JP`, because later you will not be able to explain accurately what content the recipient received.

## 4. Organizing Message Bundles by Locale

Spring provides `MessageSource` to look up messages by message code and locale. The common approach uses properties files following `ResourceBundle` conventions.

Example structure:

```text
src/main/resources/
└── mail/
    ├── messages.properties
    ├── messages_vi.properties
    ├── messages_vi_VN.properties
    ├── messages_en.properties
    ├── messages_en_US.properties
    ├── messages_ja.properties
    └── messages_ja_JP.properties
```

File roles:

- `messages.properties`: base bundle or fallback language defined by the application.
- `messages_vi.properties`: general Vietnamese translation.
- `messages_vi_VN.properties`: Vietnamese specific to Vietnam.
- `messages_en_US.properties`: US English version.
- `messages_ja_JP.properties`: Japanese in Japan.

With locale `vi-VN`, the bundle mechanism can look up the specific `messages_vi_VN.properties`, fall back by language to `messages_vi.properties`, and then to the base bundle. Actual fallback behavior is also affected by `MessageSource` configuration; control it explicitly instead of implicitly relying on the server's locale.

### Example Vietnamese File

```properties
mail.order.subject=Xác nhận đơn hàng {0}
mail.order.heading=Đơn hàng của bạn đã được xác nhận
mail.order.greeting=Xin chào {0},
mail.order.body=Đơn hàng {0} đã được xác nhận. Cảm ơn bạn đã mua hàng.
mail.order.cta=Theo dõi đơn hàng
mail.order.support=Cần hỗ trợ? Hãy liên hệ với chúng tôi.
```

### Example US English File

```properties
mail.order.subject=Order confirmation {0}
mail.order.heading=Your order is confirmed
mail.order.greeting=Hello {0},
mail.order.body=Order {0} has been confirmed. Thank you for your purchase.
mail.order.cta=Track your order
mail.order.support=Need help? Contact us.
```

Message codes such as `mail.order.subject` are stable identifiers in code. Actual values vary by locale.

### Setting UTF-8 Encoding for Message Bundles

With `ResourceBundleMessageSource`, you can configure encoding explicitly:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ResourceBundleMessageSource;

@Configuration
public class MailMessageConfiguration {

    @Bean
    public MessageSource mailMessageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();

        source.setBasenames("mail/messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);

        return source;
    }
}
```

`setBasenames("mail/messages")` points to bundle files on the classpath without needing the `.properties` extension. `setDefaultEncoding("UTF-8")` specifies the encoding when reading files. Disabling system-locale fallback prevents results from accidentally depending on the server locale; fallback across bundles by language/region still needs intentional design.

If using Spring Boot auto-configuration for the message source, you can configure:

```yaml
spring:
  messages:
    basename: mail/messages
    encoding: UTF-8
    fallback-to-system-locale: false
```

Property names and binding capability must match the project's Spring Boot version. If the application declares its own `MessageSource` bean, verify whether that bean replaces or supplements the message source used by the template engine.

## 5. Looking Up Subject by Locale with MessageSource

`MessageSource` can return content by code, arguments, and locale:

```java
String subject = messageSource.getMessage(
        "mail.order.subject",
        new Object[] { orderNumber },
        locale
);
```

If `locale` is `vi-VN`, the subject comes from the Vietnamese bundle; if `en-US`, it comes from the matching English bundle.

A small service:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Component;

@Component
public class MailSubjectResolver {

    private final MessageSource messageSource;

    public MailSubjectResolver(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String orderConfirmation(
            String orderNumber,
            Locale locale
    ) {
        return messageSource.getMessage(
                "mail.order.subject",
                new Object[] { orderNumber },
                locale
        );
    }
}
```

Using the overload without a default message means **a missing message code can throw `NoSuchMessageException`**. For transactional emails, this is usually better than sending a blank subject or accidentally using the wrong language. If business rules have a fallback, perform the fallback intentionally and record the result.

### Arguments in Message Patterns

In a properties file:

```properties
mail.order.subject=Order confirmation {0}
mail.order.greeting=Hello {0},
mail.order.item-count=You ordered {0} items.
```

`MessageSource` processes arguments following `MessageFormat` rules. Watch out for single quotes in patterns: `MessageFormat` uses single quotes to escape special characters. If translated text contains a single quote to display, translators must be instructed how to write patterns properly, such as doubling quotes when necessary.

Do not build sentences from fragments like `prefix + customerName + suffix` when grammar structure can differ across languages. Put the entire sentence in the message bundle with placeholders.

## 6. Localizing HTML Templates with Thymeleaf

Message bundles suit subjects, CTAs, and UI strings. For emails with HTML layouts, you can use separate templates per locale or combine a shared template with message keys.

### 6.1. Separate Templates per Locale

Example:

```text
mail/
└── order-confirmation/
    ├── v1/
    │   ├── vi-VN.html
    │   ├── en-US.html
    │   └── ja-JP.html
    └── v2/
        ├── vi-VN.html
        ├── en-US.html
        └── ja-JP.html
```

Vietnamese template:

```html
<!doctype html>
<html lang="vi" dir="ltr">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body>
  <main>
    <h1>Đơn hàng của bạn đã được xác nhận</h1>
    <p>Xin chào <span th:text="${customerName}">bạn</span>,</p>
    <p>
      Mã đơn hàng:
      <strong th:text="${orderNumber}">ORD-001</strong>
    </p>
    <a th:href="${trackingUrl}">Theo dõi đơn hàng</a>
  </main>
</body>
</html>
```

The English template can have a different order and phrasing:

```html
<!doctype html>
<html lang="en" dir="ltr">
<head>
  <meta charset="UTF-8">
  <title>Order confirmation</title>
</head>
<body>
  <main>
    <h1>Your order is confirmed</h1>
    <p>Hello <span th:text="${customerName}">customer</span>,</p>
    <p>
      Order number:
      <strong th:text="${orderNumber}">ORD-001</strong>
    </p>
    <a th:href="${trackingUrl}">Track your order</a>
  </main>
</body>
</html>
```

Separate templates allow editors to adjust layout, forms of address, and content order per language. The downside is that multiple files can duplicate structure and require synchronization when adding new data fields.

### 6.2. Using Message Expressions in Thymeleaf

You can keep a shared HTML structure and fetch strings from `MessageSource`:

```html
<!doctype html>
<html lang="vi" dir="ltr">
<body>
  <main>
    <h1 th:text="#{mail.order.heading}">Order confirmed</h1>
    <p th:text="#{mail.order.greeting(${customerName})}">
      Hello, customer
    </p>
    <p>
      <span th:text="#{mail.order.number-label}">Order number</span>:
      <strong th:text="${orderNumber}">ORD-001</strong>
    </p>
    <a th:href="${trackingUrl}"
       th:text="#{mail.order.cta}">Track your order</a>
  </main>
</body>
</html>
```

In Thymeleaf:

- `#{...}` looks up messages using the context's locale.
- `${...}` reads data variables placed in the context.
- `th:text` writes text content and HTML-escapes by default.
- `th:href` sets the URL attribute value; the URL must still be validated beforehand.

A shared structure works well when languages share similar layouts. When languages differ significantly in sentence order or layout, locale-specific templates can be clearer.

### 6.3. Configuring SpringTemplateEngine

For applications using Thymeleaf Spring integration, you can configure an engine for email:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

@Configuration
public class MailTemplateConfiguration {

    @Bean
    public SpringTemplateEngine mailTemplateEngine(
            MessageSource mailMessageSource
    ) {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();

        resolver.setPrefix("mail/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(true);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        engine.setMessageSource(mailMessageSource);
        return engine;
    }
}
```

`SpringTemplateEngine` provides Spring integration, including message expressions and the Spring dialect. The `org.thymeleaf.spring6` package fits Thymeleaf integration for Spring 6; applications using a different Spring/Thymeleaf version need the corresponding dependencies and packages.

## 7. Rendering Templates for a Specific Locale

Do not let the renderer pick up the server locale automatically. Pass `Locale` into every render call:

```java
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class LocalizedMailTemplateRenderer {

    private final SpringTemplateEngine templateEngine;

    public LocalizedMailTemplateRenderer(
            SpringTemplateEngine templateEngine
    ) {
        this.templateEngine = templateEngine;
    }

    public String render(
            String templateName,
            Locale locale,
            Map<String, Object> variables
    ) {
        Context context = new Context(locale);
        context.setVariables(variables);

        return templateEngine.process(templateName, context);
    }
}
```

Example:

```java
String html = renderer.render(
        "order-confirmation/v2/vi-VN",
        Locale.forLanguageTag("vi-VN"),
        Map.of(
                "customerName", "Alice Nguyen",
                "orderNumber", "ORD-2026-001",
                "trackingUrl",
                "https://shop.example.org/orders/ORD-2026-001"
        )
);
```

`Context(locale)` supplies the locale to message expressions in the template. Template path and locale are passed separately because **template key/version** and **rendering language** are two independent management dimensions.

If using a shared template with a message bundle, the template name may consist solely of key/version; the locale is still passed via `Context`. If using separate HTML files per locale, the template name can contain the language tag, such as `order-confirmation/v2/vi-VN`.

## 8. Sending Subject, Plain Text, and HTML in the Same Locale

A complete email should generate all three content parts in the same locale:

1. Subject looked up from message bundle.
2. Plain text built from bundle or separate text template.
3. HTML rendered from locale-specific template.

Service example:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Map;
import org.springframework.context.MessageSource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class LocalizedOrderMailer {

    private final JavaMailSender mailSender;
    private final MessageSource mailMessageSource;
    private final LocalizedMailTemplateRenderer renderer;

    public LocalizedOrderMailer(
            JavaMailSender mailSender,
            MessageSource mailMessageSource,
            LocalizedMailTemplateRenderer renderer
    ) {
        this.mailSender = mailSender;
        this.mailMessageSource = mailMessageSource;
        this.renderer = renderer;
    }

    public void sendConfirmation(
            String recipient,
            String orderNumber,
            String customerName,
            String trackingUrl,
            Locale locale
    ) throws MessagingException {

        String subject = mailMessageSource.getMessage(
                "mail.order.subject",
                new Object[] { orderNumber },
                locale
        );

        String plainText = mailMessageSource.getMessage(
                "mail.order.body",
                new Object[] { orderNumber, trackingUrl },
                locale
        );

        String html = renderer.render(
                "order-confirmation/v2/" + locale.toLanguageTag(),
                locale,
                Map.of(
                        "customerName", customerName,
                        "orderNumber", orderNumber,
                        "trackingUrl", trackingUrl
                )
        );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.org", "Example Store");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, html);

        mailSender.send(message);
    }
}
```

The example assumes the corresponding message codes and templates already exist for the selected locale. In a real application, check supported locales, ensure templates have all required variables, build URLs from a trusted domain, use a localized sender display name if needed, and keep subject/plain/HTML on the same version.

The `MimeMessageHelper(message, true, "UTF-8")` constructor enables multipart, needed for plain/HTML alternatives. The UTF-8 charset supports Vietnamese, Japanese, and other Unicode characters in bodies/headers. It does not automatically convert an email address with a Unicode local-part into a valid SMTPUTF8 address.

### Do Not Let Subject Use One Locale While Body Uses Another

A common design bug is building the subject from `LocaleContextHolder.getLocale()` in the request while the worker renders HTML using the default locale. The result can be an English subject with a Vietnamese body.

Select the locale **once** in business logic, then pass that same value to the subject resolver, plain-text renderer, and HTML renderer. Record the used locale in send-request metadata if auditing is needed.

## 9. Formatting Dates and Times by Locale and Time Zone

Dates and times often appear in booking confirmations, appointments, invoices, or shipping notifications. Two inputs are needed:

- `Locale`: date format, month names, and component order.
- `ZoneId`: time zone to convert a timestamp into local time.

Example:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Instant appointment = Instant.parse("2026-11-12T09:30:00Z");

Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

DateTimeFormatter formatter =
        DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.LONG)
                .withLocale(locale)
                .withZone(zone);

String localizedDate = formatter.format(appointment);
```

The same `Instant` can display differently when changing locale or time zone. That does not mean the event timestamp changed.

**Do not use locale to infer time zone.** Fetch the time zone from the user profile or appointment data. If an email involves legal deadlines, clearly display the time zone or region name so recipients are not misled.

### Avoid Formatting Dates Too Early

Do not store pre-formatted date strings and reuse them for every locale. Store standard timestamps such as `Instant`, `OffsetDateTime`, or an appropriate time type, then format when rendering the email. This allows regenerating the email for another locale without losing source information.

## 10. Formatting Numbers, Currencies, and Measurement Units

`NumberFormat` can format numbers by locale:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

BigDecimal amount = new BigDecimal("1250000.50");

Locale vietnamese = Locale.forLanguageTag("vi-VN");
NumberFormat numberFormat =
        NumberFormat.getNumberInstance(vietnamese);

String number = numberFormat.format(amount);
```

For currency, take the **currency code from the transaction** and format by locale:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

BigDecimal total = new BigDecimal("1250000");
String currencyCode = "VND";

Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat formatter =
        NumberFormat.getCurrencyInstance(locale);

formatter.setCurrency(Currency.getInstance(currencyCode));

String localizedAmount = formatter.format(total);
```

Locale affects separators, symbol placement, and presentation; currency code defines the actual currency unit. Do not replace VND with USD merely because the email is sent in English.

For measurement units, know the source unit and conversion policy. For example, a parcel has a weight of 2 kg; if the recipient is in a market using pounds, the system can convert to the corresponding unit and state the unit clearly. Never merely swap the `kg` label for `lb` while keeping the number unchanged.

### Use Typed Values; Do Not Use Formatted Strings as Source Data

Keep `BigDecimal`, `Currency`, `Instant`, `ZoneId`, and appropriate data types until the rendering step. A formatted string is **locale-specific output** and should not be used for calculations or stored as the original transaction value.

## 11. Localizing Plurals and Parameterized Sentences

Languages have different pluralization rules. For example, English distinguishes `1 item` and `2 items`; some languages have more plural categories than `one` and `other`.

Do not build sentences by concatenation:

```java
String text = count + " item(s)";
```

That is unnatural and hard to translate. You can use message patterns for simple cases:

```properties
mail.cart.count=You have {0} items in your cart.
```

However, `MessageFormat` does not provide all plural/gender rules across languages. For content with complex plurals, consider **ICU MessageFormat** or a localization system supporting CLDR plural/select rules.

A conceptual pattern:

```text
{count, plural,
    one {You have one item}
    other {You have # items}
}
```

This is illustrative ICU MessageFormat syntax, not default `java.text.MessageFormat` syntax. Add the appropriate library and configuration if using it.

Beyond plurals, sentences may need choices by grammatical gender, product type, or business state. Discuss the context of each message code with translators; a short string stripped of context is often hard to translate accurately.

## 12. Localizing HTML Content and Display Language

HTML emails should declare the document language:

```html
<html lang="vi" dir="ltr">
```

For right-to-left languages such as Arabic or Hebrew, consider the `dir` attribute:

```html
<html lang="ar" dir="rtl">
```

Key notes:

- Set `lang` matching the locale so screen readers and assistive tools understand the language.
- For RTL, verify alignment, icon order, punctuation, numbers, and links.
- Do not assume switching `text-align: right` alone suffices to convert a layout to RTL.
- Use email-compatible CSS; many clients do not fully support modern CSS.
- Use fonts with glyphs covering the supported scripts.
- Keep alt text for images and ensure critical information is in text.
- Test mixing RTL text with LTR order codes, URLs, and phone numbers.

If the locale determines display direction, pass a `textDirection` variable determined from the supported locale list rather than inserting arbitrary strings into HTML attributes.

## 13. Fallback When Translations or Templates Are Missing

A localization system must clearly define what happens when no translation exists for the requested locale.

For example, a user chooses `ja-JP`, yet the order confirmation email currently only has `vi-VN` and `en-US`. A policy could be:

```text
ja-JP
  ↓ no regional translation
ja
  ↓ no Japanese bundle
application default: en-US
  ↓ render and record resolvedLocale=en-US
```

Fallback levels typically include:

1. Full locale, e.g., `ja-JP`.
2. Language-only, e.g., `ja`.
3. Product-published default locale, e.g., `en-US`.
4. If still no message/template exists, **fail rendering explicitly** rather than sending an email missing content.

### Message Bundle Fallback and HTML Template Fallback Are Two Separate Things

`MessageSource` may find `mail.order.subject` from the base bundle, yet the HTML template `order-confirmation/v2/ja-JP.html` may still not exist. Conversely, the HTML template may exist while a message code inside it is missing.

Handle both sources:

- Message bundle: check message codes and locale fallback.
- Template: check file/template name and version.
- Plain text: verify whether a corresponding version exists.
- Subject: verify it is non-empty and in the same locale as the body.

### Do Not Fall Back Silently

If the requested locale is `ja-JP` yet the system sends `en-US`, record that fact. Falling back is acceptable if the product defines it, yet you should store both:

```text
requestedLocale = ja-JP
resolvedLocale  = en-US
fallbackReason  = TEMPLATE_NOT_AVAILABLE
```

This helps explain why a user received an email in a language different from their profile preference. For legal emails or market-mandated content, fallback may not be allowed; in that case, block creating the send request until an approved translation is ready.

## 14. Locale Must Propagate Through Asynchronous Tasks

A common bug in queue-based mail-sending systems is relying on `LocaleContextHolder` inside workers.

In a synchronous HTTP request, Spring can place the locale on the thread's context. Yet when creating an asynchronous task or pushing a message to a queue, the worker may run on **another thread, another process, or another machine**. The request's thread-local context does not propagate automatically across a queue.

Do not do this:

```java
// Inside a worker, do not assume the original request's locale still exists.
Locale locale = LocaleContextHolder.getLocale();
```

Instead, select the locale when creating the request and store it in the event/outbox:

```java
public record EmailRequested(
        String messageId,
        String recipient,
        String templateKey,
        String templateVersion,
        String requestedLocaleTag,
        String resolvedLocaleTag,
        String payloadJson
) {
}
```

When the worker processes it:

```java
Locale locale =
        Locale.forLanguageTag(record.resolvedLocaleTag());

String subject = messageSource.getMessage(
        "mail.order.subject",
        new Object[] { orderNumber },
        locale
);
```

This keeps results consistent across instances and aids auditing. If policy requires determining the locale at send time, the worker can invoke the locale policy using stored profile data, yet **that rule must be documented explicitly**. Never let results depend accidentally on thread-locals.

### When Is LocaleContextHolder Used?

`LocaleContextHolder` is useful during synchronous request processing when the application configures `LocaleResolver`/`LocaleContextResolver`. For example, a controller can use the locale resolved from the HTTP request. However, when creating background jobs, extract the locale as explicit data before the request ends.

Do not use `LocaleContextHolder` as long-term storage for user preferences.

## 15. Combining Localization with Template Versioning

Locale and template version are two independent dimensions:

```text
templateKey = order-confirmation
templateVersion = v3
locale = vi-VN
variant = default
```

A template can have version `v3` for multiple languages. Choose a policy:

**Shared version across all locales:** `v3` is one release covering `vi-VN`, `en-US`, `ja-JP`. If the Japanese translation is not ready yet, either do not mark the whole release complete or define an explicit fallback.

**Per-locale version:** `vi-VN/v3`, `en-US/v2`, `ja-JP/v1`. This is flexible, though send records must store the exact version of that locale.

Either way, generated emails should record at least:

```json
{
  "messageId": "mail-12345",
  "templateKey": "order-confirmation",
  "templateVersion": "v3",
  "requestedLocale": "vi-VN",
  "resolvedLocale": "vi-VN",
  "variant": "default"
}
```

If message bundle contents change independently of the HTML template, tie them to the same release ID or content hash. Otherwise, the same template version can render a different subject after the bundle is updated.

**Published versions should be immutable.** If changing translations or wording, create a new version/release and preserve old content for pending requests referencing it.

## 16. Security and Untrusted Data in Localized Emails

Translations do not alter the security requirements of HTML emails.

- Use `th:text` to insert data into text nodes with HTML escaping.
- Validate URLs before putting them into `th:href`.
- Do not allow user data to become raw HTML unless sanitized per policy.
- Do not include secrets, internal tokens, or unnecessary data in emails.
- Validate dynamic variables in subjects to prevent header injection; use `MimeMessageHelper` APIs instead of concatenating raw headers.
- Do not assume externally supplied translations are always safe to render.
- Control permissions for editing and releasing templates/bundles.

A translation may contain special characters, quotes, line breaks, or broken placeholders. Validate data before release, especially for message patterns using `MessageFormat`.

## 17. Testing Localized Subject and Body

Testing a single locale is insufficient if an email has multiple translations. Maintain a test matrix by **template key × version × locale**.

| Test | What to Verify |
|---|---|
| Message bundle lookup | Required codes exist for supported locales. |
| Subject rendering | Subject is in the right language, parameters substituted, no leftover placeholders. |
| Plain-text rendering | Has complete content, CTA, and key information. |
| HTML rendering | Template loads right locale/version, no unresolved variables remain. |
| Unicode | Vietnamese, Japanese, punctuation, and special characters display properly. |
| Number/date/currency | Formatted per data's locale, time zone, and currency. |
| RTL | Reading direction, alignment, URLs, and identifiers display properly. |
| Fallback | Locales missing translations are handled per defined policy. |
| Async | Worker uses the stored locale instead of relying on the request thread. |
| MIME integration | Subject, text, and HTML have proper charsets and valid packaging. |

### MessageSource Test Example

```java
@Test
void resolvesOrderSubjectInVietnamese() {
    Locale locale = Locale.forLanguageTag("vi-VN");

    String subject = messageSource.getMessage(
            "mail.order.subject",
            new Object[] { "ORD-001" },
            locale
    );

    assertThat(subject).contains("Xác nhận đơn hàng");
    assertThat(subject).contains("ORD-001");
}
```

Another test for English should confirm the subject comes from the English bundle, not the default bundle.

### Testing Intentional Fallback

If `ja-JP` lacks a translation and policy permits falling back to `en-US`, tests should verify:

- `requestedLocale` remains `ja-JP`.
- `resolvedLocale` is recorded as `en-US`.
- Subject, plain text, and HTML all use `en-US`.
- Logs/metadata record the fallback reason.
- No part still uses `ja-JP` while another uses `en-US`.

### Checking Actual Emails

You can use Mailpit or GreenMail in test environments to receive emails. Verify the `Subject` header encodes and decodes properly; `Content-Type` of text/HTML has the right charset; Unicode content is not corrupted into garbled characters; plain text and HTML convey identical information; and the locale is recorded in send-request metadata.

SMTP test servers do not fully emulate the renderers of Gmail, Outlook, or Apple Mail. For critical emails, inspect rendering on target clients and devices, especially for RTL and CJK fonts.

## 18. Common Mistakes

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| English subject, Vietnamese body | Both parts resolved locales separately | Choose locale once and pass to all renderers. |
| Body falls back to default bundle | Missing locale-specific message or unclear fallback | Check properties files and resolved locale. |
| HTML fails to render while subject translates | Missing template file for locale/version | Check template catalog and fallback policy. |
| Worker sends email in server locale | Locale was not stored in queue/outbox | Store language tag in record and pass explicitly. |
| Month names or numbers wrong for region | Used JVM default format or manual string concatenation | Use `DateTimeFormatter`/`NumberFormat` with explicit locale. |
| Wrong time zone displayed | Inferred `ZoneId` from locale or used default timezone | Store and use `ZoneId` separately. |
| Amount shows wrong currency | Took currency from locale instead of transaction | Take currency code from business data. |
| Translation missing or ungrammatical | Concatenated sentence fragments, wrong placeholders | Use complete message patterns and review translations. |
| HTML broken in RTL languages | Changed alignment only without handling direction and mixed text | Use `dir`, test layout, and verify on real clients. |
| Vietnamese/Japanese diacritics garbled | Inconsistent bundle/template or MIME charset | Use UTF-8 from source files to `MimeMessageHelper`. |
| Old email uses unexpectedly new translation | Worker fetched `latest` instead of pinned version | Record version/release in outbox. |
| Subject contains literal `{0}` | Message pattern not resolved or missing argument | Check message code, arguments, and `MessageSource`. |

## 19. Recommended Architecture for Multi-Language Emails

Responsibilities can be separated into components:

```text
Business event
    |
    v
Mail request / outbox
    ├── templateKey
    ├── templateVersion
    ├── requestedLocale
    ├── resolvedLocale
    ├── recipient
    └── payload
         |
         v
Locale policy
         |
         v
Template + MessageSource renderer
    ├── subject
    ├── plain text
    └── HTML
         |
         v
MimeMessage builder
         |
         v
JavaMailSender
         |
         v
SMTP provider
```

Each part has a single role:

- **Business event:** supplies business data needing notification.
- **Mail request/outbox:** holds recipient, template version, locale, and payload to render.
- **Locale policy:** chooses locale by profile, transaction, or fallback.
- **Renderer:** looks up message bundles and renders subject/plain/HTML.
- **Message builder:** creates `MimeMessage`, sets headers, charset, and MIME parts.
- **JavaMailSender:** sends messages to SMTP.
- **Delivery tracker:** records SMTP results, bounces, and delivery events if provider supports them.

This separation allows swapping template engines or adding languages without rewriting SMTP sending logic. It also allows testing translations independently of mail server connectivity.

## 20. Takeaways

- **Locale** defines language and regional conventions; it does not automatically define transaction time zone or currency.
- Choose locale with an explicit policy: user preference, transaction locale, request preference, and application default.
- Use **`MessageSource` and resource bundles** to look up subject, CTA, footer, and parameterized strings.
- Use **Thymeleaf/SpringTemplateEngine** or an appropriate template engine to render HTML by locale; keep plain text matching.
- Pass **the same locale** to subject, plain text, and HTML. When processing asynchronously, store the language tag in the outbox instead of relying on the request's `LocaleContextHolder`.
- Use `DateTimeFormatter` and `NumberFormat` with explicit locales; obtain time zone and currency from corresponding business data.
- Use UTF-8 for message bundles, templates, and `MimeMessageHelper`; test both subject and body.
- Define explicit fallbacks, record `requestedLocale` and `resolvedLocale`, and never silently send in a different language.
- Version templates/bundles so sent email content can be reproduced; test per template version and locale.
- Verify HTML escaping, URLs, RTL, Unicode, and rendering across target mail clients.

Good email localization starts with **choosing the right locale**, then using that locale consistently to generate the subject, plain text, HTML, and formatted values. When locale, template version, and business data are recorded clearly, Spring Mail can send consistent, testable emails that remain traceable when investigation or content updates are needed.
