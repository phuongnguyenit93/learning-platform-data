# Relationship Between Exporter-Specific CORS Configuration and Spring MVC in Spring Data REST

## Goal

An application may simultaneously expose two groups of endpoints:

- **Spring Data REST resources:** collection, item, search, and association endpoints exported from repositories.
- **Spring MVC endpoints:** controllers written by the application itself, such as reports, uploads, dashboards, or business APIs.

Both run within a Spring MVC application, yet their CORS configurations do not share a single registry by default.

The most important point in the Spring Data REST documentation is: **CORS configured for Spring MVC is not automatically applied to Spring Data REST.** If an application uses both the repository exporter and custom controllers, you need to clearly identify which group each endpoint belongs to and configure CORS accordingly.

This article explains the difference between the two mechanisms, how to configure each side, how to coordinate with `@CrossOrigin` and Spring Security, and how to test preflight requests to avoid errors when a browser calls the API from another origin.

## 1. What Problem Does CORS Solve?

CORS (Cross-Origin Resource Sharing) is the mechanism by which a server declares which origins are allowed to read responses from a browser. An origin consists of three components:

- Scheme, for example `https`.
- Host, for example `app.example.com`.
- Port, for example `443` or `8080`.

Two URLs with the same host but different schemes or ports are still two different origins. For example:

~~~text
Frontend: https://app.example.com
Backend:  https://api.example.com
~~~

The browser treats this as a cross-origin request. If the frontend uses JavaScript to call the backend, the server must return appropriate CORS response headers for the browser to let scripts read the response.

Example headers:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
~~~

CORS is a policy enforced by the browser. It is not a server authentication or authorization mechanism. A client that does not run in a browser, such as curl, Postman, or another backend service, is not bound by the browser's Same-Origin Policy.

Therefore, configuring CORS properly does not replace Spring Security, authorization, or per-resource permission checks.

## 2. Two Endpoint Groups in the Same Application

Suppose the application has:

~~~text
Spring Data REST:
  /api/people
  /api/people/42
  /api/people/search
  /api/people/42/address

Spring MVC:
  /mvc-api/reports
  /mvc-api/imports
  /mvc-api/dashboard
~~~

Spring Data REST uses the repository exporter and its own HandlerMappings to create REST resources. Spring MVC handles controllers declared with `@RestController`, `@Controller`, or corresponding controller mappings.

Therefore, you should not assume that configuring a single `WebMvcConfigurer.addCorsMappings("/**")` automatically covers all endpoints in Spring Data REST.

The Spring Data REST documentation explicitly states that existing Spring Web MVC CORS configuration is not applied to Spring Data REST. Spring Data REST provides its own registry through the `RepositoryRestConfigurer.configureRepositoryRestConfiguration(config, cors)` callback.

## 3. Configuring CORS Specifically for the Spring Data REST Exporter

The global way to configure CORS for repository resources is to implement `RepositoryRestConfigurer` and use the `CorsRegistry` parameter passed in by the framework:

~~~java
@Component
public class DataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "If-Match",
                "If-None-Match")
            .exposedHeaders("ETag", "Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Main imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
~~~

The example restricts CORS to resources whose path starts with `/people/`:

- `allowedOrigins`: the frontend origins allowed to make calls.
- `allowedMethods`: the HTTP methods the browser is allowed to execute.
- `allowedHeaders`: the request headers the frontend is allowed to send.
- `exposedHeaders`: the response headers JavaScript is allowed to read.
- `allowCredentials`: whether credentials such as cookies or HTTP authentication attached to browser requests are allowed.
- `maxAge`: how long the browser can cache the preflight result, in seconds.

If the application sets a Spring Data REST base path, such as `/api`, verify that the mapping pattern matches the path the handler actually receives in the application. Use integration tests against the deployed URL to confirm the mapping rather than guessing from the repository name.

The Spring Data REST documentation uses `cors.addMapping("/person/**")` as an example in this callback. This is a registry dedicated to the exporter, not the registry obtained from `WebMvcConfigurer`.

## 4. Configuring CORS for Spring MVC Controllers

For application-authored controllers, configure globally via `WebMvcConfigurer.addCorsMappings`:

~~~java
@Configuration
public class MvcCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/mvc-api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id")
            .exposedHeaders("Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Main imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

This configuration applies to handlers managed by Spring MVC that match the `/mvc-api/**` path pattern.

You can use `@CrossOrigin` on a controller or method when only a single endpoint needs its own policy:

~~~java
@RestController
@RequestMapping("/mvc-api/reports")
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {RequestMethod.GET},
    maxAge = 3600
)
public class ReportController {

    @GetMapping
    public ReportSummary getReport() {
        return new ReportSummary();
    }
}
~~~

Class-level `@CrossOrigin` applies to the controller's methods; method-level annotation allows finer-grained configuration for a specific endpoint.

This is Spring MVC configuration. It does not replace the Spring Data REST exporter's own CORS registry.

## 5. Comparing the Two Registries

| Item | Spring Data REST exporter | Spring MVC |
| --- | --- | --- |
| Global extension point | `RepositoryRestConfigurer` | `WebMvcConfigurer` |
| Callback | `configureRepositoryRestConfiguration(config, cors)` | `addCorsMappings(registry)` |
| Registry | `CorsRegistry` passed by Spring Data REST | `CorsRegistry` of Spring MVC |
| Primary endpoints | Repository collection, item, search, association | Custom-written controllers |
| Endpoint-level annotation | `@CrossOrigin` on repository | `@CrossOrigin` on controller/method |
| Automatically uses the other's config? | Does not automatically pick up existing MVC config | Does not use the Spring Data REST registry as MVC config |

Both configurers can be registered in the same ApplicationContext. Example:

~~~text
ApplicationContext
    |
    +-- DataRestCorsConfiguration
    |       |
    |       +-- RepositoryRestConfigurer
    |               |
    |               +-- /api/people/**
    |               +-- /api/orders/**
    |
    +-- MvcCorsConfiguration
            |
            +-- WebMvcConfigurer
                    |
                    +-- /mvc-api/**
                    +-- /admin-api/**
~~~

Both configurations can use the same origins and header lists, but they must be declared at the proper extension points. If you only add a mapping in Spring MVC without configuring Spring Data REST, the browser may be able to call custom controllers while still hitting CORS errors when calling repository resources.

## 6. Per-Repository CORS Configuration with @CrossOrigin

In addition to the global registry, Spring Data REST supports `@CrossOrigin` on repository interfaces. This annotation applies to the entire repository:

~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.DELETE
    },
    maxAge = 3600
)
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

This approach fits when a repository has a different policy from the remaining repositories. For example:

- People allows only the internal frontend to read and create.
- PublicCatalog allows only GET from the public website.
- InternalAudit does not open CORS to browser frontends.

According to the Spring Data REST documentation, `@CrossOrigin` allows all origins and HTTP methods by default. Therefore, do not put an empty annotation on a repository holding sensitive data in production unless intended.

When using `@CrossOrigin` and the global CORS registry simultaneously, Spring Data REST supports combining global configuration with fine-grained configuration. Verify the actual result of the combined values; do not assume two policies intersect under a "stricter configuration wins" rule.

## 7. @RepositoryRestController and Custom Controllers Alongside Repositories

Spring Data REST supports Spring MVC CORS on custom controllers annotated with `@RepositoryRestController`:

~~~java
@RepositoryRestController
public class PersonCustomController {

    @CrossOrigin(
        origins = "https://app.example.com",
        maxAge = 3600
    )
    @RequestMapping(
        path = "/people/export",
        method = RequestMethod.GET,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ExportResult exportPeople() {
        return new ExportResult();
    }
}
~~~

An important detail in the Spring Data REST documentation: controllers annotated with `@RepositoryRestController` can inherit `@CrossOrigin` configuration from the associated repository.

This is helpful when a custom endpoint shares a base path and policy with a repository resource. However, a regular `@RestController` does not automatically inherit a CORS policy from a repository simply because it calls the same service or accesses the same entity.

Distinction:

- `@RepositoryRestController`: custom controller integrated with Spring Data REST, capable of inheriting CORS configuration from the associated repository.
- `@RestController`: regular Spring MVC controller, using MVC CORS mappings or its own `@CrossOrigin`.
- Repository interface: `@CrossOrigin` policy applied to REST resources generated by the repository exporter.

## 8. Which Configurations Combine with One Another?

In Spring MVC, global CORS mappings can combine with local `@CrossOrigin` on a controller/method. Spring's combination rules typically merge lists such as origins, methods, and headers. For single-valued attributes like `allowCredentials` or `maxAge`, local configuration may override global configuration.

Spring Data REST also allows combining the exporter's global registry with fine-grained `@CrossOrigin` configuration. However, the two global registries of Spring MVC and Spring Data REST remain two independent configuration points.

For example:

~~~java
// Global Spring Data REST configuration
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST")
    .maxAge(1800);
~~~

~~~java
// Fine-grained configuration on a repository
@CrossOrigin(
    origins = "https://admin.example.com",
    methods = {RequestMethod.GET, RequestMethod.DELETE}
)
public interface AdminRepository
        extends JpaRepository<AdminRecord, Long> {
}
~~~

When multiple configurations overlap, inspect the final response headers for each route. Do not use a broad annotation that inadvertently opens additional origins or methods that the global policy intended to restrict.

In particular, if enabling credentials, do not use the wildcard origin `*` with `allowCredentials(true)`. Declare specific origins or use `allowedOriginPatterns` with controlled patterns.

## 9. Spring Security and CORS Processing Order

If the application uses Spring Security, CORS must be handled before the authentication step. Browser preflight requests typically do not send session cookies like `JSESSIONID`. If Spring Security requires authentication before CORS is processed, the OPTIONS request may be rejected before the browser receives the required CORS response.

Spring Security supports CORS in the filter chain:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/**", "/mvc-api/**")
                    .authenticated()
                .anyRequest().denyAll()
            );

        return http.build();
    }
}
~~~

Spring Security can use a `CorsConfigurationSource` to configure CORS at the filter layer. Example:

~~~java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {

    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(
            List.of("https://app.example.com"));
    configuration.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    configuration.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "If-Match"));
    configuration.setAllowCredentials(true);
    configuration.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", configuration);
    source.registerCorsConfiguration("/mvc-api/**", configuration);

    return source;
}
~~~

When a `UrlBasedCorsConfigurationSource` bean exists, Spring Security can use this source for `http.cors()`. This is a filter-chain processing layer, distinct from the two registries declared via `RepositoryRestConfigurer` and `WebMvcConfigurer`.

Spring Security can also use Spring MVC's CORS configuration if Spring MVC is present and no separate `CorsConfigurationSource` exists. Do not infer from this that Spring Security automatically uses Spring Data REST's separate registry. If configuring filter-level CORS, ensure the source covers both exporter routes and necessary custom MVC routes, then test across the entire filter chain.

Avoid letting multiple CORS layers simultaneously add conflicting headers. Identify which layer handles preflight and verify the actual response to ensure only a consistent policy is present.

## 10. Preflight Requests and Required Headers

Browsers typically send an OPTIONS preflight before the actual request when the request uses methods or headers outside the simple group.

For example, the frontend wants to send PATCH with Authorization and Content-Type:

~~~http
OPTIONS /api/people/42
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
~~~

The server needs to verify:

- Is Origin in the allowed origins?
- Is PATCH permitted?
- Are Authorization and Content-Type in the allowed headers?
- If cookies/credentials are used, does the policy allow credentials?

A successful preflight response may contain:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
~~~

The browser then sends the actual request. The exact preflight status code can vary by handler; what matters is that the response has valid CORS headers.

If the frontend sends custom headers such as `If-Match`, `X-Request-Id`, or `X-CSRF-TOKEN`, add them to allowed headers. If JavaScript needs to read response headers such as `ETag`, `Location`, or `X-Total-Count`, add them to exposed headers.

`Access-Control-Allow-Headers` determines which request headers the browser is allowed to send; `Access-Control-Expose-Headers` determines which response headers JavaScript is allowed to read. These two lists serve opposite directions.

## 11. Credentials, Cookies, and CSRF

If the frontend uses session cookies or browser credentials, the configuration must allow credentials:

~~~java
.allowCredentials(true)
.allowedOrigins("https://app.example.com")
~~~

Do not combine `allowCredentials(true)` with `allowedOrigins("*")`. Browsers do not accept a wildcard origin in a credentialed response. Configuring specific origins clearly limits trusted domains.

CORS and CSRF solve two different problems:

- CORS decides whether the browser may read a cross-origin response.
- CSRF protects the server against forged requests sent using the user's credentials.

If the application uses session cookies and allows the frontend to send cookies, configure appropriate CSRF tokens. Adding an origin to CORS does not disable CSRF protection and does not prove a request is legitimate.

Do not enable credentials just because the frontend encountered a CORS error. Enable it only when the use case genuinely requires cookies or credentials automatically sent by the browser; use HTTPS and restrict to specific origins.

## 12. Example of an Application with Both Spring Data REST and MVC

Suppose the frontend is at `https://app.example.com`. Repository APIs live under `/api`, custom MVC lives under `/mvc-api`.

Spring Data REST configuration:

~~~java
@Component
public class DataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Authorization", "Content-Type", "If-Match")
            .exposedHeaders("ETag", "Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Spring MVC configuration:

~~~java
@Configuration
public class MvcCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/mvc-api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Authorization", "Content-Type")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

How they divide:

| Request | Configuration to check |
| --- | --- |
| GET collection `/api/people` | Spring Data REST CORS |
| PATCH item `/api/people/42` | Spring Data REST CORS and Security filter if present |
| GET association `/api/people/42/address` | Spring Data REST CORS |
| GET custom report `/mvc-api/reports` | Spring MVC CORS |
| POST custom import `/mvc-api/imports` | Spring MVC CORS |
| Custom `@RepositoryRestController` | Spring Data REST/repository CORS and related method-level config |

Do not test only one URL. Collection, item, search, association, and custom controllers may route through different handlers.

## 13. Testing CORS with MockMvc

Test preflight separately for the repository exporter and custom MVC controllers.

### Preflight to Spring Data REST

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DataRestCorsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsConfiguredOriginToPatchRepositoryResource()
            throws Exception {

        mockMvc.perform(options("/api/people/42")
                .header(HttpHeaders.ORIGIN,
                        "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "PATCH")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization,content-type"))
            .andExpect(status().is2xxSuccessful())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.com"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("PATCH")));
    }
}
~~~

### Preflight to a Spring MVC controller

~~~java
@Test
void allowsConfiguredOriginToCallMvcController()
        throws Exception {

    mockMvc.perform(options("/mvc-api/reports")
            .header(HttpHeaders.ORIGIN,
                    "https://app.example.com")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"))
        .andExpect(status().is2xxSuccessful())
        .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"));
}
~~~

### Disallowed origin

~~~java
@Test
void doesNotAllowUnknownOrigin() throws Exception {

    mockMvc.perform(options("/api/people/42")
            .header(HttpHeaders.ORIGIN,
                    "https://untrusted.example")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "PATCH"))
        .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
}
~~~

The tests are template examples; adjust base paths, routes, status codes, and headers to match your application's versions of Spring Data REST, Spring MVC, and Spring Security.

If the Security filter processes preflights before HandlerMapping, run tests with the Security filter enabled. Tests using MockMvc without filters can miss the exact layer causing failures in production.

## 14. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Custom MVC controller works but repository resource hits CORS | Only WebMvcConfigurer was configured | Add configuration via RepositoryRestConfigurer |
| Repository resource works but custom controller hits CORS | Only exporter CORS was configured | Add WebMvcConfigurer or @CrossOrigin on the MVC controller |
| OPTIONS returns 401/403 before reaching controller | Security processes authentication before preflight | Enable CORS in the Security filter chain and place CORS handling before authentication |
| GET works but PATCH/PUT is blocked | Allowed methods omit write methods | Add the actual methods to allowedMethods |
| Requests with Authorization are blocked | Authorization is not in allowedHeaders | Add Authorization to allowedHeaders |
| JavaScript cannot read ETag | ETag is not exposed | Add ETag to exposedHeaders |
| Cookies are not sent | allowCredentials not enabled or wildcard origin used | Use a specific origin and allowCredentials(true) when genuinely needed |
| @CrossOrigin annotation has no effect on SDR | Annotation placed on a regular custom controller or non-repository route | Use repository annotation or appropriate RepositoryRestConfigurer |
| Assumed MVC configuration applied to SDR but it did not | Two independent registries | Check and configure both extension points |
| Multiple Access-Control-Allow-Origin headers | Multiple filters/configuration layers adding headers | Designate one primary handler and align policies |
| CORS allows it but request still gets 403 | Authorization/CSRF rejects the request | Check Spring Security; CORS does not grant permissions |
| Preflight test passes but browser still fails | Missing actual headers, credentials, Vary, or production filter differs from test | Inspect Network tab and response headers of both OPTIONS and actual request |

## 15. Implementation Workflow

1. List all endpoints and classify whether each is handled by Spring Data REST or Spring MVC.
2. Identify frontend origins per environment.
3. Configure repository resources via `RepositoryRestConfigurer`.
4. Configure custom MVC endpoints via `WebMvcConfigurer` or `@CrossOrigin`.
5. If using `@RepositoryRestController`, check inherited policy from the associated repository.
6. Allow only the methods and headers actually needed.
7. Expose only response headers JavaScript needs to read.
8. Enable credentials when cookies/sessions are required and use specific origins.
9. If Spring Security is present, ensure preflight is processed before authentication and filter-level CORS does not conflict with handler-level configuration.
10. Test OPTIONS for collection, item, association, search, and custom MVC routes.
11. Inspect both the actual request after preflight and its response headers.
12. Do not treat CORS as authorization; preserve appropriate security rules and CSRF protection.

## References

- [Spring Data REST 5.1.2 — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html): repository `@CrossOrigin`, custom `@RepositoryRestController`, global exporter `CorsRegistry`, and note that Spring MVC config does not apply to Spring Data REST.
- [Spring Framework — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `WebMvcConfigurer`, `@CrossOrigin`, preflight, credentials, and how global/local CORS combine.
- [Spring Security 7.1 — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): processing CORS before authentication, `CorsConfigurationSource`, `http.cors()`, and integration with MVC.
- [Spring Framework API — CorsConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowed origins, methods, headers, credentials, exposed headers, and max age.
