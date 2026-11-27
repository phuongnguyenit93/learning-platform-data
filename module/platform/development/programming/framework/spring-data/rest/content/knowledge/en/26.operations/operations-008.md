# Controlling HAL Explorer Activation in Deployment Environments

## 1. What HAL Explorer Does and Why It Must Be Controlled

HAL Explorer is a web UI for exploring REST APIs that use HAL or HAL-FORMS. It reads hypermedia links in responses, allowing navigation from the root resource to collections, items, searches, and other relations, while displaying response status, headers, and bodies.

HAL Explorer is an API client capable of sending state-changing requests. Spring Data REST documentation describes GET, POST, PUT, PATCH, and DELETE operations directly inside the UI. Therefore, treat it as an operational tool for developers or support teams with appropriate permissions, not as a read-only documentation page.

Spring Data REST provides built-in integration via the dependency:

- Maven: org.springframework.data:spring-data-rest-hal-explorer
- Gradle: org.springframework.data:spring-data-rest-hal-explorer

When this dependency is on the runtime classpath, Spring Data REST auto-configures HAL Explorer at the application's root URI. If the API uses a base path such as /api, verify the actual URI after starting the application; the UI may navigate or redirect to the API root.

Key distinctions:

- **HAL Explorer is a client UI.** It helps users explore and invoke the API.
- **Spring Data REST is still the API.** Repository resources, HAL links, and HTTP endpoints continue operating even when the Explorer UI is removed.
- **Spring Security decides who can call the API and what they are allowed to do.** Explorer does not create its own authorization layer and cannot replace server-side authorization.

## 2. Enabling HAL Explorer in an Application

When using Spring Boot, the dependency version is managed by Spring Boot dependency management or the Spring Data BOM. Do not pin the version manually unless the project explicitly manages Spring Data versions.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-rest-hal-explorer</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.data:spring-data-rest-hal-explorer")
}
~~~

After adding the dependency, run the application and open the Spring Data REST root URI in a browser. Explorer reads the HAL document, lists available links, and lets you open resources by relation.

For quick local testing, you can start the application locally:

~~~bash
./mvnw spring-boot:run
~~~

or:

~~~bash
./gradlew bootRun
~~~

When the dependency is absent from the runtime classpath, Spring Data REST can still return HAL JSON at the API root as long as the Spring Data REST starter and repository configuration remain enabled. Removing HAL Explorer does not disable Spring Data REST.

## 3. Controlling the Dependency by Environment

Spring Data REST documentation describes enabling Explorer via the dependency and auto-configuring the UI at the root URI. Spring Data REST's basic settings list properties such as base path, page size, media type, and response body; the documentation does not define an enable/disable property for HAL Explorer such as spring.data.rest.enable-hal-explorer.

Therefore, do not add a line like the following assuming the framework will recognize it:

~~~properties
spring.data.rest.enable-hal-explorer=false
~~~

If you want Explorer present only in development or testing environments, manage the dependency in your build configuration.

### Maven Profile

Place the dependency in a dedicated profile in pom.xml:

~~~xml
<profiles>
    <profile>
        <id>dev-hal-explorer</id>
        <dependencies>
            <dependency>
                <groupId>org.springframework.data</groupId>
                <artifactId>spring-data-rest-hal-explorer</artifactId>
            </dependency>
        </dependencies>
    </profile>
</profiles>
~~~

Build with Explorer:

~~~bash
./mvnw -Pdev-hal-explorer package
~~~

Production build without activating the profile:

~~~bash
./mvnw package
~~~

### Gradle Property

With Gradle Groovy DSL, you can add the dependency conditionally:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")

    if (providers.gradleProperty("enableHalExplorer").orNull == "true") {
        runtimeOnly("org.springframework.data:spring-data-rest-hal-explorer")
    }
}
~~~

Run locally with Explorer:

~~~bash
./gradlew bootRun -PenableHalExplorer=true
~~~

Production build without passing the property:

~~~bash
./gradlew bootJar
~~~

Runtime-only is appropriate when the application does not need direct references to Explorer classes in source code. Declaring implementation as shown in the Spring Data REST documentation is also valid.

### Choosing a Deployment Approach Based on Artifact Strategy

The build profiles above produce different artifacts: the dev build includes the Explorer dependency, while the production build does not. This is straightforward and easy to verify, but keep it in mind if your release process requires building a single artifact and promoting it sequentially across dev, staging, and production.

If you must use the exact same artifact across all environments, choose one of the following approaches:

- Host Explorer in a separate application or static host, and expose that route only on the internal network.
- Keep the dependency in the artifact but block the UI URI at the reverse proxy or Spring Security in production. Verify the exact route before blocking so you do not accidentally block the API root itself.
- Grant UI access only to operations teams while enforcing separate authorization on API resources.

Do not use @Profile assuming the dependency disappears from the classpath. Spring profiles control beans and runtime configuration; they do not remove libraries packaged inside the artifact.

## 4. Securing Explorer and the API in Production

### Securing Both the UI and REST Resources

Two URL layers must be checked:

1. The URI serving the Explorer HTML page.
2. The API URIs that Explorer calls to read or modify resources.

You can protect the Explorer page with a role for developers or support teams. The API requires authorization per resource and operation. If only the HTML page is protected while the API remains public, users can still call the API via curl or other clients. Conversely, if the API is protected while the Explorer page is public, unauthenticated users can view the UI while API requests are rejected.

When configuring Spring Security, verify the actual Explorer path and API root before writing request matchers. If the API base path is /api, the root URI and Explorer route may be tied to that base path. Do not copy generic matchers without checking mappings for your specific version.

### Repository and Method Authorization

Spring Data REST integrates with Spring Security. You can use method-level security such as @PreAuthorize to restrict access on specific repositories or methods. Example:

~~~java
@PreAuthorize("hasRole('ROLE_USER')")
public interface OrderRepository extends CrudRepository<Order, UUID> {

    @PreAuthorize("hasRole('ROLE_ADMIN')")
    @Override
    Optional<Order> findById(UUID id);

    @PreAuthorize("hasRole('ROLE_ADMIN')")
    @Override
    void deleteById(UUID id);
}
~~~

This is a concise example illustrating where permissions are placed. Method security must be enabled with @EnableMethodSecurity, and all sensitive repository methods must be covered.

Note: method-level security overrides repository-level security rather than combining with it. For CrudRepository delete operations, review all delete variants such as deleteById, delete, deleteAll(Iterable), and deleteAll() so no call path is missed.

If an internal repository should not be exported as a REST resource, annotate it directly:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends CrudRepository<AuditRecord, UUID> {
}
~~~

You can choose an appropriate repository detection strategy, such as exporting only explicitly annotated repositories. This shrinks the API surface even when Explorer is not installed.

### CSRF When Using Session or Cookie Authentication

Spring Security enables CSRF protection by default for unsafe HTTP methods such as POST, PUT, PATCH, and DELETE. Because HAL Explorer can send these methods, requests must include a valid CSRF token if the application uses session/cookie-based authentication and CSRF is enabled.

How to handle this:

- Ensure the client obtains the token according to the CSRF mechanism configured by the application.
- Send the token in the request header or parameter per Spring Security configuration.
- Test both requests missing a token and requests with a valid token.
- Do not disable CSRF globally just so Explorer can send POST or DELETE.

For applications using bearer tokens not automatically attached by the browser, the CSRF model may differ. Identify how credentials are sent and evaluate the application's threat model before changing CSRF configuration.

### CORS When Explorer Runs on a Different Origin

If Explorer is bundled inside the same Spring Boot application and served from the same origin as the API, additional CORS configuration is usually unnecessary for the UI to call that API.

If using a hosted Explorer or a separate static host, the browser enforces CORS. The API must return appropriate CORS headers for Explorer's origin. Allow only the required domains, HTTP methods, and headers; never use Access-Control-Allow-Origin: * in production. HAL Explorer documentation also warns that wildcard configurations are only for development/testing.

### TLS and Credentials

- Use HTTPS for both the UI and the API.
- Prefer short-lived tokens and least-privilege permissions.
- Do not share bookmarked URLs or screenshots containing tokens or credentials.
- In newer standalone HAL Explorer versions, documentation notes custom headers can be stored in the URL fragment to restore state. Check the exact UI version bundled before relying on this detail; never put real tokens into shared links or tickets.
- Restrict access with a VPN, internal network, reverse proxy allowlist, or operational roles if Explorer is kept in production.

## 5. Base Path Configuration and Access

Spring Data REST serves the API at the root URI by default. You can change the base path in application.yml:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
~~~

With this configuration, exported resources live under /api. Check the Explorer UI route for the exact dependency version in use; do not assume the HTML URI and the API root always share the exact same path.

Verification example using curl:

~~~bash
curl -i -H "Accept: text/html" https://example.internal/api/
~~~

The request above checks the response requested by a browser. To test the API root independently of the UI:

~~~bash
curl -i -H "Accept: application/hal+json" https://example.internal/api/
~~~

When Explorer is enabled, the response for the browser route is typically HTML or a redirect to the Explorer page per the dependency's mapping. When Explorer is removed, the API root must still return HAL JSON if Spring Data REST remains enabled and the request asks for the HAL media type.

If the app sets a context path via server.servlet.context-path, reverse proxy path rewrite, or ingress prefix, include those segments in your test URLs.

## 6. Testing Environment-Based Activation/Deactivation

Do not rely solely on visual inspection after deployment. Combine checks for build dependencies, HTTP responses, and access control.

### Checking the Dependency in the Artifact

Maven, when building the dev variant:

~~~bash
./mvnw -Pdev-hal-explorer dependency:tree -Dincludes=org.springframework.data:spring-data-rest-hal-explorer
~~~

Maven, when building production without activating the profile:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-rest-hal-explorer
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-rest-hal-explorer --configuration runtimeClasspath
~~~

For the production artifact, the expected output is no dependency path to spring-data-rest-hal-explorer. You can inspect the packaged executable jar using jar tf and search for the artifact name inside BOOT-INF/lib.

### Integration Tests for API Root and UI

Example using Spring Boot, MockMvc, and Spring Security Test. Adjust EXPLORER_URI and API_ROOT to match your application's actual base path and routes.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HalExplorerExposureTests {

    private static final String EXPLORER_URI = "/";
    private static final String API_ROOT = "/api/";

    @Autowired
    MockMvc mvc;

    @Test
    void apiRootStillReturnsHal() throws Exception {
        mvc.perform(get(API_ROOT).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links").exists());
    }

    @Test
    void explorerEntryIsHtmlWhenIncludedInThisBuild() throws Exception {
        mvc.perform(get(EXPLORER_URI).accept(MediaType.TEXT_HTML))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML));
    }
}
~~~

The UI test should run only in build variants that include the Explorer dependency. For production builds without the dependency, verify the Explorer route no longer returns an HTML page; if the API root and Explorer route overlap, still confirm that an Accept: application/hal+json request returns HAL JSON. Some versions or base-path mappings may redirect, so verify the final URI and response for your specific version before locking assertions.

Important note: @ActiveProfiles("dev") only activates Spring profile configuration. It does not add dependencies to the classpath. If the dependency is controlled by a Maven/Gradle build profile, run tests with the matching build profile.

### Testing Access Control and CSRF

Add the Spring Security test dependency if the project does not already include it:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Example verifying a state-changing request with a CSRF token:

~~~java
@Test
@WithMockUser(roles = "API_ADMIN")
void authorizedUserCanCreateResourceWithCsrf() throws Exception {
    mvc.perform(post("/api/people")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "firstName": "Grace",
                  "lastName": "Hopper"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

Also include tests for these cases:

- Anonymous callers cannot read the API or open the internal UI, per the authentication policy.
- Read-only users cannot send POST, PUT, PATCH, or DELETE.
- Users lacking delete permission receive 403 when calling delete endpoints.
- Cookie/session requests missing a CSRF token are rejected; requests with a valid token are processed according to permissions.
- If Explorer runs on a different origin, preflight requests from allowed origins succeed and disallowed origins do not receive CORS permissions.

Do not disable filters in MockMvc security tests; using @AutoConfigureMockMvc(addFilters = false) bypasses the very filter chain you need to verify.

## 7. Pre-Deployment Checklist

- [ ] Confirmed whether the Explorer dependency is present or absent on the artifact's runtime classpath.
- [ ] Confirmed the right profile/build variant is selected for dev, staging, and production.
- [ ] Recorded exact Explorer URI, API root, base path, and context path.
- [ ] API root returns HAL JSON when clients send Accept: application/hal+json.
- [ ] Explorer page is accessible only to permitted groups.
- [ ] API has server-side authorization; security does not rely on hiding buttons in the UI.
- [ ] GET permissions and write/delete permissions are tested separately.
- [ ] CSRF is properly enforced for session/cookie authentication.
- [ ] CORS is opened only for required origins if Explorer is hosted on a different origin.
- [ ] HTTPS is enabled; tokens are short-lived and never shared in URLs/logs.
- [ ] Internal repositories or sensitive data are not unintentionally exported.
- [ ] Automated tests verify UI and API state after every build/deploy.

## 8. Troubleshooting

| Symptom | Common Cause | How to Resolve |
|---|---|---|
| Opening root URI does not show Explorer | Dependency missing from runtime classpath or build profile not enabled | Check dependency tree/dependencyInsight and the actual artifact |
| Dev has Explorer, but production still has it too | Dependency is in default dependencies rather than a dedicated profile, or wrong artifact deployed | Check build logs, artifact version, and runtimeClasspath |
| Unsure which property disables Explorer | Searching for a property not published by Spring Data REST documentation | Manage the dependency per build variant or block the verified route at security/proxy |
| URI / returns 404 while API is at /api | API base path or server context path was changed | Check spring.data.rest.base-path, server.servlet.context-path, and reverse proxy rewrites |
| Browser renders HAL JSON instead of HTML | Request hits the API representation or Explorer route is not mapped as expected | Send Accept: text/html, check the root URI and dependency mappings |
| Explorer opens, but API returns 401/403 | UI route and API have separate security policies; API request lacks credentials or roles | Check authentication headers/sessions and repository authorization |
| GET works, but POST/DELETE returns 403 | Missing CSRF token or user lacks write/delete permission | Check CSRF header/token and method-level security |
| Requests from hosted Explorer are blocked by CORS | API does not allow the UI origin or misses preflight headers/methods | Allow only required origins, methods, and headers |
| Users can delete data through Explorer | API permits deletes for the logged-in user's role | Restrict delete permissions on the server, check all delete methods, and apply least privilege |
| API root stops working after removing Explorer | Accidentally removed the Spring Data REST starter or disabled repository configuration | Remove only the HAL Explorer dependency; keep the Spring Data REST starter and config if the API must remain active |
| Shared links contain credentials | UI stores custom headers in the URL fragment in some versions | Do not share links containing tokens; revoke exposed tokens and use short-lived tokens |

When diagnosing auto-configuration, you can run the application with --debug to inspect auto-configuration conditions. Also check the runtime dependency tree; that is the most direct way to confirm whether Explorer is present in the running artifact.

## 9. Official Documentation and Examples

- [Spring Data REST Reference — Tools / HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html): Maven/Gradle dependencies, auto-configuring the UI at the root URI, HAL navigation, and GET/POST/PUT/PATCH/DELETE operations.
- [Spring Data REST Reference — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): Spring Boot starter, auto-configuration, base path, and Spring Data REST configuration properties.
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html): protecting repositories and methods with Spring Security; note that method-level rules override repository-level rules.
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): default CSRF protection for unsafe HTTP methods, token repositories, request headers, and JavaScript integration.
- [HAL Explorer Reference Documentation](https://toedter.github.io/hal-explorer/release/reference-doc/): UI capabilities, authentication headers, CORS, data operations, and browser state persistence. This documentation covers current standalone HAL Explorer; verify against the version bundled in spring-data-rest-hal-explorer.
- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): how Spring Boot activates and excludes auto-configuration.
- [Spring Data REST — Getting Started guide](https://spring.io/guides/gs/accessing-data-rest): HAL API example, resource links, pagination, and CRUD calls over HTTP.