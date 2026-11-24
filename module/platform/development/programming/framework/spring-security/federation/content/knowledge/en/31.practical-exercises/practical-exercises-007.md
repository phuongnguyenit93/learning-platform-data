# Integrating CAS Login, Service Ticket Verification, and Single Sign-Out

## 1. Objectives of the Comprehensive Exercise

In **Spring Security - federation**, this exercise combines three tasks that must be designed as **one complete login–session–logout lifecycle**:

1. **CAS Login**: redirect users from the Spring Security application (called the *service* or CAS client) to the Central Authentication Service (CAS Server) for centralized login.
2. **Service Ticket (ST) Verification**: issue an `Authentication` and local `HttpSession` only after the app verifies the ticket with the CAS Server over back-channel HTTPS for the **exact service URL**, and applies local account/authorization policy.
3. **Single Sign-Out (SLO)**: when the CAS SSO session ends, the app receives the logout notification and invalidates **only the local session linked to the service ticket**, never blindly wiping all sessions by username.

This is the **CAS protocol**, not SAML 2.0 Web SSO—even though CAS logout notifications may use XML with a SAML 2.0 namespace. Never use `Saml2WebSsoAuthenticationFilter` in place of `CasAuthenticationFilter`, nor assume an OIDC `id_token`, a CAS `ticket`, and a SAML `Assertion` are interchangeable.

### 1.1. Verifiable Outcomes

Upon completion, a development team can demonstrate:

- User `alice` visiting `/reports` with no local session is redirected to `https://sso.example.org/cas/login?...`.
- CAS Server logs the user in and redirects to the **exact** `https://portal.example.org/login/cas?ticket=ST-...`.
- Spring Security calls `https://sso.example.org/cas/serviceValidate`, passing the **exact** `ticket` and `service`.
- Only after a successful validation response does the app create `Authentication` and a session; disabled local accounts or those lacking permissions are denied.
- Reusing the same ST or using an ST issued for another service is **not** allowed.
- Local `POST /logout` ends the app session yet **does not by default terminate the CAS TGT**.
- Global logout via CAS `/logout`, when CAS SLO is enabled and delivery succeeds, ends sessions at participating CAS clients that handle SLO.
- Forged SLO callbacks cannot force the app to destroy sessions; valid callbacks invalidate only the session mapped to the matching ticket.
- In a cluster, ticket/session mappings and local session storage share a consistent design across nodes, or deployment limits are explicitly documented.

**Principle:** CAS handles centralized authentication; the Spring Security app remains responsible for local sessions, local account admission, authorization, and SLO handling. A successful HTTP redirect or a query parameter starting with `ST-` is not proof of user authentication.

## 2. Vocabulary and Trust Boundaries

| Subject | Location / Controller | Role | Security Boundary |
| --- | --- | --- | --- |
| **CAS Server** | `https://sso.example.org/cas` | Login, holds SSO session/TGT, issues and verifies STs, sends SLO notifications if configured. | Trust only approved CAS Server endpoints over HTTPS/TLS; service registry bounds clients. |
| **CAS service / Portal** | `https://portal.example.org` | Spring app needing centralized login; verifies ST, creates `SecurityContext` and `HttpSession`. | Never consider a user logged in just because the browser carries a ticket. |
| **TGT** (Ticket Granting Ticket) | CAS Server | Backing ticket issuing STs for a CAS SSO session. | Never forward raw TGTs to the Spring app. |
| **TGC** (Ticket Granting Cookie) | Browser on the CAS site | Cookie representing the SSO session so CAS recognizes the browser on subsequent logins. | **Distinct** from the Spring app's `JSESSIONID`. |
| **ST** (Service Ticket) | Carried by browser to service callback; validated by CAS Server | Opaque, short-lived, **single-use** ticket bound to a specific service. | ST is a bearer credential; never log raw URLs/tickets. |
| **CAS Assertion** | Result of **ticket validation** from CAS Server | Contains principal and, depending on CAS version/profile, attributes. | Must come from a trusted CAS ticket validator, never from client headers. |
| **Spring Authentication** | App `SecurityContext` | Principal/authorities after CAS validation and local admission. | Does not automatically grant business/admin permissions. |
| **HttpSession / JSESSIONID** | Spring app and browser | Stores `SecurityContext`/local data per session strategy. | Distinct from CAS TGT/TGC; has its own TTL. |
| **SLO SessionIndex** | `LogoutRequest` sent by CAS in CAS SLO format | Normally references the **service ticket ID** to locate the local session. | **Not `HttpSession` ID**; never use username to wipe all sessions. |

### 2.1. Two Connection Types That Must Never Be Mixed

```text
Browser-facing redirects:
  Browser ----> CAS /login?service=...
  Browser <---- CAS redirect
  Browser ----> Portal /login/cas?ticket=ST-...

Trusted server-to-server:
  Portal ---- HTTPS ----> CAS /serviceValidate?ticket=...&service=...

Single Logout:
  Browser/User ----> CAS /logout
  CAS Server ---- SLO notification ----> Portal service callback
  Portal maps ticket -> local session -> invalidates session
```

**The CAS Server verifies user credentials**; the browser **does not** verify STs, and the app does not "decode an ST" to identify the user. The ticket validator must query the real CAS Server.

## 3. Lab Environment and Example Addresses

A practice architecture consists of:

| Component | Illustrative URL | Purpose |
| --- | --- | --- |
| CAS Server | `https://sso.example.org/cas` | CAS login/validation/logout. |
| CAS Login | `https://sso.example.org/cas/login` | CAS authentication page. |
| ST validation | `https://sso.example.org/cas/serviceValidate` | CAS 2.0 XML validation for ST. |
| CAS 3 attributes | `https://sso.example.org/cas/p3/serviceValidate` | CAS 3 profile with attributes when properly configured on the client. |
| CAS logout | `https://sso.example.org/cas/logout` | Terminates the CAS SSO session. |
| Spring app | `https://portal.example.org` | Protected service. |
| Service callback | `https://portal.example.org/login/cas` | `CasAuthenticationFilter` receives STs and CAS SLO normally posts to this service URL. |
| Protected page | `https://portal.example.org/reports` | Accessible only after Authentication + authorization. |
| Local logout | `POST https://portal.example.org/logout` | Terminates the local session. |
| Sign-out page | `https://portal.example.org/signed-out` | Explains local vs. global logout. |

**These are illustrative domains, not a pre-built environment.** In real deployments, use HTTPS with valid certificates; the CAS Server maintains a **service registry** permitting exact service URLs or strictly reviewed regexes. Never register wildcard all-URLs, wildcard subdomains, or `http://` in production.

### 3.1. Prerequisites for Real Practice

1. Java 17 or newer, and an organization-supported Spring Boot / Spring Security Servlet stack.
2. A sandbox CAS Server, test accounts `alice` and `bob`, and a service registry with valid callbacks.
3. `spring-security-cas` + Apereo Java CAS Client compatible with your **exact** Spring Security / Jakarta Servlet runtime; Spring Security 7 docs still cover CAS client integration.
4. Bidirectional HTTPS for browser→service and service→CAS, with truststores matching the right CA/hostname.
5. A `UserDetailsService` or local account directory holding `enabled/disabled` status, tenant, and permissions, never trusting raw role inputs from the browser.
6. Ability to inspect **redacted** logs across CAS, Spring Security, proxy, session store, and SLO delivery.
7. A local session strategy, shared store/affinity when running multiple nodes, and browser test scripts to trace cookies and redirects.

**Version caution:** the CAS chapter of the Spring Security reference retains some descriptions/XML dating back to Spring Security 3.x even though the doc path still exists in 7.x. Always check **exact-release Javadocs**, especially `CasAuthenticationProvider`, Jakarta Servlet, and the CAS Client major version. Never copy an old namespace snippet and assume it builds on every Boot release.

## 4. Step-by-Step CAS Login: From `/reports` to Authentication

### 4.1. Complete Sequence

```text
User Browser              Spring Portal                  CAS Server
    |                          |                              |
    | GET /reports             |                              |
    |------------------------->|                              |
    |                          | unauthenticated              |
    |                          | ExceptionTranslationFilter   |
    |<-------------------------| 302 to CAS login             |
    |                          |                              |
    | GET CAS /login?service=<encoded portal /login/cas>      |
    |-------------------------------------------------------->|
    |                          |                      check TGC |
    |                          |                      or MFA    |
    |<--------------------------------------------------------|
    | 302 Location: https://portal.../login/cas?ticket=ST-A    |
    |                          |                              |
    | GET /login/cas?ticket=ST-A                              |
    |------------------------->|                              |
    |                          | CasAuthenticationFilter      |
    |                          | CasAuthenticationProvider    |
    |                          | HTTPS /serviceValidate       |
    |                          | ticket=ST-A                  |
    |                          | service=exact callback       |
    |                          |----------------------------->|
    |                          |                              | verify
    |                          |                              | ST, service,
    |                          |                              | one-time
    |                          |<-----------------------------|
    |                          | CAS XML success/failure      |
    |                          |                              |
    |                          | load local user + authorities|
    |                          | create Authentication        |
    |                          | SecurityContext / session    |
    |<-------------------------| redirect to safe page        |
    | GET /reports with local JSESSIONID                     |
    |------------------------->|                              |
    |<-------------------------| 200 if authorized             |
```

**Trust decision point:** `CasAuthenticationProvider` grants `Authentication` only when a `TicketValidator` validates the ST with the CAS Server and combines it with local account details/authorities. **A local `UserDetailsService` is never a CAS password verifier**; it looks up roles/status after identity is verified.

### 4.2. CAS TGC Differs from the Local Session Cookie

- The browser holds a **CAS TGC** after logging into CAS.
- Portal holds its own **JSESSIONID** after logging into Portal.
- Deleting Portal's `JSESSIONID` while keeping CAS TGC: visiting a protected Portal page can perform **silent SSO** via a fresh ST without prompting for a password again.
- Clearing CAS TGC/TGT without SLO: Portal's `JSESSIONID` can still live until the local session expires or logs out.
- CAS SLO attempts to close the gap between the two states, yet delivery is **best-effort** with no guarantee that every service receives the callback.

## 5. `Service Ticket`: Service-Scoped, Single-Use, Short-Lived

Per the CAS protocol:
- The CAS Server issues an ST for the **exact service** requested via `/login?service=...`.
- The browser returns to the service URL with query `ticket=ST-opaque`.
- The service calls `/serviceValidate` or `/p3/serviceValidate` with the ticket and the **exact matching service URL**.
- An ST can be validated **only once**; even when validation fails with `INVALID_SERVICE`, the ticket is consumed per the CAS spec.
- STs have a short TTL and carry no client-decodable credentials.
- An `authenticationSuccess` response is trustworthy only from a trusted CAS back-channel with TLS CA/hostname verification—never read from a browser-submitted form field.

### 5.1. Common Pitfall: Service URL

```text
CAS issues:
  service=https://portal.example.org/login/cas

Spring validates:
  service=https://portal.example.org/login/cas
  ticket=ST-A       -> SUCCESS

Wrong validation:
  service=http://portal-internal:8080/login/cas
  ticket=ST-A       -> INVALID_SERVICE

Also wrong:
  service=https://portal.example.org/admin
  ticket=ST-A       -> INVALID_SERVICE
```

`service` is not "a plausible-looking domain"—it is the exact **service identifier** the CAS Server bound to the ST. Depending on the CAS server's URL matching policy, differing schemes, hosts, ports, paths, or queries trigger mismatches. **Strict/exact public URL matching is the safe default.** Never change the CAS registry to `.*` just to silence `INVALID_SERVICE`.

Behind a load balancer/ingress:
- Public service is `https://portal.example.org/login/cas`, not `http://app-pod:8080/login/cas`.
- `ServiceProperties.service` must match the callback URL handled by the filter.
- Proxies must overwrite client-sent `X-Forwarded-Proto/Host/Port` and send trusted values to the backend if configured to use them.
- Never let attackers control `Host`/forwarded headers to forge redirect service URLs.
- App/context paths, trailing slashes, queries, and URL encoding must stay consistent.

### 5.2. Sample CAS `/serviceValidate` Call

Use **only fake tickets in test environments**, because STs in URLs can be logged:

```bash
curl --silent --show-error --fail-with-body \
  --get 'https://sso.example.org/cas/serviceValidate' \
  --data-urlencode 'service=https://portal.example.org/login/cas' \
  --data-urlencode 'ticket=ST-DEMO-NOT-REAL'
```

`curl --get --data-urlencode` properly URL-encodes query parameters. A fake ST returns `INVALID_TICKET`, which is the **expected result**. Never copy real STs from DevTools into shell history or logs.

**Illustrative success response** (trustworthy only from verified CAS):

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

**Illustrative failure response:**

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    The ticket was issued for a different service
  </cas:authenticationFailure>
</cas:serviceResponse>
```

Beyond `INVALID_SERVICE`, handle `INVALID_TICKET`, `INVALID_REQUEST`, and `INTERNAL_ERROR` per version/profile. The HTTP status can still be 200 on a CAS XML `authenticationFailure`, so **never grant login just by checking HTTP 200**; inspect the validator outcome per the CAS protocol.

### 5.3. Differences Between CAS 2 and CAS 3

| Endpoint | When to Use | Notes |
| --- | --- | --- |
| `/validate` CAS 1 | Legacy two-line `yes/no` | Lacks attributes / CAS 2 XML structure; not for proxy tickets. |
| `/serviceValidate` CAS 2 | ST → XML `authenticationSuccess`/Failure | Suits basic CAS service ticket verification. |
| `/p3/serviceValidate` CAS 3 | ST validation with CAS attributes | Use a CAS3-compatible validator like `Cas30ServiceTicketValidator` when attributes are needed. |
| `/proxyValidate`, `/p3/proxyValidate` | ST/PT under proxy profile | **Do not use** if the lab needs only direct CAS Login; accepting PTs requires an explicit proxy trust policy. |

**Do not confuse with a SAML2 ACS endpoint.** A CAS 2.0 protocol response uses the `cas:` prefix, yet it is not an IdP SAML Assertion.

## 6. Spring Security Component Diagram

```text
HttpSecurity / Spring Security FilterChain
  |
  +-- ExceptionTranslationFilter
  |     +-- CasAuthenticationEntryPoint
  |           builds CAS /login?service=<ServiceProperties.service>
  |
  +-- CasAuthenticationFilter
        +-- watches /login/cas
        +-- extracts opaque ticket parameter
        +-- delegates to AuthenticationManager / ProviderManager
              +-- CasAuthenticationProvider
                    +-- CAS TicketValidator (server-to-server HTTPS)
                    +-- CAS Assertion: principal, attributes
                    +-- UserDetailsService / account admission
                    +-- CasProxyDecider (if accepting proxy tickets)
        +-- success: SecurityContextRepository / HttpSession
        +-- failure: deny, no local session

Before Spring Security filters (for CAS SLO):
  Apereo SingleSignOutFilter
       +-- map validated ticket request to HttpSession
       +-- handle CAS logoutRequest and invalidate mapped session
  SingleSignOutHttpSessionListener
       +-- remove mappings when sessions expire or are destroyed
```

### 6.1. Components and Responsibilities

| Class | Role |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirects the browser to CAS login. |
| `ServiceProperties` | Defines the callback service URL and `sendRenew`. |
| `CasAuthenticationFilter` | Receives `ticket` at callback `/login/cas`. |
| `CasAuthenticationProvider` | Bridges Spring `Authentication` to the CAS `TicketValidator`. |
| `Cas20ServiceTicketValidator` | Validates ST against CAS 2 `/serviceValidate`. |
| `Cas30ServiceTicketValidator` | Validates ST/attributes via CAS 3 profile when properly configured. |
| `ProviderManager` | Routes authentication requests to the CAS provider. |
| `UserDetailsService` | Looks up local user status and authorities after the CAS assertion. |
| `SecurityContextRepository` | Saves/loads Spring `Authentication` in the local session. |
| `SingleSignOutFilter` | CAS client filter tracking tickets/logins and handling SLO by invalidating the matching session. |
| `SingleSignOutHttpSessionListener` | Cleans up mappings when an `HttpSession` is destroyed or expires. |

**Cross-check class and method names against your exact Spring Security / CAS Client versions.** `SingleSignOutFilter` is not Spring's `LogoutFilter`; the two mechanisms handle two distinct logout sources.

## 7. Maven/Gradle Dependencies and Compatibility Issues

In a Spring Boot project whose BOM/parent already manages Spring Security versions:

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
  <dependency>
    <groupId>org.apereo.cas.client</groupId>
    <artifactId>cas-client-core</artifactId>
    <!-- Choose a Jakarta-compatible release approved by your BOM. -->
  </dependency>
</dependencies>
```

**This is a dependency fragment**, not a complete POM. CAS Client may be pulled transitively by `spring-security-cas`; declare it directly only when pinning/controlling versions. **Never leave the artifact version blank** if your BOM does not manage `cas-client-core`; pin an approved version on direct dependencies instead. Java CAS Client 4.x belongs to the Jakarta-compatible line—for example, Maven Central lists `cas-client-core` 4.1.1 in 2026—yet always verify compatibility across Spring Security, Boot, Java, and JAXB/Jakarta.

Commands to inspect dependencies:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.apereo.cas.client
mvn dependency:tree -Dincludes=jakarta.servlet
mvn dependency:tree -Dverbose
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-cas --configuration runtimeClasspath
./gradlew dependencyInsight --dependency cas-client-core --configuration runtimeClasspath
```

**Common error:** Boot 3/4 apps use `jakarta.servlet.*`, whereas legacy CAS clients bind to `javax.servlet.*`, or mismatched CAS Client 3.x/4.x modules cause `NoClassDefFoundError`. Never swap single JARs on the classpath until it happens to boot; select a compatible set per BOM and security advisories.

## 8. Java Spring Security Configuration — Scoped Example

The snippet below clarifies wiring **Spring Security 7.1 API** with a compatible CAS client dependency set. It is a **Spring Boot Servlet application fragment** requiring Java, Servlet, Spring Security, CAS dependencies, and a real `UserDetailsService`; **it is not a standalone Java SE file**. Hostnames are examples—no live CAS Server exists at these URLs.

```java
package example.cas;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class CasLoginSecurityConfig {

    private static final String CAS_BASE =
        "https://sso.example.org/cas";

    private static final String PORTAL_SERVICE =
        "https://portal.example.org/login/cas";

    @Bean
    SecurityFilterChain casChain(HttpSecurity http,
                                 UserDetailsService localUsers)
            throws Exception {

        ServiceProperties service = new ServiceProperties();
        service.setService(PORTAL_SERVICE);
        service.setSendRenew(false);

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(service);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(CAS_BASE));
        provider.setUserDetailsService(localUsers);
        provider.setKey("portal-cas-authentication-provider-v1");

        CasAuthenticationEntryPoint entry =
            new CasAuthenticationEntryPoint();
        entry.setLoginUrl(CAS_BASE + "/login");
        entry.setServiceProperties(service);

        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setServiceProperties(service);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());

        http.authenticationProvider(provider)
            .exceptionHandling(ex ->
                ex.authenticationEntryPoint(entry))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/signed-out").permitAll()
                .requestMatchers("/login/cas").permitAll()
                .requestMatchers("/reports").hasAuthority("reports:read")
                .anyRequest().authenticated())
            .addFilterBefore(casFilter,
                UsernamePasswordAuthenticationFilter.class)
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out"));

        return http.build();
    }
}
```

**Items to complete before production:**
1. Supply `UserDetailsService` from a local directory, map the CAS principal to the right tenant/account, block `disabled/locked/expired` accounts, and verify authorities.
2. Run integration tests confirming `SecurityContext` persists properly in `HttpSession`, with cookies and session fixation protection. Custom filters/providers may need a session strategy/context repository consistent with `SecurityFilterChain`.
3. The snippet above covers only **CAS Login and ST validation**—it does **not yet** include the SLO filter, listener, gateway source checks, logout-all flow, or health monitoring.
4. `CasAuthenticationFilter` is instantiated **inside the chain**, not exposed as a `@Bean` Servlet Filter that would auto-register and run twice.
5. `/login/cas` must be registered on the CAS Server with the exact service URL, and `permitAll` still executes the CAS auth filters. **Never** put the callback in `web.ignoring()`.
6. `http.logout` keeps CSRF enabled by default; for browser sessions, **POST `/logout` requires a CSRF token**. Never disable CSRF app-wide because CAS SLO uses POST.
7. `UserDetailsService` must enforce local roles/status per policy. Never ship a test account with default `ROLE_ADMIN` in production.
8. `setKey` is Spring's internal provider identifier, **not a CAS shared secret** or CAS password.
9. `setSendRenew(true)` forces CAS to re-prompt for primary credentials per the CAS protocol for sensitive services; test UX/MFA and the CAS registry, and never treat it as logout.
10. If using `Cas30ServiceTicketValidator` for attributes, swap the class per version and verify mapping/attribute trust; never accept raw header roles.

### 8.1. Additional Steps Outside Code

- `UserDetailsService`: take `username` from the **verified CAS Assertion**, never from query parameters or headers.
- Separate `SecurityFilterChain` for admin endpoints if needed, preserving CSRF and tenant scoping.
- Ingress HTTPS/forwarded headers: accurate public service/callback URLs; never trust client-supplied `Host`.
- Session strategy/cookies: `HttpOnly`, `Secure`, `SameSite` suitable for GET CAS callbacks; CAS SLO back-channel uses no browser cookies.
- CAS Server service registry: strictly bound allowed service URLs/patterns; enable/allow SLO delivery to the service.
- Logging: redact `ticket` and `logoutRequest` at gateway, app, and APM.
- Security review: inbound CAS SLO source trust; session mappings stay accurate and expire cleanly across nodes.

## 9. `CasAuthenticationProvider`: Local Admission Does Not Equal CAS Login

Suppose CAS Server succeeds and returns principal `alice`. The app may have local records:

| CAS Principal | Local Account | Local Permissions | `/reports` |
| --- | --- | --- | --- |
| `alice` | ACTIVE | `reports:read` | 200. |
| `bob` | ACTIVE | lacks `reports:read` | 403. |
| `carol` | DISABLED | has old role | Reject admission/login. |
| `david` | Not provisioned | none | Deny or route through approved provisioning workflow. |
| `alice@partnerB` | Belongs to another tenant | partnerB only | Never admitted to tenantA despite similar username. |

**Approach:** after CAS validation, `CasAuthenticationProvider` queries `UserDetailsService` and/or a controlled converter to check local account status using trusted mappings. `CasAuthenticationProvider#setUserDetailsChecker` can help enforce status checks depending on the Spring Security version. When reading attributes from CAS 3, distinguish `CAS` verified attributes from forged `HTTP headers` and **never grant `ROLE_ADMIN` from an attribute without a trust policy**.

### 9.1. Handling Duplicate Usernames / Multi-Tenant

Never use a bare string `"alice"` across all external identity sources if one CAS Server serves multiple realms/tenants. Resolve a stable subject combined with the CAS realm/issuer policy, map to a unique local key, check lock status, and verify permissions. Never auto-create privileged local accounts for unknown CAS principals.

### 9.2. Logout and Permissions Do Not Refresh Instantly

Once `Authentication` and roles sit in a local session, permissions may survive until the session expires. If `bob` has a permission revoked, prior CAS ticket validation will not cause Spring to re-check on every request automatically. Implement TTLs, revocation, or authority refresh matched to risk and plan for existing sessions.

## 10. Single Sign-Out: Local Logout, CAS Logout, and Session Sync

### 10.1. Three Distinct Cases

| Action | CAS TGT/TGC | Local Portal Session | Other CAS Clients |
| --- | --- | --- | --- |
| Local `POST /logout` | **Not terminated automatically** | Spring logout clears `Authentication` and invalidates local session per config. | Unaffected. |
| Browser visits CAS `/logout` | CAS destroys TGT/TGC | **Not cleared automatically** if client lacks/misses SLO. | Same; depends on SLO. |
| CAS `/logout` + working SLO | CAS TGT destroyed | CAS sends logout notification; client maps ticket→session and invalidates. | Clients receiving notifications close matching sessions. |

The CAS Server is an **SSO session manager**, **not the session manager for every application**. CAS can send SLO to multiple services, yet per the CAS protocol delivery failures **do not block CAS logout**, so ending the TGT does not prove every local session was destroyed.

### 10.2. Where Does the SLO Message Go?

Under CAS SLO back-channel:
- CAS Server POSTs to the **service URL recorded when the ST was issued**; in our example, `/login/cas`.
- The form parameter is normally named **`logoutRequest`**, containing XML in CAS SLO format.
- The XML uses `samlp:LogoutRequest`, and `samlp:SessionIndex` typically **carries the service ticket ID**, not the username, TGT, or `JSESSIONID`.
- The CAS client looks up `ST -> HttpSession` and invalidates the matching session.
- `SingleSignOutHttpSessionListener` removes mapping records once a session expires or is invalidated.

**Synthetic** XML example, never for real verification:

```xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-example"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:00Z">
  <saml:NameID>@NOT_USED@</saml:NameID>
  <samlp:SessionIndex>ST-opaque-original</samlp:SessionIndex>
</samlp:LogoutRequest>
```

**Do not mistake this for a complete SAML 2.0 Web SSO signature**: CAS Single Logout formats its XML with a SAML namespace, yet **CAS Client SLO policy and transport trust are separate**. Because back-channel POSTs lack a trustworthy signature, **protect the callback source** via mTLS/trusted gateway/network ACLs, exact routing, and anti-spoofing defenses (preventing logout DoS on others' sessions).

### 10.3. Exact SLO Progression

```text
User has local CAS sessions:
  Service Ticket ST-1 -> Portal Session SID-1 -> alice
  Service Ticket ST-2 -> Another Session SID-2 -> alice

User asks CAS /logout:
  CAS destroys SSO TGT/TGC
  CAS sends SLO POST for ST-1 to Portal service URL
  Portal SingleSignOutFilter:
     recognize trusted logoutRequest
     look up ST-1 -> SID-1
     invalidate SID-1
     remove mapping ST-1
  CAS sends logout for ST-2 if recorded/appropriate:
     invalidate SID-2
```

**Never use `NameID=alice` to destroy all of Alice's sessions.** A user may have two browsers, two devices, or a local session not yet recorded by CAS. Invalidating by exact service-ticket mapping both honors the contract and limits blast radius.

### 10.4. SLO Can Be Fire-and-Forget

CAS SLO delivery is best-effort per protocol:
- Client offline, network timeout, or WAF blocks POST => local session may stay alive.
- `ST → Session` mapping lost on node restart => callback finds no session.
- CAS TGT expires naturally without SLO in certain modes/server policies => app session lives independently.
- Browser/front-channel SLO blocked by cookie/privacy policies or a closed tab.
- Late/duplicate SLO POST after session expiry => handle idempotently without throwing endless 500s.
- User performs local logout while CAS SSO stays alive => visiting a protected resource may silently re-login.

Defense-in-depth solution: bounded session TTLs, local revocation, access-control checks, durable SLO storage where needed, and monitoring/incident response; **never rely on SLO as the sole revocation mechanism** for privileged access.

## 11. Apereo Java CAS Client `SingleSignOutFilter` and Listener

Per Spring Security CAS docs and Apereo Java CAS Client:
- **`org.apereo.cas.client.session.SingleSignOutFilter`** records the ticket on login requests to map it to the session, and also receives CAS `logoutRequest`s to invalidate sessions.
- **`org.apereo.cas.client.session.SingleSignOutHttpSessionListener`** cleans up mappings when sessions are destroyed.
- **The SLO filter must run before the CAS Authentication Filter** and usually before the Spring Security `FilterChain` in the Servlet filter stack so it observes both the initial ST request and SLO callbacks.
- Apereo Java CAS Client exposes `logoutParameterName` (default `logoutRequest`) and `logoutCallbackPath` to restrict which endpoint parses POST bodies.
- UTF-8 encoding filters must be ordered properly, especially if a form/POST body could be consumed before the CAS SLO filter runs.

### 11.1. Sample Servlet Listener/Filter Config for Spring Boot Jakarta

This is a **Spring Boot Servlet fragment** with a Jakarta-compatible Apereo Java CAS Client; **it is not a standalone Java SE program**:

```java
package example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloServletConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilter() {
        FilterRegistrationBean<SingleSignOutFilter> reg =
            new FilterRegistrationBean<>();
        reg.setFilter(new SingleSignOutFilter());
        reg.addUrlPatterns("/*");
        reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        reg.addInitParameter("logoutCallbackPath", "/login/cas");
        return reg;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
```

**Things to verify when wiring into the real filter chain:**
1. With Boot/security filter ordering, `SingleSignOutFilter` must execute **before** the Spring Security CAS login filter and any request handler that might consume the POST body.
2. Verify `logoutCallbackPath` matches the exact service URL/path the CAS Server POSTs to; check the exact CAS client release's source/Javadoc when deploying.
3. The ticket-to-session mapping is registered during **GET `/login/cas?ticket=...`**, and the session survives CAS authentication; test across session-fixation ID rotation.
4. Register the listener **once**—never duplicate it across `web.xml` and Java bean registration.
5. That filter **does not itself verify the SLO caller is the CAS Server**; enforce mTLS/ingress policy, network identity/source restrictions, and a separate security review.
6. On Boot 3/4 using Jakarta Servlet, the CAS Client must be a Jakarta-compatible build; never mix legacy `javax.servlet.Filter` classes.
7. Default mapping in Java CAS Client is typically **in-memory/static** per servlet context—**unsuitable by default for multi-node**, requiring shared session mapping or a clustering strategy supported by your client version.
8. `SessionIndex` must map **this session's ST**, not `JSESSIONID` or username. Test logging out one user holding multiple sessions.
9. CAS SLO POST runs before Spring's CSRF filter when intercepted in its own Servlet filter; **never disable CSRF app-wide**. If SLO traverses the Spring chain, configure only a narrow CSRF exemption aligned with source trust.
10. Test CAS SLO interceptor/registration behavior with JUnit integration and a CAS sandbox rather than relying on mocked `HTTP 200`.

### 11.2. Network Permissions and SLO Source Trust

Depending on deployment, CAS SLO XML does not always carry a signed XML signature. **An attacker who discovers an ST (e.g., leaked in access logs) and can POST a forged `logoutRequest` can force that session to terminate** if the endpoint fails to verify the sender. This is **logout DoS / session disruption**—not necessarily account takeover, yet still a security defect.

Protections:
- Accept SLO callbacks only from the CAS Server / approved gateway, using mTLS / service identity whenever possible.
- Network ACLs are defense-in-depth; never trust client-supplied `X-Forwarded-For`.
- Block inbound SLO requests from arbitrary hosts reaching pods directly and bypassing ingress.
- Restrict `logoutCallbackPath`, HTTP method, body size, XML parser settings, and rate limits.
- Never log raw `logoutRequest`, ST, or `JSESSIONID`; log only opaque event refs.
- In a cluster, `ST → session` mapping must be reliable and deletions idempotent.

**Never apply `permitAll` across all endpoints just so CAS SLO can call in.** Callbacks lack browser `Authentication`, yet must flow strictly through the protocol filter and source trust checks.

## 12. Designing "Sign Out Here" vs. "Sign Out Everywhere" Actions

A UI should separate two clear choices:

- **Local logout**: POST `/logout` with a Spring Security CSRF token, clear local `SecurityContext` and `HttpSession`, and render `/signed-out`.
- **Global logout**: POST a CSRF-protected endpoint to destroy the local session, then **redirect the browser to a fixed CAS logout URL from server configuration**. CAS destroys the TGT, dispatches SLO to supported services, and optionally redirects to a **CAS-registered service/redirect URL** per policy.

**Never use a GET link with local logout side effects without CSRF evaluation**; never accept `?returnUrl=https://attacker.example` and pass it into CAS `service` or a local redirect. If the CAS Server allows post-logout redirects, the URL must match the exact service registry/allowlist—never attacker input.

### 12.1. Global Logout Pseudocode Pattern

```text
POST /logout/all
  require current browser CSRF token
  clear local SecurityContext, invalidate local HttpSession
  expire local auth-related cookies via approved policy
  redirect browser to fixed:
    https://sso.example.org/cas/logout
  CAS invalidates its TGT/TGC
  CAS attempts SLO notifications to other CAS clients
  show safe public signed-out page according to CAS server config
```

An application can handle local logout via `SecurityContextLogoutHandler`, a custom logout success handler, and CSRF config. The snippet above is **workflow pseudocode**, not drop-in code for every Spring version.

### 12.2. Why Can Local Logout Immediately Log Back In?

```text
Portal POST /logout
  -> JSESSIONID invalidated
Browser GET /reports
  -> Portal redirects CAS /login
  -> CAS TGC still active
  -> CAS issues NEW ST
  -> Portal verifies it and logs in again
```

This is **CAS SSO working as designed**, not automatically a bug. If the user intends to leave the entire suite, terminate the CAS TGT/TGC; if leaving only this app, design UX that avoids immediately redirecting back to a protected URL.

## 13. Sessions, Ticket Mapping, and Concurrency

### 13.1. Session Fixation Protection

Spring Security enforces a session fixation strategy: after successful CAS login, the container may call `changeSessionId()` or migrate the session. Never store a **pre-login `JSESSIONID` string** as an immutable `ST → session` value. CAS client filters normally track `HttpSession` and a listener to invalidate properly; **test explicitly across session rotation** rather than assuming mappings survive every implementation.

### 13.2. Same User, Two Devices

```text
Laptop browser:
   CAS ST-A -> Portal session SID-A
Phone browser:
   CAS ST-B -> Portal session SID-B

CAS SLO for ST-A:
  invalidate SID-A
  leave SID-B alone until the matching SLO event arrives
```

Never delete `username -> all sessions` when the notification identifies a single ticket. If policy requires revoking **all** of a user's sessions (offboarding, compromise), that is a **distinct administrative workflow** requiring explicit tenant/user identity and audit.

### 13.3. Multi-Node Failure

```text
Login request:
  LB -> Node A, ST-1 mapped to HttpSession SID-1 in A's memory

SLO callback:
  CAS -> LB -> Node B
  Node B has no mapping ST-1 -> SID-1
  returns 200/no-op or no match
  SID-1 on Node A remains active
```

**Sticky sessions do not automatically fix back-channel CAS SLO**, because the SLO callback **carries no browser `JSESSIONID`** for the load balancer to route by sticky cookie. Use one of these tested designs:
- Shared `ST → session ID` mapping plus shared Spring Session store with atomic revocation APIs.
- Dedicated SLO coordinator service or event bus routing to the owning node with durable delivery, TTL, and replay/idempotency.
- Client/storage adapter supporting distributed mapping if your exact version provides it.
- Keep to a single-node architecture for simple labs, yet **never advertise multi-node SLO** when backed only by a local static map.

Test rolling restarts, node failovers, Redis outages, delayed/retried callbacks, and two browsers. **Never award QA PASS merely because one node returned SLO 200.**

### 13.4. Idempotency and Pending Logout

- Repeated `LogoutRequest` for an already-invalidated ST → no-match/idempotent, never breaks a newer session.
- Late SLO arriving after the user already logged back in with a new ST → never invalidate the **new session** just because the username matches.
- CAS Server timeout → app must still enforce session TTLs or fallback revocation; never "ignore" stale sessions indefinitely.
- HTTP 200 from the callback does not prove the session was deleted; verify access with the **old cookie** is rejected.
- `HttpSessionListener` cleanup curbs stale ticket mappings; when the store or listener fails, emit telemetry and repair.
- Local session expiry is independent of CAS TGT expiry; refresh permissions per policy.

## 14. Testing Directly Against a CAS Sandbox

### 14.1. Preparing the CAS Server Registry

1. Permit service `https://portal.example.org/login/cas` in the CAS registry.
2. Enable the CAS protocol endpoint `/serviceValidate` with a TLS certificate matching the hostname.
3. Use a test identity provider/user store, never production credentials.
4. Configure CAS logout/SLO delivery to the exact service URL handled by the client filter.
5. Define login role/tenant mappings for `alice` and `bob`.
6. If the CAS Server emits attributes, consume them only through a compatible CAS 3 validator and trust policy.
7. Keep ticket values **redacted** across CAS, proxy, and app logs.

### 14.2. Happy-Path CAS Login

- Unauthenticated browser `GET /reports`.
- Spring redirects to CAS `/login?service=<encoded exact callback>`.
- CAS authenticates and redirects the browser back to the callback with a fresh ST.
- Spring's CAS filter calls `/serviceValidate` with the right CAS host and `service`.
- CAS returns XML success; local `UserDetailsService` returns an enabled user + roles.
- Spring creates `SecurityContext`/session; browser lands on `/reports` and gets 200.
- Subsequent browser reloads of `/reports` must use the local session, **without re-validating the ST**.

### 14.3. Single-Use ST and Wrong Service

- Replay an already-validated ST to the callback: CAS returns `INVALID_TICKET`; no new session is created.
- Take an ST issued for `portal` and validate it claiming another app's `service`: CAS returns `INVALID_SERVICE`.
- **Immediately after the wrong-service validation**, retry the same ST with the right service: still `INVALID_TICKET` if CAS consumed the ticket.
- Submit fake/expired/malformed tickets: reject; never fall back to trusting a username.
- Fail `/serviceValidate` via network error or invalid cert: fail closed, creating no `Authentication`.
- Never log `ticket` in browser history/Referrer, ingress access logs, or APM.

### 14.4. CAS Logout / SLO E2E

1. Log into Portal via CAS, open DevTools, and note a safe `sessionRef`.
2. Also log into a second CAS client if observing global logout behavior.
3. Trigger global logout in the browser via CAS `/logout` (through an intentional UI flow).
4. CAS destroys the TGT and POSTs SLO to registered service URLs; observe only the `logoutRequest` **presence flag**, never logging raw XML.
5. CAS client `SingleSignOutFilter` looks up `ST → HttpSession` and invalidates it.
6. Call `/reports` again using the **old local cookie**. Must be unauthenticated and redirect to login / start a new session.
7. Check the second client similarly; if it stayed logged in, inspect delivery/mapping.
8. Repeat with local `/logout`: the CAS TGT may stay alive and hitting `/reports` again may silently re-login.
9. Repeat with a forged SLO from the Internet / without mTLS: must be rejected before invalidating any local session.
10. Repeat for duplicate SLO, expired sessions, cross-node routing, and CAS outages.

**Never measure SLO just by viewing a "signed out" page**: that page can render even if `HttpSession` was not invalidated. Call a protected API with the **old cookie** and verify the audit event.

## 15. Runnable Java 17: Simulating Single-Use ST, Exact Service, and SLO Mapping

This is a **standalone Java SE 17** program requiring neither Spring nor a real CAS Server. It simulates CAS Server **ticket issuance**, single-use ST validation for the exact service, local admission, and the `ST → session` table used by CAS SLO.

**Mandatory limitations:** `trustedCasSource` in this example is a boolean **representing the outcome of verified mTLS/ingress checks**. Never take that boolean from client-supplied HTTP queries/headers/JSON in production. The program does not parse XML, verify TLS, manage TGT/TGC, run the CAS protocol, or handle distributed sessions; it merely clarifies the logic to verify when wiring Spring Security/CAS.

Create **`CasLoginAndSloDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public final class CasLoginAndSloDemo {

    private static final String SERVICE =
        "https://portal.example.org/login/cas";

    record ServiceTicket(String id, String service, String principal) {}

    record Verified(boolean success, String code, String principal) {}

    static final class FakeCasServer {
        private final Map<String, ServiceTicket> tickets =
            new HashMap<>();

        void issue(String id, String service, String principal) {
            tickets.put(id, new ServiceTicket(id, service, principal));
        }

        Verified validate(String ticketId, String presentedService) {
            // Consume even on failed service match: CAS one-time semantics.
            ServiceTicket issued = tickets.remove(ticketId);
            if (issued == null) {
                return new Verified(false, "INVALID_TICKET", null);
            }
            if (!issued.service().equals(presentedService)) {
                return new Verified(false, "INVALID_SERVICE", null);
            }
            return new Verified(true, "SUCCESS", issued.principal());
        }
    }

    static final class PortalSessions {
        private final Map<String, String> sessions = new HashMap<>();
        private final Map<String, String> ticketToSession =
            new HashMap<>();

        String admit(String serviceTicket, Verified verified,
                     String sessionId, boolean localEnabled) {
            if (!verified.success()) {
                return "DENY_" + verified.code();
            }
            if (!localEnabled) {
                return "DENY_LOCAL_ACCOUNT";
            }
            sessions.put(sessionId, verified.principal());
            ticketToSession.put(serviceTicket, sessionId);
            return "AUTHENTICATED";
        }

        String receiveSlo(boolean trustedCasSource, String serviceTicket) {
            if (!trustedCasSource) {
                return "DENY_SLO_SOURCE";
            }
            if (serviceTicket == null || serviceTicket.isBlank()) {
                return "DENY_SLO_FIELDS";
            }
            String sessionId = ticketToSession.remove(serviceTicket);
            if (sessionId == null) {
                return "NO_MATCH";
            }
            sessions.remove(sessionId);
            return "INVALIDATED";
        }

        String status(String sessionId) {
            return sessions.containsKey(sessionId) ? "ACTIVE" : "ABSENT";
        }
    }

    public static void main(String[] args) {
        FakeCasServer cas = new FakeCasServer();
        PortalSessions portal = new PortalSessions();

        cas.issue("ST-A1", SERVICE, "alice");
        cas.issue("ST-A2", SERVICE, "alice");

        System.out.println("LOGIN_A1=" + portal.admit(
            "ST-A1", cas.validate("ST-A1", SERVICE), "SID-A1", true));
        System.out.println("LOGIN_A2=" + portal.admit(
            "ST-A2", cas.validate("ST-A2", SERVICE), "SID-A2", true));
        System.out.println("SESSION1_BEFORE=" + portal.status("SID-A1"));

        System.out.println("ST_REPLAY=" +
            cas.validate("ST-A1", SERVICE).code());

        cas.issue("ST-WRONG", SERVICE, "bob");
        System.out.println("WRONG_SERVICE=" +
            cas.validate("ST-WRONG",
                "https://portal.example.org/admin").code());
        System.out.println("WRONG_SERVICE_REPLAY=" +
            cas.validate("ST-WRONG", SERVICE).code());

        System.out.println("FORGED_SLO=" +
            portal.receiveSlo(false, "ST-A1"));
        System.out.println("SESSION1_AFTER_FORGERY=" +
            portal.status("SID-A1"));

        System.out.println("REAL_SLO_A1=" +
            portal.receiveSlo(true, "ST-A1"));
        System.out.println("SESSION1_AFTER_SLO=" +
            portal.status("SID-A1"));
        System.out.println("SESSION2_AFTER_SLO_A1=" +
            portal.status("SID-A2"));
        System.out.println("DUPLICATE_SLO_A1=" +
            portal.receiveSlo(true, "ST-A1"));

        cas.issue("ST-BOB", SERVICE, "bob");
        System.out.println("DISABLED_BOB=" + portal.admit(
            "ST-BOB", cas.validate("ST-BOB", SERVICE),
            "SID-BOB", false));
        System.out.println("BOB_SESSION=" + portal.status("SID-BOB"));

        System.out.println("EMPTY_SLO=" + portal.receiveSlo(true, ""));
        System.out.println("REAL_SLO_A2=" +
            portal.receiveSlo(true, "ST-A2"));
        System.out.println("SESSION2_AFTER_SLO=" +
            portal.status("SID-A2"));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac CasLoginAndSloDemo.java
java CasLoginAndSloDemo
```

**Exact stdout**:

```text
LOGIN_A1=AUTHENTICATED
LOGIN_A2=AUTHENTICATED
SESSION1_BEFORE=ACTIVE
ST_REPLAY=INVALID_TICKET
WRONG_SERVICE=INVALID_SERVICE
WRONG_SERVICE_REPLAY=INVALID_TICKET
FORGED_SLO=DENY_SLO_SOURCE
SESSION1_AFTER_FORGERY=ACTIVE
REAL_SLO_A1=INVALIDATED
SESSION1_AFTER_SLO=ABSENT
SESSION2_AFTER_SLO_A1=ACTIVE
DUPLICATE_SLO_A1=NO_MATCH
DISABLED_BOB=DENY_LOCAL_ACCOUNT
BOB_SESSION=ABSENT
EMPTY_SLO=DENY_SLO_FIELDS
REAL_SLO_A2=INVALIDATED
SESSION2_AFTER_SLO=ABSENT
```

### 15.1. Why Is This Output Useful?

- `LOGIN_A1/A2`: the same principal can hold **two local sessions**, so never map solely by username.
- `ST_REPLAY`: a validated ticket is consumed by CAS and cannot be reused.
- `WRONG_SERVICE`: an ST is scoped to one service; a mismatched service is rejected.
- `WRONG_SERVICE_REPLAY`: even a failed validation can consume the ST, so after fixing the service URL, **obtain a new ST** rather than retrying the old one.
- `FORGED_SLO`: an SLO from an untrusted peer must be blocked before touching mappings.
- `REAL_SLO_A1`: ST-A1 invalidates only SID-A1; **SID-A2 stays active** until ST-A2's event arrives.
- `DUPLICATE_SLO`: replaying the same SLO event must be idempotent.
- `DISABLED_BOB`: CAS credential is valid, yet local user status denies admission.
- `EMPTY_SLO`: missing `SessionIndex`/ticket must be rejected rather than guessing by username.
- `REAL_SLO_A2`: completes invalidating the second session when its matching event arrives.

**Never drop the demo class into a production Spring `AuthenticationFilter`.** `HashMap` lives in a single JVM and is not cluster-safe; `trustedCasSource` must come from a real verification layer, and `Verified` must never be supplied by the caller. Production CAS ticket validators require TLS, CAS XML parsing, and full account admission; SLO listeners/filters and shared session stores require E2E QA.

## 16. CAS Login and Service Ticket Test Matrix

| ID | Case | Expected |
| --- | --- | --- |
| L01 | Unauthenticated user opens `/reports`. | Spring redirects to CAS Login with exact service. |
| L02 | User holds valid CAS TGC, no local `JSESSIONID`. | CAS may issue a fresh ST / silent SSO; app still validates ST. |
| L03 | CAS returns valid unused ST for matching service. | `CasAuthenticationProvider` creates `Authentication` after local admission. |
| L04 | Same ST submitted a second time after validation. | `INVALID_TICKET`; no new session created. |
| L05 | Well-formatted yet forged ST. | CAS rejects; never "decode" principal from ST. |
| L06 | Expired ST. | CAS rejects; app fails closed. |
| L07 | ST for service A validated with service B. | `INVALID_SERVICE`; ticket consumed. |
| L08 | After invalid-service attempt, retry right service with old ST. | Fails; acquire a fresh ST. |
| L09 | `service` uses internal HTTP URL instead of public HTTPS. | Reject; fix ingress/`ServiceProperties`. |
| L10 | CAS back-channel cert expired / hostname mismatch. | Validation fails closed; never use trust-all TLS. |
| L11 | CAS Server outage or timeout. | No `Authentication` created; show safe error. |
| L12 | CAS returns XML `authenticationFailure` with HTTP 200. | Deny login. |
| L13 | Valid CAS assertion yet local account disabled. | Deny account admission. |
| L14 | Valid CAS assertion yet `reports:read` role absent. | 403 resource authorization. |
| L15 | CAS username in self-asserted HTTP header. | Ignored; creates no principal. |
| L16 | New CAS Server outside approved endpoints. | Do not auto-trust issuer/URL. |
| L17 | CAS `renew=true` for sensitive service. | Prompts for primary credentials per CAS policy. |
| L18 | Multi-tenant username collision. | Stable identity mapping never assigns wrong local tenant. |
| L19 | Ticket leaks into Nginx access logs. | Security QA FAIL; redact / incident handling. |
| L20 | Validation succeeds yet local session drops `SecurityContext`. | Next request is unauthenticated; fix repository/filter session wiring. |
| L21 | User performs local logout then revisits `/reports` while CAS TGC lives. | Silent re-login may occur — expected UX. |
| L22 | CAS client using `Cas20ServiceTicketValidator` receives a Proxy Ticket. | Reject as not an ST; proxy profile requires separate setup. |
| L23 | Spring filter callback URL mismatches registered `/login/cas`. | Detect login redirect loop / invalid service. |
| L24 | App runs both servlet CAS auth filters and Spring CAS filter. | Detect double validation; single-use ST consumed prematurely. |

## 17. Single Sign-Out Test Matrix

| ID | Case | Expected |
| --- | --- | --- |
| S01 | CAS `/logout` destroys TGT, sends SLO for ST-1. | Portal invalidates session mapped to ST-1. |
| S02 | POST `logoutRequest` from untrusted source. | Blocked before session invalidation. |
| S03 | SLO `SessionIndex=ST-1`, user holds SID-1 and SID-2. | Only SID-1 invalidated; never wipe by username. |
| S04 | Repeated CAS SLO for ST-1. | Idempotent / no match; does not disrupt new sessions. |
| S05 | SLO for `ST-unknown`. | Safe no match, telemetry emitted. |
| S06 | SLO missing `SessionIndex` or malformed XML. | Reject / handled failure; never delete arbitrary sessions. |
| S07 | CAS sends callback over HTTP when only HTTPS is approved. | Block/redirect policy; fix CAS service config. |
| S08 | Callback hits a route other than `/login/cas`. | Detect missing SLO delivery; fix routing. |
| S09 | SLO filter runs after Spring auth filter and POST body already read. | Test fails; fix filter ordering. |
| S10 | Local session already timed out before CAS SLO. | No match / idempotent; no endless 500s. |
| S11 | Listener fails to clean up mapping after session destroy. | Detect stale mapping / memory leak. |
| S12 | SLO hits node B while ticket mapping sits on node A. | Cannot QA PASS if SID-A stays active. |
| S13 | Node A restarts and local mapping is lost. | Fail-safe report / alternative distributed strategy. |
| S14 | Shared store fails during SLO handling. | Alert/retry/revocation; no fake silent success. |
| S15 | Browser/front-channel SLO blocked by third-party cookies. | Never treat front-channel as an absolute guarantee. |
| S16 | CAS Server offline during global logout. | Local session destroyed; CAS SSO may linger—report clearly. |
| S17 | CAS `/logout` succeeds yet client B callback times out. | TGT ended while B's local session remains; matches best-effort semantics. |
| S18 | Local `/logout` while CAS TGC remains. | CAS SSO persists; silent re-login may occur. |
| S19 | CAS logout uses attacker-supplied redirect service URL. | Reject open redirect / enforce allowlist. |
| S20 | CAS SLO POST blocked by Spring CSRF before filter. | Fix narrow routing/order; never disable CSRF app-wide. |
| S21 | CAS SLO XML routed to Spring SAML2 `SingleLogoutFilter`. | Do not use the wrong protocol handler. |
| S22 | CAS SLO callback tries to wipe all sessions for a username. | Reject behavior; map exact `ticket → session`. |
| S23 | `ST → HttpSession` mapping breaks after session fixation rotation. | Detect; use proper listener/session-mapping strategy. |
| S24 | User logs out everywhere across 2 tabs / 2 browsers / multiple nodes. | Each session invalidated by its recorded CAS ticket; verify old cookies. |
| S25 | Authorization status disabled while CAS SSO stays active. | Local checks/revocation deny access immediately per policy. |
| S26 | Oversized SLO request body / malicious XML entity. | Enforce XML parser/body limits; deny safely. |
| S27 | Filter registered twice (`web.xml` + Spring bean). | Detect duplicate SLO / session invalidation. |
| S28 | SLO returns 200 yet session stays authenticated. | Test FAIL: callback acceptance does not equal session invalidation. |

## 18. Observability and Debugging Without Leaking Secrets

### 18.1. Event-Oriented Logging Without Raw Tickets

```text
event=CAS_LOGIN_REDIRECT
trace_ref=login-43
service_ref=portal-cas-login
registration_ref=corporate-cas
result=REDIRECT_TO_CAS

event=CAS_ST_VALIDATION
trace_ref=login-43
ticket_ref=hmac(ST-opaque)
service_ref=portal-cas-login
cas_response=SUCCESS
local_account_state=ACTIVE
authn_result=SUCCESS

event=CAS_SLO_RECEIVED
trace_ref=slo-91
cas_peer_trusted=true
service_ticket_ref=hmac(ST-opaque)
session_mapping=FOUND
session_invalidation=SUCCESS
```

This is a **suggested schema**, not default logging. Use keyed HMAC references only when event correlation is truly needed; avoid raw tickets, session cookies, CAS TGCs, SLO XML, PII, and easily guessed hashes.

### 18.2. Metrics to Monitor

```text
cas_login_redirect_total{service}
cas_ticket_validation_total{service,result}
cas_invalid_service_total{service}
cas_ticket_replay_rejected_total{service}
cas_backchannel_tls_failure_total{service}
cas_local_admission_denied_total{reason}
cas_slo_received_total{service,source_trust}
cas_slo_session_mapping_total{service,result}
cas_slo_invalidation_total{service,result}
cas_slo_callback_latency_seconds{service}
cas_session_revoke_lag_seconds{service}
```

**Never use raw ticket/session/user identifiers as metric labels.** Alert if `invalid_service` spikes after an ingress change, ST validation failures spike after CAS cert rotation, SLO callbacks arrive without invalidating sessions, or untrusted SLO peer attempts increase.

### 18.3. Log Categories by Spring Version

Depending on version, use selectively:
- `org.springframework.security.cas` for CAS auth/provider behavior.
- `org.apereo.cas.client` for CAS client validation/SLO.
- `org.springframework.security.web` for filter chain and session persistence.
- CAS Server logs / service registry for issuance, validation, and SLO delivery.
- Ingress access logs with **redacted** `ticket` query parameters and `logoutRequest` form bodies.
- Spring Session Redis/JDBC metrics for session TTL/revocation.

**Never enable DEBUG/TRACE across the entire production web stack** if it prints raw URL headers/params. CAS `authenticationFailure` logs and Spring `AuthenticationException` messages can contain sensitive inputs; sanitize before storing.

## 19. Troubleshooting Decision Tree

```text
User cannot access protected Portal page
 |
 +-- Browser redirected to CAS /login?   NO
 |      -> Spring authorization/entry point/FilterChain
 |
 YES
 |
 +-- CAS redirected to correct /login/cas with ST?  NO
 |      -> CAS service registry, login, MFA, allowed service URL
 |
 YES
 |
 +-- CasAuthenticationFilter executed?  NO
 |      -> callback matcher, context path, filter order
 |
 YES
 |
 +-- HTTPS /serviceValidate succeeded?  NO
 |      -> CAS DNS/TLS/truststore/network timeout
 |
 YES
 |
 +-- CAS XML authenticationSuccess?  NO
 |      +-- INVALID_TICKET -> expired/reused/fake
 |      +-- INVALID_SERVICE -> service exact URL mismatch
 |      +-- other errors -> CAS config/logs
 |
 YES
 |
 +-- Local account ACTIVE and authorized?  NO
 |      -> UserDetailsService, account/tenant/roles
 |
 YES
 |
 +-- SecurityContext persists across next request?  NO
 |      -> Session/repository/cookie/CSRF/login filter
 |
 YES: CAS Login works
 |
 User signs out at CAS
 |
 +-- CAS SLO notification sent?  NO
 |      -> service SLO configuration, CAS TGT flow
 |
 YES
 |
 +-- Reaches trusted SLO filter before Spring?  NO
 |      -> ingress/mTLS/filter order/POST body/CSRF
 |
 YES
 |
 +-- ST SessionIndex maps local session?  NO
 |      -> ticket->session record, listener, cluster routing/store
 |
 YES
 |
 +-- Old session rejected afterward?  NO
        -> invalidation/storage propagation/security-context cache
```

**One root cause, one layer to fix:** a login redirect loop is not automatically a ticket error; unsynchronized logout is not necessarily the CAS Server's fault; XML success does not prove the user holds business permissions.

## 20. Common Integration Failures

| Failure | Cause | Remediation |
| --- | --- | --- |
| Continuous CAS redirect loop. | Mismatched `service` URL/callback matcher; `SecurityContext` not persisted. | Compare browser URL, `ServiceProperties`, filter, cookies/session. |
| `INVALID_SERVICE`. | CAS issued ST for public HTTPS, app validated with internal HTTP or different path/query. | Fix exact public service identity/ingress; obtain a fresh ST. |
| `INVALID_TICKET`. | ST expired, already validated, double-filtered, or forged. | Trace single-use lifecycle; never retry the old ST. |
| CAS returns XML failure yet app creates a session. | Custom integration checked only HTTP 200. | Use CAS `TicketValidator` and handle failure branches properly. |
| `CasAuthenticationFilter` never runs. | Filter order / URL mismatch. | Map exact `/login/cas`; inspect `SecurityFilterChain`. |
| SAML response filter processes CAS ST. | Mixed CAS with SAML2 SP. | Use separate CAS integration. |
| GET login succeeds yet other pages return 401. | `SecurityContextRepository`/session persistence/cookie issue. | Check `HttpSession`, cookie Secure/Path, and context saving. |
| CAS login OK yet wrong `ROLE_ADMIN`. | Overly broad `UserDetails`/attribute mapping. | Enforce least privilege, local account status, and tenant mapping. |
| Immediate re-login after local logout. | CAS TGT/TGC still alive. | Clarify local vs. global logout UX. |
| CAS global logout yet Portal stays accessible. | Missing SLO filter / lost mapping / dropped callback. | Debug delivery, source trust, ST mapping, and old cookie. |
| SLO POST gets 302 to CAS login. | Request intercepted by Spring auth entry point. | Place SLO filter before auth chain; use dedicated callback route. |
| SLO POST gets 403. | CSRF/WAF/ingress block or source trust denial. | Separate real trust denials from matcher defects; narrow policy. |
| SLO POST returns 200 yet session persists. | Mapping not found or wrong session invalidated. | Test `ST → HttpSession`, cluster, and session store. |
| SLO breaks after multi-node deploy. | Static/in-memory map on node A, callback hits B. | Shared mapping / revocation coordinator. |
| SLO kills the wrong new session. | Mapped by username instead of ST, or stale mapping. | Exact `ticket → session`, idempotency. |
| CAS callback has SAML namespace so `Saml2LogoutRequestFilter` was used. | Confused CAS SLO with SAML 2.0 SLO. | Follow CAS client protocol and use the right handler. |
| CAS TLS trust failure. | Wrong CA truststore/hostname/TLS version. | Fix CA/hostname/mTLS; never use trust-all. |
| Client 4.x/Jakarta fails on startup. | Mixed legacy `javax.servlet` Java CAS Client or dependencies. | Pin compatible set; inspect dependency tree. |
| CAS `/p3/serviceValidate` attributes missing. | Using CAS 2 validator or release policy omits attributes. | Use CAS 3-compatible validator and attribute release. |
| SLO XML parser/encoding fails. | Body already consumed, wrong content type, filter order/charset. | Fix filter order, UTF-8, and request limits. |
| Forged SLO request DoS against client. | Public SLO endpoint lacks peer trust; ticket leaked. | mTLS/gateway allowlist, redaction, rate limiting. |

## 21. Anti-Patterns and Why They Are Wrong

1. **"Seeing `ticket=ST-...` means the user is logged in."** Not yet validated with the CAS Server.
2. **"ST is a JWT so we can decode it to read the user."** A CAS ST is an opaque credential.
3. **"If ST had the wrong service, re-validate the same ticket with the right URL."** STs are single-use; even failed validations consume them.
4. **"Spring local session equals CAS TGT."** They are two independent session systems.
5. **"CAS logout guarantees every `HttpSession` is deleted."** SLO is best-effort.
6. **"`SingleSignOutFilter` authenticates the CAS caller over HTTPS."** A server HTTPS cert does not authenticate the inbound caller.
7. **"SLO `SessionIndex` is `JSESSIONID`."** In CAS SLO, it is normally the ST ID used to look up the session.
8. **"SLO contains `samlp:LogoutRequest`, so it must be Spring SAML2 logout."** Different protocol and context.
9. **"Destroy all sessions by username upon receiving one `logoutRequest`."** Wrong scope; enables DoS.
10. **"Testing SLO on a single node is enough."** Back-channel callbacks carry no sticky browser cookies.
11. **"HTTP 200 on SLO proves the session was revoked."** Must verify with the old cookie.
12. **"If the CAS TGC stays alive, local logout failed."** Silent re-login can be valid SSO behavior.
13. **"Pass any query `returnUrl` into CAS `/logout`."** Open redirect; enforce an allowlist.
14. **"Disable CSRF app-wide so CAS logout POST succeeds."** Exposes business endpoints to CSRF; fix filter order/matchers.
15. **"Derive authorities from unchecked usernames/headers."** Must come from local policy + verified assertions.
16. **"Use trust-all TLS to work around validation timeouts."** Abandons server trust; insecure.
17. **"Mapping `ST → Session` in a static `HashMap` is cluster-ready."** Neither distributed nor synchronized.
18. **"Keep legacy `javax.servlet` code in Boot Jakarta."** Incompatible APIs.
19. **"Logging raw tickets in URLs is fine because they are single-use."** Bearer secrets can still be stolen before validation.
20. **"SLO completely replaces local session timeouts and revocation."** Callbacks can be lost.
21. **"Accept an SLO callback as valid CAS if `X-Forwarded-For` claims CAS's IP."** Attackers can spoof headers.
22. **"Use `Cas20ServiceTicketValidator` to accept proxy tickets without policy."** Proxies require dedicated validators and trusted chains.
23. **"Redirecting to `/reports` after logout is good enough UX."** Can immediately auto-login again via CAS TGC.
24. **"Add another CAS client validation filter to be extra sure."** Risks double-validating a single-use ST.
25. **"Upgrade CAS Server / Java Client without running regressions."** Protocol/config changes can break login/SLO.

## 22. Production Acceptance Checklist

1. Spring Security, CAS client, Servlet/Jakarta, and Java versions are supported and locked in the SBOM.
2. CAS Server service registry accepts only exact approved HTTPS service URLs.
3. Spring `CasAuthenticationEntryPoint` points to the trusted CAS login host.
4. `ServiceProperties.service` matches the real `CasAuthenticationFilter` callback.
5. STs are validated with `Cas20ServiceTicketValidator` / appropriate validator over trusted HTTPS.
6. Expired, forged, replayed, and wrong-service STs are rejected, including HTTP 200 XML failures.
7. Raw STs never construct a `Principal`/`Authentication`, and roles never come from HTTP headers.
8. Local account status, tenant, and roles are checked independently of CAS login success.
9. `SecurityContext` persists in `HttpSession` across the proper lifecycle with `Secure`/`HttpOnly` cookies and `SameSite` policy.
10. Local login/logout enforce session fixation protection and CSRF for browser actions.
11. Local logout and global CAS logout choices are presented with accurate UX.
12. CAS `/logout` enforces a service redirect allowlist with no open redirects.
13. CAS SLO is enabled/permitted on the CAS Server and posts to the exact service URL.
14. `SingleSignOutFilter` runs in proper order before the CAS auth chain and body-reading filters.
15. `SingleSignOutHttpSessionListener` is registered exactly once and cleans up mappings.
16. CAS SLO source trust is enforced via mTLS/gateway controls, never trusting client headers.
17. `SessionIndex` maps the exact service ticket ID; never infer deletion from username/`JSESSIONID`.
18. Duplicate, unknown, and late SLO callbacks are idempotent with reason-code logging.
19. After SLO, old cookies/sessions cannot access protected endpoints.
20. Multi-node `ST → Session` mapping/revocation is designed and verified with real failover tests.
21. CAS outages / lost callbacks have session TTL / revocation fallbacks, alerts, and runbooks.
22. API/session authorization never depends solely on SLO delivery.
23. Query `ticket` and form `logoutRequest` are redacted across CDN, ingress, APM, and app logs.
24. Unit, component, integration, and E2E CAS tests cover negative security paths.
25. CAS service credentials, certs/truststores, and audits are protected by RBAC.
26. Never alter filter behavior or disable validation just to make the login happy path pass.

## 23. Review Questions

1. **How do CAS TGT and ST differ?** — TGT manages the CAS SSO session; ST is a single-use ticket bound to one service.
2. **Are TGC and `JSESSIONID` the same?** — No; the CAS SSO cookie is separate from the local app session cookie.
3. **What does `CasAuthenticationEntryPoint` do?** — Redirects the browser to CAS login with the service URL.
4. **What does `CasAuthenticationFilter` do?** — Captures the ST at `/login/cas` and invokes `AuthenticationManager`.
5. **Where does `CasAuthenticationProvider` obtain identity?** — From the CAS `TicketValidator` after verifying the ST, combined with local user mapping.
6. **Why can an ST not be validated twice?** — CAS consumes the ST on the first validation attempt per protocol.
7. **What error does a wrong `service` produce?** — `INVALID_SERVICE`, and the ticket is normally consumed too.
8. **Does CAS XML success automatically grant `reports:read`?** — No; local account/authority policy still governs access.
9. **Does local logout destroy the CAS TGT?** — Not by default.
10. **Does CAS global logout immediately delete every local session?** — Not guaranteed; SLO delivery is best-effort.
11. **Where must `SingleSignOutFilter` run?** — Before CAS authentication processing so it sees both tickets and logout callbacks.
12. **What is `SingleSignOutHttpSessionListener` used for?** — Cleaning up ticket/session mappings when a session is destroyed.
13. **What does CAS SLO `SessionIndex` contain?** — Typically the service ticket ID to look up the right local session.
14. **Should all sessions be deleted by `NameID`/username?** — No, unless executing a separate authorized revoke-all workflow.
15. **Why can SLO hitting another node fail?** — The local `ST → session` mapping is absent on that node.
16. **How do you prove SLO genuinely terminated a session?** — Call a protected API with the old cookie and verify it is no longer authenticated.
17. **Why is mTLS/ingress trust critical for SLO?** — CAS SLO XML may lack a trustworthy signature, so sender verification prevents forged logouts.
18. **How does CAS `/serviceValidate` differ from `/proxyValidate`?** — `/serviceValidate` handles STs only; `/proxyValidate` serves profiles accepting PTs and proxy chains.
19. **Why never log an ST?** — An ST is a bearer credential even though it is single-use.
20. **What does comprehensive QA require?** — Accurate CAS Login/ST validation, local authorization/sessions, local/global logout, SLO ticket-to-session mapping, security tests, and multi-node verification.

## References

- [Spring Security 7 — CAS Authentication, Service Ticket and Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Spring Security — Project Modules, spring-security-cas.jar](https://docs.spring.io/spring-security/reference/modules.html)
- [Apereo CAS — CAS Protocol Specification: login, /serviceValidate, ST one-time, SLO](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Apereo CAS — Logout and Single Sign-Out (best-effort, front/back channel)](https://apereo.github.io/cas/development/installation/Logout-Single-Signout.html)
- [Apereo Java CAS Client — README, SingleSignOutFilter and listener](https://github.com/apereo/java-cas-client/blob/master/README.md)
- [Maven Central — Apereo CAS Client Core versions](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client-core)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)