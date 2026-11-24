# Distinguishing Application Logout, CAS Logout, and Single Sign-Out

**Module:** Spring Security – federation  
**Parent topic:** CAS Logout  
**Applies to:** CAS Protocol with Apereo CAS Server/Java CAS Client, Spring Security 6.x, Spring Boot 3.x, Java 17+, Servlet applications.

## 1. Three logout types do not have the same scope

CAS provides **Single Sign-On (SSO)**: the user authenticates at the CAS Server and receives a Service Ticket (**ST**) to enter one or more applications. However, after the ST is verified, each application typically creates its **own HttpSession**, so logging out has at least three meanings:

1. **Application logout (local/application logout):** portal clears the SecurityContext and HttpSession **of portal**, without directly touching the CAS session or other applications.
2. **CAS logout:** the CAS Server revokes the Ticket-Granting Ticket (**TGT**) and central login state, without directly having the authority to delete the HttpSession inside each application's JVM.
3. **Single Sign-Out (SLO):** the CAS Server sends **logout notifications** to the applications that participated in the SSO session; each CAS client attempts to locate and destroy its **corresponding local session**.

| Action | CAS TGT/SSO | Portal HttpSession | Reports HttpSession |
| --- | --- | --- | --- |
| Local logout at portal | May remain | **Ended** | May remain |
| CAS logout, no SLO | **Ended** | May remain | May remain |
| CAS logout + full SLO success | **Ended** | **Ended** | **Ended** |
| CAS logout + SLO failure at reports | **Ended** | Ended if callback succeeds | **May remain** |

**Most important point:** a page showing "logged out" can only assert the scope that the system **actually revoked**. CAS SLO is described by Apereo as **best effort**; network, browser, configuration, or session store issues can cause some applications to miss the notification.

## 2. CAS TGT/TGC, Service Ticket, and application sessions

~~~text
Browser
  +-- TGC cookie for domain sso.example.org
  |      -> CAS Server -> TGT (SSO session)
  |
  +-- Cookie portal.example.org
  |      -> Portal HttpSession -> SecurityContext
  |
  +-- Cookie reports.example.org
         -> Reports HttpSession -> SecurityContext

CAS login may issue:
  ST-P (for portal only)
  ST-R (for reports only)
~~~

- **TGT (Ticket-Granting Ticket):** central SSO state managed by the CAS Server, with its own lifetime/revocation policy.
- **TGC (Ticket-Granting Cookie):** browser cookie referencing the TGT at CAS. This cookie is not an application cookie.
- **ST (Service Ticket):** an opaque, service-bound credential used for **a single verification attempt**. Portal sends the ST to CAS **/serviceValidate**, and upon successful validation creates a local Authentication.
- **SecurityContext/HttpSession:** login state managed by each Service Provider/CAS client, typically used by Spring Security for subsequent requests.
- **ST→HttpSession mapping:** a CAS client supporting SLO needs to associate the login ticket identifier with the local session so it can later destroy the right session upon receiving an SLO callback.

**An expired or already consumed ST does not automatically expire the local HttpSession.** It is evidence used at the login callback, not an access token that must be resent on every request. **An expired CAS TGT** also does not automatically notify every application immediately; an app may still continue using its stored SecurityContext.

## 3. Application logout in Spring Security

A local logout button typically sends **POST /logout** with a valid CSRF token. Spring Security 6 Servlet has **LogoutFilter**; standard LogoutHandlers handle:

1. Invalidating the local HttpSession.
2. Clearing the SecurityContext in SecurityContextHolder and SecurityContextRepository.
3. Cleaning up active remember-me credentials/CSRF tokens when appropriate.
4. Publishing a logout event and using LogoutSuccessHandler to redirect to the notification page.

Java DSL example:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/logged-out").permitAll()
        .anyRequest().authenticated())
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

This is a **fragment** that must be placed inside a complete **SecurityFilterChain**. It only ends the **local session** and does not call CAS **/logout**. If the user still has a valid TGC/TGT, when opening a protected page on portal, Spring Security will redirect the browser to CAS login, CAS can issue a **new ST**, and the user returns to portal **without entering a password**.

Example timeline:

~~~text
09:00  Browser logs in to CAS and portal.
09:10  Browser POST /logout at portal -> local session ends.
09:11  User GET /private at portal -> redirect to CAS /login.
09:11  CAS TGT is still active -> issues a new ST for portal.
09:11  Portal validates the new ST -> creates a new local HttpSession.
~~~

It is not the old ST being reused. If a user reports "I logged out and could still log right back in", check **whether the CAS TGT is still active** rather than immediately concluding SecurityContextLogoutHandler is broken.

### Local idle timeout is also independent

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
~~~

**30m** here is the Servlet HttpSession idle timeout at the application, **not** the TGT timeout, TGC cookie lifetime, or Service Ticket TTL. CAS is not the session manager for portal/reports; each side has its own idle/absolute/revocation policy.

## 4. CAS Server logout

Example URL:

~~~text
https://sso.example.org/cas/logout
~~~

Per the CAS Protocol, **/logout** ends the **CAS SSO session**, destroys/prevents reuse of the current TGT, and deletes or invalidates the associated TGC.

Once the CAS SSO session has ended, the next time the browser visits **CAS /login** it cannot reuse that TGT to obtain an ST as before; the user may have to re-authenticate according to CAS policy. However:

- Portal, if it already has a local HttpSession, may **still be logged in** if there is no SLO/revocation.
- Reports, if it already has a local HttpSession, may also **still be logged in**.
- Even when the browser has deleted the TGC, the portal/reports cookies are **independent cookies**.
- The CAS Server cannot directly call HttpSession.invalidate() inside another application's JVM.
- A CAS session on this machine does not necessarily mean all of the user's devices are logged out as well; an all-device logout policy is a separate problem.

CAS may allow post-logout redirection via the **service parameter** depending on version/configuration. Do not take an arbitrary return URL from the browser to redirect (open redirect); the target must be in the **allowlist/registered services** and redirection must be enabled on the CAS Server.

### CAS logout is not yet synonymous with Single Sign-Out

If portal only redirects the browser to CAS /logout while **reports has no SLO receiver**, the CAS TGT may have been revoked while the reports local session still allows access.

Therefore, "global logout" must be clearly defined in product requirements:

- End the **SSO session at CAS**?
- Destroy the **application sessions linked to that TGT**?
- Or destroy **all sessions across all devices**, including systems outside CAS?

Those three goals have different difficulty and scope. Do not write "logged out everywhere" in the UI just because of a single redirect to CAS /logout.

## 5. Single Sign-Out is the mechanism for coordinating local session revocation

When a CAS TGT is explicitly expired, CAS can send SLO notifications to the registered services the user accessed during the SSO session. Idle timeout cases may also trigger SLO depending on the CAS implementation/policy.

~~~text
Browser          CAS Server           Portal SP            Reports SP
   |                 |                    |                     |
   | /cas/logout     |                    |                     |
   |---------------->| Delete TGT/TGC     |                     |
   |                 |--- SLO callback -->|                     |
   |                 |                    | invalidate session  |
   |                 |------------------------------ SLO callback |
   |                 |                    |          invalidate  |
   |<----------------| logout page        |                     |
~~~

The arrow ordering is illustrative; CAS may send notifications asynchronously, and some callbacks may fail. **SLO is a notification, not an ACID transaction or a guarantee that every application succeeded.**

The CAS Server typically knows which services were logged in via the STs issued in the same SSO relationship. Each CAS client needs a way to map **ST identifier → local session**, and upon receiving the notification, invalidate the corresponding local HttpSession.

### Conditions for SLO to take effect

1. CAS Server enables SLO for the **CAS Protocol** and the specific service registration.
2. The service registry advertises a service URL or **logoutUrl** that the CAS Server can reach.
3. The application has **SingleSignOutFilter** or an equivalent CAS client receiver.
4. The CAS client has tracked the login ticket and stored its mapping to the local session.
5. The callback is delivered to the receiver over the right HTTP method/binding.
6. The receiver accepts/trusts the notification according to security policy.
7. The mapping still exists and points to the active local HttpSession.
8. With multiple nodes, the session and correlation mapping can be shared/routed properly.
9. The session is genuinely invalidated; subsequent browser requests no longer retain the prior SecurityContext.
10. Monitoring and safe fallback behavior are in place when SLO does not complete.

**Do not assume** every application that uses CAS for login supports SLO simply because the CAS Server enables it. Each service needs the appropriate client library/receiver and configuration.

## 6. Back-channel SLO: CAS Server sends an HTTP POST to the application

**Back-channel** means the CAS Server sends a **server-to-server** callback without waiting for the user's browser to carry the notification to each application.

~~~text
CAS Server
  |
  | POST to registered service URL or logoutUrl
  | form field logoutRequest = XML LogoutRequest
  v
SingleSignOutFilter at Portal
  |
  | parse SessionIndex (CAS ST identifier)
  | look up mapping from ticket ID to HttpSession
  v
HttpSession.invalidate()
  |
  +-- Subsequent browser requests no longer have the old Authentication.
~~~

Traditional CAS Protocol uses XML **shaped like a SAML 2.0 LogoutRequest**:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_cas_logout_example"
    Version="2.0"
    IssueInstant="2026-11-07T05:00:00Z">
  <saml:NameID>employee-847</saml:NameID>
  <samlp:SessionIndex>ST-portal-login-example</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

This is only a **structural illustration**, not a valid SLO request to send to a real application. CAS Protocol SLO may use **SessionIndex as the Service Ticket identifier**; the client looks up the ST→HttpSession mapping to destroy the session.

**SessionIndex is not JSESSIONID**. If a receiver simply calls **request.getSession(false)**, it will usually fail to find the browser session to destroy, because a back-channel request **from the CAS Server** typically does not carry the user's session cookie.

**Protocol distinction:** CAS LogoutRequest XML looks similar to SAML2, but **CAS Protocol** SLO is not automatically identical to **SAML 2.0 Web Browser Single Logout**. Do not use Spring Security **saml2Logout()** as a direct replacement for CAS client **SingleSignOutFilter**.

## 7. Front-channel SLO: notifications pass through the browser

Apereo CAS also has **front-channel** variants (e.g., AJAX/JSONP or iframe depending on server version/service policy). The browser on the CAS logout page is instructed to contact the applications' logout endpoints.

~~~text
CAS logout page in browser
    |
    +--> portal front-channel logout callback
    +--> reports front-channel logout callback
    +--> billing front-channel logout callback
~~~

**Do not assume Java CAS Client supports every front-channel variant.** Some approaches depend on the browser, cookie SameSite attributes, third-party cookie blocking policies, CORS/CSP, when the tab is closed, and whether the endpoint accepts GET/JSONP. You must check **CAS Server logoutType**, client configuration, network/browser behavior, and the corresponding protocol.

| Criterion | Back-channel | Front-channel |
| --- | --- | --- |
| Transport path | CAS Server → app server | Through the user's browser |
| Needs browser to stay on logout page? | Not a primary delivery condition | Often dependent |
| Carries user's cookies? | Not by default | Depends on cookie/browser policy |
| Delivery capability if browser leaves page | Possible, if CAS Server can still reach app | Usually reduced |
| Risks | App unreachable, timeout, wrong correlation/store | Blocked by browser, cross-site cookies, tab closed |
| Callback protection | Server-to-server trust, TLS, source controls | Request trust, browser security, token/correlation |
| Certainty level | Still **best effort** | Still **best effort** |

**Do not claim back-channel guarantees revoking every session.** It only reduces browser dependency; actually destroying the right HttpSession remains each application's responsibility.

## 8. How does the CAS SLO client map a Service Ticket to an HttpSession?

~~~text
At portal CAS login:
    GET /login/cas?ticket=ST-P
                |
                +--> CasAuthenticationFilter validates ST-P
                |
                +--> CAS SLO client stores:
                     ST-P -> portal HttpSession P-1

At CAS logout:
    POST logoutRequest
    SessionIndex = ST-P
                |
                +--> look up ST-P -> HttpSession P-1
                |
                +--> P-1.invalidate()
~~~

The CAS client does not need the user's full credentials to invalidate a session; it needs **a trustworthy correlation identifier**. Do not destroy all sessions by matching a username taken from unverified XML, especially in multi-tenant setups or when the same user is on multiple devices.

### 8.1. Why is a listener needed?

Apereo Java CAS Client provides **SingleSignOutHttpSessionListener**, which removes the session mapping when an HttpSession expires naturally or is destroyed, avoiding stale associations in memory. This listener runs inside the **Servlet application** and does not manage the CAS TGT.

### 8.2. Session fixation and session ID changes

Spring Security may call **changeSessionId** after authentication to prevent session fixation. You must test that the ST→session correlation still finds the **actual active session** after the session ID changes. Do not store a fixed JSESSIONID yourself without updating it when the session strategy rotates the ID.

### 8.3. Multiple nodes and shared session stores

Example:

~~~text
Browser CAS callback -> portal node A: ST-P mapping at A
CAS SLO callback     -> portal node B: B has no mapping
~~~

Adding **Spring Session Redis** shares HttpSessions, but **does not automatically turn every static map in the CAS client into a distributed map**. If the ST→session mapping lives inside JVM A, a callback hitting B may fail to find the session.

You must test and design for: a shared correlation store, SLO routing/event bus, session revocation checks, or a cluster-aware CAS client implementation. Sticky browser sessions may not help back-channel calls because the CAS Server callback carries no user cookies.

## 9. Spring Security 6: how is local logout configured?

Example Servlet SecurityFilterChain using CAS Protocol login and local logout. You can use the following **logout DSL** section on its own to add to an existing working CAS client chain:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/logged-out", "/error").permitAll()
        .anyRequest().authenticated())
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

**Note:** This is a fragment, not a standalone Spring Boot application. You need CAS login configured via **spring-security-cas** with **CasAuthenticationFilter**, **CasAuthenticationProvider**, and **TicketValidator**. **Local logout** only clears the HttpSession/SecurityContext and does not invoke CAS /logout without a subsequent handler or UI flow.

### 9.1. Redirecting to CAS logout after local logout

If the product goal is **clicking logout ends both local and CAS SSO**, replace the logout DSL above with:

~~~java
// casLogoutUrl comes from trusted server-side configuration,
// e.g., https://sso.example.org/cas/logout
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.sendRedirect(casLogoutUrl))
    .permitAll());
~~~

**Order:** Spring Security runs the local LogoutHandlers **first**, then **LogoutSuccessHandler** redirects the browser to the CAS logout URL. The CAS Server processes the TGT and may then send SLO notifications if enabled and supported by each client.

**Do not place two logoutSuccessHandlers in the same DSL** expecting both to execute. This is a **replacement pattern** for local-only logout. `casLogoutUrl` is a fixed HTTPS URL, not taken from an arbitrary query parameter or returnUrl. If the CAS redirect fails, the local session may already be gone while the TGT might not be revoked; the UI must explain this accurately.

### 9.2. Two logout choices in the UI

If the product wants two buttons:

~~~text
"Log out of this application"
  -> POST /logout with CSRF
  -> local session ends
  -> /logged-out (public page)
  -> CAS TGT may remain

"Log out of SSO"
  -> local logout with CSRF
  -> redirect to CAS /logout
  -> CAS TGT ends
  -> CAS SLO notifications to registered applications
~~~

These two buttons need **two explicitly configured flows** (either two Spring Security endpoints or a local logged-out page offering a safe CAS logout link), not a single default POST /logout that guesses the choice from the button label. Never create a GET /logout state-changing action without a CSRF/confirmation policy.

## 10. Spring Boot 3 + Java 17: minimal CAS login and local logout

This article focuses on **logout scope**. The Java code below is a CAS Protocol client configuration sufficient to show where **local logout** attaches, not a CAS Server. Integration testing requires a real HTTPS CAS Server, a proper service registry, user **demo** in CAS, TLS metadata/trust, and a **Jakarta Servlet CAS client** version compatible with Spring Boot 3.

### 10.1. Maven dependencies

In a project with a compatible Spring Boot parent/BOM:

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
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
~~~

The CAS client library must match **Jakarta Servlet** for Boot 3 and Spring Security 6; do not force an older dependency version without verifying compatibility.

### 10.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    logout-url: https://sso.example.org/cas/logout
    service-url: https://portal.example.org/login/cas

server:
  servlet:
    session:
      timeout: 30m
~~~

**service-url** must match the callback URL allowlisted by the CAS Server. The example.org domains are **illustrative**, not a live ready-to-use login service. **CAS logout-url** is not Spring Security's local **/logout**.

### 10.3. Main application

**src/main/java/com/example/cas/CasApplication.java**

~~~java
package com.example.cas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasApplication.class, args);
    }
}
~~~

### 10.4. Security configuration

**src/main/java/com/example/cas/CasSecurityConfig.java**

~~~java
package com.example.cas;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String url) {
        ServiceProperties p = new ServiceProperties();
        p.setService(url);
        p.setSendRenew(false);
        return p;
    }

    @Bean
    CasAuthenticationEntryPoint entryPoint(
            ServiceProperties serviceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {
        CasAuthenticationEntryPoint p =
            new CasAuthenticationEntryPoint();
        p.setLoginUrl(loginUrl);
        p.setServiceProperties(serviceProperties);
        return p;
    }

    @Bean
    UserDetailsService demoUsers() {
        return name -> {
            if (!"demo".equals(name)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Unknown local user");
            }
            // CAS authenticates the identity; the UserDetails password is not
            // used during Service Ticket validation.
            return User.withUsername(name)
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build();
        };
    }

    @Bean
    CasAuthenticationProvider casProvider(
            ServiceProperties serviceProperties,
            UserDetailsService demoUsers,
            @Value("${app.cas.server-base-url}") String casBaseUrl) {
        CasAuthenticationProvider p = new CasAuthenticationProvider();
        p.setServiceProperties(serviceProperties);
        p.setTicketValidator(
            new Cas20ServiceTicketValidator(casBaseUrl));
        p.setUserDetailsService(demoUsers);
        p.setKey("portal-cas-v1");
        return p;
    }

    @Bean
    SecurityFilterChain browser(
            HttpSecurity http,
            ServiceProperties serviceProperties,
            CasAuthenticationEntryPoint entryPoint,
            CasAuthenticationProvider casProvider) throws Exception {

        SecurityContextRepository repo =
            new HttpSessionSecurityContextRepository();

        // Only one CasAuthenticationFilter in SecurityFilterChain,
        // not a @Bean, to avoid extra auto-registration in the Servlet container.
        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setFilterProcessesUrl("/login/cas");
        filter.setServiceProperties(serviceProperties);
        filter.setAuthenticationManager(new ProviderManager(casProvider));
        filter.setSecurityContextRepository(repo);
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/logged-out", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(sc -> sc.securityContextRepository(repo))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/logged-out")
                .permitAll())
            .addFilterAt(
                filter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Key takeaways:**

- **CasAuthenticationFilter** verifies the CAS ST at the **/login/cas** callback; it is not a logout filter.
- **CasAuthenticationProvider** uses a CAS ticket validator for the CAS Protocol; do not manually parse/query the ST to construct an Authentication.
- **HttpSessionSecurityContextRepository** persists Authentication across subsequent requests after the CAS ST is validated.
- **.logout(...)** above specifies **application logout**, and does not automatically call CAS logout.
- **UserDetailsService** intentionally restricts to the demo user; production must verify local account enabled status, tenant/roles/grants, and never auto-grant access to every CAS subject.
- The CAS filter is instantiated with **new** inside SecurityFilterChain; do not register it a second time as a Servlet Filter bean.
- **Default CSRF protection** still protects POST /logout and state-changing application actions.

### 10.5. Controller and test run

**src/main/java/com/example/cas/CasController.java**

~~~java
package com.example.cas;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CasController {

    @GetMapping("/")
    public String home() {
        return "CAS logout scope demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/logged-out")
    public String loggedOut() {
        return "Local session ended. CAS SSO may remain active.";
    }
}
~~~

In a complete Maven project with a real CAS Server and JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Verify the public endpoint once the application starts:

~~~bash
curl -i http://localhost:8080/
~~~

Body per the controller:

~~~text
CAS logout scope demo
~~~

To test logout, log in to CAS via a real public HTTPS callback and then submit a form POST /logout with a CSRF token and browser session cookie. If the user is anything other than `demo`, local account policy rejects them even if CAS authenticates successfully. The sample cannot perform end-to-end login on its own because the example.org domain has no real CAS Server.

## 11. Adding SingleSignOutFilter and listener: a Servlet variant

Java CAS Client documentation describes **SingleSignOutFilter** and **SingleSignOutHttpSessionListener** for CAS Protocol SLO. Example of registering a **single filter** in the Servlet container (without simultaneously adding it again to SecurityFilterChain):

**src/main/java/com/example/cas/CasSloConfig.java**

~~~java
package com.example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> sloFilter() {
        FilterRegistrationBean<SingleSignOutFilter> b =
            new FilterRegistrationBean<>();
        b.setFilter(new SingleSignOutFilter());
        b.setName("casSingleSignOutFilter");
        b.addUrlPatterns("/*");
        // Runs before Spring Security; verify the actual order when deploying.
        b.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return b;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
    sloSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
~~~

**Important explanation:**

- **SingleSignOutFilter** is the CAS Java Client's SLO filter, not **CasAuthenticationFilter** which handles ST login.
- The SLO filter is registered **once** before the security chain in this variant, to track login tickets and handle CAS SLO callbacks.
- **SingleSignOutHttpSessionListener** cleans up the association when the local session ends.
- If you choose to add the SLO filter **inside the Spring Security chain** as in the Spring Security CAS XML example, you must **not** keep the Servlet filter registration above. Pick **only one** approach to avoid duplicate processing.
- Verify ordering relative to CharacterEncodingFilter, the CAS authentication filter, CSRF, and client version. The code is reference wiring only and does not replace interoperability testing.
- When using Spring Boot 3, **the CAS client must support Jakarta Servlet**; check actual dependencies if you encounter javax.servlet vs jakarta.servlet errors.
- This is not yet proof that the CAS Server has enabled SLO for the service; the server must have a valid registered service logoutType/channel/endpoint.

### SLO callback security warning

Traditional CAS Protocol SLO **must not be assumed by default to be fully signature-verified SAML2 logout XML**. An endpoint accepting POST **logoutRequest** from the Internet can become a target for **logout CSRF/DoS** if an attacker can forge messages to destroy sessions.

Measures to evaluate:

1. End-to-end HTTPS between the CAS Server and the application.
2. **mTLS or an authenticated channel at the gateway/ingress** when architecture permits.
3. Network allowlists and trusting forwarded headers only from controlled reverse proxies.
4. Binding the message/correlation ID to a tracked session.
5. Replay protection, invalid SessionIndex handling, parse error handling, and rate limiting.
6. Never allowing untrusted sources to destroy sessions solely by a self-declared NameID/username.
7. CSRF handling for **server-to-server SLO** must be separated from browser CSRF; **do not disable CSRF globally**.
8. Because the SLO filter runs **before** Spring Security in this variant, do not assume the inner SecurityFilterChain automatically protects it.

Specific validation/verification capabilities of SingleSignOutFilter depend on the CAS client version and configuration; test the threat model against the real system. In particular, never write a custom endpoint that accepts a SessionIndex string and destroys every session sharing the same username.

## 12. Runnable Java 17: simulating the independence of the three scopes

The standalone example below needs neither Spring nor a CAS Server. It clarifies the **logical state** of local logout, CAS logout, and full or partial SLO.

**File: CasLogoutScopeDemo.java**

~~~java
public final class CasLogoutScopeDemo {

    record Sessions(boolean casSso,
                    boolean portal,
                    boolean reports) { }

    static Sessions localPortalLogout(Sessions s) {
        return new Sessions(s.casSso(), false, s.reports());
    }

    static Sessions centralCasLogout(Sessions s) {
        return new Sessions(false, s.portal(), s.reports());
    }

    static Sessions successfulSlo(Sessions s) {
        return new Sessions(false, false, false);
    }

    static Sessions partialSlo(Sessions s) {
        return new Sessions(false, false, s.reports());
    }

    static Sessions reenterPortal(Sessions s) {
        if (!s.casSso()) {
            return s;
        }
        // CAS SSO is still active -> assume CAS issues a new ST.
        return new Sessions(true, true, s.reports());
    }

    static String state(Sessions s) {
        return "cas=" + s.casSso()
            + ",portal=" + s.portal()
            + ",reports=" + s.reports();
    }

    public static void main(String[] args) {
        Sessions active = new Sessions(true, true, true);
        Sessions localOnly = localPortalLogout(active);

        System.out.println("start=" + state(active));
        System.out.println("localOnly=" + state(localOnly));
        System.out.println(
            "localThenReenter=" + state(reenterPortal(localOnly)));
        System.out.println(
            "casOnly=" + state(centralCasLogout(active)));
        System.out.println(
            "sloSuccess=" + state(successfulSlo(active)));
        System.out.println(
            "sloPartial=" + state(partialSlo(active)));
    }
}
~~~

Run:

~~~bash
javac CasLogoutScopeDemo.java
java CasLogoutScopeDemo
~~~

**Deterministic stdout:**

~~~text
start=cas=true,portal=true,reports=true
localOnly=cas=true,portal=false,reports=true
localThenReenter=cas=true,portal=true,reports=true
casOnly=cas=false,portal=true,reports=true
sloSuccess=cas=false,portal=false,reports=false
sloPartial=cas=false,portal=false,reports=true
~~~

Explanation:

- **localOnly:** portal session ends, CAS and reports may remain.
- **localThenReenter:** CAS TGT remains, so the simulation allows a new ST to create a new portal session.
- **casOnly:** CAS TGT is destroyed, but local sessions do not automatically disappear.
- **sloSuccess:** CAS SSO and both local sessions end.
- **sloPartial:** the reports callback fails, so the reports session remains.

This is an **educational state machine**, performing no CAS XML parsing, network calls, or signature verification. In production, do not use a browser-submitted boolean to decide whether a session has been revoked.

## 13. Integration testing: three scenarios that must be separated

### 13.1. Local logout, TGT still active

**Given:** the browser logged in to portal/reports via CAS; the TGT is still valid.  
**When:** POST /logout at portal with a CSRF token.  
**Then:** portal HttpSession/SecurityContext is cleared; reports may remain; CAS TGT may remain. Upon reopening portal, CAS can issue a new ST without asking for a password.

Do not mistake a fresh login redirect for a failed local logout. Observe the **new session ID + new ST**, without printing raw tickets into logs.

### 13.2. CAS logout without an SLO receiver

**Given:** portal and reports have local sessions.  
**When:** the browser visits CAS /logout, but the applications do not support SLO.  
**Then:** the TGT expires; requests to portal/reports using local session cookies before expiration can still succeed.

Do not try to solve this by shortening the ST TTL. The ST was already used at login; local session lifecycle is a separate mechanism.

### 13.3. CAS logout with SLO

**Given:** CAS Server has SLO enabled, service registrations have proper channel/endpoints, and each app has an ST→HttpSession mapping and a trusted receiver.  
**When:** CAS /logout is triggered and callbacks are sent to portal/reports.  
**Then:** each receiver invalidates the right session; subsequent browser requests can no longer use the old SecurityContext.

If the reports callback times out, this is a **partial SLO outcome**. Record the failure and apply risk-mitigation measures; do not claim "all sessions were deleted".

## 14. Negative test suite, errors, and troubleshooting

| Test/error | Expected result or diagnosis |
| --- | --- |
| POST /logout without CSRF token | Rejected if CSRF is enabled |
| After local logout, user re-enters without password | TGT remains, CAS issues a new ST; check local session before and after |
| CAS logout page reports success, yet portal is still accessible | SLO is missing or portal session was not invalidated |
| SLO callback carries no browser cookie | Receiver uses ST→session mapping, does not guess with request.getSession() |
| SessionIndex differs from mapped ST | Do not accidentally destroy another session |
| Callback has a username matching another user | Do not delete all sessions by username alone |
| Spoofed callback from the Internet | Rejected by trust/network/message controls |
| Replayed callback | Do not accidentally destroy another user; handle idempotently/atomically per policy |
| CAS Server sends to wrong URL | Fix service registry logoutUrl/callback path |
| CAS Server cannot reach app | Check DNS, TLS, firewall, proxy, allowlist |
| SLO hits a different node than login node | Check shared ST→session mapping and session store |
| Spring Session Redis present, but CAS map is in-JVM | Logout still risks failing |
| SLO filter not placed before security chain | Check order/CSRF/matching and registration |
| SLO filter registered twice | Clean up duplicate Servlet/Security registrations |
| CAS SLO XML resembles SAML LogoutRequest | Do not confuse with SAML2 SP logout/LogoutResponse |
| Front-channel blocked by browser | Test SameSite/CSP/CORS/third-party cookies; consider back-channel |
| Browser tab closed during CAS logout | Do not assume front-channel completed |
| Local account disabled while session remains | Authorization/revocation policy must deny access |
| SLO applies to only one CAS SSO session | Do not automatically report all-device logout |
| Callback returns HTTP 200, yet local session remains usable | Must test an HTTP resource after the callback, not just status code |
| User-supplied global logout redirect URL | Block open redirect; use fixed URL/allowlist |
| CAS-independent API tokens remain valid | Must have separate token revocation; SLO does not revoke them |
| Raw ST/TGT/cookie appears in logs | Mask/sanitize queries and reduce PII logging |

### What to measure to verify real success

- CAS TGT revocation event (minimized ID, not raw TGT).
- SLO requests sent per registered service and channel type.
- SLO callbacks received/parsed and trust-checked.
- ST→HttpSession mapping found/not found.
- HttpSession actually invalidated on each app node.
- Whether post-logout HTTP requests are still accepted or rejected with redirect/401.
- Callback retries/timeouts/errors/partial failures.
- The distinction between CAS logout and **all-devices logout**.

**Do not store verbatim** ST, TGC, TGT, SessionIndex, JSESSIONID, or logout XML in APM/access logs. Use correlation IDs without secrets, enforce retention policies, and restrict viewer access.

## 15. Multi-pod SLO controls and compensating policies

CAS SLO is a useful layer, but should not be the **sole revocation control** for sensitive data. Compensating layers:

1. **SP idle timeout** suited to sensitivity; background polling can keep sessions alive, so consider **absolute lifetime**.
2. **Local account enabled/disabled** checked per policy on access; a disabled user must not retain access solely because a session cookie remains.
3. **Resource-level authorization** checking grants/tenant at action time, not just a role snapshot from login.
4. **Cluster-wide session invalidation** on SLO callback or admin revocation.
5. **SSO session duration** and requiring reauthentication/fresh auth for sensitive operations.
6. **Monitoring failures** when the CAS Server cannot deliver SLO to an SP.
7. **Fail closed** for sensitive actions if the local authorization source is unavailable.
8. Incident response runbook when users report "I logged out, yet my session in another app is still active".

Especially in multi-tenant environments, never arbitrarily destroy sessions for users sharing the same email/username across different tenants or CAS servers. Clearly identify the **CAS authority/TGT relationship + service ticket mapping + local session owner**.

## 16. Production checklist

- [ ] Product documentation clearly distinguishes **application logout, CAS logout, Single Sign-Out**.
- [ ] POST local logout has CSRF protection, invalidates HttpSession, and clears SecurityContext.
- [ ] CAS logout URL is server-side configured HTTPS, with no open redirect.
- [ ] Never infer TGT deletion solely from portal having logged out.
- [ ] Never infer local sessions were deleted solely because CAS /logout returned success.
- [ ] CAS Server service registry enables the right SLO channel/endpoint for each application.
- [ ] Each SLO-enabled application has **SingleSignOutFilter + SingleSignOutHttpSessionListener** or a tested equivalent.
- [ ] SingleSignOutFilter is registered **once** in the proper order; no mixing of Servlet and Security chain registrations.
- [ ] Back-channel SLO **does not depend on browser cookies**; reliable ST→HttpSession correlation mapping is in place.
- [ ] SessionIndex is not confused with JSESSIONID or username.
- [ ] Receiver does not trust logoutRequest from arbitrary sources; TLS/mTLS/network/replay protections match the architecture.
- [ ] Do not treat CAS Protocol SLO XML as a full SAML2 logout transaction without an actual SAML profile.
- [ ] Tested sessions across multiple nodes, sticky sessions, and shared mapping/store.
- [ ] Tested partial SLO, callback timeouts, browser close, and IdP/CAS outages.
- [ ] Tested local logout followed by SSO re-login while TGT remains active.
- [ ] Never report global SLO success without verifying downstream sessions.
- [ ] Account/permission revocation and idle/absolute timeouts exist as defense-in-depth layers.
- [ ] Logging out one TGT does not automatically apply to all devices unless a dedicated policy implements it.
- [ ] No raw tickets/cookies/SLO XML are logged; auditing uses appropriate correlation IDs.
- [ ] When deploying on Boot 3, verify the CAS client supports **Jakarta Servlet** and all APIs match the version.

**Conclusion:** **Application logout** ends one application's session; **CAS logout** ends the central SSO session; **Single Sign-Out** coordinates requesting participating applications to invalidate their own sessions. The three states are **independent by default**. Reliable cross-application logout requires a protocol-correct CAS SLO client, ST-to-session mapping, callback protection, cluster consistency, testing, and partial-failure handling.

## 17. References

- [Apereo CAS 8.0.x – Logout & Single Logout](https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html): application logout vs CAS logout, best-effort SLO, back-/front-channel, and service logoutType.
- [CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): /logout, Single Logout callback, Service Tickets, and TGT.
- [Spring Security – CAS Authentication and Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CAS SLO filter/listener and local vs central logout.
- [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): LogoutFilter, LogoutHandler, LogoutSuccessHandler, CSRF.
- [Apereo Java CAS Client README](https://github.com/apereo/java-cas-client/blob/master/README.md): SingleSignOutFilter, SingleSignOutHttpSessionListener, and registration order.
- [Spring Boot – Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): FilterRegistrationBean and ServletListenerRegistrationBean.
- [Spring Session – Redis Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared HttpSession; distributed CAS correlation mapping must be verified separately.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session expiration, logout, CSRF, revocation, and lifecycle.
