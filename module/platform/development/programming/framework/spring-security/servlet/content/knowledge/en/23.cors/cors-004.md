# CorsConfiguration: origins, methods, headers, and exposedHeaders in Spring Security Servlet

## 1. Context: Why Is CORS Needed?

Suppose the UI runs at **http://localhost:5173** and calls an API at **http://localhost:8080**. These are two different **origins** because an origin is defined by **scheme (http/https) + host + port**. Browsers enforce the Same-Origin Policy, so JavaScript on origin A is not allowed by default to read responses from origin B.

**Cross-Origin Resource Sharing (CORS)** lets server B declare a policy so the browser knows which websites may read results, which methods and request headers are permitted when preflight occurs, and which additional response headers JavaScript may read. In Spring Framework/Spring Security Servlet, **org.springframework.web.cors.CorsConfiguration** holds that policy.

Four properties are central:

| Java API | Which question does it answer? | Example |
| --- | --- | --- |
| **setAllowedOrigins(...)** | Pages from **which origins** are allowed to access cross-origin responses? | http://localhost:5173 |
| **setAllowedMethods(...)** | Which **HTTP methods of the actual request** are accepted for CORS? | GET, POST |
| **setAllowedHeaders(...)** | Which **request headers** is the browser allowed to send? | Content-Type, X-CSRF-TOKEN |
| **setExposedHeaders(...)** | Which additional **response headers** is JavaScript allowed to read? | X-Request-ID, Content-Disposition |

These properties differ in **data direction** and **purpose**. They do not replace authentication, authorization, CSRF, or business checks. CORS is **enforced by browsers**; curl, Postman, or server-to-server clients are not bound by the browser Same-Origin Policy.

## 2. allowedOrigins and Origin Matching

An origin consists of **scheme + host + port**, excluding path, query, or fragment:

| Frontend page | Backend | Cross-origin? |
| --- | --- | --- |
| http://localhost:5173 | http://localhost:8080 | Yes: different port |
| https://app.example.com | https://api.example.com | Yes: different host |
| https://app.example.com | http://app.example.com | Yes: different scheme |
| https://app.example.com/dashboard | https://app.example.com/api | No: path does not count |
| https://app.example.com | https://app.example.com:443 | No: 443 is the default port for HTTPS |

Browsers normally send **Origin: http://localhost:5173** on cross-origin calls. To allow this origin:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("http://localhost:5173"));
~~~

**Note on values:** write the exact origin, without adding **/dashboard** or a trailing **/**. A UI using a different scheme/port is a different origin. You should distinguish trusted frontend origins from the backend API domain.

There are two APIs:

~~~java
// Explicit list of origins:
cors.setAllowedOrigins(List.of(
        "http://localhost:5173",
        "https://app.example.com"));

// Alternative when there is a real need for multiple subdomains:
cors.setAllowedOriginPatterns(List.of("https://*.example.com"));
~~~

**allowedOrigins** takes exact origin values or the wildcard **"*"** in permissible cases. **allowedOriginPatterns** accepts Spring's pattern syntax, for example **https://*.example.com**, not general regex. When an origin matches a pattern, Spring returns the specific origin in **Access-Control-Allow-Origin**.

For requests carrying cookies/credentials, **do not combine allowedOrigins("*") with allowCredentials(true)**. Browsers do not accept the wildcard **Access-Control-Allow-Origin: *** with credentialed requests; Spring also checks this and may report an invalid configuration. List exact trusted origins. Do not enable overly broad patterns if subdomains might be managed by untrusted parties.

## 3. allowedMethods: Which Methods Are Permitted?

~~~java
cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
~~~

This list is for the **methods of the actual API request**. For requests requiring preflight, the browser sends **OPTIONS** to ask whether the intended method is permitted:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

In the example, **Access-Control-Request-Method: POST** must be matched against **allowedMethods**. **OPTIONS** is the preflight method; **it is not necessary to add OPTIONS to allowedMethods for a POST preflight to be permitted**.

When valid, the preflight response may carry:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
~~~

The lines above illustrate the semantics and do not guarantee the exact header ordering or set across every version/proxy. The browser decides whether to send the actual POST based on the preflight response.

**Distinguish two layers of checks:** CORS allowing POST does not mean the user is authorized to create an order. The actual request can still return 401, 403, or 422 due to authentication, authorization, CSRF, or validation. Conversely, if a method is not permitted by CORS, the browser will not let JavaScript invoke/read it under CORS, even though the endpoint can still receive requests from non-browser clients.

## 4. allowedHeaders: Request Header Names

~~~java
cors.setAllowedHeaders(List.of(
        "Content-Type",
        "X-CSRF-TOKEN",
        "X-Request-ID"));
~~~

**allowedHeaders** describes **request headers the browser wants to send**; preflight declares the names in **Access-Control-Request-Headers**. For example:

- **Content-Type: application/json** usually triggers preflight because it is not among CORS-safelisted Content-Type values.
- **Authorization: Bearer ...** is a non-safelisted request header; if the frontend actually sends it, **Authorization** must be permitted.
- **X-CSRF-TOKEN** is a header commonly used when sending a CSRF token for an application authenticating via session cookies.
- **X-Request-ID** on the **request** only needs allowedHeaders if the frontend proactively sends it. If only the server returns X-Request-ID, that name needs **exposedHeaders**, not allowedHeaders.

HTTP header names are semantically case-insensitive. Not every GET/POST triggers a preflight: a GET sending no special headers normally skips OPTIONS, while a GET adding Authorization or custom headers normally needs one.

You can declare **setAllowedHeaders(List.of("*"))** to accept a broad set, though in production you should list only the needed headers to minimize over-permissive configuration. **allowedHeaders does not govern which response headers JavaScript can read**; that is a different property.

## 5. exposedHeaders: Response Header Names

Even when a request passes CORS, cross-origin JavaScript can only read the **CORS-safelisted response headers** automatically: **Cache-Control, Content-Language, Content-Length, Content-Type, Expires, Last-Modified, Pragma**. Other response headers must be declared via **Access-Control-Expose-Headers**:

~~~java
cors.setExposedHeaders(List.of(
        "X-Request-ID",
        "Content-Disposition"));
~~~

Example server response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: X-Request-ID,Content-Disposition
X-Request-ID: request-42
Content-Disposition: attachment; filename="orders.csv"
Content-Type: application/json
~~~

Frontend:

~~~javascript
const response = await fetch("http://localhost:8080/api/orders", {
  credentials: "include"
});
console.log(response.headers.get("X-Request-ID"));     // request-42
console.log(response.headers.get("Content-Type"));     // application/json
~~~

If the actual response contains **X-Request-ID** without exposing it, DevTools Network may still display that header, yet **response.headers.get("X-Request-ID")** in cross-origin JavaScript returns **null**. **exposedHeaders only permits reading existing headers; it does not create headers.** The controller or gateway must actually emit the required header.

Do not expose **Set-Cookie** expecting JavaScript to read it: per Fetch, it is a **forbidden response-header name** and is filtered out of response.headers; **HttpOnly** cookies are also unreadable from document.cookie. With credentialed requests, use an explicit exposedHeaders list and avoid relying on wildcard "*" because wildcard interactions with Fetch and Spring have subtle pitfalls.

## 6. CORS Requests, Preflight, and Direction of Each Header

A GET request with no special headers can go directly:

~~~http
GET /api/orders HTTP/1.1
Origin: http://localhost:5173
~~~

If the server returns valid CORS headers, the browser lets code read the response. However, for a JSON POST with a CSRF header:

~~~javascript
await fetch("http://localhost:8080/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "actual-token-value-from-server"
  },
  body: JSON.stringify({ name: "order-01" })
});
~~~

The browser normally sends an **OPTIONS preflight** first, with **Origin**, **Access-Control-Request-Method: POST**, and **Access-Control-Request-Headers: content-type,x-csrf-token**. If the response allows the origin, POST, and those request headers, the browser then sends the actual POST. Session cookies are included only when **fetch credentials** and cookie policy allow. Then the browser evaluates CORS headers on the actual response before letting JS read it.

Preflight can be cached per **Access-Control-Max-Age** and browser limits. **Do not write frontend code to invoke preflight manually**; that is the browser's job. Having an Origin on a request does not guarantee there will be a preflight.

| Header | Direction | Configuration/purpose |
| --- | --- | --- |
| Origin | Browser → API | Matched against allowedOrigins/allowedOriginPatterns |
| Access-Control-Request-Method | Browser → API, preflight | Matched against allowedMethods |
| Access-Control-Request-Headers | Browser → API, preflight | Matched against allowedHeaders |
| Access-Control-Allow-Origin | API → Browser | Permitted origin |
| Access-Control-Allow-Methods | API → Browser, preflight | Methods usable |
| Access-Control-Allow-Headers | API → Browser, preflight | Request headers permitted to be sent |
| Access-Control-Expose-Headers | API → Browser, response | Additional response headers JS may read |
| Access-Control-Allow-Credentials | API → Browser | allowCredentials |
| Access-Control-Max-Age | API → Browser, preflight | maxAge |

**Access-Control-Allow-Headers** and **Access-Control-Expose-Headers** are both response headers yet serve two different purposes: the former grants permission to **send request headers**, while the latter grants permission to **read response headers**.

## 7. Runnable Example: Spring Boot 3.4.5, Java 17, and Spring Security Servlet

This example uses backend **http://localhost:8080**, frontend **http://localhost:5173**, allows GET/POST, JSON + CSRF request headers, and exposes **X-Request-ID**. To demonstrate independence, **CSRF remains enabled** by default; endpoints use **permitAll()** only to avoid setting up login in the demo.

Create the project:

~~~text
cors-servlet-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cors/CorsDemoApplication.java
    └── test/java/demo/cors/CorsDemoApplicationTests.java
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
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>cors-servlet-demo</artifactId>
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

**src/main/java/demo/cors/CorsDemoApplication.java**:

~~~java
package demo.cors;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN", "X-Request-ID"));
        cors.setExposedHeaders(List.of(
                "X-Request-ID", "Content-Disposition"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().permitAll());
        // CSRF remains enabled by default.
        return http.build();
    }
}

@RestController
@RequestMapping("/api")
class OrderController {
    @GetMapping("/orders")
    ResponseEntity<Map<String, String>> list() {
        return ResponseEntity.ok()
                .header("X-Request-ID", "request-42")
                .body(Map.of("status", "ready"));
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
                request.getAttribute(CsrfToken.class.getName());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "token", token.getToken(),
                        "headerName", token.getHeaderName()));
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, String>> create(
            @RequestBody Map<String, String> order) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Request-ID", "request-43")
                .body(Map.of("name", order.getOrDefault("name", "unnamed")));
    }
}
~~~

**Code explanation:** **CorsConfiguration** holds the policy; **UrlBasedCorsConfigurationSource** binds the policy to the server-side API path **/api/***. **http.cors(Customizer.withDefaults())** adds CORS handling into the Spring Security filter chain; cookie-less preflight can also be processed before the authentication step. **anyRequest().permitAll()** is for demo use only, not a production configuration. CORS does not automatically disable CSRF.

The **GET /api/csrf** endpoint lets the UI fetch a real token issued by Spring Security while setting **Cache-Control: no-store**. With Spring Security 6, the token in the request attribute may be XOR-masked before presentation to mitigate BREACH risk; the frontend sends that token back via the specified header. **GET /api/orders** returns the **X-Request-ID** response header to test exposedHeaders.

### 7.1. Testing Preflight with curl

Run the backend:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -H "Origin: http://localhost:5173" \
  "http://localhost:8080/api/orders"

curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: https://attacker.example" \
  -H "Access-Control-Request-Method: POST"
~~~

Expected observations: valid GET returns **200** with the exact **Access-Control-Allow-Origin** and **X-Request-ID**; valid preflight is accepted and returns the required **Access-Control-Allow-*** headers; an untrusted origin is rejected, typically **403**. The exact set of headers may differ in order and casing.

**curl does not enforce the browser's CORS policy**; it only helps verify which headers the server sends. On Windows PowerShell 5.1, **curl** may be an alias for Invoke-WebRequest; use **curl.exe** if you want curl syntax.

### 7.2. Calling fetch from a Real UI

Open a frontend served at **http://localhost:5173**. The following JavaScript uses the same cookie/session when fetching the CSRF token and posting:

~~~javascript
const api = "http://localhost:8080/api";

// GET: no preflight needed when no special headers are sent.
const getResponse = await fetch(api + "/orders", {
  credentials: "include"
});
console.log(getResponse.status);                     // 200
console.log(getResponse.headers.get("X-Request-ID")); // request-42
console.log((await getResponse.json()).status);       // ready

// Fetch the CSRF token from the server and let the browser receive/keep the session cookie.
const tokenResponse = await fetch(api + "/csrf", {
  credentials: "include"
});
const csrf = await tokenResponse.json();

// JSON POST: the browser normally sends an OPTIONS preflight automatically first.
const postResponse = await fetch(api + "/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ name: "order-01" })
});
console.log(postResponse.status);                     // 201
console.log(postResponse.headers.get("X-Request-ID")); // request-43
console.log((await postResponse.json()).name);         // order-01
~~~

This is a learning scenario running on a **page served from the exact allowed origin**; running in a page on another origin will be governed differently by CORS. If login/logout rotates or clears the CSRF token, the UI must obtain a new token. Cookie configuration (SameSite, Secure, Domain...), session store, and browser policy must also allow the cookie to be used in fetch.

## 8. Testing the Server with Spring Security Test and MockMvc

Create **src/test/java/demo/cors/CorsDemoApplicationTests.java**:

~~~java
package demo.cors;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CorsDemoApplicationTests {
    private static final String ALLOWED = "http://localhost:5173";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightAllowsConfiguredOriginMethodAndHeaders()
            throws Exception {
        mvc.perform(options("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED)
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                "content-type,x-csrf-token"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void preflightRejectsUnlistedOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                        .header(HttpHeaders.ORIGIN, "https://attacker.example")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void responseExposesRequestId() throws Exception {
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                        containsString("X-Request-ID")))
                .andExpect(header().string("X-Request-ID", "request-42"));
    }

    @Test
    void corsAllowedDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"order-01\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidCsrfSucceeds() throws Exception {
        mvc.perform(post("/api/orders")
                        .header(HttpHeaders.ORIGIN, ALLOWED)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"order-01\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("order-01"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify preflight origin/method/headers, rejected origin, exposed response header, and the distinction between CORS and CSRF. **MockMvc simulates the server side**; you must test in a real browser to observe cookie policies, preflight caching, and JavaScript's `response.headers` restrictions.

## 9. allowCredentials, Session Cookies, and CSRF

For a UI using session cookies, the code typically needs:

~~~java
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowCredentials(true);
~~~

and fetch needs **credentials: "include"** for cross-origin. Credentialed request responses must have **Access-Control-Allow-Origin** equal to the specific origin and **Access-Control-Allow-Credentials: true**; wildcard origin is invalid here.

This **does not guarantee cookies will be sent**. Cookies are also governed by **Domain, Path, SameSite, Secure, HttpOnly**, anti-third-party-cookie rules, and HTTPS availability. For truly cross-site relationships, a **SameSite=None; Secure** cookie is typically required to be sent in that context. **allowCredentials** allows the browser to handle credentials under CORS policy; it does not alter cookie restrictions.

**CORS is not CSRF:** certain POST requests from simple HTML forms can be sent by the browser even without preflight; CORS mainly prevents code from an unpermitted origin from reading responses or making requests requiring preflight. For APIs using automatically attached cookies, CSRF protection is still needed for state-changing operations. **permitAll()** also does not automatically exempt CSRF checks.

**CORS is not authorization:** non-browser clients can set Origin arbitrarily; the backend must still authenticate, check permissions on resources, validate input, and audit as required. For server-to-server calls not running in a browser, CORS is generally not an enforced boundary.

## 10. Integrating Spring MVC, Spring Security, and Scope of Application

Spring MVC supports **@CrossOrigin** or **WebMvcConfigurer#addCorsMappings**. Spring Security can integrate MVC's CORS policy under appropriate configuration conditions. In this example, the policy is declared **explicitly via a CorsConfigurationSource bean** and activated via **http.cors(Customizer.withDefaults())**, making it clear which configuration source the filter chain uses.

If an application has multiple SecurityFilterChain beans, check which chain actually handles **/api/** and ensure CORS is enabled on that chain. If an OPTIONS preflight hits an authentication filter before CORS, it may get 401 due to carrying no cookies; this is why the order of CORS and Security matters greatly. Avoid creating multiple CorsFilter instances or duplicate CORS sources with unclear precedence.

**registerCorsConfiguration("/api/**", cors)** is a **server path** pattern, not an allowed origin. **setMaxAge(3600L)** sets how many seconds preflight is cached (browsers still have their own limits), not the lifetime of a session, token, or cookie. **applyPermitDefaultValues()** populates relatively permissive defaults; do not call it without reviewing the unconfigured properties.

## 11. Real-World Incidents and How to Debug

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Browser reports missing Access-Control-Allow-Origin | Origin mismatches scheme/port/host; path does not apply CORS | Check the request's Origin and policy mapping |
| OPTIONS returns 403 | allowedOrigins, allowedMethods, or allowedHeaders mismatch | Compare Access-Control-Request-Method/Headers against config |
| OPTIONS returns 401 | Security authentication runs before CORS | Inspect http.cors(...) and the active filter chain |
| GET works, JSON POST gets CORS error | JSON POST requires preflight; Content-Type not yet allowed | Allow Content-Type and POST if required by business logic |
| Authorization header causes preflight error | allowedHeaders does not contain Authorization | Add Authorization when the real client uses it |
| X-Request-ID visible in Network yet JS reads null | exposedHeaders does not list the header | setExposedHeaders(List.of("X-Request-ID")) |
| Browser rejects wildcard origin + credentials | Incompatible allowCredentials and allowedOrigins config | Use explicit origins |
| curl returns 200 yet fetch fails | curl does not enforce browser CORS | Inspect DevTools Network and CORS response |
| Preflight passes then POST 403 | Missing/wrong CSRF token, authorization, or backend error | Inspect actual request, server logs, token/session |
| Cookie not included | credentials, SameSite, Secure, Domain, or browser policy | Inspect Application/Cookies, network request |
| Through CDN/proxy works sometimes and fails other times | CORS response wrongly cached without Origin/preflight headers | Check Vary: Origin, Access-Control-Request-Method/Headers |

When debugging, proceed step by step: **actual Origin** → presence of **OPTIONS preflight** → **Access-Control-Request-Method/Headers** → **Access-Control-Allow-*** in the response → status and logic of the **actual request** → **exposedHeaders** if JS cannot read a response header. Do not disable CSRF or open all origins to "fix" browser errors without understanding the specific request.

## 12. Self-Check

1. Is a UI at **localhost:5173** calling an API at **localhost:8080** cross-origin? **Yes, different port.**
2. OPTIONS preflight asks for POST permission: which property is **POST** checked against? **allowedMethods.**
3. The UI sends header X-CSRF-TOKEN yet only wants to read X-Request-ID from the response: the first belongs in **allowedHeaders**, the second in **exposedHeaders**.
4. The API returns X-Request-ID yet JS reads null even on a 200 response: check **Access-Control-Expose-Headers**.
5. Can **allowedOrigins("*")** be used with **allowCredentials(true)**? **No.**
6. If preflight succeeds yet POST gets 403, is it definitely a CORS error? **No: it may be CSRF/authz.**
7. Does CORS block curl or Postman from setting Origin themselves? **No, CORS is primarily enforced by browsers.**

**Key Takeaways:** **allowedOrigins** restricts **origins**, **allowedMethods** restricts **request methods**, **allowedHeaders** restricts **sent request headers**, and **exposedHeaders** grants cross-origin JavaScript permission to **read response headers**. On Spring Security Servlet, integrate CorsConfiguration via **CorsConfigurationSource + http.cors(...)**, test both preflight and actual requests, and keep authentication, authorization, and CSRF separate.
