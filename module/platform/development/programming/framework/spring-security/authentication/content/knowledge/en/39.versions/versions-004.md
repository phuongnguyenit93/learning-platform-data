# Reading Legacy Configurations Using WebSecurityConfigurerAdapter or Deprecated APIs in Spring Security

## 1. Why Is Reading Legacy Configurations an Essential Skill?

Many Java projects still contain classes like `SecurityConfig extends WebSecurityConfigurerAdapter`, calling `configure(HttpSecurity)`, `configure(WebSecurity)`, and `configure(AuthenticationManagerBuilder)`. Beginners see snippets such as:

```java
http.authorizeRequests()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
    .and()
    .formLogin();
```

In Spring Security 6.x, several of these classes and methods were removed or deprecated. Copying them verbatim into Spring Boot 3.x may fail to compile. Worse yet, replacing them with new APIs without understanding the **original rules** can accidentally expose public endpoints, disable CSRF, break login, misconfigure sessions, or drop method authorization.

The goal of this lesson is **reading, interpreting, inventorying, and converting configurations**, not merely memorizing new syntax. You must be able to answer:

1. Which requests does the legacy configuration **protect**, and which requests are bypassed completely?
2. Through which **provider** are users authenticated: form login, HTTP Basic, JDBC, LDAP, OAuth2, a custom filter, or Bearer JWT?
3. What do the `role`, `authority`, method security, and matcher ordering rules mean?
4. Which endpoints did Spring Security create, such as `POST /login` or `POST /logout`?
5. When migrating to `SecurityFilterChain`, does **behavior** stay intact, especially in places that were already unsafe?
6. Are you upgrading from Spring Security 5.6, 5.8, 6.5, or 7.0? Valid APIs also depend on **version and Servlet vs. WebFlux**.

Target code examples focus on **Spring Boot 3.x + Spring Security 6.5 + Java 17+ + Servlet/MVC**. The closing sections explain what you need to know when moving to Spring Security 7.x/Boot 4.x. Legacy code illustrates a configuration to read, **not a pattern recommended for new deployments**.

## 2. Mapping Versions Before Editing Code

| Version/Branch | Identifying Characteristics | Reading and Migration Direction |
| --- | --- | --- |
| Spring Security 5.6 and earlier | `WebSecurityConfigurerAdapter` widely used; `authorizeRequests`, `antMatchers`, `.and()` common | Understand all three overrides and rule order before swapping APIs |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` **deprecated**; `SecurityFilterChain` and `WebSecurityCustomizer` beans recommended | Can migrate class by class before changing Java/Jakarta |
| Spring Security 5.8 | Bridge release preparing for 6.0; many modern APIs already present | Clean up deprecated APIs, matchers, method security, and session assumptions |
| Spring Security 6.0+ | `WebSecurityConfigurerAdapter` and old `antMatchers`/`mvcMatchers` DSL **removed**; Servlet types moved to `jakarta.*` | Use `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `@EnableMethodSecurity` |
| Spring Security 6.5 | Prepares migration to 7.x; certain legacy matchers and DSLs deprecated for removal | Use Lambda DSL, review `PathPatternRequestMatcher`, audit matchers and filter-chain boundaries |
| Spring Security 7.x | Lambda DSL mandatory; `AntPathRequestMatcher`/`MvcRequestMatcher` removed from modern configuration paths | Prepare new pattern semantics and test thoroughly on compatible Boot/Jakarta versions |

**Two milestones you must not confuse:** `WebSecurityConfigurerAdapter` was **deprecated in 5.7**, and **removed in 6.0**. In 5.7/5.8, old code may still compile with warnings; in 6.0, it must be replaced. Do not conclude “just bumping the version makes Spring migrate the class automatically”.

**Spring Boot 2.7 → Boot 3.0** is also an ecosystem upgrade: Boot 3 uses Java 17+, Spring Framework 6, and Jakarta EE packages (e.g., `jakarta.servlet` instead of `javax.servlet`). This is **not just** a security DSL syntax change.

A controlled upgrade path is typically: Boot 2.7 + Security 5.8 to prepare → Boot 3.x + Security 6.x → resolve 6.5 deprecation warnings to prepare for Boot 4/Security 7. Cross-check proper BOM/dependency alignment rather than forcing an arbitrary Spring Security major onto an incompatible Boot major.

## 3. Three Legacy configure Methods: Each Has Its Own Responsibility

`WebSecurityConfigurerAdapter` was an inheritance-based base class for configuring multiple aspects of Spring Security:

| Legacy | Responsibility | Replace With |
| --- | --- | --- |
| `configure(HttpSecurity http)` | Defines filter chain, request authorization, login, logout, CSRF, session, exception handling | One or more `@Bean SecurityFilterChain` methods |
| `configure(WebSecurity web)` | Customizes `WebSecurity` level, especially `web.ignoring()` bypassing security filters | `@Bean WebSecurityCustomizer` **only if bypassing is truly needed**, or prefer `permitAll` in the filter chain |
| `configure(AuthenticationManagerBuilder auth)` | Registers users, providers, JDBC/LDAP, password encoder, manager construction | `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider`, `AuthenticationManager` beans as appropriate |

How to read a legacy class:

```text
@Configuration / @EnableWebSecurity
      |
      v
extends WebSecurityConfigurerAdapter
      |
      +-- configure(WebSecurity)
      |     -> WHICH REQUESTS NEVER ENTER Spring Security?
      |
      +-- configure(HttpSecurity)
      |     -> WHICH REQUESTS ENTER THE FILTER CHAIN?
      |     -> which rules allow / deny?
      |     -> which provider/login/logout/session/CSRF are enabled?
      |
      +-- configure(AuthenticationManagerBuilder)
            -> how are credentials verified?
            -> which UserDetailsService, which encoder?
            -> are there custom providers or LDAP/JDBC?
```

**Do not read only `configure(HttpSecurity)`.** An endpoint that appears to require authentication in `authorizeRequests` may still skip security filters entirely if `configure(WebSecurity).ignoring()` excluded it earlier.

### Other Places That Also Define Access Rules

- `@EnableGlobalMethodSecurity` + `@PreAuthorize`/`@Secured`: method/service-level permissions.
- `@Order` or multiple `WebSecurityConfigurerAdapter` classes: ordering of security chains.
- Dedicated `@Bean` components such as custom filters, `AuthenticationProvider`, `AuthenticationEntryPoint`.
- Spring Boot properties for sessions, cookies, reverse proxies, and OAuth2 clients/providers.
- Controller routes, servlet paths, and reverse-proxy path rewrites affecting request matchers.

A migration that updates only one class while ignoring method security, static resources, or custom providers is usually incomplete.

## 4. Legacy Spring Security 5.x Example: Reading Rule by Rule

This is a **legacy code sample** written in Spring Security 5.x style. **Do not compile it under Security 6.5** because the class and DSL have been removed.

```java
// Example for READING in legacy Security 5.x projects.
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.authentication.builders
        .AuthenticationManagerBuilder;
import org.springframework.security.config.annotation.method.configuration
        .EnableGlobalMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.builders.WebSecurity;
import org.springframework.security.config.annotation.web.configuration
        .EnableWebSecurity;
import org.springframework.security.config.annotation.web.configuration
        .WebSecurityConfigurerAdapter;

@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/assets/**").permitAll()
                .antMatchers("/login").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .formLogin()
                .permitAll()
                .and()
            .httpBasic();
    }

    @Override
    public void configure(WebSecurity web) throws Exception {
        web.ignoring().antMatchers("/assets/**");
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth)
            throws Exception {
        // Password {noop} is ONLY for illustrating a test environment.
        auth.inMemoryAuthentication()
            .withUser("alice")
            .password("{noop}test-only-password")
            .roles("USER")
            .and()
            .withUser("root")
            .password("{noop}test-only-admin")
            .roles("ADMIN");
    }
}
```

Interpretation:

1. `/assets/**` **is ignored in WebSecurity**, so these requests **bypass FilterChainProxy**; the `antMatchers("/assets/**").permitAll()` rule inside `HttpSecurity` becomes redundant for requests already ignored.
2. `/login` is permitted and `formLogin()` provides the corresponding authentication flow. With default form login, Spring Security handles `POST /login` and serves the default login page or a custom configured page.
3. `/admin/**` requires the user to hold authority `ROLE_ADMIN`. `hasRole("ADMIN")` automatically adds the `ROLE_` prefix, so you do not write `hasRole("ROLE_ADMIN")`.
4. All other paths hit `anyRequest().authenticated()`: the caller merely needs to be authenticated, not necessarily hold a specific role.
5. `.and()` exits the child configurer back to `HttpSecurity` in the legacy DSL.
6. `httpBasic()` enables HTTP Basic alongside form login, which can cause entry point/401 vs. login redirect behavior to differ by request type.
7. `@EnableGlobalMethodSecurity(prePostEnabled=true)` enables `@PreAuthorize`/`@PostAuthorize` on methods.
8. `{noop}` stores raw passwords solely for demo purposes. **Never use it in production**; always use an adaptive one-way hash/`PasswordEncoder` aligned with policy.

**Not yet a production application:** it still needs HTTPS, session/cookie hardening, CSRF, password hashing, error handling, an account store, logout, and security matcher tests. The example is chosen to learn rule reading, not to suggest running the legacy version.

## 5. Rewriting for Spring Security 6.5 with a SecurityFilterChain Bean

Instead of subclassing `WebSecurityConfigurerAdapter`, modern applications expose configuration beans. Example class **in Spring Boot 3.x/Java 17+**, using Spring Security 6.5 Servlet:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.configuration
        .EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ModernSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/login").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password(encoder.encode("demo-only-password"))
                    .roles("USER")
                    .build(),
                User.withUsername("root")
                    .password(encoder.encode("demo-only-admin"))
                    .roles("ADMIN")
                    .build());
    }
}
```

When dropped into a Spring Boot 3.x project with `spring-boot-starter-web` and `spring-boot-starter-security`, this class creates the security chain and a test user store. The usernames/passwords here are **fixtures**, not production credentials. A real password encoder generates salted bcrypt hashes; each startup can yield different strings. Production should store hashes in a DB/IdP and manage credential secrets properly.

### Meaning Changes, Not Just Syntax Changes

| Legacy Configuration | Modern Configuration | What Is Preserved? |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain` | Replaces inheritance with composition |
| `configure(HttpSecurity)` | Bean method accepting `HttpSecurity` and calling `http.build()` | Security filters for matching requests |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Request policy, though authorization implementation can differ |
| `antMatchers("/admin/**")` | `requestMatchers("/admin/**")` | URL matching intent; **must test actual matcher semantics** |
| `.anyRequest().authenticated()` | `.anyRequest().authenticated()` inside lambda | Fallback rule within the **selected chain** |
| `.formLogin().and()` | `.formLogin(Customizer.withDefaults())` | Enables form login defaults |
| `.httpBasic()` | `.httpBasic(Customizer.withDefaults())` | Enables HTTP Basic defaults |
| `web.ignoring().antMatchers(...)` | Prefer `requestMatchers(...).permitAll()` or `WebSecurityCustomizer` | **Not strictly equivalent** when converting ignoring → permitAll |
| `configure(AuthenticationManagerBuilder)` | `UserDetailsService`/`PasswordEncoder`/provider beans | Explicit authentication configuration |
| `@EnableGlobalMethodSecurity(prePostEnabled=true)` | `@EnableMethodSecurity` | Enables pre/post method checks by default |

**Switching to `permitAll` for static assets is an intentional improvement, not 100% identical semantics to ignoring.** It keeps requests inside the security chain so Spring Security can still apply headers and other protections while authorization for the resource is public.

### Do Not Disable CSRF Just to Make New Code “Run Easily”

The modern example **does not** call `http.csrf(csrf -> csrf.disable())`. For form login/browsers with session cookies, CSRF protection should stay enabled and supply tokens on state-changing requests. If the application is strictly stateless Bearer tokens, evaluate separately after analyzing credential transport accurately; never assume JSON APIs are immune to CSRF.

## 6. Why Is the SecurityFilterChain Bean the New Architecture?

A `SecurityFilterChain` consists of a list of security filters and a `RequestMatcher` defining the scope of requests to which the chain applies. `FilterChainProxy` selects the **first matching chain** to handle a request.

```text
HttpServletRequest
      |
      v
DelegatingFilterProxy
      |
      v
FilterChainProxy
      |
      +-- SecurityFilterChain @Order(1): /api/**
      |           | match -> runs filters of the API chain
      |
      +-- SecurityFilterChain @Order(2): /admin/**
      |           | match -> runs filters of the admin chain
      |
      +-- SecurityFilterChain fallback: /** (all remaining requests)
                  | match -> runs fallback filters
```

Each request uses only **the first matching chain**; it does not fall through to the next chain on denial. Therefore, an `@Order(1)` chain with an overly broad policy can **completely shadow** an admin chain below it.

### securityMatcher Differs from requestMatchers

- `http.securityMatcher("/api/**")`: decides whether **this entire SecurityFilterChain applies** to the request.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin/**")...)`: once the request **is already inside the chain**, selects which authorization rule within that chain applies.
- `anyRequest()` applies only to **every request selected into the chain**; it does not protect URLs that failed to match any chain.

Lacking a fallback chain for `/portal/**` when other chains only match `/api/**` can leave `/portal/**` requests **unprotected by Spring Security** (external proxy/container protections are not automatically equivalent).

### Multiple SecurityFilterChains Example

```java
@Configuration
@EnableWebSecurity
class MultipleChainsSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
```

Imports are the same Spring Security group as above plus `org.springframework.core.annotation.Order`. This is an **alternative configuration** to `ModernSecurityConfig`; do not enable both examples simultaneously without controlling order. It requires a `UserDetailsService`/`AuthenticationProvider` source and real tests; the class does not run standalone via `javac`.

Note that the API chain above keeps CSRF defaults. When a browser automatically attaches HTTP Basic credentials, CSRF can still apply; do not disable it merely because the route starts with `/api`.

**A common trap:** if `securityMatcher("/secured/**")` is used alongside default form login `POST /login`, that endpoint may **not belong to the chain**; the login filter never runs, causing 404 or broken flows. Either place `loginProcessingUrl`/`loginPage` within scope, or configure a valid fallback chain. Spring Security docs explicitly warn about endpoints provided by security filters.

## 7. URL Matching Differs Across Major Versions

A naive conversion:

```text
Legacy:
  .antMatchers("/admin/**").hasRole("ADMIN")

New:
  .requestMatchers("/admin/**").hasRole("ADMIN")
```

looks equivalent, yet **you must not assume matcher implementations and path normalization behave identically**.

### Ant, MVC, and PathPattern

- `AntPathRequestMatcher` in older versions works with Ant-style rules on the request path, with specifics around `servletPath`/`pathInfo`.
- `MvcRequestMatcher` accounts for Spring MVC semantics and may require `HandlerMappingIntrospector` and matching `servletPath`.
- `PathPatternRequestMatcher` uses `PathPattern`, which is the default direction in Spring Security 7; paths are written as **application-absolute URLs excluding the context root**, with servlet `basePath` rules.
- In Spring Security 6.5, `AntPathRequestMatcher`/`MvcRequestMatcher` were deprecated for removal, with preparing `PathPatternRequestMatcher` recommended.

What needs testing goes beyond `/admin`:

| Request Path | Risk |
| --- | --- |
| `/admin/report` | Normal path |
| `/admin` | Does pattern `/admin/**` match the root? Check per matcher/version |
| `/adminx` | Must not accidentally match prefix `/admin` |
| `/ADMIN/report` | Case sensitivity and normalization |
| `/api;param=1/admin` | Semicolons/path parameters/firewall |
| `/api//admin` | Double-slash handling/firewall |
| `/app/admin/report` | `/app` is the context path, not necessarily in the matcher pattern |
| `/servlet/admin/report` | Non-default servletPath needs builder/basePath |
| Encoded slashes, dot segments | URL decoding/path traversal and `StrictHttpFirewall` |
| `/admin/report?x=1` | Query string is not the path and should not drive authorization matchers |

When moving to Security 7, read `6.5/migration-7/web.html` on `PathPatternRequestMatcher`, and test patterns using Ant-only syntax or special servlet mappings. Never disable `StrictHttpFirewall` just to “make an old matcher work”.

### Proactively Preparing for 7.x

Spring Security 6.5 provides `PathPatternRequestMatcher` and a configuration mechanism so the DSL uses PathPattern matchers before bumping majors:

```java
// Migration preparation bean on Security 6.5, per official documentation:
@Bean
PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
    return new PathPatternRequestMatcherBuilderFactoryBean();
}
```

`PathPatternRequestMatcherBuilderFactoryBean` belongs to `org.springframework.security.config.web`. This is a **config fragment**: it needs imports, a Spring context, and testing of real MVC mappings. If the project uses multiple servlets or non-default servlet base paths, do not enable it blindly before evaluating matchers.

**Do not hard-code `/app` into every matcher** just because the app sets `server.servlet.context-path=/app`: PathPattern matchers normally evaluate paths **excluding the context path**, though other servlet paths follow their own rules.

## 8. WebSecurityCustomizer and permitAll: Similar Access, Different Protection

Legacy snippet:

```java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/css/**", "/js/**");
}
```

A conversion can preserve ignoring semantics via a bean:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
            .requestMatchers("/css/**", "/js/**");
}
```

However, this is **not the default recommendation**. `web.ignoring()` excludes those requests from Spring Security’s `FilterChainProxy`. That also prevents relevant security filters from running on them, including Spring Security response headers and other protections the application expects.

The more commonly recommended approach:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/css/**", "/js/**").permitAll()
        .anyRequest().authenticated());
```

Key differences:

| Aspect | `web.ignoring()` | `permitAll()` |
| --- | --- | --- |
| Static resource read authorization | Allowed by skipping security chain | Allowed by authorization manager |
| Runs Spring Security filters | **No** | **Yes**, in the selected chain |
| Security response headers from Spring Security | Not applied by the chain | Can be applied |
| CSRF/other filters on public endpoints | Bypassed in Spring Security | Still traverses filters, unless a specific filter excludes it |
| Observability/metrics/filter behavior | Altered due to bypass | Consistent with the rest of the app |
| Suitable by default for dynamic endpoints | No | Possibly, depending on actual permissions |

**`permitAll()` only waives the authorization requirement; it does not disable CSRF, exempt authentication filters, or make a POST missing CSRF valid.** For instance, a permitted `POST /signup` may still require a CSRF token in a cookie-based app.

In particular, never convert `web.ignoring().antMatchers("/api/**")` to `permitAll` without understanding both: one disables all Spring Security, the other grants public access; both can be dangerous if `/api/**` holds private data.

## 9. Migrating AuthenticationManagerBuilder and Registering Providers

A legacy class often contains:

```java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth.userDetailsService(myUserDetailsService)
        .passwordEncoder(myPasswordEncoder);
}
```

In bean-based configuration, options depend on the use case:

1. **Standard username/password form login:** expose `UserDetailsService` and `PasswordEncoder` beans; verify Spring Boot/Spring Security actually picks the right provider/manager.
2. **Custom AuthenticationProvider:** register the provider on the right `HttpSecurity` or `AuthenticationManager`.
3. **Custom login controller/service needing a manager:** provide/inject a clearly wired `AuthenticationManager`, rather than grabbing an object disconnected from the login filter.
4. **Multi-chain:** each chain can have its own authentication manager; do not assume all chains share a single global manager.

Explicit provider/manager example for Spring Security 6.5:

```java
@Bean
AuthenticationManager explicitPasswordManager(
        UserDetailsService users, PasswordEncoder encoder) {

    DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
    dao.setPasswordEncoder(encoder);
    return new ProviderManager(dao);
}
```

Imports: `org.springframework.security.authentication.AuthenticationManager`, `org.springframework.security.authentication.ProviderManager`, `org.springframework.security.authentication.dao.DaoAuthenticationProvider`.

When a chain must use this exact manager:

```java
@Bean
SecurityFilterChain customLoginChain(
        HttpSecurity http,
        AuthenticationManager explicitPasswordManager) throws Exception {

    return http
            .authenticationManager(explicitPasswordManager)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

These two snippets form an **alternative configuration**; do not enable them alongside the full class in section 5 without managing beans of the same type and chain ordering. Verify the user service, password encoder, success/failure handling, and context persistence with integration tests. When creating `ProviderManager` manually, authentication events/publishers, erase-credentials, parent providers, and custom settings may not be copied automatically from the default manager.

**Never implement password checks with `raw.equals(storedHash)`**, or switch hashes from BCrypt to `{noop}` to “fix a 401 Login error”. Migrating encoders/hashes is a separate plan with legacy hash verification and verified auto-rehashing.

### Does Every Application Need an AuthenticationManager Bean?

**No.** An application needing only standard form login can run with `UserDetailsService`/`PasswordEncoder` and a security chain without publishing a separate global `AuthenticationManager` bean. Create an explicit manager when the architecture requires it, then test against circular dependencies and duplicate provider wiring.

## 10. @EnableGlobalMethodSecurity → @EnableMethodSecurity

Method authorization does not live only in HTTP rules. Legacy example:

```java
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacyMethodSecurity {}
```

Migrated to Spring Security 6.x:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

`@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter` **by default**, while `@Secured` and JSR-250 have dedicated flags.

### Default-Change Trap During Migration

If the old configuration only enabled `securedEnabled=true` **without** enabling pre/post annotations:

```java
@EnableGlobalMethodSecurity(securedEnabled = true)
```

converting directly to:

```java
@EnableMethodSecurity(securedEnabled = true)
```

can unintentionally **also enable** `@PreAuthorize`/`@PostAuthorize` because `prePostEnabled=true` is the new default. To stay faithful to the old behavior:

```java
@EnableMethodSecurity(
        securedEnabled = true,
        prePostEnabled = false)
```

Similarly, `jsr250Enabled=true` for `@RolesAllowed`/`@PermitAll` needs verification of the right javax/jakarta annotation imports and runtime behavior. Spring Security method security relies on Spring AOP, so **self-invocation** (a method calling another method on the same object directly) can bypass the proxy; never assume annotation tests cover every call path.

### Do Not Use HTTP Authorization as a Substitute for Domain Permissions

`.requestMatchers("/admin/**").hasRole("ADMIN")` protects a URL, yet a service method `approveOrder(id)` may be invoked from a scheduled job, message listener, or another API. When business logic must be protected, use proper method/service authorization and verify resource ownership/tenant boundaries. Migrating to `@EnableMethodSecurity` does not invent domain authorization that was never designed.

## 11. @EnableWebSecurity, Request Matchers, and Spring Boot Auto-Configuration

In Spring Boot, once the application provides a `SecurityFilterChain` bean, Boot typically backs off its auto-configured default security chain. That means:

- You **must** include an appropriate fallback rule (such as `anyRequest().authenticated()` or `denyAll()` depending on policy).
- Do not assume that adding an `/api/**` chain makes Boot protect the remaining URLs automatically.
- Do not create an overly broad `@Bean WebSecurityCustomizer` expecting the fallback chain to protect those paths.
- Inspect filters/beans added by OAuth2 resource server, OAuth2 client, management/Actuator, and service-specific security starters.
- When using multiple chains, define explicit `@Order` and matchers on every chain.

### Security Filter-Provided Endpoints

Certain endpoints are served by the filter chain itself: form login processing, logout, OAuth2 authorization redirects/callbacks. If `securityMatcher` excludes those paths, they can disappear even though you called `formLogin`/`oauth2Login` in the chain.

Example (illustrating a scope mistake):

```java
http.securityMatcher("/secure/**")
    .formLogin(Customizer.withDefaults());
```

The default `POST /login` **is not under** `/secure/**`. For this chain to serve it, configure `loginProcessingUrl`/`loginPage` inside the scope, or provide a properly configured fallback chain. When specifying a custom login page, the application must provide the corresponding GET route/template; Spring does not generate custom UI pages automatically.

### DispatcherType and ERROR/FORWARD

Spring Security 6 changed how dispatch types are authorized. An `ERROR` dispatch to `/error` can be blocked by an `authenticated` rule, causing developers to see 401/403 instead of the original error. Where appropriate, configure:

```java
http.authorizeHttpRequests(auth -> auth
        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Import `jakarta.servlet.DispatcherType`. This example must be applied according to your **actual error-page security policy**, not as advice to permit every dispatcher type unconditionally. `permitAll` does not disable remaining filters; protect error responses from leaking exceptions, stack traces, or secrets.

## 12. Other Deprecated APIs Worth Recognizing When Reading Legacy Code

| Sign in Source | Modern Status / Direction | What to Test |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter` | Removed 6.x → `SecurityFilterChain` bean | Beans/chains are actually registered |
| `authorizeRequests()` | Prefer `authorizeHttpRequests(...)` | Do authorization decisions differ? |
| `antMatchers(...)`/`mvcMatchers(...)` in DSL | Removed 6.0 → `requestMatchers(...)` | URL matching, servletPath, encoded paths |
| `antMatcher(...)` selecting a chain | `securityMatcher(...)` | Which chain matches, whether fallback remains |
| `httpBasic().and()` | `httpBasic(Customizer.withDefaults())` | 401 entry point, WWW-Authenticate |
| `formLogin().and()` | `formLogin(Customizer.withDefaults())` | Login endpoints, CSRF, sessions |
| `csrf().disable()` | Only with real justification: `csrf(csrf -> csrf.disable())` | **Never** turn “syntax translation” into blind CSRF disabling |
| `authorizeRequests().anyRequest()` | `authorizeHttpRequests(auth -> auth.anyRequest()...)` | Fallback access rules |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | prePost/secured/jsr250 flags |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` in Boot 3/Security 6 | Third-party dependencies, filter registration |
| Custom `AntPathRequestMatcher` | Prepare `PathPatternRequestMatcher` for 7 | Path semantics and servlet mappings |
| `.apply(new CustomDsl())` | `.with(customDsl, customizer)` in 6.2+/7 | Filter order and customization |
| `shouldFilterAllDispatcherTypes(false)` | `dispatcherTypeMatchers(...)` | ERROR/FORWARD dispatch per policy |
| `web.ignoring().antMatchers(...)` | `WebSecurityCustomizer` or recommended `permitAll` | Static headers, filter bypass |
| `AuthenticationManagerBuilder` in adapter | User/service/provider/manager beans | Provider wiring, password hashing, events |
| `SecurityContextPersistenceFilter` assumptions | Review `SecurityContextHolderFilter`/explicit save in 6 | Custom login persists SecurityContext |
| `authorizeHttpRequests().and()` | Lambda DSL mandatory in 7 | No non-lambda chaining |

### “Deprecated” vs. “Removed”

- **Deprecated:** code may still compile in the current version, yet the compiler warns and the framework recommends migrating.
- **Deprecated for removal:** likely to be deleted in the next major release; even more urgent to test before upgrading.
- **Removed:** compile error because the symbol is gone; must be replaced with an API providing matching semantics.

Do not fix all deprecations with blind search-and-replace. Filter order, security matchers, and authentication methods can alter behavior.

## 13. Spring Security 7.x: What Else Needs Preparation?

The migration documentation from 6.5 to 7.x highlights:

- **Lambda DSL is mandatory:** chaining like `http.authorizeHttpRequests().anyRequest()...and()`/`http.httpBasic()` is no longer valid; use `authorizeHttpRequests(auth -> ...)`, `httpBasic(Customizer.withDefaults())`, `csrf(csrf -> ...)`.
- `AntPathRequestMatcher` and `MvcRequestMatcher` are no longer supported as legacy DSL implementations; `PathPatternRequestMatcher` is the default.
- Path patterns must follow PathPattern rules, with **application-absolute URLs excluding the context root**; specifically verify non-default servlet paths.
- Custom DSL `apply()` calls must move to `with()`.
- Legacy settings for sessions, headers, dispatch types, or authorization managers may have updated defaults/behavior; read the guide for the **exact version being deployed**.
- Boot 4/Security 7 also introduces non-security changes (such as Jackson alignment), so test the whole application, not only `SecurityConfig`.

**Do not call `PathPatternRequestMatcher` just another name for `AntPathRequestMatcher`.** They define path semantics differently. Test odd URLs and gateway rewrites before upgrading production.

## 14. Servlet vs. WebFlux: Two Non-Interchangeable DSLs

Legacy WebFlux code uses `@EnableWebFluxSecurity` and `ServerHttpSecurity`, not Servlet’s `WebSecurityConfigurerAdapter`.

| Servlet MVC | Reactive WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| `requestMatchers(...)` | `pathMatchers(...)` |
| `UsernamePasswordAuthenticationFilter` | Authentication WebFilters |
| `HttpSession`/`SecurityContextHolder` | `WebSession`/`ReactiveSecurityContextHolder` |
| `OncePerRequestFilter` | `WebFilter` |
| Servlet `jakarta.servlet.*` | Reactive APIs |

WebFlux configuration example (snippet, not a full project):

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(auth -> auth
                    .pathMatchers("/public/**").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Do not try to call MVC’s `HttpSecurity` in WebFlux or swap `ServerHttpSecurity` for `HttpSecurity` merely because both contain “security”.

## 15. Standalone Java 17: Distinguishing Public, Ignored, and Filter-Chain Selection

This example does not import Spring so it can **compile with Java SE 17** and produce deterministic output. It models several core concepts:

- Legacy config using `web.ignoring("/assets/**")` for public assets → allowed, yet **runs no Spring Security filters**.
- Modern config using `requestMatchers("/assets/**").permitAll()` → allowed, yet **still runs filters**.
- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority.
- `securityMatcher("/api/**")` selects the API chain, without replacing the authorization rules inside.
- Without a fallback chain, other requests may **not be protected by Spring Security**.

Create **`LegacySecurityPolicyDemo.java`**:

```java
import java.util.*;

public class LegacySecurityPolicyDemo {
    record Request(
            String path, boolean authenticated, Set<String> authorities) {}

    record Decision(
            boolean allowed, boolean securityFiltersApplied,
            String matchedRule) {}

    // Simple prefix pattern simulation, NOT an Ant/Mvc/PathPattern engine.
    static boolean matches(String pattern, String path) {
        if (pattern.equals("/**")) return path.startsWith("/");
        if (pattern.endsWith("/**")) {
            String prefix = pattern.substring(0, pattern.length() - 3);
            return path.equals(prefix) || path.startsWith(prefix + "/");
        }
        return pattern.equals(path);
    }

    static boolean role(Request request, String role) {
        return request.authenticated()
                && request.authorities().contains("ROLE_" + role);
    }

    static Decision evaluate(Request r, boolean modern) {
        if (matches("/assets/**", r.path())) {
            return modern
                    ? new Decision(true, true, "assets_permitAll")
                    : new Decision(true, false, "assets_ignored");
        }

        if (matches("/login", r.path())) {
            return new Decision(true, true, "login_permitAll");
        }

        if (matches("/admin/**", r.path())) {
            return new Decision(
                    role(r, "ADMIN"), true, "admin_hasRole");
        }

        return new Decision(
                r.authenticated(), true, "fallback_authenticated");
    }

    static String apiChainSelection(String path, boolean hasFallback) {
        if (matches("/api/**", path)) return "API_CHAIN";
        return hasFallback ? "DEFAULT_CHAIN" : "NO_SECURITY_CHAIN";
    }

    public static void main(String[] args) {
        Request assets = new Request("/assets/app.css", false, Set.of());
        Decision oldAssets = evaluate(assets, false);
        Decision newAssets = evaluate(assets, true);

        System.out.println("oldAssetsAllowed=" + oldAssets.allowed());
        System.out.println("oldAssetsFiltered="
                + oldAssets.securityFiltersApplied());
        System.out.println("newAssetsAllowed=" + newAssets.allowed());
        System.out.println("newAssetsFiltered="
                + newAssets.securityFiltersApplied());

        Request guestAdmin =
                new Request("/admin/report", false, Set.of());
        Request userAdmin = new Request(
                "/admin/report", true, Set.of("ROLE_USER"));
        Request actualAdmin = new Request(
                "/admin/report", true, Set.of("ROLE_ADMIN"));

        System.out.println("guestAdminAllowed="
                + evaluate(guestAdmin, true).allowed());
        System.out.println("userAdminAllowed="
                + evaluate(userAdmin, true).allowed());
        System.out.println("adminAllowed="
                + evaluate(actualAdmin, true).allowed());

        System.out.println("anonymousLoginAllowed="
                + evaluate(new Request("/login", false, Set.of()), true)
                        .allowed());
        System.out.println("anonymousPrivateAllowed="
                + evaluate(new Request("/private", false, Set.of()), true)
                        .allowed());

        System.out.println("apiRequestChain="
                + apiChainSelection("/api/orders", true));
        System.out.println("uiRequestChain="
                + apiChainSelection("/ui/home", true));
        System.out.println("missingFallback="
                + apiChainSelection("/ui/home", false));
    }
}
```

Run:

```bash
javac LegacySecurityPolicyDemo.java
java LegacySecurityPolicyDemo
```

**Verified stdout:**

```text
oldAssetsAllowed=true
oldAssetsFiltered=false
newAssetsAllowed=true
newAssetsFiltered=true
guestAdminAllowed=false
userAdminAllowed=false
adminAllowed=true
anonymousLoginAllowed=true
anonymousPrivateAllowed=false
apiRequestChain=API_CHAIN
uiRequestChain=DEFAULT_CHAIN
missingFallback=NO_SECURITY_CHAIN
```

### Reading the Output Correctly

- Both old and new assets are “allowed”, yet `oldAssetsFiltered=false` and `newAssetsFiltered=true` demonstrate why **ignoring is not equivalent to permitAll**.
- Guests and `ROLE_USER` users are denied the admin route; only an authenticated user with `ROLE_ADMIN` passes the rule.
- `anonymousLoginAllowed=true` shows the login page must be reachable before authentication.
- `anonymousPrivateAllowed=false` illustrates the fallback requiring login.
- `apiRequestChain=API_CHAIN` and `uiRequestChain=DEFAULT_CHAIN` illustrate first-match chain selection.
- `missingFallback=NO_SECURITY_CHAIN` shows the risk of defining an API-only chain while leaving the rest unprotected.

**Limitation:** `matches(...)` only supports exact paths and a very simple `/**` suffix. It does not model `AntPathRequestMatcher`, `MvcRequestMatcher`, `PathPatternRequestMatcher`, URL decoding, `servletPath`, `contextPath`, firewalls, HTTP methods, CSRF, sessions, or JWTs. Integration tests with real Spring Security are required before treating any policy as equivalent.

## 16. Testing Rules After Migration with Spring Security Test

Confirming the new configuration **compiles** is not enough. You must verify requests/responses with `spring-security-test` + Spring MVC `MockMvc`, using real application beans and the real security chain.

Dependencies in a Spring Boot 3.x project with test setup:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Test fragment template (requires matching `/private`, `/admin/report`, and static asset controller routes in the test app):

```java
@SpringBootTest
@AutoConfigureMockMvc
class MigrationSecurityTest {

    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadPrivatePage() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loggedInUserWithoutAdminRoleIsForbidden() throws Exception {
        mvc.perform(get("/admin/report")
                .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminHasAccessToAdminRoute() throws Exception {
        mvc.perform(get("/admin/report")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk());
    }

    @Test
    void realPasswordLoginStillWorks() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("demo-only-password"))
                .andExpect(authenticated());
    }
}
```

Imports: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.test.web.servlet.MockMvc`, `org.junit.jupiter.api.Test`, static `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin`, `org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated`, and `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status`.

**Note:** `with(user(...))` simulates an authenticated principal to test authorization, **without verifying passwords** through `DaoAuthenticationProvider`. To test the form-login credential flow, use `formLogin()` with a real user source/encoder in test configuration. In many projects, unauthorized requests return 401 JSON (HTTP Basic/Bearer) instead of a redirect; adapt assertions to the **agreed contract** rather than hard-coding every app to expect 302.

When testing routes lacking controller handlers in the fixture, you may get `404` after authorization permits the request; provide the endpoint or assert the filter/authorization outcome intentionally rather than expecting `200` on a nonexistent route.

### Testing Bypass-Prone Cases

| Test | Expectation |
| --- | --- |
| Anonymous `GET /login` | Allowed; login page works |
| Anonymous `GET /private` | Login redirect or 401 per mechanism |
| Anonymous `GET /admin/report` | Denied access |
| `ROLE_USER` accesses `/admin/report` | 403 |
| `ROLE_ADMIN` accesses `/admin/report` | Allowed when resource exists |
| `GET /assets/app.css` | Public, yet security headers remain when using permitAll |
| `POST /login` wrong password | Failure handler, no authenticated session created |
| `POST /transfer` missing CSRF on cookie-based browser | Rejected per CSRF policy |
| `POST /logout` with valid CSRF | Session invalidated per policy |
| `GET /adminx` | Not confused with `/admin/**` |
| `GET /ADMIN/report` | Case handling per matcher policy |
| Servlet context path other than `/` | Rules match path accurately |
| Encoded slash/semicolon/traversal | Firewall/matcher handles safely |
| API chain `/api/**` and browser chain `/**` | First matching chain selected accurately |
| `GET /error` / ERROR dispatch | Error handling avoids secondary failure |
| Session cookie after login | ID created/rotated and context persisted |
| Method `@PreAuthorize` invoked | Denied when unauthorized |
| WebSecurity ignoring static | Explicitly aware Spring Security does not apply headers |
| Boot version bump | Dependencies resolve, no javax servlet/removed APIs remain |
| HTTP Basic vs. form login | Entry points, request matchers, 401/403/302 accurate |
| OAuth2 resource server/custom filters | Real matchers and providers, not just bean presence |
| Zero matching chains | No unintended unprotected routes |

## 17. Checklist for Investigating Compile Errors During Upgrades

### “Cannot resolve symbol WebSecurityConfigurerAdapter”

- Confirm you are on Spring Security 6.x/7.x.
- Remove inheritance and move `configure(HttpSecurity)` logic to a `SecurityFilterChain` bean.
- Split `configure(WebSecurity)` into a choice between `permitAll` and `WebSecurityCustomizer`.
- Split `configure(AuthenticationManagerBuilder)` into user source/provider/manager beans.
- Never add a Security 5.x dependency to Boot 3 just to bring back the old class: that readily causes Spring Framework/Jakarta conflicts.

### “Cannot resolve method antMatchers” or “mvcMatchers”

- Replace with `requestMatchers(...)` matching the DSL.
- Check imports, Spring MVC presence, servlet paths, and matcher behavior.
- On 6.5 preparing for 7, evaluate `PathPatternRequestMatcher`.
- Run URL security tests; do not merely satisfy the compiler syntactically.

### “package javax.servlet does not exist”

- Boot 3/Spring Framework 6 moved to Jakarta packages: `jakarta.servlet.*`.
- Check custom Filters, HttpServletRequest/Response, interceptors, and third-party libraries.
- Do not mix `javax.servlet.Filter` with `jakarta.servlet.Filter` via casts or bridges.
- Check servlet container version and plugin/dependency BOM.

### “No qualifying bean of type AuthenticationManager”

- `authenticationManagerBean()` from the adapter no longer exists.
- If a custom flow needs a manager, declare/obtain it via explicit configuration or `AuthenticationConfiguration.getAuthenticationManager()` in the right context.
- Verify provider, encoder, and UserDetailsService wiring.
- Avoid circular dependencies: a manager bean injecting itself or a filter bean injecting an uninitialized security config.

### “POST /login returns 404”

- Does a `SecurityFilterChain` have a `securityMatcher` excluding `/login`?
- Are `formLogin()`/`loginProcessingUrl()` enabled on the right chain?
- Does the custom login page GET route exist?
- Does a reverse proxy/path rewrite/contextPath alter the actual request path?

### “Every POST now returns 403”

- Check CSRF tokens and mechanisms rather than disabling CSRF hastily.
- If clients moved to stateless Bearer, analyze credential transport and `SecurityFilterChain` separately.
- Check filter order/CSRF matchers, error dispatches, and request mappings.

### “Static assets no longer have security headers”

- Is `web.ignoring()` active? If so, filters do not run.
- Switch appropriate assets to `permitAll` to keep the header writer active.
- Check cache headers/CSP at edge and app to avoid conflicting duplicate headers.

## 18. Common Migration Mistakes

**Mistake 1 — Only renaming the class.** `WebSecurityConfigurerAdapter` cannot be replaced by `SecurityFilterChain` while keeping the three overrides; responsibilities must be split cleanly.

**Mistake 2 — Replacing `antMatchers` with `requestMatchers` without testing paths.** Security 6/7 changes matcher semantics; URL edge cases can shift.

**Mistake 3 — Switching `web.ignoring` to `permitAll` while claiming zero behavior change.** Static access is similar, but filters and headers differ.

**Mistake 4 — Using `web.ignoring("/api/**")` to make an API public.** Bypassing all security filters can inadvertently drop CSRF/headers/observability; audit scope and use controlled authorization policies.

**Mistake 5 — Forgetting `anyRequest` or a fallback chain.** A URL matching no chain can fall completely outside Spring Security protection.

**Mistake 6 — Setting the wrong `@Order`.** A `/**` chain placed first prevents `/api/**` chains below it from ever matching.

**Mistake 7 — Thinking `securityMatcher` and `requestMatchers` are equivalent.** One selects the chain; the other selects policies inside the chain.

**Mistake 8 — Disabling CSRF to “fix all 403s”.** If browsers use session cookies/form login, CSRF risk remains intact.

**Mistake 9 — Dropping the password encoder or using `{noop}`.** Never weaken password storage to fix compile/login errors; credential migration is a separate track.

**Mistake 10 — Assuming `@Bean AuthenticationManager` is automatically used by web filters.** Verify the actual manager and filter chain wiring.

**Mistake 11 — Dropping `@EnableGlobalMethodSecurity` when removing the adapter.** Method-level authorization may silently stop or change defaults.

**Mistake 12 — Converting `securedEnabled` to `@EnableMethodSecurity` and unintentionally enabling prePost.** Audit annotation flags.

**Mistake 13 — Mixing `javax.servlet` and `jakarta.servlet`.** Causes compile errors or third-party filters failing to register properly.

**Mistake 14 — Collapsing multi-chain setups into one overly broad chain.** OAuth/Basic/form errors, session policies, and endpoint matchers no longer match prior behavior.

**Mistake 15 — Confusing 401/403/302.** HTTP Basic/Bearer/unauthenticated requests use different entry points than form login; a new status code does not necessarily mean lost roles.

**Mistake 16 — Treating `@WithMockUser` tests as login tests.** The annotation bypasses credential verification; test `formLogin` and real providers.

**Mistake 17 — Securing only URLs and neglecting services.** A service can be invoked from multiple entry points; maintain method/domain authorization.

**Mistake 18 — Adopting PathPattern without testing reverse-proxy `servletPath`.** Context roots, path prefixes, and encoded paths can introduce bypasses or mismatches.

**Mistake 19 — Disabling `StrictHttpFirewall` when an old matcher rejects a path.** Can open path traversal/malformed URLs; fix matchers/routing properly instead.

**Mistake 20 — Failing to verify endpoints created by security filters.** Form login/logout/OAuth callbacks can fall outside `securityMatcher` and vanish.

**Mistake 21 — Adding multiple `SecurityFilterChain` beans without ordering.** Behavior diverges from legacy adapters that had explicit order.

**Mistake 22 — Treating deprecation cleanup as finishing a Boot upgrade.** Java 17, Jakarta, Spring Framework 6, dependencies, and serializers must all be compatible.

**Mistake 23 — Testing only GET.** POST/CSRF, login/logout, OAuth callbacks, and ERROR dispatches commonly expose migration bugs.

**Mistake 24 — Copying configs from blogs targeting a different version.** DSL imports/types vary; always consult the reference for the running major/minor version.

**Mistake 25 — Testing in MockMvc without security filters.** If `@AutoConfigureMockMvc(addFilters=false)` or standalone setup omits the filter chain, authorization tests can pass falsely.

## 19. Safe Phased Migration Plan

1. **Inventory:** lock down Java, Boot/Security versions, and list legacy adapters, method-security annotations, providers, servlet filters, and proxy routes.
2. **Behavior snapshot:** build a matrix of URL/method/role, status codes, CSRF, login/logout, cookies/sessions, provider responses, and headers.
3. **Prepare 5.8 if upgrading from 5.x:** clean up deprecated APIs where possible and establish test coverage before bumping majors.
4. **Update configuration entrypoints:** split adapters into `SecurityFilterChain` beans, decide where `WebSecurityCustomizer` is truly needed, and expose proper `UserDetailsService`/`PasswordEncoder`/manager beans.
5. **Preserve authorization:** keep matcher ordering, roles/authorities, security matcher scopes, fallback chains, and method security flags intact.
6. **Switch Servlet/Jakarta:** update imports, dependency coordinates, custom filters, and third-party integrations.
7. **Verify authentication:** check form/Basic/OIDC/JWT, CSRF, session rotation, context persistence, and manager/provider wiring.
8. **End-to-end behavior tests:** run positive + negative HTTP matrices with Spring Security Test/MockMvc and real browser/proxy checks where appropriate.
9. **Prepare for 7.x:** move fully to Lambda DSL, test `PathPatternRequestMatcher` in 6.5, and update custom DSL `apply` → `with`.
10. **Controlled rollout:** canary release, monitor login 401/403/302 rates, auth failures, CSRF, and chain metrics, and roll back on policy regressions.

### Key Behaviors to Compare Before and After

| Behavior | Before Migration | Must Confirm After Migration |
| --- | --- | --- |
| Anonymous access to `/login` | Allowed | Allowed |
| Anonymous access to private API | Denied/redirect | Matching denial/redirect |
| USER accessing ADMIN | 403 | 403 |
| ADMIN accessing ADMIN | Allowed | Allowed |
| Static assets | Ignored or permitAll | Explicitly confirm keeping ignoring vs. upgrading to permitAll |
| Form login | POST/login path, remember-me, session | Same path or intentional change |
| Logout/CSRF | Method + token policy | Not weakened |
| OAuth redirect callbacks | Correct endpoints/state | Not blocked by `securityMatcher` |
| AuthenticationProvider | JDBC/LDAP/custom flow | Right provider + encoder, no double registration |
| Method `@PreAuthorize`/`@Secured` | On/off per config | Preserve flags and ownership checks |
| Multiple chains | In legacy order | No fallback gaps |
| Exception handling | 401/403/redirect handler | No unexpected semantic shifts |
| Response headers | Applied/not applied | No lost HSTS/CSP security headers |
| Error dispatch | `/error` and FORWARD | No secondary unauthorized error |
| Proxy/servlet path | Public vs. internal URLs | Request matchers still enforce properly |

## 20. Final Checklist When Reading Any Legacy Spring Security Guide

- [ ] Read the right **version** of the docs? Know 5.7 deprecated, 6.0 removed, 6.5 preparing for 7?
- [ ] Identified all `configure` overrides in the `WebSecurityConfigurerAdapter` class?
- [ ] Separated the `web.ignoring` list from `permitAll`?
- [ ] Captured the exact order of `antMatchers/mvcMatchers/anyRequest` rules and permissions?
- [ ] When using `SecurityFilterChain`, verified `http.build()` and which bean Boot actually selects?
- [ ] Distinguished `securityMatcher` (selects chain) from `requestMatchers` (selects internal rules)?
- [ ] Confirmed a fallback chain exists for paths not matching specialized chains?
- [ ] Ensured login/logout/OAuth2 callbacks were not stranded outside chain scope?
- [ ] Mapped `AuthenticationManagerBuilder` cleanly to UserDetailsService/PasswordEncoder/providers?
- [ ] Avoided `{noop}` and avoided disabling CSRF over migration errors?
- [ ] Converted `@EnableGlobalMethodSecurity` to `@EnableMethodSecurity` and checked defaults?
- [ ] Updated `javax.servlet` to `jakarta.servlet` per Boot 3/Framework 6?
- [ ] Prepared Lambda DSL and PathPattern rules for Security 7?
- [ ] Tested routes with context paths, servlet paths, odd encodings, roles, CSRF, and ERROR dispatches?
- [ ] Tested real login through filters/providers, not just `@WithMockUser`?
- [ ] Verified static security headers, session cookies, CSRF, and active filter chains via integration tests?
- [ ] Confirmed no new endpoints became public due to missing fallbacks or overly broad matchers?
- [ ] Confirmed no deprecated APIs or custom filters alter behavior across major upgrades?

### Official References

- Spring Security 5.7 API — `WebSecurityConfigurerAdapter` deprecated: https://docs.spring.io/spring-security/site/docs/5.7.0/api/org/springframework/security/config/annotation/web/configuration/WebSecurityConfigurerAdapter.html
- Spring Security 6.5 — Java Configuration, multiple `SecurityFilterChain`: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — Authorization for Servlet HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security / migration flags: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — Preparation for 7, Configuration Migrations/Lambda DSL: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security 6.5 — Preparation for 7, Web Migrations/PathPattern: https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html
- Spring Security 6.5 API — `PathPatternRequestMatcher`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html
- Spring Boot 3 Migration Guide (maintained by spring-projects): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Spring Security 6.5 — Spring Security Test, MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html

**Conclusion:** reading legacy configurations is not merely spotting deprecated classes. You must reconstruct **filter chains, matcher scopes, authentication sources, method authorization, filter-generated endpoints, and default security controls**. When moving to `SecurityFilterChain`/Lambda DSL, prove through tests that critical permissions and processing paths have not weakened, while proactively addressing differences in PathPattern, Jakarta, and Spring Security 7.
