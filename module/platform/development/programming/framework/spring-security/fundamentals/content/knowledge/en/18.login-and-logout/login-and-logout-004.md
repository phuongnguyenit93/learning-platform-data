# JSON Login Is an Input Format, Not a Session or Token Model

## 1. Goal: separate the HTTP format from the login persistence strategy

An API often receives login credentials in JSON format:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"demo123"}
~~~

Looking at that JSON body alone, **you cannot conclude whether the app uses sessions or JWTs**. JSON is merely **how data sent to the endpoint is encoded**; it does not define how the server verifies the password, stores Authentication, confirms identity on the next request, or logs out.

The exact same JSON POST request can lead to several valid designs:

- **Stateful/session login**: the server authenticates and then saves the SecurityContext state in HttpSession. The client receives and sends back a session cookie on later requests.
- **Token-based login (often stateless)**: the server authenticates and then issues an access token; the client sends the token via Authorization: Bearer on subsequent requests; the server validates the token on each request.
- **Hybrid model**: JSON login issues a token stored in a cookie, or the system uses sessions for web and Bearer tokens for API/mobile. You must read the actual configuration to determine which parts remain stateful.

Lesson objectives:
1. Distinguish **JSON request body**, **authentication**, **authorization**, **SecurityContext**, **HttpSession**, **session cookie**, and **access token**.
2. Understand why a successful JSON POST does not automatically give the next GET an Authentication.
3. Write a Spring Boot 3.x + Spring Security 6.x, Java 17+ example using JSON login **and sessions**, with explicit SecurityContext persistence.
4. Sketch the Bearer token flow accurately without mistaking returning a token string in JSON for complete security.
5. Properly design CSRF, session fixation, cookies, HTTPS, logout, lifetimes, and failed login handling.
6. Diagnose the issue "POST /api/login returns 200 but the next request returns 401."

**Core principle:** *The credential transport format* and *the mechanism for persisting/verifying identity across requests* are two **independent** decisions, even though they are often implemented in the same login flow.

## 2. Separating the layers in a login flow

| Component | What question does it answer? | What it does NOT mean |
| --- | --- | --- |
| **Content-Type: application/json** | What format is the client using to send data? | The app must use JWT or be stateless |
| **@RequestBody LoginRequest** | How does the server read username/password fields from the body? | The password has been verified |
| **AuthenticationManager.authenticate(...)** | Are the credentials valid according to the configured AuthenticationProviders? | The identity has been persisted to the next request |
| **Authentication** | What are the principal, authorities, and authentication status for this execution? | A session cookie or JWT |
| **SecurityContext** | Where is the current Authentication placed for authorization to read? | A storage mechanism with an unlimited lifetime |
| **SecurityContextRepository** | Is the context loaded/saved across requests, and where is it stored? | HttpSession must be used in every application |
| **HttpSession + JSESSIONID** | How does the server associate multiple requests via a session? | The cookie contains the entire Authentication |
| **Access token** | How are credentials for subsequent requests issued and verified? | Any arbitrary string is automatically secure |
| **Authorization** | Does the authenticated user have permission to call the endpoint? | Equivalent to POST /api/login succeeding |

On Spring Security Servlet, **SecurityContextHolder** provides the active security context for the current processing thread. After the request, the filter chain manages clearing the context. With sessions, the next GET can load the SecurityContext saved in the session; with Bearer tokens, the next GET can construct Authentication from the token sent by the client in that request.

### 2.1. Three questions to ask when reviewing a login API

**Question 1 – Input ingestion:** Does the endpoint accept JSON, application/x-www-form-urlencoded, HTTP Basic, OAuth2 redirect, or another mechanism? This is how credentials enter the system.

**Question 2 – Authentication:** Does the server use UserDetailsService + PasswordEncoder, an identity provider, LDAP, OIDC, or an external authentication service to verify identity? The outcome is an Authentication or an error; JSON syntax does not dictate the verification source.

**Question 3 – Identity persistence:** After successful authentication, does the server save SecurityContext in HttpSession, return an access token, or require fresh credentials on the next request? This architectural decision affects clients, CSRF, logout, scaling, and operations.

Do not collapse these three questions into the assumption "JSON login = token."

## 3. Two flows with identical JSON input but different next steps

### 3.1. Case A: JSON login + server-side session

~~~text
Client                             Spring Boot / Spring Security
  | POST /api/login
  | Content-Type: application/json
  | {"username":"alice","password":"..."}
  |------------------------------------>
  |                                      Parse JSON
  |                                      AuthenticationManager.authenticate()
  |                                      Authentication succeeds
  |                                      Create SecurityContext
  |                                      SecurityContextRepository.saveContext(...)
  |                                      Save SecurityContext tied to HttpSession
  |<------------------------------------
  | HTTP 200 + Set-Cookie: JSESSIONID=...
  |
  | GET /api/me
  | Cookie: JSESSIONID=...
  |------------------------------------>
  |                                      Load SecurityContext from session
  |                                      Get Authentication and check permissions
  |<------------------------------------
  | HTTP 200 {"username":"alice"}
~~~

**The cookie here carries a session ID**, not a JWT and not the raw JSON of Authentication. The server typically manages session attributes; with multiple server instances, you may need Spring Session or an appropriate session storage strategy.

If the client forgets to send the cookie, sends it with the wrong scope/domain/path, or the session has expired, the next request may be treated as unauthenticated even though the earlier JSON POST returned 200.

### 3.2. Case B: JSON login + Bearer access token

~~~text
Client                             Authentication/Token Service
  | POST /api/login
  | Content-Type: application/json
  | {"username":"alice","password":"..."}
  |------------------------------------>
  |                                      Parse JSON + authenticate()
  |                                      Issue controlled access token
  |<------------------------------------
  | HTTP 200 {"access_token":"<token>","token_type":"Bearer"}
  |
  | GET /api/me
  | Authorization: Bearer <token>
  |------------------------------------>
  |                                      Verify signature or introspection
  |                                      Check expiration, issuer, audience, permissions
  |                                      Create Authentication for request
  |<------------------------------------
  | HTTP 200 {"username":"alice"}
~~~

Here the server may not store an HttpSession to restore identity on the next request. Yet a token-issuing system may still maintain **refresh tokens, revocation lists, login sessions at the authorization server, or device state** somewhere. Therefore, "Bearer token" does not mean "the entire system has no state."

**Not every token is a JWT.** An access token can be an opaque string requiring introspection, or a signed and verified JWT. Simply adding three dot-separated segments to a JSON response does not make a system secure JWT authentication.

### 3.3. Pragmatic comparison table

| Criterion | JSON login + HttpSession | JSON login + Bearer token |
| --- | --- | --- |
| Login body | Can be JSON | Can be JSON |
| What does server do after authentication? | Saves SecurityContext into session/repository | Issues token per policy; resource server validates token on requests |
| What does client send on next GET? | Valid session cookie | Authorization: Bearer token (or chosen token transport mechanism) |
| Restoring Authentication | From session/repository | From credential/token verification result for the request |
| Revoking access | Can invalidate session | Depends on token: short-lived tokens, introspection, revocation list, rotation… |
| CSRF | Especially important when browsers auto-send session cookies | Depends on how credentials are sent by browser; Bearer in Authorization header is not auto-attached like cookies |
| XSS | Application must be protected; HttpOnly helps restrict JS reading cookies | Tokens in JS-accessible storage risk theft via XSS; storage choice must fit threat model |
| Scaling across servers | Needs proper session sharing/affinity | Self-verifying JWT reduces session lookups; still needs key rotation/revocation where appropriate |
| Logout | Usually invalidates session + clears SecurityContext | Client discards token; may need to revoke refresh/access tokens if policy requires |
| Proving permissions | Authorities from Authentication stored in context | Authorities usually from token claims/introspection and converter |

**These are two architectural models, not intrinsic properties of Content-Type.**

## 4. Spring Security 6: successful login is not automatically persisted

A custom JSON login endpoint might do:

~~~java
Authentication auth = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password));
~~~

The code above requires an AuthenticationManager configured with a Provider capable of authenticating username/password. On success, it returns an appropriate Authentication, but **does not automatically ensure SecurityContext is written to HttpSession**.

In Spring Security 6.x, context persistence requires attention to **SecurityContextRepository**. If a custom controller sets Authentication without saving it, the current request may read Authentication from SecurityContextHolder, while the next request receives none of that state.

Core pattern for session persistence:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(auth);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

This is only a **fragment**, not a complete secure login flow. In a Servlet application, a standard filter/form login also handles the session authentication strategy (e.g., session fixation protection), authentication events, context persistence, and other policies. If you build a custom login controller, you must design those steps yourself rather than assuming those four lines are enough.

On the other hand, if you choose Bearer tokens, you must **issue valid tokens** and configure **token validation** for subsequent requests. Merely adding:

~~~java
return Map.of("token", "some-string");
~~~

does not create a working Bearer authentication system; if the server does not verify the token and build an Authentication on new requests, GET /api/me will still be rejected.

## 5. Runnable demo: JSON POST yet maintaining login via HttpSession

Demo objective: prove that a **POST /api/login accepting JSON** keeps subsequent **GET /api/me requests** authenticated via cookie/session. The example keeps **CSRF enabled** (including login), uses a cookie jar when running curl, performs explicit **SecurityContextRepository** saving, and applies **ChangeSessionIdAuthenticationStrategy** to mitigate session fixation within the scope of the lesson.

### 5.1. Preparing the project

Create a project from Spring Initializr:

- **Spring Boot 3.x**, **Java 17+**, **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** (spring-boot-starter-web) and **Spring Security** (spring-boot-starter-security).

Create exactly one source file:

~~~text
src/main/java/com/example/demo/JsonLoginSessionApplication.java
~~~

The program has one public class matching the filename; config/controller classes in the same package are package-private for Spring Boot component scanning.

### 5.2. Complete Java code

~~~java
package com.example.demo;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class JsonLoginSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginSessionApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy() {
        return new ChangeSessionIdAuthenticationStrategy();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .securityContext(context -> context
                .securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, auth) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"status\":\"logged_out\"}");
                })
                .permitAll())
            .build();
    }
}

@RestController
class AuthApi {

    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    AuthApi(AuthenticationManager manager,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    // GET issues a CSRF protection token to the client; stored in session by default.
    @GetMapping("/api/csrf")
    Map<String, String> csrf(CsrfToken token) {
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken());
    }

    public record LoginRequest(String username, String password) {
    }

    public record LoginResult(String username, String mode) {
    }

    @PostMapping(path = "/api/login",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    LoginResult login(@RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {
        try {
            Authentication authentication = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()));

            // Custom controller must explicitly apply
            // the required session authentication steps.
            sessionStrategy.onAuthentication(
                authentication, request, response);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);

            // Choose session model and save explicitly.
            repository.saveContext(context, request, response);

            return new LoginResult(authentication.getName(), "session");
        } catch (AuthenticationException ex) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED,
                "Invalid username or password");
        }
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin(Authentication authentication) {
        return Map.of("message", "admin-only",
                      "username", authentication.getName());
    }
}
~~~

**Code explanation:**

- Spring MVC uses Jackson (via Spring Web) to deserialize the JSON body into **LoginRequest**; **consumes = application/json** checks the endpoint's media type.
- **AuthenticationManager** is configured with **DaoAuthenticationProvider**, **UserDetailsService**, and **PasswordEncoder**. UserDetailsService only holds two demo users for easy verification.
- **AuthenticationException** produces a generic 401 response without disclosing which user exists; passwords are never logged.
- **SessionAuthenticationStrategy** is invoked after authentication to rotate the session ID when an applicable session exists; this demonstrates session fixation protection for a custom flow. Standard mechanisms can also add concurrency handling and CSRF token rotation depending on policy.
- **SecurityContextRepository** in the example is HttpSessionSecurityContextRepository. The same instance is passed to both HttpSecurity and the login controller, avoiding saving into repository A while the security filter reads repository B.
- **SecurityContextHolder.setContext** lets code within the current request see Authentication; **saveContext** is the step that persists login to the next request.
- **CSRF enabled by default**: JavaScript/browsers/curl must fetch the token from GET /api/csrf and send it in the header on POST login or logout. Simply using JSON does not exempt you from CSRF checks.
- **Form login and HTTP Basic are disabled** in the demo to clearly demonstrate the JSON endpoint managing authentication itself. HTTP Basic is not used as a fallback login mechanism here.
- **Standard LogoutFilter** handles **POST /api/logout**, invalidates the session via default logout handlers, and returns JSON; this endpoint is not a method on AuthApi.
- **PasswordEncoderFactories.createDelegatingPasswordEncoder()** creates password hashes using an appropriate default; the password demo123 in source is for learning only. Real environments must use a proper user store and password policy.
- **GET /api/admin** requires role ADMIN (authority ROLE_ADMIN); successful authentication does not grant admin permissions automatically.

**Demo limitations:** No rate limiting, MFA, audit logging, account lockout, full security event handling, distributed session store, or deep hardening tests. Production applications should prefer standard maintained login mechanisms, or implement a custom authentication filter with fuller session/concurrency/CSRF strategies. This code illustrates session-based context persistence, not a production-ready authentication package.

### 5.3. Running the program

At the root directory of the created Gradle project:

~~~bash
./gradlew bootRun
~~~

On Windows use **gradlew.bat bootRun**. By default, the application listens on **http://localhost:8080** unless server.port is changed.

### 5.4. Testing session-based login with curl

The example below uses **Bash + Python 3** to extract the token from JSON. Create a temporary cookie jar in the working directory to ensure subsequent requests send **the exact session cookie**.

~~~bash
# 1. Request a CSRF token and save the session cookie.
curl -s -c cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

# 2. Read the token from JSON (without needing jq).
CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf.json'))['token'])")

# 3. POST JSON, sending the same cookie + CSRF token.
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-TOKEN: $CSRF" \
  -d '{"username":"alice","password":"demo123"}' \
  http://localhost:8080/api/login

# 4. New request: no password sent, only the cookie.
curl -i -b cookies.txt http://localhost:8080/api/me

# 5. Alice does not have ROLE_ADMIN.
curl -i -b cookies.txt http://localhost:8080/api/admin

# 6. No cookie sent: not considered logged in.
curl -i http://localhost:8080/api/me
~~~

**Expected HTTP results from the configuration**:

| Turn | Expected result | Reason |
| --- | --- | --- |
| GET /api/csrf before login | **200** JSON token, cookie for CSRF/session as needed | Public endpoint and token initialized on demand |
| Valid POST /api/login, right cookie + CSRF | **200**, JSON with username=alice, mode=session | AuthenticationManager authenticates and context is saved to session |
| GET /api/me with cookie after login | **200**, JSON with username=alice | SecurityContextRepository loads context from session |
| GET /api/admin with alice cookie | **403** | Alice lacks ROLE_ADMIN |
| GET /api/me without cookie | **401** | No Authentication restored |
| POST /api/login wrong password, valid CSRF | **401** | AuthenticationManager rejects credentials |
| POST /api/login missing/wrong CSRF token | **403** | CSRF filter blocks before controller |

**These are theoretical predictions, not actual execution logs.** Cookie flags, headers, and error bodies may vary with Spring Boot/Spring Security configuration, proxies, and environment. The 200 login response may include a Set-Cookie with a new session ID due to session fixation protection; curl uses **-c cookies.txt** to save cookie updates.

**Note when re-running the demo:** The GET /api/csrf command retrieves the token before login. In real systems, the CSRF token may be actively refreshed after authentication; if so, the client must fetch the new token before the next POST. For SPA apps, Spring Security has specific considerations for deferred CSRF tokens and BREACH protection.

### 5.5. Logout

Because CSRF is enabled and logout uses POST, a valid token must be sent along with the session cookie. Within the demo, after login you can GET /api/csrf once more to obtain the current token and then POST /api/logout:

~~~bash
curl -s -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/api/logout

# Subsequent GET no longer has Authentication from the logged-out session.
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected result: successful logout returns **200** and JSON **{"status":"logged_out"}**; GET /api/me afterward returns **401** because the security session is no longer valid.

**Logout is not just returning 200 in JSON.** The server must invalidate the session/security context, and clear or revoke credentials according to the chosen model. With standalone access tokens, deleting the JSESSIONID cookie does not automatically invalidate the token.

## 6. Token model: both issuance and verification are required

An endpoint might return JSON like:

~~~json
{
  "access_token": "token-value",
  "token_type": "Bearer",
  "expires_in": 900
}
~~~

This is a **structural example**, not a real JWT and not a usable token. If an application chooses Bearer tokens, it must decide at minimum:

1. **Token type:** JWT or opaque reference token?
2. **Who issues it?** Which trusted Authorization Server or token service?
3. **Who verifies it?** Does the resource server verify signatures/JWK or introspection, issuer, audience, expiration, and other constraints?
4. **Where do permissions live?** How are claims or introspection responses mapped to GrantedAuthority?
5. **Where does the client store the token?** Browser memory, cookie, native app storage; evaluate XSS/CSRF for the chosen option.
6. **How long does the access token live?** TTL, refresh token rotation, token revocation, multi-device logout.
7. **Are HTTPS, rate limiting, and password brute-force protection in place?** Tokens cannot compensate for weak transport or a weak login endpoint.

Spring Security OAuth2 Resource Server can validate tokens issued by a compatible system. The example is **only a configuration fragment**, requiring the OAuth2 Resource Server starter and a valid issuer/JWK:

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/me").authenticated()
        .anyRequest().denyAll())
    .oauth2ResourceServer(oauth -> oauth.jwt());
~~~

This snippet **does not issue JWTs**. The resource server uses the corresponding JWT decoder/issuer configuration to validate tokens on incoming requests; do not assume the JSON login endpoint from the session example automatically generates access tokens just by adding oauth2ResourceServer.

A client sends:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Bearer eyJ...example...
~~~

The resource server considers the request authenticated only if the token **is genuinely valid and configured for the right issuer**. A random string or a self-asserted JWT claiming admin rights that the server does not trust must be rejected.

### 6.1. Does a token in a cookie equal a session?

No. A cookie is a **client-side transport/storage mechanism for a value**; it can hold a session ID, a JWT, an opaque token, or another value depending on design. If the browser automatically attaches cookies to requests, **CSRF** must still be evaluated for state-changing operations. Wrapping a token in an HttpOnly cookie does not make the system immune to CSRF.

Conversely, an access token explicitly placed by JavaScript into the **Authorization** header is not auto-attached by the browser like a cookie, yet storing tokens in a web app requires evaluating XSS, token theft, and API origin restrictions. Separate **credential format**, **transport**, **storage**, **server validation**, and **session persistence** to avoid absolute claims.

### 6.2. JWT is not Spring Security's default session

A request carrying a valid JWT can be authenticated independently of HttpSession. Within each request, Spring Security still creates/maintains Authentication in SecurityContext **while processing that request**; not using HttpSession only means that context is not persisted by a server-side session for the next GET. Once the request ends, the holder is cleared according to the filter lifecycle.

**Stateless does not mean there is no SecurityContext**, and **having a SecurityContext does not mean HttpSession was used**.

## 7. Security specifics when using JSON login

### 7.1. CSRF does not depend on Content-Type in a simple way

A browser using session cookies may automatically attach cookies according to cookie policy, creating CSRF risk on state-changing requests. Sending **application/json** often triggers CORS/preflight for cross-origin requests, yet that **is not a general replacement for CSRF protection**.

Decide on CSRF based on how credentials are auto-attached by browsers and your threat model:
- Session cookie/browser web app: normally keep CSRF protection and supply tokens for POST/PUT/PATCH/DELETE.
- Bearer token API placed strictly in the Authorization header explicitly by the client: typically has a different CSRF model; still protect tokens from XSS and audit any auto-sent cookies/credentials.
- JWT in a cookie: still evaluate CSRF; the "JWT" label grants no exemption.
- Do not disable CSRF system-wide merely for convenience when testing JSON with curl.

### 7.2. HTTPS, cookies, and session fixation

In production, login must run over **HTTPS**. For sessions:
- Enable the **Secure** cookie flag in the appropriate HTTPS environment; use **HttpOnly** for session cookies.
- Set **SameSite**, Path, and Domain appropriately for your cross-origin/cross-site architecture.
- Use session fixation protection (rotating the session ID at login where appropriate).
- Configure session timeout, invalidate sessions on logout, and handle sessions across multiple replicas.
- Never send session IDs in URLs or JSON responses, and never log Cookie/Set-Cookie or passwords.

CORS only controls browser behavior for cross-origin requests; it **does not authenticate identity** and grants no business permissions. With a cross-origin frontend, configure CORS, credentials, and cookie policy properly while keeping server-side authentication and authorization.

### 7.3. Brute-force and enumeration protection

Return the same error message for nonexistent usernames and wrong passwords, such as **401 Invalid username or password**. Also implement rate limiting/throttling, anomaly monitoring, MFA when appropriate, sensible lockout/backoff policies, and avoid disclosing account existence through observable response differences.

Never store plaintext passwords in sessions or logs. When using UserDetailsService, use an appropriate PasswordEncoder (e.g., BCrypt or another strong configured algorithm) and manage password resets and credential changes properly.

### 7.4. Checking permissions after login

**Successful login does not automatically grant administrative privileges.** Authentication carries authorities, and authorization policies can still require ROLE_ADMIN, report:write, or ownership/tenant conditions.

If the app saves Authentication in the session, permissions in the context may reflect login time; if roles are revoked mid-session, you need a strategy to refresh or enforce revocation. With JWTs carrying claims, permission data can likewise persist until token expiration unless the system adds revocation/supplementary checks.

### 7.5. Do not return unnecessary credentials in JSON

After POST login, the response in the session model can simply be:

~~~json
{"username":"alice","mode":"session"}
~~~

There is no need to return the password, credential hash, session ID, or the entire Authentication object for the client to know login succeeded. Conversely, a token model returns the access token per the chosen standard over a secure channel; avoid exposing tokens where logs or analytics might collect them.

## 8. Integration testing for session-based JSON login

A good test must exercise **two separate requests**, not merely assert POST /api/login returns 200. If the second request lacks the cookie, or login fails to save SecurityContext, the test will expose it.

In the demo's Gradle project, add test dependencies if not already present:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **build.gradle fragment**; Spring Initializr usually already includes starter-test—avoid duplicate declarations.

Create **src/test/java/com/example/demo/JsonLoginSessionApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginSessionApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonLoginPersistsAuthenticationInSession()
            throws Exception {

        MvcResult login = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"alice\",\"password\":\"demo123\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("session"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/admin").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows use **gradlew.bat test**. The test uses **MockMvc and the CSRF test helper** to focus on proving that after JSON POST, Authentication is persisted into the same HttpSession, while a GET without a session is treated as unauthenticated. The test code reflects expected behavior per the lesson configuration; Gradle was not run in this content.

For production systems, additionally test:
1. Wrong-password login returns 401 and creates no authenticated session.
2. POST login missing CSRF token is rejected.
3. Logout invalidates the session; GET /api/me after logout returns 401.
4. Session fixation protection works properly when a pre-login session exists.
5. Session timeout, cookie flags, cross-origin frontends, revoked permissions, and concurrent sessions.
6. Admin endpoints allow only users with ROLE_ADMIN.
7. Passwords, tokens, and session identifiers are never logged or echoed.

## 9. Common misconceptions

| Claim or symptom | Problem | Correct analysis |
| --- | --- | --- |
| "POST login accepts JSON so it definitely uses JWT." | Confuses body encoding with auth persistence | Check response, cookies, token service, and security config. |
| "Login returned 200 so GET /me is definitely authenticated." | Context may not be saved or client may not send credentials | Check saveContext, repository, Set-Cookie/Cookie, or Authorization header. |
| "Having JSESSIONID means the user is logged in." | Session may exist for CSRF, request cache, or other data | Inspect the actual Authentication inside SecurityContext. |
| "No JSESSIONID means no SecurityContext." | Token authentication still uses context per request | Check resource-server/Bearer configuration. |
| "JWT and cookies are mutually exclusive." | JWTs can also be transported in cookies | Separate token format from transport/storage. |
| "Putting a token in an HttpOnly cookie prevents CSRF." | Browsers can automatically attach cookies | Evaluate CSRF by request type and cookie policy. |
| "Disabling CSRF is mandatory to accept application/json." | Confuses CSRF with JSON parsing | Use CSRF headers and proper client handling if protecting a session. |
| "SecurityContextHolder.setContext is enough to stay logged in." | Spring Security 6 custom flows require explicit save | Call SecurityContextRepository.saveContext when persisting. |
| "A token returned from login is automatically verified by Spring on the next GET." | Validation/decoder/introspection is not yet configured | Configure Resource Server or an appropriate authentication filter. |
| "JSON logout returning 200 revoked all tokens." | Stateful logout and token revocation differ | Design invalidation/revocation for the credentials in use. |
| "Every GET returning 403 is due to a wrong password." | 401, 403, CSRF, roles, and matchers differ | Check status, Authentication, GrantedAuthority, and policy order. |
| "The cookie holds UserDetails as JSON." | Standard sessions usually store only a session ID in the cookie | Look for data in the server-side session store. |
| "Stateless removes the need to protect tokens." | The token becomes the critical credential | Protect HTTPS, token storage, TTL, rotation/revocation, audience/issuer. |
| "Sessions must hit the same server instance." | A shared session store can be used | Design topology/Redis/Spring Session/affinity per requirements. |

## 10. Architectural decision checklist

Before introducing a JSON login endpoint into a system, answer:

1. **Who is the client?** Server-rendered browser, SPA, mobile app, or service-to-service?
2. **What is the input credential?** Username/password, passkey, OTP, OIDC authorization code, or something else? A JSON body alone does not describe it.
3. **Who authenticates?** Internal AuthenticationManager, identity provider, or authorization server?
4. **How do subsequent requests authenticate?** Session cookie, Bearer token, mTLS, or another mechanism?
5. **Who stores/revokes state?** HttpSession store, token service, revocation list, refresh token store?
6. **Is CSRF needed?** Can browsers auto-send cookies/credentials on cross-site requests?
7. **What are the lifetimes?** Session idle timeout, access-token TTL, refresh token expiration and rotation.
8. **Where does logout take effect?** Server session invalidation, refresh token revocation, client deletion, all devices?
9. **When are permissions computed?** Login time, every request, or upon role change?
10. **Have two independent requests been tested?** A successful POST login and a protected GET with/without appropriate credentials?
11. **Are HTTPS, cookie flags, CORS, and brute-force login protections configured?**
12. **Are standard Spring Security mechanisms used wherever possible?** Custom login/controllers must cover the steps standard filters already handle.

**Conclusion:** **JSON login only determines how credentials are received.** If you want **sessions**, save and restore SecurityContext properly via SecurityContextRepository and HttpSession/cookies. If you want **tokens**, issue tokens through a trusted mechanism and configure token verification on subsequent requests. Choosing sessions or tokens is a decision about **state management, credentials, and security**, not an automatic consequence of Content-Type: application/json.

## Official documentation for further study

- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Persisting Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — CSRF protection for JavaScript applications: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
