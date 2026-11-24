# RelyingPartyRegistrationResolver and Per-Request Registration Selection in Spring Security SAML 2.0

> **Topic:** Spring Security – Federation. **Section:** Multiple IdPs and Tenants. This lesson explains how Spring Security determines which **`RelyingPartyRegistration`** to use for an HTTP request in a SAML 2.0 Service Provider application, how to write a **`RelyingPartyRegistrationResolver`** for controlled selection, and how to preserve trust boundaries across outbound AuthnRequest generation, inbound SAMLResponse handling, metadata publishing, and Single Logout.

## 1. Real-World Problem: One Application, Multiple IdPs or Tenants

A Java Spring Security application might serve:

- Tenant **alpha** at `https://alpha.portal.example.org`, linked to IdP alpha.
- Tenant **beta** at `https://beta.portal.example.org`, linked to IdP beta.
- One tenant with **multiple IdP options** (e.g., an employee IdP and a partner IdP).
- Two tenants using **the same IdP product** but with different entityIDs/tenants, signing keys, or policy configurations.
- Multiple logical SP applications running inside one Java service, sharing codebase while having **different Entity IDs, ACS URLs, and signing/decryption credentials**.

When a user hits a hostname, path, or login page, the system needs to know **which SAML configuration to use** to build the AuthnRequest. When the IdP sends a SAMLResponse to the ACS, the system must again pick **the right trust configuration** to verify signature, Issuer, Audience, Recipient, InResponseTo, and attributes.

If the wrong registration is selected:

- The browser may be sent to another tenant's IdP.
- The AuthnRequest may use the wrong SP Entity ID or ACS URL.
- The SAMLResponse fails verification because the trusted IdP certificate does not match.
- More dangerously: an insufficiently constrained custom converter could accept an assertion from **an IdP outside the permitted tenant**, causing account/role mix-ups.

**Core idea:** `RelyingPartyRegistrationResolver` does not mean "let any HTTP request pick any IdP." It is a **context decision point** that must rely on trusted mappings and work together with downstream SAML validators.

## 2. Easily Confused Components and Terms

| Concept | Role | API/Location |
|---|---|---|
| `RelyingPartyRegistration` | An SP ↔ IdP link configuration: SP Entity ID/ACS/credentials and IdP issuer/SSO/verification cert | `org.springframework.security.saml2.provider.service.registration` |
| `registrationId` | Spring's internal lookup key for a registration, e.g., `alpha`, `beta` | `RelyingPartyRegistration.getRegistrationId()` |
| `RelyingPartyRegistrationRepository` | Data store queried by registration ID; may be static or backed by DB/cache | `findByRegistrationId(String)` |
| `IterableRelyingPartyRegistrationRepository` | Allows enumerating registrations to display choices or publish metadata | Spring Security registration repository |
| `RelyingPartyRegistrationResolver` | Resolves the appropriate registration from the HTTP request and optional ID hint | `resolve(HttpServletRequest, String)` |
| `DefaultRelyingPartyRegistrationResolver` | Built-in implementation: extracts ID, queries repository, and resolves placeholders | `org.springframework.security.saml2.provider.service.web` |
| `Saml2AuthenticationTokenConverter` | Converts an ACS request into an AuthenticationManager input token; needs a registration | Takes `RelyingPartyRegistrationResolver` in constructor |
| `Saml2AuthenticationRequestResolver` | Determines/creates **outbound AuthnRequest** from an HTTP request | **Separate** extension point |
| `Saml2MetadataResponseResolver` | Determines which SP metadata is published for a request | **Separate** extension point |
| `Saml2AuthenticationRequestRepository` | Stores issued AuthnRequests to correlate callbacks, usually bound to session | Helps prevent cross-session/tenant mix-ups |

**Specifically:** `registrationId` is not `SP Entity ID`, not `IdP Entity ID`, not a public tenant ID, and not `NameID`. You can name `registrationId=alpha` while the IdP issuer is a completely different URL.

### One Registration Describes Both Sides

~~~text
RelyingPartyRegistration "alpha"
  SP / relying party:
      entityID = https://alpha.portal.example.org/saml/sp
      ACS = https://alpha.portal.example.org/login/saml2/sso/alpha
      signingCredentials / decryptionCredentials = SP keys
  IdP / asserting party:
      entityID = https://login.alpha-idp.example.org/issuer
      SSO = https://login.alpha-idp.example.org/sso
      verificationCredentials = trusted IdP signing cert

RelyingPartyRegistration "beta"
  SP / relying party:
      entityID = https://beta.portal.example.org/saml/sp
      ACS = https://beta.portal.example.org/login/saml2/sso/beta
      signingCredentials / decryptionCredentials = SP keys
  IdP / asserting party:
      entityID = https://login.beta-idp.example.org/issuer
      SSO = https://login.beta-idp.example.org/sso
      verificationCredentials = trusted IdP signing cert
~~~

**Rule:** a login for alpha must use the exact registered SP/IdP pair. An IdP beta certificate is **not automatically accepted** to verify an alpha user, even if the user has the same email.

## 3. Three Distinct "Choose Registration" Moments by Phase

### 3.1. SP-Initiated: Before Sending AuthnRequest

~~~text
User -> GET /private on alpha.portal.example.org
            |
            v
   Login entrypoint / identity picker
            |
            v
   Choose registration "alpha"
            |
            v
 GET /saml2/authenticate/alpha
            |
            v
 Saml2AuthenticationRequestResolver
            |
            v
 AuthnRequest -> IdP alpha
~~~

Here, the system must **choose an IdP/registration to start**. With the default URL `/saml2/authenticate/{registrationId}`, Spring gets enough hint from the path. If the app uses custom domains or URLs without an ID, you can configure `Saml2AuthenticationRequestResolver` or an entrypoint/redirect controller with an explicit mapping; **merely replacing the ACS converter does not automatically alter AuthnRequest generation**.

### 3.2. ACS Callback: After Receiving SAMLResponse

~~~text
IdP alpha -> Browser -> POST /login/saml2/sso/alpha
                        |
                        v
            Saml2WebSsoAuthenticationFilter
                        |
                        v
           Saml2AuthenticationTokenConverter
                        |
                        v
           RelyingPartyRegistrationResolver
                        |
                        v
              Registration alpha
                        |
                        v
          OpenSAML/Spring Security verifies
          issuer, signature, Audience, Recipient,
          Destination, InResponseTo, conditions
                        |
                        v
                    Authentication
~~~

When receiving a Response, the default precedence may check a **saved AuthnRequest**, the ID from the URL, or the **Issuer** from the Response if needed. The Issuer before signature verification is **untrusted data**; it can serve as a **hint to look up a fixed trust set**, but its content is only trusted after the provider verifies it against the signing keys/conditions of the matching registration.

### 3.3. Publishing SP Metadata

~~~text
IdP admin -> GET /saml2/metadata/alpha
                    |
                    v
      Saml2MetadataResponseResolver
                    |
                    v
      SP metadata for registration alpha
      (Entity ID, ACS, public certificates)
~~~

Metadata is a **separate** flow. Customizing the ACS resolver **does not automatically** make `/saml2/metadata` output the right tenant's XML. If a hostname needs a single metadata endpoint or a URL without a `registrationId`, design an appropriate `Saml2MetadataResponseResolver`/repository. Wrong metadata causes the IdP to store the wrong SP Entity ID, ACS, or signing cert.

### Extension-Point Matrix

| Purpose | Notable Input Data | Corresponding Extension Point |
|---|---|---|
| Pick an IdP from login UI | Verified tenant context, allowed IdP list | Login entrypoint/picker; `Saml2AuthenticationRequestResolver` |
| Generate AuthnRequest | Request path/registration hint, SP/IdP configuration | `Saml2AuthenticationRequestResolver` |
| Receive and validate SAMLResponse | Pending request, ACS URL, Response issuer/ID | `Saml2AuthenticationTokenConverter` with `RelyingPartyRegistrationResolver` |
| Publish metadata | Metadata URL, hostname, registration | `Saml2MetadataResponseResolver` |
| Receive SAML LogoutRequest | IdP issuer, current user/registration | Corresponding SLO request validator/resolver |
| LogoutResponse callback | Pending LogoutRequest and issuer | SLO response validation/repository |

**Do not expect one resolver to automatically "handle" all flows.** A multi-tenant deployment must explicitly verify every endpoint has consistent mappings.

## 4. Exact RelyingPartyRegistrationResolver API

Per Spring Security 6.5/7.1 JavaDoc, the interface is:

~~~java
package org.springframework.security.saml2.provider.service.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;

public interface RelyingPartyRegistrationResolver {
    RelyingPartyRegistration resolve(
            HttpServletRequest request,
            String relyingPartyRegistrationId);
}
~~~

This is a **core-signature illustration**; the actual JavaDoc includes nullability annotations depending on version—do not copy the interface into your project since Spring already provides it.

- `request`: the current HTTP request (e.g., host, path, server context, gateway-normalized headers).
- `relyingPartyRegistrationId`: a **hint** if another component already knows the ID; may be `null`.
- Return: the matching registration object; implementations may return `null` if unresolvable or disallowed.
- There is **no** `resolve(request)` method on this interface. The single-argument `convert(request)` method belongs to `DefaultRelyingPartyRegistrationResolver` when used as a `Converter`.

### 4.1. Built-In Implementation

~~~java
RelyingPartyRegistrationResolver resolver =
        new DefaultRelyingPartyRegistrationResolver(registrations);

RelyingPartyRegistration selected =
        resolver.resolve(request, "alpha");
~~~

This is a **fragment** requiring `registrations` and `request` from the application. `DefaultRelyingPartyRegistrationResolver` queries `RelyingPartyRegistrationRepository` and resolves URI template placeholders such as `{baseUrl}` and `{registrationId}` from the request context.

**Do not confuse:** This resolver **does not verify XML Signatures**, does not check Issuer/Audience, and does not grant an `Authentication`. Those responsibilities belong to the Spring Security/OpenSAML provider after registration selection.

### 4.2. Difference Between Repository and Resolver

| Repository | Resolver |
|---|---|
| Takes a **registration ID** and returns a record | Takes **`HttpServletRequest` + optional registration ID** |
| Stores IdP/SP/credentials configuration | Applies selection rules for a specific request |
| Can load from config, DB, cache, metadata | Can decide based on host/path/tenant context |
| Returns not-found if ID is missing | Can reject incompatible host/ID combinations |
| Knows no HTTP context when looking up solely by ID | Sees HTTP context, yet **must not trust arbitrary headers** |
| E.g., `findByRegistrationId("alpha")` | E.g., `resolve(request, "alpha")` |

If tenant selection simply comes from `registrationId` in the path and each ID has a fixed registration, **you do not need a custom resolver**. Using the default reduces security-critical code to maintain.

## 5. Where Is It Safe to Derive a Registration?

A multi-tenant app may see many signals: hostname, path prefix, query parameter, session tenant, login invitation, or Response issuer. **Not all signals carry the same level of trust.**

| Signal | Example | What Can It Be Used For? | Risk |
|---|---|---|---|
| Explicit URL path ID | `/saml2/authenticate/alpha` | Select registration when starting login | User can supply another ID; requires tenant allowlist |
| Gateway-managed public hostname | `alpha.portal.example.org` | Map to tenant alpha | Host header spoofing without trusted routing |
| Application path prefix | `/t/alpha/login` | Map tenant inside internal routes | Must verify tenant exists and access rights |
| Query parameter | `?tenant=alpha` | Allowlisted UI/entrypoint hint | **Not** proof of authorization or trust |
| Arbitrary HTTP header | `X-Tenant: alpha` | Only when inserted by a **trusted proxy** after stripping inbound | Attacker sets header if proxy fails to sanitize |
| Email domain | `user@alpha.example.org` | May assist initial discovery | Does not prove IdP/tenant; easy domain confusion |
| Authenticated session cookie | Registration/tenant in server session | Correlate post-login context | Must defend against session fixation/tampering |
| Saved AuthnRequest state | Original request ID/registration | **Strong basis for SP-initiated callback** | Lost cookie/session, repository mismatch |
| `SAMLResponse.Issuer` | IdP URL from XML | Hint to pick a **trusted registration candidate** | Unverified payload; multiple tenants may share an issuer |
| `Assertion.Audience` | SP Entity ID | Check assertion targets the right SP | Never select trust solely from an unsigned assertion |

**Decision rule:** Use a **server-controlled and allowlisted** mapping to pick a registration candidate, then let the SAML provider **verify** that candidate against issuer/keys/audience/recipient/request state. Never grant roles based solely on a browser-supplied ID/hint.

### 5.1. When Is the Host Header Trustworthy?

`request.getServerName()` can read the host from the HTTP request/`Host` header or processed forwarded headers. If the app lets clients connect directly and send arbitrary `Host` headers, host-based mapping cannot guarantee tenant isolation.

To stay safe:

1. Expose tenant hostnames only through a **gateway/ingress that validates TLS/SNI and virtual hosts**.
2. Block direct backend access that bypasses the trusted proxy.
3. Have the proxy strip client-sent `Forwarded`, `X-Forwarded-Host`, and `X-Tenant` headers before injecting canonical internal values.
4. Configure Spring Boot forwarded-header handling to match your infrastructure.
5. Allowlist exact hostnames and normalize case per DNS semantics; avoid sloppy substring or suffix checks.
6. If `Host` and `registrationId` disagree, **reject**; never fall back to a default tenant.
7. Never build Metadata/ACS URLs from an unvalidated `Host` header due to host header injection risk.

### 5.2. When Is a Path-Based Registration ID Better?

Use explicit URLs such as:

~~~text
GET  /saml2/authenticate/alpha
POST /login/saml2/sso/alpha
GET  /saml2/metadata/alpha
~~~

Pros: simple, easy to audit, supported out of the box by Spring Security, and clear in logs. Cons: when one SP hosts multiple tenants on one hostname, a user can manually change `alpha` to `beta`. This is **only acceptable** if the user/tenant context is permitted to use IdP beta and post-login authorization isolates tenants.

If each hostname is strictly bound to one tenant, enforce the **host-to-registration** rule across entrypoint, response handling, and metadata—not just the path entered by the user.

## 6. Example Configuration of Two Registrations with Spring Boot YAML

Illustrative configuration for a Spring Security Servlet SP following Spring Boot 3.x/matching structure; IdP URLs are **example values**, not real metadata:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          alpha:
            entity-id: "https://alpha.portal.example.org/saml/sp"
            acs:
              location: "https://alpha.portal.example.org/login/saml2/sso/alpha"
            assertingparty:
              metadata-uri: "https://login.alpha-idp.example.org/metadata"
          beta:
            entity-id: "https://beta.portal.example.org/saml/sp"
            acs:
              location: "https://beta.portal.example.org/login/saml2/sso/beta"
            assertingparty:
              metadata-uri: "https://login.beta-idp.example.org/metadata"
~~~

Spring Boot constructs a `RelyingPartyRegistrationRepository` from the matching config, with `alpha`/`beta` as each `registrationId`.

**In real deployments:**
- IdP alpha must register the exact alpha SP Entity ID and ACS; likewise for beta.
- `metadata-uri` must be a trusted metadata source with the right tenant issuer and signing cert.
- The application must not blindly trust metadata just because HTTPS succeeds; verify trust/source and key rollover.
- If the IdP requires signed AuthnRequests, add an SP signing credential and configure the IdP to trust the public cert.
- If Assertions are encrypted, add the corresponding SP decryption credential.
- For Spring Boot 4/Spring Security 7, verify exact property names for your running version.

### 6.1. Do Not Blindly Copy Shared Entity ID and ACS Across All Tenants

There are cases where one SP shares an SP Entity ID/ACS across multiple IdPs. SAML profiles do not forbid all such variants, yet when IdP issuers overlap or differ across tenants and signatures/credentials vary, lookup grows ambiguous. Separating SP Entity ID and ACS per tenant is usually simpler operationally and for trust, **though not always mandatory**.

Maintain a contract table:

| Tenant | `registrationId` | SP Entity ID | ACS URL | IdP Issuer | IdP Signing Fingerprint |
|---|---|---|---|---|---|
| Alpha | `alpha` | `https://alpha.portal.example.org/saml/sp` | `https://alpha.portal.example.org/login/saml2/sso/alpha` | Verified alpha issuer | Alpha cert fingerprint |
| Beta | `beta` | `https://beta.portal.example.org/saml/sp` | `https://beta.portal.example.org/login/saml2/sso/beta` | Verified beta issuer | Beta cert fingerprint |

Never distribute private keys in spreadsheets, public metadata, or logs. Fingerprints can be shared, yet only establish trust once the source is verified.

## 7. Java 17+ Custom Resolver Bound to Hostname and Rejecting Conflicting Hints

This is the centerpiece example of the lesson. It **enforces** the registration derived from a gateway-verified hostname and checks `relyingPartyRegistrationId` if an upstream component supplies one. When the host is not allowlisted or the ID mismatches, it returns `null` so authentication fails. It **never** falls back to the first tenant.

File `src/main/java/com/example/saml/HostBoundRegistrationResolver.java`:

~~~java
package com.example.saml;

import java.util.Locale;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;

public final class HostBoundRegistrationResolver
        implements RelyingPartyRegistrationResolver {

    private final RelyingPartyRegistrationResolver delegate;

    private final Map<String, String> allowedHosts = Map.of(
            "alpha.portal.example.org", "alpha",
            "beta.portal.example.org", "beta");

    public HostBoundRegistrationResolver(
            RelyingPartyRegistrationRepository repository) {
        this.delegate = new DefaultRelyingPartyRegistrationResolver(repository);
    }

    @Override
    public RelyingPartyRegistration resolve(
            HttpServletRequest request, String relyingPartyRegistrationId) {
        String host = request.getServerName();
        if (host == null) {
            return null;
        }

        String expectedId = allowedHosts.get(host.toLowerCase(Locale.ROOT));
        if (expectedId == null) {
            return null;
        }

        if (relyingPartyRegistrationId != null
                && !expectedId.equals(relyingPartyRegistrationId)) {
            return null;
        }

        return this.delegate.resolve(request, expectedId);
    }
}
~~~

**Step-by-step explanation:**

1. `allowedHosts` is a **server-configured allowlist**, never taken from a JSON body or query parameter.
2. `getServerName()` is treated as a source **controlled by a trusted ingress**; without ingress protection, it is **not safe enough**.
3. `toLowerCase(Locale.ROOT)` handles simple DNS hostnames; in production, handle IDNA/Punycode, ports, trailing dots, and canonical host rules per your gateway.
4. Host not in allowlist → `null`; never defaults to alpha.
5. If path/callback carries hint `beta` while the request hits host `alpha` → `null`; never picks one side arbitrarily.
6. The delegate is `DefaultRelyingPartyRegistrationResolver`, which queries the repository and resolves URI templates.
7. The resolver **only selects a candidate** and does not verify SAML signatures itself; the provider must still check issuer, signing key, audience, recipient, and conditions.

**Important limitation:** This snippet **does not block outbound AuthnRequest generation via the default resolver** if the app still allows `GET /saml2/authenticate/beta` on host alpha; protect outgoing initiation separately (Section 9). Nor does it replace the metadata resolver. This highlights the distinction between "resolving a registration on Response receipt" and "selecting an IdP when starting the flow."

### 7.1. Integrating the Resolver with the SAML Response AuthenticationConverter

File `src/main/java/com/example/saml/SamlSecurityConfiguration.java`, Java 17+ in a Spring Boot Servlet project with `spring-security-saml2-service-provider`:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationTokenConverter;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    RelyingPartyRegistrationResolver relyingPartyRegistrationResolver(
            RelyingPartyRegistrationRepository repository) {
        return new HostBoundRegistrationResolver(repository);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationResolver registrationResolver)
            throws Exception {

        Saml2AuthenticationTokenConverter converter =
                new Saml2AuthenticationTokenConverter(registrationResolver);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml2 -> saml2
                .authenticationConverter(converter))
            .build();
    }
}
~~~

**Mechanism:** `Saml2AuthenticationTokenConverter` accepts `RelyingPartyRegistrationResolver` in its constructor; `saml2Login(saml2 -> saml2.authenticationConverter(converter))` wires the converter into the **ACS authentication request step**. Spring Security/OpenSAML continues verifying signatures and conditions.

**Do not equate:** This config does not automatically block `GET /saml2/authenticate/{registrationId}` on the wrong hostname. Route users through an allowlisted custom entrypoint/selector and block mismatched direct outgoing URIs, or configure an appropriate `Saml2AuthenticationRequestResolver`. This Spring code requires dependencies/classpath and real IdPs; **it is not a standalone `javac` program**.

### 7.2. If You Want to Change the Response Callback URL

For example, choosing a fixed callback URL `/saml/acs` across multiple hosts:

~~~java
http.saml2Login(saml2 -> saml2
    .loginProcessingUrl("/saml/acs")
    .authenticationConverter(converter));
~~~

This is a **fragment inside `SecurityFilterChain`**. For callbacks without `registrationId` in the path, the converter must resolve from trusted host and/or request state; `HostBoundRegistrationResolver` above can return the registration by host, while still verifying issuer/signature/Audience/Recipient.

You must update **the ACS in every `RelyingPartyRegistration`**, published SP metadata, and the IdP's stored Reply URL. Changing `loginProcessingUrl` alone without updating ACS/location causes the IdP to POST to the wrong endpoint or Spring to reject Recipient/Destination.

## 8. Standalone Java 17: Testing the "Hint Must Match Tenant" Principle

This program is **standalone**, requires no Spring, and illustrates the host→registration policy that rejects conflicting path hints. It does not parse SAML XML, verify signatures, or decide user permissions; its output is strictly **selection policy before the SAML provider**.

File `TenantSelectionDemo.java`:

~~~java
import java.util.Locale;
import java.util.Map;

public class TenantSelectionDemo {

    static final Map<String, String> HOST_TO_REGISTRATION = Map.of(
            "alpha.portal.example.org", "alpha",
            "beta.portal.example.org", "beta");

    static String select(String hostname, String hintedId) {
        if (hostname == null) {
            return "REJECT";
        }

        String expected = HOST_TO_REGISTRATION.get(
                hostname.toLowerCase(Locale.ROOT));

        if (expected == null) {
            return "REJECT";
        }

        if (hintedId != null && !expected.equals(hintedId)) {
            return "REJECT";
        }

        return expected;
    }

    public static void main(String[] args) {
        System.out.println(select("alpha.portal.example.org", "alpha"));
        System.out.println(select("beta.portal.example.org", null));
        System.out.println(select("alpha.portal.example.org", "beta"));
        System.out.println(select("unknown.example.org", "alpha"));
        System.out.println(select(null, "alpha"));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac TenantSelectionDemo.java
java TenantSelectionDemo
~~~

**Exact stdout:**

~~~text
alpha
beta
REJECT
REJECT
REJECT
~~~

**Meaning of each case:**

1. Host alpha with hint alpha → selects alpha.
2. Host beta with no hint → selects beta via allowlist.
3. Host alpha with hint beta → rejects rather than silently preferring the hint or the host.
4. Unregistered host → rejects.
5. Null host → rejects.

**Limitation:** If an attacker can spoof `Host`, the function will still return `alpha` based on the attacker's string. Production therefore needs **trusted edge routing** and full SAML signature/issuer/audience validation. The demo only shows deterministic decision logic, not trust in the host or payload.

## 9. Outbound AuthnRequest Generation Must Also Be Protected

A common mistake is thinking: "I wrote a custom `RelyingPartyRegistrationResolver` for SAMLResponse, so every login now routes to the right tenant." That is **incorrect**.

### 9.1. Default Outgoing Route

Spring Security generates AuthnRequests at:

~~~text
GET /saml2/authenticate/{registrationId}
~~~

When a user visits `/saml2/authenticate/beta` on host alpha, the request filter may pick **beta** if it relies solely on the path. Even if the later callback is rejected by `HostBoundRegistrationResolver`, the user was already redirected to IdP beta, causing a broken UX or unwanted context/redirect exposure.

**Solutions by priority:**

1. If using a single hostname where users may pick an IdP, render a **picker** listing only registrations permitted for the tenant, then redirect to `/saml2/authenticate/{id}`.
2. If each hostname mandates a single IdP, expose an entrypoint/endpoint on that host allowing only the mapped ID and **block mismatched outgoing URLs**.
3. When custom query/URI formatting is needed, use `Saml2AuthenticationRequestResolver` or `saml2Login.authenticationRequestUriQuery(...)` per your API version.
4. If customizing the request repository, ensure the AuthnRequest is saved with the registration/tenant and correlation state bound to the right browser.
5. If the app has multiple entrypoints, inspect every alias/path capable of initiating AuthnRequest, not just buttons on the login page.

### 9.2. Key API Differences to Remember

| API | Method / Usage Point | Result |
|---|---|---|
| `RelyingPartyRegistrationResolver` | `resolve(HttpServletRequest, String)` | `RelyingPartyRegistration` |
| `Saml2AuthenticationRequestResolver` | `resolve(HttpServletRequest)` | An `AbstractSaml2AuthenticationRequest` (Redirect/Post request per provider) |
| `Saml2LoginConfigurer.authenticationRequestResolver(...)` | Attaches strategy to build AuthnRequest | Handles outgoing login requests |
| `Saml2LoginConfigurer.authenticationConverter(...)` | Attaches converter to read SAMLResponse | Handles incoming ACS Responses |
| `Saml2LoginConfigurer.loginProcessingUrl(...)` | Changes callback URL | Must update metadata/ACS at the same time |
| `Saml2MetadataConfigurer.metadataResponseResolver(...)` | Attaches metadata strategy | Handles metadata GET requests |

**Spring Security 7.x:** JavaDoc provides `authenticationRequestUriQuery(...)` and marks `authenticationRequestUri(...)` as deprecated. Do not carry API names from the legacy Spring SAML Extension into modern SAML2 Service Provider applications.

### 9.3. Example Dedicated Routing Entrypoint Without Replacing the Default Resolver

A controller supporting a domain-based entrypoint can resolve the ID from a trusted host and redirect:

~~~java
@GetMapping("/start-sso")
String startSso(HttpServletRequest request) {
    String host = request.getServerName();
    if ("alpha.portal.example.org".equalsIgnoreCase(host)) {
        return "redirect:/saml2/authenticate/alpha";
    }
    if ("beta.portal.example.org".equalsIgnoreCase(host)) {
        return "redirect:/saml2/authenticate/beta";
    }
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST, "Unknown tenant host");
}
~~~

This is a **method fragment** inside a Spring MVC controller with appropriate imports. Routing UI buttons through `/start-sso` does not guarantee that direct `GET /saml2/authenticate/other` is blocked. If cross-host initiation must be disallowed, enforce protection on the actual AuthnRequest route in a security filter/router or custom resolver, and write regression tests for direct access.

**UX note:** An app with multiple IdPs for the same tenant cannot always force a single ID by hostname. In that case, the host identifies the tenant while the user chooses an ID from the **tenant's IdP allowlist**. Mapping from a user's email domain is suitable only as an **initial hint**, never as proof of permissions or issuer.

## 10. Receiving SAMLResponse: Request State, URL, and Issuer

Per the Spring Security SAML2 Login Overview and Authenticating Responses documentation, the default converter can determine the registration from:
- An issued and stored matching AuthnRequest.
- The registration ID in the callback URL.
- When those hints are absent, the IdP Issuer parsed from the Response.

**Trust levels must be distinguished:**

### 10.1. Matching AuthnRequest Present (SP-Initiated)

~~~text
Browser for tenant alpha
  -> SP issues AuthnRequest ID=_req123 using registration alpha
  -> stores ID + registration alpha + browser session context
  -> IdP alpha returns SAMLResponse InResponseTo=_req123
  -> Spring looks up pending request
  -> selects registration alpha
  -> verifies issuer/signing cert/audience/recipient/time
  -> creates Authentication for the right tenant
~~~

This is the preferred flow because it has **request correlation** with the browser session. If the pending request is lost due to `SameSite` cookies, clustered session storage, or proxies, **never silently fall back to IdP-initiated** to skip `InResponseTo` validation.

### 10.2. No AuthnRequest (IdP-Initiated)

In IdP-initiated login, the IdP sends an unsolicited Response without `InResponseTo`. An app with two IdPs/tenants must identify the right registration via ACS URL/host and registered issuer. If the **Issuer is identical** across multiple tenant registrations and no distinguishing state exists, selection becomes ambiguous.

**Solution:** Use explicit dedicated ACS/host/paths, require a known `registrationId` with allowlisted host/issuer matching, or **reject unsolicited SSO** per security policy. Never brute-force every IdP's trusted certificates and accept whichever verifies if the outcome could skew tenant/authorization boundaries.

### 10.3. Why Issuer Is a Hint, Not Trust

Response XML can claim anything:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_response_01"
    Version="2.0"
    Destination="https://alpha.portal.example.org/login/saml2/sso/alpha">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    https://login.alpha-idp.example.org/issuer
  </saml:Issuer>
  <!-- Signature and Assertion omitted -->
</samlp:Response>
~~~

The snippet above is **not a valid Response**; it merely illustrates one field. An attacker can put any Issuer in an unsigned payload. You may parse Issuer as a **lookup hint** into an allowlisted repository, but accept it only after the SAML provider uses the **matching IdP verification credential** to verify the XML Signature and semantic conditions. Using Issuer as a lookup key is different from trusting Issuer as proof of the IdP.

### 10.4. Mandatory Checks After Resolver Returns Registration

| Check | Goal |
|---|---|
| Response/Assertion signature | Signature valid under the public key of the **IdP in the chosen registration** |
| Response/Assertion Issuer | Matches configured IdP entityID |
| Assertion `AudienceRestriction` | Contains SP Entity ID of the **chosen registration** |
| Response `Destination` | Matches the ACS URL the browser posted to |
| SubjectConfirmation `Recipient` | Matches the expected ACS |
| `InResponseTo` | If SP-initiated, matches pending AuthnRequest of the browser/session |
| Time conditions | `NotBefore`/`NotOnOrAfter` valid, bounded clock skew |
| Replay | Assertion/Response ID cannot be reused against profile rules |
| NameID mapping | Combines issuer/tenant/subject; never links accounts by email alone |
| `GrantedAuthority` | Maps groups/roles per tenant and IdP trust policy |

**Crucial:** The resolver returning `alpha` **does not mean** an alpha user has been authenticated. Only complete provider/correlation/authorization checks establish a valid session and permissions.

## 11. Multiple IdPs for a Single Tenant

"Multi-IdP" and "multi-tenant" are not identical.

- **One tenant, multiple IdPs:** A corporate tenant lets employees use IdP A and partners use IdP B. One local account may link multiple identities per policy.
- **Multiple tenants, one IdP per tenant:** Alpha and Beta isolate data and roles. SAML selection must enforce tenant isolation.
- **Multiple tenants sharing one IdP:** May share an IdP signing key/issuer while differing in SP Entity ID/ACS/attributes. Tenant scope must remain explicit.
- **One IdP with multiple tenants/realms:** Differs in issuer, endpoints, certificates, or metadata; cannot rely solely on the IdP product name.

### 11.1. What Should the Picker Do?

An IdP picker page should:

1. Determine tenant context through trusted routing.
2. List **only IdPs/registrations permitted by that tenant**.
3. Use stable, opaque, allowlisted `registrationId` values.
4. Route to the AuthnRequest endpoint of the selected registration.
5. Never place roles/admin flags in query parameters or hidden fields.
6. After callback, verify the registration against the original tenant context and SAML validation.
7. Define policy when a user attempts to switch IdPs or log in to another tenant in the same browser.

**Do not** extract a domain from a typed email and automatically trust that IdP; email is browser-supplied data. It can assist discovery/UX, but full authentication must still run.

### 11.2. Separating Tenant from Application Authorization

Even when a user is valid at IdP beta, the application must never open alpha data just because the user holds `ROLE_USER`. Authorization requires explicit tenant scope: resource tenant ID, authenticated issuer/subject, and allowed roles. For role mapping, prefer an approved `(issuer, group-id)` pair rather than flat group names that collide across IdPs.

## 12. Publishing Metadata Consistently with the Resolver

When an IdP administrator asks "Where is alpha's SP metadata?", the answer can be:

~~~text
GET https://alpha.portal.example.org/saml2/metadata/alpha

EntityID: https://alpha.portal.example.org/saml/sp
ACS:      https://alpha.portal.example.org/login/saml2/sso/alpha
Certs:    SP public signing/encryption certs per policy
~~~

**Never fetch** beta's metadata on alpha's hostname and import it into IdP alpha. Because Spring's metadata API can return multiple `EntityDescriptor`s when the repository is `Iterable`, make sure IdP admins use the registration-specific metadata endpoint or a custom metadata response resolver.

### 12.1. Metadata Has Its Own Resolver

Example DSL enabling metadata publishing:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

This is a fragment inside `SecurityFilterChain`. In modern Spring Security, endpoints typically include `/saml2/metadata` and `/saml2/metadata/{registrationId}`.

To customize metadata lookup from hostname/path, use `Saml2MetadataResponseResolver` wired via `saml2Metadata(saml2 -> saml2.metadataResponseResolver(...))`. Do not confuse it with `RelyingPartyRegistrationResolver` on `Saml2AuthenticationTokenConverter`.

**Warning:** Public metadata URL, SP Entity ID, ACS in metadata, and IdP configuration must align per tenant. Behind a reverse proxy, `{baseUrl}` may emit wrong HTTP localhost URLs if forwarded headers are untrusted or misconfigured. Fix routing/explicit URLs rather than disabling `Destination`/`Recipient` validation.

## 13. Dynamic Selection from a Database

A SaaS application may add new tenants/IdPs without restarting servers. In that case, `RelyingPartyRegistrationRepository` can:

- Load a registration from the DB by `registrationId` (including tenant ownership and status).
- Load/parse admin-approved IdP metadata.
- Cache registrations by a stable key with appropriate TTL/metadata lifecycle.
- Support overlapping old/new signing certificates during key rotation.
- Deactivate configurations when a tenant is disabled or an IdP integration is revoked.

The resolver must **still** map requests to an **approved ID**, never letting a request supply an arbitrary metadata URL to trust any IdP's cert. If DB-backed tenant configs hold signing credentials, private keys must live in a secret manager/HSM, never plaintext in application metadata tables.

### 13.1. Minimal Conceptual DB Schema

| Field | Meaning | Principle |
|---|---|---|
| `registration_id` | Stable/unique config key | Do not arbitrarily reuse IDs across different tenants/issuers |
| `tenant_id` | Owner of the registration | Only this tenant may use it |
| `public_host` | Allowlisted host | Apply trusted gateway mapping |
| `sp_entity_id` | SP logical identity | Matches IdP-stored Audience/Identifier |
| `acs_url` | Public SAML callback URL | Matches IdP Reply URL |
| `idp_entity_id` | Trusted issuer | Matches IdP metadata issuer |
| `idp_metadata_uri` | Verified metadata source | Never accepted directly from end users |
| `signing_cert_fingerprint` | IdP signing material version | Tracks rotation and auditing |
| `enabled` | Whether login is allowed | Disabled → resolver/repository fail closed |
| `config_version` | Revision for cache invalidation | All nodes pick up updates atomically |

This table is a **data contract**, not a schema change requirement for this task. When verifying SAML, use a consistent configuration snapshot from AuthnRequest through Response, especially during certificate rotation.

### 13.2. Caching and Metadata Refresh

Spring Security provides `CachingRelyingPartyRegistrationRepository` and refresh-capable metadata repository approaches. With runtime-mutable configs:

1. Pin trust anchors and approved metadata sources.
2. Never let attackers supply metadata URLs for the server to fetch arbitrarily (SSRF).
3. Enforce clear TTL/cache invalidation on certificate changes or tenant disablement.
4. Ensure all nodes hold compatible trusted credentials during a rotation window.
5. Never delete the old public signing key while valid in-flight Responses remain; retire only after the overlap window.
6. When a registration/cert is missing or metadata fetch fails, fail closed and alert operations; never fall back to another tenant.
7. Maintain an audit trail of who changed IdP metadata, issuer, ACS, or signing keys.

**Distinction:** A dynamic repository changes the **set of registrations**. A resolver changes the **selection rule** from a request. You need both if new tenants are onboarded dynamically and URLs do not contain the ID.

## 14. Do Not Trust HTTP Headers and Prevent Tenant Mix-Ups

### 14.1. An Anti-Pattern

~~~java
// UNSAFE: X-Tenant can be sent by the client.
String registrationId = request.getHeader("X-Tenant");
return repository.findByRegistrationId(registrationId);
~~~

If the backend accepts this header directly, a user in alpha can set `X-Tenant: beta` and trick the app into picking beta's IdP/trust config. Even if SAML validation still blocks some cases, **do not create a selection vulnerability** that risks misbinding authorities or data across tenants.

**Better:** Ingress determines tenant from hostname/routing/server config, strips inbound `X-Tenant` before adding internal headers, blocks direct backend access, and the Spring resolver uses a host→registration allowlist while verifying any request ID hint.

### 14.2. Another Anti-Pattern

~~~java
// UNSAFE: user can pick IdP metadata from a URL.
String metadataUrl = request.getParameter("metadataUrl");
// Do not use metadataUrl to dynamically fetch a new IdP and trust its signing cert.
~~~

This introduces **SSRF, trust substitution, and tenant confusion**. Metadata must only come from admin-approved configuration sources with HTTPS and/or appropriate metadata-signature verification and explicit trust.

### 14.3. Do Not Brute-Force Every Key of Every IdP

Some custom code tries:
- Parse the Response.
- Try verifying the signature with every certificate of every registered IdP.
- Whichever key verifies, treat the user as belonging to that tenant.

This bypasses **request/tenant context** and causes account mix-ups when IdPs issue multiple accounts/group claims. **Correct:** candidate registrations must be constrained by trusted route or pending request, then verify that IdP's signer along with Audience/Recipient/Issuer. If multiple valid registrations cannot be disambiguated, **reject** instead of picking the first match in array order.

### 14.4. Tenant Context Must Flow into Authorization

After login, store server-side identity bindings such as:
- application tenant ID;
- chosen `registrationId` and trusted IdP issuer;
- NameID/subject ID with appropriate format/qualifiers;
- mapped authorities per the tenant's allowlist.

Never merge local users across two IdPs using email alone. Never let a post-login request-path tenant ID override the authenticated principal's tenant without an authorization check.

## 15. Testing the Resolver and Full SSO Flow

### 15.1. Resolver Unit Tests

For `HostBoundRegistrationResolver`:

| Request | Hint ID | Expected |
|---|---|---|
| Host alpha | `alpha` | Returns alpha registration |
| Host beta | `beta` | Returns beta registration |
| Host alpha | `null` | Returns alpha |
| Host beta | `null` | Returns beta |
| Host alpha | `beta` | **`null`/reject** |
| Host beta | `alpha` | **`null`/reject** |
| Host unknown | `alpha` | **`null`/reject** |
| Host null/empty | `alpha` | **`null`/reject** |
| Direct backend host spoof | `alpha` | Blocked at edge; resolver alone does not prove safety |
| ID missing in repo | `alpha` | Fail closed / no registration |

You can unit-test the Spring implementation using `MockHttpServletRequest` from `spring-test` with a test `InMemoryRelyingPartyRegistrationRepository` holding fake-but-structurally-valid registrations. **No fake SAMLResponse is needed** for host→ID mapping tests, but separate protocol-level integration tests are mandatory.

### 15.2. SP-Initiated Integration Tests

1. User visits alpha hostname and receives alpha login/picker/IdP.
2. `AuthnRequest.Issuer` equals SP alpha Entity ID.
3. Destination SSO URL belongs to IdP alpha, not beta.
4. ACS URL in the request and IdP registration is the public alpha URL.
5. Pending request saves registration alpha and binds to the browser session.
6. IdP alpha returns a Response with `InResponseTo` pointing to the exact AuthnRequest.
7. Spring converter selects alpha; OpenSAML verifies IdP alpha signing key, issuer, Audience, Recipient, and time.
8. Principal/roles match alpha tenant with zero beta data.
9. Requests on the beta host behave symmetrically.
10. Direct `GET` to beta's initiation URI on the alpha host is blocked by policy.

### 15.3. ACS / IdP-Initiated Integration Tests

| Case | Expected |
|---|---|
| IdP alpha Response to ACS alpha, valid signature | Accepted after validation and tenant policy checks |
| IdP beta Response to ACS alpha | **Rejected** even though beta is another registered IdP |
| Response with wrong Audience yet valid signature | **Rejected** |
| Response with wrong Recipient/Destination | **Rejected** |
| Response signed by untrusted key | **Rejected** |
| Response with `InResponseTo` not matching browser/session | **Rejected**; no unsolicited fallback |
| IdP-initiated without pending request | Allowed only if policy permits unsolicited SSO and routing is unambiguous |
| Two tenants sharing the same IdP issuer without trusted distinguishing context | **Reject ambiguity** |
| Expired assertion or future `NotBefore` | **Rejected** |
| Replayed Assertion/Response ID | **Rejected** per profile |
| Shared role/group name across tenants | Mapped strictly per tenant/issuer allowlist |
| Beta metadata requested via alpha host when policy forbids | Never leaks wrong config; route metadata per policy |
| Session cookie lost across cross-site POST | Fails correlation properly; fix `SameSite`/store, never drop validation |

### 15.4. Multi-Node Environment Tests

- AuthnRequest created on node A, callback lands on node B.
- Session repository or custom `Saml2AuthenticationRequestRepository` preserves state.
- Certificate rotation is synchronized across nodes.
- Disabled tenant configuration applies consistently.
- Request state from one browser is never reused for another browser.
- Reverse proxy sanitizes forwarded headers; hostname mapping cannot be overwritten by users.
- Public metadata on all nodes exposes the same Entity ID/ACS/trust configuration version.

**Note:** Testing solely with `SecurityMockMvcRequestPostProcessors.user(...)` or synthetic `Authentication` objects does not exercise SAML Signature/Audience/Recipient checks. Use a real test IdP or validly signed SAML fixtures alongside deliberate negative messages.

## 16. Layered Troubleshooting

| Symptom | Possible Cause | Diagnostic Step |
|---|---|---|
| "No relying party registration found" | Missing ID, host not allowlisted, repository not loaded | Log canonical host, ID hint, repository version; never log raw SAML |
| Browser redirected to wrong IdP | Outgoing AuthnRequest selection not tenant-bound | Check picker, `/saml2/authenticate/{id}`, outgoing resolver |
| ACS reports invalid signature | Selected registration differs from signing IdP or cert rotated | Check issuer, chosen registration, trusted signing keys |
| ACS reports invalid Audience | SP Entity ID differs from IdP's expected Audience | Compare SP metadata and IdP config for that tenant |
| ACS reports invalid Recipient | ACS path/hostname differs from public Reply URL | Compare proxy, IdP stored ACS, and request URL |
| SSO works on localhost but fails behind ingress | `{baseUrl}` computed from internal HTTP host | Configure trusted Forwarded headers or explicit public URLs |
| Multi-tenant login intermittently fails under load balancing | Nodes hold stale config/cache or request repo loses state | Synchronize cache/keys and Spring Session |
| Shared IdP issuer across tenants causes converter mismatch | Lookup by Issuer alone is ambiguous | Use request state, dedicated ACS/host, or reject unsolicited |
| SAMLResponse without `InResponseTo` accepted unexpectedly | Overly permissive IdP-initiated policy | Deny unsolicited or add explicit policy; test login CSRF |
| Metadata returns all registrations | `Iterable` repository at shared endpoint | Use per-registration metadata or custom response resolver |
| Newly disabled tenant can still log in | Stale cache or repository ignores `enabled` flag | Invalidate cache/refresh and fail closed |
| IdP cert changed while TLS works fine | SAML signing key rotation is separate from TLS | Update trusted IdP verification credentials |
| Alpha user accesses beta data | Authorization missing tenant scope | Fix resource-level tenant checks and issuer+subject mapping |
| ACS 404 after customizing path | `loginProcessingUrl` changed without updating metadata/IdP | Align Spring filter, ACS metadata, and IdP Reply URL |
| Custom `AuthenticationConverter` skips signature checks | Provider/manager wired incorrectly | Keep default OpenSAML validation and test negative signatures |
| Host spoofing selects another registration | Backend trusts untrusted `Host`/`Forwarded` headers | Block direct backend access, sanitize proxy headers, allowlist |

**Debugging order:** tenant routing → host/path ID hint → repository/registration → AuthnRequest state → issuer/certificate/Audience/ACS → authentication provider → principal/authorities → business tenant authorization. Avoid disabling signature or audience validation just to make login "succeed."

## 17. Pre-Production Design Checklist

- [ ] Clearly define how **multi-IdP** differs from **multi-tenant** and what determines the tenant before authentication.
- [ ] Every registration ID is unique, stable, and belongs to the right tenant.
- [ ] SP Entity ID, ACS, IdP issuer, SSO URL, and signing certificates are verified per registration.
- [ ] Use the default repository when simple ID lookup suffices; customize the resolver only for clear request-based needs.
- [ ] `RelyingPartyRegistrationResolver.resolve(HttpServletRequest,String)` is implemented fail closed.
- [ ] Never trust client-spoofable `Host`/`X-Forwarded-Host`/`X-Tenant`; enforce trusted ingress routing.
- [ ] Never allow user query parameters or metadata URLs to become trusted IdP issuers/keys.
- [ ] When host/path/hint conflict, reject; never fall back to the first tenant.
- [ ] Outgoing AuthnRequest selection enforces matching policy, not just the ACS converter.
- [ ] SAMLResponse selection preserves pending AuthnRequest/browser state for SP-initiated flows.
- [ ] IdP-initiated/unsolicited Responses are accepted only per policy and never cause ambiguous issuer lookups.
- [ ] Response/Assertion signatures are verified using the exact IdP verification credentials of the chosen registration.
- [ ] Issuer, Audience, Recipient, Destination, timing, `InResponseTo`, and replay checks are all enforced.
- [ ] Metadata endpoints match each tenant and never publish the wrong Entity ID/ACS/cert.
- [ ] SLO request/response selection is configured and tested separately if federated logout is enabled.
- [ ] Never merge local accounts by email alone, and never map roles without tenant scope.
- [ ] Dynamic DB/caching has explicit lifecycle/rotation, auditing, and tenant disablement.
- [ ] Unit tests for host/path hints and integration tests for cross-tenant/multi-node/negative signatures pass.
- [ ] Never log full `SAMLResponse`, NameID, private keys, sensitive group claims, or cookies.
- [ ] Spring Security 6.x/7.x APIs are locked in with proper migration/tests; never copy legacy Spring SAML Extension examples.

## 18. Self-Check Questions

1. **Does `RelyingPartyRegistrationResolver` return an `Authentication`?** No. It returns a `RelyingPartyRegistration` for downstream components to process.
2. **What is the core method of the interface?** `resolve(HttpServletRequest request, String relyingPartyRegistrationId)`.
3. **How do Repository and Resolver differ?** A Repository looks up by ID; a Resolver selects an ID/config from the request and optional hint.
4. **What does `DefaultRelyingPartyRegistrationResolver` do?** Extracts the registration ID from context, queries the repository, and resolves URI placeholders.
5. **If there are multiple IdPs and the callback path already includes `registrationId`, is a custom resolver mandatory?** No. The default path works when trust and isolation are handled properly.
6. **Does a custom SAMLResponse converter make outbound AuthnRequests automatically pick the right tenant?** No. Outgoing flows use `Saml2AuthenticationRequestResolver` or a dedicated entrypoint.
7. **Is `Host`-based IdP selection inherently safe?** No, not unless `Host`/`Forwarded` headers are normalized and enforced by a trusted gateway.
8. **What if host is alpha and hint is beta?** Fail closed; never select beta from user input.
9. **Is `Issuer` inside `SAMLResponse` trustworthy before signature verification?** No. It may only act as a hint to look up a candidate registration.
10. **Can a SAMLResponse validly signed by beta log into alpha?** No, when tenant policy permits only alpha; registration, issuer, Audience, and ACS must match.
11. **Why is a pending AuthnRequest useful?** It binds registration, request ID, and browser/session to prevent mix-ups and login CSRF.
12. **What should you do with a shared ACS that lacks `registrationId`?** Use controlled trusted host/state/issuer mapping, a custom converter, and reject ambiguous cases.
13. **Is metadata handled by the same ACS converter?** No. It has its own `Saml2MetadataResponseResolver`.
14. **What is metadata SSRF?** Letting a user supply an IdP metadata URL that the server fetches and trusts arbitrarily.
15. **How should selection work when one tenant has two IdPs?** The user picks from the tenant's allowlist without conflating tenant and IdP.
16. **When two tenants share one issuer, is lookup by Issuer enough?** No; you need request state or another trusted distinguishing context.
17. **Is changing `loginProcessingUrl` enough for callbacks to work?** No. You must also update ACS metadata and the IdP Reply URL.
18. **Can the resolver skip signature validation?** No; the provider must verify signatures and conditions after selection.
19. **What needs attention with dynamic registrations?** Caching, atomic configs, signing cert rotation, disabled tenants, trust anchors, and auditing.
20. **What must cross-tenant authorization rely on?** Tenant ID from verified authentication, issuer/subject, and resource-specific rules.

## 19. Official Documentation

- Spring Security – SAML 2.0 Login Overview; registration repository, URI patterns, selection, and multi-IdP: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses; custom `AuthenticationConverter`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests; request resolver and AuthnRequest repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML Metadata and custom `Saml2MetadataResponseResolver`: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- JavaDoc – `RelyingPartyRegistrationResolver`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/RelyingPartyRegistrationResolver.html
- JavaDoc – `DefaultRelyingPartyRegistrationResolver`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/DefaultRelyingPartyRegistrationResolver.html
- JavaDoc – `Saml2AuthenticationTokenConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html
- JavaDoc – `Saml2LoginConfigurer`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html
- JavaDoc – `Saml2AuthenticationRequestResolver`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2AuthenticationRequestResolver.html
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OWASP – SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Conclusion:** `RelyingPartyRegistrationResolver` lets Spring Security **choose the SP↔IdP configuration from an HTTP request** rather than deriving only a simple registration ID. However, selecting a configuration **is not authentication**. A multi-tenant/multi-IdP system must enforce **trusted mappings across the entrypoint, AuthnRequest, ACS, and metadata**, forbid arbitrary client-chosen trust, and always verify issuer, signature, audience, recipient, request correlation, and tenant-scoped authorization before granting access.
