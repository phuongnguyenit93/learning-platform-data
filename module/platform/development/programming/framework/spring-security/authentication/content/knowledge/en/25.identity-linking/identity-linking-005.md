# CAS: Service Tickets and Centralized Authentication in Spring Security

## 1. The Problem: Many Applications, One Login Place

Suppose an organization has an HR portal, a documentation system, and an admin application. If each application handles passwords and login sessions on its own, users have to log in repeatedly, and the security team must maintain multiple authentication mechanisms with inconsistent policies. **Central Authentication Service (CAS)** solves this by delegating user authentication to a **CAS Server**, while each application acts as a **CAS Service** that verifies login credentials issued by CAS.

A typical CAS deployment consists of:

- **CAS Server:** centralized authentication service connected to identity sources (LDAP/AD, database, MFA, etc.) that issues tickets.
- **Browser:** navigates between applications and CAS, carrying the CAS SSO session cookie and the service ticket in the callback URL.
- **CAS Service (client/application):** Spring Security application protecting resources, redirecting unauthenticated users to CAS and **verifying tickets directly with the CAS Server**.
- **Application user/permission store:** maps the CAS-verified username or attributes to local accounts and `GrantedAuthority` instances for access control.

**Lesson objectives:** understand `service ticket` (ST), `ticket-granting ticket` (TGT), `TGC` cookie, redirect flow, and back-channel validation; learn how to configure Spring Security Servlet with CAS, separate centralized authentication from authorization, and handle security, logout, and troubleshooting.

CAS here refers to **Apereo CAS / the CAS protocol**, not OAuth 2.0 Authorization Code, not OIDC ID Token, and not Spring Security's "default session mechanism". A CAS Server may support other protocols via separate modules, but this lesson focuses on the **CAS protocol with Service Tickets**.

## 2. Terminology and Responsibilities

| Component / Concept | Role | Where It Lives |
| --- | --- | --- |
| **CAS Server** | Authenticates users and issues/validates tickets per policy | Centralized authentication infrastructure |
| **CAS Service** | Application using CAS (e.g., `https://hr.example.test`) | Spring/Java backend |
| **service identifier** / `service` | Target URL **for which an ST is issued**, e.g., `https://hr.example.test/login/cas` | Value passed in login and validation requests |
| **Ticket-Granting Ticket (TGT)** | Ticket representing the CAS SSO session, used to mint additional STs | Managed by CAS Server |
| **Ticket-Granting Cookie (TGC)** | Browser cookie carrying a reference to the CAS TGT session | Browser, scoped to the CAS domain |
| **Service Ticket (ST)** | Opaque string such as `ST-...` issued for **one service**, used by the service to verify identity | Passed via redirect to the service callback |
| **Local session / JSESSIONID** | Spring application session created after ticket verification | Browser and application |
| **Proxy Ticket (PT)** | Ticket for another backend in a CAS delegation flow, distinct from ST | CAS proxy flow (extension) |
| **Authentication** | Verified identity for the request inside the application | Spring Security's `SecurityContext` |
| **Authorization** | Decision on whether the user has roles/permissions for a resource | Application rules |

TGT and TGC are **not** Service Tickets:

- After a user logs into CAS, CAS creates/maintains an SSO session (TGT) and the browser receives a TGC per policy.
- Each time an application logs in through CAS, CAS issues a **fresh ST** dedicated to that application.
- Applications do **not** receive the CAS TGT and must never use TGC directly as a credential.
- A verified ST is typically exchanged for **local authentication/session**; subsequent requests use the local session rather than reusing the ST.

For example, when a user has accessed App A and then visits App B: the browser sends the TGC to CAS when redirected from App B, and CAS can recognize the SSO session and issue a new **ST-B** without prompting for a password again. **ST-A and ST-B are different**, because they were issued for different services.

## 3. Step-by-Step CAS Login Flow

Assumed example:

~~~text
CAS Server       https://sso.example.test/cas
Spring App       https://hr.example.test
Service callback https://hr.example.test/login/cas
Target resource  https://hr.example.test/profile
~~~

Overall flow:

~~~text
   Browser                     Spring Service                     CAS Server
      |                               |                                |
 (1)  | GET /profile                  |                                |
      |------------------------------>|                                |
 (2)  | 302 → /cas/login?service=...  |                                |
      |<------------------------------|                                |
 (3)  | GET /cas/login?service=...                                     |
      |--------------------------------------------------------------->|
 (4)  |    form login / use valid TGC                                  |
      |<-------------------------------------------------------------->|
 (5)  | 302 → /login/cas?ticket=ST-...                                 |
      |<---------------------------------------------------------------|
 (6)  | GET /login/cas?ticket=ST-...  |                                |
      |------------------------------>|                                |
 (7)  |                               | GET /cas/serviceValidate       |
      |                               |   ?ticket=ST-...&service=...   |
      |                               |------------------------------->|
 (8)  |                               | XML success + username         |
      |                               |<-------------------------------|
 (9)  | 302 → /profile, local session |                                |
      |<------------------------------|                                |
(10)  | GET /profile + local cookie   |                                |
      |------------------------------>|                                |
      | 200 authorized content        |                                |
      |<------------------------------|                                |
~~~

Detailed steps:

1. The browser requests `/profile` without a valid `Authentication` in the Spring session.
2. Spring Security detects that the resource requires authentication; `CasAuthenticationEntryPoint` issues an HTTP redirect to `https://sso.example.test/cas/login` with a `service` query parameter pointing to the **application's callback**.
3. The browser reaches CAS. If no CAS session exists, CAS presents its login form or centralized authentication workflow (potentially with MFA); if a valid TGC exists and SSO policy permits, password entry may be skipped.
4. CAS issues a **fresh ST bound to that exact registered callback** and redirects the browser back to `https://hr.example.test/login/cas?ticket=ST-...`.
5. `CasAuthenticationFilter` in the application receives the callback request, extracts `ticket`, creates a CAS-specific authentication request, and delegates to `AuthenticationManager`.
6. `CasAuthenticationProvider` uses `TicketValidator` to open a **server-to-server HTTPS** connection to CAS `/serviceValidate` with the **same service URL** and ST.
7. CAS checks that the ST is valid, unused, and **matches the service**. On success, CAS returns a response containing the username and optional attributes; CAS consumes the ST.
8. The provider loads authorities for the user; Spring populates `SecurityContext`, persists the local session if configured, and redirects back to the originally requested URL.
9. The browser uses the **application's** cookie for subsequent requests. Keeping the TGC on the CAS domain enables SSO into other applications, but does not replace each application's own cookie.

### Illustrative Redirect URLs

Redirect from application to CAS:

~~~http
HTTP/1.1 302 Found
Location: https://sso.example.test/cas/login?service=https%3A%2F%2Fhr.example.test%2Flogin%2Fcas
~~~

After authentication, CAS redirects back to the callback:

~~~http
HTTP/1.1 302 Found
Location: https://hr.example.test/login/cas?ticket=ST-example-9a82
~~~

Application validates the ST over server-to-server HTTPS (URL shortened for readability):

~~~http
GET /cas/serviceValidate?service=https%3A%2F%2Fhr.example.test%2Flogin%2Fcas&ticket=ST-example-9a82 HTTP/1.1
Host: sso.example.test
~~~

Illustrative CAS 2.0 XML success response:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

When the ticket is invalid, CAS may return:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_TICKET">
    Ticket is invalid or already consumed
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

The `ST-example-...` strings above are placeholder examples to explain the protocol; real deployments must let CAS issue unpredictable tickets. Never construct tickets from usernames or treat any string starting with `ST-` as authenticated.

## 4. Security Properties of a Service Ticket

An ST is neither a password nor a self-contained decodable token:

1. **Opaque:** the service cannot derive a username or claims from the ST string itself. The service must query the CAS Server via its validation endpoint.
2. **Bound to a service:** a ticket issued for `https://hr.example.test/login/cas` cannot be used to log into `https://admin.example.test/login/cas`.
3. **One-time validation:** the CAS standard requires an ST to be usable for only **one validation attempt**. Whether validation succeeds or fails, the ticket may be consumed; therefore, never blindly retry with the same ST.
4. **Short-lived:** an unused ST should have a short TTL; exact parameters are governed by CAS Server policy. Never assume "5 minutes" is guaranteed across every deployment.
5. **Unpredictable:** CAS generates cryptographically strong random strings; services do not mint them.
6. **Does not replace a local session:** after consuming the ST, the application must manage its own session or appropriate state mechanism.

**Practical consequence:** a `GET /login/cas?ticket=ST-...` request re-sent by the browser after the ST was already validated will **not** count as a valid new login. The user may still access the application via an existing local session, but re-validating that same ST must fail.

### Is Checking the "ST-" Prefix Alone Safe?

No. An attacker can send `ticket=ST-anything`. Spring Security must invoke a trusted `TicketValidator` and verify that the CAS response matches the exact `service`. Never build a rule like "if a ticket parameter exists, mark authenticated", and never trust a user identity attached by the browser in query parameters or headers.

## 5. Service URL: A Small Detail That Often Causes Major Bugs

The `service` parameter is the callback resource URL for which CAS issued the ST. It must be defined consistently across:

- `CasAuthenticationEntryPoint` when redirecting to CAS login.
- `ServiceProperties` in Spring Security.
- `CasAuthenticationFilter` listening at `/login/cas`.
- `TicketValidator` when asking CAS to validate a ticket.
- The service registry allowed by the CAS Server.

Examples:

~~~text
Valid:
https://hr.example.test/login/cas

Common mismatches:
http://hr.example.test/login/cas             (different scheme)
https://hr.example.test:8443/login/cas       (different port)
https://hr.example.test/app/login/cas        (different context path)
https://hr.example.test/login/cas/           (different trailing slash)
https://internal-host:8080/login/cas         (internal backend URL)
~~~

Depending on CAS Server policy/registry, these mismatches cause `INVALID_SERVICE`, validation failures, or redirects outside the allowlist. Never "accept all service URLs" as a quick fix; the service registry must strictly restrict authorized schemes, hosts, ports, paths, and callbacks.

**When the application sits behind a reverse proxy:** the external URL is `https://hr.example.test/login/cas`, while the backend may see `http://127.0.0.1:8080`. Configure a **fixed public service URL** and handle forwarding headers only from a **trusted proxy**. Never blindly accept `X-Forwarded-*` host/scheme values from the public Internet.

## 6. Common CAS Endpoints

| Endpoint | Meaning |
| --- | --- |
| `/login?service=...` | Browser authenticates at CAS and receives an ST for the service; may use TGC for SSO |
| `/logout` | CAS terminates the central SSO session per policy |
| `/validate` | CAS 1.0 protocol, returns simple `yes/no` |
| `/serviceValidate` | CAS 2.0 ST validation, typically returns XML |
| `/p3/serviceValidate` | CAS 3.0 validation, may return user attributes |
| `/proxyValidate` | CAS 2.0 validation supporting proxy tickets |
| `/p3/proxyValidate` | CAS 3.0 validation with proxy info/attributes |
| `/proxy` | Issues a proxy ticket to a backend from a valid proxy-granting ticket (PGT) |

Important parameters:

- `ticket`: the ST being validated; required on validation endpoints.
- `service`: the service identifier for which the ticket was issued; **must match**.
- `renew=true`: enforces a policy requiring fresh primary-credential authentication instead of relying on an existing SSO session; avoid enabling unnecessarily if seamless SSO is desired.
- `gateway=true` on login: attempts passive SSO without forcing an interactive login form; requires handling redirects and the unauthenticated case properly.
- `pgtUrl`: HTTPS callback in proxy-ticket flows, **not needed** for standard services that only consume STs.

CAS 2.0 XML contains `<cas:authenticationSuccess>` or `<cas:authenticationFailure>`; CAS 3 responses can include additional attributes. Do not confuse CAS protocol 3.0 with "CAS Server product version 3"; modern CAS server generations can support multiple protocol versions.

## 7. Participating Spring Security Classes

In **Spring Security Servlet**, the `spring-security-cas` module provides CAS integration.

| Component | Role |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirects browser to CAS login when a request requires authentication |
| `ServiceProperties` | Declares the stable service URL and `sendRenew` policy |
| `CasAuthenticationFilter` | Receives `ticket` at the callback and creates `CasServiceTicketAuthenticationToken` |
| `CasServiceTicketAuthenticationToken` | CAS-specific authentication request before ticket validation |
| `AuthenticationManager` / `ProviderManager` | Dispatches the request to the provider accepting CAS tokens |
| `CasAuthenticationProvider` | Uses `TicketValidator` to verify the ticket; loads user/authorities |
| `Cas20ServiceTicketValidator` | Apereo Java CAS Client class calling the ST validation endpoint |
| `CasAuthenticationToken` | Authenticated `Authentication` produced after the provider succeeds |
| `SecurityContextRepository` | Determines how `SecurityContext` is persisted, typically in the HTTP session |
| `UserDetailsService` / authorities mapper | Maps the CAS-verified username to application permissions |

In modern Spring Security 6.x releases, `CasAuthenticationFilter` creates `CasServiceTicketAuthenticationToken`. Some older tutorials mention a special `UsernamePasswordAuthenticationToken`; always consult the API of your actual version rather than copying Java 5/Servlet XML namespace configurations into a modern Spring Boot project.

**Separation of duties:** the CAS Server verifies identity; Spring's `CasAuthenticationProvider` validates the CAS ticket and builds `Authentication`; the application still decides access control. A valid CAS login does not mean every resource is `permitAll`.

## 8. Spring Boot 3.x / Spring Security 6.x Example (Java 17+)

This example is a Spring-side **CAS Service**, not a CAS Server implementation. It **compiles and runs** once you create a Maven project with the right dependencies, yet end-to-end login requires a live CAS Server, a public callback URL, valid TLS certificates, and matching CAS accounts.

### 8.1. Project Setup and Dependencies

From Spring Initializr, select **Java 17+**, **Maven**, **Spring Boot 3.5.x**, Spring Web, and Spring Security. Boot 3.5.x brings in compatible Spring Security 6.5.x via dependency management. Add to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
</dependency>
~~~

The project needs the transitive dependencies pulled in by the CAS module, including Apereo Java CAS Client (`cas-client-core`). Let Spring Boot's BOM manage Spring Security versions; never arbitrarily mix Spring Security 7 with Boot 3 or incompatible CAS client versions.

### 8.2. Configuring the Service URL

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Example: real CAS Server deployed by the organization.
cas.server-url-prefix=https://sso.example.test/cas

# PUBLIC callback URL, must be allowed by the CAS Server.
cas.service-url=https://hr.example.test/login/cas
~~~

If the application sits behind a TLS proxy, set `cas.service-url` to the **public HTTPS URL** (do not use `localhost:8080` if the browser/CAS cannot reach it). The reverse proxy must route `/login/cas` to the right application.

### 8.3. Complete Java Code

File `src/main/java/demo/cas/CasDemoApplication.java`:

~~~java
package demo.cas;

import java.util.Map;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CasDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${cas.server-url-prefix}") String casBaseUrl,
            @Value("${cas.service-url}") String callbackUrl) throws Exception {

        // CAS identifies the service by this exact callback URL.
        ServiceProperties service = new ServiceProperties();
        service.setService(callbackUrl);
        service.setSendRenew(false);

        // Demo: CAS has verified user 'alice', while the application
        // decides whether to provision the user and grant roles.
        var users = new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}not-used-by-cas")
                    .roles("USER")
                    .build()
        );

        var provider = new CasAuthenticationProvider();
        provider.setKey("hr-cas-provider");
        provider.setServiceProperties(service);
        provider.setTicketValidator(
                new Cas20ServiceTicketValidator(casBaseUrl));
        provider.setUserDetailsService(users);

        var manager = new ProviderManager(provider);

        // Use the same repository for the chain and CAS callback filter:
        // Spring Security 6.x requires explicitly saving the context.
        var contextRepository = new HttpSessionSecurityContextRepository();

        var casFilter = new CasAuthenticationFilter();
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setAuthenticationManager(manager);
        casFilter.setServiceProperties(service);
        casFilter.setSecurityContextRepository(contextRepository);

        var entryPoint = new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(casBaseUrl + "/login");
        entryPoint.setServiceProperties(service);

        http
            .securityContext(sc ->
                    sc.securityContextRepository(contextRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error", "/login/cas").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex ->
                    ex.authenticationEntryPoint(entryPoint))
            .addFilterAt(casFilter, CasAuthenticationFilter.class);

        return http.build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/health")
        String health() {
            return "CAS service started";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList()
            );
        }
    }
}
~~~

**Key points of the example:**

- `ServiceProperties.service` points to the exact public callback for which CAS issues STs. `CasAuthenticationFilter` handles `/login/cas` by default; the example sets the path explicitly to avoid confusion.
- `CasAuthenticationEntryPoint` uses the configured CAS login URL and service identifier to redirect the browser when login is needed.
- `Cas20ServiceTicketValidator` calls CAS over HTTPS with the ticket and service URL. The Java code never parses a username from the ST and never accepts identity from a bare query parameter.
- `CasAuthenticationProvider` relies on the validation response and loads user details. User `alice` is provisioned; any other CAS user not present in the service will not automatically receive `ROLE_USER`.
- `ProviderManager` serves as the CAS filter's authentication manager. Wire the provider into the exact manager used by the filter; do not just declare a provider bean and assume every filter picks it up.
- `HttpSessionSecurityContextRepository` is **wired directly into both the CAS filter and the security chain**; once a ticket is valid, authentication is persisted so subsequent requests use the local session rather than re-validating an already-consumed ST.
- Only `/health` is a public route in this example. `/login/cas` is permitted through authorization so the filter can process callbacks; `permitAll` does not mean a GET callback with a fake ST creates a valid `Authentication`.
- This demo does not implement SLO, proxy tickets, complex attribute mapping, or multi-tenancy. Those require dedicated configuration.

**Version note:** this example targets **Spring Boot 3.5.x / Spring Security 6.5.x**. APIs and session persistence mechanisms may change when upgrading to Spring Security 7 / Boot 4; always consult your project version's Javadoc and migration guide beforehand.

### 8.4. Running and Observing

In the Maven directory (with JDK and Maven or Maven Wrapper installed):

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell/CMD: `mvnw.cmd spring-boot:run`. Without the wrapper: `mvn spring-boot:run`.

Verify that the application starts **without needing CAS**:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

Expected HTTP status and body:

~~~text
HTTP/1.1 200
...
CAS service started
~~~

Once deployed at a public URL and CAS allows `https://hr.example.test/login/cas`, open `https://hr.example.test/me` in a browser:

1. No local session → receives a redirect to CAS login with the `service` parameter.
2. Log into CAS as `alice` or reuse a valid TGC → CAS redirects back to the callback with an ST.
3. The app validates the ST via `/serviceValidate` and loads user `alice` with authority `ROLE_USER`.
4. The browser is routed back to `/me` (via request cache/success flow) and receives a response with authenticated data.

Valid JSON example:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_USER"]
}
~~~

Depending on version and provider, `Authentication` may contain extra framework-recorded authorities such as authentication factor markers; **do not hard-code the entire exact authorities array in integration tests** without verifying against your running version.

Without a real CAS Server or DNS/TLS configured for `example.test`, the example still illustrates the Java configuration yet **cannot complete end-to-end login**. Do not mistake a DNS error to the placeholder domain for a bug in `CasAuthenticationProvider`.

## 9. Standalone Java 17 Experiment: Service Binding and One-Time Validation

To verify the core logic yourself without a CAS Server, the program below simulates a **ticket store** and two rules: an ST belongs to only one service, and every validation attempt consumes the ticket.

This is a **learning model**; it does not perform TLS, password authentication, cryptographically random ticket minting, session management, or CAS XML protocol handling. Never put this simulation code into production.

Create `ServiceTicketRulesDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ServiceTicketRulesDemo {

    record Ticket(String service, String username) {}

    static boolean validate(
            Map<String, Ticket> issued, String value, String service) {
        // remove() simulates a single validation attempt,
        // even when the provided service URL is wrong.
        Ticket ticket = issued.remove(value);
        return ticket != null && ticket.service().equals(service);
    }

    public static void main(String[] args) {
        String hr = "https://hr.example.test/login/cas";
        String admin = "https://admin.example.test/login/cas";

        Map<String, Ticket> tickets = new HashMap<>();
        tickets.put("ST-demo-1", new Ticket(hr, "alice"));

        System.out.println(validate(tickets, "ST-demo-1", hr));
        System.out.println(validate(tickets, "ST-demo-1", hr));

        tickets.put("ST-demo-2", new Ticket(hr, "alice"));
        System.out.println(validate(tickets, "ST-demo-2", admin));
        System.out.println(validate(tickets, "ST-demo-2", hr));
    }
}
~~~

Run:

~~~bash
javac --release 17 ServiceTicketRulesDemo.java
java ServiceTicketRulesDemo
~~~

**Exact stdout:**

~~~text
true
false
false
false
~~~

Explanation:

- Line 1: `ST-demo-1` belongs to the HR service → valid the first time.
- Line 2: ticket already consumed → replay fails.
- Line 3: `ST-demo-2` was issued for HR but sent to Admin → service mismatch.
- Line 4: `ST-demo-2` was also consumed during the mismatched validation → cannot be reused.

In a real CAS Server, validity also includes TTL, randomness, issue timestamp, session/policy status, and additional checks.

## 10. Single Sign-On vs. Single Logout

**SSO:** the user authenticates at CAS once; subsequent applications can receive fresh STs via TGC. Each service still creates its own local session after validating its ST.

**Local logout:** Spring Security clears `SecurityContext` and the local session/cookie per configuration. If the TGC at CAS remains valid, returning to the application in the browser can immediately trigger SSO again without re-entering a password.

**Central logout:** CAS Server terminates the TGT/TGC; however, local sessions already created across applications **do not necessarily disappear automatically**. Synchronized sign-out requires **Single Logout (SLO)** or an equivalent mechanism:

- CAS notifies logged-in services via compatible back-channel/front-channel requests.
- The application verifies the logout notification and locates the matching session to invalidate it.
- Apereo Java CAS Client includes components such as `SingleSignOutFilter`/session mapping; configuration must respect filter ordering, lifecycle, and session storage.
- When running multiple replicas, use a consistent session mapping/shared session strategy; a local map on one instance may miss a session residing on another instance.
- SLO depends on network, browser, and timeout conditions, so design handling for failed notifications.

**Key takeaway:** stripping the ST from the URL after validation and closing the local session does not guarantee the user is fully logged out of CAS. Conversely, CAS logout does not automatically clear every local session if services have not integrated SLO.

## 11. renew, gateway, and SSO Experience

### 11.1. `sendRenew`

When `renew=true` is requested, CAS enforces a policy requiring fresh primary authentication instead of accepting a prior SSO session. In Spring Security, `ServiceProperties.setSendRenew(true)` requests that behavior during login and validation.

Use `renew` when a resource genuinely needs fresh authentication at access time, weighing UX and compatibility with MFA/IdP policies. Do not enable it on every request if your organization expects seamless SSO.

### 11.2. `gateway`

`gateway=true` lets the browser ask CAS whether an SSO session already exists **without forcing an interactive login form**. Without a valid TGC, CAS may redirect back to the service without a ticket. The application must handle the unauthenticated branch cleanly and avoid redirect loops.

### 11.3. Stateful Session vs. Stateless

Typical web browser flows use a **local HTTP session** after validation so the ST is never reused. In remote/stateless scenarios, sending a ticket on every request breaks easily because tickets are single-use. Spring Security offers `StatelessTicketCache` in its CAS integration to support specialized flows, though it does not turn an ST into an infinitely reusable bearer token.

If the client is an SPA, mobile app, or backend API, evaluate UX, cross-site cookies, CSRF, logout, and session models before adopting CAS browser redirects. OIDC/OAuth 2.0 may fit modern API ecosystems better; base the decision on actual requirements and infrastructure.

## 12. Proxy Tickets: Extending When One Service Calls Another

A Service Ticket issued for App A **must never be forwarded to Backend B to log into B**. CAS defines **proxy authentication** for calling downstream backends on the user's behalf:

1. App A validates the ST and supplies an HTTPS `pgtUrl` to CAS, provided App A is registered as a CAS proxy.
2. CAS verifies the callback and issues a **proxy-granting ticket (PGT)** along with a `PGTIOU` correlation handle per protocol.
3. App A uses the PGT to call CAS `/proxy?targetService=...` and obtain a **Proxy Ticket (PT)** for Backend B.
4. App A forwards the PT to Backend B.
5. Backend B calls `/proxyValidate` (not standard `/serviceValidate`) to validate the PT and verifies the **proxy chain** contains only allowed proxies.

This mechanism is not enabled in the ST demo above. Receiving proxy tickets in Spring Security requires `Cas20ProxyTicketValidator`, `CasAuthenticationFilter`/proxy callback configuration, PGT storage, `CasProxyDecider`, and an allowlist of permitted proxies. Carelessly using `AcceptAnyCasProxy` can grant unintended trust.

**Clear separation:** ST is for browser login to one service; PT is for delegation across properly configured services. Never reuse an ST as a PT.

## 13. Security Checklist for Deploying CAS

### 13.1. Protecting Transport and Tickets

- Use **HTTPS with valid certificates** for CAS login, CAS validation, service callbacks, and every channel carrying tickets or cookies.
- The JVM must trust the CAS Server's actual CA; never disable hostname verification or TLS certificate validation "just to get login working".
- Because STs appear in URLs, they can leak through access logs, browser history, proxy logs, monitoring, or `Referer` headers. Validate promptly, clean up callback URLs, and never log raw tickets.
- Never embed tickets into HTML pages, analytics, third-party resource URLs, or uncontrolled redirects. Set an appropriate `Referrer-Policy`.
- Validate STs over server-to-server connections to the **exact trusted CAS Server**; never call arbitrary URLs supplied by a client.

### 13.2. Service Registry and Redirects

- Register an explicit allowlist of permitted services and exact callback URLs on the CAS Server.
- Never accept arbitrary service URLs or overly broad regexes that enable open redirects or ticket leakage to attackers.
- Configure `ServiceProperties.service` as a fixed public HTTPS URL, consistent across login and validation.
- Behind a proxy, trust forwarded host/proto only from a trusted ingress; prevent header spoofing.

### 13.3. Sessions and Permissions

- Configure session fixation protection and Secure/HttpOnly/SameSite cookie flags according to topology and browser requirements.
- Enforce authorization in the application; a valid CAS username does not grant access to every endpoint.
- User/role mapping must account for account changes, disabled accounts, and sensitive privileges.
- Never store CAS passwords in the application, and never place TGC/TGT into the application session.
- Clearly define local logout, central logout, SLO, timeouts, and multi-instance behavior.

### 13.4. Availability and Observability

- The CAS Server is critical infrastructure; monitor validation latency, login failure rates, certificate expiration, and outages.
- Configure sensible timeouts for validation calls; CAS network failures must **fail closed**, never letting users through because a ticket could not be checked.
- Never arbitrarily retry an ST after a timeout: the previous validation attempt may already have consumed the ticket even if the response was lost. Route the user back through login to obtain a fresh ST when needed.
- Audit user/service/trace IDs and appropriate result codes; mask tickets, cookies, and sensitive data.

## 14. Diagnosing Typical Failures

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Redirect loop between App ↔ CAS | Local session not saved, cookie not sent, callback misses filter, wrong service URL | Check `CasAuthenticationFilter`, repository, cookies, path, and redirects |
| CAS returns `INVALID_SERVICE` | Scheme/host/port/path mismatch or callback missing from registry | Compare exact URLs across login, validation, and service registry |
| CAS returns `INVALID_TICKET` | ST expired, already validated, or wrong flow | Inspect request counts and redirects; never retry the same ST |
| GET `/login/cas?ticket=...` creates no Authentication | Filter absent from security chain, callback path mismatch, provider rejects token | Check filter order, matchers, and manager/provider |
| Ticket valid, yet user cannot enter | User unprovisioned or missing `GrantedAuthority` | Check CAS username, `UserDetailsService`, and policy |
| TLS handshake / PKIX error | JVM truststore missing CA, wrong certificate hostname, or misconfigured TLS proxy | Inspect trust chain, DNS, hostname, and upstream proxy |
| Still logged in after local logout | TGC at CAS remains valid; browser gets SSO again | Distinguish local logout from CAS central logout |
| CAS logout leaves service accessible | SLO not integrated or local session not invalidated | Check logout callback, session mapping, and cluster behavior |
| Every request bounces back to CAS | Local session not created/saved, wrong Secure/SameSite/Domain cookie flags | Inspect `Set-Cookie`, request cookies, and context repository |
| Behind reverse proxy generates `http://internal:8080` | Wrong public URL / forwarded headers | Pin `cas.service-url` and configure trusted proxy |
| CAS login succeeds, yet admin API returns 403 | CAS confirmed identity, local authorization denied access | Check authority mapping and access rules |

**Effective debugging order:** verify public callback and service registry → verify redirect with `service` parameter → confirm browser returns with an ST → verify HTTPS back-channel call → inspect validation response → inspect `Authentication`/session → finally inspect authorities. This isolates the exact failing layer instead of relaxing permissions to mask a ticket error.

## 15. Comparing CAS with Other Identity Linking Mechanisms

| Criterion | CAS Protocol (ST) | OIDC Authorization Code | SAML 2.0 Web SSO |
| --- | --- | --- | --- |
| Primary goal | Web SSO with a CAS Server | Federated login and claims under OIDC | Enterprise SSO based on SAML assertions |
| Data returned to browser at login | Opaque ST, typically in `ticket` query param | Authorization code, then back-channel token exchange | SAML response/assertion |
| Verification | Service queries CAS validation endpoint | Client exchanges code at token endpoint and validates tokens/claims per spec | SP validates signature, issuer, audience, time, correlation |
| Central SSO session | CAS TGT/TGC | OpenID Provider session | IdP session |
| Application authorization | Still decided by the app | Still decided by the app | Still decided by the app |
| Best fit | Ecosystems already running CAS, classic browser SSO | Modern web, mobile, and API apps with OIDC-capable IdPs | Enterprise ecosystems requiring SAML |

Never turn an ST into a JWT, long-lived API token, or "OAuth code". CAS ST has its own **service binding + one-time validation** rules.

## 16. Exercises and Self-Check Questions

1. Explain the differences between `TGT`, `TGC`, `ST`, and local `JSESSIONID`.
2. A user logged into App A via CAS; when visiting App B, do they reuse ST-A? Why or why not?
3. Why must Spring Security call `/serviceValidate` instead of trusting the `ticket` parameter?
4. Can ST-A issued for `https://a.example.test/login/cas` be used at App B?
5. What happens when a service validates the same ST a second time after a successful attempt?
6. Why does CAS logout not guarantee clearing sessions across all applications without SLO?
7. When a backend runs on HTTP behind a TLS reverse proxy, should the service URL be internal HTTP or public HTTPS?
8. What distinct roles do `CasAuthenticationProvider`, `TicketValidator`, and `UserDetailsService` play?
9. When is `renew=true` useful, and why can it degrade the SSO experience?
10. Why does a service that has already validated an ST still need `hasRole`/`hasAuthority` rules?

For extra hands-on practice, open Chrome DevTools/Network in a CAS test environment you have access to and record the **request/redirect sequence without storing real tickets**: the login URL with `service`, callback, server-side validation (via redacted logs), CAS cookies, and application cookies. Compare them against the diagram in section 3 and the failure cases in section 14.

## 17. Official References

- [Apereo CAS — CAS Protocol specification](https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html)
- [Apereo CAS — Protocol overview](https://github.com/apereo/cas/blob/master/docs/cas-server-documentation/protocol/CAS-Protocol.md)
- [Spring Security — CAS Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Spring Security — CasAuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html)
- [Spring Security — CasAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Project modules and dependencies](https://docs.spring.io/spring-security/reference/6.5/modules.html)
