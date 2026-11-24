# The `Authorization` Header and the HTTP Basic Authentication Flow

## 1. What Problem Does HTTP Basic Solve?

HTTP Basic is a standard HTTP authentication mechanism (RFC 7617): the client sends a username and password in the `Authorization` header so the server can identify who is making the request. It is commonly suited for command-line tools, internal APIs protected by HTTPS, or testing environments. This is an **authentication mechanism**; whether the authenticated user is allowed to access a resource belongs to the **authorization** step.

The core idea: with HTTP Basic, the client constructs the string `username:password`, Base64-encodes the bytes of that string, and sends it with the request. Base64 is only **data encoding, not cryptographic encryption**; anyone who can read the header can decode it back into the login credentials. Therefore, Basic must always be used together with HTTPS/TLS and appropriate password-protection measures.

The two headers serve different roles:

| Header | Direction | Meaning |
| --- | --- | --- |
| `Authorization: Basic …` | Client → server | The client presents login credentials for the current request. |
| `WWW-Authenticate: Basic realm="…"` | Server → client, typically with HTTP 401 | The server announces the supported authentication scheme and prompts the client for credentials. |

`Authorization` does **not** mean the request has already been permitted. The server still has to verify the credentials and check the user's permissions.

## 2. Structure of the `Authorization: Basic` Header

Syntax:

~~~http
Authorization: Basic <base64(username:password)>
~~~

Example with username `user` and password `pass`:

1. Concatenate into the string `user:pass` (the first `:` acts as the username/password separator).
2. Convert the string into bytes using a character encoding agreed upon by both sides.
3. Base64-encode it into `dXNlcjpwYXNz`.
4. Send the header:

~~~http
GET /private HTTP/1.1
Host: example.test
Authorization: Basic dXNlcjpwYXNz
~~~

Decoding the part after the `Basic` keyword yields `user:pass`; the server does **not** compare the raw Base64 string against a password in the database. It splits the username and password and then passes them to the application's credential verification mechanism.

**Easily confused details:**

- `Basic` is the authentication scheme name; the Base64 string follows a space. HTTP header field names are case-insensitive.
- The first colon separates the username and password; the username must not contain `:`, while the password may contain `:`.
- RFC 7617 leaves the default credential encoding open for backward compatibility with legacy systems. The server may specify `charset="UTF-8"` in the `WWW-Authenticate` *challenge* (this is a server-side parameter, not a parameter attached to the credential string); when using non-ASCII characters, both sides must agree on the encoding.
- Base64 neither hides the password nor creates a time-limited or signed login token.

## 3. HTTP Cycle When Credentials Are Missing

Suppose `GET /private` requires login.

~~~http
GET /private HTTP/1.1
Host: localhost:8080
~~~

If the request lacks valid authentication information, the server may respond:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Here, `401 Unauthorized` means **authentication has not succeeded** (the status name is easily confused with authorization). `WWW-Authenticate` is the authentication *challenge*. `realm` is the name of the protection space advertised by the server; `Realm` is only an illustrative value and can be configured differently.

The client may prompt the user for a username/password and resend the request:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic dXNlcjpwYXNz
~~~

Not every client is required to wait for `401`: tools such as cURL can send Basic credentials on the very first request (*preemptive authentication*). A browser may display a login dialog upon receiving the challenge and may retain the credentials for a period of time; that caching behavior should not be treated as a controlled application login session.

## 4. Flow Inside Spring Security (Servlet)

For a Spring MVC application using `SecurityFilterChain` with `httpBasic` enabled, the typical flow is:

1. **The request enters the security filter chain.** Filters run before the controller. If the request has `Authorization: Basic …`, `BasicAuthenticationFilter` processes those credentials.
2. **Create an unauthenticated authentication object.** `BasicAuthenticationFilter` decodes the credentials and creates a `UsernamePasswordAuthenticationToken` containing the username/password, then passes this object to `AuthenticationManager`.
3. **Verify credentials.** `AuthenticationManager` (typically `ProviderManager`) delegates to the appropriate `AuthenticationProvider`. For standard username/password accounts, `DaoAuthenticationProvider` can use `UserDetailsService` to load the user and `PasswordEncoder.matches(...)` to compare the input password with the hashed password.
4. **If valid**, the provider returns an authenticated `Authentication` along with the list of authorities (`GrantedAuthority`). Spring Security places the result into `SecurityContextHolder` for the request and continues the filter chain. `AuthorizationFilter` evaluates access rules; only if allowed is the controller invoked.
5. **If invalid**, the associated security context is cleared and `AuthenticationEntryPoint` handles the failure, typically returning `401` with a Basic challenge. If credentials are absent and the resource requires authentication, `AuthorizationFilter` denies access and `ExceptionTranslationFilter` triggers the entry point to initiate authentication.

Summary diagram (branches may depend on configuration):

~~~text
Client → HTTP request
           │
           ├─ Authorization: Basic ... present
           │    → BasicAuthenticationFilter
           │    → UsernamePasswordAuthenticationToken
           │    → AuthenticationManager / AuthenticationProvider
           │         ├─ Invalid credentials → AuthenticationEntryPoint → 401
           │         └─ Valid → SecurityContextHolder holds Authentication
           │
           └─ No Basic credentials → not authenticated via Basic
                                     (other mechanisms may still apply)
                         │
                         ▼
                  AuthorizationFilter
                     ├─ Allowed → Controller → 2xx
                     ├─ Unauthenticated, login required → 401/challenge
                     └─ Authenticated, insufficient permissions → 403
~~~

It is important to distinguish two questions: **"Who are you?"** is handled by authentication, and **"What are you allowed to do?"** is handled by authorization. Succeeding at authentication does not guarantee permission to access every endpoint.

Note for Spring Security Servlet: according to the reference documentation, the default HTTP Basic configuration may omit the `WWW-Authenticate` header and response body on 401 responses for requests carrying `X-Requested-With: XMLHttpRequest`, in order to avoid triggering the browser's login dialog. Therefore, when debugging, do not conclude that "no `WWW-Authenticate`" means the server is not using Basic.

## 5. Runnable Spring Boot 3.x / Spring Security 6.x Example

The following example uses Java 17+, Spring Web, and Spring Security. The goal is to observe 200, 401, and 403 statuses *directly* in a small application. To avoid putting a real account into source code, the two credentials below are **demo data only**, created in memory and using BCrypt.

If your Gradle project already uses the Spring Boot plugin and dependency management, the following two dependencies are needed in `build.gradle` (this is a **configuration snippet**, not a complete build file):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Create the file `src/main/java/com/example/basic/BasicDemoApplication.java`:

~~~java
package com.example.basic;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Map<String, String> publicPage() {
            return Map.of("message", "public");
        }

        @GetMapping("/private")
        Map<String, String> privatePage(Principal principal) {
            return Map.of("user", principal.getName());
        }

        @GetMapping("/admin")
        Map<String, String> adminPage(Principal principal) {
            return Map.of("admin", principal.getName());
        }
    }
}
~~~

Create the file `src/main/java/com/example/basic/SecurityConfig.java`:

~~~java
package com.example.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Here:

- `httpBasic(Customizer.withDefaults())` registers HTTP Basic processing. When providing your own `SecurityFilterChain`, you should explicitly declare the authentication mechanism you want to use.
- `requestMatchers("/public").permitAll()` opens the public resource; the remaining paths require authentication. `/admin` also requires `ROLE_ADMIN` (Spring Security maps `hasRole("ADMIN")` to the corresponding authority).
- `SessionCreationPolicy.STATELESS` indicates that the application does not create/use an HTTP session to store `SecurityContext` for this flow. The Basic header can still be sent on **every request**; being "stateless" does not make Base64 any safer.
- `BCryptPasswordEncoder` hashes and verifies passwords. This is an in-memory demo; a real system needs an account store, secret management, login rate limiting, and appropriate operational policies.
- The example only uses `GET` requests, which do not change server state. The configuration does not disable default CSRF protection; when adding POST/PUT/DELETE, you must evaluate CSRF according to the client type rather than disabling it automatically.

Run the application from the Gradle-configured Spring Boot project:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `gradlew.bat bootRun`. Because this is a Spring Boot application using external libraries, a standalone `javac` command does not have the required classpath; use Gradle to compile and run.

### Testing with cURL

~~~bash
# Public: no username/password needed.
curl -i http://localhost:8080/public

# No credentials: private resource requires authentication.
curl -i http://localhost:8080/private

# Valid credentials (demo).
curl -i -u reader:demo-pass http://localhost:8080/private

# Wrong password.
curl -i -u reader:wrong-pass http://localhost:8080/private

# Authenticated but missing ADMIN role.
curl -i -u reader:demo-pass http://localhost:8080/admin

# Has ADMIN role.
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Key results to observe:

| Request | Expected HTTP status | Meaning |
| --- | --- | --- |
| `GET /public` without credentials | `200 OK` | Public endpoint. |
| `GET /private` without credentials | `401 Unauthorized` | Authentication required; typically includes a Basic challenge. |
| `GET /private` with `reader:demo-pass` | `200 OK` | Auth succeeded; JSON body contains `"user":"reader"`. |
| `GET /private` with wrong password | `401 Unauthorized` | Credentials rejected. |
| `GET /admin` with `reader:demo-pass` | `403 Forbidden` | Authenticated, but does not have `ROLE_ADMIN`. |
| `GET /admin` with `admin:admin-pass` | `200 OK` | Access granted; body contains `"admin":"admin"`. |

The statuses above apply to **this example configuration**. Another application may change the entry point, error handlers, authorization policies, or filter chain, causing response details to differ. The `curl` commands do not require writing Base64 manually; depending on the client, `-u` may send Basic on the first request. If PowerShell aliases the `curl` command to another tool, invoke `curl.exe`.

**Do not use real accounts in sample commands, logs, screenshots, or shell history.** For real credentials, the safe way to supply secrets depends on the operational environment; the `-u username:password` flag is handy for demos but can be exposed in command history or process lists.

## 6. Why Is 401 Different from 403?

| Scenario | Common interpretation | Result |
| --- | --- | --- |
| No credentials sent, endpoint requires login | No verified identity yet | `401` with a Basic challenge (subject to configuration exceptions). |
| Basic sent, but wrong username/password | Authentication failed | `401`. |
| Logged in, but only has `ROLE_READER`, endpoint requires `ROLE_ADMIN` | Authorization failed | `403`. |
| Valid credentials and sufficient permissions | Allowed to proceed to the controller | Business response, typically `2xx`. |

A `403` code can occur for other reasons (for example, blocked by the CSRF filter), so you need to read logs for the exact filter and request context; do not assume every 403 is due to a missing role.

## 7. Security Points and Limitations to Understand

1. **Always use HTTPS.** Base64 can be decoded immediately. HTTP Basic does not protect the transport channel, prevent eavesdropping, prevent replay, or limit credential lifetime on its own. Protect both the client → reverse proxy connection and appropriate hops within your infrastructure.
2. **Credentials are resent per request.** Basic is not a session token, OAuth access token, or JWT. A client/browser may remember credentials, but that does not provide dedicated token revocation or expiration. Changing or revoking the password is one way to stop previously accepted Basic credentials from being accepted.
3. **Do not expose `Authorization`.** Avoid writing the raw header into access logs, tracing, analytics, exception messages, shared screens, or debugging tools. Verify whether proxies/gateways forward the header properly and mask sensitive data when logging.
4. **Hash passwords on the server.** Do not store plaintext passwords or treat Base64 as "data encryption". Use an appropriate password hash (`BCrypt`, `Argon2` depending on the system) and verify with `PasswordEncoder`. Authorization must always be enforced on the server.
5. **Do not disable CSRF mechanically.** Basic does not use the application's login cookie, but a browser can automatically resend cached HTTP Basic credentials. Therefore, an API accessed by browsers must still be evaluated for CSRF if it performs state-changing operations; an API used only by clients that do not automatically send credentials has a different risk model.
6. **Protect against password guessing.** Basic does not provide MFA, rate limiting, account lockout/throttling, anomaly detection, or credential lifecycle management out of the box. Add these controls according to system requirements. Grant only least-privilege permissions per user/endpoint.
7. **Pay attention to CORS and caching.** CORS governs whether browser JavaScript can read cross-origin responses; it does not replace authentication or authorization. Do not accidentally cache private responses in shared caches; apply `Cache-Control` appropriate for sensitive data.

When a system needs end-user login, explicit logout, MFA, time-limited tokens, delegated permissions, or login via an identity provider, evaluate an appropriate session/cookie mechanism or OAuth2/OIDC. HTTP Basic has the advantage of simplicity, at the trade-off of repeatedly transmitting the raw credentials.

## 8. How to Self-Check and Debug

- **Inspect the incoming request:** are the header name `Authorization` and scheme `Basic` correct? Does the Base64 value decode to `username:password` as the client intended? Test only with demo credentials or in controlled environments; never put real credentials into logs.
- **Distinguish 401 and 403:** 401 points toward the authentication mechanism, credentials, or entry point; 403 points toward access permissions or another filter such as CSRF. Do not modify authorization rules before verifying that the request was actually authenticated.
- **Check the filter chain:** does the application have `httpBasic(...)` in the exact `SecurityFilterChain` serving that URL? Do `securityMatcher`, `requestMatchers`, and chain ordering match the endpoint?
- **Check the authentication backend:** does `UserDetailsService` load the right user? Is the user enabled/unlocked/non-expired? Is the password encoded with the matching `PasswordEncoder`? Does the authority have the `ROLE_` prefix required by `hasRole`?
- **Check the client and gateway:** is the client sending the header over HTTPS to the right host/port? Is a reverse proxy stripping `Authorization`? Is the browser caching stale credentials, or is there an `X-Requested-With: XMLHttpRequest` header affecting the challenge returned?
- **For Unicode characters:** review the encoding and the challenge's `charset="UTF-8"`. Mismatched encodings can cause a password that looks right in the UI to produce different bytes sent to the server.

A reliable test must demonstrate all three cases: **no credentials → 401**, **valid credentials but insufficient permissions → 403**, **valid credentials and sufficient permissions → access granted**. Also test wrong passwords and requests going through a reverse proxy in real deployments.

## 9. Takeaways

- `Authorization: Basic …` is a **request header carrying credentials**; `WWW-Authenticate: Basic realm="…"` is the server's **response challenge**.
- Base64 enables transporting `username:password` in a header and **does not secure** credentials; HTTPS is required.
- In Spring Security Servlet, `BasicAuthenticationFilter` processes Basic credentials, `AuthenticationManager` and its providers authenticate them, `SecurityContextHolder` holds the result for the request, and `AuthorizationFilter` decides authorization.
- `401` indicates authentication has not succeeded; `403` usually means authenticated but not permitted (or blocked by a filter such as CSRF).
- HTTP Basic does not inherently provide sessions or expiring tokens. Carefully consider credential retransmission, log protection, least privilege, and browser CSRF risks.

### References

- RFC 7617 — The 'Basic' HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617
- Spring Security Reference — HTTP Basic Authentication (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security Reference — CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
