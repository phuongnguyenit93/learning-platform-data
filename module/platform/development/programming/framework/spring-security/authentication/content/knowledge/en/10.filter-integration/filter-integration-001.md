# DelegatingFilterProxy, FilterChainProxy, and Where Credentials Are Received

Spring Security in a **Servlet** application protects HTTP requests before they reach `DispatcherServlet` and controllers. The entry point of this system is a **Servlet Filter** chain. In that chain, **`DelegatingFilterProxy`** serves as the bridge from the servlet container to a Spring bean; that bean is typically named **`springSecurityFilterChain`** and is a **`FilterChainProxy`**. `FilterChainProxy` checks which **`SecurityFilterChain`** matches the current request **first**, then executes the security filters of the selected chain in exact order. Only the **authentication filter** at the appropriate position receives the password, HTTP Basic header, Bearer token, or callback from an identity provider—**`DelegatingFilterProxy` does not decode or verify credentials itself**.

This is foundational knowledge when learning Spring Security Authentication: if an endpoint enters the **wrong security chain**, if an authentication filter runs **after the authorization filter**, or if a custom filter is registered by the container **a second time outside `FilterChainProxy`**, the application can lose authentication, return confusing 401/403 responses, or even partially bypass controls.

This lesson belongs to the **Filter Integration** group. The goal is to understand the exact responsibilities and positions of `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, and authentication filters; master chain selection, configuring multiple chains, adding custom filters, the `SecurityContext` lifecycle, session/JWT scenarios, debugging techniques, along with a runnable **Java 17** example to observe chain selection and filter execution.

## 1. Architecture from HTTP Request to Controller

~~~text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty/Undertow...)
    |
    +-- Container Filter A (if any)
    |
    +-- DelegatingFilterProxy
    |       Spring bean name: "springSecurityFilterChain"
    |       |
    |       '--> FilterChainProxy (Spring Security)
    |                 |
    |                 +-- Select first SecurityFilterChain with matching matcher
    |                 |
    |                 +-- SecurityContextHolderFilter (load context)
    |                 +-- Protection filters: headers / CORS / CSRF...
    |                 +-- Corresponding authentication filter
    |                 |     form / HTTP Basic / bearer JWT / custom
    |                 |     -> AuthenticationManager / AuthenticationProvider
    |                 |     -> Trusted Authentication
    |                 +-- AnonymousAuthenticationFilter (if needed)
    |                 +-- ExceptionTranslationFilter
    |                 '--> AuthorizationFilter
    |
    +-- Container Filter B (if any)
    |
    v
DispatcherServlet -> Controller -> Service
~~~

This diagram is a **conceptual flow**, not a fixed list of filters. Spring Security builds the actual filter list depending on `HttpSecurity`, the authentication mechanism, version, and configuration. An endpoint that does not use form login will not need `UsernamePasswordAuthenticationFilter`. A bearer resource server typically has `BearerTokenAuthenticationFilter`. Container filters outside Spring Security may appear before or after the proxy depending on container order, but their positions are **not automatically controlled by `FilterChainProxy`**.

### 1.1. Three Classes Whose Names Are Often Confused

| Component | Who registers/manages it? | Primary responsibility | Does it directly verify passwords/JWTs? |
|---|---|---|---|
| `DelegatingFilterProxy` | Called by Servlet container; delegate bean belongs to Spring context | Forwards `doFilter` to a Spring-managed `Filter` bean | **No** |
| `FilterChainProxy` | Spring Security, usually bean `springSecurityFilterChain` | Selects `SecurityFilterChain`, executes security filters, coordinates firewall/cleanup | **Does not verify credentials itself**; orchestrates filters |
| `SecurityFilterChain` | Spring Security configuration, usually from `HttpSecurity.build()` | Holds a `RequestMatcher` and an **ordered list of Filters** for a request scope | The chain itself does not; filters inside may |
| `UsernamePasswordAuthenticationFilter` and similar | Security filter inside a chain | Reads credentials/tokens from request, invokes authentication mechanism | **Handles credential ingestion**, delegates verification to provider/manager |
| `AuthenticationManager` and `AuthenticationProvider` | Spring Security authentication subsystem | Validates evidence and returns trusted `Authentication` or throws an error | **Yes**, depending on provider |

**Do not conflate the two uses of "chain"**: the container `FilterChain` is the entire path of a request through servlet filters to the servlet; a `SecurityFilterChain` is a list of **security filters** selected by `FilterChainProxy` according to a matcher.

### 1.2. Why Need a Proxy Instead of Registering Every Filter with the Container?

The Servlet container understands objects conforming to `jakarta.servlet.Filter` and registration order, but by default it does not understand the Spring `ApplicationContext`, DI, or transaction/security beans. `DelegatingFilterProxy` lets **the container invoke a Spring bean** created and configured by the Spring ecosystem.

`FilterChainProxy` also supports what simple URL filter mappings cannot easily express: multiple filter chains applied via matchers based on path, HTTP method, or conditions on `HttpServletRequest`. It is also the integration point for `HttpFirewall` and the `SecurityContext` cleanup lifecycle to reduce state leakage across requests.

## 2. DelegatingFilterProxy: The Servlet ↔ Spring Bridge

The class resides in Spring Framework:

~~~java
org.springframework.web.filter.DelegatingFilterProxy
~~~

It **does not belong** to the `org.springframework.security...` package, but is commonly used to bring Spring Security's filter infrastructure into the Servlet container.

### 2.1. The Bean Name springSecurityFilterChain

In a standard Servlet Spring Security configuration, there is an infrastructure Spring bean named:

~~~text
springSecurityFilterChain
~~~

This bean is typically a `FilterChainProxy`. `DelegatingFilterProxy` looks up that `Filter` bean by name, then delegates the call. Illustrative pseudo code:

~~~java
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain containerChain)
        throws IOException, ServletException {

    Filter springBean = lookupBean("springSecurityFilterChain");
    springBean.doFilter(request, response, containerChain);
}
~~~

**This is pseudo code**, because `lookupBean` only illustrates looking up the Spring bean, not an API you can call directly. `DelegatingFilterProxy` also handles lifecycle details, initialization, and bean lookup according to Spring Framework.

If the container invokes the proxy but cannot find the target bean, the application may fail at startup or upon receiving a request. Do not manually create another bean with the same name `springSecurityFilterChain` without understanding how Spring Security manages it.

### 2.2. Registration in Traditional Web Applications

For **WAR/web.xml** deployments (not Spring Boot auto-configuration), a common registration is:

~~~xml
<filter>
    <filter-name>springSecurityFilterChain</filter-name>
    <filter-class>org.springframework.web.filter.DelegatingFilterProxy</filter-class>
</filter>

<filter-mapping>
    <filter-name>springSecurityFilterChain</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

The container registers **a filter named `springSecurityFilterChain`**, with class `DelegatingFilterProxy`. At runtime, the proxy delegates to the **Spring bean of the same name**, not to a servlet or controller with that name.

In Servlet 3+, you can register it via a corresponding Java initializer, such as extending `AbstractSecurityWebApplicationInitializer`. **In Spring Boot with standard auto-configuration, the filter proxy is usually registered automatically**: do not copy `web.xml` or add a second `FilterRegistrationBean` just to "enable Spring Security".

### 2.3. Lifecycle and Dependency Injection

The delegating proxy resolves the initialization timing mismatch between the container and the Spring context, allowing security filters to live inside the IoC container. Filter beans can therefore use Spring DI and Spring lifecycle callbacks. `FilterChainProxy` does not invoke `init`/`destroy` on each delegate security filter the way the container does for directly registered filters; if a custom filter needs resource initialization/cleanup, design it around the Spring bean lifecycle.

**Remember:** `DelegatingFilterProxy` is a **bridge**, not the place to put password verification logic, JWT parsing, or user queries.

## 3. FilterChainProxy: The Central Dispatcher

`org.springframework.security.web.FilterChainProxy` implements `jakarta.servlet.Filter` and manages **a list of `SecurityFilterChain` instances**. Each `SecurityFilterChain` has its own matcher and security filters.

### 3.1. Which Chain Is Selected for a Request?

Suppose an application has three chains in order:

~~~text
Chain 1: /api/admin/**  -> JWT + admin policy
Chain 2: /api/**        -> JWT + API scope
Chain 3: /**            -> Form login + session

Request GET /api/admin/users:
  Chain 1 matches -> ONLY Chain 1 runs

Request GET /api/orders:
  Chain 1 does not match
  Chain 2 matches -> ONLY Chain 2 runs

Request GET /home:
  Chain 1 does not match
  Chain 2 does not match
  Chain 3 matches -> ONLY Chain 3 runs
~~~

**Crucial rule: `FilterChainProxy` selects the **first** matching security chain.** It **does not merge** filters from all matching chains, nor does it "run chain 1 then continue to chain 2" after chain 1 finishes. Therefore, more specific chains must have higher priority than general chains.

If `/**` is configured first, a request to `/api/admin/users` also matches the general chain and **the API chains below it are never selected**. This is a very common configuration mistake.

### 3.2. What If No SecurityFilterChain Matches?

The request can proceed down to the Servlet/container **without being protected by Spring Security** through any chain. This differs from having a matching chain whose authorization rule is `permitAll()`.

- **No chain matches:** no authentication, authorization, security headers, or protection filters that the app expects from the Spring Security chain.
- **Chain matches + `permitAll()`:** the request still passes through the chain's filters and can receive other protections (headers, CSRF policy, logging, SecurityContext, etc.) even though the endpoint does not require login.

There should be an appropriate fallback chain if the requirement is for every endpoint to be covered by Spring Security. Test with real routes rather than just seeing that beans were created and assuming every URL is secure.

### 3.3. Where Does HttpFirewall Fit?

`FilterChainProxy` coordinates with `HttpFirewall` to validate/normalize how the request path is viewed when evaluating matchers and performing security processing. By default, Spring Security provides a firewall mechanism suited to the configuration, helping reduce risks from invalid or inconsistent paths between the container and security matchers.

Do not disable the firewall or arbitrarily allow encoded slashes, duplicate slashes, path traversal, or unusual delimiters just to make a broken URL "work". Any firewall change must be accompanied by testing request mapping, reverse proxies, normalization, and authorization; a URL interpreted differently by the container and the security matcher can lead to a **bypass**.

### 3.4. SecurityContext and Cleanup

The Spring Security filter infrastructure manages the `SecurityContext` per request, typically using `ThreadLocal` via `SecurityContextHolder` and the appropriate filter. The context is loaded or created when the request begins, may be updated after authentication, and is cleared when execution completes so that a servlet pool thread does not carry an old user's identity into another request.

Do not write a shared singleton/static field named `currentUser`. Also do not manually call `setContext` from a raw username before a provider authenticates it: the holder is where **verified authentication results are stored**, not a tool for turning input into a trusted user.

## 4. SecurityFilterChain: Filter Selection Boundary, Not Just URL Rules

A `SecurityFilterChain` consists of:

1. A **`RequestMatcher`** that decides whether the chain applies to the request.
2. An **ordered list of `Filter`s** that run for the selected request.

In Spring Boot/Spring Security 6.x, it is typically configured via `@Bean SecurityFilterChain` and `HttpSecurity`:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **configuration snippet** that requires imports and an appropriate Spring Boot/Spring Security runtime. It creates a default chain applying to all remaining requests, with authn/authz filters according to the DSL. `requestMatchers("/", "/assets/**").permitAll()` specifies permissions **within the selected chain**, and does not change the overall matcher of the chain.

### 4.1. How Does securityMatcher Differ from requestMatchers?

This is one of the most important distinctions when working with multiple chains:

| Syntax | Effect | Consequence |
|---|---|---|
| `http.securityMatcher("/api/**")` | Selects **which requests enter this chain** | Other requests do not use this chain's filters |
| `http.authorizeHttpRequests(a -> a.requestMatchers("/api/public/**").permitAll())` | Defines **authorization rules inside the chain** | Requests still traverse the chain; login is simply not required for that matcher |
| `http.authorizeHttpRequests(a -> a.anyRequest().authenticated())` | Default rule inside the selected chain | Does not make the chain apply to all URLs if `securityMatcher` is narrow |
| `web.ignoring()` or excluding requests from security chains | **Bypasses security filters** for those requests | May lose security headers and other protective mechanisms |

For example, if you configure:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

`/api/public/info` still enters the **API chain** and receives the filters configured for the API; authorization allows anonymous access at that endpoint. `/home` does not enter the API chain; it can be handled by a different chain.

### 4.2. @Order Is Chain Priority, Not Internal Filter Order

Use `@Order(1)`, `@Order(2)`, or Spring-determined ordering to coordinate **the `SecurityFilterChain` beans**:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    // API chain
    return http.securityMatcher("/api/**").build();
}
~~~

This is a short illustrative example. Do not think `@Order(1)` on this bean means a custom authentication filter runs before `BasicAuthenticationFilter` **inside** the chain. Internal filter ordering is determined by the Spring Security DSL, filter order registration, and `addFilterBefore/After/At`.

## 5. Where Is Authentication Received?

**Credentials are received at the corresponding authentication filter**—typically located inside `SecurityFilterChain` after necessary infrastructure components and before the authorization stage. These filters read a specific credential format, construct an unverified `Authentication` request or equivalent, and pass it to the appropriate `AuthenticationManager`/`AuthenticationProvider` or verifier.

### 5.1. Table of Common Mechanisms

| Request type | Common filter | What is extracted from request? | Who verifies it? |
|---|---|---|---|
| Form login | `UsernamePasswordAuthenticationFilter` | Username/password from login POST form | `AuthenticationManager` → provider, e.g. `DaoAuthenticationProvider` |
| HTTP Basic | `BasicAuthenticationFilter` | `Authorization: Basic ...` | `AuthenticationManager` → provider |
| Bearer JWT/OAuth2 access token | `BearerTokenAuthenticationFilter` | `Authorization: Bearer ...` | `AuthenticationManager`/`JwtAuthenticationProvider` + `JwtDecoder` or opaque token introspector |
| OAuth2/OIDC login | `OAuth2LoginAuthenticationFilter` | Authorization response at configured callback | OAuth2/OIDC components and corresponding provider |
| Remember-me (if enabled) | `RememberMeAuthenticationFilter` | Remember-me cookie | RememberMeServices/authentication manager per policy |
| Custom API key | Application-designed filter | Header/token per application protocol | Vetted custom verifier/provider |

The filter that **receives** credentials is not always the component that **verifies** every detail. For example, `UsernamePasswordAuthenticationFilter` does not directly compare bcrypt hashes in the database. It creates an unauthenticated `UsernamePasswordAuthenticationToken` and calls `AuthenticationManager`; the provider loads `UserDetails` and calls `PasswordEncoder.matches(...)`.

### 5.2. Concrete Form Login Flow

~~~text
POST /login
  |
  v
UsernamePasswordAuthenticationFilter
  |
  +--> Extract username/password from HttpServletRequest
  +--> UsernamePasswordAuthenticationToken (unauthenticated)
  +--> AuthenticationManager.authenticate(request)
  |      |
  |      +--> DaoAuthenticationProvider
  |               +--> UserDetailsService.loadUserByUsername
  |               +--> PasswordEncoder.matches
  |               +--> account status checks
  |
  +-- FAILURE -> AuthenticationFailureHandler, configured response
  |
  '-- SUCCESS
         -> Verified Authentication
         -> SecurityContextHolder / SecurityContextRepository
         -> SessionAuthenticationStrategy / remember-me if enabled
         -> AuthenticationSuccessHandler
~~~

The exact order of callbacks and context persistence depends on the Spring Security version and filter, but **the invariant core** is that credentials are verified **before** the request is treated as a trusted principal. If you write a custom authentication controller or filter, do not construct `UsernamePasswordAuthenticationToken.authenticated(...)` directly from a username and roles sent by the client.

### 5.3. How Do HTTP Basic and Bearer JWT Differ in Where Verification Happens?

~~~text
GET /api/orders
Authorization: Basic <base64 username:password>
  -> BasicAuthenticationFilter
  -> AuthenticationManager / username-password provider
  -> Authentication in the request's SecurityContext

GET /api/orders
Authorization: Bearer <access-token>
  -> BearerTokenAuthenticationFilter
  -> JwtDecoder/JwtAuthenticationProvider or opaque token introspection
  -> Authentication in the request's SecurityContext
~~~

Base64 in Basic **is only encoding, not security**; requests must be protected by TLS. For JWT, the validator must check signature/algorithm, issuer, audience, exp/nbf, and required policies; **do not simply Base64-decode the payload and create an authenticated principal**. A token containing a `roles` claim does not automatically grant access to an account or tenant if the backend has not verified the identity, claims, and authorization.

### 5.4. Successful Authentication Differs from Successful Authorization

After a filter verifies identity, **`AuthorizationFilter`** or method security still needs to decide whether the user is allowed to access the URL/resource. Scenario:

~~~text
Alice: valid credentials -> Authentication succeeds
Alice: calls GET /admin -> lacks ROLE_ADMIN
=> Authorization denies, not "wrong password"
~~~

`ExceptionTranslationFilter` is the bridge that **handles `AuthenticationException`/`AccessDeniedException` from downstream** and invokes the appropriate `AuthenticationEntryPoint` or `AccessDeniedHandler`. It does not authenticate passwords itself; some authentication filters have their own failure handlers and can handle errors before the authorization filter runs.

**Do not assume every HTTP 401 or 403 comes from the same filter.** 401 usually indicates missing/invalid authentication or a challenge; 403 usually indicates denied permissions or another policy such as CSRF. Inspect the actual filter chain and exception source.

## 6. Filter Order: Before, During, and After Authentication

Spring Security guarantees a specific filter order within a chain built with `HttpSecurity`. Although versions and configs produce different lists, the conceptual milestones are typically:

~~~text
Load SecurityContext / set up request context
          |
          v
Pre-authentication protection:
CORS, CSRF, configured header/security policies
          |
          v
Authentication filters:
Basic / form / bearer / custom...
          |
          v
AnonymousAuthenticationFilter (if still unauthenticated)
          |
          v
ExceptionTranslationFilter (translate downstream exceptions)
          |
          v
AuthorizationFilter / authorization checks
          |
          v
Controller / Servlet
~~~

Do not treat a simplified diagram as a fixed "full list"; several filters such as logout, request cache, remember-me, session management, or security context persistence have their own positions. To know the **actual order**, inspect DEBUG logs at startup and TRACE logs when requests run in a test environment.

### 6.1. Why Must Authentication Come Before Authorization?

Suppose authorization checks `hasRole("READER")`, but the authentication filter has not read the bearer token yet. When authorization runs, the context may be null/anonymous, causing valid requests to fail with 401/403. Conversely, assigning a role before verifying the token opens a bypass path.

**Rule:** place a custom filter early enough to produce an `Authentication` for filters that depend on it, without bypassing required protection filters (CSRF/CORS/headers/context initialization).

### 6.2. Methods for Adding Filters

~~~java
http.addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAfter(myFilter, BasicAuthenticationFilter.class);
http.addFilterAt(myFilter, UsernamePasswordAuthenticationFilter.class);
~~~

These three lines are **independent API examples**, not meant to be used simultaneously for the same filter as a meaningful configuration. The methods:

- `addFilterBefore(Filter, Class<?>)`: places the custom filter **before** the reference filter's position.
- `addFilterAfter(Filter, Class<?>)`: places it **after** the reference filter's position.
- `addFilterAt(Filter, Class<?>)`: registers it at the reference filter's **position**. Understand how the DSL registers this: if the default filter still exists in the same slot, do not rely on unguaranteed ordering as if it were a safe "replacement". To change an auth mechanism, explicitly disable or reconfigure the default filter.
- The reference position must be a filter whose order is known to Spring Security. Placing a filter relative to a class without a registered order can cause errors or unexpected behavior.
- Position custom filters by **function**: request logging, authentication, authorization, or post-processing; do not always anchor everything to `UsernamePasswordAuthenticationFilter` because the application might not use form login.

### 6.3. Guidance for Positioning a Custom Authentication Filter

A rule of thumb from Spring Security's architecture: a custom authentication filter should usually sit **after `LogoutFilter`**, meaning after initial context/protection setup, yet before anonymous/authorization. The exact position depends on the filter type, CSRF/CORS policies, other auth mechanisms, and whether the chain should stop when credentials are missing.

If your filter only checks a known quota after authentication, a position after `AnonymousAuthenticationFilter` may fit better; if it must finish before authorization, it must not be placed after `AuthorizationFilter`. In all cases, write security integration tests proving the filter **runs exactly once, enters the right chain, and has a trusted `Authentication` when required**.

## 7. Configuring Multiple SecurityFilterChains in Spring Security 6

Suppose an application has an API using HTTP Basic under `/api/**` (illustrative only) and a website using form login/session for all remaining URLs:

~~~java
@Configuration
@EnableWebSecurity
class WebSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain websiteChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **Spring configuration example** (requiring imports, authentication beans, and a Spring Boot/web app), not a standalone Java 17 file. Depending on your Spring Security/Boot version, use the corresponding DSL. **Do not copy this example to production without defining the provider/user store, CSRF, CORS, HTTPS, session policies, and endpoint behavior.**

Analysis:

- `apiChain` has `@Order(1)` so it is evaluated before `websiteChain`.
- `securityMatcher("/api/**")` limits the API chain to API URLs.
- `/api/health` has `permitAll()` yet still **passes through the API chain**; other configured filters remain active.
- The API chain demonstrates `STATELESS`; it does not by default create a session to store authentication for subsequent requests. HTTP Basic credentials are sent and re-verified per request depending on configuration.
- The website chain has no custom `securityMatcher`, so it matches remaining requests and acts as a fallback.
- Form login uses different filter/session mechanisms from the API. Both chains can share the same `AuthenticationManager`/provider/user store if configured appropriately.

**Note on CSRF:** This example keeps default CSRF settings; state-changing requests (POST/PUT/DELETE) using cookies/browsers may receive 403 when missing a CSRF token, even with a valid password. Do not disable CSRF application-wide just because an API returns 403; determine the auth mechanism and the risk of browsers automatically sending credentials before deciding CSRF scope.

### 7.1. Common Matcher Pitfalls

~~~text
/api/**          matches API paths, e.g. /api/orders
/api/admin/**    narrower scope than /api/**
/**              broad fallback
~~~

Actual matcher behavior can depend on Servlet path, MVC/path matching configuration, HTTP method, and Spring Security version. Do not infer all semantics from a single string expression when the app has multiple servlets, a context path, or special dispatchers. Test with real request URLs via `MockMvc` or integration tests and verify which chain is selected.

### 7.2. Is the Login Endpoint in the Right Chain?

Suppose you write:

~~~java
http.securityMatcher("/secured/**")
    .formLogin(Customizer.withDefaults());
~~~

If the default login endpoint `POST /login` and page `GET /login` fall outside the `/secured/**` matcher, the endpoints provided by Spring Security may **not exist in this security chain**. The result is a 404 or unhandled login, even though the filter bean was created.

To avoid this, include the login URL within an appropriate security matcher, configure `loginProcessingUrl` appropriately, or use a fallback chain that matches the login endpoint. **Filter position within a chain cannot rescue a URL already excluded by the chain's matcher.**

### 7.3. PermitAll vs. Ignoring Spring Security

For a publicly accessible endpoint, you should generally prefer `permitAll()` over bypassing Spring Security completely via `web.ignoring()`. `permitAll()` retains relevant security filters such as header protection and behaviors needed for context/observability depending on configuration.

If an application ignores certain static assets for performance reasons, you must fully understand the impact: those URLs have no security filters and may not receive response headers added by Spring Security. Do not treat "asset" as an excuse to let clients access critical data APIs without going through a security chain.

## 8. Custom Filters in Spring Boot: Avoiding Double Execution

If you declare a `Filter` as a Spring bean (e.g. `@Component` or `@Bean`), **Spring Boot can automatically register it with the Servlet container**. If that same instance is also added via `http.addFilterBefore(...)` into a `SecurityFilterChain`, it can be invoked **twice**:

~~~text
Servlet container filter registration
    -> CustomTokenFilter (1st time)
    -> DelegatingFilterProxy
        -> FilterChainProxy
            -> CustomTokenFilter (2nd time)
            -> AuthorizationFilter
~~~

Consequences:

- Reading tokens/DB twice, increasing latency.
- Setting authentication during a run with the wrong scope or timing.
- Logic consuming the request body or single-use tokens getting triggered again.
- Logging, auditing, and rate limiting counted twice.
- The filter outside `FilterChainProxy` may run before context is loaded or after it has been cleared.

### 8.1. How to Fix This in Spring Boot

If a custom filter must be a Spring bean for dependency injection, you can **disable automatic registration with the Servlet container**:

~~~java
@Bean
FilterRegistrationBean<CustomTokenFilter> customTokenFilterRegistration(
        CustomTokenFilter filter) {
    FilterRegistrationBean<CustomTokenFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

This is a **configuration snippet**, requiring `CustomTokenFilter`, imports, and Boot dependencies; it does not remove the filter from the Spring Security chain, it only prevents the container from auto-registering an extra copy. You then still add the filter to `HttpSecurity` in the proper chain and position.

Another approach is to instantiate the custom filter inside the security configuration and **not declare it as a Servlet Filter bean** for Boot to auto-scan/register. Whichever approach you choose, integration tests must verify that **each request passes through the filter exactly once**, rather than just inspecting bean definitions.

### 8.2. Does OncePerRequestFilter Completely Solve It?

`OncePerRequestFilter` is a Spring Web utility for controlling execution within a certain dispatch/request scope, but it **does not replace** registering the filter in the right chain and position. It can prevent duplicate execution across certain dispatches, yet it does not magically give a filter outside the security chain the full Spring Security lifecycle, nor does it guarantee that all Servlet async/error dispatch configurations behave as you expect.

Consider `shouldNotFilter`, `shouldNotFilterAsyncDispatch`, and `shouldNotFilterErrorDispatch` where appropriate. Container-level `ASYNC`/`ERROR` dispatcher configurations and security dispatcher types can affect when a filter runs again; do not assume "Once" means strictly once across every request lifecycle.

### 8.3. Do Not Read and Consume the Request Body Carelessly

If a custom filter reads the entire `HttpServletRequest.getInputStream()` to look for a password/token in JSON without providing an appropriate body wrapper, the downstream controller may fail to read the payload. For JWTs/API keys, prefer protocol headers; for custom JSON login, use a well-designed authentication filter/converter with body size limits and log protection.

An authentication filter should have defined failure behavior: when a token is invalid, do not continue the chain with a fabricated `Authentication`; when a token is absent on a public endpoint, you can let downstream authorization decide. This distinction must be specified and tested.

## 9. Runnable Java 17 Example: FilterChainProxy First-Match Selection

This example uses **Spring Security Web** and **Spring Test Mock Servlet** to directly demonstrate `FilterChainProxy`'s routing mechanism. We create:

- An API chain with matcher `/api/**`, containing two demo filters named `api.authentication` and `api.authorization`.
- A fallback Web chain with `AnyRequestMatcher.INSTANCE`, containing demo filters `web.authentication` and `web.authorization`.
- Demo `Filter`s that **only print their names and call `chain.doFilter(...)`**, without verifying passwords or issuing Authentication; they make the execution order clearly observable.
- A `FilterChainProxy` containing the API chain before the Web chain.
- An extra run with **only the API chain** to prove that a `/public` request matching no chain still proceeds to the Servlet.

**Distinction:** the program invokes `FilterChainProxy` directly with mock requests so it **does not spin up `DelegatingFilterProxy` or a real container**. Sections 1–2 explain the bridge layer inside a web server; this demo focuses on verifying exact **selection and execution** of actual filter chains rather than faking login.

### 9.1. Project Structure

~~~text
filter-chain-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/FilterChainDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'filter-chain-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.3.8'
    implementation 'org.springframework:spring-test:6.1.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.FilterChainDemo'
}
~~~

Running this requires Java 17+, a compatible Gradle version, and Maven Central on the first download. The sample pins Spring Security Web 6.3.8, Spring Framework Test 6.1.18, and Servlet 6 API for the console demo. A real Spring Boot project should use Spring Boot dependency management/BOM to keep Spring versions aligned.

### 9.2. Full Java File

Create `src/main/java/example/FilterChainDemo.java`:

~~~java
package example;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.DefaultSecurityFilterChain;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.AnyRequestMatcher;

public final class FilterChainDemo {

    static final class NamedFilter implements Filter {
        private final String name;

        NamedFilter(String name) {
            this.name = name;
        }

        @Override
        public void doFilter(
                ServletRequest request,
                ServletResponse response,
                FilterChain chain)
                throws IOException, ServletException {
            System.out.println(name);
            chain.doFilter(request, response);
        }
    }

    private static SecurityFilterChain apiChain() {
        return new DefaultSecurityFilterChain(
                new AntPathRequestMatcher("/api/**"),
                new NamedFilter("api.authentication"),
                new NamedFilter("api.authorization"));
    }

    private static SecurityFilterChain webChain() {
        return new DefaultSecurityFilterChain(
                AnyRequestMatcher.INSTANCE,
                new NamedFilter("web.authentication"),
                new NamedFilter("web.authorization"));
    }

    private static void run(
            FilterChainProxy proxy, String path)
            throws IOException, ServletException {

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        request.setServletPath(path);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        FilterChain servlet = (req, res) -> {
            String uri = ((HttpServletRequest) req).getRequestURI();
            System.out.println("servlet -> " + uri);
        };

        System.out.println("== " + path + " ==");
        proxy.doFilter(request, response, servlet);
    }

    public static void main(String[] args) throws Exception {
        SecurityFilterChain api = apiChain();
        SecurityFilterChain web = webChain();

        FilterChainProxy both =
                new FilterChainProxy(List.of(api, web));

        run(both, "/api/orders");
        run(both, "/home");

        // No fallback: /public does not match /api/**.
        FilterChainProxy apiOnly =
                new FilterChainProxy(List.of(api));
        run(apiOnly, "/public");
    }
}
~~~

### 9.3. Running and Reading the Output

If you created a Gradle Wrapper in the project:

~~~bash
./gradlew run
~~~

If only Gradle is installed, use `gradle run`. On Windows PowerShell with the wrapper, the command is typically `.\gradlew.bat run`.

The `System.out.println` lines from the program (ignoring Gradle logs):

~~~text
== /api/orders ==
api.authentication
api.authorization
servlet -> /api/orders
== /home ==
web.authentication
web.authorization
servlet -> /home
== /public ==
servlet -> /public
~~~

Analysis:

1. Request `/api/orders` matches `AntPathRequestMatcher("/api/**")` first. `FilterChainProxy` runs **only** the two API filters, then the Servlet; it does not run the two Web filters even though the fallback could also match.
2. Request `/home` does not match API, but matches `AnyRequestMatcher.INSTANCE`. The proxy runs the Web chain.
3. With a proxy containing only the API chain, request `/public` matches no chain and therefore passes down to the Servlet **without going through any security filters** in this proxy. That **does not mean** the Servlet container has no other filters at all, only that no Spring Security chain was applied.

**Warning:** `NamedFilter` is an order-observation marker; it **does not perform real authentication or authorization**, despite having `authentication`/`authorization` in its name. To protect production endpoints, use an `HttpSecurity` configuration with authentication providers, authorization policies, exception handling, and standard protection filters.

### 9.4. Experimenting with Order to Understand First-Match

Change:

~~~java
new FilterChainProxy(List.of(api, web))
~~~

to:

~~~java
new FilterChainProxy(List.of(web, api))
~~~

When `/api/orders` is evaluated, `AnyRequestMatcher.INSTANCE` at the front matches immediately; the **Web chain** is selected and the API chain **does not run**. This is why fallback chains must come after specialized chains.

Try adding a chain matching only `/api/admin/**` and placing it before `/api/**`. Test `/api/admin/users` to confirm the specialized chain takes precedence while `/api/orders` still routes to the general API chain.

### 9.5. Limitations and Extensions of the Demo

- The demo invokes `FilterChainProxy` directly without starting a Spring `ApplicationContext` or Servlet container; the `DelegatingFilterProxy` bridge is covered separately.
- There is no real `AuthenticationManager`/`Provider`, `SecurityContextHolderFilter`, `CsrfFilter`, or `AuthorizationFilter`; marker names do not grant permissions.
- `MockHttpServletRequest.setServletPath(path)` lets matchers read the Servlet path in the simulation. In a real container, servlet path, context path, proxy prefix, and MVC mapping must be tested under actual configuration.
- There is no session, TLS, JWT decoder, or login redirect. After understanding selection, follow up with integration tests on a Spring Boot app with real filter chains, rather than relying on the demo to assess production security.
- Later library versions may change recommended matcher APIs. The code pins Spring Security 6.3.x to match the lesson accurately.

## 10. Configuring a Safe Custom Authentication Filter

If you want to ingest a custom API key/JWT, do not place that logic inside `DelegatingFilterProxy` or write a Servlet filter outside all Spring Security chains and assume requests are secure. Choose the appropriate chain and mechanism, ideally using **built-in filters/providers** before building a custom one.

Illustrative *flow outline* for a header-based authentication filter:

~~~text
doFilterInternal(request, response, chain):
    if request is outside the protected matcher:
        chain.doFilter; return

    extract credential from the defined header
    if missing:
        let authorization/appropriate filter decide or return 401
        DO NOT arbitrarily construct an authenticated token

    if present:
        create an UNAUTHENTICATED Authentication request
        invoke a vetted AuthenticationManager / provider
        if failure:
            handle response via AuthenticationEntryPoint/FailureHandler
            DO NOT continue as logged in

        if success:
            newContext = SecurityContextHolder.createEmptyContext()
            newContext.setAuthentication(verified)
            SecurityContextHolder.setContext(newContext)
            if stateful and must persist across subsequent requests:
                SecurityContextRepository.saveContext(...)
            chain.doFilter(...)
~~~

This is **pseudo code**, not a runnable Java implementation. In production you must also design exception handling, cleanup, async dispatch, invalid tokens, rate limiting, account status, error masking, clock skew, credential erasure, bearer-token revocation, and safe logging.

### 10.1. Why Use Standard Mechanisms When Appropriate?

For OAuth2 access tokens/JWTs, Spring Security resource server already provides `BearerTokenAuthenticationFilter`, `JwtDecoder`, issuer validation, authorities conversion, and configurable error handling. Manually parsing base64 JWTs and setting `Authentication` can skip signature, audience, expiry, or key rotation checks.

For username/password forms, `UsernamePasswordAuthenticationFilter` together with `AuthenticationManager`/`DaoAuthenticationProvider` handles many details: failure handlers, credential comparison, context persistence, session strategy, and security events. A custom filter should have a **clear architectural reason** rather than "putting code in a Filter earlier than a Controller feels safer".

### 10.2. Position of a Custom Filter Relative to SecurityContextHolderFilter

A filter running before context is loaded may not see authentication from the session, or may set a context that a subsequent filter replaces or clears as part of its lifecycle. A filter running after authorization will be too late to supply identity for permission checks.

This explains why **filter order is part of security design**. Tests must prove when the context is present, that authentication is established early enough, and that credentials are not retained beyond their required lifecycle.

## 11. Authentication Failure, Exception Handling, and HTTP Status

A request can be blocked before the controller at several points:

| Stage | Example failure | Common response |
|---|---|---|
| Servlet container filter | Request too large, invalid encoding, upstream policy | Container/filter returns error |
| `FilterChainProxy`'s `HttpFirewall` | Rejected URL/path | RequestRejectedException and response per configured handler |
| `CorsFilter`/CORS processing | Origin/header/method not allowed | CORS rejected or invalid preflight |
| `CsrfFilter` | State-changing request missing CSRF token | Typically 403 |
| `UsernamePasswordAuthenticationFilter` | Username/password mismatch | Authentication failure handler, redirect or configured error |
| `BasicAuthenticationFilter` | Invalid Basic credentials | Entry point, usually 401/challenge per config |
| `BearerTokenAuthenticationFilter` | Invalid/expired Bearer token | Authentication entry point, usually 401 per protocol |
| `AuthorizationFilter` | Insufficient privileges or anonymous | `ExceptionTranslationFilter` + entry point/AccessDeniedHandler, 401 or 403 depending on case |

**Do not treat the status code as proof of which filter ran.** For example, 403 can come from CSRF rather than business authorization; 404 on login can happen because the login processing URL is not inside the chain; 401 can occur due to missing credentials or a rejected token.

When a custom filter handles exceptions, do not catch/swallow every `RuntimeException` and convert it into `BadCredentialsException`: infrastructure failures (DB down, JWK endpoint error) need distinct identification, fail-closed handling, and observability. At the same time, public responses must not disclose whether a username exists, token strings, secrets, stacktraces, or internal configuration.

## 12. Spring Security DEBUG/TRACE: Finding Which Filter Actually Ran

### 12.1. Viewing the Filter List at Startup

You can enable logging in dev/test environments:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Spring Security typically logs `DefaultSecurityFilterChain` details at startup, for example:

~~~text
Will secure any request with [
  SecurityContextHolderFilter,
  HeaderWriterFilter,
  CsrfFilter,
  UsernamePasswordAuthenticationFilter,
  BasicAuthenticationFilter,
  AnonymousAuthenticationFilter,
  ExceptionTranslationFilter,
  AuthorizationFilter
]
~~~

This is a **shortened example**, not a complete or fixed output. The real list depends on the DSL and version and may contain many other filters. Verify the **exact chain** by matcher rather than just counting filters.

When you need to see each filter invoked during tests, you can enable appropriate TRACE logging:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Or raise specific security log levels as needed. **Do not leave TRACE enabled indefinitely in production** if it logs extensive request/identity metadata, increasing overhead and risking sensitive data exposure. Use controlled, short-lived logging with restricted access.

### 12.2. Recommended Diagnostic Sequence

1. **What is the specific request?** Record method/path and correlation ID, stripping tokens/passwords.
2. **Has the Servlet container registered `DelegatingFilterProxy`?** In Boot, verify auto-registration and avoid adding it twice.
3. **Can the proxy find the Spring bean `springSecurityFilterChain`?** If missing, resolve context/bootstrap setup.
4. **Which chain does `FilterChainProxy` select?** Inspect `@Order`/matchers and debug logs.
5. **Is the authentication endpoint URL inside the chain?** Especially for form login and custom callbacks.
6. **Are the authentication filters created/enabled in the selected chain?** Do not expect a form login filter if the DSL did not enable it.
7. **Is the filter order correct?** Authentication must precede authorization and follow required context setup.
8. **Does the provider/decoder accept the credential?** Check UserDetailsService, PasswordEncoder, issuer/audience/JWK, and account status.
9. **Does the context have an Authentication?** Null, anonymous, or real; never dump tokens/passwords.
10. **Is the context saved properly if a session is needed?** Spring Security 6 often requires explicit save for custom flows.
11. **Which chain does the next request enter?** Session cookie/JWT, stateless policy, and path matchers may differ from login.
12. **Does any custom filter run twice?** Check bean auto-registration/`addFilterBefore`/`OncePerRequestFilter`.
13. **Does the controller run `@Async`?** ThreadLocal and context propagation need separate handling.

### 12.3. Troubleshooting Common Errors

| Symptom | Possible cause | Fix |
|---|---|---|
| Login endpoint returns 404 | `securityMatcher` excludes `/login` or login filter is not enabled | Put login path in the right chain, verify matcher |
| API expects JWT but shows form login | Fallback `/**` precedes the API chain | Give the API chain higher priority |
| Public endpoint still returns 401 | `requestMatchers` does not match or a different chain was selected | Debug matcher/method, distinguish chain vs. authorization |
| Endpoint lacks security headers | No chain matches / `ignoring` bypass used | Use fallback/`permitAll` and configure headers |
| Custom auth filter never runs | Added to wrong chain or wrong `securityMatcher` | Inspect chain/registration/order |
| Custom filter runs twice | Boot container auto-registration + Security DSL | Disable one registration via `FilterRegistrationBean` |
| Valid JWT still returns 403 | Token lacks authority, CSRF on write endpoint, or tenant policy | Check exception source, not just status code |
| Request has auth before login filter | Old session loaded or custom filter set it early | Check context load/flow, do not immediately assume bypass |
| Filter reading body breaks controller | `InputStream` was already consumed | Use a converter or proper request wrapper |
| Next request after custom login loses auth | Context set without saving/session cookie | Check repository/session strategy |
| Account A appears on request B | `ThreadLocal` not cleared or singleton auth state | Use standard filter lifecycle, clear context |
| Disabling CSRF "fixes" POST 403 | May open CSRF vulnerability if browser sends cookies/Basic auth | Analyze credential transport and threat model |
| A filter without `@Order` runs unexpectedly | Confusing Servlet Filter order with `SecurityFilterChain` order | Configure at the right layer, test actual chain |
| URL path differs behind reverse proxy | Inconsistent context/servlet path, encoded path, or rewrite | Align forwarding/firewall/matcher configuration |

## 13. Testing Across Three Layers

### 13.1. Unit Tests for Matchers and Custom Filters

- Matcher `/api/**` matches `/api/orders` and does not match `/home`.
- Chain `/api/admin/**` is evaluated before `/api/**`.
- Custom filter does not invoke the verifier when a request is outside its defined scope.
- Missing/invalid credentials never become an authenticated principal.
- Filter does not leak raw passwords/JWTs in logs or responses.
- Calls `chain.doFilter` per contract when allowed to proceed; intentionally stops on authentication failure.

### 13.2. Spring Security / MockMvc Integration Tests

| Request | Expectation |
|---|---|
| `GET /api/orders` missing credentials | API chain handles it, 401/entry point per policy |
| `GET /api/orders` valid Basic/JWT | Authenticates via the right mechanism, proceeds to authorization |
| `GET /home` unauthenticated | Website chain, redirects to login or proper entry point |
| `GET /assets/app.js` | Chain with `permitAll`, still receives security headers if configured |
| `POST /login` valid/invalid credentials | Correct login filter and handler, no 404 |
| `POST /api/orders` missing CSRF (if required by policy) | 403 from CSRF, not confused with `AuthorizationFilter` |
| `GET /api/admin/users` with regular-user token | Denied by authorization |
| URL matching no chain in a test config | Catches potential bypass risk before production deployment |
| Custom token filter declared as a Boot bean | Does not run twice once added to the security chain |
| Logout or subsequent session request | Context persistence/invalidation follows policy |
| `ASYNC` and `ERROR` dispatches | No double-auth or context leakage |
| Encoded/unusual path URL requests | `HttpFirewall`/matchers behave consistently, no bypass |
| Multiple servlets or context-path | Matcher checks `servletPath`/`pathInfo` accurately |

`MockMvc` helps test security chains, but it does not fully simulate production firewalls, reverse proxies, or servlet container sessions. For areas sensitive to proxy rewrites or HTTP parsing, run integration tests against a real container.

### 13.3. E2E and Security Regression

- Run the system behind a load balancer/reverse proxy as in production, verifying Authorization/headers/cookies are not improperly altered by the proxy.
- Probe endpoints with variations in slashes, encoded URLs, HTTP methods, and context paths according to your threat model.
- Rate-limit login and API key verification to prevent brute-force/DoS; `PasswordEncoder` cost must not be set arbitrarily.
- Test concurrent logins across multiple users to detect context/thread-reuse leaks.
- Test rollouts combining website sessions and stateless APIs: chain order must not break when adding new filters.
- Verify that logout, account locking, and role changes take effect as required by security policies.
- Maintain the list of chains and matchers in tests as a **contract**: adding a new endpoint or namespace must require an explicit security decision.

## 14. Core Misconceptions

**1. "DelegatingFilterProxy authenticates passwords."**  
False. It bridges the Servlet container to a Spring bean. Authentication filters/providers handle credentials.

**2. "There is one SecurityFilterChain per request and Spring runs every matching chain."**  
False. `FilterChainProxy` selects **the first matching chain**; it does not merge filter lists.

**3. "securityMatcher and requestMatchers are the same thing."**  
False. `securityMatcher` defines the scope of the entire chain; `requestMatchers` inside the authorize DSL defines permission rules within that chain.

**4. "@Order determines the order of authentication filters relative to authorization."**  
False. `@Order` on `SecurityFilterChain` determines priority between chains, whereas internal filter order is governed by the Security DSL/`addFilter...`.

**5. "A filter running proves the user is logged in."**  
False. A filter may inspect an unauthenticated request, create an anonymous context, or return 401. Only an `Authentication` verified across a trust boundary is trustworthy.

**6. "Enabling STATELESS means there is no SecurityContext."**  
False. A stateless request can still populate `SecurityContext` from a Basic/Bearer token on every request.

**7. "permitAll and ignoring are equivalent."**  
False. `permitAll` still runs the chain's security filters; ignoring/excluding matchers can bypass filters altogether.

**8. "Creating a @Component Filter and calling addFilterBefore is always safe."**  
False. Spring Boot may auto-register it in the container and then run it again inside Spring Security, causing double invocation.

**9. "Invalid Basic credentials will always return 403."**  
False. Failures normally go through an entry point/challenge (typically 401); 403 can come from CSRF or authorization.

**10. "You can construct an authenticated Authentication from a username/roles in the request."**  
False. That is an authentication bypass. A provider/verifier must validate the credential/token.

**11. "More filters means better security."**  
False. Misordered filters, unmatched URLs, or double registration can cause bugs/side effects and widen the attack surface.

**12. "Setting SecurityContextHolder in custom login is enough to stay logged in tomorrow."**  
False. You need `SecurityContextRepository`/session persistence or per-request stateless authentication, depending on policy.

## 15. Pre-Production Checklist

- [ ] Verify a single properly configured `DelegatingFilterProxy`/`springSecurityFilterChain` entry point; no duplicate registration in Boot.
- [ ] Distinguish the roles of Servlet `FilterChain`, `FilterChainProxy`, and `SecurityFilterChain`.
- [ ] Document `@Order` and the matcher of each chain; narrower chains before broad fallbacks.
- [ ] Verify every critical endpoint matches a chain with appropriate protection.
- [ ] Distinguish `securityMatcher` from authorization `requestMatchers(...).permitAll/hasRole...`.
- [ ] Know exactly which authentication filter reads which credential type: form, Basic, Bearer, OIDC, custom.
- [ ] Never turn a raw username/token directly into an authenticated principal; use `AuthenticationManager`/providers/decoders.
- [ ] Verify auth filters run before authorization and after required context/protection setup.
- [ ] When adding a custom filter, position it intentionally with `addFilterBefore/After/At` and test actual order.
- [ ] Prevent custom `Filter` beans from being registered twice in both the container and the Spring Security chain.
- [ ] Use `OncePerRequestFilter` only for appropriate dispatch scoping; do not treat it as a substitute for chain configuration.
- [ ] Keep `HttpFirewall`, URL normalization, reverse proxy, and path matching consistent.
- [ ] Maintain CSRF/CORS/headers per your threat model; do not disable them globally just because of a 403 error.
- [ ] If using session login, ensure authentication is saved/restored properly in Spring Security 6 and the login endpoint is in the chain.
- [ ] If stateless, require credentials to be verified on every request; do not rely on a persisted session holder.
- [ ] Never leak credentials, JWTs, user secrets, session cookies, or full `Authentication`/claims in logs.
- [ ] Debug with Spring Security logs and real-route integration tests; restrict TRACE in production.
- [ ] Test empty/missing chains, first-match behavior, form + API chains, custom filter invocation count, anonymous access, error/async dispatches, and logout.
- [ ] After filter chain updates, re-run security regression tests and measure latency/login errors.

**Remember:** `DelegatingFilterProxy` **brings Spring Security into the Servlet container**; `FilterChainProxy` **selects the single first matching `SecurityFilterChain`**; **the authentication filter inside the selected chain** reads credentials and delegates them to a trusted verifier/provider; other filters load context, protect requests, translate exceptions, and enforce authorization. Understanding the right layer, position, and order prevents both login bugs and bypass vulnerabilities.

### Official Documentation

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, matchers, firewall, and adding filters.
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `@Order`, multiple `SecurityFilterChain` beans, and `securityMatcher` vs. `requestMatchers`.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, `SecurityContextHolder`, `AuthenticationManager`, and providers.
- [Spring Security — Username and Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): form login, HTTP Basic, and `DaoAuthenticationProvider`.
- [Spring Security — Authentication Persistence / Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit save, and session state.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer authentication and token verification.
- [Spring Boot — Disable Servlet Filter Registration](https://docs.spring.io/spring-boot/how-to/webserver.html): `FilterRegistrationBean` and preventing filter beans from auto-registering.
- [Spring Security — FilterChainProxy JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html): first-matching `SecurityFilterChain`, `HttpFirewall`, and lifecycle.
