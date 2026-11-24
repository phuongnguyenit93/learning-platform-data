# Distinguishing Unauthenticated, Authentication Failed, and Insufficient Permissions in Spring Security

> **Scope:** Spring Security on HTTP applications, with Java 17+, Spring Boot 3.x, and Spring Security 6.x (Servlet stack) examples. Specific status codes depend on HTTP Basic, form login, Bearer token mechanisms, and application configuration.

## 1. Distinguishing the Three Scenarios

**Authentication** answers "Who is sending the request and is the identity proof valid?". **Authorization** answers "Is that identity allowed to perform this operation on this resource?".

| Scenario | Essence | Example | Common response for HTTP Basic/Bearer APIs |
| --- | --- | --- | --- |
| **Unauthenticated** | There is no valid authenticated identity for the current request. The client may not have provided credentials or the login session has expired. | Calling `GET /api/account` without `Authorization` or a session. | **401 Unauthorized**, initiating authentication. |
| **Authentication failed** | Authentication was attempted but the credentials were not accepted; no trusted identity was created. | Wrong password, expired/invalid-signature Bearer token, locked account. | Usually **401 Unauthorized**; form login may redirect back to the login page showing an error. |
| **Insufficient permissions** (*authenticated but forbidden*) | Authentication succeeded, but permissions/roles/scopes or access policies do not allow the operation. | A user with `ROLE_USER` accessing an endpoint requiring `ROLE_ADMIN`. | Usually **403 Forbidden**. |

**Key takeaway:** "Unauthenticated" and "authentication failed" can both receive **401**, but they differ in whether the client **has not sent proof** or **has sent invalid proof**. "Insufficient permissions" is a matter of the **authorization** step, typically occurring after authentication has succeeded. **You cannot infer the exact cause from the HTTP status code alone.**

### 1.1. Understanding 401, 403, and Login Redirects

- **401 Unauthorized**: the traditional HTTP name contains the word "Unauthorized", but its practical meaning is **missing valid authentication credentials** for a resource that requires authentication. HTTP Basic/Bearer responses usually also include `WWW-Authenticate` to tell the client which authentication mechanism to use.
- **403 Forbidden**: the server refuses to fulfill the request. A common case is that the user is logged in but lacks a role/scope. However, **403 does not automatically prove a missing role**: CSRF protection, `denyAll()`, or other policies can also produce 403.
- **302 Found** or an equivalent redirect: for websites using form login, unauthenticated users are usually redirected to `/login`, while failed logins are usually redirected to `/login?error`. After the browser follows the redirect, the final page may return 200, so you must inspect each request in the Network tab.
- **200 OK**: the endpoint is allowed and processed successfully; public endpoints can return 200 even when unauthenticated.

For example, `GET /admin` without credentials and `GET /admin` with an invalid token can both return 401 on an API. `GET /admin` using a valid account that only has the USER role is usually 403. You should not equate "wrong login" with "insufficient permissions".

## 2. Spring Security Components Involved in Processing

In a **Servlet SecurityFilterChain**, the typical flow consists of:

1. An **Authentication filter** such as `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, or `BearerTokenAuthenticationFilter` extracts credentials from the request and calls `AuthenticationManager`/`AuthenticationProvider` to authenticate.
2. When authentication succeeds, an `Authentication` object containing the principal and authorities is placed into the `SecurityContext`.
3. If not logged in, `AnonymousAuthenticationFilter` may add an **`AnonymousAuthenticationToken`** representing a guest. Therefore, **`Authentication != null` does not mean the user is truly authenticated**.
4. **`AuthorizationFilter`** applies rules such as `authenticated()`, `hasRole(...)`, `hasAuthority(...)`; when access is denied, an `AccessDeniedException` is typically thrown.
5. **`ExceptionTranslationFilter`** handles `AuthenticationException` and `AccessDeniedException` thrown in the filter chain after it:
   - Unauthenticated/anonymous or encountering `AuthenticationException`: invokes **`AuthenticationEntryPoint`** to initiate authentication, usually 401 or a login redirect.
   - Authenticated but encountering `AccessDeniedException`: invokes **`AccessDeniedHandler`**, usually returning 403.

Conceptual diagram:

```text
HTTP request
  |
  v
Authentication filter (when credentials are present)
  |-- invalid credentials --> authentication failure handler / entry point
  |                           (Basic/Bearer usually 401; form usually redirect)
  v
SecurityContext (authenticated or anonymous)
  |
  v
AuthorizationFilter evaluates rules
  |-- allowed ----------------------> Endpoint
  |
  +-- denied --> ExceptionTranslationFilter
                    |-- anonymous/unauthenticated --> AuthenticationEntryPoint
                    |                                 (usually 401 or redirect)
                    +-- authenticated -------------> AccessDeniedHandler
                                                     (usually 403)
```

**Important nuance:** Authentication filters often handle authentication failures directly inside the filter itself. For instance, `UsernamePasswordAuthenticationFilter` uses an `AuthenticationFailureHandler`, while HTTP Basic can directly invoke `AuthenticationEntryPoint`. Therefore, saying "all password errors are caught by `ExceptionTranslationFilter`" is inaccurate. That filter mainly translates security exceptions propagated to it from downstream processing into appropriate responses.

### 2.1. Exceptions and Diagnostic Signals

| Exception or mechanism | Common meaning | Branch to inspect |
| --- | --- | --- |
| `BadCredentialsException` | Credentials were not accepted. | Authentication failed; usually 401 on APIs. |
| `UsernameNotFoundException`, `LockedException`, `DisabledException`, `CredentialsExpiredException` | Conditions that can cause authentication to fail; some providers intentionally hide the specific reason. | Authentication; do not disclose account details to the client. |
| `InvalidBearerTokenException` | Token is invalid / no longer accepted. | Bearer authentication; usually 401. |
| `AccessDeniedException` | Resource protection rule does not allow access. | Check whether anonymous or authenticated, then inspect rules/policies. |
| CSRF token error | State-changing request without a valid CSRF token. | May return 403 even without a missing role. |

**Do not configure a single shared handler that always returns 403 for all `AuthenticationException` and `AccessDeniedException`**: doing so prevents the client from distinguishing when authentication is needed versus when access permissions are needed.

## 3. Java 17+ Example for Directly Observing 401 and 403

Use a Spring Boot 3.x application with compatible Java/Boot plugins. Required Gradle dependencies (add to the project's `dependencies` block):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create the file `src/main/java/demo/security/SecurityStatusDemoApplication.java`:

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityStatusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityStatusDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/account")
    String accountEndpoint() {
        return "account";
    }

    @GetMapping("/api/admin")
    String adminEndpoint() {
        return "admin";
    }
}
```

Here `httpBasic()` enables HTTP Basic authentication; `formLogin(...disable)` prevents form login redirects from masking API status codes. `hasRole("ADMIN")` requires the granted authority **`ROLE_ADMIN`**; `User.roles("ADMIN")` automatically creates that authority. Reader only has `ROLE_USER`, while admin has `ROLE_ADMIN`. `BCryptPasswordEncoder` hashes passwords when creating users; these hardcoded accounts are **for learning only** and must not be hardcoded into real applications.

Run the application (from a Boot project configured with the plugins and versions):

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. Once the application is running on `localhost:8080`, open a Bash terminal with `curl` and call each in turn:

```bash
# (1) No credentials
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/account

# (2) Credentials provided but wrong password
curl -s -o /dev/null -w '%{http_code}\n' -u reader:wrong http://localhost:8080/api/account

# (3) Reader authenticated successfully, but missing ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 http://localhost:8080/api/admin

# (4) Admin has the right ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin123 http://localhost:8080/api/admin

# (5) Public endpoint
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
```

Expected output, with each command printing one status code line:

```text
401
401
403
200
200
```

**Explanation:** (1) authentication not attempted; (2) attempted but wrong; neither has a valid identity, so 401. (3) reader was authenticated, but lacks the role, so 403. (4) has the required role, so enters the endpoint; (5) `permitAll()`, so no login is needed.

View full headers with `curl -i http://localhost:8080/api/account`; with HTTP Basic, the 401 response usually includes `WWW-Authenticate: Basic ...`. Actual headers depend on configuration/client. The requests in the example all use `GET`, so CSRF did not need to be disabled; when adding state-changing requests via cookies/sessions, handle CSRF properly.

## 4. Why Does the Authentication Mechanism Change the Result?

### 4.1. HTTP Basic and APIs

- Not sending credentials to a resource requiring login → usually **401**.
- Sending a wrong username/password → usually **401**, because authentication fails before a valid principal exists.
- Correct username/password with only `ROLE_USER`, while the endpoint requires `ROLE_ADMIN` → usually **403**.
- HTTP Basic resends credentials on every request; **HTTPS is mandatory** in production systems.

### 4.2. Form Login on Websites

1. The browser visits a private page while unauthenticated. `LoginUrlAuthenticationEntryPoint` usually redirects the browser to `/login` (HTTP redirect).
2. The user submits an invalid form. `UsernamePasswordAuthenticationFilter` calls `AuthenticationFailureHandler`; the default configuration usually redirects to `/login?error`.
3. Login succeeds, but the user lacks the role: `AccessDeniedHandler` usually returns 403 or displays an access-denied page.

Therefore, **do not mechanically apply "unauthenticated = 401" to form login**. A redirect can be the expected behavior. In DevTools, inspect the original request's status, the `Location` URL, and the final response after redirects.

### 4.3. OAuth2 Resource Server with Bearer Tokens

| Input | Authentication outcome | Common response |
| --- | --- | --- |
| No Bearer token sent to a protected endpoint | Unauthenticated | **401**; may include `WWW-Authenticate: Bearer`. |
| Expired, invalid-signature, or rejected token | Authentication failed | **401**, usually with Bearer error `invalid_token`. |
| Valid token, but missing required scope/authority | Authenticated but insufficient permissions | **403**, may include `insufficient_scope` in the Bearer challenge. |
| Valid token, sufficient scope/authority | Allowed to proceed | Endpoint returns status based on processing result. |

Detailed `WWW-Authenticate` headers depend on `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler`, and the Resource Server configuration. **A valid JWT does not mean permission to call every API**: authentication only proves identity; authorization must still check scopes/authorities.

## 5. Common Diagnostic Mistakes and How to Handle Them

**Mistake 1 — checking anonymous state incorrectly.** `AnonymousAuthenticationToken` can exist in `SecurityContext`, and even `isAuthenticated()` returns true. Checking only `authentication != null` or only `isAuthenticated()` can misclassify an anonymous user as logged in. When customizing, use reliable mechanisms such as `AuthenticationTrustResolver` or Spring Security's authorization rules.

**Mistake 2 — confusing `hasRole` with `hasAuthority`.** `hasRole("ADMIN")` matches `ROLE_ADMIN` by default; `hasAuthority("ADMIN")` matches `ADMIN` literally. If the provider grants a different authority than expected, an authenticated user still gets 403. Bearer JWTs typically map scopes to authorities like `SCOPE_reports.read`; do not confuse them with roles.

**Mistake 3 — attributing every 403 to roles.** If `GET` works but `POST` to the same resource returns 403, check the CSRF token, HTTP method matchers, and method security. Do not unconditionally disable CSRF to "fix the error"; understand whether the application uses cookies/sessions or header tokens and the CSRF threat model.

**Mistake 4 — always converting 401 to 403 or vice versa.** An API client receiving 401 can usually prompt for login or send valid credentials; receiving 403 due to a missing role will not be solved by logging in again with the same permissions. Converting between them causes UI login/refresh-token loops and hides configuration bugs.

**Mistake 5 — checking only the final page's status after redirects.** Form login triggers chained requests; a login screen returning 200 does not prove the request to the protected page succeeded. Inspect each request and its `Location` header.

**Mistake 6 — leaking sensitive causes.** For failed logins, return a generic "Invalid login credentials" rather than "Username exists, wrong password"; never log plaintext passwords, raw Bearer tokens, or session secrets. Safely log request ID, endpoint, exception type, and authorization decision for diagnostics.

### Ordered Checklist

1. Identify the **authentication mechanism** (Basic, form/session, Bearer) and whether the request actually includes credentials.
2. Check **whether authentication succeeded or failed**: provider, encoder, account status, token expiry/signature/issuer/audience according to your system.
3. If authentication succeeded, inspect the actual **principal and granted authorities**, rather than only reading the roles table in the DB.
4. Check **access rules**: `requestMatchers` ordering, HTTP method, URL, `authenticated()`, `hasRole`, `hasAuthority`, and `@PreAuthorize` if method security is enabled.
5. For unexpected 403s, also check **CSRF** and other policies.
6. Check which handler is producing the response: `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, `AccessDeniedHandler`; for form login, inspect the redirects.

## 6. Scenario Exercises

**A.** Request without an Authorization header to an HTTP Basic endpoint requiring `ROLE_ADMIN`. → **Unauthenticated**, usually 401. `AuthorizationFilter` may deny it; `ExceptionTranslationFilter` detects anonymous and initiates authentication.

**B.** Request sending the wrong password to call an API allowing any authenticated user. → **Authentication failed**, usually 401. Sending credentials does not mean the credentials are valid.

**C.** User with `ROLE_USER` properly logged in, calling an endpoint requiring `ROLE_ADMIN`. → **Insufficient permissions**, usually 403; changing the password will not fix a missing authority.

**D.** User is logged in, `GET /profile` returns 200, but `POST /profile` returns 403. → **Insufficient information to conclude a missing role**. Check the CSRF token, HTTP-method rules, and method security.

**E.** JWT with a valid signature but missing the `reports.write` scope to write a report. → **Authenticated, insufficient permissions**, usually 403. If the signature were invalid or expired, that would be an **authentication failure**, usually 401.

## 7. Key Takeaways

Decision workflow: **Is there a valid authenticated identity yet?** If not, distinguish **no credentials sent** from **invalid credentials** for appropriate handling/business logic/logging; APIs typically respond with 401. If there is a valid identity, check roles/scopes/policies; insufficient permissions usually yield 403. When encountering an unexplained 403, also check CSRF and other rules. **Status codes are symptoms of the processing mechanism, not a substitute for root-cause analysis.**

### Official Documentation

- [SecurityFilterChain and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Authorize HttpServletRequests, hasRole, and hasAuthority](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [OAuth2 Resource Server with Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/)
- [Spring Security FAQ (403 errors with POST/CSRF)](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html)
