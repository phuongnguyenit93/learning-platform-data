# Distinguishing User Passwords, Kerberos Tickets, and Service Keytabs

> **Module:** Spring Security – federation · **Group:** Kerberos and SPNEGO. This document explains the three credential types in Kerberos v5, who holds them, at which stage they appear, how Spring Security SPNEGO uses them, and how to inspect and operate them safely when deploying Java 17+ applications.

## 1. Core Takeaway

The three terms are not interchangeable:

1. **User password:** an initial secret or authentication factor that helps a user prove their identity to the KDC/identity system. In password-based Kerberos flows, the password relates to the **user principal's long-term key** via a string-to-key function; the password **is not sent to the Spring HTTP application when the browser uses Kerberos SPNEGO**. Many environments use PKINIT, smart cards, OS logon, or other mechanisms instead of direct password entry.
2. **Kerberos ticket:** an artifact **issued by the KDC**, containing principal, target service, and lifetime fields protected cryptographically. There is a **Ticket Granting Ticket (TGT)** used to request other tickets and a **service ticket (ST)** scoped to a specific service. The client holds the corresponding session key and sends **the ticket plus an Authenticator** to prove key possession. A ticket **is not a user password**.
3. **Service keytab:** a binary file storing **long-term secret keys** for one or more service principals along with principal/enctype/kvno fields. The Spring/JAAS/GSS acceptor uses the keytab to decrypt/verify tickets addressed to its service. This file **is not a ticket and not a plaintext password**, yet it is a high-value secret requiring strict protection; never send it to the browser.

**Mental model:** user password/initial method → **AS exchange** to acquire TGT → **TGS exchange** to acquire service ticket → HTTP client sends **SPNEGO AP-REQ** → service uses **keytab** to verify ticket and Authenticator → Spring creates Authentication/roles after validation.

## 2. Architecture Overview: Kerberos + HTTP SPNEGO

~~~text
                   REALM: EXAMPLE.ORG
   +------------------------------------------------+
   | KDC: Authentication Server + Ticket Granting   |
   | Long-term principal keys, policies, ticketing  |
   +------------------------------------------------+
          ^ AS-REQ/AS-REP             ^ TGS-REQ/TGS-REP
          |                           |
 User/password or other auth       TGT + request
          |                           |
          v                           v
  +--------------------------------------------------+
  | Client workstation / OS credential cache        |
  | TGT + key material; service ticket + session key |
  +--------------------------------------------------+
                          |
                          | Browser / GSS / SPNEGO
                          | Authorization: Negotiate
                          v
  +--------------------------------------------------+
  | Spring Servlet app at portal.example.org         |
  | SPN HTTP/portal.example.org@EXAMPLE.ORG          |
  | Keytab with HTTP service long-term keys          |
  | Kerberos ticket validation -> trusted principal  |
  | UserDetailsService -> GrantedAuthority           |
  +--------------------------------------------------+
~~~

No step in this diagram requires the browser to **send alice's password to the portal application**. GSS/SPNEGO carries a proof using a service ticket, not Basic Auth credentials.

## 3. Key Concepts

| Term | Meaning |
|---|---|
| **Principal** | A Kerberos identity such as `alice@EXAMPLE.ORG` or `HTTP/portal.example.org@EXAMPLE.ORG` |
| **Realm** | Kerberos administrative domain, usually written in uppercase |
| **KDC** | Key Distribution Center; consists of AS and TGS |
| **AS-REQ / AS-REP** | Initial exchange for the client to acquire a TGT |
| **TGT** | Ticket issued for `krbtgt/REALM@REALM`, used to request service tickets |
| **TGS-REQ / TGS-REP** | Client uses TGT to request a ticket for another service |
| **Service Ticket** | Ticket targeted at a specific service principal |
| **AP-REQ / AP-REP** | Client presents ticket and Authenticator to the app; AP-REP can support mutual authentication |
| **Authenticator** | Fresh data protected by the client–service session key |
| **Session key** | Short-lived key issued by the KDC for a client–service exchange |
| **Long-term key** | Persistent key of a user principal or service principal |
| **Keytab** | File storing long-term keys, principal, enctype, and kvno |
| **SPN** | Service Principal Name, e.g. `HTTP/portal.example.org` |
| **kvno** | Key Version Number, useful when long-term keys are rotated |
| **enctype** | Encryption type associated with a key or ticket |
| **Credential cache** | Client-side storage holding TGT, STs, and key material |
| **SPNEGO** | GSS-API mechanism negotiation, RFC 4178 |
| **HTTP Negotiate** | HTTP authentication scheme carrying GSS/SPNEGO tokens, RFC 4559 |
| **JAAS / Java GSS** | Java APIs for Kerberos login and accepting security contexts |
| **SecurityContext** | Spring Security Authentication state, distinct from a Kerberos ticket |

A **CAS** ticket, **SAML Assertion**, or **OIDC ID Token** belongs to **different protocols**. Never treat a CAS string named "ticket" as a Kerberos service ticket.

## 4. Where Does the User Password Belong?

### 4.1. With Password-Based Authentication

A user `alice@EXAMPLE.ORG` on Linux might run:

~~~bash
kinit alice@EXAMPLE.ORG
~~~

The client interacts with the Authentication Service to obtain a TGT. For password-based methods, the password/derived key serves authentication and decrypts the encrypted Kerberos reply. **Never send a plaintext password to portal**. Once a TGT is obtained, the client can acquire STs for many services via the TGS without prompting for the password each time.

### 4.2. Passwords and User Long-Term Keys Differ

A password is a secret string a user can memorize and type. A Kerberos long-term key is cryptographic material bound to a principal. In many password-based schemes, the key is derived via standardized string-to-key, salt, and enctype rules; **you cannot replace it with a custom hash function like SHA-256(password)** and expect Kerberos compatibility.

The KDC also stores long-term keys for principals, yet a Spring acceptor app **does not need to read the user password** to verify service tickets.

### 4.3. Not Every Kerberos User Types a Password

Mechanisms such as Windows domain sign-in, PKINIT/smart cards, hardware auth, or OS credential caches can supply a TGT without the web app ever seeing a password entry. Hence "a Kerberos session exists" does not prove the user just typed a password or completed enterprise-grade MFA.

### 4.4. Does Changing a Password Immediately Invalidate Old Tickets?

Not by default. When a user changes their password/long-term key, previously issued TGTs/STs can remain valid until their lifetime ends or until the KDC/realm policy performs appropriate revocation. **A password change differs from ticket expiry, kdestroy, application logout, and account disable**.

During incident response, evaluate tickets, OS logon sessions, remote sessions, and session lifecycles rather than only resetting the password.

## 5. What Is a Kerberos Ticket Really?

### 5.1. TGT Is for the Ticket Granting Service

A TGT is issued by the AS after initial authentication; the sensitive part of the ticket is encrypted for `krbtgt/REALM` using a key controlled by the KDC. The user/client holds the TGT and matching key material to send TGS-REQs. **The TGT is not presented directly to an HTTP portal in standard SPNEGO.**

### 5.2. Service Ticket Is for a Specific SPN

The TGS issues a ticket for example:

~~~text
Client principal = alice@EXAMPLE.ORG
Service principal = HTTP/portal.example.org@EXAMPLE.ORG
Lifetime = per KDC policy
Service ticket = ticket encrypted for target service long-term key
Client side = ticket + client-service session key
~~~

A service ticket meant for `HTTP/wiki.example.org` cannot automatically be used for `HTTP/portal.example.org`. Verify the **sname/service principal**, realm, keys, and GSS proof rather than merely reading a username string from a token.

### 5.3. Session Keys Inside Kerberos Exchanges

The KDC establishes a short-lived client-service key. The client learns the session key from the appropriate reply part. The service recovers the session key from the encrypted ticket part protected by the long-term service key.

Differences:

| Session key | Long-term key in keytab |
|---|---|
| Bound to a client-service ticket/context | Bound to a service principal and kvno/enctype |
| Short-lived with the ticket | Valid until rotation or retirement |
| Protects Authenticator/GSS operations | Protects the encrypted ticket part |
| Used by both client and service in the exchange | Held by the KDC and the service |
| Not a user password | Not a user password |

### 5.4. Why a Ticket Alone Does Not Prove Who Is Presenting It

In the AP exchange, the client presents the ticket **together with an Authenticator protected by the session key**. The service uses the long-term key from its keytab to decrypt the encrypted ticket part, extract the session key, and check the Authenticator/timestamp/replay policy. If a client holds only the ticket binary without the matching session key/proof, it has not completed valid Kerberos authentication.

### 5.5. Exposure of a Ticket Cache Is Still Dangerous

A credential cache can contain tickets and key material that allow an attacker to impersonate sessions if compromised. **Never publish klist cache files**, never log token bytes, and never assume "it's just a ticket so it needs no protection".

## 6. What Is a Service Keytab?

A keytab typically contains entries with:
- Principal, e.g. `HTTP/portal.example.org@EXAMPLE.ORG`.
- kvno of the long-term key.
- Encryption type/enctype, e.g. an AES Kerberos enctype.
- Corresponding secret key bytes.

A keytab can contain multiple enctypes, multiple kvnos during rotation, and even multiple principals. **One file does not necessarily equal one account or one password.** It is a binary file, not an HTTPS certificate or a TGT store.

### 6.1. A Keytab Is Not a Plaintext Password

A keytab stores cryptographic keys; in AD or realms using password-derived service secrets, a keytab may carry key material derived from an account secret, yet it does not store a plaintext password string as entered in a form. Regarding **sensitivity**, MIT Kerberos documentation treats a host keytab similarly to a host password because anyone obtaining the keys can impersonate the principal within that scope.

### 6.2. Which Side Primarily Uses the Keytab?

In Spring Security SPNEGO:
- The browser is the **initiator**, using the OS TGT or ticket cache.
- The HTTP server is the **acceptor**, using the service principal key from the keytab to verify incoming AP-REQs.
- The service normally **does not need to know the user password**.

Keytabs are not restricted to acceptors: batch services can also run **kinit -k** with a keytab containing their principal to acquire a TGT non-interactively. That further proves a keytab is a sensitive secret to guard, not a public configuration file.

### 6.3. How Dangerous Is a Compromised Keytab?

Exposed long-term keys can:
- Enable service impersonation for the corresponding SPN.
- Decrypt the encrypted part of captured service tickets matching the key/kvno.
- Expose session keys from captured tickets.
- Permit other Kerberos operations allowed by the principal/key and policy.

The impact is not limited to one expired ST; it persists until keys are rotated and old tickets expire. **Incident response and key rotation are required** rather than merely deleting the exposed file.

## 7. Comparison Table of the Three Credential Types

| Perspective | User password | Kerberos ticket | Service keytab |
|---|---|---|---|
| Created from | User/account authentication process | KDC (AS/TGS) | KDC/admin and service account keys |
| Typical usage point | Initial auth AS-REQ/preauth | TGT at TGS, ST at service | Service-side GSS acceptor |
| Sent to Spring HTTP app? | **No** in Kerberos SPNEGO | Token containing ST/AP-REQ is sent | **No** |
| Lifetime relationship | Account credential validity | Ticket lifetime/flags | Long-term key version/rotation |
| Contents | Initial secret | Client/service principal, encrypted part, session info | Principal, kvno, enctype, secret keys |
| User-specific or service-specific? | User | TGT user→TGS; ST client→target service | Service principal |
| Is it a TLS cert? | No | No | No |
| Can it authenticate web users? | Typically used to get a TGT | ST+Authenticator after verification | Only helps the server verify tickets |
| If compromised | User credential compromise | Ticket/cache hijack | Service impersonation/key compromise |
| Effect of changing user password? | Yes | Already-issued tickets may persist | Does **not** directly change service keytab |
| Effect of changing service key/kvno? | Not directly | STs for the service may be affected | Keytab must be synchronized |
| Automatically grants business permissions? | No | No | No |
| Inspection tool | Never log/dump | `klist`, `kvno` | `klist -kte` (metadata) |
| Cleared by local HttpSession logout? | No | Not by default | No |

**Practical consequence:** resetting alice's password will not fix a portal keytab with the wrong SPN/kvno, and updating portal's keytab will not wipe the browser's user password or TGT.

## 8. The Three Kerberos Exchanges

### 8.1. AS Exchange – Acquiring a TGT

~~~text
Client alice                    KDC Authentication Service
     |                                       |
     | AS-REQ / preauth per policy           |
     +-------------------------------------->|
     |                                       | verify client identity
     |                                       | create TGT and session key
     |<--------------------------------------+
     | AS-REP                                |
     | Store TGT + client-side key material  |
~~~

The TGT encrypted part typically uses the `krbtgt/REALM` key. The client does not decrypt the TGT with a password and hand it to an HTTP app. In a password-based AS exchange, the user secret/derived key decrypts the appropriate portion of the AS reply, not a service ticket.

### 8.2. TGS Exchange – Acquiring a Service Ticket

~~~text
Client with TGT                  KDC Ticket Granting Service
     |                                        |
     | TGS-REQ: HTTP/portal.example.org       |
     | includes TGT and authenticator         |
     +--------------------------------------->|
     |                                        | validate TGT
     |                                        | issue service ticket
     |<---------------------------------------+
     | TGS-REP: ST + client-side session key  |
~~~

The user is not prompted for a password in a normal TGS step. One TGT can request tickets for many target SPNs subject to trust and policy.

### 8.3. AP Exchange – Presenting the Ticket to the Service

~~~text
Browser with ST                      HTTP/portal service
     |                                        |
     | AP-REQ: service ticket + authenticator |
     +--------------------------------------->|
     |                                        | keytab -> service long-term key
     |                                        | decrypt ticket encrypted part
     |                                        | recover session key
     |                                        | check authenticator/replay/time
     |                                        | verified client principal
     |<---------------------------------------+
     | AP-REP if mutual auth required         |
~~~

The service typically **does not contact the KDC on every AP-REQ** to validate the ST by forwarding the ticket to the KDC. It uses its long-term key and local GSS ticket verification, alongside KDC policies, clocks, and realm configuration. Do not confuse this with **CAS Service Ticket validation**, which makes a back-channel call to CAS.

## 9. HTTP SPNEGO/Negotiate Carries the AP Exchange

HTTP Negotiate per RFC 4559:
1. A protected request lacks valid credentials.
2. The service may return **401 Unauthorized** with `WWW-Authenticate: Negotiate`.
3. Browser/SSPI/GSS-API acquires a service ticket for `HTTP/portal.example.org` and builds a token.
4. The browser sends `Authorization: Negotiate <Base64GssToken>`.
5. The Spring Security SPNEGO filter passes the token to the GSS ticket validator.
6. Ticket and Authenticator are verified; the trusted principal is extracted from the GSS context.
7. Spring creates Authentication and enforces UserDetails/authorization policy.

~~~http
GET /private HTTP/1.1
Host: portal.example.org
Authorization: Negotiate YIIB...example-opaque-token...
~~~

The header is illustrative only and does not contain a valid token.

### 9.1. Multiple Round Trips May Be Needed

The SPNEGO/GSS handshake can involve multiple 401/response tokens. A success response may also carry a final `WWW-Authenticate: Negotiate ...` for mutual authentication. Never hardcode an assumption of strictly one request and one response across all clients.

### 9.2. Is a Negotiate Header Always Kerberos?

**No.** SPNEGO negotiates a GSS mechanism. Some Windows environments can fall back to **NTLM**. If policy requires Kerberos-only, verify the negotiated mechanism and block unapproved fallbacks. Simply seeing the word Negotiate does not prove Kerberos v5 ran.

### 9.3. Kerberos Does Not Replace HTTPS

RFC 4559 emphasizes that HTTP Negotiate is only an authentication facility and does not automatically encrypt all HTTP headers, bodies, and cookies. Applications still require **HTTPS/TLS**, session management, CSRF protection, and business authorization.

## 10. Service Principal Name (SPN) Binds the Keytab to a Hostname

Example service principal:

~~~text
HTTP/portal.example.org@EXAMPLE.ORG
~~~

Components:
- `HTTP` is the service class.
- `portal.example.org` is the hostname the browser uses for the service.
- `EXAMPLE.ORG` is the Kerberos realm.

The browser requests a ticket for an SPN based on URL/DNS/SSPI policies. The web server's keytab must contain the principal/key matching that ticket. If the browser uses `portal.example.org` while the keytab only holds `HTTP/pod-001.internal`, GSS validation usually fails.

### 10.1. AD and SPN Mapping

In Microsoft Active Directory, an SPN is attached to a service or computer account. The KDC encrypts tickets with the key of the associated principal/account. If an SPN is duplicated or attached to the wrong account, tickets may be encrypted with a key that does not match the deployed keytab.

**Do not fix this by resetting the user's password.** Have an authorized admin check the SPN owner, keytab account, FQDN, canonicalization, and KDC logs.

### 10.2. Load Balancers, Reverse Proxies, and Kubernetes

When multiple Spring nodes serve the same public hostname:
- Browsers still request tickets for the public HTTP SPN.
- Acceptor nodes must share the appropriate key, or a proxy must terminate Negotiate in front of the backend per a defined architecture.
- Never use individual pod hostnames as the SPN if browsers do not visit those hosts directly.
- Secrets/kvno/enctype must be rolled out in sync across replicas.
- TLS termination at a proxy **differs** from the Kerberos service keytab; never trust an untrusted `X-Remote-User` header from a client.

## 11. kvno and enctype in a Keytab

### 11.1. What Is kvno?

**Key Version Number** distinguishes versions of a service principal's long-term key. For example:

| Entry | Principal | kvno | enctype |
|---|---|---:|---|
| 1 | HTTP/portal.example.org@EXAMPLE.ORG | 4 | aes256-cts-hmac-sha1-96 |
| 2 | HTTP/portal.example.org@EXAMPLE.ORG | 4 | aes128-cts-hmac-sha1-96 |
| 3 | HTTP/portal.example.org@EXAMPLE.ORG | 5 | aes256-cts-hmac-sha1-96 |

This is an **illustrative table**, containing no secret key bytes. Having multiple kvnos coexist can help during rotation if the realm/service platform supports it.

### 11.2. When a Keytab Is Stale

Suppose the KDC issues an ST encrypted with a new service long-term key kvno 5, while the server still runs keytab kvno 4. The server lacks the matching long-term key to decrypt the ticket. The user still has the right password and a valid TGT, yet the browser gets 401 when the app verifies the ticket.

Compare:
- Exact principal.
- kvno.
- Enctypes supported by KDC/client/server.
- Whether the key material matches the right account/realm.
- Time and clock skew.
- Whether all nodes run synchronized versions.

Never re-enable weak DES/RC4 arbitrarily just to "make tickets work"; follow security policy and compatibility plans.

### 11.3. Does a Keytab Expire Like a Service Ticket?

No. A keytab stores long-term keys and normally has no expiration field like `Ticket.endtime`. Saying a "keytab expired" usually means the key rotated, the kvno is stale, the account was disabled, or enctype/SPN mismatched. Diagnose the real root cause.

## 12. Practical Commands with MIT Kerberos

Run in an **authorized environment** and never paste ticket/keytab contents publicly.

### 12.1. Viewing the User Credential Cache

~~~bash
klist
~~~

You can see the client principal and TGT `krbtgt/EXAMPLE.ORG@EXAMPLE.ORG`, plus acquired STs such as `HTTP/portal.example.org@EXAMPLE.ORG`. Do not confuse this with a keytab.

### 12.2. Obtaining a User TGT in a Test Environment

~~~bash
kinit alice@EXAMPLE.ORG
klist
~~~

`kinit` performs the configured initial authentication method and may prompt for a password. This is the **initiator** side. Never use this user password to configure a Spring web acceptor.

### 12.3. Requesting a Ticket for a Specific Service

~~~bash
kvno HTTP/portal.example.org@EXAMPLE.ORG
~~~

This command normally requires a valid TGT and KDC reachability, then displays the kvno of the issued ticket. There is no fixed stdout for real servers; values depend on the KDC.

### 12.4. Listing Keytab Metadata

~~~bash
klist -kte /run/secrets/portal-http.keytab
~~~

The output lists principal/kvno/timestamp/enctype entries per MIT Kerberos version. It does not print secret bytes, yet realm/host metadata remains internal infrastructure info.

### 12.5. Using a Keytab to Acquire a TGT (Only When Truly Needed)

~~~bash
kinit -k -t /run/secrets/portal-http.keytab HTTP/portal.example.org@EXAMPLE.ORG
~~~

This proves a keytab **can serve as a credential for a principal**, not solely as an acceptor file. It is not required for a pure SPNEGO HTTP acceptor; never run it on production services outside approved procedures.

### 12.6. Destroying a User Ticket Cache

~~~bash
kdestroy
~~~

This deletes the credential cache in the configured scope. It **does not reset the user password, delete the server keytab, or log out all Spring HttpSessions across the system**.

### 12.7. Creating or Rotating Keytabs Requires KDC Admin Privileges

In MIT Kerberos, admin operations like `kadmin ktadd` can extract keys into a keytab. **Many ktadd configurations randomize service keys by default**, incrementing the kvno and invalidating keytabs still used on other servers. Change control is mandatory; never run risky admin commands directly on a production realm. In AD, tools such as `ktpass` can likewise alter account/service keys if invoked with the wrong flags.

## 13. Java 17 JAAS: Service Acceptor Using a Keytab

Java 17 includes `com.sun.security.auth.module.Krb5LoginModule`.

Common options for a pure acceptor:
- `useKeyTab=true`: load keys from the keytab.
- `keyTab="/run/secrets/portal-http.keytab"`: path to the secret file.
- `storeKey=true`: store the keytab/keys in the JAAS Subject private credentials.
- `principal="HTTP/portal.example.org@EXAMPLE.ORG"`: expected principal.
- `isInitiator=false`: accept GSS contexts rather than performing an AS exchange to obtain a client TGT.
- `doNotPrompt=true`: never fall back to interactive password prompts.
- `useTicketCache=false` when a pure acceptor does not use a client ticket cache.

Example **JAAS config fragment**:

~~~text
KerberosAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/portal-http.keytab"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    principal="HTTP/portal.example.org@EXAMPLE.ORG";
};
~~~

This is JAAS file syntax so a LoginContext can reference the `KerberosAcceptor` entry. When using Spring Security Kerberos's `SunJaasKerberosTicketValidator`, the library can configure JAAS internally; do not assume this file is read automatically without proper integration wiring.

### 13.1. JVM krb5 Config

~~~bash
java -Djava.security.krb5.conf=/etc/krb5.conf -jar portal.jar
~~~

This is an illustrative command requiring a real JAR, KDC/DNS/realm config, and mounted secrets. Setting the system property alone does not enable Spring Security Kerberos.

## 14. Which Classes Does Spring Security Kerberos/SPNEGO Use?

| Class | Role |
|---|---|
| `SpnegoEntryPoint` | Returns HTTP 401/Negotiate challenge when authentication is needed |
| `SpnegoAuthenticationProcessingFilter` | Reads Authorization: Negotiate and passes the token to AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Validates service ticket/SPNEGO token and loads UserDetails |
| `SunJaasKerberosTicketValidator` | JAAS/GSS-based ticket validator using service principal/keytab |
| `UserDetailsService` | Looks up local account and app permissions from verified Kerberos principal |
| `GrantedAuthority` | Mapped application permission, not pre-granted by the keytab |
| `SecurityContext` | Spring's post-validation authentication session |
| `SecurityFilterChain` | Filters, entry point, and authorization rules |

**Principle:** Spring receives a verified Kerberos username from the provider. The KDC/service ticket **does not automatically grant ROLE_ADMIN** or permission to read HR data. The application must map permissions per directory/DB/tenant policy.

## 15. Java Spring Security SPNEGO Integration Sample

The example below is a **configuration class** for Spring Security Servlet and a matching Spring Security Kerberos release, syntactically valid Java that **cannot run via plain javac** because it requires Spring dependencies, a KDC, an SPN, a real keytab, and a web app.

File `src/main/java/com/example/security/SpnegoSecurityConfig.java`:

~~~java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class SpnegoSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator() {
        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.example.org@EXAMPLE.ORG");
        validator.setKeyTabLocation(
                new FileSystemResource("/run/secrets/portal-http.keytab"));
        return validator;
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Demo: production needs a directory/database and tenant policy.
        return username -> {
            if (!"alice@EXAMPLE.ORG".equals(username)) {
                throw new UsernameNotFoundException(
                        "Principal not provisioned");
            }
            return new User(
                    username,
                    "{noop}unused-for-spnego",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));
        };
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        AuthenticationManager manager = new ProviderManager(provider);

        // Local instance stays only in the Spring Security filter chain;
        // avoid accidental second auto-registration as a Servlet Filter bean.
        var spnegoFilter = new SpnegoAuthenticationProcessingFilter();
        spnegoFilter.setAuthenticationManager(manager);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationManager(manager)
            .addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

### 15.1. Explanation

- The SPN is **HTTP/public-hostname**, not a user principal.
- `SunJaasKerberosTicketValidator` takes the keytab path; the secret lives in a volume/secret manager, **never in source**.
- `SpnegoAuthenticationProcessingFilter` reads the token; `KerberosServiceAuthenticationProvider` performs validation and returns the authenticated principal.
- The demo `UserDetailsService` provisions only `alice@EXAMPLE.ORG`, rather than granting ROLE_READER to every user with a Kerberos ticket. In production, use DB/LDAP per business policy.
- The password literal on `UserDetails` is a structural placeholder for UserDetails; **it is never used to verify SPNEGO**, and there is no form login in the sample filter chain.
- Register the filter only inside **SecurityFilterChain**; avoid defining a `@Bean Filter` that Spring Boot would accidentally auto-register a second time in the servlet container.
- You must test filter order, Authentication persistence, session fixation, CSRF, and browser/realm compatibility for your Spring Security / Spring Security Kerberos version.
- The code is an **integration sample**, not a standalone runnable Spring Boot app because routes/@SpringBootApplication, dependency management, and a KDC are omitted.

### 15.2. Maven Dependencies Fragment

Place inside `<dependencies>` of a Spring Boot POM with a BOM/parent and compatible Kerberos module versions:

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
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
  </dependency>
</dependencies>
~~~

Do not assume a Spring Boot starter auto-configures Kerberos/keytab merely from these dependencies. Verify module versions, Java/Jakarta Servlet, Spring Security core, and release notes before deploying.

## 16. Standalone Java 17: Demonstrating That Tickets and Keytabs Are Not Interchangeable

The program below **compiles/runs on Java 17+ and uses no real secrets**. It simulates metadata checks (SPN and kvno) only, **performing no Kerberos cryptography**.

File `CredentialKindsDemo.java`:

~~~java
public class CredentialKindsDemo {

    enum Kind {
        USER_PASSWORD,
        TGT,
        SERVICE_TICKET,
        SERVICE_KEYTAB
    }

    record Ticket(String servicePrincipal, int kvno, boolean tgt) {
    }

    record KeytabEntry(String servicePrincipal, int kvno) {
    }

    static String purpose(Kind kind) {
        return switch (kind) {
            case USER_PASSWORD -> "INITIAL_USER_AUTH";
            case TGT -> "OBTAIN_SERVICE_TICKETS";
            case SERVICE_TICKET -> "ACCESS_ONE_SERVICE";
            case SERVICE_KEYTAB -> "VERIFY_FOR_SERVICE_PRINCIPAL";
        };
    }

    static boolean metadataMatch(Ticket t, KeytabEntry k) {
        return !t.tgt()
                && t.servicePrincipal().equals(k.servicePrincipal())
                && t.kvno() == k.kvno();
    }

    public static void main(String[] args) {
        for (Kind k : Kind.values()) {
            System.out.println(k + "=" + purpose(k));
        }

        var target = "HTTP/portal.example.org@EXAMPLE.ORG";
        var webTicket = new Ticket(target, 5, false);
        var tgt = new Ticket("krbtgt/EXAMPLE.ORG@EXAMPLE.ORG", 7, true);
        var currentKey = new KeytabEntry(target, 5);
        var oldKey = new KeytabEntry(target, 4);

        System.out.println("current=" +
                metadataMatch(webTicket, currentKey));
        System.out.println("stale=" +
                metadataMatch(webTicket, oldKey));
        System.out.println("tgtAsWeb=" +
                metadataMatch(tgt, currentKey));
    }
}
~~~

Commands:

~~~bash
javac CredentialKindsDemo.java
java CredentialKindsDemo
~~~

**Exact stdout:**

~~~text
USER_PASSWORD=INITIAL_USER_AUTH
TGT=OBTAIN_SERVICE_TICKETS
SERVICE_TICKET=ACCESS_ONE_SERVICE
SERVICE_KEYTAB=VERIFY_FOR_SERVICE_PRINCIPAL
current=true
stale=false
tgtAsWeb=false
~~~

**Explanation:**
- USER_PASSWORD represents the user's initial authentication step, without storing a password string.
- TGT is used strictly in the ticket-granting flow, not as a web service ticket.
- The service ticket matches the current principal/kvno in the simulation; the stale kvno fails.
- Real Kerberos verification **must verify** encrypted part integrity, authenticator/session key, replay cache, clock skew, realm/policy, enctype, and SPNEGO mechanism.
- `metadataMatch` is solely a **metadata exercise**; never use it as a production AuthenticationProvider.
- A real keytab can contain multiple kvnos/enctypes, so a single-entry example does not cover every production configuration.

## 17. Keytab Rotation, kvno, and Multi-Node Deployment

### 17.1. Why Does Rotation Cause 401?

The KDC issues an ST encrypted with the new service long-term key kvno 6, while the server still runs keytab kvno 5. The service lacks the matching key to process the ticket. The user's password is still valid and the TGT is still valid, yet the browser receives 401 when the app verifies.

Conversely, switching the server too early to only the new key while browsers still hold old-kvno STs can also fail depending on platform/ticket cache and overlap policy.

### 17.2. Safe Rotation Procedure

1. Identify the SPN, owning service account, and all hosts/pods/reverse proxies accepting Kerberos.
2. Record enctypes, old kvno, keytab file locations, and ticket lifetimes.
3. Align on the CAS/AD/MIT KDC (meaning the Kerberos KDC here, **not the CAS native protocol**) key rotation policy.
4. Generate the new keytab via an approved administrative workflow; verify account/SPN mapping.
5. If supported by the platform, maintain key overlap long enough for existing tickets to expire.
6. Deploy secrets via secret manager/volume strictly for the right service UID.
7. Verify JVM/GSS acceptor keytab reload behavior; a restart/reinitialization may be needed.
8. Test each node via the public hostname and a ticket using the active kvno/enctype.
9. Retire old keys per TTL/policy while ensuring application continuity.
10. If a keytab is exposed, execute incident response, revoke/rotate service keys, and assess ticket/key exposure.

### 17.3. Do Not Run ktadd Recklessly

A `kadmin ktadd` operation can **randomize the service long-term key**, increment kvno, and invalidate keytabs still active on other servers. Depending on the environment, an option to keep keys may exist, yet choosing flags/roles requires admin approval. Never run these admin commands as "a quick way to grab a test keytab" on a production realm.

## 18. Common Misconceptions in SPNEGO Deployment

### 18.1. Domain Login Succeeds, Yet Portal Returns 401

The browser may acquire the right ST while the web service keytab has the wrong SPN/kvno/enctype. **Do not try to fix it by resetting alice's password.** Check keytab, SPN mapping, DNS, and JVM file permissions.

### 18.2. Keytab Is Valid, Yet the Browser Sends No Token

The browser may lack a TGT, Integrated Windows Authentication policy may disallow Negotiate for that host, a proxy may block headers, or the KDC may be unreachable. Inspect `klist`, browser auth zone, SPN, 401 challenge, and network.

### 18.3. 401 Followed by 403

Kerberos validation succeeded, yet `UserDetailsService` found no local user/role or business permissions denied access. Principal authentication and authorization are two distinct steps.

### 18.4. A New TLS Certificate Will Not Fix a Keytab Error

The HTTPS certificate serves TLS; the service keytab holds Kerberos long-term keys. They are **different secrets**. Working HTTPS does not prove working SPNEGO ticket acceptance.

### 18.5. Local Logout Followed by Immediate Re-Login

Spring `/logout` clears HttpSession, yet the workstation TGT remains. The browser can acquire an ST and re-Negotiate immediately. This is SSO by design, not automatically a logout bug. If global logout is required, design a dedicated credential/session lifecycle workflow; local logout does not clear the OS Kerberos ticket cache.

### 18.6. SPNEGO Does Not Guarantee Kerberos

Windows HTTP Negotiate can fall back to NTLM. If the app requires Kerberos-only, verify the accepted mechanism and disable fallback per policy; never inspect only the header prefix.

### 18.7. Using the Service Keytab to Authenticate Outgoing Requests?

A portal calling a backend on a user's behalf may need Kerberos delegation/constrained delegation or a separate service principal. **Never copy an incoming Negotiate token to the backend**: that ticket targets portal, not the backend SPN. Never extract user passwords or TGTs from an incoming AP-REQ.

## 19. Troubleshooting by Symptom

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC cannot find SPN | Check SPN, FQDN, realm mapping |
| `KRB_AP_ERR_MODIFIED` | Wrong keytab/account key, duplicate SPN | Check SPN owner, kvno, enctypes |
| `KRB_AP_ERR_SKEW` | Clock skew between client/server/KDC | Sync NTP and check realm clock policy |
| `GSSException: No valid credentials` | Unreadable keytab file, wrong JAAS principal | Check path, owner/ACL, acceptor config |
| 401 without Negotiate header | Filter/entrypoint not triggered | Check SecurityFilterChain and 401 challenge |
| Browser sends no Authorization: Negotiate | No TGT/policy/browser block | Check OS credentials, browser auth config |
| Ticket request fails despite user holding TGT | Wrong SPN/realm/KDC routing | `kvno HTTP/...`, DNS/KDC |
| Token acceptance fails after rotation | Stale keytab/missing kvno/enctype | `klist -kte`, deployment timing |
| Only one node fails | Stale node keytab or missing secret mount | Inspect per node |
| Authentication passes, yet 403 | Missing UserDetails/role or resource policy | Check local account/authorities |
| User changes password, yet still SSOs | Existing TGT/ST not yet expired | Ticket/session lifecycle policy |
| Negotiate header is actually NTLM | SPNEGO mechanism fallback | Check security mechanism policy |
| SSL OK, yet Kerberos fails | TLS cert differs from Kerberos service key | Check matching keytab principal |
| Immediate re-login after local Spring logout | User's TGT remains in OS cache | Explain SSO/re-auth behavior |
| Raw Authorization token appears in logs | Proxy or app logged header | Scrub/mask logs and handle incident |
| Service starts, yet validator fails | Wrong realm config/time/DNS/file permissions | JAAS/GSS/KDC diagnostics |

**Layered debugging:** user initial auth → TGT cache → TGS-REQ for HTTP SPN → browser Negotiate → service keytab → GSS acceptor validation → Spring Authentication → UserDetails/authorization → business resource.

Never disable time/replay checks or accept unsigned/unvalidated tokens just to make login "work".

## 20. Protecting Keytabs, Ticket Caches, and User Passwords

### 20.1. User Password / Long-Term Key

- Never collect, store, or log user passwords in a Kerberos SPNEGO HTTP acceptor.
- Enforce domain/password/PKINIT/MFA policies and account lifecycle controls.
- When a password changes, evaluate existing live TGTs/STs.
- Never assume a user password can substitute for a keytab.

### 20.2. Ticket Cache

- Protect OS logon sessions and credential caches.
- Never send tickets/session keys via logs/chat/debug dumps.
- Enforce ticket lifetimes, replay defenses, and constrained delegation per policy.
- `kdestroy` clears only the local cache, not all Spring sessions.

### 20.3. Service Keytab

- Mount keytabs from secret storage with file ACLs restricted to the service UID.
- Never place them in source repos, public container images, artifacts, or docs.
- Avoid bundling unrelated service principals into a single keytab unnecessarily.
- Rotate keys with change control, kvno overlap, testing, and restart plans.
- Never use a domain administrator account as a web service principal.
- Treat a leaked keytab as a service long-term credential compromise.
- Never log raw keys or confuse keytabs with TLS certificates.

### 20.4. HTTP Application Security

- Always use HTTPS/TLS alongside Kerberos.
- Never drop CSRF protection on POST requests simply because SPNEGO is used.
- Check Spring session fixation, logout, and session persistence.
- Realm/tenant identity mapping must prevent a user from another realm from claiming a same-named account.
- Business permissions must rely on verified user + UserDetails + resource scope, not the keytab.
- Keep GSS replay/clock checks enabled.

## 21. Integration Testing with KDC and Spring

### 21.1. Positive Tests

| Test | Condition | Expectation |
|---|---|---|
| P1 | Client has valid TGT | Can request ST for an allowed SPN |
| P2 | ST matches SPN, valid service keytab | GSS accept succeeds |
| P3 | Valid Authenticator/time/replay | Returns verified principal |
| P4 | Principal has active account | Spring Authentication holds proper authorities |
| P5 | Resource authorization allows | HTTP 200 for authorized user |
| P6 | Public hostname via load balancer | ST for public HTTP SPN validates on every node |
| P7 | New keytab matches kvno/enctype | Service continues accepting valid tickets |
| P8 | Kerberos succeeds, yet business denies | 403 per policy |
| P9 | TGT remains after local logout | Browser can re-Negotiate per SSO policy |
| P10 | Production TLS enabled | HTTP data remains independently protected |

### 21.2. Negative Tests

| Test | Fault | Expectation |
|---|---|---|
| N1 | Ticket for another SPN | Reject |
| N2 | Keytab lacks key/service principal | Reject |
| N3 | Keytab kvno/enctype mismatch | Reject |
| N4 | Tampered AP-REQ | Reject |
| N5 | Replayed Authenticator | Reject per Kerberos replay policy |
| N6 | Client/server clock drift | Reject; fix NTP |
| N7 | Principal from disallowed realm/tenant | Grant no local roles |
| N8 | UserDetailsService has no provisioned user | Deny business login |
| N9 | SPNEGO falls back to unapproved NTLM | Fail policy |
| N10 | Keytab readable by another container | Security audit fail |
| N11 | ST/Negotiate token appears in logs | Privacy/security fail |
| N12 | Cookie/session logout mismatch | Verify local SSO behavior |
| N13 | New keytab deployed to only one node | Per-node regression detected |
| N14 | User password reset while old tickets remain | Assess separate revocation |
| N15 | Copying incoming Negotiate to another backend SPN | Reject; no audience bypass |
| N16 | HTTP POST missing CSRF token | Spring protects per policy |
| N17 | Valid TLS cert, wrong SPN | Kerberos still rejects |
| N18 | Compromised keytab file | Rotate/incident response; stop using old file |

Unit tests can mock Authentication to verify `@PreAuthorize`, yet **cannot replace integration tests using a KDC/browser/real signed Kerberos tickets**. The Java 17 example in section 16 demonstrates metadata only, not cryptography.

## 22. Go-Live Checklist

- [ ] Clearly distinguished user password, TGT, Service Ticket, session key, and service keytab.
- [ ] Spring SPNEGO acceptor never demands the user password.
- [ ] Browser holds Kerberos credentials and negotiates the right HTTP SPN.
- [ ] Service keytab contains the right principal, kvno, and enctype and is protected by a secret store.
- [ ] KDC/realm/DNS/clock/NTP are verified.
- [ ] Public hostname SPN and proxy/ingress routing are consistent.
- [ ] Keytab is absent from JARs, Git, public images, and logs.
- [ ] Key rotation is coordinated across all replicas, with overlap where appropriate.
- [ ] Spring Security filter/provider/validator match the target version and are registered only once.
- [ ] Spring UserDetailsService enforces account/role/tenant policy rather than granting admin to every principal.
- [ ] HTTPS/TLS and CSRF remain active.
- [ ] Negotiate/NTLM fallback is rejected unless explicitly permitted by security policy.
- [ ] Local logout is not assumed to delete the OS TGT or keytab.
- [ ] Tests cover wrong SPN, stale keytab, replay, clock skew, missing TGT, and wrong realm.
- [ ] Incident response runbooks cover keytab leaks and ticket cache compromise.
- [ ] Demo `metadataMatch` code is never used as a real Kerberos validator.

## 23. Review Questions

1. **What is the password used for?** It serves as the initial user authentication / long-term key source in password-based Kerberos.
2. **Does a Kerberos browser send the password to Spring?** No.
3. **What is a TGT?** A ticket used to request service tickets from the TGS.
4. **What is an ST?** A ticket issued by the KDC for a specific service principal.
5. **Which key protects the ticket?** The encrypted ticket part typically uses the target service's long-term key.
6. **What does a service keytab contain?** Service principal entries with long-term keys, kvno, and enctype.
7. **Does a keytab contain plaintext passwords?** No, yet it must be guarded like a high-value secret.
8. **Is the session key stored statically in the keytab?** No; the session key is scoped per ticket/context.
9. **What is the role of the Authenticator?** It proves the client possesses the session key and supports replay/freshness checks.
10. **What kind of ticket does HTTP SPNEGO send?** A service ticket for the HTTP SPN, not a raw TGT.
11. **What does an SPN typically look like?** `HTTP/portal.example.org@EXAMPLE.ORG`.
12. **When does kvno matter?** During service key rotation and when accepting encrypted ticket parts.
13. **How does a stale keytab manifest?** 401/GSS failures due to lacking a key with the matching kvno/enctype.
14. **How does klist differ from klist -kte?** One inspects the credential cache; the other inspects keytab metadata.
15. **Is kinit -k required for a web acceptor?** No, only when a service must act as an initiator or for specific checks.
16. **Does changing a user's password fix a keytab error?** No.
17. **Kerberos passes, yet Spring returns 403?** Authorization or role/account mapping may be denying access.
18. **Does an HTTPS certificate replace a keytab?** No.
19. **Is a Negotiate header guaranteed to be Kerberos?** No; another mechanism may have been negotiated.
20. **Does local logout expire the OS TGT?** Not by default.
21. **Can an incoming token be forwarded to call another backend?** Not directly—the target SPN differs; delegation requires its own mechanism.
22. **What should be done if a keytab is leaked?** Execute incident response, rotate service keys, and assess affected tickets/sessions.
23. **If a user has a TGT yet cannot access the web app, what should you inspect?** SPN, service ticket, keytab/kvno/enctype, GSS filter, and roles.

## 24. Official Technical References

- **RFC 4120 – The Kerberos Network Authentication Service (V5):** https://www.rfc-editor.org/rfc/rfc4120
- **RFC 4559 – SPNEGO-based Kerberos and NTLM HTTP Authentication:** https://www.rfc-editor.org/rfc/rfc4559
- **RFC 4178 – SPNEGO:** https://www.rfc-editor.org/rfc/rfc4178
- **RFC 4121 – Kerberos GSS-API mechanism:** https://www.rfc-editor.org/rfc/rfc4121
- **MIT Kerberos – Application servers and keytabs:** https://web.mit.edu/Kerberos/www/krb5-current/doc/krb_admins/appl_servers.html
- **MIT Kerberos – kinit:** https://web.mit.edu/Kerberos/www/krb5-current/doc/user/user_commands/kinit.html
- **MIT Kerberos – klist:** https://web.mit.edu/Kerberos/www/krb5-current/doc/user/user_commands/klist.html
- **MIT Kerberos – kvno:** https://web.mit.edu/Kerberos/www/krb5-current/doc/user/user_commands/kvno.html
- **MIT Kerberos – kadmin, ktadd:** https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/admin_commands/kadmin_local.html
- **Oracle Java SE 17 – Krb5LoginModule:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- **Spring Security – Spring Security Kerberos (Servlet):** https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- **Spring Security – KerberosServiceAuthenticationProvider JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- **Spring Security – SpnegoAuthenticationProcessingFilter JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html

**Summary:** The **password/initial user credential** authenticates the user to the KDC and acquires a TGT; a **Kerberos ticket** is issued by the KDC—a TGT requests tickets, while a Service Ticket + Authenticator proves the client to a specific SPN; a **service keytab** stores long-term keys so the web acceptor can verify tickets issued for it. The three differ in owner, lifecycle, scope, and leak impact. Spring Security grants access only after GSS verifies the ticket and the application's UserDetails/authorization accepts the user; TLS, CSRF, sessions, keytabs, and ticket caches must continue to be protected.
