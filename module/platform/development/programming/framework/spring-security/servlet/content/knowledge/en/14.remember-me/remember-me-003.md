# TokenBasedRememberMeServices and Signed Cookie Contents in Spring Security Servlet

> **Scope:** Spring Security 6 on the Servlet stack, Java 17+, **Remember Me** flow when the application uses form login. The focus is `TokenBasedRememberMeServices`, the **signed but unencrypted** remember-me cookie, token creation/verification/`Authentication` restoration steps, expiration, and revocation limitations. Includes a runnable Spring Boot 3.3.5 sample application to observe cookies and `authenticated()` vs. `fullyAuthenticated()` authorization.

## 1. What Problem Does Remember Me Solve?

In a web application, an **HTTP session** usually holds the logged-in user's state. When the session expires or the browser loses its session cookie, users normally have to re-enter their username and password. **Remember Me** lets the browser send a cookie that outlives the session so the application can re-identify the account without requiring interactive login on every visit.

A typical experience:

1. The user opens the login page and enters username/password.
2. The user **explicitly checks** the “Remember me” box on the form.
3. Spring Security authenticates the account successfully and sends an additional signed `remember-me` cookie.
4. When the login session is lost or expires, the browser still retains and sends the remember-me cookie to the website.
5. The security filter verifies the cookie using a server-side secret key and current account data.
6. If the cookie is valid, the system establishes a **remember-me authentication** in `SecurityContext` for the request. The user can access endpoints requiring `authenticated()`, while sensitive actions can require interactive re-login via `fullyAuthenticated()`.

**Remember Me differs from a session:** a `JSESSIONID` typically references server-side session state; a remember-me cookie in the token-based mechanism carries data whose **signature the server can verify on its own**. That cookie is not an HTTP session ID, not a CSRF token, and not a JWT/OAuth2 access token.

**Remember Me does not replace initial authentication:** the cookie is normally issued only after the user has logged in successfully through the standard mechanism and opted in (unless `alwaysRemember` is configured). If a user has never logged in, submitting a username by itself is insufficient to create a trusted remember-me authentication.

## 2. Placing TokenBasedRememberMeServices in the Servlet Filter Chain

In Spring Security Servlet, the participating components have distinct roles:

| Component | Responsibility |
| --- | --- |
| `UsernamePasswordAuthenticationFilter` | Reads `POST /login`, creates the username/password request, and authenticates via `AuthenticationManager` |
| `RememberMeServices` | Interface for `loginSuccess`, `loginFail`, `autoLogin`, and remember-me handling |
| **`TokenBasedRememberMeServices`** | Issues cookies with expiration and signature; reads cookies and verifies expiration/signature against user data and secret key |
| `RememberMeAuthenticationFilter` | When no suitable authentication exists in the context yet, tries `RememberMeServices.autoLogin(...)` to restore identity from the cookie |
| `RememberMeAuthenticationToken` | `Authentication` object representing a remember-me login |
| `RememberMeAuthenticationProvider` | Verifies that the remember-me token was created under a key trusted by the provider |
| `UserDetailsService` | Loads the account, encoded password, roles, and current status; supports cookie verification |
| `SecurityContextRepository` | Saves/loads context per application policy; separate from cookie validity |
| `AuthorizationFilter` | Applies `authenticated()`, `fullyAuthenticated()`, `hasRole(...)` rules after identity is established |

Conceptual diagram:

```text
Interactive login
  Browser POST /login + username/password + _csrf + remember-me=true
       |
       v
UsernamePasswordAuthenticationFilter
       |
       v
AuthenticationManager / DaoAuthenticationProvider
       |
       +-- Failure -> failure handler, no valid remember-me created
       |
       +-- Success
              |
              v
      RememberMeServices.loginSuccess(...)
              |
              v
      TokenBasedRememberMeServices creates signed cookie
              |
              v
      Set-Cookie: remember-me=...; Max-Age=...
              |
              v
      Browser stores cookie according to browser attributes

Subsequent visit, when no session authentication remains
  GET /account + Cookie: remember-me=...
       |
       v
RememberMeAuthenticationFilter
       |
       v
TokenBasedRememberMeServices.autoLogin(...)
       |  parse fields, verify expiration, user, and signature
       |
       +-- Invalid -> clear/reject cookie, continue as anonymous
       |
       +-- Valid -> RememberMeAuthenticationToken
                              |
                              v
                  RememberMeAuthenticationProvider
                              |
                              v
                  Request SecurityContext
                              |
                              v
                  AuthorizationFilter checks permissions
```

The exact path can vary by version, request matchers, filter configuration, and `SecurityContextRepository`. Yet the core principle does not change: **remember-me authentication must be verified on the server**—never trust a cookie merely because it contains a username or readable Base64.

## 3. Why Is It Called a “Signed” Cookie?

`TokenBasedRememberMeServices` typically uses a **secret-keyed digest signature** to detect cookie tampering. The cookie payload is Base64-encoded so it fits cleanly into an HTTP cookie, but Base64 does not hide its contents.

In the modern token-based format, the content before Base64 encoding generally has this structure:

```text
username : expirationTime : algorithmName : signatureHex
```

Where:

- **`username`**: the remembered user's name. Anyone holding the cookie can read it after Base64 decoding.
- **`expirationTime`**: server-established expiration instant, typically represented in **Unix epoch milliseconds** inside the token. It governs server-side expiration checks, not merely the browser's `Max-Age` attribute.
- **`algorithmName`**: name of the digest algorithm used to compute the signature, such as SHA-256 in modern configurations.
- **`signatureHex`**: digest string computed from the username, expiration, **stored account password**, and application **secret key**.

An illustrative formula following the `TokenBasedRememberMeServices` model:

```text
signatureHex =
    HEX( DIGEST_algorithm(
        username + ":" +
        expirationTime + ":" +
        userDetails.getPassword() + ":" +
        serverSecretKey
    ))

cookieValue =
    Base64(username + ":" +
           expirationTime + ":" +
           algorithmName + ":" +
           signatureHex)
```

This is a **conceptual teaching formula**, not replacement code for Spring Security. Older cookie/token generations differ in field count or algorithm selection; when reading code or operating an app, verify the Spring Security version and the class issuing the cookie. Do not hardcode a four-field parser in a controller for “quick authentication”.

**Important:** `userDetails.getPassword()` normally returns the **encoded password hash** in the database, not the user's plaintext password. That hash participates in computing the signature on the server, yet **does not appear directly as a cookie field**. The cookie also **does not need** to contain the secret key.

### Signed Does Not Mean Encrypted

| Property | Signed token-based cookie |
| --- | --- |
| Can it be Base64-decoded to reveal username/expiration? | **Yes** |
| Is it protected against arbitrary tampering with `expirationTime` or username? | **Yes**, if the signature/secret is protected and a sound algorithm is used |
| Does the cookie hide the username from someone holding the cookie? | **No** |
| Is the cookie a JWT? | **No**; it has its own format and verifier |
| Is the cookie single-use? | **No**; it can be sent repeatedly while still valid |
| Can a stolen cookie be replayed? | **Yes**; a signature does not stop replay of an intact cookie |
| Can a single cookie be reliably revoked solely by logging out? | Unreliable if a copy of the cookie was stolen and has not expired |

A security nuance: this is a **Spring Security keyed digest mechanism**, so do not loosely call it a “JWT signature” or “standard HMAC” without inspecting the exact implementation. Applications should **use the framework's classes** instead of rolling custom algorithms, and especially avoid MD5 for new tokens.

## 4. How the Cookie Is Created on Successful Login

With form login and remember-me enabled, the flow typically involves:

1. The browser displays a form with `username`, `password`, and `remember-me` checkbox fields. The POST form must also submit a valid CSRF token.
2. `UsernamePasswordAuthenticationFilter` calls `AuthenticationManager.authenticate(...)`. The provider verifies the password hash, account flags, and authorities.
3. Upon authentication success, `RememberMeServices.loginSuccess(request, response, successfulAuthentication)` is invoked as part of the success path.
4. The remember-me service checks whether the user requested remember-me. By default the choice is determined by the `remember-me` parameter, unless `alwaysRemember` is configured.
5. `TokenBasedRememberMeServices` computes `expirationTime`, chooses the configured signing algorithm, fetches the password hash from `UserDetailsService`, computes the signature, and writes the token into the cookie.
6. The response emits `Set-Cookie` with the configured name and attributes. The browser retains the cookie for matching domain/path requests.
7. Requests within the current session may continue using `UsernamePasswordAuthenticationToken` from form login; remember-me **does not have to be used immediately** while the session still holds an authentication.

Illustrative response example (secret value redacted):

```http
HTTP/1.1 302 Found
Set-Cookie: remember-me=<base64-token>; Max-Age=86400; Path=/; HttpOnly
Location: /
```

This is **not a fixed transcript**: `JSESSIONID` may also be present, the `Location` header can differ due to saved requests or success handlers, and `Secure`/`SameSite` attributes depend on HTTPS, reverse proxies, server config, and cookie settings. Never copy real remember-me values from production into documentation, logs, or tickets.

### Checkbox vs. alwaysRemember

Normally the user must **check** the remember-me box. Leaving it unchecked still allows normal login/session creation, yet **no new remember-me cookie is issued**.

Some apps configure `alwaysRemember(true)`: then remember-me is issued on every successful login regardless of the checkbox. That decision impacts privacy on shared devices; **do not enable it without product requirements, user policy, and security review**.

## 5. How RememberMeAuthenticationFilter Validates the Cookie

When the request's security context lacks a suitable identity, `RememberMeAuthenticationFilter` calls `rememberMeServices.autoLogin(request, response)`. With `TokenBasedRememberMeServices`, the core logical steps are:

1. Read the cookie with the configured name, usually `remember-me`.
2. Base64-decode and extract the fields according to the format supported by the class.
3. Check whether `expirationTime` has passed; an expired cookie must be rejected even if the browser still sends it.
4. Load `UserDetails` by username using `UserDetailsService`. Non-existent, disabled, locked, or ineligible accounts are rejected per the corresponding validation checks.
5. Recompute the signature using the cookie fields, the **current password hash** in `UserDetails`, and the **current secret key**.
6. Compare against the signature in the cookie; if data was modified, the secret key differs, or the password hash changed so the signatures do not match, reject the cookie.
7. Build a `RememberMeAuthenticationToken`, verified by `RememberMeAuthenticationProvider` and the trusted authentication flow under the matching key.
8. Place the result in `SecurityContext` for the request and proceed to authorization.

If the cookie is invalid, Spring Security usually clears it on the response when possible and the request continues unauthenticated. An endpoint requiring `authenticated()` may initiate form login again; a `permitAll()` endpoint remains accessible as anonymous.

### Why Reload UserDetails?

A signed cookie **should not carry a permanent snapshot of permissions**. After the cookie is issued, an account might be locked, deleted, have its password changed, or have roles modified. Fetching the current `UserDetails` lets the app apply trustworthy status and authorities at restoration time.

This has two consequences:

- **Password hash changes** typically invalidate old cookies, even if the cookie expiration timestamp has not passed.
- **Role changes** affect the authorities of a new remember-me authentication because current authorities are loaded. With a user cache, you must understand cache invalidation to avoid stale data.

**Do not rely on editing roles inside the cookie** to grant permissions—token-based cookies are not where the client defines authorities.

## 6. Authenticated and Fully Authenticated Are Not the Same

Remember-me authentication typically has `isAuthenticated()==true`, yet Spring Security distinguishes **full interactive login** from **restored via remember-me** through the trust resolver.

Authorization rules:

| Rule | Username/password just logged in | Restored via remember-me |
| --- | --- | --- |
| `permitAll()` | Allowed | Allowed |
| `authenticated()` | Allowed | **Usually allowed** if the cookie is valid |
| `fullyAuthenticated()` | Allowed | **No**; requires interactive re-login |
| `hasRole("USER")` | If user has role USER | If user has role USER, still allowed depending on the specific rule |
| `denyAll()` | Denied | Denied |

Why is `fullyAuthenticated()` needed? A remember-me cookie is **longer-lived evidence**, easier to steal on shared devices. For tasks like changing passwords, adding payment methods, or sensitive administration, apps usually require users to provide full authentication again.

Example:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/account/sensitive").fullyAuthenticated()
        .requestMatchers("/account").authenticated()
        .anyRequest().permitAll());
```

This is a Java fragment inside `SecurityFilterChain`, not a standalone runnable class. With form login, when a user with only remember-me authentication accesses `/account/sensitive`, `ExceptionTranslationFilter` normally prompts for interactive re-login; do not assume it always returns 403 instead of redirecting, because the entry point and security configuration determine the HTTP response.

An important note: `fullyAuthenticated()` is a distinction within Spring Security's authentication model; **it does not replace MFA, re-authentication timeouts, or high-risk transaction verification**. For sensitive operations, concrete security requirements may be stricter.

## 7. Token-Based Remember-me vs. Persistent Token Repository

Spring Security offers two common remember-me approaches:

| Aspect | `TokenBasedRememberMeServices` | `PersistentTokenBasedRememberMeServices` |
| --- | --- | --- |
| Basis | Cookie with data and signature depending on server key/password hash | Cookie referencing series/token in a server-side persistent store |
| Separate token database needed for verification? | **Not required**, needs `UserDetailsService` | **Yes**, needs `PersistentTokenRepository` |
| Cookie check | Expiry + signature + current user | Match token/series against the data store |
| Revoke **a single device** | Hard; no independent token record per device | Can delete the corresponding token/series |
| Detect unauthorized token use | Limited because the cookie can be replayed | Supports token rotation and mismatch detection depending on implementation |
| Best fit | Simple systems with low per-device revocation needs | Systems needing stricter remembered-session/device management |

`TokenBasedRememberMeServices` is **not an OAuth2 access token** and `PersistentTokenBasedRememberMeServices` is **not a JWT service**. Both are Spring Security Servlet remember-me mechanisms for specific use cases and threat models.

**Design decision:** if you need “log out from all devices”, “revoke a specific lost device”, or token reuse detection, a persistent-token repository and device management mechanism may fit better. With a signed token-based cookie, there is no default database row per cookie to delete individually.

## 8. Expiration, Signatures, Key Rotation, and Logout

### 8.1. Two Types of Expiration to Distinguish

A remember-me cookie has:

- **Server-side expiration inside the signed payload** (`expirationTime`). Once expired, the server rejects it; modifying the timestamp to extend it invalidates the signature.
- **Browser cookie expiration** (`Max-Age` or `Expires`). The browser decides whether to keep sending the cookie.

Do not inspect only `Max-Age` and conclude the server will definitely accept the cookie. The server still checks the signed expiration, username, and signature.

In the hands-on example, we set `tokenValiditySeconds(86400)`, equal to **24 hours**. This is a demo value; production must pick TTL based on risk, account sensitivity, revocability, and shared devices. Do not set an excessively long lifetime just so users log in less often.

### 8.2. Password Hash Changes

Because the signature depends on `UserDetails.getPassword()`, changing a password or its hash can cause previously issued cookies to fail signature verification.

An easily overlooked detail: BCrypt uses a salt. If a demo app **regenerates the hash from the same plaintext on every startup**, the hash will normally differ after restart, making old remember-me cookies **invalid even though the demo password did not change**. In real products, password hashes must be stored durably in a database rather than regenerated on each startup.

### 8.3. Secret Key Changes

`TokenBasedRememberMeServices` requires a **stable and sufficiently secret server key**. If an app runs multiple instances, those instances must share the **same key** (or an intentional versioning/rotation strategy). If each node uses a different key, users may fail remember-me when requests route to another node.

- Exposing the key allows attackers to forge cookies under certain conditions; treat it as a critical secret.
- Key rotation can **invalidate all cookies signed with the old key**. That can be desirable after a leak, yet affects UX for all users.
- Never commit secrets to source, write them to logs, or pass them as browser query parameters.
- Provide the key via a secrets manager or deployment environment with clear rotation/restart procedures.

### 8.4. Does Logout Revoke the Cookie?

In a standard logout flow, Spring Security invokes logout handlers (including the remember-me handler if configured), clearing the browser cookie via the appropriate response header.

However, **clearing the cookie on the current browser cannot revoke a stolen copy held elsewhere** if that token-based cookie has not expired and the user/key has not changed. This is the **replay** risk of bearer-style remember-me cookies. To revoke a specific cookie immediately, consider a persistent token store or a design with a revocation record.

## 9. Runnable Application Example: Java 17 + Spring Security 6

The Spring Boot 3.3.5 project below uses an in-memory `UserDetailsService` and default form login. When the **Remember me** checkbox is ticked, `rememberMe(...)` creates **`TokenBasedRememberMeServices` by default** for username/password. The configuration shares the key with the `RememberMeAuthenticationProvider` created by `RememberMeConfigurer`, avoiding wiring an incompatible provider manually.

Endpoints:

- `GET /`: public, returns instructional text.
- `GET /account`: requires only `authenticated()`.
- `GET /account/sensitive`: requires `fullyAuthenticated()`, denying/prompting for re-login if only remember-me authentication is present.
- `GET /logout`: not intended for logout via GET; **default Spring Security logout is CSRF-protected and uses the appropriate action**.

Demo account: `lan` / `demo123`, role `USER`. Do not use this account in production.

### 9.1. Directory Structure

```text
remember-me-demo/
├── pom.xml
└── src/main/java/example/remember/
    ├── RememberMeApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>remember-me-demo</artifactId>
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
```

### 9.3. RememberMeApplication.java

```java
package example.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.remember;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        String key = System.getenv("REMEMBER_ME_KEY");
        if (key == null || key.length() < 32) {
            throw new IllegalStateException(
                    "REMEMBER_ME_KEY must be a stable secret of at least 32 characters");
        }

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/account/sensitive").fullyAuthenticated()
                .requestMatchers("/account").authenticated()
                .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());

        // With UserDetailsService present, this config uses
        // TokenBasedRememberMeServices as the default remember-me mechanism.
        // The key is also used to register the provider verifying remember-me tokens.
        http.rememberMe(remember -> remember
                .key(key)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(24 * 60 * 60)
        );

        // CSRF remains default. Form POST /login and logout require a token.
        return http.build();
    }
}
```

**Explanation of key choices:**

1. `REMEMBER_ME_KEY` is read from an **environment variable**, not hardcoded. Its value should remain stable across restarts and identical across instances. The “at least 32 characters” constraint in the example is a demo rule to prevent very short secrets; production requires a randomly generated key with high entropy, not merely a predictable 32-character string.
2. `rememberMe(...)` specifies `userDetailsService(users)` and `key(key)`: Spring Security configures compatible `TokenBasedRememberMeServices` and `RememberMeAuthenticationProvider`. Do not add a second `new TokenBasedRememberMeServices` using a different key.
3. `rememberMeParameter("remember-me")` is the form checkbox/field name, distinct from `rememberMeCookieName("remember-me")` which is the cookie name sent to the browser. Both names happen to match in the demo but belong to two different channels.
4. `tokenValiditySeconds(24 * 60 * 60)` sets the remember-me token lifetime here to **24 hours**.
5. `authenticated()` on `/account` accepts valid remember-me authentication, whereas `fullyAuthenticated()` on `/account/sensitive` requires the user to re-authenticate per policy.
6. `formLogin(Customizer.withDefaults())` provides the default login page and handles form POSTs. We do not build a custom POST controller receiving passwords. Never disable CSRF.
7. The demo user's BCrypt hash **is regenerated on restart**; because the signature relies on the hash, cookies from an earlier run normally become invalid. Real account stores must persist password hashes durably.

### 9.5. DemoController.java

```java
package example.remember;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home:open /account, then sign in with remember-me";
    }

    @GetMapping("/account")
    public String account(Authentication auth) {
        return "user=" + auth.getName()
                + ";authenticationType=" + auth.getClass().getSimpleName();
    }

    @GetMapping("/account/sensitive")
    public String sensitive(Authentication auth) {
        return "sensitive:" + auth.getName();
    }
}
```

The response body intentionally reveals the **Authentication class** so you can observe the difference in the lab. Do not arbitrarily expose full Authentication objects, credentials, claims, or sensitive details in production responses.

### 9.6. Running the Application

In a POSIX/macOS/Linux shell, set a dedicated demo secret, then start:

```bash
export REMEMBER_ME_KEY="demo-change-this-to-a-long-random-secret-2026"
mvn spring-boot:run
```

The value above is **for localhost only**; never use it as a key in a real system. On PowerShell, set the environment variable using PowerShell syntax before running Maven.

Once started, Tomcat listens by default at `http://localhost:8080`. In production you must use **HTTPS** to protect passwords, session cookies, and remember-me cookies from interception on the wire.

### 9.7. Testing Remember Me in the Browser

1. Open a new private browser window so no old session/cookies exist.
2. Visit `http://localhost:8080/account`. Because you are not logged in, the browser is typically redirected to `/login`.
3. On the default login page with remember-me enabled, tick the **Remember me** checkbox, enter `lan` / `demo123`, and submit the form. Spring Security handles the CSRF token on the generated form.
4. Once logged in, navigate to `/account`. Typical output:

```text
user=lan;authenticationType=UsernamePasswordAuthenticationToken
```

5. Open Developer Tools → Storage/Cookies. You can see both the session cookie (such as `JSESSIONID`) and `remember-me`; do not copy/share full cookie values.
6. **Delete only the `JSESSIONID` cookie**, keep the `remember-me` cookie, and do not click Logout. Refresh `/account`.
7. If the cookie is valid and the remember-me components work, the typical result changes to:

```text
user=lan;authenticationType=RememberMeAuthenticationToken
```

8. Access `/account/sensitive` while restored only via remember-me. The `fullyAuthenticated()` rule requires interactive re-login; with form login, you typically see a redirect to login instead of `sensitive:lan`.
9. After logging in interactively again, visiting `/account/sensitive` returns:

```text
sensitive:lan
```

**Distinguish clearly:** a browser still holding a remember-me cookie after `JSESSIONID` is removed does not mean the browser “logged out”. Remember-me is designed to re-identify the user. If you want to test failure due to an expired or tampered cookie, use a separate test environment and avoid modifying production cookies.

### 9.8. Why Not Use curl POST /login With Only Username/Password?

Spring Security Servlet normally enables CSRF for form login. A `POST /login` request needs a **valid CSRF token and the associated session cookie**. A command like:

```bash
# Missing CSRF token; usually rejected before login:
curl -i -d 'username=lan&password=demo123&remember-me=on' \
  http://localhost:8080/login
```

normally **does not** succeed when CSRF is enabled. Never disable CSRF site-wide just to run a demo. The browser-generated form lets you test the proper flow and inspect cookies most easily.

A complete automated testing approach uses `spring-security-test` + `MockMvc` with CSRF support, then asserts the `Set-Cookie` header, authentication token class, and `fullyAuthenticated()` rules; do not assume `@WithMockUser` generates a real remember-me cookie.

## 10. Reading and Inspecting Cookies: Do's and Don'ts

In a local environment, you can inspect the **cookie name**, `Max-Age`, `Path`, `Secure`, and `HttpOnly` in Developer Tools. To understand the format, you can Base64-decode a **cookie produced by the demo itself**; however, Base64 decoding **does not verify the signature**.

Do not use browser JavaScript via `document.cookie` as a mandatory security test. Remember-me cookies are normally protected with `HttpOnly`, so page JavaScript should not be able to read the value. Developer Tools can still display it to operators on a test machine.

When debugging cookies:

| Symptom | What to check |
| --- | --- |
| No `remember-me` cookie after login | Was the `remember-me` checkbox ticked, did login actually succeed, is remember-me enabled? |
| Cookie appears then disappears after logout | The remember-me logout handler cleared the cookie per policy; expected behavior |
| Cookie exists yet refresh stays anonymous | Expired, key mismatch, password hash changed, account disabled, user service error, domain/path, or browser did not send cookie |
| One node accepts, another node rejects | Nodes may use different secret keys or different user/password data |
| Refresh over HTTPS does not send cookie | Check `Secure`, domain/path, SameSite, reverse proxy, and browser policy |
| Cookie used to work yet becomes invalid after restart | Key randomized again, or in-memory BCrypt password hash regenerated |
| Tampered username/expiration is rejected | Signature check caught the modification; correct behavior |
| Cookie still works after user clicks logout on another machine | Signed tokens have no per-device revocation record by default; assess threat model |
| Can access `/account` yet blocked from `/account/sensitive` | `authenticated()` accepts remember-me, `fullyAuthenticated()` does not |

Never log or attach a **complete signed cookie** to a support ticket: anyone holding a valid cookie can replay it during its lifetime if the system lacks other binding controls.

## 11. Common Security Misconceptions

### “If a cookie is signed, a thief cannot use it”

**False.** A signature prevents modifying contents without knowing the secret, yet **does not prevent replaying an intact valid cookie**. That is why HTTPS, HttpOnly, Secure, bounded TTL, XSS/CSRF defenses, and controls on sensitive actions are critical.

### “Base64 encrypts user information”

**False.** Base64 is trivially reversible. Username, expirationTime, and algorithmName are not secrets protected by encryption; the signature only detects tampering.

### “A remember-me cookie is like a session ID”

**False.** A session ID references server-side state; a token-based remember-me cookie is verified via signature and user data. A remember-me cookie can be accepted even when no active `JSESSIONID` exists.

### “Changing password always keeps old cookies working”

**Incorrect for standard token-based remember-me.** The signature depends on the current password hash; changing the hash normally invalidates old cookies. This is an advantage for bulk revocation, and also why password hashes must be stored stably rather than regenerated at each startup.

### “Logout clearing the cookie means all copies are revoked”

**Not guaranteed.** Logout normally clears the cookie in the current browser, while a stolen copy may remain validly signed until expiration or password/key change. If the app requires per-device revocation, you need a server-side token store and management mechanism.

### “Remember Me is enough to allow changing passwords”

**Not necessarily.** Protect sensitive routes with `fullyAuthenticated()` or proper re-authentication/step-up instead of relying on `authenticated()` for all operations.

### “Because it is signed, CSRF is unnecessary”

**False.** Browsers automatically send cookies (including remember-me cookies) to matching origins. A malicious site can attempt to trigger requests where the browser attaches the cookie, so state-changing actions require CSRF protection per the threat model. A remember-me signature **is not a CSRF token**.

## 12. Production Deployment Considerations

- **Cookies:** restrict `Path` and `Domain` to what is needed; set `Secure` when serving over HTTPS, and use `HttpOnly` and `SameSite` according to the browser model. With TLS termination at a reverse proxy, configure trusted forwarded headers properly so the server detects HTTPS. Avoid setting a broad `Domain` accidentally.
- **Keys:** cryptographically random secret with sufficient entropy, stored in a secrets manager, synchronized across clusters, with a rotation procedure and awareness of impact on live cookies.
- **TTL:** choose a short lifetime proportional to risk; users on shared devices must easily be able to leave Remember me unchecked. Distinguish a 24-hour remember-me from a few-minute login session.
- **Passwords:** store BCrypt/Argon2/PBKDF2 hashes per policy and ensure `UserDetailsService` retrieves stable hashes. Changing the key or hash can invalidate all old tokens.
- **CSRF:** maintain or design proper protection for state-changing operations backed by cookies/sessions; do not blindly disable it assuming signed cookies suffice.
- **XSS:** `HttpOnly` reduces script cookie reading yet does not prevent all XSS harm; apply CSP and proper input/output handling.
- **Account state:** disabled/locked/deleted accounts must not auto-login via old cookies; verify behavior against the actual provider, user checker, and cache.
- **Auditing:** never log raw tokens. Track interactive login, auto-login, failures, logout, password changes, and key rotation safely.
- **Sensitive areas:** use `fullyAuthenticated()` for operations requiring user re-interaction; MFA/recent auth needs stricter rules.
- **Per-device revocation:** if genuinely required, consider `PersistentTokenBasedRememberMeServices` and a token store; plain signed cookies do not allow revoking a single copy easily.
- **Multi-instance:** secret keys and user data must be consistent; if hashes differ across nodes, remember-me behavior becomes unstable.

## 13. Exercises and Knowledge Check

1. **What is `TokenBasedRememberMeServices` used for?** Issuing and verifying signed remember-me cookies based on user, expiry, password hash, and server secret.
2. **Is a token-based cookie encrypted?** Not in the sense of hiding content; it can be Base64-decoded, while the signature detects tampering.
3. **Does the cookie contain the plaintext password or hash as a separate field?** No; the password hash is used server-side to recompute the signature.
4. **What happens if the user does not tick remember-me?** Normally no new cookie is issued, unless `alwaysRemember` is configured.
5. **After deleting `JSESSIONID`, can the remember-me cookie still work?** Yes, if the browser sends an unexpired cookie with a valid signature and user.
6. **Why can a hash change invalidate the cookie?** The signature depends on the current `UserDetails.getPassword()`.
7. **Why does an app restart invalidate demo cookies even when the raw password did not change?** BCrypt generates a new salted hash in the in-memory user store on each startup; the signature used the old hash.
8. **What is the difference between `RememberMeAuthenticationToken` and `UsernamePasswordAuthenticationToken`?** The former is an identity restored via remember-me; the latter typically represents an interactive username/password login.
9. **Are `authenticated()` and `fullyAuthenticated()` equivalent under remember-me?** No; remember-me usually satisfies `authenticated` but does not satisfy `fullyAuthenticated`.
10. **Can we take username/expiry from the cookie and grant authentication directly?** No; you must verify the signature, user status, and Spring Security provider flow.
11. **Does logout revoke all copied cookies?** Not guaranteed; there is no per-device revocation store by default.
12. **What happens when multiple nodes use different keys?** Cookies signed by node A may be rejected by node B; a consistent key or rotation strategy is required.
13. **Why does a signed cookie still need HTTPS?** Because someone stealing the intact cookie can replay it, even without altering the signature.
14. **Is a remember-me cookie a CSRF token?** No; the browser can automatically send the cookie in a CSRF request.

## 14. Operational Checklist

- [ ] Issue cookies only after authenticated login and policy-compliant remember-me opt-in.
- [ ] Use standard `TokenBasedRememberMeServices`/`RememberMeConfigurer` rather than homegrown client-data signing algorithms.
- [ ] Protect the secret key, synchronize across instances, and plan rotation.
- [ ] Set reasonable lifetimes for both signed expiration and browser cookies; test server-side expiration.
- [ ] Use stably stored password hashes rather than random re-hashing on every startup.
- [ ] Verify `RememberMeAuthenticationFilter` and `RememberMeAuthenticationProvider` are wired with the right chain/key.
- [ ] Never treat Base64-decoded username/role data as authentication proof.
- [ ] Protect sensitive URLs with `fullyAuthenticated()` or stronger step-up mechanisms.
- [ ] Enforce HTTPS, appropriate HttpOnly/Secure/SameSite flags, XSS prevention, and CSRF protection.
- [ ] Test missing session cookie with remember-me cookie present, as well as tampered/expired cookies, password changes, and locked accounts.
- [ ] Understand that logout clearing the current cookie does not guarantee revoking stolen token copies.
- [ ] If device management is needed, consider a persistent-token repository and server-side revocation.

**Summary:** `TokenBasedRememberMeServices` issues a **Base64 cookie containing username, expiration, algorithm info, and signature**. The server uses a **secret key + current password hash** to verify the cookie when no session authentication remains. Signatures protect **integrity**, not **confidentiality**, and do not stop **replay** if a cookie is stolen. `RememberMeAuthenticationFilter` creates the remembered identity, while `fullyAuthenticated()` helps require interactive re-login for critical resources.