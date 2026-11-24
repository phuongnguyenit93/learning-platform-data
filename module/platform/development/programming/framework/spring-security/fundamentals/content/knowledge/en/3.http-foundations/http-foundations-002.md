# The Authorization header and how credentials are transmitted in HTTP

> **Scope:** HTTP foundations in Spring Security (Servlet/Spring MVC, Java 17+, Spring Boot 3.x). This lesson explains how credentials travel from client to server, the exact meaning of the **Authorization** header, the differences between Basic, Bearer, cookie/session, and other credential transmission methods. Not every transmission method uses the same authentication mechanism or has the same level of security.

## 1. First: credentials are transmitted, then identity is verified

When calling a protected API, the client must present proof so the server knows who it is or whom it represents. That proof can be a **username/password**, **access token**, **session identifier**, **API key**, **request signature**, or **client certificate**.

Three things must be distinguished:

1. **Credential transport:** where is the proof sent? For example, an HTTP request header, cookie, request body, or TLS handshake.
2. **Authentication:** how does the system verify the proof? For example, looking up an account and checking a password, verifying a JWT, looking up a session, or checking a signature.
3. **Authorization:** once identity and authorities are known, does the system allow access to the specific endpoint/resource?

~~~text
Client
  |
  |  Request + credential (if any)
  v
HTTP / TLS transport
  |
  v
Spring Security: selects SecurityFilterChain
  |
  +--> Filter reads the appropriate credential (Basic / Bearer / session / ...)
  |        |
  |        v
  |    Verify -> Authentication -> SecurityContext
  |
  +--> Check permissions (AuthorizationManager)
               |
               +--> ALLOW -> Controller / Service -> HTTP response
               |
               +--> DENY  -> AuthenticationEntryPoint / AccessDeniedHandler
~~~

**Authorization** is the name of an HTTP header; **authorization** is also the name of the *permission-checking* activity. The **Authorization** header is primarily used to **carry authentication information** to the server. It does not by itself decide whether the user has permission.

A header that looks valid can still carry a wrong password, an expired token, a token intended for another API, or a token with insufficient permissions. The server must verify the proof, then evaluate permissions.

## 2. Syntax and lifecycle of the Authorization header

HTTP provides a general format for HTTP authentication:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: <scheme> <credentials>
~~~

The snippet above is a **syntax template**, not a usable credential. The **scheme** indicates how the server should interpret the credential portion:

| Scheme | Example meaning | Primary proof |
| --- | --- | --- |
| **Basic** | Username and password encoded in Base64 | Username/password |
| **Bearer** | Whoever possesses the token can use it within its scope | Access token |
| **Digest** | Challenge/response mechanism based on scheme parameters | Hash computed from credential/challenge |
| **Negotiate** | HTTP authentication that can use SPNEGO/Kerberos | Protocol token |
| **AWS4-HMAC-SHA256** | Request signature according to the service's rules | Credential scope + HMAC signature |

Several important notes:

- **HTTP header names are case-insensitive**: **Authorization** and **authorization** represent the same header field.
- **Authentication scheme names are also case-insensitive** per HTTP, but the credential/token content must be preserved exactly; **do not lowercase tokens**.
- The syntax of the part after the scheme **depends on the scheme**. Do not assume every credential is a JWT or Base64.
- The **Authorization** header is intended for the target server. The **Proxy-Authorization** header is for a proxy requiring authentication and has its own challenge, **Proxy-Authenticate**.
- **Content-Type** and **Accept** describe request/response data types and **do not carry credentials**. An **X-CSRF-TOKEN** also does not replace **Authorization**: a CSRF token proves action validity in CSRF protection, not a login identity on its own.

### 2.1. The challenge/response cycle

HTTP authentication can proceed as follows:

~~~http
GET /api/private HTTP/1.1
Host: api.example.test
~~~

The server may respond:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="learning"
~~~

The client selects a supported scheme and resends the request with credentials:

~~~http
GET /api/private HTTP/1.1
Host: api.example.test
Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l
~~~

The illustrative Base64 string corresponds to **aladdin:opensesame**, not a token to fetch from a real server. After checking the credential, the server may return **200**, **403**, or another response per business logic.

**Not every client waits for a 401 before sending the header**. API clients often send Authorization right on the first request (*preemptive authentication*). An application using session cookies may not send an Authorization header even while logged in.

### 2.2. Distinguishing Authorization and WWW-Authenticate

| Header | Direction | Role |
| --- | --- | --- |
| **Authorization** | Client → server | Sends HTTP authentication credentials |
| **WWW-Authenticate** | Server → client | Announces scheme/challenge to authenticate, usually alongside 401 |
| **Proxy-Authorization** | Client → proxy | Sends credentials for a proxy |
| **Proxy-Authenticate** | Proxy → client | Proxy challenge, usually alongside 407 |
| **Cookie** | Browser/client → server | Sends cookies, which may contain a session identifier |
| **Set-Cookie** | Server → browser/client | Sets cookies according to attribute policies |

**401 Unauthorized** in HTTP usually means the client needs to provide valid authentication information. The status name is misleading; normally this is an *authentication* issue. **403 Forbidden** usually means the server recognized the client but does not allow the action, or the request was blocked by another defense mechanism. With form login, an unauthenticated request may get a **302 Redirect** to the login page instead of a 401 challenge. Specific responses also depend on configuration.

## 3. HTTP Basic: transmitting username/password via Authorization

**HTTP Basic** is a very easy-to-understand mechanism supported by many HTTP clients:

~~~text
username + ":" + password
       |
       v
bytes (per agreed charset)
       |
       v
Base64
       |
       v
Authorization: Basic <base64-string>
~~~

Example:

~~~text
username: aladdin
password: opensesame

Concatenated string: aladdin:opensesame
Base64:              YWxhZGRpbjpvcGVuc2VzYW1l
~~~

Corresponding request:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l
~~~

**Base64 is not security encryption**. Anyone who sees the Base64 string can decode it to retrieve the username/password. With Basic, clients can often resend the credential across many requests; therefore **HTTPS/TLS** is required in any environment with network traffic. Do not send Basic over plaintext HTTP.

### 3.1. Constructing a Basic header manually in Java 17

The following file **BasicHeaderDemo.java** is **standalone**, using only the JDK:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {
    public static void main(String[] args) {
        String username = "aladdin";
        String password = "opensesame";
        String pair = username + ":" + password;

        String encoded = Base64.getEncoder()
            .encodeToString(pair.getBytes(StandardCharsets.UTF_8));

        System.out.println("Authorization: Basic " + encoded);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
~~~

**Exact stdout:**

~~~text
Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l
~~~

The example intentionally uses fake credentials to show how encoding works; **do not print real credentials or write them to logs**.

**Charset note:** for usernames/passwords containing non-ASCII characters, client and server must agree on the representation; the Basic specification allows the challenge to announce **charset="UTF-8"**. When encountering login errors with Vietnamese accents or Unicode, do not assume the server always interprets bytes as UTF-8 without confirming configuration on both sides. The first colon separates username and password; usernames should not contain a colon under the Basic format.

### 3.2. Sending Basic with curl

~~~bash
curl -i -u aladdin:opensesame https://api.example.test/api/me
~~~

This syntax **illustrates how curl builds Basic Authorization**; the sample URL is not a running API. In a real terminal, the password string on the command line may appear in history or process info; you can use **curl -u aladdin** and let curl prompt for the password, depending on the runtime environment. Avoid pasting real passwords into scripts, logs, screenshots, or source repositories.

### 3.3. Is Basic a one-time login that then uses a session?

**Not necessarily.** HTTP Basic is a mechanism for transmitting username/password and authenticating per request. After authentication, Spring Security places the **Authentication** object into the **SecurityContext** for filters/controllers to use during that request; whether the context is saved to the next request depends on **SecurityContextRepository/session policy**. Do not infer that "Basic always has a session by default" or "Basic is always stateless by default" without checking the application configuration.

For APIs using Basic, **SessionCreationPolicy.STATELESS** can be set so Spring Security does not create/use an HttpSession to store the SecurityContext. This does not change the requirement that passwords must be protected in transit.

## 4. Bearer token: passing access rights with a token

The **Bearer** scheme commonly appears when a client calls an OAuth2 Resource Server:

~~~http
GET /api/reports HTTP/1.1
Host: resource.example.test
Authorization: Bearer abc.def.ghi
~~~

The string **abc.def.ghi** only illustrates syntax and is **not a valid JWT**.

The word "bearer" emphasizes that **whichever party holds the token can generally use the token**, if the server accepts it. If a token is leaked, someone else can reuse it until it expires or is revoked per the system's mechanism. Tokens must be protected like secrets.

### 4.1. Bearer does not mean JWT

Bearer describes **how the token is used**; the access token content itself can be:

- **JWT**: a token containing claims in Base64URL-encoded segments; with JWS, the server verifies the signature, allowed algorithm, and relevant claims.
- **Opaque token**: a string without a client-readable claims structure; the resource server can query the authorization server via introspection or a corresponding mechanism.
- Another token format agreed upon by the system.

A JWT payload can be read after Base64URL decoding, but **being readable does not mean the token is valid or its signature has been verified**. Signed JWTs (JWS) normally **do not encrypt the data in claims confidentially**. Do not place passwords, private keys, or unnecessary private information in claims.

**Minimum validation appropriate to the token type and system** may include: signature/trusted keys, allowed algorithms, **issuer (iss)**, **audience (aud)**, **expiration (exp)**, not-before time **nbf**, revocation/active status if applicable, and **scope/authorities** permissions. Do not treat decoding a JWT as a login step. In particular, configuring an issuer does not mean every system automatically checks the desired audience properly; you must inspect the decoder/validator configuration.

### 4.2. Access token vs ID token and refresh token

| Token | Purpose | Sent to resource APIs? |
| --- | --- | --- |
| **Access token** | Allows the resource server to check access rights | **Yes**, when the resource server expects it |
| **ID token** (OpenID Connect) | Info about the user's authentication session for the OAuth/OIDC client | **Do not substitute for an access token** to call APIs |
| **Refresh token** | Requests a new access token through an authorized flow | **Do not send as Bearer** to resource APIs |

A common mistake is putting an **ID token** in the Authorization header to call an API thinking it is an access token, or sending a refresh token to every endpoint. Both misuse the token's purpose and can expose sensitive information.

### 4.3. How to send Bearer with an HTTP client

In a shell where the **ACCESS_TOKEN** environment variable already holds a real access token for the right API:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://resource.example.test/api/reports
~~~

The line continuation **\\** and **$ACCESS_TOKEN** syntax in the example fit bash-like shells; for PowerShell, use PowerShell's way of reading environment variables. **Do not test against untrusted endpoints** because that header carries a valuable credential. Do not put tokens in URLs or commit tokens to repositories.

In Java using **Spring WebClient/RestClient**, use the library's built-in Bearer header API rather than concatenating strings manually when supported. Only forward a token to another service if the token has **the right audience and scope** for that service; do not automatically forward a user's bearer token to every downstream host.

### 4.4. Bearer errors and responses

With an OAuth2 Bearer-compliant resource server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When a token is invalid, the challenge may include additional info such as **error="invalid_token"**. When a token is valid but lacks scope, the response is typically **403** and may include **error="insufficient_scope"**.

Do not rely on a fixed error body to determine the reason; clients should check **status**, challenge, and API configuration. Do not echo raw tokens or internal data in error messages.

## 5. Comparing ways to pass credentials over HTTP/TLS

**The Authorization header is common, but it is not the only option.**

| Transmission method | Example location | Commonly used for | Risks/things to know |
| --- | --- | --- | --- |
| **Authorization: Basic** | Request header | Username/password | Base64 is decodable; often sent repeatedly; requires HTTPS |
| **Authorization: Bearer** | Request header | OAuth2 access token | Stolen tokens can be replayed; needs audience/scope/expiration |
| **Cookie: SESSION=...** | Cookie request header | Session-based web app | Browser auto-attaches; manage SameSite, CSRF, and sessions |
| **X-API-Key: ...** | Custom request header | API key for service/client | Keys are often long-lived; needs scopes, rotation, rate limits |
| **Authorization: AWS4-HMAC-SHA256 ...** | Signed request header | Signature-authenticated API | Must canonicalize method/path/query/headers/body and timestamp properly |
| **mTLS client certificate** | TLS handshake | Services with certificate identity | Manage CA, certificate issuance/revocation, and identity mapping |
| **Username/password in login body** | HTTPS POST form or JSON | Login before creating session/token | Only send to trusted login endpoint; do not log body |
| **Access token in URL query** | Query string | Special/legacy cases | **Not recommended**: leaks via logs, history, shared URLs |
| **Access token in form body** | application/x-www-form-urlencoded | Restricted cases per RFC 6750 | Strict conditions, not a default choice for resource APIs |

**The transmission form determines the risks, but does not by itself determine validity.** Whether credentials come from a header, cookie, or TLS, the backend still needs to verify them and check permissions at the exact point of access.

### 5.1. API keys and custom headers

An API may define its own:

~~~http
GET /api/jobs HTTP/1.1
Host: internal.example.test
X-API-Key: demo-key-for-explanation
~~~

**X-API-Key** is a common convention, not a default HTTP authentication scheme that Spring Security verifies automatically. If using API keys, you must implement/integrate a mechanism to read the header, match the key against a secure record, and produce an appropriate **Authentication**. You can alternatively use an Authorization scheme specified by the API documentation, but **do not invent a custom scheme when OAuth2, mTLS, or existing tools already meet requirements**.

An API key usually proves **application/client identity**, not necessarily the end user. When checking permissions, distinguish "service A" from "user X using service A." Grant only necessary permissions, use expiration/rotation when appropriate, audit, and rate-limit.

### 5.2. Request signatures (HMAC)

Some systems do not send raw passwords, instead signing a canonicalized representation (*canonical request*) consisting of method, path, query, certain headers, body hash, and timestamp. The server reconstructs the corresponding representation, verifies the signature, timestamp, and replay policy.

This is a **different mechanism** from Basic/Bearer. Simply adding a **Signature** header does not make Spring Security understand or verify the signature automatically; you need a library/implementation of the specific protocol and anti-replay policy. Mismatches in canonicalization can cause valid requests to be rejected or create security bugs.

### 5.3. mTLS

With **mutual TLS**, the client presents a **client certificate** during the TLS handshake; identity can be verified at the reverse proxy or the application, then mapped to a principal. An **Authorization** header is not necessarily present. If a proxy terminates TLS and passes identity info to the backend via a header, only trust that header when the proxy is controlled and the backend cannot be called directly to spoof the header.

## 6. Cookie/session: logged in without an Authorization header

A web application using form login can use a session cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

The response above is an example cookie policy; actual attributes depend on the application and servlet container. The browser stores the cookie and sends it in subsequent requests if Domain/Path/Secure/SameSite conditions match:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-id>
~~~

**A session identifier is a credential**: someone holding a valid session ID can be associated by the server with the user's session. The server looks up the session (or session management system) and restores authentication-related info per configuration. A cookie **is not a role or password by itself**; it typically only carries a session identifier.

Attributes to understand:

- **HttpOnly** restricts JavaScript access to the cookie via document.cookie, helping reduce certain XSS cookie-theft risks; it **does not prevent XSS from sending requests on behalf of the user**.
- **Secure** only allows sending the cookie over an appropriate HTTPS channel (with some differences on localhost); always set it for session cookies in production.
- **SameSite=Lax/Strict/None** controls cross-site cookie-sending context in browsers. **SameSite=None** requires **Secure** in modern browsers.
- **Path/Domain** limits cookie scope; set it reasonably narrow and consider the **__Host-** prefix if technical conditions fit.
- **Max-Age/Expires** and server-side session timeout affect lifecycle. Deleting the cookie in the browser does not fully replace invalidating the server-side session.

**Cookie and Authorization are not mutually exclusive on the same HTTP request.** A request can carry both a session cookie and a Bearer/Basic header simultaneously. The system must have a clear policy on chains/filters and **which identity source is accepted**, avoiding conflicts or unpredictable behavior.

### 6.1. Auto-attached cookies and CSRF

Browsers usually auto-attach cookies per cookie policy. A malicious page can cause the browser to send a request with side effects to an application where the user is logged in. Therefore, applications using **cookies/sessions for state-changing operations** must consider CSRF protection.

Spring Security Servlet enables **CSRF** protection by default for unsafe HTTP methods, such as **POST**, unless configuration is changed. The client must provide a valid CSRF token via the corresponding mechanism when the endpoint requires it. **Do not disable CSRF just to make a POST stop returning 403**.

An API that only accepts **Bearer tokens explicitly attached by the client in the Authorization header** and does not rely on browser-auto-sent credentials has a different CSRF model than a session-cookie app. However, **if the bearer token is stored in a browser-auto-sent cookie**, CSRF risk still exists. Even browsers caching and auto-resending HTTP Basic credentials must be analyzed in context.

### 6.2. Should access tokens be placed in cookies?

With a **Backend for Frontend (BFF)**, the browser can hold an HttpOnly session cookie while the backend stores/orchestrates the access token to call resource APIs. This avoids exposing access tokens to browser JavaScript, but requires managing CSRF, sessions, XSS, and backend trust boundaries.

Putting an **access token directly in a cookie** does not mean the resource server reads it automatically: Spring Security OAuth2 Resource Server **looks for Bearer tokens in the Authorization header by default**. If you want to use a cookie mechanism, you must explicitly design the authentication flow; do not enable an arbitrary resolver just to "accept tokens from everywhere."

## 7. Putting credentials in the request body and URL

### 7.1. POST /login with username/password in the body

~~~http
POST /login HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded

username=alice&password=example
~~~

This is an illustrative example; **HTTPS** and an implemented login endpoint are required. The server verifies credentials and may then **create a session** or **issue a token** depending on architecture. Passing username/password in the body **does not automatically make them safer than headers**, because the body can still be logged or exposed if TLS is misconfigured. Login APIs and resource APIs have different responsibilities; resource APIs typically **do not accept passwords on every request**.

In OAuth2 Authorization Code + PKCE, an **authorization code** can appear in the redirect callback URI and then be exchanged by the client for a token via the token endpoint. **An authorization code is not an access token**; state/PKCE must be used and redirect URIs configured properly. Do not infer that because an authorization code appears in a query string, putting an **access token** in a URL is safe.

### 7.2. Why should access tokens not be placed in URLs?

Example to avoid:

~~~http
GET /api/me?access_token=sample-secret HTTP/1.1
Host: resource.example.test
~~~

URLs can be recorded in **access logs, reverse proxy logs, browser history, analytics, telemetry, screenshots, copied links**, and many intermediate systems. RFC 6750 describes passing tokens via query parameters but **does not recommend it** due to token exposure risk.

Similarly, avoid **username/password** in URLs, such as via the userinfo part or query parameters. If compatibility with a legacy system is required, tightly restrict, evaluate, and migrate to a supported standard as soon as possible.

### 7.3. Form-encoded Bearer tokens are also an exception

RFC 6750 permits a method of transmitting access tokens in the **request entity-body** with **Content-Type: application/x-www-form-urlencoded** when specific conditions are met. This is **not the default method**. Spring Security Resource Server does not enable reading tokens from form bodies by default; enabling support requires configuring a custom resolver.

A new API should prefer **Authorization: Bearer** over HTTPS, unless a specific protocol/architecture mandates another choice.

## 8. The Authorization header in Spring Security Servlet

Spring Security does not "automatically log in" every request with an Authorization header. An appropriate filter must be enabled and configured to verify the credential.

### 8.1. HTTP Basic filter

With **httpBasic(...)**, the typical processing chain:

~~~text
Authorization: Basic <base64>
         |
         v
BasicAuthenticationFilter
         |
         v
UsernamePasswordAuthenticationToken (unauthenticated)
         |
         v
AuthenticationManager
         |
         v
AuthenticationProvider (e.g., DaoAuthenticationProvider)
         |
         +--> UserDetailsService + PasswordEncoder
         |
         v
Authenticated Authentication
         |
         v
SecurityContextHolder -> AuthorizationFilter -> Controller
~~~

If credentials are wrong, the authentication mechanism handles the error and may invoke **AuthenticationEntryPoint** to return 401. If credentials are missing, a rule requiring authenticated can trigger **ExceptionTranslationFilter** and the Basic entry point. For an authenticated user lacking authority, **403** is typically returned.

**httpBasic** does not read Bearer tokens such as JWTs. Sending **Authorization: Bearer ...** to an application configured only with Basic will not authenticate the request as Bearer. The proper Resource Server mechanism must be enabled.

### 8.2. Bearer token filter

With **oauth2ResourceServer(...)** configured, the typical flow:

~~~text
Authorization: Bearer <access-token>
         |
         v
BearerTokenAuthenticationFilter
         |
         v
BearerTokenResolver (reads Authorization header by default)
         |
         v
Appropriate AuthenticationManager / AuthenticationProvider
         |
         +--> JWT: JwtDecoder, validators, authorities mapping
         |
         +--> Opaque: introspection / token status
         |
         v
Authentication in SecurityContext
         |
         v
AuthorizationFilter -> Controller
~~~

**An Authorization header without a valid Bearer token** does not produce a valid identity. The Resource Server must have the necessary key/trust configuration to validate tokens. After authentication, **scope/authority** and resource policies must still be enforced.

### 8.3. Session cookie

With form login/session, SecurityContext management components can restore info from **SecurityContextRepository/HttpSession** at the start of a request. Neither BasicAuthenticationFilter nor BearerTokenAuthenticationFilter is needed to re-check a password on every cookie read. Authentication may have been saved from an earlier login, depending on configuration and session state.

The flows above **can be combined**, but each application must proactively design matchers, filter chains, context persistence policy, and priority authentication sources. One should not accept "whichever credential happens to be present" without clear principles.

## 9. Complete practical example: Spring Boot 3 + HTTP Basic

This section is **a standalone runnable application** with Java 17+ and Spring Boot 3.x. It demonstrates requests with/without an Authorization header and authentication/authorization responses. The endpoints only use **GET** so demo logic does not mix with CSRF token issuance for state-changing requests.

Use a Spring Boot 3.x project already configured with Gradle/Java, add **Spring Web**, **Spring Security**, and test dependencies:

**build.gradle** (dependencies snippet added to a project that already has plugins and version management):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create three files in **src/main/java/com/example/headerauth/**.

### 9.1. HeaderAuthApplication.java

~~~java
package com.example.headerauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeaderAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeaderAuthApplication.class, args);
    }
}
~~~

### 9.2. SecurityConfig.java

~~~java
package com.example.headerauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

Explanation:

- **httpBasic(Customizer.withDefaults())** enables Basic Authorization header processing.
- **SessionCreationPolicy.STATELESS** specifies that the example does not rely on HttpSession to save/read SecurityContext for the next request; Basic credentials are used whenever sending an authenticated request.
- **/api/public** is public, **/api/me** requires login, and **/api/admin** requires **ROLE_ADMIN**. Other URLs are denied.
- **BCryptPasswordEncoder** verifies passwords via hash rather than plaintext comparison. Simple demo passwords are only for **localhost**, not for production.
- **hasRole("ADMIN")** checks the **ROLE_ADMIN** authority by default. An authenticated username does not automatically have ADMIN permission.

### 9.3. DemoController.java

~~~java
package com.example.headerauth;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        String roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + roles;
    }

    @GetMapping("/api/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

Spring MVC can supply the current **Authentication** to a controller parameter on an authenticated request. The **/api/me** endpoint shows the identity and authorities **after** Spring Security has processed the header.

### 9.4. Run the application and observe headers/status

From the project directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -H "Authorization: Bearer sample.invalid.token" \
  http://localhost:8080/api/me
~~~

**Expected** with the exact demo config:

| Request | Status | Body on success / reason |
| --- | --- | --- |
| GET /api/public, no credential | **200** | **public** |
| GET /api/me, no credential | **401** | HTTP Basic requires authentication |
| GET /api/me, Basic alice:alice123 | **200** | **alice ROLE_USER** |
| GET /api/admin, Basic alice:alice123 | **403** | Authenticated but missing ROLE_ADMIN |
| GET /api/admin, Basic admin:admin123 | **200** | **admin-only** |
| GET /api/me, Basic wrong password | **401** | Invalid credentials |
| GET /api/me, sample Bearer | **401** | Application only enables HTTP Basic, not Resource Server |

When testing missing credentials, inspect the **WWW-Authenticate** header of the 401. In normal HTTP Basic it announces the Basic scheme; some configurations may customize the challenge or handle XHR requests differently. Error responses have no fixed body to rely upon.

**Note:** this demo does not verify Bearer tokens because Resource Server is not configured. Do not use the 401 result of a fake Bearer string to conclude whether a real JWT is valid.

### 9.5. Testing Spring Security via MockMvc

Create **src/test/java/com/example/headerauth/AuthorizationHeaderTest.java**:

~~~java
package com.example.headerauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationHeaderTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireAuthorization() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void missingCredentialsGetUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsCreateAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserMayStillBeForbidden() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bearerHeaderIsNotBasicAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer sample.invalid.token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**MockMvc** sends requests through the filter chain configured by Spring Boot integration testing; these tests verify how the client presents the Basic header along with HTTP decisions. **httpBasic(...)** in Spring Security Test helps build a properly formatted header, rather than bypassing authentication. The tests do not need hardcoded Base64 strings.

## 10. If using Bearer JWT instead of Basic, how is it configured?

This is **a separate architectural variant** of the example above; do not add it into the same Basic demo SecurityFilterChain without designing a policy that accepts multiple credentials. With **Spring Boot 3.x**, a JWT resource server usually needs dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The **application.yml** example below uses an illustrative issuer URL; **it must be replaced with a real issuer exposing valid metadata/JWK** for the resource server to run and verify tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
~~~

Inside a **@Configuration** class, a separate chain for a Bearer-based API can be configured as follows (the snippet is **not a standalone Java program**):

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Corresponding imports (**HttpSecurity**, **SecurityFilterChain**, **Bean**, **Customizer**) and a valid JWT decoder configuration in the project are required. With the common default scope mapping, a token with scope **reports.read** is converted into authority **SCOPE_reports.read**. If the system uses a different claim or prefix, a corresponding converter must be configured. **A valid token must still have sufficient scope and be accepted by the intended audience**; audience checks matching the API should be configured rather than relying solely on a valid signature.

Spring Security Resource Server accepts Bearer from **Authorization** by default. If the token is in a custom header/form body, a custom **BearerTokenResolver** can support it, though that is an architectural decision requiring evaluation; the default configuration **does not** automatically read cookies or query access_token as equivalent login methods.

For **opaque access tokens**, replace the JWT handling direction with **opaqueToken/introspection** configuration matching the authorization server. Do not write code splitting JWT strings to verify opaque tokens manually.

## 11. Browser: Authorization, CORS, and credential mode

When frontend JavaScript calls a cross-origin API:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
    headers: {
        Authorization: "Bearer " + accessToken
    }
});
~~~

This is an **illustrative snippet**; the **accessToken** variable must come from a valid token acquisition mechanism; secrets must never be hardcoded in frontend source code. Browsers allow code to set the Authorization header, but **a cross-origin request with Authorization usually triggers a CORS preflight** (**OPTIONS**) before the actual request.

The server must respond appropriately to the preflight, for example allowing the origin and the **Authorization** header per CORS policy. **CORS is a browser policy controlling cross-origin response-reading permission**, not proof of login or backend authorization. Succeeding with Postman/curl does not prove the browser frontend will pass CORS.

With session cookies and cross-origin **fetch**, the client may need:

~~~javascript
const response = await fetch("https://api.example.test/account", {
    credentials: "include"
});
~~~

When using credentialed CORS, the server must configure **Access-Control-Allow-Credentials** and **Access-Control-Allow-Origin** to the exact allowed origin; browsers do not accept the wildcard **\*** for Allow-Origin in credentialed requests. Cookies must also satisfy **SameSite**, **Secure**, Domain/Path, and browser policies. **credentials: "include"** does not create a session or grant permissions if no cookie exists.

**Notable differences:**

- Authorization Bearer manually attached by JavaScript code is usually **not automatically added by the browser to every request**.
- Cookies/sessions can be **auto-sent** by the browser if cookie conditions are met, so CSRF must be addressed.
- When a browser caches Basic credentials, it may auto-resend them depending on HTTP authentication mechanics; CSRF and actual browser behavior must also be evaluated.
- Changing CORS cannot fix an invalid token, missing scope, or wrong requestMatcher.

## 12. Safety checklist when transmitting credentials

1. **Enforce HTTPS/TLS** when sending passwords, tokens, session cookies, or API keys over the network. Clients must verify server certificates; do not use options that disable TLS checks to "fix" production issues.
2. **Do not place secrets in URLs**, logs, queries, browser history, analytics, stack traces, telemetry, screenshots, or error messages. Configure redaction filters for **Authorization**, **Cookie**, **Set-Cookie**, **X-API-Key**, and login request bodies.
3. **Choose the right credential type**: access token for resource APIs, ID token for OIDC clients, refresh token for token endpoints; passwords only transmitted to intended authentication endpoints.
4. **Limit lifetime, scope, and audience**. Leaked keys/tokens should support revocation or rotation depending on the model. If a resource server accepts multiple issuers, clear trust boundaries must be designed.
5. **Do not arbitrarily forward the Authorization header across redirects/downstream calls**. Only send tokens to trusted hosts and the right audience; when an HTTP client follows redirects automatically, check header-forwarding behavior, especially across domains.
6. **Control proxies/gateways**: ensure required headers reach the right backend; do not trust an "X-User" header fabricated by Internet clients. TLS termination does not mean client-to-backend is always safe if the internal channel can be eavesdropped on.
7. **Separate authentication and authorization**: a properly formatted header does not prove permission; always verify action, resource, tenant, and scope.
8. **Account for CSRF with browser-auto-sent credentials**, session fixation, XSS, and logout/session invalidation. **HttpOnly** reduces the risk of JavaScript reading cookies, but does not solve every XSS or CSRF issue on its own.
9. **Do not store long-lived access tokens in localStorage while ignoring the XSS threat model**. Choose token/cookie/BFF storage based on the threat model and token lifecycle, avoiding statements like "HttpOnly alone is secure enough."
10. **Test missing/invalid credential states too**. Beyond 200, test 401, 403, expired tokens, wrong audience, wrong permissions, undeclared paths, and proxy/CORS behavior if actual clients use browsers.

## 13. Diagnosing a request returning 401 or 403

When **curl** with an Authorization header is still rejected, check in order:

| To verify | Diagnostic question |
| --- | --- |
| **Transport** | Does the request actually carry Authorization/Cookie to the right host and over HTTPS? |
| **Scheme** | Does the API expect **Basic** or **Bearer**? Was an ID token sent instead of an access token? |
| **Filter chain** | Which **SecurityFilterChain** does the request match? Is httpBasic/resource server enabled on the right chain? |
| **Credential validity** | Is the Basic password right? Does the JWT have valid signature/issuer/audience/exp? Is the opaque token still active? |
| **SecurityContext** | Is a valid Authentication placed in the context? |
| **Authority/scope** | Does it have the exact ROLE_ADMIN or SCOPE_reports.read required by the rule? |
| **Resource policy** | Have owner, tenant, action, and business state been checked? |
| **Other filters** | Do CSRF, CORS, reverse proxy, custom filters, or app errors affect the response? |

In development environments, Spring Security logging can be enabled:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Only use an appropriate log level and **do not log raw credentials/tokens**. In production, prefer correlation IDs, verified principal IDs, actions, resource IDs, and access decisions, in compliance with data policies.

Typical mistakes:

- **Confusing Authorization with permission:** having a Bearer header does not prove the token is valid or allowed to read any document.
- **Confusing Base64 with encryption:** Basic exposes the password whenever the credential is read.
- **Confusing JWT with all Bearer tokens:** opaque tokens cannot be decoded into claims on the client.
- **Confusing Cookie with Authorization:** a browser session can be valid even when Authorization is absent.
- **Confusing 401 with 403:** invalid/missing credentials differs from having an identity without permission.
- **Confusing CORS with authorization:** CORS is a browser access rule, not a substitute for backend controls.
- **Putting access tokens in URLs:** very easily recorded accidentally by intermediate systems.
- **Accepting tokens from everywhere for "convenience":** expands the attack surface and causes identity source conflicts.

## 14. Self-check questions

**Question 1.** A request has **Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l**. Can the server already treat the caller as valid?

**Answer:** Not yet. That is the Base64-encoded username/password; the server still has to verify the credential, account status, and access rules.

**Question 2.** A request has no Authorization header but carries a valid session cookie. Can Spring Security identify the user?

**Answer:** Yes, if the application has an appropriately configured session/SecurityContext restoration mechanism and the session is still valid. Not every application uses sessions.

**Question 3.** Must **Authorization: Bearer** always contain a JWT?

**Answer:** No. A Bearer token can be a JWT, an opaque token, or another format suited to the system; it must be verified by the corresponding mechanism.

**Question 4.** Why does a web page calling an API via fetch encounter a CORS error while curl calls the API fine?

**Answer:** Browsers enforce CORS (often with a preflight when using cross-origin Authorization), whereas curl does not enforce browser CORS policies. The API still must check authentication and authorization independently.

**Question 5.** Can HTTP Basic or Bearer be safe over plaintext HTTP?

**Answer:** No. HTTPS/TLS is needed to protect credentials in transit; Basic's Base64 provides no secrecy, and a leaked Bearer token can be reused.

**Question 6.** Why should you avoid sending access tokens in query strings?

**Answer:** URLs are saved in many places like history, access logs, analytics, or shared links; this increases the chance of credential exposure.

**Question 7.** An API configured with **httpBasic(...)** receives **Authorization: Bearer**. Does it automatically authenticate the token?

**Answer:** No. Appropriate Bearer-handling configuration/filters (typically OAuth2 Resource Server) and valid token validation are required.

**Question 8.** Can you use an **HttpOnly cookie** and then ignore CSRF?

**Answer:** No. HttpOnly restricts cookie access from JavaScript; cookies can still be auto-sent by the browser. State-changing requests need CSRF protection suited to the architecture.

## Official references

- HTTP Semantics — **Authorization / HTTP authentication**: https://www.rfc-editor.org/rfc/rfc9110.html
- HTTP Basic Authentication — **RFC 7617**: https://www.rfc-editor.org/rfc/rfc7617.html
- OAuth 2.0 Bearer Token Usage — **RFC 6750**: https://www.rfc-editor.org/rfc/rfc6750.html
- MDN — **Authorization header**: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Authorization
- MDN — **HTTP Authentication**: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication
- Spring Security — **HTTP Basic Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **OAuth 2.0 Bearer Tokens**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security — **CSRF**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — **Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html

**Key takeaway:** **Authorization** is a credential transport channel within the HTTP authentication framework. The server only establishes identity after verifying credentials with an appropriate mechanism, and only then decides **whether the action is allowed on that resource**. When choosing how to send authentication info, consider **transport security, permissions, expiration, leakage risks, and how browsers/clients actually send requests**.
