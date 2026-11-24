# Verifying Access Policies After Actual Deployment

After deploying springdoc-openapi, you must verify that real users can only access Swagger UI and OpenAPI documentation according to the designed policy. Configuration in source code is not enough to prove documentation is protected: a reverse proxy may expose another path, a document group may be missed in security matchers, or a CDN may serve cached content.

Verification must cover the entire documentation surface: the Swagger UI page, static UI assets, default OpenAPI JSON/YAML, each group's documentation, and any customized URLs. Test with unauthenticated users, authenticated users lacking permissions, and users with appropriate permissions.

## 1. Defining the Intended Access Policy

Before testing, clearly write down which documentation is public and who is allowed to read it. There is no single policy suitable for every application.

| Documentation Type | Typical Policy | How to Verify |
|---|---|---|
| Public API | Anyone can read the specification | Access from an anonymous session and external network |
| Internal API | Only employees or internal network can access | Test from external network and non-member accounts |
| Partner API | Only authorized partner accounts | Test with a valid partner account and other accounts |
| Admin API | Only operations or admin teams can read | Test regular users, role-lacking users, and admins |
| Disabled documentation | Do not expose Swagger UI or OpenAPI in that environment | Verify endpoints return 404 or response matching disabled config |

Define UI access permissions separately from OpenAPI document download permissions. Someone may be allowed to view an introductory page without being allowed to download internal documentation; another system may require the exact same permission for both UI and JSON.

Do not treat obscure URLs, robots.txt, CORS, or hiding Swagger UI buttons as authorization mechanisms. Users can still call documentation endpoints directly if the server permits it.

## 2. Listing All Endpoints That Need Protection

With default springdoc settings, common URLs include:

| Component | Default URL |
|---|---|
| Default OpenAPI document | /v3/api-docs |
| OpenAPI document in YAML format | /v3/api-docs.yaml |
| Document group | /v3/api-docs/{group} |
| Swagger UI page | /swagger-ui.html |
| Swagger UI resources | /swagger-ui/** |

If there are multiple groups, such as public, partner, and internal, check each group URL. Protecting /v3/api-docs while omitting /v3/api-docs/{group} can leave group documents accessible.

Paths can change via configuration:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /docs
~~~

When paths change, security matchers, proxy rules, firewalls, and test scripts must all be updated. Do not assume endpoints remain at default paths.

Beyond the URLs above, check each group's JSON/YAML endpoints, the redirect target from /swagger-ui.html to UI assets, the Swagger UI configuration file, URLs configured in springdoc.swagger-ui.url or urls, URLs exposed by an API gateway after path rewriting, and documentation endpoints on the management port if configured separately.

Build your URL list from the actual deployment configuration and use that list as the baseline for checks. Never test a single UI page and conclude all documentation is protected.

## 3. Understanding HTTP Outcomes During Permission Checks

Response codes typically indicate which policy is being enforced:

| Outcome | Common Meaning | What to Verify |
|---|---|---|
| 200 OK | Request accepted | Does the content match the expected document and target audience? |
| 302 Found or equivalent redirect | Redirects to login page or another URL | Does the redirect match SSO flow without leaking internal paths? |
| 401 Unauthorized | No valid authentication credentials | Is an appropriate WWW-Authenticate header sent for HTTP auth? |
| 403 Forbidden | Authenticated yet insufficient permissions, or denied by policy | Are users lacking authority/role blocked properly? |
| 404 Not Found | Endpoint does not exist or is intentionally hidden | Is documentation truly disabled or is a path misconfigured? |
| 5xx | Application, proxy, or upstream error | Inspect logs and service health |

Status codes depend on the authentication mechanism. With HTTP Basic or Bearer tokens, unauthenticated requests typically receive 401. With form login or SSO, browsers may be redirected to a login page. Authenticated users lacking permissions typically receive 403.

Do not judge policies by status code alone. For example, 200 might return an HTML login page instead of OpenAPI JSON; 302 might send users to an unexpected host. Check Content-Type, Location, and response bodies as well.

## 4. Protecting Documentation with Spring Security

The example below uses HTTP Basic and the DOCS_READ authority to restrict documentation. Real accounts should be managed through an identity system or user store appropriate for the environment:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain documentationSecurity(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher(
                "/v3/api-docs",
                "/v3/api-docs/**",
                "/v3/api-docs.yaml",
                "/swagger-ui.html",
                "/swagger-ui/**"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasAuthority("DOCS_READ")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This example illustrates two security filter chains. The first chain applies only to documentation URLs; the second chain handles remaining requests. @Order and securityMatcher must be configured consistently so documentation requests do not fall into a less restrictive chain.

If using hasRole("API_DOCS"), Spring Security typically checks authority ROLE_API_DOCS. If using hasAuthority("DOCS_READ"), the authority name must match exactly. Never grant documentation read permissions to every account just so Swagger UI works.

In systems using form login, OAuth2 Login, SSO, or JWT, replace HTTP Basic with the corresponding authentication mechanism. Authorization policies for documentation URLs must still be applied explicitly.

## 5. Protecting Document Groups

The /v3/api-docs/{group} endpoint is also a document that can contain schemas, endpoints, and dedicated metadata. Verify every group falls inside the intended protection boundary.

For example, restricting internal docs with a separate authority:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/v3/api-docs/internal",
        "/v3/api-docs/internal/**"
    ).hasAuthority("INTERNAL_DOCS_READ")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml",
        "/swagger-ui.html",
        "/swagger-ui/**"
    ).hasAuthority("DOCS_READ")
);
~~~

Place specific matchers before general matchers so sensitive groups are not matched by a broader rule first. When using multiple SecurityFilterChain beans, verify chain order and chain-level matchers; matcher ordering inside one chain cannot fix a request already claimed by an earlier chain.

If Swagger UI displays a list of multiple documents, users may see group names even if they lack permission to download those groups' contents. Consider including only permitted groups in springdoc.swagger-ui.urls, or applying login and authorization consistently to both the list and each document.

Do not rely on removing a group from the dropdown to protect its content. If the group URL is still served, users can call that URL directly.

## 6. Authorization by Role or Scope

You can authorize by user role:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/swagger-ui.html", "/swagger-ui/**")
        .hasRole("API_DOCS")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasRole("API_DOCS")
    .anyRequest().authenticated()
);
~~~

Or use scopes in access tokens when documentation is protected by an OAuth2 Resource Server:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers(
            "/v3/api-docs",
            "/v3/api-docs/**",
            "/v3/api-docs.yaml",
            "/swagger-ui.html",
            "/swagger-ui/**"
        ).hasAuthority("SCOPE_api.docs.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(resourceServer -> resourceServer
        .jwt(Customizer.withDefaults())
    );
~~~

The example authority must be mapped from actual claims or scopes in the token. Verify issuer, audience, signature, expiration, and how Spring Security maps scopes before using this rule.

One important caveat with Swagger UI: the UI usually needs to load the OpenAPI document before rendering operations and the Authorize button. If the JSON document itself accepts only Bearer tokens while the UI has no way to obtain and send a token prior to loading the spec, users can hit a circular dependency: needing the spec to log in, yet needing to log in to load the spec. For interactive UIs, consider session/SSO or a suitable browser authentication mechanism; never embed a static access token in UI configuration to work around this.

## 7. Checking Matchers and Filter Chain Ordering

An authorization configuration can look right yet fail to protect endpoints if requests are handled by a different chain.

Items to verify:

1. Does the documentation chain's securityMatcher cover every actual URL?
2. Does the documentation chain have the right @Order priority relative to the general chain?
3. Does an earlier chain match requests and apply permitAll()?
4. Do specific matchers for internal groups precede general matchers?
5. Are URLs behind a reverse proxy rewritten before Spring Security receives the request?
6. When springdoc.api-docs.path or springdoc.swagger-ui.path changes, are matchers updated?
7. Is any web.ignoring() or bypass filter accidentally skipping protection?

Never use web.ignoring() for documentation requiring authorization. Bypassing security filters can leave endpoints without expected authentication and authorization. For resources meant to be public, use permitAll() inside an appropriate chain so baseline security filters remain active.

## 8. Checking Behind a Reverse Proxy or API Gateway

In production, clients typically connect through a domain or gateway rather than calling the Spring Boot port directly. The gateway can perform an authentication layer, rewrite paths, or cache responses. Therefore, test through the exact public URLs users access.

~~~text
Client
  |
  v
https://api.example.com/docs
  |
  v
Reverse proxy / API gateway
  |
  | rewrite /docs to /swagger-ui.html
  | forward identity headers (if any)
  v
Spring Boot + Spring Security + springdoc
  |
  +--> Swagger UI
  +--> /v3/api-docs
  +--> /v3/api-docs/{group}
~~~

Verify:

- The gateway does not publicly expose an internal documentation path.
- Rewrite rules do not bypass authentication middleware.
- User identity headers are trusted only when the gateway strips forged headers from clients and sets them itself.
- Spring Boot cannot be reached directly from external networks to bypass the gateway when architecture requires all traffic to flow through the gateway.
- X-Forwarded-* or Forwarded headers are processed properly so URLs published in OpenAPI match the public domain.
- Gateways and CDNs do not cache access-controlled documentation responses as shared content for unauthenticated users.

If the gateway authenticates users and passes identity headers to the application, restrict backend connectivity so only the trusted gateway can send those headers. If clients can send X-User, X-Roles, or similar headers directly to the backend, they can spoof identities.

## 9. Checking Caching and Content Delivery

OpenAPI JSON/YAML can reveal internal endpoints, schema names, data models, and deployment details. For access-controlled documentation, ensure proxies, CDNs, and browsers do not share responses across users or environments.

Inspect headers:

- Cache-Control: cache policy suited to sensitivity and authentication mechanism.
- Vary: if responses depend on auth headers or cookies, caches must differentiate contexts properly.
- Age or CDN-specific headers: help detect whether responses came from cache.
- Via or gateway headers: help identify which layer served the response.

For sensitive documentation, consider Cache-Control: private, no-store or an equivalent policy per security requirements. Do not check headers only on the application directly; call through the production domain to confirm the gateway/CDN does not override the policy.

When switching documentation from private to public or vice versa, purge old caches and audit distributed copies. Removing a path at the origin does not clear content already cached by a CDN.

## 10. Checking CSRF, CORS, and Browser Authentication

Swagger UI typically loads documentation with GET requests. These read requests normally do not require a CSRF token. However, Try it out can send POST, PUT, PATCH, or DELETE to APIs; if the application uses cookie/session authentication, state-changing requests still require an appropriate CSRF policy.

Never disable CSRF globally just to make Swagger UI work. Identify which requests use cookies and which use Bearer tokens, then apply policies matching each authentication mechanism.

CORS only controls whether browsers allow JavaScript to read cross-origin responses. CORS does not replace authentication or authorization. If Swagger UI and the API share the same origin, separate CORS rules are typically unnecessary for loading documentation. If they sit on different origins, allow only required origins, methods, and headers.

When testing in a browser, open Developer Tools and inspect the Network tab:

- Does the UI page load HTML, JavaScript, CSS, and config?
- Do requests to OpenAPI JSON/YAML send cookies or tokens properly?
- Do login redirects return to the right page?
- Are there any CORS or mixed-content errors?
- Do Try it out requests carry required CSRF tokens or Authorization headers?
- Do responses accidentally contain tokens, cookies, or credentials in the body?

## 11. Testing with curl from the Deployment Environment

Run checks from a machine or runner able to reach the public domain. The commands below use illustrative URLs.

### 11.1. Unauthenticated Requests

~~~bash
curl -i https://api.example.com/v3/api-docs
curl -i https://api.example.com/v3/api-docs.yaml
curl -i https://api.example.com/swagger-ui.html
curl -i https://api.example.com/swagger-ui/index.html
curl -i https://api.example.com/v3/api-docs/internal
~~~

If policy requires login, these requests must receive a denial or redirect to the designated login mechanism. Never receive 200 with internal documentation simply by trying an alternate path.

### 11.2. Requests with an Authorized Account

With HTTP Basic, let curl prompt for the password instead of putting the password in the command:

~~~bash
curl -i -u docs-reader https://api.example.com/v3/api-docs
~~~

Then test group URLs and Swagger UI with the same account. When using a Bearer token, supply the token via an environment variable in the test shell and avoid saving tokens in script files or command history.

### 11.3. Requests with an Under-Privileged Account

Log in with a valid account lacking documentation-reading authority. The expected result is typically 403. Test internal groups separately to verify an account with only public access cannot read internal documentation.

Do not treat an account's inability to open the UI page as sufficient. Call JSON/YAML endpoints directly because users can bypass the UI.

## 12. Automated Testing with MockMvc

You can use Spring Boot tests to verify policies inside the application. The example below assumes documentation endpoints are protected by the DOCS_READ authority:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentationAccessTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousUserCannotReadOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userWithoutDocumentationAuthorityIsForbidden() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .with(user("ordinary-user")))
            .andExpect(status().isForbidden());
    }

    @Test
    void documentationReaderCanReadOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .with(user("docs-reader")
                    .authorities(new SimpleGrantedAuthority("DOCS_READ"))))
            .andExpect(status().isOk());
    }
}
~~~

The test example assumes HTTP Basic or a mechanism returning 401 for anonymous users. If the application uses form login, the result may be a redirect; adjust assertions to match the chosen policy. Add tests for YAML, Swagger UI, static resources, and each group—not just /v3/api-docs.

These tests use Spring Security request post processors, requiring the spring-security-test dependency in test scope. MockMvc verifies filter chains inside the application. It does not test production gateway, CDN, DNS, or network policies. Therefore, integration testing through the deployment domain is still required.

## 13. Caller and Endpoint Test Matrix

Build a matrix so no scenario is missed:

| Caller | Swagger UI | Default OpenAPI | Public Group | Internal Group |
|---|---|---|---|---|
| Unauthenticated | Per policy | Per policy | Per policy | Per policy |
| Regular user | Denied or UI-only | Denied | Denied or allowed per policy | Denied |
| Partner account | Per partner policy | Per policy | Allowed | Denied |
| Internal employee | Allowed | Allowed | Allowed if granted | Per internal role |
| Administrator | Allowed | Allowed | Allowed | Allowed |

Fill in concrete expected outcomes per system, then record actual HTTP statuses and response bodies for every cell. If policies differ between UI and documents, reflect that clearly in the matrix.

## 14. When You Want to Disable Documentation in Production

If production does not need to publish documentation, disable OpenAPI and Swagger UI endpoints via configuration:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

After deployment, verify that default endpoints and group endpoints no longer serve documentation. Responses are typically 404 or match the application's routing behavior. If documentation still appears, check active profiles, configuration overrides, gateway routes, and the running artifact.

Disabling Swagger UI while leaving OpenAPI JSON active can still expose the entire contract. Conversely, disabling OpenAPI while keeping the UI page can leave the UI unable to load a spec. Decide clearly whether to disable both or only one part.

If operations teams need documentation without exposing it on production instances, deploy an internal portal or a dedicated profile/instance protected by appropriate network and identity policies.

## 15. Distinguishing Documentation Protection from API Protection

Setting security rules on /v3/api-docs/** protects only documentation. It does not automatically protect business endpoints such as /api/orders or /api/admin.

Conversely, protecting APIs with JWTs does not mean Swagger UI and OpenAPI are protected. Both surfaces must be tested independently:

| Surface | Question to Answer |
|---|---|
| Swagger UI | Who is allowed to load the UI page and assets? |
| OpenAPI JSON/YAML | Who is allowed to read schemas, paths, operations, and security metadata? |
| API runtime | Who is allowed to call endpoints and perform actions? |
| Authorization server | Who is allowed to log in, obtain tokens, and request scopes? |
| Gateway/CDN | Who can reach or receive cached content? |

Documentation can expose internal endpoint names, request/response structures, security mechanisms, and business models. Even without real data, this can still be information your organization's policy requires restricting.

## 16. Common Post-Deployment Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Protecting only /swagger-ui.html | JSON/YAML remain publicly accessible | Protect both OpenAPI endpoints and UI resources |
| Omitting /v3/api-docs/{group} | Internal groups remain exposed | Use matchers covering groups and test each group |
| Matchers still use default paths after config change | New endpoints fall outside rules | Sync matchers with springdoc.api-docs.path and swagger-ui.path |
| General chain precedes documentation chain | Documentation requests get handled by another policy | Verify @Order and securityMatcher |
| Using permitAll() for UI assets while forgetting JSON | UI loads yet spec leaks or fails to load | Define separate policies for HTML, assets, and documents |
| Only hiding a group from dropdown | Users still call group URLs directly | Authorize group endpoints on the server |
| Gateway rewrite bypasses authentication | Public URLs skip application policy | Test through the gateway and audit rewrite rules |
| CDN caches private documentation | Unauthenticated users may receive cached copies | Set private/no-store caching and purge caches |
| Using CORS instead of authorization | Non-browser clients can still call endpoints | Enforce authentication and authorization on the server |
| Disabling UI while forgetting OpenAPI JSON | Contract is still published | Disable and test both if production needs no docs |
| Docs require Bearer token yet UI cannot load spec | Circular dependency before Authorize | Use session/SSO or an appropriate spec-loading mechanism |
| Testing only with admin accounts | Fails to detect regular users reading docs | Test anonymous, under-privileged, and authorized users |

## 17. Pre- and Post-Release Verification Workflow

Follow in order:

1. Document public, partner, internal, and admin policies for each document.
2. List UI, assets, JSON, YAML, groups, and customized URLs.
3. Reconcile springdoc.*.path with Spring Security matchers.
4. Check SecurityFilterChain ordering and authorities/roles/scopes.
5. Test anonymous, under-privileged, and authorized users with MockMvc.
6. Deploy to a test environment and call endpoints through the gateway domain.
7. Check redirects, statuses, Content-Type, Location, and response contents.
8. Verify caching, forwarded headers, path rewrites, and gateway bypass resistance.
9. Open Swagger UI in a browser and inspect all requests in the Network panel.
10. Verify each document group via its direct URL.
11. If production does not publish docs, enable disable flags and verify endpoints stop serving.
12. Record test results for comparison after future security or infrastructure changes.

After upgrading Spring Security, springdoc, paths, gateways, or SSO, re-run relevant checks. A change that appears to affect only the UI can alter document URLs or filter chains.

## 18. Key Takeaways

- Define clearly who may read Swagger UI, OpenAPI JSON/YAML, and each document group.
- Protect UI pages, static resources, default endpoints, YAML, and groups.
- Check actual paths after configuring springdoc.api-docs.path or springdoc.swagger-ui.path.
- Verify SecurityFilterChain order, securityMatcher, and role/scope matchers.
- Return 401, 403, redirects, or 404 per policy; inspect both response bodies and headers.
- Test from production domains through reverse proxies/API gateways, not only localhost.
- Check caches/CDNs so private documentation is never shared across users.
- CORS does not replace authentication; never disable CSRF globally just so Swagger UI works.
- MockMvc tests filter chains; supplement with integration tests across deployment infrastructure.
- If not publishing documentation in production, disable both OpenAPI and Swagger UI and verify actual endpoints.
- Protecting documentation does not replace protecting runtime APIs; both surfaces require separate policies and tests.

After deploying springdoc-openapi, verify policies with real requests from multiple account types through the true production path. Conclude documentation is protected only when every UI, JSON/YAML, and document group URL behaves according to the defined permission matrix, including through gateways and caches.
