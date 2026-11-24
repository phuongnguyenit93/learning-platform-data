# Testing Templates with Complete and Missing Data

## 1. Why Test Email Templates with Multiple Datasets?

In **Spring Framework Mail**, applications usually separate email content generation from SMTP sending. An HTML template may render properly with one sample dataset yet fail when encountering real-world data: an empty customer name, an empty product list, a missing delivery address, an overly long order number, or a field containing special characters.

Order confirmation template example:

~~~html
<h1>Hello, <span th:text="${customerName}">there</span>!</h1>
<p>Order number: <strong th:text="${orderNumber}">ORD-001</strong></p>
<p>Delivery address: <span th:text="${deliveryAddress}">...</span></p>
<ul>
  <li th:each="item : ${items}">
    <span th:text="${item.name}">Product name</span>
  </li>
</ul>
~~~

If tests only provide complete `customerName`, `orderNumber`, `deliveryAddress`, and `items`, the template may pass fine. Yet in production, you may encounter:

- `customerName` is null, empty string, or whitespace-only.
- `deliveryAddress` is absent because the customer chose in-store pickup.
- `items` is an empty list or null because source data was not prepared.
- A product line is missing a name or display price.
- The order tracking URL has not been generated yet.
- The customer name contains `<`, `&`, quotes, or Unicode characters.
- A required variable is forgotten during rendering, leaving blanks or a template error.

**Testing templates with complete and missing data** verifies the template's data contract, behavior when optional fields are absent, and reaction when required data is invalid. The goal is not merely "renders without throwing an exception," but that the generated content is accurate, unambiguous, does not leak data, and remains readable in real-world scenarios.

## 2. Separating Template Rendering from Sending Emails

An email-sending system typically has these steps:

~~~text
Business data
    |
    v
Application service
    |
    v
Email model / DTO
    |
    v
Template renderer
    |
    +--> Subject
    |
    +--> text/plain body
    |
    +--> text/html body
              |
              v
         MimeMessageHelper
              |
              v
         JavaMailSender
              |
              v
          SMTP server
~~~

Each step has its own testing scope:

| Component | What to Verify | Is SMTP Needed? |
|---|---|---|
| Business data preparation | Right data, right permissions, right rules | No |
| Model passed to template | Required/optional fields, default values | No |
| Template renderer | Content, conditionals, loops, escaping, locale | No |
| MIME message assembly | Subject, charset, text/html, attachments | No SMTP server needed; can verify with Jakarta Mail |
| SMTP adapter | Calls JavaMailSender with right message, handles transport errors | Sender can be mocked |
| SMTP integration | Protocol, responses, TLS/AUTH per environment | Needs an SMTP test server |

**Template testing should not depend on real SMTP.** A broken template must be caught by fast, repeatable tests requiring no credentials. If template render tests have to connect to a provider, the boundary between content presentation and transport has been blurred.

A template can render properly while SMTP sending fails; conversely, SMTP can accept an email with a broken template. These two outcomes must be observed independently.

## 3. Defining the Data Contract Before Writing Tests

Before writing test cases, classify every variable the template uses:

| Category | Example | What to Do If Missing? |
|---|---|---|
| **Required** | Order number, recipient email, total amount to confirm | Validate and reject rendering or reject creating the send request |
| **Optional** | Delivery address, promo code, tracking URL | Hide the corresponding section or display an alternative message |
| **Has default** | Display name, generic greeting, secondary label | Use the defined fallback |
| **Potentially empty list** | Products, invoice lines, change history | Display empty state or hide the list block |
| **Formatted data** | Date/time, monetary amount, quantity | Normalize before rendering or format by locale |
| **Sensitive data** | Tokens, verification codes, personal info | Include only when needed and under protection policy |

This classification prevents two opposite mistakes:

- **Missing required data yet still sending the email:** the recipient gets an unusable message, e.g., "Order number: null."
- **Missing optional data causing the whole email to fail:** a customer without a delivery address still deserves a valid order confirmation email.

Templates should not decide every business rule themselves. For example, requiring an order to have an order number is an application/domain layer rule; the template simply displays that number. Conversely, hiding the address line when no address exists is a presentation rule that can be expressed with a template conditional.

### Explicit Model Example

~~~java
import java.util.List;

public record OrderConfirmationModel(
        String orderNumber,
        String customerName,
        String deliveryAddress,
        List<OrderLineModel> items,
        String trackingUrl,
        String placedAtText,
        String totalText) {
}

public record OrderLineModel(
        String name,
        String quantityText,
        String lineTotalText) {
}
~~~

`placedAtText` and `totalText` here are pre-formatted for the desired locale. This keeps the template from implementing currency logic or complex time conversions itself. If you want the template to format dates/money itself, explicitly declare the locale and test output across multiple locales.

## 4. Designing Templates That Handle Missing Fields

Example file **templates/mail/order-confirmation.html**:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Order confirmation</title>
</head>
<body>
  <h1>Order Confirmed</h1>

  <p>
    Hello,
    <strong th:text="${customerName} ?: 'there'">there</strong>!
  </p>

  <p>
    Order number:
    <strong th:text="${orderNumber}">ORD-001</strong>
  </p>

  <p th:if="${placedAtText != null and !#strings.isEmpty(placedAtText)}">
    Order time:
    <span th:text="${placedAtText}">12/11/2026</span>
  </p>

  <section th:if="${deliveryAddress != null and !#strings.isEmpty(deliveryAddress)}">
    <h2>Delivery Address</h2>
    <p th:text="${deliveryAddress}">Sample address</p>
  </section>

  <section>
    <h2>Items</h2>
    <ul th:if="${items != null and !#lists.isEmpty(items)}">
      <li th:each="item : ${items}">
        <span th:text="${item.name}">Product</span>
        <span> — </span>
        <span th:text="${item.quantityText}">1</span>
        <span> — </span>
        <span th:text="${item.lineTotalText}">100,000 VND</span>
      </li>
    </ul>
    <p th:unless="${items != null and !#lists.isEmpty(items)}">
      Product details will be updated in your order.
    </p>
  </section>

  <p>
    Total:
    <strong th:text="${totalText}">100,000 VND</strong>
  </p>

  <p th:if="${trackingUrl != null and !#strings.isEmpty(trackingUrl)}">
    <a th:href="${trackingUrl}">Track order</a>
  </p>
</body>
</html>
~~~

The template above illustrates these behaviors:

- Customer name falls back to "there" if the variable has no value.
- Delivery address and order time appear only when content exists.
- Product list is iterated when non-null and non-empty.
- When there are no items, the email displays a fallback sentence.
- Tracking link appears only when a URL exists.
- Displayed values use **th:text**, escaping HTML content instead of inserting dynamic data as raw markup.

**Order number and total amount are required data** in the example. Do not use dummy fallbacks like `ORD-001` or `100,000 VND` in real emails if source data is missing. Values between tags are only preview placeholder content when Thymeleaf attributes are not processed; the renderer must validate required fields before sending.

`th:href` takes a dynamic URL value. If the URL can originate from a user or untrusted source, validate scheme/host against application policy before passing it into the template. HTML escaping does not automatically guarantee a safe URL.

## 5. Configuring the Thymeleaf Renderer with UTF-8

Spring Framework Mail does not mandate a specific template engine. You can use Thymeleaf, FreeMarker, Mustache, or a custom renderer. The example below picks **Thymeleaf** to illustrate passing models and testing conditional branches.

A template resolver needs to know the resource location, file extension, template mode, and charset:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;
import org.thymeleaf.templatemode.TemplateMode;

@Configuration
public class MailTemplateConfiguration {

    @Bean
    ClassLoaderTemplateResolver mailTemplateResolver() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);
        resolver.setCheckExistence(true);
        return resolver;
    }

    @Bean
    SpringTemplateEngine mailTemplateEngine(
            ClassLoaderTemplateResolver mailTemplateResolver) {
        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(mailTemplateResolver);
        return engine;
    }
}
~~~

This example creates a resolver for mail templates located in **classpath:/templates/**. `setCacheable(false)` is convenient during development and testing so templates are re-read; production can enable caching depending on how resources are deployed and updated. If the application already uses Thymeleaf auto-configuration, avoid registering overlapping resolvers or unintentionally altering the web template resolver. You can use a separate engine/resolver configuration for mail or configure an explicit resolver order.

The path **mail/order-confirmation** passed to `process(...)` has its prefix and suffix prepended/appended by the resolver to locate **templates/mail/order-confirmation.html**.

### Renderer Building Context from Model

~~~java
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class OrderConfirmationTemplateRenderer {
    private final SpringTemplateEngine templateEngine;

    public OrderConfirmationTemplateRenderer(
            SpringTemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public String render(
            OrderConfirmationModel model,
            Locale locale) {
        validateRequiredFields(model);

        Context context = new Context(locale);
        context.setVariable("orderNumber", model.orderNumber());
        context.setVariable("customerName", model.customerName());
        context.setVariable("deliveryAddress", model.deliveryAddress());
        context.setVariable("items", model.items());
        context.setVariable("trackingUrl", model.trackingUrl());
        context.setVariable("placedAtText", model.placedAtText());
        context.setVariable("totalText", model.totalText());

        return templateEngine.process(
                "mail/order-confirmation", context);
    }

    private static void validateRequiredFields(
            OrderConfirmationModel model) {
        if (model == null) {
            throw new IllegalArgumentException(
                    "Order confirmation model is required");
        }
        if (model.orderNumber() == null
                || model.orderNumber().isBlank()) {
            throw new IllegalArgumentException(
                    "Order number is required");
        }
        if (model.totalText() == null || model.totalText().isBlank()) {
            throw new IllegalArgumentException(
                    "Order total is required");
        }
    }
}
~~~

Here `orderNumber` and `totalText` are required; `customerName`, `deliveryAddress`, `items`, `trackingUrl`, and `placedAtText` are handled by the template under optional rules. If the business contract differs, update the validator and template together. Never mark a field as required in the service while silently keeping a dummy fallback in the template.

If the project uses **Thymeleaf 3.1 + Spring 6**, `org.thymeleaf.spring6.SpringTemplateEngine` is the Spring 6 adapter. With Spring 5, the integration package and dependencies differ; use the Thymeleaf version matching your actual Spring version.
## 6. Writing Tests for Complete Data

Complete-data tests prove the template can display all key content when every required field has a value. The dataset should resemble real situations, not just short strings like "A", "B", "C".

Fixture example:

~~~java
import java.util.List;

final class OrderMailFixtures {
    private OrderMailFixtures() {
    }

    static OrderConfirmationModel completeOrder() {
        return new OrderConfirmationModel(
                "ORD-2026-00125",
                "Nguyễn Minh Anh",
                "12 Nguyễn Huệ, Quận 1, TP. Hồ Chí Minh",
                List.of(
                        new OrderLineModel(
                                "Mechanical keyboard white",
                                "1",
                                "1.250.000 ₫"),
                        new OrderLineModel(
                                "Wireless mouse",
                                "2",
                                "980.000 ₫")),
                "https://shop.example.test/orders/ORD-2026-00125",
                "12/11/2026 09:30",
                "2.230.000 ₫");
    }
}
~~~

The fixture data includes Vietnamese text, punctuation, currency, multiple products, and a URL. It helps catch encoding errors, list iteration, and rendering of fields longer than simple placeholders.

A test with **JUnit Jupiter** and **AssertJ**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderConfirmationTemplateRendererTest {
    private OrderConfirmationTemplateRenderer renderer;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);

        renderer = new OrderConfirmationTemplateRenderer(engine);
    }

    @Test
    void rendersCompleteOrderData() {
        String html = renderer.render(
                OrderMailFixtures.completeOrder(),
                Locale.forLanguageTag("vi-VN"));

        assertThat(html)
                .contains("Nguyễn Minh Anh")
                .contains("ORD-2026-00125")
                .contains("12 Nguyễn Huệ")
                .contains("Mechanical keyboard white")
                .contains("Wireless mouse")
                .contains("1.250.000 ₫")
                .contains("2.230.000 ₫")
                .contains("12/11/2026 09:30")
                .contains("Track order")
                .contains("https://shop.example.test/orders/ORD-2026-00125");
    }
}
~~~

The test assumes the template file is packaged on the test classpath at **src/main/resources/templates/mail/order-confirmation.html**. The resolver in the test uses the matching prefix and suffix. If the template resides in `src/test/resources` or has another name, adjust the resolver/resource path accordingly.

This test only constructs `SpringTemplateEngine` and the renderer; **it does not start SMTP, does not need `JavaMailSender`, and does not send real emails**. This is a unit test for rendering. When using Spring Boot's Thymeleaf auto-configuration, you can inject the configured engine, provided you ensure the test uses the right resolver for mail.

### Verifying Content Regions by Meaning

Instead of merely asserting the whole HTML is non-empty, verify:

- The order number appears once or the exact number of times designed.
- Each product line appears, in order if ordering is required.
- Total amount and date/time are formatted.
- The link has the exact prepared URL.
- The customer name is inserted into the greeting position.
- Sample placeholders such as "ORD-001" do not appear when real content should use model data.

You can verify specific content:

~~~java
assertThat(html).contains("Mechanical keyboard white");
assertThat(html).contains("Wireless mouse");
assertThat(html).doesNotContain("Product name");
~~~

There is no need to assert every whitespace or newline in HTML if those are not part of the template contract. Assertions should focus on meaningful content and structure.

## 7. Testing When Optional Fields Are Missing

This is an important test group because real data is often not as complete as an ideal fixture. For example, the model has a valid order number and total, yet lacks customer name, address, order time, tracking URL, or product list.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Locale;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderConfirmationMissingDataTest {
    private OrderConfirmationTemplateRenderer renderer;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        renderer = new OrderConfirmationTemplateRenderer(engine);
    }

    @Test
    void rendersFallbackAndHidesOptionalSections() {
        OrderConfirmationModel model = new OrderConfirmationModel(
                "ORD-2026-00999",
                null,
                null,
                List.of(),
                null,
                null,
                "450.000 ₫");

        String html = renderer.render(
                model, Locale.forLanguageTag("vi-VN"));

        assertThat(html)
                .contains("Hello")
                .contains(">there</strong>")
                .contains("ORD-2026-00999")
                .contains("450.000 ₫")
                .contains("Product details will be updated")
                .doesNotContain("Delivery Address")
                .doesNotContain("Order time:")
                .doesNotContain("Track order")
                .doesNotContain("null");
    }
}
~~~

Expected outcomes:

- Greeting uses fallback "there".
- Delivery address does not appear.
- Order time does not appear.
- Empty product list is replaced by an appropriate message.
- The string "null" does not appear in recipient content.
- Order number and total still appear because they are required fields.

### Testing Null Lists and Empty Lists

**null** and **empty list** are two distinct states in Java. Templates must be designed under a clear contract. If both mean "no product lines to display," test both:

~~~java
@Test
void handlesNullItemList() {
    OrderConfirmationModel model = new OrderConfirmationModel(
            "ORD-2026-01000",
            "Customer",
            null,
            null,
            null,
            null,
            "0 ₫");

    String html = renderer.render(model, Locale.forLanguageTag("vi-VN"));

    assertThat(html)
            .contains("Product details will be updated")
            .doesNotContain("Product name");
}
~~~

If null `items` is an invalid domain data state, **validate and reject** instead of treating it like an empty list. This decision belongs to the model's contract, not something tests should guess.

### Testing Empty and Whitespace-Only Strings

Templates using **#strings.isEmpty(...)** can distinguish empty strings per library rules, yet whitespace-only strings may still count as having content. If blank must be treated as missing, normalize data at the application layer:

~~~java
private static String optionalText(String value) {
    if (value == null || value.isBlank()) {
        return null;
    }
    return value.trim();
}
~~~

Then pass the normalized value to the template. Testing **null**, empty strings, whitespace-only strings, and strings with content separately prevents emails from showing a section containing only whitespace.

## 8. Testing Missing or Invalid Required Data

For required fields, the right behavior is usually **stopping before rendering**, rather than letting the template render null, empty strings, or dummy placeholders.

Example checking order number:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Locale;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderConfirmationRequiredDataTest {
    private OrderConfirmationTemplateRenderer renderer;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        renderer = new OrderConfirmationTemplateRenderer(engine);
    }

    @Test
    void rejectsMissingOrderNumber() {
        OrderConfirmationModel model = new OrderConfirmationModel(
                null,
                "Alice Nguyen",
                null,
                List.of(),
                null,
                null,
                "100.000 ₫");

        assertThatThrownBy(() ->
                renderer.render(model, Locale.forLanguageTag("vi-VN")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Order number is required");
    }

    @Test
    void rejectsBlankTotal() {
        OrderConfirmationModel model = new OrderConfirmationModel(
                "ORD-2026-001",
                "Alice Nguyen",
                null,
                List.of(),
                null,
                null,
                "   ");

        assertThatThrownBy(() ->
                renderer.render(model, Locale.forLanguageTag("vi-VN")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Order total is required");
    }
}
~~~

Tests must prove the error occurs **before SMTP sending**. If the renderer only creates an HTML string, throwing `IllegalArgumentException` fits the example. A system may use Bean Validation and a specialized exception; what matters is not sending emails with insufficient data.

Fields may be required in one email type yet optional in another. Do not build one overly broad validator and impose the same rules on every template. Define models and validation per email use case.
## 9. Testing HTML Escaping with Untrusted Data

Email templates often insert customer names, product names, or user-entered notes. With **th:text**, Thymeleaf escapes content so special characters render as text. With **th:utext**, content is inserted into HTML as markup and can create vulnerabilities if data is uncontrolled.

Example test with customer name containing HTML:

~~~java
@Test
void escapesCustomerNameInsteadOfRenderingMarkup() {
    OrderConfirmationModel model = new OrderConfirmationModel(
            "ORD-2026-02000",
            "<img src=x onerror=alert(1)> & guest",
            null,
            List.of(),
            null,
            null,
            "100.000 ₫");

    String html = renderer.render(model, Locale.forLanguageTag("vi-VN"));

    assertThat(html)
            .contains("&lt;img")
            .contains("&amp; guest")
            .doesNotContain("<img src=x");
}
~~~

This test proves data is displayed as text in HTML. Do not merely check whether the raw string appears, because escaped output may represent content using entities such as **&lt;** and **&amp;**.

### Do Not Use th:utext for Arbitrary User Data

~~~html
<!-- Safer for ordinary text: -->
<span th:text="${customerName}">Customer</span>

<!-- Only use when value is trusted and controlled HTML: -->
<div th:utext="${trustedHtmlFragment}"></div>
~~~

**th:utext** does not escape markup. Only use it when HTML content is generated by a trusted source or has passed through a context-appropriate sanitizer. Having valid UTF-8 data does not make it safe when inserted into HTML.

### URLs Need Separate Policy

HTML attribute escaping does not equate to URL validation. If `trackingUrl` can be controlled by users, verify allowed schemes/hosts, such as accepting only HTTPS and the system's domain. Tests should cover:

- HTTPS URLs on valid domains are displayed.
- Null or empty URLs hide the link.
- Disallowed schemes such as `javascript:` are rejected before rendering or mail creation.
- URLs with special query characters are encoded properly.

Do not merely assert that the template throws no exception when receiving an arbitrary URL.

## 10. Testing Lists with Complete Items and Missing Properties

A non-empty list does not guarantee every item is valid. For instance, a product line might have a name yet lack a quantity, or have a quantity yet lack a line price. If those fields are required for recipients to understand the order, validate each item before rendering.

You can add list validation:

~~~java
private static void validateItems(
        java.util.List<OrderLineModel> items) {
    if (items == null) {
        return; // Only valid if null means no list.
    }

    for (int index = 0; index < items.size(); index++) {
        OrderLineModel item = items.get(index);
        if (item == null) {
            throw new IllegalArgumentException(
                    "Order item at index " + index + " is required");
        }
        if (item.name() == null || item.name().isBlank()) {
            throw new IllegalArgumentException(
                    "Order item name is required at index " + index);
        }
        if (item.quantityText() == null
                || item.quantityText().isBlank()) {
            throw new IllegalArgumentException(
                    "Order item quantity is required at index " + index);
        }
        if (item.lineTotalText() == null
                || item.lineTotalText().isBlank()) {
            throw new IllegalArgumentException(
                    "Order item total is required at index " + index);
        }
    }
}
~~~

Then call `validateItems` during model validation before rendering. The rule above is an example for order confirmation emails; if business rules allow some values to be absent, adjust the contract rather than applying rigid validation.

Testing an item missing its name:

~~~java
@Test
void rejectsAnItemWithoutName() {
    OrderConfirmationModel model = new OrderConfirmationModel(
            "ORD-2026-02001",
            "Alice Nguyen",
            null,
            List.of(new OrderLineModel(null, "1", "50.000 ₫")),
            null,
            null,
            "50.000 ₫");

    assertThatThrownBy(() ->
            renderer.render(model, Locale.forLanguageTag("vi-VN")))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Order item name is required");
}
~~~

If the template is designed to display lines missing a field with a placeholder like "Updating," tests must assert that exact behavior. Never let that case accidentally turn into the string "null" or a confusing blank row.

### Checking Item Count

For an order with many lines, you can verify the rendered item count:

~~~java
long renderedItems = java.util.regex.Pattern
        .compile("<li>")
        .matcher(html)
        .results()
        .count();

assertThat(renderedItems).isEqualTo(2);
~~~

Counting HTML tags with regex only fits simple templates with stable markup. If HTML structure is complex or has nested `li` tags, use an HTML parser to query the DOM by selector and count exact elements belonging to the product list.

## 11. Testing Locale, Date/Time, and Currency

Email templates can be sent to users in multiple languages. Rendering the same model with different locales can change:

- Subject and labels such as "Mã đơn hàng" and "Order number."
- Date and time formatting.
- Thousands/decimal separators.
- Currency symbols and placement.
- Pluralization or greetings.

**Do not rely on the JVM's default locale** because developer, CI, and production environments may differ. Pass `Locale` explicitly to the renderer and verify results for each supported locale.

Example formatting monetary amounts before passing to the template:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public final class MoneyTextFormatter {
    private MoneyTextFormatter() {
    }

    public static String formatVnd(BigDecimal amount, Locale locale) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(java.util.Currency.getInstance("VND"));
        return formatter.format(amount);
    }
}
~~~

Exact output depends on the locale provider/JDK and currency conventions. For systems needing strictly deterministic formatting, specify scale, separators, and currency symbols by product policy rather than relying on environment defaults.

Tests can verify supported locales:

~~~java
@Test
void rendersVietnameseAndEnglishLabels() {
    OrderConfirmationModel model = OrderMailFixtures.completeOrder();

    String vietnamese = renderer.render(
            model, Locale.forLanguageTag("vi-VN"));
    String english = renderer.render(
            model, Locale.forLanguageTag("en-US"));

    assertThat(vietnamese).contains("Mã đơn hàng");
    assertThat(english).contains("Order number");
}
~~~

This test assumes the template uses a message bundle for labels instead of hardcoding Vietnamese like the illustrative template above. When implementing i18n, separate template message keys from static content and provide corresponding resource files.

### Using MessageSource for Subject and Labels

The subject is usually generated separately from the HTML body. You can use Spring **MessageSource** to fetch the subject by locale:

~~~properties
# messages_vi.properties
mail.order-confirmation.subject=Xác nhận đơn hàng {0}
~~~

~~~properties
# messages_en.properties
mail.order-confirmation.subject=Order confirmation {0}
~~~

~~~java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Component;

@Component
public class MailSubjectFactory {
    private final MessageSource messageSource;

    public MailSubjectFactory(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String orderConfirmation(String orderNumber, Locale locale) {
        return messageSource.getMessage(
                "mail.order-confirmation.subject",
                new Object[] {orderNumber},
                locale);
    }
}
~~~

Test the subject factory separately to ensure message keys have complete translations, placeholders substitute properly, and locale fallback follows policy. When building `MimeMessage`, pass Unicode strings to `setSubject`; Jakarta Mail handles MIME header encoding.

## 12. Checking Subject, Text Body, and HTML Body Together

A complete email may contain:

- Subject generated by `MessageSource` or a subject factory.
- `text/plain` body for clients that do not render HTML.
- `text/html` body for clients supporting HTML.
- Attachments or inline resources if needed.

Do not only test the HTML template and assume subject and `text/plain` are automatically right. Verify each part at its respective boundary.

Example building a MIME message from subject and rendered content:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderConfirmationMailComposer {
    private final JavaMailSender sender;
    private final OrderConfirmationTemplateRenderer renderer;
    private final MailSubjectFactory subjects;

    public OrderConfirmationMailComposer(
            JavaMailSender sender,
            OrderConfirmationTemplateRenderer renderer,
            MailSubjectFactory subjects) {
        this.sender = sender;
        this.renderer = renderer;
        this.subjects = subjects;
    }

    public MimeMessage compose(
            OrderConfirmationModel model,
            String recipient,
            Locale locale) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject(subjects.orderConfirmation(
                model.orderNumber(), locale));

        String plain = "Order " + model.orderNumber()
                + " has been confirmed.";
        String html = renderer.render(model, locale);
        helper.setText(plain, html);
        return message;
    }
}
~~~

This is an illustrative composer. In a real application, plain text should come from a separate template or the same model/template abstraction to keep text and HTML from drifting apart. The `compose` method **only builds `MimeMessage`** and does not send SMTP; calling `sender.send(message)` can live in a separate adapter.

With `multipart/alternative`, tests can parse the serialized message and verify both parts:

~~~java
MimeMessage message = composer.compose(
        OrderMailFixtures.completeOrder(),
        "alice@example.test",
        Locale.forLanguageTag("vi-VN"));

message.saveChanges();
Object content = message.getContent();

// For multipart/alternative, traverse BodyParts and check
// text/plain and text/html after Jakarta Mail decodes them.
~~~

Because MIME structure can nest multiple multiparts, tests should locate parts by **Content-Type** rather than assuming a fixed index position.
## 13. Case Where a Variable Is Not Passed into Context

Two situations are easily conflated:

1. The model has a property whose value is **null**.
2. The template renderer **did not put that variable** into the Context.

Depending on the template engine and how expressions are written, a nonexistent variable may be treated as null, evaluate to an empty string, or raise an error when accessing sub-properties. Do not rely on this implicit behavior to guard required data.

Example with Thymeleaf:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("orderNumber", "ORD-001");
// Intentionally omit customerName.

String html = templateEngine.process(
        "mail/order-confirmation", context);
~~~

The template may render an empty customer name or a fallback depending on the expression. If a field is required, **validate the model before calling `process(...)`**. If a field is optional, the template must clearly express hide/fallback rules and test that behavior.

### Do Not Use Template Errors to Replace Validation

An expression such as:

~~~html
<span th:text="${order.customer.name}"></span>
~~~

can cause issues if `order` or `customer` does not exist. If this is required data, the application service should construct a valid model or throw a specific business error before rendering. If `customer` is optional, check explicitly:

~~~html
<span th:if="${order != null and order.customer != null}"
      th:text="${order.customer.name}">Customer</span>
~~~

In a better design, templates do not receive a deep domain object with many nullable relationships. Create a **flat view model** containing only the fields needed for display, reducing the risk of accessing lazy properties or depending on entity structure.

## 14. What Cases Should a Test Dataset Cover?

A practical matrix can be organized by group:

| Dataset | Example | Expectation |
|---|---|---|
| **Complete** | Name, address, items, URL, time, total all present | All sections render properly |
| **Missing optional** | Name null, no address, URL null | Fallback/hide sections per design |
| **Empty collection** | `items` is an empty list | Empty state appears, no item rows |
| **Null collection** | `items` is null | Per chosen contract: empty state or validation error |
| **Blank text** | Address is whitespace-only string | Normalize to null or hide section |
| **Missing required** | `orderNumber` null/blank, `total` null | Rendering rejected before creating email |
| **Invalid item** | `item` null or missing name/quantity | Validation error or defined placeholder |
| **Unicode** | Vietnamese names, accented characters, emoji | Content preserved accurately after rendering |
| **HTML special characters** | Name contains `<`, `>`, `&`, quotes | Escaped in text nodes |
| **Invalid URL** | Disallowed scheme | Rejected before rendering or sending |
| **Boundary values** | Very long name, large list, hyphenated codes | Does not break layout or exceed defined limits |
| **Multiple locales** | `vi-VN` and `en-US` | Labels, subject, dates/money match locale |

You do not need a separate test for every combination of every field. Prioritize cases with conditional branches, validation rules, or direct impact on recipient information. Combinations can be organized using **parameterized tests** when they share one expectation.
### Parameterized Test for Optional Strings

Example verifying null, empty, and blank addresses are all hidden after normalization:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class OptionalAddressTemplateTest {
    static Stream<String> missingAddresses() {
        return Stream.of(null, "", "   ");
    }

    @ParameterizedTest
    @MethodSource("missingAddresses")
    void hidesAddressWhenItIsMissing(String address) {
        OrderConfirmationModel model = new OrderConfirmationModel(
                "ORD-2026-03000",
                "Alice Nguyen",
                optionalText(address),
                List.of(),
                null,
                null,
                "200.000 ₫");

        String html = renderer.render(
                model, Locale.forLanguageTag("vi-VN"));

        assertThat(html).doesNotContain("Delivery Address");
    }
}
~~~

In the example, **renderer** is an instance configured in the test class setup and **optionalText** is the normalization helper from earlier. The stream supplies missing-data scenarios so the same assertion runs on each. If you prefer not to normalize upfront, write a template condition checking blank per your template engine and test that behavior directly.

## 15. Testing Templates in a Spring Test Context

If the template engine is configured as a Spring bean and the renderer uses dependency injection, you can use **@SpringBootTest** to verify wiring and resource resolution:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MailTemplateSpringContextTest {
    @Autowired
    private OrderConfirmationTemplateRenderer renderer;

    @Test
    void rendersTemplateFromApplicationClasspath() {
        String html = renderer.render(
                OrderMailFixtures.completeOrder(),
                Locale.forLanguageTag("vi-VN"));

        assertThat(html)
                .contains("ORD-2026-00125")
                .contains("Nguyễn Minh Anh");
    }
}
~~~

This test verifies **Spring wiring, template resolvers, and resources packaged on the application classpath**. If the application also auto-configures `JavaMailSender` and mail bean conditions are enabled, the context may need an appropriate SMTP host configuration or a mocked sender. However, renderer tests should not call `send()`.

If the goal is solely rendering templates, **@SpringBootTest is not needed**. Constructing the engine/resolver directly as in previous tests is usually faster and better isolated. Use a Spring context when you want to verify the exact resolver/bean configuration the application actually uses.

### Test Slices and Mocked Senders

An MVC test does not need to initialize SMTP to verify a controller calls an application service. An application service test can mock **MailPort**. A renderer test can instantiate Thymeleaf standalone. Mocking **JavaMailSender** only makes sense when testing the component actually calling the sender.

Never add real SMTP credentials into test properties. Never let a test profile accidentally inherit production hosts from developer machines or CI configuration. If tests need the SMTP protocol, use a dedicated SMTP test server and dummy data.

## 16. Distinguishing Template Errors from Mail-Sending Errors

Template renderers and `JavaMailSender` can fail at different times:

| Error | Stage | How to Handle |
|---|---|---|
| Template does not exist | Resolve template | Check name, prefix/suffix, and resource packaging |
| Missing required variable | Validate model or render | Supply missing data or reject request |
| Expression/loop error | Render template | Check property path and data types |
| Encoding/template resource error | Read template or create MIME | Check file and resolver charset |
| MIME preparation error | Create `MimeMessage` | Check subject, body, attachments, addresses |
| SMTP AUTH/connectivity error | Transport send | Check host, port, TLS, credentials, and network |
| SMTP rejects message | SMTP transaction | Read response code, quota, size, and recipient policy |

One way to organize results:

~~~text
PENDING
  |
  v
MODEL_VALIDATED
  |
  v
TEMPLATE_RENDERED
  |
  v
MIME_COMPOSED
  |
  v
SMTP_SUBMITTING
  |
  +--> SMTP_ACCEPTED
  |
  +--> SUBMISSION_FAILED
  |
  +--> SUBMISSION_UNKNOWN
~~~

Status names are business suggestions, not a built-in Spring enum. Separating statuses helps log and retry at the right place. If template rendering fails, retrying SMTP will not solve it. If SMTP times out after sending DATA, re-rendering will not resolve uncertainty about whether the server already accepted the message.

### Do Not Catch Exceptions and Send Emails Missing Content

Do not do this:

~~~java
String html;
try {
    html = renderer.render(model, locale);
} catch (Exception ex) {
    html = "<p>Hello</p>"; // Generic fallback can mask data errors.
}
mailSender.send(buildMessage(html));
~~~

This can turn a template error into an email missing information, misleading recipients. If a fallback exists, the fallback must be **a separately designed and tested template**, not an arbitrary HTML string in a catch block. For critical emails, it is usually best to stop, record the rendering error, and move the request to a state requiring attention.
## 17. Checking Subject and Separate Text Templates

The subject usually does not live inside the HTML body file. If using **MessageSource**, the subject is content that must be tested separately by locale and substitution data.

Example with a Vietnamese subject:

~~~properties
# messages_vi.properties
mail.order-confirmation.subject=Xác nhận đơn hàng {0}
~~~

Testing the subject factory:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.ResourceBundleMessageSource;

class MailSubjectFactoryTest {
    @Test
    void resolvesVietnameseSubject() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");

        MailSubjectFactory factory = new MailSubjectFactory(source);
        String subject = factory.orderConfirmation(
                "ORD-2026-00125", Locale.forLanguageTag("vi"));

        assertThat(subject)
                .isEqualTo("Xác nhận đơn hàng ORD-2026-00125");
    }
}
~~~

The example assumes **messages_vi.properties** sits at the classpath root and contains the right message key. In a Spring Boot application, `MessageSource` may be auto-configured; testing `ResourceBundleMessageSource` directly isolates bundle lookup. Align the basename and filenames with your actual configuration.

If the subject contains user data, do not concatenate uncontrolled content directly into headers. Validate length, strip CR/LF per policy, and pass Unicode strings via `setSubject` so Jakarta Mail handles MIME header encoding.

### If Body Has Both Text and HTML Templates

Some applications use two separate files:

~~~text
templates/mail/order-confirmation.txt
templates/mail/order-confirmation.html
~~~

Test two separate renderers or an **EmailContentRenderer** returning a text/html pair. Tests must ensure both versions contain the same critical business data: order number, total amount, and support info. Both versions do not have to use identical phrasing, yet must not contradict each other.

## 18. Checking MIME After Rendering Templates

After templates render, applications usually pass HTML to **MimeMessageHelper**. You can test the MIME assembly step independently without opening an SMTP connection:

1. Create a `MimeMessage` using a Jakarta Mail `Session` in tests.
2. Set Subject, `text/plain`, and HTML body.
3. Call `saveChanges()` and serialize via `writeTo(...)`.
4. Parse the message back from bytes.
5. Read MIME parts by `Content-Type` and assert decoded content.

Example creating a message:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.springframework.mail.javamail.MimeMessageHelper;

Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, StandardCharsets.UTF_8.name());

helper.setSubject("Xác nhận đơn hàng ORD-001");
helper.setText(
        "Đơn hàng ORD-001 đã được xác nhận.",
        "<html lang=\"vi\"><body><p>Đơn hàng "
                + "<strong>ORD-001</strong> đã được xác nhận.</p>"
                + "</body></html>");

message.saveChanges();
~~~

MIME tests can verify:

- Subject after re-parsing remains the exact Unicode string.
- Message is multipart when `text/plain` and `text/html` are needed.
- Both `text/plain` and `text/html` parts exist.
- Decoded body contains order number, customer name, and expected content.
- Charset of text parts matches UTF-8.

If a message contains attachments or inline images, MIME may have multiple nested layers. Traverse the multipart tree recursively and locate parts by media type, rather than assuming HTML is always at the first or last position.

**MIME tests do not send mail.** Only when verifying SMTP handshake, AUTH, STARTTLS, or server responses is an SMTP test server needed. This separation pinpoints errors at the right layer and prevents template tests from depending on the network.

## 19. Anti-Patterns When Testing Templates

### Testing Only with Perfect Data

With only one complete fixture, tests fail to catch empty sections, wrong fallbacks, or errors when lists have no elements. Have at least one **complete** case, one **missing optional** case, and **invalid required** cases.

### Using Dummy Placeholders as Production Data

If the template pre-populates "ORD-001", "Customer name", or "100,000 VND" and someone forgets to substitute a variable, the email may contain sample copy. Tests should assert real data appears and sample placeholders no longer appear in dynamic positions.

### Asserting Only That HTML Is Non-Empty

A template can render thousands of characters yet miss the order number, have the wrong recipient name, or omit products. Assert key content and display conditions.

### Checking Only for the String "null"

Absence of the word "null" is necessary but not sufficient. A section can still exist with empty content, stray separators, or an unnatural greeting. Check both **content** and **presence/absence of sections**.

### Overly Rigid Whole-HTML Snapshot Comparisons

Full snapshots can be useful when templates are UIs needing strict markup control, yet break easily on whitespace changes, attribute ordering, or formatting that does not affect content. For typical email templates, prefer DOM/selector checks or meaningful content assertions. Use snapshots when the team genuinely wants to review every template change.

### Checking Content While Ignoring Escaping

User names can contain HTML or special characters. Normal-data tests do not catch unsafe use of `th:utext`. Add cases containing `<`, `>`, `&` and verify output is escaped.

### Using Production SMTP in Tests

Tests can send real emails to users, hit quotas, fail on flaky networks, or alter external system state. Template tests should run standalone. SMTP integration tests use a test server/sandbox and dummy data.

### Sharing Mutable Fixtures

If tests mutate a shared List or model across tests, execution order can vary results. Use a factory creating a fresh model per test; collections should be immutable or unmutated after construction.

### Skipping Nested Items Missing Fields

A list with two items does not mean both items are valid. Tests must cover null items, empty names, missing quantities, and fields required by business logic.

### Ignoring Locales

Tests that pass only on a developer's default locale may format dates/money differently in production. Pass `Locale` explicitly and test supported locales.

## 20. Process for Building a Test Suite for an Email Template

A maintainable workflow:

1. **Define the model**: list required, optional, default, collection, and sensitive fields.
2. **Normalize data**: trim strings, format dates/money, and validate URLs/recipients at the appropriate layer.
3. **Write the template**: use conditionals for optional fields, empty states for collections, meaningful fallbacks, and default escaping for text.
4. **Test full fixture**: verify all data and repeated lines appear.
5. **Test missing optional**: null, empty, blank, and empty/null collections per contract.
6. **Test missing required**: renderer or application service rejects before creating email.
7. **Test special data**: Unicode, HTML characters, URLs, long values, and locales.
8. **Test subject/text/html**: verify all parts of the email describe the same business event.
9. **Test MIME composition**: inspect Content-Type, charset, and re-parsed body if needed.
10. **SMTP integration tests**: run only when protocol/transport checks are needed, using a test server.

A test matrix can be stored as documentation beside the template:

| Case ID | Dataset | Expected Result |
|---|---|---|
| TC-01 | Full order | Full name, address, items, URL, and total amount |
| TC-02 | Customer name null | Uses default greeting |
| TC-03 | Address null/blank | Hides address section |
| TC-04 | Items empty | Displays empty state |
| TC-05 | Items null | Per chosen contract: empty state or validation error |
| TC-06 | Order number blank | Rejects rendering |
| TC-07 | Total missing | Rejects rendering |
| TC-08 | Customer name contains HTML | Escaped as text, no markup rendered |
| TC-09 | Tracking URL wrong scheme | Rejected before sending |
| TC-10 | Locale vi/en | Appropriate labels and formatting |
| TC-11 | Subject/body MIME | Unicode content preserved after round-trip |

Not every email needs exactly eleven test cases. The table is a pattern to identify risks and pick cases matching each template's data contract.

## 21. Integrating with the Mail Service Without Mixing Responsibilities

Once templates are rendered and tested independently, the mail service can coordinate the renderer and sender:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailService {
    private final JavaMailSender sender;
    private final OrderConfirmationTemplateRenderer renderer;
    private final MailSubjectFactory subjectFactory;

    public OrderConfirmationMailService(
            JavaMailSender sender,
            OrderConfirmationTemplateRenderer renderer,
            MailSubjectFactory subjectFactory) {
        this.sender = sender;
        this.renderer = renderer;
        this.subjectFactory = subjectFactory;
    }

    public void send(
            OrderConfirmationModel model,
            String recipient,
            Locale locale) throws MessagingException {

        String html = renderer.render(model, locale);
        String subject = subjectFactory.orderConfirmation(
                model.orderNumber(), locale);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(html, true);

        sender.send(message);
    }
}
~~~

This is a synchronous HTML sending example. In systems needing `text/plain` too, you can render two templates and call the `setText(plain, html)` overload. If sending post-transaction or via an outbox, the worker calls this service/adapter after claiming a job. Regardless of dispatch method, **the renderer can still be tested independently without calling `JavaMailSender`**.

One note on errors: if rendering fails, no SMTP submission has happened yet. If MIME creation fails, there is no valid message to send. If send fails, classify transport errors and SMTP status; do not lump everything under "template error."

## 22. Principles to Remember

**Complete data** tests that the template can display all information. **Missing data** tests that the email stays meaningful when optional information is absent. **Invalid required data** must be rejected before creating the email. These are three distinct groups and must be tested explicitly.

With Spring Framework Mail, you can use Thymeleaf or another template engine to render HTML, then pass the result to `MimeMessageHelper` and `JavaMailSender`. Test the renderer with fixture data without depending on SMTP; inspect MIME separately when needed; and use an SMTP test server only for protocol tests.

A reliable template is one with **a clear data contract**, deliberate handling of null/empty/blank, escaping of untrusted data, sensible empty states, and tests covering both complete and missing cases. That keeps emails accurate and understandable even when real data differs from ideal samples.
