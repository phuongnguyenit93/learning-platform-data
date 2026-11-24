# Same-Origin Policy and the Purpose of CORS

## 1. The core question: can a web page read data from another origin?

Suppose an application has:
- **Frontend**: http://localhost:5173, running JavaScript in the browser.
- **Backend**: http://localhost:8080, exposing the APIs /api/public and /api/private.

JavaScript code from the frontend wants to call:

~~~javascript
const response = await fetch("http://localhost:8080/api/public");
const data = await response.json();
console.log(data);
~~~

The two URLs share the same hostname **localhost** but have different ports **5173** and **8080**, so they **do not share the same origin**. The browser enforces the **same-origin policy (SOP)**: scripts from one origin cannot freely read data belonging to another origin. For an API to intentionally allow pages from trusted origins to access responses, the browser and server coordinate via **Cross-Origin Resource Sharing (CORS)**.

**CORS is neither an authentication mechanism nor business authorization.** CORS decides whether **a page/script running in a browser at origin A** is allowed by the browser to **read a response** from origin B. After passing CORS, the server must still check Authentication, GrantedAuthority, CSRF when needed, and resource access permissions.

This lesson covers:
1. How an origin is defined by **scheme + host + port**.
2. What SOP protects against and what it does not prevent.
3. The purpose of CORS and how browsers enforce the policy through HTTP headers.
4. How ordinary requests differ from **OPTIONS preflight** requests.
5. Why **credentials, cookies, SameSite, CSRF**, and CORS must be evaluated separately.
6. Configuring Spring Security 6.x / Spring Boot 3.x to process CORS before requiring authentication.
7. A Java 17+ demo with a frontend at localhost:5173 and an API at localhost:8080, tested via browser, curl, and MockMvc.
8. Common configuration mistakes, the limits of CORS, and how to test safely.

> Example scope: **Spring MVC / Servlet stack**. Spring WebFlux uses **CorsWebFilter**, **ServerHttpSecurity**, and its own reactive APIs. Do not copy Servlet classes verbatim into WebFlux.

## 2. What is an Origin?

An **Origin** is a tuple of three components:

~~~text
origin = (scheme, host, port)
~~~

For example, the origin of **https://app.example.com:443/dashboard** is:
- Scheme: **https**.
- Host: **app.example.com**.
- Port: **443**, which is the default port for HTTPS.

The path **/dashboard**, query string, fragment, and anything after the hostname are not part of origin comparison. Two URLs can share the same host yet differ in scheme or port and still be **cross-origin**.

### 2.1. Origin comparison table

Suppose the current page is open at **https://app.example.com/home**:

| Resource URL | Same origin? | Reason |
| --- | --- | --- |
| https://app.example.com/api/me | **Yes** | Scheme, host, and effective port all match |
| https://app.example.com:443/api/me | **Yes** | Port 443 is the default for HTTPS |
| https://app.example.com:8443/api/me | **No** | Different port |
| http://app.example.com/api/me | **No** | Different scheme and effective port |
| https://api.example.com/api/me | **No** | Different subdomain/host |
| https://app.example.com/other-path | **Yes** | Only the path differs |
| https://app.example.com/api?q=1 | **Yes** | Query does not change the origin |
| https://APP.example.com/api/me | **Yes**, after proper host normalization | DNS hostnames are case-insensitive |
| https://app.example.org/api/me | **No** | Different host |

In a development environment, **http://localhost:5173** and **http://localhost:8080** are not the same origin because their ports differ. **http://localhost:5173** and **http://127.0.0.1:5173** also have different origins because their hostnames differ, even though both point to the local machine.

**Origin** is not completely synonymous with **site** in cookie security:
- Origin considers scheme, host, and port.
- The **site** concept typically relies on scheme and registrable domain, without treating port the same way origin does.
- Therefore, two **cross-origin** URLs can still be **same-site** under cookie rules. Consequence: CORS and SameSite cookies solve two different problems; neither can replace the other.

### 2.2. Where does JavaScript code's origin come from?

When the browser loads **index.html** from http://localhost:5173, scripts on that page run with that document's origin. When the script calls fetch against http://localhost:8080, the browser compares the current origin with the target origin.

Where the built frontend HTML/JavaScript is hosted matters more than the source code folder name. React, Vue, Angular, and Vite do not change the SOP concept: the browser still uses the document's URL origin when executing the code.

Certain situations such as sandboxed documents, data URLs, or file URLs can have an **opaque origin**; the browser may send the header **Origin: null**. Do not automatically treat the value "null" as a trusted origin to allow in production.

## 3. What does the Same-Origin Policy (SOP) protect?

SOP is a cornerstone of browser security designed to prevent scripts from an untrusted origin from arbitrarily reading or interfering with data and context from another origin.

For example:
- A user signs in to a banking application at **https://bank.example**.
- At the same time, the user opens a malicious page at **https://evil.example**.
- If a script on evil.example were free to read responses from bank.example using the user's credentials, an attacker could attempt to extract balances, account details, or sensitive data.

SOP establishes a protective boundary: a script from evil.example **does not automatically have permission** to retrieve content from bank.example just because both pages are open in the same browser.

### 3.1. Do not mistake SOP for “the browser blocks every cross-origin HTTP request”

This is a common misconception. Browsers still allow many kinds of cross-origin operations, depending on the mechanism:
- Navigating to a URL on another origin.
- Loading images via **img** elements.
- Loading scripts from another source according to relevant policies and attributes.
- Submitting HTML forms to another origin under browser-supported conditions.
- Executing certain cross-origin **fetch** requests while **preventing the script from reading the response** if CORS is not satisfied.

Therefore, SOP **does not guarantee that a request is never sent to the server**. For certain simple requests, the backend may have already received and processed the request even though the calling script cannot read the response. This is why **CORS does not replace CSRF**.

### 3.2. SOP has many facets; CORS focuses on one specific part

Same-origin security also covers:
- DOM access across frames/windows of different origins.
- Script ability to read data from fetch/XMLHttpRequest.
- Storage, resource, and other browser API restrictions.
- Additional defenses such as CSP, COOP/COEP, CORP, sandbox, and SameSite.

**CORS is primarily a mechanism for a server to allow sharing responses with designated origins in situations where the browser enforces CORS.** It does not “turn off SOP for the whole browser”, does not make every cross-origin DOM readable, does not disable cookie/storage boundaries, and does not automatically grant API permissions.

## 4. What is CORS designed to do?

**Cross-Origin Resource Sharing (CORS)** is a mechanism using HTTP request/response headers by which a server indicates which origins the browser may allow to access a given resource. The browser inspects those headers to decide whether JavaScript may read the response.

CORS solves a very common legitimate need:

~~~text
SPA at https://app.example.com
         |
         | fetch("https://api.example.com/me")
         v
API at https://api.example.com
         |
         +--> Allow origin https://app.example.com?
                  |
                  +--> Yes: return appropriate CORS response headers
                  |         Browser allows JS to read the response
                  |
                  +--> No: browser does not share the response with JS
~~~

**The server decides the sharing policy; the browser enforces the policy on scripts.** CORS is useful when frontend and backend are on separate domains or ports, when web fonts reside on a CDN, or when one origin needs to load resources via fetch/canvas.

CORS does not identify who the user is. CORS only looks at the origin of the page issuing the request; it does not check the account's business permissions. An origin permitted to make CORS calls **cannot automatically** read every user's profile.

### 4.1. CORS is a contract between server and browser, not a barrier blocking all clients

An HTTP client such as **curl**, Postman, or a backend service can send requests directly to an API without being governed by browser SOP. It can set any Origin header itself or omit Origin altogether. Therefore, you cannot protect data by saying “only app.example.com is allowed by CORS”.

**Real API protection must use Authentication + Authorization**, validation, rate limiting, and ownership/tenant checks. CORS is only one part of web browser security.

## 5. Key HTTP headers of CORS

There are two groups:
1. **Request headers** added by the browser to indicate the origin and, during preflight, the intended method/headers.
2. **Response headers** returned by the server to declare the sharing policy.

### 5.1. Common request headers

| Header | When is it used? | Meaning |
| --- | --- | --- |
| **Origin** | Applicable cross-origin requests, and certain same-origin requests | Origin of the page/context initiating the request |
| **Access-Control-Request-Method** | OPTIONS preflight | HTTP method that the actual request will use |
| **Access-Control-Request-Headers** | OPTIONS preflight when needed | List of custom/request headers the actual request intends to send |

Preflight example:

~~~http
OPTIONS /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-lesson-client
~~~

This is a request generated by the **browser** to ask permission before a GET with a custom header. A typical frontend does not manually write an OPTIONS call to “imitate CORS”; the developer declares fetch, and the browser decides whether preflight is needed and sends it automatically.

### 5.2. Common response headers

| Header | Function |
| --- | --- |
| **Access-Control-Allow-Origin** | Origin allowed to receive the response; can be a specific origin or `*` where appropriate |
| **Access-Control-Allow-Methods** | HTTP methods allowed in the preflight result |
| **Access-Control-Allow-Headers** | Request headers allowed during preflight |
| **Access-Control-Allow-Credentials** | Indicates whether the browser may share the response when the request carries credentials |
| **Access-Control-Max-Age** | Instructs caching of the preflight result for a period, subject to browser limits |
| **Access-Control-Expose-Headers** | Response headers outside the CORS-safelisted list that JS is allowed to read |
| **Vary: Origin** | Tells caches that the response may vary by request Origin |
| **Vary: Access-Control-Request-Method / Headers** | May be needed when the preflight response varies by method/headers |

Example of a server allowing the frontend at localhost:5173 to read the response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"message":"hello-from-api"}
~~~

The **Access-Control-Allow-Origin** header declares response-sharing permission, not a login pass. If an endpoint requires Authentication and the request lacks valid credentials, the server can still return **401**, accompanied by CORS headers so the frontend can read and handle the error properly.

### 5.3. The `*` wildcard has a very specific meaning

~~~http
Access-Control-Allow-Origin: *
~~~

The `*` means the server allows **any origin** to read the response in requests **without CORS credentials**. This can make sense for public data such as certain public APIs and public static files.

When a request uses credentials, the server **must not** use `*` for **Access-Control-Allow-Origin** if it wants the browser to allow reading the response. The browser will block access in a situation like:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

For applications using cookies/sessions, you must list specific trusted origins and send **Access-Control-Allow-Credentials: true** if sharing credentialed responses is truly needed. Do not return **Access-Control-Allow-Origin** by echoing every unchecked Origin value.

### 5.4. Origin is not a role or username

If one browser at **https://app.example.com** opens two different accounts, both send the same Origin in cross-origin requests to the API. CORS does not know which account is allowed to view a report. Data permissions depend on Authentication and Authorization on the backend.

Similarly, an attacker can build a non-browser HTTP client and arbitrarily set:

~~~http
Origin: https://app.example.com
~~~

The server must not treat the Origin header as a credential proving identity. CORS relies on browser policy for scripts; Origin is merely a signal for the server to apply the corresponding sharing policy.

## 6. “Simple” requests and OPTIONS preflight

Not every cross-origin request triggers a preflight. The browser may send a **CORS simple request** (the descriptive term used in MDN) directly and then inspect the response headers. Other requests require a **preflight** before sending the actual request.

### 6.1. Example of a simple GET without preflight

~~~javascript
fetch("http://localhost:8080/api/public");
~~~

An ordinary GET with no custom headers, under appropriate conditions, can be sent directly. If the backend returns a response without CORS headers accepting the Origin, the browser **does not let JavaScript read the response**.

This is especially important: the server may log that the GET arrived and returned 200, while DevTools still reports a CORS error on the frontend. Do not conclude that the browser never sent the request just because fetch() rejected.

### 6.2. Example of a GET with a custom header requiring preflight

~~~javascript
fetch("http://localhost:8080/api/public", {
    headers: {"X-Lesson-Client": "frontend-demo"}
});
~~~

The **X-Lesson-Client** header is not in the CORS-safelisted request headers group. The browser typically sends:

~~~http
OPTIONS /api/public HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-lesson-client
~~~

If the policy permits it, the server responds with, for example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: x-lesson-client
Access-Control-Max-Age: 1800
~~~

After the preflight succeeds, the browser can send the actual GET, and still checks the CORS headers on the **actual GET response** before sharing the content with the script.

**Preflight is not a business request**: it only asks about cross-origin policy. Do not create data or perform state-changing operations in an OPTIONS handler.

### 6.3. JSON POST usually requires preflight, but you cannot say every POST does

A POST using **Content-Type: application/json** normally triggers preflight because this Content-Type is not among the CORS-safelisted content types. Conversely, a form POST using Content-Types such as **application/x-www-form-urlencoded**, **multipart/form-data**, or **text/plain** under appropriate conditions can be a simple request and require no preflight.

Reference table:

| Cross-origin JavaScript request | Likely to preflight? | Why |
| --- | --- | --- |
| GET /api/public, no custom header | Usually **no** | Method and headers meet simple conditions |
| GET, X-Lesson-Client header | **Yes** | Non-safelisted custom header |
| GET, Authorization header | **Yes** | Authorization is not a CORS-safelisted request header |
| POST, Content-Type: application/json | **Yes** | Non-safelisted Content-Type |
| Form POST, application/x-www-form-urlencoded | Possibly **no** | Meets simple conditions if no other triggers exist |
| PUT or DELETE | Usually **yes** | Method is not in the simple methods group |
| Request using any custom header | Possibly **yes** | Must check the actual header and value |

The outcome also depends on detailed rules in the Fetch/CORS specification (request mode, header/value, browser policy…). Use **DevTools Network** to inspect actual requests rather than guessing from endpoint names.

### 6.4. Preflight lacking cookies is normal

By browser rules, **CORS preflight does not carry credentials** such as session cookies. Therefore, if the server requires OPTIONS to be authenticated before returning CORS headers, the browser may never be able to send the actual request carrying a valid cookie.

This is why Spring Security recommends **processing CORS before Spring Security authentication/authorization** for preflight, for example via **CorsFilter / CorsConfigurationSource** and **http.cors(...)**. Forcing all clients to manually send JSESSIONID in OPTIONS is not the right solution.

## 7. Credentials: CORS does not automatically send cookies

With browser fetch, two parts must both be in place when a frontend calls a different-origin API using session cookies:

1. **The client explicitly opts in to sending credentials**, e.g. fetch with **credentials: "include"**.
2. **The server allows credentialed CORS**, returning a specific Origin and Access-Control-Allow-Credentials: true.

Example frontend at **https://app.example.com**:

~~~javascript
const response = await fetch(
    "https://api.example.com/api/me",
    {credentials: "include"}
);
~~~

The server must have a CORS policy accepting the origin https://app.example.com and credentialed requests, yet **cookies still obey Secure, SameSite, Domain, Path, expiration, and browser privacy/tracking policies**. CORS does not force the browser to send cookies blocked by SameSite or third-party-cookie policies.

### 7.1. Do not confuse cross-origin with cross-site

Two subdomains of the same site can be cross-origin while still being same-site in cookie context. Conversely, a frontend and backend on two different registrable domains can be cross-site; in that case cookie policy is stricter and must be tested in a real browser.

For example, **localhost:5173** and **localhost:8080** are cross-origin yet can be considered same-site under the cookie model. Do not take a local example and conclude that SameSite=None is always required in every deployment.

### 7.2. Do not use a wildcard when credentials are enabled

In Spring Framework, configuring:

~~~java
configuration.setAllowedOrigins(List.of("*"));
configuration.setAllowCredentials(true);
~~~

is a **disallowed** combination for allowedOrigins. Spring provides **allowedOriginPatterns** to support patterns and respond with the specific matched origin, yet **an overly broad pattern remains a serious risk**. Use an **exact origin allowlist** whenever possible.

A safer policy for a credentialed application is:

~~~java
configuration.setAllowedOrigins(
    List.of("https://app.example.com"));
configuration.setAllowCredentials(true);
~~~

The two snippets above are **configuration fragments**, not standalone runnable classes. Setting allowCredentials=true must be accompanied by proper cookie/CSRF design and endpoint authorization, not merely enabled to “make CORS errors go away”.

### 7.3. CSRF and CORS are related but serve different purposes

**CORS**: does the browser allow a script at origin A to **read the response** from origin B?

**CSRF**: does the server accept a **forged state-changing request** carrying credentials automatically attached by the browser?

With a simple request, the browser can **send a POST** even if the script cannot read the response. Therefore, configuring CORS alone does not replace a **CSRF token**. If an application uses session cookies or auto-sent JWT cookies, CSRF must be evaluated for unsafe methods, along with Origin/Referer checks where appropriate.

Conversely, a Bearer token API where the client explicitly attaches the Authorization header has a different threat model; it still requires token validation and XSS/token-leakage defenses. Do not conclude “we use JWT so we don't need CSRF” merely because the token format is JWT.

## 8. Spring Boot 3.x Demo: CORS in the browser and authorization on the backend

We will build a simple backend application:
- **GET /api/public**: public endpoint returning JSON.
- **GET /api/private**: returns JSON only with valid HTTP Basic authentication.
- **Allowed origin**: only **http://localhost:5173**.
- **Allowed methods**: GET.
- **Allowed request headers**: X-Lesson-Client and Authorization.
- **CORS credentials mode**: does not support sharing credentialed responses via cookies; the demo frontend only calls the public API and does not use session cookies.

The demo intentionally **has no data-modifying endpoints**. Therefore, we do not need to disable CSRF to try CORS. HTTP Basic is used solely to illustrate a separate protected endpoint, and the password is a local test password.

### 8.1. Preparing the project

Use **Spring Initializr** to create a project:
- **Java 17+**, **Spring Boot 3.x**, built with **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** and **Spring Security**.

Create the exact Java file:

~~~text
src/main/java/com/example/demo/CorsSopDemoApplication.java
~~~

### 8.2. Complete Java source code for the backend

~~~java
package com.example.demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsSopDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsSopDemoApplication.class, args);
    }
}

@Configuration
class CorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();

        // Only the frontend at this exact origin can read the API via CORS.
        configuration.setAllowedOrigins(
            List.of("http://localhost:5173"));

        // The demo only has GET, no business POST/PUT/DELETE.
        configuration.setAllowedMethods(List.of("GET"));

        // This custom header triggers preflight when called from a browser.
        configuration.setAllowedHeaders(
            List.of("X-Lesson-Client", "Authorization"));

        configuration.setAllowCredentials(false);
        configuration.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        // Restrict the policy to /api/** endpoints.
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // Integrate CORS into the Spring Security filter chain.
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/private")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            // Default CSRF protection is preserved.
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(reader);
    }
}

@RestController
class ApiController {

    @GetMapping("/api/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "hello-from-api");
    }

    @GetMapping("/api/private")
    Map<String, String> privateInfo(Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "message", "authenticated");
    }
}
~~~

**Runnability notes:**
- The public top-level class name matches the file name **CorsSopDemoApplication.java**.
- The other classes are package-private in the same package; Spring Boot component scan discovers them.
- Spring Boot 3.x with the two starters listed above provides HttpSecurity, SecurityFilterChain, Spring MVC, and JSON serialization.
- **UrlBasedCorsConfigurationSource** is the bean that allows Spring Security to integrate CORS using the documented configuration.
- **http.cors(Customizer.withDefaults())** enables the appropriate CORS processing path in the security filter chain so valid preflight requests are not treated as unauthenticated requests.
- **permitAll** on GET /api/public is not equivalent to a CORS allowlist. A request from curl can still access the public endpoint without an Origin.
- **authenticated** on GET /api/private requires Authentication; an allowed origin does not replace a password/credential.
- **setAllowCredentials(false)** is intentionally used in this test frontend **without cookies**. To demonstrate credentialed CORS with sessions, a different policy and proper login/CSRF design are required.
- **{noop}** is only for local learning; production must use a PasswordEncoder and a secure user store.
- CSRF is not disabled because the demo only uses GET. If data-modifying POSTs are added, CSRF must be evaluated based on how credentials are sent.

### 8.3. Running the backend

In the Gradle project root directory:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

If **server.port** is unchanged, the API typically listens at **http://localhost:8080**.

### 8.4. Standalone HTML frontend to observe browser CORS

Create a **web** directory in the project root and the file **web/index.html**:

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Same-origin policy / CORS demo</title>
</head>
<body>
    <h1>Testing CORS with Spring Security</h1>
    <p>Open this page at localhost:5173 to be allowed to read the API.</p>
    <button id="ordinary">Ordinary GET</button>
    <button id="preflight">GET with custom header</button>
    <button id="private">GET requiring login</button>
    <pre id="output"></pre>

    <script>
        const base = "http://localhost:8080";
        const output = document.getElementById("output");

        async function call(path, headers = {}) {
            output.textContent = "Calling API...";
            try {
                const response = await fetch(base + path, {
                    method: "GET",
                    headers: headers
                });
                const body = await response.text();
                output.textContent =
                    "HTTP " + response.status + "\n" + body;
            } catch (error) {
                output.textContent = "Browser rejected or " +
                    "request failed: " + error.message;
            }
        }

        document.getElementById("ordinary")
            .addEventListener("click", function () {
                call("/api/public");
            });

        document.getElementById("preflight")
            .addEventListener("click", function () {
                call("/api/public", {
                    "X-Lesson-Client": "frontend-demo"
                });
            });

        document.getElementById("private")
            .addEventListener("click", function () {
                call("/api/private");
            });
    </script>
</body>
</html>
~~~

**This HTML file runs in the browser** when served through an HTTP server. Do not open file:// directly, because the page may then have an opaque origin and the result will no longer match the designed localhost:5173 example.

Using Python 3 (if available):

~~~bash
python3 -m http.server 5173 --directory web
~~~

On Windows, the equivalent command is typically:

~~~powershell
py -3 -m http.server 5173 --directory web
~~~

Then open **http://localhost:5173** in the browser. At this point the frontend origin is **http://localhost:5173**, while the API is at **http://localhost:8080**.

### 8.5. What to observe

**Button 1 — Ordinary GET:**
- The browser sends GET /api/public with Origin http://localhost:5173.
- The CORS policy matches, and the server returns Access-Control-Allow-Origin.
- The script reads the **200** response and the body containing **hello-from-api**.
- A GET request without custom headers may not need preflight.

**Button 2 — GET with X-Lesson-Client:**
- The browser generates a preflight **OPTIONS /api/public**.
- The preflight declares Access-Control-Request-Method: GET and Access-Control-Request-Headers: x-lesson-client.
- CORS handles OPTIONS before HTTP authorization.
- If the preflight succeeds, the browser sends the actual GET.
- The GET result is **200**, just like Button 1.

**Button 3 — Protected GET:**
- The Origin is still accepted by CORS.
- However, there are no valid HTTP Basic credentials; Spring Security returns **401**.
- The frontend can read status **401** because the CORS policy allows that origin to read responses.
- This proves that **passing CORS does not mean passing authorization**.

**The statuses above are expected outcomes from the configuration, not captured execution logs.** Browsers may cache preflight thanks to Max-Age; therefore, after one attempt, you may not see OPTIONS on every click. Open DevTools Network and adjust cache/refresh settings when needed.

### 8.6. Trying an origin not in the allowlist

In a third terminal, use the same web directory but start another HTTP server:

~~~bash
python3 -m http.server 5174 --directory web
~~~

Open **http://localhost:5174**. The HTML/JS is identical, but the origin is now **http://localhost:5174**, which is not in allowedOrigins.

When the script calls GET /api/public at localhost:8080:
- The browser does not share the response with JavaScript.
- DevTools Console/Network may display a CORS error.
- With the CorsFilter setup in the example, the Spring CORS processor can also return 403 for a request with a disallowed Origin.
- If a simple request actually reaches the backend and is rejected there, that is server-side CORS handling; if a different backend simply omits response headers, the browser will still block the script from reading the response. Both cases produce a similar frontend error experience, yet the HTTP-layer cause differs.

**Do not change the frontend port and forget to update allowedOrigins**, because origin matching includes the port. To support multiple valid frontend origins, configure an exact list and document why each origin is trusted.

## 9. Verifying HTTP with curl: observing headers without confusing it with browser SOP

**curl does not enforce SOP/CORS like a browser**. It can help verify whether the server returns the right headers, but curl reading the body does not prove a browser will allow reading the body.

### 9.1. Request with an accepted Origin

~~~bash
curl -i \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/public
~~~

Typical expectation: **HTTP 200**, header **Access-Control-Allow-Origin: http://localhost:5173**, JSON with message hello-from-api. On Windows PowerShell, use **curl.exe** if curl is an incompatible alias.

### 9.2. Preflight with a custom header

~~~bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-lesson-client" \
  http://localhost:8080/api/public
~~~

Typical expectation: **200**, headers allowing origin/method/request header, and possibly **Access-Control-Max-Age**. This request **sends no Authorization or session cookie**; CORS preflight does not require credentials.

### 9.3. Disallowed origin

~~~bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-lesson-client" \
  http://localhost:8080/api/public
~~~

With Spring DefaultCorsProcessor, preflight for a disallowed origin typically receives **403 Invalid CORS request**. This is **the server-side CORS processor's decision**, not the browser blocking response reading. A browser may show a CORS error at the JavaScript level even though the actual HTTP status codes differ across APIs.

### 9.4. Authentication is independent of CORS

~~~bash
# Without HTTP Basic credentials, even with a valid Origin:
curl -i \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private

# With valid credentials of the demo user:
curl -i -u reader:demo123 \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private
~~~

Expected:
- First request: **401** because it is unauthenticated, not because the Origin is wrong.
- Second request: **200**, JSON with username reader and message authenticated.

Do not use the test password **demo123** in real systems. When running curl -u in shared environments, note that the command line may be saved in history or visible to process inspection.

### 9.5. Sending no Origin

~~~bash
curl -i http://localhost:8080/api/public
~~~

Expect **200** without needing browser CORS headers. This is a clear example that **CORS is not a mechanism to protect an API from non-browser access**. If you want to block unauthorized clients, you must use Authentication/Authorization and appropriate security controls.

## 10. Comparison table: CORS, Authentication, Authorization, and CSRF

| Mechanism | Primary question | Who checks it? | Example |
| --- | --- | --- | --- |
| **SOP** | May a script at origin A freely read content from origin B? | Browser | Script at evil.example cannot arbitrarily read bank.example response |
| **CORS** | Does server B agree to share its response with a script from origin A? | Server declares, browser enforces | Allow-Origin: https://app.example.com |
| **Authentication** | Who is sending the request/credential? | Server / identity provider | Session, HTTP Basic, OAuth2 Resource Server |
| **Authorization** | Which resources may that identity view/modify? | Server | hasAuthority, hasRole, ownership |
| **CSRF protection** | Was a state-changing request forged by an external page using auto-sent credentials? | Server, combined with browser semantics | CSRF token for POST with session cookie |
| **SameSite cookie** | Does the browser send a cookie in certain cross-site contexts? | Browser based on cookie attributes | SameSite=Lax/Strict/None |
| **CSP** | Which script/resource sources may the page load and run? | Browser per page policy | script-src, connect-src |

**CORS is not a substitute for Authentication, Authorization, or CSRF**. Misconfigured CORS can expand cross-origin data reading to an untrusted website, yet even a locked-down CORS policy does not protect an API against curl or server-side clients.

## 11. Automated testing with MockMvc

In addition to browser testing, you can test Spring Security's CORS configuration to confirm:
- Preflight requires no login.
- Allowed origins receive the proper Access-Control-Allow-Origin.
- Other origins are not allowed.
- Endpoints requiring Authentication still return 401 when credentials are missing.
- Valid credentials still pass authorization.

Add to **build.gradle** if not already present:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **Gradle Groovy DSL fragment**, not a complete build.gradle. Spring Initializr usually already adds starter-test; avoid duplicate entries.

Create **src/test/java/com/example/demo/CorsSopDemoApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsSopDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void trustedOriginCanReadPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173"))
            .andExpect(jsonPath("$.message")
                .value("hello-from-api"));
    }

    @Test
    void anonymousPreflightIsProcessedBeforeAuthentication()
            throws Exception {
        mvc.perform(options("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-lesson-client"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173"));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/public")
                .header(HttpHeaders.ORIGIN, "http://localhost:5174")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void corsAllowedDoesNotMeanUserAuthenticated()
            throws Exception {
        mvc.perform(get("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173"));
    }

    @Test
    void correctlyAuthenticatedUserCanAccessPrivateEndpoint()
            throws Exception {
        mvc.perform(get("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }
}
~~~

Run from the project directory:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

The tests above verify **server-side CORS/Spring Security behavior** in MockMvc. They **do not automatically run a real browser's SOP**; to prove that JavaScript is blocked at a disallowed origin, you still need to test an actual frontend on ports 5173/5174 or run browser-based E2E tests.

**The results stated in this lesson are expected based on the configuration; Gradle/tests were not executed in this content.**

## 12. How to debug a “CORS policy blocked” error

When Console reports a CORS error, do not immediately add `*` to every config. Follow this order.

### 12.1. Identify the two real origins

Write down clearly:
- Full frontend URL including scheme, host, and port.
- Full API URL including scheme, host, and port.
- Redirect URL if any.
- Actual Origin sent by the browser in the Network tab.

For example, **localhost** and **127.0.0.1** are two different hostnames. A frontend running at http://localhost:3000 is not automatically accepted if only http://localhost:5173 is allowed.

### 12.2. Check OPTIONS preflight first

If the browser sends OPTIONS:
1. Does the request have the expected **Origin**?
2. What is **Access-Control-Request-Method**?
3. Which headers does **Access-Control-Request-Headers** list?
4. Did preflight receive an appropriate HTTP 200/204 or a 301/302/401/403?
5. Does the response include **Access-Control-Allow-Origin**, **-Methods**, and **-Headers** satisfying the request?
6. Is OPTIONS being blocked before CORS by a Spring Security authentication filter, gateway, or reverse proxy?

A preflight redirected to /login or returning 401 due to missing session is usually a sign that **CORS filter/config ordering is wrong**. This cannot be fixed by forcing the browser to send a password in OPTIONS.

### 12.3. If preflight passes, check the actual request's response

The browser still requires matching CORS headers on the actual request. An API whose preflight returns 200 while the actual POST/GET returns 401/403/500 without Allow-Origin can cause the frontend to see only a generic CORS error.

Inspect server logs by status/path/trace ID; distinguish:
- 401: no valid authentication.
- 403: insufficient permissions, CSRF, or rejection by the CORS processor.
- 404: no handler or route differs from the expected URL.
- 5xx: application/gateway error that may not attach CORS headers.

**Do not broaden permissions to hide authorization or server errors.**

### 12.4. Check cookies, SameSite, and credentials

If the frontend must send a session cookie:
- Does fetch have **credentials: "include"**?
- Does the server return **Access-Control-Allow-Credentials: true** along with a specific allowed origin?
- Does the cookie have the right **Secure, SameSite, Domain, Path** for the environment?
- Does the browser have policies blocking third-party cookies?
- Did login/session actually succeed?
- Does the CSRF token match the current session for POST/PUT/PATCH/DELETE?

Do not assume adding **allowCredentials(true)** is enough to fix cookies rejected by the browser or expired sessions.

### 12.5. Check gateway, CDN, cache, and multiple security chains

With a reverse proxy, ingress, or CDN:
- Does the proxy answer OPTIONS directly and omit CORS headers?
- Are there duplicate **Access-Control-Allow-Origin** headers from both the gateway and Spring causing an invalid header?
- Does the cache use **Vary: Origin** when policy differs by origin?
- Do error responses returned by the gateway still include appropriate CORS headers?
- If there are multiple **SecurityFilterChain** beans, which chain matches /api/** and does it have cors()?

According to Spring Security 6.5 documentation, when there are **multiple CorsConfigurationSource beans**, the framework cannot necessarily determine automatically which source belongs to each chain. In that case, you can explicitly configure **configurationSource** in each chain's DSL.

## 13. Common configuration mistakes and misconceptions

| Misconception/mistake | Why is it wrong or dangerous? | Correct approach |
| --- | --- | --- |
| “CORS is how I lock my API down to only my frontend.” | curl or backend services are not bound by SOP | Use server-side Authentication + Authorization |
| “Without CORS, browsers cannot send requests.” | Simple requests can be sent before the browser blocks reading | Do not use CORS instead of CSRF |
| “Just add permitAll and cross-origin fetch will work.” | permitAll checks API access, does not add CORS response headers | Enable CORS and allow appropriate origins |
| “Origin localhost:5173 and localhost:8080 are the same.” | Different ports → cross-origin | Compare scheme + host + port |
| “Frontend and API both use HTTPS so they are same-origin.” | Host or port can still differ | Compare all three components |
| “@CrossOrigin protects the endpoint from attackers by default.” | CORS declares response sharing, does not authenticate users | Configure narrow origins and separate authorization |
| “Access-Control-Allow-Origin: * + credentials=true works.” | Browsers reject wildcard with credentials | Use specific trusted origins |
| “Preflight must be logged in first.” | Browser preflight carries no session cookies | Process CORS before authentication/authorization |
| “OPTIONS returning 200 guarantees GET/POST can be read.” | Actual response also needs CORS headers and must pass auth | Check both preflight and actual response |
| “JSON POST is definitely always a simple request.” | application/json usually triggers preflight | Check Content-Type and request headers |
| “Passing CORS means the user can read any data.” | Origin is not identity/authority | Protect endpoints and ownership |
| “CORS error? Just disable CSRF.” | Two mechanisms with different purposes | Keep CSRF when browsers use cookie credentials |
| “Allow every Origin with regex for convenience.” | Can expose authenticated data to untrusted domains | Allowlist specific origins, review patterns |
| “Origin: null is safe localhost.” | Opaque origins can arise from many sources | Do not trust null without a specific threat model |
| “If the server sends Set-Cookie, the browser will always store it.” | Cookie flags and privacy policies still apply | Check Secure/SameSite/third-party policies |
| “CORS always blocks responses from curl.” | curl does not enforce SOP | Use curl to inspect headers, browser to test SOP |
| “Only add headers on 200, not on errors.” | Frontend may fail to read 401/403/500 | Ensure proper CORS handling in filters/gateway |
| “Vary doesn't matter; caches figure out Origin automatically.” | Caches may mix up responses across origins | Check Vary, caching, and CDN policies |

## 14. CORS design checklist for real-world systems

Before deploying a CORS configuration to production, answer:

1. What are the exact frontend origins in **dev, staging, and production**?
2. Is **cross-origin** actually needed, or can a same-origin API be served via a reverse proxy?
3. Which APIs allow cross-origin access, and which definitely do not need it?
4. Are allowed origins narrowly declared, avoiding wildcards when credentials are used?
5. Do allowed methods and allowed headers reflect actual frontend needs?
6. Is OPTIONS preflight processed before authentication/authorization layers?
7. Do both actual responses and error responses carry proper CORS headers when needed?
8. Are **credentials: include**, cookies, or Authorization headers used? What is the rationale and threat model?
9. If cookies are used, are SameSite/Secure/HttpOnly/Domain/Path and CSRF configured and tested?
10. Are there redundant configs across Spring MVC, Spring Security, and the gateway causing duplicate headers or conflicting policies?
11. Are sensitive endpoints protected with roles/scopes/ownership regardless of whether the origin is allowed?
12. Have **trusted origins**, **untrusted origins**, **preflight**, **actual requests**, **401/403**, and real browsers all been tested?
13. If returning dynamic origins, do CDNs/caches support Vary: Origin and proper caching policies?
14. Have redirect URLs, protocol upgrades, ports, and localhost aliases been accounted for?
15. Is configuration drift monitored when adding new frontends or moving an API to another domain?

### Self-assessment questions

1. Which components make up an origin? Why does localhost:5173 differ from localhost:8080?
2. Does the same-origin policy strictly forbid browsers from sending all cross-origin requests, or does it mainly restrict types of data access/reading?
3. Who proposes the CORS policy and who enforces it for JavaScript running in the browser?
4. Why can a curl request still succeed even when frontend JavaScript is blocked by CORS?
5. How do the roles of **Origin**, **Access-Control-Allow-Origin**, **Access-Control-Request-Method**, and **Access-Control-Allow-Headers** differ?
6. Why does a GET request with the **X-Lesson-Client** header require preflight while a plain GET may not?
7. Why should CORS preflight not be required to carry JSESSIONID?
8. When a frontend uses credentials: include, why can't Allow-Origin: * be used?
9. Can CORS replace a CSRF token for a POST carrying a session cookie?
10. If preflight passes but GET /api/private returns 401, is this necessarily a CORS error?
11. Why can two cross-origin pages still be considered same-site for cookies?
12. In Spring Security 6, why is **http.cors(...)** needed with CorsConfigurationSource or proper Spring MVC integration?
13. Why do MockMvc tests verifying CORS headers still require testing with a real browser?
14. If a system has two SecurityFilterChain beans, which chains need to be reviewed for CORS?
15. Why shouldn't you blindly echo every Origin into Access-Control-Allow-Origin when user data is involved?

**Remember:** **SOP** is the browser's boundary between origins. **CORS** is the mechanism by which **a server publishes controlled exceptions** so the browser allows pages from another origin to read responses. CORS does not authenticate users, does not grant business permissions, does not block non-browser HTTP clients, and **does not replace CSRF protection**. With Spring Security, ensure preflight is handled properly, declare narrow origins/methods/headers, and always verify both browser behavior and backend authorization.

## 15. Official documentation

- MDN — Same-origin policy: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy
- MDN — Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Request credentials in Fetch: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- Spring Security 6.5 — CORS (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html
- Spring Framework 6.x — CORS in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Fetch Living Standard — CORS protocol: https://fetch.spec.whatwg.org/
