# Distinguishing Multiple AuthenticationProviders in One AuthenticationManager vs. Multiple SecurityFilterChains

> **Core takeaway:** **Multiple AuthenticationProviders in one AuthenticationManager** answer the question **“How is this login credential verified?”**. **Multiple SecurityFilterChains** answer the question **“Which set of filters and security policies must this HTTP request pass through?”**. The two mechanisms operate at **two different layers** and can be used independently or combined in the same Spring Security application.

## 1. The Big Picture

In a **Spring Security Servlet** application, a request passes through **FilterChainProxy** before reaching Spring MVC. The proxy inspects the list of **SecurityFilterChain** beans in priority order and selects the **first chain** that matches the request. Inside the chain, the appropriate authentication filter (for example, **BasicAuthenticationFilter**, **UsernamePasswordAuthenticationFilter**, or a custom filter) constructs an unauthenticated **Authentication** object and delegates to **AuthenticationManager**. If the manager is a **ProviderManager**, it asks the matching **AuthenticationProvider** instances to verify the credentials.

~~~text
HTTP request: GET /api/me, Authorization: Basic ...
                 |
                 v
     DelegatingFilterProxy
                 |
                 v
       FilterChainProxy
                 |
          inspects chains
          in @Order sequence
                 |
                 +-- SecurityFilterChain #1: /api/**  <-- matches first
                 |      |
                 |      +-- SecurityContext / CSRF / ... / BasicAuthenticationFilter
                 |                                         |
                 |                              creates Authentication
                 |                                         |
                 |                                         v
                 |                                 AuthenticationManager
                 |                                         |
                 |                                  ProviderManager
                 |                                    /        \
                 |                        PasswordProvider   ApiKeyProvider
                 |                       (user/pass token)  (API key token)
                 |                                    \        /
                 |                              authentication result
                 |                                         |
                 |                               AuthorizationFilter
                 |                                         |
                 |                                         v
                 |                                  MVC controller
                 |
                 +-- SecurityFilterChain #2: fallback (does not run for this request)
~~~

**Decisions happen in two different places:**

- **FilterChainProxy** matches the **HttpServletRequest** via each chain's **RequestMatcher**. That selects the *set of filters*.
- **ProviderManager** receives the **Authentication object** created by a filter and asks which provider can verify that *credential type*. That selects *where credentials are verified*.
- **AuthorizationFilter** (or the configured authorization mechanism) checks what the authenticated principal is allowed to do. Selecting the right chain or authenticating successfully does not mean having sufficient permissions.

Do not lump both together as “choosing a login method” and mix up **@Order**, **supports(...)**, **securityMatcher(...)**, and **requestMatchers(...)**.

## 2. Exact Comparison Table

| Aspect | Multiple AuthenticationProviders in one manager | Multiple SecurityFilterChains |
| --- | --- | --- |
| Coordinating component | **ProviderManager** (an AuthenticationManager implementation) | **FilterChainProxy** |
| Data used for selection | **Authentication**: token class, credentials, and provider logic | **HttpServletRequest**: path, method, header, or RequestMatcher condition |
| Extension points | **AuthenticationProvider.authenticate(...)** and **supports(...)** | **SecurityFilterChain** bean, **HttpSecurity**, **securityMatcher(...)**, **@Order** |
| Primary question | “Who/what verifies these credentials?” | “Which filter chain, login flow, session, CSRF, and authorization rules apply to this request?” |
| Ordering | List of providers iterated by ProviderManager; results/exceptions affect whether subsequent providers are tried | Ordered list of chains; the **first matching chain** is selected |
| If nothing matches | May throw **ProviderNotFoundException** if no provider authenticates and no suitable parent exists | If **no chain matches**, the request is **not protected by Spring Security** |
| Can multiple results be applied? | One authenticate call may consult multiple providers but ultimately returns **one successful Authentication** or fails | A request is handled by **one** SecurityFilterChain in FilterChainProxy, without merging filters from remaining chains |
| Where permission rules live | Providers return **GrantedAuthority** from a trusted source | Chains configure **authorizeHttpRequests**, though method security may also be used alongside |
| Examples | Username/password + API key with distinct token types; password + OTP provider | **/api/** uses Basic/stateless; web pages use form login/session |
| Common design mistake | A weaker provider accepts credentials that an earlier provider rejected | A high-priority catch-all chain shadows a specific chain, or no catch-all exists |

**One AuthenticationManager is not equivalent to one SecurityFilterChain.** One chain can have a manager with multiple providers; multiple chains can share a manager or use separate managers. The relationship is not one-to-one by default.

## 3. How Multiple Providers Work Inside One Manager

### 3.1. The ProviderManager Contract

Core interface:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

With **ProviderManager**, the conceptual processing order is:

1. Receive an unverified **Authentication**.
2. Iterate over the configured **AuthenticationProvider** instances.
3. For a provider where **supports(authentication.getClass())** indicates it can handle the token type, call **authenticate(authentication)**.
4. If the provider returns a **valid Authentication**, return the successful result. A provider that cannot handle it may return **null** so the manager tries the next one.
5. If a provider throws an error, the manager handles it according to the **AuthenticationException** type and its fallback behavior; for some errors, iteration may stop early. **Do not assume every error stops immediately or every error falls through to the next provider.**
6. If no provider authenticates, the manager may consult a configured **parent AuthenticationManager**; ultimately authentication fails, potentially with **ProviderNotFoundException** when no supporting provider is found.

**supports(...) is not a URL filter.** A provider that supports **UsernamePasswordAuthenticationToken** does not inherently know whether the request came from **/api/** or **/web/**. If you want to restrict by context, choose the right filter/manager/token and evaluate the trust boundary; do not rely on endpoint names pulled arbitrarily from Authentication.details.

Most login filters create a specific Authentication object:

| Filter/mechanism | Input typically created | Suitable provider |
| --- | --- | --- |
| **HTTP Basic** | **UsernamePasswordAuthenticationToken** | Usually **DaoAuthenticationProvider** or a username/password-compatible provider |
| **Form login** | **UsernamePasswordAuthenticationToken** | Also usually the same **DaoAuthenticationProvider** |
| **Custom API key filter** | Application-defined **ApiKeyAuthenticationToken** | Custom provider supporting this token type |
| **OAuth2 Resource Server JWT** | Specialized token created by the bearer/JWT mechanism | JWT verification component following Spring Security's architecture |
| **Pre-authenticated identity** | Pre-auth token created by a specific filter | Provider for pre-auth contexts, trusting identity only from a verified upstream component |

**Key observation:** Enabling both **httpBasic()** and **formLogin()** does not necessarily require two providers, because both default filters use the username/password token and can usually call the same **DaoAuthenticationProvider**. Conversely, registering an **ApiKeyProvider** in the manager **does not automatically authenticate HTTP requests carrying X-API-Key**: there must be a filter or trusted endpoint that creates an **ApiKeyAuthenticationToken** and passes it to the manager.

### 3.2. Java 17 Example: One ProviderManager with Two Credential Types

The example below is a **standalone program inside a Spring Boot 3.x project** with the **Spring Security** dependency. It does not create HTTP endpoints; its purpose is to show **the same manager** handling two different Authentication types. Create a Maven project via Spring Initializr (Java 17+, **Spring Security** dependency), place **src/main/java/com/example/demo/ProviderManagerDemo.java** under the corresponding package, and use this class as the sole main class of the demo project.

~~~java
package com.example.demo;

import java.util.Collection;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootApplication
public class ProviderManagerDemo implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(ProviderManagerDemo.class, args);
    }

    @Override
    public void run(String... args) {
        var manager = new ProviderManager(List.of(
                new PasswordProvider(),
                new ApiKeyProvider()));

        Authentication person = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo-pass"));

        Authentication job = manager.authenticate(
                ApiKeyToken.request("example-key"));

        System.out.println("password: " + person.getName()
                + " | " + person.getAuthorities().iterator().next()
                        .getAuthority());
        System.out.println("api-key: " + job.getName()
                + " | " + job.getAuthorities().iterator().next()
                        .getAuthority());

        try {
            manager.authenticate(ApiKeyToken.request("wrong"));
        } catch (BadCredentialsException ex) {
            System.out.println("invalid key: rejected");
        }
    }

    static final class PasswordProvider implements AuthenticationProvider {
        @Override
        public Authentication authenticate(Authentication input)
                throws AuthenticationException {
            if (!supports(input.getClass())) {
                return null;
            }
            boolean valid = "alice".equals(input.getName())
                    && "demo-pass".equals(input.getCredentials());
            if (!valid) {
                throw new BadCredentialsException("Invalid credentials");
            }
            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
        }
    }

    static final class ApiKeyProvider implements AuthenticationProvider {
        @Override
        public Authentication authenticate(Authentication input)
                throws AuthenticationException {
            if (!supports(input.getClass())) {
                return null;
            }
            if (!"example-key".equals(input.getCredentials())) {
                throw new BadCredentialsException("Invalid API key");
            }
            return ApiKeyToken.verified("nightly-job");
        }

        @Override
        public boolean supports(Class<?> type) {
            return ApiKeyToken.class.isAssignableFrom(type);
        }
    }

    static final class ApiKeyToken extends AbstractAuthenticationToken {
        private final String principal;
        private String credentials;

        private ApiKeyToken(
                String principal,
                String credentials,
                Collection<? extends GrantedAuthority> authorities,
                boolean verified) {
            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(verified);
        }

        static ApiKeyToken request(String apiKey) {
            return new ApiKeyToken(null, apiKey, List.of(), false);
        }

        static ApiKeyToken verified(String subject) {
            return new ApiKeyToken(subject, null,
                    List.of(new SimpleGrantedAuthority("SCOPE_read")),
                    true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return credentials;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            credentials = null;
        }
    }
}
~~~

Run inside the newly created project directory:

~~~bash
./mvnw spring-boot:run
~~~

PowerShell on Windows uses **.\mvnw.cmd spring-boot:run**. Alongside the Spring Boot log lines, the three lines printed by the program will be:

~~~text
password: alice | ROLE_USER
api-key: nightly-job | SCOPE_read
invalid key: rejected
~~~

**Analysis:** The first request token is an instance of **UsernamePasswordAuthenticationToken**, so **PasswordProvider** supports it. The second request token is an instance of **ApiKeyToken**, so **ApiKeyProvider** supports it. A single **ProviderManager** verified both credential types; there is no need to create two SecurityFilterChains to demonstrate this.

**Scope boundaries of the example:** the password and API key are hard-coded **only to study the dispatch flow**. Never deploy this kind of comparison to production. For real passwords, use **UserDetailsService** and **PasswordEncoder.matches** against a stored hash; for API keys, use a server-controlled key store, manage scopes, expiration, and revocation, avoid logging credentials, and compare securely by design. The **ApiKeyToken.verified(...)** factory is internal and may only be called by the provider after verification; never let the client construct an authenticated token itself. In a real app, the filter must construct an unauthenticated request token from the header and never accept roles from the client.

**Additional note:** the demo uses a manager constructed directly inside **CommandLineRunner**. It is a **ProviderManager** API exercise; it does not yet integrate that manager into an HTTP filter chain. When integrating into a web app, configure the corresponding **AuthenticationManager** on the chain and add a filter to read the API key if you want to authenticate an API key header.

## 4. How Multiple SecurityFilterChains Work

### 4.1. FilterChainProxy Selects a Chain Per Request

In a Servlet environment, Spring Security uses **FilterChainProxy** to manage **SecurityFilterChain** beans. Each chain has a **RequestMatcher**; **securityMatcher(...)** restricts the set of requests the chain handles. **@Order** determines the order in which chains are evaluated: a chain with higher priority is evaluated first. Once a chain matches, **only that chain runs**, even if other chains could also match.

Example:

~~~text
@Order(1): SecurityFilterChain A, securityMatcher("/api/admin/**")
@Order(2): SecurityFilterChain B, securityMatcher("/api/**")
No @Order: SecurityFilterChain C, matches all requests by default

GET /api/admin/users -> A
GET /api/items       -> B
GET /login           -> C
GET /favicon.ico     -> C
~~~

Swapping the order of A and B can cause **/api/admin/users** to be matched by B first. The stricter policy placed on A will not be applied to that request. **@Order only orders chains**; it does not select an AuthenticationProvider.

If all three chains have restrictive **securityMatcher** rules and none matches **/unlisted**, Spring Security applies no security filter chain to that request. Therefore, multi-chain applications usually include **one final chain without a securityMatcher**, with an explicit policy for everything else.

### 4.2. securityMatcher vs. requestMatchers

The two APIs look similar but serve two different purposes:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

- **securityMatcher("/api/**")**: this chain is selected only for requests under **/api/**. It scopes the entire chain.
- **requestMatchers("/api/admin/**").hasRole("ADMIN")**: an authorization rule **inside the already-selected chain**; it does not create a new chain.
- **anyRequest().authenticated()**: every remaining request **within the current chain**, not “every request in the application” if the chain is scoped by securityMatcher.

A dangerous mistake is configuring **requestMatchers("/admin/**")** in a chain whose **securityMatcher("/api/**")** never matches **/admin/**. That rule never runs for **/admin/**. To protect other URLs, the chain's matcher must cover those URLs or another suitable chain must handle them.

### 4.3. Spring Boot 3.x Example: Two Chains for API and Web

This is a **separate demo project** from the **ProviderManagerDemo** example in section 3. Create a Spring Boot 3.x/Java 17+ project with **Spring Web** and **Spring Security**, keep the **DemoApplication** class generated by Spring Initializr, and place the two classes below under package **com.example.demo**. The example uses one account from **UserDetailsService** so both HTTP Basic and form login can sign in, while two **SecurityFilterChain** beans apply **different request and session mechanisms**.

File **src/main/java/com/example/demo/MultiChainSecurityConfig.java**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .requestCache(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**The two chains have different responsibilities:**

- **apiChain** has **@Order(1)**, matches only **/api/**, uses **HTTP Basic**, disables form login, and chooses **SessionCreationPolicy.STATELESS** so sessions are not used to store Authentication for the API. The example only tests GET requests.
- **webChain** has no **securityMatcher**, so it acts as the default chain evaluated afterwards; it uses **formLogin**, sessions for browser UX, and does not enable BasicAuthenticationFilter. It also covers **/login** so Spring Security's default login page works.
- Both reference the same username/password verification logic via UserDetailsService and PasswordEncoder. **This does not prove the two chains are sharing the same AuthenticationManager object.** Spring may configure separate managers per HttpSecurity or share authentication components. If you need the exact same **instance**, inject and attach **http.authenticationManager(sharedManager)** explicitly.
- The example **does not disable CSRF**. CSRF still needs evaluation whenever the client is a browser, including HTTP Basic if the browser sends credentials automatically. The demo only sends GET requests; for POST/PUT/DELETE, you must choose a CSRF policy matching the access model, not disable it just to bypass a 403 error.

File **src/main/java/com/example/demo/IdentityController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api " + authentication.getName();
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web " + authentication.getName();
    }
}
~~~

In **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Run on Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

On Windows PowerShell, set **$env:DEMO_USER_PASSWORD = "demo-pass"**, then run **.\mvnw.cmd spring-boot:run**. The demo password is for localhost only; never store real secrets in a repository. In production environments, use HTTPS and configure secure cookies.

Test requests:

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/me
curl -i http://localhost:8080/web/me
curl -i http://localhost:8080/login
curl -i http://localhost:8080/public
~~~

Expected results:

| Request | Selected chain | Expected result |
| --- | --- | --- |
| **GET /api/me**, no credentials | **apiChain** | **401 Unauthorized**, possibly with **WWW-Authenticate: Basic** |
| **GET /api/me**, valid Basic | **apiChain** | **200 OK**, body **api alice** |
| **GET /web/me**, no session | **webChain** | **302** redirect to the **/login** page |
| **GET /login** | **webChain** | **200 OK**, HTML login form provided by Spring Security |
| **GET /public** | **webChain** | **200 OK**, body **public** |

If you send **Authorization: Basic ...** to **/web/me** from a fresh client without a session, do not expect the Basic filter to run automatically: **webChain** disabled HTTP Basic. That request still normally redirects to the HTML login page. Each chain has its **own set of filters**, so the same HTTP header can lead to different behavior across URL areas.

**Note on filter-provided endpoints:** If you restrict **webChain** with **securityMatcher("/web/**")**, the default **GET /login** page and **POST /login** handler fall outside that matcher. They may be handled by another chain or return 404. When using narrowly scoped chains, move **loginPage**, **loginProcessingUrl**, **logoutUrl**, and related paths into the chain's scope or keep a fallback chain covering them.

## 5. Can Both Be Combined in One Application?

**Yes, and this is the most commonly misunderstood part.** For example, consider a system serving:

- **/api/**: machine-to-machine clients using API keys or bearer tokens.
- **/web/**: users logging in via a username/password form.
- **/internal/**: employees connecting over a differently authenticated link.

You can use **multiple SecurityFilterChains** to separate request areas and policies; each chain can have its own **AuthenticationManager** or share a single manager with multiple providers. One valid architecture:

~~~text
FilterChainProxy
  |
  +-- chain #1: /api/** (stateless, accepts API key)
  |       |
  |       +--> ApiKeyFilter --> AuthenticationManager A
  |                              +--> ApiKeyProvider
  |                              +--> JWT Provider (if present)
  |
  +-- chain #2: /web/** (session + form login)
  |       |
  |       +--> UsernamePasswordAuthenticationFilter
  |                                  |
  |                                  v
  |                           AuthenticationManager B
  |                                  +--> DaoAuthenticationProvider
  |
  +-- chain #3: fallback (deny/explicit policy)
~~~

Another valid structure: two different chains **sharing** one manager configured with **DaoAuthenticationProvider** and **ApiKeyProvider**. However, there must be filters creating the right **Authentication token type** for each credential.

### 5.1. Shared Manager Configuration, Wiring Skeleton

The snippet below **only illustrates wiring** and cannot compile standalone because the provider beans and API key filter are not declared. It shows **the connection points**; it is not a substitute for real HTTP filter configuration:

~~~java
// Illustrative snippet in @Configuration; define
// passwordProvider, apiKeyProvider, and apiKeyFilter in a real project.
@Bean
AuthenticationManager sharedManager(
        AuthenticationProvider passwordProvider,
        ApiKeyAuthenticationProvider apiKeyProvider) {
    return new ProviderManager(List.of(
            passwordProvider,
            apiKeyProvider));
}

@Bean
@Order(1)
SecurityFilterChain apiChain(
        HttpSecurity http,
        AuthenticationManager sharedManager) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authenticationManager(sharedManager)
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            // Add ApiKeyFilter at the appropriate filter position
            // to convert the API key header into an ApiKeyAuthenticationToken.
            .build();
}

@Bean
SecurityFilterChain webChain(
        HttpSecurity http,
        AuthenticationManager sharedManager) throws Exception {
    return http
            .authenticationManager(sharedManager)
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

When **ApiKeyFilter** is not registered, requests carrying only **X-API-Key** do not automatically reach the manager, even though ApiKeyProvider exists. When sharing a manager, providers must verify the right token type and trusted data source; do not allow a provider to be invoked in the wrong context and leak permissions from another area.

If you choose multiple managers, you can configure a specific **AuthenticationManager** for each chain. In some cases, child managers use a common **parent AuthenticationManager**. That is an **architecture and trust boundary** choice; it is not an implicit behavior guaranteed by creating two SecurityFilterChain beans.

### 5.2. When to Choose Which Approach?

| Requirement | Typically suitable solution | Why |
| --- | --- | --- |
| Same endpoint allows multiple credential types | **One chain + appropriate filters + multi-provider manager**, if request policies match | Decision is based on credentials after the request enters the chain |
| Same username/password, but API URLs return 401 while web UI redirects to login | **Multiple chains**, optionally sharing UserDetailsService/provider | The difference lies in entry point, session, filters, and response, not password checking |
| API key for /api and form session for /web, different CSRF/policies | **Multiple chains**, each configuring appropriate filters/manager | Differences in both request scope and authentication mechanism |
| Support two different internal password sources | **ProviderManager with specialized providers** or a unified authentication service | Need to clearly define user context and fallback order; avoid trying a weak source after a strong one |
| Stricter authorization on /admin than /user, same login mechanism | Possibly just **requestMatchers** in one chain; multiple chains if filters/policies differ significantly | Avoid creating a new chain when only an authorization rule differs |
| Need both form login and Basic in the same URL area | One chain with **formLogin + httpBasic**, usually sharing the username/password provider | Two different authentication filters can share the same token type |
| One path accepts both JWT and API key | One chain with filters/tokens for each mechanism and corresponding manager/providers, or split chains via matcher if genuinely partitionable | **Multiple chains do not stack**, a request enters only the first matching chain |

### 5.3. Why You Should Not Use Multiple Chains Just to “Try the Next Provider”

Suppose **/api/orders** matches both SecurityFilterChain A and B. If A uses Basic but has no valid credentials, **FilterChainProxy does not pass the request on to B** to try a login token. It already chose A as soon as A's matcher matched; authentication failures inside A are handled according to chain A. Trying multiple providers belongs to **ProviderManager inside a chain**, not FilterChainProxy.

Conversely, if a manager supports both **PasswordProvider** and **ApiKeyProvider** but the chain only has **BasicAuthenticationFilter**, a request containing **X-API-Key** is not turned into an ApiKeyToken. Simply adding a provider does not replace registering a filter.

This is why the two layers must be designed and tested separately.

## 6. Ordering and Fallback: Two Easily Overlooked Error Sources

### 6.1. Chain Shadowed by @Order

**Dangerous example:**

~~~java
@Bean
@Order(1)
SecurityFilterChain all(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain admin(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(a -> a.anyRequest().hasRole("ADMIN"))
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

In this **bug-illustration** example, the **all** chain has no securityMatcher, so it matches every request right at priority **1**. Requests to **/api/admin/users** never reach the **admin** chain. The fix is to put the specific **/api/admin/** chain first and the catch-all chain last, or design the authorization rules in the proper order within one chain.

**Do not read the two beans as two stacked layers of defense.** They are two mutually exclusive choices at the FilterChainProxy layer.

### 6.2. A Later Provider Accidentally Accepts Credentials Rejected by an Earlier One

If a manager registers two providers that both **supports(UsernamePasswordAuthenticationToken.class)**, examine closely:

1. Do both providers accept username/password? If so, how is the authentication source differentiated?
2. When one provider throws **BadCredentialsException**, the manager may continue trying another provider depending on exception type and configuration. Is that the intended policy, or does it open a weak fallback path?
3. Does the later provider verify credentials independently, with a trusted source and account state checks?
4. If there is a **parent AuthenticationManager**, could it create an unintended acceptance path?
5. If a user with the same username exists in both sources, could the returned **authorities** become ambiguous or escalate privileges?

**Solution:** use distinct token types for distinct credential formats; when user domains must be separated, route explicitly and enforce a consistent acceptance policy. Test every provider-fallback branch, especially when a source is down or credentials are wrong. Do not use **return null** to ignore credentials known to be invalid just to let “another provider try”.

### 6.3. If No Chain Matches, Does Spring Security Block It?

**Not automatically.** Per the documentation, a request matching no SecurityFilterChain is not protected by Spring Security. If all chains have narrow matchers, inspect endpoints like **/actuator/**, **/error**, **/login**, **/favicon.ico**, new routes, other HTTP methods, and internal paths.

A **fallback SecurityFilterChain** with **anyRequest().denyAll()** is usually a conservative choice for APIs with explicitly defined endpoints; mixed applications can use a fallback listing public routes and **anyRequest().authenticated()**. Avoid using a broad **permitAll()** fallback without understanding the consequences.

## 7. Session, CSRF, Entry Points, and Per-Chain Scope

When using multiple chains, each chain can have different settings:

| Component | Sample stateless API | Sample session-based Web |
| --- | --- | --- |
| How credentials arrive | HTTP Basic, Bearer/JWT, or custom filter | Form login |
| SecurityContext | Does not use session to retrieve Authentication if truly stateless | Loads/saves SecurityContext via session as configured |
| Unauthenticated response | Usually **401** (JSON/WWW-Authenticate) | Usually **302** to login page |
| CSRF | Evaluate per credential mechanism; bearer in a JS-attached header without auto-attached cookies can be exempt by design | Usually requires CSRF token because browsers send cookies automatically |
| Logout | For bearer tokens: typically revoke token/credential per model; not session logout by default | Session invalidation, cookies, and CSRF must be handled |
| Request cache/redirect | Usually does not save requests | May save the request to redirect back after login |
| Authorization | API scopes/roles | Web user roles/permissions |

Do not copy **csrf(AbstractHttpConfigurer::disable)** from a cookie-free bearer-token API onto a form-login chain. And **SessionCreationPolicy.STATELESS** does not automatically turn an endpoint into a secure API; it only sets the session policy, while authentication and authorization still must be configured.

TLS is also independent of chain/provider choices: whether logging in via Basic, form, or API key, sensitive credentials still require **HTTPS** and certificate verification. If the API sits behind a reverse proxy, verify trusted forwarding headers and TLS termination points.

## 8. Testing to Distinguish the Two Layers

### 8.1. Build a Request → Chain Matrix

Based on **MultiChainSecurityConfig** in section 4:

| Test | Request | Expected chain | Result |
| --- | --- | --- | --- |
| API without Basic | GET /api/me | apiChain | 401 |
| API with valid Basic | GET /api/me + Basic | apiChain | 200, body **api alice** |
| Web unauthenticated | GET /web/me | webChain | Redirect to login |
| Login page | GET /login | webChain | 200 HTML |
| Public | GET /public | webChain | 200 |
| Web sends Basic without session | GET /web/me + Basic | webChain | Still no form-login, usually redirects |
| Admin shadowed by higher-order catch-all | GET /api/admin/x in section 6's broken config | catch-all chain | ADMIN rule in later chain does not run |

You must verify which chain was actually selected, not just the status code. Two chains might happen to both return 401; checking only status would miss a matching bug.

### 8.2. Testing with MockMvc

For the project in section 4, add the test dependency **spring-boot-starter-test** (and **spring-security-test** if you want mock SecurityContext or CSRF utilities). Create **src/test/java/com/example/demo/MultiChainSecurityTest.java**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.user.password=demo-pass")
@AutoConfigureMockMvc
class MultiChainSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiNeedsCredentials() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAcceptsCorrectBasicCredentials() throws Exception {
        String encoded = Base64.getEncoder().encodeToString(
                "alice:demo-pass".getBytes(StandardCharsets.UTF_8));

        mvc.perform(get("/api/me")
                .header("Authorization", "Basic " + encoded))
                .andExpect(status().isOk())
                .andExpect(content().string("api alice"));
    }

    @Test
    void webRedirectsWithoutFormSession() throws Exception {
        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void webDoesNotTreatBasicHeaderAsFormLogin() throws Exception {
        String encoded = Base64.getEncoder().encodeToString(
                "alice:demo-pass".getBytes(StandardCharsets.UTF_8));

        mvc.perform(get("/web/me")
                .header("Authorization", "Basic " + encoded))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicRouteIsAccessible() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

In PowerShell: **.\mvnw.cmd test**. These tests verify the observable behavior of the two chains. To test **ProviderManager**, add tests supplying both Authentication token types as in section 3, verifying **supports(...)**, valid/invalid credentials, unavailable sources, and accurate authorities. If you have a custom API key filter, test that the header is converted to **ApiKeyToken** and the provider is invoked.

### 8.3. Observing at Runtime

In development, you can temporarily enable Spring Security logging to see which chain/filters protect a request:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

TRACE logging can generate a large volume of events or sensitive metadata; enable it only sparingly on a development machine, and never copy logs containing Authorization/credentials to public places. You can set breakpoints in **FilterChainProxy** to observe the selected chain, **BasicAuthenticationFilter** or a custom filter to observe the created Authentication, and **ProviderManager** to see which provider is called.

**Do not infer the actual number of managers from bean names.** To know whether managers are shared or separate, inspect the bean configuration, the built filter chain structure, and runtime behavior.

## 9. Self-Check Questions

**Question 1:** There are two AuthenticationProviders (password and API key) in one manager. Does a request sending **X-API-Key** log in automatically?

**No.** ProviderManager only receives an **Authentication** sent by a filter or endpoint. A filter is needed to convert the header into the right token type and call the manager. Simply registering a provider does not add a header-reading filter.

**Question 2:** Two chains both match **/api/orders**; the first uses Basic and authentication fails. Does Spring automatically try the next chain using JWT?

**No.** **FilterChainProxy** picks the first matching chain and does not fall back to another chain on authentication failure. If you need to support both Basic and JWT on the same endpoint, design them inside the same chain or split matchers so they are genuinely distinct.

**Question 3:** If Basic and form login both use username/password, do we need two providers?

**Not necessarily.** Both filters can create a **UsernamePasswordAuthenticationToken**, and a single DaoAuthenticationProvider can verify credentials for both. Separate chains are still useful if HTTP responses, sessions, and protection policies differ.

**Question 4:** Are **securityMatcher("/api/**")** and **requestMatchers("/api/admin/**").hasRole("ADMIN")** the same?

**No.** The first selects the chain's scope; the second sets an authorization rule inside the already-selected chain.

**Question 5:** If there is no fallback chain and a request matches no chain, what happens?

That request is not protected by Spring Security, even though a controller or another component might have its own checks. Therefore, you must verify the coverage of all chains.

**Question 6:** Can an AuthenticationManager be shared across multiple chains?

**Yes.** When intentionally sharing, configure the manager and inject it into each **HttpSecurity**. However, two independent chains do not implicitly prove they share the same instance; check the actual wiring.

**Question 7:** A manager has two providers that both support username/password, and the first provider throws BadCredentialsException. Can we be sure the second provider will not be called?

**No.** Exception handling and fallback depend on **ProviderManager**, the exception type, and configuration. Design compatible providers under the same policy and write tests preventing weaker authentication paths.

## 10. Design Checklist

- [ ] Document **which request → which SecurityFilterChain**, including login, logout, error, actuator, and new routes.
- [ ] Place specific chains before general ones, with accurate **@Order** and **securityMatcher**.
- [ ] Include an explicit fallback chain; never leave unintended paths outside Spring Security.
- [ ] For each chain, list the filters that actually accept Basic, form, bearer, API key, or other credentials.
- [ ] For each filter, identify the **Authentication token type** it creates and the **AuthenticationManager** it calls.
- [ ] For each manager, list its **AuthenticationProvider**s; verify **supports**, ordering, parent manager, and failure branches.
- [ ] Never accept tokens marked authenticated, roles, or principals self-asserted by the client without verification.
- [ ] Obtain authorities from a trusted source; enforce authorization in the right chain scope and method security if used.
- [ ] Explicitly design session, CSRF, entry point, error response, login/logout paths, TLS, and rate limiting per area.
- [ ] Test 401/403/302/200 as well as which chain/filter/provider actually runs; test matcher intersections.
- [ ] Do not reflexively disable CSRF or open a broad permitAll just to work around matching errors.

## 11. Official Documentation

- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): ProviderManager, AuthenticationProvider, parent manager, and SecurityContext.
- [Spring Security 6.5 — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): multiple SecurityFilterChains, **@Order**, **securityMatcher** vs. **requestMatchers**, and filter-provided login endpoints.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, first-match chain selection, and filter ordering.
- [AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/AuthenticationProvider.html): **supports** and **authenticate** contracts.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): verifying credentials and protecting accounts when using multiple authentication mechanisms.
