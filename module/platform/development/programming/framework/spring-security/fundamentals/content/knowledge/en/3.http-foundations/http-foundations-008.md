# REST APIs do not automatically dictate whether an app must use sessions or tokens

> **Context:** HTTP foundations in Spring Security (Servlet/Spring MVC, Java 17+, and Spring Boot 3.x). When designing APIs, one often hears the claim "REST is stateless, so you must use JWT and never use sessions." That claim mixes up **API architectural style**, **client state lifecycle**, **authentication mechanism**, and **how login state is stored**. These decisions are related, yet need to be analyzed separately.

## 1. What must be understood correctly first

- **REST** is an architectural style with constraints, including **stateless communication**: the server must have enough information from each request to understand and process that request; the server does not rely on **client conversational state** stored between requests.
- **HTTP** is a request/response protocol where each request can be independent; HTTP still supports cookies, authorization headers, and multiple mechanisms for applications to maintain login state.
- **Session** is a way to maintain login context or other data across multiple requests. If the server must look up **a client's authentication session saved from a previous request** to understand a request, the application depends on server-side session state and does not satisfy a **strict REST statelessness** interpretation for that flow.
- **Token** is a piece of proof. A token can be a self-verifiable JWT, or an opaque token requiring a query to a service/lookup server to check validity. A token does not automatically make a system "stateless."
- **Spring Security** does not force every JSON API application to choose sessions or JWTs. You configure **SecurityFilterChain**, the **Authentication** mechanism, **SecurityContextRepository**, and the session policy for the architecture you are building.

Practically speaking: **an HTTP API returning JSON can still use session cookies** just like many web applications. However, if the requirement is **strict compliance with the REST stateless constraint**, treat reliance on server-stored client sessions as a dependency to remove or redesign. The "REST API" label on documentation does not automatically dictate the application's authentication method.

## 2. Three independent questions easily conflated into one

When designing the endpoint **GET /api/orders/42**, ask in order:

| Decision axis | Question | Example choices |
| --- | --- | --- |
| **API style / semantics** | What are the resources, HTTP methods, representations, and REST constraints? | GET /orders/42, JSON response, cache policy, hypermedia if applicable |
| **Authentication / credential** | How does the client prove its identity? | Form login, HTTP Basic, OAuth2 access token, API key, mTLS |
| **Authentication state management** | Where does the next request obtain identity from? | HttpSession, Basic header every time, JWT Bearer, opaque token + introspection, BFF session |

Do not deduce one axis from another. An endpoint returning JSON can serve a browser via session cookie, a mobile app via access token, or an internal service via mTLS, depending on implementation and security constraints.

**REST statelessness does not mean:**

1. "The server may not store any data at all." The server still stores **resource state**: orders, accounts, inventory, versions, user permissions, etc.
2. "Databases/caches may not be used." Databases and caches can serve resource state or permission checks; what matters is that a request must not be forced to rely on implicit **client conversational context** from a prior request.
3. "Every request must contain a password." Requests can use an issued credential, such as a Bearer access token.
4. "JWT is mandatory." Opaque tokens, signed requests, or Basic can also supply sufficient authentication info under their respective mechanisms; meanwhile a JWT with wrong issuer/audience/signature is still worthless.
5. "Having JWT makes everything stateless." JWTs can be paired with refresh-token stores, revocation lists, authorization server sessions, or other stateful mechanisms.

## 3. What does REST statelessness truly require?

Per Roy Fielding's description of REST, each request from client to server must contain all the information necessary for the server to understand the request; requests cannot take advantage of stored context on the server from prior interactions. **Client session/application state** is the client's responsibility, while **resource state** can be and usually is stored on the server.

Resource example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: example.test
Accept: application/json
Authorization: Bearer <access-token>
~~~

An implementation can read **resource 42** from the database and verify identity/permissions from the access token in the request. A database storing orders does not violate the stateless idea. The core question is: does the server need to remember "this client just reached step 2 in a previous conversation" or "this session id points to a context kept from an earlier login" to understand the request?

### 3.1. Distinguishing application state and resource state

- **Resource state**: the state of a resource managed by the server; for example, order 42 is **PAID**. This is business data.
- **Client application state**: which screen the client is on, which filters are selected, which workflow step, which next representation/URL. In strict REST, the server does not keep a secret "conversation slot" that the client is forced to rely on.
- **Authentication/session state**: username, authorities, or SecurityContext kept across requests. Storing them on the server and looking them up via a cookie creates a dependency between requests. That may **fit a real-world web application completely well**, yet one should be honest about the difference from a strict stateless constraint.

A workflow can still span multiple steps in a stateless API if **workflow state is an addressable resource with explicit state transitions**, for example **POST /orders** creates an order and **POST /orders/42/approve** acts on current resource state and permissions in the request. There is no need for the server to keep a global variable "client is at step 2."

### 3.2. Stateless HTTP does not erase the session concept

HTTP requests are usually independent at the protocol layer. To preserve login, a web app may do:

~~~text
POST /login (log in)
    |
    v
Server authenticates, stores SecurityContext/session, issues session id
    |
    v
Set-Cookie: JSESSIONID=...
    |
    v
GET /account  +  Cookie: JSESSIONID=...
    |
    v
Server looks up session -> gets Authentication -> checks permissions
~~~

HTTP still transports valid requests, yet **useful authentication info resides in server-side session state**. Sessions are not a mandatory property of HTTP or REST; they are **an application architecture choice**.

## 4. Two ways through the same protected endpoint

Suppose endpoint **GET /me** returns user information.

### 4.1. Using a session cookie

~~~http
POST /login HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded

username=alice&password=example
~~~

This is an illustrative HTTP example, not real login credentials. On success, a web application may create a session and return a cookie:

~~~http
HTTP/1.1 302 Found
Location: /
Set-Cookie: JSESSIONID=<session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Afterward the browser sends:

~~~http
GET /me HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-id>
~~~

The server needs to find an active session, restore authentication, and then decide permissions. The client **does not need to resend the password on every request**. The browser also typically auto-sends the cookie according to the cookie's Domain/Path/Secure/SameSite.

With session cookies, logout can invalidate the server-side session. However, distributed systems must design shared session storage, stickiness, or an appropriate mechanism; adding server instances does not automatically ensure every instance sees the same session.

### 4.2. Using a Bearer access token

After a valid token issuance flow (e.g., OAuth2 Authorization Code + PKCE), the client uses the access token to call the API:

~~~http
GET /me HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

The resource server needs to verify the token, issuer, intended audience, expiration, and appropriate permissions. If the token is a **signed JWT**, much information can be verified via keys/validators without querying a per-client session on every request. If the token is **opaque**, the resource server can use **introspection** or look up data managed by the authorization server. These approaches have different operational characteristics.

A Bearer token means "whoever holds the token can generally use the token." Thus a stolen access token is a serious risk, even when the API does not use sessions.

**An access token is not an ID token**: an ID token in OpenID Connect is for the client to verify info about the authentication session; do not grab an ID token instead of an access token to send to every resource API.

### 4.3. Using HTTP Basic with independent requests

~~~http
GET /me HTTP/1.1
Host: api.example.test
Authorization: Basic YWxpY2U6ZXhhbXBsZQ==
~~~

The illustrative Base64 string represents **alice:example**. Basic typically resends username/password per request, so it can be deployed without using HttpSession to store SecurityContext. **Basic does not need JWT**, yet must use HTTPS; Base64 is not security encryption. Browsers may auto-resend Basic credentials per HTTP authentication mechanics, so you must not infer "stateless means definitely no CSRF."

All three approaches still must check an **AuthorizationManager** or business policy to decide whether access to **GET /me** is allowed. No mechanism replaces permission checks by itself.

## 5. Session, JWT, and opaque token: comparing the right criteria

| Criterion | Session cookie storing context on server | Bearer JWT access token | Opaque access token |
| --- | --- | --- | --- |
| **Credential held by client** | Session identifier | JWT | Opaque string |
| **How server knows identity** | Looks up session/context | Verifies signature and claims | Lookup/introspection |
| **Keeps session state on server** | Typically yes | Not required to verify a properly signed JWT, though the system may still have other state | Typically has token status data on the token-issuing server |
| **Immediate revocation** | Can invalidate session server-side | Typically needs short lifetimes, revocation lists, or extra measures | Can check token status, depending on caching |
| **Client-readable data** | Session id is usually opaque/uninterpretable | Signed JWT payload is usually readable after Base64URL decode | Client usually cannot read claims directly |
| **Risk if credential leaks** | Session hijacking until expiration/revocation | Token usage until expiration/revocation | Token usage until expiration/revocation |
| **System scaling** | Needs consistent session store or equivalent solution | Resource server can verify locally; needs key rotation/validators | Needs introspection/lookup or controlled caching |
| **Browser/CSRF** | Auto-sent cookie: CSRF must be considered | Bearer header explicitly added by code: different CSRF model | Depends on how token is passed; cookie-stored tokens also have CSRF |
| **Typical fit** | Traditional web apps, server-rendered, BFF | APIs for mobile/SPA/services in OAuth2 architecture | APIs needing opaque tokens and centralized status checks |

The table is a **comparison of common characteristics**, not immutable assertions. A JWT can also be placed in a cookie; a session id can be sent via a custom header; an opaque token can still be cached; a system can use sessions in the browser and access tokens between backend and APIs. Therefore asking "cookie or JWT?" is actually comparing **a credential transport medium** with **a token format**, which are not at the same conceptual level.

### 5.1. A cookie is not a session; a JWT is not a header

- **Cookie** is a browser mechanism for storing/sending a name/value pair via the Cookie header; the value can be a session id or a token depending on architecture.
- **Session** is server-side context or a session concept in the system; it can be identified via a cookie.
- **Authorization** is a common HTTP header for sending Basic/Bearer credentials.
- **JWT** is a token format with claims; how a JWT is transmitted is not fixed to a header, although **Authorization: Bearer** is usually the standard choice for resource APIs.
- **OAuth2** is an authorization and token-issuance framework; OAuth2 does not mean JWT or "mandatory stateless."
- **OpenID Connect** adds an identity layer on top of OAuth2; an ID token serves a different purpose than an access token.

## 6. How does Spring Security manage SecurityContext and HttpSession?

**Authentication** (principal, authorities, authentication status) is held by Spring Security in the request's **SecurityContext**. **SecurityContextHolder** lets filters/controllers/services access that context within the appropriate execution scope. A **SecurityContextRepository** can load/save context between requests, for example via **HttpSessionSecurityContextRepository**, or not persist across sessions like **NullSecurityContextRepository**.

Simplified lifecycle:

~~~text
Receive request
    |
    v
Find matching SecurityFilterChain
    |
    v
Load/initialize SecurityContext per the chain's repository
    |
    v
Authentication filter reads matching credential
    |
    v
SecurityContext holds valid Authentication
    |
    v
AuthorizationFilter / method security
    |
    v
Controller and service
    |
    v
End request, clear thread-bound SecurityContext
~~~

Two things must be distinguished:

1. **Current context** exists during request processing, regardless of whether the API is configured stateless or not.
2. **Persisting context across requests** is a separate matter; it depends on the repository and authentication/login mechanism. In modern setups, login filters usually must explicitly save the context if it is to be reused on subsequent requests.

### 6.1. What does SessionCreationPolicy actually mean?

Spring Security Servlet defines the following policies:

| Value | Meaning regarding HttpSession in Spring Security |
| --- | --- |
| **ALWAYS** | Always creates an HttpSession when needed per Spring Security's mechanism |
| **IF_REQUIRED** | Only creates a session when required; this is the typical default choice |
| **NEVER** | Does not proactively create a session, but can use an existing session |
| **STATELESS** | Does not create a session and does not use HttpSession to obtain SecurityContext |

**STATELESS** is a **Spring Security** session-management configuration option, not a validator of compliance with all REST constraints. It **does not forbid every other part of the application from calling request.getSession()**, does not prove the server uses no database/cache, and does not automatically enable JWT authentication.

Example configuring a separate API chain that does not store SecurityContext in HttpSession:

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .httpBasic(Customizer.withDefaults());
~~~

This is a **configuration snippet inside SecurityFilterChain**, not a complete program. HTTP Basic lets requests supply credentials on every call; there is no mandatory need to store an authentication session. Because browsers can auto-send Basic credentials and because CSRF requirements depend on how clients are used, **do not casually disable CSRF solely based on the word STATELESS**.

### 6.2. REST does not require SessionCreationPolicy.STATELESS in every product

A server-rendered web app reasonably uses sessions because browser clients, logout, CSRF, and login lifecycle align. When a team calls its JSON endpoints a "REST API," that label does not automatically transform an existing application into a stateless architecture. You can serve JSON over HTTP via sessions while still having clean API semantics, while accurately describing its boundaries regarding the REST stateless constraint.

Conversely, a system choosing **STATELESS** because every request carries Basic or Bearer credentials still has to handle the rest: resource-level permissions, token revocation, rate limiting, and logging. It does not guarantee a secure API by itself.

## 7. Practical example: one application with both web sessions and a sessionless API

The example uses **Spring Boot 3.x, Spring Security 6.x, and Java 17+**. We create **two SecurityFilterChains with explicit matchers**:

- **/api/**: HTTP Basic with **SessionCreationPolicy.STATELESS**. Requests to the API must supply Basic credentials themselves when endpoints require login.
- **Web section**: form login and sessions. After logging in, a browser can access **/web/me** using the cookie containing the session id.

Both share the same demo user list. The example uses only **GET** for business endpoints; **POST /login** uses the CSRF token provided by Spring Security. Passwords are dummy values for localhost.

### 7.1. Dependencies

From a Spring Boot 3.x project with plugins, Gradle Wrapper, and dependency management, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create the Java files in **src/main/java/com/example/sessionortoken/**, with package **com.example.sessionortoken**.

### 7.2. SessionOrTokenApplication.java

~~~java
package com.example.sessionortoken;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionOrTokenApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionOrTokenApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java: two chains, two policies

~~~java
package com.example.sessionortoken;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
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
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .requestMatchers("/web/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

**Explanation of key points:**

- **@Order(1)** selects the **/api/** chain first; **@Order(2)** is the web chain declaring no securityMatcher so it catches the remaining URLs.
- **securityMatcher("/api/**")** decides which requests **belong to the API chain**; **requestMatchers(...)** inside decides authorization rules. If you omit a catch-all chain for other URLs, those URLs may fall outside Spring Security's protection layer.
- The API chain uses **STATELESS**, not loading SecurityContext from HttpSession. Even if a client has the web session cookie, a **/api/me** request carrying only that cookie is not automatically recognized as logged in by the API chain.
- The web chain uses **formLogin**. Spring Security can generate the default login page **GET /login**, accept **POST /login**, save context in the session upon successful login, and restore it on subsequent requests.
- The two chains apply different mechanisms within **the same HTTP application**, illustrating that "serving an API" does not force the entire application to use one login method.
- **anyRequest().denyAll()** blocks undeclared endpoints. In real development, design intentional exceptions for health, error/forward dispatches, static assets, and technical endpoints.
- CSRF **is not disabled**. The example runs GET requests and form logins with valid CSRF tokens; if opening POST/PUT/DELETE on the API, design a CSRF policy based on client type and how credentials are sent.
- **BCryptPasswordEncoder** hashes passwords for verification; the demo uses fixed passwords for easy testing, whereas production must use proper credential/identity management.

### 7.4. DemoController.java

~~~java
package com.example.sessionortoken;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/api/public")
    public String publicApi() {
        return "api-public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web:" + authentication.getName();
    }
}
~~~

The controller simply receives the **Authentication** already verified by Spring Security; it does not read passwords, cookies, or Bearer tokens from the request directly.

### 7.5. Run and observe with an HTTP client

Start from the project directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Test the API first:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i http://localhost:8080/web/me
~~~

**Expected** results with the illustrative configuration:

| Request | Status | Meaning |
| --- | --- | --- |
| Anonymous → GET /api/public | **200**, body **api-public** | Public API |
| Anonymous → GET /api/me | **401**, with Basic challenge | API needs credentials right in the request |
| Basic alice → GET /api/me | **200**, body **api:alice** | HTTP Basic authenticates for the request |
| Anonymous → GET /web/me | **302** to login page | Web chain uses form login |
| After successful login, session cookie → GET /web/me | **200**, body **web:alice** | Web chain uses session |
| Sending only web-session cookie to GET /api/me | **401** | API chain does not use that session to authenticate |

Distinction to note: using **curl -u** to send Basic for **one request** does not mean curl kept a login session for **the next request**. To simulate web login manually with curl, you must handle the login page/form, cookie jar, and CSRF token properly. The MockMvc tests below provide a more reproducible example.

### 7.6. MockMvc tests proving the two approaches operate independently

Create **src/test/java/com/example/sessionortoken/SessionOrTokenTest.java**:

~~~java
package com.example.sessionortoken;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionOrTokenTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiAcceptsBasicWithoutSession() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:alice"));

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void webLoginCreatesReusableSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);

        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:alice"));

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void webWithoutSessionRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicApiRequiresNoCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Meaning of each assertion group:**

1. **apiAcceptsBasicWithoutSession:** the API uses Basic credentials right on requests with the header; a new request without the header does not automatically retain login.
2. **webLoginCreatesReusableSession:** form login with a valid CSRF token creates a session; sending that session on the next web request recognizes the same user.
3. **webLoginCreatesReusableSession (API part):** sending that same session to the **STATELESS** API chain does not substitute for Basic credentials.
4. **webWithoutSessionRedirectsToLogin:** the form-login entry point can respond with a redirect, differing from HTTP Basic challenges.
5. **publicApiRequiresNoCredentials:** publicly permitted resources require no authentication.

These are integration tests for **Spring Boot 3.x**. If using Spring Boot 4 or another Spring Security version, packages/imports and some test APIs may change; adjust to your chosen dependencies rather than copying mechanically.

## 8. If choosing Bearer tokens instead of HTTP Basic for the API

HTTP Basic clarifies the idea that **each request carries its own credentials**, yet repeatedly sending passwords does not suit many production APIs. In systems with OAuth2/OIDC, an API can be an **OAuth2 Resource Server** accepting access tokens.

Add the appropriate dependency to the Spring Boot 3.x project:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Illustrative issuer configuration in **application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
~~~

The issuer above is an **example address**, not a live endpoint issuing tokens. With JWT, the Resource Server needs trusted keys and validators; in production you must configure checks for **issuer**, **audience**, expiration, and related parameters per API specification.

Replace **apiChain**'s Basic mechanism with the following snippet inside SecurityFilterChain configuration; this is a **snippet**, not a standalone compilable Java class:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll()
    )
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

From the client:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <valid-access-token>
~~~

**Do not swap an ID token for an access token.** Spring Security reads Bearer from the Authorization header by default and validates the access token per configuration. A valid JWT lacking the required authority or failing resource-level policy must still be denied.

**STATELESS** here suits an API not using HttpSession to store SecurityContext; **JWT is not a mandatory consequence of STATELESS**. Replacing JWT with opaque tokens + introspection still runs an API without relying on browser login sessions, though with a different degree of external state dependency.

## 9. How do CORS, CSRF, and how clients carry credentials interact?

### 9.1. Cookie sessions and CSRF

Browsers usually auto-send session cookies per cookie rules. This creates **Cross-Site Request Forgery** risk when another page can cause the browser to emit requests on the user's behalf. Web apps using sessions/cookies for data-modifying actions need CSRF mechanisms like valid tokens and appropriate cookie attributes.

**HttpOnly** helps restrict JavaScript from reading cookies, yet does not solve CSRF: browsers can still auto-attach cookies. **SameSite** is a risk-reduction layer, not a replacement for all CSRF protections. In Spring Security Servlet, CSRF protection is enabled by default for unsafe HTTP methods unless configured otherwise.

### 9.2. Bearer tokens in the Authorization header

If frontend JavaScript explicitly attaches a Bearer header to requests, the browser **does not automatically add that header to every cross-site request** like cookies. Thus the CSRF model differs from session cookies. However, the frontend must protect access tokens against **XSS**, log leakage, third-party scripts, and unsafe token storage.

If **the token is stored in an auto-sent cookie**, requests still carry CSRF risk even if the cookie content is a JWT. The right question is **whether the browser automatically attaches the credential to requests**, not "whether the inner format is a JWT or a session ID."

### 9.3. CORS is not authentication

Browsers sending **Authorization: Bearer** to another origin usually require a CORS preflight. The server must configure CORS accurately (origin, method, headers, credentials), yet allowing CORS **does not grant permissions** to a user. CORS is a browser-side mechanism governing cross-origin resource access; curl/Postman do not enforce that browser policy.

If a frontend uses session cookies cross-origin with **credentials: include**, both **SameSite/Secure** policies and CORS credentials must be satisfied simultaneously. **Access-Control-Allow-Origin: *** is invalid for credentialed responses in browsers; specific allowed origins must be declared.

### 9.4. HTTPS and credential safety

Whether using cookies, Basic, or Bearer:

- Enforce valid TLS over untrusted networks.
- Avoid writing **Authorization**, **Cookie**, **Set-Cookie**, passwords, and tokens into logs.
- Never put access tokens in URL queries or browser history.
- Limit permissions, lifetime, audience, revocation capability, and rotation.
- Never blindly forward bearer tokens to downstream services with the wrong audience.
- For sessions, require session fixation protection, timeouts, invalidation, and cookie settings like **Secure**, **HttpOnly**, and **SameSite**.

## 10. Which option should you choose for real-world scenarios?

There is no single perfect default for every client. Choose based on **credential source**, **trust boundaries**, **operational complexity**, and **logout/revocation behavior**.

| Scenario | Suitable direction to consider | Reasons and things to handle |
| --- | --- | --- |
| Server-rendered website, same origin | **Form login + session cookie** | Fits browsers, clear logout/session management; manage CSRF and cookies |
| Web SPA with separate backend | **OAuth2 Authorization Code + PKCE**, consider **BFF** | Consider keeping tokens on backend with HttpOnly session cookie; manage CSRF/XSS/CORS |
| Mobile client calling API | **OAuth2 access token** | Fits clients with token issuance/refresh flows, secure token storage, and scope/audience |
| Service-to-service | **OAuth2 client credentials, workload identity, or mTLS** | Service identity, credential rotation, scopes, and auditing |
| Internal tool with few endpoints | **Basic over HTTPS** may work in controlled contexts | Simple, yet sends passwords per request; watch rotation and client storage |
| System needing rapid permission revocation | **Sessions or opaque tokens/introspection**, or short-lived JWTs + extra measures | Weigh lookup cost, caching, and consistency |
| API with multiple resource/tenant zones | **Any suitable auth mechanism + resource authorization** | Sessions/JWTs do not prove a user may read a specific resource |

**BFF (Backend for Frontend)** is a common pattern: the browser holds a **session cookie** with the BFF; the BFF performs OAuth2, holds the appropriate tokens, and uses **access tokens** to call downstream APIs. Such a system **uses both sessions and tokens** at different boundaries. There is no contradiction: each layer has its own responsibility and threat model.

### 10.1. Decision-making workflow

1. **Identify clients:** same-origin browser, SPA, mobile, CLI, services, or partners.
2. **Map trust boundaries:** which domains, reverse proxies, gateways, and frontends/backends do credentials cross?
3. **Define authentication needs:** username/password, OAuth2, enterprise SSO, API keys, workload identity, or mTLS?
4. **Define how login persists:** session store, local token validation, introspection, or BFF.
5. **Define permission requirements:** roles, scopes, resource ownership, tenants, and denial policies.
6. **Determine revocation speed:** logout, account lock, token compromise, refreshing authorities.
7. **Assess browser risks:** CSRF, XSS, CORS, SameSite, token storage.
8. **Define negative tests:** missing credentials, wrong credentials, wrong audience, expired tokens, non-existent sessions, wrong tenant, accessing API with web cookies when unsupported.

Architecture docs should state **specifically**: "The `/api/**` API uses verified Bearer JWTs and does not read HttpSession," or "`/web/**` uses session cookies and CSRF," rather than merely writing "this is a REST API so it is stateless."

## 11. Common misconceptions and corrections

**Misconception 1 — "REST mandates JWT."**  
REST does not prescribe a token format. JWT is a tool with specific pros and cons. Choose it only when it truly fits authentication/authorization, signature/claim checks, and key distribution.

**Misconception 2 — "Session cookies break HTTP."**  
HTTP still uses normal request/response exchanges. However, requests depending on server-side sessions differ from REST's strict stateless constraint. Distinguish protocol from architectural style.

**Misconception 3 — "STATELESS means the server stores no data."**  
Spring Security STATELESS does not use HttpSession to retrieve SecurityContext. The server still stores orders, accounts, audits, and resource state, and can use databases/caches for other purposes.

**Misconception 4 — "JWT has no state."**  
Signed JWTs can be verified locally, yet systems still need plans for refresh tokens, logout, revocation, key rotation, session lists, or account status. Self-verifiable JWTs do not prove the *entire system* is stateless.

**Misconception 5 — "Tokens are safer than cookies."**  
Comparisons must specify **token format**, **storage location**, **transport**, **lifetime**, **scope**, **XSS/CSRF**, and **revocation**. JWTs in localStorage and HttpOnly session cookies have different risk surfaces; there is no absolute winner.

**Misconception 6 — "For a stateless API, disabling CSRF is right."**  
CSRF relates to how browsers auto-attach credentials. Browsers can auto-send cookies or HTTP auth credentials. Only design CSRF exemptions after properly assessing clients and credentials.

**Misconception 7 — "Using sessions forces form login on every endpoint."**  
One application can have multiple SecurityFilterChains, such as web sessions for UI and Basic/Bearer for APIs. Proper matchers and tests are needed so the two mechanisms do not accidentally overwrite each other.

**Misconception 8 — "Having an Authorization header means having permission."**  
That is only a credential carrier. The server still must verify identity, issuer/audience/expiry if a token, and specific permissions/ownership.

**Misconception 9 — "No session stored means no tenant check needed."**  
Authentication and authorization are two separate tasks. A stateless API can still leak resources if it checks only a generic role and allows accessing arbitrary IDs.

**Misconception 10 — "Opaque tokens cannot be used for stateless APIs."**  
Opaque tokens can be sent per request and checked via introspection. The resource server depends on token state in another service; that differs from holding client conversational sessions inside the app itself. Describe concrete properties instead of inferring from token labels.

## 12. Self-check questions

**Question 1.** An API returns JSON and accepts **JSESSIONID** from the browser. Can that API be called a "REST API"?

**Suggested answer:** In everyday software conversation, people may still call it that to refer to HTTP resource endpoints. But if evaluating **strict REST statelessness**, relying on authentication context stored in HttpSession is a server-side state dependency that must be acknowledged.

**Question 2.** When Spring Security sets **SessionCreationPolicy.STATELESS**, does a request have a **SecurityContext**?

**Answer:** Security context still exists during request processing when the authentication mechanism produces an Authentication. STATELESS governs using HttpSession to save/read context across requests; it does not eliminate the need for SecurityContext in the current request.

**Question 3.** Why can JWTs be verified without a session lookup, yet a system using JWTs still have state?

**Answer:** A JWT's signature/claims themselves can be verified locally, yet the system still manages accounts, permissions, refresh tokens, signing keys, and possibly revocation/denylists. "Self-contained token" does not mean the entire system stores no state.

**Question 4.** A browser completes form login and sends **JSESSIONID** to **/api/me** in the two-chain example. Does the API automatically log in as alice?

**Answer:** No. The API chain uses **STATELESS** and **HTTP Basic**, and does not read web sessions to restore SecurityContext. API requests need appropriate credentials.

**Question 5.** Can a web app using an HttpOnly cookie containing a JWT ignore CSRF?

**Answer:** You cannot infer that. Cookies can be auto-sent by the browser; CSRF must be evaluated as with any auto-attached credential. HttpOnly mainly restricts JavaScript from reading the cookie.

**Question 6.** Should a service-to-service API with no browser choose sessions or JWT?

**Answer:** You must consider the threat model, identity provider, credential rotation, permissions, and revocation. OAuth2 client credentials, mTLS, or workload identity are worth considering; REST does not choose for you.

**Question 7.** If the database still stores orders, can an API satisfy the stateless constraint?

**Answer:** Yes. Orders are **resource state**, distinct from **client conversational state**. Individual requests can still contain the info needed to operate on resources.

**Question 8.** The API returns 401 without a Basic header and the website returns 302 to /login. Why?

**Answer:** The two chains have different **AuthenticationEntryPoints**: HTTP Basic typically challenges with 401, while form login typically redirects. Status codes arise from the authentication/navigation mechanism, not the "REST" label.

## Official references

- Roy Fielding, **Architectural Styles and the Design of Network-based Software Architectures**, Chapter 5, REST: https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm
- HTTP Semantics, **RFC 9110**: https://www.rfc-editor.org/rfc/rfc9110.html
- HTTP State Management Mechanism, **RFC 6265**: https://www.rfc-editor.org/rfc/rfc6265.html
- OAuth 2.0 Bearer Token Usage, **RFC 6750**: https://www.rfc-editor.org/rfc/rfc6750.html
- Spring Security — **Session Management**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — **Java Configuration / Multiple HttpSecurity**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **OAuth2 Resource Server**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html

**Idea to keep:** **REST sets constraints on how requests behave, whereas sessions or tokens are authentication system design decisions.** To adhere to strict REST statelessness, avoid relying on server-side client session state; to operate a secure web/API system, choose the right credential mechanism, manage its lifecycle, and enforce permissions on every resource.
