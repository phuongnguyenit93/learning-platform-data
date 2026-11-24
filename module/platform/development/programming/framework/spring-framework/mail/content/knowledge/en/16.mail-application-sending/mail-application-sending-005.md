# Mapping Business Data to a Mail Model

## 1. Why do you need a dedicated mail model?

In an application using **Spring Framework Mail**, the data needed to send an email often comes from many places: orders, user accounts, invoices, appointments, transactions, or business processing results. These objects are designed for business logic and persistence; their structure does not necessarily fit the content of an email.

For example, an order entity might contain:

- Internal IDs and relationships to customers.
- Line items as lazy-loaded collections.
- Payment status, shipping details, and audit fields.
- References to user, address, and payment method entities.
- Internal fields that should not be shown to recipients.

If you pass that entire entity into a template, the email template becomes coupled to the persistence structure and can accidentally access unnecessary data. Changes to the entity or JPA relationships can also break templates.

A cleaner way to organize this is to map business data into a **mail model** (a data model dedicated to emails):

~~~text
Domain / application data
          |
          v
   Mail model mapper
          |
          v
    Mail model (DTO)
          |
          v
    Template renderer
          |
          +--> HTML body
          |
          +--> Plain-text body
          |
          v
    MimeMessageHelper
          |
          v
    JavaMailSender
~~~

The mail model contains only the values the email needs to display or use. As a result:

- Templates do not need to know how entities are stored in the database.
- Data is selected, formatted, and validated before rendering.
- One mail model can serve both HTML and plain text.
- Mapping can be tested without connecting to SMTP.
- Email layout changes have minimal impact on the domain model.

> **Principle:** Map business data into a small, meaningful, and stable structure before rendering the email. Templates receive data prepared for presentation, not the application's entire object graph.

## 2. Distinguishing domain model, mail model, and template context

Three related concepts serve different purposes:

| Component | Responsibility | Example |
| --- | --- | --- |
| **Domain model** | Represents business rules and state | `Order`, `Customer`, `Invoice` |
| **Mail model** | Holds data needed to build a specific email type | `OrderConfirmationMailModel` |
| **Template context/model** | Supplies variables to the template engine | Thymeleaf `Context` with variable `mail` |
| **Rendered content** | Content after template processing | HTML and plain-text strings |
| **MIME message** | Packages content and headers for sending | `MimeMessage` |

Example:

~~~java
// Business data (abbreviated).
public record OrderSummary(
        String orderNumber,
        String customerName,
        BigDecimal totalAmount,
        String currencyCode,
        Instant createdAt) {
}

// Data dedicated solely to the email.
public record OrderConfirmationMailModel(
        String recipientName,
        String orderNumber,
        String orderDate,
        String totalAmount,
        String detailsUrl) {
}
~~~

`OrderSummary` describes a business result. `OrderConfirmationMailModel` already holds presentation-ready strings, such as formatted dates and currency. The template does not have to look up customer details, compute totals, or build URLs itself.

### 2.1. A mail model is not a copy of an entity

Avoid creating an email DTO simply by copying every field from an entity:

~~~java
// Avoid: email model exposing too much persistence data.
public class OrderMailModel {
    private Long id;
    private CustomerEntity customer;
    private List<OrderLineEntity> lines;
    private PaymentEntity payment;
    private String internalNote;
    private String databaseStatus;
    // ...
}
~~~

The template does not need to know about the payment entity or JPA relationships. It usually only needs:

~~~java
public record OrderMailModel(
        String orderNumber,
        String customerDisplayName,
        String paymentStatusLabel,
        String totalDisplay,
        List<OrderLineMailModel> items) {
}
~~~

A mail model should reflect **what the recipient needs to know**, not how the database stores records.

### 2.2. Each email type should have a meaningful model

Avoid using one giant `Map<String, Object>` for every email type with many optional keys:

~~~java
Map<String, Object> model = new HashMap<>();
model.put("name", name);
model.put("order", order);
model.put("invoice", invoice);
model.put("resetToken", token);
model.put("appointment", appointment);
~~~

Different templates may use different keys; typos or missing keys often surface only at render time. Instead, create purpose-specific models:

- `OrderConfirmationMailModel`
- `PasswordResetMailModel`
- `InvoiceReadyMailModel`
- `AppointmentReminderMailModel`

The type name reveals what kind of information the template receives and lets the compiler assist during mapping.

## 3. Identifying required data before writing a mapper

Before writing code, describe what the email must display. For example, an order confirmation email:

| Content in email | Business data source | Mail model should contain |
| --- | --- | --- |
| Recipient name | Customer profile | `recipientName` |
| Order code | Order | `orderNumber` |
| Order date | Order timestamp | Formatted `orderDate` |
| Line items | Order lines | List of `OrderLineMailModel` |
| Total amount | Total computed in business logic | Formatted `totalAmount` |
| Shipping address | Shipping address | `shippingAddressLines` |
| Order link | Trusted base URL + public order ID | Built `detailsUrl` |
| Language | Recipient preference | `Locale` or locale tag |

Include only fields that are actually used. If the template does not need database IDs, internal tokens, operational notes, or sensitive payment info, do not add those fields.

### 3.1. Display data vs. calculated data

Templates should display results already calculated in the business layer. For example, an order total must be calculated per domain/service rules for taxes, discounts, rounding, and currency; the mapper only formats the result.

Do not let the template compute totals itself:

~~~html
<!-- Avoid letting the template compute business totals -->
<span th:text="${order.unitPrice * order.quantity}"></span>
~~~

Instead, the domain/application service calculates the exact value, and then the mapper builds the model:

~~~java
new OrderLineMailModel(
        line.productName(),
        line.quantityLabel(),
        line.lineTotalDisplay());
~~~

This avoids duplicating pricing rules in templates and keeps the same values consistent across emails, web pages, and reports.

## 4. Designing a mail model with Java records

In modern Java, `record` fits data-carrying DTOs well. For example:

~~~java
package com.example.mail.model;

import java.util.List;
import java.util.Locale;

public record OrderConfirmationMailModel(
        String recipientName,
        String orderNumber,
        String orderDate,
        List<OrderLineMailModel> items,
        String totalAmount,
        String shippingAddress,
        String detailsUrl,
        Locale locale) {

    public OrderConfirmationMailModel {
        items = List.copyOf(items);
    }
}
~~~

A line item:

~~~java
package com.example.mail.model;

public record OrderLineMailModel(
        String productName,
        String quantity,
        String lineTotal) {
}
~~~

Notable traits:

- Fields are final by record semantics, matching an immutable model.
- `List.copyOf(...)` creates a list that cannot be modified externally after the model is built.
- Field names carry presentation meaning and do not depend on database column names.
- `detailsUrl` is an already-constructed link, not an entity or a URL concatenated inside the template.
- `locale` specifies the email's language and can be used during message rendering.

If the application runs on a Java version without records, you can write an equivalent immutable DTO class with a constructor and getters.

### 4.1. When should you keep native data types?

Not every field should become a string. You can keep native types when the template or rendering step uses them appropriately:

| Data | Common suitable choice |
| --- | --- |
| Order code | `String` |
| Display name | `String` |
| Quantity | `int` or formatted string depending on template |
| Total amount | `BigDecimal` with currency code, or formatted string |
| Timestamp | `Instant`/`ZonedDateTime` or formatted string |
| List of line items | `List<OrderLineMailModel>` |
| Full URL | Validated `URI` or `String` |
| Locale | `Locale` or locale tag |

If the template only displays dates and currencies, preformatted strings keep the template simple. If the template needs to render values in multiple formats or share one model across multiple channels, keeping `BigDecimal`, `Currency`, and native timestamps can help. What matters is **never letting templates execute complex business rules**.

## 5. Mapper: converting business data to a mail model

A mapper is an intentional conversion component. It takes data fetched from the domain/application layer, selects needed fields, formats them, and returns the mail model.

Example input data for a mapper:

~~~java
package com.example.order;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderMailData(
        String publicOrderId,
        String orderNumber,
        Instant createdAt,
        BigDecimal totalAmount,
        String currencyCode,
        List<OrderLineMailData> lines,
        String shippingAddress) {
}

public record OrderLineMailData(
        String productName,
        int quantity,
        BigDecimal lineTotal) {
}

public record RecipientMailPreferences(
        String displayName,
        String localeTag,
        String zoneId) {
}
~~~

These are projections/data snapshots prepared for the email task, not JPA entities. When fetching from a repository, the application service can create these records inside a transaction and hand them to the mapper once all required data is loaded.

### 5.1. Complete mapper

~~~java
package com.example.mail.mapper;

import java.math.BigDecimal;
import java.net.URI;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import com.example.mail.model.OrderConfirmationMailModel;
import com.example.mail.model.OrderLineMailModel;
import com.example.order.OrderMailData;
import com.example.order.OrderLineMailData;
import com.example.order.RecipientMailPreferences;

@Component
public class OrderConfirmationMailMapper {

    private final String publicBaseUrl;

    public OrderConfirmationMailMapper(
            @Value("${app.public-base-url}") String publicBaseUrl) {
        this.publicBaseUrl = publicBaseUrl;
    }

    public OrderConfirmationMailModel map(
            OrderMailData order,
            RecipientMailPreferences recipient) {

        Locale locale = Locale.forLanguageTag(recipient.localeTag());
        ZoneId zone = ZoneId.of(recipient.zoneId());

        String orderDate = formatDate(order.createdAt(), zone, locale);
        String totalAmount = formatMoney(
                order.totalAmount(), order.currencyCode(), locale);

        List<OrderLineMailModel> items = order.lines().stream()
                .map(line -> mapLine(line, order.currencyCode(), locale))
                .toList();

        String detailsUrl = buildDetailsUrl(order.publicOrderId());

        return new OrderConfirmationMailModel(
                recipient.displayName(),
                order.orderNumber(),
                orderDate,
                items,
                totalAmount,
                order.shippingAddress(),
                detailsUrl,
                locale);
    }

    private OrderLineMailModel mapLine(
            OrderLineMailData line,
            String currencyCode,
            Locale locale) {

        return new OrderLineMailModel(
                line.productName(),
                Integer.toString(line.quantity()),
                formatMoney(line.lineTotal(), currencyCode, locale));
    }

    private String formatDate(
            Instant instant,
            ZoneId zone,
            Locale locale) {

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale)
                        .withZone(zone);

        return formatter.format(instant);
    }

    private String formatMoney(
            BigDecimal amount,
            String currencyCode,
            Locale locale) {

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(Currency.getInstance(currencyCode));
        return formatter.format(amount);
    }

    private String buildDetailsUrl(String publicOrderId) {
        URI uri = UriComponentsBuilder
                .fromUriString(publicBaseUrl)
                .pathSegment("orders", "{orderId}")
                .encode()
                .buildAndExpand(Map.of("orderId", publicOrderId))
                .toUri();

        return uri.toASCIIString();
    }
}
~~~

This snippet illustrates Java 17 or later because it uses records and `Stream.toList()`. The records and imports must reside in their respective Java files. `app.public-base-url` must be a trusted application setting, such as the official customer portal domain.

The mapper performs these steps:

1. Selects `Locale` and `ZoneId` according to the recipient.
2. Formats timestamps according to language and time zone.
3. Formats currency according to locale and currency code.
4. Converts each order line to an email-specific DTO.
5. Builds the URL from a trusted base URL and URI-component-encoded public ID.
6. Returns an immutable model.

### 5.2. The mapper should not contain domain calculation rules

The example above receives `totalAmount` and `lineTotal` already determined by the business layer. The mapper only formats them. If the total requires vouchers, taxes, or rounding rules, let the domain/application service compute them first.

Nor should the mapper decide which orders are allowed to send, who is a valid recipient, or whether a transaction is complete. Those decisions belong to the use case/application service.

## 6. Putting the mail model into the Thymeleaf context

Once the mapper returns the mail model, the next step is passing it to the template engine. With Thymeleaf, you can use `org.thymeleaf.context.Context`:

~~~java
import org.thymeleaf.context.Context;

Context context = new Context(model.locale());
context.setVariable("mail", model);

String html = templateEngine.process(
        "mail/order-confirmation",
        context);
~~~

The template receives a variable named `mail`. Fields in the model are accessed using property expressions:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Order confirmed</h1>
  <p>
    Hello
    <strong th:text="${mail.recipientName}">customer</strong>,
  </p>
  <p>
    Order code:
    <strong th:text="${mail.orderNumber}">ORD-0001</strong>
  </p>
  <p>
    Order date:
    <span th:text="${mail.orderDate}">January 01, 2026</span>
  </p>
  <h2>Items</h2>
  <table>
    <thead>
      <tr><th>Product</th><th>Quantity</th><th>Subtotal</th></tr>
    </thead>
    <tbody>
      <tr th:each="item : ${mail.items}">
        <td th:text="${item.productName}">Sample product</td>
        <td th:text="${item.quantity}">1</td>
        <td th:text="${item.lineTotal}">100,000 VND</td>
      </tr>
    </tbody>
  </table>
  <p>
    Total:
    <strong th:text="${mail.totalAmount}">100,000 VND</strong>
  </p>
  <p th:text="${mail.shippingAddress}">Shipping address</p>
  <p><a th:href="${mail.detailsUrl}">View order</a></p>
</body>
</html>
~~~

`th:text` escapes text data using Thymeleaf's default mechanism. `th:href` writes the URL into an HTML attribute; the URL must be constructed from a trusted base URL and validated against application policy before placing it in the model. Never use `th:utext` for recipient names, product names, or untrusted notes.

### 6.1. Multiple variables or a single mail variable?

There are two common approaches:

**One variable holding the mail model:**

~~~java
context.setVariable("mail", model);
~~~

The template accesses `${mail.orderNumber}`, `${mail.totalAmount}`, `${mail.items}`.

**Exposing each value as a separate variable:**

~~~java
context.setVariable("recipientName", model.recipientName());
context.setVariable("orderNumber", model.orderNumber());
context.setVariable("totalAmount", model.totalAmount());
context.setVariable("items", model.items());
~~~

The first approach keeps the namespace clean and makes explicit that the template receives a typed model. The second approach is helpful when integrating a legacy template that already expects individual variables. For new templates, a single `mail` variable holding a DTO is usually easier to maintain.

### 6.2. Using a Map when template APIs require dynamic keys

`Map<String, Object>` remains useful when templates are dynamically configured or have variable key sets. You can convert a model into a map explicitly:

~~~java
Map<String, Object> variables = new HashMap<>();
variables.put("recipientName", model.recipientName());
variables.put("orderNumber", model.orderNumber());
variables.put("orderDate", model.orderDate());
variables.put("totalAmount", model.totalAmount());
variables.put("items", model.items());

Context context = new Context(model.locale());
context.setVariables(variables);
~~~

In return, the compiler no longer verifies that keys exist or are spelled correctly. If using a map, centralize map creation in a dedicated mapper/renderer, define constants for important keys, or test templates to catch mismatched variable names.

### 6.3. Do not share Context across multiple emails

`Context` holds variables for a single render pass. Never store a mutable context in a singleton service field and overwrite variables per recipient:

~~~java
// Avoid: context shared across requests.
private final Context sharedContext = new Context();
~~~

Two concurrent requests can overwrite each other's recipient name, order code, or URL. Create a fresh context for every render:

~~~java
Context context = new Context(model.locale());
context.setVariable("mail", model);
String html = templateEngine.process(templateName, context);
~~~

`TemplateEngine` is typically configured as a shared bean; context and mail model instances should be created per message.

## 7. Rendering HTML and plain text from the same model

An HTML email should have a matching plain-text version. Both must pull data from **the same mail model** to prevent discrepancies between formats.

~~~text
              OrderConfirmationMailModel
                         |
              +----------+----------+
              |                     |
              v                     v
       Thymeleaf HTML         PlainTextRenderer
              |                     |
              v                     v
          htmlBody              plainBody
              |                     |
              +----------+----------+
                         |
                         v
          MimeMessageHelper.setText(plain, html)
~~~

Example plain-text renderer:

~~~java
package com.example.mail.render;

import com.example.mail.model.OrderConfirmationMailModel;

public class OrderConfirmationPlainTextRenderer {

    public String render(OrderConfirmationMailModel mail) {
        StringBuilder text = new StringBuilder();
        text.append("Hello ")
                .append(mail.recipientName())
                .append(",\n\n");
        text.append("Order ")
                .append(mail.orderNumber())
                .append(" has been confirmed.\n");
        text.append("Order date: ")
                .append(mail.orderDate())
                .append("\n\n");

        text.append("Items:\n");
        mail.items().forEach(item -> text.append("- ")
                .append(item.productName())
                .append(" | Qty: ")
                .append(item.quantity())
                .append(" | ")
                .append(item.lineTotal())
                .append('\n'));

        text.append("\nTotal: ")
                .append(mail.totalAmount())
                .append("\n");
        text.append("Shipping address: ")
                .append(mail.shippingAddress())
                .append("\n\n");
        text.append("View order: ")
                .append(mail.detailsUrl());

        return text.toString();
    }
}
~~~

The plain-text renderer does not need HTML escaping. Data is appended as plain text; `<`, `&`, or quotes in names remain normal text characters. URLs must still be constructed and validated beforehand.

### 7.1. Sending both versions via MimeMessageHelper

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo(recipientEmail);
helper.setSubject("Order confirmation " + model.orderNumber());
helper.setText(plainBody, htmlBody);

mailSender.send(message);
~~~

`setText(plainBody, htmlBody)` creates both content versions inside `multipart/alternative` when the helper has multipart enabled. The mail client can choose plain text or HTML depending on its capabilities and settings.

### 7.2. Text templates can use MessageSource

For multilingual emails, you do not have to hard-code every label in templates. You can use Spring's `MessageSource` or Thymeleaf message expressions to resolve strings by locale:

~~~html
<h1 th:text="#{mail.order.confirmed}">
  Order confirmed
</h1>
<span th:text="#{mail.order.number}">
  Order code
</span>
~~~

The context is created with the recipient's locale:

~~~java
Context context = new Context(model.locale());
context.setVariable("mail", model);
~~~

Message keys such as `mail.order.confirmed` are translated in resource bundles per locale. Personal and transactional data still come from the mail model; message bundles provide only **static labels and wording**.

## 8. Formatting dates, times, currency, and quantities

Display formatting depends on the recipient's language and region. The same instant may need to render differently:

| Locale | Example date display |
| --- | --- |
| `vi-VN` | 12 tháng 11 năm 2026 |
| `en-US` | November 12, 2026 |
| `en-GB` | 12 November 2026 |

Do not format dates by manually concatenating day/month/year strings. Use `DateTimeFormatter` and locale:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale)
                .withZone(zoneId);

String displayDate = formatter.format(instant);
~~~

`Instant` represents a global point in time; `ZoneId` determines the recipient's local date/time. For a `LocalDate` value that is already a business calendar date, do not convert it through a time zone.

### 8.1. Formatting currency

Use `BigDecimal` for monetary values, `Currency` for the currency code, and `NumberFormat` to display per locale:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance(locale);
formatter.setCurrency(Currency.getInstance(currencyCode));
String displayAmount = formatter.format(amount);
~~~

Never convert `BigDecimal` to `double` just for formatting, as precision can be lost. Never assume all recipients use the same currency or the same thousands/decimal separators.

### 8.2. Do not share mutable NumberFormat across requests

`NumberFormat` is not safe for concurrent use across threads. Create the formatter per map/render call, or use a per-request instance factory. By contrast, `DateTimeFormatter` is immutable and thread-safe, so it can be shared when the pattern/locale is fixed.

### 8.3. Formatting must not alter business values

For example, if the original amount is `BigDecimal("1234567.50")`, the mapper may format it as a locale-specific string, but must never round or alter the business amount just to fit a template. Rounding rules must be determined beforehand in the business layer; the formatter only controls presentation.

## 9. Nulls, empty collections, and incomplete data

The mail model needs an explicit policy for missing data. If a template receives `null`, some expressions may print the string `"null"`, leave unintended blanks, or fail when dereferencing properties.

For example, the mapper should decide:

- Missing recipient name: use a product-approved neutral greeting.
- Missing secondary address: omit creating an empty address line.
- Empty item list: determine whether this is valid or anomalous business data.
- Missing URL: do not render a link with an empty `href`.
- Missing timestamp or currency: reject creating the email if those are required fields.

Example:

~~~java
String recipientName = recipient.displayName();
if (recipientName == null || recipientName.isBlank()) {
    recipientName = "customer";
}

List<OrderLineMailModel> items = order.lines() == null
        ? List.of()
        : order.lines().stream()
                .map(line -> mapLine(line, order.currencyCode(), locale))
                .toList();
~~~

This is an illustrative fallback policy. Do not blindly replace every null with an empty string; if required data is missing to send an accurate notification, stop and record a business error.

### 9.1. Distinguishing null collections from empty collections

- `null` may mean data was not loaded or the source did not provide it.
- An empty list may mean business logic confirmed there are zero items.

Do not silently turn `null` into an empty list if doing so masks a query or mapping bug. Decide based on the input data contract.

### 9.2. Keeping collection order deterministic

If the email lists order lines, ordering must be determined by business logic or the query. Do not rely on the accidental iteration order of a `HashSet` or an unordered collection relation. A deterministic mail model makes email content testable, comparable, and reproducible.

## 10. Loading data from repositories without passing entities to templates

In JPA applications, entities often have lazy relationships. If a template accesses `order.customer.name` or iterates `order.lines` after the transaction closes, the application can hit `LazyInitializationException`. Even while the transaction is open, templates can trigger unintended extra queries.

Load the exact data needed for the email at the application/repository layer and build a snapshot:

~~~java
public record OrderMailData(
        String publicOrderId,
        String orderNumber,
        Instant createdAt,
        BigDecimal totalAmount,
        String currencyCode,
        List<OrderLineMailData> lines,
        String shippingAddress) {
}
~~~

The repository can use a projection or dedicated query to fetch the required columns. The application service wraps the result into a DTO, and the email mapper receives that DTO:

~~~text
OrderRepository / query projection
             |
             v
       OrderMailData
             |
             v
   OrderConfirmationMailMapper
             |
             v
 OrderConfirmationMailModel
~~~

### 10.1. Application service example

~~~java
package com.example.order;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderMailDataService {

    private final OrderRepository orderRepository;

    public OrderMailDataService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public OrderMailData loadForConfirmation(String orderId) {
        return orderRepository.findMailDataByPublicId(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order was not found"));
    }
}
~~~

`findMailDataByPublicId` is an illustrative method; the repository must implement the corresponding projection/query. The goal is to return materialized data rather than an entity with lazy relationships for the template to traverse.

### 10.2. Consistent snapshots when sending asynchronously

If an email is queued for later sending, do not just store an ID and let the worker arbitrarily load the entity at a different time without considering data state. The order may change between event emission and when the worker sends the mail.

Depending on business rules, you can:

- Store a **snapshot of the fields to send** alongside the event/outbox record.
- Or store the ID and explicitly specify that the email must reflect the latest state at send time.
- Use versions or event payloads to avoid mixing data from two states.
- Only send after the business transaction has successfully committed.

For example, a payment confirmation email must usually reflect the committed amount and status. If the mapper reads part of the data before commit and part after commit, the content can become inconsistent.

## 11. Separating the mail envelope from template content

An email has both routing metadata and content:

| Group | Examples | Where used |
| --- | --- | --- |
| **Envelope/header** | From, To, Cc, Reply-To, Subject | `MimeMessageHelper` and Jakarta Mail API |
| **Mail model** | Name, order code, line items, date, total, link | HTML/plain-text templates |
| **MIME resources** | PDF, CID logo, attachments | `addAttachment` / `addInline` |

You do not need to put everything into the same template object. For instance, the recipient address used for delivery should be passed to the mailer:

~~~java
mailer.send(
        recipientEmail,
        subject,
        plainBody,
        htmlBody);
~~~

The template receives only the fields it needs. This separation reduces the risk of accidentally rendering email addresses, routing metadata, or sensitive fields into the email body.

### 11.1. Model for attachments

If an email type has file attachments, describe files with a separate structure:

~~~java
public record MailAttachment(
        String filename,
        InputStreamSource content,
        String contentType) {
}
~~~

The mailer accepts the validated attachment list:

~~~java
helper.setText(plainBody, htmlBody);

for (MailAttachment attachment : attachments) {
    helper.addAttachment(
            attachment.filename(),
            attachment.content(),
            attachment.contentType());
}
~~~

Do not pass document entities or arbitrary file paths into templates. Filename, access permissions, content type, and byte sources must be resolved in the application layer. The `InputStreamSource` must be able to open a stream suitable for MIME serialization.

## 12. URLs and sensitive data in the mail model

A mail model may contain URLs for recipients to view an order, download documents, or verify an account. URLs must be built from a **trusted base URL** in application configuration with properly encoded components.

Avoid:

~~~java
String url = request.getParameter("returnUrl");
String html = "<a href=\"" + url + "\">Open order</a>";
~~~

The input could point to an external domain or disallowed scheme. Build URLs from the application domain:

~~~java
String detailsUrl = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .pathSegment("orders", "{id}")
        .encode()
        .buildAndExpand(publicOrderId)
        .toUriString();
~~~

If the URL contains a verification or password reset token:

- The token must have an explicit expiration and scope.
- Include the token only in links of emails that require it.
- Never write full URLs/tokens into logs, metrics, or exception messages.
- Do not place tokens into model fields unused by the template.
- Use HTTPS and the official domain.
- Prevent token reuse after verification or expiration.

A mail model may need to carry a tokenized URL for link rendering; that does not mean the whole model is safe to serialize/log. Treat the model as data that may contain sensitive information.

### 12.1. Do not pre-escape data in the mapper

The mapper should return raw text data:

~~~java
return new OrderLineMailModel(
        line.productName(),
        Integer.toString(line.quantity()),
        formattedTotal);
~~~

Let Thymeleaf `th:text` escape the product name in the HTML text context. Do not call `Encode.forHtml` in the mapper and then pass the escaped string into `th:text`; that causes double escaping.

Similarly, URLs must be built and validated at the URI layer, and then the template engine writes them into attributes. Do not HTML-escape URLs in the mapper before passing them to `th:href`.

## 13. Complete email-sending workflow

An order confirmation use case can be organized into components:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import com.example.mail.mapper.OrderConfirmationMailMapper;
import com.example.mail.model.OrderConfirmationMailModel;
import com.example.mail.render.OrderConfirmationPlainTextRenderer;
import com.example.order.OrderMailData;
import com.example.order.OrderMailDataService;
import com.example.order.RecipientMailPreferences;

@Service
public class OrderConfirmationMailer {

    private final OrderMailDataService dataService;
    private final OrderConfirmationMailMapper mapper;
    private final TemplateEngine templateEngine;
    private final OrderConfirmationPlainTextRenderer plainRenderer;
    private final JavaMailSender mailSender;

    public OrderConfirmationMailer(
            OrderMailDataService dataService,
            OrderConfirmationMailMapper mapper,
            TemplateEngine templateEngine,
            OrderConfirmationPlainTextRenderer plainRenderer,
            JavaMailSender mailSender) {
        this.dataService = dataService;
        this.mapper = mapper;
        this.templateEngine = templateEngine;
        this.plainRenderer = plainRenderer;
        this.mailSender = mailSender;
    }

    public void send(
            String publicOrderId,
            String recipientEmail,
            RecipientMailPreferences preferences)
            throws MessagingException {

        OrderMailData source =
                dataService.loadForConfirmation(publicOrderId);

        OrderConfirmationMailModel model =
                mapper.map(source, preferences);

        Context context = new Context(model.locale());
        context.setVariable("mail", model);
        String htmlBody = templateEngine.process(
                "mail/order-confirmation", context);

        String plainBody = plainRenderer.render(model);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipientEmail);
        helper.setSubject("Order confirmation " + model.orderNumber());
        helper.setText(plainBody, htmlBody);

        mailSender.send(message);
    }
}
~~~

This example assembles the components at the application service level. The `OrderMailDataService`, mapper, renderer, `TemplateEngine`, and `JavaMailSender` beans must be configured in the application. `recipientEmail` must come from an authenticated/authorized recipient source. The `From` address must belong to an authorized domain and SMTP account.

Processing flow:

1. Load the data snapshot needed for the email.
2. Map the snapshot into the mail model.
3. Render HTML from the template and plain text from the same model.
4. Create the MIME message.
5. Set envelope/headers and both content versions.
6. Send via JavaMailSender.

In larger systems, snapshot loading and sending may live in two separate services or processes. What matters is that the data contract between them is clear and sufficient to build the email accurately.

## 14. Testing mapping and templates without SMTP

The mapper is plain Java code and can be tested independently:

~~~java
@Test
void mapsOrderToConfirmationMailModel() {
    OrderMailData order = new OrderMailData(
            "public-123",
            "ORD-2026-001",
            Instant.parse("2026-11-12T08:00:00Z"),
            new BigDecimal("125000.00"),
            "VND",
            List.of(new OrderLineMailData(
                    "Keyboard", 1, new BigDecimal("125000.00"))),
            "12 Nguyen Hue, Ho Chi Minh City");

    RecipientMailPreferences recipient =
            new RecipientMailPreferences(
                    "Lan",
                    "vi-VN",
                    "Asia/Ho_Chi_Minh");

    OrderConfirmationMailModel model =
            mapper.map(order, recipient);

    assertThat(model.recipientName()).isEqualTo("Lan");
    assertThat(model.orderNumber()).isEqualTo("ORD-2026-001");
    assertThat(model.items()).hasSize(1);
    assertThat(model.detailsUrl())
            .contains("/orders/public-123");
}
~~~

This example uses JUnit and AssertJ; the mapper must be constructed with a test base URL. There is no need to initialize JavaMailSender or open an SMTP connection to test data mapping.

### 14.1. Cases to include in mapper tests

- `vi-VN`, `en-US`, and the product's default locale.
- Different time zones, especially timestamps near UTC midnight.
- Currencies with different decimal place counts.
- Lists with zero, one, and multiple line items.
- Product names with Vietnamese diacritics and special characters.
- Missing values according to each fallback policy.
- Public IDs containing characters that require URL path encoding.
- Invalid currency codes or ZoneIds producing clear errors.

### 14.2. Testing templates

You can render a template with a fixed model:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("mail", sampleModel);

String html = templateEngine.process(
        "mail/order-confirmation", context);

assertThat(html).contains("ORD-2026-001");
assertThat(html).contains("View order");
~~~

This test verifies that the template receives the right variable and renders key content. You can add data containing `<`, `&`, and quotes to verify `th:text` escapes properly; inspect URL attributes separately to verify destinations are generated per policy.

### 14.3. Testing the MIME message

If you need to confirm plain text and HTML coexist, you can use a fake/mock JavaMailSender returning a real MimeMessage created from a Jakarta Mail Session, and inspect the message after the service calls send. Or send to an SMTP sink in an integration test.

Unit tests for mappers or templates do not need a real SMTP connection. Separating steps helps pinpoint whether a bug belongs to mapping, templates, or transport.

## 15. Validation and the mail model contract

The mail model is the contract between the mapper and the template. If a required field is missing, the error should be caught early before creating the MIME message.

Validation can occur at two layers:

- **Input data validation**: order number, currency code, timestamp, recipient preferences, and URLs must be valid per business rules.
- **Mail model validation**: required template fields must have values and collections must be in a defined state.

Example with Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Locale;

public record PasswordResetMailModel(
        @NotBlank String recipientName,
        @NotBlank String resetUrl,
        @NotNull Locale locale,
        @NotNull List<String> supportContacts) {
}
~~~

Validation annotations take effect only when the application actually invokes a validator or integrates validation into model creation. Declaring annotations does not automatically ensure every record is checked. For data that cannot be safely sent when missing, the mapper should refuse to build the model and return a contextual error.

### 15.1. Distinguishing required vs. optional data

| Field | Example policy |
| --- | --- |
| Recipient | Must have a valid address in the envelope |
| Transaction code | Required if the email confirms a specific transaction |
| Total amount/currency | Required for invoice emails |
| Display name | Can use a neutral greeting if business rules allow |
| Secondary address | Line can be omitted if absent |
| Details link | Required if the email directs users to a details page |
| Item list | May be empty if the email type permits; otherwise raise a data error |

Do not use the same fallback for every field. An empty string in a decorative field might be acceptable; an empty string in an amount or verification link can render the email incorrect.

### 15.2. Do not turn mapping errors into fake successful emails

If the mapper cannot build a URL, does not recognize a currency code, or lacks an order number, do not send an email containing placeholders like `null`, `0`, or an empty link just to avoid throwing an exception. Stop at model creation and let the use case record an appropriate failure.

Conversely, an optional field like display name may have a product-approved fallback. The policy must be documented clearly so maintainers understand why one field falls back while another fails the task.

## 16. Manual mapping or MapStruct?

For a small mail model, manual mapping is usually easy to read:

~~~java
return new OrderConfirmationMailModel(
        recipient.displayName(),
        order.orderNumber(),
        formatDate(order.createdAt(), zone, locale),
        mapLines(order.lines(), locale),
        formatMoney(order.totalAmount(), order.currencyCode(), locale),
        order.shippingAddress(),
        buildDetailsUrl(order.publicOrderId()),
        locale);
~~~

When an application has many email types and many similar fields, **MapStruct** can reduce boilerplate conversion code by generating mappers at compile time:

~~~java
@Mapper(componentModel = "spring")
public interface RecipientMailMapper {

    RecipientHeaderMailModel toModel(RecipientProfile source);
}
~~~

This is only a simple mapper example. Logic-heavy operations such as formatting money/dates, choosing locales, building URLs, filtering sensitive info, or translating business states should still be written explicitly in custom mapping methods or dedicated assembler classes.

Never let a tool automatically copy every field from an entity into an email model. The goal is to pass **only permitted and necessary data** into templates.

## 17. Mapping multiple emails and avoiding N+1 queries

When notifying many recipients, invoking the mapper must not trigger a new query per order line or per recipient when data can be fetched in batches.

Example of an inefficient flow:

~~~text
List of 100 orders
   |
   +--> load customer for order 1
   +--> load lines for order 1
   +--> load customer for order 2
   +--> load lines for order 2
   ...
~~~

If relationships are lazy-loaded, query count can grow rapidly. A better structure uses batch queries/projections to fetch the required data for a group of emails, then maps from the loaded snapshot:

~~~text
Batch query / projection
          |
          v
List<OrderMailData>
          |
          v
Map each item to a mail model
          |
          v
Render and send per recipient
~~~

Notes:

- Select only the columns needed for the email.
- Sort collections according to business order.
- Avoid accessing repositories from templates or from mail model getters.
- When sending in batches, limit concurrent messages and handle per-message failures per policy.
- Never share a mutable Context or MimeMessage across multiple recipients.

### 17.1. Dedicated model per recipient

If the same transaction notifies multiple people, content may differ according to each recipient's language or permissions. Build a separate model per recipient:

~~~java
for (RecipientMailPreferences recipient : recipients) {
    OrderConfirmationMailModel model =
            mapper.map(orderSnapshot, recipient);
    mailRenderer.renderAndSend(recipient.email(), model);
}
~~~

This is illustrative pseudocode; recipient email may live in a separate envelope DTO. Never mutate a shared model while sending multiple messages sequentially if fields from a previous recipient could leak over.

## 18. Common mapping mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Template prints `null` | Missing field or wrong key | Define required fields, validate model before rendering |
| Template cannot find variable | Variable name in context mismatches template | Use a clear key contract and test rendering |
| `LazyInitializationException` | Template accesses entity/lazy relation outside transaction | Use projections/snapshots and mail DTOs |
| Email shows wrong currency/amount | Wrong locale/currency or mapper recalculates amounts | Use business currency code and locale formatter |
| Date is off by one day | Wrong time zone or mixing up Instant and LocalDate | Use recipient ZoneId or keep business LocalDate |
| Link points to wrong domain | Using request URL instead of trusted base URL | Build URL from config and encode components |
| User name renders `&amp;lt;` | Escaped in mapper and escaped again by template | Pass raw data and escape at the sink |
| Plain text differs from HTML | Two renderers read data from different sources | Render both from the same mail model |
| Line items out of order | Source collection is unordered | Sort in query/domain before mapping |
| Email contains internal info | Mail model copied entire entity | Use an allowlist of required fields |
| Two recipients' contents mixed | Shared mutable Context/model/message | Create dedicated objects per send |
| Email sends stale data | Worker loads entity at a different time from event | Use snapshot/version per business requirements |

## 19. Frequently asked questions

**"Is a mail model a DTO?"**  
Usually yes. It is a DTO tailored to a specific email type, holding the fields a template needs and optionally preformatted display values.

**"Should JPA entities be passed directly to Thymeleaf?"**  
No. Templates can become coupled to the entity, trigger lazy relations, fire extra queries, or expose internal fields. Map to a small DTO before rendering.

**"Should one Map be used for all emails?"**  
Maps are useful when keys are genuinely dynamic, but for fixed email types, typed models clarify the contract and prevent key typos. If using a Map, centralize key creation in one place and test template rendering.

**"Should the mapper format currency and dates?"**  
Yes, when it is locale/timezone presentation formatting. Rules for totals, taxes, discounts, and rounding must live in the business layer; the mapper only formats the outcome.

**"Should HTML be escaped inside the mapper?"**  
Usually no. Keep text data in raw form and let Thymeleaf `th:text` or context-appropriate encoders escape at output time. Avoid double escaping.

**"Should the mail model contain the recipient email?"**  
Not necessarily. Delivery addresses in the mailer's envelope are usually kept separate from template variables. This lowers the risk of addresses or routing metadata unexpectedly appearing in the body.

**"Should PDF files or Resources be placed in the mail model?"**  
If the template only presents text/HTML content, no. Attachments can be passed in a separate structure to the mailer. Filenames, content types, access rights, and byte sources must be validated before sending.

**"Can the same mail model be shared between HTML and plain text?"**  
Yes, and it should be. Sharing one model ensures both versions reflect the same transaction codes, amounts, dates, and URLs. HTML and plain-text renderers differ only in presentation.

**"Should templates format dates and currency themselves?"**  
Templates may use simple utilities if your architecture specifies it, but centralizing formatting in a mapper/service is usually easier to test and keep consistent. Never let templates execute business rules.

**"When sending email asynchronously, when is the mail model created?"**  
It depends on whether the email must reflect the state at event emission or the latest state at send time. If exact historical state is needed, store a snapshot or full event payload; if latest state is needed, the worker reloads by ID under an explicit policy.

## 20. Takeaways for mapping business data to a mail model

A maintainable email-sending flow can be structured as:

~~~text
Use case / application service
        |
        v
Load required data (projection/snapshot)
        |
        v
Mail mapper
  - select permitted fields
  - format dates/currency by locale
  - build URLs from trusted base URL
  - handle null/collections per policy
        |
        v
Typed mail model
        |
        +--> Thymeleaf HTML renderer
        |
        +--> Plain-text renderer
        |
        v
Mail envelope + MIME resources
        |
        v
MimeMessageHelper
        |
        v
JavaMailSender
~~~

The mail model establishes a clear boundary between business data and email content. Repositories/application services supply the needed snapshot; mappers select and format data; templates handle presentation; the mailer packages MIME and sends. Maintaining this boundary keeps emails easy to test, easy to localize, loosely coupled to persistence, and less likely to leak internal details or send inconsistent content.
