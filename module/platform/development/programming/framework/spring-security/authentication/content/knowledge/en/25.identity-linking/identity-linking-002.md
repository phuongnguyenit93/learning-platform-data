# SAML2 Login: Service Provider, Identity Provider, and Assertion

## 1. Objectives and Context

**SAML 2.0 Login** is a mechanism that lets a web application authenticate users through an external identity system. In Spring Security, the application acts as the **Service Provider (SP)**, while the authentication system (such as ADFS, Keycloak, or an enterprise IdP supporting SAML) acts as the **Identity Provider (IdP)**. After authenticating the user, the IdP returns a SAML message containing an **Assertion** for the SP to verify and establish an application login session.

After this lesson, you should be able to:

- Distinguish **SP / Relying Party**, **IdP / Asserting Party**, **Assertion**, **SAML Response**, **Metadata**, **Entity ID**, **ACS**, and **NameID**.
- Describe the **SP-initiated SSO** flow and distinguish it from **IdP-initiated SSO**.
- Understand how Spring Security generates `AuthnRequest`, receives `SAMLResponse`, validates the assertion's signature/conditions, and creates `Saml2Authentication`.
- Configure a **Spring Boot 3.x + Spring Security 6.x (Servlet, Java 17+)** application as a Service Provider using `RelyingPartyRegistrationRepository` and `HttpSecurity.saml2Login(...)`.
- Read common assertion fields, map identities and authorities, test happy/failure paths, and troubleshoot SSO errors behind a reverse proxy.
- Understand key differences when working with Spring Security 5.x/6.x/7.x; avoid using APIs that changed across versions.

**Lesson scope:** SAML 2.0 **Web Browser SSO Profile** in Spring Security Servlet. This is login based on **XML assertions**, not the OAuth 2.0 Authorization Code or OpenID Connect (OIDC) protocol. An application needs a real IdP or a test IdP configured with mutual trust to run the full end-to-end flow.

## 2. Roles: SP, IdP, Browser, and User

| Role | Name in Spring Security | Responsibility |
| --- | --- | --- |
| **Service Provider (SP)** | **Relying Party** | Application that needs to know who is accessing it; sends authentication requests, receives and verifies SAML Responses, and establishes sessions/authorities |
| **Identity Provider (IdP)** | **Asserting Party** | Authenticates users using the organization's mechanisms (password, MFA, security key, ...), signs assertions, and returns results to the SP |
| **Browser (User Agent)** | User's browser | Redirects to the IdP and submits HTTP POST/Redirect carrying SAML messages; the browser is an **untrusted** medium for message contents |
| **User** | `Principal` after authentication | Individual or login account; authorization policies within each application are decided by the SP |

Example:

```text
SP:      https://app.example.org
IdP:     https://login.example.org
User:    linh@example.org

SP Entity ID:  https://app.example.org/saml2/service-provider-metadata/company-idp
IdP Entity ID: https://login.example.org/idp
ACS:          https://app.example.org/login/saml2/sso/company-idp
```

`Entity ID` is a **logical identifier** of a SAML entity, typically expressed as a URI. It is **not necessarily a URL openable in a browser**. `ACS` (*Assertion Consumer Service*) is where the SP receives the SAML Response. Both values must be properly registered and agreed upon between the SP and the IdP.

In Spring Security, an SP–IdP pair is described by `RelyingPartyRegistration`; a `registrationId` such as `company-idp` is an **internal key** to select the configuration, distinct from both Entity IDs.

## 3. What Is a SAML Assertion? Distinguishing It from SAML Response

An **Assertion** is a statement issued by an IdP about a subject. In SAML 2.0, an assertion can carry:

- `Issuer`: the entity that issued the assertion.
- `Subject` and `NameID`: the identity of the subject, such as a stable user identifier.
- `SubjectConfirmation`: conditions for confirming the subject; in Browser SSO this is typically **bearer** along with `Recipient`, `InResponseTo`, and `NotOnOrAfter`.
- `Conditions`: validity window (`NotBefore`, `NotOnOrAfter`), `AudienceRestriction` to restrict which SP may accept it.
- `AuthnStatement`: details about the authentication event, authentication timestamp, and sometimes session index and authentication context.
- `AttributeStatement`: additional attributes such as email, display name, or groups; **not automatically application permissions**.

A **SAML Response** is the outer wrapper message carrying a status and one or more assertions (which may be encrypted). Both the response and assertion can carry XML signatures depending on IdP configuration and binding. The browser typically sends `SAMLResponse` (Base64-encoded) in a form POST to the ACS.

**Conceptual XML diagram** example, not a complete or validly signed SAML Response:

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response123"
    InResponseTo="_request789"
    Destination="https://app.example.org/login/saml2/sso/company-idp">
  <saml:Issuer>https://login.example.org/idp</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion456">
    <saml:Issuer>https://login.example.org/idp</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user-7392</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            InResponseTo="_request789"
            Recipient="https://app.example.org/login/saml2/sso/company-idp"
            NotOnOrAfter="2030-01-01T10:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions
        NotBefore="2030-01-01T09:59:00Z"
        NotOnOrAfter="2030-01-01T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://app.example.org/saml2/service-provider-metadata/company-idp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="2030-01-01T10:00:00Z"/>
    <saml:AttributeStatement>
      <saml:Attribute Name="email">
        <saml:AttributeValue>linh@example.org</saml:AttributeValue>
      </saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>
```

**Do not send this sample XML to an ACS to test login.** It intentionally omits signatures, namespaces/types of certain elements, and protocol constraints. `InResponseTo` cannot be set arbitrarily: it must correlate with the actual authentication request sent. `NotOnOrAfter` is the timestamp at which it is **no longer valid**; time comparisons must use UTC with controlled clock-skew tolerance.

XML signatures protect integrity and identify a trusted issuer. **Base64 is neither encryption nor signature verification**. If an assertion contains sensitive data, `EncryptedAssertion`/`EncryptedAttribute` and the SP's decryption key can be used per policy.

## 4. End-to-End SP-Initiated SSO Flow

```text
User             Browser                 SP (Spring Security)             IdP
    |                 |                           |                      |
    | Open /dashboard |                           |                      |
    |---------------->| GET /dashboard            |                      |
    |                 |-------------------------->|                      |
    |                 |      not logged in        |                      |
    |                 |<--------------------------|                      |
    |                 | GET /saml2/authenticate/company-idp              |
    |                 |-------------------------->|                      |
    |                 |     Create AuthnRequest + RelayState             |
    |                 |<--------------------------|                      |
    |                 | POST/Redirect request to IdP                     |
    |                 |------------------------------------------------->|
    |                 |                     IdP authenticates, maybe MFA |
    |                 |<-------------------------------------------------|
    |                 | POST SAMLResponse to ACS                         |
    |                 |-------------------------->|                      |
    |                 |     Verify signature, issuer, audience, time     |
    |                 |     recipient, correlation, create Authentication|
    |                 |<--------------------------|  session/cookie      |
    |                 | GET /dashboard            |                      |
    |                 |-------------------------->|                      |
    |<----------------|  Protected content        |                      |
```

Spring Security details:

1. The user accesses a route requiring `.authenticated()`. If no valid security context exists, the application initiates SAML login; it may display an IdP selection page when multiple `RelyingPartyRegistration` entries are registered.
2. `Saml2WebSsoAuthenticationRequestFilter` handles endpoints like `/saml2/authenticate/{registrationId}`, builds `<saml2:AuthnRequest>`, and sends it to the IdP using the configured HTTP-Redirect or POST binding. It uses `RelyingPartyRegistration` to look up the SP Entity ID, ACS, and IdP SSO URL.
3. The IdP authenticates the user according to the IdP's policy. SAML does not require the SP to know the user's password or the IdP's MFA methods.
4. The IdP constructs `<samlp:Response>` with the assertion and signatures/encrypted elements per metadata/policy, sending it via the browser to the SP's ACS. The browser must not be treated as a trusted authority for message content.
5. `Saml2WebSsoAuthenticationFilter` receives the POST at `/login/saml2/sso/{registrationId}` (or the corresponding supported endpoint), creates `Saml2AuthenticationToken`, and delegates to `AuthenticationManager`/the SAML authentication provider.
6. The provider uses the registered IdP details to verify the signature, decrypt if needed, validate Response/Assertion conditions, and return `Saml2Authentication`. On failure, no authenticated session is created.
7. Upon success, Spring Security places `Authentication` in `SecurityContext`; the application's security context/session persistence mechanism determines how subsequent requests observe the login.

**Correlation:** in SP-initiated SSO, AuthnRequest has an `ID` and associated HTTP state (`RelayState` if used). The provider/request repository must match `InResponseTo` against the pending request. By default, Spring Security uses `HttpSessionSaml2AuthenticationRequestRepository` for AuthnRequest; therefore cookie/session configuration, reverse proxies, and load balancing can affect login.

## 5. How Does IdP-Initiated SSO Differ from SP-Initiated SSO?

In **IdP-initiated SSO**, the user launches an application from the IdP portal, and the IdP sends a SAML Response to the SP's ACS **without a prior AuthnRequest from the SP**. This flow is commonly called an *unsolicited SAML response*.

Trade-off: there is no pending AuthnRequest to strictly match `InResponseTo` as in SP-initiated flow. If the SP and IdP support IdP-initiated SSO, dedicated controls are required: issuer, signature, audience, recipient, validity window, replay protection, tenant identity, cookie/session, and RelayState/target URL. Do not accept an uncorrelated response merely because the browser forwarded it to the ACS.

When there is no business requirement for IdP-initiated SSO, prefer **SP-initiated** to maintain stronger correlation. Support for unsolicited responses depends on the configuration, version, and policy of the application; test it directly rather than assuming the ACS endpoint accepts arbitrary POSTs.

## 6. Metadata: The Foundation of Trust Between SP and IdP

**Metadata** is an XML document describing how entities communicate with each other, typically containing:

| Attribute | In IdP Metadata | In SP Metadata |
| --- | --- | --- |
| `entityID` | Expected IdP/Issuer identifier | SP/Audience identifier to which the IdP issues assertions |
| SSO service | IdP URL receiving AuthnRequest, HTTP binding | Typically not an IdP SSO URL |
| ACS | Not where the IdP consumes SP assertions | URL/bindings receiving Responses |
| Verification certificates | Public key used by SP to verify IdP signatures | Public key used by IdP to verify signed SP requests |
| Encryption certificates | Per IdP policy | Public key provided by SP so IdP can encrypt assertions for SP |
| Single Logout services | Optional, if supported by both parties | Optional, separate from login |

`RelyingPartyRegistration` holds the configuration for an SP–IdP **pair**. `RelyingPartyRegistrationRepository` manages one or more such pairs.

- `registrationId` is an application-chosen key, such as `company-idp`.
- `RelyingPartyRegistrations.fromMetadataLocation(...)` can initialize a registration from IdP metadata (URL or appropriate resource).
- `InMemoryRelyingPartyRegistrationRepository` fits when configurations are few and static; with multiple IdPs, tenants, or auto-refreshing metadata, a clear repository, caching, and rotation strategy is required.
- `.saml2Metadata(withDefaults())` exposes **SP metadata** at `/saml2/metadata` or `/saml2/metadata/{registrationId}` in Spring Security versions supporting that DSL.
- You must register the SP Entity ID, ACS URL, public certificates, and signing requirements with the IdP before real SSO will work.

**Crucial:** trusting unauthenticated XML metadata is risky. Fetch it from a trusted administrative source over HTTPS, verify metadata signatures if policy requires, and pin or rotate verification certificates in a controlled manner. Automatic metadata refresh must monitor key/issuer changes and provide a recovery path if the IdP is unreachable.

## 7. Spring Boot 3.x + Spring Security 6.x Service Provider Example

This is a **Servlet** example using Java 17+ and Gradle. The Java classes below are structurally complete, but the application will only perform real logins once provided with **valid IdP metadata** and SP registration on the IdP.

### 7.1. Dependencies

In `build.gradle` of a Spring Boot 3.x project with dependency-management plugin/BOM already configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-saml2-service-provider` brings in SAML Relying Party support and the compatible OpenSAML library. Do not add OAuth2 Client or Resource Server just to get SAML Login. Never force `spring-security-*` modules onto a major version mismatched with the Spring Boot BOM.

### 7.2. Pointing to Verified IdP Metadata

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

app:
  saml:
    idp-metadata-location: ${IDP_METADATA_LOCATION:classpath:metadata/company-idp.xml}
```

The file `classpath:metadata/company-idp.xml` must be **real** metadata provided by a trusted IdP; this example does not bundle that file. `IDP_METADATA_LOCATION` can be replaced with an HTTPS metadata URL managed by your organization. In production, the SP must be accessed over **HTTPS** at its official public URL; do not use default `localhost:8080` as a real ACS.

### 7.3. Security Configuration and RelyingPartyRegistrationRepository

File `src/main/java/example/saml/SamlSecurityConfig.java`:

```java
package example.saml;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("${app.saml.idp-metadata-location}") String idpMetadata) {

        RelyingPartyRegistration registration =
            RelyingPartyRegistrations.fromMetadataLocation(idpMetadata)
                .registrationId("company-idp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().authenticated()
            )
            .saml2Login(withDefaults())
            .saml2Metadata(withDefaults());

        return http.build();
    }
}
```

Code notes:

- Once you define a `RelyingPartyRegistrationRepository` bean, do not simultaneously define another repository in YAML and lose track of which configuration is active.
- `RelyingPartyRegistrations.fromMetadataLocation` reads IdP settings (issuer, SSO URL, verification key, signing requirements...) from metadata; `registrationId` here is `company-idp`.
- `saml2Login(withDefaults())` enables the SAML login flow and registers the corresponding request/response filters; `saml2Metadata(withDefaults())` publishes SP metadata for registration with the IdP.
- `/me` requires successful `Authentication`; it never grants `ROLE_ADMIN` or business roles based on email.
- An application with multiple security filter chains must ensure login and ACS requests match the chain containing `.saml2Login(...)`; a wrong matcher can cause 404/403 on the ACS or never establish `Authentication`.
- In practice, metadata may require **signed AuthnRequests**. In that case, the SP needs a securely managed signing private key + certificate; this example does not provide that key and does not guarantee compatibility with every IdP.

### 7.4. Bootstrap and Controller Reading Identity

`src/main/java/example/saml/SamlDemoApplication.java`:

```java
package example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlDemoApplication.class, args);
    }
}
```

`src/main/java/example/saml/CurrentUserController.java`:

```java
package example.saml;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> currentUser(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of("nameId", principal.getName());
    }
}
```

In Spring Security **6.x**, `Saml2AuthenticatedPrincipal` is the standard API for accessing `NameID` and attributes. In **7.1+**, several of these principal APIs have been deprecated in favor of `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`. When upgrading, consult the migration guide and Javadoc for your exact version; do not copy 7.1 configurations into 6.x expecting the same object types.

The returned value is the `NameID` issued by the IdP, which may be an opaque identifier rather than an email or display username. Never assume `NameID` is a durable primary key or unique across all IdPs. Structure DTOs to return only the required fields; avoid returning the entire assertion to the frontend.

Run the application:

```bash
./gradlew bootRun
```

When metadata is valid and the IdP has registered the SP, open:

```text
http://localhost:8080/saml2/authenticate/company-idp
```

This is only a **local address to initiate the flow**. A real IdP must allow the ACS and SP Entity ID matching the public base URL published by the application. A demo project intending end-to-end SSO typically requires a public HTTPS hostname or a corresponding test IdP environment.

## 8. Manual IdP Configuration via Spring Boot Properties

When IdP metadata is not fetched automatically, Spring Boot 3.x allows specifying **Asserting Party** properties in `application.yml`. Condensed example replacing the repository bean in section 7.3 (if using this YAML, **remove the `relyingPartyRegistrations` bean above** to avoid duplicate configuration):

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company-idp:
            assertingparty:
              entity-id: "https://login.example.org/idp"
              sso-url: "https://login.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/idp-signing.crt"
```

`idp-signing.crt` must be a **real public certificate** used to verify the IdP's signature, managed and rotated under a trusted process. The URLs and Entity ID above are placeholders and must be replaced with values provided by your IdP; exact property names and metadata import options may vary across Spring Boot versions. Before choosing an approach, check `Saml2RelyingPartyProperties` in your running Boot version.

Related configuration elements:

| Configuration | Meaning |
| --- | --- |
| SP `entityId` | Audience/SP identifier used by the IdP when issuing assertions |
| SP ACS URL | Destination where the IdP sends Responses |
| IdP `entity-id` | Expected IdP Issuer |
| IdP SSO URL/binding | Endpoint/binding receiving AuthnRequest |
| IdP verification certificate(s) | Verifies Response/Assertion signatures |
| SP signing credential | Signs AuthnRequest when required by the IdP |
| SP decryption credential | Decrypts EncryptedAssertion/EncryptedAttribute when encryption is used |

**Signing and verification are opposite sides:** the SP uses its own private key to sign requests; the SP uses the **IdP's public certificate** to verify responses. **Decryption** requires the SP's private key and cannot be performed with only a public certificate. Store private keys in a secure secret manager/keystore and never commit them to Git.

## 9. Signatures, Assertion Conditions, and Security Checks

Upon receiving `SAMLResponse`, the application must treat every byte arriving from the browser as **untrusted data**. The SAML authentication provider/OpenSAML must perform standard validations; the application must never Base64-decode a response itself and extract `NameID` to grant access.

Minimum checks:

1. **Signature and trust:** signatures on the Response or assertions per profile/policy must be valid and verified against the **registered IdP key**, not an arbitrary certificate carried in the request. If configuration requires signed assertions, never weaken that requirement just because integration is difficult.
2. **Issuer:** the Issuer in the message/assertion must match the IdP of the `RelyingPartyRegistration`, not be chosen by an arbitrary URL parameter.
3. **AudienceRestriction:** Audience must contain the Entity ID of the receiving SP. Never use an assertion issued for App A to log into App B.
4. **Destination/Recipient:** the response must target the exact ACS and SubjectConfirmationData must match the recipient; these values depend on public scheme/host/port.
5. **Time conditions:** `NotBefore`, `NotOnOrAfter`, and SubjectConfirmationData must be valid against the current time. Synchronize NTP and bound clock skew; do not expand tolerance indefinitely to mask clock errors.
6. **InResponseTo:** for SP-initiated SSO, correlate the response with a pending AuthnRequest; session/RelayState and request ID must be retained and correlated by design.
7. **SubjectConfirmation:** bearer confirmation, expiration, recipient, and related constraints must satisfy the Web Browser SSO Profile.
8. **Replay:** prevent a previously used response/assertion from being accepted again when required by policy/provider, tracking IDs over an appropriate window; this adds protection beyond signatures and time windows.
9. **XML processing:** prevent XML signature wrapping, XXE, weakly configured parsers, and accidentally reading an unsigned assertion. Use a vetted provider and keep libraries updated.
10. **Account status and permissions:** a valid assertion only proves what the IdP asserted; the SP must still decide which users/tenants may sign in, how sessions are maintained, and what authorities apply.

The exact validation sequence may vary across OpenSAML/Spring Security versions, but none of these security requirements may be dropped. In modern versions, Spring Security uses OpenSAML for validation, decryption, and principal construction.

**Do not confuse TLS with XML Signature:** HTTPS protects individual network hops. SAML signatures protect message integrity across browser transit; the two mechanisms complement each other.

## 10. Reading NameID, Attributes, and Assigning Authorities in the Application

After successful SSO, Spring Security establishes a `Saml2Authentication`. On standard 6.x APIs, `getPrincipal()` is a `Saml2AuthenticatedPrincipal`; you can read:

```java
String subject = samlPrincipal.getName();
Object email = samlPrincipal.getFirstAttribute("email");
var attributes = samlPrincipal.getAttributes();
String registrationId = samlPrincipal.getRelyingPartyRegistrationId();
```

The snippet above **illustrates** usage inside a method that already has `Saml2AuthenticatedPrincipal samlPrincipal`, not a standalone program. Actual attribute names (e.g., ADFS claim URIs) depend on IdP configuration and can be multi-valued; never assume `email` is always present. Email or `displayName` is insufficient as a stable account key if the IdP permits changes.

Choose a durable identity key by policy, such as `(IdP entityId, immutable subject ID)`; avoid linking two identities from different IdPs solely due to matching email. With multiple tenants, lock down the exact relying-party registration and issuer before mapping an account.

### Authentication vs. Authorization Are Distinct

- Successful `Saml2Authentication`: a valid SAML assertion exists under the SP's policy.
- `Authentication.getAuthorities()`: the Spring Security authority set; requires a dedicated mapping policy to yield `ROLE_FINANCE`, `ROLE_ADMIN`, etc.
- `hasRole("FINANCE")`: expects authority `ROLE_FINANCE` per the default role prefix; `hasAuthority("ROLE_FINANCE")` checks the exact string.

Example controller allowing access only when an **application-granted** role is present:

```java
package example.saml;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class FinanceController {

    @PreAuthorize("hasAuthority('ROLE_FINANCE')")
    @GetMapping("/finance/report")
    public String report() {
        return "Allowed";
    }
}
```

For `@PreAuthorize` to work, enable **`@EnableMethodSecurity`** in the application and invoke through a Spring-managed bean/proxy. **Do not** automatically grant `ROLE_FINANCE` just because the IdP sends `department=Finance`. Require an explicit mapping policy, verified allowlists/groups, and least-privilege testing; the group/authority mapping approach must match your provider and Spring Security version.

## 11. Default Endpoints and Common Misconceptions

| Endpoint / Component | Role | Notes |
| --- | --- | --- |
| `/saml2/authenticate/{registrationId}` | Initiates SP-initiated login, sends AuthnRequest to IdP | `registrationId` selects the configuration |
| `/login/saml2/sso/{registrationId}` | Assertion Consumer Service receiving SAML Response | Typically POST containing `SAMLResponse`; newer versions also support an ID-less form |
| `/saml2/metadata/{registrationId}` | Exports SP metadata for IdP import | Requires enabling `saml2Metadata(...)` on supported versions |
| `Saml2WebSsoAuthenticationRequestFilter` | Builds/sends AuthnRequest | Distinct from the filter receiving SAML Response |
| `Saml2WebSsoAuthenticationFilter` | Authenticates SAML Response via AuthenticationManager | Not itself an Identity Provider |
| `RelyingPartyRegistrationRepository` | Stores SP–IdP configuration pairs | May hold multiple registrations |
| `Saml2Authentication` | Authenticated object inside Spring Security | Not an IdP-issued bearer token to distribute freely |

Default ACS, SP Entity ID, and metadata URLs can all be customized; whenever you change an endpoint, update metadata and the corresponding registration at the IdP. `registrationId` is only a routing key, **not proof that the user belongs to that IdP**. Issuer and signature verification remain mandatory.

### Reverse Proxy / Public Base URL

Real deployments typically look like:

```text
Browser HTTPS -> Load Balancer/Ingress -> Spring Boot (internal HTTP)
Public baseUrl: https://app.example.org
Internal URL:   http://service:8080
```

If the SP constructs the ACS using the internal URL `http://service:8080`, the IdP may reject requests because Destination/Recipient differs from the public URL or uses the wrong scheme. Configure a trusted reverse proxy and appropriate Spring Boot/container forwarded headers, or explicitly set the SP Entity ID/ACS per registered metadata. Never let clients inject `X-Forwarded-Host`/`X-Forwarded-Proto` via bypass paths; the proxy must sanitize incoming headers.

When scaling across multiple instances, ensure `AuthnRequest` state, HTTP sessions, and correlation are not lost. Use sticky sessions or appropriate distributed session storage; never disable correlation checks just to work around an "InResponseTo mismatch" error.

### CSRF at the ACS

SAML HTTP-POST binding causes the browser to POST from the **IdP's origin** to the ACS. This differs from a user submitting a form while on the SP. Spring Security's SAML2 configuration handles this flow; if you customize CSRF matchers, specifically verify the ACS so valid POSTs are not blocked and CSRF is not unnecessarily disabled application-wide. Allowing POSTs to the ACS **does not relax signature, recipient, replay, or correlation checks**.

## 12. Layered Testing

### 12.1. Pre-Run SP/IdP Configuration Checks

1. Confirm `spring-security-saml2-service-provider` and all Spring Security dependencies share compatible versions.
2. IdP metadata has the correct `Entity ID`, SSO URL, signing certificate, and binding; the SP is registered at the IdP.
3. SP metadata advertises the exact **public** Entity ID, ACS, and verification/signing details.
4. The IdP can reach the HTTPS ACS, TLS certs are valid, and clocks on both sides are synchronized.
5. Confirm policies for signed AuthnRequest, signed SAML Response/Assertion, encryption, account identifiers, and SLO if applicable.
6. If multiple IdPs exist, verify `registrationId` routing and tenant/issuer isolation.

### 12.2. MockMvc Only Tests Authorization; It Does Not Simulate Signature Verification

You can construct a mock `Saml2Authentication` **in tests** and pass it into MockMvc to test controllers/authorization separately from SAML XML verification.

File `src/test/java/example/saml/CurrentUserTest.java`:

```java
package example.saml;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CurrentUserTest {

    @Autowired
    MockMvc mvc;

    @Test
    void principalCanReachProtectedEndpoint() throws Exception {
        var principal = new DefaultSaml2AuthenticatedPrincipal(
            "user-7392", Map.of()
        );
        var auth = new Saml2Authentication(
            principal,
            "<test-only/>",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );

        mvc.perform(get("/me").with(authentication(auth)))
            .andExpect(status().isOk())
            .andExpect(content().json("{\"nameId\":\"user-7392\"}"));
    }
}
```

`"<test-only/>"` above **is not a valid SAML Response**; this test bypasses the protocol layer to verify `SecurityContext`, controllers, and authorization once a principal exists. For the test to run, the Spring context still needs a `RelyingPartyRegistrationRepository`; provide valid test metadata fixtures on `classpath` or an appropriate test configuration. For Spring Security 7.1+, check deprecated principal types and replacement APIs.

### 12.3. Integration Testing with a Test IdP

Each path requires independent evidence:

| Scenario | Expected Result |
| --- | --- |
| Valid SP-initiated AuthnRequest; IdP logs user in and returns signed Response | SP verifies, creates session, `/me` returns identity |
| Assertion/response signature tampered with | SAML authentication rejected |
| IdP Issuer differs from trusted registration | Rejected |
| Audience does not match SP Entity ID | Rejected |
| `Recipient`/`Destination` does not match public ACS | Rejected |
| Assertion expired or not yet valid | Rejected |
| `InResponseTo` does not match pending request | Rejected under SP-initiated flow |
| Response/assertion replayed | No new session issued per anti-replay policy |
| Valid assertion but account/role disallowed | Blocked by application policy (typically 403 on forbidden resources) |
| Cookies/session lost during IdP redirect or instance switch | SSO fails to complete; investigate state/correlation cause |
| IdP signing key rotation | Metadata/verification key updated safely without relaxing validation |

Merely running `curl` against `/login/saml2/sso/company-idp` with hand-crafted XML **is not a successful integration test** if the XML is not signed by a trusted IdP. Use a test IdP (test Keycloak/ADFS instance or SAML sandbox) with a reachable public SP URL, and enable auditing while restricting sensitive data.

## 13. Version-Specific Configuration Notes

| Release Era | Key Points |
| --- | --- |
| **Spring Security 5.2+** | SAML 2.0 Login SP gradually introduced into Spring Security; APIs/capabilities evolved across 5.x releases |
| **Spring Security 5.7–5.8** | `WebSecurityConfigurerAdapter` deprecated in 5.7; migrate to `SecurityFilterChain` |
| **Spring Security 6.x / Boot 3.x** | Java 17+, `jakarta.servlet.*`; uses `saml2Login(Customizer)` and `RelyingPartyRegistrationRepository`; OpenSAML 4 or 5 depending on setup/version |
| **Spring Security 7.x / Boot 4.x** | Continues lambda/Customizer configuration; watch for OpenSAML provider changes, assertion/principal access APIs, and MFA/authority markers in 7.x |

Do not mix up Javadocs across versions: older articles reference `OpenSaml4AuthenticationProvider`, whereas newer documentation presents `OpenSaml5AuthenticationProvider` and `Saml2ResponseAssertionAccessor`. Class names used for custom converters/providers must match **your exact dependency tree**. The basic examples in this lesson choose standard SP configuration APIs to avoid tying directly to a specific provider vendor.

In Spring Security 7.1+, `Saml2AuthenticatedPrincipal`/`DefaultSaml2AuthenticatedPrincipal` are moving toward deprecation; follow the migration guide and replacement APIs for that version. Never alter `Authentication` or disable assertion checks merely to keep legacy mapper code compiling.

## 14. Common Errors and Root-Cause Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| 404 at `/saml2/authenticate/company-idp` | Wrong registrationId, missing registration, chain lacks `saml2Login` | Verify repository bean, exact ID, and chain matcher |
| IdP reports unknown SP / invalid audience | SP Entity ID mismatches registered metadata | Compare Entity ID **character-for-character** (scheme, path, case) |
| IdP rejects AuthnRequest | IdP requires signature while SP lacks signing key, wrong binding, Destination/issuer | Check metadata/signing policy and request binding |
| POST to ACS returns 403/404 | Wrong ACS path, CSRF matcher, security chain, proxy, or route authorization | Verify registered endpoint/ACS, filter chain, and forwarded headers |
| `InResponseTo` mismatch | Lost session/request repository, SameSite cookie, load balancing, or unsolicited response | Check session/cookie/RelayState/correlation; never skip validation |
| Assertion/Response signature validation failed | Wrong/expired IdP cert, stale metadata, tampered signature, XML mismatch | Check verification credentials and rotation |
| Assertion expired / not yet valid | Clock skew, NTP drift, or invalid assertion timestamps | Synchronize clocks; apply small bounded tolerance |
| Destination/Recipient mismatch | SP sees HTTP/internal host while IdP posts to HTTPS/public URL | Fix public baseUrl, ACS, and trusted proxy configuration |
| Login succeeds but `/finance/report` returns 403 | `ROLE_FINANCE` not mapped by policy | Inspect authorities and account/tenant mapping |
| Login succeeds but next request is unauthenticated | Lost session cookie, misconfigured reverse proxy/session storage | Inspect Set-Cookie, SameSite/Secure, host, session replication |
| Missing or wrong-type email claim | IdP omits attribute, uses different URI/claim name, or sends multiple values | Check IdP metadata/claim mapping; handle null and types |
| MockMvc passes while real SSO fails | MockMvc injects authenticated principal without testing XML signatures | Run end-to-end tests with a trusted IdP |

When debugging SAML, log only essential fields such as timestamp, registrationId, validation failure reason, and request correlation ID. Avoid writing raw `SAMLResponse`, XML assertions containing emails/groups, private keys, session cookies, or secret certificates into production logs.

## 15. Important Design Boundaries

- **SAML Authentication ≠ OAuth2 Access Token:** SAML Login creates a web login session at the SP; it does not produce JWTs for REST APIs and is not an OAuth 2.0 authorization server.
- **IdP supplies authentication facts; SP decides application permissions:** a claim like `groups=Admins` requires an explicit mapping/tenant policy before becoming `ROLE_ADMIN`.
- **Signed XML ≠ Encrypted XML:** signatures verify origin and integrity; encryption hides content. Do not disable TLS or signatures simply because encryption is enabled.
- **SP logout ≠ IdP Single Logout:** calling `/logout` usually clears only the local session; SAML Single Logout requires both parties to support dedicated messages, keys, and endpoints (`saml2Logout` where applicable).
- **NameID ≠ email:** NameID can be transient/persistent, opaque, and IdP-dependent. Organizations need explicit contracts for identity linking and account lifecycles.
- **Multiple tenants/IdPs require strict boundaries:** each `registrationId` represents a relying-party/asserting-party pair; validate actual issuer and audience to avoid cross-tenant mix-ups.
- **Never trust the browser or URL to verify an IdP:** trust comes from registration, verification keys, and provider validation.

Operational rule: let Spring Security/OpenSAML perform SAML verification and manage `Authentication`; register SP/IdP metadata accurately, keep public HTTPS URLs/ACS stable, manage certificate rotation and session correlation, and map authorities only after verifying both the assertion and the local account.

## 16. Official References

- Spring Security – SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.3 – Security/SAML Relying Party: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security 6.5 – `Saml2AuthenticatedPrincipal` API: https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
