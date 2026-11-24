# Template Registry and Content Versioning

In a production **Spring Framework Mail** system, an email is not merely a few **subject**, **text**, and **HTML** strings hardcoded in Java. A single product may send verification emails, receipts, security alerts, invoices, appointment updates, and customer care campaigns in multiple languages, for multiple tenants, across multiple providers. Content must evolve over time while preserving control, reconciliation, and reproducibility of what was sent.

A **template registry** is a repository for registering email templates along with metadata, data contracts, versions, approval states, and selection rules. The application does not hardcode full HTML inside business services; it requests a template by **template key**, **locale**, **tenant/brand**, and a **specific version**. The registry returns a matching registered content revision, which the template engine renders into Subject, plain text, and HTML for delivery via **JavaMailSender**.

**Content versioning** is critical: if you change the wording of the "Order confirmed" email today, which template should a notification enqueued yesterday yet retried tomorrow use? Without deciding upfront, the same logical notification can produce different content across retries, causing discrepancies in audits, pricing, and legal terms.

This guide covers designing a **production-grade** template registry and version management: template identity and contracts; draft–approve–publish workflows; immutable revisions; selection by locale/tenant; variable validation; Spring Mail and Thymeleaf integration; outbox version pinning; caching; rollout/rollback; security; testing; monitoring; and runbooks.

> **Core principle:** Once a template revision is **published** and has been used, it must be treated as **immutable**. "Rollback" means switching the active pointer to a previously approved revision—**never overwriting historical content**. For emails requiring consistency, the notification/outbox must explicitly persist the pinned revision and input data.

## 1. Problems with hardcoding templates in code

A simple implementation:

~~~java
String subject = "Order confirmation " + orderId;
String html = "<h1>Hello " + customerName + "</h1>";
mailSender.send(...);
~~~

This may work for demos, yet in production it has many limitations:

- Every wording change requires editing code, running tests, and redeploying.
- Email copy is tangled into business logic, making content/legal reviews hard.
- You cannot tell which content version was sent if templates are edited in place.
- Hard to support multiple languages, tenants, brands, and email types.
- No input variable schema: missing variables may only be discovered at send time.
- No previews, approver history, changelogs, or rapid rollbacks.
- Impossible to roll out gradually by environment, tenant, or percentage.
- Retries may unintentionally re-render with newer content.

A registry solves content management and selection. It **does not replace** the mail-sending system, transactional outbox, MIME helper, or send-authorization checks.

## 2. Components in the design

~~~text
Business Application
       |
       v
Notification Service
       |
       +--> Delivery policy (consent/suppression)
       |
       +--> Template Resolution
       |       |
       |       +--> Template Registry
       |       +--> Active Revision Mapping
       |       +--> Locale/Tenant Fallback Policy
       |       '--> Variables Contract
       |
       +--> Template Renderer
       |       |
       |       +--> Subject
       |       +--> text/plain
       |       '--> text/html
       |
       '--> Mail Composer
               |
               +--> MIME / attachments / CID
               |
               v
           JavaMailSender
               |
               v
           SMTP Provider
~~~

When using an outbox:

~~~text
Business Transaction
        |
        v
Notification Outbox + pinned template revision
        |
        v
Worker loads immutable template revision
        |
        v
Render + Compose MIME
        |
        v
SMTP submission
~~~

Responsibilities should be separated:

| Component | Responsibility | Should not do |
| --- | --- | --- |
| **Business service** | Choose notification type and business data | Hold long HTML/email layouts |
| **Template registry** | Store templates/versions/metadata/activations | Send SMTP directly |
| **Resolver** | Pick the right revision per policy | Modify published bodies |
| **Variable validator** | Enforce model contract | Silently ignore critical variables |
| **Renderer** | Render text/HTML/subject | Decide mail-sending permissions |
| **MIME composer** | Build MimeMessage and attachments | Alter approved content |
| **Mail sender** | Submit email via SMTP | Treat SMTP accepted as Inbox delivered |
| **Outbox worker** | Retry/deliver and persist outcomes | Pick arbitrary new content on each retry |

## 3. From template key to revision

First, distinguish the **logical template** from a **concrete content revision**.

Example:

~~~text
Template key:
  ORDER_CONFIRMED

Locale:
  vi-VN

Brand:
  retail-main

Variant:
  default

Published revision:
  17

Content hash:
  sha256:...
~~~

A tuple of **template key + locale + brand + variant** can have many revisions. Each revision is an immutable snapshot containing subject, body, metadata, and model schema (or an immutable reference to the schema).

### Identifier types

| Field | Example | Meaning |
| --- | --- | --- |
| **templateKey** | ORDER_CONFIRMED | Stable logical email type |
| **locale** | vi-VN | Content language/region |
| **brand/tenant scope** | retail-main | Brand identity or tenant-scoped content |
| **variant** | default, short | Intentionally designed variation |
| **revisionId** | UUID | Unique identifier of one content snapshot |
| **versionNumber** | 17 | Human-readable version number within a scope |
| **active pointer** | revision 17 | Revision selected for new requests |
| **contentHash** | SHA-256 | Digest of canonical content bytes |
| **schemaVersion** | 3 | Data variable contract version |

**revisionId** is not **notificationId**. One revision can serve millions of notifications; each notification should pin one revision and a meaningful model snapshot when reproducibility is required.

### Template key is not a filename

Do not use a filename like **order-confirmed-17.html** as the sole business key. Filenames are storage details; the registry may use a database, object storage, or artifact bundles. **Template key** must be a logical identifier independent of physical storage.

## 4. What does the template registry store?

A production registry holds more than HTML snippets. A record may include:

~~~text
Template Definition
  - templateKey: PASSWORD_RESET
  - ownerTeam: identity-platform
  - purpose: SECURITY
  - allowedChannels: EMAIL
  - defaultLocale: vi-VN
  - complianceClassification: TRANSACTIONAL

Template Revision
  - revisionId
  - locale / brand / variant
  - subjectTemplate
  - plainTextTemplate
  - htmlTemplate
  - variableSchemaVersion
  - assetManifest
  - contentHash
  - lifecycleStatus
  - createdBy / reviewedBy / approvedAt
  - createdAt / publishedAt

Template Activation
  - environment / tenant scope
  - templateKey / locale / brand / variant
  - activeRevisionId
  - effectiveFrom
  - activatedBy / reason
~~~

### Separating content from transport configuration

The registry should define **content, layout, variables, and asset sources**. SMTP credentials, provider access tokens, and retry policies do not belong in template bodies. From/Reply-To policies can be referenced via a **verified sender profile** managed by the mail service rather than letting template authors enter arbitrary addresses.

### A template can have multiple parts

| Part | Purpose |
| --- | --- |
| **Subject** | Email subject, often parameterized |
| **Preheader** | Preview line, embeddable in HTML |
| **Plain text** | Readable fallback for non-HTML clients |
| **HTML** | Formatted body |
| **CTA label/link** | Action text/URL generated safely |
| **Inline asset manifest** | Logos and icons pinned to the revision |
| **Attachment policy** | Allowed attachment types; bytes need not live in registry |
| **Variable schema** | Required fields, types, formatters, defaults |
| **Locale metadata** | Language and formatting rules |

A complete email may share common partials. If layouts/headers/footers are separate templates, **pin dependency versions** or create snapshot bundles; otherwise, layout changes will silently alter how old revisions render.

## 5. Immutable revisions and mutable active pointers

This is the single most important boundary.

~~~text
ORDER_CONFIRMED / vi-VN
   |
   +-- Revision 15 (PUBLISHED, immutable)
   +-- Revision 16 (PUBLISHED, immutable)
   +-- Revision 17 (PUBLISHED, immutable)
   '-- Revision 18 (DRAFT, editable before publish)

Active pointer ----> Revision 17
~~~

On rollback:

~~~text
Before rollback: active -> Revision 17
After rollback:  active -> Revision 16

Revision 16/17 bytes do not change.
~~~

### Why never edit a published version in place?

Suppose a notification was created with revision 17. If staff edit revision 17's HTML without creating a new revision:

- Audit events can no longer reproduce what was sent.
- Retries of the same notification may change wording.
- Caches may serve old bytes while the database holds new ones.
- Per-version performance comparisons yield corrupted metrics.
- Past approvals no longer cover the modified content.

**Published revisions are immutable**; edits must create revision 18. The same rule applies to inline assets and dependent templates.

### Drafts are editable, yet need history tracking

A draft can be updated many times; when workflow requires review, snapshot the exact version submitted for review. Use a **draft generation** or create an immutable revision upon submission for review so reviewers are not inspecting a "moving target."

### Same version label does not guarantee identical content

Human-readable version strings like **v1.2** can collide due to manual entry. Rely on `revisionId`/unique constraints and `contentHash`; never use `"v1.2"` alone as an immutability key.

## 6. Lifecycle of a template

An illustrative state machine:

~~~text
        Create
          |
          v
        DRAFT
          |
          v
      VALIDATING
        |     |
   Failed     Passed
        |     |
        v     v
       DRAFT  IN_REVIEW
                  |
              +---+---+
              |       |
           Rejected  Approved
              |       |
              v       v
             DRAFT   APPROVED
                       |
                       v
                   PUBLISHED
                       |
                 +-----+------+
                 |            |
                 v            v
             DEPRECATED    REVOKED
~~~

This is an application model, not a built-in Spring Mail state machine.

### Meaning of each state

| State | Meaning | Usable for new production sends? |
| --- | --- | --- |
| **DRAFT** | Content being authored | No |
| **VALIDATING** | Checking schema, syntax, previews/tests | No |
| **IN_REVIEW** | Under review | No |
| **APPROVED** | Snapshot approved | Not yet, until activated |
| **PUBLISHED** | Eligible for activation per policy | Yes, when active |
| **DEPRECATED** | No longer selected for new requests | May serve pinned retries per policy |
| **REVOKED** | Content banned from use, even on retries if policy requires | No; requires emergency handling |

**PUBLISHED** and **ACTIVE** are not synonymous. A published revision might not be selected by any active pointer, or might only be active in staging or for selected tenants.

### Never delete historical revisions to "retire" them

If a revision has ever sent emails, its metadata and hash have audit value. You can stop new sends by updating active pointers or applying a revocation policy. Physical deletion/redaction must follow retention and privacy rules, yet **do not delete revisions by default** upon retirement.

## 7. Author, reviewer, and operator workflow

A practical workflow:

~~~text
Content Author
    |
    v
Create draft revision
    |
    v
Edit subject / plain / HTML / translations
    |
    v
Run validation + render preview
    |
    v
Submit immutable review snapshot
    |
    v
Reviewer approves exact revision hash
    |
    v
Release operator publishes
    |
    v
Activate for chosen environment/tenants
    |
    v
Monitor delivery / bounce / user feedback
    |
    v
Keep or rollback active pointer
~~~

### Separation of duties

- **Author:** creates/edits drafts.
- **Reviewer:** verifies content and schema; cannot approve edits made after review.
- **Publisher:** publishes approved revisions.
- **Operator:** activates, disables, or rolls back versions per policy.
- **Auditor:** inspects approval history, hashes, and active scopes without necessarily having edit rights.

For security, legal, or financial emails, independent reviewers, accessibility checks, and compliance reviews may be required. Four-eyes rules must match organizational governance; Spring Framework Mail does not enforce these roles itself.

### Approvals must bind to the content hash

If a reviewer approves HTML A while the author edits the draft to HTML B before publishing, the approval is invalid. At approval time, record **revisionId + contentHash + variableSchemaVersion + assetBundleHash** so publishing knows the exact approved artifact.

## 8. Template manifests and data contracts

A template must declare what data it expects, what types they have, and how missing values are handled.

Example manifest (application-defined syntax):

~~~yaml
templateKey: ORDER_CONFIRMED
locale: vi-VN
brand: retail-main
variant: default
version: 17
purpose: TRANSACTIONAL
renderer: THYMELEAF
requiredVariables:
  - name: customerDisplayName
    type: STRING
    maxLength: 120
  - name: orderCode
    type: STRING
    maxLength: 64
  - name: total
    type: MONEY
    currencyField: currency
  - name: orderLink
    type: VERIFIED_URL
optionalVariables:
  - name: supportContact
    type: STRING
    default: "Support Team"
assets:
  logo: "sha256:immutable-logo-blob-hash"
senderProfile: "retail-transactional"
~~~

**MONEY**, **VERIFIED_URL**, and this entire manifest schema are business conventions, not Thymeleaf types. Production needs a formal validator with explicit schemas, format constraints, and concrete URL/sender policies.

### Benefits of manifests

- Catch missing required variables before SMTP submission.
- Prevent passing the wrong type for URLs or currency amounts.
- Verify template compatibility with event/model versions.
- Let editors and previews auto-generate sample variable input forms.
- Enforce length limits and display fallbacks.
- Generate test fixtures across locales/tenants.
- Record exactly which content/variables were approved for a given revision.

### Never default every null value to an empty string

If **orderCode** is missing and the renderer sends Subject "Order confirmation ", the email loses business validity. Required variables should **fail closed** with an explicit error category; only optional variables may use declared, verified defaults.

## 9. Variable schemas: types, defaults, and formatters

In a sound registry, model variables are not just an arbitrary **`Map<String, Object>`**.

| Data type | Example | Validation/formatting |
| --- | --- | --- |
| **STRING** | customerDisplayName | Non-null, max length, Unicode |
| **INTEGER** | quantity | Valid numeric range |
| **DECIMAL** | totalAmount | Precision, scale, currency unit |
| **MONEY** | total + currency | Locale-specific display; never use double for accounting values |
| **DATE / INSTANT** | appointmentAt | Timezone, locale date pattern |
| **BOOLEAN** | showSupportLink | Conditional rendering |
| **ENUM** | deliveryStatus | Allowlisted values |
| **URL** | orderLink | HTTPS, trusted host, valid path/query |
| **LIST** | lineItems | Element count cap, per-item structure |
| **OBJECT** | shippingAddress | Nested field schema, PII handling |

### Money and timezones must be explicit

Never simply call **`amount.toString()`** for multilingual emails assuming users will understand. You need currency, locale, rounding policy, and source data. Similarly, convert `Instant`s to the recipient's or business's timezone rather than accidentally picking up a container's default timezone.

Example formatting helper:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public final class MoneyFormatter {

    public String format(
            BigDecimal amount,
            Currency currency,
            Locale locale
    ) {
        if (amount == null || currency == null || locale == null) {
            throw new IllegalArgumentException("Money data missing");
        }

        NumberFormat format = NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(currency);
        return format.format(amount);
    }
}
~~~

This snippet illustrates display formatting; business rounding rules and min/max fraction digits must still be specified separately. Never parse formatted strings back into monetary calculations.

### Allow defaults only for genuinely optional variables

~~~text
supportContact missing
  -> default "Support Team" per revision/locale

orderCode missing
  -> RENDER_VALIDATION_FAILED
  -> Do not send an order confirmation email without an order code
~~~

Defaults are also **part of versioned content**. If a default string changes, the revision should change; if defaults live in global config, historical content can no longer be reproduced accurately.

### Avoid rendering "live" mutable data arbitrarily

Templates should not query databases/APIs directly during rendering:

~~~text
Rendering ORDER_CONFIRMED
  -> calls orderService.getLatestPrice()
  -> calls currencyService.getTodayRate()
  -> calls userService.getCurrentName()
~~~

When retried days later, prices or discounts may have changed, making the email inaccurate for that notification. Instead, have the **business service create a model snapshot** when deciding to send, including finalized amounts and policy-issued links.

## 10. Selecting templates by locale, tenant, brand, and variant

A resolver might accept:

~~~java
public record TemplateSelector(
        String templateKey,
        String tenantId,
        String brand,
        String locale,
        String variant,
        String environment
) {
}
~~~

These fields serve distinct roles:

- **templateKey**: logical email to send.
- **tenantId**: owner/configuration scope of the content.
- **brand**: visual/brand identity.
- **locale**: language/region.
- **variant**: intentionally selected variation.
- **environment**: dev, staging, production—never let staging point to production accidentally.

### Rule-based locale fallback, never guesswork

Example for a recipient requesting **vi-VN**:

~~~text
Requested: vi-VN / brand-A / default
    |
    +-- 1. Exact locale + brand
    |
    +-- 2. Parent language vi + brand (if approved)
    |
    +-- 3. Default locale + brand
    |
    '-- 4. No eligible revision -> resolution failure
~~~

Some content must **never fall back**: region-specific legal terms, regulated country notices, or security templates requiring dedicated translation and approval. Define fallback policies per template/purpose rather than picking "any available language."

### Tenant isolation matters more than convenience

If Tenant A has no custom template, falling back to an approved **global template** can be fine. Never fall back to Tenant B's template, leaking private branding, URLs, or copy.

~~~text
tenant-A exact revision
    -> tenant-A generic brand
    -> approved global revision
    -> ERROR

Never -> tenant-B revision
~~~

### Variants and A/B testing

**Variants** can test subjects or layouts. For a single notification, **pick the variant once** via stable experiment assignment and persist it in the outbox. If a retry flips from variant A to B, A/B metrics skew and content becomes inconsistent.

Only run experiments when email purpose and policies allow. For security or legal emails, content changes need stricter approval than marketing experiments.

## 11. ResolvedTemplate is a snapshot, not a promise to look up later

The resolver should return a reproducible revision:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record ResolvedMailTemplate(
        UUID revisionId,
        String templateKey,
        String locale,
        String brand,
        String variant,
        int contentVersion,
        int schemaVersion,
        String subjectTemplate,
        String plainTextTemplate,
        String htmlTemplate,
        String contentHash,
        Instant publishedAt,
        Map<String, String> assetReferences
) {
}
~~~

### Immutable means never returning a mutable draft reference

Do not return a **TemplateDraft** that someone else could edit during rendering. Fetch an immutable snapshot of a published revision so subject/plain/HTML/assets/schema all belong to one consistent revision.

### The active pointer can change between two queries

~~~text
T1: Query subject -> active revision 17
T2: Operator activates revision 18
T3: Query HTML -> active revision 18
~~~

An email with v17 subject and v18 HTML is broken. The resolver must **pick one revisionId first**, then read all content using that exact revisionId.

### Revision ID should appear in audits

~~~text
notification_id: 8a...
template_key: ORDER_CONFIRMED
template_revision_id: 6f...
template_hash: sha256:...
locale: vi-VN
variant: default
render_model_hash: sha256:...
sent_at: ...
smtp_submission_outcome: ACCEPTED
~~~

Do not dump full model snapshots into text logs since they may contain personal data. Hashes help verify canonicalized bytes; to re-render, you still need retained model snapshots and permitted assets.

## 12. Data model with Java records and interfaces

A registry API can be defined as:

~~~java
import java.util.UUID;

public interface TemplateRegistry {

    ResolvedMailTemplate resolveActive(
            TemplateSelector selector
    );

    ResolvedMailTemplate getRevision(UUID revisionId);

    TemplateManifest getManifest(UUID revisionId);
}

public record TemplateManifest(
        UUID revisionId,
        int schemaVersion,
        java.util.List<VariableDefinition> variables,
        String senderProfile
) {
}

public record VariableDefinition(
        String name,
        VariableType type,
        boolean required,
        int maxLength,
        String formatter
) {
}

public enum VariableType {
    STRING, DECIMAL, MONEY, DATE, URL, BOOLEAN, LIST, OBJECT
}
~~~

These are **application-defined** contracts, not built-in Spring Mail interfaces.

### Two APIs with distinct meanings

- **resolveActive(selector)** is used when creating a new unpinned notification.
- **getRevision(revisionId)** is used when retrying or investigating a pinned notification.

Never call `resolveActive` again during retries when policy requires preserving content.

### When no valid revision exists

The resolver should return categorized errors:

~~~text
TEMPLATE_NOT_FOUND
TEMPLATE_NOT_ACTIVE
LOCALE_NOT_ALLOWED
TENANT_SCOPE_VIOLATION
TEMPLATE_REVOKED
SCHEMA_NOT_COMPATIBLE
ASSET_BUNDLE_MISSING
~~~

Never silently swap to another `templateKey` or send a blank email. Missing production templates require alerts and policy action, not infinite SMTP retries.

## 13. Storage design in PostgreSQL

A minimal design uses three table groups:

1. **mail_template_definition** — logical identity and owner.
2. **mail_template_revision** — versioned content and metadata, immutable once published.
3. **mail_template_activation** — active revision mapping per scope.

PostgreSQL example:

~~~sql
CREATE TABLE mail_template_definition (
    template_key VARCHAR(120) PRIMARY KEY,
    owner_team VARCHAR(120) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    default_locale VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mail_template_revision (
    revision_id UUID PRIMARY KEY,
    template_key VARCHAR(120) NOT NULL
        REFERENCES mail_template_definition(template_key),
    tenant_scope VARCHAR(120) NOT NULL,
    brand VARCHAR(120) NOT NULL,
    locale VARCHAR(40) NOT NULL,
    variant VARCHAR(80) NOT NULL,
    version_number INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    subject_template TEXT NOT NULL,
    plain_text_template TEXT NOT NULL,
    html_template TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    asset_bundle_hash VARCHAR(128),
    content_hash VARCHAR(128) NOT NULL,
    status VARCHAR(40) NOT NULL,
    created_by VARCHAR(120) NOT NULL,
    approved_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_template_revision_scope
        UNIQUE (
            template_key, tenant_scope, brand,
            locale, variant, version_number
        )
);

CREATE TABLE mail_template_activation (
    environment VARCHAR(40) NOT NULL,
    tenant_scope VARCHAR(120) NOT NULL,
    brand VARCHAR(120) NOT NULL,
    locale VARCHAR(40) NOT NULL,
    variant VARCHAR(80) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    active_revision_id UUID NOT NULL
        REFERENCES mail_template_revision(revision_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_by VARCHAR(120) NOT NULL,
    PRIMARY KEY (
        environment, tenant_scope, brand,
        locale, variant, template_key
    )
);
~~~

This is an illustrative schema, not tables created by Spring Mail. The **FK `active_revision_id`** proves the revision exists, yet **is insufficient** to prove it matches the same template key/locale/tenant and `PUBLISHED` status. Add transaction/service validation or composite-key foreign references matching the scope.

### Block UPDATEs on published revisions

Application-level status checks are insufficient if multiple SQL paths exist. You can:

- Grant only `INSERT` for drafts/new revisions and restrict `UPDATE` on published rows.
- Use triggers or stored procedures blocking edits to immutable content.
- Gate special maintenance behind audited migrations/approvals.
- Protect stored assets against overwriting existing object keys.

Updating audit metadata or switching status to `DEPRECATED` may still be allowed by separate design; **body, manifest, and content hash** of published revisions must remain immutable.

### Never use version number ordering as the active policy

The highest version is not necessarily what production uses. Revision 19 might be `DRAFT`, revision 18 `PUBLISHED` yet active only for a pilot tenant, while revision 17 is broadly active. Select via the activation table, never **`MAX(version_number)`**.

## 14. Atomic activation and rollback

When activating revision 18, the operation should:

1. Verify the revision is approved/published.
2. Verify matching allowed `templateKey`/tenant/brand/locale/variant.
3. Check the current active pointer or version stamp.
4. Swap the pointer in a short transaction.
5. Record before/after audit events.
6. Emit a cache invalidation notice if caching is used.

### Preventing races between two operators

~~~text
Operator A reads active=17, wants activate=18.
Operator B reads active=17, wants rollback=16.
Without conditional UPDATE, last writer wins.
~~~

Use compare-and-set:

~~~sql
UPDATE mail_template_activation
SET
    active_revision_id = :new_revision_id,
    activated_at = CURRENT_TIMESTAMP,
    activated_by = :operator
WHERE environment = :environment
  AND tenant_scope = :tenant_scope
  AND brand = :brand
  AND locale = :locale
  AND variant = :variant
  AND template_key = :template_key
  AND active_revision_id = :expected_old_revision_id;
~~~

If affected rows = 0, the active pointer already changed. The API should return a conflict, reload state, and ask the operator to retry per policy—never silently overwrite without the operator knowing.

### Never perform external I/O inside the activation transaction

Do not hold the database transaction open while notifying all workers or calling a render service. Commit the pointer first, then emit cache invalidation events; consumers must handle lost/stale invalidations via TTLs or versioning.

### Rollback never erases history

~~~text
14:00 active=17
14:30 active=18
14:45 rollback active=17

Activation audit:
  [14:30] 17 -> 18, reason campaign update
  [14:45] 18 -> 17, reason render regression
~~~

If events were already enqueued with revision 18 between 14:30 and 14:45, do not silently flip them to 17 merely because of a rollback. Define explicit policies for pending jobs and emergency revocations.

## 15. Rendering with Thymeleaf in Spring

**Thymeleaf** is a popular template engine for generating HTML/text emails. Spring Framework Mail / `JavaMailSender` **does not render Thymeleaf automatically**; the application configures the template engine and passes rendered content to the MIME helper.

Example HTML for a revision:

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="en">
<body>
  <h1 th:text="|Hello ${customerDisplayName}|">Hello</h1>
  <p>Order <strong th:text="${orderCode}">ORD-000</strong>
     has been confirmed.</p>
  <p>Total: <span th:text="${formattedTotal}">0 ₫</span></p>
  <a th:href="${orderLink}">View details</a>
</body>
</html>
~~~

Example text template:

~~~text
Hello [[${customerDisplayName}]],

Order [[${orderCode}]] has been confirmed.
Total: [[${formattedTotal}]]
Details: [[${orderLink}]]
~~~

Subject template (Thymeleaf TEXT mode):

~~~text
Order confirmation [[${orderCode}]]
~~~

### Never pick the wrong resolver for a registry

**ClassLoaderTemplateResolver** loads templates from the classpath; it knows nothing about revision bodies stored in a database. When the registry supplies content directly, configure **StringTemplateResolver**, treating the source string as template content rather than a filename. This choice requires strict control over who can author templates, because server-side template engines expose expression power beyond simple placeholder replacement.

### Example renderer processing an immutable revision

~~~java
import java.util.Locale;
import java.util.Map;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.StringTemplateResolver;

public final class ThymeleafMailContentRenderer {

    private final TemplateEngine htmlEngine;
    private final TemplateEngine textEngine;

    public ThymeleafMailContentRenderer() {
        this.htmlEngine = engine(TemplateMode.HTML);
        this.textEngine = engine(TemplateMode.TEXT);
    }

    private static TemplateEngine engine(TemplateMode mode) {
        StringTemplateResolver resolver = new StringTemplateResolver();
        resolver.setTemplateMode(mode);
        resolver.setCacheable(false);

        TemplateEngine engine = new TemplateEngine();
        engine.setTemplateResolver(resolver);
        return engine;
    }

    public RenderedMailContent render(
            ResolvedMailTemplate revision,
            Map<String, Object> checkedModel
    ) {
        Locale locale = Locale.forLanguageTag(revision.locale());
        Context context = new Context(locale, checkedModel);

        String subject = textEngine.process(
                revision.subjectTemplate(), context
        );
        String plainText = textEngine.process(
                revision.plainTextTemplate(), context
        );
        String html = htmlEngine.process(
                revision.htmlTemplate(), context
        );

        if (subject.isBlank()
                || subject.contains("\r")
                || subject.contains("\n")) {
            throw new IllegalArgumentException(
                    "Rendered subject is invalid"
            );
        }

        return new RenderedMailContent(
                subject, plainText, html,
                revision.revisionId(),
                revision.contentHash()
        );
    }
}

public record RenderedMailContent(
        String subject,
        String plainText,
        String html,
        java.util.UUID revisionId,
        String contentHash
) {
}
~~~

This example intentionally disables caching on **StringTemplateResolver** to avoid mis-caching by raw template source text. Production can cache compiled templates keyed by **revisionId + contentHash** if the engine/resolver supports it safely, never by a mutable name like **ORDER_CONFIRMED** across changing bytes without invalidation. The renderer assumes **checkedModel** is already validated, templates come from approved sources, and dependencies/expressions are restricted by policy.

### Render all three parts from one context

Subject, plain, and HTML must share one **model snapshot** and one **revisionId**, avoiding:

~~~text
Subject: revision 18, order total = 250
Plain:   revision 17, order total = 200
HTML:    revision 18, order total = 220
~~~

The renderer produces an immutable **RenderedMailContent** object and can be tested without opening an SMTP connection.

## 16. Template content must defend against injection

Suppose a customer's name is:

~~~text
<img src=x onerror=alert(1)>
~~~

If concatenated directly into unescaped HTML, user-controlled markup enters the email. In Thymeleaf, **`th:text`** applies context-appropriate escaping; **`th:utext`** inserts unescaped HTML and is suitable only for content approved/sanitized by policy.

### Risks by context

| Location | Risk | Mitigation |
| --- | --- | --- |
| **HTML text** | HTML injection | Context-aware escaping |
| **HTML attribute** | Data breaks out of attributes | Attribute-aware rendering, validation |
| **URL** | Dangerous scheme or spoofed host | Allowlist HTTPS/hosts, URL builder |
| **Subject/Header** | CRLF/header injection | Reject CR/LF, enforce length limits |
| **Plain text** | Misleading wording / data leakage | Schema and content review |
| **CSS/inline styles** | Tracking / remote assets, client quirks | Asset policy, previews |
| **Dynamic template syntax** | Server-side template injection | Never pass user data as template source |

### Never compile user input as a template

Wrong:

~~~java
String templateSource = request.getParameter("html");
// Then render as a trusted server-side template.
~~~

If content authors can create templates in the registry, they wield power over rendering execution. Editors require RBAC, template feature allowlists, and sandboxing/engine restrictions if authors are not fully trusted. Only feed reviewed revisions into **StringTemplateResolver**; never assume a server-side engine is a safe sandbox by default.

### URLs should be constructed by the application

If an email contains a verification link:

~~~text
https://app.example.test/verify?token=...
~~~

Do not let templates accept an arbitrary `baseUrl` from users. The business service should assemble URLs from trusted configuration, properly encode paths/queries, and enforce TTLs and one-time tokens per policy. Templates only display verified URLs.

### Previews must also be safe

Admin HTML preview pages need appropriate sandboxing/CSP, avoiding script execution or automatic external resource fetches simply because a template lives in the registry. Email clients behave inconsistently, yet that never justifies granting arbitrary HTML admin-page privileges.

## 17. Building MimeMessage from rendered content

Once the resolver and renderer finish, **JavaMailSender** receives the final content. The template registry does not need to know SMTP passwords, transport sockets, or retries.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringMailComposer {

    private final JavaMailSender sender;

    public SpringMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(
            String verifiedFrom,
            String validatedRecipient,
            RenderedMailContent content
    ) throws Exception {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom(verifiedFrom);
        helper.setTo(validatedRecipient);
        helper.setSubject(content.subject());
        helper.setText(content.plainText(), content.html());

        sender.send(message);
    }
}
~~~

**MULTIPART_MODE_MIXED_RELATED** is usually appropriate when mixing body alternatives, inline resources, and attachments. Without attachments or inline images, a simpler MIME mode may be used depending on requirements and mail-client compatibility.

### MIME helper does not read the template registry

**MimeMessageHelper** sets From/To/Subject, plain/HTML, CID images, and attachments; it does not choose content versions for the application. All revision/locale/schema decisions must happen beforehand.

### Attachments should not depend on draft assets

If revision 17 references logo v3, retrying a notification on revision 17 a month later must still retrieve logo v3 bytes (within retention bounds). Never routinely call **`assetService.getLatestLogo()`** and mutate an old version's appearance.

### SMTP accepted is not delivered

**JavaMailSender.send(...)** succeeding means transport submission completed under its contract—not that the recipient saw it in their Inbox. The registry/versioning handles **content consistency**; delivered, bounced, complained, and unsubscribed states must be tracked separately via mail providers where available.

## 18. When to pin versions: at enqueue or at send?

Two strategies carry different meanings:

### Strategy A — Pin when creating the notification

~~~text
T0 Business event occurs
   -> resolve active template revision 17
   -> snapshot model
   -> insert outbox(notification, revision 17, model)

T1 Operator activates revision 18

T2 Worker sends old notification
   -> getRevision(17)
   -> render model snapshot
   -> send
~~~

**Pros:** every notification has consistent content; retries never switch templates; easy auditing. **Cons:** if delayed a long time, may send buggy or outdated v17 content, requiring revocation/expiry controls.

### Strategy B — Resolve at first send time

~~~text
T0 Business event -> save notification intent + model
T1 Operator activates revision 18
T2 Worker first attempt
   -> resolve active revision 18
   -> persist pin 18
   -> send
T3 Retry same notification
   -> use pinned 18
~~~

**Pros:** picks the newest approved copy when the worker starts sending. **Cons:** notifications created simultaneously yet processed at different times may use different revisions; policy must explicitly accept and document this.

### Both must pin before external side effects

Whether choosing A or B, once an attempt is submitted to SMTP, related retries/reconciliations must retain the matching snapshot. If T2 sent v18 and T3 resolves active v19 after a timeout, the recipient may get two emails with differing copy.

### Different email types often pick different policies

| Use case | Pinning suggestion | Reason |
| --- | --- | --- |
| **Receipt / invoice** | Pin when business commits | Amounts and wording must be reproducible |
| **Password reset / OTP** | Pin at creation/early, short deadline | Avoid changing links/codes across retries |
| **Security alert** | Pin approved safe version | High-stakes copy needing auditability |
| **Scheduled marketing** | Per campaign snapshot/activation policy | Campaigns have dedicated schedules and approvals |
| **Product updates** | Can resolve at dispatch before attempt | Newer approved copy is acceptable |

No single policy fits every product, yet **the rule must be defined and persisted**, never left to accidental worker execution timing.

## 19. Render models must also be versioned or snapshotted

Pinning revision 17 while each retry still calls:

~~~text
orderService.findCurrentOrder(orderId)
~~~

can still alter content. For instance, an order might be refunded after the initial confirmation email was enqueued.

### What needs to be frozen

A snapshot might contain:

~~~json
{
  "modelSchemaVersion": 3,
  "customerDisplayName": "Customer Name",
  "orderCode": "ORD-1528",
  "totalAmount": "250000.00",
  "currency": "VND",
  "orderLinkId": "order-view-7b8"
}
~~~

For **sensitive links**, you do not always have to store raw tokens in long-lived model snapshots. You can store a reference and explicitly define token issuance timing, TTL, and retry semantics, or render the mail snapshot once and store protected MIME/subject/content under appropriate retention. Either option must balance security against reproducibility.

### Model snapshots must carry a schema version

When a domain DTO evolves from:

~~~text
v1: totalPrice -> STRING
v2: totalAmount -> DECIMAL, currency -> STRING
~~~

a notification pinned to an older revision must render under the contract that revision supports. Never feed a new DTO blindly into an old template hoping field names match.

### Re-rendering differs from resending raw MIME

- **Re-render:** from revision + model + formatters + assets; may depend on renderer/runtime versions.
- **Resend MIME snapshot:** resends stored bytes, preserving exact formatting yet complicating MIME headers, `Message-ID`, token TTLs, and retention.

Neither strategy guarantees exactly-once SMTP. When a provider may have accepted before a client timeout, run **UNKNOWN/reconciliation** before deciding to resend.

### Separate send attempts from content versions

One notification:

~~~text
notificationId = N-101
revisionId = R-17
modelSnapshotId = M-101
attemptId = A-1, A-2, ...
~~~

**attemptId** changes per attempt; **notificationId**, **revisionId**, and model snapshot ID usually stay fixed for the same logical notification.

## 20. Outbox schema for template version pinning

An illustrative outbox table:

~~~sql
CREATE TABLE mail_notification_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    notification_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(60) NOT NULL,
    recipient_ref VARCHAR(180) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_revision_id UUID NOT NULL
        REFERENCES mail_template_revision(revision_id),
    template_hash VARCHAR(128) NOT NULL,
    model_schema_version INTEGER NOT NULL,
    model_snapshot_json JSONB NOT NULL,
    locale VARCHAR(40) NOT NULL,
    variant VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_notification_dedup
        UNIQUE (tenant_id, notification_key)
);

CREATE INDEX idx_mail_outbox_due
ON mail_notification_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

**recipient_ref** can point to an access-controlled recipient record instead of storing raw email addresses inline; if you must keep the address at creation time, design snapshots, PII encryption, and retention. **model_snapshot_json** may also hold PII; enforce encryption, authorization, purge policies, and keep it out of logs.

### Write inside the business transaction when required

~~~text
BEGIN
  Update Order state
  Insert mail_notification_outbox(
      template_revision_id,
      model_snapshot_json,
      notification_key
  )
COMMIT
~~~

When business data and the outbox share one database transaction, the send intent is guaranteed to commit alongside business changes. Since SMTP acceptance sits outside the transaction, leases, retries, and idempotency/reconciliation are still required.

### Pinning when the worker first picks a revision

Under resolve-on-first-send, `template_revision_id` may initially be nullable **before** the first attempt. Alter the schema to permit null and perform an atomic update so two workers cannot pin two different revisions. Never copy the `NOT NULL` schema above and claim it supports nulls: those are **two different designs**.

### Never change the pinned revision because of an SMTP retry error

A connect/refused or 4xx error has nothing to do with templates. Workers must keep the pinned revision and only retry transport per policy—never "switch to latest" to cure SMTP failures.

## 21. Combining with transactional outbox and idempotency

The template registry solves **which content**; the transactional outbox solves **durable notification intent**.

~~~text
OrderConfirmed event
      |
      v
Select revision 17 + model snapshot
      |
      v
Write outbox row with stable notification key
      |
      v
Worker claims job atomically
      |
      v
Render revision 17 + snapshot
      |
      v
Submit SMTP
      |
      +-- Accepted -> ACCEPTED
      +-- Proven not accepted retryable -> RETRY_WAIT
      +-- Permanent reject -> PERMANENT_FAILED
      '-- Unknown after network ambiguity -> UNKNOWN
~~~

### The outbox can be claimed atomically

With PostgreSQL:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_notification_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND available_at <= CURRENT_TIMESTAMP
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_notification_outbox AS job
SET status = 'IN_FLIGHT',
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE job.id = candidate.id
RETURNING
    job.id,
    job.template_revision_id,
    job.model_snapshot_json;
~~~

This is a minimal claim example, **not a complete production-safe worker implementation**: production requires lease owners/tokens, timeouts, attempt history, recovery, fencing, retry policies, and outcome classification. Crucially, two workers must never read `PENDING` and send before acquiring ownership.

### Content consistency does not equal once-only sending

If the SMTP server receives `DATA` and the client loses the response, the worker cannot tell whether it was accepted. Even with pinned template revisions and model snapshots, retries can still send duplicates. **Immutable templates give consistent content, not exactly-once delivery**.

### Notification dedup and template revision are separate keys

**notification_key** prevents duplicate business event enqueuing, whereas **revisionId** identifies content. Different notifications can share the same revision; never merge them merely because they share a template key/version.

## 22. Changing content for pending notifications

This is a product decision, not purely a SQL statement.

Suppose:

~~~text
10:00  20,000 notifications enqueued with revision 17
10:15  Content team discovers a typo in revision 17
10:20  Publish revision 18 and switch active pointer
10:30  8,000 v17 notifications still unsent
~~~

### Three groups to distinguish

1. **No attempt yet:** consider policy-governed migration if updated copy is genuinely necessary.
2. **Currently IN_FLIGHT:** never swap revisions mid-submission; outcomes may already be ambiguous.
3. **ACCEPTED/UNKNOWN:** never automatically turn into resends of revision 18; handle via reconciliation and duplicate-risk rules.

### Strategies for pending revisions

| Policy | Behavior | When appropriate |
| --- | --- | --- |
| **Keep pinned** | All v17 notifications proceed with v17 | Minor wording tweaks |
| **Pause + review** | Hold unsent v17 jobs | Broken copy needing human decision |
| **Migrate not-attempted** | Move selected unattempted v17 jobs to v18 with audit | Must-fix copy, not yet submitted |
| **Revoke** | Block v17 even for future attempts | Severe security/legal error |
| **Cancel + recreate** | Cancel unsent jobs, create new notifications per business policy | Logical event/content genuinely changed |

### Migrations must be conditional

Never run:

~~~sql
-- Do not run blindly in production:
UPDATE mail_notification_outbox
SET template_revision_id = :revision_18
WHERE template_revision_id = :revision_17;
~~~

That can modify `ACCEPTED`/`UNKNOWN` jobs and corrupt audits. Valid migrations must restrict to unattempted states, verify model schema compatibility, record old/new revisions, reason, operator, and confirm per batch. If emails already went out, use a dedicated **correction notice** workflow instead of quietly altering history.

### Revocation needs clear policies

A revision carrying a malicious URL or illegal disclaimer may need blocking even for already-pinned jobs. That does not mean deleting the revision; retain metadata and move unsent jobs to **NEEDS_REVIEW** or cancel per policy. Sending a correction email to people who already received the bad copy is an **intentional new notification**, not a silent retry with swapped content.

## 23. Dependencies, layouts, and asset versions

An email template is rarely just one HTML file:

~~~text
ORDER_CONFIRMED revision 17
   |
   +-- subject template v17
   +-- plain template v17
   +-- html body v17
   +-- shared header layout v5
   +-- shared footer layout v9
   +-- logo asset hash A
   +-- button style asset hash B
   '-- variable schema v3
~~~

If the shared header automatically uses the latest copy, revision 17 renders differently even though its main template row never changed. Therefore, **pin the dependency graph** or build an immutable **render bundle**.

### Immutable bundle manifest

~~~json
{
  "revisionId": "6f15ed00-0000-4000-8000-000000000017",
  "renderer": "THYMELEAF",
  "html": "sha256:html-body-v17",
  "plain": "sha256:plain-v17",
  "subject": "sha256:subject-v17",
  "layout": "sha256:header-v5",
  "footer": "sha256:footer-v9",
  "assets": {
    "logo": "sha256:logo-v3",
    "button": "sha256:button-v2"
  }
}
~~~

These hashes are illustrative placeholders, not real SHA-256 digests. In production, use explicit canonicalization and hash real bytes to verify integrity.

### Inline assets vs remote assets

- **CID inline images:** embedded inside `MimeMessage`, requiring content bytes from the pinned asset revision.
- **Remote HTTPS images:** email clients fetch them after delivery; images may change or get blocked, so visual output isn't strictly reproducible.
- **Attachments:** often contain sensitive business records; enforce explicit policies/references rather than grabbing the latest file on retries.

For high-audit emails, specify which versions of attachments/layouts/resources must be kept. An HTML content hash alone **cannot guarantee** identical rendering if assets or formatter libraries change.

## 24. Registry caching: immutable content vs mutable activation

Reading the same revision thousands of times can load the database, so registries usually cache. However, distinguish carefully:

| Cache | Appropriate key | Characteristics |
| --- | --- | --- |
| **Revision content** | revisionId + contentHash | Immutable, can use long TTL |
| **Manifest** | revisionId + schemaVersion | Immutable alongside revision |
| **Compiled template** | revisionId + engineVersion + contentHash | Tied to renderer/runtime |
| **Active pointer** | environment + tenant + key + locale + brand + variant | Mutable, needs invalidation |
| **Fallback resolution** | full selector + policyVersion | Changes when activations/policies change |
| **Recipient-specific rendered output** | Never cache by templateKey | Contains PII, tokens, and business data |

### Why active pointers are harder to cache than revisions

~~~text
Node A cache: active -> revision 17
Node B cache: active -> revision 17

Operator activates revision 18
  |
  +-- Node A invalidates immediately -> 18
  '-- Node B misses invalidation -> stays 17
~~~

New notifications can temporarily resolve to two different revisions. When strict/immediate version selection is required, design matching consistency: read active pointers from the authoritative source, use short TTLs, version stamps, or confirmed invalidations.

### Revision caches can use long TTLs when content is immutable

When revision 17 is genuinely immutable, caching by `revisionId + hash` can live a long time without fear of silent edits behind the scenes. Still:

- Check **REVOKED** status from authoritative policy if immediate blocking is required.
- Ensure asset/dependency bundles remain fetchable.
- Bound eviction and cache capacity.
- If the renderer upgrades, compiled output caches may need a new namespace.

### Cache misses must never fall back to arbitrary copies

On a cache miss when the registry DB is temporarily unreachable, workers should retry per policy or fail closed depending on purpose. Never pick an unversioned local file just to make SMTP succeed.

### Never cache token-bearing rendered output without strict isolation

If HTML output is cached by **`templateKey`** without recipient/model identity, one user could receive another user's token link. If personalized output caching is genuinely needed, enforce full keys, TTLs, encryption, access controls, and risk reviews; most systems should cache only **revision sources**, never PII-filled HTML.

## 25. Cache invalidation and rollout consistency

A common strategy:

~~~text
Operator publishes revision 18
          |
          v
DB transaction changes active pointer
          |
          v
Commit + record activation event
          |
          v
Event bus / pub-sub invalidates selector caches
          |
          v
Workers resolve revision 18 for NEW notifications
~~~

If an invalidation event is lost, TTLs or version checks must let caches converge to the right state. Never assume pub-sub delivery is exactly-once; activation events can repeat or lag.

### Version stamps for active pointers

An activation row can include:

~~~text
templateKey=ORDER_CONFIRMED
tenant=tenant-A
locale=vi-VN
activeRevision=18
activationVersion=6
~~~

Caches store `activationVersion` to detect stale entries. Atomic pointer updates must increment the version in the same transaction.

### Consistency scenarios

| Requirement | Viable solution |
| --- | --- |
| Staging / dev | Short TTL may suffice |
| Marketing campaign rollout | Activation snapshots and canary assignment |
| Transactional audit | Pin revision at enqueue time |
| Security template emergency revoke | Strong revocation check at send time |
| Multi-region | Define max propagation lag and fallback when unverified |

### Never split subject and body into two mutable cache keys

If subject caches by `templateKey` while HTML caches by `templateKey+locale` and invalidations race, a single render can mix two revisions. The resolver must return a **complete revision snapshot**, and everything renders from that snapshot.

## 26. Separating publishing from active traffic

**Publishing** makes a revision eligible for use; **activating** puts it into live traffic. Separating the two enables:

1. Publish revision 18 after review.
2. Preview in staging or a pilot tenant.
3. Run smoke tests/golden fixtures.
4. Activate revision 18 for 1% of eligible traffic.
5. Watch errors, bounces, and support feedback.
6. Ramp to 5%, 25%, 100% per policy.

### Weighted rollouts must be sticky

If a worker picks variants randomly on every attempt:

~~~text
Attempt 1: variant A
Retry 2:   variant B
~~~

the same notification changes content mid-flight. Compute assignment from **stable notification/recipient/experiment IDs** or persist the assignment before external side effects.

An assignment model:

~~~java
public record TemplateAssignment(
        String experimentId,
        String variant,
        java.util.UUID revisionId
) {
}
~~~

### Never A/B test content requiring strict consistency

Testing marketing copy is fine; invoices, tax notices, or password resets need strict review and tracking. A campaign marketer should not be able to alter a security-critical template purely through an experiment flag.

### Rollouts require sufficient observability

A syntactically valid revision can still emit broken links in a rare locale. Track:

- Render failure rate by revision/locale.
- Email rejected/accepted rates and bounces when provider events exist.
- Missing/mismatched variables.
- Unusual spikes in complaints or support tickets.
- Failure rates in canary cohorts vs control cohorts for the same purpose.

**SMTP acceptance rate** does not fully capture recipient experience; evaluating campaigns also requires delivery/bounce metrics when providers supply them, following tracking policies.

## 27. Previews, fixtures, and golden render snapshots

A registry shines when reviewers see realistic output before publishing. Previews should use **model fixtures** across locales, tenants, and edge cases.

### Essential fixtures

| Fixture | Purpose |
| --- | --- |
| **happy-path** | Normal data |
| **long-customer-name** | Line wrapping / layout breakage |
| **missing-optional** | Defaults and conditional rendering |
| **currency-vnd / currency-usd** | Monetary formatting |
| **rtl-locale** (if supported) | Text directionality |
| **special-characters** | Unicode, quotes, HTML escaping |
| **url-with-query** | Link encoding and host checks |
| **many-line-items** | Email length limits |
| **no-attachments** | Plain/HTML remain complete |
| **expired-token** | Never display invalid CTAs |

Example fixture:

~~~json
{
  "fixture": "long-customer-name",
  "templateKey": "ORDER_CONFIRMED",
  "revisionId": "6f15ed00-0000-4000-8000-000000000017",
  "locale": "vi-VN",
  "model": {
    "customerDisplayName": "A very long customer name with characters < & >",
    "orderCode": "ORD-1528",
    "formattedTotal": "250.000 ₫",
    "orderLink": "https://app.example.test/orders/ORD-1528"
  }
}
~~~

Fixtures must follow data governance: use **synthetic/fake data**—never paste raw customer records or production tokens into preview systems.

### Golden snapshots should be tested intentionally

Store expected rendered Subject/plain/HTML for a revision and model fixture. If output shifts after an engine/version change, developers catch it before deployment. When copy changes intentionally, create a new revision and update snapshots through review rather than auto-overwriting baselines.

### Visual rendering across email clients

HTML emails render differently across Outlook, Gmail, and mobile clients. Testing can include visual screenshots in supported clients, checking responsive layouts, alt text, dark mode, and image blocking. This belongs to the template publishing pipeline; it does not require the lesson's STEP 4 worker to test rendering on a specific client.

### Plain text must carry meaningful content

Never leave **`plainTextTemplate`** empty assuming everyone reads HTML. Plain text supports non-HTML clients and accessibility tools and needs corresponding links and instructions.

## 28. Static analysis of templates before publishing

Beyond previews, automated checks can detect:

- Missing template key/revision/locale/brand.
- Invalid renderer syntax.
- Variables referenced without manifest declarations.
- Required variables missing from fixtures.
- Dead branches or uncovered conditionals.
- Subject containing line breaks after rendering.
- HTTP links outside allowlists or using unsafe schemes.
- Unclosed HTML tags or malformed markup.
- Images missing alt text per policy.
- Missing plain-text body.
- Deleted mandatory legal/copyright/footer blocks.
- Broken asset references.
- Excessive length or unreplaced placeholder markers.

### Static analysis does not prove runtime correctness

A template can pass syntax checks and sample fixtures yet fail when real data is longer or a service returns null. Therefore, enforce **runtime variable validation** with categorized errors and alerts, not just one-time publish checks.

### Schema compatibility at publish time

If revision 18 requires a new **`trackingUrl`** variable that business producers do not supply yet:

~~~text
Producer model schema v2
Template revision 18 expects schema v3
   -> SCHEMA_NOT_COMPATIBLE
   -> Do not activate in production
~~~

Either make the variable optional with a safe default, or deploy the producer first and publish the template afterward. Never let the engine silently render null as the literal word `"null"` inside an email.

## 29. Compatibility across multiple application versions

During rolling deployments, v1 and v2 workers can coexist:

~~~text
Worker v1 supports model schema: 1, 2
Worker v2 supports model schema: 2, 3

Template revision 18 requires schema 3
~~~

Activating revision 18 while v1 workers still process new notifications causes render failures. A safe release plan:

1. Deploy code supporting schema v3 backward-compatibly.
2. Verify all active workers support v3.
3. Publish/activate template revision 18.
4. Monitor errors and canaries.
5. Remove old schema support only once no pinned outbox jobs need it and retention allows.

### Event/model contracts must be explicit

Model snapshots can carry **`modelSchemaVersion=2`** in the outbox. Renderers can maintain **`v2→v3`** adapters if supported, yet adapters must be explicitly tested and pinned rather than guessing renamed fields.

### Renderer engine versions matter too

Two versions of Thymeleaf or formatting libraries can differ in whitespace, escaping, locale formatting, or expression evaluation. For high-audit emails, store **`rendererVersion`** or **`renderBundleVersion`** alongside revisions for reproducibility. Where byte-level fidelity is critical, consider storing protected **rendered content snapshots** per security/retention policy.

### Never silently change template languages

If revision 17 used Thymeleaf and a new engine switches to FreeMarker, the same revision source cannot be parsed by a different engine without migration. **`renderer type/version`** must be durably persisted metadata.

## 30. Protecting the registry from unauthorized access and changes

Templates carry logos, URLs, legal copy, and account instructions. Anyone who can alter templates could phish users or redirect them to spoofed sites.

### Role-based and scoped permissions

| Role | Sample permissions |
| --- | --- |
| **Viewer** | View approved content within tenant |
| **Author** | Create/edit drafts in scope |
| **Reviewer** | Approve exact snapshots |
| **Publisher** | Publish approved revisions |
| **Operator** | Activate/rollback within scope |
| **Auditor** | View history and hashes |
| **Security administrator** | Audited emergency revocations |

All actions require authentication and tenant-scoped authorization. Never just hide the "Publish" button in the UI; enforce checks on server APIs.

### Prevent content editors from changing sender identities

Marketing teams may manage copy, yet **From domains, Return-Path, Reply-To, DKIM, and DMARC** belong to sending policy. Never let editors type arbitrary `From` addresses and send from unverified domains. Reference allowlisted `senderProfile` IDs.

### Review content for phishing risks

A new template adding a "Sign in to verify" link pointing outside product-owned hosts is high risk. Static URL allowlists, independent reviewers, and change monitoring are effective controls. Check more than just valid HTML.

### Secrets never belong in template bodies

SMTP credentials, provider API tokens, and signing keys must never enter variable schemas, draft previews, or template sources. One-time recipient tokens may appear in links; generating and storing them belongs to authentication/business services with TTLs, audits, and no-logging policies.

### Audits must be append-only

An audit record should capture:

~~~text
action=PUBLISH
revisionId=...
previousStatus=APPROVED
newStatus=PUBLISHED
actor=content-publisher-1
at=2026-01-01T09:00:00Z
contentHash=sha256:...
reason=release-notes-reference
~~~

Never allow content editors to delete history of past approvals or activations. Retention and privacy rules may require purging certain data; design audit metadata to preserve minimum policy-compliant evidence.

## 31. Monitoring and metrics for the template registry

Because the template registry controls content, failures can surface before SMTP is even reached—for example, registry DB outages, wrong locale fallbacks, stale active-pointer caches, or missing variables.

### Recommended metrics

| Logical name | Type | Meaning |
| --- | --- | --- |
| **mail_template_resolutions** | Counter | Resolution counts by outcome |
| **mail_template_resolution_seconds** | Timer | Latency to resolve revisions |
| **mail_template_renderings** | Counter | Render successes/failures |
| **mail_template_render_seconds** | Timer | Render duration |
| **mail_template_missing_variables** | Counter | Missing required variable errors |
| **mail_template_schema_mismatch** | Counter | Producer vs revision incompatibilities |
| **mail_template_cache_requests** | Counter | Cache hits/misses/failures |
| **mail_template_activation_changes** | Counter | Activation/rollback counts |
| **mail_template_revoked_blocked** | Counter | Jobs blocked due to revoked revisions |
| **mail_template_resolution_fallback** | Counter | Locale/brand/scope fallback counts |
| **mail_template_preview_failures** | Counter | Errors previewing drafts/revisions |
| **mail_notification_stuck_due_template** | Gauge | Pending notifications stuck due to template errors |

These are **application-instrumented** metrics, not emitted natively by **`JavaMailSender`**. When exporting to Prometheus, normalize names and append **`_total`** suffixes on counters per registry conventions.

### Low-cardinality labels

Safe labels:

~~~text
purpose=security|transactional|marketing
result=success|not_found|invalid_model|revoked
locale=vi-VN|en-US|other
environment=staging|production
renderer=thymeleaf|freemarker
~~~

**templateKey** and **revisionId** help investigations, yet evaluate cardinality carefully as templates and versions grow. Never put recipient addresses, `notificationId`, `orderId`, raw subjects, or model values into metric labels.

### Micrometer wrapper example

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Map;

public final class MeteredTemplateRenderer {

    private final ThymeleafMailContentRenderer delegate;
    private final MeterRegistry registry;

    public MeteredTemplateRenderer(
            ThymeleafMailContentRenderer delegate,
            MeterRegistry registry
    ) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public RenderedMailContent render(
            ResolvedMailTemplate revision,
            Map<String, Object> checkedModel
    ) {
        Timer.Sample sample = Timer.start(registry);
        String result = "failure";
        try {
            RenderedMailContent output =
                    delegate.render(revision, checkedModel);
            result = "success";
            return output;
        } finally {
            registry.counter(
                    "mail_template_renderings",
                    "result", result
            ).increment();
            sample.stop(
                    registry.timer("mail_template_render_seconds")
            );
        }
    }
}
~~~

This example measures render counts and duration without classifying exception types. Production code can map errors to bounded reason codes, never raw exception text as labels.

### Spot pre-SMTP errors

If mail outbox due backlog grows alongside rising **`mail_template_renderings{result=failure}`**, do not focus on SMTP hosts first. Inspect registry lookups, model schemas, asset availability, or the renderer runtime.

### Active revision dashboard

A panel might show:

~~~text
Template key         Locale   Active   Activated at
ORDER_CONFIRMED      vi-VN    rev17    ...
ORDER_CONFIRMED      en-US    rev15    ...
PASSWORD_RESET       vi-VN    rev04    ...

Render failures (5m):  12
Fallback resolutions:  43
Cache stale warnings:   2
Revoked jobs blocked:   0
~~~

In multi-tenant/high-revision systems, paginate and scope-filter dashboards. Do not force every key into Prometheus labels if cardinality explodes; use read-only registry queries for detailed drill-downs.

## 32. Impact-based alerting

Not all template errors have equal severity. An experimental marketing template failing can wait until business hours, whereas **`PASSWORD_RESET`** missing an active revision locks users out of account recovery.

### Suggested alerts

| Alert | Signal | Action |
| --- | --- | --- |
| **Security template unavailable** | Cannot resolve critical security template | Investigate activation/registry immediately |
| **Render failure spike** | Render errors climb by purpose | Check schema/locale/renderer |
| **Template missing variables** | Required variable errors | Producer/template compatibility |
| **Cache not converging** | Nodes return different active revisions than authoritative store | Invalidate/reconcile caches |
| **Revoked revision still attempted** | Workers try using revoked content | Block sends, verify policy |
| **Template asset missing** | Unable to fetch immutable asset | Check object store/retention/manifest |
| **Approval bypass** | Published without valid approval | Security audit, lock activation |
| **Mail due backlog caused by rendering** | Jobs waiting due to render errors | Fix content/model, not just scale SMTP |

### Tie alerts to purpose and state

Do not alert merely because "revision 18 has no active pointer yet" while it is still `DRAFT`. However, if a required production key lacks an active revision, signal clearly even before traffic hits it. Pair **config readiness validation** before release with runtime failure metrics.

### Do not assume rollback resolves the whole incident

After switching the active pointer back to 17, notifications already pinned to 18 may still sit in `PENDING`/`RETRY_WAIT`. Alerts must watch **jobs pinned to revoked/broken revisions**, not just the active pointer panel.

## 33. Testing registry resolution

Resolver tests should cover exact combinations of template key, tenant, locale, variant, and environment.

### Example policy test with a fake registry

A resolver interface:

~~~java
public interface ActiveTemplateResolver {
    ResolvedMailTemplate resolve(TemplateSelector selector);
}
~~~

Sample input:

~~~text
Template:
  key=ORDER_CONFIRMED
  locale=vi-VN
  tenant=tenant-A
  brand=retail
  active=rev17

Given:
  selector tenant-A / vi-VN / retail
Expected:
  resolved revision rev17
~~~

### Mandatory test cases

| Scenario | Outcome |
| --- | --- |
| Exact tenant/locale/brand exists | Exact match selected |
| Tenant revision missing, global approved allowed | Falls back to approved global |
| Tenant B revision exists, A missing | Never selects B |
| Locale vi-VN missing, en-US fallback forbidden | Resolution failure |
| Active pointer points to `DRAFT` | Blocks send, reports misconfiguration |
| Active revision is `REVOKED` | Blocks send |
| Highest version number is `DRAFT` | Never auto-selected |
| Revision exists yet asset missing | Asset integrity failure |
| Manifest incompatible with producer | Schema mismatch |
| Operator changes active during resolution | Single response stays within one revision |

### Testing concurrency

Two operators concurrently activate different revisions from the same expected pointer: one succeeds while the other gets a conflict rather than silently overwriting. With multi-region replication, also test convergence and stale-pointer behavior.

### Testing isolation

A tenant cannot read, activate, or preview another tenant's drafts/assets without permission. Enforce this at server APIs/repositories, not only in the UI.

## 34. Unit testing rendering and required variables

Because the renderer is decoupled from SMTP, tests invoke it directly:

~~~text
revision 17 + checked model -> RenderedMailContent
~~~

### Recommended test suite

1. **Required variable missing:** fails before SMTP.
2. **Optional variable missing:** uses default from the exact revision's manifest.
3. **Wrong type:** fails with explicit reason code.
4. **HTML escaping:** names with `<`, `>`, `&` never become raw markup.
5. **URL validation:** links with wrong hosts/schemes are rejected.
6. **Subject CRLF:** no line breaks or header injection.
7. **Locale formatting:** prices and dates use the right locale/timezone.
8. **Long fields:** bounded length, no renderer OOM.
9. **Plain + HTML:** both carry required business info.
10. **Shared layout versions:** revision 17 still uses pinned assets/layouts.
11. **Renderer upgrades:** golden fixture outputs do not shift unexpectedly.
12. **Revoked revisions:** blocked from sending per policy.

### Short JUnit example

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ThymeleafMailContentRendererTest {

    @Test
    void rendersSubjectAndBothBodyForms() {
        ResolvedMailTemplate revision =
                new ResolvedMailTemplate(
                        UUID.randomUUID(),
                        "ORDER_CONFIRMED",
                        "vi-VN",
                        "retail-main",
                        "default",
                        17,
                        3,
                        "Order confirmation [[${orderCode}]]",
                        "Order [[${orderCode}]] has been confirmed.",
                        "<p th:text=\"${orderCode}\">old</p>",
                        "sha256:demo",
                        Instant.parse("2026-01-01T00:00:00Z"),
                        Map.of()
                );

        RenderedMailContent result =
                new ThymeleafMailContentRenderer().render(
                        revision,
                        Map.of("orderCode", "ORD-1528")
                );

        assertEquals(
                "Order confirmation ORD-1528",
                result.subject()
        );
        assertTrue(result.plainText().contains("ORD-1528"));
        assertTrue(result.html().contains("ORD-1528"));
        assertEquals(revision.revisionId(), result.revisionId());
    }
}
~~~

This snippet tests the renderer; **variable validation** sits upstream of rendering in the architecture and needs separate tests. UUID/hash values here are test data; never treat dummy hashes as integrity proof for real templates.

### Testing without SMTP

Testing templates requires no real emails. MIME composer/SMTP integration tests can use GreenMail or an isolated SMTP test fixture. Keep fast parser/renderer unit tests separate from slower network/integration tests.

## 35. Integration testing with Spring Mail and an SMTP fixture

An integration test can follow:

~~~text
In-memory/fake Registry
        |
        v
Pinned revision 17
        |
        v
Validator + Renderer
        |
        v
MimeMessageHelper
        |
        v
GreenMail local SMTP
        |
        v
Captured MIME
        |
        +-- Subject
        +-- plain/html
        +-- charset
        '-- attachment/inline asset refs
~~~

### Key assertions

- Actual Subject contains the expected order code/variables.
- To/From are addresses permitted by validation/verified policy.
- Both plain and HTML contain core content.
- MIME charset handles Vietnamese/Unicode properly.
- HTML contains no unrendered placeholders.
- Inline CIDs and attachments match the manifest.
- Revision 17 renders even if the active pointer switched to 18 before retry.
- Already-accepted emails are not auto-resent merely because registry activation changed.

### Testing rollback does not alter old notifications

~~~text
Given:
  N1 pinned=revision17
  active pointer changed=revision18
  operator rollback active=revision16

When:
  N1 is dispatched

Then:
  N1 uses revision17
  contentHash matches pinned revision17
~~~

### Testing version migration only affects unattempted jobs

Another integration test can verify a 17→18 migration touches only unsent, non-`IN_FLIGHT`, non-`UNKNOWN`/`ACCEPTED` notifications with compatible schemas and auditing. The goal is never rewriting history for anything already submitted to SMTP.

### Never use SMTP timeouts to swap templates

If the server may have accepted while the client missed the response, the job enters `UNKNOWN`. Never switch to the latest revision and resend as a "workaround."

## 36. Runbook: a new template version causes send failures

Suppose after activating revision 18, dashboards show rising **render failures** and growing mail outbox backlogs. A runbook prevents jumping straight to blaming SMTP.

### Step 1 — Verify symptoms

Collect:

~~~text
templateKey / purpose:
environment / tenant / locale / variant:
active revision:
revision hash:
activation time:
first render failure time:
failure category:
number of pending notifications:
number of attempts already submitted:
oldest due age:
~~~

Correlate failure onset with active pointer changes, producer deployments, or renderer upgrades. If errors affect only one rare locale or specific tenant, do not shut down unrelated email traffic.

### Step 2 — Distinguish resolver, model, and rendering

| Symptom | Suspect |
| --- | --- |
| **TEMPLATE_NOT_FOUND** | Broken activation/mapping or missing scope |
| **LOCALE_NOT_ALLOWED** | Fallback policy disallows fallback |
| **SCHEMA_NOT_COMPATIBLE** | Producer model vs revision mismatch |
| **MISSING_REQUIRED_VARIABLE** | Producer omitted variable |
| **ASSET_NOT_FOUND** | Asset bundle/retention issue |
| **RENDERER_PARSE_ERROR** | Template syntax / engine version |
| **INVALID_SUBJECT** | CRLF or blank subject |
| **SMTP_CONNECT_FAILURE** | Transport, not template |

Clear failure categories avoid dumping full models/HTML containing personal data.

### Step 3 — Stop new impact if necessary

If a new template contains broken links or policy-violating wording, consider:

- **Pause** notifications for the affected key/scope.
- **Roll back the active pointer** for new requests.
- **Revoke the revision** if even pinned jobs must stop.
- Pause the campaign or keep only valid transactional flows running.

Rolling back the active pointer **does not change** revisions already pinned in the outbox. Handle pending jobs separately.

### Step 4 — Segment the outbox

~~~text
Group A: no attempt yet, pinned bad revision
Group B: IN_FLIGHT, possibly submitting
Group C: ACCEPTED, already submitted
Group D: UNKNOWN, result ambiguous
Group E: render failed before SMTP submission
~~~

For Group E, fix the model or migrate revisions per policy if proven unsent; never rewrite Group C's accepted history, and reconcile Group D before retrying.

### Step 5 — Fix in place or create a new revision?

If revision 18 only has a one-character typo, **never edit revision 18 in place**. Create revision 19 from the fix, test, and approve. Handle pending notifications on revision 18 via an audited migration policy instead of letting "revision 18 suddenly morph into new content."

### Step 6 — Confirm recovery

- New notifications resolve the intended active revision.
- Renderer errors drop.
- Pending due jobs and oldest age decline.
- No extra broken-template notifications go out unintentionally.
- Jobs pinned to the bad version are held/migrated/revoked per state.
- Audits record operator, reason, old/new revisions.
- Caches converged or bypassed if stale.

### Step 7 — Postmortem

Examine how the bug slipped past validation/previews—were fixtures or schema contracts missing? Add tests for variants, locales, token URLs, or producer versions, and keep template errors separated from SMTP errors in alerts.

## 37. Runbook: active pointer is right, yet emails still use an old version

Symptoms:

~~~text
Registry DB active = revision 18
App node A emits revision 18
App node B emits revision 17
~~~

Possible causes:

- Node B's active-pointer cache was not invalidated.
- Node B reads a database region/replica experiencing replication lag.
- Different environment/tenant/brand/locale selectors.
- Some notifications were **pinned to revision 17 before activation** (which may be completely expected).
- Worker renders from a classpath template instead of the registry.
- Compiled template cache was keyed by `templateKey` instead of `revisionId`/hash.

### Analyze by data category

**Case 1 — New notification expected to use revision 18:** inspect resolver/cache consistency and activation scope.

**Case 2 — Existing notification pinned to 17:** not a cache bug; that is the pinning policy working as designed. If business needs it changed, run an unattempted-only audited migration.

### Safe actions

- Check **`notificationId -> pinned revision`** first.
- Compare full selectors and `activationVersion`.
- On stale caches, invalidate the right scope or temporarily bypass cache.
- Verify revision body hashes against the authoritative source.
- Never alter `contentHash` in the database to force old data to match.
- Never replay already-accepted emails just to unify versions.

### Consequence of wrong cache keys

If compiled templates cache under **`ORDER_CONFIRMED`** while new data resolves **`revision 18`**, the engine may serve compiled v17 bodies. Cache keys must include `revisionId`/`contentHash`/renderer version by contract rather than relying on manual invalidation commands on every publish.

## 38. History storage, retention, and privacy

Template revision metadata generally outlives individual notifications. Yet **model snapshots** and **rendered MIME** can hold PII, so retention must vary by data class.

| Data | Why keep it | Risk |
| --- | --- | --- |
| **Template source revision** | Public/approved copy history | May contain internal URLs or restricted text |
| **Content hash + audit** | Verification and approval trail | May reveal sensitive changes |
| **Model snapshot** | Per-notification content reproduction | PII, names, addresses, amounts, tokens |
| **Rendered MIME** | Investigations / transaction records | Full content and attachments |
| **Sender/recipient metadata** | Delivery audits, suppression | Email addresses, personal data |
| **Asset bundle** | Reproduce revisions | Graphics, licensed files, tracking |

### Never store tokens indefinitely just for re-rendering

Password reset tokens or one-time links have short TTLs. Audit needs do not justify keeping plaintext tokens for years. Store metadata, hashes/opaque references, and template details instead; when reproducing, show a redacted copy or secret-free proof.

### Content retention differs from delivery history

You can retain:

~~~text
revisionId + contentHash + approvedAt
~~~

long-term, while deleting or pseudonymizing:

~~~text
recipient full address
model snapshot with PII
raw attachment bytes
~~~

according to data policies. Once models are purged, state clearly that exact re-rendering is no longer possible for that notification. Never promise "100% email reproduction forever" when retention purges required inputs.

### Audits should not log full content into application logs

Suggested log:

~~~text
event=mail_template_resolved
template_key=ORDER_CONFIRMED
revision_id=6f...
locale=vi-VN
resolution=EXACT
render_result=SUCCESS
notification_id=opaque-id
~~~

Opaque IDs can still carry correlation risk, so manage log access and retention too.

## 39. Common implementation mistakes

### Mistake 1 — Editing published revisions directly

**Consequence:** broken audits, retries changing old notification copy, inconsistent caches.

**Fix:** create a new revision and move the active pointer only after approval.

### Mistake 2 — Selecting templates with MAX(versionNumber)

**Consequence:** picks `DRAFT` or unactivated revisions.

**Fix:** resolve via activation mapping and scope.

### Mistake 3 — Taking Subject and HTML from two revisions

**Consequence:** recipients see contradictory content.

**Fix:** one `ResolvedTemplate` snapshot holds all parts.

### Mistake 4 — Not pinning revisions in the outbox

**Consequence:** post-deploy retries generate different emails than prior attempts.

**Fix:** pin at enqueue or before the first attempt and keep it fixed.

### Mistake 5 — Pinning templates without pinning models

**Consequence:** the same revision renders changed prices/names/links from updated DB data.

**Fix:** versioned model snapshots or rendered content snapshots per policy.

### Mistake 6 — Falling back from one tenant to another's template

**Consequence:** leaks private branding/links/content.

**Fix:** explicit approved fallback chains; never cross-tenant.

### Mistake 7 — Falling back locales without compliance checks

**Consequence:** sends wrong regional legal wording.

**Fix:** purpose/region-specific fallback policies with approval.

### Mistake 8 — Defaulting every null variable to an empty string

**Consequence:** emails go out missing order codes, amounts, or CTAs.

**Fix:** validate required variables; defaults only for optional ones.

### Mistake 9 — Using double for money

**Consequence:** precision, formatting, or rounding bugs.

**Fix:** `BigDecimal`/currency and business-defined formatters.

### Mistake 10 — Assuming HTML escaping suffices for URLs

**Consequence:** URLs with dangerous schemes or hosts can still render.

**Fix:** URL validation, trusted hosts, and link builders.

### Mistake 11 — Using th:utext for user input

**Consequence:** HTML injection in emails and previews.

**Fix:** `th:text`/escaping or an approved sanitizer.

### Mistake 12 — Passing untrusted source to StringTemplateResolver

**Consequence:** server-side template expressions can go beyond placeholder substitution.

**Fix:** author RBAC, reviews, sandboxing/allowlists, and restricted contexts.

### Mistake 13 — Caching active revisions too long

**Consequence:** operator rolled back, yet nodes still serve the old version.

**Fix:** short TTLs, `activationVersion`, invalidation/reconciliation.

### Mistake 14 — Caching compiled templates by templateKey

**Consequence:** new revision bytes get confused with old compiled output.

**Fix:** key by `revisionId`/`contentHash` and engine version.

### Mistake 15 — Caching personalized HTML by templateKey

**Consequence:** one user receives another user's info/tokens.

**Fix:** never cache shared rendered PII; cache immutable sources.

### Mistake 16 — Immutable revision body while logos still fetch latest

**Consequence:** approved emails cannot be reproduced faithfully.

**Fix:** pin asset manifests/dependency bundles.

### Mistake 17 — Rolling back the pointer and assuming all pending emails are fixed

**Consequence:** jobs already pinned to the bad revision still send.

**Fix:** triage unattempted, `IN_FLIGHT`, `UNKNOWN`, and `ACCEPTED` groups.

### Mistake 18 — Migrating revisions on already-accepted jobs

**Consequence:** audit/version records no longer match what was actually sent.

**Fix:** alter only unsubmitted jobs when policy permits, with auditing.

### Mistake 19 — Previewing templates with production PII

**Consequence:** customer data/tokens leak to reviewers or logs.

**Fix:** synthetic fixtures and access controls.

### Mistake 20 — Generating password reset URLs inside templates

**Consequence:** token TTLs/hosts are not managed in a trusted layer.

**Fix:** business/auth service constructs verified URLs; templates only display them.

### Mistake 21 — Letting marketing editors freely change verified From addresses

**Consequence:** DMARC alignment failures, phishing, or unverified-domain sends.

**Fix:** allowlisted `senderProfile` separate from template copy.

### Mistake 22 — Providing HTML without plain text

**Consequence:** certain clients and accessibility workflows break.

**Fix:** maintain equivalent `text/plain` content.

### Mistake 23 — Not versioning variable schemas

**Consequence:** rolling deploys hit mismatches between v2 producers and v3 renderers.

**Fix:** `modelSchemaVersion` and compatibility matrices.

### Mistake 24 — Blocking all deprecated revisions even for pinned retries

**Consequence:** valid older notifications unexpectedly fail to complete.

**Fix:** distinguish `DEPRECATED` from `REVOKED`; define send-time policies.

### Mistake 25 — Treating SMTP errors as template errors

**Consequence:** teams edit copy during a provider outage.

**Fix:** separate resolution/render/MIME/SMTP metrics and states.

### Mistake 26 — Treating SMTP accepted as delivered

**Consequence:** claiming users received emails when only submitted to a provider.

**Fix:** track delivery/bounce events separately.

### Mistake 27 — Infinite retries on render errors

**Consequence:** backlogs grow with zero progress because the template stays broken.

**Fix:** classify permanent/config/temporary failures, alert, and pause/review.

### Mistake 28 — Not recording approvers and hashes

**Consequence:** impossible to trace who approved what during incidents.

**Fix:** immutable review snapshots and append-only audits.

### Mistake 29 — Rollout variants changing across retries

**Consequence:** one notification renders different variants, skewing experiments.

**Fix:** stable assignment and revision pinning.

### Mistake 30 — Assuming template versioning gives exactly-once SMTP

**Consequence:** retrying `UNKNOWN` can still send duplicates.

**Fix:** classify SMTP outcomes, reconcile, keep idempotent notification logic, and document risk policies.

## 40. Practical scenarios

### Scenario A — Editing one sentence in a published email

Revision 17 is active for `ORDER_CONFIRMED`. Content wants to tweak an intro sentence while keeping the same version number.

**Q:** Can we UPDATE `html_template` on revision 17?

**A:** No. Create revision 18, edit/approve content, and activate per policy. Revision 17 must stay immutable so past emails and pinned jobs remain verifiable.

### Scenario B — Subject v18, HTML v17

A worker fetches subject and HTML via two `"getActiveTemplatePart"` calls while an operator activates a new revision in between.

**Q:** How should reading be fixed?

**A:** Resolve **`revisionId` once**, then fetch subject/plain/HTML/assets for that exact revision. Never query active pointers per part.

### Scenario C — Marketing email scheduled three days ahead

A campaign is approved today on revision 12. Tomorrow an author tweaks copy and activates revision 13.

**Q:** Which version does the campaign use in two days?

**A:** Depends on defined policy. If the campaign snapshot pins revision 12, use 12. If designed as resolve-at-send, pick 13 before the first attempt and pin it; scheduled changes must be approved. Never leave selection to random worker timing.

### Scenario D — Retrying an invoice email a day later

An invoice was issued at 250,000 VND, yet the next day the order DB reflects a 50,000 VND refund.

**Q:** Is pinning template revision 17 enough to preserve the original copy?

**A:** Not yet. Pin the finalized **model snapshot**/facts or rendered content so retries still send the amount valid at invoice issuance. Never query live current order totals on each attempt.

### Scenario E — Locale vi-VN has no template yet

Global fallback `en-US` exists, yet the template is a legal notice permitted only in approved country-specific translations.

**Q:** Should we fall back to `en-US`?

**A:** No if policy forbids it. Record a resolution failure and alert/manual review instead of sending unapproved wording.

### Scenario F — Tenant A lacks a custom template

Tenant B has a polished approved revision, while no global one exists.

**Q:** Can we pick Tenant B's revision?

**A:** No. Fallback may only traverse allowed scopes, such as approved global. Tenant isolation must hold.

### Scenario G — Template contains an unsafe URL

Revision 18 has a CTA pointing outside the domain allowlist.

**Q:** Is valid Thymeleaf syntax enough to publish?

**A:** No. URLs must pass trusted-host/scheme validation; security/content reviews block publishing otherwise.

### Scenario H — A required variable is missing

The model lacks `orderCode`, yet the Subject needs the order code.

**Q:** Send with a blank order code or fail?

**A:** Fail closed in the variable validator with a clear reason, without SMTP submission. Only optional variables declared in the manifest use defaults.

### Scenario I — One node still uses an old revision

DB active=18; one node resolves 18 while another resolves 17.

**Q:** Are all v17 emails wrong?

**A:** Not necessarily. First separate **new notifications** from **old pinned notifications**. If new notifications expecting 18 resolve 17, investigate stale caches or activation scopes. Old jobs pinned to 17 using 17 are likely working as intended.

### Scenario J — Immediate rollback after a severe mistake

Revision 18 has wrong info, and 3,000 unsent jobs are already pinned to 18.

**Q:** Is flipping active back to 17 enough?

**A:** No. Rollback only affects new selections. Pause/migrate/revoke unattempted jobs per policy while leaving `IN_FLIGHT`/`ACCEPTED`/`UNKNOWN` untouched to preserve audits and prevent duplicates.

### Scenario K — Subject A/B test

A user receives variant A on attempt 1, then a retry randomly picks B.

**Q:** What went wrong?

**A:** Unstable variant assignment. Compute deterministic assignment and pin revision/variant in the notification record.

### Scenario L — Content editor wants to change From

A template author enters a From address on a domain unverified with the SMTP provider.

**Q:** Should the registry allow this?

**A:** Separate `senderProfile` under mail delivery policy and domain verification. Template authors cannot override verified sender identities.

### Scenario M — Password reset link expires

A notification pinned revision 5, and the token TTL expires during retries.

**Q:** Keep sending the old link?

**A:** Enforce business deadlines and token policies. Never let a template engine mint fresh tokens uncontrolled on retry. Cancel the stale notification and let the user request a new one with a fresh token.

### Scenario N — Shared layout updates logo

Revision 17 body is unchanged, yet the global footer/logo is updated.

**Q:** Will v17 emails reproduce identically?

**A:** Only if dependencies/assets were pinned. If layouts pull latest, identical revisions render differently. Use immutable bundles or dependency manifests.

### Scenario O — SMTP reports accepted, yet user hasn't received it

Revision/render had no errors, and SMTP submission succeeded.

**Q:** Will rolling back the template fix it?

**A:** Unlikely. Check downstream delivery, bounces, suppressions, spam, and provider status. Registry/content consistency differs from deliverability.

### Scenario P — Two operators activate concurrently

Operator A tries to activate 18 while B tries to activate 16 from pointer 17.

**Q:** How do we stop silent overwrites?

**A:** Use compare-and-set or activation versions; fail when the expected pointer no longer matches and ask the operator to refresh state.

### Scenario Q — New revision requires a new model schema

Template v19 expects `trackingUrl`, which old workers do not supply yet.

**Q:** Just activate and catch runtime errors?

**A:** No. Use compatibility validation and a rollout sequence: deploy supporting producers/renderers first, test fixtures, then activate.

### Scenario R — Previews using real customer data

A content editor without invoice permissions opens a preview that loads production invoices.

**Q:** Is this safe?

**A:** No. Use synthetic fixtures, RBAC, and keep tokens/PII out of previews/logs. If real data is ever needed under exceptional rules, enforce dedicated permissions and protections.

### Scenario S — Revision urgently REVOKED

A template's CTA host was compromised; pinned jobs are still pending.

**Q:** Should workers keep sending because they were pinned?

**A:** No if revocation policy blocks all sends. Pinning ensures consistency, yet emergency security policies override revision eligibility. Pause/review jobs rather than swapping in a new version without migration/authorization.

### Scenario T — Template engine upgrade

A newer Thymeleaf version changes whitespace/escaping even though old revision sources didn't change.

**Q:** Does source `contentHash` guarantee identical rendered bytes?

**A:** No. Exact re-rendering requires knowing renderer/dependency versions, model snapshots, and asset bundles; for strict requirements, store protected rendered snapshots.

## 41. Comparing registry architectures

Not every product needs a full-blown CMS. Choose based on scale and workflow.

| Option | Benefits | Limitations |
| --- | --- | --- |
| **Templates in Git/classpath** | PR reviews, simple, release-bound | Copy changes require deploys |
| **Database registry** | Runtime activation, easy metadata/audits | Needs RBAC, schema, caching, migrations |
| **Object storage + DB metadata** | Large immutable bundles, versioned content | Needs asset integrity, consistency, retention |
| **CMS/headless editor** | Convenient authoring/previews | Must integrate approvals, security, snapshots |
| **External ESP templates** | Provider renders/sends, low self-hosting | Lock-in, hard cross-provider pinning, audit/data limits |
| **Hybrid** | Shared design system + runtime activation | More complex; must pin dependencies |

### When does Git-based fit?

With a handful of rarely changing transactional templates, repository templates versioned with code releases can suffice. Still, replaying notifications after upgrades requires knowing **application/template artifact versions** and model snapshots. Not having a DB registry does not excuse skipping content versioning.

### When does a DB registry fit?

With many tenants/locales, non-developer authors, content approvals, and deploy-free rollbacks/rollouts, a runtime registry pays off. In return, you must operate a control plane with matching security and auditing.

### Using ESP-hosted templates

Some email providers host templates and versions. When failing over across multiple providers, **`template_123`** on A may not exist or render identically on B. Map and pin provider-specific versions, or render inside the application and submit finalized content via SMTP/API.

### Keep the domain decoupled from the renderer

Domain services should say:

~~~text
Send ORDER_CONFIRMED with order snapshot
~~~

instead of:

~~~text
Render Thymeleaf file templates/mail/order-confirmed-v17.html
~~~

Registry/resolver/renderer adapters handle details so replacing Thymeleaf with FreeMarker or ESP templates later never forces rewriting domain logic.

## 42. Production implementation checklist

### Identity and content

- Stable **templateKey**, distinct from filenames and `notificationId`.
- Scopes (`tenant`/`brand`/`locale`/`variant`/`environment`) clearly defined.
- Each revision bundles subject, plain text, HTML, and metadata.
- Content/dependency hashes and revision IDs persisted.
- Renderer type/version and variable schemas have explicit contracts.
- Published revisions and assets are immutable.

### Release workflow

- Author/reviewer/publisher/operator permissions are bounded.
- Approvals bind to the exact revision content hash.
- Publishing does not auto-activate when policy separates the two steps.
- Active pointer updates are atomic with compare-and-set.
- Append-only audits record actor, timestamp, reason, old/new revisions.
- Previews and fixtures cover locales, tenants, and edge cases.
- Canary/failback/rollback scopes and emergency revocation exist.

### Rendering and sending

- Variable validator enforces required, optional, types, lengths, and URLs.
- Subject CR/LF validation and proper HTML escaping are applied.
- Plain text matches HTML content meaningfully.
- Links/tokens are generated by trusted application services.
- Template copy cannot arbitrarily alter verified sender profiles.
- MIME composer uses the exact same revision/model for all parts.
- Mail delivery policies still verify consent/suppression.

### Retries and consistency

- Revision pinning occurs at enqueue or before the first attempt.
- Model snapshots carry schema versions or use rendered snapshots.
- Attempts reuse pinned revisions and variants.
- `IN_FLIGHT`/`UNKNOWN` jobs do not auto-migrate content.
- Emergency revocations can block pending attempts.
- Notification keys, template revisions, and attempt IDs remain separate.
- Immutable rendering is never mistaken for exactly-once SMTP.

### Operations and data

- Revision caches are separate from active-pointer caches, with invalidation.
- Alerts cover stale caches, render errors, and schema mismatches.
- Retention policies cover models, HTML, MIME, and PII.
- Previews use synthetic fixtures and sandboxing.
- Raw subjects/content are not dumped into general logs.
- Audits and runbooks cover broken templates and rollbacks.
- Compatibility across rolling deployments is tested.
- Remote/inline asset dependency versions are explicitly pinned.

## 43. Template selection flow for a notification

~~~text
                  New business notification
                            |
                            v
                  Delivery policy allows?
                       |            |
                      No           Yes
                       |            |
                       v            v
                  SUPPRESSED    Resolve selector
                                    |
                       +------------+-----------+
                       |                        |
                  No eligible revision      Revision found
                       |                        |
                       v                        v
                  FAIL / REVIEW         Validate schema contract
                                                |
                                        +-------+-------+
                                        |               |
                                     Invalid           Valid
                                        |               |
                                        v               v
                                  FAIL / REVIEW      Choose pin policy
                                                        |
                                       +----------------+---------------+
                                       |                                |
                                  Pin at enqueue                   Pin at first send
                                       |                                |
                                       +----------------+---------------+
                                                        |
                                                        v
                                           Save revision + model snapshot
                                                        |
                                                        v
                                             Worker claims notification
                                                        |
                                                        v
                                          Is revision still allowed to send?
                                                |               |
                                               No              Yes
                                                |               |
                                                v               v
                                          PAUSE / REVIEW     Load exact revision
                                                                |
                                                                v
                                                       Render subject/plain/HTML
                                                                |
                                                     +----------+---------+
                                                     |                    |
                                                  Failure               Success
                                                     |                    |
                                                     v                    v
                                               Triage/error          Compose MIME
                                                                          |
                                                                          v
                                                                     SMTP submit
                                                                          |
                                                   +----------------------+----------------+
                                                   |                      |                |
                                                ACCEPTED            NOT_ACCEPTED         UNKNOWN
                                                   |                      |                |
                                                   v                      v                v
                                                 Record                Retry            Reconcile
                                                                        pinned
                                                                       revision
~~~

This is an **illustrative business diagram**, not a built-in Spring Mail state machine. Production needs transactions/outboxes, leases/fencing, provider outcomes, and proper recovery. Crucially, a pinned yet **`REVOKED`** revision must never send automatically just because its content hash still matches.

## 44. Key principles to remember

~~~text
Template key                    = logical template identity
Template revision ID            = one specific content snapshot
Active pointer                  = selects revision for new requests
Published revision              = immutable
Rollback                        = switch active pointer, never edit history
Template latest version         != active revision
Template approval               = bound to exact snapshot/hash
Variable schema                 = input contract, not arbitrary Map
Required variable missing       -> fail closed
Optional variable               -> explicit per-revision default
Tenant fallback                 -> only through allowed scopes
Locale fallback                 -> per policy, never random
Pinned revision                 -> consistent rendering per notification
Pinned revision alone           != model snapshot
Rendered output                 = subject + plain + HTML from one revision
Shared header/footer/logo       -> pin dependency versions
Preview                         -> synthetic data, never leak tokens
Renderer compiled cache         -> keyed by revision/hash/engine
Active pointer cache            -> needs invalidation/versioning
Security revoke                 -> can block pinned revisions
Outbox retry                    -> keeps stable notification/revision/variant
SMTP accepted                   != delivered
Immutable content               != exactly-once SMTP
~~~

**Template registries and content versioning** are a production pattern that decouples **the decision to send an email** from **approved, verifiable content**. In Spring Framework Mail, business services raise notifications with a template key and contracted model; the registry resolves a published revision by tenant/locale/variant; a renderer like Thymeleaf renders content; `MimeMessageHelper` packages MIME; and `JavaMailSender` submits via SMTP. The governing rule is **published revisions are immutable, active pointers are mutable, and notifications pin exact revisions and required data per policy**. Adding approvals/audits, controlled caching, schema compatibility, canaries, rollbacks, emergency revocations, and a transactional outbox lets teams update copy flexibly without losing the ability to explain **which version, which data, and why** an email was permitted to go out.
