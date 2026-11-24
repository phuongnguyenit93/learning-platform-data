# CORS for Multiple SecurityFilterChains and Different Endpoint Groups

## 1. The Problem and Desired Outcome

A Spring Boot 3.x / Spring Security 6.x application on the **Servlet stack** may simultaneously serve a public API for one website, an internal API for another website, and a traditional MVC UI running on the same origin:

- **/api/catalog/**: read by **https://catalog.example**, carrying no credentials.
- **/api/operations/**: used by **https://console.example**, with authentication and **OPERATOR** permission; CORS allows GET/POST from this origin without automatically bypassing CSRF.
- **/web/**: traditional MVC pages running on the same origin, not intended to be opened cross-origin.

Each group needs a different policy. If CORS is opened too broadly, an origin that should only read the catalog could receive responses containing data from the internal API when a user has credentials. If CORS configuration is not invoked on the chain handling OPTIONS, the browser may report preflight errors even though the controller works normally via curl.

**CORS (Cross-Origin Resource Sharing)** is a rule allowing the browser to decide whether JavaScript from one origin may read responses from another origin. An origin consists of **scheme + hostname + port**: **https://console.example**, **http://console.example**, and **https://console.example:8443** are three different origins. CORS does not grant authentication/authorization; server-to-server clients, curl, or Postman do not enforce browser CORS restrictions. CORS is also not a substitute for CSRF.

This lesson focuses on how to arrange **SecurityFilterChain**, **securityMatcher**, **CorsConfigurationSource**, chain ordering, and verifying both preflight and actual requests.

## 2. Two Routing Layers: Filter Chain and CORS Source

Spring Security uses **FilterChainProxy** to find the **first matching SecurityFilterChain** in order. Each request passes through only the one selected security chain. **securityMatcher(...)** decides which chain a request belongs to; **requestMatchers(...)** inside **authorizeHttpRequests** only sets authorization rules after the chain has been selected.

~~~text
Browser
  │
  ├── Preflight (if needed): OPTIONS /api/operations/tasks
  │   Origin: https://console.example
  │   Access-Control-Request-Method: POST
  │   Access-Control-Request-Headers: authorization,x-csrf-token
  │
  ▼
FilterChainProxy: selects the FIRST MATCHING SecurityFilterChain
  │
  ├── /api/operations/**  → operationsChain (@Order 1)
  │                           → CORS policy for console.example
  ├── /api/catalog/**     → catalogChain    (@Order 2)
  │                           → CORS policy for catalog.example
  └── remaining paths     → webChain        (@Order 3)
                              → CORS not opened
  │
  ▼
CorsFilter in the selected chain
  ├── Valid preflight: returns CORS response, ends OPTIONS processing
  ├── Rejected origin/method/header: usually HTTP 403
  └── Valid actual request: adds CORS headers, continues
  │
  ▼
CSRF → Authentication → Authorization → Controller
~~~

This diagram simplifies the filters while keeping the right logical order: **CORS must be processed before security checks requiring credentials**. Preflight does not have the full cookies/credentials of the actual request, so if the system forces OPTIONS to log in, the browser may encounter 401/403/302. **http.cors(...)** lets Spring Security place the CORS filter in the right position.

### Preflight vs. Actual Request

| Type | Key request/response | Meaning |
| --- | --- | --- |
| Preflight | OPTIONS + **Origin**, **Access-Control-Request-Method**, sometimes **Access-Control-Request-Headers** | Asks the server whether the cross-origin actual request is allowed; normally needs no login |
| Actual request | GET/POST with Origin and real payload | May have **Access-Control-Allow-Origin** added, yet still must pass authentication, authorization, and CSRF |
| Browser | Checks CORS response headers | Lets JavaScript read the response only when policy is satisfied; does not replace server-side permissions |

Not every cross-origin request triggers OPTIONS. For example, a simple GET typically sends the actual request directly. Requests using an **Authorization** header, **Content-Type: application/json**, or methods like PUT/DELETE usually require preflight per browser rules.

A preflight receiving 200 only proves **the CORS policy permits sending the request**. The actual POST can still get 401 for missing login, 403 for missing role, or 403 for missing CSRF token.

## 3. Clearly Designing Endpoint Groups and Precedence Order

| Security chain | Path | Allowed origins | Methods | Credentials | Permissions / CSRF |
| --- | --- | --- | --- | --- | --- |
| operationsChain | **/api/operations/** | **https://console.example** | GET, POST | **true** | role OPERATOR; CSRF enabled |
| catalogChain | **/api/catalog/** | **https://catalog.example** | GET | **false** | public read |
| webChain | fallback | Cross-origin not configured | — | per web session | form login; CSRF enabled |

Use **@Order(1)** and **@Order(2)** for the two narrow matchers; the fallback **@Order(3)** does not call securityMatcher, so it matches all remaining paths. Placing the fallback first would prevent later chains from ever handling requests.

Not only must actual methods hit the chain: **OPTIONS preflight must also hit the same chain**. For instance, if a custom securityMatcher only accepts GET/POST, OPTIONS will fall through to the fallback and may require login. A path-based matcher covering both OPTIONS and actual requests is usually more appropriate.

If multiple endpoints share one authentication and authorization model, multiple chains are not mandatory. You can use one CorsConfigurationSource with multiple **registerCorsConfiguration(pathPattern, policy)** calls. Only split chains when there is a security boundary needing separate handling; each chain still needs a consistent CORS policy.

## 4. Complete Spring Boot 3.x / Java 17+ Example

In a Spring Boot project with Gradle wrapper, the dependencies needed are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

File **src/main/java/com/example/corsgroups/CorsGroupsApplication.java**:

~~~java
package com.example.corsgroups;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsGroupsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsGroupsApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    @Order(1)
    SecurityFilterChain operationsChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/operations/**")
                .cors(cors -> cors.configurationSource(
                        sourceFor("/api/operations/**",
                                List.of("https://console.example"),
                                List.of("GET", "POST"),
                                List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"),
                                true)))
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("OPERATOR"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain catalogChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/catalog/**")
                .cors(cors -> cors.configurationSource(
                        sourceFor("/api/catalog/**",
                                List.of("https://catalog.example"),
                                List.of("GET"),
                                List.of("Content-Type"),
                                false)))
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().permitAll())
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    private CorsConfigurationSource sourceFor(
            String path,
            List<String> origins,
            List<String> methods,
            List<String> headers,
            boolean credentials) {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(origins);
        policy.setAllowedMethods(methods);
        policy.setAllowedHeaders(headers);
        policy.setAllowCredentials(credentials);
        policy.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration(path, policy);
        return source;
    }

    // For local demo only; replace with a real identity system.
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo-operator")
                        .password(encoder.encode("local-only-password"))
                        .roles("OPERATOR")
                        .build());
    }
}

@RestController
class ApiController {
    @GetMapping("/api/catalog/items")
    List<String> items() {
        return List.of("book", "pen");
    }

    @GetMapping("/api/operations/status")
    String status() {
        return "ready";
    }

    @PostMapping("/api/operations/tasks")
    String createTask() {
        return "created";
    }

    @GetMapping("/web/home")
    String home() {
        return "home";
    }
}
~~~

### Configuration Analysis

**(1) Each chain specifies its own source via cors.configurationSource(...).** The **sourceFor** method creates a **CorsConfiguration** and registers it for the exact path with **UrlBasedCorsConfigurationSource**. The two policies never mix origins, methods, headers, or credentials flags. There are two layers of scoping: **securityMatcher** selects the chain, and **registerCorsConfiguration** selects the policy by path. When changing paths, update both.

**(2) Operations accepts GET/POST from one concrete origin.** **setAllowCredentials(true)** informs the browser it may permit credentialed requests when other conditions are met. When using cross-origin fetch, configure **credentials** appropriately on the client. Cross-site cookies also depend on **SameSite**, **Secure**, domain, and browser policies. Basic auth in the demo aids learning, yet the fact that browsers cache/auto-send Basic credentials is a reason CSRF must be considered.

**(3) CORS does not replace authorization.** The operations chain still requires **ROLE_OPERATOR** on actual requests. The demo keeps CSRF enabled: a POST by a logged-in user without a valid CSRF token still gets 403. For a cross-origin frontend to perform POSTs using session/cookie/Basic, you must design how CSRF tokens are obtained/sent appropriately for the real system. Never disable CSRF simply because you just allowed a CORS origin.

**(4) Catalog only has public GET.** The CORS policy does not permit cross-origin POSTs from browsers, yet the server must still restrict methods at the route and/or authorization layer. Never treat CORS as a firewall blocking curl/Postman or other backends from sending requests.

**(5) Fallback does not open CORS.** Same-origin web pages continue working with form login and default CSRF. A request with Origin from console.example to **/web/home** does not inherit the operations CORS policy.

**(6) Do not use wildcard origin when allowing credentials.** **setAllowedOrigins(List.of("*"))** is incompatible with **setAllowCredentials(true)** and will be rejected by Spring during configuration validation. Use an explicit list of origins or controlled allowedOriginPatterns; avoid arbitrarily reflecting Origin in responses.

**(7) Do not configure multiple uncoordinated CORS sources simultaneously.** An application might have **WebMvcConfigurer.addCorsMappings**, **@CrossOrigin**, a custom **CorsFilter**, or a reverse proxy adding headers. Unify where CORS is handled. When multiple **CorsConfigurationSource** beans or multiple chains exist, **cors.configurationSource(...)** avoids relying on framework auto-selection. If multiple layers both add **Access-Control-Allow-Origin**, the browser may reject due to duplicate headers.

## 5. Testing with MockMvc

The tests below verify the boundary between the two chains, login-less OPTIONS preflight, role-protected actual requests, and POST still requiring CSRF.

File **src/test/java/com/example/corsgroups/CorsGroupsTest.java**:

~~~java
package com.example.corsgroups;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CorsGroupsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void catalogAcceptsItsOrigin() throws Exception {
        mvc.perform(get("/api/catalog/items")
                        .header(HttpHeaders.ORIGIN, "https://catalog.example"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://catalog.example"))
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS));
    }

    @Test
    void catalogRejectsConsoleOrigin() throws Exception {
        mvc.perform(get("/api/catalog/items")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isForbidden());
    }

    @Test
    void operationsPreflightRequiresNoLogin() throws Exception {
        mvc.perform(options("/api/operations/tasks")
                        .header(HttpHeaders.ORIGIN, "https://console.example")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                "authorization,x-csrf-token"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://console.example"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true"));
    }

    @Test
    void operationsPreflightRejectsCatalogOrigin() throws Exception {
        mvc.perform(options("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://catalog.example")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void operationsActualGetRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void operationsRejectsInsufficientRole() throws Exception {
        mvc.perform(get("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void operationsAllowsAuthorizedRead() throws Exception {
        mvc.perform(get("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void allowedOriginDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/operations/tasks")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void csrfTokenAllowsPost() throws Exception {
        mvc.perform(post("/api/operations/tasks")
                        .header(HttpHeaders.ORIGIN, "https://console.example")
                        .with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void webFallbackDoesNotAddCorsOrigin() throws Exception {
        mvc.perform(get("/web/home")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

Run from the project root with the Gradle wrapper:

~~~bash
./gradlew test --tests com.example.corsgroups.CorsGroupsTest
~~~

On Windows, use **gradlew.bat** instead of **./gradlew**. With the sample configuration, the 10 tests expect **200, 403, 200, 403, 401, 403, 200, 403, 200, 200** respectively. **@WithMockUser** simulates an authenticated principal; **with(csrf())** supplies a valid CSRF token in tests, not a production token-issuance method. In real integration, also verify proxies, cookies, redirects, servlet path config, and authentication policies beyond the demo.

### Testing Preflight Requests Independently

Start the application:

~~~bash
./gradlew bootRun
~~~

Send OPTIONS like a browser:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/operations/tasks' \
  -H 'Origin: https://console.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,x-csrf-token'
~~~

Expected: **HTTP 200** with headers **Access-Control-Allow-Origin: https://console.example** and **Access-Control-Allow-Credentials: true**; no Basic authentication needed in preflight. This **does not guarantee the actual POST succeeds**: POST still requires authentication credentials, the proper role, and a CSRF token. curl only helps observe the response and does not enforce browser CORS policy.

## 6. Common Issues and Tracing the Root Cause

| Symptom | Check | Fix |
| --- | --- | --- |
| OPTIONS returns 401/302 | securityMatcher accepts only actual methods, fallback is chosen, or http.cors is missing | Route preflight to the right chain and run CORS before auth |
| OPTIONS returns 403 | Origin, method, or **Access-Control-Request-Headers** is not in policy | Compare actual request against the group's CorsConfiguration |
| Catalog origin can read operations | Shared matcher/policy too broad or proxy generates headers | Restrict origins per endpoint; add negative tests across groups |
| Duplicate Access-Control-Allow-Origin | MVC config, Security CorsFilter, and proxy all add headers | Pick a single responsible owner and remove overlapping configs |
| Preflight 200 yet actual 401/403 | CORS valid, missing login/role/CSRF | Debug the security layer per the actual response |
| allow-credentials set yet cookie not sent | Cookie SameSite/Secure/domain or fetch credentials misconfigured | Check cookies and requests in the browser's Network tab |
| Browser CORS error yet curl works | Curl does not enforce CORS; origin/port/redirect or error response differs | Compare both preflight and actual request in browser Network |
| New routes swallowed by fallback | Wrong @Order or overlapping securityMatchers | Place narrow matchers before fallback; add path-based tests |

Additionally, CORS **does not block CSRF**. The browser can send certain cross-origin requests even without letting JavaScript read the response. A JWT in a cookie still carries CSRF risk; a bearer-token API manually attached in an Authorization header has a different risk assessment. Evaluate CSRF based on **how credentials are sent**, not on labels like REST/API. HTTP Basic remembered by a browser can also act as an automatically sent credential.

Do not use a broad path **/** or allowed origin **\*** as a temporary fix just to make every preflight pass. Across different environments, specify exact scheme, hostname, port, context-path, DispatcherServlet mapping, gateway, and extra filters. When using multiple chains and MVC CORS, check which **chain is actually selected first** before concluding the bug is in a controller.

## 7. Checklist for Reviewing Your Own Design

1. Which group do the path and actual HTTP method belong to? Could any preceding securityMatcher accidentally intercept the request?
2. Is OPTIONS preflight routed into the exact same chain as the actual request?
3. Does that chain's CorsConfigurationSource register the right pattern, origins, methods, headers, and credentials?
4. Is an origin allowed in group A guaranteed **not to inherit** group B's policy?
5. Do actual requests still enforce authentication, roles, and CSRF when needed?
6. Have you tested both **allowed** and **rejected** cases, including missing credentials, wrong role, missing CSRF, and disallowed origins?
7. Are there any proxies, MVC configs, or extra CorsFilters causing duplicate headers or changing behavior in production?

A clean explanation example: **OPTIONS /api/operations/tasks** from **https://console.example** enters **operationsChain** and is approved by CORS before authentication; **POST /api/operations/tasks** still requires the OPERATOR role and a CSRF token; Origin **https://catalog.example** is rejected by operations' CORS. **GET /api/catalog/items** from catalog.example is publicly readable, while **/web/** paths continue using the same-origin web policy.
