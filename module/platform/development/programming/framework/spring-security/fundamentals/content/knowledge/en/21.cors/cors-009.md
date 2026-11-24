# Testing with a Browser Instead of Relying Only on curl Results

> **Module:** Spring Security – fundamentals  
> **Group:** CORS  
> **Topic:** Testing with a browser instead of relying only on curl results  
> **Practice scope:** Spring MVC/Servlet, Spring Security 6.5.x, Spring Boot 3.5.7, Java 17+, modern browsers, and command-line HTTP clients.

## 1. Learning objectives

After this lesson, you will know how to:

1. Explain why an API works fine with `curl` or Postman yet JavaScript `fetch` in a browser reports a CORS error.
2. Distinguish **origin**, **site**, **same-origin**, **cross-origin**, and **cross-site**.
3. Observe the `Origin` request header, `OPTIONS` preflight, and `Access-Control-Allow-*` response headers in DevTools.
4. Recognize cases where the browser only blocks permission to **read the response** versus cases where the browser blocks the **actual request before preflight**.
5. Test four failure classes: origin not in allowlist, disallowed header, disallowed method, and incompatible credential mode.
6. Run a Java 17+ lab with a frontend at `127.0.0.1:5500`, API at `127.0.0.1:8080`, and the same frontend at `127.0.0.1:5501` to reproduce the difference.
7. Write Spring `MockMvc` tests for CORS policy, while understanding why MockMvc does not replace a real browser.
8. Distinguish CORS from HTTP authentication, authorization, CSRF, CSP, SameSite cookies, and network errors.
9. Build a QA/CI checklist covering preflight, actual requests, credentials, redirects, proxies, and side effects.

**Core message:** CORS is a protection mechanism enforced by **browsers**. `curl` can inspect a server's response headers, yet it does not apply Same-Origin Policy/CORS checks like a browser. Hence **“curl got 200 OK” does not prove “frontend JavaScript is allowed to read the response”**.

## 2. The origin concept and why even a different port triggers CORS

An origin is defined by the tuple:

~~~text
scheme + hostname + port
~~~

Examples:

| Source page | Target URL | Same origin? | Reason |
| --- | --- | --- | --- |
| `http://127.0.0.1:5500` | `http://127.0.0.1:8080` | No | Different port |
| `http://localhost:5500` | `http://127.0.0.1:5500` | No | Different hostname |
| `http://example.test` | `https://example.test` | No | Different scheme |
| `https://app.example.test` | `https://api.example.test` | No | Different subdomain |
| `https://example.test/a` | `https://example.test/b` | Yes | Path is not part of origin |
| `https://example.test` | `https://example.test:443` | Yes | 443 is the HTTPS default port |

The **Same-Origin Policy** restricts JavaScript on website A from reading data from cross-origin website B unless B grants matching CORS permission. Without this boundary, an untrusted page could try to read data from systems where the user is signed in.

**CORS (Cross-Origin Resource Sharing)** is an HTTP-header mechanism allowing a resource server to declare which origins the browser may permit to access responses.

**Cross-origin is not synonymous with cross-site.** `SameSite` cookies use the site concept, which can span multiple subdomains; meanwhile CORS checks the full origin (scheme, hostname, port). A frontend `app.example.test` calling `api.example.test` can be cross-origin yet still same-site depending on scheme/domain. Therefore never equate CORS with cookie policy or CSRF.

## 3. How does a browser differ from curl at its core?

Suppose the backend has an endpoint:

~~~http
GET /api/public HTTP/1.1
Host: 127.0.0.1:8080
~~~

Using the CLI:

~~~bash
curl -i http://127.0.0.1:8080/api/public
~~~

Curl does not bind the request to a web page with origin `http://127.0.0.1:5501`, so it does not auto-send preflight or enforce CORS response checks. If the API returns 200 with JSON, curl reads it.

However, from the page `http://127.0.0.1:5501`:

~~~javascript
fetch("http://127.0.0.1:8080/api/public")
  .then(response => response.json())
  .then(console.log)
  .catch(console.error);
~~~

The browser knows the script comes from origin 5501. If the backend only permits 5500, the browser forbids the script at 5501 from reading the response; the promise may reject with a `TypeError`, and DevTools shows a specific CORS message.

### Comparison table

| Check | Browser `fetch` | Ordinary curl |
| --- | --- | --- |
| Aware of JavaScript page's origin | Yes | No |
| Automatically sends `Origin` when needed | Yes | User can add manually |
| Automatically sends `OPTIONS` preflight | Yes if request requires it | No |
| Enforces `Access-Control-Allow-Origin` | Yes | No |
| Enforces `Allow-Methods`/`Allow-Headers` for preflight | Yes | No |
| Evaluates `credentials`, cookies, SameSite/Secure | Yes | Not under browser policy |
| Blocks JavaScript from reading CORS-violating responses | Yes | No |
| Applies CSP, mixed content, browser privacy settings | Yes | Not the same mechanism |
| Checks HTTP status/body on backend | Yes when response is readable | Yes |
| Manually simulates preflight | Unnecessary, browser handles it | Can send manual `OPTIONS` |

Thus, curl and browsers **do not replace each other**: curl is useful for checking HTTP connectivity, status, headers, and payloads; a browser is necessary to verify browser enforcement.

One important detail: if curl **deliberately** sends a rejected `Origin` header, the Spring CORS processor can return 403. That tests server policy when it sees an Origin, yet **curl still does not enforce CORS rules on the result** like a browser. Depending on implementation, another server might return 200 without CORS headers; curl would still read the body while a browser blocks it.

## 4. When does the browser send preflight?

### 4.1. Simple requests — OPTIONS not necessarily sent

Example:

~~~javascript
fetch("http://127.0.0.1:8080/api/public");
~~~

For a simple GET without special headers, the browser normally sends the GET directly and then checks CORS headers on the response:

~~~text
Browser at 5500
  |
  +-- GET /api/public
  |   Origin: http://127.0.0.1:5500
  v
API at 8080
  |
  +-- 200 OK
  |   Access-Control-Allow-Origin: http://127.0.0.1:5500
  v
Browser lets JS read response
~~~

If the server disallows the origin, the GET request **may already have been processed**, yet JavaScript still cannot read the response. Never treat a CORS failure message as proof the request never reached the backend.

### 4.2. Non-simple requests — browser sends OPTIONS first

Example:

~~~javascript
fetch("http://127.0.0.1:8080/api/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Demo-Tag": "browser"
  },
  body: JSON.stringify({ message: "hello" })
});
~~~

`Content-Type: application/json` is not among the CORS-safelisted content types for simple requests; `X-Demo-Tag` is a custom header. The browser performs an **OPTIONS preflight**:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-demo-tag
~~~

If the server agrees, the response carries information like:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://127.0.0.1:5500
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-Demo-Tag
~~~

Then the browser sends the **actual POST**. If preflight is rejected, the browser **does not send the actual POST** after that preflight. This is a test you must observe in the Network tab and cannot infer from a curl POST.

### 4.3. Preflight is not a login request

Under the CORS/Fetch model, preflight carries no normal cookies/credentials like `JSESSIONID`. Therefore Spring Security recommends **processing CORS before authentication/authorization** so OPTIONS does not get 401 simply for lacking a session cookie.

Preflight **grants no business permissions** and does not prove the user is logged in. After preflight succeeds, the actual request still requires authentication, authorization, and CSRF protection for cookie-based state-changing operations.

### 4.4. Why is OPTIONS sometimes not visible?

Possible reasons:

- The GET/POST request belongs to simple requests and needs no preflight.
- The browser cached the preflight result per `Access-Control-Max-Age`.
- DevTools is filtering requests, e.g. showing only Fetch/XHR or hiding OPTIONS.
- The request never happened due to a JavaScript error, CSP, mixed content, DNS, TLS, or earlier connection failure.
- A Service Worker or cache layer altered the actual flow.

Do not “fix” things solely because OPTIONS is absent. Determine whether the request requires preflight and inspect the full Network log.

## 5. Headers that must be checked

| Header | Source | Role |
| --- | --- | --- |
| `Origin` | Browser request | Origin of the script making the request |
| `Access-Control-Request-Method` | OPTIONS request | Intended actual HTTP method |
| `Access-Control-Request-Headers` | OPTIONS request | Request headers needing approval |
| `Access-Control-Allow-Origin` | Response | Origin permitted to share the response |
| `Access-Control-Allow-Methods` | OPTIONS response | List of allowed methods |
| `Access-Control-Allow-Headers` | OPTIONS response | List of allowed request headers |
| `Access-Control-Allow-Credentials` | Response | Whether credentialed requests are allowed |
| `Access-Control-Expose-Headers` | Response | Response headers JS may read beyond safelisted ones |
| `Access-Control-Max-Age` | OPTIONS response | Preflight cache duration |
| `Vary: Origin` | Response | Helps caches distinguish responses by Origin |

**Note:** Method/header values are case-insensitive under relevant HTTP rules. Browsers may list header names in lowercase, while Spring returns them with different casing. Do not write rigid assertions on arbitrary ordering unless required by your system.

A response with `HTTP 200` yet missing a valid `Access-Control-Allow-Origin` can still be blocked by the browser. To diagnose, examine **both request headers, response headers, browser console, and origin URLs**.

## 6. Complete demo in Java 17 + Spring Boot

The project has three independently running components:

~~~text
Allowed frontend:          http://127.0.0.1:5500
Spring Boot backend:       http://127.0.0.1:8080
Disallowed frontend:       http://127.0.0.1:5501
~~~

The backend accepts CORS only from port **5500**. The frontend on port **5501** serves the exact same HTML yet is restricted by the origin allowlist.

Endpoints:

- `GET /api/public`: public JSON, simple request.
- `GET /api/stats`: count of POSTs actually processed.
- `POST /api/echo`: accepts JSON, increments counter, and returns an exposable header.
- `OPTIONS /api/echo`: preflight automatically sent by the browser when POST has JSON/custom headers.

**Safety scope:** This demo has no login/cookies; the POST endpoint only increments an in-memory counter. Security disables CSRF **in this stateless demo API with no ambient credentials** to isolate CORS. Never copy this exact setup to an API with cookie login and real data.

### 6.1. Project structure

~~~text
cors-browser-lab/
  pom.xml
  PreviewServer.java
  frontend/
    index.html
  src/main/java/com/example/corslab/
    CorsBrowserLabApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/corslab/
    CorsBrowserLabTests.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>cors-browser-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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

### 6.3. CorsBrowserLabApplication.java

~~~java
package com.example.corslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsBrowserLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsBrowserLabApplication.class, args);
    }
}
~~~

### 6.4. SecurityConfig.java

~~~java
package com.example.corslab;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://127.0.0.1:5500"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-Demo-Tag"));
        cors.setExposedHeaders(List.of("X-Demo-Result"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(0L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").permitAll()
                .anyRequest().denyAll());

        return http.build();
    }
}
~~~

Explanation:

- `UrlBasedCorsConfigurationSource` configures CORS for `/api/**` and is used by Spring Security via `.cors(...)`.
- Only origin `http://127.0.0.1:5500` is permitted, with no wildcards.
- Methods include GET, POST, OPTIONS; permitted custom headers include `Content-Type` and `X-Demo-Tag`.
- Sending `X-Not-Allowed` causes preflight rejection.
- `Access-Control-Expose-Headers` allows JS to read response header `X-Demo-Result`.
- `setAllowCredentials(false)` means the demo grants no credentialed CORS access.
- `setMaxAge(0L)` reduces caching during the exercise so preflight is easier to observe.
- `STATELESS` avoids using sessions to restore Spring Security authentication.
- `csrf(AbstractHttpConfigurer::disable)` is **deliberate in a lab with no cookie authentication and no real data**, not a general recommendation.
- `requestMatchers("/api/**").permitAll()` lets the lab isolate the CORS variable; production requires separate authentication/authorization.

### 6.5. DemoController.java

~~~java
package com.example.corslab;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final AtomicInteger posts = new AtomicInteger();

    public record EchoInput(String message) {}

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "public");
    }

    @GetMapping("/stats")
    public Map<String, Integer> stats() {
        return Map.of("acceptedPosts", posts.get());
    }

    @PostMapping("/echo")
    public ResponseEntity<Map<String, Object>> echo(
            @RequestBody EchoInput request,
            @RequestHeader(value = "X-Demo-Tag",
                           defaultValue = "none") String tag
    ) {
        int current = posts.incrementAndGet();
        return ResponseEntity.ok()
            .header("X-Demo-Result", "accepted")
            .body(Map.of(
                "message", request.message(),
                "tag", tag,
                "acceptedPosts", current
            ));
    }

    int currentAcceptedPosts() {
        return posts.get();
    }
}
~~~

The controller only mutates in `@PostMapping`, never when the browser asks OPTIONS. The counter lets us verify: a failed preflight **prevents POST from executing**. However, note that a **simple POST** can reach the server before the browser blocks the response; CORS is not a mechanism preventing all kinds of side effects.

### 6.6. application.properties

~~~properties
server.address=127.0.0.1
server.port=8080
~~~

The API binds only to loopback in the lab, preventing accidental exposure to external networks. Use the exact hostname `127.0.0.1` in frontend/browser so the origin matches the configuration.

### 6.7. PreviewServer.java — pure Java 17 frontend server

Place at the root `cors-browser-lab/PreviewServer.java`:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class PreviewServer {
    public static void main(String[] args) throws IOException {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 5500;
        byte[] html = Files.readAllBytes(Path.of("frontend/index.html"));

        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", port), 0
        );

        server.createContext("/", exchange -> {
            exchange.getResponseHeaders().set(
                "Content-Type", "text/html; charset=UTF-8"
            );
            exchange.getResponseHeaders().set(
                "Cache-Control", "no-store"
            );

            exchange.sendResponseHeaders(200, html.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(html);
            }
        });

        server.start();
        System.out.println("Frontend origin: http://127.0.0.1:" + port);
    }
}
~~~

Run from the project root directory:

~~~bash
java --add-modules jdk.httpserver PreviewServer.java 5500
~~~

Expected stdout:

~~~text
Frontend origin: http://127.0.0.1:5500
~~~

`PreviewServer` uses the `jdk.httpserver` module built into JDK 17. Neither Node nor Python is required. It merely serves a single static HTML file on loopback and is **not a production web server**.

Do not open the frontend via a `file://` path because it can produce an opaque origin/`Origin: null` quite different from the exercise.

### 6.8. frontend/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CORS browser lab</title>
  <style>
    body { font: 16px/1.5 system-ui, sans-serif;
           max-width: 850px; margin: 3rem auto; padding: 0 1rem; }
    button { margin: .3rem; padding: .65rem 1rem; cursor: pointer; }
    pre { white-space: pre-wrap; word-break: break-word;
          background: #eee; padding: 1rem; min-height: 150px; }
  </style>
</head>
<body>
  <h1>CORS browser test</h1>
  <p>Frontend origin: <strong id="origin"></strong></p>
  <p>Backend URL: http://127.0.0.1:8080</p>

  <button id="simple">1. Simple GET</button>
  <button id="allowed">2. Allowed JSON POST</button>
  <button id="blocked">3. Blocked header POST</button>
  <button id="credentials">4. Credentialed GET</button>
  <button id="stats">5. Read POST counter</button>

  <pre id="log"></pre>

  <script>
    const api = "http://127.0.0.1:8080";
    const log = document.getElementById("log");
    document.getElementById("origin").textContent = location.origin;

    function line(message) {
      log.textContent += message + "\n";
    }

    async function run(label, action) {
      line("\n" + label);
      try {
        const response = await action();
        line("HTTP available to JS: " + response.status);
        line("X-Demo-Result: " +
            response.headers.get("X-Demo-Result"));
        line("Body: " + await response.text());
      } catch (error) {
        line("Fetch error: " + error.name + ": " + error.message);
        line("Inspect DevTools Console and Network for CORS details.");
      }
    }

    document.getElementById("simple").onclick = () =>
      run("Simple GET", () => fetch(api + "/api/public"));

    document.getElementById("allowed").onclick = () =>
      run("Allowed JSON POST", () => fetch(api + "/api/echo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Demo-Tag": "browser"
        },
        body: JSON.stringify({ message: "hello from browser" })
      }));

    document.getElementById("blocked").onclick = () =>
      run("Denied header preflight", () => fetch(api + "/api/echo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Not-Allowed": "test"
        },
        body: JSON.stringify({ message: "should not be posted" })
      }));

    document.getElementById("credentials").onclick = () =>
      run("Credentialed GET", () => fetch(api + "/api/public", {
        credentials: "include"
      }));

    document.getElementById("stats").onclick = () =>
      run("Read counter", () => fetch(api + "/api/stats"));
  </script>
</body>
</html>
~~~

This JavaScript actually executes in a browser, sends `fetch` requests, and obeys CORS. The log displays responses **only when JavaScript is allowed by the browser to access them**; when blocked, the message may be `TypeError: Failed to fetch`, while DevTools Network still shows the HTTP requests that occurred.

### 6.9. Running the full lab

Open terminals in the project directory.

**Terminal 1 — backend:**

~~~bash
mvn clean test
mvn spring-boot:run
~~~

**Terminal 2 — allowed frontend:**

~~~bash
java --add-modules jdk.httpserver PreviewServer.java 5500
~~~

Open page:

~~~text
http://127.0.0.1:5500
~~~

**Terminal 3 — disallowed frontend origin (optional):**

~~~bash
java --add-modules jdk.httpserver PreviewServer.java 5501
~~~

Open page:

~~~text
http://127.0.0.1:5501
~~~

Both frontends serve the **exact same HTML file**. The only difference is port/origin, making it easy to isolate the CORS cause. Stop old processes if ports are already in use. Never edit the backend allowlist while measuring if your goal is comparing pass vs fail.

## 7. Expected results and how to observe in the browser

| Button / test | Frontend origin | Preflight? | Expected behavior | Did actual POST happen? |
| --- | --- | --- | --- | --- |
| Simple GET | 5500 | Usually no | JS reads 200/JSON | No |
| Allowed JSON POST | 5500 | Yes | OPTIONS passes, POST 200 | Yes, counter increments |
| Blocked header POST | 5500 | Yes | OPTIONS rejected, JS reports CORS | No |
| Credentialed GET | 5500 | Usually no | JS blocked due to missing ACA-Credentials | No, only GET may have arrived |
| Simple GET | 5501 | Usually no | JS blocked due to disallowed origin | No, GET may have arrived |
| JSON POST | 5501 | Yes | Preflight disallows origin | No |

**Note:** The HTTP status returned by Spring on a rejected request may be 403. In many other systems, a server might return 200 with no CORS headers; the browser still blocks JS. Do not rely on status 200/403 alone as the sole indicator.

### 7.1. Open DevTools

1. Visit `http://127.0.0.1:5500`.
2. Press `F12`, open **Network** and **Console**.
3. Enable Preserve log if redirects occur; ensure request filters do not hide OPTIONS.
4. Click **Simple GET**; locate GET /api/public.
5. Click **Allowed JSON POST**; locate OPTIONS first, POST second.
6. Click **Blocked header POST**; compare OPTIONS with the previous case.
7. Click **Read POST counter** to verify side effects.
8. Open the same page on port 5501 and repeat.
9. Inspect both request headers and response headers, not just red error lines.

### 7.2. Case A: simple GET from valid origin

Expected Network:

~~~http
GET /api/public HTTP/1.1
Origin: http://127.0.0.1:5500
~~~

Response contains:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://127.0.0.1:5500
~~~

JS reads JSON:

~~~json
{"status":"public"}
~~~

These are results **expected from the code**, not outputs executed inside this document. Seeing no OPTIONS is normal because this GET requires no preflight.

### 7.3. Case B: JSON POST with an allowed header

The browser first sends:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-demo-tag
~~~

The backend confirms origin, method, and header. The browser then sends:

~~~http
POST /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Content-Type: application/json
X-Demo-Tag: browser

{"message":"hello from browser"}
~~~

Expected response 200 with `X-Demo-Result: accepted` and JSON containing `acceptedPosts`. If the browser reads `X-Demo-Result` via `response.headers.get(...)`, that is because the backend added `Access-Control-Expose-Headers: X-Demo-Result`.

### 7.4. Case C: disallowed header

The `Blocked header POST` button makes the browser request:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-not-allowed
~~~

`X-Not-Allowed` is not in the allowlist. The Spring CORS processor rejects the preflight. In Network, you may see HTTP 403 on OPTIONS, with **no subsequent actual POST**. The counter does not increment.

This outcome differs from a simple GET blocked **only at the response-reading step**, where the backend may have already processed the GET.

### 7.5. Case D: forbidden origin

Open the HTML from `http://127.0.0.1:5501` and click Simple GET. The origin is now 5501. Spring's CORS config allows only 5500; the browser refuses to let the script read the response. Do not change the backend URL, because the goal of the exercise is changing only the source page origin.

### 7.6. Case E: credentials include

The `Credentialed GET` button runs:

~~~javascript
fetch("http://127.0.0.1:8080/api/public", {
  credentials: "include"
});
~~~

The browser requires the response to be compatible with credentials mode. Because the demo backend sets `allowCredentials(false)` and omits `Access-Control-Allow-Credentials: true`, JavaScript is blocked. This occurs **even though the server has no user cookies in the demo**: fetch credentials mode still governs CORS validation.

A simple GET can actually reach the backend and its response appear in Network, yet JavaScript cannot read it. This is not a server error intentionally hiding secrets, but the policy configured by the lab.

## 8. Why is curl still useful yet insufficient?

### 8.1. Curl sends no Origin by default

~~~bash
curl -i http://127.0.0.1:8080/api/public
~~~

Expect 200 and JSON. This **does not test** whether a browser from origin 5501 can read the response.

### 8.2. Curl sending a valid Origin

~~~bash
curl -i \
  -H "Origin: http://127.0.0.1:5500" \
  http://127.0.0.1:8080/api/public
~~~

Expect `Access-Control-Allow-Origin` for 5500. Curl can inspect server-side CORS headers, yet cannot test browser preflight caching, credentials mode, CSP, cookies, or JS response readability.

### 8.3. Curl simulating preflight

~~~bash
curl -i -X OPTIONS \
  -H "Origin: http://127.0.0.1:5500" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-demo-tag" \
  http://127.0.0.1:8080/api/echo
~~~

Expect preflight to be accepted. Try replacing `x-demo-tag` with `x-not-allowed` to see the server reject it per configuration.

### 8.4. Curl sending POST without preflight

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "X-Demo-Tag: cli" \
  -d '{"message":"sent by curl"}' \
  http://127.0.0.1:8080/api/echo
~~~

Expect POST 200 and counter increment. Curl does not ask permission via OPTIONS first; it sends POST immediately. Therefore do not conclude “curl can POST so the browser must be able to POST”.

### 8.5. Curl with a disallowed Origin

~~~bash
curl -i \
  -H "Origin: http://127.0.0.1:5501" \
  http://127.0.0.1:8080/api/public
~~~

The Spring CORS processor in the lab can actively return 403. Yet another server might return 200 without ACAO and curl would still print the body. Browsers enforce CORS checks regardless of how a server chooses its status code.

**Conclusion:** Curl answers “What does the HTTP server reply when I send these headers?”. A browser additionally answers “Can JavaScript from the current origin send the actual request and read the response?”.

## 9. MockMvc: verifying Spring Security CORS policy

MockMvc is great for verifying that the backend returns the right ACA headers and rejects invalid preflights, yet it **runs no browser engine** and enforces no JS response exposure policy.

Create file `src/test/java/com/example/corslab/CorsBrowserLabTests.java`:

~~~java
package com.example.corslab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsBrowserLabTests {

    private static final String ALLOWED =
        "http://127.0.0.1:5500";

    private static final String DENIED =
        "http://127.0.0.1:5501";

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoController controller;

    @Test
    void allowedGetIncludesCorsHeader() throws Exception {
        mvc.perform(get("/api/public").header("Origin", ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", ALLOWED))
            .andExpect(jsonPath("$.status").value("public"));
    }

    @Test
    void allowedPreflightSucceeds() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-demo-tag"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", ALLOWED))
            .andExpect(header().exists("Access-Control-Allow-Methods"))
            .andExpect(header().exists("Access-Control-Allow-Headers"));
    }

    @Test
    void unlistedHeaderPreflightIsRejected() throws Exception {
        int before = controller.currentAcceptedPosts();

        mvc.perform(options("/api/echo")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-not-allowed"))
            .andExpect(status().isForbidden());

        assertEquals(before, controller.currentAcceptedPosts());
    }

    @Test
    void deniedOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", DENIED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedActualPostReturnsCorsAndExposedHeader()
            throws Exception {
        mvc.perform(post("/api/echo")
                .header("Origin", ALLOWED)
                .header("X-Demo-Tag", "test")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", ALLOWED))
            .andExpect(header().exists(
                "Access-Control-Expose-Headers"))
            .andExpect(header().string("X-Demo-Result", "accepted"))
            .andExpect(jsonPath("$.message").value("hello"));
    }

    @Test
    void requestWithoutOriginReachesApi() throws Exception {
        mvc.perform(post("/api/echo")
                .header("X-Demo-Tag", "cli")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"from curl\"}"))
            .andExpect(status().isOk());
    }
}
~~~

Run `mvn clean test`. These tests check server-side policy:

- Origin 5500 receives ACAO.
- POST preflight with allowed headers succeeds.
- Unknown header is blocked; counter does not increment.
- Origin 5501 is blocked.
- Actual POST from valid origin carries CORS headers and body.
- Request without Origin can still reach the public API.

**Limitations:** MockMvc does not prove whether a browser generates preflight, auto-sends cookies per SameSite, enforces CSP, or exposes response headers to JavaScript. Thus a complete QA strategy requires **MockMvc + browser E2E/DevTools**, never relying on only one of the two.

The code is a knowledge example with complete files/imports/dependencies; **no actual Maven run output is recorded in this lesson**, so do not claim `BUILD SUCCESS` unless you execute it yourself.

## 10. Credentialed CORS and cookies: do not use wildcards

For apps with session-cookie login, a cross-origin frontend may use:

~~~javascript
fetch("https://api.example.test/me", {
  credentials: "include"
});
~~~

The backend must configure explicit origins and allow credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Wrong when the browser requests credentialed access:**

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

The browser will not let JavaScript use the response because wildcard origins are incompatible with credentialed CORS. Spring Framework also forbids using `allowedOrigins("*")` directly with `allowCredentials(true)`. You can use `allowedOriginPatterns` for trusted patterns, yet must never turn it into an unchecked “echo every Origin”.

Illustrative fragment (do not use verbatim with the public lab):

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.test"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
cors.setAllowCredentials(true);
~~~

Passing CORS is **not enough** for cookie login to work:

- The browser must send cookies when `credentials` allows.
- Cookies need proper `Domain`/`Path`/`Secure`/`SameSite`, and may be blocked by third-party cookie restrictions.
- The server session must still be valid; `SecurityContext`/`Authentication` must be restored.
- POST/PUT/DELETE with cookie authentication **still require CSRF defense** per threat model.
- The user must have permission on real data, not merely come from an allowed origin.
- Preflight normally lacks session cookies; do not block it with HTTP authentication.
- Login redirects/preflight redirects can cause errors; inspect Network details.

**CORS is not a CSRF defense:** Some simple requests can reach the server before the browser blocks reading the response. The backend must protect side effects with corresponding authentication, authorization, CSRF, and business rules.

## 11. A CORS failure is not always a CORS config problem

When the browser Console reports a network or CORS error, check in order:

1. **What is the real origin?** Compare full scheme/hostname/port; `localhost` and `127.0.0.1` are not the same host.
2. **Is the backend running?** DNS, port, TLS certificate, firewall, proxy, or HTTP 5xx can make `fetch` reject.
3. **Is an HTTPS page calling an HTTP API?** The browser may block mixed content before CORS finishes.
4. **Is there a CSP `connect-src`?** CSP can block fetches to a URL even if the server returns proper ACAO.
5. **Does the request have a preflight?** OPTIONS returning 401/403 or redirecting may be the source.
6. **Which method and request headers did preflight ask for?** Compare against the real allowlist.
7. **Does the response have ACAO matching the origin?** Do not use the backend URL as the expected ACAO value.
8. **Is credentials mode used?** Check ACA-Credentials and wildcard origins.
9. **Are cookies actually sent?** `SameSite`, `Secure`, and browser privacy policies can affect this.
10. **Are there redirects/login/gateway layers?** Redirects from OPTIONS or API responses lacking ACA headers can fail.
11. **Is there a reverse proxy/CDN?** Stripped headers, responses cached for the wrong origin, missing `Vary: Origin`.
12. **Was the actual request even sent?** An OPTIONS failure differs from a simple GET/POST response rejection.
13. **Is there a Service Worker or extension?** Those layers can intercept/modify requests.
14. **Did HTTP 401/403 come from authz/CSRF?** Do not blame every 403 on CORS.
15. **Did the frontend use `mode: "no-cors"`?** Opaque responses prevent JS from reading JSON and are not a proper CORS fix.

Common example scenario:

~~~text
Backend allows: http://127.0.0.1:5500
Browser opens:  http://localhost:5500

=> Origin DOES NOT MATCH, even on the same machine.
~~~

Or:

~~~text
Browser:
  Origin: https://app.example.test
  Request headers: Authorization, Content-Type

Backend:
  AllowedHeaders: Content-Type

=> Preflight requesting Authorization is rejected.
~~~

Fix **the exact config matching real needs** rather than opening `*` indiscriminately or disabling Spring Security entirely.

## 12. Diagnostic clues by layer

| Symptom | Layer to inspect first | Hint |
| --- | --- | --- |
| Curl GET 200, browser reports CORS | CORS/Origin | ACAO and actual origin |
| OPTIONS 401 | Security filter ordering | `.cors(...)` and authentication on preflight |
| OPTIONS 403 | CORS allowlist | Origin, Method, Headers |
| Browser POST never appears | Preflight | OPTIONS failed or another browser block |
| GET Network 200 yet JS TypeError | Browser response exposure | ACAO, ACA-Credentials, CSP |
| JS reads JSON yet misses custom response header | Exposed headers | `Access-Control-Expose-Headers` |
| CORS passes yet API returns 401 | Authentication | Cookie/bearer/session |
| CORS passes yet API returns 403 | Authorization/CSRF | Role, policy, CSRF token |
| Browser sends cookie yet server sees anonymous | Cookie/session | SameSite, session expiration, store |
| Localhost test works yet production fails | Proxy/TLS/allowlist | Scheme, host, forwarded headers, CDN |
| Sometimes OPTIONS appears, sometimes not | Preflight caching | `Access-Control-Max-Age` and browser cache |
| JS receives only an opaque response | Fetch mode | Never use `no-cors` to fetch JSON |

### 12.1. When the actual request ran yet the browser blocked the response

A dangerous mental trap is:

> “If the browser reported CORS, the backend could not have written data.”

False. CORS primarily protects JS's ability to read responses. With **simple requests**, the browser can send the actual request, the backend executes the mutation, and then the browser blocks reading the response. Therefore the backend must still enforce CSRF protection and authorization for state-changing actions.

In the lab, JSON POST is **preflighted**: when preflight fails, the browser does not send POST. That is a property of **this specific test case**, not a guarantee of CORS for all requests.

### 12.2. Error responses also need proper CORS

If an allowed frontend calls the API and the backend returns 400/401/403/404/500, error responses should also include matching CORS headers so JS can read the status/message. If error-handling middleware drops ACAO, the frontend may see only a CORS error instead of the underlying error JSON, making debugging hard.

Do not abuse CORS headers to “mask” 401/403 errors. Ensure CORS policy is applied consistently while the server still rejects unauthenticated/unauthorized requests.

## 13. QA matrix for real projects

| Group | Test case | What to observe |
| --- | --- | --- |
| Origin | Allowed origin | JS reads response |
| Origin | Unknown origin/different port | JS cannot read response |
| Origin | HTTP vs HTTPS | Different schemes are not confused |
| Preflight | JSON POST + custom header | OPTIONS precedes POST |
| Preflight | Forbidden header | POST does not run when OPTIONS fails |
| Preflight | Forbidden method | Actual request not sent after preflight rejection |
| Simple request | GET without custom headers | May need no OPTIONS |
| Credentials | include + ACA-Credentials true + specific origin | Browser reads response when cookie policy permits |
| Credentials | include + wildcard ACAO | Browser blocks |
| Cookies | SameSite/Secure/third-party policy | Cookies sent or blocked appropriately |
| CSRF | Session-cookie POST missing CSRF | Backend rejects mutation |
| Authn/Authz | User lacks permission | Passing CORS still yields 401/403 |
| Expose | Custom response header | JS can read when exposed |
| Error | 400/401/403/500 | Frontend reads status/error per policy |
| Proxy | CDN caches multiple origins | Does not mix responses across Origins |
| Browser | Chrome/Firefox/Edge | Appropriate cross-origin behavior |
| Cache | Preflight maxAge | Do not mistake cached preflight for missing config |
| Side effects | Blocked preflight vs blocked response | Know whether server processed the operation |

**Minimum acceptance criteria:** A browser from an allowed origin can call the API and read the expected body/headers; a browser from a disallowed origin is restricted; preflight runs when needed; credentials/CSRF/authz are not unintentionally opened; backend side effects are verified.

## 14. Mistakes to avoid

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| “curl returned 200 so CORS is OK” | Curl does not enforce browser policy | Use browser DevTools/E2E |
| “Every POST has OPTIONS” | Simple POSTs may skip preflight | Check method/content-type/headers |
| “Seeing no OPTIONS means it's broken” | Simple request or cached preflight | Check Network/cache |
| “CORS error means the request never entered the server” | Simple requests may have been processed | Check server state/logs |
| Setting ACAO `*` with credentials | Browsers reject it | Explicit origin allowlist |
| Echoing every `Origin` unchecked | Can expose sensitive data | Trusted allowlist |
| Disabling Spring Security because OPTIONS 401 | Opens vulnerabilities | Integrate CORS in proper order |
| Disabling CSRF because browser reports CORS | CSRF and CORS are distinct | Keep CSRF when using cookies |
| `fetch` `mode: "no-cors"` | Opaque response, cannot read JSON | Configure server CORS |
| Testing only Postman/MockMvc | Misses browser enforcement | Add browser E2E |
| Serving frontend via `file://` | Opaque Origin differs from lab | Run an HTTP server |
| Assuming localhost = 127.0.0.1 | Different hostnames | Align URLs/allowlist |
| Treating CORS as user permission | CORS does not authenticate users | Separate authn/authz |
| Forgetting `Vary: Origin` with dynamic origins | Shared caches mix responses | Standard cache/header policy |

## 15. Self-check exercises

**Exercise 1.** Frontend opens at `http://127.0.0.1:5501`; backend allows `http://127.0.0.1:5500`. Why does the browser block GET even though curl gets 200?

**Exercise 2.** Browser sends a JSON POST with `X-Demo-Tag`. List three important request/response headers in preflight and explain when the actual POST is sent.

**Exercise 3.** When adding `X-Not-Allowed`, the backend counter does not increment. What observation proves preflight blocked the POST?

**Exercise 4.** Browser sends a simple GET and no OPTIONS appears. Does this prove CORS is disabled?

**Exercise 5.** A login page uses cookie sessions, frontend sets `credentials: "include"`, server returns `Access-Control-Allow-Origin: *`. What will the browser do? Which config should be fixed?

**Exercise 6.** The API returns the right `Access-Control-Allow-Origin`, yet JavaScript cannot read `X-Demo-Result` even though Network shows it. Which header must be added?

**Exercise 7.** A simple POST executed a mutation yet the browser reported CORS. Why does CORS not replace CSRF protection?

**Exercise 8.** Preflight gets 401 from Spring Security even though the API URL requires login. Why must login cookies not be demanded inside preflight?

**Exercise 9.** Distinguish curl with an Origin header, MockMvc CORS tests, and browser E2E. What does each verify?

**Exercise 10.** Design 5 test cases for an SPA using cookie sessions, a cross-origin API, CSRF tokens, and multiple error responses.

**Suggested answers:**

1. Port is part of the origin; JavaScript from 5501 is not in the allowlist.
2. OPTIONS carries Origin, Access-Control-Request-Method, Access-Control-Request-Headers; the browser sends POST only after permission is granted.
3. Network shows a rejected OPTIONS with no subsequent actual POST; the counter stays unchanged.
4. No, simple GETs usually need no preflight; preflight also has caching.
5. Browsers reject wildcards for credentialed CORS; use a specific origin and `Access-Control-Allow-Credentials: true`, and verify cookie policy.
6. `Access-Control-Expose-Headers: X-Demo-Result`.
7. The browser can send simple requests before blocking the response; the backend must guard side effects with CSRF/authz.
8. OPTIONS asks CORS permission before the actual request and normally sends no session cookie; integrate CORS properly before auth.
9. Curl/MockMvc test server behavior; browser E2E tests SOP/preflight/cookies/response exposure.
10. Include allowed/disallowed origin, credentials include, missing/valid CSRF, permission 403, and error response CORS.

## 16. Conclusion

**Thorough CORS testing must include a real browser.** Curl checks APIs and headers effectively, yet does not reproduce Same-Origin Policy, automatic preflight, credentials mode, cookie restrictions, or whether JavaScript is allowed to read responses.

Effective workflow:

1. Use MockMvc/curl to verify backend CORS policy.
2. Serve the frontend via an HTTP server at a **specific origin**.
3. Open DevTools to inspect **OPTIONS and actual requests**.
4. Compare allowed and disallowed origins.
5. Check credentials mode/cookies/redirects/CSRF if login is present.
6. Verify server-side side effects rather than inferring solely from JS exceptions.
7. Keep authentication and authorization independent of CORS.

### Official references

- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [MDN — CORS wildcard and credentials error](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials)
- [MDN — Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials)
- [Spring Security 6.5 — CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Framework — Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
