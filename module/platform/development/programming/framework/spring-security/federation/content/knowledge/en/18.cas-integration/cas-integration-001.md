# ServiceProperties and Configuring the Service URL and Ticket-Processing Endpoint

> **Topic:** Spring Security – Federation. **Knowledge Group:** CAS Integration. This Knowledge article focuses on the role of `org.springframework.security.cas.ServiceProperties`, rules for determining the **application's service URL**, the `CasAuthenticationFilter` endpoint that receives the Service Ticket, and the CAS server endpoint used to **validate the ticket**. This guide targets Java 17+, Spring Boot Servlet applications, and the Spring Security CAS client; examples use Spring Security 6.5.x/Boot 3.x-compatible APIs, with reminders to verify APIs against your actual version.

## 1. Learning Objectives

After completing this article, you will be able to:

1. Distinguish the **CAS Server** from the **CAS Service/Client** (the Spring application to protect).
2. Understand why `ServiceProperties.service` is typically the **absolute HTTPS URL of the application callback**, such as `https://app.example.org/login/cas`.
3. Explain the rule of **one service URL across all three hops**: the `service` parameter sent to `/cas/login`, the URL the browser returns to with `ticket`, and the `service` parameter sent to `/cas/serviceValidate`.
4. Distinguish `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `TicketValidator`, and `AuthenticationManager`; know which bean calls which.
5. Configure `filterProcessesUrl` to match the **local path** of `ServiceProperties.service`, accounting for context path, HTTPS reverse proxy, and port.
6. Understand that a CAS **Service Ticket (ST)** is a single-use, service-bound proof; it is not the application browser session, a CAS Ticket-Granting Ticket (TGT), or a JWT.
7. Write a clear Spring Security CAS Java configuration, avoiding double-registering the servlet filter and without dropping CSRF or authorization.
8. Detect `INVALID_SERVICE`, `INVALID_TICKET`, login loops, callback 404s, and wrong proxy scheme/hostname errors using a test matrix.
9. Understand `sendRenew`, the differences between `/serviceValidate`, `/p3/serviceValidate`, `/proxyValidate`, and the optional proxy receptor.
10. Apply security controls: service registry allowlist, HTTPS, preventing ticket leakage in logs/referrer, controlling Host/forwarded headers, and never trusting an unvalidated ticket from a callback.

**Key takeaway:** `ServiceProperties` is not a bean describing the CAS Server, nor is it where tickets are stored. It is the configuration for **the service application itself that is logging in**. If the `service` used when issuing the ST differs from the `service` used when validating the ST, CAS must reject it, even if the user authenticated successfully at the CAS Server.

## 2. The Big Picture: CAS Server, Browser, and Spring Security Service

Suppose:

| Component | Illustrative URL or Identifier | Role |
| --- | --- | --- |
| **CAS Server base URL** | `https://sso.example.org/cas` | Organization's SSO/IdP system |
| **CAS Login endpoint** | `https://sso.example.org/cas/login` | Where the browser is redirected to authenticate |
| **CAS Ticket-validation endpoint** | `https://sso.example.org/cas/serviceValidate` | Application backend sends the ST along with `service` to validate |
| **Spring Application (Service)** | `https://app.example.org` | Service to protect |
| **Application's CAS callback** | `https://app.example.org/login/cas` | Browser returns here with `?ticket=ST-...` |
| **`ServiceProperties.service`** | `https://app.example.org/login/cas` | Service identifier sent to CAS when requesting and validating an ST |
| **`CasAuthenticationFilter.filterProcessesUrl`** | `/login/cas` | Request path **on the application** watched by the filter |
| **Business page** | `https://app.example.org/reports` | Resource accessible only to authenticated/authorized users |

**Common pitfall:** `/login/cas` is **not** a CAS Server URL. It is the callback path on the **Spring application**. Meanwhile, `/cas/login` and `/cas/serviceValidate` reside on the **CAS Server**. Both sides may contain the word "cas" in their paths, but their host, responsibility, operator, and processing order are different.

### 2.1. The Complete Flow

```text
Browser                      Spring Service                    CAS Server
  |                                |                                |
  | GET /reports                   |                                |
  |------------------------------->|                                |
  |                   No Authentication yet                         |
  |                                |                                |
  |            CasAuthenticationEntryPoint                            |
  | 302 Location: https://sso.example.org/cas/login?                |
  |          service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas    |
  |<-------------------------------|                                |
  |                                                                 |
  | GET /cas/login?service=...                                       |
  |---------------------------------------------------------------->|
  |                               CAS login/TGT/TGC                  |
  |                               CAS issues ST for exact service    |
  | 302 Location: https://app.example.org/login/cas?ticket=ST-xxx   |
  |<----------------------------------------------------------------|
  |                                |                                |
  | GET /login/cas?ticket=ST-xxx   |                                |
  |------------------------------->|                                |
  |                      CasAuthenticationFilter                     |
  |                      creates CasServiceTicketAuthenticationToken|
  |                      AuthenticationManager                      |
  |                      CasAuthenticationProvider                  |
  |                                |                                |
  |                                | GET /cas/serviceValidate       |
  |                                | ?ticket=ST-xxx                 |
  |                                | &service=https://app.../login/cas
  |                                |------------------------------->|
  |                                |     validate ST: service match |
  |                                |<-------------------------------|
  |                         CAS assertion: user alice               |
  |                         UserDetails/authorities                 |
  |                         SecurityContext/HttpSession             |
  | 302 /reports or success URL    |                                |
  |<-------------------------------|                                |
  | GET /reports with application session cookie                    |
  |------------------------------->|                                |
  |<-------------------------------| 200 (if authorized)            |
```

In this example, there is **one fixed callback URL** for issuing and validating the ST. This principle eliminates a common class of bugs: using the business page URL as `service` during login while using the `/login/cas` callback during validation.

### 2.2. What Is the CAS Protocol and How Does It Differ from SAML/OIDC?

The CAS protocol passes **an opaque service ticket string** through the browser `ticket` query parameter. The CAS client uses a backend connection to the CAS Server to validate the ticket and obtain the user's identity, typically via XML at `/serviceValidate` or `/p3/serviceValidate`. Do not attempt to decode an ST like a JWT or SAMLResponse; the ST itself carries no claims for the application to trust. The trust anchor is **the validation result from the CAS Server verified over TLS at the correct endpoint**.

An Apereo CAS IdP may simultaneously support SAML2/OIDC, but when an application uses the **CAS protocol**, the `ServiceProperties`/`CasAuthenticationFilter` beans and the ST flow differ from `saml2Login` or `oauth2Login`. Do not configure a SAML `RelyingPartyRegistration` and expect it to replace CAS `ServiceProperties`.

## 3. `ServiceProperties` Represents the **Application Service**, Not the CAS Server

The `org.springframework.security.cas.ServiceProperties` class holds essential details about the application participating in CAS. According to the Spring Security Java API, the notable properties are:

| Property/Method | Role | Typical Value/Scope |
| --- | --- | --- |
| `setService(String)` / `getService()` | Official **Service URL** of the Spring service | `https://app.example.org/login/cas` |
| `setSendRenew(boolean)` / `isSendRenew()` | Instructs sending `renew` on login/validation, requiring primary credential authentication per CAS semantics | `false` by default |
| `setArtifactParameter(String)` / `getArtifactParameter()` | Name of the request parameter carrying the artifact/ticket | `ticket` by default |
| `setServiceParameter(String)` / `getServiceParameter()` | Name of the CAS service parameter | `service` by default |
| `setAuthenticateAllArtifacts(boolean)` / `isAuthenticateAllArtifacts()` | Enables artifact handling across multiple URLs, useful for proxy tickets in advanced scenarios | Usually left as default `false` for simple ST login |
| `afterPropertiesSet()` | Validates bean configuration during Spring initialization | Does not replace ticket validation |

**Common confusion:** `service` is **not** `https://sso.example.org/cas`. That address is the **CAS Server base URL** used to construct `Cas20ServiceTicketValidator`. Nor is it `https://sso.example.org/cas/login`, because that is where login begins at CAS. And it is not the protected resource URL `/reports` if the filter receives the ST at `/login/cas`.

### 3.1. Minimal Example Declaring ServiceProperties

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.ServiceProperties;

@Configuration
public class CasServicePropertiesConfig {

    @Bean
    ServiceProperties serviceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService("https://app.example.org/login/cas");
        properties.setSendRenew(false);
        return properties;
    }
}
```

This is a Spring configuration class **within an application that has the Spring Security CAS classpath**, not a plain Java program compiled with `javac` without dependencies. A real file needs a package declaration matching the project, such as `package com.example.casdemo;` at the top of the file, saved at `src/main/java/com/example/casdemo/CasServicePropertiesConfig.java`.

`ServiceProperties` is **only one part** of the configuration. With this bean alone, users cannot yet log in with CAS because the entry point, filter, provider, ticket validator, and proper filter chain are still missing.

### 3.2. Why Does `service` Need to Be an Absolute HTTPS URL?

The CAS Server uses `service` as the **ticket return destination**, and simultaneously binds the issued ST to that service identifier. A valid URL needs:

- The `https` scheme matching how browsers actually reach the application.
- The public/canonical hostname permitted by the CAS Server in its **service registry**.
- The actual port when not using the standard HTTPS port, if the real endpoint uses a custom port.
- The context path (if the application is deployed under `/portal`, `/finance`, ...).
- The exact callback path handled by `CasAuthenticationFilter`, usually `/login/cas`.
- Static query parameters only if the architecture intentionally uses them and CAS/service matching has been tested; keep the callback simple and **do not** attach dynamic business query parameters.

The CAS protocol recommends allowing only registered/approved `service` URLs, preferring HTTPS. Do not allow arbitrary websites to attach `?service=https://attacker...` to receive an ST; the CAS service registry configuration must restrict URLs explicitly and require administrative approval.

### 3.3. Three Places Where the Service Identifier Must Stay Consistent

```text
A. Spring ServiceProperties.getService()
   https://app.example.org/login/cas

B. CAS /login?service=...
   https://app.example.org/login/cas

C. CAS /serviceValidate?service=...&ticket=ST-xxx
   https://app.example.org/login/cas

=> A == B == C (per CAS service matching policy)
```

The CAS Server must verify that the `service` used for validation matches the exact service for which the ST was issued. You cannot take a ticket issued for `https://app.example.org/login/cas` and validate it under `http://app-internal:8080/login/cas` or `https://other.example.org/login/cas`.

**Do not append `?ticket=ST-xxx` to `ServiceProperties.service`.** `ticket` is a parameter the CAS server adds to the **browser callback**; when validating, the application sends the ticket as a **separate parameter** alongside the original service identifier value.

## 4. Distinguishing the Service URL from `filterProcessesUrl`

An important invariant is:

```text
ServiceProperties.service =
    "https://app.example.org/portal/login/cas"

CasAuthenticationFilter.filterProcessesUrl =
    "/login/cas"
```

This example is correct when the Servlet application has `context-path=/portal` and the filter matcher applies to the path **inside the context**. The Spring Security filter typically matches the application path corresponding to `/login/cas`; the full URL from the browser adds the scheme, host, and `/portal` context path.

When there is no context path:

```text
ServiceProperties.service =
    "https://app.example.org/login/cas"

CasAuthenticationFilter.filterProcessesUrl =
    "/login/cas"
```

Do not write `setFilterProcessesUrl("https://app.example.org/login/cas")` to mimic `service`, because the filter processes the **in-application request path**, and does not match an absolute URL in standard configuration. Conversely, do not write `setService("/login/cas")` and expect the CAS Server to know the application's host and HTTPS scheme.

### 4.1. Comparing Several Deployments

| Public Deployment | Correct `service` URL | Local `filterProcessesUrl` |
| --- | --- | --- |
| Root context, HTTPS 443 | `https://app.example.org/login/cas` | `/login/cas` |
| Context path `/portal` | `https://app.example.org/portal/login/cas` | `/login/cas` |
| HTTPS port 8443 | `https://app.example.org:8443/login/cas` | `/login/cas` |
| Reverse proxy path prefix `/finance` | `https://app.example.org/finance/login/cas` | `/login/cas` **if** proxy/context mapping makes the servlet see `/login/cas`; verify in practice |
| CAS service running on a separate subdomain | `https://pay.example.org/login/cas` | `/login/cas` |
| Local development `localhost` | `https://localhost:8443/login/cas` with TLS and dev CAS registry | `/login/cas` |

**Note on reverse proxy prefixes:** If the proxy does not strip `/finance` and the servlet sees the prefix in the handled path, the matcher may need adjustment. Do not manually strip paths with `replace` in auth code just to "make it match"; first standardize the ingress, context path, and servlet path configuration. Inspect the Network redirects, request URI, and actual path matcher in tests.

### 4.2. Mismatches That Commonly Cause `INVALID_SERVICE`

```text
https://app.example.org/login/cas
https://app.example.org/login/cas/
http://app.example.org/login/cas
https://app.example.org:8443/login/cas
https://app.example.org/portal/login/cas
https://app-internal:8080/login/cas
```

These URLs must not be treated as the same service identifier simply because their paths contain the word "cas". In particular, scheme, port, path, and trailing slash can make a difference. Some CAS deployments have custom service matching or regex rules; **lenient configuration is not a security fix** to mask a wrong URL. Always export and use a single agreed canonical URL in both the Spring app and the CAS service registry.

## 5. Spring Security CAS Components and Their Responsibilities

| Component | Package (Spring Security) | Responsibility |
| --- | --- | --- |
| `ServiceProperties` | `org.springframework.security.cas` | Configures the service URL, `renew`, and ticket/service parameters |
| `CasAuthenticationEntryPoint` | `org.springframework.security.cas.web` | When unauthenticated, redirects the browser to CAS `/login` with `service` |
| `CasAuthenticationFilter` | `org.springframework.security.cas.web` | Watches the `/login/cas` callback, extracts `ticket`, creates the authentication request |
| `CasAuthenticationProvider` | `org.springframework.security.cas.authentication` | Calls `TicketValidator` to verify the ticket and load authorities/principal |
| `Cas20ServiceTicketValidator` | `org.apereo.cas.client.validation` | Calls CAS `/serviceValidate` with `ticket` and `service` |
| `AuthenticationManager` / `ProviderManager` | `org.springframework.security.authentication` | Dispatches the AuthenticationProvider to process the CAS token |
| `UserDetailsService` or `AuthenticationUserDetailsService` | Spring Security core | Maps the user from the CAS assertion to a local account/authorities |
| `SecurityFilterChain` | `org.springframework.security.web` | Ensures the CAS filter, entry point, security context, and authorization sit properly in the chain |
| `SecurityContextRepository` | `org.springframework.security.web.context` | Persists the successful SecurityContext so subsequent requests carry Authentication |
| `HttpSession` or Spring Session | Servlet/Spring Session | Application session, **distinct** from TGT/TGC on the CAS Server |

### 5.1. Processing Order on Callback

1. Browser sends `GET /login/cas?ticket=ST-...` to the **Spring app**.
2. `CasAuthenticationFilter` has a matcher matching `filterProcessesUrl`, so it extracts the ticket from the default `ticket` request parameter.
3. The filter creates a `CasServiceTicketAuthenticationToken` to pass to `AuthenticationManager`.
4. `CasAuthenticationProvider` invokes the configured `TicketValidator`, passing the **ST + `ServiceProperties.service`** to the CAS validation endpoint.
5. The CAS Server checks that the ST is unexpired, unconsumed, and issued for that service, returning success with the principal or failure such as `INVALID_TICKET`/`INVALID_SERVICE`.
6. The provider builds an authenticated `CasAuthenticationToken` from the CAS assertion and applies user details/authorities as configured.
7. Spring Security saves the `SecurityContext`, creates/rotates the local app session per policy, and redirects the user to the previously requested URL or success URL.
8. Subsequent requests use the app session cookie without replaying the ST.

**Do not create an MVC `@GetMapping("/login/cas")` to call CAS REST manually and create a session by hand.** This endpoint must be handled by the security filter; an MVC controller cannot replace the CAS client's checks.

### 5.2. Important Differences Between Endpoints

`/login/cas` in the application is where the **ticket is received**. `/cas/serviceValidate` on the CAS Server is where the **ticket is validated**. Because the path names look similar, using the wrong host is a serious source of errors. Always specify "server" or "client" clearly in documentation and logs.

## 6. CAS Protocol Endpoints: Choosing the Right Validator

| CAS Server Endpoint | Purpose | When to Use |
| --- | --- | --- |
| `/cas/login` | CAS login, issues a Service Ticket and redirects back to `service` | Browser SSO |
| `/cas/validate` | CAS 1.0 validation returning plain text | Legacy systems; not preferred when attributes are needed |
| `/cas/serviceValidate` | CAS 2.0 validation returning XML, validates a Service Ticket | Standard `Cas20ServiceTicketValidator` |
| `/cas/p3/serviceValidate` | CAS 3.0 validation, can return user attributes | When client/protocol are configured compatibly |
| `/cas/proxyValidate` | Validates Service Tickets and Proxy Tickets per policy | Advanced proxy authentication |
| `/cas/p3/proxyValidate` | CAS 3.0 proxy validation + attributes | Only when proxy is required |
| `/cas/logout` | Terminates the SSO session on the CAS Server | Distinct from the app's local `/logout` |
| `/cas/proxy` | Requests a Proxy Ticket using a PGT | CAS proxy delegation flow, not normal login |

**Do not confuse `/cas/serviceValidate` with `ServiceProperties.service`.** `ServiceProperties.service` is the **application's** URL, usually `https://app.example.org/login/cas`. Meanwhile, the validator takes the base `https://sso.example.org/cas` and calls the corresponding validation endpoint according to the protocol.

### 6.1. Example CAS Validation Request/Response

The CAS Server receives:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-EXAMPLE HTTP/1.1
Host: sso.example.org
```

If the ticket was issued for that exact service and has not been used or expired, the server may return:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

If the `service` value does not match:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    Service identifier does not match the issued ticket.
  </cas:authenticationFailure>
</cas:serviceResponse>
```

This is **illustrative data**, not a real ST or an expected response from a public server. Do not use the literal string `ST-EXAMPLE` expecting login to succeed; CAS accepts only an ST it issued itself within its validity policy.

**CAS `INVALID_SERVICE` is an extremely valuable signal:** immediately inspect the service URL at the entry point, browser callback, and TicketValidator; do not conclude that the user entered the wrong password.

### 6.2. An ST Is Not a Reusable Access Token

Under the CAS protocol, an ST:

- Is issued for **one specific service identifier**.
- Is **single-use upon validation**: CAS must invalidate it after one validation attempt, even if validation fails.
- Usually has a short lifetime; it must not be cached in the application as a long-lived login credential.
- Is carried by the browser in the `ticket` query parameter, risking exposure in browser history, reverse proxy access logs, and Referer headers; exposure must be minimized.
- Must not be passed through a JavaScript client or accepted via a user-supplied API to grant access while skipping backend CAS validation.

When a user refreshes an old callback URL, the already-consumed ST may be rejected. That is replay protection, not the CAS Server losing its session; a new login flow can issue a fresh ST if the TGT/TGC is still valid.

## 7. Spring Boot / Java 17: A Configuration-Complete CAS Demo Application

### 7.1. Dependencies and Versions

This example targets **Spring Boot 3.x compatible with Spring Security 6.5.x**, Java 17+, Servlet/MVC. CAS integration is **not** provided by a dedicated Boot CAS starter; you must add the Spring Security CAS module.

In a Maven project with Spring Boot dependency management, add:

```xml
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
```

This is a **`pom.xml` fragment**, not a standalone runnable POM; the project needs an appropriate parent/BOM, build plugins, and repositories. In the verified versions, `spring-security-cas` depends on Apereo CAS client core; inspect with `mvn dependency:tree` if the project has exclusions or version conflicts, and manage versions via the Spring Boot/Security BOM.

The CAS Server must be a working test environment, not something created automatically by these three dependencies. Use JDK 17+, a CAS Server with HTTPS trusted by the client, a test user `alice`, and a registered service.

### 7.2. `application.yml` Configuration

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    service-url: https://app.example.org/login/cas
```

**Note:** This models an application exposed via an HTTPS reverse proxy at `app.example.org:443`, with the backend listening on HTTP 8080. `forward-headers-strategy: framework` is only appropriate if the reverse proxy **is trusted, strips forwarded headers sent by the browser**, and sets the right headers before forwarding to the app. When running locally without a proxy, `cookie.secure=true` may prevent an HTTP localhost browser from sending the cookie; use a dedicated development profile with TLS/test certificates and matching service URL/registered service. Never disable HTTPS in production just to "make it work".

The `example.org` domains are illustrative placeholders; **replace all of them with a real test CAS/application having real DNS, TLS, and service registry entries**. Without a test CAS Server, the configuration demo cannot complete login.

### 7.3. Spring Security Configuration Class

File `src/main/java/com/example/casdemo/CasSecurityConfig.java`:

```java
package com.example.casdemo;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
        @Value("${app.cas.service-url}") String serviceUrl) {

        ServiceProperties properties = new ServiceProperties();
        properties.setService(serviceUrl);
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    TicketValidator ticketValidator(
        @Value("${app.cas.server-base-url}") String casBaseUrl) {

        return new Cas20ServiceTicketValidator(casBaseUrl);
    }

    // Lab only: this account already exists in test CAS.
    // CAS verifies identity; UserDetailsService assigns local authorities.
    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused-for-cas")
                .roles("USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
        ServiceProperties properties,
        TicketValidator validator,
        UserDetailsService users) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(properties);
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        provider.setKey("cas-demo-provider-v1");
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain casWeb(
        HttpSecurity http,
        ServiceProperties properties,
        CasAuthenticationProvider provider,
        SecurityContextRepository contextRepository,
        @Value("${app.cas.login-url}") String casLoginUrl)
        throws Exception {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setServiceProperties(properties);
        entryPoint.setLoginUrl(casLoginUrl);

        // DO NOT declare this Filter as a @Bean so Spring Boot
        // does not auto-register an extra servlet Filter outside the chain.
        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setServiceProperties(properties);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setSecurityContextRepository(contextRepository);
        casFilter.setAuthenticationFailureHandler(
            new SimpleUrlAuthenticationFailureHandler("/cas-error"));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out",
                    "/cas-error", "/error").permitAll()
                .requestMatchers("/reports/**").hasRole("USER")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        http.addFilterAt(casFilter, CasAuthenticationFilter.class);
        return http.build();
    }
}
```

**Part-by-part explanation:**

- `ServiceProperties.service` is read from `app.cas.service-url`, never dynamically generated from a raw `Host` header.
- `Cas20ServiceTicketValidator` takes the **CAS Server base URL** to call `/serviceValidate`, not the app's callback URL.
- `CasAuthenticationProvider` verifies the ST through the validator and uses `UserDetailsService` to load local authorities. The demo password `{noop}unused-for-cas` **is not used for CAS authentication**; it is simply an explicit lab user fixture, not guidance for storing production passwords.
- `CasAuthenticationEntryPoint` redirects to CAS login with the exact service from `ServiceProperties`.
- `CasAuthenticationFilter` watches `/login/cas`, uses `ProviderManager`, and persists `SecurityContext` through the repository shared with the chain.
- `setFilterProcessesUrl("/login/cas")` is the **filter path**, distinct from `https://app.example.org/login/cas` which is the **service URL**.
- `http.addFilterAt(casFilter, CasAuthenticationFilter.class)` places the CAS filter into the security chain. The filter is **instantiated inside** the chain method instead of being exposed as a `@Bean`, preventing Spring Boot from auto-registering it as a global servlet filter and risking double ticket processing.
- `CasAuthenticationProvider` remains a configuration bean; the `ProviderManager` for the CAS filter has a single provider and does not require a password/form-login provider.
- `SecurityContextRepository` is assigned consistently so that authentication after the CAS callback persists across subsequent requests in `HttpSession` when configured properly.
- `requestMatchers("/reports/**").hasRole("USER")` only illustrates authorization. Production must verify user/account status, tenant/role/resource, and the application's own policies.
- `/cas-error` and `/signed-out` are only marked `permitAll`, and **do not yet have MVC pages automatically**; controllers/templates must be provided as shown in the next section.
- Local `/logout` **does not** automatically invoke CAS Server logout/SLO. With CSRF enabled, logout should use **POST with a CSRF token**.
- The `/login/cas` callback **must not** be added to `web.ignoring`, excluded from the chain, or handled by a manual controller.
- Spring Security does not automatically guarantee that a CAS username matches a user account in your DB or belongs to the right tenant; the demo only has `alice`. Production requires a `UserDetailsService` reading users/authorities from a controlled internal source.

**Version dependency:** Spring Security 6.x uses the Jakarta Servlet API and provides the methods shown above. APIs across Spring Security 6.x/7.x, transitive CAS client dependencies, and Boot versions may change; consult Javadocs and build with the project's exact BOM before applying. This is a Spring class inside a project, not standalone code that compiles with the JDK without dependencies.

### 7.4. Controller and Spring Boot Application Class

File `src/main/java/com/example/casdemo/CasDemoApplication.java`:

```java
package com.example.casdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/casdemo/DemoController.java`:

```java
package com.example.casdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "Public CAS demo page");
    }

    @GetMapping("/reports")
    public Map<String, String> reports(Authentication authentication) {
        return Map.of(
            "message", "Protected report",
            "principal", authentication.getName());
    }

    @GetMapping("/cas-error")
    public Map<String, String> casError() {
        return Map.of("status", "CAS authentication failed");
    }

    @GetMapping("/signed-out")
    public Map<String, String> signedOut() {
        return Map.of("status", "Local application session ended");
    }
}
```

**Prerequisites:** A compatible Spring Boot Maven/Gradle app, a test IdP/CAS Server, an HTTPS reverse proxy, service registration, and user `alice` on both the CAS Server and local fixture. If CAS returns a different principal, the lab will fail at `UserDetailsService` even if CAS verified the ticket; that is a separate **authorization/local mapping step**, not a reason to skip ticket validation.

### 7.5. Running Integration Tests

In a project with the Maven wrapper and a valid test CAS Server configured:

```bash
./mvnw spring-boot:run
```

On Windows you can use `mvnw.cmd spring-boot:run`. Before opening the browser, verify that the public reverse proxy `https://app.example.org` actually routes to backend port 8080, the service URL is in the CAS registry, the CAS login URL is reachable, and the Java truststore trusts the CAS Server's TLS certificate.

Without a test CAS Server, you can only run up to the redirect step or observe validation failures; **no Spring Boot command automatically turns this example into a CAS Server**. Testing against a real system must take place in an authorized staging environment.

## 8. Configuring the Service Registry on the CAS Server

The CAS Server typically maintains a **service registry** specifying which applications are allowed to request CAS login/tickets. To use `https://app.example.org/login/cas`, CAS must have a matching registration in the format/management API appropriate for your actual CAS version.

**Conceptual policy example:**

```text
Registered service:
  id              = app-cas-demo
  serviceId        = https://app.example.org/login/cas
  enabled          = true
  owner            = team-app
  redirect / CAS protocol allowed = per policy
  permitted authentication policy = per contract
```

Across many Apereo CAS versions, `serviceId` in a RegisteredService may be a **regular expression** or controlled by CAS's matching strategy; thus, the example above represents **registration intent**, not a claim that every CAS Server lets you copy this YAML verbatim into production.

**If using a regex**, escape dots, anchor the start/end, and restrict HTTPS/hostname/path. Overly broad regexes such as `.*`, `https?://.*`, or `https://.*example.org/.*` can accept services controlled by others or look-alike hosts. Registrations must be approved by an authorized administrator, never taken from the browser or an unverified ticket.

### 8.1. Client Configuration Alone Is Insufficient If the CAS Server Has Not Registered the Service

Sequence:

1. The app determines a fixed `serviceUrl`.
2. The CAS admin registers **that exact public URL** with the appropriate policy.
3. Verify the browser redirect actually receives `/cas/login?service=...`.
4. Verify `/serviceValidate?service=...`.
5. Check `INVALID_SERVICE`/unauthorized service logs if CAS refuses to issue or validate a ticket.
6. Lock down configuration in **both places** before testing with a user group.

Not every `INVALID_SERVICE` error is caused by a missing registration; CAS might issue an ST for one URL while the validator validates the ST under a different URL. Determine whether the error occurs on the **login request** or the **validate request** to pinpoint the right side.

## 9. Reverse Proxy / Ingress and Wrong Public URLs

Typical deployments look like:

```text
Browser
  |
  | HTTPS https://app.example.org/login/cas
  v
Reverse proxy / Ingress :443
  |
  | HTTP http://app-backend:8080/login/cas
  v
Spring Boot :8080
  |
  | HTTPS https://sso.example.org/cas/serviceValidate
  v
CAS Server
```

If the application constructs `service` dynamically from `request.getScheme()`/`getServerName()` on the backend, it can become `http://app-backend:8080/login/cas`. The CAS Server issued the ticket using `https://app.example.org/login/cas`, while validation uses the internal address, causing `INVALID_SERVICE`.

### 9.1. Safe Configuration Practices

- For a **single stable service URL**, prefer explicit configuration `app.cas.service-url=https://app.example.org/login/cas` and share the same `ServiceProperties` across entry point, filter, and provider.
- Let the reverse proxy manage TLS/Host/port/path rewrites. Only trust `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-Port` coming from approved proxies, stripping any values supplied by the browser.
- Ensure `server.forward-headers-strategy` matches the topology; **do not treat enabling it as a silver bullet** if the proxy forwards spoofed headers or the app uses a wrong hard-coded URL.
- Verify the context path and `filterProcessesUrl` received on the Spring app. If the proxy adds a prefix, determine explicitly which layer strips it.
- Never alter `ServiceProperties.service` based on raw `Host`/`Referer` headers or user-supplied query parameters.
- Never add internal HTTP URLs to the CAS service registry just to "fix" production HTTPS.
- Never disable service matching or accept arbitrary CAS Server certificates when encountering SSL/TLS errors.
- If serving multiple vanity domains, design each allowed service/tenant against a verified registry instead of dynamically assembling hosts from requests.

### 9.2. Network Debugging Checklist

In browser DevTools Network (test environment):

1. `GET /reports` -> app returns 302 to CAS login.
2. Decode the `service` query param in `Location`: it must be `https://app.example.org/login/cas`.
3. CAS login completes -> `Location` returns to **the same service** with `?ticket=...`.
4. Browser sends GET to the exact callback without being redirected to another host/HTTP/path before the filter handles it.
5. Backend calls CAS validation with **the same service**. Inspect server-side debug logs via safe configuration; **never log real tickets**.
6. CAS returns success or a failure code.
7. App establishes `Authentication`/HttpSession and redirects to `/reports`; the resource enforces the expected role/user.

If you only see the browser reach `/login/cas?ticket=...` and get a 404, most likely the CAS filter is not in the right chain, the path matcher is wrong, the app has a different servlet context path, or the security config was overridden.

## 10. Securing Tickets in URLs, Logs, and Redirects

### 10.1. A Ticket Is a Sensitive Credential, Even If Single-Use

The browser receives the callback:

```text
https://app.example.org/login/cas?ticket=ST-example
```

The risk is that the ST can appear in:

- Access logs of ingress/reverse proxy/CDN/WAF.
- Browser history, address bar, and screen recordings.
- Monitoring/tracing query strings.
- `Referer` headers sent to external resources if the callback is not handled and redirected properly.
- Crash/report attachments shared by users.
- Cache/analytics pipelines.

**Controls:**

1. Enforce HTTPS for the CAS Server, SP callback, and validation.
2. Never log raw `ticket` query parameters; log only request ID, failure category, service registration ID, and a controlled hash if event correlation is needed.
3. Keep the callback as a filter endpoint, validate the ST immediately, and redirect to a URL without the ticket.
4. Set an appropriate `Referrer-Policy`, such as `no-referrer` on sensitive URLs, and avoid loading third-party assets on the callback.
5. Block open redirects when handling saved requests; never forward an ST to another host via an untrusted `redirect` parameter.
6. Do not let clients/browsers call `/serviceValidate` directly with unnecessary secrets; the application backend must use trusted TLS.
7. At WAF/ingress layers, allow `ticket` on the **restricted** callback path without logging or echoing it back.
8. Never store the ticket in application cookies or JavaScript `localStorage` to maintain a session.

### 10.2. Service Ticket Replay

A CAS ST is issued for one service and is valid for **one validation only**. Once the validator consumes the ST, another GET to the callback with the same ST must fail. To log in again, the app initiates a new CAS login flow; CAS can issue a new ST if the TGT/TGC is still active on the CAS Server.

Do not use `CasAuthenticationProvider`/ticket validator to "verify" an ST repeatedly like a bearer token. If the app needs to call downstream backend services, use an authorized **CAS proxy ticket** model or OAuth2 per your architecture; never replay app A's browser ST to app B.

## 11. `sendRenew`: Requiring CAS Reauthentication, Not Changing the Service URL

`ServiceProperties#setSendRenew(true)` directs CAS login/validation to include the `renew` parameter per the CAS protocol. The default is `false`.

- **`false`:** CAS may use the existing SSO TGT/TGC to issue a new ST, usually without prompting the user for a password again.
- **`true`:** instructs CAS not to rely solely on the existing SSO session; the user must authenticate with primary credentials per CAS semantics/policy, and ticket validation must check the `renew` condition.
- Do not assume `renew=true` equals phishing-resistant MFA or any specific assurance level. If business rules require MFA, establish a separate CAS authentication policy/attribute assurance contract.
- `renew` **does not change** `ServiceProperties.service`, `filterProcessesUrl`, or the CAS validation base URL.
- `renew=true` also does not revoke an active local application session; to force fresh authentication when a user already has a session, the app must actively initiate a **new authentication flow** rather than merely setting the property and waiting.

**Note:** `gateway` is used for passive SSO checks and has different semantics; the CAS protocol states that `gateway` and `renew` are incompatible. Do not enable both by guesswork.

## 12. Multiple Applications, One CAS Server

```text
CAS Server: https://sso.example.org/cas
          |
          +-- App A service https://reports.example.org/login/cas
          |
          +-- App B service https://hr.example.org/login/cas
          |
          +-- App C service https://pay.example.org/portal/login/cas
```

All three apps may share a CAS SSO session, yet they have **different service identifiers** and **different STs**. An ST issued for App A must not validate at App B; CAS must enforce service binding. Therefore, you cannot copy `ServiceProperties.service` verbatim from A to B, even though they share the same CAS Server base URL.

Each app creates its own **local HttpSession** after CAS validation. When App A performs a local logout, the CAS TGT/TGC may remain valid and App B keeps its session; that is a session/logout concern, not a misconfigured `ServiceProperties`.

### 12.1. Multiple Tenants and Service URLs

If a single Spring app serves multiple tenants, distinguish between:

- One fixed service URL shared across all tenants, checking tenant membership after authentication.
- Multiple service URLs/hostnames/callbacks registered individually in CAS per tenant.
- Multiple CAS Servers for different partners (each with its own trust boundary and service registration).

A simple `ServiceProperties` with one static `service` fits the **single service URL** model. If the service identifier must vary by tenant, do not mutate `setService(...)` on a singleton bean per request: that introduces race conditions and mixes tenants/issuers. Design an approved resolver/registry, request correlation, and exact-service validation while preventing cross-tenant ticket acceptance.

For dynamic/Proxy Ticket scenarios, Spring Security provides `ServiceAuthenticationDetailsSource`, `ServiceAuthenticationDetails`, and `authenticateAllArtifacts` as an advanced model; **do not enable them casually**, because they widen the set of URLs that can process tickets. Every allowed service must map to a verified tenant/registration, never derived from a raw `Host` header or browser-chosen URL.

## 13. Plain Java 17: Seeing the Three URLs and Exact Matching Clearly

This program runs on JDK 17 **without Spring or a CAS Server**. It simulates building a URL-encoded login URL with `service` and comparing service identifiers across configurations. It **does not create a real ST, call `/serviceValidate`, or authenticate a user**.

File `CasServiceUrlDemo.java`:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public final class CasServiceUrlDemo {

    private static final String CAS_BASE =
        "https://sso.example.org/cas";

    private static final String SERVICE =
        "https://app.example.org/login/cas";

    private static final String FILTER_PATH = "/login/cas";

    static String casLoginUrl(String base, String service) {
        return base + "/login?service=" +
            URLEncoder.encode(service, StandardCharsets.UTF_8);
    }

    static boolean exactMatch(String expected, String actual) {
        return expected.equals(actual);
    }

    public static void main(String[] args) {
        System.out.println("registered=" + SERVICE);
        System.out.println("login=" +
            casLoginUrl(CAS_BASE, SERVICE));
        System.out.println("filterPath=" + FILTER_PATH);

        System.out.println("matchExact=" +
            exactMatch(
                SERVICE,
                "https://app.example.org/login/cas"));

        System.out.println("httpDiff=" +
            exactMatch(
                SERVICE,
                "http://app.example.org/login/cas"));

        System.out.println("slashDiff=" +
            exactMatch(
                SERVICE,
                "https://app.example.org/login/cas/"));

        System.out.println("contextDiff=" +
            exactMatch(
                SERVICE,
                "https://app.example.org/portal/login/cas"));

        System.out.println("callbackWithTicket=" +
            SERVICE + "?ticket=ST-TEST");

        System.out.println("validationService=" + SERVICE);
    }
}
```

Compile and run commands:

```bash
javac --release 17 CasServiceUrlDemo.java
java CasServiceUrlDemo
```

Deterministic stdout:

```text
registered=https://app.example.org/login/cas
login=https://sso.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas
filterPath=/login/cas
matchExact=true
httpDiff=false
slashDiff=false
contextDiff=false
callbackWithTicket=https://app.example.org/login/cas?ticket=ST-TEST
validationService=https://app.example.org/login/cas
```

**Lesson:** When the CAS Server issues an ST for `SERVICE`, validation must resend `SERVICE`; the callback URL with `ticket` appended is the **browser request**, not the service value the validator should send. URL-encoding the `service` parameter is a **query representation**, not a new identifier.

`exactMatch` illustrates strict comparison between **administrator-approved strings**. It **does not replace** a parser, CAS service registry, CAS server `TicketValidator`, or production URL-handling policy. Do not strip queries, drop trailing slashes, change schemes, lowercase entire URLs, or "normalize" arbitrarily to accept an ST for the wrong service.

## 14. Practical Testing: Distinguishing Browser, Callback, and Server-Side Validation

Prepare a test CAS Server with the right registered service and user `alice`. Use browser DevTools Network and application logs with tickets redacted. Never use production tickets in public sample commands.

### 14.1. Happy Path

1. Browser calls `GET https://app.example.org/reports` without an app session.
2. Spring uses `CasAuthenticationEntryPoint` to return a 302 redirect to `https://sso.example.org/cas/login?service=...`.
3. Decoding `service` shows `https://app.example.org/login/cas`, not `/reports` or an internal HTTP URL.
4. CAS Server checks the registered service; the user logs in or has a valid CAS SSO session.
5. CAS redirects the browser back to `https://app.example.org/login/cas?ticket=ST-...`.
6. Spring `CasAuthenticationFilter` receives the callback on `/login/cas`.
7. The backend calls `https://sso.example.org/cas/serviceValidate` with the ticket and `service=https://app.example.org/login/cas`.
8. CAS Server returns `authenticationSuccess`; principal `alice` is mapped locally to `ROLE_USER`.
9. Spring establishes Authentication/app session and redirects to `/reports`, returning HTTP 200 with no ST left in the URL.
10. Refreshing `/reports` authenticates via the app session without revalidating the ST.

**QA evidence:** The ST is consumed **exactly once**, success originates from the CAS Server, the new app session works, and the user receives no privileges beyond local policy.

### 14.2. Checking Redirects Only, Without a Real ST

You can inspect the login redirect from a machine authorized to reach staging:

```bash
curl -I https://app.example.org/reports
```

Expect `302` and `Location` pointing to CAS login with the encoded service; in practice, `GET` may return `302` while `HEAD` behaves differently depending on the app/proxy. If `HEAD` is not representative, use `curl -i -o /dev/null -D - https://app.example.org/reports` or a browser.

**Do not manually GET `/serviceValidate?ticket=ST-TEST` and expect success.** Fake or already-consumed STs must be rejected. To verify the validator across a test matrix, have test CAS issue real STs and observe the real integration; each ticket is single-use.

## 15. Test Matrix for STs and Service Identifiers

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| **Correct callback** | Both `ServiceProperties.service` and CAS registered service are the HTTPS app URL, filter `/login/cas` | Login succeeds if ST is valid |
| **Wrong scheme** | CAS issues ST for HTTPS, validation sends HTTP | `INVALID_SERVICE`, no session created |
| **Wrong host** | CAS issues for `app.example.org`, validation sends `app-internal` | Rejected |
| **Wrong port** | CAS issues for `:8443`, validation omits port | Rejected if service does not match policy |
| **Wrong context path** | CAS issues `/portal/login/cas`, validator uses `/login/cas` | Rejected |
| **Wrong trailing slash** | CAS issues `/login/cas`, validator sends `/login/cas/` | Not treated as equivalent arbitrarily |
| **Wrong filter matcher** | CAS callback `/login/cas`, filter watches `/cas/login` | CAS filter ignores ST; login fail/404/loop |
| **Filter not in chain** | Config creates bean without adding it to the right SecurityFilterChain | ST is not authenticated |
| **Validating same ST twice** | ST already verified by CAS, validate called again | `INVALID_TICKET` / replay prevented |
| **Expired ST** | Ticket exceeds CAS lifetime window | Rejected |
| **ST from another CAS Server** | App points validator at a server that did not issue the ticket | Rejected |
| **Unmatched CAS registered service** | Service not in allowlist | CAS rejects service/ticket |
| **Browser has CAS TGT/TGC but no app session** | Access `/reports` | Can SSO again to obtain a new ST and new app session |
| **CAS user absent from local user registry** | CAS validation succeeds for user not permitted by app | No authorized app Authentication granted; demo code may fail |
| **Insufficient business permissions** | CAS principal verified but lacks `ROLE_USER`/tenant permission | `403` or resource denied |
| **Untrusted CAS Server HTTPS cert** | Backend fails to verify CAS TLS | Connection/validation fails; never enable trust-all |
| **Callback with fake ticket** | `?ticket=ST-FAKE` | Rejected, no session created |
| **App behind reverse proxy** | Browser HTTPS, backend HTTP, fixed canonical service | Succeeds if trust/callback routing is right |
| **Host header injection** | Client sends forged Host/Forwarded to alter service | Approved service value must not change |
| **Unknown business query parameter** | Browser appends `?next=https://evil...` to callback | No open redirect or service alteration |
| **CSRF/logout** | App logout via POST with CSRF | Local session destroyed; CAS session may remain |

**Isolating one variable per test:** To prove `INVALID_SERVICE`, test CAS must issue a valid ST for service A and then attempt validation with service B per policy; do not use an expired or fake ST because `INVALID_TICKET` will mask the root cause. Because STs are single-use, each negative case needs a **fresh ticket**.

## 16. Fast Symptom-Based Diagnostics

| Symptom | Common Causes | How to Check and Fix |
| --- | --- | --- |
| CAS login succeeds but app loops back to login | Service URL mismatch, session cookie not saved, provider/filter error | Compare the three service values, app session, and cookie |
| CAS Server reports `INVALID_SERVICE` | `service` differed between ticket issuance and validation; or server service registry denies it | Check `Location`, registered service, and validation request |
| App callback returns 404 | CAS filter does not match, missing from chain, wrong context path/proxy rewrite | Check `filterProcessesUrl` vs servlet path and Spring Security chain |
| App callback returns 403 | Other Spring Security/CSRF rule, HTTP method, WAF, or blocked route | Check filter chain, HTTP method, origin, and CSP/WAF |
| ST gets `INVALID_TICKET` | ST expired, already used, wrong server, fake ticket, or renew policy | Use a fresh ST issued by test CAS; do not retry the same ST |
| CAS Server `/serviceValidate` hits TLS error | JVM truststore does not trust CAS Server, hostname mismatch, MITM proxy | Install proper trust chain, verify FQDN, never disable TLS |
| Backend tries calling `https://app.example.org/serviceValidate` | Confused client service URL with CAS server validation URL | Validator must use the CAS base URL |
| Filter uses full URL in `setFilterProcessesUrl` | Confused request path with service identifier | Use local `/login/cas`; `service` is the absolute HTTPS URL |
| Ticket validates but user lacks access | `UserDetailsService` cannot find principal, local role/tenant policy denies | Check local mapping/entitlement; never skip CAS validation |
| App loses session after CAS callback | `SecurityContextRepository` not persisted, wrong `Secure`/`SameSite` cookie, session store error | Check repo and `Set-Cookie`/Session ID/HTTPS |
| Callback processed twice | CAS filter is both a Boot servlet bean and a filter inside Spring Security chain | Register only inside the chain or disable servlet auto-registration |
| App runs under `/portal` but service lacks prefix | Context path/proxy differs from public URL | Use public service `/portal/login/cas` and matching local filter path |
| Browser auto-SSOs again after local logout | CAS TGT/TGC still exists | Distinguish local logout from CAS global/SLO |
| No user prompt despite re-login requirement | `sendRenew=false` and valid CAS SSO session exists | Evaluate `sendRenew=true` + CAS auth policy; do not assume MFA |
| Overly broad service matching | CAS allow-all or unanchored regex | Tighten service registry and prevent open redirects |
| Multi-tenant app uses another tenant's service | Singleton `ServiceProperties` mutated per request | Design isolated registry/binding and test cross-tenant |
| Ticket appears in access logs | Proxy logs raw query string | Redact ticket, check Referer/retention, and update logging policy |
| Error occurs on one pod only | Differing config/service URL/cookie/session store | Compare release, env vars, routes, truststore, Session/Redis |
| CAS Server reports no registered service | CAS service registry unconfigured, wrong URI/regex | Register exact HTTPS callback and review policy |

### 16.1. Decision Tree for Login Failures

```text
A. Did the browser receive a 302 to CAS login?
   |
   +-- No: SecurityFilterChain / EntryPoint / protected matcher.
   |
   +-- Yes: decode ?service=...
         |
         +-- Does service equal the approved HTTPS URL?
               |
               +-- No: fix ServiceProperties / proxy / config.
               |
               +-- Yes: did CAS allow the service and issue an ST?
                     |
                     +-- No: CAS registry, IdP/TLS policy.
                     |
                     +-- Yes: did the browser GET callback /login/cas?ticket?
                           |
                           +-- No: DNS, redirect, context, ingress.
                           |
                           +-- Yes: did CasAuthenticationFilter run?
                                 |
                                 +-- No: matcher/filter chain.
                                 |
                                 +-- Yes: what did backend /serviceValidate return?
                                       |
                                       +-- INVALID_SERVICE: compare service strings exactly.
                                       +-- INVALID_TICKET: ST expiry/replay/server.
                                       +-- TLS/network fail: truststore, hostname.
                                       +-- success: local UserDetails/authorities,
                                                    SecurityContext/session/roles.
```

A system can have **multiple bugs at once**. If fixing the service URL still leaves a login loop, check session persistence and session cookies instead of loosening service matching.

## 17. CAS Proxy Tickets Are a Separate Feature—Do Not Enable Just for Regular Login

Spring Security CAS supports applications that need to act on behalf of a user when calling downstream CAS services via **proxy tickets (PT)**. This additionally uses:

- `Cas20ProxyTicketValidator` / `/proxyValidate`.
- `proxyReceptorUrl` on the application so the CAS Server can deliver a Proxy-Granting Ticket (PGT).
- `ProxyGrantingTicketStorage` with lifecycle/cleanup.
- `ServiceAuthenticationDetailsSource` when validating tickets against dynamic service URLs.
- `ServiceProperties.authenticateAllArtifacts` when genuinely needing to handle artifacts outside the default callback.
- An authorized proxy chain allowlist; **never** use `acceptAnyProxy=true` in production.

**Core warning:** `proxyReceptorUrl` is **not** the basic `filterProcessesUrl` and is not a standard app's `ServiceProperties.service`. The PGT callback is a separate protocol endpoint, typically requiring HTTPS with strict TLS/PKIX verification. If you only need CAS login and an `HttpSession`, **do not configure PGT/proxy receptor** because it increases attack surface and the number of endpoints to protect.

If Proxy Tickets are genuinely needed, write a dedicated design using the CAS protocol docs and exact-version Spring Security CAS Javadocs; never turn on `authenticateAllArtifacts=true` just to work around a callback 404 or `INVALID_SERVICE`.

## 18. CAS Local Logout, SSO Logout, and Authentication Freshness

Local `POST /logout` on the app:

- Destroys the app's own `HttpSession`/`SecurityContext`.
- Does not automatically destroy the CAS TGT/TGC at `sso.example.org`.
- When revisiting the app, the user may be issued a fresh ST by CAS based on the TGT/TGC and log back in without re-entering a password.

CAS Server `/cas/logout`:

- Terminates/coordinates the CAS SSO session per configuration and CAS SLO.
- Does not automatically clear every service's local session if those services do not receive or handle SLO notifications.
- Is not `ServiceProperties.service` and does not replace the CAS callback.

For sensitive transactions, `ServiceProperties.sendRenew=true` can request primary-credential reauthentication per CAS, but **does not guarantee MFA level or session freshness for every application**. Business policies may require assurance context, transaction binding, and separate authorization checks rather than merely checking that the user holds a CAS ST.

## 19. Minimum Security Baseline for a CAS Client

1. **Strict HTTPS** between browser–service and service–CAS; backend verifies the CAS Server's TLS certificate without disabling hostname verification.
2. **CAS service registry allowlist** with exact or carefully anchored regexes, hostname/path ownership, and approval.
3. **Fixed canonical service** from trusted configuration, never constructed from client-controlled raw `Host`/`X-Forwarded-*` headers.
4. **CAS Filter inside SecurityFilterChain**, never `web.ignoring` the callback and never writing a custom controller to accept STs.
5. **Backend CAS validation** with the exact service identifier; never trust an opaque ticket solely because it has an `ST-` prefix.
6. **Single-use tickets**, failing closed on replay, expired tickets, or validation failures.
7. **CSRF protection** on state-changing session-cookie actions; the CAS GET callback is handled by the protocol, not an excuse to disable CSRF everywhere.
8. **Session fixation protection** and `Secure`, `HttpOnly`, `SameSite` cookies matching HTTPS topology; never URL-rewrite `JSESSIONID`.
9. **Redact ST** in logs/tracing/query metrics; appropriate `Referrer-Policy` and `no-store` on redirects/callbacks.
10. **User identity/authorization** after ticket validation; internal membership/roles must not be inferred from unapproved email/groups.
11. **Local logout != CAS SSO logout**; if SLO is needed, design it explicitly and test partial failures.
12. **Multi-tenant binding**: correct source/issuer/service URL and tenant context; never share tickets or local sessions across organizations.
13. **Monitored timeouts/availability** for CAS validation; if CAS is unavailable, never issue sessions from unvalidated tickets.
14. **Rate limiting and anomaly monitoring** on CAS login/callback/validation; never log tickets verbatim.
15. **Change management** for changes to service URL, context path, reverse proxy, CAS hostname, truststore, or service registry.
16. **Regression tests** for exact URL matching, wrong service, expired/replayed ST, filter matcher, and session persistence after every deploy.

## 20. Practice Exercises and Answers

**Question 1.** The CAS Server URL is `https://sso.example.org/cas`, and the app runs publicly at `https://portal.example.org/app` with callback `/app/login/cas`. What should `ServiceProperties.service` be?

**Answer:** `https://portal.example.org/app/login/cas`. `https://sso.example.org/cas` is only used as the CAS server base URL for the validator; the local filter matcher is usually `/login/cas` inside context `/app`.

**Question 2.** Spring configures `ServiceProperties.service=https://portal.example.org/login/cas` but `CasAuthenticationFilter.filterProcessesUrl=/cas/login`. The browser returns to `/login/cas?ticket=...`. What happens?

**Answer:** The filter does not match the callback; the ST goes unprocessed, resulting in a 404, redirect loop, or no `Authentication` created. Change `filterProcessesUrl` to `/login/cas`; do not change `service` to the CAS Server login URL.

**Question 3.** CAS issues an ST for `https://portal.example.org/login/cas`, but the Java validator sends `service=http://portal-internal:8080/login/cas`. Why does login fail?

**Answer:** **`INVALID_SERVICE`** because the service identifiers do not match. Use the canonical HTTPS URL consistently and fix proxy/config; do not open the CAS service registry to arbitrary hosts.

**Question 4.** `GET /login/cas?ticket=ST-REAL` was just validated successfully by Spring. The user refreshes the old callback URL; CAS returns `INVALID_TICKET`. Is CAS broken?

**Answer:** Not necessarily. STs are single-use and already consumed. The app should redirect after login so the URL does not retain the ticket; revisiting protected resources will use the local session or start a new CAS flow if the session is gone.

**Question 5.** Can an `@GetMapping("/login/cas")` controller read the ticket itself and mark `SecurityContext` authenticated if the string starts with `ST-`?

**Answer:** No. The CAS filter/provider/validator must validate the ticket with the CAS Server, verify the exact service, and apply local identity/authorization.

**Question 6.** Does `ServiceProperties.sendRenew=true` automatically enable MFA and cause the CAS Server to revoke old local sessions of all applications?

**Answer:** No. `renew` requests CAS reauthentication per primary-credentials semantics; it does not assert an MFA level and does not revoke other `HttpSession` instances.

**Question 7.** A multi-tenant app mutates `ServiceProperties.service` on a singleton bean based on `X-Forwarded-Host` from the browser on every request. Is this safe?

**Answer:** No. It risks Host header injection, tenant mix-ups/race conditions, and validating tickets under the wrong service. Use verified service/tenant mappings and request correlation if multiple services are genuinely required.

**Question 8.** Only the public port changes from 443 to 8443 while the backend port stays the same. Which configurations need review?

**Answer:** `ServiceProperties.service`, CAS registered service, reverse proxy, browser `Location` callback, actual filter matcher, TLS, and URL policy. The service URL may need `:8443`; do not only modify backend `server.port`.

## 21. Deployment Acceptance Checklist

- [ ] Three URLs defined: CAS Server base, CAS login, **application service callback**; no confusion between host/server/client.
- [ ] `ServiceProperties.service` is the public absolute HTTPS URL with accurate scheme/port/context/path.
- [ ] `CasAuthenticationFilter.filterProcessesUrl` matches the local path of the `service` callback, defaulting to `/login/cas` at root context.
- [ ] `CasAuthenticationEntryPoint` and `CasAuthenticationProvider` share the **same ServiceProperties**; validator calls the right CAS server base.
- [ ] CAS service registry has registered the **exact service URL** with an owned policy, no allow-all service IDs.
- [ ] `ticket` is not added to the service URL configuration; the browser callback carries `ticket` while backend validation sends the original service value.
- [ ] ST is verified once by CAS; a second validation attempt is rejected.
- [ ] CAS login and ticket-validation endpoints reside on the **CAS Server**; the callback filter resides on the **Spring app**.
- [ ] Boot app has `spring-security-cas` and compatible CAS Client dependencies; dependency tree/BOM verified.
- [ ] CAS filter is registered only in the Spring Security chain; not auto-registered twice as a global Filter bean.
- [ ] Successful authentication is persisted to `SecurityContext`/`HttpSession`; session fixation/CSRF/cookie policies are in place.
- [ ] CAS user maps to local account/roles/tenant membership per policy, without granting global access automatically.
- [ ] Reverse proxy accepts forwarded headers only from trusted hops; canonical host/service is consistent.
- [ ] TLS verification is not disabled and internal HTTP is not registered as a production service.
- [ ] ST, raw queries/cookies, and ticket-validation secrets are never logged; appropriate `no-store`/`Referrer-Policy` applied.
- [ ] Tested happy path, invalid service, wrong path/port/scheme, expired/replayed ST, CAS outage, SSL failure, and missing local user.
- [ ] `sendRenew` and CAS SSO/global logout are understood as distinct mechanisms; local logout is not treated as CAS logout.
- [ ] If proxy tickets/PGT are needed, dedicated design/tests exist instead of turning on `authenticateAllArtifacts` casually.
- [ ] Tested across multiple pods/tenants/context paths and regressed after ingress, cert/truststore, or registered service changes.
- [ ] Runbook exists to compare the three `service` values at login, callback, and validation when diagnosing `INVALID_SERVICE`.

**Conclusion:** CAS integration with Spring Security succeeds when **one fixed, CAS-registered `ServiceProperties.service`** points to the application callback endpoint handled by `CasAuthenticationFilter`, and `CasAuthenticationProvider`/`TicketValidator` verifies the ST with the CAS Server using **that exact same service identifier**. Understanding the boundary between the absolute URL and the local filter path—while preserving single-use ticket validation, HTTPS, session management, and application authorization—prevents login loops, `INVALID_SERVICE` errors, and the risk of accepting tickets meant for another service.

## 22. Official References

1. [Spring Security – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `ServiceProperties`, CAS interaction sequence, `CasAuthenticationEntryPoint`, filter/provider, and validator.
2. [Spring Security 6.5 API – CasAuthenticationFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): `/login/cas` callback and ticket processing.
3. [Spring Security API – ServiceProperties](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html): `service`, `sendRenew`, `ticket`/`service` parameters, and `authenticateAllArtifacts`.
4. [Spring Security API – CasAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationEntryPoint.html): CAS login redirect/service URL.
5. [Spring Security API – CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): `TicketValidator`, `UserDetailsService`, and CAS authentication methods.
6. [Spring Security – Project Modules/Dependencies](https://docs.spring.io/spring-security/reference/6.5/modules.html): `spring-security-cas` module and Apereo CAS client.
7. [Apereo CAS – Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `service`, `ticket`, ``/login`, ``/serviceValidate`, `INVALID_SERVICE`, single-use ST, and proxy protocol.
8. [Apereo CAS – CAS Protocol Overview](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html): TGT/TGC, ST, service registration, and CAS variants.
9. [Apereo CAS – Ticket Validation](https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html): exact `service` matching and ticket validation policies.
10. [Spring Security – Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local session logout/CSRF, distinct from CAS SSO logout.
11. [Spring Security – Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): `SecurityContextRepository` and HttpSession persistence.
12. [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies/session/sensitive URL data.
13. [OWASP – Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): redirect and URL input handling.
