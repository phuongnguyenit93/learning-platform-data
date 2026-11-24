# Application Session Lifetime, Assertion Lifetime, and Independent IdP Sessions

**Module:** Spring Security – federation  
**Parent topic:** Sessions and browsers  
**Context:** SAML 2.0 Web Browser SSO, Spring Boot 3.x, Spring Security 6.x, Java 17+.

## 1. The Most Important Point: One SSO Event Has Multiple "Clocks"

In SAML 2.0, a user logs in at an **Identity Provider (IdP)** and enters a **Service Provider (SP)** via a verified SAML Response/Assertion. At first glance, the user only "logs in once", yet the system actually maintains several distinct states and lifetimes:

1. **SAML Assertion validity:** the window during which the SP is permitted to **accept authentication evidence** received from the IdP when processing `SAMLResponse`, via **Conditions.NotBefore/NotOnOrAfter** and **SubjectConfirmationData.NotOnOrAfter**.
2. **Application session lifetime at the SP:** the duration the SP continues recognizing the user via **SecurityContext + HttpSession** or its corresponding session store; includes **idle timeout**, and potentially an application-enforced **absolute lifetime**.
3. **SSO session lifetime at the IdP:** the duration the IdP continues treating the browser as authenticated with the IdP to issue new SAMLResponses without requiring full interactive authentication; the IdP keeps its own cookie/session state.
4. **AuthnStatement.SessionNotOnOrAfter (if present):** a session boundary declared by the IdP in the **SAML AuthnStatement**; must not be automatically equated with the SP's HttpSession timeout or the IdP cookie lifetime.

The first three clocks **do not lock onto each other automatically**. A SAML assertion expiring in 5 minutes **does not mean** the SP HttpSession automatically expires at minute 5; an IdP session expiring **does not mean** an active SP session vanishes automatically. Conversely, an expired SP session does not prove the IdP session has expired either.

**Initial takeaway:** When the SP receives `SAMLResponse`, it must verify the assertion **is currently valid**; after login is accepted, sustaining access depends on **SP session policy**. Synchronizing session lifetimes or requiring re-authentication requires designing **explicit additional policies**, not inferring automatic coupling from the protocol.

## 2. Comparison Table of Four Time Layers

| Concept | Controlling Party | Field / Config | What expires? | Automatically ends SP session? |
| --- | --- | --- | --- | --- |
| **SAML Assertion validity** | Asserted by IdP, verified by SP | **Conditions.NotBefore / NotOnOrAfter**, bearer **SubjectConfirmationData.NotOnOrAfter** | Acceptability of the assertion during the login step | **Not by default** once login creates a session |
| **SP idle timeout** | SP/Servlet/Spring Session | **server.servlet.session.timeout**, **HttpSession.maxInactiveInterval** | HttpSession not accessed within the configured interval | **Yes** when the SP session expires |
| **SP absolute lifetime** | SP policy, usually enforced by the app | **authenticatedAt + maxLifetime** | Absolute limit since authentication, even with continuous activity | **Yes if enforced by the app** |
| **IdP SSO session** | IdP | IdP cookie + server-side session, IdP policy | Ability to reuse login at the IdP | **Not automatically** |
| **AuthnStatement.SessionNotOnOrAfter** | Asserted by IdP, interpreted by SP/policy | **saml:AuthnStatement SessionNotOnOrAfter** | Session boundary between subject and authentication authority declared in the assertion | **Do not assume Spring auto-maps it to HttpSession timeout** |
| **AuthnStatement.AuthnInstant** | Asserted by IdP | **saml:AuthnStatement AuthnInstant** | Not an expiry; records time of authentication | **No** |
| **SAML Response IssueInstant** | Asserted by IdP | **samlp:Response IssueInstant** | Response creation timestamp; not itself an expiry | **No** |
| **SAML metadata validUntil** | Metadata publisher | **EntityDescriptor.validUntil** | Trust metadata validity, **not a user session** | **Not directly** |

**Do not conflate them:** "assertion valid until 08:05", "IdP session until 08:30", and "SP idle timeout 30 minutes" are three different statements at three different layers. Verification procedures at each layer differ as well.

## 3. SAML XML: Pinpointing Each Timestamp

The XML snippet below is solely for **reading structure**. It lacks signatures and many parts of a valid SAML Response and **must never be put into production directly**:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion_1"
    Version="2.0"
    IssueInstant="2026-11-07T08:01:00Z">
  <saml:Issuer>https://idp.example.org/saml/company</saml:Issuer>

  <saml:Subject>
    <saml:NameID>employee-847</saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          InResponseTo="_authn_req_123"
          Recipient="https://portal.example.org/login/saml2/sso/company"
          NotOnOrAfter="2026-11-07T08:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>

  <saml:Conditions
      NotBefore="2026-11-07T08:00:00Z"
      NotOnOrAfter="2026-11-07T08:05:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://portal.example.org/saml/sp/company</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>

  <saml:AuthnStatement
      AuthnInstant="2026-11-07T07:45:00Z"
      SessionIndex="idp-session-index-77"
      SessionNotOnOrAfter="2026-11-07T08:30:00Z">
    <saml:AuthnContext>
      <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
      </saml:AuthnContextClassRef>
    </saml:AuthnContext>
  </saml:AuthnStatement>
</saml:Assertion>
~~~

### 3.1. Conditions.NotBefore and Conditions.NotOnOrAfter

- **NotBefore** (when declared): earliest instant at which the assertion is valid under Conditions.
- **NotOnOrAfter** (when declared): **at this exact instant the assertion is no longer valid**; "on or after" means the boundary instant itself is excluded.
- Conditions also contains **AudienceRestriction** and other constraints. An assertion must still be rejected if Audience/Issuer/signature is wrong, even when timestamps are valid.

In the example:

~~~text
08:00:00Z                  Conditions take effect
08:04:59Z                  Not yet at NotOnOrAfter
08:05:00Z                  At NotOnOrAfter -> invalid
08:05:01Z                  Invalid
~~~

Real validators may have a bounded **clock skew tolerance** to accommodate clock drift between IdP and SP; never add a "30-minute grace period" to assertions or drop `NotOnOrAfter` because browsers are slow. Test policies must account for configured clock skew consistently with the SAML standard.

### 3.2. SubjectConfirmationData.NotOnOrAfter

For bearer confirmation used in **SAML Web Browser SSO Profile**, **SubjectConfirmationData** carries specific constraints such as:

- **Recipient:** the SP ACS that must receive the assertion.
- **InResponseTo:** correlates with the AuthnRequest stored by the SP during SP-initiated login.
- **NotOnOrAfter:** deadline for accepting the bearer assertion to confirm the subject.

The SP must check **both Conditions** and **bearer SubjectConfirmationData** per the profile, rather than picking whichever NotOnOrAfter looks longer. In the example both end at 08:05; if bearer NotOnOrAfter were **08:04** while Conditions were **08:05**, the effective acceptance deadline is tightened to **08:04**.

**Bearer confirmation expiry must not be interpreted as automatically destroying a previously created SP HttpSession.** It prevents **reusing the assertion as proof during the authentication step**, working alongside request correlation and replay checks.

### 3.3. AuthnInstant Is Not Assertion IssueInstant

**AuthnInstant=07:45Z** means the IdP states the user authenticated at 07:45. **Assertion IssueInstant=08:01Z** is when the assertion was issued. The IdP can issue a fresh assertion from an **existing IdP session**, so AuthnInstant can be older than IssueInstant.

If business rules require "authenticated within 10 minutes before approving a wire transfer", looking only at a recent Assertion IssueInstant does not prove the user just re-authenticated. You need an **authentication freshness** policy based on AuthnInstant/appropriate auth signals, controlled reauthentication requests, and verification that the IdP honored them.

### 3.4. SessionNotOnOrAfter and SessionIndex

**AuthnStatement.SessionNotOnOrAfter** is the time boundary of the **session declared by the authentication authority (IdP)**. Per SAML Core, it is the instant at or after which the session between the subject and authentication authority must be considered ended. This attribute **may be omitted**.

**SessionIndex** is a SAML session identifier for correlation between IdP and SP, especially for SAML Single Logout. It is **not** the application's `JSESSIONID` or Redis session key.

**Caution:** SessionNotOnOrAfter asserted inside an assertion **does not automatically alter the SP HttpSession's `maxInactiveInterval` in Spring Security 6**. If SP policy requires the application session to end at the IdP-declared deadline, extract it from the verified assertion, store a safe limit at the SP, and enforce it actively. Never extract SessionNotOnOrAfter from unverified XML.

## 4. Three Cookies/Sessions in the Browser: IdP and SP Are Independent

After SSO, the browser typically holds:

~~~text
Browser
  |
  +-- IdP cookie (domain idp.example.org)
  |      -> IdP checks SSO session and login time
  |
  +-- SP cookie (domain portal.example.org)
  |      -> SP/Servlet/Spring Session locates HttpSession
  |      -> SecurityContext holds the user's Authentication
  |
  +-- SAMLResponse (passes through ACS callback only during login)
         -> Assertion is not re-sent on ordinary HTTP requests
~~~

**The IdP cookie and SP cookie have different domains and different owners.** The SP cannot read ordinary IdP session cookies, nor can it inspect the SP cookie to tell whether the IdP session has expired. An IdP "SSO session expired" notice appears only when the browser/flow actually interacts with the IdP again or via a designed notification/revocation channel.

What commonly happens:

1. User visits the SP for the first time with no SP session → Spring starts SAML login.
2. If the browser still has a valid IdP session, the IdP can issue a new SAMLResponse without prompting the user for a password again.
3. The SP verifies the assertion at the ACS and creates **Saml2Authentication**, storing it in SecurityContext/HttpSession.
4. Subsequent requests to the SP primarily use the SP session cookie without calling the IdP.
5. The IdP session can expire between steps 3 and 4 without the SP receiving any event.

**Do not equate "closing a browser tab" with logging out.** Session cookies may be restored by the browser, backend sessions remain alive, and the IdP may have its own remember-me policy. Only actual session invalidation/expiration guarantees the SP stops accepting that session.

## 5. SP Idle Timeout: What Does "30 Minutes of Inactivity" Mean?

In a Servlet application, **HttpSession.maxInactiveInterval** represents the **interval without requests accessing the session** before the session is deemed expired. Common Spring Boot config:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
~~~

This is an **idle timeout**, not an absolute cap measured from when the user logged in.

Example:

~~~text
08:01  SAML login -> SP session active
08:10  GET /me -> session accessed
08:30  GET /dashboard -> session accessed again
08:55  GET /reports -> session still active if idle timeout = 30m
09:24  GET /orders -> session still active if idle timeout = 30m
...
~~~

If valid requests keep arriving before the idle deadline, the session can survive for a very long time unless bounded by **absolute lifetime, account revocation, logout, session store TTL**, or other policies.

**Note:** This describes the logical behavior; exact moments when containers update `lastAccessedTime`, session invalidation mechanics, and Redis/DB expiration may vary slightly. Background AJAX/polling requests from an open tab can also keep accessing the session without representing real user interaction.

### Idle Timeout Is Not Cookie Max-Age

A session cookie **without a fixed Max-Age** merely means the browser handles it with session-cookie semantics. It does not guarantee the backend keeps the session forever, nor does it prove the backend deleted the session when the browser closed. Conversely, an existing cookie cannot resurrect an expired HttpSession.

**Never use cookie expiration as the sole source of truth for authorization.** The backend must check session existence, SecurityContext validity, approved account/permissions, and additional policy limits.

## 6. SP Absolute Lifetime: Capping Sessions Even While Active

Many financial, HR, or administrative applications need a **maximum lifetime after authentication**, such as **8 hours**, even if the user keeps clicking continuously.

Illustrative policy:

~~~text
authenticatedAt = 08:01 UTC
idleTimeout = 30 minutes
absoluteLifetime = 8 hours

sessionActive(now) =
    now < authenticatedAt + 8 hours
    AND now < lastActivityAt + 30 minutes
    AND localAccountEnabled
    AND not revoked
~~~

**Absolute lifetime must be implemented by the application** or a session management system supporting it. Configuring **server.servlet.session.timeout** alone does not create an absolute lifetime. You can store a client-tamper-proof timestamp **SP_AUTH_AT** inside the server-side session, then enforce the cap in a filter/policy interceptor/authorization boundary.

Points to protect:

- `authenticatedAt` must be recorded **after SAML validation succeeds**, never read from an HTTP request parameter.
- Do not reset absolute lifetime just because the user refreshes a page; reset only upon a verified new reauthentication per policy.
- Once absolute lifetime expires, **invalidate the session** and clear SecurityContext rather than merely hiding UI buttons.
- Across multiple nodes, store `authenticatedAt` in the shared session store with synchronized clocks.
- When multiple login mechanisms exist, track authentication times per `Authentication` instead of treating every anonymous session as authenticated.
- When **MFA/step-up** occurs, store the step-up timestamp separately; do not conflate it with the initial SP login timestamp.

### Do Not Blindly Assign SessionNotOnOrAfter as the SP Lifetime

An organizational policy may require SP sessions not to exceed the IdP-declared lifetime. In that case, the **enforced SP session deadline** is the earliest of:

~~~text
spAbsoluteDeadline =
    min(
      spAuthenticatedAt + spAbsoluteLifetime,
      idpSessionNotOnOrAfter (if verified and required by policy),
      userRevocationDeadline (if present)
    )
~~~

Alongside this, an independent **idle timeout** still applies. This is a **custom application rule**, not default behavior inferred by SAML/Spring Boot. When the IdP omits SessionNotOnOrAfter, enforce a local absolute cap rather than assuming the IdP session never expires.

## 7. When the IdP Session Expires While the SP Session Is Alive

Scenario:

~~~text
08:00  User logs in at IdP
08:01  IdP issues assertion (valid until 08:05)
08:01  SP verifies successfully and creates 30m idle timeout session
08:30  IdP session is considered ended per policy/declaration
08:31  User still interacts with SP; SP session may remain valid
08:40  SP hits idle timeout if last request was 08:10
~~~

At **08:31**, if the browser only calls SP resources and the SP session is active, Spring Security normally reads the **SecurityContext stored in HttpSession**. It **does not call back to the IdP on every request** to check whether the IdP cookie is still valid.

If the SP session expires at 08:40 and the browser visits again at 08:41:

- The SP initiates a new SAML login.
- If the IdP session is still valid, the IdP can silently SSO and return a new assertion.
- If the IdP session has expired, the IdP may require re-login or authentication steps per IdP policy.
- Regardless of whether the IdP prompts for a password, the SP must still **verify a fresh SAMLResponse** per rules before granting a new session.

**Disabling a user at the IdP** also does not automatically delete all SP sessions immediately. If policy demands near-real-time revocation, the SP needs revalidation, local account status checks, SLO/session revocation, or designed and tested event mechanisms. Do not rely solely on past assertion expiry to terminate sessions.

## 8. Reverse Scenario: SP Times Out Before the IdP

For example, the IdP SSO session lasts until 18:00 while the SP idle timeout is only 15 minutes.

~~~text
09:00  IdP login, SP creates session
09:10  User stops using application
09:25  SP session hits idle timeout
09:26  User opens /me; SP no longer has SecurityContext
09:26  Browser is redirected to IdP
09:26  IdP still has SSO session -> issues new SAMLResponse
09:26  SP verifies and creates new session
~~~

The user may see a **brief redirect flicker** and think "the SP never logged out", even though the old SP session expired and a **new SAML login transaction** just succeeded. To force the user to re-enter an authentication factor, lowering SP idle timeout alone is **not enough**; you must request **reauthentication** from the IdP per policy.

SAML **AuthnRequest `ForceAuthn=true`** can ask the IdP for fresh authentication instead of silently reusing an existing session, provided the IdP/profile supports and enforces it. **`ForceAuthn` does not guarantee MFA or guarantee a password prompt**; the exact authentication factor depends on `AuthnContextRequested`, IdP policy, and federation agreements. If a sensitive app needs fresh MFA, specify the assurance level and verify `AuthnInstant`/`AuthnContext` after callback.

## 9. When the Assertion Has Expired While the SP Session Remains Active

This is the single most important comprehension check.

**Suppose** an assertion has **Conditions.NotOnOrAfter=08:05**; the SP receives and validly verifies it at **08:01**, then stores SecurityContext. At **08:20**, the browser accesses `/reports` with a still-valid SP session cookie.

**What is right:** The SP can allow the 08:20 request under **SecurityContext/session + authorization policy** without requiring the "08:05" assertion to still be alive. The assertion served as **point-in-time authentication evidence**, not a bearer access token re-sent and re-validated on every request.

**What is wrong:** Saving the raw SAMLResponse as a credential and replaying it at 08:20 to "refresh login" or mint new OAuth tokens while bypassing `NotOnOrAfter`/replay protection. When fresh authentication is needed, execute a **new SAML transaction** with a new valid Response, or a clearly designed refresh/re-auth mechanism.

In **OAuth2/OIDC** integrations, access tokens and ID tokens serve different purposes, audiences, and expirations. Do not copy-paste "JWT access token exp" logic directly onto SAML Assertions at the ACS or vice versa.

## 10. How Does Spring Security Manage SecurityContext and HttpSession?

Typical flow:

~~~text
GET /private
  -> SecurityFilterChain
  -> no Authentication in SecurityContext yet
  -> AuthenticationEntryPoint initiates SAML2 Login
  -> SP stores AuthnRequest in HttpSession
  -> browser goes to IdP
  -> POST SAMLResponse to ACS
  -> Saml2WebSsoAuthenticationFilter + AuthenticationManager
  -> verify signature/issuer/audience/recipient/time/correlation
  -> verified Saml2Authentication
  -> SessionAuthenticationStrategy (session fixation protection)
  -> SecurityContextHolder
  -> SecurityContextRepository saves context into HttpSession
  -> subsequent HTTP requests restore context from HttpSession
~~~

**Important:** An HttpSession **can be created before the user logs in** to store AuthnRequest/SavedRequest. An existing session does not mean the user is authenticated. Upon successful SAML login, Spring Security typically **rotates the session ID** for session fixation protection under the default strategy on Servlet 3.1+.

Spring Security 6 uses **SecurityContextHolderFilter** and explicit saving by default; standard **`saml2Login()`** handles persistence automatically upon successful authentication. Custom code modifying `Authentication` must call **`SecurityContextRepository.saveContext(...)`** to persist across requests, though **never write a custom SAMLResponse verification filter** just to save sessions.

### Which SessionCreationPolicy Should You Choose?

| Policy | Short Meaning | For SAML2 Browser SSO |
| --- | --- | --- |
| **IF_REQUIRED** | Spring creates a session when needed | Fits session-based browser SSO deployments |
| **ALWAYS** | Creates a session on every entry to the chain | Usually unnecessary; increases resource usage |
| **NEVER** | Spring does not proactively create a session yet may use an existing one | Can affect request correlation/login; test very carefully |
| **STATELESS** | Does not use HttpSession for SecurityContext | Unsuitable by default for SAML2 browser SSO needing request correlation/session persistence |

**Do not set `STATELESS` on a web SAML2 chain** merely to save RAM while `AuthenticationRequestRepository` still uses HttpSession. For Bearer JWT APIs, create a **separate stateless `SecurityFilterChain`**; do not apply it to the ACS/browser login chain.

## 11. Spring Boot 3 + Java 17 Example: 30-Minute SP Session Independent of IdP/Assertion

The hands-on example below targets **Spring MVC Servlet + SAML2 login**. Completing real login requires an **IdP with valid metadata XML**, SP entityID/ACS registered at the IdP, policy-compliant signing/decryption credentials, and a public HTTPS domain. The **example.org** domain is illustrative only, not a live IdP.

### 11.1. Dependencies

In the dependencies section of **`pom.xml`** for a Maven project with a compatible Spring Boot parent/BOM:

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

If IdP metadata is stored on the classpath, you need a vetted **`src/main/resources/metadata/company-idp.xml`** file; do not treat an unsigned sample XML without certificates as a real IdP. Keep dependency versions aligned with the Boot BOM to avoid mixing incompatible OpenSAML versions.

### 11.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    idp-metadata-location: classpath:metadata/company-idp.xml

server:
  servlet:
    session:
      timeout: 30m
~~~

**timeout: 30m** is the SP HttpSession **idle timeout**. It **does not** set assertion `NotOnOrAfter`, alter the IdP SSO cookie lifetime, or automatically create an absolute SP session lifetime.

HTTPS production setups typically require `Secure`/`HttpOnly` cookies. With an IdP using **cross-site HTTP-POST binding** to the ACS, **SameSite** policy must also be browser-tested; **`SameSite=Lax/Strict` may block session cookies on cross-site POSTs**. If **`SameSite=None; Secure`** over HTTPS is required, keep CSRF protection enabled for application actions (see section 15). Never blindly enable `Secure` cookies while debugging over plain HTTP localhost.

### 11.3. Main class

**src/main/java/com/example/session/SessionLifecycleApplication.java**

~~~java
package com.example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
~~~

### 11.4. Spring Security configuration

**src/main/java/com/example/session/SamlSecurityConfig.java**

~~~java
package com.example.session;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.idp-metadata-location}") String location) {

        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(location)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .logout(logout -> logout.logoutSuccessUrl("/"));

        return http.build();
    }
}
~~~

**Key explanations:**

- **`RelyingPartyRegistrations.fromMetadataLocation(...)`** loads trusted IdP configuration; **`registrationId=company`** keys the SP–IdP relationship.
- **SP entityID/ACS** must match the IdP registration. When running on localhost, an `example.org` ID/ACS cannot route callbacks back to localhost.
- **`saml2Login()`** enables SAML Web Browser SSO and provider checks.
- **`SessionCreationPolicy.IF_REQUIRED`** lets Spring create HttpSessions when browser SAML flows need them.
- **`sessionFixation().changeSessionId()`** rotates the session ID upon authentication success, preventing fixation.
- **`logoutSuccessUrl("/")`** handles routing after **local logout**; it does not enable **SAML Single Logout** at the IdP.
- **Never disable CSRF app-wide** to "fix" callbacks, nor manually parse SAMLResponse inside a controller.

### 11.5. Controller Observing the SP Session Without Reading the IdP Cookie

**src/main/java/com/example/session/SessionController.java**

~~~java
package com.example.session;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/")
    public String home() {
        return "SAML session lifetime demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentSession(
            Authentication authentication,
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);

        return Map.of(
            "authenticated", String.valueOf(authentication.isAuthenticated()),
            "registrationId", principal.getRelyingPartyRegistrationId(),
            "spSessionPresent", String.valueOf(session != null),
            "spIdleTimeoutSeconds", String.valueOf(
                session == null ? -1 : session.getMaxInactiveInterval())
        );
    }
}
~~~

**Why use `getSession(false)`?** It only reads the existing session if present, **without creating a new session** during observation. Meanwhile, **`getMaxInactiveInterval()`** returns the configured idle interval in **seconds**, not the remaining seconds of the session; do not calculate exact remaining TTL from that property.

The controller assumes **`/me` is accessed only via SAML2 Authentication** in this example. If multiple login mechanisms exist, check principal nullness/type. In production never expose session IDs, raw SAMLResponses, cookies, or sensitive identifying attributes in responses/logs; the values shown here are purely technical metrics.

### 11.6. Running and Observing

In a Maven project with JDK 17+ and real metadata:

~~~bash
mvn spring-boot:run
~~~

Public endpoint once the app starts cleanly:

~~~bash
curl -i http://localhost:8080/
~~~

Response body matching the controller:

~~~text
SAML session lifetime demo
~~~

To verify real sessions:

1. Open **`/me`** via the public SP URL registered with the IdP.
2. The browser redirects to the IdP, authenticates, and POSTs a valid SAMLResponse to the ACS.
3. The SP creates Authentication/HttpSession; **`/me`** may return **`authenticated=true, spSessionPresent=true, spIdleTimeoutSeconds=1800`** per config.
4. Reload `/me` before the idle timeout: the SP restores SecurityContext from the session cookie without needing a new SAMLResponse.
5. Wait long enough for the session to expire, then call `/me`: the SP requires a new authentication round-trip; the IdP may silently SSO if the IdP session remains active.
6. Test local logout, deleting the SP cookie, IdP session expiry, and fresh SAML callbacks as separate scenarios.

There is no exact fixed JSON stdout for users/IdPs because it depends on the live environment and session. **1800** is the number of seconds equivalent to 30 minutes per the sample config; containers may override timeouts via other settings, so verify at runtime.

## 12. Runnable Java 17: Three Clocks Without Automatic Coupling

The following Java 17 program **runs standalone**, needing no Spring Boot/IdP/DB. It simulates **assertion validity**, a given **IdP session boundary**, and **SP idle/absolute lifetimes** across fixed UTC instants. This is a logic exercise, **not a SAML signature validator** or production session solution.

**File: SessionClockDemo.java**

~~~java
import java.time.Duration;
import java.time.Instant;

public final class SessionClockDemo {

    enum LocalStatus {
        ACTIVE,
        IDLE_EXPIRED,
        ABSOLUTE_EXPIRED
    }

    record LocalSession(
            Instant authenticatedAt,
            Instant lastSeenAt,
            Duration idleTimeout,
            Duration absoluteLifetime) {

        LocalStatus statusAt(Instant now) {
            if (!now.isBefore(authenticatedAt.plus(absoluteLifetime))) {
                return LocalStatus.ABSOLUTE_EXPIRED;
            }
            if (!now.isBefore(lastSeenAt.plus(idleTimeout))) {
                return LocalStatus.IDLE_EXPIRED;
            }
            return LocalStatus.ACTIVE;
        }
    }

    static boolean assertionValidAt(
            Instant now, Instant notBefore, Instant notOnOrAfter) {

        return !now.isBefore(notBefore)
            && now.isBefore(notOnOrAfter);
    }

    static boolean idpSessionValidAt(
            Instant now, Instant sessionNotOnOrAfter) {
        return now.isBefore(sessionNotOnOrAfter);
    }

    public static void main(String[] args) {
        Instant before = Instant.parse("2026-11-07T08:00:00Z");
        Instant assertionEnd = Instant.parse("2026-11-07T08:05:00Z");
        Instant idpEnd = Instant.parse("2026-11-07T08:30:00Z");

        LocalSession sp = new LocalSession(
            Instant.parse("2026-11-07T08:01:00Z"),
            Instant.parse("2026-11-07T08:10:00Z"),
            Duration.ofMinutes(30),
            Duration.ofMinutes(90));

        System.out.println("assertionAt0804=" + assertionValidAt(
            Instant.parse("2026-11-07T08:04:00Z"),
            before, assertionEnd));
        System.out.println("assertionAt0805=" + assertionValidAt(
            assertionEnd, before, assertionEnd));
        System.out.println("spAt0820=" + sp.statusAt(
            Instant.parse("2026-11-07T08:20:00Z")));
        System.out.println("idpAt0831=" + idpSessionValidAt(
            Instant.parse("2026-11-07T08:31:00Z"), idpEnd));
        System.out.println("spAt0831=" + sp.statusAt(
            Instant.parse("2026-11-07T08:31:00Z")));
        System.out.println("spAt0840=" + sp.statusAt(
            Instant.parse("2026-11-07T08:40:00Z")));

        LocalSession busySp = new LocalSession(
            Instant.parse("2026-11-07T08:01:00Z"),
            Instant.parse("2026-11-07T09:20:00Z"),
            Duration.ofMinutes(30),
            Duration.ofMinutes(90));

        System.out.println("spAt0931=" + busySp.statusAt(
            Instant.parse("2026-11-07T09:31:00Z")));
    }
}
~~~

Compile/run:

~~~bash
javac SessionClockDemo.java
java SessionClockDemo
~~~

**Exact stdout on Java 17+:**

~~~text
assertionAt0804=true
assertionAt0805=false
spAt0820=ACTIVE
idpAt0831=false
spAt0831=ACTIVE
spAt0840=IDLE_EXPIRED
spAt0931=ABSOLUTE_EXPIRED
~~~

Explanation:

- At 08:04 the assertion is still within its validity window; **08:05 equals NotOnOrAfter**, so false.
- The SP session logged in at 08:01 and was last accessed at 08:10; at 08:20 and **08:31** the SP remains active under the 30-minute idle and 90-minute absolute limits.
- The IdP session per the **08:30** boundary expired by 08:31, yet **does not automatically expire the SP session**.
- **08:40** reaches 30 minutes since the last access at 08:10 → SP idle expired.
- For another session remaining active until 09:20, by **09:31** it hits **90 minutes since the 08:01 login**, so absolute expired despite only 11 minutes of idle time.

**Technical boundary:** The program assumes state instants come from a trusted source; it does not fetch real IdP cookies or parse SAML Responses. Use an injected **`Clock`** or synchronized server UTC time in production; never accept client-supplied timestamps to extend sessions. When the IdP omits `SessionNotOnOrAfter`, apply a dedicated policy rather than assuming an arbitrary timestamp.

## 13. Enforcing Absolute Timeout in a Real Application

Spring Boot **does not automatically enforce an absolute timeout on authenticated sessions solely via idle timeout configuration**. To enforce an 8-hour cap, an application can:

1. Upon **SAML login success**, record an **`authenticatedAt`** from the server clock into the session, **after** SAML validation and after applying `SessionAuthenticationStrategy`. Never take it from a query/header.
2. On each protected request, use a filter/authorization service that reads the existing session **without creating a new session**, and checks the deadline.
3. If the deadline is reached, invalidate the HttpSession, clear SecurityContext via Spring's logout/repository mechanisms, and require a new authentication cycle.
4. If preserving the original target request is desired, use an appropriate SavedRequest/request cache; never redirect to arbitrary client-supplied addresses.
5. Share `authenticatedAt` via Spring Session/Redis across multiple nodes and enforce concurrent session controls.
6. Do not reset `authenticatedAt` on every GET or whenever the IdP sends a fresh assertion if policy mandates a strict absolute cap from initial login.
7. Test after logout, expired sessions, multiple tabs, browser restore, locked users, node switching, and step-up.

Example **policy logic snippet** (not a standalone filter):

~~~java
Instant now = clock.instant();
Instant authenticatedAt =
    (Instant) session.getAttribute("SP_AUTHENTICATED_AT");

if (authenticatedAt == null
        || !now.isBefore(authenticatedAt.plus(Duration.ofHours(8)))) {
    // In production flow: use logout/session-invalidation
    // configured by Spring Security to clean up context/session.
    session.invalidate();
    SecurityContextHolder.clearContext();
    response.sendRedirect(request.getContextPath() + "/reauth");
    return;
}
~~~

This snippet only **illustrates where to place the check**: session, clock, response, and security context are passed into an appropriate flow; the `/reauth` URL must be configured safely without causing redirect loops. In a real application, prefer Spring-configured **`LogoutHandler`/`SecurityContextRepository`** to clean state completely, rather than just the two statements in the fragment.

**Defense in depth:** for highly sensitive actions, authorization decisions should also check **account enabled/permissions** at action time. Ending sessions by time is one condition; granting access must not rely solely on "the session hasn't timed out yet".

## 14. Controlling Sessions Across Multiple Instances

If an application runs multiple pods/nodes behind a load balancer, per-node local sessions can cause:

- AuthnRequest stored on node A yet SAMLResponse POSTs to node B → lost request correlation.
- Login succeeds on node A, next request hits node B → lost SecurityContext.
- Absolute `authenticatedAt` stored only on one node → nodes calculate differently.
- Session revoked on A yet still active on B → fails security policy.

**Spring Session** with Redis/DB is one approach to share HttpSession across multiple instances, leveraging Spring Security's session cookie logic and repositories:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Metadata/RelyingPartyRegistration must be uniform across nodes, Redis secured with TLS/ACLs, session data given appropriate TTLs/serializers, clocks synchronized, and session invalidation propagated properly. Sticky sessions can reduce node switching but are a poor substitute for consistent failover/revocation management.

**Do not treat Redis TTL as an absolute session policy** if the adapter continually extends TTL whenever the session is accessed; maintain a separate absolute timestamp if business rules require it. Never put session IDs or SAMLResponses into logs/URLs.

## 15. Cookies and CSRF When the Browser Returns from the IdP

SAML Web Browser SSO commonly uses **HTTP-POST binding**: an IdP on another domain POSTs SAMLResponse to the SP's **ACS**. When AuthnRequest was stored in HttpSession, the SP needs the browser to send the right session cookie on the callback to correlate **`InResponseTo`/`RelayState`**.

- **Secure**: cookie sent only over HTTPS.
- **HttpOnly**: JavaScript cannot read the cookie.
- **SameSite**: **Lax/Strict may block the cookie on cross-site POSTs**. If needed over production HTTPS, **`SameSite=None; Secure`** may be used.
- **Domain/Path**: must fit the SP's public hostname/callback; reverse proxies must not rewrite wrong cookie domains.
- **CSRF protection**: remains mandatory for business POST/PUT/DELETE endpoints using session cookies; **never disable CSRF app-wide** just to fix SAML callbacks.

Example cookie policy **strictly for HTTPS production environments tested with cross-site POST**:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: none
      timeout: 30m
~~~

Depending on Servlet container/Spring Session, the cookie name may be **`JSESSIONID`** or **`SESSION`**. A browser may still hold a cookie after the backend session expires; in that case the request must re-login and cannot be "recovered" merely by keeping the old cookie.

If the cookie is missing on the ACS POST, never "fix" it by disabling `InResponseTo`, Audience, or signature validation. That widens the trust boundary to mask a session/binding bug.

## 16. Local Logout, SAML Single Logout, and IdP Expiration

**Local logout at the SP** (typically POST **`/logout`** with a valid CSRF token) clears SecurityContext and invalidates the local HttpSession. It **does not automatically** log out the IdP or other SPs.

**SAML Single Logout** is a distinct flow requiring **`saml2Logout()`**, SingleLogoutService endpoints, and matching signing/verification credentials when the IdP supports it. Either SP or IdP can initiate a LogoutRequest; the recipient returns a LogoutResponse. Only when all parties cooperate and browser/network flows complete uninterrupted can multiple sessions be expected to terminate per policy.

| Event | SP session | IdP session | Other SPs |
| --- | --- | --- | --- |
| SP idle timeout | Expires | May remain | Not automatically affected |
| SP absolute timeout | Expires if implemented | May remain | Not automatically affected |
| SAML assertion NotOnOrAfter passes after login | May remain | Cannot infer state | Cannot infer |
| User performs local logout at SP | Deleted | May remain | May remain |
| User logs out at IdP without SLO to SP | May remain | Expires | May remain |
| SLO completes successfully across parties | Related session terminated | Per IdP outcome | Only SPs that actually participated/succeeded |

**Do not treat redirecting the browser to `/login?logout` as proof that all IdPs/SPs ended their sessions.** With `PartialLogout` or users closing tabs mid-cascade, results may not be global. Clear UX and session timeouts/response handling are needed as additional defense layers.

## 17. Authentication Freshness for Sensitive Operations

A common policy:

- **Viewing dashboard:** valid SP session and required role.
- **Viewing confidential data:** valid SP session, unrevoked account, and active DB permissions.
- **Approving money transfers:** valid SP session, **recent AuthnInstant** or strong authentication/step-up meeting assurance levels and business approval.
- **Changing password/API keys:** requires fresh authentication per dedicated policy, never relying solely on a long-lived SP session.

Distinguish carefully:

1. **Assertion IssueInstant:** when the IdP issued the assertion; can be brand new even if the user logged into the IdP hours ago.
2. **AuthnInstant:** when the IdP states the user authenticated; better suited for freshness checks, yet must be verified and interpreted with the right context/issuer.
3. **`ForceAuthn` in AuthnRequest:** signals a request for fresh authentication at the IdP, not self-contained proof that MFA occurred.
4. **`AuthnContextClassRef`:** describes authentication context/level per IdP; requires an explicit contract rather than assuming "PasswordProtectedTransport" means MFA.
5. **Local step-up timestamp:** trustworthy only if recorded by the app after a verified strong-auth step, never self-reported by the client.

If policy requires shortening the IdP session to match the SP, work with the IdP and design re-authentication/SLO. **Do not set SP idle timeout = assertion lifetime** merely because both are durations.

## 18. Scenario Matrix for Right Conclusions

| Scenario | What should the SP do? |
| --- | --- |
| SAMLResponse arrives at ACS at **08:04**, NotOnOrAfter=08:05, all other checks valid | Can create a new SP session |
| SAMLResponse arrives at **08:05** sharp, ignoring illustrative clock skew | Reject assertion; do not create Authentication from that response |
| User has valid SP session at **08:20**, initial assertion expired at 08:05 | Can proceed after checking SP session/authorization |
| IdP cookie expires at **08:30**, SP session remains valid | Do not delete SP session automatically unless policy/revocation/SLO requires it |
| SP session expires at **08:40**, IdP session remains | Start new SAML login; IdP may SSO without password |
| SP session expired and IdP session also expired | Start new SAML login; IdP may require re-authentication |
| Browser loses SP cookie while IdP session remains | Run a new SAML login loop; do not restore SP SecurityContext from a nonexistent cookie |
| AuthnStatement SessionNotOnOrAfter=08:30 while SP timeout is configured for 2 hours | Do not assume Spring auto-caps SP at 08:30; if policy requires it, enforce that deadline explicitly |
| DB/IdP locks user after SP login | SP may not know automatically; requires revocation/revalidation/session policy |
| Absolute deadline reached even while user keeps clicking | Terminate SP session if absolute policy is implemented |
| User performs local logout while IdP session remains | May SSO back in quickly; to link logouts, configure SLO |
| AuthnInstant is too old for sensitive transaction, Assertion IssueInstant is fresh | Require appropriate fresh auth/step-up; do not equate IssueInstant with AuthnInstant |

## 19. Testing and Troubleshooting

### 19.1. Minimum Test Suite

1. **Expired assertion at ACS:** have a test SAML IdP issue an assertion past `NotOnOrAfter` with a valid signature; verify failure (do not merely mutate signed XML and fail signature first).
2. **Future NotBefore:** rejected before permitted time, accounting for configured clock skew.
3. **Bearer SubjectConfirmationData expires before Conditions:** rejected at the stricter deadline.
4. **Assertion valid at login yet expires afterward:** SP session stays active per independent policy.
5. **SP idle timeout:** stop sending requests long enough; session expires.
6. **SP absolute timeout:** keep sending requests; still expires at absolute deadline.
7. **IdP session expires before SP:** SP requests continue under local session without auto-redirecting unless triggered by reauth.
8. **SP session expires before IdP:** browser goes through a new SAML login, potentially without entering a password.
9. **ForceAuthn/freshness:** inspect `AuthnInstant`/`AuthnContext` of the new assertion, not just redirects.
10. **User revoked at IdP:** verify SLA for detecting/revoking local sessions per policy rather than assuming automatic sync.
11. **Local logout:** SP session is invalidated while IdP may remain active.
12. **SLO:** verify IdP/SP notifications and handling of `SessionIndex`/LogoutRequest/Response.
13. **SameSite cookie:** cross-site ACS POST still carries the cookie needed to find AuthnRequest.
14. **Two nodes:** log in on node A, request node B; session/deadlines remain consistent.
15. **Clock skew:** test boundaries around `NotBefore`/`NotOnOrAfter` without adding unbounded grace periods.
16. **Browser restore:** old cookies cannot resurrect an expired backend session.
17. **Multiple tabs:** one tab sending keep-alives may extend idle timeout; absolute lifetime still caps it.
18. **Post-login authorization:** valid session with revoked role/DB grant must be handled per authorization policy.

### 19.2. Common Errors

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| Login fails with "assertion expired" | IdP/SP clock skew, network delay, overly short NotOnOrAfter | NTP, UTC timestamps, proper clock skew policy, and ACS test |
| SP logs out earlier than IdP | SP idle/absolute timeout shorter than IdP session | Check each party's policy; do not call it an IdP bug |
| SP stays active after IdP session expires | SP HttpSession is independent and lacks SLO/revalidation | Design revocation/reauthentication if business requires |
| User immediately logs back in after SP timeout | IdP session still valid and issues a new assertion | Inspect new SAML transaction and `AuthnInstant` |
| Session seems never to expire | Heartbeats/AJAX continuously refresh idle timer | Inspect network traffic; add an absolute cap |
| SP session lost mid-SAML callback | SameSite, Secure, reverse proxy, multi-node | ACS POST cookies, AuthnRequest repo, and shared store |
| `GET /me` keeps redirecting | Cookie not saved/sent, backend session lost, wrong ACS | Session cookie flags, backend session store, SAML validation |
| Cookie present yet login lost | HttpSession expired or revoked | Inspect backend expiration, not just DevTools cookies |
| IdP group removed yet SP role unchanged | Principal/SecurityContext is a login-time snapshot | Refresh/revoke authorities/sessions per policy |
| User just logged out yet got logged back in fast | Local logout only while IdP session persists | Configure SLO/re-auth as needed |
| Expiration tests show inconsistent outcomes | Ignoring timezones, skew, NotOnOrAfter exclusivity | Use `Instant`/UTC, controlled `Clock`, and exact profiles |

In dev you can temporarily enable DEBUG:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

**Never write SAMLResponses, cookies, `SessionIndex`, `JSESSIONID`, private keys, or unnecessary identifying data** into logs, test reports, or issue trackers. Use correlation IDs and minimized timestamps; synchronize server clocks and add metrics tracking session expiration/re-authentication failures.

## 20. Production Checklist

- [ ] SAMLResponse is verified for signature, Issuer, AudienceRestriction, Recipient, InResponseTo, and **time conditions** before creating Authentication.
- [ ] **Conditions.NotOnOrAfter** and **SubjectConfirmationData.NotOnOrAfter** are distinguished from SP session lifetime.
- [ ] **Assertion IssueInstant** is never used instead of **AuthnInstant** for freshness checks.
- [ ] **SessionNotOnOrAfter** is understood as IdP session data and does not automatically become Spring's HttpSession timeout.
- [ ] Appropriate **SP idle timeout** is set, ensuring browser/background requests do not inadvertently keep sessions alive forever.
- [ ] Where needed, server-side **SP absolute lifetime** is enforced without resetting on every GET.
- [ ] If policy binds SP sessions to a verified IdP session deadline, the earliest-deadline cap is implemented properly.
- [ ] Account-disable/permission-revocation policy exists for active SP sessions.
- [ ] Browser SAML2 chain uses an appropriate **SecurityContextRepository/HttpSession**; `STATELESS` is not accidentally enabled.
- [ ] Cookies use HTTPS Secure/HttpOnly and POST-callback-compatible SameSite; business CSRF remains protected.
- [ ] Across multiple nodes, session/reauth timestamps are shared consistently and clocks are synchronized.
- [ ] Local logout or SAML Single Logout matches requirements; never claim all IdPs/SPs logged out when only the SP session was cleared.
- [ ] Fresh authentication/step-up is designed for sensitive actions using trusted `AuthnInstant` and assurance levels.
- [ ] Tested boundary conditions for `NotBefore`/`NotOnOrAfter`, idle, absolute, IdP expiry, `ForceAuthn`, session cookies, and revocation.
- [ ] Raw SAML/XML, session IDs, SAML private keys, and sensitive data are never logged.
- [ ] Operations docs specify **who owns each "clock"**, IdP outage contingencies, and UX states when re-login is needed.

**Learning summary:** **Assertion validity** governs evidence acceptance at the ACS; **SP session validity** governs whether subsequent HTTP requests count as logged in; **IdP session validity** governs whether the IdP can issue new assertions without forcing user re-authentication. These clocks are **independent by default**. Synchronizing them requires explicit verification policies, absolute session caps, reauthentication, revocation, or SAML Single Logout.

## 21. References

- [Spring Security – Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContextRepository, SessionCreationPolicy, session timeouts, session fixation, explicit save.
- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAMLResponse validation, Assertion Conditions, and Authentication.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response/assertion validators and Authentication conversion.
- [Spring Security – SAML2 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): AuthnRequest, SAML login flow, session correlation.
- [Spring Security – SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated logout and session state.
- [Spring Session – Boot/Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): storing shared HttpSessions across instances.
- [OASIS – SAML 2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Conditions, SubjectConfirmationData, AuthnStatement, SessionNotOnOrAfter, AuthnInstant.
- [OASIS – SAML 2.0 Profiles Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO Profile, bearer SubjectConfirmation rules.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): idle/absolute timeouts, fixation, cookies, and session lifecycles.
