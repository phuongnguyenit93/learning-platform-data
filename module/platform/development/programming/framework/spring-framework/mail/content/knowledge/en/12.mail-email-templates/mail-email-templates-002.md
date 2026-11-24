# Template Variables and Default Values

In an application that sends email using **Spring Framework Mail**, message content typically varies by recipient and event: user name, order number, expiration date, monetary amount, confirmation link, or support details. Hardcoding those values directly into Java strings forces code changes whenever content changes, while creating multiple email variants easily leads to scattered, hard-to-control logic.

**Email templates** solve this problem by separating presentation from data. A template contains placeholders to be substituted; the application prepares a **model/context** consisting of variables and renders it into the final content before sending via **JavaMailSender**. A variable may be required, may be optional, or may need a **default value** when data is not provided.

This topic focuses on how to declare and pass **template variables**, how to choose where to place default values, how to handle **missing/null/blank** values, and key considerations when using variables in HTML emails. Examples use **Thymeleaf** for illustration because it integrates well with the Spring ecosystem; the principles for data and fallbacks still apply to FreeMarker or another template engine, though variable syntax and default expressions will differ.

## 1. What Is a Template Variable?

A template is content with static parts and dynamic parts. Welcome email example:

~~~html
<html>
  <body>
    <h1>Welcome, <span th:text="${recipientName}">friend</span>!</h1>
    <p>Your account has been created successfully.</p>
    <p>Account code: <strong th:text="${accountCode}">ACC-000</strong></p>
  </body>
</html>
~~~

In the example:

- **recipientName** is the recipient name variable.
- **accountCode** is the account code variable.
- The expressions **${recipientName}** and **${accountCode}** access data in the Thymeleaf context.
- **th:text** instructs Thymeleaf to write the variable value as the text content of the element.
- The content inside the span or strong tags is a **fallback value in the template file** when viewing the HTML file directly or when Thymeleaf attributes have not been processed yet. When rendered successfully, th:text replaces that content with the evaluated value.

A template variable is not a Java variable sitting directly inside the HTML file. It is a **key name in the context** that the template engine looks up during rendering.

### Separating Three Components

~~~text
Business data
   |
   | recipientName = "Lan"
   | accountCode   = "ACC-1528"
   v
Template context / model
   |
   | recipientName -> "Lan"
   | accountCode   -> "ACC-1528"
   v
Email template
   |
   | ${recipientName}
   | ${accountCode}
   v
Rendered HTML/text
   |
   v
MimeMessage -> JavaMailSender -> SMTP
~~~

**Business data** is business information retrieved from a database or service. **Context** is the set of values the template is allowed to use. **Template** determines how they are presented. **Rendered content** is the complete string the application places into the MIME message.

Separating these parts helps:

- Change email content without modifying mail-sending logic.
- Use the same dataset to generate both HTML and plain-text versions.
- Validate required variables before sending.
- Apply default values consistently.
- Test templates independently of SMTP.

## 2. Passing Variables to a Template with Thymeleaf

With Thymeleaf, the application typically creates a **Context**, sets variables with **setVariable(...)**, and then calls **TemplateEngine.process(...)**.

~~~java
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class WelcomeTemplateRenderer {

    private final TemplateEngine templateEngine;

    public WelcomeTemplateRenderer(TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public String renderHtml(String recipientName, String accountCode) {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("recipientName", recipientName);
        context.setVariable("accountCode", accountCode);

        return templateEngine.process("mail/welcome", context);
    }
}
~~~

The template name **mail/welcome** is mapped by the resolver to the corresponding file, such as **templates/mail/welcome.html**, depending on the application's configuration. The actual path and file extension depend on the **ITemplateResolver** in use.

The template can read the variables:

~~~html
<p>Hello <span th:text="${recipientName}">friend</span>.</p>
<p>Account code: <span th:text="${accountCode}">ACC-000</span></p>
~~~

If **recipientName** has the value **Lan** and **accountCode** has the value **ACC-1528**, the rendered output is essentially:

~~~html
<p>Hello <span>Lan</span>.</p>
<p>Account code: <span>ACC-1528</span></p>
~~~

The template engine substitutes dynamic values into the right positions while preserving the static HTML structure.

### Variable Names Must Match Between Java and the Template

If Java passes:

~~~java
context.setVariable("recipientName", "Lan");
~~~

but the template writes:

~~~html
<span th:text="${receiverName}">friend</span>
~~~

then the two key names do not match. The template does not automatically infer **receiverName** from **recipientName**. Depending on the engine and expression, a nonexistent variable may evaluate to null/empty or raise an error when the expression accesses further properties. Therefore, variable names must be treated as a **contract between renderer and template**.

A useful convention:

| Variable Name | Meaning | Suggested Data Type |
| --- | --- | --- |
| **recipientName** | Recipient display name | String |
| **accountCode** | Account code | String |
| **activationUrl** | Activation link | Controlled URI or String |
| **expiresAt** | Expiration timestamp | Formatted Instant/ZonedDateTime |
| **totalAmount** | Monetary amount | BigDecimal |
| **currencyCode** | Currency code | String or enum |
| **items** | List of line items | List |
| **supportEmail** | Support email address | String |

Variable names should describe **business meaning**, not display position such as **firstLineText** or **greenButtonLabel**, unless that is genuinely UI-specific data. A stable name allows multiple templates to share a model without depending on a specific layout.

## 3. What Is a Default Value?

A default value is the value used when optional data **is not provided or does not have a useful value** under the chosen rules.

Example:

~~~text
recipientName = null
~~~

Instead of rendering:

~~~text
Hello null!
~~~

the application can display:

~~~text
Hello there!
~~~

Or when a specific support address is missing, the email can use a general support mailbox:

~~~text
If you need help, please contact support@example.test.
~~~

However, **not every variable should have a default**. If **activationUrl** is missing in an account activation email, substituting a dummy URL or an empty string can produce an unusable email. For required variables, the right behavior is usually to **reject rendering and report a data error**, rather than masking the error with a default value.

### Categorize Variables Before Choosing Defaults

| Variable Kind | Example | When Data Is Missing |
| --- | --- | --- |
| **Required** | activationUrl, orderId, verificationCode | Report an error and do not send an incomplete template |
| **Optional with sensible default** | recipientName, supportEmail | Use a business-accepted fallback value |
| **Optional where entire section can be hidden** | promotionCode, secondaryAddress | Do not render the related element if there is no value |
| **Business-allowed empty** | middleName, companyName | Display empty or omit without making the sentence awkward |
| **Typed data requiring formatting** | totalAmount, expiresAt | Do not replace with an arbitrary string; apply explicit locale/format |

A good default must be **semantically accurate**, not merely remove null from the template. For example, if a monetary amount is missing, displaying **0 VND** could mislead the recipient into thinking the order is free. If the expiration date is missing, displaying the current date is false information. In such cases, hide the section without data or refuse to send.

## 4. Distinguishing Missing, Null, Empty, and Blank

The states below are distinct:

| State | Example | Meaning |
| --- | --- | --- |
| **Missing** | Never called setVariable for recipientName | Key does not exist in context |
| **Null** | setVariable("recipientName", null) | Key is present but value is null |
| **Empty** | Empty string "" | String with length 0 |
| **Blank** | "   " or string with only tabs/spaces | Has characters but no useful content |
| **Present** | "Lan" | Has a displayable value |

Not all template engines handle these cases the same way. An expression may return null when a key is missing, whereas a deep property access like **customer.name** may fail if **customer** does not exist. Therefore, do not rely on accidental engine behavior to define your data policy.

### Blank Is Not Automatically the Same as Null

The check:

~~~java
if (recipientName == null) {
    recipientName = "there";
}
~~~

only handles null. If **recipientName** is a whitespace-only string, the email could still become:

~~~text
Hello    !
~~~

If business rules treat whitespace-only strings as missing data, normalize using **isBlank()** and **strip()**:

~~~java
String displayName =
        recipientName == null || recipientName.isBlank()
                ? "there"
                : recipientName.strip();
~~~

This is a decision of the **data preparation layer**, not automatic behavior of every template engine.

## 5. Placing Defaults in Java or in the Template?

There are two common places to supply default values:

1. **In Java before rendering**: the model already has normalized values, and the template focuses only on presentation.
2. **In the template**: display expressions choose a fallback value when a variable has no data.

Both approaches serve different purposes and can work together, but do not put the same policy in multiple places without good reason.

### Defaults in Java: Centralized Data Policy

~~~java
public record WelcomeMailModel(
        String recipientName,
        String accountCode,
        String supportEmail
) {
    public static WelcomeMailModel from(
            String recipientName,
            String accountCode,
            String supportEmail
    ) {
        String normalizedName =
                recipientName == null || recipientName.isBlank()
                        ? "there"
                        : recipientName.strip();

        if (accountCode == null || accountCode.isBlank()) {
            throw new IllegalArgumentException(
                    "accountCode is required"
            );
        }

        String normalizedSupportEmail =
                supportEmail == null || supportEmail.isBlank()
                        ? "support@example.test"
                        : supportEmail.strip();

        return new WelcomeMailModel(
                normalizedName,
                accountCode.strip(),
                normalizedSupportEmail
        );
    }
}
~~~

When rendering:

~~~java
WelcomeMailModel model = WelcomeMailModel.from(
        rawName,
        accountCode,
        configuredSupportEmail
);

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("recipientName", model.recipientName());
context.setVariable("accountCode", model.accountCode());
context.setVariable("supportEmail", model.supportEmail());
~~~

Advantages of this approach:

- **null/blank/default** rules live in one testable place.
- The template does not have to repeat conditions for the same variable in multiple places.
- Both HTML and plain-text versions receive the same normalized data.
- Required variables are validated before rendering, making it easy to return clear business errors.

This is usually the best choice for **values with business meaning**, such as a standard display name, default support address, or required order number.

### Defaults in the Template: Fallback for Presentation Purposes

Thymeleaf allows conditional expressions right at the display site:

~~~html
<p>
  Hello
  <span th:text="${recipientName != null ? recipientName : 'there'}">there</span>!
</p>
~~~

The expression above uses **recipientName** when non-null; if null, it uses the literal **there**. This is a presentation-layer fallback. It does not automatically handle whitespace-only strings.

If null or empty strings need to be handled, Thymeleaf provides the **#strings** utility. Example:

~~~html
<span th:text="${#strings.isEmpty(recipientName) ? 'there' : recipientName}">
  there
</span>
~~~

The expression **#strings.isEmpty(...)** handles empty values using Thymeleaf's utility; it does not replace the application's Java blank-string normalization policy. If **"   "** is also considered missing, normalize it before putting it into the context.

Template fallbacks fit **simple display phrasing**, such as a greeting that can use "there" when no name is available. They should not be the only place checking required values like confirmation URLs or monetary amounts.

### Which Should You Choose?

| Scenario | Where to Handle |
| --- | --- |
| Required variable must exist | Java/service/model validation |
| Normalizing null, blank, whitespace, formatting | Java before rendering |
| Business defaults shared across multiple templates | Java/model or a policy service |
| Fallback phrasing specific to one template | Template, if simple and clear |
| Showing/hiding an HTML section based on data | Template with conditionals |
| Values depending on locale, timezone, currency | Java/service or explicitly configured formatter |

A helpful rule of thumb is: **Java decides what data is allowed into the email; the template decides how to present that data**. You can keep small fallbacks in the template for resilience, but do not use fallbacks to hide an important data error.

## 6. Default Values in Thymeleaf

Thymeleaf uses **Standard Expressions** to read variables and evaluate expressions. Some commonly used patterns:

### Using the Conditional Operator

~~~html
<p th:text="${recipientName != null ? recipientName : 'there'}">
  Hello there
</p>
~~~

This is a clear approach when the condition only checks null.

### Using the Empty-String Check Utility

~~~html
<p th:text="${#strings.isEmpty(recipientName) ? 'there' : recipientName}">
  Hello there
</p>
~~~

Suitable when either null or empty is treated as missing. If data may contain whitespace, normalize in Java or use a check function matching your application's rules.

### Using the Elvis Expression for Concise Fallbacks

Thymeleaf supports the **Elvis operator** in Standard Expressions:

~~~html
<span th:text="${recipientName} ?: 'there'">there</span>
~~~

This expression picks the left-hand value if present, otherwise uses the right-hand default expression. Elvis syntax can be shorter than a ternary conditional, but in templates maintained by multiple people, prefer readable syntax and test against the Thymeleaf version in use.

### Fallback for Nested Properties

Suppose the context has a **customer** variable with a **displayName** property. If customer always exists but displayName can be null:

~~~html
<span th:text="${customer.displayName != null ? customer.displayName : 'there'}">
  there
</span>
~~~

If **customer** itself can be null, accessing **customer.displayName** may fail before the fallback applies, depending on how the expression is evaluated. It is safer to prepare a clearly structured model in Java, or check the parent object first:

~~~html
<span th:text="${customer != null and customer.displayName != null
                  ? customer.displayName
                  : 'there'}">
  there
</span>
~~~

In long templates, nested conditions reduce readability. If multiple dependent properties exist, prepare a display variable such as **recipientName** in Java instead of forcing every template to understand the entire business object structure.

## 7. Default Does Not Mean Hiding an Element

There are two different needs:

- **Replace a missing value with default content.**
- **Do not display that section when there is no data.**

For example, a promotion code only appears when a campaign is active:

~~~html
<p th:if="${promotionCode != null and !#strings.isEmpty(promotionCode)}">
  Promo code:
  <strong th:text="${promotionCode}">WELCOME</strong>
</p>
~~~

If there is no code, the entire paragraph is not rendered. This differs from:

~~~html
<p>
  Promo code:
  <strong th:text="${promotionCode != null ? promotionCode : 'None'}">
    None
  </strong>
</p>
~~~

In the second example, the message still appears and displays **None**. Both can be right depending on the intended user experience.

### Using Conditionals with Boolean Variables

~~~html
<p th:if="${showSupportInstructions}">
  If you need assistance, please contact support.
</p>
~~~

Do not use a default value of **true** for a flag controlling a sensitive section if visibility depends on permissions or business state. Determine the boolean in Java from checked data and policies.

### Using Defaults for Lists

If the item list is empty, do not invent a dummy row like **"No products"** if the email is confirming an order where missing data may indicate an error. You can:

- Reject rendering if the list is required data.
- Display a sentence like **"No line items"** if business rules truly allow an empty list.
- Hide the entire table if the table is optional.

Conditional example:

~~~html
<table th:if="${items != null and !items.isEmpty()}">
  <tr th:each="item : ${items}">
    <td th:text="${item.name}">Product name</td>
    <td th:text="${item.quantity}">1</td>
  </tr>
</table>
<p th:if="${items == null or items.isEmpty()}">
  No line items.
</p>
~~~

The snippet above illustrates two display branches. If the list must have at least one line, validate in Java and do not render the "No line items" branch to mask an error.

## 8. Preparing a Clear Model Before Rendering

An email template can use many variables. If **setVariable(...)** is called per variable scattered across multiple services, key names and defaults easily drift across flows. You should create a dedicated model for each email type.

~~~java
import java.math.BigDecimal;
import java.time.ZonedDateTime;
import java.util.List;

public record OrderMailModel(
        String recipientName,
        String orderNumber,
        BigDecimal totalAmount,
        String currencyCode,
        ZonedDateTime createdAt,
        List<OrderMailItem> items,
        String supportEmail
) {
    public OrderMailModel {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                    "orderNumber is required"
            );
        }
        if (totalAmount == null || currencyCode == null
                || currencyCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing total amount or currency"
            );
        }

        recipientName =
                recipientName == null || recipientName.isBlank()
                        ? "there"
                        : recipientName.strip();

        supportEmail =
                supportEmail == null || supportEmail.isBlank()
                        ? "support@example.test"
                        : supportEmail.strip();

        items = items == null ? List.of() : List.copyOf(items);
    }
}

public record OrderMailItem(
        String name,
        int quantity,
        BigDecimal lineTotal
) {
}
~~~

This is an illustrative Java record; in projects using an older Java version, you can use an ordinary immutable class. The record compact constructor validates required data, normalizes the display name and support address, and replaces a null list with an empty list.

Important consideration: if **empty items** is an invalid order state, do not silently convert null to an empty list. The model must reflect real business rules. Normalization is only appropriate when the default has valid semantic meaning.

Render model:

~~~java
Context context = new Context(locale);
context.setVariable("order", orderMailModel);
String html = templateEngine.process("mail/order-confirmation", context);
~~~

The template accesses:

~~~html
<p>Hello <span th:text="${order.recipientName}">there</span>.</p>
<p>
  Order:
  <strong th:text="${order.orderNumber}">ORD-000</strong>
</p>
<p>
  Support:
  <span th:text="${order.supportEmail}">support@example.test</span>
</p>
~~~

Instead of creating dozens of top-level keys like **recipientName**, **orderNumber**, **totalAmount**, the **order** model groups data belonging to the same business concept. For large templates, this reduces the risk of key collisions and clarifies data provenance.

## 9. Typed Variables Must Be Formatted Before Display

Not every variable is a String. An email can contain:

- Monetary amounts as **BigDecimal**.
- Dates/times as **Instant**, **LocalDate**, or **ZonedDateTime**.
- Quantities as integers.
- Statuses as enums.
- Lists of product lines.

Do not convert everything into strings immediately when fetching data from the database. Keeping explicit data types aids validation and proper locale-based formatting.

### Monetary Amounts

Monetary amount example:

~~~java
BigDecimal totalAmount = new BigDecimal("1250000.50");
String currencyCode = "VND";
~~~

Do not use a default of **0** if a missing totalAmount signals a data error. If a required value is absent, reject rendering. When data is present, format currency according to locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public String formatMoney(
        BigDecimal amount,
        String currencyCode,
        Locale locale
) {
    if (amount == null || currencyCode == null) {
        throw new IllegalArgumentException(
                "Missing amount or currencyCode"
        );
    }

    NumberFormat format = NumberFormat.getCurrencyInstance(locale);
    format.setCurrency(Currency.getInstance(currencyCode));
    return format.format(amount);
}
~~~

The output depends on locale and currency. **vi-VN** may format VND differently from **en-US**; do not manually concatenate number strings with currency suffixes if you want to support multiple languages. In addition, decimal-digit rules also depend on the currency.

Another option is passing **BigDecimal** and the currency code into the context and using a formatter/utility configured in the template. However, formatting in Java allows reusing the result for both HTML and plain text and is easier to test. What matters is keeping locale and currency consistent.

### Dates and Times

A date/time stored as **Instant** is a global point in time; when displaying to the recipient, you need to determine the **timezone** and **locale**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public String formatExpiry(
        Instant expiresAt,
        ZoneId recipientZone,
        Locale locale
) {
    if (expiresAt == null) {
        throw new IllegalArgumentException(
                "expiresAt is required"
        );
    }

    DateTimeFormatter formatter = DateTimeFormatter
            .ofPattern("dd/MM/yyyy HH:mm z", locale)
            .withZone(recipientZone);

    return formatter.format(expiresAt);
}
~~~

If the expiration date is security-sensitive information or affects usage rights, never use a default date just so the template renders. You must pass the exact timestamp determined by business logic.

### Boolean and Enum Variables

For boolean flags, define variable names with clear meaning:

- **showSupportInstructions**: whether to display support instructions.
- **isTrialAccount**: whether the account is a trial account.
- **paymentReceived**: whether payment has been received.

A missing boolean variable should not automatically become **true** if doing so could expose content or make a false assertion. For status enums, map to a display label in Java or an explicit message table instead of rendering technical enum names like **PAYMENT_PENDING_REVIEW** directly to customers.

## 10. Locale and Language-Specific Default Variables

An email template can be sent to recipients in multiple languages. In that case, defaults can also depend on locale:

| Locale | Suggested Default Name |
| --- | --- |
| **vi-VN** | bạn |
| **en-US** | there |
| **fr-FR** | bonjour |

This is only a phrasing example; real content should be authored appropriately for language and culture. Do not hardcode a fixed Vietnamese string in Java and send the same template for every locale.

Thymeleaf Context can accept a locale:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Context context = new Context(locale);
context.setVariable("recipientName", displayName);
~~~

The template engine can use this locale for built-in message resolution and formatter mechanisms. For multi-language emails, manage the **template**, **message bundle**, **date/currency formats**, and **default text** under the same locale.

### Using Message Bundles for Default Phrases

Instead of hardcoding fallback phrasing in the template, you can put fallback labels in a locale-specific message bundle. Vietnamese bundle example:

~~~properties
mail.greeting.defaultName=bạn
mail.support.label=Bộ phận hỗ trợ
~~~

And the English bundle:

~~~properties
mail.greeting.defaultName=there
mail.support.label=Support team
~~~

The template can use Thymeleaf's message expression:

~~~html
<span th:text="${recipientName != null
                  ? recipientName
                  : #messages.msg('mail.greeting.defaultName')}">
  there
</span>
~~~

The exact organization depends on the application's **MessageSource** and template resolver configuration. The goal is to place **language-dependent wording** in translation sources rather than scattering strings across Java services.

### Default Locale Must Be Chosen Deliberately

If the recipient has no locale, the application needs a defined policy:

- Use the locale selected by the user in their profile.
- Use the locale associated with the transaction or product.
- Use the system's published default locale.

Do not guess the locale solely from the email address or server timezone. If choosing **vi-VN** as the default, pass that locale into Context and use the same locale when formatting dates/currency, avoiding emails with a Vietnamese greeting and dates formatted in a different locale.

## 11. HTML Escaping: Dynamic Variables Must Not Become Markup

When inserting variables into an HTML email, distinguish **text content** from **HTML structure**.

Suppose a user has the name:

~~~text
Lan <Manager> & Co
~~~

If this string is inserted directly into HTML as markup, characters **<**, **>**, and **&** can be interpreted as syntax. The template may render incorrectly or produce unintended content.

In Thymeleaf, **th:text** is the appropriate way to display a value as text and perform HTML escaping:

~~~html
<p>Hello <span th:text="${recipientName}">there</span>.</p>
~~~

If the value is **Lan <Manager> & Co**, the escaped HTML output is equivalent to:

~~~html
<p>Hello <span>Lan &lt;Manager&gt; &amp; Co</span>.</p>
~~~

Browsers/email clients display the characters back as text content rather than treating them as HTML tags.

### Avoid Using th:utext with Untrusted Data

**th:utext** renders HTML content without escaping the way th:text does. If data comes from users, a database that may hold user-entered data, or an external system, passing it directly into **th:utext** can create unwanted markup and risk malicious HTML content.

Only use unescaped HTML when the value was generated by a trusted template source or has passed through a sanitization process appropriate for the purpose. For user names, addresses, notes, and free-form input, prefer **th:text**.

### Defaults Must Also Be Escaped According to Context

A default value like **there** is a safe literal in the example. But if the default is fetched from configuration or a database, it still needs to be handled according to the target context. Not every string escaped for HTML text is safe when placed into:

- HTML attributes such as **href** or **title**.
- URL.
- JavaScript or CSS.
- Unescaped HTML content.

**HTML text escaping does not replace URL validation**. For links in emails, restrict schemes (usually HTTPS), control domains per business rules, and encode attribute values properly. Do not put an arbitrary user-provided URL into href just because the template used th:text at the display site.

## 12. URL Variables and Safe Default Values

A confirmation email usually has an **activationUrl** variable. This is a **required** variable because without it, the recipient cannot perform the action.

~~~java
if (activationUrl == null || activationUrl.isBlank()) {
    throw new IllegalArgumentException(
            "Cannot render email because activationUrl is missing"
    );
}
~~~

Do not default to a generic URL if it is not a real confirmation URL. The recipient might click an unrelated page and think they completed the action.

In the template:

~~~html
<a th:href="${activationUrl}" th:text="#{mail.activate.button}">
  Activate account
</a>
~~~

Here **activationUrl** is placed into the href attribute, while the button label comes from the message bundle. The application must generate the URL from a trusted source, ensure the right scheme and host, keep the token time-limited, and avoid logging it. The template only presents the prepared URL.

### URL Values Should Not Fall Back to an Empty String

If you use:

~~~html
<a th:href="${activationUrl ?: '#'}">Activate</a>
~~~

then the email still has a button, but the button performs no valid action. This is an **error-hiding** fallback. For required variables, it is better to stop rendering, log a template data error, and avoid sending an unusable email.

## 13. Using the Same Model for HTML and Plain Text

An email may need two content versions: **text/plain** and **text/html**. Do not create two independent sets of variables, because default values between the two versions can drift apart.

Recommended flow:

~~~text
Business data
    |
    v
Validate required fields
    |
    v
Normalize optional fields and defaults
    |
    v
One mail model
    |
    +--> Render HTML template
    |
    '--> Render plain text template
              |
              v
       MimeMessageHelper.setText(plain, html)
              |
              v
       JavaMailSender.send(...)
~~~

Example:

~~~java
Context htmlContext = new Context(locale);
htmlContext.setVariable("order", orderMailModel);

Context textContext = new Context(locale);
textContext.setVariable("order", orderMailModel);

String html = htmlTemplateEngine.process(
        "mail/order-confirmation",
        htmlContext
);
String plain = textTemplateEngine.process(
        "mail/order-confirmation",
        textContext
);
~~~

The two templates can use the same variable names and the same model. The **template mode** configuration differs: the HTML resolver produces HTML, while the text resolver produces plain text. Within an application, you can use two resolvers/engines or configure the template engine in a way suitable for your template structure.

After rendering:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.test");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plain, html);

mailSender.send(message);
~~~

**setText(plain, html)** creates alternative content parts in a MIME message. Both versions must use the same values for **recipientName**, **orderNumber**, **totalAmount**, **activationUrl**, and related data. If the plain version says "expires in 15 minutes" while HTML says "30 minutes", that is a model/template creation bug rather than an SMTP error.

### Display Fallbacks Must Be Consistent

If **recipientName** is missing, normalize to **there** in the model before creating the two Contexts. Do not let HTML use the fallback **there** while plain text renders **null**. Likewise, if there is no promotion code, both versions must either hide the promotion section or display the corresponding business message consistently.

## 14. Variable Syntax and Defaults Depend on the Template Engine

Variable names and default rules are not universal Java or Spring Mail syntax. They belong to the **template engine** the application chooses.

| Engine | Variable Reading Syntax | Fallback Illustration | Notes |
| --- | --- | --- | --- |
| **Thymeleaf** | Dollar expression in Standard Expression | Ternary conditional or Elvis expression | Has Standard Dialect, utilities, and message expressions |
| **FreeMarker** | Dollar expression in FTL | Default operator using exclamation mark | Missing/null rules differ from Thymeleaf |
| **Mustache** | Double curly braces | Section/inverted section or default from model | Logic syntax in templates is kept minimal |

FreeMarker example:

~~~ftl
<p>Hello ${recipientName!"there"}!</p>
<p>Order number: ${orderNumber!"No code yet"}</p>
~~~

In FreeMarker, the **!** operator provides a fallback value when the left-hand expression is missing/null according to engine rules. It does not automatically treat whitespace-only strings as missing. If blank handling is needed, normalize data before rendering or use an expression/utility appropriate for your FreeMarker version.

Mustache examples usually rely on a model that already has defaults:

~~~mustache
<p>Hello {{recipientName}}!</p>
{{#showPromotion}}
  <p>Promo code: {{promotionCode}}</p>
{{/showPromotion}}
~~~

Mustache does not use fallback syntax like Thymeleaf or FreeMarker in ordinary variable expressions. The application should pass a normalized **recipientName** and a **showPromotion** flag in the model.

**Do not copy default syntax from one engine to another.** A Thymeleaf file may contain **th:text**, whereas FreeMarker uses its own directives and syntax. The template resolver and template mode must also match the file being rendered.

### Spring Placeholders Are Not the Same as Email Template Variables

In Spring configuration:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST:smtp.example.test}
~~~

is Spring's **property placeholder** mechanism for reading environment configuration and default values. It is not a Thymeleaf template variable.

In email templates, dollar expressions are used to read the context. Even though the notation looks similar, **the data source and evaluation timing differ**:

- Spring property placeholders are resolved during bean binding/configuration.
- Template variables are resolved when rendering content for a specific email.
- MIME headers/body are created only after the template has rendered to a string.

Do not put template syntax into YAML expecting Spring to substitute recipient variables; nor should you expect the template engine to read every environment variable unless the application explicitly passes them into the context.

## 15. Avoid Passing an Overly Broad Model to the Template

A convenient yet uncontrolled approach is putting the entire entity/database object into the context:

~~~java
context.setVariable("user", userEntity);
~~~

That can let the template access many properties unrelated to the email, such as internal states, private information, or lazy-loading relationships. It also couples email content directly to the entity structure.

Instead, create a **mail view model** containing only the necessary data:

~~~java
public record PasswordResetMailModel(
        String recipientName,
        String resetUrl,
        String expiresInText,
        String supportEmail
) {
}
~~~

This model does not need to contain passwords, internal tokens that must not be exposed, or the entire account object. **resetUrl** is a URL generated according to security policy; the template only receives the URL to display.

Benefits:

- The template sees only the exact data needed for presentation.
- Easy to validate required variables and defaults.
- Reduces coupling to entities, ORM, and lazy-loading.
- Avoids accidentally putting private fields into HTML emails.
- The model can be tested without connecting to a database.

### Do Not Let Templates Access Services or Databases Directly

Templates should render from **prepared data**, not execute database queries, call external APIs, or generate tokens while evaluating expressions. Those tasks must happen in a service before rendering.

For example, instead of letting the template look up the support address by tenant, the service should resolve the tenant, determine supportEmail, and pass the variable into the model. This causes data errors to surface at a clear boundary instead of occurring mid-way through HTML rendering.

## 16. Validate Required Variables Before Rendering

A template may depend on multiple variables. Define a contract for each template:

| Template | Required Variables | Optional/Default Variables | Hideable Sections |
| --- | --- | --- | --- |
| **mail/welcome** | accountCode | recipientName, supportEmail | promotion |
| **mail/password-reset** | resetUrl, expiresInText | recipientName | support instructions |
| **mail/order-confirmation** | orderNumber, totalAmount, currencyCode | recipientName, supportEmail | note, promotion |

This is an example of a **template contract**, not automatic Thymeleaf metadata. You can express the contract via record/constructor validation, or a validator class before calling TemplateEngine.

~~~java
public record PasswordResetMailModel(
        String recipientName,
        String resetUrl,
        String expiresInText,
        String supportEmail
) {
    public PasswordResetMailModel {
        if (resetUrl == null || resetUrl.isBlank()) {
            throw new IllegalArgumentException(
                    "resetUrl is required"
            );
        }
        if (expiresInText == null || expiresInText.isBlank()) {
            throw new IllegalArgumentException(
                    "expiresInText is required"
            );
        }

        recipientName =
                recipientName == null || recipientName.isBlank()
                        ? "there"
                        : recipientName.strip();

        supportEmail =
                supportEmail == null || supportEmail.isBlank()
                        ? "support@example.test"
                        : supportEmail.strip();
    }
}
~~~

If a valid model is constructed successfully, the template can rely on those invariants. This keeps the template cleaner and avoids repeating conditions for required variables.

### Missing Variables and Wrong Property Paths

A template might reference:

~~~html
<span th:text="${order.customer.displayName}">there</span>
~~~

But the model only passes:

~~~java
context.setVariable("order", orderSummary);
~~~

If **orderSummary** has no **customer** or **displayName**, the expression may not evaluate as expected. Adding a default at the end does not always fix an invalid property path.

To reduce errors:

- Use a mail model with a stable structure instead of an entity that changes constantly.
- Name variables and properties according to a consistent convention.
- Validate required properties in the constructor or validator.
- Render the template in tests with complete sample data.
- Avoid deep property-chain access when the template only needs a normalized value.

## 17. Connecting the Template Renderer with JavaMailSender

A template engine only generates content. **JavaMailSender** remains responsible for sending the MIME message. A service usually has two parts: rendering the template and sending the email.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.Locale;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class PasswordResetMailService {

    private final TemplateEngine templateEngine;
    private final JavaMailSender mailSender;

    public PasswordResetMailService(
            TemplateEngine templateEngine,
            JavaMailSender mailSender
    ) {
        this.templateEngine = templateEngine;
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            PasswordResetMailModel model,
            Locale locale
    ) throws MessagingException {

        Context context = new Context(locale);
        context.setVariable("mail", model);

        String html = templateEngine.process(
                "mail/password-reset",
                context
        );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("security@example.test");
        helper.setTo(recipient);
        helper.setReplyTo(model.supportEmail());
        helper.setSubject("Password reset request");
        helper.setText(html, true);

        mailSender.send(message);
    }
}
~~~

Corresponding template:

~~~html
<html>
  <body>
    <h1>Reset password</h1>
    <p>Hello <span th:text="${mail.recipientName}">there</span>.</p>
    <p>The link is valid for
      <strong th:text="${mail.expiresInText}">15 minutes</strong>.
    </p>
    <p>
      <a th:href="${mail.resetUrl}">Reset password</a>
    </p>
    <p>
      Support:
      <span th:text="${mail.supportEmail}">support@example.test</span>
    </p>
  </body>
</html>
~~~

In the example:

1. **PasswordResetMailModel** validates required variables and normalizes optional values.
2. **Context** passes the model under the key **mail**.
3. **TemplateEngine.process(...)** generates the complete HTML.
4. **MimeMessageHelper.setText(html, true)** marks the body as HTML.
5. **JavaMailSender.send(...)** forwards the message to the transport.

This is an HTML-only example to clarify the rendering and sending process. If the email needs a plain-text fallback, render a text template as well and use **setText(plain, html)** in an appropriate multipart mode.

### Why Validate the Model Before Calling process?

If the template is missing **resetUrl**, the content could render as an empty or broken link. Pre-validation ensures errors are reported at the data layer, where there is enough context to generate the URL or reject the request. The template engine cannot invent a valid confirmation token just because a variable is null.

## 18. Testing Template Variables and Defaults Without Sending Email

Template rendering can be tested independently of SMTP. This helps catch:

- Variable names in Java not matching names used in the template.
- Default values not appearing when null/blank.
- A required variable missing.
- Incorrect HTML escaping.
- Optional sections not hidden as expected.
- Locale not passed properly.

Renderer test example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

class WelcomeTemplateTest {

    private final TemplateEngine templateEngine = createTestEngine();

    @Test
    void rendersNameAndAccountCode() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("recipientName", "Lan");
        context.setVariable("accountCode", "ACC-1528");

        String html = templateEngine.process(
                "mail/welcome",
                context
        );

        assertTrue(html.contains("Lan"));
        assertTrue(html.contains("ACC-1528"));
    }

    @Test
    void displaysFallbackNameWhenNameIsNull() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("recipientName", null);
        context.setVariable("accountCode", "ACC-1528");

        String html = templateEngine.process(
                "mail/welcome",
                context
        );

        assertTrue(html.contains("there"));
    }
}
~~~

**createTestEngine()** is a helper that sets up TemplateEngine and the resolver for tests, depending on how the application configures Thymeleaf. The snippet above illustrates the testing idea; a complete test needs the project's exact template resolver and resource paths.

### Checking Escaping

~~~java
context.setVariable("recipientName", "Lan <Manager> & Co");
String html = templateEngine.process("mail/welcome", context);

assertTrue(html.contains("Lan &lt;Manager&gt; &amp; Co"));
~~~

This test confirms the variable is displayed as escaped text when the template uses **th:text**. If the template switches to **th:utext**, expectations must change and an appropriate HTML input-control process must be in place.

### Checking Required Variables

If the model rejects a null **resetUrl**, you can test constructor/model validation:

~~~java
assertThrows(
        IllegalArgumentException.class,
        () -> new PasswordResetMailModel(
                "Lan",
                " ",
                "15 minutes",
                "support@example.test"
        )
);
~~~

This is a test for the **data contract**, not an SMTP test. Separating model, template, and mail transport tests helps pinpoint where a failure comes from.

## 19. Grouping Multiple Variables in Context

When a template has only a few variables, calling **setVariable(...)** per key is quite readable. For larger models, you can group data into an object or map.

Example using an object:

~~~java
Context context = new Context(locale);
context.setVariable("order", orderMailModel);
context.setVariable("recipient", recipientView);
context.setVariable("supportEmail", supportEmail);
~~~

Example using a map:

~~~java
Map<String, Object> variables = new HashMap<>();
variables.put("recipientName", displayName);
variables.put("accountCode", accountCode);
variables.put("supportEmail", supportEmail);

Context context = new Context(locale);
context.setVariables(variables);
~~~

A Map is suitable when a model is built dynamically or when a single renderer is shared across multiple templates. However, if there are many keys, a strongly typed object model is usually easier to read and safer.

### Note on Map.of(...)

Java's **Map.of(...)** does not allow null keys or values. Therefore:

~~~java
Map<String, Object> variables = Map.of(
        "recipientName", recipientName,
        "accountCode", accountCode
);
~~~

can throw **NullPointerException** if recipientName is null. If optional data may be null, normalize beforehand, use an object model, or use a map that can hold nulls during preparation. Do not let a Map.of error be mistaken for a template engine bug.

### Avoid Key Name Collisions

If the context sets:

~~~java
context.setVariable("name", recipientName);
context.setVariable("name", companyName);
~~~

then the later assignment overwrites the earlier value. The template will see only one **name** key, making results hard to explain.

Use names that express exact meaning:

- **recipientName** for the recipient.
- **companyName** for the business.
- **supportContactName** for the support contact person.

If a nested model is used, such as **mail.recipient.name** and **mail.company.name**, the template can express relationships more clearly.

## 20. Common Mistakes When Using Template Variables and Defaults

### Mistake 1: Not Passing a Variable Yet Expecting the Template to Know the Data

The template uses **recipientName**, but the renderer never puts that key into Context. The template engine cannot automatically pull a name from the SMTP recipient or infer it from the email address.

**How to handle:** define the model and context contract; pass the right variable or replace the template with real data from a clear source.

### Mistake 2: Using a Default for a Required Variable

If **activationUrl** is missing, falling back to the homepage URL can produce an email that looks valid but cannot perform the confirmation action.

**How to handle:** validate required variables in Java; do not render or send if data is missing.

### Mistake 3: Checking Only Null and Ignoring Blank

A string **"   "** is non-null and can produce a blank greeting.

**How to handle:** decide whether blank is considered missing; if so, use **isBlank()** and **strip()** in the normalization layer.

### Mistake 4: Defaults Differing Between HTML and Plain Text

HTML displays **there**, while plain text displays **null** or an empty string.

**How to handle:** normalize once in the mail model and share it across both renderers.

### Mistake 5: Copying Syntax from Another Template Engine

FreeMarker's default expression is not Thymeleaf syntax; Mustache syntax is different again.

**How to handle:** identify the template engine and version in use, and write expressions in that engine's dialect.

### Mistake 6: Using th:utext for User Names or Notes

Data can be interpreted as HTML instead of being displayed as text.

**How to handle:** prefer **th:text** for text values; only use unescaped HTML with properly controlled/sanitized content.

### Mistake 7: Formatting Dates or Money with Arbitrary Defaults

Displaying **0 VND** when an amount is missing, or displaying today's date when an expiration date is missing, can mislead recipients.

**How to handle:** classify required and optional data; format according to locale/timezone, and never replace missing business values with fake numbers or dates.

### Mistake 8: Using the Entire Entity as the Model

The template may accidentally access sensitive attributes or unnecessary database relationships.

**How to handle:** create a mail view model containing only the fields needed for display.

### Mistake 9: Creating a URL Fallback with #

The button still appears but performs no action.

**How to handle:** required URLs must be constructed and validated in Java; if the URL is missing, stop rendering.

### Mistake 10: Assuming Successful Rendering Means the Email Was Sent

TemplateEngine only generates an HTML/text string. It does not connect to SMTP and does not confirm mail delivery.

**How to handle:** separate rendering status from sending status. Only after rendering does the application build MimeMessage and call JavaMailSender.

## 21. Template Variable Processing Flow in a Mail Job

A flow can be organized as follows:

~~~text
Receive business event
       |
       v
Fetch data from service/repository
       |
       v
Create mail view model
       |
       +--> Validate required variables
       |
       +--> Normalize null/blank
       |
       +--> Select locale/timezone/currency
       |
       +--> Compute valid defaults
       |
       v
Create template Context
       |
       v
Render HTML and/or plain text
       |
       v
Create MimeMessage
       |
       v
JavaMailSender.send(...)
       |
       v
Record submit status and handle errors
~~~

Each step has a clear responsibility:

| Step | Responsibility |
| --- | --- |
| Fetch data | Read business information from a defined source |
| Mail view model | Restrict data allowed to appear in the message |
| Validation | Reject when required variables are missing or invalid |
| Normalization | Handle null/blank and optional values per policy |
| Formatting | Standardize dates, currencies, and quantities by locale |
| Context | Pass the model into the template engine under consistent key names |
| Render | Generate HTML/plain-text strings |
| MIME creation | Package content and attachments if any |
| Sending | Submit message via JavaMailSender |

Do not mix all steps into one long string-concatenation block. When a template does not render properly, you can inspect the model first; when MIME is wrong, inspect the rendered message; when SMTP fails, check the exception and transport.

## 22. Self-Check Through Scenarios

### Scenario A — Null Recipient Name

The model receives **recipientName = null**. The email needs a natural greeting.

**Question:** where should this be handled?

**Answer:** if the default **there** is a general policy, normalize in the Java mail model so both HTML and plain text share it. The template can add a small fallback as a presentation safeguard.

### Scenario B — Whitespace-Only Recipient Name

**Question:** is checking **recipientName != null** enough?

**Answer:** no. A blank string is still non-null. If blank is treated as missing, use **isBlank()** and normalize with **strip()**.

### Scenario C — Missing activationUrl

**Question:** should the homepage URL be used as the default so the email still sends?

**Answer:** no, unless the homepage is genuinely the intended business action. A confirmation email needs a valid URL; if the URL is missing, stop rendering and report a data error.

### Scenario D — No promotionCode

**Question:** should you display "No code" or hide the whole section?

**Answer:** it depends on product copy. If the promo code is optional information, you can hide the whole section. If the recipient needs to know no promotion applies, display a clear sentence. Both approaches must stay consistent between HTML and plain text.

### Scenario E — HTML and Plain Text Using Two Separate Contexts

**Question:** can you normalize the name in the HTML context and not normalize it in the text context?

**Answer:** no. Both Contexts should receive the same normalized mail model; they differ only in how they render.

### Scenario F — Name Contains Angle Brackets

**Question:** should you strip **<** and **>** from a user's name before rendering?

**Answer:** no need to strip arbitrarily. When displaying as text, use an HTML escaping mechanism such as **th:text** to preserve meaning without interpreting the string as markup. If specific name-data rules exist, apply them in a separate validation layer.

### Scenario G — Different Default Names by Language

**Question:** should you hardcode "there" in every template?

**Answer:** not if the system sends in multiple languages. Select the locale before rendering and pull the default from a message bundle or locale-aware model.

### Scenario H — Missing Expiration Date Variable

**Question:** can you use the current date to avoid a template error?

**Answer:** not if the expiration date affects usage rights. This is required data; you must obtain the exact timestamp from business logic or stop sending.

### Scenario I — Template Uses FreeMarker Syntax in Thymeleaf

**Question:** why doesn't the default work?

**Answer:** the syntax belongs to a different engine. Verify the exact template engine, resolver, and dialect in use; write fallback expressions matching the engine actually rendering the file.

## 23. Principles to Remember

~~~text
Template variable
    -> data key in Context/model

Default value
    -> use only when optional data is missing

Missing / null / empty / blank
    -> distinct states requiring an explicit policy

Required variable
    -> validate in Java; do not replace with dummy values

Optional variable
    -> normalize/default or hide the display section

HTML text
    -> use th:text to escape text content

HTML URL
    -> control scheme/domain and generate URLs in Java

HTML + plain text
    -> use the same normalized mail model

Template engine
    -> variable/default syntax depends on Thymeleaf, FreeMarker, Mustache...

JavaMailSender
    -> send the MIME message only after content has rendered
~~~

**Template variables** are the bridge between business data and email content; **default values** help handle optional fields naturally when data is absent. To avoid sending malformed messages, distinguish missing/null/empty/blank, validate required variables, normalize defaults in the model, use syntax matching the template engine, and escape data for HTML context. When both plain text and HTML exist, use the same model so both versions stay consistent before placing content into **MimeMessage** and sending via **JavaMailSender**.

## 9. Typed Variables Must Be Formatted Before Display

Not every variable is a String. An email can contain:

- Monetary amounts as **BigDecimal**.
- Dates/times as **Instant**, **LocalDate**, or **ZonedDateTime**.
- Quantities as integers.
- Statuses as enums.
- Lists of product lines.

Do not convert everything into strings immediately when fetching data from the database. Keeping explicit data types aids validation and proper locale-based formatting.

### Monetary Amounts

Monetary amount example:

~~~java
BigDecimal totalAmount = new BigDecimal("1250000.50");
String currencyCode = "VND";
~~~

Do not use a default of **0** if a missing totalAmount signals a data error. If a required value is absent, reject rendering. When data is present, format currency according to locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public String formatMoney(
        BigDecimal amount,
        String currencyCode,
        Locale locale
) {
    if (amount == null || currencyCode == null) {
        throw new IllegalArgumentException(
                "Missing amount or currencyCode"
        );
    }

    NumberFormat format = NumberFormat.getCurrencyInstance(locale);
    format.setCurrency(Currency.getInstance(currencyCode));
    return format.format(amount);
}
~~~

The output depends on locale and currency. **vi-VN** may format VND differently from **en-US**; do not manually concatenate number strings with currency suffixes if you want to support multiple languages. In addition, decimal-digit rules also depend on the currency.

Another option is passing **BigDecimal** and the currency code into the context and using a formatter/utility configured in the template. However, formatting in Java allows reusing the result for both HTML and plain text and is easier to test. What matters is keeping locale and currency consistent.

### Dates and Times

A date/time stored as **Instant** is a global point in time; when displaying to the recipient, you need to determine the **timezone** and **locale**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public String formatExpiry(
        Instant expiresAt,
        ZoneId recipientZone,
        Locale locale
) {
    if (expiresAt == null) {
        throw new IllegalArgumentException(
                "expiresAt is required"
        );
    }

    DateTimeFormatter formatter = DateTimeFormatter
            .ofPattern("dd/MM/yyyy HH:mm z", locale)
            .withZone(recipientZone);

    return formatter.format(expiresAt);
}
~~~

If the expiration date is security-sensitive information or affects usage rights, never use a default date just so the template renders. You must pass the exact timestamp determined by business logic.

### Boolean and Enum Variables

For boolean flags, define variable names with clear meaning:

- **showSupportInstructions**: whether to display support instructions.
- **isTrialAccount**: whether the account is a trial account.
- **paymentReceived**: whether payment has been received.

A missing boolean variable should not automatically become **true** if doing so could expose content or make a false assertion. For status enums, map to a display label in Java or an explicit message table instead of rendering technical enum names like **PAYMENT_PENDING_REVIEW** directly to customers.

## 10. Locale and Language-Specific Default Variables

An email template can be sent to recipients in multiple languages. In that case, defaults can also depend on locale:

| Locale | Suggested Default Name |
| --- | --- |
| **vi-VN** | bạn |
| **en-US** | there |
| **fr-FR** | bonjour |

This is only a phrasing example; real content should be authored appropriately for language and culture. Do not hardcode a fixed Vietnamese string in Java and send the same template for every locale.

Thymeleaf Context can accept a locale:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Context context = new Context(locale);
context.setVariable("recipientName", displayName);
~~~

The template engine can use this locale for built-in message resolution and formatter mechanisms. For multi-language emails, manage the **template**, **message bundle**, **date/currency formats**, and **default text** under the same locale.

### Using Message Bundles for Default Phrases

Instead of hardcoding fallback phrasing in the template:

~~~html
<span th:text="${recipientName != null ? recipientName : 'there'}">
  there
</span>
~~~

you can put fallback labels in a locale-specific message bundle. Example Vietnamese bundle:

~~~properties
mail.greeting.defaultName=bạn
mail.support.label=Bộ phận hỗ trợ
~~~

And the English bundle:

~~~properties
mail.greeting.defaultName=there
mail.support.label=Support team
~~~

The template can use Thymeleaf's message expression to fetch labels:

~~~html
<span th:text="${recipientName != null
                  ? recipientName
                  : #messages.msg('mail.greeting.defaultName')}">
  there
</span>
~~~

The exact organization depends on the application's **MessageSource** and template resolver configuration. The goal is to place **language-dependent wording** in translation sources rather than scattering strings across Java services.

### Default Locale Must Be Chosen Deliberately

If the recipient has no locale, the application needs a defined policy:

- Use the locale selected by the user in their profile.
- Use the locale associated with the transaction or product.
- Use the system's published default locale.

Do not guess the locale solely from the email address or server timezone. If choosing **vi-VN** as the default, pass that locale into Context and use the same locale when formatting dates/currency, avoiding emails with a Vietnamese greeting and dates formatted in a different locale.

## 11. HTML Escaping: Dynamic Variables Must Not Become Markup

When inserting variables into an HTML email, distinguish **text content** from **HTML structure**.

Suppose a user has the name:

~~~text
Lan <Manager> & Co
~~~

If this string is inserted directly into HTML as markup, characters **<**, **>**, and **&** can be interpreted as syntax. The template may render incorrectly or produce unintended content.

In Thymeleaf, **th:text** is the appropriate way to display a value as text and perform HTML escaping:

~~~html
<p>Hello <span th:text="${recipientName}">there</span>.</p>
~~~

If the value is **Lan <Manager> & Co**, the escaped HTML output is equivalent to:

~~~html
<p>Hello <span>Lan &lt;Manager&gt; &amp; Co</span>.</p>
~~~

Browsers/email clients display the characters back as text content rather than treating them as HTML tags.

### Avoid Using th:utext with Untrusted Data

**th:utext** renders HTML content without escaping the way th:text does. If data comes from users, a database that may hold user-entered data, or an external system, passing it directly into **th:utext** can create unwanted markup and risk malicious HTML content.

Only use unescaped HTML when the value was generated by a trusted template source or has passed through a sanitization process appropriate for the purpose. For user names, addresses, notes, and free-form input, prefer **th:text**.

### Defaults Must Also Be Escaped According to Context

A default value like **there** is a safe literal in the example. But if the default is fetched from configuration or a database, it still needs to be handled according to the target context. Not every string escaped for HTML text is safe when placed into:

- HTML attributes such as **href** or **title**.
- URL.
- JavaScript or CSS.
- Unescaped HTML content.

**HTML text escaping does not replace URL validation**. For links in emails, restrict schemes (usually HTTPS), control domains per business rules, and encode attribute values properly. Do not put an arbitrary user-provided URL into href just because the template used th:text at the display site.

## 12. URL Variables and Safe Default Values

A confirmation email usually has an **activationUrl** variable. This is a **required** variable because without it, the recipient cannot perform the action.

~~~java
if (activationUrl == null || activationUrl.isBlank()) {
    throw new IllegalArgumentException(
            "Cannot render email because activationUrl is missing"
    );
}
~~~

Do not use a default:

~~~text
activationUrl = https://example.test/
~~~

if it is not a real confirmation URL. The recipient might click an unrelated page and think they completed the action.

In the template:

~~~html
<a th:href="${activationUrl}" th:text="#{mail.activate.button}">
  Activate account
</a>
~~~

Here **activationUrl** is placed into the href attribute, while the button label comes from the message bundle. The application must generate the URL from a trusted source, ensure the right scheme and host, keep the token time-limited, and avoid logging it. The template only presents the prepared URL.

### URL Values Should Not "Fall Back" to an Empty String

If you use:

~~~html
<a th:href="${activationUrl ?: '#'}">Activate</a>
~~~

then the email still has a button, but the button performs no valid action. This is an **error-hiding** fallback. For required variables, it is better to stop rendering, log a template data error, and avoid sending an unusable email.

## 13. Using the Same Model for HTML and Plain Text

An email may need two content versions: **text/plain** and **text/html**. Do not create two independent sets of variables, because default values between the two versions can drift apart.

Recommended flow:

~~~text
Business data
    |
    v
Validate required fields
    |
    v
Normalize optional fields and defaults
    |
    v
One mail model
    |
    +--> Render HTML template
    |
    '--> Render plain text template
              |
              v
       MimeMessageHelper.setText(plain, html)
              |
              v
       JavaMailSender.send(...)
~~~

Example:

~~~java
Context htmlContext = new Context(locale);
htmlContext.setVariable("order", orderMailModel);

Context textContext = new Context(locale);
textContext.setVariable("order", orderMailModel);

String html = htmlTemplateEngine.process(
        "mail/order-confirmation",
        htmlContext
);
String plain = textTemplateEngine.process(
        "mail/order-confirmation",
        textContext
);
~~~

The two templates can use the same variable names and the same model. The **template mode** configuration differs: the HTML resolver produces HTML, while the text resolver produces plain text. Within an application, you can use two resolvers/engines or configure the template engine in a way suitable for your template structure.

After rendering:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.test");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plain, html);

mailSender.send(message);
~~~

**setText(plain, html)** creates alternative content parts in a MIME message. Both versions must use the same values for **recipientName**, **orderNumber**, **totalAmount**, **activationUrl**, and related data. If the plain version says "expires in 15 minutes" while HTML says "30 minutes", that is a model/template creation bug rather than an SMTP error.

### Display Fallbacks Must Be Consistent

If **recipientName** is missing, normalize to **there** in the model before creating the two Contexts. Do not let HTML use the fallback **there** while plain text renders **null**. Likewise, if there is no promotion code, both versions must either hide the promotion section or display the corresponding business message consistently.
