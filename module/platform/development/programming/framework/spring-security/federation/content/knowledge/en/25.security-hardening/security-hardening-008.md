# Do Not Disable Signature, Audience, Recipient, or Time Checks to Fix Configuration Errors

## 1. The Problem: A Login Failure Does Not Mean the Validator Is Wrong

When deploying **Spring Security - federation**, a Service Provider (SP) receives a **SAML2 Response** from an Identity Provider (IdP), or an OIDC/JWT application receives tokens from an OpenID Provider/Authorization Server. Operators may encounter **signature invalid**, **audience mismatch**, **recipient/destination mismatch**, **assertion expired**, **InResponseTo mismatch**, or **JWT invalid audience**. A dangerous “quick fix” is disabling the failing check so users can log in.

**Principle: never disable signature, audience, recipient, time, or request correlation checks to mask configuration errors.** You must trace the discrepancy to **IdP/SP metadata, verification certificate/key, EntityID, ACS URL, HTTPS/reverse proxy, token audience/client ID, NTP, or session repository** and fix it at the root cause.

This lesson belongs to the **Security Hardening** group of **Spring Security - federation**. The focus is SAML2 Web Browser SSO, while clarifying equivalent checks in OIDC and JWT APIs. Examples use **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**. All `example.org` hosts/IDs are illustrative; real login requires an operational IdP and metadata/trust.

### Objectives

1. Explain why signature, trusted issuer, audience, recipient, and time are **independent** conditions.
2. Distinguish **SAML2 Issuer, AudienceRestriction, Destination, SubjectConfirmationData Recipient, InResponseTo, NotBefore, NotOnOrAfter**.
3. Identify common causes: **SP entity ID differing from IdP Audience**, internal ACS differing from public HTTPS, signing cert rollover, clock drift, and lost AuthnRequest.
4. Know why **OIDC ID Token aud=client_id** whereas **JWT access token aud=resource API**.
5. Use Spring Security/OpenSAML and NimbusJwtDecoder without writing validators that skip checks.
6. Run a Java 17 demo proving a valid signature can still be rejected for wrong audience/recipient/time.
7. Organize negative tests and config remediation procedures that still **fail closed**.

## 2. Checks and Risks When Disabled

| Check | What it proves | If skipped |
| --- | --- | --- |
| **Signature + trusted key** | Message/Assertion/Token was signed by a key belonging to the trusted issuer over the exact signed data. | User/attribute forgery, XML Signature Wrapping. |
| **Issuer** | Exact IdP/OP/AS in trust configuration. | Wrong IdP, realm, or registration. |
| **Audience** | Token/Assertion was issued for the exact SP/Relying Party/API. | Token substitution from app A to B. |
| **Recipient (SAML)** | Bearer Assertion is allowed to be presented at the exact receiving endpoint. | Assertion sent to a different ACS/endpoint. |
| **Destination (SAML)** | Protocol Response is addressed to the exact endpoint. | Response redirected to an unintended endpoint. |
| **NotBefore/NotOnOrAfter, exp/nbf** | Within the permitted time window. | Replay and use of expired/not-yet-valid credentials. |
| **InResponseTo, state, nonce** | Login response matches the corresponding request/browser flow. | Login CSRF, request confusion, token replay. |
| **Replay + local authorization** | Bearer proof is not reused against policy; user has resource rights. | SSO replay or privilege escalation. |

A valid signature **does not replace audience**. A matching audience **does not replace recipient**. A matching recipient **does not prove the Assertion is unexpired**. Passing all of them still requires local account, tenant/resource authorization, replay/ID policy, and session security.

~~~text
Incoming protocol response
  |
  +-- valid signature anchored to trusted issuer key? -- NO -> REJECT
  +-- trusted issuer/registration? -------------------- NO -> REJECT
  +-- intended audience matches consumer? ------------ NO -> REJECT
  +-- valid SAML Recipient/Destination? --------------- NO -> REJECT
  +-- Conditions/SubjectConfirmation/time valid? ----- NO -> REJECT
  +-- correct request correlation/replay policy? ----- NO -> REJECT
  +-- local account/tenant/resource rights? ---------- NO -> DENY
  |
  +-- all required checks pass -> authenticated and authorized
~~~

**Fail closed** does not mean locking users out permanently: it is the necessary property while a system is misconfigured, preventing issuing privileged Authentications for invalid messages. Never “temporarily grant ROLE_USER” by reading unverified raw NameID/email.

## 3. SAML2: Distinguish EntityID, Audience, ACS, Recipient, Destination

Suppose a SAML Service Provider has:

~~~text
IdP EntityID:
    https://idp.example.org/saml2

SP EntityID:
    https://sp.example.org/saml2/service-provider-metadata/corp

ACS endpoint:
    https://sp.example.org/login/saml2/sso/corp

Spring registrationId:
    corp

AuthnRequest ID:
    _REQ_42

SAML Response ID:
    _RESP_9001

SAML Assertion ID:
    _ASSERT_8001
~~~

SAML Assertion **`AudienceRestriction`** typically contains the **SP EntityID**, not the IdP EntityID, ACS, or registrationId. **`SubjectConfirmationData Recipient`** is typically the **ACS URL** where the bearer assertion is presented. **`Response Destination`** is an attribute on the protocol Response pointing to the endpoint where the message is sent per SAML profile/binding. Recipient and Destination may be equal, yet they are **not the same field**.

**`registrationId`** is Spring's configuration key used to look up `RelyingPartyRegistration`. A callback URL containing `corp` does not prove the issuer on its own and is not tenant authorization. After selecting a candidate registration, the provider must still validate trusted key/issuer/audience/recipient/time.

### Conditions example

~~~xml
<saml:Conditions
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  NotBefore="2030-01-01T11:55:00Z"
  NotOnOrAfter="2030-01-01T12:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://sp.example.org/saml2/service-provider-metadata/corp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

This is an explanatory **XML fragment**, not a signed Assertion that can log in. If the IdP emits audience `https://sp.example.org/` while SP config has the longer EntityID above, the response must be rejected. **Fix the SP/IdP registration**, do not remove the AudienceRestriction validator.

SAML can carry multiple AudienceRestrictions and multiple Audience elements inside one restriction; **OpenSAML** handles this per spec—never write `firstAudience.equals(...)` and ignore other conditions.

### Recipient example

~~~xml
<saml:SubjectConfirmation
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
    Recipient="https://sp.example.org/login/saml2/sso/corp"
    InResponseTo="_REQ_42"
    NotOnOrAfter="2030-01-01T12:05:00Z"/>
</saml:SubjectConfirmation>
~~~

Recipient binds to **bearer subject confirmation**. It is not the SP EntityID. If it points to a different ACS, never wave it through with “matching audience is enough”.

### Response Destination example

~~~xml
<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  ID="_RESP_9001"
  Version="2.0"
  IssueInstant="2030-01-01T12:00:00Z"
  InResponseTo="_REQ_42"
  Destination="https://sp.example.org/login/saml2/sso/corp">
  <!-- Attribute example only, not a complete signed Response. -->
</samlp:Response>
~~~

Response Destination specifies the endpoint permitted to receive the protocol Response; bearer Recipient protects subject confirmation at the ACS. Fix the **IdP Reply URL/ACS and SP metadata**, do not drop the comparisons.

## 4. SAML Signatures, XML Signature Wrapping, and Metadata Trust

SAML uses **XML Digital Signature**. An IdP may sign the Response, Assertion, or both per profile/trust contract. Do not claim every profile mandates both signatures; the security requirement is that **the data used to mint Authentication sits within a valid signature from a trusted IdP**, and protocol conditions are checked.

Proper steps:

1. Verify XML-DSig, Reference URI, signed IDs, transforms, and canonicalization via **OpenSAML**, never parsing/verifying with ad-hoc XML code.
2. Use **IdP verification X509 credentials** from trusted RelyingPartyRegistration/IdP metadata.
3. Verify issuer matches that registration's **IdP EntityID**.
4. Read principal/attributes **from the validated signed element**, not from another attacker-injected Assertion.
5. Defend against **XML Signature Wrapping** (Assertion A signed while app reads unsigned Assertion B), duplicate IDs, and parser hazards.
6. Allow only security-policy-compliant algorithms, key strengths, XML parsers, and certificate rotation.
7. Never trust a **self-carried KeyInfo X509Certificate in the Response** unless anchored to trusted verification credentials.

**Base64 decoding is not signature validation.** An XML parser reading a NameID does not mean the IdP authenticated that NameID. An IdP signing a message also does not automatically grant `ROLE_ADMIN`: Spring must still map local groups and tenant/resource permissions per internal policy.

### When the IdP rotates its signing certificate

Symptom: logins begin failing signature checks at a specific time; it may fail only on certain nodes due to differing metadata caches.

**Safe procedure:** verify IdP metadata through an administrative/trusted channel; verify the issuer and new cert; update RelyingPartyRegistration verification credentials; allow old/new overlap within a controlled window; ensure all SP nodes share the trust config; run positive and negative signature tests. **Never** set `trustAll=true`, drop the signature validator, or accept arbitrary certificates from raw XML.

**TLS certificate, IdP SAML signing certificate, SP decryption certificate, and SP AuthnRequest signing key** have distinct roles. Do not try fixing SAML signing errors by swapping the web TLS cert by mistake.

## 5. Audience Mismatch Is Often Caused by Out-of-Sync SP EntityID

Typical causes:

- IdP Audience = `https://sp.example.org/app`, while Spring SP EntityID = `https://sp.example.org/saml2/service-provider-metadata/corp`.
- HTTP → HTTPS migration, domain changes, or reverse proxy altering SP metadata.
- Copying an IdP app registration from staging to production while sharing the wrong entity ID.
- Changing IdP realm, registrationId, or tenant while keeping an old audience.
- Multiple IdPs/SPs: a Response carries `partner`'s audience while hitting `corp`'s callback.

**How to fix:**

1. Export **SP metadata** from the running configuration; read `EntityDescriptor entityID`.
2. Inspect the AudienceRestriction actually issued by the **trusted IdP** in sandbox/redacted logs.
3. Configure the IdP Audience to match the agreed **SP entityID** exactly.
4. If a stable EntityID is needed, set an explicit entityId and configure the same value in the IdP app registration.
5. Keep audience validation enabled; never accept wildcard audiences for all SPs.

One IdP can issue tokens for many SPs; that is precisely why audience binding must never be disabled.

## 6. Recipient/Destination Mismatch Is Often Caused by HTTPS Reverse Proxies

A common pattern:

~~~text
Public browser / IdP POST:
  https://sp.example.org/login/saml2/sso/corp

TLS ingress:
  https://sp.example.org

Request to Spring pod:
  http://spring-pod:8080/login/saml2/sso/corp

If app thinks ACS is:
  http://spring-pod:8080/login/saml2/sso/corp

While IdP issues Recipient:
  https://sp.example.org/login/saml2/sso/corp
~~~

Proper validation rejects because **recipient/destination are defined by the external endpoint and trust contract**, not by whatever backend route the app guesses.

**Fix:**

- Verify exact public scheme/host/port/path/registrationId/ACS.
- Check IdP Reply URL/ACS and SP metadata `AssertionConsumerService Location`.
- Configure the canonical public ACS in RelyingPartyRegistration.
- Configure forwarded headers on the trusted reverse proxy; Spring Boot can use **`server.forward-headers-strategy: framework`**.
- The proxy must strip/overwrite `Forwarded`/`X-Forwarded-*` from public clients to prevent host-header poisoning.
- With multiple context paths/tenants, manage ACS binding and session/correlation accurately.
- Re-issue a fresh signed Response from the IdP after fixing; **never edit raw XML in flight**.

**Never disable Recipient/Destination.** Doing so turns a configuration mismatch into the risk of bearer assertions being replayed to other endpoints.

## 7. SAML Time: Two Validity Regions Must Be Checked

| Field | Meaning |
| --- | --- |
| **Conditions.NotBefore** | Assertion cannot be used before this instant (barring a bounded skew policy). |
| **Conditions.NotOnOrAfter** | Assertion is no longer valid from this instant onward. |
| **SubjectConfirmationData.NotBefore** | Earliest bound for bearer confirmation if present. |
| **SubjectConfirmationData.NotOnOrAfter** | Separate upper bound for bearer confirmation. |
| **Response/Assertion IssueInstant** | Issuance time; may also be checked per freshness/profile. |
| **AuthnStatement.AuthnInstant** | Time the IdP authenticated the user, not necessarily when the Response was issued. |
| **SessionNotOnOrAfter** | Advisory IdP session lifetime, not automatically Spring's HttpSession lifetime. |

For example, if **now=2030-01-01T12:00:00Z**, `NotBefore=11:55Z`, and `NotOnOrAfter=12:05Z`, it is inside the window. **At exactly 12:05:00Z**, the Assertion is expired: **NotOnOrAfter is an exclusive bound**. Never write a custom check `now <= notOnOrAfter`.

Time must be synced via **UTC/NTP/Windows Time** across IdP, SP, Kubernetes nodes, and VMs. A small bounded clock skew can be reasonable depending on Spring/OpenSAML version/profile. **Never increase skew to hours or infinity**: that widens the replay window and masks clock drift.

If login is slow because the IdP requires MFA, measure latency and agree on an appropriate token lifetime with the IdP admin. Never remove NotBefore/NotOnOrAfter just because users act slowly. If timestamps are encoded with the wrong timezone or milliseconds-vs-seconds in JWTs, fix the issuer/serialization side.

## 8. InResponseTo, nonce, state, and replay

### SP-initiated SAML

The SP generates an **AuthnRequest ID** and stores it in the request repository/session; the IdP returns `Response.InResponseTo` and/or `SubjectConfirmationData.InResponseTo` per profile. The SP must correlate the exact request ID and initiating session.

If **InResponseTo mismatch** occurs because a load balancer switched nodes, SameSite/Secure cookies are wrong, the browser opened multiple tabs, or the session was lost, fix the request repository/cookies/shared session/ACS. **Never disable correlation** across all requests just to make login pass.

### IdP-initiated SAML

An unsolicited SAML Response may have no prior AuthnRequest to correlate. If the product requires it, use an **explicit** IdP-initiated policy with an IdP allowlist, proper registration, signature/issuer/audience/recipient/time checks, and full replay protection. Never turn all SP-initiated requests into “allow unsolicited”.

### Signed messages can still be replayed

A signature confirms origin/integrity, **not that the message has never been sent before**. You must check assertion/response IDs, replay cache/one-time semantics, time windows, and request correlation per profile. Stretching Assertion lifetimes excessively increases the replay window.

### OAuth2/OIDC

**`state`** binds the authorization callback to the browser session/CSRF; **`nonce`** binds the ID Token to the authentication request when used. They differ from SAML InResponseTo yet likewise prevent response confusion/replay. Never disable state/nonce on cookie/callback errors; fix the redirect URL/session and provider registration.

## 9. OIDC ID Token Differs from JWT Access Token

In OIDC:

- **ID Token `iss`** must match the trusted OpenID Provider issuer.
- **ID Token `aud`** must contain the Relying Party's **client_id**. With multiple audiences, validate additional audiences and `azp` per OIDC Core.
- **JWS signature** must be verified using keys/algorithms from trusted OP metadata/JWKS.
- **`exp`** must not be past due; `iat` and `auth_time` may support freshness policy; `nbf` if present must be honored.
- **`nonce`**, if sent by the client, must be verified.
- **`state`** must match the OAuth2 request; redirect URI and PKCE must follow flow/client policy.

In an OAuth2 Resource Server, the `aud` of a **JWT access token** is typically the **resource API identifier**, not the OIDC client_id by default.

~~~text
ID Token for browser application:
  iss = https://login.example.org/realms/corp
  aud = web-client-123
  sub = alice-opaque

Access Token for reports API:
  iss = https://login.example.org/realms/corp
  aud = api://reports
  scope = reports.read
~~~

An API must not accept a web client's ID Token just because `sub` and signature are valid. **Request an access token meant for the API**; never drop the audience validator on the API.

**Decoding a Base64URL payload is not verifying a JWT.** Never accept `alg=none`, treat `kid` as a trust anchor, or fetch JWKs from untrusted URLs self-declared in the JWT header like `jku`/`x5u`. When the IdP rotates JWKS, refresh the key set from trusted issuer metadata rather than disabling signatures.

## 10. Standalone Java 17: A Valid Signature Must Still Be Rejected When Audience Is Wrong

**FederationValidationDemo.java** uses real RSA-SHA256 to sign a **simulated message**, then checks issuer, audience, recipient, request ID, and time. Only JDK 17 is needed.

**Mandatory limitation:** this is **not a SAML XML-DSig or JWT/JWS verifier**. `canonicalForDemo()` joins fields with `|` and does not protect against XML canonicalization/string ambiguity; randomly generated demo keys are not trusted IdP keys. In production, use OpenSAML/Spring Security/NimbusJwtDecoder.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;

public class FederationValidationDemo {
    record Envelope(String issuer, String audience, String recipient,
                    String inResponseTo, Instant notBefore,
                    Instant notOnOrAfter, String subject) {
        String canonicalForDemo() {
            return String.join("|", issuer, audience, recipient,
                inResponseTo, notBefore.toString(),
                notOnOrAfter.toString(), subject);
        }
    }

    record Policy(String issuer, String audience,
                  String recipient, String requestId) {}

    static byte[] sign(Envelope value, PrivateKey key)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(value.canonicalForDemo()
            .getBytes(StandardCharsets.UTF_8));
        return signer.sign();
    }

    static boolean verify(Envelope value, byte[] proof, PublicKey key)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(value.canonicalForDemo()
            .getBytes(StandardCharsets.UTF_8));
        return verifier.verify(proof);
    }

    static String check(Envelope value, byte[] proof, PublicKey key,
                        Policy p, Instant now)
            throws GeneralSecurityException {
        if (!verify(value, proof, key)) {
            return "REJECT SIGNATURE";
        }
        if (!p.issuer().equals(value.issuer())) {
            return "REJECT ISSUER";
        }
        if (!p.audience().equals(value.audience())) {
            return "REJECT AUDIENCE";
        }
        if (!p.recipient().equals(value.recipient())) {
            return "REJECT RECIPIENT";
        }
        if (!p.requestId().equals(value.inResponseTo())) {
            return "REJECT IN_RESPONSE_TO";
        }
        if (now.isBefore(value.notBefore())) {
            return "REJECT NOT_YET_VALID";
        }
        if (!now.isBefore(value.notOnOrAfter())) {
            return "REJECT EXPIRED";
        }
        return "ACCEPT";
    }

    static void show(String label, Envelope value, byte[] sig,
                     PublicKey key, Policy p, Instant now)
            throws GeneralSecurityException {
        System.out.println(label + ": "
            + check(value, sig, key, p, now));
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        Policy policy = new Policy(
            "https://idp.example.org/saml",
            "https://sp.example.org/metadata/corp",
            "https://sp.example.org/login/saml2/sso/corp",
            "_REQ_42");

        Instant now = Instant.parse("2030-01-01T12:00:00Z");
        Instant start = Instant.parse("2030-01-01T11:55:00Z");
        Instant end = Instant.parse("2030-01-01T12:05:00Z");

        Envelope good = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, end, "alice");
        byte[] goodProof = sign(good, pair.getPrivate());
        show("valid", good, goodProof, pair.getPublic(), policy, now);

        Envelope tampered = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, end, "mallory");
        show("tampered", tampered, goodProof,
            pair.getPublic(), policy, now);

        Envelope wrongIssuer = new Envelope("https://other.example.org",
            policy.audience(), policy.recipient(), policy.requestId(),
            start, end, "alice");
        show("wrong issuer", wrongIssuer,
            sign(wrongIssuer, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope wrongAudience = new Envelope(policy.issuer(),
            "https://other.example.org/metadata", policy.recipient(),
            policy.requestId(), start, end, "alice");
        show("wrong audience", wrongAudience,
            sign(wrongAudience, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope wrongRecipient = new Envelope(policy.issuer(),
            policy.audience(), "https://other.example.org/acs",
            policy.requestId(), start, end, "alice");
        show("wrong recipient", wrongRecipient,
            sign(wrongRecipient, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope wrongRequest = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), "_REQ_WRONG",
            start, end, "alice");
        show("wrong request", wrongRequest,
            sign(wrongRequest, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope future = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            Instant.parse("2030-01-01T12:01:00Z"), end, "alice");
        show("future", future, sign(future, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope expired = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, Instant.parse("2030-01-01T11:59:00Z"), "alice");
        show("expired", expired, sign(expired, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope boundary = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, now, "alice");
        show("boundary", boundary,
            sign(boundary, pair.getPrivate()),
            pair.getPublic(), policy, now);

        show("no signature", good, new byte[0],
            pair.getPublic(), policy, now);
    }
}
~~~

Run:

~~~bash
javac FederationValidationDemo.java
java FederationValidationDemo
~~~

**Exact stdout** (keypair differs each run, yet check results stay identical):

~~~text
valid: ACCEPT
tampered: REJECT SIGNATURE
wrong issuer: REJECT ISSUER
wrong audience: REJECT AUDIENCE
wrong recipient: REJECT RECIPIENT
wrong request: REJECT IN_RESPONSE_TO
future: REJECT NOT_YET_VALID
expired: REJECT EXPIRED
boundary: REJECT EXPIRED
no signature: REJECT SIGNATURE
~~~

Notably: **wrong issuer/audience/recipient/request** were all **validly re-signed with the test private key**, proving that a valid signature still cannot replace policy checks. **NotOnOrAfter is exclusive**, so `boundary` rejects.

Never use this demo to verify real XML/JWTs: it lacks signed-element/reference/canonicalization checks, trust anchoring, multiple AudienceRestrictions, replay caches, token types, and XML parser protections.

## 11. Spring Boot 3.3.5: Configuring a SAML2 SP with Public EntityID and ACS

The sample uses trusted IdP metadata, explicit public SP entity ID and ACS, and the **default Spring Security SAML2 provider** without overriding validators. A real IdP sandbox and trusted metadata are needed to run SAML end-to-end.

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
  <artifactId>secure-saml-sp</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

### application.yml

~~~yaml
server:
  port: 8080
  # Only when a trusted proxy manages Forwarded/X-Forwarded-*.
  forward-headers-strategy: framework

app:
  saml:
    idp-metadata: "${CORP_IDP_METADATA_URI}"
~~~

**CORP_IDP_METADATA_URI** must be an approved IdP metadata source, not a browser-chosen URL. It may be an admin-managed file or a trusted HTTPS endpoint with integrity checks, cache refresh, and key rollover.

### Main class

**src/main/java/com/example/samlguard/SamlGuardApplication.java**

~~~java
package com.example.samlguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlGuardApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlGuardApplication.class, args);
    }
}
~~~

### SecurityConfig.java

**src/main/java/com/example/samlguard/SecurityConfig.java**

~~~java
package com.example.samlguard;

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
public class SecurityConfig {
    @Bean
    RelyingPartyRegistrationRepository registrations(
            @Value("${app.saml.idp-metadata}") String metadata) {

        RelyingPartyRegistration corp =
            RelyingPartyRegistrations
                .fromMetadataLocation(metadata)
                .registrationId("corp")
                .entityId(
                    "https://sp.example.org/saml2/service-provider-metadata/corp")
                .assertionConsumerServiceLocation(
                    "https://sp.example.org/login/saml2/sso/corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Explanation:**

- `RelyingPartyRegistrations.fromMetadataLocation()` pulls IdP EntityID, SSO endpoint, and verification credentials from trusted metadata.
- `.entityId(...)` fixes the **SP audience** to be used by the IdP.
- `.assertionConsumerServiceLocation(...)` pins the **public HTTPS ACS** for Recipient/Destination.
- `.registrationId("corp")` is a config key, not tenant/issuer trust by itself.
- `.saml2Login()` keeps Spring Security/OpenSAML signature/issuer/audience/recipient/time/correlation validations intact.
- `.saml2Metadata()` publishes SP metadata for the IdP admin to compare; do not use unprotected metadata content for self-service trust.
- If the IdP requires signed AuthnRequests or encrypted Assertions, configure SP signing/decryption credentials per policy rather than turning off requirements.
- With multiple IdPs or ACS paths, select registrations safely and never treat issuer from raw XML as proof.
- `forward-headers-strategy` is only safe with trusted ingress stripping public forwarded headers.

### Controller

**src/main/java/com/example/samlguard/HomeController.java**

~~~java
package com.example.samlguard;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HomeController {
    @GetMapping("/")
    public String home() {
        return "SAML2 SP ready";
    }

    @GetMapping("/private")
    public String privatePage(Authentication auth) {
        return "Authenticated: " + auth.getName();
    }
}
~~~

Run:

~~~bash
mvn spring-boot:run
~~~

With a real IdP sandbox/trusted metadata/HTTPS callback: GET / is public; GET /private triggers SAML2 login; Spring validates the signed SAMLResponse/Assertion, issuer, audience, and recipient/time before creating Authentication. **Without a real IdP/key/ACS, you cannot claim end-to-end login passes.**

**Version note:** Spring Security 6.3.x uses the OpenSAML4 provider; Spring Security 7.x documentation has OpenSAML5 APIs. Never paste custom validators from another version. This example intentionally **does not override** response/assertion validators.

## 12. JWT Resource Server: Keep Default Issuer/Time, ADD Audience

A Resource API must accept **access tokens** issued specifically for that API. In Spring Security 6.x, Resource Server includes trusted issuer/JWKS validation and timestamps; to enforce `aud=api://reports`, add a validator **by composing with defaults**.

This configures a **separate API application**, not code inside the SAML SP in section 11.

**Dependency fragments in API pom.xml:**

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

**API application.yml:**

~~~yaml
app:
  jwt:
    issuer: "${TRUSTED_JWT_ISSUER}"
    audience: "api://reports"
~~~

**src/main/java/com/example/api/ApiSecurityConfig.java**

~~~java
package com.example.api;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.jwt.issuer}") String issuer,
            @Value("${app.jwt.audience}") String expectedAudience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "JWT audience does not include this API", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Never use** `decoder.setJwtValidator(audienceValidator)` alone: that overwrites default issuer/exp/nbf validators. **`DelegatingOAuth2TokenValidator`** combines audience checking with **`JwtValidators.createDefaultWithIssuer`**, keeping defaults. `NimbusJwtDecoder` verifies the JWS signature with keys from trusted issuer metadata/JWKS; a user-supplied JWT header never selects the trust anchor.

If the contract requires a specific token profile/type (such as **RFC 9068**), add type/profile validation; a website's ID Token must not be accepted as an API access token just because its signature is valid.

### OIDC client registration is a different configuration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope:
              - openid
              - profile
        provider:
          corp:
            issuer-uri: "${OIDC_ISSUER_URI}"
~~~

Here the ID Token audience must contain **OIDC_CLIENT_ID**. On mismatch, fix the OP app/client registration rather than dropping OIDC aud validation. Meanwhile, the API audience is `api://reports`, not automatically equal to `client_id`.

## 13. Layer-Accurate Troubleshooting Table

| Symptom | Suspect | Correct Action |
| --- | --- | --- |
| Signature invalid after IdP rollout | Signing cert/key rotated or stale metadata. | Refresh trusted verification credentials, check IdP EntityID, roll out across all nodes. |
| Audience invalid in production | Wrong SP EntityID or staging metadata used. | Compare SP metadata against IdP Audience for the right environment. |
| Recipient mismatch after ingress migration | Public HTTPS URL differs from internal host/path. | Configure canonical ACS and trusted forwarded headers. |
| Destination mismatch | IdP Reply URL differs from actual ACS. | Fix IdP app registration/binding; do not drop Destination. |
| InResponseTo mismatch | AuthnRequest state lost due to session/LB/cookie. | Fix request repository, SameSite, Secure, shared session. |
| NotBefore too far in the future | Clock skew, wrong IdP timestamp. | Sync NTP/UTC and bounded skew policy. |
| NotOnOrAfter already expired | Slow callback, short IdP TTL, clock drift. | Measure flow and tune IdP TTL reasonably; keep validator. |
| Unknown JWT kid | JWKS rollover, wrong issuer, stale cache. | Refresh trusted JWKS; verify issuer and key provenance. |
| JWT invalid audience | ID Token/web token sent to API. | Request an access token for the right resource; keep API audience. |
| Wrong OIDC issuer | Wrong realm/issuer-uri. | Fix client/provider metadata. |
| User has valid token but lacks permission | Local RBAC/tenant membership. | Return 403/deny; never change audience to grant roles. |

**Do not “try disabling validators one by one to see if login works” on a real system.** Use redacted logs, trusted metadata, and signed sandbox fixtures. To test the audience validator independently, create a **validly signed token/Assertion with the wrong audience**; editing XML after signing is caught by the signature validator first.

## 14. Mandatory Negative Test Matrix

| # | Scenario | Expected |
| --- | --- | --- |
| 1 | SAML signed Response/Assertion, valid issuer/audience/ACS/time | Passes authentication if local account is permitted. |
| 2 | Modify principal after signing | Invalid signature → reject. |
| 3 | XML with signed Assertion A and fake unsigned Assertion B | Do not take B as principal; reject wrapping. |
| 4 | XML KeyInfo carries attacker cert | Do not trust certificates outside metadata. |
| 5 | IdP rotates key before SP updates trusted metadata | Fail closed; never skip signature. |
| 6 | Issuer from another IdP registration | Reject. |
| 7 | Matching issuer string but untrusted signing key | Reject. |
| 8 | Signed AudienceRestriction targets another SP | Reject. |
| 9 | Multiple AudienceRestrictions unsatisfied | Reject per SAML Conditions semantics. |
| 10 | Staging assertion sent to production SP | Reject audience/recipient. |
| 11 | Bearer Recipient wrong ACS | Reject. |
| 12 | Response Destination wrong ACS | Reject. |
| 13 | ACS scheme changed HTTPS→HTTP | Reject until metadata/proxy fixed. |
| 14 | Reverse proxy uses wrong host/port/path | Reject; fix canonical external ACS. |
| 15 | InResponseTo differs from saved request ID | Reject. |
| 16 | SP AuthnRequest session repository lost | Fail closed; fix storage/HA. |
| 17 | Browser opens multiple login tabs | Request IDs are not mixed up. |
| 18 | IdP-initiated Response on app disallowing unsolicited | Reject. |
| 19 | Permitted IdP-initiated | Still validates signature, aud, recipient, time, replay. |
| 20 | Future Conditions NotBefore | Reject, outside valid bounded skew. |
| 21 | Conditions NotOnOrAfter equal to now | Expired (exclusive). |
| 22 | SubjectConfirmationData expired while Conditions valid | Reject. |
| 23 | Conditions expired while SubjectConfirmation valid | Reject. |
| 24 | IdP/SP clocks 15 minutes apart | Do not widen skew infinitely; fix NTP. |
| 25 | Replay signed assertion/response ID | Reject per replay policy. |
| 26 | Invalid OIDC ID Token signature | Reject. |
| 27 | Wrong OIDC ID Token iss | Reject. |
| 28 | OIDC aud missing RP client_id | Reject. |
| 29 | OIDC aud has multiple audiences, azp unsatisfied | Reject. |
| 30 | OIDC nonce/state mismatch | Reject correlation. |
| 31 | Expired OIDC ID Token exp | Reject. |
| 32 | Stale OIDC auth_time when max_age required | Re-auth per policy. |
| 33 | API receives browser app's ID Token | Reject type/audience. |
| 34 | JWT access token wrong aud with valid signature | Reject. |
| 35 | JWT access token wrong iss with right aud | Reject. |
| 36 | JWT alg=none/invalid signature | Reject. |
| 37 | JWT jku points to attacker host | Never trust self-declared key URL. |
| 38 | Key rotation at trusted issuer | Controlled JWKS refresh, still verifies. |
| 39 | Future JWT nbf / expired exp | Reject. |
| 40 | Valid token but disabled user | Local authorization denies. |
| 41 | Valid token but missing tenant membership | 403, no cross-tenant access. |
| 42 | Proxy accepts client-sent X-Forwarded-Host | Test fails; strip/overwrite. |
| 43 | Custom audience validator drops issuer/time defaults | Test fails; do not deploy. |
| 44 | Same SAML Assertion sent to wrong registration | Reject trust/audience/recipient mismatch. |
| 45 | Logs contain raw SAMLResponse/JWT/keys | Security QA fails; redact. |

## 15. Remediation and Release Checklist

**SAML2 trust**

- [ ] IdP EntityID, signing certificate/KeyDescriptor, and trusted metadata are accurate.
- [ ] Never trust arbitrary KeyInfo from messages; never drop XML signatures.
- [ ] SP EntityID matches the AudienceRestriction issued by the IdP.
- [ ] Public HTTPS ACS matches both Recipient and Destination.
- [ ] Both Conditions and SubjectConfirmationData times are validated.
- [ ] InResponseTo and replay protection match the profile.
- [ ] IdP-initiated SSO, if enabled, is allowlisted and separately constrained.
- [ ] Metadata/cert rotation has a plan, overlap, and rollback.

**OIDC/JWT**

- [ ] ID Token signature/issuer/aud(client_id)/exp/state/nonce are validated.
- [ ] API access token signature/issuer/aud(resource)/exp/nbf/type match the contract.
- [ ] JWKS come solely from trusted issuers; never accept `alg=none` or token-header URLs.
- [ ] Add custom validators by composition, never overwriting defaults.

**Operations/authorization**

- [ ] SP/IdP/API clocks synced to UTC/NTP; small clock tolerance requires approval.
- [ ] Reverse proxy trusts Forwarded headers only from trusted ingress.
- [ ] Tests with validly signed wrong audience/recipient/time and replay all reject.
- [ ] Logs safely use trace IDs/reason codes; never emit raw tokens/PII/keys.
- [ ] Local account, roles, tenant, and resource-level authorization are enforced.
- [ ] When positive login fails, fix configuration; never delete negative test expectations.

## 16. Review Questions

**1. Is a valid SAML signature enough to log into any SP?**  
No. Audience, Recipient/Destination, Conditions, issuer, request correlation, and local authorization must all still pass.

**2. How does Audience differ from Recipient?**  
Audience is typically the SP EntityID; Recipient is the ACS endpoint where the bearer Assertion is presented.

**3. Can Destination replace Recipient?**  
No. Destination belongs to Response; Recipient belongs to SubjectConfirmationData. Both have distinct semantics even when sharing the ACS URL.

**4. Why not disable Recipient when Spring runs behind HTTPS ingress?**  
Because the root cause is usually wrong canonical public ACS/proxy headers; fix IdP/SP metadata and forwarding trust boundaries.

**5. At the exact NotOnOrAfter instant, is the Assertion still valid?**  
No. The upper bound is exclusive; it must be rejected once the limit is reached.

**6. Is a certificate inside KeyInfo automatically trustworthy?**  
No. It must be anchored to trusted IdP verification credentials.

**7. When InResponseTo mismatches due to an LB, what should you fix?**  
Fix the AuthnRequest repository, session cookies, and HA; never remove correlation.

**8. What must OIDC ID Token audience contain?**  
It must contain the RP's `client_id`, checking additional audiences/`azp` per OIDC Core. API access tokens use a different audience.

**9. Why doesn't editing Audience on XML after signing test audience checks independently?**  
Because the signature fails first. A freshly signed fixture with the wrong audience yet valid signature is needed.

**10. How do you add an audience validator for Spring JWT while keeping issuer/exp/nbf?**  
Compose `JwtValidators.createDefaultWithIssuer` with your audience validator via `DelegatingOAuth2TokenValidator`.

**11. Should skew be set to 24h when an IdP's clock drifts?**  
No. Sync NTP/UTC and keep a small bounded tolerance per policy.

**12. If protocol validation passes, does that automatically grant ROLE_ADMIN?**  
No. Local user/group mapping, tenant/resource checks, and least privilege are still required.

## 17. Official Documentation

1. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AudienceRestriction, SubjectConfirmationData, Recipient, Conditions, and NotOnOrAfter.
2. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO bearer profile.
3. [Spring Security 6.3 OpenSaml4AuthenticationProvider](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): provider trust/validation.
4. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, entityID, ACS, metadata.
5. [Spring Security Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response/assertion validation; check API version.
6. [Spring Boot 3.3 Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): SAML2 SP configuration.
7. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token iss/aud/exp/nonce/azp.
8. [RFC 7519 JWT](https://www.rfc-editor.org/rfc/rfc7519): exp, nbf, iat, iss, aud.
9. [RFC 7515 JWS](https://www.rfc-editor.org/rfc/rfc7515): signature/algorithm.
10. [RFC 9068 OAuth2 JWT Access Token](https://www.rfc-editor.org/rfc/rfc9068): access token type/audience.
11. [Spring Security OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JwtDecoder and validation composition.
12. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML Signature Wrapping/trust/replay.
13. [OWASP JWT Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): signature validation and key trust.
14. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default and least privilege.

**Conclusion:** Secure federation requires **a trusted issuer's signature, right audience, right recipient/destination, right time window, request correlation/replay checks, and local authorization**. When login fails, resolve **metadata, keys, EntityID, ACS URL, reverse proxy, token client/resource ID, NTP, or session**—never disable validation checks to hide configuration errors.