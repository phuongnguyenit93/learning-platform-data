# Verifying Outbound Messages Against IdP Metadata and Policy

## 1. Lesson Objectives and Scope

In **SAML 2.0 Web Browser SSO**, a Spring Security application acts as the **Service Provider (SP, Relying Party)** and generates an **AuthnRequest** asking the **Identity Provider (IdP, Asserting Party)** to authenticate a user. Even a request with valid XML can still be rejected by the IdP if sent to the wrong SSO endpoint, with the wrong Binding, missing a required signature, using an unacceptable signing algorithm, using an unregistered Issuer/ACS, or carrying ForceAuthn/NameIDPolicy requirements beyond policy.

The topic **“Verifying outbound messages against IdP metadata and policy”** has two distinct verification layers:

1. **Pre-flight / outbound contract check by the SP:** Does the AuthnRequest Spring is about to generate and send match **trusted IdP metadata** and the **SP–IdP configuration contract**?
2. **Inbound verification by the IdP upon receipt:** Do the URL/Binding/message/signature/cert/Issuer/ACS/timestamps/extensions comply with the IdP's active policy? **Only the IdP can confirm this step truly passes.**

Never equate “the SP sees matching metadata” with “the IdP accepted the AuthnRequest.” Metadata describes **published capabilities/configuration**, while the IdP may enforce **additional policies** per partner, tenant, environment, and product version. The final verdict must be confirmed via an **actual SSO flow in a test environment** alongside safe logs/telemetry on both sides.

**Scope:** Spring Security Servlet SAML 2.0 Service Provider, Java 17+, Spring Boot 3.3.5/Spring Security 6.x examples; does not implement an IdP and does not customize response validators. Any examples containing `example.org` domains are simulations, not live endpoints.

### Questions to Answer After This Lesson

- How is AuthnRequest checked against **EntityDescriptor/IDPSSODescriptor/SPSSODescriptor**?
- How to distinguish **SSO URL, HTTP binding, Destination, Issuer, ACS URL, ProtocolBinding**, and **registrationId**?
- When **WantAuthnRequestsSigned=true**, how does Spring require an **SP private key** and an **IdP-trusted certificate**?
- Why does an **HTTP-Redirect query signature** differ from an **HTTP-POST XML signature**?
- How to configure Spring Security to produce a contract-compliant AuthnRequest?
- How to test positive/negative cases to catch invalid requests before going to production?

## 2. AuthnRequest Flow and Verification Points

Simplified diagram for SP-initiated SSO:

~~~text
[Browser]               [Spring Security SP]                       [IdP]
   | GET /private                |                                    |
   |--------------------------->|                                    |
   |                            | select RelyingPartyRegistration     |
   |                            | read asserting-party metadata       |
   |                            | create AuthnRequest                 |
   |                            | sign/serialize/encode per Binding   |
   |                            | save AuthnRequest for correlation   |
   |<------ Redirect or POST form -----------------------------------|
   |-------------------------- SAMLRequest ------------------------->|
   |                            |                                    | validate:
   |                            |                                    | - SSO endpoint/Binding
   |                            |                                    | - Issuer & SP registration
   |                            |                                    | - SP signature and certificate
   |                            |                                    | - ACS, Destination, timestamps
   |                            |                                    | - ForceAuthn/NameIDPolicy...
   |                            |                                    |
   |<------------------------ login / MFA / SSO page -----------------|
   |------------------------- log in at IdP ------------------------->|
   |<------------------------ SAMLResponse ---------------------------|
   | POST SAMLResponse          |                                    |
   |--------------------------->| verify Response/Assertion          |
   |<---------------------------| create Authentication if valid      |
~~~

**Saml2WebSsoAuthenticationRequestFilter** and a **Saml2AuthenticationRequestResolver** (in Spring Security 6.x, **OpenSaml4AuthenticationRequestResolver**) cooperate to build the AuthnRequest at an endpoint typically `/saml2/authenticate/{registrationId}`. RelyingPartyRegistration provides the SSO address, protocol, EntityID, ACS, and credentials. When sent, the request context is typically saved by **Saml2AuthenticationRequestRepository** so the later callback can validate **InResponseTo**.

Creating/signing the AuthnRequest is the **outbound path to the IdP**; receiving/validating SAMLResponse at the ACS is the **return path to the SP**, handled by different validators. This topic focuses on the **outbound** path, yet you still must persist the right request ID to verify the **inbound** return path.

### Two Independent Verification Directions

| Layer | Actor | Data Source | Question |
| --- | --- | --- | --- |
| **Pre-dispatch** | SP / dev team | IdP metadata, IdP onboarding policy, SP registration | Are we sending the right identifiers/endpoint/binding and using a valid key/algorithm? |
| **Upon receipt** | IdP | Registered SP metadata/config, key trust, IdP policy | Does the request match an authorized SP, valid signature, and compliant timestamps/ACS/policy? |
| **Upon Response return** | SP | IdP verification credential, saved AuthnRequest, and SAML profile | Was the SAMLResponse/Assertion issued by a trusted IdP for the right request and SP? |

A system can pass step one yet fail step two due to out-of-sync IdP configuration or product-specific policies not inferable from metadata XML.

## 3. IdP Metadata: What Must Be Read Accurately?

IdP metadata is typically an XML document containing an **EntityDescriptor** with an **IDPSSODescriptor**. Validate the document source and pick the **right entityID/role**. Fields directly relevant to AuthnRequest:

| Metadata Field | Meaning for Outbound Requests | Usage |
| --- | --- | --- |
| **EntityDescriptor.entityID** | Logical identifier of the **IdP**; distinguish from the metadata download URL. | Matches asserting party ID and later Response issuer; never confuse with AuthnRequest Issuer. |
| **IDPSSODescriptor.protocolSupportEnumeration** | IdP role supports SAML2 protocol. | Look for **urn:oasis:names:tc:SAML:2.0:protocol**. |
| **SingleSignOnService.Binding** | Which binding the IdP accepts AuthnRequests over: HTTP-Redirect, HTTP-POST... | Pick a binding supported by both Spring and the IdP. |
| **SingleSignOnService.Location** | **IdP's** endpoint where the SP sends requests. | Target destination and normally **AuthnRequest.Destination**. |
| **WantAuthnRequestsSigned** | IdP advertises preference/requirement for signed AuthnRequests. | If true, SP needs signing credentials and IdP must trust SP's cert; if omitted, metadata default is false, though live policy must still be checked. |
| **NameIDFormat** | NameID formats advertised as supported by the IdP. | Consider when customizing **NameIDPolicy.Format**; do not request emailAddress by default. |
| **KeyDescriptor use=signing** | Public certificate for the **SP to verify IdP-signed messages**. | Do not confuse with **SP's private key used to sign AuthnRequests**. |
| **Extensions / SigningMethod (if present)** | May advertise supported/preferred signing algorithms depending on metadata profile. | Negotiate algorithms with IdP and configure Spring; never guess SHA1 for compatibility. |
| **validUntil / cacheDuration** | Metadata validity expiration and caching hints. | Never rely on expired configs; maintain refresh and rotation workflows. |
| **SingleLogoutService** | SAML logout endpoint. | Not the endpoint receiving AuthnRequests; never pick it by mistake as SSO Location. |

**Not every policy lives in metadata.** An IdP may require an exact SP entityID, ACS URL allowlist, RelayState rules, specific signing algorithms, MaximumAuthenticationAge, MFA/conditional access, RequestedAuthnContext, tenant restrictions, or binding constraints. Those requirements must come from **IdP documentation/administrators** and real testing.

### Illustrative IdP Metadata XML

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml/metadata"
    validUntil="2030-01-01T00:00:00Z">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">

    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso/redirect"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso/post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**For structural learning only**, not metadata to import into production; IDPSSODescriptor omits signing KeyDescriptors in the sample because real certificates are not supplied. Use real metadata from a trusted IdP with complete certificates for SSO to actually operate.

**Interpretation:** the IdP supports **two SSO endpoints with distinct bindings**, requires signed AuthnRequests, and advertises persistent NameID support. If the SP selects HTTP-Redirect, Destination should match **/saml/sso/redirect** and the signature must be generated per Redirect binding, **not an XML ds:Signature inside the payload instead**.

## 4. SP Metadata and IdP-Side Policy

The IdP does not read only its own metadata. It also needs **SP metadata/registration** to know who is permitted to request login and where to return Responses.

SP metadata has an **EntityDescriptor with SPSSODescriptor**, containing:

- **SP entityID:** SP identifier; usually appears in **AuthnRequest.Issuer**.
- **AssertionConsumerService (ACS):** URL/index/binding to which the IdP is allowed to send SAMLResponses; published by SP and allowlisted by IdP.
- **SP KeyDescriptor use=signing:** **SP** public certificate for the IdP to verify signed AuthnRequests.
- **SP KeyDescriptor use=encryption:** certificate used if the IdP needs to encrypt Assertions for the SP; not used by default to verify AuthnRequest signatures.
- **AuthnRequestsSigned:** SP advertises that it signs AuthnRequests when matching policy/credentials apply.
- **WantAssertionsSigned:** SP's expectation for signatures on Assertions/Responses; distinct from the IdP's WantAuthnRequestsSigned.

**Never swap keys:**

| Task | Who Signs / Holds Private Key? | Who Verifies / Holds Public Key? |
| --- | --- | --- |
| SP builds **signed AuthnRequest** | **SP** holds private signing key. | **IdP** verifies with SP's registered public signing certificate. |
| IdP builds **signed SAMLResponse/Assertion** | **IdP** holds private signing key. | **SP** verifies with IdP's trusted public verification certificate. |
| IdP encrypts Assertion for SP | IdP uses **SP public encryption key**. | SP uses **SP private decryption key**. |
| Federation/partner signs metadata | Metadata publisher/federation holds private metadata-signing key. | Consumer trusts signer certificate via approved trust anchor. |

**Having a public certificate in XML does not by itself establish trust.** The IdP must receive the SP certificate through a trusted onboarding process; likewise, the SP must obtain IdP metadata from a trusted source. Key rollover, expiry monitoring, and algorithm policies are required.

### Interaction Between the Two Signing Flags

| IdP WantAuthnRequestsSigned | SP AuthnRequestsSigned | What Must Be Confirmed |
| --- | --- | --- |
| true | true | SP has valid private key, IdP knows public certificate, signature matches binding and algorithm. |
| true | false | **Configuration mismatch**; IdP normally rejects unsigned AuthnRequests. |
| false or absent | true | Usually accepted if IdP trusts the key/allows signed requests; check specific policy. |
| false or absent | false | Can send unsigned if IdP policy permits. This is **not** proof the IdP always accepts it. |

**WantAuthnRequestsSigned=false does not prohibit signed requests**. It only indicates the IdP does not advertise a mandatory requirement via that attribute; separate IdP policies may still differ. Conversely, **AuthnRequestsSigned=true** cannot be merely a string in metadata if Spring does not actually sign.

## 5. AuthnRequest Fields That Must Be Cross-Checked

XML sample to view structure, **unsigned**, with some optional elements omitted:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_12345"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:00Z"
    Destination="https://idp.example.org/saml/sso/redirect"
    AssertionConsumerServiceURL="https://app.example.com/login/saml2/sso/corp"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">

  <saml:Issuer>
    https://app.example.com/saml2/service-provider-metadata/corp
  </saml:Issuer>

  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      AllowCreate="true"/>
</samlp:AuthnRequest>
~~~

**Not yet a complete/signed SAML message.** To log in, Spring/IdP must use real metadata, certificates, and profiles; values here are illustrative and must not be taken as advice to hard-code a static ID/timestamp.

### Field-by-Field Cross-Check Table

| AuthnRequest Field | Right Source to Compare | Rule / Meaning |
| --- | --- | --- |
| **ID** | SP generator, request repository. | Unique/unpredictable within required scope; used for InResponseTo when IdP returns Response. |
| **Version="2.0"** | SAML 2.0 protocol. | Never use another version arbitrarily. |
| **IssueInstant** | SP clock and IdP allowed skew. | Valid UTC timestamp; avoid stale or far-future requests; synchronize NTP. |
| **Destination** | Selected **SingleSignOnService.Location** from IDPSSODescriptor. | Normally must match the receiving SSO endpoint; never use ACS or metadata download URL. |
| **Issuer** | **SP EntityDescriptor.entityID** registered at IdP. | **Not IdP entityID**, not login username, and not registrationId. |
| **AssertionConsumerServiceURL** | **SP AssertionConsumerService Location** permitted by IdP. | Public HTTPS URL; must match environment/tenant/registration. |
| **AssertionConsumerServiceIndex** | ACS **index** in SP metadata trusted by IdP. | Used when asking IdP to pick ACS by index; never invent an index outside metadata. |
| **ProtocolBinding** | Binding SP expects for **Response at ACS**, if specified. | **Not** the binding used to send AuthnRequest to the IdP. |
| **ForceAuthn** | IdP policy and fresh authentication requirement. | true asks IdP to re-authenticate per profile; verify in practice whether IdP supports it and satisfies business needs. |
| **IsPassive** | IdP policy for passive SSO. | true asks IdP not to interact with user; may fail if interactive prompt/MFA is needed. |
| **NameIDPolicy.Format** | IDPSSODescriptor.NameIDFormat and partner agreement. | Do not request unsupported formats; do not treat emailNameID as an immutable user ID. |
| **RequestedAuthnContext** | Authn contexts/classes supported/issuable by IdP. | Does not “enable MFA” via an arbitrary string; IdP decides authentication. |
| **Scoping** | IdP/IdP proxy contract if used. | Can affect proxying/federation chains; requires separate testing. |

**Important:** AuthnRequest.**ProtocolBinding** describes the **binding for SAMLResponse back to the ACS** (e.g., HTTP-POST); it does not mean the AuthnRequest itself must be sent via HTTP-POST. A very common and completely valid flow is **AuthnRequest via HTTP-Redirect**, **Response back via HTTP-POST**.

### ACS Index vs. ACS URL

If using **AssertionConsumerServiceIndex**, the IdP looks up the endpoint from **SPSSODescriptor** by index. If using **AssertionConsumerServiceURL** (and ProtocolBinding when appropriate), the request must match an endpoint allowlisted by the IdP. Per SAML AuthnRequest rules, **do not arbitrarily combine ACS index with ACS URL/ProtocolBinding in the same request**; consult the relevant profile and implementation. SP metadata is the source for the IdP to verify valid ACS values, not a browser-selected URL.

## 6. HTTP-Redirect and HTTP-POST: Two Dispatch Methods, Two Signing Methods

The exact same AuthnRequest XML can be transported via **HTTP-Redirect** or **HTTP-POST**, yet **packaging and signatures differ**.

### 6.1. HTTP-Redirect Binding

For Redirect, the SP typically:

1. Constructs AuthnRequest XML, possibly with customized fields.
2. Applies DEFLATE per binding rules, then Base64-encodes and URL-encodes into **SAMLRequest**.
3. If signing is needed: builds canonical data per binding rules over URL-encoded parameter pairs in the order **SAMLRequest**, **RelayState if present**, **SigAlg**.
4. Signs that byte string with the **SP private key**, URL-encoding the Base64 signature into **Signature**.
5. Returns **HTTP 302** sending the browser to **IdP SingleSignOnService.Location** with the corresponding query params.

Example URL shape (illustrative only, no real signature):

~~~text
https://idp.example.org/saml/sso/redirect
  ?SAMLRequest=<URL_ENCODED_DEFLATED_BASE64_AUTHNREQUEST>
  &RelayState=<URL_ENCODED_STATE>
  &SigAlg=<URL_ENCODED_SIGNATURE_ALGORITHM_URI>
  &Signature=<URL_ENCODED_BASE64_SIGNATURE>
~~~

**Do not** copy the example URL and treat it as a valid SAMLRequest. In Redirect binding, **the signature protects the prescribed query string**, so do not look for **ds:Signature inside the XML**. When verifying, the IdP must use the **received URL-encoded values** in the exact signing order; decoding and re-URL-encoding differently can break the signature.

**RelayState** (if present) is included in the signed data per Redirect binding rules. Do not treat RelayState as AuthnRequest.ID; never turn RelayState into an open redirect or infinitely reusable secret key. SAML Redirect is subject to proxy/browser URL limits; depending on field count and policy, the IdP may require switching to POST.

### 6.2. HTTP-POST Binding

For POST, the SP typically embeds Base64-encoded AuthnRequest XML into an auto-submitting HTML form sent to the **IdP SingleSignOnService** with HTTP-POST binding.

~~~html
<form method="post" action="https://idp.example.org/saml/sso/post">
  <input type="hidden" name="SAMLRequest"
         value="BASE64_XML_PLACEHOLDER"/>
  <input type="hidden" name="RelayState"
         value="OPAQUE_STATE_PLACEHOLDER"/>
</form>
~~~

This is an **illustrative form**, not a valid request. When SAML XML requires signing under standard POST binding, the signature resides in **XML ds:Signature** (per the XML Digital Signature profile), distinct from Redirect's **Signature query param**. Certain special profiles like **HTTP-POST SimpleSign** have their own rules; **do not confuse them** with default HTTP-POST XML Signature.

### Comparison Table

| Characteristic | Redirect AuthnRequest | POST AuthnRequest |
| --- | --- | --- |
| HTTP | Browser **GET** to IdP SSO endpoint. | Browser **POST** form to IdP SSO endpoint. |
| IdP Config | SingleSignOnService Binding=HTTP-Redirect. | SingleSignOnService Binding=HTTP-POST. |
| SAMLRequest Param | DEFLATE + Base64 + URL encoding. | Base64 XML in form field. |
| Common Signature | Query **SigAlg + Signature** protecting SAMLRequest and RelayState (if present). | **ds:Signature** inside XML, per binding/profile. |
| QA Focus | Query URL-encoding, raw query signature, right URL, no accidental stripping of SigAlg/Signature. | XML signature/canonicalization, right endpoint/action, submission, and session. |
| Frequent Error | IdP demands signed Redirect, yet request has only unsigned SAMLRequest. | IdP demands POST XML signature, yet SP generates Redirect signature. |

**Do not re-implement DEFLATE/signature/XMLSig with a few lines of application code**. Spring Security/OpenSAML already handle bindings and signing; when debugging, inspect payloads in a sandbox against policy rather than disabling signature verification.

## 7. AuthnRequest Signing and Algorithms: Three Conditions Required

An AuthnRequest accepted by an IdP requiring signatures normally needs all three simultaneously:

1. **SP actually signs** with the private key matching the public certificate registered at the IdP.
2. **Signature is placed appropriately for the binding** (Redirect query signature or POST XML Signature) and covers the right data.
3. **Algorithm is permitted by the IdP** (commonly RSA-SHA256 or a modern contracted algorithm), with valid certificate chain and rotation.

If any condition is missing, the AuthnRequest XML may look “field-complete” yet be rejected by the IdP with **InvalidSignature**, **SignatureRequired**, **UntrustedRelyingParty**, **UnsupportedAlgorithm**, or equivalent vendor errors.

### RSA-SHA256 and Other Algorithms

Spring Security chooses an appropriate signing algorithm by default (docs cite **rsa-sha256** as the typical default). The IdP may publish signing algorithms via metadata extensions or specify them in the contract. Do not downgrade to **RSA-SHA1/DSA-SHA1** just “for compatibility” if security policy forbids them; weak algorithms must be excluded under current security requirements.

If the application needs another algorithm, in suitable Spring Security versions you can configure **assertingPartyMetadata.signingAlgorithms(...)** or use approved metadata containing SigningMethod. Always test the real binding/algorithm against the IdP. **Metadata may only advertise preferences, without guaranteeing every key/algorithm works in every binding.**

### Certificates and Private Keys

- **SP private key:** must be stored securely in a secret manager/keystore/KMS/HSM matching architecture; never commit to source code, container images, or Google Sheets.
- **SP public signing certificate:** delivered to the IdP during onboarding; may be published in SPSSODescriptor KeyDescriptor use=signing.
- **IdP public verification certificate:** used by the SP to verify SAMLResponse/Assertion; **never used to sign AuthnRequests**.
- **Rollover:** the IdP must trust the new SP certificate before the SP switches to the new key; maintain an overlap window and valid rollback.
- **Algorithm/signature:** having just a `.crt` file is insufficient; the private key must match the public key and a Spring-supported algorithm/format.

**Never use a reverse proxy's TLS certificate as the SP signing credential merely because the hostname matches.** TLS certificates and SAML signing certificates serve different roles; they might coincide in certain setups, yet that must be explicitly designed/agreed rather than assumed.

## 8. How Does Spring Security Use Metadata to Issue AuthnRequests?

In a Servlet app, **spring-security-saml2-service-provider** uses **RelyingPartyRegistration**. A registration holds both SP and IdP details:

| Field | Which Side? | Effect on Outbound AuthnRequest |
| --- | --- | --- |
| **registrationId** | SP application's config lookup key. | Selects partner at `/saml2/authenticate/{registrationId}`. |
| **entityId** | SP | Populates **AuthnRequest.Issuer**. |
| **assertionConsumerServiceLocation** | SP | Populates **AssertionConsumerServiceURL** and matches IdP allowlist. |
| **signingX509Credentials** | SP | Holds private key/public certificate for **signing AuthnRequests** when needed. |
| **assertingPartyMetadata.entityId** | IdP | Identifies the IdP; never inserted in place of SP Issuer. |
| **assertingPartyMetadata.singleSignOnServiceLocation** | IdP | Selects target endpoint and usually populates **AuthnRequest.Destination**. |
| **assertingPartyMetadata.singleSignOnServiceBinding** | IdP | Binding SP uses to send request: REDIRECT or POST per real support. |
| **assertingPartyMetadata.wantAuthnRequestsSigned** | IdP | Indicates signing requirement; Spring uses it to decide issuance per config/version. |
| **assertingPartyMetadata.signingAlgorithms** | IdP | Influences signing algorithm selection when used. |
| **assertingPartyMetadata.verificationX509Credentials** | IdP | Used later to verify IdP responses, not for SP request signing. |

**RelyingPartyRegistrationRepository** stores permitted registrations. It is not a user store and does not issue Assertions. Spring Security SAML login is a **Service Provider** integration; the IdP must still be deployed/operated separately.

### Why Must IdP Metadata Be Loaded from a Trusted Source?

If an attacker can swap the IdP metadata URL at will, they can alter Destination endpoints, Issuers, and certificates inside the registration. Therefore:

- Load IdP metadata only from organization-approved URLs/files;
- Use HTTPS and proper trust; if policy mandates **signed metadata**, verify its signature against a pre-known **metadata trust anchor**;
- Never let the browser choose the metadata URL, signing key, or SSO endpoint;
- Inspect **entityID**, **IDPSSODescriptor role**, **SingleSignOnService**, **validUntil/cacheDuration**, and certificate rotation;
- Review metadata changes procedurally rather than auto-accepting unknown IdPs as partners.

**Successfully parsing XML does not mean metadata signatures were verified.** Newer Spring Security releases have dedicated APIs for managing signed metadata/refresh; do not copy Spring Security 7 APIs into Boot 3.x without checking compatibility.

## 9. Sample Config: Spring Boot 3.3.5 / Java 17 Signed AuthnRequest

Example illustrating an **SP** application integrating with an IdP that requires signed AuthnRequests. This sample works only with **real IdP metadata**, **real SP private key/certificate**, and the IdP having the SP entityID and ACS properly registered.

### 9.1. Maven

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
    <artifactId>outbound-authnrequest-demo</artifactId>
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

### 9.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-saml-signing-private.pem"
                  certificate-location: "file:/run/secrets/sp-saml-signing-public.crt"
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"

server:
  port: 8080
~~~

**corp** is the registrationId. **SAML_IDP_METADATA_URI** is the real approved IdP metadata URL. The **/run/secrets/** path only illustrates a secret-mount layout; replace with actual paths per OS/container. Spring Boot reads the **SP signing private key + matching public X.509 certificate**, not the IdP verification certificate.

**Note:** when IdP metadata sets **WantAuthnRequestsSigned=true**, signing credentials must be ready and the IdP must have the **SP public certificate** registered. If your metadata has WantAuthnRequestsSigned=false yet organizational policy still requires signing, align IdP registration/policy and Spring config rather than flipping a local flag and assuming the IdP accepts it.

If the IdP allows only **HTTP-POST AuthnRequest**, the registration must select **SingleSignOnService.Binding=POST** from metadata/negotiation. Do not invent a POST URL by changing the path of a Redirect endpoint.

### 9.3. Application Class

**src/main/java/com/example/outbound/OutboundApplication.java**

~~~java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboundApplication.class, args);
    }
}
~~~

### 9.4. SecurityFilterChain

**src/main/java/com/example/outbound/SecurityConfig.java**

~~~java
package com.example.outbound;

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

**Explanation:** Spring Security uses the configured registration, generates AuthnRequests at **/saml2/authenticate/corp**, handles Responses at the typical ACS **/login/saml2/sso/corp**, and publishes SP metadata at **/saml2/metadata/corp**.

### 9.5. Simple Controller

**src/main/java/com/example/outbound/DemoController.java**

~~~java
package com.example.outbound;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Outbound AuthnRequest SP ready";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return "NameID=" + user.getName();
    }
}
~~~

Run in the folder containing `pom.xml` once real IdP metadata and signing files are present:

~~~bash
mvn spring-boot:run
~~~

Verifiable outcomes:

- **GET http://localhost:8080/** returns exactly **Outbound AuthnRequest SP ready** if the app starts successfully.
- **GET http://localhost:8080/saml2/metadata/corp** outputs **SPSSODescriptor** from registration `corp`. Verify **SP entityID, ACS, and signing KeyDescriptor** are accurate; do not mistake this for IdP metadata.
- **GET http://localhost:8080/saml2/authenticate/corp** initiates an AuthnRequest to the IdP SSO endpoint. Redirect or POST depends on the IdP binding configuration.
- **GET http://localhost:8080/me** starts the SAML flow if unauthenticated; only when the IdP accepts the request and Spring verifies a valid Response does it return **NameID=<IdP-issued value>**. There is no fixed NameID/response.

**Without real IdP metadata and a private key, the example will not log in on its own**. That is the expected boundary of an SP, not a reason to disable signature verification.

## 10. Customizing AuthnRequest and Re-Verifying After Every Change

Spring Security 6.x enables customizing the OpenSAML AuthnRequest via **OpenSaml4AuthenticationRequestResolver**. For instance, the IdP may allow/require **ForceAuthn=true** in high-security scenarios.

This is an **additional bean** in the same Spring Boot 3.3.5 application above; not a standalone Java class run via `javac`:

**src/main/java/com/example/outbound/RequestCustomizationConfig.java**

~~~java
package com.example.outbound;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class RequestCustomizationConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        var registrationResolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);
        var resolver =
                new OpenSaml4AuthenticationRequestResolver(registrationResolver);

        resolver.setAuthnRequestCustomizer(context ->
                context.getAuthnRequest().setForceAuthn(true));

        return resolver;
    }
}
~~~

**Explanation:** This bean supplies a resolver so Spring Security produces an **AuthnRequest with ForceAuthn=true**. The framework still manages signing/Binding/registration per configuration; **ForceAuthn is not a signature** and does not guarantee the IdP will enforce MFA. If customizing Issuer, Destination, or ACS, check against metadata and the IdP allowlist; if modifying XML fields **after signing**, signatures can break. The safe sequence is **customizing the message before the framework signs it**, rather than rewriting URL/form output in a late filter.

**Important version note:** Spring Security 6.x uses OpenSaml4AuthenticationRequestResolver in many versions; newer docs may use **OpenSaml5AuthenticationRequestResolver**. Match classes/imports to your actual Spring Security version. This example targets **Boot 3.3.5/Security 6.x**; do not port verbatim to Spring Security 7.x.

### Customized Fields and Risks

| AuthnRequest Change | Field / Element | Additional Verification |
| --- | --- | --- |
| Require re-login | ForceAuthn=true | Does IdP accept and interpret policy properly? Compatible with IsPassive? |
| Suppress login UI | IsPassive=true | IdP may return NoPassive error if interaction is needed. |
| Pick NameID | NameIDPolicy.Format/AllowCreate | Does IdP support format? Is there a durable identifier agreement? |
| Require authn context | RequestedAuthnContext | Does IdP support corresponding class/mechanism? Not automatic MFA. |
| Change Destination | AuthnRequest.Destination | Matches selected IdP SingleSignOnService Location? |
| Change Issuer | AuthnRequest.Issuer | Matches SP entityID registered at IdP? |
| Change ACS | AssertionConsumerServiceURL / Index | Present in SP metadata and IdP allowlist? |
| Switch Redirect/POST | Asserting party SSO binding | Right SSO endpoint and signature placement per Binding? |
| Change SigAlg | Registration signing algorithm | Does IdP trust/allow algorithm? Is SP key compatible? |

**Never let end users directly dictate Destination, Issuer, ACS, signing key, or algorithm** via query parameters. Those are trusted values governed by partner configuration.

## 11. Operational Outbound Verification Process

A test must never conclude “valid” merely because the browser redirected. Follow this sequence:

### A. Freeze the Partner Contract

1. Record **IdP entityID**, trusted metadata URL/metadata version, and policy checksum/version.
2. Select **SingleSignOnService** with matching Binding and Location; never guess from a login page URL.
3. Lock down **WantAuthnRequestsSigned**, signing algorithm, SP certificate fingerprint (if agreed), and whether IdP policy mandates signed requests.
4. Lock down **SP entityID, ACS URL/binding/index**, SP metadata delivered to IdP, NameIDFormat, and custom parameters.
5. Document dedicated policies: ForceAuthn, IsPassive, RequestedAuthnContext, RelayState, skew, max request age, tenant/account restrictions.
6. Separate **dev/test/prod** environments: each environment may have distinct entityIDs, ACS URLs, keys, and SSO endpoints.

### B. Verify Spring Configuration Before Sending

1. Verify **RelyingPartyRegistrationRepository** has valid registrationIds without accidentally assigning another IdP.
2. Check resolved **SP entityId** and **assertionConsumerServiceLocation**, especially behind proxies.
3. Check **asserting party entityId**, SSO URL, Binding, and WantAuthnRequestsSigned loaded from metadata/policy.
4. Verify **signingX509Credentials** hold a matching SP private key and public cert with secure file permissions; confirm IdP trusts the cert.
5. Verify signing algorithms are allowed; exclude weak/incompatible algorithms per policy.
6. Record **AuthnRequest.ID**, registrationId, and timestamp in a secure correlation store (never log private keys, secrets, or raw assertions).

### C. Observe the Actual AuthnRequest in Sandbox

1. Open **/saml2/authenticate/corp** from an unauthenticated sandbox browser.
2. If Redirect, observe HTTP **302 Location** to the IdP SSO URL; verify **SAMLRequest** is present, and when signing is required, **SigAlg** + **Signature** exist (RelayState as used).
3. If POST, observe the auto-submit form, **action URL**, **SAMLRequest**, and XML signature when needed.
4. Use a dedicated SAML protocol tool in the **test environment** to inspect decoded XML, confirming Version/IssueInstant/ID/Issuer/Destination/ACS/ProtocolBinding and custom fields.
5. Verify **the signature using the IdP-approved SP public certificate** per algorithm and binding. Never verify with an arbitrary cert extracted from an untrusted request.
6. Check UTC timestamps and skew; check proxy host/scheme/port; never use localhost as a production ACS.

**Security note:** devtools/HTTP traces can contain login info, RelayState, and SAMLResponse. Retain only sanitized evidence, restrict access, and never share raw production payloads in chat/tickets.

### D. Confirm IdP Acceptance

A real AuthnRequest can be rejected by the IdP despite a valid signature if the SP is unregistered, the ACS is not allowlisted, or ForceAuthn/NameIDFormat policies fail. Use IdP/sandbox logs to confirm:

- Arrived at the exact **SSO endpoint and binding**;
- **SP issuer** was recognized;
- **Signature** verified cleanly with the trusted SP key;
- **ACS** is permitted, and request ID and IssueInstant are valid;
- NameID/AuthnContext/ForceAuthn/IsPassive policies were accepted;
- Once the user authenticated, the IdP issued the Response to the **right ACS** and SP verified Response/InResponseTo.

If the IdP returns an error, distinguish **request rejected at IdP** from **Response rejected back at SP**. The two errors lie in opposite directions and require different diagnostics.

## 12. Standalone Java 17: Auditing Metadata and AuthnRequest Contract

To understand the principle of comparing **IdP metadata against the outgoing message**, the example below uses **plain JDK 17 Java** to parse static metadata XML written inline, locate an **IDPSSODescriptor**, inspect **WantAuthnRequestsSigned** and a **SingleSignOnService**, and compare against simulated SP config.

**Mandatory limits:** this **only checks configuration fields**; it performs no XML signature verification, trust-bootstrap, XSD/profile validation, DEFLATE, Base64, certificate chains, IdP-side ACS allowlists, or response verification. **Never deploy it to production in place of Spring Security/OpenSAML**, and never conclude the IdP accepted a request when the program prints PASS.

**OutboundContractDemo.java**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class OutboundContractDemo {
    private static final String MD =
            "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final String REDIRECT =
            "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect";

    public static void main(String[] args) throws Exception {
        String metadata = """
                <md:EntityDescriptor
                  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                  entityID="https://idp.example.org/metadata">
                  <md:IDPSSODescriptor
                    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
                    WantAuthnRequestsSigned="true">
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
                new InputSource(new StringReader(metadata)));
        Element entity = document.getDocumentElement();
        NodeList roles = entity.getElementsByTagNameNS(
                MD, "IDPSSODescriptor");
        Element idpRole = (Element) roles.item(0);
        Element sso = (Element) idpRole.getElementsByTagNameNS(
                MD, "SingleSignOnService").item(0);

        String configuredIdp = "https://idp.example.org/metadata";
        String outgoingDestination = "https://idp.example.org/sso";
        boolean spHasSigningKey = true;
        boolean requestActuallySigned = true;
        boolean wantSigned = Boolean.parseBoolean(
                idpRole.getAttribute("WantAuthnRequestsSigned"));

        boolean issuerMatches = configuredIdp.equals(
                entity.getAttribute("entityID"));
        boolean bindingMatches = REDIRECT.equals(sso.getAttribute("Binding"));
        boolean destinationMatches = outgoingDestination.equals(
                sso.getAttribute("Location"));
        boolean signingPolicyMatches = !wantSigned
                || (spHasSigningKey && requestActuallySigned);

        boolean pass = issuerMatches && bindingMatches
                && destinationMatches && signingPolicyMatches;

        System.out.println("IdP entity matched: " + issuerMatches);
        System.out.println("Redirect binding matched: " + bindingMatches);
        System.out.println("Destination matched: " + destinationMatches);
        System.out.println("Signed request required: " + wantSigned);
        System.out.println("Signing policy matched: " + signingPolicyMatches);
        System.out.println("Outbound contract: " + (pass ? "PASS" : "FAIL"));

        boolean wrongDestination = "https://other.example.org/sso"
                .equals(sso.getAttribute("Location"));
        System.out.println("Wrong destination accepted: " + wrongDestination);
    }
}
~~~

Compile and run in the folder with the file:

~~~bash
javac OutboundContractDemo.java
java OutboundContractDemo
~~~

**Exact stdout:**

~~~text
IdP entity matched: true
Redirect binding matched: true
Destination matched: true
Signed request required: true
Signing policy matched: true
Outbound contract: PASS
Wrong destination accepted: false
~~~

**Explanation:** “Outbound contract: PASS” means only that the simulated static fields are **logically consistent**. The program **does not generate a real signature** (`requestActuallySigned` is assumed), knows nothing of IdP policies outside metadata, lacks SP issuer/ACS inputs, and has no HTTP transport. **In real production, only the IdP can verify an AuthnRequest signature, and Spring/OpenSAML handle the SAML protocol.**

If `outgoingDestination` is changed to **https://other.example.org/sso**, Destination matching must fail. If `wantSigned=true` while `spHasSigningKey=false` or `requestActuallySigned=false`, `signingPolicyMatches=false`. These negative conditions must become real **test cases** during implementation.

## 13. Positive/Negative Test Suite

To test each condition individually, use an **IdP/SP sandbox** with approved test metadata/keys. When testing signature mismatch, construct the request **with the right binding** and sign with a test key; do not tamper with a signed URL query and then rely on a generic error to pinpoint the root cause.

| # | Outbound AuthnRequest Scenario | Expected Outcome |
| --- | --- | --- |
| 1 | SSO Location/Binding matches metadata, valid SP issuer and ACS, request signed per policy, valid timestamp | IdP can **accept the request** and proceed with login. |
| 2 | IDPSSODescriptor WantAuthnRequestsSigned=true, SP sends unsigned request | **Rejected** for missing signature. |
| 3 | Signed Redirect has SAMLRequest yet lacks SigAlg/Signature | **Rejected** when IdP requires signed requests. |
| 4 | Signed POST sent when IdP expects Redirect query signature on Redirect endpoint | **Rejected** due to binding/signature placement mismatch. |
| 5 | SP uses a private key not matching the certificate registered at IdP | **Rejected** as invalid/untrusted signature. |
| 6 | SP picks a signing algorithm forbidden by IdP policy | **Rejected** as unsupported/weak algorithm. |
| 7 | AuthnRequest.Destination is SP ACS instead of IdP SSO Location | **Rejected** as Destination/endpoint mismatch. |
| 8 | Redirect AuthnRequest sent to an SSO endpoint configured only for POST | **Rejected** as binding mismatch. |
| 9 | AuthnRequest.Issuer is IdP entityID instead of SP entityID | **Rejected** as unknown/invalid SP. |
| 10 | Valid SP issuer, yet unregistered at the IdP | IdP typically **rejects unknown SP**. |
| 11 | Valid SP issuer, ACS URL points to another tenant/application | **Rejected** as ACS not in allowlist. |
| 12 | ACS uses `http://internal` instead of public HTTPS URL | **Rejected** unless allowed by IdP; fix proxy/config. |
| 13 | AssertionConsumerServiceIndex missing from IdP-trusted SP metadata | **Rejected** or ACS index error. |
| 14 | ProtocolBinding specifies HTTP-Artifact, yet SP/IdP implement only HTTP-POST Response | **Rejected** as unsupported requested binding. |
| 15 | IssueInstant too stale/in the future per IdP policy | **Rejected** or request validity error. |
| 16 | Duplicate AuthnRequest.ID reused from before | **Rejected** per replay/duplicate ID policy. |
| 17 | NameIDPolicy.Format unsupported by IdP | **Rejected** or policy/format error status per IdP. |
| 18 | IsPassive=true when IdP requires interactive login/MFA | IdP may return **NoPassive**; never force IdP to render a form violating policy. |
| 19 | ForceAuthn=true when IdP lacks support/different policy | Must verify how IdP enforces; never assume re-authentication occurred. |
| 20 | Valid request, yet Response rejected at SP for invalid audience/recipient | Distinguish **outbound success** from **inbound Response validation failure**. |
| 21 | Two registrations for different IdPs; request uses signing cert of the other registration | **Rejected** because IdP does not trust that cert/issuer for this partner. |
| 22 | New IdP metadata rotated SSO endpoint/cert policy while SP uses old config | May be **rejected**; perform controlled metadata/trust refresh. |
| 23 | Redirect query URL-encoding altered by reverse proxy after signing | **Rejected** as invalid query signature. |
| 24 | Signed AuthnRequest uses RelayState pointing to a disallowed domain | Application must prevent **open redirect/state injection**; test end-to-end. |

**A negative test passes** when the IdP/SP rejects deliberately without issuing an out-of-policy session. Never “fix” errors by removing all signing requirements, opening wildcard ACS, or accepting arbitrary issuers.

### Verification Practices to Avoid with Production Payloads

- Never paste real SAMLRequest/SAMLResponse payloads into public web decoder sites.
- Never send private keys over chat/tickets or upload private keys to external test tools.
- Never log raw SAMLResponse, session cookies, sensitive NameID/Attributes, or full signed queries containing state.
- Never leave a debug endpoint generating unsigned AuthnRequests active in production without explicit policy.
- Never inflate clock skew to hours to bypass IssueInstant errors.

## 14. Error Table and Isolation Guide

| Symptom | First Branch to Check | Remediation |
| --- | --- | --- |
| IdP reports **SignatureRequired/Unsigned AuthnRequest** | WantAuthnRequestsSigned, signing policy, and actual wire signature. | Configure SP signing private key/certificate, confirm IdP trust and binding. |
| IdP reports **InvalidSignature** | SP certificate, algorithm, Redirect query encoding/POST XML Signature. | Check keys, certs, signing mode, and proxies; never disable verification. |
| IdP reports **Unknown SP / Invalid Issuer** | AuthnRequest.Issuer and registered SP entityID. | Align SP entityID in IdP onboarding and SP metadata. |
| IdP reports **Invalid Destination** | IdP SingleSignOnService Location, AuthnRequest.Destination. | Pick the right endpoint for the binding; never confuse with ACS URL. |
| IdP reports **Invalid ACS / Reply URL mismatch** | ACS URL/index and SP metadata. | Fix IdP allowlist, public HTTPS URL, path, and reverse proxy. |
| IdP reports **Unsupported Binding** | HTTP-Redirect/POST request binding, Response ProtocolBinding. | Distinguish the two binding directions and pick config published by IdP. |
| IdP reports **Unsupported NameIDFormat** | NameIDPolicy.Format and IDPSSODescriptor.NameIDFormat. | Agree on format with IdP; never force emailAddress if unsupported. |
| IdP reports **NoPassive** | IsPassive=true and login/MFA requiring interaction. | Change passive requirement or UX; never force IdP to violate policy. |
| IdP prompts for fresh authentication | ForceAuthn, IdP session/MFA policy. | Re-test at IdP; ForceAuthn alone does not guarantee MFA. |
| Request contains **http://internal:8080** in production | BaseUrl/forwarded headers/ACS/entityID. | Fix reverse proxy and metadata before signing/sending requests. |
| Signed Redirect valid locally yet fails via LB | URL encoding/query normalization, proxy rewriting. | Inspect request at final egress boundary and avoid modifying signed queries post-signing. |
| New SP cert active yet IdP still trusts old key | SP signing credential rotation and IdP certificate enrollment. | Roll out with overlap; notify IdP before switching private key. |
| IdP accepted request yet Spring still fails login | Response issuer/signature/audience/recipient/InResponseTo. | Debug the **IdP → SP** direction rather than looking only at outbound AuthnRequest. |

**Never conclude “Spring is broken” from a generic SAML status alone.** Check state and timing: was an HTTP redirect/form sent, did the IdP receive it, did failure occur during request signature verification or Response processing, and is the right `registrationId` active?

## 15. Production Deployment Checklist

**Trust Sources and Onboarding**

- IdP metadata must come from a verified source with exact entityID and IDPSSODescriptor.
- Agreement on metadata signature checks if needed, plus refresh/rotation per validUntil/cacheDuration.
- IdP holds SP entityID/ACS allowlist, SP public signing certificate, and allowed algorithms.

**Outbound Messages**

- RegistrationId selects the right IdP; never let users directly control metadata URLs.
- SSO Location and Binding come from trusted IdP config; AuthnRequest.Destination is accurate.
- AuthnRequest.Issuer is SP entityID; ACS URL/index matches registered SP metadata.
- ProtocolBinding specifies the Response at ACS, never confused with outbound HTTP binding.
- WantAuthnRequestsSigned and SP signing credentials are consistent; when signing, match binding/signature/algorithm.
- IssueInstant/ID/ForceAuthn/IsPassive/NameIDPolicy/RequestedAuthnContext follow contract; never use hard-coded/invalid values.

**Security Operations**

- SP private key never appears in source code, logs, Docker images, or shared docs; access controls and rotation exist.
- Public HTTPS URLs, secure forwarded headers, and consistent NTP.
- AuthnRequest is stored in the proper browser context so **Response.InResponseTo** can be verified later.
- Multiple IdPs/tenants follow allowlists; never trust unverified issuers on the fly.
- Tested both positive/negative flows in sandbox and recorded sanitized technical errors.
- Keep full SAMLResponse/Assertion validation enabled: signature, issuer, audience, destination, recipient, timestamps, and replay.

## 16. Review Questions

**Question 1.** The IdP has WantAuthnRequestsSigned=true. Spring only loaded metadata and sent a Redirect without SigAlg/Signature. Are requirements met?  
**Answer:** **No.** Metadata only states policy; the SP must sign with the private key matching the IdP-trusted certificate, per Redirect binding and algorithm.

**Question 2.** Should AuthnRequest.Issuer equal IdP entityID or SP entityID?  
**Answer:** The **SP entityID** registered at the IdP. The SP issues the request; IdP entityID is the recipient's identity and the later issuer of the Response.

**Question 3.** AuthnRequest travels via HTTP-Redirect while ProtocolBinding=HTTP-POST. Is that a contradiction?  
**Answer:** **No.** Outbound request uses Redirect; ProtocolBinding asks the IdP to return the **Response via HTTP-POST to the ACS**.

**Question 4.** Is the IdP's `KeyDescriptor use=signing` the key the SP needs to sign AuthnRequests?  
**Answer:** **No.** The SP signs with the **SP private key**. The IdP's signing KeyDescriptor lets the SP verify IdP-signed messages; the IdP checks AuthnRequests using the registered **SP public certificate**.

**Question 5.** The browser was redirected to the IdP's login page; does that guarantee the IdP accepted the AuthnRequest?  
**Answer:** **No.** Redirecting only proves the request was sent; the IdP still checks issuer, signature, ACS, binding, and policy and can reject it.

**Question 6.** After enabling ForceAuthn=true, can we conclude the user re-authenticated with MFA?  
**Answer:** **No.** ForceAuthn is a protocol request; actual behavior depends on IdP policy/capabilities and must be verified via Response/AuthnContext/IdP audits.

**Question 7.** The IdP signed the Response successfully, yet the SP's original AuthnRequest went to the wrong Destination. Should you fix it by disabling Destination checks on the SP?  
**Answer:** **No.** AuthnRequest Destination must match the IdP SSO endpoint; Response Destination/Recipient must match the ACS. Fix the broken direction rather than disabling validation.

## 17. Authoritative References

1. [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): filters/resolvers, AuthnRequest repository, signing credentials, bindings, and customization. **Note that `latest` docs may be 7.x; check the 6.x version for Boot 3.3.5.**
2. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, signing credentials, issuer, ACS, OpenSAML, and SP/IdP relationships.
3. [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): reading IDPSSODescriptor and exporting SPSSODescriptor for IdP registration.
4. [Spring Boot 3.3 – Spring Security, SAML Relying Party](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): YAML properties for SP signing private-key-location, certificate-location, and asserting party.
5. [Spring Security 6.x – OpenSaml4AuthenticationRequestResolver API](https://docs.spring.io/spring-security/site/docs/6.2.x/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html): how to customize AuthnRequest in the 6.x family.
6. [OASIS SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): IDPSSODescriptor, SPSSODescriptor, SingleSignOnService, WantAuthnRequestsSigned, and KeyDescriptor.
7. [OASIS SAML 2.0 Bindings Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect query signature/DEFLATE and HTTP-POST binding.
8. [Microsoft Learn – SAML request must be signed](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/error-code-aadsts76021-request-not-signed): example scenario where the IdP rejects a request signed in the wrong place between Redirect and POST.

**Closing principle:** verifying outbound AuthnRequests means **checking trusted metadata + IdP contract + right signature/binding + real IdP testing**. **The SP being able to build an AuthnRequest does not mean the IdP will accept it**. Keep Issuer (SP entityID), Destination (IdP SSO endpoint), ACS (SP callback), signing policy, and request correlation consistent to preserve the security of the entire SAML login.
