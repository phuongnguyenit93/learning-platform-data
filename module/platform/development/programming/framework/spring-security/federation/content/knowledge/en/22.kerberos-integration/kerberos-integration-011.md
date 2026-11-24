# Limitations of Application Logout While User Workstation Kerberos Tickets Remain Valid

## 1. Real-World Problem: Logout Succeeds Yet the User Immediately Logs Back In

Employee **alice@EXAMPLE.ORG** is logged into a corporate domain-joined Windows workstation. Her browser permits **Integrated Windows Authentication (IWA)** on **https://intranet.example.org**. The browser receives the **HTTP 401 WWW-Authenticate: Negotiate** challenge, uses the machine's Kerberos credentials, sends **Authorization: Negotiate**, and Spring Security creates a local Authentication and HttpSession.

Alice clicks **Logout**. The application clears SecurityContext, invalidates HttpSession, and redirects to a public page. Yet when Alice reopens **/private**, the browser can automatically authenticate via Kerberos again **without prompting for a password**. Users easily misinterpret this as a broken logout.

Both statements are simultaneously true:

- **Local logout succeeded:** the application ended the old HTTP session, and the old SecurityContext cannot be reused.
- **Kerberos SSO persists:** the user's workstation TGT or service ticket remains valid; the browser can perform **a brand-new authentication** to obtain a brand-new application session.
- **Local authorization is independent:** Kerberos recognizing the user does not restore revoked permissions, roles/tenant memberships, or disabled accounts.

**Core rule:** **Spring Security `POST /logout` does not destroy TGTs or service tickets in the user's OS Kerberos cache.** That lies in a separate scope owned by the client machine and the Kerberos KDC. A web app logout button cannot promise the user is logged out of their entire workstation, domain, or all applications.

This lesson belongs to **Kerberos Integration / Spring Security - federation**, using examples with **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, and Spring Security Kerberos extension 2.1.0**. Domain **EXAMPLE.ORG** and URL **example.org** are examples only; real Kerberos login requires an actual KDC/AD, SPN, keytab, DNS/HTTPS, and browser policy.

### Objectives

1. Distinguish **TGT, service ticket, GSS/SPNEGO authentication, SecurityContext, HttpSession, cookies, and local account status**.
2. Describe **local logout → protected request → HTTP Negotiate → silent reauthentication**.
3. Configure **LogoutFilter, SecurityContextLogoutHandler, POST /logout, CSRF, and a logout success page** properly in Spring Security 6.x.
4. Prevent immediate re-authentication on `/signed-out` using a **public filter chain without the SPNEGO filter**.
5. Distinguish **OS logoff**, purging Kerberos caches, disabling users, revoking local sessions, and **step-up authentication**.
6. Design logout guidance for intranets, shared workstations, and multi-app enterprises.
7. Verify the old session is invalidated while demonstrating a new Kerberos login can still happen.
8. Preserve HTTPS, CSRF, ticket validation, local authorization, and replay protections alongside logout handling.

## 2. Where Do the Independent States Live?

| State | Who Holds It? | Does Spring Local Logout Clear It? |
| --- | --- | --- |
| **Windows/OS logon session** | Workstation operating system. | No. |
| **TGT** | OS Kerberos credential cache, e.g., Windows LSA or MIT ccache. | No. |
| **Kerberos service ticket** | Client credential cache, scoped to a specific SPN. | No. |
| **GSS/SPNEGO exchange** | Browser/OS and server acceptor during HTTP authentication. | Does not wipe all device GSS credentials/contexts. |
| **Spring Authentication** | Request SecurityContext or persisted repository. | Yes, when LogoutFilter runs properly. |
| **Spring SecurityContextRepository** | HttpSession or configured store. | Cleared by properly configured logout handler. |
| **HttpSession** | Servlet container or Spring Session shared store. | Normally invalidated. |
| **JSESSIONID/SESSION cookie** | Browser, bound to website, domain/path. | May be expired/deleted on best effort; old session must be invalid on server. |
| **Local account, roles, and tenant membership** | App database/LDAP/IGA. | Not deleted automatically; still checked. |
| **Other application sessions** | App B, SaaS, IdP, other proxies. | Not logged out automatically by App A. |
| **SAML/OIDC IdP session** | Enterprise IdP/OP, if bridged. | Not cleared automatically when logging out of a Kerberos app. |

**A TGT is not JSESSIONID**, and **a service ticket is not a session cookie**. A client holding a TGT can request a service ticket for **HTTP/intranet.example.org@EXAMPLE.ORG**; the web server verifies that ticket via GSS-API/keytab. Once authenticated, Spring can issue a cookie to avoid running a GSS exchange on every request.

**TGT differs from service ticket:** the TGT is presented to the KDC/TGS to obtain tickets, whereas a service ticket is bound to one SPN and may already be cached on the client. Purging the TGT while leaving an unexpired service ticket **does not necessarily** block access to that service. Conversely, lacking a service ticket while holding a TGT when the KDC is unreachable also prevents obtaining a new ticket.

## 3. HTTP and Kerberos Sequence After Local Logout

~~~text
T0  User logs into Windows/domain
    Client OS cache: valid TGT

T1  Browser GET /private
    SP: HTTP 401 WWW-Authenticate: Negotiate
    Browser: obtains service ticket for SPN, sends GSS token
    SP: GSS/Kerberos validator checks token + keytab + service policy
    SP: UserDetailsService maps verified principal -> local account
    SP: creates Authentication, saves SecurityContext into session S1
    GET /private -> HTTP 200 if authorized

T2  User POSTs /logout with valid CSRF token
    Spring LogoutFilter:
       invalidate HttpSession S1
       clear Authentication and SecurityContext
       cleanup repository / CSRF state per config
       redirect to /signed-out
    OS workstation: TGT/ST unchanged

T3  GET /signed-out
    Public chain without SpnegoAuthenticationProcessingFilter
    HTTP 200: "This application session has ended"

T4  User returns to GET /private
    Protected chain: 401 Negotiate
    Browser: still holds TGT/ST, auto-sends fresh Kerberos token
    SP: re-verifies, checks local account and permissions
    If passing -> new local SecurityContext/session S2
    S2 differs from S1; user may not have to re-enter password
~~~

**Logout does not resurrect S1.** If after T2 the user receives session S2, that is a **new authentication**, not the old session remaining alive. QA must trace the session lifecycle plus **KERBEROS_AUTHENTICATION** and **LOCAL_LOGOUT** events rather than just checking whether the browser renders the private page.

### HTTP Example

Logout request when CSRF is enabled:

~~~http
POST /logout HTTP/1.1
Host: intranet.example.org
Cookie: JSESSIONID=OLD_SESSION
Content-Type: application/x-www-form-urlencoded

_csrf=VALID_CSRF_TOKEN
~~~

An illustrative response:

~~~http
HTTP/1.1 302 Found
Location: /signed-out
~~~

The servlet container and cookie settings decide whether an extra `Set-Cookie` expiring `JSESSIONID` is sent; **not every deployment produces identical headers byte-for-byte**. What must be verified is that **OLD_SESSION is invalidated on the server**.

Afterward:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

A browser holding valid credentials can automatically respond:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Authorization: Negotiate NEW_GSS_TOKEN_GENERATED_FOR_THIS_EXCHANGE
~~~

The raw token is merely an illustrative placeholder. **Never copy/replay an old HTTP token** and call it Kerberos authentication: the GSS/Kerberos acceptor still checks the authenticator, keytab, freshness, clock, and replay. Depending on browser/settings, multiple Negotiate rounds and final tokens may occur.

## 4. What Does Spring Security Logout Actually Process?

Per Spring Security 6.x Servlet logout architecture:

- **GET /logout** with CSRF enabled usually renders a confirmation page containing a form, rather than executing logout.
- **POST /logout + valid CSRF token** is processed by **LogoutFilter**.
- **SecurityContextLogoutHandler** clears Authentication, clears SecurityContext in the holder/repository, and invalidates HttpSession per config.
- Additional logout handlers can clear CSRF tokens, remember-me tokens, or app-specific data.
- **LogoutSuccessHandler** decides the post-logout status/redirect, e.g., to **/signed-out**.
- **LogoutFilter runs before AuthorizationFilter**, so you do not need to open all protected resources just to let logout execute.

**The Logout button must use POST**, or an equivalent CSRF-protected mechanism; never disable CSRF just to use `GET /logout` as a state-changing action.

### 4.1. Commonly Used APIs

~~~java
// Illustrative Java DSL snippet placed inside HttpSecurity configuration.
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/signed-out")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .permitAll());
~~~

- **invalidateHttpSession(true):** invalidates the application's HttpSession.
- **clearAuthentication(true):** removes Authentication from SecurityContext on logout.
- **deleteCookies("JSESSIONID"):** hints the browser to delete the cookie if domain/path/config match. The server session must already be invalidated even if the browser still sends the old cookie.
- **logoutSuccessUrl("/signed-out"):** redirects to a public page; requires a `permitAll` route **and** preventing SPNEGO from auto-authenticating on that route.
- None of these calls delete the **Kerberos TGT/ST** on the workstation.

### 4.2. Clear-Site-Data and Cookies Are Not KDC Logout

**Clear-Site-Data** is an HTTP response header instructing the browser to clear site data (cookies/storage/cache depending on directives and browser). This header **is not a protocol for managing Kerberos tickets in Windows LSA**. Clearing a web origin's cookies is not equivalent to signing out of a Windows domain.

`JSESSIONID` cookies should carry appropriate **Secure, HttpOnly, and SameSite** attributes. On logout, truly blocking session hijacking relies on **server-side session invalidation**, not merely the browser deleting a cookie.

### 4.3. Why Can a Public URL Still Auto-Reauthenticate?

`permitAll("/signed-out")` alone does not stop authentication filters from running. A browser that already used Negotiate may proactively send **Authorization: Negotiate** on subsequent requests depending on HTTP auth caches/browser behavior. If `SpnegoAuthenticationProcessingFilter` still sits in the chain serving `/signed-out`, it can process the header and create a local Authentication right on the public page.

The illustrative solution below separates:

1. **Public/logout chain** for **/**, **/logout**, and **/signed-out**, with no SPNEGO filter attached.
2. **Protected fallback chain** for all remaining URLs, using the SPNEGO entry point/filter/provider.

Splitting chains keeps the confirmation page from challenging or processing Negotiate **in Spring**, yet **does not block re-login** once the user visits `/private`. If an enterprise reverse proxy acts as the Kerberos acceptor ahead of Spring, you must also exempt the public logout URL at the **proxy**.

## 5. Kerberos Tickets Can Remain Valid Across Multiple States

| Client Credentials After Logout | Possible Behavior |
| --- | --- |
| **TGT valid and KDC reachable; ST uncached** | Client requests a new service ticket via TGS and can authenticate. |
| **Cached ST still valid, TGT gone** | Client can still present the ST for that service without immediately contacting the KDC. |
| **TGT valid yet KDC offline, no ST** | Client cannot fetch a new ticket; Negotiate fails. |
| **Both TGT and ST expired/gone, no way to reacquire** | Browser cannot finish silent SSO; app keeps challenging. |
| **Browser does not allowlist site** | Browser does not send Negotiate automatically even though OS holds a TGT. |
| **Wrong SPN/keytab or time skew/replay** | Server rejects GSS validation even though a ticket exists on the client. |
| **User's local account disabled** | App blocks new logins/access per policy even with a valid Kerberos ticket. |
| **Session S1 still active in another app** | Logging out of App A does not automatically terminate App B's session. |

TGTs/STs have their own lifetimes, renewable policies, encryption keys, KVNOs, and trust realms. Never promise that disabling a user in Active Directory **immediately** voids every previously issued service ticket. Local app sessions, cached service tickets, and permission caches can survive until expiration or revalidation. Rapid revocation requires **app-level authorization and session revocation**.

**Kerberos logout is not like CAS SLO, SAML2 SLO, or OIDC RP-initiated logout.** Even when an IdP uses Kerberos for upstream login and issues SAML/OIDC to SaaS, logging out of SaaS/IdP does not automatically clear the workstation's TGT.

## 6. Standalone Java 17: Simulating Local Sessions Differing from Workstation Tickets

**KerberosLogoutStateDemo.java** runs with JDK 17 alone, requiring no KDC/AD/keytab. It is a state model, **performing no real Kerberos validation**. When the code prints **NEW_APP_SESSION_AFTER_KERBEROS**, it **assumes** the client could obtain a ticket, the GSS acceptor verified it, and the local account is permitted; never replace that with a client-sent boolean in production.

~~~java
public class KerberosLogoutStateDemo {
    record Tickets(boolean hasTgt, boolean hasServiceTicket,
                   boolean kdcReachable) {}

    static String accessPrivate(boolean localSession, Tickets tickets,
                                boolean activeAccount) {
        if (!activeAccount) {
            return "403 ACCOUNT_DISABLED";
        }
        if (localSession) {
            return "200 EXISTING_APP_SESSION";
        }

        boolean canTryKerberos = tickets.hasServiceTicket()
                || (tickets.hasTgt() && tickets.kdcReachable());
        if (!canTryKerberos) {
            return "401 NEED_KERBEROS_CREDENTIAL";
        }
        // Simulates condition only; does not verify a GSS token.
        return "200 NEW_APP_SESSION_AFTER_KERBEROS";
    }

    public static void main(String[] args) {
        Tickets workstation = new Tickets(true, true, true);

        System.out.println("before logout: "
                + accessPrivate(true, workstation, true));

        // Local logout clears app session, DOES NOT touch OS credential cache.
        boolean appSession = false;
        System.out.println("after logout: session=" + appSession);
        System.out.println("cached tickets: tgt=" + workstation.hasTgt()
                + ", service=" + workstation.hasServiceTicket());

        System.out.println("signed-out page: 200 PUBLIC");
        System.out.println("revisit: "
                + accessPrivate(appSession, workstation, true));

        Tickets serviceOnly = new Tickets(false, true, false);
        System.out.println("cached service only: "
                + accessPrivate(false, serviceOnly, true));

        Tickets tgtWithKdc = new Tickets(true, false, true);
        System.out.println("TGT with KDC: "
                + accessPrivate(false, tgtWithKdc, true));

        Tickets offline = new Tickets(true, false, false);
        System.out.println("TGT without KDC: "
                + accessPrivate(false, offline, true));

        Tickets empty = new Tickets(false, false, false);
        System.out.println("no tickets: "
                + accessPrivate(false, empty, true));

        System.out.println("account revoked: "
                + accessPrivate(false, workstation, false));
    }
}
~~~

Run:

~~~bash
javac KerberosLogoutStateDemo.java
java KerberosLogoutStateDemo
~~~

**Exact stdout:**

~~~text
before logout: 200 EXISTING_APP_SESSION
after logout: session=false
cached tickets: tgt=true, service=true
signed-out page: 200 PUBLIC
revisit: 200 NEW_APP_SESSION_AFTER_KERBEROS
cached service only: 200 NEW_APP_SESSION_AFTER_KERBEROS
TGT with KDC: 200 NEW_APP_SESSION_AFTER_KERBEROS
TGT without KDC: 401 NEED_KERBEROS_CREDENTIAL
no tickets: 401 NEED_KERBEROS_CREDENTIAL
account revoked: 403 ACCOUNT_DISABLED
~~~

**Takeaway:** clearing the local session does not delete client tickets. If the user holds an unexpired ST or a TGT with a reachable KDC, a new authentication can start. Checking active local account status blocks access per policy. In reality, a cached ticket can still fail on wrong SPN/keytab/clock/replay/realm/browser/GSS mechanisms, so the demo **does not define Kerberos acceptance policy itself**.

## 7. Spring Boot 3.3.5 + Kerberos Extension 2.1.0

The sample below uses **two SecurityFilterChains** to isolate the public logout page from the custom SPNEGO filter. Conditions to run real Kerberos:

- KDC/Active Directory realm **EXAMPLE.ORG** exists.
- User **alice@EXAMPLE.ORG** is allowed by both realm and local app.
- SPN **HTTP/intranet.example.org** is properly registered on a service account.
- Server has a **keytab** holding service keys with matching principal/KVNO/enctype and tight permissions.
- Browser IWA policy permits `intranet.example.org`; client machine holds Kerberos credentials.
- HTTPS DNS/ingress serves **https://intranet.example.org**; localhost HTTP does not share the same SPN.
- Session/CSRF cookies and reverse proxies are securely operated.

### 7.1. pom.xml

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
    <artifactId>kerberos-local-logout</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-core</artifactId>
            <version>2.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-web</artifactId>
            <version>2.1.0</version>
        </dependency>
    </dependencies>
    <build><plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins></build>
</project>
~~~

**Spring Security Kerberos is an extension**, not included automatically by starter-security alone. The **2.x** family uses groupId **org.springframework.security.kerberos**; never copy 7.x APIs/coordinates into Boot 3.3 without verifying dependency compatibility. This sample is for learning; check security advisories and run integration tests when upgrading versions.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

app:
  kerberos:
    principal: "HTTP/intranet.example.org@EXAMPLE.ORG"
    keytab: "/etc/security/keytabs/http-intranet.keytab"
~~~

This is an illustrative keytab path. In production mount the secret file server-side, protect file ACLs and rotation, and never commit keytabs to Git. Match the public hostname to the SPN; never dynamically derive principals from untrusted `Host`/`X-Forwarded-Host` headers.

### 7.3. Main Class

**src/main/java/com/example/krblogout/KerberosLogoutApplication.java**

~~~java
package com.example.krblogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosLogoutApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — Separated Public/Logout and Protected Chains

**src/main/java/com/example/krblogout/SecurityConfig.java**

~~~java
package com.example.krblogout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository sessionContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
    }

    @Bean
    UserDetailsService users() {
        return username -> {
            // Only principals provisioned in the local user store.
            if (!"alice@EXAMPLE.ORG".equals(username)) {
                throw new UsernameNotFoundException("Local account denied");
            }
            return User.withUsername(username)
                    .password("{noop}not-used-for-kerberos")
                    .authorities("ROLE_EMPLOYEE")
                    .build();
        };
    }

    @Bean
    SunJaasKerberosTicketValidator kerberosValidator(
            @Value("${app.kerberos.principal}") String principal,
            @Value("${app.kerberos.keytab}") String keytab) {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(keytab));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    @Order(1)
    SecurityFilterChain publicAndLogout(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        http
            .securityMatcher("/", "/signed-out", "/logout")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .securityContext(sc -> sc
                .securityContextRepository(repository))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .permitAll());

        // Do not place SpnegoAuthenticationProcessingFilter on chain 1.
        // CSRF stays enabled per Spring Security defaults.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain protectedApplication(
            HttpSecurity http, SecurityContextRepository repository,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        SpnegoAuthenticationProcessingFilter spnego =
                new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(repository);
        spnego.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(sc -> sc
                .securityContextRepository(repository))
            .authenticationProvider(provider)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);

        // No securityMatcher: chain 2 protects ALL remaining URLs.
        return http.build();
    }
}
~~~

**Scope-accurate analysis:**

1. **@Order(1)** matches **/**, **/logout**, **/signed-out** with no SPNEGO filter attached. On public landing pages, Spring neither inspects Negotiate headers nor emits 401 challenges.
2. **LogoutFilter** in the public chain handles **POST /logout** with a CSRF token. `GET /logout` typically shows Spring's confirmation form.
3. **@Order(2)** acts as the protected fallback chain **for every URL outside chain 1**; no accidental gap from matching only `/private` while forgetting other routes.
4. **SpnegoEntryPoint** emits 401 Negotiate on protected URLs when anonymous.
5. **SpnegoAuthenticationProcessingFilter** reads the `Authorization: Negotiate` token and delegates via **ProviderManager** to **KerberosServiceAuthenticationProvider/SunJaasKerberosTicketValidator**.
6. **SecurityContextRepository** is shared across both chains and the filter so logout clears persisted state properly and successful SPNEGO logins save stateful sessions.
7. **ChangeSessionIdAuthenticationStrategy** mitigates session fixation upon creating an Authentication.
8. **UserDetailsService** restricts permitted accounts; never auto-provision every Kerberos user as admin.
9. **deleteCookies JSESSIONID** cleans only the app cookie, not the OS TGT.
10. Never enable hidden formLogin/Basic fallbacks or disable CSRF just for demos.
11. **Users holding valid Kerberos tickets can still re-authenticate on /private.** This configuration does not pretend to "block Kerberos re-login".
12. If a reverse proxy serves as the SPNEGO acceptor, verify authentication scoping at the proxy outside Spring as well.

For production, add operation/resource/tenant authorization, account revocation, session timeouts/HA, keytab rotation, TLS, log redaction, and browser compatibility. The demo does not configure AD, KDC, or workstations automatically.

### 7.5. Controller

**src/main/java/com/example/krblogout/Pages.java**

~~~java
package com.example.krblogout;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Pages {

    @GetMapping("/")
    public String home() {
        return "Public home. Visit /private or GET /logout.";
    }

    @GetMapping("/signed-out")
    public String signedOut() {
        return "Local application session ended. "
            + "Kerberos tickets on your workstation may remain valid.";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "Kerberos authenticated: " + authentication.getName();
    }
}
~~~

### 7.6. Run and Observe

~~~bash
mvn spring-boot:run
~~~

If the app starts and keytab/KDC/browser sandbox are properly configured:

1. **GET /** returns public text without invoking Spring's SPNEGO filter.
2. **GET /private** when anonymous receives 401 Negotiate; the browser uses IWA if hostname and policy allow.
3. **alice@EXAMPLE.ORG** holds a valid ticket and is permitted by `localUsers`; `GET /private` returns **Kerberos authenticated: alice@EXAMPLE.ORG**.
4. **GET /logout** renders the logout confirmation page (with default CSRF enabled).
5. **POST /logout** with valid CSRF performs local logout and redirects to **/signed-out**.
6. **GET /signed-out** skips Spring's SPNEGO filter and confirms local logout succeeded.
7. **GET /private again** can silently re-authenticate with Kerberos and create a new session without prompting for a password.
8. If the local user is disabled or lacks roles/tenant rights, the app must deny per local policy regardless of having a ticket.

Without a real KDC/keytab, end-to-end Kerberos login cannot be confirmed. The `example.org` URL in this lesson is illustrative, not a real CAS/SAML IdP or Kerberos domain.

## 8. Distinguishing Three Types of "Wanting to Prevent Re-Access"

### 8.1. User Wants to See a "Logged Out" Screen

This is a UX requirement. Use **POST logout + public /signed-out without SPNEGO** to show a confirmation message before the user actively navigates back to a protected resource. Never promise this action blocks future silent Kerberos authentication.

### 8.2. Enterprise Wants to Revoke All Local Sessions

The app can use **Spring Session, SessionRegistry, indexed session repositories**, or session version/revoked-before timestamps to invalidate a user's active HttpSessions per policy, even multi-node. Yet if the user still holds Kerberos credentials and remains approved in the local app, a **new** login can still succeed.

Combine **application session revocation + a local account permission gate** if you need to block subsequent access as well. An already-issued session does not automatically pick up AD permission changes unless the app rechecks them.

### 8.3. Sensitive Actions Requiring User Presence or Fresh MFA

If a user clicks Logout and policy demands **interactive authentication** before entering payroll/admin, HTTP 401 Negotiate is insufficient because the browser can silently reauthenticate. Enforce a **step-up assurance policy** (such as WebAuthn/FIDO2 or IdP/app-verified MFA) and validate freshness, operation, device, and account state before permitting the action. Kerberos can remain the bootstrap identity without treating it as fresh MFA proof.

**Never use tricks like disabling replay protection or accepting unverified GSS tokens** to work around logout UX. Accept 401 Negotiate or route to a compliant IdP per policy; protect the protocol first.

## 9. Client Kerberos Commands and Permission Boundaries

### Windows

On a client machine within an authorized logon session:

~~~powershell
klist
klist tgt
klist tickets
~~~

**`klist purge`** can delete Kerberos tickets for the **selected logon session**. Run only in a lab or under IT procedures, as it affects all Kerberos-using applications rather than just one website:

~~~powershell
# ONLY WHEN APPROVED ON YOUR OWN MACHINE/SESSION:
klist purge
~~~

**Never run that command on the web server expecting it to delete tickets in users' browsers.** It affects only the credential cache of the machine/identity executing it, subject to logon session options and privileges. Even after a purge, a logged-in workstation can reacquire tickets via OS domain credentials/SSO policy. Purging does not automatically terminate active HttpSessions on other applications.

### MIT Kerberos on Linux/macOS

~~~bash
klist
# ONLY in a managed environment with full understanding of impact:
kdestroy
~~~

**`kdestroy`** deletes the selected Kerberos credential cache in MIT Kerberos environments, not a universal command clearing every browser/OS credential across devices. With KCM, SSSD, keyrings, multiple ccaches, or live in-process GSS contexts, behavior depends on platform.

### OS Logoff vs. Lock Screen

- **Signing out/logging off the workstation OS session** ends the user session at the device level per platform policy, typically required when leaving a shared machine.
- **Locking the screen** does not delete the TGT; it only restricts physical access provided others cannot unlock it.
- **Closing tabs/browsers or using private windows** does not guarantee the OS TGT disappears.
- **Web JavaScript has no universal right to invoke OS commands to purge Kerberos TGTs** and should never ask for such privileges.

For kiosks/hot desks, combine app logout, OS session management, user switching, device policies, and local account/session timeouts. Never claim web app logout alone leaves an unlocked machine safe for the next person.

## 10. Account Disable / AD Revocation Does Not Instantly Void All Cached Tickets

When an AD admin disables a user, the KDC can refuse **new tickets** per policy, yet:

- **Previously issued service tickets** may stay valid until expiry or until the service checks additional policy.
- **Issued TGTs** have their own lifetimes; KDC responses to subsequent ticket requests depend on account state and realm policy.
- **Existing local Spring sessions** can continue being trusted by the app without revocation/session revalidation.
- **Unrefreshed UserDetailsService caches** or role/tenant memberships can retain revoked permissions.
- **External proxies** or upstream IdPs maintain their own sessions.

For near-immediate revocation on sensitive APIs, require:

1. **Server-side local account state** as an updatable source of authority.
2. Blocking **new Kerberos Authentications** for disabled accounts without auto-reprovisioning.
3. Re-checking **roles/tenant/resource permissions** per risk-based TTL/version on sensitive requests/actions.
4. Revoking app sessions across **all nodes** via shared store/session registry.
5. Clearing/revalidating permission caches and other issued internal tokens.
6. Monitoring/auditing, reason codes, and logout-all-devices policies.
7. Never claiming "all Kerberos tickets were revoked" without OS/KDC-level verification.

**Authorization differs from authentication:** a valid Kerberos ticket only identifies the principal; the application decides whether the account is still active and permitted to access the resource.

## 11. Reverse Proxies, Browser Auth Caches, and Race Conditions

If a proxy (IIS, Apache, Nginx + module, or gateway) acts as the **Kerberos acceptor**, it may authenticate the browser **before the request reaches Spring**. Spring app logout ends only local state; the proxy can still re-authenticate the browser and forward a **verified identity header** to the backend.

In that setup:

- Public `/signed-out` must be **authentication-exempted** at the proxy to avoid challenges.
- The backend must trust only identity headers overwritten by the proxy over a trusted channel, never accepting **X-User/X-Remote-User** directly from the Internet.
- Forced logout/re-auth policies must cover proxy sessions as well if any exist.
- Browsers may send Negotiate tokens preemptively from auth caches; test real behavior on enterprise-managed Edge/Firefox.

Multi-tab/race conditions:

- Tab A POSTs `/logout` while Tab B already started a request with S1; verify the backend handles session invalidation safely.
- Tab B after logout can acquire a new S2 via silent SPNEGO; never confuse it with S1.
- Browser-cached HTML/JS or service workers may still show sensitive data after logout: apply **`Cache-Control: no-store`** where appropriate and reset frontend state.
- Load balancers/clusters must invalidate shared sessions properly; test Spring Session Redis/JDBC/sticky sessions.
- An old session cookie may remain in the browser yet must be rejected by the server.

## 12. Diagnosing Logout and Silent Login Issues

| Symptom | Likely Reality | How to Verify |
| --- | --- | --- |
| Redirecting to `/private` after logout immediately returns 200 | Protected URL triggered fresh Kerberos SSO. | Redirect to public `/signed-out`, compare S1/S2. |
| `/signed-out` is `permitAll` yet app still authenticates | SPNEGO filter processed preemptive Authorization. | Exclude filter from public chain; check proxy. |
| `POST /logout` returns 403 | Missing/invalid CSRF token, not necessarily a Kerberos error. | GET confirmation, POST with CSRF. |
| `GET /logout` does not invalidate session | Expected default with CSRF enabled. | Use POST logout; never disable CSRF. |
| S1 still accepted after logout | Real bug in LogoutFilter/repository/shared session invalidation. | Test old S1 cookie, logs, and session store. |
| `/private` returns 200 even after clearing cookies | Browser reauthenticated via Kerberos, issuing S2. | Trace Negotiate exchanges and session IDs. |
| `klist purge` ran yet browser still silent-logs in | Ticket reacquired, wrong logon session/cache purged, or OS policy. | Check exact client cache and IT policy. |
| AD account disabled yet user still gets in | Cached ST/local session or stale permission cache persists. | Enforce local account gate + session revocation. |
| `Clear-Site-Data` ran yet TGT remains | Header does not control OS credential caches. | Separate browser site state from Kerberos. |
| Logged out on Node A, Node B still authenticated | Session store/cluster out of sync. | Test Redis/JDBC sessions and invalidation. |
| User missing role still gets 200 after login | Checked only `authenticated`, missing resource authorization. | Method/service authorization, tenant ACLs. |
| Other tab shows report after logout | Frontend cache, in-flight race, or silent reauth. | `no-store`, session trace, frontend state reset. |
| 401 Negotiate loop when app expects login | Browser omits ticket, keytab/SPN/clock error, or filter fails to save context. | KDC/SPN, browser policy, SecurityContextRepository. |
| Next person on kiosk accesses previous user's data | OS session remained open with valid TGT. | OS logoff/kiosk policy, step-up for sensitive actions. |

A good QA report distinguishes **LOCAL_LOGOUT** from **KERBEROS_REAUTH**, without storing raw `Authorization: Negotiate`, `JSESSIONID`, keytabs, TGTs, or service tickets.

## 13. Positive/Negative Test Matrix

Use a **Kerberos KDC/AD sandbox** for integration tests; use the standalone Java 17 program in section 6 to illustrate logic without a real realm.

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | `POST /logout` with valid CSRF | Session S1 invalidated, SecurityContext cleared. |
| 2 | `POST /logout` missing CSRF | 403, no unauthorized logout. |
| 3 | `GET /logout` with CSRF enabled | Confirmation form instead of state-changing GET. |
| 4 | `GET /signed-out` after logout | Public 200, no HTTP Negotiate from Spring. |
| 5 | Browser preemptive Negotiate to `/signed-out` | Public chain skips SPNEGO filter. |
| 6 | Reusing S1 cookie after logout | Server rejects the old session. |
| 7 | TGT/ST valid, `GET /private` after logout | New Kerberos authentication can create S2. |
| 8 | No TGT/ST and unable to acquire | No session auto-created; 401/fallback per policy. |
| 9 | Cached ST valid yet TGT expired | Browser can authenticate to that SPN per policy. |
| 10 | TGT valid, ST uncached, KDC reachable | Browser can fetch a new ST. |
| 11 | TGT valid, ST uncached, KDC offline | Cannot fetch new ST; fails without alternate mechanism. |
| 12 | Browser lacks intranet allowlist | Does not auto-send Negotiate. |
| 13 | Expired/replayed/wrong-SPN service ticket | Kerberos validator rejects. |
| 14 | Locally disabled account | Grants no new access despite valid Kerberos ticket. |
| 15 | Active session yet role revoked | Policy revalidation blocks sensitive permissions. |
| 16 | Request from Tab B after Tab A logs out | S1 fails; S2 may be created if Kerberos remains valid. |
| 17 | Multi-node shared session invalidation | Session revoked across all nodes. |
| 18 | `Clear-Site-Data` clears only site data | OS TGT stays intact unless explicitly purged. |
| 19 | `klist purge` on exact user logon session | Tickets in that cache cleared; may reacquire per OS policy. |
| 20 | `kdestroy` MIT cache | Selected cache cleared; does not log out all HTTP apps. |
| 21 | OS sign-out then another user logs in | New user does not inherit old OS logon context. |
| 22 | Spring public chain misses unknown route | Protected fallback chain still requires authentication. |
| 23 | Reverse proxy acts as SPNEGO acceptor | Public logout exemption at proxy tested separately. |
| 24 | Logout all application sessions | Sessions revoked, though new Kerberos login still obeys account policy. |
| 25 | Sensitive action requires step-up | Silent SPNEGO does not satisfy MFA freshness. |
| 26 | App logout does not affect App B | Expected; App B holds its own session. |
| 27 | Domain account disabled while cached ticket exists | Local authorization blocks access per policy. |
| 28 | User sees sensitive data in browser cache post-logout | `Cache-Control: no-store`/frontend reset per risk. |
| 29 | Session fixation on Kerberos re-login | Session ID rotation/strategy enforced. |
| 30 | Browser retains TGT during `GET /signed-out` | Public page renders without Spring auto-reauth. |

**Never evaluate logout solely by HTTP 200 on `/private`.** You must distinguish whether **the old session was destroyed** versus whether **a new authentication was initiated**.

### Trace for QA

~~~text
POST /logout (CSRF OK)
  -> 302 /signed-out; S1 invalidated

GET /signed-out
  -> 200 PUBLIC; no Spring Negotiate challenge

GET /private
  -> 401 Negotiate
  -> browser may send Authorization Negotiate
  -> GSS validation + local UserDetails
  -> if permitted, new session S2
~~~

Record privacy-sanitized trace IDs and internal actor IDs, never raw session IDs or tickets. Automated tests can assert **S1 != S2** using test-only identifiers without printing them to logs outside secure environments.

## 14. Operational Checklist

**Logout and sessions**

- [ ] `POST /logout` processed by Spring LogoutFilter with CSRF protection.
- [ ] HttpSession invalidated; Authentication/SecurityContext/repository cleared.
- [ ] Session cookie cleanup matches name/domain/path; old sessions rejected.
- [ ] Public `/signed-out` free of SPNEGO filter/challenge, even under preemptive Negotiate.
- [ ] Protected fallback chain leaves no endpoints exposed outside allowlist.
- [ ] SecurityContextRepository consistent between SPNEGO success and logout.
- [ ] Multi-node session invalidation, session fixation, and concurrent requests tested.

**Kerberos and user policy**

- [ ] Never assume the web app can revoke TGT/ST on workstations.
- [ ] Browser IWA/SPN/keytab/KDC/time/replay/TLS protections remain intact.
- [ ] Disabled users/revoked memberships never admitted merely because Kerberos passes.
- [ ] Never run `klist purge`/`kdestroy` on clients when users simply click website logout.
- [ ] Step-up/fresh MFA designed when actions demand user presence.
- [ ] With a Kerberos proxy, public/logout exemptions configured at the proxy.
- [ ] Shared workstations enforce OS logoff/kiosk reset and display accurate messaging.

**Testing and monitoring**

- [ ] Tested S1 logout, silent SPNEGO S2, and missing-ticket scenarios.
- [ ] Tested preemptive Negotiate on landing pages, browser policies, and Firefox/Edge.
- [ ] Tested disabled accounts, permission revocation, multi-tab, App B, and HA.
- [ ] Sensitive data uses appropriate cache policies to prevent post-logout frontend leaks.
- [ ] Logs exclude Kerberos tokens, ticket caches, credentials, and raw cookies.
- [ ] Local logout is never labeled "global/domain logout".

## 15. Review Questions

**1. Why can a user log out and immediately re-enter the intranet without a password?**  
Because Spring cleared the local session, yet the client still holds a TGT/ST or can fetch a new ticket and perform **a fresh Kerberos authentication**.

**2. Can Spring Security `POST /logout` destroy a Windows TGT?**  
No. It controls only application-level sessions/SecurityContext/cookies, not the OS credential manager.

**3. If the TGT is gone yet a service ticket remains, can the browser still SSO?**  
Possibly, if that service ticket is still valid for the SPN and accepted by the GSS acceptor per policy.

**4. Why isn't `permitAll` on `/signed-out` enough?**  
Authentication filters can still run and process Negotiate headers; a public chain **without `SpnegoFilter`** avoids silent reauth right on the confirmation page.

**5. How do `GET /logout` and `POST /logout` differ when CSRF is enabled?**  
`GET` normally shows a confirmation form; `POST` with a valid CSRF token executes logout.

**6. If `JSESSIONID` is cleared yet the user is authenticated again, does that prove logout failed?**  
No. Check whether old session S1 was invalidated; the user may have been issued a new session S2 via Kerberos.

**7. Can `klist purge` be run from the Spring server to delete tickets on clients?**  
No. The command affects caches/logon sessions on the machine running it, not remote browsers.

**8. Does disabling a user in AD instantly cancel all cached STs/sessions?**  
Cannot be guaranteed; depends on ticket lifetimes, KDC, local sessions, services, and permission caches. Enforce local account gates and revocation.

**9. How should we require MFA after logout even when a TGT still exists?**  
Use an explicit step-up/MFA freshness policy, rather than relying on 401 Negotiate to force a browser password prompt.

**10. If a proxy handles Kerberos ahead of Spring, where must the logout success page be fixed?**  
Both **proxy authentication routing/exemptions** and Spring session policy must be updated; splitting `SecurityFilterChain` on the backend alone may not suffice.

## 16. Standards and API Documentation

1. [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET/POST logout, CSRF, SecurityContextLogoutHandler, and success handlers.
2. [Spring Security 6.5 — LogoutConfigurer Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/LogoutConfigurer.html): invalidateHttpSession, clearAuthentication, deleteCookies, logoutSuccessUrl.
3. [Spring Security 6.5 — SecurityContextLogoutHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html): clearing context and invalidating session.
4. [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter 2.x API](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): filter, SecurityContextRepository, SessionAuthenticationStrategy.
5. [Spring Security Kerberos — Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SPNEGO entry point, validator, provider.
6. [Microsoft Learn — klist on Windows](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/klist): TGT/service tickets, purging per logon session.
7. [MIT Kerberos — kdestroy](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kdestroy.html): client credential cache lifecycle.
8. [RFC 4120 — Kerberos V5](https://www.rfc-editor.org/rfc/rfc4120): TGT, service tickets, AS/TGS, ticket lifetime.
9. [RFC 4559 — SPNEGO HTTP authentication](https://www.rfc-editor.org/rfc/rfc4559): 401 Negotiate, GSS tokens, and HTTP protection boundaries.
10. [Microsoft Edge AuthServerAllowlist](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authserverallowlist): integrated authentication per browser/host policy.
11. [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContextRepository, session fixation, concurrency.
12. [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF defense for logout and state-changing operations.

**Conclusion:** Spring Security logout **only terminates the application's session**; it does not delete **TGTs/service tickets** residing on the workstation. Consequently, the browser can automatically log back in via **Kerberos SPNEGO** whenever the user visits a protected URL. The proper design is **CSRF-protected POST logout, invalidating HttpSession/SecurityContext, and a public signed-out page free of SPNEGO**, paired with **account authorization/revocation, step-up policies, and OS session management** when further access must be prevented.
