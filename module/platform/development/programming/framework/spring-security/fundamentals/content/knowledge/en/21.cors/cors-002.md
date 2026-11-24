# Origin Consists of Protocol, Hostname, and Port in CORS

A frontend running at `http://localhost:5173` calls a Spring Boot API at `http://localhost:8080`. Both applications are on the same machine, share the hostname `localhost`, and use the HTTP protocol, yet the browser still treats them as **cross-origin** because their port numbers differ. Likewise, `https://shop.example.test` does not share an origin with `http://shop.example.test` because the protocol differs, and `https://api.example.test` does not share an origin with `https://shop.example.test` because the hostname differs.

That is the foundational concept of **Cross-Origin Resource Sharing (CORS)**: for HTTP(S) URLs, an origin is determined by **protocol (scheme), hostname, and effective port**. CORS allows a target website to advertise exceptions so scripts from other origins may read responses under browser policy; CORS **does not replace** user authentication, authorization, or CSRF protection.

This lesson belongs to the **CORS** group of **Spring Security - fundamentals**, using Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x with Servlet/Spring MVC. We will compute origins, compare URLs and sites, read HTTP headers, understand preflight, configure CORS accurately, and test changes to a single component: scheme, hostname, or port.

## 1. Definition and the three components of an origin

For a standard HTTP(S) URL:

~~~text
https://app.example.test:8443/orders?page=2#summary
└─┬─┘ └─────────┬──────┘ └┬─┘ └───────────┬───────┘
scheme        hostname    port       path/query/fragment

Origin = (scheme, hostname, effective port)
       = https://app.example.test:8443
~~~

- **Scheme**: URL protocol, typically `http` or `https`.
- **Hostname**: for example `app.example.test`, `localhost`, `127.0.0.1`, `api.example.test`.
- **Effective port**: the explicitly specified port, or the default port if omitted in the URL.

**Not part of the origin:** path (`/orders`), query (`?page=2`), fragment (`#summary`), Controller name, HTTP method name, login state, or user permissions. Paths can affect server routing and authorization, but they do not change a URL's origin.

Use this tuple to compare two URLs:

~~~text
same-origin = same scheme
          AND same hostname
          AND same effective port
~~~

This reflects the result after the browser **normalizes URLs/origins according to the standard**, rather than directly comparing unnormalized raw input strings.

## 2. Same-origin URL comparison table

Take the reference URL `https://shop.example.test/cart`.

| Second URL | Protocol | Hostname | Effective port | Same origin? |
| --- | --- | --- | --- | :---: |
| `https://shop.example.test/orders` | https | shop.example.test | 443 | ✅ |
| `https://shop.example.test/cart?item=1` | https | shop.example.test | 443 | ✅ |
| `https://shop.example.test:443/checkout` | https | shop.example.test | 443 | ✅ |
| `https://shop.example.test:8443/cart` | https | shop.example.test | 8443 | ❌ |
| `http://shop.example.test/cart` | http | shop.example.test | 80 | ❌ |
| `http://shop.example.test:443/cart` | http | shop.example.test | 443 | ❌ |
| `https://api.example.test/cart` | https | api.example.test | 443 | ❌ |
| `https://www.shop.example.test/cart` | https | www.shop.example.test | 443 | ❌ |
| `https://SHOP.example.test/cart` | https | shop.example.test after normalization | 443 | ✅ |

Each reason:

- URLs differing only in **path/query** can still be same-origin.
- `:443` on HTTPS is the default port, so `https://shop.example.test:443` has the same origin as `https://shop.example.test`.
- `:8443` differs from 443, so the origin differs even with the same hostname.
- HTTP and HTTPS are not same-origin even if the hostname or numeric port matches.
- Two hostnames like `shop.example.test` and `api.example.test` are not automatically same-origin even though both are registered under `example.test`.
- DNS resolving two hostnames to the same IP **does not** make them same-origin.

### Default ports to remember

~~~text
http://example.test      = http://example.test:80
https://example.test     = https://example.test:443

http://example.test:443  != https://example.test:443
https://example.test:80  != https://example.test
~~~

The `=` sign here only means **same origin** for HTTP(S) URLs; it does not claim the two URLs have identical text strings or identical server behavior.

## 3. Localhost, 127.0.0.1, and frontend dev servers

A project might run Vite at `http://localhost:5173` and Spring Boot at `http://localhost:8080`. Because the ports differ, a script in the Vite page calling the Spring API is a cross-origin request.

| Frontend | API | Same origin? | Cause |
| --- | --- | :---: | --- |
| `http://localhost:5173` | `http://localhost:8080` | ❌ | Different port |
| `http://localhost:5173` | `http://localhost:5173/api` | ✅ | Only path differs |
| `http://localhost` | `http://localhost:80` | ✅ | Default port 80 |
| `http://localhost:8080` | `http://127.0.0.1:8080` | ❌ | Different hostname |
| `http://localhost:8080` | `https://localhost:8080` | ❌ | Different scheme |
| `https://app.example.test` | `https://api.example.test` | ❌ | Different hostname |

**`localhost` and `127.0.0.1` are not the same hostname**, even though both can reach the same machine. Origin rules do not perform DNS lookups to verify whether two hosts ultimately point to the same IP.

You can use a **dev proxy**: the browser only calls `http://localhost:5173/api/orders`, while the dev server proxies the request internally to `http://localhost:8080/api/orders`. Then the URL accessed by the browser shares the same origin as the frontend page, so the browser does not require CORS for that connection. The backend service still runs on port 8080; the browser simply does not talk to it directly.

Do not use `allowedOrigins("*")` merely to suppress local development errors. You can explicitly allow `http://localhost:5173` in Spring or configure an explicit dev proxy.

## 4. Origin differs from URL, site, cookie domain, and server Host

| Term | Example | Used for |
| --- | --- | --- |
| Full URL | `https://app.example.test:8443/orders?id=1` | Identifying a resource |
| Origin | `https://app.example.test:8443` | Same-Origin Policy, CORS |
| Hostname | `app.example.test` | One component of an origin |
| Site (schemeful) | Typically `https://example.test` | SameSite cookies, same-site model |
| Cookie Domain | `example.test` if declared as such | Scope of hosts receiving the cookie |
| HTTP Host header | `api.example.test:443` | Target host of an HTTP/1.1 request |
| HTTP Origin header | `https://app.example.test` | Source origin initiating the request |

**Same-site does not mean same-origin:**

~~~text
https://app.example.test  → https://api.example.test

Cross-origin (different hostname)
Yet can be same schemeful site (https + example.test)
~~~

`SameSite` cookies evaluate by site, whereas CORS evaluates by origin. Thus, a frontend and API on two subdomains can be **same-site**, while scripts still require CORS checks when reading responses from the other origin.

Under the *schemeful same-site* model, `http://app.example.test` and `https://app.example.test` are treated as cross-site because their schemes differ. They are also two different origins. A cookie with `Domain=example.test` does not automatically grant JavaScript from any subdomain permission to read data from another origin.

## 5. Port normalization, hostnames, and opaque origins

### Effective port

In HTTP, a URL without a port has an effective port of 80. In HTTPS, a URL without a port has an effective port of 443. Thus `https://app.example.test` and `https://app.example.test:443` share the same origin, even though the URL strings are not identical.

Browsers typically **do not serialize default ports** into origin strings. For instance, `window.location.origin` can return `https://app.example.test` without necessarily including `:443`.

### Hostname normalization

DNS names follow case-insensitivity rules and handle internationalized domain names via IDNA/Punycode. Therefore, you should not compare two raw URLs using ad-hoc string operations. Spring's CORS provides standard configuration and matching components; use them.

### Opaque origin and Origin: null

Not every document has an HTTP(S) tuple origin. Some cases have an **opaque origin**, such as `data:` URLs, certain `file:` documents, or a `sandbox`ed `iframe` without `allow-same-origin`.

A special origin can be serialized in a request as:

~~~http
Origin: null
~~~

`null` here does not mean “no Origin header”, nor is it a safe hostname. Do not add `"null"` to a trusted origin list just to make a local HTML file work, because many untrusted sources produce the exact same serialization.

Not every `blob:` or `about:blank` document has an opaque origin: a script-created `about:blank` document can inherit an origin, and a blob URL can be bound to the environment that created it. This lesson focuses on HTTP(S), where the tuple rule applies directly.

## 6. Java 17+ program computing HTTP(S) origins

The following is **a standalone, compilable Java program** using `java.net.URI` and a record to illustrate default ports. It does not implement full browser rules for opaque origins or internationalized domain names.

Create `OriginDemo.java`:

~~~java
import java.net.URI;
import java.util.Locale;

public class OriginDemo {

    record OriginKey(String scheme, String host, int port) {
    }

    static OriginKey of(String rawUrl) {
        URI url = URI.create(rawUrl);
        String scheme = url.getScheme();
        String host = url.getHost();

        if (scheme == null || host == null) {
            throw new IllegalArgumentException("HTTP(S) URL required");
        }

        scheme = scheme.toLowerCase(Locale.ROOT);
        host = host.toLowerCase(Locale.ROOT);

        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("Unsupported scheme");
        }

        int port = url.getPort();
        if (port == -1) {
            port = scheme.equals("https") ? 443 : 80;
        }

        return new OriginKey(scheme, host, port);
    }

    static boolean sameOrigin(String left, String right) {
        return of(left).equals(of(right));
    }

    public static void main(String[] args) {
        String base = "https://shop.example.test/orders";

        System.out.println(sameOrigin(
                base, "https://shop.example.test:443/cart"));
        System.out.println(sameOrigin(
                base, "http://shop.example.test/cart"));
        System.out.println(sameOrigin(
                base, "https://shop.example.test:8443/cart"));
        System.out.println(sameOrigin(
                base, "https://api.example.test/cart"));
        System.out.println(sameOrigin(
                base, "https://shop.example.test/orders?page=2"));
    }
}
~~~

Commands:

~~~bash
javac OriginDemo.java
java OriginDemo
~~~

Exact stdout for this code:

~~~text
true
false
false
false
true
~~~

In order: default HTTPS port matches; different scheme; different port; different hostname; only query differs. **Do not use this custom helper as a production Origin verification system**; in Spring Security, use `CorsConfiguration` and the framework's CORS processing.

## 7. The HTTP Origin request header

When a script at `https://app.example.test` calls an API at `https://api.example.test`, the browser may send:

~~~http
GET /api/greeting HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

**`Host` indicates the target server; `Origin` indicates the origin causing the request.** The Origin header contains no path/query/fragment:

~~~http
Origin: https://app.example.test
Origin: http://localhost:5173
Origin: https://app.example.test:8443
Origin: null
~~~

Do not write `Origin: https://app.example.test/dashboard?x=1` for a standard HTTP(S) origin.

`Origin` may be absent on some ordinary GET/HEAD requests, and may carry the value `null` in certain cases. Browsers follow rules for setting this header automatically, whereas **curl/Postman and custom HTTP clients can spoof any Origin header**. Hence Origin does not prove a logged-in user and must not be used as a credential.

`Referer` may include the source URL path depending on Referrer-Policy, whereas Origin is designed to express only the origin with more limited information.

## 8. CORS allows sharing responses across origins

The Same-Origin Policy (SOP) restricts scripts from one origin from arbitrarily reading/interacting with resources from another origin. CORS lets a server declare which origins may read responses in a browser context.

Script in `https://app.example.test`:

~~~javascript
fetch("https://api.example.test/api/greeting");
~~~

Because the origins differ in hostname, the browser enforces CORS. The server can allow it via the header:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

What **CORS does not do**:

- Does not turn two origins into the same origin.
- Does not authenticate a user or grant an ADMIN role.
- Does not by default prevent every cross-origin request from **being sent** to the server.
- Does not replace CSRF protection on applications using cookies/sessions.
- Does not block curl or HTTP clients that do not enforce browser policy.

A request may already have reached the server and caused a side effect, while the browser refuses to let the script read the response. This is especially important for HTML form POSTs that do not require preflight.

## 9. CORS preflight: OPTIONS is not a business method

The browser requires an **OPTIONS preflight** before certain cross-origin requests, such as a JSON POST with `Content-Type: application/json` or headers outside the safelisted list.

~~~http
OPTIONS /api/greeting HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Distinguish:

- The method of the preflight request itself is **OPTIONS**.
- `Access-Control-Request-Method: POST` indicates the method of the request that will be sent next if allowed.
- `Access-Control-Request-Headers` lists the intended headers.

The server may reply:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

The response above is an example; exact status and headers depend on configuration. Preflight typically **carries no login cookies/credentials**. Therefore Spring Security needs to process CORS before authentication checks that could reject OPTIONS simply for lacking a session.

Do not fix preflight errors by letting `OPTIONS /**` through unconditionally without configuring origin, method, and headers. CORS only accepts preflight **matching policy**, after which the actual request must still pass authentication, authorization, and CSRF when needed.

## 10. Credentialed CORS and wildcards

If a frontend at `https://app.example.test` needs the browser to send permitted cookies to the API:

~~~javascript
fetch("https://api.example.test/api/greeting", {
  method: "GET",
  credentials: "include"
});
~~~

The browser only sends credentials in accordance with cookie/SameSite/Secure/third-party cookie policies. If the request is credentialed, the server also needs to respond with:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

The following configuration is **not valid** for the browser to share a credentialed response:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

With credentialed CORS, do not use wildcard `*` in `Access-Control-Allow-Origin`; a specific origin is required. When a server responds with a value depending on the request Origin, `Vary: Origin` helps caches distinguish those variants.

Do not enable credentials just because the frontend reports a CORS error. For APIs serving personal data, this is a trust decision: **code at an allowed origin can read responses** when browser and server conditions permit. CORS also does not act as a substitute for a CSRF token when auto-sent cookies are used.

## 11. Spring Boot 3.3 + Spring Security 6.3 Example

We will build a sample API:

- `GET /api/greeting` requires authentication.
- `POST /api/greeting` requires authentication and a CSRF token; stores a demo string in memory.
- Allows cross-origin only from `https://app.example.test` and `http://localhost:5173`.
- CORS-allowed methods: GET, POST.
- To illustrate credentials, tests use HTTP Basic and a demo account.
- Keeps default CSRF enabled rather than disabling it application-wide.
- Unlisted requests are denied via `denyAll`.

### 11.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'origin-cors-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Java files below share the package `example.origincors`. The example requires Gradle or a compatible wrapper.

### 11.2. OriginCorsApplication.java

~~~java
package example.origincors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OriginCorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(OriginCorsApplication.class, args);
    }
}
~~~

Save at `src/main/java/example/origincors/OriginCorsApplication.java`.

### 11.3. SecurityConfig.java

~~~java
package example.origincors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/greeting")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/greeting")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Do not disable CSRF: POST still requires a valid token.
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of(
                "https://app.example.test",
                "http://localhost:5173"
        ));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }
}
~~~

Explanation:

1. `http.cors(Customizer.withDefaults())` integrates CORS processing with Spring Security so preflight is processed before authentication.
2. `setAllowedOrigins(...)` uses exact **origins**, with no path: `https://app.example.test` rather than `https://app.example.test/dashboard`.
3. `https://app.example.test:8443` is not allowed by this allowlist because the port differs.
4. `http://app.example.test` is not allowed because the scheme differs.
5. `http://localhost:5174` is not allowed because the port differs from the 5173 dev server.
6. `setAllowCredentials(true)` is a demo choice; in production enable it only if truly needed and origins are trusted.
7. `allowedMethods` and `allowedHeaders` only govern CORS. They **do not** replace `authorizeHttpRequests`.
8. `anyRequest().denyAll()` blocks out-of-scope URLs.
9. BCrypt `PasswordEncoder` and the in-memory account are for learning only; do not use sample users/passwords outside test environments.
10. CSRF remains enabled by default for POST. HTTP Basic credentials may be remembered/reused by the browser; do not blindly drop CSRF.

### 11.4. GreetingStore.java

~~~java
package example.origincors;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class GreetingStore {

    private final ConcurrentHashMap<String, String> values =
            new ConcurrentHashMap<>();

    public void save(String user, String message) {
        values.put(user, message);
    }

    public String get(String user) {
        return values.getOrDefault(user, "(unset)");
    }

    public void clear() {
        values.clear();
    }
}
~~~

`ConcurrentHashMap` is only a mock store for measuring side effects in tests, not a database or durable persistence mechanism.

### 11.5. GreetingController.java

~~~java
package example.origincors;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greeting")
public class GreetingController {

    private final GreetingStore store;

    public GreetingController(GreetingStore store) {
        this.store = store;
    }

    @GetMapping
    public String read(Authentication auth) {
        return "Hello, " + auth.getName();
    }

    @PostMapping
    public String save(@RequestParam String message,
                       Authentication auth) {
        store.save(auth.getName(), message);
        return "Saved for " + auth.getName() + ": " + message;
    }
}
~~~

CORS allows a browser origin to read responses per policy, yet the Controller is still invoked only when the security chain permits it. `GET` only reads; `POST` modifies the mock store.

## 12. Testing method, origin, and CSRF with MockMvc

In `src/test/java/example/origincors/OriginCorsTest.java`:

~~~java
package example.origincors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OriginCorsTest {

    @Autowired MockMvc mvc;
    @Autowired GreetingStore store;

    @BeforeEach
    void reset() {
        store.clear();
    }

    @Test
    void allowedPreflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://app.example.test"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void differentHostnameFails() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://evil.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void differentSchemeFails() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "http://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void differentPortFails() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test:8443")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void localhostPortIsImportant() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isOk());

        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "http://localhost:5174")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void notAllowedCorsMethodFailsPreflight() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
                .andExpect(status().isForbidden());
    }

    @Test
    void corsDoesNotReplaceAuthentication() throws Exception {
        mvc.perform(get("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void allowedOriginCanReadWithCredentials() throws Exception {
        mvc.perform(get("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .with(httpBasic("lan", "demo123")))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://app.example.test"))
                .andExpect(content().string("Hello, lan"));
    }

    @Test
    void disallowedOriginIsRejectedBeforeController() throws Exception {
        mvc.perform(get("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://evil.example.test")
                .with(httpBasic("lan", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void noOriginHeaderDoesNotRequireCorsHeader() throws Exception {
        mvc.perform(get("/api/greeting")
                .with(httpBasic("lan", "demo123")))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void allowedOriginCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .with(httpBasic("lan", "demo123"))
                .param("message", "unsafe"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.get("lan"));
    }

    @Test
    void allowedOriginCanPostWithCsrf() throws Exception {
        mvc.perform(post("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .with(httpBasic("lan", "demo123"))
                .with(csrf())
                .param("message", "hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Saved for lan: hello"));

        assertEquals("hello", store.get("lan"));
    }
}
~~~

Run:

~~~bash
./gradlew test --tests '*OriginCorsTest'
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "*OriginCorsTest"
~~~

**Expected result:** **12 tests** pass with the exact project/dependencies of the example. This is **an expectation derived from the code and Spring Security contract**, not an actual run recorded here. The tests verify server-side CORS policy, preflight, HTTP Basic authentication, and CSRF. `MockMvc` **does not fully simulate a browser**: it does not prove whether SameSite cookies are sent, whether preflight caching works, or whether JS can actually read the response.

When you need to guarantee browser behavior, run two real test origins and inspect the Network tab; do not share real cookies/tokens or passwords.

## 13. Diagnosing from DevTools/Network

In the browser, open Developer Tools → Network, enable Preserve log, and call the API:

~~~javascript
console.log(window.location.origin);

fetch("http://localhost:8080/api/greeting", {
  method: "GET",
  credentials: "include"
});
~~~

If the frontend page runs at `http://localhost:5173`, `window.location.origin` matches that value. The browser calls API origin `http://localhost:8080`, so it is cross-origin. The call may fail due to missing authentication, cookie policy, or CORS config; the snippet only illustrates how to observe.

Debugging workflow:

1. Check **Request URL** to determine the API's origin.
2. Compare against **window.location.origin** to identify the source.
3. Check whether an `OPTIONS` request precedes the actual request.
4. Inspect `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` on preflight.
5. Inspect `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials` in the response.
6. Check the URL behind any reverse proxy and TLS certificates to avoid confusing network errors with CORS.
7. If CORS permits it but you receive 401/403, check authentication, authorization, and CSRF separately.
8. When dealing with credentialed responses, check SameSite/Secure/third-party cookie policies; `credentials: include` does not force the browser to bypass these rules.

**A CORS error in the console does not guarantee the actual request never reached the server.** Some requests are sent while JS is blocked from reading the response; if preflight fails, the actual request may not be sent. Check both Network and selective server logs.

## 14. Reverse proxies and public URLs

Browsers may access:

~~~text
https://api.example.test
        |
        | Reverse proxy HTTPS :443
        v
http://api-service:8080   (internal network)
~~~

The **browser-facing** origin of the API is `https://api.example.test`, not `http://api-service:8080`. The CORS allowlist must be based on the origin of the **frontend calling the API**, not the backend's internal hostname/port. If the frontend is at `https://app.example.test`, the server needs to allow that origin when legitimate cross-origin access is required.

When building redirect URLs or handling scheme/host in the application, trust `Forwarded` or `X-Forwarded-*` headers only when controlled by a trusted reverse proxy. Never let Internet clients spoof forwarded headers to influence security decisions. With multiple `SecurityFilterChain` beans, ensure CORS is applied to the right chain and API routes do not fall through to an unprotected chain.

## 15. Common mistakes

1. **“Same domain means same origin.”** False if scheme/hostname/port differ.
2. **“localhost:5173 and localhost:8080 are same-origin.”** False because ports differ.
3. **“localhost and 127.0.0.1 are same-origin.”** False because hostnames differ.
4. **“HTTP and HTTPS are same-origin if they share a hostname.”** False because schemes differ.
5. **“Explicit port 443 differs from default HTTPS.”** False regarding effective port.
6. **“Path and query are part of the origin.”** False; they affect the URL, not the origin.
7. **“Same-site subdomains allow JS to read responses without CORS.”** False; same-site differs from same-origin.
8. **“The Origin header includes the source page's path.”** False for normal HTTP(S) origin tuples.
9. **“Origin: null is safe because it has no host.”** False; opaque origins can be untrusted.
10. **“CORS allowing an origin means the user is logged in.”** False; authentication/authorization are still required.
11. **“CORS replaces CSRF.”** False; a request with side effects can be sent even if the browser prevents JS from reading the response.
12. **“Allow-Origin: * with Allow-Credentials: true is accepted by browsers.”** False for credentialed requests.
13. **“OPTIONS preflight needs login just like the actual POST.”** Preflight normally carries no credentials; CORS must process it first.
14. **“An Origin header from curl is trustworthy proof of identity.”** False; non-browser clients can set it arbitrarily.
15. **“CORS error, so disable CSRF.”** False because they are two distinct mechanisms.
16. **“The internal server runs on :8080 so the browser sees origin :8080.”** False when sitting behind a public reverse proxy.
17. **“Reflecting every requested Origin in Allow-Origin is safe.”** False; equivalent to allowing untrusted origins.
18. **“CORS blocks all requests from other domains.”** False; CORS mainly controls response sharing in the browser.

## 16. Self-check exercises and answers

**1.** Are `https://example.test` and `https://example.test:443` same-origin?

**Answer:** Yes, because the default effective port for HTTPS is 443.

**2.** Are `http://example.test:443` and `https://example.test:443` same-origin?

**Answer:** No. The HTTP scheme differs from HTTPS.

**3.** Does `http://localhost:5173` calling `http://localhost:8080` require considering CORS?

**Answer:** Yes, for browser scripts calling directly. Different ports make it cross-origin.

**4.** Can `https://app.example.test` and `https://api.example.test` be same-site yet cross-origin?

**Answer:** Yes, they can share the same schemeful site yet be cross-origin due to different hostnames.

**5.** Are `https://app.example.test/cart` and `https://app.example.test/orders?tab=1` same-origin?

**Answer:** Yes. Different path/query does not change the origin.

**6.** A preflight sends `OPTIONS` with `Access-Control-Request-Method: POST`. What is the current request's method?

**Answer:** OPTIONS; POST is the method of the intended subsequent request.

**7.** The server returns `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`; can a credentialed JS fetch read the response?

**Answer:** No under CORS. Credentialed responses cannot use a wildcard Allow-Origin.

**8.** The API allows `https://app.example.test`, while the frontend runs at `https://app.example.test:8443`. Is it allowed by default?

**Answer:** No. A different port produces a different origin.

**9.** Does `Origin: null` mean the source is a trusted website?

**Answer:** No. It can come from an opaque origin; do not whitelist it indiscriminately.

**10.** CORS allows the origin, but the user sends no credentials to an endpoint requiring login. Will the API return the data?

**Answer:** No. CORS grants neither identity nor permissions.

**11.** If frontend and backend are served under the same public URL `https://shop.example.test/api`, while the backend runs internally on port 8080, does the browser need CORS just because of the internal port?

**Answer:** No. The origin the browser sees is based on the public URL, not the internal service port.

## 17. Deployment checklist

- Have full scheme, hostname, and effective port been identified from browser origins?
- Are frontend URLs and API URLs clearly distinguished across dev/prod ports?
- Have default ports HTTP 80 and HTTPS 443 been checked?
- Has confusing same-site cookies with same-origin CORS been avoided?
- Are allowed origins properly formatted without path/query?
- When allowCredentials is enabled, have wildcards `*` been avoided and sources limited to trusted ones?
- Is preflight handled before authentication that depends on sessions/cookies?
- Are allowedMethods and allowedHeaders declared according to real requests?
- Have Origin null and untrusted subdomains been checked?
- Have CORS errors been separated from CSRF, authentication, authorization, and TLS?
- Have different schemes, different hostnames, different ports, different local dev ports, and same-origin requests needing no CORS been tested?
- When using a reverse proxy, have public URLs and trusted forwarded headers been verified?
- Has behavior been tested in a real browser in addition to MockMvc?

**Remember:** For HTTP(S), **an origin consists of scheme + hostname + effective port**. Changing just **one** component can make it cross-origin; changing path/query keeps it same-origin. CORS enables response sharing between origins under browser policy; it **does not** replace authentication, authorization, or CSRF protection.

## References

- [MDN — Origin](https://developer.mozilla.org/en-US/docs/Glossary/Origin): origin tuple, default ports, opaque origins.
- [MDN — Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy): restrictions across origins.
- [MDN — Origin HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin): syntax and meaning of Origin.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight and credentialed requests.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): wildcards and specific origins.
- [Spring Security — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS before authentication and CorsConfigurationSource configuration.
- [Spring Framework — Web MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS configuration, credentialed requests, and preflight.
