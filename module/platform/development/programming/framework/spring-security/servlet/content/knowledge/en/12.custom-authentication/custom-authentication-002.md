# Designing a Custom Authentication Token and Unauthenticated State in Spring Security Servlet

**Context:** Java 17+, Spring Security 6.x, and Spring Boot 3.x on Jakarta Servlet. This lesson belongs to the **Custom Authentication** group. The focus is on distinguishing an *authentication request* token from an *authenticated* token, how to create a custom <code>Authentication</code>, using an <code>AuthenticationProvider</code> to verify evidence, and placing a trusted result into the <code>SecurityContext</code> in a controlled manner.

Here the word **token** means a Java object implementing the <code>org.springframework.security.core.Authentication</code> interface. It is **not by default a JWT, OAuth2 access token, API key, or string sent by a client**. A custom Authentication token may exist only inside the JVM, used to carry credentials from a filter to AuthenticationManager and the result from AuthenticationProvider back to Spring Security.

## 1. Why Do We Need a Custom Authentication Token?

Spring Security already provides many common authentication types such as username/password, Basic, OAuth2/OIDC, bearer token, X.509, and pre-authentication. You should only create a custom token when login evidence or business state cannot be represented appropriately with built-in mechanisms, for example:
- Authenticating with a specialized credential type issued by an internal system.
- Combining an account with a server-verified challenge.
- Connecting an AuthenticationProvider that verifies credentials according to a custom business protocol.
- Representing pre- and post-authentication phases while still integrating with <code>AuthenticationManager</code>, <code>SecurityContext</code>, and Spring Security authorization.

There is no need to create a custom token just because a controller wants to know the user's roles or needs an extra attribute. You can use a custom principal in an existing authentication mechanism, an <code>AuthenticationConverter</code>, or a <code>GrantedAuthoritiesMapper</code>, depending on the goal. Avoid inventing a login mechanism instead of a supported standard when OIDC/OAuth2, SAML, or passkeys have suitable libraries.

### Five Components on the Authentication Path

| Component | Role | Is it a source of authorization trust? |
| --- | --- | --- |
| <code>Authentication</code> | Object describing the authentication request/result | Not necessarily: depends on <code>isAuthenticated()</code> and creation source |
| <code>AuthenticationManager</code> | Coordinates authentication, typically <code>ProviderManager</code> | Delegates verification to a provider |
| <code>AuthenticationProvider</code> | Verifies credentials and returns an authenticated Authentication | **Yes**, after verifying the evidence itself |
| <code>SecurityContext</code> | Holds the request/session Authentication | Holds state; does not verify credentials itself |
| <code>SecurityContextHolder</code> | Provides the SecurityContext to currently executing code | Not a place to self-mark a user as trusted |

Typical sequence:

~~~text
HTTP request
    |
SecurityFilterChain / custom authentication filter
    |
custom Authentication (isAuthenticated = false)
    |
AuthenticationManager -> AuthenticationProvider.supports(...)
    |
Provider checks credential from a trusted source
    |-----------------------------+
    | Wrong / missing             | Valid
    v                             v
AuthenticationException      Authenticated Authentication
(401, no context saved)      isAuthenticated = true
                                  |
                             SecurityContext
                                  |
                             AuthorizationFilter
                                  |
                        200 / 403 depending on GrantedAuthority
~~~

Never authorize a request just because the client sends a flag <code>authenticated=true</code>, <code>role=ADMIN</code>, or an <code>Authentication</code> constructed by a controller itself.

## 2. Contract of the Authentication Interface

<code>Authentication</code> extends <code>Principal</code> and has key methods:

- <code>getPrincipal()</code>: the presented identity or identifier; before authentication this may only be an unverified username, after authentication it is the confirmed principal.
- <code>getCredentials()</code>: the evidence for authentication, such as a password, code, or other credential. Raw credentials should be erased/not retained after completion.
- <code>getAuthorities()</code>: list of <code>GrantedAuthority</code>. Authorities have authorization meaning **only when they come from a verified source**.
- <code>getDetails()</code>: additional request data, such as remote address or device info; does not substitute for credential verification.
- <code>isAuthenticated()</code> and <code>setAuthenticated(...)</code>: represents/updates the object's state according to the token type's contract.
- <code>getName()</code>: identifying name used by the <code>Principal</code> API.

Typically <code>AbstractAuthenticationToken</code> pre-implements much of the contract, such as the authority list, details, <code>isAuthenticated()</code>, <code>getName()</code>, and credential erasure via <code>CredentialsContainer</code>. A custom token must complete <code>getPrincipal()</code>, <code>getCredentials()</code>, and decide how trusted state is created.

### Two States of the Same Token Type

**Unauthenticated request token:**

~~~text
principal = "learner"           (only a claim from the request)
credentials = "..."             (unverified code)
authorities = []                (do not trust client permissions)
authenticated = false
~~~

**Authenticated result token:**

~~~text
principal = "learner"           (verified via provider)
credentials = null              (do not retain raw code)
authorities = [ROLE_LEARNER]    (server-granted)
authenticated = true
~~~

Do not interpret <code>authenticated=false</code> as "anonymous user" in all cases: a request token can carry a proposed username/credential that has not yet been verified. Also do not use the boolean alone to prove a user is validly logged in: certain special tokens such as <code>AnonymousAuthenticationToken</code> have <code>isAuthenticated()</code> set to true by contract, while authorization rules such as <code>authenticated()</code> use appropriate interpretation to distinguish anonymous users. Trusted state must be determined by **the authentication pipeline and the Authentication type**.

## 3. Principles for Designing a Secure Token

A well-designed custom token has:
1. Public factories/constructors **only for the unauthenticated state**. Client input placed in a request token carries no privileged authorities.
2. Constructors/factories creating an authenticated token are called only from trusted code after the provider verifies the credential. This is a design rule, not a sandbox mechanism replacing code review.
3. Prevent arbitrary code from calling <code>setAuthenticated(true)</code> on a request token to bypass the provider.
4. Separate <code>principal</code>, <code>credentials</code>, and <code>authorities</code> semantically; credentials can be erased after authentication.
5. Do not include credentials in <code>toString()</code>, logs, exceptions, or details. A <code>String</code> already read from an HTTP header has limitations on memory erasure; avoid retaining extra copies.
6. Retain only server-granted permission data. If the client sends <code>X-Role: ADMIN</code>, the filter/provider must ignore it.
7. Do not allow an Authentication to have <code>isAuthenticated=true</code> merely because JSON/headers/tokens were parsed. Parsing is not verification.

An unauthenticated token must flow to <code>AuthenticationManager.authenticate(...)</code>; failure must produce a meaningful <code>AuthenticationException</code>. Do not grant high default authorities when the database is slow, headers are missing, or credentials are invalid.

## 4. Standalone Example: Demo Code in HTTP Headers, Per-Request Stateless

The example uses two headers <code>X-Demo-User</code> and <code>X-Demo-Code</code> to illustrate the custom token mechanism. The provider verifies the demo user <code>learner</code> and a server-side code read from an environment variable. When valid, it grants only <code>ROLE_LEARNER</code>.

**This is a training mechanism, absolutely not a production login design.** Shared codes, credentials in headers, and the lack of replay protection/rate limiting/rotation/per-user identification make it unsuitable for real systems. In production, prefer OAuth2/OIDC, properly verified bearer tokens, mTLS, or another standard mechanism. The example is limited to GET, creates no session, and **does not disable CSRF** (Spring Security still maintains its default policy for state-changing methods).

Project structure:

~~~text
custom-token-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/customauth/
    │   │   ├── CustomAuthApplication.java
    │   │   ├── DemoCodeAuthenticationToken.java
    │   │   ├── DemoCodeAuthenticationProvider.java
    │   │   ├── DemoCodeFilter.java
    │   │   └── SecurityConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/customauth/
            └── CustomAuthenticationTest.java
~~~

### 4.1. File pom.xml

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
    <artifactId>custom-token-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

### 4.2. Controller for Testing Authentication Results

Create <code>src/main/java/com/example/customauth/CustomAuthApplication.java</code>:

~~~java
package com.example.customauth;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CustomAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/private")
    public String privateEndpoint(Principal principal) {
        return "private:" + principal.getName();
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin";
    }
}
~~~

<code>/private</code> requires an authenticated user with role LEARNER; <code>/admin</code> requires ADMIN. The sample provider **grants only ROLE_LEARNER**, so even valid credentials are not enough to access admin; this is the difference between successful authentication and granted authorization.

### 4.3. Custom Authentication Token: Unauthenticated Factory and Trusted Factory

Create <code>src/main/java/com/example/customauth/DemoCodeAuthenticationToken.java</code>:

~~~java
package com.example.customauth;

import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class DemoCodeAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private DemoCodeAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        if (authenticated) {
            // Internal constructor only for provider results.
            super.setAuthenticated(true);
        }
    }

    // Allowed to be created from request data: NOT yet trusted.
    public static DemoCodeAuthenticationToken unauthenticated(
            String username, String code) {
        return new DemoCodeAuthenticationToken(username, code, null, false);
    }

    // Used only within the same package after provider verification.
    static DemoCodeAuthenticationToken authenticated(
            String username,
            Collection<? extends GrantedAuthority> authorities) {
        return new DemoCodeAuthenticationToken(
            username, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                "Cannot mark request token as trusted");
        }
        super.setAuthenticated(false);
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }
}
~~~

Important explanation:

- <code>unauthenticated(...)</code> calls the constructor with <code>authorities=null</code>; <code>AbstractAuthenticationToken</code> represents an empty authority set. <code>isAuthenticated()</code> starts as false.
- <code>authenticated(...)</code> is a **package-private** factory called by the demo provider after verification, passing server-created authorities. This is only a codebase convention, not a security boundary against other code in the same package; every call site to the factory must still be reviewed.
- External <code>setAuthenticated(true)</code> calls are blocked. Only the trusted branch of the internal constructor uses <code>super.setAuthenticated(true)</code>. Do not create a public factory allowing callers to attach the ADMIN role themselves.
- After authentication, <code>credentials=null</code>. That avoids retaining the raw code in the result token. <code>eraseCredentials()</code> also clears credentials on the request token if invoked.
- <code>principal</code> on an unauthenticated request is only a user-claimed string; it becomes a trusted identity only when the provider verifies it successfully.

Modern Spring Security also includes built-in tokens with static <code>unauthenticated(...)</code>/<code>authenticated(...)</code> factories. The rules about where trusted state originates remain the same.

### 4.4. AuthenticationProvider Verifies the Code from a Server Source

Create <code>src/main/java/com/example/customauth/DemoCodeAuthenticationProvider.java</code>:

~~~java
package com.example.customauth;

import java.util.List;
import org.springframework.core.env.Environment;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DemoCodeAuthenticationProvider
        implements AuthenticationProvider {

    private final PasswordEncoder encoder;
    private final String expectedCodeHash;

    public DemoCodeAuthenticationProvider(
            PasswordEncoder encoder, Environment environment) {
        this.encoder = encoder;
        String demoCode = environment.getRequiredProperty("demo.auth.code");
        // Do not retain raw credentials as a provider field.
        this.expectedCodeHash = encoder.encode(demoCode);
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        if (!(authentication instanceof DemoCodeAuthenticationToken request)
                || request.isAuthenticated()) {
            throw new BadCredentialsException("Invalid demo credentials");
        }

        String username = (String) request.getPrincipal();
        String code = (String) request.getCredentials();

        // Verify code on the server; do not trust identity or roles from headers.
        boolean codeValid = encoder.matches(
            code == null ? "" : code, expectedCodeHash);
        if (!codeValid || !"learner".equals(username)) {
            throw new BadCredentialsException("Invalid demo credentials");
        }

        DemoCodeAuthenticationToken result =
            DemoCodeAuthenticationToken.authenticated(
                "learner",
                List.of(new SimpleGrantedAuthority("ROLE_LEARNER")));
        result.setDetails(request.getDetails());
        return result;
    }

    @Override
    public boolean supports(Class<?> type) {
        return DemoCodeAuthenticationToken.class.isAssignableFrom(type);
    }
}
~~~

**Distinguishing <code>supports</code> and <code>authenticate</code>:**
- <code>supports(type)</code> only indicates that the provider **can handle the token type**. It does not yet verify that any credential is valid.
- <code>authenticate</code> must verify the evidence before returning an <code>isAuthenticated=true</code> token.
- If the token is supported but the credential is wrong, the provider throws <code>BadCredentialsException</code>, never returning an authenticated object.
- A provider can return <code>null</code> when it cannot decide and wants the next provider to process according to its contract; however, **never** use <code>null</code> as "success" or allow requests without evidence to skip authentication.
- The resulting Authentication is granted only <code>ROLE_LEARNER</code> by the server. A spoofed header <code>X-Demo-Roles: ROLE_ADMIN</code> is completely ignored in the provider.

The demo hashes a code configured from the environment at startup. It does **not** replace a production credential store, and has no attempt limits, secret rotation, one-time codes, or replay protection. Never deploy this header-code mechanism in a public environment.

### 4.5. Custom Filter Converts HTTP Headers into a Request Token

Create <code>src/main/java/com/example/customauth/DemoCodeFilter.java</code>:

~~~java
package com.example.customauth;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.web.filter.OncePerRequestFilter;

public final class DemoCodeFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;

    public DemoCodeFilter(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String username = request.getHeader("X-Demo-User");
        String code = request.getHeader("X-Demo-Code");

        // No credentials present: let anonymous/authorization handle it.
        if (username == null && code == null) {
            chain.doFilter(request, response);
            return;
        }

        // One header present but the other missing: reject explicitly.
        if (username == null || code == null
                || username.isBlank() || code.isBlank()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        DemoCodeAuthenticationToken requested =
            DemoCodeAuthenticationToken.unauthenticated(username, code);
        requested.setDetails(
            new WebAuthenticationDetailsSource().buildDetails(request));

        final Authentication verified;
        try {
            verified = authenticationManager.authenticate(requested);
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED,
                "Invalid demo credentials");
            return;
        } finally {
            requested.eraseCredentials();
        }

        // Per-request authentication: DO NOT save to HttpSession.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

The filter makes explicit decisions:
1. Neither header present: does not auto-login. The request may be allowed into public endpoints; protected endpoints will be challenged by authorization for authentication.
2. Missing header/wrong code: responds with 401 and does not save a trusted Authentication.
3. Credentials are wrapped into <code>DemoCodeAuthenticationToken.unauthenticated(...)</code> and passed to <code>AuthenticationManager</code>.
4. Only the result returned by the provider is placed into the SecurityContext. The input token has its credentials erased when verification finishes.
5. Because the demo uses <code>SessionCreationPolicy.STATELESS</code>, the SecurityContext is not saved to HttpSession. The same browser wanting to access <code>/private</code> on the next request must resend valid credentials.
6. The context is cleared in <code>finally</code> so identities do not leak to other requests when servlet threads are reused.

For a real product, you must add duplicate-header/canonicalization checks, trusted proxy handling, rate limiting, timeouts, metrics, and credential redaction across all logs. Using <code>sendError</code> in the demo filter is an intentionally simple choice; real projects should stay consistent with <code>AuthenticationEntryPoint</code> and JSON/problem-details responses.

An important limitation: a custom authentication filter **does not automatically run inside every SecurityFilterChain**. It runs only in the chains where you register it. If there are multiple chains or narrow matchers, verify that real requests enter the right chain under the **first matching SecurityFilterChain** rule.

### 4.6. SecurityFilterChain, ProviderManager, PasswordEncoder

Create <code>src/main/java/com/example/customauth/SecurityConfiguration.java</code>:

~~~java
package com.example.customauth;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationManager demoAuthenticationManager(
            DemoCodeAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager demoAuthenticationManager)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").hasRole("LEARNER")
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, error) -> response.sendError(401)))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                new DemoCodeFilter(demoAuthenticationManager),
                AnonymousAuthenticationFilter.class)
            .build();
    }
}
~~~

Rationale:
- <code>ProviderManager</code> knows only the provider supporting the custom token; other built-in credentials are not used automatically in this demo.
- <code>DemoCodeFilter</code> is instantiated **directly when building the SecurityFilterChain**, **not declared as a <code>@Component</code> or <code>@Bean</code> Servlet Filter**. If a Filter is a bean in Spring Boot Servlet, it can be auto-registered in the container as well, causing it to run twice or in the wrong order.
- <code>addFilterBefore(..., AnonymousAuthenticationFilter.class)</code> lets the custom filter establish an authenticated context before anonymous authentication and authorization run.
- <code>SessionCreationPolicy.STATELESS</code>: does not use HttpSession to save/load SecurityContext; the context lives only within the demo request.
- <code>formLogin</code> and <code>httpBasic</code> are disabled so learners can distinguish the new authentication path from built-in username/password filters.
- <code>exceptionHandling(...authenticationEntryPoint...)</code> produces a 401 response for protected endpoints when no valid Authentication exists; callers with a valid Authentication lacking the required authority usually receive 403.
- <code>anyRequest().denyAll()</code> prevents unlisted paths from being permitted by default. This rule applies because **the sample SecurityFilterChain matches all requests**.
- **CSRF is not disabled** in the demo: only GETs are permitted. If POSTs are added later, CSRF must be evaluated based on how browsers send credentials; never disable CSRF app-wide without a threat model.

### 4.7. Declaring the Demo Code from an Environment Variable

Create <code>src/main/resources/application.yml</code>:

~~~yaml
demo:
  auth:
    code: ${DEMO_AUTH_CODE}
~~~

At startup, if <code>DEMO_AUTH_CODE</code> is not provided, the demo lacks required configuration and should not run. In tests, a dedicated <code>demo.auth.code</code> property is used; the dummy code is a test fixture and must not be reused in production. In production, secrets must come from a controlled system with transport and lifecycle protection.

## 5. Observing Request/Result State in Java

After the parser extracts the two headers, the initial token has:

~~~java
DemoCodeAuthenticationToken submitted =
    DemoCodeAuthenticationToken.unauthenticated(
        "learner", "test-code-123456789");

// submitted.isAuthenticated() == false
// submitted.getAuthorities().isEmpty() == true
// submitted.getPrincipal().equals("learner") == true
// submitted.getCredentials() holds the unverified raw code.
~~~

The snippet above is understood within the demo package and dependencies, not as a standalone Java file with <code>main</code>. Do **not** call <code>submitted.setAuthenticated(true)</code>: the demo intentionally throws <code>IllegalArgumentException</code> as a reminder not to promote a request token into a trusted token.

After successful verification:

~~~java
Authentication result = demoAuthenticationManager.authenticate(submitted);

// result.isAuthenticated() == true
// result.getPrincipal().equals("learner") == true
// result.getCredentials() == null
// result.getAuthorities() contains exactly ROLE_LEARNER
~~~

The returned object carries the LEARNER authority because **the AuthenticationProvider verified the server-side code**. The username string "learner" itself does not grant any role. When the code is wrong, the provider throws <code>BadCredentialsException</code> and no authenticated result is returned.

If an application needs multi-step authentication (such as an OTP challenge), do not mark a token <code>authenticated=true</code> merely because step 1 completed. You can use a separate request/challenge type, store verified challenge state with a TTL/anti-replay guard, and create a fully authenticated token only when all required conditions are met. If a partial-authentication model with restricted permissions is needed, model it explicitly via authentication type/authorities and dedicated rules rather than misusing <code>isAuthenticated</code>.

## 6. Running HTTP Requests and Reading Results

On Windows PowerShell, inside the directory containing <code>pom.xml</code>:

~~~powershell
$env:DEMO_AUTH_CODE = "local-demo-code-123456789"
mvn spring-boot:run
~~~

In another terminal:

~~~powershell
# Public.
curl.exe -i http://localhost:8080/public

# No headers sent -> anonymous -> 401.
curl.exe -i http://localhost:8080/private

# Valid credentials -> 200, body "private:learner".
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: local-demo-code-123456789" http://localhost:8080/private

# Wrong credentials -> 401.
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: bad-code" http://localhost:8080/private

# Only one header -> 401.
curl.exe -i -H "X-Demo-User: learner" http://localhost:8080/private

# Valid credentials but missing ROLE_ADMIN -> 403.
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: local-demo-code-123456789" http://localhost:8080/admin

# Forged role header cannot escalate privileges -> 403.
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: local-demo-code-123456789" -H "X-Demo-Roles: ROLE_ADMIN" http://localhost:8080/admin
~~~

| Request | Authentication | Authorization | Expected HTTP |
| --- | --- | --- | --- |
| GET /public, no header | Anonymous | permitAll | 200, <code>public</code> |
| GET /private, no header | No real user | hasRole LEARNER | 401 |
| GET /private, valid user/code | Custom token authenticated, ROLE_LEARNER | Passes | 200, <code>private:learner</code> |
| GET /private, wrong code | AuthenticationException | Not treated as authenticated user | 401 |
| GET /private, missing one header | No valid token created | Rejected at filter | 401 |
| GET /admin, valid user/code | ROLE_LEARNER | Missing ROLE_ADMIN | 403 |
| GET /admin, also sends X-Demo-Roles=ROLE_ADMIN | ROLE_LEARNER | Forged header has no effect | 403 |

A second request after receiving 200 must resend the headers to keep accessing <code>/private</code>, because the example **does not save logins to HttpSession**. Do not equate a custom Authentication token with an automatically persisted login session.

## 7. Testing Token, Provider, and SecurityFilterChain with MockMvc

Add <code>src/test/java/com/example/customauth/CustomAuthenticationTest.java</code>:

~~~java
package com.example.customauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.auth.code=test-code-123456789")
@AutoConfigureMockMvc
class CustomAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AuthenticationManager demoAuthenticationManager;

    @Test
    void requestTokenStartsUntrustedAndCannotSelfAuthenticate() {
        DemoCodeAuthenticationToken request =
            DemoCodeAuthenticationToken.unauthenticated(
                "learner", "test-code-123456789");

        assertThat(request.isAuthenticated()).isFalse();
        assertThat(request.getAuthorities()).isEmpty();
        assertThatThrownBy(() -> request.setAuthenticated(true))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void onlyProviderCanReturnVerifiedAuthority() {
        Authentication result = demoAuthenticationManager.authenticate(
            DemoCodeAuthenticationToken.unauthenticated(
                "learner", "test-code-123456789"));

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getCredentials()).isNull();
        assertThat(result.getPrincipal()).isEqualTo("learner");
        assertThat(result.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactly("ROLE_LEARNER");
    }

    @Test
    void noHeadersPublicAllowedAndPrivateRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void goodCredentialIsAuthenticatedForOneRequest() throws Exception {
        mvc.perform(get("/private")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "test-code-123456789"))
            .andExpect(status().isOk())
            .andExpect(content().string("private:learner"));

        // Stateless: a new request without headers does not retain the previous identity.
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongOrPartialHeadersAreRejected() throws Exception {
        mvc.perform(get("/private")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "wrong"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private")
                .header("X-Demo-User", "learner"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private")
                .header("X-Demo-User", "other")
                .header("X-Demo-Code", "test-code-123456789"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedRoleComesFromProviderNotClientHeader() throws Exception {
        mvc.perform(get("/admin")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "test-code-123456789")
                .header("X-Demo-Roles", "ROLE_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedUrlIsDeniedEvenWithValidCredential() throws Exception {
        mvc.perform(get("/unlisted")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "test-code-123456789"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run <code>mvn test</code>. The tests prove:
- A request token starts unauthenticated and cannot elevate privileges via its setter.
- The provider returns an authenticated result only after verifying the credential.
- Public endpoints do not require headers; protected endpoints require Authentication.
- Wrong/missing credentials or wrong username yield 401.
- Being authenticated **does not mean having every permission**: LEARNER still receives 403 on <code>/admin</code>.
- Self-declared role headers have no effect on the outcome.
- One successful request does not automatically create a login session for the next request.

The code and status codes shown here are tailored to the demo configuration and do not represent every system with custom exception handlers or multiple filter chains. In real integrations, add tests for filter ordering, excluded paths, context propagation, logout, and authentication failure handling.

## 8. Distinguishing Incomplete Authentication from Anonymous and Authorization

There are at least four states to distinguish:

| State | Example | Should access to protected endpoint be allowed? |
| --- | --- | --- |
| No credentials | Request to <code>/private</code> without headers | No; authentication is typically required |
| Parsed credentials, **unverified** | <code>DemoCodeAuthenticationToken.unauthenticated(...)</code> | No; must invoke the provider |
| Verified credentials but lacking permission | Result has ROLE_LEARNER, requests <code>/admin</code> | No; authorization returns 403 |
| Verified credentials with permission | Result has ROLE_LEARNER, requests <code>/private</code> | Yes, if other rules also pass |

An <code>Authentication</code> can already hold a principal while unauthenticated. Do not take <code>getPrincipal()!=null</code> as proof of login; at that point the principal may only be caller-claimed data. Similarly, do not rely on the size of <code>getAuthorities()</code> on an input token to decide whether credentials are valid. The authority set is trustworthy only after the provider.

In Spring Security, anonymous authentication is handled by a dedicated mechanism and can create an <code>AnonymousAuthenticationToken</code>. An anonymous token is not equivalent to an actually authenticated user even though its <code>isAuthenticated()</code> can be true. When checking logic in production code, prefer Spring Security rules like <code>authenticated()</code> or an <code>AuthenticationTrustResolver</code> instead of inferring from a single boolean.

## 9. Authentication Token vs Network-Transmitted Tokens

Using the same word "token" for all of the following easily causes design mistakes:

- **Java Authentication token:** an in-process object, e.g., <code>DemoCodeAuthenticationToken</code>, carrying trusted/untrusted state based on how it was constructed.
- **API key or demo code:** a string sent by the client; merely proposed evidence that can be wrong, leaked, or replayed.
- **JWT access token:** a signed string with claims requiring verification of signature, issuer, audience, expiry, and other constraints. Parsing the payload alone is not authentication.
- **HttpSession ID:** a server-side session reference key, typically carried by a cookie; Spring Security may use sessions to store the SecurityContext.
- **CSRF token:** used to mitigate cross-site request forgery; by itself it proves no identity and must never become an authority.

A custom <code>Authentication</code> can be built from a verified JWT or trusted account data. However, instantiating a Java object <code>new SomeAuthenticationToken(...)</code> does not replace verifying the underlying protocol.

## 10. When Session-Based Login Is Needed Instead of Stateless

The example in section 4 intentionally does not persist the SecurityContext across requests. If building a **stateful login**, do not merely change <code>SessionCreationPolicy</code> from STATELESS to IF_REQUIRED and expect every custom filter to write the session automatically.

In Spring Security 6, default configuration using <code>SecurityContextHolderFilter</code> may require **explicitly saving the SecurityContext** via <code>SecurityContextRepository</code> when custom authentication succeeds. You must also consider <code>SessionAuthenticationStrategy</code> to handle session fixation, session limits, and lifecycle. Pay attention to the invocation order of these components and save the context **only after** AuthenticationManager returns a successful result.

Illustrative snippet (not copy-pasteable standalone into the stateless demo):

~~~java
// The repository, request, and response components must be configured
// inside a valid stateful authentication filter/handler.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

<code>SecurityContextRepository</code> may use HttpSession, request attributes, or a composite repository by design. Know which repository the SecurityFilterChain actually uses; do not merely call <code>getSession(true)</code> and stuff Authentication into an arbitrary attribute. With a standard <code>AuthenticationFilter</code>, you can combine converter, success/failure handlers, and repository via framework APIs instead of managing everything manually.

With a custom provider, on logout or credential revocation, the corresponding session/token must be cleaned up. <code>eraseCredentials()</code> is not logout: it only clears sensitive evidence from the object, without invalidating the session.

## 11. AuthenticationFilter and AuthenticationConverter: Another Option for Production

In the demo, to make every step visible, <code>DemoCodeFilter</code> extends <code>OncePerRequestFilter</code> and calls AuthenticationManager directly. In real projects, a more idiomatic Spring Security design typically consists of:

1. <code>AuthenticationConverter</code>: turns structurally validated HTTP input into an **unauthenticated** custom request token; returns null if not applicable.
2. <code>AuthenticationManager</code> / <code>ProviderManager</code>: selects the provider supporting the token.
3. <code>AuthenticationProvider</code>: verifies evidence and returns a trusted Authentication.
4. <code>AuthenticationFilter</code>: coordinates authentication, success/failure handlers, security context, and the appropriate repository.
5. <code>SecurityFilterChain</code>: declares filter position, matchers, and authorization.

Separating the converter from the provider lets you test credential parsing, missing/malformed/duplicate headers separately from server-side verification. Never let a converter build a token with client-declared authorities. A provider must recognize the right token type via <code>supports</code> and handle failures via <code>AuthenticationException</code>; do not use arbitrary <code>RuntimeException</code>s that mix system errors with invalid credentials.

In applications with multiple providers, <code>ProviderManager</code> may try providers per their contracts. A provider that determines credentials are invalid must report an appropriate error; do not allow another mechanism to accidentally turn invalid credentials into a valid account with broader permissions.

## 12. Security Rules for Authentication Results

A trusted Authentication should satisfy these invariants:

| Invariant | Why does it matter? |
| --- | --- |
| Principal comes from a verified server/IdP source | Avoids trusting self-declared usernames or userIds |
| Credentials removed from result if unneeded | Reduces risk of logs/dumps leaking secrets |
| Authorities determined solely by the server | Prevents privilege escalation from headers/client body |
| <code>isAuthenticated=true</code> only after sufficient evidence | Prevents bypassing the authentication provider |
| Context does not leak to other requests/threads | Prevents user B from assuming user A's identity |
| Failures do not create an authenticated context | Invalid requests must receive 401 or consistent failure handling |
| Context is saved **only if policy requires** | Stateless flows do not create unintended sessions |
| Session/token revocation designed if needed | Logout or permission changes take effect properly |

A provider can load an account from a database, check locked/disabled/expired status, verify credentials, and grant authorities from real roles/permissions. The simplified demo omits those parts, so header-code must not be treated as a replacement for production authentication.

Choices like <code>ROLE_LEARNER</code> and <code>hasRole("LEARNER")</code> involve the default <code>ROLE_</code> prefix. If code creates <code>SimpleGrantedAuthority("LEARNER")</code> while a rule checks <code>hasRole("LEARNER")</code>, you may get 403 because the authority does not match. <code>hasAuthority("report:read")</code> compares the exact permission string without adding a prefix.

## 13. Common Mistakes and How to Check Them

| Error / Symptom | Cause | Resolution |
| --- | --- | --- |
| Creating request token with <code>authenticated=true</code> | Trusting unverified data | Default unauthenticated factory; provider creates trusted token |
| <code>setAuthenticated(true)</code> callable from anywhere | Bypasses provider | Disallow setter elevation; review all trusted constructors/factories |
| Client sends <code>ROLE_ADMIN</code> and API allows it | Granting authorities from client data | Map permissions from verified server or IdP |
| Provider returns <code>null</code> for wrong credentials | Can be misinterpreted in provider chain | Throw AuthenticationException for wrong credentials |
| Wrong credentials cause 500 | AuthenticationException not handled in the right place | Failure handler/entry point returns authentication failure response |
| GET /private without headers returns 200 | Filter or authorization is misconfigured as permitAll | Test anonymous, inspect matchers, filter order |
| GET /admin as LEARNER returns 200 | Overly broad authority or rule granted | Test roles/permissions and least-privilege principle |
| Log in once but next request still needs header | Stateless, SecurityContext not saved | Design stateful flow if session is truly needed |
| Custom stateful login works only on first request | Forgot saveContext or session strategy | Check SecurityContextRepository/Spring Security 6 |
| Filter runs twice | Spring Boot auto-registers a Filter bean and Spring Security adds it too | Avoid auto-registered Servlet Filter bean or disable registration explicitly |
| Custom filter does not run | Registered on wrong SecurityFilterChain/matcher order | Identify first matching chain and addFilterBefore position |
| Secret appears in logs | Printing full Authentication/request/headers | Redact credentials, audit log pipelines and error handlers |
| JWT parsed successfully but unverified | Confusing parsing with trust | Verify issuer, audience, signature, expiry, appropriate claims |
| Thread handling another request carries old user | Forgot to clear SecurityContext | Clear context in finally and use proper context propagation |
| Disabling CSRF on cookie/session apps | Removing protection for state-changing requests | Assess threat model, enable CSRF at appropriate scope |

## 14. Checklist When Implementing Custom Authentication

1. Identify **why** built-in authentication types do not fit; clearly define the boundary between the credential source and the Java Authentication token.
2. Design the unauthenticated token with proposed principal, raw credentials, empty authorities, <code>isAuthenticated=false</code>; block arbitrary state elevation.
3. Define a provider supporting the exact class, verifying against a trusted source and producing a trusted Authentication without retaining raw credentials.
4. Place the custom filter/converter properly in the SecurityFilterChain; avoid duplicate auto-registration; verify the first matching chain.
5. Choose stateless or stateful intentionally. For stateful, configure SecurityContextRepository, explicit save, and session fixation/session limits as needed.
6. Declare authorization rules by role/permission; deny unlisted URLs by default.
7. Treat authentication failure/expired accounts as authentication errors, avoiding accidental fallbacks into broad access.
8. Protect credentials with TLS, secret management, rate limiting, TTL/anti-replay when needed, and log controls; do not use the demo header-code in production.
9. Test token factories, provider success/failure, 200/401/403, forged role headers, concurrent requests, session behavior, and endpoints not matching the matcher.
10. Review permissions when credentials/roles are revoked, multi-node deployments, and cross-request context persistence.

## 15. Self-Check Questions

**Question 1:** A custom Authentication token has <code>principal="admin"</code> but <code>isAuthenticated=false</code>. Can ADMIN permissions be granted yet?  
**Answer:** No. The principal on a request token is a claim; the provider has not yet verified the identity or granted trusted authorities.

**Question 2:** Why not allow any code to call <code>setAuthenticated(true)</code>?  
**Answer:** Because request data could then be promoted to trusted state without going through AuthenticationManager/Provider. Trusted tokens must be created only after verification.

**Question 3:** The provider verifies the code correctly and grants <code>ROLE_LEARNER</code>. Why does <code>/admin</code> still return 403?  
**Answer:** Successful authentication does not imply authorization for every feature. The rule requires <code>ROLE_ADMIN</code>, while the token only holds LEARNER.

**Question 4:** After a successful GET /private, will a second GET /private without headers be recognized automatically?  
**Answer:** Not in the stateless demo. SecurityContext is not saved into HttpSession, so new requests must re-authenticate.

**Question 5:** Does calling <code>SecurityContextHolder.setContext(...)</code> in a custom stateful filter guarantee the session is saved for the next request?  
**Answer:** Not automatically. You must understand SecurityContextRepository, explicit save in Spring Security 6, and the session authentication strategy in use.

**Question 6:** An anonymous token's <code>Authentication.isAuthenticated()</code> can return true. So how should you check for a real user?  
**Answer:** Use Spring Security's authorization/trust resolver, not just the boolean. Anonymous tokens have special semantics and are not equivalent to a verified user.

**Remember:** A custom Authentication token is **an in-server state model**. Clients may only create **unauthenticated** requests; only the <code>AuthenticationProvider</code> verifies evidence and produces a trusted result with server-granted authorities. SecurityContext holds the result per stateless/stateful policy, while authorization decides whether each endpoint is permitted.
