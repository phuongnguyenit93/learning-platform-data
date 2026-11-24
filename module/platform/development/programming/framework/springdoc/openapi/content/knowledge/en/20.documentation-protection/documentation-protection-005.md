# Public Documentation vs. Internal-Network-Only Documentation

OpenAPI specifications and Swagger UI help developers understand how to call an API, yet documentation itself is an information surface that requires management. Public documentation can help partners integrate quickly; internal documentation may contain administrative endpoints, operational workflows, private hostnames, schemas, or conventions intended strictly for systems inside the company.

With Spring Boot and springdoc-openapi, you must distinguish three layers: **business APIs**, **OpenAPI JSON/YAML documents**, and the **Swagger UI interface**. Protecting Swagger UI does not automatically protect the specification file; hiding the specification file does not protect business endpoints. Documentation access permissions must be designed separately while accurately reflecting the network boundaries and authentication policies of the deployment environment.

## 1. Public Documentation or Internal-Only Access?

API documentation can be divided by target audience:

| Documentation Type | Audience | Typical Appropriate Content |
|---|---|---|
| Public API docs | External developers, partners, customers | Public endpoints, request/response schemas, authentication flows, limits, errors, and approved examples. |
| Partner docs | Authorized partners | Integration-contract-specific APIs, sandboxes, scopes, quotas, and onboarding guides. |
| Internal docs | Employees, internal services, operations teams | Internal endpoints, administrative APIs, private servers, operational workflows, and inter-service conventions. |
| Restricted/admin docs | Admin or security teams | Sensitive operations, support tools, privileged operational actions, and admin-only endpoints. |

Not every API needs public documentation. The decision should be based on who needs to integrate and how much information the documentation reveals, not merely on whether an endpoint requires login.

### 1.1. What Does Public Documentation Provide?

Public docs are appropriate when an organization wants external developers to discover and integrate with the API independently. Public documentation typically needs:

- Clear base URLs and target environments.
- Authentication schemes and instructions for obtaining credentials.
- Request/response schemas, status codes, and error formats.
- Rate limits, pagination, versioning, and deprecation policies.
- Examples containing no real data or secrets.
- Support contact instructions and terms of use.

An API can still require a token even if its documentation is public. **Public documentation does not mean a public API requires no authentication.** Clients read the contract first, then must still authenticate when calling protected endpoints.

### 1.2. What Information Does Internal Documentation Contain?

Internal docs may describe:

- Endpoints callable only from internal services or private networks.
- Hostnames, ports, routes, or server URLs not exposed to the Internet.
- Administrative, debugging, support, or operational APIs.
- Details of internal scopes, roles, tenants, and authorization provisioning flows.
- Schemas or fields intended solely for inter-service integration.
- Examples containing identifiers, business data, or internal conventions.

Do not assume internal documentation is automatically safe to share across the entire company. Some operations may only be appropriate for operations or security teams. Classify by audience and actual required permissions.

## 2. Three Surfaces to Protect Separately

Springdoc commonly exposes the following URLs (configurable via properties):

| Surface | Common Default URL | Content |
|---|---|---|
| OpenAPI JSON | /v3/api-docs | OpenAPI specification for the default document. |
| Grouped OpenAPI | /v3/api-docs/{group} | Specification of a GroupedOpenApi. |
| OpenAPI YAML | /v3/api-docs.yaml (if YAML endpoint enabled) | Same OpenAPI contract in YAML format. |
| Swagger UI | /swagger-ui.html and /swagger-ui/** | HTML pages, JavaScript, CSS, and UI assets. |
| Swagger UI configuration | /v3/api-docs/swagger-config | Configuration of document URLs that the UI will load. |

Three points to verify:

1. **Swagger UI** is the interface for viewing and trying APIs. If the HTML page is protected while JSON remains public, users can still download the specification directly.
2. **OpenAPI JSON/YAML** contains the entire exported contract. Protecting the UI while forgetting JSON endpoints creates no real access boundary.
3. **Business APIs** still need their own security policies. Disabling or locking documentation does not automatically make business endpoints any safer.

Access flow diagram:

~~~mermaid
flowchart TD
    D[Developer] --> U[Swagger UI]
    D --> J[OpenAPI JSON/YAML]
    U --> J
    D --> A[Business API]
    J --> I[Contract information]
    A --> S[Spring Security / API Gateway]
    I --> P{Documentation policy}
    P -->|Public| PUB[Internet / Developer portal]
    P -->|Internal| VPN[Private ingress / VPN / SSO]
    P -->|Restricted| ADM[Authorized group]
~~~

Swagger UI typically loads JSON from a separate URL. Consequently, if the UI and JSON have different policies, you must test the specification-loading request in the browser, not just the initial UI page.

## 3. Grouping Documentation with GroupedOpenApi

Springdoc lets you split operations into separate documents. For example, public and internal groups:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/public/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/api/internal/**", "/api/admin/**")
                .build();
    }
}
~~~

With this configuration, springdoc can serve separate documents at:

- /v3/api-docs/public
- /v3/api-docs/internal

pathsToMatch selects operations by path for each document. It can be combined with pathsToExclude, packagesToScan, packagesToExclude, or predicates appropriate for your springdoc version.

### 3.1. Groups Are Not an Access Control Mechanism

GroupedOpenApi only splits specification content. It does not enforce authentication, restrict who downloads JSON, or establish a network boundary. If /v3/api-docs/internal remains anonymously accessible, anyone who knows the URL can still retrieve internal documentation.

Likewise, hiding an operation from the public group does not protect the business endpoint. That endpoint must still be controlled by Spring Security or a gateway.

### 3.2. Selecting Public Content via an Allow-List

For public documentation, select explicitly approved paths:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch(
                    "/api/catalog/**",
                    "/api/orders/**"
            )
            .pathsToExclude(
                    "/api/catalog/internal/**",
                    "/api/orders/*/admin/**"
            )
            .build();
}
~~~

An allow-list helps avoid accidentally publishing a new endpoint simply because a controller was added to a shared package. After every path change, inspect the public spec to confirm operations land in the right group.

Do not rely solely on path names like /internal or an Internal tag to protect data. Those are only document selection criteria; authorization must be configured at the access layer.

## 4. Protecting OpenAPI and Swagger UI with Spring Security

If all documentation is strictly for employees, you can require a dedicated authority to access documentation URLs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                "/v3/api-docs",
                                "/v3/api-docs/**",
                                "/v3/api-docs.yaml",
                                "/swagger-ui.html",
                                "/swagger-ui/**"
                        ).hasAuthority("DOCS_READ")
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

In this example, users need the DOCS_READ authority to download OpenAPI JSON, Swagger UI, and Swagger UI configuration. HTTP Basic is merely an easy-to-see example in requests; production can use SSO, OAuth2 Login, Bearer tokens, or whatever authentication mechanism the organization uses.

Check matcher ordering. Specific rules must precede general rules so a broader permitAll() or wider matcher does not grant unintended access.

### 4.1. Public Spec and Internal Spec in the Same Application

If you want the public group downloadable anonymously while the internal group requires dedicated permission, place the specific public matcher before the matcher protecting the rest:

~~~java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            "/v3/api-docs/public",
                            "/v3/api-docs/public/**"
                    ).permitAll()
                    .requestMatchers(
                            "/v3/api-docs",
                            "/v3/api-docs/**",
                            "/v3/api-docs.yaml",
                            "/swagger-ui.html",
                            "/swagger-ui/**"
                    ).hasAuthority("DOCS_READ")
                    .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

With this setup, the public JSON can be downloaded anonymously; other JSON documents and Swagger UI require DOCS_READ. Swagger UI is protected because UI configuration may list internal groups as well. If you want a dedicated public Swagger UI, deploy a UI/config pointing strictly to the public spec, or serve the public UI from a separate portal. Do not expose a shared UI listing internal groups and expect those groups to protect themselves.

Actual URLs may differ when changing springdoc.api-docs.path, context path, servlet path, or Swagger UI path. Adjust matchers to the configured URLs and also verify /v3/api-docs/swagger-config and YAML endpoints if enabled. If public and internal groups share a YAML URL via query parameters or content negotiation, check how the gateway/Spring Security distinguishes audiences; separating hosts or deployments is clearer when path-based authorization is not possible.

### 4.2. Separating Security Chains When Separate Policies Are Needed

Large applications can use multiple SecurityFilterChain beans with @Order and securityMatcher to apply different policies to docs and business APIs. This is useful when documentation uses SSO or separate Basic auth while business APIs use Bearer JWTs.

When using multiple chains:

- A chain with a narrow matcher for docs must have higher priority than the general chain.
- The docs chain must cover JSON, group JSON, swagger config, HTML, and UI assets requiring protection.
- The business API chain must still protect business endpoints.
- Do not let a documentation URL fall into a chain without authorization rules.

Do not create multiple chains just to change one matcher. Keep a simpler configuration if the same authentication mechanism and authority apply to all docs.

## 5. Combining Network Boundaries with Authentication

For internal or restricted documentation, docs can be placed behind one or more layers:

| Layer | Example | Purpose |
|---|---|---|
| Private network | Private subnet, internal load balancer, private DNS | Not directly routable from the Internet. |
| Remote access | VPN or Zero Trust access gateway | Verifies devices/users before entering the internal network. |
| Identity | SSO, OAuth2/OIDC, mTLS | Identifies the person or service. |
| Authorization | Roles/authorities like DOCS_READ, DOCS_ADMIN | Restricts which groups can read documentation. |
| Application | Spring Security or gateway policy | Protects the docs URLs and UI directly. |
| Audit | Access logs, identity, timestamp, request ID | Traces who downloaded documentation and when. |

Network allow-lists or VPNs reduce external reachability but do not replace authorization. A machine already inside the VPN may still belong to a group not authorized to view admin documentation. For sensitive documentation, combine private ingress with authentication and dedicated permissions.

### 5.1. Separating Hostnames or Deployments

A clean design uses separate hosts:

- developer.example.com: developer portal and public API docs.
- api-docs.intra.example: internal docs behind private ingress/SSO.
- admin-docs.intra.example: restricted docs for operations teams.

Separate hosts make DNS, TLS, gateway, logging, and policies independent. They can be deployed alongside the application or split into a portal reading exported OpenAPI artifacts. If sharing the same application, corresponding paths must still be protected in Spring Security or the gateway.

Do not treat an obscure hostname as a security measure. Access permissions must be checked at the network/gateway and application levels.

## 6. Information to Review Before Publishing

Before exporting a public spec, review its content as an artifact that can be downloaded, cached, and committed to source control:

- **Server URLs**: do not expose internal hostnames, IPs, ports, or private routes.
- **Operations**: do not include admin, debug, internal health, or support operations in the public group.
- **Schemas**: remove internal fields, table names, persistence structures, or attributes not meant for clients.
- **Examples**: never use real access tokens, API keys, emails, phone numbers, or customer data.
- **Descriptions**: remove implementation notes, internal service names, infrastructure details, and unapproved information.
- **Security**: accurately describe authentication flows, scopes, and permissions available to external clients.
- **Error responses**: do not publish stack traces, exception classes, SQL, or debugging details.
- **Extensions**: review x-* vendor extensions because they can contain owners, tickets, hostnames, or internal metadata.
- **Links and callbacks**: verify URLs do not point to private systems or test environments.
- **Versioning/deprecation**: publish only approved versions and sunset schedules.

A document containing no secrets can still reveal system architecture, administrative capabilities, or integration points. Evaluate against your threat model and target audience.

## 7. Production Environment Configuration

Not every system needs to serve Swagger UI directly in production. Several options exist:

| Option | Implementation | When Appropriate |
|---|---|---|
| Disable UI, keep protected OpenAPI JSON | springdoc.swagger-ui.enabled=false, keep springdoc.api-docs.enabled=true and apply security | Internal portal or tools need to read the spec without bundling a UI with the service. |
| Disable all runtime docs | Disable springdoc.api-docs.enabled and springdoc.swagger-ui.enabled | Docs are built/exported in a separate pipeline or production needs no docs endpoints. |
| Keep UI and JSON internal | Enable both, place behind SSO/VPN/Spring Security | Internal teams need to test APIs from the production environment. |
| Publish static public artifacts | Export reviewed OpenAPI and publish to a developer portal | Public docs require versioning, approval, and caching independent of the app. |

Example disabling runtime docs in the production profile:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

These two flags turn off documentation endpoints provided by springdoc; they do not disable or protect business APIs. If internal docs are needed in production, do not enable this turn-off setting for that profile; instead keep docs active and lock down access properly.

### 7.1. Do Not Confuse Actuator with OpenAPI Documentation

Spring Boot Actuator exposes management/observability endpoints such as health, info, metrics, env, or mappings depending on configuration. This is a separate surface from /v3/api-docs and Swagger UI. Do not open all of Actuator just to make a health check public.

If springdoc integration is enabled to include Actuator endpoints in documentation, distinguish between:

- Actuator operations appearing in OpenAPI.
- Actuator endpoints being reachable at runtime.
- Who is allowed to download the documentation describing those endpoints.

Each layer needs its own policy. Sensitive endpoints such as env, configprops, beans, mappings, or shutdown (if present) must be evaluated and protected via Actuator configuration, not merely hidden from Swagger UI.

## 8. Exporting and Publishing OpenAPI Artifacts

For public docs, you can decouple documentation generation time from service runtime:

1. Build the application or start a test environment with the appropriate configuration.
2. Fetch OpenAPI JSON from /v3/api-docs or each group.
3. Validate schemas and inspect $ref, security, server URLs, and examples.
4. Review public/internal classification and sensitive information.
5. Save the artifact by version, e.g., openapi-public-1.4.0.json.
6. Publish to the configured developer portal or static hosting.

This approach allows public docs to be reviewed before release without opening documentation endpoints on production services. For internal docs, artifacts can be stored in an internal registry/repository with access control.

### 8.1. Artifact Versioning

Assign clear versions and keep change history:

- Include the API version in info.version or follow an artifact versioning convention.
- Do not overwrite old artifacts if clients still depend on them.
- Record the commit/build number that generated the spec.
- Review breaking changes before publishing.
- Set deprecation and sunset dates when older APIs are retired.
- Keep public and internal artifacts in repositories or permission scopes suited to each audience.

OpenAPI artifacts can be shared independently of the service. Thus, permission to download an artifact and permission to access API endpoints are two separate decisions.

## 9. Caching, Indexing, and Documentation URLs

Public documentation can be cached on a CDN or static hosting. This speeds up loading but requires cache invalidation when releasing new versions. Internal documentation should generally not be cached by shared proxies unless cache keys vary by identity.

For sensitive documentation:

- Consider Cache-Control: private, no-store on docs responses to prevent browser/shared caching.
- Do not include internal docs URLs in public sitemaps.
- X-Robots-Tag: noindex, nofollow can instruct crawlers not to index; this is not an authorization measure.
- Do not rely on robots.txt, obscure URLs, or hidden UI pages to protect JSON.
- Inspect redirects and CDN origins to prevent public caches from accidentally storing internal versions.

For public docs, caching policies can use public, max-age=... or immutable versioned URLs. Choose TTLs matching your release and rollback process.

## 10. Testing Documentation Access Permissions

Security tests should verify JSON, Swagger UI, swagger-config, and each group:

| Request | Identity | Example Expected Outcome |
|---|---|---|
| GET /v3/api-docs/public | Anonymous | 200 if the public spec is permitted publicly. |
| GET /v3/api-docs/internal | Anonymous | 401 or 403 per authentication entry point/policy. |
| GET /v3/api-docs/internal | Has DOCS_READ | 200. |
| GET /swagger-ui.html | Anonymous | Blocked if the UI lists internal docs. |
| GET /v3/api-docs/swagger-config | Anonymous | Blocked if config contains internal URLs. |
| GET /api/admin/** | Anonymous or regular user | Blocked per business security policy, regardless of whether docs are disabled. |

MockMvc example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentationAccessTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsAnonymousAccessToPublicSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
                .andExpect(status().isOk());
    }

    @Test
    void deniesAnonymousAccessToInternalSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "DOCS_READ")
    void allowsAuthorizedUserToReadInternalSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal"))
                .andExpect(status().isOk());
    }
}
~~~

The example assumes the configuration uses an authentication entry point returning 401 for anonymous users. If the application redirects to a login page or returns 403, adjust assertions to match the real contract. Tests should also run against the project's actual created groups and docs endpoints.

### 10.1. Checking Public Spec Contents

Beyond authorization, verify the public artifact contains no internal paths:

~~~java
@Test
void publicSpecificationDoesNotExposeInternalOperations() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/internal/health']").doesNotExist())
            .andExpect(jsonPath("$.paths['/api/admin/reindex']").doesNotExist());
}
~~~

In real tests, replace the two illustrative paths with the application's actual internal paths. You can parse the JSON and assert the set of allowed paths to verify the allow-list generally.

## 11. Common Pitfalls

- **Locking only Swagger UI while leaving /v3/api-docs public**: users can still download the spec directly.
- **Locking only JSON while forgetting swagger-config or UI assets**: the UI may expose group lists or fail policy checks.
- **Assuming GroupedOpenApi is access control**: groups only filter content, they do not authenticate callers.
- **Assuming disabling docs protects the API**: business endpoints still require security policies.
- **Sharing one Swagger UI for both public and internal docs**: config may list internal groups; protect the UI or split UI/config by audience.
- **Relying solely on VPN or IP allow-lists**: users inside the network still need appropriate roles/authorities.
- **Publishing private server URLs**: external clients cannot reach them and may learn internal structure.
- **Putting real data into examples**: specs may be saved or shared unexpectedly.
- **Opening all of Actuator**: management/observability endpoints have separate policies.
- **Using robots.txt or obscure URLs as security**: crawler policies do not prevent direct access.
- **Failing to check CDN caching**: internal artifacts can end up stored in shared caches.
- **Not testing docs paths after changing context path**: security matchers may miss the new URLs.

## 12. Workflow for Choosing a Documentation Policy

1. **Classify the audience**: public, partner, internal, or restricted.
2. **Select operations**: create an allow-list for the public group and dedicated groups for internal ones.
3. **Review content**: server URLs, schemas, examples, extensions, security, and error details.
4. **Choose distribution**: runtime endpoints, a private portal, or reviewed static artifacts.
5. **Establish network boundaries**: public ingress, private ingress, VPN, or Zero Trust gateway per audience.
6. **Configure authentication/authorization**: dedicated roles or authorities for docs.
7. **Protect all URLs**: OpenAPI JSON, group JSON, Swagger UI, assets, and swagger-config.
8. **Separate Actuator policy**: do not let documentation rules widen access to management endpoints.
9. **Configure caching and auditing**: verify CDN, Cache-Control, and access logs.
10. **Test**: anonymous callers, internal users, under-privileged users, and public spec contents.

## 13. Review Checklist

- [ ] Audiences for public, partner, internal, and restricted docs are defined.
- [ ] Public group contains only approved operations.
- [ ] Internal groups cannot be downloaded anonymously.
- [ ] Swagger UI and swagger-config have policies matching the groups they list.
- [ ] OpenAPI JSON/YAML is protected independently of the UI.
- [ ] Business APIs still have their own security policies.
- [ ] Network boundaries are combined with authentication and authorization.
- [ ] Server URLs, schemas, examples, descriptions, and extensions have been reviewed.
- [ ] Actuator endpoints have separate policies.
- [ ] Static artifacts have proper versioning, review, and access control.
- [ ] Caches/CDNs do not leak internal documentation.
- [ ] Tests cover anonymous, authorized, unauthorized access, and the public content allow-list.

## 14. References

- [springdoc-openapi documentation](https://springdoc.org/)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [OpenAPI Specification 3.1.2](https://spec.openapis.org/oas/v3.1.2.html)
- [MDN – HTTP Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control)
- [Google Search Central – Robots meta tag and X-Robots-Tag](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag)

Public and internal documentation should have clear audiences, content, and access policies. GroupedOpenApi helps split contracts; Spring Security and gateways control who can download JSON/UI; private ingress restricts network routes; review and versioning workflows govern published content. Protecting all of these layers gives developers the documentation they need without accidentally exposing internal-only structure and operations.
