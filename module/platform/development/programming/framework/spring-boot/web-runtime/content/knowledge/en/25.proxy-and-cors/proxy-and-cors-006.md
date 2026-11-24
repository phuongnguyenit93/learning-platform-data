# Same-Origin Policy, origins, and the purpose of CORS

> **Scope:** Spring Boot web-runtime → Proxy and CORS. This lesson explains the browser security foundation **Same-Origin Policy (SOP)**, how an **origin** is determined, why **Cross-Origin Resource Sharing (CORS)** is needed, how browsers perform preflight checks and validate responses, and how to implement CORS in Spring MVC alongside a comparison with Spring WebFlux and Spring Security. Hands-on examples use **Java 17+, Spring Boot 3.3.x**, a browser, `curl`, and a static web server on another port. CORS is a browser policy, **not an API authentication or authorization mechanism**.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Determine the origin of a URL from **scheme + hostname + port**, and distinguish same-origin from same-site.
2. Explain which resource read/access operations SOP restricts, while certain navigation or cross-origin image/script loads are permitted under separate rules.
3. State why CORS exists: allowing **an origin authorized by the server** to read a response from another origin in the browser without disabling SOP globally.
4. Read `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Expose-Headers`, `Access-Control-Max-Age`, and `Vary` accurately.
5. Distinguish requests that do not require preflight from requests that require an **`OPTIONS` preflight**; understand that a browser may send the actual request yet block JavaScript from reading the response.
6. Build a Java 17+ application using `@CrossOrigin`, test from a frontend on port 5500 to an API on port 8080, simulate preflight with `curl`, and inspect DevTools.
7. Choose centralized CORS configuration in Spring MVC/WebFlux, integrate with Spring Security and proxies, and handle credentials/cookies without granting overly broad access.
8. Separate CORS from CSRF, CSP, `SameSite` cookies, TLS, authentication, authorization, and proxy settings to avoid vulnerabilities or bad fixes like `Access-Control-Allow-Origin: *` on every endpoint.

## 2. Background: how is an origin determined?

Under the standard URL model, a web document's origin consists of:

~~~text
origin = (scheme, host, port)
~~~

Example:

~~~text
URL:     https://shop.example.test:8443/products?id=5#details
Scheme:  https
Host:    shop.example.test
Port:    8443
Origin:  https://shop.example.test:8443
~~~

**Path, query, and fragment are not part of the origin.** An origin is not the full page URL and does not include `/products?id=5#details`. When comparing origins, a scheme's default port is normalized: HTTP defaults to 80, HTTPS defaults to 443; `https://example.test` and `https://example.test:443` have equivalent origins in normal HTTP contexts. However, HTTPS and HTTP have **different schemes**, so they are different origins.

| Page A | Resource B | Same-origin? | Why? |
|---|---|---|---|
| `https://app.example.test/a` | `https://app.example.test/b?x=1` | Yes | Scheme, host, and port match; differing path/query does not matter |
| `https://app.example.test` | `http://app.example.test` | No | Different scheme (HTTPS vs. HTTP) |
| `https://app.example.test` | `https://api.example.test` | No | Different hostname/subdomain |
| `https://app.example.test` | `https://app.example.test:8443` | No | Different port (443 vs. 8443) |
| `http://localhost:5500` | `http://localhost:8080` | No | Same host/scheme, different port |
| `http://localhost:8080` | `http://127.0.0.1:8080` | No | Different hostname; DNS name and IP are not treated as the same origin |
| `https://example.test` | `https://example.test:443` | Yes | Default port for HTTPS |
| `https://shop.example.test` | `https://api.example.test` | No | Cross-origin even though they may belong to the same *site* |

### Origin vs. site

**Same-origin** compares the three components scheme–host–port. **Same-site** relates to the browser's *site* concept, typically based on scheme and registrable domain (eTLD+1) under the schemeful same-site model. Two subdomains `shop.example.test` and `api.example.test` can be **same-site yet cross-origin**. `SameSite` cookies use site-based rules; SOP/CORS use origins. Never configure CORS by reasoning "same company" or "same second-level domain" while ignoring hostname, port, or scheme.

### Opaque origins and `Origin: null`

Documents loaded from `data:`, sandboxed iframes without same-origin privileges, or certain local file contexts can have an **opaque origin** (not a normal scheme/host/port tuple). When serialized in a header, such an origin may become the literal string `null`. Never blindly allowlist `Access-Control-Allow-Origin: null` to "support local HTML files"—many untrusted contexts produce opaque origins and would gain read access if the server permits literal `null`. To learn CORS, serve the frontend via a local HTTP server instead of opening `file:///.../index.html` directly.

A `blob:` URL usually inherits the origin of the environment that created it; do not treat every blob URL as a separate hostname. Origin relates to how the browser assigns privileges to an *environment*, rather than simply comparing raw URL strings textually.

## 3. What does the Same-Origin Policy (SOP) protect?

SOP is the set of browser security rules that prevents content from one origin from **arbitrarily reading or tampering with sensitive data of another origin**. If you are logged into your bank at `https://bank.example.test`, a malicious page at `https://evil.example.test` is not allowed to simply use JavaScript `fetch` to read the bank's HTML or API responses containing personal data unless the server grants appropriate CORS permissions.

Yet SOP is **not simply "browsers block every cross-origin request."** Several cross-origin interactions are foundational to the Web:

- Users can click links to **navigate** to another site.
- Pages can load images via `<img src="https://...">` and certain other resources under dedicated rules.
- Browsers can load and execute cross-origin scripts via classic `<script src="...">` under applicable policies, though reading the raw response directly with `fetch` differs.
- A page can embed a cross-origin iframe, though scripts inside the iframe and parent page are restricted from accessing each other's DOM.
- HTML forms can submit requests to another origin under certain conditions; being able to submit **does not equal** allowing the submitting page's script to read the response.

By separating permissions to **send, embed, read, and manipulate the DOM**, SOP lets the Web function while isolating data across origins. Policies such as CSP, CORP/COEP, and iframe sandboxing add distinct layers of restriction—they are not alternative names for CORS.

### Intuitive example

Suppose `https://app.example.test` executes:

~~~javascript
const response = await fetch("https://api.example.test/profile");
const profile = await response.json();
console.log(profile);
~~~

This is a **cross-origin fetch**. The browser applies CORS mode (the default for `fetch` on most cross-origin HTTP requests), sends `Origin: https://app.example.test` when appropriate, and checks the API's response. If the server does not return permissive CORS headers, JavaScript **cannot read** the response as a valid data object. That does not prove the request never reached the server.

Against the same URL, `curl https://api.example.test/profile` or a Java backend HTTP client does not enforce browser SOP. **CORS is not designed to block bots, `curl`, or server-to-server clients.** The API must still authenticate, authorize, and validate input.

## 4. What problem was CORS created to solve?

In modern architectures, a frontend at `https://app.example.test`, an API at `https://api.example.test`, and public data on a CDN can live on separate origins. SOP blocks JavaScript from reading cross-origin responses by default, even when **the API owner intentionally wants another frontend app to read them**.

**Cross-Origin Resource Sharing (CORS)** is the protocol coordinating that permission using HTTP headers between the browser and server. An API can specify:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

{"message":"Public API data for the selected frontend"}
~~~

When the `Origin` in the browser request matches the origin allowed by the server and other conditions hold, the browser lets JavaScript read the response. The server **does not disable SOP**; it simply declares a scoped exception.

### What CORS is not

- **Not authentication:** `Access-Control-Allow-Origin` does not identify who the user is or verify a valid token.
- **Not authorization:** direct clients from another server can still call the API unless independent access controls exist.
- **Not CSRF protection:** state-changing requests can still be sent via certain mechanisms even when the browser denies scripts access to read the response.
- **Not a reverse proxy:** CORS is an HTTP/browser policy; a proxy is a network component that forwards requests or adds headers.
- **Not "enabling HTTPS":** TLS encrypts and authenticates the transport layer; CORS governs response access by origin.
- **Not JSON/404/500 error handling:** even when a response has valid CORS headers, the server can still return application errors.

**Primary purpose:** allow a web page controlled access to **HTTP responses from another origin**, as chosen by the server and enforced by the browser.

## 5. Two paths: directly sent requests and preflighted requests

In introductory lessons, CORS requests meeting specific criteria are often called **simple requests**; in the Fetch Standard itself, the exact rules revolve around **CORS-safelisted methods/headers/content types** and additional conditions.

### 5.1. Requests that do not need preflight

A plain cross-origin `GET` with browser-permitted headers can be sent directly:

~~~http
GET /api/message HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5500
Accept: */*
~~~

If the server permits it:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Vary: Origin
Content-Type: application/json

{"message":"Hello from API"}
~~~

The browser checks CORS headers **after receiving the response**; if valid, JavaScript reads the body. If the allow headers are missing or mismatched, the browser raises a CORS error and withholds the response from JavaScript, even though the request **may already have been processed by the server**.

Common criteria for **skipping preflight** include method `GET`, `HEAD`, or `POST`; request headers in the safelist; and `Content-Type` (if set by the client) being one of `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`, along with related conditions. **This is a summary, not the full Fetch Standard**: finer restrictions apply to header values, event listeners, streaming bodies, and more.

### 5.2. Requests that require an `OPTIONS` preflight

With JavaScript:

~~~javascript
await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "client-123"
  },
  body: JSON.stringify({message: "Hello"})
});
~~~

The browser normally must perform a **preflight**, because `Content-Type: application/json` is not a safelisted content type and `X-Request-ID` is a custom header.

Before sending `POST`, the browser automatically sends:

~~~http
OPTIONS /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

The server responds with permission metadata, for example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-Request-ID
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

A successful preflight status may be `200` or another 2xx status depending on server/framework; the body normally contains no API data. Only if the browser accepts the check result does it send the actual `POST`. If preflight is rejected, the **actual `POST` is never sent** by the browser over that CORS flow. By specification, preflight requests normally **do not carry cookies**, so apps using Spring Security must process `OPTIONS` in the right order before session-requiring checks.

### 5.3. Why doesn't preflight "protect the API" in place of the backend?

Preflight is **browser behavior**. `curl`, Java `HttpClient`, Postman, or server-side code can send `POST` directly without sending `OPTIONS` first. If an endpoint transfers money whenever it receives a `POST` without auth or CSRF tokens, CORS cannot prevent abuse.

A **simple** HTML form `POST` can also reach the server from a cross-site page, even when scripts cannot read the response. Therefore, never treat "CORS allows only the right origin" as CSRF defense.

## 6. Reference table of CORS headers

| Header | Sent by | Meaning | Common misconception |
|---|---|---|---|
| `Origin` | Browser request | Origin of the environment sending the request, e.g., `http://localhost:5500` | Believing the header cannot be forged by `curl`/bots |
| `Access-Control-Request-Method` | Browser preflight | The method the browser intends to use for the actual request | Confusing it with the `OPTIONS` method |
| `Access-Control-Request-Headers` | Browser preflight | Non-safelisted request headers the browser wants to send | Thinking it lists response headers |
| `Access-Control-Allow-Origin` | Server response | Only one valid origin or `*` under appropriate conditions | Returning `origin1, origin2` as a list, which browsers reject |
| `Access-Control-Allow-Methods` | Server preflight | Methods permitted for the actual request | Thinking it replaces Spring route mapping and authorization |
| `Access-Control-Allow-Headers` | Server preflight | Request headers permitted on the actual request | Confusing it with headers JS is allowed to read from the response |
| `Access-Control-Allow-Credentials` | Server response | `true` allows sharing a credentialed response under CORS | Combining it with `Access-Control-Allow-Origin: *` |
| `Access-Control-Expose-Headers` | Server response | Non-safelisted response headers scripts may read | Confusing it with `Allow-Headers` |
| `Access-Control-Max-Age` | Server preflight | Hint to cache the preflight result in seconds | Thinking it caches the JSON response or session |
| `Vary: Origin` | Server response / cache | Response variants depend on `Origin` | CORS passes on one origin yet a CDN serves cached headers to another origin |

### `Access-Control-Allow-Origin`: a single origin, not an array

A response can contain:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

or, for **truly public resources and requests without credentials**:

~~~http
Access-Control-Allow-Origin: *
~~~

Do not use:

~~~http
Access-Control-Allow-Origin: https://app.example.test, https://admin.example.test
~~~

expecting the browser to accept both. When multiple origins are permitted, the server matches the incoming `Origin` against an **allowlist** and returns **one** matching origin per request, with accurate cache-vary headers. Never reflect arbitrary incoming origins without checking, as that effectively lets any website read granted responses.

### `Expose-Headers` is not `Allow-Headers`

Suppose the API returns:

~~~http
X-Request-ID: server-echo-001
Access-Control-Expose-Headers: X-Request-ID
~~~

Only then can browser JavaScript read `response.headers.get("X-Request-ID")` on a cross-origin response (beyond the default safelisted headers). Conversely, to **send** `X-Request-ID` on the request, preflight requires a matching `Access-Control-Allow-Headers`. **`Set-Cookie` does not become readable by JavaScript merely by adding it to `Expose-Headers`.**

### Preflight `max-age` differs from HTTP cache `max-age`

`Access-Control-Max-Age: 600` tells the browser it may cache the preflight result under its own semantics; browsers can enforce caps and separate caching rules. It **does not** replace `Cache-Control` for response bodies and does not guarantee preflight stays cached for exactly 600 seconds in every browser. To re-test `OPTIONS`, change the URL/method/headers combination or clear the preflight cache in browser tools; do not assume a page refresh always triggers a new preflight.

## 7. CORS with cookies, credentials, and `SameSite`

Browser `fetch` has an option:

~~~javascript
fetch("https://api.example.test/account", {
  credentials: "include"
});
~~~

`credentials: "include"` asks the browser to apply cross-origin credential-sending rules. However, **cookies are not automatically guaranteed to be sent**: it still depends on cookie domain/path, `Secure`, `SameSite`, third-party cookie policies, privacy restrictions, and HTTPS transport. In genuinely cross-site cookie flows, cookies typically need `SameSite=None; Secure` in modern browsers; that does not grant CORS read access by itself.

If the server intentionally allows an origin to make credentialed requests, the matching response must include:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Never combine `Access-Control-Allow-Origin: *` with credentialed CORS.** Browsers refuse to expose the response to scripts under that combination. Setting `Access-Control-Allow-Credentials: false` is not the standard way to "deny"; when disallowing, simply omit the header.

### Credentialed CORS differs from CSRF

If the browser automatically attaches session cookies to the API, a cross-site page can still attempt to trigger state-changing requests via forms, navigations, or compatible paths without reading the response. Failing CORS read access does not mean cookies or side effects did not happen. Protecting mutations requires **CSRF tokens, `SameSite` cookies, `Origin`/`Referer` checks where appropriate, authentication, and authorization** tailored to the application model.

With tokens in `Authorization`, a custom/non-safelisted request header typically triggers preflight, yet the backend must still validate signature/expiry/scope/permissions. Preflight does not verify token validity. A common mistake is broadly enabling `allowCredentials(true)` and unchecked origins to "fix login"; that can let malicious origins read sensitive data whenever cookies/auth credentials are sent.

### How CORS and cookies differ across four cases

| Case | Does the browser send cookies? | What CORS headers does the server need? | Note |
|---|---|---|---|
| Default cross-origin fetch `credentials: "same-origin"` | Does not send cross-origin credentials in default mode | Valid ACAO; ACAC not strictly needed | JavaScript can read public data, no session |
| Cross-origin fetch `credentials: "include"` | May send if cookie/policy allows | Explicit origin + `Access-Control-Allow-Credentials: true` | No wildcard; CSRF/authorization still needed |
| Server-to-server request | Client sets headers/cookies manually | CORS not needed for client to read | Backend must still authenticate and authorize |
| Preflight `OPTIONS` | Per spec, does not carry normal session cookies | Needs allow-headers/methods/origin; security must not block erroneously | Do not require session login on preflight |

## 8. Complete example: Spring Boot MVC serving a cross-origin API

We set up **two local servers**:

~~~text
Browser page: http://localhost:5500/index.html
               |
               | fetch /api/message and /api/echo
               | Origin: http://localhost:5500
               v
Spring Boot:  http://localhost:8080
               |
               v
           @RestController
~~~

This is **cross-origin** because port 5500 differs from port 8080. No login, cookies, or database are needed for this exercise; they would only obscure observing CORS directly.

### 8.1. Runnable Maven POM

Create a Java 17+ Spring Boot project with `pom.xml`:

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
    <groupId>example</groupId>
    <artifactId>cors-origin-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Spring MVC uses embedded Tomcat by default via `spring-boot-starter-web`. This setup has **no Spring Security**, making it ideal for isolating CORS behavior. In production, integrate Spring Security or appropriate auth controls on every sensitive endpoint.

### 8.2. Complete Java source

Create `src/main/java/example/cors/OriginCorsApplication.java`:

~~~java
package example.cors;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.RequestMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class OriginCorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OriginCorsApplication.class, args);
    }

    public record EchoPayload(String message) { }

    @RestController
    @RequestMapping("/api")
    @CrossOrigin(
            origins = "http://localhost:5500",
            methods = {RequestMethod.GET, RequestMethod.POST},
            allowedHeaders = {"Content-Type", "X-Request-ID"},
            exposedHeaders = "X-Request-ID",
            maxAge = 600)
    public static class DemoController {

        @GetMapping("/message")
        public ResponseEntity<Map<String, String>> message() {
            return ResponseEntity.ok()
                    .header("X-Request-ID", "server-get-001")
                    .body(Map.of("message", "Hello from API"));
        }

        @PostMapping("/echo")
        public ResponseEntity<Map<String, String>> echo(
                @RequestBody EchoPayload payload) {

            if (payload.message() == null
                    || payload.message().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "message must not be blank");
            }

            return ResponseEntity.ok()
                    .header("X-Request-ID", "server-echo-001")
                    .body(Map.of("echo", payload.message()));
        }
    }
}
~~~

Configure the port in `src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

**Code explanation:**

- `@RestController` makes the controller write JSON/text responses instead of template views.
- `@CrossOrigin` limits the **origin** allowed to read responses from a browser to `http://localhost:5500`. A page opened at `http://127.0.0.1:5500` is a **different origin**, so it is not automatically permitted.
- `methods = {GET, POST}` specifies which methods CORS allows for this API; it **does not create new routes**. `@GetMapping` and `@PostMapping` determine which methods/paths the app actually handles.
- `allowedHeaders` lets the browser send JSON `Content-Type` and custom header `X-Request-ID`; other request headers remain subject to CORS checks.
- `exposedHeaders` lets JavaScript read `X-Request-ID` on the **response**; unrelated to allowed request headers.
- `maxAge = 600` hints at caching the **preflight result** for 600 seconds; it does not cache the JSON response for 600 seconds.
- `allowCredentials` is not enabled. This is a public cookie-free demo, safer than enabling credentials broadly when unnecessary.
- Do not manually write `@RequestMapping(method=OPTIONS)` handlers. Spring MVC's CORS infrastructure handles valid `OPTIONS` preflight requests for controller mappings automatically.

The Spring Boot application requires Maven 3.x and Java 17+. Start from the root directory:

~~~bash
mvn spring-boot:run
~~~

Verify there is no origin restriction for a plain HTTP client:

~~~bash
curl -i http://localhost:8080/api/message
~~~

Expected result is **HTTP 200** and JSON containing `"message":"Hello from API"`. `curl` does not enforce SOP. When no `Origin` is sent, whether CORS-specific headers appear does not govern whether `curl` can read the body.

## 9. Complete local HTML page to observe CORS in the browser

Create a `frontend/` folder alongside `pom.xml` with `frontend/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Origin and CORS</title>
</head>
<body>
  <h1>Frontend on port 5500</h1>
  <button id="read">Cross-origin GET</button>
  <button id="send">POST JSON requiring preflight</button>
  <pre id="result"></pre>

  <script>
    const output = document.getElementById("result");
    const base = "http://localhost:8080/api";

    document.getElementById("read")
      .addEventListener("click", async () => {
        try {
          const response = await fetch(base + "/message");
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const data = await response.json();
          const trace = response.headers.get("X-Request-ID");
          output.textContent = "GET: "
            + JSON.stringify(data) + "\ntrace=" + trace;
        } catch (error) {
          output.textContent = "GET failed: " + error.message;
        }
      });

    document.getElementById("send")
      .addEventListener("click", async () => {
        try {
          const response = await fetch(base + "/echo", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": "client-123"
            },
            body: JSON.stringify({message: "From frontend"})
          });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const data = await response.json();
          const trace = response.headers.get("X-Request-ID");
          output.textContent = "POST: "
            + JSON.stringify(data) + "\ntrace=" + trace;
        } catch (error) {
          output.textContent = "POST failed: " + error.message;
        }
      });
  </script>
</body>
</html>
~~~

Use `output.textContent` instead of `innerHTML` to avoid accidentally executing HTML returned in a response. That is good defensive practice even though this lesson focuses on CORS.

In a second terminal, start a static web server in the `frontend` folder:

~~~bash
cd frontend
python3 -m http.server 5500
~~~

On Windows you can use `py -m http.server 5500` or `python -m http.server 5500` depending on your setup. Open exactly:

~~~text
http://localhost:5500/index.html
~~~

Do not open the file directly via `file:///`, and do not arbitrarily switch to `http://127.0.0.1:5500` if the server only permits `localhost:5500`.

### What to observe in DevTools

Open **Developer Tools → Network**, and enable Preserve log if you want to keep request logs across actions:

1. Click "Cross-origin GET": you should see a `GET` request to port 8080, with a response containing `Access-Control-Allow-Origin: http://localhost:5500` and a JSON body. There will not necessarily be an `OPTIONS` request.
2. Click "POST JSON requiring preflight": you should see `OPTIONS /api/echo`, followed by `POST /api/echo`. If the browser holds a valid preflight cache entry, `OPTIONS` may not reappear on subsequent clicks.
3. The output displays `trace=server-get-001` or `trace=server-echo-001` because the server sets the `X-Request-ID` response header and `Access-Control-Expose-Headers` allows scripts to read it.
4. Serve the frontend tab on a non-allowlisted origin (e.g., another server on port 5501) and retry: the browser should refuse to expose the response to JS or not send the actual request if preflight fails. The Console will report a CORS policy error.

**Note:** browser errors usually look like `TypeError: Failed to fetch` or "blocked by CORS policy," without necessarily exposing the HTTP status to JavaScript. This differs from a server returning 4xx/5xx with valid CORS headers, where JS can inspect `Response` with `ok=false`.

## 10. Using `curl` to separate browser behavior from server behavior

`curl` is useful for inspecting request/response headers, yet it **does not enforce CORS itself**. The commands below merely simulate the headers a browser normally sends.

### 10.1. `GET` with an allowed `Origin`

~~~bash
curl -i \
  -H 'Origin: http://localhost:5500' \
  http://localhost:8080/api/message
~~~

In Windows PowerShell, use `curl.exe` and keep the command on one line if needed. Expect a 200 response, JSON, and `Access-Control-Allow-Origin` matching the frontend origin; `Vary: Origin` and preflight Vary headers may also appear per Spring's implementation.

### 10.2. Simulated preflight

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/echo \
  -H 'Origin: http://localhost:5500' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-request-id'
~~~

This is an `OPTIONS` request **with complete preflight headers**. Running just `curl -X OPTIONS` without `Origin` and `Access-Control-Request-Method` is not equivalent to browser preflight. In a valid response, expect the origin allowed, `POST` and both request headers accepted, and `Access-Control-Max-Age` within Spring/browser policy. The status may be 200 or an appropriate 2xx success code.

### 10.3. Sending the actual `POST`

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H 'Origin: http://localhost:5500' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: client-123' \
  --data '{"message":"Hello"}'
~~~

A successful response contains JSON with `"echo":"Hello"` and `X-Request-ID: server-echo-001`. Using `curl`, you can read `X-Request-ID` even if the server **did not** expose it to browser JavaScript: that is the difference between a raw HTTP/network client and browser CORS enforcement.

### 10.4. `Origin` not in the allowlist

~~~bash
curl -i \
  -H 'Origin: http://localhost:5501' \
  http://localhost:8080/api/message
~~~

Spring MVC's CORS processor can return 403 for requests with a disallowed `Origin`; exact HTTP behavior depends on routes, filter chains, and config. `curl` can read bodies regardless of CORS, so **never conclude "CORS allows it" simply because `curl` receives a body**. What matters is whether a browser permits reading the response from that origin, and whether the server enforces independent protections on sensitive resources.

### 10.5. Request without an `Origin` header

~~~bash
curl -i http://localhost:8080/api/message
~~~

A request from `curl` without `Origin` is not a browser-governed cross-origin request. Many APIs still return 200. **CORS is not an IP firewall, JWT verifier, or API key gate.**

## 11. Why `@CrossOrigin` should not be used indiscriminately

Spring Framework lets you place `@CrossOrigin` on controller classes or methods. Using `@CrossOrigin` without specifying origins can yield relatively broad defaults; current framework documentation notes that defaults allow origins/headers/methods per mapping while `allowCredentials` is off by default. For public endpoints serving truly public data this may be fine, whereas private APIs require a strict allowlist.

Two contrasting examples:

~~~java
// Illustrates annotation declaration only.
@CrossOrigin(origins = "https://app.example.test")
@GetMapping("/public-catalog")
public List<Item> list() { /* ... */ }
~~~

~~~java
// Risky: broader than necessary for user-specific data.
@CrossOrigin
@GetMapping("/user-profile")
public Profile profile() { /* ... */ }
~~~

`Item` and `Profile` belong to a real app and do not compile standalone here. Broad CORS does not cause an authentication bypass by itself, yet if clients send credentials under other settings or an endpoint is mistakenly treated as public, cross-origin read exposure can become too wide. Always choose policies based on data classification, trusted origins, and credential requirements.

### When should you use `@CrossOrigin`?

- One or a few endpoints have a specialized policy that is clearest right next to the controller.
- The CORS policy is tied to the route's business semantics without many dynamic origins.
- Small projects or public APIs needing a clear allowlist.

When many controllers share the same frontend origins and consistent CORS requirements, prefer **central configuration** instead of duplicating annotations across dozens of classes.

## 12. Spring MVC: global CORS configuration

In a Spring MVC application, you can use `WebMvcConfigurer`:

~~~java
package example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class GlobalMvcCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5500")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Request-ID")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

This Java class can be added to an MVC project instead of `@CrossOrigin`; when testing **this configuration**, **remove `@CrossOrigin`** from the demo controller to keep a single policy source. When both annotations and global settings exist, Spring MVC can **combine** local and global CORS configs per framework rules; collection properties can be merged while single-valued properties may override. Never rely on intuition that "the stricter policy always wins."

- `addMapping("/api/**")` applies to routes matching the pattern, not "enabling CORS on all static pages/resources."
- `allowedOrigins` checks **origin strings** with scheme, host, and port. It does not match URL paths directly.
- `allowedMethods` declares methods CORS allows, yet endpoints/controllers must still define handlers for those methods.
- `allowedHeaders` governs preflight request headers; `exposedHeaders` governs response headers readable by browser scripts.
- `maxAge` is interpreted in seconds, not JSON TTL.
- `allowCredentials(false)` is a non-credentialed policy; if cookies are unnecessary, this is the simpler choice.

**You do not need `@EnableWebMvc` just to enable CORS.** Spring Boot MVC auto-configuration is already active; adding a `WebMvcConfigurer` is the minimally invasive extension. `@EnableWebMvc` can alter many of Boot's defaults and is unnecessary for fixing CORS.

### Multiple allowed origins

When serving both production and a dev frontend:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins(
                "https://app.example.test",
                "http://localhost:5500")
        .allowedMethods("GET", "POST");
~~~

This list is the **server allowlist**; each response returns the single matching origin for **that request**, never an `Access-Control-Allow-Origin` containing both. Avoid keeping dev localhost origins in production unless genuinely needed; configure per profile/environment.

## 13. Origin patterns, wildcards, and proxy caching

### Do not use wildcards indiscriminately

If data is truly public and uses no credentials, `Access-Control-Allow-Origin: *` may be used. For account data, transaction histories, internal info, or cookie-based APIs, that is usually inappropriate.

With `allowCredentials(true)` in Spring CORS, `allowedOrigins("*")` cannot be combined per Spring/Fetch rules. The framework provides `allowedOriginPatterns` to match origin groups when genuinely needed; it echoes back **the specific matched origin** rather than a literal wildcard. Still, broad patterns like `https://*.example.test` can accidentally authorize a taken-over subdomain or untrusted tenant. **Prefer explicit allowlists** for credentialed apps.

### Mind `Vary` and CDNs

Suppose a shared HTTP cache/CDN stores a response with:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

If the CDN ignores `Vary: Origin` or fails to partition cache keys by variant, a client from `https://admin.example.test` can receive response headers cached from the earlier origin. Browsers will typically block reading due to the mismatched ACAO, yet faulty caching can trigger unpredictable failures or leaks if combined with unsafe Origin reflection. For authenticated data, also design `Cache-Control: private/no-store`, keys/authorization, and CDN caching rules carefully.

Especially for **preflight responses**, variation can depend on `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`. Frameworks typically add matching `Vary` headers; if a proxy adds headers itself, make sure it does not emit multiple invalid ACAO values.

### Proxies and CORS headers must have a single owner

An architecture:

~~~text
Browser --> CDN/Ingress/Nginx --> Spring Boot API
               |
               +--- may add/overwrite CORS headers
~~~

If Nginx returns `Access-Control-Allow-Origin: *` while Spring returns a specific origin, the response can contain **two ACAO headers** or incompatible values. The browser will reject it. It is best to designate **one primary layer owning CORS policy**, especially with cookies, and test end-to-end through the real ingress. If the proxy handles `OPTIONS` itself, ensure its policy stays synchronized with Spring Security/routes rather than letting through methods/headers the backend rejects.

## 14. Spring Security: CORS must be processed before authentication

When `spring-boot-starter-security` is present, Spring Security's filter chain can reject preflight if `OPTIONS` lacks a session/cookie/token. Spring Security docs emphasize that CORS should be processed **before** security checks via proper integration, because preflight requests usually carry no session credentials.

With Spring MVC configured via `WebMvcConfigurer`, Security can typically integrate:

~~~java
// Configuration fragment: place in @Configuration of an app
// that already has spring-boot-starter-security.
@Bean
SecurityFilterChain filterChain(HttpSecurity http)
        throws Exception {
    http.cors(Customizer.withDefaults());
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    return http.build();
}
~~~

This **snippet** requires imports (`org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer`, `org.springframework.context.annotation.Bean`) and an app with auth configured. **Do not** drop this snippet into a non-Security demo expecting it to compile. It also **does not disable CSRF**; for cookie-authenticated POSTs, keep proper CSRF protection and handle tokens in the frontend.

If Spring Security does not pick up your expected MVC CORS config, you can define a `UrlBasedCorsConfigurationSource` bean with an explicit allowlist and wire `http.cors(...)` accordingly. Never define multiple competing `CorsConfigurationSource` beans expecting Security to guess the right one; verify bean wiring, filter order, and Spring Security version.

### True meaning of 401/403 on preflight

A valid `OPTIONS` request can be rejected because:

1. Security enforces authentication before the CORS filter runs.
2. The `Origin` is not allowed.
3. The method (e.g., `DELETE`) is not in `allowedMethods`.
4. A header (e.g., `Authorization` or `X-Token`) is not in `allowedHeaders`.
5. The request was blocked earlier by a gateway/WAF before reaching Spring.
6. The path does not match a controller/CORS mapping or proxy routing altered it.

Calling `permitAll()` on all `OPTIONS` **is not enough** if CORS headers are missing, and opening all `OPTIONS` grants no data read access either. Conversely, disabling CSRF globally just so POST "stops throwing CORS errors" is dangerous; distinguish CORS preflight, CSRF token failures, and authentication failures using Network tabs and logs.

## 15. Spring WebFlux also supports CORS, using reactive config APIs

In WebFlux, annotated controllers still support `@CrossOrigin`. For global configuration in WebFlux, use `WebFluxConfigurer` and the reactive package:

~~~java
package example.reactivecors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class GlobalReactiveCorsConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Request-ID")
                .exposedHeaders("X-Request-ID")
                .maxAge(600);
    }
}
~~~

This class is a **configuration file for a WebFlux project**, not a standalone runnable server; it needs `@SpringBootApplication`, `spring-boot-starter-webflux`, and annotated routes. In Spring WebFlux, `WebFluxConfigurer` / `org.springframework.web.reactive.config.CorsRegistry` differ from `WebMvcConfigurer` / `org.springframework.web.servlet.config.CorsRegistry`. Be careful not to import the wrong `CorsRegistry` package.

If the app uses **functional endpoints (`RouterFunction`)**, use `CorsWebFilter` or compatible reactive pipeline configuration, rather than assuming `@CrossOrigin` on another controller covers functional routes. Spring Security WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity.cors(...)`, **distinct** from Servlet `SecurityFilterChain`/`HttpSecurity`.

Note: using WebFlux does not make CORS "non-blocking authorization." Browsers enforce the exact same Origin/CORS model; only the server's HTTP runtime differs. For both MVC and WebFlux, test CORS together with the reverse proxy and security middleware of the deployed stack.

## 16. Distinguishing CORS from CSRF, CSP, and related mechanisms

| Mechanism | Primary goal | Where enforced? | Replaces CORS? |
|---|---|---|---|
| **SOP** | Isolates read/DOM access across origins | Browser | CORS is a controlled exception for certain requests |
| **CORS** | Server allows browser JS to read cross-origin responses under conditions | HTTP headers + browser | Does not replace auth, CSRF, or CSP |
| **CSRF protection** | Prevents a user's browser from being tricked into state-changing actions using automatic credentials | Server + cookie/token/origin checks | No. CORS does not block all mutating requests |
| **CSP `connect-src`** | Restricts where the **current page's** JavaScript may connect | Browser enforcing page-issued policy | No. Frontend CSP does not grant API CORS access on another origin |
| **`SameSite` cookies** | Restricts sending cookies based on site relationship | Browser cookie policy | No. Same-site differs from same-origin |
| **CORP/COEP/COOP** | Resource/browsing-context isolation policies mitigating other cross-origin risks | Browser / response headers | No. Applies to distinct use cases |
| **TLS/HTTPS** | Secures transport and authenticates endpoints via trust | HTTP transport | No. An HTTPS app and HTTPS API can still be cross-origin |
| **Authentication/Authorization** | Establishes identity and enforces resource/action permissions | Application / API gateway | Required independently of CORS |
| **Reverse proxy** | Routes, terminates TLS, caches, rate-limits, may inject headers | Infrastructure | A proxy can manage CORS, yet the proxy itself is not SOP |

**Practical rule:** if browser CORS blocks JavaScript, never rush to "fix" it by disabling CSRF, putting `*` on every endpoint, adding wildcard response headers, or launching a browser with web security disabled. Instead, diagnose the exact origin, preflight, and read permissions under browser policy.

## 17. Layer-by-layer CORS debugging checklist

### Step 1 – Record the two exact origins

- What is the open frontend URL **including scheme, hostname, and port**?
- What API URL is `fetch` calling?
- Is there an HTTP → HTTPS redirect, cross-host redirect, or proxy rewrite making the effective origin different from expected?
- Did the user open the frontend with `localhost` or `127.0.0.1`? Those are two different hostnames.

In the DevTools Console:

~~~javascript
console.log(window.location.origin);
~~~

Expected result for the lab when opened at the right URL: `http://localhost:5500`. Do not guess the origin from a project name or host IP.

### Step 2 – Inspect the first Network request

- Is there an `OPTIONS` preflight? If yes, inspect `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
- If `OPTIONS` returns 401/403/404/405, check Security, CORS mappings, gateway/WAF, and routes.
- If there is no `OPTIONS`, the request may be CORS-safelisted or preflight was cached by the browser; never treat "no `OPTIONS` seen" as proof CORS is disabled.
- If `GET` was sent and returned 200 yet the Console reports CORS, inspect response headers: does ACAO match the frontend origin exactly? Are there duplicate headers or an invalid wildcard+credentials combination?

### Step 3 – Inspect preflight and actual responses

Distinguish:

~~~text
Preflight OPTIONS response:
  Access-Control-Allow-Origin
  Access-Control-Allow-Methods
  Access-Control-Allow-Headers
  Access-Control-Max-Age
  Access-Control-Allow-Credentials (if credentialed)

Actual GET/POST response:
  Access-Control-Allow-Origin
  Access-Control-Allow-Credentials (if credentialed)
  Access-Control-Expose-Headers (if JS reads custom headers)
~~~

If preflight succeeds yet the actual response lacks ACAO (for instance, the server throws 500 and a proxy strips headers on error pages), the browser still blocks JS from reading the response. CORS must apply consistently across both success and error responses through the right middleware/proxy.

### Step 4 – Separate network/TLS errors from CORS

If DNS lookup fails, a TLS certificate is untrusted, mixed-content policy blocks an HTTP call from an HTTPS frontend, the server is not listening, or a proxy times out, the browser reports fetch failure before CORS completes. Adding ACAO to a controller **cannot fix** TLS/network errors. Use `curl` with proper TLS verification, the Network waterfall, server logs, and proxy logs to find where the request stopped.

### Step 5 – Check credentials and cookies

If `fetch` uses `credentials: "include"`, check:

- Explicit origin allowlist, not `*`.
- Response `Access-Control-Allow-Credentials: true` where appropriate.
- Cookie domain/path/`SameSite`/`Secure` and third-party cookie policy.
- API actually enforces authentication and authorization.
- CSRF tokens handled properly for mutations; never disable CSRF as a "CORS workaround."
- Browser preflight `OPTIONS` does not carry normal session cookies; Spring Security filter ordering is right.

### Step 6 – Eliminate proxy conflicts

Test both direct backend `http://localhost:8080` and the real URL through ingress. If the two paths differ, a proxy/CDN/WAF is likely altering headers or blocking `OPTIONS`. Do not configure both Nginx and Spring to each emit their own ACAO; choose one owner and write an integration test against the final URL.

## 18. Common configuration errors

| Symptom | Possible cause | Fix |
|---|---|---|
| `No 'Access-Control-Allow-Origin' header` | Route lacks CORS policy, controller mismatch, proxy drops header | Configure right mapping and origin, inspect actual response |
| `ACAO does not match origin` | Wrong scheme/host/port, frontend uses IP instead of localhost | Check `window.location.origin`, fix allowlist accurately |
| `Credential is not supported if ACAO='*'` | Credentialed fetch combined with wildcard | Use explicit origin + `allowCredentials(true)` when truly needed |
| `Multiple Access-Control-Allow-Origin` | Both proxy and app add the header | Keep one CORS owner; never send a list of origins in ACAO |
| `Request header x-request-id not allowed` | Custom request header not permitted by preflight | Add to `allowedHeaders` if the API legitimately permits it |
| `Method PUT/DELETE not allowed` | Method not permitted by preflight | Add only required methods alongside matching routes/authorization |
| `OPTIONS` 401/403 | Security chain blocks preflight or wrong origin | Enable CORS integration before auth, verify allowlist |
| `POST` 403 after `OPTIONS` succeeded | Missing CSRF token, auth/authorization failure | Diagnose Security; do not assume it is CORS |
| `GET` 200 in `curl` yet `fetch` fails | `curl` does not enforce CORS; browser lacked matching ACAO | Test in browser DevTools, inspect CORS headers |
| `Set-Cookie` unreadable via `response.headers` | `Set-Cookie` is forbidden from JS exposure | Let the browser manage cookies per policy; do not read via fetch headers |
| Frontend opened via `file:///...` gives `null` origin | Page not served from a stable HTTP origin | Run a local static server on localhost |
| HTTPS frontend calling HTTP API blocked | Mixed content / HTTPS security, not just CORS | Serve the API over HTTPS or configure TLS proxy properly |
| Preflight cache hides `OPTIONS` | `Access-Control-Max-Age` or browser cache | Test cold/clean cache and avoid false conclusions |
| Browser still fails despite right backend | CDN/proxy/WAF alters headers or caches variants | Test via real URL, `Vary: Origin`, single policy owner |
| API called by bots from unknown origins | CORS is not a firewall or API auth | Add authentication, authorization, rate limiting, validation |
| User data readable by JS on untrusted site | Overly broad allowed origins + credentialed responses | Narrow allowlist, review cookies, credentials, CSRF, and sensitive data |

## 19. Practical pre-release test matrix

A cross-origin API should be tested for both **allowed** and **denied** cases, not just a single 200 response.

| Case | Where the request originates | Expected browser behavior |
|---|---|---|
| 1. Allowed `GET` | `http://localhost:5500` → `http://localhost:8080/api/message` | JS reads JSON; `OPTIONS` not strictly required |
| 2. Allowed JSON `POST` | 5500 → `/api/echo` with JSON and `X-Request-ID` | Valid preflight (if uncached), `POST` sent and JS reads JSON |
| 3. Allowed exposed header | 5500 → `/api/message` | JS reads `X-Request-ID` due to `Expose-Headers` |
| 4. Disallowed origin | 5501 → same API | Browser denies JS access to response; simple `GET` may still reach the route |
| 5. Wrong scheme | `https://localhost:5500` (if serving HTTPS) → HTTP API | Different origin; may also hit mixed-content blocking |
| 6. Wrong hostname | `http://127.0.0.1:5500` → localhost API | Does not match `http://localhost:5500` |
| 7. Disallowed method | 5500 → `DELETE /api/echo` | Rejected by preflight or no handler; do not add a `DELETE` route unintentionally |
| 8. Disallowed header | 5500 → `POST` with `X-Admin-Key` | Browser preflight fails if header is not allowed |
| 9. Credentialed wildcard | Any origin + `credentials: include` + wildcard ACAO | Browser refuses to share response with JS |
| 10. Server error page | Allowed origin yet handler returns 4xx/5xx | CORS headers must still allow JS to read useful errors; authorization remains enforced |
| 11. Proxy/nginx path | Frontend → deployed public API URL | Matches backend policy, no duplicate or stripped ACAO |
| 12. Server-to-server request | Java `HttpClient` or `curl` without `Origin` | API still requires auth; CORS is not a security filter |

When writing automated tests, do not check only `Access-Control-Allow-Origin` in `curl` responses: include **browser-level integration tests** (Playwright/Selenium or manual DevTools) to verify real `fetch`/preflight/credentials behavior. For production systems, use organization-owned hosts rather than assuming example domains have real DNS/TLS.

### One-sentence summary

**SOP sets the boundary on reading/touching data between origins in the browser; CORS is a server-granted exception letting browser JavaScript read selected cross-origin responses; authentication, authorization, and CSRF protection must still be designed independently.**

## 20. Self-check questions

**1. Does an origin include path and query?**  
No. Standard origins consist of scheme, host, and port. `https://a.example.test/x` and `https://a.example.test/y?z=1` share the same origin.

**2. Are `http://localhost:5500` and `http://localhost:8080` same-origin?**  
No. Their ports differ.

**3. Do `https://shop.example.test` and `https://api.example.test` share the same origin because they share a registrable domain?**  
No. Different subdomains have different hostnames and are cross-origin, even though they may be same-site.

**4. Does SOP block browsers from sending every cross-origin request?**  
No. SOP mainly restricts reading/accessing responses; certain resource loads, navigations, and form requests cross-origin still occur under Web rules.

**5. Why does CORS exist?**  
So a server can allow JavaScript from selected origins to read cross-origin responses without disabling SOP across the whole Web.

**6. `curl` shows no CORS error, while browser `fetch` fails. Who is wrong?**  
Neither is necessarily wrong. `curl` does not enforce browser SOP, whereas the browser checks response headers under CORS. Inspect the API response and allowlist.

**7. Does `POST` `application/json` with `X-Request-ID` normally send `OPTIONS` first?**  
Yes, when it is a cross-origin browser CORS request without a valid preflight cache entry, due to the non-safelisted content type and header.

**8. Does preflight `OPTIONS` carry session cookies like the actual request?**  
Per CORS rules, preflight normally omits cookies; security must handle preflight before cookie-dependent authentication.

**9. Can a server return ACAO with two comma-separated origins?**  
No. The response must specify one origin or `*` under valid conditions.

**10. How do `Access-Control-Allow-Headers` and `Access-Control-Expose-Headers` differ?**  
`Allow-Headers` lists request headers the browser may send after preflight; `Expose-Headers` lists response headers JavaScript may read.

**11. Does CORS protect against CSRF automatically?**  
No. Some state-changing requests can still be sent without needing to read the response. Dedicated CSRF protection and authorization are still required.

**12. Can `Access-Control-Allow-Origin: *` be used with `Access-Control-Allow-Credentials: true` for cookie-based APIs?**  
No. Browsers reject this combination for credentialed CORS.

**13. Is `Access-Control-Max-Age` the TTL of the JSON response?**  
No. It controls preflight result caching under browser rules; it does not replace `Cache-Control` response caching.

**14. Do you need `@EnableWebMvc` when using `@CrossOrigin`?**  
No. Spring MVC supports CORS, and Spring Boot auto-configuration handles default MVC setup; just configure the right policy.

**15. Why might `OPTIONS` return 403 while `GET` works?**  
Because of CORS policy (preflight methods/headers), Security filter order, proxy behavior, or route mapping. Inspect Network and request headers.

**16. If a `@RestController` handles `GET /api/message` with 200 in `curl` yet the browser cannot read it, is CORS definitely the cause?**  
Not necessarily. It could be network/TLS/mixed content/CSP or CORS; verify whether the request reached the server and check DevTools.

**17. Is a `SameSite` cookie the same as same-origin?**  
No. `SameSite` is based on site relationships; SOP/CORS use scheme–host–port origins.

**18. If CORS preflight fails, does that mean bots cannot call the API?**  
No. Bots and server-side HTTP clients can send requests directly; the API must enforce authentication, authorization, and rate limits itself.

## 21. References

- [MDN – Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): origin definition, read boundaries, and opaque origins.
- [MDN – Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin): `Origin` request header and serialization.
- [MDN – Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): HTTP request/response headers, preflight, credentials, and browser behavior.
- [MDN – CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors): common errors and troubleshooting.
- [MDN – Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): wildcard, explicit origins, `Vary`, and caching.
- [MDN – Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials): credentialed fetches and preflight rules.
- [Fetch Standard (WHATWG)](https://fetch.spec.whatwg.org/): normative specification for the CORS protocol, safelists, preflight, and credentials.
- [Spring Framework – MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `@CrossOrigin`, global `WebMvcConfigurer`, combining local and global configuration.
- [Spring Framework – WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): annotations, reactive config, and `CorsWebFilter`.
- [Spring Security – Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): integrating `CorsFilter`/`CorsConfigurationSource` and preflight before auth.
- [Spring Security – Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): integrating policy in reactive `SecurityWebFilterChain`.
- [Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/): Spring MVC/WebFlux and web runtime configuration.