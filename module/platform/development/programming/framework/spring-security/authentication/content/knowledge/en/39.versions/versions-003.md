# AuthenticationManager, AuthenticationProvider Beans, and Modern Spring Security Configuration

From Spring Security 5.7 through the 6.x and 7.x branches, Servlet security configuration relies increasingly on **Spring beans** and the **lambda DSL**, replacing `WebSecurityConfigurerAdapter` inheritance. A common source of confusion is: once you have a `SecurityFilterChain` bean, where does **AuthenticationManager** come from? When is `UserDetailsService` alone enough, and when must you create `AuthenticationProvider` and `ProviderManager`? Does defining a new bean make the login filter use that bean? Why does old code using `new DaoAuthenticationProvider()` compile in one version yet fail in a newer one?

This lesson clarifies **components, wiring, global vs. local scope, version differences, Java 17+ examples, testing, and common configuration mistakes**. The focus is **Spring Security Servlet**; WebFlux uses `ReactiveAuthenticationManager` and `SecurityWebFilterChain`, and Servlet beans cannot be copied verbatim into the reactive stack.

**Goals after this lesson:** identify what builds the AuthenticationManager for a filter chain; configure username/password with modern beans without creating redundant managers; deliberately publish a manager for custom REST login; compose multiple providers with proper `supports(...)` and ordering; handle credential erasure/events/HTTP sessions properly; and recognize why a Spring Security 5.x snippet is incompatible with 6.x/7.x.

## 1. The Big Picture of Servlet Authentication

An HTTP request carrying credentials crosses distinct boundaries:

~~~text
Browser / HTTP client
        |
        v
SecurityFilterChain (Servlet)
        |
        +-- Authentication filter:
        |     UsernamePasswordAuthenticationFilter
        |     BasicAuthenticationFilter / custom filter / ...
        |
        +-- Creates an UNAUTHENTICATED Authentication request
        |
        v
AuthenticationManager.authenticate(authentication)
        |
        v
ProviderManager (common implementation)
        |
        +-- AuthenticationProvider 1: supports token type?
        +-- AuthenticationProvider 2: supports token type?
        +-- ...
        |
        v
AuthenticationProvider verifies credentials and account policy
        |
        +-- Success -> returns AUTHENTICATED Authentication
        +-- Failure -> AuthenticationException
        +-- Cannot decide -> null / next provider
        |
        v
Filter handles success/failure, session, and SecurityContext
        |
        v
Authorization checks authorities on subsequent requests
~~~

**`AuthenticationManager` is neither a user nor a session store.** It is the interface for an authentication invocation. `AuthenticationProvider` is the strategy doing verification work for a specific credential type. `SecurityFilterChain` selects the filters and HTTP rules; `SecurityContextHolder` holds the Authentication for the current processing scope; `SecurityContextRepository` handles persistence when needed.

### Key Components

| Component | Role | Common API |
| --- | --- | --- |
| `SecurityFilterChain` | Configures which filters run and HTTP access rules | `http.authorizeHttpRequests(...)`, `http.formLogin(...)` |
| `AuthenticationManager` | Authentication entry point called by filters/controllers | `authenticate(Authentication)` |
| `ProviderManager` | Iterates through AuthenticationProviders | `new ProviderManager(provider)` or List |
| `AuthenticationProvider` | Authenticates one category of tokens | `supports(Class<?>)`, `authenticate(...)` |
| `DaoAuthenticationProvider` | Username/password via a user store | `UserDetailsService` + `PasswordEncoder` |
| `UserDetailsService` | Loads user info, password hash, status/authorities | `loadUserByUsername(...)` |
| `PasswordEncoder` | Compares/encodes password hashes | `matches(raw, encoded)`, `encode(raw)` |
| `Authentication` | Unauthenticated input token or verified identity | `UsernamePasswordAuthenticationToken` |
| `AuthenticationEventPublisher` | Success/failure events if configured on the manager | `DefaultAuthenticationEventPublisher` |
| `SecurityContextRepository` | Persists context for subsequent HTTP requests | `saveContext(...)` |

**A UserDetailsService does not compare passwords itself**: `DaoAuthenticationProvider` calls the user service and then uses the encoder to compare the submitted password against the stored hash. **PasswordEncoder is not an AuthenticationProvider**, and **AuthenticationManager does not issue session cookies on its own**.

## 2. Important Version Milestones

| Branch | Notable Changes | Recommended Style |
| --- | --- | --- |
| Spring Security 5.4 | Initial support for `SecurityFilterChain` bean configuration | Gradually move away from inheritance |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` deprecated | Component-based beans |
| Spring Security 6.x | Removed `WebSecurityConfigurerAdapter`, moved to Jakarta Servlet, dropped legacy matcher APIs | `@Bean SecurityFilterChain`, `requestMatchers`, lambda DSL |
| Spring Security 6.5 | Older constructors/setters of `DaoAuthenticationProvider` deprecated | Constructor taking `UserDetailsService` |
| Spring Security 7.x | Lambda DSL configuration is the modern standard; `DaoAuthenticationProvider(UserDetailsService)` is used in 7.x docs | Keep bean-based config, avoid removed APIs |

If a project uses Spring Boot, the Spring Security version is normally chosen by Boot’s dependency management. **Do not manually pin `spring-security-config` to a different version from `spring-security-web`**. Use the BOM and inspect the application’s dependency tree.

Common compatibility pairings:

- Spring Boot 2.x pairs with Spring Security 5.x (javax Servlet).
- Spring Boot 3.x pairs with Spring Security 6.x (Jakarta Servlet).
- Spring Boot 4.x pairs with Spring Security 7.x (Jakarta Servlet).

These are **generational compatibility groupings**, not an exact mapping table for every minor release. Before upgrading, inspect the specific dependency tree/BOM and the corresponding migration guides.

### Legacy Code That Must Be Replaced

~~~java
// Spring Security 5.x style; do not use after upgrading to 6/7:
class SecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests().anyRequest().authenticated();
    }
}
~~~

Modernizing is not just deleting `extends`; you must convert declarations into beans, update matchers, and review authentication wiring. For example:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

This fragment needs imports for `@Configuration`, `@EnableWebSecurity`, `@Bean`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer`. There is no `WebSecurityConfigurerAdapter` and no `configure(...)` override.

**Do not treat `permitAll()`, `web.ignoring()`, and `requestMatchers()` as identical**: `permitAll()` still passes through the security filter chain and can preserve security headers/CSRF behavior; `web.ignoring()` bypasses the chain for that request. For login/public endpoints, usually prefer `permitAll()` rather than disabling all security filters.

## 3. When Do You Not Need to Define an AuthenticationManager Bean?

For a typical form login/HTTP Basic application, you may only need:

1. `SecurityFilterChain` for HTTP configuration;
2. `UserDetailsService` to load users;
3. `PasswordEncoder` to verify password hashes.

Spring Security can build `DaoAuthenticationProvider` and `AuthenticationManager` internally when configured appropriately. **Not every project needs to write `@Bean AuthenticationManager`**.

Structurally complete example for Spring Boot Servlet:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;

@Configuration(proxyBeanMethods = false)
public class SimpleSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("training-password-only"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Runs inside a Spring Boot project**, not as a standalone Java class compiled with `javac`. Requires Spring Web and Spring Security starters, a main `@SpringBootApplication`, and protected routes. The `alice` account here is a **learning fixture**, not an example of production password deployment. Do not commit test passwords to a real application’s Git repository; production uses a managed user store and hashes.

Why the code stays simple:

- `UserDetailsService` only supplies UserDetails;
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` handles password hashes using delegating format (for example the `{bcrypt}` prefix by default);
- Spring Security can use the built-in provider to support form login;
- There is no need to create a duplicate `ProviderManager` alongside the one the framework already builds.

**Condition to check:** if there are multiple UserDetailsService beans or multiple AuthenticationProvider beans, or you configured AuthenticationManagerBuilder manually, auto-wiring may behave differently. Do not assume every bean is automatically gathered into one manager; inspect the actual chain and configuration, or declare explicit composition deliberately.

## 4. How Do AuthenticationManager and ProviderManager Differ?

`AuthenticationManager` is an interface:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

This is an abbreviated signature representation for explanation, **not a redeclaration of the interface in your project**.

`ProviderManager` is the standard implementation. It holds a list of `AuthenticationProvider` instances. Each provider indicates via `supports(Class<?>)` whether it handles that type of Authentication.

Flow:

~~~text
Request: UsernamePasswordAuthenticationToken
   |
   v
ProviderManager
   |
   +-- DaoAuthenticationProvider.supports(...) -> true
   |        |
   |        +-- valid credential -> authenticated Authentication
   |        +-- invalid -> AuthenticationException
   |
   +-- CustomApiKeyProvider.supports(...) -> false (skipped)
   |
   +-- No provider supports -> ProviderNotFoundException
~~~

A provider returning `null` means **it makes no decision**, allowing the manager to try the next provider. If a supporting provider throws an exception, the manager applies handling logic depending on the exception type; some account-status/service exceptions can stop further attempts. Do not assume every exception is ignored to try the next provider or that every provider returning null means “bad credentials”.

**Provider ordering matters** when multiple providers support the same Authentication token. You must define who is authoritative to verify, who can abstain, which exception types must halt the flow, and whether credential downgrade could occur.

`ProviderManager` can have a parent `AuthenticationManager`. The parent is consulted when local providers do not handle the request per contract. A parent/shared manager is useful across multiple filter chains, but can blur boundaries or emit duplicate events if misconfigured.

## 5. When Do You Need an AuthenticationManager @Bean?

There are three common reasons:

1. **A custom REST/controller** calls `authenticate(...)` directly instead of using a built-in login filter.
2. You want to configure **an explicit set of providers** and policies such as an event publisher or credential erasure.
3. Multiple `SecurityFilterChain` beans need separate/local managers, or a shared manager for common mechanisms.

Bean-style example publishing a password manager:

~~~java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);

    return new ProviderManager(provider);
}
~~~

This is a **fragment inside `@Configuration`**, using the constructor taking `UserDetailsService` compatible with Spring Security 6.5 and 7.x. Do not use `new DaoAuthenticationProvider()` followed by `setUserDetailsService(...)` in new code; that no-arg constructor and setter were deprecated in 6.5 and removed in 7.x APIs.

**A `@Bean AuthenticationManager` can be injected**, but do not conclude every chain automatically picks that exact instance in every complex configuration. When you want a chain to use that manager, wire it **explicitly**:

~~~java
@Bean
SecurityFilterChain formChain(
        HttpSecurity http,
        AuthenticationManager authenticationManager) throws Exception {

    return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Do not declare a manager bean when there is only one provider and built-in form auth already works properly; the more custom beans you add, the more tests you need to ensure the runtime manager matches what you expect.

### Spring Bean Scope Is Not Token Scope

`AuthenticationManager` and `AuthenticationProvider` are usually **singleton beans** holding configuration/strategies, not one bean per user. Never store raw passwords, the current request’s mutable `Authentication`, or user-specific session data in fields of a singleton provider.

Every authentication attempt creates its own `Authentication`; the manager/provider processes the request. Post-success session and Authentication context are managed by filters/controllers and repositories, not by a singleton manager holding the “currently logged-in user”.

## 6. Explicit Configuration Pattern Compatible with Spring Security 6.5+/7.x

When you need to guarantee the right manager and the right provider, you can use the following pattern for a Spring Boot Servlet application. It defines beans, main imports, and the security chain; **it requires a Spring Boot runtime and does not run standalone via `javac`**.

File **ExplicitAuthenticationConfig.java**:

~~~java
package demo.security;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ExplicitAuthenticationConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("demo")
                .password(encoder.encode("training-password-only"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(demo);
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService service, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(service);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher events) {
        return new DefaultAuthenticationEventPublisher(events);
    }

    @Bean
    AuthenticationManager authenticationManager(
            DaoAuthenticationProvider dao,
            AuthenticationEventPublisher events) {
        ProviderManager manager = new ProviderManager(dao);
        manager.setAuthenticationEventPublisher(events);
        return manager;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager)
            throws Exception {
        return http
                .authenticationManager(authenticationManager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Points to check in this pattern:**

- `DaoAuthenticationProvider(UserDetailsService)` is the 6.5/7.x-compatible constructor, paired with `setPasswordEncoder(...)`.
- `PasswordEncoder` is a single bean so sign-up, password change, and login share the same hashing rules.
- `ProviderManager` has only **one password provider**, avoiding accidentally accepting other authentication types.
- `ProviderManager#setAuthenticationEventPublisher(...)` is called explicitly because a manually constructed manager **does not publish events by default**.
- `HttpSecurity.authenticationManager(authenticationManager)` binds the manager to that specific chain without relying on auto-wiring inference.
- `@Configuration(proxyBeanMethods=false)` uses method-parameter injection instead of calling `@Bean` methods directly, avoiding errors when config classes do not proxy methods.
- `formLogin(...)` uses the standard filter, which handles success/failure, security context, and session strategy per framework rules.
- InMemory user/password is for **demo/testing only**; never hardcode credentials in production.

If Spring Boot already auto-creates a `UserDetailsService` or the application has multiple user stores, check for **duplicate beans**. When configuring a custom ProviderManager, do not add a duplicate DaoAuthenticationProvider via another builder without defining order and purpose.

## 7. Obtaining AuthenticationManager for Custom REST Login

In a Spring-managed controller/service, you can inject the bean:

~~~java
@RestController
@RequestMapping("/auth")
public class LoginController {

    private final AuthenticationManager manager;

    public LoginController(AuthenticationManager manager) {
        this.manager = manager;
    }

    @PostMapping("/verify")
    public String verify(@RequestBody LoginRequest request) {
        Authentication unauthenticated =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        request.username(), request.password());

        Authentication verified =
                manager.authenticate(unauthenticated);

        return "Authentication verified for " + verified.getName();
    }

    public record LoginRequest(String username, String password) {}
}
~~~

This is a **Spring MVC fragment**, needing imports and a SecurityFilterChain allowing `POST /auth/verify`; it does not run standalone. **It only demonstrates the credential-check step**, not a complete secure login API. Specifically:

1. Do not return `verified.getName()` in a public API if privacy policy forbids it.
2. Do not log request bodies/passwords.
3. For **session-based login**, after authentication you must build a new context, call `SecurityContextHolder.setContext(...)` and `SecurityContextRepository.saveContext(context, request, response)` before the response commits, and apply an appropriate session fixation strategy.
4. For **token-based login**, after authentication you must issue tokens via a properly designed token service that signs/verifies securely; subsequent requests send the Bearer token. Do not create sessions if the API is defined as stateless.
5. Cookie/session-based flows require CSRF, anti-brute-force/rate limiting, failure handlers that avoid user enumeration, and proper transaction/session lifecycle handling.
6. Those requirements are why standard auth filters are preferred whenever Spring Security already supports the equivalent feature.

**Calling `AuthenticationManager.authenticate(...)` does not automatically log in subsequent HTTP requests**. The manager verifies; the filter/controller owns setting the context and persisting state.

## 8. Distinguishing Input Authentication Tokens from Results

With username/password, typical values are:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);

Authentication result = authenticationManager.authenticate(request);

if (!result.isAuthenticated()) {
    throw new IllegalStateException("Provider did not authenticate");
}
~~~

This is a Java fragment inside a Spring app. `username`/`rawPassword` come from an untrusted request; never do this:

~~~java
// Extremely dangerous: assigning authorities before checking credentials!
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

The `authenticated(...)` factory or three-argument constructor must only be used once **a trusted provider/trust boundary has verified the identity**. Never return a token marked authenticated simply because the client sent `role=ADMIN`.

On success, `DaoAuthenticationProvider` usually returns a `UsernamePasswordAuthenticationToken` with `principal` as `UserDetails` and authorities from a trusted identity store. In Spring Security 7, some authentication mechanisms add a factor authority such as `FACTOR_PASSWORD` for multi-factor models; therefore tests asserting an **exact list of authorities** can become brittle on upgrade. Test the required roles per policy rather than assuming the authority list never gains extra elements.

**Do not retain raw passwords longer than necessary.** By default, `ProviderManager` attempts to erase credentials from a successful Authentication via `CredentialsContainer`. If a cache shares the same UserDetails object, erasure can affect the cache; the proper solution is usually copying/not caching password objects, not arbitrarily disabling `eraseCredentialsAfterAuthentication` globally.

## 9. What Does AuthenticationProvider.supports(...) Exactly Mean?

Core interface:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

This is an abbreviated signature for learning; do not redeclare a duplicate interface alongside Spring.

- `supports(TokenType.class) == true`: the provider **is capable of** handling that Authentication type; it does not mean authentication is guaranteed to succeed.
- `authenticate(...)` returns an authenticated `Authentication` if verification succeeds.
- Returning `null` means the provider abstains for this request; `ProviderManager` may try another provider.
- Throwing `AuthenticationException` means authentication failed; how the manager handles it and whether it tries other providers depends on the exception type/configuration.
- `supports(...)` returning false for all providers (with no parent handling it) usually leads to `ProviderNotFoundException`.

**Never write a provider that returns an authenticated token for every token type**, or a provider with a broad `supports(Authentication.class)` that ignores the credential type. That easily lets requests of another type pass through the wrong verification path.

### Providers for Multiple Credential Types

Suppose an application has:

- `DaoAuthenticationProvider` for username/password;
- A `ServiceKeyAuthenticationProvider` for issued/managed service API keys;
- OAuth2 resource server for Bearer JWTs, usually configured with `oauth2ResourceServer()` rather than rewriting JWT validation.

If you try to bundle all three into one `ProviderManager`, you must clearly define the token types and which flows/filters create each token. In many cases you should **separate `SecurityFilterChain` beans** by route and protocol, especially between browser session login and stateless APIs.

## 10. Building a Custom AuthenticationProvider Safely

Learning scenario: a backend receives a service-to-service credential rather than username/password. A custom provider should support its **own token type** instead of reusing `UsernamePasswordAuthenticationToken` and guessing what the password field means.

Illustrative fragment in a Spring Security project (not standalone runnable because it requires `ServiceCredentialVerifier` and the token implementation):

~~~java
public final class ServiceKeyAuthenticationProvider
        implements AuthenticationProvider {

    private final ServiceCredentialVerifier verifier;

    public ServiceKeyAuthenticationProvider(
            ServiceCredentialVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        if (!(authentication instanceof ServiceKeyAuthenticationToken keyToken)) {
            return null;
        }

        String presentedKey = (String) keyToken.getCredentials();
        ServiceIdentity identity = verifier.verify(presentedKey);

        if (identity == null) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Only AFTER successful verification should an authenticated token be built.
        return ServiceKeyAuthenticationToken.authenticated(
                identity.id(), identity.authorities());
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return ServiceKeyAuthenticationToken.class.isAssignableFrom(tokenType);
    }
}
~~~

`ServiceCredentialVerifier`, `ServiceIdentity`, and `ServiceKeyAuthenticationToken` are **application-defined types**; this is explicit framework pseudocode and does not pretend Spring provides `ServiceKeyAuthenticationToken.authenticated(...)` out of the box. In a real implementation:

1. Subclass `AbstractAuthenticationToken` with clear unauthenticated and authenticated states.
2. Ensure only the filter on service-key endpoints creates unauthenticated tokens from the designated header.
3. Prefer storing a **verifier** of the key in a trusted store; validate cryptographically with proper constant-time comparison, key rotation, and revocation.
4. `AuthenticationProvider` must never accept authorities sent by the client.
5. Never log raw keys, and never expose to clients any difference between a nonexistent key and a wrong key.
6. Implement `eraseCredentials()`/`CredentialsContainer` when needed to clear secrets.
7. Ensure `supports(...)` matches the exact token class and does not bypass account/service status policies.
8. For standard Bearer JWTs, prefer `oauth2ResourceServer().jwt(...)` and a `JwtDecoder` checking issuer/audience rather than a custom provider parsing tokens without signature verification.

## 11. Composing Multiple Providers Explicitly

One way to organize them:

~~~java
@Bean
AuthenticationManager authenticationManager(
        DaoAuthenticationProvider passwordProvider,
        ServiceKeyAuthenticationProvider serviceKeyProvider,
        AuthenticationEventPublisher publisher) {

    ProviderManager manager = new ProviderManager(
            List.of(serviceKeyProvider, passwordProvider));
    manager.setAuthenticationEventPublisher(publisher);
    return manager;
}
~~~

This fragment requires importing `java.util.List`, real provider beans, and a Spring context. Order can be chosen per policy; each provider must support the right token type. Adding a new provider to the manager without a filter/controller creating `ServiceKeyAuthenticationToken` will not make endpoints authenticate keys automatically.

**Do not register two providers for the same password token just to “fall back if provider A says invalid”** if doing so allows downgrade. For example, if a primary directory rejects a disabled account, you must not arbitrarily try a local fallback to log that disabled account in. There are `AuthenticationException` subtypes such as `AccountStatusException` that the manager handles under special rules; test real cases rather than assuming “any error tries B”.

If multiple providers serve different organizations/tenants, route to the right provider based on a **verified** tenant context and never trust a domain/tenantId from the request to self-authorize.

## 12. Global Manager vs. Local Manager of a SecurityFilterChain

Two scopes should be kept separate:

**Global AuthenticationManager bean**

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationProvider provider) {
    return new ProviderManager(provider);
}
~~~

Useful for components needing direct injection and sharing a common contract. However, an application with multiple chains may need different selections.

**Local AuthenticationManager for a single chain**

~~~java
@Bean
SecurityFilterChain adminChain(
        HttpSecurity http,
        AuthenticationManager adminManager) throws Exception {

    return http
            .securityMatcher("/admin/**")
            .authenticationManager(adminManager)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().hasRole("ADMIN"))
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This snippet assumes `adminManager` was defined with a provider supporting username/password for Basic. Do not pass a service-key manager to Basic and then be surprised by `ProviderNotFoundException`.

**Important:** a `@Bean AuthenticationManager` does not guarantee every chain picks up that bean identically when you have local overrides and auto-configuration. To know for sure which provider filter chain A uses, verify via integration tests and runtime wiring. When multiple beans share a type, use `@Qualifier` or explicit names to avoid injecting the wrong one.

## 13. Multiple SecurityFilterChains: Clear Path Boundaries

An application might use session form login for web and JWT for APIs:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

This is Spring Security Servlet configuration requiring `JwtDecoder`/JWK setup and the OAuth2 resource server dependency for the API. `@Order` comes from Spring Core; `securityMatcher("/api/**")` scopes the API chain, while the browser chain acts as the fallback. Each request matches **one SecurityFilterChain selected in order**, rather than running all chains sequentially.

Distinguish:

- `securityMatcher(...)` decides whether **the entire chain** applies to the request.
- `requestMatchers(...)` inside `authorizeHttpRequests` decides **authorization rules inside the selected chain**.
- `http.authenticationManager(manager)` sets the manager **for the chain being built**.
- `anyRequest().authenticated()` does not verify passwords; authentication filters perform verification.

With the pattern above, logging in via form to create an HTTP session for the browser **does not make `/api/**` allow requests without Bearer**. That is the intended behavior of a stateless API architecture, not Spring Security “losing the user”.

**CSRF/CORS** must be evaluated per client type. Session-based browser flows normally require CSRF; stateless JWT APIs may use a different policy, but you must never disable CSRF broadly just to make one test pass.

## 14. Why Is AuthenticationConfiguration.getAuthenticationManager() Sometimes Used?

Many Spring Security 6.x guides write:

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration config) throws Exception {
    return config.getAuthenticationManager();
}
~~~

The idea is to **expose the global manager built by Spring Security** for injection into custom components. This can fit when the global manager is already configured via user store/provider/builder and you want a reference to that exact instance.

However, this is **not a silver bullet for every project**:

- If you already defined another `@Bean AuthenticationManager`, it can cause bean ambiguity or circular dependencies depending on config.
- If multiple `SecurityFilterChain` beans use local managers, this global manager does not represent all chains.
- If providers or bean wiring are missing, retrieving the manager does not magically create the implementation you want.
- Across versions, global manager setup and auto-configuration can change.

**Recommendation:** if the project only uses built-in form login with one user store, do not expose the manager unnecessarily. If a REST/controller needs a manager, use explicit `ProviderManager(DaoAuthenticationProvider)` configuration as in 7.x docs, or expose the actual Spring-built manager **after verifying the dependency graph**. Avoid mixing both patterns in the same application without clear reason.

## 15. Should AuthenticationManagerBuilder Still Be Used?

`AuthenticationManagerBuilder` still appears in some docs/configs for fine-tuning the global manager, yet the modern architectural direction is **bean composition** whenever possible.

Legacy configuration signs to review:

~~~java
// Illustration of a prior-generation API:
protected void configure(AuthenticationManagerBuilder auth) throws Exception {
    auth.inMemoryAuthentication()
        .withUser("user")
        .password("{noop}password")
        .roles("USER");
}
~~~

This ties to the old `WebSecurityConfigurerAdapter` and is not the pattern for Spring Security 6/7. Replace it with an `InMemoryUserDetailsManager` or `JdbcUserDetailsManager` bean and an appropriate encoder.

When you have a custom provider, do not pull the entire app back to builder DSL just to register it. Instead declare a provider bean and an explicit `ProviderManager`, or register it through the version-supported DSL when the policy is clear. Use maps/chains and bean scopes for easier testing.

## 16. Credential Erasure, Caching, and Password Hashing

By default, `ProviderManager` can erase credentials from a successful Authentication to reduce how long secrets stay in memory. This involves `CredentialsContainer`.

Example pitfall:

~~~text
UserDetailsService returns the exact cached UserDetails object
     |
     v
ProviderManager returns Authentication referencing the same object
     |
     v
eraseCredentials() wipes the password hash on the cached object
     |
     v
Next login gets cached user with password erased
     |
     v
Password verification fails
~~~

Preferred solutions:

- Do not cache mutable objects containing passwords that are unintentionally shared.
- Create an appropriate copy when putting UserDetails into Authentication.
- Use caching strategies/frameworks that preserve proper semantics.
- Test multiple consecutive logins, as well as logins after password updates and cache eviction.
- Do not disable `eraseCredentialsAfterAuthentication` globally unless the risk has been carefully evaluated.

**Use PasswordEncoder in its proper role**:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode("password-used-only-for-test");

boolean matches = encoder.matches(
        "password-used-only-for-test", storedHash);
~~~

`DelegatingPasswordEncoder` lets hash formats carry an algorithm prefix, supporting policy evolution. In production, new passwords must be hashed per policy; never store plaintext or use `{noop}` for real users. When changing algorithms/costs, plan rehashing on login/password change rather than expecting “identical encrypted password every time” (salting changes output).

## 17. Authentication Events When Manually Constructing ProviderManager

An operational bug: the application has `@EventListener(AuthenticationFailureBadCredentialsEvent.class)` yet receives no events even when authentication fails. If you construct manually:

~~~java
ProviderManager manager = new ProviderManager(daoProvider);
~~~

per Javadoc, the default event publisher of a self-built manager can be **no-op**. If you need events, register one:

~~~java
DefaultAuthenticationEventPublisher publisher =
        new DefaultAuthenticationEventPublisher(applicationEventPublisher);

manager.setAuthenticationEventPublisher(publisher);
~~~

This snippet needs Spring’s `ApplicationEventPublisher` from the context. Never log raw passwords/Authentication objects/exception details when handling events; use event type, reason code, opaque request ID, and PII policy.

**A parent manager can cause duplicate events.** When a child manager publishes an event for a result/exception from its parent and the parent also publishes, one attempt can emit multiple events. Define a single clear publishing responsibility and test actual event counts.

Custom `AuthenticationException` subclasses do not automatically inherit superclass mappings in `DefaultAuthenticationEventPublisher` because matching uses the concrete class. When accurate failure metrics are needed, add explicit mappings or an appropriate fallback event.

## 18. Standalone Java 17: Simulating Provider Selection by Token Type

This program does not use Spring, does not implement credential hashing, and **must not be used for real authentication**. It only models the idea: a manager receives a typed request, finds a provider whose `supports` matches, and only that provider verifies. Spring’s `ProviderManager` has more complex null/exception/parent handling.

Create **ProviderSelectionDemo.java**:

~~~java
import java.util.List;

public class ProviderSelectionDemo {

    sealed interface LoginRequest
            permits PasswordLogin, ServiceKeyLogin, UnknownLogin {}

    record PasswordLogin(String user, String password)
            implements LoginRequest {}

    record ServiceKeyLogin(String key) implements LoginRequest {}

    record UnknownLogin() implements LoginRequest {}

    interface Provider {
        boolean supports(LoginRequest request);
        String authenticate(LoginRequest request);
    }

    static class PasswordProvider implements Provider {
        public boolean supports(LoginRequest request) {
            return request instanceof PasswordLogin;
        }

        public String authenticate(LoginRequest request) {
            PasswordLogin login = (PasswordLogin) request;
            return "alice".equals(login.user())
                    && "training-only".equals(login.password())
                    ? "USER:alice" : "DENIED";
        }
    }

    static class ServiceKeyProvider implements Provider {
        public boolean supports(LoginRequest request) {
            return request instanceof ServiceKeyLogin;
        }

        public String authenticate(LoginRequest request) {
            ServiceKeyLogin login = (ServiceKeyLogin) request;
            return "demo-key".equals(login.key())
                    ? "SERVICE:worker-a" : "DENIED";
        }
    }

    static String authenticate(List<Provider> providers, LoginRequest request) {
        for (Provider provider : providers) {
            if (provider.supports(request)) {
                return provider.authenticate(request);
            }
        }
        return "NO_PROVIDER";
    }

    public static void main(String[] args) {
        List<Provider> providers =
                List.of(new ServiceKeyProvider(), new PasswordProvider());

        System.out.println("Password login = "
                + authenticate(providers,
                        new PasswordLogin("alice", "training-only")));

        System.out.println("Service key = "
                + authenticate(providers, new ServiceKeyLogin("demo-key")));

        System.out.println("Invalid password = "
                + authenticate(providers, new PasswordLogin("alice", "bad")));

        System.out.println("Unsupported token = "
                + authenticate(providers, new UnknownLogin()));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ProviderSelectionDemo.java
java ProviderSelectionDemo
~~~

Exact stdout:

~~~text
Password login = USER:alice
Service key = SERVICE:worker-a
Invalid password = DENIED
Unsupported token = NO_PROVIDER
~~~

**Scope note:** the program compares secrets via fixed strings solely for reproducible output; **it does not protect real passwords/API keys**, and has no hashing, constant-time comparison, credential erasure, account policies, events, or SecurityContext. In real Spring Security, use `DaoAuthenticationProvider`/`PasswordEncoder` and a verifier that manages service keys securely. The lesson from the lab is **never let a password provider process a service token or vice versa**.

## 19. Unit Testing the AuthenticationManager Bean Directly

Instead of only testing controllers with `@WithMockUser`, call the **manager bean** with test credentials to prove provider wiring actually works.

JUnit 5 + Spring Boot Test example, using `ExplicitAuthenticationConfig` from section 6 and user `demo`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AuthenticationManagerBeanTest {

    @Autowired
    AuthenticationManager manager;

    @Test
    void acceptsCorrectPassword() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "demo", "training-password-only");

        Authentication result = manager.authenticate(request);

        assertTrue(result.isAuthenticated());
        assertEquals("demo", result.getName());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
    }

    @Test
    void rejectsWrongPassword() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "demo", "wrong-password");

        assertThrows(BadCredentialsException.class,
                () -> manager.authenticate(request));
    }
}
~~~

This test needs a Spring Boot project with the example beans and JUnit 5. It verifies **manager + DAO provider + password encoder** are actually wired together; it does not on its own test Servlet cookies, CSRF, or session persistence.

If using authentication factors in Spring Security 7, avoid asserting authorities solely with a fixed exact list; verify `ROLE_USER` alongside the version-specific security requirements.

### MockMvc for the Filter Chain

Add tests:

~~~java
mvc.perform(formLogin("/login")
        .user("demo")
        .password("training-password-only"))
    .andExpect(authenticated().withUsername("demo"));

mvc.perform(formLogin("/login")
        .user("demo")
        .password("wrong-password"))
    .andExpect(unauthenticated());
~~~

This is a **Spring Security Test fragment**, needing MockMvc configured with `springSecurity()` and static imports `formLogin`, `authenticated`, and `unauthenticated`. With standard form login config, check HTTP behavior and follow the session on request B with `MockHttpSession`; **do not use `with(user(...))` to pretend the password provider ran**.

If the API uses custom JSON login, use MockMvc POST JSON + CSRF where needed, and verify responses and context/token storage per contract. Do not test one chain and assume all remaining chains received the right manager.

## 20. Testing Local Managers and Multiple Authentication Types

The test matrix should include:

| Test | Expectation |
| --- | --- |
| SecurityFilterChain bean exists | FilterChainProxy selects the chain for the route |
| One UserDetailsService + valid encoder | Password provider verifies properly |
| Wrong password | AuthenticationException, no authenticated token |
| Account disabled/locked | Rejected per policy, no unauthorized fallback |
| Custom token type | Only supporting provider handles it |
| No provider for token | ProviderNotFoundException in Spring manager |
| Two providers support same class | Ordering and exception/fallthrough match design |
| Parent AuthenticationManager | Used only when appropriate, no policy bypass |
| Manual ProviderManager | Event publisher attached if needed |
| SecurityFilterChain local manager | HTTP request selects the right manager |
| REST controller injects manager | Same intended instance/configuration |
| Username/password auto-config | No duplicate provider/bean ambiguity |
| Multiple `UserDetailsService` beans | Does not rely on ambiguous auto-selection |
| Password hash wrong id/algorithm | Rejected; configuration error diagnosed |
| Credential erasure + user cache | Multiple consecutive logins still succeed |
| Form login → subsequent request | Session/context persisted and restored |
| Stateless API missing Bearer | Expected 401, does not accept cookie auth |
| Session/API chain matchers | Does not pick the wrong filter chain |
| Custom failure event | Mapped properly, no credential leaks |
| Upgrade 6.5 → 7.x | No-arg DaoAuthenticationProvider gone; new constructor works |

Do not write only a `@WithMockUser` test and conclude the manager is configured properly: mock users can create Authentication directly without passing through the password provider.

## 21. Common Mistakes When Upgrading Versions

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter cannot be resolved` | Removed in Spring Security 6 | Migrate to `@Bean SecurityFilterChain` |
| `antMatchers(...) cannot be resolved` | Old matcher API removed | Use `requestMatchers(...)` / `securityMatcher(...)` appropriately |
| `javax.servlet... cannot be resolved` | Spring Boot 3+/Jakarta migration | Use `jakarta.servlet.*` |
| `DaoAuthenticationProvider()` constructor missing | Spring Security 7 removed no-arg constructor | Use `new DaoAuthenticationProvider(userDetailsService)` |
| `setUserDetailsService(...)` missing | Legacy setter deprecated/removed | Inject UserDetailsService via constructor |
| Controller cannot inject AuthenticationManager | Bean not exposed or bean ambiguity | Explicit `@Bean`, proper `@Qualifier` |
| Provider bean declared but filter does not use it | Incorrect manager/chain wiring | Check `http.authenticationManager(...)` |
| `ProviderNotFoundException` | No provider supports token type | Check `supports` and chain |
| Login succeeds yet next request is anonymous | Manager only verified, context/session not saved | Check SecurityContextRepository and cookies |
| Correct password throws BadCredentialsException | Encoder/hash id, user store, account policy | Check matches/encoded hash, never log raw password |
| Both chains match /api | Incorrect order/matcher | Put specific chain before fallback |
| AuthenticationFailureEvent does not reach listener | Manual ProviderManager default publisher is no-op | Attach AuthenticationEventPublisher |
| Duplicate events | Parent/child managers both publish same attempt | Designate single publisher, test count |
| Credential cache loses hash after login | ProviderManager erases credentials | Avoid shared mutable cached UserDetails |
| Bean circular dependency | Cross-calling `@Bean` methods / config depends on manager too early | Constructor/method injection, separate wiring |
| REST Login bean works but HTTP Basic fails | REST manager differs from chain manager | Wire explicitly, test both |
| Stateless endpoint rejects session user | API intentionally requires Bearer per request | Send token, do not switch to stateful carelessly |
| 403 error after auth | Authorization or CSRF, not provider | Check authorities/CSRF separately |

**Never fix by disabling CSRF, enabling `anyRequest().permitAll()`, forging authenticated tokens, or switching the whole app to STATELESS/ALWAYS without diagnosis.** Those workarounds hide root causes and break security boundaries.

## 22. When Should You Avoid Creating a ProviderManager Yourself?

Even though `new ProviderManager(...)` looks simple, it increases responsibility:

- You must pass the right list of providers, token types, and ordering/parent policy;
- You must attach an event publisher if you need authentication events;
- You must consider credential erasure/caching;
- You must wire it into **the right SecurityFilterChain**;
- You must integrate session strategy and context persistence in custom login;
- You must handle password failures, account status, and multi-factor requirements;
- You must avoid creating a bean colliding with the framework’s default manager.

If you only use standard username/password, `UserDetailsService` + `PasswordEncoder` + `SecurityFilterChain` is easier to maintain. If using LDAP, SAML, OAuth2/OIDC, JWT, or passkeys, prefer Spring Security’s dedicated mechanisms before writing a new custom provider.

**You need a custom provider when you have a genuinely custom protocol/credential type**, not to change an HTTP error page or controller route. Changing login UI belongs in the appropriate handler/filter/entry point; changing how users are fetched may only require a custom UserDetailsService.

## 23. Key Decisions for Spring Boot Production

1. **Authentication method:** password, LDAP/AD, SAML, OIDC, JWT, API key, or multiple mechanisms?
2. **State model:** browser session or stateless Bearer? Can one request reach multiple chains?
3. **Credential storage:** where are password hashes stored; PasswordEncoder policy/rehash and credential rotation?
4. **Manager composition:** auto manager or explicit `@Bean`; who owns wiring?
5. **Provider boundaries:** which token classes are supported, and which errors must block fallback?
6. **Events and audit:** is auditing required; who publishes; how are duplicates/PII leaks prevented?
7. **Context persistence:** standard login flow or custom; saved before response commit?
8. **Method/HTTP authorization:** authenticated users still need resource/tenant permission checks.
9. **Testing:** test beans, provider dispatch, filter chains, sessions, stateless APIs, CSRF/CORS, and upgrade regressions.
10. **Dependencies:** use Spring Boot BOM, compatible Java/Jakarta versions, and check API deprecations before upgrading.

### Self-Review Configuration Checklist

- Do I need to define an AuthenticationManager bean, or does Spring Security already handle it?
- If defined, is that manager **the actual instance the filter chain uses**?
- Which provider supports `UsernamePasswordAuthenticationToken`? Which custom tokens have separate providers?
- Does DaoAuthenticationProvider use the **constructor accepting UserDetailsService** and a valid PasswordEncoder?
- Does UserDetailsService only load users without “authenticating” bad passwords itself?
- Have I avoided `WebSecurityConfigurerAdapter` and `antMatchers` in Spring Security 6/7?
- Am I protecting passwords/credentials and avoiding keeping raw secrets in Authentication or logs?
- If testing a custom manager needing an event publisher, are there no duplicate events with a parent?
- Have I tested HTTP session persistence **separately** from credential verification?
- Does the `SecurityFilterChain` configuration have accurate matchers/order without mixing browser and API?
- On upgrade, have I checked the actual Java APIs of the resolved dependencies?

**Conclusion:** Modern Spring Security configuration should start from **beans with clear responsibilities**: `SecurityFilterChain` for HTTP, `UserDetailsService` + `PasswordEncoder` for passwords, `AuthenticationProvider` for verifying one credential type, and `AuthenticationManager/ProviderManager` when composition or injection is truly needed. Do not confuse the manager with a session; do not assume every provider bean enters every filter chain; do not reuse APIs removed after `WebSecurityConfigurerAdapter`. An explicit configuration may be a few lines longer, yet is far easier to test, upgrade, and keep securely bounded.

### Official References

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Username/Password Authentication (Publish an AuthenticationManager Bean): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — DaoAuthenticationProvider API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security — ProviderManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security — Servlet Configuration and Multiple Chains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Password Storage and DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — SecurityContext Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — MockMvc Authentication Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security Engineering — Without WebSecurityConfigurerAdapter: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter/
- Spring Security 6.5 DaoAuthenticationProvider API (deprecated constructors): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
