# Placing the CAS Filter in SecurityFilterChain and Avoiding Duplicate Request Processing

**Module:** Spring Security – Federation  
**Parent Topic:** CAS Integration  
**Scope:** CAS Protocol Service Ticket authentication for Servlet applications; Spring Boot 3.x, Spring Security 6.5, Java 17+. This article does not mix CAS Protocol with Spring Security SAML2 login or OAuth2/OIDC.

## 1. Objective: One CAS Callback Traverses the Right Authentication Path

In Central Authentication Service (**CAS**), after a user logs in at the CAS Server, the browser is redirected back to the application (**service/CAS client**) with the query parameter **`ticket=ST-...`**. The application uses **CasAuthenticationFilter** to receive the callback, **CasAuthenticationProvider** and **TicketValidator** call the CAS Server to validate the ticket, and then the app establishes **`Authentication`/`SecurityContext`** and its own session.

Problems arise when the CAS filter is placed wrongly in the security chain or registered twice across **two layers**:

1. **Servlet container filter chain:** Tomcat/Jetty/Undertow invokes Servlet Filters registered with the container.
2. **Spring Security `FilterChainProxy`:** itself invoked via **`DelegatingFilterProxy`**, picks one **`SecurityFilterChain`** and runs that chain's security filters.

If a **`CasAuthenticationFilter`** is both exposed as a **`Filter` bean** so Spring Boot auto-registers it with the container *and* inserted via **`http.addFilterAt(...)`** into Spring Security, the same request can pass through the filter instance **twice at two different positions/orders**. Consequences include duplicate callback handling, broken sessions/redirects, or attempting to re-validate an already-consumed Service Ticket.

**Practical rule:** A typical browser CAS application needs **one `CasAuthenticationFilter` inside the right `SecurityFilterChain`** and **zero standalone Servlet Filter registrations for that same filter**. Each callback must result in **one validation attempt** of the Service Ticket at the CAS Server, not two.

**Precision note:** Being invoked twice at the **`doFilter`** level does not always mean two ticket validations. **`AbstractAuthenticationProcessingFilter`** may succeed and redirect/short-circuit the chain before another filter runs. When debugging, distinguish **filter invocations**, **authentication attempts**, and **back-channel CAS validation calls** rather than jumping to conclusions from a single log line.

## 2. What Are the Two Layers: Servlet Filters and Spring Security?

~~~text
HTTP request from browser
       |
       v
Servlet Container Filter Chain
       |
       +-- Encoding / Observability / CORS filters (if any)
       |
       +-- DelegatingFilterProxy("springSecurityFilterChain")
               |
               v
         FilterChainProxy
               |
               +-- SecurityFilterChain #1 (e.g., /api/**)?
               |       -> selected only if first matcher matches
               |
               +-- SecurityFilterChain #2 (browser, fallback)
                       |
                       +-- SecurityContextHolderFilter
                       +-- HeaderWriterFilter
                       +-- CsrfFilter
                       +-- LogoutFilter
                       +-- CasAuthenticationFilter
                       +-- AnonymousAuthenticationFilter
                       +-- ExceptionTranslationFilter
                       +-- AuthorizationFilter
                       |
                       v
                    Controller/Servlet
~~~

**The diagram is simplified:** the exact filter list and ordering depend on DSL configuration, version, and other filters. Do not treat it as an immutable universal order for every app. What matters is that **the CAS authentication filter sits after essential security-context/exploit-protection filters and before authorization**, rather than sitting as a container filter outside the security boundary unintentionally.

### 2.1. `DelegatingFilterProxy`

**DelegatingFilterProxy** bridges the Servlet container and a Spring bean acting as a Filter. In Spring Boot with Spring Security, the key bean is normally named **`springSecurityFilterChain`** and is backed by **`FilterChainProxy`**.

You **do not need** to create a second `DelegatingFilterProxy` or instantiate `FilterChainProxy` manually to add a CAS filter. Spring Boot and Spring Security manage this plumbing automatically when Servlet Security is configured properly.

### 2.2. `FilterChainProxy` Picks Only the First Matching Chain

Suppose there are two chains:

~~~text
@Order(1) SecurityFilterChain API:
  securityMatcher("/api/**")
  -> for Basic/Bearer API

@Order(2) SecurityFilterChain Browser:
  default matcher for all remaining requests
  -> contains CasAuthenticationFilter
~~~

A request to **`/api/orders`** matches the first API chain and **never runs** the browser chain. A request to **`/login/cas`** does not match `/api/**`, so it enters the browser chain.

**Two `SecurityFilterChain` beans matching does not mean both run.** `FilterChainProxy` evaluates them in priority order and selects **only the first chain**. If an earlier chain has an overly broad **`/**`** or **`/*`** matcher without a CAS filter, the callback is "swallowed" by that other chain and never reaches the intended CAS filter.

### 2.3. `securityMatcher` Differs from `requestMatchers` in `authorizeHttpRequests`

- **`http.securityMatcher(...)`** decides **whether a `SecurityFilterChain` is selected to handle the request**.
- **`authorizeHttpRequests(...).requestMatchers(...)`** decides **authorization rules inside the already-selected chain**.
- **`permitAll()`** only states that authorization allows the URL; it **does not** create a CAS callback endpoint, **does not** insert `CasAuthenticationFilter`, and **does not** fix wrong chain selection.
- **`web.ignoring()`** bypasses Spring Security completely for matching URLs; ignoring **`/login/cas`** prevents the CAS filter inside the chain from ever seeing the callback.

**Error example:** The browser chain sets **`securityMatcher("/app/**")`**, yet the CAS callback is **`/login/cas`**. Even though the filter was added with `addFilterAt`, it **never runs** for that callback. Fix the matcher or align the callback/service URL rather than trying to "fix routing" with `permitAll`.

## 3. What Does `CasAuthenticationFilter` Do When Receiving a Service Ticket?

Spring Security provides **CasAuthenticationFilter** in the **spring-security-cas** module. For standard stateful browser CAS:

1. Browser accesses a protected resource with no `Authentication`.
2. **ExceptionTranslationFilter** invokes **CasAuthenticationEntryPoint** to redirect the browser to CAS **`/login?service=...`**.
3. CAS Server authenticates or reuses a valid SSO/TGT session and issues a new **Service Ticket** strictly for that service.
4. Browser returns to the callback, typically **`GET /login/cas?ticket=ST-...`**.
5. **CasAuthenticationFilter**, via **`AbstractAuthenticationProcessingFilter`**, matches the callback request and creates an unauthenticated **`CasServiceTicketAuthenticationToken`**.
6. **AuthenticationManager / ProviderManager** delegates the token to **CasAuthenticationProvider**.
7. The provider uses **TicketValidator** to call the CAS Server **`/serviceValidate`** (or configured endpoint) with **ticket + service URL**.
8. If CAS returns **`authenticationSuccess`** and the local account is accepted, the provider produces an authenticated **`CasAuthenticationToken`**.
9. The filter runs **`SessionAuthenticationStrategy`**, updates **`SecurityContextHolder`**, and persists context via **`SecurityContextRepository`**.
10. The success handler redirects to the original resource or permitted URL; subsequent requests use the SP `HttpSession` instead of re-validating the ST.

**An ST may be validated only once.** The CAS Protocol requires the CAS Server to invalidate the ST after **a single validation attempt, even if validation fails**. Therefore duplicate callback processing does not merely waste CPU: the second validation can fail with **`INVALID_TICKET`** even though the first succeeded.

### 3.1. Callback Must Match the Exact Path

`CasAuthenticationFilter` watches **`/login/cas`** by default. **`ServiceProperties.getService()`** must be the **public canonical callback URL** sharing that path, for example:

~~~text
ServiceProperties.service = https://portal.example.org/login/cas

FilterProcessesUrl         = /login/cas

CAS login parameter:
service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas

CAS validation parameter:
service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas
~~~

Do not configure **`ServiceProperties.service`** as `https://portal.example.org/` while the filter listens on `/login/cas`. Never construct the service URL from untrusted `Host`/`Forwarded` headers; the public HTTPS proxy and internal HTTP backend must agree on the service URL allowlisted at the CAS Server.

### 3.2. Do Not Enable `authenticateAllArtifacts` When Using Only Browser STs

**`ServiceProperties.setAuthenticateAllArtifacts(true)`** is an extended mode that handles CAS artifacts across arbitrary URLs (typically for proxy tickets or stateless clients). It alters **`requiresAuthentication`** logic and how service URLs are resolved; it is unnecessary for simple browser login.

For this guide, leave **`authenticateAllArtifacts=false`**, processing only the **`/login/cas`** callback. Never set it to `true` to "fix" a mismatched callback path, as that causes other URLs carrying a `ticket` query param to trigger authentication unexpectedly.

### 3.3. Service Tickets, Sessions, and Idempotency Requirements

- An **ST** is a **one-time** credential; its validation must never be treated as an idempotent request.
- The **SP `HttpSession`** is the local authentication result after a valid ST, serving many HTTP requests over the session lifetime.
- A **browser refreshing the callback URL** carrying an old ST is a brand-new HTTP request, not proof the filter ran twice on a single request.
- **CAS Single Logout (SLO)** has its own filters and lifecycle; never conflate it with the ST-validation filter or register CAS `SingleSignOutFilter` twice.

## 4. Types of Duplicate Processing and How to Tell Them Apart

| Symptom | Typical Cause | How to Identify |
| --- | --- | --- |
| **One HTTP request runs `CasAuthenticationFilter.doFilter` twice** | Filter bean auto-registered in container **and** added to security chain | Inspect Spring Boot Filter registrations and `SecurityFilterChain` |
| **Two `CasAuthenticationFilter` instances in the same chain** | Called `addFilterAt`/`addFilterBefore` twice or DSL/plugin added one | Print filter list of the matching chain and count instances of that class |
| **Two HTTP requests arrive at the same callback** | Refresh/back button, double redirect, browser retry, proxy retry, JS re-fetch | Request ID/trace ID, ST-masked access logs, CAS validate call count |
| **Two CAS `/serviceValidate` calls** | Two processing attempts or custom code retrying ST after timeout | Metrics/mock CAS endpoint, `TicketValidator` invocation count |
| **One callback processed by two different filter layers** | Raw CAS Servlet Filter / legacy `web.xml` plus Spring Security CAS filter | Check Servlet container registrations, legacy libs, filter ordering |
| **Callback falls into the wrong chain** | Broad `securityMatcher`/`@Order` or missing callback path | Spring Security TRACE chain selection, `FilterChainProxy.getFilters` |
| **Filter logs multiple times without calling CAS validate** | `DispatcherType.REQUEST`/`ERROR`/`FORWARD`/`ASYNC`; instrumentation runs per dispatch | Log `dispatcherType` + path + correlation ID; check `attemptAuthentication` |
| **CAS returns Success yet app enters redirect loop** | `SecurityContext` not saved, missing session cookie, wrong success handler | Inspect persistence/redirect chain rather than counting `doFilter` |
| **`INVALID_TICKET` after an earlier success** | Ticket already consumed; another flow tried reusing it | Count validation attempts per trace; never log raw tickets |

**Never "fix" this by skipping CAS validation.** Because a ticket can be attempted only once, prevent duplicate filter invocations and duplicate browser callbacks at the root cause rather than caching authentication keyed by raw ST to permit replay.

## 5. Mistake Number One: Filter Bean Auto-Registering Outside `SecurityFilterChain`

**Dangerous** example in Spring Boot:

~~~java
@Configuration
class IncorrectCasConfig {

    @Bean
    CasAuthenticationFilter casAuthenticationFilter() {
        return new CasAuthenticationFilter();
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http,
                            CasAuthenticationFilter casFilter)
            throws Exception {
        http.addFilterAt(
            casFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
~~~

This snippet **illustrates what to avoid, not a complete runnable class** (missing `AuthenticationManager`, validator, etc.). When the filter is a `@Bean`, Spring Boot **auto-registers it with the embedded Servlet container**, while `http.addFilterAt` inserts the same filter into `FilterChainProxy`. Consequently, the CAS filter can execute **outside** and **inside** the security chain.

### 5.1. Why `@Order` on a Filter Bean Is Not Enough

**`@Order`** or container filter registration order only adjusts ordering within the scope where it applies. It **does not eliminate** dual registration of the same filter, and does not force an auto-registered filter into `FilterChainProxy`.

**`@Order`** on a **`SecurityFilterChain` bean** prioritizes chain matchers—a completely different purpose. Never slap `@Order` onto a CAS filter and assume duplicate processing is fixed.

### 5.2. Preferred Pattern: Instantiate the Filter with `new` Inside `SecurityFilterChain`

~~~java
@Bean
SecurityFilterChain browser(
        HttpSecurity http,
        ServiceProperties service,
        CasAuthenticationEntryPoint entryPoint,
        CasAuthenticationProvider provider)
        throws Exception {

    CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
    casFilter.setFilterProcessesUrl("/login/cas");
    casFilter.setServiceProperties(service);
    casFilter.setAuthenticationManager(new ProviderManager(provider));

    // Configure SecurityContextRepository + session strategy
    // as shown in the complete example later.

    http
        .exceptionHandling(e -> e.authenticationEntryPoint(entryPoint))
        .addFilterAt(
            casFilter, UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
~~~

**This is a fragment**, not complete code. The key lesson: `CasAuthenticationFilter` **is not a `@Bean`** in this pattern, so Spring Boot **does not discover it as a Servlet Filter bean**. It lives solely in the chain where you added it via `HttpSecurity`.

### 5.3. When You Truly Must Declare a `@Bean` for Injection

Occasionally an app needs a filter bean (for dependency injection, tests, or reuse). In that case, explicitly disable Servlet auto-registration:

~~~java
@Bean
FilterRegistrationBean<CasAuthenticationFilter>
disableCasServletRegistration(CasAuthenticationFilter filter) {
    FilterRegistrationBean<CasAuthenticationFilter> bean =
        new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
~~~

Required imports:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.security.cas.web.CasAuthenticationFilter;
~~~

**This is an ALTERNATIVE** to instantiating with `new` in Section 5.2, not something to add on top of both. With the bean variant: configure **one `CasAuthenticationFilter` bean with all collaborators set**, inject that single instance into **one** `SecurityFilterChain`, and declare a disabled `FilterRegistrationBean` for **that exact instance**.

**Understanding `setEnabled(false)`:** It prevents **container registration** for this bean; it **does not disable the CAS filter inserted into Spring Security**. If a legacy servlet filter registration still exists via `web.xml`/`@WebFilter`/`ServletContext.addFilter`, remove that registration separately.

## 6. Positioning `CasAuthenticationFilter` in `HttpSecurity`

Spring Security offers three placement methods:

- **`addFilterBefore(customFilter, SomeKnownFilter.class)`**: places it before a filter whose order slot Spring Security knows.
- **`addFilterAfter(...)`**: places it after a known filter.
- **`addFilterAt(customFilter, SomeKnownFilter.class)`**: places it at the **same order slot** as the reference filter; very suitable for placing CAS authentication at the standard auth filter slot.

For browser CAS **without `formLogin`** and without competing auth filters in that slot, a common pattern is:

~~~java
http.addFilterAt(
    casAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class);
~~~

**Do not interpret `addFilterAt` as "removing every other filter at that slot."** It only specifies position. If another config also adds `UsernamePasswordAuthenticationFilter` or a second `CasAuthenticationFilter` at the same slot, resolve the conflict cleanly rather than relying on arbitrary tie-breaking among filters with the same order.

**Never use `addFilterAfter(..., AuthorizationFilter.class)`** for CAS login: authorization would reject the request before the ST is ever validated. An authentication filter belongs in the authentication zone, before authorization and aligned with `SecurityContext` handling.

### 6.1. Steps That Must Stay Intact

1. **`SecurityContextHolderFilter`/`SecurityContextRepository`** prepares loading of any existing `SecurityContext`.
2. Request-protection filters (headers, method/endpoint CSRF, etc.) remain active.
3. **`CasAuthenticationFilter`** intercepts callbacks matching its URL.
4. **`AuthenticationManager`** verifies the CAS token via provider and validator.
5. **`SessionAuthenticationStrategy`** enforces session fixation protection for stateful browser login.
6. **`SecurityContextRepository.saveContext(...)`** is invoked by the authentication filter per Spring Security 6 on success.
7. **`AuthorizationFilter`** enforces resource permissions.
8. **`SuccessHandler`/`FailureHandler`** redirects or reports failure cleanly; never construct `Authentication` directly from the `ticket` query param.

**Never alter ordering by creating a new `DelegatingFilterProxy` or a second `FilterChainProxy`.** Spring Security manages their lifecycle and `HttpFirewall`; bypassing them can corrupt `SecurityContext` and session state.

## 7. Spring Boot 3 / Spring Security 6.5 / Java 17 Example: One Filter, One Callback

This is a Spring MVC Servlet example using **CAS Protocol 2.0** for browser login. It uses **`spring-security-cas`**, not `saml2Login()`. The **`example.org`** domains are placeholders; running against real CAS requires an HTTPS CAS Server, a service registry entry permitting the service URL, a **`demo`** user on the CAS Server, and valid TLS metadata/certificates. The example grants only `ROLE_USER` for demo purposes and does not replace production account linking or business authorization.

### 7.1. Dependencies in `pom.xml`

In a Maven project with a compatible Spring Boot parent/BOM:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
~~~

The CAS client validator comes via the CAS client dependency compatible with the Spring Security module. If your version does not pull **`cas-client-core`** transitively into the dependency tree, add it per the module guide and inspect Maven dependencies; never force an old CAS client version outside the BOM without checking compatibility.

### 7.2. `application.yml`

**src/main/resources/application.yml**

~~~yaml
app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    service-url: https://portal.example.org/login/cas

server:
  servlet:
    session:
      timeout: 30m

logging:
  level:
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security.web.DefaultSecurityFilterChain: DEBUG
~~~

**`server-base-url`** is the CAS Server base configured for the validator to call **`/serviceValidate`**. **`login-url`** is where the browser is redirected. **`service-url`** is the public callback registered in the CAS service registry.

Do not assume **`http://localhost:8080`** can receive CAS callbacks when the declared service URL is **`https://portal.example.org/login/cas`**. When running in a test environment, update the public service URL consistently across the client, CAS registry, and reverse proxy.

Note that this logging setup is **for development environments only** and must not log raw query tickets. Spring Security DEBUG can record request paths/metadata; production requires sanitizing access logs, traces, and URL parameters.

### 7.3. Main Class

**src/main/java/com/example/cas/CasApplication.java**

~~~java
package com.example.cas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasApplication.class, args);
    }
}
~~~

### 7.4. Complete CAS Configuration

**src/main/java/com/example/cas/CasSecurityConfig.java**

~~~java
package com.example.cas;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String serviceUrl) {
        ServiceProperties props = new ServiceProperties();
        props.setService(serviceUrl);
        props.setSendRenew(false);
        props.setAuthenticateAllArtifacts(false);
        return props;
    }

    @Bean
    CasAuthenticationEntryPoint casEntryPoint(
            ServiceProperties serviceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(loginUrl);
        entryPoint.setServiceProperties(serviceProperties);
        return entryPoint;
    }

    @Bean
    UserDetailsService localUsers() {
        // Demo only for CAS user "demo"; password is never used
        // to authenticate CAS. Production looks up a local account DB.
        return username -> {
            if (!"demo".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Local user not enabled");
            }
            return User.withUsername(username)
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build();
        };
    }

    @Bean
    CasAuthenticationProvider casProvider(
            ServiceProperties serviceProperties,
            UserDetailsService localUsers,
            @Value("${app.cas.server-base-url}") String casBaseUrl) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(serviceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(casBaseUrl));
        provider.setUserDetailsService(localUsers);
        provider.setKey("portal-cas-provider-v1");
        return provider;
    }

    @Bean
    SecurityFilterChain browserSecurity(
            HttpSecurity http,
            ServiceProperties serviceProperties,
            CasAuthenticationEntryPoint entryPoint,
            CasAuthenticationProvider provider) throws Exception {

        SecurityContextRepository contextRepository =
            new HttpSessionSecurityContextRepository();

        // IMPORTANT: no @Bean and no @Component.
        // Registered solely via HttpSecurity inside this chain.
        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();

        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setServiceProperties(serviceProperties);
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setSecurityContextRepository(contextRepository);
        casFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(sc -> sc
                .securityContextRepository(contextRepository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .addFilterAt(
                casFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Why does this avoid double registration?**

- Only **`CasAuthenticationProvider`, `ServiceProperties`, and `CasAuthenticationEntryPoint`** are shared beans. None of them are **Servlet Filters**.
- **`CasAuthenticationFilter`** is instantiated exclusively with **`new`** inside **`browserSecurity`**; with no **`@Bean`** for the filter, Spring Boot cannot auto-register it outside Spring Security.
- Only **one `http.addFilterAt`** places it into the browser chain.
- **`filterProcessesUrl=/login/cas`** aligns with the registered public **`ServiceProperties.service`**.
- **`ProviderManager(provider)`** contains only the CAS provider for callbacks; no two competing providers process `CasServiceTicketAuthenticationToken`.
- **`HttpSessionSecurityContextRepository`** is shared between the authentication filter and the security chain, preventing login from succeeding on one request without persisting context.
- **`ChangeSessionIdAuthenticationStrategy`** mitigates session fixation upon successful CAS login.
- **`SessionCreationPolicy.IF_REQUIRED`** keeps browser CAS stateful instead of accidentally setting `STATELESS` and losing sessions.
- **`formLogin()`** is disabled, avoiding a competing `UsernamePasswordAuthenticationFilter` at the same slot. **`addFilterAt`** sets the authentication filter's position without assuming another filter is automatically removed.
- **`http.csrf().disable()`** is unnecessary for a standard CAS GET callback. CSRF protection for state-changing app actions remains enabled by default.

**Additional caveats:** this demo config allows only CAS user **`demo`**; if CAS logs in as any other user, the local `UserDetailsService` throws an error even when ticket validation succeeds. That is **fail-closed** per demo policy, not a duplicate filter. The `"{noop}unused-by-cas"` password field is just a sample `UserDetails` placeholder and **never participates in CAS authentication**; production must manage credentials properly if additional auth mechanisms are enabled.

### 7.5. Controller to Observe Post-Login `Authentication`

**src/main/java/com/example/cas/CasController.java**

~~~java
package com.example.cas;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CasController {

    @GetMapping("/")
    public String home() {
        return "CAS filter-chain demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(Principal principal) {
        return Map.of(
            "name", principal.getName(),
            "authentication", "local-SP-session");
    }
}
~~~

After a successful CAS callback, **`/me`** uses the local `Authentication` from `SecurityContext`/`HttpSession`. There is no need to resend the Service Ticket on subsequent requests. Production should restrict exposed principal/attribute fields based on user permissions.

### 7.6. Run Commands and Expected Behavior

In a complete Maven project with Java 17+, run:

~~~bash
mvn spring-boot:run
~~~

Public endpoint once the app starts:

~~~bash
curl -i http://localhost:8080/
~~~

Body:

~~~text
CAS filter-chain demo
~~~

For an unauthenticated **`GET /me`** at the public SP URL: the browser is redirected to CAS **`/login?service=...`**. After CAS issues a fresh Service Ticket, the callback **`/login/cas?ticket=ST-...`** passes through the single configured `CasAuthenticationFilter`, the ticket is verified over the CAS back-channel, and `SecurityContext` is saved. The browser then uses the SP session cookie.

**These steps describe logical expectations, not a claim of an end-to-end run** against a CAS Server on `example.org`. Without an actual CAS server, an allowlisted service, and user `demo`, full login cannot complete with sample code alone.

## 8. Multiple `SecurityFilterChain` Variant: Ensuring the CAS Callback Is Not Swallowed

An application may define **`/api/**`** for stateless Bearer/Basic APIs alongside a stateful CAS browser area.

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserSecurity(HttpSecurity http,
        /* dependencies for CAS */) throws Exception {
    // Create/configure CasAuthenticationFilter with new here,
    // using ServiceProperties/ProviderManager/ContextRepository.
    // http.addFilterAt(casFilter, UsernamePasswordAuthenticationFilter.class);
    // Then return http.build().
}
~~~

**This is an architectural fragment** (with placeholder comments and missing imports/dependencies on the second method), not a second snippet to paste verbatim into Section 7's demo class. To use multiple chains for real, adapt Section 7's `browserSecurity` method accordingly and import **`org.springframework.core.annotation.Order`**, **`org.springframework.security.config.Customizer`**, and **`SessionCreationPolicy`**.

**Matching rules:**

- `GET /api/orders` -> API chain at `@Order(1)`; `CasAuthenticationFilter` is not used.
- `GET /login/cas?ticket=...` -> does not match `/api/**`, so it enters the browser chain containing the CAS filter.
- `GET /private` -> browser chain, which can initiate CAS login.
- If the browser chain sets **`securityMatcher("/web/**")`**, the **`/login/cas`** callback is excluded; include the callback in the matcher or use a fallback chain—never just `permitAll`.
- If the API chain sets **`securityMatcher("/**")`** with higher priority, it captures every request including the callback, and the browser chain never runs. That is a **chain selection bug**, not a CAS `TicketValidator` failure.

**Note:** Applications with multiple paths, proxies, and authentication schemes need crisp boundaries. Do not enable HTTP Basic on the browser CAS chain unnecessarily, as it changes the entry point and login experience. Across multiple chains, each chain has its own `HttpSecurity` shared objects and exception handling; never assume API configuration carries over to the browser chain.

## 9. How to Find Which Filter Was Actually Selected

There are two levels to inspect:

### 9.1. Startup: Filter List for Each Chain

Enable controlled DEBUG logging and inspect **`DefaultSecurityFilterChain`** at startup:

~~~yaml
logging:
  level:
    org.springframework.security.web.DefaultSecurityFilterChain: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

You should see **`CasAuthenticationFilter`** listed inside the browser chain's security filters. Count instances in that chain: **the target is one**.

`FilterChainProxy` TRACE logs show which matcher was evaluated and which chain was chosen for each request. **Do not leave TRACE enabled in production**, as it can expose URLs containing **`ticket=ST-...`**, paths, and sensitive access details.

### 9.2. Runtime: Distinguishing HTTP Requests from Servlet Dispatches

If logs repeat, first record and correlate sanitized fields:

~~~text
request correlation ID
dispatcherType = REQUEST / FORWARD / ERROR / ASYNC
HTTP method
normalized path (WITHOUT ticket query)
selected SecurityFilterChain
CasAuthenticationFilter.doFilter entry count
CasAuthenticationFilter.attemptAuthentication count
TicketValidator.validate count
HTTP response status / redirect destination (sanitized)
~~~

**A single request can be dispatched multiple times** in the Servlet lifecycle. An exception can trigger an **`ERROR` dispatch**; an async request can trigger an **`ASYNC` redispatch**. That does not necessarily mean two browser requests or two CAS validation attempts.

**Never log raw tickets.** If dev/test correlation is needed, use a **test-issued request ID** or a short-TTL keyed hash rather than using the ticket as a long-lived identifier.

### 9.3. Counting the Right Components to Confirm "Double" Processing

| Metric | Expected Value for One Happy-Path Callback | Meaning |
| --- | --- | --- |
| Browser callback HTTP requests | 1 request from browser for a fresh ST | Single entry URL into the app |
| `SecurityFilterChain` selected | 1 (first matching chain) | `FilterChainProxy` does not stack chains |
| `CasAuthenticationFilter` in chosen chain | 1 | No duplicate instances inserted |
| Servlet auto-registrations of CAS filter | 0 | No standalone CAS layer outside security |
| CAS `TicketValidator` validation attempts | 1 | Single-use Service Ticket |
| CAS Server `serviceValidate` calls | 1 | Server-side back-channel evidence |
| SP `SecurityContext` after callback | Authenticated when local account valid | Not granted automatically from ST string alone |

**If you actually see two Servlet callbacks**, check browser refreshes, proxy retries, JavaScript callbacks, and redirect loops before blaming filter-bean auto-registration. If you see one request yet two attempts, inspect duplicate filters, custom provider retries, gateway interception, or exception/re-dispatch re-execution.

## 10. How Does Spring Boot Auto-Register a Filter Bean?

In Spring Boot Servlet, any Spring bean of type **`jakarta.servlet.Filter`** is auto-registered as a **Servlet Filter** with the embedded container. If that exact same filter instance is also invoked by Spring Security's `FilterChainProxy`, it executes in two places.

Example:

~~~text
Servlet Container
  |
  +-- CasAuthenticationFilter bean   <-- auto-registered outside Security
  |
  +-- DelegatingFilterProxy(springSecurityFilterChain)
          |
          +-- FilterChainProxy
                  |
                  +-- CasAuthenticationFilter bean
                         <-- same filter instance also added via addFilterAt
~~~

**Therefore, a single singleton bean does not guarantee single execution.** One instance can sit at two registration points. Inspect the **filter registration paths**, not just the number of beans created.

### 10.1. Registration Options Table

| Declaration Style | Can Auto-Register in Servlet? | Inside `SecurityFilterChain`? | Recommendation |
| --- | --- | --- | --- |
| **`new CasAuthenticationFilter()` inside `@Bean SecurityFilterChain`**, added once via `addFilterAt` | No, because it is not a Filter bean | Yes | **Preferred** |
| **`@Bean CasAuthenticationFilter`** + `addFilterAt`, without disabling container registration | Yes | Yes | **Avoid** |
| **`@Bean CasAuthenticationFilter`** + **`FilterRegistrationBean.enabled=false`** + single `addFilterAt` | Prevented by `FilterRegistrationBean` | Yes | Use when a bean is needed |
| **`@WebFilter`** or **`ServletContext.addFilter`** only | Yes | Not necessarily | Does not replace standard Spring Security CAS filter |
| Creating **two separate CAS filters** in the same chain | Maybe not auto-registered | Two present | Avoid |
| Registering an extra **`DelegatingFilterProxy`** outside Boot config | Can create multiple entries into Spring Security | Yes | Avoid unless thoroughly reviewed |

**Once you pick an approach, remove legacy XML/`web.xml`/filter registrations from older setups.** Eliminating duplicate registrations at the source is far better than adding log guards or suppressing duplicate errors.

## 11. Preventing Duplicate Validation at the Protocol Level

A CAS Service Ticket is **service-bound** and **one-time**. Trying the same ST twice yields:

~~~text
Attempt 1: CAS /serviceValidate(ticket=ST-X, service=portal)
   -> cas:authenticationSuccess
   -> ST-X is consumed

Attempt 2: CAS /serviceValidate(ticket=ST-X, service=portal)
   -> cas:authenticationFailure/INVALID_TICKET
~~~

**There is no safe "retry until it works" strategy.** If a callback is hit twice or a CAS validation timeout leaves consumption status unclear, obtain a **new ST** via a fresh CAS login flow.

### 11.1. Never Attach Business Side Effects to the Callback GET

While the CAS GET callback performs **login authentication** per protocol, the application must never let **`/login/cas`** create orders, process payments, or perform other business side effects. Process the ST -> establish `Authentication` and redirect to a clean URL; subsequent business actions require proper authorization and CSRF protection.

### 11.2. Never Keep the Ticket in the Final Redirect

Practice:

~~~text
GET /login/cas?ticket=ST-X
  -> CAS validation
  -> login success
  -> 302 /private
  -> browser GET /private (no ticket)
~~~

Avoid having the success handler redirect back to the **request URL still containing `?ticket=ST-X`**. When the user refreshes a URL holding a ticket, CAS must reject the replay. "Used ticket" errors after browser back/refresh should be handled via a controlled new login flow or an appropriate message—never by accepting old tickets.

### 11.3. POST, CSRF, and Proxy Retries

- Standard CAS browser Service Tickets arrive via a **GET callback**; default CSRF protection does not require a token on safe GET methods.
- State-changing POST/PUT/DELETE APIs still need CSRF protection with cookie sessions; **never disable CSRF globally** just to get the CAS callback working.
- Reverse proxies/load balancers must not blindly retry GET callbacks carrying tickets when the upstream may have already consumed the ST; timeout/retry rules must respect single-use semantics.
- If handling CAS callbacks via custom POST or gateway mode, design method matching and CSRF threat models explicitly; never flip the filter to **`authenticateAllArtifacts=true`** for every path.

## 12. Runnable Java 17: Simulating Double Registration and One-Time Tickets

To see how **two registration paths can trigger two validation attempts**, use a standalone program needing no Spring, CAS Server, or network. This is an **intentional simulation**: the real framework often redirects/short-circuits the filter chain upon success and thus does not always hit CAS twice on every misconfiguration. This program demonstrates why you must never assume "if two filters exist, the ST will still work fine."

**File: `DuplicateCasFilterDemo.java`**

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class DuplicateCasFilterDemo {

    static final class TicketRegistry {
        private final Set<String> unused = new HashSet<>();
        int validationAttempts;

        void issue(String ticket) {
            unused.add(ticket);
        }

        boolean validateOnce(String ticket) {
            validationAttempts++;
            return unused.remove(ticket);
        }
    }

    static final class SimulatedCasFilter {
        private final TicketRegistry registry;
        int callbackInvocations;
        int successes;
        int failures;

        SimulatedCasFilter(TicketRegistry registry) {
            this.registry = registry;
        }

        void apply(String path, String ticket) {
            if (!"/login/cas".equals(path)) {
                return;
            }

            callbackInvocations++;
            if (registry.validateOnce(ticket)) {
                successes++;
            } else {
                failures++;
            }
        }
    }

    static final class Pipeline {
        final List<SimulatedCasFilter> servletFilters =
            new ArrayList<>();
        final List<SimulatedCasFilter> securityFilters =
            new ArrayList<>();

        void process(String path, String ticket) {
            for (SimulatedCasFilter filter : servletFilters) {
                filter.apply(path, ticket);
            }
            for (SimulatedCasFilter filter : securityFilters) {
                filter.apply(path, ticket);
            }
        }
    }

    public static void main(String[] args) {
        TicketRegistry goodTickets = new TicketRegistry();
        goodTickets.issue("ST-A");
        SimulatedCasFilter goodFilter =
            new SimulatedCasFilter(goodTickets);
        Pipeline good = new Pipeline();
        good.securityFilters.add(goodFilter);
        good.process("/login/cas", "ST-A");
        System.out.println(
            "singleInvocations=" + goodFilter.callbackInvocations);
        System.out.println(
            "singleValidations=" + goodTickets.validationAttempts);
        System.out.println(
            "singleSuccess=" + goodFilter.successes);

        TicketRegistry badTickets = new TicketRegistry();
        badTickets.issue("ST-B");
        SimulatedCasFilter badFilter =
            new SimulatedCasFilter(badTickets);
        Pipeline bad = new Pipeline();
        bad.servletFilters.add(badFilter);
        bad.securityFilters.add(badFilter);
        bad.process("/login/cas", "ST-B");
        System.out.println(
            "doubleInvocations=" + badFilter.callbackInvocations);
        System.out.println(
            "doubleValidations=" + badTickets.validationAttempts);
        System.out.println(
            "doubleSuccess=" + badFilter.successes);
        System.out.println(
            "doubleFailure=" + badFilter.failures);

        good.process("/private", null);
        System.out.println(
            "afterPrivateValidations=" +
                goodTickets.validationAttempts);

        good.process("/login/cas", "ST-A");
        System.out.println(
            "afterReplayValidations=" +
                goodTickets.validationAttempts);
        System.out.println(
            "afterReplayFailures=" + goodFilter.failures);
    }
}
~~~

Compile and run (Java 17+):

~~~bash
javac DuplicateCasFilterDemo.java
java DuplicateCasFilterDemo
~~~

**Exact stdout:**

~~~text
singleInvocations=1
singleValidations=1
singleSuccess=1
doubleInvocations=2
doubleValidations=2
doubleSuccess=1
doubleFailure=1
afterPrivateValidations=1
afterReplayValidations=2
afterReplayFailures=1
~~~

**Explanation:**

- When the filter lives only in the security chain, the first callback produces **one invocation and one validation**.
- When the exact same instance is added to both **`servletFilters`** and **`securityFilters`**, the model invokes both, triggering **two validation attempts** where the CAS registry succeeds on the first and fails on the second.
- Requests to **`/private`** do not match the callback, so the filter validates no ticket.
- A fresh browser request to **`/login/cas`** with already-used `ST-A` is rejected—that is a **replay request**, distinct from double registration within a single request.

**Explicit limitation:** In real Spring Security, `CasAuthenticationFilter` normally redirects via its success handler so the chain may not reach the second registration. The simulation illustrates the architectural risk and counting method, **not the exact execution count across every Spring release**. Real verification must check filter registrations, selected chains, and CAS `TicketValidator`/server metrics.

## 13. Integration Test: Verifying the Chain Holds Exactly One CAS Filter

In the example project, add the test dependency to `pom.xml`:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

The chain-structure check can run in a Spring Boot test configured with valid test CAS properties. Example **complete test class**:

**src/test/java/com/example/cas/CasFilterChainTest.java**

~~~java
package com.example.cas;

import java.util.List;

import jakarta.servlet.Filter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.web.FilterChainProxy;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class CasFilterChainTest {

    @Autowired
    @Qualifier("springSecurityFilterChain")
    Filter springSecurityFilterChain;

    @Test
    void callbackHasExactlyOneCasFilter() {
        FilterChainProxy proxy =
            (FilterChainProxy) springSecurityFilterChain;

        List<Filter> filters = proxy.getFilters("/login/cas");
        assertNotNull(filters, "Callback must match a security chain");

        long count = filters.stream()
            .filter(CasAuthenticationFilter.class::isInstance)
            .count();

        assertEquals(1L, count,
            "Selected chain must have exactly one CAS filter");
    }

    @Test
    void ordinaryPathIsNotAnExtraCasCallback() {
        FilterChainProxy proxy =
            (FilterChainProxy) springSecurityFilterChain;

        List<Filter> filters = proxy.getFilters("/private");
        assertNotNull(filters);
        assertEquals(1L, filters.stream()
            .filter(CasAuthenticationFilter.class::isInstance)
            .count());

        // The CAS filter sits in the chain, yet only calls attemptAuthentication
        // when the request actually matches /login/cas.
    }
}
~~~

**Limitation:** This test inspects the **security filter list of the selected chain**; it does not prove that the **Servlet container did not auto-register a filter bean**. With the sample pattern creating the filter via **`new`** without a `@Bean`, auto-registration of that instance is avoided. With the `@Bean` variant, add tests/inspections for **`FilterRegistrationBean.enabled=false`** and Servlet container filter registrations.

### 13.1. Test Counting One CAS Validation Attempt

A more decisive integration test creates a **valid test ST** on a CAS test server or trusted mock CAS endpoint, then verifies:

~~~text
Given:
  CAS user demo is authenticated,
  CAS Server issues a fresh ST for the public service URL.

When:
  Browser performs GET /login/cas?ticket=<fresh-ST> once.

Then:
  Selected SecurityFilterChain contains exactly one CasAuthenticationFilter;
  TicketValidator calls CAS /serviceValidate exactly once;
  CAS returns authenticationSuccess per protocol;
  SP persists authenticated SecurityContext;
  Browser redirects to a clean URL with no ticket.
~~~

Next, deliberately **refresh the old callback URL** and verify it fails safely or starts a new flow; the old ST must never succeed again. A second test can intentionally create **two filter registrations** in a test harness to confirm your structural/startup check catches the misconfiguration before production.

**Never mock `AuthenticationProvider` to return "always authenticated"** and claim CAS validation was tested. Chain placement tests and CAS protocol validation tests cover different scopes; include both filter-structure tests and single-invocation validator tests.

### 13.2. Async and `ERROR` Dispatches

If a test or app uses Servlet async or error pages, multiple dispatches can occur for one request. Log **`DispatcherType`** and the count of back-channel validation attempts. The goal is not forbidding all dispatches, but **never re-validating the same ST as though it were a fresh ticket**. Never rely on a `OncePerRequestFilter` wrapper as your sole patch for dual registrations; remove the duplicate registration at its root.

## 14. Negative Test Suite and QA Checklist

| Test Case | Expected Result |
| --- | --- |
| Callback `/login/cas` with fresh ST | Filter handles it once in non-duplicate setup; CAS validation succeeds |
| Browser `GET /private` after login | Restores `SecurityContext` from session; **does not re-validate ST** |
| Refresh `/login/cas?ticket=old-ST` | CAS rejects used ST; no new `Authentication` created from replay |
| Filter declared both as `@Bean` and `addFilterAt` without disabling auto-registration | Config/structural check detects duplicate; blocked from production |
| `@Bean` variant + `FilterRegistrationBean.enabled=false` | Zero Servlet auto-registrations for that CAS filter |
| Two `CasAuthenticationFilter` instances in the same chain | Structural test fails; keep exactly one instance |
| `FilterChainProxy` has API chain `@Order(1)` and browser `@Order(2)` | `/api/**` enters API chain; `/login/cas` enters browser chain |
| API chain matcher `/**` ordered ahead of browser | Test catches that callback never sees CAS filter |
| Browser chain matches only `/app/**` | `/login/cas` misses; fix matcher/URL |
| `permitAll("/login/cas")` while `securityMatcher` excludes callback | CAS still unhandled; `permitAll` does not fix selection |
| `web.ignoring("/login/cas")` | Callback bypasses Spring Security; CAS login fails |
| `ServiceProperties.service` differs from public callback URL | CAS service validation fails; never bypass |
| Reverse proxy forwards HTTPS to HTTP backend | Service URL keeps fixed public HTTPS value |
| Filter executes on two Servlet dispatches `ERROR`/`REQUEST` | Distinguish invocations from CAS validation attempts |
| CAS `/serviceValidate` times out | Never retry same ST blindly; start fresh flow when needed |
| CAS returns HTTP 200 with XML `authenticationFailure` | No `Authentication` created |
| CAS succeeds yet local user disabled | Business access denied |
| Spring Security 6 fails to save context | Test catches failure/redirect loop; wire repository properly |
| GET callback without `ticket` | No fake `Authentication`; handle error/redirect properly |
| Business POST with cookie yet no CSRF token | Rejected per CSRF policy |
| 2-node CAS Server cluster | Single-use ticket registry is atomic across CAS Server |
| Legacy filter bean from `web.xml`/`@WebFilter` remains | Clean up duplicate registration; keep one path |
| Two users log in concurrently in two sessions | Sessions/authentications isolated; no user data in mutable shared filter fields |
| Browser closes tab at CAS and reopens | No `Authentication` created without a fresh valid ST |
| Callback ticket leaked via logs/analytics | Logs sanitize query strings; raw tickets never stored |

### Suggested Automated Assertions

- **Count of `CasAuthenticationFilter` in chosen chain = 1**.
- **Count of automatic Servlet registrations of the CAS filter = 0**.
- **`TicketValidator` calls = 1** per fresh ST and single callback HTTP request.
- **`Authentication.isAuthenticated() = true`** only after CAS success response and local account acceptance.
- **`SecurityContext` persistence** works across the subsequent request.
- **`ServiceProperties.service`** matches the canonical service issued by the CAS Server.
- **Zero raw STs** appear in final redirect URLs, application logs, APM, or browser analytics.
- **No infinite redirect loop** when a valid session cookie is present.
- **CSRF and authorization** on business resources remain active.

## 15. Typical Operational Errors

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| **`CasAuthenticationFilter` appears twice in logs** | Filter bean auto-registered + `http.addFilterAt`, or separate dispatch | Check both servlet registrations and selected chain; log `dispatcherType` |
| **CAS `INVALID_TICKET` on callback** | ST already consumed; duplicate validator run, refresh, or timeout | Count CAS validation calls, check browser/proxy retries, mint fresh ST |
| **Callback skips `CasAuthenticationFilter` despite ticket** | Callback excluded by `securityMatcher`, `web.ignoring`, or wrong filter URL | Fix chain matcher and `ServiceProperties.service` |
| **CAS Service Ticket mismatch** | `http`/`https`, host, port, or path differs between `/login` and validation | Use canonical public service URL and proper proxy trust |
| **Succeeds then loops back to CAS login** | `SecurityContext` not saved, lost session, or `SameSite`/cookie error | Use `HttpSessionSecurityContextRepository` and proper session strategy |
| **403 error on callback** | Wrong security chain/CSRF/HTTP method, custom POST, or blocking rule | Check method, matcher, and CSRF policy; never disable CSRF globally |
| **CAS never called yet controller sees `ticket`** | Query reaches controller directly because filter did not match | Never authenticate in controller; fix CAS filter path |
| **Filter runs in wrong order** | Registered in outer container; `@Order` misused on Filter | Use `HttpSecurity.addFilterAt` inside the right chain |
| **`ClassNotFoundException` for CAS client** | Missing compatible `cas-client-core` module | Inspect Maven dependency tree and compatibility |
| **CAS validation OK yet user lacks access** | Local `UserDetailsService`/roles/disabled account | Separate CAS authentication from local authorization |
| **Two chains both "match" yet browser filter never runs** | `FilterChainProxy` picks first chain | Fix `@Order`/`securityMatcher` and add fallback browser chain |
| **Bug occurs only with multiple app nodes** | Unshared sessions, proxy routing callbacks, lost state | Check Spring Session/sticky sessions and cookies; CAS ticket registry separately |
| **Duplicate filter after migrating from XML** | Legacy CAS filter/`DelegatingFilterProxy` still registered | Remove old wiring; keep single `SecurityFilterChain` config |
| **CAS logout leaves local session alive** | SLO is configured separately from the CAS ST filter | Design and verify CAS `SingleSignOutFilter`/session lifecycle |
| **ST token shows up in traces** | Logs capture URL query strings and redirect headers | Mask `ticket` parameter in reverse proxy/APM/access logs |

### Shortest Diagnostic Sequence

~~~text
1. What is the CAS callback public service URL?
2. Which SecurityFilterChain owns /login/cas?
3. Do FilterChainProxy's selected filters include CasAuthenticationFilter?
4. How many CAS filter instances exist in that chain?
5. Did the Servlet container register an extra CAS filter?
6. Does CasAuthenticationFilter have the right filterProcessesUrl?
7. Does ServiceProperties.service match the CAS service registry?
8. How many times does TicketValidator call CAS on a fresh ST?
9. Does CAS return authenticationSuccess or authenticationFailure?
10. Does the local UserDetailsService accept the user?
11. Does SecurityContextRepository persist the session after login?
12. Is the browser redirected to a clean URL with no ticket?
~~~

Avoid the "just retry `/serviceValidate` again" workaround when an ST has already been used. That makes matters worse because CAS tickets are non-idempotent.

## 16. Extension Points to Consider

### 16.1. CAS Proxy Tickets / Stateless Integrations

Spring Security's **`CasAuthenticationFilter`** also supports proxy ticket flows and **`authenticateAllArtifacts`**. When tickets must be validated on URLs beyond the default callback, you must configure **`ServiceAuthenticationDetailsSource`**, a proxy `TicketValidator`, a stateless ticket cache, and strict policies. **Never turn on that mode merely to fix a filter failing to match `/login/cas`**, as it widens the set of requests that can trigger authentication.

**Stateful browser ST callbacks** and **stateless PT APIs** have distinct lifecycles. If your app already exposes Bearer/OAuth APIs, use a separate stateless chain rather than passing STs on every API request.

### 16.2. CAS Single Logout and Duplicate Filters

CAS Single Logout typically uses a CAS client filter/listener to receive logout events and invalidate sessions. That is **not** the `CasAuthenticationFilter` that validates STs. When implementing SLO, choose one registration approach and ordering explicitly so you do not auto-register a `SingleSignOutFilter` bean while also adding it into Spring Security and processing logout events twice.

**Do not fold SLO into the CAS login callback:** logout requests from the CAS Server can arrive when the user has no active SP browser request, requiring a session registry and clear policy. Even in SLO, double registration can cause duplicate invalidations/logs or wrong ordering.

### 16.3. Multiple Tenants and Multiple CAS Servers

If a service supports multiple CAS Servers or tenants, you cannot use a single service URL or let a `TicketValidator` pick a CAS Server from an arbitrary query parameter. Choose the **trusted CAS configuration** per approved tenant/route, maintain distinct canonical service URLs, and link local accounts to the corresponding issuer/CAS authority. With multiple chains, each tenant's callback must match the right chain with a single filter/validator per policy.

If two chains share a callback path pattern yet target different CAS Servers, differentiate them reliably by route, host/tenant, and state. Never guess the issuing CAS server from the **`ST-...`** ticket string.

## 17. Production Checklist

- [ ] Defined the exact **CAS service callback** and canonical HTTPS URL, permitted by the CAS Server registry.
- [ ] **`CasAuthenticationFilter`** resides solely in the intended **`SecurityFilterChain`**, with zero container auto-registration.
- [ ] If the filter must be a bean, **`FilterRegistrationBean.enabled=false`** is set and all legacy servlet registrations are removed.
- [ ] Matching chain includes the CAS filter for **`/login/cas`**, not swallowed by a higher-priority chain.
- [ ] Clear distinction between **`securityMatcher`** (chain selection) and **`requestMatchers`** (in-chain authorization).
- [ ] Neither **`web.ignoring("/login/cas")`** nor placing the CAS filter after authorization is used.
- [ ] Filter is not added twice at the same slot via DSL, `addFilterAt`, or legacy XML.
- [ ] **`ServiceProperties.service`** and **`filterProcessesUrl`** align with the public URL for which the CAS Server issues STs.
- [ ] **`CasAuthenticationEntryPoint`, `CasAuthenticationProvider`, and `TicketValidator`** share the same trusted CAS Server/service config.
- [ ] **`authenticateAllArtifacts=false`** for normal browser STs unless an explicit proxy design exists.
- [ ] **`SecurityContextRepository`/`HttpSession`** saves `Authentication` after callback, with proper session fixation protection.
- [ ] One-time STs are validated once; never retry the same ST after error or timeout.
- [ ] After CAS validation succeeds, redirect to a clean URL so subsequent browser requests use the SP session.
- [ ] CSRF protection for application state changes is not disabled for the CAS callback.
- [ ] Logs, APM, proxies, and browsers never retain raw STs; sanitized correlation IDs are used.
- [ ] Tests verify chain structure, container registrations, `TicketValidator` invocation count, session persistence, and replay.
- [ ] Multi-chain tests with `/api/**` and `/login/cas` confirm `@Order` does not swallow the callback.
- [ ] Tests cover browser retries, `ERROR`/`ASYNC` dispatches, wrong service URLs, disabled local accounts, and DB/CAS timeouts.
- [ ] Migration plan exists if the project has legacy CAS XML, external container filters, or older Spring Security versions.
- [ ] Successful CAS authentication is never equated with business authorization; local accounts, roles, and tenants are always checked.

**Conclusion:** To prevent duplicate request processing in Spring Security CAS, place **one `CasAuthenticationFilter` at the right authentication slot in `SecurityFilterChain`**, ensure **`FilterChainProxy` selects the right chain for `/login/cas`**, and prevent Spring Boot from registering that filter a second time with the Servlet container. Combined with **single-use CAS Service Tickets**, canonical service URLs, `SecurityContext` persistence, and validation-attempt counting tests, your application will maintain a verifiable CAS login flow free of replay errors and redirect loops.

## 18. References

- [Spring Security 6.5 – Servlet Security Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, filter ordering, and `Filter` bean auto-registration warnings.
- [Spring Security 6.5 – Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `securityMatcher` vs. `requestMatchers` and first-matching `SecurityFilterChain`.
- [Spring Security – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CAS filter/provider/entry point, callback URLs, and stateful vs. stateless CAS tickets.
- [Spring Security 6.5 – CasAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): callback path, ticket processing, `serviceProperties`, and `securityContextRepository`.
- [Spring Security 6.5 – CasAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): provider settings, local `UserDetailsService`, and `TicketValidator`.
- [Spring Security 6.5 – FilterChainProxy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/FilterChainProxy.html): first-match chain selection, firewalling, and filter lifecycle.
- [Spring Boot – Servlet Filters / FilterRegistrationBean](https://docs.spring.io/spring-boot/reference/web/servlet.html): Servlet filter bean auto-registration and controlling filter registrations.
- [CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service-ticket one-time validation and service binding.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, session lifecycle, and cookie security.
