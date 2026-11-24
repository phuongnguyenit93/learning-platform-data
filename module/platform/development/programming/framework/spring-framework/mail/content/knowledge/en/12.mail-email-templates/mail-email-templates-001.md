# Data Model for an Email Template

In **Spring Framework Mail**, an email template typically receives data from the application and generates HTML or plain-text content to send to recipients. For example, an order confirmation template needs the customer name, order number, list of products, total amount, order timestamp, and a link to view details. Passing a database entity directly into the template or letting the template query data itself couples the presentation layer to the storage structure and risks exposing unnecessary information.

An **email template data model** (template data model or mail view model) is a curated set of clearly named values prepared specifically for template rendering. This model acts as a contract between the **business layer** and the **email presentation layer**:

~~~text
Database / Domain model
          |
          v
Application service + mapper
          |
          v
Email template data model
          |
          +--------------------+
          |                    |
          v                    v
HTML template             Plain-text template
          |                    |
          +---------+----------+
                    |
                    v
             Rendered content
                    |
                    v
       MimeMessage / MimeMessageHelper
                    |
                    v
             JavaMailSender
~~~

A good data model makes emails easier to maintain, test, personalize, and send asynchronously. It also creates a security boundary: the template only receives the data needed for display and cannot arbitrarily access entities, SMTP secrets, or internal system fields.

## 1. Why Do We Need a Separate Model for Email?

Suppose the application has an order entity:

~~~java
class OrderEntity {
    Long id;
    UserEntity customer;
    List<OrderLineEntity> lines;
    BigDecimal total;
    String paymentProviderReference;
    String internalNote;
    String fraudReviewStatus;
    // many other relationships and internal fields
}
~~~

If the raw entity is passed to the template:

~~~java
context.setVariable("order", orderEntity);
~~~

the template can access too many properties, depend on the ORM structure, and accidentally display data not intended for the customer. A lazy relationship can also trigger unintended queries during rendering; schema or mapping changes can also break the template.

Instead, the application layer creates a dedicated model:

~~~java
public record OrderConfirmationMailModel(
        String customerName,
        String orderNumber,
        String totalText,
        List<OrderLineMailModel> lines,
        String orderUrl) {
}
~~~

The model only contains what the email needs to display. The template does not need to know which table the order is stored in, how many ORM relationships the customer has, or which payment provider the system uses.

### 1.1. Key Benefits

| Benefit | Practical Meaning |
| --- | --- |
| **Separation of business logic and presentation** | HTML/CSS can be changed without modifying order logic |
| **Data minimization** | Only selected fields can appear in the email |
| **Contract stability** | Templates use clear variable names independent of entities/database |
| **Ease of testing** | Sample models can be created directly without spinning up an entire database |
| **Multi-language readiness** | Data can be formatted according to locale before rendering |
| **Asynchronous sending readiness** | The model can be captured as an immutable payload for a queue |
| **Reusability** | HTML and plain text can share the same dataset |

## 2. Distinguishing Email Envelope, Template Model, and Template Context

In email-sending code, these three concepts are often conflated, but they serve different purposes.

| Component | What It Contains | Example |
| --- | --- | --- |
| **Mail envelope/message metadata** | Sender, recipients, Cc/Bcc, Reply-To, Subject | `from`, `to`, `subject` |
| **Template data model** | Business data used for presentation | `customerName`, `orderNumber`, `totalText` |
| **Template context** | How variables are passed into a single template engine render | Thymeleaf `Context` with `setVariable(...)` |

Example:

~~~java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Order confirmation A123");

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", "Alice Nguyen");
context.setVariable("orderNumber", "A123");
context.setVariable("totalText", "220.000 ₫");
~~~

`customerName` and `orderNumber` are presentation data. `To` and `Subject` are email metadata. Not every variable placed in the context should appear in the template; pass only the model actually needed.

A clean design usually has a separate envelope object and a separate content model. That allows changing recipients or the subject according to delivery policies without forcing the presentation model to carry SMTP details.

## 3. Principles for Designing an Email Data Model

### 3.1. Contain Only Data Needed for Display

Start from the template and ask: **what information does the recipient need to see?** Every variable in the template should have a business reason.

For example, an order confirmation email might need:

- recipient name;
- order number;
- formatted order date and time;
- list of products;
- quantity and line total for each item;
- total amount and currency;
- shipping address at the level permitted for display;
- link to view the order;
- support contact address or instructions.

There is no need to include fields such as passwords, internal tokens, fraud review status, staff notes, database connection IDs, or the entire customer object in the model.

### 3.2. Name by Meaning, Not by Database Position

Variable names should express **meaning to the template reader**:

| Cryptic Name | Clearer Name |
| --- | --- |
| `u` | `customerName` |
| `ordNo` | `orderNumber` |
| `amt` | `totalAmountText` |
| `dt` | `orderedAtText` |
| `lst` | `orderLines` |
| `flag1` | `showSupportInformation` |

Do not name template variables after database columns such as `c_name`, `col_17`, or abbreviations only the mapper author understands. A template is a contract read by both backend developers and content owners.

### 3.3. Distinguish Required and Optional Fields

Example:

| Field | Required? | Handling If Missing |
| --- | --- | --- |
| `orderNumber` | Yes | Do not build the confirmation email if the order number is missing |
| `customerName` | Yes, or has a business fallback value | Use a generic greeting if permitted |
| `orderLines` | Yes | Use an empty list or reject model creation depending on email type |
| `deliveryAddress` | Depends on email | Hide the address section if not applicable |
| `supportUrl` | Depends on email type | Omit the CTA or use a default support channel |
| `promotionText` | No | Do not render the promotion section when absent |

Do not leave the template to guess how to handle every `null` field. Default rules should be decided in the application layer or explicitly documented in the template.

### 3.4. Use Appropriate Data Types

Do not turn everything into `String` too early. You can keep meaningful types at the model layer and format them in the mapper:

- `UUID` for job IDs or identifier IDs;
- `BigDecimal` for monetary amounts;
- `Currency` or currency codes for currency units;
- `Instant`, `LocalDate`, `OffsetDateTime` for timestamps/dates;
- `URI` for generated and controlled links;
- `List<...>` for repeated lines;
- `boolean` for display conditions.

If the template only needs to display a string, formatting in the mapper into `totalText` or `orderedAtText` can keep the template simpler. Choose one consistent approach based on template complexity; do not let each template calculate money or timezones under different rules.

## 4. Example Model for an Order Confirmation Email

Suppose the email needs the customer name, order number, order date, product list, total amount, and a link to view the order.

### 4.1. Nested Model Using Java Records

~~~java
package com.example.mail.model;

import java.util.List;
import java.util.Objects;

public record OrderLineMailModel(
        String productName,
        String sku,
        int quantity,
        String unitPriceText,
        String lineTotalText) {

    public OrderLineMailModel {
        Objects.requireNonNull(productName, "productName");
        Objects.requireNonNull(unitPriceText, "unitPriceText");
        Objects.requireNonNull(lineTotalText, "lineTotalText");

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
~~~

Email-level model:

~~~java
package com.example.mail.model;

import java.util.List;
import java.util.Objects;

public record OrderConfirmationMailModel(
        String customerName,
        String orderNumber,
        String orderedAtText,
        List<OrderLineMailModel> orderLines,
        String subtotalText,
        String shippingFeeText,
        String totalText,
        String orderUrl,
        boolean showSupportInformation) {

    public OrderConfirmationMailModel {
        Objects.requireNonNull(customerName, "customerName");
        Objects.requireNonNull(orderNumber, "orderNumber");
        Objects.requireNonNull(orderedAtText, "orderedAtText");
        Objects.requireNonNull(totalText, "totalText");
        Objects.requireNonNull(orderUrl, "orderUrl");

        orderLines = List.copyOf(
                Objects.requireNonNull(orderLines, "orderLines"));
    }
}
~~~

Notable points:

- **Records** provide constructors, accessors, and basic methods, making the data model clear.
- `String` and `boolean` fields are suitable for pre-prepared presentation information.
- `List.copyOf(...)` creates an immutable copy of the list, preventing a source list from being mutated after the model is created.
- Each product line has its own model; the template does not have to know the product entity structure.
- Required fields are validated right when creating the model. More complex business rules can live in a factory/mapper or validator.

In a Java project, each `public record` should reside in its own file matching the type name. The two snippets above are presented back-to-back for readability.

### 4.2. Why Use a Nested Model?

If there is only one product, a flat model might suffice. However, an order usually has a list of multiple lines. A nested model:

~~~text
OrderConfirmationMailModel
  customerName
  orderNumber
  orderedAtText
  orderLines
    ├── OrderLineMailModel
    ├── OrderLineMailModel
    └── OrderLineMailModel
  subtotalText
  shippingFeeText
  totalText
  orderUrl
~~~

gives each product line a consistent structure. If a `discountText` or `imageUrl` field is added per product, you only need to extend `OrderLineMailModel` and the corresponding template, rather than creating scattered variables such as `product1Name`, `product2Name`.

## 5. Building the Model from Business Data

Templates should not query the database. An application service or a dedicated mapper fetches the data and transforms it into the model.

Model example:

~~~java
public class OrderMailModelMapper {

    public OrderConfirmationMailModel toModel(
            Order order,
            Customer customer,
            Locale locale,
            URI trustedBaseUri) {
        // Select and format data before handing it to the template.
    }
}
~~~

The mapper needs to:

1. Select fields allowed for display.
2. Validate required data.
3. Format money, date/time, and locale.
4. Build URLs from a trusted domain.
5. Convert entity lists into child model lists.
6. Apply business-defined defaults.

### 5.1. Mapper Example with Money and Date/Time Formatting

~~~java
package com.example.mail.mapping;

import com.example.mail.model.OrderConfirmationMailModel;
import com.example.mail.model.OrderLineMailModel;
import java.math.BigDecimal;
import java.net.URI;
import java.text.NumberFormat;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import org.springframework.web.util.UriComponentsBuilder;

public class OrderMailModelMapper {

    public OrderConfirmationMailModel toModel(
            Order order,
            Customer customer,
            Locale locale,
            ZoneId displayZone,
            URI trustedBaseUri) {

        NumberFormat moneyFormat =
                NumberFormat.getCurrencyInstance(locale);
        moneyFormat.setCurrency(Currency.getInstance(order.currencyCode()));

        DateTimeFormatter dateFormat =
                DateTimeFormatter.ofPattern(
                        "dd/MM/yyyy HH:mm z",
                        locale
                ).withZone(displayZone);

        List<OrderLineMailModel> lines = order.lines().stream()
                .map(line -> new OrderLineMailModel(
                        line.productName(),
                        line.sku(),
                        line.quantity(),
                        moneyFormat.format(line.unitPrice()),
                        moneyFormat.format(line.lineTotal())
                ))
                .toList();

        URI orderUrl = UriComponentsBuilder
                .fromUri(trustedBaseUri)
                .pathSegment("orders", order.publicReference())
                .build()
                .encode()
                .toUri();

        return new OrderConfirmationMailModel(
                customer.displayName(),
                order.publicReference(),
                dateFormat.format(order.createdAt()),
                lines,
                moneyFormat.format(order.subtotal()),
                moneyFormat.format(order.shippingFee()),
                moneyFormat.format(order.total()),
                orderUrl.toString(),
                true
        );
    }
}
~~~

The mapper snippet assumes that the types `Order`, `Customer`, and methods such as `currencyCode()`, `createdAt()` already exist in the domain model. It is an example of where to place data-preparation logic, not a definition of a concrete entity for every project.

**Money:** use `BigDecimal` for business calculations. `NumberFormat` is for display only; never use a formatted string to sum or compare monetary amounts.

**Date and time:** store timestamps using explicit timezone/instant types; format according to the recipient's timezone or product rules. Do not use the server's default timezone as the display rule for all customers.

**URL:** `trustedBaseUri` must come from controlled configuration. Do not take the host from the `Host` header or an arbitrary user-submitted URL and put it directly into an email. If `publicReference` contains special characters, `pathSegment` together with `encode()` helps build an appropriate URI.

### 5.2. Do Not Perform Business Calculations in Templates

Templates can iterate over product lines, display `totalText`, and show/hide the support section. However, do not use template expressions to:

- calculate taxes, discounts, or totals on their own;
- decide whether an order has been paid;
- determine whether the recipient has permission to view the order;
- query repositories or call external services;
- generate verification tokens or create security codes on their own.

These decisions belong in domain/application services. The template is where **already-decided data is presented**.

## 6. Passing the Model to Thymeleaf

After the mapper creates `OrderConfirmationMailModel`, the application service creates the context:

~~~java
import java.util.Locale;
import org.thymeleaf.context.Context;

OrderConfirmationMailModel model = mapper.toModel(
        order,
        customer,
        Locale.forLanguageTag("vi-VN"),
        ZoneId.of("Asia/Ho_Chi_Minh"),
        URI.create("https://app.company.example")
);

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("mail", model);

String html = templateEngine.process(
        "mail/order-confirmation",
        context
);
~~~

Instead of passing each variable at the root level:

~~~java
context.setVariable("customerName", model.customerName());
context.setVariable("orderNumber", model.orderNumber());
context.setVariable("totalText", model.totalText());
~~~

we can pass **a single clearly named object** called `mail`. This reduces the number of root variables and helps the template show that they belong to the same data contract.

Both approaches are valid. Choose a consistent convention in the project; if a template has multiple distinct data groups, you can use separate names such as `mail`, `branding`, or `footer`, but do not turn the context into a dumping ground for every service and entity in the application.

## 7. Using the Model in an HTML Template

Example `src/main/resources/templates/mail/order-confirmation.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Order Confirmation</title>
</head>
<body style="margin:0;padding:24px;font-family:Arial,sans-serif;">
  <main style="max-width:600px;margin:auto;">
    <h1>Order Confirmed</h1>

    <p>
      Hello
      <strong th:text="${mail.customerName}">Customer</strong>,
    </p>

    <p>
      Order number:
      <strong th:text="${mail.orderNumber}">A123</strong>
    </p>

    <p>
      Order time:
      <span th:text="${mail.orderedAtText}">12/11/2026</span>
    </p>

    <table role="presentation" cellpadding="8" cellspacing="0"
           style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th align="left">Product</th>
          <th align="right">Quantity</th>
          <th align="right">Unit Price</th>
          <th align="right">Subtotal</th>
        </tr>
      </thead>
      <tbody>
        <tr th:each="line : ${mail.orderLines}">
          <td th:text="${line.productName}">Product name</td>
          <td align="right" th:text="${line.quantity}">1</td>
          <td align="right" th:text="${line.unitPriceText}">100.000 ₫</td>
          <td align="right" th:text="${line.lineTotalText}">100.000 ₫</td>
        </tr>
      </tbody>
    </table>

    <p>
      <strong>Total:</strong>
      <span th:text="${mail.totalText}">100.000 ₫</span>
    </p>

    <p>
      <a th:href="${mail.orderUrl}"
         href="https://app.company.example/orders/A123">
        View order
      </a>
    </p>

    <p th:if="${mail.showSupportInformation}">
      If you need support, please reply to this email.
    </p>
  </main>
</body>
</html>
~~~

The expressions access properties of the model:

| Expression | Retrieved Value |
| --- | --- |
| `mail.customerName` | Customer name |
| `mail.orderNumber` | Order number |
| `mail.orderLines` | List of product lines |
| `line.productName` | Name of the current line in the loop |
| `mail.totalText` | Formatted total amount |
| `mail.orderUrl` | Application-generated link |
| `mail.showSupportInformation` | Flag controlling the support section |

`th:text` escapes content for HTML text context. User data such as customer names or product names should be inserted using `th:text`; do not use `th:utext` to directly render untrusted markup.

### 7.1. Use One Model for HTML and Plain Text

Important transactional emails should have both content formats. Plain text can be built from the same model:

~~~java
public String renderPlainText(OrderConfirmationMailModel mail) {
    StringBuilder text = new StringBuilder();
    text.append("Hello ")
        .append(mail.customerName())
        .append("\n\n");
    text.append("Order ")
        .append(mail.orderNumber())
        .append(" has been confirmed.\n");
    text.append("Order time: ")
        .append(mail.orderedAtText())
        .append("\n\n");

    for (OrderLineMailModel line : mail.orderLines()) {
        text.append("- ")
            .append(line.productName())
            .append(" x ")
            .append(line.quantity())
            .append(": ")
            .append(line.lineTotalText())
            .append("\n");
    }

    text.append("\nTotal: ")
        .append(mail.totalText())
        .append("\n");
    text.append("View order: ")
        .append(mail.orderUrl())
        .append("\n");

    return text.toString();
}
~~~

Then:

~~~java
helper.setText(
        renderPlainText(model),
        html
);
~~~

`setText(plainText, htmlText)` on `MimeMessageHelper` sets two alternative representations of the same email content. Both use the same model to avoid discrepancies in order numbers, totals, or links between HTML and text.

## 8. Choosing Between Formatted Data and Typed Data

There are two common approaches:

**Approach A — model holds formatted values:**

~~~java
public record OrderMailModel(
        String totalText,
        String orderedAtText) {
}
~~~

Pros: simple template, no need to know how to format money and time. Cons: if many templates need the same data in different locales, the mapper must create a separate model for each locale.

**Approach B — model holds typed data:**

~~~java
public record OrderMailModel(
        BigDecimal total,
        Currency currency,
        Instant orderedAt) {
}
~~~

Pros: preserves data type semantics and can format by locale in the renderer. Cons: templates or expressions can become more complex and formatting rules can easily scatter without a shared formatter.

### 8.1. How to Choose Appropriately

| Requirement | Usually Suitable Approach |
| --- | --- |
| Single locale, fixed format | Can pre-format into text |
| Multiple locales, multiple currencies | Keep typed data and format via a shared formatter or locale-specific mapper |
| Simple template, template editors do not need to know Java types | Pre-formatted display strings |
| Multiple different displays from the same value | Keep typed values and provide meaningful fields/formatters |
| Data needing calculation/comparison | Keep original types in the business layer; do not calculate using formatted strings |

A balanced approach is for the model to hold **typed business values** together with the necessary **display text fields**:

~~~java
public record MoneyMailModel(
        BigDecimal amount,
        String currencyCode,
        String displayText) {
}
~~~

However, do not duplicate every field if the template only needs one string. The model should serve real requirements, not become a copy of the entire domain object.

## 9. Null, Optional Fields, and Empty Lists

Templates can display incorrectly or throw errors when a variable is missing. A clear data policy must be defined:

- Required fields: do not build the model if missing.
- Optional fields: use `Optional` in the application layer if useful, then convert to an explicit value for the template.
- Lists with no elements: usually use an empty list instead of `null`.
- Skippable text: use an empty string or display flag depending on business rules.

Example:

~~~java
List<OrderLineMailModel> lines =
        sourceLines == null
                ? List.of()
                : sourceLines.stream()
                    .map(this::toMailLine)
                    .toList();
~~~

In a record, `List.copyOf` does not accept `null`; therefore, normalize null to an empty list **before** creating the model, or reject it if the list is required.

### 9.1. Use Display Flags Instead of Tangled Template Logic

If the delivery address section only appears when the order has home delivery:

~~~java
public record DeliveryMailModel(
        boolean showDeliveryAddress,
        String deliveryAddressText) {
}
~~~

Template:

~~~html
<section th:if="${mail.delivery.showDeliveryAddress}">
  <h2>Delivery Address</h2>
  <p th:text="${mail.delivery.deliveryAddressText}">Address</p>
</section>
~~~

A boolean flag expresses a decision already prepared by business logic. Avoid writing template conditions based on multiple internal status fields such as `paymentStatus`, `fulfillmentCode`, `isPickup` and inferring complex rules there; let the mapper translate them into a clear meaning such as `showDeliveryAddress`.

## 10. Safe Data and Privacy

Emails are often stored in many places: recipient inboxes, sending systems, logs, backups, and preview tools. Therefore, the template model must follow the principle of **including only necessary data in message content**.

### 10.1. Do Not Pass the Entire Entity

Avoid:

~~~java
context.setVariable("user", userEntity);
context.setVariable("order", orderEntity);
context.setVariable("payment", paymentEntity);
~~~

Instead, create a DTO:

~~~java
public record AccountWelcomeMailModel(
        String displayName,
        String supportAddress,
        String signInUrl) {
}
~~~

Do not put passwords, password hashes, session cookies, API tokens, secret keys, full payment card data, or internal notes into the template model. If an email needs a verification code, apply a random token with an appropriate scope and expiration; do not use a long-lived secret value as email content.

### 10.2. Escape Content According to Context

A value that is safe when displayed as text is not necessarily safe when placed into:

- HTML attributes;
- URL;
- CSS;
- JavaScript;
- filenames or email headers.

Use context-aware template engine syntax and appropriate URI/HTML APIs. With Thymeleaf, prefer `th:text` and `th:href`; do not put untrusted data into `th:utext`, `th:style`, or arbitrary expressions.

### 10.3. URLs Must Be Generated from a Trusted Source

A model with `orderUrl` should receive a link generated by the application from a configured base URL. Do not take a raw user-supplied `returnUrl` and pass it into the template. The template engine can escape attributes, but it does not know whether that URL points to a valid domain.

When generating confirmation or password-reset links, consider:

- HTTPS;
- random, hard-to-guess tokens with limited purpose and expiration;
- not logging full tokens;
- not using the link as the sole mechanism replacing backend authentication/authorization;
- not letting the template or model turn an external domain URL into a trusted link.

### 10.4. Minimize Personal Data in Emails

Not every piece of information in the database should be included in an email. For example, an invoice might only need an order number, a partial address, the total amount, and a link to view details after signing in. Sensitive account or payment data should be minimized in accordance with product policy and applicable laws.

## 11. Model Immutability When Sent Through a Queue

If emails are sent asynchronously, the model may be placed in a queue or outbox. A mutable model can be modified by the producer after enqueueing, causing the worker to render different content than intended.

Unsafe example:

~~~java
class MutableMailModel {
    String customerName;
    List<OrderLineMailModel> orderLines;
}

queue.add(model);
model.orderLines.clear(); // Worker may see an empty list.
~~~

With records and defensive copying:

~~~java
public record OrderMailJob(
        String customerName,
        String orderNumber,
        List<OrderLineMailModel> orderLines,
        String totalText,
        String orderUrl) {

    public OrderMailJob {
        orderLines = List.copyOf(orderLines);
    }
}
~~~

`String` and child records with immutable fields are suitable for snapshots. If a record contains `byte[]`, `Date`, a mutable `Map`, or a mutable entity, the record itself is not immutable enough; deep copying or converting to immutable value types is required.

### 11.1. Capture Data or Render HTML Before Enqueueing?

There are two strategies:

| Strategy | Queue Payload | Pros | Things to Manage |
| --- | --- | --- | --- |
| Enqueue immutable model and render in worker | DTO and template version | Small payload, easy to inspect fields | Must keep template version and snapshot data stable |
| Render HTML/text first and enqueue | Rendered content | Preserves the exact generated content | Large payload, must protect personal content in queue |

If business rules require retries to send the **exact content that was accepted**, store an HTML/text snapshot or an immutable model alongside the template version. Do not simply save `orderId` and let the worker arbitrarily query the latest data and use the latest template.

### 11.2. Models Must Not Contain SMTP Secrets

Queue payloads should not contain:

~~~text
smtpPassword
smtpApiKey
oauthRefreshToken
databasePassword
~~~

Workers retrieve connection details from runtime configuration or a secret manager. That way, when rotating credentials, you do not have to update all pending jobs and do not duplicate secrets into brokers, dead-letter queues, or backups.

## 12. Data Models for Different Email Types

Do not force every email to use one giant model with dozens of optional fields. Each email type has its own contract:

| Email Type | Model Fields Potentially Needed |
| --- | --- |
| Account welcome | `displayName`, `signInUrl`, `supportAddress` |
| Order confirmation | `customerName`, `orderNumber`, `orderLines`, `totalText`, `orderUrl` |
| Password reset | `displayName`, `resetUrl`, `expiresAtText` |
| Periodic report | `reportTitle`, `periodText`, `summaryRows`, `downloadUrl` |
| Ticket notification | `ticketNumber`, `statusText`, `latestMessagePreview`, `ticketUrl` |
| Invoice | `invoiceNumber`, `issuedAtText`, `billingAddress`, `lineItems`, `grandTotalText` |

A dedicated type per email kind helps the compiler and code readers understand what data is required. You can use a common interface for truly shared metadata, but do not create an abstraction just so all models share unrelated field names.

### 12.1. Distinguishing Content Model and Mail Command

A send request can consist of:

~~~java
public record SendTemplatedMailCommand(
        String recipient,
        String templateId,
        String templateVersion,
        Locale locale,
        OrderConfirmationMailModel model) {
}
~~~

This is a **command/job** describing a request to send a template. `OrderConfirmationMailModel` is **content data**. When multiple recipients, Cc/Bcc, sender identity, correlation ID, or schedule are needed, that information can belong to envelope/job metadata rather than being stuffed into the HTML model.

Separating command and model helps ensure:

- one model can render HTML and text;
- one command can specify template/locale/version;
- transport metadata can change by environment;
- renderer tests do not need to create an SMTP sender;
- workers can inspect job status without parsing HTML content.

## 13. Multi-Language and Branding Models

An application may send the same type of email in Vietnamese or English. Templates should not guess the locale from the recipient's name or email address.

Example:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
OrderConfirmationMailModel model = mapper.toModel(order, customer, locale);

Context context = new Context(locale);
context.setVariable("mail", model);
~~~

The template engine can use a message bundle to fetch static strings such as table headings, the "Total" label, or greetings. Dynamic data such as names, order numbers, and monetary amounts still come from the model.

### 13.1. Directory Structure by Locale

~~~text
templates/
  mail/
    vi/
      order-confirmation.html
    en/
      order-confirmation.html
~~~

The application selects a template based on the determined locale:

~~~java
String templateName = switch (locale.toLanguageTag()) {
    case "en", "en-US", "en-GB" -> "mail/en/order-confirmation";
    default -> "mail/vi/order-confirmation";
};
~~~

This is only an example of template selection. For larger systems, you can use a locale resolver or message bundles instead of writing a long switch statement. What matters is having a **defined fallback locale**, so you do not generate an email with half Vietnamese labels and half English labels.

### 13.2. Branding Should Be Separated from Transaction Data

Logo, primary color, company name, and support address can belong to a branding model:

~~~java
public record MailBrandingModel(
        String companyName,
        String logoUrl,
        String supportEmail,
        String footerText) {
}
~~~

When rendering, pass `mail` and `branding` separately:

~~~java
context.setVariable("mail", orderModel);
context.setVariable("branding", brandingModel);
~~~

This way, changing a logo or footer does not require adding fields to every transaction model. However, if branding must be fixed at the time of enqueueing, it needs to be snapshotted or versioned just like the template.

## 14. Attachments and Resources Outside the Content Model

Emails may have attachments, inline images, or downloadable documents. Such data does not necessarily belong directly in the template model.

A send request can distinguish:

~~~text
Template data:
  customerName
  invoiceNumber
  totalText
  downloadUrl

Message resources:
  attachment: invoice.pdf
  inline image: company-logo
~~~

Attachments are MIME data and may require bytes, resources, or object storage IDs. Template data mainly describes display content. If the template needs to reference a CID image, synchronize the ID between the HTML and the MIME builder, without necessarily stuffing the entire image bytes into the context.

When putting resources into a queue:

- do not just store a path to a temporary file that may be deleted/overwritten;
- store an object storage version or content hash if integrity is needed;
- limit payload size and total email size;
- protect file access permissions;
- avoid logging content or binary data.

## 15. Testing Models and Templates

Separating the model enables testing without real SMTP. You can test across three layers:

1. **Mapper test:** domain data is transformed into the model correctly.
2. **Template render test:** the model produces HTML/text with the right variables and proper escaping.
3. **Mail assembly test:** HTML/text is placed into MIME properly, with appropriate headers and recipients.

### 15.1. Testing the Mapper

Illustrative example:

~~~java
@Test
void mapsOrderToMailModel() {
    Order order = sampleOrder();
    Customer customer = sampleCustomer();

    OrderConfirmationMailModel model = mapper.toModel(
            order,
            customer,
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh"),
            URI.create("https://app.company.example")
    );

    assertEquals("A123", model.orderNumber());
    assertEquals("Alice Nguyen", model.customerName());
    assertFalse(model.orderLines().isEmpty());
    assertTrue(model.orderUrl().startsWith(
            "https://app.company.example/orders/"));
}
~~~

The `sampleOrder()` and `sampleCustomer()` methods are fixtures provided by the test. Tests should also check missing data, different currencies, timezones, empty lists, and links with characters that need encoding.

### 15.2. Testing Templates with Special Data

A test model with the name:

~~~text
An <Admin> & Co
~~~

should be rendered with `th:text` so the HTML contains the corresponding escaped form instead of creating an unintended HTML element. Also verify:

- order numbers with special characters;
- long product names;
- empty or multi-line lists;
- URLs generated from allowed domains;
- optional fields hidden appropriately;
- locale fallback working;
- total amounts and dates/times not formatted incorrectly.

### 15.3. Testing Mail Assembly

You can mock `JavaMailSender` and capture the sent `MimeMessage` to verify:

- `From`, `To`, `Reply-To`, and `Subject`;
- `text/plain` and `text/html` contain the same core information;
- attachments and Content-ID match the model/resource;
- charset is UTF-8 when Vietnamese characters are present.

For integration testing, a simulated SMTP server such as Mailpit or GreenMail helps inspect the raw message and preview it. It confirms submission to the test server, not delivery to a production Inbox.

## 16. Versioning Models and Templates

Templates can change over time: adding fields, renaming variables, changing layouts, or switching locales. If there are pending send jobs, a new template might no longer understand the old model.

Example:

~~~text
Template v1:
  customerName
  orderNumber
  totalText

Template v2:
  recipient.displayName
  order.reference
  totals.grandTotalText
  actions.orderUrl
~~~

If template v2 is deployed while the queue still has payloads matching the v1 structure, workers may render missing variables or fail.

Options:

- **Maintain backward compatibility:** the new template supports old fields while old jobs still exist.
- **Version templates/models:** jobs record `templateId` and `templateVersion`, and workers select the right version.
- **Render before enqueueing:** save an HTML/text snapshot if guaranteed unchanged content is needed.
- **Payload migration:** only use when there is a clear job-data migration plan.

Do not rename fields in the model and delete the old template immediately while pending jobs still use the old version. Queue retention, dead-letter queues, and retry schedules must also be factored into the template compatibility window.

## 17. Common Anti-Patterns

| Anti-pattern | Why It Causes Problems | Alternative |
| --- | --- | --- |
| Passing the entire JPA entity to the template | Field leakage, lazy loading, schema coupling | Dedicated DTO/model for email |
| One giant model for all email types | Many null fields and confusing logic | Separate model per email type |
| Variable names abbreviated after DB columns | Hard to read, template coupled to database | Names based on business semantics |
| Calculating totals in Thymeleaf | Mixes business logic with presentation | Calculate in domain/application service |
| Passing raw user-supplied HTML | Risk of malicious markup | Escape text or controlled allowlist sanitization |
| Using arbitrary URLs in the model | Can lead to phishing domains | Generate URLs from trusted base URI |
| Using one string for both HTML and plain text | Text version may show tags or miss content | Render both formats from the same model |
| Putting SMTP password into the context | Secrets appear in template/debug payloads | Secrets only in runtime configuration |
| Keeping a mutable model in a queue | Producer may modify content after enqueueing | Record/immutable snapshot and defensive copy |
| Not versioning templates | Old jobs are incompatible with new templates | Template version or content snapshot |
| Model contains overly sensitive data | Email, queue, and logs become unnecessary data stores | Data minimization and retention |
| Template querying the database directly | Rendering is hard to test, depends on transactions | Mapper creates model before rendering |

## 18. Process for Designing a Model for a New Template

When receiving a request to build an email, you can proceed in this order:

1. **Identify purpose and recipients:** what does this email notify about, and who is allowed to view it?
2. **Sketch the content:** define the heading, paragraphs, lists, CTA, and footer.
3. **List variables:** names, codes, monetary amounts, timestamps, URLs, display flags.
4. **Classify fields:** required/optional, data types, sensitive data, locale.
5. **Create DTO/record:** use meaningful types, nested models for lists, defensive copies where needed.
6. **Write mapper:** fetch data from domain, format, and build links from a trusted source.
7. **Put the model into the template context:** establish a clear variable naming contract.
8. **Render HTML and plain text:** use the same model so content does not diverge.
9. **Build MIME and send:** separate headers/recipients from the content model.
10. **Test and version:** test boundary data, locales, escaping, and pending jobs.

### 18.1. Sample Data Contract Table

Before writing code, you can write down the contract for the order confirmation email:

| Field | Type | Required | Source | Where Displayed |
| --- | --- | --- | --- | --- |
| `customerName` | `String` | Yes | Customer profile | Greeting |
| `orderNumber` | `String` | Yes | Order | Subject/content |
| `orderedAtText` | `String` | Yes | Creation time + timezone | Order details |
| `orderLines` | `List<OrderLineMailModel>` | Yes, may be empty per policy | Order details | Product table |
| `totalText` | `String` | Yes | Calculated and formatted total | Total |
| `orderUrl` | `String` or `URI` | Yes | Trusted base URL + public code | CTA |
| `showSupportInformation` | `boolean` | No | Product rules | Support section |

This contract can be stored alongside the template documentation or expressed in a Java record. When adding or changing fields, update the mapper, template, fixtures, and tests together.

## 19. Comprehensive Scenario: One Model Serving Multiple Presentations

Suppose a system sends an order confirmation via email. Building the model once:

~~~java
OrderConfirmationMailModel model = new OrderConfirmationMailModel(
        "Alice Nguyen",
        "A123",
        "12/11/2026 14:30 GMT+7",
        List.of(
                new OrderLineMailModel(
                        "Java Book",
                        "JAVA-01",
                        1,
                        "200.000 ₫",
                        "200.000 ₫"),
                new OrderLineMailModel(
                        "Shipping fee",
                        "SHIP",
                        1,
                        "20.000 ₫",
                        "20.000 ₫")
        ),
        "200.000 ₫",
        "20.000 ₫",
        "220.000 ₫",
        "https://app.company.example/orders/A123",
        true
);
~~~

From the same model:

- The HTML template displays the table, heading, colors, and view-order button.
- The plain-text renderer creates a bulleted list and full URLs.
- Mapper tests verify the order number, monetary amount, and link.
- Template tests verify that names with special characters are escaped.
- The queue can hold an immutable model snapshot and template version.
- Mail assembly creates a new `MimeMessage`, sets headers, and sends via `JavaMailSender`.

If the HTML is later changed from a table layout to a card layout, **the model does not necessarily have to change** because the meaning of the data remains the same. If business logic adds a "tracking number" field, only then do you extend the model and template contract accordingly.

This is the goal of a good data model: the template receives only the data needed for presentation, independent of the database, SMTP, or internal implementation details. When this boundary is clear, a Spring Mail application can grow to support more email templates, more locales, and more delivery channels while maintaining consistency, security, and testability.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`, and how messages are created.
- **Spring Boot Reference — Thymeleaf:** auto-configuration, template resolver, and template configuration.
- **Thymeleaf Documentation — Standard Dialect:** variable access, loops, conditionals, escaping, and URLs.
- **Java Language Specification / Java API:** records, immutable value types, `List.copyOf`, and date/time types.
- **Java API — `BigDecimal`, `Currency`, and `NumberFormat`:** storing and displaying currency.
- **RFC 2045–2049 — MIME:** representing plain text, HTML, and multipart content in email.
