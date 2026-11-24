# JEE Pre-authentication and Identity Provided by the Servlet Container in Spring Security

## 1. Context and Objectives

In a Java web application running on a **Servlet Container** (such as Apache Tomcat or a Jakarta EE application server), the container itself can authenticate users before the request reaches the application. Spring Security then does not need to ask for a password again; it **receives the container-verified identity** to build an `Authentication` object and enforce the application's access policy.

That is the **pre-authentication** model. "JEE" is the historical name of the Java EE integration mechanism; Spring Boot 3/Spring Security 6 uses Jakarta EE's `jakarta.servlet.*` namespace. The Spring Security class name remains `J2eePreAuthenticatedProcessingFilter`.

After this lesson, you should be able to explain and verify:

1. Who actually authenticates: the **Servlet Container**, via its configured realm/security domain and login mechanism (BASIC, FORM, or another container-supported mechanism).
2. The container supplies the username via `HttpServletRequest.getUserPrincipal()` and roles via `isUserInRole(String)`.
3. `J2eePreAuthenticatedProcessingFilter` extracts the authenticated username; `PreAuthenticatedAuthenticationProvider` completes the Spring `Authentication`, including authorities.
4. `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` can convert container roles into Spring `GrantedAuthority` values, such as `STAFF` → `ROLE_STAFF`.
5. For container-authenticated requests, Spring Security's `hasRole("ADMIN")` governs business access permissions. A valid principal **does not mean** access to every endpoint.
6. Without a trustworthy principal on the incoming request, pre-auth **never fabricates an identity**. Tests must prove that missing principals are rejected.

The example focuses on the **Servlet stack**. It does not configure Spring WebFlux, read Reactor Context, or use Spring Security form login in place of the container.

## 2. Trust Boundary: Who Authenticates, Who Authorizes?

There are two distinct layers:

| Layer | Responsibility | Signal / Mechanism |
| --- | --- | --- |
| Servlet Container | Verify credentials (or accept SSO per server config), manage realm/security domain, attach principal and JEE roles to request | `request.getUserPrincipal()`; `request.isUserInRole("ADMIN")` |
| Spring Security | Receive container-provided identity, create `SecurityContext`/`Authentication`, map roles, and enforce `authenticated()`, `hasRole(...)`, method security if enabled | `J2eePreAuthenticatedProcessingFilter`, `PreAuthenticatedAuthenticationProvider`, `AuthorizationFilter` |

Typical flow:

```text
Browser / HTTP client
     |
     | 1. HTTP request + credential/SSO evidence
     v
Servlet Container (realm + login mechanism)
     | 2. authentication succeeds
     | 3. attaches Principal and role list to Servlet request
     v
Spring Security FilterChainProxy
     |
     | J2eePreAuthenticatedProcessingFilter
     |   -> request.getUserPrincipal().getName()
     |   -> PreAuthenticatedAuthenticationToken
     |   -> AuthenticationManager / PreAuthenticatedAuthenticationProvider
     |   -> obtain GrantedAuthority from details or UserDetailsService
     |   -> SecurityContextHolder
     v
AuthorizationFilter: authenticated(), hasRole("ADMIN"), ...
     |
     v
Controller / service
```

**Do not confuse:** `PreAuthenticatedAuthenticationProvider` does not re-verify username/password. It relies on the assumption that **the external identity source already authenticated the user**. If the container fails to configure authentication properly, or a proxy layer can be spoofed by clients while still trusted by the app, the entire model collapses.

### APIs Provided by the Servlet Container

Before the application's security layer intervenes, a request genuinely protected by the container can be observed as follows:

```java
import jakarta.servlet.http.HttpServletRequest;
import java.security.Principal;

Principal principal = request.getUserPrincipal();
String username = principal == null ? null : principal.getName();
boolean hasAdminRole = request.isUserInRole("ADMIN");
String authMechanism = request.getAuthType();
```

This is an **illustrative snippet inside code where `request` already exists**, not a standalone class. `getUserPrincipal()` can return `null` if the container has not authenticated; `isUserInRole(...)` is meaningful only when the container has established the corresponding role mapping. `getAuthType()` may return `BASIC`/`FORM` or a container-supported mechanism name, or `null`, depending on the server and login method.

**Observation note:** After the request passes `SecurityContextHolderAwareRequestFilter`, Spring Security may *wrap* `HttpServletRequest` so that `getUserPrincipal()` / `isUserInRole()` reflect the Spring `Authentication`. Thus, calling those methods **inside a controller** is not always independent proof of the raw data originally provided by the container. The proper integration point to inspect is the request before the pre-auth filter or traces from the container itself.

## 3. Spring Security JEE Pre-auth Components

### 3.1. `J2eePreAuthenticatedProcessingFilter`

This filter extends `AbstractPreAuthenticatedProcessingFilter`. It extracts the **principal name** from `HttpServletRequest.getUserPrincipal()`. Container authentication has no standard API to pass raw passwords to Spring; hence the filter uses a **dummy** credentials value, not a password checked by the application.

When a principal is present and the Spring context holds no authentication yet, the filter creates a `PreAuthenticatedAuthenticationToken` and passes it to `AuthenticationManager`. If no principal is present, there is no identity to pre-authenticate. In a pre-auth-only configuration, requests to protected endpoints must be denied.

### 3.2. `PreAuthenticatedAuthenticationProvider`

The provider accepts `PreAuthenticatedAuthenticationToken` and invokes `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` to retrieve user/authorities. Two valid paths exist:

- **Use container roles:** `PreAuthenticatedGrantedAuthoritiesUserDetailsService` reads the `GrantedAuthority` list from `Authentication.getDetails()`; details **must** implement `GrantedAuthoritiesContainer`.
- **Use application business roles:** `UserDetailsByNameServiceWrapper` queries `UserDetailsService` with the container-authenticated name to fetch account status and internal permissions. You must manage account-name synchronization / identity linking and prevent mapping collisions.

The provider does not issue authentication calls to LDAP/Tomcat realms itself; that was already the container's job. Never configure `DaoAuthenticationProvider` to re-check a pre-auth token's dummy password.

### 3.3. `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource`

This bridges JEE roles and Spring Security authorities:

1. The list of **mappable** role names is specified via `MappableAttributesRetriever`, e.g., `STAFF` and `ADMIN`.
2. For each role name, the details source invokes `request.isUserInRole(role)`. Only roles the container affirms the user holds are retained.
3. `Attributes2GrantedAuthoritiesMapper` converts container role names into `GrantedAuthority` instances. The default simple mapper prepends `ROLE_` if not already present.
4. `PreAuthenticatedGrantedAuthoritiesUserDetailsService` extracts authorities from details and constructs user details for Spring Security.

If the container returns `isUserInRole("ADMIN") == true`, Spring receives `ROLE_ADMIN` by default. `hasRole("ADMIN")` checks for `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` uses the full authority name. Do not write `hasRole("ROLE_ADMIN")` when using the standard prefix.

**Mandatory condition:** Container role names, security-role/role-mapping configuration, and the mappable roles list must stay consistent. Merely adding `ADMIN` to the mappable list **does not grant** ADMIN to anyone; role verification is still performed by the container via `isUserInRole`.

## 4. Complete Example: Spring Boot 3, Java 17, Servlet Container Pre-auth

The example has two verification modes:

- **MockMvc:** runs tests in Spring Boot, mocking container APIs to verify filter, principal, and role mapping. This is a Spring Security integration test, not a real realm test.
- **WAR on a security-configured container:** real authentication happens at the container, then Spring enforces authorization. When simply running `bootRun` on embedded Tomcat **without a configured realm + protection**, `getUserPrincipal()` is typically `null` and protected endpoints return `403` per the configuration below. That is normal, not a Spring bug.

Create a small project with the following files.

### 4.1. `build.gradle`

Standalone Gradle example using Spring Boot 3.3.5 (Java 17) and Spring Security 6.x managed by Spring Boot:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // Deployable WAR onto an external Servlet Container.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use **Spring MVC/Servlet**; do not add `spring-boot-starter-webflux` to this example. If your organization uses another Spring Boot BOM/plugin, adjust versions for that environment while preserving container authentication semantics.

### 4.2. Application and WAR Initializer

File `src/main/java/com/example/jee/JeePreauthApplication.java`:

```java
package com.example.jee;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class JeePreauthApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(JeePreauthApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(JeePreauthApplication.class, args);
    }
}
```

`SpringBootServletInitializer` allows deploying a WAR onto a compatible Jakarta Servlet container (e.g., Tomcat 10.1 for a Boot 3.3 app). The `main` method still supports development/testing with embedded Tomcat, though the embedded server knows nothing about realm users unless you configure it.

### 4.3. Spring Security Config Consuming Container Principal/Roles

File `src/main/java/com/example/jee/SecurityConfig.java`:

```java
package com.example.jee;

import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.mapping.SimpleMappableAttributesRetriever;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedGrantedAuthoritiesUserDetailsService;
import org.springframework.security.web.authentication.preauth.j2ee.J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource;
import org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        // 1. Do not re-verify password; use roles present in pre-auth details.
        var userDetails = new PreAuthenticatedGrantedAuthoritiesUserDetailsService();
        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(userDetails);
        var manager = new ProviderManager(provider);

        // 2. List of mappable JEE roles.
        var roleNames = new SimpleMappableAttributesRetriever();
        roleNames.setMappableAttributes(Set.of("STAFF", "ADMIN"));

        var detailsSource =
                new J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource();
        detailsSource.setMappableRolesRetriever(roleNames);
        // Default mapper: STAFF -> ROLE_STAFF, ADMIN -> ROLE_ADMIN.

        // 3. Filter extracting name provided by the Servlet Container.
        var preAuthFilter = new J2eePreAuthenticatedProcessingFilter();
        preAuthFilter.setAuthenticationManager(manager);
        preAuthFilter.setAuthenticationDetailsSource(detailsSource);

        // Each HTTP request relies on the current container principal.
        // Do not use Spring HTTP session as an independent "identification source".
        preAuthFilter.setSecurityContextRepository(
                new NullSecurityContextRepository());

        return http
                .securityContext(context -> context.securityContextRepository(
                        new NullSecurityContextRepository()))
                .sessionManagement(session -> session.sessionCreationPolicy(
                        SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .requestMatchers("/api/whoami").authenticated()
                        .anyRequest().denyAll())
                // Pre-auth has no application login page to redirect to.
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(
                                new Http403ForbiddenEntryPoint()))
                // Container may use BASIC/FORM; Spring does not re-perform login.
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .addFilterBefore(preAuthFilter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

**Why configure it this way?**

- `J2eePreAuthenticatedProcessingFilter` reads the username from the **container-provided `getUserPrincipal()`**, not from client-sent headers.
- `ProviderManager(provider)` holds only the pre-auth provider; the provider derives authorities from details built by `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource`.
- `ROLE_` is the standard prefix checked by `hasRole`. In this code the mappable list includes `STAFF`/`ADMIN`; Spring accepts a role only if the container's `isUserInRole` returns true.
- `NullSecurityContextRepository` on **both the filter and SecurityContext chain** prevents saving Spring `Authentication` into the HTTP session and reusing an old principal when the container identity changes. The container can still manage its own session for its login mechanism.
- `SessionCreationPolicy.STATELESS` at the **Spring Security layer** does not require the container to be stateless. With container FORM login, cookies/JSESSIONID can still be used by the container to track sessions.
- Because the app does not initiate login itself, `Http403ForbiddenEntryPoint` returns `403` when Spring receives no accepted principal; this is a response **from Spring Security** in simulated tests. In real deployments, the container may intercept earlier and return `401 + WWW-Authenticate` or redirect to a login page per `web.xml` before the request reaches the filter.
- `.formLogin(...disable)` and `.httpBasic(...disable)` disable only **Spring Security's login mechanisms**; they do not disable BASIC/FORM configured on the Servlet Container.
- `.addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` places the pre-auth filter in the Spring Security filter chain before the form-login position, after the standard filters that prepare the Security Context.

Do not register `preAuthFilter` as another global Servlet `Filter` outside the chain unless needed: running the filter twice in two different positions makes behavior unpredictable. In the example, the filter is instantiated inside the chain config, preventing Boot from auto-registering it as a standalone container filter bean.

### 4.4. Endpoints Requiring Identification and Authorization

File `src/main/java/com/example/jee/ApiController.java`:

```java
package com.example.jee;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/whoami")
    public Map<String, Object> whoAmI() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return Map.of(
                "name", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    public String adminOnly() {
        return "admin-ok";
    }
}
```

At `/api/whoami`, Spring Security has already checked `authenticated()` before the handler executes. `SecurityContextHolder` belongs to the Servlet filter thread context for the current request. Expected response for user `alice` holding role `STAFF`:

```json
{
  "name": "alice",
  "authorities": ["ROLE_STAFF"]
}
```

Endpoint `/api/admin` requires `ROLE_ADMIN`. A user logged into the container with only `STAFF` must receive `403`.

## 5. Configuring Protection at the **Servlet Container** (Real WAR)

The Spring code above **is not responsible for creating realms or verifying credentials**. For a WAR deployed to an external server, real container security is required.

Illustrative `src/main/webapp/WEB-INF/web.xml` declaration for a Jakarta Servlet 6.0 container:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
    <security-constraint>
        <web-resource-collection>
            <web-resource-name>Secured API</web-resource-name>
            <url-pattern>/api/*</url-pattern>
        </web-resource-collection>
        <auth-constraint>
            <role-name>STAFF</role-name>
            <role-name>ADMIN</role-name>
        </auth-constraint>
    </security-constraint>

    <login-config>
        <auth-method>BASIC</auth-method>
        <realm-name>DemoRealm</realm-name>
    </login-config>

    <security-role>
        <role-name>STAFF</role-name>
    </security-role>
    <security-role>
        <role-name>ADMIN</role-name>
    </security-role>
</web-app>
```

Meaning:

- `/api/*` must pass container checks and hold one of `STAFF`/`ADMIN` before the request reaches the application.
- `<login-config>` selects HTTP BASIC **executed by the container**; there must be an **actual realm configured on the container** for `DemoRealm`/the app mapping users → roles. Declaring `web.xml` without defining a realm/user store is **not sufficient** for login.
- `<security-role>` declares role names; it **does not grant roles** to users.
- `isUserInRole("ADMIN")` returns true only if the container has mapped that role; consult server documentation when LDAP/AD groups must be mapped to JEE roles.
- Across Servlet versions, schema structure and packaging may vary; the example illustrates the standard Jakarta Servlet 6.0 model, not a realm configuration for every server.

To build: `./gradlew clean bootWar` (Windows: `gradlew.bat clean bootWar`). Deploy the WAR generated in `build/libs/` to a compatible container. If the WAR is named `jee-preauth-0.0.1-SNAPSHOT.war`, deployment URLs typically carry the matching context path, e.g., `https://host/jee-preauth-0.0.1-SNAPSHOT/api/whoami`; the actual context name depends on deployment/container settings. Use HTTPS because BASIC sends Base64-encoded credentials, not encrypted ones.

**Important:** if you merely run `./gradlew bootRun` with embedded Tomcat without configuring container authentication, endpoints will return `403`; do not enable Spring form login to "fix" this symptom. Provide a valid container realm or run the MockMvc tests in the next section.

## 6. Automated Testing: Simulating Container Principal/Roles

The tests below verify that Spring accepts the identity and maps roles. They intentionally **do not use `SecurityMockMvcRequestPostProcessors.user("alice")`**, because that helper creates an authentication directly in Spring Security and could let tests pass even if `J2eePreAuthenticatedProcessingFilter` were broken.

At the MockMvc layer, set the principal and user roles directly on **MockHttpServletRequest**, matching the data the container must supply in real deployments.

File `src/test/java/com/example/jee/JeePreauthTest.java`:

```java
package com.example.jee;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JeePreauthTest {

    @Autowired
    MockMvc mvc;

    @Test
    void staffPrincipalFromContainerCanReadIdentity() throws Exception {
        mvc.perform(get("/api/whoami").with(request -> {
                    request.setUserPrincipal(() -> "alice");
                    request.addUserRole("STAFF");
                    return request;
                }))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("ROLE_STAFF"));
    }

    @Test
    void staffCannotEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin").with(request -> {
                    request.setUserPrincipal(() -> "alice");
                    request.addUserRole("STAFF");
                    return request;
                }))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleFromContainerIsMappedToSpringRole() throws Exception {
        mvc.perform(get("/api/admin").with(request -> {
                    request.setUserPrincipal(() -> "bob");
                    request.addUserRole("ADMIN");
                    return request;
                }))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-ok"));
    }

    @Test
    void missingContainerPrincipalCannotBecomeAuthenticated()
            throws Exception {
        mvc.perform(get("/api/whoami"))
                .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test --tests com.example.jee.JeePreauthTest
```

Windows:

```powershell
gradlew.bat test --tests com.example.jee.JeePreauthTest
```

When configured properly, **4 tests are expected to pass**: container principal `alice` is reflected in Spring, `STAFF` is denied admin access, `ADMIN` is granted admin access, and requests missing a container principal are rejected. These HTTP statuses reflect **MockMvc + Spring Security chain**, and do not describe every status a real container might emit when rejecting credentials before Spring.

**Limitation of this test:** `MockHttpServletRequest.setUserPrincipal(...)` and `addUserRole(...)` only simulate the container layer. They do not prove Tomcat/Jetty/application server configured its realm, constraints, identity propagation, role mapping, TLS, or sessions correctly. After tests pass, you must still run **integration tests against the WAR deployed on the actual production container**.

## 7. End-to-End Verification on a Real Servlet Container

Deploy the WAR, determine the exact context path and realm, then use an HTTP client. The examples below use BASIC handled by the **container**, not Spring Basic:

```bash
# Unauthenticated: container typically returns 401 and WWW-Authenticate
curl -i https://localhost:8443/jee-preauth/api/whoami

# User in realm with STAFF
curl -i -u alice:example-password \
  https://localhost:8443/jee-preauth/api/whoami

# Authenticated STAFF without ADMIN
curl -i -u alice:example-password \
  https://localhost:8443/jee-preauth/api/admin

# User granted ADMIN by container
curl -i -u bob:example-password \
  https://localhost:8443/jee-preauth/api/admin
```

The URLs, accounts, and passwords are **illustrative data**, not live endpoints or credentials. Never put real passwords into shell history on shared machines; when needed, use interactive password prompts or a secure system secret store.

| Scenario | Container | Spring Security | Expected Outcome |
| --- | --- | --- | --- |
| No credentials for protected endpoint | Blocks/challenges, usually 401 (BASIC) | May not receive request | No data exposed |
| Alice container-authenticated with STAFF | `principal=alice`, `isUserInRole("STAFF")=true` | Maps `ROLE_STAFF`; `authenticated()` passes | `/api/whoami` returns 200, name=alice |
| Alice has STAFF but not ADMIN | Authentication succeeds | `hasRole("ADMIN")` fails | `/api/admin` returns 403 |
| Bob has ADMIN | Authentication succeeds, ADMIN true | `ROLE_ADMIN` granted | `/api/admin` returns 200 |
| No principal from container yet request reaches Spring | Unauthenticated | Pre-auth creates no user; `Http403ForbiddenEntryPoint` | 403 in the sample config |

Read container and Spring logs separately to identify which layer blocked a request. An HTTP 401 from the container is **not** necessarily a bug in `PreAuthenticatedAuthenticationProvider`; an HTTP 403 from Spring after authentication may indicate a role-mapping or authorization mismatch.

## 8. Two Ways to Grant Authorities and When to Use Each

### A. Trust the Container's JEE Roles (Example in Section 4)

- The container already manages users and roles accurately, e.g., a realm connected to LDAP/AD mapping groups → `STAFF`/`ADMIN`.
- Uses `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` and `PreAuthenticatedGrantedAuthoritiesUserDetailsService`.
- Fewer lookups against an application user store.
- Role changes require the container to refresh/apply updates per session lifecycle, caching, and server configuration.

### B. Take **Identity** from Container, Load **Business Permissions** from Application

For instance, the application has a database storing account status, tenant, department, and custom permissions. You can replace `PreAuthenticatedGrantedAuthoritiesUserDetailsService` with `UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>`:

```java
UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken> wrapper =
        new UserDetailsByNameServiceWrapper<>();

wrapper.setUserDetailsService(applicationUserDetailsService);
provider.setPreAuthenticatedUserDetailsService(wrapper);
```

This is a replacement snippet inside a configuration block that already has `provider` and `applicationUserDetailsService`, requiring imports for `UserDetailsByNameServiceWrapper` and `PreAuthenticatedAuthenticationToken`; **it is not a standalone Java program**. `applicationUserDetailsService` runs `loadUserByUsername(name)` to load internal permissions. With this approach, `isUserInRole` data from the container **does not automatically** become application permissions; you must decide when to trust container roles, when to use the internal permission store, and how to reconcile them.

**Security requirement:** the application identifier key must map stably to the container-authenticated identity. Never strip down to just the local-part of an email, drop domain/realm qualifiers, or match usernames across namespaces when collisions can occur between organizations.

## 9. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `getUserPrincipal() == null` | Container security constraint/realm not enabled, or running embedded Tomcat without container auth | Inspect container config, `web.xml`, protected URL patterns, and login mechanism |
| Container login succeeds yet Spring returns 403 on `hasRole("ADMIN")` | Container role missing, wrong case, `isUserInRole` false, or mappable roles mismatch | Measure roles at container boundary; compare `ADMIN`, `ROLE_ADMIN`, `hasRole` |
| Principal present but authorities empty | Missing details source, role mapping, or `PreAuthenticatedGrantedAuthoritiesUserDetailsService` with details not implementing `GrantedAuthoritiesContainer` | Check `setAuthenticationDetailsSource`, `setMappableRolesRetriever`, mapping |
| Spring authentication gets `ROLE_ADMIN` even without ADMIN | Container role mapping or business permission store configured too broadly | Audit role source; map only container-confirmed roles |
| Receives 401 before hitting controller | Servlet Container blocked with authentication challenge | Check access logs/container realm before debugging Spring Security |
| Unexpected re-login after one request | Container session cookie/SSO ticket not forwarded, expired, or misrouted | Check cookie/JSESSIONID, domain, SameSite, proxy, session store config |
| `ClassNotFoundException: javax.servlet...` on Boot 3 | Legacy Java EE `javax.servlet` library/container used | Boot 3 requires Jakarta Servlet `jakarta.servlet`, use Tomcat 10.1 or compatible server |
| Request has spoofed user from strange header | App trusts `X-User` or another header from the Internet | Use trusted container principal API; block spoofing at edge, reject arbitrary headers |
| Tests pass without container auth | Tests use `user()` / `@WithMockUser` creating principal directly in Spring | Test separately with `setUserPrincipal`/`addUserRole` plus an end-to-end pass through a real container |
| User A switches to B yet still sees A's permissions | Spring session holds old `Authentication` or caches are out of sync | Inspect SecurityContext persistence, principal-change handling, logout, and session invalidation |

### Operational Points to Align On

- **Trust boundary:** only a security-configured container/identity layer may assert a principal. Do not use `request.getHeader("X-User")` as a substitute for `getUserPrincipal()` without a trusted gateway, mTLS/private network, and proper verification/anti-spoofing controls.
- **Login and logout:** Spring Security pre-auth does not define container login/logout itself. When the container handles BASIC or FORM, session start/termination depends on the container/SSO; calling Spring logout alone may not terminate the external identity.
- **Permissions and roles:** authenticating a user does not grant `ROLE_ADMIN` by default. JEE roles and Spring roles can be decoupled; clearly define the authoritative permission source, mapping, and refresh rules.
- **Session/identity changes:** the application must avoid retaining an old authentication when the container principal changes or is revoked. For example, configure a context repository that skips Spring session persistence to re-read identity per request; if using session persistence, consider `setCheckForPrincipalChanges(true)` and an invalidation policy.
- **Request protection:** continue enforcing HTTPS, CORS controls, CSRF matching client/credential type, HTTP security headers, and endpoint authorization. Pre-auth does not replace those defenses.
- **Never guess from responses:** correlate every 401, 403, or redirect with the exact layer that produced it: container realm, gateway, pre-auth filter, entry point, or authorization rule.

## 10. Self-Assessment Checklist

A JEE pre-auth deployment meets requirements when evidence covers the full chain:

1. The Servlet Container genuinely authenticates users and provides the principal via `getUserPrincipal()`; clients cannot pick a principal via forged headers.
2. `isUserInRole` reflects container-granted roles, with explicit name and scope mapping.
3. `J2eePreAuthenticatedProcessingFilter` passes the verified name into a Spring `PreAuthenticatedAuthenticationToken`; the provider completes authorities.
4. Spring Security endpoints enforce `authenticated()` and `hasRole(...)` accurately: STAFF users read identity but cannot enter admin; ADMIN users enter admin.
5. Requests lacking a container principal remain blocked. Tests do not use `mockUser()` to mask integration bugs.
6. For real WAR deployments, realm, session/SSO, container challenges, and role mapping are verified separately; MockMvc tests validate only the Spring portion.

### Reference Documentation

- [Spring Security Reference – Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html)
- [Spring Security API – J2eePreAuthenticatedProcessingFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eePreAuthenticatedProcessingFilter.html)
- [Spring Security API – J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource.html)
- [Spring Security API – PreAuthenticatedAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [Spring Security API – PreAuthenticatedGrantedAuthoritiesUserDetailsService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html)
- [Spring Security API – SimpleAttributes2GrantedAuthoritiesMapper](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/authority/mapping/SimpleAttributes2GrantedAuthoritiesMapper.html)
