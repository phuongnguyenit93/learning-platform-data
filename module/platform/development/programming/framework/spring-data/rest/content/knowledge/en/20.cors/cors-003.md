# Configuring CORS for Custom Controllers in Spring Data REST

## 1. Goal

When a frontend runs on a different origin from the backend, the browser applies the same-origin policy and may block JavaScript from reading responses. CORS (Cross-Origin Resource Sharing) lets the server declare which origins, HTTP methods, and headers are allowed to access resources from a browser.

In an application with Spring Data REST, you need to distinguish between two groups of endpoints:

- **Repository endpoints and custom controllers within Spring Data REST's URI space:** use Spring Data REST's CORS configuration, @CrossOrigin on the repository or custom @RepositoryRestController, or RepositoryRestConfigurer.
- **Regular Spring MVC custom controllers:** use @CrossOrigin or WebMvcConfigurer.addCorsMappings.

A common point of confusion is that global CORS mappings declared with WebMvcConfigurer do not automatically apply to Spring Data REST endpoints. Determine which handler mapping processes the controller before choosing how to configure it.

## 2. Origin and the Same-Origin Policy

An origin is defined by scheme, host, and port. For example:

    http://localhost:3000
    http://localhost:8080
    https://localhost:3000
    https://app.example.com

The path /customers is not part of the origin. https://app.example.com differs from https://admin.example.com even though both applications may call the same backend.

If a frontend at http://localhost:3000 calls a backend at http://localhost:8080, the request is cross-origin. The server must return appropriate CORS response headers so the browser allows the frontend to read the response.

CORS is primarily a browser access-control mechanism. curl or Postman does not enforce the browser's CORS policy; requests from those tools may succeed even when the browser still reports a CORS error.

## 3. How Does a Preflight Request Work?

For certain cross-origin requests, the browser sends a preliminary check request (preflight) using HTTP OPTIONS. Preflight typically occurs when a request uses PUT, PATCH, DELETE, custom headers, or a content type outside the simple request group.

For example, the browser wants to send a PATCH with Authorization and Content-Type:

    OPTIONS /api/customers/42
    Origin: https://app.example.com
    Access-Control-Request-Method: PATCH
    Access-Control-Request-Headers: authorization, content-type, if-match

The server checks whether the origin, method, and request headers are permitted. A valid preflight response may contain:

    HTTP/1.1 200 OK
    Access-Control-Allow-Origin: https://app.example.com
    Access-Control-Allow-Methods: GET, POST, PATCH
    Access-Control-Allow-Headers: Authorization, Content-Type, If-Match
    Access-Control-Max-Age: 3600

After the preflight is accepted, the browser sends the actual PATCH request. For simple requests that do not require preflight, the browser can send the request first and only let JavaScript read the response if the CORS response headers are valid.

Access-Control-Request-Method indicates the method the browser wants to use in the actual request. Access-Control-Request-Headers lists the request headers that need to be allowed. The Spring CORS infrastructure can handle preflights without the controller having to implement OPTIONS logic.

## 4. Identifying the Type of Custom Controller

**Controller integrated with Spring Data REST**

Use @RepositoryRestController when a custom handler maps into the repository's URI space and needs to leverage Spring Data REST's base path, message converters, exception handling, and integrations. This type of controller supports @CrossOrigin on methods/classes and can inherit CORS configuration from the associated repository.

**Regular Spring MVC controller**

Use @RestController for standalone endpoints that do not need to be handled as repository resources. Configure CORS using @CrossOrigin or global mappings via WebMvcConfigurer.

Do not choose the configuration approach based solely on the class name. Annotations control the handler mapping and request path; that is what determines which CORS configuration gets applied.

## 5. Configuring @RepositoryRestController with @CrossOrigin

Example of a custom endpoint returning a Customer summary within Spring Data REST's URI space:

    @RepositoryRestController
    public class CustomerSummaryController {

        private final CustomerService customerService;

        public CustomerSummaryController(
                CustomerService customerService) {
            this.customerService = customerService;
        }

        @CrossOrigin(
            origins = "https://app.example.com",
            methods = RequestMethod.GET,
            allowedHeaders = {
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            },
            exposedHeaders = {
                "ETag",
                "Link"
            },
            maxAge = 3600
        )
        @GetMapping(
            path = "/customers/{id}/summary",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        @ResponseBody
        public CustomerSummary getSummary(
                @PathVariable Long id) {
            return customerService.getSummary(id);
        }
    }

In this example:

- origins restricts which frontend is allowed to call the endpoint.
- methods allows GET.
- allowedHeaders declares which request headers the browser is allowed to send.
- exposedHeaders allows JavaScript to read certain response headers.
- maxAge lets the browser cache the preflight result for the specified number of seconds.

The values in the example are illustrative. Replace the origin, path, and headers to match the actual frontend and API. You can place @CrossOrigin at the class level if all methods share the same policy; place it at the method level when individual endpoints need separate policies.

## 6. Inheriting CORS from the Associated Repository

Spring Data REST supports @CrossOrigin directly on the repository interface:

    @CrossOrigin(
        origins = "https://app.example.com",
        methods = {
            RequestMethod.GET,
            RequestMethod.POST,
            RequestMethod.PATCH
        },
        allowedHeaders = {
            "Authorization",
            "Content-Type",
            "If-Match"
        },
        exposedHeaders = {
            "ETag",
            "Location"
        },
        maxAge = 3600
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

A custom controller annotated with @RepositoryRestController can inherit @CrossOrigin configuration from the associated repository. This is useful when a custom route shares the repository base path and needs the same origin policy.

If a custom controller method needs a different policy, you can configure @CrossOrigin separately on the method or class. Check the rules for combining global and local configurations in the version of Spring Framework/Spring Data REST in use.

Do not assume every custom controller is tied to a repository. If a controller has no associated repository, configure CORS explicitly on the handler or via the mechanism appropriate for that controller type.

## 7. Global CORS Configuration for Spring Data REST

Multiple Spring Data REST endpoints can be configured in a single RepositoryRestConfigurer:

    @Component
    public class SpringDataRestCorsConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            cors.addMapping("/customers/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods(
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE"
                )
                .allowedHeaders(
                    "Authorization",
                    "Content-Type",
                    "If-Match",
                    "If-None-Match",
                    "X-Request-Id"
                )
                .exposedHeaders(
                    "ETag",
                    "Location",
                    "Link"
                )
                .allowCredentials(true)
                .maxAge(3600);
        }
    }

configureRepositoryRestConfiguration receives a CorsRegistry to configure CORS for Spring Data REST. The mapping /customers/** applies only to paths matching that pattern within Spring Data REST's URI space.

You can add separate mappings for different repositories instead of opening permissions for all of /**. When changing the base path using RepositoryRestConfiguration, check the actual path that the mapping receives.

Do not confuse RepositoryRestConfigurer with WebMvcConfigurer. Spring Data REST has its own CORS registry; global Spring MVC CORS configuration does not automatically apply to repository REST endpoints.

## 8. Configuring CORS for Regular @RestController

If the custom endpoint is a regular Spring MVC controller, you can use WebMvcConfigurer:

    @Configuration
    public class WebCorsConfig implements WebMvcConfigurer {

        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/custom/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods(
                    "GET",
                    "POST",
                    "PATCH",
                    "DELETE"
                )
                .allowedHeaders(
                    "Authorization",
                    "Content-Type",
                    "X-Request-Id"
                )
                .exposedHeaders(
                    "Location",
                    "ETag"
                )
                .allowCredentials(true)
                .maxAge(3600);
        }
    }

Or configure directly on the controller:

    @RestController
    @RequestMapping("/custom/reports")
    @CrossOrigin(
        origins = "https://app.example.com",
        methods = {
            RequestMethod.GET,
            RequestMethod.POST
        },
        allowedHeaders = {
            "Authorization",
            "Content-Type"
        },
        exposedHeaders = {
            "Location",
            "ETag"
        },
        maxAge = 3600
    )
    public class ReportController {

        @GetMapping("/{id}")
        public Report getReport(@PathVariable Long id) {
            // ...
        }
    }

The MVC configuration above applies to custom MVC controllers. If an endpoint is handled as a Spring Data REST endpoint, use Spring Data REST's CORS configuration or @CrossOrigin on the appropriate custom @RepositoryRestController.

Do not create two overlapping global mappings with different origins/methods/headers without understanding how Spring combines them. Duplicate configurations can lead to conflicting or hard-to-diagnose CORS response headers.

## 9. Differences Between allowedHeaders and exposedHeaders

| Configuration | Meaning | Example |
|---|---|---|
| allowedHeaders | Request headers the browser is allowed to send to the server | Authorization, Content-Type, If-Match |
| exposedHeaders | Response headers JavaScript is allowed to read | ETag, Location, Link |

For example, the frontend sends If-Match to update a resource with an ETag. This header must be in allowedHeaders.

If the frontend needs to read the new ETag after an update, ETag must be in exposedHeaders. The server may send ETag in the response, but JavaScript cannot read it via Fetch/XHR without an expose configuration.

Similarly, Location is useful after a POST creates a resource; Link may contain hypermedia relations that the client needs to read. Expose only the response headers that are actually needed.

## 10. Credentialed Requests and Origin Wildcards

If the frontend sends cookies/sessions or uses fetch credentials include mode, the server needs to allow credentials:

    fetch("https://api.example.com/custom/profile", {
      method: "GET",
      credentials: "include"
    });

The server configuration needs to enable allowCredentials(true) and specify a concrete origin, for example https://app.example.com.

Do not combine allowedOrigins("*") with allowCredentials(true). The CORS specification does not permit a wildcard origin with credentialed requests. If a dynamic set of subdomains is needed, Spring supports allowedOriginPatterns; the pattern must still be carefully restricted.

If the frontend manually adds a Bearer token in the Authorization header, that header must be permitted in allowedHeaders. Sending an Authorization header manually does not necessarily require enabling cookie credentials; only enable credentials when the request actually needs to send cookies, HTTP authentication, or the corresponding browser credentials.

CORS does not replace authentication, authorization, or CSRF protection. Allowing an origin to send requests does not mean callers from that origin are authorized to read or modify all data.

## 11. Integrating with Spring Security

CORS needs to be processed before Spring Security's authorization filter. OPTIONS preflights typically do not carry session cookies, so if security requires authentication before CORS is processed, the request may receive 401/403 even though the actual request could be authenticated.

With modern Spring Security, enable CORS integration in SecurityFilterChain:

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http) throws Exception {

        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.OPTIONS,
                    "/**"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }

The code snippet illustrates the integration order; .cors(...) needs a CORS configuration source or integration mechanism compatible with the application. If declaring a separate CorsConfigurationSource for the filter chain, register path patterns, origins, methods, and headers matching the custom endpoints. If using multiple CORS configuration layers, avoid returning duplicate or conflicting Access-Control-Allow-Origin headers.

Permitting OPTIONS through a security matcher does not automatically generate CORS response headers. It only lets the preflight reach the appropriate CORS processing. Do not open all actual requests to anonymous users just to fix preflight.

If using @RepositoryRestController, test preflight on that exact URI with Spring Security enabled. Do not just test another @RestController and assume the repository controller behaves identically.

## 12. Checking with curl

You can send a manual preflight to observe the response headers:

    curl -i -X OPTIONS "http://localhost:8080/customers/42/summary" -H "Origin: https://app.example.com" -H "Access-Control-Request-Method: PATCH" -H "Access-Control-Request-Headers: authorization,content-type,if-match"

Check the headers:

- Does Access-Control-Allow-Origin match the frontend origin?
- Does Access-Control-Allow-Methods include PATCH?
- Does Access-Control-Allow-Headers include Authorization, Content-Type, and If-Match?
- Is Access-Control-Allow-Credentials present if the request uses credentials?
- Does Access-Control-Max-Age match the configured value?

Then try the actual request with Origin:

    curl -i "http://localhost:8080/customers/42/summary" -H "Origin: https://app.example.com" -H "Accept: application/json"

curl only helps inspect what headers the server returns; it does not enforce the browser CORS policy. Also verify from a browser at the exact frontend origin to confirm JavaScript can read the response.

## 13. Testing CORS with MockMvc

For Spring MVC or custom repository controllers, you can write integration tests sending Origin and preflight headers:

    @SpringBootTest
    @AutoConfigureMockMvc
    class CustomerCorsTest {

        @Autowired
        private MockMvc mockMvc;

        @Test
        void allowsConfiguredOriginForPreflight()
                throws Exception {

            mockMvc.perform(options(
                    "/customers/42/summary")
                    .header(
                        "Origin",
                        "https://app.example.com"
                    )
                    .header(
                        "Access-Control-Request-Method",
                        "PATCH"
                    )
                    .header(
                        "Access-Control-Request-Headers",
                        "authorization,content-type,if-match"
                    ))
                .andExpect(status().isOk())
                .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "https://app.example.com"
                ))
                .andExpect(header().string(
                    "Access-Control-Allow-Methods",
                    org.hamcrest.Matchers.containsString("PATCH")
                ));
        }
    }

The preflight status may vary depending on the handler mapping and configuration; assert the actual response contract of the application. What matters is that the response has the appropriate origin, method, and headers, and is not blocked by Spring Security before CORS.

You can test a disallowed origin:

    mockMvc.perform(options("/customers/42/summary")
            .header("Origin", "https://unknown.example")
            .header(
                "Access-Control-Request-Method",
                "PATCH"
            ))
        .andExpect(status().isForbidden());

403 is common behavior for rejected preflights in Spring CORS processing; adjust according to actual error handling and configuration. Also check that the actual request has the expected Access-Control-Allow-Origin and exposed headers.

## 14. Common Errors

**Using WebMvcConfigurer for Spring Data REST endpoints**

Global MVC CORS mappings do not automatically apply to Spring Data REST. Use RepositoryRestConfigurer or @CrossOrigin on the repository/custom RepositoryRestController.

**Confusing @RestController with @RepositoryRestController**

The two annotations route requests through different handler mapping mechanisms. Determine whether the controller needs to integrate into the repository URI space or serve as a standalone MVC endpoint.

**Allowing only GET while the frontend sends PATCH**

A preflight requesting PATCH will not pass if allowedMethods lacks PATCH. Declare the actual methods, not just OPTIONS.

**Missing request headers in allowedHeaders**

Authorization, Content-Type, If-Match, or custom headers can cause preflight to fail if not permitted.

**Not exposing ETag or Location**

The server may return these headers, but JavaScript cannot read them if exposedHeaders is missing.

**Using wildcard with credentials**

Do not use an allowedOrigins wildcard when allowCredentials=true. Specify concrete origins or use restricted allowedOriginPatterns.

**Spring Security blocking OPTIONS**

Preflights do not carry session cookies like actual requests. Ensure CORS is processed before authorization and configure security to allow preflights to reach the right CORS handler.

**Configuring CORS but forgetting authentication**

CORS only controls browser cross-origin access. It does not authenticate callers or authorize data access.

**Testing with curl and concluding the browser works**

curl does not enforce CORS. Verify from a browser at the real origin, while checking the Network tab to inspect both preflight and actual requests.

## 15. Hands-on Exercises

Suppose the frontend runs at https://app.example.com and the backend has Spring Data REST along with a custom endpoint returning a Customer summary:

1. Create a custom endpoint in the repository URI space using @RepositoryRestController.
2. Use @CrossOrigin to allow only the frontend origin and the method the endpoint needs.
3. Declare allowedHeaders for Authorization, Content-Type, and X-Request-Id.
4. Expose ETag, Location, or Link if the frontend needs to read these headers.
5. Create a RepositoryRestConfigurer to configure CORS globally for a repository path.
6. Create a standalone @RestController and configure CORS separately with WebMvcConfigurer.
7. Confirm that the global MVC mapping does not automatically configure Spring Data REST repository endpoints.
8. Enable Spring Security and verify OPTIONS preflights are not blocked before CORS.
9. Send a preflight with curl and check Access-Control-Allow-Origin, Methods, and Headers.
10. Open the frontend in a browser and call the endpoint; inspect both the preflight and the actual request.
11. Try a disallowed origin, a disallowed method, and a disallowed header.
12. If using cookie credentials, verify explicit origin, allowCredentials, and CSRF policy.
13. Write MockMvc integration tests for a valid origin and a rejected origin.

Self-check questions:

- What components make up an origin?
- When does a browser send an OPTIONS preflight?
- Why does WebMvcConfigurer global CORS not automatically apply to Spring Data REST?
- When should you use @RepositoryRestController and when should you use @RestController?
- How does allowedHeaders differ from exposedHeaders?
- Why does ETag need to be exposed if the frontend has to read it?
- Why cannot a wildcard origin be used with credentialed requests?
- Why must CORS be processed before Spring Security?
- Does CORS replace authentication, authorization, or CSRF protection?

## 16. Key Takeaways

- CORS lets the server declare origins, methods, and headers that a browser is allowed to use.
- Determine whether an endpoint belongs to Spring Data REST or Spring MVC before configuring.
- Spring Data REST supports @CrossOrigin on repositories and custom @RepositoryRestControllers.
- RepositoryRestConfigurer receives a CorsRegistry to configure CORS globally for Spring Data REST.
- WebMvcConfigurer.addCorsMappings configures MVC endpoints; this mapping does not automatically apply to Spring Data REST.
- OPTIONS preflights check origin, method, and request headers before the actual request.
- allowedHeaders permits request headers; exposedHeaders lets JavaScript read response headers.
- Credentialed requests require specific origins; do not use a wildcard origin with allowCredentials=true.
- CORS must be processed before Spring Security authorization.
- CORS does not replace authentication, authorization, or CSRF protection.
- Verify with a browser and integration tests; curl only helps inspect response headers.

## References

- Spring Data REST Reference — Configuring CORS: https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html
- Spring Framework Reference — CORS support in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security Reference — CORS integration: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Data REST Reference — Custom REST controllers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
