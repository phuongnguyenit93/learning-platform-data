# RelyingPartyRegistrationRepository and InMemoryRelyingPartyRegistrationRepository in Spring Security SAML 2.0

**RelyingPartyRegistrationRepository** is the interface Spring Security uses to look up the SAML 2.0 configuration linking a **Relying Party (RP) / Service Provider (SP)** application with an **Asserting Party (AP) / Identity Provider (IdP)**. **InMemoryRelyingPartyRegistrationRepository** is the common implementation that holds one or more `RelyingPartyRegistration` configurations in memory.

When an application must log in via an enterprise IdP, Spring Security needs to know **which IdP is trusted, where the SSO URL is, which certificate verifies signatures, what the SP Entity ID is, and where the ACS receives SAMLResponse**. This information resides in `RelyingPartyRegistration`; the repository helps login filters and related components find the right registration by `registrationId`.

**Key point to remember:** the repository manages **trust configuration for SP–IdP pairs**—it is not a user store, does not hold passwords, does not store login sessions, does not perform authorization, and does not directly validate SAML assertions.

## 1. Three Concepts: Registration, Repository, InMemory Repository

| Component | Type | Role | Example |
| --- | --- | --- | --- |
| `RelyingPartyRegistration` | Configuration data class | Describes an RP/SP and AP/IdP pair, from identifiers to endpoints and credentials | Connecting Portal to the corporate IdP |
| `RelyingPartyRegistrationRepository` | Interface | Looks up `RelyingPartyRegistration` by key | `findByRegistrationId("corp")` |
| `InMemoryRelyingPartyRegistrationRepository` | Implementation class | Stores registrations at initialization and provides lookup/iteration | Two registrations `corp`, `partner` |
| `IterableRelyingPartyRegistrationRepository` | Extended interface | Allows iterating over all registrations | Used for combined metadata or IdP selection pages |
| `RelyingPartyRegistrations` | Utility class | Helps create a builder from SAML IdP metadata | `fromMetadataLocation(...)` |

Viewed from a dependency perspective:

~~~text
SAML login components
         |
         v
RelyingPartyRegistrationRepository (interface)
         |
         +-----------------------------+
         |                             |
         v                             v
InMemoryRelyingParty...       Custom / caching repository
         |                             |
         v                             v
RelyingPartyRegistration(s)   RelyingPartyRegistration(s)
         |
         v
SP metadata + IdP metadata + X.509 credentials
~~~

Separating the interface from the implementation allows using **InMemory** when configuration rarely changes, or switching to a custom repository when supporting many tenants or dynamic metadata updates, while login handling depends primarily on the lookup contract.

## 2. What Does RelyingPartyRegistration Actually Contain?

Each object represents an **RP–AP pair** usable in SAML Web Browser SSO. To create a registration, the SP needs information about **itself** and trusted information about the **IdP**:

| Side | Property/Metadata | Purpose |
| --- | --- | --- |
| SP | `registrationId` | Internal key to select the registration, e.g., `corp` |
| SP | `entityId` | Entity ID that the IdP recognizes in SAML |
| SP | `assertionConsumerServiceLocation` | URL receiving SAML Responses at the SP |
| SP | `signingX509Credentials` | Private key and certificate the SP uses to sign when needed |
| SP | `decryptionX509Credentials` | Credentials to decrypt SAML assertions encrypted by the IdP |
| IdP | `assertingPartyMetadata(...).entityId(...)` | Identifier of the trusted asserting party/issuer |
| IdP | `singleSignOnServiceLocation` and binding | URL/method to send AuthnRequest |
| IdP | `verificationX509Credentials` | Public certificate used to verify signatures from the IdP |
| Both sides | Signing requirements, logout endpoints, NameID format... | Agreed protocol rules |

**Especially easy to confuse among the three IDs:**

- **`registrationId`** is the internal label chosen by the SP for the registration pair, such as `corp`. This value typically appears in default login URLs.
- **SP `entityId`** is the identifier in metadata and SAML messages so the IdP knows which SP is requesting authentication.
- **IdP `entityId`** is the identifier of the authentication system trusted by the SP, commonly used when checking the issuer.

They **do not have to be equal**. For example:

| registrationId | SP entityId | IdP entityId |
| --- | --- | --- |
| `corp` | `https://portal.example.test/saml/sp` | `https://idp.example.test/entity` |
| `partner` | `https://portal.example.test/saml/partner` | `https://login.partner.example.test/idp` |

If an IdP returns a Response from a known issuer but sends it to the ACS/recipient of another registration, matching only email or an issuer is not enough to allow login. Selecting the right registration is part of tenant protection and the trust relationship.

## 3. Repository Role in the SAML2 Web Browser SSO Flow

~~~text
(1) Browser                  (2) Spring Security SP
    GET /private  ------------->  Authorization requires login
                                         |
                                         v
                               RelyingPartyRegistrationRepository
                                         |
                          findByRegistrationId("corp")
                                         |
                                         v
                               RelyingPartyRegistration
                         IdP SSO URL, SP entityId, ACS, cert...
                                         |
                                         v
(3) Browser  <-------------  Create SAML AuthnRequest
       |                                 
       +---------> (4) IdP authenticates user
                          |
                          v
                    SAML Response
                          |
                          v
(5) Browser ----------> (6) SP / ACS
                              |
                              v
                  Resolve matching registration
                              |
                     Validate SAML response
                              |
                              v
                      Spring Authentication
                              |
                      Business authorization
~~~

When the browser initiates `/saml2/authenticate/corp`, Spring can typically find the registration based on `corp`. When receiving the SAML Response, resolution may rely on the **stored AuthnRequest**, issuer information, or a case-specific resolver strategy. Therefore, **do not assume every callback looks up solely by path**.

The repository provides **configuration**. The underlying filters, authentication providers, and SAML library are responsible for building/parsing messages and validating signatures, time conditions, recipient, audience, and matching request constraints.

### Common Default Endpoints

| Endpoint | Role |
| --- | --- |
| `/saml2/authenticate/{registrationId}` | Generates AuthnRequest for a registration |
| `/login/saml2/sso/{registrationId}` | ACS processing SAML Responses with default login processing config |
| `/saml2/metadata/{registrationId}` | Exports SP metadata if `saml2Metadata` is enabled |
| `/saml2/metadata` | Can export metadata for multiple registrations if iteration is supported |
| `/saml2/service-provider-metadata/{registrationId}` | Compatible metadata URL supported by Spring Security |

Besides paths carrying registrationId, current versions also support some endpoints without an id; resolution logic from authenticated context, request, or issuer must be evaluated carefully. **Customizing the ACS URL** requires synchronizing `assertionConsumerServiceLocation`, the login processing filter, and the IdP configuration.

## 4. The RelyingPartyRegistrationRepository Contract

Package:

~~~java
org.springframework.security.saml2.provider.service.registration
~~~

Core method of the interface:

~~~java
RelyingPartyRegistration findByRegistrationId(String registrationId);
~~~

**Behavior:** looks up a `RelyingPartyRegistration` by `registrationId`; returns **null** if not found. This is not an API for finding users, checking login status, or assigning permissions.

Example configuration with `corp` and `partner`:

~~~text
repository:
  "corp"      => SP + corporate IdP registration
  "partner"   => SP + partner IdP registration

findByRegistrationId("corp")      => corporate registration
findByRegistrationId("missing")   => null
~~~

In some Spring Security 6.x/7.x versions, the interface also supports `findUniqueByAssertingPartyEntityId(String entityId)`: looks up the unique registration matching the IdP entityId, or returns null if not unique/not found. **If two registrations share the same issuer**, you cannot rely solely on the issuer to randomly pick one registration.

`RelyingPartyRegistrationRepository` is not required to be Iterable. When features such as an IdP selection page or multi-registration metadata need to enumerate configurations, implement `IterableRelyingPartyRegistrationRepository` or also support `Iterable<RelyingPartyRegistration>` depending on the version's API. `InMemoryRelyingPartyRegistrationRepository` already supports iteration.

### Service Usage Example

Assuming `RelyingPartyRegistrationRepository repository` is injected:

~~~java
RelyingPartyRegistration registration =
        repository.findByRegistrationId("corp");

if (registration == null) {
    throw new IllegalStateException("Unknown registration: corp");
}

String chosenRegistrationId = registration.getRegistrationId();
~~~

This is a **snippet inside an application method**, using an existing `repository` variable; it is not standalone Java with `main`. With the `corp` configuration, `chosenRegistrationId` equals the string `corp`. The existence of a registration **does not prove a user has authenticated**.

## 5. How Does InMemoryRelyingPartyRegistrationRepository Work?

Class:

~~~java
org.springframework.security.saml2.provider.service.registration
    .InMemoryRelyingPartyRegistrationRepository
~~~

The package path above is wrapped onto two lines for readability only; a real Java import must use a single-line package name. The class has constructors accepting **varargs** or a **Collection** of `RelyingPartyRegistration`:

~~~java
new InMemoryRelyingPartyRegistrationRepository(corp);
new InMemoryRelyingPartyRegistrationRepository(corp, partner);
new InMemoryRelyingPartyRegistrationRepository(registrations);
~~~

In the last example, `registrations` is a `Collection<RelyingPartyRegistration>`. The implementation supports:

- `findByRegistrationId(String)` to retrieve a registration by ID.
- `findUniqueByAssertingPartyEntityId(String)` when a unique matching pair exists.
- `iterator()` to iterate over configured registrations.

**Advantages:** minimal code, clean lookup, no database needed just to hold a set of SAML configurations, easy bean registration, supports multiple IdPs, and works well when the registration set is stable.

**Limitations:** this is an in-process configuration store. InMemory **does not persist to a database**, **does not automatically add tenants** when users sign up, **does not automatically poll IdP metadata**, and **does not automatically rotate certificates** once a registration has been built. On restart, the application rebuilds the repository from beans/properties. When an IdP changes keys or SSO URLs, a controlled refresh/redeployment mechanism is required.

"Having InMemory in the name" does not mean it is only for demos; production with one or a few rarely changing IdPs can use it, provided key rotation, monitoring, and configuration changes are managed.

## 6. Java 17+ Example: Configuring a Registration via IdP Metadata

Goal: a **Spring Boot 3.x / Spring Security 6.x, Servlet MVC** application logging in via a corporate IdP with `registrationId=corp`, using a custom-declared InMemory repository.

Prerequisites before running:

1. The project has Spring Boot Web/Security and a compatible **`spring-security-saml2-service-provider`** module.
2. Real IdP metadata is provided by an administrator, e.g., `src/main/resources/saml/corp-idp-metadata.xml`.
3. The SP is registered at the IdP with matching **SP Entity ID** and **ACS**; signing/decryption credentials must be provided if required by the protocol and IdP.
4. The minimal example does not yet provide an SP private key for signing AuthnRequest. Use the template as-is only when the IdP **does not require the SP to sign AuthnRequest** and no separate decryption configuration is needed.
5. All `example.test` values in this article are illustrative only; they do not represent an active provider.

File: **src/main/java/com/example/security/SamlSecurityConfig.java**

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
            .registrationId("corp")
            .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
            .assertionConsumerServiceLocation(
                "{baseUrl}/login/saml2/sso/{registrationId}")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

**Part-by-part explanation:**

1. **`fromMetadataLocation(...)`** reads IdP metadata from `classpath:`, `file:`, or a trusted HTTPS endpoint and creates a `RelyingPartyRegistration.Builder`. IdP metadata usually describes only the IdP; SP configuration such as the private key for signing AuthnRequest may need to be added separately.
2. **`.registrationId("corp")`** sets the stable key used for repository lookup and in the login endpoint `/saml2/authenticate/corp`.
3. **`.entityId(...)`** sets the RP/SP Entity ID that the IdP uses to identify the application. The `{baseUrl}` and `{registrationId}` placeholders are supported by Spring Security; the IdP must see a final URL/ID matching the SP configuration.
4. **`.assertionConsumerServiceLocation(...)`** specifies the endpoint receiving SAMLResponse. The default path in the example matches `Saml2WebSsoAuthenticationFilter`.
5. **`new InMemoryRelyingPartyRegistrationRepository(corp)`** stores the registration in-process. Spring Security retrieves the `RelyingPartyRegistrationRepository` bean to look up configuration.
6. **`.saml2Login(Customizer.withDefaults())`** enables the SAML login flow. **`.saml2Metadata(Customizer.withDefaults())`** enables the endpoint publishing SP metadata for the IdP to use during registration.

**This is a configuration class belonging to a Spring Boot project**, not a standalone program compiled/run with `javac`/`java` without dependencies. There is no fixed stdout. The Java code above uses APIs available in Spring Security 6.x; when upgrading major versions, re-verify the APIs and especially OpenSAML/deprecation changes.

### Do Not Confuse Input Metadata with Output Metadata

- **Input:** `corp-idp-metadata.xml` contains **IdP** information (entity ID, SSO endpoint, certificate/binding); the builder reads it to know which IdP is trusted.
- **Output:** `/saml2/metadata/corp` can export **SP metadata** based on the registration; it helps the IdP administrator confirm the SP entity ID, ACS, and certificate if present.
- **Do not create a fake IdP metadata file** with placeholder certificates and use it for real login. When using a metadata URL, verify the source, TLS, and update strategy.

## 7. Integrating Multiple IdPs in the Same Repository

The company's Portal application has an internal IdP and a partner IdP. Replace the **repository bean method** in section 6 with:

~~~java
@Bean
RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
    RelyingPartyRegistration corp = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
        .registrationId("corp")
        .build();

    RelyingPartyRegistration partner = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/partner-idp-metadata.xml")
        .registrationId("partner")
        .build();

    return new InMemoryRelyingPartyRegistrationRepository(corp, partner);
}
~~~

This snippet **uses the imports, package, and class from section 6** and **replaces** the old bean method; do not define two beans of the same type without specifying clearly which bean Spring Security should use.

Once configured:

| URL | Selected Configuration |
| --- | --- |
| `/saml2/authenticate/corp` | Corporate IdP |
| `/saml2/authenticate/partner` | Partner IdP |
| `/login/saml2/sso/corp` | Callback for the corp configuration |
| `/login/saml2/sso/partner` | Callback for the partner configuration |
| `/saml2/metadata/corp` | SP metadata for the corp pair |
| `/saml2/metadata/partner` | SP metadata for the partner pair |

In practice, Spring Security can resolve a SAML Response via the AuthnRequest context or issuer, without necessarily requiring the callback path to always include registrationId. **Do not accept a corp Response under the partner registration**; maintain accurate tenant constraints, request state, audience, recipient, and signature checks.

With multiple registrations, the default login page can display IdP choices if the repository supports iteration. `InMemoryRelyingPartyRegistrationRepository` satisfies this requirement.

### One IdP with Multiple Registrations

When multiple tenants or environments **share one IdP entityId**, finding a "unique registration by issuer" can become ambiguous. `findUniqueByAssertingPartyEntityId` is appropriate only when there is a single pair for that issuer; if there are multiple pairs, resolution rules must use the request, a trusted tenant, and the SAML authentication context. Taking an email or picking an arbitrary tenant before verifying the assertion can lead to cross-tenant login.

## 8. Configuring with Spring Boot Properties Instead of @Bean

For standard setups, Spring Boot can auto-create a `RelyingPartyRegistrationRepository` from SAML2 properties when dependencies and auto-configuration conditions match. Spring Boot 3.x example:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp-metadata.xml"
~~~

**Note:** this is an **alternative** to declaring a custom repository bean. The **`corp`** key is used by Spring Boot as the `registrationId`. Check property syntax for your Spring Boot version and configure SP signing/decryption credentials if needed.

| Criterion | Using `application.yml` | Using `@Bean` with InMemory |
| --- | --- | --- |
| Single IdP, simple configuration | Concise and easy to manage | Concise but requires Java code |
| Multiple IdPs | Multiple keys under `registration` | Multiple registration objects |
| Reading IdP metadata | Via `metadata-uri` property | Via `fromMetadataLocation` or manual builder |
| Runtime configuration changes | Does not happen automatically just by editing the file | InMemory does not auto-refresh |
| Custom initialization logic | Limited by property binding | Easy to integrate config from internal systems |
| Integration test & review | Inspect YAML and property binding | Inspect Java factory/bean |

If you expose your **own repository bean**, Spring Boot typically backs off from creating the default bean from properties. Therefore, do not configure both sources assuming Spring will automatically merge them. Decide one metadata source and owner for a registration set to avoid conflicts.

## 9. Creating a Registration from Metadata or Manual Configuration?

### Option A: IdP Provides Trusted XML Metadata

~~~java
RelyingPartyRegistration corp = RelyingPartyRegistrations
    .fromMetadataLocation("https://idp.example.test/metadata")
    .registrationId("corp")
    .build();
~~~

An HTTPS metadata snippet like above requires a genuinely reachable endpoint, certificate, and valid XML. `example.test` is only a dummy domain; it will not work in practice until replaced with a real IdP. The utility extracts issuer, SSO endpoint, and verification certificates from metadata, reducing manual parameter copying.

### Option B: Manual Asserting Party Configuration

When the IdP does not provide metadata, `RelyingPartyRegistration.withRegistrationId(...)` lets you declare the issuer, SSO URL, binding, and **`verificationX509Credentials`** from a trusted certificate. However, the configuration code is longer and PKI data must be managed accurately.

Code fragment illustrating **inside the builder**:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistration
    .withRegistrationId("corp")
    .assertingPartyMetadata(party -> party
        .entityId("https://idp.example.test/entity")
        .singleSignOnServiceLocation("https://idp.example.test/sso")
        .wantAuthnRequestsSigned(false)
        .verificationX509Credentials(credentials ->
            credentials.add(idpVerificationCredential)))
    .build();
~~~

**Note:** the `idpVerificationCredential` variable is a `Saml2X509Credential` created from a **valid X.509 certificate of the IdP** per the organization's trust procedure. Because the example does not supply a real certificate, this is an **illustrative integration snippet** and not a standalone runnable Java program; replace it with real configuration. `wantAuthnRequestsSigned(false)` is only appropriate when the IdP genuinely does not require signed requests.

IdP metadata **does not automatically supply** the SP private key. If the IdP requires signing AuthnRequest, configure SP signing credentials; if the IdP encrypts assertions, provide SP decryption credentials. Do not confuse the **IdP verification certificate** with the **SP signing private key**.

## 10. Why Is Iterable Important for Metadata and the IdP Selection Page?

The `RelyingPartyRegistrationRepository` interface primarily addresses **lookup**. Some utilities need **enumeration**:

1. The default login page needs to know which asserting parties the application has to display choices when multiple IdPs exist.
2. SP metadata exporting all registrations via an ID-less endpoint needs to iterate through the list.
3. Configuration audit/monitoring tools may need to inventory declared registrations.

`InMemoryRelyingPartyRegistrationRepository` is an implementation of **`IterableRelyingPartyRegistrationRepository`** and provides `iterator()`. A custom repository implementing only `RelyingPartyRegistrationRepository` will **not automatically** support iteration; when listing is needed, choose an Iterable-capable interface/adapter per the version's documentation.

**Do not confuse** iteration with automatic IdP discovery on the Internet. The list includes only registrations configured by the application, with authorized trust sources that pass appropriate verification policies.

## 11. InMemory Limitations: Configuration Updates and Key Rotation

Consider when creating the bean:

~~~text
Startup:
  Read IdP metadata at version A
       |
       v
  Build RelyingPartyRegistration
       |
       v
  Store in InMemory repository
       |
       v
  Login while application is running

IdP rotates certificate or changes SSO endpoint to version B
       |
       v
  Old repository DOES NOT automatically know version B
       |
       v
  Login failures may occur if not updated
~~~

Having `fromMetadataLocation` read an HTTPS URL at startup **does not guarantee** that it will automatically refresh on every login. Many issues arise when an IdP rotates certificates, changes SSO endpoints, alters bindings, or retires an old cert.

Three common strategies:

- **Static + controlled deployment:** store verified metadata/certs in config and update the deployment when the IdP prepares rotation. Suits few IdPs with clear release processes.
- **Rebuild registrations from trusted metadata:** monitor IdP metadata and rebuild registrations with a proper atomic/configuration update mechanism, rather than mutating a map while Spring Security is reading it.
- **Metadata refresh/caching:** in supported versions, use `CachingRelyingPartyRegistrationRepository` with a supplier from a repository/metadata and a CacheManager; or build a custom repository on top of a refreshing metadata repository provided by the library. Manage TTL, cache invalidation, network errors, and safe fallback behavior.

Do not confuse **cache** with synchronizing every kind of state: caching only regulates metadata reloading when designed properly. **It does not automatically update user sessions or revoke authorization**. When an IdP rotates its certificate, never disable SAML signature checks to temporarily suppress errors.

### Metadata URLs Must Be Protected

SAML metadata contains trust information (issuer, endpoints, certificates). Free-form URLs entered by customers/tenants must not be passed straight into `fromMetadataLocation` without controlling source allowlists, network access, TLS, and approval policies. Otherwise, the application risks reading spoofed sources or triggering SSRF in dynamic configuration systems.

## 12. SP Metadata and Reverse Proxy Constraints

SP metadata is typically used by the IdP to record the **SP Entity ID, ACS URL, and SP certificates**. When enabled:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Spring Security can publish metadata at `/saml2/metadata`, `/saml2/metadata/{registrationId}`, and supported compatible paths.

A common scenario:

~~~text
Browser: https://portal.example.test
              |
       HTTPS Reverse Proxy
              |
       Spring app: http://10.0.0.5:8080
~~~

If `{baseUrl}` resolves to `http://10.0.0.5:8080` due to misconfigured forwarded headers, metadata may advertise **an ACS and SP Entity ID that do not match** the external URL registered at the IdP. The IdP may then reject requests or send responses to the wrong address.

Solutions include defining the public URL explicitly, configuring reverse proxy/forwarded headers via a trusted mechanism, and inspecting actual metadata in production. Do not accept arbitrary `X-Forwarded-Host` headers from the Internet without a trusted proxy in front, as it affects URLs generated inside messages.

**Consistency principle:** the entityId/ACS values registered at the IdP must match the repository configuration and actual SP endpoints.

## 13. Security When Using the Repository

`InMemoryRelyingPartyRegistrationRepository` does not directly check user authentication. During login, Spring Security components use the registration to validate the SAML Response and create an `Authentication`. Ensure:

1. **Correct IdP issuer:** accept only permitted asserting parties; do not rely on email, query string, or username to bypass issuer verification.
2. **Correct certificate trust:** verify signatures using verification credentials from approved metadata/certificates. Never use an unverified certificate source.
3. **Correct audience and recipient:** a validly signed Response meant for another SP must not be accepted.
4. **Correct validity window and request binding:** check `NotBefore`, `NotOnOrAfter`, `InResponseTo`, subject confirmation, and replay where applicable.
5. **Dedicated SP private keys:** signing AuthnRequest and decrypting assertions require SP-owned private keys, stored securely and never placed in logs or public YAML.
6. **Tenant isolation:** prevent IdP A's registration from being used when processing a Response for IdP B or another environment.
7. **Independent authorization:** `Saml2AuthenticatedPrincipal` is proof of authentication; admin, data, and resource permissions require policy-based authorization checks.
8. **Separate session and logout:** the repository stores trust config; SP sessions, cookies, Single Logout, and account lifecycle are separate responsibilities.
9. **Certificate rotation plan:** track expiration dates, deployment timing for new metadata, and overlap windows between old/new certs when supported by the IdP.
10. **Sensible monitoring:** monitor SAML and metadata errors without writing full SAML assertions, private keys, or PII into logs.

**Bad example:** A developer takes the IdP entityId from an unverified request, looks up a registration with that issuer, and allows login into a tenant chosen by a query parameter. This can cross tenant boundaries. **Right approach:** use AuthnRequest state, bound IDs/tenants, and validate messages against the exact SP–IdP pair.

## 14. Diagnosing Errors in the Application

| Issue | Possible Cause | Check/Resolution |
| --- | --- | --- |
| `findByRegistrationId("corp")` returns null | Wrong key, bean contains a different set of registrations | Verify bean method, registrationId, and called endpoint |
| Startup fails to read metadata | Wrong classpath path, HTTPS error, invalid XML | Check resources in `src/main/resources`, source trust, and startup logs |
| Browser redirects to wrong IdP | Wrong registration or SSO URL/binding | Check `/saml2/authenticate/{id}` URL and IdP metadata |
| IdP reports unrecognized SP | SP Entity ID unregistered or mismatched | Compare SP metadata with IdP configuration |
| IdP rejects unsigned AuthnRequest | IdP requires SP signing | Configure signing credentials; check IdP requirements |
| SAMLResponse arrives but Spring reports validation failure | Wrong signature, issuer, recipient, audience, or time | Cross-check metadata and debug logs with sensitive data masked |
| ACS returns `404` or filter does not run | Callback URL mismatches login processing URL | Align ACS builder, `saml2Login`, and IdP |
| After IdP rotation, signature is no longer valid | Repository holds old certificate | Refresh metadata/certificates through a safe procedure |
| `/saml2/metadata` does not return a list | Metadata DSL not enabled or repository not Iterable | Enable `saml2Metadata`, use an iterable implementation |
| User logs in successfully but receives `403` | Missing authority or business permission | Check principal/attribute mapping and authorization |
| Wrong tenant when multiple registrations share issuer | Issuer lookup is not unique | Design resolver with trusted state/registrationId |
| Behind proxy generates internal HTTP ACS | Wrong external base URL or forwarded headers | Standardize HTTPS public URL and proxy trust |

Do not "fix" errors by disabling signature, audience, recipient, or time checks, or by allowing all tenants. Those errors usually indicate incompatible trust/registration configuration.

## 15. Implementation Choice Scenarios

### A. Single Corporate IdP, Stable Configuration

For example, an intranet Portal logging in only via the corporate IdP. Spring Boot properties or an InMemory bean is a simple choice. Test ahead of certificate rotation dates and schedule new metadata deployments.

### B. Three B2B Partners

The Portal serves three partner organizations. Create three `RelyingPartyRegistration` instances (each with a clear registrationId) and return an InMemory repository. **Tenant isolation** checks remain mandatory even after the user authenticates successfully via a partner IdP.

### C. Many Tenants Self-Onboarding IdPs at Runtime

The number of tenants changes frequently; metadata, certificates, and authentication policies may be updated by administrators. An InMemory repository created once at startup is not flexible enough. Design a custom repository or trusted metadata refresh/cache mechanism, enforce permissions on config changes, and verify IdP sources.

### D. Switching Between Staging and Production

Do not share SP Entity ID, ACS, or private keys arbitrarily. Each environment should have explicit registrations; ensure public URLs, metadata, and IdP settings match the environment. Avoid hard-coding one domain and reusing the same bean across both staging and production.

### E. IdP Rotates Signing Certificates Quarterly

If operations wants zero-restart certificate rotation, a refreshing metadata repository or cache with an appropriate TTL is needed, accepting approved keys during the transition window. Test failure modes when the IdP metadata endpoint is unreachable; never relax signature verification.

## 16. Implementation and QA Checklist

- [ ] Assign each SP–IdP pair a stable, non-colliding `registrationId`.
- [ ] Configure accurate SP Entity ID, ACS, IdP Entity ID, SSO endpoint, and bindings.
- [ ] Obtain IdP metadata from a verifiable source containing the proper verification cert.
- [ ] Include SP signing/decryption credentials if required by IdP policy or protocol.
- [ ] Choose one clear configuration source: Boot properties or a repository bean.
- [ ] When using InMemory, understand the post-startup configuration update lifecycle.
- [ ] With multiple registrations, test request initiation and callbacks per IdP, including shared IdP issuers.
- [ ] If combined metadata or an IdP selection page is needed, ensure the repository supports Iterable.
- [ ] Test SSO, ACS, and metadata endpoints in an environment with HTTPS/proxies.
- [ ] Have a plan for certificate rotation, metadata refresh, monitoring, and safe error handling.
- [ ] Never allow one tenant's configuration to authenticate a response for another tenant.
- [ ] Separate SAML authentication from role, tenant, and resource authorization.

## 17. Self-Check Questions

**1. Does `RelyingPartyRegistrationRepository` store user accounts or passwords?**  
No. It stores **SAML configuration for RP/AP**, not personal login credentials or sessions.

**2. Must `registrationId="corp"` equal the SAML Entity ID?**  
No. Registration ID is an internal key. SP Entity ID and IdP Entity ID are protocol identifiers.

**3. What does `findByRegistrationId("missing")` return when not found?**  
It returns **null** per the API contract.

**4. Can one InMemory repository hold multiple IdPs?**  
Yes. Use the varargs/Collection constructor with multiple `RelyingPartyRegistration` instances.

**5. Does fetching HTTPS metadata at startup guarantee automatic refresh when the IdP rotates certificates?**  
No. You must design repository updates/rebuilds or a metadata refresh/cache mechanism.

**6. Why is `IterableRelyingPartyRegistrationRepository` useful?**  
It allows enumerating registrations, supporting features such as the IdP selection page and combined metadata.

**7. If two registrations have the same IdP issuer, can one be picked automatically by issuer?**  
Not safely if it cannot be uniquely distinguished. Trusted request/tenant context is required.

**8. After successful SAML login, does a user automatically gain admin privileges?**  
No. Application-level authorization checks remain mandatory.

**9. Can InMemory be deployed in production?**  
Yes, if the configuration set is stable and key rotation/metadata updates are operationally controlled.

**10. Why does the SP signing key differ from the IdP verification certificate?**  
The SP uses **its own private key** to sign (if required); the SP uses the **IdP's public certificate** to verify signatures on messages from the IdP.

## 18. Conclusion

**`RelyingPartyRegistrationRepository` is Spring Security SAML2's registration lookup contract; `InMemoryRelyingPartyRegistrationRepository` is the implementation that stores registrations in memory and supports iteration.** Use this implementation for a few IdPs with relatively static configurations. When many tenants change continuously or dynamic lookup, metadata refresh, or frequent certificate rotation is needed, consider a purpose-built repository/metadata layer. In all cases, keep the **issuer – entity ID – ACS – certificate – audience – tenant** boundaries exact, and separate authentication from authorization.

### Official Documentation

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 API — `RelyingPartyRegistrationRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrationRepository.html
- Spring Security 6.5 API — `InMemoryRelyingPartyRegistrationRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/InMemoryRelyingPartyRegistrationRepository.html
- Spring Security 6.5 API — `RelyingPartyRegistrations`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html
