# RelyingPartyRegistration and the Configuration Model for an SP–IdP Relationship

In Spring Security SAML 2.0, **`RelyingPartyRegistration` is the configuration describing a specific trust relationship between a Service Provider (SP) and an Identity Provider (IdP)**. Here, the Spring application acts as the **SP**, also called the *Relying Party (RP)*; the enterprise login system acts as the **IdP**, also called the *Asserting Party (AP)*.

A proper SP–IdP relationship must answer: who is the SP, who is the IdP, where to send login requests, where to receive the SAML Response, which certificate to use to verify signatures, when messages must be signed or decrypted, and which principal is allowed to access resources after login. Declaring only an IdP URL or merely adding a SAML dependency does not establish a secure trust relationship.

**Learning objectives:**

- Understand `RelyingPartyRegistration` as a **two-sided** configuration model, not a "user account".
- Distinguish Spring's `registrationId` from the SP and IdP `entityId` values.
- Create an SP–IdP configuration using Spring Boot properties or JavaConfig; understand where registrations are stored in `RelyingPartyRegistrationRepository`.
- Trace the flow `AuthnRequest` → IdP → `SAMLResponse` → Assertion Consumer Service (ACS) → `Authentication`.
- Verify metadata, certificates, signatures, audience/recipient, tenant, reverse proxy, and common mistakes.
- Know how to scale from one relationship to multiple IdPs without mixing trust boundaries.

## 1. Concept and Scope of a Registration

| Term | Name in Spring Security | Role |
| --- | --- | --- |
| SP / RP | Relying Party | Our application that receives SAML results issued by the IdP |
| IdP / AP | Asserting Party | Authenticates users and issues SAML Responses/Assertions |
| SP entity ID | `RelyingPartyRegistration.entityId` | Stable SAML identifier published by the SP, typically a URI |
| IdP entity ID | `AssertingPartyMetadata.entityId` | Issuer identifier of the IdP, used to verify the issuing source |
| Registration ID | `registrationId` | Internal Spring key used to look up the relationship configuration |
| ACS | `assertionConsumerServiceLocation` | SP URL that receives the SAML Response from the browser |
| IdP SSO URL | `singleSignOnServiceLocation` | IdP endpoint that receives `AuthnRequest` |
| IdP verification credential | `verificationX509Credentials` | Public certificate/trusted key for the SP to verify the IdP's signature |
| SP signing credential | `signingX509Credentials` | Private key and certificate the SP uses to sign `AuthnRequest` if needed |
| SP decryption credential | `decryptionX509Credentials` | SP private key used to decrypt assertions encrypted by the IdP |
| Repository | `RelyingPartyRegistrationRepository` | Looks up approved configuration by `registrationId` |

**A `RelyingPartyRegistration` describes an SP + IdP configuration pair.** It does not store employee lists, passwords, internal roles, or login sessions. Those belong to the authentication system, account store, and another authorization layer.

For example, an SP named Portal A trusts company B's IdP:

- `registrationId = partner-b` chosen by the Portal A development team.
- SP Entity ID: `https://portal.example.com/saml2/service-provider-metadata/partner-b`.
- SP ACS: `https://portal.example.com/login/saml2/sso/partner-b`.
- IdP Entity ID: `https://login.partner-b.example/saml2/idp`.
- IdP SSO URL: `https://login.partner-b.example/saml2/sso`.
- IdP certificate: X.509 certificate verified and trusted by A specifically for B.

`registrationId` is only an **internal** lookup key. It can be `partner-b` or `corp`, but **it does not replace the SAML Entity ID** of either party. The SP and IdP must also explicitly agree on URIs, bindings, certificates, and signing policies.

## 2. Why Not Just Declare an IdP URL?

SAML Web Browser SSO exchanges signed assertions that are time-bounded and recipient-restricted. Consider taking a validly signed SAML Response from IdP B meant for SP C and submitting it to Portal A: if Portal A only verifies the signature while ignoring audience or recipient, it risks accepting a message issued **for a different system**.

Therefore, the configuration must bind the relationship pair:

~~~text
SPRING REGISTRATION: partner-b
    SP / Relying Party
       entityId = https://portal.example.com/saml2/service-provider-metadata/partner-b
       ACS      = https://portal.example.com/login/saml2/sso/partner-b
       signing/decryption credentials = SP-owned, if needed
    IdP / Asserting Party
       entityId = https://login.partner-b.example/saml2/idp
       SSO URL  = https://login.partner-b.example/saml2/sso
       verification certificate = IdP-owned, verified
    POLICY
       accept the right IdP, right SP, right request, and right time
       map NameID/attributes per Portal A policy
       enforce separate application / tenant permissions
~~~

The URIs containing `.example` here are learning placeholders and do not exist for actual login.

## 3. An End-to-End SP-Initiated SSO Flow

Suppose a user visits a page requiring login on Portal A:

~~~mermaid
sequenceDiagram
    participant U as User / Browser
    participant SP as Portal A - Spring Security SP
    participant REP as RelyingPartyRegistrationRepository
    participant IDP as IdP B
    U->>SP: GET /private
    SP->>REP: Look up registration partner-b
    REP-->>SP: SP + IdP metadata and credentials
    SP-->>U: Redirect to IdP with AuthnRequest
    U->>IDP: Send SAMLRequest (HTTP-Redirect binding)
    IDP->>IDP: Authenticate user, verify SP
    IDP-->>U: Form returning SAMLResponse (HTTP-POST binding)
    U->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Look up registration, validate Response/Assertion
    SP->>SP: Create Authentication, evaluate permissions
    SP-->>U: Session / authorized page
~~~

Technical walkthrough:

1. `Saml2WebSsoAuthenticationRequestFilter` creates an `AuthnRequest` based on the selected `RelyingPartyRegistration`.
2. The SP sends the request only to the configured IdP SSO endpoint and satisfies request signing requirements (if the IdP requires them).
3. The IdP authenticates the account and creates a Response/Assertion with issuer, subject, audience, recipient, time conditions, and signature.
4. The browser forwards the Response to the SP's ACS. The browser **is not a trusted source**: the SAML payload must be verified by the server.
5. `Saml2WebSsoAuthenticationFilter` extracts the message, resolves the registration, and invokes the `AuthenticationManager`/provider handling SAML; in modern Spring Security, the provider is backed by OpenSAML.
6. If verification succeeds, Spring creates a `Saml2Authentication`/principal and places it in `SecurityContext` according to the session policy.
7. The application must still check access permissions for URLs, data objects, and tenants. A valid signature from IdP B does not grant Portal A administrator privileges.

Default paths in many Spring Security Servlet configurations:

| Purpose | Commonly Used Default Path |
| --- | --- |
| Initiate login with a configuration | `/saml2/authenticate/{registrationId}` |
| ACS to receive and process Response | `/login/saml2/sso/{registrationId}` |
| ACS without ID, when supported by the resolver | `/login/saml2/sso` |
| SP metadata | `/saml2/metadata`, `/saml2/metadata/{registrationId}`, or `/saml2/service-provider-metadata/{registrationId}` |

For example, `/saml2/authenticate/partner-b` is the endpoint to **initiate authentication**, not where users submit passwords and not a protected API endpoint. The ACS `/login/saml2/sso/partner-b` is where the Response is processed; it must match the URI registered with the IdP. Do not change one side unilaterally while forgetting to update the other.

## 4. Data Model of `RelyingPartyRegistration`

A registration can be viewed along two branches:

~~~mermaid
flowchart TB
    R["RelyingPartyRegistration<br/>registrationId = partner-b"]
    SP["SP / Relying Party"]
    AP["IdP / Asserting Party"]
    R --> SP
    R --> AP
    SP --> E["entityId / SP issuer"]
    SP --> C["ACS location + binding"]
    SP --> X["signing / decryption X.509 credentials"]
    AP --> I["IdP entityId / Issuer"]
    AP --> S["Single Sign-On Service URL + binding"]
    AP --> V["verification X.509 credentials"]
    AP --> W["AuthnRequest signing expectations"]
~~~

The components relate as follows:

**SP side:**

- `entityId` represents the SP in SAML. The IdP typically puts this value into the `AudienceRestriction` of an assertion intended for the SP.
- `assertionConsumerServiceLocation` is the address to which the browser sends the Response. The IdP validates it against the configured registration.
- `signingX509Credentials` are SP assets; the private key must remain secret.
- `decryptionX509Credentials` are used if an encrypted assertion is received and the SP must decrypt it.
- Logout binding/location information, when using SAML Single Logout, must be configured consistently; login and logout are two separate flows.

**IdP side:**

- `entityId` is the expected issuer in SAML.
- `singleSignOnServiceLocation` is where the SP sends `AuthnRequest`.
- `verificationX509Credentials` are the public certificates that the SP trusts to verify signatures.
- `wantAuthnRequestsSigned` (builder model) or the equivalent property indicates whether the IdP requires the SP to sign `AuthnRequest`.

Do not confuse:

- The IdP's **verification** certificate with the SP's **signing private key**.
- SP Entity ID with IdP Entity ID.
- SP metadata with IdP metadata.
- User NameID with registrationId.
- Having one registration with having one user: a single registration can serve many IdP users.

## 5. Creating a Minimal Registration with Spring Boot Properties

A Servlet project using Spring Boot and Spring Security SAML2 needs the `spring-security-saml2-service-provider` dependency. Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

Versions should be managed by the Spring Boot BOM or chosen consistently with the running Spring Security/Framework version. The module depends on OpenSAML; depending on the version and artifact repositories, you may need to add the official Shibboleth Maven repository as documented by Spring Security. Do not assume every build in every environment needs only Maven Central.

Once the IdP provides complete verified parameters, a minimal `application.yml` configuration can be:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "https://portal.example.com/saml2/service-provider-metadata/partner-b"
            acs:
              location: "https://portal.example.com/login/saml2/sso/partner-b"
            assertingparty:
              entity-id: "https://login.partner-b.example/saml2/idp"
              singlesignon:
                url: "https://login.partner-b.example/saml2/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:saml/partner-b-signing.crt"
~~~

Properties such as `entity-id`, `acs.location`, `assertingparty.entity-id`, `assertingparty.singlesignon.url`, and `assertingparty.verification.credentials` describe the **SP–IdP pair**. After building, verify that the Spring Boot version in use shares the same property model, especially during major upgrades; do not apply configuration from old Spring Security 5 blogs to a new project without cross-checking.

Conditions for using this example:

- The file `saml/partner-b-signing.crt` contains the **real, verified public certificate** of IdP B; the file does not appear automatically.
- `sign-request: false` is appropriate only when IdP B **genuinely does not require signing AuthnRequest**. In environments requiring signing, the SP must have a signing credential and declare the signing requirement properly.
- Public URIs must be accepted/registered accurately by IdP B, including HTTPS scheme, hostname, path, and trailing slash.
- Do not remove the IdP certificate information just to silence a signature error; an SP without a reliable trust anchor cannot authenticate SAML securely.
- Published SP metadata will contain the configured SP parameters; it must be provided to the IdP administrator to import into their system.

Boot can create a `RelyingPartyRegistrationRepository` from properties. Spring Security will use that repository to determine the SP–IdP pair for each request.

### Configuring `SecurityFilterChain`

A minimal Spring Security Servlet class, **requiring the Boot application and registration above**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Save the file `SamlSecurityConfiguration.java` in the Spring Boot module that has the SAML dependency. The code demonstrates:

- `saml2Login` enables the Web Browser SSO flow for configured registrations.
- `saml2Metadata` enables publishing SP metadata; endpoints such as `/saml2/metadata/partner-b` must be reachable by the IdP according to network/application policy.
- `/health` is public in the example; all other URLs require login; `/admin/**` additionally requires `ROLE_ADMIN`.
- The configuration **does not automatically map IdP attributes to `ROLE_ADMIN`** and does not decide object/tenant permissions; the application must handle those separately.

**Specifically:** SAML Browser SSO typically POSTs from an external IdP page to the ACS. Spring Security has built-in CSRF logic for the standard flow; when customizing the ACS or CSRF policy, test the actual flow. Do not disable CSRF for the entire application just to "fix SAML".

## 6. Creating a Repository with JavaConfig When Configuration Is Not in YAML

Sometimes the SP must load metadata from the IdP instead of entering each endpoint and certificate manually. Spring Security provides `RelyingPartyRegistrations.fromMetadataLocation(...)`. A full JavaConfig skeleton example for a registration:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class SamlRegistrationConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("${app.saml.partner-b.metadata-url}") String trustedMetadataUrl) {

        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation(trustedMetadataUrl)
                .registrationId("partner-b")
                .entityId("https://portal.example.com/saml2/service-provider-metadata/partner-b")
                .assertionConsumerServiceLocation(
                        "https://portal.example.com/login/saml2/sso/partner-b")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

Illustrative properties:

~~~yaml
app:
  saml:
    partner-b:
      metadata-url: "https://login.partner-b.example/saml2/metadata"
~~~

**This is JavaConfig for a Spring project** and does not run standalone with `javac` without Spring dependencies; the sample URL does not work either. When `fromMetadataLocation` runs, the library reads the metadata and builds part of the IdP configuration. The input **must be a trusted metadata location** configured by an administrator; do not take a URL from an arbitrary request and fetch it directly due to SSRF risks and accepting a wrong trust anchor.

In production, metadata is updated, signature-verified, and certificates are rotated according to policy; loading once at startup can leave old keys/certificates around indefinitely. Consider a repository/metadata resolver mechanism that supports time-based refresh, metadata signature verification if required by the organization, and a rollback deployment procedure. Do not fetch arbitrary metadata and blindly trust every certificate found inside.

If a custom `RelyingPartyRegistrationRepository` bean is declared, clarify whether that bean **replaces or is used by Spring instead of** the auto-configured repository; avoid managing one copy in YAML and another in JavaConfig without knowing which one actually runs.

## 7. When You Need to Build Both SP–IdP Sides Manually

Some IdPs do not provide complete metadata or the metadata does not reflect the full contract. In that case, you can use the `RelyingPartyRegistration.withRegistrationId(...)` builder.

The snippet below **is only a fragment illustrating the model**: the variable `idpVerificationCertificate` is an `X509Certificate` already loaded and verified from secure configuration, not a standalone class.

~~~java
RelyingPartyRegistration registration =
        RelyingPartyRegistration.withRegistrationId("partner-b")
            .entityId("https://portal.example.com/saml2/service-provider-metadata/partner-b")
            .assertionConsumerServiceLocation(
                    "https://portal.example.com/login/saml2/sso/partner-b")
            .assertingPartyMetadata(party -> party
                .entityId("https://login.partner-b.example/saml2/idp")
                .singleSignOnServiceLocation(
                    "https://login.partner-b.example/saml2/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(credentials ->
                    credentials.add(Saml2X509Credential.verification(
                        idpVerificationCertificate))))
            .build();
~~~

You must import the exact `RelyingPartyRegistration` and `Saml2X509Credential` classes for the Spring Security version in use. If the IdP requires request signing, add the **SP's signing credential** with a properly protected certificate and private key, and do not set `wantAuthnRequestsSigned(false)` to bypass an error.

Identifying where parameters belong:

| Parameter to Declare | Which Side in the Builder? | Reason |
| --- | --- | --- |
| `registrationId` | Root registration | Spring looks up the exact configuration for the flow |
| `entityId(...)` on root builder | SP | IdP identifies the SP; assertions restrict audience to the SP |
| `assertionConsumerServiceLocation(...)` | SP | Browser sends the SAML Response to the ACS |
| `signingX509Credentials(...)` | SP | SP signs AuthnRequest/LogoutRequest per contract |
| `decryptionX509Credentials(...)` | SP | SP decrypts EncryptedAssertion if the IdP encrypts it |
| `assertingPartyMetadata(p -> p.entityId(...))` | IdP | Accept only the issuer the SP has chosen to trust |
| `singleSignOnServiceLocation(...)` in party | IdP | Address to send AuthnRequest |
| `verificationX509Credentials(...)` in party | IdP | Verify SAML signatures created by the IdP |
| `wantAuthnRequestsSigned(...)` | IdP policy | SP knows when requests must be signed |

For certificate data imported from a PEM file, distinguish the **IdP public certificate** used for verification from the SP private key used for signing/decryption; do not copy a private key into Java source or the repository.

## 8. Understanding `registrationId`, Entity ID, and URL Mapping

These are three distinct types of identifiers:

**A. `registrationId`** is an application-chosen key, such as `partner-b`. It can appear in paths like `/saml2/authenticate/partner-b` and `/login/saml2/sso/partner-b`, helping Spring distinguish multiple registrations. It carries no user identity meaning.

**B. SP Entity ID** is the SAML identifier published to the IdP. Its value may look like a URL, but it is **not necessarily a GET-able endpoint**. IdPs often configure it as "Audience URI" or "SP Entity ID". Do not change it arbitrarily because changing the Entity ID can mismatch existing assertions and the IdP-side registration.

**C. IdP Entity ID** identifies the organization/product issuing assertions. It is typically found in IdP metadata and must match the issuer of accepted messages. The IdP SSO URL is an endpoint for sending requests, not necessarily identical to the Entity ID.

Spring allows placeholders such as `{baseUrl}`, `{registrationId}`, `{baseScheme}`, `{baseHost}`, and `{basePort}` in supported URIs. For example:

~~~text
SP entityId:
{baseUrl}/saml2/service-provider-metadata/{registrationId}

SP ACS:
{baseUrl}/login/saml2/sso/{registrationId}

If baseUrl = https://portal.example.com, registrationId = partner-b:

SP entityId:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP ACS:
https://portal.example.com/login/saml2/sso/partner-b
~~~

When running behind a reverse proxy, a wrong scheme/host in `baseUrl` can cause the IdP to see an incorrect ACS/Entity ID, causing login loops or Audience/Recipient/Destination errors. Determine a fixed public URL, trust `Forwarded`/`X-Forwarded-*` only from **proxies managed by the application**, and verify forwarding configuration. Do not accept an arbitrary Host header as the SP entityId if the environment does not control the host.

**Important characteristic:** the metadata path is often accessed as an XML document, whereas **the Entity ID value** inside metadata is simply a consistent identifier. The two may look syntactically similar without serving the same function.

## 9. Two-Sided Metadata: What to Read, What to Publish?

### IdP Metadata

Typically IdP metadata contains `EntityDescriptor`, `IDPSSODescriptor`, `SingleSignOnService` endpoints with bindings, and signing/encryption keys. The SP uses this data to populate the `AssertingPartyMetadata` side.

- Metadata can be imported from a trusted URL, a managed file, or a configuration store.
- Cross-check `entityID`, certificates, and bindings with the IdP operator.
- Metadata XML may be signed; if policy requires it, verify the signature with an appropriate trust anchor.
- HTTPS protects transport, but does not by itself prove that an arbitrary endpoint is the organization's genuine IdP.
- Certificates expire and can rotate: establish an update process with an overlap window between old/new keys if the IdP supports it.

### SP Metadata

SP metadata typically contains `SPSSODescriptor`, SP Entity ID, ACS location, bindings, and public keys provided by the SP to the IdP. The IdP uses SP metadata to know where to send Responses and to verify signed AuthnRequests when required.

With `saml2Metadata(Customizer.withDefaults())`, Spring Security can publish metadata at `/saml2/metadata` and `registrationId`-scoped variants depending on the current version's mechanism. When using multiple registrations, metadata should be provided for the exact SP–IdP pair approved by the corresponding IdP administrator.

An onboarding sequence:

1. Register IdP B with administrator A and receive IdP metadata via a trusted channel.
2. SP A configures `RelyingPartyRegistration` for B, specifying entityId, ACS, certificates, and sign/decrypt policies.
3. SP A exports SP metadata to administrator B.
4. Administrator B registers SP A (exact SP Entity ID, ACS, signing certificate), ensuring B only issues assertions for SP A.
5. Both parties run integration tests with a test user and verify signature, audience, time, recipient, and logout if applicable.
6. When versions/keys change, each party updates metadata according to the rotation procedure and runs regression checks.

SP A publishing metadata does not automatically create access on B. There must be a **corresponding configuration on the IdP**.

## 10. `RelyingPartyRegistrationRepository`: How Is Configuration Looked Up?

`RelyingPartyRegistrationRepository` represents the registration store. A simple implementation is `InMemoryRelyingPartyRegistrationRepository` when the IdP list is small and relatively static. The repository is queried by `registrationId`; Spring has resolvers to determine the registration corresponding to a SAML request.

### Single IdP

~~~text
RegistrationRepository:
  partner-b -> RelyingPartyRegistration(
      SP = Portal A,
      IdP = B
  )
~~~

The standard flow starts from `/saml2/authenticate/partner-b`, so the registration must be unique. Do not let a request arbitrarily choose a different configuration based solely on an unverified payload.

### Multiple IdPs

~~~text
RegistrationRepository:
  corp-a    -> SP Portal A + Corp A IdP
  partner-b -> SP Portal A + Partner B IdP
  partner-c -> SP Portal A + Partner C IdP
~~~

Each entry has its own `registrationId`, its own IdP Entity ID, its own verification certificate, and may have its own SP Entity ID/ACS. Two partners both using the username `alice` does not mean they are the same internal account.

**Multi-tenant note:** multiple registrations support multi-IdP federation, but **do not automatically create tenant isolation**. The application layer must still check: which tenant issuer B is allowed into, whether the user has an active membership, how B's roles are mapped, and whether resources belong to the right tenant.

### Finding the Registration When Processing a Response

In the SP-initiated flow, Spring can use the saved `AuthnRequest` and the `registrationId` in the URL. In some cases, the framework may rely on the Response issuer to locate the matching registration. Regardless of how it is found, **finding a registration does not mean the Response is valid**: signatures, issuer, audience, recipient, time conditions, request correlation, and SAML conditions must still be verified.

When you want to replace the registration selection mechanism, use official extension points such as `RelyingPartyRegistrationResolver` or the corresponding authentication converter/resolver for each endpoint. Avoid mapping responses based on email or a client-sent tenant header.

## 11. Registering Multiple Relationships Does Not Mean Linking Multiple Identities

SAML identity federation has two separate layers:

1. **Trust configuration:** `RelyingPartyRegistration` states "SP A trusts assertions from IdP B within these limits".
2. **Identity/account mapping:** from the verified assertion, the application decides which internal user is used, which tenant they belong to, and what permissions they hold.

The user identifier can come from `NameID` or an attribute with stable semantics per the IdP contract, however:

- A **persistent** `NameID` can be suitable for account linking if the IdP guarantees its semantics and uniqueness scope.
- A **transient** `NameID` is not suitable as a long-term stored key.
- Email, display name, and username can change or be reused and should not be used to automatically merge accounts across organizations.
- Having the same subject/NameID from B and C does not prove they are the same person.

Suggested domain key:

~~~text
ExternalIdentityKey(
   tenantId,
   assertingPartyEntityId,
   persistentNameId,
   nameIdQualifierIfRelevant
) -> localUserId
~~~

This is a conceptual model; NameID attributes and qualifiers must be designed according to the actual SAML contract. Some IdPs emit a user attribute suitable as an immutable identifier; use it only when the IdP commits to its persistence. Do not automatically grant `ADMIN` from an external `groups=admins` attribute without a mapping approved by organization A.

**Example:** IdP B authenticates user `employee-123` and SP A verifies the Response successfully. The system must still check that partner B has been invited, the contract is active, the user has tenant B membership, and permission to view B's orders. That happens after `RelyingPartyRegistration`.

## 12. Signing, Decryption, and Commonly Confused Key Pairs

| Operation | Who Uses the Private Key? | Who Needs the Public Certificate? | Configured Where? |
| --- | --- | --- | --- |
| IdP signs SAML Response/Assertion | IdP | SP to verify | `AssertingPartyMetadata.verificationX509Credentials` |
| SP signs AuthnRequest | SP | IdP to verify | `RelyingPartyRegistration.signingX509Credentials` |
| IdP encrypts Assertion for SP | IdP uses SP's public certificate to encrypt | SP uses corresponding private key to decrypt | `RelyingPartyRegistration.decryptionX509Credentials` |
| SP signs LogoutRequest when required | SP | IdP to verify | Signing credentials and corresponding SLO config |

Do not include the SP's private key in public SAML metadata. Metadata only distributes the necessary certificate/public key portion. The IdP public certificate must also come from an agreed trusted source; do not accept "whatever certificate is embedded in the Response" as a root of trust.

**Key rotation:** when the IdP rotates its certificate, the SP may need to accept both old and new public keys simultaneously during a transition period per policy. If the SP rotates its signing key, the IdP must update its configuration to verify AuthnRequests. For the SP decryption key, in-flight encrypted assertions must be managed and the old key retained during the valid period.

**Do not confuse signing with encryption:** signature verification and decryption are required when specified by message/protocol type, and you must never "disable verification because decryption failed".

## 13. What Must Be Verified in a SAML Response

When validating a Response sent to the ACS, check at least:

1. **Issuer:** does it match the approved `AssertingPartyMetadata.entityId`?
2. **Signature:** are the required XML elements verified with the trusted certificate of the right IdP, protecting against signature wrapping?
3. **AudienceRestriction:** is the assertion intended for the exact SP entityId?
4. **Recipient/Destination:** was the message sent to the actual ACS/endpoint configured by the SP?
5. **Time:** are `NotBefore`, `NotOnOrAfter`, and `IssueInstant` valid within the specified clock skew?
6. **Request correlation:** for SP-initiated flows, does `InResponseTo` bind to an `AuthnRequest` created and stored by the SP?
7. **Replay:** has the Response/Assertion ID already been used, or has it exceeded the allowed window?
8. **Subject confirmation:** do holder/recipient/validity match the SAML profile in use?
9. **Conditions/AuthnStatement:** does it satisfy IdP conditions and the authentication level required by the business?
10. **Application authorization:** which endpoints/tenants/objects can the user access?

Spring Security SAML2 relies on its provider and the OpenSAML library for standard verification, but you still must configure it accurately and test negative cases. If customizing the authentication provider or response converter, do not accidentally drop the default validation steps.

**IdP-initiated login:** an unsolicited Response flow may lack a corresponding `AuthnRequest`; it does not carry the same correlation guarantees as SP-initiated flows. Enable it only when policy allows, with strict issuer, recipient, audience, replay checks, and safe session/RelayState handling. Do not treat a missing `InResponseTo` as automatically valid simply because the IdP signed it.

## 14. ACS Paths, Reverse Proxies, and Header Forwarding

A classic bug occurs when the Spring application runs internally on `http://localhost:8080`, while users access it via `https://portal.example.com`. If the SP generates the ACS from the internal base URL, metadata can advertise the wrong URL; the IdP sends the Response to the wrong endpoint, causing `Destination`/`Recipient`/`Audience` errors or redirect loops.

How to handle it:

- Prefer setting SP `entityId` and `acs.location` to fixed public URLs registered with the IdP.
- If using the `{baseUrl}` placeholder, configure trusted forwarded headers properly across Boot, proxy, and security policy; accept them only from trusted ingress/proxies.
- Align TLS, SNI, host, port, context path, and redirect URLs consistently.
- Do not allow clients to send arbitrary `Forwarded` or `X-Forwarded-Host` headers that could manipulate the SP Entity ID/ACS.
- When changing domains, coordinate updates to both SP metadata and IdP registration in the deployment sequence.

Do not "fix" this by disabling `Recipient`/`Destination` checks: that hides misconfiguration and weakens message recipient protection.

## 15. SAML Bindings and Protocol Details Do Not Fit in a Single URL

**HTTP-Redirect binding** is commonly used to pass `AuthnRequest` from the SP to the IdP via the browser. **HTTP-POST binding** is commonly used to send `SAMLResponse` back to the ACS. Depending on the IdP, `AuthnRequest` may go over POST and logout may use different bindings.

Things to verify:

- Which `SingleSignOnService` bindings and URLs does IdP metadata list?
- Does the SP choose a binding that the IdP actually supports?
- Does the IdP know the expected SP ACS URL/binding?
- Is a request signature required and is the signing algorithm accepted?
- Is the assertion signed, encrypted, and bound to the right policy?
- Are logout requests/responses configured and tested separately if used?

`RelyingPartyRegistration` groups the parameters of an SP–IdP pair, but a wrong binding configuration will still break communication. A properly signed Response sent to the wrong endpoint/binding can be legitimately rejected.

## 16. Standalone Java 17: Checking the SP–IdP Contract Before Real Integration

The code below is a plain Java example to reason about **one relationship configuration** and evaluate a few logical conditions. The code **does not verify SAML/XML signatures, does not issue sessions, does not read IdP metadata, and does not use Spring Security**. In a real product, run this policy **only after** Spring Security/OpenSAML has validated the Response and selected a trusted registration.

Create file `SamlRegistrationDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class SamlRegistrationDemo {
    record Registration(
            String id,
            String spEntityId,
            String acsUrl,
            String idpEntityId) {}

    record VerifiedAssertion(
            String issuer,
            String audience,
            String recipient,
            String subject) {}

    static boolean matches(
            Registration registration,
            VerifiedAssertion assertion) {
        return assertion.issuer().equals(registration.idpEntityId())
                && assertion.audience().equals(registration.spEntityId())
                && assertion.recipient().equals(registration.acsUrl());
    }

    public static void main(String[] args) {
        Registration partnerB = new Registration(
                "partner-b",
                "https://portal.example.com/saml2/service-provider-metadata/partner-b",
                "https://portal.example.com/login/saml2/sso/partner-b",
                "https://login.partner-b.example/saml2/idp");

        Map<String, Registration> repository = Map.of(
                partnerB.id(), partnerB);
        Registration selected = repository.get("partner-b");

        VerifiedAssertion valid = new VerifiedAssertion(
                partnerB.idpEntityId(),
                partnerB.spEntityId(),
                partnerB.acsUrl(),
                "employee-123");

        VerifiedAssertion wrongAudience = new VerifiedAssertion(
                partnerB.idpEntityId(),
                "https://another.example.com/sp",
                partnerB.acsUrl(),
                "employee-123");

        VerifiedAssertion wrongIssuer = new VerifiedAssertion(
                "https://login.partner-c.example/saml2/idp",
                partnerB.spEntityId(),
                partnerB.acsUrl(),
                "employee-123");

        System.out.println("Registration: " + selected.id());
        System.out.println("Valid: " + matches(selected, valid));
        System.out.println("Wrong audience: "
                + matches(selected, wrongAudience));
        System.out.println("Wrong issuer: "
                + matches(selected, wrongIssuer));
        System.out.println("Unknown registration: "
                + repository.containsKey("unknown"));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac SamlRegistrationDemo.java
java SamlRegistrationDemo
~~~

Exact stdout:

~~~text
Registration: partner-b
Valid: true
Wrong audience: false
Wrong issuer: false
Unknown registration: false
~~~

Explanation:

- `registrationId = partner-b` looks up the exact configured pair in the repository.
- `Valid: true` only asserts that the three *assumed-verified* values match the contract; it does not state that the signature/time conditions are valid.
- `Wrong audience: false` illustrates that an assertion intended for another SP must be rejected.
- `Wrong issuer: false` illustrates that IdP C cannot impersonate IdP B.
- `Unknown registration: false` illustrates that the repository does not accept unregistered IDs.

Do not use the `VerifiedAssertion` record as a trusted object if it is constructed directly from user-submitted JSON/XML. This structure is only for conceptual illustration; cryptographic and SAML profile checks must be performed by a battle-tested library.

## 17. Integration Testing a Real Registration

Set up a test IdP with explicit metadata and certificates, and an SP running over HTTPS at a real URL (or a controlled tunnel/lab). At minimum, the following test cases are needed:

| Test | Input Condition | Expected Outcome |
| --- | --- | --- |
| Repository lookup | `registrationId=partner-b` | Returns the exact SP Entity ID and IdP B Entity ID |
| Unknown registration | `registrationId=unknown` | Does not initiate SSO under any trust context |
| SP metadata | GET metadata for an allowed registration | Contains accurate SP entityID, ACS, and certificate |
| IdP metadata | Read verified metadata | Issuer and SSO URL match the organization; verification cert is accurate |
| SP-initiated SSO | Browser visits `/saml2/authenticate/partner-b` | AuthnRequest reaches IdP B; ACS receives Response |
| Different audience | Validly signed assertion from B but meant for SP C | Rejected |
| Different issuer | Assertion from IdP C at registration B | Rejected |
| Wrong ACS recipient | Response sent to an ACS outside the allowlist | Rejected |
| Expired ticket/assertion | `NotOnOrAfter` has passed | Rejected |
| Wrong request correlation | `InResponseTo` does not match an SP-stored request | Rejected in SP-initiated flow |
| Replay Response | Resubmit the same assertion under anti-replay policy | Does not create an unauthorized new session |
| Certificate rotation | IdP rotates signing cert per procedure | Only trusted certificates are accepted |
| IdP-initiated if supported | No originating request | Applies dedicated unsolicited Response policy |
| Unauthorized user | Valid SAML but insufficient role/membership | Login may succeed; sensitive actions return 403 |
| Multi-tenant | B and C share the same NameID/email | No cross-tenant account linking/privilege merging |
| HTTPS proxy | Valid public URL and forwarded headers | SP Entity ID/ACS match metadata and IdP |

You can start checking metadata with:

~~~bash
curl -i https://portal.example.com/saml2/metadata/partner-b
~~~

This command requires the application to be running and the endpoint to be reachable. The response depends on configuration; **there is no fixed XML stdout** to copy. Directly inspect `EntityDescriptor entityID`, `AssertionConsumerService Location`, `KeyDescriptor`, and the bindings. Do not treat an HTTP 200 metadata response as proof that login works; run the full flow with a real/test IdP.

Spring MockMvc tests can partially verify endpoints and authorization, but do not prove signature validation, IdP certificates, or the SAML browser round-trip without proper fixtures. A reliable test suite needs a combination of configuration unit tests, SAML integration tests, end-to-end tests, and negative cases.

## 18. Common Errors: Viewed from a Single Registration Perspective

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `registration not found` when opening login URL | Wrong `registrationId` or repository does not contain the entry | Check URL, bean, and Spring Boot configuration |
| IdP reports "unknown SP" | SP entityId misconfigured at the IdP | Cross-check SP metadata and IdP configuration |
| Response fails with "invalid issuer" | IdP entityId does not match the trusted source | Check IdP metadata, issuer, and registration |
| "Invalid audience" | Assertion intended for a different SP entityId | Align audience/SP entityId; do not disable validation |
| "Invalid recipient/destination" | ACS URL differs from public URL, proxy has wrong scheme/host | Fix ACS and forwarded header trust |
| "Signature invalid" | Wrong/rotated certificate, signed element differs from expectation | Check IdP signing cert and signature policy |
| "Unable to decrypt" | IdP encrypts assertion, SP lacks or has wrong decryption key | Align SP public cert and corresponding private key |
| `InResponseTo` not found | Session storing the request was lost, SameSite/cookie/proxy, or wrong flow | Check request repository and IdP-initiated design |
| Login loop | ACS blocked, session not created, wrong path/security rule | Trace POST ACS, filter chain, cookies, and response |
| Login succeeds but page is inaccessible | Missing local user/role/tenant or missing rule | Check application mapping and authorization |
| Two tenants merged into one user | Using email/NameID while ignoring issuer/tenant | Design safe identity key and account linking |
| Sudden IdP metadata change breaks login | Certificate/endpoint changed, cache not refreshed | Rotation procedure, refreshing metadata repository, rollback |
| Copying old example fails on method error | Different Spring Security/OpenSAML major version | Verify docs/Javadoc for the exact version |

When diagnosing, record the actual versions of Spring Boot, Spring Security, OpenSAML, the registrationId, checked issuer/audience/recipient, and validation errors. Do not log raw SAML Responses, assertions, private keys, session cookies, or sensitive personal data.

## 19. Spring Security and OpenSAML Version Notes

Modern Spring Security supports SAML2 in the `spring-security-saml2-service-provider` module. Method names and builder/provider details can change across major versions, especially between Spring Security 5/6/7 documentation and the bundled OpenSAML version.

- Prefer `SecurityFilterChain` and `saml2Login`; legacy examples based on `WebSecurityConfigurerAdapter` do not apply directly in new applications.
- In current Spring Security 7 documentation, SAML Response verification uses `OpenSaml5AuthenticationProvider`. Do not copy provider APIs verbatim from OpenSAML 3/4 blog posts.
- Spring Boot properties are the application-level configuration model; Java builders are the Spring Security API. Do not infer Java method names from YAML property names or vice versa.
- Identify the right servlet stack: Spring Security SAML2 Web Browser SSO is documented on the **Servlet** branch. Do not assume a Reactive adapter exists automatically just because a WebFlux app has the SAML dependency on the classpath.
- Use Spring Boot dependency management and check `dependencyInsight`/`dependency:tree` to avoid mismatched `spring-security-*` or OpenSAML versions.

Gradle example for a Java module:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

These are dependency inspection commands; outputs depend on the project and cannot be determined from a learning example. A successful build only verifies part of the setup: you must run an actual SP–IdP handshake to verify issuer, ACS, bindings, and certificates.

## 20. Design Decisions When Supporting Multiple Partners

**One registration per IdP:** usually makes it easier to separate certificates, endpoints, lifecycle, and audit logs. Do not use `registrationId = default` for all partners and let the client pick the IdP.

**Shared vs. separate SP entityId:** some organizations can use one shared SP entityId for the same application; others use a per-partner/tenant entityId. The choice must align with the IdP contract, ACS, metadata, certificates, and policy; there is no single mandatory answer. With a shared SP Entity ID, you must still verify the IdP issuer and proper tenant mapping.

**Static vs. dynamic repository:** small lists can use `InMemoryRelyingPartyRegistrationRepository`. Large lists or frequently changing metadata can use a trusted data store/metadata resolver/cache. Even when dynamic, only administrators or approved workflows may add IdPs; endpoints must not accept arbitrary metadata URLs from user requests.

**Registration and revocation:** when contract B ends, disable the registration/membership per policy, revoke active sessions, and block API access. Deleting an IdP configuration does not automatically invalidate all existing sessions.

**Audit:** record registrationId, verified issuer, timestamp, internal user, tenant, verification outcome, and rotation events. Do not store raw assertions in production logs without explicit requirements and clear data protection controls.

## 21. Synthesis Exercise: Auditing an SP–IdP Configuration

Portal A plans to integrate with IdP B. B provides A with these parameters:

~~~text
IdP entityId: https://login.partner-b.example/saml2/idp
IdP SSO URL: https://login.partner-b.example/saml2/sso
IdP signing certificate: partner-b-signing.crt
Registered SP entityId: https://portal.example.com/saml2/service-provider-metadata/partner-b
Registered SP ACS: https://portal.example.com/login/saml2/sso/partner-b
AuthnRequest signing required: no
~~~

**Question 1:** Does `registrationId` have to equal the IdP entityId?

**Answer:** No. Choose an internal key like `partner-b`, and map it to the IdP entityId, SP entityId, and ACS in `RelyingPartyRegistration`. Registration ID is not a SAML protocol identifier.

**Question 2:** A Response is signed by B, but `AudienceRestriction` lists Portal C's SP entityId. Should it be accepted?

**Answer:** No. IdP B's signature is not enough; the assertion must be intended for SP A with the matching audience.

**Question 3:** B rotates its certificate before A updates its config. Should signature validation be disabled to avoid downtime?

**Answer:** No. Execute planned rotation, verify the new certificate via a trust channel, and update the configuration/metadata resolver. If old and new keys must be supported in parallel, follow a mutually agreed policy.

**Question 4:** A user from B sends a valid Response containing the attribute `groups=admin`. Should `ROLE_ADMIN` be granted in A?

**Answer:** Only if there is an authorization mapping policy controlled by A and the user belongs to the appropriate tenant/context. Never automatically infer application admin rights from external claims.

**Question 5:** Running behind a TLS proxy, `http://internal:8080/login/saml2/sso/partner-b` appears in the metadata. What should be done?

**Answer:** Set the correct public ACS/base URL `https://portal.example.com/...`; verify trusted forwarded headers and synchronize the configuration at the IdP. Do not disable `Recipient` checks to "rescue" login.

## 22. Deployment Checklist for an SP–IdP Relationship

1. **SP identity:** unique `registrationId`, stable SP Entity ID, accurate public ACS URL and binding.
2. **IdP identity:** accurate issuer/entityID, SSO endpoint and metadata verified from a trusted source.
3. **Certificates:** IdP public verification cert, SP private signing/decryption keys (if needed), rotation schedule, and expiration handling.
4. **Protocol:** AuthnRequest signing policy, Response/Assertion signing, NameID format, time conditions, audience, recipient, correlation, and anti-replay.
5. **Spring integration:** SAML dependency, Boot config or Java repository, `saml2Login` and `saml2Metadata` properly routed.
6. **Application identity:** user mapping based on issuer + persistent identifier, never auto-merging by email.
7. **Authorization:** roles, tenants, object ownership, offboarding, and session revocation managed separately.
8. **Runtime:** HTTPS, reverse proxy, trusted forwarded headers, time synchronization, metadata failures, cache/rotation, and safe logging.
9. **Tests:** happy path, unknown IdP, wrong audience/recipient, invalid signature, expired/replayed assertion, wrong correlation, certificate rotation, and tenant permissions.
10. **Operations:** document registration owner, onboarding process, trust keys, metadata changes, and rollback plan.

**Key takeaway:** `RelyingPartyRegistration` is not merely an "IdP URL". It is the technical contract between **one specific SP** and **one approved IdP**: identifiers, send/receive endpoints, signature verification/decryption mechanisms, and protocol expectations. Spring Security performs SAML authentication based on that contract; the application still owns user mapping and resource authorization.

### Official Documentation

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html)
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — RelyingPartyRegistration API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html)