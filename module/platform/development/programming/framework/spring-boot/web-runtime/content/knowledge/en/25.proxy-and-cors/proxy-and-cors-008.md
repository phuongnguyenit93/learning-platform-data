# OPTIONS preflight and processing order before authentication

**Module:** Spring Boot - web-runtime  
**Parent topic:** Proxy and CORS

## 1. The problem: why does OPTIONS return 401 while GET with a token works?

Suppose a frontend runs at **http://localhost:5173** and a Spring Boot API runs at **http://localhost:8080**. A user has logged in, and the frontend wants to call `GET /api/profile` with an **Authorization** header or an application header **X-Request-Id**. The browser may send an **OPTIONS preflight request** before sending the actual `GET`.

Example JavaScript illustrating the request:

~~~javascript
fetch("http://localhost:8080/api/profile", {
    headers: {
        "Authorization": "Bearer <access-token>",
        "X-Request-Id": "request-101"
    }
});
~~~

This merely illustrates a frontend that obtains a valid token; the runnable demo later uses **HTTP Basic** so it is easy to test with `curl`, and has no bearer-token issuer.

If **OPTIONS** is rejected by an authentication filter with **401 Unauthorized**, the browser reports a CORS error and **never sends the actual GET**. Therefore, adding a token to `GET`, editing the controller, or opening `GET` permissions will not fix the problem. You must configure **CORS to be processed before authentication** for a valid preflight, while still enforcing authentication and authorization on the actual request.

This lesson aims to help you:

- Understand origins and the conditions that trigger preflight.
- Read CORS request and response headers accurately.
- Master the order **CorsFilter → Authentication → Authorization → Controller** in Servlet Spring Security.
- Run a **Spring Boot 3.x + Spring Security 6 + Java 17+** example.
- Test `OPTIONS` succeeding without credentials, while the actual `GET` still requires authentication.
- Distinguish CORS from **CSRF**, `401`/`403` errors, and factors blocking `OPTIONS` in **proxies, ingresses, CDNs, and API gateways**.

## 2. Origin: scheme, hostname, and port

An origin is the combination **scheme + hostname + port**. CORS is the mechanism enforced by browsers when JavaScript on one origin wants to access a resource on another origin.

| Frontend | API | Same origin? | Reason |
| --- | --- | --- | --- |
| http://localhost:5173 | http://localhost:8080/api/profile | No | Different port. |
| https://app.example.test | https://api.example.test/profile | No | Different host. |
| http://app.example.test | https://app.example.test/api | No | Different scheme. |
| https://example.test | https://example.test/api | Yes | Scheme, host, and default port match. |
| https://example.test:443 | https://example.test/api | Yes | Port 443 is the default for HTTPS. |

**CORS is not authentication or a firewall.** An HTTP client such as `curl` can attach any `Origin`; it does not obey browser response-reading restrictions. Allowing an origin does not prove the caller has permission to view data. The backend must still verify credentials, permissions, and input.

**CORS also does not block every cross-origin request before it reaches the server.** Simple requests can actually be sent, and the browser only stops JavaScript from reading the response if the server withholds CORS permission. This is especially important when designing CSRF protection.

## 3. When does a browser need to send an OPTIONS preflight?

A cross-origin request typically needs a preflight if it uses a method or request headers outside the **CORS-safelisted** set. Familiar cases:

| Actual request JavaScript intends to send | Usually triggers preflight? | Explanation |
| --- | --- | --- |
| GET, no custom headers | No | Can qualify as a simple request. |
| GET with Authorization | Yes | `Authorization` is not a CORS-safelisted header. |
| GET with X-Request-Id | Yes | Custom header is not safelisted. |
| POST with Content-Type: application/json | Yes | JSON is not in the safelisted `Content-Type` group. |
| POST with Content-Type: application/x-www-form-urlencoded and safe headers | Usually no | Can qualify as a simple request. |
| POST with multipart/form-data meeting safelist conditions | Usually no | A simple form upload may not need preflight. |
| Cross-origin PUT, PATCH, or DELETE | Yes | Method is outside `GET`/`HEAD`/`POST`. |
| GET to the same origin | No CORS preflight | No cross-origin boundary to check. |

The basic safelisted request methods are **GET, HEAD, POST**. The `Content-Type` values generally permitted within safelist conditions are **application/x-www-form-urlencoded, multipart/form-data, and text/plain**; additional Fetch Standard constraints still apply. Do not look only at the method name and ignore headers.

Browsers maintain a **preflight cache** separate from the regular HTTP cache. Thus a second call may skip `OPTIONS` while still being a preflight-capable request, as long as the cached result remains valid. That does not mean the browser or server disabled CORS.

**Normal frontends do not need to send `OPTIONS` manually.** The browser handles it automatically before the actual request. Using `curl` to simulate `OPTIONS` only tests the server; it does not populate the browser's preflight cache.

## 4. What does preflight ask and what does it omit?

Suppose the browser needs `GET /api/profile` with both `Authorization` and `X-Request-Id`. It may send:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization,x-request-id
~~~

Key distinctions:

1. **OPTIONS** is the method of the preflight step.
2. **Access-Control-Request-Method: GET** asks whether the **actual request's** method is allowed.
3. **Access-Control-Request-Headers** lists the **header names** the browser plans to send, not the token value.
4. **Origin** is the frontend's origin, not the backend URI.
5. Browser preflight normally **does not carry `Authorization` or session cookies such as `JSESSIONID`**; therefore it cannot be required to log in like the actual request.
6. Other HTTP headers may appear depending on the browser, without changing the meaning of these three primary CORS fields.

A server allowing the request may return:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization,x-request-id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

This is an illustrative response. Spring's `CorsFilter` usually returns **200** for a valid preflight; an API gateway may return **204 No Content**. Header order, casing, and how **Vary** lines are combined may vary as long as the semantics are right.

Each header has a distinct role:

| Header | Meaning |
| --- | --- |
| Origin | Actual origin of the requesting page/browser. |
| Access-Control-Request-Method | Intended method of the actual request. |
| Access-Control-Request-Headers | Names of the request headers that will appear on the actual request. |
| Access-Control-Allow-Origin | Origin accepted by the server; for credentialed requests, never use an uncontrolled wildcard. |
| Access-Control-Allow-Methods | Methods allowed from this origin. |
| Access-Control-Allow-Headers | Request headers permitted to be sent. |
| Access-Control-Allow-Credentials | Lets the browser expose credentials under CORS policy when set to `true`. |
| Access-Control-Max-Age | How long the browser may cache the **preflight result**; not data TTL. |
| Vary | Guides shared caches to distinguish responses by Origin/method/headers asked. |
| Access-Control-Expose-Headers | Set on the actual response so JavaScript can read non-safelisted response headers. |

Only after preflight passes does the browser send the actual `GET`:

~~~http
GET /api/profile HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Authorization: Bearer <access-token>
X-Request-Id: request-101
~~~

**A 200 preflight does not guarantee a 200 GET.** The `GET` request may return 401 due to missing credentials, 403 due to insufficient permissions, or another status from business logic. When the actual response includes valid CORS headers, the frontend can read the 401/403 status and handle login state appropriately.

## 5. Why process CORS before authentication?

Spring Security Servlet documentation states clearly that CORS must be processed **before Spring Security authentication**, because preflight requests usually lack cookies such as **JSESSIONID**. If an authentication filter runs first and requires a session on all requests, `OPTIONS` gets a 401/403 and terminates before the CORS handler is ever reached.

Wrong flow:

~~~text
Browser: OPTIONS /api/profile
  |
  v
Spring Security authentication filter
  |
  +--> Cookie/Authorization missing
  |
  +--> 401 Unauthorized (or redirect to login)
  |
  X   CORS headers never generated
  |
Browser: blocks flow, never sends actual GET.
~~~

Right flow:

~~~text
Browser: OPTIONS + Origin + Access-Control-Request-Method
  |
  v
CorsFilter / CORS processing integrated into SecurityFilterChain
  |
  +--> Checks origin, requested method, requested headers
  |      |
  |      +--> Valid: returns CORS headers, ends preflight
  |      |
  |      +--> Invalid: rejects CORS
  |
  X   Does not require auth for preflight

Browser: actual GET + Authorization/Cookie if present
  |
  v
CORS validation of actual request
  |
  v
Authentication -> Authorization -> Controller
  |
  v
Actual response + matching CORS headers
~~~

Saying "CORS before Spring Security" does not require **manually creating a Servlet `CorsFilter` bean** with the lowest order. Spring Security 6 supports **http.cors(Customizer.withDefaults())** to integrate `CorsFilter` at the right position in the security filter chain when a suitable configuration source exists.

**Do not confuse ordinary `OPTIONS` with CORS preflight.** Preflight carries markers such as `Origin` and `Access-Control-Request-Method`. An `OPTIONS` request lacking those headers may continue through authorization under the system's default policy.

### Is `permitAll` on OPTIONS enough?

The following configuration **is not a complete CORS solution**:

~~~java
// Illustrative pattern that is insufficient to replace CorsFilter:
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Even if `OPTIONS` is no longer blocked by authentication, the browser still requires matching **Access-Control-Allow-Origin**, **Allow-Methods**, and **Allow-Headers**; without them, preflight still fails. Conversely, with `CorsFilter` in the right place, you do not need to open **all `OPTIONS`** on every URL just to make preflight work.

Never disable security on `GET`/`POST` to fix `OPTIONS`; actual requests must remain authenticated and authorized as before.

## 6. CORS differs from authentication, authorization, and CSRF

| Goal | Typical component | Applies to preflight? |
| --- | --- | --- |
| Is the origin allowed to exchange cross-origin data? | CORS policy / `CorsFilter` | **Yes**, this is the required check. |
| Who is calling the API? | Spring Security authentication, session/JWT/Basic | **Do not use preflight to check user identity**; check the actual request. |
| Is the user allowed to read/modify the resource? | Authorization roles/scopes/ownership | **Check the actual request**, do not infer from CORS. |
| Could a state-changing request from another page exploit auto-sent credentials? | CSRF tokens, `Origin` validation, and additional controls | **Check on actual state-changing requests**, do not rely on preflight as sole defense. |

**CORS is not a complete anti-CSRF layer.** A simple cross-origin form `POST` can skip preflight and still hit the server if the backend lacks CSRF protection. With cookie-based sessions, consider CSRF tokens and `SameSite` alongside additional measures. If an app uses HTTP Basic where the browser auto-sends credentials, CSRF risk must also be analyzed.

**Do not disable `csrf()` just to handle `OPTIONS`.** This demo exposes only `GET` endpoints, so default CSRF stays enabled. When opening `POST`, `PUT`, or `DELETE`, determine authentication and CSRF policies separately; a passing `OPTIONS` preflight does not guarantee an actual `POST` will not get 403.

## 7. Spring Boot 3.x + Java 17+ demo with `SecurityFilterChain`

The project uses Spring MVC, embedded Tomcat, and Spring Security 6. Two endpoints:

- **GET /api/public/ping** is public, suitable for browsers to test preflight without exposing credentials.
- **GET /api/profile** requires HTTP Basic authentication; preflight is accepted before authentication, while an unauthenticated actual `GET` must return 401.

Spring Boot **3.3.13** is used for a consistent dependency set in this example. For new projects, pick a Boot release still under maintenance support and check framework changes.

### 7.1. File structure

~~~text
cors-preflight-demo/
  pom.xml
  src/main/
    java/com/example/corsdemo/
      CorsPreflightDemoApplication.java
      WebSecurityConfiguration.java
    resources/
      application.properties
  src/test/
    java/com/example/corsdemo/
      CorsPreflightDemoApplicationTests.java
~~~

### 7.2. Complete `pom.xml`

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
    <artifactId>cors-preflight-demo</artifactId>
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

Do not use **WebSecurityConfigurerAdapter**, as Spring Security 6 moved to **SecurityFilterChain**-based configuration.

### 7.3. `application.properties`

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=cors-preflight-demo
~~~

### 7.4. Main class and controller

Create **src/main/java/com/example/corsdemo/CorsPreflightDemoApplication.java**:

~~~java
package com.example.corsdemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CorsPreflightDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsPreflightDemoApplication.class, args);
    }
}

@RestController
class DemoApiController {

    @GetMapping("/api/public/ping")
    public ResponseEntity<Map<String, String>> ping() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-public")
                .body(Map.of("message", "pong"));
    }

    @GetMapping("/api/profile")
    public ResponseEntity<Map<String, String>> profile(Principal principal) {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-profile")
                .body(Map.of("user", principal.getName(),
                             "status", "authenticated"));
    }
}
~~~

One public class is declared in the matching file; the package-private controller in the same package is discovered by component scanning. **Principal** is populated only when the actual request has been authenticated per `SecurityFilterChain`.

The **X-Request-Id** header is a sample value to test **Access-Control-Expose-Headers**; in production, derive request IDs from tracing/middleware.

### 7.5. CORS and Security configuration

Create **src/main/java/com/example/corsdemo/WebSecurityConfiguration.java**:

~~~java
package com.example.corsdemo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/api/profile").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo-pass")
                .roles("LEARNER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Explanation of key decisions:**

1. **.cors(Customizer.withDefaults())** integrates CORS into Spring Security. With a **UrlBasedCorsConfigurationSource** bean present, Spring Security knows which source holds the policy.
2. **setAllowedOrigins** contains the **frontend origin**, not the backend address. Host and port must match exactly, e.g., 5173 differs from 3000.
3. **setAllowedMethods(List.of("GET"))** specifies the **actual request** methods permitted. Preflight uses `OPTIONS`, while **Access-Control-Request-Method** asks for `GET`; you do not have to add `OPTIONS` to this list.
4. **setAllowedHeaders** specifies the request header names the frontend may send. Allowing **Authorization** permits the header name only—it does not mean the server accepts invalid tokens.
5. **setExposedHeaders** lets JavaScript read the **X-Request-Id** response header, which is outside the response-header safelist.
6. **setAllowCredentials(true)** illustrates credentialed CORS for one explicit origin. This carries high trust; systems not needing cross-origin cookies/credentials should consider `false`. Never combine `true` with **allowedOrigins="*"**.
7. **setMaxAge(3600L)** controls browser preflight caching, not caching profile data for one hour.
8. **anyRequest().denyAll()** shows that unlisted actual endpoints are not opened up automatically. Valid preflight requests are handled by `CorsFilter` ahead of the actual-request authorization rules.
9. **Default CSRF is not disabled**, because the demo exposes only `GET` endpoints. There is no reason to drop CSRF to fix CORS.
10. **{noop}demo-pass** and HTTP Basic are for local demo only. Production requires a secure authentication provider, proper password hashing, HTTPS, and secret management; never hardcode passwords in source.

**Note:** do not declare an additional standalone Servlet **CorsFilter** bean with a different policy, to avoid duplicate processing. With multiple **SecurityFilterChain**s or multiple CORS sources, bind the right policy to the chain serving each target path. If using Spring MVC global config/**@CrossOrigin** instead of a source bean, still enable CORS integration in Spring Security and verify merge rules.

### 7.6. Build, test, and start

From the directory containing `pom.xml`, with Maven and Java 17+:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

The server listens on **http://localhost:8080**. Once Maven resolves dependencies, these commands run without needing a frontend. The test command runs the test class shown later; the second command starts the server after tests pass.

## 8. Testing OPTIONS and actual requests with `curl`

**`curl` does not issue preflight requests automatically like a browser.** To reproduce preflight, call `OPTIONS` with browser-like headers. The results below assume direct access to Spring Boot, with no proxy altering responses.

### A. Valid preflight without Authorization

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,x-request-id'
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization,x-request-id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
~~~

`Vary` and a few other headers may appear. Order and casing are unimportant; what matters is that a valid `OPTIONS` succeeds **without credentials**, whereas the actual profile endpoint still enforces authentication.

### B. Actual GET missing credentials

~~~bash
curl -i -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/profile'
~~~

Expect **401 Unauthorized** from the demo's HTTP Basic authentication. The response can still include **Access-Control-Allow-Origin** so the allowed frontend can read the error. **Preflight PASS + actual 401** is not a contradiction.

### C. Actual GET with valid credentials

~~~bash
curl -i -u learner:demo-pass \
  -H 'Origin: http://localhost:5173' \
  -H 'X-Request-Id: web-101' \
  'http://localhost:8080/api/profile'
~~~

Expect **200 OK** and JSON containing:

~~~json
{"user":"learner","status":"authenticated"}
~~~

JSON property order may vary. The response may include **Access-Control-Expose-Headers: X-Request-Id** along with the sample header **X-Request-Id: demo-profile**.

**-u** sends HTTP Basic credentials on the actual request. A browser preflight will not attach credentials from `-u`, because those are two separate client behaviors. In production, never place passwords directly in terminal history or source code.

### D. Invalid Origin

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: GET'
~~~

In the demo, the CORS processor typically returns **403 Forbidden/Invalid CORS request** because the origin is not allowlisted. This is a **CORS** rejection; it does not mean the user lacks a role or sent a bad JWT.

### E. Disallowed method

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE'
~~~

Only `GET` is allowed in the CORS config, so preflight requesting `DELETE` must be rejected. Even if `DELETE` were allowed in CORS, you would still need `@DeleteMapping`, authentication, authorization, and CSRF protection where applicable.

### F. Disallowed header

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-unknown-header'
~~~

**x-unknown-header** is absent from `allowedHeaders`, so preflight is rejected per policy. Do not set `allowedHeaders="*"` unconditionally without reviewing custom headers and the trust boundary.

### G. Plain OPTIONS, not a preflight

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/profile'
~~~

This request lacks **Origin** and **Access-Control-Request-Method**, so it is not treated as a valid CORS preflight. With **anyRequest().denyAll()**, it can return 403. Do not use a headerless `OPTIONS` result to dispute the success of preflight test case A.

## 9. JavaScript/browser test without embedding passwords

A real frontend at **http://localhost:5173** can test the public endpoint:

~~~javascript
async function loadPing() {
  const response = await fetch(
    "http://localhost:8080/api/public/ping",
    {
      method: "GET",
      headers: { "X-Request-Id": "browser-1" }
    }
  );

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  const payload = await response.json();
  const requestId = response.headers.get("X-Request-Id");
  console.log(payload.message, requestId);
}

loadPing().catch(console.error);
~~~

When the browser sees a cross-origin `GET` carrying **X-Request-Id**, it normally sends an `OPTIONS /api/public/ping` preflight first and then sends `GET`. The console can print **pong demo-public** because the public API returns `pong` and exposes the response header.

**If no OPTIONS appears:** the browser may be using its preflight cache, the frontend may be going through a same-origin dev proxy, or the request no longer carries the triggering header. Inspect **DevTools Network**, Request URL, Origin, and actual request list; do not equate "no OPTIONS seen" with "CORS is off."

**Do not try to fix it with fetch mode `"no-cors"`.** Under `no-cors`, the response becomes **opaque** and JavaScript cannot read the body, status, or headers as needed. The real fix is configuring the server and proxy properly.

### Cookies/credentials in `fetch`

If an API uses cross-origin session cookies and is designed to permit them, the frontend typically needs:

~~~javascript
fetch("https://api.example.test/account", {
  credentials: "include"
});
~~~

This snippet illustrates syntax only; the example URL is not an endpoint of the Basic demo. With **credentials: include**, the server needs **Access-Control-Allow-Credentials: true** and an explicit **Access-Control-Allow-Origin**, not a wildcard. Cookies also remain governed by **SameSite**, **Secure**, **Domain**, **Path**, HTTPS, and browser policies for third-party cookies.

**Preflight does not need to carry JSESSIONID to authenticate the user.** The browser decides whether to attach cookies on the actual request based on credentials mode and cookie policy. If the actual request uses a JavaScript-set `Authorization` header, **Authorization** must be listed in `Access-Control-Allow-Headers`.

## 10. Common mistakes when combining CORS and security

### 10.1. Only adding `@CrossOrigin` on the controller

**@CrossOrigin** and **WebMvcConfigurer#addCorsMappings** configure CORS at Spring MVC's `HandlerMapping`. Yet if the security filter blocks `OPTIONS` before `HandlerMapping` runs, the annotation may never apply to that request.

Two common valid setups:

1. Configure a **CorsConfigurationSource** bean and **http.cors(...)** as in the demo.
2. Configure MVC global CORS/`@CrossOrigin` and enable **http.cors(...)** so Spring Security pulls the MVC CORS source when appropriate.

Review global + local merging rules and avoid declaring two conflicting policies. With multiple `SecurityFilterChain`s, do not assume chain A's policy applies to preflight routed to chain B.

### 10.2. Permitting `OPTIONS` yet missing CORS headers

If you only **permitAll OPTIONS**, preflight may receive 200/204, yet the browser still blocks the actual request because **Access-Control-Allow-Origin** or the requested method/header is missing. The CORS policy itself must execute.

### 10.3. Using wildcard when credentials are enabled

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

This is **not** a valid credentialed CORS response for browsers. Spring Framework also rejects **allowedOrigins="*"** combined with **allowCredentials=true** under standard configuration. If dynamic tenant origins are required, use **allowedOriginPatterns** with a managed list/pattern rather than reflecting every `Origin` unchecked.

### 10.4. Treating every 403 as having the same cause

- **403 on preflight**: may be a disallowed origin, method, or header.
- **403 on actual request**: may be authorization, CSRF, actual CORS check, WAF, or proxy.
- **401 on preflight**: usually an auth filter/gateway running ahead of CORS.
- **401 on actual request**: usually missing/invalid credentials per the authentication scheme.
- **302 to a login page on preflight**: browsers often treat this as a CORS error or invalid redirect; never require the browser to log in via `OPTIONS`.

Always identify **which request returned the status** and **from which layer** before changing code.

## 11. Reverse proxies, ingresses, API gateways, and processing order

A real request may traverse multiple components:

~~~text
Browser
  |
  v
CDN / WAF / API Gateway (may block OPTIONS)
  |
  v
Ingress / Nginx (may rewrite paths, return 204, redirect)
  |
  v
Spring Boot Servlet filter chain
  |
  v
CorsFilter -> Authentication -> Authorization -> Controller
~~~

**If the reverse proxy returns 401 before Spring, enabling `http.cors` in the backend is not enough.** You must agree on where `OPTIONS` is handled:

**Backend-managed option:** the proxy preserves `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` and forwards `OPTIONS` to Spring. Edge auth layers do not block preflight, while still protecting actual requests.

**Gateway-managed option:** the gateway responds **200/204** to preflight per origin/method/header policy ahead of gateway authentication; actual requests then pass through authentication and the backend. Actual responses—including 401/403—need matching CORS headers. Avoid having both the gateway and backend emit conflicting or duplicate `Access-Control-Allow-Origin` headers.

**Common proxy pitfalls:**

- Edge allows only `GET`/`POST` and returns **405** for `OPTIONS`.
- OAuth2 proxy redirects preflight to a login page with 302/303.
- Public HTTPS endpoint redirects `OPTIONS` from HTTP, causing browser redirect or mixed-content errors.
- Ingress strips `Origin`/`Access-Control-Request-*`, preventing Spring from recognizing preflight.
- Proxy rewrites **/api/profile** to **/profile** while the CORS source only matches **/api/**.
- CDN caches a preflight response for Origin A and serves it to Origin B due to wrong cache keys/`Vary`.
- Gateway emits wildcard `Allow-Origin` while backend emits an explicit origin and `Allow-Credentials: true`.
- WAF blocks `OPTIONS` or the `Authorization` name inside `Access-Control-Request-Headers` even though actual `GET` is allowed.

**Vary** matters whenever CORS responses differ by `Origin`, requested method, and requested headers. If a CDN caches preflight, partition properly across those dimensions so responses are never reused across origins. **Access-Control-Max-Age** guides browser preflight caching; it does not set API data TTL.

For actual requests returning private data, configure **Cache-Control** and shared-cache policies separately. Never equate "allowing an origin to read a response" with "allowing a CDN to publicly cache that response."

### CORS does not protect against spoofed Origin outside browsers

`curl` can send **Origin: http://localhost:5173** from anywhere. That does not make `curl` a trusted frontend. APIs must always authenticate actual requests, enforce resource authorization, and defend against CSRF according to the auth model. CORS is a browser control, not an API client verifier.

## 12. `MockMvc` integration tests verifying the right order

Create **src/test/java/com/example/corsdemo/CorsPreflightDemoApplicationTests.java**:

~~~java
package com.example.corsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPreflightDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization,x-request-id"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true"));
    }

    @Test
    void actualRequestWithoutLoginIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173"));
    }

    @Test
    void actualRequestWithLoginSucceeds() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("learner", "demo-pass"))
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void unknownOriginIsRejected() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://untrusted.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void forbiddenMethodIsRejected() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Key takeaways:

- **@SpringBootTest + @AutoConfigureMockMvc** loads the application context including Spring Security filters.
- Valid preflight to a protected endpoint succeeds **without credentials**.
- Unauthenticated actual request still returns **401**.
- Actual request with valid HTTP Basic returns **200** and `Principal` is populated in the controller.
- Wrong origin or method is rejected by the CORS policy.
- These tests do not replace a real browser, CDN, HTTPS, redirects, preflight cache, or cookie-blocking policies.

When adding an actual `POST`, add **CSRF and authorization** integration tests; `OPTIONS 200` does not prove `POST` will be accepted.

## 13. Spring WebFlux and reactive security

If the app uses **spring-boot-starter-webflux** on Reactor Netty, Servlet **CorsFilter** and **SecurityFilterChain** are not the right APIs for the reactive stack. WebFlux has:

- **CorsWebFilter**.
- **SecurityWebFilterChain** and **ServerHttpSecurity.cors(...)**.
- **org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource**.
- **WebFluxConfigurer#addCorsMappings** and reactive `HandlerMapping` CORS handling.

The principle remains **preflight is processed before authentication**. However, never copy Servlet MVC bean types into WebFlux expecting them to run. Especially when a project has both `web` and `webflux` starters, check whether Boot configured the app as Servlet or Reactive; Spring MVC is usually chosen by default if both are present.

Reactive config example purely for recognizing the APIs, not a standalone runnable program:

~~~java
package com.example.reactivecors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class ReactiveCorsSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .cors(Customizer.withDefaults())
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(List.of("Authorization", "X-Request-Id"));
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

This is configuration for a separate WebFlux project that already has a Spring Boot main class and reactive security dependency. Depending on Spring Security version, filter ordering and integration across multiple `SecurityWebFilterChain`s must be tested just like the Servlet case.

## 14. Diagnosing in the actual request order

To pinpoint the error in DevTools Network:

1. Check **Request URL**: is it truly cross-origin? Verify scheme, host, port, and proxy.
2. Look for an **OPTIONS** request; inspect `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
3. Check the `OPTIONS` status. If **401/302**, suspect authentication/gateway running ahead of CORS. If **403**, suspect origin/method/header policy or WAF.
4. Check **Access-Control-Allow-Origin/Methods/Headers** and credentials headers; 200 alone is insufficient.
5. Check whether the browser sent the **actual request** after preflight.
6. If actual was sent, inspect status 200/401/403/404/500 and causes in authentication, authorization, CSRF, or business logic.
7. If `curl` to local works yet public domain fails, locate which proxy/CDN/ingress layer alters the request/response.
8. If there is no preflight despite custom headers, consider browser preflight caching or a same-origin dev proxy.
9. Do not rely solely on generic **TypeError: Failed to fetch** messages; network, TLS, mixed content, CSP, DNS, or proxy errors can also produce it.
10. Inspect logs safely: record request ID, `Origin`, method/path/status; **never log raw tokens, passwords, or session cookies**.

### Error matrix

| Observed result | Likely interpretation | Action |
| --- | --- | --- |
| OPTIONS 401 | Authentication runs before CORS or auth proxy blocks it | Integrate `CorsFilter` before auth, or configure edge to handle preflight. |
| OPTIONS 302 to login | Auth entry point tries to redirect `OPTIONS` | Never require login on `OPTIONS`; handle CORS early. |
| OPTIONS 403 Invalid CORS request | Origin/method/header/path outside policy | Compare allowlist with `Access-Control-Request-*`; do not open blindly. |
| OPTIONS 200 yet missing Allow-Origin | `OPTIONS` permitted without passing through CORS processor | Configure CORS source + filter or edge properly. |
| Valid OPTIONS 204 from ingress, app sees nothing | Edge handles preflight directly | Inspect edge policy, actual requests, and headers. |
| OPTIONS PASS, actual 401 | Caller lacks credentials | Fix authentication on actual request; do not touch CORS. |
| OPTIONS PASS, actual 403 | Authorization/CSRF/CORS actual check | Check security logs and separate 403 sources. |
| curl GET 200, browser blocked | `curl` does not enforce browser CORS | Test in browser/`OPTIONS` with real `Origin` and credentials mode. |
| Public domain fails, localhost works | Proxy/ingress/CDN/auth gateway alters flow | Compare response headers hop by hop and route by route. |
| Cookie not reaching API | `SameSite`/`Secure`/`Domain`/`Path`/credentials/browser policy | Inspect cookies in DevTools; never force preflight to carry cookies. |

## 15. Production checklist

- [ ] Identify exact frontend **scheme + host + port** and trusted origins.
- [ ] Distinguish **simple requests** from preflighted requests caused by method, header, or `Content-Type`.
- [ ] Ensure CORS processing runs before authentication on the responsible hop.
- [ ] With Spring Security Servlet, enable **http.cors(...)** and use **CorsConfigurationSource** or compatible MVC CORS config.
- [ ] Do not replace CORS with a bare **OPTIONS permitAll** rule.
- [ ] Separate preflight permission from **authentication/authorization/CSRF** on actual requests.
- [ ] Set `allowedOrigins`, `allowedMethods`, and `allowedHeaders` using least privilege; never reflect arbitrary `Origin`.
- [ ] Never combine wildcard `Allow-Origin` with `Allow-Credentials: true`.
- [ ] Verify credential-free preflight PASSES; credential-free actual request FAILS.
- [ ] Verify invalid origins, methods, and headers are genuinely rejected.
- [ ] Observe `Access-Control-Allow-*`, `Vary`, and `Max-Age` over real HTTP.
- [ ] Ensure API gateway/WAF/CDN/ingress does not redirect or block `OPTIONS` before CORS.
- [ ] Ensure actual 401/403 responses include matching CORS headers so the frontend can handle them.
- [ ] Check browser credentials mode and cookie rules; never use `fetch` `no-cors` to dodge policy.
- [ ] Test multi-chain security/filter order, reverse proxy path mapping, and CSRF on state-changing methods.
- [ ] Never log bearer tokens, Basic credentials, session IDs, or CSRF tokens while debugging.

## 16. Knowledge self-check

**1. Why does the browser send OPTIONS before a GET carrying Authorization?**  
`Authorization` is outside the CORS safelist. The browser asks the server to approve the origin, method, and header name before sending the actual `GET`.

**2. In preflight, what does `Access-Control-Request-Method: GET` mean?**  
`GET` is the intended method of the actual request; the method currently being sent is `OPTIONS`.

**3. Why shouldn't JSESSIONID be required on preflight?**  
Browser preflights usually omit session cookies; authentication occurs on the actual request after CORS approves it.

**4. Are preflight 200 and actual GET 401 contradictory?**  
No. CORS permission does not grant access to read the profile; authentication is still enforced.

**5. Is permitting OPTIONS alone enough for the browser to send the actual request?**  
No. The response must also carry valid `Access-Control-Allow-*` headers.

**6. Why can a GET trigger preflight while a POST sometimes does not?**  
A `GET` with custom headers/`Authorization` triggers preflight; a simple `POST` using a safelisted `Content-Type` and no non-safelisted headers may skip preflight.

**7. Can `Access-Control-Allow-Origin: *` be combined with `Allow-Credentials: true`?**  
No, not for credentialed browser requests; use an explicit origin or controlled pattern policy instead.

**8. Does CORS replace CSRF protection?**  
No. Simple requests can still be sent; whenever credentials are attached automatically, state-changing operations must be protected.

**9. What if Spring returns OPTIONS 200 on localhost yet the public domain returns 401?**  
Inspect the CDN/WAF/API gateway/ingress/auth proxy and each hop's policy before editing app code.

**10. Why doesn't `curl -u` automatically send OPTIONS?**  
`curl` does not implement the browser CORS preflight protocol; send a separate `OPTIONS` request to test it.

**11. What is the role of `Vary: Origin`?**  
It helps shared caches distinguish responses depending on `Origin`, reducing the risk of serving wrong CORS permissions across origins.

**12. When is `CorsWebFilter` needed instead of `CorsFilter`?**  
When using the Spring WebFlux reactive stack rather than Servlet MVC.

## 17. References

- **Spring Security – Servlet CORS:** https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html (CORS before authentication, `CorsFilter`, `UrlBasedCorsConfigurationSource`).
- **Spring Framework – MVC CORS:** https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html (preflight/simple/actual, credentials, `@CrossOrigin`, `CorsConfiguration`).
- **Spring Security – CSRF:** https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html (distinguishing CORS from CSRF protection).
- **Spring Boot – Servlet Web Applications:** https://docs.spring.io/spring-boot/reference/web/servlet.html (Servlet web stack).
- **MDN – CORS:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- **MDN – Preflight request:** https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request
- **MDN – Access-Control-Allow-Headers:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers
- **WHATWG Fetch Standard:** https://fetch.spec.whatwg.org/ (CORS-preflight, credentials mode, safelisted methods/headers).