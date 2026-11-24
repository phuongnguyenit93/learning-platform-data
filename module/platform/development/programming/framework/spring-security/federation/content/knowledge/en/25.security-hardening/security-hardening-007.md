# Size Limits for SAMLResponse, XML, and Attribute Data

> **Topic:** Spring Security – federation. **Group:** Security Hardening. This standalone Knowledge document explains how to design **layered resource limits** when Spring Security acts as a SAML 2.0 Service Provider/Relying Party (SP/RP) receiving `SAMLResponse` from an Identity Provider/Asserting Party (IdP/AP). The primary scope is HTTP-POST Binding, Java 17+, Spring Boot Servlet, Spring Security SAML 2.0, and OpenSAML. Every capacity figure in the examples is an **illustrative starting budget, not a default limit or mandatory SAML number**: you must measure real IdP payloads, confirm with partners, test, and establish resource-based policies.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the sizes of the **HTTP request body**, form-urlencoded `SAMLResponse` value, Base64 string, **decoded XML bytes**, DOM/XML object tree, and post-verification AttributeStatement data.
2. Explain why blocking large request bodies at NGINX/Ingress does **not** replace limits on decoded bytes, XML depth, entity expansion, and attribute counts.
3. Identify related attacks: request flooding, memory/CPU exhaustion, XML parser DoS, XXE/SSRF, oversized signature/encrypted assertions, attribute-count explosion, and log amplification.
4. Configure HTTP POST limits in reverse proxies and embedded Tomcat/Spring Boot while avoiding confusing multipart settings with SAML POST binding.
5. Place a guard before `Saml2WebSsoAuthenticationFilter` to check **Base64/XML format and budgets** without rewriting the SAML validator.
6. Preserve OpenSAML/Spring Security cryptographic, issuer, audience, destination, recipient, time, request correlation, and replay checks.
7. Enforce a **post-signature-verification attribute budget**: attribute name count, value count, per-value length, total size, and an allowlist of truly needed fields.
8. Understand the impact of `EncryptedAssertion`, multiple `Assertion` elements, multiple `AttributeValue` elements, group claims, and large user data on budgets.
9. Handle `413 Content Too Large`, `400 Bad Request`, signature/issuer errors, and internal errors consistently without leaking SAMLResponse/raw XML in logs.
10. Run a plain Java 17 example simulating pre-parse budgets and post-trust-verification budgets with exact stdout.
11. Build a QA matrix covering `limit-1`/`limit`/`limit+1` boundaries, chunked POSTs, malformed Base64, DOCTYPE/XXE, encrypted assertions, signature wrapping, group explosion, and clusters.
12. Choose approved limit increases rather than disabling controls or trusting browser/IdP-sent payloads just because a request carries `SAMLResponse`.

**Golden rule:** There is no single `maxSamlResponseSize` that handles every risk on its own. Multiple **independent limits** are needed, and you must **reject the entire request** when a limit is exceeded; never truncate XML, drop attributes, or try to verify a signature over modified data.

## 2. Flow Model and Where Costs Arise

In SAML 2.0 Web Browser SSO HTTP-POST:

```text
Browser               Edge Proxy / WAF          Spring/Tomcat                  OpenSAML
   |                         |                       |                           |
   | POST /login/saml2/sso/corp                    |                           |
   | Content-Type: application/x-www-form-urlencoded                           |
   | body=SAMLResponse=<Base64 XML>&RelayState=...                               |
   |------------------------>|                       |                           |
   |                [1] raw body limit               |                           |
   |                         |                       |                           |
   |                         | ---- HTTP POST -----> |                           |
   |                         |               [2] Tomcat form parsing             |
   |                         |               [3] SAMLResponse character limit    |
   |                         |               [4] Base64 decode byte limit        |
   |                         |                       |----- decoded XML --------->|
   |                         |                       |                      [5] secure XML parse
   |                         |                       |                      [6] signature / issuer
   |                         |                       |                          / audience / time
   |                         |                       |<----- verified principal--|
   |                         |               [7] attribute count/value budget    |
   |                         |               [8] local user + tenant mapping     |
   |                         |               [9] SecurityContext/session         |
   |<------------------------|<----------------------|                           |
```

This model has at least **nine points** operators can control, though not all share the same API. For example:

- A reverse proxy can reject request bodies before the JVM, reducing CPU/heap pressure.
- Tomcat processes form POSTs under servlet rules; it bounds bytes used for form parameter parsing and parameter count.
- Spring Security `Saml2WebSsoAuthenticationFilter` extracts `SAMLResponse` as a request parameter, resolves the registration, and passes it to the authentication manager.
- OpenSAML builds DOM/XML objects, verifies signatures, processes encrypted assertions, and validates SAML conditions. These are expensive operations that can allocate memory many times larger than input bytes.
- The post-validation principal can contain thousands of group values; if copied into HttpSession, Redis, audit logs, or business requests, the DoS surface does not end at the parser.

**Confusion to avoid:** An HTTP 413 at the edge means the **form body** was too large; it does not prove the XML had a bad signature. OpenSAML signature failures differ from request budget failures. These events must be instrumented separately, without returning secret details to the browser.

## 3. Data Nature: SAMLResponse Is Not Raw XML Directly in HTTP POST

Illustrative SAML POST Binding example:

```http
POST /login/saml2/sso/corp HTTP/1.1
Host: sp.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PHNhbWxwOlJlc3BvbnNlLi4u&RelayState=opaque
```

The `SAMLResponse` value is the **Base64 of the SAML Response XML**, transmitted as a form parameter under URL-encoding rules. The XML typically looks like:

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-id" Version="2.0"
    Destination="https://sp.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <!-- Signature, Status, and Assertion are illustrative only -->
  <saml:Assertion ID="_assertion-id">
    <saml:AttributeStatement>
      <saml:Attribute Name="groups">
        <saml:AttributeValue>team-finance</saml:AttributeValue>
        <saml:AttributeValue>team-operations</saml:AttributeValue>
      </saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>
```

This is **not a valid SAML response for logging in**: the example omits conditions/signatures required by the trust contract. Never use hand-written XML like this to bypass signature verification. To test the happy path, use a staging IdP issuing a **real signed SAML Response** matching your registration/ACS.

### 3.1. Base64 and URL encoding increase size

Standard Base64 formula for `n` input bytes:

```text
base64Length = 4 * ceil(n / 3)

XML bytes    Base64 ASCII chars (approx.)
     3                   4
   300                 400
 30,000             40,000
300,000            400,000
450,000            600,000
```

The HTTP form body also includes the `SAMLResponse=` parameter name, `RelayState`, URL encoding of Base64 special characters like `+`, `/`, `=`, and possibly other params. Hence the **HTTP body is typically larger than the Base64 string**, with the difference depending on URL encoding/partner/browser. Even partially unpadded Base64 must conform to what the library accepts.

**Do not compare `SAMLResponse.length()` directly to raw XML bytes.** Java's `String.length()` counts UTF-16 code units; Base64 is normally all ASCII so it roughly matches ASCII chars, whereas XML AttributeValues can be multi-byte UTF-8. For Unicode values and log/session limits, measure **UTF-8 bytes**, not just Java character counts.

### 3.2. Do not apply the wrong decompression for the binding

- HTTP-POST Binding normally receives **Base64-encoded XML**, without the “DEFLATE raw XML” step of HTTP-Redirect Binding for SAML messages.
- HTTP-Redirect Binding typically applies DEFLATE+Base64+URL encoding to `SAMLRequest` or `SAMLResponse` per binding, carrying its own expansion risk if supported.
- HTTP `Content-Encoding` `gzip`/`br` at the HTTP layer is a separate matter and may be decompressed by a proxy. If the product does not support request compression at the ACS, **reject non-identity Content-Encoding** to avoid compression bombs.
- `EncryptedAssertion` is XML Encryption; once decrypted, XML can turn into a DOM/object subtree larger than the ciphertext. It is **not** HTTP compression. Both pre- and post-decryption checks are needed architecturally.

**Do not implement SAMLResponse HTTP-POST inflation “for extra compatibility”** without a binding agreement and post-decompression size checks. That can turn a tiny request into a massive payload.

## 4. Threat Model: Why Does Large Size Become a Security Bug?

| Attack/failure | Input/processing path | Consequence |
| --- | --- | --- |
| **HTTP body flood** | Thousands of large POSTs to ACS | Exhausts bandwidth, sockets, proxy buffers, temp files |
| **Chunked upload without Content-Length** | Transfer-Encoding chunked or streaming requests | Bypasses guards that inspect only the Content-Length header |
| **Form parameter flood** | Many junk keys/duplicate `SAMLResponse` | Parse/hash CPU, memory, ambiguous input |
| **Massive Base64** | Long `SAMLResponse` field | String/byte array allocations, GC pressure |
| **Oversized DOM/XML tree** | Valid XML with many nodes/attrs | Heap growth, parsing latency, OOM |
| **XML entity expansion** | DTD/internal entity chain | Exponential CPU/memory; “Billion Laughs” |
| **XXE/external resource** | DOCTYPE, external DTD/entity/XInclude | SSRF, local-file disclosure, network calls |
| **XML Signature wrapping** | Multiple assertions/IDs/reference ambiguity | Can read identity from unsigned node if library/config is flawed |
| **Signature verification DoS** | Many signatures, transforms, references | Spikes CPU before determining the message is invalid |
| **Encrypted assertion overload** | Many EncryptedAssertions/keys | Decryption CPU and DOM/heap growth |
| **Attribute explosion** | `groups`/`memberOf` with thousands of values | Memory, session bloat, Redis/network amplification |
| **Long text/markup values** | Multi-MB AttributeValue, heavy Unicode | Log/JSON/HTML rendering overhead, XSS if rendered unsafely |
| **Multi-tenant registration confusion** | IdP A sends huge payload for SP/tenant B | Resource exhaustion or authorization misbinding |
| **Overlooked logout/metadata XML** | `SAMLRequest` on SLO, metadata parser, or XML upload | DoS paths outside ACS |
| **Observability amplification** | Logging raw `SAMLResponse`, XML, attributes | Disk/cost/privacy incident |
| **Unbounded retries** | IdP sends valid message that RP rejects, browser loops | Login storm, self-inflicted load spike |

Even a trusted IdP can emit an oversized assertion due to AD group bloat or a config bug. **Resource limits still apply to trusted partners**; signature trust is not a license for unbounded heap/CPU usage.

### 4.1. Amplification model

Suppose a raw form body is 700 KiB:

```text
700 KiB HTTP body
  -> ~550 KiB Base64 string (rough estimate)
  -> ~410 KiB XML bytes
  -> DOM nodes + Java XML objects + signature/decrypt intermediates
  -> Java String/List/Map attributes in principal
  -> HttpSession / Spring Session Redis serialization
  -> logs/events/cache/JSON responses
```

This is a **qualitative example**. There is no guaranteed “XML ×10 RAM” multiplier for every runtime; memory growth depends on XML shape, parser, OpenSAML, allocations, policy mapping, and JVM heap. Measure heap allocation/GC and p95 parse time using valid payloads near the limit.

## 5. Designing a Multi-Layered Resource Budget

### 5.1. An illustrative initial budget for one application

| Location | Illustrative budget | Actual unit | Why |
| --- | --- | --- | --- |
| NGINX/Ingress `client_max_body_size` | **1 MiB** | HTTP request body bytes | Block before JVM, including chunked/uploads |
| Tomcat `max-http-form-post-size` | **1 MiB** | Form POST bytes fed to parameter parsing | Prevent container from parsing huge forms |
| Tomcat `max-parameter-count` | **16** | GET+POST parameter count | Stop parameter flooding/duplicates |
| App guard `MAX_BASE64_CHARS` | **650,000** | Base64 string characters | Bound Base64 input before decode |
| App guard `MAX_XML_BYTES` | **450,000** | Decoded XML byte[] length | Block oversized XML before OpenSAML |
| XML parser `maxElementDepth` | **64** | Nesting depth | Stop abnormally deep XML |
| XML parser `entityExpansionLimit` | **100** or DTD forbidden | Count | Limit entity amplification; prefer forbidding DTD |
| XML parser `totalEntitySizeLimit` | **10,000** or DTD forbidden | Chars/size per parser | Backstop against amplification |
| Post-verification `MAX_ATTRIBUTE_NAMES` | **32** | Valid Attribute names | Bound fields entering principal/session |
| Post-verification `MAX_TOTAL_VALUES` | **128** | Total values | Curb group explosion |
| Post-verification `MAX_SINGLE_VALUE_BYTES` | **2,048** | UTF-8 bytes per value | Prevent giant text strings |
| Post-verification `MAX_TOTAL_ATTRIBUTE_BYTES` | **32 KiB** | Total UTF-8 bytes of names+values | Bound session/cache/serialization |

**This is an example profile**, not claimed to fit every federation. A partner legitimately sending 150 group values will be rejected by this example; agree on a group strategy, which permissions are truly needed, and per-registration limits. Define multiple profiles based on verified needs rather than guessing one global limit.

The relationships are designed intentionally:

```text
HTTP form body <= 1,048,576 bytes
Base64 chars  <=   650,000 chars
decoded XML   <=   450,000 bytes
attribute blob <=  32,768 UTF-8 bytes

4 * ceil(450,000 / 3) = 600,000 Base64 characters
=> Allow a little headroom for variation/malformed content,
   while decoded XML still has its own separate limit.
```

**Why is the Base64 limit 650,000 larger than 600,000?** The guard can catch XML >450,000 after decoding even if the encoded field has not yet hit the string cap. In production you can tighten the encoded cap closer to contract and add padding/format integrity checks. These values are not Spring Security defaults.

### 5.2. Empirical rules for choosing thresholds

1. Collect statistics on **valid payloads** per IdP/tenant/test cohort, measuring only size/histograms, **never storing raw assertions**.
2. Measure raw body bytes, Base64 chars, decoded XML bytes, XML element count/depth, attribute counts/total bytes, p95/p99 CPU, and heap.
3. Isolate outlier data sources: nested groups, multiple encrypted assertions, embedded certificate chains, long custom attribute JSON.
4. Add headroom for normal variance, avoiding arbitrary “max observed ×100”.
5. Negotiate IdP attribute release: send only needed groups/roles, using stable opaque IDs or an ACL-protected backend lookup when group membership is huge.
6. Define profiles per `RelyingPartyRegistration`/partner and govern changes through review and audit.
7. Assess accessibility/availability impact: a legitimate user with many groups should not be locked out silently; provide a clear support/ticket workflow.
8. Test boundaries at ±1 unit at the **exact target layer**. A `MAX_XML_BYTES` test needs valid Base64 inside an allowed body so the proxy does not block it first.
9. Observe saturation under peak load instead of tuning solely on a dev machine with huge heap.
10. Attach policy version to deployments/metrics so you know why a partner suddenly started hitting 413 after a change.

## 6. HTTP POST and Spring Security SAML 2.0: Which Endpoints Receive Data?

In Spring Security Servlet, configured ACS endpoints are typically:

```text
POST /login/saml2/sso/{registrationId}
POST /login/saml2/sso             (some cases look up registration from state/response)
```

The sender posts the `SAMLResponse` form. `Saml2WebSsoAuthenticationFilter` uses the authentication converter to build a `Saml2AuthenticationToken`, then the OpenSAML-backed authentication provider verifies signatures and conditions before creating `Saml2Authentication`.

- `/saml2/authenticate/{registrationId}` generates AuthnRequests; it is **not** the ACS receiving Responses.
- `/logout/saml2/sso` or another configured SLO endpoint handles logout `SAMLRequest`/`SAMLResponse` and needs its own guard.
- `/saml2/metadata` serves/publishes metadata; if the app also **imports metadata from a URL**, handle XML/HTTP response size and SSRF separately rather than reusing the ACS guard for all metadata fetches.
- If customizing `saml2Login(...loginProcessingUrl(...))` or multi-tenant routes, update ACS consistently across RelyingPartyRegistration, IdP metadata, WAF, and the filter guard. Never leave a custom ACS outside all limits.

**Never use `web.ignoring()` to “bypass security for the ACS”.** The ACS must be handled by the SAML authentication filter to verify signature/issuer/audience, not by a custom REST controller accepting XML.

## 7. NGINX/Ingress: Early HTTP Body Rejection

This is an **NGINX configuration fragment** for an RP with `/login/saml2/sso/{registrationId}`. TLS is already configured by the organization; the reverse proxy connects to HTTPS upstream with server certificate verification.

```nginx
# Fragment inside server { listen 443 ssl; ... }
location ^~ /login/saml2/sso/ {
    # Overall form body budget at ingress:
    client_max_body_size 1m;
    client_body_timeout 10s;
    proxy_request_buffering on;

    # Upstream HTTPS with server identity verification:
    proxy_pass https://saml-backend.internal.example.org:8443;
    proxy_ssl_server_name on;
    proxy_ssl_name saml-backend.internal.example.org;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate
        /etc/nginx/trust/saml-backend-ca.pem;

    proxy_set_header Host sp.example.org;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host sp.example.org;

    proxy_connect_timeout 5s;
    proxy_read_timeout 30s;
}
```

**Important notes:**

- `client_max_body_size 1m` checks **HTTP request body size at the edge**; NGINX typically returns HTTP **413** when exceeded, before forwarding upstream.
- `proxy_request_buffering on` makes the proxy read/buffer the request before sending to the backend. Buffering affects temp files/disk and latency; plan capacity, timeouts, and disk permissions. It does **not** replace a size limit.
- `client_body_timeout` is an idle timeout between body reads, not an absolute end-to-end deadline; add separate request rate/connection limits against slow clients.
- `proxy_ssl_verify on` protects the backend hop; not directly part of SAML size policy, yet required to preserve TLS trust when carrying authentication evidence.
- Canonical `Host`/`X-Forwarded-Host` at the proxy must match the public ACS URL. The edge must strip client-sent `Forwarded` and `X-Forwarded-*` headers before setting them to prevent recipient/destination mismatches.
- If using `/login/saml2/sso` **without a registrationId**, apply matching policy to that exact location or use a properly configured regex/location. Never leave it unbounded because a trailing `/` didn't match.
- Across multiple ingress hops (CDN → WAF → NGINX), enforce sizes at the **actual public ingress** and ensure alternate hosts/paths cannot bypass limits.
- NGINX `client_max_body_size 0` disables checking: **never** use it to “fix login errors” when an IdP sends too many groups.
- `nginx -t` checks syntax, **not** that HTTP 413/PKIX/routing work. Test through the public host and observe upstream bytes.

### 7.1. HTTP 413, chunked requests, and body buffering

Never read `Content-Length` from the browser alone and assume the body is small. Requests can omit Content-Length, use `Transfer-Encoding: chunked`, or have framing rewritten by proxies. **NGINX can count body bytes as read**, whereas a Servlet Filter inspecting `getContentLengthLong()` may see `-1`.

If handling streaming requests directly in the app without a trusted ingress, you need a **bounded-read body wrapper** that actually counts bytes before any `getParameter*`/XML parse, compatible with Servlet container form parsing and request replay. That is subtle: never write a filter that reads `ServletInputStream` and still expects `getParameter("SAMLResponse")` to work without valid caching/replay, or the data may already be consumed before Spring Security sees it.

### 7.2. If an IdP hits 413 after increasing group counts

Proper remediation workflow:

1. Identify which layer returned 413 (CDN, WAF, NGINX, Tomcat, app guard).
2. Compare valid payload sizes via redacted metrics.
3. Determine which groups are truly needed in SAML; trim attribute release if possible.
4. If increasing the limit is justified, adjust **the relevant layers** deliberately and check memory/CPU/session/Redis impact.
5. Add a representative signed partner fixture and negative regression tests.
6. Never bypass size checks based on a browser-supplied `?idp=trusted`; policy must come from verified registration.

## 8. Tomcat/Spring Boot: Form Limits Differ from Multipart and Uploads

For **Spring Boot 3.x/Spring Security 6.x on embedded Tomcat**, example in `src/main/resources/application.yml`:

```yaml
server:
  tomcat:
    max-http-form-post-size: 1MB
    max-parameter-count: 16
    max-swallow-size: 2MB
  max-http-request-header-size: 8KB

spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              singlesignon:
                url: "https://idp.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:corp-idp-signing.crt"
```

**Configuration warning:** IdP/certificate values are placeholders; this is a Spring Boot project fragment, not runnable without a real staging IdP and proper RelyingPartyRegistration/ACS. Never put an IdP signing certificate into the TLS truststore as a substitute for XML Signature verification. Conversely, the IdP's HTTPS cert is not automatically its XML signing key.

- `server.tomcat.max-http-form-post-size` limits POST content parsed into parameters (`application/x-www-form-urlencoded`/multipart parts per container rules). It is **not** a limit on every HTTP request body across all content types.
- `server.tomcat.max-parameter-count` caps total query + POST parameters, stopping `SAMLResponse=...` padded with hundreds of junk fields from burning parser CPU/memory.
- `max-swallow-size` caps how much body Tomcat will drain after an error/abort to keep the connection alive. It does **not** replace `max-http-form-post-size` or raw body limits.
- `server.max-http-request-header-size` caps request line/headers; it does **not** cap Base64 in the POST body.
- `spring.servlet.multipart.max-file-size` and `max-request-size` apply to multipart uploads and are **not** the primary control for SAML HTTP-POST Binding `application/x-www-form-urlencoded`.
- Jetty, Undertow, and Boot 4/Security 7 differ in property semantics/versions; consult **docs for your exact embedded server and version**. Never copy `server.tomcat.*` to Jetty assuming it takes effect.
- Tomcat may handle `maxPostSize` errors differently depending on config/container; not every oversize payload necessarily returns 413. Test actual responses/statuses and **never accept a partial/empty form as a valid login**.
- With HTTP/2 → HTTP/1.1 proxies or service meshes, each layer has its own framing/body limits. Enforce effective policies along the **entire real call path**.

### 8.1. Order of checks matters

A Servlet Filter calling `request.getParameter("SAMLResponse")` already causes the container to **parse the form** before the filter measures the value length. Therefore:

```text
Ingress raw-body limit
    -> Tomcat form/parameter limit
        -> Spring pre-SAML filter checks Base64/XML bytes
            -> OpenSAML secure parse, signature and assertions
                -> post-verification attribute budget
                    -> local user mapping + session persistence
```

**Do not claim the Java filter below prevents all container memory allocations.** It is an **additional guard before OpenSAML**, while out-of-JVM ingress and container limits block earlier.

## 9. Spring Security Guard: Reject Oversized Base64/XML Before OpenSAML

### 9.1. Filter scope and rules

Apply only to the configured **POST ACS**; paths like SAML SLO must have their own budget. The guard:

- Validates method, URL, Content-Type, Content-Encoding, and query policy.
- Checks `getContentLengthLong()` early when known; **never** treats it as the defense for chunked bodies.
- Reads `getParameterValues("SAMLResponse")` after Tomcat's form limits; requires **exactly one** value.
- Checks parameter count and Base64 character count before decoding.
- Decodes Base64 with `java.util.Base64.getDecoder()`, rejecting invalid data; measures decoded XML bytes without keeping the byte[] in session/logs.
- **Does not parse XML here** to avoid double-parser/differential behavior. Spring/OpenSAML performs parsing and validation next.
- For requests exceeding budget, rejects the **entire request** instead of truncating and letting the provider consume incomplete XML.
- Never prints `SAMLResponse` or XML in logs/error responses.

### 9.2. Java filter in a Spring Boot application

File `src/main/java/com/example/saml/SamlAcsSizeGuard.java`:

```java
package com.example.saml;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class SamlAcsSizeGuard extends OncePerRequestFilter {

    private static final long MAX_FORM_BYTES = 1_048_576L;
    private static final int MAX_BASE64_CHARS = 650_000;
    private static final int MAX_XML_BYTES = 450_000;
    private static final int MAX_FORM_PARAMS = 8;
    private static final int MAX_RELAY_BYTES = 256;

    private static boolean isAcs(String path) {
        return "/login/saml2/sso".equals(path)
            || path.startsWith("/login/saml2/sso/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        // Servlet path normally excludes context path.
        String path = request.getServletPath();
        if (!isAcs(path) || !"POST".equals(request.getMethod())) {
            chain.doFilter(request, response);
            return;
        }

        // Lab policy: ACS has no query string.
        // If a partner's ACS needs a registered static query,
        // design a dedicated matcher instead of dropping the check completely.
        if (request.getQueryString() != null) {
            response.sendError(400, "Unexpected ACS query string");
            return;
        }

        String contentType = request.getContentType();
        if (contentType == null ||
            !contentType.toLowerCase(Locale.ROOT)
                .startsWith("application/x-www-form-urlencoded")) {
            response.sendError(415, "Unsupported SAML POST content type");
            return;
        }

        String encoding = request.getHeader("Content-Encoding");
        if (encoding != null &&
            !"identity".equalsIgnoreCase(encoding)) {
            response.sendError(415, "Compressed request not supported");
            return;
        }

        // Can reject early only when length is known. Chunked/-1:
        // ingress/container byte limits are mandatory.
        long bodyBytes = request.getContentLengthLong();
        if (bodyBytes > MAX_FORM_BYTES) {
            response.sendError(413, "SAML request body too large");
            return;
        }

        // Calling getParameter* TRIGGERS form parsing:
        // Tomcat max-http-form-post-size must be configured.
        String[] values = request.getParameterValues("SAMLResponse");
        if (values == null || values.length != 1 ||
            values[0] == null || values[0].isEmpty()) {
            response.sendError(400, "Exactly one SAMLResponse required");
            return;
        }

        if (request.getParameterMap().size() > MAX_FORM_PARAMS) {
            response.sendError(400, "Too many SAML form parameters");
            return;
        }

        String samlBase64 = values[0];
        if (samlBase64.length() > MAX_BASE64_CHARS) {
            response.sendError(413, "SAMLResponse base64 too large");
            return;
        }

        String relayState = request.getParameter("RelayState");
        if (relayState != null &&
            relayState.getBytes(StandardCharsets.UTF_8).length >
                MAX_RELAY_BYTES) {
            response.sendError(413, "RelayState too large");
            return;
        }

        final byte[] xml;
        try {
            xml = Base64.getDecoder().decode(samlBase64);
        }
        catch (IllegalArgumentException ex) {
            response.sendError(400, "Malformed SAMLResponse base64");
            return;
        }

        if (xml.length == 0) {
            response.sendError(400, "Empty SAMLResponse");
            return;
        }

        if (xml.length > MAX_XML_BYTES) {
            response.sendError(413, "Decoded SAML XML too large");
            return;
        }

        // DO NOT call DocumentBuilder.parse(xml) here.
        // DO NOT modify request parameters or signed XML.
        // Spring Security/OpenSAML continues validation.
        chain.doFilter(request, response);
    }
}
```

**Trust boundaries of the example:**

- This class uses Jakarta Servlet + Spring Web `OncePerRequestFilter` in a Spring Boot project. It is **not** a standalone `javac` program; Spring dependencies are required.
- The filter checks **length and Base64 syntax**; it does not guarantee valid XML, right issuer, or valid signature. Any valid Base64 under the limit can still be rejected by OpenSAML.
- `startsWith("application/x-www-form-urlencoded")` is a pragmatic format check, yet stricter Content-Type parsing and application charset contracts should be used where needed; reject mismatched content types.
- A proxy may have already decompressed Content-Encoding before the JVM; the sample assumes edge policy rejects compressed ACS requests and does not decompress itself.
- `MAX_RELAY_BYTES=256` is an **illustrative policy**. SAML HTTP-POST/Redirect Bindings have their own RelayState profile constraints; choose the right interoperability contract. RelayState must bind to a trusted transaction/session, not merely pass length checks.
- `getParameterMap()` has already been parsed by Tomcat before Java counts it. Never use `getParameter*` in place of a raw-body limit.
- Error strings are generic codes that **never** echo user input or Base64/NameID. Apps may use `ErrorController`/standard handlers for consistent UX/logging.
- Ingress rate limiting, connection limits, and timeouts are still required; this filter does not solve distributed floods or request-body slowloris on its own.
- Ensure the filter runs **before the Spring SAML converter**. If the app customizes `loginProcessingUrl`, update the route check in this filter to match.

### 9.3. Registering the filter in the right SecurityFilterChain

File `src/main/java/com/example/saml/SamlSecurityConfig.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2WebSsoAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        // Filter created only inside the chain; avoid an external @Bean Filter
        // which would cause Boot to auto-register an extra global Servlet Filter.
        http.addFilterBefore(
            new SamlAcsSizeGuard(),
            Saml2WebSsoAuthenticationFilter.class);

        return http.build();
    }
}
```

**Config scope:** Spring Security 6.x/Boot 3.x, Java 17+, Servlet. Requires `spring-security-saml2-service-provider` and proper `RelyingPartyRegistration`/IdP signing certificates. For Spring Security 7.x, check Javadoc/migration notes, especially principal/response authentication converters and callbacks; never mix code from two major versions in the same example.

**Mandatory order check:** An app may declare multiple `SecurityFilterChain` beans. The guard must live **in the chain handling ACS requests**, not only in a business API chain. Test with a synthetic POST to the ACS and verify the guard returns 413 when exceeding limits, **before** OpenSAML parses.

### 9.4. Strengths and gaps of the filter

| Layer | Does this guard protect? | What else is needed? |
| --- | --- | --- |
| Large raw HTTP body | **Partially**, when Content-Length is known | Real ingress byte limit, chunked/streaming |
| Container parameter parsing | **No, runs after parse** | Tomcat max form size/parameter count |
| Huge Base64 | **Yes**, after form parse | Connection/rate controls |
| Large decoded XML bytes | **Yes** | Secure parser/decrypt complexity budgets |
| XXE/DTD/entity expansion | **No** | OpenSAML/JAXP parser hardening |
| XML signature wrapping | **No** | Secure OpenSAML validators and signed-node binding |
| EncryptedAssertion expansion | **No, happens at decrypt** | Library-specific node/complexity budgets |
| Many SAML AttributeValues | **No** | Post-validation attribute limits/allowlist |
| Cached role/tenant grant | **No** | Authoritative authorization |
| SAML replay/InResponseTo | **No** | SAML authentication provider + request correlation |
| Total server CPU under flood | **No** | WAF/rate/concurrency/timeouts, sizing |

**Never treat the guard as a replacement “SAML parser” or “SAML validator”.** Write tests proving that once payloads pass the guard, OpenSAML still rejects unsigned messages, unknown issuers, wrong audiences, expired assertions, and mismatched subject recipients.

## 10. XML Hardening: DOCTYPE, Entity Expansion, Parser Limits

### 10.1. Why are XML byte limits not enough?

An XML document of only a few kilobytes containing DTDs/entities can expand into huge data during parsing or reference external resources. XML nested thousands of elements deep also drives recursive parser/DOM execution, heavy allocations, and CPU spikes.

Defensive layers:

- **Disallow DTD/DOCTYPE** on untrusted SAML Responses when unneeded.
- **Disallow external general/parameter entities and external DTDs**; block local/network fetches.
- Disable **XInclude** unless the protocol genuinely requires it, as XInclude can fetch outside DTDs.
- Enable JAXP `FEATURE_SECURE_PROCESSING` and deny external access via `ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA`.
- Set processing limits (depth, entity expansion, total entity size, XML name size, element attributes, node count) as supported by parser/JDK.
- Never allow the XML parser to auto-download schemas/XSDs from URLs inside messages.
- Validate XML Signatures only through a supported library; never manually DOM-parse and call `getElementsByTagName("Assertion").item(0)`.
- **Fail startup/deployment** if policy-required parser security settings are unsupported, rather than catching the exception and parsing insecurely.

### 10.2. JAXP parser example for app-owned XML

The snippet below **illustrates hardening for a standalone parser only**—it is not advice to replace OpenSAML's parser with a custom DOM and reserialize signed SAML:

```java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public final class HardenedXmlReader {

    public static Document readBoundedXml(InputStream stream)
            throws Exception {

        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newDefaultInstance();

        factory.setNamespaceAware(true);
        factory.setXIncludeAware(false);

        // Disallow DOCTYPE and external XML resources.
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);

        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        factory.setAttribute("jdk.xml.maxElementDepth", "64");
        factory.setAttribute("jdk.xml.entityExpansionLimit", "100");
        factory.setAttribute("jdk.xml.totalEntitySizeLimit", "10000");

        DocumentBuilder builder = factory.newDocumentBuilder();

        // stream MUST already be byte-bounded before calling.
        // Never parse user-supplied URLs/file names.
        return builder.parse(stream);
    }
}
```

**Conditions of use:**

- `DocumentBuilderFactory.newDefaultInstance()` exists since JDK 9 and picks the JDK's default parser. Other implementations may differ in properties/features.
- `FEATURE_SECURE_PROCESSING` **does not block every external entity automatically**; you must also lock down external access and DOCTYPE/DTD.
- `"jdk.xml.maxElementDepth"` and processing limits are JDK XML properties; supported values and defaults vary by JDK/vendor. Test on your exact Java runtime.
- This is not code to call directly on `SAMLResponse` to read NameID. Use **OpenSAML/Spring Security** to parse and validate SAML per protocol. Parsing separately to “pre-count” both allocates a second DOM and creates **parser differential and signature wrapping** risks.
- If the app genuinely needs to inspect XML tree shape, use library-supported extension points, ensuring you still validate the **exact signed node** and bound large allocations upfront where possible.
- Never turn off parser restrictions just because an IdP sends a DTD; standard SAML Web SSO needs no DTD. If a special partner requires non-standard XML constructs, review and update the security contract.

### 10.3. JDK XML properties to know

| Property/feature | Limit | Layer |
| --- | --- | --- |
| `XMLConstants.FEATURE_SECURE_PROCESSING` | Enables secure processing mode and certain limits | DOM/SAX/XPath/Transformer per implementation |
| `XMLConstants.ACCESS_EXTERNAL_DTD` | Protocols permitted for DTD reads | XML parser/schema |
| `XMLConstants.ACCESS_EXTERNAL_SCHEMA` | Protocols permitted for XSD reads | SchemaFactory/Parser |
| `jdk.xml.entityExpansionLimit` | Total entity expansions | JAXP parser |
| `jdk.xml.totalEntitySizeLimit` | Total size of expanded entities | JAXP parser |
| `jdk.xml.maxElementDepth` | XML tree depth | JAXP parser |
| `jdk.xml.maxXMLNameLimit` | Length of XML element/attr names | JAXP parser |
| `jdk.xml.elementAttributeLimit` | Number of XML **attributes** on an element | JAXP parser |
| `jdk.xml.maxGeneralEntitySizeLimit` | Size of an individual entity | JAXP parser |
| `jdk.xml.maxOccurLimit` | Grammar nodes when processing XSD maxOccurs | Schema validation |

**Important distinction:** an XML **attribute** `Name="..."` on an element differs from a **SAML Attribute** element `<saml:Attribute Name="groups">`, and differs from **AttributeValue**. `jdk.xml.elementAttributeLimit` does **not** bound the number of `<saml:Attribute>` or `<saml:AttributeValue>` elements. You must implement separate post-validation SAML attribute budget logic.

### 10.4. OpenSAML does not automatically use your parser

Spring Security relies on OpenSAML; OpenSAML has its own parser pool/unmarshaller/security defaults. Defining a `DocumentBuilderFactory` Spring Bean **does not automatically change the XML parser used by OpenSAML**. Check parser pool configuration and extension points for your exact OpenSAML version:

1. Inspect `spring-security-saml2-service-provider` and transitive OpenSAML dependencies in `mvn dependency:tree`.
2. Verify OpenSAML's default parser features and current security advisories.
3. If customizing the parser, use **supported initialization/parser pool configuration**, not reflection or speculative global parser overrides.
4. Verify assertions with DOCTYPE/XXE are rejected in real integration tests (a signed fixture cannot be “injected” post-signing and remain valid).
5. Never “parse, alter XML, then verify signature” using a custom-normalized DOM.
6. Maintain XML parser/decrypt/validation budgets and rate limits. Never blindly trust JVM default limits.

## 11. Signature Checks, Encrypted Assertions, and XML Signature Wrapping

**Size limits ≠ SAML trust verification.** After the pre-parse budget, OpenSAML/Spring Security must still check:

- SAML Response/Assertion signature with the right registration's **trusted IdP signing certificate** and permitted signature algorithms.
- `Issuer` matches the IdP, `Destination` matches the ACS, `AudienceRestriction` matches the SP entityID.
- `SubjectConfirmationData.Recipient` matches the callback; `InResponseTo` correlates to the request when required by the flow.
- `NotBefore/NotOnOrAfter`, bearer confirmation time, and replay/one-time-use policy.
- Decrypt encrypted assertions using the **SP decryption credentials** when the IdP uses encryption.
- Map principal/attributes **only from the validated assertion bound to the right signature**, never selecting an unsigned assertion with matching field names.
- Block signed XML wrapping/duplicate IDs/reference ambiguity per library policy and patched versions.
- Never trust `RelayState` to determine tenant or perform arbitrary external redirects.
- Never let response status `Success` substitute for signature/issuer/recipient checks.
- Never trust XML attributes from a request before the provider returns an authenticated principal.

### 11.1. Budgets before and after decryption

```text
HTTP POST byte limit
   |
   v
Base64 string limit
   |
   v
Decoded XML byte limit
   |
   v
OpenSAML secure parse + crypto validation
   |
   +-- Signature verification
   +-- EncryptedAssertion/EncryptedID decryption
   +-- Signed response / assertion conditions
   +-- Validation result
   |
   v
Verified attribute budget
   |
   v
Local identity + tenant authorization
```

**When XML contains `EncryptedAssertion`:** pre-decryption body/XML limits are still required; post-decryption, the object tree can exceed the encrypted payload. The post-validated-decryption attribute budget stops **business/session data bloat**, though it cannot prevent every allocation **during** decryption. Where risk is high, consider max assertion count, encrypted data node count, signatures/references/transforms, provider-specific bounds, and IdP contracts capping assertion counts.

### 11.2. Do not “fix” oversized assertions by truncating

Wrong approaches:

```text
SAMLResponse = SAMLResponse.substring(0, MAX)
XML = XML.replaceAll("<AttributeValue>...", "")
Only take first Assertion before signature checks
Ignore Signature when XML is too big
Use unsigned NameID when signed Assertion too large
Silently drop extra groups and allow ROLE_USER
Set maxPostSize=-1 / client_max_body_size 0 globally
```

- Truncating Base64/XML breaks integrity and causes parser/crypto errors.
- Dropping attributes **before validation** alters signed XML, breaking signature semantics or causing parser mismatches.
- Silently dropping roles without clear rules produces inconsistent authorization decisions. Instead: **fail closed** with a generic message and have the IdP trim data or use a trusted backend lookup.
- Never fall back to an unsigned assertion when parsing a large signed assertion fails.

## 12. Limiting Attribute Data After Trust Verification

A SAML AttributeStatement can carry many `<saml:Attribute>` elements, each with many `<saml:AttributeValue>` elements, possibly containing non-string XMLObjects. A partner could emit thousands of groups. Accepting and mapping **all** of them into `Authentication`/`HttpSession` causes:

- `GrantedAuthorities` bloat, raising memory and role-check overhead.
- `SPRING_SECURITY_CONTEXT` serialization to Redis adding latency/network/storage overhead.
- Expensive session replication/backup and cluster failover.
- Logs/audits/exports duplicating unnecessary claims.
- Potential authorization bypass if `groups`→`ROLE_ADMIN` mapping lacks an allowlist or issuer trust contract.

### 12.1. Minimal attribute release

| Attribute/claim | Needed? | Safe handling |
| --- | --- | --- |
| `NameID` or immutable external subject | Usually needed for identity | Bind to trusted `Issuer`/registration; check format/length |
| `email` | Possibly for contact | Do not use as sole identity key if mutable/reused |
| `displayName` | UX | Limit bytes, escape on HTML render, avoid flooding logs |
| `groups` | Possibly for authorization | Only groups from approved IdP; cap count, least-privilege mapping |
| `department`, `costCenter` | Business | Validate schema; never turn raw text into SQL/commands |
| `entitlements` | Sensitive | Use signed/verified context, version/issuer binding, local policy |
| Rich XML attributes | Rare | Needs dedicated schema and hardening; never blindly call `toString()` on arbitrary objects |
| Blob/certificate/custom JSON encoded in XML | Usually unneeded | Reject or move to a separately bounded channel |

**Never grant `ROLE_ADMIN` because a `groups` attribute contains the string `admin` from some newly added IdP.** Mapping must bind to issuer/registration, group namespace, tenant membership, and application policy.

### 12.2. When AttributeValue is not always a String

Spring Security 6.x `Saml2AuthenticatedPrincipal#getAttributes()` returns `Map<String, List<Object>>`, because SAML allows values of multiple types. Under a policy accepting **only text attributes**, you can:

1. Reject any non-`String` value per the IdP contract.
2. Never call `value.toString()` on arbitrary objects to compute size when an object might serialize/lazy-load/incur high cost.
3. Measure `value.getBytes(StandardCharsets.UTF_8).length` to bound Unicode bytes.
4. Limit total attributes/values before creating authority objects and before persisting the session.
5. Never serialize the entire raw SAMLResponse or XML tree into the business model just to extract a group.
6. If a partner requires structured values, write a bounded typed parser/mapper and test it as a dedicated feature.

### 12.3. Java policy class limiting verified attributes

Example **in a Spring 6.x application**, file `src/main/java/com/example/saml/VerifiedAttributeBudget.java`:

```java
package com.example.saml;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

public final class VerifiedAttributeBudget {

    private static final int MAX_NAMES = 32;
    private static final int MAX_VALUES = 128;
    private static final int MAX_VALUE_BYTES = 2_048;
    private static final int MAX_TOTAL_BYTES = 32_768;

    private VerifiedAttributeBudget() { }

    /**
     * Call ONLY AFTER OpenSAML has validated Response/Assertion.
     * Partner in this example must emit text AttributeValues.
     */
    public static void check(Map<String, List<Object>> attrs) {
        if (attrs == null || attrs.size() > MAX_NAMES) {
            throw new IllegalArgumentException(
                "Verified SAML attribute count exceeded");
        }

        int valueCount = 0;
        int totalBytes = 0;

        for (var entry : attrs.entrySet()) {
            String name = entry.getKey();
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "SAML attribute name invalid");
            }

            totalBytes +=
                name.getBytes(StandardCharsets.UTF_8).length;

            List<Object> values = entry.getValue();
            if (values == null) {
                throw new IllegalArgumentException(
                    "SAML attribute values unavailable");
            }

            if ((long) valueCount + values.size() > MAX_VALUES) {
                throw new IllegalArgumentException(
                    "SAML attribute values exceeded");
            }
            valueCount += values.size();

            for (Object value : values) {
                if (!(value instanceof String text)) {
                    throw new IllegalArgumentException(
                        "Unexpected non-text SAML attribute");
                }

                int bytes =
                    text.getBytes(StandardCharsets.UTF_8).length;

                if (bytes > MAX_VALUE_BYTES) {
                    throw new IllegalArgumentException(
                        "SAML value too large");
                }

                totalBytes += bytes;
                if (totalBytes > MAX_TOTAL_BYTES) {
                    throw new IllegalArgumentException(
                        "Total SAML attributes too large");
                }
            }
        }

        if (totalBytes > MAX_TOTAL_BYTES) {
            throw new IllegalArgumentException(
                "Total SAML attribute bytes exceeded");
        }
    }
}
```

**This is policy logic, not yet wired into the SAML provider.** It must not be called by manually decoding XML before Spring, and should not be placed solely in an MVC controller after the session has already been issued. Inside the provider/custom converter for your Spring Security version, enforce it **after signature/conditions validation and before the successful Authentication is saved**.

In production, replace `IllegalArgumentException` with `Saml2AuthenticationException`/a policy-specific authentication failure matching your API version (so malformed input does not become a 500), and never log full attribute values. Use overflow-safe byte summation `if (bytes > MAX_TOTAL_BYTES - totalBytes) reject` if policy raises thresholds to large sizes; this sample keeps the maximum total small by capping name/value counts early, yet production code should still remain defensive.

### 12.4. Integration point with Spring Security 6.5 / OpenSAML 5

A common extension point in Spring Security 6.5 is:

```java
// Intentional fragment, not a complete class.
// Applies when using OpenSaml5AuthenticationProvider
// and the converter returns Saml2Authentication/Saml2AuthenticatedPrincipal.

OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();

OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter
    defaultConverter =
    new OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter();

provider.setResponseAuthenticationConverter(responseToken -> {
    Saml2Authentication authentication =
        defaultConverter.convert(responseToken);

    Saml2AuthenticatedPrincipal principal =
        (Saml2AuthenticatedPrincipal) authentication.getPrincipal();

    VerifiedAttributeBudget.check(principal.getAttributes());

    return authentication;
});

// Register provider in SecurityFilterChain via:
// saml2Login(saml -> saml.authenticationManager(
//     new ProviderManager(provider)));
```

**Version/API caveats:**

- The snippet requires importing `OpenSaml5AuthenticationProvider`, `Saml2Authentication`, `Saml2AuthenticatedPrincipal`, and `ProviderManager` matching Spring Security 6.5; use it as a **configuration fragment** where IdP/RelyingPartyRegistration already exist, not standalone javac code.
- In Spring Security 7, `Saml2AuthenticatedPrincipal` is marked deprecated in favor of `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`. Update the converter per version; never mix APIs.
- Because the converter checks **after** OpenSAML has created objects, it protects against storing oversized attributes/role explosion, yet it does **not** completely prevent parsing/decryption cost before the converter. If you need hard upper bounds on nodes/attribute structures **before** large allocations, customize validators/parser pool via tested extension points without replacing default signature checks.
- If letting `IllegalArgumentException` bubble up causes clients to see 500, replace it with an authentication-policy exception and a failure handler emitting sanitized error codes; verify end-to-end.
- The converter must read **only the verified** assertion/attributes that the provider bound to the exact signed object. Never pick another assertion using custom XPath/regex.

### 12.5. Why not just drop excess attributes and allow login anyway?

An IdP sending a long `groups` list might accidentally exceed the limit:

- If the app's mapping has an explicit policy “only two allowlisted roles are needed”, configure the IdP to release only those small roles or have the backend check membership from an authority store.
- **Never arbitrarily truncate** a group list, because a critical privilege group might sit in the truncated tail, or code taking “the first group” could change authorization semantics.
- If policy permits dropping **certain non-security attributes** after signature validation, design a deterministic allowlist that cannot affect principal/tenant/role decisions and audit it.
- In the SAML metadata/attribute contract, IdP and SP should agree on a **stable subject** and minimal attribute set; when thresholds are exceeded, show a generic error and open a review workflow instead of relaxing limits system-wide.
- In all cases, never grant privileges from unverified data.

## 13. EncryptedAssertion, Certificates, and Signature Complexity

A SAML Response may contain:

```xml
<samlp:Response ...>
  <ds:Signature>...</ds:Signature>
  <saml:EncryptedAssertion>...</saml:EncryptedAssertion>
</samlp:Response>
```

When encryption is used:

1. The “outer” XML may look small, yet after decryption it expands into assertions and attributes.
2. There can be multiple encrypted objects, encrypted keys, and XML signatures; total CPU cost grows with count/complexity.
3. Decryption must use the **SP's decryption credential** for the right registration, never arbitrarily using the IdP signing cert.
4. Enforce a **cipher algorithm allowlist** and cap the count of assertions/EncryptedAssertions per IdP contract.
5. Never accept “partial success” when one assertion fails decryption while the parser returns another assertion lacking a valid signature.
6. After decryption, verify signed-node binding, conditions, audience, and subject confirmation.
7. If multiple valid assertions exist per profile, the app needs an explicit policy for which to use; never opportunistically pick whichever assertion carries a desired role.
8. Encrypted data/crypto can be expensive even when the HTTP body < size limit, so enforce per-request budgets, rate limits, CPU metrics, and load tests.

**Never raise `maxXMLBytes` indefinitely to rescue an IdP sending many EncryptedAssertions.** First determine what the IdP is emitting, whether the signing/encryption scheme is necessary, and whether attributes/duplicate assertions can be trimmed.

## 14. RelayState, Duplicate Parameters, and Response Pollution

`RelayState` is typically opaque correlation state; it is not a pre-trusted route/URL.

**Issues to block:**

- Multiple `SAMLResponse` fields in the body or across query+body causing ambiguous `getParameter()` precedence. Accept **only one** field.
- `SAMLResponse` in the query string when the ACS expects a POST body. The sample policy rejects queries altogether to prevent HTTP parameter pollution; if an IdP profile requires a static query, design an explicit matcher.
- Oversized, duplicated `RelayState`, or one containing an external URL or masquerading as a tenant ID. Bound its bytes and verify it matches the created request/session correlation; never pass it directly to `redirect`.
- Unexpected fields like `username`, `role`, or `tenant` sent alongside SAMLResponse. **Never** use them for authentication/authorization; optionally reject via an agreed form-parameter allowlist.
- If a proxy/Servlet container mis-decodes `+`, `%2B`, or Unicode, Base64 may be corrupted. Diagnose encoding rather than disabling checksums/signatures or “fixing Base64 by replacing spaces with +” by guesswork.
- Never push assertions into GET/query params, where they leak in URLs/referrers/logs and exceed header/URL limits; use metadata-defined bindings.
- If Content-Type is `multipart/form-data` while SAML integration only accepts URL-encoded POST, reject rather than letting the app accept XML file uploads.

## 15. Logging, HTTP Errors, and UX When Budgets Are Exceeded

### 15.1. Classifying errors by layer

| Category | Typical HTTP | Meaning |
| --- | --- | --- |
| Edge raw body exceeded | **413** | Request body larger than ingress policy |
| App Base64/XML byte budget exceeded | **413** | Payload too large before SAML parser |
| Malformed form, missing/duplicate `SAMLResponse` | **400** | Invalid request structure |
| Unsupported Content-Type/Content-Encoding | **415** | Binding payload transport unsupported by policy |
| XML parse fail / DOCTYPE / XXE | Typically **400** or auth failure | Malformed/prohibited XML; do not log in |
| Invalid signature, wrong issuer/audience, expired assertion | Auth failure, redirect/login/401 per app | Untrusted SAML authentication |
| Attribute budget exceeded post-validation | Auth failure, generic notice | Verified assertion too large for app contract |
| WAF blocked/rate limited | **429** or gateway status | Request rate/session policy |
| IdP/network infrastructure error | 5xx or domain-specific unavailable | Distinct from malformed assertions |

**Do not force everything into HTTP 413.** Badly signed XML is an authentication failure, not a bandwidth issue. If the parser hits `OutOfMemoryError`, that is a severe operational failure and likely means the guard ran too late; never catch it and return 200 with a default user.

### 15.2. Data permitted in metrics

Measure:

```text
saml_acs_requests_total{registration,decision,reason}
saml_acs_body_bytes_histogram{registration}
saml_base64_chars_histogram{registration}
saml_decoded_xml_bytes_histogram{registration}
saml_parse_duration_seconds{registration}
saml_signature_validation_failure_total{registration}
saml_attribute_names_histogram{registration}
saml_attribute_values_histogram{registration}
saml_attribute_bytes_histogram{registration}
saml_session_serialized_bytes_histogram{application}
saml_acs_inflight_requests{node}
saml_413_total{layer,route}
saml_xml_security_rejections_total{reason}
```

**Do not log**:

```text
Raw SAMLResponse / Base64
Raw decoded XML / Assertion / NameID if PII
Full AttributeStatement / group values
XML signing or decryption private keys
Session cookies, RelayState opaque secrets
SAML signing certificates as sensitive dump in every error
Full Authorization headers / tokens
```

Cardinality control: never put username/NameID, arbitrary issuer URLs, XML attribute values, or request IDs into Prometheus labels. Use allowlisted registrationId, reason category, and bounded sizes. Error responses should display a harmless correlation ID and avoid echoing payloads.

### 15.3. Runbook when a partner reports 413

1. Record timestamp, registrationId/IdP, status, ingress route, policy version, and correlation ID (never ask for the full SAMLResponse over email).
2. Identify the **layer** returning 413: CDN, WAF, NGINX, Tomcat, or app guard.
3. Inspect raw-body/Base64/XML/attribute histograms without turning on raw XML debug logging in production.
4. Ask the IdP to inspect attribute release, nested groups, and encrypted assertions in a test environment.
5. If an increase is legitimately required, consider a **per-registration threshold** and review p95/p99 resource consumption instead of raising limits for all endpoints.
6. Run boundary tests, malicious fixtures, and CPU/memory/Redis serialization checks.
7. Deploy via canary, watching CPU/GC/413 rate and login success.
8. Document QA results with the new limit, approving owner, rationale, and review date.
9. If a partner repeatedly exceeds limits, propose trimming group claims or switching to an authenticated, properly cached backend userinfo/entitlement lookup.
10. Never worsen user errors with infinite retry loops or advise “open Developer Tools and send us the whole SAMLResponse”.

## 16. Standalone Java 17: Simulating Two-Phase Budgets

This example runs with **JDK 17 without Spring, IdP, or certificates**. It illustrates a **pre-XML-parse budget** and a **simulated post-trust-verification attribute budget**. It does NOT verify signatures, parse XML, generate valid SAMLResponses, or **prove the security of a real SP**.

File `SamlPayloadBudgetDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class SamlPayloadBudgetDemo {

    private static final int MAX_FORM_BYTES = 1_048_576;
    private static final int MAX_BASE64_CHARS = 650_000;
    private static final int MAX_XML_BYTES = 450_000;
    private static final int MAX_ATTRIBUTE_NAMES = 32;
    private static final int MAX_VALUES = 128;
    private static final int MAX_VALUE_BYTES = 2_048;
    private static final int MAX_ATTRIBUTE_BYTES = 32_768;

    static String envelopeDecision(int bodyBytes, String base64) {
        if (bodyBytes > MAX_FORM_BYTES) {
            return "REJECT_FORM_BYTES";
        }
        if (base64 == null || base64.isEmpty()) {
            return "REJECT_BASE64";
        }
        if (base64.length() > MAX_BASE64_CHARS) {
            return "REJECT_BASE64_CHARS";
        }

        byte[] xml;
        try {
            xml = Base64.getDecoder().decode(base64);
        }
        catch (IllegalArgumentException ex) {
            return "REJECT_BASE64";
        }

        if (xml.length == 0) {
            return "REJECT_XML_EMPTY";
        }
        if (xml.length > MAX_XML_BYTES) {
            return "REJECT_XML_BYTES";
        }

        // Only means "allow to proceed to the next parse/verify step".
        return "ALLOW_PREPARSE";
    }

    // attrs is a fixture assumed ALREADY verified via SAML.
    // Production never accepts this map directly from the browser.
    static String attributeDecision(Map<String, List<String>> attrs) {
        if (attrs == null || attrs.size() > MAX_ATTRIBUTE_NAMES) {
            return "REJECT_ATTRIBUTE_NAMES";
        }

        int valueCount = 0;
        int byteCount = 0;
        for (var entry : attrs.entrySet()) {
            String name = entry.getKey();
            if (name == null || name.isBlank()) {
                return "REJECT_ATTRIBUTE_NAME";
            }

            byteCount +=
                name.getBytes(StandardCharsets.UTF_8).length;

            List<String> values = entry.getValue();
            if (values == null ||
                (long) valueCount + values.size() > MAX_VALUES) {
                return "REJECT_ATTRIBUTE_VALUES";
            }

            valueCount += values.size();

            for (String value : values) {
                if (value == null) {
                    return "REJECT_ATTRIBUTE_VALUE";
                }
                int n = value.getBytes(StandardCharsets.UTF_8).length;
                if (n > MAX_VALUE_BYTES) {
                    return "REJECT_ATTRIBUTE_VALUE_BYTES";
                }
                byteCount += n;
                if (byteCount > MAX_ATTRIBUTE_BYTES) {
                    return "REJECT_ATTRIBUTE_TOTAL_BYTES";
                }
            }
        }

        return byteCount > MAX_ATTRIBUTE_BYTES
            ? "REJECT_ATTRIBUTE_TOTAL_BYTES"
            : "ALLOW_MAPPED";
    }

    public static void main(String[] args) {
        String validDemoXml = Base64.getEncoder().encodeToString(
            "<demo/>".getBytes(StandardCharsets.UTF_8));

        String hugeXml = Base64.getEncoder().encodeToString(
            new byte[MAX_XML_BYTES + 1]);

        System.out.println("smallEnvelope=" +
            envelopeDecision(150, validDemoXml));

        System.out.println("largeBody=" +
            envelopeDecision(MAX_FORM_BYTES + 1, validDemoXml));

        System.out.println("badBase64=" +
            envelopeDecision(150, "%%%"));

        System.out.println("largeXml=" +
            envelopeDecision(700_000, hugeXml));

        System.out.println("smallAttributes=" +
            attributeDecision(
                Map.of("groups", List.of("ops", "staff"))));

        Map<String, List<String>> manyNames =
            new LinkedHashMap<>();
        for (int i = 0; i < 33; i++) {
            manyNames.put("field" + i, List.of("x"));
        }
        System.out.println("manyNames=" +
            attributeDecision(manyNames));

        System.out.println("manyValues=" +
            attributeDecision(
                Map.of("groups", java.util.Collections.nCopies(
                    129, "x"))));

        System.out.println("longValue=" +
            attributeDecision(
                Map.of("groups", List.of("x".repeat(2_049)))));

        Map<String, List<String>> aggregate =
            new LinkedHashMap<>();
        for (int i = 0; i < 19; i++) {
            aggregate.put("g" + i,
                List.of("x".repeat(1_800)));
        }
        System.out.println("aggregate=" +
            attributeDecision(aggregate));
    }
}
```

Compile/run:

```bash
javac --release 17 SamlPayloadBudgetDemo.java
java SamlPayloadBudgetDemo
```

Exact stdout:

```text
smallEnvelope=ALLOW_PREPARSE
largeBody=REJECT_FORM_BYTES
badBase64=REJECT_BASE64
largeXml=REJECT_XML_BYTES
smallAttributes=ALLOW_MAPPED
manyNames=REJECT_ATTRIBUTE_NAMES
manyValues=REJECT_ATTRIBUTE_VALUES
longValue=REJECT_ATTRIBUTE_VALUE_BYTES
aggregate=REJECT_ATTRIBUTE_TOTAL_BYTES
```

**Explanation:**

- `smallEnvelope=ALLOW_PREPARSE` only says Base64 of `<demo/>` is small and decodable. `<demo/>` is **not** a signed SAML Response; OpenSAML will not allow login.
- `largeBody=REJECT_FORM_BYTES`: raw form body exceeds limit.
- `badBase64=REJECT_BASE64`: invalid Base64 syntax; never “swap characters so it decodes”.
- `largeXml=REJECT_XML_BYTES`: encoded value is still under 650,000 chars yet decoded XML byte[] is 450,001 bytes, caught separately.
- `smallAttributes=ALLOW_MAPPED`: small simulated map, still needing real identity + authorization.
- `manyNames=REJECT_ATTRIBUTE_NAMES`: 33 names > 32.
- `manyValues=REJECT_ATTRIBUTE_VALUES`: 129 values > 128.
- `longValue=REJECT_ATTRIBUTE_VALUE_BYTES`: single text value has 2,049 UTF-8 bytes > 2,048.
- `aggregate=REJECT_ATTRIBUTE_TOTAL_BYTES`: 19 values × 1,800 bytes plus names > 32 KiB.
- This code performs no TLS, XML parsing, certificate chaining, signatures, audience, recipient, replay, or IdP source matching. Both functions simulate **resource budgets** only and must never be used to grant Authentication in production.

## 17. Integration Testing with Real IdPs and Signed Fixtures

**To test a failure other than signature failure**, use a fixture validly signed by a test IdP or build a fixture with test IdP/keys and sign **after** modifying content. If you take a signed SAMLResponse and inject 10,000 AttributeValues via text editing, the signature will fail before or alongside attribute checks, skewing test conclusions.

### 17.1. Happy path

1. Register SAML RP `corp`, ACS `https://sp.example.org/login/saml2/sso/corp`, and right test IdP trust.
2. Test IdP issues a signed Response with right issuer/audience/recipient/destination/time and contracted group values.
3. Record **size metrics only**, never keeping the raw SAMLResponse in logs or reports.
4. Browser POSTs the form through CDN/NGINX/Tomcat/Spring Security.
5. Edge raw body limit, Tomcat form limits, and app Base64/XML guard let it pass.
6. OpenSAML parse/verify and signature/conditions PASS.
7. Attribute budget PASSES, local user/tenant mapping PASSES.
8. Local SecurityContext/session is created, app returns authorized resource.
9. Verify Redis/session serialized bytes stay within budget; refresh/login does not trigger GC storms.

### 17.2. Boundary and negative test matrix

| Test | Input/setup | Expected |
| --- | --- | --- |
| **HTTP body limit -1** | Form body 1 byte below 1 MiB | Not blocked by edge size; still must pass SAML validation |
| **HTTP body limit** | Exactly 1 MiB | Standard “> limit” policy usually accepts; test real NGINX |
| **HTTP body limit +1** | 1 byte over 1 MiB | 413 at edge, never reaches OpenSAML |
| **Chunked POST** | No Content-Length, oversized body | Proxy/container still rejects, no bypass |
| **Many form parameters** | 17+ keys when Tomcat limit is 16 | Reject; no crash |
| **Duplicate SAMLResponse** | Two fields with same name | 400, never pick “first” |
| **SAMLResponse in query** | POST with query `SAMLResponse=...` | Guard rejects per policy, preventing parameter pollution |
| **Missing SAMLResponse** | Form lacks field | 400 |
| **Malformed Base64** | Contains `%%%` or bad padding | 400, no permissive fallback |
| **Encoded char limit +1** | Base64 >650,000 chars yet HTTP body under proxy limit | 413 at app guard |
| **Decoded XML bytes limit +1** | Valid Base64, XML 450,001 bytes | 413, no XML parsing |
| **Decoded XML empty** | Base64 of 0 bytes | 400 |
| **Small unsigned XML** | `<demo/>` or unsigned SAML | Guard may pass, OpenSAML authentication FAILS |
| **DOCTYPE/XXE** | XML contains DTD/external entity | XML parse security rejects; no file read/network call |
| **Entity amplification** | Nested entities/billion-laughs | Parser rejects, CPU/memory bounded |
| **XML depth >64** | Deeply nested elements | Reject at parser limit when configured |
| **Huge XML names** | Huge element/attribute names | Reject per XML name/byte budget |
| **Many DOM nodes** | Thousands of XML elements within byte budget | Node/parser complexity policy rejects or bounded by benchmark |
| **Many XML signatures** | Many References/Transforms | Reject unsupported complexity/invalid signatures |
| **Signature wrapping** | Duplicate IDs, injected unsigned assertion | Reject; never read unsigned NameID/role |
| **Wrong issuer** | Signed by wrong IdP trust/registration | Authentication FAILS |
| **Wrong audience** | AudienceRestriction for another SP | Authentication FAILS |
| **Wrong recipient** | SubjectConfirmationData.Recipient differs from ACS | Authentication FAILS |
| **Wrong Destination** | Response Destination differs from public ACS | Authentication FAILS |
| **Expired Assertion** | NotOnOrAfter in the past | Authentication FAILS |
| **Replay** | Re-sent Response/ticket per correlation policy | Reject per anti-replay/OneTimeUse/request policy |
| **Valid EncryptedAssertion** | Signed/encrypted fixture within budgets | Decrypt/verify succeeds, verified attributes only |
| **EncryptedAssertion expansion** | Many decrypted values exceed budget | No session created, bounded failure recorded |
| **Multiple Assertions** | More assertions than contract permits | Reject or handle per provider policy, never pick unsigned |
| **Many SAML attribute names** | 33 verified names | Fails attribute budget |
| **Many values** | 129 verified values | Fails attribute budget |
| **One long value** | UTF-8 >2,048 bytes | Fails attribute budget |
| **Aggregate values too large** | Total UTF-8 >32 KiB | Fails attribute budget |
| **Nested group explosion** | Test IdP emits hundreds of groups | Reject / IdP trims groups per contract |
| **Unicode multi-byte value** | Vietnamese/emoji, byte count > char count | Proper UTF-8 byte budget applied |
| **Oversized RelayState** | >policy, signed response still valid | Guard rejects |
| **Content-Encoding gzip** | HTTP compressed POST out of policy | 415/reject at edge/app, never inflate |
| **POST wrong Content-Type** | JSON, multipart, or raw XML directly | 415/reject per ACS binding |
| **SAML SLO endpoint** | Large logout `SAMLRequest` | Separate size/parse/signature budget |
| **Metadata import** | Very large/untrusted metadata XML | Separate bounded fetch/parse and SSRF protection |
| **Redis/session bloat** | Verified attributes close to budget | Serialized session bytes remain within SLA |
| **Login burst** | Many small signed responses/sec | Rate/concurrency limits, no CPU exhaustion |
| **Two pods different config** | Ingress A limit 1m, B unlimited | Fail deployment consistency; fix policy drift |
| **IdP partner changes attributes** | Group release doubles 2× | Alert, explicit review; never auto-raise global limits |
| **Error logs leak XML** | Large invalid request | No raw SAMLResponse/XML/NameID logged |
| **Browser retry loop** | IdP keeps sending oversized response | Graceful error, avoid auto-redirect storm |

### 17.3. Beware of tests hitting the wrong target

To test the **decoded XML limit**, craft a request body and encoded char count **below** the raw/encoded limits, otherwise the edge blocks it first and you haven't tested the app guard.

To test the **post-verification attribute budget**, use a signed assertion whose count/value exceeds profile while the overall request stays under network/XML budgets. Editing content after signing only proves the signature is invalid, not that attribute counts are enforced.

To test **XML entity expansion**, a validly signed message is unnecessary (DOCTYPE breaks XML/signature contracts): the goal is that the parser **rejects before accessing the network or consuming excessive resources**. This is a parser-hardening test, not an acceptance test for signed SAML messages.

To test **HTTP POST size with Content-Length -1**, send a chunked upload through the **actual public ingress**, not merely a Servlet Filter unit test on the JVM.

## 18. Automated Testing in Spring Security Without Calling Production IdPs

### 18.1. Three test tiers to separate

1. **Java unit tests:** `SamlPayloadBudgetDemo`/attribute policy testing boundary arithmetic and fail-closed logic; do not pretend to verify SAML.
2. **Servlet integration tests:** Use MockMvc or embedded Tomcat to verify filter order, oversized Base64/decoded XML, Content-Type, and HTTP statuses. MockMvc **does not fully simulate** ingress/chunked/Tomcat connector limits.
3. **Real SAML integration tests:** Staging IdP issues signed encrypted/unencrypted fixtures, browser ACS has valid correlation/time/issuer/recipient. Test invalid cases and measure memory/CPU/session.
4. **Infrastructure tests:** NGINX/WAF/k8s ingress 413, chunked bodies, body buffering/temp files, rate limits, multiple replicas, and certs/routes.
5. **Load/performance tests:** p95/p99 parse latency, GC allocations, heap high-water mark, CPU, and queue depths at near-limit payloads under concurrency.

A single MockMvc test for 413 does not replace real TLS/NGINX/body streaming tests. Conversely, synthetic huge Base64 without a signature suffices to prove the **pre-parse guard**, not post-validation mapping.

### 18.2. Sample test scenarios as a fixture table

```text
fixture-small-signed.xml               valid,  25 KiB, 3 attributes
fixture-near-limit-signed.xml          valid, 445 KiB, bounded attributes
fixture-too-many-groups-signed.xml     valid, 300 KiB, 180 group values
fixture-expired-signed.xml             expired NotOnOrAfter
fixture-foreign-issuer-signed.xml      wrong trusted issuer
fixture-encrypted-many-values.xml      decrypts to oversized attribute set
fixture-invalid-duplicate-id.xml       signature-wrapping/ID ambiguity
fixture-xxe-doctype.xml                untrusted XML parser rejection test
```

File names illustrate test structure only; they are **not pre-existing files** or a requirement to create them in the repository. Each signed fixture must be generated/signed by a test IdP with dedicated certificates; never store production private keys or production user data in CI.

### 18.3. PASS criteria for “resources bounded”

An implementation PASSES if:

- Requests exceeding the raw HTTP limit never reach the app parser, including streaming/chunked.
- Oversized forms/too many parameters are rejected by Tomcat/edge without silently picking partial parameters.
- Encoded/XML limits reject before OpenSAML.
- XML parser rejects DOCTYPE/XXE without accessing test URLs/files.
- Signed-response validation remains mandatory on all small payloads, with no bypass.
- Verified attributes exceeding policy never enter an active `SecurityContext`/HttpSession/Redis.
- Valid near-limit IdP fixtures still log in within latency/memory SLAs.
- Zero raw SAMLResponse/XML/secret leaks in logs/errors/metrics.
- All pods/regions/ingress routes enforce the same security policy version.
- Tenant/issuer-specific exceptions have owners, expirations, change approvals, and protective tests.

## 19. Troubleshooting Common Issues

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Browser sees 413 before reaching Spring | NGINX/WAF/CDN body budget | Check request size, IdP release, ingress policy |
| Only one user fails to log in | User has very many groups/attributes | Measure attribute count via redacted telemetry, trim release |
| Spring sees empty SAMLResponse | Tomcat form parser/parameter limit exceeded | Check Tomcat logs/status, form size config |
| `Invalid character in Base64` | Form encoding corrupted `+`/`%2B`, or request tampered | Fix IdP/browser form URL encoding, never decode permissively |
| Raw body under limit yet XML bytes exceed | Encoded/decoded budgets differ | Check MAX_XML_BYTES, consider trimming IdP XML |
| XML parser OOMs despite small body | Entity expansion, deep XML, many nodes | Enforce DOCTYPE/XXE/depth/node limits, update library |
| CPU spike during login | Signatures/decrypt/complex XML | Crypto complexity/rate budgets, optimize IdP response |
| `Signature validation failed` after dropping groups | Someone edited signed XML after signing | Only IdP may change attribute release and re-sign |
| Invalid recipient/destination behind reverse proxy | Forwarded host/proto/ACS mismatch | Fix canonical ACS/trusted headers |
| Login succeeds yet Redis session is huge | Unbounded verified attributes/roles stored | Post-validation budget, map minimal identity |
| Some tenants always denied | Global budget doesn't fit IdP contracts | Per-trusted-registration profile limits |
| Continuous IdP timeout/retries | Error handling triggers login loop | Stop auto-retries, show sanitized error with request ID |
| Unsupported `XMLConstants` property | Different JAXP provider/library | Fail configuration, use supported parser/security settings |
| 413 returns 502 to client | Proxy buffering/swallow/timeouts/upstream connection | Test integration statuses, improve error boundary |
| JWT/Group mapping still grants roles past limit | Attribute checks placed too late in controller | Enforce before Authentication/session creation |
| 403 from business resource | Not necessarily SAML size | Distinguish tenant/role authorization from SAML login failure |
| Performance differs across pods | JVM heap/OpenSAML/config drift | Align versions, heaps, ingress limits, and load tests |
| Metadata fetch OOM | Unbounded external XML download/parser | Separate metadata max bytes/depth/SSRF controls |
| SAML SLO DoS | ACS guard does not cover SLO | Add policy for logout request/response |
| Payload leaks in traces | APM logs request body/form parameters | Disable/redact body, retention control, and incident review |

### 19.1. Quick decision tree

```text
User reports "SAML login fails"
           |
           v
Did proxy/WAF return HTTP 413?
  |-- YES -> inspect raw-body size & IdP attribute release.
  |
  +-- NO -> Did Tomcat reject form/parameters?
               |-- YES -> verify max form & param limits.
               |
               +-- NO -> Did pre-SAML guard reject?
                           |-- BASE64/XML SIZE -> 413 by policy.
                           |-- FORM/BASE64 INVALID -> 400/415.
                           |
                           +-- NO -> Did OpenSAML parse securely?
                                       |-- NO -> DTD/XXE/depth/invalid XML.
                                       |
                                       +-- YES -> Signature/issuer/audience?
                                                     |-- FAIL -> SAML trust.
                                                     |
                                                     +-- PASS -> Attribute budget?
                                                                |-- FAIL -> partner contract
                                                                |           or values too large.
                                                                |
                                                                +-- PASS -> Local user/roles/
                                                                             tenant/session.
```

**Never fix the wrong layer:** An HTTP 413 is not cured by disabling signature verification. An invalid XML signature is not cured by raising the body limit. A 403 due to missing tenant permissions is not caused by parser/size limits.

## 20. Rules for Raising Limits and Partner Exceptions

### 20.1. Legitimate cases needing large payloads

Suppose an IdP must transmit several hundred certificate attributes or nested group chains that the business cannot immediately trim. Before relaxing:

1. Verify the use case genuinely requires that data inside the SAML assertion for authorization.
2. Try designing to send only a stable subject + minimal claims, looking up entitlements on the backend from a trusted source.
3. If large group membership is required, define **max groups/total bytes** per tenant/registration and enforce least privilege.
4. Measure parse/decrypt/validate CPU, peak heap, serialized session bytes, Redis bandwidth, and p95 login under concurrent load.
5. Ensure Java/NGINX/Tomcat/JAXP/OpenSAML have compatible controls.
6. Choose a limit with reasonable headroom, never unlimited.
7. Record policy review/approval and exception expiration date.
8. Test both signed positive fixtures and malicious negative fixtures under the new limit.
9. Roll out via canary per registration, watching 413/latency/GC/heap/errors.
10. Once the IdP fixes release, lower the limit back to the appropriate minimum.

**Never use a browser-chosen query string (`?tenant=vip`, `?idp=trusted`) to select larger thresholds.** Profiles must come from verified registration/trust context; the pre-validation ingress layer may rely on trusted host/path routes and WAF policy, never on unsigned body data.

### 20.2. What to do with many group values?

Trade-off options:

- IdP releases only **app-relevant** groups, omitting unnecessary nested/transitive groups.
- IdP emits a single app-approved `role` instead of full memberships.
- SP receives a stable subject, then the backend looks up groups/entitlements from an authenticated directory/authorization service with TTL/invalidation caching.
- If groups are needed for UI display, serve them from a paginated, authorized API instead of stuffing them into signed assertions/sessions.
- Separate identity from authorization; keep the SAML Response strictly as login proof while backend policy grants data access.
- Do not self-hash group names and treat hashes as authorization claims unless issuer and receiver both verify signed mappings and collision handling.
- Increasing size is only a fallback after evaluating data-reduction options.

## 21. Exercises and Answers

**Q1.** An IdP sends an HTTP body of 900 KiB, Base64 value of 590,000 chars, decoded XML of 442 KiB, and post-verification attributes totaling 20 KiB. Does the profile in section 5 accept it?

**Answer:** It can pass the **illustrative size limits** (subject to other controls), yet must still be parsed securely, verify SAML signature/issuer/audience/recipient/time, and check counts/depth/attribute values and local authorization. Never treat “small” as trusted.

**Q2.** An XML file is only 8 KiB, yet contains a DOCTYPE chaining entities that expand to hundreds of MB. Is `MAX_XML_BYTES=450,000` sufficient?

**Answer:** No. Raw/decoded XML size does not stop entity expansion; you must forbid DTD/XXE, cap expansions/depth/nodes, and use a hardened parser.

**Q3.** A Servlet filter checks only `request.getContentLengthLong() > 1MiB`. Can a chunked request without Content-Length bypass it?

**Answer:** Yes. `getContentLengthLong()` is often `-1`. Use an ingress body limit checking actual bytes, Tomcat form limits, and a bounded reader if direct streaming is truly required.

**Q4.** Tomcat has `spring.servlet.multipart.max-request-size: 1MB`. Does that protect SAML HTTP-POST binding?

**Answer:** It is not the primary guard. SAML POST is `application/x-www-form-urlencoded`, which uses `server.tomcat.max-http-form-post-size`/parameter count and ingress body limits.

**Q5.** A SAMLResponse has an invalid signature but a tiny payload. Can login proceed because it stayed within the size budget?

**Answer:** No. Size budgets only bound resources; the authentication provider must still verify signature/trust/conditions.

**Q6.** Strip `AttributeValue` elements from a signed Response at the gateway and let Spring validate the rest. Is that safe?

**Answer:** No. Altering signed XML before verification breaks signatures/bindings or enables XML signature wrapping; the IdP must trim data **before signing** or the SP applies intentional mapping **after validation**.

**Q7.** A Base64 field has 600,000 ASCII chars; roughly how many bytes can the decoded XML be?

**Answer:** With valid padding, at most around 450,000 bytes, from `4*ceil(n/3)`. Actual bytes depend on padding/format; enforce strictly on **post-decode** byte length.

**Q8.** After signature validation, `groups` has 160 values while policy caps at 128. Should you take the first 128 values and assign ROLEs from them?

**Answer:** Not by default. Fail closed with an explicit policy, ask the IdP to reduce groups, or perform backend lookup; truncation makes role/tenant mapping inconsistent.

**Q9.** An application sets only `jdk.xml.elementAttributeLimit=10`. Does that block 1,000 `<saml:Attribute>` elements?

**Answer:** No. That JAXP property limits XML attributes on **a single element**, which differs from the count of **SAML Attribute elements**. You need application-specific attribute budget checks.

**Q10.** Using another JAXP XML parser to parse and grab the first NameID before handing XML to OpenSAML to verify. What is wrong?

**Answer:** Risk of trusting unverified content/parser differentials/signature wrapping. Map the principal only from an assertion validated by OpenSAML.

**Q11.** An HTTP request gets 413 from NGINX and Spring logs nothing. Is this a Spring Security SAML provider bug?

**Answer:** No. The proxy blocked it before the request reached the app; check the ingress body limit and partner IdP attribute release.

**Q12.** Should full Base64/XML be logged for diagnostics since SAMLResponse is signed?

**Answer:** No. Assertions can carry PII/roles/session identifiers; a signature does not make data public. Log only sizes, registration ID, error category, and sanitized trace ID per policy.

## 22. Pre-Production Acceptance Checklist

- [ ] Mapped the SAML HTTP-POST flow: IdP → browser → edge → Tomcat → Spring SAML filter → OpenSAML → principal/session.
- [ ] Understood that raw HTTP form body, Base64 chars, decoded XML bytes, DOM/OpenSAML objects, and verified attributes are **distinct budgets**.
- [ ] Edge/Ingress/WAF enforces `client_max_body_size` or equivalent on **all** ACS routes, including registrationId-less paths if used.
- [ ] Size policy works with Content-Length, chunked, HTTP/2-to-HTTP/1, and request buffering.
- [ ] Tomcat/Jetty/Undertow form-post and parameter-count limits match exact server/version, not confused with multipart.
- [ ] Guard runs before `Saml2WebSsoAuthenticationFilter` and after container form limits; no duplicate global filter registration.
- [ ] `SAMLResponse` length and decoded XML bytes bounded; invalid Base64 and duplicate fields rejected.
- [ ] No separate XML parsing before OpenSAML to extract NameID/attributes; no truncating signed XML.
- [ ] XML parser forbids unneeded DTD/XXE/external entities/XInclude, enabling FSP and version-appropriate processing limits.
- [ ] Actual **OpenSAML parser pool** configuration verified, not assuming a JAXP Bean affects the library automatically.
- [ ] SAML signature/issuer/audience/destination/recipient/time/correlation/replay remain mandatory, never replaced by size guards.
- [ ] EncryptedAssertion has decryption and post-decryption complexity/attribute budgets, not just cipher size.
- [ ] Assertion count/XML nodes/signature refs have explicit policies if IdP/profile has special needs.
- [ ] Post-verification limits check names, values, single UTF-8 bytes, total bytes, types, and allowlisted attributes.
- [ ] Groups/roles map only from contracted issuer/registration; never create `ROLE_ADMIN` from raw group text.
- [ ] Local account/tenant/resource authorization still fails closed even when the SAML response is valid and small.
- [ ] Reject duplicate `SAMLResponse`, RelayState injection, untrusted route/tenant selectors, or out-of-policy Content-Encoding.
- [ ] ACS guard does not break Spring Security SAML CSRF/request correlation logic.
- [ ] SAML SLO/metadata XML/HTTP-Redirect bindings have separate budget/XXE/SSRF controls.
- [ ] Over-budget responses return sanitized errors (413/400/415 or appropriate auth failure), avoiding login loops.
- [ ] Monitoring records size/count/latency/rate/heap trends with bounded labels, without logging raw SAML/XML/PII.
- [ ] Tested with real signed IdP fixtures and encrypted assertions, not solely unsigned/mutated XML.
- [ ] Negative tests cover limit-1/limit/limit+1, malformed Base64, XXE, deep nodes, group explosion, duplicate form params, and signature wrapping.
- [ ] Integration/performance tests measure p95/p99 parsing, heap, GC, and serialized session bytes under peak concurrency.
- [ ] All pods/ingress regions share the same policy, with canary/revert and version metadata.
- [ ] Runbook exists to pinpoint the failing layer when an IdP changes group release; never disable size limits with unlimited values.
- [ ] Per-trusted-IdP/registration exceptions undergo review, expiration, and audit, never taken from untrusted queries/headers.
- [ ] All certificates/signing credentials, sample assertions, and user attributes are protected across staging/CI/production.
- [ ] Clearly distinguished **HTTP size PASS** from **SAML authentication PASS** and **business authorization PASS**.

**Conclusion:** Resource hardening for SAML Web SSO requires **defense in depth**: raw HTTP body limits at the edge, form size/parameter-count limits in the Servlet container, Base64 and XML byte limits before OpenSAML, hardened XML parsing/crypto validation, and **post-verification attribute budgets** to prevent identity, authority, and session bloat. No single layer replaces another. A secure SP rejects entire oversized requests, continues validating signature/issuer/audience/recipient/time on small requests, maps only trusted data, and enforces separate tenant/resource policies.

## 23. Official References

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): HTTP-POST `SAMLResponse`, ACS endpoints, `Saml2WebSsoAuthenticationFilter`, and OpenSAML validation flow.
2. [Spring Security – Authenticating SAML 2.0 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): Response converter, signature/conditions validation, assertions, attributes, custom provider, and migration differences.
3. [Spring Security 6.5 – Saml2WebSsoAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/saml2/provider/service/web/authentication/Saml2WebSsoAuthenticationFilter.html): SAML SSO ingestion path.
4. [Spring Security 6.5 – Saml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `Map<String,List<Object>>` attributes and `getFirstAttribute`.
5. [Spring Security – SAML2 migration notes](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/migration-7/saml2.html): API changes and OpenSaml5AuthenticationProvider response converter.
6. [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `server.tomcat.max-http-form-post-size`, `max-parameter-count`, `max-swallow-size`, and header size.
7. [Apache Tomcat – HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): `maxPostSize`, `maxParameterCount`, why form parameter parsing differs from raw body limit.
8. [NGINX – ngx_http_core_module: client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size): request body/HTTP 413 limit.
9. [NGINX – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): buffering, `proxy_pass`, and upstream HTTPS.
10. [OASIS – SAML 2.0 HTTP Bindings Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-POST/Redirect bindings, Base64, RelayState, and transport profile.
11. [OASIS – SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Response`, `Assertion`, `AttributeStatement`, conditions, and XML objects.
12. [OWASP – XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): DOCTYPE, external entities, secure JAXP factories.
13. [OWASP – Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): application/resource limits and request flooding.
14. [Oracle Java 17 – JAXP Security Guide](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html): `jdk.xml.*` processing limits, `FEATURE_SECURE_PROCESSING`, and external access.
15. [OWASP – XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): XML parser hardening and XML signature handling.
16. [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoid logging sensitive data, bounded event structure.
17. [OWASP – Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): allowlists and input size/structure bounds.
18. [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): validating inputs/responses and session boundaries.
