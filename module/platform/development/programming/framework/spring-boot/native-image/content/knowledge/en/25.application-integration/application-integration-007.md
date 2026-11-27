# Spring Security with Filter Chains, Method Security, and Identity Integration

Spring Security protects Spring Boot applications across multiple layers: the filter chain controls HTTP requests, method security guards business operations, and identity integrations authenticate users or services via `UserDetails`, JWT, OAuth 2.0, and OpenID Connect. When moving an application to **GraalVM Native Image**, standard Spring Security components already integrate with Spring AOT, yet certain dynamic application access paths still require reflection hints.

In the **`SPRING_BOOT_NATIVE_IMAGE`** module, the objective is to compile a Spring Boot application using Spring AOT, evaluate startup and memory, verify compatibility, package containers, and operate the native build. This lesson focuses on designing `SecurityFilterChain`, method authorization, and identity integration so they are AOT-analyzable; adding hints for custom principals or `Authentication` invoked via SpEL; and verifying security flows on the native executable.

> **Scope:** the primary examples use the Servlet stack (Spring MVC and `SecurityFilterChain`). WebFlux uses `SecurityWebFilterChain` and a separate reactive security context; do not mix the two models. Spring Security supports Native Image, yet classes and members accessed dynamically by your application still need verification.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of `FilterChainProxy` and the ordering of `SecurityFilterChain` beans.
- Configure request authorization for stateless APIs and session-based web logins.
- Place custom filters at the right position in the filter chain.
- Enable method security with `@EnableMethodSecurity` and protect services with `@PreAuthorize`/`@PostAuthorize`.
- Integrate custom `UserDetails`, `Authentication`, OAuth2 Resource Server, and OIDC Login.
- Identify when SpEL method calls on a custom principal require reflection hints.
- Distinguish Spring Security's built-in Native Image support from application-specific hints.
- Test authentication, authorization, method security, and identity providers on the native executable.

## 2. Three-Layer Security Architecture

A request entering a Servlet application typically passes through these layers:

1. **Servlet filter chain:** receives the request from the container and delegates into Spring Security.
2. **Security filter chain:** loads `SecurityContext`, protects the request, authenticates credentials, and enforces request authorization.
3. **Method security:** when a controller/service calls a protected Spring bean, an interceptor checks permissions before or after method execution.

Identity can come from many sources: username/password, JWT bearer tokens, opaque tokens, OAuth2 Login/OIDC, or a custom authentication system. Spring Security turns the authentication result into an `Authentication` and places it into `SecurityContext` for authorization layers to inspect.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet container filters"]
    B --> C["DelegatingFilterProxy"]
    C --> D["FilterChainProxy"]
    D --> E["Matching SecurityFilterChain"]
    E --> F["Load SecurityContext"]
    F --> G["Authentication filters"]
    G --> H["Request authorization"]
    H --> I["Controller"]
    I --> J["Spring service proxy"]
    J --> K["Method authorization"]
    K --> L["Business method"]
    M["UserDetails / JWT / OIDC / custom Authentication"] --> G
~~~

With Native Image, standard filters and authorization managers already belong to Spring Security. Parts requiring extra review usually lie in custom filters, custom principals, SpEL expressions, serializers, or identity libraries integrated by the application.

## 3. SecurityFilterChain and Request Processing Order

A `SecurityFilterChain` is a set of filters applied to a group of requests. `FilterChainProxy` evaluates chains in order and selects **the first chain whose matcher matches**. If multiple chains match a URL, subsequent chains are not applied to that request.

Example API using bearer tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this example:

- The health endpoint and catalog GET requests are public.
- `/api/admin/**` requires authority `ROLE_ADMIN` because `hasRole("ADMIN")` automatically prepends `ROLE_`.
- All remaining requests require authentication.
- The API uses bearer tokens without cookies/sessions, so it is configured as stateless.
- CSRF is disabled for this chain because credentials are sent via the `Authorization` header; do not copy this choice to a cookie/session web application without evaluating CSRF.

### Multiple Filter Chains

An application can separate API and browser login into distinct chains:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

The first chain matches only `/api/**`; the second handles everything else. When creating multiple chains, verify:

- Does `securityMatcher` cover the intended URLs?
- Does `@Order` place specific chains before general fallback chains?
- Are there any requests that fail to match any chain?
- Are Actuator endpoints protected intentionally?

Defining a custom `SecurityFilterChain` bean causes Spring Boot to back off its default web security configuration. The application then becomes responsible for declaring all required rules. Spring Boot may still configure a default `UserDetailsService` if no corresponding authentication bean exists and dependencies do not cause that auto-configuration to back off.

## 4. Custom Filters: Choosing the Right Position

Custom filters are commonly used to check tenants, correlation identities, or custom credential types. Filter order matters because it determines whether `SecurityContext` has been loaded or authentication has already run.

| Filter Type | Typical Suitable Position |
|---|---|
| Custom authentication filter | After `LogoutFilter` and before authorization steps |
| Filter reading authenticated principal to check tenant | After `AnonymousAuthenticationFilter` |
| Filter guarding requests before authentication | After `SecurityContextHolderFilter`, depending on purpose |

Example filter checking tenant access after authentication has run:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class TenantAccessFilter extends OncePerRequestFilter {

    private final TenantAuthorizationService tenantAuthorizationService;

    public TenantAccessFilter(TenantAuthorizationService tenantAuthorizationService) {
        this.tenantAuthorizationService = tenantAuthorizationService;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            filterChain.doFilter(request, response);
            return;
        }

        String tenantId = request.getHeader("X-Tenant-Id");
        if (tenantId == null
                || !tenantAuthorizationService.canAccess(authentication, tenantId)) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        filterChain.doFilter(request, response);
    }
}
~~~

Registering the filter in the chain:

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(
        HttpSecurity http,
        TenantAccessFilter tenantAccessFilter) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .addFilterAfter(
            tenantAccessFilter,
            AnonymousAuthenticationFilter.class);

    return http.build();
}
~~~

If a filter is declared as a Spring bean in a Spring Boot Servlet application, Boot may also register it directly with the servlet container. When the filter should run only inside the Spring Security chain, disable the separate servlet registration:

~~~java
@Bean
FilterRegistrationBean<TenantAccessFilter> tenantFilterServletRegistration(
        TenantAccessFilter filter) {
    FilterRegistrationBean<TenantAccessFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

This prevents the filter from executing twice on the same request. If the filter is instantiated directly and only added to the chain, no separate servlet registration exists to disable.

### Custom Filters and Native Image

The fact that a filter is a custom class **does not automatically mean reflection hints are required**. If the filter is created by Spring via constructor injection and attached directly to the chain, AOT can usually process the standard bean structure. Hints are needed only when the filter or a library it uses performs dynamic access that the builder cannot infer, such as:

- Calling methods on a principal via reflection/SpEL.
- Loading an implementation by a class name read from configuration.
- Reading a resource using a dynamically constructed name.
- Creating JDK proxies or using JNI without metadata.

Inspect actual native errors and add hints for the exact class/member/resource. Do not register broad reflection for all filters and every Spring Security class.

## 5. Method Security Protecting the Business Layer

Request authorization answers "which endpoint may this request reach?" Method security answers "is this user permitted to invoke this specific business operation?"

Spring Boot Starter Security does not enable method-level authorization automatically. Enable it explicitly with `@EnableMethodSecurity`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

You can then use `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` on Spring-managed beans:

~~~java
@Service
public class InvoiceService {

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice findById(String invoiceId) {
        return loadInvoice(invoiceId);
    }

    @PreAuthorize(
        "hasAuthority('invoice:read:any') or #ownerId == authentication.name")
    public List<Invoice> findForOwner(String ownerId) {
        return loadInvoices(ownerId);
    }

    @PostAuthorize(
        "returnObject.ownerId == authentication.name or hasAuthority('invoice:read:any')")
    public Invoice read(String invoiceId) {
        return loadInvoice(invoiceId);
    }
}
~~~

Meaning:

- `hasAuthority` matches the exact authority string.
- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority.
- `@PreAuthorize` evaluates before the method runs.
- `@PostAuthorize` evaluates against the result after the method returns.
- `#ownerId` accesses a method parameter; `returnObject` refers to the return value.

Method security uses Spring AOP proxies. Calls must pass through the Spring bean proxy for the interceptor to apply. Calling a secured method from another method in the same instance (self-invocation via `this`) bypasses the proxy and can skip the interceptor; structure services or invoke across proper bean boundaries.

### Distinguishing Roles and Authorities

| Expression | Rule |
|---|---|
| `hasRole("ADMIN")` | Checks `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Checks exact string `ROLE_ADMIN` |
| `hasAuthority("invoice:read")` | Checks exact permission `invoice:read` |
| `hasAnyAuthority("invoice:read", "invoice:read:any")` | Allows any of the listed permissions |

Standardize authority conventions across the identity provider, JWT converters, `UserDetails`, and method security.

## 6. Custom UserDetails and Principals in SpEL Expressions

A particularly important use case for Native Image is SpEL invoking methods on a custom principal. Example custom `UserDetails`:

~~~java
import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public class CustomUserDetails implements UserDetails {

    private final String username;
    private final String password;
    private final Collection<? extends GrantedAuthority> authorities;

    public CustomUserDetails(
            String username,
            String password,
            Collection<? extends GrantedAuthority> authorities) {
        this.username = username;
        this.password = password;
        this.authorities = authorities;
    }

    public boolean isAdmin() {
        return this.authorities.contains(
                new SimpleGrantedAuthority("ROLE_ADMIN"));
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return password;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

Service using the principal's method:

~~~java
@Service
public class AdminReportService {

    @PreAuthorize("principal?.isAdmin()")
    public Report generateSensitiveReport() {
        return createReport();
    }
}
~~~

Spring Security evaluates the expression and may use reflection to invoke `isAdmin()`. Native Image does not allow arbitrary reflective access by default. If this method or class is not covered by hints, the application may work on the JVM yet fail when invoking the method on the native executable.

Spring Security recommends registering custom `UserDetails` classes with `@RegisterReflectionForBinding`:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding(CustomUserDetails.class)
class SecurityRuntimeHintsConfiguration {
}
~~~

If `@PreAuthorize`/`@PostAuthorize` expressions reference multiple custom principal or `Authentication` types, register all corresponding types and test every expression. Do not register only the first principal class and assume every data type used in SpEL already has metadata.

### When SpEL Calls a Dedicated Authorization Bean

Complex authorization logic can be extracted into a bean:

~~~java
@Component("invoiceAuthz")
public class InvoiceAuthorization {

    public boolean canRead(Authentication authentication, Invoice invoice) {
        return invoice.ownerId().equals(authentication.getName())
                || authentication.getAuthorities().stream()
                    .anyMatch(authority ->
                        authority.getAuthority().equals("invoice:read:any"));
    }
}
~~~

~~~java
@PreAuthorize("@invoiceAuthz.canRead(authentication, #invoice)")
public Invoice read(Invoice invoice) {
    return loadInvoice(invoice.id());
}
~~~

Spring Security AOT can scan Spring beans for methods annotated with `@PreAuthorize` or `@PostAuthorize`, resolve beans referenced in security expressions, and register appropriate runtime hints for those beans. Even so, custom types invoked dynamically inside expressions still need separate verification.

## 7. Integrating Username/Password via UserDetailsService

For applications using form login or HTTP Basic, `UserDetailsService` loads account details and `PasswordEncoder` verifies passwords:

~~~java
@Configuration(proxyBeanMethods = false)
class PasswordAuthenticationConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            AccountRepository accounts) {
        return username -> accounts.findByUsername(username)
                .map(account -> new CustomUserDetails(
                        account.username(),
                        account.passwordHash(),
                        account.authorities()))
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));
    }
}
~~~

Passwords stored in the database must be password hashes generated by `PasswordEncoder`; never store plain text. For production, configure rate limiting, lockout policies, MFA, or an appropriate identity provider mechanism.

If `CustomUserDetails` is only used to supply `getUsername()`/`getAuthorities()` via static access paths, extra hints may not be necessary. If SpEL or a library calls its methods/fields via reflection, add binding hints as shown earlier and test on native.

## 8. OAuth2 Resource Server with JWT

Resource Server validates bearer tokens from clients and populates `Authentication`. For JWTs, Spring Security uses `JwtDecoder` to verify signatures, issuer, expiration, and decode claims.

Spring Boot dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Spring Boot can auto-configure Resource Server from this property. To customize the chain manually, use:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

### Mapping Claims to Authorities

An identity provider may issue a custom `roles` claim. Use `JwtAuthenticationConverter` to convert claims into `GrantedAuthority` instances:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopesConverter =
            new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopesConverter.convert(jwt));

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            roles.stream()
                    .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                    .forEach(authorities::add);
        }
        return authorities;
    });
    return converter;
}
~~~

Attach the converter to the resource server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
~~~

Method security can then use `hasRole("ADMIN")` or `hasAuthority("SCOPE_invoice.read")` according to the chosen convention.

### JWT and Native Image

Standard Spring Security Resource Server components are supported on Native Image. When an application uses custom converters, custom `Authentication`, or SpEL calling methods on principals, check additionally:

- Are custom classes processed by AOT as Spring beans?
- Is there any un-inferred reflective access?
- Are public keys, certificates, or config files read as classpath resources?
- Is the JWK endpoint/issuer reachable from the native runtime environment?

`issuer-uri` typically requires identity provider metadata discovery and fetching the JWK set as needed. That is a runtime network operation. If you want to configure the JWK Set URI directly, you can use `jwk-set-uri`; if issuer validation is still needed, configure the issuer accordingly per Spring Security documentation. Do not confuse network discovery with classpath resource hints.

## 9. Opaque Tokens and Introspection

With opaque bearer tokens, the application does not decode JWTs locally. It sends the token to the authorization server for introspection and receives token validity, subject, and scopes.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Spring Security uses `OpaqueTokenIntrospector` to validate tokens. Introspection credentials must come from a secret manager or securely managed environment; never commit secrets into the repository.

In the native executable, verify:

- Container DNS, networking, proxy, and TLS trust configuration.
- Whether the authorization server is reachable from the deployment environment.
- Timeout, retry, and failure behavior when the introspection endpoint is unavailable.
- Whether authorities map properly to endpoints/methods.

This is primarily a network/runtime integration check; add reflection hints only if a custom introspector performs dynamic access not recognized by AOT.

## 10. OAuth2 Login and OpenID Connect

OAuth2 Client can log users in via OAuth 2.0 or OIDC. With OIDC, the `openid` scope causes Spring Security to engage OIDC components such as `OidcUserService` and validate ID tokens.

Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Registration configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company-idp:
            issuer-uri: https://identity.example.com
~~~

Enable OAuth2 Login in the chain:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .oauth2Login(Customizer.withDefaults());
~~~

Spring Security exposes login/redirect endpoints based on registration configuration. The redirect URI must match the identity provider's configuration and the external URL exposed by any reverse proxy. Inside containers, verify forwarded headers, HTTPS scheme, and host so callback URIs are built accurately.

### Native Integration Requires Testing the Full Flow

Do not only verify that the login page returns a redirect. Verify:

1. The authorization request is built with the right client, scopes, and redirect URI.
2. The callback receives the authorization code.
3. The token endpoint is called and the ID token is validated.
4. The UserInfo endpoint is called if required by configuration.
5. The user is mapped to the expected principal/authorities.
6. The session or authorized client is stored and reused on subsequent requests.

If using a custom `OAuth2UserService`/`OidcUserService`, check custom principals and methods called via SpEL or libraries using reflection. Never put real client secrets or tokens into logs or test fixtures.

## 11. Mapping Identity to a Business Principal

In a multi-tenant system, the principal may carry a user ID, tenant ID, and normalized permissions. You can use a custom `UserDetails` for username/password or a custom `OAuth2User`/`OidcUser` for federated login.

~~~java
public record ApplicationPrincipal(
        String userId,
        String tenantId,
        Set<String> permissions) {

    public boolean canManageTenant() {
        return permissions.contains("tenant:manage");
    }
}
~~~

When translating identity from an external provider, consume only verified claims and map them to the internal model. Never trust client-supplied headers like `X-User-Id` or `X-Roles` unless they are set by a trusted proxy with verified authentication and clear network boundaries.

If a security expression calls `principal.canManageTenant()`, confirm the principal type is retained and the method has the required reflection hint. You can register the class with:

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding(ApplicationPrincipal.class)
class PrincipalHintsConfiguration {
}
~~~

If the principal is wrapped in a custom `Authentication`, register that custom class too when expressions or libraries access it via reflection. Hints do not replace validating claim provenance and authorization rules.

## 12. What Does Spring Security AOT Handle Automatically?

Spring Security integrates with Spring AOT and Native Image. Many standard components such as filter chains, authentication managers, request authorization, JWT Resource Server, and method security work without requiring users to register every framework class manually.

For method security, Spring Security AOT can:

- Scan Spring beans in the `ApplicationContext` for methods annotated with `@PreAuthorize` or `@PostAuthorize`.
- Resolve bean names referenced in security expressions.
- Register appropriate runtime hints for referenced beans.
- For return-object authorization features supported in the corresponding version, inspect return types for related security annotations.

However, applications may still need hints for custom `UserDetails`, custom `Authentication`, or types whose methods SpEL invokes dynamically. Distinguish accordingly:

| Component | Handling Approach |
|---|---|
| Standard filters/authorization managers | Use Spring Security integration; do not register bulk reflection manually |
| Statically configured `SecurityFilterChain` | Let Spring AOT handle standard bean/configuration processing |
| Custom principal used in SpEL | Register reflection binding hints when needed |
| Custom method invoked via reflection | Identify the exact member and register the appropriate hint |
| Public key/certificate/schema read from classpath | Check resource hints if not automatically detected by the framework |
| Custom OAuth2 service or converter | Test on native; add hints for actual dynamic access |

## 13. Registering Runtime Hints When Needed

For custom principals, `@RegisterReflectionForBinding` is usually the simplest option and aligns with Spring Security guidance.

If a custom library invokes a specific method outside binding, you can use `RuntimeHintsRegistrar` to register method invocation:

~~~java
public class SecurityRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
                ApplicationPrincipal.class, "canManageTenant");
        if (method != null) {
            hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
        }
    }
}
~~~

Register the registrar via `@ImportRuntimeHints` on a configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(SecurityRuntimeHints.class)
class SecurityHintsConfiguration {
}
~~~

This example illustrates registering a narrow method invocation hint. In a real project, check the Spring Framework API version in use and verify whether `@RegisterReflectionForBinding` already covers the use case. Do not add both mechanisms for the same access without reason.

## 14. Testing Request Authorization and Method Security

Test the two authorization layers independently. An endpoint may be rejected by request filters before method security runs; conversely, a request may enter the controller while the service denies the operation.

### Testing the Filter Chain with MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class InvoiceSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/invoices/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedJwtCanReadInvoice() throws Exception {
        mockMvc.perform(get("/api/invoices/42")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("invoice:read"))))
                .andExpect(status().isOk());
    }
}
~~~

The `jwt()` request post-processor from Spring Security Test creates a mock `Authentication` for MVC tests. It tests request authorization and controller mapping, yet does not verify real JWT signature validation by the decoder.

### Testing Method Security

~~~java
@SpringBootTest
class InvoiceMethodSecurityTests {

    @Autowired
    InvoiceService invoiceService;

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanLoadInvoice() {
        assertThat(invoiceService.findById("INV-100")).isNotNull();
    }

    @Test
    @WithMockUser(authorities = "invoice:write")
    void writerWithoutReadPermissionIsDenied() {
        assertThatThrownBy(() -> invoiceService.findById("INV-100"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

These tests verify that method security proxies apply when invoked through Spring beans. For custom principals, write dedicated tests using the actual production principal type and security expressions.

## 15. Native Integration Tests for Identity Flows

Native tests must verify what mock tests cannot prove. For a JWT Resource Server, include tests using real tokens signed by test keys and a local JWK endpoint:

- Tokens without a valid signature are rejected.
- Expired tokens are rejected.
- Wrong issuer/audience is rejected per policy.
- Valid tokens are converted into `Authentication`.
- Role/scope claims map accurately to authorities.
- Requests are permitted through both the filter chain and method security.
- Valid tokens lacking permissions receive HTTP 403 at the right layer.

For OIDC Login, use a mock identity provider in integration tests to test authorization redirects, callbacks, token exchange, and principal mapping. Avoid depending on public identity providers in CI tests whenever possible.

### Running Native Tests

If the build has Native Build Tools and Spring AOT configured:

~~~bash
# Gradle
./gradlew nativeTest

# Maven profile with nativeTest configured
./mvnw test -PnativeTest
~~~

Profile/task names depend on project configuration. Beyond native tests, build and run the final application executable inside a container to verify networking, TLS, session stores, cookies, reverse proxies, and environment variables.

### Testing Custom Principals in Native

If method security evaluates `principal.isAdmin()`:

1. Run JVM tests to verify expression logic.
2. Register `CustomUserDetails` with `@RegisterReflectionForBinding`.
3. Build AOT/native.
4. Invoke the protected method with the custom principal in the native executable.
5. Verify both allowed and denied cases.

Do not only check that the build succeeded. SpEL reflection errors often surface only when the method security expression is actually evaluated.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Endpoint requires authentication despite permit rule | Request matched another chain or chain order/matcher is wrong | Check `@Order`, `securityMatcher`, and first-match ordering |
| Custom filter runs twice | Filter bean is registered both with the servlet container and inside `SecurityFilterChain` | Disable servlet registration if the filter belongs only to the security chain |
| Filter does not see principal | Filter placed before authentication filter or request is unauthenticated | Place at the right position relative to expected authentication events |
| `@PreAuthorize` does not run | `@EnableMethodSecurity` missing, method not called via Spring proxy, or unmanaged bean | Check configuration, bean boundaries, and self-invocation |
| SpEL cannot find method on custom principal in native | Missing reflection hints for custom `UserDetails`/`Authentication` | Use `@RegisterReflectionForBinding` for the custom type |
| Roles do not match | JWT claim mapping and `ROLE_`/scope conventions inconsistent | Check converter and use `hasRole`/`hasAuthority` as intended |
| JWT valid on JVM but native cannot reach JWK endpoint | DNS/TLS/network/container configuration | Check runtime connectivity, trust store, and issuer/JWK URI |
| OIDC callback uses wrong redirect URI | Reverse proxy/forwarded headers or registration URI mismatch | Align external URL and forwarded header configuration |
| Native build passes but custom auth flow fails | Tests did not exercise custom principal, converter, or provider | Add native integration tests covering that exact code path |

## 17. Pre-Release Checklist

- [ ] Classify the application as Servlet or WebFlux; use the matching security chain type.
- [ ] Verify `SecurityFilterChain` ordering and matchers for every endpoint group.
- [ ] Enable CSRF appropriately for how credentials are stored (cookies/sessions vs. bearer headers).
- [ ] Review session policy, CORS, logout, and error handling.
- [ ] Position custom filters properly in the authentication/authorization flow.
- [ ] Prevent double registration of custom filters across servlet container and security chain.
- [ ] Enable `@EnableMethodSecurity` if using method annotations.
- [ ] Verify methods are called through Spring proxies without self-invocation bypasses.
- [ ] Standardize roles/authorities across `UserDetails`, JWT claims, and SpEL.
- [ ] Register hints for custom `UserDetails`/`Authentication` invoked via SpEL when needed.
- [ ] Test JWT signature, issuer, expiry, audience, and authority mapping.
- [ ] Test OIDC callbacks/sessions if using OAuth2 Login.
- [ ] Manage client secrets, signing keys, and credentials via a secret manager/environment.
- [ ] Run JVM tests, AOT/native tests, and smoke tests on the final executable.
- [ ] Test inside containers with realistic TLS, DNS, proxy, cookie, and forwarded-header settings.

## 18. Self-Check Exercises

**Question 1.** How does `FilterChainProxy` choose a `SecurityFilterChain` when multiple chains exist?

**Hint:** it evaluates them in order and uses only the first chain whose matcher matches.

**Question 2.** Why can a stateless API using bearer tokens disable CSRF in the example, whereas a cookie/session web login typically must keep CSRF enabled?

**Hint:** CSRF exploits credentials automatically sent by browsers such as cookies; bearer tokens explicitly placed in headers by clients have a different threat model. Evaluate how credentials are stored and transmitted.

**Question 3.** Is `@EnableMethodSecurity` enabled automatically by Spring Boot Starter Security?

**Hint:** no. It must be enabled explicitly to use `@PreAuthorize`/`@PostAuthorize`.

**Question 4.** Why might a custom `UserDetails` require reflection hints in Native Image?

**Hint:** SpEL may use reflection to invoke methods like `principal.isAdmin()`; the class/member must be registered.

**Question 5.** Does `@RegisterReflectionForBinding` need to be applied to every class in Spring Security?

**Hint:** no. Spring Security already supports Native Image; add hints only for custom types/dynamic accesses not inferred by the framework.

**Question 6.** Does a MockMvc test using `jwt()` prove that the JWT decoder verifies real signatures?

**Hint:** no. It constructs a mock `Authentication`; integration tests with real signed tokens and JWK/decoder are required.

**Question 7.** With WebFlux, should you read `SecurityContext` directly via `SecurityContextHolder` in a custom reactive filter?

**Hint:** no. The reactive stack stores security context in Reactor `Context`; use the appropriate reactive security APIs.

## 19. References

- [Spring Security — GraalVM Native Image Support](https://docs.spring.io/spring-security/reference/native-image/index.html): overview of Native Image support and cases needing extra hints.
- [Spring Security — Method Security in GraalVM Native Image](https://docs.spring.io/spring-security/reference/native-image/method-security.html): custom `UserDetails`/`Authentication`, SpEL, and `@RegisterReflectionForBinding`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, and Spring Security AOT.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, filter ordering, and adding custom filters.
- [Spring Security — OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/): Resource Server, OAuth2 Client, OAuth2 Login, and OIDC.
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): auto-configuration, custom `SecurityFilterChain`, MVC, and WebFlux security.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): Runtime Hints, reflection, resources, and proxy metadata.

**Key Takeaway:** Spring Security supports Native Image out of the box for standard features. Configure filter chains and method authorization with normal Spring Security APIs; focus verification on custom principals, `Authentication` types, expressions, and filters with dynamic access. Combine JVM security tests with native integration tests for JWT/OIDC and method authorization to verify bean topology, reflection hints, and actual authentication/authorization behavior in the final executable.
