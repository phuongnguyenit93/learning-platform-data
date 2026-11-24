# Global CORS, @CrossOrigin, and CorsWebFilter in Spring WebFlux

CORS (Cross-Origin Resource Sharing) is a mechanism that lets browsers decide whether JavaScript from one origin is allowed to read responses from a server at another origin. In Spring WebFlux, there are three common ways to configure it: declaring a global policy with WebFluxConfigurer, scoping rules to a controller with @CrossOrigin, and handling CORS at the WebFilter layer with CorsWebFilter.

These three approaches sit at different layers. Global configuration fits when many APIs share one policy; @CrossOrigin is convenient when a single controller or method needs custom rules; CorsWebFilter is useful when you want to handle CORS at the filter layer, including functional endpoints and cases where CORS must run before Spring Security.

This lesson belongs to **WebFlux Configuration**, focusing on the CORS protocol, preflight requests, choosing a configuration style, combining policies, credentials, wildcard origins, filter ordering, and testing.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the same-origin policy and the role of CORS in browsers.
- Distinguish origins by scheme, host, and port.
- Recognize simple requests and preflight OPTIONS requests.
- Read the key CORS request/response headers.
- Configure global CORS using WebFluxConfigurer.addCorsMappings().
- Use @CrossOrigin at the controller or method level.
- Configure CorsWebFilter and UrlBasedCorsConfigurationSource.
- Choose the right configuration approach for annotated controllers and functional endpoints.
- Understand how global and local configurations are combined.
- Configure credentials safely, avoiding invalid wildcard origins.
- Distinguish allowedHeaders from exposedHeaders.
- Understand maxAge, Vary: Origin, and caching effects.
- Place CORS at the right position when using reactive Spring Security.
- Test preflight and actual requests with WebTestClient.

## 2. Same-Origin Policy and CORS

Browsers enforce the same-origin policy to restrict JavaScript from reading data from another origin. An origin is defined by three parts:

- Scheme: http or https.
- Host: domain name or server address.
- Port: connection port.

Examples:

| URL | Compared to https://app.example.com | Same Origin? |
| --- | --- | --- |
| https://app.example.com/orders | Same scheme, host, port | Yes |
| https://app.example.com:443/profile | Default HTTPS port | Yes |
| http://app.example.com/orders | Different scheme | No |
| https://api.example.com/orders | Different host | No |
| https://app.example.com:8443/orders | Different port | No |

CORS lets the server declare which origins may read responses, which methods may be used, which request headers may be sent, and which response headers JavaScript is allowed to inspect.

For example, a frontend running at https://app.example.com calls an API at https://api.example.com. This is a cross-origin request. The API must return appropriate CORS response headers so the browser allows the frontend to read the result.

### CORS Is Not an Authentication Mechanism

CORS is a policy enforced by browsers. It does not replace authentication, authorization, or CSRF protection.

- HTTP clients such as curl, Postman, or service-to-service clients do not apply the browser's same-origin policy.
- CORS does not stop an external program from sending requests to the server.
- CORS mainly decides whether the browser allows JavaScript to read the response.
- The server must still authenticate users and check authorization on every API.
- With cookie/session authentication, CSRF must still be evaluated under the application's security model.

Do not use CORS as a way to protect sensitive data. If an API does not require login, CORS does not make that API private.

## 3. Simple Requests and Preflight Requests

Browsers can send certain cross-origin requests directly. For requests outside the simple category, browsers usually send a preliminary check request called a **preflight**.

### Simple Request

Some requests do not require a preflight, such as a simple GET or POST with a Content-Type that CORS considers safelisted, provided the method and request headers meet the specification's criteria.

The actual request might contain:

~~~http
GET /api/products HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Accept: application/json
~~~

The server's response may include:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json
~~~

The browser checks Access-Control-Allow-Origin. If the origin is allowed, JavaScript can read the response.

### Preflight Request

Requests such as PUT, DELETE, or requests with custom headers like Authorization usually require a preflight. The browser sends OPTIONS before the actual request:

~~~http
OPTIONS /api/products/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

The server must respond with the corresponding policy:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

If the preflight succeeds, the browser proceeds to send the actual request. If the preflight fails, the browser typically does not send the actual request.

Not every OPTIONS request is a CORS preflight. A preflight has Origin and Access-Control-Request-Method; an ordinary OPTIONS request can be a business request or a request sent by another tool.

## 4. Key CORS Headers

| Header | Direction | Meaning |
| --- | --- | --- |
| Origin | Request | Origin of the web page initiating the request |
| Access-Control-Request-Method | Preflight request | Method the browser intends to send |
| Access-Control-Request-Headers | Preflight request | Request headers the browser intends to send |
| Access-Control-Allow-Origin | Response | Origin allowed to read the response, or * where appropriate |
| Access-Control-Allow-Methods | Response | Allowed HTTP methods |
| Access-Control-Allow-Headers | Response | Allowed request headers |
| Access-Control-Allow-Credentials | Response | Allows requests using browser credentials |
| Access-Control-Expose-Headers | Response | Response headers readable by JavaScript |
| Access-Control-Max-Age | Preflight response | Time the browser may cache the preflight result |
| Vary | Response | Indicates request headers that affect the response/cache variant |

### allowedHeaders and exposedHeaders Are Different

These two settings are often confused:

- **allowedHeaders:** request headers the browser is allowed to send, such as Authorization, Content-Type, X-Request-Id.
- **exposedHeaders:** response headers JavaScript is allowed to read, such as X-Request-Id or ETag.

For example, the server may return X-Request-Id, but JavaScript cannot read that header unless it is listed in exposed headers (aside from default safelisted response headers).

### allowCredentials

When the browser needs to send cookies or credentials according to credentials mode, the server must allow credentials with:

~~~http
Access-Control-Allow-Credentials: true
~~~

In Spring, the corresponding setting is allowCredentials(true).

If credentials are allowed, do not use allowedOrigins("*"). CORS does not allow a response to combine a wildcard origin with Access-Control-Allow-Credentials: true. Specify explicit origins or use allowedOriginPatterns with a controlled list of patterns. When using patterns, Spring echoes back the matched actual origin instead of sending the wildcard character.

### maxAge

maxAge specifies how long the browser may cache the preflight result, in seconds. A large value reduces the number of OPTIONS requests, but also means policy changes may not take effect for cached results until they expire.

maxAge is not the cache expiration for regular API responses.

## 5. Configuring Global CORS with WebFluxConfigurer

For annotated controllers, the common approach is creating a class that implements WebFluxConfigurer and overrides addCorsMappings().

~~~java
package com.example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class GlobalCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Content-Type",
                "Authorization",
                "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Explanation:

- addMapping("/api/**") applies the policy to URLs matching the path pattern.
- allowedOrigins() lists specific allowed origins.
- allowedMethods() restricts methods.
- allowedHeaders() restricts request headers.
- exposedHeaders() exposes response headers to JavaScript.
- allowCredentials(true) allows the browser to send credentials under the CORS policy.
- maxAge(3600) lets the browser cache preflight responses for up to one hour.

Global configuration fits when multiple controllers share a policy. Multiple mappings can be declared for different URL groups, such as /api/public/** and /api/admin/**.

### Example with Multiple Endpoint Groups

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/public/**")
        .allowedOrigins("https://www.example.com")
        .allowedMethods("GET")
        .allowedHeaders("Accept")
        .maxAge(1800);

    registry.addMapping("/api/admin/**")
        .allowedOrigins("https://admin.example.com")
        .allowedMethods("GET", "POST", "PUT", "DELETE")
        .allowedHeaders("Authorization", "Content-Type")
        .allowCredentials(true)
        .maxAge(300);
}
~~~

Separating mappings keeps policies clear per API area. Do not open all of /api/** if only one frontend group needs access.

## 6. Using @CrossOrigin at the Controller or Method Level

@CrossOrigin is an annotation declaring CORS on a controller or handler method.

### Controller-Level Configuration

~~~java
@RestController
@RequestMapping("/reports")
@CrossOrigin(
    origins = "https://dashboard.example.com",
    allowedHeaders = {"Authorization", "Content-Type"},
    methods = {RequestMethod.GET, RequestMethod.POST},
    maxAge = 1800)
public class ReportController {

    @GetMapping
    public List<String> reports() {
        return List.of("daily", "monthly");
    }
}
~~~

Handlers in the controller apply this annotation policy unless a method has local configuration that supplements or overrides it according to Spring's combination rules.

### Method-Level Configuration

~~~java
@RestController
@RequestMapping("/documents")
public class DocumentController {

    @GetMapping("/{id}")
    @CrossOrigin(
        origins = "https://reader.example.com",
        methods = RequestMethod.GET)
    public Map<String, String> find(@PathVariable String id) {
        return Map.of("id", id, "name", "guide.pdf");
    }

    @PostMapping
    @CrossOrigin(
        origins = "https://editor.example.com",
        methods = RequestMethod.POST,
        allowedHeaders = {"Content-Type", "Authorization"})
    public Map<String, String> create() {
        return Map.of("status", "created");
    }
}
~~~

Method-level annotations are useful when individual endpoints require different origins or methods.

### Defaults to Watch Out For

When attributes are omitted, @CrossOrigin has fairly broad defaults: all origins, all request headers, and the methods supported by the handler; maxAge defaults to 1800 seconds. Explicitly declare origins and required permissions instead of relying on defaults in production applications.

In particular, do not add an empty @CrossOrigin to a controller just to “enable CORS” if the global policy restricts origins. A broad local configuration can alter the combined result and widen permissions unexpectedly.

## 7. Combining Global Configuration and @CrossOrigin

Spring allows combining global CORS configuration with local configuration on controllers/methods. Lists such as origins, methods, allowed headers, and exposed headers can be combined; certain single-valued attributes such as allowCredentials and maxAge prioritize the local value when set.

Therefore, do not assume a local annotation always narrows the global configuration. A broad local origin list, especially a wildcard, can expand the effective policy.

Example:

- Global allows only https://app.example.com.
- A method has @CrossOrigin(origins = "https://admin.example.com").
- The effective configuration may allow both origins under Spring's combination behavior.

Treat the effective policy as the result of both sources. If a strict policy is required, explicitly declare origins in both global and local configs, then test with requests carrying the corresponding Origin.

Do not configure credentials together with wildcard origins. If global and local combine to a wildcard while credentials are enabled, the configuration may be rejected or fail to produce valid CORS responses.

## 8. allowedOrigins and allowedOriginPatterns

Spring provides two ways to declare origins:

- allowedOrigins: a list of exact origins.
- allowedOriginPatterns: a list of patterns to match origins.

Exact origin example:

~~~java
.allowedOrigins(
    "https://app.example.com",
    "https://admin.example.com")
~~~

Pattern example:

~~~java
.allowedOriginPatterns(
    "https://*.example.com",
    "https://preview-*.example.net")
~~~

Patterns are useful when there are multiple controlled subdomains, such as tenants or preview environments. With allowedOriginPatterns, Spring checks the actual origin and returns the matched origin in Access-Control-Allow-Origin. This can be used together with allowCredentials(true), though patterns must still be restricted to trusted domains.

Avoid broad patterns like * in systems using credentials. Do not blindly reflect any Origin sent by the client. Origin is caller-supplied data; it must be checked against an allowlist or controlled patterns.

## 9. What Is CorsWebFilter?

CorsWebFilter is a Spring WebFlux WebFilter that handles CORS at the reactive filter layer. It accepts a CorsConfigurationSource to look up policies by request path.

CorsWebFilter is especially useful when:

- You want to process CORS at the filter layer before other filters.
- You use functional endpoints with RouterFunction.
- You want to centralize CORS policy in a single bean.
- You need CORS to run before Spring Security so preflights do not require authentication.

Configuration example:

~~~java
package com.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class FilterCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
            List.of("https://app.example.com"));
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(
            List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);

        return new CorsWebFilter(source);
    }
}
~~~

In the example, the source registers the policy for /api/**. CorsWebFilter reads Origin and preflight headers, finds the matching configuration, and handles CORS before the request proceeds deeper into the filter chain.

### Should CorsWebFilter and WebFluxConfigurer Be Enabled Together?

Normally, choose one primary approach for the same path:

- WebFluxConfigurer.addCorsMappings() for CORS attached to WebFlux handler mappings.
- CorsWebFilter for handling CORS at the filter layer.

Do not register two different policies for the same path without clearly understanding their ordering and interaction. Duplicate configurations can produce unpredictable response headers or make debugging preflights difficult.

If using Spring Security, choose the CORS integration managed by Security or ensure the CORS filter runs before Security. Do not stack multiple CORS filters just to try to fix preflight errors.

## 10. CORS with Functional Endpoints

Functional endpoints use RouterFunction and HandlerFunction instead of annotated controllers:

~~~java
@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route(
            RequestPredicates.GET("/functional/status"),
            request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("status", "ok")));
    }
}
~~~

Functional routes do not have methods on which to place @CrossOrigin like annotated controllers. When CORS is needed for these routes, CorsWebFilter is the clear choice because it applies by request path at the filter layer.

For example, register /functional/** in UrlBasedCorsConfigurationSource:

~~~java
source.registerCorsConfiguration("/functional/**", functionalCorsConfig);
~~~

You can use the same CorsWebFilter to register multiple path patterns, each with its own CorsConfiguration. Policies should align with any annotated endpoints if they serve the same frontend.

## 11. CORS and Spring Security WebFlux

CORS must be processed before Spring Security's authorization step. A preflight request usually does not carry session cookies or credentials like an actual request. If Security blocks OPTIONS before CORS handles it, the browser reports a preflight failure and does not send the actual request.

With reactive Spring Security, you can provide a CorsConfigurationSource and enable CORS in ServerHttpSecurity:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(
        List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));
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
        CorsConfigurationSource corsConfigurationSource) {

    return http
        .cors(cors ->
            cors.configurationSource(corsConfigurationSource))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This snippet requires the spring-boot-starter-security dependency and corresponding Spring Security imports. If the application already uses a standalone CorsWebFilter, avoid registering a second CORS policy inside Security unintentionally. Choose one clear configuration and verify CORS runs before authorization.

Permitting OPTIONS in authorization rules clarifies intent for preflights, but does not replace CORS configuration. The server must still validate the requested Origin, method, and headers.

CORS also does not exempt actual requests from authentication. Actual GET/POST requests still go through authentication and authorization according to application policy.

## 12. Credentials, Cookies, and the Authorization Header

If the frontend uses session cookies or credentials mode, configuration must be synchronized between browser and server.

Frontend example:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

The server must return a specific origin and:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

It must not return:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

The browser will reject this response according to CORS rules.

If the frontend sends an Authorization header, the preflight must permit that header in Access-Control-Allow-Headers. allowCredentials and permitting the Authorization header are two related request settings but are not identical: Authorization is a request header that must be allowed; allowCredentials controls browser credentials mode.

With cross-site cookies, also consider cookie attributes such as SameSite and Secure. Valid CORS alone does not guarantee the browser will send cookies if cookie policy forbids it.

## 13. Vary: Origin and Caching

When a server returns different responses depending on Origin, caches must know the response depends on the Origin header. Vary: Origin helps caches distinguish response variants by origin.

For preflights, responses also depend on the requested method and headers; therefore responses can contain:

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Spring's CORS processor manages the appropriate Vary headers during processing. If writing custom filters/proxies to add CORS headers, preserve Vary properly to avoid caching one origin's response and mistakenly serving it to another origin.

Do not configure a CDN to cache CORS responses by URL alone if response headers vary by Origin while the cache key ignores Origin.

## 14. How to Diagnose CORS Errors

CORS errors usually appear in the browser console, but the cause may lie in the server, proxy, authentication, or cache.

Diagnostic steps:

1. Open DevTools Network and locate the OPTIONS request.
2. Check the Origin of the frontend page.
3. Check Access-Control-Request-Method.
4. Check Access-Control-Request-Headers.
5. Inspect the preflight status and response headers.
6. Compare Access-Control-Allow-Origin against the actual origin.
7. Check allowed methods and headers.
8. If using credentials, confirm allow-credentials is true and allow-origin is not *.
9. Check whether OPTIONS is blocked by Spring Security, a gateway, or a reverse proxy.
10. Check redirects: preflights and cross-origin redirects may not be handled by browsers as expected.
11. Check Vary and caching if only certain users/origins fail.
12. Inspect the actual response using curl, keeping in mind curl does not enforce the browser's same-origin policy.

### Example Checking Preflight with curl

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/products" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

This command lets you observe response headers. It does not prove a browser will allow JavaScript to read the response; verify browser policies and real requests.

### Common Symptoms

- **No Access-Control-Allow-Origin:** server does not apply CORS config to the path/origin, or a proxy stripped the header.
- **Origin mismatch:** different scheme, host, or port; check the port too.
- **Method not allowed:** Access-Control-Request-Method is not in allowedMethods.
- **Header not allowed:** a request header is not in allowedHeaders.
- **Invalid credentials:** wildcard origin used together with credentials.
- **Preflight receives 401/403:** Security or a gateway blocks OPTIONS before CORS.
- **JavaScript cannot read a custom response header:** missing from exposedHeaders.
- **Fails only after deploy:** proxy/cache or production origin differs from local origin.

## 15. Complete Java 17+ Example with Spring Boot WebFlux

This example uses global configuration via WebFluxConfigurer and a dedicated endpoint using @CrossOrigin. CorsWebFilter was presented as an alternative; do not register that filter simultaneously in the same sample app.

### Project Structure

~~~text
webflux-cors-demo/
├── pom.xml
└── src
    ├── main/java/com/example/cors
    │   ├── CorsDemoApplication.java
    │   ├── GlobalCorsConfiguration.java
    │   └── CorsController.java
    └── test/java/com/example/cors
        └── CorsControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-cors-demo</artifactId>
  <version>1.0.0</version>

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

### CorsDemoApplication.java

~~~java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

### GlobalCorsConfiguration.java

~~~java
package com.example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class GlobalCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Content-Type",
                "Authorization",
                "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

### CorsController.java

~~~java
package com.example.cors;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CorsController {

    @GetMapping("/api/products")
    public List<Map<String, String>> products() {
        return List.of(
            Map.of("id", "p-1", "name", "Keyboard"),
            Map.of("id", "p-2", "name", "Mouse"));
    }

    @GetMapping("/api/products/{id}")
    public Map<String, String> product(@PathVariable String id) {
        return Map.of("id", id, "name", "Example product");
    }

    @GetMapping("/annotated/info")
    @CrossOrigin(
        origins = "https://admin.example.com",
        methods = RequestMethod.GET,
        allowedHeaders = {"Authorization"})
    public Map<String, String> annotatedInfo() {
        return Map.of("scope", "method-level CORS");
    }
}
~~~

The /api/** endpoints use the global policy. The /annotated/info endpoint uses its own @CrossOrigin and illustrates method-level configuration.

### CorsControllerTests.java

~~~java
package com.example.cors;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(CorsController.class)
@Import(GlobalCorsConfiguration.class)
class CorsControllerTests {

    @Autowired
    private WebTestClient client;

    @Test
    void allowsConfiguredOriginOnActualRequest() {
        client.get()
            .uri("/api/products")
            .header("Origin", "https://app.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com")
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Credentials",
                "true")
            .expectHeader()
            .exists("Access-Control-Expose-Headers");
    }

    @Test
    void acceptsPreflightForAllowedMethodAndHeaders() {
        client.options()
            .uri("/api/products")
            .header("Origin", "https://app.example.com")
            .header(
                "Access-Control-Request-Method",
                "POST")
            .header(
                "Access-Control-Request-Headers",
                "authorization,content-type,x-request-id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com")
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Credentials",
                "true")
            .expectHeader()
            .exists("Access-Control-Allow-Methods")
            .expectHeader()
            .exists("Access-Control-Allow-Headers");
    }

    @Test
    void rejectsPreflightFromUnknownOrigin() {
        client.options()
            .uri("/api/products")
            .header("Origin", "https://untrusted.example.org")
            .header(
                "Access-Control-Request-Method",
                "GET")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void appliesMethodLevelCrossOrigin() {
        client.get()
            .uri("/annotated/info")
            .header("Origin", "https://admin.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://admin.example.com");
    }
}
~~~

The tests verify CORS response headers for an actual request, preflight, a disallowed origin, and method-level annotation. WebTestClient verifies server behavior; it does not replace real browser testing because browsers also enforce same-origin and cookie policies.

Run tests:

~~~bash
mvn -q test
~~~

If all four tests pass, Maven exits with exit code 0.

Run the application:

~~~bash
mvn spring-boot:run
~~~

Test actual request:

~~~bash
curl -i "http://localhost:8080/api/products" \
  -H "Origin: https://app.example.com"
~~~

Test preflight:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/products" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

## 16. Common Pitfalls and Fixes

1. **Confusing origin with domain.** Origin includes scheme, host, and port. Compare the full origin URL.
2. **Thinking CORS is authentication.** CORS is only a browser response-reading policy; the server must still authenticate and authorize.
3. **Configuring allowedOrigins but forgetting methods.** Preflights can fail if the requested method is not permitted.
4. **Forgetting Authorization in allowedHeaders.** The browser sends a preflight and the server rejects the custom header.
5. **Using allowedHeaders as exposedHeaders.** One is for request headers; the other is for response headers JavaScript may read.
6. **Using wildcard origins with credentials.** This configuration is invalid; use explicit origins or controlled patterns.
7. **Reflecting every request Origin.** That is equivalent to allowing every website; validate against an allowlist.
8. **Leaving @CrossOrigin with broad defaults.** Explicitly declare origins, methods, and headers for endpoints.
9. **Assuming a method-level annotation always narrows the global config.** Local and global configurations are combined; a local list can widen permissions.
10. **Registering both CorsWebFilter and WebFluxConfigurer for the same path unintentionally.** Can create duplicate policies or confusing response headers.
11. **Letting Spring Security block OPTIONS.** CORS needs to be processed before authorization; integrate CORS in reactive Security.
12. **Thinking permitAll on OPTIONS is enough.** Preflights also need CORS response headers with matching origin, methods, and headers.
13. **Forgetting exposedHeaders.** The browser receives the response header, but JavaScript cannot read custom headers.
14. **Setting maxAge too long when policies change frequently.** Browsers may keep using stale cached preflight results.
15. **Forgetting Vary: Origin.** Caches may serve one origin's response to another origin.
16. **Testing with curl and concluding browsers will work.** curl does not enforce CORS; test in a browser.
17. **Testing only actual GET requests and skipping preflights.** PUT, DELETE, or custom headers can fail before the actual request is sent.
18. **Treating every OPTIONS request as a preflight.** Preflights must include Origin and Access-Control-Request-Method.
19. **Using CORS to protect an API from another server.** Server-to-server clients are not governed by browser same-origin policy.
20. **Ignoring cookie SameSite/Secure attributes.** Valid CORS alone is not enough for browsers to send cross-site cookies.

## 17. CORS Deployment Checklist

Before releasing a WebFlux API, check:

- **Origin inventory:** which origins are used by production, staging, and local dev frontends?
- **Path scope:** which paths does CORS apply to?
- **Allowed origins:** is an explicit allowlist used?
- **Methods:** are only necessary methods permitted?
- **Request headers:** are Authorization, Content-Type, and custom headers declared?
- **Exposed headers:** which headers does JavaScript need to read?
- **Credentials:** are cookies/credentials truly required?
- **Wildcard:** are wildcard origins never combined with credentials?
- **Preflight:** is OPTIONS handled before authentication/authorization?
- **Configuration style:** WebFluxConfigurer, @CrossOrigin, or CorsWebFilter?
- **Combination:** do global/local policies unintentionally widen origins?
- **Functional routes:** if using RouterFunction, does the filter-level policy cover them?
- **Cache:** are Vary and maxAge appropriate?
- **Security:** are authentication, authorization, and CSRF configured separately?
- **Testing:** are actual requests, preflights, denied origins, and credentials tested?
- **Browser:** has DevTools been checked on the real production origin?

## 18. Self-Check Exercises

**Exercise 1.** Do two URLs with the same host but different schemes have the same origin?  
**Answer:** No. Origin includes scheme, host, and port.

**Exercise 2.** Which HTTP method does a preflight request typically use?  
**Answer:** OPTIONS.

**Exercise 3.** What does Access-Control-Request-Method indicate?  
**Answer:** The method the browser intends to use for the actual request.

**Exercise 4.** How do allowedHeaders and exposedHeaders differ?  
**Answer:** allowedHeaders permits request headers to be sent; exposedHeaders permits JavaScript to read response headers.

**Exercise 5.** Why should allowedOrigins("*") not be used with allowCredentials(true)?  
**Answer:** CORS forbids combining a wildcard Access-Control-Allow-Origin with Access-Control-Allow-Credentials: true.

**Exercise 6.** What is WebFluxConfigurer.addCorsMappings() used for?  
**Answer:** Declaring global CORS policies by URL mapping.

**Exercise 7.** Where can @CrossOrigin be placed?  
**Answer:** At the controller class level or handler method level.

**Exercise 8.** At which layer does CorsWebFilter handle CORS?  
**Answer:** Reactive WebFilter layer, before downstream handlers/filters in the chain.

**Exercise 9.** Why does CORS need to run before Spring Security?  
**Answer:** Preflights usually do not carry cookies/sessions; if Security blocks first, the browser does not receive a valid CORS response.

**Exercise 10.** What does maxAge mean?  
**Answer:** How long the browser may cache the preflight result, in seconds.

**Exercise 11.** What does Vary: Origin help with?  
**Answer:** Tells caches that responses depend on Origin to avoid serving cached responses to the wrong origin.

**Exercise 12.** Does a successful curl request prove browsers will have no CORS errors?  
**Answer:** No. curl does not enforce the same-origin policy; test with real preflights and a browser.

## 19. Key Takeaways

CORS is a browser mechanism controlling whether JavaScript can read cross-origin responses. An origin consists of scheme, host, and port. Preflights use OPTIONS with Origin, Access-Control-Request-Method, and optionally Access-Control-Request-Headers. The server must return the proper Access-Control-Allow-Origin, Methods, Headers, and Credentials if needed.

In WebFlux, WebFluxConfigurer.addCorsMappings() configures global policy; @CrossOrigin configures at controller or method level; CorsWebFilter handles CORS at the filter layer and fits functional routes or running before Spring Security. Choose one primary configuration style per path and avoid duplicate policies.

Credentials cannot be combined with wildcard origins. allowedHeaders controls request headers; exposedHeaders controls response headers readable by JavaScript. maxAge caches preflight results; Vary: Origin helps caches distinguish responses by origin. Finally, CORS does not replace authentication, authorization, or CSRF protection. Test actual requests, preflights, and production browsers.

### References

- Spring Framework, [CORS in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html).
- Spring Framework, [WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework Javadoc, [CrossOrigin](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/CrossOrigin.html).
- Spring Framework Javadoc, [CorsWebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html).
- Spring Framework Javadoc, [CorsConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html).
- Spring Security, [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- MDN, [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS).
