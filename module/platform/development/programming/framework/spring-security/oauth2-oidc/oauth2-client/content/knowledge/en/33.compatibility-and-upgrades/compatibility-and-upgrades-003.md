# 33.3. Migrating Legacy Adapter Configuration to SecurityFilterChain

## 1. The Upgrade Problem

An **Employee Portal** application built with Spring Boot 2 and Spring Security 5 lets employees sign in with OpenID Connect (OIDC), call an Orders API with an access token, and authorize administrative pages. The legacy configuration relies on `WebSecurityConfigurerAdapter`:

~~~java
// LEGACY ONLY — does not compile on Spring Security 6.
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/", "/login", "/assets/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .oauth2Login()
                .loginPage("/login")
                .and()
            .oauth2Client();
    }
}
~~~

When upgrading to **Spring Boot 3 / Spring Security 6**, the adapter class is removed; legacy DSLs such as `antMatchers()` and `.and()` must also be replaced. The modern configuration is declared via **`@Bean SecurityFilterChain`**:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/assets/**")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth -> oauth
                .loginPage("/login")
            )
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is **component-based configuration**: instead of subclassing an adapter class, you provide beans to Spring Security.

**Key point:** the fact that the application compiles and starts does not mean it was migrated properly. Browser login, redirect/callback URIs, state/nonce/PKCE, session/CSRF, OIDC claims/authorities, authorized-client tokens, logout, and API permissions must all be preserved accurately.

> Scope: Java 17+, Spring MVC/Servlet, Spring Boot 3, Spring Security 6, OAuth2 Login, and OIDC Client. This lesson also covers handling legacy vendor adapters and distinguishing from WebFlux/Resource Server. Code is illustrative and does not use production secrets or tokens.

## 2. Learning Objectives

After this lesson, learners should be able to:

1. Understand why `WebSecurityConfigurerAdapter` was replaced by beans.
2. Convert `configure(HttpSecurity)` into a `SecurityFilterChain`.
3. Replace `authorizeRequests()/antMatchers()` with `authorizeHttpRequests()/requestMatchers()`.
4. Distinguish `securityMatcher` from `requestMatchers`.
5. Maintain OAuth2 Login, OIDC callbacks, and authorized-client management.
6. Migrate custom login pages, user services, success/failure handlers, and logout.
7. Migrate `configure(WebSecurity)` and authentication components properly.
8. Separate a browser OIDC session chain from a Bearer Resource Server API chain when needed.
9. Understand the impact of Jakarta Servlet, Spring Boot 3, CSRF, proxies, and sessions.
10. Regression-test security behavior and prepare rollout/rollback.

## 3. Old vs. New API Cross-Reference Table

| Legacy Spring Security | Spring Security 6 / modern config | Meaning |
|---|---|---|
| `extends WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain` | No adapter inheritance |
| `configure(HttpSecurity)` | Bean method accepting `HttpSecurity`, calling `http.build()` | HTTP security |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | AuthorizationManager-style |
| `antMatchers(...)` | `requestMatchers(...)` | URL matching rules |
| `mvcMatchers(...)` | `requestMatchers(...)` or explicit `RequestMatcher` | Check servlet/path semantics |
| `http.antMatcher(...)` | `http.securityMatcher(...)` | Restrict scope of the entire filter chain |
| Chained DSL `.and()` | Lambda DSL | Explicit configuration per configurer |
| `configure(WebSecurity)` | `WebSecurityCustomizer` if needed | Be careful bypassing filters |
| `configure(AuthenticationManagerBuilder)` | `UserDetailsService`, providers, `AuthenticationManager` beans | Decoupled authentication |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Method security |
| `javax.servlet.*` | `jakarta.servlet.*` | Spring Boot 3/Jakarta |

Spring Security supported `SecurityFilterChain` bean declarations prior to 6.x and deprecated `WebSecurityConfigurerAdapter` in the 5.7 line. The Lambda DSL is the recommended style for new configurations.

## 4. Why Is Component-Based Configuration Better?

~~~mermaid
flowchart TD
    A["Legacy WebSecurityConfigurerAdapter"] --> B["configure(HttpSecurity)"]
    A --> C["configure(WebSecurity)"]
    A --> D["configure(AuthenticationManagerBuilder)"]
    B --> E["New @Bean SecurityFilterChain"]
    C --> F["New WebSecurityCustomizer only if needed"]
    D --> G["New AuthenticationManager / authentication beans"]
    E --> H["FilterChainProxy"]
    I["OAuth2 Client beans"] --> H
~~~

Advantages:

- Not locked into overriding a single base class.
- Can define **multiple `SecurityFilterChain`s** with clear scopes and ordering.
- Authentication providers, OIDC user mapping, authorized-client managers, and HTTP security are configured independently.
- Easier to swap individual components in integration tests.

However, multiple beans also introduce risks of **duplicate beans**, **wrong filter chain ordering**, or **paths falling outside every chain**. That is why migration requires testing.

## 5. Preparation Step: Record the Old Security Contract

Do not modify code before listing current behavior:

| Behavior | Details to extract from legacy adapter |
|---|---|
| Public URLs | `/`, `/login`, assets, health |
| Protected URLs | Browser pages, admin pages, JSON APIs |
| Authorities | `ROLE_ADMIN`, scopes, tenant permissions |
| OAuth2 registration IDs | `company`, `partner`, ... |
| Login page | Custom-built or generated page |
| Authorization request | Default URI or custom resolver |
| Redirect callback | Base URI, `redirect_uri` |
| User mapping | `OidcUserService`, `OAuth2UserService`, groups/claims |
| Success/failure | Redirect, audit, provisioning |
| Authorized clients | Session, JDBC, Redis, or service |
| HTTP client | `WebClient`, `RestClient`, `RestTemplate` |
| Session/CSRF | `SessionCreationPolicy`, CSRF exemptions |
| Logout | Local logout, OP logout, token revocation |
| Filter order | Custom filters and adapter ordering |

When replacing configuration, the goal is to preserve these properties or change them intentionally.

## 6. Legacy Adapter Configuration with Multiple Responsibilities

Full historical example:

~~~java
// For reading and cross-referencing Spring Security 5 projects only.
@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class LegacyPortalSecurity
        extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers(
                    "/", "/login", "/assets/**", "/error"
                ).permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .antMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
                .and()
            .oauth2Login()
                .loginPage("/login")
                .defaultSuccessUrl("/home", false)
                .and()
            .oauth2Client()
                .and()
            .logout()
                .logoutSuccessUrl("/");
    }

    @Override
    public void configure(WebSecurity web) {
        web.ignoring().antMatchers("/favicon.ico");
    }
}
~~~

What to preserve:

~~~text
/                     public
/login                public
/assets/**            public
/error                public
/admin/**             ROLE_ADMIN
/api/**               authenticated
everything else       authenticated
OIDC login            active
OAuth2 client         active
custom login page     /login
post-login landing    /home unless saved request wins
logout success        /
~~~

Also review `web.ignoring()`: it bypasses the filter chain completely, unlike `permitAll()`.

## 7. Equivalent Modern Configuration with SecurityFilterChain

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
    .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration
    .EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain portalFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/assets/**",
                    "/favicon.ico", "/error"
                ).permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth -> oauth
                .loginPage("/login")
                .defaultSuccessUrl("/home", false)
            )
            .oauth2Client(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/")
            );

        return http.build();
    }
}
~~~

What is new:

1. No class extending the adapter.
2. `@Bean SecurityFilterChain` receives `HttpSecurity` injected by Spring.
3. `authorizeHttpRequests` and `requestMatchers` replace the old DSL.
4. `oauth2Login` preserves browser OAuth/OIDC login.
5. `oauth2Client` preserves OAuth2 Client features needed for authorized clients.
6. `http.build()` constructs the chain.

### 7.1. Not Every Bean Must Be Declared Manually

Spring Boot can create `ClientRegistrationRepository` and authorized-client components from properties. Unless you need a custom manager or repository, avoid creating duplicate beans that cause auto-configuration to back off.

### 7.2. Is @EnableWebSecurity Mandatory?

Spring Boot typically provides Security auto-configuration, but declaring `@EnableWebSecurity` makes the Java configuration's intent explicit. The key is avoiding two unintended filter chains caused by importing multiple configurations.

### 7.3. Not for WebFlux

If the application actually uses WebFlux Reactive, the equivalent is `SecurityWebFilterChain(ServerHttpSecurity)`, not `SecurityFilterChain(HttpSecurity)`.

## 8. Lambda DSL and Customizer.withDefaults()

Before:

~~~java
http
    .authorizeRequests().anyRequest().authenticated()
    .and()
    .oauth2Login()
    .and()
    .oauth2Client();
~~~

After:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults());
~~~

The Lambda DSL does not need `.and()` because after each lambda, configuration returns to `HttpSecurity`.

`Customizer.withDefaults()` enables the module with default settings; it does not mean all security/business policies are automatically appropriate.

### 8.1. Custom DSLs

If the old adapter used a custom `AbstractHttpConfigurer`, in Spring Security 6.2+ check `http.with(customDsl, customizer)` instead of `http.apply(customDsl)`, which is deprecated heading into Spring Security 7. Adjust according to your exact version.

### 8.2. Avoid Calling build() Twice

`HttpSecurity` is the builder for a single `SecurityFilterChain`. Never reuse an already-built builder for another chain.

## 9. requestMatchers() Is Not the Same as securityMatcher()

`requestMatchers()` inside `authorizeHttpRequests` is an **authorization policy inside a chain**:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
~~~

`securityMatcher()` is the **condition selecting the entire chain**:

~~~java
http.securityMatcher("/api/**");
~~~

### 9.1. Very Common Bug: OIDC Callback Outside the Chain

~~~java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
~~~

However, OAuth2 Login defaults to using:

~~~text
/oauth2/authorization/{registrationId}
/login/oauth2/code/{registrationId}
~~~

These two paths are not under `/api/**`. Without another chain containing the login filters, login initiation/callbacks will not work.

### 9.2. A Fallback Chain Protecting All Requests

For a browser app, include a chain without `securityMatcher` as a fallback, or ensure all required endpoints are matched by an intentional set of chains.

### 9.3. What Happens If No Chain Matches?

Requests matching no chain may **bypass Spring Security filters**. `anyRequest().authenticated()` in an `/api/**` chain does not protect `/admin/**`.

## 10. Migrating antMatchers/mvcMatchers with Path Care

Old:

~~~java
.antMatchers(HttpMethod.GET, "/catalog/**").permitAll()
.antMatchers("/admin/**").hasRole("ADMIN")
~~~

New:

~~~java
.requestMatchers(HttpMethod.GET, "/catalog/**").permitAll()
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Spring Security 6 supports `requestMatchers(...)` by path/method, but applications with **multiple Servlets**, custom servlet paths, or special URL parsing should select an explicit `RequestMatcher` and write tests to confirm semantics.

### 10.1. Do Not Accidentally Permit POST

~~~java
.requestMatchers(HttpMethod.GET, "/catalog/**").permitAll()
.requestMatchers(HttpMethod.POST, "/catalog/**")
    .hasRole("EDITOR")
~~~

Do not replace this with `.requestMatchers("/catalog/**").permitAll()`, as that could open write access.

### 10.2. Context Path Differs from Servlet Path

If the application is deployed with `server.servlet.context-path` or a custom `spring.mvc.servlet.path`, verify the actual matcher; do not prepend context prefixes into rules without understanding the matcher API.

### 10.3. Rule Ordering

A broad rule placed first can shadow narrower rules. Order controlled public endpoints first, specific rules next, and `anyRequest()` last.

## 11. Spring Boot 3, Java 17, and Jakarta Servlet

Upgrading from Spring Boot 2 to 3 simultaneously shifts the platform:

~~~text
Java 17+
Spring Framework 6
Spring Security 6
Jakarta EE namespace
~~~

Custom filter example:

~~~java
// Old:
import javax.servlet.FilterChain;
import javax.servlet.http.HttpServletRequest;

// New:
import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
~~~

Do not replace every `javax` namespace in Java SE; for instance, `javax.net.ssl` does not become `jakarta.net.ssl`.

### 11.1. Do Not Mix Spring Security 5 and 6 JARs

If `WebSecurityConfigurerAdapter` is missing, the fix is not adding `spring-security-config` 5.x to Boot 3. Migrate the code and use compatible dependency management/BOM.

### 11.2. JPA, Validation, and Other APIs

Jakarta Persistence/Validation imports may also need updating. They sit outside OIDC config but can block app startup/tests during migration.

## 12. ClientRegistration Remains the Core

`SecurityFilterChain` does not itself hold client ID, secret, or issuer. Spring Boot can read:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://login.company.example/realms/employees
~~~

`company` is the **registration ID**; `company-oidc` is the **provider alias**.

### 12.1. The `openid` Scope

When requested scopes include `openid`, Spring Security performs OIDC login with appropriate ID Token/`OidcUser` behavior. Do not treat an access token as an ID Token.

### 12.2. Secrets

Store client secrets in a secret manager or runtime environment; never commit them to source. When switching app/versions, confirm matching client registration at the OP and the right secret version.

### 12.3. Issuer Discovery

`issuer-uri` can cause the app to run OIDC discovery to build provider metadata. Integration tests should use fake metadata/`ClientRegistration` so they do not call a production IdP.

### 12.4. Registration ID Can Be a Storage Key

Renaming a registration ID can affect:

~~~text
/oauth2/authorization/{registrationId}
/login/oauth2/code/{registrationId}
authorized client lookup by registrationId
~~~

Do not rename an ID just for "prettier naming" while overlooking redirects and the token store.

## 13. oauth2Login() and oauth2Client() Have Different Roles

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults());
~~~

`oauth2Login()` handles **browser login** and creates the authenticated principal/session.

`oauth2Client()` supports **OAuth2 Client authorization/authorized clients** for calling downstream APIs with access tokens.

A successful Browser OIDC login does not prove:

- The Orders API will accept the access token.
- The access token has not expired.
- The authorized-client repository/service is storing tokens in the right place.
- Another `ClientRegistration` has received user consent.

### 13.1. Resource Server Is a Separate Role

`oauth2ResourceServer(server -> server.jwt(...))` is for an API **accepting Bearer access tokens**, not a replacement for Authorization Code browser login.

## 14. Custom Login Page After Migration

When declaring:

~~~java
.oauth2Login(oauth -> oauth.loginPage("/login"))
~~~

the application needs a `/login` page/route and must permit anonymous access:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login", "/assets/**").permitAll()
    .anyRequest().authenticated())
~~~

Controller:

~~~java
@Controller
class LoginPageController {
    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

HTML:

~~~html
<a href="/oauth2/authorization/company">
  Sign in with Company SSO
</a>
~~~

### 14.1. Do Not Confuse the Login Page with the OAuth Authorization Endpoint

`/login` is the Portal's UI. `/oauth2/authorization/company` is the Spring Security endpoint that initiates the redirect to the OP.

### 14.2. Login Redirect Loop

If `/login` also requires authentication, anonymous browsers can enter an infinite redirect loop to the login page. Test accessing `/login` without a session.

### 14.3. Custom Login Page Has No Automatic View

Setting `loginPage("/login")` means Spring does not generate a default template for you. Provide an actual controller/view or matching endpoint.

## 15. Authorization Request and Callback URI

Default URIs:

~~~text
Start:    /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
~~~

When customization is required:

~~~java
http.oauth2Login(oauth -> oauth
    .authorizationEndpoint(auth -> auth
        .baseUri("/sso/authorize"))
    .redirectionEndpoint(redirection -> redirection
        .baseUri("/sso/callback/*")));
~~~

then configure the registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/sso/callback/{registrationId}"
~~~

Login initiation link:

~~~text
/sso/authorize/company
~~~

### 15.1. Three Points Must Align

1. Authorization initiation URL.
2. Spring Security callback matcher.
3. Redirect URI on the OAuth2 `ClientRegistration` and registered at the OP.

Changing only one can trigger `invalid_redirect_uri`, callback 404, or `authorization_request_not_found`.

### 15.2. State, Nonce, PKCE

Never drop `state`, `nonce`, or PKCE code verifier when migrating custom authorization request resolvers/repositories. They bind the browser callback to the original authorization request.

## 16. Custom AuthorizationRequestRepository

Old adapter:

~~~java
http.oauth2Login()
    .authorizationEndpoint()
    .authorizationRequestRepository(customRepository);
~~~

Lambda DSL:

~~~java
http.oauth2Login(oauth -> oauth
    .authorizationEndpoint(auth -> auth
        .authorizationRequestRepository(customRepository)));
~~~

`customRepository` implements:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Default Servlet login typically stores the original authorization request in `HttpSession`. If using a custom cookie repository, ensure appropriate integrity/TTL/SameSite/Secure/HttpOnly and replay protection.

### 16.1. Do Not Use ThreadLocal Instead of Session

OIDC authorization involves browser redirects; the callback arrives in a different request, potentially on a different node. `ThreadLocal` cannot persist original state across this flow.

### 16.2. Multi-Node Session Store

Multi-pod apps can use Spring Session Redis/JDBC or another session-continuity solution. Migrating `SecurityFilterChain` does not automatically create a shared session.

## 17. OIDC User Mapping and Authorities

A legacy app may use a custom `OidcUserService` or vendor role mapper. New DSL:

~~~java
http.oauth2Login(oauth -> oauth
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(appOidcUserService)));
~~~

Illustrative service bean:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser>
appOidcUserService() {
    OidcUserService delegate = new OidcUserService();

    return request -> {
        OidcUser user = delegate.loadUser(request);
        Set<GrantedAuthority> authorities =
            new HashSet<>(user.getAuthorities());

        Object groups = user.getClaims().get("groups");
        if (groups instanceof Collection<?> values
                && values.contains("portal-admins")) {
            authorities.add(
                new SimpleGrantedAuthority("ROLE_ADMIN"));
        }

        if (user.getUserInfo() == null) {
            return new DefaultOidcUser(
                authorities, user.getIdToken(), "sub");
        }
        return new DefaultOidcUser(
            authorities,
            user.getIdToken(),
            user.getUserInfo(),
            "sub"
        );
    };
}
~~~

This is a **mapping pattern**, not a universal policy for every IdP. Verify the provider claims contract, issuer, tenant membership, and role source.

### 17.1. OAuth2UserService vs. OidcUserService

Within `userInfoEndpoint`, `userService(...)` handles generic OAuth2 UserInfo; `oidcUserService(...)` handles OIDC login. Use the right hook for the login type.

### 17.2. Role Mapping Does Not Happen Automatically

`hasRole("ADMIN")` typically checks `ROLE_ADMIN`. A JSON claim `{"roles":["admin"]}` does not automatically become a `GrantedAuthority` without mapping.

### 17.3. Identity Mapping

User identity should be based on trusted `(issuer, subject)` and tenant mapping in multi-org setups—never auto-merge users by email alone.

## 18. Success/Failure Handlers

Before:

~~~java
.oauth2Login()
    .successHandler(loginSuccessHandler)
    .failureHandler(loginFailureHandler)
~~~

After:

~~~java
http.oauth2Login(oauth -> oauth
    .successHandler(loginSuccessHandler)
    .failureHandler(loginFailureHandler));
~~~

Handlers can perform:

- Internal user provisioning/linking.
- Tenant membership checks.
- Login success/failure auditing.
- Redirecting to a saved request or default page.
- Displaying a safe error when the OP rejects login.

### 18.1. SavedRequest

`defaultSuccessUrl("/home", false)` normally respects the original saved request. Replacing it with a custom handler that always redirects to `/home` can make users lose the page they were trying to access before login.

### 18.2. Do Not Turn Handlers into Bypasses

A success handler must never accept an ID Token with an invalid signature/issuer/audience; it runs after authentication succeeds. Likewise, a failure handler must never create an authenticated principal when a callback fails.

### 18.3. Sanitized Errors

Never write raw provider error descriptions, authorization codes, access tokens, client secrets, or ID Tokens to logs or browser responses.

## 19. Authorized-Client Persistence Lives Outside HTTP Rules

`OAuth2AuthorizedClient` contains:

~~~text
ClientRegistration
principalName
OAuth2AccessToken
OAuth2RefreshToken (if present)
~~~

Core types:

~~~java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
OAuth2AuthorizedClientManager
~~~

The repository typically manages authorized clients across Servlet requests (often backed by `HttpSession`). The service manages them at the application level (in-memory/JDBC/custom).

### 19.1. Migration Does Not Mean Dropping the Token Store

If the legacy system stored refresh tokens in JDBC/Redis, accidentally switching to an InMemory store loses tokens on restart and causes reauthorization/token-endpoint storms.

### 19.2. Accurate Registration/Principal

Never cache tokens solely by email or username. An authorized client must bind to the exact registration and trusted principal; multi-tenant apps must partition accordingly.

## 20. OAuth2AuthorizedClientManager for Servlet Requests

When a custom manager is needed:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientRepository repository
) {
    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .clientCredentials()
            .build();

    DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
            registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

`DefaultOAuth2AuthorizedClientManager` is for `HttpServletRequest` contexts, loading/saving authorized clients and refreshing via the provider chain.

### 20.1. Do Not Create Unnecessary Managers

Some Spring Security versions provide a default manager bean; customize only when you need specific grants, providers, error handlers, or persistence.

### 20.2. Custom Success/Failure Handlers

Replacing handlers without persisting newly refreshed tokens can hit the token endpoint on every request. Overly broad failure handlers can wipe authorized clients belonging to other users/tenants.

### 20.3. Do Not Try to Escalate Scopes via Refresh

A refresh token cannot grant new permissions on its own. An API returning `403 insufficient_scope` requires checking consent/RBAC/authorization contracts, not infinite refreshing.

## 21. Background Jobs Use a Service-Based Manager

A `client_credentials` scheduled task has no browser `HttpServletRequest`. Use:

~~~java
@Bean
AuthorizedClientServiceOAuth2AuthorizedClientManager
serviceAuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientService service
) {
    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Request:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("reports-service")
    .principal("reports-job")
    .build();

OAuth2AuthorizedClient authorized =
    manager.authorize(request);
~~~

`reports-job` is a service storage principal, not an OIDC-logged-in employee. In production, the registration and service identity must come from trusted job configuration.

## 22. WebClient or RestClient After Removing the Adapter

For Servlet:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

integrates OAuth2 Client with `WebClient`. Spring Security 6.4+ also provides:

~~~java
OAuth2ClientHttpRequestInterceptor
~~~

for `RestClient`.

### 22.1. WebClient Example

~~~java
@Bean
WebClient ordersWebClient(OAuth2AuthorizedClientManager manager) {
    var oauth =
        new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .baseUrl("https://orders.example.test")
        .apply(oauth.oauth2Configuration())
        .build();
}
~~~

Explicit request:

~~~java
import static org.springframework.security.oauth2.client.web
    .reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
    .clientRegistrationId;

Mono<String> orders = ordersWebClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

### 22.2. Never Forward Bearer Tokens to Arbitrary URLs

If a request parameter determines the host:

~~~text
?target=https://untrusted.example
~~~

and `WebClient` attaches the token to the `Authorization` header, access tokens can leak. Bind registrations and destinations via a trusted allowlist.

### 22.3. Downstream Errors Differ from Login Errors

Orders API `401 Bearer invalid_token` differs from an unauthenticated Portal browser; `403 insufficient_scope` differs from an expired session. Do not log the user out on every HTTP 401 or evict authorized clients on 429/5xx.

## 23. Sessions Are Critical for Browser Login

Servlet OIDC authorization code login typically needs to store:

~~~text
OAuth2AuthorizationRequest
state
nonce
PKCE code_verifier per flow
SecurityContext
SavedRequest
~~~

Therefore:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

**is not suitable by default** for HttpSession-based browser OIDC login.

### 23.1. Bearer-Only APIs Can Be Stateless

Separate an API Resource Server chain if you want stateless JWT; keep the browser login chain on an appropriate session policy.

### 23.2. Session Fixation

Spring Security provides session fixation protection such as rotating the session ID after authentication. Tests must verify the callback correlates before login and the new session retains the authenticated state.

### 23.3. Multi-Node

Multiple pods require shared session storage/routing strategies; changing the adapter alone does not fix session continuity.

## 24. CSRF: Do Not Accidentally Disable It for Browsers

A common migration mistake is adding:

~~~java
.csrf(csrf -> csrf.disable())
~~~

app-wide just because a POST test returned 403. With browser session/cookie authentication, CSRF protection is usually still required.

### 24.1. Exempt Only With Justification

~~~java
.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider"))
~~~

Webhooks must be authenticated via their own mechanism (HMAC/mTLS or provider verification), never merely "permitted" because they are webhooks.

### 24.2. For Bearer-Only Stateless APIs

APIs accepting only `Authorization: Bearer` headers, without relying on auto-sent browser cookies, can use a different policy. Consider separating the `SecurityFilterChain`.

### 24.3. MockMvc

~~~java
mockMvc.perform(post("/api/settings")
        .with(oidcLogin())
        .with(csrf()))
    .andExpect(status().isOk());
~~~

`csrf()` comes from `SecurityMockMvcRequestPostProcessors`. If a POST test gets 403, check CSRF and roles, not just the OAuth token.

## 25. Two SecurityFilterChains: Browser OIDC and External Bearer API

~~~java
@Configuration
@EnableWebSecurity
public class MultiChainSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain externalApi(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/external/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(server -> server
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/assets/**", "/error"
                ).permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### 25.1. Chain Order

`FilterChainProxy` selects the first chain matching the request. The API chain at `@Order(1)` intercepts `/api/external/**` first; the browser fallback chain at `@Order(2)` handles all other routes.

### 25.2. Callbacks Remain Covered

Because the browser chain has no `securityMatcher`, it still matches:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
~~~

### 25.3. When Is Disabling CSRF on the API Valid in This Example?

Only when this API chain is **Bearer-only**, stateless, and does not accept browser cookie auth. If the API also accepts session cookies, do not disable CSRF.

## 26. configure(AuthenticationManagerBuilder) After Migration

Old adapter:

~~~java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth.userDetailsService(users)
        .passwordEncoder(passwordEncoder);
}
~~~

In the component-based model, if needed, an application can declare:

~~~java
@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails localAdmin = User.withUsername("local-admin")
        .password(encoder.encode("test-only-password"))
        .roles("ADMIN")
        .build();
    return new InMemoryUserDetailsManager(localAdmin);
}

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

This is a **local test/demo account** example; production must never store passwords in source, even hashed. Use an appropriate credential store and provisioning policy.

If a global manager is truly required:

~~~java
@Bean
AuthenticationManager authenticationManager(
    AuthenticationConfiguration configuration
) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

### 26.1. OIDC-Only Apps Rarely Need Local Password Login

If all users sign in via OIDC, do not add a `UserDetailsService`/password authentication just to replace an old override that is no longer needed.

### 26.2. Custom AuthenticationProvider

If you have a custom provider, register it as a bean/configuration scoped to the right chain. Do not let an API Bearer flow accidentally use a browser-login provider.

## 27. WebSecurityCustomizer: Only When Bypassing Filters Is Necessary

Old:

~~~java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**");
}
~~~

Recommended in most cases:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated())
~~~

`permitAll` keeps requests passing through the Spring Security filter chain, unlike `web.ignoring` which skips all filters, headers, and security infrastructure.

### 27.1. If a Customizer Is Truly Needed

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/very-special-unfiltered-path");
}
~~~

Evaluate carefully. Never ignore authentication endpoints, OIDC callbacks, or sensitive data.

### 27.2. Health Endpoints

Liveness/readiness health endpoints should have explicit network/access policies; never disable security app-wide just because a probe gets 401.

## 28. Method Security: @EnableMethodSecurity

Old:

~~~java
@EnableGlobalMethodSecurity(prePostEnabled = true)
~~~

New:

~~~java
@EnableMethodSecurity
~~~

Example:

~~~java
@Service
public class ReportsService {
    @PreAuthorize("hasRole('ADMIN')")
    public Report readSensitiveReport() {
        return /* ... */;
    }
}
~~~

### 28.1. Role Mapping

`hasRole("ADMIN")` usually expects `GrantedAuthority` `ROLE_ADMIN`. If a legacy IdP adapter previously mapped vendor groups, port that logic to `OidcUserService`/`GrantedAuthoritiesMapper`/JWT converter accordingly.

### 28.2. Self-Invocation

Proxy-based method security may not intercept `this.securedMethod()` called internally within the same bean; do not assume migrating the annotation fixes that automatically.

### 28.3. URL Rules and Service Rules Complement Each Other

HTTP controllers, scheduled jobs, or internal callers may invoke the same service; method security is an extra authorization layer, not a replacement for tenant/resource ownership validation.

## 29. Legacy Vendor-Specific Adapters (e.g., Keycloak)

A project may extend an IdP SDK adapter rather than only `WebSecurityConfigurerAdapter`. Legacy vendor adapters often performed:

- Browser OAuth2/OIDC login.
- Bearer token authentication.
- Mapping vendor-specific roles.
- Session registration and SSO logout.
- Token propagation/refresh.
- Client secret/provider configuration.

**There is no one-to-one class swap** that preserves all features.

| App role | Spring Security native replacement |
|---|---|
| Browser redirects/SSO | `oauth2Login()` with OIDC |
| Downstream tokens | `oauth2Client()` and manager |
| JWT Bearer API | `oauth2ResourceServer().jwt()` |
| Opaque token API | `oauth2ResourceServer().opaqueToken()` |
| UserInfo/OIDC role mapping | `OidcUserService`/`GrantedAuthoritiesMapper` |
| JWT resource roles | `JwtAuthenticationConverter` |
| RP-initiated logout | OIDC logout handler |
| Provider back-channel logout | Dedicated integration per provider/version |

### 29.1. Vendor Role Claims

For example, some IdPs emit structures like:

~~~json
{
  "realm_access": {"roles": ["auditor"]},
  "resource_access": {
    "portal": {"roles": ["admin"]}
  }
}
~~~

This is not a standard OAuth/OIDC claim schema that Spring understands out of the box. Map it according to verified tokens/claims and business policy.

### 29.2. Do Not Use Service Tokens to Bypass 403

If a logged-in user lacks permission, never call the API with a privileged `client_credentials` token just to make the request succeed. Permission boundaries must still be enforced.

### 29.3. Client and Resource Server Differ

An app receiving mobile API bearer tokens typically needs a Resource Server, not necessarily browser OAuth2 Login. Classify the role before migrating the adapter.

## 30. Logout Is Not Automatically Equivalent Across Adapters

Local logout:

~~~java
.logout(logout -> logout
    .logoutSuccessUrl("/"))
~~~

does not automatically terminate the SSO session at the OP or revoke all access/refresh tokens.

When the OP supports RP-initiated OIDC logout, Spring Security provides:

~~~java
OidcClientInitiatedLogoutSuccessHandler
~~~

Example:

~~~java
@Bean
LogoutSuccessHandler oidcLogout(
    ClientRegistrationRepository registrations
) {
    var handler =
        new OidcClientInitiatedLogoutSuccessHandler(registrations);
    handler.setPostLogoutRedirectUri("{baseUrl}/");
    return handler;
}
~~~

Attach to the chain:

~~~java
http.logout(logout -> logout
    .logoutSuccessHandler(oidcLogoutHandler));
~~~

`oidcLogoutHandler` in the example is an injected bean. Requires OP metadata/support and an appropriate post-logout URI allowlist.

### 30.1. Three Distinct Lifecycles

~~~text
Local HttpSession
OAuth2AuthorizedClient access/refresh tokens
OpenID Provider SSO session
~~~

Do not assume clearing one automatically terminates the other two.

## 31. Custom Filters in SecurityFilterChain

Old adapter:

~~~java
http.addFilterBefore(
    customFilter, UsernamePasswordAuthenticationFilter.class);
~~~

New bean chain still has:

~~~java
http.addFilterBefore(
    customFilter, UsernamePasswordAuthenticationFilter.class);
~~~

However, determine whether the filter should run before or after:

~~~text
OAuth2 authorization request filter
OAuth2 login authentication filter
SecurityContext filters
AuthorizationFilter
~~~

### 31.1. Avoid Double Filter Registration

If `customFilter` is a `@Component Filter`, Spring Boot may register it with the Servlet container automatically, while `http.addFilterBefore` registers it again in the Spring Security chain. Adjust `FilterRegistrationBean` or bean wiring to avoid double execution.

### 31.2. Do Not Block Callbacks with a Custom Bearer Filter

A custom filter rejecting every request lacking `Authorization: Bearer` will break browser callbacks if it runs before `OAuth2Login`. Use `RequestMatcher` and test specific endpoints.

### 31.3. Never Build Authentication from an Unsigned JWT

Claims extracted from an unverified JWT header/payload are untrusted. Require signature/issuer/audience checks before granting authorities.

## 32. Exception Handling: JSON API vs. Browser Login

For browser login, anonymous requests can redirect to a login page. JSON APIs often need `401` instead of 302/HTML:

~~~java
http.exceptionHandling(errors -> errors
    .defaultAuthenticationEntryPointFor(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
        new AntPathRequestMatcher("/api/**")
    ));
~~~

`AntPathRequestMatcher` is available in many Spring Security 6 releases but may be deprecated in newer ones; if moving to newer matchers, replace with a `RequestMatcher` of equivalent semantics.

### 32.1. 401 vs. 403

- **401**: caller is unauthenticated or session is invalid.
- **403**: caller is authenticated but lacks permission, or CSRF was rejected.

Do not return 401 for missing `ROLE_ADMIN`, causing the frontend to loop back to login endlessly.

### 32.2. Downstream 401 Does Not Automatically Log Out the Browser

Orders API returning `401 Bearer invalid_token` may require reauthorizing the authorized client, not necessarily marking the Portal user unauthenticated.

## 33. Trusted Proxy, baseUrl, and Redirect URI

In production:

~~~text
Browser HTTPS portal.company.example
  -> Reverse proxy
      -> Spring Boot HTTP 8080
~~~

Public OIDC callback:

~~~text
https://portal.company.example/login/oauth2/code/company
~~~

`{baseUrl}` must be resolved by Spring with the correct public scheme/host.

A configuration may use:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

However, ingress must **strip/overwrite client-supplied `Forwarded`/`X-Forwarded-*` headers**. Never use untrusted `X-Forwarded-Host` as a redirect URI, tenant ID, or issuer selector.

### 33.1. Redirect Mismatch

The IdP may reject a redirect URI that does not match its registration. When changing domains/paths/proxies, update the URI on both the OP and Spring sides.

### 33.2. SameSite

Browser cross-site OIDC callbacks depend on session cookies. GET callbacks with `Lax` work for many browser flows, whereas `response_mode=form_post` has different cross-site cookie requirements. Never disable state/CSRF to work around a wrong cookie policy.

## 34. SecurityContext Persistence in 6.x

If a custom adapter previously set Authentication manually:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

after migration do not assume Authentication is persisted for the next request. For custom authentication flows, use `SecurityContextRepository` or proper Spring Security authentication infrastructure.

### 34.1. Default OAuth2 Login

The OAuth2 Login filter has a lifecycle that persists the authenticated session per configured mechanism; never set the principal before `state`/nonce/ID Token are verified.

### 34.2. Test the Second Request

After the login callback, send a subsequent request using the issued cookie/session to verify `SecurityContext` persistence—do not assert only the callback redirect.

### 34.3. Do Not Bypass Session Fixation

The session ID may rotate after login. This is desired security behavior; tests must handle original authorization request/session correlation accordingly.

## 35. ERROR/FORWARD Dispatchers and Authorization

After migration, some applications see error pages turn into 403 because authorization rules apply to error/forward dispatches. When policy allows:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.ERROR,
        DispatcherType.FORWARD
    ).permitAll()
    .requestMatchers("/error").permitAll()
    .anyRequest().authenticated())
~~~

This is an intentional example; review the security requirements of your error views. Never blindly permit all sensitive forwards.

### 35.1. Distinguish Primary Requests from Error Dispatches

A request failing with 500 that is then denied on the error dispatch can surface as 403, misleading investigation. Log/trace by dispatch type and check HTTP filter rules too.

## 36. Upgrade Test Plan

| Test case | Expected |
|---|---|
| Anonymous GET `/` | Public |
| Anonymous GET `/assets/app.css` | Public, no unintended bypass |
| Anonymous GET `/login` | No redirect loop |
| Anonymous GET `/admin/report` | Login entry point or API 401 per policy |
| Regular OIDC user GET `/admin/report` | 403 |
| OIDC user `ROLE_ADMIN` GET `/admin/report` | 200 |
| OIDC user GET `/api/me` | 200 |
| POST `/api/settings` without CSRF | 403 if session CSRF is enabled |
| POST with CSRF and authentication | Succeeds |
| GET `/oauth2/authorization/company` | Redirects to trusted authorization endpoint |
| Callback with wrong state | Rejected |
| Callback ID Token wrong issuer/audience/signature | Rejected |
| Valid callback with same session | Authenticated |
| Token store loads right registration/principal | Yes |
| Outbound API Bearer | Token for right registration |
| Local logout | Session invalidated |
| OIDC OP logout | Per dedicated config |
| Bearer-only external API without token | 401, no HTML login |
| Bearer-only external API valid JWT | Policy checks issuer/audience/scopes |
| User from another tenant | No cross-tenant token/data access |

### 36.1. Do Not Test Only the Happy Path

An `oidcLogin()` test returning 200 at a controller only proves a mocked Authentication passed an authorization rule; it does not prove Authorization Code callback or ID Token signature validation.

## 37. Testing SecurityFilterChain with MockMvc

Dependencies:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Test fragment:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityMigrationIT {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotAccessAdminPage() throws Exception {
        mvc.perform(get("/admin/report"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void normalOidcUserCannotAccessAdminPage() throws Exception {
        mvc.perform(get("/admin/report")
                .with(oidcLogin()))
            .andExpect(status().isForbidden());
    }

    @Test
    void oidcAdminCanAccessAdminPage() throws Exception {
        mvc.perform(get("/admin/report")
                .with(oidcLogin()
                    .authorities(
                        new SimpleGrantedAuthority("ROLE_ADMIN"))))
            .andExpect(status().isOk());
    }
}
~~~

`/admin/report` needs an actual controller returning 200 when permitted. The anonymous redirect assertion assumes a browser chain with a login entry point; if the app configures an HTTP 401 API entry point, adjust the test to match the contract.

### 37.1. CSRF Test

~~~java
mvc.perform(post("/api/settings")
        .with(oidcLogin()))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/settings")
        .with(oidcLogin())
        .with(csrf()))
    .andExpect(status().isOk());
~~~

These tests require the route/controller to exist and not fail other business validation; the example illustrates CSRF policy.

### 37.2. API Tests Must Use the Right Authentication Type

If an API Resource Server uses JWT Bearer, the `jwt()` postprocessor fits authorization tests; do not use `oidcLogin()` to claim JWT resource validation ran.

## 38. OAuth2 Authorization Request/Callback Integration Tests

MockMvc:

~~~java
@Test
void startsOauthLogin() throws Exception {
    mvc.perform(get("/oauth2/authorization/company"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().exists("Location"));
}
~~~

Parse `Location` and assert:

~~~text
authorization endpoint matches trusted OP
client_id matches ClientRegistration
redirect_uri matches public callback
scope includes openid
state is nonempty
nonce is present for OIDC as required
PKCE code_challenge when configured
~~~

### 38.1. Callback Test with Fake OP

Fake token/JWKS endpoints let you test:

- Browser authorization request/state/session.
- Token endpoint response parsing.
- ID Token signature, issuer, audience, expiration.
- OIDC nonce validation.
- Authentication success/failure handlers.
- Session persistence.

Do not use `oidcLogin()` as a substitute for cryptographic tests.

### 38.2. With Multiple Registrations

Verify `/oauth2/authorization/company` cannot accidentally consume a callback/token meant for `partner`, especially when both share an issuer.

## 39. Authorized Client and Downstream Tests

MockMvc tests can seed an authorized client:

~~~java
mvc.perform(get("/api/orders")
        .with(oidcLogin())
        .with(oauth2Client("company")))
    .andExpect(status().isOk());
~~~

If the controller requires:

~~~java
@RegisteredOAuth2AuthorizedClient("company")
OAuth2AuthorizedClient client
~~~

the test must assert the right registration/principal/access-token context, not just 200.

### 39.1. Custom Repositories

The `oauth2Client()` test postprocessor may seed the `HttpSession` repository; if production uses a custom JDBC/Redis service, set up the matching store so tests do not give false confidence.

### 39.2. Outbound Bearer

Use a fake Orders API server/`ExchangeFunction` to assert:

~~~http
Authorization: Bearer <test-token-for-company>
~~~

Never expose real tokens in logs or Portal HTTP responses.

## 40. Low-Risk Migration Roadmap

### Step 1 — Capture the Security Contract

List public/protected URLs, roles, clients, session/CSRF, redirect URIs, logout, and custom filters. Write regression tests first.

### Step 2 — Prepare Dependencies

Upgrade Java, Spring Boot/Security, and Jakarta; avoid mixing major versions.

### Step 3 — Extract Beans

Create reusable `OAuth2UserService`/`OidcUserService`, authorized-client repositories/managers, and `AuthenticationProvider`s where needed.

### Step 4 — Replace the Adapter

Create `SecurityFilterChain`, porting authorization rules to the Lambda DSL and new matchers.

### Step 5 — Lock Chain Order

Ensure OAuth login initiation/callbacks always match the intended chain; keep stateless APIs cleanly separated if present.

### Step 6 — Sync with External IdP

Client IDs, secrets, issuer, authorization/token endpoints, redirect URI, role mapping, logout.

### Step 7 — Run Regression Tests

Happy-path and negative auth/authorization/CSRF/token/session/tenant/callback tests.

### Step 8 — Observe Rollout

Monitor login failures, callback state mismatches, token refresh errors, 401/403/429/5xx, and session/cookie incidents.

### Step 9 — Prepare Rollback

Keep the previous release/tag and a compatibility plan for tokens, sessions, and database schemas if storage migrated.

### Step 10 — Remove Leftover Adapters

Do not leave legacy configurations and new chains active together, causing overlapping security rules or hard-to-explain bypasses.

## 41. Post-Migration Observability

Metrics/logs should distinguish:

~~~text
oauth.login.start
oauth.login.success
oauth.login.failure
oauth.callback.state_mismatch
oauth.token.refresh.failure
authorization.denied
csrf.denied
session.invalidated
downstream.invalid_token
~~~

These names are application-defined examples, not a guarantee that Spring Security emits all of them by default.

**Never log**:

~~~text
access_token
refresh_token
id_token
client_secret
authorization_code
Authorization Bearer header
JSESSIONID/SESSION cookie
private key
~~~

### 41.1. Trace by Dependency and Registration

If only the `company` registration login fails, check its issuer, secret, redirect URI, and callback matcher. If all ADMIN requests return 403, check authority mapping, method security, and CSRF.

### 41.2. Do Not Enable Overly Broad Wire Logs

HTTP debug logs can print token endpoint requests/responses; enable only for controlled windows, redact, and enforce strict retention.

## 42. Quick Troubleshooting

| Symptom | Possible cause | Fix |
|---|---|---|
| `WebSecurityConfigurerAdapter` not found | Spring Security 6 removed adapter | Use `@Bean SecurityFilterChain` |
| `antMatchers()` does not exist | Legacy DSL | Use `requestMatchers` |
| `.and()` deprecated/unsuitable | Legacy DSL | Lambda DSL |
| `javax.servlet.*` compile error | Jakarta namespace | `jakarta.servlet.*` |
| Login page redirect loop | `/login` not `permitAll` | Fix authorization |
| OAuth start 404 | Chain does not match login entry | Fallback chain, registration |
| Callback 404 | Redirect matcher mismatch | Align redirect URI |
| `invalid_redirect_uri` | Provider registration mismatch | Fix public host/redirect |
| `authorization_request_not_found` | State/session lost | Cookie/SameSite/shared session |
| ID Token invalid issuer | Issuer config/trust mismatch | Correct `ClientRegistration` |
| User is admin yet gets 403 | Role mapping lost | OIDC authorities mapper |
| POST 403 | CSRF or role | Proper token/permissions |
| API returns HTML login page | Wrong chain/entry point | JSON 401 policy |
| Continuous token refreshes | Persistence/manager issue | Check store/success handler |
| Logout does not exit IdP | Local logout only | RP-initiated logout integration |
| Filter runs twice | Container + chain registration | `FilterRegistrationBean` |
| Error page turns into 403 | Dispatcher rule | ERROR/FORWARD policy |
| Multiple chains bypass URL | Wrong `securityMatcher`/order | Test chain coverage |
| Tests call production IdP | Issuer discovery | Fake provider/test profile |

## 43. Anti-Patterns to Avoid

**1.** Replacing only the adapter class without verifying login/callback/authorization semantics.

**2.** Putting `securityMatcher("/api/**")` on the only chain that has OAuth2 login.

**3.** Placing a broad `@Order(1)` chain before specific chains.

**4.** Using `web.ignoring("/**")` to "fix" 401s.

**5.** Disabling CSRF across an entire browser session app.

**6.** Enabling `STATELESS` for an HttpSession-based OIDC login chain.

**7.** Replacing OAuth2 Client and Resource Server with the same feature.

**8.** Dropping a vendor adapter's custom OIDC role mapper.

**9.** Failing to verify ID Token issuer/audience/signature.

**10.** Using email as a stable identity key across providers.

**11.** Changing the redirect URI without updating the OP.

**12.** Trusting `X-Forwarded-Host` without a trusted proxy.

**13.** Assuming local logout equals OP logout/token revocation.

**14.** Losing authorized-client persistence and causing a token endpoint storm.

**15.** Testing only 200 responses without testing anonymous/403/CSRF/callback/tenant cases.

## 44. Practice Exercises

### Exercise 1 — Migrate URL Rules

Legacy:

~~~java
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .anyRequest().authenticated();
~~~

**Answer:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated());
~~~

### Exercise 2 — OIDC Callback Returns 404

The only chain has `.securityMatcher("/api/**")`, and the callback is `/login/oauth2/code/company`.

**Solution:** The callback falls outside the chain; add a fallback chain covering OAuth2 endpoints or configure matching intentionally.

### Exercise 3 — Missing `ROLE_ADMIN`

ID Token has `groups=["admins"]`, yet `GrantedAuthorities` contains only `OIDC_USER`.

**Solution:** Port verified claim/tenant role mapping into `OidcUserService`/`GrantedAuthoritiesMapper`; do not expect Spring to grant `ROLE_ADMIN` automatically.

### Exercise 4 — Wrong Redirect Host

OP registers a public HTTPS URI, yet the app sends an HTTP localhost callback.

**Solution:** Check proxy forwarded headers, public base URL, `redirect-uri`, and OP client registration.

### Exercise 5 — POST 403

User is OIDC-logged-in, yet POST requests are rejected.

**Solution:** Check CSRF and RBAC; do not reflexively disable CSRF.

### Exercise 6 — Manager Cannot Find Token

Browser is authenticated, yet `WebClient` calling Orders API lacks a token.

**Solution:** Check `ClientRegistration`, principal, authorized-client repository/service, and manager.

### Exercise 7 — Scheduled Job

A `client_credentials` job uses the request-scoped `DefaultOAuth2AuthorizedClientManager`.

**Solution:** Use `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a service store.

### Exercise 8 — Static Assets

Legacy used `web.ignoring` for `/assets/**`.

**Solution:** Consider `requestMatchers("/assets/**").permitAll()` to keep security filters active.

### Exercise 9 — Vendor Adapter

Legacy adapter mapped provider realm roles automatically.

**Solution:** Determine whether it is browser OIDC or Resource Server, then map in `OidcUserService`/`GrantedAuthoritiesMapper` or the appropriate JWT converter.

### Exercise 10 — Logout

Local logout still leaves the OP session active.

**Solution:** If terminating OP SSO is required, configure OIDC RP-initiated logout per the provider contract and test it separately.

### Exercise 11 — State Mismatch

MockMvc `oidcLogin()` passes, yet real callbacks report invalid state.

**Solution:** Mock Authentication bypasses the callback. You need a fake OP integration test with the same browser session/state.

### Exercise 12 — Two Filter Chains

External JWT API must be stateless, while browsers need OIDC sessions.

**Solution:** Separate chains using `@Order`, `securityMatcher`, and a fallback browser chain; do not disable CSRF in the browser chain.

## 45. Pre-Deployment Checklist

| Question | Requirement |
|---|---|
| No classes still extending `WebSecurityConfigurerAdapter`? | Yes |
| `@Bean SecurityFilterChain` defined? | Yes |
| Using Lambda DSL? | Yes |
| `antMatchers`/`mvcMatchers` migrated? | Yes |
| `securityMatcher` scoped correctly? | Yes |
| Fallback chain protects remaining paths? | Yes |
| Multiple chain order tested? | Yes |
| Login page accessible anonymously? | Yes |
| OAuth2 authorization endpoint works? | Yes |
| OIDC callback matcher/redirect URI aligned? | Yes |
| State/nonce/PKCE still verified? | Yes |
| `ClientRegistration` issuer/clientId correct? | Yes |
| No hard-coded secrets? | Yes |
| OIDC authorities mapping still accurate? | Yes |
| Method security enabled if needed? | Yes |
| Session/CSRF appropriate for browser login? | Yes |
| `OAuth2AuthorizedClient` store compatible? | Yes |
| Manager matches web vs. job context? | Yes |
| Bearer API chain separated when needed? | Yes |
| API never mistakenly returns browser login HTML? | Yes |
| Static assets do not bypass filters unnecessarily? | Yes |
| Custom filters not double-registered? | Yes |
| Local logout/OP logout clearly defined? | Yes |
| Trusted proxy/public base URL accurate? | Yes |
| Jakarta imports updated? | Yes |
| MockMvc tests for 401/403/CSRF? | Yes |
| Fake OP tests for OIDC callback? | Yes |
| Token/registration/tenant isolation tested? | Yes |
| Logs do not leak credentials? | Yes |
| Rollback plan ready? | Yes |

## 46. Official References

- Spring Security Blog — **Spring Security without the WebSecurityConfigurerAdapter**: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter
- Spring Security 6.5 — **Java Configuration**: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — **Advanced OAuth2 Login Configuration**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security 6.5 — **Core OAuth2 Client Interfaces and Classes**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html
- Spring Security 6.5 — **Configuration Migrations / Lambda DSL**: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html

Cross-reference snippets against your project's **exact major/minor version**; some matchers/configuration APIs may change or become deprecated in newer releases.

## 47. Summary

Migrating from `WebSecurityConfigurerAdapter` to `SecurityFilterChain` means shifting from inheritance-based configuration to **independent beans**. Core modern pattern:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults());
    return http.build();
}
~~~

However, a real OAuth2/OIDC Client also involves **`ClientRegistration`, issuer/client ID, redirect URI, authorization state/nonce/PKCE, authenticated sessions, CSRF, user/authority mapping, authorized-client storage, token refresh, downstream HTTP integration, and logout semantics**. With vendor-specific adapters, you may need to separate browser login, Resource Server Bearer validation, and provider-specific claims/roles.

The greatest migration risks typically lie in an **overly narrow `securityMatcher` leaving callbacks outside the chain**, overly broad `permitAll` rules, enabling stateless mode in the wrong context, forgetting CSRF/role mapping, losing token persistence, or overlooking proxy redirects. Write tests covering **valid login, anonymous denial, ADMIN permissions, callback state/ID Token verification, sessions, token registration, and tenant isolation**.

**Key principle:** migration is complete when **security behavior is preserved or improved**, not merely when the code compiles and an endpoint returns HTTP 200.
