# EntityDescriptor, IDPSSODescriptor, and SPSSODescriptor in SAML 2.0 Metadata

## 1. The Role of SAML 2.0 Metadata

In a **SAML 2.0 federation** system, the Service Provider (SP) and Identity Provider (IdP) need to know in advance which partners are trusted, which endpoints receive messages, which bindings are supported, which public certificates are used to verify signatures, and which rules apply to login/logout.

**SAML 2.0 Metadata** is a standard XML document that publishes these technical facts so that parties can configure trust relationships. Metadata is typically exchanged during partner onboarding, configuration updates, key rotation, SSO/SLO deployment, or incident troubleshooting. **Metadata is not a SAMLResponse, not an Assertion, not a login session, and does not contain user passwords.**

Three core elements:

- **EntityDescriptor:** describes **a single entity**, with an **entityID** identifier and one or more roles.
- **IDPSSODescriptor:** describes the **IdP role** in SSO: the **SingleSignOnService** endpoints, signing keys, NameID formats, and AuthnRequest signing requirements.
- **SPSSODescriptor:** describes the **SP role**: the **AssertionConsumerService (ACS)** endpoints, Assertion signing requirements, AuthnRequest signing information, or SAML Assertion decryption keys.

In **Spring Security Servlet**, an application integrating **spring-security-saml2-service-provider** acts as an **SP/Relying Party**: the application **reads IdP metadata** to learn about the IdP and **publishes SP metadata** so the IdP can register the application. Publishing an SPSSODescriptor **does not automatically turn Spring Security into a SAML IdP**.

This lesson uses OASIS SAML 2.0 rules and the Spring Boot 3.x/Spring Security 6.x, Java 17+ model. The goal is to understand metadata properly and how to operate it in practice, not to build a custom XML parser that self-grants authentication.

## 2. Namespace, Structure, and How to Identify Roles

Official SAML metadata namespace:

~~~text
urn:oasis:names:tc:SAML:2.0:metadata
~~~

Example namespace declaration:

~~~xml
xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
~~~

The **md** prefix is a convention in examples; XML using another prefix or a default namespace still represents the same elements as long as the namespace URI remains unchanged.

An easy-to-remember structure tree:

~~~text
md:EntitiesDescriptor                       (optional: groups multiple entities)
  └── md:EntityDescriptor entityID="..."
        ├── ds:Signature                    (if metadata is signed)
        ├── md:Extensions                   (optional)
        ├── md:IDPSSODescriptor             (if acting as an IdP)
        │     ├── md:KeyDescriptor*
        │     ├── md:SingleLogoutService*
        │     ├── md:NameIDFormat*
        │     └── md:SingleSignOnService+
        ├── md:SPSSODescriptor              (if acting as an SP)
        │     ├── md:KeyDescriptor*
        │     ├── md:SingleLogoutService*
        │     ├── md:NameIDFormat*
        │     ├── md:AssertionConsumerService+
        │     └── md:AttributeConsumingService*
        ├── md:Organization?
        └── md:ContactPerson*
~~~

In the diagram, **+** means at least one, **\*** means 0 or more, and **?** means optional. This is a conceptual diagram; the actual XML element order must follow the SAML Metadata XSD. An EntityDescriptor can contain multiple role descriptors (IdP, SP, AttributeAuthority...), and each role has its own configuration.

**EntitiesDescriptor** differs from EntityDescriptor: EntitiesDescriptor is a **collection of multiple entities**, commonly used for a federation's metadata. If loading an aggregate, you must select the **right entityID and the right role**; do not arbitrarily pick the first EntityDescriptor.

### Metadata vs. Per-Login Messages

| Concept | What does it describe? | When is it used? |
| --- | --- | --- |
| **EntityDescriptor/role descriptors** | Technical identity, endpoints, certificates, and capabilities of a partner. | Onboarding, trust configuration, metadata refresh, rollover. |
| **AuthnRequest** | SP requests the IdP to authenticate a user. | A single SP-initiated login session. |
| **SAML Response/Assertion** | IdP returns the authentication/subject result, which the SP must verify. | A specific login session. |
| **LogoutRequest/LogoutResponse** | Single Logout messages when supported by the parties. | Federation logout flow. |

**Metadata signatures and SAMLResponse signatures are two different things**. Even when metadata is already trusted, every SAMLResponse/Assertion must still be validated for signature, issuer, audience, destination, subject confirmation, InResponseTo, and timestamps according to the profile.

## 3. EntityDescriptor: Identity of a SAML Entity

Illustrative form:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml/metadata"
    validUntil="2030-01-01T00:00:00Z"
    cacheDuration="PT8H">
  <!-- Must contain a real role descriptor inside, for example IDPSSODescriptor -->
</md:EntityDescriptor>
~~~

This snippet only illustrates attributes and is **not complete metadata** because the role descriptor has been omitted.

| Attribute / Element | Role | Notes |
| --- | --- | --- |
| **entityID** | Required; logical identifier of the entity. | Usually a URI/URL, but **not necessarily the metadata download URL**. |
| **ID** | Optional; XML ID that can be used for ds:Signature references. | Not AuthnRequest.ID or a session ID. |
| **validUntil** | Optional; expiration timestamp for metadata validity. | Not a token or session lifetime. |
| **cacheDuration** | Optional; suggested cache duration, in XML duration format. | Not the user's SSO login duration. |
| **ds:Signature** | Optional; signature protecting the metadata content. | Merely having a signature does not mean trust has been verified. |
| **Organization** | Optional; operating organization information. | Does not replace entityID for identifying a partner. |
| **ContactPerson** | Optional; technical/support contact. | Do not use email as a trust anchor. |

**entityID is a logical identifier**, so it can differ from the metadata download location and SAML flow endpoints. Valid example when configuring an SP:

~~~text
SP entityID:
  https://sp.example.com/saml2/service-provider-metadata/corp

SP metadata URL:
  https://sp.example.com/saml2/metadata/corp

SP ACS URL:
  https://sp.example.com/login/saml2/sso/corp
~~~

The three values can share the same hostname while having different paths; do not arbitrarily edit them to be identical. **AuthnRequest.Issuer is usually the SP entityID**, **Assertion Audience usually contains the SP entityID**, and **SAMLResponse goes to the ACS URL**.

### Can one entity be both an IdP and an SP?

Yes. An identity broker/gateway can both receive SAML from an external IdP (acting as an SP upstream) and issue SAML to other applications (acting as an IdP downstream). A single entity's metadata can publish both IDPSSODescriptor and SPSSODescriptor if the system actually supports both. **Do not conflate roles:** each role's endpoints and keys serve different functions.

### Aggregate Metadata with EntitiesDescriptor

~~~xml
<md:EntitiesDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Name="ExampleFederation">
  <md:EntityDescriptor entityID="https://idp-a.example.org/metadata">
    <!-- IDPSSODescriptor of IdP A -->
  </md:EntityDescriptor>
  <md:EntityDescriptor entityID="https://idp-b.example.org/metadata">
    <!-- IDPSSODescriptor of IdP B -->
  </md:EntityDescriptor>
</md:EntitiesDescriptor>
~~~

This example is a **structural skeleton with role descriptors omitted**, not a document to import directly. A metadata bundle with multiple IdPs requires a clear way to select the **entityID and role**, a clear trust source, and handling for cache/expiry of both the aggregate and individual entities.

## 4. IDPSSODescriptor: Identity Provider Metadata

IDPSSODescriptor is the role descriptor that describes an **IdP providing SAML 2.0 login services**. The SP reads this role to learn the **IdP entityID, SSO endpoints, bindings, and signature verification keys**, as well as whether the IdP requires the SP to sign AuthnRequests.

| Field in IDPSSODescriptor | Meaning |
| --- | --- |
| **protocolSupportEnumeration** | Required for role descriptors; contains protocol URIs. SAML2 uses **urn:oasis:names:tc:SAML:2.0:protocol**. |
| **WantAuthnRequestsSigned** | Optional; true when the IdP requires AuthnRequests from the SP to be signed. By specification, if omitted it defaults to false in metadata; IdP operational policy should still be confirmed. |
| **KeyDescriptor use="signing"** | Public certificate/key of the IdP for the SP to verify signatures on Responses, Assertions, and Logout messages per policy. |
| **SingleSignOnService** | **At least one required**. Endpoint **belonging to the IdP** that receives AuthnRequests, with Binding and Location. |
| **SingleLogoutService** | Optional. IdP endpoint supporting SAML Single Logout if SLO is integrated. |
| **NameIDFormat** | Optional. NameID formats such as persistent, transient, emailAddress. |
| **ArtifactResolutionService** | Optional for profiles using SAML Artifact/artifact resolution; not needed in common HTTP Redirect/POST flows. |

### Sample IDPSSODescriptor XML

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/saml/metadata"
    validUntil="2030-01-01T00:00:00Z">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>
            REPLACE_WITH_REAL_BASE64_X509_PUBLIC_CERTIFICATE
          </ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/logout"/>

    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**This is only an XML explanation sample.** The string REPLACE_WITH_REAL_BASE64_X509_PUBLIC_CERTIFICATE **is not a valid certificate** and the example.org domain is illustrative; do not use this metadata for real authentication.

Reading the example:

1. **EntityDescriptor.entityID** identifies the **IdP issuer**. It is the IdP identifier, not necessarily an HTML login page.
2. **WantAuthnRequestsSigned=true** indicates that **the SP must sign AuthnRequests** per policy. The SP needs a signing private key, and the IdP needs the SP's public certificate to verify it.
3. **KeyDescriptor use=signing** publishes the **IdP's** public key/certificate; the SP uses it to verify messages signed by the IdP. It must not be confused with the HTTPS certificate of the IdP website unless there is an explicit trust contract.
4. **SingleSignOnService HTTP-Redirect** is one IdP login entry option. An IdP can publish multiple bindings; the SP chooses a compatible binding.
5. **SingleLogoutService** is the IdP's SLO entry point; merely declaring the endpoint does not automatically enable cross-application logout.
6. **NameIDFormat=persistent** shows that the IdP publishes a NameID format; it does not allow inferring that NameID is an email or an immutable userId across all systems.

**Especially important:** IdP metadata may contain **multiple KeyDescriptors** during key rotation. Do not blindly select a certificate based on XML order; use a trust policy and verified metadata updates.

## 5. SPSSODescriptor: Service Provider Metadata

SPSSODescriptor describes what the **SP application** publishes to the IdP. Most importantly, it includes the **SP entityID** and **AssertionConsumerService URL**, where the IdP POSTs the SAMLResponse. Spring Security Servlet outputs metadata in this format when **saml2Metadata()** is enabled.

| Field in SPSSODescriptor | Meaning |
| --- | --- |
| **protocolSupportEnumeration** | SAML 2.0 protocol supported by the SP; not a binding URI. |
| **AuthnRequestsSigned** | Optional; true when the SP advertises signed AuthnRequests. Must have matching signing credentials and actual runtime configuration. |
| **WantAssertionsSigned** | Optional; indicates the SP wants Assertions to be signed. Does not replace the SP performing signature validation. |
| **KeyDescriptor use="signing"** | SP's public certificate for the **IdP to verify** signatures on AuthnRequest/Logout messages created by the SP. |
| **KeyDescriptor use="encryption"** | SP's public certificate for the **IdP to encrypt** Assertions sent to the SP; the SP keeps the decryption private key. |
| **AssertionConsumerService** | **At least one required**, with **Binding, Location, index**; may specify **isDefault**. |
| **SingleLogoutService** | Optional; SP endpoint supporting the SLO protocol. |
| **NameIDFormat** | Optional; describes NameID formats supported/expected by the SP. |
| **AttributeConsumingService** | Optional; describes the service and attributes the SP needs (RequestedAttribute), such as email, group. |

### Sample SPSSODescriptor XML

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://sp.example.com/saml2/service-provider-metadata/corp"
    validUntil="2030-01-01T00:00:00Z">

  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      AuthnRequestsSigned="false"
      WantAssertionsSigned="true">

    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.com/login/saml2/sso/corp"
        index="0"
        isDefault="true"/>

    <md:AttributeConsumingService index="0" isDefault="true">
      <md:ServiceName xml:lang="vi">Ung dung noi bo</md:ServiceName>
      <md:RequestedAttribute Name="email" isRequired="false"/>
    </md:AttributeConsumingService>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

This sample **has no certificates** because the SP does not yet use signing or encryption keys, nor does it have a metadata signature. It is a structural illustration; actual XML generated by Spring Security may differ while still conforming to the standard.

Explanation:

- **entityID** belongs to EntityDescriptor, serves as the **SP issuer** for AuthnRequests, and is typically the **Audience** the IdP puts into the Assertion.
- **AssertionConsumerService.Location** is the **SP's HTTP address** that receives the SAMLResponse, distinct from entityID even on the same host. For example, Spring Security's ACS typically has the path **/login/saml2/sso/{registrationId}**.
- **index** is an integer distinguishing published ACS endpoints. It is **not the registrationId**, nor a NameID or request ID. The optional **isDefault** helps determine the default ACS according to metadata rules.
- **AuthnRequestsSigned=false** in the example indicates the SP does not sign AuthnRequests; if the IdP sets WantAuthnRequestsSigned=true, you must configure signing credentials and align policies.
- **WantAssertionsSigned=true** asks the IdP to sign the Assertion per the contract; it does not mean the Assertion is encrypted.
- **AttributeConsumingService** describes desired attributes and **does not enforce application authorization**.

If the SP publishes KeyDescriptor use=encryption, the IdP can encrypt Assertions for the SP using that public certificate; **only the SP holds the decryption private key**. If the SP publishes use=signing, the IdP uses that public cert to verify AuthnRequests signed by the SP; **only the SP holds the signing private key**. The use attribute is optional, and policy must determine key purpose; never equate the IdP certificate with the SP certificate.

### Which metadata role contains which endpoint?

| Endpoint | Where published | Who owns it | Purpose |
| --- | --- | --- | --- |
| **SingleSignOnService** | **IDPSSODescriptor** | IdP | Receives SAML AuthnRequests from the SP. |
| **AssertionConsumerService** | **SPSSODescriptor** | SP | Receives SAMLResponses from the IdP. |
| **SingleLogoutService** | Both roles can publish | Each side | Receives SLO messages matching the binding. |
| **ArtifactResolutionService** | Role supporting Artifact | Side providing resolution service | Exchanges artifacts for SAML messages. |

Do not confuse the IdP metadata endpoint with the SSO endpoint, nor the SP metadata endpoint with the ACS. Metadata is where **configuration is published**; SSO/ACS are where **login messages are received**.

## 6. Comparison Table of the Three Descriptors

| Question | EntityDescriptor | IDPSSODescriptor | SPSSODescriptor |
| --- | --- | --- | --- |
| **Role?** | Entity wrapper description. | IdP SSO. | SP SSO. |
| **Identifier?** | entityID required. | Uses parent's entityID. | Uses parent's entityID. |
| **Required endpoint?** | Does not specify a concrete SSO endpoint. | At least one SingleSignOnService. | At least one AssertionConsumerService. |
| **Which certificates?** | Metadata itself may be signed with ds:Signature. | Public cert/KeyDescriptor of the IdP. | Public cert/KeyDescriptor of the SP. |
| **Signing policy?** | Metadata signature if present. | WantAuthnRequestsSigned. | AuthnRequestsSigned, WantAssertionsSigned. |
| **Logout info?** | May have child roles. | Optional SingleLogoutService. | Optional SingleLogoutService. |
| **Values Spring uses?** | EntityID/partner identity. | SSO endpoint, IdP verification credentials. | SP ACS/entityId/credentials to publish metadata. |

Quick check: if XML only has **IDPSSODescriptor** and SingleSignOnService, it is **IdP** metadata. If it only has **SPSSODescriptor** and AssertionConsumerService, it is **SP** metadata. If it has both, the partner publishes **both roles**. If XML starts with **EntitiesDescriptor**, you must find the corresponding child EntityDescriptor.

## 7. Protocol URI, Binding URI, and HTTP URL Are Not the Same

| String | Meaning |
| --- | --- |
| **urn:oasis:names:tc:SAML:2.0:protocol** | SAML2 protocol URI in **protocolSupportEnumeration**. |
| **urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect** | Message transport via Redirect binding. |
| **urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST** | Message transport via form POST binding. |
| **urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact** | Binding using artifacts when parties implement resolution. |
| **https://idp.example.org/saml/sso** | HTTP **Location** of the IdP SingleSignOnService. |
| **https://sp.example.com/login/saml2/sso/corp** | HTTP **Location** of the SP AssertionConsumerService. |

**protocolSupportEnumeration** answers "which protocol is supported"; **Binding** answers "how is the message transported"; **Location** answers "where is it received". Do not put the HTTP-POST binding URI into protocolSupportEnumeration or treat the protocol URI as a Location.

### Relationship to Response.Destination, SubjectConfirmationData.Recipient, and Audience

When the IdP sends an Assertion to the SP:

- **Response.Destination** is usually the **SP's ACS**.
- **SubjectConfirmationData.Recipient** for bearer confirmation is usually the **ACS receiving the Assertion**.
- **Conditions.AudienceRestriction / Audience** is usually the **SP entityID**.
- **Response/Assertion.Issuer** is the IdP entityID as agreed.
- **AuthnRequest.Issuer** is the SP entityID.

Therefore, do not arbitrarily force **SP entityID to match the ACS URL**. It is normal for metadata to declare two different values.

## 8. Establishing Trust with Metadata

A complete SAML SP–IdP workflow typically includes:

1. **IdP admin exports IdP metadata**: EntityDescriptor + IDPSSODescriptor, entityID, SingleSignOnService, signing KeyDescriptor, bindings, and policies.
2. **SP admin verifies the metadata source**, loads/registers it under the trust process; selects the right entityID/role if the metadata contains multiple entities.
3. **Spring Security builds RelyingPartyRegistration**: IdP verification credentials, IdP SSO URL, SP entityID and ACS; adds signing/decryption credentials if needed.
4. **SP publishes SP metadata**: EntityDescriptor + SPSSODescriptor, entityID, ACS Binding/Location, SP public certs when present.
5. **IdP admin registers the SP** with the exact entityID, ACS, and SP public cert; aligns AuthnRequestsSigned/WantAuthnRequestsSigned and policies.
6. **Test SP-initiated SSO**: Spring sends AuthnRequest to IdP SingleSignOnService; IdP sends SAMLResponse to SP AssertionConsumerService; Spring validates signature, issuer, audience, destination, subject confirmation, timestamps, and request correlation.
7. **Operational testing**: logout, cert rotation, metadata cache, public URLs, multiple IdPs, metadata fetch failures, and application permissions.

~~~text
   TRUST CONFIGURATION
   IdP -- IDPSSODescriptor ------------> Spring SP
   SP  -- SPSSODescriptor -------------> IdP

   SSO FLOW
   Browser -> Spring SP -> IdP SingleSignOnService
   Browser <- IdP SAMLResponse
   Browser -> Spring SP AssertionConsumerService
   Spring SP -> validate Response/Assertion -> local Authentication
~~~

### Which keys are used?

| Key | Where is the private key kept? | Where is the public certificate used? |
| --- | --- | --- |
| **IdP signing** | IdP. | SP verifies Response/Assertion/Logout signed by the IdP. |
| **SP signing** | SP. | IdP verifies AuthnRequest/Logout signed by the SP. |
| **SP decryption** | SP. | IdP encrypts Assertion sent to the SP; SP decrypts it. |
| **Metadata signing** | Metadata publisher or federation operator. | Consumer verifies metadata using a preconfigured trust anchor. |

KeyDescriptor publishes a **public certificate**, not a private key. **Metadata signing** and **SAMLResponse signing** may use different keys; do not equate a certificate in XML with an HTTPS CA. A certificate inside untrusted metadata **cannot verify that same metadata**, because an attacker could replace both the data and the certificate.

### Metadata Validity and Caching

**validUntil** is the metadata expiration timestamp; **cacheDuration** is a suggested cache interval. They do **not** determine the session lifetime at the SP/IdP or Assertion.NotOnOrAfter. Depending on the metadata provider and policy, caching/refresh may apply a shorter bound and handle aggregates.

If the IdP rotates its signing key, metadata may publish **multiple signing certificates** during the transition window. The SP must have a valid trust update process, cert expiry alerts, and testing—not "pick the first certificate" or disable signature validation on error. When the metadata URL fails, system policy decides whether to use a still-valid cache or fail closed; expired metadata should not be used indefinitely.

### Risks When Loading Metadata

- Do not let end users supply arbitrary metadata URLs/hosts for the backend to fetch; guard against **SSRF**, spoofed sources, and misconfigured trust.
- Do not accept any arbitrary role or entityID just because the metadata XML carries a signature from a **key self-declared in that same file**.
- XML should be parsed with a maintained SAML library, with DTD/external entities disabled per policy, protecting against XML signature wrapping and applying schema/profile validation.
- If metadata is signed, verify it with a **trusted signer** or an independent trusted source and check the signature scope.
- Do not copy test certificates, placeholders, or private keys into Google Sheets or real production tickets.

## 9. Spring Security Servlet: Reading IdP Metadata and Publishing SP Metadata

### 9.1. RelyingPartyRegistration Is Not an XML EntityDescriptor

In Spring Security, **RelyingPartyRegistration** represents **a relationship between an SP and an asserting party (IdP)**, consisting of:

- **SP side:** SP entityId, ACS location, AuthnRequest signing credentials and decryption credentials, logout configuration.
- **IdP side:** IdP entityId/issuer, SSO location, binding, IdP verification certificates, logout location.
- **registrationId:** a technical name in Spring, such as **corp**, used to select a partner configuration; **not synonymous with** the XML entityID.

An application can have multiple RelyingPartyRegistrations. When loading federation aggregate IdP metadata, you must select the right IdP entityID; RelyingPartyRegistration is not a user and is not an IDPSSODescriptor published by Spring.

### 9.2. Spring Boot 3.3.5 + Java 17 Example

This is a **real SP application**, runnable once registered with a **real IdP**, providing a metadata URI and matching trust/ACS/entityID. It **does not create an IdP**.

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
    <artifactId>saml-metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
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

**SAML_IDP_METADATA_URI** must be an organization-approved IdP metadata URL. The sample metadata URL **https://idp.example.org/saml/metadata** is only an example and should not be expected to be reachable. If the IdP requires signed AuthnRequests, the SP must configure the corresponding signing private key/public certificate; the minimal YAML does not include them yet.

**src/main/java/com/example/metadata/SamlMetadataApplication.java**

~~~java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlMetadataApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlMetadataApplication.class, args);
    }
}
~~~

**src/main/java/com/example/metadata/SecurityConfig.java**

~~~java
package com.example.metadata;

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
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**src/main/java/com/example/metadata/DemoController.java**

~~~java
package com.example.metadata;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/")
    public String home() {
        return "SAML metadata SP demo";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return "NameID=" + user.getName();
    }
}
~~~

Set the **SAML_IDP_METADATA_URI** variable to a valid IdP metadata URL, configure trust and register the SP at the IdP, then run in the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Deterministic outcomes:

- **GET http://localhost:8080/** returns the exact text **SAML metadata SP demo**.
- **GET http://localhost:8080/saml2/metadata/corp** outputs **SP metadata XML** from registration **corp**, typically containing EntityDescriptor + SPSSODescriptor + AssertionConsumerService. Spring also supports metadata paths such as **/saml2/metadata** and **/saml2/service-provider-metadata/corp** depending on configuration.
- **GET http://localhost:8080/saml2/authenticate/corp** initiates SP-initiated SSO to the IdP SingleSignOnService.
- **GET http://localhost:8080/me** without a session requires SAML login; after the IdP issues a valid Response to the ACS, the body has the form **NameID=<value issued by IdP>**; a fixed subject cannot be assumed.

**You cannot run a full SSO flow with fake metadata**, because you need a real IdP, signing trust, and matching ACS and SP entityID. The lesson only requires an **SP** application; Spring Security saml2Login/saml2Metadata does not provide a user store, MFA, centralized login, or an IDPSSODescriptor like a SAML IdP.

### 9.3. Default SP entityID and ACS

In Spring Security 6, the common pattern is:

~~~text
SP entityID:
  {baseUrl}/saml2/service-provider-metadata/{registrationId}

SP ACS:
  {baseUrl}/login/saml2/sso/{registrationId}
~~~

For example registrationId = corp. If running behind a proxy, **baseUrl must be the public HTTPS URL** seen by the IdP. Common mistake: the SP outputs metadata with **http://internal:8080** instead of **https://sp.example.com**, causing the IdP to reject ACS/Recipient/Destination. The fix is to configure forwarded headers/host/proxy and set the right entityID/ACS; do not disable validation.

### 9.4. Spring Security Version Caveat

The APIs **RelyingPartyRegistrations**, **RelyingPartyRegistration**, **saml2Metadata()**, and metadata mapping behavior depend on the version. Spring Security 7.x adds new APIs for AssertingPartyMetadataRepository, and IdP metadata signature verification/refresh; do not copy imports and constructors from 7.x into a Boot 3.x/Security 6.x project without checking dependencies. Being **able to read metadata** does not automatically prove the metadata was signed and trust-verified per policy.

## 10. Standalone Java 17: Reading Roles in XML Without Self-Authenticating SAML

The plain Java example below only identifies **EntityDescriptor, IDPSSODescriptor, SPSSODescriptor, and SSO/ACS endpoints** in **a sample XML**. It is **not a SAML trust validator**: it does not verify signatures, schemas, certificates, metadata source, entityID authenticity, or profile security. Do not use it in place of Spring Security/OpenSAML.

**MetadataReaderDemo.java**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.xml.sax.InputSource;

public class MetadataReaderDemo {
    private static final String NS =
            "urn:oasis:names:tc:SAML:2.0:metadata";

    public static void main(String[] args) throws Exception {
        String xml = """
                <md:EntityDescriptor
                  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                  entityID="https://idp.example.org/metadata">
                  <md:IDPSSODescriptor
                    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
                    <md:SingleSignOnService
                      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                      Location="https://idp.example.org/sso"/>
                  </md:IDPSSODescriptor>
                </md:EntityDescriptor>
                """;

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        Document document = factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
        Element root = document.getDocumentElement();

        System.out.println("entityID=" + root.getAttribute("entityID"));
        System.out.println("IdP=" + root
                .getElementsByTagNameNS(NS, "IDPSSODescriptor").getLength());
        System.out.println("SP=" + root
                .getElementsByTagNameNS(NS, "SPSSODescriptor").getLength());
        System.out.println("SSO=" + root
                .getElementsByTagNameNS(NS, "SingleSignOnService").getLength());
        System.out.println("ACS=" + root
                .getElementsByTagNameNS(NS, "AssertionConsumerService").getLength());
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac MetadataReaderDemo.java
java MetadataReaderDemo
~~~

**Exact stdout:**

~~~text
entityID=https://idp.example.org/metadata
IdP=1
SP=0
SSO=1
ACS=0
~~~

The sample XML has **one IdP role and no SP role**, so the counts are 1/0/1/0. The getElementsByTagNameNS method finds all elements matching the namespace and local name in the subtree; if the XML is an **EntitiesDescriptor aggregate**, you must locate the specific entity before counting. Disallowing DOCTYPE/external DTD in the example demonstrates a cautious parser, but **does not replace verifying metadata trust**.

## 11. Practical Checks with Metadata

| Case | Result / What to Check |
| --- | --- |
| IdP metadata has a valid EntityDescriptor but **no IDPSSODescriptor** | Cannot treat it as IdP SSO metadata suitable for a Spring SP. |
| IdP metadata has no SingleSignOnService | Missing required capability/role for Web Browser SSO; the IdP must fix it. |
| SP metadata has no AssertionConsumerService | Does not adequately describe the SP SSO role; check metadata publishing config. |
| SP EntityID differs from IdP registration | IdP may reject AuthnRequest or Response audience will be wrong. |
| SP ACS differs from URL allowlisted at IdP | IdP may reject Reply URL, or SP rejects Recipient/Destination. |
| SP metadata declares AuthnRequestsSigned=false while IdP requires signed requests | Must enable signing on the SP and exchange the public certificate. |
| SP metadata declares WantAssertionsSigned=true while Response/Assertion is not signed per policy | SP must not downgrade trust validation to allow login. |
| IdP signing certificate changes | Refresh metadata/key rollover under trust, verify validity window and overlap. |
| Metadata is signed but signer is unverified | Not sufficient to trust metadata; requires an independent trust anchor. |
| Federation aggregate has multiple EntityDescriptors | Select the right entityID and IDPSSODescriptor/SPSSODescriptor. |
| User can log in but lacks /admin permission | SAML metadata does not grant business roles; check SP authorities/authorization. |
| Logging out of A does not log out of B | Distinguish local session, IdP session, and SLO; SingleLogoutService is only capability config. |

### Quick Verification Workflow During SP Integration

1. Read IdP metadata from a source confirmed by the IdP admin, inspect **EntityDescriptor.entityID** and **IDPSSODescriptor**.
2. Cross-check **SingleSignOnService Location/Binding**, signing certificates, and **WantAuthnRequestsSigned**.
3. Retrieve SP metadata from **/saml2/metadata/corp**, check **SPSSODescriptor**, SP entityID, and **AssertionConsumerService Location/Binding/index**.
4. Send the IdP admin the SP entityID, HTTPS ACS, SP cert if applicable, and NameID/attribute requirements if needed.
5. Test the real AuthnRequest/Response flow in a sandbox, verifying signature, timestamps, InResponseTo, Recipient, Destination, and Audience.
6. Test behind proxy/cluster and with certificate rotation, metadata expiry, and logout policy.

Do not arbitrarily add Redirect/ACS endpoints in metadata if the application **does not actually serve those endpoints**. Metadata and runtime configuration must describe **the same reality**.

## 12. Common Misconceptions to Avoid

1. **"EntityDescriptor itself is the IdP."** Incorrect; it is the entity wrapper. Only the IDPSSODescriptor role indicates the entity publishes SAML IdP SSO capabilities.
2. **"Metadata URL and entityID are the same thing."** Not necessarily; one is where the document is downloaded, the other is a logical identifier.
3. **"SingleSignOnService belongs to the SP."** No; it is the IdP endpoint receiving AuthnRequests. The SP has AssertionConsumerService.
4. **"ACS and entityID must share the same URL."** No; ACS is an HTTP target, entityID is an identifier used in issuer/audience.
5. **"Metadata containing an X509Certificate is definitely trustworthy."** No; the metadata source and trust anchor must be verified.
6. **"Having SPSSODescriptor in Spring turns the app into an IdP."** No; Spring Security saml2Metadata() primarily publishes SP metadata.
7. **"To receive an encrypted Assertion, you only need the IdP signing certificate."** No; the SP needs a decryption key and the IdP needs the SP's public encryption cert.
8. **"KeyDescriptor use=signing is always the SP's signing key."** Depends on the role: inside IDPSSODescriptor it is the IdP's key; inside SPSSODescriptor it is the SP's key.
9. **"If SingleLogoutService is present, system-wide logout works automatically."** No; SLO configuration, signing/verification, and support from both sides are required.
10. **"validUntil = SSO session lifetime."** No; validUntil is the **metadata** expiration.
11. **"protocolSupportEnumeration can replace the HTTP-POST binding."** No; that is the protocol URI; binding is an endpoint attribute.
12. **"Successfully importing XML means trust has been verified."** No; parsing success does not equate to verifying the metadata signature and an approved issuer.

## 13. Self-Check Questions

**1. XML contains EntityDescriptor and IDPSSODescriptor/SingleSignOnService. What kind of metadata is this?**  
It is metadata for an entity publishing the **IdP SSO** role. The SP uses it to find the IdP entityID, SSO endpoint, certificates, and policies.

**2. XML contains EntityDescriptor and SPSSODescriptor/AssertionConsumerService. What kind of metadata is this?**  
It is **SP SSO** metadata, used by the IdP to register entityID, ACS, signing/encryption public keys, and other options.

**3. SP entityID = https://sp.example.org/saml/metadata, ACS = https://sp.example.org/login/saml2/sso/corp. Do these two URLs conflict?**  
No. EntityID is the identifier; ACS is the address receiving Responses. Audience/Issuer and Recipient/Destination are checked according to their respective roles.

**4. IdP metadata requires WantAuthnRequestsSigned=true; is enabling saml2Login() alone on the Spring SP enough?**  
Not yet. The SP must have an appropriate signing private key, the IdP must have the SP's public certificate, and the flow must actually sign AuthnRequests per binding/policy.

**5. The IdP just rotated its signing cert, and the SP starts reporting invalid signatures; should verification be disabled?**  
No. You must update metadata/trust following the key rotation process, check old/new certificates, and plan an overlap window.

**6. If both IDPSSODescriptor and SPSSODescriptor appear in the same EntityDescriptor, is the metadata malformed?**  
Not necessarily. An entity can serve multiple roles; the consuming system must pick the right role.

**7. Spring Security outputs /saml2/metadata/corp without an IDPSSODescriptor. Is this a bug?**  
No. A Spring application configured with saml2Login is a **Service Provider**; it publishes SPSSODescriptor. The IdP is a separate system.

## 14. References

- [OASIS – Metadata for the OASIS Security Assertion Markup Language (SAML) V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): specification for EntityDescriptor, IDPSSODescriptor, SPSSODescriptor, KeyDescriptor, endpoints, and schema.
- [OASIS – SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): context for using metadata in Web Browser SSO.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): reading IdP metadata and publishing SP metadata with **saml2Metadata()**.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, SP entityID/ACS, and SAML2 filters.
- [SAML Metadata XML Schema](https://github.com/keycloak/keycloak/blob/main/saml-core/src/main/resources/schema/saml/v2/saml-schema-metadata-2.0.xsd): XML structure, attributes, and element ordering.

**Key takeaway:** **EntityDescriptor identifies an entity**, **IDPSSODescriptor publishes the IdP's SSO endpoints/certificates/policies**, and **SPSSODescriptor publishes the SP's ACS/certificates/policies**. Properly distinguishing these three layers helps configure trust, deploy Spring Security SAML2, and diagnose federation issues without bypassing security checks.
