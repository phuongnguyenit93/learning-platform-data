# Template Versioning and Data Compatibility

Transactional emails are typically sent from HTML templates such as order confirmations, invoices, password resets, or shipping notifications. Over time, templates evolve: adding display fields, changing layouts, supporting new languages, or adding links. Meanwhile, the data the application passes into templates also changes alongside models and business rules.

If a new template requires a field that an old event lacks, the email may fail during rendering. If a field is renamed or changes meaning while an old template still uses it, content can become wrong even though the application still sends the message successfully. Therefore, two related yet distinct things must be managed:

- **Template version:** the version of the email's content and presentation structure.
- **Data contract/schema version:** the version of the structure and meaning of the data the template receives to render.

In **Spring Framework Mail**, a template engine such as Thymeleaf renders the body from a model; `JavaMailSender` and `MimeMessageHelper` package and send the MIME message. Versioning should be organized at the template and model management layer, before the message is sent.

## 1. Why Do Email Templates Need Versioning?

An initial template might display only the customer name and order code:

```html
<p>Hello <span th:text="${customerName}">Customer</span>.</p>
<p>Order <strong th:text="${orderCode}">ORD-001</strong> has been confirmed.</p>
```

Later, the product team wants to add total amount and estimated delivery date:

```html
<p>Total amount: <span th:text="${totalAmountLabel}">0 ₫</span></p>
<p>Estimated delivery: <span th:text="${estimatedDeliveryLabel}">Delivery date</span></p>
```

The new template may need variables:

```text
customerName
orderCode
totalAmountLabel
estimatedDeliveryLabel
```

Meanwhile, an older event sitting in the queue might contain only:

```json
{
  "customerName": "Alice Nguyen",
  "orderCode": "ORD-001"
}
```

If the system replaces the current template with a version requiring all four variables without a compatibility strategy, old events may render with missing data or fail. This is a **data contract issue between producer and consumer**:

```text
Business service / event producer
          |
          | data following schema
          v
      Mail model
          |
          | variables passed in
          v
     Email template
          |
          | HTML / plain text
          v
 MimeMessageHelper -> JavaMailSender -> SMTP
```

The template is a consumer of data. Every change to a template or model must check whether consumer and producer still understand the same contract.

Versioning helps:

- Keep old emails renderable while older events remain in the queue.
- Roll out content changes gradually without interrupting mail delivery.
- Know exactly which template produced an email during investigations.
- Support rolling back to a version known to be compatible.
- Separate visual layout changes from changes to data structure or meaning.
- Manage multiple languages, tenants, or notification types with independent lifecycles.

## 2. Distinguishing Template Version and Data Schema Version

These two versions can change independently.

| Concept | Description | Example |
| --- | --- | --- |
| **Template version** | Version of HTML/text content and presentation | `order-confirmation/v2` changes layout, adds total section |
| **Data schema version** | Version of structure and semantics of the model passed to template | `OrderConfirmationDataV2` adds `totalAmountLabel` |
| **Business event version** | Version of business event payload stored or sent via queue | `OrderConfirmedV1` emitted by order service |
| **Renderer version** | Version of logic preparing the model or rendering templates | Adapter converting legacy model to new model |

Do not assume a single version number represents every layer. For instance, template `v3` can still use data schema `v2`; a template can update colors without changing the model; or a schema can be upgraded while the template stays the same.

### Independent Versions Example

```text
Template order-confirmation/v1
        |
        +-- uses OrderConfirmationDataV1

Template order-confirmation/v2
        |
        +-- uses OrderConfirmationDataV1
        |      (layout change only, new data not needed yet)
        |
        +-- or OrderConfirmationDataV2
               (adds totalAmountLabel)
```

A request metadata record might look like:

```json
{
  "templateKey": "order-confirmation",
  "templateVersion": 2,
  "dataSchemaVersion": 1,
  "locale": "vi-VN"
}
```

This indicates presentation template version 2 still accepts data schema version 1. That is a valid option if template v2 does not require new fields or the renderer can provide defaults.

## 3. Defining the Template Data Contract

Before versioning a template, clearly define **what data the template is allowed to receive**. A good data contract describes field names, data types, meaning, nullability, and formatting.

Example contract for an order confirmation email:

| Field | Type | Required? | Meaning |
| --- | --- | --- | --- |
| `customerName` | String | Yes | Normalized display name |
| `orderCode` | String | Yes | Order code |
| `orderUrl` | URI/String | Yes | Application-generated HTTPS URL |
| `totalAmountLabel` | String | No in schema v1; may be required in v2 | Total amount formatted by locale/currency |
| `estimatedDeliveryLabel` | String | No | Formatted estimated delivery date |
| `locale` | Locale/code | Yes per send request | Language and formatting conventions |

A contract should document more than variable names:

- **Type:** String, BigDecimal, Instant, UUID, enum, or custom data type.
- **Nullability:** whether a field can be absent, null, or must always be present.
- **Meaning:** is `orderDate` order creation time, confirmation time, or payment time?
- **Formatting:** does monetary amount include currency, and which time zone do dates use?
- **Source:** which service does the field come from and what validation has it passed?
- **Security context:** is the data permitted in emails and visible to this recipient?
- **Display rules:** when a value is missing, hide the section, display fallback text, or treat as an error?

### Do Not Pass the Entire Entity into the Template

Do not pass a database entity or large domain object directly into the template context merely for convenience:

```java
// Avoid: template can access too many unrelated fields.
context.setVariable("order", orderEntity);
context.setVariable("customer", customerEntity);
```

Create a **mail model** containing only data needed for display:

```java
public record OrderConfirmationDataV1(
        String customerName,
        String orderCode,
        String orderUrl
) {}
```

The mail model acts as a boundary between business logic and the template. When entities change, templates are not directly coupled to database structure. Furthermore, selective fields reduce the risk of exposing information not meant for emails.

## 4. Which Changes Are Compatible and Which Break the Contract?

Whether a change is compatible depends on **the direction of change**: a new template reading old data, or an old template reading new data.

### 4.1. Changes That Are Usually Backward Compatible

In the template-consumer context, a new template can still work with old data when:

- Adding an **optional** field and the template has a fallback when missing.
- Adding a presentation section that needs no new data.
- Changing colors, fonts, spacing, or layout without altering the contract.
- Adding a field used only when present, not required for old events.
- Adding a variable that the renderer can derive from old fields with equivalent meaning.

For example, template v2 adds an estimated delivery line but displays it only when data exists:

```html
<p th:if="${estimatedDeliveryLabel != null}">
  Estimated delivery:
  <span th:text="${estimatedDeliveryLabel}">Not available yet</span>
</p>
```

If the old model does not supply `estimatedDeliveryLabel`, the template can still render the rest. However, if a variable is omitted from the context, ensure template engine expressions handle missing variables as desired; a clearer approach is for the renderer to normalize the model and always supply null or a default value.

### 4.2. Changes That Can Break Compatibility

| Change | Why It Can Be Breaking | How to Handle |
| --- | --- | --- |
| Removing a field used by the template | Template no longer has data to render | Keep the field during transition or create a new schema |
| Renaming `customerName` to `recipientName` | Old consumers still look for the old name | Adapter or new schema/template version |
| Changing `totalAmount` type from number to unformatted string | Formatting logic may misbehave or error | Define a new field with explicit type and meaning |
| Changing `orderDate` from creation time to confirmation time | Name stays the same while meaning changes | Use a new field name or version the contract |
| Making an optional variable required | Old events may lack the value | Migrate data or release a new schema |
| Changing date format without notice | Templates or clients misread it | Keep standard time types and format at the right layer |
| Changing `orderUrl` from full URL to relative path | Templates/renderers may produce broken links | Use a new field or preserve the old contract |
| Changing currency unit while keeping field name | Content may become business-incorrect | Attach currency explicitly and version the contract |

**Changing a field's meaning is also a breaking change**, even when name and type stay identical. For example, `amount` previously meant post-tax total and now means pre-tax amount; the template still renders, yet the email gives wrong information.

### 4.3. Forward Compatibility

Forward compatibility here usually means **old consumers can still process new data**:

- Producer adds a new field; old template ignores it because it is unused.
- DTO adapter forwards only the fields the old template needs.
- Event payload has extended fields while preserving old fields and old semantics.

Template engines usually ignore unreferenced variables. However, if the renderer strictly validates the whole model or changes old field names/types, compatibility can break. Therefore, define the contract explicitly rather than relying on template engines ignoring unknown fields.

## 5. Strategies for Versioning Templates

There are several ways to manage template versions. The right choice depends on whether templates are packaged with the application or managed externally.

### 5.1. Version in Resource Paths

With templates on the classpath:

```text
src/main/resources/templates/mail/
└── order-confirmation/
    ├── v1.html
    ├── v2.html
    └── v3.html
```

The renderer selects a specific template name:

```java
String templateName = switch (version) {
    case 1 -> "mail/order-confirmation/v1";
    case 2 -> "mail/order-confirmation/v2";
    default -> throw new IllegalArgumentException(
            "Unsupported template version: " + version
    );
};
```

Pros:

- Old and new versions can coexist in one artifact.
- Easy to review changes in Git.
- Can re-render an old event with the exact template version.
- Rollback can re-select the previous version if the model is compatible.

Limitations:

- Editing a template usually requires building and deploying the application.
- With multiple locales, file count grows by templates × versions × locales.
- Requires a cleanup policy for old versions once no events need them.

### 5.2. Versions in a Template Storage System

With templates managed in a database or internal service, you can store metadata:

| Field | Example |
| --- | --- |
| `template_key` | `order-confirmation` |
| `version` | `2` |
| `locale` | `vi-VN` |
| `data_schema_version` | `2` |
| `status` | `DRAFT`, `PUBLISHED`, `RETIRED` |
| `created_at` | Creation timestamp |
| `published_at` | Publication timestamp |
| `content_hash` | Hash of template content |

A **PUBLISHED** version should be treated as immutable. If edits are needed, create a new version instead of overwriting published content. This makes it possible to know exactly which content generated an email.

A template management system also needs:

- Permissions controlling who can edit and who can publish.
- Audit history of changes and authors.
- Template validation before publication.
- Control over allowed variables.
- Restricting template access from untrusted sources.
- Mechanisms to select the active version and roll back.

### 5.3. The `current` or `active` Alias

An application may have a logical pointer:

```text
order-confirmation/current -> order-confirmation/v3
```

An alias helps pick the new version for emails generated after rollout. However, if an event sits in a queue for hours and the worker only looks up `current` at processing time, that event may be rendered with the new template even though it was created when the old version was active.

That may or may not be the desired behavior. If content reproducibility is needed, **save the selected version with the event or mail request** when creating the send request.

### 5.4. Should Semantic Versioning Be Used?

You can use meaningful version numbers:

- **Major:** incompatible contract changes, such as removing/renaming required fields or changing semantics.
- **Minor:** adding optional fields or new capabilities compatible with old models.
- **Patch:** presentation fixes, typos, or CSS changes that do not alter the contract.

For example, `2.1.3` represents template major 2, minor 1, patch 3. This is a **project-chosen governance convention**, not a mandatory standard of Spring Mail or Thymeleaf. If a project only needs integers `v1`, `v2`, that can also suffice; what matters is classifying breaking changes consistently.

## 6. Versioning the Data Contract

The template version only tells **which content to use**. To render accurately, the application also needs to know which schema the model follows.

A simple approach is defining separate DTOs per version:

```java
import java.util.Locale;

public record OrderConfirmationDataV1(
        String customerName,
        String orderCode,
        String orderUrl,
        Locale locale
) {}

public record OrderConfirmationDataV2(
        String customerName,
        String orderCode,
        String orderUrl,
        String totalAmountLabel,
        String estimatedDeliveryLabel,
        Locale locale
) {}
```

Here V2 adds two fields. V1 preserves the old contract so old events or processing flows can continue working.

### Do Not Simply Add Fields to an Uncontracted Map

Example:

```java
Map<String, Object> model = new HashMap<>();
model.put("customerName", customerName);
model.put("orderCode", orderCode);
model.put("totalAmount", amount);
```

A Map is flexible yet carries several risks:

- Typos in field names are caught only at render time or when content is missing.
- Data types can drift silently between producers.
- Does not clearly express which fields are required and which are optional.
- The meaning of a key can change without compiler support.

If using a Map because the template engine needs a key-value context, build the Map from a **strongly typed DTO** in an adapter step. Do not let every service set arbitrary keys on its own.

### Distinguishing Missing, Null, and Empty Fields

These three states can carry different meanings:

| State | Possible Meaning | How to Handle |
| --- | --- | --- |
| Field absent from payload | Old producer did not know the field | Adapter supplies default or null |
| Field has value null | Producer knows the field but lacks data | Display fallback content or hide section |
| Field is empty string | Field present but value has zero characters | Normalize per contract |
| Field has valid value | Data present to display | Render in the right context |

Do not rely on how a template engine handles missing variables as a contract rule. Normalize states in the mail model so the template receives data with clear semantics.

## 7. Using Adapters for Old and New Data Compatibility

When an old producer emits events under schema V1 while a new template needs V2, you can use an **adapter** to convert:

```text
Legacy event V1
  customerName, orderCode, orderUrl
          |
          v
   OrderConfirmationAdapter
          |
          | fill default values or look up appropriate data
          v
   OrderConfirmationDataV2
          |
          v
   Template order-confirmation/v2
```

Example:

```java
public final class OrderConfirmationAdapter {

    private OrderConfirmationAdapter() {}

    public static OrderConfirmationDataV2 fromV1(
            OrderConfirmationDataV1 oldData
    ) {
        return new OrderConfirmationDataV2(
                oldData.customerName(),
                oldData.orderCode(),
                oldData.orderUrl(),
                null,
                null,
                oldData.locale()
        );
    }
}
```

The adapter above **does not invent data**: the two new fields are left null because V1 lacks that information. Template V2 must handle missing states deliberately.

If new data can be fetched from an authoritative source, the adapter can take an additional service for lookup. However, consider:

- Is the data still accurate at send time?
- Should an old event reflect order state at creation time or current state?
- Will the lookup alter the meaning of an email already created earlier?
- If the data service is unavailable, should the email wait, fall back, or fail?

The adapter is where contract translation happens; do not hide critical business logic inside template expressions.

## 8. Designing New Templates with Clear Fallbacks

A V2 template can accept new fields while still handling old data:

```html
<h1>Order Confirmed</h1>
<p>
  Hello
  <strong th:text="${customerName}">Customer</strong>!
</p>
<p>
  Order code:
  <strong th:text="${orderCode}">ORD-001</strong>
</p>

<section th:if="${totalAmountLabel != null and !#strings.isEmpty(totalAmountLabel)}">
  <p>
    Total amount:
    <strong th:text="${totalAmountLabel}">0 ₫</strong>
  </p>
</section>

<section th:if="${estimatedDeliveryLabel != null and !#strings.isEmpty(estimatedDeliveryLabel)}">
  <p>
    Estimated delivery:
    <span th:text="${estimatedDeliveryLabel}">Not available yet</span>
  </p>
</section>

<a th:href="${orderUrl}">View order</a>
```

The template uses `th:if` to display only sections with data. Text values use `th:text` for escaping. `orderUrl` must be generated by the backend from a trusted domain and validated before entering the template; HTML escaping on `th:href` does not validate the URL destination on its own.

A meaningful fallback must be defined by business rules. For example, if no estimated delivery date exists, hiding that line can make sense. However, if a security verification code is missing, **never generate a dummy value** just to make the template render.

## 9. Selecting a Template Version for Each Email

When multiple versions exist, the system needs a selection rule:

- Use the latest version for all new emails.
- Pin the version to the event when the event is created.
- Choose by notification type, locale, tenant, or campaign.
- Keep old versions for backlogged events in the queue.
- Allow partial rollouts and then expand.

A request metadata record might look like:

```java
public record TemplateRef(
        String templateKey,
        int templateVersion,
        int dataSchemaVersion,
        String locale
) {}
```

Example:

```java
TemplateRef ref = new TemplateRef(
        "order-confirmation",
        2,
        1,
        "vi-VN"
);
```

This means using template v2 with schema v1 model. If template v2 requires schema v2, the request must state that explicitly or an adapter must convert it.

### Selecting Templates via Allowlist

Do not take template names directly from untrusted input:

```java
// Avoid: external data decides arbitrary template names.
String templateName = request.templateName();
String html = templateEngine.process(templateName, context);
```

Map a key/version allowed by the application:

```java
public String resolveTemplateName(TemplateRef ref) {
    if (!"order-confirmation".equals(ref.templateKey())) {
        throw new IllegalArgumentException("Unsupported template key");
    }

    return switch (ref.templateVersion()) {
        case 1 -> "mail/order-confirmation/v1";
        case 2 -> "mail/order-confirmation/v2";
        default -> throw new IllegalArgumentException(
                "Unsupported template version"
        );
    };
}
```

In a real application, you can use a registry/catalog instead of a switch. Either way, versions must be looked up from a registered and authorized list.

### Which Version Is Used for Pending Events?

This is an important decision in asynchronous systems:

| Policy | How Old Queue Events Are Handled | Best Fit When |
| --- | --- | --- |
| **Pin at creation** | Save template version when creating request; worker reuses that version | Reproducibility and consistent content are required |
| **Resolve at send time** | Worker picks `current` when starting to send | Every email should use the latest content |
| **Pin schema, resolve template** | Keep the event's schema yet choose a template compatible with that schema | Many visual templates exist while the data contract is stable |
| **Adapter then current** | Convert old event to current model and use active template | A reliable adapter exists and reducing maintained templates is desired |

No single policy fits every product. Invoices or confirmation emails may need content/versions tied to the business timestamp; marketing emails may prefer using the active template at send time. Decide the policy before implementing.

## 10. Rolling Out Contract Changes Additively

When a new field must be added, the least disruptive rollout is **add first, use later, and only make required if truly necessary**.

Suppose V1 only has `customerName`, `orderCode`, `orderUrl`; V2 adds `totalAmountLabel`.

### Phase 1 — Extend Producer Compatibly

The producer adds the new field while keeping old fields:

```json
{
  "schemaVersion": 1,
  "customerName": "Alice Nguyen",
  "orderCode": "ORD-001",
  "orderUrl": "https://app.example.org/orders/...",
  "totalAmountLabel": "1.250.000 ₫"
}
```

During this phase, old consumers/templates ignore the new field. Once the new field becomes an official part of the schema, release schema v2 instead of silently mutating the v1 contract.

### Phase 2 — Release Template/Renderer Supporting Optional Field

Template V2 displays `totalAmountLabel` when present. The model adapter can supply null for old events.

### Phase 3 — Begin Sending New Data

New producers emit events under schema V2; consumers know how to read V1 and V2 or have a conversion adapter. Template V1 still works with old models if events remain to be processed.

### Phase 4 — Monitor and Retire V1

Retire V1 support only when:

- No V1 events remain in queues/retries/dead-letter queues needing rendering.
- Old producers have been upgraded or stopped emitting.
- Legacy payload stores have been migrated or have long-term adapters.
- Historical content can be recovered or queried per retention policy.

Do not delete old templates/schemas merely because the new deployment finished; queues, retries, and long-term storage may still reference old versions.

## 11. Migration Process When a Field Is Renamed or Changes Meaning

Suppose `customerName` needs to be renamed to `recipientDisplayName`.

**Error-prone approach:**

1. Rename the field in the producer.
2. Delete `customerName`.
3. Deploy the new template.
4. Old events still contain `customerName`, while the new template looks for `recipientDisplayName` and finds no data.

**Phased conversion approach:**

```text
Schema V1:
  customerName
      |
      v
Adapter:
  recipientDisplayName = customerName
      |
      v
Schema V2:
  recipientDisplayName
      |
      v
Template V2
```

During the transition, the adapter understands both schemas:

```java
public String resolveRecipientDisplayName(
        Integer schemaVersion,
        String customerName,
        String recipientDisplayName
) {
    if (schemaVersion != null && schemaVersion >= 2) {
        return recipientDisplayName;
    }
    return customerName;
}
```

This is a simple example. Production code should use versioned DTOs and validate required fields; do not let multiple unrelated nullable parameters make the contract ambiguous.

After all producers have moved to V2 and no V1 data remains to process, the old field can be retired in a later release. If a field's meaning changes, **do not reuse the old name with new semantics**; create a new field or a new schema.

## 12. Managing Versions When Templates Have Multiple Languages

A template can have multiple locales:

```text
mail/
└── order-confirmation/
    ├── v1/
    │   ├── vi-VN.html
    │   └── en-US.html
    └── v2/
        ├── vi-VN.html
        └── en-US.html
```

Layout version and locale are two independent dimensions:

| Template version | Locale | Purpose |
| --- | --- | --- |
| v1 | vi-VN | Old Vietnamese version |
| v1 | en-US | Old English version |
| v2 | vi-VN | New Vietnamese version |
| v2 | en-US | New English version |

When only translating content without changing the data contract or layout, you can treat it as updating a locale asset within the same version or issuing a patch per project conventions. If a new language requires new fields or distinct structure, evaluate it as a template/data contract change.

Do not fall back to another language automatically without a rule. For example, if `vi-VN` is missing, falling back to `en-US` may send recipients content they do not understand. Define explicit locale fallback, such as `vi-VN -> vi -> default`, and decide what to do when no translation exists.

## 13. Managing Versions for Externally Stored Templates

Some systems allow editors to author email content via an admin portal and store templates in a database/object storage. In that case, separate:

- **Template key:** stable identifier for the email type.
- **Version:** immutable version once published.
- **Locale:** language.
- **Data schema version:** model contract required by the template.
- **Status:** draft, published, retired.
- **Metadata:** author, timestamp, content/hash, change description.

Logical record example:

```json
{
  "templateKey": "order-confirmation",
  "templateVersion": 3,
  "dataSchemaVersion": 2,
  "locale": "vi-VN",
  "status": "PUBLISHED",
  "contentHash": "sha256:...",
  "publishedAt": "2026-11-12T09:00:00Z"
}
```

When rendering, the template service must:

1. Determine key/version/locale per policy.
2. Fetch the exact published version.
3. Verify the data schema version required by the template.
4. Run an adapter if the model does not match the schema yet.
5. Render with normalized data.
6. Return the result along with version metadata for the sending layer to record.

Editor-managed templates remain **presentation code**. Do not allow templates to execute arbitrary Java, invoke internal services, or access secrets. Restrict editing permissions and control expressions/template features per the application's threat model.

## 14. Handling Errors When Template Versions Are Incompatible

A system should distinguish template selection errors, contract errors, and SMTP sending errors.

| Error | Example | How to Handle |
| --- | --- | --- |
| Template version not found | Event references v3 while artifact only has v1/v2 | Check registry/deployment; fall back only if a defined compatibility mapping exists |
| Unsupported data schema | Template v2 requires schema 2 while model is schema 1 | Run adapter or choose a compatible template |
| Missing required field | `orderCode` is null | Stop rendering and report business error; never invent data |
| Missing optional field | `estimatedDeliveryLabel` is null | Hide corresponding section or display defined fallback |
| Missing locale | No `vi-VN` template exists | Apply published locale fallback or reject explicitly |
| Template syntax error | Invalid Thymeleaf expression | Fix/re-publish template; do not retry SMTP |
| SMTP temporarily unavailable | Timeout, 4xx response | Bounded/backoff retries per sending policy |
| SMTP permanent rejection | Recipient or sender rejected | Address recipient/permission issues; do not retry infinitely |

### Should You Automatically Fall Back to an Old Template?

Only when the old template has been verified **compatible with the current model and content remains business-accurate**. Uncontrolled fallback can send outdated information, omit legal notices, or use obsolete links.

Example:

- Template v2 only changed colors and spacing, model unchanged: falling back to v1 may be acceptable.
- Template v2 added mandatory payment-term disclosures: falling back to v1 may no longer be appropriate.
- Template v2 uses new fields but an adapter can convert accurately: fallback may be permitted per policy.

When falling back, record **the requested version** and **the actually rendered version**, along with the reason. Do not swap versions silently, as that hampers investigation.

### Does a Plain-Text Fallback Replace a Template Version?

Not completely. Plain text is an alternative presentation format within the same message (`multipart/alternative`), whereas template version is a content/contract version. You can have HTML template v2 and plain-text v2; if HTML rendering fails, a separately prepared plain-text fallback can help basic notifications still go out. However, ensure the fallback conveys complete content and does not omit critical details.

## 15. Spring Boot Example: Rendering by Template Version

The example below uses Thymeleaf and Spring Mail. Two templates are packaged on the classpath:

```text
src/main/resources/templates/mail/order-confirmation/v1.html
src/main/resources/templates/mail/order-confirmation/v2.html
```

Two DTOs:

```java
import java.util.Locale;

public record OrderConfirmationV1(
        String customerName,
        String orderCode,
        String orderUrl,
        Locale locale
) {}

public record OrderConfirmationV2(
        String customerName,
        String orderCode,
        String orderUrl,
        String totalAmountLabel,
        String estimatedDeliveryLabel,
        Locale locale
) {}
```

The renderer selects the template version explicitly:

```java
import org.springframework.stereotype.Component;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Component
public class OrderConfirmationRenderer {

    private final TemplateEngine templateEngine;

    public OrderConfirmationRenderer(TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public String renderV1(OrderConfirmationV1 data) {
        Context context = new Context(data.locale());
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("orderUrl", data.orderUrl());

        return templateEngine.process(
                "mail/order-confirmation/v1",
                context
        );
    }

    public String renderV2(OrderConfirmationV2 data) {
        Context context = new Context(data.locale());
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("orderUrl", data.orderUrl());
        context.setVariable("totalAmountLabel", data.totalAmountLabel());
        context.setVariable(
                "estimatedDeliveryLabel",
                data.estimatedDeliveryLabel()
        );

        return templateEngine.process(
                "mail/order-confirmation/v2",
                context
        );
    }
}
```

The renderer is only responsible for turning a DTO into HTML. It does not send emails and does not query the database itself for missing data.

### Template V1

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Order Confirmed</h1>
  <p>Hello <span th:text="${customerName}">Customer</span>.</p>
  <p>Order code: <strong th:text="${orderCode}">ORD-001</strong></p>
  <a th:href="${orderUrl}">View order</a>
</body>
</html>
```

### Template V2

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Order Confirmed</h1>
  <p>Hello <span th:text="${customerName}">Customer</span>.</p>
  <p>Order code: <strong th:text="${orderCode}">ORD-001</strong></p>

  <p th:if="${totalAmountLabel != null}">
    Total amount: <strong th:text="${totalAmountLabel}">0 ₫</strong>
  </p>
  <p th:if="${estimatedDeliveryLabel != null}">
    Estimated delivery:
    <span th:text="${estimatedDeliveryLabel}">Not available yet</span>
  </p>

  <a th:href="${orderUrl}">View order</a>
</body>
</html>
```

Template V2 supports optional fields. Text values are escaped with `th:text`; URLs must be built by the backend from a trusted domain and validated before entering the model.

### Selecting Version and Sending with `JavaMailSender`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class OrderConfirmationMailService {

    private final JavaMailSender mailSender;
    private final OrderConfirmationRenderer renderer;

    public OrderConfirmationMailService(
            JavaMailSender mailSender,
            OrderConfirmationRenderer renderer
    ) {
        this.mailSender = mailSender;
        this.renderer = renderer;
    }

    public void sendV1(
            String recipient,
            OrderConfirmationV1 data
    ) throws MessagingException {
        String html = renderer.renderV1(data);
        String plain = "Hello " + data.customerName()
                + ". Order " + data.orderCode()
                + " has been confirmed: " + data.orderUrl();

        send(recipient, data.orderCode(), plain, html);
    }

    public void sendV2(
            String recipient,
            OrderConfirmationV2 data
    ) throws MessagingException {
        String html = renderer.renderV2(data);
        String plain = "Hello " + data.customerName()
                + ". Order " + data.orderCode()
                + " has been confirmed: " + data.orderUrl();

        if (data.totalAmountLabel() != null) {
            plain += "\nTotal amount: " + data.totalAmountLabel();
        }
        if (data.estimatedDeliveryLabel() != null) {
            plain += "\nEstimated delivery: " + data.estimatedDeliveryLabel();
        }

        send(recipient, data.orderCode(), plain, html);
    }

    private void send(
            String recipient,
            String orderCode,
            String plain,
            String html
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );
        helper.setFrom("notifications@example.org");
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + orderCode);
        helper.setText(plain, html);
        mailSender.send(message);
    }
}
```

The code illustrates two versioned entry points to clearly show which model pairs with which template. In large applications, you can consolidate logic into a registry/dispatcher instead of creating many similar methods. The sender address in the example must be replaced with an address authorized by the SMTP provider.

**Key point:** `renderV1` does not implicitly accept V2, and `renderV2` does not assume every old event already has the new fields. Each rendering path has an explicit contract.

## 16. Dispatcher Based on Mail Request Metadata

When there are many email types, you can store an independent request:

```java
public record MailTemplateSelection(
        String templateKey,
        int templateVersion,
        int dataSchemaVersion,
        String locale
) {}
```

A dispatcher can pick the model adapter and renderer:

```java
public String renderOrderConfirmation(
        MailTemplateSelection selection,
        Object eventData
) {
    if (!"order-confirmation".equals(selection.templateKey())) {
        throw new IllegalArgumentException("Unknown template key");
    }

    return switch (selection.templateVersion()) {
        case 1 -> {
            OrderConfirmationV1 model =
                    adaptToV1(selection.dataSchemaVersion(), eventData);
            yield renderer.renderV1(model);
        }
        case 2 -> {
            OrderConfirmationV2 model =
                    adaptToV2(selection.dataSchemaVersion(), eventData);
            yield renderer.renderV2(model);
        }
        default -> throw new IllegalArgumentException(
                "Unsupported template version"
        );
    };
}
```

The `adaptToV1(...)` and `adaptToV2(...)` functions are application-implemented conversions; they must verify the actual schema and never invent fake business values. `Object` in the example keeps focus on dispatch; in production code, use concrete event/DTO types or a registry with type-safe mapping.

## 17. Versioning When Sending Asynchronously Through a Queue

An easily overlooked scenario: an email is created from an event, yet a worker sends it later.

```text
Time T1:
Order service emits event V1
       |
       v
Queue holds event for several hours

Time T2:
Application deploys template V2

Time T3:
Mail worker reads event V1
       |
       v
Select template/schema
       |
       +-- V1 unsupported --> render error
       |
       +-- V1 adapter/renderer exists --> can send
```

This occurs when queues back up, workers stop for a long time, retries occur, or dead-letter messages are replayed days later. Therefore:

- Keep parsers/adapters for old event schemas as long as needed.
- Record `schemaVersion` in events instead of guessing from field presence.
- If content at creation time must be preserved, store `templateVersion` with the event.
- Do not delete old templates while queues/retries may still reference them.
- Have clear policies for dead-letter queues and replays.
- On replay, decide whether to use the original version or current version and record the choice.

### Pin Version or Use Current?

**Pinning version at request creation** suits emails with archival, audit, or reproducibility significance. **Resolving version at send time** suits when all outbound emails should use the latest content. Either way, record the actual rendered version for investigation.

An asynchronous request may contain:

```json
{
  "notificationId": "c3d5e1c4-...",
  "eventType": "OrderConfirmed",
  "eventSchemaVersion": 1,
  "templateKey": "order-confirmation",
  "templateVersion": 1,
  "locale": "vi-VN",
  "recipientId": "customer-123"
}
```

The example omits full personal data from the illustrative payload. Systems can store a model snapshot or data reference per policy; weigh consistency, privacy, and retention duration.

## 18. Recording Metadata to Investigate and Reproduce Emails

When users report "the email I received differs from the email on screen," operations teams need to know which template and data generated the message.

Useful metadata:

| Metadata | Purpose |
| --- | --- |
| `notificationId` | Business ID to track a send request |
| `templateKey` | Email type |
| `templateVersion` | Rendered content version |
| `dataSchemaVersion` | Input model schema |
| `locale` | Language/format |
| `renderedAt` | Render timestamp |
| `contentHash` | Hash of template or rendered content for comparison |
| `providerMessageId` | ID provided by sending service if available |
| `deliveryStatus` | Send/delivery status per provider data |

It is not always necessary to store full HTML and models. If storing:

- Define retention periods and access controls.
- Do not record tokens, passwords, or unnecessary sensitive data.
- You can store hashes and versions instead of content copies if sufficient for reconciliation.
- If exact reproduction is required, store a minimal data snapshot and immutable templates; storing only the template name is insufficient if version content can be modified.

Published templates should be treated as immutable. If an old version's content is modified directly, `templateVersion=2` metadata no longer identifies which emails were rendered before vs. after the edit.

## 19. Controlling Rollouts and Rollbacks

When releasing a new template version, you can roll out in stages:

1. **Publish the new version** in an inactive state.
2. Test rendering with models representing supported schemas.
3. Route a small percentage of emails or a group of tenants to the new version.
4. Monitor rendering errors, missing variables, delivery errors, and content feedback.
5. Expand scope if outcomes are satisfactory.
6. If issues arise, switch the `current` alias back to the previous version or stop selecting the new version for new requests.

Template rollback does not automatically restore changed event payloads. If producers stopped emitting the old schema, template v1 may not accept the new model. Therefore, **rollbacks must consider both template version and data schema version**.

### Compatibility Matrix During Rollout

| Producer | Model/Adapter | Template | Expected Outcome |
| --- | --- | --- | --- |
| Producer V1 | Data V1 | Template V1 | Works as before |
| Producer V1 | Adapter V1 → V2 | Template V2 | Works if adapter provides a valid contract |
| Producer V2 | Data V2 | Template V2 | Works with new fields |
| Producer V2 | Data V2 | Template V1 | Works if V1 only needs old fields and adapter preserves semantics |
| Producer V1 | Data V1 no adapter | Template V2 requiring new fields | Risks errors or missing content |

This matrix must be defined in rollout design; never assume every combination is compatible.

## 20. Managing Template Changes in Git

For templates packaged in a repository, store each version as a separate artifact:

```text
templates/mail/order-confirmation/
  v1.html
  v2.html
  v3.html
```

Benefits:

- Reviews clearly show which versions were added or changed.
- Easy to locate the commit that introduced a template.
- Code rollbacks can restore the corresponding template.
- Prevents altering already-published content of old versions.

If using a single `order-confirmation.html` file and overwriting it on every edit, versioning must be managed via commits/releases or another registry. This may suffice for small apps, yet makes re-rendering old emails difficult if the old template is no longer in the running artifact.

### File Naming Conventions

Names should include:

- Stable template key: `order-confirmation`.
- Version: `v1`, `v2`.
- Locale if stored in separate files: `vi-VN`, `en-US`.

Example:

```text
order-confirmation/v2/vi-VN.html
order-confirmation/v2/en-US.html
```

Do not embed version numbers into business event names or email subjects; that is operational metadata, not content recipients need to see.

## 21. Common Mistakes When Versioning Templates

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| New template fails to render old events | Old model lacks required fields | Adapter, intentional fallback, or keep old renderer |
| Email has blank lines/missing info | Optional field lacks display rules | Define fallback or hide section |
| Old template displays new data wrongly | Field kept name yet changed meaning/unit | Use schema version and new fields |
| Queue backlog errors after deploy | Worker receives old payload while only new template/schema remains | Retain old version support or perform controlled queue migration |
| Rollback fails to work | Producer switched schema while template reverted to old version | Maintain compatibility adapter or roll back producer in sync |
| Cannot tell which template an email used | Actual template version was not stored | Record render metadata and provider ID |
| Locales get mixed | Language fallback was not defined | Select locale per policy and record it |
| One tenant receives another tenant's content | Template alias updated per tenant/rollout | Record selection context and resolved version |
| Old email changes when re-rendered | Old template version content was overwritten | Treat published versions as immutable |
| Template renders cleanly yet wrong business output | Field changed semantics without changing contract | Version schema when meaning changes |
| Cannot replay dead-letter events | Old adapter/template was deleted | Define retention for schema and template versions |
| New template selected for incompatible event | Picked `current` at send time without checking schema | Resolver must check template/schema pair |

### Separating Rendering Errors from SMTP Errors

```text
Resolve template version
        |
        +-- version does not exist --> Selection error
        |
        v
Adapt data schema
        |
        +-- missing required data --> Contract error
        |
        v
Render HTML/text
        |
        +-- expression/template error --> Render error
        |
        v
Build MimeMessage
        |
        +-- invalid address/MIME --> Message error
        |
        v
JavaMailSender -> SMTP
        |
        +-- timeout/auth/quota/relay --> Transport error
```

Retries fit only errors likely to resolve themselves, such as transient network errors. Nonexistent templates or models missing required fields require fixing contracts/deployments; SMTP retries cannot fix them.

## 22. Key Principles

1. **Version templates and data separately.** Link them via a contract instead of merging into one single number.
2. **Keep contracts clear.** Field names, types, meaning, nullability, locale, and format must be documented.
3. **Prefer additive changes.** Add optional fields and fallbacks before making them required.
4. **Do not change semantics in place.** If a field's meaning changes, release a new schema or a new field.
5. **Keep old versions long enough.** Queues, retries, dead-letter queues, and send histories may still reference them.
6. **Use adapters for migration.** Transform data in a strongly typed layer rather than hiding logic in templates.
7. **Pin or resolve versions per policy.** For each email type, decide whether the version is chosen at request creation or at send time.
8. **Published templates should be immutable.** To edit, release a new version.
9. **Record actual version metadata.** Store template key/version, schema version, locale, and notification ID for investigation.
10. **Roll back both sides.** Templates and producers/models must stay compatible with each other when reverting to an old version.

## 23. Self-Practice Scenarios

### Scenario A: Adding a Total Amount Field to an Email

Template v1 uses only `customerName` and `orderCode`. Template v2 adds `totalAmountLabel`, yet the queue still holds v1 events.

**How to handle:** keep v1 schema support, use an adapter to convert v1 data to the v2 model with `totalAmountLabel` set to null, and let template v2 hide the total section when absent. If the total amount is business-mandatory content, never fabricate a value; query authoritative data or continue using the appropriate v1 flow.

### Scenario B: Changing `deliveryDate` from Estimated Date to Committed Date

The field name stays the same, yet the meaning has changed.

**How to handle:** this is a semantic breaking change. Use a new field such as `committedDeliveryDate` or a new schema; do not continue passing committed dates into the old field while old templates treat it as an estimated date.

### Scenario C: Template v3 Only Changes Colors and Fonts

The model has not changed.

**How to handle:** you can bump the template version or patch per project conventions; there is no need to bump the data schema version if the contract has not changed.

### Scenario D: Event v1 Is Replayed After Three Months

Template v1 was deleted after deploying v2.

**How to handle:** establish retention policies for templates and adapters. If replays must reproduce original content, keep v1 immutable. If using the current template is allowed, migrate the schema in a controlled manner and record the actual rendered version.

### Scenario E: A Tenant Trials a New Template Before Other Tenants

**How to handle:** the resolver can select versions by tenant/rollout cohort, while recording selection metadata. Never let template keys or versions come directly from user input; the registry only allows published, approved versions.

## 24. Conclusion

Versioning email templates is not just renaming files from `v1.html` to `v2.html`. What must be managed is **compatibility between template content, data contracts, pending events, and renderer logic**. The template version describes presentation; the data schema version describes the data the template is permitted to receive. Both can change independently, yet must be connected by an explicit contract.

In Spring Framework Mail, use dedicated DTOs for mail models, adapters to convert old/new schemas, immutable template versions, and resolvers that select versions by policy. For compatible changes, prefer adding optional fields and clear fallbacks; for breaking changes, release new versions and roll out in phases. Storing actual version metadata makes investigation, replay, and rollback accurate. When producers, models, and templates are upgraded deliberately, applications can evolve email content while still handling old data and queued events.
