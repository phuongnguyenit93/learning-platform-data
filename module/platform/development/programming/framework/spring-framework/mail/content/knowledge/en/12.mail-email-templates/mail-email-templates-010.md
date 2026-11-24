# Template Not Found and Rendering Errors in Spring Framework Mail

When a Spring application sends emails using templates, errors can appear before SMTP is even called. A template may not be found, a resource may be unreadable, template syntax may be invalid, or passed data may be insufficient to render content. These errors are commonly grouped together as **template errors**, yet they have different causes and handling strategies.

In Spring Framework Mail, a template-based email flow typically includes:

1. Selecting the template by notification type and language.
2. The template resolver locating the resource on the classpath or filesystem.
3. The template engine reading and parsing the template syntax.
4. The engine evaluating expressions and substituting data into the corresponding positions.
5. The application receiving the rendered HTML/text string.
6. The application building a MIME message and sending via JavaMailSender.

If step 2, 3, or 4 fails, the application does not yet have valid email content to send. **Do not treat every template error as an SMTP error**, nor send the raw unrendered template file just to avoid an error. Identify which step failed, store enough information for diagnosis, and apply an appropriate fallback or retry policy.

## 1. Distinguishing Error Categories

A "failed to send email" message can hide many distinct errors:

| Error Category | Example | When It Occurs | Main Handling Approach |
| --- | --- | --- | --- |
| **Template not found** | Missing order-ready.html on classpath | When the resolver looks up the template | Check name, prefix/suffix, resource packaging, and artifact |
| **Resource read failure** | External file does not exist or lacks read permission | When opening the resource | Check source, filesystem permissions, volume, and I/O |
| **Template parse failure** | HTML template has invalid Thymeleaf syntax | When the engine parses the template | Fix the template, syntax, or fragment |
| **Expression/render failure** | Expression references a property absent from context | When the engine evaluates expressions | Check view model and variable names |
| **Template logic failure** | Conditional or loop uses wrong data type | During rendering | Check data types and template logic |
| **Encoding failure** | Garbled Vietnamese text or resource cannot be decoded | When reading or rendering | Standardize charset, prefer UTF-8 |
| **MIME construction failure** | Content/attachment cannot be packaged | After rendering, before SMTP | Check MimeMessage and attached resources |
| **SMTP submission failure** | Server rejects AUTH, MAIL FROM, or DATA | When sending | Check SMTP transport and server response |

This distinction prevents wrong fixes. For instance, increasing SMTP timeout will not fix a missing template; retrying repeatedly will not fix a permanent syntax error; changing a template will not fix rejected SMTP credentials.

### Processing Flow and Failure Points

~~~mermaid
flowchart TD
    A["Business event"] --> B["Select template key and locale"]
    B --> C["Template resolver"]
    C --> D{"Resource found?"}
    D -- "No" --> E["Template not found"]
    D -- "Yes" --> F["Read and parse template"]
    F --> G{"Valid syntax?"}
    G -- "No" --> H["Parse error"]
    G -- "Yes" --> I["Render with context"]
    I --> J{"Render succeeded?"}
    J -- "No" --> K["Expression / data error"]
    J -- "Yes" --> L["Build MimeMessage"]
    L --> M["JavaMailSender"]
    M --> N{"SMTP accepted?"}
    N -- "No" --> O["Mail transport error"]
    N -- "Yes" --> P["Submitted"]
~~~

Each branch requires its own log type, job status, and retry decision. In particular, **template rendering should finish before calling JavaMailSender**, so template errors are not mixed into transport errors.

## 2. How Does the Template Resolver Locate Files?

A template engine does not guess file locations. It receives a **template name**, and one or more resolvers identify the corresponding resource.

Example resource structure:

~~~text
src/main/resources/
└── templates/
    └── mail/
        ├── order-ready.html
        ├── order-ready.txt
        ├── payment-received.html
        └── password-reset.html
~~~

If the resolver is configured with prefix **templates/mail/** and suffix **.html**, the template name **order-ready** is mapped to:

~~~text
templates/mail/order-ready.html
~~~

Therefore, when encountering a template-not-found error, check the entire mapping:

| Component | Example Value | Question to Check |
| --- | --- | --- |
| Template name | order-ready | Is code passing the right key? |
| Prefix | templates/mail/ | Is it the right folder on the classpath? |
| Suffix | .html | Does the actual file have that exact extension? |
| Resource location | templates/mail/order-ready.html | Was the file packaged? |
| Classloader | Application classloader | Is the resource on the runtime classpath? |
| Locale | vi or en | Was the wrong locale folder selected? |

### Configuring the Thymeleaf Resolver for Email

With Spring 6 and Thymeleaf Spring 6, you can use a classloader-based resolver:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

@Configuration
public class MailTemplateConfiguration {

    @Bean("mailHtmlTemplateEngine")
    public SpringTemplateEngine mailHtmlTemplateEngine() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/mail/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCheckExistence(true);
        resolver.setCacheable(true);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        return engine;
    }
}
~~~

This resolver searches for templates on the classpath. Significant settings:

- **prefix** is the root directory of templates.
- **suffix** is appended to the template name when the resolver searches for files.
- **TemplateMode.HTML** instructs the engine to parse HTML/Thymeleaf syntax.
- **characterEncoding** specifies the charset used when reading resources.
- **checkExistence** lets the resolver check whether a resource exists during resolution, useful when multiple resolvers are chained in order.
- **cacheable** enables caching parsed templates, appropriate for stable packaged templates in production.

The example above creates only an HTML engine. If there is a separate text version, configure a text resolver and engine with suffix **.txt** and TemplateMode.TEXT. Do not use a single HTML resolver and expect the engine to locate all formats automatically.

### Template Names Usually Exclude the Suffix

With the prefix/suffix above, calling:

~~~java
String html = mailHtmlTemplateEngine.process(
        "order-ready", context);
~~~

looks for order-ready.html. If code passes **order-ready.html** while the resolver also appends the suffix, the path can become order-ready.html.html. Standardize on one convention: the template name is a key without extension, while the resolver manages prefix/suffix.

## 3. Template Not Found: Causes and Diagnosis

A template-not-found error usually comes from one of the following causes.

### 3.1. Wrong Name or Case Mismatch

For example, the actual file is:

~~~text
templates/mail/order-ready.html
~~~

but code calls:

~~~java
mailHtmlTemplateEngine.process("Order-Ready", context);
~~~

On some Windows filesystems, case differences may not surface when running locally. When deploying on Linux or in case-sensitive environments, mismatched casing can prevent the resolver from finding the file.

Keep template names consistent, use stable keys, and inspect files inside the artifact. Do not rely on "it works in my local dev environment."

### 3.2. Wrong Prefix or Suffix

Suppose the resource is in **templates/mail/** while the resolver configures prefix **mail/templates/**. The resolver searches the wrong location even though the file is already inside the JAR.

Verify all three values:

~~~text
Template name: order-ready
Prefix:        templates/mail/
Suffix:        .html
Resolved path: templates/mail/order-ready.html
~~~

Log the template key and resolver configuration at a safe diagnostic level. Do not log full template content or rendered personal data.

### 3.3. Resource Not Packaged in the JAR

A file can exist in the repository yet be missing from the artifact due to:

- Being placed under a directory not treated as a resource by the build tool.
- Gradle/Maven configuration excluding the file from resource processing.
- Wrong name or path in the source tree.
- Resource residing in another module that is absent from the runtime classpath.
- Deployed artifact is not the newly built version.

Source path:

~~~text
src/main/resources/templates/mail/order-ready.html
~~~

Runtime path:

~~~text
templates/mail/order-ready.html
~~~

When running from an executable JAR, resources typically sit in the JAR's classpath area. Never use source tree paths such as **src/main/resources/...** to load files at runtime.

### 3.4. Using Filesystem Paths Instead of Classpath Paths

The following code depends on the process working directory:

~~~java
new File("src/main/resources/templates/mail/order-ready.html");
~~~

This path usually does not exist when the application is deployed. For resources packaged with the application, use ClassPathResource, ResourceLoader, or a classpath-capable template resolver.

### 3.5. Using getFile() with a Resource Inside a JAR

A classpath resource inside an executable JAR may not be a standalone file on the filesystem. Therefore, **Resource.getFile()** can fail even when the resource actually exists.

Read via stream:

~~~java
Resource resource = new ClassPathResource(
        "templates/mail/order-ready.html");

try (InputStream input = resource.getInputStream()) {
    String source = StreamUtils.copyToString(
            input, StandardCharsets.UTF_8);
}
~~~

When using a template engine, you usually do not need to read files manually; just configure the resolver properly and call process by template name.

### 3.6. Locale Selects a Nonexistent Directory

Suppose the application selects:

~~~text
templates/mail/fr/order-ready.html
~~~

but only **vi/** and **en/** folders exist. A default template may exist yet the code has no locale fallback.

Define explicit rules:

1. Look up the template pair by exact locale.
2. If absent, try the reduced locale per application rules (e.g., vi-VN to vi).
3. If still absent, use the approved default locale.
4. If a required template still does not exist, mark a configuration error and do not send wrong content.

Do not concatenate user-sent locales directly into filesystem paths. Use a locale and template-key allowlist.

## 4. Loading Resources Directly to Pinpoint Where the Failure Lies

If you suspect a resource is missing, you can verify with the Spring Resource API before rendering:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource template = new ClassPathResource(
        "templates/mail/order-ready.html");

if (!template.exists() || !template.isReadable()) {
    throw new IllegalStateException(
            "Required mail template is missing or unreadable");
}
~~~

This check distinguishes **missing/unreadable resources** from syntax or expression errors inside the template. However, if the template engine uses its own resolver, the resource check must use the matching location and source for that resolver.

For templates on the filesystem:

~~~java
Resource template = resourceLoader.getResource(
        "file:/etc/myapp/mail/order-ready.html");
~~~

Check process read permissions, volume mounts, paths, and filesystem availability. If files are modified while the application is running, also account for template engine caching.

**Do not take arbitrary resource locations from requests.** Select templates via an allowlisted key and map to a fixed location to avoid path traversal or unintended file/URL access.

## 5. Parse Error: File Found, Syntax Invalid

A template can exist and be readable yet fail to parse. With Thymeleaf, common errors include:

- Unclosed/mismatched HTML tags or fragments violating structure required by the engine.
- Invalid Thymeleaf expression syntax.
- Misspelled or misplaced attribute processor.
- Referenced fragment does not exist.
- Text template using HTML-mode syntax or vice versa.
- Template containing unusual characters/encoding preventing the parser from reading it.

Example:

~~~html
<p th:text="${customerName">Customer name</p>
~~~

The expression is missing a closing brace. When the engine parses or processes the attribute, it can throw an exception instead of producing the expected content.

Correct example:

~~~html
<p th:text="${customerName}">Customer name</p>
~~~

### Valid HTML Does Not Mean a Valid Template

A file may open in a browser yet fail to render through Thymeleaf if template expressions are wrong. Conversely, a template that renders does not guarantee every email client displays CSS/HTML identically. These are two separate concerns:

| Check | What It Confirms |
| --- | --- |
| HTML parser/browser | HTML structure can be parsed by a browser |
| Template engine | Template syntax and expressions can be rendered |
| Email client | How content appears in the mail reading environment |
| Accessibility review | Whether recipients can read and act on the content |

When encountering a parse error, inspect the template name, line/column position if the exception provides it, related fragments, and the running template version. Do not look only at local files if production is running an older artifact.

## 6. Render Error: Template Exists, Data Does Not Match

After parsing, the engine evaluates expressions and reads data from the context. Template example:

~~~html
<p>Hello <span th:text="${customer.name}">Name</span></p>
<p>Order code: <span th:text="${order.id}">ORD-000</span></p>
~~~

The context needs the corresponding variables:

~~~java
Context context = new Context(locale);
context.setVariable("customer", customerView);
context.setVariable("order", orderView);
~~~

If code only passes **customerName** and **orderId**, the template cannot access **customer.name** or **order.id** under that structure. The engine may render an empty value, skip the element, or throw an error depending on the expression, configuration, and access mode.

### Common Causes

| Cause | Example | How to Fix |
| --- | --- | --- |
| Missing variable | Template uses customerName but context lacks it | Synchronize variable names between renderer and template |
| Wrong object structure | Template uses customer.name but String was passed | Pass the properly typed view model or update the expression |
| Null value | order.customer is null | Validate/fallback before rendering or handle conditionally |
| Wrong data type | Loop expects List but received String | Normalize data types in the view model |
| Fragment missing parameter | Fragment requires order but caller did not pass it | Check fragment signature and call site |
| Invalid method call in expression | Calling a nonexistent or restricted getter/method | Use properties explicitly exposed on the view model |
| Optional data skipped | Template assumes address is always present | Define required/optional fields |

### Passing an Explicit View Model

Instead of passing the entire JPA entity, create a dedicated model for email:

~~~java
public record OrderReadyMailModel(
        String customerName,
        String orderId,
        String pickupLocation,
        String pickupDeadline,
        String orderUrl
) {
}
~~~

Then place stably named variables into the context:

~~~java
Context context = new Context(locale);
context.setVariable("customerName", model.customerName());
context.setVariable("orderId", model.orderId());
context.setVariable("pickupLocation", model.pickupLocation());
context.setVariable("pickupDeadline", model.pickupDeadline());
context.setVariable("orderUrl", model.orderUrl());
~~~

Template:

~~~html
<h1>Order Is Ready</h1>
<p>Hello <span th:text="${customerName}">Customer</span></p>
<p>Order code: <span th:text="${orderId}">ORD-000</span></p>
<p>Location: <span th:text="${pickupLocation}">Location</span></p>
<p>Pickup deadline: <span th:text="${pickupDeadline}">Time</span></p>
<a th:href="${orderUrl}">View order</a>
~~~

A view model clarifies the contract between Java and the template. When the database structure changes, the template does not have to depend on entities or lazy-loading relationships. When adding a required field, model, renderer, and tests can be updated together.

### Validating Required Fields Before Rendering

Do not wait for the template engine to catch every data error. Validate upfront:

~~~java
private static void validate(OrderReadyMailModel model) {
    Objects.requireNonNull(model, "model");
    requireText(model.customerName(), "customerName");
    requireText(model.orderId(), "orderId");
    requireText(model.pickupLocation(), "pickupLocation");
    requireText(model.pickupDeadline(), "pickupDeadline");
    requireText(model.orderUrl(), "orderUrl");
}

private static void requireText(String value, String field) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                "Required mail field is missing: " + field);
    }
}
~~~

This is a basic validation example. In a real application, checks must also enforce schema, length, data access permissions, allowed URLs/hosts, locale, and business rules.

## 7. Example Thymeleaf Renderer and Error Classification

A renderer can centralize template selection, context preparation, and engine invocation:

~~~java
package com.example.mail;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.exceptions.TemplateEngineException;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class MailTemplateRenderer {

    private final SpringTemplateEngine htmlEngine;

    public MailTemplateRenderer(
            @Qualifier("mailHtmlTemplateEngine")
            SpringTemplateEngine htmlEngine) {
        this.htmlEngine = htmlEngine;
    }

    public String renderOrderReady(
            OrderReadyMailModel model,
            Locale locale) {
        validate(model);

        Context context = new Context(locale);
        context.setVariable("customerName", model.customerName());
        context.setVariable("orderId", model.orderId());
        context.setVariable("pickupLocation", model.pickupLocation());
        context.setVariable("pickupDeadline", model.pickupDeadline());
        context.setVariable("orderUrl", model.orderUrl());

        try {
            return htmlEngine.process("order-ready", context);
        } catch (TemplateEngineException exception) {
            throw new MailTemplateRenderException(
                    "Cannot render mail template: order-ready",
                    exception);
        }
    }

    private static void validate(OrderReadyMailModel model) {
        if (model == null
                || model.customerName() == null
                || model.orderId() == null
                || model.pickupLocation() == null
                || model.pickupDeadline() == null
                || model.orderUrl() == null) {
            throw new IllegalArgumentException(
                    "Order-ready mail data is incomplete");
        }
    }
}
~~~

Application-specific exception:

~~~java
public class MailTemplateRenderException extends RuntimeException {

    public MailTemplateRenderException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The example illustrates catching Thymeleaf `TemplateEngineException` errors. In real code, the specific exception may be a subclass such as `TemplateInputException` or `TemplateProcessingException`; keep the cause for investigation. Data validation errors are thrown before the render block and must not be misclassified as template syntax errors.

Do not catch every `RuntimeException` and return an empty string. Doing so lets emails still be created with missing content, hides the root cause, and can cause business consequences.

## 8. Separating Rendering Errors from SMTP Sending Errors

The renderer should finish before the service calls `JavaMailSender`:

~~~java
public void sendOrderReady(
        OrderReadyMailModel model,
        Locale locale) throws MessagingException {

    String html = renderer.renderOrderReady(model, locale);
    String plain = plainTextRenderer.renderOrderReady(model, locale);

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8");

    helper.setFrom(fromAddress);
    helper.setTo(recipientAddress);
    helper.setSubject("Order " + model.orderId() + " is ready");
    helper.setText(plain, html);

    mailSender.send(message);
}
~~~

This example assumes sender, renderer, and addresses are injected; the text version is rendered by a corresponding renderer. Separating steps helps distinguish:

- **Pre-send errors:** data, template name, resource, parse, or render.
- **Send-time errors:** MIME construction, connection, TLS, SMTP AUTH, MAIL FROM, RCPT TO, or DATA.
- **Post-send errors:** relay accepted, yet delivery to destination mailbox was delayed or bounced.

If exceptions are caught in the same layer, still classify by stage and preserve the root cause. Do not turn every error into an "SMTP server unavailable" message.

## 9. Multiple Template Resolvers and Lookup Order

An application may use multiple resolvers—for example, default templates on the classpath, tenant-specific templates on the filesystem, HTML and text using different suffixes, or locale-based templates in separate folders.

When multiple resolvers participate, **order and existence checking** affect the outcome. A first resolver might claim a template name even when the resource does not match, or a resolver might report not found and give the next resolver a chance, depending on configuration.

With Thymeleaf, you can configure resolvers in order and use checkExistence to assist selection:

~~~java
ClassLoaderTemplateResolver classpathResolver =
        new ClassLoaderTemplateResolver();
classpathResolver.setPrefix("templates/mail/");
classpathResolver.setSuffix(".html");
classpathResolver.setTemplateMode(TemplateMode.HTML);
classpathResolver.setOrder(2);
classpathResolver.setCheckExistence(true);

// Another resolver can be added before/after per design.
~~~

This snippet configures one resolver, not a complete multi-source setup. When multiple resolvers exist, set order, prefix/suffix, pattern, cache, and fallback behavior for each resolver, then test cases where a template exists in multiple locations.

### Avoid Implicitly Falling Back to the Wrong Template Type

Suppose the template for a payment confirmation email is missing. If the resolver falls back to a generic template saying only "Hello", the application may send an email missing critical information yet treat it as a success.

Fallback must be **an intentional business decision**, not an accidental result returned by a second resolver. A default template should only be used when it truly fits the notification type and contains all required information.

## 10. Fallback Policy When a Template Is Missing

Not every template has the same criticality. You can categorize:

| Content Type | Example | Appropriate Behavior |
| --- | --- | --- |
| Required template | OTP, transaction confirmation, legal notice | Do not send wrong content; report config error and handle safely |
| Template with approved fallback | Simple notification with standard text version | Can use controlled fallback if all required info remains present |
| Optional decorative element | Logo or banner | Can omit decorative element if main content remains complete |
| Optional marketing block | Product recommendations | Can omit block if transactional info is unaffected |

### Do Not Use Raw Template Source as a Fallback

Suppose a file has:

~~~text
Hello {{customerName}},
Order {{orderId}} is ready.
~~~

If rendering fails, never send this raw string to the customer. Recipients will see unreplaced placeholders, and the message is no longer a complete email.

A fallback must be another controlled template that renders successfully, minimal plain-text content built explicitly from validated data, or not sending and marking an error for operational handling.

### Fallback from HTML to Plain Text

If the HTML template fails yet the plain-text template still renders, the system can send text-only **when business rules permit**. For example, a simple order-status email might have an approved text template.

Do not apply automatically to emails where HTML carries required information absent from text, or where HTML and text templates are not versioned together. If the render error stems from missing data, the text version may also be wrong.

A safe policy:

1. Render text and HTML from the same view model.
2. If HTML rendering fails, log the error with template key/version.
3. Use text-only only when the text template rendered cleanly and is marked as a valid fallback for that notification type.
4. If text also fails or data is invalid, do not submit the email.

## 11. Retry or Do Not Retry?

Retries are only useful when the cause can resolve on its own. Many template errors are permanent until the file or data is fixed.

| Error | Immediate Auto-Retry? | Reason |
| --- | --- | --- |
| Wrong template name | No | Configuration name will not fix itself after a few seconds |
| Missing file in artifact | No | Must build/deploy the right artifact |
| Invalid template syntax | No | Must fix content and re-release |
| Missing required variable in context | Not via blind retry | Must fix mapping or business data |
| External file temporarily unmounted | Limited retry possible | Only when confirmed to be a transient infrastructure issue |
| Template storage temporarily unreachable | Retry with backoff possible | Depends on source and recoverability |
| SMTP server temporary rejection | Retry per error code | This is a transport error, separate from rendering |
| Wrong SMTP AUTH credentials | Do not retry continuously | Must fix secrets/login permissions |

### Job Classification

~~~text
PENDING
  |
  +-- Template missing / parse error --> TEMPLATE_CONFIG_ERROR
  |
  +-- Required data invalid ----------> INVALID_NOTIFICATION_DATA
  |
  +-- Render successful --------------> READY_TO_SEND
                                           |
                                           +--> SMTP accepted --> SUBMITTED
                                           |
                                           +--> Temporary error --> RETRY_SCHEDULED
                                           |
                                           +--> Permanent error --> SEND_FAILED
~~~

This is an illustrative state model. Configuration template errors should usually go to an error-handling queue/dead-letter or an intervention state rather than repeatedly attempting to render the same broken template.

If external template files can be fixed without deploying, a job can retry after the template version changes. However, clearly decide whether the job uses **the template version at event creation time** or **the latest version at retry time**. The two options can produce different content for the same notification.

## 12. Logging and Observing Template Errors

Good logs pinpoint whether an error occurred in the resolver, parser, expression, or SMTP without exposing recipient data.

An event log might store:

~~~json
{
  "event": "mail_template_render_failed",
  "notificationId": "order-ready-ORD-184-v1",
  "templateKey": "order-ready",
  "locale": "vi-VN",
  "templateVersion": "2026.11.12-2",
  "stage": "RENDER",
  "exceptionType": "TemplateProcessingException",
  "retryable": false
}
~~~

This is illustrative JSON for internal logs, not default Thymeleaf output. Never put email bodies, SMTP passwords, access tokens, or full personal data into logs. When recipient correlation is needed, use a notification ID or a controlled identifier.

### Useful Metrics

| Metric | What It Indicates |
| --- | --- |
| Template-not-found count by template key | Which template is missing or misconfigured |
| Parse/render error count by version | Which template release caused an incident |
| Render success rate by locale | Which locale is missing a template pair or data |
| Render duration | Overly complex template or slow resource source |
| Fallback rate | Quality and stability of primary templates |
| Post-render SMTP error rate | Separates template quality from transport |

You can alert on the first error of a required template or when error rates exceed a threshold. For critical transactional templates, **a missing-template error after deploy** can signal an artifact missing resources and should be caught early.

### Do Not Log Full Exceptions in Ways That Expose Data

Stack traces are useful for developers, yet exception messages sometimes contain expressions, paths, variable names, or data from context. Logs must follow the system's data policy. You can keep exception causes in controlled logs and emit short operational messages with a correlation ID.

## 13. Testing Templates Before Release

Templates are part of the email-sending product. Test them before deploying, rather than waiting until customers receive broken messages.

Test layers can include:

1. **Resource presence:** is the file on the classpath or configured source?
2. **Parse:** does the template engine parse syntax successfully?
3. **Render:** with complete sample data, does the engine produce output?
4. **Required content:** does output contain order number, deadline, URL, and required info?
5. **Escaping:** can data with special characters create unintended markup?
6. **Locale coverage:** does each supported locale have both HTML and text templates?
7. **MIME composition:** are HTML and text placed into the right parts?
8. **Artifact packaging:** are resources still readable when running from a JAR?

### Unit Testing Template Rendering

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.thymeleaf.context.Context;

class MailTemplateRenderTest {

    @Test
    void rendersOrderReadyTemplate() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", "An");
        context.setVariable("orderId", "ORD-184");
        context.setVariable("pickupLocation", "District 1 Pickup Counter");
        context.setVariable("pickupDeadline", "17:00 on 15/11/2026");
        context.setVariable(
                "orderUrl",
                "https://shop.example/orders/ORD-184");

        String html = mailHtmlTemplateEngine.process(
                "order-ready", context);

        assertTrue(html.contains("ORD-184"));
        assertTrue(html.contains("District 1 Pickup Counter"));
        assertTrue(html.contains("17:00 on 15/11/2026"));
    }
}
~~~

The example assumes the test can access the **mailHtmlTemplateEngine** bean. It checks key business fields in the output, not merely that the method did not throw an exception.

### Testing Nonexistent Templates

You can verify the engine throws an error when calling a key absent from the classpath:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.thymeleaf.exceptions.TemplateEngineException;

class MissingMailTemplateTest {

    @Test
    void missingTemplateIsReported() {
        Context context = new Context();

        assertThrows(
                TemplateEngineException.class,
                () -> mailHtmlTemplateEngine.process(
                        "template-does-not-exist", context));
    }
}
~~~

The exact exception type depends on the resolver and Thymeleaf version; in project tests, assert the actual subclass if stricter checking is desired. The goal is ensuring errors are not swallowed and an empty email is not returned as if rendering succeeded.

### Checking All Templates in a Catalog

If there are many templates, you can maintain a list of supported keys:

~~~java
List<String> requiredTemplates = List.of(
        "order-ready",
        "order-cancelled",
        "payment-received",
        "password-reset");

for (String templateName : requiredTemplates) {
    mailHtmlTemplateEngine.process(templateName, sampleContext);
}
~~~

The snippet illustrates rendering templates with a sample context. Each template may require different variables, so the test suite should define **a dedicated context per template** rather than using one shared incomplete context and concluding the whole catalog is valid.

### Checking the Artifact After Building

A test running in an IDE may find resources from the classes directory, while the deployed executable JAR is missing resources. Verify that templates are packaged inside the artifact, prefixes/suffixes match runtime paths, filenames match casing exactly, resources read via classpath stream, and the engine can render when running in the actual deployment mode.

Do not depend on the source directory at runtime. If templates live on the filesystem outside the JAR, verify volumes, read permissions, and versions mounted in the corresponding environment.

## 14. Caching and Errors After Updating Templates

Template engines often cache parsed template content or structures. This reduces I/O and parsing overhead when sending many emails, but can cause symptoms:

- Editing an external filesystem file while emails still use old content.
- One instance uses the new template version while another still uses the old version.
- A broken template gets cached and keeps failing across multiple notifications.
- After deploy, some instances have not restarted or loaded the new version.

For templates packaged in a JAR, deployment usually means building a new artifact and rolling out new instances. For external templates, define cache TTL, invalidation/reload mechanisms, atomic updates, and rollback.

### Attaching Template Version to Notifications

If notifications are stored long-term and retried hours later, decide which version to use:

| Policy | Meaning |
| --- | --- |
| Render with current version | Content may change after the job is created |
| Record version when creating job | Retries use the same version already determined |
| Store snapshot of rendered content | Retries can send identical content, but require data protection and retention management |

For legal or critical transactional notices, versioning may be required to know exactly what content was sent to recipients. For simple notifications, using the current version may suffice. The decision belongs to the system's business and audit policies.

## 15. Security When Handling Template Errors

Templates can read files, evaluate expressions, and insert data into HTML. Therefore, both template sources and context data must be controlled.

### Use Only Trusted Templates

Do not take arbitrary template content from users and feed it directly into a template engine with full expression capabilities. Templates can invoke expressions, access properties, or include fragments depending on the engine/configuration. If a product allows users to customize emails, design a restricted template language or an appropriate allowlist, authorization, and sandbox mechanism.

### Escape HTML Data

In Thymeleaf, use **th:text** for text content:

~~~html
<p th:text="${customerName}">Customer name</p>
~~~

Do not use **th:utext** for untrusted data without a proper HTML sanitization pipeline. For URLs in **th:href**, validate scheme/host and access permissions before rendering; HTML escaping does not replace URL validation.

### Do Not Let Fallbacks Expose Data

If the primary template fails, never send debug output, stack traces, internal variable names, SQL, filesystem paths, or exception messages to the recipient. Fallbacks must be approved content, not exception text.

### Do Not Log Sensitive Data

Logging template key, locale, version, notification ID, and exception type is usually enough to start investigation. Avoid logging full email bodies, tokenized URLs, password-reset codes, or account data.

## 16. Suggested Troubleshooting Workflow

When notified "email template failed," proceed in this order:

1. **Identify the notification ID and template key.** Know which email type is failing.
2. **Identify the stage.** Resolver, resource reading, parsing, rendering, MIME building, or SMTP.
3. **Check template name/prefix/suffix.** Compare against runtime resource paths.
4. **Check the artifact or file source.** Is the resource present and readable by the process?
5. **Check locale and resolver order.** Was the wrong directory or resolver picked?
6. **Inspect the root exception and error location.** Parse error or expression/data error?
7. **Inspect the context.** Do required variables have the right names, types, and values?
8. **Render with sample data in a controlled environment.** Never use real customer data for public debugging.
9. **Decide fallback/retry.** Permanent errors need config/template fixes; transient infra errors may allow bounded retries.
10. **Inspect SMTP separately after rendering succeeds.** Only once the template produces valid content should submission errors be investigated.

### Quick Isolation Table

| Symptom | First Check |
| --- | --- |
| Only one template fails | Template key, file, suffix, and syntax of that template |
| All templates not found | Prefix, classpath, artifact, or resolver bean |
| Only one locale fails | Locale template pair and fallback |
| Works locally, fails in production | JAR contents, casing, volumes, and paths |
| Template parses but fails to render | Context variables, data types, nulls, and expressions |
| Render succeeds but email does not send | MIME construction and SMTP transport |
| Template edited yet old error persists | Cache, unrolled-out instances, or version |
| Some workers fail, others succeed | Artifact/configuration mismatch across instances |

## 17. Self-Check Questions

**1. Is template not found an SMTP error?**

No. It is an error at the resolver step looking up the resource, occurring before the application submits the email.

**2. A file is in the repository yet missing in production; what could cause this?**

The resource may not have been packaged, wrong prefix/suffix, case mismatch, missing module on runtime classpath, or the deployed artifact is the wrong version.

**3. Why not use getFile() for every ClassPathResource?**

Because resources inside an executable JAR may not exist as standalone files. Read with getInputStream() or let the template resolver handle the resource.

**4. How does a template parse error differ from a render error?**

A parse error relates to template syntax or structure; a render error usually relates to expressions, variables, data types, or operations during evaluation.

**5. Does a missing variable in context always throw an exception?**

Not necessarily. Behavior depends on the expression, engine, and configuration; some cases render empty or skip the element. Therefore, validate required data before rendering and test output.

**6. Should raw template source be sent if rendering fails?**

No. Recipients may see unreplaced placeholders or technical content. Use an approved fallback or do not send.

**7. Should template parse errors be retried continuously?**

No. Syntax errors are permanent until the template is fixed; blind retries only add load and repeat the failure.

**8. Can you fall back from HTML to plain text?**

Yes, when the text version is a valid fallback, rendered cleanly, and contains all essential information for that email type. Do not do this automatically when data or the text template also failed.

**9. Why must templates be tested in an executable JAR?**

Because resources may work in an IDE yet be missing or unreadable in the deployed artifact. Testing in the production execution mode catches packaging bugs.

**10. Can template engine caching cause errors after deploy?**

Yes. Instances may hold old templates or have mismatched versions. Manage caching, rollouts, and template versions.

**11. How do you avoid confusing rendering errors with sending errors?**

Render HTML/text before calling JavaMailSender, record distinct stages, and investigate SMTP only after valid content has been generated.

**12. Which log fields are useful without logging the email body?**

Notification ID, template key, locale, template version, stage, exception type, and retryability are usually enough to begin isolation.

## Conclusion

**Template not found and rendering errors occur during email content generation**, before Spring Mail hands the message to SMTP. Template not found typically relates to template name, resolver prefix/suffix, classpath, or unpackaged resources; parse errors relate to template syntax; render errors typically relate to context, variables, data types, or expressions. Separate rendering from sending, use a view model with a clear contract, verify resources and templates inside the real artifact, preserve original exceptions, and log by template key/version. Use only approved fallbacks, never send unrendered template source, and retry only when the cause is recoverable. **Classifying the exact stage speeds up fixes and prevents sending incomplete or wrong emails to recipients.**
