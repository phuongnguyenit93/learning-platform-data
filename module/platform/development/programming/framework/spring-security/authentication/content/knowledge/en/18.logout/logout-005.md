# Clearing Remember-Me and Long-Lived Login Credentials on Logout

> **Goal:** Design **logout** functionality in Spring Security so users are not automatically logged back in by a leftover remember-me cookie; while clearly understanding what must be deleted in the **browser**, what must be **revoked on the server**, the limits of single-device logout, and cases involving **refresh tokens, OAuth2/OIDC, multiple sessions, or persistent login data**. The focus is **Spring Boot 3.x, Spring Security 6.x, Servlet/MVC, Java 17+**.

## 1. Logout Is More Than Redirecting to the Login Page

An application using session cookies may still store multiple types of long-lived login evidence. For instance:

1. **JSESSIONID**: references the HTTP session holding `SecurityContext`.
2. **Remember-me cookie**: credential allowing Spring Security to automatically re-authenticate when no session exists.
3. **Persistent remember-me token**: **series/token** record in the database, used to verify the cookie and capable of surviving restarts.
4. **Access token / refresh token**: if the app uses OAuth2 or issues its own tokens, they may reside on the client, in a server-side token store, or in `OAuth2AuthorizedClientService`.
5. **Session at the Identity Provider (IdP)**: the user may still be logged in at the identity provider despite logging out of the application.
6. **Browser storage**: localStorage, sessionStorage, IndexedDB, caches, Service Workers, or frontend state, if the app stored login data there.

If you only execute:

~~~java
return "redirect:/login";
~~~

you have only changed where the browser is navigated. The old session may still be valid, the remember-me cookie may still be sent, and server tokens may not have been revoked. After the redirect, **RememberMeAuthenticationFilter** can automatically rebuild Authentication, making users think logout is broken.

**Invariant of secure logout:** once the operation completes, credentials within the logout scope requested by the user **cannot continue to restore an authenticated session**. There must be tests proving this by **reusing old cookies/tokens** after logout.

## 2. Matrix of What Must Be Cleared and Who Has Authority to Clear It

| Data | Where it lives | What logout must do | Notes |
| --- | --- | --- | --- |
| SecurityContext | SecurityContextHolder and repository | Clear Authentication, delete/save an empty context via the proper mechanism | Do not just set a variable in a controller |
| HTTP session | Servlet container / Spring Session | **Invalidate** the session or revoke its ID | Deleting cookies on the client is not enough |
| JSESSIONID | Browser | Send an expired cookie when appropriate; check Path/Domain | Server invalidation is the decisive measure |
| Remember-me cookie | Browser | Issue **Set-Cookie** expiring the cookie with exact name, Path, Domain | Client could still keep a copy if it ignores the header |
| Persistent remember-me token | Database / token repository | Revoke the corresponding record per policy | Must handle the null authentication case |
| Hash-based remember-me cookie | Browser and server-side signing formula | Expire cookie; revoking stolen copies requires changing password/hash or key/denylist policy | No default per-device record to delete |
| App-issued refresh token | Client + token-issuing system | Revoke/mark invalid server-side if supported | Deleting client-side without revoking still risks replay |
| OAuth2AuthorizedClient | Session, database, service/repository | Remove the authorized client/token stored in the app per architecture | Does not automatically revoke tokens at the Authorization Server |
| Session at OIDC IdP | Identity provider | If SSO logout is needed, run the IdP's logout flow | Local logout does not automatically log out of the IdP |
| Browser localStorage/IndexedDB | Application's browser origin | Frontend removes keys/datasets it manages | Server Set-Cookie does not arbitrarily wipe all storage |
| Password Manager | Browser or OS | Not within the app's arbitrary deletion authority | Do not promise deleting passwords saved by the user |

**Clearing on the client** stops the browser from sending the credential. **Revoking on the server** ensures even a stolen copy is no longer accepted. For logout to have security meaning, prioritize both places whenever a credential has server-side state.

## 3. What Does Spring Security's LogoutFilter Handle?

With standard Spring Security Servlet configuration, **LogoutFilter** handles the logout endpoint before the request reaches a controller, normally **POST /logout** when CSRF is enabled. **GET /logout** can display a confirmation page; a GET route should not be treated as a state-changing operation in an app with CSRF.

~~~text
Browser
  |
  | POST /logout
  | Cookie: JSESSIONID=...
  | Cookie: remember-me=...
  | valid CSRF token
  v
SecurityFilterChain
  |
  +-- CsrfFilter: reject if token is invalid/missing
  |
  +-- LogoutFilter
        |
        +-- SecurityContextLogoutHandler
        |     +-- invalidate HttpSession
        |     +-- clear Authentication / SecurityContextHolder
        |     +-- clear SecurityContextRepository
        |
        +-- RememberMeServices.logout(...)
        |     +-- expire remember-me cookie
        |     +-- if persistent and Authentication is present:
        |            removeUserTokens(username)
        |
        +-- CsrfLogoutHandler: delete stored CSRF token
        |
        +-- Additional LogoutHandlers if configured
        |
        v
      LogoutSuccessHandler
        |
        v
      Redirect /login?logout or JSON 200/204 per API contract
~~~

Key points:

- **LogoutFilter** and the LogoutHandlers are pre-configured by Spring Security when **logout()** and **rememberMe()** are used properly. Do not write a custom endpoint that only calls **session.invalidate()** and assume all remember-me tokens were also revoked.
- **SecurityContextLogoutHandler** cleans up session/context. It does not automatically revoke tokens in a custom login-persistence store built by the application.
- **RememberMeServices** implements **LogoutHandler**. For hash-based services, it expires the cookie; for **PersistentTokenBasedRememberMeServices**, the standard implementation also calls **PersistentTokenRepository.removeUserTokens(authentication.getName())** when **Authentication is non-null**.
- **LogoutSuccessHandler** only decides the post-processing response (redirect/JSON). A **200** or **302** response does not prove every token was actually revoked.
- Custom LogoutHandlers meant for cleanup are expected not to throw errors that break the flow. If a revoke operation at a remote service can fail, separate error/compensation rules and observability are needed instead of silently confirming "logged out everywhere" before completion.

### 3.1. Why Keep CSRF for Cookie-Based Logout?

Browsers automatically attach session/remember-me cookies when a request matches. If another site can trigger logout via **GET** or an unchecked POST, an attacker can force users to log out (logout CSRF) or cause session confusion. With Spring Security's CSRF enabled, **POST /logout** must carry a valid CSRF token; **GET /logout** serves primarily as a confirmation page.

Do not disable **csrf()** just to make a curl POST `/logout` command succeed. In the browser, the form/logout client must send a valid token. If an application exclusively uses bearer tokens in the Authorization header with no browser-attached credentials, the CSRF design may differ, though that is a threat-model-based decision.

### 3.2. Processing Order with Multiple SecurityFilterChains

If the app has an **/api/** chain, a **/web/** chain, and a fallback, the **/logout** endpoint must reside in the chain with the matching **LogoutFilter**/RememberMeServices. For example, if the web chain uses **securityMatcher("/web/**")** while the logout URL is **/logout** outside that scope, the logout request may be blocked by the fallback or processed by a different chain.

**A request is handled only by the first matching chain.** There is no mechanism where "logout fails in this chain so it falls through to the next chain's LogoutFilter". Test both URLs and matchers, not just controller/route names.

## 4. Hash-Based Remember-Me and Persistent Remember-Me Clear Differently

### 4.1. Hash-Based (TokenBasedRememberMeServices)

A hash-based cookie is issued by Spring Security from the username, expiration timestamp, password info stored in UserDetails, and a server-controlled key. The issued cookie needs no separate token record in the DB.

On logout:

1. The service sends an instruction to expire the remember-me cookie in the browser.
2. The current session is invalidated by the logout handler.
3. **If an attacker copied the cookie before logout**, that copy may remain valid until expiration because the server has no default per-cookie record to mark as revoked.
4. Broader invalidation requires changing the **password hash**, rotating the key (which affects all users), or implementing a server-checked denylist/token-version mechanism.

**Conclusion:** deleting the cookie is necessary for normal users but is not equivalent to revoking all copies of a hash-based cookie. Do not promise "log out of all devices" if the solution only sends an expiring cookie to the current device.

### 4.2. Persistent-Token (PersistentTokenBasedRememberMeServices)

A persistent cookie in the default implementation contains a random **series** and **token**. The server-side repository stores the matching data:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

On auto-login, the service looks up the series, checks the token, rotates the token, and updates last_used. The cookie is treated as a **bearer credential**: copied tokens can be replayed, so the table and backups must be protected like secrets.

**Logout behavior of the default implementation:** when a valid **Authentication** is passed to **PersistentTokenBasedRememberMeServices.logout(...)**, it calls **removeUserTokens(username)**. The standard **PersistentTokenRepository** contract deletes **by username**, not by series. Therefore **a single logout can revoke all remember-me records for the user**, not just one device.

~~~text
Before logout:
  alice:
     series-A => token-A (laptop)
     series-B => token-B (mobile)
     series-C => token-C (tablet)

POST /logout with Authentication = alice
  -> PersistentTokenRepository.removeUserTokens("alice")

After logout:
  alice: no series-A/B/C left
  -> remember-me cookies from all three devices cannot auto-login
~~~

**Make a clear product policy decision:** log out the current device, or log out all remembered devices? With the default repository/service, deleting by user is a notable behavior. If **single-device** revocation is needed, design a custom repository/service managing series, ownership, revocation, and transactions; do not call removeUserTokens and present it as deleting a single device.

### 4.3. The Null Authentication Case

In the persistent implementation, **removeUserTokens(...) only runs when Authentication is non-null**. When the browser sends logout after the session has already expired, or a custom logout mishandles SecurityContext, only the cookie may be expired in the response while the server record remains undeleted.

A browser honoring Set-Cookie will stop sending the cookie, but **a stolen token copy may still be valid**. If a strict requirement is "revoke tokens even without a session", the system must design an appropriate token/account ownership verification flow before revoking server-side, or require re-authentication to revoke everything. **Do not** let the client pass an arbitrary username to delete that username's tokens without authentication: it may work, yet creates a way to force-logout other users' accounts.

### 4.4. Logout When the DB Is Unavailable

If the repository fails or the database times out, client-side cookie deletion may still succeed while server-side revocation remains incomplete. You cannot rely on a clean HTTP response to assert revocation. Depending on security requirements, behaviors should include:

- Recording the revocation/incident request in a reliable system if the primary DB is unavailable, with a resynchronization mechanism.
- Returning an appropriate error instead of displaying "logged out of all devices" when it is not guaranteed.
- Using short session/token policies and failing closed when persistent token verification cannot reach the DB.
- Tracking bounded retries and audits; never write raw tokens to queues/logs.

Do not let a token store error cause the system to **skip verification and still allow auto-login to succeed**.

## 5. Distinguishing Single-Device Logout, All-Session Logout, and Full SSO Logout

A product should define at least three operations:

| User Goal | What Must Be Revoked | Built-in by Default? |
| --- | --- | --- |
| **Log out here** | Current session + remember-me cookie and server token per policy | Supported by Spring Security, though the default persistent service may revoke by username |
| **Log out all devices** | Every existing session and every long-lived token/series for the user | Requires SessionRepository/registry integration, token store, and multi-device handling |
| **Log out the entire SSO/IdP account** | Local app + IdP session + relying parties' sessions if protocol supports it | Requires IdP/protocol logout flow (OIDC RP-initiated logout, SAML SLO, etc.) |

**Do not conflate concepts:**

- **removeUserTokens(username)** deletes the user's persistent remember-me token records; **it does not automatically invalidate all active HTTP sessions** on other machines.
- **session.invalidate()** invalidates the current session; **it does not automatically revoke all remember-me tokens or refresh tokens**.
- **Clear-Site-Data** clears browser-side data within supported scope; **it does not automatically revoke tokens in the database or at the IdP**.
- Local logout of an OAuth2 app **does not automatically log out of the IdP**; the user may SSO back in without entering a password.

When a product features a "Log out of all devices" button, build a **revocation workflow** with a full inventory of relevant storages/issuers, consistent policy, idempotency, and end-to-end tests. Do not slap that label onto a default POST `/logout`.

## 6. Spring Boot 3.x, Spring Security 6.x, Java 17+ Example: Persistent Remember-Me and Logout

The example uses **Spring MVC/Servlet**, **form login**, **JDBC persistent remember-me**, and **H2** for a learning environment. It demonstrates standard logout revoking the session, expiring cookies, and deleting server-side records. There is no custom logout endpoint so Spring Security's LogoutHandler chain is not bypassed.

### 6.1. Project Initialization

Use Spring Initializr with **Java 17+**, **Spring Boot 3.x**, Maven, and dependencies: **Spring Web**, **Spring Security**, **Spring JDBC**, **H2 Database**, **Spring Boot Starter Test**. Add the **spring-security-test** dependency with test scope.

Typical dependencies section of **pom.xml**:

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is part of a Maven project that already has the Spring Boot parent/BOM and plugins generated by Initializr; not a complete standalone pom. All Java classes below belong in **src/main/java/com/example/logoutdemo/**.

### 6.2. Local Configuration

File **src/main/resources/application.properties**:

~~~properties
server.port=8080

# H2 file for demo purposes. Production uses managed DB, migrations, and TLS.
spring.datasource.url=jdbc:h2:file:./logout-demo;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Server session is a DIFFERENT structure from remember-me token.
server.servlet.session.timeout=15m
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Secret must be supplied from environment variable/secret manager.
demo.user.password=${DEMO_USER_PASSWORD}
demo.remember.key=${REMEMBER_ME_KEY}
~~~

The example sets **secure=true** for session and remember-me cookies. For real browser usage, serve over HTTPS (using a local HTTPS reverse proxy or direct TLS configuration). HTTP port 8080 here is only for studying backend flows; browsers may withhold Secure cookies over plain HTTP except for localhost exceptions. **Production strictly requires HTTPS and certificate validation**.

The H2 file **logout-demo.mv.db** holds sensitive credentials, must reside in a protected local directory, and must be listed in **.gitignore**. Never share DB files, backups, or keys. When wanting repeatable clean-state tests, use a separate test database instead of arbitrarily deleting production data.

File **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

In production, use Flyway/Liquibase and backup policies. Do not let a schema file automatically run/mutate production data without a review process.

### 6.3. Application Entry Point

File **LogoutDemoApplication.java**:

~~~java
package com.example.logoutdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
~~~

### 6.4. Configuring UserDetailsService and Remember-Me Repository

File **SecurityConfig.java**:

~~~java
package com.example.logoutdemo;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("USER")
                        .build());
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        // schema.sql already created the table: do not enable createTableOnStartup.
        return repository;
    }

    @Bean
    RememberMeServices rememberMeServices(
            UserDetailsService users,
            PersistentTokenRepository tokens,
            @Value("${demo.remember.key}") String key) {
        var service = new PersistentTokenBasedRememberMeServices(
                key, users, tokens);
        service.setParameter("remember-me");
        service.setCookieName("remember-me");
        service.setTokenValiditySeconds(7 * 24 * 60 * 60);
        service.setUseSecureCookie(true);
        service.setCookieCustomizer(cookie -> {
            cookie.setSecure(true);
            cookie.setHttpOnly(true);
            cookie.setPath("/");
            cookie.setAttribute("SameSite", "Lax");
        });
        return service;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RememberMeServices rememberMeServices,
            @Value("${demo.remember.key}") String key) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .requestMatchers("/account/security")
                            .fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .rememberMe(remember -> remember
                        .key(key)
                        .rememberMeServices(rememberMeServices))
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .logoutSuccessUrl("/login?logout"))
                .build();
    }
}
~~~

**Meaning and boundaries:**

1. **JdbcTokenRepositoryImpl** is the series/token store for persistent remember-me; the demo account source is **InMemoryUserDetailsManager**.
2. **PersistentTokenBasedRememberMeServices** issues the cookie when the user submits form login with the **remember-me** parameter, then verifies and rotates the token when auto-login is needed.
3. **setCookieCustomizer(...)** ensures the remember-me cookie has **Secure, HttpOnly, SameSite=Lax, Path=/**. This is a separate cookie and is not inferred from JSESSIONID's **server.servlet.session.cookie.***.
4. **.rememberMe(...rememberMeServices(...))** attaches the standard service to the chain so both the remember-me recognition filter and logout infrastructure use the same service.
5. **logout()** uses the standard LogoutFilter without bypassing RememberMeServices. Under the standard persistent implementation, **logout with Authentication** triggers **removeUserTokens(username)**.
6. **fullyAuthenticated()** blocks RememberMeAuthenticationToken on sensitive routes, enforcing full interactive authentication (or step-up per design).
7. Do not disable CSRF. Form login/logout require a valid CSRF token.
8. The demo key must remain stable across nodes/restarts if a consistent trust model is desired; never commit production keys to source control.

**This local configuration illustrates the security flow and does not yet run an HTTPS server on port 8080.** To test in a production-like browser setup, configure TLS certificates/local ingress. Do not change **secure=true** to false in production for easier debugging.

### 6.5. Controller Observing Authentication

File **ProfileController.java**:

~~~java
package com.example.logoutdemo;

import java.util.Map;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public")
    public String welcome() {
        return "public";
    }

    @GetMapping("/private")
    public Map<String, Object> privateEndpoint(
            Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "remembered",
                authentication instanceof RememberMeAuthenticationToken);
    }

    @GetMapping("/account/security")
    public String securitySettings() {
        return "fresh login required";
    }
}
~~~

After a successful form login, **/private** normally returns **remembered=false**. If the session is lost while the remember-me cookie remains valid, it can auto-login and return **remembered=true**. After a proper logout and server token deletion, the old cookie must **not** restore Authentication; a new request to **/private** will redirect to login.

### 6.6. Starting the Demo and Important Limitations

Set environment variables with a dummy password and a remember-me key supplied by a secret manager:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
export REMEMBER_ME_KEY="$(openssl rand -hex 32)"
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
$env:REMEMBER_ME_KEY = "<stable-secret-for-local-environment>"
.\mvnw.cmd spring-boot:run
~~~

**Note:** the openssl command generates a new key on every shell run. To test remember-me across restarts, use a stable key and a persistent DB in the same environment; otherwise test results will be polluted by key changes.

Because of the Secure cookie, place HTTPS in front of the app when testing with a browser. Never send real passwords over HTTP, and never bypass certificate verification. Inspect Set-Cookie at the endpoint the browser actually connects to, even when TLS terminates at a reverse proxy.

## 7. Testing Remember-Me Deletion with MockMvc and JDBC

The most important test is **real login → receive cookie → verify DB token → logout → verify cookie expired, DB cleared → attempt reusing old token**. Tests that only use **@WithMockUser** do not issue a real remember-me cookie and cannot prove the full flow.

### 7.1. Test Source

File **src/test/java/com/example/logoutdemo/RememberMeLogoutTest.java**:

~~~java
package com.example.logoutdemo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.user.password=demo-pass",
        "demo.remember.key=test-only-key-not-for-production",
        "spring.datasource.url=jdbc:h2:mem:logout_test;DB_CLOSE_DELAY=-1",
        "server.servlet.session.cookie.secure=true"
})
@AutoConfigureMockMvc
class RememberMeLogoutTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void resetPersistentTokens() {
        jdbc.update("DELETE FROM persistent_logins");
    }

    private int rememberedDeviceCount() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM persistent_logins WHERE username = ?",
                Integer.class,
                "alice");
        return count == null ? 0 : count;
    }

    private MvcResult loginWithRememberMe() throws Exception {
        return mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass")
                    .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();
    }

    @Test
    void logoutRevokesDatabaseTokenAndCookie()
            throws Exception {

        MvcResult login = loginWithRememberMe();

        Cookie originalRememberMe =
                login.getResponse().getCookie("remember-me");
        assertNotNull(originalRememberMe);
        assertEquals(7 * 24 * 60 * 60,
                originalRememberMe.getMaxAge());
        assertTrue(originalRememberMe.getSecure());
        assertTrue(originalRememberMe.isHttpOnly());
        assertEquals(1, rememberedDeviceCount());

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        MvcResult logout = mvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"))
                .andReturn();

        // Server-side revocation: a copied cookie cannot be reused.
        assertEquals(0, rememberedDeviceCount());

        // LogoutHandler issues a new cookie with Max-Age=0.
        Cookie cleared =
                logout.getResponse().getCookie("remember-me");
        assertNotNull(cleared);
        assertEquals(0, cleared.getMaxAge());

        // Do not send session; intentionally replay old remember-me cookie.
        mvc.perform(get("/private").cookie(originalRememberMe))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutOfOneSessionRevokesAllRememberedSeriesByDefault()
            throws Exception {

        MvcResult firstLogin = loginWithRememberMe();
        MvcResult secondLogin = loginWithRememberMe();

        // Each login with remember-me creates a new series.
        assertEquals(2, rememberedDeviceCount());

        MockHttpSession firstSession =
                (MockHttpSession) firstLogin
                        .getRequest().getSession(false);
        assertNotNull(firstSession);

        mvc.perform(post("/logout")
                    .session(firstSession)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        // Default repository deletes by username, not just one series.
        assertEquals(0, rememberedDeviceCount());

        Cookie secondDeviceCookie =
                secondLogin.getResponse().getCookie("remember-me");
        assertNotNull(secondDeviceCookie);

        mvc.perform(get("/private").cookie(secondDeviceCookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndTokenRemains()
            throws Exception {

        MvcResult login = loginWithRememberMe();
        assertEquals(1, rememberedDeviceCount());

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        assertEquals(1, rememberedDeviceCount());
    }

    @Test
    void loginWithoutRememberMeDoesNotCreatePersistentToken()
            throws Exception {

        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass"))
                .andExpect(status().is3xxRedirection());

        assertEquals(0, rememberedDeviceCount());
    }
}
~~~

**What do the tests prove?**

- **logoutRevokesDatabaseTokenAndCookie** checks both client and server: Set-Cookie Max-Age=0 is not enough; the DB record must be gone and the old cookie cannot log back in.
- **logoutOfOneSessionRevokesAllRememberedSeriesByDefault** checks the practical effect of **removeUserTokens(username)** in the standard implementation. The product must decide whether revoking all remembered devices is desired.
- **logoutWithoutCsrfIsRejectedAndTokenRemains** shows that an invalid POST logout must not change security state.
- **loginWithoutRememberMeDoesNotCreatePersistentToken** ensures remember-me is not unintentionally enabled for every user.

**Tests simulate HTTP via MockMvc and use in-memory H2.** They do not replace container/browser testing for SameSite, Path, Domain, TLS, and cookie stores. If implementation/schema/version differs, adjust assertions to match the real configuration; never tweak expectations just to make a test green without understanding the security behavior.

### 7.2. Running the Tests

~~~bash
./mvnw test
./mvnw -Dtest=RememberMeLogoutTest test
~~~

PowerShell:

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd '-Dtest=RememberMeLogoutTest' test
~~~

Expected result: tests complete successfully when source project and dependencies are correct. **Do not report stdout or passing test counts unless you actually ran them in your environment.**

### 7.3. Extended Acceptance Matrix

| Scenario | What Must Be Checked |
| --- | --- |
| Valid login with remember-me checked | DB has token, cookie has Secure/HttpOnly/SameSite/Path/Max-Age |
| Valid login without checking remember-me | No long-lived remember-me token created |
| Wrong password | No remember-me cookie issued and no DB token added |
| Logout valid session, valid CSRF | Session invalid, SecurityContext cleared, remember-me cookie expired, DB revoked |
| Logout missing CSRF | Returns 403; does not inadvertently revoke data from forged request |
| Reusing old remember-me cookie after logout | Cannot auto-authenticate |
| Cookie stolen before logout | Copy is still rejected if DB token was revoked |
| Logout after session already expired | Explicitly verify whether DB token was deleted; do not trust cookie clearing alone |
| Logout from one remembered device | With default service, test impact on all series of the username |
| User changes password | Integrate policy to revoke remember-me tokens, refresh tokens, and sessions properly |
| User locked/disabled | Old token must not build a valid Authentication |
| DB outage during logout | Respond per policy, emit event/audit, and never claim revocation succeeded when it did not |
| Logout across multiple tabs | Other tabs do not restore session via old token; frontend state is synchronized |
| Concurrent request during logout | Review risk of in-flight request using old context and revocation eventual consistency |
| IdP session still alive | Local logout does not mean IdP logout; test SSO re-login |
| Refresh token still alive | Revoke at token issuer or token store, not just deleting localStorage |
| Multi-instance / Redis / Spring Session | Properly invalidate shared session store; do not clear state on one node only |

## 8. Deleting Cookies Properly: Name, Path, Domain, and Prefixes

Cookies in a browser are distinguished by **name + domain + path**. Sending:

~~~http
Set-Cookie: remember-me=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

tells the browser to delete the cookie with the matching scope. If the original cookie had **Path=/app** while the deletion header has **Path=/**, the browser may retain the original cookie. Similarly, a mismatched **Domain** can create or delete the wrong cookie.

**Rules:**

1. Record the exact **name**, **Path**, and **Domain** of the cookie at issuance time.
2. On logout, expire the cookie with matching scope. Ensure the logout URL resides on the proper host/path so the browser accepts the expiring Set-Cookie.
3. Send **Max-Age=0** or an Expires date in the past. Do not send a longer Max-Age due to parameter confusion.
4. Preserve Secure and HttpOnly per policy; use HTTPS properly.
5. Inspect **Application/Storage → Cookies** and **Network → Set-Cookie** in a real browser; do not guess from config.
6. If changing cookie names or paths across application versions, consider a transition period supporting deletion of legacy cookies.

### 8.1. Session Cookie JSESSIONID

Spring Security's **SecurityContextLogoutHandler** invalidates the session by default; normally this prevents reuse of the old ID. If explicit deletion of the JSESSIONID cookie is desired, Spring Security allows:

~~~java
.logout(logout -> logout
    .deleteCookies("JSESSIONID"))
~~~

This is only an **illustrative DSL snippet**, not a full SecurityFilterChain. Cookie deletion effectiveness depends on the Servlet container, Path, and Domain, so test in real deployments. **Never replace server-side invalidation with deleteCookies**: if someone copied the session ID and the server still keeps the session, the copy remains a risk.

### 8.2. Clear-Site-Data

Header:

~~~http
Clear-Site-Data: "cookies"
~~~

instructs the browser to clear cookies within supported scope. Spring Security can configure:

~~~java
var clearCookies = new HeaderWriterLogoutHandler(
    new ClearSiteDataHeaderWriter(
        ClearSiteDataHeaderWriter.Directive.COOKIES));

http.logout(logout -> logout
    .addLogoutHandler(clearCookies));
~~~

This is an illustrative snippet in Java configuration; import the corresponding classes from **org.springframework.security.web.authentication.logout** and **org.springframework.security.web.header.writers**. **Clear-Site-Data** may affect more cookies/data than intended, depending on directive and browser; evaluate sharing an origin with other apps and browser compatibility. Clearing storage/cache can have broader impact than clearing session cookies.

**Clear-Site-Data does not call PersistentTokenRepository and does not revoke refresh tokens.** It is a browser-side operation, not a server revocation mechanism.

## 9. Long-Lived Login Credentials Beyond Remember-Me

### 9.1. Application-Issued Refresh Tokens / Access Tokens

An SPA or mobile app may use short-lived access tokens paired with long-lived refresh tokens. Secure logout typically requires:

~~~text
Client sends valid logout request
    |
    +-- Identify refresh token/session to revoke
    +-- Server revokes refresh token/token family per policy
    +-- Delete client-held token from storage
    +-- Invalidate session if the model uses sessions
    +-- Return status and synchronize across tabs/devices
~~~

**Already-issued JWT access tokens may still be accepted by APIs until exp** if the system verifies offline without checking revocation/denylist/epoch. Deleting the token from localStorage does not invalidate stolen copies. If "immediate logout" is required, design **token revocation, reference tokens, denylists, session epochs, or short access-token lifetimes** accordingly.

**Refresh token rotation**: if using token families, logout should revoke the right family or all families per user choice, while checking for replay. Do not treat a cookie named `refresh-token` as Spring Security's remember-me token; the two mechanisms have different services/issuers.

### 9.2. OAuth2AuthorizedClientService and IdP

With Spring Security OAuth2 Client, the app may store **OAuth2AuthorizedClient** containing access and refresh tokens issued to the app. On logout, removing the authorized client from the application's service/repository may be necessary. However:

- Deleting the internal **OAuth2AuthorizedClient** **does not automatically call the Authorization Server's revocation endpoint**.
- Logging out of the app **does not automatically remove the SSO session** at the IdP. When the user returns, the IdP may log them in automatically.
- If the goal is **OIDC RP-Initiated Logout**, use the IdP's endpoint flow with `id_token_hint`, `post_logout_redirect_uri`, and supported parameters; verify provider configuration.
- **SAML Single Logout** or back-channel logout have their own mechanisms; do not assume a local logout endpoint covers every relying party.

Only claim "complete logout" when the protocol and participating systems have genuinely completed revocation. If the IdP does not support it, clearly state the limitation to the user.

### 9.3. Browser localStorage, sessionStorage, IndexedDB, and Caches

If the frontend stores login data:

~~~javascript
// Frontend illustration running on the application's origin.
localStorage.removeItem("app-access-token");
localStorage.removeItem("app-user");
sessionStorage.removeItem("app-draft-auth-state");
~~~

These keys are examples for a custom-defined application; they are not APIs created by Spring Security. Do not use **localStorage.clear()** on a shared origin without understanding it will wipe valid data from other components. If tokens remain in IndexedDB or caches, delete them by managed schema/name, while clearing in-memory state and tabs via an appropriate mechanism such as **BroadcastChannel**.

For HttpOnly cookies, JavaScript **cannot** read or delete cookies via **document.cookie** like regular cookies. The server must issue an expiring Set-Cookie with matching scope. **Service Workers** and PWAs may still cache sensitive data; have an appropriate cache-clearing strategy.

**Passwords saved in the browser/OS password manager cannot and should not be arbitrarily deleted by the application.** Logging out is not equivalent to deleting an account or clearing all user autofill settings.

## 10. When an SPA Needs a JSON Logout Endpoint

REST applications often want to return **204 No Content** or JSON 200 instead of redirecting. The right approach is to **still let LogoutFilter handle it**, while replacing **LogoutSuccessHandler**:

~~~java
.logout(logout -> logout
    .logoutUrl("/api/logout")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setStatus(204);
        response.setHeader("Cache-Control", "no-store");
    }))
~~~

This is an **abbreviated configuration snippet**, not a standalone SecurityFilterChain. Ensure **/api/logout** lies inside the exact SecurityFilterChain containing LogoutFilter and RememberMeServices. With session cookies, POST logout still requires CSRF if protection is enabled.

Do not replace it with a **@PostMapping("/api/logout")** that only executes:

~~~java
// INTENTIONALLY WRONG example: only deletes a cookie in the browser,
// does not invalidate session, does not revoke database tokens.
response.addHeader("Set-Cookie",
        "remember-me=; Max-Age=0; Path=/");
~~~

The request may return HTTP 200/204 and the frontend closes its modal, yet **persistent_logins** still holds the token. If a real custom endpoint is needed, invoke the appropriate **LogoutHandler**s (SecurityContextLogoutHandler, RememberMeServices, CSRF logout, custom revoke handler), enforce CSRF/authorization, and test the full lifecycle. Do not duplicate logout logic while omitting a handler.

### 10.1. Should the Logout API Be Idempotent?

From a user behavior standpoint, logging out multiple times should not recreate sessions/credentials or leak information. If a second request arrives after the session is gone, returning status per the API contract may be 204/401 depending on design, **without falsely confirming revocation of a specific unverified token**.

Do not let the API accept an arbitrary username in the body and call **removeUserTokens(username)** unauthenticated; that can be abused to force-logout other accounts. When revoking by user, identify the user from a trusted principal or a fully verified credential token.

## 11. When Must All Long-Lived Login Credentials Be Force-Cleared?

| Event | Recommended Handling | Why |
| --- | --- | --- |
| Normal logout | Invalidate session, clear remember-me cookie; revoke remember tokens per policy | Prevent automatic re-login |
| Log out all devices | Revoke all remembered series, sessions, and refresh-token families | Remove login access from other devices |
| Password change | Consider revoking remember-me, refresh tokens, and old sessions | Old credentials may have been compromised |
| Account locked or disabled | Block login + auto-login, revoke long-lived tokens | Prevent continued access via old tokens |
| Stolen cookie detected | Revoke series/token, investigate session reuse and related sessions | Cookies are bearer credentials |
| `persistent_logins` database leaked | Assume replay risk; revoke potentially exposed tokens, audit backups | Raw series/tokens in DB are secrets |
| Hash-based signing key leaked | Rotate key, assess exposed password hashes, revoke as needed | Cookie signatures can be forged |
| User revokes OAuth2 consent | Delete authorized-client data and revoke tokens at issuer if supported | Tokens still live at Authorization Server |
| User requests account deletion | Dedicated workflow covering revocation, retention, audit, and policy-based data deletion | Logout is not account deletion |

In multi-instance systems, **revocation must be visible from every node**. If sessions reside in Redis/Spring Session, delete the exact entry in the shared store. If credential/token validation is cached, enforce TTL/invalidation so stale caches never ignore revoked records.

## 12. Common Pitfalls When Clearing Login Credentials

### 12.1. Only Redirecting to /login

The user may still hold a valid SecurityContext or remember-me cookie. **Fix:** use LogoutFilter, verify session invalidation, cookie expiration, and token store cleanup.

### 12.2. Only Deleting JSESSIONID

RememberMeAuthenticationFilter can immediately recreate Authentication from the remember-me cookie afterward. **Fix:** expire the remember-me cookie and revoke persistent tokens.

### 12.3. Only Deleting the Remember-Me Cookie

A stolen copy of the cookie can still be reused if the persistent record has not been revoked. **Fix:** verify **removeUserTokens** or custom server-side revocation.

### 12.4. Assuming Default Logout Only Revokes the Current Device

Standard PersistentTokenBasedRememberMeServices calls **removeUserTokens(username)** when Authentication is present, typically revoking **all series** for the user. **Fix:** test the policy and design separate per-device revocation if required.

### 12.5. Believing Password Changes Automatically Delete Persistent Tokens

Database tokens do not inherently depend on the password hash the way hash-based cookies do. **Fix:** attach explicit revocation to password-change/account-disable flows.

### 12.6. Rotating the Remember-Me Key to Revoke Persistent Tokens

Changing the key does not delete series/token rows still stored in the database. **Fix:** actively revoke persistent records.

### 12.7. Deleting Cookies with the Wrong Path/Domain

The browser retains the old cookie even though the response includes Max-Age=0 for another cookie of the same name. **Fix:** issue deletion with matching scope and inspect in DevTools.

### 12.8. POST /logout Without CSRF Treated as a Password Error on 403

CsrfFilter may block the request before LogoutFilter. **Fix:** send a valid token; do not disable CSRF to make tests pass.

### 12.9. Custom Controller Only Calling session.invalidate()

Insufficient if SecurityContextRepository, remember-me tokens, CSRF tokens, and custom stores remain untouched. **Fix:** use the built-in logout infrastructure or invoke all designed handlers.

### 12.10. Forgetting Data Stored by SPA or OAuth2AuthorizedClientService

Deleting browser cookies does not delete bearer/refresh tokens stored elsewhere. **Fix:** inventory credential stores, revoke them, and clear frontend state per architecture.

### 12.11. Claiming "Log Out Everywhere" While IdP Session Remains Alive

The user can return and automatically log back in via SSO. **Fix:** integrate OIDC/SAML logout if supported, and clearly communicate local vs. global scope.

### 12.12. Writing Raw Tokens to Logs for Debugging

Remember-me tokens, refresh tokens, session IDs, and Authorization headers are all replayable secrets. **Fix:** redact them, logging correlation IDs and revocation status instead of raw values.

## 13. Production Acceptance Checklist

- [ ] Logout uses **POST** with CSRF protection when the app authenticates via browser cookies.
- [ ] Endpoint belongs to the proper SecurityFilterChain; not shadowed by a fallback matcher.
- [ ] Current session is invalidated; SecurityContextHolder and repository are cleared.
- [ ] Real RememberMeServices is wired into SecurityFilterChain and the logout flow.
- [ ] Remember-me cookie is expired via Set-Cookie with matching **name/Path/Domain/Secure**.
- [ ] JSESSIONID is invalidated server-side; cookie is deleted when appropriate.
- [ ] For persistent tokens: repository actually deletes rows per policy; test reusing old cookies.
- [ ] Scope is clearly defined as **current logout** vs **all remembered devices**; do not misstate default behavior.
- [ ] Test **null Authentication** or DB failure cases so false revocation confirmations are never returned.
- [ ] Password changes, account disabling, and incidents have policies to revoke remember-me and refresh tokens.
- [ ] If issuing custom access/refresh tokens, logout includes proper server-side revocation and client-side cleanup.
- [ ] If using OAuth2/OIDC/SAML SSO, distinguish local logout from IdP/global logout.
- [ ] Browser storage, service worker/caches, and multi-tab state are cleared in a controlled way.
- [ ] Never expose raw cookies/tokens in logs, test output, crash dumps, or tickets.
- [ ] Test post-logout token replay, concurrent requests, multi-instance setups, and Redis/database consistency.
- [ ] Sensitive endpoints require **fullyAuthenticated()** or step-up authentication rather than trusting remember-me indefinitely.
- [ ] Monitoring for logout/revocation failures and an incident-response runbook are in place.

## 14. Self-Check Questions

**1. Why is a user still recognized after logging out of a session?** Because the remember-me cookie is still valid and RememberMeAuthenticationFilter can automatically re-authenticate once the session is gone. Check both the cookie and the token store.

**2. Is deleting the remember-me cookie in the browser enough to revoke a stolen token?** No, especially when a copy exists elsewhere. For persistent tokens, you must revoke the server-side record; for hash-based tokens, consider changing the password/key or adding a revocation mechanism.

**3. How many devices can a single logout affect with standard PersistentTokenBasedRememberMeServices?** When a valid Authentication is provided, the implementation calls **removeUserTokens(username)**, which can delete every series belonging to that user. You must test and document the exact scope.

**4. When Authentication is null, does persistent logout guarantee deleting all tokens in the DB?** No. Deletion by username in the standard implementation depends on Authentication. A separate design is required if revocation must also happen after the session has expired.

**5. Does deleting JSESSIONID delete access tokens in OAuth2AuthorizedClientService?** Not by default. Tokens stored on the server or Authorization Server have separate lifecycles; clean up and revoke the appropriate components.

**6. Why should GET /logout not arbitrarily perform state changes?** GET requests are easily triggered via navigation; Spring Security typically uses GET for a confirmation page and POST with CSRF for the actual logout.

**7. Is using Clear-Site-Data: "cookies" equivalent to revoking a refresh token?** No. It instructs the browser to delete cookies; you must still revoke active tokens on the server/issuer.

## 15. References

- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): LogoutHandler chain, session/context, remember-me cleanup, Clear-Site-Data, and logout endpoints.
- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html): hash-based and persistent remember-me, cookies, UserDetailsService, and schema.
- [PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html): logout(), token rotation, CookieTheftException, and repository.
- [PersistentTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html): removeUserTokens(username), create/update/get token.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): invalidating sessions, cookie clearing, and session policies.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF tokens and logout for cookie-based apps.
- [Spring Security 6.5 — OAuth2 Login / OIDC Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): configuring logout with OpenID Connect if needed.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Max-Age, Path, Domain, Secure, HttpOnly, SameSite.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session expiration, revocation, and cookie security.
