# SAML2 Login: RelyingPartyRegistration, Metadata, and Attribute Mapping

> **Scope:** Spring Security 6.x on the **Servlet stack** (Spring MVC, Spring Boot 3.x, Java 17+, Jakarta Servlet). This lesson explains how a Spring app acts as a **SAML 2.0 Service Provider / Relying Party (SP/RP)**, how to create and look up `RelyingPartyRegistration`, exchange metadata with an Identity Provider (IdP), receive `SAMLResponse`, and read and map SAML attributes into application identity/permissions. Spring examples require project dependencies; they are not standalone Java SE programs run via `javac`.

## 1. What Problem Does SAML2 Login Solve?

In enterprise environments, users may already be managed at an IdP (such as an internal SSO system). A web app need not manage passwords itself when it trusts the IdP and configures SAML 2.0 properly. In this model:

- **Identity Provider (IdP), also called Asserting Party:** the system that authenticates users and issues SAML assertions/responses under a trust agreement.
- **Service Provider (SP), also called Relying Party:** the Spring application that receives responses, verifies SAML security conditions, and creates `Authentication` and an application login session.
- **SAML Assertion:** the IdP's statement about the subject (user), validity timestamps/conditions, authentication method, and supplied attributes.
- **SAML Response:** the message carrying assertions from IdP to SP. Either the response, the assertion, or both may be signed depending on config/validity; signatures must be verified per the SP's trust policy.
- **Binding:** how SAML messages travel over HTTP. SP-initiated SSO commonly uses HTTP-Redirect for `AuthnRequest` and HTTP-POST for `SAMLResponse`.
- **Metadata:** XML describing an entity's entity ID, endpoints, bindings, and X.509 certificates. Metadata is **configuration/trust material**, not a login message.

This is server-side Servlet **SAML2 Login**, distinct from OAuth2 Client/OIDC. SAML uses XML assertions and SP/IdP trust; OAuth2/OIDC typically uses authorization codes and access/ID tokens. Do not move SAML configs into OAuth2 `ClientRegistrationRepository`.

### Expected Outcomes After This Lesson

You will be able to answer: which IdP a `registrationId` points to, where the SP entity ID/ACS URL live, what IdP/SP metadata contain, at which step a `SAMLResponse` is validated before trusting it, why `NameID` is not an email by default, and how to map IdP groups/roles in a controlled way.

## 2. SP-Initiated SAML2 Login Flow on Servlet

High-level diagram:

~~~text
[Browser]                         [Spring Security SP]                   [IdP]
   |                                      |                                |
   | GET /saml2/authenticate/corp         |                                |
   |------------------------------------->|                                |
   |                                      | lookup RelyingPartyRegistration |
   |                                      | build AuthnRequest + RelayState |
   | 302 Redirect to IdP SSO endpoint     |                                |
   |<-------------------------------------|                                |
   | GET IdP URL with SAMLRequest/RelayState ----------------------------->|
   |                                      |                                |
   |                           (IdP authenticates user / checks policy)    |
   |                                      |                                |
   | POST /login/saml2/sso/corp           |<--- SAMLResponse + RelayState  |
   |------------------------------------->|                                |
   |                                      | decode + verify SAML response  |
   |                                      | validate issuer/audience/ACS   |
   |                                      | validate time/subject/signature|
   |                                      | create Saml2Authentication     |
   |                                      | SecurityContext + session      |
   | login success / redirect             |                                |
   |<-------------------------------------|                                |
~~~

Steps to understand:

1. The browser visits the **SP login initiation path** `/saml2/authenticate/{registrationId}` (typically the default path). Spring queries `RelyingPartyRegistrationRepository` to identify the matching IdP.
2. Spring constructs an `AuthnRequest` (with ID, issuer, target ACS, and other parameters) and saves correlation state if required by the flow. Depending on config and IdP requirements, the `AuthnRequest` may need to be **signed with the SP's private key**.
3. The browser is redirected to the **IdP SingleSignOnService URL**; the IdP authenticates the user, enforces enterprise policies, and issues a SAML Response.
4. The browser POSTs `SAMLResponse` (typically Base64-encoded XML) to the SP's **Assertion Consumer Service (ACS)**, usually `/login/saml2/sso/{registrationId}` by default.
5. Spring Security's SAML processor must verify a **trust-aligned signature**, issuer, destination/recipient, audience, validity timestamps, and subject confirmation; for SP-initiated flows it also correlates the response against the original request (e.g., `InResponseTo`). Only after validation succeeds are identity and attributes placed into `Saml2Authentication`.
6. After sign-in, Spring Security uses Servlet `SecurityContext`/session mechanisms to store authenticated state per configuration. Authorization in the app must still rely on `GrantedAuthority`, resource ownership, and explicit policies.

**RelayState is neither a password nor authentication proof.** It correlates flow and navigation state per configuration. Never trust an arbitrary URL in `RelayState` to redirect externally without validation. SAML POST callbacks to ACS can arrive from another origin, yet that **does not mean** the app should disable CSRF on all endpoints. Keep a clear separation between the ACS handled by the SAML filter and business POST endpoints.

### Difference Between SP-Initiated and IdP-Initiated

In **SP-initiated** flows, the application originates the `AuthnRequest`, giving a basis to correlate callbacks/`InResponseTo`. In **IdP-initiated (unsolicited)** flows, the IdP pushes a SAML Response to the ACS without a prior SP request, so it typically **lacks the same level of correlation** as SP-initiated flows. Support IdP-initiated flows only when IdP/SP policies, validation, replay/login-CSRF protections, and risk acceptance are explicitly designed and tested; prefer SP-initiated when possible.

## 3. What Is RelyingPartyRegistration?

`org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration` is the **trust relationship configuration between the SP and an IdP**. It instructs Spring Security on building `AuthnRequest`, receiving `SAMLResponse`, verifying signatures, and publishing SP metadata. It does not store user login sessions or hold the current `SAMLResponse`.

| Concept | Practical meaning |
| --- | --- |
| **registrationId** | Internal Spring key, e.g., `corp`, used to select the registration and in default login/ACS URLs. |
| **SP entityId** | Identifier of the **Service Provider** in the SAML protocol; used by the IdP to identify the SP audience/issuer. |
| **ACS location / binding** | URL at the SP receiving SAML Responses, typically via HTTP-POST. The IdP must be configured with this exact public address. |
| **Asserting Party entity ID** | Issuer/entity ID of the IdP accepted by the SP. |
| **SingleSignOnService location / binding** | Endpoint and binding used by the SP to send `AuthnRequest` to the IdP. |
| **Verification X.509 credentials** | Trusted public certificate(s) used to verify the IdP's signatures. |
| **SP signing credentials** | Private key and certificate used when the SP must sign `AuthnRequest` or appropriate SP messages. |
| **SP decryption credentials** | Private key/certificate needed when the IdP encrypts assertions/NameIDs/attributes that the SP must decrypt. |
| **Metadata** | Entity ID, endpoints, bindings, and certificates exchanged between SP and IdP. |

Do not confuse these IDs:

~~~text
Spring registrationId: "corp"                         (internal key)
SP entityId:           "https://app.example.org/saml2/service-provider-metadata/corp"
IdP entityId:          "https://idp.example.org/metadata" (example only)
IdP SSO endpoint:      "https://idp.example.org/sso"      (endpoint, not entity ID)
SP ACS:                "https://app.example.org/login/saml2/sso/corp"
~~~

**Entity ID is an identifier**, not necessarily a URL that returns 200 on GET. The actual ID must match the agreement between IdP and SP verbatim. Metadata URL is where *XML metadata is fetched*. In many systems, entity ID, metadata URL, and SSO endpoint are three distinct values.

### Why Does One Registration Represent Only One Trust Configuration?

An application may trust multiple IdPs (e.g., `corp` and `partners`), each with a different issuer, certificate, and SSO location. `registrationId` selects the right configuration. Never accept an arbitrary IdP URL from a query parameter and trust any `SAMLResponse` from that URL. For multi-tenant setups, map tenant → trusted registration and isolate credentials/policies.

## 4. RelyingPartyRegistrationRepository: Looking Up the Right Configuration

`org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository` is the interface enabling Spring to find an RP registration by key:

~~~java
RelyingPartyRegistration findByRegistrationId(String registrationId);
~~~

- Spring SAML filters query the repository to pick the matching issuer, ACS URL, and trust certificate.
- With `InMemoryRelyingPartyRegistrationRepository`, the repository holds one or more registrations loaded at startup.
- If lookup returns nothing, the flow cannot construct/recognize a valid RP; the app should reject via framework mechanisms rather than picking another provider arbitrarily.
- The repository is **not** a password or token database; verified SAML Responses produce a separate `Saml2Authentication`.

Like other configuration repositories in Spring Security, an in-memory repository fits well when the IdP set is relatively static. Dynamic repositories must handle certificate updates, metadata refreshes, concurrent logins, and consistency across `AuthnRequest`/ACS callbacks.

## 5. SAML Metadata: IdP Metadata vs. SP Metadata

One of the most important integration steps is **accurate two-way metadata exchange**.

| Metadata | Who publishes it? | How does SP/IdP use it? |
| --- | --- | --- |
| **IdP / Asserting Party metadata** | IdP | SP reads IdP entity ID, SSO/SLO endpoints, supported bindings, verification certificates, and IdP parameters. |
| **SP / Relying Party metadata** | Spring app (SP) | IdP identifies SP entity ID, ACS URL/binding, and SP certificates if signed requests/encrypted assertions are required. |

Excerpt example of **IdP metadata** (abbreviated conceptual XML, not a complete document for import):

~~~xml
<EntityDescriptor entityID="https://idp.example.org/entity">
    <IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <KeyDescriptor use="signing">...</KeyDescriptor>
        <SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://idp.example.org/sso"/>
    </IDPSSODescriptor>
</EntityDescriptor>
~~~

Real XML requires standard SAML metadata namespaces, actual `KeyInfo/X509Certificate` contents, and sometimes a metadata signature. The `...` in the snippet **only denotes omitted structure** and must not be imported literally. Fetch complete IdP metadata from a trusted channel rather than manually transcribing certificate text.

Snippet example of **SP metadata** (also an abbreviated XML outline):

~~~xml
<EntityDescriptor entityID="https://app.example.org/saml2/service-provider-metadata/corp">
    <SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://app.example.org/login/saml2/sso/corp"
            index="0"/>
    </SPSSODescriptor>
</EntityDescriptor>
~~~

What implementers must cross-check **on real metadata**: SP entity ID, ACS URL, binding, signing/decryption certs (if configured), IdP issuer, SSO URL, and signature verification certs. **Never guess the issuer by taking the metadata URL**, and never assume an HTTPS metadata URL guarantees every future certificate is trustworthy.

### Metadata Certificates Are Not HTTPS Keys

- **TLS certificate:** protects the HTTPS connection when downloading metadata or sending requests.
- **SAML signing certificate:** verifies XML signatures on SAML messages/assertions; it may differ from the TLS cert and have a separate lifecycle.
- **SP private signing key:** never appears in metadata; SP metadata publishes only the necessary public certificate.
- **Decryption private key:** must also stay on the server/secret store, never sent to the IdP as private material.
- When an IdP rotates signing keys, metadata may hold multiple valid certificates during a transition window. Establish a procedure to update registrations/trust rather than reflexively deleting old certs or trusting unknown ones.

Load metadata from a trusted URI or a local XML copy with verified provenance. Untrusted user-supplied metadata can cause **SSRF**, redirects to malicious endpoints, or alter the verification keys trusted by the SP.

## 6. Boot Configuration via IdP Metadata URI

This is usually the cleanest approach when the IdP provides complete metadata. A Servlet project uses Java 17+, Spring Boot 3.x, `spring-boot-starter-web`, `spring-boot-starter-security`, and the `spring-security-saml2-service-provider` module; let the Spring Boot BOM manage compatible dependency versions.

Example Maven dependencies inside `pom.xml` (this is a **configuration fragment**, not a complete POM):

~~~xml
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
~~~

Example `application.yml` using a hypothetical IdP serving SAML metadata:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

**Analysis:**

- `corp` is the **registrationId**. It appears in the login initiation URL `/saml2/authenticate/corp` and default ACS configuration.
- `metadata-uri` points to the **IdP metadata**, from which Spring builds the Asserting Party configuration; it is not a link to SP metadata.
- To run for real, replace with the reachable metadata URL of an actual IdP with verified provenance containing valid issuer/endpoints/verification certificates. In many loading setups, metadata is read during registration/startup; **do not assume the library automatically refreshes certificates** when the IdP rotates keys.
- Boot auto-creates `RelyingPartyRegistrationRepository` from YAML if no app-defined bean exists. If you already defined a Java repository bean, YAML registrations **do not necessarily merge automatically**; pick one consistent management approach.
- When the IdP requires signed `AuthnRequest` or encrypted assertions, add SP **signing** or **decryption credentials**; they are not inferred from IdP metadata. Private keys must be protected separately.

### Notes on Signing/Decryption

In Boot config, SP signing credentials typically consist of **private-key-location** and **certificate-location**; IdP verification credentials are public certificates from IdP metadata. Optional structure example:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: classpath:saml/sp-signing.key
                  certificate-location: classpath:saml/sp-signing.crt
~~~

This is an **optional supplement** for `registration.corp`, not a complete YAML config and not pointing to a real private key. In production, do not commit private keys into repositories without proper protection; use secret stores, filesystem permissions, and rotation processes. If the IdP does not require the SP to sign requests, avoid adding signing credentials just to "fill out all fields."

## 7. Configuring SecurityFilterChain and Default Endpoints

Example `SamlSecurityConfig.java` in a Boot component-scanned package. It uses the YAML repository above; the example targets **Spring Security 6.1+** to use the `saml2Metadata` DSL:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                        "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Roles of each piece:

- `.saml2Login(...)` enables filters/handlers for SAML2 SSO on the Servlet stack. Requires a valid `RelyingPartyRegistrationRepository`.
- `.saml2Metadata(...)` enables publishing SP metadata on the Spring Security-supported endpoint, typically `/saml2/service-provider-metadata/{registrationId}`. Check the exact URL in the deployed framework version.
- `anyRequest().authenticated()` requires authentication for remaining resources. To implement admin/staff permissions, **map SAML attributes to `GrantedAuthority`** and configure matching authorization rules.
- `permitAll` on SP metadata does not make business paths public. Metadata typically must be reachable by the IdP/admins to register the SP; if separate security policies apply, scope accordingly.
- This config does **not** disable CSRF protection, alter session policies, or automatically turn on single logout or group mapping. Those capabilities require dedicated configuration and testing.
- Behind a reverse proxy, generate the SP entity ID/ACS using a **trusted public HTTPS base URL**; avoid request-generated metadata emitting `http://localhost:8080` or internal hosts when the IdP knows only the public hostname. Accept forwarded headers only from proxies you control.

### URLs to Cross-Check

| Path / parameter | Meaning |
| --- | --- |
| `/saml2/authenticate/corp` | SP URL typically initiating a SAML `AuthnRequest` to the IdP. |
| `/login/saml2/sso/corp` | Default ACS endpoint typically handling `SAMLResponse` POSTs. |
| `/saml2/service-provider-metadata/corp` | Typical SP metadata URL when `saml2Metadata` is enabled. |
| **SP entity ID** | ID inside SAML XML and SP metadata; must be registered accurately at the IdP. |
| **IdP SSO URL** | Endpoint on the IdP receiving `AuthnRequest`; read from IdP metadata. |
| **IdP issuer/entity ID** | Value Spring matches against the SAML response/assertion issuer per trust configuration. |

These paths can be customized and are also affected by the Servlet context path. **Never assume default endpoints prove** public URLs are accurate when running behind a proxy or under a subpath.

## 8. Creating RelyingPartyRegistration in Java Without Boot YAML

You can use `RelyingPartyRegistrations.fromMetadataLocation(...)` and an in-memory repository. Example `SamlRegistrationConfig.java` is an **alternative** to YAML `spring.security.saml2.relyingparty.registration.corp`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
                .fromMetadataLocation("https://idp.example.org/saml/metadata")
                .registrationId("corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }
}
~~~

- `fromMetadataLocation(...)` builds the registration from **IdP metadata**. The URL is illustrative; real/trusted metadata is needed to initialize successfully.
- `registrationId("corp")` is the internal key for lookups/URLs, not the IdP entity ID.
- `build()` creates the configuration; it does not log a user in.
- The repository holds one or more registrations for Spring Security's filter chain.
- If the IdP requires a specific SP entity ID, ACS URL, or signing credentials, add them to the builder/config before `build()` per the IdP agreement; do not rely blindly on defaults.
- **Do not configure two repository beans of the same type side by side** expecting Boot to merge them automatically. One clear registration source avoids callbacks failing with wrong issuers/certificates.

This is a Spring class requiring dependencies and real IdP metadata; it does not run standalone with plain `javac/java`. Unit tests can construct the repository from trustworthy local metadata fixtures to verify lookups, while end-to-end tests need a real or sandbox IdP.

## 9. Accessing User Details from Saml2Authentication

Once a `SAMLResponse` is verified, Spring Security creates a `Saml2Authentication` whose principal implements `Saml2AuthenticatedPrincipal`. Key fields include **NameID** (`getName()`) and SAML attributes (`getAttributes()`, `getFirstAttribute(...)`).

### 9.1 NameID Is Not an Email by Default

In SAML, the subject can hold a `NameID` in various formats: persistent, transient, email-address, or an IdP-specific identifier. For example:

~~~text
SAML Subject/NameID = "A7D0C1E4F..."
Attribute Name="email" = "lan@example.org"
Attribute Name="displayName" = "Lan Nguyen"
Attribute Name="groups" = ["employees", "app-report-readers"]
~~~

The structure above is sample data only. `NameID` can be an opaque ID and should be treated as a **stable identifier key** only when the IdP genuinely commits to stability, uniqueness, and tenant boundaries. Never use email automatically as a primary key if emails can change or be reassigned. If the IdP switches `NameID` from persistent to transient, re-evaluate your account-linking strategy.

### 9.2 Reading Attributes in a Spring MVC Controller

Example `SamlProfileController.java` with an endpoint requiring successful login:

~~~java
package com.example.web;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlProfileController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        String nameId = principal.getName();
        String email = principal.getFirstAttribute("email");
        String displayName = principal.getFirstAttribute("displayName");

        Map<String, String> result = new LinkedHashMap<>();
        result.put("subject", nameId);
        result.put("email", email == null ? "" : email);
        result.put("displayName",
                displayName == null ? "" : displayName);
        return result;
    }
}
~~~

This code requires successful SAML2 login, `/me` protected by `authenticated()`, and the IdP actually emitting attributes named `email`/`displayName` (otherwise they return `null`). It **does not fabricate data** if the IdP omits them. Never return sensitive SAML data to public endpoints, especially full `getAttributes()`, raw `SAMLResponse` XML, or session indices.

An illustrative response given the hypothetical data above:

~~~json
{
  "subject": "A7D0C1E4F...",
  "email": "lan@example.org",
  "displayName": "Lan Nguyen"
}
~~~

This JSON is **hypothetical** assuming the IdP emits those exact attributes; Spring Security does not guarantee these keys or values in all environments.

### 9.3 Attribute Name, FriendlyName, and URI/OID

SAML assertions can carry attribute names in multiple forms: `Name="email"`, `Name="urn:oid:0.9.2342.19200300.100.1.3"`, `FriendlyName="mail"`, or URIs per the IdP's schema. `getFirstAttribute("email")` works only when the **actual attribute name** loaded by Spring is `email`.

Tasks during integration:

1. Ask the IdP for the exact list of **Attribute Names** and a valid test response sample (with PII/keys redacted).
2. Identify the `NameID` format, unique user ID attribute, email, display name, groups, and value lists.
3. Choose a stable schema (name/URI) for the app; never guess from `FriendlyName` or labels shown in the IdP admin UI.
4. Distinguish **single-valued** from **multi-valued** attributes; `getFirstAttribute` returns only the first value when multiple exist.
5. Preserve semantics and Unicode encoding; test missing attributes, empty lists, type changes, and schema changes.
6. When linking accounts, always bind the user to a trusted issuer/tenant plus stable ID; prevent account takeover when emails collide across two IdPs.

## 10. Mapping SAML Attributes to Spring Security Roles

Spring Security cannot infer `ROLE_ADMIN` automatically from any SAML attribute containing the word "admin." SAML attributes are **provenance-verified data** once a response validates, yet the meaning of each group/role must still be explicitly configured by the application.

Suppose the IdP emits:

~~~text
Attribute Name="groups":
  - employees
  - finance-readers
  - app-admins

Application policy:
  employees       -> ROLE_USER
  finance-readers -> REPORT_READ
  app-admins      -> ROLE_ADMIN
~~~

**Good rule:** use an allowlist of group names issued by a trusted IdP and map them to narrow, meaningful application authorities. Never convert arbitrary strings from an assertion into `ROLE_*` privileges. Administrative privileges in particular must depend on the right issuer, right attribute name, and an approved policy.

### 10.1 Java Example: Pure, Easily Unit-Testable Mapping Function

Class `SamlGroupAuthorityPolicy.java` below illustrates only the **mapping logic**. It does not register itself as a filter or modify `SecurityContext`; integrate it into the stage that converts SAML authentication into principal/authorities using the API of your **Spring Security version**.

~~~java
package com.example.security;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;

public final class SamlGroupAuthorityPolicy {

    private SamlGroupAuthorityPolicy() {
    }

    public static Set<GrantedAuthority> map(
            Saml2AuthenticatedPrincipal principal) {

        List<String> groups = principal.getAttribute("groups");
        Set<GrantedAuthority> authorities = new HashSet<>();

        if (groups == null) {
            return Set.of();
        }
        if (groups.contains("employees")) {
            authorities.add(new SimpleGrantedAuthority("ROLE_USER"));
        }
        if (groups.contains("finance-readers")) {
            authorities.add(new SimpleGrantedAuthority("REPORT_READ"));
        }
        if (groups.contains("app-admins")) {
            authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
        }
        return Set.copyOf(authorities);
    }
}
~~~

Explanation:

- The `groups` list issued by the IdP **must be accepted only after the entire SAML assertion validates successfully**. This function does not verify SAML signatures itself.
- Missing `groups` returns an empty authority set, never implicitly granting `ROLE_ADMIN`.
- `hasRole("ADMIN")` checks `ROLE_ADMIN` per the default prefix; `hasAuthority("REPORT_READ")` checks the exact authority `REPORT_READ`.
- Do not grant `ROLE_USER` to everyone automatically if the app requires membership in `employees`; in this example roles are granted only when the matching group is present.
- If the IdP uses an attribute URI/OID instead of `groups`, change to the **exact name** and ensure the list/data type matches.
- Attaching authorities to `Saml2Authentication` depends on your Spring version's authentication/provider extension points; the function above is a **reusable/testable policy**, not a config that by itself makes `@PreAuthorize` see new roles.

### 10.2 Where Should Authority Mapping Be Integrated?

Common implementation approaches:

- During the **authentication conversion** stage supported by the SAML authentication provider: after validating the response and building the principal, extract trusted attributes → apply mapping → build `Authentication` with the right granted authorities.
- Use an **internal authorization service** after linking `NameID`/issuer to an enterprise account; this is a solid choice when business roles are not managed by the IdP.
- Scope mapping by **issuer + registrationId + attribute schema** when multiple IdPs exist; identical `"app-admins"` strings from two IdPs must not automatically grant identical privileges.

Never just write `@PreAuthorize("hasRole('ADMIN')")` hoping an IdP attribute turns into an authority automatically. Verify `Authentication.getAuthorities()` in an integration test **after the mapping step**. Provider-related classes/OpenSAML APIs evolved across Spring Security 6.x; when using a specific extension point, check the exact API/version instead of copying snippets from another version.

### 10.3 Testing Mapping Policy Without an IdP

In unit tests, construct a synthetic principal with `DefaultSaml2AuthenticatedPrincipal` to test mapping. Example JUnit 5 file `SamlGroupAuthorityPolicyTest.java`:

~~~java
package com.example.security;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;

class SamlGroupAuthorityPolicyTest {

    @Test
    void mapsOnlyAllowlistedGroups() {
        var principal = new DefaultSaml2AuthenticatedPrincipal(
                "subject-123",
                Map.of("groups", List.of("employees", "finance-readers")));

        var authorities = SamlGroupAuthorityPolicy.map(principal)
                .stream()
                .map(a -> a.getAuthority())
                .toList();

        assertTrue(authorities.contains("ROLE_USER"));
        assertTrue(authorities.contains("REPORT_READ"));
        assertFalse(authorities.contains("ROLE_ADMIN"));
    }
}
~~~

This test only verifies the Java class's **group-mapping rules**; it does not prove SAML signatures, issuers, ACS callbacks, or filter chains work. Integration tests must use a test/sandbox IdP and validly signed responses to verify trust chains along with real authentication/authorization.

## 11. Security Conditions You Must Never Skip When Validating SAML Responses

Never parse `SAMLResponse` yourself with an XML parser and call `SecurityContextHolder.getContext().setAuthentication(...)` based solely on a `NameID` or email field. Let the SAML authentication provider verify messages and mandatory conditions.

Key validation groups:

- **Signature & trust:** assertion/response signatures valid per SP policy using permitted certificates from the corresponding IdP; never trust an arbitrary cert embedded inside the response.
- **Issuer:** assertion/response originates from the expected IdP entity ID for the registration, not an arbitrary issuer.
- **Audience restriction:** assertion is issued for the right SP entity ID. An assertion for app A must never log into app B.
- **Destination/Recipient/ACS:** response is addressed to the SP's exact endpoint with matching binding and subject confirmation; never accept responses meant for another SP.
- **Time conditions:** `NotBefore`, `NotOnOrAfter`, and subject confirmation must be valid within reasonable clock skew; never disable time checks to bypass clock drift.
- **Correlation:** for SP-initiated flows, verify request ID and `InResponseTo`, plus `RelayState`/session correlation where applicable.
- **Replay:** reject assertions/responses replayed beyond policy; replay prevention may require a shared state store across multiple nodes.
- **XML safety:** use a supported SAML/OpenSAML stack; never enable XML external entities or roll signature validation from scratch.
- **Attribute mapping:** trust attributes only *after* validation, map by trusted issuer/name/schema, and never grant admin rights from user-supplied text.
- **Transport:** use HTTPS, `Secure`/`HttpOnly` cookies, and trusted reverse proxies; SAML signatures do not replace cookie/session protection.

**SAML assertions can contain PII.** Never log raw Base64 `SAMLResponse`, decrypted assertions, sensitive `NameID`s, full attributes, private keys, or session cookies. When debugging is required, use controlled tracing and redact data.

## 12. SAML POST Callbacks, CSRF, and SameSite Cookies

A practical detail often overlooked: the IdP typically sends an **HTTP-POST from the IdP domain to the ACS on the SP domain**. That is a **cross-site** context in the browser. If the flow uses `HttpSession` to hold `AuthnRequest` before redirecting, and the session cookie is withheld on the POST callback due to `SameSite=Lax`/`Strict`, the SP may **fail to correlate the `AuthnRequest`** or lose session state.

Things to check:

1. Does the browser actually send the session cookie on the ACS POST? Check DevTools "Cookies blocked reason" and domain-level `SameSite`/`Secure` configuration.
2. If a cookie is required on cross-site POSTs, `SameSite=None; Secure` may fit in supporting browsers; HTTPS is mandatory and third-party cookie restrictions must be assessed. Do not apply it blindly to every cookie.
3. If storing state outside the session or using custom setups, ensure correlation and session fixation handling remain accurate.
4. **Never disable CSRF application-wide.** The ACS is a SAML protocol endpoint handled by the authentication filter; configure request matchers/CSRF handling properly for callbacks in Spring Security. Business POSTs using sessions still require CSRF protection.
5. Behind a proxy/ingress, verify the public ACS URL, cookie `Domain/Path`, path rewriting, and forwarded scheme. A callback arriving at a different URL than the one emitted in `AuthnRequest` may be rejected by the IdP or SP.

No single `SameSite` value fits every SAML setup. Verify against your **actual IdP, binding, and browsers**.

## 13. Multi-Node Environments, Signing Keys, and Metadata Rotation

In multi-instance SP deployments:

- **State correlation / sessions:** `AuthnRequest` may start on node A while the callback lands on node B. Use sticky sessions or an appropriate shared session/state store; never "fix" this by disabling `InResponseTo` verification.
- **Clock skew:** synchronize NTP and configure allowed clock skew per policy; drift causes `NotBefore`/`NotOnOrAfter` failures.
- **IdP certificate rotation:** monitor expiration, update trusted IdP verification credentials from a trusted metadata source, and handle overlapping key transition periods cleanly.
- **SP signing/decryption keys:** protect private keys, maintain a rotation strategy, and publish accurate public certificates in SP metadata for the IdP; never use test private keys in production.
- **Metadata caching:** if registrations are built from IdP metadata at startup, do not assume new certs load automatically at runtime. Establish a tested re-fetch/redeploy/repository-update and rollback process.
- **Multiple IdPs/tenants:** select registrations from a verified/controlled tenant context, never letting requests specify arbitrary issuers. Give each registration accurate entity IDs and keys.
- **Logout:** local Spring logout and SAML Single Logout (SLO) are distinct mechanisms; SLO requires supporting metadata, endpoints, and capabilities on both SP and IdP. Never promise "IdP logout" merely by clearing the Spring session.

## 14. Layer-by-Layer Integration Verification

### 14.1 Sequential Checklist

1. **Confirm config:** repository contains `registrationId=corp`; SP entity ID and ACS match IdP config; IdP issuer, SSO location, and signing cert match trusted metadata.
2. **Inspect SP metadata:** open the app's published metadata endpoint; verify `EntityDescriptor`, entity ID, ACS binding/location, and public certificates if present. Do not merely check for HTTP 200 OK.
3. **Initiate login:** verify GET `/saml2/authenticate/corp` redirects to the right IdP and produces an `AuthnRequest` with expected issuer, ACS, and request ID.
4. **Login at IdP:** using a test account, confirm `SAMLResponse` posts to the registered public HTTPS ACS URL; never paste raw responses into public tickets.
5. **Verify at SP:** `Saml2Authentication` is created only for valid responses; invalid issuer/audience/signature/timing must reject the request.
6. **Attributes:** inspect `NameID` format, exact attribute names (URI/OID), and single/multi values; test missing/empty attributes.
7. **Role mapping:** only allowlisted groups receive intended authorities; one IdP/tenant must never map into another tenant's admin.
8. **Session/ACS:** inspect cookie `SameSite`, `Path`, `Secure`, and HTTP POST callback behavior; test state correlation across multiple nodes.
9. **Logout and role revocation:** verify local session behavior, IdP SLO if needed, and permission updates when groups are revoked.

### 14.2 Distinguishing Unit Tests from Integration Tests

- **Unit tests:** build mapping policies and use synthetic `DefaultSaml2AuthenticatedPrincipal` instances to test group scenarios. Does not exercise SAML XML validation.
- **MockMvc tests:** simulate authentication to test controller authorization, though that does not replace testing SAML signatures, IdP trust, and ACS callbacks.
- **Integration tests:** require a test IdP or validly signed SAML fixtures alongside config verification; test issuer, audience, timestamps, request correlation, cookies, metadata, and negative failures. No need to hit a production IdP just to test group mapping.

## 15. Common Errors

| Symptom | Common cause | Diagnostic check |
| --- | --- | --- |
| `/saml2/authenticate/corp` does not start flow | Missing `saml2Login`, wrong registration ID, missing dependency, or filter chain mismatch. | Inspect RP repository bean, URL, security chain, and dependencies. |
| App fails startup fetching metadata | Unreachable metadata URI, invalid XML, missing issuer/endpoint, or TLS trust error. | Check trusted metadata source, redacted config logs, and connectivity. |
| IdP rejects SP with "unknown entity/audience" | Wrong SP entity ID or metadata registered at IdP. | Cross-check entity ID in SP metadata vs. IdP configuration. |
| IdP reports wrong ACS/Recipient | Wrong hostname/port/context-path in ACS URL, wrong proxy forwarded headers, or path rewrite. | Inspect public HTTPS URL emitted in `AuthnRequest` and IdP configuration. |
| `SAMLResponse` signature rejected | IdP signing cert rotated, wrong verification credential, or assertion/response unsigned per policy. | Check cert chain/trust config and signature requirements; never disable verification. |
| `InResponseTo` mismatch | Lost session/request state, callback routed to another node, IdP-initiated flow, or `SameSite` cookie dropped. | Inspect state repository, load balancer, browser cookies, and SP-initiated request IDs. |
| SAML assertion expired or "not yet valid" | Clock drift or mismatched `NotBefore/NotOnOrAfter`. | Synchronize clocks; inspect IdP issuance and policy clock skew. |
| Login succeeds yet email is missing | IdP does not emit `Name="email"` or uses a different OID/URI. | Inspect PII-redacted raw attribute names in test data; do not guess `FriendlyName`. |
| Login succeeds yet `ROLE_ADMIN` is missing | IdP group name differs, mapper not wired, wrong tenant/issuer, or policy denies admin. | Inspect attributes and authorities post-authentication; never assign admin automatically. |
| User from another IdP logs in as existing user | Account linking uses non-unique email or ignores issuer/tenant. | Fix account linking to use issuer + stable subject ID with validation. |
| Logins fail across the board after IdP cert change | Registry still holds old cert; metadata not refreshed/redeployed. | Perform overlapping cert rotation and check trusted metadata source. |
| User still logged in after SP logout | IdP SSO session persists; local logout is not SLO. | Design logout matching requirements; verify both SP and IdP. |

## 16. Practical Implementation Choices

**Single stable enterprise IdP:** configure Boot with `assertingparty.metadata-uri`, enable `saml2Login` and `saml2Metadata` (when needed), and supply SP metadata to the IdP. Add SP signing/decryption credentials only when the agreement requires them.

**Multiple IdPs for one app:** create multiple `RelyingPartyRegistration` entries with distinct `registrationId`s; lock flows to the right tenant/provider to avoid IdP confusion and account takeover. Be careful with the generated login page and exposing registration IDs.

**Apps using IdP groups for permissions:** read `Saml2AuthenticatedPrincipal` after SAML response verification, build allowlist mappings, attach authorities during the authentication conversion step, and test real `hasRole`/`hasAuthority` enforcement. Keep business permissions inside the app if the IdP is not the trusted source for them.

**High-availability systems:** prepare shared state/session stores, metadata refresh, IdP signing cert rotation, SP keys, NTP, proxy/cookie handling, and incident procedures before opening production login.

**Remember:** `RelyingPartyRegistration` defines **which IdP the SP trusts, which endpoints/certs apply, and where assertions arrive**; metadata is the **trust and interoperability contract**; `Saml2Authentication` exists only after validating `SAMLResponse`; only post-verification attributes may be mapped to application identity and `GrantedAuthority`. Secure SAML login requires getting trust, metadata, callbacks, account linking, and authorization right—not just a working redirect screen.

## References

- Spring Security — SAML2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Javadoc — RelyingPartyRegistration: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- OASIS SAML 2.0 Technical Overview and SAML Metadata specifications: https://www.oasis-open.org/committees/security/
