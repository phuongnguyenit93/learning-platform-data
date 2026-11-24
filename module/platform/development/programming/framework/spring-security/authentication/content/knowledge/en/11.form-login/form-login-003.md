# UsernamePasswordAuthenticationFilter and the username, password Parameters

**Module:** Spring Security – authentication. **Parent topic:** Form Login.  
**Reference version:** Spring Security Servlet 6.5.11, Java 17+. Focuses on HTTP form login field names, how the filter extracts credentials, customization, and testing.

## 1. Starting from a Real Request

A default Spring Security login form submits:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan%40example.test&password=secret-123
~~~

`UsernamePasswordAuthenticationFilter` reads two HTTP request parameters named **`username`** and **`password`**. It turns the values into an unauthenticated `UsernamePasswordAuthenticationToken` and hands it to `AuthenticationManager`. If the provider verifies them successfully, the framework handles `SecurityContext`/session and calls the success handler; on failure, it calls the failure handler.

**Distinction:** This filter is **not** responsible for comparing the raw password against the database hash. `DaoAuthenticationProvider` and `PasswordEncoder` verify the password, `UserDetailsService` loads the account, and `AuthenticationSuccessHandler` and `AuthenticationFailureHandler` decide the HTTP response.

By default, the processing URL is `POST /login`. A page can be rendered at `GET /login`. GET is to **display the form**, while POST is to **submit credentials**; two different jobs sharing the same path.

## 2. Integration Diagram in the Servlet Filter Chain

~~~text
Browser GET /private (anonymous)
          |
          v
AuthorizationFilter -> ExceptionTranslationFilter
          |
          v
AuthenticationEntryPoint -> redirect GET /login
          |
          v
HTML form: input name="username"
           input name="password"
           CSRF token
          |
          v
POST /login (form-urlencoded)
          |
          v
SecurityFilterChain
          |
          +-- CsrfFilter: validates token when protection is required
          |
          v
UsernamePasswordAuthenticationFilter
          |
          +-- matcher POST /login?
          +-- obtainUsername(request)
          +-- obtainPassword(request)
          +-- UsernamePasswordAuthenticationToken.unauthenticated(...)
          |
          v
AuthenticationManager / ProviderManager
          |
          +-- DaoAuthenticationProvider
          |      +-- UserDetailsService.loadUserByUsername
          |      +-- PasswordEncoder.matches(raw, storedHash)
          |      +-- account status / authorities
          |
          +-- SUCCESS -> SessionAuthenticationStrategy
          |              SecurityContextRepository
          |              AuthenticationSuccessHandler
          |              redirect saved request / target page
          |
          +-- FAILURE -> clear SecurityContextHolder
                         AuthenticationFailureHandler
                         /login?error / generic 401
~~~

Abbreviated diagram for Spring Security Servlet 6.5.11. Do not assume a JSON request, bearer token, or OAuth2 callback passes through this form-login filter.

## 3. Core API of UsernamePasswordAuthenticationFilter

Full class name:

~~~java
org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter
~~~

It extends `AbstractAuthenticationProcessingFilter`. Commonly used methods and properties:

| Member | Signature/name | Purpose |
| --- | --- | --- |
| Attempt | `attemptAuthentication(HttpServletRequest,HttpServletResponse)` | Reads credentials and calls AuthenticationManager |
| Username | `obtainUsername(HttpServletRequest)` | Protected hook to read the username parameter |
| Password | `obtainPassword(HttpServletRequest)` | Protected hook to read the password parameter |
| Rename username | `setUsernameParameter(String)` | Changes the request parameter name from `username` |
| Rename password | `setPasswordParameter(String)` | Changes the request parameter name from `password` |
| Read current names | `getUsernameParameter()`, `getPasswordParameter()` | Useful for tests/debugging |
| POST only | `setPostOnly(boolean)` | Defaults to `true`; GET login should not be opened |
| Attach details | `setDetails(request,authRequest)` | Sets WebAuthenticationDetails per config |
| URL/matcher | `setFilterProcessesUrl`/`setRequiresAuthenticationRequestMatcher` | Inherited from base class; DSL is cleaner to manage |
| Managers/handlers | `setAuthenticationManager`, `setAuthenticationSuccessHandler`, `setAuthenticationFailureHandler` | Inherited from base class |

**Normally use `http.formLogin(...)`**, rather than manually instantiating an extra filter in the chain. Only configure the filter directly when there is a specific framework-level requirement and you fully understand ordering, matchers, CSRF, context persistence, and session policy.

### Default parameter names

~~~java
UsernamePasswordAuthenticationFilter.SPRING_SECURITY_FORM_USERNAME_KEY;
UsernamePasswordAuthenticationFilter.SPRING_SECURITY_FORM_PASSWORD_KEY;
~~~

These two constants represent the default names `username`/`password`. They are **HTTP key names**, not an assertion that every application uses username rather than email as an identifier.

## 4. Why Does HTML name Matter More Than id?

~~~html
<form action="/login" method="post">
  <label for="login-identifier">Username</label>
  <input id="login-identifier" name="username" type="text"
         autocomplete="username" required>

  <label for="login-secret">Password</label>
  <input id="login-secret" name="password" type="password"
         autocomplete="current-password" required>

  <!-- With CSRF enabled, server/template must insert a valid CSRF token. -->
  <button type="submit">Sign In</button>
</form>
~~~

- `id="login-identifier"` is for labels/DOM; the filter **does not** look up by HTML id.
- `name="username"` determines that the browser submits the `username` parameter.
- `name="password"` determines which parameter carries the raw password.
- `type="password"` masks characters in the UI; it **does not encrypt the password on the network**.
- `method="post"` avoids sending passwords in query URLs.
- `required` is client-side UX validation, not a substitute for server validation.
- `autocomplete` assists password managers and accessibility.

The form below will miss parameters when read by the default filter:

~~~html
<!-- WRONG if backend still expects username/password. -->
<input id="account" name="emailAddress" type="text">
<input id="secret" name="pwd" type="password">
~~~

Even if the user fills everything out accurately, `getParameter("username")` and `getParameter("password")` cannot retrieve those two fields.

**Request parameter names are case-sensitive.** `username` differs from `userName`, and `password` differs from `passWord`.

## 5. obtainUsername/obtainPassword Logic and Normalization

The two protected methods use the Servlet API by default:

~~~java
// Illustrates basic logic; not a standalone class.
String username = request.getParameter(usernameParameter);
String password = request.getParameter(passwordParameter);
~~~

Inside `attemptAuthentication` in Spring Security 6.5, values are further normalized:

~~~java
// Simplified logic for study.
String username = obtainUsername(request);
username = (username != null) ? username.trim() : "";

String password = obtainPassword(request);
password = (password != null) ? password : "";
~~~

**Crucial points:**

1. Username is `trim()`med on both ends before creating the token. For instance, `"  lan@example.test  "` becomes `"lan@example.test"`.
2. **Password is not trimmed.** `"  secret  "` and `"secret"` are two different raw passwords.
3. If a parameter is absent, the filter uses `""`. That does not mean missing fields are accepted or automatically return HTTP 400; the provider usually rejects authentication.
4. `String.trim()` is not equivalent to Unicode canonicalization, case-insensitive email handling, or identity-linking policy. Those must be aligned across registration, DB lookup, login, recovery, and unique constraints.

**Never write** `request.getParameter("password").trim()` in a filter/controller: if a user intentionally chose a password with leading/trailing spaces, modifying the raw credential will cause login to fail.

Never call `toLowerCase` on passwords. Whether account names/emails are case-insensitive is a controlled business decision, not something imposed by parameter names.

## 6. Request Parameters vs. JSON Request Body

`request.getParameter("username")` is not a JSON parser. A standard browser form sends `application/x-www-form-urlencoded`, which the servlet container parses into HTTP parameters.

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&password=secret
~~~

Compare with:

~~~http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"lan","password":"secret"}
~~~

With a JSON body, the default form-login filter **does not automatically read** the two JSON properties. It typically gets null/empty strings from `getParameter`, causing failure. **Merely changing `AuthenticationSuccessHandler` to return JSON does not turn the request into JSON login.**

If the product truly needs JSON login, choose an appropriate authentication filter/converter or controller, parse the body with size limits, build an unauthenticated token, invoke `AuthenticationManager`, and handle session strategy/SecurityContext, CSRF/cookie/CORS, and handlers completely. Never construct an authenticated token from client JSON to "bypass the provider".

### Query Strings Can Still Be a Parameter Source

Servlet request parameters can come from the query string or the body depending on parsing. Therefore, do not assume `getParameter("password")` **only reads the POST body**, and never place passwords in the URL:

~~~text
/login?username=lan&password=secret     <-- UNSAFE
~~~

URLs can end up in proxy logs, browser history, analytics, and Referer headers. Always use HTTPS POST and avoid logging full form bodies or credentials.

## 7. Unauthenticated Token and Trust Boundary

The filter constructs a token like this:

~~~java
UsernamePasswordAuthenticationToken token =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
~~~

This token:

- Has an initial `principal`, usually the username string;
- Has `credentials` equal to the raw password from the request;
- Has `isAuthenticated() == false`;
- Is passed to `AuthenticationManager.authenticate(token)`.

`DaoAuthenticationProvider` can load `UserDetails`, call `PasswordEncoder.matches(raw,stored)`, check locked/disabled/expired status, and return a verified result with authorities from a trusted source.

**Wrong and dangerous:**

~~~java
// Never take roles from an unverified payload and self-grant privileges.
UsernamePasswordAuthenticationToken.authenticated(
        request.getParameter("username"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

The `authenticated(...)` factory does not verify a password. It is an API for trusted code holding valid proof, not a login shortcut bypassing `AuthenticationManager`.

A successful `Authentication` result may contain `UserDetails` and authorities. Never treat the `username` request parameter as proof that the sender owns the account with that name.

## 8. Authentication Details: Metadata Is Not Credentials

`setDetails(HttpServletRequest,UsernamePasswordAuthenticationToken)` attaches metadata provided by `AuthenticationDetailsSource`, which by default can be `WebAuthenticationDetails` such as remote address and session ID.

- An IP address can be a risk-scoring/rate-limit signal, **not proof of identity**.
- Do not blindly trust `X-Forwarded-For` from clients unless reverse proxies are configured as trusted.
- Session IDs and authentication details are sensitive; never return them in public JSON.
- Do not attach raw passwords to details and log the whole token.
- Do not put client-supplied roles/tenants into details expecting providers to treat them as trusted.

If OTP/MFA login is required, use a proper multi-step verification flow per policy rather than concatenating an OTP onto the raw password via an ad-hoc `obtainPassword` override.

## 9. Renaming Parameters via HttpSecurity.formLogin

This is the recommended customization approach in Servlet applications:

~~~java
// Inside HttpSecurity configuration; snippet is not standalone.
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/auth/login")
        .usernameParameter("email")
        .passwordParameter("passcode")
        .defaultSuccessUrl("/home", false)
        .failureUrl("/signin?error")
        .permitAll());
~~~

With that:

| Component | New value |
| --- | --- |
| Page displaying form | `GET /signin` |
| Filter credential-processing URL | `POST /auth/login` |
| Request key for username | `email` |
| Request key for password | `passcode` |
| Success | Matching saved request or `/home` |
| Failure | Typically redirects to `/signin?error` with generic message |

`usernameParameter("email")` **does not automatically turn `UserDetailsService` into "lookup by email"**. It only changes the HTTP key name. If account lookup actually uses email, `UserDetailsService`/repository must recognize that string consistently.

Do not add a `@PostMapping("/auth/login")` just because `loginProcessingUrl("/auth/login")` is configured: Spring Security's filter normally consumes the request before Spring MVC. A separate controller is only needed if you **intentionally design a custom authentication mechanism**.

### When Configuring a Custom Page

`loginPage("/signin")` means the application must be able to render `GET /signin`. If this URL still requires authentication, users can hit a redirect loop. `permitAll()` on form login and the corresponding authorization request matchers must be valid.

## 10. HTML Parameter Names Must Change in Sync

With the `email`/`passcode` configuration, the form must use matching keys:

~~~html
<form th:action="@{/auth/login}" method="post">
  <label for="email">Email</label>
  <input id="email" name="email" type="text"
         autocomplete="username" required>

  <label for="passcode">Password</label>
  <input id="passcode" name="passcode" type="password"
         autocomplete="current-password" required>

  <button type="submit">Sign In</button>
</form>
~~~

This is an **integrated Thymeleaf form snippet**, not a standalone HTML file compatible with CSRF policy by itself. With Spring MVC + Thymeleaf using an appropriate `RequestDataValueProcessor`, `th:action` inserts the hidden CSRF input for POST forms. Always **inspect the actual rendered HTML** to verify the token is present, especially after switching template engines or security config.

Do not only change `placeholder="Email"` or `id="email"` while forgetting to change `name`. Do not hardcode the action URL to another domain if the app runs under a servlet context path; `th:action` builds URLs relative to the application context.

## 11. Renaming Directly on the Filter Only When Truly Needed

If you are building a filter manually for a special use case:

~~~java
UsernamePasswordAuthenticationFilter filter =
        new UsernamePasswordAuthenticationFilter(authenticationManager);

filter.setUsernameParameter("email");
filter.setPasswordParameter("passcode");
~~~

These setters only modify **that instance**. If the `formLogin` DSL already created another filter in `SecurityFilterChain`, changing a separate bean may have no effect.

A manually constructed filter also requires:

- URL/HTTP matcher;
- The proper AuthenticationManager;
- SecurityContextRepository if sessions are needed;
- SessionAuthenticationStrategy (fixation/concurrent sessions);
- Success/Failure handlers;
- Remember-me policy and event publisher;
- CSRF and filter ordering;
- Tests running through the real filter chain.

If you only want different field names, use the DSL instead of subclassing or adding a second filter.

### Protected obtainUsername/obtainPassword

These two methods can be overridden for special protocol needs. However, parsing JSON, adding tenant/multifactor fields, or normalizing passwords in a subclass changes the **authentication protocol**, not just UI customization. Threat modeling and thorough tests are required.

## 12. postOnly and RequestMatcher: Two Different Layers

There are two separate questions:

1. `AbstractAuthenticationProcessingFilter.requiresAuthentication(request,response)`: does the request match the URL/method matcher?
2. `UsernamePasswordAuthenticationFilter.attemptAuthentication(...)`: does `postOnly=true` reject methods other than POST?

In the default setup, the matcher targets `POST /login`. Therefore `GET /login` usually displays the form and **never enters `attemptAuthentication`**. Calling `attemptAuthentication` directly with GET in a unit test causes `postOnly=true` to throw `AuthenticationServiceException`; do not confuse that with GET form behavior in a real chain.

~~~java
// NOT recommended for public form login:
filter.setPostOnly(false);
~~~

Changing this flag **does not change the `POST /login` matcher into GET/POST for every URL**. Moreover, allowing passwords over GET risks URL leaks; never "fix a form bug" by disabling POST-only.

If a form POSTs to `/login` while the DSL processes `/auth/login`, the matcher does not match. The request may then fall through to another filter or controller, returning 404/405/403 rather than `BadCredentialsException`.

## 13. Java 17 Demo: Running the Real Filter and Testing Field Names

The demo invokes **`UsernamePasswordAuthenticationFilter.attemptAuthentication(...)` directly** on mock Servlet requests, using **`ProviderManager` + `DaoAuthenticationProvider` + `PasswordEncoderFactories`** for real password verification. This is a standalone Java 17 program without Spring Boot, a web server, or a DB; it does not test matchers, CSRF, sessions, or redirects, as those belong in integration tests.

The demo shows:

1. Default keys `username,password`;
2. Username is trimmed while password **preserves spaces**;
3. Custom keys `email,passcode`;
4. Forms sending wrong keys or missing password must fail;
5. Passing GET directly to `attemptAuthentication` is rejected.

**To prevent credential erasure from affecting objects stored in memory**, the loader returns a `UserDetails` copy on every authentication attempt. Production systems should also avoid sharing mutable `UserDetails` instances between caches/stores and the authentication principal.

### 13.1. Structure

~~~text
form-parameters-demo/
├── build.gradle
└── src/main/java/example/FormParametersDemo.java
~~~

**build.gradle file:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
    implementation 'org.springframework:spring-web:6.2.19'
    implementation 'org.springframework:spring-test:6.2.19'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.FormParametersDemo'
}
~~~

**src/main/java/example/FormParametersDemo.java file:**

~~~java
package example;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

public final class FormParametersDemo {

    private static MockHttpServletRequest request(
            String method, String userKey, String username,
            String passKey, String password) {

        MockHttpServletRequest req =
                new MockHttpServletRequest(method, "/login");

        if (userKey != null && username != null) {
            req.addParameter(userKey, username);
        }
        if (passKey != null && password != null) {
            req.addParameter(passKey, password);
        }
        return req;
    }

    private static Authentication attempt(
            UsernamePasswordAuthenticationFilter filter,
            MockHttpServletRequest request) {
        return filter.attemptAuthentication(
                request, new MockHttpServletResponse());
    }

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        // Store holds an encoded hash, not the raw password.
        String rawPassword = "  correct-123  ";
        UserDetails account = User.withUsername("lan@example.test")
                .password(encoder.encode(rawPassword))
                .roles("USER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(account);

        // Return a copy so ProviderManager.eraseCredentials does not
        // accidentally erase the password hash from the object in store/cache.
        UserDetailsService users = name ->
                User.withUserDetails(store.loadUserByUsername(name)).build();

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager =
                new ProviderManager(provider);

        UsernamePasswordAuthenticationFilter normal =
                new UsernamePasswordAuthenticationFilter(manager);

        System.out.println("default.keys="
                + normal.getUsernameParameter() + ","
                + normal.getPasswordParameter());

        Authentication first = attempt(normal, request(
                "POST", "username", "  lan@example.test  ",
                "password", rawPassword));

        System.out.println("default.name=" + first.getName());
        System.out.println("default.authenticated="
                + first.isAuthenticated());

        // Password missing spaces => differs from the stored raw password.
        try {
            attempt(normal, request(
                    "POST", "username", "lan@example.test",
                    "password", "correct-123"));
            System.out.println("trimmedPassword=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println(
                    "trimmedPassword=BadCredentialsException");
        }

        UsernamePasswordAuthenticationFilter customized =
                new UsernamePasswordAuthenticationFilter(manager);
        customized.setUsernameParameter("email");
        customized.setPasswordParameter("passcode");

        System.out.println("custom.keys="
                + customized.getUsernameParameter() + ","
                + customized.getPasswordParameter());

        Authentication second = attempt(customized, request(
                "POST", "email", "lan@example.test",
                "passcode", rawPassword));

        System.out.println("custom.name=" + second.getName());
        System.out.println("custom.authenticated="
                + second.isAuthenticated());

        // Send old keys to the filter expecting email/passcode.
        try {
            attempt(customized, request(
                    "POST", "username", "lan@example.test",
                    "password", rawPassword));
            System.out.println("wrongKeys=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println("wrongKeys=BadCredentialsException");
        }

        // Missing password => provider must reject.
        try {
            attempt(customized, request(
                    "POST", "email", "lan@example.test",
                    null, null));
            System.out.println("missingPassword=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println("missingPassword=BadCredentialsException");
        }

        // Call attemptAuthentication DIRECTLY with GET:
        // postOnly=true rejects before credential verification.
        try {
            attempt(customized, request(
                    "GET", "email", "lan@example.test",
                    "passcode", rawPassword));
            System.out.println("getMethod=unexpected");
        } catch (AuthenticationServiceException expected) {
            System.out.println("getMethod=AuthenticationServiceException");
        }
    }
}
~~~

### 13.2. Running

Use **JDK 17+** and a compatible Gradle version; from the `form-parameters-demo` directory:

~~~bash
gradle -q run
~~~

Or `./gradlew -q run` if a wrapper is present; on Windows `gradlew.bat -q run`. Dependencies will be downloaded from Maven Central on the first run.

**Stdout printed by the program itself** (excluding Gradle/library logs if any are configured):

~~~text
default.keys=username,password
default.name=lan@example.test
default.authenticated=true
trimmedPassword=BadCredentialsException
custom.keys=email,passcode
custom.name=lan@example.test
custom.authenticated=true
wrongKeys=BadCredentialsException
missingPassword=BadCredentialsException
getMethod=AuthenticationServiceException
~~~

### 13.3. Interpreting the Output

- `default.keys=username,password` proves the two default names.
- `default.name=lan@example.test`: the filter trims leading/trailing spaces on username, and the provider loads the right user.
- `default.authenticated=true`: the raw password containing spaces matches, and the encoder verifies the hash.
- `trimmedPassword=BadCredentialsException`: passwords are not auto-normalized; stripping spaces produces a different secret.
- `custom.keys=email,passcode`: the two setters change parameter names on **that exact filter instance**.
- `custom.authenticated=true` for the same account: input field naming is unrelated to the hashing algorithm.
- `wrongKeys` and `missingPassword`: the provider rejects when the filter receives empty or missing username/password.
- `getMethod=AuthenticationServiceException`: `postOnly` defaults to true **when `attemptAuthentication` is called**.

**Demo limitations:** It does not pass through `doFilter`, so it **does not test `RequestMatcher`**, CSRF, session fixation, `SecurityContextRepository`, redirects, or success/failure handlers. In practice, `GET /login` typically just renders the form rather than triggering an attempt. Full-chain tests are covered later.

## 14. Complete Configuration-Level Spring Boot Servlet Integration

The snippets below are **integration snippets, not a standalone runnable application**. They assume a Spring Boot Servlet project with Spring Security, Thymeleaf, and an appropriate `UserDetailsService`/`PasswordEncoder` already provided.

### SecurityFilterChain

~~~java
@Configuration
@EnableWebSecurity
class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/signin", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/signin")
                .loginProcessingUrl("/auth/login")
                .usernameParameter("email")
                .passwordParameter("passcode")
                .defaultSuccessUrl("/home", false)
                .failureUrl("/signin?error")
                .permitAll());

        return http.build();
    }
}
~~~

### GET /signin controller

~~~java
@Controller
class LoginPageController {

    @GetMapping("/signin")
    String loginPage() {
        return "signin";
    }
}
~~~

### Thymeleaf template

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Sign In</title>
</head>
<body>
  <p th:if="${param.error}">
    Sign in failed. Please try again or contact support.
  </p>

  <form th:action="@{/auth/login}" method="post">
    <label for="email">Email</label>
    <input id="email" name="email" autocomplete="username" required>

    <label for="passcode">Password</label>
    <input id="passcode" name="passcode" type="password"
           autocomplete="current-password" required>

    <button type="submit">Sign In</button>
  </form>
</body>
</html>
~~~

`th:if` is Thymeleaf syntax evaluated on the server; the error message **does not use `exception.getMessage()`**. Whether the user is locked, disabled, or the username does not exist, the public message should stay generic per the threat model.

CSRF token: with proper Spring MVC + Thymeleaf integration, `th:action` and `RequestDataValueProcessor` can add the hidden input automatically. **Inspect the actual rendered HTML** rather than assuming every template engine inserts CSRF automatically. If writing HTML/JS manually, send the token per your `CsrfTokenRepository` policy.

**Do not declare a POST controller alongside the filter URL** unless intentionally replacing the authentication mechanism. With `loginProcessingUrl("/auth/login")`, Spring Security's filter handles the request.

## 15. CSRF: Right Password Yet HTTP 403

Cookie/session-based browser form login normally requires CSRF protection. `CsrfFilter` can reject a POST missing a token **before `UsernamePasswordAuthenticationFilter` runs**:

~~~text
POST /auth/login
      |
      v
CsrfFilter
      +--> missing/invalid CSRF token -> 403
      |
      v
UsernamePasswordAuthenticationFilter
      |
      v
AuthenticationManager
~~~

Therefore:

- `403` does not automatically mean the password is wrong.
- `AuthenticationFailureHandler` for username/password does not necessarily run.
- Do not disable CSRF globally just so the frontend can log in.
- Check the token in templates, session/cookie, hidden input/header, and token rotation.
- With cookie-auth SPAs, ensure the client sends tokens and cookies per SameSite/CORS policies.
- Stateless APIs using bearer headers have a different threat model; do not apply cookie-auth conclusions mechanically.

A CSRF token **does not** replace a password, and a password does not replace a CSRF token.

## 16. AJAX Frontend with form-urlencoded

A frontend using fetch can keep the standard form-login filter by sending the body in the expected format:

~~~javascript
// Illustrative code, not standalone: csrfToken must be obtained securely from server.
const credentials = new URLSearchParams({
  email: "lan@example.test",
  passcode: "user-entered-password"
});

const response = await fetch("/auth/login", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-CSRF-TOKEN": csrfToken
  },
  body: credentials
});
~~~

Never hardcode real passwords in frontend source; in real UIs the value comes from user input. The CSRF header name depends on server configuration.

With default form login, the server usually **redirects** on success/failure. Following a redirect in `fetch` may return the target HTML page instead of JSON. If the client expects JSON responses, configure `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` to return JSON accordingly; changing response handlers **does not** make the filter parse JSON request bodies.

Ensure session cookies are sent on subsequent requests, and verify CORS policy and SameSite/Secure/HttpOnly attributes. When building custom JSON login, redesign the entire authentication/session/context pipeline rather than just changing Content-Type.

## 17. Multiple SecurityFilterChains: Why Isn't the Filter Running?

An application may have:

~~~text
/api/**  -> stateless bearer resource server
/web/**  -> form login + HTTP session
/**      -> fallback
~~~

If `POST /auth/login` matches the first chain which lacks `UsernamePasswordAuthenticationFilter`, configuring `formLogin` on the second chain will not help. Check:

1. Which `securityMatcher` matches the method/URL;
2. `@Order` across multiple chains and the fallback matcher;
3. Whether `loginProcessingUrl` falls within the active chain;
4. Which filter receives POST and whether there are duplicate filters;
5. Whether `CsrfFilter` or an authorization filter blocks it earlier;
6. Whether a custom login controller exists in another chain;
7. Which providers are configured on the relevant `AuthenticationManager`.

Do not see a `UsernamePasswordAuthenticationFilter` bean in the application context and assume the endpoint actually uses it. A bean/instance may not belong to the active chain.

## 18. Success/Failure Handlers, SecurityContext, and Session

After `AuthenticationManager` returns a result:

| Branch | Main tasks |
| --- | --- |
| Success | SessionAuthenticationStrategy, create/save SecurityContext, remember-me hook, success handler and redirect/response |
| Failure | Clear SecurityContextHolder, remember-me failure hook, failure handler returning generic message |
| Unauthenticated on protected resource | AuthenticationEntryPoint initiates login/challenge |
| Authenticated but missing permissions | Authorization/AccessDeniedHandler, typically HTTP 403 |

In Spring Security 6, `SecurityContextHolderFilter` uses an explicit-save style; built-in form login handles context persistence when properly configured. **A custom login controller calling `authenticate(...)` and `setContext(...)` without `SecurityContextRepository.saveContext(...)` may succeed on the current request while the next request returns 401.**

Do not confuse "next request loses the session" with "wrong parameter names". There are two distinct checks: whether the provider recognized the credentials, and whether the session/token was saved, issued, and sent back properly.

## 19. Preventing Account Enumeration via Login Errors

Failure responses should not vary by specific cause such as:

~~~text
Missing username -> 404 USER_NOT_FOUND
Wrong password   -> 401 WRONG_PASSWORD
Account locked   -> 423 ACCOUNT_LOCKED
Account disabled -> 403 DISABLED
~~~

Attackers can probe status codes, bodies, redirects, or headers to enumerate account existence/state. For unverified endpoints, return a consistent response across sensitive failure cases:

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Sign in failed. Please check your credentials."
}
~~~

`AuthenticationFailureHandler` is the right place to standardize **form authentication failure** responses, not to grant access to locked accounts. Spring Security offers `hideUserNotFoundExceptions` on the DAO provider, but that alone does not address Locked/Disabled responses, timing oracles, rate limits, or signup/recovery leakage.

Server-side auditing can still distinguish internal causes, provided access is restricted and **passwords/hashes/tokens are never logged**. Use rate limiting, monitoring, controlled lockout, and recovery flows to mitigate credential stuffing/brute force.

## 20. Abnormal Inputs: Missing, Duplicate, and Unicode

### Missing parameters

If a request omits the configured field names, `obtainUsername`/`obtainPassword` may return null; the standard filter substitutes `""` before calling the manager. Do not assume that produces HTTP 400. The provider may throw `BadCredentialsException` and the failure handler returns the generic error.

### Duplicate parameters

~~~text
username=lan&username=admin&password=secret
~~~

`getParameter` returns one value from the parameter array. If a reverse proxy/WAF and Servlet container parse duplicates differently, HTTP parameter pollution can occur. Depending on your threat model, inspect/reject duplicate username/password parameters at ingress or a dedicated filter and test against the real servlet container. Never let a client pass `role=ADMIN` to alter authenticated authorities.

### Unicode, length, and canonicalization

Bound request sizes and parameter counts/lengths to mitigate DoS. For usernames/emails, define consistent normalization across registration, login, recovery, and unique DB constraints. **Never normalize raw passwords** into another string during verification. Test Unicode (including non-ASCII characters) under consistent end-to-end encoding.

Do not dump request bodies or session IDs into debug logs; log only request IDs, outcomes, and controlled metadata.

## 21. Separating the Roles of Unit Tests and Integration Tests

**Unit-level**: call `attemptAuthentication(...)` as in the Java demo to verify parameter keys, trimming, and provider behavior. These tests **bypass** URL matchers, CSRF, and `SessionAuthenticationStrategy`.

**Integration-level**: send HTTP requests through `SecurityFilterChain` and verify:

| Scenario | Expectation |
| --- | --- |
| GET login page | Form renders for anonymous user |
| POST right URL, right names, valid credentials + CSRF | Succeeds, correct session/redirect |
| POST valid credentials with old keys when filter expects new keys | Fails |
| POST missing CSRF | Blocked per CSRF policy; handler may not run |
| POST JSON to default filter | Not auto-parsed as form params |
| POST wrong URL/method | Does not hit form-login matcher |
| Username with spaces | Trimmed per standard behavior |
| Password with spaces | Preserved as raw credential |
| Unknown/locked/disabled account | Rejected, no authenticated session issued |
| Second request with session cookie | Receives right Authentication if stateful |
| GET credentials in URL | Not supported as a safe login mechanism |
| Multiple filter chains | Correct chain/matcher/provider/handlers |
| Logout | Session/context destroyed per policy |
| Rate limit/brute force | Throttling works without leaking userExists via 429 |

### Spring Security Test Illustration (Not Standalone)

~~~java
// Requires MockMvc, Spring Security Test, and real app config.
mvc.perform(post("/auth/login")
        .with(csrf())
        .param("email", "lan@example.test")
        .param("passcode", "correct-password"))
    .andExpect(authenticated());

mvc.perform(post("/auth/login")
        .with(csrf())
        .param("username", "lan@example.test")
        .param("password", "correct-password"))
    .andExpect(unauthenticated());
~~~

The response may be a 302 redirect with HTML formLogin, or 200/401 JSON if JSON handlers are configured; status assertions must match the actual contract. After successful login, test a follow-up request using the issued session cookie/id. Do not test `ControllerAdvice` in isolation and assume you tested the authentication filter: `AuthenticationException` is typically caught by the filter and delegated to the failure handler.

## 22. Common Errors and Root-Cause Lookup Table

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Valid input always fails | HTML `name` differs from backend names | Align `usernameParameter`/`passwordParameter` with form |
| GET /signin redirect loop | Custom login page lacks permitAll | Permit the loginPage for anonymous access |
| POST returns 404/405 | Wrong `loginProcessingUrl` or chain matcher | Check method, action, and context path |
| POST returns 403 despite right password | Missing/invalid CSRF token or another filter blocking | Inspect CsrfFilter and rendered token |
| POST JSON does not authenticate | Default filter reads request parameters | Use form-urlencoded or a dedicated JSON auth flow |
| Passwords with spaces always fail | Frontend/custom code trims password | Remove raw password transformation |
| Trimmed username hits wrong account | Inconsistent DB/service normalization | Standardize identity lookup and unique keys |
| Manually created filter's handlers don't run | Filter instance not wired into active chain | Prefer formLogin DSL or wire the exact instance |
| Changed keys yet frontend sends old ones | Frontend/backend deploy out of sync | Compatible rolling deploy and integration tests |
| ControllerAdvice doesn't catch BadCredentials | Filter already handled the exception | Configure AuthenticationFailureHandler |
| Login 200 but next request 401 | Custom flow forgot SecurityContextRepository/session | Explicit save and cookie/session strategy |
| Wrong username vs. locked account differ | Enumeration oracle | Generic response, internal audit |
| GET credentials appear in query string | Form uses GET or bad JS | Use POST + TLS, never log URLs with secrets |
| Duplicate parameters behave inconsistently | HTTP parameter pollution | Validate/reject duplicates and test ingress |
| Login succeeds but redirects to wrong URL | RequestCache/defaultSuccessUrl/handler | Verify saved request and target |
| Filter intercepts API endpoint by mistake | Multiple chains/order/matchers | Separate web form and stateless API chains |
| Login slows down after BCrypt cost change | CPU hashing + brute force | Benchmark, rate limit, and plan capacity |
| User gains wrong role from request | App creates trusted token from input | Use only provider-verified authorities |
| Browser has JSESSIONID before login | RequestCache/failure handler/other component created session | Trace session creation rather than assuming auth succeeded |

**Low-risk debugging sequence:** inspect method/URL/content-type/names in DevTools (without capturing real passwords); verify `SecurityFilterChain`; check CSRF; check provider/encoder/account flags; finally verify cookies/session and redirects.

## 23. Implementation Checklist

1. Form method `POST` over HTTPS.
2. `form action` matches `loginProcessingUrl`.
3. HTML `name` matches `usernameParameter`/`passwordParameter`.
4. GET login page is open to anonymous users with no redirect loop.
5. `UserDetailsService` supports the submitted identity value (username/email).
6. PasswordEncoder hashes/verifies properly; raw password is not trimmed or case-folded.
7. CSRF protects browser cookie-auth; token is rendered and submitted properly.
8. Never put credentials in query URLs or logs.
9. Never construct authenticated tokens from client payloads.
10. Success/failure handlers return UI-appropriate contracts without leaking account state.
11. AuthenticationManager/provider is on the right chain, with no duplicate filters.
12. Built-in form flow handles session fixation/context persistence; custom flows must include all of them.
13. Test passwords with spaces, usernames with spaces, and Unicode/encoding.
14. Test missing/duplicate parameters and oversized requests.
15. Test that POST JSON is not misinterpreted as form parameters.
16. Test logout, remember-me, and follow-up requests with the session.
17. Rate limiting/CAPTCHA must not create an account enumeration oracle.
18. Do not treat `id`/`placeholder` as HTTP parameter names.
19. Use aligned Spring Security/Spring Framework versions via BOM whenever possible.
20. Auditing, monitoring, and support tools never retain raw passwords/tokens.

## 24. Self-Check Questions

**1.** Which URL/method does the default filter accept?  
**Answer:** `POST /login` with default `UsernamePasswordAuthenticationFilter`. `GET /login` is normally the form page.

**2.** What are the two default parameters?  
**Answer:** `username` and `password`, based on HTTP parameter names.

**3.** HTML has `id="email"` but `name="username"`; which key does the filter read?  
**Answer:** `username`; `id` is not a request parameter name.

**4.** Does changing `usernameParameter("email")` automatically make DB lookup query by email?  
**Answer:** No. It only changes the request key; `UserDetailsService` must support that identity lookup.

**5.** Does the filter verify the BCrypt hash itself?  
**Answer:** No. It passes an unauthenticated token to `AuthenticationManager`; the provider/`PasswordEncoder` verifies it.

**6.** Are username and password trimmed the same way?  
**Answer:** No. Username is trimmed by the standard filter, while password is not trimmed.

**7.** Will sending `application/json` automatically be read by `obtainUsername`?  
**Answer:** Not by default; you need form-urlencoded or a dedicated JSON authentication integration.

**8.** Why can a POST with the right password return 403?  
**Answer:** CSRF may reject the request before the auth filter runs; inspect the CSRF token and filter chain.

**9.** Does `postOnly=true` mean every `GET /login` throws `AuthenticationServiceException`?  
**Answer:** No. The default matcher normally does not route GET into `attemptAuthentication`. Calling the method directly with GET triggers the rejection.

**10.** Does `UsernamePasswordAuthenticationToken.authenticated(...)` verify username/password?  
**Answer:** No. Never use it with unverified client input.

**11.** Does changing `loginPage` automatically change `loginProcessingUrl`?  
**Answer:** They are distinct concepts; configure both explicitly when needed so the GET page and POST processing are not confused.

**12.** Does a passing unit test on `attemptAuthentication` guarantee subsequent browser requests remain logged in?  
**Answer:** No. You must test the filter chain, session strategy, `SecurityContextRepository`, cookies, and redirects.

**13.** Why shouldn't passwords be placed in query strings even over HTTPS?  
**Answer:** URLs can still be recorded in browser history, server/proxy logs, analytics, and elsewhere.

**14.** When a request sends the right password with mismatched field names, should the response reveal "username does not exist" for easier debugging?  
**Answer:** No. Public responses must protect account existence/state; debug via secure internal telemetry.

**15.** If an app has both a bearer API and form login, does the form filter handle every API request?  
**Answer:** No. Each `SecurityFilterChain`/`RequestMatcher` has its own scope and authentication mechanism.

## 25. Official References

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): GET login page, POST form, `username`/`password`, CSRF, and authentication filter flow.
- [UsernamePasswordAuthenticationFilter API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html): `attemptAuthentication`, `obtainUsername`, `obtainPassword`, parameter setters, and `setPostOnly`.
- [FormLoginConfigurer API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html): `loginPage`, `loginProcessingUrl`, `usernameParameter`, and `passwordParameter`.
- [AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): RequestMatcher, success/failure, context, and session strategy.
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): matching raw passwords against hashes and handling account state.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): AuthenticationManager, ProviderManager, and Authentication tokens.
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF protection for form/cookie authentication.
- [Spring Security 6.5 – Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation and context persistence.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication failures, anti-enumeration, and brute-force mitigation.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): secure password hash storage.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF tokens/headers for browser flows.

**Conclusion:** `UsernamePasswordAuthenticationFilter` turns **HTTP parameters → unauthenticated token → AuthenticationManager**. By default it handles **`POST /login`** and reads **`username`/`password`** via Servlet `getParameter`; use `FormLoginConfigurer` to rename them in sync with HTML. Username is trimmed while password is preserved verbatim. A proper login flow also requires CSRF, provider/encoder, filter matchers, handlers, and session/context persistence—not just two input fields.
