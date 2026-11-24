# CORS Preflight OPTIONS: Why Must It Be Processed Before Authentication Decisions in Spring Security Servlet?

## 1. The Problem: The Real Request Hasn't Been Sent Yet, Yet the Browser Is Already Blocked

Suppose the UI runs at `http://localhost:5173` and the Spring Boot API runs at `http://localhost:8080`. The two URLs have **different origins** because they use different ports. The frontend calls the API with `fetch`, including an `Authorization` header. The browser may send an **OPTIONS preflight** before sending the real GET/POST:

~~~http
OPTIONS /api/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

If Security requires an authenticated user right at OPTIONS, the server may return `401 Unauthorized` or `403 Forbidden`. Preflight does not carry login credentials like the real request, so the browser **does not proceed to send the GET/POST**; the user sees a CORS error even though the username, password, or access token used for the real request may be completely valid.

This is the most important point:

> **A CORS preflight is a question from the browser about cross-origin access policy, not a user's business operation. The server must handle this question before forcing the request through the application's authentication/authorization decisions.**

In a **Spring Security Servlet** application, the standard integration is enabling `http.cors(...)` and providing the proper CORS configuration; Spring Security places CORS handling at the appropriate position before the authentication and authorization filters.

Goal of this lesson: explain accurately when OPTIONS preflight occurs, how headers are exchanged, the position of `CorsFilter`, Spring Security 6 configuration, and testing CORS, authentication, authorization, and CSRF independently.

## 2. Distinguishing Origin, Same-Origin, Same-Site, and CORS

An **origin** is defined by the tuple **scheme + hostname + port**. For a UI at `http://localhost:5173`, the following URLs have these relationships:

| API URL | Same origin as frontend? | Reason |
| --- | --- | --- |
| `http://localhost:5173/api` | Yes | Same scheme, hostname, and port. |
| `http://localhost:8080/api` | No | Different port. |
| `https://localhost:5173/api` | No | Different scheme. |
| `http://127.0.0.1:5173/api` | No | Different hostname. |

**Cross-Origin Resource Sharing (CORS)** allows a server to declare which sources may access resources from JavaScript running in a browser. The browser enforces this rule for cross-origin requests governed by CORS. `curl`, Postman, or ordinary server-to-server code **are not blocked by CORS in a browser**; they can still send the exact same HTTP request. Therefore, "Postman works, frontend fails" does not prove the backend has allowed that origin.

**Same-origin** differs from **same-site**: the `SameSite` cookie policy evaluates site relationships, whereas CORS evaluates origins. Two applications on subdomains of the same site can still be **cross-origin** and require CORS handling; cookies and CSRF remain separate decisions.

CORS is a browser mechanism controlling whether code on another origin can read responses or perform certain cross-origin requests. It **does not grant business permissions**, does not protect the API from arbitrary clients, and does not replace authentication/authorization.

## 3. What Is Preflight? When Does the Browser Send OPTIONS?

For certain cross-origin requests, the browser needs to ask the server beforehand whether the intended **method** and **headers** are allowed. It automatically issues an OPTIONS request to **the exact URL of the intended request**, with three typical headers:

- `Origin`: the origin of the page that initiated the request.
- `Access-Control-Request-Method`: the HTTP method of the **actual request**; for example GET, POST, PUT, DELETE.
- `Access-Control-Request-Headers`: names of request headers not on the list exempt from prior asking that the browser intends to send; for example `authorization,content-type`.

A simple CORS request normally **does not** need preflight if it uses GET/HEAD/POST and only uses headers/values in the CORS-safelisted group per the specification. Cases that commonly cause the browser to require preflight:

| Cross-origin JavaScript request | Usually triggers preflight? | Why |
| --- | --- | --- |
| `fetch(url)` with GET and no custom headers | No | Usually a CORS request eligible to be sent directly. |
| GET with `Authorization: Bearer ...` | **Yes** | `Authorization` is not a CORS-safelisted request header. |
| POST with `Content-Type: application/json` | **Yes** | `application/json` is not among the safelisted MIME values for Content-Type. |
| Form POST `application/x-www-form-urlencoded` with no special headers | Usually no | Method and Content-Type meet safelisted conditions. |
| PUT, PATCH, DELETE | **Yes** | These are not CORS-safelisted methods. |
| POST with `X-CSRF-TOKEN` | **Yes** | Custom headers must be evaluated in preflight. |

The complete conditions are determined by the browser's Fetch/CORS algorithm, including header limits and special cases; the table above covers common practical scenarios.

**OPTIONS is the preflight method; `Access-Control-Request-Method` indicates the method of the actual request.** For example, a preflight `OPTIONS /api/items/7` with `Access-Control-Request-Method: DELETE` does not mean the browser has deleted the resource; it is only asking the server whether DELETE is accepted from this origin.

Not every OPTIONS request is a CORS preflight. An OPTIONS request invoked manually that **lacks `Origin` or `Access-Control-Request-Method`** is not a preflight as typically recognized by `CorsFilter`; that request may proceed to authentication, routing, or another OPTIONS handler.

## 4. Two-Step Flow: Ask First, Then Execute

Suppose the frontend calls:

~~~javascript
const response = await fetch("http://localhost:8080/api/notes", {
  method: "GET",
  headers: {
    "Authorization": "Bearer " + accessToken
  }
});
~~~

Because of the Authorization header, the browser may first emit:

~~~http
OPTIONS /api/notes HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

If the origin, method, and header are allowed, a typical CORS response looks like:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

The successful preflight status code is usually 200 or 204 depending on the server; formatting, ordering, or header count may differ. What matters is that the server supplies the policy for the **requested origin, method, and headers**; the browser checks the response. Once preflight is valid, the browser then sends the actual request:

~~~http
GET /api/notes HTTP/1.1
Origin: http://localhost:5173
Authorization: Bearer <access-token>
~~~

At this point the backend evaluates the token, access permissions, and business logic. Even if preflight succeeded, the actual request can still receive **401** (unauthenticated), **403** (insufficient permissions or CSRF check failed), **404**, **500**, etc. In the actual response, appropriate CORS headers still need to appear so the browser lets the frontend read the response; "preflight succeeded" does not automatically authorize the actual request.

Sequence diagram:

~~~text
Web page origin A                            Spring Boot API origin B
         |                                             |
         | OPTIONS /api/notes                          |
         | Origin: A                                   |
         | Access-Control-Request-Method: GET          |
         | Access-Control-Request-Headers: auth...     |
         |-------------------------------------------->|
         |                                             | CorsFilter
         |                                             | - checks origin/method/header
         |                                             | - returns CORS response
         |<--------------------------------------------|
         |                                             |
         | Browser checks CORS response                |
         |           +-----------------------------+   |
         |           | If INVALID: STOP            |   |
         |           +-----------------------------+   |
         |                                             |
         | GET /api/notes + Authorization              |
         |-------------------------------------------->|
         |                                             | CorsFilter (actual request)
         |                                             | Authentication/Authorization
         |                                             | Controller if permitted
         |<--------------------------------------------|
         | Browser checks CORS of actual response      |
~~~

The browser may cache the preflight result according to `Access-Control-Max-Age` within the browser's own limits; therefore you will not necessarily see OPTIONS before **every** identical call. Preflight caching does not replace a login session or authorization outcome.

## 5. Why Must CORS Run Before Authentication and Authorization?

The answer lies in the **semantics of preflight** and the **information the browser sends**:

1. Preflight is sent by the browser to negotiate CORS policy **before** the actual request. It is not a business request.
2. Standard preflight does not attach credentials such as session cookies or the login credentials of the actual request. The intended `Authorization` header is only named **by header name** in `Access-Control-Request-Headers`, without carrying the access token in the preflight.
3. If authentication filters see OPTIONS before the CORS filter, an `anyRequest().authenticated()` rule can cause 401; if an authorization rule rejects it, it can cause 403.
4. The browser interprets a rejected preflight or missing appropriate `Access-Control-Allow-*` headers as **failing the CORS policy**. It does not send the actual request, so the backend never even gets the chance to validate the real credentials.
5. Letting CORS handle it first lets the browser learn the access policy; when the actual request arrives, **authentication and authorization still run in full**.

~~~text
WRONG POSITION:
OPTIONS -> Authentication/Authorization -> 401/403 -> Browser blocks -> NO actual request

RIGHT POSITION:
OPTIONS -> CorsFilter -> valid CORS response
Actual GET/POST/... -> CorsFilter -> Authentication -> Authorization -> Controller
~~~

In the Servlet model, the outermost filter goes through `DelegatingFilterProxy` and then into Spring Security's `FilterChainProxy`. When `http.cors(Customizer.withDefaults())` is configured, Spring Security integrates `CorsFilter` at an early position in the security filter chain, **before the usual authentication steps**. When it encounters a valid preflight, `CorsFilter` responds immediately without continuing through the rest of the chain. For an actual request, it checks and attaches CORS response headers and lets the request proceed.

Distinguish **authentication** from **authorization**: authentication identifies who the client/user is; authorization decides whether they are allowed to access the feature. Both are still needed for the actual request. Enabling CORS **does not** automatically turn `/api/**` into `permitAll()`.

In systems with a reverse proxy, gateway, load balancer, WAF, or multiple security chains, preflight must also be routed to the appropriate CORS component. A gateway returning 401 for OPTIONS before Spring Security can break the flow even when the Java configuration is already correct.

## 6. Configuring Spring Security 6 Servlet Properly

The following complete example uses **Java 17**, **Spring Boot 3.3.5**, Spring Web MVC, and Spring Security 6. We will:

- Allow only the frontend `http://localhost:5173` to call `/api/**` paths.
- Allow actual CORS methods **GET, POST**, and headers **Authorization, Content-Type**.
- Keep `anyRequest().authenticated()` and HTTP Basic to prove preflight **does not** require login while the actual request **still** requires login.
- Keep default CSRF to show that CORS and CSRF are two separate layers of checks.

Maven project structure:

~~~text
cors-preflight-demo/
  pom.xml
  src/main/java/example/cors/CorsPreflightDemoApplication.java
  src/test/java/example/cors/CorsPreflightDemoApplicationTests.java
~~~

**pom.xml**:

~~~xml
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
    <groupId>example</groupId>
    <artifactId>cors-preflight-demo</artifactId>
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

**src/main/java/example/cors/CorsPreflightDemoApplication.java**:

~~~java
package example.cors;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CorsPreflightDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsPreflightDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}demo1234")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @RestController
    @RequestMapping("/api/notes")
    static class NotesController {

        @GetMapping
        Map<String, String> getNotes() {
            return Map.of("message", "read permitted");
        }

        @PostMapping
        Map<String, String> saveNote(@RequestBody Map<String, String> request) {
            return Map.of("saved", request.getOrDefault("message", ""));
        }
    }
}
~~~

Explanation of each key component:

- `.cors(Customizer.withDefaults())` enables CORS integration in the **Spring Security filter chain**. This is what ensures preflight handling happens earlier than authentication.
- The `corsConfigurationSource` bean supplies path-based CORS policy. `/api/**` covers only the API and does not automatically open CORS for every resource in the application.
- `setAllowedOrigins(...)` lists **trusted origins**; hostname, scheme, and port must exactly match the `Origin` sent by the browser.
- `setAllowedMethods(...)` lists the accepted **methods of the actual request**. Preflight uses OPTIONS, but **you do not need to add OPTIONS to allowedMethods just to make GET/POST preflight work**.
- `setAllowedHeaders(...)` lets the browser send `Authorization` and `Content-Type` in the actual request after preflight passes; header names are matched case-insensitively per HTTP rules.
- `setMaxAge(1800L)` suggests the browser cache the preflight decision for 1,800 seconds; the browser may enforce a lower cap.
- `anyRequest().authenticated()` **still protects the actual request**. HTTP Basic provides an easily testable authentication example. The account and `{noop}` are for local development only, **not** a production password-storage design.
- `.csrf(Customizer.withDefaults())` keeps the default CSRF check; this example does not use the trick of disabling CSRF to make POST work.

To run the application, JDK 17+ and Maven are required:

~~~bash
mvn spring-boot:run
~~~

**Option when Spring MVC CORS mapping already exists:** instead of providing a `CorsConfigurationSource` bean, you can declare the policy in `WebMvcConfigurer#addCorsMappings` and then enable `http.cors(...)`; Spring Security can use the MVC configuration when no dedicated CORS source exists. With multiple `CorsConfigurationSource` beans or multiple `SecurityFilterChain` beans, explicitly declare the source for each chain if auto-detection cannot disambiguate. Avoid duplicate configurations across a proxy, custom filter, and MVC without understanding the processing order.

## 7. Testing Preflight and Actual Requests Directly with curl

`curl` **does not enforce the browser's CORS policy**, yet it is very useful for observing the HTTP status and headers the server returns. The following examples use the application from Section 6.

**Step 1 — simulate a GET preflight with an Authorization header, WITHOUT sending a username/password:**

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Expected result: **200 OK**; the response contains `Access-Control-Allow-Origin: http://localhost:5173`, includes the GET method in `Access-Control-Allow-Methods`, and allows `authorization` in `Access-Control-Allow-Headers`. Preflight does not require an `Authorization` header or login cookie.

**Step 2 — actual GET request, without Basic credentials:**

~~~bash
curl -i http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173'
~~~

Expected result: **401 Unauthorized**; even though the origin is valid, the actual request must authenticate. CORS headers may still appear on the 401 response so the browser can process the response properly according to CORS.

**Step 3 — actual GET request, with valid credentials:**

~~~bash
curl -i -u learner:demo1234 \
  http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173'
~~~

Expected result: **200 OK** with body `{"message":"read permitted"}`. This is the HTTP Basic authentication step, occurring **after** the CORS step for the actual request.

**Step 4 — another origin attempts a preflight:**

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: http://untrusted.example' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Result with the default `CorsFilter` and the configuration above: **403 Forbidden / Invalid CORS request**. The browser does not accept this origin; it will not proceed to send the actual request.

**Step 5 — preflight for a JSON POST from an allowed origin:**

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Expected result: **200 OK**. However, if you subsequently send the actual JSON POST with Basic credentials but **without a CSRF token**, the configuration keeping default CSRF may return **403 Forbidden**:

~~~bash
curl -i -u learner:demo1234 \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}' \
  http://localhost:8080/api/notes
~~~

This is **not a contradiction**: preflight only confirms the method and headers allowed for CORS; CSRF is an independent step on the actual request. For POST to succeed in a CSRF-enabled application, the client must obtain and send a valid CSRF token according to the configured repository/handler.

Note: the `Vary` response header, formatting of `Access-Control-Allow-Headers`, or error body may differ depending on version/configuration. What needs to be verified is the status and appropriate policy values, not a byte-for-byte comparison against the illustration.

## 8. Testing with MockMvc: Proving Preflight Precedes Authentication

Add the file **src/test/java/example/cors/CorsPreflightDemoApplicationTests.java**:

~~~java
package example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPreflightDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightSucceedsWithoutAuthentication() throws Exception {
        mvc.perform(options("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "GET")
                        .header("Access-Control-Request-Headers", "authorization"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin", "http://localhost:5173"))
                .andExpect(header().exists("Access-Control-Allow-Methods"))
                .andExpect(header().exists("Access-Control-Allow-Headers"));
    }

    @Test
    void actualGetStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/notes")
                        .header("Origin", "http://localhost:5173"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin", "http://localhost:5173"));
    }

    @Test
    void actualGetWithBasicAuthenticationSucceeds() throws Exception {
        mvc.perform(get("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .with(httpBasic("learner", "demo1234")))
                .andExpect(status().isOk());
    }

    @Test
    void preflightFromUntrustedOriginIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                        .header("Origin", "http://untrusted.example")
                        .header("Access-Control-Request-Method", "GET")
                        .header("Access-Control-Request-Headers", "authorization"))
                .andExpect(status().isForbidden());
    }

    @Test
    void preflightPostIsAllowedButActualPostStillNeedsCsrf()
            throws Exception {
        mvc.perform(options("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers", "content-type"))
                .andExpect(status().isOk());

        mvc.perform(post("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .with(httpBasic("learner", "demo1234"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test suite verifies two separate layers of behavior:

- **A valid preflight without credentials is still handled by CORS**, not blocked by `anyRequest().authenticated()`.
- **The actual request must still authenticate**; an actual POST is also subject to CSRF checking if enabled. An untrusted origin is rejected by CORS before reaching business processing.

`MockMvc` is not a browser and does not automatically issue a preflight. The test must **construct the OPTIONS request with full `Origin` and `Access-Control-Request-Method`** as shown above. Conversely, merely testing a bare `options("/api/notes")` without headers does not prove CORS preflight configuration.

## 9. CORS, 401/403, CSRF, and Credentials: Which Layers Decide What?

| Layer | Question resolved | Example outcome |
| --- | --- | --- |
| **CORS (preflight)** | Can origin A send that method/header to API origin B? | Valid preflight returns 2xx + CORS headers; policy violation may return 403. |
| **Authentication** | Does the actual request prove an identity? | Missing/wrong Basic/JWT/session → 401 or login redirect depending on mechanism. |
| **Authorization** | Does that identity have permission to call the endpoint? | Logged in but lacking permission → usually 403. |
| **CSRF** | Does a state-changing request in an automatically-sent-credential model carry a valid token? | POST/PUT/PATCH/DELETE missing/wrong token → usually 403. |
| **Controller/business logic** | Is the operation valid in terms of data and business rules? | 200/201/400/404/... depending on logic. |

**Preflight is not a promise that the actual request will succeed.** It is only a decision about cross-origin policy. Likewise, logging in successfully does not mean every origin is permitted by CORS.

If the application uses a **session cookie** and the frontend genuinely needs to send cookies cross-origin, additional conditions apply:

- The frontend uses `fetch(url, { credentials: "include" })` when it needs to send credentials across origins.
- The CORS policy must allow a **specific** origin and enable `config.setAllowCredentials(true)`; the relevant response must include `Access-Control-Allow-Credentials: true`.
- You cannot use `Access-Control-Allow-Origin: *` to let the browser read a credentialed response. Avoid blindly reflecting every origin and enabling credentials.
- Cookies must also satisfy `Secure`, `SameSite`, domain/path, and browser third-party cookie policies. A successful CORS check does not by itself cause cookies to be sent.
- **Preflight still does not carry the session cookie**, even when the actual request is expected to send cookies. Thus handling CORS before authentication is even more critical.

The demo in Section 6 uses HTTP Basic, so it **does not enable `allowCredentials`** and does not depend on cookies. Only add `setAllowCredentials(true)` if the application truly needs it and allowed origins are strictly restricted. With an `Authorization` header explicitly attached by the frontend, the browser will preflight because of the header name, regardless of whether the target endpoint accepts that token.

A common security mistake is `allowedOrigins("*")` or an overly broad set of `allowedOriginPatterns`, especially when combined with `allowCredentials(true)`. Identify the exact valid origins in the deployment environment instead of trusting every origin by default just to fix a frontend error.

## 10. Why Doesn't `permitAll() OPTIONS` Usually Solve the Root Problem?

A configuration frequently copied when seeing 401 on preflight:

~~~java
// Illustration of the idea only; does not replace CORS configuration.
auth.requestMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**")
    .permitAll();
~~~

This only tells **AuthorizationFilter** not to require permissions for OPTIONS requests matching the matcher. It **does not** generate `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, or `Access-Control-Allow-Headers`, does not validate allowed origins, and does not fix cases where a proxy or another authentication filter has already blocked earlier. The browser may still reject the response due to missing or invalid CORS headers.

With proper `http.cors(...)` integration, a valid preflight is **handled early by `CorsFilter`**; normally you do not need a rule permitting all OPTIONS just to fix CORS. A rule allowing all OPTIONS can also open a wider scope than actually intended. When there is a business OPTIONS endpoint, authorize it according to that endpoint's actual requirements.

A related mistake: adding `@CrossOrigin` on a controller while Security already returns 401 before the request reaches Spring MVC. You need to integrate CORS configuration into the security filter chain; if using Spring MVC's mapping approach, ensure `http.cors(...)` picks up that configuration.

## 11. Diagnosing Real-World Issues in Order

When the frontend reports "blocked by CORS policy", open **DevTools → Network** (in the browser) and separate the **OPTIONS preflight** from the **actual request**. A helpful sequence:

1. **Is there an OPTIONS before the actual request?** If not, the request may be eligible for direct sending, preflight may be cached, or the error may be in another phase. Do not claim "CORS isn't running" just because you don't see OPTIONS.
2. **Did OPTIONS send the expected `Origin` and `Access-Control-Request-Method`?** Match scheme, host, and port accurately against the configuration; do not confuse the OPTIONS request method with the requested method.
3. **Did OPTIONS receive 401/302 to login?** CORS may be running after the auth mechanism, or a proxy/gateway is blocking OPTIONS. Check filter ordering, the security chain matching the URL, and layers in front of the application.
4. **OPTIONS 200 yet the browser still rejects?** Inspect `Access-Control-Allow-Origin`, `-Methods`, `-Headers`, and `-Credentials` if needed. A 200 status alone is **not enough** for a valid preflight.
5. **OPTIONS 403?** `CorsFilter` itself may have rejected the origin, method, or header; or a security/proxy rule may have rejected it. Use headers and logs to identify the source of the error; **do not assume every 403 is authorization**.
6. **OPTIONS succeeded, yet the actual request gets 401?** CORS passed; check the credentials/token, HTTP Basic/JWT/session, and cookies of the actual request.
7. **OPTIONS succeeded, yet the actual request gets 403?** Inspect authorization, CSRF token, and other policies. A JSON POST using session cookies typically needs a CSRF token even though CORS is permitted.
8. **GET works, JSON POST fails right at OPTIONS?** A GET with no special headers may skip preflight; JSON POST requires checking `Content-Type`. Check `allowedHeaders` and `allowedMethods`.
9. **CORS works locally but fails after deploy?** Check the actual frontend origin, HTTPS, port, reverse proxy routing, HTTP OPTIONS at the gateway, `Vary` header, cache/CDN rules, and filter ordering.
10. **Are there multiple `SecurityFilterChain` beans?** Determine which chain matches **OPTIONS**; a security matcher restricted by method sometimes causes OPTIONS to fall into another chain without CORS. The CORS source must also apply to the request path.
11. **Credentials enabled, yet cookies aren't sent?** Check `fetch.credentials`, cookie `SameSite`/`Secure`, and browser policy. Do not conclude the bug is in `CorsFilter` solely because cookies are missing.
12. **Only seeing a CORS error in the frontend while backend logs show 500?** The browser may hide the response content due to missing CORS headers on the error path. Fix the backend bug and ensure the CORS response policy is applied consistently.

When debugging, log **method, URL, Origin, Access-Control-Request-Method/Headers, status, security chain, and rejection reason** in the development environment. Do not log passwords, bearer tokens, session cookies, or sensitive secrets in production.

## 12. Comprehension Check Exercises

**Scenario A:** The frontend makes a cross-origin GET with `Authorization`. The browser sends OPTIONS without an access token, and the server returns 401. Should authentication be disabled for GET? **No.** Preflight must be handled in the proper order; the actual GET still requires authentication.

**Scenario B:** Preflight returns 200 without `Access-Control-Allow-Headers: authorization` while the browser requested that header. Will the browser send the actual GET? **Normally no**, because the preflight response does not allow the requested header. A 200 response status is not enough.

**Scenario C:** The preflight for a JSON POST succeeds, then the actual POST returns 403 due to a missing CSRF token. Is CORS necessarily misconfigured? **Not necessarily.** CORS and CSRF check different things; identify the source of the 403 on the actual request.

**Scenario D:** The backend defines `allowedMethods = ["GET", "POST"]` without `"OPTIONS"`. Will the POST preflight necessarily be rejected? **No.** `allowedMethods` represents the **actual** methods the browser wants to send; preflight OPTIONS is the policy-querying mechanism.

**Scenario E:** Calling OPTIONS with curl using `-X OPTIONS` but without `Origin` and `Access-Control-Request-Method`; the server returns 401. Does that prove CORS integration is broken? **No.** This is not yet a complete CORS preflight.

**Scenario F:** Using `permitAll()` for all OPTIONS, yet the browser still reports a missing `Access-Control-Allow-Origin`. What needs to be done? **Actually configure and integrate CORS** so the server returns the right origin/method/header policy, and also check proxies and chains.

## 13. Key Takeaways

- **Preflight is an OPTIONS request sent by the browser before the actual request** when the method/headers require querying policy; the `Access-Control-Request-Method` header specifies the actual request's method.
- The browser normally **does not send the actual request's credentials in a preflight**. Therefore you cannot require preflight to go through login like the actual request.
- In **Spring Security Servlet**, enable `http.cors(Customizer.withDefaults())` with a CORS configuration source so `CorsFilter` handles preflight early; when valid, it returns a CORS response without running the rest of the security chain.
- **The actual request still requires authentication, authorization, and possibly a CSRF token**. A 2xx preflight only allows the browser to proceed to the next step for CORS.
- **`permitAll(OPTIONS)` does not generate CORS response headers**; you must verify the policy and filter ordering.
- When errors occur, separate the two requests in Network, inspect the status and all CORS headers, and then determine whether the error belongs to CORS, auth, authorization, CSRF, or a proxy.
