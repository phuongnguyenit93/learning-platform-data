# Same-Origin Policy and the Scope That CORS Addresses

> **Context:** Spring Security application on the **Servlet stack**, Spring Boot 3.x / Spring Security 6.x, Java 17+. This lesson clarifies the browser's protection mechanism, how CORS enables controlled response sharing, how to configure CORS in the right place in Spring Security, and the security boundaries that CORS does not replace.

## 1. Learning Objectives

After this lesson, you will be able to:

- Determine whether two URLs are **same-origin or cross-origin** based on scheme, hostname, and port; distinguish `same-origin` from `same-site`.
- Explain why JavaScript from one origin is normally **not allowed to read** the response from another origin even though the request may have been sent.
- Describe the roles of the `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials` headers, as well as the two steps: **preflight** and **actual request**.
- Distinguish CORS from authentication, authorization, CSRF, resource loading restrictions, and server-to-server access control.
- Configure CORS for a Servlet API with a `SecurityFilterChain` so that preflight is handled before authentication filters, then verify with a browser and `curl`.

## 2. Same-Origin Policy (SOP): What Is the Browser Restricting?

An **origin** is the tuple **(scheme, host, port)** of a URL. Path, query, and fragment do not contribute to determining the origin. For HTTP(S) schemes, the default port is normalized during comparison.

Suppose a page is running at `http://localhost:5173/index.html`:

| Target URL | Compared to the page | Reason |
|---|---|---|
| `http://localhost:5173/api/data` | Same origin | Same scheme, host, and port |
| `http://localhost:5173/other/path?x=1` | Same origin | Different path/query does not change the origin |
| `http://localhost:8080/api/data` | Cross origin | Different port |
| `https://localhost:5173/api/data` | Cross origin | Different scheme |
| `http://127.0.0.1:5173/api/data` | Cross origin | `127.0.0.1` and `localhost` are two different hosts |
| `http://api.localhost:5173/api/data` | Cross origin | Different subdomain |

The **Same-Origin Policy** is a set of rules enforced by the **user agent (browser)** so that code from one origin cannot arbitrarily access the data, DOM, and state of another origin. For example, a script at `https://shop.example.test` cannot freely read the DOM inside a login iframe of `https://bank.example.test`. With `fetch` / `XMLHttpRequest`, JavaScript cannot inspect the response body/headers of another origin unless CORS rules are satisfied.

Common point of confusion: **SOP does not mean every cross-origin request is blocked from being sent.** Browsers have long permitted various cross-origin loading/sending behaviors, such as:

- `<img src="https://...">` loads an image from another origin; the page normally **cannot read the pixels** of a cross-origin image via canvas if CORS conditions are missing.
- `<script src="https://...">` as a classic script can load from another source under script-loading rules; JavaScript modules and many modern APIs have their own CORS requirements.
- An HTML form can send a request to another origin. This is one reason **CSRF** must be considered.
- `fetch` can issue a request to another origin. If the server does not allow sharing via CORS, the script is prevented from reading the response; some requests may already have taken effect on the server before the script receives the error.

It is also necessary to distinguish **same-site** (a concept involving registrable domain and scheme, especially in the `SameSite` cookie policy) from **same-origin** (which also requires the port to match). Two applications `https://app.example.test` and `https://api.example.test` may be same-site yet still **cross-origin**, so JavaScript reading the API must consider CORS. Conversely, a same-origin API does not need CORS enabled merely because the path differs.

## 3. What Does CORS Solve, and What Does It Not Solve?

**Cross-Origin Resource Sharing (CORS)** is a mechanism for the **target server to declare to the browser** which origins are allowed to access cross-origin responses via CORS-checked APIs such as `fetch`. The server emits CORS headers; the **browser** checks them and decides whether to let JavaScript see the response.

Simple flow:

```text
Page: http://localhost:5173           API: http://localhost:8080
          |                                     |
          | GET /api/public                     |
          | Origin: http://localhost:5173 ----> |
          |                                     |
          | <---- 200 OK                        |
          |       Access-Control-Allow-Origin: |
          |         http://localhost:5173       |
          |       {"message":"hello"}           |
          |                                     |
  Browser checks policy against origin
          |
  Allows JavaScript to read JSON
```

If the server does not send matching headers, the browser reports a CORS error / network-level failure to the `fetch` code, even though the server may have processed the request and returned an HTTP response. Do not conclude "the request never reached the server" solely from a Console message: you must distinguish the **actual request** from the **preflight** (Section 4).

CORS boundaries:

| What CORS can support | What CORS does not do |
|---|---|
| Let JavaScript from an approved origin read an API response | Does not authenticate the user or prove the client is trustworthy |
| Restrict origins, methods, and headers usable in a CORS request | Does not replace Spring Security authorization rules |
| Pre-check certain requests via preflight | Does not stop all cross-origin form/simple requests from being sent |
| Limit how the browser exposes responses to cross-origin JavaScript | Does not block `curl`, Postman, mobile apps, or server-to-server calls |
| Allow conditional response sharing with credentials | Does not by itself prevent CSRF or XSS |
| Clarify the contract between frontend and backend on different origins | Does not let JavaScript bypass SOP to read a cross-origin iframe's DOM |

**CORS is not a mechanism to protect resources from arbitrary clients.** A non-browser program can set the `Origin` header arbitrarily or omit it altogether. Therefore, the backend must still authenticate tokens/sessions, check permissions on every endpoint, and protect sensitive data. Merely whitelisting the origin of an "official" frontend does not turn a public API into a private API.

## 4. Two Types of CORS Requests: Direct and Preflight

### 4.1. Requests That Do Not Require Preflight

The browser may send the **actual request** directly for requests that satisfy "CORS-safelisted" conditions, typically `GET`, `HEAD`, or certain `POST` requests with headers and `Content-Type` belonging to the standardized safe set (for example `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`, along with additional specification limits). The response must still be approved under CORS before JavaScript can read it.

Example:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Accept: */*
```

Server responds:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: application/json

{"message":"hello"}
```

The response is exposed to JavaScript because the returned origin matches `Origin`. Not having a preflight also **does not mean** the browser skips CORS.

### 4.2. Requests Requiring Preflight (OPTIONS)

The browser typically sends a preflight when a cross-origin request uses methods like `PUT`, `PATCH`, `DELETE`, custom headers like `X-Client-Version`, `Authorization`, or `Content-Type: application/json`. The `OPTIONS` request announces the **method and headers of the actual request** to ask whether the server allows them:

```http
OPTIONS /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-client-version
```

A valid preflight response might look like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: x-client-version
Access-Control-Max-Age: 600
```

If approved, the browser proceeds to send the **actual GET** carrying `X-Client-Version` and checks CORS on the **actual response**. Preflight does not by itself authorize the user and does not guarantee the actual request will succeed: the API may still return 401, 403, or a business error.

If the preflight fails, the browser **does not send the corresponding actual request**. Browsers normally do not send cookies or authentication credentials in a preflight; therefore the backend must not require the preflight to have a logged-in session in order to return CORS headers. Cookies or credentials for the **actual request** are a separate topic in Section 5.

Noteworthy cases:

- `GET` carrying an `Authorization` header typically requires preflight because this header is not in the safelisted group.
- `POST` with `Content-Type: application/json` typically requires preflight; `POST` with `text/plain` may not, yet it can still cause state changes on the server.
- `credentials: "include"` in `fetch` **does not by itself** turn every request into a preflight. Whether preflight is required depends on the method, headers, and conditions in the CORS specification.
- The browser may cache the **preflight result** according to `Access-Control-Max-Age` within browser-enforced limits. Caching a preflight does not mean caching API data or access permissions.

## 5. Meaning of Important CORS Headers

| Header | Direction | Meaning |
|---|---|---|
| `Origin` | Request | Origin where the script/document initiated the request; managed by the browser in a web context |
| `Access-Control-Request-Method` | Preflight request | Method of the intended actual request |
| `Access-Control-Request-Headers` | Preflight request | Names of non-safelisted headers intended to be sent |
| `Access-Control-Allow-Origin` | Response | Origin allowed to read the response; or `*` if valid when credentials are not used |
| `Access-Control-Allow-Methods` | Preflight response | Methods permitted for use |
| `Access-Control-Allow-Headers` | Preflight response | Headers that the actual request is permitted to carry |
| `Access-Control-Allow-Credentials` | Response | `true` if the browser is permitted to expose the response to a request with credentials |
| `Access-Control-Expose-Headers` | Actual response | Additional response headers JavaScript is allowed to read, beyond the safelisted group |
| `Access-Control-Max-Age` | Preflight response | Hint for how long the browser may cache the preflight result |
| `Vary: Origin` | Response/cache | Helps caches distinguish response versions by `Origin` when the allow-origin value varies dynamically |

**Do not use `Access-Control-Allow-Origin: *` for CORS requests with credentials.** When the browser sends a request with `credentials: "include"`, the response needs `Access-Control-Allow-Origin` matching the specific origin along with `Access-Control-Allow-Credentials: true`; a wildcard does not satisfy that requirement.

On the client:

```javascript
fetch("https://api.example.test/me", {
  credentials: "include"
});
```

This configuration asks the browser to include eligible credentials (such as cookies) in the actual request if cookie policy allows. If the frontend and API are cross-site, cookies are also subject to `SameSite`, `Secure`, and third-party cookie policies. **Allowing response sharing via CORS does not by itself force the browser to send cookies, does not create a session, and does not override cookie policies.**

Do not confuse `Access-Control-Allow-Headers` (permitting **request headers**) with `Access-Control-Expose-Headers` (permitting reading additional **response headers**). The `Set-Cookie` header is a forbidden response-header name and does not become readable via `fetch` simply by adding it to exposed headers.

Do not unconditionally reflect every client `Origin` value into `Access-Control-Allow-Origin`. Doing so is nearly equivalent to opening response reading to every website, which is very dangerous if the API accepts credentials. If multiple origins are needed, use an explicit allowlist checking scheme, host, and port. Avoid arbitrarily allowing the `null` origin because many document contexts have an opaque origin represented as `null`.

## 6. Runnable Example: Spring Security Servlet and Frontend on a Different Port

Demo goal: a page at `http://localhost:5173` can read the API `http://localhost:8080/api/public`; a page from another port is not allowed to read it under CORS. The `/api/private` endpoint still requires authentication even though the origin is in the allowlist.

### 6.1. Create the Spring Boot Application

A Gradle project with Java 17+ and the Web MVC and Security starters. Minimal `build.gradle` file:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

File `src/main/java/demo/cors/CorsLessonApplication.java`:

```java
package demo.cors;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CorsLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsLessonApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicData() {
        return Map.of("message", "hello");
    }

    @GetMapping("/api/private")
    public Map<String, String> privateData() {
        return Map.of("message", "private");
    }
}
```

File `src/main/java/demo/cors/WebSecurityConfig.java`:

```java
package demo.cors;

import java.time.Duration;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class WebSecurityConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Must match the exact scheme, host, and port of the frontend.
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of("X-Client-Version"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(Duration.ofMinutes(10));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, CorsConfigurationSource corsSource)
            throws Exception {
        http
            // CORS is processed before the authentication/authorization portion of the chain.
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // Default CSRF is kept as-is; the demo only uses GET.
        return http.build();
    }
}
```

**Why must `http.cors(...)` be configured?** Spring Security has its own filter chain. A preflight `OPTIONS` request normally carries no login cookie/credentials; if it is processed like an API request requiring authentication before CORS runs, it may receive 401/403 without the proper CORS headers. When integrating CORS with Spring Security, the CORS mechanism is placed before the chain's authentication steps so preflight is handled properly.

Intentional limitations chosen for the demo:

- Only the origin `http://localhost:5173`, only the `GET` method, and the custom request header `X-Client-Version` are allowed. `OPTIONS` used for preflight can be handled even though it is not in the method list of the **actual request**.
- `setAllowCredentials(false)` because the public endpoint does not require cross-origin cookie sharing. If cookies/sessions are desired, you must specifically design the CORS, cookie, CSRF, and login policies; do not blindly set `true` without considering those consequences.
- Spring Security requires login for `/api/private`, even when the origin is in the CORS allowlist. Sharing a response via CORS **does not** mean the user is authorized.
- The demo does not disable CSRF. When adding `POST`/`PUT` with session cookies, you must follow the proper CSRF token contract or an appropriate equivalent protection mechanism.

For a project with Gradle Wrapper, run the backend at `localhost:8080`:

```bash
./gradlew bootRun
```

### 6.2. Create a Page on Another Origin

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CORS demo</title>
</head>
<body>
  <button id="load">Fetch API</button>
  <pre id="out"></pre>
  <script>
    document.getElementById("load").addEventListener("click", async () => {
      const out = document.getElementById("out");
      try {
        const response = await fetch("http://localhost:8080/api/public", {
          headers: { "X-Client-Version": "1" },
          credentials: "omit"
        });
        const body = await response.json();
        out.textContent = response.status + " " + JSON.stringify(body);
      } catch (error) {
        out.textContent = "Request/CORS error: " + error.name;
      }
    });
  </script>
</body>
</html>
```

From the `frontend` directory, run a static server (for example if Python 3 is installed):

```bash
python -m http.server 5173
```

Open `http://localhost:5173` and click **Fetch API**. Expected output line:

```text
200 {"message":"hello"}
```

Because the `X-Client-Version` header is not in the CORS-safelisted group, in the browser's Network tab you will usually see an `OPTIONS` request before the `GET` (unless the preflight has already been cached). The browser checks `Access-Control-Allow-Origin` on the response so JavaScript is allowed to read the JSON.

To see the rejection case, serve the same page on `http://localhost:5500` and open it on that port. `Origin` will be `http://localhost:5500`, which is not in the allowlist: preflight is rejected, the actual GET using the custom header will not be sent, and `fetch` does not return JSON to JavaScript. Do not rely on the specific error message text; each browser formats it differently.

### 6.3. Check the Handshake with curl

`curl` is useful to **observe HTTP headers**, but it **does not enforce SOP/CORS itself** like a browser.

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/public
```

Expected status 200, body `{"message":"hello"}`, and `Access-Control-Allow-Origin: http://localhost:5173`.

Send a manual preflight:

```bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-client-version" \
  http://localhost:8080/api/public
```

A successful response is expected to include the appropriate `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers` headers. Status and header casing may vary by version/stack; the correctness criterion is valid CORS values per the protocol.

Try changing `Origin` to `http://localhost:5500`. The backend may return a CORS rejection response, such as 403; the key point is that the browser does not allow a script on port 5500 to read the body under the CORS mechanism. For an ordinary request without an `Origin` header, `curl` can still call the API without browser cross-origin constraints.

Try the endpoint that requires login:

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private
```

Without credentials, Spring Security returns **401 Unauthorized** for HTTP Basic. CORS may let the browser see the status/response if the origin is approved; it **does not** turn 401 into 200.

## 7. Boundaries with Authentication, Authorization, CSRF, and XSS

### Authentication / Authorization

Imagine the frontend is at `https://app.example.test` and the API is at `https://api.example.test`:

1. CORS answers: "Is a script from `app.example.test` allowed to **read** the response from `api.example.test`?"
2. Authentication answers: "Which authenticated user or client made this request?"
3. Authorization answers: "Is that identity allowed to view this data, modify this resource, or perform this operation?"

The three questions are **independent**. An origin approved by CORS can still receive 401 or 403. Conversely, missing CORS headers can cause the browser to block reading a response that the backend validly authenticated and processed.

### CSRF

An external page can cause a victim's browser to send certain requests to a system where a login cookie exists (for example via a form). A state-changing request can execute on the server even when the browser is not allowed to read the response. **Therefore, a CORS whitelist does not by itself prevent CSRF.**

For applications using sessions/cookies, you need a CSRF token for state-changing operations or a properly designed equivalent defense, along with appropriate `SameSite` cookie configuration. Do not configure `csrf.disable()` just to "fix CORS", and do not treat the fact that a request does not need preflight as a sign of safety.

### XSS

If an attacker can inject JavaScript into the allowed origin itself (XSS), that code can access the APIs permitted by that origin's CORS policy, within the scope of existing credentials and permissions. **CORS does not block XSS.** You must prevent injection, escape output, apply CSP, and manage sessions/tokens properly.

### DOM and iframes

CORS primarily serves resource access via CORS-checked requests; it **does not allow** a script from origin A to manipulate the DOM of an iframe from origin B. To exchange data between two cross-origin windows/iframes, use `window.postMessage` with exact checks on `event.origin` and `targetOrigin`. To restrict who may embed a page, see CSP `frame-ancestors` or the corresponding framing policy; that is a separate concern from CORS.

## 8. Applying This in Real-World Spring Security Servlet Applications

- **Identify exact frontend origins** across local, staging, and production environments; a different scheme or port is a different origin. Do not use `*` just to clear Console errors, especially when the API uses credentials.
- **Place CORS before authentication.** With Spring Security 6, use `http.cors(...)` and an appropriate `CorsConfigurationSource` (as in the example), or integrate consistent Spring MVC configuration via the CORS mechanism supported by Spring Security. If there are multiple `SecurityFilterChain` beans, verify which chain matches the actual route.
- **Keep path, method, and header scope minimal.** For example `/api/**` for the frontend instead of accidentally opening the entire application. Avoid configuring multiple `CorsFilter`/`@CrossOrigin`/global sources simultaneously that produce conflicting headers.
- **Do not use an `OPTIONS permitAll` rule as a substitute for CORS handling.** Bypassing authorization only solves part of it: preflight still needs proper response headers and valid origin/method/header allowlists.
- **Design CORS specifically when using credentials.** Specify exact origins, `allowCredentials(true)` if genuinely needed, appropriate cookies, and proper authentication/authorization/CSRF. Do not send tokens or passwords in the query string to avoid preflight.
- **If the response varies `Access-Control-Allow-Origin` by `Origin`**, ensure caches/CDNs respect `Vary: Origin`. CORS libraries usually emit the appropriate `Vary` header automatically; it is still worth verifying in real environments.
- **Need to read custom response headers from JavaScript?** Set `Access-Control-Expose-Headers` for the header names actually needed. This only changes which response headers are readable; it does not affect preflight requests.
- **Do not trust `Origin` as an authenticated identity.** Non-browser clients can easily forge arbitrary headers. Always keep token/session verification and authorization on the API.
- **Check proxies/gateways.** If a gateway already handles CORS, clearly define which layer owns the policy; check for duplicate ACAO, caching, and headers behind the reverse proxy.

## 9. Testing Matrix and Common Pitfalls

| Scenario | What to verify |
|---|---|
| Page and API share the same origin | `fetch` reads the response without enabling cross-origin CORS |
| `http://localhost:5173` calls `GET /api/public` | 200 response + exact allow-origin; JS reads JSON |
| Page at `localhost:5173` calls with `X-Client-Version` | Valid OPTIONS preflight, followed by actual GET execution |
| Page at `localhost:5500` calls the same API | Cannot read; with a custom header, preflight fails and the actual request does not run |
| Unauthenticated `GET /api/private` from a valid origin | Still 401; CORS does not replace authentication |
| Request with credentials | Exact origin required, allow-credentials when needed; cookies and CSRF remain controlled |
| POST with side effects, especially using session cookies | Do not rely on CORS; CSRF and business permissions must be checked |
| `curl` from any host | Can call directly; CORS is not a firewall |
| Proxy/CDN caching responses per origin | Must not wrongly serve an allow-origin header belonging to another origin |
| Browser reports a CORS error | Inspect Network, identify whether it is OPTIONS or actual request, check actual status and response headers |

**Pitfall 1 — "CORS blocks malicious requests from reaching the server."** It is primarily a **browser policy controlling response sharing**. For many requests, the server has already received the request before JavaScript is blocked from reading it.

**Pitfall 2 — "Just open `Access-Control-Allow-Origin: *` and you're done."** This opens non-credentialed response reading to every origin where applied; and it cannot be used for CORS responses with credentials.

**Pitfall 3 — "Preflight OPTIONS is a business API request."** OPTIONS asks for permission to use a method/header and normally carries no login credentials; do not require it to have a valid session, and do not confuse the preflight result with business authorization.

**Pitfall 4 — "Spring MVC `@CrossOrigin` is enough in every case."** The security filter chain can return 401/403 before reaching the controller, so you must ensure CORS is properly integrated with Spring Security and the right chain.

**Pitfall 5 — "Enabling CORS grants access to the account."** CORS, authentication, and authorization answer different questions; a client allowed to read must still have permission for each resource.

**Pitfall 6 — "No CSRF is needed because the browser blocks reading the response."** A state-changing operation can execute even when the response cannot be read. CSRF and cookie policies still need proper design.

## 10. Key Takeaways

- **SOP** protects origin boundaries in the browser; an origin is defined by `scheme + host + port`.
- **CORS** is conditional permission from the **target server** for the browser to expose a response to cross-origin JavaScript.
- **Preflight** is a prior check for certain methods/headers; not every cross-origin request triggers a preflight, and the actual response is still checked.
- **Spring Security Servlet** needs to process CORS early in the filter chain so OPTIONS is not wrongly rejected for lacking credentials.
- **CORS does not replace authentication, authorization, CSRF, XSS protection, or API access control**. Verify both the browser policy and actual server-side protections.