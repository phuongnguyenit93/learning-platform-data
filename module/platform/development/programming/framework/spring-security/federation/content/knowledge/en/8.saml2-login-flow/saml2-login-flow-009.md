# Saving SecurityContext and Creating an Application Session After Successful SAML2 Authentication

**Module:** Spring Security – federation  
**Parent topic:** SAML2 login flow  
**Platform:** Spring Boot 3.x, Spring Security 6.x, Servlet/MVC, Java 17+.

## 1. Big Picture

After the user logs in at the **Identity Provider (IdP)**, the browser sends **`SAMLResponse`** to the **Service Provider (SP)**. Spring Security must verify `SAMLResponse`, establish a trusted **`Authentication`**, and persist the authenticated state so subsequent requests do not repeat the entire SAML flow.

Three related yet completely distinct concepts exist:

- **SecurityContext:** Spring Security object holding **`Authentication`**, including principal and authorities. It describes the security state used by the current request.
- **SecurityContextHolder:** access point to `SecurityContext` on the thread handling the request (using `ThreadLocal` by default). It is **not a multi-request session persistence mechanism**.
- **HttpSession + SecurityContextRepository:** where the SP stores `SecurityContext` across HTTP requests. The browser carries a session identifier cookie (**JSESSIONID** or **SESSION** depending on config), while the actual authentication data lives server-side.

Additionally, the IdP has its own **SSO session**. The IdP session and SP application session are not the same session; they can expire or be logged out at different times.

**Desired outcome:** On the first visit to a login-protected page, the user is routed to the IdP; after a valid `SAMLResponse`, the SP saves `Authentication` into `SecurityContext`; the browser returns with the SP session cookie and is recognized on subsequent requests. Successful authentication alone **does not automatically grant** all business roles: the SP still enforces authorization.

## 2. Components in Spring Security

| Component | Responsibility |
| --- | --- |
| **Saml2WebSsoAuthenticationRequestFilter** | Creates and sends `AuthnRequest` to start SAML2 browser SSO. |
| **Saml2AuthenticationRequestRepository** | Stores `AuthnRequest` and correlation info until `SAMLResponse` returns; uses `HttpSession` by default. |
| **Saml2WebSsoAuthenticationFilter** | Receives `SAMLResponse` at the ACS endpoint and runs the authentication flow. |
| **AuthenticationManager / SAML provider** | Verifies Response/Assertion against registered IdP policies; creates authenticated `Authentication` if successful. |
| **Saml2Authentication** | `Authentication` representing a successful SAML login; principal is typically `Saml2AuthenticatedPrincipal`. |
| **SecurityContext / SecurityContextHolder** | Context holding `Authentication` and where the current request reads it. |
| **SecurityContextRepository** | Abstraction that loads/saves context so the next request restores authentication. |
| **HttpSessionSecurityContextRepository** | Stores context inside the SP's `HttpSession`. |
| **RequestAttributeSecurityContextRepository** | Holds context for dispatches within the same request; does not replace cross-request persistence. |
| **DelegatingSecurityContextRepository** | Combines multiple repositories; common defaults include request attribute and `HttpSession`. |
| **SecurityContextHolderFilter** | In Spring Security 6, loads `SecurityContext` from the repository for the request without auto-saving changes at request end. |
| **SessionAuthenticationStrategy** | Applies login-time policies, such as rotating the session ID to defend against session fixation. |
| **AuthenticationSuccessHandler** | Redirects or writes a response upon successful authentication; typically restores the user's originally requested URL. |
| **LogoutHandler** | Clears authentication/session state upon logout per configuration. |

Spring Security SAML2 provides these components out of the box. Normal applications **do not manually decode `SAMLResponse`**, craft fake `Authentication`s, or call `HttpSession.setAttribute` with custom keys to "remember the user".

## 3. Flow from HTTP Request to Login Session

~~~text
Browser                      Spring Security SP                   SAML IdP
   |                                |                                 |
   | GET /profile                   |                                 |
   |------------------------------->| no Authentication               |
   |<-------------------------------| redirect to start login         |
   | GET /saml2/authenticate/company|                                 |
   |------------------------------->| creates AuthnRequest            |
   |                                | saves request correlation       |
   |<-------------------------------| sends browser to IdP ---------->|
   |                                |                                 | login
   | POST /login/saml2/sso/company  |<--------------------------------|
   |------------------------------->| SAMLResponse + RelayState       |
   |                                | verifies Response/Assertion     |
   |                                | Authentication succeeds         |
   |                                | SessionAuthenticationStrategy   |
   |                                | SecurityContextHolder.set       |
   |                                | Repository.saveContext          |
   |<-------------------------------| redirect + session cookie       |
   |                                |                                 |
   | GET /profile + cookie          |                                 |
   |------------------------------->| Repository.loadContext          |
   |                                | Authorization checks permissions|
   |<-------------------------------| 200 (if authorized)             |
~~~

This diagram shows the **conceptual sequence**, omitting some intermediate filters. Login may conclude by redirecting to the previously requested page or a default page per the success handler.

### 3.1. Before SAMLResponse Arrives

When an unauthenticated browser hits a protected page, **`SecurityFilterChain`** evaluates the request. **`ExceptionTranslationFilter`** and **`AuthenticationEntryPoint`** initiate SAML login. The common **`/saml2/authenticate/{registrationId}`** endpoint builds `AuthnRequest` and sends the browser to the IdP.

**`HttpSession` may already exist before login** to store **`AuthnRequest`** saved by **`HttpSessionSaml2AuthenticationRequestRepository`**, CSRF tokens, or `SavedRequest` (the URL requested before SSO). Having an `HttpSession` **does not mean** the user is authenticated.

By retaining `AuthnRequest` on the SP side, the system can verify **`InResponseTo`** and related metadata when the IdP replies. Never pull `RelayState` or request IDs from the client and trust them without session binding and anti-replay protection.

### 3.2. IdP Returns SAMLResponse

The browser POSTs to the **Assertion Consumer Service (ACS)**, typically **`/login/saml2/sso/{registrationId}`**. **`Saml2WebSsoAuthenticationFilter`** extracts response data, resolves the registration, and calls `AuthenticationManager`. The SAML2/OpenSAML provider checks:

1. Response/Assertion signature using a trusted IdP certificate.
2. Issuer matching the IdP in the registered `RelyingPartyRegistration`.
3. `AudienceRestriction` targeting the exact SP entityID.
4. Recipient/Destination targeting a valid ACS.
5. `Conditions`, `NotBefore`, `NotOnOrAfter`, and configured clock skew.
6. `InResponseTo`/request correlation with `AuthnRequest` in SP-initiated flows, plus replay protection.
7. `NameID`, `SubjectConfirmation`, and decryption requirements if applicable.

**Only after passing validation** is a trusted `Authentication` created. Never treat an XML parser or Base64 decoding as proof of login.

### 3.3. When Authentication Succeeds

In the standard flow:

- **`SessionAuthenticationStrategy`** handles the new login event, including session fixation protection.
- Spring Security establishes a **`SecurityContext`** holding `Authentication`, typically **`Saml2Authentication`** with `Saml2AuthenticatedPrincipal`.
- Spring persists the context via the appropriate **`SecurityContextRepository`** so future requests can restore it.
- **`AuthenticationSuccessHandler`** responds; by default usually redirecting the user back to `SavedRequest` or a fallback page.
- The browser retains the SP's session cookie and sends it back on subsequent requests to the SP.

**Note:** Saying "create a session after authentication" can mislead people into thinking `HttpSession` is only created at the callback. In reality, a pre-login session may already exist; Spring typically **rotates the session ID upon successful authentication**, and from that point forward the session holds the authenticated user's `SecurityContext`.

### 3.4. Subsequent Requests

On a post-login `GET /profile`, the Servlet container or Spring Session looks up `HttpSession` using the cookie. **`SecurityContextHolderFilter`** reads the context from the repository; **`SecurityContextHolder`** lets `AuthorizationFilter`/controllers access `Authentication` during the request. Application code can inject **`Authentication`** or **`@AuthenticationPrincipal`**.

There is no need to call the IdP or attach `SAMLResponse` on every HTTP request. When the request finishes, the thread's holder is cleared, while the context persisted in the session/repository remains until expiration or logout.

## 4. How SecurityContext Is Saved in Spring Security 6

### 4.1. SecurityContextHolder Only Holds Per-Request State

Example reading the context inside a controller/service within the security filter chain:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    String name = authentication.getName();
}
~~~

This is a **snippet**, not a standalone Java class. It requires importing **`org.springframework.security.core.Authentication`** and **`org.springframework.security.core.context.SecurityContextHolder`**.

The next request may run on a different thread or application instance. Therefore, never store `SecurityContext` in a **`static`** variable or key it by thread ID. The repository is the persistence layer.

### 4.2. Which Repository Holds the Context?

Spring Security 6 configurations typically use **`DelegatingSecurityContextRepository`** combining:

- **`RequestAttributeSecurityContextRepository`:** stores in request attributes so dispatches within the same HTTP request see the context.
- **`HttpSessionSecurityContextRepository`:** stores the context in `HttpSession`, allowing new requests to restore `Authentication`.

Actual sequence:

~~~text
Verified Authentication
        |
SecurityContextHolder (request)
        |
SecurityContextRepository.saveContext(context, request, response)
        |
        +--> RequestAttributeSecurityContextRepository
        |
        +--> HttpSessionSecurityContextRepository
                         |
                         v
                      HttpSession
                         |
             session cookie carrying session ID
                         |
                    Next Request
                         |
SecurityContextRepository.loadDeferredContext / loadContext
                         |
SecurityContextHolder + Authorization
~~~

The exact load method name depends on implementation API/version; the main idea is **loading from the repository on new requests**. Cookies do not contain the entire `SecurityContext`.

### 4.3. Spring 5 vs. Spring 6 Differ on Explicit Save

In classic Spring Security 5 defaults, **`SecurityContextPersistenceFilter`** could automatically save context mutations before the request/response ended.

In Spring Security 6, the default setup uses **`SecurityContextHolderFilter`** with **`requireExplicitSave`**: the filter loads context yet **does not automatically write every change back to the repository**. Consequently, custom code wishing to persist `Authentication` across requests must call **`SecurityContextRepository.saveContext(...)`** explicitly.

**This is not a reason to call `saveContext` manually after every SAML login.** When using **`saml2Login()`** and standard authentication filters, Spring Security already handles saving context in the success flow. Manual saving is only needed if your application **writes an alternative/custom flow** that modifies `Authentication` itself.

## 5. Spring Boot 3 and Java 17+ Example: SAML2 Login with SP Session

This sample is code for a Spring Boot/Maven project with Java 17+ and Spring Security 6.x. You need a **real IdP**, trusted XML metadata, and SP entityID/ACS registered at the IdP before attempting login. `example.org` domains are illustrative only.

### 5.1. Maven Dependencies

In the **`dependencies`** section of `pom.xml` using a compatible Spring Boot parent/BOM:

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

Spring SAML2 service provider uses OpenSAML; follow Spring Boot dependency management and avoid forcing conflicting OpenSAML versions.

### 5.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    metadata-location: classpath:metadata/company-idp.xml

server:
  servlet:
    session:
      timeout: 30m
~~~

Place real, approved IdP metadata at **`src/main/resources/metadata/company-idp.xml`**. **`timeout: 30m`** is normally the **idle timeout** of the SP's `HttpSession`, not the SAML Assertion lifetime or IdP session lifetime. If the IdP requires signed AuthnRequests or encrypted assertions, add SP credentials per IdP policy.

### 5.3. Main Class

**src/main/java/com/example/saml/SamlSessionApplication.java**

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSessionApplication.class, args);
    }
}
~~~

### 5.4. SecurityFilterChain, IdP Registration, and Session Policy

**src/main/java/com/example/saml/SamlSecurityConfig.java**

~~~java
package com.example.saml;

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
            @Value("${app.saml.metadata-location}") String metadataLocation) {

        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(metadataLocation)
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
            .logout(logout -> logout
                .logoutSuccessUrl("/"));

        return http.build();
    }
}
~~~

**Configuration analysis:**

- **`RelyingPartyRegistrations.fromMetadataLocation()`** reads IdP metadata to build the trusted issuer's SAML2 config. **`RelyingPartyRegistrationRepository`** supplies registrations to login filters.
- **`/login/saml2/sso/company`** is the SP's ACS, which must match where the IdP sends responses; SP entityID and ACS must be registered accurately at the IdP.
- **`saml2Login()`** wires authentication filters, provider, context, and success/failure processing.
- **`SessionCreationPolicy.IF_REQUIRED`** allows creating/maintaining `HttpSession` when SAML browser flows need it, rather than stateless mode.
- **`sessionFixation().changeSessionId()`** rotates the session ID on login to guard against session fixation. This is the default on Servlet 3.1+; written explicitly here for clarity.
- **`logoutSuccessUrl("/")`** redirects after local logout; it does not configure SAML Single Logout with the IdP.
- No manual `SecurityContextRepository` declaration: browser SSO uses appropriate default persistence in Spring Security.
- **Do not disable CSRF app-wide.** Standard SAML2 login handles the ACS appropriately; if customizing `loginProcessingUrl` or filter chains, ensure ACS matchers and CSRF align.

**Warning:** if running on **`http://localhost:8080`**, the sample callback configured as **`https://portal.example.org/`** will not route back to localhost. Use a test environment with registered URLs/ACS or update SP entityID/ACS identically on both SP and IdP—never disable Recipient/Destination validation to work around URL errors.

### 5.5. Controller Inspecting Post-Login Session State

**src/main/java/com/example/saml/SessionController.java**

~~~java
package com.example.saml;

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
        return "SAML SP session ready";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(
            Authentication authentication,
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal,
            HttpServletRequest request) {

        HttpSession existing = request.getSession(false);

        return Map.of(
            "authenticated", String.valueOf(authentication.isAuthenticated()),
            "name", principal.getName(),
            "registrationId", principal.getRelyingPartyRegistrationId(),
            "sessionPresent", String.valueOf(existing != null)
        );
    }
}
~~~

**Why `getSession(false)`?** It does not auto-create an `HttpSession`. Calling default `request.getSession()` inside a session check could create a brand-new session, falsely leading you to conclude "a session already existed and login succeeded".

In an app using only SAML2 login, the principal at `/me` post-auth is typically **`Saml2AuthenticatedPrincipal`**. If also supporting form login, OAuth2, or Bearer tokens, the controller must handle each principal type rather than casting every `Authentication` to SAML.

**Never output session IDs, raw `SAMLResponse`, cookies, sensitive NameIDs, or excess SAML attributes in production responses/logs.** The sample response is solely for learning flow inspection.

### 5.6. Running and Testing

In a valid Maven Spring Boot project:

~~~bash
mvn spring-boot:run
~~~

Once started cleanly, query the public endpoint:

~~~bash
curl -i http://localhost:8080/
~~~

Controller response body:

~~~text
SAML SP session ready
~~~

To test real SAML2, open the **registered SP URL** in a browser, visit **`/me`**, complete login at the IdP, and let the IdP send `SAMLResponse` to the ACS. Observe:

1. Before `Authentication` exists, the browser is guided into the SAML login flow.
2. After login, `/me` returns **`authenticated=true`**, **`sessionPresent=true`**, along with the actual subject and `registrationId`.
3. Refresh `/me` multiple times while the session is valid: no need to re-send `SAMLResponse` on every request.
4. Open a different browser or clear SP cookies: the SP has no prior `Authentication`; if the IdP still has an SSO session, re-login may be fast.
5. After a valid local logout, the SP drops its session; revisiting a protected page triggers a fresh SP SAML login round-trip.

Exact JSON varies by IdP/user and system policy. If IdP metadata/ACS is wrong or the IdP has not registered the SP, login will not complete; never claim session persistence works based on a mock example alone.

## 6. Manual saveContext: When a Custom Flow Mutates Authentication

This commonly causes bugs when upgrading Spring Security 5 to 6. A custom filter/controller might do:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
~~~

This snippet **only sets the context for the current request**. Under Spring Security 6 defaults, to persist across requests you must add:

~~~java
securityContextRepository.saveContext(context, request, response);
~~~

This code is a **snippet**; variables must come from a trusted authentication flow. **`verifiedAuthentication`** must be the result of `AuthenticationManager`/validators that fully verified SAML—never constructed from browser input and manually flagged `authenticated=true`.

Helper class example (solely for verified custom flows, **unnecessary with standard `saml2Login()`**):

~~~java
package com.example.saml;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;

public final class VerifiedSessionWriter {

    private final SecurityContextRepository repository;

    public VerifiedSessionWriter(SecurityContextRepository repository) {
        this.repository = repository;
    }

    public void persist(
            Authentication verified,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (verified == null || !verified.isAuthenticated()) {
            throw new IllegalArgumentException(
                "Authentication must already be verified");
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);
        repository.saveContext(context, request, response);
    }
}
~~~

This class compiles in a project with Spring Security and Jakarta Servlet dependencies; it is **not** a SAML response validator. The repository instance must match the repository the filter chain uses to restore context on the next request. Saving to one repository and loading from another makes sessions "disappear" with no compile error.

Save the context **before the response commits**, because `Set-Cookie`/redirects may fail to modify headers once committed. In custom flows, also enforce session-fixation policy, correlation, CSRF, and failure handling yourself; standard **`saml2Login()`** is usually the safer choice.

## 7. Pre- and Post-Login Sessions: Session Fixation

**Session fixation** is an attack where an adversary tricks a victim into authenticating under a session ID already known to the attacker.

Correct sequence:

~~~text
Anonymous browser -> HttpSession ID = S1
                |
          AuthnRequest saved in S1
                |
          Valid SAMLResponse
                |
         SessionAuthenticationStrategy
                |
       HttpServletRequest.changeSessionId()
                |
          Authenticated session ID = S2
                |
       SecurityContext persisted
~~~

On Servlet 3.1+, **`changeSessionId`** is the default strategy when session fixation protection is active. It rotates the ID while keeping necessary session attributes. Alternatives are **`newSession`** or **`migrateSession`**; never use **`none`** without a verified alternative defense.

**How to check:** if a session existed before login, compare the ID before/after in DevTools in a test environment; the ID should change per configuration. Never disclose session IDs in logs, issue trackers, or screenshots.

## 8. Session Cookies and SAML HTTP-POST Callbacks

SP cookies must be sent by the browser on post-login requests. Settings to review:

- **Secure:** transmit cookies only over HTTPS.
- **HttpOnly:** JavaScript on the page cannot read the cookie.
- **Domain/Path:** match the application's hostname/path behind any reverse proxy.
- **SameSite:** especially affects `SAMLResponse` POSTs from IdP to ACS.

Many IdPs use a **cross-site HTTP POST** for the browser to deliver `SAMLResponse`. If the SP session cookie uses **`SameSite=Lax`** or **`Strict`**, the browser may withhold the cookie on the cross-site POST. The SP loses the `HttpSession` holding `AuthnRequest`, causing request correlation errors or login loops.

If the actual flow requires cookies on cross-site POSTs, **`SameSite=None; Secure`** over HTTPS may be needed. Production example:

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

**Do not apply this mechanically to HTTP localhost**; `Secure` cookies require HTTPS in real environments and behave differently across browsers/localhost. Inspect real ACS requests in DevTools, Servlet/Spring Session cookie policies, and reverse proxies.

**`SameSite=None` is not a CSRF exemption:** business POST/PUT/DELETE endpoints using session cookies still require CSRF protection. Only the ACS callback handled and verified by Spring SAML2 per SAML profile gets the targeted exemption. Never disable CSRF app-wide to fix a callback error.

## 9. Timeouts and IdP Session vs. SP Session

| Component | Who Manages It? | Auto-Destroys SP SecurityContext? |
| --- | --- | --- |
| **SP HttpSession idle timeout** | SP / Servlet / Spring Session | Yes—if the session expires, old `Authentication` cannot be restored |
| **Internal absolute timeout** | SP policy if explicitly enforced | Can proactively force reauthentication; not automatic from idle timeout alone |
| **IdP SSO session timeout** | IdP | Does not automatically destroy SP `HttpSession` without a linked mechanism |
| **SAML Assertion Conditions.NotOnOrAfter** | IdP/Assertion validator | Condition for accepting the assertion at login; not the default `HttpSession` lifetime |
| **AuthnStatement.SessionNotOnOrAfter** | IdP when supplied | Can be used in SP session policy if explicitly implemented |
| **SAML Single Logout** | SP + IdP participating together | Can coordinate session termination if both configure SLO properly |

A SAML assertion valid for 5 minutes can establish an SP session with a 30-minute idle timeout. That is not automatically a bug: **assertion lifetime** and **application session lifetime** serve different goals. For sensitive operations, enforce absolute lifetimes, step-up auth, or IdP reauthentication.

If the SP session expires while the IdP still has an SSO session, the browser may complete a fresh SAML login round-trip almost silently without re-entering a password; the SP must still validate the new `SAMLResponse`.

## 10. Local Logout vs. SAML Single Logout

In standard config, **`POST /logout`** with a valid CSRF token invokes Spring Security's logout handlers, typically:

- invalidating the SP's `HttpSession`;
- clearing `Authentication` from `SecurityContextHolder`;
- removing context from the repository per configuration;
- redirecting to the logout success URL.

**`GET /logout`** normally renders a confirmation page when CSRF is enabled. Never call GET expecting logout to have definitely occurred.

**Local logout does not mean the IdP logged out.** When the user revisits the SP, the IdP may still hold an SSO session and issue a new `SAMLResponse`. For federated logout, configure **`saml2Logout()`** alongside `SingleLogoutService`, signing credentials, endpoints, request/response verification policies, and IdP support. Spring Security supports RP-initiated and AP-initiated SAML Single Logout; that is a separate topic from merely clearing local `HttpSession`.

## 11. Running Multiple Nodes: Sharing AuthnRequest and SecurityContext

In a single-node app, `HttpSession` usually resides in the servlet container's memory. When a load balancer distributes requests across multiple nodes:

- `AuthnRequest` is saved on node A, while `SAMLResponse` POSTs to node B: B cannot find the original request to verify `InResponseTo`.
- `SAMLResponse` is verified on node A and `SecurityContext` is saved in session A, yet `/me` hits node B: B knows nothing of the authenticated session.
- Sticky sessions can help, yet do not fully solve node replacement or failover.

You can use **Spring Session** with Redis/DB as a shared session store so **`HttpSession`** is readable across nodes. With Spring Boot, Redis dependency via BOM:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Approved Redis address example:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example.org
      port: 6379
server:
  servlet:
    session:
      timeout: 30m
~~~

Spring Session integrates via a Servlet Filter to back `HttpSession` with the shared store; the cookie may be named **SESSION**. Spring Security continues using `SecurityContextRepository` to save context into that logical session.

When deploying, check object/session serialization, matching registration/metadata config across nodes, cookie domain/path, Redis TLS/ACLs, expiration, monitoring, and data protection policies. **Never expose the session store publicly on the Internet.**

**Two repositories to keep distinct:** **`HttpSessionSaml2AuthenticationRequestRepository`** saves `AuthnRequest` in the session before ACS; **`HttpSessionSecurityContextRepository`** saves `SecurityContext` post-authentication. Multi-node systems need both states available on whichever node handles the request.

## 12. Customizing AuthenticationSuccessHandler Without Losing the Session

Some apps want to redirect to `/dashboard` or write audit records after SAML2 login. You do not need to re-save `SecurityContext` manually just to change navigation.

Example using `SavedRequestAwareAuthenticationSuccessHandler` to preserve the original URL:

~~~java
.saml2Login(saml -> {
    SavedRequestAwareAuthenticationSuccessHandler delegate =
        new SavedRequestAwareAuthenticationSuccessHandler();
    delegate.setDefaultTargetUrl("/me");

    saml.successHandler((request, response, authentication) -> {
        // Log only minimal audit info, never SAMLResponse/cookies.
        delegate.onAuthenticationSuccess(request, response, authentication);
    });
})
~~~

This is a **fragment inside `SecurityFilterChain`**, requiring import of **`org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler`**. It replaces **`saml2Login(Customizer.withDefaults())`** in the example—do not place both side by side. If a `SavedRequest` exists, the delegate prioritizes the requested URL; **`/me`** is the fallback.

The success handler must handle the response properly and never write raw `SAMLResponse` into the session. In custom flows, committing the response too early before context is saved breaks cookies/redirects. With standard Spring flows, authentication and context persistence are handled by the filter before the success handler finishes.

## 13. Common Errors and Locating the Right Layer

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| SAML login succeeds yet refreshing prompts login again | Cookie withheld, `SecurityContextRepository` didn't save/load, session expired | `Set-Cookie`, cookie on next request, repository, and session timeout |
| ACS reports missing original AuthnRequest | `SameSite` cookie blocked, node switch, session lost before callback | Network ACS POST, `HttpSessionSaml2AuthenticationRequestRepository`, load balancer |
| Custom `setContext` only, vanishes on next request | Spring 6 explicit save omitted | Call `saveContext` on right repository; avoid manual flow if unneeded |
| 401/redirect after login despite valid `Authentication` at callback | No cross-request persistence or wrong filter chain | `SecurityContextHolderFilter`, repository, cookies, matchers |
| Session ID does not rotate after login despite prior session | Session fixation protection disabled, custom flow skips `SessionAuthenticationStrategy` | Check `changeSessionId` config and authentication filter |
| Refresh hitting node B loses session | Local `HttpSession` on node A | Spring Session or proper routing/session sharing |
| User authenticated yet `/admin` returns 403 | Missing authorities/roles | Role mapping and authorization policy; do not alter SAML validation |
| Logout followed immediately by silent re-login | IdP SSO session still active | Distinguish local logout from SAML SLO |
| `Secure` session cookie not sent during HTTP testing | Production cookie config in non-HTTPS dev | HTTPS test domain or proper dev config |
| SAML POST from IdP drops cookie | `SameSite=Lax`/`Strict` on cross-site POST | Inspect browser/ACS and use `SameSite=None; Secure` if needed |
| Redis session deserialization error after deploy | Incompatible object/session serializer | Check codec, versions, sensitive fields |
| Roles changed yet session retains old permissions | Authorities stored in `SecurityContext` not refreshed | Re-evaluate permissions or revoke session on policy change |

**Useful debug order:** check **SAMLResponse validation → success event → session fixation → saveContext → Set-Cookie → cookie on next request → load context → authorization**. If the user is authenticated yet lacks roles, that is an authorization error, not a session persistence error.

Enable `DEBUG` only in development environments:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Never log `SAMLResponse`, cookies, session IDs, private keys, or sensitive identifying attributes. Use correlation IDs and sanitized messages to observe the flow.

## 14. Practical Scenarios

### A. Does having an HttpSession before login mean authenticated?

**No.** `HttpSession` may only hold `AuthnRequest` or `SavedRequest`. Only a verified `Authentication` inside `SecurityContext` establishes authentication.

### B. A Spring 6 custom controller puts Authentication into SecurityContextHolder and redirects, yet the next request is anonymous?

**Because the holder does not persist across requests.** Custom flows must call `SecurityContextRepository.saveContext(context, request, response)` on the matching repository, alongside credential verification and session strategy. Standard SAML2 login already handles this.

### C. IdP Assertion is valid for only 5 minutes, yet `/me` stays authenticated 20 minutes later?

**That can be completely valid under SP policy.** `NotOnOrAfter` bounds assertion acceptance at login time, not `HttpSession` expiration by default. Design idle/absolute session timeouts and reauthentication per business needs.

### D. IdP SSO session remains active after `POST /logout` at the SP?

**Normal for local-only logout.** The SP session was cleared; the IdP can still issue a new `SAMLResponse`. True SLO is required to coordinate federated logout.

### E. ACS hits node B while AuthnRequest is on node A?

**Correlation can fail.** Share `HttpSession` or a trusted request-correlation repository across nodes while keeping anti-replay and request/session binding.

### F. If only SAML2 login is needed, should we set `SessionCreationPolicy.STATELESS` to save RAM?

**Do not apply mechanically.** `STATELESS` typically prevents using `HttpSession` for `SecurityContext`; standard browser SAML2 relies on session/persistence and request correlation. Stateless operation requires a different architecture providing equivalent security.

### G. `SameSite=Lax` cookie prevents `POST SAMLResponse` from carrying the session ID?

**Inspect the cross-site POST in DevTools.** You may need `SameSite=None; Secure` over HTTPS or a tightly designed alternative request repository, while still protecting business endpoints with CSRF.

### H. SAMLResponse validates cleanly, yet `/admin` returns 403?

**Authentication persistence may still be working fine.** Fix role/permission mapping. Authentication and authorization are two separate steps.

## 15. Deployment and QA Checklist

- [ ] `SAMLResponse` flows through **`Saml2WebSsoAuthenticationFilter`** and trusted provider; signature, issuer, audience, recipient, time, and correlation are verified.
- [ ] `SecurityFilterChain` enables **`saml2Login()`**, and ACS URL matches IdP and `registrationId`.
- [ ] SP persists `SecurityContext` via `SecurityContextRepository`/`HttpSession` across requests.
- [ ] Team understands **`SecurityContextHolder`** is per-request only; custom flows require explicit **`saveContext`** in Spring Security 6.
- [ ] Browser SAML2 chain uses an appropriate session policy; `STATELESS` is not enabled without an alternative design.
- [ ] Session fixation protection uses **`changeSessionId`** or an equivalent strategy.
- [ ] Cookies set **`Secure`**, **`HttpOnly`**, proper Domain/Path; **`SameSite`** tested with ACS POST.
- [ ] CSRF exemptions cover only required SAML endpoints; state-changing app routes remain protected.
- [ ] Idle timeouts, optional absolute lifetimes, permission revocation, and reauthentication triggers are defined.
- [ ] Team distinguishes SAML Assertion lifetime, IdP SSO session, SP `HttpSession`, local logout, and SAML SLO.
- [ ] Multi-node setups share `AuthnRequest` and `SecurityContext` properly; serialization and session store security verified.
- [ ] `SAMLResponse`, tokens/cookies/session IDs, and sensitive data are kept out of logs.
- [ ] Tested login, page reload, fresh browser, session expiration, logout, missing roles, blocked cookies, cross-node callbacks, and failover.

**Key takeaway:** **Verified `SAMLResponse` → `Authentication` → `SecurityContext` → `SecurityContextRepository` → `HttpSession` → session cookie → `SecurityContext` restored on subsequent requests.** SAML2 login does not make every page accessible; roles and authorization policies must still be evaluated at the SP.

## 16. Official Reference Documentation

- [Spring Security 6.5 – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): handling AuthnRequest/Response and Authentication.
- [Spring Security 6.5 – SAML2 Authentication Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html): `HttpSessionSaml2AuthenticationRequestRepository` and request correlation.
- [Spring Security 6.5 – Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, `requireExplicitSave`, `SessionCreationPolicy`, session fixation, and timeouts.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): authentication filter, `SecurityContextHolder`, success handler.
- [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): local logout and `SecurityContextLogoutHandler`.
- [Spring Security 6.5 – SAML Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html): RP/AP-initiated SLO.
- [Spring Session – Spring Boot Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared `HttpSession` storage.
