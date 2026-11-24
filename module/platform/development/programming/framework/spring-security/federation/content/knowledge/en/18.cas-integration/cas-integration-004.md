# CasAuthenticationProvider and Choosing a TicketValidator in Spring Security CAS

**Central Authentication Service (CAS)** is a single sign-on (SSO) protocol in which the **CAS Server** authenticates users and issues a **service ticket (ST)** for a **service** application to validate before granting login. In **Spring Security – Federation**, the component connecting the CAS protocol to the application's authentication system is **`CasAuthenticationProvider`**. However, the provider does not call arbitrary CAS endpoints on its own: it requires a specific **`TicketValidator`** from the **Apereo Java CAS Client** to verify the ticket with the CAS Server.

Choosing a validator is not simply picking the newest class name. You must answer: **what kind of ticket does the service receive? Does the server support CAS 2.0 or CAS 3.0 validation? Are user attributes needed? Are proxy tickets and proxy-chain delegation permitted?** You must also properly configure the **service URL, TLS, renew policy, local account/authorities, session lifecycle, and replay testing**.

**Lesson objective:** understand the pipeline `CasAuthenticationEntryPoint -> CasAuthenticationFilter -> AuthenticationManager -> CasAuthenticationProvider -> TicketValidator`, choose the right `Cas20ServiceTicketValidator`, `Cas30ServiceTicketValidator`, or proxy validator when required, apply it in a Spring Security application, and identify common pitfalls without weakening CAS trust boundaries.

> **Core principle:** for a web application that only needs CAS login and does not accept proxy tickets, choose a **service-ticket validator** compatible with the CAS protocol published by the server. **Never configure `acceptAnyProxy=true` as a workaround for login errors**; it alters the trust boundary and opens up delegated authentication surface.

## 1. CAS Login Flow and the Provider's Position

A Spring Boot Servlet application using CAS typically involves four roles:

| Role | Component | Function |
| --- | --- | --- |
| User | Browser | Navigates to the app and CAS Server, and returns with a `ticket`. |
| CAS Server | e.g., `https://sso.example.org/cas` | Authenticates users, issues ST/PT, and performs single-use validation at the validation endpoint. |
| CAS Service / Spring application | e.g., `https://portal.example.org` | Receives `/login/cas?ticket=ST-...` callback and creates an app session after verification. |
| Local security / authorization | `UserDetailsService`, `GrantedAuthority`, `SecurityContext` | Binds the CAS-authenticated identity to the application's own account, lock status, roles, and permissions. |

### 1.1. Detailed Sequence Diagram

~~~text
 Browser                Spring Security Portal                  CAS Server
   |                           |                                    |
   | GET /reports              |                                    |
   |-------------------------->|                                    |
   |              no Authentication yet                             |
   |                           | CasAuthenticationEntryPoint        |
   |<--- 302 /cas/login?service=https://portal.../login/cas --------|
   |---------------------------------------------------------------->|
   |                           |                                login/MFA
   |<--- 302 https://portal.example.org/login/cas?ticket=ST-... ----|
   |                           |                                    |
   | GET /login/cas?ticket=ST- |                                    |
   |-------------------------->|                                    |
   |                           | CasAuthenticationFilter            |
   |                           | creates ticket Authentication      |
   |                           |       |                            |
   |                           | ProviderManager                    |
   |                           |       |                            |
   |                           | CasAuthenticationProvider          |
   |                           |       |                            |
   |                           | TicketValidator.validate(ST,service)|
   |                           |---------- HTTPS /p3/serviceValidate ->|
   |                           |<--------- Assertion / failure ------|
   |                           |                                    |
   |                           | Map CAS principal to local user    |
   |                           | Check local account status         |
   |                           | Create CasAuthenticationToken      |
   |                           | Save SecurityContext/session       |
   |<--------------------------|                                    |
   | 302 /reports              |                                    |
~~~

The diagram illustrates **CAS 3.0 service-ticket validation**; if using CAS 2.0, the validation endpoint may be `/serviceValidate`. Actual endpoint names and certificates must match the CAS Server version and configuration.

**Distinguish the two HTTP channels:**

- **Browser -> CAS**: `/login?service=...` so the user can authenticate.
- **Spring backend -> CAS**: `/serviceValidate?service=...&ticket=...` or `/p3/serviceValidate?...` to validate the ticket; this is a **server-to-server HTTPS channel**, never relying on the browser claiming it logged in.

`CasAuthenticationProvider` cannot accept an unverified ST merely because it begins with `ST-`. **A ticket is an opaque credential**, not a JWT from which the service can decode an identity on its own.

## 2. CAS Ticket Types and Identifiers

| Entity | Abbreviation | Role | Do Not Confuse With |
| --- | --- | --- | --- |
| **Ticket Granting Ticket** | TGT | CAS Server stores SSO authority after user authentication; browser typically holds a corresponding cookie. | Single-use ST sent to the application; never pass a TGT as ticket input to an SP. |
| **Service Ticket** | ST | Issued specifically for one `service` value; validated by the service with the CAS Server, typically **only once**. | PT or application session. |
| **Proxy Granting Ticket** | PGT | Authorizes an authenticated service to obtain **proxy tickets** to call another service on behalf of the user per CAS protocol. | Initial login ST. |
| **Proxy Granting Ticket IOU** | PGTIOU | Correlation value linking the validation response and the callback delivering the PGT. | The actual secret PGT. |
| **Proxy Ticket** | PT | CAS credential used when delegating through one or more proxy services; requires proxy-chain verification. | Regular ST validated via `serviceValidate`. |
| **Spring `HttpSession`** | `JSESSIONID` | Post-authentication application session maintained per Spring Security policy. | CAS tickets or CAS Server SSO cookies. |

### 2.1. An ST Is Bound to the Service URL

When the CAS Server issues:

~~~text
ticket = ST-abcdef...
service = https://portal.example.org/login/cas
~~~

the `service` at validation time must satisfy the CAS Server's matching rules against the recorded URL. If the validator sends:

~~~text
service = http://portal.internal:8080/login/cas
~~~

instead of the public HTTPS URL used when issuing the ticket, validation can fail with **`INVALID_SERVICE`**. This is a very common failure mode when running behind a reverse proxy or load balancer.

**Correct:** `ServiceProperties.service` must be the **exact public callback URL** matching `CasAuthenticationFilter`, the CAS service registry, and the login redirect URL. **Never build the service URL from request headers not verified by a trusted proxy.**

### 2.2. Single-Use ST, Not a Reusable Access Token

The CAS protocol specifies that a service ticket is valid for **one validation attempt**; afterwards the ticket is invalidated, even if that validation attempt fails. Refreshing `/login/cas?ticket=ST-old` or resending the same ST to the endpoint can trigger `INVALID_TICKET`, which is normal anti-replay behavior.

Some CAS proxy/stateless designs may use **`StatelessTicketCache`** to reuse a **previously validated result** across requests under a specific policy; do not confuse this cache with the CAS Server allowing a fresh ST to pass validation multiple times. When extending to stateless mode, carefully review revocation, TTL, service scope, and replay risks.

## 3. What `CasAuthenticationProvider` Does—and Does Not Do

**`org.springframework.security.cas.authentication.CasAuthenticationProvider`** is a Spring Security `AuthenticationProvider` declared in **`spring-security-cas`**. It handles authenticating a CAS ticket submitted by the filter to `AuthenticationManager`.

### 3.1. Primary Collaborators

| Component / Property | Role |
| --- | --- |
| `ServiceProperties` | Holds the **service callback URL**, `sendRenew`, `authenticateAllArtifacts`, and ticket/service parameter names. |
| `TicketValidator` | Sends ticket + service to the right CAS validation endpoint, parses the response, and returns `org.apereo.cas.client.validation.Assertion` or throws an error. |
| `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` | Maps the verified CAS principal/attributes to an application user and authorities. |
| `UserDetailsService` (depending on version/API) | Simpler lookup of a local user by CAS principal; checks lifecycle and internal permissions. |
| `UserDetailsChecker` | Allows checking user status where supported; must be tested for `LOCKED`/`DISABLED` in practice. |
| `GrantedAuthoritiesMapper` | Normalizes authorities after user lookup; does not replace resource-level authorization checks. |
| Internal provider `key` | Identifies the provider that created `CasAuthenticationToken` for supporting already-authenticated tokens; **not a CAS server signing key or user password**. |
| `StatelessTicketCache` (if enabled) | Caches validated ticket results for stateless/proxy flows per policy. |

Once `TicketValidator` returns a valid **Assertion**, the provider invokes the user-details service, checks the account, and produces a **`CasAuthenticationToken`** for Spring Security to store in **`SecurityContext`**.

**Important:** `CasAuthenticationProvider` **does not decide on its own** whether a user can approve invoices, which tenant they belong to, or whether they can enter a locked local account. That logic belongs in `UserDetailsService`/custom policy and the authorization layer. If an ST is valid yet the local account is `DISABLED`, **admission must be denied**.

### 3.2. API Flow from Spring's Perspective

~~~text
CasAuthenticationFilter
  -> AuthenticationManager.authenticate(ticketAuthentication)
     -> CasAuthenticationProvider.supports(authenticationType)
        -> TicketValidator.validate(ticket, service)
           -> CAS Server /serviceValidate or /p3/serviceValidate
              -> Assertion (principal, attributes, proxy chain, ...)
        -> loadUserDetails / userDetailsChecker
        -> authorities mapping
        -> CasAuthenticationToken (authenticated)
  -> SecurityContextRepository / HttpSession
~~~

A note on versioned docs: many long-standing CAS reference sections describe `UsernamePasswordAuthenticationToken` with `CAS_STATEFUL_IDENTIFIER`; newer Javadocs for `CasAuthenticationFilter` and the provider also reference **`CasServiceTicketAuthenticationToken`**. Always **check your exact API version** (Spring Security 6.x/7.x) rather than instantiating a token class from an older guide and assuming every release uses the same one. Rely on the framework's filter and manager to avoid constructing tokens manually.

### 3.3. Provider Key Is Not an Authentication Secret

`CasAuthenticationProvider#setKey(String)` requires a stable string identifying the provider. Never confuse it with a SAML/JWT signing key, an OIDC `client_secret`, or a CAS password. It cannot replace:

- Validating the **service ticket** via the CAS Server over TLS.
- CAS Server replay protection.
- Session cookie / CSRF protection.
- `UserDetails` checks and authorization.

When running multiple instances, provider configuration must be consistent; never change the key arbitrarily between requests of the same session type. Never put a key in code to "protect" accounts while skipping ST validation.

## 4. `TicketValidator`: Interface and Origin

In the Apereo Java CAS Client, the interface:

~~~java
org.apereo.cas.client.validation.TicketValidator
~~~

defines the ticket validation operation. Conceptually, the core call is:

~~~java
Assertion assertion = ticketValidator.validate(ticket, serviceUrl);
~~~

The resulting assertion holds the CAS `Principal` and may include attributes, authentication date/proxy chain, and protocol/version-specific data. When the CAS Server rejects an ST/PT or returns an invalid response, the validator throws an exception; Spring must treat it as an **Authentication failure**, never fabricating a fallback principal.

Common implementations:

- `Cas20ServiceTicketValidator` — validates service tickets via **CAS 2.0 `/serviceValidate`**.
- `Cas30ServiceTicketValidator` — uses **CAS 3.0 `/p3/serviceValidate`**, suitable when extended user attributes are needed in the response.
- `Cas20ProxyTicketValidator` — handles **CAS 2.0 `/proxyValidate`**, capable of accepting **proxy tickets** and validating proxy chains.
- `Cas30ProxyTicketValidator` — uses **CAS 3.0 `/p3/proxyValidate`**, supporting proxy tickets and CAS 3.0 attributes.

**These validator classes live in `org.apereo.cas.client.validation`**, not `org.springframework.security.cas.authentication`. Spring invokes them; the Apereo CAS client implements the ticket validation protocol.

### 4.1. Choose by Protocol and Requirement, Not Spring Major Version

| Application Context | Appropriate Validator | Expected CAS Endpoint | Notes |
| --- | --- | --- | --- |
| Web app receiving regular **ST**, server supports CAS 2 validation. | `Cas20ServiceTicketValidator` | `/serviceValidate` | Conservative choice when only the principal is needed, CAS 2 compatible. |
| Web app receiving ST, server supports CAS 3 and app needs **attributes**. | `Cas30ServiceTicketValidator` | `/p3/serviceValidate` | Appropriate when using user/organization attributes released by CAS via CAS 3. |
| Service must validate **PT** via CAS 2 proxy protocol. | `Cas20ProxyTicketValidator` | `/proxyValidate` | Must define an explicit **proxy trust policy**. |
| Service must validate PT via CAS 3 proxy protocol and needs attributes. | `Cas30ProxyTicketValidator` | `/p3/proxyValidate` | Do not pick simply because the server is CAS 3; requires a real proxy use case. |
| CAS Server supports both CAS 2 and CAS 3. | Choose by contract, attributes, and ticket type. | Per validator. | **Server product version != protocol endpoint**; inspect actual release configuration. |
| Project does not accept proxies but IdP/caller sends a PT. | **Reject PT** via service-ticket validator. | `/serviceValidate` or `/p3/serviceValidate` | Do not "fall back to a proxy validator" just to suppress errors. |

**Do not choose `Cas20ProxyTicketValidator` merely because it has CAS20 in its name and you want to "support everything."** Proxy authentication is a delegated trust relationship; expanding from ST to PT is a significant security boundary change.

### 4.2. How Do CAS 2.0 and 3.0 Differ?

**CAS 2.0** introduced `/serviceValidate` and `/proxyValidate` with XML responses for validating service/proxy tickets. **CAS 3.0** extended attribute delivery for **authentication/user attributes**, typically via `/p3/serviceValidate` and `/p3/proxyValidate`.

Example CAS 2 response (abbreviated):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>user-42</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Example CAS 3 response (abbreviated, illustrative):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>user-42</cas:user>
    <cas:attributes>
      <cas:employeeId>emp-742</cas:employeeId>
      <cas:department>Finance</cas:department>
      <cas:affiliation>staff</cas:affiliation>
      <cas:affiliation>auditor</cas:affiliation>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**The XML snippets above illustrate structure only, not responses you can feed directly into Spring to authenticate.** The CAS client must receive them over a ticket validation connection to a trusted CAS Server. Fields like `department` or `affiliation` can be multi-valued; the application must not assume every attribute is a single `String`. More importantly, **receiving an attribute does not mean the application should trust it to grant admin roles**.

### 4.3. Do Not Confuse the Service Validation Endpoint with the CAS Login URL

CAS login is typically:

~~~text
https://sso.example.org/cas/login?service=...
~~~

CAS 2 validation:

~~~text
https://sso.example.org/cas/serviceValidate?service=...&ticket=...
~~~

CAS 3 validation:

~~~text
https://sso.example.org/cas/p3/serviceValidate?service=...&ticket=...
~~~

You normally pass the **CAS server base URL** `https://sso.example.org/cas` to the constructor of `Cas20ServiceTicketValidator` or `Cas30ServiceTicketValidator`; the validator appends the protocol endpoint automatically. **Never pass `.../login` into the constructor**, and never append `/serviceValidate` twice.

A modern CAS server may provide CAS 2/3 alongside OIDC/SAML; **never use a CAS `TicketValidator` to validate an OIDC ID Token or a SAMLResponse**. Those are different protocols with different validators.

## 5. `ServiceProperties`: Binding the Ticket to the Right Application

`ServiceProperties` is the contract between the Spring CAS client and the CAS Server regarding the **service URL**.

~~~java
ServiceProperties properties = new ServiceProperties();
properties.setService("https://portal.example.org/login/cas");
properties.setSendRenew(false);
~~~

This is a **Java snippet inside a Spring Security project**, requiring `import org.springframework.security.cas.ServiceProperties;`.

| Property | Meaning | Risk If Misconfigured |
| --- | --- | --- |
| `service` | Callback service URL sent during redirect to CAS and during ticket validation. | `INVALID_SERVICE`/ticket mismatch, or service identity confusion. |
| `sendRenew` | When enabled, sends `renew` per CAS to force explicit authentication instead of reusing an SSO session. | If mismatched between login and validation, fails or misses freshness guarantees. |
| `authenticateAllArtifacts` | Allows handling tickets at additional URLs; requires dynamically determining the service URL. | Widens ticket acceptance surface, risks wrong service boundaries or stateless cache issues. |
| `artifactParameter` | Ticket parameter name, defaulting usually to `ticket`. | Filter misses the ticket if mismatched. |
| `serviceParameter` | Service parameter name, defaulting to `service`. | CAS login does not receive the right callback. |

### 5.1. Notes on `sendRenew=true`

The CAS protocol defines the `renew` parameter; it instructs CAS to accept only tickets issued after **presenting primary credentials** rather than silently logging in via an existing SSO session. This is a **reauthentication policy**, not automatically **MFA** or phishing resistance. If business rules require MFA, establish a separate assurance/context contract with the CAS Server and verify the result rather than relying solely on `renew=true`.

When immediate reauthentication on every app entry is unnecessary, `sendRenew=false` allows leveraging CAS SSO. In sensitive applications, weigh enabling `renew` with awareness of UX and CAS Server policy, and design step-up flows for sensitive operations instead of applying it indiscriminately to every page.

### 5.2. Configuration Behind a Reverse Proxy

If the portal runs in a container at `http://portal-pod:8080` while users visit `https://portal.example.org`, the **CAS service URL must be the public HTTPS URL** accepted and registered by the CAS Server. Never build the URL from an untrusted `X-Forwarded-Host` header, as an attacker can supply a bogus service URL.

Verify:

1. The reverse proxy supplies forwarded headers over a trusted link and strips headers injected directly by clients.
2. Spring Boot/Spring Security resolves the external scheme/host/path accurately.
3. The CAS Server **service registry** allowlists `https://portal.example.org/login/cas` accurately.
4. Browser redirects and backend validation use the exact same service URL for which the ticket was issued.
5. Never embed `JSESSIONID`, sensitive query parameters, or arbitrary return URLs inside `service` unless explicitly managed.

**Never disable service-matching validation** to work around proxy/HTTPS misconfigurations. Binding a ticket to its service is a key defense against forwarding a ticket from app A to app B.

## 6. Choosing `ServiceTicketValidator` When Only Web Login Is Needed

In most Spring MVC applications:

~~~text
Browser -> CAS Server /login
        -> ST issued for https://portal.example.org/login/cas
        -> Spring CasAuthenticationFilter
        -> CasAuthenticationProvider
        -> Cas20ServiceTicketValidator or Cas30ServiceTicketValidator
        -> CAS Server validates ticket/service
        -> local admission and session
~~~

**Choose a service ticket validator** when the application **does not need to receive tickets via a proxy service**. If you need user attributes for profile mapping, choose **`Cas30ServiceTicketValidator`** when the CAS 3 validation endpoint is supported.

Spring bean example:

~~~java
@Bean
TicketValidator ticketValidator() {
    return new Cas30ServiceTicketValidator("https://sso.example.org/cas");
}
~~~

Required imports:

~~~java
import org.apereo.cas.client.validation.TicketValidator;
import org.apereo.cas.client.validation.Cas30ServiceTicketValidator;
~~~

This is a bean in a Spring Configuration class, not a standalone Java SE program.

**Do not choose `Cas30ServiceTicketValidator` just because the CAS Server is labeled "v7/v8"**; verify that the server actually enables **CAS protocol v3 endpoints**, attribute release, and Java CAS Client compatibility. A CAS Server across multiple product releases may still expose the CAS 2 `/serviceValidate` endpoint.

### 6.1. Controlling Attributes

If CAS 3 returns `attributes.roles=["analyst"]`, never do:

~~~text
CAS attributes.roles -> ROLE_ADMIN or ROLE_ + arbitraryString
~~~

without an allowlist and tenant mapping. The CAS Server is responsible for **authenticating identity**; the app must still check local `LOCKED/DISABLED` status, approved tenant/permissions, and return 403 for unauthorized actions. Attributes used for display vs. attributes used for authorization have different provenance requirements.

## 7. Choosing `ProxyTicketValidator` When True Delegation Is Required

CAS proxy authentication lets Service A (having authenticated the user) call Service B **on behalf of** the user. Service B receives a **proxy ticket (PT)** rather than a browser-login ST.

~~~text
Browser --> Service A ------ ST validate ------> CAS
                |      pgtUrl / PGTIOU
                |<----- PGT callback / PGT ------- CAS
                |
                | request PT for Service B
                +-------------------------------> CAS /proxy
                |<------------------------------- PT-for-B
                |
                +------ HTTP request + PT ------> Service B
                                                  |
                                       Cas20/30ProxyTicketValidator
                                                  |
                              CAS /proxyValidate or /p3/proxyValidate
                                                  |
                                       checks service=Service-B, proxies
                                                  |
                                         authorize / deny
~~~

This is the CAS proxy flow, **not SAML `ProxyRestriction` or OAuth Token Exchange**. The CAS Server issues a PT scoped to a target service; Service B must validate the PT and **verify the proxy chain** to confirm only authorized intermediaries delegated the request.

### 7.1. Proxy Validators and Trusted Proxy Lists

Proxy validators expose related settings:

- `acceptAnyProxy`: if `true`, any proxy chain is accepted within the validator's scope; **must not be used by default in production**.
- `allowedProxyChains`: specifies permitted proxy chains when supported by the CAS client/server and defined by enterprise policy.
- `proxyCallbackUrl`/`proxyGrantingTicketStorage`: used to request and receive a **PGT** when the app needs to **mint PTs for downstream services**.
- `proxyReceptorUrl` on `CasAuthenticationFilter`: endpoint receiving the PGT callback; must match the URL called by the CAS Server.

**Safe choice:** if Service B has no proxy business case, **do not switch to a proxy validator**. If PT support is required, define an explicit allowlist based on verified **proxy identities/URLs**, and test that a proxy chain containing an unknown hop fails. Setting `acceptAnyProxy=true` widens who is allowed to impersonate users.

### 7.2. Two Different Meanings of "Proxy"

1. **An app proxying to a backend**: needs a **PGT** to request PTs; configures an HTTPS callback, storage, and the appropriate `Cas20/30ProxyTicketValidator`.
2. **A backend app receiving a PT**: needs a proxy validator to verify the PT and the traversed proxy list; the backend does not necessarily need a PGT itself.

Do not conflate these two cases and assume every app must register a `pgtUrl`. Implement PGT/callbacks only when actually issuing proxy tickets.

### 7.3. Protecting the PGT Callback Strictly

The CAS Server calls `pgtUrl` over HTTPS, delivering `pgtId` and `pgtIou` for correlation. Ensure:

- Exact callback URL, validated certificates/TLS, and no redirects to external domains.
- Store PGTs in an access-controlled store, and never log raw callback URLs/queries containing PGTs.
- Correlate PGT with PGTIOU from the validation response **for the exact matching transaction**.
- Clean up PGTs/expired tickets with TTLs, quotas, revocation, and rotation procedures.
- Never reuse a PGT indiscriminately to request PTs for backends outside an allowlist.

Enabling proxy mode is a **trust-boundary change**; it requires a separate security review beyond configuring `CasAuthenticationProvider`.

## 8. Spring Boot Servlet Sample: Provider + Validator + Filter + Entry Point

The example below targets **Spring Security 6.x, Java 17+** and illustrates **CAS 3.0 service tickets** without proxying. This configuration is part of a **Spring Boot application** with a real CAS Server, Spring Security 6.x, and a compatible Java CAS Client. Because CAS config depends on versions, compile and test against locked BOM/dependencies; **do not treat this snippet as a complete project without CAS service registration and a user repository**.

### 8.1. Module-Level Dependencies

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
  <dependency>
    <groupId>org.apereo.cas.client</groupId>
    <artifactId>cas-client-core</artifactId>
  </dependency>
</dependencies>
~~~

**This is a Maven `pom.xml` dependency fragment**, not a complete POM. Versions must be managed via Spring Boot dependency management and/or a compatible Apereo CAS client version; never copy an arbitrary version. Recent Spring Security/CAS Client combinations have Java/Jakarta API shifts; verify Java 17+, `jakarta.servlet`, and exact modules during upgrades.

### 8.2. Java Configuration

File `src/main/java/example/cas/CasSecurityConfig.java`:

~~~java
package example.cas;

import org.apereo.cas.client.validation.Cas30ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
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

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService("https://portal.example.org/login/cas");
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    TicketValidator ticketValidator() {
        // CAS protocol 3.0; use Cas20ServiceTicketValidator
        // if the server only supports CAS 2.0 service validation.
        return new Cas30ServiceTicketValidator(
                "https://sso.example.org/cas");
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties serviceProperties,
            TicketValidator ticketValidator,
            UserDetailsService userDetailsService) {

        CasAuthenticationProvider provider =
                new CasAuthenticationProvider();
        provider.setServiceProperties(serviceProperties);
        provider.setTicketValidator(ticketValidator);
        provider.setUserDetailsService(userDetailsService);
        provider.setKey("portal-cas-provider");
        return provider;
    }

    @Bean
    CasAuthenticationEntryPoint casEntryPoint(
            ServiceProperties serviceProperties) {

        CasAuthenticationEntryPoint entryPoint =
                new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl("https://sso.example.org/cas/login");
        entryPoint.setServiceProperties(serviceProperties);
        return entryPoint;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            CasAuthenticationProvider provider,
            CasAuthenticationEntryPoint entryPoint) throws Exception {

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setAuthenticationManager(new ProviderManager(provider));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                    entryPoint))
            .addFilterAt(filter, CasAuthenticationFilter.class);

        return http.build();
    }
}
~~~

The setters in this configuration reflect **CAS provider/entry point APIs** documented in Spring Security, though you must verify that **`CasAuthenticationFilter` is placed in the right filter chain** for your running version. This is a service-ticket flow example and **does not yet** include a `UserDetailsService` bean, account DB, controllers, CAS Server registration, TLS certificates, or integration tests; those must be supplied by the real project. Without a `UserDetailsService`, the application will fail bean injection at startup.

**Security note:** the provider uses `UserDetailsService` to look up the local account from the CAS-verified principal. Ensure `UserDetails` enforces `disabled/locked` status and tenant-scoped authorities; verify with integration tests. Systems with complex ID/attribute mapping may need `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` instead of simple username lookup.

### 8.3. When CAS 2.0 Is Needed Instead of CAS 3.0

Swap the validator bean:

~~~java
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;

@Bean
TicketValidator ticketValidator() {
    return new Cas20ServiceTicketValidator(
            "https://sso.example.org/cas");
}
~~~

This is a **replacement snippet**; never register two beans of the same type without `@Qualifier` disambiguation; in the configuration above, there is **only one validator** for the provider. CAS 2 service validation does not mean CAS 3 attribute APIs will return attributes as desired; if attributes are required, use the matching endpoint and response profile.

### 8.4. When `ProxyTicketValidator` Is Needed

When there is a genuine requirement to accept PTs:

~~~java
import org.apereo.cas.client.validation.Cas30ProxyTicketValidator;

@Bean
TicketValidator ticketValidator() {
    Cas30ProxyTicketValidator validator =
            new Cas30ProxyTicketValidator("https://sso.example.org/cas");
    // Configure an explicit proxy-chain allowlist per your
    // Apereo Java CAS Client version and proxy contract.
    // Never enable acceptAnyProxy in production.
    return validator;
}
~~~

This is a **configuration snippet illustrating class selection**, **not a complete production proxy setup**. You must configure allowed proxy chains, PGT handling if applicable, session/stateless service details, and end-to-end tests. Never "swap the validator" while skipping proxy-chain protection, exact service URLs, and backend authorities.

### 8.5. Filter URL and Proxies May Differ

`CasAuthenticationFilter` normally watches `/login/cas` (configurable via `filterProcessesUrl`). When handling only browser STs, the **service URL** typically points to this endpoint. When `ServiceProperties.authenticateAllArtifacts=true` is used to receive tickets at other URLs, the filter may need **`ServiceAuthenticationDetailsSource`** to compute the dynamic service URL per request. Turning on the flag without configuring the details source and validator accurately can cause ticket mismatches or unintended ticket acceptance on wrong endpoints.

URL strings must align with the CAS **service registry** and the ticket issuer. Never accept a `service` from a browser query string in place of the server-configured URL.

## 9. `TicketValidator` and Customizing HTTPS / Trust Policies

### 9.1. HTTPS Must Genuinely Verify the CAS Server

`TicketValidator` sends the ticket credential to the CAS Server; if the application suffers a MITM attack or connects to a rogue CAS Server, an attacker can capture the ST and return a forged identity. Therefore:

- Configure only the **HTTPS URL** of the real CAS Server.
- Use the Java truststore/PKIX with valid certificates and strict hostname verification.
- Never install `TrustAll`/`NoopHostnameVerifier` or an `SSLContext` that skips certificate validation just to "fix SSL errors."
- Restrict outbound egress and DNS per architecture, ensuring the CAS base URL is never derived from user input.
- Configure proper connect/read timeouts and **fail closed** on timeouts or 5xx responses.
- Keep secrets and tickets out of logs, metrics, query traces, and error pages.

Even if the browser CAS login leg uses HTTPS, the **server-to-server validation leg** must also be protected. Never pull an identity straight from `ticket` or browser headers if HTTPS validation fails.

### 9.2. CAS Service Registry on Server and Client Must Stay Synchronized

A CAS Server normally maintains a **service registry** allowing only registered callbacks/services. This protects against issuing tickets to unknown services and open redirects. The SP must align:

~~~text
CAS Server /login service:
  https://portal.example.org/login/cas

CasAuthenticationEntryPoint:
  same ServiceProperties.service

CasAuthenticationProvider -> TicketValidator:
  same validated service URL

CAS Server service registry:
  permits exactly intended service identity
~~~

A CAS registry may use URL patterns or regexes to cover environments; keep them **as specific as possible** to avoid accidentally permitting attacker-controlled subdomains or redirect endpoints. Never simply tweak `service` in the URL until login succeeds; verify why a given service identifier is correct.

### 9.3. Never Grant Default Privileges Directly from `TicketValidator`

The CAS validation result tells you the CAS-authenticated `principal` and the attributes released by CAS. In Spring Security, **authorization** still belongs to local authorities and method/resource policies.

For example, a CAS principal `user-42` might carry attribute `roles=admin` from an external directory while the local app account is locked: **deny admission**, and never synthesize `ROLE_ADMIN` solely because the XML response contains the word "admin." If no local record exists and JIT provisioning is not approved, deny by default. When multiple tenants or IdP sources sit behind CAS, identity mapping needs namespace/issuer or identity-source scoping rather than matching by bare email alone.

## 10. `UserDetailsService`, Assertion, and Local Permissions

### 10.1. Two Options for Loading Users

**One:** `UserDetailsService` can look up `username` from CAS `Assertion.getPrincipal().getName()` (via wrapper/framework path), appropriate when the CAS principal is an agreed stable key with a 1-to-1 local account DB mapping.

**Two:** `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` lets you inspect the full **CAS Assertion** and attributes returned by the validator. This fits scenarios requiring mapping CAS subjects to local accounts, tenants, multi-valued attributes, or complex admission policies. Still, never use arbitrary groups to grant admin; enforce an allowlist and local entitlements.

In both cases:

- The CAS principal is a **post-validation result**; never read it from a `username` request parameter.
- If the account is `LOCKED`/`DISABLED`, reject authentication and do not create an authenticated `SecurityContext`.
- If the local status DB experiences an outage, **fail closed** when an admission decision cannot be made.
- Any mapped `GrantedAuthority` is merely an input; backends must still enforce **resource/tenant/ownership** checks on every API.

### 10.2. `CasAuthenticationToken` and `Assertion`

After authentication, Spring Security places a `CasAuthenticationToken` into `SecurityContext`. This token represents a **successful authentication result** and may retain the `Assertion` from the CAS client.

Distinguish:

| Spring / CAS Object | Origin | Used For |
| --- | --- | --- |
| `CasServiceTicketAuthenticationToken` or version-specific CAS request token | Created by filter from CAS ticket callback. | Input to `AuthenticationManager`; **does not prove login succeeded**. |
| `Assertion` (`org.apereo.cas.client.validation.Assertion`) | `TicketValidator` after CAS server validation. | CAS principal and attributes/proxy details released by CAS. |
| `CasAuthenticationToken` | `CasAuthenticationProvider` after user loading/checks. | Authenticated `Authentication`; holds principal and authorities. |
| `SecurityContext` | Maintained by Spring Security. | Identity/authorization state for the current request. |
| Local account record | Approved DB or service. | Status, tenant, roles/entitlements, revocation. |

Never retain raw CAS tickets as long-lived credentials in the app, and never serialize `Assertion`/PGT into public JSON or logs. If exposing `/me`, return only minimal fields (such as local user ID and relevant permissions), never `ticket` or validation URLs.

## 11. Standalone Java 17: Selecting a Validator by Policy

The standalone program below tests **validator selection rules**, distinguishing CAS2/CAS3, ST/PT, attributes, and proxy allowlists. It **imports neither Spring nor Apereo CAS**, and does not actually send tickets or verify signatures; the `Choice` record simply describes the validator name and endpoint so it runs on **JDK 17**.

File `CasValidatorSelectionDemo.java`:

~~~java
import java.util.Set;

public class CasValidatorSelectionDemo {

    enum Protocol { CAS2, CAS3 }
    enum TicketKind { SERVICE, PROXY }

    record Requirement(
            Protocol protocol,
            TicketKind ticketKind,
            boolean requireUserAttributes,
            String proxyIdentity) {}

    record Choice(String validatorName, String endpoint,
                  boolean allowed) {}

    static Choice choose(Requirement req, Set<String> allowedProxies) {
        if (req.requireUserAttributes()
                && req.protocol() != Protocol.CAS3) {
            return new Choice("NONE", "NONE", false);
        }

        if (req.ticketKind() == TicketKind.SERVICE) {
            if (req.protocol() == Protocol.CAS3) {
                return new Choice("Cas30ServiceTicketValidator",
                                  "/p3/serviceValidate", true);
            }
            return new Choice("Cas20ServiceTicketValidator",
                              "/serviceValidate", true);
        }

        // PROXY: allow only if an explicit proxy identity exists,
        // has been verified, and is on the allowlist.
        if (req.proxyIdentity() == null
                || !allowedProxies.contains(req.proxyIdentity())) {
            return new Choice("NONE", "NONE", false);
        }

        if (req.protocol() == Protocol.CAS3) {
            return new Choice("Cas30ProxyTicketValidator",
                              "/p3/proxyValidate", true);
        }
        return new Choice("Cas20ProxyTicketValidator",
                          "/proxyValidate", true);
    }

    public static void main(String[] args) {
        Set<String> trustedProxies =
                Set.of("https://gateway.example.org/pgt");

        Choice service2 = choose(new Requirement(
                Protocol.CAS2, TicketKind.SERVICE, false, null),
                trustedProxies);
        System.out.println(service2.validatorName()
                           + " " + service2.endpoint());

        Choice service3 = choose(new Requirement(
                Protocol.CAS3, TicketKind.SERVICE, true, null),
                trustedProxies);
        System.out.println(service3.validatorName()
                           + " " + service3.endpoint());

        Choice unsupported = choose(new Requirement(
                Protocol.CAS2, TicketKind.SERVICE, true, null),
                trustedProxies);
        System.out.println(unsupported.allowed());

        Choice proxy3 = choose(new Requirement(
                Protocol.CAS3, TicketKind.PROXY, true,
                "https://gateway.example.org/pgt"),
                trustedProxies);
        System.out.println(proxy3.validatorName()
                           + " " + proxy3.endpoint());

        Choice untrusted = choose(new Requirement(
                Protocol.CAS3, TicketKind.PROXY, true,
                "https://untrusted.example.org/pgt"),
                trustedProxies);
        System.out.println(untrusted.allowed());

        Choice proxy2 = choose(new Requirement(
                Protocol.CAS2, TicketKind.PROXY, false,
                "https://gateway.example.org/pgt"),
                trustedProxies);
        System.out.println(proxy2.validatorName()
                           + " " + proxy2.endpoint());
    }
}
~~~

Compile and run:

~~~bash
javac CasValidatorSelectionDemo.java
java CasValidatorSelectionDemo
~~~

**Exact stdout:**

~~~text
Cas20ServiceTicketValidator /serviceValidate
Cas30ServiceTicketValidator /p3/serviceValidate
false
Cas30ProxyTicketValidator /p3/proxyValidate
false
Cas20ProxyTicketValidator /proxyValidate
~~~

Explanation:

1. CAS2 service receiving ST, no attributes needed -> **Cas20ServiceTicketValidator**.
2. CAS3 receiving ST and attributes needed -> **Cas30ServiceTicketValidator**.
3. CAS2 when policy requires CAS3 attributes -> **not satisfied**; upgrade the endpoint contract or change the data source.
4. CAS3 receiving PT from an allowlisted proxy -> **Cas30ProxyTicketValidator** can be considered.
5. PT from an unknown proxy -> deny; never "open `acceptAnyProxy` to try it out."
6. CAS2 receiving PT from an allowed proxy -> **Cas20ProxyTicketValidator**, with chain trust configured in the real CAS client.

**Important limitation:** `proxyIdentity` in this demo is a parameter assumed **already authenticated by the validator/server**. In production, never take a proxy URL from a browser-supplied HTTP header and put it in an allowlist; the CAS Client must extract and verify the proxy chain from the CAS validation response. This demo performs no Java networking, issues no service tickets/PGTs, and tests no TLS; it solely illustrates deployment selection logic.

## 12. Validator Selection Decision Flow: Practical Checklist

~~~text
Does the app receive CAS tickets by contract?
  |
  +-- No: use the actual protocol's validator (OIDC/SAML), not CAS.
  |
  +-- Yes:
         |
         +-- Receives SERVICE tickets only?
         |     |
         |     +-- CAS2 endpoint /serviceValidate
         |     |      => Cas20ServiceTicketValidator
         |     |
         |     +-- CAS3 endpoint /p3/serviceValidate
         |            => Cas30ServiceTicketValidator
         |
         +-- Must genuinely receive PROXY tickets?
               |
               +-- No proxy allowlist contract
               |      => reject PT / do not use a proxy validator
               |
               +-- Has proxy-chain policy, target service, and TLS
                      |
                      +-- CAS2 /proxyValidate
                      |      => Cas20ProxyTicketValidator
                      |
                      +-- CAS3 /p3/proxyValidate
                             => Cas30ProxyTicketValidator
~~~

Before finalizing, document which endpoints the CAS Server enables, how the service ID is registered, which attributes are needed, and whether proxy delegation is required.

### 12.1. Connectivity Verification Steps

1. Configure the **HTTPS CAS base URL** and verify the CA certificate/hostname from the host running Spring.
2. Check the CAS Server service registry for the exact **public `/login/cas` callback**.
3. Verify the filter matches `/login/cas?ticket=...` and the Spring auth manager includes `CasAuthenticationProvider`.
4. Confirm the CAS Server supports `/serviceValidate` or `/p3/serviceValidate` (for service validation).
5. Verify `UserDetailsService`/account mapping and role policies with real principals from CAS.
6. If using proxying, define Service B, PGT callback, proxy-chain allowlist, and the appropriate `/proxyValidate` setup.
7. Run integration tests for first-time ST, replay, wrong service, invalid ticket, outages, attributes, and local account status.

**Never paste real tickets into browser DevTools screenshots or shared log systems** as proof of verification. In test environments, use dedicated test identities/tickets and redact sensitive values when recording results.

## 13. Common Integration Errors and Diagnostics

| Symptom | Common Cause | Safe Verification |
| --- | --- | --- |
| Redirect to CAS then infinite loop back. | Filter misses `/login/cas`, provider not wired, service URL mismatch, or session not persisted. | Inspect `CasAuthenticationFilter`, `CasAuthenticationEntryPoint`, filter chain, callback, and error handler. |
| CAS returns `INVALID_SERVICE`. | `ServiceProperties.service` differs from issuance `service`, or registry rejects it. | Compare exact public URL, forwarded headers, context path, and proxy. |
| CAS returns `INVALID_TICKET`. | Ticket used, expired, wrong CAS server, or multiple validation calls sent. | Log correlation and cause; never retry the same ST as a fallback. |
| CAS 3 attributes are missing. | Using CAS 2 `/serviceValidate`, CAS Server not releasing attrs, or mapper not reading them. | Check CAS 3 endpoint, attribute release policy, and Assertion attributes. |
| Backend sends a PT to `serviceValidate` and fails. | Service validator does not accept proxy tickets. | If PT use case is valid, switch to proxy protocol with allowlist; never disable validation. |
| `ClassNotFoundException: Cas30ServiceTicketValidator`. | Missing `cas-client-core` or incompatible dependency version. | Inspect dependency tree / Jakarta compatibility; do not guess class names. |
| `NoSuchMethodError` on startup. | Version mismatch between Spring Security CAS module and Apereo CAS client. | Use dependency management/BOM and pin tested versions. |
| Java `SSLHandshakeException`. | Invalid CAS cert/hostname/truststore. | Fix PKIX/truststore; never enable trust-all. |
| CAS principal is right yet app returns 403. | Missing local role/entitlement/tenant. | Inspect `UserDetailsService`, granted authorities, and resource policy. |
| `LOCKED` local account still logs in. | Account checker/mapping not properly wired into CAS provider. | Test CAS auth path with `UserDetailsChecker`/admission policy. |
| Proxy ticket from unknown service still validates. | `acceptAnyProxy=true`, unrestricted proxy chain. | Deny and define proper `allowedProxyChains`. |
| CAS endpoint returns XML/JSON but validator fails to parse. | Wrong protocol validator, media type, or response profile. | Compare `/serviceValidate` vs `/p3/serviceValidate` and CAS Client version. |
| Callback on node B lacks session from node A. | Local-only session store without sticky/failover support. | Use Spring Session / shared store and test multi-node. |
| Browser auto-SSOs again right after local logout. | CAS TGT/SSO cookie still active on CAS Server. | Distinguish app logout from CAS single logout; configure SLO separately. |
| Validation timeout still results in login success. | Fallback grants access when CAS is unreachable. | **Fail closed**; ask user to retry, never create a session on network errors. |
| Service URL uses `http://pod:8080` behind reverse proxy. | Misconfigured forwarded-header trust or hard-coded internal service. | Use the external HTTPS service registered in CAS and verify proxy trust. |
| One ST validates successfully multiple times. | CAS server or custom validator violates single-use, or cache misused. | Test atomic one-time ticket invalidation and inspect cache/stateless paths. |

### 13.1. Reading `AuthenticationException` Errors Properly

CAS validators may throw the CAS client's `TicketValidationException`; the Spring adapter/provider translates errors into the authentication failure path per API/version. Never return full exceptions containing tickets, internal URLs, or stack traces to the browser. Suggested internal classification:

~~~text
CAS_TICKET_INVALID
CAS_SERVICE_MISMATCH
CAS_VALIDATOR_NETWORK_FAILURE
CAS_VALIDATOR_RESPONSE_FORMAT_ERROR
CAS_PROXY_NOT_ALLOWED
CAS_LOCAL_ACCOUNT_LOCKED
CAS_LOCAL_ACCOUNT_NOT_PROVISIONED
CAS_AUTHENTICATION_SUCCESS
~~~

These names are **application-suggested reason codes**, not an official Spring Security exception list. Use metrics like `cas_validation_latency`, `cas_ticket_replay_rejected`, `cas_provider_success_total` and audits with correlation IDs and redacted tickets for analysis.

## 14. Testing a Provider and Each Validator

| Test Case | Expected Result |
| --- | --- |
| Fresh ST, right CAS server + service URL, `ACTIVE` local user. | Validator succeeds; provider builds `Authentication` with valid authorities. |
| ST reused after successful validation. | CAS Server rejects with `INVALID_TICKET`. |
| ST submitted for validation after a previous failed attempt. | CAS Server rejects the old ticket per single-use protocol. |
| ST issued for service A sent to service B. | Validation fails with `INVALID_SERVICE` or equivalent. |
| Expired ST. | Rejected; no Spring session created. |
| Untrusted CAS Server / invalid TLS. | Fails closed; never trust-all. |
| CAS endpoint returns error / times out. | No authenticated `Authentication` created. |
| CAS 2 service ticket with `Cas20ServiceTicketValidator`. | Receives principal when endpoint/contract are valid. |
| CAS 3 ST with `Cas30ServiceTicketValidator`. | Receives principal and attributes released by the CAS Server. |
| CAS 3 ST with `Cas20` validator. | Verify support and attribute limits; do not assume all CAS 3 attributes appear. |
| PT sent to `/serviceValidate`. | Rejected by service-only validation. |
| PT from allowlisted proxy via proxy validator. | Validates when service and proxy-chain policy match. |
| PT from unknown proxy. | Rejected; never flip `acceptAnyProxy` to `true`. |
| Proxy chain contains an unapproved extra hop. | Rejected. |
| PGT callback fails to correlate PGTIOU. | No proxy ticket issued/used. |
| `ServiceProperties.sendRenew=true` while user only has SSO cookie. | CAS requires/enforces fresh explicit login per renew policy. |
| CAS user exists but local account is `DISABLED`. | Admission denied; no authenticated session created. |
| CAS user has admin group but is unapproved locally. | `ROLE_ADMIN` not granted automatically. |
| Multi-node callback and session store. | No lost sessions or node-dependent discrepancies. |
| Reverse proxy external HTTPS vs. internal HTTP. | Uses exact public service URL in both redirect and validation. |
| CAS server releases multi-valued attributes. | Mapper handles types properly and enforces allowlist. |
| Local logout while CAS TGT stays alive. | Never assume CAS SSO was cleared; test SLO separately. |

**Java unit tests** for validator selection only check class-selection policy, not CAS login. You need integration tests against a test CAS Server or controlled environment: issue real STs, run callbacks, verify validation network calls, user mapping, auth sessions, and replay. In particular, test **wrong service** and **proxy chain**; both directly guard linked authentication boundaries.

## 15. CAS and SAML/OIDC: Never Mix Validators

Within the same federation ecosystem, one CAS Server may act as a CAS protocol server, SAML IdP, OIDC OP, or broker. However, the protocols do not share credentials or validators:

| Protocol Used by App | Browser Callback | Appropriate Auth Components |
| --- | --- | --- |
| **CAS** | `?ticket=ST-...` at service callback. | `CasAuthenticationFilter` + `CasAuthenticationProvider` + **CAS `TicketValidator`**. |
| **SAML 2.0 Web SSO** | `SAMLResponse` (HTTP-POST/Artifact). | `Saml2WebSsoAuthenticationFilter` + OpenSAML provider/validators and `RelyingPartyRegistration`. |
| **OIDC** | `?code=...&state=...` then ID Token. | `oauth2Login()`, OIDC decoder/validation, `ClientRegistration`. |
| **OAuth Resource Server** | `Authorization: Bearer <access_token>`. | JWT decoder or opaque-token introspector, audience/scope/permission policy. |

If a project is considering migrating from CAS to OIDC/SAML, never try to "reuse `TicketValidator`" to validate a JWT or XML Assertion. Design a proper migration covering issuer/subject mapping, logout, sessions, and entitlements, protecting each protocol at every hop.

## 16. Serious Mistakes to Avoid

1. **Choosing a validator by Spring version rather than CAS validation endpoint.** Wrong: you must match CAS2/CAS3 protocol and ticket type.
2. **Letting `TicketValidator` take any CAS URL from a browser query.** Wrong: creates SSRF and trust confusion.
3. **Using `Cas20ProxyTicketValidator` for every service.** Wrong: may open PT acceptance beyond business requirements.
4. **Enabling `acceptAnyProxy=true` just to "make login pass."** Wrong: bypasses proxy trust-chain verification.
5. **Failing to match the validation service URL with the ticket-issuing service.** Wrong: weakens protection against cross-app ticket forwarding.
6. **Using an internal HTTP URL behind a reverse proxy.** Wrong: causes `INVALID_SERVICE` and risks mis-issued tickets.
7. **Retrying the same ST multiple times after validation fails.** Wrong: STs normally allow only one validation attempt.
8. **Silencing `SSLHandshakeException` with TrustAll.** Wrong: credentials and identities can be forged.
9. **Using `Assertion.getPrincipal().getAttributes()` to grant all roles blindly.** Wrong: requires local policy and allowlisting.
10. **Allowing a `LOCKED` local account to log in simply because CAS succeeded.** Wrong: admission and authentication are separate gates.
11. **Confusing `sendRenew` with MFA.** Wrong: reauthentication does not prove authenticator type or assurance level.
12. **Mistaking `provider.key` for a ticket-signing secret.** Wrong: it does not replace validation or TLS.
13. **Confusing `CasAuthenticationToken` with an unverified ticket request.** Wrong: distinguish input tokens from authenticated results.
14. **Enabling `authenticateAllArtifacts` unconditionally.** Wrong: opens more URLs to tickets and requires safe service details.
15. **Logging raw tickets in logs/tracing.** Wrong: leaks one-time credentials and service metadata.
16. **Confusing PGTIOU with the actual PGT.** Wrong: PGTIOU only correlates the callback.
17. **Allowing PGT callbacks over HTTP or unverified connections.** Wrong: the callback is sensitive and requires TLS and trust checks.
18. **Using a CAS `TicketValidator` to handle OIDC ID Tokens or `SAMLResponse`s.** Wrong: they are distinct protocols.
19. **Assuming local logout logs out the CAS Server and every other service.** Wrong: sessions, TGTs, and SLO require separate policies.
20. **Testing only the happy-path login.** Wrong: wrong service, untrusted-proxy PTs, replay, CAS outages, and local account locks matter more.

## 17. Production Deployment Decision Checklist

1. Does the app use the **CAS protocol** itself, or OIDC/SAML served by the CAS Server? Is the corresponding callback defined?
2. Are the CAS Server base URL and login URL configured with HTTPS, proper truststore/hostname checks, and the service registry?
3. Do browser callback `/login/cas`, `ServiceProperties.service`, and ticket validation `service` share the same public URL?
4. Which of `/serviceValidate`, `/p3/serviceValidate`, `/proxyValidate`, or `/p3/proxyValidate` does the CAS Server support?
5. Does the service genuinely need **user attributes** from CAS 3, or only the principal?
6. Does the service accept only STs, or also PTs? If PTs, are approved proxy chains and untrusted-proxy tests in place?
7. If PGTs are needed, are `pgtUrl`/proxy receptor/storage secured, PGTIOU correlated, and TTL cleanup active?
8. Have the Spring Security version and `spring-security-cas`/CAS client dependencies been tested for compatibility?
9. Is `CasAuthenticationFilter` in the right filter chain, and does `AuthenticationManager` include the provider?
10. Does `CasAuthenticationProvider` have the right `serviceProperties`, `ticketValidator`, `key`, and user-details service?
11. Do local `LOCKED/DISABLED` account flags and entitlements/tenants block CAS-authenticated users when required?
12. Is `sendRenew` used per authentication freshness policy without being mistaken for MFA?
13. Are tickets validated over TLS, rejecting replay and wrong services, with raw credentials excluded from logs?
14. Have CAS Server failures and timeouts been tested to fail closed?
15. In multi-node deployments, are session stores, trust config, and service URLs consistent across nodes?
16. Are local logout vs. CAS Single Logout, session revocation, and browser SSO cookie policies defined?
17. Does observability capture correlation, reason codes, and latency without leaking tickets, PGTs, or user data?
18. Do integration tests cover STs, CAS 3 attributes, PT/proxy chains, local locks, failover, and reverse proxies?

## 18. Knowledge Self-Check

1. **Which framework does `CasAuthenticationProvider` belong to?** — Spring Security's CAS module; it integrates ticket validation into `AuthenticationManager`.
2. **Which library does `TicketValidator` belong to?** — Apereo Java CAS Client, package `org.apereo.cas.client.validation`.
3. **Where is a CAS service ticket delivered?** — To the service callback `/login/cas?ticket=...`, after which the Spring backend validates it with the CAS Server.
4. **Is a ticket that was validated once still valid to validate again?** — No, per the single-use ST rule of the CAS protocol.
5. **Which endpoint does `Cas20ServiceTicketValidator` call?** — CAS 2 `/serviceValidate`.
6. **What do you choose to retrieve CAS 3 user attributes?** — Use `Cas30ServiceTicketValidator` with supported CAS 3 endpoints and attribute release.
7. **When is `Cas30ProxyTicketValidator` needed?** — When a service has a business case to accept CAS 3 PTs and defines a proxy trust policy.
8. **Is `acceptAnyProxy=true` a safe production setting?** — Not by default; it opens an unrestricted proxy trust chain.
9. **Is PGTIOU the same as PGT?** — No; PGTIOU correlates the validation response with the PGT callback.
10. **What must `ServiceProperties.service` match?** — The public callback URL used when CAS issued the ticket and the `service` URL sent during validation.
11. **Does `sendRenew` guarantee MFA?** — No; it controls reauthentication requirements, not authenticator assurance level.
12. **Does successful CAS validation grant admin permissions?** — No; local accounts, entitlements, and tenants must still be verified.
13. **If the CAS Server is unreachable, may login fall back to succeeding?** — No, when validation is required; it must fail closed.
14. **Why can't a CAS validator be used for a `SAMLResponse`?** — Because they are different protocols and authentication artifacts.
15. **After local logout, can a user SSO back in immediately?** — Yes, if the session/TGT at the CAS Server is still alive; a CAS SLO policy is needed if centralized logout is desired.
16. **Which tests matter besides the happy path?** — Ticket replay, wrong service, TLS failures, untrusted-proxy PTs, locked accounts, outages, and multi-node behavior.

## References

- [Spring Security — CAS Authentication (reference, Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Spring Security API — CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html)
- [Spring Security API — CasAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html)
- [Spring Security API — CasAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationEntryPoint.html)
- [Spring Security API — ServiceProperties](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html)
- [Apereo CAS — CAS Protocol Specification: ST, serviceValidate, proxyValidate, CAS3 endpoints, PGT/PGTIOU](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Apereo CAS — CAS Protocol versions and service attributes](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html)
- [Apereo Java CAS Client — implementations and validation filters](https://github.com/apereo/java-cas-client/blob/master/README.md)
