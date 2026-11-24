# Preflight, Credentials, and Allowed Origins in Spring WebFlux

## 1. What Problem Does CORS Solve?

CORS (Cross-Origin Resource Sharing) is an HTTP mechanism that lets browsers decide whether JavaScript from one origin is allowed to read responses from a server at another origin.

Example:

- Frontend: `https://app.example.com`
- Backend API: `https://api.example.com`

These two addresses have different origins because their hostnames differ, even though they may belong to the same site. When JavaScript on the frontend calls the API, the browser sends the `Origin` header. The backend must return appropriate CORS response headers so the browser allows JavaScript to read the response.

An origin is defined by the tuple:

~~~text
scheme + host + port
~~~

Examples:

| Origin | Same origin as https://app.example.com? | Reason |
| --- | --- | --- |
| `https://app.example.com` | Yes | Same scheme, host, default port |
| `http://app.example.com` | No | Different scheme |
| `https://api.example.com` | No | Different host |
| `https://app.example.com:8443` | No | Different port |
| `https://app.example.com/admin` | Not a distinct origin | Path is not part of the origin |

Origins in an allowlist have no path and normally no trailing slash. Use `https://app.example.com`, not `https://app.example.com/`.

**CORS is a browser policy for cross-origin responses.** It does not replace authentication, authorization, CSRF protection, or server-side access control. A program calling an API with curl, Postman, or a backend service is not subjected to CORS by a browser.

## 2. Two Request Types: Simple and Preflight

CORS distinguishes simple requests from requests requiring a preflight.

### 2.1. Simple Requests

Browsers can send certain cross-origin requests without asking first via OPTIONS. The safelisted methods are:

- `GET`
- `HEAD`
- `POST`

Request headers must also belong to the CORS-safelisted group and meet value constraints. Examples include `Accept`, `Accept-Language`, `Content-Language`, and `Content-Type` with certain allowed media types.

Thus, a simple form POST can be sent directly to the server. The response still needs appropriate CORS headers for JavaScript to read the response.

### 2.2. Preflight Requests

If a request uses a non-safelisted method or includes non-safelisted request headers, the browser usually sends an OPTIONS request first. This OPTIONS request is called a **CORS preflight**.

For example, the frontend wants to send a PUT with JSON, a bearer token, and a request ID:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization,content-type,x-request-id
~~~

Meaning:

- `Origin`: origin of the page calling the API.
- `Access-Control-Request-Method`: method of the actual request about to be sent.
- `Access-Control-Request-Headers`: non-safelisted request headers the actual request wants to use.

The browser waits for the server to allow the origin, method, and headers. If the preflight fails, the browser does not send the actual PUT request.

Cases that commonly trigger a preflight:

| Request | Preflight? | Reason |
| --- | --- | --- |
| GET with standard Accept | Usually no | Method and headers are safelisted |
| Form-urlencoded POST with safelisted headers | Usually no | Request meets simple request conditions |
| PUT or PATCH | Yes | Method is not in the safelist |
| POST with Content-Type application/json | Yes | JSON media type is not in the Content-Type safelist |
| GET with X-Request-Id header | Yes | Custom header is not safelisted |
| Request with Authorization header | Yes | Authorization is a request header that must be explicitly allowed |

Enabling credentials alone does not mean every request requires a preflight. Preflight depends mainly on method and request headers. Credentials mode affects the conditions under which the browser accepts the response.

## 3. Preflight and Actual Request Flow

A request requiring a preflight takes two HTTP round trips:

~~~text
JavaScript on https://app.example.com
                  |
                  | PUT + JSON + Authorization
                  v
        Browser creates OPTIONS preflight
                  |
                  | Origin
                  | Access-Control-Request-Method: PUT
                  | Access-Control-Request-Headers: ...
                  v
            Spring WebFlux
                  |
                  | Check origin, method, headers
                  v
        Does OPTIONS response allow?
             /             \
           No               Yes
            |                |
            v                v
       Browser blocks   Browser sends actual PUT
                              |
                              | Origin + credentials if requested
                              v
                       Spring WebFlux
                              |
                              v
                       HTTP response
                              |
                              | ACAO + ACAC if required
                              v
                   Does browser let JavaScript read?
~~~

Preflight is a policy check step. It is not a business request and usually does not need a separate OPTIONS method in controllers. Spring WebFlux can handle preflight before invoking any handler.

## 4. Key Response Headers

| Response header | Meaning |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin allowed to read the response |
| `Access-Control-Allow-Credentials` | Allows the browser to expose the response when the request uses credentials mode include |
| `Access-Control-Allow-Methods` | HTTP methods allowed for the actual request |
| `Access-Control-Allow-Headers` | Request headers allowed to be sent |
| `Access-Control-Expose-Headers` | Additional response headers JavaScript is allowed to read |
| `Access-Control-Max-Age` | Duration the browser may cache the preflight result |

### 4.1. Access-Control-Allow-Origin

If allowing only one frontend:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

If the request does not use credentials, the server can return:

~~~http
Access-Control-Allow-Origin: *
~~~

Do not return multiple origins as a list in a single header value. A CORS response for a request must return the specific allowed origin or wildcard when no credentials are used.

If the server dynamically selects an origin from an allowlist, the response should include `Vary: Origin` so caches/proxies distinguish responses by request Origin.

### 4.2. Access-Control-Allow-Methods

Example:

~~~http
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
~~~

This header tells the browser which methods are permitted for the actual request. It does not create a PUT endpoint in a controller and does not grant business permissions to a user.

If an API only supports GET and POST, do not allow PUT or DELETE just to make preflights pass.

### 4.3. Access-Control-Allow-Headers

Example:

~~~http
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id, X-CSRF-TOKEN
~~~

This header allows the browser to send the corresponding request headers in the actual request.

If the frontend sends `Authorization` or custom headers, include them in the allowlist. Do not allow all headers if the API only needs a small set.

### 4.4. Access-Control-Expose-Headers

Some response headers are readable by JavaScript by default, such as `Content-Type`, `Content-Length`, `Cache-Control`, `Last-Modified`, and `Expires`.

Other headers such as `Location`, `ETag`, or `X-Request-Id` must be exposed if the frontend needs to read them:

~~~http
Access-Control-Expose-Headers: Location, ETag, X-Request-Id
~~~

`Set-Cookie` is a forbidden response header; JavaScript cannot read it by adding it to `Access-Control-Expose-Headers`.

### 4.5. Access-Control-Max-Age

Example:

~~~http
Access-Control-Max-Age: 3600
~~~

The browser can cache the preflight result for the permitted duration, reducing OPTIONS requests. This is a browser preflight cache, not a general API data cache duration. Browsers may enforce their own upper cap lower than the value sent by the server.

In Spring, `maxAge(3600)` configures the value in seconds.

## 5. What Are Credentials?

In Fetch/CORS, credentials include items such as:

- HTTP cookies.
- HTTP authentication entries.
- TLS client certificates.

With the Fetch API, the `credentials` option controls whether the browser sends cross-origin credentials and accepts credentialed responses.

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Common values:

| Fetch credentials mode | Behavior |
| --- | --- |
| `omit` | Do not send credentials |
| `same-origin` | Send credentials only for same-origin requests; this is fetch's default |
| `include` | Allow sending credentials for cross-origin requests too, if cookie/browser policies permit |

With XMLHttpRequest, the equivalent option is `xhr.withCredentials = true`.

### 5.1. allowCredentials(true) Does Not Send Cookies by Itself

The server setting:

~~~java
.allowCredentials(true)
~~~

merely tells the browser the response may be shared when the request uses credentials mode include. It does not create sessions, log users in, or force the browser to send cookies.

For cookies to be sent, the frontend must use the appropriate credentials mode; cookies must also satisfy domain, path, Secure, SameSite, and browser privacy policies.

### 5.2. Preflights Do Not Carry Cookies

A very important detail: CORS preflight requests always use credentials mode `same-origin`, so browsers do not send cross-origin cookies on OPTIONS preflights.

However, the actual request that follows can still use credentials mode `include`. Therefore, the preflight response must indicate that the server allows credentialed requests, and the actual response must also satisfy credential rules.

Preflight response example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, PUT
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Max-Age: 3600
~~~

The browser does not need cookies at the OPTIONS step. It only checks the policy to decide whether the actual request may be sent.

### 5.3. Conditions for a Credentialed Response

If a request uses credentials mode `include`, the browser requires:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

Two conditions:

1. `Access-Control-Allow-Origin` must be a specific origin matching the request Origin. It must not be `*`.
2. `Access-Control-Allow-Credentials` must have the exact lowercase value `true`.

Values like `True`, `TRUE`, or `1` are not valid substitutes for `true`.

### 5.4. Bearer Tokens in Authorization vs. Cookie Credentials

The frontend can attach a bearer token itself:

~~~javascript
fetch("https://api.example.com/api/profile", {
  headers: {
    "Authorization": "Bearer " + token
  }
});
~~~

The `Authorization` header is a request header that must be allowed in preflight. It does not mean the browser sends cookies automatically. If you only use JavaScript-managed bearer tokens and do not need cross-origin cookies/HTTP authentication, you usually do not need `credentials: "include"`.

CORS configuration still must allow `Authorization` in allowed headers. If the actual request uses credentials mode include, the server must also satisfy a specific ACAO and ACAC true.

## 6. Wildcards and Credentials: Rules to Remember

### 6.1. Do Not Use allowedOrigins("*") with allowCredentials(true)

The following configuration is invalid under CORS:

~~~java
configuration.setAllowedOrigins(List.of("*"));
configuration.setAllowCredentials(true);
~~~

Browsers reject:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

When credentials mode is include, the server must return a specific origin. Spring also checks and rejects combining wildcard origins with credentials.

The right configuration lists trusted origins:

~~~java
configuration.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com"));

configuration.setAllowCredentials(true);
~~~

### 6.2. allowedOriginPatterns

Spring supports `allowedOriginPatterns` when matching a structured group of origins:

~~~java
configuration.setAllowedOriginPatterns(List.of(
        "https://*.preview.example.com"));

configuration.setAllowCredentials(true);
~~~

When a pattern matches, Spring returns the matched actual origin in `Access-Control-Allow-Origin`, not the pattern string or a wildcard. Therefore, this API can be used with credentials.

However, the broader the pattern, the more websites are trusted. `allowedOriginPatterns("*")` effectively allows almost any origin and is very dangerous when combined with credentials. Only use tightly scoped patterns, such as a preview domain controlled by your organization.

If there are only a few fixed frontends, `allowedOrigins` with an exact list is usually easier to audit.

### 6.3. Wildcards in Methods, Headers, and Exposed Headers

The CORS specification also restricts how wildcards are interpreted when credentials mode is include.

- For allowed methods and allowed headers, wildcards should not be assumed to grant all methods/headers when credentials are present.
- Spring offers convenient handling: when configured with a wildcard for allowed methods/headers, it can echo the method and headers requested in preflight back into the response.
- For exposed headers, Spring supports wildcards, but the CORS specification does not define wildcards the same way for credentialed responses.

For clear and auditable configuration, explicitly list the methods, request headers, and exposed response headers actually needed instead of relying on wildcards.

## 7. How Should an Allowed Origins List Be Designed?

A good allowlist accurately describes the frontends permitted to access the API.

### 7.1. Origins Are Exact Values

Example:

~~~java
.allowedOrigins(
        "https://app.example.com",
        "https://admin.example.com",
        "http://localhost:5173")
~~~

These three origins are three separate environments/applications. Variations in scheme or port are not automatically allowed.

Do not write:

- `https://app.example.com/dashboard`: origins do not include paths.
- `https://*.example.com` in allowedOrigins: this wildcard is not an exact origin.
- `https://app.example.com/`: a trailing slash is not the standard serialized origin format.
- `https://app.example.com:3000` if the frontend actually runs on another port.

### 7.2. Separate Development and Production Origins

Do not keep localhost in the production allowlist without reason. Configuration can come from environment variables or configuration properties:

~~~yaml
app:
  cors:
    allowed-origins:
      - https://app.example.com
      - https://admin.example.com
~~~

A local profile can add:

~~~yaml
app:
  cors:
    allowed-origins:
      - http://localhost:5173
      - http://localhost:3000
~~~

YAML examples must be bound into an appropriate Java configuration. Do not read origins from requests and reflect them blindly without checking an allowlist.

### 7.3. Be Careful with Origin: null

Some environments such as file URLs, sandboxed iframes, or opaque origins can send:

~~~http
Origin: null
~~~

Do not allow `null` just to make a test page work. Only add it if there is a specific use case and you understand which sources can produce an opaque origin.

### 7.4. Do Not Use Substring Checks for Origins

Do not write manually:

~~~java
if (origin.contains("example.com")) {
    // allow
}
~~~

Substring checks can accept spoofed hostnames like `example.com.attacker.test` or origins outside trusted domains.

Use `CorsConfiguration`, an exact allowlist, or tightly scoped pattern matching. Do not substitute `Referer` for `Origin`; CORS relies on the Origin request header.

## 8. Global CORS Configuration with WebFluxConfigurer

For annotated controllers, the standard approach is implementing `WebFluxConfigurer` and registering URL patterns via `CorsRegistry`.

~~~java
@Configuration
public class WebCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com")
                .allowedMethods(
                        "GET", "POST", "PUT", "PATCH", "DELETE")
                .allowedHeaders(
                        "Authorization",
                        "Content-Type",
                        "X-Request-Id",
                        "X-CSRF-TOKEN")
                .exposedHeaders(
                        "Location",
                        "ETag",
                        "X-Request-Id")
                .allowCredentials(true)
                .maxAge(3600);
    }
}
~~~

Explanation:

- `addMapping("/api/**")` limits the policy to API paths.
- `allowedOrigins` is the list of permitted frontends.
- `allowedMethods` are the methods of actual requests.
- `allowedHeaders` are the request headers the frontend may send.
- `exposedHeaders` are response headers JavaScript needs to read.
- `allowCredentials(true)` allows sharing responses for requests using credentials mode include.
- `maxAge(3600)` allows caching preflight responses up to the configured 3600 seconds, subject to browser caps.

There is no need to add OPTIONS to allowedMethods just because preflights use OPTIONS. `Access-Control-Allow-Methods` describes the actual request method queried in `Access-Control-Request-Method`. Only add OPTIONS if the API actually exposes OPTIONS as a business method.

There is no need to write custom controllers handling OPTIONS for each route once CORS is properly configured.

### 8.1. Do Not Enable @EnableWebFlux Just to Configure CORS

In Spring Boot, a `@Configuration` class implementing `WebFluxConfigurer` is sufficient for the example above. Do not add `@EnableWebFlux` unless you intentionally want to replace Boot's WebFlux auto-configuration.

### 8.2. Default Values of CorsRegistry

When using `CorsRegistry.addMapping`, Spring initializes the configuration with permit defaults. These defaults typically include:

- All origins allowed.
- All request headers allowed.
- GET, HEAD, and POST allowed.
- Credentials disabled.
- Max age of 30 minutes.

Do not rely on defaults for production APIs. Explicitly specify origins, methods, headers, and credentials according to the actual contract.

## 9. @CrossOrigin for Controller-Level Configuration

If only a single controller or method needs a custom CORS policy, `@CrossOrigin` can be used:

~~~java
@RestController
@RequestMapping("/api/reports")
@CrossOrigin(
        origins = "https://app.example.com",
        methods = {
                RequestMethod.GET,
                RequestMethod.POST
        },
        allowedHeaders = {
                "Content-Type",
                "Authorization"
        },
        exposedHeaders = "X-Request-Id",
        allowCredentials = "true",
        maxAge = 3600)
public class ReportController {
    // Endpoints
}
~~~

The annotation can be placed on a class or method. Class-level configuration applies to methods in the controller; method-level config can supplement or adjust it.

Spring allows combining global CORS and local CORS. Lists such as origins, methods, headers, and exposed headers are typically combined additively; single-valued attributes such as allowCredentials and maxAge can be overridden by local config.

This means adding a local annotation can expand the allowed origins/methods compared to global config. Review both places when investigating why a route has broader permissions than expected.

Use a consistent global policy for normal APIs; only use the annotation for exceptions with clear justification.

## 10. CorsWebFilter for Functional Endpoints

For functional routing via `RouterFunction` and `HandlerFunction`, `CorsWebFilter` can be used:

~~~java
@Configuration
public class FunctionalCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of(
                "https://app.example.com"));

        config.setAllowedMethods(List.of(
                "GET", "POST", "PUT"));

        config.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id"));

        config.setExposedHeaders(List.of(
                "Location",
                "X-Request-Id"));

        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);

        return new CorsWebFilter(source);
    }
}
~~~

`CorsWebFilter` accepts a `CorsConfigurationSource` and handles CORS at the WebFilter layer. This is a good fit when the application uses functional endpoints or needs filter-level processing.

Do not register multiple overlapping CORS layers simultaneously without deliberate intent. Having global HandlerMapping config, a CorsWebFilter, and a gateway all adding headers can produce duplicate headers or inconsistent policies.

## 11. Integrating with Spring Security WebFlux

When Spring Security is present, processing order is critical.

CORS must be handled before security authorization. OPTIONS preflights do not carry cross-origin cookies. If Spring Security runs first and requires an authenticated session, it may reject OPTIONS due to the missing session cookie. The browser then never sends the actual request.

Reactive Spring Security supports CORS via `ServerHttpSecurity.cors` and places `CorsWebFilter` at the proper position in the security chain.

Example:

~~~java
@Configuration
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of(
                "https://app.example.com",
                "https://admin.example.com"));

        config.setAllowedMethods(List.of(
                "GET", "POST", "PUT", "PATCH", "DELETE"));

        config.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id",
                "X-CSRF-TOKEN"));

        config.setExposedHeaders(List.of(
                "Location",
                "X-Request-Id"));

        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
                .cors(cors -> cors.configurationSource(corsSource))
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().permitAll())
                .build();
    }
}
~~~

Requires the `spring-boot-starter-security` dependency in addition to `spring-boot-starter-webflux`.

Key points:

- The CORS source holds the shared allowlist.
- `http.cors(...)` integrates CORS into the Spring Security filter chain.
- Security still authenticates and authorizes actual requests.
- Preflights are handled before authentication/authorization, so no session cookie is needed on OPTIONS.
- Do not register an extra standalone CorsWebFilter with the same policy if Spring Security already manages CORS for that chain.

If the application uses cookie sessions, keep CSRF protection appropriate for the authentication model. CORS does not replace CSRF tokens.

## 12. Cookies, SameSite, and Cross-Origin Credentials

Origin and site are two different concepts.

Example:

- Frontend: `https://app.example.com`
- API: `https://api.example.com`

These two URLs have different origins but are typically same-site by registrable domain. Therefore, cookie SameSite rules are not identical to CORS same-origin rules.

If frontend and API are genuinely cross-site, cookies usually require:

~~~http
Set-Cookie: SESSION=...; Path=/; Secure; HttpOnly; SameSite=None
~~~

Notes:

- `SameSite=None` requires `Secure` in modern browsers.
- `HttpOnly` prevents JavaScript from reading the cookie directly.
- Browser privacy/third-party-cookie policies can still block cookies even when CORS is correct.
- Cookie domain/path and HTTPS must match.
- The frontend must use `credentials: "include"` if it wants to send cookies cross-origin.

Example:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

If the browser does not send cookies, inspect DevTools Application/Storage and Network to see whether the cookie was dropped due to SameSite, Secure, domain, expiration, or third-party cookie policy. Do not just broaden CORS wildcards to fix cookie issues.

## 13. CORS Does Not Replace Authentication, Authorization, and CSRF

CORS mainly decides whether the browser shares a response with cross-origin JavaScript. It is not a firewall and does not protect endpoints from all HTTP clients.

Consequences:

1. curl, Postman, and backend services can send requests without CORS.
2. A simple cross-origin request can reach the server even if the browser ultimately blocks JavaScript from reading the response.
3. The server must still authenticate users and check permissions on every resource.
4. Cookie-authenticated state-changing endpoints still need appropriate CSRF protection.
5. An allowlisted origin must not be treated as a trusted user identity.

For example, an HTML form can send a simple POST from another website. If the server relies on session cookies without CSRF defense, the request can still be processed even if the attacker cannot read the response.

Therefore:

- Use Spring Security authentication.
- Use user/role/resource authorization.
- Use CSRF tokens or a CSRF strategy suited to session cookies.
- Set cookie SameSite according to your threat model.
- Restrict CORS origins to limit which websites can read responses.
- Do not allow credentialed CORS for all origins.

CORS is an additional browser policy layer, not a business authorization mechanism.

## 14. Cache, Vary, and Preflight

When a server returns `Access-Control-Allow-Origin` based on the request's origin, responses vary by Origin. Shared caches or reverse proxies must know that.

Use:

~~~http
Vary: Origin
~~~

For preflight responses, caches must also distinguish requested methods and request headers; CORS responses typically use:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Spring CORS processing manages the corresponding Vary headers. If a gateway or cache sits in front of the application, check whether that layer preserves Vary.

Do not cache responses containing user-specific data as if they were public responses. CORS does not automatically make a response safe to share through a cache.

## 15. Private Network Access

Some browsers enforce additional checks when a public website attempts to call resources on private network addresses, such as LAN devices or internal services.

Spring Framework supports configuring `allowPrivateNetwork` on `CorsConfiguration`/`CorsRegistration` in versions that provide this API.

Enable it only when the application genuinely requires browser access to a private network and has a proper threat model. Do not enable private network access together with allow-all origins. Restrict to specific origins and check the behavior/versions of browsers supporting this policy.

This is an additional policy alongside standard CORS, not a reason to open the allowlist to every website.

## 16. Runnable Spring Boot WebFlux Java 17+ Example

This example creates an API:

~~~text
GET /api/profile
PUT /api/profile
~~~

Allowed frontends:

~~~text
https://app.example.com
https://admin.example.com
~~~

The API accepts credentials mode include, permits PUT and the headers Authorization, Content-Type, X-Request-Id. Responses expose X-Request-Id and Location.

### 16.1. Project Structure

~~~text
webflux-cors-demo/
  pom.xml
  src/main/java/example/cors/CorsDemoApplication.java
  src/main/java/example/cors/WebCorsConfiguration.java
  src/main/java/example/cors/ProfileController.java
  src/test/java/example/cors/CorsIntegrationTest.java
~~~

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Spring Boot BOM manages compatible Spring Framework, Reactor, and related dependencies.

### 16.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-cors-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 16.3. Startup Class

**src/main/java/example/cors/CorsDemoApplication.java**

~~~java
package example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

### 16.4. Allowlist Configuration

**src/main/java/example/cors/WebCorsConfiguration.java**

~~~java
package example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com")
                .allowedMethods(
                        "GET", "POST", "PUT", "PATCH", "DELETE")
                .allowedHeaders(
                        "Authorization",
                        "Content-Type",
                        "X-Request-Id",
                        "X-CSRF-TOKEN")
                .exposedHeaders(
                        "Location",
                        "X-Request-Id")
                .allowCredentials(true)
                .maxAge(3600);
    }
}
~~~

### 16.5. Controller

**src/main/java/example/cors/ProfileController.java**

~~~java
package example.cors;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @GetMapping
    public Mono<ResponseEntity<Map<String, String>>> read() {
        return Mono.just(
                ResponseEntity.ok()
                        .header("X-Request-Id", "demo-123")
                        .body(Map.of(
                                "id", "user-1",
                                "displayName", "WebFlux learner")));
    }

    @PutMapping
    public Mono<Map<String, String>> update(
            @RequestBody Map<String, String> body) {

        return Mono.just(body);
    }
}
~~~

The controller does not check Origin itself. The CORS policy is applied in WebFlux infrastructure; authentication and authorization belong to the application's security layer.

### 16.6. Testing Preflight and Actual Response

**src/test/java/example/cors/CorsIntegrationTest.java**

~~~java
package example.cors;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowsConfiguredOriginMethodAndHeaders() {
        client.options()
                .uri("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header(
                        "Access-Control-Request-Headers",
                        "authorization,content-type,x-request-id")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin",
                        "https://app.example.com")
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Credentials",
                        "true")
                .expectHeader().exists(
                        "Access-Control-Allow-Methods")
                .expectHeader().exists(
                        "Access-Control-Allow-Headers")
                .expectHeader().valueEquals(
                        "Access-Control-Max-Age",
                        "3600");
    }

    @Test
    void actualResponseContainsCorsHeaders() {
        client.get()
                .uri("/api/profile")
                .header("Origin", "https://app.example.com")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin",
                        "https://app.example.com")
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Credentials",
                        "true")
                .expectHeader().exists(
                        "Access-Control-Expose-Headers")
                .expectHeader().valueEquals(
                        "X-Request-Id",
                        "demo-123");
    }

    @Test
    void rejectsOriginOutsideAllowlist() {
        client.options()
                .uri("/api/profile")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "PUT")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

These tests verify:

- OPTIONS preflight from an allowed origin.
- PUT declared in the allowlist.
- Authorization, Content-Type, and X-Request-Id accepted.
- Actual response includes CORS headers and exposed headers.
- Origins outside the allowlist are rejected.

WebTestClient checks HTTP responses. It does not simulate all browser CORS enforcement; add browser tests for cookies and third-party-cookie behavior if the app uses session credentials.

### 16.7. Running Tests

In the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

If tests pass, all three test methods complete. This is a WebFlux integration example on a Spring Boot-managed embedded server.

## 17. Sending Requests from a Browser

Example request with cookie credentials and custom headers:

~~~javascript
const response = await fetch(
  "https://api.example.com/api/profile",
  {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": "browser-123",
      "Authorization": "Bearer " + token
    },
    body: JSON.stringify({
      displayName: "Reactive learner"
    })
  }
);

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const requestId = response.headers.get("X-Request-Id");
const profile = await response.json();
~~~

The browser will preflight due to the PUT method and custom headers. Only if the preflight succeeds does the browser send the actual PUT.

`credentials: "include"` asks the browser to use cross-origin credentials if cookie/browser policies allow. The server must return a specific origin and `Access-Control-Allow-Credentials: true`. The `X-Request-Id` header is readable from JavaScript only because the server exposed it.

If only using a bearer token without needing cross-origin cookies, `credentials: "include"` can be omitted; the Authorization header still must be permitted in the preflight.

## 18. Checking Preflight with curl

Send OPTIONS to inspect response headers:

~~~bash
curl -i -X OPTIONS \
  https://api.example.com/api/profile \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
~~~

Expected response has headers similar to:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Expose-Headers: Location,X-Request-Id
Access-Control-Max-Age: 3600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Check the actual response:

~~~bash
curl -i \
  https://api.example.com/api/profile \
  -H "Origin: https://app.example.com"
~~~

`curl` does not enforce CORS like a browser. It only helps inspect whether the server returns the right headers. A successful curl command does not prove a browser will accept the request; browsers also apply Fetch/CORS, cookie, and privacy policies.

## 19. Diagnosing CORS Errors in the Browser

When the frontend reports a CORS error, inspect the Network tab in order:

1. Is there an OPTIONS preflight?
2. Does OPTIONS return status 200/204?
3. Does the sent `Origin` have the right scheme, host, and port?
4. Does `Access-Control-Allow-Origin` match the origin?
5. Does `Access-Control-Allow-Methods` contain the actual method?
6. Does `Access-Control-Allow-Headers` contain every custom request header?
7. If using credentials include, does the response have a specific ACAO and ACAC true?
8. Is the actual request sent after OPTIONS?
9. Does the actual response have matching ACAO/ACAC?
10. If JavaScript cannot read a response header, is that header listed in `Access-Control-Expose-Headers`?
11. Are cookies blocked by the browser due to SameSite, Secure, or third-party-cookie policy?
12. Is a gateway, reverse proxy, or CDN overwriting/duplicating CORS headers?

Common errors:

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| OPTIONS returns 401/403 | Security blocks preflight before CORS | Integrate CORS into Spring Security to run before authorization |
| No Access-Control-Allow-Origin | No matching config or origin disallowed | Check URL mapping and exact origin |
| Wildcard origin unusable with cookies | Credentials mode include rejects ACAO `*` | Use explicit origin list or scoped patterns |
| PUT method rejected | PUT not yet in allowedMethods | Add the actual required method |
| Authorization header rejected | Header not yet in allowedHeaders | Explicitly add Authorization |
| JSON POST fails preflight | Content-Type application/json not allowed yet | Add Content-Type to allowedHeaders |
| Actual request sent but JS cannot read response | Actual response missing CORS headers or credentials mismatch | Inspect the actual response, not only OPTIONS |
| JS cannot read X-Request-Id | Header not exposed yet | Add X-Request-Id to exposedHeaders |
| Cookie missing from request | Frontend lacks credentials include or cookie policy blocks it | Check fetch/XHR and cookie attributes |
| curl works but browser fails | curl does not enforce CORS | Check Network tab and headers received by the browser |
| Two Access-Control-Allow-Origin headers present | Gateway and app both add headers | Choose one layer to own CORS |
| Fails only on 401/500 responses | Error response from proxy/security lacks CORS headers | Apply CORS at the layer returning the error response |

## 20. Dangerous Configuration Mistakes

### 20.1. Reflecting Every Origin

Do not do:

~~~java
response.getHeaders().set(
        "Access-Control-Allow-Origin",
        request.getHeaders().getOrigin());
~~~

Without an allowlist check, any website can be echoed back as an allowed origin. Combined with credentials, this can let malicious websites read responses containing user data.

Use Spring CorsConfiguration to validate origins before reflecting them.

### 20.2. Allowing Every Origin with Credentials

Do not use:

~~~java
.allowedOrigins("*")
.allowCredentials(true)
~~~

This combination is invalid and is not a way to fix CORS errors. Declare exact origins or a scoped set of allowedOriginPatterns.

### 20.3. Opening Every Method and Header

Configuration:

~~~java
.allowedMethods("*")
.allowedHeaders("*")
~~~

may be convenient for testing environments, but widens the attack surface. Allow only methods and headers the API actually uses.

### 20.4. Using CORS as Authentication

Do not treat an allowlisted Origin as proof that a user is logged in. A non-browser HTTP client can forge Origin. Authentication and authorization must be verified independently.

### 20.5. Arbitrarily Allowing Origin: null

Do not add `null` to the allowlist just to make file:// or sandboxed iframes work. Determine the request source and threat model before permitting it.

## 21. Checklist Before Deploying CORS to Production

- [ ] Identify all frontend origins by scheme, host, and port.
- [ ] Do not include paths or trailing slashes in origins.
- [ ] Use exact allowedOrigins when there is a fixed set of frontends.
- [ ] Only use allowedOriginPatterns for scoped preview/tenant domains.
- [ ] Never use wildcard origins with credentials.
- [ ] Enable allowCredentials only when cross-origin cookies/HTTP credentials are truly needed.
- [ ] Understand that preflights do not send cookies, while actual requests can use credentials.
- [ ] List actual methods in allowedMethods.
- [ ] List required request headers in allowedHeaders.
- [ ] Expose response headers that the frontend needs to read.
- [ ] Set a reasonable maxAge and understand browsers may cap caching.
- [ ] Process CORS before Spring Security authentication/authorization.
- [ ] Do not register duplicate CORS filters/configs.
- [ ] Use appropriate Vary headers when responses vary by Origin.
- [ ] Do not treat CORS as authentication, authorization, or CSRF protection.
- [ ] Cross-site cookies have appropriate SameSite/Secure settings.
- [ ] Tests cover passing preflights, rejected origins, and actual responses.
- [ ] Browser integration tests exist if using cookie credentials.
- [ ] Verify CORS headers at gateway/CDN/proxy and on error responses.
- [ ] Do not log tokens, cookies, or sensitive information while debugging.

## 22. Self-Check

**Question 1.** What components make up an Origin?

Scheme, host, and port. Paths are not part of the origin.

**Question 2.** When does a browser send a CORS preflight?

When the request needs a preliminary check, usually due to a non-safelisted method or non-safelisted request headers.

**Question 3.** Which HTTP method does a preflight use?

OPTIONS, with Access-Control-Request-Method and optionally Access-Control-Request-Headers.

**Question 4.** Do preflights carry cross-origin cookies?

No. Preflights use credentials mode same-origin; the actual request that follows can still use credentials include.

**Question 5.** Why cannot a credentialed response use Access-Control-Allow-Origin: *?

Browsers require ACAO to match the exact request Origin when credentials mode is include.

**Question 6.** What is the valid value for Access-Control-Allow-Credentials?

The exact lowercase value `true`.

**Question 7.** How do allowedOrigins and allowedOriginPatterns differ?

allowedOrigins takes a list of specific origins or a special wildcard; allowedOriginPatterns supports patterns and Spring returns the matched actual origin.

**Question 8.** Does Authorization need to be declared in allowedHeaders?

Yes. It is a request header that must be explicitly permitted during preflight.

**Question 9.** Does allowCredentials(true) send cookies automatically?

No. Browser clients must use the right credentials mode and cookies must satisfy domain, Secure, SameSite, and browser privacy policies.

**Question 10.** When using Spring Security WebFlux, where should CORS run?

Before security authorization. Use `ServerHttpSecurity.cors` with a CorsConfigurationSource so Spring Security places CorsWebFilter in the right order.

**Question 11.** Does CORS prevent curl from calling an API?

No. CORS is a browser policy; the server must still enforce authentication, authorization, and CSRF.

**Question 12.** Why do responses need Access-Control-Expose-Headers?

So JavaScript can read response headers outside the safelisted group, such as Location or X-Request-Id.

**Question 13.** What is maxAge used for?

Tells the browser how long to cache preflight results; it does not cache API response bodies.

**Question 14.** Why is testing OPTIONS with curl alone not enough?

curl does not enforce browser CORS or cookie policies. Actual requests and real browser Network behavior must also be tested.

## 23. Official References

- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): preflight, actual requests, @CrossOrigin, global configuration, CorsWebFilter, and credentialed requests.
- [Spring Framework — CorsConfiguration JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowedOrigins, allowedOriginPatterns, allowedMethods, allowedHeaders, allowCredentials, maxAge, and allowPrivateNetwork.
- [Spring Framework — CorsRegistration JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/CorsRegistration.html): URL-based CORS configuration for WebFlux.
- [Spring Framework — CorsWebFilter JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html): reactive CORS WebFilter.
- [Spring Security — CORS for Reactive Applications](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/cors.html): CORS must be processed before Spring Security and configuring CorsConfigurationSource.
- [ServerHttpSecurity.CorsSpec JavaDoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html): configuring CORS and CorsConfigurationSource in a reactive security chain.
- [WHATWG Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#cors-protocol): preflight, credentials mode, request/response headers, wildcard restrictions, and CORS checks.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): practical explanation of browser preflight, credentials, and CORS response headers.

**Key takeaway:** Build your allowlist from actual frontend origins, configure explicit methods and headers, and enable credentials only when needed. OPTIONS preflights do not carry cookies, yet must permit the policy of the actual request; credentialed responses require ACAO matching the exact Origin and ACAC set to true. In WebFlux, you can use WebFluxConfigurer or CorsWebFilter; when integrating Spring Security, use ServerHttpSecurity.cors so CORS runs before authorization. CORS does not replace authentication, authorization, or CSRF protection.