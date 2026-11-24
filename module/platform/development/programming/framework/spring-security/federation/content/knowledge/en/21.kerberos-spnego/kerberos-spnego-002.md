# Realm, KDC, Principal, and Service Principal Name in Kerberos/SPNEGO

**Kerberos** is a network authentication protocol based on tickets, secret keys, and a trusted third party called the **Key Distribution Center (KDC)**. In a **Spring Security Kerberos + SPNEGO** integration, the browser typically obtains a service ticket from the KDC and sends it to the application via HTTP `Authorization: Negotiate ...`. The application only accepts the token when it can verify the ticket with the key of **the exact service**, usually stored in a **keytab**. To understand why a configuration works or fails, you must precisely grasp **realm, KDC, principal, and Service Principal Name (SPN)**.

An end-to-end example:

~~~text
Kerberos realm:           CORP.EXAMPLE
Domain/DNS zone:          corp.example
KDC (Windows DC):         dc01.corp.example
User principal:           lan@CORP.EXAMPLE
Service principal:        HTTP/portal.corp.example@CORP.EXAMPLE
AD SPN:                   HTTP/portal.corp.example
AD service account:       CORP\svc_portal
Browser public URL:       https://portal.corp.example/
Spring acceptor keytab:   /etc/security/keytabs/portal-http.keytab
~~~

**Crucial distinction:** **An SPN is not a URL, not a keytab filename, not a user's username, and not a KDC hostname.** An SPN is the identifier of a *service instance* that the KDC uses to locate the right service account/key. In AD, the SPN string is usually registered in the form `HTTP/portal.corp.example`; in a full Kerberos principal, the realm may be appended: `HTTP/portal.corp.example@CORP.EXAMPLE`.

This lesson belongs to the **Kerberos and SPNEGO** group, progressing from foundational concepts to AS/TGS/AP flows, identity/trust, Windows AD and MIT Kerberos configuration, Spring Security JavaConfig, keytab/KVNO/encryption types, reverse-proxy pitfalls, authorization protection, and testing. It includes a standalone **Java 17** program to illustrate SPN, hostname, and keytab matching logic while highlighting the limits of string-based checks.

## 1. Terminology Map

| Term | Role | Example | What It Is Not |
| --- | --- | --- | --- |
| **Realm** | Kerberos administrative space containing principals and KDC/keys | `CORP.EXAMPLE` | Not simply a DNS zone or Windows UPN suffix |
| **KDC** | Trusted component issuing TGTs and service tickets | `dc01.corp.example` | Not the Portal web server itself |
| **AS (Authentication Service)** | KDC component issuing TGTs after verifying the client | AS-REQ/AS-REP | Does not directly grant Spring roles |
| **TGS (Ticket Granting Service)** | KDC component issuing service tickets based on a TGT | TGS-REQ/TGS-REP | Not an HTTP callback |
| **Principal** | Identifier of a Kerberos user, service, or system component | `lan@CORP.EXAMPLE` | Not automatically synonymous with an email account |
| **Service principal** | Kerberos principal designated for a specific service | `HTTP/portal.corp.example@CORP.EXAMPLE` | Not every user's principal |
| **SPN** | Service identifier used by KDC/AD to look up an account/key | `HTTP/portal.corp.example` | Not a TLS certificate SAN |
| **TGT** | Ticket for the TGS, typically cached after user login | `krbtgt/CORP.EXAMPLE@CORP.EXAMPLE` | Do not send raw TGTs to Portal in browser SPNEGO |
| **Service ticket** | Ticket for the service `HTTP/portal.corp.example` | Wrapped inside a GSS/SPNEGO token | Not a JWT or SAML Assertion |
| **Keytab** | File containing key entries and principal/kvno/enctype for the acceptor | `portal-http.keytab` | Not a TLS truststore |
| **KVNO** | Key Version Number: the key version of a principal | `kvno=7` (illustrative) | Not an HTTP status code |
| **SPNEGO** | GSS-API mechanism for negotiating via `Negotiate` | HTTP 401 + Negotiate | Not a KDC or realm name |
| **AD service account** | AD object holding credentials/keys for a service SPN | `CORP\svc_portal` | Not necessarily the HTTP hostname |
| **UserDetailsService** | Spring lookup for local user/authorities after Kerberos check | `loadUserByUsername(...)` | Not a cryptographic service ticket verifier |

Three layers must be distinguished: **DNS** locates the host; **Kerberos SPN** identifies the service account; **HTTP/TLS** transports requests and protects the channel. When a browser visits HTTPS, the Kerberos HTTP service class **is still `HTTP/`**, not `HTTPS/`.

## 2. What Is a Realm?

A realm identifies the administrative domain of a Kerberos system. By convention, a realm is usually written in uppercase DNS-like style (`CORP.EXAMPLE`), whereas a DNS domain is lowercase (`corp.example`). In Windows Active Directory, an AD domain is typically tied to a Kerberos realm with the same spelling, though that **is not a mandatory identity across all systems**.

A realm encompasses:

- A set of user/service principals and their corresponding secret keys.
- One or more **KDCs** issuing tickets within the trust boundary.
- Login rules, authentication policies, ticket lifetimes/renewals, and encryption policies.
- Trust relationships needed to access services in other realms.
- DNS/KDC discovery configuration and hostname/domain-to-realm mappings.

Example:

~~~text
DNS domain:           corp.example
Kerberos realm:       CORP.EXAMPLE
KDC hosts:            dc01.corp.example, dc02.corp.example
User:                 lan@CORP.EXAMPLE
Service:              HTTP/portal.corp.example@CORP.EXAMPLE
Cross-realm partner:  PARTNER.EXAMPLE (only when proper trust exists)
~~~

**A user having the email `lan@partner.example` does not automatically mean their Kerberos realm is `PARTNER.EXAMPLE`.** Email, UPN, NetBIOS logon name, and Kerberos principal can be configured or mapped differently. The application must use the identity/realm verified by the Kerberos validator rather than inferring trust from an email domain.

### A Realm Is Not an Application Tenant

One Kerberos realm can serve multiple applications and multiple internal organizations. Conversely, a multi-tenant application can accept principals from multiple realms via trust/cross-realm mechanisms. **Kerberos proves a principal within a trust space**; deciding whether that person can access tenant A or data B remains the application's responsibility.

## 3. KDC, AS, and TGS: Same Center, Different Roles

The KDC provides two key logical services:

1. **AS (Authentication Service):** receives `AS-REQ`, authenticates the client per policy, and issues a **Ticket Granting Ticket (TGT)** along with appropriate key material. With AD, this can involve pre-authentication, smart card/PKINIT, and other policies rather than always being a password.
2. **TGS (Ticket Granting Service):** receives `TGS-REQ` protected by the TGT and an Authenticator, identifies the requested service principal, and issues a **service ticket** for that target.

~~~mermaid
sequenceDiagram
    participant U as Client/Browser
    participant KDC as KDC of CORP.EXAMPLE
    participant WEB as Spring Portal acceptor
    U->>KDC: AS-REQ (user principal / preauthentication)
    KDC-->>U: AS-REP + TGT for krbtgt/CORP.EXAMPLE
    U->>KDC: TGS-REQ for HTTP/portal.corp.example
    KDC->>KDC: Look up SPN → service account → key version/enctype
    KDC-->>U: TGS-REP + service ticket for HTTP/portal...
    U->>WEB: HTTP Authorization: Negotiate <GSS token>
    WEB->>WEB: SPNEGO/JGSS uses keytab to verify service ticket
    WEB-->>U: 200 or additional Negotiate token if mutual auth is needed
~~~

**AS and TGS do not have to be two physical machines**. In Active Directory, a Domain Controller typically performs the KDC role. In MIT Kerberos, multiple primary/secondary KDCs can run for the same realm. **Do not hardcode a single DC** if the organization uses DNS SRV/discovery/failover.

### A TGT Is Not a Ticket for Every Service

`krbtgt/CORP.EXAMPLE@CORP.EXAMPLE` is the ticket-granting-service principal. A TGT allows the client to request subsequent service tickets, whereas the web server `HTTP/portal.corp.example` requires **a service ticket carrying the matching service principal**. Never design a Spring app to accept a raw TGT as a bearer token in place of a service ticket.

A service ticket typically contains a portion encrypted with the **long-term key of the service principal**. Therefore, Portal must possess the proper keytab/credential of the service account — if the key is wrong, the ticket cannot be processed by the acceptor.

## 4. Principal: Identifier for Users, Services, and TGS

Under Kerberos V5 (RFC 4120), a principal name consists of name components and a realm. Common human-readable representations:

~~~text
user principal:
  lan@CORP.EXAMPLE

service principal with host instance:
  HTTP/portal.corp.example@CORP.EXAMPLE

another service principal:
  host/node01.corp.example@CORP.EXAMPLE

TGS principal:
  krbtgt/CORP.EXAMPLE@CORP.EXAMPLE
~~~

Delimiters:

- `@REALM`: binds the name to a specific Kerberos realm.
- `/instance`: adds an instance component, typically a hostname for a network service.
- `HTTP/`: service class for HTTP authentication, even when the URL runs over HTTPS.
- `krbtgt/`: TGS principal, not an HTTP website.

### How Do a User Principal and a Service Principal Name Differ?

| Type | Subject | Example | Key / Mechanism |
| --- | --- | --- | --- |
| User principal | End user | `lan@CORP.EXAMPLE` | Client holds TGT from AS, managed by OS/credential cache |
| HTTP service principal | Web service | `HTTP/portal.corp.example@CORP.EXAMPLE` | App/acceptor's keytab/service account |
| TGS principal | Ticket-granting service | `krbtgt/CORP.EXAMPLE@CORP.EXAMPLE` | KDC and realm hold the key protecting TGTs |
| Computer/host principal | Machine/host service | `host/node01.corp.example@CORP.EXAMPLE` | Machine/service credential per environment |

**A principal does not inherently carry roles.** Even if the KDC confirms `lan@CORP.EXAMPLE`, Spring must still look up the local account and authorities; a username that looks like `admin` or shares a `service-account` name grants no privileges on its own.

### KerberosPrincipal in Java 17

The JDK provides `javax.security.auth.kerberos.KerberosPrincipal` with constants `KRB_NT_PRINCIPAL`, `KRB_NT_SRV_HST`, and getters such as `getName()`, `getRealm()`, and `getNameType()`. This is an **identity representation object**, not a network login or ticket verification API:

~~~java
KerberosPrincipal user = new KerberosPrincipal(
        "lan@CORP.EXAMPLE",
        KerberosPrincipal.KRB_NT_PRINCIPAL);

KerberosPrincipal service = new KerberosPrincipal(
        "HTTP/portal.corp.example@CORP.EXAMPLE",
        KerberosPrincipal.KRB_NT_SRV_HST);
~~~

You must import `javax.security.auth.kerberos.KerberosPrincipal`. This snippet distinguishes name types; **a successful constructor call does not prove the principal exists in the KDC** or that a keytab contains the matching key. Never inspect `getRealm()` and allow every principal in that realm admin access.

## 5. SPN: The Service's Logical Address for Kerberos

In Active Directory, an SPN is registered on an **account object**, typically a computer account or service account. The KDC uses the SPN to locate the key of the account backing the service. For a website:

~~~text
Browser URL:
https://portal.corp.example/reports

Service class:
HTTP

Browser target host:
portal.corp.example

Requested SPN:
HTTP/portal.corp.example

Corresponding Kerberos principal (common representation):
HTTP/portal.corp.example@CORP.EXAMPLE

AD account owning SPN:
CORP\svc_portal
~~~

**The relationship that must hold:** the browser requests `HTTP/portal.corp.example` → the KDC finds the SPN registered on the right account → the KDC encrypts the ticket with that account's key → the Spring acceptor has a valid keytab for the account/principal → verifies the token → looks up user details/roles.

**A wrong SPN causes two primary failure modes**:

1. **The KDC finds none or too many owners:** `KDC_ERR_S_PRINCIPAL_UNKNOWN` or `KDC_ERR_PRINCIPAL_NOT_UNIQUE` depending on the environment.
2. **The KDC issues a ticket, but Spring cannot decrypt/accept it:** `KRB_AP_ERR_MODIFIED` or a Kerberos integrity/decryption failure, usually caused by a wrong keytab, changed account password, mismatched KVNO/enctype, or an SPN pointing to the wrong account.

An SPN is not an HTTP path: `HTTP/portal.corp.example` is a principal; `/login` or `/api/reports` are normally **not** part of the SPN. HTTPS URL paths, queries, and fragments are not used to select the SPN in typical HTTP Kerberos use cases.

## 6. SPN Syntax and Naming Conventions in Windows AD

Microsoft documentation describes a general syntax that can include service class, host, port, and service name, such as `serviceclass/host:port/servicename` in special cases. For **HTTP Negotiate**, the standard pattern remains `HTTP/fqdn`.

~~~text
Common HTTP SPN:
  HTTP/portal.corp.example

Another alias:
  HTTP/reports.corp.example

Service principal with realm:
  HTTP/portal.corp.example@CORP.EXAMPLE

A non-HTTP example:
  MSSQLSvc/sql01.corp.example:1433
~~~

**Do not automatically append a port to an HTTP SPN** just because the URL uses `:8443`. HTTP SPN port handling depends on client/Windows settings/service conventions; verify the exact SPN the client requests via `klist`/traces instead of guessing. Do not register `HTTPS/portal...` simply because the site uses TLS.

**Case sensitivity:** service class/hostname matching in AD follows its own rules; however, Kerberos realms and principals/keytabs are stored and matched with specific casing. Use a consistent casing convention, verify actual credentials, and do not blindly lowercase everything assuming realms/keys are equivalent across all implementations.

### An SPN Must Belong to Exactly One Account

Microsoft recommends `setspn -S` instead of `-A` because `-S` checks for duplicate SPNs before adding. Duplicate SPNs across multiple AD accounts can prevent the KDC from determining the right key or cause tickets to be encrypted for a different account than Portal's keytab. Check SPNs across the relevant domain/forest scope before and after registration.

## 7. Looking Up SPNs in Active Directory

On a Windows machine with RSAT/AD tools installed and appropriate permissions:

~~~powershell
# Query a specific SPN (read-only):
setspn -Q HTTP/portal.corp.example

# List SPNs on a service account (read-only):
setspn -L CORP\svc_portal

# Find duplicate SPNs (read-only):
setspn -X

# Query forest-wide scope when needed:
setspn -F -Q HTTP/portal.corp.example
~~~

These are **diagnostic commands**, have no fixed stdout, and should only be run in a real authorized AD domain/forest. If an SPN is duplicated, identify **the true owning account, which service uses it, and the impact on other applications** before changing anything. Do not delete every SPN that "looks like Portal" because another machine/application may depend on it.

### Registering an SPN (AD-Modifying Operation, Authorized Operators Only)

~~~powershell
# Illustrative servicePrincipalName modification in AD:
setspn -S HTTP/portal.corp.example CORP\svc_portal
~~~

Run this only after the service account has been created/approved, duplicate checks have passed, and a change request is in place. This is **not a command to run on every node** of a Kubernetes/VM cluster. A **public virtual hostname** usually maps to a single SPN with a clear owning account; backend replicas can use the corresponding approved credentials/keytab per policy.

**Never run `setspn -A` unconditionally** because it can skip duplicate checks. Migrating from an old account to a new one requires a cutover, keytab rollover, and rollback plan; do not arbitrarily move a production SPN just because of a single `KRB_AP_ERR_MODIFIED`.

### UPN, sAMAccountName, and SPN

AD uses distinct attributes:

- **sAMAccountName:** e.g., `svc_portal`, the legacy account name in the domain.
- **userPrincipalName (UPN):** may look like `svc_portal@corp.example` or another suffix.
- **servicePrincipalName:** values such as `HTTP/portal.corp.example`, used to locate the account for service tickets.

**Do not treat the service account's UPN as its SPN**. The KDC needs the proper `servicePrincipalName` for the HTTP service; an account having a matching UPN does not automatically register `HTTP/portal...`.

## 8. Principal, SPN, DNS, and Browser Target: The Binding Chain

Configuration checks can be viewed as a chain:

~~~text
User opens:
  https://portal.corp.example/

Browser requests Kerberos service ticket for:
  HTTP/portal.corp.example

AD servicePrincipalName entry:
  HTTP/portal.corp.example -> CORP\svc_portal

KDC service ticket encrypted under:
  key of svc_portal, selected KVNO/enctype

Spring acceptor:
  servicePrincipal = HTTP/portal.corp.example@CORP.EXAMPLE
  keytab principal/key(s) for svc_portal

Result:
  valid GSS Kerberos security context -> user principal
~~~

**If a single link fails to match, single sign-on can fail even when DNS, TLS, and LDAP all work**. For example, load balancer `portal.corp.example` forwards to `node01.corp.example`, while Spring uses keytab `HTTP/node01.corp.example@CORP.EXAMPLE`. The browser still requests a ticket for `HTTP/portal.corp.example`, so the node may fail to accept the ticket.

### DNS CNAME / Alias

A DNS alias helps the browser find an IP/endpoint, but **does not automatically create an SPN or grant access to the target account's key**. Depending on OS/SSPI/GSS settings, the client may pick the SPN from the URL host or the canonicalized DNS name. In many setups, the browser visits the public hostname and requests `HTTP/public-host`.

If switching from `portal.corp.example` to `reports.corp.example`, verify in practice:

1. Which SPN the browser requests (`HTTP/portal...` or `HTTP/reports...`).
2. Whether AD has that SPN registered on the right account.
3. Whether the keytab/acceptor contains the corresponding principal/keys.
4. Whether the TLS certificate SAN covers the new public hostname.
5. Whether the reverse proxy/virtual host forwards the Negotiate header properly.

**Do not assume a CNAME always resolves the SPN to the canonical target** or vice versa; DNS canonicalization varies by client. Microsoft provides specific guidance for Entra Application Proxy Kerberos Constrained Delegation (KCD) recommending A records over CNAMEs in certain cases; that is **guidance for that architecture**, not a universal DNS/Kerberos rule.

## 9. Keytab: Why the Service Must Hold the Exact Key

A **keytab** is a file storing principals and key material so a service does not need interactive password entry every time it accepts a Kerberos ticket. When the KDC issues a service ticket for `HTTP/portal.corp.example`, part of the ticket is encrypted with the service account's long-term key. The Java GSS/JAAS acceptor uses the key from the keytab to decrypt/verify and establish the security context.

A single keytab can hold multiple entries for:

- One or more managed principals.
- Different encryption types (e.g., AES256/AES128) per policy.
- Multiple key version numbers (**KVNO**) during key rotation.

**Keytabs are highly sensitive**: anyone who copies one can potentially impersonate the service, accept Kerberos tickets, or perform key-based actions within the protocol scope. Never commit keytabs to Git, public container images, or unprotected artifact servers. Prefer managed secret volumes/keystores, least-privilege permissions, rotation, and access auditing.

### KVNO and Key Rotation

When the service account's password/secret changes, the KDC may issue tickets with a **new KVNO**. If Portal's keytab still holds the old key, the Spring acceptor cannot decrypt the ticket. Some environments maintain an overlap period for keys/versions so service is not disrupted during cutover, though this must be managed transparently.

To inspect on Linux with the appropriate tool:

~~~bash
# List keytab metadata, WITHOUT printing key material:
klist -kte /etc/security/keytabs/portal-http.keytab
~~~

Depending on the implementation, `-k` displays the keytab, `-t` timestamps, and `-e` encryption types. Do not post full output if it contains sensitive principal names. Check the principal, KVNO, and enctype against the standardized KDC/service account.

**Do not change the service account password or re-run keytab exporters repeatedly without coordination**: some tools (such as `ktpass`) can alter the key/KVNO and break all app nodes still using the old keytab. Creating/rotating keytabs must be handled by the AD/PKI/IAM owner per runbook.

## 10. How Do MIT Kerberos and Windows AD Differ in Administration?

| Task | Typical MIT Kerberos | Typical Active Directory |
| --- | --- | --- |
| Configure realm/KDC | `/etc/krb5.conf`, DNS SRV | Domain join, DC/KDC discovery, optional krb5.conf on Linux |
| Create service principal | `kadmin`, `addprinc` per policy | Create service account/computer account and attach SPN |
| Issue keytab | `ktadd` per MIT workflow | AD-managed keytab export/ktpass/gMSA per architecture |
| Query principals | `kadmin getprinc` (requires privileges) | `setspn -Q/-L` |
| User tickets | `kinit`, `klist` | Windows `klist`, logon cache, or MIT kinit |
| Service ticket | `kvno HTTP/host` | Windows `klist get HTTP/host` or browser negotiation |
| KDC | krb5kdc/kadmind per topology | Active Directory Domain Controllers |

A Windows **gMSA** is useful when a service runs in a Windows environment supporting automatic password management. For Linux/Spring containers using a keytab, you must design proper identity/secret distribution and rotation; **do not assume a Windows gMSA automatically produces a Linux-usable keytab**.

**The standard KDC port is TCP/UDP 88**. Blocking DNS/DC/KDC at the firewall can prevent the browser from acquiring a service ticket. Registering the right SPN without KDC reachability still prevents SSO.

## 11. Configuring krb5.conf with Realm and KDC

A Linux/JDK example using MIT-style configuration:

~~~ini
[libdefaults]
    default_realm = CORP.EXAMPLE
    dns_lookup_realm = false
    dns_lookup_kdc = true
    rdns = false

[realms]
    CORP.EXAMPLE = {
        kdc = dc01.corp.example
        kdc = dc02.corp.example
    }

[domain_realm]
    .corp.example = CORP.EXAMPLE
    corp.example = CORP.EXAMPLE
~~~

Meaning:

- `default_realm`: default realm when no explicit `@REALM` is given.
- `kdc`: KDC hosts for the realm; DNS SRV may be used if policy permits.
- `dns_lookup_kdc`: enables KDC discovery via DNS depending on implementation.
- `rdns=false`: reduces reliance on reverse DNS lookups in many client configs, though it does not replace hostname/SPN determination across the entire browser stack.
- `[domain_realm]`: maps DNS domains/hostnames to the corresponding realm.

**These hosts are illustrative only**. Do not use `CORP.EXAMPLE` as a real production realm if your domain differs. KDC discovery differs across Linux MIT Kerberos, Windows LSA, and Java; test on the actual OS/JVM/browser.

### How Does Java 17 Locate the KDC/Realm?

Oracle Java 17 supports:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
~~~

Or both JVM properties together:

~~~text
-Djava.security.krb5.realm=CORP.EXAMPLE
-Djava.security.krb5.kdc=dc01.corp.example
~~~

**If you set either `java.security.krb5.realm` or `java.security.krb5.kdc`, you must set both**. Oracle notes that relying solely on these two properties may not provide sufficient mappings for **cross-realm**, so when multiple trusted realms exist, an appropriate `krb5.conf` is still needed.

The configuration path may be loaded/cached by the JVM when Kerberos classes initialize; do not assume editing the file immediately updates every running JVM pod. A controlled restart/reinitialization per runbook may be needed. Never read realm/KDC from an HTTP request and mutate JVM global properties at runtime.

## 12. Browser SPNEGO: WWW-Authenticate and Authorization

SPNEGO (Simple and Protected GSS-API Negotiation Mechanism) negotiates security mechanisms within GSS-API. Over HTTP, the flow is typically:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

A browser (if configured to trust the site for Integrated Authentication) obtains or reuses a service ticket and then sends:

~~~http
GET /private HTTP/1.1
Host: portal.corp.example
Authorization: Negotiate <base64-encoded-GSS-token>
~~~

Spring Security processes the GSS token and does not read a user password from the header. In an AD environment, Windows SSPI/browsers may **fall back to NTLM** when Kerberos fails, depending on client/server policy. Therefore:

**`Authorization: Negotiate` does not by itself prove that a Kerberos ticket was used.** If policy requires Kerberos mutual authentication or rejects NTLM, you must inspect the negotiated mechanism and configure fallback rejection per security policy. Do not treat every `Negotiate` token as carrying a valid Kerberos service ticket.

### Browsers Do Not Automatically Send Negotiate to Every Internet Host

Windows/Edge/Chrome/Firefox enforce policies for intranet/allowed authentication servers. Depending on the OS and browser management:

- The site must be in the intranet zone/allowlist for Integrated Authentication.
- The browser must have a valid credential cache/TGT.
- Hostname/SPN resolution must match.
- Proxies must not strip `WWW-Authenticate` or `Authorization` headers.
- HTTPS/TLS and cookies/sessions still require protection per threat model.
- For cross-origin calls, do not assume JavaScript fetch/XHR automatically sends Negotiate; CORS/credentials/browser policies are a separate concern.

Do not force every browser or Internet user to use Kerberos. Typically SPNEGO serves internal networks/managed devices, with a policy-approved login fallback for other clients.

## 13. Spring Security Kerberos: Components in Their Proper Roles

The **Spring Security Kerberos** documentation illustrates:

| Component | Function |
| --- | --- |
| `SpnegoEntryPoint` | Returns HTTP 401 and `WWW-Authenticate: Negotiate` or redirects to a fallback page per configuration |
| `SpnegoAuthenticationProcessingFilter` | Reads `Authorization: Negotiate ...`, creates a request token, and passes it to AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Authenticates the **service ticket/SPNEGO token** for an HTTP acceptor |
| `SunJaasKerberosTicketValidator` | Uses Java JAAS/JGSS and **servicePrincipal/keytab** to verify tickets |
| `KerberosAuthenticationProvider` | Provider for Kerberos username/password authentication (a different use case from SPNEGO service tickets) |
| `KerberosTicketValidator` | Contract for verifying Kerberos/GSS tokens |
| `UserDetailsService` | Loads user attributes and Spring `GrantedAuthorities` after the ticket is verified |
| `SecurityFilterChain` / `HttpSecurity` | Attaches entry point, filter, and authorization rules |

**Two commonly confused AuthenticationProviders:** `KerberosServiceAuthenticationProvider` is for **browser SPNEGO service tickets**, whereas `KerberosAuthenticationProvider` uses a `KerberosClient` in a Kerberos username/password flow. Do not wire the second provider to handle `Authorization: Negotiate` expecting it to decrypt tokens with a keytab.

In Spring Security Kerberos 7.1.x, module coordinates changed compared to older Spring Security Kerberos 2.x articles. Check the actual version and dependency tree rather than copying Maven snippets from an old blog post and overriding the Spring Security BOM.

## 14. Spring Security JavaConfig Accepting SPNEGO

This is an **integration example for a Spring Security Servlet project**, requiring the appropriate Kerberos dependencies, real principal/keytab, Spring MVC/Servlet, and a local UserDetailsService. **It cannot run standalone with `javac`**.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosTicketValidator;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class SpnegoKerberosSecurityConfig {

    @Bean
    KerberosTicketValidator kerberosTicketValidator(
            @Value("${app.kerberos.service-principal}") String principal,
            @Value("${app.kerberos.keytab-location}") Resource keytab) {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(keytab);
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            KerberosTicketValidator validator,
            UserDetailsService users) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    AuthenticationManager kerberosAuthenticationManager(
            KerberosServiceAuthenticationProvider provider) {
        return new ProviderManager(provider);
    }

    @Bean
    SpnegoAuthenticationProcessingFilter spnegoFilter(
            AuthenticationManager kerberosAuthenticationManager) {
        SpnegoAuthenticationProcessingFilter filter =
                new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(kerberosAuthenticationManager);
        return filter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SpnegoAuthenticationProcessingFilter spnegoFilter)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(
                    new SpnegoEntryPoint("/login")))
            .addFilterBefore(
                    spnegoFilter, BasicAuthenticationFilter.class);
        return http.build();
    }
}
~~~

**Requirements to run:**

- `UserDetailsService` must be a real bean mapping the Kerberos principal to a local account/authorities, not using a service account as a shared user.
- `/login` must have a proper fallback flow if `SpnegoEntryPoint("/login")` is configured; otherwise it can cause a redirect loop or a missing page.
- This is an integration-point sample; authorization, logout, session strategy, CSRF, form login, or multi-chain filter matching must be completed for the application.
- Never leave `setDebug(true)` enabled indefinitely in production; GSS/JAAS debugging can expose principals, infrastructure metadata, and sensitive details.
- Beans/classes must match the resolved Spring Security Kerberos/JDK version; do not mix Spring Security 7 modules with Spring Security 5-era APIs.

**Consequence of a wrong principal:** `SunJaasKerberosTicketValidator` needs a service principal/keytab matching the **target ticket**. If the browser requests `HTTP/portal.corp.example` while the validator expects `HTTP/node01.corp.example@CORP.EXAMPLE`, the problem cannot be fixed by adding Spring roles or changing `UserDetailsService`.

### Corresponding application.yml

~~~yaml
app:
  kerberos:
    service-principal: "HTTP/portal.corp.example@CORP.EXAMPLE"
    keytab-location: "file:/etc/security/keytabs/portal-http.keytab"
~~~

The configuration above only binds two `@Value` properties; it does **not** create the keytab or register the SPN. Some environments/versions use a principal in the form `HTTP/portal.corp.example` and fall back to the default realm; to avoid ambiguity, prefer the full principal when supported by the keytab/JGSS implementation and verified with the KDC.

### Spring Security Kerberos Dependencies by Version

Example for **Spring Security Kerberos 7.1.x** from the Spring reference (dependency versions managed by the BOM):

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
  </dependency>
</dependencies>
~~~

This is a **Maven fragment**, not a complete pom.xml. The 7.1.x line is documented by Spring for JDK 17 and the corresponding Spring Security/Framework versions. In a Spring Boot 3/Security 6 system, coordinates/versions from the older Kerberos line may be required; **do not change groupId or bump versions by guesswork**.

## 15. Local User Mapping After Kerberos Authentication

A Kerberos ticket verifying `lan@CORP.EXAMPLE` **does not automatically prove Lan is an admin**. `KerberosServiceAuthenticationProvider` uses `UserDetailsService` to load authorities after verification. Policy example:

~~~text
Verified Kerberos principal:
  lan@CORP.EXAMPLE

Identity-link store:
  (trustedRealm=CORP.EXAMPLE, principal=lan) -> localUserId=u-1007

Local status:
  ACTIVE

Local roles:
  ROLE_REPORT_VIEWER

Request to /admin:
  DENY unless local grant exists
~~~

A multi-realm system might have `lan@CORP.EXAMPLE` and `lan@PARTNER.EXAMPLE` belonging to two different people. **Never take only the part before `@` and merge accounts automatically.** The identity-link key should include the realm (or an immutable identifier guaranteed by the directory/trust contract).

Safe authorization steps:

1. Verify the ticket with the right keytab and proper KDC/trust semantics.
2. Record the authenticated principal and trusted realm.
3. Check whether the local user is enabled/locked/offboarded.
4. Map the principal (with realm) to an internal identity per policy.
5. Grant only approved authorities, not based on account names or unverified `memberOf` values.
6. Apply tenant/object-level authorization on every request.
7. Manage session lifetime, role refresh, and local logout as required.

**SPNEGO authentication does not replace HTTPS/TLS.** Kerberos proves the principal, while HTTPS protects HTTP payloads/cookies and defends against downgrade/MITM per the threat model.

## 16. Browser → Reverse Proxy → Spring: Public SPN and Backend Keytab

Assume the architecture:

~~~text
User Browser
   |
   | https://portal.corp.example/
   v
HTTPS Load Balancer (public virtual host)
   |
   +----> Spring pod A: portal-app-a.internal:8080
   |
   +----> Spring pod B: portal-app-b.internal:8080

Public SPN:
  HTTP/portal.corp.example

AD SPN owner:
  CORP\svc_portal

Spring acceptor principal:
  HTTP/portal.corp.example@CORP.EXAMPLE
~~~

**The browser usually requests a ticket for the URL's public hostname, not the pod name**. Therefore, backend apps must hold credentials that accept the **public HTTP service principal**. When multiple replicas share a service keytab, secure secret distribution and rotation are mandatory; a keytab is not public config that can be baked into an image.

A reverse proxy must pass the HTTP `Authorization: Negotiate` header untouched to the backend if it acts solely as pass-through. If the reverse proxy **terminates Kerberos itself** and builds an identity assertion/header to forward to the backend, **the trust boundary has moved**: the Spring backend is no longer the Kerberos acceptor; you must authenticate the ingress/proxy channel and block Internet clients from forging identity headers like `X-Remote-User`. Never read an unverified username header from a proxy and treat it as a Kerberos login.

### DNS Aliases / Multi-URL

If the same application serves both `portal.corp.example` and `reports.corp.example`, each hostname browsers actually visit may need its own SPN registered on the proper owning account. A keytab/acceptor may require multiple principals or host-specific credentials depending on the framework; do not assume a keytab with a single HTTP principal will accept every alias.

### Kerberos Channel Binding and HTTPS

Some Windows Extended Protection / Channel Binding Token (CBT) policies bind the authentication token to the TLS channel. If TLS terminates at a proxy and the GSS token is forwarded to the backend, a channel-binding mismatch can occur depending on versions and policies. **Do not fix this by disabling Extended Protection domain-wide** for a single misconfiguration: evaluate topology, JVM/SSPI versions, proxy TLS termination, CBT support, and security-policy-compliant options.

## 17. KDC Discovery, DNS SRV, and Firewall

KDC discovery can come from AD/DC Locator, DNS SRV, or `krb5.conf`. Example records:

~~~dns
_kerberos._tcp.corp.example. IN SRV 0 100 88 dc01.corp.example.
_kerberos._tcp.corp.example. IN SRV 10 100 88 dc02.corp.example.
_kerberos._udp.corp.example. IN SRV 0 100 88 dc01.corp.example.
~~~

These are **illustrative DNS records**, not necessarily the exact queries every Windows/Java client issues. Port **88/TCP and UDP** is the standard KDC port. Depending on the environment, DNS, directory, and other AD ports may also be needed for domain join/discovery.

If `kinit` succeeds on Linux yet the browser still fails SSO, the root cause may be browser policy/SPN/HTTP headers rather than KDC reachability. If the browser sends Negotiate yet Spring fails, check the keytab/KVNO/enctype and service principal. **Diagnose step by step** rather than opening the entire firewall.

## 18. Client-Side Ticket Inspection Tools

In a managed Linux/MIT Kerberos environment:

~~~bash
# Obtain a TGT for the test user in the realm:
kinit lan@CORP.EXAMPLE

# Inspect the credentials cache:
klist

# Request a service ticket for the exact HTTP principal:
kvno HTTP/portal.corp.example@CORP.EXAMPLE

# Inspect the acceptor-side keytab (does not print secret keys):
klist -kte /etc/security/keytabs/portal-http.keytab
~~~

These commands only run on machines with a real Kerberos client/keytab/KDC. **They have no fixed stdout** and will fail if illustrative realm/host/cert/username values have not been replaced. `kinit` may prompt for a password or another authentication factor; never pass passwords on the command line. `kvno` only proves the KDC can issue a service ticket for the requested principal; **it does not prove the Spring backend has the right keytab to decrypt it**.

In a Windows domain environment:

~~~powershell
# Inspect the ticket cache (read-only):
klist

# Request a specific service ticket in a domain-joined environment:
klist get HTTP/portal.corp.example

# Check SPN mapping:
setspn -Q HTTP/portal.corp.example

# Check for duplicates:
setspn -X
~~~

An administrator or RSAT tools may be required. Running diagnostics should never automatically alter SPNs/account credentials. When testing an alias, replace the hostname in the command with **the actual hostname the browser visits**.

## 19. Common Errors: Identify the Layer Before Fixing

| Error or Symptom | Suspected Layer | Interpretation / Resolution |
| --- | --- | --- |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC/SPN | Service principal not found; check `setspn -Q`, hostname/realm |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | AD/SPN | Duplicate owners; run `setspn -X` and clean up mapping |
| `KRB_AP_ERR_MODIFIED` | Service acceptor/keys | Ticket cannot be decrypted; check owner, keytab, password, KVNO, enctype |
| `KDC_ERR_ETYPE_NOSUPP` | Encryption policy | Client/KDC/service share no common enctype; check AES/RC4 policy |
| `KRB_AP_ERR_SKEW` | Clock | Time skew between client/KDC/service exceeds tolerance; sync NTP |
| `Clock skew too great` | Clock | Check system clocks; do not disable replay protection |
| `Cannot find KDC for realm` | DNS/krb5.conf | Check realm, SRV records, network reachability to KDC port 88 |
| `Server not found in Kerberos database` | SPN/realm | Target service principal does not exist or realm mapping is wrong |
| `Message stream modified` / checksum fail | Keytab/key | Wrong key or altered ticket; check KVNO/key owner, do not disable integrity |
| `Integrity check on decrypted field failed` | Keytab/enctype | Keytab file differs from KDC/service account key |
| Repeated HTTP 401 | Browser/Negotiate | No ticket sent, keytab failed, NTLM fallback, filter chain, or DNS |
| Browser only sends NTLM | Mechanism/policy | Kerberos failed to acquire SPN ticket or policy is wrong; do not mistake for Kerberos |
| Spring 403 after Negotiate | Authorization | Kerberos auth likely succeeded, but local user lacks authorities |
| Login works on node A, fails on node B | Keytab/rollout | The two nodes have different keytab/KVNO or realm configs |
| Alias fails while canonical FQDN works | Host/SPN | Missing alias SPN or browser canonicalizes hostname differently |
| Fails after service account password change | Key rollover | Stale keytab, KVNO mismatch; rotate in sync |
| SPNEGO fails through HTTPS proxy | Header/CBT | Proxy strips Negotiate, TLS channel binding, or trust topology issue |
| Off-domain browser does not silent SSO | Client setup | No domain session/TGT, missing trusted intranet settings |
| User roles mixed up across realms | Identity mapping | Local principal mapping strips the realm |
| `GSSException: Defective token detected` | SPNEGO parser/transport | Truncated token, unsupported mechanism, or key/encoding mismatch |

**Not every 401 error means "wrong SPN".** Verify whether the browser sent `Authorization: Negotiate`, whether the KDC issued a ticket for the right SPN, whether the server has the right keytab, and whether Spring actually received the GSS token in the filter chain.

### Least-Invasive Debugging Order

1. Record the **public browser hostname**, HTTPS protocol, and authentication challenge.
2. Check whether browser policy allows Negotiate for that host.
3. Verify TGT and service ticket on the client with `klist`/`kvno`.
4. Query the SPN in AD with `setspn -Q`; check duplicates with `-X`.
5. Confirm the SPN owner account, deployed keytab principal, KVNO, and enctype.
6. Verify Java `krb5.conf`/KDC discovery, clock skew, and DNS.
7. Check whether the reverse proxy preserves `WWW-Authenticate` and `Authorization` or terminates auth itself.
8. Check `SpnegoAuthenticationProcessingFilter`, provider, validator, and local user mapping.
9. Run E2E tests with a low-privilege user first, verifying tenant/resource permissions.
10. Only when necessary, enable short-lived Kerberos debugging in staging with safely redacted logs.

## 20. Keytab, Encryption Types, and Protecting Secrets

Service account keys are used in Kerberos ticket encryption. Operational points:

- Avoid legacy **DES** and **RC4** per security baseline; prefer AES enctypes compatible across AD/KDC/JDK, verifying actual policy before migration.
- Do not read an algorithm name like `aes256-cts-hmac-sha1-96` and assume you can arbitrarily swap HTTP/TLS ciphers; that is a **Kerberos enctype name**, not a TLS cipher suite.
- Every service account requires least privilege; never grant Domain Admin for SPNEGO.
- Mount the keytab only for the service process that needs it, with strict file permissions and never in Git or public images.
- Key rotation must synchronize the KDC account credential/KVNO across **all** Spring nodes.
- Never log raw key bytes; `klist -kte` normally shows metadata only, yet still reveals principal/infrastructure names that need protection.
- Avoid reusing the same service keytab across unrelated systems to limit blast radius.
- Review replay caches, ticket lifetimes, and clock synchronization; never disable Kerberos replay protection to bypass intermittent errors.

**A Kerberos service ticket is not a Bearer JWT**. Never copy a base64 `Negotiate` token into chat/logs or reuse it like a permanent API key; authentication data and GSS contexts must be handled by standard libraries.

## 21. Kerberos Double Hop and Constrained Delegation

SPNEGO lets the browser authenticate **to Portal**, yet that **does not automatically mean** Portal can use the user's identity to access a second SQL/SMB/HTTP service.

Example:

~~~text
Browser user Lan
   | HTTP/portal.corp.example (Kerberos ticket)
   v
Spring Portal
   | wants to access HTTP/reports-backend.corp.example as Lan
   v
Downstream service
~~~

**This is the delegation/double-hop problem**. Active Directory provides Kerberos Constrained Delegation (KCD)/S4U flows under admin-configured conditions and permissions. It does not work merely by forwarding the browser token or copying Lan's username into an HTTP header.

**Permissions that must be restricted**:

- Which service account is permitted to delegate?
- To **which target SPNs** may it delegate?
- Which users/tenants may be impersonated under policy?
- If protocol transition/S4U is used, are security conditions verified?
- Does the downstream service actually validate the new Kerberos ticket?

Never enable **unconstrained delegation** to solve ordinary errors. It drastically expands a service account's power if compromised. In multi-tier web apps, prefer designs with explicit identity propagation, least privilege, and thorough auditing.

## 22. Standalone Java 17: Simulating Realm–SPN–Keytab Matching

The program below helps learners understand a **logical configuration check**: the public hostname determines the expected SPN, the realm attaches to the principal, and the service principal configured in the keytab must match. It also simulates an SPN registered on two owners.

**Important:** this code operates purely on **strings**. It does **not** perform Kerberos AS/TGS/AP exchanges, contact a KDC/AD, inspect keytab bytes, verify a GSS ticket, check real DNS canonicalization, or decide IAM roles. The program is solely a diagnostic thinking aid.

Create file **`KerberosSpnBindingDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class KerberosSpnBindingDemo {

    static String expectedHttpSpn(String browserHost) {
        return "HTTP/" + browserHost.toLowerCase(Locale.ROOT);
    }

    static String fullServicePrincipal(String spn, String realm) {
        return spn + "@" + realm;
    }

    static String checkBinding(
            String browserHost,
            String registeredSpn,
            String keytabPrincipal,
            String realm) {

        String expectedSpn = expectedHttpSpn(browserHost);
        if (!expectedSpn.equalsIgnoreCase(registeredSpn)) {
            return "DENY: browser SPN is not registered";
        }
        String expectedPrincipal =
                fullServicePrincipal(expectedSpn, realm);
        if (!expectedPrincipal.equalsIgnoreCase(keytabPrincipal)) {
            return "DENY: keytab principal mismatch";
        }
        return "OK: names align";
    }

    public static void main(String[] args) {
        String realm = "CORP.EXAMPLE";
        String host = "portal.corp.example";
        String spn = "HTTP/portal.corp.example";
        String keytabName = "HTTP/portal.corp.example@CORP.EXAMPLE";

        Map<String, List<String>> owners = Map.of(
                "HTTP/portal.corp.example", List.of("CORP\\svc_portal"),
                "HTTP/legacy.corp.example",
                List.of("CORP\\svc_old", "CORP\\svc_other"));

        System.out.println("Realm: " + realm);
        System.out.println("Browser SPN: " + expectedHttpSpn(host));
        System.out.println("Full principal: "
                + fullServicePrincipal(spn, realm));

        System.out.println("Correct binding: "
                + checkBinding(host, spn, keytabName, realm));

        System.out.println("Wrong alias: " + checkBinding(
                host, "HTTP/node01.corp.example", keytabName, realm));

        System.out.println("Wrong keytab: " + checkBinding(
                host, spn, "HTTP/node01.corp.example@CORP.EXAMPLE",
                realm));

        System.out.println("Portal SPN owners: "
                + owners.get(spn).size());

        System.out.println("Legacy duplicate: "
                + (owners.get("HTTP/legacy.corp.example").size() > 1));

        System.out.println("HTTP over TLS still uses HTTP SPN: "
                + expectedHttpSpn(host).startsWith("HTTP/"));
    }
}
~~~

Run with JDK 17:

~~~bash
javac KerberosSpnBindingDemo.java
java KerberosSpnBindingDemo
~~~

**Exact stdout:**

~~~text
Realm: CORP.EXAMPLE
Browser SPN: HTTP/portal.corp.example
Full principal: HTTP/portal.corp.example@CORP.EXAMPLE
Correct binding: OK: names align
Wrong alias: DENY: browser SPN is not registered
Wrong keytab: DENY: keytab principal mismatch
Portal SPN owners: 1
Legacy duplicate: true
HTTP over TLS still uses HTTP SPN: true
~~~

### Takeaways from the Program

- The browser uses the **visited hostname** to form the HTTP SPN in the simple case; a reverse proxy does not automatically swap it to the node name.
- The realm is appended to the full principal; do not confuse it with a DNS record.
- Having the right SPN while the keytab holds a different principal still fails.
- An SPN has **one owner** by design; duplicates in an AD forest are an error to investigate.
- HTTPS **does not change the HTTP service class**.

**Intentional limitation:** `checkBinding` compares strings case-insensitively to teach the concept; it does **not** replace Kerberos GSS-API or AD SPN lookup. It knows nothing about keytab KVNO, AES keys, service account passwords, canonical DNS, or the Kerberos protocol. Do not conclude production is safe merely from "OK" output; test with a real KDC and Java acceptor.

## 23. Test Matrix for Verifying Spring Kerberos/SPNEGO Integration

| Group | Scenario | Expectation |
| --- | --- | --- |
| Realm | `default_realm=CORP.EXAMPLE` and KDC reachable | Client can acquire TGT |
| KDC | DNS SRV and fallback DC accurate | KDC is discovered and serves AS/TGS |
| User principal | Valid `lan@CORP.EXAMPLE` | AS issues TGT per policy |
| Unknown user | Non-existent principal | AS rejects |
| SPN | `HTTP/portal.corp.example` registered on right account | KDC issues service ticket |
| Missing SPN | No `HTTP/portal...` record | KDC rejects service request |
| Duplicate SPN | Two AD accounts own the same SPN | Must be detected and fixed before production |
| Wrong owner | SPN points to account differing from keytab | Spring acceptor rejects ticket |
| Keytab | Correct principal/KVNO/enctype | JGSS ticket validation succeeds |
| Stale keytab | Account password rotated | Fail closed; requires rolling out new keytab |
| Public hostname | Browser visits `portal.corp.example` | Browser requests HTTP/public SPN |
| Alias | Browser visits `reports.corp.example` | Matching alias SPN and keytab, or controlled rejection |
| HTTPS | Browser accesses HTTPS Portal | TLS succeeds, SPN remains HTTP/host |
| Browser policy | Managed intranet device | Negotiate header sent when policy permits |
| No credential | External unmanaged browser | Valid fallback login, no 401 loop |
| Header proxy | Pass-through proxy | `Authorization: Negotiate` reaches filter intact |
| Reverse proxy terminates auth | Trusted identity header architecture | Backend does not trust headers from Internet |
| Provider | `KerberosServiceAuthenticationProvider` | Verifies ticket before loading user details |
| Wrong realm | Untrusted `lan@PARTNER.EXAMPLE` | Not merged with `lan@CORP.EXAMPLE` |
| Local user disabled | Valid Kerberos ticket | Local app still denies |
| Roles | `ROLE_ADMIN` absent in local policy | HTTP 403 on protected admin route |
| Clock skew | Client/KDC/service clock drift | Kerberos rejects per policy |
| Enctype | Keytab lacks enctype supported by KDC | Authentication fails; fix key policy |
| NTLM fallback | Browser does not use Kerberos | Not falsely accepted as SPNEGO Kerberos success |
| Delegation | App calls downstream with user identity | Allowed only with KCD/S4U policy and downstream validation |
| Two replicas | Pods A/B have same approved credentials | Both accept valid tickets |
| Key rotation | Planned KVNO increment | No outage beyond expected cutover window |

**Running a string-checking Java program alone does not prove SPNEGO works.** Integration tests must run against a test KDC/domain account, managed browser/HTTP client, real service principal/keytab, and properly wired Spring Security application. Negative tests for wrong SPN/keytab/KVNO and mixed-realm users are also mandatory.

## 24. Safe Operational Deployment Procedure

1. **Lock down the public URL** of the application, e.g. `https://portal.corp.example`, rather than relying on pod DNS.
2. **Confirm the realm/KDC** and domain trust model managed by the IAM/AD owner.
3. **Create/select a service account** with least privilege, without Domain Admin rights.
4. **Query SPNs** beforehand with `setspn -Q`/`-X`, distinguishing service class and hostname.
5. **Register the unique SPN** `HTTP/portal.corp.example` on the right account per change request.
6. **Generate/rotate the official keytab**, verifying principal, KVNO, and enctypes.
7. **Distribute the keytab** via secret management to Spring nodes with strict file permissions.
8. **Configure krb5.conf/JVM** with accurate realm and KDC inside the actual container/VM.
9. **Enable Spring Kerberos filter/provider/validator** with the proper servicePrincipal/keytab, not using the password provider for SPNEGO.
10. **Configure browser policy** for Negotiate on the public hostname; enforce HTTPS and safe proxy headers.
11. **Map principal with realm** to local user and authorities, checking disabled accounts/tenants.
12. **Test AS/TGS/AP** using `kinit/klist/kvno`, browser E2E, and protected Spring logs.
13. **Test negative cases**: wrong SPN, duplicate, stale KVNO, cross-realm user, NTLM fallback.
14. **Monitor** KDC errors, 401 loops, keytab rotation, authentication latency, and account lockouts.
15. **Maintain a rollback runbook** for keytab/account/SPN and a secret rotation schedule with the IAM/security team.

### Things You Must Not Do

- Do not enable `permitAll` across the whole app when the filter fails.
- Do not read a username from an unverified `X-Remote-User` header.
- Do not grant admin roles solely because a principal belongs to `@CORP.EXAMPLE`.
- Do not copy a keytab into Git or a shared Docker image.
- Do not arbitrarily disable the replay cache, encryption protection, or Extended Protection.
- Do not enable unconstrained delegation to work around double-hop errors.
- Do not treat an NTLM fallback as proof that a Kerberos ticket was verified.
- Do not move SPN ownership across accounts in production without a key rollover plan.
- Do not conflate user principal, SPN, UPN, DNS host, and TLS certificate SAN.

## 25. Quick Q&A

**Q:** Why does HTTPS Portal still need SPN `HTTP/portal.corp.example` instead of `HTTPS/portal.corp.example`?

**A:** `HTTP` is the **Kerberos service class** for HTTP authentication, regardless of whether the transport layer uses TLS. HTTPS protects the channel; it does not change the standard SPN class.

**Q:** Is the KDC the web server that receives `Authorization: Negotiate`?

**A:** No. The KDC issues TGTs and service tickets, whereas the **web server/Spring acceptor** receives and verifies the token using its keytab.

**Q:** If a user has `lan@CORP.EXAMPLE`, must the server keytab contain that principal?

**A:** No. The SPNEGO service's keytab normally holds the **HTTP service principal**; the user principal/TGT belongs on the client/KDC side, not in the service keytab.

**Q:** Are `HTTP/portal.corp.example` and `CORP\svc_portal` the same thing?

**A:** No. The SPN is the service identifier; the AD account owns the SPN and long-term key. The KDC uses that mapping to issue tickets for the right account.

**Q:** Does an SPN need `@CORP.EXAMPLE` appended when running setspn?

**A:** In AD, `setspn` usually registers `HTTP/portal.corp.example` in `servicePrincipalName`. In Kerberos/JAAS/keytabs, the full form `HTTP/portal.corp.example@CORP.EXAMPLE` may be used. Do not append the realm to `setspn -S` in keytab style unless AD requires it.

**Q:** Why does `setspn -Q` find the SPN while Spring still reports `KRB_AP_ERR_MODIFIED`?

**A:** The SPN may be attached to the **wrong account**, the keytab may differ in key/KVNO/enctype, the account password may have changed, or the acceptor may expect a different principal.

**Q:** Can all duplicate SPNs simply be deleted and re-registered during peak hours?

**A:** No. SPNs involve other systems; verify the rightful owner and perform migration/rotation under IAM change control.

**Q:** When the browser sends `Authorization: Negotiate`, is it guaranteed to be Kerberos?

**A:** No. SPNEGO can negotiate other mechanisms like NTLM depending on client/server policy; you must verify the actual mechanism and ensure the validator rejects unwanted fallbacks.

**Q:** Once domain CORP authenticates Kerberos, is `ROLE_ADMIN` granted automatically?

**A:** No. Spring still requires a dedicated local role/tenant authorization policy.

**Q:** If the same web app gains a hostname alias, is adding a DNS record enough?

**A:** Not necessarily. Check which SPN the browser actually requests, the AD owner, the keytab/acceptor, the TLS SAN, and proxy routing.

## 26. Official Documentation and References

1. [RFC 4120 — The Kerberos Network Authentication Service (V5)](https://www.rfc-editor.org/rfc/rfc4120): realm, principal, KDC, AS/TGS exchanges, tickets, and security model.
2. [Oracle Java 17 — Kerberos Requirements](https://docs.oracle.com/en/java/javase/17/security/kerberos-requirements.html): `krb5.conf`, `java.security.krb5.realm`, and `java.security.krb5.kdc`.
3. [Oracle Java 17 — KerberosPrincipal Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/javax/security/auth/kerberos/KerberosPrincipal.html): `KRB_NT_PRINCIPAL`, `KRB_NT_SRV_HST`, and realm/name types.
4. [Spring Security Kerberos — Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): dependency coordinates and compatibility of Spring Security Kerberos 7.1.x.
5. [Spring Security Kerberos — Spring and Spring Security Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, and keytabs.
6. [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): receiving `Negotiate` tokens and AuthenticationManager.
7. [Microsoft Learn — Configure Service Principal Name](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/how-to-configure-spn): AD SPN format, ownership, and mapping principles.
8. [Microsoft Learn — setspn command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setspn): `-Q`, `-X`, `-L`, and `-S`, checking duplicate SPNs.
9. [Microsoft Learn — KRB_AP_ERR_MODIFIED and Wrong SPN Account](https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-event-4-access-denied): issue where the KDC issues a ticket using a different account than the service acceptor.
10. [Microsoft Entra — Troubleshoot Kerberos Constrained Delegation](https://learn.microsoft.com/en-us/entra/identity/app-proxy/application-proxy-back-end-kerberos-constrained-delegation-how-to): KCD, DNS, duplicate SPNs, and target services.
11. [MIT Kerberos Documentation](https://web.mit.edu/kerberos/krb5-latest/doc/): `kinit`, `klist`, `kvno`, krb5.conf, service principals, and keytabs.
12. [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): HTTP `WWW-Authenticate: Negotiate` and GSS token exchange.

**Final takeaway:** **Realm** defines the Kerberos trust domain; **KDC** issues TGTs and service tickets; **principal** identifies a user or service; **SPN** binds a hostname/service class to the right account/key. For Spring Security SPNEGO, the chain **browser hostname → HTTP SPN → AD owner/KDC ticket → service keytab → GSS validation → local authorities** must stay consistent. Never equate resolving DNS or receiving HTTP 401 with having verified a Kerberos ticket and authorized the user.