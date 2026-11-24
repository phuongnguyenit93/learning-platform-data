# Controlling Metadata URLs, HTTP Redirects, and SSRF Risks in SAML2

> **Context:** Spring Security – federation, **SAML2 Metadata** section. This lesson focuses on how a Service Provider (SP/Relying Party) retrieves Identity Provider (IdP/Asserting Party) metadata from a trusted source, how to handle HTTP redirects, and **Server-Side Request Forgery (SSRF)** risks when metadata URLs are externally controlled. It also distinguishes SP metadata publishing URLs from SAML login flow redirects, which serve different functions.

## 1. Why Are Metadata URLs a Security Boundary?

In SAML2 federation, metadata is not merely an XML file describing a system: it carries data deciding **whom the application trusts and where messages are sent/received**. IdP metadata typically contains `entityID`, `IDPSSODescriptor`, `SingleSignOnService` endpoints per supported binding, X.509 certificates for signature verification, and sometimes Single Logout endpoints. SP metadata typically contains `entityID`, `SPSSODescriptor`, `AssertionConsumerService`, and SP public certificates if configured.

If an application lets any user, tenant, or partner supply a metadata URL and the backend fetches it automatically, the backend becomes an **HTTP client operating inside the internal network** at an outsider's command. That is an SSRF gateway. Moreover, if the fetched metadata is accepted unconditionally, an adversary can swap the IdP key/endpoint trusted by the SP, leading to **federation trust hijacking**, even without reaching internal network services.

**Two independent risk classes to defend against:**

1. **SSRF on the fetch path:** the backend sends HTTP requests to unauthorized IPs/hosts/paths, potentially reaching loopback, private networks, admin services, or cloud instance metadata services.
2. **Trust relationship poisoning:** the returned XML causes the SP to swap the `entityID`, SSO URL, or public key used to validate `SAMLResponse` from the IdP. If the verifier takes certificates from untrusted XML, forged assertion signatures will pass because the attacker chose the key.

These two checks do not replace each other. A completely public HTTPS URL can return forged metadata; validly signed metadata from a registered source still must not allow the backend to blindly follow redirects to an internal host.

### 1.1. Identifying URLs and Their Roles Correctly

| Value / Endpoint | Typically used by whom? | Does the Spring app fetch it over the network? | Meaning |
| --- | --- | --- | --- |
| **IdP metadata location** such as `https://idp.partner.example/saml/metadata` | SP backend or metadata refresh job | **Yes, if configured to use metadata via URL** | XML source establishing IdP configuration |
| **IdP `entityID`** such as `https://idp.partner.example/issuer` | SP's SAML validator | **Not automatically just because it looks like a URL** | Logical IdP identifier; compared against issuer in SAML |
| **`SingleSignOnService Location`** | Browser redirected to IdP during SP-initiated SSO | Primarily the destination of browser SAML flows | Endpoint receiving `AuthnRequest`; must still be approved |
| **SP metadata URL** such as `https://sp.example.org/saml2/metadata/partner` | IdP/operations reading SP metadata | **Published by the SP** | Advertises SP's entityID, ACS, and public certificates |
| **SP ACS** such as `https://sp.example.org/login/saml2/sso/partner` | Browser POSTs `SAMLResponse` from IdP | Not a URL for fetching IdP metadata | Spring endpoint verifying assertions and creating sessions |
| **Cloud instance metadata** such as `169.254.169.254` | Host/internal cloud agents | **Not SAML metadata** | May expose infrastructure/credentials; common SSRF target |

**Rule to remember:** `entityID` is an **identifier**, not an instruction saying "GET this URL". Only URLs designated as network endpoints should serve as request targets, and they must still belong to the trust contract.

## 2. IdP Metadata Fetch Flow and How SSRF Happens

Valid flow:

```text
[Administrator approves IdP]
             |
             v
[Static URL or metadata file configuration]
             |
             v
[Backend SP / metadata fetch job]
             |
             | HTTPS GET only to permitted destination
             v
[IdP metadata endpoint]
             |
             | XML (entityID, SSO endpoints, signing certs)
             v
[Verify source + integrity + partner + structure]
             |
             v
[RelyingPartyRegistration / repository]
             |
             v
[Verify SAMLResponse during login]
```

Typical broken flow:

```text
[User/tenant enters arbitrary metadataUrl]
                    |
                    v
[Backend GETs metadataUrl]
                    |
                    | First server returns 302 Location: internal host
                    v
[HTTP client auto-follows redirect]
                    |
                    v
[127.0.0.1 / private network / admin service / cloud metadata]
                    |
                    v
[Response leaked or request causes side effects inside network]
```

SSRF can occur **before any valid SAML XML ever appears**. If the system exposes response bodies, errors, or request latencies back to whoever submitted the URL, an attacker can map internal services. Even without returning the body, "blind" SSRF can trigger side effects or leak host availability via timing.

### 2.1. Places Where External URLs Easily Slip In

- **"Add identity provider"** forms in multi-tenant systems letting users enter a metadata URL.
- Partner onboarding APIs accepting JSON with `metadataUrl` or `metadata_uri` and calling `RelyingPartyRegistrations.fromMetadataLocation(value)` directly in the request.
- Periodic metadata refresh schedulers reading URLs from a database editable by lower-privileged tenant/admins.
- "Test metadata", "Validate SAML connection", or "Preview IdP settings" features fetching URLs to inspect them.
- Federation aggregate metadata loaders containing referenced URLs, imports, resolvers, or external resource fetches.
- APIs accepting a partner's "SP metadata URL" and having the server proactively fetch it, when all operations actually need is an admin uploading a vetted file separately.

Never assume a metadata-fetching API "is only for admins" and is therefore safe: a tenant-level admin must not be allowed to steer an HTTP client into the host platform's internal networks or credentials. Separate **identity configuration privileges** from **network connection control**.

### 2.2. Cascading Risks When Metadata Is Altered

If an attacker can replace IdP metadata, they can inject a new X.509 certificate under `KeyDescriptor use="signing"` or point to their own SSO endpoint. An SP that fetches and accepts the new metadata may start trusting assertions signed by the attacker. Therefore, a single successful HTTPS fetch **never authorizes** changing the IdP's trusted keys without a verification process; TLS only authenticates the connection to the target server under PKI trust, not authority to alter federation configuration.

## 3. Distinguishing Three Easily Confused "Redirects"

| Name | Who performs it? | Example | How does it relate to SSRF? |
| --- | --- | --- | --- |
| **SAML HTTP-Redirect Binding** | SP/IdP directs the **browser** to an SSO endpoint, passing encoded SAML messages in the URL | Browser goes to IdP with `SAMLRequest` and possibly `RelayState` | It is a SAML protocol binding; **not** the backend fetching metadata |
| **HTTP 30x when backend fetches metadata** | Metadata server returns `301`, `302`, `303`, `307`, or `308` with `Location` | GET metadata returns 302 to a new host/URL | If the HTTP client auto-follows `Location` without re-validating the target, it can cause SSRF |
| **Application/web login HTTP redirect** | Web app redirects browser to login page or post-login target | `302 Location: /login` or to IdP | Usually not SSRF; however, `returnUrl`/`RelayState` must not create an **open redirect** to arbitrary domains |

At the HTTP level, a SAML AuthnRequest using HTTP-Redirect Binding may use status 302 to send the **browser** to the IdP. Meanwhile, the Spring backend **fetching metadata** and auto-following 302s is governed by **the backend's HTTP client and URL policy**. These differ in actor, target resource, and trust level.

**Safest way to handle redirects when fetching metadata:** do not auto-follow HTTP redirects. If an IdP officially moves metadata to a new URL, require an admin to approve the new URL, update the allowlist, and re-verify keys/issuer. Never treat `301 Moved Permanently` as permission to automatically expand trust. If a business requirement forces following redirects, every hop must undergo the same validation as the initial URL, cap hop counts, forbid HTTPS→HTTP downgrades, and defend against DNS rebinding/redirect loops; the simpler and safer choice remains **fail closed on every 30x**.

## 4. URL Control Policy: Prefer Configuration from Trusted Sources

### 4.1. Authorize Per Partner, Never Arbitrary URLs

For a federation with a bounded list of IdPs, maintain a catalog:

| Attribute | Illustrative Example |
| --- | --- |
| Partner / tenant | `partner-a` |
| Internal Registration ID | `partner` |
| Approved metadata URL | `https://idp.partner.example/saml/metadata` |
| Expected IdP entityID | `https://idp.partner.example/issuer` |
| Permitted hosts/IPs/network paths | Approved by infrastructure team, routed via dedicated egress policy |
| Trusted metadata/IdP signing cert | Approved key or fingerprint, rollover procedure |
| Audit/refresh interval | Policy-driven, with owner and monitoring |
| Change approver | Federation owner and security/IdP lead |

Instead of accepting a full URL from callers, clients can send just an identified **partnerId**, and the server **retrieves the configured URL from an admin-controlled catalog**. This eliminates parser bugs, userinfo (`user@host`), scheme changes, ports, paths, or query smuggling.

If tenants genuinely need to onboard new IdPs, use a **propose → verify → approve → activate** workflow. Never fetch a new URL directly inside a public request using a worker with access to internal networks.

### 4.2. When URLs Must Be Accepted, Enforce Multi-Layer Controls

1. **Scheme:** require `https` in production; reject `http`, `file`, `jar`, `ftp`, `gopher`, `data`, and unapproved schemes. `classpath:` is solely for packaged app-controlled resources, never a scheme for tenants to choose.
2. **Hostname/FQDN:** match against an **exact** allowlist; never use `contains("trusted.example")` or `endsWith("trusted.example")` without dot-boundary checks. Names like `trusted.example.attacker.invalid` must be rejected.
3. **Port:** allow only approved TLS ports, typically 443; block admin, database, and arbitrary ports.
4. **Path/query:** use fixed configured paths/URLs; never concatenate raw path/query input to build fetch URLs.
5. **Userinfo/fragment:** disallow `username:password@host`, unusual fragments, empty URLs, or parser ambiguities. If policy allows only one canonical URL, **compare the entire approved URL** and issue requests from that canonical URI.
6. **Resolved target IP:** DNS can return loopback, private, link-local, unique-local IPv6, multicast, or cloud metadata IPs; network policy must decide valid IPs and **pin connections to verified IPs** or block at egress. Checking DNS first and letting the HTTP client re-resolve later is vulnerable to **DNS rebinding / TOCTOU**.
7. **HTTP redirects:** disable auto-follow and treat 30x as a controlled error. Never allow HTTPS-to-HTTP downgrades.
8. **Network intermediaries:** if the HTTP client uses a proxy, the forward proxy/egress gateway must also enforce destination allowlists and forbid tunneling past policy.
9. **Response handling:** cap payload size, connect/read timeouts, acceptable content types, retry counts, and refresh rates. Parse XML only through a hardened SAML parser/library.
10. **Fetch worker isolation:** run under a service account without permissions to read unnecessary cloud credentials/metadata, restrict outbound privileges, and isolate from internal admin APIs.

**Never rely on a standalone blocklist.** Blocking a few IPs like `127.0.0.1` or `169.254.169.254` easily misses IPv6, private subnets, DNS aliases, or alternate IP notations. When real deployments require private IdPs, explicitly **approve and isolate** those private IP/endpoints rather than applying a blanket "block all private IPs" rule that breaks valid integrations and leads teams to disable checks.

### 4.3. DNS Rebinding Is a Connect-Time Flaw, Not Just Syntax

An easy-to-miss flawed flow:

```text
1. Resolve idp.partner.example -> public IP
2. Verify IP is public, mark safe
3. HTTP client re-resolves hostname afterward
4. Second DNS lookup returns internal IP
5. HTTP client connects to internal IP
```

This is a race condition between **DNS validation** and **the actual connection**. Mitigations include an egress proxy permitting only approved hosts/destinations, a controlled resolver, connection pinning to the verified IP while preserving SNI/Host and hostname certificate checks, or network-layer blocks on prohibited ranges. **Java's `HttpClient` in the example below does not provide IP pinning for all cases on its own.** Thus URI checks plus disabling redirects in code are necessary, yet **insufficient** if an allowed domain's DNS can be manipulated.

## 5. Spring Security: Two Distinct Metadata Configuration Approaches

### 5.1. Loading IdP Metadata from an Admin-Approved URL

Spring Security supports building `RelyingPartyRegistration` from a metadata location, for example:

```java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("https://idp.partner.example/saml/metadata")
        .registrationId("partner")
        .build();
```

This is an **illustrative snippet** for a Spring Security app with the `spring-security-saml2-service-provider` dependency and appropriate imports. `fromMetadataLocation` reads metadata from the given location. When the location is a network URL, **fetching occurs from the backend** using the library's resource/client behavior. Never pass `request.getParameter("metadataUrl")` or a tenant JSON field directly into this call.

**Important:** Do not assume Spring's metadata loading API automatically enforces your organization's full anti-SSRF policy. HTTP redirect, timeout, proxy, XML/metadata refresh, and signature verification behavior depend on the exact version, configuration, and API; test and wrap with appropriate policy enforcement.

Building a registration from metadata does not mean **every signing certificate inside that XML is trustworthy**. Verify the source, expected entityID, trusted key source, refresh conditions, and change controls. For signed metadata, configure proper **trust anchors/verification credentials**; never assume that just because XML contains `<Signature>`, its signature was verified against an independently trusted key.

### 5.2. Locking Metadata Source to an Approved `classpath` Resource

For infrequently changing IdPs or labs with vetted metadata, a simpler-to-govern approach is retrieving the XML through a trusted admin channel, verifying it offline, and packaging it with the release.

File: `src/main/resources/saml/idp-partner-approved.xml` (a **real, intact, approved** XML document, not a file freshly generated from user claims).

The Java Spring Security 6+/Java 17+ config below builds the registration from a classpath file and enables SAML login/metadata; this code belongs in a Spring Boot project with Spring Web and `spring-security-saml2-service-provider`, **not a standalone program runnable with raw `javac`**.

```java
package com.example.samlmetadata;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration partner =
            RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/idp-partner-approved.xml")
                .registrationId("partner")
                .build();
        return new InMemoryRelyingPartyRegistrationRepository(partner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/saml2/authenticate/**",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**")
                    .permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/login/saml2/sso",
                    "/login/saml2/sso/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
```

**Explanation:**

- Spring loads IdP config from `classpath` when creating the bean; no IdP metadata URL comes from requests or other tenants.
- `registrationId` is `partner`, used to distinguish registrations; it is **not a network URL** and must never be resolved as a fetch host.
- `saml2Login` handles AuthnRequest and `SAMLResponse`; `saml2Metadata` **publishes the SP's metadata**. Both DSLs serve opposite data directions.
- Public endpoints in the example still pass through SecurityFilterChain; `permitAll` does not bypass SAML signature verification at the ACS.
- Even when stored on the classpath, metadata XML must be verified from a trusted source and checked for `entityID` and certificates before build; file updates must go through review/CI/CD. Never treat "already on the classpath" as proof the metadata is right.
- This configuration does not handle assertion decryption, request signing, or SLO if required by the IdP; configure RP settings accordingly once agreed with the IdP.

**Lifecycle trade-off:** Classpath loading prevents arbitrary runtime outbound metadata fetches, at the cost of requiring an update process for certificates/endpoints when the IdP rotates keys. Dynamic refresh is safe when using approved data/sources and verifying before updating the trust store, never when triggered by user-supplied URLs.

## 6. Java 17+ Pattern for an HTTP Client Fetching Approved URLs and Rejecting Redirects

The example below uses **a single fixed metadata URL**. It demonstrates bounding HTTP redirects, timeouts, and body size, while **never using an incoming request URL to issue network requests**. `idp.partner.example` is an illustrative domain; the class compiles standalone with JDK 17+, though actually fetching metadata requires replacing the **admin-approved constant** with a valid HTTPS endpoint, ensuring trusted egress/TLS/CA, and validating XML after download.

File `ApprovedMetadataFetch.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ApprovedMetadataFetch {
    private static final URI APPROVED =
        URI.create("https://idp.partner.example/saml/metadata");

    private static final int MAX_BYTES = 1024 * 1024;

    private ApprovedMetadataFetch() {
    }

    // Used only to illustrate exact URL allowlist; always fetch using APPROVED.
    static boolean isApproved(String candidate) {
        return APPROVED.toASCIIString().equals(candidate);
    }

    static byte[] fetchApproved() throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpRequest request = HttpRequest.newBuilder(APPROVED)
            .timeout(Duration.ofSeconds(8))
            .header("Accept", "application/samlmetadata+xml, application/xml")
            .GET()
            .build();

        HttpResponse<InputStream> response =
            client.send(request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            // Includes 301, 302, 303, 307, and 308: all are rejected.
            if (response.statusCode() != 200) {
                throw new IOException(
                    "Metadata fetch returned HTTP " + response.statusCode());
            }

            byte[] buffer = new byte[8192];
            int total = 0;
            int n;

            while ((n = body.read(buffer)) != -1) {
                total += n;
                if (total > MAX_BYTES) {
                    throw new IOException("Metadata exceeds byte limit");
                }
                output.write(buffer, 0, n);
            }

            return output.toByteArray();
        }
    }

    public static void main(String[] args) {
        System.out.println(isApproved(
            "https://idp.partner.example/saml/metadata"));
        System.out.println(isApproved(
            "http://idp.partner.example/saml/metadata"));
        System.out.println(isApproved(
            "https://idp.partner.example/other"));
        System.out.println(isApproved(
            "https://idp.partner.example/saml/metadata?next=1"));
    }
}
```

Compile/run command for **pure Java policy portion only** (no HTTP calls, no Spring required):

```bash
javac --release 17 ApprovedMetadataFetch.java
java ApprovedMetadataFetch
```

Exact stdout:

```text
true
false
false
false
```

**What the code accomplishes:**

- Builds requests solely to the `APPROVED` constant, **never** using `candidate` as a fetch target.
- `Redirect.NEVER` refuses to follow any 30x status; `response.statusCode() != 200` turns redirects into errors.
- Enforces connect timeout, request timeout, and an XML body byte limit while reading.
- Java's default HTTPS client still validates TLS certificates via the configured truststore; never installs a trust-all manager or disables hostname verification.
- Closes streams on success or failure; never prints body/token contents to the console.

**What the code intentionally omits and why extra layers are required:**

- Does not mitigate **DNS rebinding** or pin connections to approved IPs; DNS/egress policy must control paths to permitted domains.
- Does not parse XML, check `entityID`, certificate/metadata signatures, `validUntil`, or rollover policy; **never load downloaded `byte[]` directly into the trust store** without vetting.
- Does not implement retry/cache/ETag, large legitimate metadata, or off-heap resource caps; tune limits based on real IdPs and system policy.
- Does not verify `Content-Type`, response encoding, or XML safety; `Content-Type` is only a hint, not a security verification.
- Does not accommodate private IdP endpoints; those require explicit network-layer connectivity/allowlists rather than stripping all restrictions.
- Does not turn URL allowlist logic into an enterprise onboarding service; an illustrative constant does not replace enterprise configuration management.

### 6.1. Why Never Call `fromMetadataLocation(candidate)` Directly?

Example **never to write** in a public API:

```java
// Anti-pattern illustration, do not use in production:
String url = request.getParameter("metadataUrl");
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation(url)
    .registrationId("tenant")
    .build();
```

Beyond network risks, an adversary can inject attacker-controlled metadata into the registration, dictating which issuer/certificate the SP trusts. Never let `onboard`, `preview`, or `validate` features turn string-input privileges into **authentication trust establishment privileges**.

Proper multi-tenant architecture:

```text
Tenant submits integration request
          |
          v
Store request in "pending" status
          |
          v
Approval team checks IdP owner, issuer, metadata URL,
certificates, IP/egress, and data permissions
          |
          v
Job fetches from approved URI, no redirect following,
bounded timeout/size, verifies XML/trust
          |
          v
Store approved metadata version
          |
          v
Create/update corresponding registration
          |
          v
Monitor and manage refresh/rollover
```

## 7. Controlling XML and SAML2 Metadata Integrity

SSRF via URL is only half the problem. Once XML arrives, the application must treat its content **as authoritative authentication configuration**.

### 7.1. Structure and Fields to Review

Valid IdP metadata normally uses `EntityDescriptor` with `entityID` and `IDPSSODescriptor`. Simplified structural example, **not XML usable for real login**:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.partner.example/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- Public X.509 certificate data would appear here -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.partner.example/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

Before loading into `RelyingPartyRegistrationRepository`, verify:

1. `entityID` matches **the contracted IdP identifier**, never blindly picking the first element when XML has multiple `EntityDescriptor` entries.
2. `IDPSSODescriptor` is present, conforms to SAML 2.0 protocol, and lists supported/approved bindings and SSO endpoints.
3. `KeyDescriptor` belongs to the trusted issuer, certificates comply with policy with no anomalous key swaps; distinguish certificates verifying **SAML signatures** from certificates verifying **metadata signatures** when present.
4. `validUntil`, `cacheDuration`, or refresh mechanisms are properly applied (when present), alongside criteria to reject expired/revoked versions per policy.
5. XML is parsed by a reputable SAML library with unnecessary external entity/DTD features disabled; enforce parser depth, size, and time bounds.
6. Never fetch additional URLs from `Location`, `entityID`, or reference elements merely because they appear in XML; every secondary connection needs its own purpose and allowlist.
7. Compare a **diff** between new and old metadata; changes to signing certificates, issuers, endpoints, or SLO bindings are sensitive modifications requiring review/auditing.

### 7.2. Metadata Signatures Are Not Always Verified by Default

Spring Security provides metadata repository APIs to verify signatures against pre-trusted **verification credentials**, such as `OpenSaml5AssertingPartyMetadataRepository` in corresponding docs. **Never infer that if XML has a signature, Spring already verified it with an independently trusted key**. Spring docs note that without verification credentials configured on that repository API, it **does not perform signature validation**.

Crucially, establish an **independent trust anchor**: a metadata-signing certificate or public key confirmed via an organizational channel, an authenticated TLS server, or vetted and pinned metadata. Taking the certificate embedded inside untrusted XML to verify that same XML's signature lets a forged self-signed file "verify mathematically" without proving it belongs to the agreed IdP.

**Additional distinction:** The signing certificate in IdP metadata is used by the SP to verify **SAMLResponse/Assertion**, whereas the metadata signing certificate verifies the integrity/origin of **the metadata document** when metadata signing is used. These two certificates may be identical or different depending on IdP policy; never equate them automatically.

### 7.3. XXE Can Turn XML Parsers into Another SSRF Channel

Even when metadata fetch URLs are strictly locked down, malicious XML containing **external entities** or DTDs referencing external resources can cause misconfigured parsers to read files or make network calls. Use OpenSAML and framework parsers with secure defaults; if parsing XML manually, disable DTD/external entities and external schemas/stylesheets unless needed, and cap memory and parse time. Avoid logging raw XML/tokens on errors.

**Defense sequence:** (1) validate URL and connection → (2) receive size-bounded body → (3) parse XML safely → (4) verify issuer/keys/metadata signature against trust anchor → (5) only then update registration. Skipping any step can break the trust boundary.

## 8. Refreshing Metadata and Rotating Certificates Without Opening Holes

IdP metadata often needs updates when the IdP rotates assertion-signing certificates, SSO endpoints, or SLO policies. Disabling refresh permanently breaks logins once old certificates expire, while refreshing arbitrary user-supplied URLs opens SSRF and trust-poisoning risks.

Recommended workflow:

1. Store the **current metadata version** with issuer, URL/source, fingerprint, fetch time, and approver/workflow.
2. Refresh via scheduled jobs with **dedicated egress**, using only approved sources. New HTTP redirects or domain changes must fail the job and raise alerts.
3. Verify HTTPS, XML, issuer, metadata signature/trust, and certificate diffs. Ensure fetched data matches the right **partner** and never overwrites another registration.
4. Determine whether new metadata is pre-approved or awaits review. If automating key rotation, define strict rules: independent trust anchor, signature validation, change scope, and overlap windows.
5. Update the repository **atomically**, preventing login requests from reading half-updated registrations or mixed old/new certificates.
6. Maintain clear rollback and monitoring: SAML signature errors, metadata fetch 30x responses, issuer/cert diffs, expiring certs, stale metadata, and IdP 5xx responses.
7. On fetch failure, **never fall back to URLs seen in redirects** and never "trust all certificates" to recover. Decisions to retain cached copies or halt new sessions must follow predetermined validity and risk limits.
8. If an issuer/key is suspected of compromise, suspend the trust relationship and remediate existing sessions; merely swapping an XML file is not enough to revoke forged identities already accepted.

In multi-tenant systems, isolate signing credentials, issuers, and refresh schedules per partner; never share one dynamic metadata file across all tenants if governance and contents differ.

## 9. Publishing SP Metadata: Managing URLs, Redirects, and Public Headers

Spring Security can publish SP metadata via the DSL:

```java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
```

Common default endpoints:

- `GET /saml2/metadata` — metadata for the RP registration set.
- `GET /saml2/metadata/{registrationId}` — metadata for a specific RP.
- `GET /saml2/service-provider-metadata/{registrationId}` — compatibility URL for that RP.

**This is the direction where IdPs/partners fetch SP-published metadata**, distinct from the Spring backend downloading IdP metadata. The public metadata endpoint emits public SP XML; unless you add a feature accepting a user URL to fetch, that endpoint **is not SSRF by itself**. Still, enforce controls:

- Published metadata must reflect accurate `entityID`, ACS, bindings, and public certificates for the exact SP/tenant.
- Never let `{baseUrl}` be dictated by `Host`/`X-Forwarded-Host` from untrusted clients. Configure canonical HTTPS hosts and trusted proxies to avoid emitting attacker-controlled ACS/issuers in metadata.
- With multiple tenants, restrict enumerating all registrations via `/saml2/metadata`, publish per-tenant per policy, or distribute metadata over administrative channels.
- Never embed private signing keys, secrets, session cookies, or raw assertions into SP metadata.
- Apply security headers and authorization on public URLs as required; use `permitAll()` rather than bypassing the entire SecurityFilterChain where appropriate.
- If a reverse proxy redirects the metadata endpoint via HTTP→HTTPS `301/302`, the IdP downloader **might not auto-follow**; provide the final canonical HTTPS URL directly, unify the FQDN, and avoid unnecessary redirect chains.

If an app implements an endpoint like `GET /metadata?url=...` where the backend fetches XML from the parameter, that is an **SSRF-prone proxy/fetcher**, not a standard SP metadata endpoint. Never build one just for "convenient debugging".

### 9.1. Beware of Host Headers and Reverse Proxies

For instance, when Spring sits behind a TLS-terminating reverse proxy, the public URL may be `https://sp.example.org` while upstream is `http://app:8080`. If the app trusts client-supplied `X-Forwarded-Proto`/`X-Forwarded-Host`, it can publish metadata with forged `entityID`/ACS values. The proxy must strip client-supplied forwarded headers, inject accurate values, and the backend must trust headers only from trusted proxies. After deployment, GET the live metadata and verify SAML entityID/ACS against IdP configuration.

SP metadata emitting wrong URLs typically causes **`Destination`/`Recipient` mismatches or login loops**, which can never be fixed by skipping SAML signature checks or setting permit-all.

## 10. Threat Model and SSRF Testing Matrix

| Test / Lab Input | Expected Outcome | Evidence to Retain |
| --- | --- | --- |
| Exact approved HTTPS metadata URI on allowlist | Requests only the approved endpoint; processes XML after validation | Audit of partnerId, approved target, verification outcome |
| `http://` instead of `https://` | Rejected due to wrong scheme | Policy error with zero outbound requests |
| Same host yet unapproved port/path/query | Rejected | No connection to arbitrary targets |
| Host looking like partner domain with extra suffix | Rejected | Parser/allowlist unit tests |
| URL with `userinfo@host`, IP literal, IPv6 loopback, internal hostname | Rejected if outside policy | Zero network calls on rejection |
| Permitted endpoint returns HTTP `301/302/303/307/308` with another `Location` | **Does not follow**, returns controlled error | Status log without leaking redirect target secrets |
| HTTPS endpoint returns `Location: http://...` | Never downgrades to HTTP | Zero secondary HTTP requests |
| DNS of permitted host resolves to private/link-local/loopback IP against policy | Blocked at connection/egress layer | Counters, firewall/egress-deny logs, IPv4+IPv6 checks |
| XML with external entity/DTD attempting external URL fetch | Parser performs zero fetches | Sandbox XXE test, no file/network access |
| XML with wrong issuer, invalid metadata signature, or unapproved cert | Trust/repository not updated | Diff/validation failure; prior metadata retained per policy |
| Valid XML unexpectedly changing signing key | Awaits approval or trusted rollover workflow | Key fingerprint audit, approval event |
| Oversized, slow, or never-ending metadata response | Hits timeout/quota, closes connection | Timeout/size metrics, no OOM |
| SP metadata endpoint accessed with spoofed Host header | Does not emit attacker-specified host in entityID/ACS | Verification against canonical HTTPS URL |
| Unauthenticated user calls `/saml2/metadata/partner` | Per publishing policy, receives only **SP public metadata** | No private keys/secrets/assertions exposed |

**Safe testing approach:** use test-team-controlled mock servers, proxies/MockWebServer/WireMock, or sandboxes. Simulate malicious `Location` headers and XML; verify the HTTP client genuinely **makes no second connection**. You never need to hit real admin services or cloud metadata endpoints to prove SSRF defenses work.

When egress controls run on Kubernetes/VMs/cloud, test along the **actual network path** of pods/containers, including forward proxies and IPv6, rather than relying solely on unit-test hostname comparisons.

## 11. Common Errors and Diagnostic Signals

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Initial metadata URL looks valid yet app connects to another host | HTTP client followed 30x, DNS changed, proxy rewrote | Disable redirects, enforce target policy per hop and at egress; inspect network logs |
| Spring startup hangs/fails when IdP metadata unreachable | Remote metadata fetched while building `RelyingPartyRegistration`; timeout or DNS/proxy | Test approved source, check timeouts, use approved classpath snapshot when suitable |
| "Could not resolve" or unparseable metadata error | URL returns HTML login/SSO page, 30x to another page, malformed XML | Never follow/parse HTML; use official metadata endpoint or trusted IdP file |
| Metadata updated cleanly yet SAMLResponse fails signature | Certificate mismatch, IdP rollover, tampered metadata, stale SP cache | Check IdP certificate and rollover workflow; never skip signature checks |
| Metadata URL submitted via tenant form triggers requests to internal IPs | SSRF via URL input, redirect, DNS, or XML parser | Disable arbitrary fetching, block internal egress, audit parser/tenant permissions |
| Metadata has XML signature yet source unverified | Signature verification lacks configured trust anchor | Configure independent verification credentials or vet files out-of-band |
| SP metadata returns HTTP URLs or strange hosts | Proxy forwarded headers/`{baseUrl}` misconfigured | Configure canonical URL/proxy trust; inspect live XML |
| IdP reports SP metadata fails to load due to redirect | SP returns HTTP→HTTPS 301/302 and IdP downloader doesn't follow | Give final HTTPS URL directly, avoid redirect chains |
| Java does not trust IdP's TLS certificate | Broken CA/truststore, hostname mismatch, expired cert | Install valid trust anchor, check chain/SAN/clock; never disable TLS |
| Connection fails after legitimate IP/DNS change | Stale egress allowlist, outdated IP pinning rules | Update destination catalog via change review; never open to all Internet |
| Metadata refreshes repeat excessively | Unbounded scheduler retries, wrong cache interval | Cap timeouts/retries, add backoff and alerts; protect IdP from traffic floods |

**Self-verification sequence:**

```text
1. Is metadata being FETCHED from the IdP or PUBLISHED by the SP?
2. Who entered, who can edit, and who approved the source URL?
3. Does the URL match scheme/host/port/path/query on the allowlist?
4. Can the HTTP client follow 30x or use proxies/redirects outside policy?
5. Can DNS and the actual connection hit loopback/private/link-local?
6. Is the body size/time-bounded and parsed safely as XML?
7. Are EntityID, signing cert, and metadata signature verified against independent trust?
8. Does the new metadata alter trust privileges, endpoints, or certs?
9. Do SAML login, issuer/audience/ACS, and actual SP metadata still match?
```

## 12. Checklist Before Enabling Metadata Refresh in Production

- [ ] Only approved partners/IdPs have active metadata URLs; regular users cannot submit URLs for backend fetching.
- [ ] HTTPS endpoints pin host, port, and path/query; arbitrary userinfo/schemes/ports/hosts rejected.
- [ ] HTTP client does not follow 30x; timeouts, body size, retries, and resource quotas are bounded.
- [ ] DNS/egress policy blocks prohibited destinations, including IPv4/IPv6, proxies, loopback, private/link-local, and cloud instance metadata.
- [ ] XML parser is hardened against XXE/external entities and overly deep/large XML; blocks unapproved URL references.
- [ ] Verified entityID and IdP metadata role; signing certificate changes require review or metadata signature trust anchor verification.
- [ ] Fetched results are never turned into `RelyingPartyRegistration` until passing policy and approval checks.
- [ ] Refresh includes versioning, auditing, alerts, cache/expiry/rollover, rollback, and clear outage handling.
- [ ] `saml2Metadata` publishes SP metadata with the canonical HTTPS host and exact tenant, leaking no secrets.
- [ ] Tests pass rejecting redirects, spoofed URIs, DNS rebinding, XXE, wrong-issuer XML, untrusted certificates, and oversized metadata.
- [ ] Incident playbook defines how to suspend an IdP/registration, reject assertions, and handle active sessions if metadata is poisoned.

**Final message:** Metadata URLs are part of **the privilege of establishing trust relationships**. Spring Security helps parse SAML metadata and create registrations, yet the application must still govern **who can choose metadata sources**, **where the HTTP client actually connects**, **redirects and XML**, and **which keys/certificates are trusted**. Implemented properly, a partner can update metadata only within agreed bounds; SSO configuration features can never be abused to turn the backend into an internal network proxy.

## 13. References

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — `RelyingPartyRegistrations.fromMetadataLocation`, `fromMetadata(InputStream)`, repositories, and SAML endpoints.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — parsing IdP metadata, publishing SP metadata, verifying metadata signatures with verification credentials.
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — HTTP-Redirect Binding and metadata.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — allowlists, HTTP redirects, DNS rebinding, and defense in depth.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html) — protecting XML parsers against XXE.
- [MITRE CWE-918 — Server-Side Request Forgery](https://cwe.mitre.org/data/definitions/918.html) — SSRF definition and vulnerability model.
