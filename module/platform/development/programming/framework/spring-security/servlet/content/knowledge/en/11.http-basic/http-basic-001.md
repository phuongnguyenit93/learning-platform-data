# HTTP Basic Flow and Authorization Header in Spring Security Servlet

## 1. Lesson Objectives

**HTTP Basic Authentication** is a simple HTTP authentication mechanism: the client sends a username and password as a value in the **Authorization** header. The server decodes the representation, verifies credentials through an authentication mechanism, and then allows or denies access according to the security policy. Spring Security Servlet supports this flow via filters and AuthenticationManager, without requiring us to decode the header manually in controllers.

After this lesson, you can:

1. Read the **Authorization: Basic ...** syntax properly and know what the Base64 content actually contains.
2. Distinguish the request **Authorization** header from the response **WWW-Authenticate** header.
3. Trace the path from **BasicAuthenticationFilter** to **AuthenticationManager**, **AuthenticationProvider**, **SecurityContext**, and then **AuthorizationFilter**.
4. Explain the **200, 401, 403** statuses in HTTP Basic and why invalid credentials differ from insufficient permissions.
5. Write a Spring Boot Java 17+ application using **SecurityFilterChain**, **httpBasic**, **UserDetailsService**, **PasswordEncoder**, and URL rules.
6. Practice with **curl**, inspect real headers, and verify with **MockMvc**.
7. Identify risks: **Base64 does not encrypt secrets**, HTTPS must be used, browsers may resend credentials, avoid logging headers, and handle proxies/charset/CSRF according to needs.

**Scope:** Spring Security on the **Servlet stack**, such as Spring MVC. This lesson covers how HTTP Basic and the Authorization header work, not a guide to building custom OAuth2, JWT, or a new login protocol.

## 2. Big Picture: Client, HTTP Headers, Servlet Filters

When a client calls an endpoint protected with HTTP Basic, the conceptual flow is:

~~~text
Client                                   Server (Spring Security Servlet)
  |                                                |
  |  GET /me HTTP/1.1                              |
  |  Authorization: Basic <base64-user-colon-pass>  |
  |----------------------------------------------->|
  |                                                |
  |                  DelegatingFilterProxy         |
  |                         |                      |
  |                  FilterChainProxy              |
  |                         |                      |
  |                 SecurityFilterChain            |
  |                         |                      |
  |              BasicAuthenticationFilter         |
  |                reads Authorization             |
  |                         |                      |
  |                  AuthenticationManager         |
  |                         |                      |
  |                  AuthenticationProvider        |
  |                         |                      |
  |           UserDetailsService + PasswordEncoder |
  |                         |                      |
  |              Authentication succeeded?         |
  |                   /              \             |
  |                 Yes               No           |
  |                 |                  |           |
  |        sets SecurityContext       401          |
  |                 |                              |
  |          AuthorizationFilter                   |
  |                 |                              |
  |          has URL permission?                   |
  |           /          \                         |
  |         Yes           No                       |
  |         |               |                      |
  |      Controller        403                     |
  |         |                                      |
  |<--------+---- HTTP 200 / response -------------|
~~~

The diagram illustrates roles, not a complete list of every filter in every SecurityFilterChain. Filters handling SecurityContext, CSRF, exceptions, anonymous access, and authorization may participate at different stages.

**Authentication** asks: “Who is sending the request, and have they proven their identity?”. **Authorization** asks: “Is that authenticated identity allowed to use this resource?”. HTTP Basic is primarily a way of **supplying credentials for the authentication step**, not a replacement for authorization configuration.

## 3. Syntax of the Authorization Header

According to HTTP Basic (RFC 7617), the client sends:

~~~http
GET /me HTTP/1.1
Host: example.test
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
~~~

The value after **Basic** is the Base64 encoding of the string:

~~~text
Aladdin:open sesame
~~~

This is a sample credential pair used to explain the format. They do **not** belong to the users configured in the Spring Boot project in the hands-on section.

General structure:

~~~text
Authorization: Basic <base64(username:password)>
               |     |
               |     +-- Base64 string of user-id + : + password
               +-------- authentication scheme
~~~

**Key points:**

- The exact header name is **Authorization**, not Authentication and not Proxy-Authorization.
- The scheme is **Basic**; per HTTP rules, the scheme name is case-insensitive, though it is commonly capitalized as Basic.
- **The first colon** separates user-id and password before Base64 encoding. Therefore, user-id in this format must not contain a colon; password may contain colons.
- There is a space between **Basic** and the encoded credentials string.
- Base64 is only an **encoding**, reversible back to the original bytes; there is no secret encryption algorithm or signature protecting this string.
- The header is sent on every request where the client wants to authenticate with Basic; it can be sent proactively or after the server returns a challenge.
- For non-ASCII characters, client and server must agree on the charset. RFC 7617 defines a **charset="UTF-8"** parameter on the challenge in supported cases; do not assume all historical clients/servers interpret bytes identically.

**Base64 is never a substitute for TLS.** If a request travels over unencrypted HTTP, an observer on the wire can capture and decode the credentials. Use **HTTPS** and ensure TLS covers the path through proxies/load balancers to the appropriate trust boundary.

### Does Base64 “encrypt the password”?

No. For example, if someone sees:

~~~text
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
~~~

they can Base64-decode it to recover **Aladdin:open sesame** directly. Therefore:

- Do not capture or write the raw Authorization header into logs, traces, analytics, or exceptions.
- Do not forward the header to secondary services unnecessarily.
- Do not treat a Basic credential pair like an access token with independent scope/expiry.
- Do not put raw credentials in URL query strings because URLs may be stored in history, logs, or Referer headers.
- If you must use Basic with real credentials, have credential rotation/revocation, rate limiting, and brute-force detection in place.

## 4. Request Authorization vs Response WWW-Authenticate

The two headers serve two different directions of communication.

| Header | Sender | Purpose |
| --- | --- | --- |
| **Authorization: Basic ...** | Client → server | Sends credentials to attempt authentication for the request |
| **WWW-Authenticate: Basic realm="..."** | Server → client | Announces the supported/required authentication scheme in a challenge |
| **Proxy-Authorization** | Client → proxy | Credentials intended for a proxy; does not replace Authorization to the origin server |
| **Proxy-Authenticate** | Proxy → client | Challenge from a proxy, typically associated with HTTP 407 |

For example, when credentials are missing and the endpoint requires login:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

**Realm** is a label for the protection space so the user agent knows the authentication scope; a realm is not a password hash, JWT scope, or session ID. In Spring Security, the realm value is configurable. Do not hardcode expectations on the exact string "Realm" across all applications.

A client can:

1. Send GET /me without Authorization.
2. Receive 401 with a WWW-Authenticate: Basic challenge.
3. Prompt the user for username/password or use stored credentials.
4. Resend GET /me with Authorization: Basic ...
5. Receive 200 if the credentials are valid **and** the user has sufficient permissions.

Many HTTP clients, including curl when using the **-u** option, can **send Basic immediately on the first request** without waiting for 401. That is why you often see the Authorization header appear right away on the first API call.

**401 Unauthorized**, despite its HTTP status phrase, does not simply mean “lacking permission”; in this context it primarily signals that authentication is required or incomplete. **403 Forbidden** means the server understood the request but **refuses authorization to perform it**, typically when the user is authenticated but lacks the required authority.

## 5. Where Does Spring Security Process Authorization: Basic?

Main components of the Servlet flow:

| Component | Responsibility |
| --- | --- |
| **FilterChainProxy** | Selects the first SecurityFilterChain whose matcher matches the request |
| **BasicAuthenticationFilter** | Recognizes HTTP Basic and converts credentials into an authentication request |
| **BasicAuthenticationConverter** | Parses/decodes Basic credentials when the filter uses a converter |
| **AuthenticationManager** | Coordinates authentication, typically implemented by ProviderManager |
| **DaoAuthenticationProvider** | Authenticates username/password with UserDetailsService and PasswordEncoder |
| **UserDetailsService** | Loads username, password hash, account status, and authorities |
| **PasswordEncoder** | Compares raw password against stored hash via matches(...) |
| **SecurityContextHolder** | Provides the Authentication for the current processing thread/execution |
| **AuthorizationFilter** | Checks whether the request is authorized under authorizeHttpRequests rules |
| **BasicAuthenticationEntryPoint** | Returns HTTP 401 and WWW-Authenticate: Basic when a challenge is needed |
| **ExceptionTranslationFilter** | Translates certain downstream authentication/authorization exceptions into responses via entry point/access denied handler |

**BasicAuthenticationFilter** should not be confused with defining users. The filter only handles the HTTP Basic mechanism; it does not create accounts or query a database on its own without a suitable AuthenticationProvider/UserDetailsService.

### 5.1. Request with Valid Basic Credentials

~~~text
Authorization: Basic <credentials>
           |
BasicAuthenticationFilter
           |
BasicAuthenticationConverter -> username + raw password
           |
UsernamePasswordAuthenticationToken (not yet authenticated)
           |
AuthenticationManager.authenticate(...)
           |
DaoAuthenticationProvider
           |
UserDetailsService.loadUserByUsername(...)
           |
PasswordEncoder.matches(raw, storedHash)
           |
Authentication succeeded
           |
SecurityContextHolder holds Authentication
           |
AuthorizationFilter checks role/authority
           |
Controller
~~~

In the normal flow, credentials on the resulting Authentication may be **erased** after authentication to reduce how long the raw password lingers in the result object. Do not call Authentication.getCredentials() in a controller expecting to retrieve the password, as it may already be null.

### 5.2. Request with Invalid Basic Credentials

~~~text
Authorization: Basic <invalid-password>
           |
BasicAuthenticationFilter
           |
AuthenticationManager -> authentication failed
           |
Clears/cleans context appropriately, calls entry point
           |
HTTP 401 + WWW-Authenticate challenge (per configuration)
~~~

If the filter handles the error and terminates the response, subsequent filters may **not** run and the controller is not invoked.

### 5.3. Missing Authorization on an Authenticated URL

When a request has no Basic credentials, BasicAuthenticationFilter typically continues down the chain without authenticating a user. At the authorization step, the protected URL is not permitted for anonymous users, so exception handling returns an authentication challenge, usually **401** in a Basic-only configuration.

The difference from an invalid password: a missing header is **not** a Basic credential parsing error; the request simply lacks an identity satisfying the rule. Both may result in 401 on a protected endpoint, but they arise from different processing branches.

### 5.4. Authenticated Without the Required Role

A user has **ROLE_USER**, while /admin requires **ROLE_ADMIN**:

~~~text
Authorization: Basic <valid-user-credentials>
            |
Authentication succeeded -> user has ROLE_USER
            |
AuthorizationFilter checks hasRole("ADMIN")
            |
Insufficient role -> 403 Forbidden
~~~

**hasRole("ADMIN")** by default looks for the authority **ROLE_ADMIN**; do not write hasRole("ROLE_ADMIN") and double-prefix it. The role name is assigned in UserDetailsService via roles("ADMIN") in the example.

## 6. Does HTTP Basic Create a Session?

**HTTP Basic is a scheme for sending username/password in a request**, not a definition that the server is always stateless. This mechanism can work alongside sessions if the application configures sessions; do not conclude that merely calling httpBasic() makes everything automatically stateless.

In the demo we set:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

This instructs Spring Security not to use HttpSession to load SecurityContext across requests. Every protected request must provide suitable authentication evidence, such as Basic credentials. Spring Security may establish a new Authentication for a later request, but it will not revive a login just because HTTP Basic succeeded on a previous request.

**On the client side**, a browser may remember Basic credentials and automatically resend the Authorization header on subsequent requests. As a result, the user may feel “still logged in” even though the server uses no session. This is the **client resending credentials**, which differs from the server restoring Authentication from a session cookie.

**Logout for HTTP Basic is unlike form login.** The server can return 401 or reject credentials, but there is not always a standard way to force every browser to clear cached Basic credentials. If you need a clean logout/session experience, consider a more suitable login mechanism.

## 7. Complete Spring Boot Example: HTTP Basic and Authorization Header

The application will have:

- GET **/public** requiring no authentication.
- GET **/me** requiring any authenticated user.
- GET **/admin** requiring ROLE_ADMIN.
- User **learner / learner-pass** with ROLE_USER.
- User **admin / admin-pass** with ROLE_ADMIN.

These passwords and accounts are strictly for local testing. Never deploy hardcoded passwords to production and **never** test demo credentials against real systems.

### 7.1. Stack and Project Structure

Uses **Java 17+**, **Maven**, **Spring Boot 3.3.13**, **Spring Security 6**.

~~~text
basic-auth-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/basicdemo/
    │   ├── BasicDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/basicdemo/
        └── BasicAuthenticationFlowTest.java
~~~

No custom BasicAuthenticationFilter is needed to run the demo: **httpBasic(Customizer.withDefaults())** uses Spring Security's standard mechanism.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>basic-auth-demo</artifactId>
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

The Spring Boot starter parent manages compatible versions of Spring Framework and Spring Security. There is no need to pin Spring Security versions manually for the starters.

### 7.3. BasicDemoApplication.java

~~~java
package com.example.basicdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
~~~

This file is the Spring Boot entry point. Because the classes share the **com.example.basicdemo** package, configuration beans and controllers are automatically picked up by component scan.

### 7.4. SecurityConfig.java

~~~java
package com.example.basicdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
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
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails administrator = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, administrator);
    }
}
~~~

**Block-by-block explanation:**

1. **SecurityFilterChain** replaces the older WebSecurityConfigurerAdapter approach in Spring Security 6.
2. **sessionCreationPolicy(STATELESS)** keeps the demo independent per request; no session is used to store Authentication across GET calls.
3. **requestMatchers(HttpMethod.GET, ...)** specifies exact HTTP methods and paths. Requests outside these routes hit denyAll; arbitrary POST/PUT calls are not permitted by default.
4. **authenticated()** requires a valid identity. **hasRole("ADMIN")** requires the ROLE_ADMIN authority.
5. **httpBasic(Customizer.withDefaults())** enables Basic authentication and its standard entry point; the application does not read the Authorization header manually.
6. **formLogin(AbstractHttpConfigurer::disable)** disables redirecting to an HTML login page so curl calls missing credentials receive a Basic challenge.
7. **PasswordEncoder** creates BCrypt hashes for the sample users; each startup may produce different hash strings due to salting.
8. **InMemoryUserDetailsManager** serves local demos, not a production user management system.

**CSRF is not disabled.** The example only uses GET, so no CSRF token is needed. If you add state-changing endpoints, evaluate CSRF based on how browsers/clients send credentials: browsers can cache and send HTTP Basic automatically. Do not conclude that STATELESS or HTTP Basic automatically eliminates CSRF risk.

### 7.5. DemoController.java

~~~java
package com.example.basicdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

The **Authentication** parameter in /me is supplied by Spring Security once the request is authenticated. The controller never receives raw passwords, reads the Authorization header, or re-runs PasswordEncoder.matches. This is separation of concerns: filters/providers authenticate first, and the controller only handles permitted requests.

## 8. Running the Application and Calling curl

From the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Maven requires JDK 17+ and network access to download dependencies when not yet cached. Once the application starts successfully, it listens by default on **http://localhost:8080** in local configuration.

**Note on passwords in command lines:** the curl -u syntax in the examples uses public sample credentials. For real secrets, avoid putting passwords directly into command history, process listings, or saved scripts; choose a secure way to supply secrets suited to your OS and tooling.

### 8.1. Public Endpoint, No Authorization Header

~~~bash
curl -i http://localhost:8080/public
~~~

Response elements to observe:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"public-ok"}
~~~

Other headers and header ordering may be added by the server/framework. What matters is status **200** and the public JSON body.

### 8.2. /me Endpoint Missing Authorization

~~~bash
curl -i http://localhost:8080/me
~~~

Key output:

~~~http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
~~~

Because credentials are absent and /me requires authenticated(), the server sends a Basic challenge. The realm name depends on configuration; with this default configuration it is typically Realm.

### 8.3. /me Endpoint with Valid Basic Credentials

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/me
~~~

Key output:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"username":"learner"}
~~~

The **-u username:password** option makes curl generate Authorization: Basic with the corresponding Base64 string. Spring Security verifies the password against the BCrypt hash in UserDetailsService. Afterward, /me is allowed to execute.

### 8.4. Wrong Password

~~~bash
curl -i -u learner:wrong-pass http://localhost:8080/me
~~~

Expected **401 Unauthorized**, without invoking the /me controller. This case differs from a request without credentials in its internal filter path, though both fail to satisfy authentication.

### 8.5. Authenticated but Missing ADMIN Role

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/admin
~~~

Expected **403 Forbidden**: learner has ROLE_USER and a valid password, but lacks ROLE_ADMIN. Do not report “wrong login” for this case; the issue is **authorization**, not credential validity.

### 8.6. Admin Access with Proper Role

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Key output:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"admin-ok"}
~~~

### 8.7. When the Authorization Header Uses Another Scheme

If a client sends **Authorization: Bearer ...** in this demo configured only for HTTP Basic, the bearer token is not authenticated as a username/password by the Basic filter. On /me, if no other mechanism authenticates the request, the result still fails authenticated() and gets challenged.

Do not swap one scheme for another by changing the prefix and expecting the server to understand: **Basic** and **Bearer** are two protocols with different semantics, credentials, and verification logic.

Verification matrix:

| Request | Credentials/role | Expected status | Meaning |
| --- | --- | --- | --- |
| GET /public | No Authorization | 200 | Public URL |
| GET /me | No Authorization | 401 | Unauthenticated, Basic challenge returned |
| GET /me | learner valid password | 200 | Valid authentication |
| GET /me | learner wrong password | 401 | Invalid credentials |
| GET /admin | learner valid password, ROLE_USER | 403 | Authenticated but missing role |
| GET /admin | admin valid password, ROLE_ADMIN | 200 | Sufficient permission |

**Do not rely on a specific error page body or exact header set** as an immutable contract unless you have configured and tested a custom handler. Status codes and the challenge's WWW-Authenticate header are the core focus for this lesson.

## 9. MockMvc Testing: Proving the Basic Flow and Challenge

Create **src/test/java/com/example/basicdemo/BasicAuthenticationFlowTest.java**:

~~~java
package com.example.basicdemo;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoAuthorizationHeader() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"));
    }

    @Test
    void protectedEndpointReturnsBasicChallengeWhenMissingCredentials()
            throws Exception {

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic")));
    }

    @Test
    void validBasicCredentialsAuthenticateRequest() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void invalidBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/me").with(
                httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutRequiredRoleReceivesForbidden()
            throws Exception {

        mvc.perform(get("/admin").with(
                httpBasic("learner", "learner-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorWithCorrectRoleCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin").with(
                httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-ok"));
    }
}
~~~

Run from the root directory:

~~~bash
mvn test
~~~

**Key checks:**

- Public endpoint returns 200 without a header.
- Protected endpoint without credentials returns 401 with **WWW-Authenticate** starting with **Basic**.
- Valid Basic username/password lets /me return the identity.
- Wrong password returns 401.
- Valid login lacking role returns 403.
- Sufficient role returns 200.

MockMvc does not need a live HTTP server listening on port 8080; it simulates requests passing through Spring MVC and the filter chain integrated in the test context. **httpBasic(...)** from spring-security-test builds the Basic Authorization header without computing Base64 manually. The tests do not assume passwords are kept in session.

## 10. Building an Authorization Header Manually to Understand the Format

You **do not need** to write Base64 logic in controllers. However, to understand the protocol, you can run the following standalone Java snippet.

Create **BasicHeaderDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {

    public static void main(String[] args) {
        String username = "Aladdin";
        String password = "open sesame";

        String userPass = username + ":" + password;
        String token = Base64.getEncoder().encodeToString(
            userPass.getBytes(StandardCharsets.UTF_8));

        System.out.println("Authorization: Basic " + token);

        String decoded = new String(
            Base64.getDecoder().decode(token),
            StandardCharsets.UTF_8);

        System.out.println("Decoded example: " + decoded);
    }
}
~~~

Compile and run independently of Spring Boot:

~~~bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
~~~

Exact stdout:

~~~text
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
Decoded example: Aladdin:open sesame
~~~

This example **intentionally prints sample credentials** to prove Base64 is reversible. Never print decoded credentials like this for real accounts. If the system uses non-ASCII characters, the charset must be agreed upon; the demonstration deliberately uses ASCII so the Base64 output is deterministic.

**Key takeaway:** anyone who obtains the header can perform the exact same decode operation; Base64 does **not** secure credentials.

## 11. When Does BasicAuthenticationFilter Run and Not Run?

**Authorization header present with syntactically valid Basic scheme:** the filter parses username/password and asks AuthenticationManager to verify them. On success, it sets Authentication in the appropriate SecurityContext. On failure, returning a challenge may terminate the chain.

**No Authorization header:** the Basic filter normally passes the request along without creating an Authentication out of thin air. Another filter or session policy may supply a context if configured; in the stateless Basic-only demo, /me without a header results in 401.

**Authorization with a scheme other than Basic:** BasicAuthenticationFilter does not turn a bearer token into a password. Another authentication mechanism must be configured if you want to accept that scheme.

**Malformed header (invalid Base64, missing colon separator, strange formatting):** the converter/filter may reject the authentication attempt; the final status and body depend on exception/entry point configuration. Do not assume a header merely “containing Basic” is enough.

**Public path with a bad header:** even if /public has permitAll, if a client actively sends invalid Basic credentials, the authentication filter may reject it before reaching the controller. Therefore, **permitAll does not mean preceding filters ignore all Basic header errors**. When testing a public endpoint, send the request without Authorization so results are not confused.

**Multiple SecurityFilterChains:** each request is processed only by the first chain whose matcher matches. If one chain for /api/** does not enable httpBasic while another chain does, challenge behavior can differ per URL. Do not assume every URL on the server shares the same authentication scheme.

## 12. Error Codes and How to Interpret Them in Real Applications

| HTTP code | Common situation | What developers should check |
| --- | --- | --- |
| **200 OK** | Request succeeded, sufficient permission | Controller was invoked; does not mean body data is automatically safe |
| **401 Unauthorized** | Missing credentials, wrong password, invalid credentials, or unauthenticated | WWW-Authenticate, authentication/entry point config, what the client sent |
| **403 Forbidden** | Valid Authentication but missing role, or rejected by another policy | Authorities, authorizeHttpRequests, CSRF, method security |
| **407 Proxy Authentication Required** | Proxy requires its own authentication | Proxy-Authenticate/Proxy-Authorization, do not confuse with origin Basic |
| **302 Found** | Can appear when form login/redirect is enabled instead of Basic-only | Check entry points and Accept header |

**403 does not always prove the username/password were right.** For example, a POST missing a CSRF token can return 403 even before successful authentication; a custom handler may also return 403. To analyze a real failure, inspect the filter configuration and the exact request.

For an HTTP Basic API, a clean design is: **401** when unauthenticated with a challenge; **403** when authenticated but denied by a rule. However, policies across multiple security chains or custom error handlers can alter behavior.

**Do not return overly detailed error messages** distinguishing whether a username exists or revealing valid accounts to help attackers enumerate users. Internal audits may record error categories at an appropriate, protected level.

## 13. HTTPS, Browsers, CSRF, and Proxies

### 13.1. HTTPS Is a Fundamental Requirement

Authorization: Basic carries username/password in decodable Base64. Over plaintext HTTP, credentials can be read, copied, or altered in transit. Production requires HTTPS with proper TLS configuration, certificate management, and proper reverse proxy handling.

Using **http://localhost:8080** in the example is strictly for local testing. Never expose an HTTP Basic endpoint with real accounts over the open Internet.

### 13.2. Browsers May Resend Credentials Automatically

Some browsers cache Basic credentials per protection space and automatically resend them on later requests. Thus, even when the server is stateless, credentials may still be sent by the browser every time. This affects logout UX and the CSRF attack surface.

Do not treat Basic as the default choice for interactive web apps needing sophisticated login/logout flows. Form login/session or federated authentication may fit better depending on the system.

### 13.3. CSRF Can Still Be Relevant

A browser can automatically send cached Basic credentials under matching conditions, much like it automatically attaches cookies. When building state-changing endpoints, do not automatically disable CSRF protection just because you use HTTP Basic or SessionCreationPolicy.STATELESS.

CSRF analysis must consider the threat model: client type, whether credentials are sent automatically, cookie/origin/CORS policies, and HTTP methods. For APIs serving only machine-to-machine clients that explicitly control headers, the design may differ from browser apps; it must have sound justification and corresponding tests.

### 13.4. Reverse Proxy / Load Balancer

Sometimes a browser sends Authorization properly, yet it arrives missing at the application. The cause may be a gateway failing to forward the header or rewriting the request. Configure proxies to forward required headers across appropriate trust boundaries and ensure raw credentials are never written to access logs.

**Do not log all request headers** to debug 401s in production. If observability is needed, log high-level status such as “Authorization header present / scheme Basic”, timestamp, request ID, and outcome; mask the header value completely.

### 13.5. CORS and Preflight Requests

Browser CORS is a separate policy from HTTP Basic. A preflight OPTIONS request may be rejected by security rules if CORS is not configured properly. When serving a cross-origin frontend, configure CORS for allowed origins/methods/headers and test OPTIONS; **do not** fix it by indiscriminately allowing all origins with credentials.

### 13.6. Credential Charset and Colons

RFC 7617 uses the format user-id + ":" + password before Base64 encoding. A username containing a colon cannot be represented unambiguously in Basic; passwords, however, can contain colons. For Unicode usernames/passwords, client and server must agree on the charset; prefer explicit rules/declarations rather than guessing from ASCII test results.

## 14. Common Mistakes When Integrating HTTP Basic

### Mistake 1 — Thinking Basic Encrypts Passwords

Wrong. Basic converts raw username/password to Base64, not encryption. Use HTTPS and protect the Authorization header in logs/proxies.

### Mistake 2 — Sending the Wrong Header Name

Wrong: Authentication: Basic ... or Token: Basic ... and expecting Spring Security to understand. The right header is **Authorization: Basic ...**.

### Mistake 3 — Header Missing the Basic Prefix

Sending a bare Base64 string in Authorization does not match the Basic scheme. It needs the scheme and a space, and the Base64 payload must decode to username:password.

### Mistake 4 — Treating Authorization: Bearer as Basic

A Bearer token is not Base64 of username:password under Basic. If you want Bearer, enable a separate resource server/token authentication mechanism; do not rewrite the prefix by string concatenation.

### Mistake 5 — Comparing Password Directly Against the BCrypt Hash

Wrong. UserDetails stores a hash, not a raw password. PasswordEncoder.matches(raw, storedHash) is how verification works; never use equals between raw and hash.

### Mistake 6 — Confusing 401 and 403

401 usually indicates missing/invalid authentication; 403 can mean valid identity lacking a role or denied by a policy such as CSRF. Inspect SecurityContext, rules, and exception handling rather than overriding status codes manually to mask errors.

### Mistake 7 — Enabling Both formLogin and httpBasic Without Knowing Which Entry Point Responds

When both mechanisms are enabled, the application may redirect HTML clients and challenge API clients based on matchers/Accept headers. If the goal is a pure Basic API, configure it explicitly and test status/WWW-Authenticate.

### Mistake 8 — Believing STATELESS Makes Clients Forget Credentials

STATELESS primarily governs how Spring Security uses sessions. Browsers or clients can still cache and resend Authorization. Basic logout is not as simple as invalidating HttpSession.

### Mistake 9 — Assuming Every Public Request Always Returns 200 Even with a Bad Basic Header

The authentication filter can process an invalid Authorization header before reaching the permitAll rule. Test public endpoints without the header when verifying permitAll.

### Mistake 10 — Forgetting chain.doFilter When Writing Additional Filters

A custom Servlet/Security filter that short-circuits the chain improperly will prevent BasicAuthenticationFilter or AuthorizationFilter from running as expected. Before writing a custom filter, prefer Spring Security's standard extension points and define ordering explicitly.

### Mistake 11 — Logging/Capturing Requests with Real Passwords

The raw Authorization header is a secret. Use test data and redaction tools; restrict access to traces/heap dumps and session recordings. Never attach request captures containing real credentials to issue trackers.

### Mistake 12 — Expecting HTTP Basic to Manage Accounts and Permissions by Itself

HTTP Basic is only a credential transport scheme. UserDetailsService, PasswordEncoder, AuthenticationProvider, authorities, and authorizeHttpRequests rules are what govern authentication and access control.

## 15. Step-by-Step Troubleshooting

If a client receives an unexpected 401/403, check in order:

1. **URL, method, scheme:** does the request hit the right HTTP path, HTTPS/TLS, and HTTP method?
2. **SecurityFilterChain:** are there multiple chains? Does the first matching chain enable httpBasic?
3. **Authorization header:** is it present when reaching the server? Is the scheme Basic? Did the proxy forward it? Check presence without logging raw values.
4. **Encoding:** was the Basic value built from username + ":" + password before Base64? Any charset mismatch or colon in the username?
5. **UserDetailsService:** does the username exist? Are enabled/locked/expired flags set appropriately?
6. **PasswordEncoder:** is the stored hash in the encoder's expected format? Is the password right?
7. **AuthenticationManager:** is a provider configured that can authenticate UsernamePasswordAuthenticationToken?
8. **SecurityContext:** did the filter establish Authentication successfully for this request? Is any custom filter clearing/overwriting the context at the wrong time?
9. **Authorization rules:** does the endpoint use authenticated(), hasRole(), or hasAuthority()? Does the ROLE_ prefix match?
10. **Exception/entry point:** does 401 include the right WWW-Authenticate? Is another login form/handler intervening?
11. **CSRF/CORS:** for POST/OPTIONS, is an independent policy rejecting the request?
12. **Client:** is the browser caching wrong Basic credentials or sending a stale header? Use curl or a fresh independent client to isolate.
13. **Safe observability:** log filter chain flow at an appropriate level, track 401/403 metrics and request IDs; never log passwords, encoded Authorization values, or tokens.

**When debugging, never disable all authentication/authorization just to “make the request pass”.** Instead, reproduce the request with test data, pinpoint the exact state transition, and fix the needed configuration.

## 16. Practice Exercises

### Exercise A — Decode the Header Correctly

Which username/password pair corresponds to Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==? Can it be considered “securely encrypted password”?

**Answer:** Aladdin and open sesame; Base64 is reversible and is not encryption that protects secrets.

### Exercise B — Distinguish 401 and 403

A client sends learner/learner-pass to GET /admin and receives 403. Why not 401?

**Answer:** credentials are valid and Authentication succeeds, but learner has ROLE_USER while the rule requires ROLE_ADMIN. This is an authorization denial, not a bad password.

### Exercise C — Missing Authorization

Call GET /me without sending the header. Does BasicAuthenticationFilter automatically create a default user to grant access? Why does it return 401?

**Answer:** the filter does not invent an authenticated user from a request lacking credentials; the authenticated() rule is not satisfied. The Basic entry point issues the challenge.

### Exercise D — Stateless and Browsers

The server is configured as STATELESS. A browser still calls /me successfully on a second request without the user re-entering a password. Does that prove a server session was used?

**Answer:** No. The browser can automatically resend cached Basic Authorization credentials. Inspect the request/headers and SecurityContext policy instead of inferring from UI behavior.

### Exercise E — Modify the Config Yourself

Change the GET /admin rule from hasRole("ADMIN") to hasAuthority("ROLE_ADMIN"). Are the two equivalent with the sample UserDetailsService? What happens if you change it to hasAuthority("ADMIN")?

**Answer:** hasRole("ADMIN") normally checks ROLE_ADMIN, which is equivalent to hasAuthority("ROLE_ADMIN") under default settings. hasAuthority("ADMIN") checks for the exact string ADMIN, so it does not match a user with ROLE_ADMIN.

### Exercise F — Build a Basic Header in Java

Run BasicHeaderDemo.java and compare its output with the example in section 3. Replace the password with a string containing a colon, then Base64-decode it to observe the rule splitting at the **first** colon.

**Hint:** adding a colon in the password can still be represented; adding one to the username makes the Basic format unable to delimit the username as intended.

### Exercise G — Test a Bad Request on a Public URL

Call GET /public without Authorization and then call it again with invalid Basic credentials. Explain why the second response can differ from 200 even though /public is configured with permitAll.

**Answer:** BasicAuthenticationFilter can process the invalid credentials and return 401 before AuthorizationFilter evaluates permitAll.

### Exercise H — Draft a Test Matrix

For /public, /me, /admin and the two demo accounts, design tests for missing credentials, invalid credentials, valid learner, and valid admin. Verify 200/401/403 and WWW-Authenticate accordingly; do not assume an immutable error body when no custom handler is configured.

## 17. Pre-Production Checklist for HTTP Basic

- [ ] Understand that **Authorization: Basic Base64(username:password)** is an encoding, not secure encryption.
- [ ] Enable **HTTPS** on every transport path carrying credentials; verify reverse proxies and TLS termination.
- [ ] Never log, trace, or return raw Authorization headers, passwords, or decoded credentials.
- [ ] SecurityFilterChain defines proper matchers and enables httpBasic on the endpoints that need it.
- [ ] UserDetailsService or an appropriate AuthenticationProvider is configured with a secure PasswordEncoder.
- [ ] **authenticated/hasRole/hasAuthority** rules apply to exact methods/paths with an appropriate default deny.
- [ ] Distinguish **401 challenge** from **403 insufficient permission**, testing missing/invalid/valid headers.
- [ ] Verify **WWW-Authenticate** and realm are configured properly.
- [ ] Do not assume HTTP Basic is always stateless; configure SessionCreationPolicy explicitly if needed.
- [ ] Account for browser credential caching, Basic logout behavior, and CSRF on state-changing endpoints.
- [ ] Test CORS/OPTIONS, gateway/proxy forwarding, and charset handling when required.
- [ ] Put rate limiting, safe auditing, and brute-force/credential-stuffing monitoring in place.
- [ ] Never use sample accounts/passwords in production; manage secrets and password rotation/resets securely.
- [ ] Before writing custom filters, prefer built-in Spring Security mechanisms and verify the right filter chain.

**Conclusion:** HTTP Basic uses the **Authorization: Basic ...** header to transport Base64-encoded username/password. In Spring Security Servlet, **BasicAuthenticationFilter** turns credentials into an authentication request, **AuthenticationManager/Provider** verifies the password, **SecurityContext** holds the result for the request, and **AuthorizationFilter** decides access. **401** typically signals authentication required with **WWW-Authenticate**, whereas **403** typically signals insufficient permissions after authentication. Because Base64 does not protect secrets, **HTTPS, header protection, and proper access rules** are mandatory.
