# Checking Principal, SecurityContext, and Operation Permissions

## 1. Knowing the Caller and Deciding Permissions Are Two Different Things

A management endpoint might allow anyone to read a general status while restricting who can change that state. For example, anyone can view the maintenance flag of an experimental application; a read-only account has a valid username, yet only maintainers may enable or disable the flag.

To design this properly, distinguish:

- **Authentication:** establishing the caller's identity.
- **Authorization:** deciding whether that identity is permitted to perform a specific operation.
- **`Principal`:** representation of the identity supplied by the security mechanism for the call.
- **Actuator's `SecurityContext`:** provides the identity and role checks within the endpoint invocation context.
- **`SecurityFilterChain`:** handles HTTP security before the call reaches the endpoint method.

A `Principal` named `viewer` does not mean that account is allowed to change configuration. Nor does a username prove someone is an administrator; permissions must come from policies and trustworthy authentication data.

This lesson uses **Spring Boot 3.3.13, Spring MVC, and Spring Security**, with Java 17+ source code. The example and eight tests below have been run on Java 21.

## 2. Choosing the Right Principal and SecurityContext

### 2.1. Principal Is Supplied from the HTTP Call

In an operation exposed over the web, Actuator supports receiving `java.security.Principal` as a special parameter. It is not a query parameter named `principal` that the user must send.

An illustrative method, placed inside a web endpoint bean:

```java
@ReadOperation
public Map<String, Object> inspect(
        @Nullable Principal principal,
        SecurityContext securityContext) {
    return Map.of(
            "caller", principal == null ? "anonymous" : principal.getName(),
            "canChange", securityContext.getPrincipal() != null
                    && securityContext.isUserInRole("MAINTAINER"));
}
```

The snippet above illustrates using both parameters; the complete program and configuration are in section 5. Important imports:

```java
import java.security.Principal;
import org.springframework.boot.actuate.endpoint.SecurityContext;
import org.springframework.lang.Nullable;
```

`@Nullable` indicates the operation accepts cases with no authenticated identity. When `principal == null`, handle that branch before calling `getName()`.

For example, `principal == null ? "anonymous" : principal.getName()` can be used for display information. Assigning the string `"anonymous"` only creates a display label; it does not create a user or grant any permissions.

The mechanism for passing `Principal` and `SecurityContext` into web operations is described in [Spring Boot 3.3 Web Endpoint Security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.security).

### 2.2. Two SecurityContext Types Share the Same Short Name

| Full Type | Role | Relevant Methods |
| --- | --- | --- |
| `org.springframework.boot.actuate.endpoint.SecurityContext` | Actuator endpoint invocation context | `getPrincipal()`, `isUserInRole(String)` |
| `org.springframework.security.core.context.SecurityContext` | Spring Security context, holding `Authentication` | `getAuthentication()`, `setAuthentication(...)` |

In the operation signature in this lesson, you must import **Actuator's SecurityContext**. Do not substitute Spring Security's type just because the IDE suggests the same short name.

Actuator's `SecurityContext` has a clear contract: `getPrincipal()` can return `null`, `isUserInRole(role)` returns the role check result, and `SecurityContext.NONE` represents an empty context. See the [Actuator SecurityContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/SecurityContext.html).

Spring Security has a broader model: `SecurityContextHolder` provides a context holding `Authentication`, from which `GrantedAuthority` permissions can be read. These concepts are presented in [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html). You do not need to access `SecurityContextHolder` just to perform the two checks Actuator's context already provides.

### 2.3. Do Not Infer Login Status from an Out-of-Context Check

In a typical Spring Security setup, accessing `SecurityContextHolder` directly may encounter an `AnonymousAuthenticationToken` for anonymous users. Hence merely checking `authentication != null` or `authentication.isAuthenticated()` alone is not enough to classify a genuinely logged-in user.

At the boundary of this example's web operations, use `Principal` and `SecurityContext.getPrincipal()` provided by Actuator. If working deeper with Spring Security APIs, distinguish anonymous users via policies or `AuthenticationTrustResolver`, rather than looking at the name `"anonymousUser"` and guessing.

Do not cast every `Principal` to `UserDetails`. In Spring Security's Servlet integration, `Principal` is typically an `Authentication`; the user object inside it also depends on the authentication mechanism. Keep the `Principal` type when only `getName()` is needed.

## 3. Checking Roles According to Contract

In the example, accounts are created using:

```java
User.withUsername("maintainer")
        .password(encodedPassword)
        .roles("MAINTAINER")
        .build();
```

This is an illustrative snippet; `encodedPassword` must be a password encoded according to the encoder configuration. The complete code below generates that value with `PasswordEncoder`.

With default role configuration, `roles("MAINTAINER")` creates authority `ROLE_MAINTAINER`. Inside the experiment's web operation, we use:

```java
securityContext.isUserInRole("MAINTAINER")
```

Spring Security integrates with Servlet and typically applies the `ROLE_` prefix automatically for role checks. This behavior is explained in [Servlet API integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html#servletapi-roles).

The expressions below target the same role under default configuration, but belong to different APIs:

| Location | Check Expression |
| --- | --- |
| Actuator `SecurityContext` in MVC example | `isUserInRole("MAINTAINER")` |
| Spring Security authorization rule | `hasRole("MAINTAINER")` |
| Exact authority match in Spring Security | `hasAuthority("ROLE_MAINTAINER")` |

Do not generalize this prefix as a fixed rule for every adapter, role-prefix configuration, or authority assignment mechanism. If an application uses authorities such as `maintenance:write` or OAuth2 scopes, use appropriate authority checks in Spring Security or a policy layer, and test with the real configuration.

Username, role, and operation permission are three distinct concepts. An account named `maintainer` that only holds role `VIEWER` must still be denied state changes. Renaming an account is not a way to grant permissions.

## 4. Two Places to Enforce Access Control

### 4.1. HTTP Rules Before Entering the Endpoint

`SecurityFilterChain` can require authentication, check roles per request, and apply protections like CSRF. If a request is blocked here, the endpoint method does not run.

Spring Security selects the first matching request rule in the list. Specific rules must come before broad rules. See [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

Merely adding an ID to `management.endpoints.web.exposure.include` only exposes the endpoint over HTTP; it is not a rule permitting everyone to invoke operations. Appropriate security configuration is required.

### 4.2. Decisions Inside the Operation

An operation may need caller information to:

- Choose summary data vs. detailed data.
- Check permissions before performing an action.
- Record who performed a change.
- Apply policies that depend on specific data.

**Permission checks must complete before state-mutating effects.** If you mutate state first and then return `403`, the system has still executed the unauthorized action even though the HTTP status looks like a denial.

A `canChange` field returned to a UI is purely display support information. When receiving a write request, the server must recheck permissions against the current context. Do not use a `canChange` value submitted by the browser as proof.

If an operation is invoked from multiple entry points such as HTTP, background schedules, or another API, place shared policies at the appropriate layer. Configuring `SecurityFilterChain` alone does not guard direct Java calls. When using method security such as `@PreAuthorize`, enable it in configuration and ensure calls pass through proxies; this lesson focuses on checking the web operation context.

## 5. Complete Program: Viewing Status and Changing the Maintenance Flag

### 5.1. Experiment Policy

| Caller | GET status | POST change with valid CSRF |
| --- | --- | --- |
| Unauthenticated | Can view sample info; `canChange=false` | 401 |
| `viewer`, role `VIEWER` | Sees own name; `canChange=false` | 403 |
| `maintainer`, role `MAINTAINER` | Sees own name; `canChange=true` | 200 and changes state |

The maintenance flag here is just an in-memory boolean variable. It does not stop accepting requests, enable a maintenance page, or change application health status. We use it to observe when permissions are checked and whether the side effect occurred.

The example chooses `@WebEndpoint` because the policy and responses here are HTTP-specific. It does not expose this operation over JMX. If using a shared endpoint across multiple channels, design and test permissions for each channel; a web extension or HTTP filter does not automatically protect calls through another channel.

Standalone project structure:

```text
actuator-permissions-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/permissions/PermissionApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/permissions/PermissionTest.java
```

### 5.2. Dependencies and Versions

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>actuator-permissions-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
```

`spring-boot-starter-security` provides real security enforcement for requests. `spring-security-test` provides support for generating HTTP Basic and CSRF in tests. The Spring Security version is managed by Spring Boot 3.3.13; do not mix in a newer version on your own in this example.

### 5.3. Application, Users, Filter Chain, and Endpoint

Create `src/main/java/com/example/permissions/PermissionApplication.java`:

```java
package com.example.permissions;

import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.endpoint.SecurityContext;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.lang.Nullable;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class PermissionApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionApplication.class, args);
    }

    @Bean
    MaintenanceState maintenanceState() {
        return new MaintenanceState();
    }

    @Bean
    MaintenanceEndpoint maintenanceEndpoint(MaintenanceState state) {
        return new MaintenanceEndpoint(state);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer")
                        .password(encoder.encode("viewer-local"))
                        .roles("VIEWER").build(),
                User.withUsername("maintainer")
                        .password(encoder.encode("maintainer-local"))
                        .roles("MAINTAINER").build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        RequestMatcher maintenance = EndpointRequest.to("maintenance");
        RequestMatcher maintenanceRead = request ->
                "GET".equals(request.getMethod()) && maintenance.matches(request);

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"), maintenanceRead).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint()).authenticated()
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }

    public static class MaintenanceState {
        private final AtomicBoolean enabled = new AtomicBoolean(false);

        public boolean enabled() {
            return this.enabled.get();
        }

        public void setEnabled(boolean enabled) {
            this.enabled.set(enabled);
        }
    }

    @WebEndpoint(id = "maintenance")
    public static class MaintenanceEndpoint {
        private final MaintenanceState state;

        public MaintenanceEndpoint(MaintenanceState state) {
            this.state = state;
        }

        @ReadOperation
        public Map<String, Object> inspect(
                @Nullable Principal principal, SecurityContext securityContext) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("caller", principal == null ? "anonymous" : principal.getName());
            result.put("canChange", securityContext.getPrincipal() != null
                    && securityContext.isUserInRole("MAINTAINER"));
            result.put("maintenanceEnabled", this.state.enabled());
            return result;
        }

        @WriteOperation
        public WebEndpointResponse<Map<String, Object>> change(
                boolean enabled, SecurityContext securityContext) {
            Principal principal = securityContext.getPrincipal();
            if (principal == null) {
                return new WebEndpointResponse<>(
                        Map.of("error", "authentication_required"), 401);
            }
            if (!securityContext.isUserInRole("MAINTAINER")) {
                return new WebEndpointResponse<>(
                        Map.of("error", "forbidden"), 403);
            }

            this.state.setEnabled(enabled);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("maintenanceEnabled", this.state.enabled());
            result.put("changedBy", principal.getName());
            return new WebEndpointResponse<>(result, 200);
        }
    }
}
```

Classes are placed in one file for convenience when running. `@Bean` registers the endpoint and state; merely placing an annotation on a class without registering a bean leaves Actuator with no object to discover.

**How to read the filter chain:**

1. `health` and GET requests to the `maintenance` endpoint are permitted.
2. Remaining Actuator requests require authentication.
3. Requests outside that scope are denied by `denyAll()`.
4. HTTP Basic supplies an identity for requests with valid credentials.
5. CSRF remains enabled per default configuration.

`maintenanceRead` combines the HTTP method with `EndpointRequest`, distinguishing GET from POST without hardcoding the `/actuator` path in authorization rules.

This is a filter chain covering every request of the sample application. If adding business controllers, add policies for them; the `denyAll()` rule will reject requests not explicitly permitted. When declaring a custom filter chain, take responsibility for HTTP policies rather than expecting default configuration to protect the rest.

**How to read `inspect`:**

- `Principal` can be null because GET is allowed for unauthenticated callers.
- `caller` uses the real identity supplied by the security mechanism.
- `canChange` relies on the current context and role.
- No `principal` or `securityContext` needs to be passed in the URL.

**How to read `change`:**

- The missing-identity branch returns `401` before mutating state.
- The missing-role branch returns `403` before mutating state.
- Only after both checks does it invoke `state.setEnabled(enabled)`.
- `changedBy` comes from the authenticated `Principal`, not from the caller's JSON.

In the normal POST path under this configuration, unauthenticated requests are already blocked by the filter chain before `change`. The missing-identity branch inside the method is an additional guard, not a replacement for HTTP authentication mechanisms. A `WebEndpointResponse` only sets the response; it does not configure an authentication entry point or login challenge headers.

The two accounts and passwords in code are local learning data. `PasswordEncoder` creates the encoded password stored in memory for the experiment. Real applications need managed user stores and secrets; HTTP Basic also requires HTTPS over a network because Base64 does not encrypt transport.

### 5.4. Management Configuration

Create `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,maintenance
management.endpoints.jmx.exposure.exclude=*
management.endpoint.maintenance.cache.time-to-live=0ms
```

Expose only `health` and `maintenance` over HTTP. `maintenance` uses `@WebEndpoint`, which is already web-only; excluding JMX also makes the sample application's export scope explicit.

A TTL of 0 keeps observations immediate during the experiment. When results depend on the caller, evaluate caching mechanisms in the right context; do not put a global URL-keyed cache and reuse `caller` or `canChange` across different users.

## 6. Running and Checking Identity

In the directory containing `pom.xml`:

```shell
mvn package
java -jar target/actuator-permissions-demo-1.0.0.jar
```

Maven compiles Java along with required dependencies. Libraries are downloaded on the first run. The example uses default port `8080` and loopback address. If changing the port, adjust the URLs below.

### 6.1. Unauthenticated GET

In another terminal:

```shell
curl -s -H 'Accept: application/json' http://127.0.0.1:8080/actuator/maintenance
```

JSON body with initial state:

```json
{"caller":"anonymous","canChange":false,"maintenanceEnabled":false}
```

There is no authenticated user, yet GET is processed because the policy allows reading the sample info. This does not grant write permissions.

### 6.2. GET with the Viewer Account

```shell
curl -s -u viewer:viewer-local -H 'Accept: application/json' http://127.0.0.1:8080/actuator/maintenance
```

Body:

```json
{"caller":"viewer","canChange":false,"maintenanceEnabled":false}
```

Authentication succeeded: the operation receives the exact name `viewer`. Write permission remains `false`.

### 6.3. GET with the Maintainer Account

```shell
curl -s -u maintainer:maintainer-local -H 'Accept: application/json' http://127.0.0.1:8080/actuator/maintenance
```

Body:

```json
{"caller":"maintainer","canChange":true,"maintenanceEnabled":false}
```

If using PowerShell with a `curl` alias, call `curl.exe` to run the cURL program. Field ordering in the JSON responses above comes from `LinkedHashMap`; when testing APIs, verify field values rather than relying on JSON property order.

### 6.4. POST Has an Additional CSRF Condition

The application keeps CSRF enabled. Sending POST with a valid account but without a CSRF token can still be blocked with `403` before reaching the operation. That `403` code does not prove the user lacks the role.

The next section provides complete POST tests using MockMvc and valid CSRF tokens. `with(csrf())` is a test-environment helper; it is not an arbitrary query parameter to use in cURL or a way to disable CSRF.

The sample application does not provide a UI flow for real clients to obtain a CSRF token. If adding a client that sends POST, design how the token is obtained, sent back, and bound to the appropriate session context. Do not bypass CSRF just to make a test command succeed, especially when credentials can be sent automatically by a browser.

## 7. Eight Tests Verifying Both Permissions and Effects

Create `src/test/java/com/example/permissions/PermissionTest.java`:

```java
package com.example.permissions;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionTest {
    @Autowired MockMvc http;
    @Autowired PermissionApplication.MaintenanceState state;

    @BeforeEach
    void reset() {
        this.state.setEnabled(false);
    }

    @Test
    void anonymousReadHasNoPrincipalOrPermission() throws Exception {
        http.perform(get("/actuator/maintenance"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caller").value("anonymous"))
                .andExpect(jsonPath("$.canChange").value(false));
    }

    @Test
    void viewerReadHasIdentityButNoWriteRole() throws Exception {
        http.perform(get("/actuator/maintenance")
                .with(httpBasic("viewer", "viewer-local")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caller").value("viewer"))
                .andExpect(jsonPath("$.canChange").value(false));
    }

    @Test
    void maintainerReadRecognizesTheRole() throws Exception {
        http.perform(get("/actuator/maintenance")
                .with(httpBasic("maintainer", "maintainer-local")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caller").value("maintainer"))
                .andExpect(jsonPath("$.canChange").value(true));
    }

    @Test
    void anonymousWriteWithValidCsrfIsUnauthorized() throws Exception {
        http.perform(post("/actuator/maintenance").with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isUnauthorized());
        assertThat(state.enabled()).isFalse();
    }

    @Test
    void viewerCannotChangeStateEvenWithCsrf() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("viewer", "viewer-local")).with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("forbidden"));
        assertThat(state.enabled()).isFalse();
    }

    @Test
    void maintainerWithoutCsrfCannotChangeState() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("maintainer", "maintainer-local"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());
        assertThat(state.enabled()).isFalse();
    }

    @Test
    void maintainerWithCsrfCanChangeState() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("maintainer", "maintainer-local")).with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.maintenanceEnabled").value(true))
                .andExpect(jsonPath("$.changedBy").value("maintainer"));
        assertThat(state.enabled()).isTrue();
    }

    @Test
    void requestBodyCannotGrantTheViewerARole() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("viewer", "viewer-local")).with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true,\"role\":\"MAINTAINER\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("forbidden"));
        assertThat(state.enabled()).isFalse();
    }
}
```

Run:

```shell
mvn test
```

Successful summary:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Log lines, runtime, and JVM warnings may differ.

MockMvc traverses the security filter chain and Actuator mapping mechanism within the application context. It does not open a TCP port. HTTP Basic requests here use the two declared users, simultaneously testing integration between authentication, the Servlet principal, and Actuator's `SecurityContext`.

The [Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) documentation explains how `with(csrf())` supplies a valid token in tests.

Points to note when reading the results:

| Scenario | Primary Decision Layer | Result |
| --- | --- | --- |
| Anonymous GET | HTTP rule permits; operation receives null principal | 200, `canChange=false` |
| `viewer` GET | Authentication succeeds; role check fails | 200, `canChange=false` |
| `maintainer` GET | Identity and role match | 200, `canChange=true` |
| Anonymous POST with valid CSRF | Login required at filter chain | 401, no change |
| `viewer` POST with valid CSRF | Role check inside operation | 403, no change |
| `maintainer` POST missing CSRF | CSRF filter | 403, no change |
| `maintainer` POST with valid CSRF | Passes checks and executes operation | 200, state becomes `true` |
| `viewer` POST adding `role` to JSON | Role still comes from security context | 403, no change |

Testing unauthorized requests does not stop at checking HTTP status codes. Each denied case also asserts `state.enabled()` remains `false`. If these state assertions were omitted, a bug performing the action before rejecting could go unnoticed.

The test sending `"role":"MAINTAINER"` proves client-declared body content never becomes user permissions. The field the operation accepts to change state is `enabled`; identity and roles come from the security system.

## 8. Distinguishing 401, 403, and Input Binding Errors

**401 in the example** typically means the request requires login or HTTP Basic credentials are invalid. Although GET is `permitAll`, sending malformed or wrong Basic credentials can still fail authentication and return 401.

**403 in the example** has at least two independent causes:

- The request was rejected by the CSRF filter before the operation ran.
- The request reached the operation but lacked the `MAINTAINER` role.

Therefore, when investigating a 403 on POST, verify credentials, CSRF token, and role context in turn. You can use a breakpoint at the start of the operation or log sanitized denial events to determine how far the request traveled. Do not log passwords, tokens, full `Authorization` headers, or entire authentication objects.

If a request has the right permissions but omits `enabled` or sends a value not convertible to boolean, Actuator can return `400` during parameter binding. Do not confuse that input error with a role error. Compiler configuration from the Spring Boot parent preserves parameter names so JSON `enabled` maps properly.

## 9. Design Mistakes That Easily Create Vulnerabilities

### Only Checking That Principal Is Non-Null

That only establishes an identity condition in the active context. An authenticated account can still lack permission to make changes. Check the appropriate policy before the operation.

### Using the Username as a Role

Conditions like `principal.getName().equals("admin")` tie permissions to one account name. It does not replace a role or authority system and breaks easily when changing identity providers.

### Trusting role, user, or canChange Parameters from the Client

JSON and query parameters are caller-controlled data. Use them only as validated business inputs; never use them to establish trusted identity or self-assign roles.

In operations, `Principal` and `SecurityContext` are supplied by the web infrastructure through a dedicated mechanism. Sending `?principal=admin` is not a login mechanism.

### Importing the Wrong SecurityContext

Using `org.springframework.security.core.context.SecurityContext` where Actuator's context is needed can break special parameter injection and cause input-binding errors. Check the full package name before editing JSON or adding query parameters to work around the error.

MVC controller argument-resolver annotations like `@AuthenticationPrincipal` do not automatically turn an Actuator operation into a controller method either. Prefer parameter contracts supported by Actuator.

### Thinking permitAll Disables Security

`permitAll` permits access under the authorization rule in question. It does not strip HTTP Basic, CSRF, or other filters. That is why authentication or CSRF failures still need to be evaluated separately.

### Returning canChange and Skipping Checks on Write

Permissions can change after a UI has read state. Every write request must be rechecked from that request's own context. Hiding a button in the UI does not protect server-side operations.

### Checking After Already Mutating State

Maintain the order: obtain context → verify identity → verify permissions → perform mutation → build result. Never toggle a flag or emit external side effects before the denial branches.

### Relying on HTTP Policy for All Channels and Threads

`SecurityFilterChain` protects requests passing through that chain. Direct Java calls, JMX, background tasks, or new executors must be evaluated under their own mechanisms.

The example uses `@WebEndpoint`, so it creates no corresponding JMX operation. If expanding into a multi-channel endpoint, do not treat HTTP being secured as proof that every channel is secure.

When Servlet code transitions into asynchronous processing, the security context is not a global variable readable arbitrarily from every thread. Appropriate context propagation is needed. For WebFlux, do not copy ThreadLocal-based Servlet assumptions verbatim; use the corresponding reactive mechanism.

## 10. Practice and Verification Criteria

1. **Rename the `maintainer` account while keeping role `MAINTAINER`.** Update credentials in tests. The user is still allowed to change state, and `changedBy` reflects the new name.
2. **Keep the name `maintainer` but change its role to `VIEWER`.** GET must return `canChange=false`; POST with valid CSRF must return 403 and state must stay unchanged.
3. **Change the read policy from public to requiring login.** Confirm anonymous GET is blocked at the filter chain. Do not try to preserve null-principal expectations inside an operation that anonymous visitors are no longer allowed to enter.
4. **Add a detailed field visible only to maintainers.** Verify the response field is hidden from `viewer`, not just the HTTP status code.
5. **Add a new sensitive operation.** Write tests for an authorized user, an unauthorized user, an unauthenticated caller, and missing CSRF if the operation uses a protected method; in denied cases, confirm the side effect did not happen.

Before finalizing a management endpoint, be able to state clearly: who is identified in the call, which policy permits the operation, which layer rejects unauthorized requests, and what evidence shows rejected requests caused no change.
