# Initializing Registrations with RelyingPartyRegistrations and IdP Metadata

**Module:** Spring Security – federation  
**Learning track:** SAML2 Registration  
**Scope:** Spring MVC/Servlet application acting as a SAML 2.0 Service Provider (SP), Java 17+, Spring Boot 3.x, Spring Security 6.x.

## 1. The Problem to Solve

When an application integrates **SAML 2.0 Single Sign-On (SSO)** with an enterprise Identity Provider (IdP), both sides must know how to exchange messages, identify each other, and verify signatures. The IdP provider usually publishes an **XML metadata file or URL** containing the IdP identifier, login endpoint, and public certificate used to validate SAML Responses/Assertions.

Spring Security provides the **RelyingPartyRegistrations** utility to read that metadata and create a **RelyingPartyRegistration.Builder**. After completing the SP-specific parameters, you call **build()** to produce a **RelyingPartyRegistration**, store it in a **RelyingPartyRegistrationRepository**, and enable **saml2Login()** in SecurityFilterChain.

The ultimate goal is a clearly configured trust relationship:

~~~text
                 IdP XML Metadata (approved source)
                   |  entityID, SSO URL, binding,
                   |  verification certificates, ...
                   v
       RelyingPartyRegistrations.fromMetadataLocation(...)
                   |
                   v
       RelyingPartyRegistration.Builder
                   |  .registrationId("company")
                   |  .entityId(SP entityID)
                   |  .assertionConsumerServiceLocation(SP ACS)
                   |  .signingX509Credentials(...) if needed
                   v
            RelyingPartyRegistration
                   |
                   v
       RelyingPartyRegistrationRepository
                   |
             saml2Login()
                   |
              Browser SSO
~~~

**Important:** IdP metadata is information **published by the asserting IdP for the SP**. SP metadata is information **published by the SP application for the IdP**. The two documents have different roles and are not interchangeable.

## 2. Terminology You Must Know

| Term | Meaning in Spring Security SAML2 |
| --- | --- |
| **Identity Provider (IdP)** / **Asserting Party (AP)** | System that authenticates users and issues SAML Assertions/Responses. |
| **Service Provider (SP)** / **Relying Party (RP)** | Application that relies on the IdP's assertion to establish an Authentication/session. |
| **IdP metadata** | XML describing the IdP: entityID, SSO endpoint, binding, public verification certificate, etc. |
| **SP metadata** | XML describing the SP: entityID, ACS endpoint, and SP certificate/capability information. |
| **RelyingPartyRegistrations** | Static utility to convert IdP metadata into a builder; **not** a repository storing registrations. |
| **RelyingPartyRegistration** | Configuration of **one SP ↔ IdP/AP pair**, including both sides' details. |
| **RelyingPartyRegistrationRepository** | Looks up a registration by ID; Spring uses it when creating requests, handling callbacks, and exporting metadata. |
| **registrationId** | Internal key chosen by the application, e.g., **company**; used in SAML URLs. |
| **entityID** | Protocol identifier of the IdP or SP; not necessarily a reachable URL. |
| **ACS (Assertion Consumer Service)** | SP endpoint that receives the SAML Response, typically via HTTP POST. |
| **SSO service endpoint** | IdP endpoint receiving AuthnRequest, potentially using HTTP-Redirect or HTTP-POST binding. |
| **SAML binding** | How SAML messages are carried over HTTP (Redirect, POST, ...). |
| **X.509 certificate** | Public certificate used for signature verification or encryption depending on role; distinct from the SP's private key. |

**registrationId ≠ entityID:** **company** is a human-friendly name for internal application lookup, whereas **IdP entityID** and **SP entityID** are identifiers used in the SAML protocol. Setting a registrationId alone does not create a trust relationship with the IdP. The IdP still must be configured to accept a valid SP entityID/ACS.

## 3. What Does IdP Metadata XML Contain?

Metadata typically uses the **urn:oasis:names:tc:SAML:2.0:metadata** namespace and structures such as:

- **EntityDescriptor entityID:** IdP issuer identifier, e.g., **https://idp.example.org/saml/company**.
- **IDPSSODescriptor:** describes that the IdP supports SAML 2.0 Web Browser SSO.
- **KeyDescriptor / KeyInfo / X509Certificate:** public certificate used to verify SAML Response/Assertion signatures; multiple certificates may be present to support key rotation.
- **SingleSignOnService Binding + Location:** where the IdP receives AuthnRequest via a specific binding.
- **SingleLogoutService:** if single logout is supported; do not assume every IdP enables or operates SLO the same way.
- **NameIDFormat:** subject identifier formats advertised by the IdP.
- Attributes regarding AuthnRequest signing requirements, metadata validity/cache, and other IdP-specific capabilities.

The example below is an **illustrative XML fragment showing structure**, not ready-to-use metadata because the certificate has been replaced with a placeholder:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/saml/company">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="false">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>REAL_IDP_CERTIFICATE</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Meaning of the data:**

1. **entityID** is the IdP identity that the SP compares against the Issuer in SAML messages. Do not merely check whether hostnames share a suffix.
2. **KeyDescriptor** provides the **public certificate**, not the IdP's private signing key. The SP uses the trusted certificate to verify signatures.
3. **SingleSignOnService** tells Spring which endpoint and binding to send AuthnRequest to.
4. **WantAuthnRequestsSigned** reflects the IdP's requirement/preference for signed AuthnRequests. If signing is required, the SP must supply an appropriate signing key pair/certificate.
5. **SingleLogoutService**, assertion encryption, algorithms, multiple endpoints, and multiple entity descriptors may require additional decisions. Creating a registration from metadata reduces manual entry, but does not replace policy review.

**Attention on trust:** XML metadata may download successfully yet still not be trustworthy information. It must come from an **approved IdP** over a controlled channel/source or have its metadata signature verified per governance procedures. Do not load metadata from an arbitrary user-supplied URL in a request to establish a new issuer.

## 4. Distinguishing IdP and SP Data in RelyingPartyRegistration

| Information | Where Does It Come From? | Example | What Is It Used For? |
| --- | --- | --- | --- |
| **IdP entityID** | IdP metadata | https://idp.example.org/saml/company | Constraining the issuer (Issuer). |
| **IdP SSO URL / binding** | IdP metadata | https://idp.example.org/saml/sso, HTTP-Redirect | Sending AuthnRequest to the right endpoint. |
| **IdP verification credentials** | Trusted IdP metadata | Public X.509 certificate | Verifying SAML signatures. |
| **SP registrationId** | Chosen by application | company | Looking up configuration and forming Spring endpoints. |
| **SP entityID** | Defined by app/SP, registered at IdP | https://app.example.org/saml2/service-provider-metadata/company | Configured SP audience/identifier. |
| **SP ACS URL** | Defined by app/SP, registered at IdP | https://app.example.org/login/saml2/sso/company | Where the IdP sends SAMLResponse. |
| **SP signing certificate + private key** | Managed by SP | SP-owned key pair | Signing AuthnRequest when required. |
| **SP decryption private key** | Managed by SP | Dedicated decryption key | Decrypting assertions when encryption is used. |

**Do not swap certificates:** the IdP certificate from metadata is used to verify IdP signatures. The **SP's private key** is used to sign requests or decrypt data sent to the SP; it is not in IdP metadata and must never be put into public metadata.

A registration holds both **asserting party metadata** and **relying party metadata**. `RelyingPartyRegistrations.fromMetadataLocation(...)` initializes the IdP part from XML, but the SP must still choose `registrationId`, configure entityID/ACS if defaults are unsuitable, and add SP credentials when required by the protocol.

## 5. Core API and Common Confusions

### 5.1. Three Ways to Create a Builder

**From a URL or resource location:**

~~~java
RelyingPartyRegistration.Builder builder =
    RelyingPartyRegistrations.fromMetadataLocation(
        "https://idp.example.org/saml/metadata");
~~~

**From a file on the classpath:**

~~~java
RelyingPartyRegistration.Builder builder =
    RelyingPartyRegistrations.fromMetadataLocation(
        "classpath:metadata/company-idp.xml");
~~~

**From an InputStream provided by a trusted system:**

~~~java
try (InputStream in = /* trusted metadata InputStream */) {
    RelyingPartyRegistration.Builder builder =
        RelyingPartyRegistrations.fromMetadata(in);
}
~~~

The three snippets above are **API-explaining code**, not standalone Java programs; with **fromMetadata(InputStream)** the caller is responsible for closing the stream. The main imports belong to package **org.springframework.security.saml2.provider.service.registration**.

Metadata location can point to content stored on the classpath or an HTTPS endpoint, depending on the supported Spring ResourceLoader/mechanism. URLs must be **controlled and protected**; do not use arbitrary HTTP parameters as paths.

### 5.2. build() and Repository

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("classpath:metadata/company-idp.xml")
        .registrationId("company")
        .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(registration);
~~~

- **RelyingPartyRegistrations** (plural): static helper to parse metadata into a builder.
- **RelyingPartyRegistration** (singular): object describing **one** SP–IdP pair.
- **InMemoryRelyingPartyRegistrationRepository:** stores configuration in memory and looks up by ID; it does not mean the IdP is online or has verified any account.
- **SecurityFilterChain.saml2Login()** uses the repository to determine the IdP, endpoints, and certificates at processing time.

If the application declares its own **@Bean RelyingPartyRegistrationRepository**, Spring Boot uses that bean instead of a repository auto-configured from default properties. Do not create two conflicting configuration mechanisms expecting them to merge automatically.

### 5.3. Notable Default Values

Common defaults in Spring Security SAML2 configurations:

- **registrationId:** e.g., **company**, explicitly chosen by you.
- **Default SP entityID:** **{baseUrl}/saml2/service-provider-metadata/{registrationId}**.
- **Default ACS URL:** path **/login/saml2/sso/{registrationId}**, expanded to the application's address.
- **SP-initiated login:** **/saml2/authenticate/{registrationId}**, e.g., **/saml2/authenticate/company**.
- **SP metadata endpoint** when **saml2Metadata()** is enabled: **/saml2/metadata** or **/saml2/metadata/{registrationId}**; Spring also supports **/saml2/service-provider-metadata/{registrationId}**.
- **SAMLResponse** is typically POSTed to **/login/saml2/sso/{registrationId}** and processed by **Saml2WebSsoAuthenticationFilter**.

Specifically: **SP entityID is an identifier**, even though it looks like a URL. It is not required to point to a web page served at that URL. The **metadata endpoint** is what actually returns the XML describing the SP. The two values may share the same URL in many setups, yet serve distinct roles.

## 6. Spring Boot 3 + Java 17 Example: Initializing Repository from IdP Metadata

Example goal: an application named **staff-portal** logging in via IdP **company**. The IdP metadata configuration is provided and pre-approved, and the application creates **RelyingPartyRegistrationRepository** directly using the Java API.

**Prerequisites for running real SSO:**

1. Spring Boot 3.x / Spring Security 6.x on Java 17+.
2. The IdP supplies **real valid XML metadata** and an SP registration has been created on the IdP.
3. The IdP has received the corresponding **SP entityID** and **ACS URL**; request signing, encryption, and NameID policies are agreed upon.
4. Public URLs, TLS, reverse proxy, and sessions/cookies are configured for the deployment environment.

The example below **compiles in a Boot project with the required dependencies**, but **cannot complete login** until the sample IdP metadata is replaced with real data. Do not fabricate certificates or SAML responses to "make it run" by disabling signature verification.

### 6.1. pom.xml

In a Maven project using **spring-boot-starter-parent** or a BOM managing compatible versions, add the dependencies:

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

**spring-security-saml2-service-provider** provides SAML 2.0 RP/SP functionality; it is not an OAuth2 client or resource server starter. Some environments require configuring an internal/approved artifact repository to download OpenSAML dependencies per the Spring version guide. Do not arbitrarily mix OpenSAML 4/5 with mismatched Spring Security versions.

### 6.2. application.yml

**src/main/resources/application.yml:**

~~~yaml
app:
  saml:
    idp-metadata-location: classpath:metadata/company-idp.xml

server:
  port: 8080
~~~

Place the real approved XML metadata at **src/main/resources/metadata/company-idp.xml**. When packaged as a JAR, classpath resources remain accessible to the application. If choosing an HTTPS URL instead of classpath, configuration can be:

~~~yaml
app:
  saml:
    idp-metadata-location: https://idp.example.org/saml/metadata
~~~

Use only **pre-approved** URLs. If loading metadata at bean initialization fails because the IdP is unavailable, repository construction may fail and prevent the app from starting; a vetted metadata copy on the classpath can make startup more resilient. Conversely, classpath metadata is a **snapshot**, requiring updates/key lifecycle management when the IdP changes.

### 6.3. SsoSamlApplication.java

**src/main/java/com/example/saml/SsoSamlApplication.java:**

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SsoSamlApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoSamlApplication.class, args);
    }
}
~~~

### 6.4. SamlSecurityConfig.java: Registration Bean and Chain

**src/main/java/com/example/saml/SamlSecurityConfig.java:**

~~~java
package com.example.saml;

import org.springframework.beans.factory.annotation.Value;
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
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("${app.saml.idp-metadata-location}") String metadataLocation) {

        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(metadataLocation)
                .registrationId("company")
                .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
                .assertionConsumerServiceLocation(
                    "{baseUrl}/login/saml2/sso/{registrationId}")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/",
                    "/error",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**")
                .permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Layer-by-layer explanation:**

- **RelyingPartyRegistrations.fromMetadataLocation(metadataLocation):** parses IdP XML into a builder populated with IdP details such as entityID/SSO/certificate.
- **registrationId("company"):** stable configuration identifier used in URLs **/saml2/authenticate/company** and **/login/saml2/sso/company**.
- **entityId(...):** specifies the SP identifier announced to the IdP. For example, when deployed at **https://portal.example.org**, entityID becomes **https://portal.example.org/saml2/service-provider-metadata/company**.
- **assertionConsumerServiceLocation(...):** ACS address where the IdP must send the SAML Response. With the public base URL above, this is **https://portal.example.org/login/saml2/sso/company**.
- **InMemoryRelyingPartyRegistrationRepository:** stores the registration; Spring looks it up by ID when creating an AuthnRequest or receiving a Response.
- **saml2Login():** registers SAML2 filters/login flow, such as **Saml2WebSsoAuthenticationRequestFilter** and **Saml2WebSsoAuthenticationFilter**.
- **saml2Metadata():** enables publishing SP metadata for the IdP. Do not confuse this with **RelyingPartyRegistrations**, which **reads IdP metadata**.
- **requestMatchers(...).permitAll():** allows convenient fetching of SP metadata for IdP registration; in real systems metadata access can be restricted per policy. **permitAll** does not mean skipping SAML Response validation.
- **anyRequest().authenticated():** all remaining business endpoints require login.

**CSRF:** HTTP POST SAML Web Browser SSO must work at the ACS. With the standard **saml2Login()** configuration, Spring Security configures appropriate CSRF exemptions for SAML processing endpoints; do not disable CSRF globally via **csrf.disable()**. If you change loginProcessingUrl, re-check the CSRF matcher and configure the same path as the ACS.

**Metadata source and runtime:** the example initializes the repository only when the bean is created. It does not schedule periodic reloads of IdP metadata every few minutes. If the IdP rotates certificates, an update/reload mechanism and a plan accepting multiple certificates during the transition window are needed.

### 6.5. SamlController.java: Endpoint for Observation

**src/main/java/com/example/saml/SamlController.java:**

~~~java
package com.example.saml;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlController {

    @GetMapping("/")
    public String home() {
        return "SAML SP is running";
    }

    @GetMapping("/me")
    public String currentUser(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID: " + principal.getName()
            + ", registrationId: " + principal.getRelyingPartyRegistrationId();
    }
}
~~~

When an unauthenticated user visits **/me**, Spring initiates SAML2 login; upon successful login, the controller can read the **Saml2AuthenticatedPrincipal**. **NameID** may be a long, opaque, or mutable identifier depending on IdP settings; do not assume it is an email address or a permanent system key.

### 6.6. Running and Observing

After configuring real metadata, run inside the project's Maven directory:

~~~bash
mvn spring-boot:run
~~~

Call the unauthenticated endpoint:

~~~bash
curl -i http://localhost:8080/
~~~

Response body from the controller:

~~~text
SAML SP is running
~~~

To view **SP metadata** while the application is running:

~~~bash
curl -i http://localhost:8080/saml2/metadata/company
~~~

If the endpoint is available, the response returns **SP metadata XML**; actual content depends on public base URL, registration, and credential configuration. There is no fixed XML stdout to copy beforehand because it reflects runtime data.

In a browser, initiate **SP-initiated SSO**:

~~~text
http://localhost:8080/saml2/authenticate/company
~~~

With a properly registered IdP, the browser is redirected to the IdP, performs login, and the IdP sends **SAMLResponse** back to the ACS **/login/saml2/sso/company**. If the response is valid, the application creates an Authentication/session and allows access to **/me**.

**Caution when testing locally:** If the IdP only accepts public HTTPS ACS URLs, **http://localhost:8080** will not match. You need a test environment with a public URL, proper proxy/port settings, and accurately registered SP entityID/ACS. Never resolve an ACS mismatch by disabling Audience/Recipient/Signature validation.

## 7. Bidirectional Metadata Exchange Between IdP and SP

This is the recommended real-world deployment workflow:

1. **Receive metadata from IdP:** the IdP administrator provides an HTTPS URL/XML file over an approved channel; verify the exact tenant/environment (dev/staging/prod).
2. **Inspect metadata:** cross-check **IdP entityID**, SSO endpoint, certificate, AuthnRequest signing requirement, binding, validity, and related data against handed-over specs.
3. **Create RelyingPartyRegistration:** use **RelyingPartyRegistrations.fromMetadataLocation()**, choose a **stable registrationId**, and verify SP entityID and ACS.
4. **Configure SP keys** if the IdP requires signed AuthnRequests or encrypted assertions (see section 8).
5. **Export SP metadata:** enable **saml2Metadata()**, open **/saml2/metadata/company**, and verify EntityID and ACS in the XML.
6. **Register SP at IdP:** upload SP metadata or manually enter the exact **SP entityID / ACS / signing or encryption certificate**.
7. **Enable trust at IdP:** the IdP approves the application, user/group policies, signing requirements, and NameID format.
8. **Test bidirectional SSO:** test SP-initiated; test IdP-initiated if supported/approved by the IdP and application; verify Issuer, Audience, Recipient, InResponseTo/time, and signature.
9. **Lock in operations:** monitor certificate rotation, endpoint changes, metadata validity, sessions, and rollback procedures.

One-sided registration is usually insufficient: the SP must know the trusted IdP, and **the IdP must also know and allow the SP**. If SP metadata has a different ACS/domain than what is stored at the IdP, login fails or is rejected.

## 8. When Signing AuthnRequest or Decrypting Assertions Is Needed

IdP metadata may require **WantAuthnRequestsSigned=true**. In that case, the SP needs a **private key + certificate** pair for signing, declared in **RelyingPartyRegistration**. Partial configuration example:

~~~java
// The following variables must be supplied from secure secret storage:
PrivateKey spPrivateKey = /* securely loaded SP private key */;
X509Certificate spCertificate = /* corresponding certificate */;

Saml2X509Credential signing =
    Saml2X509Credential.signing(spPrivateKey, spCertificate);

RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation(trustedMetadataLocation)
        .registrationId("company")
        .signingX509Credentials(credentials -> credentials.add(signing))
        .build();
~~~

This **illustrates how to add credentials**, not a standalone runnable class: **spPrivateKey**, **spCertificate**, and **trustedMetadataLocation** must be provided by the application; import **java.security.PrivateKey**, **java.security.cert.X509Certificate**, **org.springframework.security.saml2.core.Saml2X509Credential**, and the registration classes. Do not copy **/* ... */** comments as real values.

- **signingX509Credentials** are the **SP's** credentials, not the IdP's verification certificate.
- For encrypted assertions, the SP needs **decryptionX509Credentials** with the SP's private key and certificate per the IdP configuration.
- The **IdP** signature verification certificate comes from IdP metadata and lives in asserting-party metadata.
- Having a signing key **does not automatically mean every AuthnRequest is signed**: it also depends on IdP requirements, binding, signing settings, and how Spring constructs the AuthnRequest.
- The IdP may require the SP's signing certificate to be uploaded in advance; check that **SP metadata** actually publishes the proper certificate and aligns with IdP policy.
- Do not embed private keys in source code, Git, logs, or public XML metadata. Use a secret manager, keystore, or approved key management mechanism.

If the IdP does not require signed AuthnRequests, the basic example in section 6 may suffice for login; however, never assume all IdPs allow unsigned requests.

## 9. Metadata Source Variants

### 9.1. Metadata from an HTTPS URL

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("https://idp.example.org/metadata.xml")
        .registrationId("company")
        .build();
~~~

**Advantages:** less manual input, retrieves data matching the managed IdP configuration. **Risks:** network/IdP dependency at read time; a wrong URL or compromised source can break trust configuration. It does not imply automatic runtime metadata refresh when the IdP rotates keys.

### 9.2. Metadata Packaged with the Application

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("classpath:metadata/company-idp.xml")
        .registrationId("company")
        .build();
~~~

**Advantages:** reproducible deployments, easy change control and rollback via application release pipelines. **Risks:** metadata/certificates become stale if not updated per the rotation schedule. Use a secure channel when initially downloading and vetting the file.

### 9.3. Metadata from a Database via InputStream

If the system stores an **approved XML metadata snapshot** in a database, you can supply an InputStream:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

public final class MetadataRegistrationFactory {

    private MetadataRegistrationFactory() { }

    public static RelyingPartyRegistration fromTrustedXml(String xml) {
        try (InputStream input = new ByteArrayInputStream(
                xml.getBytes(StandardCharsets.UTF_8))) {
            return RelyingPartyRegistrations
                .fromMetadata(input)
                .registrationId("company")
                .build();
        } catch (java.io.IOException exception) {
            throw new IllegalStateException(
                "Cannot close metadata stream", exception);
        }
    }
}
~~~

This is a Java class that **compiles in a project with Spring Security SAML2 dependencies**, but it is only a **factory for already-trusted metadata**. Never pass arbitrary XML directly from an HTTP request or a user-editable database table. If the XML stream is invalid, parsing/building can throw corresponding exceptions; the code above only illustrates handling **IOException when closing the stream**.

### 9.4. Metadata Containing Multiple IdP Entities

A metadata document can contain **EntitiesDescriptor** or multiple **IDPSSODescriptor** elements. The **collectionFromMetadataLocation(...)** API returns a collection of builders:

~~~java
Collection<RelyingPartyRegistration.Builder> builders =
    RelyingPartyRegistrations.collectionFromMetadataLocation(metadataLocation);
~~~

A **stable IdP selection/identification rule** and **distinct registrationIds** are needed for each registration before calling build/storing in the repository. Do not blindly pick the first element without identifying the issuer, and do not generate a random UUID on every startup if application URLs/identifiers must remain stable. For different IdPs, the SP needs a trusted allowlist, endpoint mappings, and proper tenant policies. Each registration corresponds to one approved RP–AP relationship.

## 10. Multiple IdPs: Explicit Registrations in the Same Repository

When supporting two approved IdPs (e.g., corporate and partner), you can create two independent registrations:

~~~java
@Bean
RelyingPartyRegistrationRepository relyingPartyRegistrations() {
    RelyingPartyRegistration company =
        RelyingPartyRegistrations
            .fromMetadataLocation(
                "classpath:metadata/company-idp.xml")
            .registrationId("company")
            .build();

    RelyingPartyRegistration partner =
        RelyingPartyRegistrations
            .fromMetadataLocation(
                "classpath:metadata/partner-idp.xml")
            .registrationId("partner")
            .build();

    return new InMemoryRelyingPartyRegistrationRepository(
        company, partner);
}
~~~

**This is a replacement bean** for the bean in section 6; do not place both in the same project with the same bean name expecting Spring to merge them automatically. Each registration is loaded from its corresponding metadata and must register its SP/ACS with the appropriate IdP.

- **/saml2/authenticate/company** initiates login to the company IdP.
- **/saml2/authenticate/partner** initiates login to the partner IdP.
- Corresponding callbacks use registrationId or AuthnRequest state so Spring locates the right registration.
- The partner IdP must not automatically grant the same privileges as the company IdP: identities, groups, and roles must be mapped per each party's policy.
- Do not distinguish two users by NameID/email **alone** when IdPs differ; account linking must be based on the verified IdP identifier + appropriate subject.
- SP entityID and ACS can differ by default registrationId. If a **shared SP entityID/ACS** is desired, configure carefully per the federation profile and ensure registration resolution when receiving Responses is accurate, rather than changing URLs by whim.

**InMemoryRelyingPartyRegistrationRepository** suits small lists and infrequently changing configurations. For systems requiring dynamic metadata management, build a repository with strict controls, configuration integrity, and caching/refresh. Never use a user-controlled database/URL to dynamically expand IdP trust on the fly.

## 11. Metadata Governance and Certificate Rotation

### 11.1. Metadata Is Not an "Always Auto-Updating" Mechanism

Calling **fromMetadataLocation(...)** reads metadata at invocation time to construct the builder; the built registration stored in **InMemoryRelyingPartyRegistrationRepository** reflects the state at that point in time. If the IdP changes its signing certificate the next day, the old repository **does not automatically know** without a corresponding refresh/redeploy mechanism.

You can design a periodically updated repository with a cache/supplier using the Spring Security API appropriate for your version, or run a pipeline updating vetted metadata artifacts. When doing so:

- Load only from **approved IdP locations**, defending against SSRF, external domain redirects, and enforcing timeouts/XML size limits.
- Authenticate metadata over a trusted channel; if the IdP signs metadata, run signature verification with the proper trust anchor.
- Support certificate rotation with an **overlap** phase between old and new certificates per IdP policy.
- Distinguish legitimate certificate rotation from IdP substitution or anomalous metadata.
- Retain a last-known-good configuration if policy permits and emit alerts; never "disable signature verification to restore SSO".
- Audit metadata changes, maintain rollback plans, and smoke-test on staging before production.

### 11.2. SP Credential Rotation Differs from IdP Credential Rotation

- **IdP verification certificates:** used by the SP to verify signatures from the IdP, typically sourced from IdP metadata.
- **SP signing credentials:** used for signed AuthnRequests; the private key must remain with the SP.
- **SP decryption credentials:** used to decrypt data encrypted by the IdP for the SP.
- When rotating an SP certificate, update SP metadata and the corresponding registration at the IdP. When rotating an IdP certificate, update the trusted IdP verification information.
- Do not delete old keys prematurely while systems are still processing data signed/encrypted with old keys.

### 11.3. SAML Response Validation Remains Critical

RelyingPartyRegistration is only **trust and endpoint configuration**. Upon receiving SAMLResponse, Spring Security/OpenSAML must still validate per profile:

- **Signature** of the Response/Assertion using the proper certificate from the trusted IdP.
- **Issuer** matching the registered IdP/AP.
- **AudienceRestriction** containing the appropriate SP entityID.
- **SubjectConfirmationData.Recipient** and **Destination** matching the ACS/callback.
- **Conditions (NotBefore/NotOnOrAfter)** and session/time/skew.
- **InResponseTo** for SP-initiated login, request state, and replay protection.
- NameID format, attributes, and post-authentication user policy.

Do not treat successful XML parsing or a signature from any arbitrary certificate as a valid login. Use standard filters/providers; never write a custom controller that Base64-decodes SAMLResponse and extracts NameID while skipping validation.

## 12. Reverse Proxy, Public Domain, and ACS Stability

When Spring Boot runs internally at **http://127.0.0.1:8080** while the public URL is **https://portal.example.org**, placeholders like **{baseUrl}** must resolve to the **public URL** registered at the IdP. Wrong scheme/host/port can cause:

- SP metadata emitting **http://...** or an internal hostname.
- The IdP rejecting AuthnRequests or refusing the ACS URL.
- SAML Responses arriving at a URL not properly routed by Spring.
- Audience/Recipient/Destination validation failures.

Remediation guidelines:

1. Register the **exact SP entityID and ACS** matching the public URL on the IdP.
2. Configure the reverse proxy to forward trusted **Forwarded / X-Forwarded-*** headers; Spring should trust only headers sent by managed proxies.
3. When fixed SP entityID and ACS are needed, set explicit public HTTPS values in the builder.
4. Inspect the XML from **/saml2/metadata/company** when accessed over the production domain and compare with the IdP.
5. Never allow clients to send arbitrary Host/X-Forwarded-Host headers to influence entityID/ACS (host-header poisoning).

Explicit configuration example:

~~~java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("classpath:metadata/company-idp.xml")
        .registrationId("company")
        .entityId("https://portal.example.org/saml2/sp/company")
        .assertionConsumerServiceLocation(
            "https://portal.example.org/login/saml2/sso/company")
        .build();
~~~

If the SP entityID differs from the metadata URL, that remains valid under SAML when both IdP and SP agree, as long as identifiers/destinations are checked accurately. Use **example.org** hostnames purely for illustration; do not assume real services exist.

## 13. Inspecting Repository Initialization Results

Once the bean is created successfully, Java code can inspect non-sensitive values **without printing private keys, tokens, or sensitive certificates**.

Example of a simple bean in a Spring Boot project:

~~~java
package com.example.saml;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;

@Configuration
public class RegistrationDiagnostics {

    @Bean
    ApplicationRunner printRegistration(
            RelyingPartyRegistrationRepository repository) {

        return args -> {
            RelyingPartyRegistration rp =
                repository.findByRegistrationId("company");
            if (rp == null) {
                throw new IllegalStateException("Missing company registration");
            }

            System.out.println("registrationId=" + rp.getRegistrationId());
            System.out.println("spEntityId=" + rp.getEntityId());
            System.out.println("idpEntityId="
                + rp.getAssertingPartyMetadata().getEntityId());
            System.out.println("acs=" + rp.getAssertionConsumerServiceLocation());
        };
    }
}
~~~

**This class compiles in a Boot project using the dependencies listed above**. However, **spEntityId** and **acs** values are evaluated from configuration and runtime context, so **there is no fixed stdout** across all environments. Lines like the following are only **samples for a hypothetical public URL**, not guaranteed output:

~~~text
registrationId=company
spEntityId=https://portal.example.org/saml2/service-provider-metadata/company
idpEntityId=https://idp.example.org/saml/company
acs=https://portal.example.org/login/saml2/sso/company
~~~

In production, this diagnostic bean is typically unnecessary; use controlled logging, inspect metadata output, and rely on secure observability tools. If the XML metadata contains multiple entities or unexpected values, inspect the **approved input and registration** rather than altering stdout to match expectations.

## 14. Common Errors When Creating RelyingPartyRegistration

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| App fails to start while loading registration | Broken/timed-out metadata URL, missing classpath file, malformed XML, or no matching IdP descriptor | Check approved metadata source, URL/file, XML content, reachability, and parse errors |
| Metadata present but registration not found | **registrationId** differs from login/callback path or repository lacks that ID | Use one consistent ID throughout and compare URLs |
| Clicking login does not redirect to IdP | **saml2Login()** not enabled, chain/matcher misses path, or metadata lacks suitable SSO service | Check SecurityFilterChain, endpoints, and bindings |
| 404/403 at ACS | IdP posts to mismatched URL, proxy misconfigured, callback outside chain, CSRF mis-customized | Compare registered ACS, Spring endpoints, and forwarding |
| IdP rejects AuthnRequest | SP entityID/ACS unregistered; IdP requires signed requests but SP lacks signing credential | Compare SP metadata and IdP settings; add signing credentials securely |
| Signed SAMLResponse is rejected | Active IdP certificate differs from trusted certificate, stale metadata, or chain validation failure | Check IdP rotation/metadata; do not disable signature validation |
| AudienceRestriction/Recipient/Destination mismatch | SP entityID or ACS differs from values used by IdP | Update both sides' configs accurately; avoid workarounds |
| AuthnRequest succeeds but login fails on InResponseTo | Browser lost session/request correlation, multi-node session not shared, or unsolicited response disallowed by policy | Check sessions, cookies, sticky sessions/distributed store, and SP-initiated policy |
| Multiple IdPs and users are mis-mapped | NameID/email identifiers are not unique across IdPs | Link identities by verified IdP issuer and subject |
| IdP rotates certificate and SSO stops | Snapshot repository or classpath metadata not updated | Apply certificate overlap/refresh plan |
| SP metadata cannot be opened | **saml2Metadata()** not enabled or endpoint blocked by authorization | Enable metadata filter and permit GET on the metadata endpoint |
| IdP configured with HTTP while app is public HTTPS | Misconfigured forwarded headers/baseUrl or un-updated explicit URLs | Fix reverse proxy and synchronize SP metadata/IdP |

Specific errors and status codes depend on binding, IdP, Spring Security version, and callback configuration. Review error messages with sensitive data redacted; avoid logging full **SAMLResponse**, session cookies, private keys, or user PII.

## 15. Comprehension Check Exercises

### Question 1 – Why must approved IdP metadata be used?

An HTTP request submits a new URL, and the SP loads metadata and creates a repository from that URL. What is the problem?

**Answer:** A client-supplied URL is not a trust anchor. An attacker can point to an IdP they control, supplying a fake yet self-consistent certificate and issuer, leading to authentication from an untrusted source; it also introduces SSRF risk. Select only from an approved IdP allowlist or audited administrative configuration.

### Question 2 – Why must the SP still be registered at the IdP after reading IdP metadata?

**Answer:** IdP metadata tells the SP about the IdP. The IdP still needs to know the **SP entityID**, **ACS**, SP certificates/capabilities, and access policies. The federation relationship is bidirectional.

### Question 3 – Must registrationId match the IdP entityID?

**Answer:** No. registrationId is an internal key (**company**), while IdP entityID is the identifier published by the IdP; they are not interchangeable. Spring paths typically include registrationId.

### Question 4 – Can the SP use the certificate inside IdP metadata to sign AuthnRequest?

**Answer:** No. The IdP's certificate is a public key for verifying IdP signatures. The SP needs its **own private key + certificate** to sign AuthnRequest when required.

### Question 5 – If fromMetadataLocation is called once, does it auto-update when the IdP rotates its certificate?

**Answer:** No. A builder/repository created from metadata reflects the state at load time. Refresh/reload must be implemented under a governed strategy supporting rotation and verifying new metadata.

### Question 6 – With only one IdP, do you need to write a custom controller to handle POST SAMLResponse?

**Answer:** No. Enable **saml2Login()**, register the repository, and let **Saml2WebSsoAuthenticationFilter** and Spring Security's provider verify the Response/Assertion. Manually Base64-decoding and reading NameID without full validation is dangerous.

### Question 7 – Where does SP metadata come from?

**Answer:** Spring Security can export SP metadata from **RelyingPartyRegistration** when **saml2Metadata()** is enabled, typically at **/saml2/metadata/company**. The IdP uses SP metadata to learn the entityID and ACS, while the SP uses IdP metadata to build the registration.

### Question 8 – When the application sits behind a reverse proxy, what must stay consistent?

**Answer:** Public base URL, SP entityID, ACS, reverse-proxy forwarded headers, SP metadata, and settings stored at the IdP. Never modify response validation just to bypass URL errors.

## 16. Implementation Checklist

- [ ] Obtain **IdP metadata for the right tenant/environment** via a trusted channel; verify entityID, SSO endpoint, binding, and signing certificate.
- [ ] Choose a stable, distinct **registrationId** for each SP–IdP relationship.
- [ ] Use **RelyingPartyRegistrations.fromMetadataLocation(...)** or **fromMetadata(InputStream)** from an approved source, then call **build()**.
- [ ] Declare a single **RelyingPartyRegistrationRepository** used by Spring; avoid duplicate conflicting beans.
- [ ] Explicitly define **SP entityID and ACS**, especially behind proxies or multiple domains.
- [ ] Configure **SP signing/decryption credentials** if required by the IdP, storing private keys securely.
- [ ] Enable **saml2Login()** for the SP and **saml2Metadata()** when metadata export is needed.
- [ ] Register **SP metadata** at the IdP; align entityID, ACS, bindings, certificates, and policies on both sides.
- [ ] Test SP-initiated SSO, POST callback, response signature, issuer, audience, recipient, time validity, and request correlation.
- [ ] Maintain policies for **IdP metadata trust**, certificate rotation, caching/reload, rollback, and monitoring.
- [ ] Authorize and link local accounts post-login by IdP issuer + subject; never grant admin solely because an assertion is valid.

**Remember:** **RelyingPartyRegistrations** turns **trusted IdP metadata** into configuration; **RelyingPartyRegistration** describes an **SP–IdP** relationship, and **RelyingPartyRegistrationRepository** supplies that configuration to SAML2 filters. For SSO to operate securely, SP metadata/ACS, signing keys, and trust configuration at the IdP must match.

## 17. References

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): IdP metadata, repository, registration builder, and endpoints.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html): parsing IdP metadata, exporting SP metadata with saml2Metadata().
- [Spring Security – SAML Authentication Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html): AuthnRequest, bindings, and request signing.
- [Spring Security – SAML Authentication Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): SAMLResponse handling and validation steps.
- [RelyingPartyRegistrations API – Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html): fromMetadataLocation, fromMetadata, collectionFromMetadataLocation.
- [OASIS SAML V2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): entity metadata structure, endpoints, and certificates.
