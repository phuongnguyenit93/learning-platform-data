# Observing the Login Page, HTTP Basic, and Unauthenticated Responses

Right after adding `spring-boot-starter-security` to a Spring Boot application, you may encounter two seemingly different responses: **a browser automatically redirects to a login page**, while `curl` or an API client receives **HTTP 401** with a prompt to send credentials. These are two ways of initiating **authentication** tailored to different client types. To understand them, you need to observe **status codes**, **HTTP headers**, **redirect paths**, **cookies/sessions**, and **the security mechanisms actually enabled**.

This lesson guides a systematic observation of three scenarios: **form login in a browser**, **HTTP Basic authentication**, and **responses when a request is unauthenticated or lacks privileges**. The examples use **Spring Boot 3, Spring Security 6, Spring MVC/Servlet, and Java 17+**. Configuration choices are stated explicitly so results are repeatable across browsers, `curl`, and MockMvc. Specific session IDs, CSRF tokens, timestamps, header ordering, and redirect URLs may vary by environment.

## 1. First: Distinguish "Not Logged In," "Wrong Password," and "Insufficient Privileges"

| Scenario | Security State | Typical Response | Meaning |
| --- | --- | --- | --- |
| Unauthenticated browser accesses a private page with `formLogin` | No logged-in principal yet | **302 Found** to `/login`, then GET `/login` is usually **200 OK** | Sends the user to a UI for entering credentials |
| API using HTTP Basic, no credentials sent | Unauthenticated | **401 Unauthorized** + `WWW-Authenticate: Basic ...` | Client must supply a valid username/password |
| API using HTTP Basic, wrong username/password | Authentication failed | Usually **401**; may include Basic challenge | Credentials were provided but rejected |
| Authenticated, yet calling an action needing another role/authority | Valid identity but not permitted | Usually **403 Forbidden** | This is an authorization issue |
| Valid user calls an endpoint with proper privileges | Authentication + authorization succeeded | Usually **200 OK** for a simple GET | Request passed all active checks |
| POST using session cookie without a valid CSRF token | Possibly logged in, invalid state-changing request | Usually **403 Forbidden** | Blocked by the CSRF layer, not equivalent to missing a role |
| Endpoint configured with `permitAll()` | Publicly allowed by policy | Usually **200 OK** | Login is not required for that endpoint |

Status codes depend on **AuthenticationEntryPoint**, **AccessDeniedHandler**, the filter chain, whether form/session or Basic/token is used, and application configuration. You cannot conclude every 302 is a login redirect or every 403 is a missing role. Always inspect the exact URL, method, response, and configuration.

### 1.1. Why Does HTTP Call 401 "Unauthorized" Even Though It Means Unauthenticated?

In HTTP authentication terminology, **401 Unauthorized** indicates the request lacks valid authentication credentials for a protected resource; the server may return `WWW-Authenticate` describing the scheme the client should use. **403 Forbidden** typically indicates the request's identity was processed yet lacks permission, or was rejected by another mechanism such as CSRF. HTTP status phrase naming does not replace distinguishing **authentication** from **authorization**.

### 1.2. Seeing a Login Page Does Not Mean the API Succeeded

A browser visiting `/home` may receive:

```text
GET /home
  -> 302 Location: /login
GET /login
  -> 200 Content-Type: text/html
```

The browser tab ends up displaying an HTML page with **200**, yet **the initial request to `/home` was not permitted**. When inspecting with Developer Tools, enable **Preserve log** and inspect the entire request sequence instead of looking only at `/login`'s status.

Similarly, `curl -L` or HTTP clients that follow redirects automatically can hide the initial status if you ignore redirect history. To study actual behavior, first **do not follow redirects automatically**.

## 2. Default Initialization Behavior of Spring Boot and Spring Security

In a Spring Boot 3 Servlet application, when you add `spring-boot-starter-security` without defining a custom `SecurityFilterChain`, Spring Boot typically configures protection for all requests and enables both **form-based login** and **HTTP Basic**. Spring Security's default configuration is conceptually equivalent to:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

The snippet above illustrates **conceptual configuration**, not a standalone Java file. In a real project, Spring Boot adds beans, security filters, and a user store via auto-configuration. When you **declare your own** `SecurityFilterChain` bean, explicitly enable the mechanisms you want, such as `formLogin(...)` and/or `httpBasic(...)`; do not assume they appear automatically in custom configuration.

### 2.1. Default User and Startup Password

If no custom `UserDetailsService`, `AuthenticationProvider`, or other authentication mechanism exists, Boot can create a default user, typically with username `user` and a **random development password** printed to the startup log. The log may contain a message about the generated security password.

This is meant for **bootstrapping and learning**, not production account management. Never rely on this password in real deployments; never share logs containing passwords, secrets, or tokens. Depending on the beans you declare yourself, the default user might not be created; therefore check your project's actual configuration before relying on the `user` account.

### 2.2. Same System, Multiple Ways to Initiate Authentication

If **a single security chain** enables both form login and HTTP Basic, Spring Security may pick an entry point based on the request, such as the content types accepted by the client. The outcome also depends on custom exception handling and how the application handles APIs. Thus, looking only at the `Accept` header or saying "browsers always get 302, curl always gets 401" is too broad a rule.

To observe both flows with predictable results, this lesson uses **two `SecurityFilterChain` beans**:

- `/api/**`: uses HTTP Basic and does not use sessions to restore authentication; unauthenticated requests receive **401**.
- All other URLs: use form login; unauthenticated requests to private pages receive **302** redirecting to `/login`.

This is a **learning sample configuration**. Production applications may use sessions, JWTs, OAuth2/OIDC, or a gateway with different policies, so always explain responses based on the actual configuration.

## 3. Observing Form Login: From a Private Page to /login

With form login, when an unauthenticated request is blocked by an access rule, `ExceptionTranslationFilter` works with `LoginUrlAuthenticationEntryPoint` to initiate login by returning a redirect.

### 3.1. Before Logging In

```http
GET /home HTTP/1.1
Host: localhost:8080
Accept: text/html
```

Typical response:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login
```

`Location` may be a relative path or a full URL depending on environment and redirect strategy. **What matters is verifying that the redirect targets the expected login page**, rather than asserting an exact character-by-character URL across all systems.

When the browser follows the redirect:

```http
GET /login HTTP/1.1
Host: localhost:8080
Accept: text/html
```

Typical response:

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8
```

The body contains the HTML login form. If the app enables `formLogin(Customizer.withDefaults())` without supplying a custom login page, Spring Security can generate a default page via `DefaultLoginPageGeneratingFilter`.

### 3.2. Who Generates the Default Login Page?

Spring Security can generate a default HTML page with `username`, `password`, and a CSRF token field when needed. This feature helps verify configuration quickly; **it is not a production UI template authored by your application**.

To verify, open `http://localhost:8080/login` in a browser and check:

1. The address bar URL changed to `/login` after visiting a private page.
2. The HTML contains a login form with username/password inputs.
3. DevTools → Network shows `GET /home` returning a redirect and `GET /login` returning HTML.
4. If CSRF protection is active, the form submits a CSRF token per Spring Security's setup.
5. On failed login, default form login normally redirects to `/login?error` rather than returning a 401 JSON error like an API.

Do not treat the default login page as a finished product UI. When using a custom page, the application must provide its own endpoint/template and align login processing URL, CSRF, errors, accessibility, and session protection properly.

### 3.3. After Submitting Form Login

Conceptual flow:

```text
GET /home              -> redirect to /login
GET /login             -> user/password + CSRF entry page
POST /login            -> UsernamePasswordAuthenticationFilter
                       -> AuthenticationManager / Provider
                       -> success: security context, session when applicable
                       -> redirect to saved request or success URL
GET /home with session -> 200, private content
```

With session-based login, browsers typically store a session cookie like `JSESSIONID` when the server requires a session. Cookie values, session fixation protection, CSRF tokens, and request caching vary by application, so do not put specific IDs in docs or assert a fixed sample string in tests.

**`POST /login` is not just sending username/password.** When CSRF protection is enabled, issuing a manual POST via curl without a valid CSRF token can return **403** before the password is even checked. A browser submitting the framework-generated form normally includes the required token. Never disable CSRF just because a manual POST failed.

### 3.4. Distinguishing a Login 302 from Application 302s

An application can return redirects for many reasons: after logout, post-submit navigation, URL canonicalization, OAuth2 callbacks, or login challenges. Inspect `Location`, the initial request, session state, and the security chain. When testing form login, verify the redirect target and that the user became authenticated; asserting only "status 302" is insufficient.

## 4. Observing HTTP Basic: 401 and WWW-Authenticate

HTTP Basic is an authentication scheme defined by HTTP. The client sends username/password in the `Authorization` header; when valid credentials are missing, the server typically returns **401** and a **`WWW-Authenticate: Basic ...`** header advertising the supported scheme.

### 4.1. Request Without an Authorization Header

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Response under this lesson's API chain configuration:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The realm name is a configuration detail; **do not hardcode `Realm` in general application tests**. Certain client requests or custom entry points may receive different headers; for example, Spring Security supports avoiding browser Basic popups in some XHR scenarios. To prove HTTP Basic is active, verify both the security chain and the challenge for the specific request.

The `WWW-Authenticate` header is the **challenge from the server**, whereas the `Authorization` header carries **credentials sent by the client**; those two names are easily confused.

### 4.2. Request With Basic Credentials

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic <base64-of-username-colon-password>
```

The actual value is the Base64 encoding of `username:password`. **Base64 is not encryption**; anyone holding the header can decode it to read the username and password. HTTP Basic is only appropriate over **HTTPS** in real usage, and you must avoid logging the `Authorization` header or exposing passwords in command lines, shell history, or screenshots.

In local examples, you can use `curl -u alice:demo-alice-pass` so curl builds the header instead of encoding Base64 manually. Once the provider verifies the credentials, the request to `/api/me` returns 200 and the sample user payload.

### 4.3. Wrong Password vs. Insufficient Privileges

- Wrong username/password → **authentication failed**, typically returns `401`.
- Valid username/password, user lacks `ROLE_ADMIN` → **authorization denied**, typically `403`.
- No username/password sent to a `permitAll()` endpoint → may return `200`.
- POST missing CSRF in a CSRF-enabled chain → may return `403`, **even with** valid username/password.

Some browsers display a native dialog prompting for username/password upon receiving a Basic challenge; API clients like curl/Postman display raw headers/status. Do not confuse the browser's native Basic dialog with the HTML `/login` page rendered by Spring Security: they are **two distinct UIs and mechanisms**.

### 4.4. Basic Usually Does Not Need a Login Session

With Basic, clients typically send credentials on **every request**. The example configures the API chain with `SessionCreationPolicy.STATELESS` so Spring Security does not use an HTTP session to restore `SecurityContext` for the API. This lets you observe the independence between the Basic API and web UI login cookies.

`STATELESS` **does not mean protections like CSRF are automatically unnecessary or off everywhere**. If an API still accepts credentials automatically sent by browsers or exposes state-changing endpoints, evaluate your threat model and exact CSRF policy. This lesson uses only GET endpoints on the API to observe authentication.

## 5. Spring Boot 3 Practice: Two Clear Flows

Goals:

| URL | Who Can Call? | What to Observe |
| --- | --- | --- |
| `GET /public` | Public | 200 even without login |
| `GET /home` | Must log in | Anonymous → 302 `/login` |
| `GET /admin` | Must have `ROLE_ADMIN` | Anonymous → login; user lacking role → 403 |
| `GET /login` | Form login | HTML page generated by Spring Security |
| `GET /api/public` | Public | 200 even without Basic credentials |
| `GET /api/me` | Must authenticate | Anonymous → 401 Basic challenge; valid Basic → 200 |
| `GET /api/admin` | Must have `ROLE_ADMIN` | Valid Basic lacking privilege → 403 |
| `POST /notes` | Must log in, needs CSRF | POST missing token → 403 when CSRF is enabled |

### 5.1. Project Creation and Dependencies

Create a **Spring Boot 3, Java 17+** project with **Spring Web (MVC)** and **Spring Security**. With Gradle Groovy DSL, in `build.gradle` of a Boot project already configured with plugins and repositories, use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

With Maven, a Boot project with `spring-boot-starter-parent`/BOM uses the equivalent dependencies. **Do not manually mix incompatible Spring Security versions with Boot**; let the project's dependency management choose consistent versions. The Gradle snippet here is a *fragment of a Spring Boot project*, not a complete build file.

### 5.2. Main Class

Create `src/main/java/example/loginobservation/LoginObservationApplication.java`:

```java
package example.loginobservation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginObservationApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginObservationApplication.class, args);
    }
}
```

### 5.3. SecurityConfig: Basic API and Web Form Login

Create `src/main/java/example/loginobservation/SecurityConfig.java`:

```java
package example.loginobservation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Detailed line-by-line explanation:

1. The two `SecurityFilterChain` beans are ordered with `@Order`. `FilterChainProxy` selects the **first chain whose matcher matches**.
2. The first chain handles only `/api/**` and uses `httpBasic`. `/api/public` is public, `/api/admin` requires role ADMIN, and remaining APIs require authentication.
3. `STATELESS` prevents the API chain from pulling authentication from a web session; sample API requests to private endpoints must supply Basic credentials.
4. The second chain **omits `securityMatcher`**, acting as a fallback for remaining URLs like `/home`, `/admin`, and `/login`. It enables `formLogin` and uses sessions by default when needed.
5. `formLogin(Customizer.withDefaults())` allows Spring Security to generate the default login page at `/login` and process login submissions; in this setup, that page belongs to the web chain.
6. Demo passwords are hashed with `BCryptPasswordEncoder`. `roles("ADMIN")` creates `ROLE_ADMIN`, matching `hasRole("ADMIN")`. Sample passwords are for local use only.
7. CSRF protection in Spring Security Servlet **is not disabled**. Therefore POST requests to the web chain require a valid CSRF token when applicable.
8. `apiChain` does not enable form login; `webChain` does not enable HTTP Basic. Consequently, 401 vs 302 behavior is cleanly determined by chain, making observation straightforward.

**Key point:** `securityMatcher("/api/**")` scopes **the entire chain**. It differs from `requestMatchers(...)`, which only defines authorization rules **inside the already-selected chain**. If a multi-chain app lacks a fallback, an unmatched URL can bypass Spring Security filters altogether. Here, `webChain` has no `securityMatcher`, so it covers everything else.

### 5.4. Controller

Create `src/main/java/example/loginobservation/ObservationController.java`:

```java
package example.loginobservation;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ObservationController {

    @GetMapping("/")
    public String index() {
        return "Welcome";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/home")
    public String home(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin page";
    }

    @GetMapping("/api/public")
    public Map<String, String> apiPublic() {
        return Map.of("message", "public api");
    }

    @GetMapping("/api/me")
    public Map<String, String> apiMe(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> apiAdmin() {
        return Map.of("message", "admin api");
    }

    @PostMapping("/notes")
    public String addNote(Principal principal) {
        return "note from " + principal.getName();
    }
}
```

`Principal` is a Java/Spring servlet abstraction for reading the identity attached to the request after authentication. Controllers **do not verify passwords themselves**; security filters and authentication providers handle that. If a service needs ownership/tenant checks on a specific resource, that is an additional business authorization layer.

In this example, `/notes` only returns a string without writing to a database; it exists to illustrate the difference between login, authorization, and CSRF.

### 5.5. Running the Application

In the Spring Boot project root containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell or CMD:

```powershell
.\gradlew.bat bootRun
```

When running, the app listens by default at `http://localhost:8080` unless `server.port` is changed. If using another port, adjust the URLs below. Two demo accounts:

| Username | Demo Password | Role |
| --- | --- | --- |
| `alice` | `demo-alice-pass` | `ROLE_USER` |
| `admin` | `demo-admin-pass` | `ROLE_USER`, `ROLE_ADMIN` |

Never use these passwords in production. In real deployments, use HTTPS, a proper identity store, password/session policies, and secure secret management.

## 6. Browser and Developer Tools Observation Exercise

### 6.1. Use an Incognito Window to Start from a Clean State

A browser session holding a `JSESSIONID` cookie may already be logged in; in that case `GET /home` returns 200 and you will not see the redirect. To study properly, open an incognito/private window or clear localhost cookies for this demo app.

Steps:

1. Open `http://localhost:8080/home` while unauthenticated.
2. Watch the address bar change to `http://localhost:8080/login`.
3. Open Developer Tools → Network, enable **Preserve log**, and visit `/home` again.
4. Filter by `Doc` or `All`; locate the `/home` and `/login` requests.
5. Select `/home` to inspect status 302 and the `Location` response header; select `/login` to inspect status 200 and the HTML form.
6. Enter `alice` / `demo-alice-pass`. After authentication, the browser redirects to the saved request (if any) or success URL; visit `/home` to see `hello alice`.
7. While logged in as Alice, visit `/admin`: expect **403** because Alice lacks `ROLE_ADMIN`, rather than a redirect to login.
8. Log out or open another incognito window and try Admin to compare permissions.

An easy-to-record observation trace:

```text
GET /home         302 -> Location contains /login
GET /login        200 -> HTML login
POST /login       302 -> login succeeded, redirect
GET /home         200 -> hello alice
GET /admin        403 -> logged-in account lacks ROLE_ADMIN
```

Exact status and target of POST login may change with custom configurations such as a login success handler or MFA. The statuses above are **expected for this explicit example**.

### 6.2. Inspecting the Session Cookie Carefully

In DevTools → Application/Storage → Cookies (section names vary by browser), check whether the app set a session cookie. **Never copy raw session ID values into logs, issue trackers, or public tutorials**. In real applications, cookies must configure `HttpOnly`, `Secure` over HTTPS, and `SameSite` matching the threat model.

Do not treat the presence of `JSESSIONID` as proof that a user is logged in: an HTTP session can exist for other purposes, such as saving an unauthenticated request or CSRF state. Verify actual `GET /home` behavior with that session and server-side Authentication/authorization.

### 6.3. When Browser Cache Obscures Observation

DevTools offers a **Disable cache** checkbox while open, which helps when inspecting requests. However, if a user is already logged in, clearing cache does not clear cookies/sessions. Do not confuse resource caching with the security context.

## 7. curl Observation Exercise: Inspecting Status and Headers Clearly

In every command below, `-i` shows HTTP response headers and body. **Do not use `-L` on the first pass** because it automatically follows redirects and can hide the initial response.

### 7.1. Calling a Private Web Endpoint Without Login

```bash
curl -i http://localhost:8080/home
```

Key output:

```text
HTTP/1.1 302
Location: .../login
```

The status reason phrase or formatting on the status line may depend on server/HTTP version, yet status 302 and a `Location` header pointing to login are the signals to note.

The login page:

```bash
curl -i http://localhost:8080/login
```

Expect **200** and an HTML login form. Do not hardcode exact HTML because the default page can change across versions and CSRF tokens.

### 7.2. Calling a Private API Without Basic Credentials

```bash
curl -i http://localhost:8080/api/me
```

Expected:

```text
HTTP/1.1 401
WWW-Authenticate: Basic ...
```

If you send `X-Requested-By: XMLHttpRequest` or configure a custom `AuthenticationEntryPoint`, challenge details may differ. With the standard curl commands in this lesson, seeing the Basic challenge is what to verify.

### 7.3. Calling the API With Valid Basic Credentials

```bash
curl -i -u alice:demo-alice-pass http://localhost:8080/api/me
```

Expect **200 OK** with JSON body:

```json
{"user":"alice"}
```

`curl -u` automatically constructs the Basic `Authorization` header. Passing passwords inline on the command line is strictly for local demos. For real credentials, use proper secret prompting and management to avoid exposure in shell history or process lists.

### 7.4. Calling the API With Wrong Basic Credentials

```bash
curl -i -u alice:wrong-password http://localhost:8080/api/me
```

Expect **401**, with no user data returned by the endpoint. Here 401 stems from **rejected credentials**.

### 7.5. Logged In Yet Lacking Admin Privilege

```bash
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin
```

Expect **403 Forbidden**, because Alice has `ROLE_USER` but lacks `ROLE_ADMIN`. With the Admin account:

```bash
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin
```

Expect **200** and body:

```json
{"message":"admin api"}
```

This is a key test pair proving **successful authentication does not guarantee successful authorization**.

### 7.6. Comparing Public Endpoints

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/public
```

Both expect **200**. Public requests still traverse their matching filter chain; `permitAll()` does not mean turning off all of Spring Security.

### 7.7. Using Accept to Verify Chain Selection

```bash
curl -i -H "Accept: text/html" http://localhost:8080/api/me
curl -i -H "Accept: application/json" http://localhost:8080/home
```

With the **two configured chains** in this example, `/api/me` still returns a 401 Basic challenge, and `/home` still redirects 302 to login. This is one way to prove **the mechanism is selected via `securityMatcher`**, not merely by `Accept`.

In a **single-chain** setup enabling both form login and Basic, content negotiation and entry points can behave differently. Distinguish these two cases before debugging or writing tests.

### 7.8. HTTP Basic and Browser Dialogs

If you visit `/api/me` directly in a browser, the browser may pop up a credential dialog triggered by the `WWW-Authenticate` header. That dialog is managed by the **browser**. It is not the HTML `/login` page and does not share the same form/CSRF/session handling.

Avoid accidentally enabling Basic challenges on web UI routes if you want all users to sign in through a consistent HTML form.

## 8. Standalone Java 17: Printing 302, 401, 200, and Headers

To observe responses without an IDE, you can use JDK 17's `java.net.http.HttpClient`. The program below **runs standalone with `javac`/`java`**, while requiring the Spring Boot app from section 5 to be running at `localhost:8080`.

Create **`HttpResponseObserver.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpResponseObserver {
    private static final String BASE = "http://localhost:8080";

    static void observe(HttpClient client, String path)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE + path))
            .GET()
            .build();

        HttpResponse<Void> response = client.send(
            request,
            HttpResponse.BodyHandlers.discarding()
        );

        boolean loginRedirect = response.statusCode() == 302
            && response.headers()
                .firstValue("Location")
                .map(s -> s.contains("/login"))
                .orElse(false);

        boolean basicChallenge = response.statusCode() == 401
            && response.headers()
                .firstValue("WWW-Authenticate")
                .map(s -> s.startsWith("Basic"))
                .orElse(false);

        System.out.println(path + " status=" + response.statusCode()
            + " loginRedirect=" + loginRedirect
            + " basicChallenge=" + basicChallenge);
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        observe(client, "/home");
        observe(client, "/api/me");
        observe(client, "/public");
    }
}
```

Compile and run from the directory containing the file:

```bash
javac HttpResponseObserver.java
java HttpResponseObserver
```

With the example app running and no cookies or credentials sent, **the exact expected stdout is**:

```text
/home status=302 loginRedirect=true basicChallenge=false
/api/me status=401 loginRedirect=false basicChallenge=true
/public status=200 loginRedirect=false basicChallenge=false
```

Why the output is deterministic in this example:

- `Redirect.NEVER` preserves the 302 without automatically fetching `/login`.
- The program sends no cookies, Authorization headers, or credentials.
- `/home` belongs to the web chain and requires login.
- `/api/me` belongs to the Basic chain and sends `WWW-Authenticate` when unauthenticated.
- `/public` is allowed via `permitAll()`.
- Checking booleans rather than printing raw realm/Location/session IDs avoids coupling to variable URL details.

If run before the server starts or on the wrong port, the program reports a connection error instead of printing all three lines. If your configuration differs from the example, rely on actual responses rather than assuming identical output.

## 9. Automated Testing with Spring Security Test and MockMvc

Manual checks help you understand requests. To protect behavior long-term, write **integration tests** against the real Spring Security filter chain. The project in section 5 already includes `spring-boot-starter-test` and `spring-security-test`.

Create `src/test/java/example/loginobservation/ObservationSecurityTest.java`:

```java
package example.loginobservation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ObservationSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousWebPageRedirectsToLogin() throws Exception {
        mvc.perform(get("/home").accept(MediaType.TEXT_HTML))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void generatedLoginPageIsHtml() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_HTML));
    }

    @Test
    void anonymousApiGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Basic")));
    }

    @Test
    void validBasicCredentialsIdentifyUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void invalidBasicCredentialsFail() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void roleControlsAdminApi() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void formLoginAuthenticatesAlice() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("demo-alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void csrfStillProtectsPost() throws Exception {
        mvc.perform(post("/notes")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPublicPagesStayAvailable() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }
}
```

Run tests:

```bash
./gradlew test --tests example.loginobservation.ObservationSecurityTest
```

In Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.loginobservation.ObservationSecurityTest
```

**Expected:** all nine test methods pass when the Boot 3 project, two chains, user store, and controller match the code above. No fixed Gradle stdout snippet is shown because plugins, versions, daemons, and logs can vary output.

### 9.1. What Is MockMvc Proving?

- `get("/home")` checks the **web chain** redirect when unauthenticated.
- `get("/login")` checks the default login page.
- `get("/api/me")` checks the **Basic chain** challenge.
- `httpBasic(...)` sends a Basic header through the application's authentication mechanism and provider.
- `formLogin()` simulates form login submission, supplying the required data for that flow.
- `user(...)` **simulates** an authenticated user for the request; useful to isolate CSRF/authorization tests, **does not prove the password provider works**.
- `status().isForbidden()` when lacking admin privileges proves authorization rules are enforced for authenticated accounts.
- The CSRF test proves POST without a token is rejected when CSRF protection is active.

To test POST **with a valid token**, add `.with(csrf())` to the MockMvc request and assert the response/side effects accordingly. In this example, testing the missing token suffices to show the protection works; never fix tests by disabling CSRF.

### 9.2. Avoid Tests That Assert Only Status 200

A 200 can come from `/login` or a public endpoint while the originally requested private resource was still denied. In tests, assert the exact **URL, user, role, status, Location, WWW-Authenticate, and body**. For state-changing actions, also verify **no unauthorized side effects occurred** when security blocks the request.

## 10. Cases Where Behavior Differs from Expectations

### 10.1. One SecurityFilterChain Enabling Both Basic and Form

If you write:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

then entry point selection can be influenced by **request matchers and content negotiation**, especially for clients accepting HTML versus API clients. This differs from the two-chain example; do not draw wrong conclusions simply because `curl` sees no redirect or a browser gets a Basic challenge.

### 10.2. Already Having an Active Login Session

If the browser holds a valid session, `GET /home` returns 200. An incognito window or clearing localhost cookies recreates the anonymous scenario. `curl` normally does not send cookies unless told to; that is one reason curl and browsers can yield different results.

### 10.3. Accept Header, XHR, and Request Cache

The `Accept` header describes the representation the client prefers, not proof of identity. Some default setups use media-type matching to pick entry points. For HTTP Basic, XHR scenarios can alter challenge details to avoid browser login popups. In addition, form login can cache the initial request and redirect back after login; HTTP Basic typically does not rely on request caching the same way.

### 10.4. Reverse Proxies, Path Prefixes, and HTTPS

Behind a gateway, `Location` may contain an absolute URL, different scheme, or host, especially when forwarded headers are misconfigured. When observing, check the actual URL called by users, base path, `X-Forwarded-*`/`Forwarded` per trust boundaries, and redirect strategy. Never blindly trust forwarded headers supplied by arbitrary clients; trust them only when set by a trusted proxy and configured appropriately.

### 10.5. POST Missing CSRF Token

A POST to a cookie/session endpoint or CSRF-enabled chain can return **403** even when credentials or the logged-in user are valid. CSRF validates **state-changing requests**, separate from authentication. To observe unauthenticated 302s, use GET against private resources; for POST, check CSRF before interpreting results.

### 10.6. Custom AuthenticationEntryPoint or AccessDeniedHandler

If a project configures `exceptionHandling` or custom API handlers, you may receive JSON 401/403 instead of a challenge or redirect. Read the `SecurityFilterChain` and custom handlers for that exact request before attributing behavior to defaults.

### 10.7. Matching the Wrong Chain

With multiple chains, `@Order` and `securityMatcher` are critical:

- The first matching chain wins.
- `anyRequest()` applies **only within the selected chain**.
- If no fallback chain fits, some URLs may go unprotected by Spring Security.
- If form login `/login` accidentally falls into a Basic-only API chain, the login page may fail to work as intended.
- Test `/api/me`, `/home`, `/login`, `/admin`, and undeclared paths to verify.

### 10.8. 401 and 403 from Other Security Layers

Do not read a response code and guess a single cause. An API may return 401 due to token expiration/issuer/audience mismatch, or 403 due to missing authorities, bad CSRF, or object-level policy denial. Web routes may redirect to an OAuth2 IdP instead of `/login` when OAuth2 login is used. Combine Network logs, sanitized server logs, and integration tests.

## 11. Observing Safely: Never Expose Credentials or Sessions

When debugging authentication, what you need are **the route, status code, handler, and policy**, not user secrets. Never write to logs or public docs:

- `Authorization` headers containing Basic credentials or Bearer tokens;
- Passwords, password hashes, access/refresh tokens, or session cookie IDs;
- Live CSRF tokens from a user session;
- Stack traces or error responses containing secrets;
- Production accounts with real passwords.

You may log **request IDs**, normalized endpoints, status codes, authentication/authorization exception types, security filter names, or privacy-compliant principal IDs. Restrict log access appropriately.

Never enable verbose security debug logging broadly in production just to chase a 401; some logs can expose sensitive details depending on the system. Prefer local reproduction and tightly scoped, time-limited logging.

### 11.1. When Do Form Login and HTTP Basic Fit?

| Criterion | Form Login | HTTP Basic |
| --- | --- | --- |
| Typical fit | Web apps with human users interacting via UI | Internal API clients, tooling, simple integrations |
| Sending credentials | Form submit, typically creating a session after login | `Authorization: Basic ...` on requests |
| When anonymous | Usually 302 to login page | Usually 401 with Basic challenge |
| Browser experience | Customizable HTML login form | Native browser credential dialog may appear |
| Key risks | Session/cookies, CSRF, logout handling | Credentials repeated per request, requires TLS and secret protection |
| What it does not solve automatically | Object/tenant permissions, XSS, business logic | Object/tenant permissions, token lifecycle, business logic |

In production apps with users, choosing among form login, OAuth2/OIDC, JWT resource servers, sessions, or other mechanisms should follow architecture and threat modeling. HTTP Basic is easy to observe while learning, not automatically ideal for every modern API.

## 12. Quick Debugging Workflow When Expectations Don't Match

When a browser does not redirect or curl does not return 401, check in order:

1. **Right URL, port, method?** Is the server running? Is the endpoint at `/home` or under a context path?
2. **Right chain?** Do `securityMatcher` and `@Order` route the request to the expected chain?
3. **Is the observed mechanism enabled?** `formLogin(...)` for web, `httpBasic(...)` for API? Any custom entry point?
4. **Does the request already carry credentials/session?** Did the browser or tool attach an old cookie or Authorization header automatically?
5. **Status and Location?** For anonymous web GET, expect 302 to `/login`; omit `-L` in curl.
6. **401 and WWW-Authenticate?** For anonymous Basic, expect the challenge; check special headers and custom handlers.
7. **Why 403?** Missing role, wrong CSRF token, object policy, CORS/browser constraints, or something else?
8. **UserDetailsService/PasswordEncoder?** Does the user exist, is the password hashed/matched properly, is the account locked or disabled?
9. **Public match?** A `permitAll()` rule matching before a private matcher can return 200 when you expected login.
10. **Real tests?** Use MockMvc/HTTP client to test anonymous, wrong Basic, valid Basic, form login, missing role, and missing CSRF.

Diagnostic chart:

```text
Unauthenticated request
  |
  +-- Matches permitAll()? ---- Yes ---> Endpoint may return 200
  |
  +-- Which protection chain selected?
       |
       +-- Form login -------> 302 to /login (in the sample web config)
       |
       +-- HTTP Basic -------> 401 + WWW-Authenticate
       |
       +-- Custom handler ---> Inspect response per custom config
       
Authenticated identity
  |
  +-- Missing role/permission --> 403 or appropriate policy denial
  |
  +-- Authorized ---------------> Proceeds to controller/service
  |
  +-- POST missing CSRF --------> May 403 before business operation
```

## 13. Common Misconceptions

1. **"Browser showing 200 on login means `/home` was accessible."** False: inspect the first `/home` request and its 302 redirect.
2. **"Every anonymous request returns 401."** With form login, private endpoints typically redirect; Basic APIs typically challenge.
3. **"401 and 403 mean the same thing."** One usually means missing/invalid credentials; the other means denied permission or another protection failure.
4. **"Having HTTP Basic gives you a `/login` page."** HTTP Basic challenges differ from HTML form login.
5. **"Base64 is secure password encryption."** Base64 is trivially decoded; HTTPS is mandatory for real credentials.
6. **"With starter-security enabled, custom configs still get form and Basic automatically."** Once you define your own chain, explicitly enable the mechanisms you want.
7. **"Adding an `/api/**` chain needs no fallback chain."** Requests outside `/api` can lose Spring Security protection if no chain matches.
8. **"isAuthenticated is enough for authorization."** Consider anonymous tokens, roles/authorities, object/tenant checks, and context.
9. **"Having role USER lets a user view every order."** Login and roles do not replace object-level authorization.
10. **"POST returned 403 because Spring Security is broken."** CSRF may be working correctly; check token, method, and policy.
11. **"`curl -L` makes the initial redirect clearer."** Automatically following redirects can obscure the initial 302 status.
12. **"A `JSESSIONID` cookie means the user is logged in."** A session can exist before login; verify context and actual privileges.
13. **"Passing a test with `@WithMockUser` proves the password works."** Mock user fakes the context without running the password provider.
14. **"Asserting 200 is enough."** Assert URL, initial request status, Location, challenge, authorities, and side effects.
15. **"You can screenshot an `Authorization` header in a bug report."** Risks leaking secrets and account takeover; always redact credentials.

## 14. Exercises and Self-Check Questions

### Exercise A: Observing 302 and 401

Using the sample app, visit `/home` in an incognito window and call `/api/me` with curl without credentials. Record **status, Location, and WWW-Authenticate** without copying secret values. Explain why the two endpoints respond differently.

### Exercise B: Identifying 403

As `alice`, call `/api/me` and `/api/admin` using HTTP Basic. Why does the first return 200 while the second returns 403? Call again as `admin` to verify the rule.

### Exercise C: CSRF and Login State

Try `POST /notes` in a test with a mocked authenticated user but without a CSRF token; what happens? When using browser form login, how does the default page handle the CSRF field? Why should you not disable CSRF to "fix" 403?

### Exercise D: Changing Chain Configuration

Temporarily update `webChain` to enable both `formLogin` and `httpBasic` and test with different `Accept` headers. Record actual behavior, then revert to the two-chain setup to compare the difference. Never ship experimental changes to production.

**Quick Questions**

1. Does `WWW-Authenticate` appear on requests or responses, and what does it do?
2. Where does `Authorization` appear, and what does it hold when using Basic?
3. Why does `GET /login` returning 200 not prove `GET /home` returns 200?
4. When is `AuthenticationEntryPoint` used?
5. Which status does an authenticated account lacking `ROLE_ADMIN` typically receive?
6. Why might an unauthenticated POST request receive 403 instead of 302?
7. With multiple `SecurityFilterChain` beans, which matcher decides which chain is selected?
8. Why cannot HTTP Basic be considered password encryption?
9. What different aspects do `@WithMockUser` and `httpBasic()` test in MockMvc?
10. When using a single chain with both form login and Basic, why cannot you rigidly apply "browser = 302, curl = 401" to every request?

**Suggested Answers:**

1. A challenge response header from the server advertising the HTTP authentication scheme.
2. A request header from the client containing Base64-encoded `username:password` under Basic.
3. Because `/home` may redirect 302 to `/login`; the HTML login page itself returns 200.
4. When security needs to initiate authentication for a request ineligible to access a resource.
5. Usually 403, denied by authorization.
6. The CSRF filter can reject state-changing requests before handling login/authorization like GET does.
7. Each chain's `securityMatcher` along with `@Order`; afterward `requestMatchers` decides permissions inside the chain.
8. Base64 is reversible encoding, not secret protection over the network.
9. Mock user creates a simulated identity to test policy; Basic sends credentials to exercise the configured authentication mechanism.
10. Because entry points may depend on content negotiation, request matchers, and custom exception handlers.

## 15. Official Documentation

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 – Java Configuration, Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – Servlet Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – Testing HTTP Basic with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
