# Mapping Domains, Paths, and Tenants to Approved Configurations

> **Module:** Spring Security – Federation. **Parent context:** Multiple IdPs and Tenants. This lesson focuses on turning a hostname, path, and user-chosen tenant into **an admin-approved `RelyingPartyRegistration`**, while re-verifying the tenant after the SAML Response is authenticated. Examples: **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x (Servlet)**. When using Spring Security 7.x, re-check the APIs and OpenSAML version; do not copy old patterns verbatim without testing.

## 1. Objectives and Prerequisites

After this lesson, learners will be able to:

1. Distinguish **business tenant**, **hostname/domain**, **application path**, **Spring Security `registrationId`**, **IdP entity ID**, **SP entity ID**, and **Assertion Consumer Service (ACS)**.
2. Design a `(host, path tenant) → allowlisted registrationId` mapping table that is **deny-by-default**, never accepting an arbitrary metadata/IdP URL from the browser.
3. Use Spring `RelyingPartyRegistrationRepository` to register multiple SP–IdP pairs while allowing only approved links to operate.
4. Control the **login initiation path** (`/saml2/authenticate/{registrationId}`), the **SAML callback** (`/login/saml2/sso/{registrationId}`), and **business resources** after authentication.
5. Explain how Spring resolves a registration from path, saved AuthnRequest, or issuer hint, and why data parsed from unverified XML is not a trusted source.
6. Bind IdP issuer, signing certificate, SP entity ID/Audience, Destination/Recipient, `InResponseTo`, and HTTP session to the right tenant.
7. Prevent **cross-tenant login**, **confused deputy**, **host-header poisoning**, **open redirect**, **SSRF from metadata URLs**, and **identity collision** across IdPs.
8. Write working Java 17 code to test mappings, integrate Spring Security SAML with two tenants, and build a negative test matrix.
9. Separate **pre-login IdP selection** from **post-login tenant authorization**; the latter cannot rely solely on query/path, domain, or email.

**Prerequisites:** HTTP/HTTPS, Host and reverse proxies, path variables, Spring MVC, `SecurityFilterChain`, SAML `AuthnRequest`/`Response`/`Assertion`, `RelyingPartyRegistration`, Session and `SecurityContext`, IdP metadata, and XML signatures.

## 2. Problem: One Application Serving Multiple IdPs and Tenants

Suppose a Portal serves two enterprise customers, **Acme** and **Beta**. Each customer has its own IdP and requires its own login flow. A clear design:

| Internal Tenant | Allowed Public Host | Login Start Path | Spring `registrationId` | Approved IdP Entity ID | SP Entity ID | Registered ACS |
| --- | --- | --- | --- | --- | --- | --- |
| `acme` | `acme.portal.example.org` | `/t/acme/login` | `acme` | `https://idp.acme.example.org/saml` | `urn:portal:acme:sp` | `https://acme.portal.example.org/login/saml2/sso/acme` |
| `beta` | `beta.portal.example.org` | `/t/beta/login` | `beta` | `https://idp.beta.example.org/saml` | `urn:portal:beta:sp` | `https://beta.portal.example.org/login/saml2/sso/beta` |

These addresses are **examples**, not live IdPs. In a real organization, IdP metadata, entity IDs, signing certificates, SP entity ID, and ACS URLs must be managed per approved partner record.

**Rule:** A request to `acme.portal.example.org/t/acme/login` may route to `registrationId=acme`; a request to `acme.portal.example.org/t/beta/login` must be **rejected**, even though `beta` is a real registration. Looking only at the path lets an attacker pick an IdP outside the hostname's tenant. Looking only at `Host` may cause the app to ignore the path's tenant. You must **check both** and define an explicit policy.

### 2.1. Concepts That Are NOT Synonymous

| Concept | What Is It? | What Can It Be Used For? |
| --- | --- | --- |
| Tenant ID `acme` | Internal key for the data and account domain in the app | Authorization, identity linking, policy |
| Host `acme.portal.example.org` | Public domain of the application entrypoint | Tenant route hint if **protected and allowlisted by ingress/edge** |
| Path `/t/acme/login` | UI route used to initiate login | Input to select a tenant **within the approved list** |
| Registration ID `acme` | Spring key to look up `RelyingPartyRegistration` | Selects SP/IdP config pair, not proof that user belongs to the tenant |
| IdP entity ID | `Issuer` of the Response/Assertion sender | Binds trust to the exact IdP |
| SP entity ID | `AudienceRestriction/Audience` issued by the IdP for the SP | Binds which application may use the Assertion |
| ACS | SP URL receiving `SAMLResponse` | Verifies `Destination` and bearer `Recipient` |
| Metadata URI | Admin address used to load IdP metadata | Bootstraps SP/IdP pair from an approved source, **never a user-submitted URL** |
| NameID | Identity within the IdP's namespace/format | Identity link **after signature and SAML conditions pass** |
| `RelayState` | Binding/flow-dependent state | Assists navigation/correlation; does not prove tenant or identity |

One tenant may have **multiple approved IdPs** during a migration, such as `acme-primary` and `acme-backup`. One IdP may serve **multiple tenants** if designed that way, yet the application must never infer that every user from that IdP belongs to every tenant. `registrationId` represents the **SP–IdP pair / trust configuration**, whereas business permissions belong to the post-validation account/tenant model.

## 3. Mapping Contract Must Be Deterministic and Closed

Recommended administrative config tables:

~~~text
ApprovedTenantRoutes
  (canonicalHost, tenantSlug) -> registrationId

  ("acme.portal.example.org", "acme") -> "acme"
  ("beta.portal.example.org", "beta") -> "beta"

ApprovedRegistrations
  "acme" -> {trusted IdP A, SP entityID A, ACS A, cert A,...}
  "beta" -> {trusted IdP B, SP entityID B, ACS B, cert B,...}

Any (host, tenantSlug) pair absent from the table -> DENY
Any registrationId absent from the repository -> DENY
Any response failing SAML validation -> DENY
Any principal unauthorized for the tenant -> 403
~~~

### 3.1. What Inputs Can Users Influence?

- HTTP `Host` and `X-Forwarded-Host` can be spoofed if the reverse proxy fails to strip/overwrite them.
- `/t/{tenant}/login` is chosen by the user; `tenant` is only a **candidate**, not proof of identity.
- Query parameters `?tenant=...`, `?idp=...`, `?metadataUrl=...` are completely **untrusted**.
- SAML `Issuer`/`NameID`/`Attributes` before signature verification are browser-transported data, also untrusted.
- `RelayState` and request ID only hold value when bound to a proper flow/session repository.
- A browser-sent `X-Tenant-ID` header cannot replace Identity/Authorization.
- Having `registrationId` inside the ACS URL of a `SAMLResponse` does not prove the Response came from that IdP.

**Selection principle:** A request may specify **a candidate lookup key**, but the server must pass that key through an allowlist/repository and then perform protocol verification. Never build a `RelyingPartyRegistration` from an arbitrary user-supplied URL.

### 3.2. Pre-Auth and Post-Auth Are Two Separate Gates

~~~text
PRE-AUTH (request from browser)
 Host + path tenant
        |
 properly canonicalized from trusted ingress
        |
 exact allowlist route
        |
 existing registrationId
        |
 RelyingPartyRegistrationRepository
        |
 Spring sends AuthnRequest to approved IdP
        |
      IdP SSO
        |
      SAMLResponse
        |
 SAML signature/Issuer/Audience/Destination/
 Recipient/Conditions/InResponseTo validator
        |
 Saml2Authentication (authenticated)
        |
POST-AUTH (accessing business data)
 trusted registrationId + identity link + tenant account
        |
 match tenant of the resource request
        |
 per-tenant authorization / row-level data isolation
        |
      ALLOW or 403
~~~

**Implementing only PRE-AUTH** lets an IdP A account mistakenly access tenant B resources via another URL if the authorization layer fails to check tenancy. **Implementing only POST-AUTH** lets the app send AuthnRequests to mismatched IdPs/ACSs, causing mix-ups and unsafe UX. Both gates are required.

## 4. Safe Domain Mapping: Never Trust Raw `Host`

A public hostname can map to a tenant when the system enforces a protected **ingress boundary**: valid TLS certificates, virtual-host allowlist, traffic routed exclusively through a controlled load balancer/reverse proxy, backend not directly reachable publicly, and forwarded headers impossible for clients to forge.

### 4.1. Flow Through a Reverse Proxy

~~~text
Browser -> TLS acme.portal.example.org
    |
Edge/Ingress:
  - Verify hostname is in the deployed host allowlist
  - Verify TLS/SNI and public route policy
  - Strip external client X-Forwarded-* headers
  - Inject fresh Forwarded/X-Forwarded-* from actual connection
  - Forward only to approved application backends
    |
Backend:
  - request.getServerName() per canonical forwarding config
  - exact-match acme.portal.example.org in allowlist
  - reject values like "Host: evil.example" outside allowlist
~~~

Specifically:

1. **Never** use `request.getHeader("X-Forwarded-Host")` directly as the tenant name.
2. If Spring sets `server.forward-headers-strategy=framework` or equivalent, ensure the edge **sanitizes** headers first and the backend cannot be reached directly. Trusting forwarded headers on a public backend enables host-header poisoning.
3. Do not accept `evil-acme.portal.example.org` simply via `endsWith("portal.example.org")`. Subdomain routing needs exact canonical mapping; wildcard DNS/TLS does not mean every name is an approved tenant.
4. Port, scheme, casing, Unicode/IDNA, trailing dots, and separators must be normalized under **one single policy** at ingress. Do not strip differing characters to "fuzzy-match."
5. When tenants share a hostname, use a **path allowlist** and matching ACS/session setup; do not treat the shared host as proof of tenant.
6. Never turn any user-typed domain into `baseUrl` to generate an SP entity ID, ACS, or IdP URL.

### 4.2. Why Avoid Arbitrary Subdomain Extraction?

Broken pattern:

~~~java
// WRONG: illustrates an anti-pattern only; do not use in production
String tenant = request.getServerName().split("\\.")[0];
String metadata = "https://" + tenant + ".example.com/saml/metadata";
// Without an allowlist/trust check, this lets an attacker influence tenant/URL.
~~~

Even if `tenant` is restricted to alphanumeric characters, that logic can still trigger metadata fetches from unapproved domains or select un-onboarded tenants. Decoding IPs/Unicode, concatenating into URIs, and making network calls also opens up **SSRF** and domain confusion. **Correct:** host/path may only serve as a key to look up an **existing registration** whose metadata URI and cert were admin-approved.

## 5. Path Mapping: Pick the Right Candidate Without Creating an Open Redirect

The `/t/{tenant}/login` path can cleanly deliver a per-tenant login experience. Routing pattern:

| Approved Host | Request | Decision |
| --- | --- | --- |
| `acme.portal.example.org` | `GET /t/acme/login` | 303 → `/saml2/authenticate/acme` |
| `beta.portal.example.org` | `GET /t/beta/login` | 303 → `/saml2/authenticate/beta` |
| `acme.portal.example.org` | `GET /t/beta/login` | 404/deny |
| `unregistered.portal.example.org` | `GET /t/acme/login` | 404/deny |
| `acme.portal.example.org` | `GET /t/ACME/login` | 404/deny unless canonical alias approved |
| `acme.portal.example.org` | `GET /t/acme/login?idp=https://evil.example` | Use fixed acme route only; ignore `idp` param |

**Never redirect to a user-supplied URL.** The redirect target is built from the `registrationId` retrieved from the allowlist table; e.g., `/saml2/authenticate/acme` is an **internal relative path**, not a `returnUrl`/`idpUrl` from the query string. For post-login return-to URLs, permit only server-controlled relative paths/saved requests; never use SAML `RelayState` as an unvalidated open redirect.

### 5.1. Warning About Bypassing the Login Picker Route

A subtle bug: the `GET /t/{tenant}/login` controller has a flawless allowlist, yet Spring Security by default still exposes:

~~~text
GET /saml2/authenticate/{registrationId}
GET /saml2/authenticate?registrationId=...
~~~

If a user on the Acme host calls `/saml2/authenticate/beta` directly, they can **bypass the tenant-selection controller**. Spring Security may still authenticate the Beta registration properly; however, UX, routing policy, and tenant assumptions can break. Therefore, **guard the AuthnRequest initiation endpoint** by host/registration, or define a custom `Saml2AuthenticationRequestResolver` using the same allowlist alongside post-auth tenant checks.

The example in Section 9 uses a **filter that directly blocks disallowed path and query forms** instead of protecting only the controller. For complex production customizations, place tenant decisions in `RelyingPartyRegistrationResolver`/`AuthenticationConverter` and a request resolver tested against your exact Spring Security version.

## 6. `RelyingPartyRegistration`: Trust Configuration, Not Free-Form Input

Spring Security models an SP/IdP pair with `RelyingPartyRegistration`. At minimum it includes:

- `registrationId` – internal key, must be unique.
- SP `entityId` – audience the IdP places in the Assertion.
- SP `assertionConsumerServiceLocation` – ACS/destination and bearer recipient.
- IdP `entityId` – asserting party issuer, from trusted metadata.
- IdP SSO URL, bindings, verification credentials (public signing cert).
- SP signing/decryption credentials if required by the profile/contract.
- SLO metadata/credentials if Single Logout is used.

A `RelyingPartyRegistrationRepository` holds the approved configurations. `InMemoryRelyingPartyRegistrationRepository` fits a fixed set of tenants; larger systems can use a DB-backed config with approval/versioning/caching. Still, a database does not make arbitrary metadata trustworthy: onboarding and refresh must remain controlled.

### 6.1. Do Not Confuse Spring `registrationId` with Issuer

Example:

~~~text
registrationId="acme"                        (Spring key)
IdP entity ID="https://idp.acme.example/saml" (trusted Issuer)
SP entity ID="urn:portal:acme:sp"              (Audience)
ACS="https://acme.portal.example.org/login/saml2/sso/acme"
~~~

A `SAMLResponse` carrying `Issuer=IdP Beta` arriving at `/login/saml2/sso/acme` must not be accepted merely because the URL says `acme`. The provider must verify signature/issuer using **IdP A verification certificates**, audience/recipient/destination against **SP A registration**, and request correlation. If any check fails, reject.

A response signed by IdP Acme with `Audience=urn:portal:beta:sp` must also be rejected at Acme. **A valid signature alone is not enough.**

### 6.2. Default Lookup vs. Custom Lookup

In Spring Security 6.5, `Saml2AuthenticationTokenConverter` can resolve a registration from a saved AuthnRequest or `registrationId` in the request URI; when absent, it can use `Response/Issuer` as a **hint** to look up an existing registration. Parsing XML issuer **does not prove the IdP signed it**; only the OpenSAML provider after full validation establishes an authenticated result.

If the system has multiple IdPs sharing the same Issuer across environments or two registrations with colliding issuers, Issuer inference becomes **ambiguous**. Use callback paths with explicit `registrationId`, session request state, and a custom `AuthenticationConverter`/resolver when truly needed, always matching against the approved repository. Never dynamically create new IdP trust upon seeing an unknown Issuer.

### 6.3. SP-Initiated Sessions and `InResponseTo`

~~~text
Host Acme + /t/acme/login
  -> allowlist: registration acme
  -> AuthnRequest ID="_req-acme-42", Issuer SP Acme
  -> store AuthnRequest + registration in repository/session
  -> browser goes to IdP Acme

IdP Acme:
  -> SAMLResponse InResponseTo="_req-acme-42"
  -> POST https://acme.portal.example.org/login/saml2/sso/acme

SP Acme:
  -> look up saved request, match InResponseTo
  -> verify signature with IdP Acme cert
  -> verify Issuer, Audience, Destination, Recipient, Conditions
  -> create Saml2Authentication with registrationId=acme
~~~

Do not rely on `RelayState` or an unsigned cookie alone to determine the final tenant. Browser state helps locate the pending request, while the SAML Response must still pass cryptographic and protocol validations. If session state is lost on callback due to `SameSite`, proxy, or load balancer issues, **never drop `InResponseTo`** just to force login through.

### 6.4. SP-Initiated vs. IdP-Initiated

**IdP-initiated SSO** may arrive without a prior AuthnRequest. With multiple tenants, it introduces issuer confusion or login CSRF risks if the SP lacks strong state/correlation. If the product does not need it, **forbid unsolicited `SAMLResponse`s** by policy; in Section 9's example, an ACS endpoint without `registrationId` is blocked by the gate, which **does not automatically replace** policies restricting unsolicited SSO on endpoints that do include `registrationId`. Verify the behavior of `Saml2AuthenticationRequestRepository` and validators for your Spring Security version, IdP binding, and security requirements. Never claim that a simple path filter completely blocks IdP-initiated login.

## 7. Identifying Users and Authorizing After SAML Authentication

A SAML response with valid signature/issuer/audience proves a principal according to the IdP. It **does not automatically prove** which tenant's data that person may view, especially when one IdP serves multiple tenants or accounts/emails overlap.

### 7.1. Proper External Identity Key

Instead of using only:

~~~text
key = NameID
or key = email
~~~

design the model as:

~~~text
Trusted IdP entity ID
  + approved registration/tenant context
  + NameID format/qualifiers/value (per IdP contract)
       |
       v
ExternalIdentityKey
       |
       +--> IdentityLink(existing internal_user_id, tenant_id)
                      |
                      +--> UserStatus=ACTIVE?
                      +--> Tenant membership enabled?
                      +--> Allowed group/role mapping?
                      |
                      v
               Authorization for resource
~~~

Never use a transient `NameID` as a long-term account key. Emails can change, be reassigned, or collide across IdPs; **never auto-link accounts across tenants by email**. If using IdP attributes for role mapping, use only protected/verified attributes and partner-approved mapping configurations.

### 7.2. `registrationId` Is Necessary, Not Sufficient

In the example below, `/t/acme/me` checks `principal.getRelyingPartyRegistrationId().equals("acme")` as an **illustrative guard** to prevent cross-registration access. In a real product, you must also check the **identity link to tenant Acme**, whether the user is active, resource permissions, and row-level data filters.

For example, a principal from Acme could authenticate successfully and then attempt:

~~~text
GET https://beta.portal.example.org/t/beta/reports
~~~

If the server only checks `authenticated()` without comparing the principal/account's tenant, the system risks **cross-tenant data exposure**. The authorization layer across APIs, services, and data must enforce tenancy consistently—not just on one demo endpoint.

## 8. Checking Domain, Path, and Tenant Across the Entire Lifecycle

| Stage | Value Trustworthy After Verification | Must Verify | Must Never Do |
| --- | --- | --- | --- |
| HTTP ingress | Host/scheme established by trusted edge | Host allowlist, TLS, canonical public routes | Trust uncontrolled raw forwarded headers |
| Tenant picker/login | Allowlisted `(host, pathTenant)` | Maps to an existing registration | Build metadata URLs from tenant string |
| Direct AuthnRequest endpoint | `registrationId` from URL/query | Host–registration binding/guard | Bypass picker to switch to another tenant |
| AuthnRequest | RP registration, SP entity ID, ACS | IdP destination, signing, stored request | Use issuer/key from user input |
| ACS callback | Candidate registration + request state | Signature, issuer, audience, destination, recipient, timing | Treat callback URL alone as sufficient |
| Authentication result | `Saml2Authentication` post provider validation | Trusted `registrationId`, principal, attributes | Provision internal user by NameID/email alone |
| Business API | Internal identity link + tenant + authorities | Tenant membership and resource ownership | Check only `isAuthenticated()` |
| Metadata publication | Approved registration & public cert | Host/ACS/Entity ID match deployment | Publish metadata built from arbitrary `Host` |
| SLO | Authenticated principal/session registration | Matching IdP, signed LogoutRequest/Response, correlation | Trigger cross-tenant logout via query `idp` |

**Every step must fail closed**—never pick a vague "default IdP" when the tenant is unclear. If supporting a tenant picker, list **only the tenants/IdPs the user is allowed to see**; the selection itself must still be revalidated on the server.

## 9. Complete Example: Java 17 + Spring Boot 3.5 + 2 Approved IdPs

This example intentionally uses **two fixed public hosts** with two tenants. The Java code creates two `RelyingPartyRegistration` instances from metadata URIs **hard-coded as the demo environment's admin source**. The routes never take an IdP URL or cert from the request. It protects:

1. `GET /t/{tenant}/login` – selects registration strictly via the `(host, tenant)` map.
2. `GET /saml2/authenticate/{registrationId}` – blocks direct access to another host's registration.
3. `POST /login/saml2/sso/{registrationId}` – blocks another host's ACS path (OpenSAML must still verify the response).
4. `GET /t/{tenant}/me` – reconciles the authenticated registration with the resource's tenant.

**Note:** This demo illustrates routing structure. Running real SAML requires real IdP metadata, IdP app registrations, public TLS/DNS hosts, valid HTTP sessions, and signing/decryption credentials if required by the IdP. Running directly on `localhost` will be rejected by the host allowlist—that is **expected behavior under the documented policy**. Use test hostnames with proper DNS/TLS or adjust the config table for your sandbox; never disable the guard in production.

### 9.1. Structure

~~~text
saml-tenant-router/
├── pom.xml
└── src/main/
    ├── java/demo/TenantSamlApplication.java
    └── resources/application.yml
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-tenant-router</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 9.3. `application.yml`

~~~yaml
server:
  port: 8080
  forward-headers-strategy: none
~~~

In the demo, the application receives the canonical host via ingress or a test client; it does not blindly trust forwarded headers. If a deployment uses a reverse proxy requiring forwarded host/scheme, enable forwarding **only after the proxy strips and sets authoritative headers** and the backend accepts connections solely from the proxy. In multi-host environments, never derive a dynamic base URL from the request to override fixed entity IDs/ACSs.

### 9.4. `src/main/java/demo/TenantSamlApplication.java`

~~~java
package demo;

import java.io.IOException;
import java.net.URI;
import java.util.Locale;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.web.Saml2WebSsoAuthenticationRequestFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class TenantSamlApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantSamlApplication.class, args);
    }

    // Both host and tenant are lookup keys into APPROVED, not inputs
    // for concatenating a client-controlled IdP metadata URL.
    record RouteKey(String host, String tenant) {}
    record TenantRoute(String tenant, String registrationId) {}

    private static final Map<RouteKey, TenantRoute> APPROVED = Map.of(
        new RouteKey("acme.portal.example.org", "acme"),
            new TenantRoute("acme", "acme"),
        new RouteKey("beta.portal.example.org", "beta"),
            new TenantRoute("beta", "beta")
    );

    static String canonicalHost(HttpServletRequest request) {
        // Meaningful only when trusted ingress controls Host/forwarded headers.
        return request.getServerName().toLowerCase(Locale.ROOT);
    }

    static TenantRoute route(HttpServletRequest request, String tenant) {
        TenantRoute result =
            APPROVED.get(new RouteKey(canonicalHost(request), tenant));
        if (result == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Unapproved tenant route");
        }
        return result;
    }

    static boolean allowedRegistration(String host, String registrationId) {
        return APPROVED.entrySet().stream().anyMatch(entry ->
            entry.getKey().host().equals(host) &&
            entry.getValue().registrationId().equals(registrationId));
    }

    @Bean
    RelyingPartyRegistrationRepository registrations() {
        // Metadata locations must be admin-approved.
        // Replace these example URLs with real sandbox IdPs.
        RelyingPartyRegistration acme =
            RelyingPartyRegistrations
                .fromMetadataLocation("https://idp.acme.example.org/metadata")
                .registrationId("acme")
                .entityId("urn:portal:acme:sp")
                .assertionConsumerServiceLocation(
                    "https://acme.portal.example.org/login/saml2/sso/acme")
                .build();

        RelyingPartyRegistration beta =
            RelyingPartyRegistrations
                .fromMetadataLocation("https://idp.beta.example.org/metadata")
                .registrationId("beta")
                .entityId("urn:portal:beta:sp")
                .assertionConsumerServiceLocation(
                    "https://beta.portal.example.org/login/saml2/sso/beta")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(acme, beta);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/t/*/login").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            // Guard runs before the AuthnRequest-generating filter.
            // It does not replace signature/audience validation.
            .addFilterBefore(
                new HostRegistrationGate(),
                Saml2WebSsoAuthenticationRequestFilter.class)
            .build();
    }

    // Guard direct Spring endpoints: the controller picker is NOT
    // the only entry point; default endpoints can still be called directly.
    static class HostRegistrationGate extends OncePerRequestFilter {
        private static final String AUTH = "/saml2/authenticate/";
        private static final String ACS = "/login/saml2/sso/";

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String host = canonicalHost(request);
            String uri = request.getRequestURI();
            String contextPath = request.getContextPath();
            String path = uri.substring(contextPath.length());

            // Disallow query-only registrationId or registration-less ACS
            // in this strict SP-initiated routing demo.
            if (path.equals("/saml2/authenticate") ||
                path.equals("/login/saml2/sso")) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            String registrationId = null;
            if (path.startsWith(AUTH)) {
                registrationId = path.substring(AUTH.length());
            } else if (path.startsWith(ACS)) {
                registrationId = path.substring(ACS.length());
            }

            if (registrationId != null &&
                (registrationId.isBlank() ||
                 registrationId.contains("/") ||
                 !allowedRegistration(host, registrationId))) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            chain.doFilter(request, response);
        }
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String index() {
            return "Use /t/acme/login or /t/beta/login on approved hosts";
        }

        @GetMapping("/t/{tenant}/login")
        ResponseEntity<Void> login(
                @PathVariable String tenant,
                HttpServletRequest request) {
            TenantRoute approved = route(request, tenant);
            // Fixed allowlisted URI; never use a user-submitted redirectUrl.
            return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(
                    "/saml2/authenticate/" + approved.registrationId()))
                .build();
        }

        @GetMapping("/t/{tenant}/me")
        ResponseEntity<Map<String, String>> me(
                @PathVariable String tenant,
                HttpServletRequest request,
                Authentication authentication) {

            TenantRoute approved = route(request, tenant);

            if (!(authentication instanceof Saml2Authentication saml) ||
                !(saml.getPrincipal() instanceof Saml2AuthenticatedPrincipal p) ||
                !approved.registrationId()
                    .equals(p.getRelyingPartyRegistrationId())) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("error", "Tenant registration mismatch"));
            }

            // Demo verifies registration only. Production MUST check
            // IdentityLink, user status, tenant membership, and roles.
            return ResponseEntity.ok(Map.of(
                "tenant", approved.tenant(),
                "registrationId", approved.registrationId()));
        }
    }
}
~~~

### 9.5. Code Explanation

- `APPROVED` holds approved `(canonicalHost, tenant)` pairs and `registrationId`s. There is no fallback. `GET /t/evil/login` or `Host=evil.example` finds no route and returns 404.
- `RelyingPartyRegistrations.fromMetadataLocation(...)` loads **pre-configured** IdP metadata. The demo metadata URIs are examples; production must use real approved IdP URLs with provenance checks, certificate rollover, and policy-controlled network egress.
- `entityId(...)` sets distinct SP entity IDs for Acme/Beta; `assertionConsumerServiceLocation(...)` pins the public HTTPS callback per host/registration. Register these values at the respective IdPs.
- `SecurityFilterChain` permits only the login picker route, keeping business APIs closed to unauthenticated callers.
- `HostRegistrationGate` blocks **direct calls** to `/saml2/authenticate/beta` on the Acme host and `/login/saml2/sso/beta` on the Acme host. It also blocks registration-less routes to reduce ambiguity in the demo. The filter does not replace SAML signature validation.
- `/t/{tenant}/me` verifies that the **authenticated principal's `registrationId`** matches the route's registration; otherwise it returns 403. The demo response omits `NameID`, attributes, and raw `SAMLResponse`.
- To protect a full production app, enforce **tenant authorization at the service/data layer**; the demo controller does not provide row-level security by itself.
- In a cluster, the AuthnRequest repository/session must work across nodes and ingress must preserve canonical hosts. If login starts on Acme and the callback switches to Beta, `HostRegistrationGate` rejects it.
- `getServerName()` assumes the edge enforces the trust boundary. If the backend is exposed directly or Host/forwarded headers are unprotected, **the sample's precondition is not satisfied**. That is an infrastructure requirement, not something Java guarantees alone.
- The implementation uses Java 17 `record` and pattern matching for `instanceof`. You do not need a custom SAML `AuthenticationProvider` or manual XML parsing.

### 9.6. Controlled Setup and Execution

First, integrate **two sandbox IdPs** and register each SP:

~~~text
Acme:
  IdP metadata = approved real URL
  SP entity ID = urn:portal:acme:sp
  ACS = https://acme.portal.example.org/login/saml2/sso/acme

Beta:
  IdP metadata = approved real URL
  SP entity ID = urn:portal:beta:sp
  ACS = https://beta.portal.example.org/login/saml2/sso/beta
~~~

If an IdP requires signed AuthnRequests, configure the SP signing private key and matching public certificate from a secret store. If the IdP issues `EncryptedAssertion`s, add **SP** decryption credentials. Never place an IdP private key into the application. If IdP metadata is unreachable, the registration bean may fail at startup; never mistake using placeholder URLs for running real login.

Run with Java 17 and Maven:

~~~bash
mvn spring-boot:run
~~~

Once sandbox DNS/TLS/Ingress serves the two public hosts, open:

~~~text
https://acme.portal.example.org/t/acme/login
https://beta.portal.example.org/t/beta/login
~~~

The app returns a 303 redirect to the corresponding initiation endpoint; Spring Security generates the AuthnRequest and sends the browser to the right IdP. After valid login, call:

~~~text
https://acme.portal.example.org/t/acme/me
https://beta.portal.example.org/t/beta/me
~~~

Acme's JSON output after a valid SAML login looks like:

~~~json
{"tenant":"acme","registrationId":"acme"}
~~~

This output **depends on a real SAML login** and will not appear if placeholder metadata URLs are left unchanged, if the browser lacks session/correlation, or if validation fails. Even when JSON is returned, production still needs `IdentityLink` and tenant entitlement queries.

### 9.7. Intentional Limitations of the Sample

1. The sample has only **one IdP per tenant**; multiple IdPs per tenant require a routing table with an allowlisted `idpChoice` and appropriate UX.
2. The sample lacks persistence for tenant membership, user status, roles, SCIM provisioning, or DB row-level filters; add these before production.
3. The sample does not register an SP metadata endpoint; if an IdP needs live metadata, enable `.saml2Metadata(Customizer.withDefaults())` and **review whether all registrations/host metadata can be enumerated** alongside your metadata exposure policy, ensuring accurate entity ID/ACS values.
4. Callback `/login/saml2/sso/{registrationId}` processes responses through Spring Security filters; **signature/issuer/audience/recipient/time/correlation** checks must be verified for your exact provider/validator version. The host gate is an additional control.
5. The sample blocks query-only AuthnRequests, yet all custom paths/gateways in production must be audited so no alias bypass exists; never claim the sample filter replaces firewall/ingress policy.
6. The sample is not designed for IdP-initiated SSO; if needed, evaluate login CSRF, replay, route registration, and missing `InResponseTo` for your exact Spring Security version.
7. To test on `localhost`, use explicit test routes matching a sandbox IdP rather than removing canonical-host checks in production builds.
8. The example uses `RelyingPartyRegistrations.fromMetadataLocation` for full metadata. For dynamic metadata onboarding, follow Section 11; **never** concatenate host/tenant strings into IdP URLs.

## 10. Standalone Java 17 Program: Checking Allowlist and Stdout

Before integrating SAML, you can verify the mapping policy as a pure Java function. The program below **runs on JDK 17 with no Spring, Maven, or IdP** and shows that both host and tenant are required to pick a registration.

**File `TenantRouteDemo.java`:**

~~~java
import java.util.Map;

public class TenantRouteDemo {

    record RouteKey(String host, String tenant) {}

    private static final Map<RouteKey, String> APPROVED = Map.of(
        new RouteKey("acme.portal.example.org", "acme"), "acme",
        new RouteKey("beta.portal.example.org", "beta"), "beta"
    );

    static String resolve(String host, String tenant) {
        // host here is assumed already canonicalized by trusted ingress;
        // an arbitrary string does not itself prove network authenticity.
        String registration = APPROVED.get(new RouteKey(host, tenant));
        return registration == null ? "DENY" : registration;
    }

    static void check(String host, String tenant) {
        System.out.println(host + " /t/" + tenant +
                "/login -> " + resolve(host, tenant));
    }

    public static void main(String[] args) {
        check("acme.portal.example.org", "acme");
        check("beta.portal.example.org", "beta");
        check("acme.portal.example.org", "beta");
        check("attacker.example.org", "acme");
        check("acme.portal.example.org", "ACME");
        check("beta.portal.example.org", "../acme");
    }
}
~~~

Run:

~~~bash
javac TenantRouteDemo.java
java TenantRouteDemo
~~~

**Exact stdout:**

~~~text
acme.portal.example.org /t/acme/login -> acme
beta.portal.example.org /t/beta/login -> beta
acme.portal.example.org /t/beta/login -> DENY
attacker.example.org /t/acme/login -> DENY
acme.portal.example.org /t/ACME/login -> DENY
beta.portal.example.org /t/../acme/login -> DENY
~~~

**Explanation:** `Map.get` with the composite key performs an exact match and returns `DENY` when absent. The `../acme` case in the demo is a pure Java test string; in real HTTP, browsers/proxies/frameworks may normalize paths or reject earlier, so never treat this demo output as proof of ingress path-traversal defense. Always test normalized paths and actual route matching in integration tests.

**Never use `resolve(...)` to assert that a user is authenticated or authorized.** It only picks a candidate registration. The SAML response still requires cryptographic verification, and resource authorization still requires an identity link and tenant membership.

## 11. Onboarding New Tenants/IdPs: Approved Configuration Change Workflow

A SaaS system may add tenants frequently, yet **dynamic tenants** do not mean "every client-supplied metadata URL is trustworthy." A standard workflow:

1. **Business approval:** define internal tenant, owner, partner IdP contract, onboarding state, and allowed domains.
2. **Domain ownership:** verify proof of domain/hostname control per policy; configure exact TLS and ingress routes to avoid hijacking existing tenants.
3. **Metadata provenance:** authorized admins or onboarding services load metadata from **pre-verified sources**; pin exact hostnames/URLs or allowlist endpoints; block redirects to internal IPs, link-local addresses, cloud metadata services, or disallowed schemes.
4. **Cryptographic trust:** verify IdP entity ID, public signing certificates, algorithms, and SSO endpoints; never use a cert extracted from an unverified `SAMLResponse`.
5. **SP registration:** assign a unique `registrationId`, SP entity ID, ACS/SLO URLs, and signing/decryption credentials if required. Avoid reusing entity IDs across tenants or colliding callbacks.
6. **Mapping approval:** commit/persist the exact `(canonicalHost, tenantSlug, registrationId)` tuple; verify the referenced approved registration exists. Serve login only for `ACTIVE` records.
7. **Staging tests:** test SP-initiated flow, signed response, issuer/audience/destination/time/correlation, AuthnRequest state, cookies, and negative cross-tenant checks.
8. **Publish/rollout:** deploy ingress/DNS/certs, metadata/trust, app mapping, and identity linking in order; prepare rollback/feature flags and never enable wildcards by default.
9. **Monitor:** track login success/failure by registration, unknown host/route, issuer mismatch, signature failure, audience/ACS mismatch, and missing session/correlation.
10. **Decommission:** stop issuing new AuthnRequests, revoke account links/tokens/sessions per policy, remove the registration from the allowlist, retire IdP trust keys safely, and handle domain reassignment.

### 11.1. Database-Backed Repository

With hundreds of IdPs, configs live in a DB (or config service) instead of a Java `Map`:

~~~text
Table tenant_route:
  canonical_host
  tenant_slug
  registration_id
  status (ACTIVE/INACTIVE)
  approved_by
  version

Table relying_party_config:
  registration_id
  trusted_idp_entity_id
  trusted_metadata_source
  sp_entity_id
  public_acs_uri
  verification_key_refs
  signing_key_refs (secret reference only)
  status
  version
~~~

Only authorized onboarding personnel/pipelines may modify these tables; runtime reads only `ACTIVE` records. Every metadata/key update must undergo validation, auditing, and rollback readiness. Resolved `registrationId` entries in the repository can be cached by version, with explicit invalidation on tenant/key revocation. Never accept a record blindly just because it exists in the DB or was self-submitted by an end user.

### 11.2. SSRF Defenses When Loading Metadata

- Never accept `?metadataUrl=...` or `X-IdP-URL` from end-user requests.
- Allow only approved schemes/hosts/ports; typically HTTPS with full TLS certificate verification.
- Block SSRF via DNS rebinding, redirects to private/link-local IPs, IPv6 local targets, cloud metadata endpoints, and URI userinfo using egress/network policy plus backend validation.
- Use snapshotted/approved metadata or a controlled distribution backend if live metadata refresh carries risk.
- Restrict payload size, content type, and parser settings; monitor certificate rotation regularly and detect unexpected metadata changes.
- **Never** assume a URL returning valid XML means the IdP is trusted.

## 12. Complex Scenarios to Handle

### 12.1. One Tenant with Multiple IdPs

Acme has a primary IdP and a backup IdP:

~~~text
tenant=acme
  -> registrationId=acme-main
  -> registrationId=acme-backup
~~~

Do not accept `?idp=any-url`; let `idpChoice` pick only **a `registrationId` inside Acme's allowlist**. Enabling a backup IdP must be approved, especially if its signing cert or issuer belongs to another system. If users from both IdPs share an email, never auto-link accounts; enforce an identity-linking policy and review process.

### 12.2. One IdP Serving Multiple Tenants

Two tenants share the same IdP entity ID, while the SP may have different entity IDs/ACSs. Reading `Response/Issuer` alone cannot distinguish the tenant because **the Issuer is identical**. Rely on SP-initiated request correlation, the exact registration, and `Audience`/`Recipient`/`Destination` checks; post-authentication, still verify the identity link to the tenant.

### 12.3. Path-Based Tenants on a Shared Host

For example, `portal.example.org/t/acme/login` and `portal.example.org/t/beta/login`. This is permissible with a **route allowlist**, provided you decide how ACS works: you can use `/login/saml2/sso/acme` and `/login/saml2/sso/beta` on the same host with two distinct registrations. Never construct IdP metadata from an arbitrary tenant path. The SAML provider still verifies audience/recipient; business resources must reconcile registration and tenant.

**Warning about shared-cookie sessions on one host:** Users may log into Acme and Beta sequentially within the same browser session, where a new authentication replaces the `SecurityContext`. If **concurrent dual-tenant/identity sessions** are required, design explicit isolation (subdomains, session partitioning, or a tenancy-aware session model)—never assume changing the URL path creates two independent sessions.

### 12.4. Tenant Aliases and Custom Domains

A customer has both `company.example.com` and `acme.portal.example.org` pointing to Acme. Both domains must be approved and explicitly mapped to the registration/tenant. SAML `Destination`/`Recipient` and the IdP ACS may require a **single canonical callback URL**, because starting an AuthnRequest on an alias and receiving the callback on the canonical host can **lose the session cookie**. Have the SSO entrypoint redirect to the canonical host **before initiating the AuthnRequest**, or implement secure server-managed cross-domain state handoff. Never add custom domains as arbitrary wildcard ACS values.

### 12.5. Proxy Altering Scheme or Host

The browser connects to `https://acme.portal.example.org`; the backend sees `http://app:8080`. If the SP computes `{baseUrl}` from the wrong host, the IdP may issue assertions targeting the internal ACS. For approved tenants, declare **fixed public entity ID/ACS values** or use forwarded headers from a trusted proxy. Never disable `Destination` checks to work around proxy issues; fix ingress, SP metadata, and IdP registration instead.

### 12.6. Migrating Users Between Tenants

A user may move from Acme to Beta through an HR process. Never "migrate" by simply changing a path or email domain. Require approval, a new identity link, revocation of old membership, policy-compliant session invalidation, separated tenant data, and auditing. A fresh SAML login in Beta must not automatically retain access to prior Acme data.

## 13. Threat Model and Negative Test Matrix

| Case | Staging Simulation | Correct Outcome |
| --- | --- | --- |
| Acme happy path | Acme host, Acme path, valid IdP Acme signed Response | Login succeeds with permissions scoped solely to Acme |
| Beta happy path | Beta host, Beta path, valid IdP Beta signed Response | Login succeeds into tenant Beta |
| Host/path mismatch | Acme host, `/t/beta/login` | Deny/404; no Beta AuthnRequest sent |
| Unregistered host | `attacker.portal.example.org/t/acme/login` | Deny |
| Unknown tenant slug | `/t/evil/login` | Deny; no IdP fallback |
| Direct generator call | Acme host, `/saml2/authenticate/beta` | Deny |
| Direct generator query | Acme host, `/saml2/authenticate?registrationId=beta` | Deny in demo |
| Cross-host ACS | POST Beta `SAMLResponse` to Acme host Beta path | Denied by host gate |
| Cross-IdP signature | IdP Beta signs Response sent to Acme ACS | Signature/issuer mismatch; unauthenticated |
| Spoofed Issuer text | Self-signed Response claiming Issuer Acme | Attacker key untrusted |
| Wrong Audience | Signed Acme Assertion with Beta Audience | Denied by OpenSAML validator |
| Wrong Destination | Valid Acme signer yet Destination is Beta ACS | Deny |
| Wrong Recipient | Bearer `SubjectConfirmation` Recipient is Beta ACS | Deny |
| Wrong `InResponseTo` | Response references another browser/tenant's AuthnRequest | Deny |
| Lost AuthnRequest state | Cookie/session omitted on callback | Correlation fails; rejected |
| IdP-initiated when prohibited | Unsolicited `SAMLResponse` | Rejected per policy |
| SAML Response replay | Resubmit an already-used response | Denied per session/replay policy |
| Duplicate account email | IdP A/B share email with distinct identities | No auto-link; no cross-tenant grant |
| Valid registration, locked user | SAML authenticated Acme, internal user disabled | 403 / deny app access |
| Acme registration calls Beta resource | `GET /t/beta/reports` with Acme principal | 403 |
| Forwarded header spoof | Client sends `X-Forwarded-Host: acme.portal.example.org` through untrusted path | Edge strips spoofed header; backend never self-trusts |
| Meta URL attack | `?metadataUrl=http://169.254.169.254/...` | Never fetched; input rejected |
| Open redirect | `?returnUrl=https://attacker.example` | Never redirects outside allowlist |
| Unknown plausible hostname | `acme.portal.example.org.evil.test` | Exact hostname check denies |
| Disabled tenant route | Map/config status `INACTIVE` | Deny |
| Rotated signing cert | IdP signs with un-updated cert | Fails until rotation handled; never disable checks |
| Backend node B lacks session | Callback lands on node B | Shared session/state or safe failure |

**Test signature/Issuer/Audience accurately:** If you edit Audience after the IdP signs, the signature breaks; login failure in that test **does not prove** the Audience validator ran. Have a test IdP sign a valid Assertion **for SP B**, then present it to SP A in staging. Similarly, to test Destination in isolation, have the test IdP issue a valid Response with the wrong destination; never tamper with signed XML and guess the failure cause.

### 13.1. Unit Tests, Integration Tests, and Browser E2E

- **Pure Java unit test:** `TenantRouteDemo` confirms exact matching and unknown denial; does not test network `Host` trust or SAML.
- **Spring MVC test:** mock canonical host, invoke `GET /t/acme/login` and `GET /t/beta/login`, assert 303 and `Location`; assert 404 on mismatch.
- **Spring Security filter test:** directly invoke `/saml2/authenticate/beta` on Acme host, query-only generator, and cross-host ACS. Verify `HostRegistrationGate` executes before SAML filters.
- **IdP integration:** use two sandbox IdPs with distinct metadata and signing certs; test AuthnRequest, `SAMLResponse`, `InResponseTo`, issuer/audience/recipient, and session handling.
- **Browser E2E:** verify TLS/SNI, canonical host, redirects, `SameSite` cookies, proxy forwarded headers, re-login, and multi-tab flows.
- **Multi-instance:** verify distributed request repository/session, metadata caching, node clocks, and consistent key rotation.
- **Authorization/service tests:** an Acme account attempts to read Beta data even with valid SAML Authentication; DB queries must bind tenant server-side.

**Never test by** disabling signature validation or placing production signing private keys in a lab. Never write SAML XML, NameID, session cookies, or private keys into unprotected logs.

## 14. Common Errors and Investigation Guide

| Symptom | Likely Layer | Investigation Steps |
| --- | --- | --- |
| `404 Unapproved tenant route` | Host/path allowlist | Canonical host, `tenantSlug`, active mapping |
| `404` at `/saml2/authenticate/...` | Direct generator guard | Host–registration pair; no query bypass |
| Redirected to wrong IdP | Route mapping or IdP picker | Ensure approved registration only |
| Wrong ACS domain/port | Proxy/public URL or IdP registration | SP metadata, fixed ACS, trusted forwarded headers |
| `Invalid Issuer` | IdP entity ID/trust | Compare Response Issuer with registration's asserting party |
| `Invalid Signature` | Cert mismatch/rotation | IdP public verification cert; never trust self-asserted `KeyInfo` |
| `Invalid Audience` | Wrong SP entity ID | `AudienceRestriction` in Assertion and SP metadata |
| `Invalid Destination` | IdP sent to wrong ACS | Expected ACS, host, scheme, path, binding |
| `Invalid Recipient` | Wrong bearer confirmation | `SubjectConfirmationData` `Recipient` |
| `InResponseTo mismatch` | Request repository/session | Callback cookie, cluster, request ID, and `RelayState` |
| Login succeeds yet 403 on tenant | Correct post-auth denial or missing mapping | Identity link, membership, and route tenant |
| User from IdP A enters tenant B | Missing post-login registration check | Enforce principal registration/tenant policy |
| Two IdPs share Issuer | Ambiguous issuer lookup | Use request state/path and approved registration |
| Error occurs on one server only | Divergent config/session/cache | Compare metadata, keys, NTP, releases |
| Metadata fails to load | Unreachable IdP URI/SSRF policy/cert error | Verify approved source, TLS, egress |
| Post-login redirect hits external URL | Missing allowlist on `returnUrl`/`RelayState` | Redirect policy, saved request, and frontend |
| Tenant alias hits login loop | Cookie scope/canonical host mismatch | Redirect to canonical host before AuthnRequest; inspect session cookie |

**Helpful investigation order:** canonical Host → `pathTenant` → active route → `registrationId` → IdP metadata/trust → AuthnRequest state → signed SAML Response → Issuer/Audience/Destination/Recipient/`InResponseTo` → principal registration → internal identity link → resource authorization. Never fix a downstream error by turning off upstream validation.

## 15. Production Deployment Checklist

- [ ] Ingress accepts only deployed domains with matching TLS/SNI; backend is not directly exposed publicly.
- [ ] Forwarded headers are stripped/rewritten at trusted proxies; app never trusts raw client headers.
- [ ] Domain aliases, tenant slugs, and `registrationId`s are defined in an admin-approved table.
- [ ] All unknown hosts/paths/registrations default to DENY with no fallback IdP.
- [ ] Direct `/saml2/authenticate/{registrationId}` and query forms cannot bypass tenant policy.
- [ ] ACS routes align with the exact registration, SP entity ID, and public URL.
- [ ] IdP entity IDs and verification certs originate from approved metadata, never from `SAMLResponse` or URL parameters.
- [ ] SAML provider retains signature, issuer, audience, destination, recipient, time, subject confirmation, and correlation checks.
- [ ] Session/request repository supports load-balanced callbacks with bounded clock skew.
- [ ] Unknown/multi-issuer edge cases have explicit policies; IdP-initiated SSO disabled unless required.
- [ ] Post-login checks verify trusted registration, `IdentityLink`, tenant membership, user status, authorities, and resource ownership.
- [ ] Never auto-link users by email alone; never treat tenant path as a security principal.
- [ ] SP signing/decryption secrets are readable only by authorized workloads for the right environment/tenant.
- [ ] Domain/tenant onboarding, metadata refresh, and cert rotation have approval, auditing, and rollback.
- [ ] Test negative cross-tenant access, spoofed `Host`, malicious metadata URLs, callback swaps, and open redirects.
- [ ] Logs record only `registrationId`, sanitized `tenantSlug`, error category, and correlation ID; never log raw `SAMLResponse`, `NameID`, or credentials.
- [ ] Tenant aliases, shared-host sessions, SLO, and logout scope are evaluated separately.

## 16. Practical Exercises

**Exercise A – Identify six ID types.** Using Acme's mapping in Section 2, list the host, path tenant, `registrationId`, IdP entity ID, SP entity ID, and ACS. Explain why a metadata URI and an Issuer do not necessarily match.

**Exercise B – Java 17.** Run `TenantRouteDemo.java` and verify the six stdout lines. Add a test for `("beta.portal.example.org","acme")` and verify `DENY`. Add an alias only after a formal route change approval.

**Exercise C – Direct endpoint bypass.** Skip `/t/acme/login` and call `/saml2/authenticate/beta` directly on the Acme hostname. Based on Section 9's filter, explain why 404 is returned. Then explain why, even with the filter running, OpenSAML must still verify the Response.

**Exercise D – Test IdP.** Register two SP/IdP pairs in a sandbox. Perform separate Acme and Beta logins, comparing AuthnRequest Issuer/ACS, Response Issuer, Audience, and resulting `registrationId`. Do not place an IdP private key in the SP.

**Exercise E – Cross-tenant authorization.** Simulate a user logged in via Acme attempting to access a Beta resource. Explain why checking `authenticated()` alone is insufficient; design a service enforcing tenant membership and resource ownership.

**Exercise F – Shared host.** Design `portal.example.org/t/acme/login` and `portal.example.org/t/beta/login`. Identify at least two issues: one browser cookie/session may not represent two tenants concurrently, and ACS must distinguish registrations. Propose a concrete session/URL policy.

**Exercise G – Custom domain.** Acme wants to use `login.acme-company.example`. Diagram domain ownership verification, TLS, canonical-host redirect, mapping approval, and IdP ACS updates. Explain why aliases cannot be added arbitrarily without evaluating cookies/correlation.

**Exercise H – Threat model.** Give three scenarios where SSRF/open redirect can occur when an app accepts `?tenant` or `?metadataUrl`, and explain how an allowlisted repository eliminates those attack paths.

**Exercise I – Shared-issuer IdP.** Two tenants point to the same IdP entity ID. Explain why `Response/Issuer` is not enough to pick a tenant, and describe the role of `registrationId` in AuthnRequest state, Audience, and post-auth membership.

**Passing criteria:** Learners can pinpoint the three boundaries **(host,path) allowlist pre-login → SAML signature/issuer/audience/ACS/correlation validation during login → tenant authorization post-login**, build the two-tenant sample app, and list at least five critical negative tests.

## 17. Official Documentation

- Spring Security 6.5 – SAML 2.0 Login Overview, `RelyingPartyRegistrationRepository`, and URI patterns: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security 6.5 – Authenticating SAML Responses, customizing registration lookup: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
- Spring Security 6.5 – Producing AuthnRequests, request URI, and repository: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html
- Spring Security 6.5 API – `Saml2AuthenticationTokenConverter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html
- Spring Security 6.5 API – `Saml2AuthenticatedPrincipal`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
- Spring Security – SAML2 SP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – SAML Relying Party and OpenSAML dependencies: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core, Issuer, Audience, and SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Metadata, EntityDescriptor/ACS: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
