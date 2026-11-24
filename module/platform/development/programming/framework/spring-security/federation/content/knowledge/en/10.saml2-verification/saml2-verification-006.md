# Correlating InResponseTo with Stored Login Requests in SAML 2.0

**Module:** Spring Security – federation  
**Context:** SAML2 Verification  
**Scope:** SAML 2.0 Web Browser SSO Profile, Spring Boot 3.x, Spring Security 6.x, and Java 17+.

## 1. Lesson Objectives

In SAML 2.0 **SP-initiated Single Sign-On**, the Service Provider (SP) initiates login with an **AuthnRequest** sent to the Identity Provider (IdP). Once the IdP finishes authenticating, the browser submits a **SAMLResponse** to the SP's Assertion Consumer Service (ACS). Verifying the SAMLResponse signature alone is **not enough**: the SP must also correlate the response against **the login request initiated by that exact SP browser session**.

The crucial link is **InResponseTo**. It references the **original AuthnRequest's ID**. Matching it alongside storing the request in a suitable repository helps:

- Prevent the application from mistakenly accepting a response meant for another request or another session.
- Mitigate **login CSRF/session swapping**: an attacker trying to feed their valid response into a victim's browser to swap login identity.
- Detect responses with no originating request, already-consumed requests, or expired requests.
- Bind response processing to the right **RelyingPartyRegistration**, IdP, SP entityID, and ACS.
- Never create an **Authentication/SecurityContext** for a SAML Response that has not proven its relationship to the active login session.

**InResponseTo is a transaction-binding condition, not a digital signature.** A matching InResponseTo with a wrong signature/Issuer/Audience/Recipient must still be rejected. Conversely, a response with a valid signature whose InResponseTo points to a non-existent request or another session's request also cannot be accepted in an SP-initiated flow requiring correlation.

## 2. Three Easily Confused IDs

SAML 2.0 has at least three identifiers to distinguish:

| Field | Example | Who creates it? | Role |
| --- | --- | --- | --- |
| **AuthnRequest.ID** | **_REQ_7f3** | SP | Unique identifier of the authentication request sent to the IdP |
| **Response.ID** | **_RESP_9a1** | IdP | Identifier of the Response message, distinct from the request ID |
| **Response.InResponseTo** | **_REQ_7f3** | IdP | Points back to the **AuthnRequest.ID** issued by the SP |

Plus one special field inside the assertion:

**SubjectConfirmationData.InResponseTo** (for bearer subject confirmation) typically must also match the originating request's **AuthnRequest.ID** per the SAML Web Browser SSO Profile.

Therefore, with the example above:

~~~text
AuthnRequest.ID                       = _REQ_7f3
SAMLResponse.ID                       = _RESP_9a1
SAMLResponse.InResponseTo             = _REQ_7f3
Assertion/SubjectConfirmationData
                      .InResponseTo   = _REQ_7f3
~~~

**Do not compare Response.ID with AuthnRequest.ID.** The two messages are generated on different sides and should have distinct IDs. The values that must match the request ID are the corresponding **InResponseTo** attributes.

**RelayState is not InResponseTo.** RelayState is HTTP binding data used to preserve correlation/navigation state across the IdP, typically an opaque value. It may help locate a saved request, yet does not replace verifying the XML Response/Assertion or binding the response to the browser that initiated the request.

## 3. SP-Initiated SSO Flow: Storing and Correlating

~~~text
Browser A                          SP (Spring Security)                 IdP
      |                                   |                             |
      | GET /private                      |                             |
      |---------------------------------->| login required              |
      |<----------------------------------| redirect                    |
      | GET /saml2/authenticate/company   |                             |
      |---------------------------------->| create AuthnRequest         |
      |                                   | ID = _REQ_7f3              |
      |                                   | save in HttpSession A       |
      |                                   | save registrationId/RelayState
      |<----------------------------------| redirect SAMLRequest ------>|
      |                                   |                             | authenticate
      | POST /login/saml2/sso/company     |<----------------------------|
      | SAMLResponse:                     |                             |
      | InResponseTo = _REQ_7f3           |                             |
      |---------------------------------->| load saved request          |
      |                                   | match right session A       |
      |                                   | Response.InResponseTo       |
      |                                   | SubjectConfirmationData     |
      |                                   | signature/Issuer/Audience/...|
      |                                   | consume request once        |
      |<----------------------------------| create session if valid     |
~~~

### Step 1 – SP Issues AuthnRequest

When an unauthenticated user accesses a protected resource:

1. Spring Security redirects the browser to **/saml2/authenticate/{registrationId}**, e.g. **/saml2/authenticate/company**.
2. **Saml2WebSsoAuthenticationRequestFilter** and the request resolver/factory create the AuthnRequest.
3. AuthnRequest carries a **unique, unpredictable ID**, SP Issuer, IdP Destination/endpoint, proper ACS info, IssueInstant, and required attributes.
4. The SP saves the correlation request object before sending SAMLRequest to the browser/IdP.
5. The browser receives a redirect or POST per the SAML binding and arrives at the right IdP.

The key point is that **the SP must retain proof that its own browser session created the AuthnRequest with that specific ID**, rather than trusting any request ID string brought back on the callback.

### Step 2 – IdP Sends SAMLResponse

After authenticating the user, the IdP builds a Response with **InResponseTo** referencing AuthnRequest.ID. The Assertion contains bearer SubjectConfirmationData with **InResponseTo**, Recipient, NotOnOrAfter, and corresponding conditions. The browser typically **POSTs** SAMLResponse to the ACS:

~~~http
POST /login/saml2/sso/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...
 
SAMLResponse=BASE64_SAML_RESPONSE&RelayState=OPAQUE_VALUE
~~~

This is a **request description**; all values are placeholders, not a real SAMLResponse. Do not put real responses/tokens into docs, logs, tracking URLs, or public observability tools.

### Step 3 – SP Retrieves the Original Request

Spring Security uses **Saml2AuthenticationRequestRepository** to locate the issued AuthnRequest. The default configuration is **HttpSessionSaml2AuthenticationRequestRepository**, storing the request in the browser's **HttpSession**.

If the browser does not send the right session cookie, HttpSession expired, or a load balancer routes the callback to a node that cannot see the session, the original request may not be found. In that situation, the system must not "fix" it by grabbing any request with the same ID system-wide while dropping the browser binding check.

### Step 4 – Verifying Correlation and SAML

Depending on the Spring Security and OpenSAML versions, the converter/provider/validators coordinate:

- Look up the corresponding **RelyingPartyRegistration**.
- Load the AuthnRequest from the repository per configured policy.
- Check **Response.InResponseTo** against AuthnRequest.ID when the flow requires it.
- Check **SubjectConfirmationData.InResponseTo** on the bearer confirmation per SAML Profile rules.
- Verify signature, Issuer, Destination, AudienceRestriction, Recipient, conditions/time, subject confirmation, and other requirements.
- Only when all conditions pass is **Saml2Authentication** and **SecurityContext** created.

**Do not treat finding a request with the same ID as sufficient.** The InResponseTo field in XML must still reside inside fully verified data, and all other conditions must be satisfied.

### Step 5 – Completion and Non-Reuse

A completed request must be **consumed/removed**, or marked used per policy, so that a replayed response cannot create another login transaction. With a distributed repository, the consume operation must be safe under concurrency. Complete SAML deployments also need replay detection policies at the **Response/Assertion ID** level, not just request ID.

Do not write Authentication into SecurityContext when correlation fails; log failure state enough to diagnose without exposing SAMLResponse, session cookies, or sensitive identifiers.

## 4. XML Example: Attributes to Cross-Check

This is an **illustrative XML fragment** with signature and several required fields omitted; **do not use it as a valid assertion**.

### 4.1. AuthnRequest Created by SP

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_REQ_7f3"
    Version="2.0"
    IssueInstant="2026-11-07T08:00:00Z"
    Destination="https://idp.example.org/sso"
    AssertionConsumerServiceURL=
        "https://portal.example.org/login/saml2/sso/company">
    <saml:Issuer>https://portal.example.org/saml/sp/company</saml:Issuer>
</samlp:AuthnRequest>
~~~

Meaning: **ID="_REQ_7f3"** is the exact identifier the SP saves; Issuer is the SP's entityID, Destination is the IdP endpoint, and ACS URL is where the SP receives responses.

### 4.2. Response Created by IdP

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_RESP_9a1"
    Version="2.0"
    IssueInstant="2026-11-07T08:01:00Z"
    Destination="https://portal.example.org/login/saml2/sso/company"
    InResponseTo="_REQ_7f3">
    <saml:Issuer>https://idp.example.org/saml/company</saml:Issuer>
    <saml:Assertion ID="_ASSERT_22b">
        <saml:Subject>
            <saml:SubjectConfirmation
                Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData
                    InResponseTo="_REQ_7f3"
                    Recipient="https://portal.example.org/login/saml2/sso/company"
                    NotOnOrAfter="2026-11-07T08:05:00Z"/>
            </saml:SubjectConfirmation>
        </saml:Subject>
    </saml:Assertion>
</samlp:Response>
~~~

**Points to identify:**

- Response.ID **_RESP_9a1** differs from AuthnRequest.ID **_REQ_7f3**.
- Response.InResponseTo and SubjectConfirmationData.InResponseTo both reference **_REQ_7f3**.
- **Destination/Recipient** point to the SP's right ACS.
- **Issuer** is the SP-approved IdP, not a domain arbitrarily injected by the browser.
- **NotOnOrAfter** is the bearer confirmation's time constraint, independent of the SP session lifetime.
- The example omits signatures and Conditions/AudienceRestriction/NameID; a real system must validate everything per profile and reject this sample XML.

## 5. How Does InResponseTo Differ from RelayState, Session, and Request ID?

| Information | What does it prove? | Enough to authenticate user? |
| --- | --- | --- |
| **Response.InResponseTo** | Response claims to answer an AuthnRequest.ID | **No**: still must verify saved request, session, and SAML validation |
| **SubjectConfirmationData.InResponseTo** | Bearer assertion binds to AuthnRequest | **No**: still need signature, SubjectConfirmation, time, Recipient... |
| **RelayState** | HTTP binding state, typically used for correlation/navigation | **No**: not automatically proof of authentication or session |
| **HttpSession ID** | Browser is presenting an SP session identifier | **No**: a session can exist while anonymous |
| **AuthnRequest.ID** | SP marks a specific login request | **No**: only a correlation key |
| **Response.ID / Assertion.ID** | Unique identifier of response/assertion | **No**: still need integrity/target checks and anti-replay |
| **Authentication/SecurityContext** | Result Spring Security accepts after verification | Basis for authentication, yet still needs authorization |

**RelayState is not a default anti-CSRF token in the sense of skipping other checks.** If building a repository that looks up requests globally only by RelayState/Response.InResponseTo, there must be an independent mechanism binding the transaction to the exact browser and preventing replay. If RelayState is used as a navigation URL, allowlist internal paths or validate strictly to prevent open redirects.

**Same session does not mean tabs cannot collide.** When a user opens multiple parallel login windows, you must know whether the specific request repository stores one request or multiple pending requests, how lookup by RelayState/ID works, and overwrite/consume behavior in the version in use. Never assume HttpSession automatically handles all parallel flows properly.

## 6. Spring Security: What Does the Default Request Repository Do?

Spring Security provides these components:

1. **Saml2WebSsoAuthenticationRequestFilter** creates and saves **AbstractSaml2AuthenticationRequest** before sending SAMLRequest.
2. **Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>** is the interface responsible for saving/loading/removing requests.
3. **HttpSessionSaml2AuthenticationRequestRepository** is the default implementation, binding the request to the browser's HttpSession.
4. **Saml2WebSsoAuthenticationFilter** together with **Saml2AuthenticationTokenConverter** use the repository to retrieve the original request when receiving the Response.
5. **OpenSAML AuthenticationProvider** performs XML/cryptographic validation and creates Authentication if valid.

Main repository APIs:

~~~java
void saveAuthenticationRequest(
    T authenticationRequest,
    HttpServletRequest request,
    HttpServletResponse response);

T loadAuthenticationRequest(HttpServletRequest request);

T removeAuthenticationRequest(
    HttpServletRequest request,
    HttpServletResponse response);
~~~

These are **illustrative signatures** of the interface methods; in real code, type T is a subclass of **AbstractSaml2AuthenticationRequest**, and load/remove methods can return null when not found. Note **removeAuthenticationRequest** removes the request from the repository, not the SP login session.

From the stored request object, you can read:

- **getId()**: AuthnRequest ID (used to match InResponseTo).
- **getRelayState()**: RelayState if present.
- **getRelyingPartyRegistrationId()**: ID of the SP–IdP registration link.
- **getSamlRequest()**: encoded AuthnRequest message for sending over the binding.
- **getAuthenticationRequestUri()** and **getBinding()**: target URL and binding for sending the request.

These getters are for inspecting the **issued request**; they do not prove a response is valid prior to provider verification.

### Why Is Storing in HttpSession Useful?

If an attacker generates a valid SAMLResponse for the **attacker's session** and feeds it to the victim's browser, the victim's SP has no matching AuthnRequest in the **victim's HttpSession**, so SP-initiated flow can reject it. This is an advantage against login substitution compared to a global repository looking up requests purely by InResponseTo.

However, browsers may omit cookies when the IdP POSTs cross-site; that is an operational issue to solve, **not a reason to disable correlation by default**.

## 7. Spring Boot 3 / Spring Security 6 Example: Keeping the Default Mechanism

This is **code for a Spring Boot 3.x, Java 17+ Servlet/MVC project**. The sample uses **RelyingPartyRegistrations.fromMetadataLocation** and **saml2Login()**. To run real SSO, you need vetted IdP metadata, a real IdP, an SP registered with matching entityID/ACS, SP certs/keys if the IdP requires them, and proper public HTTPS.

There is no need to write a custom controller to read SAMLResponse, and no need to write a custom AuthenticationProvider just to check InResponseTo.

### 7.1. Dependencies in pom.xml

In a Maven project with a compatible Spring Boot parent/BOM, add:

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

Do not force an OpenSAML version incompatible with your Spring Security version. The configuration below uses public API classes of Spring Security 6.x.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    metadata-location: classpath:metadata/company-idp.xml
server:
  servlet:
    session:
      timeout: 20m
~~~

Place real IdP metadata (including valid certificates/endpoints) at **src/main/resources/metadata/company-idp.xml**. **20m** is the SP HttpSession idle timeout, not the SAML assertion lifetime. To test on localhost, you must register the localhost ACS/entityID or use an HTTPS test domain and configure the IdP accordingly.

### 7.3. SamlCorrelationApplication.java

**src/main/java/com/example/saml/SamlCorrelationApplication.java**

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlCorrelationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlCorrelationApplication.class, args);
    }
}
~~~

### 7.4. SamlSecurityConfig.java

**src/main/java/com/example/saml/SamlSecurityConfig.java**

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
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.metadata-location}") String location) {

        RelyingPartyRegistration registration =
            RelyingPartyRegistrations
                .fromMetadataLocation(location)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Important explanation:**

- **saml2Login()** configures both ends: creating AuthnRequest and receiving Response/Assertion, using **Saml2AuthenticationRequestRepository**.
- Spring Security defaults to **HttpSessionSaml2AuthenticationRequestRepository**, so AuthnRequest is stored in the browser session before redirecting to the IdP.
- The SP does not expose an endpoint accepting assertions at an arbitrary URL; the **ACS** must be accurately configured and registered at the IdP.
- **registrationId=company** binds the request to the trusted company IdP; **entityId** is the SP protocol identifier.
- Never disable CSRF site-wide, and never set **SessionCreationPolicy.STATELESS** on the browser SAML2 chain unless there is an equivalent alternative design for storing requests/sessions.
- This sample **does not work out of the box with example.org domains**; an actual IdP must provide metadata, sign responses, and accept the SP registration.

### 7.5. Controller Only Reads Verified Identity

**src/main/java/com/example/saml/SamlController.java**

~~~java
package com.example.saml;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlController {

    @GetMapping("/")
    public String home() {
        return "SAML correlation demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of(
            "name", principal.getName(),
            "registrationId", principal.getRelyingPartyRegistrationId());
    }
}
~~~

**Do not dump SAMLResponse in the controller** or extract NameID directly from the HTTP body to "bypass InResponseTo errors". The principal is supplied by Spring after the authentication mechanism accepts the response. In production, minimize identity data exposed in HTTP responses.

### 7.6. Running and Expected Results

In a valid Spring Boot Maven project with JDK 17+:

~~~bash
mvn spring-boot:run
~~~

If metadata loads and the app starts, public request:

~~~bash
curl -i http://localhost:8080/
~~~

Body per controller:

~~~text
SAML correlation demo
~~~

For a real login request:

~~~text
GET /saml2/authenticate/company
  -> AuthnRequest created/saved in session
  -> browser redirected to IdP
  -> IdP authenticates and sends SAMLResponse
  -> POST /login/saml2/sso/company
  -> repository supplies original request to verification flow
  -> Authentication created when response satisfies all conditions
~~~

This is an **explanatory sequence**, not stdout you can fix without a real IdP. If the public ACS is **https://portal.example.org/**, you cannot expect the IdP to call back to **http://localhost:8080/** without updating the registered configuration on both sides.

## 8. When You Want an Explicit Request Repository

For applications with complex configurations, you can declare the repository bean as follows (added to the SAML2 project's **@Configuration** class):

~~~java
@Bean
Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>
authenticationRequestRepository() {
    return new HttpSessionSaml2AuthenticationRequestRepository();
}
~~~

Related imports:

~~~java
import org.springframework.security.saml2.provider.service.authentication.AbstractSaml2AuthenticationRequest;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.HttpSessionSaml2AuthenticationRequestRepository;
~~~

**Note:** This is an **explicit configuration equivalent to the default**, not a mandatory requirement and unnecessary to copy if the default repository already suffices. If using a custom repository, ensure the same repository is used when sending AuthnRequest and when receiving SAMLResponse, and configure per the API of your running Spring Security version.

### Using Spring Session with Multiple Nodes

If the callback hits a different node than the one that created AuthnRequest, **in-memory HttpSession** on only the first node will no longer suffice. Spring Session can store HttpSession in shared Redis/DB so the request repository accesses the same data across all instances.

Example dependency in a Boot project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

The application must configure reliable Redis, TLS/ACLs, session timeout, cookie domain/path, and compatible serialization. Spring Session backs Servlet HttpSession, so **HttpSessionSaml2AuthenticationRequestRepository** continues working with that logical session. Never push raw SAMLResponse into Redis under a client-defined key name.

If the business requires multiple concurrent pending requests, check repository implementation limits and build a proper concurrency strategy with TTL and atomic consume; never assume the default repository supports every multi-tab scenario.

## 9. CacheSaml2AuthenticationRequestRepository and RelayState Risks

Spring Security also offers **CacheSaml2AuthenticationRequestRepository** to store AuthnRequest in a cache, useful when avoiding full reliance on HTTP session under certain cookie/SameSite setups. However, there is a critical security warning:

**If a request is looked up globally only by RelayState or InResponseTo, you know which request the response points to, yet not whether that request was initiated by the exact current browser.**

Example login substitution attack:

1. Attacker initiates SSO in their browser, generating request ID **_REQ_ATTACKER**.
2. IdP issues a valid SAMLResponse for the attacker's account containing InResponseTo **_REQ_ATTACKER**.
3. Attacker tricks the victim's browser into POSTing that response to the SP.
4. If the SP looks up requests globally by InResponseTo **without browser/session binding**, it may accept the response and create a victim session logged into the attacker's account.

This is a form of **login CSRF**, which can make the victim operate inside an attacker-controlled account, leak data entered into that account, or cause authorization confusion.

**Risk-mitigating design** when using a distributed cache:

- Use a **random, unpredictable, short-TTL RelayState** generated by the SP rather than trusting client-supplied values.
- Store the **RelayState → pending request** mapping with access protection, expiration limit, and single-use consumption.
- Bind the pending request to a secret/marker held privately by the **initiating browser** (protected cookie/session/context); verify that exact binding when receiving the Response.
- Never treat a **matching InResponseTo** as sufficient: you still need right browser, registration, IdP, signature, audience, recipient, and time.
- Enforce **single-use atomic consume** and replay prevention for Response/Assertion IDs.
- If using a different SameSite cookie setting for HTTP-POST callbacks, test real browser/ACS behavior rather than "deleting the InResponseTo check" to work around cookies.

**Do not build a custom repository merely because a POST callback loses the session.** First check cookie attributes, HTTPS, SameSite, reverse proxy, and session store. Any cache mechanism must be rigorously designed and tested to preserve login binding.

## 10. Runnable Java 17: Simulating Request ID and Session Correlation

The following example only simulates a **correlation table** and single-use consumption. This is **not a SAML validator**; it does not parse XML, check signatures, or create Authentication. Fixed ID values are for testing only and do not represent secure production request ID generation.

**File CorrelationExample.java:**

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class CorrelationExample {

    record Pending(String requestId, String browserSession) { }

    private final Map<String, Pending> requests =
        new ConcurrentHashMap<>();

    public void save(Pending pending) {
        requests.put(pending.requestId(), pending);
    }

    public boolean consume(
            String browserSession,
            String responseInResponseTo,
            String subjectConfirmationInResponseTo) {

        if (responseInResponseTo == null
                || !responseInResponseTo.equals(
                    subjectConfirmationInResponseTo)) {
            return false;
        }

        Pending pending = requests.get(responseInResponseTo);
        if (pending == null
                || !pending.browserSession().equals(browserSession)) {
            return false;
        }

        return requests.remove(responseInResponseTo, pending);
    }

    public static void main(String[] args) {
        CorrelationExample check = new CorrelationExample();
        check.save(new Pending("_REQ_123", "browser-A"));

        System.out.println("wrongSession=" +
            check.consume("browser-B", "_REQ_123", "_REQ_123"));
        System.out.println("assertionMismatch=" +
            check.consume("browser-A", "_REQ_123", "_REQ_OTHER"));
        System.out.println("matched=" +
            check.consume("browser-A", "_REQ_123", "_REQ_123"));
        System.out.println("replay=" +
            check.consume("browser-A", "_REQ_123", "_REQ_123"));
    }
}
~~~

Run with Java 17+:

~~~bash
javac CorrelationExample.java
java CorrelationExample
~~~

**Exact stdout:**

~~~text
wrongSession=false
assertionMismatch=false
matched=true
replay=false
~~~

Analysis:

- Browser B must not use a pending request belonging to browser A.
- Wrong SubjectConfirmationData.InResponseTo → not consumed.
- First matching attempt → consumed successfully, entry removed via conditional **remove(key, expected)**.
- Re-submission → pending request no longer found, hence fails.

**Do not copy this class into real SAML login**: it does not verify signatures, issuer, audience, timestamps, Recipient, session-cookie security, XML parsing, or overall anti-replay; the map also lacks TTL, size bounds, and distributed controls. With Spring Security, use **saml2Login()** and standard request repository/validators. The goal of the Java demo is illustrating **correlation logic**, not replacing OpenSAML AuthenticationProvider.

In a distributed system, a **local ConcurrentHashMap** is not shared across nodes; if designing pending requests in Redis/DB, you need TTL, atomic compare-and-delete, and browser binding to prevent races/replays.

## 11. IdP-Initiated SSO: When There Is No Original AuthnRequest

The SAML Web Browser SSO Profile includes **unsolicited / IdP-initiated Responses**: the IdP initiates login itself and sends a Response to the SP without the browser previously carrying an SP-issued **AuthnRequest**.

In this case:

- Per profile, an unsolicited **Response has no InResponseTo**.
- Bearer **SubjectConfirmationData must also not contain InResponseTo** referencing a non-existent request.
- The SP has no saved AuthnRequest to correlate as in SP-initiated SSO.
- That **does not mean** the SP can accept arbitrary responses: it must still check signature, Issuer, AudienceRestriction, Destination/Recipient, NotOnOrAfter, replay, IdP trust, and application policy.

**Recommended policy:** If the application does not need IdP-initiated login, allow only **SP-initiated SSO** and reject unsolicited responses using the mechanism appropriate to your version/IdP. If business requirements mandate IdP-initiated:

1. Allowlist approved IdPs/tenants and permitted ACS endpoints.
2. Confirm IdP-initiated support is enabled/configured and tested in your Spring Security version.
3. Enforce full trust/subject/recipient/time validation and block replay.
4. Mitigate **login CSRF/session swapping** within design capabilities and risk policy; do not cite "no InResponseTo" to skip other safeguards.
5. Allow post-login redirects only to safe targets; never use arbitrary RelayState as an open redirect URL.

**Do not force an unsolicited Response into a fake request-matching branch.** SP-initiated and IdP-initiated are two distinct modes with different security trade-offs. Defaults/acceptance configs can vary by Spring Security and IdP, so verify the implementation and write negative tests instead of guessing.

## 12. Replay Prevention: InResponseTo Is Necessary but Not Sufficient

Suppose a valid SAMLResponse is submitted twice:

- If the first submission consumed the original request, the second **has no remaining pending request** and must fail under strict SP-initiated mode.
- If the repository only **loads without consuming**, the old request can be reused.
- If another response carries the same InResponseTo and is validly signed/qualified, apply single-use request policy and replay ID tracking; do not let "valid signature" allow one request to mint unlimited sessions.
- If a transaction fails between consume and login completion, retry design must be explicit rather than granting multiple logins.
- SAML assertions also carry **NotOnOrAfter** and time constraints. Checking expiry narrows the attack window yet **does not replace a replay cache** when profile/policy requires one.

For **Response.ID** and **Assertion.ID**, you may need to track used IDs with a TTL matching the assertion's remaining validity, while avoiding unnecessary storage of sensitive data. Whether and how Spring Security implements a replay cache by default depends on version/provider/extensions; **do not claim that checking InResponseTo replaces all replay controls**.

## 13. SameSite Cookies and Session Correlation on ACS POST

A common real-world failure:

1. Browser opens an SP page and gets HttpSession A.
2. SP stores AuthnRequest in session A and redirects the browser to the IdP.
3. IdP POSTs SAMLResponse from a different domain to the ACS.
4. Browser **omits session A's cookie** due to SameSite/cookie policy.
5. SP cannot find the original AuthnRequest and fails correlation/InResponseTo even though the IdP issued a valid Response.

Troubleshooting steps:

- Use DevTools/Network to check whether **POST ACS carries the SP session cookie**, compared with the cookie issued before redirect.
- Check **Secure**, **HttpOnly**, Domain, Path, HTTPS, and **SameSite**.
- With cross-site HTTP-POST, **SameSite=Lax/Strict can block the cookie**. You may need **SameSite=None; Secure** with HTTPS and proper CSRF protection.
- Verify the reverse proxy does not turn public HTTPS into an internal hostname/scheme, causing wrong cookie domain/path.
- Check session timeout; if the user takes too long authenticating at the IdP, the saved AuthnRequest may expire before the callback.
- With multiple nodes, check the session store and distribution/deserialization capability.

Example **production config once cross-site POST cookies are confirmed necessary**:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: none
      timeout: 20m
~~~

Do not apply this config blindly to HTTP localhost testing. **SameSite=None** does not replace CSRF protection on business endpoints; the SAML ACS has its own verification and filter-configured CSRF exception, while application state-changing operations still need protection.

**Never fix cookie issues by disabling InResponseTo, signature, or AudienceRestriction checks.** That opens a vulnerability to mask a state-persistence bug.

## 14. Multiple IdPs and Multiple Tabs: Matching Right Request with Right Trust

### 14.1. Two RelyingPartyRegistrations

An SP may use IdPs **company** and **partner**, each with its own entityID, verification certificates, SSO endpoint, and policies. When the browser initiates requests via:

~~~text
/saml2/authenticate/company
/saml2/authenticate/partner
~~~

A pending request carries not only an ID but also the chosen **registrationId**/IdP party, ACS, and corresponding browser. When receiving a response:

- Never accept a partner IdP's Response to complete a company request.
- Never pick new metadata/JWKS/certificates from an unverified Issuer or browser-supplied query parameter.
- Never merge NameIDs/emails across two IdPs into one user without an explicit mapping policy.
- Whichever IdP a request was sent to, the response must be validated against that IdP's configuration.

### 14.2. Two Tabs in the Same Session

Suppose tab 1 initiates **_REQ_A**, and tab 2 initiates **_REQ_B** inside the same HttpSession. If the repository only retains one pending request or cleans up in a specific way, tab 2 can overwrite tab 1. When tab 1's response returns, the SP cannot find request **_REQ_A**.

Proper handling:

- Verify the repository's behavior in the exact Spring Security version in use.
- If parallel logins are required, design the pending request store keyed by ID/RelayState with **bounded capacity, TTL, browser-session binding, and atomic consume**.
- Never abandon request correlation checks to "support multiple tabs".
- If wanting to restrict concurrency, provide proper UX so users run one pending flow at a time.
- Test out-of-order callbacks, concurrent tabs, and mid-flow logout.

### 14.3. Reverse Proxy, Public ACS, and Session

If the SP runs at **http://10.0.0.3:8080** behind a reverse proxy while the public ACS is **https://portal.example.org/login/saml2/sso/company**, Recipient/Destination values must align with the public URL. **Forwarded / X-Forwarded-*** headers must only be trusted from managed proxies; cookie domain and Secure must match actual HTTPS.

Wrong ACS/Issuer/metadata usually causes separate SAML validation errors; **do not blame everything on InResponseTo** simply because they appear at the callback.

## 15. Allow/Deny Scenario Table

Assume browser A issues **AuthnRequest.ID=_REQ_A** for IdP company, saved in HttpSession A. The SP allows only SP-initiated SSO and requires single use.

| Scenario | Conclusion | Explanation |
| --- | --- | --- |
| Response.InResponseTo=_REQ_A, bearer InResponseTo=_REQ_A, right session A, valid signature and other conditions | **Acceptable** | Correlation passes; still subject to full SAML validation and policy |
| Response.InResponseTo=_REQ_B | **Reject** | Does not match session A's pending request |
| Response.InResponseTo=_REQ_A yet bearer InResponseTo=_REQ_OTHER | **Reject** | SubjectConfirmationData does not match original request |
| Response points to _REQ_A yet submitted by browser B | **Reject** | Original request belongs to browser/session A, not B |
| Response.InResponseTo=_REQ_A yet request already consumed | **Reject** | Replay or duplicate transaction processing |
| Response points to _REQ_A yet invalid signature | **Reject** | Correlation does not replace cryptographic validation |
| Response points to _REQ_A yet Issuer=unselected partner IdP | **Reject** | Wrong trust relationship |
| Response points to _REQ_A yet Recipient is another app's ACS | **Reject** | Wrong target recipient |
| Valid Response yet NotOnOrAfter passed | **Reject** | Bearer subject confirmation expired |
| Response lacks InResponseTo while SP requires SP-initiated | **Reject per strict policy** | Cannot prove originating request |
| IdP-initiated Response lacks InResponseTo yet SP approved this mode | **Evaluate per separate policy** | No request correlation; still must verify trust, signature, recipient, time, and replay |

The word **"Acceptable"** is intentional: a passing InResponseTo check is only **one necessary condition**, not a conclusion that the user is fully authenticated.

## 16. Negative Testing and QA Workflow

A useful security test suite must generate **real SAMLResponses signed by a test IdP** or use supporting fixtures/SDKs. Do not manually edit signed XML and infer whether the correlation validator works, because editing XML breaks the signature and the request may be rejected **before checking InResponseTo**.

### 16.1. Tests to Include

1. **Happy path:** valid request, response/subject confirmation match ID, right browser session, valid signature/issuer/audience/time → login succeeds.
2. **Wrong Response.InResponseTo:** valid response from test IdP referencing a different request → reject.
3. **Wrong bearer InResponseTo:** test IdP issues an assertion whose SubjectConfirmationData differs from the request → reject.
4. **Missing request:** delete/expire pending request before callback → reject under strict SP-initiated.
5. **Wrong browser:** response generated for browser A, submitted in browser B → reject.
6. **Replay:** re-POST response after request was consumed → do not create a new login.
7. **IdP swap:** pending request for company, response signed by partner → reject.
8. **Wrong audience/recipient:** keep correlation valid yet wrong SAML target → reject.
9. **Expired assertion:** response arrives after NotOnOrAfter → reject.
10. **Missing cookie:** browser omits session cookie on ACS POST → fail cleanly, do not drop correlation.
11. **Multi-node:** initiate on node A, callback on node B with shared session store → works properly.
12. **Parallel tabs:** two requests and callbacks return out of order → behavior matches verified repository design, never accepting wrong request.
13. **Unsolicited:** if policy forbids, reject; if policy permits, test the separate validation suite.
14. **Open redirect:** malicious RelayState must not redirect the browser to unapproved external domains.

### 16.2. Safe Observability and Logging

In development environments you can enable:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Track **registrationId**, pending request lookup status, validation result, response status, and correlation ID in logs. Strictly never log raw **SAMLResponse**, SAMLRequest XML containing sensitive data, session cookies, private keys, or unnecessary personal NameIDs/attributes.

Some errors may be represented by **Saml2AuthenticationException** with codes such as **INVALID_IN_RESPONSE_TO**; error messages and throw sites vary by Spring Security/OpenSAML version. Do not rely solely on a single error message string in automated tests; verify both response behavior and SecurityContext state.

## 17. Common Errors

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| **InResponseTo mismatch** | Response uses another request ID or repository points to another request | Cross-check request ID, session, registration, and callback order |
| **Missing AuthnRequest** | Session expired, missing cookie, different node, overwritten repository | Inspect HttpSession/cookies/Spring Session and pending request lifecycle |
| **Login loop** | Correlation not saved properly, callback fails repeatedly | Trace redirect chain, error status, and request repository; do not disable validator |
| **Only the second tab can log in** | Repository stores only one pending request at a time | Review multi-tab design and implementation limits |
| **ACS POST lacks JSESSIONID** | SameSite, Secure, Domain/Path, or proxy | Inspect DevTools cookies, HTTPS, SameSite=None; Secure if needed |
| **Callback on another node cannot find request** | Per-instance in-memory HttpSession | Spring Session/Redis or proper routing with failover |
| **Valid signature yet login rejected** | InResponseTo, issuer, audience, recipient, time, or subject confirmation error | Inspect specific validation error, not just signature |
| **IdP-initiated login rejected** | SP requires original request; unsolicited not approved/configured | Separate modes, confirm policy; never forge request IDs |
| **Victim logged into strange account** | Missing browser-session binding/login CSRF defense | Audit repository/RelayState/global cache and restrict unsolicited |
| **Errors after Spring Security upgrade** | Differences in provider/validator/repository API or defaults | Check exact version docs, rewrite regression tests |
| **RelayState leads to external page** | Using RelayState as unvalidated URL | Validate/allowlist destination, prefer opaque server-side mapping |

**Ordered troubleshooting steps:** inspect **AuthnRequest initiation path → saved request → browser session cookie → IdP response → retrieving right pending request → matching InResponseTo → signature/Issuer/Audience/Recipient/time → Authentication**. Never start by disabling checks to "make tests pass".

## 18. Production Checklist

- [ ] SP trusts only approved IdP/metadata/verification certificates; clear registrationId/ACS.
- [ ] SP-initiated flow creates a unique **AuthnRequest.ID** and saves the pending request before sending the browser to the IdP.
- [ ] **Saml2AuthenticationRequestRepository** is used consistently in both directions.
- [ ] **Response.InResponseTo** is matched against the saved **AuthnRequest.ID**.
- [ ] **Bearer SubjectConfirmationData.InResponseTo** is verified per SAML Web Browser SSO Profile.
- [ ] Pending request is bound to the **exact browser/session**, not just global InResponseTo/RelayState.
- [ ] Single-use consumption; Response/Assertion replay controls enforced per profile and policy.
- [ ] Signature, Issuer, AudienceRestriction, Recipient/Destination, Conditions/time remain independently verified.
- [ ] **SP-initiated** and **IdP-initiated/unsolicited** are separated by explicit policy.
- [ ] Cookies/sessions on cross-site ACS POST tested; do not drop correlation due to SameSite.
- [ ] If multi-instance, session/pending request has a shared store, TTL, size limits, and proper atomic operations.
- [ ] If supporting multiple IdPs, request/response binds to the exact approved registration and issuer.
- [ ] If supporting multiple tabs, out-of-order callbacks tested; pending requests are not cross-used.
- [ ] RelayState is not usable as an open redirect or standalone proof of login.
- [ ] Negative tests exist for missing/wrong/expired/replayed requests, wrong browser, wrong IdP, and malformed responses.
- [ ] Controlled logging, without recording SAMLResponse/session cookies/private keys/sensitive NameIDs.
- [ ] Only establish **SecurityContext** and SP session after all SAML validations complete.

**Conclusion:** **InResponseTo** answers "Does this SAMLResponse/Assertion genuinely reply to the AuthnRequest that the SP issued for this browser session?". Matching must rely on the **saved request and session binding**, combined with signature, issuer, audience, recipient, timestamps, and anti-replay. In Spring Security, prefer default **saml2Login() + HttpSessionSaml2AuthenticationRequestRepository** when suitable rather than writing XML correlation logic in a controller.

## 19. References

- [Spring Security – SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): Saml2WebSsoAuthenticationRequestFilter, default request repository, RelayState, and warnings when switching to cache.
- [Spring Security – SAML 2.0 Authentication Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): Saml2AuthenticationTokenConverter, OpenSAML provider, and response/assertion validators.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML Web Browser SSO flow.
- [Spring Security 6.5 – Saml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html): save/load/remove request.
- [Spring Security 6.5 – HttpSessionSaml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/HttpSessionSaml2AuthenticationRequestRepository.html): implementation storing AuthnRequest in HttpSession.
- [OASIS SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO Profile, processing rules, unsolicited responses, and InResponseTo.
- [OASIS SAML 2.0 Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-errata-2.0-cd-04.html): bearer SubjectConfirmationData.InResponseTo and processing rules.
