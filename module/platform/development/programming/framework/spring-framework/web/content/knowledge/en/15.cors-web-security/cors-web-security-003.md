# @CrossOrigin, global configuration, and policy combination in Spring MVC

## 1. Learning objectives

A frontend page running at `https://app.example.com` calls a Spring MVC API at `https://api.example.com`. Even though they belong to the same business system, these are **two different origins**; JavaScript in the browser is governed by the **same-origin policy**. CORS (**Cross-Origin Resource Sharing**) is the HTTP mechanism that lets the server decide which origins the browser permits to read responses and which cross-origin requests are allowed under the CORS protocol.

In Spring MVC, there are two configuration levels that are very easy to misunderstand:

- **Local**: the `@CrossOrigin` annotation on a controller or method.
- **Global**: `WebMvcConfigurer#addCorsMappings` or corresponding `CorsConfiguration`/filter configurations.

If **both** are applied, Spring MVC follows a **policy combination** rule — typically **merging lists** while **overriding single-valued properties**. Never assume that a method annotation is always "stricter" or "completely overrides" the global configuration.

This lesson helps you:

1. Distinguish **origin**, **site**, CORS, preflight, actual/simple requests, and key HTTP headers.
2. Use `@CrossOrigin` at method/class level and understand the defaults and limits of each attribute.
3. Use `WebMvcConfigurer#addCorsMappings` to define policies by URL path.
4. Accurately explain `CorsConfiguration.combine`, additive lists, local scalar overrides, wildcards, `allowedOriginPatterns`, and credential rules.
5. Integrate Spring MVC CORS with Spring Security in the right order; distinguish CORS from authentication, authorization, CSRF, `SameSite` cookies, and reverse proxies.
6. Write a runnable example using **Java 17+, Spring Boot 3.x, Spring Framework 6.x**, along with MockMvc tests verifying **preflight**, **actual requests**, combined configurations, and rejected origins.
7. Diagnose CORS errors systematically instead of blindly adding `Access-Control-Allow-Origin: *`.

**Version scope:** Spring MVC (Servlet stack), Spring Framework **6.x**, and Spring Boot **3.x**. The demo code uses `spring-boot-starter-web` and does not include Spring Security by default. For Spring Framework 7/Boot 4, check the version-specific Javadoc/API before porting the example directly.

## 2. Determine the origin before analyzing policy combination

For HTTP(S), **origin = scheme + hostname + effective port**. Therefore `https://app.example.com` and `https://api.example.com` are two different origins; the path `/api/items` does not affect the comparison. `http://localhost:3000` and `http://localhost:8080` also have different origins because of different ports.

In this lesson, the problem is no longer re-learning the entire same-origin table, but understanding that **one handler can receive CORS permissions from two places**. For instance, the API at `https://api.example.com` sets a global policy for `https://app.example.com`, while a partner handler separately declares `https://partner.example.com`. The question to test is whether the origin list is **merged or replaced**, and whether attributes like `maxAge` follow the same rule.

| Policy source | Example | Responsibility to review |
| --- | --- | --- |
| Global `WebMvcConfigurer` | `https://app.example.com` on `/api/**` | Shared permissions across many routes |
| Local `@CrossOrigin` | `https://partner.example.com` on one handler | Additive permissions; does not narrow global by default |
| Spring Security/proxy | Filter chain, gateway, or CDN | Handle CORS only at the designed layer, avoiding conflicting independent policies |

Two subdomains can be **same-site for cookies yet cross-origin for JavaScript**. CORS does not authenticate a principal and does not stop `curl` from calling the API; authentication, authorization, and CSRF remain independent protective layers. The next section uses actual/preflight requests to see how Spring merges configurations rather than merely comparing URLs.

## 3. Two CORS flows: actual request and preflight

### 3.1. Actual request

Example data-reading request:

~~~http
GET /api/items HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

The server can return:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

[{"id":1,"name":"Book"}]
~~~

`Access-Control-Allow-Origin` determines which origin is allowed to read the response under CORS conditions. `Vary: Origin` informs intermediate caches that response headers may depend on Origin; caches/proxies must fully respect `Vary`.

**Do not infer** from the presence of `Access-Control-Allow-Origin` that the endpoint is protected by authentication. Without auth, outsiders can still call the API directly, regardless of CORS.

### 3.2. Preflight request

For requests requiring preflight, such as using `PATCH` or a custom request header, the browser usually sends **OPTIONS** first:

~~~http
OPTIONS /api/items/1 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-request-id
~~~

The server responds if the policy permits:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

The headers above are **a syntax example**, not a guarantee of line ordering or exact values across every Spring project. `Access-Control-Max-Age` is in **seconds**, describing how long the preflight result may be cached; browsers may enforce a lower cap.

If preflight fails, the browser **does not send the actual request** it intended to send under the CORS flow. Because preflight is an OPTIONS request sent by the browser, the frontend does not need to manually call a separate OPTIONS request before every request.

A **simple request** (a common term) does not require preflight when it satisfies conditions on the method and safelisted headers/content types. For example, a regular cross-origin `GET` can be sent directly; the browser still checks the CORS response before letting JavaScript read it. With `Content-Type: application/json` on a cross-origin POST request, preflight is usually performed because that media type is not safelisted for that case.

### Headers to remember

| Header | Direction | Meaning |
| --- | --- | --- |
| `Origin` | Request | Client origin per HTTP/browser |
| `Access-Control-Request-Method` | Preflight request | Intended actual method |
| `Access-Control-Request-Headers` | Preflight request | Intended non-safelisted request headers |
| `Access-Control-Allow-Origin` | Response | Origin allowed to read under CORS |
| `Access-Control-Allow-Methods` | Preflight response | Accepted HTTP methods |
| `Access-Control-Allow-Headers` | Preflight response | Permitted request headers |
| `Access-Control-Allow-Credentials` | Response | Permits credentialed CORS response when `true` |
| `Access-Control-Expose-Headers` | Actual response | Additional response headers JS is permitted to read |
| `Access-Control-Max-Age` | Preflight response | TTL of preflight permission |
| `Vary` | Response | Cache key depends on Origin/preflight headers |

`allowedHeaders` is for **headers sent by the client**; `exposedHeaders` is for **response headers JavaScript wants to read**. Confusing these two groups often causes the frontend to report "cannot read `X-Request-Id`" even though the API request returned 200.

## 4. Where does Spring MVC handle CORS?

On the Servlet MVC stack, `HandlerMapping` supports CORS. When a request is mapped to a controller, Spring can retrieve the `CorsConfiguration` by URL (global) and by `@CrossOrigin` (local), then combine them for the handler.

- Matching **preflight** is handled directly according to the CORS configuration instead of invoking the business handler.
- **Actual/simple CORS** is checked and response headers are added if permitted.
- If no matching CORS configuration exists, the server typically omits CORS headers on the actual request; the browser will not let JavaScript read it. Preflight without a permitting configuration is usually rejected.
- If Origin is disallowed or preflight method/headers do not match, Spring's `DefaultCorsProcessor` can return **403 Invalid CORS request**.
- If the request is **same-origin**, CORS is not the relevant permission check; the controller is still invoked normally under security/business policies.

**Especially important:** CORS operates primarily at the **edge between the browser and MVC request mapping**. It does not automatically protect static files on a CDN, gateway, or endpoints that do not pass through the same HandlerMapping; those other response paths must have CORS configured at the layer serving them.

## 5. `@CrossOrigin` at method and class level

A REST method:

~~~java
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @CrossOrigin(origins = "https://app.example.com")
    @GetMapping("/items")
    public List<Item> items() {
        return List.of(new Item(1L, "Book"));
    }

    public record Item(long id, String name) {}
}
~~~

**This is a controller illustration snippet**; it needs imports and its own file. `@CrossOrigin` applies to the `GET /api/catalog/items` handler; other methods in the same class do not automatically inherit this annotation.

The annotation can be placed on the class:

~~~java
@CrossOrigin(
        origins = {"https://app.example.com", "https://admin.example.com"},
        maxAge = 3600)
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {
    // Matching handler methods in this class use the CORS configuration.
}
~~~

This is also an abbreviated example. Class-level `@CrossOrigin` supplies configuration to multiple handlers, method-level annotations can add customizations, and they are also **combined**, not simply wiping out the class-level policy.

### Dangerous default if overlooked

~~~java
@CrossOrigin
@GetMapping("/items")
public List<Item> items() {
    return service.findAll();
}
~~~

This is an illustrative method. `@CrossOrigin` **with no arguments** defaults to allowing **all origins** and **all headers**, the HTTP methods mapped to the handler, a typical preflight maxAge of **1800 seconds**, and **does not allow credentials by default**. It easily makes a frontend demo work, yet can also grant public API read access to any website. Do not use a bare `@CrossOrigin` on APIs containing sensitive data just for a "quick CORS fix."

### Key attributes

| `@CrossOrigin` | Meaning |
| --- | --- |
| `origins` / `value` | Specific origin list, e.g. `https://app.example.com` |
| `originPatterns` | More flexible origin patterns; use only when needed and tightly bounded |
| `methods` | HTTP methods for CORS; note the handler's mapped methods |
| `allowedHeaders` | Request headers the browser may send after preflight |
| `exposedHeaders` | Additional response headers JS is allowed to read |
| `allowCredentials` | String `"true"`/`"false"` in Spring Framework 6.x's annotation |
| `maxAge` | Preflight cache TTL, in seconds |

`@CrossOrigin(allowCredentials = "true")` uses a **String** in the annotation per Spring 6.x API, not a Java boolean literal. When credentials are enabled, `origins = "*"` is rejected because it cannot satisfy the credentialed CORS response standard. Specify concrete origins or suitably constrained patterns instead.

## 6. Global CORS configuration with `WebMvcConfigurer`

Spring Framework 6.x / Spring Boot 3.x example:

~~~java
@Configuration
public class ApiCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com")
                .allowedMethods("GET", "POST", "PUT", "DELETE")
                .allowedHeaders("Content-Type", "Authorization")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(true)
                .maxAge(600);
    }
}
~~~

This is an **illustrative class**, requiring imports for `Configuration`, `WebMvcConfigurer`, and `CorsRegistry`. It applies to URLs matching `/api/**` handled by MVC; routes outside the pattern do not automatically receive this policy.

**Note on credentials:** enable `allowCredentials(true)` only if the frontend actually sends cookies, HTTP authentication, or required credentials and the trust boundary is appropriate. `Authorization: Bearer ...` is a request header that must be allowed through preflight, yet **does not automatically require enabling cookie credentials** just because the endpoint uses a bearer token. Evaluate how the frontend sends auth and specific Fetch rules.

### Defaults of global registration

If you call `registry.addMapping("/api/**")` without further restrictions, the default configuration typically permits **all origins**, **all headers**, **GET/HEAD/POST**, `maxAge=1800` seconds, and **credentials disabled**. Therefore explicitly set `allowedOrigins` for applications with non-public data.

In a standard Spring Boot application, `WebMvcConfigurer` is the way to extend MVC configuration **without** needing `@EnableWebMvc`. Adding `@EnableWebMvc` in Boot solely to enable CORS is unnecessary and can disable many useful Web MVC auto-configuration behaviors.

### Local and global are not isolated from each other

If both global `/api/**` and a method-level `@CrossOrigin` match, Spring combines **both configurations**. You cannot look only at the method annotation and conclude what final policy the browser will see. Check every active configuration, including any CORS filter, Spring Security, and gateway.

## 7. The `CorsConfiguration.combine` mechanism: the core part

In Spring MVC 6.x, when **both global and local apply**, configurations are combined according to `CorsConfiguration#combine` rules.

### 7.1. List-valued properties usually merge additively

List-based fields such as **`allowedOrigins`**, **`allowedOriginPatterns`**, **`allowedMethods`**, **`allowedHeaders`**, and **`exposedHeaders`** generally combine in an **additive / union** manner.

Suppose:

- Global `allowedOrigins = [https://app.example.com]`.
- Method `@CrossOrigin(origins = "https://partner.example.com")`.

The result for that endpoint can allow **both** `https://app.example.com` **and** `https://partner.example.com`. The method annotation **expands** the origin set compared to global; it **does not** turn it into "partner only."

For headers:

- Global `allowedHeaders = [Content-Type]`.
- Local `allowedHeaders = [X-Partner-Key]`.
- Combined: requests can use both `Content-Type` and `X-Partner-Key` when other conditions hold.

Similarly, `exposedHeaders` from global and local are merged; the frontend can read both listed response headers if the response actually includes them.

**Special wildcard `"*"` behavior:** if one combined list contains a wildcard meaning allow-all, the result may remain wildcard rather than being "narrowed" to the explicit list. Default values set by `applyPermitDefaultValues()` also have special handling when encountering explicit values. Therefore, never rely on slogans like "local always overrides" or "global always wins"; inspect the post-combine result and test it in practice.

### 7.2. Scalar properties: local overrides global

Single-valued properties such as:

- `allowCredentials`
- `maxAge`
- `allowPrivateNetwork` when used in the corresponding Spring version

combine so that **a non-null local value overrides global**. For example:

- Global `maxAge = 600`.
- Method `@CrossOrigin(maxAge = 1200)`.
- The method endpoint gets preflight `Access-Control-Max-Age: 1200` in valid cases.

Conversely, if the method does not declare `allowCredentials`, it normally inherits the global policy instead of automatically flipping the value. Distinguish explicit attributes from `null`/unspecified values.

### 7.3. Decision table

| Property | Global | Local | Interpretation after combine |
| --- | --- | --- | --- |
| origins | `app.example.com` | `partner.example.com` | Allows both origins unless another wildcard is present |
| allowedMethods | GET, POST | PATCH | Typically merges to GET, POST, PATCH, though still subject to handler mapping |
| allowedHeaders | Content-Type | X-Partner-Key | Both header names |
| exposedHeaders | X-Trace-Global | X-Trace-Partner | Both response header names |
| maxAge | 600 | 1200 | 1200 (local overrides) |
| allowCredentials | false | true | true (local overrides if explicitly declared) |

**Warning:** The table illustrates `CorsConfiguration` rules and does not claim each HTTP method has a corresponding business handler. CORS `allowedMethods` does not create a `@PatchMapping` and does not grant update permission at the security layer. If a method has no matching route, the request may still hit 404/405 or be blocked by security.

### 7.4. Why a global wildcard cannot be "narrowed" by a method annotation

Suppose global applies `allowedOrigins("*")` and local specifies a trusted domain; you **cannot assume the method has narrowed** all allowed origins. The effective configuration may still remain very broad after combine. With cookie credentials, there is also the risk of an invalid configuration if a wildcard mixes with `allowCredentials(true)`.

**The right fix** is making the global policy narrow enough from the start, choosing precise mappings (e.g., `/api/public/**` and `/api/private/**`), or putting the policy into a single `CorsConfigurationSource` when strict control is required. Do not treat a local annotation as a "deny rule" against a global `"*"`.

## 8. Wildcards, `allowedOriginPatterns`, and credentials

### 8.1. `allowedOrigins("*")` without credentials

A completely public resource API may choose `Access-Control-Allow-Origin: *` when the data is genuinely meant to be read by any browser origin and credentials are not used. This is an intentional **product/security decision**, not a "fix all CORS errors" setting.

### 8.2. Do not use `"*"` with `allowCredentials(true)`

Browsers reject credentialed CORS responses when `Access-Control-Allow-Origin: *`. Spring MVC 6.x also validates and rejects the invalid combination of `allowedOrigins("*")` with `allowCredentials(true)`.

Better:

~~~java
registry.addMapping("/api/private/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST")
        .allowCredentials(true);
~~~

This is an **illustrative snippet** inside `addCorsMappings`, not a standalone Java class. When using cookie sessions, manage CSRF and cookie scope/SameSite alongside CORS.

### 8.3. `allowedOriginPatterns` for controlled subdomains

~~~java
registry.addMapping("/api/tenant/**")
        .allowedOriginPatterns("https://*.trusted.example.com")
        .allowedMethods("GET")
        .allowCredentials(true);
~~~

When a pattern matches, Spring returns the **matched origin** in `Access-Control-Allow-Origin`, not the pattern string or `"*"`. This allows certain credentialed CORS configurations with patterns within a bounded trust boundary.

However, `https://*.trusted.example.com` **does not automatically prove every subdomain is trustworthy**: user-controlled subdomains, subdomain takeover, or poorly managed DNS can widen the attack surface. If you have a finite tenant list, an explicit origin allowlist managed via configuration is easier to audit. Validate both scheme and port—never allow `http` solely for dev convenience.

### 8.4. Cache policies and exposed headers

`Access-Control-Max-Age` lets the browser cache preflight, though many browsers enforce their own caps. It does **not** dictate how long clients/caches may store API data; data caching belongs to `Cache-Control`, ETag, and HTTP caching mechanisms.

`Access-Control-Expose-Headers` controls which response headers JavaScript may read (beyond safelisted response headers). Never leak sensitive tokens in response headers and try to "protect" them by omitting them from expose: same-origin scripts and many non-browser HTTP clients can still read them; the server must still be designed securely.

## 9. Spring Boot 3.x example: global + local truly combining

Let's build a verifiable demo:

- **Global:** all `/api/**` routes allow origin `https://app.example.com`, methods GET/POST, headers `Content-Type` and `X-Requested-With`, exposed header `X-Global-Trace`, preflight maxAge **600**.
- **Local:** handler `GET /api/demo/partner` adds origin `https://partner.example.com`, adds request header `X-Partner-Key`, adds exposed header `X-Partner-Trace`, and sets maxAge **1200**.
- **Result:** endpoint `/api/demo/global` allows only `app.example.com` from global. Endpoint `/api/demo/partner` allows **app + partner** because origins merge additively; both `X-Global-Trace` and `X-Partner-Trace` are exposed, and local maxAge is 1200.

Maven project with **Java 17+**, **Spring Boot 3.x**; dependencies **Spring Web** and **Spring Boot Starter Test**. Generate with Spring Initializr, package `com.example.demo`.

Files:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/GlobalCorsConfig.java
src/main/java/com/example/demo/CorsDemoController.java
src/test/java/com/example/demo/CorsPolicyTest.java
~~~

### 9.1. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. `GlobalCorsConfig.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class GlobalCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Requested-With")
                .exposedHeaders("X-Global-Trace")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

### 9.3. `CorsDemoController.java`

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class CorsDemoController {

    @GetMapping("/global")
    public ResponseEntity<Map<String, String>> globalOnly() {
        return ResponseEntity.ok()
                .header("X-Global-Trace", "global-001")
                .body(Map.of("scope", "global"));
    }

    @CrossOrigin(
            origins = "https://partner.example.com",
            allowedHeaders = "X-Partner-Key",
            exposedHeaders = "X-Partner-Trace",
            maxAge = 1200)
    @GetMapping("/partner")
    public ResponseEntity<Map<String, String>> partner() {
        return ResponseEntity.ok()
                .header("X-Global-Trace", "global-002")
                .header("X-Partner-Trace", "partner-002")
                .body(Map.of("scope", "global-plus-local"));
    }
}
~~~

The code above runs in a standard Spring Boot 3.x `@RestController` without Spring Security. To demonstrate additive combination, definitely **do not change global to `allowedOrigins("*")`** expecting local to narrow it; doing so completely alters what the test measures and can open CORS too broadly.

### 9.4. Why is this different from two independent policies?

`/api/demo/global` has no annotation, only the global policy.

`/api/demo/partner` falls under `/api/**` so it **receives the global policy**, while also having a local annotation. Spring MVC combines both:

~~~text
/ api / demo / partner
        |
        +--- global (/api/**)
        |       allowedOrigins: app.example.com
        |       allowedHeaders: Content-Type, X-Requested-With
        |       exposedHeaders: X-Global-Trace
        |       maxAge: 600
        |
        +--- local (@CrossOrigin on method)
                allowedOrigins: partner.example.com
                allowedHeaders: X-Partner-Key
                exposedHeaders: X-Partner-Trace
                maxAge: 1200
        |
        v
  effective CORS policy:
    origins: app + partner
    headers: Content-Type + X-Requested-With + X-Partner-Key
    exposed: X-Global-Trace + X-Partner-Trace
    maxAge: 1200
~~~

The snippet above is an explanatory diagram, not a configuration file. It highlights that **there is no automatic AND intersection** between global origins and local origins.

## 10. Testing CORS with MockMvc

With Spring Boot 3.x and `spring-boot-starter-test`, file **`src/test/java/com/example/demo/CorsPolicyTest.java`**:

~~~java
package com.example.demo;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPolicyTest {

    private static final String APP = "https://app.example.com";
    private static final String PARTNER = "https://partner.example.com";

    @Autowired
    MockMvc mockMvc;

    @Test
    void globalEndpointAllowsConfiguredOrigin() throws Exception {
        mockMvc.perform(get("/api/demo/global")
                        .header(HttpHeaders.ORIGIN, APP))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result
                        .MockMvcResultMatchers.header()
                        .string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, APP))
                .andExpect(jsonPath("$.scope").value("global"));
    }

    @Test
    void localEndpointAlsoAllowsGlobalOrigin() throws Exception {
        mockMvc.perform(get("/api/demo/partner")
                        .header(HttpHeaders.ORIGIN, APP))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result
                        .MockMvcResultMatchers.header()
                        .string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, APP));
    }

    @Test
    void partnerOriginIsAddedOnlyForLocalEndpoint() throws Exception {
        mockMvc.perform(get("/api/demo/partner")
                        .header(HttpHeaders.ORIGIN, PARTNER))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result
                        .MockMvcResultMatchers.header()
                        .string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                                PARTNER))
                .andExpect(jsonPath("$.scope")
                        .value("global-plus-local"));
    }

    @Test
    void globalOnlyEndpointRejectsPartnerPreflight() throws Exception {
        mockMvc.perform(options("/api/demo/global")
                        .header(HttpHeaders.ORIGIN, PARTNER)
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void partnerPreflightCombinesHeadersAndOverridesMaxAge()
            throws Exception {
        MvcResult response = mockMvc.perform(
                        options("/api/demo/partner")
                                .header(HttpHeaders.ORIGIN, PARTNER)
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                        "GET")
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                        "X-Partner-Key"))
                .andExpect(status().isOk())
                .andReturn();

        assertEquals(PARTNER, response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
        assertEquals("1200", response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE));

        String allowedHeaders = response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
        assertNotNull(allowedHeaders);
        assertTrue(allowedHeaders.toLowerCase(Locale.ROOT)
                .contains("x-partner-key"));
    }

    @Test
    void localEndpointExposesBothResponseHeaders() throws Exception {
        MvcResult response = mockMvc.perform(
                        get("/api/demo/partner")
                                .header(HttpHeaders.ORIGIN, PARTNER))
                .andExpect(status().isOk())
                .andReturn();

        String exposed = response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS);
        assertNotNull(exposed);
        assertTrue(exposed.contains("X-Global-Trace"));
        assertTrue(exposed.contains("X-Partner-Trace"));
    }

    @Test
    void globalPreflightUsesGlobalMaxAge() throws Exception {
        MvcResult response = mockMvc.perform(
                        options("/api/demo/global")
                                .header(HttpHeaders.ORIGIN, APP)
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                        "GET")
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                        "X-Requested-With"))
                .andExpect(status().isOk())
                .andReturn();

        assertEquals("600", response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

**Code note:** the example uses the fully qualified `MockMvcResultMatchers.header()` call to avoid ambiguity with `HttpHeaders`. You can use a static import for `header` to keep the code shorter. Package and class names are placed precisely so the test finds the Spring Boot application context in the root package.

The tests demonstrate:

- A global origin is allowed to access both the global-only endpoint and the locally annotated endpoint.
- The partner origin is added only on the annotated handler.
- Local preflight has `Access-Control-Max-Age: 1200`, while global uses 600.
- Request header `X-Partner-Key` is permitted in local preflight.
- `exposedHeaders` from global and local are unioned.
- Preflight from partner to the global-only endpoint is blocked by Spring, typically with HTTP 403.

**Limitations:** MockMvc verifies the policy Spring MVC produces; it **does not execute a real browser's CORS algorithm**, does not simulate a cookie store, does not check a CDN/gateway, and does not measure preflight cache lifetimes in Chrome/Firefox. For production, add browser end-to-end tests under real HTTPS origins and inspect the Network panel.

## 11. Testing CORS with curl without a frontend

### 11.1. Actual request from the global origin

~~~bash
curl -i "http://localhost:8080/api/demo/global"   -H "Origin: https://app.example.com"
~~~

Expected status **200 OK**, with:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

### 11.2. Actual request from the partner origin to the local method

~~~bash
curl -i "http://localhost:8080/api/demo/partner"   -H "Origin: https://partner.example.com"
~~~

Expected status **200 OK**, with headers:

~~~http
Access-Control-Allow-Origin: https://partner.example.com
Access-Control-Expose-Headers: X-Global-Trace, X-Partner-Trace
~~~

The order and formatting of the two exposed headers may vary; check header tokens rather than strict ordering.

### 11.3. Preflight for a custom header

~~~bash
curl -i -X OPTIONS   "http://localhost:8080/api/demo/partner"   -H "Origin: https://partner.example.com"   -H "Access-Control-Request-Method: GET"   -H "Access-Control-Request-Headers: X-Partner-Key"
~~~

Expected result: status **200 OK** with `Access-Control-Allow-Origin: https://partner.example.com`, `Access-Control-Allow-Headers` containing `X-Partner-Key`, and `Access-Control-Max-Age: 1200`. This is a **preflight**; the `partner()` business method does not need to run to return the OPTIONS response.

### 11.4. Disallowed origin

~~~bash
curl -i -X OPTIONS   "http://localhost:8080/api/demo/global"   -H "Origin: https://partner.example.com"   -H "Access-Control-Request-Method: GET"
~~~

With `DefaultCorsProcessor` and the configuration above, the status is typically **403 Forbidden**. `curl` still reads the response regardless of CORS; the browser blocks on the script side according to the CORS mechanism.

On Windows PowerShell, use `curl.exe` to avoid the `curl` alias and adjust line continuation per your shell. The lines above use Linux/macOS/Git Bash syntax.

## 12. Integrating Spring Security: CORS must run before authentication

When an application includes **Spring Security 6.x** (commonly paired with Boot 3.x), a standard OPTIONS preflight **does not carry session cookies**. If the security filter demands authentication before CORS is handled, the browser may see OPTIONS return 401/403 and never send the actual request.

Spring Security provides CORS support inside the security filter chain. When using MVC `WebMvcConfigurer` without declaring a separate `CorsConfigurationSource`, you can let Security use MVC's configuration:

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll());
        return http.build();
    }
}
~~~

**This is an illustrative class for projects that add the `spring-boot-starter-security` dependency**; it needs imports for `@Configuration`, `@Bean`, `SecurityFilterChain`, `HttpSecurity`, and `Customizer`. Authentication provider/login/session strategy must be configured to fit the real application. Do not copy this code into section 9's demo if you only want to test pure MVC CORS.

If the application needs a dedicated `CorsConfigurationSource`, you can register a `UrlBasedCorsConfigurationSource` and pass it to Security. However, **do not** unintentionally configure multiple `CorsFilter`s or conflicting CORS sources: responses may end up with duplicate CORS headers, or Security/filter policies may diverge from method annotations.

### Choosing the integration path

| Architecture | Starting approach |
| --- | --- |
| Pure Spring MVC, no Security | `@CrossOrigin` and/or `WebMvcConfigurer` |
| Boot 3 + Spring Security 6 with MVC CORS configured | `http.cors(Customizer.withDefaults())` leveraging MVC when appropriate |
| Security with multiple filter chains, distinct policies | Assign the corresponding `CorsConfigurationSource` per chain |
| CORS needed before MVC or for non-handler endpoints | `CorsFilter`/gateway with clear ownership |
| Reverse proxy or API gateway owns CORS | Configure at the gateway and avoid duplicate/inconsistent policies in the app |

Even when Spring Security handles preflight properly, **the actual request must still satisfy authentication and authorization**. An OK preflight does not let a user bypass security.

## 13. Credentialed requests, SameSite cookies, and CSRF

The frontend can call an API with cookies when the policy allows:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
const user = await response.json();
~~~

For the browser to let script read a credentialed CORS response, the backend must return a **specific origin** and `Access-Control-Allow-Credentials: true`. Adding `credentials: "include"` does **not** magically make browser-blocked cookies appear:
- Cookies remain constrained by `Domain`, `Path`, `Secure`, expiry, and `SameSite`.
- Some browsers block third-party cookies and enforce partitioning/tracking protection.
- Cross-origin yet same-site behaves differently for cookies than cross-site.
- Preflight is not an authorized request merely because the client wants to send credentials.

**SameSite** restricts when the browser sends cookies based on site relationships. **CORS** restricts how cross-origin JavaScript can interact with/read responses per server policy. **CSRF** is the forged-request problem when the browser automatically attaches auth cookies. CORS **does not replace CSRF tokens**, nor does it block every HTML form or cross-site navigation with side effects. With cookie-based authentication, use proper CSRF protection, per-operation authorization, and obey safe method semantics.

**Origin allowlists must align with trust boundaries:** if you permit credentialed CORS from an origin controlled by a third party, scripts on that origin can access whatever data the authenticated user is allowed to see and CORS exposes. Never add an uncontrolled origin merely because it nominally belongs to the same organization.

## 14. When combine makes the policy broader than expected

### 14.1. Overly broad global policy

~~~java
registry.addMapping("/**")
        .allowedOrigins("*")
        .allowedMethods("*");
~~~

This is an **anti-pattern example** for applications with private data. If a method later adds `@CrossOrigin(origins="https://trusted.example.com")`, you cannot assume the endpoint is now restricted only to the trusted origin; list combination may keep all origins allowed.

**Fix:** keep the global policy narrow and separate public/private routes; avoid `**` if only `/api/public/**` needs open CORS.

### 14.2. Local enabling credentials against global intent

~~~java
@CrossOrigin(
        origins = "https://partner.example.com",
        allowCredentials = "true")
@GetMapping("/private")
public SecretView privateData() {
    // ...
}
~~~

This is a **non-standalone illustrative handler** and requires authentication/authorization. `allowCredentials` is a scalar, so an explicit local setting can override global. If global origins are broad, combining them can become invalid or dangerous. Inspect the effective CorsConfiguration and test that non-allowlisted origins cannot receive private data.

### 14.3. Wildcard headers and methods

If a configuration allows `allowedHeaders("*")`, Spring may reflect specific request headers in the preflight response, especially when credentials are enabled; do not assume every header is inherently safe. Headers like `Authorization` and `X-Admin-Key` require dedicated application policies and validation.

`allowedMethods("*")` likewise does not make controllers accept every HTTP method, but it widens the CORS gate unnecessarily. For APIs with mutating methods, allow only the methods genuinely needed.

### 14.4. Mixing `CorsFilter`, `@CrossOrigin`, and a gateway

A reverse proxy may add ACAO `*` while Spring MVC returns a specific origin ACAO. Browsers may treat responses with **multiple Access-Control-Allow-Origin headers** as invalid. Do not patch around this by adding extra headers in controllers; designate **a single owning layer** for the CORS policy or configure them consistently to avoid duplicates.

## 15. CORS does not replace authorization: threat illustration

Suppose `GET /api/admin/reports` returns sensitive reports. If you only configure CORS to allow an internal origin **without** requiring a role, a user can still call the endpoint directly via an HTTP client. CORS is only a browser permission, not an ACL.

Conversely, an authenticated API can still be accessed cross-origin from scripts on an allowed origin. If `allowCredentials(true)` is set and an attacker controls an origin on the allowlist, the attacker can leverage the ability to read responses with the logged-in user's privileges. Therefore choosing origins is part of threat modeling.

Proper defense requires combining:
1. Server-side authentication and authorization.
2. A minimal CORS allowlist for real frontends.
3. CSRF protection when auth relies on cookies and for state-changing operations.
4. Cookie flags `Secure`, `HttpOnly`, and `SameSite` matched to the use case.
5. Preventing XSS in the frontend, since script running on a trusted origin inherits that origin's CORS permissions.
6. Logging/tracing that never leaks access tokens, session cookies, or sensitive data.

## 16. When encountering a CORS error: inspection workflow

Do not rely solely on the console line "blocked by CORS policy." Inspect the **Network panel** and check across layers:

| Symptom | Possible cause | Verification direction |
| --- | --- | --- |
| OPTIONS returns 401/403 before handler | Spring Security/filter blocks preflight | Configure `http.cors(...)`, check filter order, logs |
| OPTIONS 403 Invalid CORS request | Origin/method/headers not granted | Compare effective config after combine |
| GET 200 yet JS cannot read body | Missing `Access-Control-Allow-Origin`, credentials mismatch, duplicate CORS headers | Inspect actual response headers |
| API works in Postman but fails in browser | HTTP client does not enforce browser same-origin policy | Send `Origin` and preflight to diagnose server |
| Cookie not sent | `credentials`, SameSite, Secure, Domain/Path, third-party policy | DevTools Cookies and Request Headers |
| `Access-Control-Allow-Origin: *` with credentials | Combination rejected by browser | Use specific origin allowlist and ACAC true |
| Request header X-Token rejected | Not in `allowedHeaders` or preflight mismatch | Check `Access-Control-Request-Headers` |
| JS cannot read `X-Request-Id` | Missing `exposedHeaders` | Set `Access-Control-Expose-Headers` |
| Local policy does not "narrow" global | Origins/methods/headers combine via union | Inspect global + local, narrow global |
| Fails only in production | Gateway/CDN adds/strips headers, proxy rewrite, HTTPS redirect | Compare backend and gateway responses |
| Cache returns another origin's ACAO | CDN ignores `Vary: Origin` | Fix cache key/`Vary` configuration |
| Server redirects during preflight | HTTP→HTTPS or login redirect; browsers handle poorly | Use proper HTTPS/API URL upfront, run auth after CORS |
| Right origin hostname but wrong port | Origin includes scheme, host, and port | Compare exact Origin header, not just hostname |

### Seven-step debugging

1. Open DevTools → **Network** → find the OPTIONS preflight and actual request; compare Origin, method, and custom headers.
2. Inspect the preflight response: status, ACAO, Allow-Methods, Allow-Headers, Max-Age. A 401/403 may come from security/gateway outside Spring MVC.
3. Inspect the actual response: ACAO, ACAC, exposed headers, and Vary. Verify there are no conflicting duplicate ACAOs.
4. Review global `/api/**` path mappings, class-level/method-level `@CrossOrigin`, combine rules, and Security configuration.
5. Check frontend `fetch`: `credentials`, URL, method, Content-Type, headers, cookie policy, and redirects.
6. If it fails only behind a proxy/CDN, call the backend directly (in an allowed environment) and compare headers against the gateway.
7. Write MockMvc tests for **allowed origin**, **disallowed origin**, preflight **method/header**, credentials, and **combined configurations** before redeploying.

**Do not** fix this by slapping `@CrossOrigin(origins = "*")` on every controller or disabling Spring Security CORS/CSRF. Those changes may silence browser errors while widening the attack surface.

## 17. Review questions

**1. Does placing `@CrossOrigin(origins="https://partner.example.com")` on a method erase the global origin list?**

Not by default. Spring MVC 6.x combines origin lists additively. If global allows `app.example.com`, the method can allow both app and partner.

**2. How is the `maxAge` attribute combined between global and local?**

It is a scalar property: if local declares a non-null value, local overrides global. Global 600 + local 1200 on the method → preflight maxAge 1200.

**3. Why do OPTIONS preflight requests usually lack session cookies?**

Preflight is a browser policy check and does not automatically send credentials like an actual authenticated request. Security must allow CORS to be processed before auth when applicable.

**4. Does CORS protect an API when called from curl?**

No. curl does not enforce the browser's same-origin policy. APIs must be protected with authentication, authorization, and business validations.

**5. How do `allowedHeaders` and `exposedHeaders` differ?**

`allowedHeaders` controls which request headers the browser may send after preflight; `exposedHeaders` lets JS read additional response headers from the actual response.

**6. What elements are required when sending cookies via cross-origin fetch?**

Appropriate frontend `credentials`, server ACAO with specific origin + ACAC true, cookie Domain/Path/Secure/SameSite conditions satisfied, not blocked by the browser, and properly designed CSRF/authorization.

**7. Does `allowedOriginPatterns` permit using wildcards with credentials?**

It can, because for a matching pattern Spring returns the actual matched origin rather than `"*"`. However, overly broad patterns remain risky and must stay within the trust boundary.

**8. Can global origins `"*"` be narrowed by specific local origins?**

Never assume so. Fix the global policy, separate route scopes, and test the effective config instead of hoping a local annotation acts as a deny rule.

## 18. Practical application checklist

1. List real frontend origins by **scheme + host + port**. Open only necessary origins.
2. For public and private APIs, separate URL patterns clearly; never set a global wildcard and try to narrow it locally.
3. Use `@CrossOrigin` for clear exceptions, or `WebMvcConfigurer` for a consistent policy. When using both, review **combine**.
4. Remember list-valued properties generally merge additively, while non-null local scalars override global.
5. Enable `allowCredentials(true)` only when truly needed; never combine `allowedOrigins("*")` with credentials.
6. With Spring Security, process CORS preflight before authentication; avoid multiple different filters/gateways producing duplicate headers.
7. Keep `allowedMethods`/`allowedHeaders` minimal, and `exposedHeaders` limited to response headers the frontend actually needs to read.
8. Enforce CSRF, cookie protections, and XSS prevention independently; CORS is neither authentication nor authorization.
9. Test actual requests and preflight for both valid and invalid origins; check maxAge, exposed headers, credentials, and Vary.
10. Verify HTTPS, proxy/CDN behavior, and browser integration, not just MockMvc or Postman.

## Official sources

- [Spring Framework 6.2 — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html)
- [Spring Framework 6.2 — `@CrossOrigin` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/CrossOrigin.html)
- [Spring Framework 6.2 — `CorsConfiguration#combine` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — HTTP Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin)
- [OWASP — Cross Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
