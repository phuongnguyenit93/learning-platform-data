# Allowed origins, methods, headers, and exposed headers in Spring Boot — configuring CORS correctly and safely

## 1. What problem does CORS solve?

**CORS (Cross-Origin Resource Sharing)** is an HTTP protocol mechanism that lets a server inform the **browser** whether JavaScript from another origin may access the server's response, and when required, lets the browser send the actual request after a prior check (*preflight*).

For example, a frontend opens at `http://localhost:5173` while a Spring Boot backend listens on `http://localhost:8080`:

~~~text
Browser: HTML/JS page from http://localhost:5173
                    |
                    | fetch("http://localhost:8080/api/message")
                    v
Spring Boot:           http://localhost:8080
                    |
                    | CORS response headers
                    v
Browser: decides whether JavaScript may read the response
~~~

These two addresses have **different origins because their ports differ**, even though both use hostname `localhost`. An origin is the triple **scheme + host + port**. `https://app.example.test` differs from `http://app.example.test`; `https://app.example.test` differs from `https://api.example.test`; `http://localhost:3000` differs from `http://localhost:5173`. Paths such as `/admin` or `/login` **are not part of the origin**.

**CORS is not authentication or authorization.** An allowed CORS request still requires login, roles, resource permissions, CSRF defense, and validation. Conversely, `curl` and server-to-server clients are not blocked by browser CORS enforcement: they can call an endpoint even if the response lacks `Access-Control-Allow-Origin`. CORS restricts **JavaScript's ability to read results through a browser**, not as an API firewall.

Example cross-origin request:

~~~http
GET /api/message HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

The response may include:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"message":"hello"}
~~~

The browser inspects the header and allows scripts from the permitted origin to read the body. If CORS headers are missing or mismatched, the request may **have reached the server and been processed**, yet the browser blocks JavaScript from reading the response. Hence "Network shows 200 yet `fetch` reports CORS" is a very real phenomenon.

## 2. Four core concepts to distinguish

| Spring setting | Corresponding primary HTTP header | What it controls | What it does NOT control |
| --- | --- | --- | --- |
| `allowedOrigins` / `allowedOriginPatterns` | `Access-Control-Allow-Origin` | **Which web pages** may read the response via browser | Whether the user is authenticated or authorized |
| `allowedMethods` | `Access-Control-Allow-Methods` on preflight | **Intended HTTP methods** the browser may send from another origin | Whether a controller implements that method or the user has permission |
| `allowedHeaders` | `Access-Control-Allow-Headers` on preflight | **Request headers scripts want to send** | Which response headers scripts may read |
| `exposedHeaders` | `Access-Control-Expose-Headers` on actual response | **Non-safelisted response headers** JavaScript may read | Which request headers clients may send |

Read the table in two directions:

~~~text
Browser → Spring Boot (request)
  allowedOrigins  : Which Origin is accepted?
  allowedMethods  : Which GET/POST/PUT/DELETE/... are allowed?
  allowedHeaders  : Which Authorization, Content-Type, X-Request-Id,... may be sent?

Spring Boot → Browser (response)
  exposedHeaders  : Which Location, X-Request-Id, ETag,... may JS read?
~~~

**Most common trap:** adding `Authorization` to `exposedHeaders` does not let the browser send `Authorization`; you must configure `allowedHeaders`. Adding `X-Request-Id` to `allowedHeaders` does not let JavaScript read the returned `X-Request-Id`; you must configure `exposedHeaders`.

## 3. Allowed origins: exact origin match, not URL or path

### 3.1. `allowedOrigins`

Example configuration:

~~~java
.allowedOrigins(
    "http://localhost:5173",
    "https://app.example.test"
)
~~~

This allows JS from those two origins to call backend URLs covered by the matching CORS mapping. Origins such as `https://evil.example.test` or `http://localhost:3000` are disallowed unless declared explicitly.

A CORS response normally carries only **one** origin value:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Never:

~~~http
Access-Control-Allow-Origin: https://app.example.test, https://other.example.test
~~~

`Access-Control-Allow-Origin` does not accept a comma-separated list of multiple origins. When a backend permits multiple origins, it matches the incoming `Origin` against the allowlist and returns **the specific matching origin** for that request. Include `Vary: Origin` when responses vary by `Origin` so shared caches do not reuse the wrong variant.

**Never include trailing slashes or paths in allowed origins**: configure `https://app.example.test`, not `https://app.example.test/checkout`. Browsers send `Origin` as scheme/host/port or the special value `null`.

### 3.2. Wildcard origins and credentials

~~~java
.allowedOrigins("*")
.allowCredentials(true)
~~~

is an **invalid/unsafe** configuration for credentialed browser requests. Browsers reject `Access-Control-Allow-Origin: *` when requests include credentials. Spring Framework also forbids combining `*` in `allowedOrigins` with `allowCredentials(true)` under its validation rules.

If a resource is **truly public and uncredentialed**, a wildcard can make sense:

~~~http
Access-Control-Allow-Origin: *
~~~

However, when using cookies, sessions, or HTTP authentication, explicit origins are required:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

The client must also choose the credential-sending mode where appropriate; enabling credentials server-side alone does not force the browser to send cookies.

### 3.3. `allowedOriginPatterns`

Spring supports patterns when many subdomains are needed:

~~~java
.allowedOriginPatterns("https://*.example.test")
.allowCredentials(true)
~~~

Unlike `allowedOrigins("*")`, when a pattern matches, Spring echoes **the actual matched origin** rather than `*`, conforming to credentialed CORS rules.

**Security assessment:** any subdomain such as `team.example.test` is allowed if it matches the pattern, even if that subdomain is controlled by a third party or vulnerable to takeover. Overly broad patterns widen the trust boundary unnecessarily. When there are only 2–3 fixed frontends, prefer `allowedOrigins` listing exact values. Never use `allowedOriginPatterns("*")` with credentials to "let every website read authenticated data."

### 3.4. `Origin: null`

Pages from `file://`, sandboxed iframes, or origins that cannot serialize into a standard tuple may send:

~~~http
Origin: null
~~~

Do not add `"null"` to the allowlist just to silence errors on local HTML files; it opens access to many untrusted opaque-origin contexts. Develop frontends using a local dev server such as Vite, or design your test environment properly. CORS is not a mechanism for identifying a site via a header that non-browsers cannot forge.

## 4. Allowed methods: authorizes methods, does not create endpoints

`allowedMethods` defines which cross-origin HTTP methods browsers may request:

~~~java
.allowedMethods("GET", "POST", "PATCH", "DELETE")
~~~

When the browser sends a preflight asking about `POST`, Spring checks whether it is in the list and emits the corresponding `Access-Control-Allow-Methods`.

**Distinguish three concerns:**

1. CORS permits method `POST` from origin X.
2. Spring MVC actually declares `@PostMapping` at that URL.
3. The user sending `POST` is permitted to perform the action under Spring Security/authorization.

If CORS allows `POST` yet the controller only defines `GET`, the actual request still returns **405 Method Not Allowed**. If the controller defines `DELETE` yet CORS allows only `GET`, cross-origin browsers cannot pass preflight to use `DELETE`. CORS never grants business permissions.

### `OPTIONS` does not need to be added to `allowedMethods` just for preflight to work

Preflight **uses HTTP `OPTIONS`** while asking the browser to check the *actual method* via:

~~~http
Access-Control-Request-Method: POST
~~~

Therefore:

~~~java
.allowedMethods("GET", "POST")
~~~

still allows browsers to send `OPTIONS` preflight asking about `POST`. APIs do not need manual `@RequestMapping(method=OPTIONS)` controller handlers. Spring Framework/`HandlerMapping`/`CorsFilter` handles preflight directly.

### `GET`, `HEAD`, `POST`, and cases that trigger preflight

A simple request meeting CORS safelist criteria (such as `GET` with no custom headers) can **skip preflight**. A `POST` request with `Content-Type: application/json` normally needs preflight because the JSON media type is not safelisted. `PUT`, `PATCH`, and `DELETE` normally require preflight when invoked cross-origin from scripts.

Never try to force a JSON `POST` into a "simple request" just to dodge preflight. **Preflight is part of the browser's protection**, so configure it accurately instead of working around its criteria.

## 5. Allowed headers: which request headers may the client send?

Suppose the frontend calls:

~~~javascript
fetch("http://localhost:8080/api/message", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "req-101"
  },
  body: JSON.stringify({message: "hello"})
});
~~~

The browser sees that the request needs preflight and sends:

~~~http
OPTIONS /api/message HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

The server accepts it only if the configuration allows both request headers:

~~~java
.allowedHeaders("Content-Type", "X-Request-Id")
~~~

The preflight response may contain:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
~~~

The list, casing, and order of values may vary by framework/configuration; browsers apply **case-insensitive semantics to HTTP header names**. Do not write tests asserting exact raw header strings when the requirement is simply containing the permitted headers.

**`Authorization` is a request header.** If the frontend sends a bearer token from JavaScript, you normally need:

~~~java
.allowedHeaders("Authorization", "Content-Type", "X-Request-Id")
~~~

This only states that the browser may **send the header**. It does not issue tokens, validate tokens, or grant roles; the backend still needs authentication filters and permission checks.

### Header wildcards and trust boundaries

~~~java
.allowedHeaders("*")
~~~

permits a broader set of request headers (in credentialed cases Spring has rules echoing the requested headers). Though handy during prototyping, it gives up explicit control over which custom headers client code may send. For authenticated APIs, list the actual headers needed.

Browsers still enforce **forbidden request headers**; CORS settings never let JavaScript set `Host`, `Cookie`, or other Fetch-forbidden headers directly. Putting `Cookie` in `allowedHeaders` **does not let scripts set `Cookie` manually**; sending cookies requires credential mode and browser cookie rules.

Not every request header must appear in `Access-Control-Request-Headers`: the browser lists only those requiring validation; CORS-safelisted request headers meeting conditions can be sent without listing.

## 6. Exposed headers: which response headers may JavaScript read?

By default, scripts can read only **CORS-safelisted response headers** from a valid cross-origin response:

- `Cache-Control`
- `Content-Language`
- `Content-Length`
- `Content-Type`
- `Expires`
- `Last-Modified`
- `Pragma`

Other headers such as `Location`, `ETag`, `Content-Disposition`, `X-Request-Id`, or `X-RateLimit-Remaining` **are not readable by scripts by default** cross-origin. The server must declare:

~~~java
.exposedHeaders("Location", "ETag", "X-Request-Id")
~~~

Actual HTTP response:

~~~http
HTTP/1.1 201 Created
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: Location, X-Request-Id
Location: /api/message/42
X-Request-Id: req-101
Content-Type: application/json
~~~

Then JavaScript can do:

~~~javascript
const response = await fetch("http://localhost:8080/api/message", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({message: "hello"})
});

console.log(response.status);                       // 201
console.log(response.headers.get("Location"));      // /api/message/42
console.log(response.headers.get("X-Request-Id"));  // req-101
~~~

This example assumes the request succeeds, the origin is allowed, CORS is configured properly, no unexpected redirects occur, and the response carries the sample headers.

**`exposedHeaders` does not make the server automatically emit those headers.** If the backend does not return `X-Request-Id`, JavaScript still reads `null` even if it is exposed. You must both **emit the actual header** and **expose its name**.

### Never expose `Set-Cookie`

`Set-Cookie` is a **forbidden response-header name** in Fetch; JavaScript cannot read it via `response.headers.get("Set-Cookie")` even if you list `Set-Cookie` in `Access-Control-Expose-Headers`. The browser manages cookies per cookie policy. Never place secret tokens into exposed headers and treat CORS as an auth layer.

### Wildcard exposed headers and credentials

In the Fetch standard, `Access-Control-Expose-Headers: *` acts as a wildcard only for **non-credentialed** requests. On credentialed requests, `*` is treated as a literal header name. Spring notes that its implementation may still print `*` in certain credentialed cases; **never rely on the wildcard when the frontend needs to read headers with credentials**. Explicitly list `Location`, `ETag`, `X-Request-Id`, and only the headers actually required.

## 7. Credentialed CORS: cookies and fetch credentials

If the frontend must send session cookies to a cross-origin API:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include"
});
~~~

Independent conditions must hold:

1. The browser is permitted to send the cookie per `Domain`, `Path`, `Secure`, `SameSite`, and current third-party cookie policies.
2. The CORS server allows the explicit origin via `Access-Control-Allow-Origin: https://app.example.test`, **never `*`**.
3. The response includes `Access-Control-Allow-Credentials: true`.
4. The backend still authenticates and authorizes the cookie/session properly.
5. State-changing requests have appropriate **CSRF defense**. CORS does not replace CSRF protection.

### Distinguishing **cross-origin** from **cross-site**

`https://app.example.test` and `https://api.example.test` are **cross-origin**, yet may still be same-site under cookie/registrable-domain and scheme criteria. `https://shop.example.test` and `https://other-domain.test` are cross-site. `SameSite` is a **site-based** cookie attribute, not purely origin-based. The two mechanisms are independent; never treat `SameSite=Lax` or CORS as a universal fix for every credential scenario.

If requests are truly cross-site and must carry cookies, modern browsers typically require `SameSite=None; Secure`, while still subject to third-party cookie restrictions and browser privacy protections. During HTTP localhost development, `Secure` cookie behavior can differ from HTTPS production; do not extrapolate from `curl`.

**CORS lets JavaScript read responses; it does not block all state-changing requests.** A traditional HTML form from another site can submit simple requests without CORS preflight; therefore CSRF tokens, `SameSite` policies, and authorization remain essential.

## 8. Complete preflight and actual request flow

Suppose the frontend at `http://localhost:5173` wants to `POST` JSON to `http://localhost:8080/api/message`, with `X-Request-Id`:

~~~text
Browser                       Spring Boot
  |                              |
  | OPTIONS /api/message         |
  | Origin: http://localhost:5173|
  | Access-Control-Request-Method: POST
  | Access-Control-Request-Headers: content-type,x-request-id
  |----------------------------->|
  |                              | check Origin, Method, Headers
  |<-----------------------------|
  | 200 OK (preflight)           |
  | Access-Control-Allow-Origin: http://localhost:5173
  | Access-Control-Allow-Methods: GET,POST
  | Access-Control-Allow-Headers: content-type,x-request-id
  | Access-Control-Max-Age: 1800 |
  |                              |
  | POST /api/message            |
  | Origin: http://localhost:5173|
  | Content-Type: application/json
  | X-Request-Id: req-101        |
  |----------------------------->|
  |                              | controller handles request
  |<-----------------------------|
  | 201 Created                  |
  | Access-Control-Allow-Origin: http://localhost:5173
  | Access-Control-Expose-Headers: Location, X-Request-Id
  | Location: /api/message/42    |
  | X-Request-Id: req-101        |
~~~

**Practical notes:**

- `Access-Control-Allow-Methods` and `Access-Control-Allow-Headers` are primarily consumed by the browser on the **preflight response**.
- `Access-Control-Expose-Headers` takes effect on the **actual response** so the frontend can read headers.
- `Access-Control-Max-Age` is the cache TTL of the **preflight result**, not the TTL of the JSON body or CDN cache.
- Browsers may cap `max-age` below the server-advertised value and may skip `OPTIONS` on repeat calls due to the preflight cache.
- If preflight fails, the browser will **not send the actual request** in the normal flow.
- For a **simple CORS request** without preflight, the actual request can still reach the server even if the origin is denied; the browser only stops scripts from reading the response. Never treat CORS as a CSRF filter.
- Responses include `Vary: Origin`, and sometimes `Access-Control-Request-Method` and `Access-Control-Request-Headers`, so intermediate caches pick the right variant.

## 9. Spring Boot MVC: centralized configuration with `WebMvcConfigurer`

The example below uses **Java 17+, Spring Boot 3.3.x, Spring MVC**, dev frontend `http://localhost:5173`, and production frontend `https://app.example.test`. The CORS mapping applies only to `/api/**`.

~~~java
@Configuration
public class CorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "http://localhost:5173",
                        "https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders(
                        "Content-Type",
                        "Authorization",
                        "X-Request-Id")
                .exposedHeaders(
                        "Location",
                        "X-Request-Id",
                        "ETag")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
~~~

Snippet requires imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

Values and meanings:

- `addMapping("/api/**")`: limits the **backend URLs** receiving CORS rules. Does not open CORS for Actuator, Swagger, admin, or static files.
- `allowedOrigins(...)`: explicit allowlist; the dev port is part of the origin.
- `allowedMethods("GET","POST")`: only the methods required by the sample API.
- `allowedHeaders(...)`: scripts may send `Content-Type`, `Authorization`, and `X-Request-Id`.
- `exposedHeaders(...)`: browser scripts may read `Location`, `X-Request-Id`, and `ETag` when present on responses.
- `allowCredentials(true)`: allows credentialed CORS from matched origins. Does not change how browsers send cookies and does not grant login.
- `maxAge(1800)`: lets the browser cache preflight results up to policy/browser limits.

### 9.1. `@CrossOrigin` on a controller

For a single endpoint, you can use the annotation:

~~~java
@CrossOrigin(
    origins = "https://app.example.test",
    methods = {RequestMethod.GET},
    allowedHeaders = {"Authorization", "X-Request-Id"},
    exposedHeaders = {"ETag"},
    allowCredentials = "true",
    maxAge = 1800)
@GetMapping("/api/summary")
public Summary summary() {
    return service.currentSummary();
}
~~~

This is a **snippet**; `Summary` and `service` belong to a real application. The annotation is handy when a route needs a special policy. **Do not mix global and local configs carelessly**: Spring MVC can **combine** global and local configurations; list-based attributes are merged additively, so an overly broad `@CrossOrigin` can accidentally open extra origins or headers on that route. Pick one **primary configuration source** and test the final effective outcome.

Per Spring MVC docs, `@CrossOrigin` defaults and global mapping defaults are not identical. Never rely on "all origins/all headers" defaults for sensitive APIs; declare policies explicitly.

## 10. Runnable Spring Boot Java 17 project example

This example deliberately **omits Spring Security** so learners see CORS clearly first; Security integration is covered separately below.

Structure:

~~~text
cors-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/cors/CorsApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/cors/CorsHttpTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cors-lab'
~~~

`build.gradle` (uses Spring Boot 3.3.13 as a 3.x and Java 17 example; real projects should use an actively maintained version):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

`src/main/java/demo/cors/CorsApplication.java` — **a complete single Java file**:

~~~java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}

@Configuration
class ApiCorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "http://localhost:5173",
                        "https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders(
                        "Content-Type",
                        "Authorization",
                        "X-Request-Id")
                .exposedHeaders(
                        "Location",
                        "X-Request-Id",
                        "ETag")
                .allowCredentials(true)
                .maxAge(1800);
    }
}

@RestController
class MessageController {
    public record MessageResponse(String message) {
    }

    public record CreateMessage(String message) {
    }

    @GetMapping("/api/message")
    ResponseEntity<MessageResponse> read() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "req-get-101")
                .header(HttpHeaders.ETAG, "\"demo-v1\"")
                .body(new MessageResponse("hello"));
    }

    @PostMapping("/api/message")
    ResponseEntity<MessageResponse> create(
            @RequestBody CreateMessage input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .header(HttpHeaders.LOCATION, "/api/message/42")
                .header("X-Request-Id", "req-post-202")
                .body(new MessageResponse(input.message()));
    }
}
~~~

**Explanation:**

1. Spring Boot auto-configuration loads `WebMvcConfigurer` and registers the CORS mapping on Spring MVC's `HandlerMapping`.
2. Because the URL is `/api/message`, it matches `/api/**`. There is no matching rule for `/admin/**`.
3. `GET` returns `{"message":"hello"}` and response headers `X-Request-Id`, `ETag`.
4. `POST` JSON returns **201 Created**, echoing `input.message()` in the body alongside headers `Location` and `X-Request-Id`.
5. `exposedHeaders` does not generate those headers itself; the controller emits them, and CORS policy permits JS to read them.
6. `allowCredentials(true)` is only a CORS signal; the example has no authentication or business session. When adding security, configure Spring Security and CSRF defense properly.
7. No `@OptionsMapping` or `@RequestMapping(method = OPTIONS)` is needed for preflight: Spring MVC handles preflight per the CORS config.
8. The file holds one public class `CorsApplication` and package-private top-level classes `ApiCorsConfig` and `MessageController`, valid in Java 17. Two public nested records serve as Jackson DTOs.

### 10.1. Starting

Using the Gradle wrapper included in the project:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper yet, generate one with a Gradle version compatible with the plugin and JDK before running. Once the server listens on port 8080, use `curl` to simulate browser CORS headers.

### 10.2. Valid preflight

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id"
~~~

Expect status **2xx** (Spring MVC usually returns 200 for valid preflight) and headers conveying:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

List values do not have to match the exact ordering or casing shown here. `Vary` headers may also appear. **There is no JSON response body** on a valid preflight because the `POST` controller **did not run**.

### 10.3. Actual `POST`

~~~bash
curl -i "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-client-77" \
  -d '{"message":"hello"}'
~~~

Key elements to observe:

~~~http
HTTP/1.1 201 Created
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: Location, X-Request-Id, ETag
Location: /api/message/42
X-Request-Id: req-post-202
Content-Type: application/json

{"message":"hello"}
~~~

`X-Request-Id` in the response is a fixed value set by the demo controller, **not required to match** the request header `req-client-77`. In a real app, correlation IDs should be generated/validated and propagated consistently per logging/tracing policy; the demo merely distinguishes allowed vs. exposed headers.

### 10.4. Rejected `Origin`

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: https://untrusted.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

In the example config, Spring MVC normally returns **403 Invalid CORS request** for an invalid preflight. Crucially, the browser **receives no CORS approval** and never proceeds with the actual `POST` in the preflight flow. Never use `curl` without an `Origin` header to conclude an endpoint has CORS configured properly.

### 10.5. Method or request header outside the allowlist

Preflight asking for `DELETE` will be rejected:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: DELETE"
~~~

Preflight requesting an undeclared header is also rejected:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-internal-secret"
~~~

These tests show that an allowed origin **does not imply** every method or header is allowed. Never fix errors by setting `allowedMethods("*")` and `allowedHeaders("*")` when only specific methods and headers are needed.

## 11. Real frontend example: `fetch` and reading exposed headers

A script running at `http://localhost:5173`:

~~~javascript
const api = "http://localhost:8080/api/message";

async function createMessage() {
  const response = await fetch(api, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": "req-frontend-1"
    },
    credentials: "include",
    body: JSON.stringify({message: "hello from frontend"})
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  console.log("status =", response.status);
  console.log("location =", response.headers.get("Location"));
  console.log("responseId =", response.headers.get("X-Request-Id"));
  console.log("body =", await response.json());
}

createMessage().catch(console.error);
~~~

Because the server configures `allowedOrigins("http://localhost:5173")`, `allowedMethods("POST")`, `allowedHeaders("Content-Type","X-Request-Id")`, and `exposedHeaders("Location","X-Request-Id")`, the response is readable. `credentials:"include"` only lets the browser send cookies if they exist and cookie policies permit; the demo does not issue cookies.

With the example controller, the **logical console values** for the deterministic fields are:

~~~text
status = 201
location = /api/message/42
responseId = req-post-202
body = { message: 'hello from frontend' }
~~~

How JavaScript's console formats objects (quotes, ordering) varies by browser; the above illustrates logical values rather than guaranteeing byte-for-byte console output. If you omit `exposedHeaders("Location",...)`, the HTTP response may still contain `Location`, yet `response.headers.get("Location")` returns `null` in a cross-origin browser.

**Do not try frontend code** like `response.headers.get("Set-Cookie")`: it is always filtered out by Fetch, not because you forgot to add an exposed header.

## 12. Spring Security: preflight must be handled before authentication

Browser CORS preflights normally **do not send session cookies** and are not treated as authenticated business requests. If Spring Security blocks `OPTIONS` before the CORS processor runs, the frontend receives 401/403 on preflight even when the actual endpoint permits valid users.

Per Spring Security docs, integrate CORS into the security filter chain. With Spring MVC already defining `WebMvcConfigurer` CORS mappings, an example Security configuration for a real app is:

~~~java
// Snippet in @Configuration: requires spring-boot-starter-security dependency.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.cors(Customizer.withDefaults());
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Requires imports `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, and `org.springframework.security.web.SecurityFilterChain`. This is an **integration snippet**, not part of the runnable project in section 10. Depending on your auth mechanism (Bearer, OAuth2 resource server, session), add corresponding configuration.

**Do not simply `"permitAll OPTIONS /**"` to solve everything.** If CORS does not run or emit the proper headers, the browser still blocks it. Integrating `http.cors(...)` routes preflight through CORS logic ahead of authentication as designed.

If Spring Security is used alongside a `CorsConfigurationSource` bean, or there are multiple filter chains / multiple sources, verify filter ordering and **which configuration source Security uses**. Never combine a manual `CorsFilter` and `WebMvcConfigurer` across layers without controlling duplicate headers.

### CSRF does not disappear when CORS is enabled

With cookie/session authentication, state-changing requests require CSRF evaluation. Browsers can send "simple" cross-site requests via HTML forms without needing CORS permission to read responses. Never disable CSRF merely because `allowedOrigins` is restricted. For stateless token-based APIs, CSRF design differs; base the choice on your threat model and actual credential mechanism.

## 13. CORS in Spring WebFlux

Spring WebFlux also provides CORS mappings, using `WebFluxConfigurer` and the reactive handler stack—**not `WebMvcConfigurer`** in a pure WebFlux app.

WebFlux configuration snippet (inside a `@Configuration` class):

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins(
                    "http://localhost:5173",
                    "https://app.example.test")
            .allowedMethods("GET", "POST")
            .allowedHeaders(
                    "Content-Type", "Authorization", "X-Request-Id")
            .exposedHeaders("Location", "X-Request-Id")
            .allowCredentials(true)
            .maxAge(1800);
}
~~~

Note that WebFlux's `CorsRegistry` is `org.springframework.web.reactive.config.CorsRegistry`, and the class must `implements WebFluxConfigurer` importing `org.springframework.web.reactive.config.WebFluxConfigurer`.

The HTTP concepts match MVC: preflight, `Origin`, allowed/exposed headers, and credentials. When adding Spring Security WebFlux, use a reactive `SecurityWebFilterChain` and integrate CORS with `ServerHttpSecurity`, rather than copying Servlet MVC's `HttpSecurity`/`CorsFilter` onto Netty WebFlux.

Spring Boot typically favors Servlet MVC when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath. To test which configuration is active, check the actual web application type/starter and use `WebTestClient` when it is a reactive web app.

## 14. Proxies, CDNs, gateways, and CORS

A typical deployment looks like:

~~~text
Browser frontend (https://app.example.test)
   |
   v
CDN / reverse proxy / API gateway
   |
   v
Spring Boot (http://service:8080)
~~~

Often the problem is not `allowedOrigins`, but an intermediary:

- The proxy **blocks `OPTIONS`** with 401, 403, 404, or 405, so preflight never reaches Spring.
- The proxy returns `301/302` for `OPTIONS` from HTTP to HTTPS or adds/strips a slash, breaking preflight/redirects depending on the browser.
- The gateway adds its own `Access-Control-Allow-Origin` while Spring adds another, resulting in **duplicate/invalid headers**.
- The proxy strips `Access-Control-Expose-Headers` or `Access-Control-Allow-Headers`, preventing JavaScript from reading/sending as expected.
- The CDN caches preflight/actual responses yet drops `Origin`, `Access-Control-Request-Method`, or `Access-Control-Request-Headers` from its cache key, serving origin A's policy to origin B.
- TLS termination and forwarded headers cause the backend to misread the external scheme/host when generating URLs, redirects, or cookies; proxy settings must be accurate.
- The proxy alters `Origin` under a bad rule: never treat a client-spoofed `Origin` as authentication proof.

### Where should CORS be configured?

Choose **one clear layer owning the policy**:

1. **In Spring Boot:** fits APIs needing per-controller/URL policies and easy testing via `MockMvc`/`WebTestClient`.
2. **At the API gateway/proxy:** fits centralized rules across many services; ensure preflight is supported and **never overwrite/duplicate** Spring headers.
3. **Combined:** only when each layer has clearly separated duties (e.g., gateway checks a shared allowlist while Spring restricts sensitive routes); test final end-to-end headers.

A reverse proxy can also serve both frontend and API on the **same public origin**:

~~~text
https://app.example.test/          -> frontend
https://app.example.test/api/...   -> reverse proxy -> Spring Boot
~~~

When the browser makes same-origin calls, **no CORS is needed** for those calls. Same-origin proxying simplifies config, yet it does not replace authentication, CSRF, cookies, authorization, or proxy hardening.

### The `Vary` header and shared caches

When `Access-Control-Allow-Origin` is echoed from a multi-origin allowlist, responses should include:

~~~http
Vary: Origin
~~~

For preflight, variation may also depend on:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Spring's CORS processor normally manages the right `Vary` values. Do not accidentally strip them at a CDN; otherwise, a preflight response for one origin/method/header may be served mistakenly to another source. `Vary` does not replace authorization and does not make bodies containing PII safe to public-cache.

Specifically, `Access-Control-Max-Age` is browser preflight caching, **different** from `Cache-Control: public, max-age=...` for response bodies. Never public-cache APIs containing personal information just to reduce preflights.

## 15. Common CORS errors and how to diagnose them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| Browser reports "No Access-Control-Allow-Origin" | Origin mismatch, CORS disabled, error response lacks header, proxy stripped it | Check exact `Origin`, status, final headers; compare against allowlist |
| `http://localhost:3000` works yet `5173` fails | Port is part of the origin | Add the right dev origin; do not use production wildcards |
| HTTPS frontend calling HTTP API blocked | Mixed content or redirect/proxy, not just CORS | Serve the API over HTTPS with consistent security policy |
| `OPTIONS` preflight returns 401 | Security auth runs before CORS | Integrate Spring Security `http.cors(...)`; check gateway |
| `OPTIONS` preflight returns 405 | Proxy/controller handles `OPTIONS` improperly | Let the framework CORS processor handle it; configure forwarding |
| Preflight says request method not allowed | `allowedMethods` omits the actual method | Add the needed method and check the actual HTTP route |
| Preflight says header not allowed | `allowedHeaders` omits `Authorization`/custom header | Add the exact header name; do not confuse with `exposedHeaders` |
| `POST` succeeds yet JS cannot read `Location` | Missing `exposedHeaders("Location")` | Expose `Location` on actual responses |
| JS cannot read `Set-Cookie` even though exposed | `Set-Cookie` is a forbidden response header | Let the browser handle cookies; never expose tokens |
| Credentials mode says wildcard origin invalid | `Access-Control-Allow-Origin: *` with credentialed request | Use an explicit origin and enable credentials deliberately |
| Cookies not sent despite CORS passing | `credentials`, `Domain`/`Path`, `Secure`/`SameSite`, third-party cookie policy | Inspect request `Cookie` header and browser storage/network |
| `curl` returns 200 yet browser `fetch` fails | `curl` does not enforce CORS | Check DevTools preflight, headers, and console |
| Response has two ACAO headers | Gateway and Spring both add it | Pick one CORS owner and remove the duplicate |
| `allowedOrigins("https://*.example.test")` does not match | `allowedOrigins` is not pattern matching | Use a concrete list or controlled `allowedOriginPatterns` |
| API returns 403 yet console mentions CORS | Disallowed origin, auth failure, or Spring CORS rejection | Separate 403s from CORS processor, Security, and gateway logs |
| `OPTIONS` succeeds yet actual returns 401 | CORS let request through, caller unauthenticated | Configure authentication properly; do not edit CORS |
| `GET` works, JSON `POST` fails | JSON triggers preflight; `allowedHeaders`/`Methods` missing | Inspect `Access-Control-Request-*` on `OPTIONS` |
| CORS works locally, fails behind CDN | Proxy strips/caches/redirects/duplicates policy | Test against the public hostname, not only the backend port |

**Priority investigation workflow:**

1. Record the exact frontend URL (scheme, host, port), API URL, and request method/headers/credential mode.
2. Open DevTools → Network: is there an `OPTIONS` request? What are preflight and actual statuses?
3. Inspect `Origin` and `Access-Control-Request-Method` / `Access-Control-Request-Headers` if preflight ran; compare with config.
4. Confirm preflight response has matching `Access-Control-Allow-Origin/Methods/Headers/Credentials`.
5. Inspect actual response `Access-Control-Allow-Origin` and `Access-Control-Expose-Headers`; read the browser console.
6. If using Security, verify `CorsFilter`/Security chain and CSRF/auth; behind a proxy, inspect the **final** headers from the public endpoint.
7. Test a denied origin, denied method, and denied header to confirm the policy is **not overly broad**.

Never "fix" issues by setting `allowedOrigins("*")`, `allowedMethods("*")`, and `allowedHeaders("*")` across every API. That hides misconfigurations and widens the trust surface.

## 16. Automated testing with `MockMvc`

For the project in section 10, using `spring-boot-starter-test`, create `src/test/java/demo/cors/CorsHttpTest.java`:

~~~java
package demo.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsHttpTest {
    @Autowired
    MockMvc mvc;

    @Test
    void validPreflightAllowsMethodAndHeaders() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-request-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "http://localhost:5173"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
            .andExpect(header().exists(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS))
            .andExpect(header().exists(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS));
    }

    @Test
    void actualResponseExposesRequestId() throws Exception {
        mvc.perform(get("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "http://localhost:5173"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                    containsString("X-Request-Id")))
            .andExpect(header().string(
                    "X-Request-Id", "req-get-101"));
    }

    @Test
    void untrustedOriginIsRejectedOnPreflight() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN,
                        "https://untrusted.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void disallowedMethodIsRejected() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void disallowedRequestHeaderIsRejected() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-internal-secret"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.cors.CorsHttpTest
~~~

**These tests prove** that Spring MVC's CORS mapping handles preflight, actual responses, and rejection cases. They **do not** test Spring Security (since the lab omits Security), **do not** simulate browser cookie policies, and **do not** traverse a CDN/reverse proxy. If production includes those layers, add integration tests with the security filter chain and against the real public URL.

Across different framework versions, the status/body for an invalid preflight may differ. The core invariant to verify is that the browser receives no CORS approval; expecting 403 matches Spring MVC's behavior in this lab.

## 17. Testing from a browser and behind a proxy

### Browser console / frontend dev server

Serve the frontend at exact `http://localhost:5173`. Confirm JSON `POST` requests trigger preflight, and then both body and exposed headers can be read. Try switching the frontend to `http://localhost:5174`: since it is not in the allowlist, the browser must block it. Test `Authorization` if the app actually uses bearer tokens; real authentication is still needed to receive 200 after preflight passes.

### Checking behind a reverse proxy

Suppose the external API is `https://api.example.test`, reverse-proxied to port 8080. Send:

~~~bash
curl -i -X OPTIONS "https://api.example.test/api/message" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id"
~~~

At the **public endpoint**, check for 2xx status and `Access-Control-Allow-*` headers, with no duplicate ACAO. Also test the actual request and auth/status separately. If the backend origin passes while the public URL fails, check gateway/ingress/CDN rules, `OPTIONS` forwarding, redirects, CORS header rewriting, or cache-key variation.

One critical test is verifying that a non-allowlisted origin **is rejected**, instead of testing only the happy path. If the effective policy accidentally reflects any `Origin` alongside `Allow-Credentials: true`, browsers on an attacker's site can read authenticated resources under certain conditions—a security vulnerability.

## 18. Limitations of CORS to keep in mind

- **Does not protect APIs from Postman/`cURL`/server clients.** Every sensitive endpoint needs independent authentication and authorization.
- **Does not replace CSRF protection.** Cookies can still be sent via mechanisms outside CORS, especially simple requests or HTML forms.
- **Does not fix HTTPS → HTTP mixed content.** Browsers block it before CORS is evaluated.
- **Does not guarantee cookies are sent.** Fetch credentials, `SameSite`, `Secure`, `Domain`, `Path`, and third-party cookie policies are independent requirements.
- **Does not expose `Set-Cookie`.** It is a forbidden response header.
- **Does not mean scripts can send any header they want.** Forbidden request headers remain controlled by the browser.
- **Does not replace HTTP caching.** `Access-Control-Max-Age` is preflight cache duration, not response-body CDN caching.
- **Does not automatically cover all controllers.** CORS mappings are scoped by URL/`HandlerMapping` and can combine with annotations.
- **Never authorize by the `Origin` header.** Non-browser clients can spoof `Origin`; backend auth must verify trusted credentials.
- **Does not fix real 401/403/404/500 server errors.** CORS may hide detailed bodies/statuses in the browser, yet the underlying failure still needs fixing.

## 19. Pre-release CORS configuration review checklist

1. Are valid frontend origins listed with **exact scheme/host/port**? Are any local/test origins accidentally left in production?
2. Is `allowedOriginPatterns` overly broad, admitting untrusted subdomains or `Origin: null`?
3. Is `allowCredentials(true)` enabled only when needed? If so, is ACAO an explicit origin rather than `*`?
4. Does `allowedMethods` include only methods the API needs cross-origin?
5. Does `allowedHeaders` list the request headers the frontend actually sends, distinct from response headers?
6. Does `exposedHeaders` include only response headers JS needs to read, without trying to expose `Set-Cookie` or secrets?
7. Do browser requests sending JSON/`Authorization`/custom headers trigger preflight, and is `OPTIONS` handled ahead of auth by Spring Security/gateway?
8. Do errors, redirects, and proxies maintain one consistent policy without duplicating `Access-Control-Allow-Origin`?
9. Has credentialed CORS been reviewed alongside CSRF, `SameSite`/`Secure` cookies, and authorization?
10. Do shared caches/CDNs include appropriate `Vary` when ACAO varies by `Origin`?
11. Did you test rejected origins, rejected methods, rejected custom headers, and exposed headers on actual responses?
12. Did you test end-to-end in a real browser against the public proxy URL, not just via `cURL` or `MockMvc`?

## 20. Self-check exercises

**Exercise 1.** Frontend runs at `https://app.example.test`, API at `https://api.example.test`. Is CORS needed?

**Answer:** Yes, they have different hosts → different origins. Allow the frontend origin at the backend/gateway, even if they are same-site for cookies.

**Exercise 2.** Spring configures `allowedHeaders("Authorization")`. Can JavaScript automatically read `Authorization` from the response?

**Answer:** No. `allowedHeaders` controls **request** headers. To let JS read a custom **response** header, use `exposedHeaders`; however, avoid emitting credentials/tokens in response headers unnecessarily.

**Exercise 3.** The response contains `X-Request-Id`, yet JS `response.headers.get("X-Request-Id")` returns `null`. What should you check?

**Answer:** Check whether the actual response contains `Access-Control-Expose-Headers: X-Request-Id`, whether ACAO matches, and whether the header was actually sent.

**Exercise 4.** Given `allowedMethods("POST")`, preflight uses HTTP `OPTIONS`. Must you add `allowedMethods("OPTIONS")`?

**Answer:** Not just for preflight. `OPTIONS` is the preflight method, while `Access-Control-Request-Method: POST` names the actual method being checked; Spring's CORS processor handles preflight.

**Exercise 5.** Is `allowedOrigins("*")` combined with `allowCredentials(true)` valid for using cookies?

**Answer:** No. Browsers reject ACAO `*` with credentials; use explicit origins or tightly controlled origin patterns that echo the matched origin.

**Exercise 6.** Why does a JSON `POST` usually send preflight while a `GET` usually does not?

**Answer:** `Content-Type: application/json` is not a CORS-safelisted `Content-Type`, so JSON `POST` normally requires `OPTIONS`. A `GET` with simple headers may skip preflight.

**Exercise 7.** The browser reports CORS blocked, yet `curl` calls the API successfully. Does the API have a security bug blocking requests?

**Answer:** Do not conclude that. `cURL` does not enforce CORS, whereas the browser enforces cross-origin rules. Inspect `Origin`, preflight, and final headers; authentication remains separate.

**Exercise 8.** Spring Security blocks `OPTIONS` with 401. Should you disable authentication across the whole API?

**Answer:** No. Integrate CORS before Security (e.g., `http.cors(Customizer.withDefaults())` and a valid CORS mapping) so preflight is processed properly; actual requests still require auth.

**Exercise 9.** Can you set `Access-Control-Expose-Headers: *` with credentials and expect every header to be readable?

**Answer:** Do not rely on it. Per the Fetch standard, wildcard does not behave as a wildcard on credentialed responses; list explicit names. `Set-Cookie` remains unreadable regardless.

**Exercise 10.** A CDN cached a CORS response for origin A and served it to origin B. Which headers are involved?

**Answer:** `Vary: Origin`, plus `Access-Control-Request-Method` and `Access-Control-Request-Headers` for preflight. CDN cache keys/rules must respect them rather than relying only on browser enforcement.

## 21. Official documentation

- [Spring Framework — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): preflight/actual requests, `@CrossOrigin`, global CORS mappings, allowed credentials.
- [Spring Framework — CORS in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): reactive CORS mappings, `WebFluxConfigurer`, `allowedOriginPatterns`.
- [Spring Security — Servlet CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): why CORS must run before Security, `http.cors(...)`, and `CorsConfigurationSource`.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser preflight, simple requests, credentials, and response headers.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): explicit origins and wildcards.
- [MDN — Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers): specifying permitted request headers.
- [MDN — Access-Control-Allow-Methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Methods): methods allowed for actual requests.
- [MDN — Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers): script-readable headers and wildcard/credential limits.
- [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): browser rules for preflight, wildcards, credentials, and forbidden headers.

**Remember:** `allowedOrigins` answers **which site**; `allowedMethods` answers **which method**; `allowedHeaders` answers **which request headers may be sent**; and `exposedHeaders` answers **which response headers JavaScript may read**. With credentials, trust only explicit origins—never ACAO `*`. CORS must be paired with proper authentication/authorization, CSRF controls, and proxy policies—never treat it as an API firewall.