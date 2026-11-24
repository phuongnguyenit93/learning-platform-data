# Simple requests, OPTIONS preflight, and CORS headers in Spring MVC

## 1. Real-world problem: a cross-origin frontend calling an API

A frontend running at `https://app.example.test` calls an API at `https://api.example.test`:

~~~javascript
const response = await fetch("https://api.example.test/api/demo/items");
const items = await response.json();
console.log(items);
~~~

The two addresses have different hostnames and are therefore **different origins**, even though both use HTTPS. The browser enforces the **same-origin policy**: JavaScript on one origin is not permitted to arbitrarily read responses from another origin unless the server grants permission via **Cross-Origin Resource Sharing (CORS)**.

The server can send:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test

[{"id":1,"name":"Spring MVC"}]
~~~

If the request/response satisfies the CORS policy, the browser allows script to read the JSON. If the appropriate header is missing, the server **may still have processed the HTTP request and sent the response**, yet the browser prevents JavaScript from reading the result. This is the fundamental point: **CORS is a browser-enforced response access control mechanism**, not a user authentication system.

### 1.1. Lesson goals

After this lesson, you should be able to clearly distinguish:
1. How an **origin** is computed from scheme, host, and port.
2. What a **CORS-safelisted / simple** request is, why it has **no preflight**, and why it still needs response headers.
3. When the browser automatically sends an **OPTIONS preflight**, and the contents of `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
4. The exact meaning of `Access-Control-Allow-Origin`, `-Methods`, `-Headers`, `-Credentials`, `-Expose-Headers`, `-Max-Age`, and `Vary`.
5. How to configure CORS in Spring MVC with `WebMvcConfigurer` or `@CrossOrigin`, and how to integrate Spring Security in the right order.
6. How to test simple/preflight requests with MockMvc, and spot overly broad configurations, wrong origins, cookie/credential issues, and security mistakes.

This lesson uses Java 17+, Spring Boot 3.x / Spring MVC Servlet stack. The Spring Boot 3.3.5 examples reproduce the mechanics, while the CORS standard itself is defined by browser Fetch/HTTP, **not redefined by Spring**.

## 2. Origin and the same-origin policy

An origin consists of a triple:

~~~text
origin = (scheme, hostname, effective port)
~~~

For example, consider a page running at `https://app.example.test`:

| Target URL | Same-origin? | Reason |
| --- | --- | --- |
| `https://app.example.test/api/items` | Yes | Same scheme, hostname, and default port 443 |
| `https://app.example.test:443/api/items` | Yes | Port 443 is the default port for HTTPS |
| `http://app.example.test/api/items` | No | HTTP scheme differs from HTTPS |
| `https://api.example.test/api/items` | No | Different hostname/subdomain |
| `https://app.example.test:8443/api/items` | No | Port 8443 differs from 443 |
| `https://app.example.test/other/path` | Yes | Different path **does not change the origin** |

Origin does not equal site: in some cases, two subdomains have different origins yet are considered same-site for cookie policies. **CORS, SameSite cookies, and CSRF are not a single mechanism**.

A CORS request typically carries the header:

~~~http
Origin: https://app.example.test
~~~

The `Origin` value **has no path**, no trailing slash, and consists of scheme + host + port if different from the default port. Certain special cases have a `null` origin (sandboxed frames, file/opaque origins); **do not grant `null` arbitrarily** because many untrusted contexts can carry this value.

Requests without `Origin`, such as many server-to-server clients or default curl calls, do not go through the same CORS enforcement flow as browsers. Simulating an `Origin` header with curl only helps observe server responses; it **does not reproduce all browser decisions**.

## 3. What is a "simple" / CORS-safelisted request?

The term *simple request* is commonly used for requests within the scope of **not requiring CORS preflight** under Fetch. It is not "GET requests are always simple": conditions on both the method and request headers **must be satisfied simultaneously**.

### 3.1. Methods

Commonly encountered CORS-safelisted methods:

- `GET`
- `HEAD`
- `POST`

`PUT`, `PATCH`, and `DELETE` normally require preflight when called cross-origin from a browser, even without a body. `OPTIONS` is the method the browser uses to ask permission before sending the actual request; you **do not** need to call OPTIONS manually from JavaScript just because an endpoint uses PUT.

### 3.2. Request headers

Request headers explicitly set by script must belong to the **CORS-safelisted request headers** group and satisfy additional value/size constraints. Common ones include:
- `Accept`.
- `Accept-Language`.
- `Content-Language`.
- `Content-Type` with the media type constraint below.
- `Range` in certain cases where a simple value has **only one** byte range.

Fetch also specifies detailed constraints on values, lengths, unsafe bytes, and user-agent behavior; thus the list is a practical guide, **not a complete algorithm replacing the Fetch spec**. Browser-managed headers like `User-Agent`, `Host`, and certain forbidden request headers are not treated as arbitrary script-set headers.

For `Content-Type`, the common CORS-safelisted media type essences are:

~~~text
application/x-www-form-urlencoded
multipart/form-data
text/plain
~~~

**`application/json` is not on this list.** Consequently, cross-origin JSON `POST` typically triggers preflight even though `POST` is a safelisted method. Conversely, a browser-submitted form POST with `application/x-www-form-urlencoded` and no custom headers usually needs no preflight.

Also note that the name "simple" is a CORS control classification, **not a statement that the request is safe or read-only**. A simple `POST` can still mutate state, and the browser may send the request before confirming permission to read the response.

### 3.3. Scenario table

| Request from cross-origin frontend JS | Typical preflight? | Explanation |
| --- | --- | --- |
| `fetch(url)`, GET, no custom header | No | GET + safelisted headers |
| `fetch(url, {method:"HEAD"})` | No | HEAD |
| POST `application/x-www-form-urlencoded` | No | POST + safelisted media type, if other conditions hold |
| POST `text/plain` | No | Same as above |
| POST `application/json` | Yes | `Content-Type` is not safelisted |
| GET with `Authorization: Bearer ...` | Yes | Authorization is not a safelisted request header |
| GET with script-set `X-Request-Id` | Yes | Custom header |
| `PUT` with JSON | Yes | Both method and Content-Type are outside the safelist |
| `DELETE` without body | Yes | DELETE is not safelisted |
| POST multipart FormData with browser-set boundary | Usually no | Provided no non-safelisted headers are added and remaining conditions hold |

**Do not manually add `Content-Type: multipart/form-data` when sending `FormData` with fetch**: the browser needs to generate a boundary matching the body; setting the header incorrectly yourself can prevent the backend from parsing multipart. Upload streaming, event listeners, or special browser policies can also affect preflight; watch the Network tab in your target browser.

## 4. Simple request flow: no OPTIONS, still requires CORS headers

Frontend:

~~~javascript
const r = await fetch("https://api.example.test/api/demo/items", {
  method: "GET",
  headers: { Accept: "application/json" }
});
const items = await r.json();
~~~

The browser sends the actual request directly:

~~~http
GET /api/demo/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

The server processes GET and adds at least a valid origin policy:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

[{"id":1,"name":"Spring MVC"}]
~~~

**There is no `Access-Control-Request-Method` in a normal GET**, and `Access-Control-Allow-Methods` is not a required condition on a simple GET response. The browser checks `Access-Control-Allow-Origin` (and credentials if the request includes credentials) to decide whether script may read the response.

If the server omits `Access-Control-Allow-Origin` or its value does not match the origin, JavaScript typically sees a CORS error/`TypeError: Failed to fetch` and cannot read the HTTP body/status as a normal response. In server logs, the GET may still be recorded as 200. Therefore **"Network shows 200" does not prove JavaScript has read access**.

### 4.1. Why isn't a simple request CSRF protection?

A malicious page can cause the browser to send a simple form POST to another website while cookies are attached by the browser according to cookie policy. Even though CORS forbids script from reading the response, **the side effect on the server may already have occurred**.

CORS is not a CSRF filter. For session/cookie authentication and state-changing methods, you need CSRF tokens or an appropriate CSRF defense, `SameSite`/`Secure` controls, Origin/Referer checks where appropriate, and per-action authorization. Do not disable CSRF simply because you configured a CORS allowlist.

## 5. OPTIONS preflight: what does the browser ask before sending the actual request?

Suppose the frontend wants to create a resource with JSON:

~~~javascript
await fetch("https://api.example.test/api/demo/items", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "req-42"
  },
  body: JSON.stringify({ name: "Spring CORS" })
});
~~~

Because JSON Content-Type and the custom header are not safelisted, the browser usually sends an **OPTIONS preflight**:

~~~http
OPTIONS /api/demo/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

Meaning:
- `Origin`: the page calling the API.
- `Access-Control-Request-Method`: the method **intended for the subsequent request**, here POST. The current request's method is OPTIONS.
- `Access-Control-Request-Headers`: the non-safelisted headers the actual request wants to send. Browsers typically normalize names to lowercase and may sort them.
- Preflight **does not send the POST JSON body**. It is purely a policy check.
- Under Fetch, CORS preflight **does not send credentials** (such as cookies) of the actual request. Some TLS client certificate environments have implementation quirks; do not design application flows around credentials appearing in preflight.

If the server grants permission:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PUT
Access-Control-Allow-Headers: Content-Type, X-Request-Id
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

The `Vary` header can be combined into a single comma-separated line instead of three lines, e.g. `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers`.

Only after preflight is approved does the browser send the actual request:

~~~http
POST /api/demo/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Content-Type: application/json
X-Request-Id: req-42

{"name":"Spring CORS"}
~~~

The actual response still needs a matching `Access-Control-Allow-Origin`:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: X-Request-Id
X-Request-Id: create-1

{"id":2,"name":"Spring CORS"}
~~~

**A successful preflight does not replace the CORS check on the actual response.** If the actual response lacks or mismatches allow-origin, the browser still blocks JavaScript from reading it, even though the POST already ran.

### 5.1. The browser does not always send OPTIONS before every request

The browser can cache a preflight result keyed by origin/URL/method/headers and Fetch rules. `Access-Control-Max-Age` lets the server suggest a cache duration; the browser may impose its own cap or clear the cache when conditions change. This is normally a dedicated cache for **preflight results**, not the HTTP payload cache for GET/POST.

Therefore, DevTools not showing OPTIONS on the second call **does not prove the API automatically became simple**. Try "Disable cache"/cache-clearing, different network conditions, and specific origins/headers, keeping in mind that DevTools and user agents may manage the preflight cache differently from regular HTTP caches.

### 5.2. When preflight is rejected

The server may omit the corresponding allow headers, or Spring MVC/Spring Security may return an error such as **403 Invalid CORS request**. In that case, the browser **does not send the actual POST/PUT**. In JavaScript, the application typically receives a network/CORS rejection rather than a 403 body to parse with `response.json()`.

Do not write a custom `@RequestMapping(method=OPTIONS)` controller just to echo every header in production. Spring MVC has a centralized CORS processor and policy; unconditionally echoing `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` opens unintended cross-origin access.

## 6. Table of all CORS headers to remember

### 6.1. Request headers

| Header | Who sends it? | When does it appear? |
| --- | --- | --- |
| `Origin` | Browser / user-agent | Cross-origin requests and preflight; may also appear on some same-origin requests |
| `Access-Control-Request-Method` | Browser | OPTIONS preflight; specifies the actual method the client intends to use |
| `Access-Control-Request-Headers` | Browser | Preflight when requesting permission for headers; a **list of header names**, not Authorization/token values |

Do not make the frontend manually set `Access-Control-Request-Method` or `Origin` to "bypass CORS"; the browser manages those headers. The client calls `fetch` with the real method and headers, and the browser decides whether to preflight.

### 6.2. Response headers

| Header | Where it applies | Meaning |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Preflight and actual response | Allows a specific origin or `*` when credentials are not used |
| `Access-Control-Allow-Methods` | Preflight | Allows the requested HTTP methods |
| `Access-Control-Allow-Headers` | Preflight | Allows the request headers listed by the browser |
| `Access-Control-Allow-Credentials` | Preflight and actual for credentialed requests | Valid value `true` permits credentials under CORS conditions |
| `Access-Control-Max-Age` | Preflight | Seconds to cache preflight result (subject to browser limits) |
| `Access-Control-Expose-Headers` | Actual response | Lets JavaScript read extra response headers beyond the default exposed set |
| `Vary` | Responses whose content depends on Origin/preflight headers | Instructs caches to distinguish response variants |

**Do not confuse `Access-Control-Allow-Headers` with `Access-Control-Expose-Headers`.** Allow-Headers concerns headers the **client is allowed to send** (such as Authorization, X-Request-Id). Expose-Headers concerns headers **returned by the server** that script is allowed to read via `Response.headers.get(...)` (such as X-Request-Id).

JavaScript example:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/demo/items",
  { headers: { Accept: "application/json" } }
);

console.log(response.headers.get("X-Request-Id"));
~~~

For JS to read `X-Request-Id`, the cross-origin response needs `Access-Control-Expose-Headers: X-Request-Id`. The header may still be visible in the Network tab when unexposed, yet JS cannot access it; configure expose on the server, rather than adding `Access-Control-Expose-Headers` to the request.

## 7. Wildcards, credentials, cookies, and critical limits

### 7.1. `Access-Control-Allow-Origin: *`

For **non-credentialed requests**, `Access-Control-Allow-Origin: *` can allow code from any origin to read the response. It is more suited for genuinely public data intentionally provided to any website.

For credentialed requests, **do not use `Access-Control-Allow-Origin: *`**. The browser requires allow-origin to match a specific origin; the server also needs `Access-Control-Allow-Credentials: true`. In Spring Framework, `allowCredentials(true)` is incompatible with `allowedOrigins("*")`. If you truly need a pattern matching multiple origins, Spring provides `allowedOriginPatterns`, but keep patterns tightly bounded; echoing origins via overly broad patterns can still expose access to untrusted websites.

### 7.2. `fetch` and credentials

When the frontend needs the browser to send cross-origin cookies:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include"
});
~~~

`credentials:"include"` is only the **client's intent**; cookies must still satisfy domain/path/`Secure`/`SameSite` and browser third-party cookie policies. The server must respond with a specific allow-origin and `Access-Control-Allow-Credentials: true` for script to read the response.

Even when CORS permits it, a cookie with `SameSite=Lax` or `Strict` may not be sent in a truly cross-site request. With `SameSite=None`, modern browsers require `Secure`; some browsers or user policies still block third-party cookies. **CORS does not force cookies past those restrictions**.

Example actual response for a credentialed request:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"user":"example"}
~~~

Do not enable credentials solely because an API uses bearer token authentication: an `Authorization` bearer header usually triggers preflight because it is not safelisted, but using an auth header and using cookies/`credentials:"include"` are two separate aspects. Choose the policy based on the actual authentication model.

### 7.3. Preflight and Spring Security

In standard browsers, OPTIONS preflight **does not carry session cookies**. If a security filter demands authentication on OPTIONS before the CORS policy is checked, the server may reject it with 401/403 and the browser never sends the actual request. In Spring Security, process CORS at the right position **before requiring authentication**. However, letting preflight pass does **not** mean opening actual POST/DELETE requests: the real method must still be authenticated, authorized, and CSRF-checked per configuration.

### 7.4. CORS is not authorization

- Browsers enforce CORS checks; server-to-server clients can call the API without obeying `Access-Control-Allow-Origin`.
- Do not use the `Origin` header in place of `Authentication`/`Authorization`. The Origin header is not an authenticated identity.
- CORS does not protect the server against all state-changing requests and does not replace CSRF.
- CORS does not determine a user's roles/permissions after login.
- Cross-origin does not mean cross-site; cookie rules and origin rules are different.
- A CORS error in the browser does not prove the backend endpoint returned 404/500; the server may have succeeded while script was denied reading the response.

## 8. Configuring CORS in Spring MVC

There are two main approaches: controller annotations (`@CrossOrigin`) or global URL pattern configuration via `WebMvcConfigurer`. Both use Spring MVC's internal `CorsConfiguration` / CORS processor.

### 8.1. `@CrossOrigin`

Fragment example:

~~~java
@RestController
@RequestMapping("/api/public")
@CrossOrigin(origins = "https://app.example.test", maxAge = 600)
class PublicApiController {

    @GetMapping("/status")
    public String status() {
        return "ok";
    }
}
~~~

This snippet requires the corresponding Spring imports and must reside inside a Spring MVC project. `@CrossOrigin` can be placed at method or class level. With default configuration where origins are not specified, Spring MVC may allow all origins, so **do not put a bare `@CrossOrigin` on sensitive controllers without evaluating the security model**.

When both class-level and method-level configurations exist, Spring MVC can combine them. Do not assume a method-level annotation will always "narrow" all class-level origins in a deny-by-default way; verify empirically with MockMvc when multiple config layers exist.

### 8.2. `WebMvcConfigurer` and explicit allowlists

For multiple endpoints, a centralized policy is easier to govern:

~~~java
package com.example.corsdemo.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/demo/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST", "PUT")
                .allowedHeaders("Content-Type", "X-Request-Id", "Authorization")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

In the example policy:
- Only `https://app.example.test` is allowed.
- CORS is enabled only for GET, POST, and PUT on `/api/demo/**` paths; not every URL on the server is granted CORS.
- `Content-Type`, `X-Request-Id`, and `Authorization` are the **headers that may be requested via preflight**. **They do not create authentication by themselves**; controller/security must validate Authorization if used.
- `X-Request-Id` is exposed so JavaScript can read it in the actual response.
- `allowCredentials(false)` indicates the demo does not support credentialed CORS.
- `maxAge(600)` suggests caching preflight results for 600 seconds; browsers have their own limits.

**Do not equate allowedMethods with actual controller methods:** configuring CORS to allow a method does not cause Spring to create a nonexistent endpoint. For instance, allowing `PUT` without a `@PutMapping` handler can still result in 405 when the actual request is handled.

Spring MVC global config typically applies defaults for origins/headers/methods when unset, and a common default `maxAge` is 1800 seconds. However, a plain `new CorsConfiguration()` object does not allow all origins by default; defaults depend on configuration context. For APIs with explicit requirements, **state all important bounds explicitly** as in the snippet above.

### 8.3. Overlapping global and local config

If a method has `@CrossOrigin` while the application also declares `WebMvcConfigurer.addCorsMappings`, Spring MVC can combine the local and global `CorsConfiguration`. For collection attributes such as allowed origins, the merged config may be broader than intended. When a strict allowlist is the goal, prefer a single clear policy source or write MockMvc tests proving unwanted origins/methods/headers are properly rejected.

With Spring Security, the CORS filter and MVC configuration must coordinate. **Do not manually add a duplicate `CorsFilter`** without understanding filter chain ordering and merging/overriding; two header emitters can produce unpredictable responses.

## 9. Complete application: Java 17 + Spring Boot 3.3.5

A small Spring MVC project, **without Spring Security enabled**, to observe CORS independently of login/CSRF. Section 12 then shows how to integrate Spring Security.

~~~text
cors-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/corsdemo/
    │   ├── CorsDemoApplication.java
    │   └── web/
    │       ├── CorsConfig.java
    │       └── ItemController.java
    └── test/java/com/example/corsdemo/web/
        └── ItemCorsTest.java
~~~

### 9.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'cors-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

`spring-boot-starter-web` provides Spring MVC and the JSON converter needed for the example. There is no Spring Security dependency, so **do not infer that the demo secures a real API**. In production, add auth, authorization, and CSRF/rate limiting according to your use case.

### 9.2. Main application

`src/main/java/com/example/corsdemo/CorsDemoApplication.java`:

~~~java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

The `CorsConfig.java` configuration is the full file from section 8.2, saved at `src/main/java/com/example/corsdemo/web/CorsConfig.java`.

### 9.3. REST controller: GET, POST, PUT

`src/main/java/com/example/corsdemo/web/ItemController.java`:

~~~java
package com.example.corsdemo.web;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo/items")
public class ItemController {

    public record Item(long id, String name) {}
    public record ItemInput(String name) {}

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<List<Item>> list() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "list-1")
                .body(List.of(new Item(1L, "Spring MVC")));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> create(@RequestBody ItemInput input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Request-Id", "create-1")
                .body(new Item(2L, input.name()));
    }

    @PutMapping(
            path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> update(
            @PathVariable("id") long id,
            @RequestBody ItemInput input) {
        return ResponseEntity.ok(new Item(id, input.name()));
    }
}
~~~

Explanation:
- GET returns a JSON list and the `X-Request-Id` header. The CORS config exposes this header to JS.
- POST accepts JSON and creates a fixed representation with ID 2; **it does not persist to a database**, so this is not a full data-management API.
- PUT demonstrates a method requiring preflight when called cross-origin from a browser.
- The controller does not read the `Origin` header directly and does not set `Access-Control-Allow-Origin` manually. Spring MVC's CORS mapping owns the policy.
- `@PostMapping(consumes=application/json)` controls the request body/media type; it is **separate from** CORS checking request headers. CORS success does not guarantee valid JSON or business action success.

## 10. Making test HTTP calls and analyzing responses

Run in the project with Gradle wrapper and Java 17:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell/CMD use `.\gradlew.bat bootRun`. Local HTTP runs on `http://localhost:8080`, while the configured allow-origin is `https://app.example.test`: this is **still valid** for testing server CORS responses with curl because `Origin` is the source value described by the browser/curl—you do not need a running frontend page to use curl.

### 10.1. Simulating a simple GET

~~~bash
curl -i 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://app.example.test' \
  -H 'Accept: application/json'
~~~

Expected HTTP **200**, body:

~~~json
[{"id":1,"name":"Spring MVC"}]
~~~

Observe the response headers:
- `Access-Control-Allow-Origin: https://app.example.test`.
- `Access-Control-Expose-Headers: X-Request-Id`.
- `X-Request-Id: list-1`.
- Usually includes `Vary: Origin` and preflight-related Vary values added by Spring.

**No OPTIONS is seen** because curl does not automatically preflight like a browser. Calling the same GET from a browser under CORS-safelisted conditions makes the browser send GET directly.

### 10.2. Simulating OPTIONS preflight for JSON POST

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-request-id'
~~~

With the `CorsConfig` policy, expect 2xx status (usually HTTP 200), and:
- `Access-Control-Allow-Origin` is the allowed origin.
- `Access-Control-Allow-Methods` includes POST.
- `Access-Control-Allow-Headers` includes Content-Type and X-Request-Id.
- `Access-Control-Max-Age` is 600 seconds.
- Response includes appropriate `Vary`.

The preflight body is normally empty. **The `create()` controller is not running here**; OPTIONS is handled by the CORS processor. Do not expect ID 2 or an item JSON in the OPTIONS response.

### 10.3. Simulating actual POST after preflight

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://app.example.test' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req-42' \
  -d '{"name":"Spring CORS"}'
~~~

Expected HTTP **201 Created**, body:

~~~json
{"id":2,"name":"Spring CORS"}
~~~

The response includes `Access-Control-Allow-Origin`; the `X-Request-Id` header produced by the controller has value `create-1` and is exposed in the CORS config. CORS does not force the server to echo the `req-42` value from the request.

**curl sends only a single POST**, without automatically sending OPTIONS beforehand. To observe the two requests a browser actually sends, you need a cross-origin frontend page or DevTools Network. Hence curl's result tests **server-side CORS policy**, and does not prove the browser won't hit cookie, CSP, mixed content, or preflight caching issues.

### 10.4. Unpermitted origin

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

In Spring MVC with this CORS mapping, preflight with an invalid origin is usually rejected with **403 Invalid CORS request**. The browser does not send the actual POST if preflight fails. For an actual cross-origin GET request, Spring may reject with 403, whereas other systems may return a response without allow-origin and let the browser block reading.

**Do not build frontend logic expecting to parse the 403 body of a CORS rejection**, because the browser normally hides the response from script. Inspect status and logs via DevTools/server diagnostics.

### 10.5. Without Origin

~~~bash
curl -i 'http://localhost:8080/api/demo/items'
~~~

Expect HTTP 200 and JSON as usual. Without a request origin, the CORS policy normally does not add `Access-Control-Allow-Origin`. This is not a CORS vulnerability; CORS is not designed to stop non-browser HTTP clients from sending requests. Authentication/authorization must work independently.

## 11. MockMvc: testing both simple and preflight requests

`src/test/java/com/example/corsdemo/web/ItemCorsTest.java`:

~~~java
package com.example.corsdemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalToIgnoringCase;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemCorsTest {

    private static final String ORIGIN = "https://app.example.test";

    @Autowired
    MockMvc mvc;

    @Test
    void simpleGetHasCorsOriginAndExposesResponseHeader() throws Exception {
        mvc.perform(get("/api/demo/items")
                        .header("Origin", ORIGIN)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", ORIGIN))
                .andExpect(header().string(
                        "Access-Control-Expose-Headers", "X-Request-Id"))
                .andExpect(header().string("X-Request-Id", "list-1"))
                .andExpect(jsonPath("$[0].name").value("Spring MVC"));
    }

    @Test
    void preflightOptionsAllowsConfiguredPostAndHeaders() throws Exception {
        mvc.perform(options("/api/demo/items")
                        .header("Origin", ORIGIN)
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers",
                                "content-type,x-request-id"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", ORIGIN))
                .andExpect(header().string("Access-Control-Allow-Methods",
                        containsString("POST")))
                .andExpect(header().string("Access-Control-Max-Age", "600"));
    }

    @Test
    void actualJsonPostStillRequiresRealHandler() throws Exception {
        mvc.perform(post("/api/demo/items")
                        .header("Origin", ORIGIN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Spring CORS\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Access-Control-Allow-Origin", ORIGIN))
                .andExpect(jsonPath("$.id").value(2))
                .andExpect(jsonPath("$.name").value("Spring CORS"));
    }

    @Test
    void rejectedOriginCannotPreflight() throws Exception {
        mvc.perform(options("/api/demo/items")
                        .header("Origin", "https://evil.example.test")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers", "content-type"))
                .andExpect(status().isForbidden());
    }

    @Test
    void getWithoutOriginDoesNotNeedCorsResponseHeader() throws Exception {
        mvc.perform(get("/api/demo/items"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }
}
~~~

In the test file, importing the `equalToIgnoringCase` matcher is unnecessary since it is unused; if your IDE/Checkstyle checks unused imports, remove that line. The remaining assertions sufficiently demonstrate preflight and actual responses. Run:

~~~bash
./gradlew test
~~~

MockMvc does not launch a real browser and **does not automatically send preflight** when a test calls `post(...)`. Constructing `options(...)` in the test simulates a preflight request and verifies Spring's policy. With a real browser, you also need to check the network stack, caches, cookie policy, current origin, reverse proxy, and security filters. `MockMvc` verifies server decisions, but does not replace cross-origin E2E tests.

### 11.1. Testing whether permitted headers are actually returned

The test above only checks allow-origin, method, and max-age to avoid depending on allow-headers formatting/casing. Add a **case-insensitive** assertion or split the header list to confirm `Content-Type` and `X-Request-Id` appear in `Access-Control-Allow-Headers` if that is a contract you need to protect. HTTP header names are case-insensitive; do not write tests that fail merely because the server returns `content-type` instead of `Content-Type`.

For production applications, test **at least**:
- Allowed origin and rejected origin.
- Allowed method and rejected method.
- Allowed headers and headers outside the allowlist.
- Credentials on/off, verifying wildcard rejection works properly.
- Actual response having allow-origin and expose-headers when required.
- CORS running through the Spring Security filter chain before authentication/CSRF.
- Requests without Origin not getting accidentally blocked by the CORS policy.

## 12. When integrating Spring Security

For Spring MVC with Spring Security, CORS must be integrated so preflight is not unreasonably challenged for authentication **before** Spring evaluates the CORS policy. Spring Security provides `HttpSecurity.cors(...)` and can use the MVC-provided CORS configuration when proper `HandlerMappingIntrospector`/integration is present and no competing CORS configuration source exists.

Example **fragment** to add to a project that already has `spring-boot-starter-security`, the controller, and `CorsConfig` from section 8:

~~~java
package com.example.corsdemo.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/demo/**").authenticated()
                        .anyRequest().denyAll())
                .build();
    }
}
~~~

This snippet is a standalone file once the Spring Security starter is added, but **does not belong to the no-security runnable app in section 9**. Using `authenticated()` here merely illustrates a realistic policy: POST requests remain subject to default CSRF if cookie/session authentication is used; without valid credentials, the actual request will be rejected. Do not expect all MockMvc tests from section 11 to still pass after adding this class without configuring test users/CSRF tokens. For example, a JWT resource server has a different CSRF/session policy and must be designed separately.

**Do not configure security with "permitAll OPTIONS" as the sole solution** while forgetting CORS: OPTIONS must be checked by the CORS processor for origin/method/headers; permitting all OPTIONS at the security layer does not automatically give the browser a valid `Access-Control-Allow-Origin`. Conversely, an approved CORS preflight does not make the user authorized for the actual request.

If the application uses multiple `SecurityFilterChain` beans, having `cors()` on one chain does not guarantee other chains handle their routes properly; test the real paths through the entire filter chain.

## 13. Common CORS errors, classified by layer

| Symptom | Common cause | How to check / fix |
| --- | --- | --- |
| Console reports missing `Access-Control-Allow-Origin` | Route/proxy/error response did not add CORS header | Check Network + actual HTTP response and policy mapping |
| GET works with curl, blocked in fetch | Browser enforces CORS, curl does not | Send `Origin` with curl and inspect allow-origin |
| OPTIONS 401/403 before POST | Security or CORS policy blocked preflight | Check filter ordering, `cors()`, origin, method, headers |
| Form POST works but JSON POST hits CORS | JSON Content-Type triggers preflight | Configure POST and Content-Type in allowlist |
| GET with Authorization triggers preflight | Authorization is not safelisted | Explicitly allow Authorization header; still authenticate actual |
| OPTIONS 200 but POST/PUT never arrives | Preflight response missing/mismatched allow-origin/method/headers | Compare `Access-Control-Request-*` with `Access-Control-Allow-*` |
| OPTIONS passes yet actual response is blocked | Actual response lacks valid CORS headers | Check actual response/error handler/reverse proxy |
| Cookie not sent with `credentials:include` | SameSite, Secure, domain/path, third-party cookie policy | Inspect cookie attributes and browser policy |
| Cookie sent yet JavaScript still cannot read body | Missing `Access-Control-Allow-Credentials:true` or allow-origin is `*` | Use specific origin + credentials true |
| JS cannot read `X-Request-Id` | Response header not exposed | `Access-Control-Expose-Headers` |
| `@CrossOrigin` on controller does not apply | Path mismatch, different handler, Spring Security ahead of MVC | Check handler mapping/filter chain |
| CORS accidentally opens all origins | Overly broad `@CrossOrigin` or global/local config merge | Use explicit allowlist and negative tests |
| OPTIONS response redirected | Reverse proxy/auth redirect or URL normalization | Preflight should return policy directly; check gateway |
| DevTools does not show OPTIONS a second time | Preflight caching | Check `Access-Control-Max-Age` and browser cache behavior |
| Missing `Vary` header when reflecting origin dynamically | Cache serves wrong variant response | Configure Vary properly via CORS processor/proxy |
| HTTP 500 reported as CORS error | Error path does not add allow-origin | Check server logs/status, handle CORS on error responses per policy |
| Browser reports mixed content | HTTPS frontend calling HTTP backend | Use HTTPS; this is not merely CORS |
| Browser reports CSP `connect-src` | Frontend CSP blocks destination | Adjust Content Security Policy, not backend CORS |

### 13.1. Step-by-step debugging workflow

1. Identify the **actual origin** of the frontend page, including scheme/host/port. Do not confuse the API's origin with the frontend's origin.
2. In DevTools Network, locate the OPTIONS request (if any) and the actual request. Note the exact method, URL, `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
3. For preflight, compare status and `Access-Control-Allow-Origin/Methods/Headers/Max-Age`. If OPTIONS fails, do not focus on fixing the POST controller before checking the policy.
4. For the actual response, compare allow-origin, allow-credentials, and expose-headers; inspect cookie flags and `fetch(credentials)`.
5. Inspect `@CrossOrigin` / `CorsRegistry` mappings to see if overlapping configs exist.
6. If Spring Security is present, ensure CORS runs before credential-requiring auth steps; also verify actual permissions/CSRF independently.
7. Check whether ingress/API gateway/CDN handles OPTIONS itself, overwrites/strips headers, caches with wrong `Vary`, or issues HTTPS redirects.
8. Use curl with equivalent headers to confirm server behavior, then return to the browser to check SameSite, mixed content, CSP, and preflight cache.
9. Add MockMvc tests for allow + deny so regressions do not silently open unintended origins or headers.
10. Log route, origin/method/header names, and error status in a controlled manner; never log Authorization tokens/cookies/session IDs.

## 14. Self-check questions

**1.** Do two URLs with the same hostname but different ports have the same origin?

**Answer:** No, unless the ports resolve to the same effective port; port is part of the origin.

**2.** Why does a cross-origin JSON POST usually send OPTIONS while a urlencoded form POST usually does not?

**Answer:** `application/json` is not a CORS-safelisted Content-Type. `application/x-www-form-urlencoded` can be safelisted if the other method/header conditions are met.

**3.** Does a simple GET without OPTIONS still need `Access-Control-Allow-Origin`?

**Answer:** Yes, so the browser lets JavaScript read the cross-origin response. "No preflight" does not mean "skipping CORS checks."

**4.** Which header in OPTIONS states that the browser wants the real method to be PUT?

**Answer:** `Access-Control-Request-Method: PUT`; the HTTP method of the permission-checking request itself remains `OPTIONS`.

**5.** Distinguish Allow-Headers and Expose-Headers?

**Answer:** `Access-Control-Allow-Headers` specifies which **request** headers the client may send; `Access-Control-Expose-Headers` specifies which **response** headers script may read.

**6.** Can `Access-Control-Allow-Origin:*` be used with cookie-authenticated credentialed CORS?

**Answer:** No. With credentialed CORS, the response needs a matching specific origin and `Access-Control-Allow-Credentials:true`; cookies remain subject to SameSite/Secure/browser policies.

**7.** Why does `curl -H 'Origin: ...'` succeeding not guarantee the frontend will work?

**Answer:** curl does not implement full browser CORS enforcement, preflight caching, cookie policies, mixed content, or CSP. It only lets you observe the server's response.

**8.** If browser preflight carries no cookie and Spring Security returns 401, where should it be handled?

**Answer:** Integrate the CORS processor before authentication is required, typically via `http.cors(...)` and matching MVC CORS configuration; the actual request must still pass security/CSRF rules.

**9.** Does CORS protect against CSRF when the browser has already sent a simple POST?

**Answer:** No. A simple request can be sent and cause side effects before the browser decides whether to allow reading the response. Appropriate CSRF/authorization controls must be used.

## 15. Production CORS configuration checklist

1. Define explicit allowed origins with exact scheme/host/port; avoid wildcards for sensitive data.
2. Restrict allowed methods to the actual API and allowed request headers to actual needs.
3. Enable credentials only when there is a use case; never combine wildcard origin with credentials.
4. Define the minimal necessary exposed response headers, avoiding exposing sensitive information.
5. Set a reasonable maxAge, understanding browsers impose caps.
6. Ensure `Vary` is accurate when responses depend on Origin/request method/request headers.
7. Place CORS properly in the filter chain when Spring Security is present; actual requests still need auth, authorization, and CSRF.
8. Configure reverse proxies/CDNs/gateways not to strip CORS headers or cache responses across different origins.
9. Test both browser and MockMvc: simple GET, JSON POST preflight, PUT preflight, allowed/denied origins, allowed/denied headers, credentialed flows.
10. Do not use CORS as a substitute for authentication, tenant validation, network ACLs, CSRF, or rate limiting.
11. Verify HTTPS URLs, frontend CSP `connect-src`, and cookie SameSite/Secure/third-party policies.
12. On production errors, inspect OPTIONS and actual requests before changing controller logic.

## 16. Official references

- [Spring Framework — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `@CrossOrigin`, global `WebMvcConfigurer`, credentialed requests, policy defaults, and combining local/global configs.
- [Spring Framework — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowed origins/origin patterns, methods, headers, credentials, maxAge, and wildcard validation.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling preflight before authentication and `http.cors` integration.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): simple/safelisted requests, preflight, and explanation of request/response headers.
- [MDN — Preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request): OPTIONS, access-control-request headers, and preflight cache.
- [Fetch Standard — CORS Protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): normative definition of preflight, safelisted request headers, credentials, and CORS checks.
- [MDN — Set-Cookie, SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): cookie mechanisms separate from CORS.
- [Spring Framework — CORS support in HandlerMapping](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS preflight handling and configuration points in MVC mapping.

**Key takeaway:** *simple* requests **have no preflight yet still must be permitted for the browser to read the response**; JSON/custom-header/non-safelisted-method requests typically go through an **OPTIONS preflight** to ask permission before the actual request. Spring MVC emits headers according to `CorsConfiguration`; Spring Security must be integrated in the right order. CORS governs cross-origin script reading under browser policy, and **does not replace authentication, authorization, or CSRF**.
