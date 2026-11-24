# Referrer-Policy, Permissions-Policy, and Choosing Based on Application Needs

**Context:** Spring Security **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, Spring Security 6.x. Two HTTP response headers, `Referrer-Policy` and `Permissions-Policy`, help reduce navigation information leaks and restrict usage of sensitive browser APIs. They solve **two distinct security problems**: one governs **originating page information sent outbound**, and the other governs **which browser features are permitted to be used**.

## 1. The big picture

When a user opens `https://app.example.com/account?tab=security` and clicks a link to another website, the browser may send a request containing a `Referer` header identifying the previous page. If the full URL is sent, path/query components may disclose information that should not be shared.

On that same page, JavaScript or an iframe might attempt to access the camera, microphone, geolocation, fullscreen, or other web platform capabilities. Not every feature should be enabled on every page.

The two headers handle two distinct flows:

| Response header | Primary effect | Example |
| --- | --- | --- |
| `Referrer-Policy` | Controls how much source URL information appears in the **`Referer`** header when the browser navigates or loads resources. | Send only the origin `https://app.example.com/` to partners instead of the URL with query params. |
| `Permissions-Policy` | Restricts which browser features the current document and embedded documents may use. | An admin page does not need a webcam: `camera=()`. |

**Easily confused spelling:** The traditional HTTP request header is spelled `Referer` (one **r** between *refe* and *er*) for historical reasons; the response policy header is `Referrer-Policy` (full spelling). In JS there is also `document.referrer`.

Both policies are **supported and enforced by browsers**. Non-browser HTTP clients may ignore them. They **do not replace authentication, authorization, CSRF, XSS/CSP, CORS, or HTTPS encryption**.

## 2. Referrer-Policy: what does the browser send in Referer?

An **origin** is the tuple `scheme + host + port`. For example:

- `https://app.example.com/user/42` and `https://app.example.com/reports` are **same origin**.
- `https://app.example.com` and `https://api.example.com` are **cross-origin** because the hosts differ.
- `http://localhost:8080` and `http://localhost:3000` are **cross-origin** because the ports differ.
- `https://example.com` and `http://example.com` are **cross-origin** because the schemes differ.

Suppose the source document is:

```text
https://app.example.com/orders/123?view=detail
```

This page navigates to `https://partner.example.net/pay`:

- A policy allowing **full URL** may cause the destination to receive `Referer: https://app.example.com/orders/123?view=detail`.
- A policy allowing **origin** only will cause the destination to receive `Referer: https://app.example.com/`.
- The `no-referrer` policy sends no `Referer` header.

**URL fragments** such as `#section` are not included in `Referer`; usernames/passwords in URLs are also stripped per referrer processing rules. Even so, paths and queries can hold IDs, search terms, and business parameters; it is best **never to put session tokens, passwords, or secrets in URLs** in the first place.

### 2.1 Key policy values

| `Referrer-Policy` value | Same-origin navigation/load | Cross-origin navigation/load | HTTPS down to HTTP | When to consider |
| --- | --- | --- | --- | --- |
| `no-referrer` | No `Referer` | No `Referer` | No `Referer` | Highly sensitive pages; prioritize minimizing source disclosure. |
| `same-origin` | Sends source URL (no fragment) | No `Referer` | Not sent cross-origin | Want referrer details only for internal flows. |
| `strict-origin-when-cross-origin` | Sends source URL (no fragment) | Sends **origin** only | No `Referer` | Balanced choice for many applications. |
| `strict-origin` | Origin only | Origin only | No `Referer` | Want to hide paths/queries even internally. |
| `origin` | Origin only | Origin only | Policy does not block on downgrade | Domain-level attribution; weigh downgrade risk carefully. |
| `no-referrer-when-downgrade` | Sends source URL | Sends source URL | Not sent on downgrade | Legacy; risks exposing paths/queries to other HTTPS sites. |
| `unsafe-url` | Sends source URL | Sends source URL | May send even on downgrade | Avoid for URLs containing sensitive information. |

**`strict-origin-when-cross-origin`** is the default in many modern browsers when no explicit policy is set. However, applications should still **configure it intentionally** based on security needs and testing rather than relying on environment defaults.

Example with `strict-origin-when-cross-origin`:

```text
Source document: https://app.example.com/orders/123?view=detail

→ https://app.example.com/help
  Referer: https://app.example.com/orders/123?view=detail

→ https://analytics.partner.example/collect
  Referer: https://app.example.com/

→ http://legacy.partner.example/collect
  (No Referer because HTTPS → HTTP)
```

This is an **illustration of browser behavior under the policy**; `Referer` may also be absent due to element attributes, privacy settings, or deployment environments.

### 2.2 Where to place the policy?

Set the response header on the **source document** loaded by the browser, such as an HTML page:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Referrer-Policy: strict-origin-when-cross-origin
```

The policy governs **subsequent requests originating from that document**. If you only put the header on JSON API responses while the main HTML is served by a CDN or another application, you may not have configured the policy for page navigation links. Inspect the **actual HTML response** in DevTools.

Narrower configuration points exist and are used when needed:

```html
<!-- Document-wide policy if no appropriate response header is set. -->
<meta name="referrer" content="no-referrer">

<!-- Only a single link omits the referrer. -->
<a href="https://external.example/path" rel="noreferrer">External page</a>

<!-- Per-element referrer policy for a supporting resource/element. -->
<img src="https://images.example/photo.png"
     referrerpolicy="no-referrer"
     alt="Illustrative image">
```

JavaScript `fetch()` also supports the `referrerPolicy` option:

```javascript
fetch("https://api.example.net/public", {
  referrerPolicy: "no-referrer"
});
```

Do not treat `meta` tags or individual element options as the default replacement for a server-wide application policy. Prefer setting the policy on the document's **HTTP response** and overriding only on specific links/resources with clear justification.

### 2.3 What Referrer-Policy does not do

- **Does not erase** URLs from browser history, your own server access logs, internal analytics, or the address bar.
- **Does not encrypt** query contents or protect secrets embedded in URLs; use HTTPS and keep sensitive data out of URLs.
- **Does not block requests** sent to third parties; it only limits source URL details in `Referer`. To control allowed connection destinations, consider CSP `connect-src`, `img-src`, etc.
- **Does not change** CORS rules or a request's `Origin` header. A request may lack `Referer` while still carrying `Origin`.
- **Is not** a CSRF defense filter. CSRF verification requires dedicated mechanisms; never rely on `Referer` as a trustworthy login/origin credential.
- **Cannot retroactively delete** `document.referrer` already received by a destination page from a previous navigation: it must be controlled from the **source document**.

## 3. Permissions-Policy: restricting browser capabilities

`Permissions-Policy` is an HTTP response header specifying which **features** a document—and under proper conditions, child iframes—may use. It can apply to features such as:

- `camera`: camera API.
- `microphone`: microphone API.
- `geolocation`: location.
- `fullscreen`: fullscreen mode.
- `payment`: Payment Request API in supporting browsers.

Feature and directive support **varies by browser and version**; do not assume every feature name is enforced uniformly. Configure policies around actually used APIs and test on target browsers.

### 3.1 Common allowlist syntax

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
```

Interpretation:

- `camera=()`: **no document within this policy's scope** may use the camera via the restricted capability.
- `microphone=()`: same for the microphone.
- `geolocation=(self)`: permits same-origin documents within policy scope; **does not automatically approve user location prompts**. The browser must still satisfy secure context, user permission, and other rules.

Syntax:

| Syntax | General meaning | Risks / notes |
| --- | --- | --- |
| `camera=()` | Empty allowlist: blocks camera. | Blocks the main app as well if it genuinely needs the camera. |
| `camera=(self)` | Allows same-origin documents to use camera, if other conditions permit. | Does not replace the user permission prompt. |
| `geolocation=(self "https://maps.partner.example")` | Adds a specific origin to the candidate allowlist. | For cross-origin iframes, proper delegation/`allow` attributes are also needed. |
| `microphone=*` | Wildcard for origins considered by the policy mechanism. | Too broad for most apps; avoid using. |

**Syntax note:** `self` is an unquoted token; a specific origin inside the header list is **enclosed in double quotes**. Parentheses `()` signify an empty set, not a comment marker. Header directives are separated by commas.

`Permissions-Policy` **does not mean "granting camera/location access"**. Even with `camera=(self)`, the browser still requires an HTTPS secure context, user consent, and API-specific conditions. Conversely, if the policy blocks `camera=()`, JavaScript calls can be rejected even if the user previously granted camera permission to the site.

### 3.2 Iframes and delegating permissions to embedded documents

Suppose a dashboard at `https://app.example.com` embeds a map widget from `https://maps.partner.example`:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(self "https://maps.partner.example")
```

The parent HTML may contain:

```html
<iframe
  src="https://maps.partner.example/widget"
  allow="geolocation"
  title="Map">
</iframe>
```

Points to remember:

1. The parent response header must allow the iframe's origin in the appropriate **feature allowlist**.
2. For **cross-origin** iframes, delegation via the iframe's `allow` attribute is required according to browser/feature policy. Having only the header allowlist may not suffice.
3. The effective policy is governed by the **intersection of constraints** from ancestors, the iframe container, and the embedded document's own policy; a child cannot elevate permissions denied by a parent.
4. Some features require a secure context, user gesture, or user consent even after the policy permits them.

**Distinction from anti-clickjacking:** `Permissions-Policy` controls **web platform capabilities**, not whether a site may be embedded in an iframe. To control who **may embed your page**, look at CSP `frame-ancestors`, `X-Frame-Options`, and related constraints. To control where your iframes load from, use CSP `frame-src` and application policy.

The older `Feature-Policy` header is the predecessor mechanism; for new applications prefer `Permissions-Policy` and verify actual support on target browsers. Do not rely on `<meta http-equiv="Permissions-Policy">` as a substitute for HTTP headers: meta tag support does not match response headers.

## 4. Choosing policies by application needs, not one config for all

Never copy another system's configuration verbatim before knowing whether the product uses camera, microphone, geolocation, or outbound analytics.

| Application type | Suggested `Referrer-Policy` | Suggested `Permissions-Policy` | Rationale and what to test |
| --- | --- | --- | --- |
| Marketing site / docs with external links | `strict-origin-when-cross-origin` | `camera=(), microphone=(), geolocation=()` if unused | Keeps origin-level attribution; reduces API surface. |
| Internal dashboard with sensitive info in URLs | `same-origin` or `no-referrer` | Block camera/mic/geo if unused | Prevents leaking paths/queries to third parties; verify whether analytics/SSO flows depend on referrer. |
| Healthcare/finance app with many outbound links | Often consider `no-referrer` | Block unnecessary features by default | Minimizes source info; verify business flows needing internal referrers. |
| Map application needing location | `strict-origin-when-cross-origin` or stricter | `geolocation=(self), camera=(), microphone=()` | Enables only needed feature; browser still prompts user for location. |
| Same-origin video conferencing app | Choose per actual navigation flows | `camera=(self), microphone=(self)` | Blocking all would break video calls. |
| Portal embedding partner widgets | Check which URLs may leak via partner navigation | Add only **trusted partner origins** for needed features + iframe `allow` | Test delegation and browser support; avoid wildcards. |

**Decision process:**

1. List which pages use which features (camera, microphone, geolocation, fullscreen, payment, iframes) and which external services users navigate to.
2. Choose `Referrer-Policy` based on **the maximum source info allowed to be shared**. If no referrer needs to go anywhere, `no-referrer` makes sense; if origin-level analytics are needed, `strict-origin-when-cross-origin` is often more balanced.
3. For `Permissions-Policy`, **explicitly block unused features**, permit only genuinely required origins, and avoid wildcards without justification.
4. Test real behavior with same-origin pages, cross-origin pages, iframes, target browsers, HTTPS, and user permissions. Monitor feature errors after deployment.

For example, a website with checkout functionality but no camera: do not assume every payment app must permit `payment`. Enable it only if actually using the Payment Request API; payments handled via provider redirects/iframes have different requirements and must be checked against specific integration policies.

## 5. Spring Security Servlet: configuring both headers on SecurityFilterChain

Spring Security can manage multiple response security headers via `HttpSecurity.headers`. Both `Referrer-Policy` and `Permissions-Policy` should be **explicitly configured**; do not assume default headers already supply the exact policies your application wants.

The example below uses **Spring Security 6.x** DSL APIs running on Spring Boot 3.x. The demo application:
- Uses `strict-origin-when-cross-origin` for outbound navigation.
- Blocks camera/microphone, allowing geolocation only for same origin.
- Permits demo GETs to inspect headers; in real applications, apply authentication/authorization rules as needed.

**`src/main/java/com/example/httpheaders/SecurityConfig.java`**

```java
package com.example.httpheaders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth ->
                auth.anyRequest().permitAll());

        http.headers(headers -> {
            headers.referrerPolicy(referrer -> referrer.policy(
                ReferrerPolicyHeaderWriter.ReferrerPolicy
                    .STRICT_ORIGIN_WHEN_CROSS_ORIGIN
            ));

            headers.permissionsPolicy(permissions -> permissions.policy(
                "camera=(), microphone=(), geolocation=(self)"
            ));
        });

        return http.build();
    }
}
```

**`src/main/java/com/example/httpheaders/DemoController.java`**

```java
package com.example.httpheaders;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/demo/info")
    public Map<String, String> info() {
        return Map.of("status", "ok");
    }
}
```

**`src/main/java/com/example/httpheaders/HttpHeadersApplication.java`**

```java
package com.example.httpheaders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpHeadersApplication.class, args);
    }
}
```

The files above **do not compile with plain `javac`** due to Spring dependencies. Create a Spring Boot 3.x project via Spring Initializr, selecting **Java 17+**, Spring Web, and Spring Security. Match the package structure above and use the generated Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell, run `.\gradlew.bat bootRun`. By default, the app listens on port `8080` and returns JSON from `GET /demo/info`.

Verify:

```bash
curl -i http://localhost:8080/demo/info
```

The relevant headers and body will resemble:

```http
HTTP/1.1 200
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
Content-Type: application/json

{"status":"ok"}
```

An actual server may add other headers and change display ordering. The two header values above are the configuration results to verify; `200` and JSON are the demo endpoint output.

**Note on SecurityFilterChain scope:** These headers are emitted for responses passing through this filter chain. If the application has multiple `SecurityFilterChain` beans with different matchers/`@Order`, confirm **which chain applies to HTML, APIs, and related paths**. If HTML is served by nginx/CDN, Spring backend configuration will not inject headers onto CDN-served HTML pages: configure the layer that actually returns that response.

### 5.1 Environment-specific policy variants

For an ultra-sensitive dashboard, replace the Referrer-Policy block with:

```java
headers.referrerPolicy(referrer -> referrer.policy(
    ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER
));
```

If the website does not use geolocation, change the policy to:

```java
headers.permissionsPolicy(permissions -> permissions.policy(
    "camera=(), microphone=(), geolocation=()"
));
```

If the application itself needs camera and microphone:

```java
headers.permissionsPolicy(permissions -> permissions.policy(
    "camera=(self), microphone=(self), geolocation=()"
));
```

These snippets are **replacement variants** for part of `SecurityConfig`, **not** statements to append after the existing config to create conflicting header values.

In large systems, policies may be selected per profile or per route/app group, but ensure you **do not emit multiple conflicting `Referrer-Policy`/`Permissions-Policy` headers** from Spring, gateways, and CDNs; inspect the **final HTTP response** actually reaching the browser.

### 5.2 Avoid disabling default security headers

`http.headers(...)` is the integration point for policies; this example **does not call** `defaultsDisabled()` and does not disable `headers` globally. Calling `defaultsDisabled()` and enabling only the two new policies can accidentally drop other default security headers (such as MIME-sniffing or framing protections). Modify only what is needed without weakening baseline protections.

Some browsers may ignore `Permissions-Policy` directives they do not support. Seeing the header in Network **is not enough** to conclude a feature is blocked: test the actual API or iframe on target browsers.

## 6. Verifying with automated tests and browsers

Verify at **two layers**: (1) does the server emit the right headers, and (2) does the browser enforce the intended behavior.

### 6.1 Spring MVC test for headers

With the `spring-boot-starter-test` dependency, add:

**`src/test/java/com/example/httpheaders/SecurityHeadersTest.java`**

```java
package com.example.httpheaders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTest {

    @Autowired
    MockMvc mvc;

    @Test
    void sendsSecurityPolicyHeaders() throws Exception {
        mvc.perform(get("/demo/info"))
           .andExpect(status().isOk())
           .andExpect(header().string(
               "Referrer-Policy", "strict-origin-when-cross-origin"))
           .andExpect(header().string(
               "Permissions-Policy",
               "camera=(), microphone=(), geolocation=(self)"));
    }
}
```

Use the project's Gradle wrapper:

```bash
./gradlew test
```

Windows: `.\gradlew.bat test`. The test only verifies **that the filter chain emits the proper headers on the tested endpoint**. It does not prove browsers send `Referer` properly or block camera/geo across all browsers; run appropriate manual/integration tests.

### 6.2 Testing Referrer-Policy properly

1. Serve a **source HTML page** `https://app.example.com/page` and ensure the **HTML response** carries the `Referrer-Policy` header under test.
2. Place a link from that page to another test origin you control, e.g., `https://receiver.example.net/inspect`. The receiver should safely record incoming `Referer` headers in a test environment (without collecting real user data).
3. With `strict-origin-when-cross-origin`, on an HTTPS → HTTPS cross-origin request, the receiver should see **only the origin** of the source page. With `no-referrer`, the receiver should see no `Referer`.
4. Add a **same-origin** link to verify the difference between `same-origin` and `strict-origin-when-cross-origin`. If testing HTTPS → HTTP downgrades, use an appropriate test environment and note browsers may block or impose other restrictions.
5. In DevTools → **Network → Request Headers**, inspect `Referer` on the **outgoing navigation request**, rather than looking only at response headers on the destination page. If the header is missing, check `rel=noreferrer`, `referrerpolicy` attributes, privacy settings, and browser behavior.

Do not run `curl -H "Referer: ..."` to claim a `Referrer-Policy` is enforced: `curl` merely sends whatever header you manually specify and does not simulate browser policy.

### 6.3 Testing Permissions-Policy properly

Use DevTools → **Network → Response Headers** to confirm the header. Then test actual browser features:

```javascript
async function tryCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true
    });
    console.log("Camera available for this document");
    stream.getTracks().forEach(track => track.stop());
  } catch (error) {
    console.log(error.name, error.message);
  }
}

tryCamera();
```

While `camera=()` is in effect, browsers supporting this feature will deny camera access to the document even though the JavaScript API exists. Specific errors and console messages depend on the browser; `NotAllowedError` is a common outcome. Over **plain insecure HTTP**, `navigator.mediaDevices` may not even exist; thus to verify the policy genuinely, test over **HTTPS** (or `localhost`, which browsers treat as trustworthy in appropriate contexts).

For geolocation, after setting `geolocation=(self)`:

```javascript
navigator.geolocation.getCurrentPosition(
  pos => console.log("Got position", pos.coords.latitude),
  err => console.log("Position error", err.code, err.message)
);
```

Having an allowing policy only means the browser **can proceed to evaluate user permission**; the user may still deny it or the device may lack location support. Thus, failing to obtain coordinates does not by itself prove `Permissions-Policy` blocked it.

For partner iframes, test (a) the parent's header, (b) the `allow` attribute, and (c) user permissions and secure context inside the iframe. A parent header cannot force an iframe to use a feature that the iframe itself denies.

## 7. Real-world issues and troubleshooting

| Symptom | Root causes to distinguish | Remediation |
| --- | --- | --- |
| Links from sensitive pages still leak paths/queries | Header missing on **source HTML**; policy too permissive; CDN overwrote it; link override. | Inspect source HTML response and outgoing requests; switch to `same-origin`/`no-referrer` if appropriate. |
| Third-party analytics do not see full URLs | `strict-origin-when-cross-origin` sends only origin cross-origin. | Treat as intended design; use controlled analytics mechanisms rather than weakening policy to leak URLs. |
| `document.referrer` on destination page has unexpected value | Governed by the **source page** and navigation type, not only destination headers. | Inspect the source page's policy and relevant network requests. |
| Camera won't turn on; browser logs Permissions-Policy violation | `camera=()` or ancestor/iframe policy forbids it. | Open `camera=(self)` or allowlist only origins with genuine need; keep user permissions. |
| Iframe has `allow="geolocation"` yet is still blocked | Parent header omits iframe origin, parent chain blocks it, or browser/user permission missing. | Check policy intersection, exact origins, secure context, and user consent. |
| Geolocation still fails despite `geolocation=(self)` | User denied, browser blocked permission, missing HTTPS, or device lacks support. | Inspect console/Permissions/API error details; do not assume a header bug. |
| Header appears on API calls but HTML pages lack it | HTML served by static server/CDN, bypassing `SecurityFilterChain`. | Configure policy where HTML is served; test the final response. |
| Duplicated headers or inconsistent values | Configured concurrently in Spring, reverse proxy, CDN, or custom filters. | Pick a clear owning layer; inspect live headers and remove conflicting configs. |
| Browser A blocks while Browser B ignores directive | Uneven `Permissions-Policy` feature support. | Run cross-browser tests, enforce user permissions and server controls; do not stake all security on unsupported directives. |

**Never construct policies from untrusted strings.** If feature allowlists or referrer policies depend on dynamic configuration, read only from an audited/validated set of values. Never allow external users to inject arbitrary origins into `Permissions-Policy` or emit conflicting headers.

## 8. Relationship with other HTTP security headers

Setting these two new policies is only part of hardening:

- **Content-Security-Policy (CSP):** restricts sources of scripts, styles, images, network connections, and frames. Helps mitigate certain XSS paths; `frame-ancestors` controls who can embed your page. `Permissions-Policy` does not replace CSP.
- **X-Frame-Options / CSP `frame-ancestors`:** prevents clickjacking by restricting framing; not equivalent to `camera=()` or `microphone=()`.
- **Strict-Transport-Security:** instructs browsers to keep connecting over HTTPS once the HSTS policy is learned; does not control referrer details sent.
- **X-Content-Type-Options: nosniff:** reduces MIME-misinterpretation risks; unrelated to camera/location permissions.
- **Cache-Control** for private data: reduces improper caching risks; does not replace `Referrer-Policy`.
- **CORS:** controls whether other sites can read cross-origin responses; **distinct** from deciding which browser features work and how much source URL is exposed.

For cookie-authenticated applications, proper CSRF protection is still needed; for private data, server-side authorization is still required. Browser headers reduce attack surface, but **do not turn an unprotected endpoint into a secure endpoint**.

## 9. Selection exercises and quick check

**Scenario A — admin console:** A dashboard has URLs like `/customers/123?view=billing`, links out only to support documentation, and needs no camera/mic/geo. You can choose:

```http
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

After deployment, test opening the support link from a sensitive page and inspect the outgoing `Referer`; verify internal search and analytics still work as required.

**Scenario B — product with internal map:** The page locates the user, does not use camera/microphone, and needs to report referring domains for outbound links:

```http
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```

Test over HTTPS with users who have/haven't granted location permission and across multiple browsers. **A policy allowing geolocation does not automatically obtain coordinates**.

**Scenario C — call center video meetings:** A same-origin page needs camera and microphone. You can choose `camera=(self), microphone=(self)`; verify browser prompts and hardware devices. Applying `camera=()` from an admin-page template would break video calls.

**Scenario D — embedding a partner map:** An iframe from `https://maps.partner.example` needs geolocation. The header must allow the exact partner origin; the iframe needs the appropriate `allow` attribute; user consent and a secure context remain mandatory. Never open `geolocation=*` just to make a demo work.

### Pre-release checklist

- Accurately identified the application's **HTML sources** and the layers emitting response headers (Spring/CDN/proxy).
- `Referrer-Policy` aligns with what URL details may be disclosed **same-origin, cross-origin, and on downgrade**.
- No secrets are placed in paths/queries relying solely on policy to hide them.
- Every `Permissions-Policy` directive has a business justification, trusted origins, and no unwarranted wildcards.
- Camera/microphone/location/iframe flows have actually been tested on target browsers and HTTPS.
- Headers are not duplicated and do not strip other default security headers.
- Authentication, authorization, CSRF, CSP, cookies, and HTTPS remain independently enforced.

**Remember:** `Referrer-Policy` governs **how much request source information is sent**; `Permissions-Policy` governs **which browser features can be used**. Choose both based on the product: share the minimum necessary referrer by default, close unused APIs, explicitly open required APIs, and verify effectiveness via **HTML responses + real browser behavior**.
