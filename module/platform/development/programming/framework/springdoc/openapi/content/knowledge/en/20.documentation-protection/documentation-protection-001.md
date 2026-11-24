# Distinguishing Specification Read Access, UI Access, and API Execution Access

A Spring Boot application can publish API documentation via Swagger UI and OpenAPI JSON/YAML while also exposing business endpoints for clients. These three surfaces are often related, yet they have different access permissions:

1. **Swagger UI:** the web page and static assets that let users browse the documentation.
2. **OpenAPI document:** the JSON/YAML describing paths, operations, schemas, security, and responses.
3. **API runtime:** the endpoints that execute business logic, reading or modifying data.

Being able to open the Swagger UI page does not mean a user can load the specification; being able to download the specification does not mean they can call the API; and disabling the Swagger UI interface does not protect the endpoints either. You need to design separate access policies for each surface, then verify them with real requests.

## 1. Three Independent Access Surfaces

With the default configuration of springdoc-openapi, the common paths are:

| Surface | Common Default Path | Content |
|---|---|---|
| Swagger UI redirect | /swagger-ui.html | Redirects to the UI interface |
| Swagger UI assets | /swagger-ui/** | HTML, JavaScript, CSS, and UI resources |
| OpenAPI JSON | /v3/api-docs | OpenAPI specification in JSON format |
| OpenAPI YAML | /v3/api-docs.yaml | OpenAPI specification in YAML format |
| Grouped OpenAPI | /v3/api-docs/{group} | Specification of a document group |

These paths can change depending on springdoc.swagger-ui.path and springdoc.api-docs.path. If the application uses a context path or a reverse proxy, the public URL can also differ from the internal URL.

The three surfaces can be protected differently:

- A user allowed to open Swagger UI but not allowed to load the spec will see the UI page, while the operations section may fail to load.
- A user who can download the OpenAPI JSON directly may still be unable to open Swagger UI.
- A user may be blocked from accessing the documentation yet still call the API with another client if the runtime endpoint permits it.
- A user may be able to access the documentation yet be rejected by the API due to a missing token or insufficient permissions.

Decide clearly who is allowed to read the documentation, who can open the UI, and who can execute each API.

## 2. Separating Documentation Read Access from API Call Access

A common policy in internal systems:

- Development or operations team members have the DOCS_READER role to open Swagger UI and download the specification.
- Business APIs require a bearer token and appropriate scopes.
- Public endpoints only expose certain data-reading operations.
- Administrative endpoints require a dedicated role or authority.

Example permission matrix:

| Principal | Swagger UI | OpenAPI JSON/YAML | GET catalog | GET orders | POST orders |
|---|---:|---:|---:|---:|---:|
| Anonymous | No | No | Yes | No | No |
| DOCS_READER | Yes | Yes | Yes | Per API token | Per API token |
| API_USER with orders.read | Per docs policy | Per docs policy | Yes | Yes | No |
| API_USER with orders.write | Per docs policy | Per docs policy | Yes | Per read permission | Yes |

The table above illustrates that the two credential groups can be different. The DOCS_READER permission does not automatically grant orders.read or orders.write. Likewise, having a scope to call an API does not necessarily grant permission to view internal documentation.

You can use the same identity system while separating authorities for documentation and business operations. This approach lets you revoke docs access without having to change API call permissions.

## 3. OpenAPI Security Requirements Do Not Protect Documentation Endpoints

Annotations such as @SecurityScheme and @SecurityRequirement describe the authentication mechanism that clients use when calling the documented operation.

Bearer token example:

~~~java
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Attach it to an API operation:

~~~java
@GetMapping("/api/me")
@Operation(
    summary = "Get current profile",
    security = @SecurityRequirement(name = "bearerAuth")
)
public ProfileResponse getProfile() {
    return profileService.current();
}
~~~

This declaration generates metadata in OpenAPI. It does not enforce access control on /swagger-ui.html or /v3/api-docs. Documentation paths must be controlled by Spring Security, a reverse proxy, or an equivalent protection layer.

Conversely, configuring Spring Security to block /v3/api-docs does not automatically give every operation in the documentation a security requirement. You need to verify both the runtime security policy and the generated security metadata.

## 4. Configuring Default Documentation Paths

Before writing a SecurityFilterChain, identify the exact URLs served by springdoc. The default configuration typically includes:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

The paths can be changed:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /internal/docs
~~~

When changing paths, the JSON and YAML endpoints, the Swagger UI redirect, and grouped documents can change depending on the configuration. Security matchers must be updated accordingly.

Do not assume that a /v3/api-docs/** matcher will protect a custom path such as /internal/openapi. Open the application and inspect the actual URLs before finalizing the policy.

## 5. Protecting Documentation with a Dedicated SecurityFilterChain

You can use one SecurityFilterChain for documentation and another chain for business APIs. This approach clarifies the distinction between credentials for reading docs and bearer tokens for calling APIs.

The example below uses HTTP Basic for internal documentation and a JWT Resource Server for APIs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain documentationChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs/**",
                "/v3/api-docs.yaml"
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("DOCS_READER")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
~~~

Key points:

- The documentation chain only matches Swagger UI and OpenAPI endpoints.
- The API chain only matches /api/**.
- Chains are selected in order; a request enters the first chain whose matcher fits.
- DOCS_READER is the role for documentation readers.
- The API checks separate scopes such as SCOPE_orders.read and SCOPE_orders.write.
- The fallback chain denies undeclared paths.

hasRole("DOCS_READER") typically checks the authority ROLE_DOCS_READER. The application needs a UserDetailsService, authentication provider, or equivalent login mechanism to grant that role. The example only illustrates the chain structure; it must be integrated with a real user source.

The documentation chain uses HTTP Basic so the browser can authenticate when loading HTML, JavaScript, and the OpenAPI document. Only use Basic over HTTPS and manage passwords securely.

## 6. Why Separate the Documentation Chain and the API Chain?

If you combine everything under a single anyRequest().authenticated() rule, users may have to use the same kind of credential for both docs and APIs. That is not always appropriate.

Separating chains allows you to:

- Use internal login or HTTP Basic for the docs page.
- Use bearer JWTs for APIs.
- Grant a dedicated DOCS_READER role.
- Apply CSRF and session policies suitable for each surface.
- Easily verify matcher ordering and avoid accidentally exposing endpoints.

Note that only the first chain matching a request is used. If the API chain is placed first and its matcher is too broad, documentation requests may be handled by the API chain. If the docs chain uses a /** matcher, it may accidentally catch every endpoint. Restrict matchers to exact URLs.

For large applications, you can use more filter chains, but each chain needs a clear scope and tested ordering.

## 7. Public Documentation Case

If the documentation is allowed to be publicly accessible, you can permit the docs paths:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).permitAll()
    .anyRequest().authenticated()
)
~~~

This only opens the UI and specification. Business APIs can still require a JWT or specific roles.

Before making it public, review whether the spec contains:

- Administrative or internal endpoints.
- System names, paths, or infrastructure details you do not want exposed.
- Schemas containing internal fields.
- Descriptions of sensitive business workflows.
- Server URLs for staging or development environments.
- Examples containing real data or secrets.

Do not put passwords, tokens, API keys, or real personal data into examples and descriptions. OpenAPI is a document that can be downloaded and stored outside the application.

## 8. Protecting Swagger UI While Allowing OpenAPI JSON Downloads

Some organizations want developers to use their own tools to fetch the spec without exposing the Swagger UI interface to everyone.

You can configure them separately:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/swagger-ui.html", "/swagger-ui/**")
        .hasRole("DOCS_UI_USER")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasRole("SPEC_READER")
    .anyRequest().authenticated()
)
~~~

With this setup, only users with DOCS_UI_USER can open the UI, while SPEC_READER can download JSON/YAML using curl or code generation tools.

If Swagger UI needs to load the spec from /v3/api-docs, the user opening the UI must also have the SPEC_READER permission or an equivalent access mechanism. Otherwise, the HTML page may load successfully while the operations list fails because the spec fetch request receives 401/403.

If both permissions are granted to the same group, you can use the same role for both paths to keep the configuration simpler.

## 9. Allowing the UI While Blocking Direct Specification Access

The opposite policy can also occur: a group of users is allowed to access the UI through a reverse proxy or session, while direct spec endpoints are restricted.

However, Swagger UI needs to load the OpenAPI document to render operations. If the UI and spec reside in the same application, blocking the spec will prevent the UI from working unless an intermediate proxy or backend is granted permission to read the spec.

You cannot just open the HTML page and expect Swagger UI to automatically know the entire schema. The UI needs OpenAPI data from the configured URL or an embedded document.

If the goal is to let users view rendered documentation without downloading the raw spec file, you need to design an appropriate delivery channel and keep in mind that displayed content can still be extracted from the browser.

## 10. Grouped OpenAPI Also Needs Protection

When using GroupedOpenApi, springdoc can publish multiple documents, for example:

- /v3/api-docs/public
- /v3/api-docs/partner
- /v3/api-docs/admin

Groups usually still sit under the root path /v3/api-docs, but you need to verify the actual endpoints in the application. The matcher /v3/api-docs/** typically covers group paths; the root endpoint and YAML must be declared appropriately.

If public and admin have different policies, you should not rely on a single blanket matcher for all groups. You can place specific matchers before the general matcher:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/v3/api-docs/admin").hasRole("ADMIN_DOCS")
    .requestMatchers("/v3/api-docs/partner").hasRole("PARTNER_DOCS")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/public",
        "/v3/api-docs.yaml"
    ).permitAll()
    .anyRequest().authenticated()
)
~~~

Matcher ordering within the same authorization rule matters: specific rules must come before general rules. If a general matcher is evaluated first, the dedicated rule for admin may not be applied as intended.

If Swagger UI uses a specific group, configure the corresponding spec URL and verify permission to load that group. Do not let the UI accidentally load the admin document when a user is only allowed to read the public API.

## 11. Custom Paths and Reverse Proxies

If you configure:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /internal/docs
~~~

then the SecurityFilterChain needs to protect the custom paths, such as /internal/docs, the corresponding UI resources, and /internal/openapi along with any variants/groups if present.

When deploying behind a reverse proxy, external paths may be rewritten. For example, the public URL /docs may be forwarded to /swagger-ui.html. Security policies at the proxy and in the application must be consistent.

Check:

- Spring Boot context path.
- springdoc.api-docs.path.
- springdoc.swagger-ui.path.
- Proxy prefixes and rewrite rules.
- Forwarded headers.
- The URL Swagger UI uses to load the spec.
- The server URL Try it out uses to call the API.

Do not test only internal URLs. Test from the network and hostname that users actually use.

## 12. Swagger UI Authorize Is Not Documentation Page Read Permission

The Authorize button in Swagger UI uses OpenAPI security schemes to configure credentials for API requests sent via Try it out.

It typically does not replace the login mechanism for loading the Swagger UI page itself or the initial spec file.

For example:

- The browser needs to log in to load /swagger-ui/index.html.
- The browser needs read access to /v3/api-docs to fetch the specification.
- After the UI finishes loading, the user enters a bearer token via Authorize to call /api/orders.

These are three authentication steps that can use different credentials or policies. If docs are protected with HTTP Basic/session while the API uses JWT, Swagger UI can use Basic to load the documentation and a bearer token for business requests.

Do not assume a token entered in the Authorize button is already sent when the browser loads the OpenAPI file during UI initialization.

## 13. supportedSubmitMethods Does Not Protect the API

The springdoc.swagger-ui.supportedSubmitMethods setting can restrict the methods allowed to be sent via Try it out. For example, allowing only GET:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
~~~

Or disabling Try it out entirely:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

These settings only change the ability to send test calls in Swagger UI. Users can still send POST, PUT, PATCH, or DELETE using curl, Postman, or another application if the backend permits it.

To protect the API, configure authorization at runtime. To protect documentation, protect the Swagger UI and OpenAPI endpoints. Do not use one setting as a substitute for the other two.

## 14. CSRF and CORS Per Surface

If HTTP Basic or session cookies are used for docs, the browser may automatically send credentials on subsequent requests. For cookie/session-based applications, evaluate CSRF according to your Spring Security policy.

Swagger UI primarily loads pages, assets, and the spec using GET. If state-changing API operations are invoked from Try it out using a session cookie, the request may require a CSRF token.

CORS is only relevant when Swagger UI and the API/spec are on different origins. You must allow the right origins, methods, and headers such as Authorization and Content-Type. CORS does not replace authentication and does not stop curl or Postman.

For stateless APIs using bearer tokens in the Authorization header, the CSRF configuration may differ from session-based applications. Only disable CSRF once the authentication model and how the browser sends credentials have been evaluated.

## 15. Disabling Swagger UI or the OpenAPI Document

springdoc allows disabling the UI or the specification endpoint via configuration:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

Disabling Swagger UI stops serving the UI interface. Disabling api-docs stops serving dynamic documentation. Depending on configuration and version, verify the actual endpoints after startup.

Disabling docs does not automatically protect the API. Business endpoints are still handled by controllers and the SecurityFilterChain. Conversely, keeping OpenAPI JSON enabled while disabling the UI still allows consumers to download the spec if the JSON endpoint is open.

You can use separate profiles to enable docs in development and disable or restrict them in production. Ensure the final configuration is loaded under the right profile.

## 16. Verifying Access Permissions with curl

Test each surface separately. For example, when docs require HTTP Basic:

~~~bash
# Without credentials: expected 401
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/v3/api-docs

# With docs read permission: expected 200
curl -i -u docs-reader:REPLACE_WITH_SECRET \
  http://localhost:8080/v3/api-docs

# Load the UI
curl -i -u docs-reader:REPLACE_WITH_SECRET \
  http://localhost:8080/swagger-ui/index.html
~~~

Test the API with a bearer token:

~~~bash
# No token: typically 401 for endpoints requiring authentication
curl -i http://localhost:8080/api/orders

# Valid token but missing scope: typically 403
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer REPLACE_WITH_TOKEN"

# Token with matching scope: may be allowed
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer REPLACE_WITH_TOKEN"
~~~

Replace credentials with test values supplied via a secret manager or environment variables. Do not commit passwords or tokens into scripts.

Exact statuses depend on the authentication entry point and policy. A public endpoint may return 200 without a token; a nonexistent endpoint may return 404; a gateway may also alter responses.

## 17. Testing the Permission Matrix

You can write integration tests for each principal type:

| Test case | Swagger UI | OpenAPI spec | API protected |
|---|---:|---:|---:|
| Anonymous | 401/403 | 401/403 | 401 |
| User without DOCS_READER | 403 | 403 | Per API scope |
| DOCS_READER | 200 | 200 | 401 without bearer token |
| JWT with orders.read | Per docs role | Per docs role | 200 for GET orders |
| JWT with only orders.read calling POST | Per docs role | Per docs role | 403 |
| JWT with orders.write | Per docs role | Per docs role | 200/201 depending on operation |

You can use MockMvc and Spring Security Test to verify matchers and authorities. For HTTP Basic, tests can use the httpBasic helper; for a resource server, you can use jwt() to simulate scopes.

Example:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

And test a user without docs access:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isUnauthorized());
~~~

Real tests must load the exact SecurityFilterChain and user configuration. If using @WebMvcTest, import the security configuration and mock the required controller dependencies. When testing JWTs with jwt(), remember that the helper mocks Authentication; it does not verify a real token signature.

## 18. Common Pitfalls

| Symptom | Cause to Check |
|---|---|
| Swagger UI loads but has no operations | Request to fetch OpenAPI JSON got 401/403 or spec URL is wrong |
| OpenAPI JSON is publicly accessible even though UI is blocked | Only /swagger-ui/** was protected; /v3/api-docs was forgotten |
| UI is blocked but API can still be called | Docs permissions and API permissions are two separate policies |
| API requires JWT but Swagger UI does not send a token | Missing security requirement or not Authorized yet |
| Authorize button does not help load the spec | Credentials for the API are not automatically used to load the page/spec |
| Admin group is exposed | Broad permitAll matcher comes before specific group matcher |
| YAML is unprotected | Forgot the /v3/api-docs.yaml endpoint |
| Changed api-docs.path yet old URL is still accessible | Matchers or proxy configuration out of sync |
| Every request enters the docs chain | securityMatcher is too broad or chain ordering is wrong |
| Docs user can call data-modifying API | Authority granted by mistake or API chain is too permissive |
| Disabled Swagger UI yet API is still accessible | Disabling docs does not affect runtime endpoints |
| Browser CORS error | UI and API are on different origins and CORS does not allow them |

## 19. Policy Implementation Workflow

When implementing documentation protection:

1. List the Swagger UI, OpenAPI JSON/YAML, and all grouped document URLs.
2. List runtime APIs and classify public/protected endpoints.
3. Identify the groups allowed to read documentation and the groups allowed to call APIs.
4. Choose credentials for docs: session, Basic, gateway SSO, or an internal mechanism.
5. Configure SecurityFilterChains with specific matchers and clear ordering.
6. Configure API security separately by token, role, and scope.
7. Configure the Swagger UI URL so it loads the right spec and the right group.
8. Verify CORS/CSRF if cross-origin browser requests or cookies are used.
9. Test anonymous users, docs readers, API users lacking scopes, and fully authorized API users.
10. Test from the public hostname through the reverse proxy, not only localhost.
11. Review spec contents before publishing and monitor permission changes.

## 20. Checklist

- [ ] Distinguished Swagger UI, OpenAPI JSON/YAML, and API runtime.
- [ ] Listed all docs paths, including YAML and grouped documents.
- [ ] Decided whether documentation is public or internal.
- [ ] Swagger UI and OpenAPI documents have appropriate access permissions.
- [ ] DOCS_READER permission is separated from API execution scopes.
- [ ] SecurityFilterChain matchers are accurate and their ordering does not overlap.
- [ ] API endpoints are independently protected with authentication/authorization.
- [ ] OpenAPI security requirements match the actual API policy.
- [ ] Swagger UI can load the spec with appropriate credentials.
- [ ] CORS/CSRF match the origin and cookie/token model.
- [ ] supportedSubmitMethods is not treated as a backend protection measure.
- [ ] Verified profiles and custom paths in the deployment environment.
- [ ] Tested anonymous, docs reader, insufficient-scope token, and sufficient-scope token.
- [ ] Tested through the reverse proxy/public URL.
- [ ] No secrets or sensitive data in the documentation.

## 21. References

- [springdoc-openapi – official documentation](https://springdoc.org/)
- [Spring Security – Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)

Swagger UI, OpenAPI JSON/YAML, and the API runtime are three distinct access surfaces. Grant documentation read access separately, protect business endpoints with authentication and authorization, and verify that Swagger UI can load the right spec. Only when all three surfaces are verified with real requests does the documentation protection policy accurately reflect how the application is used.
