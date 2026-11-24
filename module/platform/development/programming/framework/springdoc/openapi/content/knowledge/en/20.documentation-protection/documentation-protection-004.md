# Configuring Spring Security for Servlet or Reactive Stacks

## 1. Why Protect Documentation Endpoints?

Springdoc OpenAPI typically exposes several endpoints to serve documentation and the API testing UI. With the default configuration, an application may publicly expose:

| Default Endpoint | Role |
|---|---|
| **/v3/api-docs** | OpenAPI document in JSON format |
| **/v3/api-docs.yaml** | OpenAPI document in YAML format |
| **/v3/api-docs/{group}** | JSON document for a document group |
| **/v3/api-docs/{group}.yaml** | YAML document for a document group |
| **/v3/api-docs/swagger-config** | Configuration used by Swagger UI to load documents |
| **/swagger-ui.html** | Entry path to Swagger UI, typically redirects to the UI page |
| **/swagger-ui/** | HTML, JavaScript, CSS, and Swagger UI assets |

An OpenAPI document can reveal internal paths, operation names, request/response structures, security schemes, service names, and partial architectural details. Swagger UI also lets users send test requests directly. Therefore, production environments usually need to control who can read the documentation and who can use the API testing UI.

Springdoc generates documentation; Spring Security enforces HTTP access permissions. Protection configuration must cover both JSON/YAML endpoints and Swagger UI pages and assets. Locking only the UI page while leaving documentation endpoints public still lets others download the specification directly.

This article presents two separate Spring Security configurations based on the web stack:

- **Servlet**: uses SecurityFilterChain with Spring MVC or servlet applications.
- **Reactive**: uses SecurityWebFilterChain with Spring WebFlux.

These two chain types belong to two different request-processing architectures. Choose the right one for your application; do not mix SecurityFilterChain and SecurityWebFilterChain for the same web stack.

## 2. Identifying the Exact Paths to Protect

Before writing security rules, identify the actual paths your application exposes. Springdoc provides properties to customize endpoints:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

When this configuration changes, the default documentation endpoints can become:

- **/openapi** for OpenAPI JSON.
- **/openapi.yaml** for YAML.
- **/openapi/{group}** and **/openapi/{group}.yaml** for document groups.
- **/openapi/swagger-config** for Swagger UI configuration.
- **/docs** for the Swagger UI entry point; this page may forward or redirect to UI assets.

Swagger UI asset paths still need to be verified via the Network tab. Depending on the version, page overrides, asset configuration, and reverse proxies, the browser may load additional URLs.

Do not protect only a single URL such as /v3/api-docs. The pattern /v3/api-docs/** covers group documents and swagger-config in the default layout. Similarly, /swagger-ui/** covers the UI's static files, while /swagger-ui.html is the entry point to account for.

If using custom paths, add those exact paths to your security matchers. After starting the application, open the Network tab to list every request Swagger UI makes; use that list to verify that matchers do not miss any endpoint.

## 3. Choosing an Access Policy for Documentation

There are three common models:

| Policy | How It Is Applied | When Appropriate |
|---|---|---|
| Public | Allow anonymous users to read documentation | Public APIs, documentation contains no sensitive information |
| Require login | Users must authenticate to download documentation | Documentation for employees or partners |
| Require a specific role | Only authorized groups such as API_DOCS can access | Internal documentation or production API testing UI |

There is no single right policy for every environment. Public documentation may be published on a developer portal; internal documentation typically requires authentication and authorization. Some organizations disable Swagger UI in production while still publishing OpenAPI artifacts through a controlled distribution channel.

Two decisions must be separated:

1. Who can view the OpenAPI document and Swagger UI?
2. Who can call real operations in the API?

Someone authorized to view documentation may not have permission to call the API. Conversely, a client allowed to call the API does not necessarily need access to Swagger UI. Both policies must be configured and tested independently.

## 4. Protecting Documentation in a Servlet Application

With Spring MVC or a servlet application, Spring Security uses SecurityFilterChain. You can create one chain for documentation and another chain for business APIs.

Example allowing only users with the API_DOCS role to access documentation:

~~~java
@Configuration
@EnableWebSecurity
public class ServletSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain documentationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher(
                "/v3/api-docs/**",
                "/v3/api-docs.yaml",
                "/swagger-ui/**",
                "/swagger-ui.html"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("API_DOCS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

In this example:

- The first chain matches only documentation URLs.
- hasRole("API_DOCS") requires the corresponding authority ROLE_API_DOCS.
- HTTP Basic is used as a simple authentication example; user records and the authentication mechanism must be configured in the application.
- The second chain handles remaining requests and requires login.

Order(1) ensures the documentation chain is evaluated first. Spring Security uses the first chain matching the request; the second chain acts as a fallback for remaining paths. If the application has more chains, verify ordering and matchers so you do not leave gaps where requests go unprotected.

If you want public documentation, change the rule in the first chain:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .anyRequest().permitAll()
)
~~~

The application chain continues protecting business APIs. permitAll for documentation does not mean every other endpoint is public.

## 5. Protecting Documentation with a Single SecurityFilterChain

If the application does not yet need separate chains, you can place documentation rules alongside API rules in one chain:

~~~java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/v3/api-docs/**",
                "/v3/api-docs.yaml",
                "/swagger-ui/**",
                "/swagger-ui.html"
            ).hasRole("API_DOCS")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This approach is concise and works well when the entire application uses the same authentication mechanism. However, when documentation has a different policy from business APIs, separating chains makes the scope and rule ordering clearer.

In a single shared chain, matcher order matters greatly. Specific rules for documentation must come before the general anyRequest() rule. If anyRequest() is placed first, matchers after it will never have a chance to apply.

If you need form login or OAuth2 login instead of HTTP Basic, replace the authentication mechanism accordingly and verify how Swagger UI fetches JSON. When fetching the OpenAPI document, a redirect to an HTML login page may cause the UI to receive HTML instead of JSON. For documentation endpoints, choose an approach that returns 401/403 or an authentication flow that clients can handle properly.

## 6. Configuring Public Documentation in Servlet

Some systems want public documentation while requiring login for APIs:

~~~java
@Bean
@Order(1)
SecurityFilterChain documentationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .securityMatcher(
            "/v3/api-docs/**",
            "/v3/api-docs.yaml",
            "/swagger-ui/**",
            "/swagger-ui.html"
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().permitAll()
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

The documentation chain opens only documentation endpoints. The business chain permits one public API area and requires login for remaining APIs.

If the documentation contains internal operations, private server hostnames, sensitive schemas, or examples that should not be public, consider requiring a role instead of permitAll. Just because an OpenAPI document contains no secrets does not mean all of its contents are appropriate for public release.

## 7. Protecting Documentation in a Reactive Application

With Spring WebFlux, Spring Security uses SecurityWebFilterChain and ServerHttpSecurity. Do not use servlet HttpSecurity or SecurityFilterChain in a reactive configuration.

Example creating a dedicated chain for documentation:

~~~java
@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain documentationSecurity(ServerHttpSecurity http) {
        ServerWebExchangeMatcher documentationPaths =
            new OrServerWebExchangeMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/v3/api-docs/**"
                ),
                new PathPatternParserServerWebExchangeMatcher(
                    "/v3/api-docs.yaml"
                ),
                new PathPatternParserServerWebExchangeMatcher(
                    "/swagger-ui/**"
                ),
                new PathPatternParserServerWebExchangeMatcher(
                    "/swagger-ui.html"
                )
            );

        return http
            .securityMatcher(documentationPaths)
            .authorizeExchange(authorize -> authorize
                .anyExchange().hasRole("API_DOCS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

In this example:

- PathPatternParserServerWebExchangeMatcher matches paths on the reactive exchange.
- OrServerWebExchangeMatcher combines the paths to protect.
- The first chain handles documentation endpoints.
- The second chain handles remaining requests.
- hasRole("API_DOCS") requires the ROLE_API_DOCS authority.

These matcher classes belong to Spring Security WebFlux. Exact imports must match your project's Spring Security version. If you changed springdoc.api-docs.path or springdoc.swagger-ui.path, replace the default patterns with the paths in use.

## 8. Allowing Public Documentation in Reactive

If the OpenAPI document and Swagger UI are allowed to be publicly accessible, change only the documentation chain's rule:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain documentationSecurity(ServerHttpSecurity http) {
    ServerWebExchangeMatcher documentationPaths =
        new OrServerWebExchangeMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/v3/api-docs/**"
            ),
            new PathPatternParserServerWebExchangeMatcher(
                "/v3/api-docs.yaml"
            ),
            new PathPatternParserServerWebExchangeMatcher(
                "/swagger-ui/**"
            ),
            new PathPatternParserServerWebExchangeMatcher(
                "/swagger-ui.html"
            )
        );

    return http
        .securityMatcher(documentationPaths)
        .authorizeExchange(authorize -> authorize
            .anyExchange().permitAll()
        )
        .build();
}
~~~

The application chain must still be declared to protect business routes. Never omit the fallback chain just because the documentation chain already works; requests not matching the documentation matcher are handled by another chain or could remain unprotected if no suitable chain exists.

In reactive applications, Order priority and matcher scope are just as important as in Servlet. Test one documentation request, one public API request, and one authenticated API request to verify each chain is selected properly.

## 9. Changing Documentation Endpoints Requires Updating Security Matchers

Suppose the Springdoc configuration changes the endpoints:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /developer/docs
~~~

Security matchers need to cover the new URLs:

- /internal/openapi
- /internal/openapi.yaml for default YAML
- /internal/openapi/** for groups and swagger-config
- /developer/docs
- The actual Swagger UI resource URLs loaded by the browser, usually /swagger-ui/**

In a Servlet configuration, an illustrative matcher for these paths is:

~~~java
.securityMatcher(
    "/internal/openapi/**",
    "/internal/openapi.yaml",
    "/swagger-ui/**",
    "/swagger-ui.html",
    "/developer/docs"
)
~~~

In Reactive, use the same patterns with PathPatternParserServerWebExchangeMatcher.

Do not assume a custom UI path replaces every resource path. The entry point may redirect to another page. Open the UI URL and inspect the Network tab to identify the HTML, JavaScript, CSS, swagger-config, and OpenAPI document paths.

If the application runs under a context path or reverse proxy prefix, verify the path seen by Spring Security matchers versus the path called by the browser. Avoid duplicating prefixes or omitting prefixes due to gateway rewrites.

## 10. Protecting JSON, YAML, Groups, and swagger-config

A common mistake is locking only the default JSON while forgetting related endpoints. Review:

| Request Type | Example | Rule Needed? |
|---|---|---|
| Default JSON | GET /v3/api-docs | Yes |
| Default YAML | GET /v3/api-docs.yaml | Yes |
| Group document | GET /v3/api-docs/partner | Yes |
| Group YAML | GET /v3/api-docs/partner.yaml | Yes |
| Swagger config | GET /v3/api-docs/swagger-config | Yes |
| UI entry point | GET /swagger-ui.html | Yes |
| UI resources | GET /swagger-ui/index.html, CSS, JS | Yes |
| API operations | GET/POST /api/** | Per business API policy |

The pattern /v3/api-docs/** typically covers sub-endpoints under docs. The default YAML endpoint may use a .yaml suffix on the root path; check matchers and the behavior of your running Springdoc version to ensure it is protected.

There is no need to permit all requests to /v3/** if you only want to protect OpenAPI documents. Use narrow matchers so you do not accidentally expose actuator endpoints or other system endpoints.

## 11. Distinguishing Documentation Viewing from API Execution

Swagger UI performs two kinds of requests:

1. Loading the UI, swagger-config, and OpenAPI documents.
2. Calling API operations when the user clicks Try it out.

Requests loading documentation go to Springdoc endpoints. Try it out requests go to business endpoints described in OpenAPI. The two groups can use different security chains and credentials.

For example, a user with role API_DOCS may be allowed to download documentation, while operation POST /api/orders still requires OAuth2 scope orders.write. Being able to load Swagger UI does not grant that scope. The user must authenticate according to the Security Scheme declared for the API, and the backend must verify tokens/permissions at runtime.

Conversely, a service account permitted to call the API does not necessarily need a documentation-reading role. This is an independent authorization choice.

In OpenAPI documentation, declaring @SecurityScheme and @SecurityRequirement tells Swagger UI how to prompt for operation credentials. Spring Security or the resource server is what actually verifies credentials when requests reach the API.

## 12. Do Not Disable CSRF Just to Make Swagger UI Work

Spring Security enables CSRF protection by default in many session-based servlet setups. Swagger UI can send state-changing requests like POST, PUT, PATCH, or DELETE when users click Try it out.

If the application uses session cookies and CSRF protection, state-changing requests must send a valid CSRF token. Simply protecting documentation endpoints with HTTP Basic does not solve CSRF for business APIs.

Do not disable CSRF application-wide just so Swagger UI can send POST requests. Choose a policy based on the actual authentication mechanism:

- If the API uses session cookies, keep CSRF protection enabled and supply tokens using the application's mechanism.
- If the API is stateless using bearer tokens in the Authorization header and does not rely on automatically sent cookies, CSRF can be configured appropriately for a stateless model.
- If you only want documentation reading, Springdoc endpoints are primarily GET; there is no need to disable CSRF globally for this reason.

In WebFlux, CSRF must also be configured according to how the application authenticates and uses cookies. Do not copy a disable-CSRF configuration from a stateless example into a session-based application.

## 13. CORS When Swagger UI and API Are on Different Origins

If Swagger UI is served from one host while the API is on another host, browsers enforce CORS. Loading the OpenAPI document and calling operations can be two separate cross-origin flows.

You must configure CORS for the exact Swagger UI origin, required methods, and required headers. If using the Authorization header or an API key header, an OPTIONS preflight may be sent before the actual request. If using cookies, configure credentials and specific origins.

Points to check:

- Origin of the Swagger UI page.
- Origin of the OpenAPI document.
- Server URLs in the OpenAPI document.
- Allowed methods and allowed headers.
- Access-Control-Allow-Credentials if cookies are used.
- Access-Control-Expose-Headers if the UI needs to read response headers.
- Whether OPTIONS preflight requests are blocked by security rules before CORS handles them.

CORS does not replace authentication. Allowing an origin to send requests does not mean users are granted access to the API.

## 14. Using Profiles to Disable Swagger UI Where Not Needed

Another option is not enabling the UI or OpenAPI endpoints in production environments:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

You can place this configuration in the production profile if the release workflow does not need to serve documentation directly from the application. OpenAPI artifacts can still be generated in CI and distributed through a controlled documentation repository or developer portal.

Understand the differences:

- api-docs.enabled: false turns off serving OpenAPI documents via Springdoc.
- swagger-ui.enabled: false turns off Swagger UI.
- Security rules protect endpoints that are enabled.
- Disabling documentation does not automatically protect business APIs.

If you disable only Swagger UI while leaving the OpenAPI endpoint active, others can still download JSON/YAML directly. If the goal is not to publish documentation, check both properties and try accessing the URLs after starting the production profile.

## 15. Checking Roles and Authentication Providers

The example hasRole("API_DOCS") checks the authority ROLE_API_DOCS. If the system uses an authority named API_DOCS without a prefix, you can use:

~~~java
.hasAuthority("API_DOCS")
~~~

Do not confuse hasRole with hasAuthority:

| Rule | Checked Authority |
|---|---|
| hasRole("API_DOCS") | ROLE_API_DOCS |
| hasAuthority("API_DOCS") | API_DOCS |

Accounts accessing documentation must be granted the role/authority via UserDetailsService, LDAP, OAuth2 login, a JWT converter, or whichever identity provider the application uses.

When using an OAuth2 Resource Server, tokens must contain a claim/authority mapped to documentation read access. When using OIDC login with sessions, users must be granted the corresponding role. The security chain only checks permissions; it does not create accounts or grant roles on its own.

Do not embed usernames/passwords in application.yml or source code. Use secret management and an identity provider following your organization's operational practices.

## 16. Protecting Swagger UI with Basic Auth or OIDC Login

HTTP Basic can fit simple internal environments, though browsers may cache credentials for the duration of the active session. Use HTTPS and dedicated accounts with least privilege.

In systems with SSO, you can protect documentation pages with OIDC login or centralized login. When doing so, verify:

- Does the Swagger UI page redirect to login properly?
- Do swagger-config and OpenAPI JSON fetches preserve the authenticated session?
- When the session expires, does the UI receive an appropriate status instead of an HTML login page masquerading as JSON?
- Does API Try it out use credentials matching the operation's security scheme?
- Are redirect URIs and cookie policies right for the deployment domain?

An OIDC session used to access documentation pages does not automatically produce an access token with the right scopes for every API. If an operation requires an OAuth2 bearer token, configure the corresponding scheme and authorize flow.

## 17. Common Pitfalls When Protecting Documentation

| Symptom | Causes to Check |
|---|---|
| Swagger UI opens yet OpenAPI JSON returns 401 | Rules or credentials for swagger-config/document do not match |
| /v3/api-docs is locked yet group documents remain public | Matcher covers only the root URL, missing /v3/api-docs/** |
| JSON is protected yet YAML remains public | Did not check YAML endpoint and suffix patterns |
| Swagger UI returns 404 after enabling security | Missing /swagger-ui.html or /swagger-ui/** |
| Browser receives HTML login page instead of JSON | Form login redirect applies to documentation fetch |
| User with role still receives 403 | Authority does not match ROLE_ prefix or token converter |
| API docs are protected yet API operations remain public | Only configured documentation chain, forgot API chain |
| Docs viewer can call APIs beyond their privileges | Backend does not check security scheme/scope or authorization rules |
| Reactive app does not enforce rules | Mistakenly used servlet chain or non-WebFlux matchers |
| A request matches no chain | Missing fallback chain or wrong matcher order |
| Try it out POST receives 403 | Missing CSRF token or blocked CORS preflight |
| UI loads docs yet cross-origin API calls fail | Incorrect CORS, server URL, or credential mode |
| Changed springdoc path yet docs remain publicly open | Security matchers still use default paths |
| Disabled Swagger UI yet JSON is still accessible | Did not disable api-docs or protect OpenAPI endpoint |

When investigating, inspect status codes, redirect chains, response Content-Type, and request paths in the Network tab. Then determine which chain matched and which rule decided access.

## 18. Pre-Release Testing Checklist

Test both authorized and unauthorized users:

| Request | Unauthenticated User | User with API_DOCS Role |
|---|---|---|
| Load Swagger UI entry point | 401/403 or allowed per policy | 200/valid redirect |
| Load UI CSS/JS | 401/403 or allowed per policy | 200 |
| Load swagger-config | 401/403 or allowed per policy | 200 |
| Load OpenAPI JSON | 401/403 or allowed per policy | 200 |
| Load OpenAPI YAML | 401/403 or allowed per policy | 200 |
| Load group documentation | 401/403 or allowed per policy | 200 |
| Call business API | Per API rules | Must still supply API credentials/scopes if required |

Additional tests:

1. Default endpoints and endpoints with changed paths.
2. JSON, YAML, and swagger-config documents.
3. Each document group.
4. Swagger UI entry point and static resources.
5. Public APIs and APIs requiring authentication.
6. User with documentation role but without business scopes.
7. Try it out requests with GET and state-changing requests.
8. CORS preflight when UI is on a different origin.
9. CSRF if the API uses session cookies.
10. Production profile when documentation is disabled.

Use MockMvc for Servlet and WebTestClient for Reactive. Beyond status codes, verify response Content-Type, redirect locations, and JSON contents to catch HTML login pages accidentally returned to OpenAPI clients.

## 19. Spring Security Configuration Principles for Documentation

When protecting Springdoc OpenAPI, apply these principles:

1. Identify the right web stack: Servlet uses SecurityFilterChain, Reactive uses SecurityWebFilterChain.
2. Cover OpenAPI JSON/YAML, group documents, swagger-config, UI entry point, and static resources.
3. Update matchers whenever changing springdoc.api-docs.path or springdoc.swagger-ui.path.
4. Separate documentation viewing access from business API execution access.
5. Use dedicated roles/authorities if documentation is restricted to authorized groups.
6. Keep a fallback security chain for remaining requests.
7. Do not disable CSRF across the entire application just to make Try it out work.
8. Configure CORS according to actual origins and credentials.
9. Use profiles to disable both Swagger UI and OpenAPI endpoints if an environment does not need to serve docs.
10. Test with MockMvc/WebTestClient and the browser Network tab before release.

Springdoc determines which documentation and UI are generated; Spring Security determines who can download them. Configuring properly for Servlet or Reactive protects all documentation paths while keeping business API authentication policies independent. When you verify documentation endpoints, UI assets, and Try it out requests together, development teams avoid locking one part while leaking documentation through another URL.

