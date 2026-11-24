# Testing Documentation Groups, Profiles, and Security Configuration

A Spring Boot application can generate multiple OpenAPI documents via `GroupedOpenApi`, toggle documentation by profile, and protect individual URLs with Spring Security. These configuration layers interact simultaneously with specification generation and document retrieval. Consequently, a single test calling `/v3/api-docs` under the default profile is not enough to prove that all groups, environments, and access policies behave accurately.

Contract testing must verify three separate concerns: each group contains the intended operations, each profile loads the right configuration, and documentation endpoints allow access only to authorized callers. Verify JSON, YAML, and `swagger-config` per your deployment policy, while keeping security requirements documented inside OpenAPI distinct from access control on the endpoints serving the documents.

## 1. Defining the Group, Profile, and Access Matrix

Before writing tests, define a matrix of expected behaviors. Example for an application with public and internal documentation:

| Profile | Group | JSON/YAML | Anonymous | Docs-Authorized User |
| --- | --- | --- | --- | --- |
| `local` | `public-v1` | Enabled | Allowed | Allowed |
| `local` | `internal-v1` | Enabled | Denied | Allowed |
| `staging` | `public-v1` | Enabled | Allowed | Allowed |
| `staging` | `internal-v1` | Enabled | Denied | Allowed |
| `prod` | `public-v1` | Enabled per publishing policy | Allowed if public | Allowed |
| `prod` | `internal-v1` | Enabled yet protected, or disabled per policy | Denied | Allowed if retained |

This matrix is an example; your system may pick a different policy. What matters is stating expectations explicitly for every combination. If production disables API docs completely, tests must assert that disabled behavior rather than trying to fetch docs as in staging.

Questions to answer before implementing tests:

- Which group IDs exist in each profile?
- Which paths and HTTP methods is each group allowed to include?
- Which JSON and YAML endpoints are enabled?
- Who is allowed to fetch each document?
- Which groups does `swagger-config` advertise and who may read it?
- Is Swagger UI enabled in that profile?

## 2. Configuring Two Documentation Groups

Example path-based group configuration:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

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
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/public/**")
            .build();
    }
}
```

With the default base path, the corresponding endpoints are:

| Artifact | URL |
| --- | --- |
| Public JSON | `/v3/api-docs/public-v1` |
| Public YAML | `/v3/api-docs/public-v1.yaml` |
| Internal JSON | `/v3/api-docs/internal-v1` |
| Internal YAML | `/v3/api-docs/internal-v1.yaml` |
| Swagger UI config | `/v3/api-docs/swagger-config` |

If `springdoc.api-docs.path` is customized, update the base path in tests. If the application uses a context path or reverse proxy prefix, internal tests usually target the in-app path while post-deployment smoke tests target the real public URL.

`GroupedOpenApi` filters document contents. It does not secure JSON/YAML endpoints on its own. Access control is enforced separately by Spring Security or a gateway.

## 3. Securing Each Group with Spring Security

Example policy: public docs allow anonymous reads; internal docs require authority `docs.internal.read`; all other doc paths are denied:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain documentationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET,
                    "/v3/api-docs/public-v1",
                    "/v3/api-docs/public-v1.yaml")
                    .permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/v3/api-docs/internal-v1",
                    "/v3/api-docs/internal-v1.yaml")
                    .hasAuthority("docs.internal.read")
                .requestMatchers(HttpMethod.GET, "/v3/api-docs/swagger-config")
                    .hasAuthority("docs.internal.read")
                .requestMatchers("/v3/api-docs/**").denyAll()
                .anyRequest().authenticated()
            )
            .httpBasic(basic -> {})
            .build();
    }
}
```

Here, `httpBasic` illustrates an entry point returning `401` when unauthenticated. Real applications may use sessions, bearer JWTs, or gateway SSO; in those setups, anonymous status codes may differ, such as a `302` redirect to a login page. Assert against your application's actual configured entry point.

The `swagger-config` rule is configured explicitly because this endpoint can reveal group names or URLs. When public Swagger UI should only display `public-v1`, expose a restricted URL list for the public UI and apply matching security rules. Hiding a group in the UI does not replace securing the document URL.

If `swagger-config` must serve a public UI, configure it to list only public docs and verify the response omits internal groups. When both internal and public UIs are needed, deploy separate UI configs or protect via gateway/SSO; never expose a shared config if it leaks internal documentation against policy.

## 4. Asserting the Exact Operation Set of Each Group

A test checking only one key path can miss extra operations. To confirm a group contains the exact endpoint set, parse OpenAPI JSON into a `JsonNode`, extract every HTTP method/path pair, and compare against an allowlist.

Jackson helper example:

```java
import com.fasterxml.jackson.databind.JsonNode;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;

class OpenApiOperationAssertions {

    private static final Set<String> HTTP_METHODS = Set.of(
        "get", "put", "post", "delete", "patch", "options", "head", "trace"
    );

    static Set<String> operations(JsonNode document) {
        Set<String> result = new HashSet<>();
        JsonNode paths = document.path("paths");
        Iterator<String> pathNames = paths.fieldNames();

        while (pathNames.hasNext()) {
            String path = pathNames.next();
            JsonNode pathItem = paths.path(path);
            Iterator<String> keys = pathItem.fieldNames();

            while (keys.hasNext()) {
                String method = keys.next().toLowerCase(Locale.ROOT);
                if (HTTP_METHODS.contains(method)) {
                    result.add(method.toUpperCase(Locale.ROOT) + " " + path);
                }
            }
        }
        return result;
    }
}
```

The helper collects only HTTP operation keys; it skips Path Item fields like `parameters`, `servers`, `summary`, `description`, and `$ref`. Comparing both method and path distinguishes `GET /api/orders` from `POST /api/orders`.

## 5. Testing Groups with MockMvc

In Spring MVC applications, `@SpringBootTest` paired with `@AutoConfigureMockMvc` boots a context close to the real app, including springdoc and security configuration:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class DocumentationGroupContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void publicGroupContainsOnlyPublicOperations() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs/public-v1"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(OpenApiOperationAssertions.operations(document))
            .containsExactlyInAnyOrder(
                "GET /api/public/catalog",
                "GET /api/public/products/{id}",
                "POST /api/public/orders"
            );
    }

    @Test
    @WithMockUser(authorities = "docs.internal.read")
    void internalGroupContainsOnlyInternalOperations() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(OpenApiOperationAssertions.operations(document))
            .containsExactlyInAnyOrder(
                "GET /api/internal/health",
                "GET /api/admin/audit-events",
                "DELETE /api/admin/orders/{id}"
            );
    }
}
```

`containsExactlyInAnyOrder` catches both missing and unexpected endpoints. Paths in this example are illustrative allowlists; replace them with your application's actual contract. If the test profile disables auth for docs, use a dedicated test security configuration, but never disable security in your only test and conclude production policy is verified.

## 6. Testing JSON, YAML, and `swagger-config`

Do not test JSON alone. YAML is a separate artifact that can be misrouted or missed by security matchers:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

@Test
void publicYamlIsAvailable() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-v1.yaml"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("openapi:")))
        .andExpect(content().string(containsString("/api/public/catalog")));
}

@Test
void anonymousCannotReadInternalYaml() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
        .andExpect(status().isUnauthorized());
}
```

The `401` test assumes the security entry point returns Unauthorized for anonymous callers as in the Basic Auth example above. If the application redirects to a login page, adjust assertions to match actual behavior or configure a consistent entry point for docs endpoints.

`swagger-config` should be tested per publishing policy. When public, confirm it lists only public groups; when internal, confirm anonymous callers are rejected and authorized users succeed. Never assume every springdoc version emits the exact same `urls` shape; verify JSON against your active UI configuration.

Example inspecting the config response with Jackson:

This method extends `DocumentationGroupContractTest` from the previous section, reusing `mockMvc`, `objectMapper`, and its static imports.

The anonymous test applies only when matcher rules permit reading `swagger-config` and Swagger UI is configured to advertise only the public group. The security configuration shown earlier protects this endpoint with `docs.internal.read`; to run the anonymous test, change that rule to `permitAll` and restrict the published group list.

```java
@Test
void publicSwaggerConfigDoesNotExposeInternalGroup() throws Exception {
    String body = mockMvc.perform(get("/v3/api-docs/swagger-config"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

    JsonNode config = objectMapper.readTree(body);
    String json = config.toString();

    assertThat(json).contains("public-v1");
    assertThat(json).doesNotContain("internal-v1");
}
```

This test only applies when anonymous access to `swagger-config` is intentional and configuration publishes only `public-v1`. If config is protected, replace it with the corresponding access-control test.

## 7. Testing Access Control for JSON and YAML

Splitting tests by role makes policy readable:

The methods below also belong in `DocumentationGroupContractTest` to share `mockMvc`.

```java
@Test
void anonymousCanReadPublicJson() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-v1"))
        .andExpect(status().isOk());
}

@Test
void anonymousCannotReadInternalJson() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1"))
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
void docsReaderCanReadInternalJson() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1"))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "docs.internal.read")
void docsReaderCanReadInternalYaml() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
        .andExpect(status().isOk());
}
```

These tests assume matchers use `hasAuthority("docs.internal.read")`. If using `hasRole("DOCS_READER")`, `@WithMockUser(roles = "DOCS_READER")` grants authority `ROLE_DOCS_READER`. Test authority names must match real security configuration.

`@WithMockUser` populates a mock `Authentication` in `SecurityContext`. It tests authorization rules without verifying JWT signatures, issuers, audiences, expiration, or claim mappings from real tokens. If the application uses an OAuth2 Resource Server, add tests with JWT request post-processors and integration tests for decoders/issuers as needed.

## 8. Testing Configuration per Profile

Profiles can change API docs flags, Swagger UI availability, group beans, or security policies. Use `@ActiveProfiles` to spin up a Spring test context for a specific profile:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionDocumentationProfileTest {

    @Autowired
    Environment environment;

    @Test
    void disablesSwaggerUiButKeepsProtectedOpenApiExport() {
        assertThat(environment.getProperty(
            "springdoc.swagger-ui.enabled", Boolean.class
        )).isFalse();

        assertThat(environment.getProperty(
            "springdoc.api-docs.enabled", Boolean.class
        )).isTrue();
    }
}
```

This example assumes `application-prod.yml` disables UI while keeping the OpenAPI endpoint enabled for internal pipeline export. If production disables both, adjust assertions to match policy. Testing `Environment` confirms resolved context properties; it does not prove endpoints are reachable through gateways or security.

Never add `@SpringBootTest(properties = "springdoc.swagger-ui.enabled=true")` in this test because test properties override the very profile value under test. Only supply test properties when intentionally testing that override.

## 9. Verifying Group Beans Exist Only in Target Profiles

If a group should register only in staging or production, guard its configuration with `@Profile`:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("staging")
class PartnerDocumentationConfiguration {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-v1")
            .pathsToMatch("/api/partner/**")
            .build();
    }
}
```

Checking beans per profile:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("staging")
class StagingDocumentationGroupsTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersPartnerDocumentationGroup() {
        assertThat(context.getBeansOfType(GroupedOpenApi.class))
            .containsKey("partnerApi");
    }
}
```

Add another test class with `@ActiveProfiles("prod")` to verify the bean is absent in production. Give each profile its own test class; Spring TestContext caches contexts by configuration and active profiles. Never mutate environment variables between test methods to switch a running context's active profile.

When a group always exists yet its content varies by profile, call the document endpoint in each profile rather than checking only the bean. Bean presence alone does not guarantee filters produce the right operation set.

## 10. Combining Profiles and Security in One Test Matrix

Profile tests and security tests can live in separate classes so each test stays focused. For applications with complex configuration, add integration tests covering key combinations:

| Test Context | What to Confirm |
| --- | --- |
| `local` + anonymous | UI/docs enabled per dev policy; public and internal groups behave per local rules. |
| `staging` + docs reader | QA groups exist, JSON/YAML load cleanly, and operation sets are exact. |
| `prod` + anonymous | UI disabled; public docs load only if policy permits; internal docs are denied. |
| `prod` + docs reader | Internal docs load if production retains export endpoints; no unapproved groups exist. |

You do not need to duplicate every test across all combinations if profiles share identical settings. Target combinations with genuine differences: profiles altering properties, group beans, or authorization rules. Small focused tests pinpoint failures much faster than one giant test checking everything at once.

## 11. Choosing MockMvc vs. WebTestClient

Pick tools matching your application's web stack:

| Tool | Best Fit | Notes |
| --- | --- | --- |
| `MockMvc` | Spring MVC/Servlet | Dispatches requests through `DispatcherServlet` inside test context without a live server. |
| `WebTestClient` | Spring WebFlux | Tests reactive handlers; binds to application context or hits a running server. |
| HTTP clients (`RestClient`/`WebClient`) | Post-deployment smoke tests | Verifies real networking, reverse proxies, TLS, auth, and live public URLs. |

`@WebMvcTest` is a slice test that typically skips full application and springdoc auto-configuration. When testing `/v3/api-docs` with `GroupedOpenApi`, `@SpringBootTest` is usually a better fit. If using slice tests, explicitly import required config and confirm springdoc actually initializes.

For WebFlux, pair `@SpringBootTest` with `WebTestClient`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveDocumentationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void internalGroupRequiresDocumentationAuthority() {
        webTestClient.get()
            .uri("/v3/api-docs/internal-v1")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

This example assumes WebFlux security uses a `401` entry point and supplies no `Authentication`. If your app uses login redirects or a different test security setup, adjust expectations. For WebFlux, use reactive security test support and verify group documents within the same test context.

## 12. Required Testing Dependencies

Normally `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and MockMvc support for MVC apps. When testing Spring Security with `@WithMockUser`, add `spring-security-test` if not already supplied by project dependency management:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

WebFlux apps use `WebTestClient` from Spring's test support. Pick test support matching your stack and align versions via Spring Boot dependency management. Never override Spring Security to a version different from the one managed by Spring Boot.

## 13. Security Inside OpenAPI Differs from Docs URL Protection

Two kinds of security must be tested separately:

1. **Operation security:** `components.securitySchemes` and `security` document which credentials clients must send when calling business APIs.
2. **Documentation security:** Spring Security/gateways decide who may fetch `/v3/api-docs/{group}`, YAML files, and `swagger-config`.

An internal endpoint may declare a bearer requirement in OpenAPI without securing `/v3/api-docs/internal-v1`. Conversely, the documentation URL may require session/Basic Auth even when operations inside the document require OAuth2 bearer tokens.

Tests should confirm both:

- JSON documents carry accurate security schemes and requirements for protected operations.
- Anonymous callers cannot download internal documents.
- Authorized callers can download documents.
- Public groups contain no internal operations or erroneous security metadata.

## 14. Post-Deployment Smoke Tests

In-context Spring tests cannot verify gateways, TLS, DNS, proxy rewrites, or platform-injected secrets. After deploying to staging/production, run smoke tests from the network clients or pipelines actually use:

```bash
curl --fail --silent --show-error \
  https://api.example.com/v3/api-docs/public-v1 \
  -o public-v1.json

curl --fail --silent --show-error \
  https://api.example.com/v3/api-docs/public-v1.yaml \
  -o public-v1.yaml
```

For internal groups, obtain tokens from the pipeline secret store with shell tracing disabled. Verify `401`/`403` when unauthorized, then verify `200` with an authorized service account. Never log tokens or commit them in scripts.

Smoke tests should also verify:

- URLs match the expected context path/reverse proxy prefix.
- JSON/YAML reflect the expected group ID and build version.
- `servers` in the document use the right public host, scheme, and prefix.
- `swagger-config` advertises only permitted groups.
- Operation sets match the reviewed manifest.
- Swagger UI is enabled/disabled per profile and loads documents authorized users may view.

## 15. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Tests pass only under default profile | Missing `@ActiveProfiles` or profile-specific file not loaded | Add dedicated test contexts for `local`, `staging`, and `prod`. |
| Public group contains internal endpoints | `pathsToMatch` too broad or missing `pathsToExclude` | Compare full operation sets and tighten filters. |
| Internal JSON is blocked yet YAML downloads freely | Security matcher omitted the `.yaml` suffix | Test both URLs separately and add matching rules. |
| Anonymous test gets `302` instead of `401` | Entry point redirects to login form | Confirm desired policy and align entry point or assertion. |
| `@WithMockUser` is still rejected | Test authority disagrees with `hasAuthority`/`hasRole` | Align authority names and role prefixes. |
| Profile test shows UI disabled yet endpoint stays live | Disabled only `springdoc.swagger-ui.enabled`, not `springdoc.api-docs.enabled` | Assert both properties independently and test live URLs. |
| Group test returns `404` | Group bean absent in profile or wrong group ID | Check `GroupedOpenApi` beans and active profiles. |
| JSON test passes yet Swagger UI fails to load | `swagger-config`, static assets, CORS, or browser auth differs | Inspect individual UI requests in the Network tab. |
| `@WebMvcTest` lacks `/v3/api-docs` | Slice test skips springdoc auto-configuration | Use `@SpringBootTest` or explicitly import needed config. |
| `@WithMockUser` passes yet real JWT fails | Test skips token decoder and claim mapping | Add JWT/resource-server integration tests. |
| Test context uses different properties than production | `@SpringBootTest(properties=...)` overrides profile | Remove unnecessary overrides and run post-deploy smoke tests. |

## 16. Test Implementation Checklist

Before considering contract tests complete, confirm:

1. A reviewed group/profile/access matrix exists.
2. Each group has an explicit HTTP method and path allowlist.
3. Tests assert exact operation sets, catching both missing and extra endpoints.
4. JSON and YAML are tested independently.
5. `swagger-config` exposes no unapproved groups.
6. Anonymous, authenticated-without-authority, and authorized users are all tested.
7. Profile tests use `@ActiveProfiles` without unintended test-property overrides.
8. Profile-conditional group beans are verified for presence/absence per environment.
9. Security metadata inside OpenAPI is tested separately from docs endpoint security.
10. MockMvc is used for MVC, WebTestClient for WebFlux, and HTTP smoke tests post-deploy.
11. CI tokens come from secret stores; Actuator and docs endpoints are properly secured.
12. Artifacts are exported from the right instance/build and stored per group access policy.

## 17. Guiding Principles

- Define the group, profile, and access matrix before writing tests.
- Use `@SpringBootTest` when verifying full springdoc, group beans, and Spring Security behavior.
- Use `@ActiveProfiles` to test profile configurations in isolated Spring contexts.
- Compare every group's full HTTP method/path pairs against an allowlist.
- Test JSON, YAML, and `swagger-config` individually.
- Test anonymous callers, authenticated callers lacking authority, and authorized callers.
- Separate operation security requirements from OpenAPI document retrieval permissions.
- Never treat `@WithMockUser` as proof that real JWT or OAuth2 tokens work.
- Choose MockMvc for MVC, WebTestClient for WebFlux, and HTTP clients for gateway smoke tests.
- Keep test profiles close to real policy; avoid overriding the very properties under test.
- Re-verify public URLs, artifacts, and access controls after every deployment.

Testing documentation groups, profiles, and security ensures OpenAPI specs match the intended API surface per environment and reach only authorized audiences. Group tests verify operation sets; profile tests verify loaded configuration; security tests verify who can fetch JSON, YAML, and `swagger-config`. Combining in-context Spring tests with post-deployment smoke tests catches both contract drift and gateway, proxy, or runtime configuration bugs.

## References

- [Springdoc OpenAPI – Multiple OpenAPI Definitions and GroupedOpenApi](https://springdoc.org/faq.html)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
