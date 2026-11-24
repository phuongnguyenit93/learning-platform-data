# Testing CORS, Security Headers, Firewall, and Non-Standard Paths in Spring Security Servlet

## 1. Lesson Objectives and Scope

A Spring MVC API can pass every "valid login returns 200, invalid login returns 401" test and still have security flaws at the HTTP layer:

- **CORS preflight** requests get blocked by an `AuthenticationFilter` because they carry no bearer token, preventing browsers from sending the actual request.
- Responses for a disallowed origin still leak an inappropriate **`Access-Control-Allow-Origin`**.
- Endpoints return 200 yet omit **`X-Content-Type-Options`**, **`Content-Security-Policy` (CSP)**, or **`HSTS`** over HTTPS.
- URLs containing **semicolons**, **`%2F`** (encoded slash), **`%5C`** (encoded backslash), **`..`**, or non-standard paths are interpreted differently across proxies, servlet containers, firewalls, and MVC.
- **MockMvc** tests pass while production deployments get blocked at the gateway/Tomcat, or the gateway normalizes the path before Spring Security ever sees it.

This lesson shows how to write layered HTTP tests using **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC (Servlet stack)**. Snippets assume the app uses one `SecurityFilterChain` and the default **`StrictHttpFirewall`** configuration.

**Testing goal:** know which requests expect 200, 401, 403, or 400 in the sample configuration, and know **which layer is responsible**. Never use a single HTTP status code as sole proof that CORS, authorization, and the firewall all work properly.

## 2. Four Processing Layers Involved

~~~text
Browser
  │
  ├─ Same-Origin Policy and CORS: browser inspects response
  │
  ▼
Reverse proxy / gateway / WAF
  │  May reject or normalize URI before forwarding
  ▼
Servlet container (e.g., Tomcat)
  │  Parses HTTP request target, maps, decodes/normalizes per config
  ▼
Spring Security FilterChainProxy
  │
  ├─ HttpFirewall (default StrictHttpFirewall)
  │    ├─ Rejected URI → RequestRejectedException
  │    └─ Valid URI → select security filter chain
  │
  └─ Filter chain
       ├─ CORS filter (when cors() configured properly)
       ├─ Authentication + Authorization
       ├─ CSRF (for protected requests)
       └─ Header writers
            ▼
       DispatcherServlet → Controller / Service
            │
            ▼
       Response and security headers
~~~

**CORS** is a browser mechanism deciding whether JavaScript from another origin may read the response. It is **not** API authorization: **`curl`**, server-to-server clients, and programs not bound by browser SOP can still send requests. Separate authentication/authorization is required.

**Security headers** are browser security directives (e.g., nosniff, CSP, frame restrictions, HSTS). They do not replace TLS or access control.

**HttpFirewall** inspects the request shape received by Spring Security, especially ambiguous URIs that could cause mismatches between security matchers and MVC. If the container or proxy rejects early, `HttpFirewall` never runs.

**Non-standard paths** such as **`/api/docs/a%2Fb`**, **`/api/docs;role=admin`**, or **`/api//docs`** must be evaluated across the entire processing chain, not just in controller unit tests.

### 2.1. Why Are Both MockMvc and Real HTTP Needed?

- **MockMvc** runs requests through Spring MVC and the Spring Security filters registered in the test; ideal for fast, controlled verification of filter config, headers, authorization, and controllers.
- **Direct unit tests on `StrictHttpFirewall`** show which simulated URIs the firewall implementation accepts/rejects, independent of Tomcat's raw request parsing.
- **HTTP integration tests running the app on a server** reveal whether the container accepts real requests. If a reverse proxy/WAF exists, add tests through the public URL because outer layers may rewrite paths and cache headers.

A MockMvc test confirming **400 from the default firewall** in the demo config does not mean every reverse proxy returns the exact same 400: a proxy may return 404/400 or normalize the URL before it reaches the app.

## 3. Expectations Matrix Before Writing Code

Suppose the allowed frontend is at **`https://portal.example.test`**, and the backend has a public endpoint **`GET /api/public/ping`** and a protected endpoint **`GET /api/private/data`**.

| Request | Check | Expected in sample config |
| --- | --- | --- |
| `OPTIONS /api/private/data`, allowed Origin, `Access-Control-Request-Method: GET` | Preflight without Basic credentials | **200**, `Access-Control-Allow-Origin` matches origin |
| Preflight with disallowed Origin | CORS policy | **403**, no `Access-Control-Allow-Origin` issued |
| Preflight requesting disallowed method PUT | Allowed methods | **403** |
| Preflight requesting disallowed header `X-Admin-Override` | Allowed headers | **403** |
| Public GET, allowed Origin | Actual CORS request | **200**, ACAO header matches origin |
| Public GET, disallowed Origin | Actual CORS request | **403**, no ACAO issued |
| Private GET without Basic credentials, allowed Origin | CORS **and** authentication | **401**, typically still includes ACAO from `CorsFilter` |
| Private GET with valid Basic, allowed Origin | CORS **and** authentication | **200**, response includes ACAO |
| Public GET without Origin | Not a cross-origin browser request | **200**, typically no ACAO |
| Public GET over non-TLS HTTP | Security headers | Includes nosniff, frame policy, configured CSP; **do not** expect HSTS |
| Public GET over HTTPS | Security headers | Includes above headers plus **`Strict-Transport-Security`** |
| URI with semicolon, encoded slash/backslash, or unusual path | `StrictHttpFirewall` | Rejected if the request reaches the firewall in that form |
| Private GET without credentials / without Origin | `AuthenticationEntryPoint` | **401** in HTTP Basic demo |

These codes are the **contract of the example config and Spring Security 6.x**, not a claim that every proxy, container, IdP, or custom filter returns identical values.

## 4. CORS: Preflight, Actual Requests, and Misconceptions

### 4.1. Preflight Differs from Actual Requests

Before JavaScript sends a non-"simple" cross-origin request (for example carrying an `Authorization` header), the browser may send a preflight:

~~~http
OPTIONS /api/private/data HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflights **do not need** to carry the actual request's Basic/Bearer credentials. The CORS filter must decide policy **before** the authorization filter blocks it. If the preflight response succeeds, only then does the browser consider sending the real GET request, at which point **Authentication** and **Authorization** still apply normally.

An allowed preflight response may look like:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Methods: GET,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Header order, casing, and multi-value formatting in real responses can vary by framework and proxy. Tests should assert **important values**, rather than requiring byte-for-byte raw response equality.

**`Access-Control-Allow-Credentials: true`** only carries meaning under CORS semantics; it does not prove the user is authenticated. When allowing credentials, specify trusted explicit origins—**never** configure `Access-Control-Allow-Origin: *` on credentialed responses.

### 4.2. Do Not Use permitAll() to "Fix CORS"

If preflight fails because the CORS filter is misplaced, adding **`requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()`** does not fix origin/header/method checks. It may let `OPTIONS` travel further without emitting the right CORS headers, and may expose unintended method handling.

Configure **`CorsConfigurationSource`** for the right paths, then enable **`http.cors(...)`** on the applicable security chain. With multiple `SecurityFilterChain` beans, check which chain receives the request and whether that chain handles CORS properly.

### 4.3. Origin Is Not Referer, Host, or the Backend URL

An **Origin** consists of scheme, hostname, and port per web origin rules. For example:

- **`https://portal.example.test`** differs from **`http://portal.example.test`**.
- **`https://portal.example.test`** differs from **`https://portal.example.test:8443`**.
- **`https://another.example.test`** is a different origin.
- The **`Referer`** header is no substitute for CORS configuration.
- Browsers prevent JavaScript from forging `Origin` in standard `fetch` calls, yet non-browser HTTP clients can spoof any `Origin`. Therefore never treat `Origin` as identity proof.

**CORS is not CSRF protection.** If an API uses auto-sent cookies/sessions and has state-changing POST/PUT/DELETE endpoints, you still need a proper CSRF strategy. A response blocked in the browser by CORS does not guarantee the request was never sent or side effects never happened.

## 5. Which Security Headers Should Be Tested?

In typical Spring Security Servlet setups:

| Header | Purpose | Default / notes |
| --- | --- | --- |
| **`X-Content-Type-Options: nosniff`** | Reduces browser MIME sniffing | Typically emitted by Spring Security by default |
| **`X-Frame-Options: DENY`** | Restricts embedding response in frames | Typically default; verify actual framing policy |
| **`Cache-Control / Pragma / Expires`** | Limits caching of sensitive responses | Spring Security sets default cache-control headers, though they can be overridden |
| **`Strict-Transport-Security` (HSTS)** | Instructs browsers to prefer HTTPS going forward | Usually written for **secure requests**; do not expect it on plain internal HTTP |
| **`Content-Security-Policy`** | Restricts script/resource sources and framing when configured | **Not** emitted automatically just by enabling Spring Security; must be declared |
| **`Referrer-Policy`** | Limits URL leakage in `Referer` | Define policy/emitter explicitly rather than assuming defaults |
| **`Permissions-Policy`** | Restricts browser features | May be set at app or proxy; test where it is actually emitted |

For SPAs or HTML pages, **CSP must be tailored to actual script/style/nonce/hash sources**. The example below uses a compact policy to demonstrate header assertions; if an app loads external scripts/styles, adjust CSP thoughtfully rather than switching to **`unsafe-inline`** just to silence browser errors.

**HSTS** must be verified over a real HTTPS connection, especially when TLS terminates at a reverse proxy: Spring may only see internal HTTP unless the proxy sends trusted **`Forwarded`/`X-Forwarded-Proto`** headers and the app processes them. HSTS may also be emitted by ingress. If both app and proxy set headers, check the final response at the public edge, not only local MockMvc.

**`Cache-Control`** on responses with sensitive data should be designed per content type, including reverse-proxy/CDN layers. Do not treat a Spring-emitted header alone as sufficient to control every external cache layer.

## 6. HttpFirewall and Unusual Paths

### 6.1. Why Can Ambiguous URLs Be Dangerous?

One layer might evaluate permissions on **`/api/items/a%2Fb`** while the next layer decodes it to **`/api/items/a/b`**. Or a **`;v=1`** matrix suffix gets stripped during matcher comparison yet treated as a path parameter by MVC/controller. When resource identification and permission checks rely on **two different interpretations**, routes risk bypassing policy.

**`StrictHttpFirewall`**, used by default in common Spring Security Servlet setups, rejects many dangerous or non-standard URI patterns per its implementation policy. Examples:

| Path / request target | Risk | Appropriate test |
| --- | --- | --- |
| **`/api/items;v=1`** | Semicolon / path parameter / matrix variable | Direct `StrictHttpFirewall` unit test and HTTP request |
| **`/api/items/a%2Fb`** | Encoded slash can introduce a new segment after decoding | Firewall unit test + HTTP container |
| **`/api/items/a%5Cb`** | Encoded backslash may be interpreted as a separator | Firewall unit test + HTTP container |
| **`/api/items/a%25b`** | Encoded percent may enable double decoding | Firewall unit test + raw request |
| **`/api//items`** | Multiple slashes; proxy/router may normalize | Firewall unit test + request with `--path-as-is` |
| **`/api/../admin`** | Dot-segment / traversal normalization | Firewall unit test + request where client does not pre-normalize |
| **`/api/items/%00`** | Encoded NUL / control characters | Container/firewall layer test, never reflect sensitive payloads |

Never assume every request reaches **`StrictHttpFirewall`** unmodified. Tomcat, reverse proxies, gateways, WAFs, or HTTP clients may process it **first**.

### 6.2. Firewall Runs Before Authorization Matchers

Inside **`FilterChainProxy`**, `HttpFirewall` inspects the request before selecting filters in `SecurityFilterChain`. A request rejected for a non-standard URI cannot be "opened" via **`permitAll()`**, **`hasRole()`**, or **`@PreAuthorize`**.

When receiving a disallowed request, Spring Security may throw **`RequestRejectedException`**; the default handler in many Spring Security 6 setups translates it to HTTP 400. If a container/proxy blocks earlier, the HTTP status may differ. Unit testing the exception is the clearest signal for the firewall's own rules; integration tests determine the end-to-end outcome.

### 6.3. Should You Enable setAllowSemicolon(true) or Encoded Slashes?

Only when a thoroughly analyzed business requirement demands it. Some apps using matrix variables may need **`setAllowSemicolon(true)`**; relaxing any rule must come with tests proving authorization matchers and controllers interpret the exact same resource. **`setAllowUrlEncodedSlash(true)`** does not guarantee proxies/containers let `%2F` pass through and can introduce ambiguous paths.

Never switch an entire app to a looser firewall just to make one URL or one test return 200. It is usually better to move resource keys containing slashes into query parameters, UUIDs, or opaque URL-safe IDs.

## 7. Sample Application: Spring Boot 3.x / Spring Security 6.x

The example creates an app with:
- **`GET /api/public/ping`**: public and used to inspect headers.
- **`GET /api/private/data`**: requires HTTP Basic authentication.
- CORS allowing only frontend **`https://portal.example.test`** on **`/api/**`**, GET/OPTIONS, and `Authorization`/`Content-Type` headers.
- Default security headers plus explicit CSP.
- Default **`StrictHttpFirewall`** (unrelaxed).

### 7.1. Dependencies

In a Spring Boot 3.x Gradle project with wrapper already set up, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 7.2. Application, Security Filter Chain, CORS, and Controller

Create **`src/main/java/com/example/httpsecurity/HttpSecurityTestingApplication.java`**:

~~~java
package com.example.httpsecurity;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class HttpSecurityTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpSecurityTestingApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/api/private/data").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp.policyDirectives(
                                "default-src 'self'; object-src 'none'; "
                              + "frame-ancestors 'none'")))
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
                List.of("https://portal.example.test"));
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Demo/test-only credentials for local testing.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-password"))
                        .roles("USER")
                        .build());
    }
}

@RestController
class ApiController {
    @GetMapping("/api/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/private/data")
    String privateData(Authentication authentication) {
        return "private-for-" + authentication.getName();
    }
}
~~~

**Design explanation:**

1. **`cors(Customizer.withDefaults())`** enables CORS in Spring Security; the `CorsConfigurationSource` bean supplies the policy.
2. **`Access-Control-Allow-Origin`** does not use **`*`** because **`allowCredentials(true)`** can only be safely applied with explicit origins or tightly bounded patterns.
3. `OPTIONS` preflight is decided by the CORS filter before authentication. Yet an actual GET to the private endpoint still passes through HTTP Basic; a valid origin alone never grants access.
4. The example has no state-changing POST/PUT/DELETE, so **CSRF is not disabled**. In real APIs with cookies/sessions, maintain proper CSRF protection.
5. **`X-Content-Type-Options`**, **`X-Frame-Options`**, HSTS, and cache headers follow common defaults; CSP here is **explicitly added** via **`contentSecurityPolicy`**.
6. The example keeps the **default `StrictHttpFirewall`**. If an app adds a custom `HttpFirewall`, unit test results on a newly instantiated default firewall only verify that instance's policy, not that the app uses it.

With multiple **`SecurityFilterChain`** beans, test each actual chain. Configuring CORS for one chain does not mean requests hitting another chain receive the same policy.

## 8. MockMvc and StrictHttpFirewall Test Suite

Create **`src/test/java/com/example/httpsecurity/HttpSecurityTestingTest.java`**:

~~~java
package com.example.httpsecurity;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityTestingTest {

    private static final String FRONTEND =
            "https://portal.example.test";

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightDoesNotRequireAuthentication()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "GET")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "Authorization"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                        containsString("GET")));
    }

    @Test
    void preflightWithUnknownOriginIsForbidden()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN,
                            "https://untrusted.example.test")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "GET"))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void preflightWithUnsupportedMethodIsForbidden()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "PUT"))
                .andExpect(status().isForbidden());
    }

    @Test
    void preflightWithUnsupportedHeaderIsForbidden()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "GET")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "X-Admin-Override"))
                .andExpect(status().isForbidden());
    }

    @Test
    void actualGetFromAllowedOriginReceivesCorsHeaders()
            throws Exception {
        mvc.perform(get("/api/public/ping")
                    .header(HttpHeaders.ORIGIN, FRONTEND))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND));
    }

    @Test
    void actualGetFromUnknownOriginIsRejected()
            throws Exception {
        mvc.perform(get("/api/public/ping")
                    .header(HttpHeaders.ORIGIN,
                            "https://untrusted.example.test"))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void ordinaryGetWithoutOriginNeedsNoCorsHeader()
            throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void corsDoesNotReplaceAuthentication()
            throws Exception {
        mvc.perform(get("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND));
    }

    @Test
    void authenticatedRequestStillHasCorsPolicy()
            throws Exception {
        mvc.perform(get("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("private-for-alice"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND));
    }

    @Test
    void ordinaryHttpResponseHasBasicSecurityHeaders()
            throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                        "X-Frame-Options", "DENY"))
                .andExpect(header().string(
                        "Content-Security-Policy",
                        "default-src 'self'; object-src 'none'; "
                      + "frame-ancestors 'none'"))
                .andExpect(header().exists("Cache-Control"))
                .andExpect(header().doesNotExist(
                        "Strict-Transport-Security"));
    }

    @Test
    void hstsIsPresentOnSecureRequest() throws Exception {
        mvc.perform(get("/api/public/ping").secure(true))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Strict-Transport-Security",
                        containsString("max-age=")));
    }

    @Test
    void firewallRejectsSemicolonOverMockMvc()
            throws Exception {
        // MockMvc uses the demo's default FilterChainProxy and handler.
        mvc.perform(get("/api/public/ping;v=1"))
                .andExpect(status().isBadRequest());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/items;v=1",
            "/api/items/a%2Fb",
            "/api/items/a%5Cb",
            "/api/items/a%25b",
            "/api//items",
            "/api/../items",
            "/api/items/%00"
    })
    void strictFirewallRejectsAmbiguousUri(String uri) {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", uri);

        assertThatThrownBy(
                () -> firewall.getFirewalledRequest(request))
                .isInstanceOf(RequestRejectedException.class);
    }

    @Test
    void semicolonExceptionDoesNotAllowEncodedSlash() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        firewall.setAllowSemicolon(true);

        assertThatCode(() -> firewall.getFirewalledRequest(
                new MockHttpServletRequest(
                        "GET", "/api/items;v=1")))
                .doesNotThrowAnyException();

        assertThatThrownBy(() -> firewall.getFirewalledRequest(
                new MockHttpServletRequest(
                        "GET", "/api/items/a%2Fb")))
                .isInstanceOf(RequestRejectedException.class);
    }
}
~~~

**This suite tests multiple layers without conflating them:**

- **MockMvc CORS tests** send requests through the real filter chain initialized in the Spring Test context. They do not prove production proxy/WAF policies.
- **Security header tests** verify both default headers and app-configured CSP. The HSTS test uses **`secure(true)`** because a plain MockMvc HTTP request is not a secure request.
- **MockMvc firewall test** relies on the demo Spring Security 6 config's default `FilterChainProxy`/`RequestRejectedHandler`; if a system customizes the handler, the HTTP status may differ.
- **`StrictHttpFirewall` unit tests** verify URI-blocking rules on the default implementation. They do not test how Tomcat, a gateway, or MVC routes handle the same URI.
- The **`setAllowSemicolon(true)`** test mutates only a temporary firewall instance inside the unit test; it **does not** enable that exception in the demo app or tell production to relax the firewall.
- No test boots a frontend or truly checks browser SOP; an API response with right headers is only **a precondition for browsers to permit cross-origin access**, not proof the frontend works.

### 8.1. Running the Tests

In the project root directory containing the Gradle wrapper:

~~~bash
./gradlew test --tests com.example.httpsecurity.HttpSecurityTestingTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.httpsecurity.HttpSecurityTestingTest
~~~

**Expected outcome for the sample config:** all tests pass, including 200 on valid preflight, 403 on disallowed origin/method/header, 401 on unauthenticated private endpoint, 200 with valid HTTP Basic, HSTS on secure request, 400 for semicolon path blocked by `HttpFirewall`, and `RequestRejectedException` unit tests.

That is an **expected result from the example design**, not a confirmed execution log. Run it inside a Spring Boot/Spring Security project configured with compatible versions to confirm compilation and behavior. If using a different Spring Security version, check changes to default `RequestRejectedHandler`, HSTS policy, and how MockMvc handles test paths.

### 8.2. If MockMvc Tests Do Not Behave as Expected

Check:

1. Whether **`spring-boot-starter-security`**, **`spring-security-test`**, and the app's **`SecurityFilterChain`** are truly initialized in the test context.
2. Whether **`@AutoConfigureMockMvc`** and filter registration are enabled. A MockMvc built with **`standaloneSetup(...)`** does not automatically include Spring Security filters.
3. Whether the right **`CorsConfigurationSource`** bean maps **`/api/**`** and **`http.cors(...)`** is enabled.
4. Whether the HSTS test sets **`secure(true)`**; otherwise Spring Security typically omits HSTS.
5. Whether CSP is explicitly declared; do not test for a default CSP when the app never configured one.
6. Whether another test uses **`@MockBean`** replacing a service or filter and removing the execution path under test.
7. Whether a custom **`HttpFirewall`**, **`RequestRejectedHandler`**, `SecurityFilterChain` order, or another test profile is active.

## 9. Trying Real HTTP Requests with curl

Start the sample application:

~~~bash
./gradlew bootRun
~~~

### 9.1. Valid and Invalid Preflight

From a terminal, simulate preflight:

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/private/data' \
  -H 'Origin: https://portal.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

In this sample, the expected response is **200** with **`Access-Control-Allow-Origin: https://portal.example.test`** and matching `Allow-Methods`/`Allow-Headers`. Basic credentials are not needed in the preflight.

Try another origin:

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/private/data' \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: GET'
~~~

Expected **403** from CORS processing. A short body **`Invalid CORS request`** may appear depending on framework/version. Never rely on that body or error string as sole evidence in real systems.

### 9.2. Actual Requests and Authentication

~~~bash
curl -i 'http://localhost:8080/api/private/data' \
  -H 'Origin: https://portal.example.test'

curl -i -u alice:demo-password \
  'http://localhost:8080/api/private/data' \
  -H 'Origin: https://portal.example.test'
~~~

The first request expects **401** for lacking credentials; the second expects **200** with body **`private-for-alice`**. Both still obey CORS policy; the presence of `Access-Control-Allow-Origin` on a 401 does not mean the user was granted access.

**`curl` does not enforce browser same-origin policy**, so `curl` commands alone cannot prove JavaScript on a disallowed origin cannot read responses. For web products, inspect real browser DevTools and run E2E tests as well.

### 9.3. Unusual Paths and Rejection Layers

~~~bash
curl --path-as-is -i \
  'http://localhost:8080/api/public/ping;v=1'

curl --path-as-is -i \
  'http://localhost:8080/api/items/a%2Fb'

curl --path-as-is -i \
  'http://localhost:8080/api//items'

curl --path-as-is -i \
  'http://localhost:8080/api/../items'
~~~

**`--path-as-is`** reduces `curl`'s client-side normalization of some path forms before sending, especially dot segments; it does not guarantee every byte reaches Spring untouched through proxies/Tomcat.

Interpreting results:

- **400 and `RequestRejectedException` log**: signal that the request reached Spring Security's `HttpFirewall` and was rejected.
- **400 in Tomcat/nginx logs without a Spring Security log**: an outer layer blocked early—that is not a Jwt/Auth/Controller bug.
- **404**: could mean MVC found no route, the gateway did not map the path, or the URL was normalized; does not prove the firewall rejected it.
- **403**: could come from CORS, authorization, or another security handler; inspect the request and related logs.
- **200** on an ambiguous path: check which layer transformed the URL, whether a route was bypassed, or whether the firewall was relaxed; never blindly treat it as desired behavior.

**Never enable encoded slashes or semicolons wholesale just to make HTTP tests pass.** Observe differences across layers, then design consistent URLs, routing, and matchers.

## 10. Testing Through Reverse Proxies, Gateways, and HTTPS

Production architectures often look like:

~~~text
Browser HTTPS
   ▼
Edge proxy / WAF (host, TLS, path rewrite)
   ▼
Internal HTTP Tomcat
   ▼
Spring Security Servlet
~~~

A test suite running directly against `localhost:8080` cannot verify public-edge behavior. When testing staging through a reverse proxy, verify:

1. Public URLs use proper **`https`**, hostname, and path prefix. If the proxy strips prefixes, external and internal paths must map consistently.
2. Only trusted proxies may set **`Forwarded` / `X-Forwarded-Proto` / `X-Forwarded-Host` / `X-Forwarded-Prefix`**. Clients must not be able to inject forwarded headers to spoof scheme/host/path.
3. **HSTS** is present on final HTTPS responses at the public edge even when TLS terminates at the proxy. If the app sees only internal HTTP, trusted forwarded-header handling or edge-emitted HSTS may be needed.
4. **CSP, nosniff, and frame policies** appear on user-facing responses without being stripped or overwritten by the proxy.
5. CORS preflights are not mis-redirected, blocked by gateway authentication, or given wildcard policies. Test both **`OPTIONS`** and actual methods.
6. Per-API/per-chain CORS policies are verified on each route and origin, not just on **`/api/public/ping`**.
7. Proxy/caching layers handle **`Vary: Origin`** properly if caching responses by Origin; avoid serving Origin A's ACAO header to Origin B.
8. Request targets with percent-encoding, dot segments, or semicolons are tested at **both edge and container**, not only MockMvc. Record which layer rejects them.
9. When multiple path rewrites or context paths exist, ensure authorization matchers apply to the path the app actually executes, not only the pre-rewrite public path.
10. If error responses are generated entirely at the gateway, Spring Security header writers never run; configure security headers wherever those **error responses** are produced.

Never place raw `Authorization`/Cookie/tokens or user data in public request logs while diagnosing these tests.

## 11. Common Testing Mistakes

| Mistake | Why it is wrong | How to test properly |
| --- | --- | --- |
| Testing `OPTIONS` returns 200 and concluding CORS works | May lack ACAO/Allowed-Headers or reflect arbitrary origins | Check both status and **`Access-Control-Allow-Origin/Methods/Headers`** |
| Skipping negative unknown-origin tests | Overly permissive config still passes happy paths | Test invalid origins, methods, and headers |
| Treating a valid `Origin` as authentication | CORS is only a browser cross-origin policy | Test 401/403 separately for private endpoints |
| Using `curl` to prove "browsers will block reading" | `curl` does not enforce SOP | Pair integration tests with browser E2E/DevTools |
| Disabling CSRF because CORS is enabled | CORS does not protect against all state-changing requests | Test CSRF per cookie/session and unsafe methods |
| Asserting only status 200 without headers | Missing CSP, HSTS, or nosniff goes undetected | Assert each header and secure request conditions |
| Requiring HSTS on plain MockMvc HTTP requests | Default header applies to HTTPS/secure requests | Use **`.secure(true)`** and test HTTPS public edge |
| Assuming Spring Security emits CSP automatically | CSP is not a universal default | Configure **`contentSecurityPolicy(...)`** and test it |
| Testing only standalone controllers | Skips `FilterChainProxy`, `CorsFilter`, and `HttpFirewall` | Use **`@SpringBootTest + @AutoConfigureMockMvc`** or MockMvc with `springSecurity()` |
| Treating every 400 as the firewall | Container/proxy may reject earlier | Correlate logs, firewall unit tests, and container requests |
| Testing only normal paths | Misses encoded slashes, semicolons, dot segments, double encoding | Add an unusual-URI matrix |
| Testing percent-encoded URLs where the client auto-normalizes | Test stops sending the URI you intended | Use **`--path-as-is`**, inspect raw paths and network boundaries |
| Relaxing `HttpFirewall` just to turn tests green | Reopens ambiguous-path risks | Keep defaults; relax only for evaluated business requirements |
| Disabling all security headers to "reduce conflicts" | Drops multiple browser defenses | Tune individual policies and test actual responses |
| Testing only 200 and forgetting error responses | 401/403/404 may flow through a different handler/gateway | Test error responses at every response emitter |

## 12. Checklist for an HTTP Security Test Suite

- **Right test layers:** include MockMvc with security filters, `StrictHttpFirewall` unit tests, and HTTP E2E through container/edge.
- **CORS:** test allowed origin, unknown origin, allowed preflight, disallowed method/header, actual requests with/without credentials; verify exact ACAO values.
- **CORS vs auth:** prove preflight needs no credentials while actual private requests still require authentication and authority.
- **Security headers:** verify nosniff, frame policy, configured CSP, cache policy, and HSTS only under HTTPS/secure contexts; test final responses through proxies.
- **Firewall:** test semicolons, encoded slashes/backslashes/percent signs, duplicate slashes, dot segments, and encoded NULs; identify the rejecting layer.
- **Routing:** with multiple `SecurityFilterChain` beans or path prefixes, test each chain and confirm matchers target post-rewrite endpoints.
- **HTTP statuses:** distinguish 400 parser/firewall, 401 authentication, and 403 CORS/authorization; never infer one status from a single cause.
- **CSRF:** with cookies/sessions and unsafe methods, keep dedicated CSRF tests. Never treat CORS as a substitute.
- **Proxy trust:** forwarded headers accepted only from trusted proxies; test HTTPS/HSTS, `Vary`, and security headers at the public edge.
- **Test safety:** never use production credentials, log tokens/cookies, or send unusual payloads to unauthorized third-party systems.
- **Maintenance:** after upgrading Spring Security, Tomcat, or proxy configs, rerun both positive and negative cases; avoid assertions coupled to unnecessary header order.

**Conclusion:** A solid HTTP security test suite asks more than whether an endpoint returns 200. It must prove **browsers receive CORS only for allowed origins**, **real requests remain authenticated and authorized**, **responses emit proper security headers**, and **non-standard URLs are handled consistently across the firewall, container, and reverse proxy**. Combining MockMvc, `StrictHttpFirewall` unit tests, and end-to-end public-edge testing prevents both false positives and path-interpretation bypasses.
