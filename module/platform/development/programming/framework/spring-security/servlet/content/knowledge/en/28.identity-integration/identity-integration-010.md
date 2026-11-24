# CAS, JAAS, and Kerberos: Integration Scope, Dependencies, and Prerequisites

**Module:** Spring Security – Servlet  
**Parent topic:** Identity integration

## 1. Three Names Often Mentioned Together That Do Not Share the Same Architectural Layer

When bringing Spring Security Servlet into an enterprise system with existing sign-in mechanisms, you may encounter **CAS**, **JAAS**, or **Kerberos**. All three relate to identity authentication, yet they are not three interchangeable alternatives:

- **CAS (Central Authentication Service):** a **Single Sign-On (SSO) protocol/system**. The application redirects to the CAS Server, receives a **service ticket**, and asks CAS to validate the ticket.
- **JAAS (Java Authentication and Authorization Service):** an **authentication API/framework inside the Java platform**, comprising `LoginContext`, `LoginModule`, `Subject`, and `Principal`. JAAS is a Java integration hook for login mechanisms; JAAS itself does not prescribe an SSO provider, ticket endpoint, or browser login flow.
- **Kerberos:** a **network authentication protocol built on tickets and cryptographic keys**. On enterprise intranets, web apps often use **SPNEGO / HTTP Negotiate** so browsers send Kerberos proof to the server. Kerberos requires KDC/realm/SPN/keytab infrastructure and matching client prerequisites.

Notably, **JAAS can use Kerberos** via `Krb5LoginModule` in suitable contexts; that is an **integration API → authentication mechanism** relationship, not JAAS competing with Kerberos. CAS can likewise be configured to use LDAP, Kerberos, or another identity store **on the CAS Server side**, while the Java application sees only CAS authentication results.

### 1.1. Quick Selection Table

| Criterion | CAS | JAAS | Kerberos/SPNEGO |
| --- | --- | --- | --- |
| Primary role | SSO for web applications | Java authentication API/bridge | Network and ticket-based authentication protocol |
| Who verifies credentials? | CAS Server and its identity store | Configured `LoginModule` | KDC issues tickets; recipient validates tickets |
| Typical browser flow | Redirect → CAS login → service ticket → validate | No single universal browser flow | 401 `Negotiate` → browser sends SPNEGO token |
| Works standalone with only a Maven dependency? | No; requires CAS Server/matching config | Local demo possible; production needs real `LoginModule` and identity source | No; requires realm/KDC/SPN/keytab, DNS/clock/client support |
| Fitting scenarios | Organization already runs CAS SSO or CAS-based legacy systems | Java system with existing `LoginModule`/`Subject` or JAAS bridge requirement | Intranet using Active Directory/Kerberos and enterprise browsers |
| Application permissions granted automatically? | No | No | No |
| Replaces Spring Security authorization? | No | No | No |
| Spring ecosystem dependencies | Version-dependent CAS integration, dedicated module/legacy adapter | JAAS classes in JDK; version-dependent Spring adapter | JDK GSS/Krb5; SPNEGO/Spring Kerberos adapter external to core or at gateway |

**Solution selection rule:** If a modern CAS server supports **OIDC or SAML 2.0** and the system does not mandate the CAS ticket protocol, consider integrating via `oauth2Login()` or `saml2Login()` supported by your Spring Security version. Do not add a legacy CAS adapter merely because the organization colloquially calls every enterprise login "CAS."

## 2. CAS: Ticket-Based SSO, Not an OAuth2 Access Token

### 2.1. Components and Login Flow

In the **CAS protocol**, the web application is the **service/client**, and the CAS Server manages SSO. A simplified flow:

~~~text
Browser           Servlet Application          CAS Server
   | GET /reports        |                      |
   |-------------------->|                      |
   | 302 /login?service=...                     |
   |<--------------------|                      |
   | GET CAS /login?service=...                 |
   |------------------------------------------->|
   |                user login / CAS SSO session|
   | 302 to service URL?ticket=ST-...           |
   |<-------------------------------------------|
   | GET service?ticket=ST-...                  |
   |-------------------->|                      |
   |                     | validate ticket ST   |
   |                     |--------------------->|
   |                     | principal/attributes |
   |                     |<---------------------|
   |    App session      |                      |
   |<--------------------|                      |
~~~

Terminology:

- **TGT (Ticket Granting Ticket):** used for the SSO session on the CAS Server; ordinary service applications **must not** accept a TGT as their own authorization proof.
- **ST (Service Ticket):** short-lived, typically single-use ticket bound to the target service. The application must send the ticket to the **CAS Server** for validation before constructing `Authentication`.
- **Service URL:** callback/address permitted by CAS; must match the service registration contract. Wrong hostname, scheme, port, or context path readily triggers redirect loops/validation failures.
- **Principal + attributes:** details returned by CAS upon validation; the application must still map groups/roles per business authorization policies.

**Do not confuse:** a CAS service ticket is not a bearer access token for an OAuth2 Resource Server; never configure `oauth2ResourceServer().jwt()` to "validate CAS tickets."

### 2.2. When Is CAS Appropriate?

Use the CAS protocol directly when:

1. The enterprise already operates a CAS Server and service catalog, and mandates that applications use the CAS ticket flow.
2. The application is a **Servlet** web browser app capable of login redirects and session management.
3. Operations controls HTTPS, public service URLs, load balancers, CAS trust, logout, and attribute release rules.
4. An adapter **compatible with the current Java / Spring Security / Servlet versions** exists, or a custom bridge plan has undergone security review.

Do not apply CAS browser redirects by default to pure machine-to-machine APIs; APIs typically need standard tokens/credentials suited to non-interactive clients. An SPA frontend also needs a proper BFF/session or OIDC design rather than holding STs arbitrarily in browser state.

### 2.3. CAS Dependencies and Compatibility

In the older ecosystem there existed artifact **`org.springframework.security:spring-security-cas`** and classes like `CasAuthenticationFilter`, `CasAuthenticationProvider`, `ServiceProperties`, and `Cas20ServiceTicketValidator`. However:

- **CAS is not enabled merely by adding `spring-boot-starter-security`**. The exact module, publisher, and version must be verified in the BOM/repository of the **release being deployed**.
- Do not assume old CAS modules always exist or remain compatible with **Spring Security 6/7, Java 17+, Spring Boot 3, and Jakarta Servlet**. Many online CAS tutorials use pre-Spring-Security-6 config APIs or legacy `javax.servlet`.
- Never add legacy CAS dependencies by trying random versions or forcing dependency conflicts. Verify whether the artifact is maintained, check transitive dependencies, CAS client/protocol versions, and `jakarta.servlet` compatibility.
- If using CAS Server solely as an **OIDC/SAML2 Identity Provider**, the matching web app dependency is `spring-boot-starter-oauth2-client` or the SAML modules, **not** `spring-security-cas`.

**Selection pattern, not a complete `pom.xml`:**

~~~text
Direct CAS ticket protocol:
  Verify a supported CAS module/adapter for your target release.
  Do not assume spring-security-cas is a default Boot 3 dependency.

CAS Server with OIDC:
  spring-boot-starter-oauth2-client
  SecurityFilterChain with oauth2Login(...)
  Matching OIDC issuer/client registration/redirect URI.

CAS Server with SAML 2.0:
  Appropriate Spring Security SAML2 Service Provider module.
  Register SP/IdP metadata, certificates, assertion consumer service.
~~~

### 2.4. Critical CAS Security Conditions

- **Trust ticket validation results only over an HTTPS channel** to the configured CAS Server; never trust a `ticket` parameter sent on the URL by itself.
- **Service tickets must match the service** issued by CAS for this application; never accept a ticket minted for another service to sign in.
- Prevent **open redirects** via un-allowlisted `service` or `returnUrl` parameters; configure callbacks accurately behind reverse proxies.
- Never log tickets into access logs, browser analytics, or error messages; tickets can appear in callback query strings, so enforce careful logging policies.
- Establish authentication and sessions via Spring Security mechanisms, addressing **session fixation protection**, session timeouts, `Secure`/`HttpOnly`/`SameSite` cookies, and CSRF on state-changing forms.
- Distinguish **application logout** from **Single Logout (SLO)** across all of CAS; logging out in one place does not automatically terminate every organizational session.
- Mapping attributes to permissions: use an **allowlist** and check tenant/resource; CAS identity verification does not automatically permit all operations.

## 3. JAAS: Java's Authentication Extension Point

### 3.1. JAAS Objects

JAAS is a JDK API using classes in the **`javax.security.auth.*`** namespace—this remains true on Java 17 and **does not change to `jakarta.security.auth`** merely because Spring Boot 3 uses Jakarta Servlet.

| Component | Responsibility |
| --- | --- |
| `LoginContext` | Coordinates login/logout for a named JAAS configuration. |
| `LoginModule` | Implements a specific authentication mechanism; provides `initialize`, `login`, `commit`, `abort`, `logout`. |
| `CallbackHandler` | Supplies inputs to `LoginModule` such as username, password, or interactive prompts. |
| `Subject` | Holds principals and public/private credentials depending on context and JAAS outcome. |
| `Principal` | Represents an identity or group name; does not equal a Spring authority until mapped. |
| `Configuration` / `login.config` | Selects modules and combinations of `required`, `requisite`, `sufficient`, `optional`. |

With Spring Security, JAAS is **one authentication source** that can plug into `AuthenticationManager`. Spring's JAAS adapter (if supported in your release) converts login/`Subject`/principal results into `Authentication` and `GrantedAuthority`. You still need a principal → authority mapping policy; `Subject` does not automatically make a user `ROLE_ADMIN`.

### 3.2. LoginModule Control Flags

When a configuration combines multiple `LoginModule`s:

- **`REQUIRED`**: module must succeed for overall login to succeed, though subsequent modules still execute.
- **`REQUISITE`**: must succeed; failure typically terminates login early.
- **`SUFFICIENT`**: if it succeeds and no prior REQUIRED module failed, login may complete early.
- **`OPTIONAL`**: does not by itself require success; overall result depends on the other modules and JAAS rules.

Misconfigured flags can allow weak login paths when another module fails. Test **module combinations** and failure branches, not only happy-path sign-ins.

### 3.3. Runnable Pure-JDK Java 17 Example Without Spring

The following example illustrates the exact JAAS lifecycle: configuring a module, providing callbacks, populating `Subject`/principals, and logging out. **Hard-coded credentials are strictly for learning the API—never use them as a real authentication backend.**

Save as **`JaasFlowDemo.java`**:

~~~java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public class JaasFlowDemo {
    public static void main(String[] args) throws LoginException {
        Configuration configuration = new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"training".equals(name)) {
                    return null;
                }
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                        DemoLoginModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of())
                };
            }
        };

        CallbackHandler handler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword("demo-only".toCharArray());
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        LoginContext context =
            new LoginContext("training", null, handler, configuration);

        context.login();
        Subject subject = context.getSubject();
        System.out.println("Login: OK");
        System.out.println(
            "Principals: " + subject.getPrincipals(UserIdentity.class).size());

        context.logout();
        System.out.println(
            "Principals after logout: "
            + subject.getPrincipals(UserIdentity.class).size());
    }

    public static final class UserIdentity implements Principal {
        private final String name;

        public UserIdentity(String name) {
            this.name = name;
        }

        @Override
        public String getName() {
            return name;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof UserIdentity identity
                && name.equals(identity.name);
        }

        @Override
        public int hashCode() {
            return name.hashCode();
        }
    }

    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserIdentity identity;
        private boolean authenticated;

        @Override
        public void initialize(
                Subject subject,
                CallbackHandler handler,
                Map<String, ?> sharedState,
                Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password =
                new PasswordCallback("Password: ", false);
            char[] supplied = null;

            try {
                handler.handle(new Callback[] { name, password });
                supplied = password.getPassword();

                if (!"alice".equals(name.getName())
                        || !Arrays.equals(
                            "demo-only".toCharArray(), supplied)) {
                    throw new FailedLoginException(
                        "Invalid training credentials");
                }

                identity = new UserIdentity(name.getName());
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException error) {
                LoginException exception =
                    new LoginException("Callback failed");
                exception.initCause(error);
                throw exception;
            } finally {
                if (supplied != null) {
                    Arrays.fill(supplied, '\0');
                }
                password.clearPassword();
            }
        }

        @Override
        public boolean commit() {
            if (!authenticated) {
                return false;
            }
            subject.getPrincipals().add(identity);
            return true;
        }

        @Override
        public boolean abort() {
            if (!authenticated) {
                return false;
            }
            return logout();
        }

        @Override
        public boolean logout() {
            if (identity != null) {
                subject.getPrincipals().remove(identity);
            }
            authenticated = false;
            identity = null;
            return true;
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac JaasFlowDemo.java
java JaasFlowDemo
~~~

**Expected stdout:**

~~~text
Login: OK
Principals: 1
Principals after logout: 0
~~~

**Explanation:** the module is instantiated by JAAS via class name, invokes callbacks, verifies mock data, and adds `UserIdentity` to `Subject` in `commit()`; `logout()` removes that principal. This is a **pure JDK example to understand the lifecycle**, with no HTTP session, LDAP, CAS, KDC, password hashing, or Spring Security filters. Never use sample accounts/passwords in real environments.

In real systems, a `LoginModule` must perform trustworthy verification (LDAP/Kerberos/hardware key/internal service), protect credentials, resist brute force, handle errors, and audit. If a module authenticates via Kerberos, never hand-roll Kerberos cryptography in Java.

### 3.4. When Does JAAS Integrate with Spring Security Servlet?

Use a JAAS bridge when the enterprise has an **existing operated and verified `LoginModule`** or a security/infrastructure requirement that exposes authentication results solely as a `Subject`. Spring Security's adapter (such as classes around `JaasAuthenticationProvider` and `AuthorityGranter` in supporting releases) can connect that outcome to `Authentication`.

Verify **existence and support status of the adapter** in your target release; never assume every old Spring Security 6/7 module remains present or auto-configured by a Boot starter. For new web apps using standard OIDC/SAML2, direct integration with modern protocols is usually cleaner than writing custom `LoginModule`s.

Logical flow, **not a standalone Java class**:

~~~text
HTTP request
  -> Spring Security AuthenticationFilter / AuthenticationManager
  -> Appropriate JAAS authentication provider/adapter
  -> LoginContext.login()
  -> LoginModule(s) + Subject(principals)
  -> map approved Principals to GrantedAuthority (ROLE_...)
  -> Authentication stored in SecurityContext
  -> authorization for URL, method, tenant, resource
~~~

For example, an authenticated principal named `engineering` may be mapped by **internal policy** to `ROLE_ENGINEER`. Never map every `Principal.getName()` directly into a privileged authority by string concatenation, and never trust self-created principals from client-controlled requests.

## 4. Kerberos and HTTP SPNEGO

### 4.1. What Components Does Kerberos Need?

Kerberos is an authentication mechanism using tickets and a **Key Distribution Center (KDC)**; in enterprise environments, Microsoft Active Directory often provides the KDC. Essential concepts:

- **Realm:** Kerberos domain, e.g., `EXAMPLE.COM`.
- **KDC:** server issuing/granting tickets per the protocol.
- **Client principal:** identifier of a user or service.
- **SPN (Service Principal Name):** identifier of a service, typically shaped like `HTTP/app.example.com@EXAMPLE.COM` for HTTP.
- **Keytab:** file containing secret keys for the service principal so the server can authenticate/decrypt or accept Kerberos tickets per the applicable mechanism.
- **TGT:** user's Ticket Granting Ticket used to request service tickets; ordinary web apps do not receive TGTs as HTTP credentials.
- **Service ticket:** ticket scoped to a specific SPN; browsers can present it to a website via SPNEGO/Negotiate.
- **SPNEGO:** negotiation mechanism allowing HTTP clients/servers to exchange `Negotiate` tokens for Kerberos authentication under matching conditions.

The protocol differs from CAS: browsers are not redirected to a CAS login page. Properly configured browsers obtain tickets automatically from the domain login environment and send them when the server challenges with Negotiate.

### 4.2. SPNEGO Flow in HTTP

~~~text
Domain-joined browser     HTTP app / reverse proxy      KDC
        | GET /intranet             |                   |
        |-------------------------->|                   |
        | 401 + WWW-Authenticate: Negotiate             |
        |<--------------------------|                   |
        |    obtain service ticket for HTTP/app...      |
        |----------------------------------------------->|
        |<-----------------------------------------------|
        | Authorization: Negotiate <SPNEGO token>       |
        |-------------------------->|                   |
        |                           | verify ticket     |
        |                           | using service key |
        |                           v                   |
        |                         principal             |
        |                           |                   |
        |         Spring Authentication / authorities   |
        |<--------------------------|                   |
~~~

Illustrative challenge/response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Then the client sends:

~~~http
GET /intranet HTTP/1.1
Host: app.example.com
Authorization: Negotiate <base64-SPNEGO-token>
~~~

**Do not confuse** `Authorization: Negotiate` with `Authorization: Bearer`. Bearer access tokens are used in OAuth2 Resource Servers; SPNEGO tokens are Kerberos proof used by HTTP negotiation. The values above are illustrative only, not real credentials.

### 4.3. Mandatory Conditions for Reliable Kerberos Operation

1. **Operational KDC/realm** with properly provisioned accounts or service principals.
2. **SPN matching the hostname accessed by browsers**, e.g., `HTTP/app.example.com`; avoid duplicate SPNs across accounts.
3. **Service keytab/credentials** issued for the right account and key version/type; lock down file permissions and never commit to Git.
4. **Consistent DNS, domains, and reverse proxies**; accessing via IP, alias, or another name can stop browsers from fetching the right service ticket.
5. **Synchronized clocks** across KDC, client, and server (clock skew invalidates tickets).
6. **Browser/OS permitting integrated authentication** for the hostname; usually requires intranet/enterprise policy—you cannot assume personal devices or mobile browsers automatically send Kerberos tickets.
7. **TLS/HTTPS** remains essential to protect requests/responses, cookies, and business data, and reduce proxy risks. Kerberos does not replace TLS.
8. **Realm trust / cross-domain trust** works only when infrastructure establishes it and policy permits.
9. **Multi-node / load-balanced deployments** can share consistent keytabs/service accounts; design SPNs and routing accurately.
10. **Verified principal identification and role mapping**. Kerberos tells you an identity is authenticated; it **does not automatically grant application permissions**. Groups/roles may come from LDAP/AD or a separate authorization store.

If any prerequisite is missing, expect **401 Negotiate loops**, keytab/SPN errors, wrong realm errors, or browsers prompting with a login dialog instead of silent SSO.

### 4.4. Dependencies and Scope of Spring Kerberos

At the Java layer, JAAS and Java GSS/Kerberos are **JDK** mechanisms (e.g., `javax.security.auth.login.LoginContext`, `javax.security.auth.kerberos`, `org.ietf.jgss`). A Servlet app handling **HTTP SPNEGO** directly needs extra filters/providers/adapters—or can let a **reverse proxy execute Negotiate** and forward identity over a protected delegation mechanism.

Historically the Spring ecosystem included the **Spring Security Kerberos extension** with artifacts such as:

~~~text
org.springframework.security.kerberos:spring-security-kerberos-core
org.springframework.security.kerberos:spring-security-kerberos-web
~~~

and adapter classes like `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` / `SunJaasKerberosTicketValidator`.

**These are coordinates/components to verify per version, not a guarantee of compatibility with every latest Spring Boot or Spring Security release.** The Kerberos extension follows a separate release schedule from Spring Security core. Never grab a plugin version from a Spring 4/5 tutorial and drop it into Boot 3/Security 6 ignoring Servlet namespace and API changes.

Implementation options:

- **Direct SPNEGO in the Servlet app:** requires a compatible adapter version, KDC, SPN, keytab, and testing on real infrastructure.
- **SPNEGO at a reverse proxy/SSO gateway:** the proxy handles Kerberos authentication and the app trusts identity only over a protected internal channel. **Never** trust `X-Remote-User` or `X-Forwarded-User` sent by Internet clients; the proxy must strip untrusted incoming headers, attach post-auth headers, restrict connection paths (mTLS/network policy), and enforce authorization in the app.
- **Move to OIDC/SAML2 from a Kerberos-integrated IdP:** many IdPs can use Kerberos during user sign-in while emitting standard tokens/assertions for Servlet apps to consume. Often much cleaner for off-domain browsers and modern architectures.

## 5. Dependencies: How to Layer Them and Verify Before Editing pom.xml

No single dependency "turns on CAS + JAAS + Kerberos" simultaneously. Categorize first:

| Practical need | Component / dependency | Prerequisites to verify |
| --- | --- | --- |
| Servlet web with Spring Security filter chain | `spring-boot-starter-security`, `spring-boot-starter-web` if using Boot | Compatible Boot/Java/Jakarta Servlet versions. |
| Login with CAS ticket protocol | Matching CAS module/adapter; `spring-security-cas` is the common historical name | Compatible artifact availability; service URL, CAS server, validator, logout, sessions. |
| CAS Server exposing OIDC | `spring-boot-starter-oauth2-client` | IdP issuer, client registration, secret, redirect URI, OIDC claims. |
| Pure Java JAAS `LoginModule` integration | JDK `javax.security.auth.*`; no separate Maven dependency for JAAS API | Trusted `LoginModule`, callbacks, configuration, `Subject`, role bridge. |
| Spring Security invoking JAAS | JAAS adapter/provider available in selected Spring Security release | Current API, authority mapping, session/context, logout lifecycle. |
| Kerberos/GSS-API in JVM | JDK Kerberos/GSS/JAAS | KDC, realm, service principal, keytab, `krb5.conf`, clock, DNS. |
| HTTP SPNEGO in Spring Servlet | Compatible Kerberos adapter/extension, historically `spring-security-kerberos-core`, `spring-security-kerberos-web` | Spring Security/Servlet compatibility, browser Negotiate, SPN, keytab. |
| SPNEGO at ingress/proxy | Reverse proxy with Kerberos support + secure verified identity forwarding | Strip spoofed headers, mTLS/trust boundary, internal access, auditing. |
| API receiving JWT bearer tokens | `spring-boot-starter-oauth2-resource-server` | Issuer/audience/JWK/token lifetime. Never feed CAS ST or SPNEGO tokens directly. |

### 5.1. Release Dependency Verification Checklist

Before editing `pom.xml`/build files:

1. Confirm **Java 17+**, Spring Boot, and Spring Security versions; inspect which core modules the BOM manages.
2. Check that artifacts **actually exist** and remain supported on the target release; specify **external extension** versions explicitly when not BOM-managed.
3. Confirm **`jakarta.servlet.*`** (Boot 3/Spring Security 6) vs. legacy `javax.servlet.*`; never mix adapters compiled for different namespaces.
4. Inspect the dependency tree to prevent conflicts across `spring-security-core`, Servlet APIs, HTTP clients, and third-party CAS/Kerberos libraries.
5. Avoid `WebSecurityConfigurerAdapter` from legacy examples; modern Servlet configs use `SecurityFilterChain` beans with the current DSL.
6. If the SSO source supports OIDC/SAML2 better than legacy protocols, evaluate standard protocols rather than tying the system to unmaintained bridges.
7. Run integration tests with a **real CAS server / realm / browser** before production; pure Java unit tests cannot prove ticket protocols or end-to-end SPNEGO correctness.

**Do not** rely on a hardcoded Maven version combo like "CAS 6 + Kerberos 2 + Security 6 = guaranteed to work." These modules do not necessarily release in lockstep.

## 6. Authentication, Authorities, and Identity Linking

Whether using CAS, JAAS, or Kerberos, Spring Security authorization still relies on `Authentication` and trusted `GrantedAuthority` values.

Example:

~~~text
CAS principal "an" + attribute groups=["finance"]
JAAS Subject with UserPrincipal("an") + GroupPrincipal("finance")
Kerberos principal "an@EXAMPLE.COM" + AD group lookup
                         |
                         v
       Normalize identity per trusted source
                         |
                         v
   App policy: finance -> ROLE_FINANCE_VIEWER
                         |
                         v
       hasRole("FINANCE_VIEWER")
                         |
                         v
  Further check permissions on resource/tenant/owner
~~~

Security requirements:

- **Never auto-map** arbitrary group names, realm names, or `Principal.getName()` to admin rights.
- Convert strictly via an **allowlist** and owned mapping; e.g., `engineering` → `ROLE_ENGINEER` is a business policy decision, not a built-in CAS/JAAS/Kerberos rule.
- Identity `an` from CAS realm A does not automatically match `an` from realm B. Bind identities to source issuer/realm to avoid **account confusion**.
- Treat **human user** principals differently from **machine/service** principals. For a Kerberos service principal, authenticating an SPN does not imply user privileges.
- Roles can change after login; when authentication is held in a session, define **refresh/re-login/revocation** policies if permission updates must take effect promptly.
- `/admin` may check `hasRole("ADMIN")`, yet multi-tenant data still requires **object-level authorization**.

### 6.1. When Is a Session Required vs. Not Required?

- **CAS web SSO:** after validating a service ticket, apps typically create a local authenticated session; address session timeouts, fixation protection, and logout.
- **JAAS:** `Subject`/principal results do not create an HTTP session themselves; the Spring adapter or app decides how to manage `Authentication` and `SecurityContext`.
- **SPNEGO:** browsers can exchange tokens via HTTP negotiation; apps/gateways may create sessions to cut auth round trips or authenticate per request depending on design. Define session lifecycle, caching, and identity freshness explicitly.
- **OAuth2/OIDC login:** web apps may hold sessions post-login; even when the underlying IdP authenticates via Kerberos, the app still manages its own session.

**CSRF:** If authentication relies on **automatically sent cookies** and state-changing requests exist, maintain proper CSRF protection. Using CAS or Kerberos is no reason to disable CSRF. Conversely, a completely stateless API accepting bearer tokens in the `Authorization` header has a different CSRF profile, though that policy must never be applied blindly to session-based web apps.

## 7. Integration Scope with Spring Security Servlet

### 7.1. Baseline Spring Security Web Configuration

In a modern Servlet app using a properly wired login mechanism, authorization is still declared via `SecurityFilterChain`:

~~~java
// Snippet inside HttpSecurity configuration method:
// Not enough by itself to run CAS, JAAS, or Kerberos; provider/filter must be registered separately.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/health").permitAll()
    .requestMatchers("/finance/**").hasRole("FINANCE_VIEWER")
    .anyRequest().authenticated()
);
~~~

Key takeaway: `authorizeHttpRequests` only declares **access conditions**; it **does not** install CAS service ticket validation, JAAS `LoginModule`s, or SPNEGO ticket verification.

Legacy examples using `WebSecurityConfigurerAdapter`, `configure(AuthenticationManagerBuilder)`, or `antMatchers` require migration to the current version. Never copy old snippets into Spring Security 6 assuming they compile.

### 7.2. Specific Prerequisites per Approach

**CAS direct ticket flow:**

- Endpoint/redirect targeting the right CAS login service; service ticket validator verifying with the CAS Server.
- Callback URL preserving public origin behind reverse proxies.
- Provider converting valid principals to `Authentication` and assigning authorities.
- Session/cookie/SLO and ticket replay handling.
- Adapter compatible with the active runtime and Spring Security version.

**JAAS bridge:**

- One or more trusted `LoginModule`s + explicit `Configuration`.
- `CallbackHandler` receiving credentials cleanly without retaining passwords in logs/long-lived strings.
- Adapter handling `Subject` lifecycles properly and integrating with `SecurityContext`.
- Policy-driven `Principal` → `GrantedAuthority` mapping; test login/logout/abort.
- Choose JAAS only when legacy/runtime integration demands it; do not rebuild all of Spring Security authentication when a better standard protocol exists.

**Kerberos/SPNEGO:**

- KDC/realm/SPN/keytab along with the authentication path.
- Filter/adapter/gateway understanding `Authorization: Negotiate` and returning `WWW-Authenticate: Negotiate` challenges.
- Browser intranet/Negotiate policies and matching DNS hostnames.
- Principal mapping, role lookup, reverse proxy trust boundary, timeouts, and fallbacks.
- Test with real domain-joined clients, not only unit tests with fake principals.

## 8. Error Handling: Distinguishing Authentication Evidence from Environment

| Symptom | Reasonable diagnostic path |
| --- | --- |
| CAS loops endlessly between app and CAS login | Check service URL, HTTPS/public host, cookies/sessions, callback path, ticket validator, and browser. |
| CAS reports invalid ticket | Ticket already used/expired, wrong service, wrong CAS endpoint, or server-to-server validation failure. |
| CAS login succeeds yet `/admin` returns 403 | Principal authenticated but lacks business authority or policy denies access. |
| JAAS `LoginException` | Check `LoginModule`, `login.config`, `CallbackHandler`, flags, and authentication data source. |
| JAAS `Subject` has principal yet Spring lacks roles | Missing/mismatched mapping from principal to `GrantedAuthority`; a `Subject` alone does not yield `ROLE_*`. |
| Browser Kerberos loops on 401 Negotiate | Check SPN, keytab, realm, DNS, browser integrated auth, and KDC/client/server clocks. |
| Kerberos works on one hostname yet fails on alias | SPN does not match FQDN/alias or browser refuses to send tickets for that hostname. |
| Kerberos fails behind proxy | Proxy may strip `Authorization: Negotiate`, terminate auth without safe identity forwarding, or alter hostname. |
| JDK JAAS demo runs fine yet web CAS/Kerberos fails | Demo proves only JAAS lifecycle; CAS/Kerberos require real IdP/KDC/browser/protocol adapters. |
| Legacy Spring adapter throws class/method errors | Incompatible Spring Security/Boot/Servlet namespace or dependency versions. |
| Login works yet another tenant's documents are visible | Object-level authorization bug; independent of authentication protocol. |

**Never debug by logging TGTs, service tickets, keytabs, passwords, client secrets, or full `Authorization` headers.** Log step names, error categories, correlation IDs, and safe metrics; keep credentials out of logs/traces.

## 9. Testing and Acceptance by Infrastructure

**Unit tests** can verify authority mapping, validation policies, and JAAS callbacks. Only **integration tests** verify real ticket/SSO mechanisms:

| Test item | CAS | JAAS | Kerberos/SPNEGO |
| --- | --- | --- | --- |
| Valid login | CAS Server issues ST, app validates, session created cleanly | `LoginModule` + handler/login succeed | Browser receives Negotiate challenge; ticket accepted |
| Invalid/expired credentials | Invalid/expired/replayed ST rejected | `LoginException` with no privileged principal retained | Expired ticket, wrong SPN/keytab, or untrusted realm rejected |
| Permissions | Claims/groups allowlist-mapped; missing `/admin` role → 403 | Subject principals map to right `ROLE_*` | Kerberos principal/AD groups map to right `ROLE_*` |
| Logout/revocation | App logout, CAS SLO if implemented | `LoginModule` logout/abort; Spring session cleared | Session logout/freshness, keytab rotation |
| Infrastructure | CAS unreachable/TLS error → no fail-open | Auth backend unavailable → no privileges granted | KDC/DNS/clock/browser policy/alias/proxy |
| Web protection | HTTPS, session cookies, CSRF, open redirect | Credential handling, session, and CSRF if applicable | HTTPS, reverse proxy trust, CSRF if cookie sessions exist |

**Running the JAAS demo**: `javac JaasFlowDemo.java` then `java JaasFlowDemo`. This verifies only the JDK API.

**Testing CAS or Kerberos**: requires the corresponding environment and authorized test accounts. You cannot honestly claim a standalone Java program verifies CAS/Kerberos SSO without a real CAS Server/KDC, SPN, keytab, browser, and policies.

### 9.1. Pre-Production Deployment Checklist

1. Confirm the organization's **actual login protocol**: CAS service-ticket, OIDC/SAML2 via CAS, JAAS module, Kerberos SPNEGO, or an IdP using Kerberos on the backend.
2. Pick **maintained and compatible** dependencies/adapters for your Java/Boot/Security/Servlet stack; inspect BOM and namespaces.
3. Prove the application trusts only **CAS Server / `LoginModule` / KDC / proxy identity** verified inside the trust boundary.
4. Govern HTTPS, certificates, client secrets, keytabs, realm/SPN, DNS, and clock synchronization.
5. Separate authentication from role mapping; enforce allowlists and **resource/tenant** checks.
6. Test invalid/replayed tickets, missing roles, expired credentials, unavailable backends, session timeouts, logout, and reverse proxies.
7. Never turn off CSRF/session protections by default merely because login uses SSO.
8. Maintain plans for rotation, monitoring, auditing, and IdP/KDC outages.
9. If mobile/external users need support, consider standard OIDC/SAML2 instead of forcing all clients through Kerberos browser negotiation.
10. Document ownership clearly: who operates CAS/KDC/AD/adapters, who approves permission mappings, and who handles incidents and key rotation.

## 10. Self-Check Questions

**1.** "JAAS and Kerberos are two equivalent browser SSO protocols"—is that true?

**Answer:** No. JAAS is a Java API coordinating `LoginModule`/`Subject`; Kerberos is a network authentication protocol. A JAAS `LoginModule` can interact with Kerberos in an appropriate setup.

**2.** Is adding `spring-boot-starter-security` enough for CAS login to work?

**Answer:** Not yet. You also need a CAS Server, service URL, compatible ticket validation adapter/version, or OIDC/SAML2 if the CAS Server supports them.

**3.** Should a Spring Boot 3 application copy any `spring-security-cas` version straight from an old Spring 4 post?

**Answer:** No. Verify artifact support, Java/Spring/Servlet namespaces, and the dependency tree. If using CAS Server as an OIDC IdP, OAuth2 Client OIDC integration fits better in many projects.

**4.** Why does SPNEGO work on a domain-joined laptop yet fail on a personal phone?

**Answer:** The browser/OS/device may lack a TGT or not be configured for integrated authentication with that hostname/realm. KDC, DNS, SPN, and network policy alignment are also required.

**5.** Once CAS/JAAS/Kerberos authenticates "admin," can `hasRole` and tenant checks be skipped?

**Answer:** No. Authentication confirms identity; application authority mapping and authorization decide which endpoints and objects that person may access.

**6.** Why must the application server never trust `X-Remote-User` from arbitrary requests?

**Answer:** Clients can forge headers themselves. Trust headers only when attached by an authenticating gateway after stripping client data and securing the connection/trust boundary; still enforce permissions inside the app.

**7.** Did the Java 17 JAAS sample above test Kerberos or CAS?

**Answer:** Not yet. It illustrates only `LoginContext`/`LoginModule`/`Subject` with mock credentials. CAS needs a CAS Server/ticket validator; Kerberos needs KDC/realm/SPN/keytab/Negotiate clients.

---

## Conclusion

**CAS** solves SSO via **service tickets**; **JAAS** is **Java's** authentication API capable of bridging `LoginModule`s into Spring; **Kerberos** is a ticket-based authentication protocol typically delivered via **SPNEGO/HTTP Negotiate** on intranets. Each technology requires **distinct infrastructure, dependencies, and operational conditions**. Never equate a CAS ST with an OAuth bearer token, never treat a JAAS `Subject` as automatically granting Spring roles, and never assume adding a Kerberos library suffices without SPN/keytab/KDC/browser policies.

**Safety principle:** verify adapter versions; validate tickets/credentials against trusted sources; map authorities via allowlists; use HTTPS; control sessions/CSRF/logout; and always enforce resource-level authorization after login.