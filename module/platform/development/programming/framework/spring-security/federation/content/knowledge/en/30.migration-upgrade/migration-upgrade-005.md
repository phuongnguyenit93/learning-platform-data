# Migrating CAS Clients and Filters to Jakarta Servlet-Compatible Libraries

> **Module:** Spring Security – federation · **Group:** Migration and Upgrade. Guide to migrating an application currently using **Apereo Java CAS Client 3.x**, `javax.servlet.*`, `web.xml`/Servlet filters, and sometimes `spring-security-cas` to **Jakarta Servlet** on Spring Boot 3/4 or modern Servlet containers. The goal is not just compiling: CAS service tickets must still be validated once against the **exact service URL**; filter chains must have a safe order; CAS Single Logout (SLO), sessions, and Spring `SecurityContext` must not be bypassed; and endpoints/cookies/TLS must work behind reverse proxies. Includes a JDK and framework dependency map, Java/XML fragments, testing procedures, and **a standalone-compilable/runnable Java 17 demo** to audit migration policy. URIs and users in this article are illustrative examples containing no real secrets.

## 1. Why Does Upgrading Spring Boot Break a Working CAS Client?

Legacy applications typically look like:

```text
Java 8/11/17
  |
  +-- Spring Framework 5 / Spring Boot 2
  |      Servlet API: javax.servlet.*
  |
  +-- Apereo Java CAS Client 3.x
  |      AuthenticationFilter
  |      Cas20/Cas30...TicketValidationFilter
  |      SingleSignOutFilter
  |      SingleSignOutHttpSessionListener
  |
  +-- Servlet container like Tomcat 9
         implements javax.servlet.* API
```

When moving to Spring Boot 3 / Spring Framework 6 or a Jakarta container (e.g., Tomcat 10.1):

```text
Spring Boot 3 / Spring Framework 6
  |
  +-- Jakarta Servlet 6.0: jakarta.servlet.*
  |
  +-- Application custom filters require jakarta.servlet.Filter
  |
  +-- CAS client 3.x compiled against javax.servlet.Filter
          |
          +-- cannot be used as jakarta.servlet.Filter
          +-- ClassNotFoundException / NoClassDefFoundError
          +-- ClassCastException / BeanCreationException
          +-- FilterRegistrationBean generic type mismatch
```

`javax.servlet.Filter` and `jakarta.servlet.Filter` **are two distinct Java types**, despite similar signatures and method names. Changing `import javax.servlet.*` in application code does not convert the bytecode of an old `cas-client-core` library into Jakarta classes. Moreover, CAS can fail logically even when the app starts: wrong service callback URL, double filter registration, logout callbacks blocked by the CSRF filter, or lost session indices in multi-pod deployments.

**Article scope:** CAS protocol (CAS 2/3 service-ticket login, optionally CAS SAML 1.1, proxy tickets, SLO). Do not conflate CAS client filters with Spring Security **SAML2 Web SSO**; CAS and SAML2 can coexist at the IdP, yet their tokens, callbacks, and validation profiles differ.

### 1.1. Learning Outcomes

After this lesson, you can:

1. Assess JDK–Spring Boot–Servlet–CAS client compatibility before changing dependencies.
2. Replace `javax.servlet` with `jakarta.servlet` in app code, filters, and listeners, and audit transitive dependencies.
3. Choose among **Apereo CAS servlet filters**, **Spring Security CAS AuthenticationProvider/Filter**, or **Apereo Spring Boot integration** per architecture, avoiding duplicate authentication.
4. Convert `web.xml` or `FilterRegistrationBean` registrations while keeping **`SingleSignOutFilter` before other CAS filters**.
5. Verify CAS ticket validation, exact service URL matching, TLS, and service callbacks through proxies.
6. Handle `HttpServletRequestWrapperFilter`, `AssertionThreadLocalFilter`, character encoding filters, and `SingleSignOutHttpSessionListener` lifecycles where still used.
7. Avoid duplicate `springSecurityFilterChain`/Servlet container filter registrations.
8. Design cluster-compatible SLO, handling cookies, session fixation, and Redis/Spring Session.
9. Write migration tests that detect mixed `javax.servlet-api`/`jakarta.servlet-api`, legacy CAS clients, wrong filter order, missing listeners, wrong service URLs, and ticket replay.
10. Plan canary deployments, rollbacks, alerts, and post-deployment verification.

## 2. Clearly Identify Which Architecture Uses the CAS Client

Three configuration patterns appear in legacy systems:

| Architecture | Core Components | Actual Auth Mechanism |
| --- | --- | --- |
| **A — Pure Apereo Java CAS Client Filters** | `AuthenticationFilter`, `Cas30ProxyReceivingTicketValidationFilter`, request wrapper, SLO filter/listener | CAS library validates ticket and stores assertion in request/session; app consumes principal/attributes |
| **B — Spring Security CAS Integration** | `CasAuthenticationFilter`, `CasAuthenticationProvider`, `CasAuthenticationEntryPoint`, `ServiceProperties`, CAS TicketValidator | Spring Security manages `Authentication`/`SecurityContext`/roles; ticket is validated by provider |
| **C — Apereo CAS Spring Boot Support** | `cas-client-support-springboot`, `@EnableCasClient`, and `cas.*` config | Module auto-registers CAS client filters/listeners per config; app must still bridge authorization/security |

If a project has **both** `org.apereo.cas.client.authentication.AuthenticationFilter` and `org.springframework.security.cas.web.CasAuthenticationFilter` handling the same callback/service ticket, **double redirects / double ticket validation** easily happen. CAS service tickets are typically **single-use**: the first filter validates successfully, the second reuses the same ticket and fails, causing login loops and intermittent errors.

**Before migrating, choose one primary owner of the CAS callback request.** You may keep Apereo's `SingleSignOutFilter`/listener alongside Spring Security CAS if designed and tested, but never enable both full authentication stacks simultaneously.

### 2.1. Do Not Turn a "Dependency Upgrade" into a "Protocol Switch"

- CAS `/login?service=...` returning the browser with query `ticket=ST-...` is the **CAS service-ticket flow**.
- SAML 2.0 Web SSO delivers a `SAMLResponse` to an ACS and verifies XML signatures/Assertions.
- The CAS SAML 1.1 validator (`Saml11TicketValidationFilter`) is a CAS client protocol variant; it is **not** automatically compatible with Spring Security `saml2Login()`.
- OIDC uses authorization codes, ID Tokens, and JWKS/nonce/PKCE, which differ from CAS service-ticket validation.
- If a project wants to replace CAS with OIDC/SAML2, that is a **new authentication migration** with its own trust, session, logout, claims, and compatibility plan—outside the scope of merely changing the Servlet API.

### 2.2. Inventory Before Editing

Build a table from the *running configuration*, not outdated docs:

| Area to Audit | Questions to Answer |
| --- | --- |
| Runtime | Actual JDK, servlet container/embedded Tomcat/Jetty, WAR or executable JAR? |
| Framework | Spring Boot 2.x, 3.x, or 4.x? Spring Security version? |
| CAS libraries | Which `cas-client-core` version, is `spring-security-cas` present, legacy transitives? |
| Filter registration | `web.xml`, `@WebFilter`, `@EnableCasClient`, `FilterRegistrationBean`, `HttpSecurity.addFilter...`? |
| CAS service | `casServerUrlPrefix`/`casServerLoginUrl`/`serverName`/`service`, actual callback URI and proxy host? |
| Ticket validation | CAS 1/2/3? CAS20/30 validator? Proxy tickets/PGT? Timeout/TLS? |
| SLO | `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, callback path, session registry, cluster? |
| Security context | What constructs `Authentication`/principal and assigns authorities? |
| HTTP edges | Ingress forwarded headers, cookie SameSite/Domain/Path, CSRF, redirects, logout POST? |
| Tests | Positive login, invalid/replayed ticket, local/multi-node SLO, filter counts/order, failover? |

Every migration should establish **baseline behavior** in a test environment before changing libraries.

## 3. Version Matrix: Do Not Pick 4.1.x Just Because It Is Newer

Per Maven Central POMs inspected in November 2026, Apereo Java CAS Client **4.0.4** uses `jakarta.servlet-api` 6.0 and a Java **17** baseline with Spring Boot 3 / Spring Framework 6 generation dependencies. CAS Client **4.1.1** is also Jakarta, yet its POM specifies Java **21**, Servlet **6.1**, and dependencies aligned with Spring Boot 4 / Spring Framework 7.

| Application Line | CAS Client to Evaluate | Minimum JDK by Branch | Notes |
| --- | --- | --- | --- |
| Legacy Spring Boot 2 / Tomcat 9 | Legacy Apereo CAS Client 3.x | Per legacy release | `javax.servlet.*`, not yet Jakarta |
| Spring Boot 3 / Tomcat 10.1 / Spring 6 | Apereo CAS Client 4.0.x Jakarta, e.g., 4.0.4 | 17 | Test with specific Spring Boot BOM, SLO/security/bugs, and supported patches |
| Spring Boot 4 / Spring 7 / Servlet 6.1 | Apereo CAS Client 4.1.x Jakarta, e.g., 4.1.1 | 21 | Verify both Boot/CAS artifacts and release compatibility |
| WAR deployed to external container | CAS client must match container's Jakarta Servlet generation | Per artifact/container | Never bundle duplicate `servlet-api` |
| Spring Security CAS integration | `spring-security-cas` matching Spring Security major, compatible CAS protocol validator | Per Spring Security version | **Never** mix new CAS provider with `cas-client-core` 3.x |

**Caution:** This table provides **verifiable dependency milestones**, not a guarantee that every patch combination works. Check the chosen artifact's build POM/BOM, release notes, CVEs, and CI. If the app **requires Java 17**, do not pick CAS Client 4.1.1 requiring Java 21 while merely setting `maven.compiler.release=17`; bytecode and library dependencies can still demand a Java 21 runtime.

### 3.1. Why Do Mixed Versions Cause Silent Failures?

Suppose:
- `cas-client-core:3.6.4` from legacy.
- `cas-client-support-springboot:4.1.1` from a new module.
- `spring-security-cas` from another Spring 6/7 branch.
- Boot 3's embedded Servlet API is Jakarta.

The build may pick an unexpected classpath version via dependency mediation; one module imports `javax.servlet.Filter` while another imports `jakarta.servlet.Filter`. At runtime it blows up with `NoClassDefFoundError: javax/servlet/Filter`, the CAS authentication filter fails to register, or tickets get validated twice.

**Rule:** lock **one tested set of versions** via BOM/dependency management; never override Spring Framework/Security/Tomcat arbitrarily just to "get past compile."

### 3.2. Inspect Maven and Gradle Before Editing Code

Maven:

```bash
mvn -q -DskipTests dependency:tree
mvn -q help:effective-pom
mvn -q -DskipTests clean package
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency cas-client-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
./gradlew test
```

Search for **javax.servlet**, **jakarta.servlet**, `cas-client-core` versions, `spring-security-cas`, `tomcat-embed-core`, and transitive modules. A module with `javax` in a package name **is not always an error** (many Java SE standards still use `javax.crypto`/`javax.net.ssl`); focus specifically on `javax.servlet.*`/`javax.annotation.*` belonging to Jakarta migration and the actual types in use.

### 3.3. Distinguish API from Implementation

- `jakarta.servlet:jakarta.servlet-api` is only the **Servlet API**; Tomcat/Jetty implements it.
- Embedded Spring Boot normally supplies the matching container via starters.
- When building a WAR for an external server, servlet API should be in **provided** scope so two implementations aren't packaged in the WAR.
- Never add `javax.servlet-api` to "supply missing classes" for CAS client 3.x alongside a Jakarta runtime; that only creates two Java type worlds **that cannot be cast across**.
- Do not rely on bytecode transformers/shading as a long-term workaround when official Jakarta artifacts exist; if forced to use temporary bytecode transformation, test binary compatibility, filter init/async/session/listeners, and security regressions rather than assuming bytecode rewriting completes the migration.

## 4. From javax.servlet to jakarta.servlet — What Exactly Changes?

### 4.1. Common Namespace Mapping Table

| Before Upgrade | After Upgrade |
| --- | --- |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| `javax.servlet.FilterChain` | `jakarta.servlet.FilterChain` |
| `javax.servlet.FilterConfig` | `jakarta.servlet.FilterConfig` |
| `javax.servlet.ServletRequest` | `jakarta.servlet.ServletRequest` |
| `javax.servlet.ServletResponse` | `jakarta.servlet.ServletResponse` |
| `javax.servlet.ServletException` | `jakarta.servlet.ServletException` |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` |
| `javax.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` |
| `javax.servlet.http.HttpSessionEvent` | `jakarta.servlet.http.HttpSessionEvent` |
| `javax.servlet.http.HttpSessionListener` | `jakarta.servlet.http.HttpSessionListener` |
| `javax.servlet.annotation.WebFilter` | `jakarta.servlet.annotation.WebFilter` |
| `javax.servlet.annotation.WebListener` | `jakarta.servlet.annotation.WebListener` |
| `javax.servlet.DispatcherType` | `jakarta.servlet.DispatcherType` |

**Do not** replace `javax.crypto` or `javax.net.ssl` with `jakarta`: they belong to Java SE and remain `javax.*`. Never blind-search-and-replace every `javax`.

### 4.2. Custom Filter After Migration

```java
package example.security;

import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class RequestAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        // Example only. Never log the CAS ticket or session cookie.
        chain.doFilter(request, response);
    }
}
```

The fragment above **compiles when Jakarta Servlet API is on the classpath**, but does not run standalone with JDK 17 alone. It illustrates the right imports/interface and contains no CAS authentication logic. For filters needing `init(FilterConfig)`/`destroy()` or dispatcher handling, test the full lifecycle; updating Java source imports is insufficient if utility libraries on the classpath still use `javax`.

### 4.3. HttpSessionListener After Migration

```java
package example.security;

import jakarta.servlet.http.HttpSessionEvent;
import jakarta.servlet.http.HttpSessionListener;

public final class SessionCleanupListener
        implements HttpSessionListener {
    @Override
    public void sessionDestroyed(HttpSessionEvent event) {
        // Application-specific cleanup of non-sensitive indexes.
        // Keep CAS client listener separately if its SLO mapping uses it.
    }
}
```

A custom listener like this **does not replace** Apereo's `SingleSignOutHttpSessionListener`; Apereo's listener cleans up its SLO mapping. When moving from `web.xml` to Boot registration, verify both listeners are registered **once each** and actually fire on session expiry/invalidation.

### 4.4. web.xml Jakarta Namespace

For a Jakarta Servlet 6.0 WAR, the descriptor follows the Jakarta schema:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      https://jakarta.ee/xml/ns/jakartaee
      https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

  <filter>
    <filter-name>cas-single-sign-out</filter-name>
    <filter-class>org.apereo.cas.client.session.SingleSignOutFilter</filter-class>
    <init-param>
      <param-name>logoutCallbackPath</param-name>
      <param-value>/cas/logout/callback</param-value>
    </init-param>
  </filter>
  <filter-mapping>
    <filter-name>cas-single-sign-out</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>

  <filter>
    <filter-name>cas-auth</filter-name>
    <filter-class>org.apereo.cas.client.authentication.AuthenticationFilter</filter-class>
    <init-param>
      <param-name>casServerUrlPrefix</param-name>
      <param-value>https://sso.example.org/cas</param-value>
    </init-param>
    <init-param>
      <param-name>serverName</param-name>
      <param-value>https://portal.example.org</param-value>
    </init-param>
  </filter>
  <filter-mapping>
    <filter-name>cas-auth</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>

  <filter>
    <filter-name>cas-validate</filter-name>
    <filter-class>
      org.apereo.cas.client.validation.Cas30ProxyReceivingTicketValidationFilter
    </filter-class>
    <init-param>
      <param-name>casServerUrlPrefix</param-name>
      <param-value>https://sso.example.org/cas</param-value>
    </init-param>
    <init-param>
      <param-name>serverName</param-name>
      <param-value>https://portal.example.org</param-value>
    </init-param>
  </filter>
  <filter-mapping>
    <filter-name>cas-validate</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>

  <listener>
    <listener-class>
      org.apereo.cas.client.session.SingleSignOutHttpSessionListener
    </listener-class>
  </listener>
</web-app>
```

**This descriptor illustrates the order SLO → authentication → validation**, not a complete deployment. It omits request wrapper/`AssertionThreadLocalFilter`, Spring Security filter chain, exact service callback, public health exclusions, security headers, scoped CSRF exceptions, CAS server registered service, TLS, and session clustering. `Cas30ProxyReceivingTicketValidationFilter` enables proxy validation policy only when explicitly configured; never set `acceptAnyProxy=true` without a trust contract.

### 4.5. When Should You Still Keep web.xml?

WARs deployed to external Tomcat or WebSphere/Liberty may require the descriptor; keeping `web.xml` is sensible when the runtime supports Jakarta and the configuration is verified. Spring Boot executable JARs generally favor Java configuration/`FilterRegistrationBean`. **Never enable `web.xml` + `@WebFilter` + `FilterRegistrationBean` simultaneously for the same CAS filter.**

## 5. Changing Dependencies: Maven Examples for Two Paths

### 5.1. Path Java 17 + Spring Boot 3 (Evaluate CAS Client 4.0.4)

```xml
<!-- pom.xml fragment; Boot BOM/parent manages Spring/Tomcat versions. -->
<dependency>
  <groupId>org.apereo.cas.client</groupId>
  <artifactId>cas-client-core</artifactId>
  <version>4.0.4</version>
</dependency>
```

Use `cas-client-core`, **not** the `cas-client` POM aggregator as if it held filter classes. When CAS SAML 1.1 support, proxy ticket cache, or Apereo Boot integration is needed, add the exact needed artifacts from the **same version branch**.

### 5.2. Path Java 21 + Spring Boot 4 (Evaluate CAS Client 4.1.1)

```xml
<!-- Fragment for applications meeting Java 21 / Boot 4 baseline. -->
<dependency>
  <groupId>org.apereo.cas.client</groupId>
  <artifactId>cas-client-core</artifactId>
  <version>4.1.1</version>
</dependency>
```

The 4.1.1 POM is published with `project.build.sourceVersion=21`. Never advertise 4.1.1 as a drop-in for Java 17. On Spring Boot 3 Java 17, evaluate CAS Client 4.0.x with security fixes; if an unbackported security risk exists, make an approved risk decision or upgrade the runtime rather than picking an incompatible library.

### 5.3. Apereo CAS Spring Boot Support

Apereo's README describes the module:

```xml
<dependency>
  <groupId>org.apereo.cas.client</groupId>
  <artifactId>cas-client-support-springboot</artifactId>
  <version>4.1.1</version>
</dependency>
```

Documented properties:

```properties
cas.server-url-prefix=https://sso.example.org/cas
cas.server-login-url=https://sso.example.org/cas/login
cas.client-host-url=https://portal.example.org
```

With `@EnableCasClient`, the module can auto-register authentication/validation/SLO filters. **Choose one or the other:** use the module to auto-register, **or** declare `FilterRegistrationBean`s manually; never enable both. Specifically, module 4.1.1 must be tested against Boot 4/JDK 21; never copy `@EnableCasClient` onto a 4.0.x project assuming identical APIs.

### 5.4. Jakarta Servlet API Dependency

Example WAR build with Jakarta Servlet 6.0:

```xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <scope>provided</scope>
</dependency>
```

Version is managed by the framework BOM/container policy. For executable Boot JARs, you normally **do not declare the servlet API directly**, because the web starter/container supplies it. Never add `javax.servlet-api` as a workaround.

### 5.5. Dependency Tree Fail Gate

To prevent legacy filters from slipping into runtime:

```text
FAIL migration gate if runtimeClasspath contains:
  javax.servlet:javax.servlet-api
  cas-client-core 3.x used in Jakarta request pipeline
  custom filter compiled as javax.servlet.Filter
  obsolete javax.servlet-dependent add-on
  two incompatible CAS client core versions

PASS only after verifying:
  jakarta servlet filter classes compile and load
  chosen CAS client matches JDK and Boot generation
  only one owner for CAS ticket authentication
  SLO listener/filter lifecycle registered and tested
```

You can use Maven Enforcer `bannedDependencies` to ban `javax.servlet-api` (Apereo's source POM also includes rules excluding legacy deps) and fail CI when the dependency tree is wrong. **Never ban all `javax.*`** since Java SE/JNDI/crypto still use that namespace.

## 6. Spring Boot 3: Registering Apereo Filters with FilterRegistrationBean

If the app chooses **Architecture A — pure Apereo filters**, use `FilterRegistrationBean` to control order/URLs/init params instead of servlet `web.xml`. The configuration below illustrates Spring Boot 3 / Jakarta Servlet APIs, without full authentication/authorization integration.

```java
package example.cas;

import org.apereo.cas.client.authentication.AuthenticationFilter;
import org.apereo.cas.client.validation
        .Cas30ProxyReceivingTicketValidationFilter;
import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasJakartaFilterConfiguration {

    private static final String CAS =
            "https://sso.example.org/cas";
    private static final String PUBLIC_ORIGIN =
            "https://portal.example.org";

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilter() {
        var registration = new FilterRegistrationBean<>(
                new SingleSignOutFilter());
        registration.setName("cas-single-sign-out");
        registration.addUrlPatterns("/*");
        registration.addInitParameter(
                "logoutCallbackPath", "/cas/logout/callback");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    FilterRegistrationBean<AuthenticationFilter> casAuthentication() {
        var registration = new FilterRegistrationBean<>(
                new AuthenticationFilter());
        registration.setName("cas-authentication");
        registration.addUrlPatterns("/*");
        registration.addInitParameter(
                "casServerUrlPrefix", CAS);
        registration.addInitParameter(
                "serverName", PUBLIC_ORIGIN);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return registration;
    }

    @Bean
    FilterRegistrationBean<Cas30ProxyReceivingTicketValidationFilter>
            casTicketValidation() {
        var registration = new FilterRegistrationBean<>(
                new Cas30ProxyReceivingTicketValidationFilter());
        registration.setName("cas-ticket-validation");
        registration.addUrlPatterns("/*");
        registration.addInitParameter(
                "casServerUrlPrefix", CAS);
        registration.addInitParameter(
                "serverName", PUBLIC_ORIGIN);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 30);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSessionListener() {
        return new ServletListenerRegistrationBean<>(
                new SingleSignOutHttpSessionListener());
    }
}
```

**Treat this example as a conditional configuration fragment:** it requires a Jakarta `cas-client-core` version, Boot web starter and Jakarta Servlet runtime, an explicit filter strategy, matching CAS registered service URL/port/context path, and a CAS server that genuinely invokes the SLO logout callback. A production setup also needs request wrapper/`AssertionThreadLocalFilter` per use case, login-loop fallback handling, protected URL rules, local authority mapping, health endpoints, CSRF for user-initiated logout, cookies/TLS, and distributed sessions.

### 6.1. Why Specify Order Explicitly?

Spring Boot's `FilterRegistrationBean.setOrder(int)` controls ordering in the **container filter chain**. In the example:

```text
CAS SingleSignOutFilter      order = HIGHEST_PRECEDENCE + 10
CAS AuthenticationFilter     order = HIGHEST_PRECEDENCE + 20
CAS TicketValidationFilter   order = HIGHEST_PRECEDENCE + 30
... request wrapper, Spring Security/DispatcherServlet as configured
```

**Note:** lower order numbers run earlier. Apereo's README requires `SingleSignOutFilter` to sit **before the remaining CAS filters** when using web filters. The authentication/validation ordering fits common client setups, yet must be verified end-to-end with your chosen version and filter features. If a filter reads the logout POST body, place the charset/encoding filter per documented requirements to avoid misparsing; never force every filter to `Ordered.HIGHEST_PRECEDENCE` without analyzing lifecycle.

### 6.2. Do Not Register the Same Instance Twice

A `Filter` declared as a `@Bean` may be auto-registered by Spring Boot as a Servlet container filter. If a developer also adds that filter via `http.addFilterBefore(...)`, it can execute twice: once outside `springSecurityFilterChain` and once inside. The Spring Security reference recommends **disabling container registration** if the filter belongs only in `SecurityFilterChain`:

```java
// Fragment when a custom filter should run ONLY INSIDE SecurityFilterChain.
@Bean
FilterRegistrationBean<MySecurityFilter> noContainerAutoRegistration(
        MySecurityFilter filter) {
    var bean = new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
```

`MySecurityFilter` is a hypothetical custom type, not a CAS class. Choose ownership clearly: **container filter** or **Spring Security filter**, never unintentionally both. If using `FilterRegistrationBean` as in Section 6 to register CAS filters directly at the container level, **do not** add those same filters again to `HttpSecurity`.

### 6.3. Servlet Registration Order vs. SecurityFilterChain Order Are Two Different Things

`FilterRegistrationBean.setOrder` controls the **container chain**. `http.addFilterBefore/After` controls order **inside Spring Security's FilterChainProxy**. Never look at a CAS filter's order number and assume it runs before `AuthorizationFilter` if registration happens in a different chain or dispatcher type.

Use bounded startup logs, sanitized `FilterChainProxy` debug traces, and real integration tests to confirm:
- SLO callback hits the exact filter once.
- CAS ticket is validated once.
- Protected routes check principal + local roles.
- Session invalidation and `SecurityContext` clearing work.
- Failures never produce a bogus anonymous→authenticated context.
- No infinite redirect chains occur.

## 7. Spring Security CAS: When Not Using the Full Apereo Filter Stack

If the application already uses `spring-security-cas` and Spring `SecurityContext` as its authentication/authorization source, keep the model consistent:

```text
Spring Security FilterChainProxy
  |
  +-- CAS entry point redirects to CAS /login?service=...
  +-- CasAuthenticationFilter receives ticket at callback
  +-- CasAuthenticationProvider validates ticket
  |     via CAS TicketValidator (Apereo client API)
  +-- creates authenticated CasAuthenticationToken
  +-- local authorities / role mapping
  +-- SecurityContext/session
```

Classes described in Spring Security CAS docs:

- `org.springframework.security.cas.web.CasAuthenticationFilter`;
- `org.springframework.security.cas.authentication.CasAuthenticationProvider`;
- `org.springframework.security.cas.web.CasAuthenticationEntryPoint`;
- `org.springframework.security.cas.ServiceProperties`;
- `org.apereo.cas.client.validation.Cas20ServiceTicketValidator` and other TicketValidators.

This is **different** from `org.apereo.cas.client.authentication.AuthenticationFilter`; both are named "CAS authentication" yet have different owners and request chains.

### 7.1. Points to Reconfigure

1. `CasAuthenticationEntryPoint` uses the right CAS server `loginUrl` and canonical `ServiceProperties.service` URL.
2. `CasAuthenticationFilter` processes **only the registered callback path** and passes the service ticket to `AuthenticationManager`.
3. `CasAuthenticationProvider` uses a `TicketValidator` pointing to the **trusted CAS server** over HTTPS with the matching service URL and registered service.
4. `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` (per release) maps CAS principal/attributes to local authorities; never trust an email by default.
5. Local account LOCKED/DISABLED status and tenant roles must still be enforced after ticket validation.
6. `SecurityContextRepository`, session fixation protection, and `LogoutFilter` work compatibly with the Spring Security version.
7. CAS `SingleSignOutFilter` (if needed) may be placed outside/before the auth chain per documented integration; verify session indexing and listener.
8. Do not keep Apereo `AuthenticationFilter` + `TicketValidationFilter` on the exact callback handled by the Spring CAS filter.

### 7.2. Why Not Copy Spring Security 3.x XML Namespace Config?

Spring Security CAS docs contain snippets like:

```xml
<security:http entry-point-ref="casEntryPoint">
  <security:custom-filter position="CAS_FILTER" ref="casFilter"/>
</security:http>
```

This is historical Spring Security XML configuration syntax, **not** a pattern to copy into Spring Security 6/7; class names and Jakarta dependencies must be verified for the target release. Do not take `cas-client-core:3.1.12` from a historical doc table as the standard for Boot 4. Run compile/integration tests to verify `spring-security-cas` supports your exact Spring Security major.

### 7.3. Compatibility Between Spring Security CAS and Apereo Versions

Spring Security CAS calls Java CAS client APIs during ticket validation. When upgrading Spring 5→6/7 and CAS client 3→4 together, **binary incompatibility** risks arise from:
- `javax.servlet` vs. `jakarta.servlet` packages in implementations/filters.
- Changed API signatures/constructors between Apereo 3.x and 4.x.
- Spring Security filter/session repository API changes.
- Overridden transitive Spring dependencies.
- Duplicate filters in startup container registries.

Therefore, enforce **dependency convergence, compile, and integration tests on real artifacts**, rather than relying on doc prose. If a specific CAS module doesn't run on the new stack, consider pure Apereo Jakarta servlet filters + a controlled bridge, or planning a federation move to OIDC/SAML2. Never write a custom filter that "just trusts the ticket string" to bypass the validator.

## 8. The CAS Service URL Must Match End-to-End

### 8.1. CAS Service Ticket Flow

```text
Browser -> SP /reports
  SP redirects -> https://sso.example.org/cas/login
       ?service=https%3A%2F%2Fportal.example.org%2Fcas%2Fcallback

CAS authenticates user
  CAS issues one-time Service Ticket ST-X
  CAS redirect ->
       https://portal.example.org/cas/callback?ticket=ST-X

SP TicketValidator (server-to-server HTTPS)
  GET https://sso.example.org/cas/p3/serviceValidate
      ?service=https%3A%2F%2Fportal.example.org%2Fcas%2Fcallback
      &ticket=ST-X

CAS returns valid principal/attributes for matching service
  SP establishes local authentication/session
```

The `/p3/serviceValidate` endpoint is only an example of the CAS 3 protocol; CAS 2 uses `/serviceValidate`, CAS 1 uses `/validate`, and proxy validation uses `/proxyValidate` depending on validator/protocol. **Never hardcode an endpoint that disagrees with your TicketValidator implementation.**

### 8.2. Not Just Hostname: Exact Service URL Match

A ticket issued by CAS for service `https://portal.example.org/cas/callback` is typically **invalid** when the SP validates using:
- `http://portal.example.org/cas/callback` (missing HTTPS),
- `https://portal.example.org:443/cas/callback` (different canonicalization per policy),
- `https://portal.example.org/internal/cas/callback`,
- `http://127.0.0.1:8080/cas/callback`,
- `https://portal.example.org/cas/callback/` (trailing slash if CAS does not normalize).

CAS's service registry also has rules/regexes and canonicalization; **test with the real value matching the IdP config** rather than claiming every CAS always compares raw strings identically in every deployment.

### 8.3. Reverse Proxies and Forwarded Headers

Behind ingress, the SP sees internal `http://pod:8080` while the browser uses `https://portal.example.org`. Configure `serverName` or `service` to the approved public URL across redirects, callbacks, and ticket validators. If using forwarded headers, accept them only from **trusted ingress** and strip user-supplied `X-Forwarded-Host/Proto`. Never let an attacker pick the service URL via `?service=...`.

### 8.4. Prefer a Single Fixed Service URL When Possible

For multi-route apps, a canonical `/cas/callback` service callback reduces redirect mismatches and ticket validation errors. After validation, restore the saved request/target via **server-side safe redirect state** rather than accepting arbitrary external URLs from the client. If the CAS service parameter varies across requests due to query params, enforce consistent normalization and validation.

### 8.5. Tickets Are Short-Lived, Single-Use Bearer Artifacts

A CAS Service Ticket can be used by an attacker if leaked before validation. Therefore:
- Protect with HTTPS; never log raw `ticket` values in access logs or tracing.
- Validate only against the trusted CAS server and exact expected service.
- Never accept an already-used ticket; replays must fail.
- After validation, redirect to a clean URL without the ticket if client config supports it, preventing `Referer` leaks.
- Never create a new session from a `ticket` query param without calling CAS `TicketValidator`.
- Never accept Proxy Tickets arbitrarily when the app is permitted only Service Tickets.
- Never disable hostname verification or certificate validation when CAS rotates certificates.

## 9. Choose the Right Cas20/Cas30 Validation Filter for the Protocol

Apereo Java CAS Client provides several filters:

| Filter | Purpose |
| --- | --- |
| `Cas10TicketValidationFilter` | CAS 1.0 ticket protocol |
| `Cas20ProxyReceivingTicketValidationFilter` | CAS 2.0 ticket validation, optional proxy support |
| `Cas30ProxyReceivingTicketValidationFilter` | CAS 3.0 ticket validation / attributes support |
| `Cas30JsonProxyReceivingTicketValidationFilter` | JSON-formatted CAS3 validation response |
| `Saml11TicketValidationFilter` | CAS-compatible SAML 1.1 validation, not SAML2 SSO |
| `CasJWTTicketValidationFilter` | CAS server-issued JWT ticket profile with distinct trust rules |

The Java package is typically `org.apereo.cas.client.validation.*`. **Do not switch Cas20→Cas30 automatically** just because Java was upgraded; the protocol response parser and IdP server capabilities must match.

### 9.1. Example Init Params

```properties
casServerUrlPrefix=https://sso.example.org/cas
serverName=https://portal.example.org
redirectAfterValidation=true
useSession=true
exceptionOnValidationFailure=true
```

These property names come from Apereo CAS client filter documentation; verify defaults for your exact version. `redirectAfterValidation` supports clean ticket URLs; `useSession` stores the assertion in `HttpSession` when enabled. If running behind a reverse proxy, test real URLs and forwarded headers.

### 9.2. Proxy Tickets Are Especially Dangerous When Over-Trusted

An application needing only login should never set `acceptAnyProxy=true`. When the business requires PGT/PT:
- Define a trusted proxy chain / `allowedProxyChains`.
- `proxyCallbackUrl` must be valid public HTTPS matching `proxyReceptorUrl`.
- The backend validator must verify the proxy chain/PGT and callback ownership.
- PGT state is stored in a protected store with explicit TTL and revocation.
- Test that invalid/unapproved proxy chains are rejected.
- Never place PGT/PT in logs or client-side storage.

### 9.3. Do Not Confuse CAS SLO with SAML2 SLO

Apereo CAS `SingleSignOutFilter` handles `logoutRequest` callbacks; CAS logout messages may use XML/SAML namespaces in the payload depending on profile, yet that is **CAS protocol logout integration**, not automatically a Spring Security `saml2Logout()` setup. Pick the SLO handler matching the CAS client/IdP config; allow invalidation only on authenticated/trusted SLO events.

## 10. Single Sign-Out: Filter Order and Listener Protect State

### 10.1. CAS Client SLO Components

Apereo documentation specifies:
- `org.apereo.cas.client.session.SingleSignOutFilter` handles CAS server logout callbacks and session mapping.
- `org.apereo.cas.client.session.SingleSignOutHttpSessionListener` cleans up mappings when an `HttpSession` is invalidated or expires.
- `SingleSignOutFilter` must be placed **before other CAS web filters** when using Servlet filters.

```text
Browser / CAS server
    |
    v
SingleSignOutFilter
    |  tracks CAS ticket->HttpSession, detects logoutRequest
    v
AuthenticationFilter
    |
    v
Cas30...TicketValidationFilter
    |
    v
Request wrapper / app / Spring Security policies
```

If SLO sits after the authentication filter, a server-to-server logout POST **may be redirected to CAS login** before SLO runs. If SLO sits after a body-consuming filter, the callback XML may become unreadable. Never assume "the filter exists in the Spring context" means the container calls it in the right order.

### 10.2. Listener Only Cleans Mappings, Does Not Replace the Filter

If `SingleSignOutFilter` maintains a ticket→session map, the listener cleans it up when a session expires. Registering the listener alone **does not** handle inbound SLO. Conversely, registering only the filter without the listener can cause stale mappings/memory leaks depending on implementation. Test both.

### 10.3. logoutCallbackPath

Apereo Client supports the `logoutCallbackPath` init param to pinpoint the path receiving logout callbacks. If the app has other controllers needing raw request bodies, scoping the callback accurately keeps the filter from touching every POST. Use the exact path configured on the CAS server; test callbacks arriving via ingress with the right HTTP method, content type, and charset, without requiring a user browser session cookie.

### 10.4. CSRF: Do Not Disable Protection for All POSTs

User-initiated local logout from a browser should use **POST + valid CSRF** when the app uses cookie sessions. However, CAS server-to-server SLO callbacks carry no browser CSRF token. Thus a **narrow CSRF exemption for the SLO endpoint** may be required, guarded by **valid CAS logout request verification** and matching security controls (source/trust/protocol handling). Never write `csrf.disable()` application-wide or exempt `/logout/**` broadly.

If `SingleSignOutFilter` runs in the container chain before Spring Security and consumes the SLO callback properly, it may not pass through the controller/CSRF filter the same way; **run real integration tests** instead of guessing. A CSRF-exempt endpoint lacking logout request verification can be abused to force-logout other users (logout CSRF).

### 10.5. CAS Logout Messages Must Be Trusted

Back-channel SLO may receive an XML `logoutRequest`. Never take a `SessionIndex` or ticket ID from a **raw unauthenticated HTTP POST** and delete arbitrary sessions if the implementation does not verify message validity/provenance. Review the CAS client/version, CAS server config, request provenance, binding, replay, and network/TLS trust; message-validation semantics differ from SAML2 SLO signature profiles. Never bake an assumption that "CAS SLO always carries an XML signature like SAML2 LogoutRequest" into your code.

### 10.6. Multi-Node SLO

If the app has multiple pods and a CAS SLO callback lands on node B while the ticket/session mapping lives in node A's memory, node B may fail to find the session to invalidate. Spring Session Redis shares `HttpSession` **by session ID**, yet does not automatically make Apereo CAS client's SLO ticket mapping distributed.

Verify:
- `SingleSignOutFilter`'s session mapping store has an appropriate shared implementation or callback routing/architecture guarantees it.
- Ticket/identifier index → **active HttpSession IDs** per policy, not just the current request.
- Session ID rotation/fixation updates mappings.
- Session expiry/cleanup and Redis failover work.
- Sessions belonging to other users are never deleted based on email/username.
- CAS logout invalidates local sessions across nodes and old browser cookies fail after callback.
- Never emit a false "global logout complete" when sessions remain active.

**Note:** distributed proxy ticket cache / Ehcache / Memcached modules in CAS client are not automatically replacements for **CAS SLO session mapping**; verify the actual API/implementation of your chosen module.

## 11. Request Wrapper, Thread-Local Assertion, and Dispatch

### 11.1. Wrapper Filter

The CAS client's `HttpServletRequestWrapperFilter` can wrap requests to expose the CAS-authenticated principal via the Servlet API. If Spring Security uses its own `SecurityContext`, decide how to bridge them. A CAS-validated principal on `HttpServletRequest` **does not automatically become a Spring `Authentication` with local authorities**.

**Trust boundary:** Map principals only after CAS `TicketValidator` verifies the ticket; never trust a `user` request parameter or `X-CAS-User` HTTP header from Internet clients.

### 11.2. AssertionThreadLocalFilter

Some legacy apps use `AssertionThreadLocalFilter` to read the CAS Assertion on the request thread. When moving to a Jakarta app / async servlet / reactive executor / thread pools:
- `ThreadLocal` does not propagate automatically to new threads.
- `ThreadLocal` must be cleaned up reliably when the request finishes to prevent leaking user context across requests.
- Never retain assertions in long-lived static `ThreadLocal`s.
- Avoid using a global thread-local as the primary authority source for async jobs.
- Test exceptions, error dispatches, async requests, and executor handoffs if used.

### 11.3. Dispatcher Types

Filter registrations have dispatcher types such as `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. When mappings shift after a Boot migration, a filter may:
- miss the callback because of a different dispatcher type,
- re-run on error/forward causing a login loop,
- consume the form POST body during SLO parsing,
- leave the authenticated principal absent on async continuation.

Never enable all dispatcher types blindly. Check protocol entrypoints, filter-specific expectations, and Spring Boot defaults, and test on the actual deployed container.

## 12. Filter Order When Combined with Spring Security

### 12.1. Distinct Chains

```text
Embedded Servlet container:
   [CharacterEncodingFilter]
   [Apereo CAS SLO filter]
   [Apereo CAS auth/validation filters (IF strategy A)]
   [springSecurityFilterChain / DelegatingFilterProxy]
       -> Spring Security FilterChainProxy
          SecurityContextHolderFilter / authentication filters
          ... AuthorizationFilter
   [DispatcherServlet]
```

**This is an illustrative layout**; exact ordering depends on registration and framework. If Spring Security CAS is **strategy B**, `CasAuthenticationFilter` belongs **inside `SecurityFilterChain`**; Apereo authentication/validation filters must never process the same ticket in parallel.

### 12.2. What Failures Does Double Registration Cause?

- `ticket=ST-X` is consumed twice: CAS returns `INVALID_TICKET`.
- Browser is repeatedly redirected to CAS login despite a valid CAS session.
- One filter puts the principal in `HttpSession` while Spring Security loads an old/anonymous context.
- `SecurityContext` is written and then wiped/overwritten by a second filter.
- SLO callback is missed because an outer filter redirects it.
- Controller sees a request user while `Authentication` remains anonymous.
- Same filter runs again on `ERROR`/`FORWARD` and fails.
- Startup logs show two registrations on the same URL pattern.

**Testable check:** instrument a CAS callback in a test environment, counting every CAS `TicketValidator` call and filter invocation; require **exactly one successful validation per ST** and zero duplicate CAS auth ownership.

### 12.3. Disabling FilterRegistrationBean When Filter Lives in HttpSecurity

If you choose to add a `Filter` to `HttpSecurity` and expose it as a Spring Bean, Boot may auto-register it with the container. Use `FilterRegistrationBean#setEnabled(false)` when you do not want container registration; adding the filter into `SecurityFilterChain` must use `HttpSecurity.addFilterBefore/After` against a valid anchor filter in your release.

Never try running the same filter instance through both pathways "just in case" a callback is missed. That causes bugs and subtle ordering bypasses.

## 13. Sessions, Cookies, CORS, and CSRF After Migration

### 13.1. CAS SSO Typically Needs a Browser Session

CAS service-ticket login often creates an `HttpSession` holding the authenticated assertion / Spring `SecurityContext`. After moving to Jakarta:
- `HttpSession` type is `jakarta.servlet.http.HttpSession`.
- Session cookie may be `JSESSIONID`, or `SESSION` with Spring Session.
- `SameSite`, `Secure`, `HttpOnly`, and `Path`/`Domain` must be tested on real browsers.
- HTTPS redirects from the CAS server back to the service callback must retain the cookie when saved requests are needed.
- Session fixation protection may rotate the session ID after login.
- Logout/SLO must invalidate the exact session ID, even across node changes.

### 13.2. A CAS Ticket Is Not a CSRF Token

A `ticket` is a bearer proof from the CAS server, not a substitute for browser CSRF state/session binding across endpoints. Business POSTs still require CSRF protection in cookie-authenticated apps. For CAS callbacks, enforce login-CSRF/session-fixation protection and service validation; CAS callbacks differ from OIDC `state`, yet that never justifies dropping browser-flow checks.

### 13.3. Cookie SameSite and Cross-Site Redirects

CAS browser login sends users across the IdP domain. Callbacks are usually top-level GETs with a service ticket, where `SameSite=Lax` behaves more favorably than on cross-site POSTs. Still, `gateway=true` flows, AJAX, browser blocking, and cookie `Domain`/`Path` can interfere. Never set `SameSite=None` just because a 302 error appeared; inspect the callback method and browser behavior, then pick a cookie policy with matching CSRF controls.

### 13.4. CORS Cannot Fix a Login Redirect

An SPA calling a protected API via `fetch` and receiving a 302 to CAS login will hit a browser CORS error; "allowing `*` for all origins" is not a fix. Use a BFF/server-side session login redirect or an appropriate protocol API, with the frontend performing top-level navigation when needed. CAS client filters target servlet/browser flows, not arbitrary XHR endpoints.

## 14. SSL/TLS, Secrets, and Trust Boundaries

### 14.1. Back-Channel Ticket Validation

`TicketValidator` calls the CAS server over HTTPS. In production:
- Trust the right server TLS certificate chain and hostname.
- Never disable certificate checks when a CA rotates.
- Enforce timeouts, redirect limits, and response size limits to avoid hanging filter threads.
- Configure only admin-approved CAS server URLs, never from a user query param.
- Never log raw service tickets, PGTs, session cookies, or sensitive CAS attributes.
- Verify XML parser XXE/DTD/oversized-response protection with safe dependency versions.
- Proxy settings and egress policies should block connections to hosts outside the allowlist.

### 14.2. Service URL and Host Header Spoofing

If the service URL is built from unsanitized `Host` or `X-Forwarded-Host` headers, an attacker can manipulate redirects or validation to target another service. Set a canonical public URL or trusted forwarded-header configuration. CAS registered service rules must be tight, never broad regexes matching any domain.

### 14.3. Proxy Granting Tickets

If using PGTs, `pgtUrl`/`proxyCallbackUrl` can trigger inbound callbacks from the CAS server; identity must be bound to the service and allowed proxy chain. Never set `acceptAnyProxy` unchecked, never open wildcard hostname verifiers, and never retain PGTs indefinitely in DBs/logs.

### 14.4. Dependency Scanning

After migration, run SCA/CVE scans on:
- `cas-client-core`;
- Spring Security/Boot/Web;
- XML parsing/security dependencies;
- Commons Codec/SLF4J;
- embedded servlet container;
- cache/session libraries.

"Jakarta-compatible" does not mean latest or patched against every CVE. Verify vulnerabilities against the deployed dependency tree rather than trusting a single version number from an article.

## 15. Phased Safe Upgrade Process

### Phase 0 — Freeze Current Behavior

- Record baseline flows: browser CAS login, renew/gateway, ticket validation, local logout, CAS SLO, proxy tickets (if used).
- Record public service URLs and CAS server registered service rules.
- Capture dependency graph, filter order/registrations, and session behavior (without storing raw tickets).
- Define acceptance criteria and current security checks.
- Assign owners for authentication, authorization, Session, and SLO.

### Phase 1 — Choose Target Platform

- If Java 17 / Boot 3: evaluate Jakarta CAS client 4.0.x and compatibility/security matrix.
- If Java 21 / Boot 4: evaluate Jakarta CAS client 4.1.x and Boot 4 support.
- If the app uses `spring-security-cas`: lock a compatible module/provider and do not add Apereo filters onto the callback.
- If replacing the protocol with OIDC: execute as a separate initiative with data/identity account-linking migration.

### Phase 2 — Dependency Migration

- Update CAS modules in sync.
- Use `jakarta.servlet-api` from Boot/container; remove `javax.servlet-api` from runtime.
- Migrate custom filters/listeners/imports.
- Update `@WebFilter`/`@WebListener` if used.
- Check XML descriptors and deployment WARs.
- Enforce Maven/Gradle dependency convergence; fail if legacy modules remain.

### Phase 3 — Filter Registration

- Pick `web.xml` **or** `FilterRegistrationBean` **or** Apereo Boot auto-registration.
- One owner for CAS login/ticket validation; avoid Spring CAS + Apereo auth dual paths.
- Place SLO filter early per CAS docs; register listener.
- Add wrapper/thread-local if the application requires it.
- Verify URL patterns/dispatcher types; avoid unexpectedly protecting `/actuator` with a login redirect.
- Test filter order in a real embedded container, not just Java unit tests.

### Phase 4 — Secure CAS Ticket Validation

- Configure trusted CAS server URL/TLS/hostname.
- Use the same canonical service URL for browser login and back-channel validation.
- Enable the right protocol validator and proxy chain allowlist if used.
- Enforce single-use tickets and `redirectAfterValidation`/clean URL policy.
- Map CAS principal to local account/authorities with account-status checks.
- Protect user logout with POST/CSRF; secure the SLO callback separately and validate legitimacy.

### Phase 5 — Session/SLO/Cluster

- Verify session cookie behavior and session fixation protection.
- Confirm CAS SLO back-channel callbacks work **without a browser cookie**.
- Verify listener cleanup and session invalidation across all nodes if HA.
- Add Redis/shared session mapping if architecture requires, rather than assuming Spring Session automatically shares CAS SLO maps.
- Revoke active sessions when a user is disabled/locked per policy.
- Keep raw ST/PGT/NameID out of logs and metrics.

### Phase 6 — Canary and Rollback

- Deploy canary to a subset of users; capture safe reason codes.
- Compare CAS login/validation failure rates, latency, redirect loops, and SLO misses against baseline.
- Test cross-version deployment if sharing sessions/serialized data; never blind rolling-deploy.
- Verify backward-compatible session representations and TTLs; controlled re-login may be necessary.
- Prepare a rollback target covering app version, CAS registered service, config secrets, and domain/cookie behavior.
- Never roll back to a `javax.servlet` artifact inside a Jakarta runtime; rollback must be coherent across the full stack.

## 16. Standalone Java 17 Demo: Audit Migration Config Before Deploy

The following example is a **static rule checker** in Java 17 requiring no Spring/Jakarta CAS dependencies and creating no real `HttpSession`. It models a `Deployment` and detects:

- CAS client 3.x on Jakarta: incompatible.
- CAS client 4.1.x running on Java 17: Java baseline too low.
- Runtime still carrying `javax.servlet`: namespace mix-up.
- Duplicate auth/validate/SLO filter registrations.
- Enabling both Apereo auth filters and Spring Security CAS auth on the same callback.
- `SingleSignOutFilter` placed after the authentication filter.
- Missing SLO `HttpSessionListener`.
- Browser `service` URL differing from expected canonical URL.

Limitations: filter names in the demo are **configuration labels** (not actual servlet `Filter` objects). It does not read `pom.xml`/`web.xml`, prove compatibility/safe parsing, call a CAS server, verify tickets/XML signatures, or test `SecurityContext`. The output is an **executable checklist**, not a security verifier.

Save file `CasJakartaMigrationAudit.java`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class CasJakartaMigrationAudit {

    private static final String EXPECTED_SERVICE =
            "https://portal.example.org/cas/callback";

    record Deployment(
            String clientVersion,
            int jdk,
            int servletMajor,
            boolean hasJavaxServlet,
            boolean hasJakartaServlet,
            List<String> filters,
            boolean hasSloListener,
            boolean twoAuthStacks,
            String serviceUrl) {}

    static String audit(Deployment deployment) {
        String version = deployment.clientVersion();
        if (version.startsWith("3.")) {
            return "FAIL_LEGACY_CAS_CLIENT";
        }
        if (!version.startsWith("4.0.")
                && !version.startsWith("4.1.")) {
            return "FAIL_UNKNOWN_VERSION";
        }

        int requiredJdk = version.startsWith("4.1.") ? 21 : 17;
        if (deployment.jdk() < requiredJdk) {
            return "FAIL_JDK_BASELINE";
        }
        if (deployment.servletMajor() < 6) {
            return "FAIL_SERVLET_GENERATION";
        }
        if (deployment.hasJavaxServlet()
                || !deployment.hasJakartaServlet()) {
            return "FAIL_SERVLET_NAMESPACE";
        }

        Set<String> unique = new HashSet<>(deployment.filters());
        if (unique.size() != deployment.filters().size()) {
            return "FAIL_DUPLICATE_FILTER";
        }
        if (deployment.twoAuthStacks()) {
            return "FAIL_DUAL_AUTH_STACK";
        }

        List<String> filters = deployment.filters();
        int slo = filters.indexOf("slo");
        int auth = filters.indexOf("auth");
        int validate = filters.indexOf("validate");

        if (slo < 0 || auth < 0 || validate < 0) {
            return "FAIL_INCOMPLETE_CHAIN";
        }
        if (slo > auth || slo > validate) {
            return "FAIL_SLO_FILTER_ORDER";
        }
        if (!deployment.hasSloListener()) {
            return "FAIL_SLO_LISTENER";
        }
        if (!EXPECTED_SERVICE.equals(deployment.serviceUrl())) {
            return "FAIL_SERVICE_URL";
        }
        return "PASS";
    }

    static Deployment baseline() {
        return new Deployment(
                "4.0.4", 17, 6, false, true,
                List.of("slo", "auth", "validate"),
                true, false, EXPECTED_SERVICE);
    }

    static Deployment copy(
            Deployment base, String version, int jdk,
            boolean hasJavax, List<String> filters,
            boolean listener, boolean twoStacks,
            String serviceUrl) {
        return new Deployment(
                version, jdk, base.servletMajor(),
                hasJavax, base.hasJakartaServlet(), filters,
                listener, twoStacks, serviceUrl);
    }

    static void check(String name, Deployment deployment) {
        System.out.println(name + ": " + audit(deployment));
    }

    public static void main(String[] args) {
        Deployment base = baseline();

        check("Boot3 Java17 CAS4.0", base);
        check("Legacy CAS3 on Jakarta",
                copy(base, "3.6.4", 17, true,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("CAS4.1 on Java17",
                copy(base, "4.1.1", 17, false,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("Boot4 Java21 CAS4.1",
                copy(base, "4.1.1", 21, false,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("Mixed javax and jakarta",
                copy(base, "4.0.4", 17, true,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("Duplicate auth filter",
                copy(base, "4.0.4", 17, false,
                    List.of("slo", "auth", "validate", "auth"),
                    true, false, EXPECTED_SERVICE));
        check("Two authentication stacks",
                copy(base, "4.0.4", 17, false,
                    base.filters(), true, true, EXPECTED_SERVICE));
        check("SLO runs too late",
                copy(base, "4.0.4", 17, false,
                    List.of("auth", "slo", "validate"),
                    true, false, EXPECTED_SERVICE));
        check("Missing SLO listener",
                copy(base, "4.0.4", 17, false,
                    base.filters(), false, false, EXPECTED_SERVICE));
        check("Wrong service URL",
                copy(base, "4.0.4", 17, false,
                    base.filters(), true, false,
                    "http://pod:8080/cas/callback"));
        check("Missing validation filter",
                copy(base, "4.0.4", 17, false,
                    List.of("slo", "auth"),
                    true, false, EXPECTED_SERVICE));
    }
}
```

Run on JDK 17 or newer:

```bash
javac CasJakartaMigrationAudit.java
java CasJakartaMigrationAudit
```

**Exact** stdout:

```text
Boot3 Java17 CAS4.0: PASS
Legacy CAS3 on Jakarta: FAIL_LEGACY_CAS_CLIENT
CAS4.1 on Java17: FAIL_JDK_BASELINE
Boot4 Java21 CAS4.1: PASS
Mixed javax and jakarta: FAIL_SERVLET_NAMESPACE
Duplicate auth filter: FAIL_DUPLICATE_FILTER
Two authentication stacks: FAIL_DUAL_AUTH_STACK
SLO runs too late: FAIL_SLO_FILTER_ORDER
Missing SLO listener: FAIL_SLO_LISTENER
Wrong service URL: FAIL_SERVICE_URL
Missing validation filter: FAIL_INCOMPLETE_CHAIN
```

### 16.1. Interpretation

- `Boot3 Java17 CAS4.0: PASS`: a combination passing a **simple static audit** does not guarantee build/runtime compatibility; integration tests are still required.
- `Legacy CAS3 on Jakarta` is rejected because CAS 3.x relies on `javax.servlet`.
- `CAS4.1 on Java17` is rejected per CAS client 4.1.x's published Java 21 baseline.
- `Mixed javax and jakarta` fails even when CAS 4.0.x is selected.
- `Duplicate auth filter` catches registering the same filter twice.
- `Two authentication stacks` catches dual CAS ticket processing between Apereo auth/validation and Spring Security CAS.
- `SLO runs too late`: SLO must receive requests before other CAS web filters per Apereo docs.
- `Missing SLO listener`: missing lifecycle cleanup per CAS client usage.
- `Wrong service URL`: browser callback/public service differs from configuration; in a real system the service ticket will be rejected by CAS per registry/validation rules.
- `Missing validation filter`: no path to validate CAS tickets; **never** treat a ticket string as an identity.

### 16.2. Limitations of the Audit Demo

1. `audit` does not check the actual POM dependency graph, nor parse bytecode or XML.
2. `servletMajor=6` is a minimum in the demo; CAS 4.1.x builds with 6.1, so real deployments must check **minor versions** and class APIs, which the demo does not verify.
3. Does not verify Spring Security CAS module behavior or internal Spring filter-chain ordering.
4. Does not check TLS CA/hostname, CAS registered services, single-use tickets, SLO authenticity, or listener callback coverage.
5. Does not detect which CAS 4.0.x patches carry security advisories.
6. Does not account for WAR vs. JAR and classloader/container differences.
7. Does not check proxy policy, CSRF, session cookies, or multi-node SLO mappings.
8. `twoAuthStacks` is a boolean supplied by the demo caller; production must scan actual registrations.
9. Does not guarantee the SLO listener works when deployed; integration tests are required.
10. The Java-version policy check is illustrated with 4.0.x/4.1.x; **future branches must verify their real POMs**.

## 17. Upgrade Testing: Unit, Integration, Browser, and Cluster

### 17.1. Dependency/API Tests

| Test ID | Scenario | Expected |
| --- | --- | --- |
| DEP-01 | Boot 3/JDK 17, CAS client 4.0.x Jakarta | Compiles + container starts once versions verified |
| DEP-02 | Boot 3/JDK 17, CAS client 3.x javax | CI FAILS, do not package release |
| DEP-03 | Boot 4/JDK 21, CAS client 4.1.x | Compiles + SSO integration passes |
| DEP-04 | Boot 3/JDK17 + cas-client-core 4.1.1 | Reject incompatible Java bytecode |
| DEP-05 | Runtime has both `javax.servlet.Filter` and Jakarta Filter in pipeline | Fail migration gate |
| DEP-06 | Custom filter imports `javax.servlet` | Compile gate detects it |
| DEP-07 | WAR bundling duplicate `servlet-api` implementation | Fail deployment review |
| DEP-08 | `cas-client` POM aggregator mistaken for filter JAR | Fail dependency resolution / class presence |
| DEP-09 | Spring Security CAS module pulls old Apereo client | Dependency convergence fails |
| DEP-10 | Boot starter + `FilterRegistrationBean` for same CAS auth filter | Duplicate registration test fails |

### 17.2. Filter Lifecycle/Order Tests

| ID | Scenario | Expected |
| --- | --- | --- |
| FIL-01 | Startup registers exactly 1 `SingleSignOutFilter` | PASS |
| FIL-02 | SLO filter stands before CAS auth/validation filters | PASS |
| FIL-03 | Listener `SingleSignOutHttpSessionListener` registered once | PASS |
| FIL-04 | Double `AuthenticationFilter` or `CasAuthenticationFilter` | FAIL |
| FIL-05 | Both Apereo CAS auth and Spring Security CAS on same ticket callback | FAIL |
| FIL-06 | Validation filter receives redirect callback with `ticket` | Validates once |
| FIL-07 | Missing validation filter | Must not authenticate from unverified ticket |
| FIL-08 | `AuthenticationFilter` redirects CAS SLO POST too | FAIL |
| FIL-09 | Invalid `logoutRequest` body | Must not destroy arbitrary sessions |
| FIL-10 | Wrapped request returns trusted CAS principal | Only after successful validation |
| FIL-11 | `AssertionThreadLocal` retains user after request exception | FAIL, prevent context leak |
| FIL-12 | Async dispatch / body read | Proper filter dispatcher & charset semantics |
| FIL-13 | Duplicate filter from `@WebFilter` + `@Bean` | FAIL |
| FIL-14 | CAS filter added to `HttpSecurity` while Boot also container-registers | FAIL |
| FIL-15 | Public health/actuator route gets unexpected login redirect | FAIL |
| FIL-16 | Unauthenticated protected route unexpectedly bypasses CAS | FAIL |

### 17.3. Ticket Validation Tests

| ID | Scenario | Expected |
| --- | --- | --- |
| TKT-01 | Browser redirected to CAS login with exact service | PASS |
| TKT-02 | Valid ticket, matching service URL, right validator | Creates principal/authentication |
| TKT-03 | Ticket issued for a different service URL | Reject |
| TKT-04 | Already-validated ticket submitted again | Reject replay |
| TKT-05 | Forged/tampered ticket | Reject |
| TKT-06 | Invalid CAS server HTTPS certificate | Reject; never disable hostname verifier |
| TKT-07 | CAS server unavailable/timeouts | Fail closed, no local admin |
| TKT-08 | Malformed CAS response XML/JSON | Reject / sanitized parser error |
| TKT-09 | CAS returns principal B, local link A | Never auto-link by email |
| TKT-10 | CAS principal ACTIVE while local user LOCKED | RP denies per local status |
| TKT-11 | Valid CAS principal lacking local role | Protected endpoint denies |
| TKT-12 | Proxy ticket from unapproved proxy chain | Reject |
| TKT-13 | `acceptAnyProxy=true` accidentally enabled | Security review FAIL |
| TKT-14 | Ticket retained in browser URL after validation | Clean-URL policy fails if unhandled |
| TKT-15 | Valid CAS Ticket yet Spring `SecurityContext` remains anonymous | Integration bridge/mapping issue |
| TKT-16 | `renew=true` policy | CAS forces reauth per validated profile |
| TKT-17 | `gateway=true` policy | No redirect loop; anonymous result handled properly |
| TKT-18 | Service URL uses spoofed proxy Host | Reject/normalize to trusted host |

### 17.4. SLO and Session Tests

| ID | Scenario | Expected |
| --- | --- | --- |
| SLO-01 | User-initiated local logout via POST + CSRF | Current local session invalidated |
| SLO-02 | CAS SLO callback to configured path | Session matching ticket revoked |
| SLO-03 | SLO callback without browser cookie | Server-side session mapping still processes |
| SLO-04 | Missing `SingleSignOutHttpSessionListener` | FAIL lifecycle QA |
| SLO-05 | Expired `HttpSession` | Ticket→session mapping cleaned up |
| SLO-06 | Browser keeps old cookie after SLO | Protected endpoints deny |
| SLO-07 | CAS SLO hits pod B, original session on pod A | Revoked if architecture requires HA |
| SLO-08 | Session ID rotated after login | SLO mapping updated |
| SLO-09 | Same user holds two sessions | Target per CAS logout mapping, never guess |
| SLO-10 | Forged SLO callback | No sessions deleted |
| SLO-11 | Duplicate/replayed SLO message | Idempotent/rejected per policy |
| SLO-12 | `LogoutResponse`/partial status absent in this CAS flow | Do not blindly apply SAML2 SLO semantics |
| SLO-13 | Spring Session Redis healthy yet Apereo SLO uses local map | Detect missing distributed index |
| SLO-14 | Missed session expire event | Reaper/reconciliation cleanup |
| SLO-15 | Broad CSRF exemption on all `/logout/**` | Security QA FAIL |
| SLO-16 | Servlet listener registered twice | Test detects duplicate lifecycle |
| SLO-17 | `ThreadLocal` assertion leaks from user A to B | Security QA FAIL |
| SLO-18 | Raw `logoutRequest`/ticket/sessionID in logs | Security QA FAIL |

### 17.5. Browser, Ingress, and Multi-Region Tests

| ID | Scenario | Expected |
| --- | --- | --- |
| BRI-01 | Public HTTPS URL, internal HTTP pod | CAS uses canonical public service |
| BRI-02 | Attacker-supplied forwarded headers | Does not alter trusted service URL |
| BRI-03 | Cookie Path differs from callback | Test detects lost session |
| BRI-04 | `SameSite` Lax/Strict/None behavior across CAS redirect | Matches browser flow and CSRF policy |
| BRI-05 | CAS login succeeds on Chrome/Firefox/mobile | No loops |
| BRI-06 | SPA `fetch` hits CAS login redirect | Proper BFF/top-level navigation UX |
| BRI-07 | Two nodes run different CAS client versions | Canary review/compatibility tests |
| BRI-08 | Redis failover between ticket validation and session save | No phantom auth created |
| BRI-09 | Request hits node B after login on node A | `SecurityContext`/session remains valid |
| BRI-10 | Node A restarts before CAS SLO callback | HA SLO works per architecture |
| BRI-11 | Service ticket logged at ingress | Redaction policy fails |
| BRI-12 | Identical CAS principals across tenants | Local account isolation |

## 18. Failure Modes and Proper Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `NoClassDefFoundError: javax/servlet/Filter` | CAS client 3.x or another lib not yet Jakarta | Switch to compatible Jakarta artifact; inspect dependency tree |
| `ClassCastException: Filter cannot be cast` | `javax` Filter placed into Jakarta registration | Pick right CAS version; never add `javax.servlet-api` workaround |
| `UnsupportedClassVersionError` | CAS 4.1.x Java 21 bytecode running on JDK 17 | Use JDK 21/Boot 4 stack or Java 17 branch artifact |
| `BeanCreationException` on filter registration | Servlet API/JDK version mismatch | Audit classloader/imports/transitives |
| Infinite CAS login redirect | Filter registered twice, wrong service URL, or callback blocked by auth filter | Pick one auth owner; compare redirect/validation paths |
| CAS returns `INVALID_TICKET` | Ticket replay, double validator, wrong service | Count validator calls and compare canonical service |
| CAS returns `INVALID_SERVICE` | Service mismatch/registry, scheme/host/path | Fix public origin / registered service config |
| Immediate 302 on SLO callback | CAS `AuthenticationFilter` intercepts logout POST | Place SLO filter before auth and scope path properly |
| Local logout works, CAS SLO doesn't | Missing SLO filter/listener/callback mapping | Test signed/trusted callback, session mapping/cluster |
| SLO clears only one node | Local-memory mapping, unshared session store | Distributed revocation / session indexing |
| Request has user principal yet Spring Security is anonymous | Apereo filter doesn't bridge `SecurityContext` | Choose Spring Security CAS or an explicit validated principal bridge |
| User lacks roles despite OK CAS validation | Missing/wrong-prefix local authority mapping | Map local roles; never auto-grant admin |
| Failed CAS login produces 500 leaking details | `ExceptionOnValidationFailure`/handlers | Sanitize failure, preserve reject |
| Browser retains ticket in URL | `redirectAfterValidation` disabled / wrong path | Clean URL after validation |
| Service URL leaks pod HTTP URL | Proxy forwarded-header trust / canonical URL | Explicit public origin, ingress sanitizer |
| Raw PGT/ticket in access logs | Query logging/tracing | Redact query keys/headers |
| SLO XML parse errors from encoding | Filter order/encoding/body read | `CharacterEncodingFilter`, callback path, tests |
| Build passes, WAR startup fails | Bundled Servlet API / loader version mismatch | `provided` scope, compatible container |
| Filter runs twice in Spring Boot | Bean auto-registration + `HttpSecurity` registration | Disable container registration for `SecurityFilterChain`-owned filters |
| CI tests all pass yet logout fails in cluster | Mocks don't use real `HttpSession` on two pods | HA SLO integration and chaos tests |

## 19. Upgrade and Deployment Runbook

### 19.1. Before Release

1. Lock one target JDK/Boot/CAS client version and approval list.
2. Verify active CAS server endpoints, registered service rules, and TLS certificate chain.
3. Review dependency tree: no obsolete servlet filters, no mixed APIs.
4. Review filter chain registrations and expected ordering.
5. Test positive CAS login against a real CAS test server and role mapping.
6. Test same-ticket replay, wrong service, and TLS failure.
7. Test local logout and IdP CAS SLO callback without a browser cookie.
8. Test canary cross-node sessions and SLO if HA is required.
9. Verify no raw tickets/PGT/NameID appear in logs.
10. Prepare a **coherent** rollback (never put a `javax` JAR into a Jakarta runtime).

### 19.2. During Canary

- Monitor `cas_login_redirect_total`, `cas_ticket_invalid_total`, `cas_service_mismatch_total`, `cas_slo_callback_total`, and `cas_slo_revocation_fail_total`.
- Add `filter_registration_duplicate_total` or a startup assertion for expected filter count.
- Track timeouts/back-channel latency and CAS server HTTP errors.
- Check session invalidation/expiry and 403 local authorization after authentication.
- Never use email, raw tickets, or session cookies as metric labels.
- If `INVALID_TICKET` appears right after a success, suspect double validation; check for duplicates before loosening trust.
- If SLO suddenly 302s to login, check filter order.
- Roll back the full version/config when symptoms cross thresholds; never disable TLS or callback checks.

### 19.3. After Release

1. Inspect the actual packaged Spring Boot runtime dependency tree.
2. Keep canary tests running as traffic shifts across nodes.
3. Verify users logged in prior to deploy are handled per policy; never silently share stale session contexts.
4. Test active account locking and CAS SLO from the test IdP.
5. Monitor listener lifecycle, stale indices, and cache memory growth.
6. Scan CVEs and security advisories after every patch upgrade.
7. Record a migration decision record: chosen strategy, rationale, source links, and owner/rollback.

## 20. Production Checklist

- [ ] Inventory covers JDK, Spring Boot, Spring Security, Servlet container, CAS client, and topology.
- [ ] Target CAS client is Jakarta-compatible **and** runs on the deployed JDK.
- [ ] Boot 3/Java 17 evaluates CAS client 4.0.x; Boot 4/Java 21 evaluates 4.1.x.
- [ ] Dependencies contain no legacy `javax.servlet-api` in the Jakarta web request pipeline.
- [ ] Custom filters/listeners use `jakarta.servlet.*`.
- [ ] No blind replacement of `javax.crypto` or `javax.net.ssl`.
- [ ] WAR descriptor/schema matches Jakarta servlet container with proper API scope.
- [ ] Exactly one CAS authentication strategy chosen (Apereo filters or Spring Security CAS).
- [ ] No duplicate filter registrations across `web.xml`, `@WebFilter`, `FilterRegistrationBean`, `@EnableCasClient`, or `HttpSecurity`.
- [ ] `SingleSignOutFilter` runs before other CAS filters per docs; listener registered once.
- [ ] Charset/callback path/dispatcher types for SLO are verified in practice.
- [ ] Canonical public HTTPS service URL matches browser redirects and CAS validation.
- [ ] CAS server registered service, trusted TLS, and exact ticket validation path match protocol.
- [ ] Tickets are validated once, with a replay negative test.
- [ ] `acceptAnyProxy` is disabled unless backed by a proxy trust policy.
- [ ] CAS principal/attributes pass safely through local role/locked-status gates.
- [ ] Spring `SecurityContext` is neither bypassed nor double-processed.
- [ ] Browser POST local logout has CSRF; CAS SLO callback is handled separately with trusted checks.
- [ ] SLO invalidates the right `HttpSession`s and cleans up mappings, including failover if HA.
- [ ] Session fixation, Redis/Spring Session, and `SameSite`/`Domain`/`Path` are tested.
- [ ] Ingress forwarded headers are trusted only from the proxy; no `Host` spoofing.
- [ ] No tickets, PGTs, session IDs, raw `logoutRequest`s, passwords, or PII in logs.
- [ ] Migration has JUnit/integration/browser/multi-node tests and canary rollback.
- [ ] Security advisories and dependency convergence reviewed before release.
- [ ] Java 17 runnable audit demo executed to validate version, filter chain, and service URL policy.

## 21. Review Questions

**1. Why can't CAS Client 3.x be used in Spring Boot 3 just by changing project imports?**  
Because the legacy client JAR was compiled against `javax.servlet.Filter`; a Jakarta Servlet container requires `jakarta.servlet.Filter`, and the two types are incompatible.

**2. Do CAS Java Client 4.0.4 and 4.1.1 both run on Java 17?**  
No. The inspected POM for 4.0.4 uses a Java 17 baseline; 4.1.1 sets a Java 21 baseline.

**3. Which Maven artifact contains the core filters?**  
`org.apereo.cas.client:cas-client-core`, not just the `cas-client` POM aggregator artifact.

**4. Should `javax.crypto` be changed to `jakarta.crypto`?**  
No. `javax.crypto` belongs to Java SE; changing that namespace is incorrect.

**5. Where should `SingleSignOutFilter` be placed?**  
Before the other CAS web filters per Apereo README; filter and listener must be registered under one consistent strategy.

**6. Should `AuthenticationFilter` and `CasAuthenticationFilter` both be enabled for the same callback?**  
No. They belong to two stacks and can re-validate the same single-use ticket, causing redirect loops/`INVALID_TICKET`.

**7. How does `FilterRegistrationBean` order differ from `HttpSecurity.addFilterBefore`?**  
One manages the Servlet container chain; the other manages position inside Spring Security's `FilterChainProxy`.

**8. When a `@Bean` Filter is added to `HttpSecurity`, why might it run twice?**  
Spring Boot can auto-register Filter Beans with the container; use `FilterRegistrationBean` with `enabled=false` if you only want the filter inside `SecurityFilterChain`.

**9. Why must the CAS service URL be exact?**  
The ticket is issued for a service and the validator must verify the exact service recognized by the CAS server; differing scheme/host/path can cause CAS to reject it.

**10. Does `INVALID_TICKET` after migration necessarily mean the CAS server is broken?**  
No. It is often caused by a single-use ticket being validated twice, double registration, or a service mismatch.

**11. Does `SingleSignOutHttpSessionListener` replace `SingleSignOutFilter`?**  
No. The listener cleans up session mappings; the filter receives and processes logout callbacks.

**12. Why doesn't Spring Session Redis automatically guarantee multi-node CAS SLO?**  
Because the CAS client may keep its ticket-to-session mapping separately in local memory; a matching distributed mapping must be verified or implemented.

**13. Is CAS `Saml11TicketValidationFilter` the same as Spring Security SAML2 login?**  
No. The CAS SAML 1.1 protocol variant differs from SAML2 Web Browser SSO.

**14. Can a `jku` URL or CAS server endpoint be accepted from a callback query parameter?**  
No. CAS server/keys/trust configuration must be server-managed, never taken from untrusted input.

**15. What should be done when the CAS server certificate rotates?**  
Update the trusted TLS chain/hostname via certificate management procedures; never disable certificate validation.

**16. Why might a CAS SLO callback lack a cookie?**  
It may be a back-channel request from the CAS server rather than a browser; session lookup requires server-side ticket/session mapping.

**17. Should CSRF be disabled on all endpoints to make CAS logout POST work?**  
No. Handle only the specific CAS callback endpoint with trust validation; browser actions still require CSRF.

**18. A CAS ticket validates successfully, yet Spring `SecurityContext` stays anonymous—why?**  
The Apereo filter and Spring Security context may not be bridged; choose the Spring Security CAS strategy or an explicit validated integration.

**19. If CAS 4.1.x fails to compile in Boot 3/Java 17, can we lower the compiler target to 17?**  
No. The app's compiler target does not alter bytecode/baselines inside dependencies; choose a compatible artifact/JDK.

**20. Which tests prove migration success beyond "the service boots"?**  
Real browser CAS login, one-time ticket validation, wrong-service rejection, local authz, CAS SLO, cross-node sessions, absence of duplicate filters, and safe logging.

## 22. Official Documentation and References

- [Apereo Java CAS Client (GitHub README)](https://github.com/apereo/java-cas-client): `cas-client-core` module, Servlet filters, filter init parameters, `AuthenticationFilter`, `Cas30ProxyReceivingTicketValidationFilter`, `SingleSignOutFilter`/listener, and `@EnableCasClient`.
- [Maven Central — CAS Client Core 4.0.4](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client-core/4.0.4): Jakarta artifact used with the Java 17 / Servlet 6 generation.
- [Maven Central — CAS Client 4.0.0 POM](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client/4.0.0): `jakarta.servlet-api:6.0.0` and `project.build.sourceVersion=17`.
- [Maven Central — CAS Client 4.1.1 Parent POM](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client/4.1.1): Servlet 6.1, JDK 21, Boot 4/Spring 7.
- [Maven Central — CAS Client Boot Support 4.1.1](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client-support-springboot/4.1.1): Boot integration artifact.
- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `CasAuthenticationFilter`, `CasAuthenticationProvider`, `CasAuthenticationEntryPoint`, `TicketValidator`, SLO integration. XML examples have historical parts; verify against current release/framework.
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, filter ordering, and warning on duplicate container registration of Filter Beans.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): `FilterRegistrationBean`, `ServletListenerRegistrationBean`, ordering, and startup filter inspection.
- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/): API and `web.xml` Jakarta namespace, container version.
- [Jakarta Servlet 6.1 Specification](https://jakarta.ee/specifications/servlet/6.1/): newer servlet generation with Jakarta EE 11.
- [Spring Boot 3 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6, Jakarta EE APIs.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic errors, local status/reauthentication.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session fixation, logout/invalidation.
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): user-initiated logout and request protections.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoiding logging ST/PGT/credentials/session IDs.

**Remember:** Upgrading a CAS client to Jakarta is not simply changing `javax.servlet` to `jakarta.servlet` in application source. You must pick a **CAS artifact compiled for Jakarta + the right Java/Spring generation**, remove legacy servlet dependencies, establish **a single owner for CAS ticket validation**, register `SingleSignOutFilter` and its listener in the right order, use a canonical `service` URL with trusted TLS ticket validation, and preserve session/CSRF/SLO semantics. In Spring Boot, pay close attention to whether filters are registered at the **container** or inside **`SecurityFilterChain`** to avoid validating an ST twice. Test **browser login, ticket replay, wrong service, local authorities, SLO, and multi-node** before go-live; never bypass protections just to stop a redirect loop.