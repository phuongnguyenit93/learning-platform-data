# Checking Issuer, Destination, and Receiving Application in SAML 2.0

> **Module:** Spring Security – federation. **Knowledge track:** SAML2 Verification. This lesson explains how to verify the IdP issuing a SAML Response, the endpoint receiving the Response, the application authorized to use the Assertion, and the corresponding login transaction. Examples use **Java 17**, Spring Boot **3.5.x**, and Spring Security **6.x** on the Servlet stack.

## 1. What Should You Understand After This Lesson?

Learners will be able to distinguish: **Issuer** is the IdP identifier; **Destination** is the URL to which the protocol Response is sent; **Audience** is the SP entity ID permitted to use the Assertion; **Recipient** is the URL receiving bearer SubjectConfirmation; and **InResponseTo** binds the result to the generated AuthnRequest. Learners should also:

- Know that expected values come from **RelyingPartyRegistration and trusted SAML metadata**, not from arbitrary HTTP parameters.
- Understand why a Response with a valid signature still must be rejected when Destination, Audience, Recipient, or transaction mismatches.
- Read XML, cross-check IdP/SP metadata, configure Spring Security, run the Java 17 example, and diagnose real-world errors.
- Perform negative testing for IdP mix-up, cross-SP replay, ACS mismatch, lost session, and request correlation.
- Distinguish successful protocol verification from post-login authorization and tenant policy.

**Prerequisites:** HTTP POST/Redirect, session cookies, HTTPS, Spring Security `Authentication` / `SecurityFilterChain`, SAML `AuthnRequest` / `Response` / `Assertion`, XML signatures, and the entity ID concept.

## 2. Four-Party Model and Trust Boundaries

SAML Web Browser SSO involves the user, browser, IdP (Asserting Party), and SP (Relying Party). The IdP authenticates the user and issues a SAML Response. The browser merely **carries** the message to the Assertion Consumer Service (ACS); the browser is not an identity-attesting party.

~~~text
User / Browser
    |
    | GET /private
    v
SP (Spring Security)
    |-- resolve RelyingPartyRegistration
    |-- generate AuthnRequest with ID
    |-- store state bound to session
    |
    +---------------> Registered IdP
                          |-- authenticate user / MFA
                          |-- issue/sign Response or Assertion
                          |
Browser <----------------+
    |
    | POST SAMLResponse
    v
SP ACS (Assertion Consumer Service)
    |
    +-- verify signing certificate of the right IdP
    +-- Issuer matches IdP entity ID
    +-- Destination matches ACS
    +-- AudienceRestriction matches SP entity ID
    +-- Recipient matches ACS
    +-- InResponseTo matches stored request
    +-- Conditions/time/replay/status valid
    |
Saml2Authentication + SecurityContext
    |
Authorization by application tenant/user/role
~~~

The diagram consists of multiple independent conditions. Passing one condition does not prove the others. **A successful SAML login** also does not automatically grant permission to view sensitive data.

## 3. Distinguishing Issuer, Destination, and Consumer

| Element | Where it appears | Matched against | Example |
| --- | --- | --- | --- |
| **Response Issuer** | `samlp:Response/saml:Issuer` | IdP entity ID in asserting party registration | `https://idp.example.org/saml` |
| **Assertion Issuer** | `saml:Assertion/saml:Issuer` | IdP entity ID per profile and trust | `https://idp.example.org/saml` |
| **Destination** | `samlp:Response/@Destination` | SP ACS URI | `https://portal.example.org/login/saml2/sso/corp` |
| **Audience** | `saml:Conditions/saml:AudienceRestriction/saml:Audience` | SP entity ID | `urn:example:portal:sp` |
| **Bearer Recipient** | `saml:SubjectConfirmationData/@Recipient` | SP ACS URI | `https://portal.example.org/login/saml2/sso/corp` |
| **InResponseTo** | `Response/@InResponseTo` and bearer confirmation | ID of stored `AuthnRequest` | `_req123` |
| **Validity** | `Conditions`, `SubjectConfirmationData` | Current time, bounded skew | `NotBefore` / `NotOnOrAfter` |

**Issuer is not ACS:** Issuer identifies the IdP signing or issuing the Assertion, not where the Response is POSTed. **Destination is not Audience:** Destination is the HTTP URL of the ACS; Audience is the logical name of the SP (entity ID), which can be a URN. **Recipient and Destination** often share the same ACS value yet apply at two different layers: protocol Response and bearer SubjectConfirmation.

### Sample Addresses Intentionally Distinct

~~~text
IdP entity ID: https://idp.example.org/saml
IdP metadata:  https://idp.example.org/metadata
SP entity ID:  urn:example:portal:sp
SP ACS URL:    https://portal.example.org/login/saml2/sso/corp
Spring registrationId: corp
~~~

The IdP entity ID and IdP metadata URL do not have to be equal. The SP entity ID is also not necessarily an endpoint fetched over HTTP. `registrationId` is Spring Security's configuration name, not SAML's `Issuer` or `Audience` field.

## 4. XML Illustrating All Constraints

The snippet below is for **reading syntax**, has no signature, and is not a valid production assertion; dates/IDs are examples.

~~~xml
<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_resp567"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:00Z"
  InResponseTo="_req123"
  Destination="https://portal.example.org/login/saml2/sso/corp">

  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="_assert789"
      Version="2.0"
      IssueInstant="2030-01-01T10:00:00Z">
    <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
    <saml:Subject>
      <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        opaque-user
      </saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_req123"
          Recipient="https://portal.example.org/login/saml2/sso/corp"
          NotOnOrAfter="2030-01-01T10:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2030-01-01T09:59:00Z"
        NotOnOrAfter="2030-01-01T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>urn:example:portal:sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
      AuthnInstant="2030-01-01T09:59:50Z"
      SessionIndex="_idp-session-42">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>
          urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Analysis:

1. `Response/Issuer` and `Assertion/Issuer` equal the expected IdP entity ID. Both must be processed per appropriate trust/profile, not just reading one string.
2. `Response/@Destination` points to the exact ACS URL for the response.
3. `AudienceRestriction` contains the SP entity ID; it **differs** from the ACS URI.
4. Bearer `Recipient` also points to the ACS; this is the condition for presenting the Assertion at the designated endpoint.
5. `Response/@InResponseTo` and `SubjectConfirmationData/@InResponseTo` use the request ID generated and stored by the SP.
6. `NotBefore/NotOnOrAfter` together with bearer expiration control validity.
7. `NameID` identifies the user within the IdP's namespace; it does not replace issuer, audience, or business permissions.
8. `StatusCode=Success` must be checked, yet does not prove on its own that the message was properly signed.

Because the example **lacks `ds:Signature`**, a real SP must reject it per SAML profile signing requirements. If an encrypted assertion is present, the SP must decrypt it with its own private key while still verifying signatures and all conditions.

## 5. Checking Issuer: Who Actually Issued It?

`Issuer` uses the SAML Assertion namespace and appears on Response or Assertion. In direct SAML Web Browser SSO, issuer usually equals the **IdP's entity ID** in `RelyingPartyRegistration.assertingPartyMetadata`.

A valid trust setup begins with:

1. An administrator approves the IdP/tenant and metadata source.
2. The SP loads or ingests verified metadata, recording the IdP entity ID and signing public certificate.
3. Spring Security creates a registration holding identifiers and verification credentials.
4. Upon receiving a Response, OpenSAML verifies the protected element's signature with the **trusted public key belonging to the IdP**, then validates issuer/registration.
5. Any unapproved discrepancy must result in authentication failure.

**Note on order:** The framework may read an unverified Issuer as a **hint** to look up an existing registration. Never treat that lookup as authentication, and never dynamically download new metadata from a browser-submitted Issuer URL.

### Forged Signatures and Issuer Mix-Up

An attacker can generate their own RSA key, sign valid XML, and fill in `Issuer=https://idp.example.org/saml`. If the SP blindly trusts the certificate embedded in the SAMLResponse, the signature will match mathematically yet the issuer has no authority. **Only use verification keys from a trusted IdP registration**; never trust a self-advertised public key inside the message.

IdP A may sign a valid response yet **not be authorized to assert identities for tenant B**. Therefore, the application must also bind registrations to tenants, user populations, and policies; a valid issuer is only one authentication condition, not authorization.

### Issuer in Response and Assertion

A Response issued by IdP A might contain an Assertion declaring Issuer B. The SP must not extract `NameID` from that Assertion and assume it belongs to A. Under standard profiles, Response/Assertion issuers must align with the trusted IdP. Signature verification must protect the exact element containing claims used to create Authentication, preventing XML Signature Wrapping. Let OpenSAML handle this rather than running XPath against an arbitrary `Assertion`.

## 6. Checking Destination: Which ACS Was the Response Sent To?

`Response/@Destination` is the target URI of the protocol message, which in Web Browser SSO HTTP-POST is normally the **Assertion Consumer Service URL**.

~~~text
SP expected ACS:
https://portal.example.org/login/saml2/sso/corp

Response Destination:
https://portal.example.org/login/saml2/sso/corp
→ URL matches; continue remaining checks.

Response Destination:
https://payroll.example.org/login/saml2/sso/payroll
→ Wrong application; Portal rejects.
~~~

Destination has presence rules under SAML Core/bindings/profiles; do not claim **every** SAML message is required to specify Destination. For browser SSO at the ACS, the SP must enforce a policy binding the exact target; if a profile allows omission, evaluate it together with signature, Recipient, Audience, and correlation, **never disabling verification globally**.

**Real-world mismatches:**

| Expected ACS | Received Destination | Assessment |
| --- | --- | --- |
| `https://portal.example.org/login/saml2/sso/corp` | Exact same URL | Right target |
| `https://portal.example.org/login/saml2/sso/corp` | `http://portal.example.org/login/saml2/sso/corp` | Wrong scheme |
| `https://portal.example.org/login/saml2/sso/corp` | `https://internal:8080/login/saml2/sso/corp` | Wrong public host/proxy |
| `https://portal.example.org/login/saml2/sso/corp` | `https://portal.example.org/login/saml2/sso/corp/` | Trailing slash difference |
| `https://portal.example.org/login/saml2/sso/corp` | `https://portal.example.org/login/saml2/sso/other` | Wrong registration |
| `https://portal.example.org/login/saml2/sso/corp` | `https://portal.example.org/old-acs` | Stale IdP registration |

Never modify Destination inside signed XML yourself; doing so breaks integrity. Never write a wildcard matcher checking only the hostname and accepting any path. Align metadata, IdP app registration, proxy, and endpoints.

### Reverse Proxy and X-Forwarded Headers

The browser may access `https://portal.example.org` while a reverse proxy forwards requests to `http://app:8080`. If SP metadata/ACS is generated from the internal host/scheme, the IdP may issue responses with an incompatible Destination.

Solution: configure an explicit public ACS, align published metadata and AuthnRequest `AssertionConsumerServiceURL`, trust forwarded headers only from **trusted proxies**, and strip corresponding headers from external clients. Do not let users influence `Host`/`X-Forwarded-Host` to alter callbacks, as that can cause host-header poisoning or open redirects.

## 7. AudienceRestriction: Which SP Is the Assertion Intended For?

`AudienceRestriction/Audience` inside `Conditions` specifies **who is authorized to consume the Assertion**. In Web Browser SSO, audience is usually the **SP entity ID**, such as `urn:example:portal:sp`, rather than an HTTP endpoint URL.

~~~xml
<saml:Conditions
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  NotBefore="2030-01-01T09:59:00Z"
  NotOnOrAfter="2030-01-01T10:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:portal:sp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Suppose Portal and Payroll use the **same IdP** and both trust the IdP's public signing certificate. An Assertion with a valid signature and matching Issuer yet Audience equal only to `urn:example:payroll:sp` must be rejected by Portal. This is the defense against **cross-SP assertion replay/token substitution**.

If one `AudienceRestriction` has multiple Audiences or an Assertion has multiple restrictions, standard SAML rules and the library validator must apply; do not simply search for the entity ID string anywhere in the XML.

**Changing an SP entity ID changes the security contract:** you must update IdP app registration, audience, metadata, and consider persistent NameIDs scoped per SP pair if the app already stores identity links. Never treat entity ID as an arbitrary label you can rename without migration.

## 8. Recipient: Where Bearer SubjectConfirmation May Be Presented

Bearer `SubjectConfirmation` typically contains `Recipient` pointing to the ACS. It restricts which endpoint may accept the bearer Assertion, along with `NotOnOrAfter` and `InResponseTo`.

~~~xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID>opaque-user</saml:NameID>
  <saml:SubjectConfirmation
    Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
      InResponseTo="_req123"
      Recipient="https://portal.example.org/login/saml2/sso/corp"
      NotOnOrAfter="2030-01-01T10:05:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
~~~

**Right Destination with wrong Recipient must still be rejected** if no confirmation satisfies the profile. Conversely, right Recipient with wrong Response Destination will also fail Response verification. Bearer NotOnOrAfter and Conditions NotOnOrAfter are two conditions that can coexist; never check one in place of the other.

An Assertion may contain multiple `SubjectConfirmation` elements. The SP must verify that a confirmation exists matching method, recipient, validity period, and correlation per profile, rather than arbitrarily grabbing the first element or skipping a field.

## 9. InResponseTo and SP-Initiated Transactions

When the SP initiates SSO, it generates an `AuthnRequest` with a random/unique ID and saves state in `Saml2AuthenticationRequestRepository`, typically bound to the HTTP session.

~~~text
SP generates AuthnRequest ID="_req123"
    |
    +-- save request + registration + session context
    |
    +-- Redirect/POST via browser to IdP
                                         |
                              IdP authenticates and issues response
                                         |
                         Response InResponseTo="_req123"
                         bearer InResponseTo="_req123"
                                         |
                              browser POSTs to ACS
                                         |
                       SP finds saved request and matches
                                         |
                  check issuer/destination/audience/recipient...
                                         |
                           only then create authenticated session
~~~

`RelayState` can help correlate request/response per binding and implementation, yet it **is not proof of identity**. Never use an arbitrary RelayState to select a tenant, account, or redirect URL outside an allowlist.

| Scenario | Response |
| --- | --- |
| SP-initiated: saved ID and InResponseTo match | Can continue validation |
| InResponseTo of a different request | Reject |
| HTTP session lost request due to timeout | Authentication failure; fix cookie/session, do not drop correlation |
| Callback routed to another node not sharing request repository | Configure appropriate shared session/repository |
| Previously used Response is re-POSTed | Reject per correlation/replay policy |
| IdP-initiated without corresponding AuthnRequest | Accept only if explicit policy permits unsolicited flow with additional safeguards |

**Login CSRF:** if an SP accepts a valid Response from an attacker in another user's browser without binding the transaction, the victim can unwittingly be logged into the attacker's account. Correlation and session handling protect against this mix-up. With IdP-initiated SSO, there is no originating request to check InResponseTo as in SP-initiated, so risks must be assessed separately.

## 10. How Does Spring Security Perform Verification?

In Servlet, `Saml2WebSsoAuthenticationFilter` receives the POST at the ACS, `Saml2AuthenticationTokenConverter` extracts the response and resolves `RelyingPartyRegistration`, creating an unauthenticated `Saml2AuthenticationToken`. `AuthenticationManager` delegates to the OpenSAML-backed AuthenticationProvider to verify signatures, decrypt, and validate Response/Assertion. A successful result is `Saml2Authentication`.

~~~text
POST /login/saml2/sso/corp
      |
Saml2WebSsoAuthenticationFilter
      |
Saml2AuthenticationTokenConverter
      |-- response XML + registration + saved request
      |
Saml2AuthenticationToken (untrusted)
      |
AuthenticationManager
      |
OpenSAML AuthenticationProvider
      |-- signature / IdP cert
      |-- Issuer + Destination
      |-- Assertion signature / Issuer
      |-- AudienceRestriction
      |-- bearer Recipient/InResponseTo
      |-- Conditions/time/status/replay
      |
Saml2Authentication (authenticated)
      |
SecurityContext + session
      |
Application role/tenant/account policy
~~~

Spring Security 6.5 has OpenSAML 4/5 processing paths depending on dependencies, while current Spring Security 7 docs typically use OpenSAML 5. Validation ordering may vary across versions, yet **trust conditions must never be skipped**. When customizing `ResponseValidator` or `AssertionValidator`, prefer composing onto the default validator. Replacing the entire validator with merely an Issuer comparison would drop essential signature, audience, time, or recipient checks.

### Selecting RelyingPartyRegistration

`registrationId` like `corp` is used for routing inside the application. Spring Security may select a registration based on the callback URL, saved AuthnRequest, or unverified Issuer as a hint within the managed set of registrations. Only after validation can the message be trusted to originate from the registered IdP. Never dynamically create a new registration from a client-supplied issuer URL or import an arbitrary public key from the Response.

## 11. Spring Boot 3.5.x and Java 17 Example

This example is a minimal Servlet SP application. It compiles with Maven, yet **requires a real test SAML IdP**, trusted IdP metadata, and accurate SP entity ID/ACS registration to complete login. The IdP URL is illustrative.

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-recipient</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
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

**src/main/java/demo/SamlRecipientApplication.java:**

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlRecipientApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlRecipientApplication.class, args);
    }

    @Bean
    RelyingPartyRegistrationRepository registrations() {
        RelyingPartyRegistration corp =
                RelyingPartyRegistrations
                    .fromMetadataLocation("https://idp.example.org/saml/metadata")
                    .registrationId("corp")
                    .entityId("urn:example:portal:sp")
                    .assertionConsumerServiceLocation(
                        "http://localhost:8080/login/saml2/sso/corp")
                    .build();
        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String index() {
            return "Open /me to start SAML authentication";
        }

        @GetMapping("/me")
        Map<String, String> me(
                @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
            return Map.of(
                "registrationId", principal.getRelyingPartyRegistrationId(),
                "authenticated", "true");
        }
    }
}
~~~

**Explanation:** `fromMetadataLocation(...)` ingests trusted IdP configuration and may fetch metadata at startup. `registrationId` is the internal name. `entityId(...)` sets the **SP entity ID** (expected Audience); `assertionConsumerServiceLocation(...)` sets the **SP ACS URL** (Destination/Recipient). `saml2Login()` delegates verification to Spring Security/OpenSAML; `/me` permits only authenticated requests and does not expose raw NameID/Assertion. The IdP must genuinely have SP entity ID `urn:example:portal:sp` and ACS `http://localhost:8080/login/saml2/sso/corp` registered. HTTP localhost is only for testing if the IdP permits it; production uses an HTTPS public ACS.

If the IdP requires the SP to sign AuthnRequests or encrypt Assertions, add the SP's signing/decryption credentials and publish the corresponding public certificates; never place the IdP's private key in the SP.

**Run:** after replacing the metadata URI with a real value and registering at the IdP:

~~~bash
mvn spring-boot:run
~~~

Visiting `http://localhost:8080/` returns the fixed response body:

~~~text
Open /me to start SAML authentication
~~~

Visit `http://localhost:8080/me` or `/saml2/authenticate/corp` to begin SSO. After a valid callback, `/me` looks like:

~~~json
{"registrationId":"corp","authenticated":"true"}
~~~

If Issuer/Destination/Audience/Recipient mismatches or state is lost, login fails and that authenticated JSON is not returned. Compare the **generated SP metadata**, IdP registration, and AuthnRequest instead of editing XML manually.

## 12. Standalone Java 17: Expected Values Are Independent

The program below runs on JDK 17. It **only simulates string checks for study after assuming the message was already verified**, and does not handle real SAML/XML Signatures, multiple Audiences, timestamps, replay, or SubjectConfirmation semantics. In production applications always use the standard Spring Security/OpenSAML validators.

**SamlTargetCheck.java:**

~~~java
import java.util.ArrayList;
import java.util.List;

public class SamlTargetCheck {
    record Expected(String issuer, String spEntityId,
                    String acs, String requestId) {}

    record Received(String responseIssuer, String assertionIssuer,
                    String destination, String audience,
                    String recipient, String inResponseTo) {}

    static List<String> errors(Expected e, Received r) {
        List<String> result = new ArrayList<>();
        if (!e.issuer().equals(r.responseIssuer())) {
            result.add("ResponseIssuer");
        }
        if (!e.issuer().equals(r.assertionIssuer())) {
            result.add("AssertionIssuer");
        }
        if (!e.acs().equals(r.destination())) {
            result.add("Destination");
        }
        if (!e.spEntityId().equals(r.audience())) {
            result.add("Audience");
        }
        if (!e.acs().equals(r.recipient())) {
            result.add("Recipient");
        }
        if (!e.requestId().equals(r.inResponseTo())) {
            result.add("InResponseTo");
        }
        return result;
    }

    static void show(String name, Expected e, Received r) {
        List<String> failures = errors(e, r);
        System.out.println(name + ": " +
                (failures.isEmpty() ? "PASS" : "FAIL " + failures));
    }

    public static void main(String[] args) {
        Expected e = new Expected(
                "https://idp.example.org/saml",
                "urn:example:portal:sp",
                "https://portal.example.org/login/saml2/sso/corp",
                "_req123");

        Received valid = new Received(
                e.issuer(), e.issuer(), e.acs(),
                e.spEntityId(), e.acs(), e.requestId());

        show("valid", e, valid);
        show("issuer", e, new Received(
                "https://other.example/saml", valid.assertionIssuer(),
                valid.destination(), valid.audience(),
                valid.recipient(), valid.inResponseTo()));
        show("destination", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                "https://other.example/acs", valid.audience(),
                valid.recipient(), valid.inResponseTo()));
        show("audience", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                valid.destination(), "urn:example:payroll:sp",
                valid.recipient(), valid.inResponseTo()));
        show("recipient", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                valid.destination(), valid.audience(),
                "https://other.example/acs", valid.inResponseTo()));
        show("request", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                valid.destination(), valid.audience(),
                valid.recipient(), "_another-request"));
    }
}
~~~

Run:

~~~bash
javac SamlTargetCheck.java
java SamlTargetCheck
~~~

**Exact stdout:**

~~~text
valid: PASS
issuer: FAIL [ResponseIssuer]
destination: FAIL [Destination]
audience: FAIL [Audience]
recipient: FAIL [Recipient]
request: FAIL [InResponseTo]
~~~

The program demonstrates that Issuer, Destination, Audience, Recipient, and InResponseTo must be compared against **five values with distinct trusted origins**. It does not prove cryptographic validity. `String.equals` here is purely illustrative; full SAML validation has rules for multiple AudienceRestriction/SubjectConfirmation elements, encoding, bindings, time, and signatures.

## 13. Negative Test Matrix and Common Pitfalls

| Test | Expected |
| --- | --- |
| Trusted IdP signing cert, Issuer/ACS/Audience/Recipient/Request match, message still valid | Proceed to create Authentication |
| Response Issuer from wrong IdP | Reject |
| Mismatched Assertion Issuer | Reject |
| Forged signature using self-advertised attacker certificate | Reject |
| Validly signed Response yet Destination points to SP B | SP A rejects |
| Matching Response Destination yet bearer Recipient is SP B | SP A rejects |
| Validly signed Assertion, Audience is SP B's entity ID | SP A rejects |
| Destination uses HTTP while official ACS is HTTPS | Reject or fail per policy |
| Destination uses internal host behind proxy | Reject; fix public ACS |
| InResponseTo mismatches pending request | Reject in SP-initiated flow |
| Callback loses session/request repository | Correlation error; do not remove check |
| IdP-initiated even though SP only permits SP-initiated | Reject per policy |
| Assertion expired / before NotBefore | Reject |
| Re-submitting an already used Response/Assertion | Reject per replay/correlation policy |
| Decryption succeeds yet signature or audience fails | Still reject |
| Matching NameID yet user is disabled | Do not grant app access |
| SAML Authentication succeeds yet lacks business permissions | 403 on protected resources |

**Note when building tests:** If you edit Audience/Destination manually *after signing*, the signature will fail; that test does not prove the Audience or Destination validator is working. To test accurately, have a test IdP issue a **validly signed message for SP B**, then present it at SP A in an isolated environment. Never send such tests into production systems.

### Error Lookup by Root Cause

| Symptom | First check |
| --- | --- |
| `invalid_issuer` | IdP entity ID and registration/tenant |
| `invalid_destination` | Public ACS scheme, host, path, port; proxy config |
| `audience_mismatch` | SP entity ID and IdP app registration |
| `invalid_recipient` | Bearer SubjectConfirmationData and ACS |
| `InResponseTo` mismatch | AuthnRequest ID, session cookie, repository, load balancer |
| `invalid_signature` | IdP signing cert/metadata, key rotation, and signed element |
| Failure on only one node | Metadata/cert, session store, clocks across instances |
| Login loop | Cookie Secure/SameSite, ACS redirect, failure handler |
| 403 after login | Tenant, user status, role/authority mapping |

**Never resolve by** dropping issuer/signature checks, writing wildcard ACS matchers, disabling audience checks, or permitting arbitrary stateless Responses. Restore proper IdP/SP metadata, proxy, session, and login rules.

## 14. Deployment Checklist and Exercises

**Checklist when connecting a new IdP:**

- [ ] Verify IdP entity ID, metadata source, and signing certificates through an approved channel.
- [ ] Pin SP entity ID and public ACS URL in SP metadata/IdP registration.
- [ ] Validate Response/Assertion Issuer, Destination, Audience, bearer Recipient, and InResponseTo.
- [ ] Keep signature, timestamp, SubjectConfirmation, Status, replay, and correlation validations active.
- [ ] Test multi-IdP, wrong-tenant, and cross-SP assertion acceptance.
- [ ] Verify reverse proxy/HTTPS, trusted forwarded headers, and distributed session when clustered.
- [ ] Never place raw SAMLResponse, NameID, attributes, or session cookies in unprotected logs.

**Exercise 1 – read XML:** Write down the IdP entity ID, SP entity ID, ACS, and AuthnRequest ID from the sample in section 4. Explain why `Audience` is not `Destination`.

**Exercise 2 – two apps sharing an IdP:** IdP A signs an Assertion for Payroll, and the Response is POSTed to Portal. List the checks that reject it without breaking the signature.

**Exercise 3 – Java 17:** Run `SamlTargetCheck.java`. Change `assertionIssuer` to observe `FAIL [AssertionIssuer]`. Explain why the demo code cannot replace OpenSAML.

**Exercise 4 – Spring Security:** Register the SP from the example with a test IdP. Inspect the SP metadata and complete a successful login, then alter the ACS in the IdP registration to reproduce a Destination/Recipient mismatch.

**Exercise 5 – reverse proxy:** Backend sees `http://app:8080` while public URL is `https://portal.example.org`. Identify and fix the mismatch; do not trust user-sent `X-Forwarded-Host`.

**Exercise 6 – correlation:** Route the callback to a node without the saved session/request. Explain why InResponseTo fails and how to use a distributed repository or appropriate session affinity.

**Mastery check:** you can explain the mappings: **IdP entity ID ↔ Issuer**, **SP entity ID ↔ Audience**, **ACS ↔ Destination/Recipient**, **AuthnRequest ID ↔ InResponseTo**, and prove a valid signature still does not allow using an Assertion on an unintended SP.

## 15. Authoritative References

- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 – OpenSAML Support: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SP Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – SAML2 Relying Party: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core – Issuer/Conditions/SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Metadata – EntityDescriptor/ACS: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
