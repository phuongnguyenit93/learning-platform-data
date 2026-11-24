# Spring MVC — Same-origin policy, origins, and conditions that trigger CORS

## 1. Goals and core questions

Suppose a frontend application runs at `http://localhost:5500` and a Spring MVC backend runs at `http://localhost:8080`. When the browser executes:

~~~javascript
const response = await fetch("http://localhost:8080/api/info");
const data = await response.json();
console.log(data);
~~~

the two URLs have the **same host `localhost` but different ports**, so they have **different origins**. The browser enforces the same-origin policy (SOP). For frontend JavaScript to read the result from the backend, the server needs to return an appropriate CORS response. Conversely, if the HTML/frontend is also served from `http://localhost:8080`, the call to `/api/info` is same-origin and does not require separate CORS permission.

After this lesson, you can:

- Precisely define **origin = scheme + hostname + effective port** and distinguish same-origin, cross-origin, same-site, and cross-site.
- Explain that SOP protects **reading/interactivity** with resources from another origin, rather than acting as a firewall blocking every network request or every resource embedding.
- Identify **when the browser uses the CORS mechanism**, when a cross-origin request needs a **preflight OPTIONS**, and when preflight is not needed yet the response must still be permitted for the browser to read.
- Understand `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Expose-Headers`, `Access-Control-Max-Age`, and `Vary: Origin`.
- Distinguish CORS from authentication, authorization, CSRF, SameSite cookies, CSP, and server-to-server HTTP requests.
- Configure Spring MVC using `WebMvcConfigurer#addCorsMappings` or `@CrossOrigin`, and integrate Spring Security with the proper filter order.
- Run a Java 17 / Spring Boot 3.5.0 application and test CORS with MockMvc, browser DevTools, and curl.

**Scope:** modern web browsers, Spring Framework 6.2 / Spring MVC (Servlet stack). CORS is a policy **enforced by the browser** according to the Fetch Standard; the server itself may still receive an HTTP request even when script is denied permission to read the response.

## 2. What actually is an origin?

In the context of HTTP(S), an origin is commonly represented by a tuple of three components:

~~~text
origin = (scheme, host, port)
~~~

For example:

~~~text
https://app.example.com:443
  │           │            │
scheme       host         effective port
~~~

If no port is written, the browser uses the scheme's default port: HTTP is typically 80, HTTPS is 443. Therefore `https://app.example.com` and `https://app.example.com:443` share the same origin.

**Path, query, and fragment are not part of the origin.** These two URLs have the same origin:

~~~text
https://shop.example.com/products?page=1
https://shop.example.com/account#settings
~~~

However, differing in just one of the three components—scheme, host, or port—is enough to make it cross-origin.

### 2.1. Origin comparison table

Suppose the source page origin is `https://shop.example.com`.

| Target URL | Same-origin? | Reason |
| --- | --- | --- |
| `https://shop.example.com/products` | Yes | Same scheme, host, port; path does not matter |
| `https://shop.example.com:443/api` | Yes | 443 is the default HTTPS port |
| `https://shop.example.com?q=java` | Yes | Query does not change the origin |
| `http://shop.example.com/api` | No | Different scheme: HTTP instead of HTTPS |
| `https://api.example.com/data` | No | Different hostname/subdomain |
| `https://shop.example.com:8443/api` | No | Different port |
| `https://example.com/api` | No | Root host differs from `shop.example.com` |
| `https://shop.example.com.evil.test/api` | No | This is a completely different host |

In a development environment:

| Source page | Target API | Conclusion |
| --- | --- | --- |
| `http://localhost:3000` | `http://localhost:8080` | Cross-origin: different port |
| `http://localhost:8080` | `http://localhost:8080/api` | Same-origin |
| `http://localhost:8080` | `http://127.0.0.1:8080` | Cross-origin: different hostname |
| `https://localhost:8080` | `http://localhost:8080` | Cross-origin: different scheme |

Note that DNS hostnames pointing to the same IP do **not** automatically make them same-origin. SOP relies on the URL's origin, not on the target IP after DNS resolution.

### 2.2. Same-origin is different from same-site

These two terms are often confused:

- **Origin** typically considers `scheme + host + port`.
- Modern **Site** is typically **scheme + registrable domain** (schemeful same-site); port is not a criterion for distinguishing sites. Registrable domain is based on public suffix rules; `localhost` has browser-specific handling.

For example, `https://app.example.com` and `https://api.example.com` are **cross-origin** (different hosts) but usually **same-site** (same scheme and registrable domain `example.com`). `http://localhost:5500` and `http://localhost:8080` are also cross-origin due to different ports, yet are typically considered same-site in local environments.

**Consequence:** configuring `SameSite` cookies does not automatically solve CORS. SameSite cookies control cookie sending based on site relationships; SOP/CORS controls response reading permissions between origins. A request can be **cross-origin yet same-site**.

### 2.3. Opaque origin, file, and Origin: null

Not every document has an explicit HTTP(S) origin. Some sandboxed, `data:`, or `file:` documents can have an **opaque origin**. When serialized in an `Origin` request header, the browser may send:

~~~http
Origin: null
~~~

Do not treat `null` as a trusted domain, and do not whitelist it just for local testing. Various untrusted documents can also serialize their origin as `null`.

**Best practice:** serve your frontend during development through an HTTP server such as `http://localhost:5500` instead of opening HTML files directly via `file:///...`; that makes origins and requests much easier to test.

`document.domain` was previously used to relax interaction between subdomains, but that mechanism has been deprecated/discouraged; do not use it as a workaround for CORS errors in modern applications.

## 3. What does the same-origin policy restrict?

SOP is a mechanism that isolates content from different sources. For instance, when a user logs into webmail `https://mail.example.com`, an arbitrary website `https://attacker.test` is not allowed to read emails, tokens, or private API contents from the webmail simply by running JavaScript `fetch()`.

### 3.1. Reading, sending, and embedding are three different behaviors

| Action | Default under SOP/browser | Example |
| --- | --- | --- |
| Script from origin A reads JSON/HTML response of origin B via `fetch`/XHR | Restricted, unless server B grants appropriate CORS permission | `fetch("https://api.example.com/private")` |
| Navigating the browser to another site | Usually allowed | Clicking a link, `window.location` |
| HTML form submitting cross-origin POST | Often allowed to be sent | `<form action="https://other.test/pay" method="post">` |
| Embedding cross-origin image/audio/video | Usually allowed to display per resource type/other policies | `<img src="https://cdn.test/p.png">` |
| Embedding traditional script from another origin | Usually allowed to load/execute per script type and CSP | `<script src="https://cdn.test/lib.js">` |
| Cross-origin module script or JS reading canvas pixels from cross-origin image | May require CORS or be tainted | `<script type="module">`, `canvas.toDataURL()` |
| Accessing the DOM of a cross-origin iframe | Strictly restricted | Parent script reading DOM from a different-origin `iframe` |
| Accessing `localStorage`/IndexedDB of origin B from origin A | Isolated per origin | `localStorage.getItem(...)` on another site |

Therefore, the statement "SOP blocks every cross-origin request" is **false**. Some requests **are sent**, yet JavaScript **cannot read the response** if CORS does not permit it.

A cross-origin `<img>` can be displayed, but when that image is drawn onto a canvas, the browser may mark the canvas as "tainted" and block reading pixels unless the resource satisfies the CORS policy.

### 3.2. Why does CSRF still exist?

Because cross-origin form submissions or certain requests can still be sent, a malicious website can attempt to cause state changes on another site if the browser sends the corresponding login cookies. **CORS does not inherently prevent CSRF** and is not the sole place to block state-changing requests.

The backend still needs measures such as:

- Appropriate CSRF tokens for cookie/session-based authentication.
- Proper `SameSite`, `Secure`, and `HttpOnly` cookie attributes.
- Checking `Origin`/`Referer` when necessary, according to a defined policy.
- Authentication, authorization, idempotency, and business logic validation.
- Never performing state-changing operations via GET alone.

CORS is a **rule for sharing response access permissions with the browser**, not the server's authorization system.

## 4. When does a request become a CORS request?

In this lesson, we focus on a JavaScript `fetch()` from document origin A to URL B:

1. If A and B are **same-origin**, CORS is not needed for script to read the response.
2. If A and B are **cross-origin**, the browser performs checks per Fetch/CORS; server B must opt in with appropriate HTTP response headers for JS to read the response.
3. Depending on the HTTP method, headers, and Content-Type, the browser may send a **preflight OPTIONS** before the main request.
4. The request may be sent successfully yet **the response is still blocked by the browser** if the headers are invalid.

Example frontend at `http://localhost:5500`:

~~~javascript
// Cross-origin because the backend runs on port 8080.
const result = await fetch("http://localhost:8080/api/info");
console.log(await result.json());
~~~

The request typically carries the header:

~~~http
GET /api/info HTTP/1.1
Origin: http://localhost:5500
Accept: */*
~~~

The server can return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: http://localhost:5500
Vary: Origin

{"service":"cors-demo","status":"ok"}
~~~

If the policy is valid, the browser lets JS access the JSON. Without a compatible `Access-Control-Allow-Origin`, the browser blocks JavaScript from reading the result even though the Network tab may record HTTP 200.

**The Origin header is generated by the user agent in a CORS flow.** A server-to-server request or `curl` can send or omit the Origin header and still receive the HTTP response because there is no browser enforcement. Therefore, never treat `Origin` as proof of the caller's identity.

### 4.1. CORS does not necessarily create a new HTTP request

Two independent concepts:

- **CORS actual request:** the main request such as GET/POST/PUT/... to the API.
- **CORS preflight request:** OPTIONS sent **before the actual request** to ask the server whether the intended method/headers are permitted.

A regular cross-origin GET **has no preflight**, yet the actual response must still include a matching ACAO. A cross-origin JSON POST usually requires preflight before sending the JSON body.

## 5. Conditions that trigger preflight OPTIONS

Preflight does not occur merely because "frontend and backend are on different ports." It depends on the combination of method, request headers, and certain other Fetch conditions. A common way to learn this is by comparing against the **CORS-safelisted** set.

### 5.1. Requests that usually do not need preflight

A cross-origin request may skip preflight when all corresponding conditions are met, for example:

- The method is `GET`, `HEAD`, or `POST`.
- Script-set request headers belong only to the CORS-safelisted group (such as `Accept`, `Accept-Language`, `Content-Language`, and certain cases of `Content-Type`, `Range`), within valid value/header limits.
- If `Content-Type` is set by script, its essence media type is one of three types: `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`.
- There are no additional factors forcing preflight under Fetch (certain streaming/upload cases and browser platforms have additional policies).

Example:

~~~javascript
// Cross-origin GET usually has no preflight,
// but still needs Access-Control-Allow-Origin for JS to read the body.
fetch("http://localhost:8080/api/info");
~~~

A form-urlencoded POST can also avoid preflight:

~~~javascript
fetch("http://localhost:8080/api/form", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: "name=Lan"
});
~~~

**No preflight does not mean the backend has granted permission.** The browser still checks the actual CORS response, and the POST request may have already reached the server before the browser blocks JS from reading the response.

### 5.2. Requests that usually require preflight

| Script-initiated request | Typical preflight? | Reason |
| --- | --- | --- |
| GET without custom headers | No | Safelisted method/headers |
| POST `Content-Type: application/x-www-form-urlencoded` | No | Safelisted content type |
| POST `Content-Type: text/plain` | No | Safelisted content type |
| POST `Content-Type: application/json` | **Yes** | `application/json` is not a safelisted Content-Type |
| PUT/DELETE/PATCH | **Yes** | Method outside GET/HEAD/POST |
| GET with `Authorization: Bearer ...` | **Yes** | Authorization is not a safelisted header |
| GET with `X-Request-ID`, `X-Tenant-ID`, or `X-API-Key` | **Yes** | Custom request headers |
| POST with `Content-Type: application/json` and credentials | **Yes** | JSON content type alone is enough to require preflight |

A client adding a custom header just for "debugging" can accidentally trigger preflight for a request that previously did not need one. However, you should not remove necessary authentication headers just to avoid OPTIONS; configure CORS/authorization properly instead.

### 5.3. Actual preflight flow for JSON POST

Frontend:

~~~javascript
const res = await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Hello" })
});
console.log(await res.json());
~~~

The browser sends first:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://localhost:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

An allowing response can look like this:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type
Access-Control-Max-Age: 1800
Vary: Origin
~~~

After a successful preflight, the browser sends the main request:

~~~http
POST /api/echo HTTP/1.1
Origin: http://localhost:5500
Content-Type: application/json

{"message":"Hello"}
~~~

The actual response must include appropriate CORS headers:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Content-Type: application/json

{"echo":"Hello"}
~~~

From the MVC application's perspective, preflight is typically handled at the CORS layer once handler mapping/config is defined, **without needing to write an OPTIONS controller yourself** just to return ACAO. Preflight can be rejected when the origin, method, or headers are not configured.

**Note:** Specific status/headers (200/204, order, capitalization) may vary by implementation. What you need to verify is whether **the policy allows the origin/method/headers** and whether the browser proceeds with the actual request. The browser may cache preflight results within its own limits, so not every JSON POST is guaranteed to emit a new OPTIONS request.

### 5.4. CORS preflight and credentials

Under Fetch, a CORS preflight normally **does not carry the actual request's credentials** (such as cookies). Therefore, a system using session authentication that blocks every OPTIONS request lacking a cookie can cause preflight to fail.

That is why when integrating Spring Security, CORS processing usually must happen **before authentication/authorization filters**. That does not mean you should unconditionally open all OPTIONS requests across the entire internet; still apply an origin/method/header allowlist at the CORS layer.

## 6. CORS response headers explained

| Server response header | Effect |
| --- | --- |
| `Access-Control-Allow-Origin` | Allows **one specific origin** or `*` under permitted conditions |
| `Access-Control-Allow-Methods` | In a preflight response, lists the methods cross-origin script is allowed to use |
| `Access-Control-Allow-Headers` | In a preflight response, allows the headers script intends to send |
| `Access-Control-Allow-Credentials` | Allows the browser to expose the response to credentialed requests when valid |
| `Access-Control-Expose-Headers` | Lets JS read additional response headers beyond the safelisted set |
| `Access-Control-Max-Age` | Lets the browser cache the preflight result, subject to browser limits |
| `Vary: Origin` | Tells caches the response may vary based on the request Origin |

### 6.1. Access-Control-Allow-Origin is not a CSV list

This header can be:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

or for a public resource without credentials:

~~~http
Access-Control-Allow-Origin: *
~~~

**Do not** put multiple origins separated by commas in a single ACAO value hoping the browser will pick one:

~~~http
Access-Control-Allow-Origin: https://a.example, https://b.example
~~~

That is not a valid list format for ACAO. If a server allows multiple origins, it typically matches the request `Origin` against an allowlist and reflects **a single validated origin** that matches. When responses vary by origin, use `Vary: Origin` to prevent shared caches from serving the wrong response.

### 6.2. Credentials and wildcard

If the frontend uses cookies/cross-origin credentials:

~~~javascript
fetch("https://api.example.com/account", {
  credentials: "include"
});
~~~

and the backend wants script to read the response, it usually needs:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Do not** combine a credentialed CORS response with:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

The browser will not let script read a credentialed response in this case. In credentialed flows, using wildcards for allowed methods/headers/exposed headers also has limitations; the safest approach is to declare an explicit allowlist according to actual needs.

Remember that `credentials: "include"` does not guarantee a cookie is actually sent. The browser also applies cookie domain/path, `Secure`, `SameSite`, and **third-party cookie policies**. For cross-site cookies, configuring `SameSite=None; Secure` is usually a necessary (not sufficient) condition in an appropriate HTTPS context.

### 6.3. Expose-Headers does not expose every header automatically

The browser allows JS to read certain CORS-safelisted response headers; to read a custom header such as `X-Request-ID`, the server can return:

~~~http
Access-Control-Expose-Headers: X-Request-ID
X-Request-ID: 32fd0d93-2d40-43fe-bdd0-7e672f210501
~~~

Frontend:

~~~javascript
const res = await fetch("http://localhost:8080/api/info");
const id = res.headers.get("X-Request-ID");
console.log(id);
~~~

If CORS only permits reading the body without exposing the custom response header, JavaScript may get `null` from `headers.get` even though the Network tab shows that header.

### 6.4. Max-Age and cache

`Access-Control-Max-Age: 1800` is the duration in seconds the browser is allowed to cache the **preflight result**, subject to browser implementation caps. It is **not** the cache lifetime of the actual JSON response.

Do not use the preflight cache as a user authorization mechanism. When changing a CORS policy, you may need to wait for browser preflight caches to expire according to their limits. HTTP caches and browser CORS preflight caches are separate mechanisms.

## 7. Without CORS headers, does the server process the request?

A very common misconception:

> "Chrome shows a CORS error, so the server definitely did not receive the request."

Not necessarily true.

### 7.1. GET case without preflight

The browser can send the GET, the server returns 200, **yet the browser blocks JavaScript from reading it** because the response lacks a matching ACAO. The Network panel may show the GET and payload, while `fetch` in script throws an error like `TypeError: Failed to fetch` or logs a console CORS message.

### 7.2. JSON POST case with preflight

The browser sends OPTIONS first. If OPTIONS is not allowed, the browser **does not send the actual POST**. This is why the backend POST controller never sees the request.

### 7.3. CORS is not the same as HTTP status

| Scenario | Server reality | JS observation |
| --- | --- | --- |
| Cross-origin GET, HTTP 200, missing ACAO | Server processed GET successfully | JS cannot read the response |
| JSON POST, preflight gets 403 | Actual POST may not be sent | Fetch blocked by CORS |
| GET with valid ACAO, HTTP 404 JSON | Server reports resource not found | JS can read status 404/body because CORS allows it |
| GET with valid ACAO, HTTP 500 JSON | Genuine server error | JS can read status 500/body if CORS allows it |
| Same-origin GET HTTP 401 | CORS not needed | JS sees HTTP 401 per semantics |
| `curl` to server without ACAO | curl still reads response | curl does not enforce SOP |

In other words, **CORS approval only governs script's access to the response**; it does not replace HTTP status, network connectivity, TLS, DNS, authentication, or server-side authorization.

## 8. How does CORS differ from other security mechanisms?

### 8.1. CORS and CSRF

- **CORS:** does the browser allow JavaScript at origin A to read the response from origin B?
- **CSRF:** can a malicious page cause a user's browser to perform an authenticated action on another server?

A cross-site HTML form POST request can be sent **without the server granting CORS for script to read the result**. Therefore CSRF tokens / SameSite cookies / appropriate Origin checks are still required for cookie-authenticated state changes.

### 8.2. CORS and authentication/authorization

CORS does not prove who the caller is. `Origin` is not a login token, and non-browser tools can send any Origin value they want. The backend must authenticate JWT/session/API key separately and check permissions on every resource and tenant.

An origin allowed by CORS where the user is not logged in may receive HTTP 401; if the CORS response is valid, the frontend **can read the 401 response** to display a login prompt. That does not mean granting access to the resource.

### 8.3. CORS and CSP

**Content Security Policy (CSP)** — such as `connect-src` — is declared by the **source page** to restrict where the frontend is allowed to connect. CORS is primarily the **target server's** choice about which origins may read responses. A request can be blocked by CSP before the network call or blocked by CORS after the call. The two policies complement, not replace, each other.

### 8.4. CORS and SOP for cookies/storage/DOM

CORS does not make origin B's localStorage or IndexedDB automatically visible to origin A's script. Nor does it let page A arbitrarily read the DOM of a cross-origin iframe. Cookies have their own domain/path/site policies and fetch credentials mode; do not infer that "allowing CORS" means "sharing all storage."

### 8.5. Browser versus backend, Postman, and curl

Server-to-server HTTP clients, command-line `curl`, Postman, and many native mobile clients are not subject to browser JavaScript SOP enforcement. Even with strict CORS configured, an attacker can still call a public API endpoint directly if network and authentication allow it.

**CORS is neither a firewall nor server authorization.** Do not use allowedOrigins as "only valid apps can call the API" without authentication/authorization.

## 9. Where does Spring MVC handle CORS?

Spring MVC has CORS support in `HandlerMapping`. When a request is mapped to a handler:

- For **preflight**, MVC can handle OPTIONS directly according to the CORS configuration, without entering the controller business method.
- For an actual cross-origin request, MVC validates the origin/config and adds appropriate CORS headers if permitted.
- If there is no matching CORS configuration, preflight may be rejected; simple/actual requests will not receive CORS headers for the browser to read the response.

Spring supports two common ways to declare this:

1. **Locally** with `@CrossOrigin` on a controller class or method.
2. **Globally scoped to URL paths** via `WebMvcConfigurer#addCorsMappings`.

You can also use `CorsFilter` when CORS needs to be handled at the filter chain level or integrated with Spring Security. Choose **one primary policy** and inspect how it combines with local rules to avoid overly broad allowances or conflicting headers.

### 9.1. @CrossOrigin for a handler

Short example:

~~~java
@RestController
@RequestMapping("/api")
public class ExampleController {

    @CrossOrigin(origins = "https://app.example.com")
    @GetMapping("/catalog")
    public List<String> catalog() {
        return List.of("Java", "Spring");
    }
}
~~~

Imports from `org.springframework.web.bind.annotation` and `java.util.List`. When the goal is just a few endpoints, local annotations are easy to read. However, when an API has many endpoints sharing a policy, global configuration is clearer and avoids copy-paste.

**Do not** casually slap `@CrossOrigin(origins = "*")` onto every controller to "make the error disappear." Doing so can inadvertently let arbitrary websites read non-credentialed API data when other protective layers are not properly designed.

### 9.2. Global CORS with WebMvcConfigurer

~~~java
@Configuration
public class ApiCorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false)
                .maxAge(1800);
    }
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

This configuration restricts the **URL path**, origin, methods, headers, and preflight cache duration. Do not place `@EnableWebMvc` in a Spring Boot application if you only need to customize CORS, as it can override helpful MVC auto-configuration parts.

**Combination note:** Global CORS configuration and local `@CrossOrigin` have Spring's combination mechanism. Several list-type attributes can be merged, making the allowed scope **broader than expected**. Review the final configuration and write tests for both allowed and forbidden origins.

### 9.3. With Spring Security

CORS preflight normally does not carry the actual request's cookie/session credentials. If Spring Security requires authentication before CORS is processed, OPTIONS may be rejected.

In a Spring Security Servlet application:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .cors(Customizer.withDefaults())
            // Declare authentication, authorization, and CSRF appropriate to the application.
            .build();
}
~~~

This fragment is **not sufficient** as a production security configuration: you need the Spring Security dependency and protection/authorization policies. `http.cors(...)` lets Security integrate CORS configuration in the right order. Do not use `permitAll OPTIONS /**` as a blanket workaround instead of configuring CORS accurately, and do not unconditionally disable CSRF for cookie/session-based applications.

In systems with a gateway, decide whether **the gateway or the Spring backend is responsible for CORS headers**, avoiding both adding different ACAOs or producing inconsistent preflight responses.

## 10. Runnable project: Spring Boot 3.5 and frontend on a different port

The following demo creates a backend API at `http://localhost:8080`, allowing only the browser frontend from `http://localhost:5500` to read cross-origin responses. It includes a GET endpoint without preflight and a JSON POST endpoint with preflight. The frontend only uses JavaScript fetch, with no session/cookies in this demo.

### 10.1. Structure

~~~text
cors-origin-demo/
├── pom.xml
├── src/main/java/demo/CorsOriginApplication.java
├── src/test/java/demo/CorsOriginTest.java
└── web-client/index.html
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cors-origin-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-test</artifactId>
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

### 10.3. CorsOriginApplication.java

All of the code below resides in **a single file** `src/main/java/demo/CorsOriginApplication.java`. Only the `CorsOriginApplication` class is public; the remaining records/controller/config are package-private, so Java 17 allows placing them in the same file.

~~~java
package demo;

import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsOriginApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsOriginApplication.class, args);
    }
}

@Configuration
class CorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                // Exact local frontend origin: scheme + host + port.
                .allowedOrigins("http://localhost:5500")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false)
                .maxAge(1800);
    }
}

record InfoResponse(String service, String status) {
}

record EchoRequest(String message) {
}

record EchoResponse(String echo) {
}

@RestController
@RequestMapping("/api")
class ApiController {
    @GetMapping(path = "/info",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<InfoResponse> info() {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(new InfoResponse("cors-demo", "ok"));
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<EchoResponse> echo(
            @RequestBody EchoRequest request) {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(new EchoResponse("Echo: " + request.message()));
    }
}
~~~

**What the application demonstrates:**

- `GET /api/info` from origin `http://localhost:5500`: actual request does not require preflight if headers are safelisted.
- `POST /api/echo` with `Content-Type: application/json`: the browser needs a preflight OPTIONS request.
- The browser can only read the response when the CORS response headers are valid; `X-Request-ID` is exposed for frontend JS to read.
- `allowCredentials(false)`: the example does not support cross-origin cookie-authenticated requests. If cookies are used, the policy must be redesigned, not merely switched from false to true.
- Only origin `http://localhost:5500` is allowed in the demo; `http://localhost:5501` or `http://127.0.0.1:5500` is a different origin.

The program **does not enable Spring Security** and does not simulate login or access control. Do not take this CORS configuration as a production authentication policy.

### 10.4. Frontend web-client/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CORS from localhost:5500</title>
</head>
<body>
  <h1>Test cross-origin fetch</h1>
  <button id="get">GET /api/info</button>
  <button id="post">POST JSON /api/echo</button>
  <pre id="output"></pre>
  <script>
    const api = "http://localhost:8080";
    const output = document.querySelector("#output");

    async function callApi(path, options) {
      try {
        const response = await fetch(api + path, options);
        const requestId = response.headers.get("X-Request-ID");
        const payload = await response.json();
        output.textContent = JSON.stringify({
          status: response.status,
          requestId,
          payload
        }, null, 2);
      } catch (error) {
        // If it is a CORS error, the browser prevents JS from reading the response body.
        output.textContent = "Fetch failed. Check Network/Console: "
          + error.message;
      }
    }

    document.querySelector("#get").addEventListener("click", () => {
      callApi("/api/info");
    });

    document.querySelector("#post").addEventListener("click", () => {
      callApi("/api/echo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Hello" })
      });
    });
  </script>
</body>
</html>
~~~

### 10.5. Starting the backend and frontend

Terminal 1, in the `cors-origin-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Terminal 2, also in the project directory, using Python 3:

~~~bash
python -m http.server 5500 --directory web-client
~~~

Open in a browser:

~~~text
http://localhost:5500
~~~

Click the GET button and open DevTools/Network. You will typically see **GET /api/info** from the frontend to the backend and a response containing `Access-Control-Allow-Origin: http://localhost:5500`. Click POST JSON, and usually there is an **OPTIONS /api/echo** before POST because Content-Type is `application/json`.

Example GET result (the UUID changes each time):

~~~json
{
  "status": 200,
  "requestId": "40eb6b51-c2f7-4b73-9921-73084776ad6f",
  "payload": {
    "service": "cors-demo",
    "status": "ok"
  }
}
~~~

Example POST result:

~~~json
{
  "status": 200,
  "requestId": "39e5594b-6306-4715-9e3e-6fce6ba1b6ec",
  "payload": {
    "echo": "Echo: Hello"
  }
}
~~~

The request IDs are only examples and are not fixed; do not rely on response timing or the exact count of OPTIONS requests because preflight caching can prevent OPTIONS from appearing on every attempt.

### 10.6. Testing with curl: does not replace browser testing

Simulate an actual GET with the Origin header:

~~~bash
curl -i 'http://localhost:8080/api/info' \
  -H 'Origin: http://localhost:5500'
~~~

You might see:

~~~http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Expose-Headers: X-Request-ID
Vary: Origin
Content-Type: application/json
~~~

Additional headers may be present; ordering and some casing vary by container.

Simulate preflight:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: http://localhost:5500' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

A valid preflight response typically contains:

~~~http
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
~~~

Now change Origin to a disallowed origin:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: http://localhost:5501' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Spring MVC may reject the preflight (typically returning **403 Invalid CORS request**). The browser will not send the actual POST for a rejected preflight.

**However:** `curl` **does not enforce SOP/CORS**; whether it receives HTTP 200 or 403, it still prints the bytes. A complete CORS test requires **browser DevTools** or integration tests verifying policy headers.

### 10.7. MockMvc tests: allowed and forbidden origins

Create `src/test/java/demo/CorsOriginTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsOriginTest {
    @Autowired
    MockMvc mvc;

    @Test
    void allowsActualGetFromTrustedOrigin() throws Exception {
        mvc.perform(get("/api/info")
                .header("Origin", "http://localhost:5500"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "http://localhost:5500"))
            .andExpect(header().string(
                    "Access-Control-Expose-Headers", "X-Request-ID"))
            .andExpect(jsonPath("$.service").value("cors-demo"));
    }

    @Test
    void requestWithoutOriginNeedsNoCorsHeader() throws Exception {
        mvc.perform(get("/api/info"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void jsonPostPreflightIsApproved() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5500")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "http://localhost:5500"))
            .andExpect(header().string(
                    "Access-Control-Allow-Methods",
                    containsString("POST")))
            .andExpect(header().string(
                    "Access-Control-Allow-Headers",
                    containsString("content-type")));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5501")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthorizedMethodForCorsIsRejected() throws Exception {
        mvc.perform(options("/api/info")
                .header("Origin", "http://localhost:5500")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These tests verify the Spring MVC CORS handler: actual response headers, preflight permit/reject by origin and method, and requests without Origin needing no ACAO. To observe browser enforcement and credentials/cookie behavior, you still need to run a browser or E2E test.

**Status note:** Spring CORS implementations may choose a different status for some successful preflights depending on configuration; this test targets typical Spring MVC 6.2 behavior. If you change frameworks or use a custom CorsProcessor, adjust expectations according to actual HTTP semantics rather than skipping origin/method/header checks.

## 11. Real-world CORS scenarios in projects

### 11.1. Frontend and API on the same domain but different ports

A page at `http://localhost:5173` calling `http://localhost:8080` is cross-origin. Allow the exact `http://localhost:5173` at the backend or use a development reverse proxy so the frontend calls `/api` on the same origin as the dev server. A dev proxy is a tool to make URLs **same-origin from the browser's perspective**, not to "disable browser security."

### 11.2. HTTPS frontend but HTTP backend

`https://app.example.com` calling `http://api.example.com` is both cross-origin and risks **mixed content**. Even before evaluating CORS, the browser may block the request due to mixed content policy. The proper fix is serving the API over HTTPS; do not use ACAO to legitimize insecure HTTP.

### 11.3. Proxy changing Host/Origin

When a gateway or reverse proxy is present, the browser sees a public URL different from the backend internal address. The CORS policy must be based on the **frontend's exact public origin**; forwarded headers must come from trusted proxies and be securely configured. Do not blindly reflect any `Origin` without an allowlist.

### 11.4. Cookie login and different subdomains

`https://app.example.com` calling `https://api.example.com` is cross-origin, even though it is usually same-site. When using `fetch(..., {credentials:"include"})` and the server permits credentials, you must allow a specific origin plus `Access-Control-Allow-Credentials: true`; cookie policies and CSRF are still required. Do not assume same-site means CORS is unnecessary.

### 11.5. CORS error masking the real error

The server returns 500 before the CORS processor attaches headers, or an error handler/gateway returns a different response. The browser only reports "CORS policy blocked," leading developers to think the origin is wrong. Inspect server logs, HTTP status, and actual headers using DevTools/curl, then fix the **backend bug** and error response CORS policy properly—never enable a wildcard to mask a 500.

### 11.6. Preflight blocked by an authentication filter

The browser sends OPTIONS without a session cookie; the Security filter returns 401/403 before the CORS config runs. The backend POST controller is never invoked. Configure CORS with Spring Security at the right layer so the CORS policy handles OPTIONS while keeping authorization on the actual request. Never drop authentication from all endpoints because of this.

### 11.7. Response cached under the wrong origin

The server allows `https://a.example`, but a CDN caches A's ACAO response and serves it to B. When ACAO is chosen dynamically, `Vary: Origin` helps caches distinguish variants. CORS does not automatically forbid caching sensitive content; `Cache-Control` must be set separately according to data privacy.

### 11.8. Custom header triggering OPTIONS

The frontend adds `X-Client-Version`, `X-Trace-ID`, or `Authorization`. Even GET requests may require preflight. If the API lacks the corresponding `allowedHeaders`, preflight is rejected. Configure only the headers actually needed; avoid defaulting to `*` on every sensitive endpoint.

## 12. Common mistakes to avoid

1. **Comparing origins by domain while forgetting port:** localhost:3000 differs from localhost:8080.
2. **Confusing path/query as part of the origin:** `/a` and `/b` on the same scheme/host/port are same-origin.
3. **Confusing same-site and same-origin:** subdomains can be same-site yet still cross-origin.
4. **Assuming every cross-origin request triggers preflight:** a plain GET does not need OPTIONS.
5. **Assuming no preflight means no ACAO needed:** the actual response must still permit JavaScript to read it.
6. **Confusing CORS with authentication:** any non-browser HTTP client can still call the API without auth.
7. **Assuming CORS is CSRF protection:** cross-site form POSTs can reach the server even without CORS.
8. **Using `Access-Control-Allow-Origin: *` for credentialed requests:** the browser will not expose the response.
9. **Writing multiple ACAO origins in a single CSV header:** not a valid format.
10. **Trusting client-supplied Origin headers as security:** non-browser clients can spoof them.
11. **Whitelisting `Origin: null` to support file://:** opaque origins are not a trusted identity.
12. **Adding @CrossOrigin("*") on all controllers:** inadvertently opens response reading wider than intended.
13. **Configuring CORS in Spring MVC while Security blocks OPTIONS first:** integrate CORS before security checks.
14. **Forgetting to expose custom response headers:** JS cannot read `X-Request-ID` even though the Network tab shows it.
15. **Using `fetch(..., {mode:"no-cors"})` as a fix:** the response becomes opaque and JS cannot read JSON/status as desired.
16. **Disabling browser web security to make a demo work:** hides misconfigurations, creates local environment risk, and is not a deployment solution.
17. **Testing only with curl:** curl does not enforce SOP; browser testing is required.
18. **Omitting Vary: Origin on reverse proxies/caches:** cached CORS headers may be wrong per origin.
19. **Treating 200 in Network as a successful fetch:** the browser may have blocked the response.
20. **Ignoring non-CORS causes:** TLS, mixed content, DNS, CSP, server errors, and redirects can be the real root cause.

## 13. Step-by-step debugging order

When the Console reports a CORS error:

1. **Confirm the source page origin** with `window.location.origin` and the API URL origin: compare scheme, host, and effective port.
2. **Inspect Network:** is there an OPTIONS request? If so, check the request's `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
3. **Check the preflight response:** does ACAO match? Are the method/headers allowed? Is there an HTTP 401/403/redirect?
4. **If the actual request occurred**, check HTTP status and response ACAO; remember a genuine 500/404 can still appear in the console as a CORS block.
5. **Check credentials mode:** default `same-origin` or `include`? Is the cookie blocked by SameSite/Secure/third-party policy? Is ACA-Credentials valid?
6. **Check Spring config:** mapping paths, `@CrossOrigin` vs `addCorsMappings`, allowed origins/methods/headers, exposed headers.
7. **If Spring Security is present**, check filter order and `http.cors(...)`, CSRF handling, and cookie-less preflight handling.
8. **If a proxy/gateway is present**, check whether ACAO headers are duplicated/stripped, Vary headers, and whether public scheme/host are rewritten.
9. **Do not fix immediately with a wildcard:** first define the intended policy and test one allowed origin and one rejected origin.
10. **Test browser + server:** curl to inspect HTTP bytes, MockMvc to verify CORS processing, and browser E2E to confirm browser enforcement.

## 14. Questions and exercises

**Exercise 1 — Computing origin:** Page `https://shop.example.com:443/cart` calls `https://shop.example.com/api`, `http://shop.example.com/api`, and `https://api.example.com/api`. Determine which cases are same-origin and explain scheme/host/port.

**Exercise 2 — Same-site:** `https://app.example.com` calls `https://api.example.com`. Are they same-origin or same-site? Why does the answer have different implications for CORS and SameSite cookies?

**Exercise 3 — Preflight:** Given four fetch requests—plain GET, JSON POST, form-urlencoded POST, and GET with an Authorization header—predict which ones require OPTIONS and why.

**Exercise 4 — Reading responses:** A cross-origin GET returns HTTP 200 JSON without ACAO. Did the server receive the request? Can browser JavaScript read the body?

**Exercise 5 — Credentials:** Write a CORS configuration for frontend `https://app.example.com` calling a cookie-authenticated API. Why can't ACAO `*` be used with credentials? What additional cookie policies and CSRF checks are needed?

**Exercise 6 — Spring MVC:** Use `WebMvcConfigurer#addCorsMappings` to allow only `https://admin.example.com` to call GET `/api/admin/**`, disallowing any other origin. Write MockMvc preflight tests for GET from that origin and a rejected DELETE.

**Exercise 7 — Debugging:** The browser reports a CORS error when the API returns 500. List three ways to distinguish a real backend error from missing CORS headers, and explain why enabling a wildcard does not fix the root cause.

**Exercise 8 — Proxy:** Both the gateway and backend add ACAO. How can you inspect for duplicate headers? How should you choose a single place of responsibility?

**Exercise 9 — Browser and curl:** Why does curl succeed against an endpoint without CORS configured while fetch from localhost:5500 fails? Name the exact policy enforcement layer.

**Exercise 10 — Security:** Explain why CORS does not protect a payment endpoint from CSRF, and why an API server still needs authorization even when allowedOrigins contains only a single domain.

## 15. Takeaways

- **HTTP(S) origin = scheme + host + effective port**; differing in any one component makes it cross-origin.
- SOP restricts script access across origins, **not blocking every request/navigation/embedding outright**.
- Cross-origin browser fetch may **not require preflight**, yet JS can only read the response if the **actual CORS response allows it**.
- **Preflight OPTIONS** typically appears with JSON POST, custom headers, or methods like PUT/DELETE.
- CORS is an opt-in browser/server policy; **it does not replace authentication, authorization, CSRF protection, or cookie security**.
- Credentialed requests cannot use ACAO wildcard `*`; a specific allowed origin along with other conditions must be used.
- In Spring MVC, choose `@CrossOrigin` or `addCorsMappings` appropriately; with Spring Security, process CORS before authentication/authorization.
- Debug based on **actual origin, OPTIONS, actual response, credentials, HTTP status, and network** — not just by reading the CORS message in the Console.

## 16. Official references

- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy): origin definition, types of cross-origin interactions, SOP.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): safelisted/simple requests, preflight, credentials, and headers.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): specific origin, wildcard, credentials, and Vary.
- [Fetch Standard](https://fetch.spec.whatwg.org/): modern definition of the CORS protocol and request/response handling.
- [Spring Framework 6.2 — MVC CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html): @CrossOrigin, WebMvcConfigurer, CorsProcessor, and global configuration.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): processing preflight before Spring Security.
