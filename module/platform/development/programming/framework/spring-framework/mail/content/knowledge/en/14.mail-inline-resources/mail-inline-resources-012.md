# Removing Unreferenced Resources

HTML emails can use logos, banners, charts, or icons embedded directly in the message. With **Spring Framework Mail**, these resources are typically added using `MimeMessageHelper.addInline(...)` and referenced by HTML via `cid:...` URLs. When a template has conditional branches, not every candidate resource appears in the rendered HTML. If the application still adds all potential resources, the email will carry MIME parts that are never referenced by the content.

**Removing unreferenced resources** means putting into the MIME message only those inline resources whose Content-ID is actually used in the final HTML. This shrinks email size, prevents unused images from appearing as attachments, limits unnecessary data exposure, and keeps the MIME structure aligned with the rendered content.

This lesson covers the relationship between HTML CIDs and MIME Content-IDs, detecting unused or missing resources, filtering resources before calling `addInline`, handling conditional templates and CSS, a Spring Boot example, testing, and common pitfalls.

## 1. How are inline resources linked to HTML?

Suppose an email has a logo:

```html
<html>
  <body>
    <img src="cid:company-logo" alt="Company logo">
    <h1>Hello!</h1>
  </body>
</html>
```

The HTML does not contain the image bytes. It only references a MIME part by Content-ID. When building the email, the application adds the image:

```java
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

In MIME, the image part may carry headers such as:

```text
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

[IMAGE_DATA]
```

Two identifiers must match:

| HTML | MIME / Spring |
|---|---|
| `src="cid:company-logo"` | `Content-ID: <company-logo>` |
| URI scheme `cid:` | `helper.addInline("company-logo", ...)` |
| Resource reference | MIME part containing the resource bytes |

`cid:company-logo` is a reference to the part with the matching Content-ID. It is not a filename, a server path, or the Message-ID of the entire email.

If the HTML does not reference `company-logo` yet the application still calls `addInline("company-logo", ...)`, the MIME message may carry an image part unused by the body. Depending on the mail client, that part may be ignored, displayed in the attachment list, or bloat the message without adding value for the recipient.

## 2. Which resources count as unreferenced?

Suppose a template can use three images:

- `brand-logo`: logo always shown.
- `promotion-banner`: shown only when a campaign has a banner.
- `order-chart`: shown only in report emails.

Resource list prepared by the application:

```text
brand-logo
promotion-banner
order-chart
```

Rendered HTML for an order confirmation email might contain only:

```html
<img src="cid:brand-logo" alt="Logo">
<h1>Your order is confirmed</h1>
```

In that case:
- `brand-logo` is referenced: must be added to MIME.
- `promotion-banner` is unreferenced: skip.
- `order-chart` is unreferenced: skip.

The set of resources to attach is **the intersection of the set of CIDs referenced by the HTML and the set of resources the application can provide**.

Let:
- `R` be the set of Content-IDs found in the rendered HTML;
- `A` be the set of Content-IDs present in the asset list prepared by the application.

Then:

```text
Inline resources to add = R ∩ A
Unused candidates       = A - R
Missing resources       = R - A
```

The three outcomes have distinct meanings:

| Outcome | Meaning | Handling |
|---|---|---|
| `R ∩ A` | Referenced by HTML and available in application assets | Add the resource to MIME. |
| `A - R` | Resource prepared but unused by HTML | Omit from the message. |
| `R - A` | HTML references a CID with no matching resource | Fail email render/build or use a pre-designed fallback. |

Do not silently ignore missing CIDs. If HTML still contains `cid:promotion-banner` without a matching part, the recipient may see a broken image. That is a consistency bug between template and assets that should be caught before sending.

## 3. Why remove redundant inline resources?

### 3.1. Reduce email size

Images embedded in MIME are typically Base64-encoded. The payload can grow by roughly one-third over raw bytes, excluding MIME headers and boundaries. If a template has several banners or charts yet uses only one image, adding them all inflates the email needlessly.

Large message sizes can:
- exceed the SMTP provider's message limit;
- increase transmission time;
- increase memory needed when constructing MIME;
- slow down email client download or processing.

### 3.2. Avoid unused resources appearing as attachments

Some mail clients display MIME parts not referenced by HTML as file attachments. Recipients may see unrelated images or assume the email carries extra documents.

`addInline` sets the disposition and Content-ID for the resource, yet does not guarantee every client hides unreferenced parts.

### 3.3. Avoid sending unnecessary data

An unreferenced resource might contain:
- internal graphics;
- charts carrying figures;
- image metadata;
- content generated specifically for a template branch;
- data the recipient has no need to see.

Even if the part never renders in the body, its bytes are still transmitted to the SMTP relay and may be stored in mailboxes or mail-processing systems. Therefore, dropping unused resources is also a **data-minimization** step.

### 3.4. Keep the MIME structure aligned with the content

If an email has one logo image, MIME should have that matching logo part. If an email has no banner, no banner part is needed. This consistency simplifies reading raw MIME, inspecting CIDs, and diagnosing issues.

### 3.5. Avoid unnecessary resource generation work

If a chart is meant only for report emails yet a service generates charts for every email type, CPU and RAM are wasted even when the image goes unused. You can filter early before building byte arrays, in addition to the final filter based on rendered HTML.

## 4. Distinguishing inline resources and regular attachments

Not every file in an email needs to be referenced by HTML.

| MIME part type | Spring API | How it is used | Filtered by HTML CIDs? |
|---|---|---|---|
| Inline image | `addInline(...)` | HTML references `cid:...` | Yes. |
| PDF attachment | `addAttachment(...)` | Recipient opens/downloads file independently | No. |
| CSV attachment | `addAttachment(...)` | Recipient opens data | No. |
| Plain-text body | `setText(...)` | Alternative content or message body | No. |
| HTML body | `setText(...)` | HTML content | Source for finding CIDs. |

**Remove only unreferenced inline resources.** Do not drop PDFs or CSVs simply because they do not appear in HTML; standalone attachments serve their own purpose and may be explicitly expected in the email.

If an email has both inline images and attachments:
- extract CIDs from the HTML;
- select the matching inline resources;
- call `setText(...)`;
- add the selected inline resources with `addInline(...)`;
- add standalone attachments with `addAttachment(...)`;
- send after finalizing MIME.

## 5. Why filter before calling addInline?

`MimeMessageHelper` provides APIs to add inline resources, for example:

```java
helper.addInline("brand-logo", logoResource, "image/png");
```

Do not assume the helper provides a public API equivalent to `removeInline(...)` to strip individual added resources. Once MIME parts are created, deleting directly depends on multipart structure and can corrupt the relationship between body and resources.

The simple, controllable approach is:
1. Render the complete HTML.
2. Collect CIDs referenced by the HTML.
3. Match against the resource registry provided by the application.
4. Raise an error if any resource is missing.
5. Call `addInline` only for referenced resources.
6. Build/send the MIME message once the filtered list is ready.

```text
Render HTML
    |
    v
Find cid: references
    |
    v
Compare with asset registry
    |
    +--> CID missing -> fail / fallback
    |
    v
Select referenced assets only
    |
    v
Create MimeMessageHelper
    |
    v
setText(...)
    |
    v
addInline(selected assets)
    |
    v
addAttachment(independent files)
    |
    v
send(...)
```

If existing code already called `addInline` for every asset before detecting unused resources, the safe remedy is usually to **build a new MimeMessage from the HTML and filtered resource list**. Mutate the multipart tree directly only if the application manages the MIME structure itself and has thorough tests for it.

## 6. Identifying CIDs referenced in HTML

CIDs can appear in multiple places, not only `img[src]`.

Common locations:
- `<img src="cid:logo">`;
- `background="cid:background-image"` attribute in legacy email HTML;
- inline CSS such as `style="background-image:url('cid:banner')"`;
- CSS inside `<style>` tags, if target email clients support that style rendering;
- other resource attributes explicitly permitted by the application.

Example:

```html
<img src="cid:brand-logo" alt="Logo">

<table background="cid:mail-background">
  <tr>
    <td style="background-image:url('cid:promo-banner')">
      Promotion details
    </td>
  </tr>
</table>
```

When collecting CIDs, understand **which HTML/CSS locations your application actually uses**. A regex matching every `cid:` substring across raw HTML can misinterpret plain text, comments, or code examples as referenced resources.

A good strategy:
- use an HTML parser to traverse elements and attributes;
- inspect URL attributes such as `src`, `background`, and `poster` if allowed by templates;
- inspect `style` attributes and `<style>` tags if CSS CIDs are used;
- handle `srcset` separately if the app uses CIDs in `srcset`;
- ignore HTTP/HTTPS URLs because they are external assets, not inline MIME parts;
- normalize CIDs under an application-controlled convention.

## 7. Consistent Content-ID conventions

Create CIDs from stable, simple server-defined tokens:

```text
brand-logo
promotion-banner
order-chart
footer-icon
```

HTML:

```html
<img src="cid:brand-logo" alt="Logo">
```

Java:

```java
helper.addInline(
    "brand-logo",
    logoResource,
    "image/png"
);
```

Do not put MIME angle brackets into HTML URLs. Use `cid:brand-logo` in HTML; `MimeMessageHelper` generates the Content-ID for the MIME part per its API.

### 7.1. Avoid duplicate CIDs

A message must not have multiple distinct inline resources sharing one Content-ID. If the registry contains two assets with the same CID, throw an error before sending.

A CID referenced multiple times in HTML usually needs only **one MIME part**:

```html
<img src="cid:brand-logo" alt="Header logo">
<img src="cid:brand-logo" alt="Footer logo">
```

Add `brand-logo` only once; both positions can reference the same part.

### 7.2. Distinguishing CID from resource name

The file `mail/logo-company.png` can use CID `brand-logo`:

```java
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo-company.png"),
    "image/png"
);
```

Filename, CID, and Content-Type are three distinct values:
- filename specifies where to read the resource;
- CID links HTML to the MIME part;
- Content-Type describes the data type.

Do not infer the CID from the filename if the template uses a different name.

### 7.3. CID URIs and encoding

In applications, restrict CIDs to a safe character set, such as letters, digits, dots, underscores, and hyphens. That makes mapping `cid:...` to registry keys simple and less error-prone.

The CID URI specification can represent certain characters with percent-encoding. If a system requires CIDs with special characters or `local-part@domain` addresses, use a parser/normalizer compliant with CID URI rules; do not apply a naive regex and assume it handles all cases. **In this lesson's examples, CIDs follow a simple ASCII convention.**

Do not blindly lowercase all Content-IDs if your convention or system treats the identifier part as case-sensitive. Use one consistent canonicalization rule across both templates and the registry.

## 8. Example registry and selector for inline resources

You can model a resource with a record:

```java
package com.example.mail;

import org.springframework.core.io.InputStreamSource;

public record InlineAsset(
    String contentId,
    InputStreamSource resource,
    String contentType
) {}
```

A render result holds HTML and the list of potentially usable resources:

```java
package com.example.mail;

import java.util.List;

public record RenderedEmail(
    String plainText,
    String htmlText,
    List<InlineAsset> inlineAssets
) {}
```

`inlineAssets` is the list of **candidate assets** for the template. It does not mean all of them must be added to MIME. The selector cross-checks them against CIDs in the HTML.

### 8.1. Using an HTML parser instead of arbitrary string matching

You can use Jsoup in the email processing or test module:

```groovy
dependencies {
    implementation 'org.jsoup:jsoup:<approved-version>'
}
```

`<approved-version>` is a placeholder; choose the version approved by your project. An HTML parser lets you traverse element attributes rather than searching raw text.

The following selector example supports CIDs in `src`, `background`, `poster`, inline CSS, and `<style>` tags. It uses a simple CID convention of letters, digits, dots, underscores, and hyphens:

```java
package com.example.mail;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;

public class InlineCidExtractor {

    private static final Pattern CID_ATTRIBUTE =
        Pattern.compile("^cid:([a-zA-Z0-9._-]+)$",
            Pattern.CASE_INSENSITIVE);

    private static final Pattern CSS_CID =
        Pattern.compile(
            "url\\\\(\\\\s*['\\\\"]?cid:([a-zA-Z0-9._-]+)['\\\\"]?\\\\s*\\\\)",
            Pattern.CASE_INSENSITIVE
        );

    public Set<String> extract(String html) {
        Document document = Jsoup.parseBodyFragment(html);
        Set<String> contentIds = new LinkedHashSet<>();

        for (Element element : document.getAllElements()) {
            collectAttribute(element.attr("src"), contentIds);
            collectAttribute(element.attr("background"), contentIds);
            collectAttribute(element.attr("poster"), contentIds);
            collectCss(element.attr("style"), contentIds);
        }

        for (Element style : document.select("style")) {
            collectCss(style.data(), contentIds);
        }

        return contentIds;
    }

    private static void collectAttribute(
            String value, Set<String> contentIds) {

        if (value == null || value.isBlank()) {
            return;
        }

        String candidate = value.trim();
        if (!candidate.regionMatches(true, 0, "cid:", 0, 4)) {
            return;
        }

        Matcher matcher = CID_ATTRIBUTE.matcher(candidate);
        if (!matcher.matches()) {
            throw new IllegalArgumentException(
                "Invalid CID URI: " + candidate
            );
        }

        contentIds.add(matcher.group(1));
    }

    private static void collectCss(
            String css, Set<String> contentIds) {

        if (css == null || css.isBlank()) {
            return;
        }

        Matcher matcher = CSS_CID.matcher(css);
        while (matcher.find()) {
            contentIds.add(matcher.group(1));
        }
    }
}
```

This selector is an example for a supported template syntax subset, not a full HTML/CSS parser for all emails:
- If using `srcset`, parse candidate URL lists separately.
- If CSS comes from external stylesheets or uses complex syntax, extend the parser accordingly.
- If the app allows CIDs in other attributes, add those attributes to the policy.
- If HTML contains `cid:` inside plain text or comments, the selector does not treat it as a referenced resource.
- If using CID URIs with percent-encoding or characters outside the allowlist, replace the simple normalizer with a compliant implementation.

Do not run regex across entire HTML files as a replacement for a parser; regex here operates only on CSS `url(...)` values already extracted from CSS context.

### 8.2. Matching against the registry and dropping unused resources

```java
package com.example.mail;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class InlineAssetSelector {

    private final InlineCidExtractor extractor;

    public InlineAssetSelector(InlineCidExtractor extractor) {
        this.extractor = extractor;
    }

    public List<InlineAsset> select(
            String html,
            List<InlineAsset> candidates) {

        Set<String> referenced = extractor.extract(html);

        Map<String, InlineAsset> registry = new LinkedHashMap<>();
        for (InlineAsset asset : candidates) {
            InlineAsset previous =
                registry.putIfAbsent(asset.contentId(), asset);

            if (previous != null) {
                throw new IllegalArgumentException(
                    "Duplicate Content-ID: " + asset.contentId()
                );
            }
        }

        // HTML references a CID with no matching resource:
        // this is a template/asset bug, do not send a broken email.
        List<String> missing = referenced.stream()
            .filter(cid -> !registry.containsKey(cid))
            .toList();

        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                "Missing inline resources for CIDs: " + missing
            );
        }

        // Preserve first-appearance order in HTML, add each CID once.
        List<InlineAsset> selected = new ArrayList<>();
        for (String cid : referenced) {
            selected.add(registry.get(cid));
        }

        return List.copyOf(selected);
    }
}
```

Result:
- CIDs referenced by HTML are selected.
- Duplicate CIDs in the candidate list are rejected.
- CIDs present in HTML without a matching resource raise an error.
- Candidates not referenced by HTML do not appear in the returned list.
- A CID appearing multiple times in HTML is added only once thanks to `Set`.

In a real application, you can record metrics for candidate count, selected count, and unused count. Never log image bytes or sensitive data for diagnostics.

## 9. Integrating the selector with JavaMailSender

Example service accepting a `RenderedEmail`, selecting inline resources first, and then building the MIME message:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.List;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlMailService {

    private final JavaMailSender mailSender;
    private final InlineAssetSelector assetSelector;

    public HtmlMailService(
            JavaMailSender mailSender,
            InlineAssetSelector assetSelector) {
        this.mailSender = mailSender;
        this.assetSelector = assetSelector;
    }

    public void send(
            String recipient,
            String subject,
            RenderedEmail rendered) throws MessagingException {

        // 1. Select only resources actually referenced by the HTML.
        List<InlineAsset> selected = assetSelector.select(
            rendered.htmlText(),
            rendered.inlineAssets()
        );

        // 2. Create MIME only after verifying a valid asset list.
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);

        // 3. Set the body before adding inline resources.
        helper.setText(
            rendered.plainText(),
            rendered.htmlText()
        );

        // 4. Add only referenced CIDs.
        for (InlineAsset asset : selected) {
            helper.addInline(
                asset.contentId(),
                asset.resource(),
                asset.contentType()
            );
        }

        // 5. Send after finalizing MIME.
        mailSender.send(message);
    }
}
```

`MULTIPART_MODE_RELATED` fits HTML with related inline resources. If the email also carries standalone attachments such as PDFs, choose `MULTIPART_MODE_MIXED_RELATED` and call `addAttachment` separately after setting the body/inline parts in the proper structure.

**Order matters:** `setText(...)` before `addInline(...)`. The selector only decides which resources are added; it does not replace MIME body construction order.

### 9.1. Why select resources before creating MimeMessage?

Pre-selecting offers several benefits:
- if a CID is missing, the error triggers before sending;
- no creating MIME parts only to figure out how to remove them;
- selected asset counts can be measured before building the message;
- the selector is easy to unit-test independently of SMTP;
- reduces risk of sending a message whose HTML points to missing resources.

If generating a resource is expensive, even better is **generating asset bytes only after knowing it is needed**. For example, do not render a 2 MB chart if the rendered HTML has no tag referencing that chart.

## 10. Conditional templates and unused resources

Suppose a template has a logo, banner, and chart:

```html
<img src="cid:brand-logo" alt="Logo">

<div th:if="¤{showPromotion}">
  <img src="cid:promotion-banner" alt="Promotion">
</div>

<div th:if="¤{showChart}">
  <img src="cid:order-chart" alt="Order chart">
</div>
```

When rendered:
- `showPromotion=false` removes CID `promotion-banner` from HTML.
- `showChart=true` includes CID `order-chart` in HTML.
- `brand-logo` is always referenced.

The candidate list may contain all three resources, yet the selector returns only:
```text
brand-logo
order-chart
```

The banner is dropped because it does not appear in the resulting HTML.

### 10.1. Keeping template conditions and the registry in sync

There are two ways to organize this:

**Approach A — Registry holds all potentially used assets.** Render HTML first, run the selector to find CIDs, and filter the registry. This is convenient when asset count is small and resources open lazily.

**Approach B — Renderer registers assets only for active branches.** When `showPromotion` is true, the renderer adds the banner to the list; when false, it skips it. You can still run the selector afterward to guarantee HTML and registry match.

Approach B avoids unnecessary candidate creation work. However, if Java conditions and template conditions are written separately, they can drift apart. Use the same model/decision object to drive both HTML and the registry.

### 10.2. Generate bytes only after confirming usage

Instead of rendering the chart for every email:

```java
List<InlineAsset> assets = new ArrayList<>();

if (showChart) {
    byte[] chartBytes = chartRenderer.render(reportData);
    assets.add(new InlineAsset(
        "order-chart",
        new ByteArrayResource(chartBytes),
        "image/png"
    ));
}
```

If `showChart` is false, the app never renders the chart. The selector still remains useful as a final check because HTML templates can change or contain other conditional branches.

## 11. CSS and CID references outside img[src]

Not every inline resource appears inside `<img>`. Some email templates use:

```html
<td style="background-image:url('cid:mail-background')">
  Content
</td>
```

Or:

```html
<style>
  .hero {
    background-image: url("cid:hero-banner");
  }
</style>
```

If the extractor scans only `img[src]`, it will miss these two CIDs and wrongly drop needed resources.

There are three strategies:
1. **Constrain template syntax:** allow CIDs only in `img[src]`, keeping the extractor simple.
2. **Intentionally support CSS CIDs:** parse `style` attributes and `<style>` tags while verifying target mail clients support that rendering.
3. **Use an asset registry built alongside the template model:** the template/renderer returns the list of used assets, while still checking consistency against output HTML.

If using external CSS, `srcset`, or client-specific attributes, document them explicitly in the template contract and add tests. Never assume an extractor scanning only `src` covers every HTML pattern.

### 11.1. srcset

Example:

```html
<img
  src="cid:logo-small"
  srcset="cid:logo-small 1x, cid:logo-large 2x"
  alt="Logo">
```

If the application uses CIDs in `srcset`, parse every candidate URL in that attribute. Checking only `src` misses `logo-large`; dropping that resource could leave clients that pick the 2x image without a matching MIME part.

If target email clients do not support this usage or the app does not need responsive CID images, restrict templates to a single plain `src`. Explicitly supported syntax is usually easier to maintain than an extractor trying to guess arbitrary HTML.

## 12. Handling missing CIDs and invalidated assets

There are two mismatch scenarios:

### 12.1. HTML references a CID missing from the registry

For instance, HTML has `cid:brand-logo` yet the registry only has `footer-icon`.

This is an error that must be caught:
- the template may use the wrong CID name;
- an asset was forgotten during registration;
- render conditions are out of sync;
- the resource failed to load or was dropped by an earlier step.

Pick one intentional behavior:
- **Fail before send:** right for logos or mandatory images.
- **Render fallback:** remove the image tag or replace it with text when the image is optional.
- **Re-render:** if the asset can be retrieved from a trusted source, regenerate HTML/registry and re-validate.

Do not send raw HTML with a missing CID if the image is an important part of the message.

### 12.2. Registry has an asset unused by HTML

This is an unreferenced candidate. Do not add it to MIME. If the resource has not been read yet, skip it without loading bytes.

If the resource was already created:
- remove its reference from the send list;
- release buffers/handles if possible;
- avoid storing unused bytes in long-lived caches needlessly;
- emit metrics for total candidates and selected count to detect templates or renderers preparing too many assets.

### 12.3. File deleted or failing after selector runs

A resource might exist in the registry yet fail to open a stream when Jakarta Mail reads it. Treat this as a MIME-creation failure rather than assuming the selector proved the bytes were readable.

For critical resources:
- use sources that can open fresh streams;
- verify resource existence before building the message when appropriate;
- handle exceptions from `addInline` or `send`;
- do not send a message whose body references an image whose resource could not be read.

## 13. Re-readable resource sources

`MimeMessageHelper.addInline(...)` accepts an `InputStreamSource`. The source should provide a fresh stream each time it is read, especially when MIME construction and sending access content more than once.

Commonly suitable sources:
- `ClassPathResource` for static images inside JARs;
- `ByteArrayResource` for pre-generated byte arrays;
- `FileSystemResource` for re-openable files;
- custom `InputStreamSource` backed by a factory opening fresh streams.

Avoid a source returning the same consumed `InputStream`:

```java
InputStream input = storage.openStream(assetId);
InputStreamSource oneShot = () -> input;
```

Instead:

```java
InputStreamSource repeatable =
    () -> storage.openNewStream(assetId);
```

`storage.openNewStream` is an illustrative API; each call must return a new stream from the start. For small payloads, `ByteArrayResource` is simpler. For large payloads, use re-openable storage with lifecycle management.

## 14. Testing the selector and MIME output

Tests should cover both CID selection and the resulting MIME after adding resources.

### 14.1. Testing removal of unreferenced resources

Suppose HTML uses only `brand-logo` while candidates include logo, banner, and chart:

```java
@Test
void selectsOnlyReferencedInlineAssets() {
    String html = """
        <html><body>
          <img src="cid:brand-logo" alt="Logo">
        </body></html>
        """;

    List<InlineAsset> candidates = List.of(
        asset("brand-logo"),
        asset("promotion-banner"),
        asset("order-chart")
    );

    List<InlineAsset> selected =
        selector.select(html, candidates);

    assertThat(selected)
        .extracting(InlineAsset::contentId)
        .containsExactly("brand-logo");
}
```

`asset(...)` is a test fixture creating a small resource, not a built-in Spring method.

### 14.2. Testing repeated CIDs

```java
@Test
void addsOneAssetForRepeatedCidReferences() {
    String html = """
        <img src="cid:brand-logo">
        <img src="cid:brand-logo">
        """;

    List<InlineAsset> selected =
        selector.select(html, List.of(asset("brand-logo")));

    assertThat(selected).hasSize(1);
}
```

A single MIME part can be referenced by multiple locations in HTML.

### 14.3. Testing missing CIDs

```java
@Test
void failsWhenHtmlReferencesUnknownCid() {
    String html = "<img src=\\"cid:missing-logo\\">";

    assertThatThrownBy(() ->
        selector.select(html, List.of(asset("brand-logo")))
    ).isInstanceOf(IllegalStateException.class);
}
```

This test ensures the app does not silently send emails with broken images.

### 14.4. Testing CSS references

```java
@Test
void detectsCidInInlineCss() {
    String html = """
        <div style="background-image:url('cid:hero-banner')">
          Hello
        </div>
        """;

    List<InlineAsset> selected =
        selector.select(html, List.of(asset("hero-banner")));

    assertThat(selected)
        .extracting(InlineAsset::contentId)
        .containsExactly("hero-banner");
}
```

If the application uses `srcset` or complex CSS stylesheets, add dedicated tests for every supported syntax.

### 14.5. Testing that MIME contains no extra parts

After the selector returns the filtered list, build a `MimeMessage`, call `setText`, and add the selected resources. In tests, save MIME changes and traverse multiparts to verify:
- exact inline part count;
- each part has the matching Content-ID;
- no CID from unreferenced candidates is present;
- extracted part bytes match fixture bytes;
- every CID in HTML has a corresponding MIME part.

Do not merely assert part count if the message also contains `multipart/alternative` or standalone attachments. Traverse the MIME structure following actual nesting and distinguish inline parts from attachments.

## 15. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Email has image absent from HTML yet listed as attachment | Added all candidate assets | Filter by CIDs present in rendered HTML. |
| HTML has `cid:logo` yet image is missing | No matching MIME part or mismatched CID | Compare CID URI and Content-ID. |
| Banner disappears when a condition turns false or true | Extractor misses CSS/attribute reference | Support the exact syntax used or restrict templates. |
| Image shows in body yet extra parts still exist | Added unused candidates at the same time | Add only selected resources; inspect raw MIME. |
| Email is unusually large | Attached all possible images or oversized images | Filter assets, generate lazily, resize/optimize. |
| Duplicate CIDs | Registry has two resources with the same ID | Reject duplicate CIDs before building message. |
| HTML references CID with no asset | Template and registry out of sync | Fail before send or render fallback. |
| Image breaks in only one template branch | Asset list does not match render condition | Share condition model and run selector on final HTML. |
| CSS background missing | Scanned only `img[src]` | Scan CSS CIDs if templates/clients support them. |
| 2x image does not show | CID in `srcset` not collected | Parse each srcset candidate or avoid CID there. |
| Resource selected yet send fails | Stream cannot reopen or storage failed | Use repeatable InputStreamSource, handle read errors. |
| Email still carries image despite template omitting it | Added parts before filtering | Select resources before addInline; rebuild message if needed. |

## 16. Performance and operational observability

You can track non-sensitive metrics:
- number of candidate inline assets supplied by the renderer;
- number of CIDs actually referenced by HTML;
- number of dropped resources;
- number of missing CIDs;
- total bytes of selected assets;
- time spent generating assets and building MIME;
- count of resource-open failures.

Example log:

```text
mail_template=order-confirmation
inline_candidates=4
inline_referenced=2
inline_selected=2
inline_unused=2
mime_build_status=success
```

Never log image bytes, Base64, or HTML content containing personal data/tokens. CIDs are generally not secrets, yet should still be technical identifiers containing no personal info.

If `inline_unused` is consistently high, the renderer may be creating too many resources or templates have many optional branches. Optimize asset generation conditionally to save CPU/RAM even before the selector drops them.

With multiple concurrent sending workers:
- limit the number of images generated per email;
- cap total MIME size;
- never share mutable `MimeMessage` or `MimeMessageHelper` across threads;
- create a separate message per send;
- cache static resources if safe, yet never cache assets containing private data across recipients.

## 17. Practice exercises

### Exercise 1 — Selecting the right resources

HTML contains `cid:logo` and `cid:chart`. The registry has `logo`, `chart`, and `banner`. Determine which set is added and which is dropped.

**Hint:** add `logo` and `chart`; drop `banner`.

### Exercise 2 — Detecting missing CIDs

HTML references `cid:promotion`, yet the registry lacks that CID. Choose appropriate behavior for an optional banner versus a mandatory logo. Write tests asserting errors or fallbacks for each case.

### Exercise 3 — Repeated CID

An HTML template uses the same logo in header and footer. Demonstrate that the selector returns only one asset and MIME needs only one part with that Content-ID.

### Exercise 4 — CSS background

A template uses `background-image:url('cid:hero')`. Extend the extractor to detect CSS CIDs and add tests for single quotes, double quotes, and whitespace.

### Exercise 5 — srcset

HTML has two candidates `cid:small-logo` and `cid:large-logo` in `srcset`. Decide whether the application supports this syntax. If yes, parse each URL; if no, update the template contract to use only `src`.

### Exercise 6 — Skipping unnecessary asset generation

A chart takes 300 ms to render and is used only in report emails. Pass the `showChart` decision into the renderer to avoid generating bytes for non-report emails, then still run the selector to verify CID/registry consistency.

### Exercise 7 — Distinguishing attachments

An email has `cid:logo` and a standalone `invoice.pdf` attachment. Drop an unused banner while keeping the PDF even though the PDF does not appear in HTML. Explain why only inline resources are filtered by CID.

### Exercise 8 — Inspecting raw MIME

Create a message with two inline candidates where HTML references only one. Save the MIME in a test and verify the unreferenced resource's part does not exist.

## 18. Summary

In Spring Framework Mail, `MimeMessageHelper.addInline(...)` adds a MIME part with a Content-ID for HTML to reference via `cid:...`. When templates have multiple branches or the registry holds many potential assets, avoid adding all resources to every email.

**Render HTML first, collect actually referenced CIDs, match against the registry, fail if any are missing, and call `addInline` only for selected resources.** Use an HTML parser to handle the exact attributes/CSS supported by templates, keep CIDs unique, ensure resources can open streams, and verify MIME in tests. Filter only inline resources; standalone attachments are kept per business requirements.

This approach reduces message size, avoids transmitting unnecessary data, and keeps MIME messages consistent with what recipients actually see.
