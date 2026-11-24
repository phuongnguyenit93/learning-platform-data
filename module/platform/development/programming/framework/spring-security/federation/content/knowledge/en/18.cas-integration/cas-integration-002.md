# CasAuthenticationEntryPoint and Redirecting to the CAS Server

## 1. Purpose and Context

In **Spring Security – Federation** systems, **Central Authentication Service (CAS)** allows multiple applications to use a centralized login server. When a browser does not yet have a session at the Spring application, the application must direct the browser to **CAS server `/login`**, along with a **service URL** so CAS knows where to send the user back after login.

The Spring Security class that performs this initial step is **CasAuthenticationEntryPoint**:

- Invoked by **ExceptionTranslationFilter** when a request requires authentication without a valid `Authentication`.
- Builds the redirect URL to **CAS `loginUrl`**, attaching the **service** parameter from **ServiceProperties**.
- Responds with an HTTP redirect, typically **302 + `Location`**.
- **Does not validate the service ticket**, does not create a user session by itself, and is not the CAS server.
- Works together with **CasAuthenticationFilter** to receive the ticket at the callback and **CasAuthenticationProvider** using a CAS **TicketValidator** to verify the ticket with the server.

**Important:** The CAS protocol with **service ticket (ST)** and **ticket-granting ticket (TGT)** is a distinct protocol. Even though an Apereo CAS server can offer SAML2/OIDC, **CasAuthenticationEntryPoint is not Saml2WebSsoAuthenticationFilter or `saml2Login()` configuration**. This article covers the **CAS native protocol**, not SAML 2.0 `SAMLResponse`/Assertion.

This guide uses **Spring Boot 3.3.5, Spring Security 6.x, and Java 17** for illustration. The CAS server and `example.org` URLs are placeholders; to test end-to-end login you must have a **real CAS server** with the service registered, HTTPS/certificates, and appropriate accounts.

### Learning Outcomes

1. Describe the roles of the browser, CAS server, Spring SP/service, and **CasAuthenticationEntryPoint**.
2. Distinguish **loginUrl**, **ServiceProperties.service**, **filterProcessesUrl**, **serverPrefix**, and the URL the user originally requested.
3. Understand the relationship **ExceptionTranslationFilter -> AuthenticationEntryPoint -> redirect -> CAS login -> ticket callback -> ticket validation -> SecurityContext**.
4. Configure a Java `SecurityFilterChain` for **Spring Security 6.x**, without mechanically copying legacy XML namespaces.
5. Predict redirect URLs, inspect **service** URL encoding, handle **sendRenew**, cookies, HTTPS, reverse proxies, and service mismatch errors.
6. Diagnose redirect loops, invalid tickets, callbacks bypassing the filter, and misconfigured access permissions.
7. Test properly without treating a successful CAS login screen display as proof that Spring has authenticated the user.

## 2. CAS Native Protocol: Service, TGT, and ST

Four easily confused concepts:

| Entity | Role |
| --- | --- |
| **CAS server** | Authenticates users centrally, maintains the SSO session, and issues tickets for registered services. |
| **CAS service / client app** | Spring Security application requiring CAS login that must validate the ticket before establishing a local `Authentication`. |
| **Ticket-Granting Ticket (TGT) and TGC cookie** | Used by CAS to recognize that the browser already has an SSO session at CAS. They are **not the Spring HttpSession**. |
| **Service Ticket (ST)** | Short-lived ticket bound to a **service URL**, carried back to the service by the browser; per the CAS protocol, **a ticket is valid for a single validation only**. |

Typical flow:

~~~text
1. Browser: GET https://app.example.org/private
                  |
                  v
2. Spring Security: no Authentication yet
   ExceptionTranslationFilter -> CasAuthenticationEntryPoint
                  |
                  v
3. HTTP 302 Location:
   https://cas.example.org/cas/login?service=<URL-ENCODED-CALLBACK>
                  |
                  v
4. Browser -> CAS server:
   - no valid TGC yet: CAS prompts for login/MFA per policy
   - valid TGC present: CAS can issue an ST without re-prompting for password
                  |
                  v
5. CAS -> Browser -> SP callback:
   https://app.example.org/login/cas?ticket=ST-...
                  |
                  v
6. CasAuthenticationFilter extracts ticket
   -> CasAuthenticationProvider
   -> TicketValidator calls CAS /serviceValidate over HTTPS
                  |
                  v
7. CAS confirms valid ticket, matching service, unused
   -> Spring creates Authentication, local SecurityContext/session
   -> redirects to requested resource or success target
~~~

**Step 3 only initiates authentication.** The application must never treat a user as logged in merely because the browser visited the CAS login URL, because the ticket has not yet been verified. In the flow above, the browser performs a **front-channel redirect** while the application makes a **back-channel** request to CAS to validate the ticket.

### URL Example

Suppose:

~~~text
CAS loginUrl:
  https://cas.example.org/cas/login

CAS server prefix:
  https://cas.example.org/cas

Service callback / ServiceProperties.service:
  https://app.example.org/login/cas

Resource the browser originally requested:
  https://app.example.org/private
~~~

When an unauthenticated request is intercepted, the entry point can send:

~~~http
HTTP/1.1 302 Found
Location: https://cas.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas
~~~

After login, CAS can return the browser to:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/login/cas?ticket=ST-EXAMPLE-ONE-TIME
~~~

**`ST-EXAMPLE-ONE-TIME` is only an illustrative placeholder**, not a real service ticket. A real ticket is trusted only after the Spring server verifies it with the CAS server via **TicketValidator**, including matching the service URL.

A request to **/private** and a service callback **/login/cas** are **two distinct URLs**. **ServiceProperties.service** normally points to the **callback** handled by the CAS filter, not to whatever private page the user happened to request.

## 3. What Does `CasAuthenticationEntryPoint` Actually Do?

The class **org.springframework.security.cas.web.CasAuthenticationEntryPoint** implements **AuthenticationEntryPoint** and **InitializingBean**. Core setup:

~~~java
CasAuthenticationEntryPoint entryPoint = new CasAuthenticationEntryPoint();
entryPoint.setLoginUrl("https://cas.example.org/cas/login");
entryPoint.setServiceProperties(serviceProperties);
entryPoint.setEncodeServiceUrlWithSessionId(false);
~~~

**This snippet only illustrates instantiation**; it requires a `serviceProperties` variable and `SecurityFilterChain` configuration. See the full example in a later section.

| Property/API | Purpose |
| --- | --- |
| **setLoginUrl(String)** | **CAS server `/login`** URL to which the browser is redirected. |
| **setServiceProperties(ServiceProperties)** | Supplies the application's service metadata, especially the **service callback URL** and renew policy. |
| **commence(request, response, exception)** | Called by `ExceptionTranslationFilter` to start login; generates the CAS redirect response. |
| **createServiceUrl(...)** | Builds the request-related service URL, defaulting to CAS client utilities and `ServiceProperties`. |
| **createRedirectUrl(serviceUrl)** | Builds the login redirect URL with the `service` parameter per CAS client rules. |
| **preCommence(...)** | Extension hook for preprocessing before redirect; do not arbitrarily alter trust or destinations here. |
| **setRedirectStrategy(...)** | Selects a redirect strategy when custom behavior is needed; does not replace ticket validation. |
| **setEncodeServiceUrlWithSessionId(false)** | Avoids embedding the servlet session ID in the service URL unnecessarily; keeps the session ID safely in cookies. |

**Do not confuse `commence` with `authenticate`:** it does not read a CAS password form, does not call `/serviceValidate`, does not parse tickets, and does not grant any `GrantedAuthority`.

### When Does `ExceptionTranslationFilter` Invoke It?

For a request marked **`authenticated()`** in `SecurityFilterChain`:

1. The request passes through the filters; no valid `Authentication` is present.
2. **AuthorizationFilter** sees that the resource requires authentication and denies access.
3. **ExceptionTranslationFilter** catches the corresponding `AccessDeniedException`/`AuthenticationException`; for an anonymous/unauthenticated user, it invokes the entry point.
4. The request may be saved by **RequestCache** to return to after login.
5. `CasAuthenticationEntryPoint` sends the redirect to CAS.

**A user who is already authenticated but lacks permissions** should receive **403 Forbidden** from the authorization policy, rather than falling into an infinite CAS redirect loop. If every 403 turns into a redirect, inspect access-denied handling and filter ordering.

### Separating Three Crucial URLs

- **loginUrl:** CAS server endpoint receiving the browser, e.g. **https://cas.example.org/cas/login**.
- **service URL:** Public URL of the Spring application **that receives the ST**, e.g. **https://app.example.org/login/cas**.
- **filterProcessesUrl:** Path on Spring where `CasAuthenticationFilter` listens, defaulting to **/login/cas**. It is a **path**, not a CAS server URL.

**Cas20ServiceTicketValidator**, in contrast, takes the **CAS server prefix**, typically **https://cas.example.org/cas**, to construct the **/serviceValidate** endpoint. Never pass a `loginUrl` ending in `/login` as `serverPrefix`, which would produce an invalid **/login/serviceValidate** path.

## 4. `ServiceProperties` and Service Matching Conditions

**org.springframework.security.cas.ServiceProperties** holds the meaningful configuration for the CAS service.

~~~java
ServiceProperties properties = new ServiceProperties();
properties.setService("https://app.example.org/login/cas");
properties.setSendRenew(false);
~~~

The **service** value must match the service for which the CAS server issued the ticket, and the callback URL must fall under the scope handled by **CasAuthenticationFilter**. The CAS protocol mandates that a ticket is valid only for the **service identifier specified when it was issued**.

### URL Consistency Rules

| Where `service` Appears | Logically Correct Value |
| --- | --- |
| Redirect from SP to **CAS `/login?service=...`** | Public HTTPS callback URL, URL-encoded. |
| CAS redirect of browser back to callback | That exact callback URL, plus the **`ticket`** query parameter. |
| CAS filter watching the app | **/login/cas** under the appropriate application context path. |
| Ticket validation at CAS | **The service URL matching the ticket** (not mixed up with the original resource URL). |
| CAS server service registry | Approves the exact service URL/hostname/path per policy. |

For example, **`service=https://app.example.org/login/cas`** and a CAS callback to **`http://localhost:8080/login/cas`** are not automatically equal. Differences in **http/https** scheme, host, port, path, context path, or encoding can cause **INVALID_SERVICE** or ticket validation failure.

**Never take the service URL directly from an untrusted query parameter or `Host` header.** The CAS server should maintain a strict **registered services allowlist** with HTTPS and no open wildcards. The SP should keep a static operator-configured public service URL, or construct it only from forwarded headers supplied by a trusted reverse proxy.

### `sendRenew`: `true` vs. `false`

- **`sendRenew(false)`:** CAS may use an existing SSO session (TGC/TGT) and issue an ST without re-prompting for a password.
- **`sendRenew(true)`:** adds the **`renew`** requirement to CAS login and ticket validation, demanding a ticket issued from direct user authentication per the CAS protocol.
- **`renew` is not MFA by default**; MFA/step-up rules depend on the CAS server and organizational policy.
- **`renew` does not mean** disabling TGC, clearing the SP session, or enabling proxy tickets.
- **`gateway=true`** is a non-interactive SSO probing mode, distinct from `renew`; combining `gateway` and `renew` has no guaranteed semantics in the CAS protocol. A standard `CasAuthenticationEntryPoint` is not a gateway redirect filter.

Enable `renew` only when business requirements demand reauthentication and the CAS server is configured accordingly; verify ticket validator behavior with `renew=true`.

## 5. Filter and Provider: Why the Entry Point Alone Is Not Enough

Three classes typically work together:

| Component | Input | Output / Work Performed |
| --- | --- | --- |
| **CasAuthenticationEntryPoint** | Unauthenticated request requiring access. | **HTTP redirect** to CAS `/login` with `service`. |
| **CasAuthenticationFilter** | Browser returns to **`/login/cas?ticket=ST-...`**. | Builds an authentication request token and invokes `AuthenticationManager`. |
| **CasAuthenticationProvider** | CAS ticket authentication token. | Delegates to `TicketValidator` to check the ST with CAS; loads `UserDetails`/authorities and creates `CasAuthenticationToken`. |
| **TicketValidator** (Apereo CAS Java Client) | ST + service URL + CAS server prefix. | Calls CAS `/serviceValidate` or matching profile; parses success or failure. |
| **SecurityContext** and local `HttpSession` | Authentication confirmed by the provider. | Maintains login state in the Spring application for subsequent requests. |

If you configure **only `CasAuthenticationEntryPoint`**, the browser can reach CAS login, return to the callback, and then immediately redirect back to login in a loop because **no filter/provider is processing the ticket**.

### Default `CasAuthenticationFilter`

In Spring Security 6.3, **CasAuthenticationFilter** handles **/login/cas** by default. In Java configuration you can set it explicitly:

~~~java
CasAuthenticationFilter filter = new CasAuthenticationFilter();
filter.setFilterProcessesUrl("/login/cas");
filter.setServiceProperties(serviceProperties);
filter.setAuthenticationManager(authenticationManager);
~~~

This snippet illustrates configuration requiring real variables; see Section 8 for a complete project. The filter must be added to **SecurityFilterChain** at the proper position (for example, before `UsernamePasswordAuthenticationFilter`).

### `CasAuthenticationProvider`

The provider requires:

- **ServiceProperties** with the same `service` as the entry point and filter.
- A **TicketValidator**, such as **org.apereo.cas.client.validation.Cas20ServiceTicketValidator** from Apereo Java CAS Client.
- **UserDetailsService** or **AuthenticationUserDetailsService** to resolve the application-side account and authorities.
- A **key** for the provider, which is an **internal identifier** used to recognize tokens, not a private signing key.
- Account active status, membership, and roles/authorization policies after CAS authentication.

For example, the CAS server might authenticate **alice** while the application only permits **bob**: if `UserDetailsService` lacks `alice` or the user is disabled, the application can still reject access. **CAS login success does not automatically grant all local roles.**

### CAS 2.0 / 3.0 Endpoints

- **/login**: CAS receives the browser and issues a service ticket.
- **/serviceValidate**: CAS server validates the ST, typically returning XML.
- **/p3/serviceValidate**: CAS protocol 3.0 can additionally return attributes per profile.
- **/proxyValidate**: used when proxy tickets and proxy trust must be processed; do not enable by default if unneeded.
- **/logout**: CAS logout endpoint, distinct from logging out of the Spring application session.

**Spring Security CAS integration uses the CAS native protocol; do not use `saml2Login()` to replace `CasAuthenticationFilter`.** A CAS server may support SAML2 separately, but that is a different integration.

## 6. Standalone Java 17: Building a Redirect URL to Understand Encoding

The program **CasRedirectUrlDemo.java** uses JDK 17 **without needing a CAS server or Spring**. It demonstrates appending the `service` query parameter when building an example URL. This is a **URL simulation**, not a replacement for `CasAuthenticationEntryPoint` or ticket validation; in production, let the Spring CAS Client build the redirect.

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class CasRedirectUrlDemo {
    private static String create(String loginUrl, String service, boolean renew) {
        if (loginUrl.contains("?")) {
            throw new IllegalArgumentException("Demo requires plain login URL");
        }
        String encodedService = URLEncoder.encode(
                service, StandardCharsets.UTF_8);
        return loginUrl + "?service=" + encodedService
                + (renew ? "&renew=true" : "");
    }

    public static void main(String[] args) {
        String loginUrl = "https://cas.example.org/cas/login";
        String service = "https://app.example.org/login/cas";

        System.out.println("default=" + create(loginUrl, service, false));
        System.out.println("renew=" + create(loginUrl, service, true));
        System.out.println("callback=" + service);
    }
}
~~~

Run:

~~~bash
javac CasRedirectUrlDemo.java
java CasRedirectUrlDemo
~~~

**Exact stdout:**

~~~text
default=https://cas.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas
renew=https://cas.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&renew=true
callback=https://app.example.org/login/cas
~~~

Explanation:

- **`service`** is encoded as **`https%3A%2F%2Fapp.example.org%2Flogin%2Fcas`** when placed in a query parameter value.
- After CAS parses the query, the logical service remains **`https://app.example.org/login/cas`**.
- **`renew=true`** is only a parameter sent to CAS and does not prove CAS actually forced the user to reauthenticate; you must test the CAS server and `TicketValidator`.
- This example does not handle login URLs that already have query strings, fragments, proxy headers, or invalid configuration URLs. Use Spring/CAS components in production.
- Never build redirect URLs directly with a **browser-supplied `service`**, as that can lead to open redirects or issuing tickets to unapproved services.

## 7. Environment Configuration: Which URLs Exist?

Project targets:

~~~text
Spring SP public URL:
  https://app.example.org

Spring CAS callback:
  https://app.example.org/login/cas

CAS base/serverPrefix:
  https://cas.example.org/cas

CAS loginUrl:
  https://cas.example.org/cas/login

CAS validation endpoint:
  https://cas.example.org/cas/serviceValidate
~~~

**The service callback and base URL must be registered by a CAS admin.** Even if the app runs internally at **`http://sp-a:8080`** behind an HTTPS reverse proxy, CAS must still redirect to **`https://app.example.org/login/cas`**, not the internal host. The CAS setup needs proper DNS and TLS trust; the browser must reach `loginUrl`, while the Spring backend must connect to `serverPrefix` over HTTPS.

Verify:

1. DNS/TLS for **`cas.example.org`** works both from the browser and from the Spring backend (backend calls `/serviceValidate`).
2. **`app.example.org`** has public HTTPS and the proxy routes **`/login/cas`** with the right path to Spring.
3. The CAS registered service allowlist contains the exact callback URL with matching scheme/host/path.
4. **ServiceProperties.service** matches the published callback.
5. **CasAuthenticationFilter** handles **`/login/cas`** properly without being blocked by another filter/security chain.
6. The CAS client can load local user/roles after successful ticket validation.
7. SP cookies have appropriate **Secure/HttpOnly/SameSite** flags, and request cache/session work properly.
8. Never use the query **`ticket`** as an `Authentication` without back-channel validation.

## 8. Complete Spring Boot 3.3.5 / Spring Security 6.x Example

This is a Spring MVC application illustrating the CAS native flow. **User `alice`** is defined locally solely to test the flow and grant `ROLE_USER`; **the CAS server must also have account `alice`** to complete the full flow. Because the configured CAS URLs use `example.org`, without a real server you can only observe the redirect and cannot complete ticket validation.

### 8.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-cas-entry-point-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-security-cas** is Spring Security's CAS native integration module; do not use **spring-security-saml2-service-provider** to implement `CasAuthenticationEntryPoint`. CAS Java Client dependencies (especially **cas-client-core**) are normally pulled in transitively via the CAS module; when upgrading versions, run **`mvn dependency:tree`** and ensure compatibility with Spring Security, Spring Boot, and Jakarta Servlet across the entire dependency graph. Never force a newer client version manually if it conflicts with the Spring libraries in use.

### 8.2. `application.yml`

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

app:
  cas:
    login-url: "https://cas.example.org/cas/login"
    server-prefix: "https://cas.example.org/cas"
    service-url: "https://app.example.org/login/cas"
    send-renew: false
~~~

Never mix up these three URLs:

- **login-url** is used for the browser redirect.
- **server-prefix** is used by `TicketValidator` to build the ST validation URL.
- **service-url** is used in the `service` query parameter on login redirect and as **`service`** during ticket validation.

In real systems, source these values from managed configuration, a secret store, or environment variables rather than assuming fixed hostnames; the public URL **https://app.example.org** must route to the running app. `example.org` has no production CAS server.

### 8.3. Application Main

**src/main/java/com/example/casdemo/CasDemoApplication.java**

~~~java
package com.example.casdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasDemoApplication.class, args);
    }
}
~~~

### 8.4. `SecurityConfig`: Entry Point, Filter, Provider, and Chain

**src/main/java/com/example/casdemo/SecurityConfig.java**

~~~java
package com.example.casdemo;

import java.util.List;
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
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
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String serviceUrl,
            @Value("${app.cas.send-renew:false}") boolean sendRenew) {
        ServiceProperties properties = new ServiceProperties();
        properties.setService(serviceUrl);
        properties.setSendRenew(sendRenew);
        return properties;
    }

    @Bean
    CasAuthenticationEntryPoint casAuthenticationEntryPoint(
            ServiceProperties serviceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {
        CasAuthenticationEntryPoint entryPoint =
                new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(loginUrl);
        entryPoint.setServiceProperties(serviceProperties);
        entryPoint.setEncodeServiceUrlWithSessionId(false);
        return entryPoint;
    }

    @Bean
    UserDetailsService localUsers() {
        // Testing only: CAS determines authentication.
        // The Spring app enforces its own account/authorities policy.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}not-used-by-cas")
                .authorities("ROLE_USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties serviceProperties,
            UserDetailsService localUsers,
            @Value("${app.cas.server-prefix}") String casPrefix) {
        CasAuthenticationProvider provider = new CasAuthenticationProvider();
        provider.setServiceProperties(serviceProperties);
        provider.setTicketValidator(
                new Cas20ServiceTicketValidator(casPrefix));
        provider.setUserDetailsService(localUsers);
        provider.setKey("demo-cas-provider-id");
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    CasAuthenticationFilter casAuthenticationFilter(
            CasAuthenticationProvider provider,
            ServiceProperties serviceProperties,
            SecurityContextRepository securityContextRepository) {
        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setFilterProcessesUrl("/login/cas");
        filter.setServiceProperties(serviceProperties);
        filter.setAuthenticationManager(
                new ProviderManager(List.of(provider)));
        // Custom CAS filters must explicitly persist authentication in Spring Security 6.
        filter.setSecurityContextRepository(securityContextRepository);
        // Rotate an existing session ID after successful CAS authentication.
        filter.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());
        return filter;
    }

    @Bean
    FilterRegistrationBean<CasAuthenticationFilter> disableServletRegistration(
            CasAuthenticationFilter filter) {
        // Because the filter is a bean, Boot would auto-register it as a Servlet filter.
        // Disable standalone registration; use it only inside SecurityFilterChain.
        FilterRegistrationBean<CasAuthenticationFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CasAuthenticationEntryPoint entryPoint,
            CasAuthenticationFilter casFilter,
            SecurityContextRepository securityContextRepository) throws Exception {
        http
            .securityContext(context -> context
                .securityContextRepository(securityContextRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .addFilterBefore(
                casFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Why each of these beans is needed:**

1. **ServiceProperties:** shares the HTTPS callback service, `sendRenew` policy, and ticket validation binding.
2. **CasAuthenticationEntryPoint:** invoked by `ExceptionTranslationFilter` when CAS login is needed; builds `Location` to CAS `loginUrl`.
3. **CasAuthenticationFilter:** handles the ticket on path **`/login/cas`** and calls `AuthenticationManager`.
4. **ProviderManager(CasAuthenticationProvider):** dispatches the authentication request token from the filter to the right CAS provider so the ST can be validated.
5. **Cas20ServiceTicketValidator:** verifies the CAS service ticket against CAS `serverPrefix` over HTTPS with valid TLS trust.
6. **UserDetailsService:** supplies local authorities; does not imply the CAS server owns those exact accounts. The example resolves only `alice`; production uses a real database/identity mapping.
7. **Disabled FilterRegistrationBean:** because `CasAuthenticationFilter` is already placed in the Spring Security chain, Boot must be prevented from auto-registering it as a standalone servlet filter **a second time**.
8. **SecurityFilterChain.exceptionHandling:** wires the entry point into `ExceptionTranslationFilter`. If omitted, you may see Spring's default login page or unexpected HTTP 401/403 responses.
9. **addFilterBefore:** ensures the CAS filter participates in the right chain and intercepts the **`/login/cas`** callback. Merely declaring a filter bean does not make Spring Security use it automatically.
10. **Do not call `formLogin()` or `saml2Login()`** in this example; multiple mechanisms can be combined, but each needs scoped request matchers/entry points rather than mixing globally.

11. **SecurityContextRepository:** Spring Security 6 requires a custom `AbstractAuthenticationProcessingFilter` to configure a repository explicitly if authentication must persist across requests. The `DelegatingSecurityContextRepository` bean coordinates `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`. `CasAuthenticationFilter` and `SecurityFilterChain` share the same bean so the CAS callback saves `Authentication` in the HTTP session and the subsequent `/private` request can read it.
12. **Session fixation:** `ChangeSessionIdAuthenticationStrategy` is attached to the custom CAS filter. If a session already exists before successful authentication, the servlet container rotates the session ID while preserving session attributes, preventing session fixation.

**Production note:** The in-memory `UserDetailsService` and `ROLE_USER` only demonstrate `alice`; they do not replace local account provisioning/authorization, and `{noop}` passwords must not be used in apps with form login. The **`provider.setKey`** value is a provider identifier string, not an encryption key; set a unique, stable identifier by design.

### 8.5. Controller

**src/main/java/com/example/casdemo/ExampleController.java**

~~~java
package com.example.casdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ExampleController {

    @GetMapping("/")
    public String home() {
        return "CAS entry point demo ready";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "CAS authenticated: " + authentication.getName();
    }
}
~~~

When unauthenticated, **`GET /private`** is intercepted by the security filter before reaching the controller. Once CAS issues a valid ticket and the provider resolves user `alice`, the endpoint can return **`CAS authenticated: alice`**. If CAS returns a user absent from the local user service, completing authentication can fail; the example intentionally does not grant `ROLE_USER` automatically to every username from CAS.

### 8.6. Regression Test: CAS Callback Must Keep Login State on the Next Request

Add `spring-boot-starter-test` (test scope) in `pom.xml`. This test **mocks the CAS provider** to isolate session persistence; it does not replace integration tests that validate Service Tickets against a real CAS server.

**src/test/java/com/example/casdemo/CasSessionPersistenceTest.java**

~~~java
package com.example.casdemo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.authentication.CasServiceTicketAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CasSessionPersistenceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    CasAuthenticationProvider casProvider;

    @BeforeEach
    void stubCasProviderWithoutNetwork() {
        when(casProvider.supports(CasServiceTicketAuthenticationToken.class))
                .thenReturn(true);
        when(casProvider.authenticate(any(Authentication.class)))
                .thenReturn(new UsernamePasswordAuthenticationToken(
                        "alice", null, AuthorityUtils.createAuthorityList("ROLE_USER")));
    }

    @Test
    void authenticationSurvivesTheRequestAfterCasCallback() throws Exception {
        MvcResult callback = mvc.perform(
                get("/login/cas").param("ticket", "ST-LOCAL-TEST"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) callback.getRequest().getSession(false);
        assertNotNull(session, "CAS callback must establish a local session");

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("CAS authenticated: alice"));
    }
}
~~~

Run `mvn -Dtest=CasSessionPersistenceTest test`. Without configuring the repository, the callback can succeed yet the subsequent `/private` request loses login state and redirects back to CAS. With the shared repository, the test confirms `Authentication` remains in the session on the next request. Also test session ID rotation when a prior session exists, timeout/logout, and real ticket validation in an integration environment.

### 8.7. Startup

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

**What you can verify immediately without a real CAS server:**

- **`GET http://localhost:8080/`** returns literally **`CAS entry point demo ready`**.
- **`GET http://localhost:8080/private`** when anonymous redirects to **`https://cas.example.org/cas/login?service=...`**, per the configured `service-url`.
- The `example.org` CAS address is not a real server; the browser cannot complete login there.
- Because the callback is set to **`https://app.example.org/login/cas`**, a real setup needs HTTPS ingress pointing to the running app and the CAS server registering that exact URL. A local process on plain HTTP **`localhost:8080`** is insufficient for end-to-end testing.

**With a valid CAS sandbox:**

1. Open **`https://app.example.org/private`**.
2. Observe HTTP 302 from the SP to **`/cas/login?service=...`**.
3. Log in to CAS with test account **`alice`**.
4. CAS redirects the browser back to **`https://app.example.org/login/cas?ticket=ST-...`**.
5. Spring `CasAuthenticationFilter` receives the ST, and the provider calls **`/cas/serviceValidate`** over HTTPS with the same `service`.
6. The CAS server returns validation success; Spring reads `alice`, `localUsers` has `alice`, and `Authentication` is created.
7. The browser returns to **`/private`** (via request cache/default success handler when configured appropriately) and receives **`CAS authenticated: alice`**.
8. Subsequent requests use the local session `SecurityContext` until the session expires or logs out.

**Do not treat the Step 2 302 response as a QA PASS for authentication.** Only Steps 6–7 prove CAS server ticket validation and local account mapping.

## 9. Checking Redirects with Browser and HTTP Tools

### Minimal Network Trace

Using browser DevTools -> Network:

~~~text
GET /private
  302 Location=https://cas.example.org/cas/login?service=...

GET CAS /cas/login?service=...
  CAS displays login or issues ticket via SSO cookie

GET /login/cas?ticket=ST-...
  Spring CAS filter handles callback

GET /private
  200 when CAS validation session + local authorization are valid
~~~

If checking with **`curl -I`**:

~~~bash
curl -I https://app.example.org/private
~~~

you may observe a **`302`** to CAS login. However, a **`HEAD`** request does not necessarily behave identically to `GET` across all apps/filter chains; use **`curl -i -s -D - -o /dev/null`** or a browser `GET` to observe real behavior. Do not run **`curl -L`** and claim login succeeds solely from a redirect chain when no CAS session exists.

Never paste real STs into terminal history or public tickets: an ST is a short-lived credential. Browser DevTools/network logs can expose tickets; strip or redact them before sharing.

### What to Check in `Location`

- Scheme and host of `loginUrl` match the approved CAS server.
- URL-decoded **`service`** equals **`https://app.example.org/login/cas`**.
- No internal host **`http://sp-a:8080`** or another tenant's service appears.
- No session identifier appears in the URL.
- If `sendRenew=true`, **`renew`** is present per protocol and matches the validator's policy.
- CAS registered service is exact, without overly permissive wildcards.
- After callback, the request enters `CasAuthenticationFilter` rather than redirecting to CAS again without validating the ticket.

## 10. Reverse Proxy, Context Path, and Cookies

### Reverse Proxy and External URL

~~~text
Browser HTTPS https://app.example.org/private
         |
         v
Load balancer / ingress (TLS termination)
         |
         v
Spring backend HTTP http://sp-a:8080/private
~~~

**`ServiceProperties.service` must be the public HTTPS callback**, not `http://sp-a:8080/login/cas`. If the app has context path **`/portal`**, the callback can be **`https://app.example.org/portal/login/cas`** while `filterProcessesUrl` matches servlet path **`/login/cas`**. Always verify the actual Servlet context configuration and reverse proxy path rewriting.

If the SP constructs URLs dynamically from requests, trust forwarded headers only when **written/overwritten by a valid proxy**. Never trust raw **`X-Forwarded-Host`** headers supplied directly from the Internet. Even with a static service URL, forwarded headers affect redirects/saved requests if the web layer generates external links.

### CAS Cookies and SP Cookies Are Different

| Cookie / Session | Where It Lives | Meaning |
| --- | --- | --- |
| **CAS TGC/TGT session** | CAS domain, e.g. `cas.example.org`. | Proves the browser has a CAS SSO session so CAS can consider issuing an ST. |
| **SP `HttpSession`/`JSESSIONID`/`SESSION`** | Application domain, e.g. `app.example.org`. | Spring service's `SecurityContext` after the ticket is validated. |
| **LB affinity cookie** | Reverse proxy/load balancer. | Keeps the browser routed to one backend; does not establish `Authentication`. |

With two SP nodes, if sessions live only in local memory and subsequent callbacks/requests land on the other node, `SecurityContext` can be lost and trigger CAS login loops. Use proper sticky sessions or **Spring Session Redis/JDBC**, and test cookie/domain/TTL and failover. **A valid CAS TGC does not mean the SP automatically has a local `Authentication`**; the SP still has to process an ST for each service/session as needed.

### Cookie Security

- SP cookies should use **`Secure`, `HttpOnly`**, and a `SameSite` attribute suited to the flow and hosts.
- CAS callbacks arrive by default via a **`GET`** front-channel redirect carrying the ticket. `SameSite=Lax` generally works with top-level cross-site GETs, but test against real browsers/policies; do not blindly copy `SameSite` settings from SAML POST bindings.
- Do not embed session IDs into the **service URL** or query parameters without specific security requirements and analysis.
- Upon successful authentication, Spring should enforce session fixation protection / cookie rotation per security config.
- TLS across browser<->CAS, browser<->SP, and SP backend<->CAS validator must be protected per trust policy.

### Logout Is Not SLO by Default

Spring's **`POST /logout`** normally invalidates only the SP local session. The user can immediately be issued a new ST by CAS because the CAS TGC still exists. Centralized CAS logout requires designing **CAS Single Logout (SLO)**, the CAS logout endpoint, and proper filter/notification handling. Never promise that calling SP logout automatically ends all CAS or sibling app sessions.

## 11. Common Redirect Errors

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| **`/private` returns 401 or a form login page** | `ExceptionTranslationFilter` does not use `CasAuthenticationEntryPoint`, or another chain matches first. | Check `SecurityFilterChain` matchers and `exceptionHandling().authenticationEntryPoint(...)`. |
| **Browser reaches CAS but CAS reports unrecognized service** | Service URL is unregistered or differs in scheme/host/path. | Compare the URL-decoded service value against the CAS registered service. |
| **CAS login succeeds, returns to `/login/cas`, then redirects to CAS again** | `CasAuthenticationFilter` is missing from the security chain, callback does not match, or ticket validation fails. | Check `filterProcessesUrl`, filter order, provider, and reason-code logs. |
| **`INVALID_SERVICE` during ST validation** | `service` at `/login` and `/serviceValidate` do not match exactly. | Share one `ServiceProperties`, keep a stable public callback, and never append `ticket` to `service`. |
| **`INVALID_TICKET`** | ST expired, already consumed, wrong service, or proxy ticket passed to ST validator. | Re-login to get a fresh ST, do not replay, and use the right CAS validation endpoint. |
| **TLS handshake fails when validating ticket** | Spring backend does not trust the CAS HTTPS certificate, wrong hostname, or proxy/TLS issue. | Fix truststore/CA/hostname; never disable certificate verification. |
| **CAS repeatedly prompts for password** | `sendRenew=true` or TGC is not retained. | Check renew policy, CAS SSO cookie/browser settings, and user settings. |
| **CAS login succeeds but Spring returns user not found** | Local `UserDetailsService` does not contain the CAS username. | Configure approved account mapping/provisioning; never grant broad default roles. |
| **`/private` returns 403 after CAS login** | Authenticated user lacks the required authority. | Check local roles/authorization; do not redirect to login to bypass role checks. |
| **Callback 404** | Wrong context path or reverse proxy does not route `/login/cas`. | Check external URL, ingress rules, and `filterProcessesUrl`. |
| **`Location` redirects to `http://internal:8080`** | Misconfigured service URL/proxy host or missing trusted forwarded headers. | Set public HTTPS `service` and configure proxy headers properly. |
| **Ticket appears in logs and analytics** | Query string logged verbatim. | Redact `ticket` from access logs/tracing/referrer and redirects. |
| **Spring CAS filter runs twice** | Filter registered as a servlet filter bean automatically and also added to `SecurityFilterChain`. | Use a disabled `FilterRegistrationBean` as shown in the example. |
| **Does not redirect back to original page after login** | `RequestCache` or success handler changed, or session lost. | Check saved requests, local `HttpSession`, `SameSite`/affinity, and success handler. |
| **Valid CAS login ST enters the wrong tenant** | Checked only the CAS username and mapped everyone into one organization. | Enforce account mapping + tenant membership after CAS validation; never trust URLs/headers. |
| **ST validated again and fails** | CAS ST is a one-time token. | Do not retry the same ST; initiate a new login flow. |

Distinguish **redirect failures** (never reached CAS), **CAS login failures**, **ticket-validation failures**, **local user/role failures**, and **session failures**. Each failure category has a different fix.

## 12. Key Security Decisions

### CAS Server Must Whitelist Service URLs

The CAS protocol recommends that the server redirect/issue tickets only for **registered authorized services**. If CAS allows arbitrary services, attackers can exploit it for open redirects or phishing/ticket misuse. The SP should send a stable service URL; the CAS server registry validates host/scheme/path and service policy.

### Never Treat the Query ST as Sole Proof

- The ST must be verified **server-to-server** over HTTPS against a trusted CAS server.
- Validation results must bind to the **service** to which the ticket was issued.
- The ST must be short-lived and single-use; avoid storing raw STs after login.
- Never log real tickets into app logs, analytics, error traces, or shared URLs.
- Never write a custom **`/login/cas`** endpoint that accepts anyone presenting a **`ticket`** query parameter while bypassing `CasAuthenticationProvider`.

### CAS Identity and Local Authority

The CAS server authenticates identity per protocol, while the SP decides whether the account may access the app. Identical usernames on two CAS servers do not automatically represent the same account. In multi-organization systems, identity binding should include **trusted CAS server/service domain**, a stable subject, tenant membership, and per-organization roles. Never treat an **`X-User`** request header as a username in place of `TicketValidator`.

### Renew Does Not Defend Against Every Attack

`renew` can demand fresh direct authentication; it does not replace TLS, one-time tickets, CSRF, session management, or authorization. Enabling `renew` can cause frequent re-login prompts; align the policy with functional risk.

### Never Use `http` / `localhost` in Production

CAS server login, CAS service callback, and ticket validation should use **public HTTPS with trusted hostnames**. Local HTTP is only for controlled sandbox demos; never open the service registry to accept arbitrary HTTP hosts in production just to "make ticket validation pass".

### Do Not Confuse OAuth2, SAML2, and CAS

| Protocol | Typical Redirect / Callback | Returned Token / Artifact |
| --- | --- | --- |
| **CAS native** | `/cas/login?service=...`, `/login/cas` | **Service Ticket**, verified at CAS `/serviceValidate`. |
| **SAML2 Web Browser SSO** | IdP SSO endpoint, SP ACS | **SAMLResponse/Assertion**, verified via XML signatures/profiles. |
| **OAuth2/OIDC authorization code** | Authorization endpoint, `redirect_uri` | **authorization code**, exchanged at token endpoint; OIDC adds ID Token. |

An Apereo CAS server supports multiple protocols, but **CasAuthenticationEntryPoint** belongs to CAS native integration. For this guide you must use **spring-security-cas**; never describe `saml2Login()` as the same filter.

## 13. Positive and Negative Testing

Use a **CAS sandbox** issuing valid tickets, a fixed service registry, and a test user, paired with server-less unit tests for entry point URLs. **Never publish real STs in reports.**

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Anonymous `GET /private` | 302 to CAS `loginUrl` with properly encoded `service`. |
| 2 | Authenticated `GET /private` | No CAS redirect; proceeds to authorization. |
| 3 | Anonymous `GET /` | 200 public, no CAS call. |
| 4 | CAS already has TGC, `sendRenew=false` | CAS can issue an ST without prompting for password per policy. |
| 5 | `sendRenew=true`, CAS user has SSO session | CAS requires direct reauthentication per renew policy. |
| 6 | CAS `loginUrl` mistakenly uses server prefix without `/login` | Browser hits wrong endpoint; inspect `Location`. |
| 7 | `service` URL host/path differs from registered service | CAS rejects the service or ticket validation fails. |
| 8 | App behind HTTPS reverse proxy but `service` is `http://internal` | Must not be accepted; fix external URL. |
| 9 | Valid callback `/login/cas?ticket=ST` | Filter/provider validate ticket and create `Authentication`. |
| 10 | Callback does not match `filterProcessesUrl` | No `Authentication`; 404/redirect/401 depending on chain. |
| 11 | Entry point present but `CasAuthenticationFilter` missing | Login loop, ST never processed. |
| 12 | Filter present but `CasAuthenticationProvider` missing | `AuthenticationManager` cannot process ST; fails. |
| 13 | CAS server `/serviceValidate` unreachable | Login fails gracefully; never bypass validator. |
| 14 | Wrong CAS HTTPS hostname/certificate | TLS validation fails; never disable verification. |
| 15 | ST validated a second time | CAS returns invalid ticket; no replay. |
| 16 | ST issued for service A but validated with service B | CAS rejects service mismatch. |
| 17 | Valid CAS user `alice`, local account `alice` enabled | Can complete login with `ROLE_USER`. |
| 18 | Another CAS user without a local account | Business login mapping fails; never auto-grant admin. |
| 19 | Authenticated user lacks admin authority | 403, no infinite redirect back to CAS. |
| 20 | Access `/private` after login on another node with local sessions | `SecurityContext` may be lost; use sticky/shared store per SLA. |
| 21 | Two apps share the same CAS TGC but have separate SP sessions | Each app needs its own local ST validation/session. |
| 22 | CAS logout ends only the CAS session | SP session does not automatically end unless CAS SLO is implemented. |
| 23 | SP logout while CAS TGC remains | Browser may re-SSO via CAS; test logout policy. |
| 24 | User submits a client-chosen service callback URL | Never allow trusted redirects/services outside the registry. |
| 25 | Spring filter auto-registered by Boot plus `addFilterBefore` | Test detects duplicate processing; disable standalone servlet registration. |
| 26 | Browser sends a forged ticket not issued by CAS | Validator rejects it; no `Authentication` created. |
| 27 | CAS admin disables service registration | CAS `/login` rejects or `/serviceValidate` fails per policy. |
| 28 | Saved request lost while CAS login succeeds | May land on default success target; does not mean ST failed. |
| 29 | Valid CAS credential but invalid tenant/role | SP denies business access; no privilege escalation. |
| 30 | CAS and SP use proxy paths with wrong port/HTTPS | Invalid service/redirect mismatch; fix URL topology. |

**A negative test passes** when the application accurately rejects invalid inputs—not when ticket validation is disabled so logins pass at all costs.

### Quick Browser Verification

1. Open **`/private`** without an SP session.
2. Inspect the **HTTP response status** and **`Location`** of the first redirect.
3. URL-decode **`service`**; compare with `ServiceProperties.service` and the CAS service registry.
4. Complete login on the CAS sandbox and verify the browser returns to **`/login/cas?ticket=...`**.
5. Confirm the backend successfully calls **`/serviceValidate`**.
6. Observe the HTTP redirect after ticket validation to the requested page and perform another authenticated request.
7. Log out of the SP and revisit, distinguishing the CAS TGC from the SP local session.
8. Test reusing an old ST, a mismatched service, renew policy, and network/TLS failures.

## 14. Common Mistakes to Avoid

1. **Thinking `CasAuthenticationEntryPoint` already authenticates the user.** It only redirects.
2. **Setting `loginUrl` to the service URL or vice versa.** One belongs to the CAS server; the other belongs to the SP.
3. **Setting `ServiceProperties.service` to `/private`** instead of the callback watched by the CAS filter.
4. **Using `CasAuthenticationFilter` while forgetting `setAuthenticationManager`/`CasAuthenticationProvider`.**
5. **Forgetting `addFilterBefore` to register the filter in `SecurityFilterChain`.**
6. **Enabling the filter bean twice** due to Boot's servlet auto-registration.
7. **Setting `server-prefix` to `.../cas/login`**, causing the validator to construct a wrong path.
8. **Giving CAS registered services overly broad wildcards**, weakening redirect/ticket controls.
9. **Disabling certificate validation** to silence TLS errors between SP and CAS.
10. **Trusting the query `ticket` without calling CAS validation.**
11. **Reusing an ST multiple times** when the protocol allows only one validation.
12. **Logging full tickets in access logs**, leaking short-lived credentials.
13. **Confusing CAS native with SAML2/OIDC** when configuring filters.
14. **Skipping app authorization because CAS authenticated the user**, without checking roles/tenants.
15. **Assigning `ROLE_ADMIN` to all CAS users** via a permissive default `UserDetailsService`.
16. **Treating SP logout as CAS Single Logout** while the CAS TGC remains active.
17. **Assuming `sendRenew=true` enables MFA for every system** without checking CAS policy.
18. **Constructing service URLs from untrusted `Host`/`X-Forwarded-Host` headers.**
19. **Failing to distinguish the public HTTPS URL from backend HTTP localhost.**
20. **Losing sessions behind a load balancer and blaming ticket validation**, without checking cookies/shared sessions.

## 15. Production Deployment Checklist

**Protocol and routing setup:**

- [ ] Confirmed **CAS native protocol**; server exposes matching `/login` and `/serviceValidate`.
- [ ] **`loginUrl=https://CAS_HOST/cas/login`** and **`serverPrefix=https://CAS_HOST/cas`** are consistent.
- [ ] **`ServiceProperties.service`** is the public HTTPS callback permitted by the CAS server registry.
- [ ] **`filterProcessesUrl`** matches the callback, accounting for context path and proxy rewrites.
- [ ] `ExceptionTranslationFilter` actually selects **`CasAuthenticationEntryPoint`** for CAS-protected resources.
- [ ] `CasAuthenticationFilter` and `CasAuthenticationProvider` work together with `TicketValidator` and `UserDetailsService`.
- [ ] CAS filter is registered once in the security chain, with no duplicate servlet auto-registration.
- [ ] Saved request/post-login redirect verified under real HTTPS and sessions.

**Security:**

- [ ] CAS login + ticket validation use HTTPS with proper truststore and hostname verification.
- [ ] CAS service registry allowlist is tight; client-chosen services are disallowed.
- [ ] ST is validated server-to-server, single-use, and service-bound; no log/referrer leaks.
- [ ] SP session cookies use `Secure`/`HttpOnly`/`SameSite` properly and session fixation protection is active.
- [ ] **`sendRenew`** matches business requirements; `renew` is not mistaken for MFA.
- [ ] Local `UserDetails`/tenant authorization runs after CAS validation; arbitrary CAS users are not granted access automatically.
- [ ] Separate logout/SLO policy exists for CAS TGC vs. SP local sessions.

**Operations and QA:**

- [ ] Test CAS sandbox and test accounts are used; `example.org` domains are never left in production configs.
- [ ] Redirect `Location`, validation responses, and authenticated resources are all verified—not just HTTP 302.
- [ ] Tested invalid tickets, consumed tickets, wrong services, TLS failures, missing roles, and disabled users.
- [ ] Tested reverse proxy, multi-node load balancer/session persistence, and session timeouts.
- [ ] Request traces, HTTP statuses, and reason codes are logged with tickets/PII/secrets redacted.
- [ ] CAS server version, CAS client, and Spring Security 6.x compatibility are tracked before upgrades.

## 16. Review Questions

**Question 1.** Does `CasAuthenticationEntryPoint` create a `CasAuthenticationToken` during the redirect?  
**Answer:** **No.** It only initiates CAS login with an HTTP redirect. The filter and provider process the ST after the callback.

**Question 2.** Why is `service=https://app.example.org/login/cas` not the same as `loginUrl=https://cas.example.org/cas/login`?  
**Answer:** `loginUrl` belongs to the CAS server receiving the browser; `service` is the SP's callback URL receiving the ST, and must match the CAS registry and validator.

**Question 3.** A user logs in to CAS successfully, the browser receives a ticket, yet Spring keeps looping back to CAS login. What should you check?  
**Answer:** Check whether `CasAuthenticationFilter` handles `/login/cas`, whether the provider/validator run properly, whether the service URLs match, and whether `SecurityContext`/session are persisted.

**Question 4.** Does `sendRenew=true` guarantee that CAS performed MFA?  
**Answer:** **No.** `renew` requires direct authentication; MFA depends on CAS server policies that must be verified separately.

**Question 5.** CAS already has a TGC so the browser gets SSO. Why must Spring still validate the ST?  
**Answer:** The CAS TGC manages SSO at CAS; the SP trusts only an ST issued by CAS for that exact service and verified server-to-server before creating a local `Authentication`.

**Question 6.** CAS returns an ST for `app.example.org`, but Spring validates it with `localhost:8080`. What happens?  
**Answer:** Ticket validation normally fails due to service mismatch; use the public HTTPS service URL consistently.

**Question 7.** Why was servlet auto-registration disabled for the `CasAuthenticationFilter` bean in the example?  
**Answer:** Because the filter was already registered via `addFilterBefore` inside `SecurityFilterChain`; external auto-registration would run it twice or in the wrong order.

**Question 8.** Can CAS login use `saml2Login()` instead of `CasAuthenticationEntryPoint`?  
**Answer:** Not for the CAS native ST flow. `saml2Login()` uses SAML2 Response/Assertion; using a CAS server as a SAML2 IdP is a separate SAML2 configuration.

**Question 9.** A CAS user has username `alice`, but the local account `alice` is locked. Can the app allow login simply because CAS succeeded?  
**Answer:** Not under application policy; the provider/user details service must enforce local account status and authorization.

**Question 10.** Does SP logout always terminate the CAS TGC and log out other applications?  
**Answer:** No; centralized logout requires separately configured CAS Single Logout (SLO).

## 17. Official Documentation and Further Reading

1. [Spring Security 6.x – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): full interaction sequence, `ServiceProperties`, `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, and `CasAuthenticationProvider`.
2. [Spring Security 6.3.5 Javadoc – CasAuthenticationProvider](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): provider, `serviceProperties`, `ticketValidator`, `userDetailsService`, and provider key.
3. [Spring Security 6.3.0-RC1 Javadoc – CasAuthenticationFilter](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): default `/login/cas` path, service ticket handling, and `setServiceProperties`.
4. [Spring Security 6.5 Javadoc – CAS web package](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/cas/web/package-summary.html): CAS entry point/filter and gateway classes.
5. [Spring Security 6.5 Javadoc – ServiceProperties](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/ServiceProperties.html): `service`, `sendRenew`, and related parameters.
6. [Apereo CAS – CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `/login?service=...`, one-time tickets, and `/serviceValidate`; development-branch docs should be cross-checked against your deployed CAS server version.
7. [Apereo CAS – CAS Protocol](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html): distinguishing CAS TGT/TGC/ST, CAS 2.0, and CAS 3.0.
8. [Apereo Java CAS Client](https://github.com/apereo/java-cas-client): `TicketValidator` library, CAS protocol filters, and `cas-client-core` dependency.
9. [Spring Security – Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): relationship among `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AuthenticationManager`.
10. [Spring Security – CAS module](https://docs.spring.io/spring-security/reference/modules.html): `spring-security-cas` module and dependencies.

**Summary:** **`CasAuthenticationEntryPoint` solely handles redirecting the browser to the CAS login server**, using **`loginUrl`** and **`ServiceProperties.service`**. **`CasAuthenticationFilter`** receives the **ST** at the **`/login/cas`** callback, and **`CasAuthenticationProvider`/`TicketValidator`** verifies the ST against the exact service with the CAS server before establishing a local `Authentication`. Enforcing **HTTPS, CAS registered services, consistent URLs, sessions, account mapping, and authorization** is essential for a secure CAS login flow.
