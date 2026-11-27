# Testing Authenticated and Authorized Management Endpoints

## 1. Objectives

In a Spring Cloud system, some management endpoints can alter an application's operational state or how the distributed system perceives an instance. Therefore, testing these endpoints must verify both business behavior and the security layer sitting in front of the endpoint.

A concrete example is the Service Registry Actuator endpoint provided by Spring Cloud Commons:

- `GET /actuator/serviceregistry` reads the current registration status.
- `POST /actuator/serviceregistry` updates the registration's status via a JSON body containing a `status` field.

With Eureka, common status values are `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`. Other providers may support a different value set or interpretation. The endpoint requires a `Registration` bean in the Spring `ApplicationContext`.

A management endpoint is secure only when all of the following requirements hold simultaneously:

1. The endpoint is intentionally enabled and exposed.
2. Requests pass through the actual security filter chain.
3. The caller is authenticated.
4. The caller holds permissions appropriate for reading or modifying status.
5. State-changing requests satisfy the CSRF policy when CSRF is enabled.
6. Tests prove unauthorized callers cannot trigger side effects.

This lesson belongs to the **Testing** chapter of the **SPRING_CLOUD_CORE** module. The module focuses on Spring Cloud's core foundations in distributed systems, especially Spring Cloud Commons, Context, externalized configuration, discovery, service registries, service communication, and testing/operating shared abstractions.

After this lesson, learners can:

- Distinguish authentication, authorization, endpoint exposure, and endpoint access.
- Protect management endpoints with Spring Security.
- Separate authorization rules for reading versus modifying service registry status.
- Write integration tests with `MockMvc` or `WebTestClient`.
- Test anonymous callers, authenticated callers lacking roles, missing CSRF tokens, and valid admins.
- Verify that side effects occurred or were blocked.
- Spot testing mistakes that bypass security filters without exercising real security.

## 2. The Spring Cloud Commons Service Registry Endpoint

Spring Cloud Commons provides an Actuator endpoint with ID `serviceregistry`. With default Actuator configuration, the base path is `/actuator`, so common URLs are:

```text
GET  /actuator/serviceregistry
POST /actuator/serviceregistry
```

The endpoint relies on a `Registration` bean in the application context. GET returns the registration status. POST accepts JSON with a `status` field and instructs the `ServiceRegistry` implementation to update status accordingly.

The endpoint operates on the current registration bound to this application. It is not an API for passing arbitrary service IDs or instance IDs to update an arbitrary registration in the registry. GET returns the provider-supplied status, typically a string like `UP`; do not assume every provider shares the exact same status set or response semantics.

Example request:

```http
POST /actuator/serviceregistry
Content-Type: application/json

{
  "status": "OUT_OF_SERVICE"
}
```

With Eureka, this operation takes the instance out of traffic during maintenance. When using Consul, Zookeeper, or another provider, check which status values the implementation supports. Never assume every provider understands the same status string.

This management endpoint has broader impact than a read-only info API. Anyone authorized to POST can change the status consumed by discovery clients and load balancers. Consequently, status-update permissions should normally be restricted to operations teams or a dedicated management service.

### 2.1. Distinguishing Endpoint ID from URL

`serviceregistry` is the endpoint ID. The HTTP URL is built from the management base path and ID:

```text
<management-base-path>/serviceregistry
```

If `management.endpoints.web.base-path` changes, the URL changes too. When writing security rules, use `EndpointRequest.to("serviceregistry")` instead of hard-coding `/actuator/serviceregistry`. This matcher ties to the endpoint ID and the application's management base path.

Some older Spring Cloud documentation used `/service-registry` or an `instance-status` subpath. In current Spring Cloud Commons, the documented endpoint ID is `serviceregistry`; always verify against your running release train before writing test paths.

## 3. Four Layers to Test

Do not lump every endpoint failure into an authentication error. An Actuator endpoint is governed by multiple independent layers:

| Layer | Question | Example configuration or check |
| --- | --- | --- |
| Endpoint availability | Is the endpoint created in the application context? | Matching `Registration` bean and `ServiceRegistry` implementation present. |
| Exposure | Is the endpoint exposed over HTTP? | `management.endpoints.web.exposure.include`. |
| Endpoint access | Does the endpoint permit read/write operations? | `management.endpoint.<id>.access` and `management.endpoints.access.default` in supported versions. |
| Authentication and authorization | Who may call the endpoint and what may they do? | Spring Security, `SecurityFilterChain`, roles, or authorities. |

These layers have distinct meanings:

- An unexposed endpoint usually has no HTTP mapping.
- An exposed endpoint lacking a `Registration` bean may fail to function or return 404 depending on configuration.
- An endpoint with restricted access may omit the corresponding operation.
- Unauthenticated requests typically receive 401 with HTTP Basic.
- Authenticated requests lacking the required role typically receive 403.
- POST requests missing a CSRF token can also receive 403 even when the caller holds an admin role.

When a test fails, identify which layer rejected the request before concluding the security rule is wrong.

## 4. Intentional Endpoint Exposure

Spring Boot exposes only the `health` endpoint over HTTP by default. JMX exposure rules are configured separately and can be broader. To use Service Registry Actuator over HTTP, add the endpoint ID to the exposure list:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,serviceregistry
```

Never use `include: "*"` just to enable one management endpoint. An explicit list prevents accidentally exposing `env`, `configprops`, `beans`, `heapdump`, `loggers`, or other endpoints containing sensitive information or system-mutating operations.

### 4.1. Endpoint Access in Spring Boot Versions Supporting Access Levels

Spring Boot can restrict access at the endpoint level. Example:

```yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,serviceregistry
  endpoint:
    health:
      access: read-only
    serviceregistry:
      access: unrestricted
```

In this example, `serviceregistry` is allowed to provide both read and write operations at the Actuator layer. Caller permissions must still be enforced by Spring Security.

The two mechanisms do not replace each other:

- `access: unrestricted` does not mean anonymous users are allowed to call the endpoint.
- Granting Spring Security role `OPS_ADMIN` does not make write operations exist if Actuator restricted the endpoint to `read-only`.
- `management.endpoints.web.exposure.include` controls whether the endpoint is exposed over HTTP; it does not grant permissions to callers.

If the application uses an older Boot version without access-level properties, use the enabled/exposure and security mechanisms appropriate for that version. Do not blindly copy Boot 4 configuration into every Boot 3 version.

## 5. Authentication and Authorization

**Authentication** verifies the caller's identity. For example, the request supplies valid HTTP Basic credentials or a valid bearer token.

**Authorization** determines whether that identity is allowed to perform a specific operation. For instance, a logged-in user holding only role `VIEWER` is not allowed to change service registry status.

A policy can be described as follows:

| Caller | GET status | POST status change |
| --- | --- | --- |
| Anonymous | Denied | Denied |
| Authenticated user, role `VIEWER` | Denied | Denied |
| Authenticated user, role `OPS_ADMIN` | Allowed | Allowed with valid CSRF when CSRF is enabled |
| Service account with write authority | Per policy | Allowed only with the matching operational authority |

Never assume every logged-in user is an administrator. Verifying authentication succeeds does not replace verifying roles/authorities.

### 5.1. Roles and Authorities

With `hasRole("OPS_ADMIN")`, Spring Security checks authority `ROLE_OPS_ADMIN`. When using `User.withUsername(...).roles("OPS_ADMIN")`, Spring automatically prepends `ROLE_`.

With OAuth2 Resource Server, policies can rely on scopes or authorities, for example:

```java
requestMatchers(EndpointRequest.to("serviceregistry"))
        .hasAuthority("SCOPE_registry.write")
```

Do not write `hasRole("ROLE_OPS_ADMIN")`: `hasRole` adds the `ROLE_` prefix automatically. When checking an exact authority string, use `hasAuthority`.

## 6. Protecting Endpoints with SecurityFilterChain

Servlet-based example for Spring Boot 4:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("serviceregistry"))
                    .hasRole("OPS_ADMIN")
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .anyRequest()
                    .authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

In this example:

- Only users with role `OPS_ADMIN` can access the `serviceregistry` endpoint.
- The `health` endpoint is publicly accessible per the chosen policy.
- Remaining requests require authentication.
- Spring Security's default CSRF protection remains active because no CSRF-disabling config is present.

Spring Boot 4 uses package `org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest`. In Spring Boot 3.x, the package is typically `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest`. Choose imports matching your application's actual version.

### 6.1. Why Take Care When Declaring Multiple SecurityFilterChains?

When an application declares a `SecurityFilterChain` bean, Spring Boot's default security auto-configuration backs off and leaves access rules to the application. If you create a chain matching only Actuator:

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
```

then that chain handles only Actuator. Another chain is needed for APIs and remaining URLs; otherwise unmatched requests may not be protected as expected.

You can use a single chain covering the whole application as shown above, or multiple chains ordered with `@Order` plus a fallback chain. Either way, test both management endpoints and business endpoints to catch any unprotected paths.

### 6.2. Using Endpoint ID Matchers

`EndpointRequest.to("serviceregistry")` is better than manual path string matching:

- Respects `management.endpoints.web.base-path`.
- Matches the endpoint root and related subpaths.
- Does not break on `/actuator` if the application changes its base path.
- Keeps security rules tied to the endpoint ID rather than a mutable URL.

If using a dedicated management server port, still test actual routing and network policies for the management port. Security matchers do not replace firewalls or network segmentation.

## 7. CSRF and POST Operations

CSRF protects applications from state-changing requests sent automatically by browsers along with cookies or credentials. Spring Security enables CSRF by default for servlet applications.

Consequently, a POST request to `serviceregistry` can be rejected with 403 when missing a CSRF token, even if the user is authenticated and holds role `OPS_ADMIN`.

In tests, separate two cases:

1. User lacks role: rejected by authorization.
2. User holds role yet lacks CSRF token: rejected by the CSRF filter.

Do not disable CSRF globally just to make POST tests pass. If an endpoint serves only machine-to-machine traffic using stateless bearer tokens without cookie/session authentication, you can design an appropriate CSRF policy after evaluating the authentication model. If using HTTP Basic or session cookies, evaluate CSRF risks and keep suitable protection.

Spring Security Test provides the `csrf()` request post-processor:

```java
mockMvc.perform(post("/actuator/serviceregistry")
        .with(user("ops-admin").roles("OPS_ADMIN"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"OUT_OF_SERVICE\"}"));
```

You can use `csrf().asHeader()` to simulate passing the token in a header. You can also test invalid tokens with `csrf().useInvalidToken()`.

## 8. Testing Strategy

To test management endpoints properly, include these test layers:

| Test type | Goal |
| --- | --- |
| Policy unit test | Verify role/authority mappings to read and write permissions. |
| MVC security test | Verify filter chain returns 401/403 and blocks side effects. |
| Actuator integration test | Verify endpoint is actually created, exposed, and reachable. |
| Provider integration test | Verify status propagates to Eureka/Consul/Zookeeper per provider contract. |
| Network test | Verify management port, firewall, proxy, and TLS in deployment environment. |

`@SpringBootTest` combined with `@AutoConfigureMockMvc` fits testing both Actuator endpoints and Spring Security in one application context. `MockMvc` runs requests through MVC and security filters without opening a real socket.

For WebFlux tests, use `WebTestClient` with `SecurityWebFilterChain`. When testing servlet container behavior, proxies, TLS termination, or a separate management port, add tests running a real server via `RANDOM_PORT`.

### 8.1. Test Dependencies

With Gradle, common dependencies include:

```groovy
testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.security:spring-security-test")
```

Use the Spring Boot BOM/plugin to manage versions. In Spring Boot 4, several test auto-configuration packages were modularized; for example, `@AutoConfigureMockMvc` lives in `org.springframework.boot.webmvc.test.autoconfigure`. In Boot 3.x, the import is typically `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`.

Never use `@AutoConfigureMockMvc(addFilters = false)` in security tests. That attribute strips security filters from `MockMvc`, leaving tests unable to verify the real protection path.

## 9. Testing with MockMvc

The following example assumes:

- The application has `ServiceRegistry` and `Registration` beans in the context.
- The endpoint is exposed over HTTP.
- Security configuration restricts `serviceregistry` to role `OPS_ADMIN`.
- HTTP Basic is configured to authenticate operations users.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,serviceregistry",
        "spring.security.user.name=ops-admin",
        "spring.security.user.password=test-secret",
        "spring.security.user.roles=OPS_ADMIN"
})
@AutoConfigureMockMvc
@Import(RegistryEndpointTestConfiguration.class)
class ServiceRegistryEndpointSecurityTests {

    private static final String ENDPOINT = "/actuator/serviceregistry";

    @Autowired
    MockMvc mockMvc;

    @Autowired
    InMemoryServiceRegistry registry;

    @BeforeEach
    void resetRegistryStatus() {
        registry.reset();
    }

    @Test
    void anonymousUserCannotReadRegistryStatus() throws Exception {
        mockMvc.perform(get(ENDPOINT)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousUserCannotPostEvenWithValidCsrfToken() throws Exception {
        String before = registry.currentStatus();

        mockMvc.perform(post(ENDPOINT)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isUnauthorized());

        assertThat(registry.currentStatus()).isEqualTo(before);
    }

    @Test
    void authenticatedUserWithoutOperationsRoleCannotReadStatus() throws Exception {
        mockMvc.perform(get(ENDPOINT)
                        .with(user("viewer").roles("VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void operationsAdminCanReadStatusUsingHttpBasic() throws Exception {
        mockMvc.perform(get(ENDPOINT)
                        .with(httpBasic("ops-admin", "test-secret"))
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("UP")));
    }

    @Test
    void operationsAdminCannotPostWithoutCsrfToken() throws Exception {
        String before = registry.currentStatus();

        mockMvc.perform(post(ENDPOINT)
                        .with(user("ops-admin").roles("OPS_ADMIN"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isForbidden());

        assertThat(registry.currentStatus()).isEqualTo(before);
    }

    @Test
    void operationsAdminCanPostWithValidCsrfToken() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .with(user("ops-admin").roles("OPS_ADMIN"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().is2xxSuccessful());

        assertThat(registry.currentStatus()).isEqualTo("OUT_OF_SERVICE");
    }

    @Test
    void viewerCannotPostEvenWithValidCsrfToken() throws Exception {
        String before = registry.currentStatus();

        mockMvc.perform(post(ENDPOINT)
                        .with(user("viewer").roles("VIEWER"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isForbidden());

        assertThat(registry.currentStatus()).isEqualTo(before);
    }
}
```

In this test:

- `httpBasic(...)` tests authentication with HTTP Basic credentials.
- `user(...)` creates an authenticated principal to test authorization without validating a password.
- `csrf()` attaches a valid CSRF token to the POST request.
- The successful admin POST test must also verify that registry status changed; asserting only 2xx is insufficient to prove the right side effect occurred.

The test fixture can inject a mock `ServiceRegistry` to verify status after POST. When using a real registry, verify status via the corresponding API/provider test and restore status after each test.

### 9.1. Fake Registry for Isolated Tests

When testing the endpoint and security without depending on a running Eureka or Consul server, you can use test-only `Registration` and `ServiceRegistry` beans. Place these imports at the top of the test file:

```java
import java.net.URI;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;
import org.springframework.context.annotation.Bean;
```

Test configuration registering a fake registration and registry:

```java
@TestConfiguration(proxyBeanMethods = false)
class RegistryEndpointTestConfiguration {

    @Bean
    TestRegistration registration() {
        return new TestRegistration();
    }

    @Bean
    InMemoryServiceRegistry serviceRegistry() {
        return new InMemoryServiceRegistry();
    }
}
```

Declare the fake registration as a package-private class in the same test source file:

```java
final class TestRegistration implements Registration {

    @Override
    public String getInstanceId() {
        return "catalog-test-1";
    }

    @Override
    public String getServiceId() {
        return "catalog-service";
    }

    @Override
    public String getHost() {
        return "127.0.0.1";
    }

    @Override
    public int getPort() {
        return 8080;
    }

    @Override
    public boolean isSecure() {
        return false;
    }

    @Override
    public URI getUri() {
        return URI.create("http://127.0.0.1:8080");
    }

    @Override
    public Map<String, String> getMetadata() {
        return Map.of();
    }
}
```

The fake registry can store status in an `AtomicReference<String>`:

```java
final class InMemoryServiceRegistry
        implements ServiceRegistry<TestRegistration> {

    private final AtomicReference<String> status =
            new AtomicReference<>("UP");

    @Override
    public void register(TestRegistration registration) {
    }

    @Override
    public void deregister(TestRegistration registration) {
    }

    @Override
    public void close() {
    }

    @Override
    public void setStatus(TestRegistration registration, String newStatus) {
        status.set(newStatus);
    }

    @SuppressWarnings("unchecked")
    @Override
    public <T> T getStatus(TestRegistration registration) {
        return (T) status.get();
    }

    String currentStatus() {
        return status.get();
    }

    void reset() {
        status.set("UP");
    }
}
```

Register both beans in `@TestConfiguration` imported into the test context as shown above. When testing a successful POST, inject `InMemoryServiceRegistry` and assert `currentStatus()` equals the expected value.

Example assertion:

```java
assertThat(registry.currentStatus()).isEqualTo("OUT_OF_SERVICE");
```

This test isolates the endpoint adapter and security. It does not verify how live Eureka/Consul stores status. Keep the fake registry out of production component scanning; leave the fixture in the test source set.

If the application already has a discovery provider on the classpath, avoid having both the test fixture and the provider register conflicting `ServiceRegistry` beans ambiguously. Use an isolated test application context or configure the test to exclude provider integration from the context.

## 10. Testing by Permission Matrix

An explicit matrix prevents testing only the happy-path admin case:

| Request | Principal | CSRF | Expected outcome |
| --- | --- | --- | --- |
| GET status | Anonymous | Not applicable | 401 |
| GET status | `VIEWER` | Not applicable | 403 |
| GET status | `OPS_ADMIN` | Not applicable | 200 |
| POST status | Anonymous | Missing/invalid | 403 from CSRF filter |
| POST status | Anonymous | Valid | 401 unauthenticated |
| POST status | `VIEWER` | Valid | 403 |
| POST status | `OPS_ADMIN` | Missing | 403 |
| POST status | `OPS_ADMIN` | Invalid | 403 |
| POST status | `OPS_ADMIN` | Valid | 2xx and status updated |

Exact status codes can differ if the application uses an OAuth2 entry point, gateway, or custom exception handler. What must remain invariant is that unauthorized requests trigger zero side effects.

### 10.1. Testing Both Before and After POST Status

A status-changing test should verify:

1. Initial registration status.
2. POST request with the exact JSON `status` field.
3. Successful HTTP response.
4. `ServiceRegistry` receives the new status.
5. Subsequent GET returns the new status or provider API confirms the new status.
6. The test cleans up status after running so other tests are unaffected.

With Eureka, `OUT_OF_SERVICE` works as an example value. With other providers, use a status supported by that implementation.

### 10.2. Verifying Rejected Requests Never Mutate the Registry

For anonymous, viewer, or missing-CSRF requests, do not only assert 401/403. Also assert that registry status remained unchanged:

```java
String before = registry.currentStatus();

mockMvc.perform(post(ENDPOINT)
        .with(user("viewer").roles("VIEWER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
    .andExpect(status().isForbidden());

assertThat(registry.currentStatus()).isEqualTo(before);
```

This assertion catches severe bugs where security returns an error response yet the status-update logic still executes via another code path or before authorization completes.

## 11. Testing OAuth2 Resource Server

If the endpoint uses bearer tokens instead of HTTP Basic, authorization can be based on scopes or authorities:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(EndpointRequest.to("serviceregistry"))
            .hasAuthority("SCOPE_registry.write")
        .anyRequest()
            .authenticated());
```

With `MockMvc`, Spring Security Test provides the `jwt()` request post-processor to create a simulated JWT authentication:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(post(ENDPOINT)
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_registry.write")))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
    .andExpect(status().is2xxSuccessful());
```

`jwt()` is helpful for testing authorization after token authentication. It does not prove a real JWT has a valid signature, expected issuer, expected audience, or properly configured decoder. Live token validation requires separate tests for `JwtDecoder`, issuer/JWK, or an identity provider test environment.

If the resource server is stateless and accepts only bearer tokens in the `Authorization` header, CSRF policies may differ from session-cookie applications. Configure and test according to your actual authentication mechanism; never use `jwt()` tests as an excuse to disable CSRF application-wide.

## 12. Testing WebFlux with WebTestClient

Reactive applications use `SecurityWebFilterChain` and `ServerHttpSecurity` instead of servlet `SecurityFilterChain` and `HttpSecurity`. Use `WebTestClient` to send requests through the reactive security chain.

Corresponding security rule example for Spring Boot 4:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.reactive.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
class ReactiveManagementSecurityConfiguration {

    @Bean
    SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
        return http.authorizeExchange(exchange -> exchange
                        .matchers(EndpointRequest.to("serviceregistry"))
                            .hasRole("OPS_ADMIN")
                        .anyExchange()
                            .authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

In Spring Boot 3.x, the reactive matcher class is `org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest`. Verify imports for your active version.

Example testing a GET request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveManagementSecurityTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void anonymousUserCannotReadRegistryStatus() {
        webTestClient.get()
                .uri("/actuator/serviceregistry")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

This example uses Boot 4's `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient` package. In Boot 3.x, the annotation typically belongs to `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`.

For authorization tests, use Spring Security reactive test support to supply principals/authorities. For POST requests when CSRF is enabled, use `SecurityMockServerConfigurers.csrf()` to send a valid token and write separate tests for missing or invalid tokens.

Do not replace `WebTestClient` with a test calling `ServiceRegistryEndpoint` directly if your goal is verifying web security filters. Direct method calls bypass the HTTP pipeline and security layer.

## 13. Mock Tests vs. Real Server Tests

`MockMvc` and `WebTestClient` in mock environments are suited for testing:

- Request matchers.
- Authentication and authorization.
- CSRF.
- JSON bodies and response statuses.
- Side effects inside the `ServiceRegistry` bean.

They do not prove:

- Whether the management port is bound to the right network interface.
- Whether firewalls or ingress rules block unwanted access.
- Whether TLS certificates, hostname verification, and reverse proxies work properly.
- Whether a separate management server port is protected identically to the application port.
- Whether the external registry actually accepts the new status.

For those requirements, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` or a test environment running a real server, then send HTTP requests to the right management address. If `management.server.port` differs from `server.port`, send requests to the management port.

## 14. Common Testing Pitfalls

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| GET returns 404 | Endpoint not exposed, missing `Registration` bean, or wrong base path/endpoint ID | Check endpoint availability, `management.endpoints.web.exposure.include`, and `/serviceregistry`. |
| GET returns 401 | Unauthenticated request or wrong credentials | Check `AuthenticationEntryPoint` and HTTP Basic/bearer token. |
| GET returns 403 | Authenticated user lacks required role/authority | Check role prefix, scope mapping, and request matcher. |
| POST returns 403 even for admin | Missing/invalid CSRF token or authorization mismatch | Distinguish CSRF rejection from access-denied; use `csrf()` in valid tests. |
| POST returns 404/405 | Endpoint access restricted to read-only or write operation unavailable | Check endpoint access level and Boot version. |
| Security test passes yet production is insecure | `MockMvc` skipped security filters or prod config differs from test | Keep filters enabled, use prod-like context, and test real server when needed. |
| Test checks only 2xx | Did not verify registry status actually changed | Assert side effect in fake registry or read back from provider. |
| Custom `SecurityFilterChain` leaves other APIs unprotected | Boot default security backed off and chain lacks fallback rule | Cover whole application or add ordered fallback chain with `@Order`. |
| `user()` test passes yet Basic login fails | Request post-processor mocks principal without testing credential store | Add tests with `httpBasic()` and real test-configured users. |
| Admin endpoint reachable over public ingress | Only checked roles inside app without restricting network exposure | Separate management port, firewall, ingress rules, and verify from external network. |

## 15. Recommended Testing Workflow

1. Confirm endpoint ID, URL, and active provider.
2. Confirm the application context has `Registration` and `ServiceRegistry` beans.
3. Expose only `health` and genuinely required management endpoints.
4. Confirm whether endpoint access permits write operations.
5. Write policies distinguishing read roles from status-changing roles.
6. Verify `SecurityFilterChain` protects both management endpoints and other application URLs.
7. Test anonymous, authenticated-without-role, and admin callers.
8. Test POST with missing, invalid, and valid CSRF tokens.
9. Assert rejected requests do not alter status.
10. Assert admin POST updates status accurately per provider.
11. Test real bearer tokens or HTTP Basic credentials matching your authentication mechanism.
12. Add real-server tests for management port, TLS, proxies, and network policies.

## 16. Self-Check Questions

1. What operations does Spring Cloud Commons' `serviceregistry` endpoint perform on GET and POST?
2. Why does the endpoint require a `Registration` bean in the application context?
3. How does endpoint exposure differ from endpoint access?
4. How does authentication differ from authorization?
5. Why must an authenticated user lacking the required role still receive 403?
6. Why can a POST be rejected by the CSRF filter even when the user holds an admin role?
7. Why use `EndpointRequest.to("serviceregistry")` instead of hard-coding `/actuator/serviceregistry`?
8. When declaring a custom `SecurityFilterChain`, what happens to Spring Boot's security auto-configuration?
9. Why do `user()` tests not replace real HTTP Basic or JWT authentication tests?
10. How do you prove a rejected request did not mutate state in the service registry?

## 17. Official References

- [Spring Cloud Commons 5.0.4 — Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons 5.0.2 — ServiceRegistryEndpoint API](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/endpoint/ServiceRegistryEndpoint.html)
- [Spring Boot — Actuator Endpoints and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Spring Security and EndpointRequest](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot 4 — Servlet EndpointRequest API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/servlet/EndpointRequest.html)
- [Spring Boot 4 — Reactive EndpointRequest API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/reactive/EndpointRequest.html)
- [Spring Boot 4 — AutoConfigureWebTestClient API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/webtestclient/autoconfigure/AutoConfigureWebTestClient.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Security — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)

Paths, import packages, and endpoint access properties change across Spring Boot/Spring Cloud versions. Check documentation for your exact release train; keep tests tied to `EndpointRequest` and provider contracts rather than relying on URLs or statuses from an older version.
