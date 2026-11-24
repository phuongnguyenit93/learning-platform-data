# Configuring spring.security.saml2.relyingparty.registration in Spring Boot

> **Module:** Spring Security – federation · **Topic:** SAML2 Registration. This lesson explains how to declare the relationship between a **Service Provider (SP)/Relying Party (RP)**—a Spring Boot application—and an **Identity Provider (IdP)/Asserting Party** using the `spring.security.saml2.relyingparty.registration` configuration branch, from a minimal IdP-metadata setup to manual configuration, X.509 certificates, multiple IdPs, and login verification.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Read the entire `spring.security.saml2.relyingparty.registration.<registrationId>` path in `application.yml` and explain every level.
2. Distinguish **SP entity ID**, **IdP entity ID**, **ACS URL**, **IdP SSO URL**, **metadata URL**, **registrationId**, and **X.509 certificate**.
3. Choose appropriately between two declaration styles: **based on IdP metadata** or **declaring IdP fields manually**.
4. Configure the IdP **verification credential**, SP **signing credential**, and SP **decryption credential** along the correct trust direction.
5. Understand the roles of Spring Boot auto-configuration, `RelyingPartyRegistrationRepository`, `SecurityFilterChain`, and `saml2Login()`.
6. Build a Java 17 + Spring Boot 3.3.x application with SAML2 login and SP metadata endpoints; integrate once a real IdP is available.
7. Configure multiple partners, ensure accurate `registrationId`, ACS, and entity ID behind a reverse proxy, and diagnose common errors without relaxing security checks.

**Scope:** The examples cover a **Spring MVC/Servlet SP**. The application does not issue assertions and does not act as an IdP. Property names reference **Spring Boot 3.3.x / Spring Security 6.x**; for other versions, check the corresponding reference documentation because Java APIs and some property names have changed over time.

## 2. Problem Statement: An SP Must Know Which IdP to Trust

Suppose `https://orders.example.org` lets employees of Company A log in through A's IdP. The application must know:

- **Who is the IdP?** Entity ID and verification certificate for SAML Response/Assertion signatures.
- **Where to send AuthnRequest?** The IdP's SSO service URL and HTTP binding (Redirect or POST).
- **Who does the SP claim to be?** The SP entity ID that the IdP uses as its audience/trust entry.
- **Where should the IdP return results?** The SP's Assertion Consumer Service (ACS URL).
- **Are signed AuthnRequests or encrypted assertions required?** If so, the SP needs the appropriate private key and certificate.
- **Which configuration belongs to partner A?** Each SP–IdP pair is identified by a `registrationId`.

Spring Boot organizes this information into a configuration tree:

~~~text
spring
└── security
    └── saml2
        └── relyingparty
            └── registration
                ├── partner-a                  <-- registrationId (name chosen by SP)
                │   ├── entity-id              <-- SP entity ID
                │   ├── acs                    <-- where SP receives SAMLResponse
                │   ├── signing                <-- SP keys used for signing
                │   ├── decryption             <-- SP keys used for decryption
                │   ├── singlelogout           <-- SP SLO options
                │   └── assertingparty
                │       ├── metadata-uri       <-- IdP-side metadata
                │       ├── entity-id          <-- IdP entity ID
                │       ├── sso-url            <-- IdP SSO endpoint
                │       ├── verification       <-- IdP public certificate
                │       └── singlelogout       <-- IdP SLO options
                └── partner-b                  <-- second registration
                    └── assertingparty...
~~~

Sub-branches are used **depending on requirements and configuration approach**; not all need to be entered when metadata supplies complete information and the IdP requires no SP-owned keys.

### Roles and Identifiers

| Name | Meaning | Illustrative Example |
| --- | --- | --- |
| `registrationId` | Internal key for Spring to identify **one RP–IdP pair**; appears in default URLs. | `partner-a` |
| **SP/RP entity ID** | Protocol identity the **application** registers with the IdP; used by the IdP as audience when issuing assertions. | `https://orders.example.org/saml2/service-provider-metadata/partner-a` |
| **IdP/Asserting Party entity ID** | Protocol identity of the assertion-issuing partner; the SP must verify the issuer matches a trusted IdP. | `https://login.partner-a.example.org/saml/metadata` |
| **ACS URL** | SP HTTP URL receiving `SAMLResponse` from the IdP. | `https://orders.example.org/login/saml2/sso/partner-a` |
| **IdP SSO URL** | IdP endpoint receiving `AuthnRequest` requests. | `https://login.partner-a.example.org/sso` |
| **IdP metadata URI** | Location to load SAML metadata XML containing IdP entity ID, services, bindings, and certificates. | `https://login.partner-a.example.org/metadata.xml` |
| **IdP verification certificate** | **IdP public** certificate trusted by the SP to verify signatures. | `classpath:certs/partner-a-idp.crt` |
| **SP signing key/certificate** | **SP** private key/cert used to sign outbound messages when required by protocol/IdP. | `file:/run/secrets/sp-sign.key` |
| **SP decryption key/certificate** | **SP** private key/cert to decrypt SAML data sent to the SP if encrypted by the IdP. | `file:/run/secrets/sp-decrypt.key` |

These are distinct types of identifiers. **Registration ID is not the SAML entity ID; metadata URL does not necessarily equal SSO URL; ACS URL is not an OIDC IdP callback.** The `example.org` URLs are illustrative placeholders only.

## 3. Prerequisites for the Configuration to Work

A SAML2-enabled SP needs **three aligned parties**: Spring Boot, the IdP, and network infrastructure.

1. The application has the `spring-security-saml2-service-provider` dependency and a `SecurityFilterChain` enabling `saml2Login`.
2. An administrator has registered the SP on a real IdP with the SP entity ID, ACS URL, bindings, SP signing certificate if required, and NameID and assertion signing/encryption policies.
3. The SP knows trusted IdP metadata or endpoints/public certificates; clocks and certificates are valid, and DNS/TLS for metadata/SSO work.
4. External URLs match where real browsers access the app; behind a reverse proxy, forwarded headers are handled in a controlled manner.
5. Java and Gradle environments are compatible; subsequent examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.x**, Servlet application.

SAML2 is a cross-system federation protocol. **Adding YAML alone does not create an IdP, real certificates, or linked accounts**. Thus standalone build examples can compile, while successful login depends on a registered IdP and real environment data.

## 4. Minimal Configuration: Loading Metadata from the IdP

**Prefer IdP metadata** when the partner provides a trusted metadata source in a format Spring Security can parse.

In `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Once the environment variable `PARTNER_A_IDP_METADATA_URI` points to a real metadata address, Spring Boot can construct the registration from that metadata: IdP entity ID, SSO service location/binding, and verifying certificates. The SP still needs to be registered **on the IdP side** with the proper entity ID and ACS. If metadata cannot be loaded, contains unsuitable multi-configurations, or the IdP expects a different profile, adjust the configuration or use custom Java registration.

**Never pick a metadata URI from a user query parameter.** The application should load only from an IdP source pre-defined in the trust contract; fetch metadata over HTTPS and verify source/target trustworthiness, especially with signed metadata and certificate rotation.

Metadata configuration is **information about the IdP**, not proof that every response from that URL is valid. At login time, the SP must still verify signatures on the proper elements, issuer, audience, recipient/ACS, status, validity window, and request correlation per SAML profile.

### 4.1. Important Default URLs

When using `registrationId=partner-a`, typical Spring Security Servlet paths are:

| Function | Default Path | Effect |
| --- | --- | --- |
| Start SP-initiated SSO | `GET /saml2/authenticate/partner-a` | Generates AuthnRequest, redirects browser to IdP. |
| Receive response (ACS) | `POST /login/saml2/sso/partner-a` | Processes form carrying `SAMLResponse` from IdP. |
| Export SP metadata | `GET /saml2/metadata/partner-a` | Serves RP metadata if `saml2Metadata()` is enabled. |
| Compatible metadata path | `GET /saml2/service-provider-metadata/partner-a` | Alternative metadata endpoint supported by Spring Security. |
| Spring Security login page | `GET /login` | Can offer login options when filters/registrations are configured. |

These paths are **application paths**; actual URLs include scheme, host, port, reverse proxy, and context path. The ACS must also match the IdP entry, not merely an internal container path.

### 4.2. Defaults for SP Entity ID and ACS

Spring Security constructs the SP entity ID by default as:

~~~text
{baseUrl}/saml2/service-provider-metadata/{registrationId}
~~~

The default ACS is typically:

~~~text
{baseUrl}/login/saml2/sso/{registrationId}
~~~

With base URL `https://orders.example.org` and registration `partner-a`, the SP entity ID is `https://orders.example.org/saml2/service-provider-metadata/partner-a`; the ACS is `https://orders.example.org/login/saml2/sso/partner-a`.

**Entity ID is a logical entity identifier** that may resemble a URL, but should not automatically be treated as an endpoint the browser calls. **ACS is a real URL that must receive HTTP requests**, and `Destination`/`Recipient` in responses must bind accurately to that endpoint. In practice, IdP policy may mandate a fixed SP entity ID URI different from the metadata URL.

## 5. Explicit Configuration to Match the SP–IdP Contract

When you need to pin SP entity ID and ACS rather than relying on dynamic base URLs, declare them explicitly:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

`{baseUrl}` and `{registrationId}` are **Spring Security URI templates**, not shell placeholders; they expand per request and registration. `${PARTNER_A_IDP_METADATA_URI}` after symbol substitution is a **Spring property placeholder reading an environment variable**, distinct from URI templates. For example, in systems requiring a **fixed** entity ID regardless of host, replace `entity-id` with the SP value registered at the IdP and set `acs` to the public endpoint. Do not change these arbitrarily after integration because the IdP will issue assertions for the old audience/callback.

Meaning:

| Branch in Registration | Owning Side | When to Customize? |
| --- | --- | --- |
| `entity-id` | SP | When the IdP requires a specific SP entity ID rather than the default. |
| `acs.location` | SP | When the ACS uses a fixed path/host or differs from the default path. |
| `acs.binding` | SP | When specifying POST/Binding matching IdP and filter configuration. |
| `assertingparty.metadata-uri` | IdP | When the IdP publishes trusted metadata. |
| `signing.credentials` | SP | When the SP must sign AuthnRequest or SLO messages. |
| `decryption.credentials` | SP | When the IdP encrypts assertions/NameID with the SP's public key. |
| `singlelogout` | SP and/or IdP | When both sides agree on SAML Single Logout and configure endpoints/bindings. |

If changing ACS to use a custom URL, changing YAML alone **may not be enough**: the HTTP filter must accept requests at the new URL. When deeply customizing ACS paths, adjust `Saml2WebSsoAuthenticationFilter`/`SecurityFilterChain` accordingly rather than only changing metadata.

## 6. Manual Configuration Without a Metadata URI

Not every IdP provides a metadata URL usable in all environments. Spring Boot 3.3.x allows specifying IdP fields directly:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "https://orders.example.org/saml2/sp/partner-a"
            acs:
              location: "https://orders.example.org/login/saml2/sso/partner-a"
              binding: POST
            assertingparty:
              entity-id: "https://login.partner-a.example.org/saml"
              sso-url: "https://login.partner-a.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/partner-a-idp.crt"
~~~

These are **simulated values** for learning the structure; replace them with real data provided and verified by the IdP. `classpath:certs/partner-a-idp.crt` requires the file to exist at `src/main/resources/certs/partner-a-idp.crt` (this is the **IdP's public certificate**, not a private key).

Key points to watch:

- **`assertingparty.entity-id`** is the issuer/EntityID that responses/assertions from the IdP must match. Never put the SP entity ID into this field.
- **`assertingparty.sso-url`** points to the **IdP's** Single Sign-On Service endpoint. It differs from metadata URI and ACS.
- **`assertingparty.verification.credentials[*].certificate-location`** is the public certificate pinned/trusted by the SP; never treat an arbitrary certificate embedded inside a SAMLResponse as a trust anchor.
- Whether the IdP uses HTTP-Redirect or HTTP-POST for AuthnRequest, coordinate the exact binding defined by metadata/registration. Do not assume every IdP uses only Redirect.
- **Manual configuration requires a certificate rotation procedure**. When the IdP changes its signing key while the SP still pins the old cert, login becomes invalid; never resolve this by disabling signature validation.

In Spring Boot 3.3, the manual configuration reference in that version's documentation uses `sso-url` under `assertingparty`; examples in some other Spring Security generation references show `singlesignon.url`. When migrating configs across versions, check the exact Spring Boot version and `Saml2RelyingPartyProperties` class running before copying properties.

### 6.1. Equivalent Properties and YAML

These two examples have identical meaning for Spring Boot property binding:

~~~properties
spring.security.saml2.relyingparty.registration.partner-a.assertingparty.entity-id=https://login.partner-a.example.org/saml
spring.security.saml2.relyingparty.registration.partner-a.assertingparty.sso-url=https://login.partner-a.example.org/sso
spring.security.saml2.relyingparty.registration.partner-a.assertingparty.verification.credentials[0].certificate-location=classpath:certs/partner-a-idp.crt
~~~

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              entity-id: "https://login.partner-a.example.org/saml"
              sso-url: "https://login.partner-a.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/partner-a-idp.crt"
~~~

The `credentials` entry is a **list**, because multiple valid certificates may be needed during key rotation. Do not turn it into a single string with multiple paths hoping the binder parses it as desired.

## 7. Three Commonly Confused Credential Types

SAML uses X.509 certificates and corresponding keys for signing/verification or encryption/decryption. Separate clearly **who holds the private key**:

| Task | Spring Boot 3.3 Field | Whose Key/Cert Is It? | Purpose |
| --- | --- | --- | --- |
| SP verifies response/assertion signature | `assertingparty.verification.credentials` | **IdP's public certificate** | Trust signatures from the registered IdP. |
| SP signs AuthnRequest/SLO | `signing.credentials` | **SP's private key and certificate** | IdP verifies outbound messages from SP when required. |
| SP decrypts encrypted assertion/NameID | `decryption.credentials` | **SP's private key and certificate** | Unwrap data encrypted specifically for the SP. |

### 7.1. When the IdP Requires Signed AuthnRequests

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/secrets/sp-signing.crt"
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

- `private-key-location` points to the **SP's private key**. Keep it in a secrets store; never commit keys to Git, container images, release artifacts, or documentation.
- `certificate-location` is the matching certificate trusted by the IdP, typically provided via SP metadata or manual registration.
- Having signing credentials **does not mean every message type is automatically signed in every situation**. Spring Security decides whether to generate signatures based on configuration and protocol/IdP needs; verify against real requests and partner signing requirements.

### 7.2. When the IdP Sends EncryptedAssertion

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/sp-decrypt.key"
                  certificate-location: "file:/run/secrets/sp-decrypt.crt"
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

The IdP uses the SP's **public key** to encrypt; the SP uses its **private key** to decrypt. **Successful decryption does not replace signature verification** of the assertion/response. The partner's encryption configuration must match algorithms, key usage, the certificate published for the SP, and library capabilities.

### 7.3. Combining Signing and Decryption

A deployment may use the same key pair if policy permits, though in practice risk and separate key-rotation lifecycles should be evaluated per purpose. A combined example **has the following structure**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/secrets/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/sp-decrypt.key"
                  certificate-location: "file:/run/secrets/sp-decrypt.crt"
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Enable only the branches actually needed. Use HTTPS, planned certificate rotation, and fail-safe error handling. Adding keys to YAML does not automatically inform the IdP of the matching public certificates: **registering SP metadata/certificates at the IdP** remains mandatory.

## 8. Complete Spring Boot Application Example (Java 17+)

The example aims for a program **that compiles and runs once a real IdP configuration is supplied**. It demonstrates the Spring Security SAML2 surface rather than writing a custom XML parser or simulating SAML signatures.

### 8.1. Project Structure

~~~text
saml-registration-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlregistration/
    │   ├── SamlRegistrationApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── resources/
        └── application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-registration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // Repository hosting some OpenSAML dependencies of the Shibboleth ecosystem.
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Purpose of the dependencies:

- `spring-boot-starter-web`: Servlet runtime and REST endpoints.
- `spring-boot-starter-security`: filter chain, session security, and authorization.
- `spring-security-saml2-service-provider`: AuthnRequest, response processing, metadata, and OpenSAML integration.
- Shibboleth Maven Repository: may be needed to resolve certain OpenSAML artifacts per the version-specific Spring Security guide.

Do not add `spring-security-oauth2-client` to enable SAML2. OIDC/OAuth2 Client is a different protocol/DSL from `saml2Login`.

### 8.2. Main Class

`src/main/java/com/example/samlregistration/SamlRegistrationApplication.java`:

~~~java
package com.example.samlregistration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlRegistrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlRegistrationApplication.class, args);
    }
}
~~~

### 8.3. SecurityFilterChain Configuration

`src/main/java/com/example/samlregistration/SecurityConfig.java`:

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Behavior:

1. `saml2Login` installs the SAML2 Service Provider flow onto the HTTP filter chain.
2. `saml2Metadata` exports SP metadata for registration with the IdP. If you omit this line, **do not assume a metadata endpoint is published by default**.
3. The `authenticated()` rule requires login for other endpoints, but **does not imply business permissions are granted**.
4. Spring Security handles requests/callbacks automatically per configuration. Do not create a controller receiving `SAMLResponse` to parse XML manually, as it is easy to omit signature/recipient/audience validation.

The template intentionally **does not disable CSRF, signature validation, issuer validation, or default filters**. If you encounter a 403 at the ACS, inspect filter, request, and binding configurations; never disable `csrf()` globally as a temporary workaround.

### 8.4. Inspecting the Principal After Login

`src/main/java/com/example/samlregistration/DemoController.java`:

~~~java
package com.example.samlregistration;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Public endpoint. Open /private to start SAML 2.0 login.";
    }

    @GetMapping("/private")
    public Map<String, Object> privatePage(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("nameId", principal.getName());
        response.put("registrationId",
            principal.getRelyingPartyRegistrationId());
        response.put("department",
            principal.getFirstAttribute("department"));
        return response;
    }
}
~~~

Upon a successful real login, `Saml2AuthenticatedPrincipal` is the principal provided by Spring Security from the processed assertion. `registrationId` identifies which IdP registration the user came from. The `department` attribute may or may not be sent by the IdP, so it can be `null` in `LinkedHashMap`. Never return raw SAML Responses, raw assertions, or sensitive data via debug endpoints in production.

### 8.5. application.yml for the Sample Program

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

Start with the simplest setup first. After confirming SP login works, if the IdP requires signing AuthnRequests, decrypting assertions, or fixing ACS/entity ID, add the branches from sections 5–7 as agreed.

**Never register** `http://localhost:8080/login/saml2/sso/partner-a` in a production IdP if browsers cannot reach the developer machine's localhost. Local integration requires a tunnel/host or a test IdP allowing the redirect/ACS with real URL configuration—never validation bypasses.

### 8.6. Test Run

With Java 17 and a compatible Gradle (or the project's Gradle Wrapper if present):

~~~bash
gradle bootRun
~~~

The `PARTNER_A_IDP_METADATA_URI` environment variable **must point to a real metadata URL** reachable by the Spring Boot runtime. With valid IdP config/resources:

1. Open `http://localhost:8080/` to test the public endpoint. The exact controller response is:
   
   ~~~text
   Public endpoint. Open /private to start SAML 2.0 login.
   ~~~

2. Open `http://localhost:8080/saml2/metadata/partner-a` and check that the SP metadata XML reflects the expected entity ID and ACS. Inspect the **XML fields**, not just HTTP 200.
3. Provide the SP metadata/entity ID/ACS to the IdP administrator and verify the exact `partner-a` partner entry.
4. Open `http://localhost:8080/private` while logged out. Spring Security starts the SP-initiated flow, sends the browser to the IdP, and the IdP returns SAMLResponse to the ACS.
5. When the assertion has a valid signature and matches time/correlation/audience/recipient checks, the app creates a session and returns JSON at `/private`. `nameId` and `department` depend on the IdP, so **there is no fixed JSON**.
6. Revisit `/private` within the same SP session to confirm the user remains recognized by session.

**If you do not yet have a real IdP**, the example still presents valid code and configuration, but successful SAML login cannot be proven just by running `gradle bootRun`. If metadata fails to load, the application may fail immediately when constructing `RelyingPartyRegistrationRepository`; valid metadata must be provided first.

## 9. Registering the SP with the IdP: A Bidirectional Process

Spring Boot configuration is only **half** of the integration. Real deployment workflow:

| Step | Executed by Which Side? | What Must Be Confirmed? |
| --- | --- | --- |
| 1. Obtain trusted IdP metadata | IdP → SP | Entity ID, SSO URL, bindings, certificates, trust, and key rotation. |
| 2. Create registration in Spring | SP | `registrationId`, proper metadata source, endpoints/certificates. |
| 3. Provide SP metadata to partner | SP → IdP | SP entity ID, ACS, supported bindings, signing/encryption certs if used. |
| 4. Register SP application | IdP | Matching audience/recipient/ACS, NameID format, AuthnRequest/Assertion signing. |
| 5. Verify real HTTP flow | Browser + SP + IdP | AuthnRequest reaches right IdP; response returns to right ACS; request correlation holds. |
| 6. Verify authentication and permissions | SP | Valid SAML verification; map local account/separate permissions; deny when unauthorized. |
| 7. Monitor and operate | Both sides | Cert rotation, metadata changes, clock skew, outages, and user offboarding. |

### Questions to Ask the IdP Before Configuring

- Does the IdP provide a **metadata URI** or must certificates be pinned manually? How is the metadata source secured/maintained?
- Does the IdP require signing **AuthnRequest**? Has it received the SP certificate?
- Does the IdP sign the **Response, Assertion, or both**? The SP must validate per the exact profile and policy.
- Will the IdP send **EncryptedAssertion** or **EncryptedID**? Which decryption key does the SP need?
- Which HTTP-Redirect/POST bindings does the IdP support? What are the exact ACS endpoint, entity ID, and SLO URL?
- What are the NameID format, minimum attributes, and user modification/revocation mechanisms?
- Is **SP-initiated SSO** required, or is IdP-initiated also supported; how are `InResponseTo` and replay policies applied?

Do not alter authn request/callback requirements under the mindset "as long as login works". Differences must be captured in an explicit integration contract.

## 10. Two IdPs: Two Independent Registration IDs

One Spring Boot SP can trust **multiple IdPs**. Example with two partners:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
          partner-b:
            assertingparty:
              metadata-uri: ${PARTNER_B_IDP_METADATA_URI}
~~~

Then:

~~~text
/saml2/authenticate/partner-a
/saml2/authenticate/partner-b

/login/saml2/sso/partner-a
/login/saml2/sso/partner-b

/saml2/metadata/partner-a
/saml2/metadata/partner-b
~~~

**Registration IDs must be unique in the repository.** It is an internal namespace selecting an SP–IdP pair; metadata/certs of two sources must never be swapped. Never let the browser specify a metadata URL/trusted certificate via request parameters. Letting a user select a partner in the UI may pick **an existing pre-configured registration**, never dynamically create a trust anchor from an external URL.

**Be careful with multi-tenant authorization:** IdP A and IdP B can emit identical NameID strings. Local accounts should link by **trusted IdP entity ID/registration + NameID + format/qualifiers context**, then check partner/tenant and separate permissions. Successful SAML authentication does not make a user an administrator of the application.

### 10.1. Inspecting Active Registrations in Java

In a development environment, instead of guessing whether config bound properly, you can add an inspection bean **if logging non-sensitive details is permitted**. The code below shows how to read the repository created by Boot.

~~~java
package com.example.samlregistration;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;

@Configuration
public class RegistrationDiagnostics {

    @Bean
    ApplicationRunner verifyRegistration(
            RelyingPartyRegistrationRepository repository) {
        return (ApplicationArguments ignored) -> {
            RelyingPartyRegistration registration =
                repository.findByRegistrationId("partner-a");

            if (registration == null) {
                throw new IllegalStateException(
                    "Missing SAML registration: partner-a");
            }

            System.out.println("SAML registration = "
                + registration.getRegistrationId());
            System.out.println("SP entity ID = "
                + registration.getEntityId());
            System.out.println("ACS = "
                + registration.getAssertionConsumerServiceLocation());
        };
    }
}
~~~

Adding this class to package `com.example.samlregistration` uses a Spring Boot `ApplicationRunner` to read the registration. With default config, output includes **`SAML registration = partner-a`**, while `SP entity ID`/`ACS` may still show URI templates until resolved in a request context. Never use diagnostics to print private keys, raw assertions, or sensitive certificates to logs. In production, this bean is usually unnecessary.

**Note:** `RelyingPartyRegistrationRepository` only supports lookup by ID on its base interface. If you need to list all registrations, use an `Iterable`-compatible repository or a separate management store; do not assume all implementations support iteration.

## 11. When to Configure in Java Instead of application.yml?

YAML fits when the number of IdPs is small, configurations are stable, metadata is clear, and no custom logic is needed. Java beans are typically needed when:

- IdP registrations live in a database or config service and must be selected per tenant/registration in a controlled way.
- Custom metadata trust criteria, certificate validation, or dedicated refresh/rotation strategies are required.
- URI/endpoint or SAML properties must be customized beyond what Boot properties express.
- Multiple registrations with varying signing/decryption policies must be coordinated.
- Request-based registration resolution must be customized without letting requests create trust anchors.

Example using a metadata URL **pre-configured by an administrative system**:

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class ManualSamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration registration =
            RelyingPartyRegistrations
                .fromMetadataLocation(
                    "https://idp.partner-a.example.org/metadata.xml")
                .registrationId("partner-a")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

**This is an alternative** to `application.yml` registration when the application needs Java-based management. Do not add this bean class at the same time assuming Spring Boot will automatically merge YAML registrations into the manual bean: **declaring your own `RelyingPartyRegistrationRepository` bean causes the corresponding auto-configured repository to back off**. To merge them, you must implement that explicitly in code.

The `idp.partner-a.example.org` address is illustrative; change it to real metadata to run. For apps using YAML only, this Java bean is **not needed**.

### 11.1. Watch Out for Metadata Updates

A registration built from metadata at startup **is not guaranteed to auto-update on every IdP key rotation**. Check the actual refresh mechanism of your repository/version and operate verified metadata/certificate refreshes. If metadata is corrupted or a certificate changes unexpectedly outside rotation windows, the system must alert clearly and fail safely; never fall back to "accept any certificate".

### 11.2. SAML Metadata Is Not OAuth Discovery

| Mechanism | SAML2 | OIDC |
| --- | --- | --- |
| Client configuration | `spring.security.saml2.relyingparty.registration` | `spring.security.oauth2.client.registration/provider` |
| Metadata/discovery | XML SAML metadata, entity descriptors, certificates, SSO services | JSON OpenID Provider discovery, issuer, endpoints, JWKS |
| Principal | `Saml2AuthenticatedPrincipal` | `OidcUser` |
| Login DSL | `saml2Login` | `oauth2Login` |
| Default callback | `/login/saml2/sso/{registrationId}` | `/login/oauth2/code/{registrationId}` |

Never use OIDC `issuer-uri` under SAML `assertingparty`, and never replace XML SAML metadata with an OIDC discovery endpoint. They use different formats, parameters, and verification mechanisms.

## 12. Deploying Behind a Reverse Proxy: Base URL Determines Configuration

Locally, requests may arrive at `http://localhost:8080`. In deployment:

~~~text
Browser
  |
  | https://orders.example.org/private
  v
Trusted ingress / reverse proxy (TLS termination)
  |
  | http://orders-service:8080/private
  v
Spring Boot app
~~~

If the application derives SP entity ID/ACS from the internal URL `http://orders-service:8080` while the IdP registered `https://orders.example.org`, issues can arise:

- AuthnRequest contains an internal ACS that the IdP rejects;
- The IdP POSTs to the public ACS, but Spring finds a `Destination`/`Recipient` mismatch;
- SP metadata outputs the wrong scheme/host, breaking IdP setup;
- Secure/SameSite cookies and login redirects do not behave as expected.

A suitable Spring Boot configuration when accepting forwarded headers only from a **trusted** proxy can use:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Safety condition: the ingress must **strip/overwrite client-sent forwarded headers** and pass headers only from trusted proxies; trusting spoofed headers can cause wrong URLs or host-header injection. Verify `/saml2/metadata/partner-a` live from the public domain, not just by reading YAML.

For systems with a stable canonical public URL, explicitly configuring `entity-id` and `acs.location` is sometimes easier to control, provided it aligns with filter callbacks and IdP agreements.

## 13. Single Logout Is a Separate Configuration

SAML2 login with `saml2Login` **does not prove the system has Single Logout (SLO)**. Local SP logout can end the application session while the IdP keeps its SSO session and other SPs remain logged in.

Spring Boot provides a `singlelogout` branch under registration to describe SLO endpoints/bindings, and Spring Security's `saml2Logout` configuration enables SAML logout flows when needed. Both sides must agree on **SLO URL, response URL, binding, signing certificates, IdP metadata, and session index**. One-sided configuration can leave logout in a partial state.

For this **registration** lesson, SLO is **optional**: add it only when the problem genuinely requires it and the IdP supports it. Example fields you may see in Spring Boot 3.3:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            singlelogout:
              url: "https://orders.example.org/logout/saml2/slo"
              binding: POST
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

This snippet **describes only part** of SLO configuration and is insufficient to claim SLO works. To run in practice, enable the proper filter/DSL, corresponding endpoints, signing keys, and metadata on both sides per profile. Never treat logout tests as proof that registration login is configured properly.

## 14. Verifying a Registration Layer by Layer

To avoid "YAML looks right yet the browser still cannot log in", verify in clear order:

| Verification Layer | Actual Check | Common Mistakes |
| --- | --- | --- |
| Property binding | Boot reads `spring.security.saml2.relyingparty.registration.partner-a` properly. | Wrong dashes, indentation, legacy `identityprovider` key, wrong registration ID. |
| IdP metadata | URL loads, XML SAML metadata is valid, issuer/SSO/cert match contract. | 404/timeout, returning HTML login page, stale metadata. |
| SP metadata | `/saml2/metadata/partner-a` advertises exact entity ID/ACS and needed key info. | Internal URLs, HTTP scheme instead of HTTPS, wrong cert. |
| IdP registration | IdP added SP entity ID + ACS, binding, cert, NameID policy. | `Audience`/`Destination`/`Recipient` mismatch. |
| AuthnRequest | `/saml2/authenticate/partner-a` goes to right IdP, response correlation exists. | Wrong IdP chosen, improper request signing, lost RelayState. |
| SAML Response | Valid signature, right issuer, time/audience/recipient/request ID pass validation. | Invalid signature, expired assertion, replay, bad InResponseTo. |
| Local session | SP creates Authentication from valid assertion. | Cookie/session/CSRF/binding mismatch. |
| Authorization | User has permissions on the **right resources**. | Login succeeds but 403 due to missing role/tenant permission. |

### 14.1. Distinguishing 3 Different Failure Modes

**Failure A: application fails to start due to missing metadata/certificate.** This is a **configuration/resource loading** error. Check metadata paths, network, TLS trust, and real certificate files. Never edit SecurityFilterChain to bypass SAML.

**Failure B: browser goes to IdP and returns to ACS, then authentication fails.** This is a **protocol/verification** error. Cross-check `Issuer`, signature, `Audience`, `Destination`, `Recipient`, `InResponseTo`, system clock, and related state. Never disable signature validation or audience checks to "fix" it.

**Failure C: SAML login succeeds, business request returns 403.** This may be **authorization**—for instance, the principal lacks an internal authority or does not belong to an allowed tenant. Fix role/policy mapping rather than modifying IdP metadata to grant over-broad privileges.

### 14.2. Safe Observation

In controlled development environments, selective DEBUG logging can trace configuration paths without printing full tokens/assertions:

~~~yaml
logging:
  level:
    org.springframework.security.saml2: DEBUG
~~~

Never leave DEBUG/TRACE enabled indefinitely in production, as logs can carry login/configuration details and leak sensitive data. Prefer logging **registrationId, error type, correlation ID**, limit NameID/attributes, and never log private keys or raw `SAMLResponse`. Restore appropriate log levels after diagnosis.

## 15. Common Pitfalls When Declaring Properties

| Symptom or Misconception | Common Cause | Resolution |
| --- | --- | --- |
| Using `spring.security.oauth2.client.registration` for SAML. | Confusing OIDC with SAML2. | Use `spring.security.saml2.relyingparty.registration` and `saml2Login`. |
| Using `identityprovider` in Boot 3.3. | Copying templates from older versions. | Use `assertingparty` per Boot 3.3 documentation. |
| Setting `sso-url` to the ACS URL. | Confusing IdP endpoint with SP endpoint. | `sso-url` belongs to IdP; `acs.location` belongs to SP. |
| Using metadata URL as SP entity ID. | Confusing configuration source with protocol identifier. | Obtain SP entity ID from SP metadata/IdP contract. |
| Mixing SP and IdP certificates. | Not separating signing and verification directions. | `assertingparty.verification` = IdP cert; `signing/decryption` = SP keys. |
| Signing response while SP trusts cert embedded in response. | Trust anchor dictated by sender. | Trust only pinned/verified IdP certificates from trusted metadata. |
| Changing `registrationId` without updating ACS/IdP config. | Registration ID appears in URLs/templates. | Synchronize updates across Spring, SP metadata, and IdP. |
| Using http/localhost in production. | Wrong reverse proxy/base URL. | Publish public metadata, use HTTPS and safe forwarded headers. |
| Placing private key in `application.yml` or Git. | Secret exposure. | Use a file/secret manager with strict read permissions. |
| IdP rotates cert and SP stops logging in. | SP retains old cert/metadata. | Establish refresh/rollover workflow; test trusted key sets. |
| Changed ACS but filter misses new POST. | Changed only metadata URL, not URL matcher. | Align callback filter and ACS registration. |
| Enabled `saml2Login` without SP metadata endpoint. | `saml2Metadata` not enabled. | Add the corresponding DSL if metadata publishing is needed. |
| Login succeeds with overly broad permissions. | Trusting external group/NameID as app role. | Link local accounts and apply least-privilege authorization. |
| Two IdPs sharing issuer/cert configuration. | Trust boundaries blurred. | Declare separate registrations and verify each trust anchor. |
| Disabling validation on issuer/audience/signature errors. | Turning misconfiguration into a vulnerability. | Fix configuration and signing artifacts; always fail closed. |

## 16. Practice Exercises and Acceptance Criteria

### Exercise A — Single IdP Configuration

1. Create the Java/Gradle project per section 8.
2. Obtain a **real metadata URI** from your test IdP and set `PARTNER_A_IDP_METADATA_URI` via environment.
3. Build/run the application and read the published SP metadata at `/saml2/metadata/partner-a`.
4. Provide SP entity ID/ACS and signing cert (if needed) to the IdP for registration.
5. Open `/saml2/authenticate/partner-a` and complete SSO in the configured environment.
6. Visit `/private` and confirm `registrationId=partner-a` and NameID comes from the test account, without exposing raw assertions.

**Pass:** Metadata and ACS match the contract, login succeeds only when the response passes validation, and no custom controller parses SAML XML manually.

### Exercise B — Switching from Metadata to Manual

In a test environment, replace `assertingparty.metadata-uri` with **`assertingparty.entity-id`, `sso-url`, and `verification.credentials`**, using real trusted values/certificates. Compare SP metadata and flow against the metadata-based config. If login fails, identify the exact issuer/certificate/SSO endpoint cause; never disable signature verification.

**Pass:** Can explain each field and why metadata-based config usually requires less setup. Can prove the cert is the **IdP verification certificate**, not an SP private key.

### Exercise C — Two IdPs

Create `partner-a` and `partner-b` with separate metadata and set up two login paths. Test selecting each registration, verifying the invoked IdP and results. If both IdPs emit the same NameID, local identity remains separated by registration source/issuer.

**Pass:** Certificates or issuers are never mixed between partners; each flow hits the configured ACS/registration.

### Exercise D — Intentional Failures and Expectations

| Test Environment Change | Safe Expectation |
| --- | --- |
| Wrong metadata URI or missing resource. | App fails to build registration or reports config error; never falls back to unverified login. |
| SP `entity-id` differs from IdP contract. | IdP rejects AuthnRequest or SP rejects assertion with wrong Audience. |
| `acs.location` mismatches public URL. | Response/Recipient/Destination is rejected or callback never reaches filter. |
| Replace IdP signing certificate with an untrusted certificate. | Assertion/response signature is rejected. |
| Change `registrationId` on SP while keeping old IdP URLs. | Login/correlation fails or picks wrong registration; never mixes IdPs. |
| Remove SP signing key when IdP requires signed AuthnRequest. | Cannot produce policy-compliant request; never fakes signature. |
| Valid principal lacking internal permissions. | Can log in, but business endpoints deny access. |

### Self-Check Questions

1. **Why is `registrationId` different from `entity-id`?** Registration ID is Spring's internal key to pick an SP–IdP pair; entity ID is the SAML identity the other side uses for matching and issuing assertions.
2. **Why must the SP still be registered at the IdP when using `metadata-uri`?** Metadata only informs the SP about the IdP; the IdP must still know SP entity ID, ACS, signing policy, and decryption capabilities.
3. **Whose cert is in `assertingparty.verification`?** The IdP's trusted public certificate so the SP can verify signatures.
4. **Whose private key is in `signing.credentials`?** The SP's, used to sign outbound messages when needed.
5. **How do `sso-url` and `acs.location` differ?** SSO URL belongs to the IdP receiving requests; ACS belongs to the SP receiving responses.
6. **Does declaring `saml2Login` automatically enable `saml2Metadata`?** Do not assume so; enable `saml2Metadata` explicitly to publish SP metadata endpoints.
7. **When is a Java repository needed?** When custom registration/refresh/store/tenant requirements exceed YAML config, while managing auto-configuration replacement.
8. **Upon successful SAML login, does the user hold all permissions in the application?** No. Authorization is a separate layer; check local account, permissions, tenant, and ownership.
9. **Why not solve signature errors by disabling signature validation?** That removes source authentication and integrity checks; fix metadata/certificates/policies properly.
10. **Why inspect metadata at the public URL after deployment?** Entity ID/ACS can be misconstructed due to reverse proxy/host/scheme, causing rejections at the IdP/SP.

## 17. Checklist for Completing a Registration

- [ ] SAML2 SP dependency present and `SecurityFilterChain` configured with `saml2Login`.
- [ ] Stable, unique **registrationId**.
- [ ] IdP entity ID, SSO URL, binding, and verification certificate/metadata originate from a **trusted source**.
- [ ] SP entity ID and ACS match the IdP contract and public URLs.
- [ ] If AuthnRequest signing is needed: **SP signing private key + certificate** configured; IdP received public cert.
- [ ] If assertion decryption is needed: matching **SP decryption private key + certificate** configured.
- [ ] SP metadata verified; IdP registered SP, certificates, and authentication method.
- [ ] Reverse proxy/forwarded headers/cookies/TLS properly handled.
- [ ] SP rejects responses with wrong issuer, signature, audience, recipient, time, or InResponseTo.
- [ ] Multiple IdPs kept separated by registration and trust contract.
- [ ] SLO marked supported only after dedicated integration and testing.
- [ ] Business permissions check local account/tenant without blindly trusting external groups.
- [ ] Plans in place for certificate rollover, metadata updates, secure logging, and regression tests.

**Rule to remember:** `spring.security.saml2.relyingparty.registration.<id>` declares **one SP–IdP trust pair**. Outer properties describe what the **SP owns/publishes**; `assertingparty` describes what the **SP knows and verifies about the IdP**. Metadata, ACS, issuer, and certificates must match on both sides; Spring Security handles the SAML protocol while the application decides business authorization.

### Official References

- [Spring Boot 3.3 – Spring Security / SAML2 Relying Party](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#web.security.saml2) — `spring.security.saml2.relyingparty.registration` branch and credentials/IdP structure.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) — catalog of `spring.security.saml2.relyingparty.registration.*`.
- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — registration, entity ID, ACS, and filter flow.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — exporting SP metadata and endpoints.
- [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — processing and validating responses.
- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.pdf) — protocol model and metadata, SP/IdP parts.
