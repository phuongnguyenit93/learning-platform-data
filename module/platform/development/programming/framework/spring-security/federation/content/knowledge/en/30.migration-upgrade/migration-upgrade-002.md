# Reconciling Metadata, entityId, and Endpoints When Replacing SAML Libraries

> **Module:** Spring Security – federation. **Knowledge group:** Migration and Upgrade. **Context:** Migrating a **SAML 2.0 Service Provider (SP/Relying Party)** application from a legacy library — such as **Spring Security SAML Extension 1.x** — to **Spring Security SAML2 Service Provider** without breaking the contract with the Identity Provider (IdP/Asserting Party). Focus areas: **metadata, SP/IdP entityID, ACS, SSO, SLO, public URLs, bindings, signing/encryption certificates, validation, migration, rollback, and regression tests**. Examples use Java 17, Spring Boot 3.5.x, and Spring Security 6.5.x; all URLs, company names, and identifiers are simulated data in a test environment.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain **SP entityID**, **IdP entityID**, metadata publication URLs, `AssertionConsumerService` (ACS), `SingleLogoutService` (SLO), and `SingleSignOnService` (SSO), and why they are not interchangeable.
2. Compare **legacy application metadata**, **new release metadata**, and **actual IdP configuration**, creating a change ledger for each difference.
3. Identify default URLs in Spring SAML Extension 1.x (`/saml/SSO`, `/saml/metadata`, `/saml/SingleLogout`) and Spring Security SAML2 6.5 (`/login/saml2/sso/{registrationId}`, `/saml2/metadata/{registrationId}`, `/logout/saml2/slo`).
4. Know when to **preserve legacy entityID/ACS/SLO** so the IdP does not need to change registration, and when to migrate to new URLs via a change request.
5. Reconcile bindings, ACS `isDefault`/`index`, NameIDFormat, `AuthnRequest` signing requirements, signing/decryption certificates, and metadata trust.
6. Map legacy beans/filters to `saml2Login`, `saml2Logout`, `saml2Metadata`, `RelyingPartyRegistration`, and the new repository/resolver.
7. Design validation tests for `Issuer`, `Audience`, `Destination`, `Recipient`, `InResponseTo`, `RelayState`, `SubjectConfirmation`, time/replay, signatures, and encryption.
8. Diagnose reverse proxy HTTPS, context path, forwarded headers, cookies, session affinity, and multi-IdP issues during migration.
9. Run the Java 17 **SamlContractDiffDemo** to detect entityID/ACS/SLO/issuer/cert drift, with deterministic stdout.
10. Plan migration across sandbox → canary → cutover → rollback, preserving security and never declaring "migrated successfully" based solely on an HTTP 302.

**Prerequisites:** HTTP, TLS, SAML 2.0 Web Browser SSO, SP/IdP, AuthnRequest/Response/Assertion, XML Signature, SAML metadata, Spring Security FilterChain, Java 17, and Servlet sessions.

## 2. Core Problem: Upgrading a Library Does Not Mean Changing Federation Identity

Suppose the IdP currently accepts the legacy SP metadata:

~~~text
Legacy Spring SAML Extension 1.x:
  SP entityID  = urn:portal:production:sp
  SP ACS       = https://portal.example.org/saml/SSO
  SP SLO       = https://portal.example.org/saml/SingleLogout
  IdP entityID = https://idp.example.org/saml
  IdP SSO      = https://idp.example.org/sso
  SP signer    = alias sp-signing-2026

New Spring Security SAML2, if left as default:
  SP entityID  = https://portal.example.org/saml2/service-provider-metadata/corporate
  SP ACS       = https://portal.example.org/login/saml2/sso/corporate
  SP SLO       = https://portal.example.org/logout/saml2/slo
  IdP entityID = https://idp.example.org/saml
  IdP SSO      = https://idp.example.org/sso
  SP signer    = depends on new registration

IdP still has registered:
  Audience     = urn:portal:production:sp
  ACS          = https://portal.example.org/saml/SSO
  SLO          = https://portal.example.org/saml/SingleLogout

=> Simply changing the dependency + adding saml2Login() will not guarantee login works.
~~~

**Three strategies:**

- **A — Preserve the legacy federation contract:** Keep SP entityID, ACS, public SLO, IdP entityID, and signing trust; configure the new library to accept the legacy URLs. Suitable when there are many IdPs/partners and the goal is to minimize blast radius. Must explicitly verify HTTP method/binding, login initiation, response resolver, and real logout.
- **B — Register a new contract:** Use new defaults and update IdP metadata/registry along with reverse proxies, public URLs, certificates, and tests. This is a trust/identity-level migration, not just deploying a JAR.
- **C — Controlled parallel execution:** Create two SP registrations (different entityIDs/ACS/keys or parallel according to IdP capability) and route separately in sandbox/canary. Do not assume the IdP supports two ACSs or two SP entityIDs; in particular, avoid letting the same AuthnRequest ID/`RelayState` be handled by both stacks.

**Do not:** let the IdP issue a SAML Assertion with `Audience=urn:portal:production:sp` while the new version expects a different entityID, and then disable AudienceRestriction validation. Nor allow any `Recipient`/`Destination` to be accepted "for compatibility." That breaks trust rather than migrating.

## 3. Distinguishing Seven Commonly Confused Values

| Term | Example | Role and Comparison Points |
| --- | --- | --- |
| **SP entityID** | `urn:portal:production:sp` | Logical identifier of the Relying Party; appears in SP metadata `EntityDescriptor/@entityID`, `AuthnRequest/Issuer`, and `Assertion/AudienceRestriction` |
| **IdP entityID** | `https://idp.example.org/saml` | Asserting Party identifier; `EntityDescriptor/@entityID` in IdP metadata; expected `Response/Issuer`, `Assertion/Issuer` |
| **SP metadata URL** | `https://portal.example.org/saml2/metadata/corporate` | HTTP address to download XML metadata; **does not have to equal SP entityID** |
| **SP ACS URL** | `https://portal.example.org/login/saml2/sso/corporate` | Browser POSTs SAMLResponse here; checks `Destination`/`Recipient` and ACS binding |
| **IdP SSO URL** | `https://idp.example.org/sso` | `AuthnRequest.Destination`, taken from IdP metadata `SingleSignOnService` |
| **SP SLO URL** | `https://portal.example.org/logout/saml2/slo` | SP receives SAML LogoutRequest/LogoutResponse; metadata `SingleLogoutService` |
| **IdP SLO URL** | `https://idp.example.org/slo` | SP sends LogoutRequest to IdP and sends LogoutResponse in AP-initiated flows |

**Key distinction:** `urn:portal:production:sp` is not a URL a browser can open, yet it is a completely valid SP entityID. Changing the metadata URL from `/saml/metadata` to `/saml2/metadata/corporate` **may** have no effect on entityID if an explicit value is preserved. Conversely, if using `{baseUrl}` defaults, changing host/port/context path can unintentionally change the logical entityID as well.

### 3.1. How to Read Metadata

SP metadata typically looks like:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:portal:production:sp">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      AuthnRequestsSigned="true"
      WantAssertionsSigned="true">
    <md:KeyDescriptor use="signing">
      <!-- ds:KeyInfo contains the public verification certificate -->
    </md:KeyDescriptor>
    <md:KeyDescriptor use="encryption">
      <!-- public encryption certificate if SP needs to decrypt -->
    </md:KeyDescriptor>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/saml/SingleLogout"/>
    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>
    <md:AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/saml/SSO"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

**This is an abridged illustrative metadata snippet**; certificate comments do not replace an actual `ds:X509Certificate`. In actual operation, the IdP needs signing/decryption public certs matching the real credentials/trust policy. `EntityDescriptor` can have `ID`, `validUntil`, `cacheDuration`, and a metadata signature; these also matter in trust/refresh policy.

IdP metadata typically includes:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">
    <md:KeyDescriptor use="signing">
      <!-- Public IdP signing certificate(s) -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/sso"/>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Trust distinction:** The TLS certificate of `idp.example.org` only proves the HTTPS server via PKI; it is not by default the IdP's SAML signing certificate. The SP must trust approved signing certificates from the metadata/trust store of that exact entityID. Never take a key from `KeyInfo` inside an untrusted SAMLResponse and treat it as a successful verification.

## 4. Reconciling Legacy and New Endpoints by Function

The paths below are typical defaults described by Spring Security Extension 1.x and Spring Security 6.5 documentation. **Legacy applications may have overridden them**, so the final source of truth remains the published metadata and IdP registration.

| Function | Spring SAML Extension 1.x | Spring Security SAML2 6.5 | Migration Action |
| --- | --- | --- | --- |
| Start SP login | `/saml/login`, often with `idp`/alias | `/saml2/authenticate/{registrationId}` | Update links or custom initiation matcher/resolver |
| SP ACS | `/saml/SSO` | `/login/saml2/sso/{registrationId}`, also supports mode without registrationId | Keep legacy URI or change IdP ACS; verify binding |
| Metadata download | `/saml/metadata` | `/saml2/metadata/{registrationId}` or `/saml2/service-provider-metadata/{registrationId}` | Do not change entityID solely because download URL changed |
| Default SP entityID | Typically `{entityBaseURL}/saml/metadata` or explicit | Typically `{baseUrl}/saml2/service-provider-metadata/{registrationId}` or explicit | Pin registered identity |
| User logout trigger | `/saml/logout`, legacy `?local=true` | `POST /logout` (SLO when enabled), can separate `POST /saml2/logout` | Do not expose arbitrary state-changing GET |
| SP SLO listener | `/saml/SingleLogout` | `/logout/saml2/slo` | Synchronize IdP metadata, protocol binding |
| SAML filters | `SAMLProcessingFilter`, `SAMLLogoutProcessingFilter` | `Saml2WebSsoAuthenticationFilter`, `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter` | Compare validator logic, do not swap classes 1:1 |
| Metadata generation | `MetadataGenerator`, `MetadataDisplayFilter` | `saml2Metadata()` + registration/repository | Compare XML output |
| Multi-IdP | `ExtendedMetadata`, aliases, `idp` parameter | `RelyingPartyRegistration`/`registrationId`/resolver | Compare tenant/issuer selection |
| Bindings/profiles | Legacy supports HTTP-POST/Artifact/PAOS/HoK depending on config | Does not provide full feature parity by default | Check unported features in the migration guide |

**Binding note:** A standard SAML Response to ACS uses HTTP-POST. Legacy features such as **HTTP-Artifact** or **PAOS/Holder-of-Key** must be checked separately because modern Spring Security does not provide a one-to-one replacement for every profile. The 6.5 migration documentation lists unported features; if one is a mandatory IdP requirement, **do not cut over** until a solution is proven via integration tests.

**Login initiation vs. ACS:** `/saml2/authenticate/corporate` is where the browser asks the SP to send an `AuthnRequest`; `/login/saml2/sso/corporate` is where the browser **returns** the `SAMLResponse`. Changing one URL while forgetting the other is a common mistake. Metadata typically publishes **ACS and SLO**, not necessarily the browser initiation route.

## 5. Migration Inventory: Gather Complete Data Before Editing

Assemble a current-state package in an approved environment:

~~~text
legacy-sp-metadata.xml       actual SP XML from legacy app
legacy-idp-metadata.xml      IdP XML trusted by legacy app
idp-registration-export      SP configuration currently stored by IdP
new-sp-metadata.xml          XML emitted by new app in staging
new-idp-metadata.xml         IdP metadata trusted by new app
test-idp-approved-cert       fingerprint of approved public signer
change-ledger.csv            old/new/expected/decision/owner/test
~~~

**Never copy private keys into documents or tickets.** Metadata contains public certificates and federation topology that can still be sensitive; enforce RBAC and retention. Never edit production metadata XML just to hide a diff.

### 5.1. Mandatory Inventory Table

| Attribute | SP-Side Source | IdP-Side Source | Must Prove |
| --- | --- | --- | --- |
| SP entityID | `EntityDescriptor/@entityID` and config | IdP audience/SP identifier | **Exact** match |
| IdP entityID | IdP metadata/trusted config | IdP issuer | Right trusted provider |
| ACS | SP metadata `AssertionConsumerService` | IdP registered SSO/ACS URL | URL, binding, index match |
| SP SLO | SP metadata `SingleLogoutService` | IdP SLO callback | URL/binding/trust match if enabled |
| IdP SSO | IdP metadata `SingleSignOnService` | IdP effective SSO route | Accurate AuthnRequest destination |
| IdP SLO | IdP metadata `SingleLogoutService` | IdP effective SLO route | Request/response proper binding |
| SP signing public cert | `KeyDescriptor use=signing` | IdP SP trust | Public key verifies requests |
| SP encryption public cert | `KeyDescriptor use=encryption` | IdP encryption config | Encrypted assertion decrypted by SP |
| IdP signing public cert | Trusted IdP metadata | IdP active/rollover signer | SP verifies response/assertion |
| `AuthnRequestsSigned` | SP metadata/actual request | IdP requires signed request | Logic and key match |
| `WantAssertionsSigned` | SP metadata/policy | IdP actual assertion signatures | Proper validation, no bypass |
| NameID/format | SP metadata/request | IdP attribute policy | Stable principal mapping |
| SessionIndex | Login assertion | IdP SLO implementation | SLO targets right user/session |
| RelayState | Repository/session | Browser roundtrip | Correlation/return URL integrity |
| Timestamp/skew | SP config | IdP profile | Time validation policy preserved |
| Public origin | Reverse proxy, `{baseUrl}` template | IdP registered endpoints | Accurate HTTPS/host/port/path |
| Entity aliases | Legacy `hostedSPName`/alias | Multi-SP/tenant registry | Never selects wrong registration |

### 5.2. A Standard Change Ledger Entry

~~~text
Field: ACS.Location
Old: https://portal.example.org/saml/SSO
New candidate: https://portal.example.org/login/saml2/sso/corporate
IdP effective value: https://portal.example.org/saml/SSO
Decision: PRESERVE_OLD_UNTIL_IDP_APPROVES_CHANGE
Owner: IAM + App + Platform
Risks: SAML Destination/Recipient mismatch; cross-site POST callback
Test: SP-initiated and IdP-initiated signed SAMLResponse
Rollback: restore old route/registration atomically
~~~

**Do not stop at a "changed" label:** Classify each diff as **expected**, **requires IdP update**, **security-sensitive**, or **blocker**. Owner and test case must be explicit.

## 6. Reading Metadata Semantically, Not Comparing Raw XML Text

XML emitted by a different library may change:
- Prefix `md:` to `m:` while the namespace URI stays identical.
- Attribute order, indentation, line endings, namespace declarations.
- XML `ID`, `validUntil`, `cacheDuration`, or serialization order.
- Multiple `KeyDescriptor` elements for rollover, certificate formatting/line wraps.
- `AssertionConsumerService` having multiple endpoints with indexes/bindings.
- `SingleLogoutService` having multiple bindings (Redirect/POST) on the same or different URLs.
- `Organization`/`ContactPerson`/`AttributeConsumingService` carrying extra metadata.

**Not every XML text change is a breaking change**, but the following fields must be strictly compared:
1. `EntityDescriptor/@entityID` (SP and IdP).
2. `SPSSODescriptor/@AuthnRequestsSigned`, `/@WantAssertionsSigned`, and actual signature policy.
3. `AssertionConsumerService@Binding`, `@Location`, `@index`, `@isDefault`.
4. `SingleLogoutService@Binding`/`@Location`/`@ResponseLocation` (if present).
5. `KeyDescriptor@use` and public key fingerprints/certificate validity/rotation.
6. `NameIDFormat` and attribute release/authentication requirements.
7. IdP `SingleSignOnService`/`SingleLogoutService` target/binding.
8. Metadata signature/trust/validUntil policy.
9. SP entityID in actual AuthnRequest, expected Assertion Audience, ACS in Destination/Recipient.
10. Correlation/security validation behavior, not just metadata snapshots.

### 6.1. Example of a "Cosmetic" Non-Breaking Metadata Diff

~~~diff
- <md:EntityDescriptor entityID="urn:portal:production:sp">
+ <m:EntityDescriptor xmlns:m="urn:oasis:names:tc:SAML:2.0:metadata"
+                     entityID="urn:portal:production:sp">
~~~

If the XML has the same namespace and value, a different prefix does not change the Entity ID. By contrast:

~~~diff
- entityID="urn:portal:production:sp"
+ entityID="https://portal.example.org/saml2/service-provider-metadata/corporate"
~~~

This is a **change in SP identity** requiring registration/review, even though both are valid strings. Do not "normalize" a URN into a URL for convenience.

### 6.2. Binding URIs Must Preserve Semantics

Two common bindings:

~~~text
urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST
urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect
~~~

Switching ACS from HTTP-POST to HTTP-Redirect is not just changing an attribute; response encoding, signature handling, and browser behavior differ, and modern Spring Security does not guarantee receiving SAML Responses over Redirect. Legacy HTTP-Artifact may require SOAP artifact resolution, channel trust, and different backend endpoints; do not force HTTP-POST when the IdP only uses artifact without an agreed change.

For SLO, an IdP may support both Redirect/POST and an SP may publish one or more `SingleLogoutService` endpoints. At cutover, verify that **inbound messages** are supported by Spring with the expected binding/method; do not just keep the URL. Never conflate the RP user-trigger URL with the SP protocol listener.

### 6.3. ACS Index and Default Flag

If metadata contains:

~~~xml
<md:AssertionConsumerService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="0" isDefault="true"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://portal.example.org/saml/SSO"/>

<md:AssertionConsumerService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="1"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact"
    Location="https://portal.example.org/saml/SSO"/>
~~~

The IdP may select by default/index/binding. If the new version advertises only a single HTTP-POST ACS, verify which endpoint the IdP actually uses; do not assume every IdP automatically switches from index 1 to index 0. If the IdP hardcodes the callback, update its registration; if it relies on metadata, verify cache/refresh and trust.

## 7. Spring Security SAML2: RelyingPartyRegistration Is the Central Point

**Legacy** may store IdP metadata and SP metadata in separate beans. **New** stores the description of an SP–IdP pair in `RelyingPartyRegistration`:
- `registrationId`: internal logical key, e.g., `corporate`.
- SP `entityId`, `assertionConsumerServiceLocation`, signing/decryption keys, SLO location.
- IdP `entityId`, SSO/SLO endpoints, public verification/encryption certificates, bindings.
- A `RelyingPartyRegistrationRepository` can hold multiple registrations, each representing one trust pair.

`registrationId` is **not** the SAML Entity ID. Changing `corporate` to `corp-prod` can alter default URLs containing `{registrationId}`, even when the explicit SP entityID stays unchanged. Renaming the id requires testing login links, resolvers, repositories, and browser callbacks.

### 7.1. Java Configuration Fragment: Preserving the Legacy Contract

The following example illustrates **how to create a registration** with trusted IdP metadata and pinned URIs. It is a **Spring Configuration fragment**, requiring a Spring Boot 3.5/Spring Security 6.5 project with the `spring-security-saml2-service-provider` dependency and real test IdP metadata; it is not a standalone JDK application.

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration
    .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistrations;

@Configuration
class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration rp = RelyingPartyRegistrations
            .fromMetadataLocation(
                "https://idp.test.example.org/metadata")
            .registrationId("corporate")
            .entityId("urn:portal:production:sp")
            .assertionConsumerServiceLocation(
                "https://portal.test.example.org/saml/SSO")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(rp);
    }
}
~~~

**Important:** Because this snippet **does not configure SP signing/decryption credentials**, it is only a **baseline registration model** for aligning Entity ID and ACS; do not claim it can log in to an IdP that requires signed AuthnRequests, encrypted Assertions, or SLO. For real SSO to work, you must add keys, SLO, verifiers, HTTPS, IdP test registration, and the corresponding flows/matchers.

### 7.2. SecurityFilterChain Matching the Legacy ACS Path

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SamlWebConfig {
    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .loginProcessingUrl("/saml/SSO"))
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Explanation:** `loginProcessingUrl("/saml/SSO")` changes the request matcher of the SAML ACS processing filter. It must **match** `assertionConsumerServiceLocation("https://portal.test.example.org/saml/SSO")` and the IdP registration. With a single registration, Spring can resolve it from state or issuer. With **multiple IdPs** and a URL without registrationId, check resolver selection; some cases require a custom `RelyingPartyRegistrationResolver`/authentication converter per Spring guides. Never treat a legacy `idp` query parameter as a trusted IdP source without verifying issuer/signature.

**Does not automatically preserve old login initiation:** `/saml/login` is a browser initiation endpoint distinct from the ACS. `loginProcessingUrl` only changes where **SAMLResponse is received**, and does not automatically add `GET /saml/login`. You can update UI links to `/saml2/authenticate/corporate`, or implement a controlled redirect from the old login link to the new initiation link; never redirect a SAML POST ACS via 302.

### 7.3. Boot Properties When Registering New Endpoints

A registration is typically expressed as:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "urn:portal:production:sp"
            assertion-consumer-service-location: >-
              https://portal.test.example.org/login/saml2/sso/corporate
            assertingparty:
              metadata-uri: https://idp.test.example.org/metadata
~~~

**This content is a fragment containing no secrets.** The Boot starter must have the SAML2 module/right dependency and reachable test IdP metadata. When using the Java registration bean from Section 7.1, **do not assume** Boot YAML and the bean merge automatically; pick one clear configuration source to avoid unexpected overrides.

### 7.4. Preserving Legacy SLO URL When Truly Supported by IdP

Spring Security 6.5 allows customizing the endpoints receiving incoming SAML LogoutRequests and LogoutResponses. **DSL fragment**:

~~~java
http.saml2Logout(saml -> saml
    .logoutRequest(req ->
        req.logoutUrl("/saml/SingleLogout"))
    .logoutResponse(res ->
        res.logoutUrl("/saml/SingleLogout")));
~~~

This is only the callback matcher, **not enough** for SLO to work. You also need:
- `singleLogoutServiceLocation("https://portal.test.example.org/saml/SingleLogout")` in the registration or corresponding Boot `singlelogout.url`;
- IdP metadata containing `SingleLogoutService` and the specific binding;
- SP PKCS#8 signing private key + public X.509 certificate, with the IdP trusting the SP key;
- IdP signing certificate in trusted metadata;
- Testing both RP-initiated and IdP-initiated SLO with **actual POST/Redirect bindings**. Changing the matcher to the old URL **does not automatically convert** the new library's HTTP-POST SLO into legacy GET/Redirect behavior.

For user-triggered legacy `GET /saml/logout`, consider changing the UI to `POST /logout` with CSRF (if SAML SLO is enabled), or separating local `POST /logout` and federated `POST /saml2/logout`. Do not recreate a GET side effect just to preserve a bookmark.

## 8. Reverse Proxy: Preserving Canonical HTTPS Public URLs

Suppose the browser sees:

~~~text
https://portal.example.org/saml/SSO
~~~

While the Spring backend runs at:

~~~text
http://portal-service:8080/saml/SSO
~~~

If `RelyingPartyRegistration.entityId` or `assertionConsumerServiceLocation` uses `{baseUrl}` and the edge does not provide proper trusted forwarding, Spring may generate:

~~~text
http://portal-service:8080/login/saml2/sso/corporate
~~~

Instead of the public ACS. The IdP sends `Destination=https://portal.example.org/...`, the SP expects the private URL, and validation fails. Never remove Destination/Recipient validation to "fix" it.

### 8.1. Spring Boot Behind a Trusted Edge

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: none
~~~

**Note:** `framework` only processes `Forwarded`/`X-Forwarded-*` headers; it **does not verify that the edge is trusted**. The reverse proxy must strip/overwrite client-supplied forwarded headers, validate allowed Host/SNI, and block direct access to the backend; choose `framework`, `native`, or `none` deliberately without processing headers twice.

`SameSite=None; Secure` may be needed for SAML HTTP-POST cross-site ACS because browsers withhold `SameSite=Lax` cookies on certain cross-site POST flows, dropping the pending AuthnRequest and `InResponseTo`. Do not assume every environment needs None: evaluate browser/IdP bindings, CSRF, and third-party-cookie restrictions via E2E. `Secure`/`HttpOnly` remain necessary; login/session repositories must never fail open.

### 8.2. Prefix and Context Path

If the public SP is `https://portal.example.org/app` while the backend is at `http://portal-service:8080/`, the following URLs must align:

~~~text
Public:
  https://portal.example.org/app/saml/SSO
  https://portal.example.org/app/saml/SingleLogout

Internal:
  http://portal-service:8080/saml/SSO
  http://portal-service:8080/saml/SingleLogout
~~~

The proxy may strip `/app`, the container may use context path `/app`, or the application may use `X-Forwarded-Prefix` exactly once. Choose **one** strategy and test both outbound and inbound directions: XML metadata has the public path, AuthnRequest uses the public ACS, the IdP POSTs to the public URL, the proxy routes to the right filter, and cookie Path and CSRF do not diverge. Never use 301/302 to fix a signed SAML POST callback hitting the wrong path.

## 9. Signing and Encryption: Certificate Fingerprints Are Part of the Contract

Metadata can hold public keys in `KeyDescriptor`:
- `use="signing"`: SP public key for the IdP to verify AuthnRequest/LogoutRequest; IdP public key for the SP to verify Response/Assertion/Logout messages.
- `use="encryption"`: SP public key for the IdP to encrypt Assertions or NameIDs; the SP needs the **matching private decryption key** to decrypt.
- Omitted `use`: per SAML metadata semantics, may apply to multiple use cases depending on policy and actual keys; do not skip a key merely because the attribute is absent.

### 9.1. Three Certificate Types That Must Not Be Confused

| Type | Who Holds the Private Key? | Function | Migration Check |
| --- | --- | --- | --- |
| SP SAML signing | SP | Signs AuthnRequest/LogoutRequest/LogoutResponse | IdP trusts the right public cert |
| SP SAML encryption | SP | Decrypts ciphertext encrypted by IdP for SP | SP has the right private key, IdP uses correct public cert |
| IdP SAML signing | IdP | Signs Response/Assertion/Logout messages | SP trusts the right IdP public cert |
| HTTPS/TLS server | Ingress/IdP web server | TLS transport + hostname validation | CA chain/expiry/hostname; **never** replaces SAML signing trust |

**How to compare:** SHA-256 fingerprint over the **DER certificate** (or public key per policy) using a standard algorithm, keeping binary/public cert files separate; Base64 line breaks and PEM headers are not real certificate changes. There may be **multiple valid certs due to rollover**; never compare only the first element and delete backup keys. Certificate expiry does not automatically imply private key compromise; SAML signer rollover requires a coordinated schedule with the IdP.

### 9.2. SP Credentials in Spring Boot (Fragment)

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "urn:portal:production:sp"
            assertingparty:
              metadata-uri: https://idp.test.example.org/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/saml/sp-signing.key
                  certificate-location: file:/run/secrets/saml/sp-signing.crt
            decryption:
              credentials:
                - private-key-location: file:/run/secrets/saml/sp-decryption.key
                  certificate-location: file:/run/secrets/saml/sp-decryption.crt
~~~

**Structural example requiring an IdP sandbox + separate key material:** key files/certs must exist at runtime with a framework-compatible PKCS#8 private key format; store in a read-only secret mount, never commit to Git, Docker images, or logs. Do not use Nginx's TLS certificate for signing/decryption credentials just because "they are all X.509." If the IdP sends only signed unencrypted Assertions, decryption configuration may be unnecessary; if the IdP mandates encrypted Assertions, a missing private decryption key is a blocker.

### 9.3. Metadata Signature vs. Message Signature

These are two separate tasks:
- **Metadata trust:** verifying XML metadata is fetched from a trusted source (HTTPS/TLS, pinned keys, verified signed metadata when federation policy requires), SSRF mitigation, caching/refresh, and certificate rollover.
- **Runtime SAML message validation:** verifying signatures on Response/Assertion/Logout, expected issuer, audience, recipient, destination, conditions, and correlation.

A "well-formed" `metadata.xml` fetched from an attacker-supplied URL establishes zero trust. Never disable metadata trust checks or use trust-all TLS to speed up library migration. If IdP metadata is signed with a metadata-signing certificate different from the message-signing certificate, distinguish the two trust anchors.

## 10. Fields in AuthnRequest/Response to Reconcile After Migration

### 10.1. Outbound AuthnRequest Issued by SP

~~~text
AuthnRequest.ID                  unique, stored for correlation
AuthnRequest.IssueInstant        reasonable timestamp
AuthnRequest.Issuer              SP entityID
AuthnRequest.Destination         IdP SingleSignOnService URL
AuthnRequest.AssertionConsumerServiceURL
                               SP public ACS URL (if specified)
AuthnRequest.ProtocolBinding     expected response binding
AuthnRequest.NameIDPolicy        NameID format & allowCreate policy
AuthnRequest.ForceAuthn          per IdP policy
AuthnRequest.IsPassive           per app policy
AuthnRequest.Signature           SP signing key per binding
RelayState                       request/session state, never an open redirect
~~~

**Every field must be measured from the actual generated request**; do not conclude "we kept entityID so all other fields must match." Legacy Spring may have set a different `NameIDPolicy`, `AuthnContextClassRef`, `ForceAuthn`, or signature algorithm. If the IdP requires signed AuthnRequests, test verification using the public SP key.

### 10.2. Inbound SAML Response/Assertion from IdP

~~~text
Response.Issuer                   trusted IdP entityID
Response.Destination              SP ACS public endpoint
Response.InResponseTo             pending AuthnRequest ID (SP-initiated)
Assertion.Issuer                  trusted IdP entityID
Assertion.AudienceRestriction     expected SP entityID
SubjectConfirmationData.Recipient SP ACS public endpoint
SubjectConfirmationData.InResponseTo
                                 correlation when applicable
Conditions.NotBefore/NotOnOrAfter time + allowed skew
AuthenticationStatement.SessionIndex
                                 SLO session context if used
NameID and NameIDFormat          principal mapping contract
Signature(s)                     trusted IdP public cert
EncryptedAssertion/NameID        correct SP private decryption key
~~~

**IdP-initiated/unsolicited SSO** may omit `InResponseTo` because there is no AuthnRequest. If the legacy app allowed it, determine **how the new library supports it and what the acceptance policy is** via explicit tests. Never disable `InResponseTo` validation for all SP-initiated Responses just to make some unsolicited cases pass. Check signer/issuer/recipient/audience/time and allowed unsolicited tenants separately.

### 10.3. Do Not Use HTTP 302 as Proof

A passing E2E login must prove:
1. The browser is redirected to the approved IdP endpoint; AuthnRequest issuer/ACS/signature are valid.
2. The IdP signs a valid SAMLResponse/Assertion; the browser POSTs it to the public ACS.
3. SP validators properly accept issuer/certificate/audience/destination/recipient/time/correlation; invalid fixtures are rejected.
4. `Saml2Authentication`/principal and authorities match policy.
5. Servlet session is created/rotated securely, protected resources enforce authorization; `403` when lacking permission is not a SAML error.
6. All negative cases—wrong signature, wrong audience, wrong recipient, replay, expired Assertion—fail closed.

Seeing only `302 /home` after login does not tell you whether authentication came from SAML or a form fallback; tests must verify the authenticated mechanism.

## 11. NameID, Attributes, and Role Mapping After Switching Libraries

Migrating metadata without checking user mapping easily causes **silent authorization drift**. Legacy `SAMLAuthenticationProvider` may extract:
- NameID/NameIDFormat (`persistent`/`transient`/`emailAddress`/`unspecified`);
- AttributeStatements with friendly names or OID URIs;
- `eduPersonPrincipalName`/UPN/email/employeeId;
- Multi-valued Group/Role attributes;
- AuthnContextClassRef and `SessionIndex`.

Modern Spring Security represents the principal via `Saml2AuthenticatedPrincipal` and `Saml2Authentication`, and can use a custom converter/`UserDetailsService`/authority mapper. Do not assume `Authentication.getName()` stays identical if legacy used a NameID different from the new principal name mapping.

**Migration tests:**

| Case | What to Compare |
| --- | --- |
| Persistent NameID | Same internal user account, matching realm/issuer |
| Transient NameID | Do not use as a stable user ID when policy requires persistent |
| Email changes | Do not grant access to another account just because email matches |
| Multivalued groups | Do not turn positional values into roles; validate scope/tenant |
| Signed attributes | Do not trust unsigned/unknown-issuer attributes |
| Disabled user | Federated login may succeed while app still blocks access |
| Unsupported NameIDFormat | Fail per IdP contract, no silent fallback |
| Multi-IdP same NameID | Use issuer/tenant context, prevent identity collision |
| Authorization role mapping | Accurate `403` for users lacking roles, never grant `ROLE_ADMIN` by default |
| SessionIndex | Accurate data preserved for SLO when IdP requires it |

**Never use an email from a browser request as a principal** unless the SAML Assertion carries a valid signature and trusted issuer. The authorization layer must be QA-tested independently even when protocol authentication passes.

## 12. SLO and Logout URLs: Swapping Libraries Easily Breaks Both Directions

SAML Single Logout has two flows:
- **RP/SP-initiated:** user logs out at the Portal, SP generates a `LogoutRequest` to IdP SLO, IdP returns a `LogoutResponse` to the SP listener.
- **IdP-initiated:** IdP sends a signed `LogoutRequest` to the SP listener, SP validates it, invalidates the local session, and returns a signed `LogoutResponse`.

Legacy may use `/saml/logout` for user initiation and `/saml/SingleLogout` as the listener. Spring Security 6.5 commonly uses user `POST /logout` and listener `/logout/saml2/slo`. These are **not** interchangeable URLs.

### 12.1. SLO Migration Matrix

| Test | Expected |
| --- | --- |
| Legacy IdP still sends `/saml/SingleLogout`, new SP listens only on `/logout/saml2/slo` | 404/unprocessed; blocker until IdP is updated |
| New SP advertises legacy SLO and listener matches legacy | IdP callback hits the right filter; must check binding |
| IdP requires inbound HTTP-Redirect, new SP accepts only POST | Do not assume renaming URL suffices; test capability |
| RP LogoutRequest lacks SP signer | IdP rejects per signing policy |
| IdP LogoutRequest signed by unknown IdP | SP rejects, no forced logout |
| Signed LogoutResponse with wrong `InResponseTo` | SP rejects correlation |
| SessionIndex incompatible with IdP | IdP does not log out the right session; fix profile |
| Browser cross-site POST callback missing session cookie | Detect request repository/correlation issue |
| User local logout | SP session cleanup only; never claim IdP logout |
| PartialLogout | Report federation incomplete, not "logged out everywhere" |
| SLO while IdP is down | Local session may be cleared, federation unconfirmed |
| Replay LogoutRequest/LogoutResponse | No repeated side effects or false success |

**Security:** Never expose `GET /saml/logout` to perform state-changing user logout without risk approval and equivalent CSRF protection. For user-facing apps, use POST + CSRF. Conversely, inbound SAML protocol POSTs to the SLO listener lack a browser form CSRF token but must validate the signed SAML message; never set `csrf.disable()` across the whole app.

### 12.2. SingleLogoutService Metadata Has Two Addresses

In IdP metadata, `SingleLogoutService.Location` is the endpoint where the IdP receives LogoutRequests, and `ResponseLocation` may specify where the IdP receives LogoutResponses. In SP metadata, the corresponding fields describe the SP receiver. When comparing XML, **do not** confuse the IdP's Location with the SP's Location. Changing the new `singlelogout.url` defines the SP callback and does not implicitly change the IdP SLO URL. In the Spring DSL, callback matchers and `RelyingPartyRegistration` must stay aligned.

## 13. OpenSAML, Spring Boot, and Servlet: Systematic Compatibility Checks

### 13.1. Layers Migrate Differently

| Layer | Legacy | New | What to Test |
| --- | --- | --- | --- |
| Spring stack | Possibly Spring 4/5, javax.servlet | Boot 3/Jakarta Servlet | Dependencies, filter registration |
| SAML abstraction | Extension beans + custom OpenSAML | `saml2Login`/`RelyingPartyRegistration` | Semantic parity, keys/URLs |
| OpenSAML | Old legacy | 4/5 depending on Spring version | Resolver/validators, signatures, encrypted Assertions |
| Servlet session | Legacy container/session store | New session store (Spring Session if used) | InResponseTo/RelayState/multi-node |
| Metadata publishing | Generator/display filter | `saml2Metadata` | EntityID, ACS, SLO, bindings, certs |
| User identity | Legacy credential/principal type | `Saml2AuthenticatedPrincipal`/`Saml2Authentication` | NameID/role mapping |
| Logout | Old filters/URL | New SLO filters/URL | RP + IdP initiated |

Do not use `mvn dependency:tree` merely to confirm a JAR is present; check for **duplicate OpenSAML versions**/transitive conflicts or unsupported plugins, ensuring Boot/Spring Security/OpenSAML versions are compatible per the BOM/migration guide. Each version also has behavioral differences such as validation order, no-registration fallback, and OpenSAML defaults; regression tests must run against the exact target artifacts.

### 13.2. Why You Should Not "Copy" Legacy Validators

Legacy code may allow `unsolicited response`, customize signature trust, replay, clock skew, NameID, encryption, and authority mapping via OpenSAML internals. The new library is designed so framework defaults enforce many checks per contract. If customizing:
- Never write a validator that "always PASSes" when issuer/destination/audience is missing.
- Never use `KeyInfo` in an untrusted Assertion as a trust anchor.
- Never drop time/replay validation to accommodate an IdP with skewed clocks.
- Never use custom XML parsing logic prone to XML Signature Wrapping.
- Record decisions: **defaults**, **policy-added checks**, and **verified exceptions** with corresponding tests.

**If a legacy feature has not been ported:** mark it as a blocker, find a supported solution, or adjust the IdP profile through change-control. Secretly changing the binding on one side does not solve a support gap.

## 14. Standalone Java 17: SamlContractDiffDemo

To review migration before having an IdP sandbox, use a Java 17 comparator fed with data **already extracted from trusted metadata and the IdP registry**. The program **does not parse XML, verify signatures, or generate AuthnRequests**: it is a **policy comparator**. The demo distinguishes entityID/issuer drift, public HTTPS, ACS/SLO paths, binding/cert rotation, and approved cutover state.

**File `SamlContractDiffDemo.java`:**

~~~java
import java.net.URI;
import java.util.Objects;

public class SamlContractDiffDemo {

    record Contract(
        String spEntityId,
        String idpEntityId,
        String acs,
        String slo,
        String acsBinding,
        String signerFingerprint) {}

    static final Contract LEGACY = new Contract(
        "urn:portal:production:sp",
        "https://idp.example.org/saml",
        "https://portal.example.org/saml/SSO",
        "https://portal.example.org/saml/SingleLogout",
        "HTTP-POST",
        "sha256:sp-signer-v1"
    );

    static boolean approvedHttps(String input) {
        try {
            URI u = URI.create(input);
            return "https".equalsIgnoreCase(u.getScheme())
                && "portal.example.org".equalsIgnoreCase(u.getHost())
                && (u.getPort() == -1 || u.getPort() == 443)
                && u.getUserInfo() == null
                && u.getQuery() == null
                && u.getFragment() == null;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    static String compare(
            Contract old,
            Contract next,
            boolean endpointChangeApproved) {
        if (!Objects.equals(old.spEntityId(), next.spEntityId())) {
            return "BLOCK_SP_ENTITY_ID";
        }
        if (!Objects.equals(old.idpEntityId(), next.idpEntityId())) {
            return "BLOCK_IDP_ENTITY_ID";
        }
        if (!approvedHttps(next.acs()) || !approvedHttps(next.slo())) {
            return "BLOCK_NON_PUBLIC_HTTPS";
        }
        if (!Objects.equals(old.acsBinding(), next.acsBinding())) {
            return "BLOCK_ACS_BINDING";
        }
        if (!Objects.equals(
                old.signerFingerprint(), next.signerFingerprint())) {
            return "REVIEW_CERT_ROTATION";
        }
        boolean moved = !Objects.equals(old.acs(), next.acs())
                || !Objects.equals(old.slo(), next.slo());
        if (moved) {
            return endpointChangeApproved
                ? "APPROVED_ENDPOINT_CHANGE_NEEDS_E2E"
                : "BLOCK_ENDPOINT_CHANGE";
        }
        return "SAME_CONTRACT_NEEDS_E2E";
    }

    static void show(String name, Contract proposed, boolean approved) {
        System.out.println(name + "="
                + compare(LEGACY, proposed, approved));
    }

    public static void main(String[] args) {
        Contract modern = new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            "https://portal.example.org/login/saml2/sso/corporate",
            "https://portal.example.org/logout/saml2/slo",
            "HTTP-POST", LEGACY.signerFingerprint());

        show("unchanged", LEGACY, false);
        show("modernBlocked", modern, false);
        show("modernApproved", modern, true);

        show("newEntityId", new Contract(
            "https://portal.example.org/saml2/metadata/corporate",
            LEGACY.idpEntityId(), LEGACY.acs(), LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);

        show("wrongIdp", new Contract(
            LEGACY.spEntityId(), "https://evil.example/saml",
            LEGACY.acs(), LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);

        show("httpAcs", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            "http://portal-service:8080/saml/SSO", LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);

        show("wrongBinding", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            LEGACY.acs(), LEGACY.slo(),
            "HTTP-Redirect", LEGACY.signerFingerprint()), false);

        show("rotatedSigner", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            LEGACY.acs(), LEGACY.slo(),
            LEGACY.acsBinding(), "sha256:sp-signer-v2"), false);

        show("evilHost", new Contract(
            LEGACY.spEntityId(), LEGACY.idpEntityId(),
            "https://evil.example/saml/SSO", LEGACY.slo(),
            LEGACY.acsBinding(), LEGACY.signerFingerprint()), false);
    }
}
~~~

**Run on JDK 17+:**

~~~bash
javac SamlContractDiffDemo.java
java SamlContractDiffDemo
~~~

**Exact stdout:**

~~~text
unchanged=SAME_CONTRACT_NEEDS_E2E
modernBlocked=BLOCK_ENDPOINT_CHANGE
modernApproved=APPROVED_ENDPOINT_CHANGE_NEEDS_E2E
newEntityId=BLOCK_SP_ENTITY_ID
wrongIdp=BLOCK_IDP_ENTITY_ID
httpAcs=BLOCK_NON_PUBLIC_HTTPS
wrongBinding=BLOCK_ACS_BINDING
rotatedSigner=REVIEW_CERT_ROTATION
evilHost=BLOCK_NON_PUBLIC_HTTPS
~~~

**How to read it:**
- `SAME_CONTRACT_NEEDS_E2E`: matching policy fields in the demo **do not prove** login works; signed SAML integration tests are still required.
- `BLOCK_ENDPOINT_CHANGE`: ACS/SLO differ while the IdP change has not been approved.
- `APPROVED_ENDPOINT_CHANGE_NEEDS_E2E`: URL change is procedurally approved, but still requires IdP registration + browser/crypto tests.
- `BLOCK_SP_ENTITY_ID`: identity changed and must be treated as a federation trust change.
- `BLOCK_NON_PUBLIC_HTTPS`: URL uses HTTP or an unknown host, violating public policy.
- `REVIEW_CERT_ROTATION`: certificate change is an event requiring a trust rollout and may be valid if approved.
- `BLOCK_ACS_BINDING`: changes the response-receiving profile; must prove IdP support.

**Explicit limitations:** Fingerprints in code are **illustrative dummy strings**, not cryptographic hashes of real certificates. A production comparator should accept **SHA-256 fingerprints computed from trusted DER public certificates**, with a multi-key rollover policy. `approvedHttps` only checks scheme/host/port/structure; it does **not** check DNS rebinding, certificate trust, exact path allowlists, canonicalization, XML signatures, metadata provenance, OAuth-style open redirects, or SAML security. Never use a Java oracle to decide production user authentication.

## 15. Procedure for Safe Metadata Extraction and Automated Comparison

### 15.1. Export at the Right Time

1. From **legacy SP staging**, download the **actual SP metadata** and record the version/git commit, timestamp, public host, and entityID. Do not infer from old config XML when the metadata generator may have customized output.
2. From the **IdP sandbox**, export trusted IdP metadata and effective SP registration: entityID, ACS/SLO/bindings, SP trust certificates, policies.
3. Run the **new Spring SAML2 version** under public HTTPS staging behind the real reverse proxy, enable `saml2Metadata`, and download the actual SP metadata.
4. Lock the metadata/sha256 fingerprint snapshot and store it in an appropriately permissioned artifact store; do not place IdP private keys or SAML tokens in reports.
5. Extract fields using a secure XML parser and compare canonical values by namespace. Never rely solely on grep for XML with namespaces/optional elements/multiple endpoints.
6. Generate the change ledger with `old/new/idpEffective` fields and fill in decision/owner/tests.
7. Submit results for IAM and App review; never automatically publish new metadata to all IdPs without approval.

### 15.2. XML Parsing Security When Writing a Real Comparator

XML metadata can contain external entities/DTDs or XML signatures; if writing a custom parser to **extract information**, you must:
- Use a namespace-aware XML parser.
- Enable secure processing, disable external entities/DTD loading/XXE, and limit size and depth.
- Never fetch external entities over the network.
- Never treat successful XML parsing as a trusted metadata signature.
- Handle multiple `EntityDescriptor` elements and select **the exact allowlisted entityID**, never just the first element.
- Distinguish `SPSSODescriptor` from `IDPSSODescriptor`.
- Compare **public certificates** by DER hash, not PEM whitespace.
- Compare `Binding` as a full standard URI, not just the substring "POST."
- Do not ignore default/index ACS or `ResponseLocation` in SLO.
- Alert when metadata has an expired `validUntil` or an untrusted signer.

**Metadata comparison is a review step, not a replacement for the framework's SAML validators.** If building an internal parser, add unit tests against XML Signature Wrapping and XXE, though you do not need to write a full SAML validator yourself; use the integrated, security-reviewed framework/OpenSAML.

### 15.3. Never Compare Private Keys by Printing Them to Logs

Reconciliation should use:
- SP public signing certificate fingerprint(s).
- SP public encryption certificate fingerprint(s).
- IdP public signing certificate fingerprint(s).
- Certificate validity/overlap window and SP/IdP signing policy.
- Alias/secret version in the secret manager (never sharing private-key bytes).
- Success/signature verification of **test AuthnRequest/Response** in the IdP sandbox.

When rotating keys, perform dual-key overlap if the IdP/metadata/framework supports it; never promise that both old and new will be accepted after a password/secret rotation. Never put production certificates/keys into Git when policy forbids it; signing public certs may be published in metadata but still require provenance management.

## 16. E2E Testing After Metadata Matches

**An E2E SSO test must verify both directions accurately:**

~~~text
User Browser                    New SP                    IdP sandbox
    |                              |                           |
    | GET /saml2/authenticate/corporate                        |
    |----------------------------->|                           |
    |       AuthnRequest (Issuer=approved SP entityID)         |
    |<----------- redirect/post ---|                           |
    |--------------------- AuthnRequest ---------------------->|
    |                              |                           |
    |                  IdP validates SP signature/policy       |
    |                              |                           |
    |<------------------ signed SAMLResponse -----------------|
    | POST public ACS             |                           |
    |----------------------------->|                           |
    |                     validate IdP signer/issuer          |
    |                     Audience/Recipient/Destination     |
    |                     InResponseTo/time/replay            |
    |                     principal/authorities               |
    |<----------------- session authenticated                 |
    | GET protected resource      |                           |
    |----------------------------->|                           |
    |<----------------- 200 or authorized 403                  |
~~~

**Do not craft unsigned XML AuthnRequest/SAMLResponse strings and call it a positive test.** A real request/response must be signed per policy with the proper certificate and binding through browser/IdP sandbox. If you edit XML after signing to test Audience or InResponseTo, the signature fails first; use a **trusted test IdP signer** to re-sign a fixture intentionally wrong in one field.

### 16.1. Positive Cases

| ID | Scenario | Pass Evidence |
| --- | --- | --- |
| S01 | New SP metadata emits exact legacy entityID | Exact `EntityDescriptor/@entityID` |
| S02 | New SP metadata preserves ACS per decision | Accurate `Location`/`Binding`/index |
| S03 | Trusted IdP metadata still has right issuer | `IDPSSODescriptor`/`SingleSignOnService` |
| S04 | SP-initiated login | Correct AuthnRequest Issuer/ACS/IdP Destination |
| S05 | IdP signs Response/Assertion | New SP verifies cert/issuer/signatures |
| S06 | IdP Response Recipient is public ACS | Matches registration, not internal host |
| S07 | Audience matches SP entityID | No audience validation bypass |
| S08 | InResponseTo and RelayState match | Request/session repository correlation |
| S09 | Session user attributes & authorities | Correct user mapping/role policy |
| S10 | Same user authenticates via old/new in lab | Semantically equivalent identity, not same browser session |
| S11 | IdP-initiated login if supported | Signed unsolicited Response under explicit policy |
| S12 | RP-initiated SLO | Signed LogoutRequest, IdP response verified |
| S13 | IdP-initiated SLO | Verify incoming signed LogoutRequest, clear correct session |
| S14 | Multi-IdP registrations | Correct issuer/tenant/registration selection |
| S15 | Browser behind reverse proxy HTTPS | No internal URL, proper cookie/CSRF |
| S16 | Multi-node login callback | Correlation survives permitted routing/state store |
| S17 | Certificate rollover in sandbox | Approved keys verify throughout window |
| S18 | Intentional cutover to new ACS | IdP registry updated, signed SAML login works |

### 16.2. Negative Cases

| ID | Fault Test | Expected |
| --- | --- | --- |
| N01 | IdP Assertion Audience still old SP while new registration uses different entityID | Reject, do not loosen audience |
| N02 | IdP Response Recipient is old ACS while new SP expects new | Reject |
| N03 | SP metadata public URLs contain `http://pod:8080` | QA fail before cutover |
| N04 | Unsigned IdP Response when policy requires signed | Reject |
| N05 | Signed by untrusted IdP certificate | Reject |
| N06 | Validly signed IdP message with wrong issuer | Reject |
| N07 | Signed message with wrong Destination | Reject |
| N08 | Signed message with wrong `InResponseTo` | Reject |
| N09 | Replayed Assertion/Response | Reject, no reused session |
| N10 | Expired Assertion / future NotBefore | Reject per clock policy |
| N11 | Wrong NameIDFormat | Never map to a different account |
| N12 | Multi-IdP same NameID, different issuer | No cross-tenant principal collision |
| N13 | IdP metadata missing/invalid signer | No trust-all fallback |
| N14 | IdP metadata expired `validUntil` | Fails/alerts per policy |
| N15 | Legacy artifact-only IdP with no POST ACS | Block migration, do not pretend supported |
| N16 | Legacy callback still registered at IdP while new filter does not match | Detect 404/unprocessed |
| N17 | New SLO listener differs from IdP-configured SLO | Detect IdP callback failure |
| N18 | Unsigned IdP-initiated LogoutRequest | Reject without invalidating user session |
| N19 | Validly signed LogoutResponse with wrong `InResponseTo` | Reject correlation |
| N20 | Direct request to SP backend with spoofed X-Forwarded-Host | Not trusted, no attacker ACS |
| N21 | Browser SAML HTTP-POST omits session cookie | Detect SameSite/session issue, no bypass |
| N22 | Callback hits another node, request state missing | Reject safely; fix shared repository |
| N23 | SP signing key rotated, IdP has not updated public cert | IdP rejects; coordinated rollout |
| N24 | SP decryption key missing, IdP Assertion encrypted | Reject, no plaintext fallback |
| N25 | GET user logout lacking CSRF on legacy endpoint | Do not restore insecure behavior by default |
| N26 | Authenticated principal lacks role | 403, never grant role to mask migration error |
| N27 | Two registrations share entityID but wrong resolver | Test routing/issuer conflicts, fail |
| N28 | Proxy rewrites SAML POST callback via 302 | Detect loss of body/state; fix route |
| N29 | Metadata trust check disabled for convenience | Security QA fail |
| N30 | Malformed XML / XXE parser attempt | Reject safely |
| N31 | IdP signing certificate rotation, new SP trusts stale key | Reject, planned rollover |
| N32 | SAML logout reports PartialLogout | Not global success |

**QA must not conflate transport and protocol:** HTTP 302 to the IdP does not prove the AuthnRequest signer is right; HTTP 200 at the ACS does not prove Audience/time/correlation validation; Base64 `SAMLResponse` does not mean it is signed; a user logged in to `/home` may have come from another mechanism. Require IdP verifier events and sanitized Spring authentication mechanism evidence.

## 17. Multi-Tenant / Multi-IdP Migration

Legacy apps may select an IdP via `/saml/login?idp=partner-a` and use `ExtendedMetadata`/aliases. Spring Security SAML2 uses `registrationId` such as `corporate-a` and `partner-b`.

~~~text
New links:
  /saml2/authenticate/corporate-a
  /saml2/authenticate/partner-b

New repository:
  corporate-a -> SP entityID urn:portal:corporate-a -> IdP A
  partner-b   -> SP entityID urn:portal:partner-b   -> IdP B

Never:
  /saml2/authenticate?assertingPartyUrl=https://evil.example
  trust IdP based only on unsigned query/header
~~~

If you want to keep a single shared ACS `/saml/SSO` for multiple IdPs:
- `RelyingPartyRegistrationResolver` must select the right trust registration from prior AuthnRequest state or validated SAML issuer/context.
- IdP signing certificates/issuers must be bound to their corresponding registration.
- Do not let `NameID=alice` from IdP B map to a user from IdP A without a federation identity policy.
- Test unsolicited IdP-initiated SSO when `registrationId` is absent from the path; accept only if the resolver enforces an explicit policy.
- Do not randomize `registrationId` without reviewing default URLs and metadata; the registration name is internal yet appears in several URL templates.
- Changing one tenant's metadata must never alter the Entity ID/ACS/keys of another tenant.

**If legacy used one SP entityID serving multiple IdPs:** Spring supports multiple `RelyingPartyRegistration` pairs, but sharing the same logical SP entityID across multiple IdPs/registrations requires clear mapping/callback/session policies. Do not force one registration for all partners hoping valid signatures will pick the right IdP automatically.

## 18. Rollout Playbook: Minimizing Downtime

### Phase 0 — Baseline and Alignment

1. Export old SP metadata, trusted IdP metadata, IdP effective registration, public URLs, keys/certificate fingerprints, and login/logout behaviors.
2. Check the feature inventory: SP-initiated, unsolicited IdP-initiated, SLO, Artifact, bindings, NameID, groups, AuthnContext, signing, decryption.
3. Decide whether to preserve old entityID/ACS/SLO or register new ones; establish a change ledger with owners and fallbacks.
4. Establish baseline authentication/authorization tests, failure metrics, and redacted SAML logs.

### Phase 1 — Staging

1. Build Spring Security SAML2 with exact Java/Boot/Spring Security/OpenSAML versions.
2. Build `RelyingPartyRegistration` from trusted IdP metadata; pin entityID/ACS/cert policies.
3. Enable the metadata endpoint and compare actual XML against legacy metadata.
4. Test browser HTTPS/proxy/Host/Forwarded/SameSite/session repository.
5. Verify signed AuthnRequest/Response with the test IdP, negative tests, and SLO/multi-IdP if used.
6. If URIs/Entity IDs must change, the IdP sandbox registration must be updated and metadata re-imported properly.

### Phase 2 — Change-Window Cutover

- Use controlled DNS/ingress routing or two truly independent SP registrations if supported by the IdP.
- Never run two stacks receiving the same `SAMLResponse`/RelayState randomly when they have different session/request repositories.
- If keeping old ACS/SLO, ensure the proxy forwards directly to the new filters rather than issuing an HTTP redirect.
- If changing ACS, ensure the IdP POSTs directly to the new **HTTPS** endpoint.
- Keep the rollback route and legacy IdP registration/keys for the approved window, but never keep expired/compromised keys broadly enabled.
- Monitor signature/issuer/Audience/Recipient/InResponseTo failures, 401/403s, SLO errors, login success by tenant, and business authorization.

### Phase 3 — Post-Cutover

- Re-export SP metadata from production, compare with the approved contract, and confirm IdP effective settings have not drifted.
- Verify rollout across multiple pods/nodes/reverse proxy routes.
- Verify certificate rollover/metadata refresh, key expiry, TLS expiry, and session store TTL.
- Retire legacy keys/endpoints/filters once all traffic has migrated and the rollback window closes.
- Update operational runbooks, audit log fields, incident processes, and long-term regression tests.
- Never declare migration complete if any tenant/IdP/legacy binding is still failing.

### 18.1. Rollback Is Not Just Rolling Back a JAR

If `entityID`/ACS/SLO/certificate were changed in the IdP registry, rolling back the Spring JAR **without rolling back the IdP registration** can prevent the old SP from receiving Assertions. A rollback plan must cover:
- IdP trust/metadata/cert state,
- DNS/ingress/canonical host/path,
- old/new SP application routes,
- session/request state compatibility,
- tenant rollout order,
- restoration of registered ACS/SLO/bindings,
- secret/key validity and overlap.

If the IdP supports only one ACS, a cutover transaction/change window is required; do not promise zero downtime for a configuration that cannot run in parallel.

## 19. Migration Troubleshooting by Symptom

| Symptom | Common Discrepancy | How to Diagnose |
| --- | --- | --- |
| IdP reports unknown SP/entity | `entityID` changed when using new default | Compare SP metadata entityID against IdP registered audience |
| IdP does not POST back to SP | New ACS not yet registered | Compare `AssertionConsumerService.Location` and IdP ACS |
| SAML Response rejected for Audience | Expected SP entityID differs from Assertion Audience | Keep identity or update IdP; never disable Audience |
| SAML Response Recipient mismatch | Public ACS vs. internal URL/prefix | Fix reverse proxy/canonical baseURL/registration |
| SAMLResponse signed but invalid signature | IdP signer cert trust/rotation | Compare IdP verification certs, signed element policy |
| Encrypted Assertion decryption fails | New SP lacks private decryption key | Secret provisioning, `KeyDescriptor use=encryption` |
| RelayState/InResponseTo mismatch | Session repo/ACS flow/multi-node | Test request storage/CSRF/SameSite |
| New SP returns 404 at `/saml/SSO` | Only new default ACS enabled | Set matcher or update IdP |
| New SP login link `/saml/login` fails | Initiation route not migrated | Update UI link or controlled GET redirect |
| New SP metadata 404 | `saml2Metadata` not enabled or different URL | Check DSL/routes; never infer Entity ID from URL |
| SLO returns 404 | IdP still points to `/saml/SingleLogout` | Listener/metadata/IdP config must align |
| Signed IdP LogoutRequest rejected | Wrong IdP cert/issuer/recipient/binding | Test SLO validation, never bypass |
| SLO clears local session only | IdP SLO unsupported/offline | Classify federation unconfirmed, not global success |
| Metadata unexpectedly has new signer | Key alias/secret rollover | Fingerprint, IdP trust, and key management |
| Artifact/PAOS flow fails | Feature lacks equivalent port | Capability gap; never force POST when unsupported |
| One tenant logs in, another fails | registrationId/issuer/resolver selection | Test each IdP/tenant separately |
| HTTP redirect to Pod internal host | Forwarded headers/public origin wrong | Fix trusted ingress and `{baseUrl}` |
| Login 200 but roles missing | NameID/attributes mapping differs | Compare principal, group mapping, authorization |
| One Pod fails, others pass | Config/cert/session repository drift | Node-level comparison |
| Clock skew errors | JVM/IdP clocks differ | NTP and allowed skew; never disable time validation |
| OpenSAML upgrade breaks custom converter | Incompatible API/validator changes | Target version migration guide, dependency tree |
| Unsolicited response rejected | Old app allowed IdP-initiated, new policy differs | Verify requirement, configure/test explicit security policy |

**Troubleshooting flow:** Identity/IdP source → SP entityID → public ACS/SLO/bindings → signer/decryption certs → actual AuthnRequest/Response fields → browser cookies/correlation → principal/role mapping → authorization. Fix the right layer; never enable trust-all to mask an underlying error.

## 20. Checklists and Exercises

### 20.1. Release Gate Checklist

- [ ] Snapshots of old/new metadata and IdP effective registration exist.
- [ ] SP entityID and IdP entityID have an approved preserve/change decision.
- [ ] ACS `Location`/`Binding`/index/default and public HTTPS are accurate.
- [ ] Changing the SP metadata URL **did not** silently change the logical Entity ID.
- [ ] IdP SSO/SLO service endpoints and bindings are accurate.
- [ ] Signing/decryption public certs, private key mounts, and rollover policy are verified.
- [ ] Metadata trust/signature/validUntil are maintained per policy.
- [ ] AuthnRequest signing, NameIDPolicy, and AuthnContext are tested with the IdP.
- [ ] SAML Response/Assertion validation for issuer/audience/destination/recipient/time/correlation passes; negative cases reject.
- [ ] Legacy artifact/PAOS/HoK behavior is inventoried; unsupported features have dispositions.
- [ ] Multi-IdP registrationId/resolver/tenant boundaries are tested.
- [ ] Principal/authorities mapping and object-level authorization have not drifted.
- [ ] Browser HTTPS/SameSite/CSRF and multi-node session repos are tested.
- [ ] RP/IdP-initiated SLO is tested if required by contract.
- [ ] IdP metadata, app routes, DNS/ingress, and rollback are jointly approved.
- [ ] No private keys, raw SAML Responses/Assertions, session cookies, or real user NameIDs exist in Git/logs.
- [ ] Incident runbooks and regression monitoring are active after cutover.

### 20.2. Practice Exercises

**Exercise A – Distinguishing URIs.** Given metadata URL `/saml/metadata` and `EntityDescriptor entityID="urn:portal:production:sp"`. When moving the metadata endpoint to `/saml2/metadata/corporate`, must the Entity ID change? Explain why not.

**Exercise B – Metadata diff.** Take two XML fixtures with the same Entity ID but different `md`/`m` prefixes. Explain why a text diff reports changes while a semantic diff reports no breaking change. If ACS Location changes, which fields on the IdP must change accordingly?

**Exercise C – Endpoint mapping.** Build a mapping table from legacy `/saml/login`, `/saml/SSO`, `/saml/SingleLogout`, `/saml/metadata` to new endpoints. Indicate which is the SP-initiated user trigger, which is the ACS, and which is the SLO listener.

**Exercise D – Java 17.** Run `SamlContractDiffDemo.java` and verify the 9 lines of stdout. Change the public ACS to `http://portal-service:8080/saml/SSO` and explain `BLOCK_NON_PUBLIC_HTTPS`. State the limitations of this comparator.

**Exercise E – Registration.** Create a `RelyingPartyRegistration` for the IdP sandbox with a fixed SP entityID and legacy ACS; add a `SecurityFilterChain` with the matching matcher. Test a signed SAML Response to the ACS over browser HTTPS without using unsigned raw XML.

**Exercise F – Signed negative case.** Use the IdP sandbox to re-sign a Response with a wrong Audience but a valid signer. Prove the SP rejects due to audience, not merely because the signature broke when editing XML after signing.

**Exercise G – Certificate migration.** The IdP uses public SP cert v1, while the new SP has private key v2. Propose an overlap/approval plan and test inbound/outbound signing/encryption to avoid downtime.

**Exercise H – SLO.** The legacy IdP sends POST `/saml/SingleLogout`, while the new SP listens only on `/logout/saml2/slo`. Design two remediation options and test both RP+IdP initiated flows; explain why changing the URL alone does not resolve a binding mismatch.

**Exercise I – Multi-tenant.** The old app used `?idp=partner-a` and the new app uses `registrationId=partner-a`. Verify that identical NameIDs across two IdPs never cross-map users/tenants.

**Exercise J – Reverse proxy.** The IdP POSTs Response to `https://portal.example.org/saml/SSO`, while the backend expects `http://portal-service:8080/saml/SSO`. Explain how to fix trusted Forwarded headers/canonical ACS; never drop `Recipient/Destination`.

**Exercise K – Artifact binding.** A partner IdP uses only Artifact Binding, and the new library's migration docs indicate no direct equivalent. Present the blocker and remediation options instead of forcing the IdP to send a different binding unannounced.

**Exercise L – Release/rollback.** Write a playbook covering IdP registration export, old/new metadata, approvals, canary, login/slo tests, keys, proxy, sessions, and rollback. Emphasize why rolling back the JAR alone is insufficient if the IdP has already updated trust.

**Passing criteria:** Ability to demonstrate that **old SP + new SP + IdP** agree on the same approved federation contract, preserving signature/recipient/audience/correlation checks and changing only planned endpoints, backed by the Java 17 comparator, E2E tests, and a real rollback.

## 21. Official Documentation and Further Reading

- Spring Security 6.5 – **SAML 2.0 Extension Migration**, differences in approaches and unported features: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/saml-extension-migration.html
- Spring Security 6.5 – **SAML 2.0 Login Overview**, default URI patterns, entityId/ACS placeholders, migration of legacy URLs: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security 6.5 – **SAML 2.0 Metadata**, publication/customization: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html
- Spring Security 6.5 – **Single Logout**, customizing request/response endpoints: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – **OpenSAML Support**, versioned components/selection: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security 6.5 – **Migration to Spring Security 7, SAML 2.0**, validation and API behavior: https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html
- Spring Security SAML Extension 1.x – **Reference Documentation**, legacy `/saml/SSO`, `/saml/SingleLogout`, entityBaseURL and filters: https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/
- Spring Security – **RelyingPartyRegistration API**, issuer/entityId/ACS pair: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- OASIS SAML 2.0 Metadata – EntityDescriptor, SPSSODescriptor, ACS and SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core – Issuer, Audience, Recipient, InResponseTo and Conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Bindings – HTTP-POST/Redirect/Artifact: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
