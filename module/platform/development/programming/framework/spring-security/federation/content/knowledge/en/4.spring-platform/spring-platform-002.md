# Spring Security SAML2 Service Provider Scope and Identity Provider Implementation Boundaries

**Core problem:** When integrating enterprise SAML 2.0 login into a Spring Boot application, Spring Security helps the application act as a **Service Provider (SP, also called Relying Party – RP)**: redirecting users to the identity provider, receiving and validating the SAML result, and creating the application's Authentication and session. Spring Security **does not turn the application into a SAML 2.0 Identity Provider (IdP)** simply by enabling SAML2 Login configuration.

This lesson belongs to the Spring platform track, focusing on **Spring Security Servlet / Spring Boot 3.x, Spring Security 6.x, Java 17+**. The scope to master is **what Spring Security provides out of the box**, **what the IdP is responsible for**, and **the required integration boundary between the two**. Examples use Spring Boot 3.3.5 to keep syntax consistent; when applying newer versions, cross-check the documentation for that exact version.

## 1. Role Separation: SP/RP, IdP/AP, and the Browser

SAML 2.0 is a federation specification that exchanges user authentication and attribute statements using XML messages with security bindings. In **SAML Web Browser SSO**, the three main actors are:

- **Service Provider (SP) / Relying Party (RP):** the application providing resources to the user. The SP does not necessarily verify the user's password directly; instead, it **conditionally trusts** a configured IdP, validates the SAML Response/Assertion, and then decides whether to create an application session.
- **Identity Provider (IdP) / Asserting Party (AP):** the system that authenticates users according to organizational identity policies, such as passwords, MFA, account lockout, devices, and access rules. After authentication, it issues a SAML Assertion for the target SP with the appropriate signature, validity window, and audience.
- **Browser:** relays SAML requests and responses via HTTP Redirect/POST bindings. The browser **is not a trusted source** of identity: every SAML Response received from the browser must be verified by the SP.

A system may have **multiple SPs sharing one IdP**. Single Sign-On (SSO) can happen because the IdP still holds an active authentication session. That does **not** mean SPs share session cookies with the IdP or with each other.

| Question | SP – Spring Security Application | IdP – Identity Provider |
| --- | --- | --- |
| Who sends the user to the login page? | Initiates the login request and redirects the browser to the IdP's SSO endpoint | Serves the login interface when needed |
| Who verifies passwords, MFA, and account status? | Does not do this in a standard SAML SP flow | The IdP and its integrated authentication systems |
| Who creates the AuthnRequest? | The SP when using SP-initiated SSO | Receives, validates, and processes the AuthnRequest |
| Who creates the SAML Response/Assertion proving authentication? | **Receives and validates** | **Issues and signs** for authorized SPs |
| Who holds the key used to verify the IdP signature? | The SP must have matching trust configuration/certificate | The IdP manages the signing key and publishes verification info per trust procedures |
| Who creates the session for application A? | Application A's SP | The IdP only manages the IdP's own login session |
| Who publishes SP metadata? | Spring Security supports metadata generation for the SP | The IdP uses SP metadata to register/verify trust |
| Who publishes IdP metadata? | The SP consumes IdP metadata | The IdP publishes Identity Provider metadata |
| Who authorizes access to application A's APIs, URLs, and business logic? | **Application A**; may map SAML attributes into internal authorities | The IdP provides identity/attributes per policy, never replacing authorization inside A |
| Who performs Single Logout across systems? | The SP can participate in SAML SLO when properly configured | The IdP must support and coordinate SLO with SPs; does not automatically synchronize every session |

**Bottom line:** Spring Security helps an application **consume and verify identity assertions**; to **issue** identity assertions for other applications, you need a genuine IdP.

## 2. What Does Spring Security SAML2 Service Provider Support?

The **spring-security-saml2-service-provider** module is the SAML2 **Relying Party** integration for Servlet applications. Given a valid **RelyingPartyRegistration** and **saml2Login()** enabled, the framework provides infrastructure to:

1. **Initiate login redirect (SP-initiated):** when an unauthenticated user accesses a protected resource, Spring Security can create an AuthnRequest for the IdP and redirect the browser to the IdP.
2. **Receive SAMLResponse at the Assertion Consumer Service (ACS):** provides the filter endpoint for HTTP POST carrying the SAMLResponse parameter; no need to write a custom controller to decode XML.
3. **Validate Response/Assertion:** uses OpenSAML and configured validators to check signatures, issuer/registration, time conditions, recipient/destination, audience, correlation, and required constraints.
4. **Create application Authentication:** from a valid result, Spring Security builds a Saml2Authentication and principal; the application's session SecurityContext can be persisted via Spring Security Servlet mechanisms.
5. **Read SAML attributes:** the application can retrieve the NameID and attributes issued by the IdP, then decide how to link accounts and map authorities.
6. **Manage multiple partner configurations:** register one or more IdPs via **RelyingPartyRegistrationRepository**; each registration describes the trust relationship between an SP and an asserting party.
7. **Publish SP metadata:** when **saml2Metadata()** is enabled, Spring Security can publish the entityId, ACS, and relevant SP details for IdP configuration.
8. **Participate in SAML Single Logout (SLO) when integrated:** Spring Security supports RP-initiated and AP-initiated SLO on the SP side, but this requires IdP support, endpoints, signatures/certificates, and consistent configuration. This is **optional and conditional**, not an automatic result of saml2Login().

### Practical Boundaries of This Scope

- The framework **does not provision accounts** at the IdP, does not manage IdP passwords/MFA, and does not own the organization-wide SSO session.
- The framework **does not issue SAML Assertions on behalf of an IdP** in the default SP model, nor does it provide a full IdP SSO endpoint, IdP metadata, or IdP-side federation partner administration.
- You should not assume **every SAML profile/binding** is fully supported out of the box. The focus is standard **Web Browser SSO**; cases like **SAML Artifact, SOAP, ECP, AttributeQuery, or custom IdP requirements** may need custom design/extensions or a dedicated IdP/SP product.
- Mapping claims to business roles, managing local accounts, provisioning/deprovisioning, authorization decisions, and protecting internal APIs **remain the application's responsibility**.
- OpenSAML is a protocol/message-processing library; having OpenSAML in your dependencies **does not mean** you have a SAML Identity Provider.

## 3. SAML Web Browser SSO Flow: What Does the SP Do, What Does the IdP Do?

### Common SP-Initiated Login Flow

~~~text
[Browser]                     [Spring SP]                        [SAML IdP]
    |-- GET /private ---------->|                                   |
    |<-- Redirect AuthnRequest -|                                   |
    |-------------------- SAMLRequest/RelayState ------------------>|
    |<------------------- login/MFA page if needed -----------------|
    |-------------------- submit credentials ---------------------->|
    |<--------------- HTML form with SAMLResponse ------------------|
    |-- POST SAMLResponse ----->|                                   |
    |                           |-- validate Response/Assertion     |
    |                           |-- create Authentication/session   |
    |<--------- /private page --|                                   |
~~~

1. **SP:** the request has no Authentication so SAML login starts; it generates an **AuthnRequest** and redirects the browser to the IdP using the configured HTTP binding.
2. **IdP:** verifies that the SP is trusted and authenticates the user per internal policy; if the IdP already has a valid SSO session, it may skip asking for a password again.
3. **IdP:** creates a **Response** containing an **Assertion** targeted at the SP. Depending on partner configuration, the signature may be on the Response, the Assertion, or both; signature presence and placement must be verified by the SP according to policy.
4. **Browser:** POSTs the SAMLResponse data to the **SP's ACS** (for example /login/saml2/sso/corp).
5. **SP:** validates the SAML document, protocol bindings, trust, and security conditions; if valid, creates **Saml2Authentication**, stores it in SecurityContext, and continues the request.
6. **Application:** after login, it must still enforce authorization by URL, role, and business rules. Successful login does not imply access to every resource.

**SAMLRequest** and **SAMLResponse** travel through the browser, but the place where passwords are verified is the **IdP**; the place that trusts the outcome and authorizes application access is the **SP**. That is the most important functional boundary.

### How Does IdP-Initiated SSO Differ?

In an **IdP-initiated flow**, the user picks the application from the IdP portal; the IdP can send a SAMLResponse that did not originate from a specific SP AuthnRequest. Spring Security can handle certain scenarios based on registration/issuer, but lacking a correlated AuthnRequest introduces risks distinct from SP-initiated flows: you must validate **destination, recipient, audience, signature, timestamps, allowed partners, session state, and replay** by design. Do not enable/allow IdP-initiated SSO by default simply because the IdP has a "Launch App" button.

**RelayState** can help preserve navigation context, but it must never be treated as a trusted URL; you must guard against open redirects and restrict allowed values.

## 4. Essential SAML Components and SP Endpoints to Understand

| Term | Practical Meaning |
| --- | --- |
| **SP entityId** | Unique logical identifier of the SP in the trust relationship; often looks like a URL, though not necessarily fetchable. The IdP must register an exact match. |
| **IdP entityId (issuer)** | Identifier of the asserting party the SP expects; must match the value inside SAML messages. |
| **AuthnRequest** | Request sent by the SP to the IdP to authenticate a user; typically contains ID, issuer, and ACS/binding info. |
| **SAML Response** | Message returned by the IdP to the SP; may carry one or more Assertions depending on profile/protocol. |
| **Assertion** | Authentication/attribute statement containing Subject/NameID, conditions, audience, validity period, and optionally AuthnStatement. |
| **NameID** | Subject identifier issued by the IdP; formats include transient/persistent/email... Never blindly assume NameID is a permanent user key. |
| **Attributes** | Attributes such as email, department, group; names/formats/trustworthiness depend on the IdP and partner agreement. |
| **ACS (Assertion Consumer Service)** | **SP** endpoint that receives the SAMLResponse and performs validation; not the IdP SSO endpoint. |
| **SingleSignOnService** | **IdP** endpoint that receives AuthnRequest from the SP. |
| **SP metadata** | XML describing the SP, usually containing SPSSODescriptor, entityID, ACS, certificates, and bindings. |
| **IdP metadata** | XML describing the IdP, usually containing IDPSSODescriptor, entityID, SSO/SLO endpoints, and verification certificates. |
| **SLO (Single Logout)** | Coordinated logout protocol; does not happen automatically just because SSO login works. |

### Common Spring Security Servlet URLs

| URL | Role | Notes |
| --- | --- | --- |
| **/saml2/authenticate/{registrationId}** | SP creates an AuthnRequest and initiates SAML login to the corresponding partner. | For example **/saml2/authenticate/corp**; this is the SP endpoint to start login. |
| **/login/saml2/sso/{registrationId}** | SP's ACS that receives SAMLResponse (typically HTTP POST). | For example **/login/saml2/sso/corp**; must be registered accurately at the IdP. |
| **/saml2/metadata/{registrationId}** | Publishes **SP** metadata when **saml2Metadata()** is configured. | For example **/saml2/metadata/corp**; used solely for SP trust exchange. |
| **/saml2/metadata** | Metadata for applicable registrations, depending on repository support. | Inspect actual output in your environment. |
| **/saml2/service-provider-metadata/{registrationId}** | Compatible SP metadata path supported by Spring. | Not IdP metadata. |
| **/logout/saml2/slo** | SP's SAML logout message endpoint when SLO is configured. | Distinct from local **POST /logout**; triggering/handling depends on configuration. |

In Spring Security 6, the RP's **default entityId** is typically built from the pattern **{baseUrl}/saml2/service-provider-metadata/{registrationId}**; the **default ACS** is typically **{baseUrl}/login/saml2/sso/{registrationId}**. The **{baseUrl}** placeholder reflects the application URL seen by the client (scheme, host, port). When running behind a reverse proxy, ensure the public URL is correct; never mistakenly register localhost or internal HTTP as the production ACS.

The endpoints above belong to the **SP application**. They **do not** turn the application into an IdP with a centralized identity login page, IdP metadata, or an Assertion-issuing service for third parties.

## 5. Spring Security Architecture on the Service Provider Side

In a Servlet application, SecurityFilterChain wires components along the flow:

- **Saml2WebSsoAuthenticationRequestFilter** initiates and encodes the AuthnRequest before redirecting to the IdP.
- **Saml2WebSsoAuthenticationFilter** receives SAMLResponse at the ACS and submits an authentication request to AuthenticationManager.
- **OpenSAML authentication provider** validates the message/assertion per the Spring Security/OpenSAML version in the project; concrete implementation names may change across versions, so avoid coupling application code directly to the implementation unless customization is needed.
- **Saml2Authentication** provides the authenticated Authentication; **Saml2AuthenticatedPrincipal** provides the user's name and attributes in Spring Security 6.x.
- **RelyingPartyRegistration** holds both SP details (entityId, ACS, signing/decryption credentials) and IdP details (issuer, SSO/SLO endpoints, verification certificates, AuthnRequest sending policy). **RelyingPartyRegistrationRepository** looks up registrations by ID.
- **SecurityContext** represents the login state within the application. With standard web sessions, the application saves/restores Authentication via the Servlet session mechanism. The IdP session remains independent on the IdP side.

Key takeaway: **RelyingPartyRegistrationRepository is not an IdP user store**. It stores **partner and trust definitions**; it does not authenticate username/password, does not store accounts/MFA, and does not issue SAML Assertions.

## 6. Spring Boot 3.3.5, Java 17 Example: Implementing an SP

The example below creates a **real SP application** runnable with Java 17/Maven once connected to a **real IdP**. It **does not include an IdP**. The IdP must provide a metadata endpoint over HTTPS (or a trusted metadata file), and you must register the SP/ACS/entityId at the IdP before login will work.

### 6.1. Dependencies and Maven Repository

OpenSAML has artifacts downloaded from the Shibboleth repository; add the repository when the project uses **spring-security-saml2-service-provider**. Use the Spring Boot BOM/parent to manage Spring dependency versions.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>saml-sp-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
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

### 6.2. Declaring the Registration to the IdP

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}

server:
  port: 8080
~~~

**corp** is the **SP's internal registrationId**, not an account name. The **SAML_IDP_METADATA_URI** value must point to real SAML IdP metadata, such as **https://idp.example.org/saml/metadata** (this address is illustrative only). Spring Boot builds **RelyingPartyRegistrationRepository** from this configuration; metadata supplies the issuer, IdP SSO URL, and signature verification certificates. Never trust an unknown or unmanaged metadata URL.

The rollout order may require coordination with the IdP admin: prepare the SP's public entityId/ACS, register at the IdP, configure the IdP metadata, and start the SP. If the IdP requires **signed AuthnRequests**, **assertion encryption**, or specific algorithms/bindings, you must add the corresponding credentials and registration settings; this minimal example does not actively configure SP signing/decryption keys.

### 6.3. Application, Filter Chain, and Controller

**src/main/java/com/example/samlsp/SamlSpDemoApplication.java**

~~~java
package com.example.samlsp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSpDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samlsp/SecurityConfig.java**

~~~java
package com.example.samlsp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**src/main/java/com/example/samlsp/DemoController.java**

~~~java
package com.example.samlsp;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SAML SP public";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID: " + principal.getName();
    }
}
~~~

**Meaning:** URI **/** requires no login, **/me** requires SAML authentication; **saml2Login()** enables the SP side to accept Assertions and log in, while **saml2Metadata()** publishes SP metadata. No code was written to accept passwords or sign Assertions for third parties – because those two tasks belong to the IdP.

### 6.4. Running and Predictable Outcomes

Set the **SAML_IDP_METADATA_URI** environment variable to a valid IdP metadata URL reachable from the server; then in the directory containing **pom.xml** run:

~~~bash
mvn spring-boot:run
~~~

- **GET http://localhost:8080/** returns the exact text: **SAML SP public**.
- **GET http://localhost:8080/saml2/metadata/corp** returns **SP metadata XML** once the registration is ready and the endpoint is permitted; this is the SP's metadata, not the IdP's. In some configurations, you may need to explicitly permit public GET access to metadata via authorization rules or dedicated access configuration.
- **GET http://localhost:8080/saml2/authenticate/corp** initiates the SP-initiated SSO flow toward the IdP. It does not display an IdP login screen inside the Spring application itself.
- **GET http://localhost:8080/me** without a session triggers a login challenge; once the IdP returns a valid Assertion, the endpoint returns a string of the form **NameID: <value issued by IdP>**. You cannot claim a fixed NameID value because it depends on the account, NameID format, and IdP policy.

For the demo to complete login, **the SP entityId and ACS must be registered at the IdP**, the trust certificate must be valid, and the callback address must be exact. If the configured IdP metadata is just a dummy URL, startup/login will fail; that is the expected consequence because this application **is only an SP**.

**Production:** configure the public HTTPS URL on your proxy/server, align metadata/domains, and register the exact ACS. Do not use HTTP localhost endpoints in production configs; do not commit secrets/private keys into files.

## 7. Metadata, Certificates, and Establishing Trust

SAML federation is not simply entering an IdP "login URL". Both sides need a **trust contract** consisting of matching facts.

### What the SP Provides to the IdP

- **SP entityId** – logical identifier of the application, exact down to the character, typically stable across upgrades.
- **ACS URL and binding** – where the IdP sends the Response, e.g., HTTPS POST to /login/saml2/sso/corp.
- **SP certificate** – if the IdP requires the SP to sign AuthnRequests or encrypt Assertions for the SP; the private key stays on the SP and must be protected.
- **SLO information** – if both sides integrate federated logout.
- **SP metadata** – XML document containing SPSSODescriptor; published via **saml2Metadata()** and used for onboarding.

### What the IdP Provides to the SP

- **IdP entityId** and exact **SSO endpoint/binding**.
- **X.509 public certificate** (or trusted metadata containing the certificate) so the SP can verify SAML signatures.
- **Signing rules:** whether the IdP signs the Response, the Assertion, or both; agreed-upon algorithms and trust policy.
- **Subject/NameID/Attribute rules:** which identifier is stable, whether email may be used as an account-linking key, and role/group attribute names.
- **Logout endpoint/certificate**, if the IdP supports SLO.
- **MFA, session, and certificate rollover policies**, managed at the IdP.

**Never reverse the roles:** a certificate published by the IdP for **SP verification** does not turn the SP into an IdP; a certificate used by the **SP to sign AuthnRequests** does not grant the SP authority to sign Assertions like an IdP. The two key pairs serve two distinct roles.

**Metadata is a trust configuration document, not automatically safe just because a URL exists.** With dynamic metadata, you must trust the source and transport, have a metadata signature verification process if required, restrict update permissions, and support rotation. If the IdP certificate changes while the SP still holds old trust data, login will fail; do not "fix" it by turning off signature validation.

## 8. Security Conditions the SP Must Validate

Because SAMLResponse travels through the browser, it can be tampered with, replayed, substituted, or sent to the wrong endpoint. Spring Security/OpenSAML SAML processing supports validation per configuration; implementation teams must still understand and test the key security conditions:

1. **Signature and trust:** only accept signatures using permitted algorithms/policies and the exact trusted certificate of a registered IdP. Never skip signatures or merely Base64/XML-parse the response to extract an email.
2. **Issuer/registration:** the issuing Identity Provider must belong to an expected partner, never accepting arbitrary issuers. When supporting multiple IdPs, resolve the exact registration from request/correlation/issuer using safe logic.
3. **AudienceRestriction:** the Assertion must target the **current SP's** entityId. An Assertion issued for SP B must not log a user into SP A.
4. **Destination and Recipient:** the message/SubjectConfirmationData must target a valid ACS of the SP, especially behind a reverse proxy.
5. **InResponseTo and initial request:** for SP-initiated login, the Response must match a previously issued AuthnRequest when required by profile/policy. Store and protect request state so unsolicited foreign responses are rejected.
6. **Time conditions:** validate NotBefore/NotOnOrAfter, SubjectConfirmationData, and response/statement timestamps per spec. Synchronize clocks via NTP; only allow small, justified clock skew.
7. **Replay protection:** reject replays of the same Assertion/Response when the profile requires replay protection. In multi-instance systems, replay/correlation state storage must fit the architecture.
8. **XML wrapping/XXE/processing:** use a maintained and securely configured SAML processor; never write raw DOM parsers/validators to "simplify" things.
9. **Session and CSRF:** after valid authentication, session cookies need appropriate Secure/HttpOnly/SameSite flags and fixation protection. Protect business actions with CSRF; never disable global CSRF protection just to accept SAML POSTs.
10. **Privacy:** SAML Assertions/attributes may contain personal data. Do not log SAMLResponse, private keys, cookies, or unsanitized full XML in production.

With an IdP-initiated flow that has no InResponseTo to correlate with an initiating request, **never skip the remaining checks**. A dedicated architectural decision and security test plan are required if the organization demands that model.

## 9. What Features Must a Real Identity Provider Implement?

If the product requirement is **"Build a Spring system that issues SAML logins for multiple enterprise applications"**, that is an **Identity Provider** design, fundamentally different from the Service Provider configuration above.

An IdP typically needs:

1. **Identity/accounts:** user directory or LDAP/AD integration, identifier rules, authentication, account lockout, credential management, password changes, recovery, and account lifecycle.
2. **Authentication policies:** MFA, risk-based authentication, anomaly detection, IdP SSO session, idle/absolute timeouts, multi-device session policies, reauthentication.
3. **SAML protocol server:** accept and validate AuthnRequests from SPs, track trusted SPs, support published bindings, and issue proper SAML Responses/Assertions per partner.
4. **Signing and keys:** manage IdP private keys, public certificates, key rollover, signing algorithms, HSM/KMS protection if needed, and metadata provenance/trust control.
5. **Enforcing Assertion conditions:** issuer, Subject/NameID, AudienceRestriction, Destination/Recipient, validity window, AuthnStatement, SessionIndex, response-to-request correlation, and replay prevention.
6. **SAML IdP metadata:** publish IDPSSODescriptor, SingleSignOnService, SingleLogoutService (if supported), KeyDescriptor with signing certificate; distribute metadata updates to SPs per agreed process.
7. **Multi-SP federation management:** onboarding, ACS/EntityID approval, attribute release policy, NameID mapping, tenancy, consent/privacy, and auditing.
8. **SLO/session tracking:** track SessionIndex, logout requests/responses, handle failures/partial logouts, and notify other SPs per support contract.
9. **Operations, monitoring, compliance:** HA, secure logging, key rotation, certificate expiry monitoring, authentication auditing, response signing, and SP compatibility testing.

**No saml2Login() configuration automatically creates this feature set.** Spring MVC, Spring Security, OpenSAML, or Spring Boot can serve as technical building blocks to **build a custom IdP**, but then you must design and test the protocol, keys, security, business logic, and operations yourself; that is a full Identity Provider development project, no longer a task of enabling SAML2 Service Provider.

### Architecture Choices When the Organization Needs an IdP

| Need | Appropriate Approach |
| --- | --- |
| Spring app needs employees to log in with corporate accounts | Use **Spring Security SAML2 SP** to federate with an existing IdP. |
| Organization needs an SSO portal for multiple SAML applications | Use a **dedicated IdP product** (e.g., Keycloak with SAML, Shibboleth IdP, or Microsoft Entra ID depending on deployment capabilities), managing SPs, authentication, and metadata there. |
| Need to broker multiple identity sources and bridge SAML and OIDC | Consider an **identity broker/gateway** supporting both protocols; Spring apps can act as a SAML SP or OIDC client downstream. |
| Want to issue Assertions from a Spring service itself | Must scope this as **building a custom IdP** with full threat model, protocol, key lifecycle, HA, and security testing; do not misuse SP config as a mock IdP. |
| Already have Spring Authorization Server and want to add a SAML IdP | Spring Authorization Server primarily supports **OAuth2/OIDC Authorization Server**; it **does not automatically become a SAML2 IdP** by enabling SAML login or an OAuth2/OIDC server. A component that genuinely supports the SAML IdP role is required. |

**Distinguish logging in from providing identity:** a Spring application can simultaneously **log in to an external IdP** and **issue OAuth2/OIDC tokens** if you also build an authorization server. Even then, that does not automatically make it an IdP issuing SAML Assertions under SAML 2.0.

## 10. Session and Single Logout: Boundary of Responsibilities

After a successful login, at least two sessions may exist:

- **IdP session:** used by the IdP to recognize the user on subsequent SSO visits, with its own timeout, MFA, and logout policies.
- **SP local session:** the Spring application manages its own SecurityContext/session cookie, timeout, and authorization.

When the **SP session expires** while the IdP session is still alive, the SP may initiate a new SAML flow; the IdP may authenticate without prompting for a password. When the **IdP session expires** while the SP session is still alive, the application may continue serving requests until the local session expires or it receives a logout/revocation event via another mechanism.

**Local logout** (typically via POST /logout with valid CSRF) only clears the local session as configured. For federated logout, Spring Security provides **saml2Logout()** on the SP side, but it requires the IdP to support **SingleLogoutService**, logout message signing/verification configuration, endpoints, and session/NameID correlation. In an appropriate setup, RP-initiated logout can send a LogoutRequest; AP-initiated logout can send a LogoutRequest to the SP so the SP responds after invalidating the local session.

Illustrative configuration snippet **to add into an existing SecurityConfig** when the IdP genuinely supports SLO:

~~~java
// Illustrative addition inside an existing HttpSecurity configuration chain.
// Requires adding SLO endpoints and signing credentials to the registration.
http.saml2Logout(Customizer.withDefaults());
~~~

This snippet **is not a standalone runnable program**, and does not trigger system-wide logout just by adding one line. You must configure signing certificates/private keys, SLO locations, IdP trust, and test RP-/AP-initiated SLO. Instant logout across all devices and all SPs cannot be guaranteed if partners do not support it.

## 11. Practice Scenario and Acceptance Checklist

A proper SP-scoped verification exercise should use a **real test IdP** or sandbox environment, one Spring SP, and metadata/keys issued by the IdP. Never hand-craft fake SAMLResponses just to "trick" validation.

**Functional verification flow:**

1. **SP metadata:** call /saml2/metadata/corp and verify entityId, HTTPS ACS, binding, and SP certificate if used. The IdP admin must register these exact values.
2. **SP-initiated SSO:** open /me without a local session; observe redirect to IdP; authenticate at IdP; IdP POSTs SAMLResponse to ACS; SP creates Authentication; /me displays the NameID from the IdP.
3. **SSO across two SPs:** log in to SP A then open SP B using the same IdP; B still starts its own flow, and the IdP may skip the password prompt if the IdP session is active.
4. **Invalid trust:** test IdP metadata with a mismatched issuer/certificate in a test environment, verifying the SP rejects login and creates no Authentication.
5. **Wrong ACS/audience:** test mismatched Destination/Recipient/AudienceRestriction between the two sides; confirm failure instead of allowing login.
6. **Clock skew:** simulate clock drift or an expired Assertion in sandbox; verify diagnosable error messages and never disable validation to "fix" it.
7. **Certificate rollover:** rehearse receiving metadata with a new certificate per procedure, ensuring zero trust gaps and no need to disable signature checks.
8. **Logout:** distinguish local logout from SAML SLO; verify to what extent SP and IdP sessions disappear, and whether other SPs receive logout.
9. **Reverse proxy:** verify actual entityId/ACS use the public HTTPS hostname, without leaking HTTP localhost or internal ports.
10. **Authorization:** after SAML authentication, a user lacking the required role must still be blocked on sensitive business endpoints.

### Common Errors

| Symptom | Possible Cause / Inspection Path |
| --- | --- |
| Cannot load IdP metadata on startup | Wrong metadata URI, IdP not running, TLS/trust/network error, incompatible trust configuration. |
| IdP reports unknown SP or invalid audience | SP entityId differs from the value registered at the IdP. |
| IdP reports ACS/Reply URL mismatch | Spring's ACS differs from the URL allowed at the IdP; proxy alters scheme/host/port. |
| POST callback fails due to signature verification | Stale/wrong IdP certificate, missing signature required by policy, trust mismatch, or modified message. |
| Authentication fails due to timestamps | NTP/clock skew, expired NotBefore/NotOnOrAfter or SubjectConfirmationData. |
| Logged in successfully but lacks access | SAML authentication succeeded but business roles/authorities are unmapped; check SP-side authorization. |
| User logs out of SP but immediately gets back in | IdP session is still active; SP local logout does not equal IdP logout. |
| Trying to export IdP metadata from /saml2/metadata | Wrong role: that endpoint exports **SP metadata**, not **IDPSSODescriptor**. |
| Added spring-security-saml2-service-provider but has no user admin UI | By design: this dependency does not build an IdP/identity store. |

## 12. Self-Check Questions

**Question 1.** An application enables saml2Login() and exposes /saml2/metadata/corp. Is it a SAML IdP yet?  
**Answer:** No. The application is an **SP**; the exported metadata is **SP metadata**, whereas an IdP must receive AuthnRequests, authenticate users, and issue signed Assertions.

**Question 2.** Who owns the /login/saml2/sso/corp endpoint and who owns SingleSignOnService in IdP metadata?  
**Answer:** The ACS **/login/saml2/sso/corp belongs to the Spring SP**; SingleSignOnService belongs to the **IdP**, receiving AuthnRequests from the SP.

**Question 3.** Why does a successful SAML login not guarantee access to /admin on the SP?  
**Answer:** The Assertion proves identity/attributes under trust. **Authorization** to /admin is still decided by the SP; you must map roles/authorities and enforce internal policies.

**Question 4.** Can you handle an IdP signature key change by disabling signature validation when errors occur?  
**Answer:** No. You must check IdP metadata, certificates, rotation, issuer, and policy; disabling verification breaks the trust boundary.

**Question 5.** If a product needs a login portal, MFA, and SAML Assertions for 20 SPs, which module should take that responsibility?  
**Answer:** That is an **Identity Provider** requirement. Choose a dedicated IdP/broker or a full custom IdP project; the **spring-security-saml2-service-provider** module only handles the SP role.

## 13. Official References

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP model, AuthnRequest, ACS, RelyingPartyRegistration, and login flow.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validating and customizing Assertion/Authentication processing.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): publishing SP metadata.
- [Spring Security – SAML 2.0 Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP-/AP-initiated SLO and configuration conditions.
- [Spring Boot – SAML 2.0](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html#web.security.saml2): SP integration and Shibboleth repository. When deploying Boot 3.3.5, check the corresponding 3.3.x documentation for version differences.

**Final reminder:** Spring Security solves the problem of **a Spring application trusting an IdP to log in as a SAML2 SP**. **Centralized authentication, identity management, and issuing SAML Assertions as an IdP** require a different system/solution and a clear trust contract with every SP.
