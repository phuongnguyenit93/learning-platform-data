# Reducing Unnecessary Template Renders

In Spring Framework Mail, an email is typically assembled from business data, HTML/plain-text templates, and recipient details. If an application renders the exact same content multiple times before calling **JavaMailSender.send(...)**, CPU, memory, database queries, and processing time increase without adding value for the recipient.

For example, a system renders an order-confirmation email once to inspect the content, once to build a `MimeMessage`, and again when a worker retries after a temporary SMTP server error. When the same template, data, and content version are used, multiple render passes can be redundant work. However, **you must never render personalized content once and share it across different recipients** just to save resources.

This lesson focuses on **safely reducing unnecessary template renders** within the **Performance and Limits** chapter of Spring Framework Mail. Key questions:

- What counts as an actual render?
- When does caching parsed templates help, and when is it not enough?
- How do you render only once in an email-creation flow?
- When sending to multiple recipients, which parts may be shared?
- With an outbox/retries, should you store render data or rendered HTML?
- How do cache keys, TTLs, template versions, tenants, and locales interact?
- How do you measure render counts and test against duplicate rendering?
- When **must you re-render** to avoid stale content, expired tokens, or data leaks?

The goal is **sending the right content with less redundant work**, without trading off business accuracy or customer data security.

## 1. Where Does Template Rendering Sit in the Send Flow?

A typical HTML email sending flow:

~~~text
Business event / request
           |
           v
Validate recipient and eligibility
           |
           v
Load immutable mail view model
           |
           v
Select template, version and locale
           |
           v
TemplateEngine.process(...)
           |
           v
Rendered HTML / plain-text content
           |
           v
MimeMessageHelper.setText(...)
           |
           v
JavaMailSender.send(...)
           |
           v
SMTP relay
~~~

**Rendering** is the step where the template engine combines data with a template to produce the output string. For instance, Thymeleaf evaluates expressions, conditionals, loops, and fragments and returns HTML.

Example:

~~~java
String html = templateEngine.process(
        "order-confirmation",
        context
);
~~~

This is one render pass. Next:

~~~java
helper.setText(plainText, html);
~~~

places the already-prepared content strings into the MIME message. **There is no need to call the template engine again** when the content has already been prepared properly.

### 1.1. Rendering Is Not SMTP Sending

A successfully rendered template can still fail on send: bad AUTH, TLS errors, rejected recipients, temporary provider overload, oversized attachments, or timeouts after `DATA`. Conversely, reducing renders does not directly fix SMTP connection latency.

### 1.2. Rendering Is Not Template Parsing

Template engines can cache the parsed structure of a template after reading it. Still, each `process` call with a `Context` creates a new output string. Distinguish between these two cache levels.

## 2. Why Does Repeated Rendering Create Overhead?

A single render pass can involve:

- Resolving the template by name.
- Parsing the template if not yet cached.
- Evaluating expressions and conditional logic.
- Processing layouts, fragments, and item lists.
- Formatting dates, times, and currencies.
- Escaping HTML and building the output string.
- Allocating intermediate objects, buffers, and strings.
- Issuing external data lookups if templates are poorly designed.

An HTML template with a table of hundreds of product lines costs much more than a simple paragraph. If rendered three times when only one output is used, the two redundant passes create unnecessary load.

Illustrative scale table:

| Mail Events | HTML Renders/Event | Total Renders |
| ---: | ---: | ---: |
| 10,000 | 3 | 30,000 |
| 10,000 | 2 | 20,000 |
| 10,000 | 1 | 10,000 |

This table **only counts invocations**; it does not claim total latency drops proportionally. When SMTP and queues are the bottleneck, cutting renders may barely change time-to-relay even though CPU improves.

## 3. Three Distinct Forms of Caching

| Cache Type | Data Retained | Benefit | Risk |
| --- | --- | --- | --- |
| **Parsed-template cache** | Parsed template structure | Reduces file reads/parsing | New templates unseen unless invalidated |
| **Rendered-output cache** | HTML/text after variable substitution | Avoids re-rendering identical content | Wrong data, stale content, PII leaks |
| **View-model/data cache** | Data needed for template | Avoids repeated data fetching | Stale business state, wrong scope |
| **Static-fragment cache** | Shared content | Reduces processing of static fragments | Requires accurate version/tenant/locale |

### 3.1. Parsed-Template Cache Does Not Eliminate `process` Calls

~~~java
String htmlA = engine.process(
        "order-confirmation",
        contextA
);

String htmlB = engine.process(
        "order-confirmation",
        contextB
);
~~~

Even when the engine caches parsed templates, this still runs two output renders.

### 3.2. Output Reuse Is What Cuts Render Count

~~~java
RenderedMail content = renderer.render(view);

// Only use content.html() and content.plainText().
// Do not call renderer.render(view) again to fetch each part.
~~~

Reusing one result object within the same unit of work is simple and generally safer than global output caching.

### 3.3. Do Not Cache the Wrong Thing

If the slow part is generating a PDF, caching HTML does not replace document caching. If templates are firing many database queries, extract data into a view model and optimize queries before adding complex HTML caching.

## 4. Principle: One Send Intent, One Content Bundle

A mail event should have clear identification:

~~~text
eventId: ORDER_CONFIRMED:1001:v3
recipientRef: customer-42
templateId: order-confirmation
templateVersion: v4
locale: en-US
~~~

Once this event's content is determined and remains unchanged across processing steps, prepare **RenderedMail** once and pass that object to MIME construction, state persistence, or policy-compliant retries.

~~~text
Mail event
    |
    v
Validated immutable view model
    |
    v
Render once
    |
    +-- Subject
    +-- HTML
    +-- Plain text
    |
    v
Prepared content
    |
    +-- Build MIME
    +-- Persist snapshot if needed
    +-- Submit through SMTP
~~~

**Rendering once** here does not strictly mean a single `templateEngine.process` call: if there are two independent templates for HTML and `text/plain`, two render calls can be completely valid. The point is **not repeating the exact same render pointlessly**.

## 5. Creating a View Model Separate from JPA Entities

Java record example:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Locale;

public record OrderMailView(
        String eventId,
        String recipient,
        String customerName,
        String orderNumber,
        BigDecimal totalAmount,
        Instant confirmedAt,
        Locale locale
) {}
~~~

A view model holding only fields the template actually uses is much easier to snapshot, test, and cache properly than passing entities directly into a template engine.

### 5.1. Prevent Templates from Querying the Database

If template expressions touch lazily loaded entities, every render can:

- Trigger N+1 queries.
- Depend on an open persistence context.
- Read different state across render passes.
- Prolong database transactions.
- Throw lazy initialization exceptions in workers.

Fetch required data in the business layer, map to an immutable DTO, and render **outside long database transactions** when appropriate.

### 5.2. Immutability Must Also Apply to Nested Objects

A `record` does not stop a field from pointing to a mutable `List` or object. For product lists, use immutable snapshots such as `List.copyOf(...)` and never mutate data inside the renderer.

### 5.3. Shared Data vs. Per-Recipient Data

We can classify:

- **Shared:** campaign headlines, public announcements, general support details.
- **Private:** name, email address, order code, amount, tokens, locale, or tenant branding.

This distinction determines which parts may safely be shared across recipients.

## 6. Configuring a Reusable Thymeleaf Engine with Parsed Template Caching

Illustrative Spring Framework configuration with Thymeleaf:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;
import org.thymeleaf.templatemode.TemplateMode;

@Configuration
public class MailTemplateConfiguration {

    @Bean("mailTemplateEngine")
    public SpringTemplateEngine mailTemplateEngine() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();

        resolver.setPrefix("mail-templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(true);

        // Illustrative TTL value, not a mandatory default.
        resolver.setCacheTTLMs(600_000L);

        SpringTemplateEngine engine =
                new SpringTemplateEngine();

        engine.setTemplateResolver(resolver);
        return engine;
    }
}
~~~

Example files:

~~~text
src/main/resources/
└── mail-templates/
    ├── order-confirmation.html
    ├── password-reset.html
    └── fragments/
        └── footer.html
~~~

### 6.1. Do Not Create a New Engine on Every Send

Avoid:

~~~java
for (OrderMailView view : allViews) {
    SpringTemplateEngine engine =
            new SpringTemplateEngine();

    // Configures engine/resolver and then renders every email.
}
~~~

Repeatedly instantiating engines bypasses template caches and adds overhead. Reuse a configured Spring bean engine instead.

### 6.2. Use a Fresh Context for Each Render

A configured engine can be shared across calls. However, **`Context` holding recipient variables is mutable**—never share it as a singleton or mutate it concurrently from multiple threads.

### 6.3. Do Not Confuse Parser Cache with Output Cache

Even with `setCacheable(true)`, every `process` call with different data still renders a new output. If the goal is reducing repeated `process` calls on identical data, change the application's orchestration.

### 6.4. Avoid Conflicts with Web Thymeleaf Configuration

If Spring Boot already auto-configures a Thymeleaf engine for web views, use named/qualified beans to isolate email templates. Do not accidentally alter resolvers shared between web and mail in production.

## 7. Example HTML Template with Dynamic Data

File **mail-templates/order-confirmation.html**:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Order Confirmation</title>
</head>
<body>
    <h1>Order Confirmation</h1>

    <p>
        Hello
        <strong th:text="${customerName}">Customer</strong>,
    </p>

    <p>
        Order
        <strong th:text="${orderNumber}">ORDER-001</strong>
        has been confirmed.
    </p>

    <p>
        Total amount:
        <strong th:text="${formattedTotal}">500000 VND</strong>
    </p>

    <p>Best regards, the Sales Team.</p>
</body>
</html>
~~~

With the resolver from the previous example, call:

~~~java
engine.process("order-confirmation", context);
~~~

to generate the HTML.

### 7.1. th:text Escapes Data

For data supplied by users or external systems, **`th:text`** performs HTML text-context escaping. Avoid **`th:utext`** on untrusted data.

Caching rendered HTML **does not automatically make dangerous data safe**. Escaping and validation rules must still be enforced.

### 7.2. Template Names Are Also Part of the Contract

If a template is renamed or missing from the classpath, rendering fails. That is a message-preparation error, not an SMTP error.

## 8. Designing RenderedMail for Output Reuse

Render output:

~~~java
public record RenderedMail(
        String subject,
        String plainText,
        String html
) {}
~~~

Renderer:

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

public final class OrderMailRenderer {

    private final TemplateEngine templateEngine;

    public OrderMailRenderer(TemplateEngine templateEngine) {
        this.templateEngine =
                Objects.requireNonNull(templateEngine);
    }

    public RenderedMail render(OrderMailView view) {
        Objects.requireNonNull(view, "view");

        String customerName =
                Objects.requireNonNull(view.customerName());
        String orderNumber =
                Objects.requireNonNull(view.orderNumber());
        BigDecimal total =
                Objects.requireNonNull(view.totalAmount());
        Locale locale =
                Objects.requireNonNull(view.locale());

        String formattedTotal =
                total.toPlainString() + " VND";

        String subject =
                "Order confirmation " + orderNumber;

        Context context = new Context(locale);
        context.setVariable("customerName", customerName);
        context.setVariable("orderNumber", orderNumber);
        context.setVariable("formattedTotal", formattedTotal);

        String html = templateEngine.process(
                "order-confirmation",
                context
        );

        String plainText =
                "Hello " + customerName + ",\n\n"
              + "Order " + orderNumber
              + " has been confirmed.\n"
              + "Total amount: " + formattedTotal + ".\n\n"
              + "Best regards, the Sales Team.";

        return new RenderedMail(
                subject,
                plainText,
                html
        );
    }
}
~~~

### 8.1. One Thymeleaf Process per HTML

In the example, the renderer calls `templateEngine.process` only once. Plain text is built from the same DTO using a simple formatter. Subject, HTML, and plain text all reuse the already-prepared `orderNumber` and `formattedTotal`.

### 8.2. When Plain Text Also Needs a Template

You can use a dedicated text template to ensure formatting. Two `process` calls (one HTML, one text) are a legitimate cost in that case. What to avoid is rendering **the exact same HTML version twice** just to retrieve repeated data.

### 8.3. Do Not Rely on Nondeterministic System Locales

`Context` accepts an explicit `Locale`. When complex date/currency formatting is required, format values using an explicit locale so output does not vary with a node's default locale.

### 8.4. This Is a Content Snapshot

`RenderedMail` holds generated strings. If persisted across retries, add rules for template version, TTL, stale content, and data protection.

## 9. Using Rendered Output to Build a MimeMessage

Service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class OrderMailDeliveryService {

    private final OrderMailRenderer renderer;
    private final JavaMailSender sender;

    public OrderMailDeliveryService(
            OrderMailRenderer renderer,
            JavaMailSender sender
    ) {
        this.renderer = renderer;
        this.sender = sender;
    }

    public void send(OrderMailView view) {
        RenderedMail content = renderer.render(view);

        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            false,
                            "UTF-8"
                    );

            helper.setFrom("orders@example.org");
            helper.setTo(view.recipient());
            helper.setSubject(content.subject());

            helper.setText(
                    content.plainText(),
                    content.html()
            );
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare MIME content",
                    ex
            );
        }

        sender.send(message);
    }
}
~~~

**A single `renderer.render(view)` call** supplies the Subject, plain text, and HTML for the message.

### 9.1. Common Anti-Pattern

~~~java
String html = renderer.render(view).html();
String plainText = renderer.render(view).plainText();

helper.setText(plainText, html);
~~~

This renders the same view twice. Beyond redundant CPU, it can produce mismatched outputs if the renderer depends on dynamic data, timestamps, or tokens.

Better:

~~~java
RenderedMail content = renderer.render(view);

helper.setText(
        content.plainText(),
        content.html()
);
~~~

### 9.2. Do Not Broadcast Rendered HTML to Many Recipients Without Privacy Review

Content rendered for one view must not be shared arbitrarily. If the email contains a name, amount, or order code, each recipient/event requires its own content.

## 10. HTML and Plain Text: Reduce Duplication While Preserving Content

A `multipart/alternative` email can carry both `text/plain` and `text/html`. They serve different email clients and accessibility needs.

Three implementation approaches:

| Approach | Cost | Notes |
| --- | --- | --- |
| HTML template + plain-text formatter from view model | 1 HTML render | Ensure both parts convey identical information |
| Two independent HTML and TXT templates | 2 format renders | Requires consistency tests |
| Canonical content model + two renderers | Architecture-dependent | Clear semantics, higher complexity |

### 10.1. Do Not Drop text/plain Just to Save One Render

If business requirements call for a plain-text part, keep it. A CPU optimization should never make emails harder to read or hurt client compatibility.

### 10.2. Do Not Strip HTML with Crude Regexes

Removing tags via regex can break links, tables, lists, or line breaks. If generating plain text from HTML, use a structure-aware converter or a tested text template.

### 10.3. Share the View Model

Even with two templates, pass the exact same prepared data rather than querying and formatting independently in two places. This reduces drift between HTML and plain text.

## 11. Do Not Render Before Determining Whether Sending Is Needed

A simple optimization is to **skip rendering entirely for ineligible mail events**.

Wasteful flow:

~~~text
Load data
    |
    v
Render HTML
    |
    v
Check unsubscribe/suppression
    |
    +-- Recipient not eligible -> discard rendered output
~~~

Better flow:

~~~text
Validate event and recipient
    |
    v
Check eligibility / preferences / suppression
    |
    +-- Not eligible -> stop
    |
    v
Load view model
    |
    v
Render and send
~~~

### 11.1. Checks That Can Run Beforehand

- Duplicate event that was already processed.
- Recipient lacks a valid address.
- User unsubscribed from marketing emails.
- Address is on a suppression list.
- Token or notification deadline has expired.
- Tenant has disabled this notification type.
- Business state no longer requires sending.
- Sender account is paused due to configuration errors.

### 11.2. Checks Requiring Re-Verification Before Send

If an event sits in an outbox for hours, preferences or permissions may change. For emails subject to unsubscribe compliance, workers should check current eligibility right before sending rather than relying on a stale check.

### 11.3. Do Not Render Just to Decide Eligibility

Avoid writing template expressions with logic like "if user is ineligible, render empty." Deciding whether to send belongs to domain/service code, not an empty HTML result.

## 12. Multi-Recipient Fan-Out: Share Only Truly Common Content

A campaign sent to many recipients falls into two categories.

### 12.1. Identical Content

A public announcement containing no user names, orders, tokens, or personalized unsubscribe links can render its body once per valid variant:

~~~text
Public content + templateVersion + locale
                   |
                   v
             Render once
                   |
                   +-- Recipient A: own MIME/envelope
                   +-- Recipient B: own MIME/envelope
                   +-- Recipient C: own MIME/envelope
~~~

Still build separate messages/envelopes when needed to protect recipient lists, track per-recipient outcomes, and retry independently.

### 12.2. Personalized Content

~~~text
Recipient A + View A -> HTML A
Recipient B + View B -> HTML B
Recipient C + View C -> HTML C
~~~

Never reuse HTML A for recipient B merely because the template name matches.

### 12.3. Check Every Source of Personalization

Even an email with a shared body can include:

- Greeting by name.
- Per-tenant footer.
- Per-recipient unsubscribe URL.
- Per-recipient tracking links.
- Unique discount codes.
- Different languages/locales.
- Customer-tier support links.

If any element differs, the output cache must be scoped accordingly or each message should render independently.

### 12.4. Avoid Sending One Message with Mass To/Cc

Sharing a body does not mean sending one MIME message exposing the recipient list. Putting everyone in To/Cc leaks addresses. Render optimization and SMTP batching are separate concerns.

## 13. Shared Fragments: Parse Cache vs. Output Cache

Thymeleaf supports fragments for headers, footers, and layouts:

~~~html
<div th:replace="~{fragments/common :: header}"></div>

<p th:text="${messageText}">Content</p>

<div th:replace="~{fragments/common :: footer}"></div>
~~~

Using fragments aids template maintainability, while parser caching avoids re-parsing fragment files repeatedly. **It does not mean fragment output is rendered only once across all emails by default.**

### 13.1. When Can Fragment Output Be Cached?

The fragment must be genuinely invariant within the cache scope:

- Contains no recipient-specific data.
- Contains no tokens or dynamic timestamps.
- Independent of tenant, or keyed by tenant.
- Independent of locale, or keyed by locale.
- Versioned/invalidated when content changes.

### 13.2. When Should It Not Be Cached?

Never share-cache footers containing per-recipient unsubscribe links, tenant-specific branded headers, or notices restricted to authorized users.

### 13.3. Prefer Engine Parser Caching First

Unless profiling proves fragment evaluation is a major cost, reusing the engine and caching parsed templates is far simpler than building a distributed fragment-output cache.

## 14. Memoization Within a Single Request or Worker Attempt

An effective, low-risk pattern:

~~~java
RenderedMail rendered = renderer.render(view);

MimeMessage message = mimeFactory.build(
        recipient,
        rendered
);

sender.send(message);
~~~

Illustrative calls in the code demonstrate data flow; **mimeFactory** is an application component.

A local variable offers clear advantages:

- No TTL or eviction needed.
- Never shared across recipients.
- No distributed synchronization needed.
- Does not retain PII beyond processing time.
- Easy to test and trace.

### 14.1. When Is a Local Object Insufficient?

If a worker fails and retries on another process, `RenderedMail` is no longer in memory. Reusing across restarts requires durably persisting snapshots or rendered content.

### 14.2. Never Use an Unbounded Static Map

A global cache holding personalized HTML can cause memory leaks, stale content, or data leaks. If long-lived caching is truly required, it needs size bounds, strict keys, TTL, eviction, isolation, and data protection.

## 15. Cache Keys for Rendered Output Must Be Complete

When caching output outside a single workflow, factors affecting content may include:

~~~text
templateId
templateVersion
locale
tenantId / brand
mailKind
businessEventId
recipient / personalizationScope
viewDataVersion or digest
featureFlagsVersion
~~~

No single cache key fits every email. Identify every variable actually used by the template or formatters.

### 15.1. Keying Only by templateId Is Dangerous

Two `order-confirmation` emails have different recipient names and order totals. Keying only by `templateId` can send customer A's email to customer B.

### 15.2. Keying Only by Recipient Is Also Insufficient

The same user can have multiple orders, different OTP codes, or multiple password-reset events. Keys must distinguish each send intent and its specific data.

### 15.3. Template Versions Prevent Stale Output

If template v5 updates legal wording, a cache entry from v4 does not update automatically. Use explicit versioning or invalidation.

### 15.4. Tenant and Locale Cannot Be Omitted

An email for tenant A may carry different logos, support addresses, or policies than tenant B. Locale governs translations and formatting. Sharing output across scopes causes privacy and business bugs.

### 15.5. Hashing the Key Does Not Protect the Value

Even if hashing/HMAC hides raw emails in the key, the cached HTML value still holds PII, tokens, or amounts. Enforce access control and encryption/retention on the cached values themselves.

## 16. TTL, Invalidation, and Sensitive Data

A long-lived output cache requires a lifecycle policy.

| Question | Reason |
| --- | --- |
| How long is cache retained? | Avoid stale data and retaining PII past expiry |
| What if the template changes? | Version or invalidate |
| What if business data changes? | Snapshot vs. refresh |
| What if the recipient unsubscribes? | Re-check eligibility |
| What if a token expires? | Avoid sending useless links |
| What if the cache fills up? | Eviction and memory limits |
| Is the cache shared across tenants? | Isolation |
| Are cache entries logged/exported? | Privacy and secret exposure |
| What happens on node restart? | Local cache resets; distributed cache persists |

### 16.1. Never Cache OTPs or Reset Links Indefinitely

Password-reset emails typically contain expiring tokens. Stale rendered HTML can be expired. Generating a fresh token requires domain logic and possibly a **new mail event**, not a template inventing random tokens per `process` call.

### 16.2. Redis Is Not Automatically Faster

A network cache lookup can take as long as or longer than a small render. Distributed caches also add serialization, invalidation, security, and operational costs. Add them only when metrics prove net benefit.

### 16.3. Never Cache Errors as Successful Output

If a template is missing or an expression fails, never store an empty string in the cache so subsequent retries send blank emails. Mark render failures explicitly.

## 17. Outbox: Store a DTO Snapshot or Rendered HTML?

With a transactional outbox, send jobs may retry after seconds, minutes, or on another node after a restart.

Two main options:

| Approach | Stored in Outbox | On Retry | Pros / Cons |
| --- | --- | --- | --- |
| **View model snapshot** | Template variables and template version | Re-renders | Less HTML stored, repeated CPU |
| **Rendered content snapshot** | Subject/plain/HTML and metadata | Reused | Fewer renders; requires PII protection and freshness checks |
| **Hybrid** | View snapshot + stateful rendered content | Reused while valid | More states and policy rules |

### 17.1. Store View Model, Render in Worker

~~~text
Business transaction
    |
    +-- Commit business change
    +-- Insert mail outbox with view snapshot
    |
    v
Worker
    |
    +-- Render
    +-- Build MimeMessage
    +-- Send
~~~

Benefit: no rendering inside the business transaction; output matches the desired template version. However, retries may re-render unless a content cache is used.

### 17.2. Persist Rendered Content After the First Render

~~~text
Outbox PENDING
    |
    v
Worker loads view snapshot
    |
    v
Render once
    |
    v
Persist subject/plain/html safely
    |
    v
SMTP attempt 1
    |
    +-- Temporary failure
    |
    v
SMTP attempt 2 reuses persisted content
~~~

As long as the persisted output remains policy-valid, retries do not re-render.

### 17.3. Store Securely

Rendered content can include customer details, amounts, or private links. Enforce tenant isolation, authorization, encryption at rest where appropriate, retention, auditing, and never log full HTML.

### 17.4. Crashing Before Persistence Can Still Re-Render

If a worker finishes rendering and crashes before saving the output, the retry will re-render. You cannot guarantee render-exactly-once across every failure window with an outbox alone.

## 18. Render-Once Does Not Guarantee Send-Once

Example:

~~~text
Render HTML
    |
    v
Persist HTML
    |
    v
SMTP server accepts message
    |
    v
Worker crashes before status update
    |
    v
Retry sends same HTML again
~~~

Here rendering happened once, yet the message may be sent twice.

Distinguish:

- **Render reuse:** avoids redundant template work.
- **Outbox:** keeps send intents durable.
- **Claim/lease:** coordinates workers.
- **Idempotency:** prevents creating duplicate intents for the same event.
- **Retry:** recovers from transient failures.
- **Unknown outcome handling:** handles cases where SMTP may have accepted the message.

Standard SMTP provides no universal exactly-once delivery guarantee. HTML caching is not a mechanism to eliminate all duplicate emails.

## 19. When Must You Re-Render?

Valid reasons:

1. The template changed and policy requires sending the updated version.
2. Business data must reflect current state.
3. Recipient, tenant, locale, or branding changed.
4. The recipient lost permission to view the content.
5. Tokens or links expired.
6. Prior output was erroneous or incomplete.
7. Mandatory legal/compliance wording changed.
8. The worker sees a snapshot version that is no longer permitted.
9. Feature flags altered message semantics.
10. A new mail event was created for a new business action.

### 19.1. Snapshot Content vs. Live Content

**Snapshot:** content reflects an event that has already occurred, such as an issued invoice. Retries usually need to keep it unchanged.

**Live:** content must reflect the state at send time. It may need to be re-rendered if the job is delayed.

This needs to be decided per email type rather than letting a cache choose automatically.

### 19.2. Avoid generating tokens directly in templates

If a template expression generates a new OTP/magic link on every `process`, retries may change the token or create unintended extra credentials. Generate the token in the business layer with its own policy and pass it into the view model.

### 19.3. Avoid uncontrolled current time

If a template reads the current time itself, output between two renders can differ. For event-based emails, pass a deterministic `Instant` into the view model to preserve consistency.

## 20. Concurrency and cache stampede

A custom-built output cache can encounter:

~~~text
Worker A -> cache miss -> render
Worker B -> cache miss -> render
Worker C -> cache miss -> render
~~~

If all use the same safe key, a per-key single-flight or compute-if-absent mechanism can help reduce duplicate rendering.

However, you need to control:

- Bounded cache and TTL.
- Do not place a single global lock across all templates.
- Do not hold a lock while making slow database/network calls.
- Do not cache exceptions permanently.
- Do not share personalized output across the wrong scope.
- Do not let one failing key block all workers.
- Do not assume a local cache resolves duplicates across nodes.

### 20.1. Do not prematurely optimize with a distributed lock

For most emails with personalized content, each event genuinely needs one render. A distributed lock does not reduce the required number of renders and can hurt throughput.

### 20.2. Share TemplateEngine, but do not share Context

Use the configured Spring bean engine and create a **new Context per render**. Do not keep a mutable Context and mutate `customerName` across concurrent requests.

## 21. Resources and attachments are a different performance problem

An email with a PDF or inline image:

~~~java
helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf"
);

helper.addInline(
        "companyLogo",
        logoResource,
        "image/png"
);
~~~

These operations involve MIME resources. Some resources may be read lazily when Jakarta Mail serializes the message inside `JavaMailSender.send`.

Eliminating one HTML render pass does not automatically make a PDF load faster.

### 21.1. Measure steps separately

Metrics you may need:

~~~text
mail.template.render.duration
mail.attachment.generate.duration
mail.resource.load.duration
mail.message.build.duration
mail.smtp.submit.call.duration
~~~

### 21.2. Do not serialize MIME twice just to measure

Calling `message.writeTo(...)` once to measure and then letting `JavaMailSender` do it again can double I/O and CPU. Use instrumentation aligned with the existing operation instead of adding expensive extra work.

### 21.3. Caching attachments also carries risk

If you store PDF `byte[]` for retries, you need limits on size, retention, access control, and integrity. Caching HTML and caching PDFs serve different goals.

## 22. Measure render counts to verify whether optimization works

Suggested metrics:

| Metric | Meaning |
| --- | --- |
| **mail.template.render.invocations** | Number of `process` calls |
| **mail.template.render.duration** | Duration per render |
| **mail.template.render.failures** | Number of render errors |
| **mail.template.output.reuse** | Number of output reuses |
| **mail.template.output.cache.hit** | Cache hits |
| **mail.template.output.cache.miss** | Cache misses |
| **mail.event.created** | Number of send intents |
| **mail.smtp.submit.attempts** | Number of send attempts |
| **mail.outbox.pending** | Backlog |

### 22.1. Render invocations per event

If an email uses a single HTML template yet metrics report 3 renders/event, check for redundant preview, validation, build, or retry renders.

If an email uses separate HTML and text templates, 2 passes may be expected. Do not apply the same target to every message type.

### 22.2. Distinguish by purpose

You can group by:

~~~text
purpose=preview
purpose=delivery
purpose=retry
~~~

A preview explicitly requested by a user is not necessarily a wasted render.

### 22.3. Counting cache hits is not enough

An output cache with a high hit rate but slow network lookups, oversized payloads, or complex invalidation may fail to improve overall system performance. You must compare CPU, memory, render duration, send latency, and operational overhead.

## 23. Instrumenting a Thymeleaf renderer with Micrometer

An adapter measuring `Timer` and `Counter`:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.IContext;

public final class ObservedHtmlRenderer {

    private final TemplateEngine engine;
    private final MeterRegistry registry;

    public ObservedHtmlRenderer(
            TemplateEngine engine,
            MeterRegistry registry
    ) {
        this.engine = engine;
        this.registry = registry;
    }

    public String render(
            String template,
            IContext context,
            String kind
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return engine.process(template, context);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.template.render.duration",
                            "kind", kind,
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.template.render.invocations",
                    "kind", kind,
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

### 23.1. Record failures too

Because the measurements live in `finally`, failed renders are still counted. If you only measure successes, dashboards will miss renders that failed due to data or template issues.

### 23.2. Control cardinality

**kind** must come from a bounded set of email type names. Do not put recipient, `orderId`, `eventId`, or arbitrary user-supplied template strings into metric tags.

### 23.3. Do not log full HTML

If diagnostics are needed, record correlation ID, kind, template version, duration, and error category. Rendered HTML can contain PII, tokens, or transaction details.

### 23.4. Do not add two overlapping Timers

If you have an outer `Timer` covering all mail preparation and a child `Timer` for rendering, do not sum their durations and call that total preparation time. The parent timer already includes the child timer.

## 24. Comparing before and after optimization

| Metric | What to evaluate |
| --- | --- |
| Render count/event | Did redundant passes decrease? |
| Total render CPU time | Did actual CPU cost drop? |
| Render p50/p95/p99 | How did per-pass latency change? |
| Worker CPU and allocation | Did memory/GC improve? |
| Queue delay | Are workers processing faster? |
| Event-to-relay acceptance | Are users seeing a benefit? |
| Cache lookup latency | Does it offset render savings? |
| Error ratio | Are there any new errors? |
| Stale/misrouted content incidents | Is data safety preserved? |

### 24.1. Per-render p95 may not drop

If a single render still takes 10 ms while dropping from 3 passes to 1, render p95 remains near 10 ms, whereas total template CPU can drop significantly.

### 24.2. End-to-end latency may not change

If SMTP and queueing take almost all the time, optimizing rendering may not make users receive emails noticeably faster. Even so, it can increase capacity and reduce cost under high traffic.

### 24.3. Optimize only with a baseline

Before building a Redis cache or distributed lock, measure process counts, duration, CPU, load, and errors, then re-test under the same load conditions.

## 25. Unit test verifying single-pass rendering

Mockito can verify orchestration without a real SMTP server:

~~~java
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Locale;
import java.util.Properties;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.IContext;

class OrderMailDeliveryServiceTest {

    @Test
    void rendersHtmlOnceBeforeSending() {
        TemplateEngine engine = mock(TemplateEngine.class);

        when(engine.process(
                eq("order-confirmation"),
                any(IContext.class)
        )).thenReturn("<p>Order confirmed.</p>");

        OrderMailRenderer renderer =
                new OrderMailRenderer(engine);

        JavaMailSender sender =
                mock(JavaMailSender.class);

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage())
                .thenReturn(message);

        OrderMailView view = new OrderMailView(
                "event-1001",
                "an@example.net",
                "Nguyễn An",
                "ORDER-1001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z"),
                Locale.forLanguageTag("vi-VN")
        );

        OrderMailDeliveryService service =
                new OrderMailDeliveryService(renderer, sender);

        service.send(view);

        verify(engine, times(1)).process(
                eq("order-confirmation"),
                any(IContext.class)
        );

        verify(sender, times(1))
                .send(any(MimeMessage.class));
    }
}
~~~

### 25.1. What does the test prove?

For one service call, `engine.process` for HTML is called once and `sender.send` is called once. Mockito does not open an SMTP connection.

### 25.2. Test actual content separately

Because the engine in this test is mocked, the test above **does not prove** that the real HTML is correct. You need a separate test using the real template and mock data to verify escaping, locale, subject, and `text/plain`.

### 25.3. Test that ineligible input does not render

If the service has an eligibility check before the renderer:

~~~java
verifyNoInteractions(engine);
verify(sender, never()).send(any(MimeMessage.class));
~~~

are useful assertions for events that are ineligible for sending.

## 26. Test that content is not mixed across recipients

A particularly important test when using an output cache:

~~~java
String htmlA = renderer.render(viewA).html();
String htmlB = renderer.render(viewB).html();

assertTrue(htmlA.contains("ORDER-A"));
assertFalse(htmlA.contains("ORDER-B"));

assertTrue(htmlB.contains("ORDER-B"));
assertFalse(htmlB.contains("ORDER-A"));
~~~

This snippet illustrates assertions where **viewA/viewB** are independent fixtures and the renderer uses the real template. It guards against missing fields in the cache key or a shared `Context`.

Scenarios to cover:

- Recipients A and B with different names and orders.
- Same recipient, different events.
- Two tenants sharing the same template name.
- Two different locales.
- Template v4 and v5.
- Multiple workers invoking render concurrently.
- Different tokens or signed URLs.
- Expired or invalidated cache entries.

**Never consider a reduced render count a success if customer outputs leak across recipients.**

## 27. Testing retries and output snapshot states

An outbox testing matrix:

| Scenario | Expected behavior |
| --- | --- |
| No output snapshot yet | Render and store if policy requires |
| SMTP 421 retry with valid snapshot | Reuse output |
| Worker restart | Read durable output if already persisted |
| Render failure | Do not send via SMTP; record preparation error |
| Recipient changed | Do not reuse for the wrong recipient |
| Template version changed | Use old snapshot or regenerate per policy |
| Token expired | Do not resend an invalid link |
| Duplicate event | Avoid creating duplicate jobs/renders |
| Crash before persist | Allow safe re-render |
| Crash after SMTP accept | Track duplicate-send risk |

Do not test SMTP by sending real emails over the Internet when the goal is only reuse logic. You can use a fake repository/outbox and a mock `JavaMailSender`.

## 28. Anti-patterns to avoid

| Anti-pattern | Problem | How to handle |
| --- | --- | --- |
| Creating a Thymeleaf engine per email | Fails to leverage engine cache | Reuse configured bean |
| Rendering in both controller and worker | Duplicate work | Render in one place, pass the result |
| Rendering twice for HTML and plain text | Redundant calls | `RenderedMail` object |
| Rendering before unsubscribe check | Wasted CPU | Check eligibility first |
| Global cache keyed by `templateId` | Leaks personalized data | Complete scope/key |
| Caching solely by `recipientId` | Mixes different events | Event/version/data key |
| Caching HTML containing OTPs indefinitely | Expired tokens, PII exposure | TTL and domain policy |
| Sharing a mutable `Context` | Concurrent data mixing | New `Context` per render |
| Querying DB inside template | N+1 queries, non-deterministic snapshot | Pre-populated DTO |
| Sharing output across tenants | Wrong branding, privacy leak | Tenant-aware isolation |
| Unnecessary re-render on every retry | Extra CPU and drifting content | Valid snapshot/persistence |
| Confusing parsed-template cache with output reuse | Misconception | Measure `process` invocations |
| Dropping plain text to save CPU | Loses compatibility | Text formatter/template |
| Caching without measuring impact | Adds complexity | Baseline, compare |
| Treating render-once as send-once | SMTP still has a duplicate window | Outbox, idempotency, review |
| Using `eventId` as a metric tag | High cardinality | Correlation ID in logs |

## 29. Frequently asked questions

**1. Does enabling Thymeleaf caching make `process` run only once?**

No. Caching typically reuses the parsed template; each `process` call with a `Context` still generates output. To reduce `process` calls, you must change the call flow or reuse output within an appropriate scope.

**2. Should all HTML emails be cached?**

No. HTML can contain PII, tokens, monetary amounts, and stale content. Cache only when key, TTL, version, access control, and update policy are clearly defined.

**3. Does an email with HTML and plain text require two render passes?**

It may require two if they are two independent templates. If plain text is built from the same view model by a formatter, a single HTML `process` pass may suffice.

**4. Why should `Context` not be a singleton?**

`Context` can hold recipient-specific variables and is typically mutable. Sharing it across threads can mix user data.

**5. Can a public announcement sent to 10,000 people be rendered once?**

Potentially, if the content is genuinely identical and contains no tokens, unsubscribe links, personalization, differing locales, or differing branding. You still need to protect envelope recipients and handle per-recipient retries where appropriate.

**6. Why is `@Cacheable` not the default choice?**

It requires a key covering all data affecting the output plus an invalidation/TTL mechanism. A misconfigured cache can send A's content to B.

**7. Should the outbox store data or HTML?**

It depends on the domain. A data snapshot is smaller and more flexible, though it may need re-rendering. Storing HTML avoids re-rendering on retry, at the cost of storing PII and potentially stale output. You can combine approaches if state transitions are clearly managed.

**8. What if the template changes while retries are in flight?**

You must decide whether to pin the snapshot version or use the new version. Do not let output depend randomly on which node processes the job.

**9. Does rendering once prevent duplicate emails?**

No. SMTP can accept a message and the worker can crash before updating state. A retry can send a duplicate even without re-rendering.

**10. When must an email be re-rendered?**

When template, data, locale, or tenant must change per policy, output is outdated, a token has expired, or a new business event requires different information.

**11. Should regex `String.replace` be used to personalize shared HTML?**

Not as a general strategy. It can break escaping and placeholders, causing HTML injection or data mix-ups. Use a proper template context or a safe formatter.

**12. Does Redis always speed things up?**

No. Cache lookups incur network and serialization overhead. Measure render cost against cache cost, and also account for security and invalidation.

**13. How should render calls be counted?**

Instrument `TemplateEngine.process` in a centralized adapter; record `Counter`/`Timer` metrics with bounded `kind`/`outcome`/`purpose` tags.

**14. Can render counts be tested without SMTP?**

Yes. Mock `TemplateEngine` and `JavaMailSender`, then verify `process` is invoked the expected number of times. Real-template tests should be run separately.

**15. Why didn't send duration improve much even though render counts dropped?**

If SMTP connections, attachments, queueing, or the provider account for most of the time, rendering is not the main bottleneck.

**16. Should queries be executed inside Thymeleaf expressions?**

Avoid this whenever possible. It makes rendering unpredictable and can cause N+1 queries. Preparing the view model upfront keeps it under control.

**17. Is rendered HTML considered personal data?**

It can be. If it contains names, email addresses, amounts, order IDs, or tokens, protect retention, access control, and deletion per policy.

**18. Is cache warming necessary?**

Only if cold-start parsing causes a significant impact. Reusing the engine and parsed-template cache is usually the first step. If you warm the cache, use dummy data and do not send via SMTP.

## 30. Key takeaways on reducing unnecessary template renders

**Effective render optimization starts by counting template engine calls and clearly defining what content may be reused.** In Spring Framework Mail, separate business data from templates, build a clear view model, use a single configured engine with parsed-template caching, and pass a **RenderedMail** object across MIME preparation instead of rendering multiple times for Subject, HTML, and plain text.

Check **eligibility, suppression, and validation** before rendering emails that will not be sent. For fan-out, share only non-personalized output within the same template version, locale, and tenant scope; never share recipient A's data with B. With a transactional outbox and retries, consider snapshotting the view model or persisting rendered content alongside TTL, versioning, access control, and expired-token policies.

**Render-once is not send-once**: SMTP errors and crashes can still produce duplicates. Measure render invocations, duration, CPU, and end-to-end impact with Micrometer; verify counts with Mockito while testing output isolation against real templates.

The desired outcome is **eliminating genuinely redundant renders** while still producing the right email, for the right recipient, at the right version, at the right time.
