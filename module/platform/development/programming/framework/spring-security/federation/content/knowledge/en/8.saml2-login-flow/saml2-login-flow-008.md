# OpenSAML-Based AuthenticationProvider and Creating Saml2Authentication

> **Module:** Spring Security – federation. **Parent context:** SAML2 login flow. This lesson dives into the processing path **SAMLResponse → Saml2AuthenticationToken → AuthenticationManager → OpenSAML-backed AuthenticationProvider → Saml2Authentication → SecurityContext** in a Spring Security Servlet application. Examples run on **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x**; differences when upgrading to Spring Security 7 are noted in a dedicated section.

## 1. Learning Outcomes

After completing this lesson, you can:

1. Identify the AuthnRequest-creating filter, `SAMLResponse`-handling filter, class converting HTTP requests into authentication tokens, and OpenSAML-backed provider.
2. Distinguish **unauthenticated** `Saml2AuthenticationToken` from **authenticated** `Saml2Authentication`, along with the roles of `AuthenticationManager` / `ProviderManager` and `RelyingPartyRegistration`.
3. Describe every validation layer before issuing a principal: signature, issuer, destination, status, decryption, audience, bearer subject confirmation, timestamps, correlation, and replay.
4. Understand why XML containing a NameID or a self-signed cert is insufficient to create a session; state trust boundaries across browser, IdP, SP, and internal accounts.
5. Explain how the provider converts a valid Assertion into `Saml2AuthenticatedPrincipal`, attributes, `GrantedAuthority`, and `Saml2Authentication`; distinguish default `ROLE_USER` from business permissions.
6. Configure working SAML Login on Spring Boot 3.5, inspect authenticated principals safely, and customize providers/converters using the right version's API.
7. Diagnose login failures without disabling validation; write an authentication and authorization test matrix covering both positive and negative cases.
8. Point out differences between **OpenSAML 4 ↔ 5** and Spring Security **6.5 ↔ 7.x** to avoid mixing APIs when copying examples.

**Prerequisites:** HTTP POST/302, cookies/sessions and `SecurityFilterChain`, Spring `Authentication` / `SecurityContextHolder`, basic XML Signature/X.509, IdP entity ID, SP entity ID, ACS, SAML `AuthnRequest`, `Response`, and `Assertion`. This lesson does not use OAuth/OIDC for login proof: SAML 2.0 has its own token structures and trust model.

## 2. Where AuthenticationProvider Fits in Spring Security Architecture

In the **Web Browser SSO Profile**, the browser takes the user to the IdP and brings the SAML response back to the SP. Our Spring Security application is the SP. Separate the **request-creation flow** from the **result-verification flow**.

~~~text
┌───────────────────────────────────────────────────────────────┐
│  A. LOGIN INITIATION (SP-initiated)                           │
│                                                               │
│  Browser -> GET /saml2/authenticate/corporate                │
│    -> Saml2WebSsoAuthenticationRequestFilter                  │
│    -> resolves RelyingPartyRegistration                       │
│    -> builds/signs/encodes AuthnRequest per IdP registration  │
│    -> saves request info for correlation (usually session)    │
│    -> redirects or POSTs via browser to IdP                   │
│                                                               │
│  IdP authenticates user, issues SAMLResponse                  │
└───────────────────────────────────────────────────────────────┘
                          |
                          v
┌───────────────────────────────────────────────────────────────┐
│  B. RECEIVING AND VALIDATING SAMLRESPONSE                     │
│                                                               │
│  Browser -> POST /login/saml2/sso/corporate                   │
│    + SAMLResponse=... [optionally with RelayState]            │
│        |                                                      │
│        v                                                      │
│  Saml2WebSsoAuthenticationFilter                              │
│        |                                                      │
│        v                                                      │
│  Saml2AuthenticationTokenConverter                            │
│    -> extracts message and resolved RelyingPartyRegistration  │
│    -> restores related AuthnRequest if present                │
│    -> Saml2AuthenticationToken [isAuthenticated=false]        │
│        |                                                      │
│        v                                                      │
│  AuthenticationManager / ProviderManager                      │
│        |                                                      │
│        v                                                      │
│  OpenSAML-backed AuthenticationProvider                       │
│    -> parse / verify / decrypt / validate                     │
│    -> maps validated Assertion to principal/authorities       │
│    -> Saml2Authentication [authenticated=true]                │
│        |                                                      │
│        v                                                      │
│  SecurityContextHolder (+ SecurityContextRepository/session)  │
│    -> authorization / controller / service                    │
└───────────────────────────────────────────────────────────────┘
~~~

**Responsibility breakdown:**

| Component | Input Received | Responsibility | What It Must Not Do |
| --- | --- | --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | SSO initiation URL, registration | Builds and sends AuthnRequest, saves request per repository mechanism | Decide `SAMLResponse` is valid |
| `Saml2AuthenticationRequestRepository` | Created AuthnRequest | Stores/restores transaction data for callback correlation | Turn `RelayState` into proof of identity |
| `Saml2WebSsoAuthenticationFilter` | HTTP request to ACS carrying `SAMLResponse` | Invokes converter, passes token to `AuthenticationManager`; handles success/failure | Manually decode XML and grant permissions in controllers |
| `Saml2AuthenticationTokenConverter` | HTTP request, registration resolver/repository | Builds `Saml2AuthenticationToken` for resolved registration | Declare the token authenticated |
| `AuthenticationManager` / `ProviderManager` | Authentication request token | Picks and invokes an `AuthenticationProvider` supporting the token type | Validate XML with ad-hoc controller logic |
| OpenSAML-backed provider | Unauthenticated token, metadata/credentials | Parses, verifies, decrypts, validates, creates authenticated result | Trust signers, issuers, or endpoints from untrusted input |
| `Saml2Authentication` | Principal/authorities built post-validation | Represents login result in Spring Security | Replace business authorization checks |
| `SecurityContextHolder` | Successful Authentication | Binds current principal to the request context | Automatically persist sessions when app is stateless |

Here **OpenSAML** is the library handling SAML protocol and XML Signature/Encryption. Spring Security wraps those operations in its familiar authentication API while managing `FilterChain`, context, sessions, failure handlers, and authorization.

## 3. From Request to Response: SAML Browser Flow Step by Step

### 3.1. Initiation Phase

1. User visits protected `GET /reports` without an authenticated session.
2. Spring Security picks a login mechanism and may redirect the user to `/saml2/authenticate/{registrationId}`; with multiple partners an IdP picker page may be needed.
3. `Saml2WebSsoAuthenticationRequestFilter` looks up the configured `RelyingPartyRegistration` for IdP/SP.
4. The request builder constructs `AuthnRequest` with `ID`, `IssueInstant`, `Issuer` (SP entity ID), IdP destination, and ACS. If required by contract, the SP signs with its signing credential.
5. Request info is saved via `Saml2AuthenticationRequestRepository`; default is typically the HTTP-session-backed implementation.
6. Browser sends AuthnRequest to IdP via Redirect or POST binding; IdP may prompt for password/MFA, enforce policies, or reuse an existing SSO session.
7. IdP sends a `SAMLResponse`, usually via HTTP POST to the SP's ACS, carrying `Status` and one or more Assertions (or EncryptedAssertions).

**Why store AuthnRequest?** Upon receiving the response, the SP can verify `InResponseTo` and generated transaction details, mitigating login CSRF and session mix-ups. `RelayState` can assist flow/navigation linking yet **is not a signature or proof of user authentication**; never trust an unbound `RelayState` or unverified request to pick an account.

### 3.2. ACS Reception Phase

Typical request:

~~~http
POST /login/saml2/sso/corporate HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PD94bWwgLi4u&RelayState=opaque-value
~~~

The values above merely illustrate body format; this is not a real `SAMLResponse`. The ACS URL must match SP metadata and registration at the IdP. Proxy/load balancer setups must compute scheme, host, path, and trusted forwarded headers accurately.

In matching versions, the filter receives the request and delegates to `Saml2AuthenticationTokenConverter`. The converter decodes transport-level data, determines the `RelyingPartyRegistration` to apply, and attaches the initiated request if present. **It does not set `authenticated=true`**. Seeing a `SAMLResponse` in Base64/XML only proves a client sent data—not that the IdP vouched for it.

## 4. `Saml2AuthenticationToken`: Unauthenticated Payload

`Saml2AuthenticationToken` is a Spring `AbstractAuthenticationToken` implementation carrying a **pending-verification SAML Response** to `AuthenticationManager`. In Spring Security 6.5:

- `getSaml2Response()` returns the properly decoded/decompressed XML string (**untrusted** data).
- `getRelyingPartyRegistration()` returns the resolved relying/asserting party config—the source of IdP entity ID, SP entity ID, ACS, and verification/decryption credentials.
- `getAuthenticationRequest()` may hold the saved AuthnRequest; can be `null` when no matching request exists.
- `getPrincipal()` is `null` at this stage.
- `isAuthenticated()` is always `false`. Calling a setter does not make it valid proof.

Do not equate this token with a JWT, OIDC ID Token, or a logged-in `Saml2Authentication`.

**Data flow example (illustrative code, not a controller method to write yourself):**

~~~java
// Illustrates layer ordering; filter/registration variables
// are supplied by Spring Security, not invoked manually in controllers.
Saml2AuthenticationToken pending =
        new Saml2AuthenticationToken(registration, decodedResponseXml);

Authentication verified = authenticationManager.authenticate(pending);
// Use verified only when authenticate() returns a valid result.
~~~

The snippet above is an **illustrative excerpt**, not a standalone compilable file because `registration`, `decodedResponseXml`, and `authenticationManager` come from framework layers. Never construct `Saml2AuthenticationToken` manually in a public endpoint to bypass request repository, SP-initiated correlation, or registration resolution checks.

### Registration Selection Boundary

`registrationId` (e.g., `corporate`) is Spring's internal identifier, distinct from protocol **IdP entity ID** and **SP entity ID**. With multiple partners, the converter/resolver can use the path, saved request state, or message issuer to find a registration **within preconfigured entries**. An issuer read from unverified XML can serve only as a **candidate lookup hint** and is trusted **only after** the provider verifies the signature and checks issuer/registration alignment. Never create a trust registration from an issuer or metadata URL supplied in a request.

## 5. `AuthenticationManager` and the OpenSAML-Backed Provider

Spring Security uses `AuthenticationManager` to authenticate an `Authentication` request. The common implementation `ProviderManager` finds an `AuthenticationProvider` whose `supports(Saml2AuthenticationToken.class)` returns true. For SAML, that is the OpenSAML-backed provider validating the response.

**Key classes by version:**

| Component | Spring Security 6.5 | Spring Security 7.x |
| --- | --- | --- |
| Provider with OpenSAML 4 | `OpenSaml4AuthenticationProvider` | No longer the default option; upgrade to OpenSAML 5 |
| Provider with OpenSAML 5 | `OpenSaml5AuthenticationProvider` (when matching OpenSAML 5 dependencies selected) | `OpenSaml5AuthenticationProvider` |
| Provider selection rule | Spring Security 6.5 picks based on OpenSAML dependencies present; 6.5 typically defaults to OpenSAML 4 | OpenSAML 5 preferred/default |
| Invariant layers | HTTP filter → `Saml2AuthenticationToken` → `AuthenticationManager` → validation → `Authentication` | Overall architecture intact; principal/assertion conversion APIs changed |
| Custom converter | `OpenSaml4AuthenticationProvider.createDefaultResponseAuthenticationConverter()` with `ResponseToken` converter (when using OpenSAML4) | New converter/accessor APIs—consult 7.x docs instead of copying 6.x code verbatim |
| Result | `Saml2Authentication` with `Saml2AuthenticatedPrincipal` common | `Saml2Authentication`/`Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor` increasingly preferred |

**Important warning on latest docs:** Spring Security reference URLs without a version segment usually display **Spring Security 7.x**, so an `OpenSaml5AuthenticationProvider` example there does not mean Spring Boot 3.5 uses OpenSAML 5 by default. Pin documentation versions to your project's dependencies; when upgrading, review Spring Security, OpenSAML, repositories, and deprecated APIs together.

### `supports()` and `authenticate()`

- `supports(...)` indicates whether the provider accepts this token class; **it does not assert token contents are valid**.
- `authenticate(...)` runs the provider's full authentication checks. On success, it returns an `Authentication` marked authenticated. On failure, it throws `AuthenticationException` or a SAML-specific error.
- `ProviderManager` can hold multiple providers; token type decides which provider applies. A provider supporting SAML cannot process form-login credentials or Bearer JWTs.

If you swap `AuthenticationManager` with a custom instance via `saml2Login(saml2 -> saml2.authenticationManager(...))`, preserve default checks or take full responsibility for complete SAML security. Avoid replacing the provider just to tweak principal display name or role mapping when converter/validator hooks already suffice.

## 6. OpenSAML Pipeline: Everything That Must Pass Before Creating a Principal

Processing has multiple stages. Spring Security docs outline the general order: parse, verify response signature, decrypt encrypted assertions, validate response, verify assertions, decrypt assertion elements, validate assertions, then convert to `Authentication`. Exact details vary by OpenSAML version and how the response is signed/encrypted; **every valid path must still guarantee the message is trusted and the content granting the principal is protected**.

### 6.1. Message Reception and Parsing

The provider receives decoded SAML Response XML from `Saml2AuthenticationToken` and parses it into OpenSAML `Response` and `Assertion` / `EncryptedAssertion` objects. The parser must use safe XML settings preventing entity expansion/XXE and unexpected object injection. Let Spring Security/OpenSAML handle parsing; never build an ad-hoc `DocumentBuilderFactory` and run XPath to pull out `NameID`.

### 6.2. Signature Verification

When a response or assertion carries `Signature`, the provider uses **the IdP's verification certificates in `RelyingPartyRegistration`** to verify integrity and signer. Depending on profile:

- The IdP may sign the `Response`, each `Assertion`, or both.
- Messages lacking required signatures per policy, with invalid signatures, or signed by untrusted certs must be rejected.
- An embedded certificate inside XML never makes itself a trust anchor; keys must be bound to the configured asserting party.
- Never hand-roll an XML Signature verifier or treat the mere presence of `<Signature>` as sufficient.
- Never evaluate XPath to read `NameID` from an element **outside** the signature's verified scope, preventing XML Signature Wrapping.

### 6.3. Decrypting Encrypted Elements

When `EncryptedAssertion`, `EncryptedID`, or `EncryptedAttribute` is present, OpenSAML uses the **SP's decryption credentials** in the registration to decrypt if configured. The SP metadata's public encryption certificate is where the IdP gets the key to encrypt; the SP keeps the matching private decryption key.

Successful decryption **does not prove origin**. Signature and issuer/audience/timing checks are still required. For individually signed assertions, decryption ordering of inner elements can affect signatures, which is why the provider separates response decryption from assertion decryption. Never "optimize" by decrypting and mutating the DOM before verifying the proper signature scope.

### 6.4. Validating the Response

Checks per profile/configuration:

| Check | Purpose | Failure Scenario |
| --- | --- | --- |
| Success `StatusCode` | IdP actually reported authentication success | `Responder`, `Requester`, or `AuthnFailed` |
| `Response/Issuer` | Response belongs to a trusted asserting party | Wrong IdP entity ID/tenant |
| `Destination` | Response sent to the right ACS/SP | Proxy altered scheme, host, or path |
| `InResponseTo` when request present | Binds response to SP-initiated transaction | Request not saved, wrong session/RelayState |
| Response signature | Ensures message/protected fields when response is signed | Wrong cert, signature mismatch, unsupported alg |
| Valid assertion present | Must have subject and valid auth info | Response lacks needed assertion |

Exact correlation rules depend on SP-initiated vs. IdP-initiated flows. In IdP-initiated, there is no issued AuthnRequest to match as in SP-initiated; explicit allow/deny policies, anti-replay, and extra validations are required rather than inventing fake request IDs.

### 6.5. Validating Each Assertion

An Assertion holds identity and claims the SP can consume. The provider/validator must check:

1. **Signature or profile-valid Response signature scope** protecting the Assertion. Never accept an Assertion unprotected under policy.
2. **Assertion Issuer** matches the trusted IdP; beware Response and Assertion having mismatched issuers.
3. `Conditions/NotBefore` and `NotOnOrAfter`: Assertion is within its validity window, with small clock skew and NTP monitoring.
4. `AudienceRestriction`: Assertion was issued for the exact **SP entity ID**, not another application.
5. `Subject`/`NameID` or `EncryptedID` plus `SubjectConfirmation`. For bearer flows, `SubjectConfirmationData/Recipient` must match ACS, `NotOnOrAfter` must hold, and `InResponseTo` where required.
6. `AuthnStatement` and authentication context constraints required by the app, if MFA/authentication strength policies apply.
7. **Replay protection**: prevents reusing Response/Assertion IDs within the validity window, coordinating with state/correlation and request storage. In clustered setups, verify how request/replay state is shared—never assume in-memory sessions handle every topology.
8. Consume `AttributeStatement` only after appropriate checks succeed; never grant admin rights because `role=admin` appeared in unverified XML.

**Never claim a valid signature alone equals PASS.** A signed Assertion with `Audience=app-B` cannot log into `app-A`; an expired Assertion is rejected; a replayed response cannot mint new sessions indefinitely.

### 6.6. Notes on Default Scope and Customization

Spring Security/OpenSAML supplies default validators, yet exact profile guarantees must be verified against **your version, bindings, configuration, and customizations**. In particular, cross-cluster anti-replay, restricting IdP-initiated, MFA checks, or strict NameID format checks may require added layers. Never claim defaults automatically enforce every business policy.

When customizing `setResponseValidator` or `setAssertionValidator`, **compose** new checks with the default validator whenever possible. Replacing a validator entirely and forgetting issuer, destination, time, or audience creates an authentication bypass. Business checks depending on tenant/account state are best applied after protocol validation in converters/services rather than disabling SAML verification.

## 7. From OpenSAML Assertion to `Saml2Authentication`

Once the message passes validation, the provider maps trusted claims into Spring Security's model.

In Spring Security 6.5, the default result typically contains:

- `Saml2AuthenticatedPrincipal`: principal whose `getName()` usually comes from the first Assertion's `Subject/NameID`, exposing `getAttributes()` and `getFirstAttribute(name)`; may also include registration ID and session index depending on implementation.
- `GrantedAuthority`: in standard config includes `ROLE_USER` (and depending on version/features may include an authority representing SAML authentication factor). This is a **login-layer default authority**, not a business policy.
- `Saml2Authentication`: an authenticated `Authentication` holding the principal, authorities, and SAML Response string via APIs like `getSaml2Response()`.
- `SecurityContext`: populated by the filter's success workflow; in session-based apps, persisted via `SecurityContextRepository` so subsequent requests see `Authentication`.

**Distinction to keep clear:** `Saml2AuthenticationToken` has `principal=null` and `isAuthenticated=false`; `Saml2Authentication` is the post-validation result with a principal and `isAuthenticated=true`. Never call a `Saml2Authentication` constructor manually and treat it as IdP proof; any code able to instantiate Java objects can build a token that looks "authenticated". Only standard filters/providers and app policy establish provenance.

### 7.1. Principal Data

| API | Returns | How to Use Safely |
| --- | --- | --- |
| `Authentication#getName()` | Principal name per converter | Display/log sparingly; do not assume globally unique user ID |
| `Saml2AuthenticatedPrincipal#getName()` | Usually NameID from verified Assertion | Use as identity-link key only paired with IdP/SP/format/qualifier |
| `getRelyingPartyRegistrationId()` | RP config ID, e.g., `corporate` | Pair with trusted IdP/SP metadata |
| `getAttributes()` | Map of SAML Attributes, often multi-valued | Apply contracted mappings; do not log all attributes |
| `getFirstAttribute(name)` | First value of specific attribute, if present | Check null, type, and trusted partner origin |
| `getAuthorities()` | Set of `GrantedAuthority` | Use for authorization after app tenant/role mapping |
| `Saml2Authentication#getSaml2Response()` | SAML Response XML string, may still contain encrypted parts | **Sensitive**; never expose in endpoints/logs/analytics |

**An IdP may issue multiple AttributeStatements or multiple assertions.** The default converter focuses on assertions/attributes per implementation; if business logic relies on multiple assertions, verify how your version converts them rather than assuming all AttributeStatements merge. Check the assertion contract and write tests for required fields.

### 7.2. Authentication Is Not Authorization

Suppose the IdP successfully authenticates user U and issues a valid NameID. The SP still must determine:

- Which tenant does U belong to?
- Which account is linked, and is that account `ACTIVE`?
- Has the account been disabled or revoked?
- Does U hold `ROLE_REPORT_VIEWER` or only `ROLE_USER`?
- Is U allowed to view `/reports/finance` or another tenant's data?

Each decision belongs to application policy. Never rely on default `hasRole("USER")` to open all business resources. When mapping IdP groups/roles, verify the group attribute name, issuer, allowed value list, contract version, and any MFA requirements.

## 8. How Spring Completes Login and Saves the Session

Once `AuthenticationManager` returns a valid result, `Saml2WebSsoAuthenticationFilter` (extending `AbstractAuthenticationProcessingFilter`) runs success handling in the filter chain. The framework places `Authentication` into `SecurityContextHolder` and, depending on configuration, persists `SecurityContext` via `SecurityContextRepository` (typically HTTP session in web apps).

Conceptual sequence:

~~~text
Validated Saml2Authentication
     ↓
AuthenticationSuccessHandler / success workflow
     ↓
SecurityContextHolder.getContext().setAuthentication(result)
     ↓
SecurityContextRepository.saveContext(...) (per config)
     ↓
Redirect to original request or success URL
     ↓
Next request + session cookie -> SecurityContext restored
     ↓
AuthorizationFilter enforces rules by authorities/tenant
~~~

**Version and configuration note:** this illustrates general behavior. Exact strategy/handler names and when context is saved can vary by Spring Security version, custom `SecurityContextRepository`, custom success handlers, and session policy. Configuring `SessionCreationPolicy.STATELESS` or omitting an appropriate request/session repository can cause SAML browser SSO correlation errors or lose `Authentication` across subsequent requests.

**Failure path:** the provider throws `AuthenticationException` (often `Saml2AuthenticationException` carrying SAML error details). The filter runs failure handling, grants no `Authentication`, clears authentication context as configured, and may redirect to a login/error page. Exact HTTP status depends on configuration/failure handler. Never write "every SAML error is always 401" because browser login normally uses redirects and can loop if misconfigured.

## 9. Spring Boot 3.5.x / Java 17 Example: Observing Authenticated Results

This example builds a basic SAML Service Provider with Spring Security. **It compiles once Maven resolves dependencies**, yet full login requires a **real test SAML IdP**, valid metadata, and registered SP entity ID and ACS. The IdP URL in config is illustrative, not a live endpoint.

Directory structure:

~~~text
saml-auth-provider-demo/
├── pom.xml
└── src/main/
    ├── java/demo/SamlFlowApplication.java
    └── resources/application.yml
~~~

### 9.1. `pom.xml`

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
    <artifactId>saml-auth-provider-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <name>Shibboleth Releases</name>
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

Spring Boot dependency management aligns the Spring Security version with Boot 3.5. Declare Shibboleth releases if your build environment needs it to resolve OpenSAML artifacts; manage dependency repositories per organization policy and inspect resolved versions with `mvn dependency:tree` when debugging.

### 9.2. `src/main/resources/application.yml`

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

`corporate` is the internal `registrationId`, and `metadata-uri` must be replaced with **organization-approved** metadata. Configuring `metadata-uri` lets Spring Boot build `RelyingPartyRegistrationRepository` and matching IdP verification data; to receive responses, register the SP entity ID and ACS (typically from SP metadata generated by the app) at the IdP.

**If the IdP requires signed AuthnRequests** or encrypted assertions, add SP signing/decryption credentials in Boot config and publish matching public certs in SP metadata; never put an IdP private key into the SP or disable signature verification.

### 9.3. `src/main/java/demo/SamlFlowApplication.java`

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlFlowApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DebugEndpoints {
        @GetMapping("/")
        String home() {
            return "Open /whoami to start SAML login";
        }

        @GetMapping("/whoami")
        Map<String, Object> whoami(Authentication authentication) {
            if (!(authentication instanceof Saml2Authentication saml)) {
                return Map.of("samlAuthenticated", false);
            }

            Saml2AuthenticatedPrincipal principal =
                    (Saml2AuthenticatedPrincipal) saml.getPrincipal();

            List<String> authorities = saml.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("samlAuthenticated", saml.isAuthenticated());
            result.put("authenticationType", saml.getClass().getSimpleName());
            result.put("registrationId",
                    principal.getRelyingPartyRegistrationId());
            result.put("principalPresent", principal.getName() != null);
            result.put("authorities", authorities);
            return result;
        }
    }
}
~~~

**Security note:** the endpoint returns only login-status metadata; **it does not return raw `SAMLResponse`, NameID, email, attributes, session cookies, or secrets**. `/whoami` is protected; if unauthenticated, the user is routed into SAML login. Checking `authentication instanceof Saml2Authentication` illustrates the result type, not a substitute for validation.

### 9.4. Registering with IdP and Running

1. At your test IdP, create a **SAML SP application** matching your app's URLs; enter the exact SP entity ID and ACS from SP metadata (typically `/saml2/service-provider-metadata/corporate` or equivalent endpoint depending on version).
2. Obtain IdP metadata from an approved source and replace `https://idp.example.org/saml/metadata` in YAML. Verify IdP entity ID, SSO endpoint, and signing cert.
3. Ensure Java 17+, Maven, and metadata reachability from the Spring backend. Run:

~~~bash
mvn spring-boot:run
~~~

4. Open `http://localhost:8080/`: exact output is:

~~~text
Open /whoami to start SAML login
~~~

5. Open `http://localhost:8080/whoami` or `http://localhost:8080/saml2/authenticate/corporate`. The browser goes to the IdP and then sends `SAMLResponse` to the ACS. On valid login, the controller can return JSON such as:

~~~json
{
  "samlAuthenticated": true,
  "authenticationType": "Saml2Authentication",
  "registrationId": "corporate",
  "principalPresent": true,
  "authorities": ["ROLE_USER"]
}
~~~

This is an **illustrative shape**. Authority sets or authentication class names may vary by version/config; newer releases may grant additional authorities such as `FACTOR_SAML_RESPONSE`. Only the public `GET /` string above is fixed output. Login cannot run against the nonexistent illustrative IdP URL.

**Observable result:** if `samlAuthenticated=true` and the principal was created by the provider, the current request completed the authentication flow. To prove security, negative tests are also needed: wrong signer, wrong issuer, wrong audience, invalid time, replay, decryption failure, and permission denial.

### 9.5. Why Not Print `getSaml2Response()`?

`Saml2Authentication#getSaml2Response()` can contain SAML XML, NameID, attributes, session context, signatures, and sensitive data. Even on successful login, never dump it into JSON, traces, logs, or shared docs. To debug messages, use a test environment, restrict access, redact data, and purge logs per retention policy.

## 10. Customizing OpenSAML-Backed AuthenticationProvider in Spring Security 6.5

When built-in properties cannot satisfy business needs, Spring Security lets you customize how a **verified Assertion becomes `Authentication`**. The common hook is `setResponseAuthenticationConverter` on the provider. Run the default converter first, then add business checks/mapping—avoid rewriting decryption and verification logic.

### 10.1. Configuration Example for OpenSAML 4, Spring Security 6.5

**Use only to replace the `SecurityFilterChain` bean in section 9**; never declare two filter chains with overlapping scope simultaneously. The example below enforces the exact registration, inspects verified attributes, and grants a **whitelisted** business authority when the group claim matches the IdP contract. This is a complete configuration class compilable in section 9's project (no user database needed); replace the group policy with your real contract in production.

**File `src/main/java/demo/CustomSamlSecurityConfiguration.java`:**

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml4AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomSamlSecurityConfiguration {

    @Bean
    SecurityFilterChain customSamlFilterChain(HttpSecurity http) throws Exception {
        OpenSaml4AuthenticationProvider provider =
                new OpenSaml4AuthenticationProvider();

        Converter<OpenSaml4AuthenticationProvider.ResponseToken,
                  Saml2Authentication> defaults =
                OpenSaml4AuthenticationProvider
                        .createDefaultResponseAuthenticationConverter();

        provider.setResponseAuthenticationConverter(responseToken -> {
            // Runs only after protocol validations executed by the provider.
            Saml2Authentication verified = defaults.convert(responseToken);
            if (verified == null) {
                throw new BadCredentialsException("Missing SAML principal");
            }

            String registrationId = responseToken.getToken()
                    .getRelyingPartyRegistration().getRegistrationId();
            if (!"corporate".equals(registrationId)) {
                throw new BadCredentialsException("Unexpected SAML partner");
            }

            Saml2AuthenticatedPrincipal principal =
                    (Saml2AuthenticatedPrincipal) verified.getPrincipal();

            List<GrantedAuthority> authorities = new ArrayList<>();
            authorities.add(new SimpleGrantedAuthority("ROLE_USER"));

            // Map only when the "groups" attribute from this IdP is
            // contracted and governed by policy.
            List<Object> groups = principal.getAttributes()
                    .getOrDefault("groups", List.of());
            if (groups.contains("reports-read")) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"));
            }

            return new Saml2Authentication(
                    verified.getPrincipal(),
                    verified.getSaml2Response(),
                    authorities);
        });

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/reports/**")
                            .hasAuthority("ROLE_REPORT_VIEWER")
                        .anyRequest().authenticated())
                .saml2Login(saml -> saml
                        .authenticationManager(new ProviderManager(provider)))
                .saml2Metadata(metadata -> {})
                .build();
    }
}
~~~

**Avoiding two `SecurityFilterChain` beans:** if using the class above, remove the `securityFilterChain` bean from `SamlFlowApplication` while keeping the controllers and `@SpringBootApplication`. Alternatively, place the provider/DSL inside the existing `filterChain` bean to keep a single chain.

**Why is this safer than validating XML manually?** The provider still runs default parse/verify/decrypt/validate steps. The converter receives `ResponseToken` post-validation, reads the verified principal, and turns on only whitelisted authorities for the registered IdP. Nothing lets an HTTP parameter self-grant `ROLE_REPORT_VIEWER`.

**Sample limitations:** `groups.contains("reports-read")` is simplified and assumes the IdP enforces the group-claim contract. Production needs identity linking to internal users, tenant restrictions, user status, group scoping, auditing, and multi-IdP testing. Never grant `ROLE_ADMIN` from unapproved claims; never use `principal.getName()` alone as a unique key across multiple IdPs/SPs.

### 10.2. Default Provider and Customizing Validators

Specific extension hooks for common requirements:

| Requirement | Extension Point | Warning |
| --- | --- | --- |
| Adjust principal name post-verification | Response authentication converter | Preserve identity namespace / IdP context |
| Map IdP groups to authorities | Response authentication converter or post-login role-mapping service | Whitelist per partner/tenant and check account status |
| Add custom response policy | Response validator | Combine new checks with the default validator |
| Add assertion condition | Assertion validator | Never replace all default validation with a weak check |
| Decrypt via HSM/remote crypto service | Response/assertion elements decrypter | Preserve XML signature / decrypt order and error handling |
| Pick RP/SP for multiple tenants | `RelyingPartyRegistrationResolver` / authentication converter | Select only approved registrations; never trust input issuers |
| Use distributed sessions | `Saml2AuthenticationRequestRepository`, suitable session store | Preserve correlation and anti-replay across nodes |
| Replace entire SAML auth flow | `saml2Login.authenticationManager(...)` | High risk: must faithfully re-implement full protocol checks |

**Version-specific:** `OpenSaml4AuthenticationProvider` applies only to OpenSAML 4. For OpenSAML 5 in Spring Security 6.5, use the valid classes and methods of that version. For Spring Security 7.x, check new `ResponseAuthenticationConverter`, `Saml2ResponseAssertionAccessor`, and deprecations. Never rename classes via search/replace assuming generic types and methods stay compatible.

## 11. Correlating AuthnRequest, RelayState, and Sessions Across Instances

A real-world failure when responses return from the IdP is **failing to find the original AuthnRequest**:

- User started flow on instance A; callback landed on instance B without shared session/request repository.
- Browser withheld session cookie due to SameSite/Secure/domain/path or wrong HTTPS proxy.
- Application uses stateless session policy while the default repository requires a session.
- User opened two login flows simultaneously, overwriting state or arriving with a late callback.
- RelayState was altered, mis-mapped, or treated as an independent trust anchor.

Spring Security uses `HttpSessionSaml2AuthenticationRequestRepository` as the default in common versions. In clusters, use Spring Session/distributed session storage or an appropriate request repository. Never build "store request by unsigned query RelayState" without binding to a valid browser session/initiation; that introduces login fixation and replay risks.

**Reading errors accurately:** `InResponseTo` mismatch is a correlation problem; wrong issuer/signature is a trust problem; decryption failure is an encryption-credential problem; disabled account is an authorization/provisioning problem. They are distinct and fixed in different places.

## 12. Multi-IdP Login: Trust Boundaries and Principals

With two registrations:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate-a:
            assertingparty:
              metadata-uri: https://idp-a.example/saml/metadata
          corporate-b:
            assertingparty:
              metadata-uri: https://idp-b.example/saml/metadata
~~~

The YAML is a structural example requiring real IdP metadata. Spring Security distinguishes each partner by registration. However, **never automatically merge two people** just because they share a `NameID` or email.

Conceptually sound account-linking model:

~~~text
Verified SAML Authentication
  + trusted IdP entity ID
  + trusted SP entity ID
  + NameID format/qualifiers/value
       ↓
ExternalIdentityKey
       ↓ lookup
IdentityLink -> internal_user_id -> tenant policy -> authorities
~~~

- `registrationId` is a handy config key, yet if admins can swap a registration's issuer while keeping the ID, manage migrations carefully to avoid aliasing users.
- Persistent `NameID`s can be SP-pairwise; transient NameIDs must never be used for long-lived account lookups.
- The SAML `email` attribute can change or be reassigned; never auto-link accounts across IdP A and B by email alone.
- The default provider proves identity per IdP/registration; internal permissions are still decided by the app.
- To get exact NameID name/format/qualifiers for identity linking, hook into the **verified assertion**. Common principal APIs in Spring Security 6.x may not expose every NameID/qualifier field; never parse unverified HTTP XML in controllers.

## 13. Failure Path: When the Provider Rejects SAMLResponse

`OpenSamlXAuthenticationProvider` can fail during parsing, signature verification, decryption, response validation, assertion validation, or conversion. On failure, Spring Security does not turn it into an authenticated session. Handlers may display an error/redirect and may re-challenge.

| Symptom | Potential Failing Stage | Remediation |
| --- | --- | --- |
| Missing or undecodable `SAMLResponse` | ACS/converter/transport parsing | Check POST binding, form fields, encoding, body limits |
| Registration not found | Converter/RP resolver | Check `registrationId`, session/issuer mapping, IdP metadata |
| `invalid_signature` | Response/Assertion signature verifier | Compare IdP verification cert, metadata cache, signer key rotation |
| `invalid_issuer` | Response/assertion validator | Align IdP entity ID and registration; never drop issuer checks |
| `invalid_destination` | Response destination validator | Align ACS URL, scheme/host/port, and trusted reverse proxy |
| `audience_mismatch` | Assertion validator | Align SP entity ID/metadata and `AudienceRestriction` at IdP |
| `InResponseTo` mismatch | Request repository/correlation | Session cookies, load balancer, saved/retrieved requests, SP-init flow |
| Expired assertion / `NotBefore` | Assertion time validator | Sync NTP clocks, avoid excessive clock skew |
| `EncryptedAssertion` fails to decrypt | Response decrypter | IdP's public encryption cert must match SP's private decryption key |
| `EncryptedID` / `EncryptedAttribute` error | Assertion decrypter | Check credentials, algorithms, and decrypt/signature order |
| Replayed response | State/replay control | Session/request correlation, replay cache per policy |
| `AuthnRequest` rejected by IdP | Request generation/signature/IdP policy | SP signing cert, binding, ACS, `NameIDPolicy` |
| Login succeeds, then 403 | Authorization | Role/tenant/account mapping in the application |
| Login succeeds, yet next request prompts again | Session/`SecurityContext` persistence | Cookies, `SecurityContextRepository`, SameSite, stateless policy |
| Error occurs on only one server | Cluster state/config | Sync sessions, metadata, certs, clocks, and rollouts |

**Never fix validation errors by weakening policy:** never drop signature, issuer, audience, time, or subject confirmation checks, or let `KeyInfo` self-define trusted keys. Focus on verifying the chain **issuer → recipient → message → registration → validation**.

## 14. Test Matrix for AuthenticationProvider

| Test | Expected Result | Responsible Layer |
| --- | --- | --- |
| Registered right IdP, valid Response, valid Assertion | Authenticated `Saml2Authentication`; valid principal and authorities | OpenSAML provider + converter |
| Token before passing through provider | `Saml2AuthenticationToken.isAuthenticated()==false` | Request token |
| Missing or undecodable `SAMLResponse` | No authenticated principal created | Filter/token converter |
| Response signed with unknown key | Rejected | Signature verification |
| Assertion tampered with after signing | Rejected | Assertion signature verification |
| IdP Issuer differs from trusted registration | Rejected | Issuer validation |
| Response sent to wrong ACS | Rejected | Destination/Recipient check |
| Assertion Audience belongs to another SP | Rejected | AudienceRestriction |
| Response/Assertion outside validity window | Rejected | Time validators |
| Bearer subject lacks valid Recipient | Rejected | SubjectConfirmation validation |
| No AuthnRequest matching SP-init `InResponseTo` | Rejected or correlation failure per policy | Request repository/validator |
| Replayed `SAMLResponse` | Rejected per replay/correlation policy | State and replay controls |
| Mismatched decryption credential | Fails, no session created | OpenSAML decrypter |
| IdP-initiated response forbidden by SP policy | Rejected | SP flow policy |
| Response carries non-whitelisted group claim | No privileged authority granted | Custom converter/authorization |
| Valid Assertion yet internal user is locked | App access denied | Account linking/policy |
| Identical NameID across IdP A and B | Two independent identities | User mapping service |
| Post-login request carries valid session cookie | `SecurityContext` restored on subsequent request | Session/Context Repository |
| Post-login call to endpoint needing `ROLE_REPORT_VIEWER`, user has only `ROLE_USER` | 403 Forbidden | AuthorizationFilter |
| IdP rotated signing key, SP caches stale metadata | Login fails until trust updates; rollover plan exists | Metadata/credential management |

### Automated Unit Tests vs. Integration Tests

- **Converter unit tests:** suitable only for testing responses already verified by standard validators; mocking a `Saml2Authentication` does not prove the XML signature pipeline is secure.
- **MVC tests with mocked principals:** helpful for controller authorization and role mapping, yet **do not** verify OpenSAML parsing, signatures, issuers, or audiences.
- **Integration tests with test IdP + metadata/keys:** required to prove end-to-end flows, request state, signature/decryption, and callbacks.
- **Negative security tests:** must cover wrong signer, wrong issuer, wrong audience, expiration, replay, and missing request correlation. Test in controlled staging environments—never attack production.

## 15. Operations and Monitoring Checklist

1. **Registration:** every IdP/SP has entity IDs, ACS, SSO URL, and verification credentials from approved metadata.
2. **Keys:** schedule rotation for IdP signing certs and SP decryption certs with overlap windows; never send private keys to partners.
3. **Sessions:** verify `Secure`/`SameSite` cookies, session lifetime, security context persistence, and clustered repositories.
4. **Clocks:** sync via NTP; allow only minimal necessary clock skew, alerting on spikes in expired responses.
5. **Error handling:** use clean failure handlers, prevent login loops; never expose full SAML XML or user identities on error pages.
6. **Logs:** log request ID/correlation ID, `registrationId`, error type, and timestamp minimally; redact NameID, email, `SAMLResponse`, Signature, session cookies, and secrets.
7. **Account mapping:** separate SAML principal names from internal user IDs; enforce tenant restrictions, whitelisted role mappings, and approval for new account links.
8. **Monitoring:** track login success/failure per partner, signature errors, missing correlations, decryption errors, audience mismatches, lost sessions, and certificate rotations.
9. **Deployment:** test load balancers, host/proxy headers, HTTPS ACS, multi-instance metadata versions, session replication, and rollbacks.
10. **Upgrades:** when moving Spring Security 6.x → 7.x, review OpenSAML 5, new converters/accessors, and deprecations, and run full integration tests.

## 16. Hands-On Exercises

**Exercise A – Draw the processing chain:** sketch the path of `SAMLResponse` from the browser through `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter`, `AuthenticationManager`, `OpenSaml4AuthenticationProvider`, `Saml2Authentication`, and `SecurityContextHolder`. Mark the exact point where `isAuthenticated` changes from `false` to `true`.

**Exercise B – Deploy:** use the section 9 project with a test IdP. Verify SP metadata, IdP SSO endpoint, signing cert, and ACS URL. Log in and confirm `/whoami` returns `samlAuthenticated=true`. Never print raw responses or NameIDs on public endpoints.

**Exercise C – Security testing:** in a test environment, send a Response signed by another key, with a wrong Audience, and an expired Assertion. Verify no authenticated session is created. Match logged error types against the pipeline in section 6.

**Exercise D – Customizing the provider:** use section 10's example **in place of** the default `filterChain`. Have your test IdP issue `groups=reports-read` and `groups=other`; verify only the whitelisted group receives `ROLE_REPORT_VIEWER`. Explain why tenant/account policy is still needed after protocol validation.

**Exercise E – Session/correlation:** run the app behind two instances with a load balancer. Configure without sticky sessions or a distributed repository and reproduce lost-request errors (if your environment permits); then synchronize session/repository storage and verify `InResponseTo` works. Explain why you cannot trust browser-sent `RelayState` alone.

**Exercise F – Upgrading:** compare Spring Security 6.5 OpenSAML support docs with 7.x docs. Explain why a snippet using `OpenSaml5AuthenticationProvider` from newer docs may not compile/run in a Boot 3.5 project without changing dependencies.

**Mastery criteria:** the learner can explain the end-to-end pipeline with exact tokens/filters/providers, deploy real SAML login against a test IdP, distinguish authentication from authorization, implement a custom converter properly, list at least five validation failure causes, and never rely on unverified SAML XML to grant a principal.

## 17. Official Documentation by Version

- Spring Security SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security **6.5 OpenSAML Support** (defaults to OpenSAML4, how to select OpenSAML5): https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security 6.5 API – Saml2AuthenticationToken: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticationToken.html
- Spring Security 6.5 API – OpenSaml4AuthenticationProvider: https://javadoc.io/doc/org.springframework.security/spring-security-saml2-service-provider/6.5.0/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html
- Spring Security 7.0 Migration – SAML2, OpenSAML5, and assertion accessor: https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- Spring Boot 3.5 Reference – Spring Security and SAML 2.0: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles (Web Browser SSO): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
