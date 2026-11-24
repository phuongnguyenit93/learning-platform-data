# Registering Service Provider Details at the IdP and Reconciling Bidirectional SAML 2.0 Configuration

> **Context:** Spring Security – federation. **Parent menu:** SAML2 Registration. This lesson guides you through registering a Spring Security application as a **Service Provider (SP)** at the **Identity Provider (IdP)**, exchanging metadata, matching fields one by one, validating the login flow, and safely operating changes.

## 1. Why Must Both Sides Be Registered?

In SAML 2.0 Web Browser SSO, the **SP/Relying Party** application does not verify user passwords itself; the SP trusts the **IdP/Asserting Party** under a pre-configured federation relationship. The IdP authenticates the user (potentially enforcing MFA), issues a `SAMLResponse` containing a signed assertion, and the browser POSTs the result to the SP's **Assertion Consumer Service (ACS)** endpoint. The SP must verify signature, issuer, audience, validity window, and conditions before creating a session.

Installing `spring-security-saml2-service-provider` only supplies **protocol capability** in the app; for login to succeed, you still need:

1. The IdP **knows and permits** an SP with a specific `entityID` and ACS URL.
2. The SP **knows and trusts** the IdP's issuer, SSO endpoint, and signing certificate/metadata.
3. Both sides agree on bindings, signing/encryption policies, NameID, attributes, and permissions.
4. Users are assigned access to the application at the IdP, and the SP application enforces their permissions.

**Key definitions:**

| Term | Meaning | Managed By Whom? |
|---|---|---|
| SP Entity ID | Logical identifier of the app; appears in `AuthnRequest/Issuer` and is used by the IdP as Audience/Identifier | SP and IdP must agree |
| ACS URL | Public SP URL receiving `SAMLResponse` via HTTP POST | Published by SP; stored by IdP as Reply URL |
| IdP Entity ID | Issuer identifier of the IdP, not necessarily a directly reachable URL | Published by IdP; trusted by SP |
| IdP SSO URL | Endpoint to which the browser is redirected with `AuthnRequest` | Published by IdP; used by SP |
| `registrationId` | Internal Spring Security key selecting `RelyingPartyRegistration` | SP application |
| SP metadata | XML describing the SP: Entity ID, ACS, bindings, and public cert when needed | Exported by SP, imported by IdP |
| IdP metadata | XML describing the IdP: issuer, SSO endpoint, signing cert, SLO if any | Exported by IdP, imported by SP |
| SP signing credential | SP private key signing AuthnRequest and public certificate for IdP verification when mandatory | SP keeps private; IdP receives public |
| IdP verification credential | IdP's public certificate for SP to verify Response/Assertion signatures | IdP keeps private; SP receives public |
| SP decryption credential | SP private key used to decrypt EncryptedAssertion; IdP receives SP public cert to encrypt | SP keeps private; IdP receives public |

`entityID` can be a URI or URN, and **does not have to be an openable HTTP path**. `registrationId` is not entityID. These values mean different things even when sharing the same partner name.

## 2. An End-to-End Configuration Example

Example for a Portal application running on Spring Security Servlet:

| Data Item | Illustrative Value |
|---|---|
| Spring registration name | `corporate` |
| SP Entity ID | `https://portal.example.org/saml2/service-provider-metadata/corporate` |
| SP ACS URL | `https://portal.example.org/login/saml2/sso/corporate` |
| SP metadata URL | `https://portal.example.org/saml2/metadata/corporate` |
| Login initiation URL | `https://portal.example.org/saml2/authenticate/corporate` |
| IdP Entity ID | `https://login.example.org/saml/company` |
| IdP SingleSignOnService URL | `https://login.example.org/saml/company/sso` |
| IdP metadata URL | `https://login.example.org/saml/company/metadata` |
| ACS Binding | HTTP-POST |
| AuthnRequest Binding | Typically HTTP-Redirect, per IdP metadata/policy |

The `example.org` domains here are illustrative. Endpoints of a real IdP (Microsoft Entra ID, AD FS, Okta, Keycloak, Shibboleth...) can have completely different structures: **never guess the IdP SSO URL from the domain name**. Always retrieve the exact value published by the IdP.

With documented Spring Security defaults, **SP Entity ID** is typically `{baseUrl}/saml2/service-provider-metadata/{registrationId}`; **ACS URL** is `{baseUrl}/login/saml2/sso/{registrationId}`. Depending on version and custom config, these paths can be changed. `/saml2/metadata/corporate` is where **the metadata document is read**, not the ACS and not the default entityID.

## 3. Trust Setup Flow Before Login

~~~text
SP Team / Spring Security                   IdP Admin
       |                                       |
       | 1. Finalize SP entityID, ACS, binding |
       | 2. Generate SP metadata / public cert |
       +------------- SP metadata ------------>|
       |                                       | 3. Create SAML app / relying party
       |                                       | 4. Save SP entityID, ACS, policy
       |<------------ IdP metadata ------------+
       | 5. Import/read IdP issuer, SSO URL,   |
       |    trusted signing certificate        |
       |                                       |
       +<----- Bidirectional reconciliation ---->+
       |         6. Positive/negative tests    |
~~~

**Two symmetrical tasks** are required:

- **Register SP at IdP:** the IdP stores the exact declared SP entityID and ACS; finalize response signature, request signature, encryption, NameID, and user assignment.
- **Register IdP in Spring:** the SP stores the exact IdP entityID, SSO URL/binding, and public verification keys from a trusted source; define `registrationId` along with SP entityID, ACS, and private keys if needed.

Having only an IdP metadata URL **does not mean** the IdP has created the application/trust entry for the SP. Conversely, only creating a SAML app at the IdP **is not enough** for the SP to verify `SAMLResponse`.

### SAML Login After Both Sides Are Registered

~~~text
Browser                   SP                             IdP
   | GET /private          |                              |
   +---------------------->|                              |
   |<---- Redirect /saml2/authenticate/corporate          |
   +------------------- AuthnRequest -------------------->|
   |                                      Login / MFA      |
   |<------------------- HTML form SAMLResponse ----------+
   +-- POST /login/saml2/sso/corporate ------------------> SP
                           | Verify signature + issuer,
                           | audience, recipient, time,
                           | InResponseTo, replay, roles
   |<----------------------+ Create session / grant access
~~~

The browser only relays messages and must never be trusted to supply any identity simply by modifying forms or payloads.

## 4. Fields the SP Must Provide to the IdP

| Field | Possible Names on IdP Console | Reconciliation Rule |
|---|---|---|
| **SP Entity ID** | Identifier, Audience URI, SP Entity ID, Relying Party Identifier | Must match `RelyingPartyRegistration.entityId` character-for-character |
| **ACS URL** | Reply URL, Recipient URL, Consumer URL, SAML ACS | Must match the public `assertionConsumerServiceLocation` |
| **ACS Binding** | HTTP-POST / Response Binding | Usually HTTP-POST; must match SP and IdP capabilities |
| **SP metadata XML/URL** | Upload Metadata, Import SP Metadata | Contains EntityDescriptor + SPSSODescriptor + ACS + certs when used |
| **SP signing certificate** | Request Signature Certificate | Public cert matching SP private key signing AuthnRequest when mandated by IdP |
| **SP encryption certificate** | Assertion Encryption Certificate | Public cert matching SP private key that will decrypt Assertion |
| **SP SLO URL** | Single Logout URL | Present if IdP and SP implement SAML Single Logout |
| **NameID Format** | Name Identifier Format | ID format used for account mapping: persistent, emailAddress, unspecified... |
| **Attribute contract** | Claims, Attribute statements | Attribute names, value types, multi-value, agreed groups/permissions |
| **Environment** | Application/Tenant | Must match dev/staging/prod; never mix metadata or certs |

Note that **SP entityID** and **ACS URL** are not interchangeable. Entity ID is a logical identifier; ACS is the actual HTTP address receiving POSTs. Wrong scheme, hostname, path, trailing slash, or context path can cause audience/destination/recipient mismatches.

### Sample SP Metadata XML

Simplified template illustrating key fields only, not real deployable metadata:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://portal.example.org/saml2/service-provider-metadata/corporate">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      AuthnRequestsSigned="false"
      WantAssertionsSigned="false">
    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified
    </md:NameIDFormat>
    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/login/saml2/sso/corporate"
        index="0"
        isDefault="true"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

In metadata generated from configs with signing/encryption, you may see `md:KeyDescriptor use="signing"` and `md:KeyDescriptor use="encryption"` holding `ds:KeyInfo` with public certificates; there may also be multiple ACSs, SLO services, and NameID formats. Import metadata only from the **target environment's app build**; never substitute a sample file like above for real metadata.

**Important:** `WantAssertionsSigned="false"` in the example does not mean the SP will trust unsigned assertions. Signature validation is still enforced by the SAML profile, policy, and security provider. During deployment, agree on whether Response, Assertion, or both are signed, and verify the exact issuer.

## 5. Fields the IdP Must Provide to Spring Security

| IdP Field | Configuration Area / Purpose in Spring |
|---|---|
| **IdP Entity ID/Issuer** | `assertingparty.entity-id`; matched against Issuer in response/assertion |
| **IdP SSO URL + Binding** | `assertingparty.singlesignon.url` and binding, or extracted from metadata |
| **IdP signing certificate(s)** | `assertingparty.verification.credentials` / trusted metadata; verifies Response/Assertion |
| **IdP metadata URL/XML** | `assertingparty.metadata-uri`; can replace manual declaration |
| **AuthnRequest signing requirement** | `WantAuthnRequestsSigned` / policy; determines if SP must sign and provide cert |
| **Response/Assertion signing policy** | Format and signature that the IdP will issue |
| **Assertion encryption policy** | Algorithms, SP encryption cert, SP private key for decryption |
| **NameID format + attributes** | Mapping principal, groups, email, department, tenant |
| **Single Logout service** | If SLO is enabled: endpoint/binding and signing requirement |
| **Session/MFA/conditions** | Policies enforced by IdP; SP still authorizes separately |

IdP metadata typically contains `md:EntityDescriptor.entityID` and `md:IDPSSODescriptor` with `SingleSignOnService` and `KeyDescriptor`. Simplified sample:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://login.example.org/saml/company">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="false">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.org/saml/company/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

This sample **lacks a certificate and is insufficient** to verify responses in real deployments. The public IdP signing cert must come from a trusted source, via real metadata and/or trust verified with the IdP administrator.

### Metadata and Trust Are Not the Same Concept

An XML file with a digital signature or containing an X.509 certificate **is not automatically trustworthy**: the SP must establish metadata provenance, trust anchors, IdP issuer, and metadata signing policies. Spring Security documentation provides ways to load metadata, including repositories supporting verification and refresh; do not assume every URL-loading method automatically verifies metadata signatures. If stored statically, plan certificate updates; if using dynamic metadata URLs, protect HTTPS, availability, timeout/cache, and source trust.

## 6. Mandatory Reconciliation Table Before Acceptance

| Protocol Meaning | SP/Spring Value | IdP Value | Correct Outcome |
|---|---|---|---|
| SP identifier | `entityId` | Identifier/Audience/Relying Party ID | **Exact match** |
| ACS POST target | `assertionConsumerServiceLocation` | ACS/Reply URL | **Matches external URL** |
| Response Binding | SP HTTP-POST endpoint | IdP response binding | Compatible |
| IdP issuer | `assertingparty.entity-id` | IdP `EntityDescriptor.entityID` | **Exact match** |
| Where SP sends requests | SingleSignOnService URL | IdP SSO endpoint | Exact URL + binding |
| Response/Assertion signature | IdP verification credentials | IdP signing cert | Key/cert matches issuer |
| Sign AuthnRequest if needed | SP private signing key | SP public signing cert at IdP | Signing and verification succeed |
| Encrypt Assertion if needed | SP private decryption key | SP public encryption cert at IdP | Matching encrypt/decrypt pair |
| NameID | Principal mapping | IdP NameID/Format/Source | Consistent identifier |
| Groups/permissions | Attribute mapping → authority | SAML group/role claims | Exact names and semantics |
| Logout | SP SLO endpoint + key | IdP SLO service/binding | Both support it |
| Environment | SP domain, registration, cert | IdP tenant/application/cert | Dev and prod separated |

**Practical check:** place side by side **live SP metadata from the deployed app**, **saved IdP config**, and **the IdP metadata that the SP reads**. Draft YAML or Word docs do not prove runtime configuration is right. When one side changes, confirm caches/rollouts picked up the new value before retesting.

### Four Frequently Confused Names

- `corporate` is Spring's internal `registrationId`.
- `https://portal.example.org/saml2/service-provider-metadata/corporate` is the **SP entityID** and usually the Audience URI at the IdP.
- `https://login.example.org/saml/company` is the **IdP entityID**, which must match the incoming Issuer.
- `https://portal.example.org/login/saml2/sso/corporate` is the **ACS**, where the IdP POSTs `SAMLResponse`. Not the metadata endpoint.

## 7. Step-by-Step Procedure to Register the SP at the IdP

### Step 1: Prepare a Profile for Each Environment

Confirm application name, environment, IdP tenant, SP and IdP owners, Java/Spring Boot/Spring Security versions, external hostname, URL and proxy path, MFA requirements, SLO, and key lifecycle policies. Prefer separate IdP applications for dev/staging/production; never use production URLs/certs in testing.

### Step 2: Configure the SP Application Before Exporting Metadata

Create a registration named `corporate` and lock down SP entityID, HTTPS ACS URL, and signing/decryption credentials if needed. Behind a reverse proxy, know the exact URL browsers actually visit. Spring Boot can build metadata from request `baseUrl`, so a misconfigured proxy can emit `http://localhost:8080` instead of `https://portal.example.org`.

### Step 3: Export SP Metadata

Enable `saml2Metadata()` on the Servlet application. Per Spring Security documentation, endpoints can be:

- `/saml2/metadata`: metadata for the set of registrations if supported by the repository.
- `/saml2/metadata/{registrationId}`: metadata for one registration.
- `/saml2/service-provider-metadata/{registrationId}`: alternative metadata endpoint.

For `corporate`, fetch `https://portal.example.org/saml2/metadata/corporate` and verify the XML has the right Entity ID, ACS URL, binding, public cert (if used), SLO, and NameIDFormat. **The metadata export address does not necessarily equal the Entity ID**.

### Step 4: Import into the IdP or Enter Manually

In the IdP console, create a **SAML 2.0** application. If metadata upload is supported, import the SP metadata for the exact environment. If entering manually:

~~~text
SAML application: Portal Corporate
SP Entity ID / Audience:
  https://portal.example.org/saml2/service-provider-metadata/corporate
ACS / Reply URL:
  https://portal.example.org/login/saml2/sso/corporate
ACS Binding:
  urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST
SP Request Signing:
  Per agreed requirement, with SP public signing cert if signing is mandated
Assertion Encryption:
  Enable when needed and IdP has received SP public encryption cert
NameID and Attributes:
  Select agreed format + identifier/group sources
~~~

Field names vary by product (Entra ID, AD FS, Okta, Keycloak, Shibboleth...) but must match in **meaning**. After importing/Saving, reopen the configuration to confirm the IdP saved the exact URL/cert; some UIs auto-transform values or list multiple "default URLs".

### Step 5: Select Message Protections

- **IdP Response/Assertion signature**: IdP signs with its private key; SP trusts the matching IdP public cert.
- **SP AuthnRequest signature**: SP signs with its private key; IdP verifies with SP's public signing cert if required by policy.
- **EncryptedAssertion**: IdP uses SP's public encryption cert; SP keeps the corresponding private key to decrypt.
- **SAML Single Logout**: configured separately if supported by both; has dedicated endpoints and signing policies.

Never use a public certificate from an untrusted payload as a verification trust anchor. Never send the SP private key to the IdP. Never relax signing policies or skip Audience/Recipient checks just to make SSO pass.

### Step 6: Assign Application Access at the IdP

Assign users/groups allowed to log in, configure MFA/conditional access, and configure NameID/attribute statements. Even with valid protocol registration, an unassigned user cannot log in. Permissions inside the SP are still decided by the application; IdP login access **does not imply** the user holds `ROLE_ADMIN`.

### Step 7: Import IdP Metadata into Spring, Reconcile, and Run Tests

Extract IdP entityID, SSO URL/binding, signing cert, and optional SLO from trusted IdP metadata. Configure Spring accordingly, review the table in section 6, and run SP-initiated tests first. Then test negative cases, permission mapping, proxies/cookies, different users/groups, and IdP-initiated flows if deliberately supported.

## 8. Spring Boot / Spring Security SAML2 SP Example

### 8.1. Maven Dependencies in a Servlet Project

The dependencies below belong in the `<dependencies>` section of a Spring Boot project using a BOM/dependency management; **not a complete pom.xml file**:

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

The SAML module uses OpenSAML. Depending on the Spring Security/Boot/OpenSAML branch, adding the Shibboleth repository as instructed by official docs may be necessary; never mix Spring Security and OpenSAML versions arbitrarily.

### 8.2. Configuring Spring Boot with IdP Metadata

File `src/main/resources/application.yml` (example domains; requires real IdP metadata and registered app):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://portal.example.org/login/saml2/sso/corporate"
            assertingparty:
              metadata-uri: "https://login.example.org/saml/company/metadata"
~~~

- `registration.corporate` is the local key.
- `entity-id` is the **SP entity ID**, which must match Identifier/Audience URI at the IdP.
- `acs.location` must match Reply URL/ACS at the IdP and be the URL browsers actually reach.
- `assertingparty.metadata-uri` is the **IdP metadata**, not SP metadata.

This syntax follows the Spring Boot SAML relying party structure. When deploying, verify property names and APIs of the **actual running Spring Boot version**. You can omit explicit SP entityID/ACS to use defaults when the public baseURL is accurate; then export metadata and inspect the output.

If the IdP lacks a metadata URL, you can configure the IdP issuer, URL, and verification cert manually:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              entity-id: "https://login.example.org/saml/company"
              singlesignon:
                url: "https://login.example.org/saml/company/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-signing.crt"
~~~

This is an **alternative to the IdP metadata URI branch**, not two blocks to paste concurrently under `registration.corporate`. `sign-request: false` is appropriate only when the IdP **permits unsigned AuthnRequests**. If the IdP requires signing, configure SP signing credentials and confirm the IdP trusts the SP public cert. With manual configuration, add SP entityID/ACS and binding fields if not using defaults.

### 8.3. Java 17+ Login Configuration and SP Metadata Export

File `src/main/java/com/example/portal/SamlPortalApplication.java`:

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlPortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlPortalApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SP ready";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

This Java 17+ code is **for a Spring Boot Servlet project**, and will not compile standalone with `javac` because it requires the Spring classpath and a working IdP/registration. In a Maven project with Maven Wrapper prepared:

~~~bash
./mvnw spring-boot:run
~~~

Once the app starts cleanly, `GET /` returns the text `SP ready`. Accessing `GET /me` requires SAML authentication; after success, the result is the actual principal name decided by the IdP/mapping, with no fixed stdout.

To fetch metadata on the deployed hostname:

~~~bash
curl -fsS "https://portal.example.org/saml2/metadata/corporate" -o sp-metadata.xml
~~~

Then inspect the XML: `EntityDescriptor.entityID`, `SPSSODescriptor.AssertionConsumerService.Location`, bindings, public certs, and SLO if used. The command succeeds only when hostname, server, and registration are truly ready; there is no fixed output to simulate.

### 8.4. When AuthnRequest Signing or Assertion Encryption Is Required

Configuration branches related to **SP signing** and **SP decryption** (merge with the configuration above when needed):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/secrets/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/sp-decryption.key"
                  certificate-location: "file:/run/secrets/sp-decryption.crt"
            assertingparty:
              metadata-uri: "https://login.example.org/saml/company/metadata"
~~~

The SP signing public/private pair and SP encryption public/private pair can be separate; each pair must serve its exact purpose. Real configurations may hold multiple credentials during rotation. **Never** upload private keys to the IdP console or commit them to source control. For signing policy, check IdP metadata `WantAuthnRequestsSigned`, bindings, and algorithms. If the IdP encrypts, the SP must hold the private decryption key **matching the SP encryption cert used by the IdP**.

### 8.5. Default URLs and Custom URLs

Per modern Spring Security Servlet documentation:

| Function | Common Default |
|---|---|
| Start SP-initiated login | `/saml2/authenticate/{registrationId}` |
| Receive SAMLResponse (ACS) | `/login/saml2/sso/{registrationId}`; other ACS paths supported per config |
| Serve SP metadata | `/saml2/metadata/{registrationId}` after enabling `saml2Metadata` |
| SP Entity ID | `{baseUrl}/saml2/service-provider-metadata/{registrationId}` |

You can customize `loginProcessingUrl` or builder `assertionConsumerServiceLocation`, but **changing the filter's processing endpoint must stay synchronized with metadata and the IdP**. Never change the path at the IdP first assuming Spring will adjust automatically.

## 9. Reverse Proxies, Absolute URLs, and Session Callbacks

A config that works on localhost can fail completely in production because external addresses differ:

~~~text
Internal Spring service:
  http://portal-service:8080/login/saml2/sso/corporate

Public browser/IdP URL:
  https://portal.example.org/login/saml2/sso/corporate

Correct configuration:
  SP metadata + IdP ACS + Recipient/Destination all use the public HTTPS URL.
~~~

Check these factors:

- **HTTPS scheme:** TLS terminates at the proxy, yet metadata must reflect the exact external URL.
- **Host/port:** public FQDN differs from internal container names and ports.
- **Context path:** if ingress adds/strips `/portal`, the ACS must reflect that accurately.
- **Trusted forwarded headers:** the app trusts `Forwarded`/`X-Forwarded-*` set only by trusted proxies; the proxy strips forged client headers before forwarding requests.
- **Cookies/sessions:** the IdP typically POSTs cross-site; check `Secure`, `SameSite`, domain, and AuthnRequest/session storage across a cluster.
- **Multiple instances:** if callbacks land on a different instance, session/request repositories must be shared or load balancing designed accordingly.

**Never "fix" by disabling Destination, Recipient, or Audience validation or allowing arbitrary redirect URLs.** Fix SP base URL/ACS, IdP Reply URL, and proxy routing so they match.

## 10. Signatures, Encryption, and SAML Condition Checks

When the IdP sends `SAMLResponse` to the ACS, the SP must verify multiple layers:

1. **IdP trusted issuer:** Response/Assertion genuinely originates from the registered IdP.
2. **XML signature:** Response or Assertion signature matches profile, certificate, and policy; never trust certs self-supplied inside an unverified payload.
3. **Audience:** Assertion targets this **SP Entity ID**.
4. **Destination / Recipient:** callback matches the registered **ACS**.
5. **InResponseTo:** for SP-initiated flows, links to the pending AuthnRequest and session context.
6. **Time window:** `NotBefore`, `NotOnOrAfter`, SubjectConfirmation, and bounded clock skew.
7. **Replay:** reject reuse of responses/assertions violating policy.
8. **Account and authorities:** map principal/claims post-authentication and apply application authorization.

**Signature ≠ encryption.** A Response or Assertion can be signed to protect origin/integrity; `EncryptedAssertion` protects confidentiality for the SP holding the private key. Successful decryption **does not prove** the assertion was issued by a trusted IdP. If an assertion is signed and then encrypted, the provider must decrypt and verify the inner signature in the proper order.

### Certificate Lifecycle

- IdP signing key rotation: SP must receive the new trusted cert **before** the IdP starts signing with the new key; old/new certs can overlap.
- SP signing key rotation: update the public cert at the IdP before the SP signs requests with the new private key.
- SP encryption key rotation: the IdP encrypts with a public cert whose corresponding private key the SP still holds; if out of sync, decryption fails.
- Record SHA-256 fingerprints, validity windows, owners, and metadata/cert update paths.
- Never log private keys, raw SAMLResponses containing PII, or cookies; never disable signature checks on errors.

## 11. NameID, Attribute Mapping, and Authorization

During IdP registration, confirm the **NameID format** and how user identifiers are sourced: persistent ID, emailAddress, unspecified, UPN, or custom subject. Never assume email is immutable: email addresses can change or be reassigned; pick a mapping key binding issuer + contract-stable subject.

SAML attributes like `email`, `department`, `groups`, or `roles` do not automatically turn into Spring Security permissions. You must:

- Verify assertion/issuer/conditions before reading attributes.
- Define attribute names (URI/short name) and multi-value mapping.
- Map groups from the **right tenant/issuer** to bounded application roles.
- Separate IdP entitlement "allowed to log into app" from SP permissions "allowed to view/edit resource".
- Handle disabled users, group changes, and account lifecycles.

Example of an **attribute fragment** (not a validly signed assertion):

~~~xml
<saml:Attribute
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Name="groups">
  <saml:AttributeValue>portal-viewers</saml:AttributeValue>
</saml:Attribute>
~~~

Only after SAML authentication completes should the app consider mapping `portal-viewers` to a policy-approved authority. Never assign admin privileges simply because a role string appeared in an unverified form.

## 12. SP-Initiated, IdP-Initiated, and SLO

**SP-initiated**: SP sends AuthnRequest and saves state; IdP returns response with `InResponseTo`. This is usually the right default for apps with protected routes. Check `RelayState` to prevent open redirects and session/login CSRF.

**IdP-initiated**: user picks the app from the IdP portal and receives a response without a matching AuthnRequest in the SP session. Support only if IdP/SP have an explicit policy; login CSRF/replay and session mapping risks must be evaluated. Never drop `InResponseTo` validation across all flows to "fix" SP-initiated errors.

**Single Logout (SLO)**: separate feature requiring IdP `SingleLogoutService` support, SP `saml2Logout` config, matching endpoints/bindings, and signing LogoutRequest/LogoutResponse per policy. Logging out locally from one app does not automatically clear the IdP session or all other apps.

## 13. Standalone Java 17: Checking Key Configuration Matches

The program below simulates **config string matching** only; it neither parses XML metadata nor verifies SAML signatures. This is **standalone, compilable/runnable** Java 17 code.

File `CompareSamlRegistration.java`:

~~~java
import java.util.Objects;

public class CompareSamlRegistration {
    static void check(String label, String spValue, String idpValue) {
        String result = Objects.equals(spValue, idpValue)
                ? "MATCH" : "MISMATCH";
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        check(
            "SP Entity ID",
            "https://portal.example.org/saml2/service-provider-metadata/corporate",
            "https://portal.example.org/saml2/service-provider-metadata/corporate"
        );
        check(
            "ACS URL",
            "https://portal.example.org/login/saml2/sso/corporate",
            "http://portal.example.org/login/saml2/sso/corporate"
        );
        check(
            "IdP Entity ID",
            "https://login.example.org/saml/company",
            "https://login.example.org/saml/company"
        );
    }
}
~~~

Commands:

~~~bash
javac CompareSamlRegistration.java
java CompareSamlRegistration
~~~

Exact stdout:

~~~text
SP Entity ID: MATCH
ACS URL: MISMATCH
IdP Entity ID: MATCH
~~~

ACS fails because the IdP stores `http://` while the SP emits `https://`. Fix the wrong side and rerun; **never switch to fuzzy matching** in SAML checks. In production, prefer comparing live runtime metadata against the IdP console; this program is an exercise in exact value checking, not a SAML validator.

## 14. Post-Registration Testing Plan

### 14.1. Positive Tests

1. Open the live SP metadata URL; confirm Entity ID, ACS, and public signing/encryption certs (if used).
2. Visit `/saml2/authenticate/corporate`; verify redirect to the right IdP SSO endpoint and AuthnRequest has the exact issuer/ACS.
3. Log in with a user assigned to the app at the IdP, completing MFA if required.
4. Confirm the IdP POSTs SAMLResponse to the stored ACS with accurate `Destination`/`Recipient`.
5. SP passes signature, issuer, audience, timing, and request state checks, then creates Authentication.
6. Verify principal NameID/attributes/roles and permitted resources.
7. Test a lower-privilege user, a user unassigned in the IdP app, and MFA policies.
8. Test local logout; test SLO separately if supported by both sides.

### 14.2. Intentional Failure Tests

| Scenario | Expectation |
|---|---|
| SP entityID differs from Assertion Audience | SP rejects |
| ACS scheme/host/path changed or wrong Recipient | IdP/SP rejects |
| IdP `Issuer` from wrong tenant | SP rejects |
| Untrusted IdP signing certificate | SP rejects |
| Assertion modified after signing | SP rejects |
| Expired response/assertion or `NotBefore` in the future | SP rejects |
| `InResponseTo` not matching a pending request | SP rejects in SP-initiated flow |
| SAMLResponse/Assertion replayed against policy | SP rejects |
| IdP mandates signed AuthnRequest yet SP sends unsigned | IdP rejects |
| EncryptedAssertion uses cert not matching SP private key | SP cannot decrypt |
| User not assigned to app at IdP | IdP refuses to issue valid session |
| User logged in without required authority | SP denies restricted resource |
| IdP metadata/certificate rotated while SP out of sync | Fails safely and alerts |

When debugging, use a test IdP and browser/SAML tracing in an authorized environment. Inspect non-sensitive fields such as Issuer, Destination, Audience, InResponseTo, timestamps, and key fingerprints; avoid pushing raw SAMLResponses containing PII/sessions to public logs.

## 15. Troubleshooting Common Errors

| Symptom | Likely Cause | Check / Fix |
|---|---|---|
| Invalid Audience / Entity ID | IdP Identifier differs from SP entityID | Compare SP metadata with app Identifier at IdP |
| Reply URL / ACS mismatch | IdP has not saved exact public ACS | Check scheme/host/port/path/context path |
| Invalid Destination / Recipient | Proxy/ingress alters URL | Update trusted forwarding or explicit ACS |
| Invalid Issuer | Pointing to wrong IdP tenant/metadata | Compare IdP metadata entityID with Spring asserting party |
| Signature validation failed | Wrong IdP cert, rotated key, or tampered payload signature | Update trusted signing cert/metadata; never disable verify |
| Unsigned AuthnRequest rejected | IdP requires SP signing | Add SP signing credential and public cert at IdP |
| EncryptedAssertion decryption failure | Wrong SP key or IdP encrypted with another cert | Check encryption cert/private key pair and algorithm |
| 404 at ACS | Wrong URL, POST binding, filter chain, or proxy rewrite | Check Servlet endpoint and ingress routing |
| Invalid InResponseTo / lost session | Cookies, SameSite, session store, or multi-node | Check AuthnRequest repository and cookies/sessions |
| NotBefore/NotOnOrAfter failed | Clock/NTP drift or expired response | Sync clocks, bound clock skew |
| Login succeeds yet 403 | IdP attribute/authority mapping mismatch | Check SP group/role policy |
| User cannot see app on IdP portal | User/group unassigned or policy blocked | Check assignment/MFA |
| Metadata endpoint 404 | `saml2Metadata` not enabled or wrong registration | Enable metadata DSL; verify URL and environment |
| SSO loop | Session cookie, ACS handling, or reverse proxy error | Check auth/session logs and cookie settings |
| SLO fails while SSO login passes | Logout flow/cert/endpoint need dedicated config | Check IdP SLO support and LogoutRequest/Response signing |

Time-saving troubleshooting order: **environment/tenant → SP entityID + ACS → IdP issuer + SSO URL → keys/certs → browser POST/session → SAML conditions → role mapping**. Never edit authorization when the actual fault lies in issuer or ACS.

## 16. Acceptance Record and Production Operations

A post-acceptance configuration record should document:

- SP name, IdP application/tenant, environment, and owners on each side.
- **SP entityID**, ACS URL/binding from live metadata; **IdP issuer**, SSO URL/binding from IdP metadata.
- SHA-256 fingerprints and validity dates of IdP signing certs; SP signing/encryption certs if used.
- Policies for Response/Assertion signatures, AuthnRequest signing, Assertion encryption, NameID, and attributes.
- Positive/negative integration tests; MFA/user assignment status, authority mappings, and optional SLO.
- Metadata update procedures, **certificate rotation** schedule, expiry alerts, rollback, and incident contacts.

When changing **Entity ID** or **ACS URL**, synchronize both IdP and SP; execute planned changes and re-verify requests/responses. When rotating certs, prepare an **overlap** phase if supported by software/partners, test before activating new keys, and never remove old keys while IdP/SP still depend on them. Keep dev/staging/prod isolated to reduce risk.

Go-live checklist:

1. Runtime SP metadata matches IdP stored Identifier, ACS, and binding.
2. SP trusts only verified IdP issuer and verification keys; assertion expiration/audience/recipient checks remain intact.
3. HTTPS, DNS, trusted reverse proxy, cookies/sessions, and multiple replicas work properly.
4. Signing/encryption certs match their keys; private keys live in a secret store with restricted file permissions.
5. User/group assignment, MFA, and SP permissions tested across valid and invalid scenarios.
6. Monitoring for SSO failures, metadata fetches, cert expiry, and safe rollback plans in place.
7. Every new change has an owner and can be reconciled against three sources: **live SP metadata, IdP stored settings, and IdP metadata read by the SP**.

## 17. Review Questions

1. **Does importing IdP metadata into Spring automatically register the SP in the IdP?** No. The IdP must still store the SP entityID/ACS and assign users to the app.
2. **Is SP entityID the same as the ACS URL?** No. EntityID is the identity/audience, while ACS is the endpoint receiving SAMLResponse.
3. **Must `registrationId` match the IdP issuer?** No; it is Spring's internal key selecting RelyingPartyRegistration.
4. **Who holds the private key for Assertion encryption?** The SP holds the private decryption key; the IdP receives the SP public encryption cert.
5. **Why might SSO fail after adding a reverse proxy?** Metadata/ACS may emit internal HTTP URLs instead of public HTTPS URLs; session cookies may also misbehave.
6. **Is successful SSO login enough to grant admin privileges?** No; authority mapping and authorization are separate SP responsibilities.
7. **Why not disable signature verification when a cert mismatches?** Doing so allows the SP to accept forged assertions. Fix trust/certs for the right issuer instead.
8. **How should IdP signing certificate rotation be handled?** The SP must load the new trusted public cert during rollout before the IdP starts signing with the new key.

## 18. Official References

- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML2 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – Authenticating Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Single Logout: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Boot – SAML2 Relying Party: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- OASIS – SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS – SAML 2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf

**Remember:** SAML configuration is accurate when **SP metadata emitted by the app**, **SP settings stored at the IdP**, and **IdP metadata/issuer/keys trusted by Spring Security** align. Login is secure only after signatures, audience, callbacks, request correlation, validity windows, and authorization are all verified properly.
