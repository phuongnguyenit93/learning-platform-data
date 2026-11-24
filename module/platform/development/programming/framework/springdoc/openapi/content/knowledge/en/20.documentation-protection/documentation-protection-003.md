# Protecting Specification Endpoints by Group

A Spring Boot application can publish multiple OpenAPI documents: public documentation for partners, internal documentation for development teams, and admin documentation for operations. Each group has its own URL, yet if all `/v3/api-docs/**` endpoints are left publicly open, outsiders can still download internal documents by calling a group's URL directly.

`GroupedOpenApi` only decides which operations appear in each document. It does not check whether the caller has permission to download the document. To restrict read access by group, you must protect the documentation endpoints with Spring Security, a gateway, or a reverse proxy. Protection rules must cover both JSON and YAML while also accounting for the `swagger-config` endpoint that Swagger UI uses to discover documents.

## 1. Endpoints That Need Protection

With default springdoc settings, common URLs include:

| Endpoint | Purpose |
| --- | --- |
| `/v3/api-docs` | Default OpenAPI JSON. |
| `/v3/api-docs.yaml` | Default OpenAPI YAML. |
| `/v3/api-docs/{group}` | OpenAPI JSON of a group. |
| `/v3/api-docs/{group}.yaml` | OpenAPI YAML of a group. |
| `/v3/api-docs/swagger-config` | Configuration used by Swagger UI to discover document URLs and UI options. |
| `/swagger-ui.html` | Swagger UI entry point. |
| `/swagger-ui/**` | HTML, JavaScript, CSS, fonts, and static UI resources. |

Example with two groups:

- `public-v1`: `/v3/api-docs/public-v1` and `/v3/api-docs/public-v1.yaml`.
- `internal-v1`: `/v3/api-docs/internal-v1` and `/v3/api-docs/internal-v1.yaml`.

If the application configures `springdoc.api-docs.path`, such as changing it to `/api-docs`, use the new base path in all security matchers. Context paths or reverse proxy prefixes must also be accounted for when checking public URLs.

## 2. Distinguishing Documentation Filtering from Endpoint Protection

A group configuration may include only public controllers in its document:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
        .group("internal-v1")
        .pathsToMatch("/api/internal/**")
        .build();
}
```

The two beans above generate two different OpenAPI documents. They do not create access rules for `/v3/api-docs/public-v1` or `/v3/api-docs/internal-v1`.

Similarly, annotations such as `@SecurityScheme`, `@SecurityRequirement`, and `@SecurityRequirements` describe an operation's authentication mechanism in the OpenAPI contract. They do not automatically protect the endpoint serving the documentation. To allow only administrators to download internal documentation, you need runtime rules such as `hasRole(...)`, `hasAuthority(...)`, or equivalent gateway policies.

## 3. Protecting All Documentation Endpoints

The `SecurityFilterChain` snippets in this article represent alternative configuration approaches. In a single application, choose and combine rules into an appropriate configuration; do not declare multiple beans with overlapping matchers unless they are separated into chains with explicit `securityMatcher` and `@Order`.

If all documentation is strictly for logged-in users, you can protect the entire API docs base path:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/v3/api-docs/**", "/v3/api-docs.yaml")
                .hasRole("DOCS_READER")
            .requestMatchers("/swagger-ui.html", "/swagger-ui/**")
                .hasRole("DOCS_READER")
            .anyRequest().authenticated()
        )
        .build();
}
```

In this example, users need the `ROLE_DOCS_READER` authority to load JSON/YAML, `swagger-config`, and UI resources. `hasRole("DOCS_READER")` automatically adds the `ROLE_` prefix; if the application uses differently named authorities, you can use `hasAuthority("docs.read")`.

If you want the UI to load while requiring authentication for document contents, you can allow static assets and protect the docs endpoints:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/swagger-ui.html", "/swagger-ui/**").permitAll()
            .requestMatchers("/v3/api-docs/**", "/v3/api-docs.yaml")
                .hasAuthority("docs.read")
            .anyRequest().authenticated()
        )
        .build();
}
```

Note: in the second configuration, the UI page can be opened, but Swagger UI still cannot load the documentation if the browser lacks valid authentication credentials. Permitting HTML/JavaScript does not mean permitting `swagger-config` or OpenAPI JSON.

## 4. Per-Group Authorization

When public and internal documentation target different audiences, declare specific matchers before general matchers:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            // swagger-config is handled separately before group matchers.
            .requestMatchers(HttpMethod.GET, "/v3/api-docs/swagger-config")
                .permitAll()

            // Only users authorized to read internal docs can download this group.
            .requestMatchers(HttpMethod.GET,
                "/v3/api-docs/internal-v1",
                "/v3/api-docs/internal-v1.yaml")
                .hasAuthority("docs.internal.read")

            // Public documentation allows anonymous downloads.
            .requestMatchers(HttpMethod.GET,
                "/v3/api-docs/public-v1",
                "/v3/api-docs/public-v1.yaml")
                .permitAll()

            // The default document is not published in this example.
            .requestMatchers(HttpMethod.GET,
                "/v3/api-docs",
                "/v3/api-docs.yaml")
                .denyAll()

            // Any other docs paths are denied unless given an explicit rule.
            .requestMatchers("/v3/api-docs/**").denyAll()
            .anyRequest().authenticated()
        )
        .build();
}
```

Matcher ordering is critical: Spring Security applies the first rule matching the request. Because `swagger-config` sits under `/v3/api-docs/`, its dedicated rule must come before the broad `/v3/api-docs/**` matcher. If the broad matcher appears first, subsequent specific rules will not be applied.

The example uses `hasAuthority("docs.internal.read")` to illustrate internal documentation read permission. This authority can be mapped from JWT claims, LDAP, a database, or your organization's authorization system. When using an OAuth2 Resource Server with scopes, authorities typically take the form `SCOPE_docs.internal.read`; the matcher must then use the exact authority name produced by the converter.

The matchers in the example restrict HTTP GET because documentation endpoints are read via GET. If the application has custom matchers or filters for other methods, ensure unwanted requests to the docs base path remain denied.

## 5. Why `swagger-config` Must Be Handled Separately

Swagger UI typically loads `/v3/api-docs/swagger-config` first, then fetches the document URLs listed in that configuration. This endpoint can contain the list of document groups, such as `public-v1` and `internal-v1`.

If `swagger-config` is publicly open while internal documentation is protected, outsiders can still learn the group names and URLs of internal docs, though they still have to pass security rules to download the content. Exposing group names can leak part of the system's structure; if you do not want to publish that information, restrict the group list in the public Swagger UI configuration or protect `swagger-config` as well.

Example publishing only the public group in a Swagger UI aimed at external users:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-v1
    urls-primary-name: Public API
    disable-swagger-default-url: true
```

The `urls` list ensures the public UI displays only the `public-v1` document. The `internal-v1` endpoint still needs its own protection rule because users can call that URL directly. Hiding an option from the UI is not an access control measure.

If an internal UI is needed, you can provide a separate Swagger UI configuration for authenticated users or deploy a standalone internal documentation page. In all cases, the server-side documentation endpoints must still be protected.

## 6. Authentication for Documentation Consumers

Choose an authentication mechanism that fits how users access Swagger UI:

| Mechanism | How It Works | Notes for Swagger UI Usage |
| --- | --- | --- |
| Session/cookie | Users log in to the app or internal portal; the browser sends cookies when loading docs | Suitable for same-origin UI; check cookies, SameSite, Secure, and CSRF per configuration. |
| HTTP Basic | Browser or client sends Basic Auth credentials | Suitable for internal docs over HTTPS; do not use weak passwords or send over HTTP. |
| Bearer token | Client sends `Authorization: Bearer ...` | Requires a way to supply the token for `swagger-config` and OpenAPI document requests. The API's Authorize button might not cover the initial document fetch. |
| Gateway/SSO | Reverse proxy or auth gateway protects docs paths | Useful when docs share enterprise login; forward identity/permissions reliably. |

A common point of confusion: security schemes in OpenAPI are usually used by Swagger UI for **Try it out** requests. They do not automatically protect requests loading `swagger-config` and OpenAPI documents. If those document-loading requests themselves require a bearer token, you must configure authentication for them independently; do not assume the **Authorize** button is already visible and used before the document loads.

For internal UIs using sessions, ensure the browser sends cookies to docs endpoints and responses are not blocked by CORS. For cross-origin UIs, configure CORS and credentials accurately. Never put client secrets or static tokens into JavaScript, YAML files, or publicly served Swagger UI configuration.

## 7. Customizing the OpenAPI Base Path

If you change the specification endpoint:

```yaml
springdoc:
  api-docs:
    path: /api-docs
```

Matchers must be updated accordingly, for example:

```java
.requestMatchers(HttpMethod.GET,
    "/api-docs/internal-v1",
    "/api-docs/internal-v1.yaml")
    .hasAuthority("docs.internal.read")
.requestMatchers(HttpMethod.GET,
    "/api-docs/public-v1",
    "/api-docs/public-v1.yaml")
    .permitAll()
.requestMatchers("/api-docs/**").denyAll()
```

If the application has a context path such as `/service`, the external URL may be `/service/api-docs/internal-v1`. How matchers receive paths depends on context path placement and Spring Security configuration; matchers typically operate on the path inside the application and do not automatically include the context path. Test actual requests and your Spring Security version's matchers instead of mechanically adding prefixes.

When running behind a reverse proxy, ensure the proxy forwards requests to the right application and does not create another public route that bypasses the security filter chain. If the gateway has its own rules, access permissions must be enforced consistently at both the gateway and the application.

## 8. Protecting Swagger UI and Static Resources

There are two independent decisions:

- Who can open the Swagger UI interface?
- Who can download each OpenAPI document?

If internal docs are for employees only, it is usually best to protect the UI page, static assets, `swagger-config`, and all documents together. If a public UI displays only a public group, you can keep the UI open while protecting internal documents with dedicated matchers.

Do not open all of `/v3/api-docs/**` just because `/swagger-ui.html` needs to load resources. Conversely, do not lock down JavaScript/CSS assets with a rule that prevents users from loading the page and still expect the UI to work.

If Swagger UI is not needed in production, disable the UI with configuration or omit the UI starter dependency. If you do not want to expose OpenAPI endpoints in production, disable the docs endpoint with `springdoc.api-docs.enabled=false` for that profile. Disabling docs is a deployment decision; it does not replace protecting business endpoints.

## 9. Testing Per-Group Access Permissions

At least three scenarios should be tested for each protected document:

1. Unauthenticated callers requesting internal documentation must be denied.
2. Authenticated users lacking the docs-reading authority must be denied.
3. Users with the proper authority must be able to download both JSON and YAML.

MockMvc example:

```java
@SpringBootTest
@AutoConfigureMockMvc
class DocumentationProtectionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadInternalDocs() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadInternalYaml() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void authenticatedUserWithoutDocsAuthorityIsForbidden() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "docs.internal.read")
    void authorizedUserCanReadInternalJson() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists());
    }

    @Test
    @WithMockUser(authorities = "docs.internal.read")
    void authorizedUserCanReadInternalYaml() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
            .andExpect(status().isOk());
    }

    @Test
    void publicDocsRemainAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists());
    }
}
```

The example assumes the application configures an entry point that returns `401` when unauthenticated. Some applications redirect to a login page or return a different status; verify against the actual policy. Also include tests for authenticated users lacking the authority to confirm `403`.

If `swagger-config` is public, verify its response does not accidentally expose internal group names outside policy. If it is protected, verify authorized users can fetch the config and Swagger UI works with the chosen login mechanism.

## 10. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Internal group can be downloaded without logging in | Filtered only via `GroupedOpenApi`, docs URLs unprotected | Add runtime matchers for the group's JSON and YAML. |
| JSON is blocked but YAML can still be downloaded | Matcher covers only the URL without the `.yaml` suffix | Add the YAML route to the same rule and test both. |
| Group protection rule has no effect | General matcher appears before specific matcher | Place specific group rules before `/v3/api-docs/**`. |
| `swagger-config` is unexpectedly blocked | Broad matcher catches config endpoint before its dedicated rule | Place the `swagger-config` matcher before group or general matchers. |
| UI opens but reports an error loading API definition | UI assets are public while docs/config require login | Configure browser auth for docs/config or protect the entire UI via session/SSO. |
| Public UI still lists internal group names | `swagger-config` exposes all registered groups | Configure a dedicated public `springdoc.swagger-ui.urls` list or protect config. |
| Group hidden in Swagger UI yet direct URL still accessible | Only hid the option in the UI, no security rule | Protect docs endpoints in Spring Security/gateway. |
| User with token still cannot load docs | Token lacks required authority or docs fetch does not send token | Check authority mapping and document-fetching auth mechanism. |
| Custom auth filter blocks public endpoints | Filter rejects requests before authorization rules | Configure the filter to skip public paths or handle credentials as designed. |
| Changed `springdoc.api-docs.path` yet docs return `404`/remain unprotected | Security matchers and proxy still use old path | Synchronize springdoc config, matchers, gateway, and Swagger UI URLs. |
| Test expects `401` but receives `302` | Entry point redirects to login page | Align assertions with the application's authentication policy. |

## 11. Implementation Checklist

Before publishing grouped documentation, verify:

- Group IDs have stable names and JSON/YAML URLs are identified.
- Public and internal documentation have separate access rules.
- Specific matchers come before general matchers.
- The `swagger-config` endpoint is protected or lists only approved public groups.
- Swagger UI and static assets have an appropriate access policy.
- Session, Basic Auth, bearer token, or SSO fits how the browser loads documentation.
- Base path, context path, and reverse proxy align with actual matchers.
- Tests verify anonymous, authenticated-without-authority, and authorized access for both JSON and YAML.
- Group documents contain no secrets, tokens, passwords, or sensitive environment data.
- If docs are not needed in production, consider disabling OpenAPI endpoints or omitting Swagger UI in that profile.

## 12. Guiding Principles

- Use `GroupedOpenApi` to split documentation content and Spring Security/gateway to control who can download it.
- Protect both JSON and YAML for each group.
- Place matchers for `swagger-config` and specific groups before the general `/v3/api-docs/**` matcher.
- Open publicly only those groups intended for publication; deny remaining groups by default.
- Remember that `swagger-config` can expose group names and URLs even when the documents themselves are protected.
- Do not treat hiding a group from Swagger UI as a security measure.
- Choose an authentication mechanism the browser can use immediately when loading configuration and OpenAPI documents.
- Keep `springdoc.api-docs.path`, context path, reverse proxy, and security matchers synchronized.
- Test direct access to JSON/YAML URLs, not just through Swagger UI.

Protecting grouped specification endpoints requires two coordinated configurations: springdoc generates separate documents by group ID, while Spring Security or the gateway decides who may download each document. When JSON, YAML, and `swagger-config` are properly protected and URLs are tested directly across roles, public documentation can be distributed smoothly while internal documentation remains behind access controls.

## References

- [Springdoc OpenAPI – official documentation](https://springdoc.org/)
- [Springdoc OpenAPI FAQ – GroupedOpenApi and Swagger UI](https://springdoc.org/faq.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OpenAPI Specification – Security Requirements](https://spec.openapis.org/oas/latest.html)
