# Integrating SPNEGO with a Service Keytab in a Kerberos Test Environment

> **Module:** Spring Security – federation · **Group:** Comprehensive Practice. This exercise sets up a Kerberos V5 lab containing a KDC, test accounts, HTTP service principal, keytab, a Spring Security application accepting **SPNEGO / HTTP Negotiate**, and tests from browser, `curl`, and Java 17. Clearly separate **user tickets**, **service secret keytabs**, **HTTP principals/SPNs**, **Kerberos authentication**, **Spring Security `Authentication`**, and **internal authorization**. KDC-mutating commands are strictly for the administrated LAB realm. Spring server snippets are fragments requiring dependencies and a real Kerberos environment; the Java 17 policy example in section 18 compiles and runs standalone yet does not verify GSS-API itself.

## 1. Problem Statement and Expected Outcomes

A user logged into a workstation in realm `LAB.EXAMPLE.TEST` visits `https://portal.lab.example.test/reports`. The browser sends a Kerberos ticket to the Java web application for SSO without re-entering a password. The Java server must prove it is service `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` using a keytab issued **by the lab KDC**. Spring Security converts the GSS result into a principal, enforces account checks and `ROLE_REPORT_VIEWER`, and only then serves data.

Acceptance criteria:

1. KDC/realm operates; test user `student1@LAB.EXAMPLE.TEST` can run `kinit` and `klist`.
2. KDC holds the exact service principal `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST`.
3. The service keytab contains matching keys/KVNO; only the application can read the file, and it is **never inside Git/JAR/logs**.
4. Unauthenticated SPNEGO endpoints return `401` with `WWW-Authenticate: Negotiate`.
5. Browsers or `curl --negotiate` use an existing ticket to send `Authorization: Negotiate ...`.
6. The Spring Security Kerberos validator uses the **exact keytab + service principal** to accept AP tokens.
7. Principal `student1@LAB.EXAMPLE.TEST` receives only application-allowed local authorities; never becomes an administrator automatically.
8. Users lacking permissions or locally locked are denied resources even when Kerberos authentication succeeds.
9. Wrong FQDN/SPN, KVNO, enctype, system clock, principal, or keytab is rejected with clear diagnostics.
10. Multi-pod apps, TLS reverse proxies, cookies/sessions, and keytab rotation are tested under controlled conditions.

**The goal is not** to reimplement the Kerberos protocol in Java. Cryptographic accept/verify steps must rely on Java GSS-API/JAAS via Spring Security Kerberos or a verified framework.

## 2. Trust-Flow Diagram: KDC, Client, Browser, SPNEGO Acceptor

```text
                      Kerberos LAB.EXAMPLE.TEST
                     +---------------------------+
                     | KDC / AS / TGS            |
                     | kdc.lab.example.test      |
                     | service keys, KVNO        |
                     +---------------------------+
                       ^              ^
             AS exchange|              |TGS for HTTP/portal...
                       |              |
                       v              |
  Linux/Windows client + browser      |
  student1@LAB.EXAMPLE.TEST            |
  kinit -> TGT in credential cache     |
             |                         |
             +-- requests service ticket
             |    HTTP/portal.lab.example.test
             |
             |  GET /reports
             +-------------------------------> Spring Web SP
             |                                  (behind TLS ingress)
             |<----------- HTTP 401             |
             | WWW-Authenticate: Negotiate      |
             |                                  |
             +----- Authorization: Negotiate -->|
                   <base64 SPNEGO token>         |
                                                v
                                        SpnegoAuthenticationProcessingFilter
                                                |
                                                v
                                        KerberosServiceAuthenticationProvider
                                                |
                                                v
                                         SunJaasKerberosTicketValidator
                                                |
                                /run/secrets/portal-http.keytab
                                contains service LONG-TERM KEY(S)
                                                |
                                    Java GSS acceptSecContext
                                                |
                                       authenticated client principal
                                                |
                                   UserDetailsService/local role policy
                                                |
                                       Spring SecurityContext
                                                |
                                           200 or 403
```

### 2.1. AS/TGS, TGT, and Service Ticket

- **KDC (Key Distribution Center):** Kerberos server issuing tickets, consisting of the Authentication Service (AS) and Ticket-Granting Service (TGS).
- **Realm:** trust domain—in the lab, `LAB.EXAMPLE.TEST`, conventionally uppercase.
- **User principal:** e.g., `student1@LAB.EXAMPLE.TEST`.
- **TGT:** Ticket-Granting Ticket obtained after `kinit` or Windows domain logon; used to request service tickets.
- **Service principal / SPN:** e.g., `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST`, identifying the HTTP service the browser actually accesses. `HTTP` is the service class even when the URL uses HTTPS.
- **Service ticket:** obtained by the client from the TGS specifically for that SPN; only a server holding the matching keytab can decrypt/verify the service portion.
- **KVNO:** key version number. Rotation can cause an old keytab to mismatch newer tickets.
- **Keytab:** container storing *long-term secret keys of the service*. It is **not** a browser token, public certificate, or "user password" to put into a frontend.
- **SPNEGO (Simple and Protected GSS-API Negotiation):** mechanism for negotiating GSS security mechanisms, commonly Kerberos; if clients/servers support other mechanisms, define an explicit acceptance policy.
- **HTTP Negotiate:** HTTP challenge/response scheme carrying GSS/SPNEGO tokens in headers.

### 2.2. A `401` in SPNEGO Is Normally an Expected Step

A normal flow often begins with:

```http
GET /reports HTTP/1.1
Host: portal.lab.example.test

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
```

The client then sends a follow-up request:

```http
GET /reports HTTP/1.1
Host: portal.lab.example.test
Authorization: Negotiate <base64-opaque-gss-token>
```

The block above **only illustrates the HTTP protocol**; never copy the bracketed placeholder as a real token. The value after `Negotiate` is a Base64-encoded binary GSS token, not a JWT/JWS or username/password. Never decode it as JSON, trust a hostname from the token without SPN verification, or log full headers.

With mutual authentication, the server may return `WWW-Authenticate: Negotiate <response-token>` even alongside HTTP 200. Do not assume a single 401 round trip always suffices; GSS negotiation may take multiple legs depending on client/mechanism.

## 3. Lab Topology and Prerequisites

Assign these names in an isolated environment:

| Component | Example FQDN / Principal | Function |
| --- | --- | --- |
| Kerberos realm | `LAB.EXAMPLE.TEST` | Scope of keys and principals |
| KDC + admin | `kdc.lab.example.test` | MIT Kerberos KDC/kadmin |
| Application public DNS | `portal.lab.example.test` | Host the browser actually calls |
| Application URL | `https://portal.lab.example.test` | TLS frontend / canonical host |
| Service principal | `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` | SPNEGO acceptor |
| Test user | `student1@LAB.EXAMPLE.TEST` | Client principal holding a TGT |
| Disabled user | `locked1@LAB.EXAMPLE.TEST` | Tests local deny logic |
| Java web app | Spring Boot 3 + JDK 17 or compatible stack | HTTP Negotiate + authorization |
| Keytab path | `/run/secrets/portal-http.keytab` | Secret readable only by the app |
| KDC config | `/etc/krb5.conf` / `/etc/krb5kdc/kdc.conf` | Realm and KDC discovery |
| Client ticket cache | OS/`kinit` default ccache | Not the server keytab |

**Requirements:** DNS or `/etc/hosts` must resolve properly (for the lab), network routes must reach the KDC and SP, NTP/chrony clocks must be synced, and HTTPS certificates must be valid/trusted by browser/`curl`. Real deployments prefer centralized DNS over `/etc/hosts`. KDC uses TCP/UDP 88 (per config), admin 749 if remote `kadmin` is enabled; never expose the admin server to the Internet.

### 3.1. Realm and DNS FQDN Are Not the Same

`LAB.EXAMPLE.TEST` is the realm; `portal.lab.example.test` is the hostname. A client accessing `https://alias.lab.example.test` may request SPN `HTTP/alias.lab.example.test` rather than `HTTP/portal.lab.example.test`. DNS CNAMEs, canonicalization, and browser policies influence SPN selection. **When aliases are needed, register matching SPNs and plan trust/rotation**, rather than disabling service principal validation.

An IP literal like `https://10.0.0.8` is normally not a standard browser SPN. Test with the real public hostname; never rewrite the keytab to `HTTP/localhost` just to bypass lab errors.

### 3.2. Four Distinct Secret Flows

- Client users hold TGTs/tickets in their user credential cache; never upload them to the server.
- Browsers send only GSS service tokens in HTTP headers over HTTPS.
- The Java server reads the long-term **service** keytab to accept tokens.
- The KDC stores the realm's secret/key database; never mount the full KDC database onto the application.

**Least-privilege principle:** the web app keytab needs keys only for its HTTP service principal—never the KDC admin principal, `krbtgt`, host root principals, or user accounts.

## 4. Choosing the Right Spring Security Kerberos Generation

Spring Security Kerberos is an extension/module requiring dedicated dependencies; it is not enabled automatically by `spring-boot-starter-security`. **Verify the exact release you deploy**:

| Stack | Artifact Group (per docs) | Notes |
| --- | --- | --- |
| Spring Boot 3 / Spring Security 6.5.x / Java 17 | `org.springframework.security.kerberos`, `spring-security-kerberos-core` and `spring-security-kerberos-web` 2.2.x | 2.2.0 branch tested with Spring Security 6.5.1, Framework 6.2.8, Jakarta Servlet |
| Spring Security 7 / Framework 7 / Java 17+ | `org.springframework.security` for `spring-security-kerberos-core` and `spring-security-kerberos-web` | **GroupId changed** per v7 docs; version managed by Spring Security BOM |
| Spring Boot 2 / Security 5 / `javax.servlet` | Legacy Kerberos generation compatible with Spring 5 | **Never** mix `javax` filters directly into a Jakarta Servlet container |

Spring Security Kerberos 7 docs note the artifact coordinates moved to `org.springframework.security`, whereas 2.2.0 uses `org.springframework.security.kerberos`. Match your BOM and runtime without pulling both group artifacts into the same application.

### 4.1. Maven Spring Boot 3 Lab

```xml
<!-- pom.xml dependency fragments; Boot parent/BOM supplies web/security -->
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
  <version>2.2.0</version>
</dependency>
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
  <version>2.2.0</version>
</dependency>
```

This is a fragment, not a complete `pom.xml` (you still need parent, repositories, build plugins, app sources, Java target, and a locked dependency tree). On Boot 3/Security 6, verify binary compatibility for your exact patch versions. **Never** swap Boot-BOM-managed Spring Security dependencies with Spring 7 artifacts simply because module names look similar.

### 4.2. Maven Spring Security 7

```xml
<!-- Schematic current-generation coordinates. Align with Boot/Security BOM. -->
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
```

Do not copy version `2.2.0` onto the new group, and do not assume Boot 4/Framework 7 runs every Boot 3 filter customization verbatim. Run compilation, integration tests, and dependency convergence checks.

### 4.3. Why Not Use `KerberosRestTemplate` as a Server Acceptor?

`KerberosRestTemplate` acts as an **outbound client** calling Kerberos-protected services, sometimes using a client keytab to obtain credentials. **This lab builds a server accepting browser SPNEGO**, which needs `SpnegoAuthenticationProcessingFilter` → `KerberosServiceAuthenticationProvider` → `SunJaasKerberosTicketValidator`. Client-initiating credentials, service acceptor credentials, and LDAP GSSAPI binds are distinct flows; never flip `isInitiator` arbitrarily.

## 5. Setting Up an MIT Kerberos KDC in the Lab

On a test Linux VM you administer, install the Kerberos server/admin and client packages for your distribution (e.g., Debian/Ubuntu):

```bash
sudo apt-get update
sudo apt-get install krb5-kdc krb5-admin-server krb5-user
```

**Never run these realm-administration steps on a corporate domain/KDC without authorization.** The lab uses an isolated network. Distro configuration wizards vary; the commands below assume an MIT Kerberos KDC initialized with `LAB.EXAMPLE.TEST` and proper ACLs/admin principals. Understand your Linux distribution thoroughly before running `kdb5_util create -s`—it creates a fresh database/realm and must **never run on a KDC serving real data**.

### 5.1. Example `/etc/krb5.conf` Used by the Lab

```ini
[libdefaults]
    default_realm = LAB.EXAMPLE.TEST
    dns_lookup_realm = false
    dns_lookup_kdc = false
    rdns = false
    udp_preference_limit = 1

[realms]
    LAB.EXAMPLE.TEST = {
        kdc = kdc.lab.example.test
        admin_server = kdc.lab.example.test
    }

[domain_realm]
    .lab.example.test = LAB.EXAMPLE.TEST
    lab.example.test = LAB.EXAMPLE.TEST
```

This is an **MIT `krb5.conf` fragment**. Java JGSS normally uses the system Kerberos configuration; you may specify `-Djava.security.krb5.conf=/etc/krb5.conf`. Never hardcode real users' realms. With Windows AD domain controllers, KDC discovery via DNS SRV/realm mapping differs; clarify DNS/UPN, trusts, and encryption policies.

### 5.2. KDC Realm Database — Only When the Lab Is Brand New

Following MIT's guide, initialize the KDC DB with the appropriate admin tool:

```bash
# On a NEW isolated MIT KDC only.
sudo kdb5_util create -s -r LAB.EXAMPLE.TEST
```

This prompts for a master database password; never put passwords into command lines/logs/chats. Create an admin principal and ACLs per your distro docs; in the lab you can use `kadmin.local` with root access on the KDC. Start the KDC daemon via systemd/service and verify network listening.

**Stop condition:** if a KDC already exists, never re-run `create`. If a test user cannot `kinit` because the KDC is unreachable, do not debug Spring Security first; fix realm/NTP/network at the Kerberos layer.

### 5.3. Test Principal and Service Principal

On the lab KDC, create a user with a password **strictly via interactive prompt**:

```bash
sudo kadmin.local -q "addprinc student1@LAB.EXAMPLE.TEST"
```

Create the HTTP service principal with a random key, **needing no password**:

```bash
sudo kadmin.local -q \
  "addprinc -randkey HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

The lab KDC database now holds two principals with distinct roles. Using `HTTP/` even though the app serves HTTPS is the **proper service class** for Kerberos HTTP SPNEGO.

### 5.4. Exporting the Service Keytab

```bash
# Run on KDC lab administrator host.
sudo install -d -m 0700 /var/lib/kerberos-lab/export
sudo kadmin.local -q \
  "ktadd -k /var/lib/kerberos-lab/export/portal-http.keytab HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

**Critically important:** in MIT Kerberos, `ktadd` **randomizes service keys on export by default**, incrementing KVNO. Re-running `ktadd` carelessly invalidates earlier keytabs already deployed on app A/B against new KDC tickets.

To export an **additional keytab for the same SPN without changing the KDC key**, MIT supports:

```bash
sudo kadmin.local -q \
  "ktadd -norandkey -k /var/lib/kerberos-lab/export/portal-node-b.keytab HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

`-norandkey` requires proper key-export permissions and KDC policy; do not use it where key export is restricted. **Do not mistake it** for a rotation strategy; routine rotation plans key changes, maintains old/new versions during transition, and updates KDC/keytabs in sync. Enterprise/AD environments do not use MIT `kadmin`; follow your domain controller's SPN/keytab procedure.

### 5.5. Inspecting Keytab, KVNO, and Enctypes

On the KDC export host:

```bash
sudo klist -kte \
  /var/lib/kerberos-lab/export/portal-http.keytab
sudo kadmin.local -q \
  "getprinc HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

`klist -kte` prints the keytab's principal, KVNO, and enctype; it does **not** print secret key bytes by default. Verify every host/realm component of the principal. Algorithms like AES256/AES128 work when supported by KDC and JVM; never downgrade to legacy DES/RC4 to "pass a test" if prohibited by policy.

**There is no fixed stdout** for KDC commands: KVNO, enctype, and key generation vary by realm, config, and version. Never copy an example `KVNO=2` and treat it as a hard requirement.

## 6. Distributing and Protecting the Server Keytab

A keytab is the **long-term secret of the service principal**, distinct from a TLS private key yet needing equally strict protection.

### 6.1. Moving It to the Application Node

A keytab created on the KDC must travel only over managed, authenticated channels such as a secret-management pipeline or secure admin transfer. On the server:

```bash
# Illustrative service-host path preparation.
sudo install -d -m 0700 /run/secrets
sudo install -o portalapp -g portalapp -m 0400 \
  /secure-admin-transfer/portal-http.keytab \
  /run/secrets/portal-http.keytab
sudo -u portalapp test -r /run/secrets/portal-http.keytab
```

These commands assume OS service account `portalapp` exists and the file arrived via a secure channel. Never run the Java app as root, never `chmod 777`, and never put a keytab into `src/main/resources`/JAR/Git/Docker images. In Kubernetes, mount secrets read-only with strict namespace/RBAC, access logs, and backup controls; consider a CSI secret provider aligned with key rotation.

### 6.2. Keytabs Across Pods Sharing a Public Hostname

Because browsers always call `https://portal.lab.example.test`, clients request tickets for `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST`, **not** `HTTP/pod-a.internal`. Therefore pods behind the same public host can share **the same service keytab** or equivalent key service. If pod A uses KVNO 3 while pod B uses KVNO 2, logins fail intermittently behind the load balancer. Secret rollouts must be uniform.

### 6.3. Preventing Secret Leakage

- Never print `keytab` bytes into logs, metrics, support tickets, or stack traces.
- Never serve the keytab to browsers or include it in HTTP responses.
- Never commit a sample keytab "to make the lab easy to run"; generate one locally in the lab.
- Never bake a keytab into Docker images, plaintext Helm values, or ConfigMaps.
- Restrict process read access, file permissions, and volume mounts.
- If exposed, treat the **service principal** as compromised and rotate keys/KVNO per runbook.
- Never let clients supply `keyTabLocation`/`servicePrincipal` via query parameters.

### 6.4. Exposing a Filename vs. Exposing Bytes

Logging a config key like `app.kerberos.keytab=/run/secrets/portal-http.keytab` may be acceptable per policy, yet never log secret contents or dump entire environment/property sources that could contain other credentials. Use allowlisted health readiness probes instead of `ls -l` debug dumps.

## 7. Testing the Kerberos Client Before Running the Web App

On a Linux client on the same realm/network, using the test principal:

```bash
# Interactive password: no password on CLI.
kinit student1@LAB.EXAMPLE.TEST
klist

# Force/request ticket for HTTP service.
kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST
klist
```

If `kvno` fails with `Server not found in Kerberos database`, check SPN spelling, DNS alias/FQDN, realm, and the actual service principal in the KDC. If `kinit` fails with `Clock skew too great`, sync NTP. If the client cannot obtain a TGT, browser/`curl` SPNEGO has no foundation to authenticate.

### 7.1. Should You Run `kinit` with the Service Keytab on the Server?

Server `HTTP/portal...` is an **acceptor** and does not need to fetch a TGT like a user to accept HTTP Negotiate. `kinit -kt /run/secrets/portal-http.keytab HTTP/...` is sometimes used in labs to verify a keytab matches the KDC, yet it uses the service keytab as an **initiator**, creates a ticket cache, and may be blocked by policy; **never** make it a mandatory step or keepalive daemon for an SPNEGO server. For acceptors, start with `klist -kte`, JAAS config, and a real Negotiate flow.

### 7.2. Client and Server in Different Clocks / Time Zones

Kerberos tickets carry start/end times, and the KDC, client, and server enforce clock-skew tolerances (typically a few minutes, per realm). Displaying local time `+07:00` is fine if UTC timestamps match; the problem is **real system clock drift**, not time-zone formatting. Run NTP/chrony on KDC, clients, and app nodes. Never raise skew tolerance to hours to mask misconfigured clocks.

## 8. JAAS/JGSS Acceptor: Service Principal and Keytab

Java 17 provides `com.sun.security.auth.module.Krb5LoginModule` in module `jdk.security.auth`, exposing JAAS options. Example `/etc/portal/jaas-krb5.conf`:

```text
PortalAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/portal-http.keytab"
    principal="HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    debug=false;
};
```

This entry is **acceptor only**. Flag meanings:

| Option | Illustrative Value | Why |
| --- | --- | --- |
| `useKeyTab=true` | Enabled | Load long-term key from keytab |
| `keyTab=...` | Absolute path | Independent of working directory |
| `principal=HTTP/...@REALM` | Exact service identity | Do not accept arbitrary principals in the keytab |
| `storeKey=true` | Enabled | Populate secret keys in JAAS Subject private credentials for GSS accept |
| `doNotPrompt=true` | Enabled | Never wait on stdin for a password in a server |
| `isInitiator=false` | Enabled | Server acts as GSS acceptor, needing no user TGT |
| `debug=false` | Safe default | Avoid sensitive/noisy debug logs outside the lab |

Oracle JDK docs also permit `principal="*"` when `isInitiator=false` to accept using any principal in the keytab. **Never use wildcards unless a multi-SPN use case has been reviewed**; the lab pins a single principal to prevent key/hostname confusion.

### 8.1. JVM Properties

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -Djava.security.auth.login.config=/etc/portal/jaas-krb5.conf \
  -jar portal.jar
```

This command is an **illustrative launcher**; run it only once the build produces `portal.jar` and real configs exist. Some Spring Security Kerberos libraries configure JAAS programmatically inside `SunJaasKerberosTicketValidator` instead of reading `PortalAcceptor` directly; do not assume setting `-Djava.security.auth.login.config` alone activates the Spring SPNEGO filter. Check your validator's source/Javadoc for how it logs in and loads the keytab.

### 8.2. JDK 17, Modules, and GSS-API

Java JGSS uses `org.ietf.jgss.GSSManager`, `GSSContext`, and `GSSCredential`. When running a custom minimized JRE image built with `jlink`, include required modules such as `java.security.jgss` and `jdk.security.auth` when code needs the JAAS module. If `NoSuchAlgorithmException`/`ClassNotFound` occurs on a custom JRE, inspect the module graph before altering the Kerberos realm.

**Never** implement Kerberos cipher/decryption from a keytab yourself. JAAS/GSS handles cryptographic acceptance; the Spring Kerberos provider turns the verified principal into Spring `Authentication`.

### 8.3. A JGSS Fragment to Understand the Acceptor

```java
// Illustrative Java GSS-API fragment; not a complete server.
// receivedToken: byte[] decoded from trusted HTTP Negotiate path.
// LoginContext/Subject is created per JAAS acceptor config.
LoginContext login =
    new LoginContext("PortalAcceptor");
login.login();
Subject subject = login.getSubject();

String clientPrincipal = Subject.doAs(
    subject, (PrivilegedExceptionAction<String>) () -> {
        GSSManager manager = GSSManager.getInstance();
        GSSCredential credential = manager.createCredential(
            null, GSSCredential.INDEFINITE_LIFETIME,
            (Oid) null, GSSCredential.ACCEPT_ONLY);
        GSSContext context = manager.createContext(credential);
        try {
            byte[] serverToken =
                context.acceptSecContext(
                    receivedToken, 0, receivedToken.length);
            // If serverToken is non-null, protocol exchange
            // may require returning it to browser.
            if (!context.isEstablished()) {
                throw new SecurityException(
                    "GSS negotiation not complete");
            }
            return context.getSrcName().toString();
        } finally {
            context.dispose();
        }
    });
```

This code is a **fragment with undeclared imports/variables** and simplified context lifetimes. It **does not** encode SPNEGO tokens, emit response tokens, handle multi-round challenge/response, bind HTTP state, or manage full replay/context lifecycles. In real apps, use the maintained Spring Security Kerberos filter rather than writing one from scratch.

## 9. Spring Security: Configuring SPNEGO on the Server

### 9.1. Key Classes

- `SpnegoEntryPoint`: emits the `401 WWW-Authenticate: Negotiate` challenge; can configure a form-login fallback per risk policy.
- `SpnegoAuthenticationProcessingFilter`: reads the Negotiate header and builds `KerberosServiceRequestToken`.
- `KerberosServiceAuthenticationProvider`: validates tokens via `KerberosTicketValidator`, then queries local `UserDetailsService`/authorities.
- `SunJaasKerberosTicketValidator`: uses JAAS/GSS to verify the service ticket against the **service principal and keytab**.
- `UserDetailsService`: maps the verified identity to internal accounts/authorities; never trusts roles from raw HTTP headers.
- `SecurityFilterChain`: route authorization, sessions/CSRF, exception handling.
- `BasicAuthenticationFilter`: anchor point where Spring docs place the SPNEGO filter before it.

**Important:** `KerberosServiceAuthenticationProvider` returns the user principal and local authorities from `UserDetailsService`; Kerberos **never auto-grants** `ROLE_ADMIN`, and authenticating a principal name does not prove local account permissions.

### 9.2. `application.yml` Fragment

```yaml
server:
  port: 8080

app:
  kerberos:
    service-principal: "HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
    keytab: "/run/secrets/portal-http.keytab"

logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.kerberos: INFO
```

The app may listen on internal HTTP port 8080 behind ingress, yet **browsers use public HTTPS** and the GSS service principal still tracks the public FQDN, not `HTTP/pod:8080`. Never place keytab bytes into YAML, environment dumps, or secrets-as-config commits.

### 9.3. Illustrative Spring Boot 3 / Security 6 Configuration

```java
package example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication
        .KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun
        .SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication
        .SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication
        .SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www
        .BasicAuthenticationFilter;

@Configuration
public class KerberosSecurityConfiguration {

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            Environment env,
            UserDetailsService localUserDetailsService) {

        String servicePrincipal = env.getRequiredProperty(
            "app.kerberos.service-principal");
        String keytab = env.getRequiredProperty(
            "app.kerberos.keytab");

        SunJaasKerberosTicketValidator ticketValidator =
            new SunJaasKerberosTicketValidator();
        ticketValidator.setServicePrincipal(servicePrincipal);
        ticketValidator.setKeyTabLocation(
            new FileSystemResource(keytab));
        ticketValidator.setDebug(false);

        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(ticketValidator);
        provider.setUserDetailsService(localUserDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        ProviderManager manager = new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/healthz").permitAll()
                .requestMatchers("/reports/admin/**")
                    .hasRole("REPORT_ADMIN")
                .requestMatchers("/reports/**")
                    .hasRole("REPORT_VIEWER")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .addFilterBefore(filter, BasicAuthenticationFilter.class)
            .build();
    }
}
```

**This is a Spring configuration fragment, not a runnable project.** It needs a Boot main class, matching dependency versions, HTTP controllers, a real `UserDetailsService`, KDC/DNS/HTTPS testing, and local account-status/authority validation. `new SpnegoEntryPoint()` emits a Negotiate challenge; a fallback page can be passed to the constructor, yet test carefully to avoid login loops.

**Important caveat:** the filter is instantiated **inside `SecurityFilterChain`**, never exposed additionally as a Servlet `@Bean Filter`/`FilterRegistrationBean`. Exposing it as a bean lets Boot auto-register it outside `springSecurityFilterChain`, causing Negotiate to run **twice**. In tested versions, `SpnegoAuthenticationProcessingFilter` exposes `setSecurityContextRepository` and `setSessionAuthenticationStrategy`; see the next section if you need persistent sessions.

### 9.4. `SecurityContext` Persistence Is an Explicit Decision

Spring Security Kerberos's filter source defaults to a request-based repository; it **does not automatically persist the authenticated `SecurityContext` across requests in `HttpSession`**. With stateless-per-request SPNEGO, browsers can re-negotiate per request as needed. If you want a frontend session cookie, configure persistence explicitly:

```java
import org.springframework.security.web.context
    .HttpSessionSecurityContextRepository;
import org.springframework.security.web.authentication.session
    .ChangeSessionIdAuthenticationStrategy;

// Extension fragment on the already-created filter.
HttpSessionSecurityContextRepository contextRepository =
    new HttpSessionSecurityContextRepository();
filter.setSecurityContextRepository(contextRepository);
filter.setSessionAuthenticationStrategy(
    new ChangeSessionIdAuthenticationStrategy());
```

**Do not just copy two lines and consider it done:** align the `SecurityFilterChain`'s `SecurityContextRepository`, session policy, invalidation, logout, CSRF, and cluster store. Never store GSS negotiation contexts or opaque tokens in the session; persist only the minimal validated `Authentication`. With Spring Session Redis, test serialization, session-fixation ID rotation, and logout/lock revocation.

For a stateless API, you may not want browser `HttpSession`s at all. Choose explicitly between stateless and stateful, and test behavior with stale cookies, revoked users, and requests lacking an `Authorization` header.

### 9.5. Calling `UserDetailsService` Alone Is Not Always Enough

A local account returning `UserDetails` with `enabled=false` or `accountNonLocked=false` must be enforced per policy—never assume every custom provider applies the same checks as password-based `DaoAuthenticationProvider`. Put an explicit account-status gate in place and verify it against your chosen provider. For sensitive routes, authorities may be cached in the session; test role revocation/account locking **after** login.

### 9.6. Spring Security 7 Changes `groupId`, Keeps the Same Concepts

In Spring Security 7, Kerberos modules moved to `org.springframework.security`. APIs like `SpnegoAuthenticationProcessingFilter` and `KerberosServiceAuthenticationProvider` still appear in current docs, yet always **cross-check constructors, builder DSLs, and the BOM**. Never mix `org.springframework.security.kerberos` 2.2.0 modules with 7.x modules on the same classpath. Spring Security 6/7 changed `SecurityContext` persistence defaults; test real sessions instead of inferring from historical samples.

## 10. Local `UserDetailsService` and Internal Permissions

A verified Kerberos user principal might be `student1@LAB.EXAMPLE.TEST`. Never treat it as an automatic admin privilege, and never match raw substrings like `.contains("admin")`. Map canonical identity → local account:

```text
Kerberos principal (verified by GSS):
  student1@LAB.EXAMPLE.TEST
      |
      v
Local identity mapping:
  protocol: kerberos
  realm: LAB.EXAMPLE.TEST
  name: student1
  localId: student-portal-001
      |
      v
Local account status = ACTIVE
Local grants = {REPORT_VIEWER}
      |
      v
GrantedAuthorities = {ROLE_REPORT_VIEWER}
```

With multiple realms or forest trusts, canonicalization policy is critical. `student1@REALM-A` is not automatically `student1@REALM-B`, and Windows UPNs do not always match `sAMAccountName`. Never strip the realm before DB lookup in multi-realm environments; an attacker from another realm could collide on the username portion.

### 10.1. Illustrative Local Mapping

```java
// UserDetailsService fragment after GSS authentication.
// localIdentityRepository and localGrantService are application-defined.
@Override
public UserDetails loadUserByUsername(String krbPrincipal) {
    LocalUser local = localIdentityRepository
        .findByKerberosPrincipal(krbPrincipal)
        .orElseThrow(() -> new UsernameNotFoundException(
            "Principal not provisioned"));

    if (!local.isEnabled() || local.isLocked()) {
        throw new DisabledException("Local access denied");
    }

    List<GrantedAuthority> authorities =
        localGrantService.grantsFor(local.getId()).stream()
            .map(SimpleGrantedAuthority::new)
            .toList();

    return User.withUsername(local.getId())
        .password("{noop}not-used-by-kerberos")
        .authorities(authorities)
        .accountLocked(false)
        .disabled(false)
        .build();
}
```

**Fragment only, not standalone code;** omits imports, interfaces, repositories, and business policies. The placeholder password **plays no role in Kerberos**, yet if that `UserDetails` object were reused by form login, a `"not-used"` string could create a dangerous password path. Production should isolate local password auth from Kerberos `UserDetails` or use locked credentials rather than predictable passwords. Depending on the provider, mapping can return a custom `UserDetails` without password-login support.

### 10.2. Testing Local Status and Roles

- `student1@LAB.EXAMPLE.TEST` ACTIVE with `ROLE_REPORT_VIEWER`: `/reports/overview` succeeds.
- `student2@LAB.EXAMPLE.TEST` ACTIVE without role: GSS succeeds, app returns 403 on protected reports.
- `locked1@LAB.EXAMPLE.TEST` has role yet locally locked: reject auth or deny all protected actions.
- Principal from `OTHER.REALM` with username matching `student1`: must not map to the same local account.
- User revoked after establishing a session: old cookie must lose data access per revocation policy.
- Debug endpoint `/whoami` returns minimal data, never printing service tickets or keytabs.

### 10.3. LDAP/AD Lookup After Kerberos

Some deployments query AD via LDAP/LDAPS for groups/authorities. That is a **separate** connection with its own trust, bind credentials, LDAP filters, and scope—not automatic just because Kerberos verified the user. If using `KerberosLdapContextSource` or GSSAPI LDAP binds, define a separate initiator identity and configure trust; never grant LDAP admin rights to the HTTP service acceptor keytab in violation of least privilege. Map LDAP groups through tenant/local policy; never grant `ROLE_ADMIN` merely because a group name contains `"admin"`.

## 11. Browser and `curl`: Testing the Right SPN

### 11.1. `curl` Negotiate on a Linux Client Holding a TGT

On a lab client machine after running `kinit student1@LAB.EXAMPLE.TEST`:

```bash
curl --version
curl -i --negotiate -u : \
  https://portal.lab.example.test/reports/overview
```

`curl` must be built with GSSAPI/Negotiate support. `-u :` is the standard syntax to trigger `curl`'s Negotiate auth; it does **not** send `student1`'s password over HTTP Basic. For HTTPS, validate real CA/hostname—never put `-k` in runbooks; if using a self-signed lab CA, install CA trust properly scoped.

Expected output may show an HTTP 401 challenge followed by HTTP 200 or 403 per local roles. There is no fixed stdout because `curl` versions, HTTP/WWW-Authenticate headers, and credential caches differ. Inspect browser/`curl` debug logs **redacted**: never save `Authorization: Negotiate` header values in build logs.

### 11.2. `curl` Without a TGT

```bash
kdestroy
curl -i --negotiate -u : \
  https://portal.lab.example.test/reports/overview
```

Expect **Kerberos authentication cannot succeed** without a credential cache or OS SSO source; the user receives 401 or configured fallback. Some hosts have other credential caches (Windows SSPI or service accounts), so exact behavior depends on OS. Never run `kdestroy` on machines holding real non-lab credentials; use it only for test principals.

### 11.3. Mandatory Browser Prerequisites

- Client machine belongs to / trusts the realm, or the user already holds Kerberos credentials.
- Browser is configured with **allowlisted SPNEGO / integrated auth sites** per enterprise policy.
- URL uses the FQDN matching the SPN; avoid IP literals.
- DNS/KDC discovery, NTP, and TLS CA trust are all valid.
- Browser supports HTTP Negotiate; if it refuses to send a token automatically, the site may be absent from the trusted intranet allowlist.
- Never force all browsers to fall back to NTLM for Kerberos; if NTLM is outside your threat model, disable/restrict it on applicable systems.
- Test both fresh login and reauthentication after local session expiry, not just requests carrying an existing cookie.

### 11.4. Edge and Proxy: Who Accepts Negotiate?

Two distinct architectures exist:

1. **Java backend acts as acceptor:** ingress **forwards** `Authorization: Negotiate` (and `WWW-Authenticate` responses) to Spring Security Kerberos; the backend reads the keytab.
2. **Ingress acts as acceptor:** proxy/gateway verifies Kerberos itself and forwards the verified identity to the backend over a trusted channel. The backend must **never** blindly trust browser-sent `X-Remote-User`; the proxy must strip spoofed headers and authenticate the backend link.

Never install the keytab on both ingress and backend and let both try to "authenticate again" unintentionally; double ticket consumption or context mismatches can occur. Terminating HTTP auth at ingress alters Spring failure responses; test the real network path.

## 12. HTTP 401/403, Redirect Loops, and Fallback

An SPNEGO flow must never enter an infinite `302` loop to a login form simply because a Negotiate header is absent. `SpnegoEntryPoint` issues a `401` challenge. When password/LDAP fallback is supported:
- Form login must enforce HTTPS, CSRF, rate limiting, and MFA per risk.
- Keep SPNEGO and form-login paths distinct; never open the web app with `permitAll` on negotiation failures.
- Browsers may not support Negotiate; restrict fallback to permitted accounts/methods.
- Never silently present a Basic auth prompt as an unintended fallback.
- When an authenticated user lacks a role, return `403 Forbidden` (per app handler) instead of an endless negotiate loop.
- For API callers, clarify challenge vs. redirect behavior; never force SPA `fetch` calls to follow redirects to a KDC.

### 12.1. Authentication vs. Authorization Differences

| Situation | Authentication | Authorization | Outcome |
| --- | --- | --- | --- |
| No Negotiate header, no session | None yet | Not evaluated | `401 WWW-Authenticate: Negotiate` |
| Invalid/malformed token | Failed | Not evaluated | Reject/challenge, sanitized |
| Valid ticket, active principal, valid role | Succeeded | Succeeded | 200 per endpoint |
| Valid ticket, active principal, missing role | Succeeded | Failed | Usually 403 |
| Valid ticket, local account LOCKED | Denied app admission | Failed | Deny; no authenticated app session created |
| Stale session after admin locks account | Previously auth | Revoked | Deny access to protected data |

**Never** treat the initial HTTP 401 as "SPNEGO failed". It is normally the required challenge. To test full SSO, inspect the final request/response after negotiation and the authenticated identity.

## 13. Kerberos Key Version, Encryption Types, and Rotation

### 13.1. Relationship Between KVNO and Keytab

Each service principal has key version(s) managed by the KDC. `ktadd` exports active keys yet **by default randomizes keys**, incrementing KVNO. A keytab holding KVNO 2 cannot accept a newly issued service ticket encrypted with KVNO 3, typically raising an error like:

```text
GSSException: Failure unspecified at GSS-API level
  Mechanism level: Cannot find key of appropriate type
  or integrity check on decrypted field failed
```

Actual messages vary by JDK/KDC/enctype; never rely on one literal string. Inspect `klist -kte` on the file and `getprinc`/`kvno` from the KDC/test client. Never put raw tickets/secrets into error reports.

### 13.2. Safe Cluster Rotation

```text
Phase 0  old KVNO = 3 in app A/B and KDC
Phase 1  approved rotation plan, snapshot current keytab
Phase 2  generate new key/KVNO through KDC admin process
Phase 3  distribute updated keytab to ALL SP nodes
         with controlled overlap/maintenance window
Phase 4  observe new tickets accepted, old ticket lifetime
Phase 5  retire old keys only after risk window and verification
```

Never assume the KDC keeps multiple active KVNOs after `ktadd`; depending on policy/history, a keytab may retain multiple entries while the KDC issues new tickets only with the current key. To prevent outages, roll out keytabs / key-version overlaps according to your MIT/AD realm's supported policy; if overlap is unsupported, schedule a controlled short maintenance window. **Never** copy an old unchanged keytab and assume it will accept new tickets.

### 13.3. Encryption Types

Kerberos SPNEGO may support AES128/AES256 and other enctypes depending on KDC, AD, and JDK. If the KDC issues an encryption type absent from the Java runtime or service keytab, GSS acceptance fails. Verify:
- `klist -kte` lists the key types.
- KDC service principal permitted enctypes.
- JDK 17 provider/enctype support.
- AD account flags / keytab generation tool when using Active Directory.
- Policies forbidding RC4/DES—never re-enable weak algorithms as a "quick fix".

### 13.4. Active Directory SPN Differences

With Microsoft AD, manage SPNs/service accounts using tools like `setspn`/`ktpass` per domain admin guidelines. Avoid duplicate SPNs across accounts; never run `setspn -A` without checking uniqueness. `ktpass` can reset the service account password/key, creating KVNO/etype mismatches with already deployed hosts. Verify with `setspn -Q HTTP/portal.lab.example.test` in an authorized AD lab and compare service account/keytab identity.

**This lab uses an MIT KDC**; do not apply `kadmin.local` commands verbatim to a Windows Domain Controller.

## 14. JAAS Debug, GSS Debug, and Safe Logging

### 14.1. Scoped Debugging

In an isolated lab, you may temporarily enable:

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -Dsun.security.krb5.debug=true \
  -Dsun.security.jgss.debug=true \
  -jar portal.jar
```

**Never leave debug flags enabled by default in production**, because logs may reveal principal names, realm mappings, and sensitive config details. Never store raw Negotiate tokens, TGTs, keytab bytes, or user attributes. After verification, turn them off and rely on safe reason codes.

### 14.2. Layered Failure Classification

| Stage | Example Issue | Tooling |
| --- | --- | --- |
| DNS/hostname | Browser hits `portal` alias while SPN uses another hostname | `getent hosts`, DNS, browser URL |
| KDC client auth | Cannot obtain TGT | `kinit`, `klist` |
| TGS lookup | Service principal does not exist | `kvno HTTP/portal...`, KDC admin |
| KDC/service key | KVNO/enctype mismatch, stale keytab | `klist -kte`, KDC `getprinc` |
| HTTP negotiation | Proxy strips headers, browser blocks Negotiate | HTTP 401/`WWW-Authenticate` headers |
| GSS accept | Bad keytab/JAAS/clock/mechanism | Sanitized GSS error, JDK/KDC configs |
| Spring authentication | Provider unwired, bean double-registered | Security filter logs/tests |
| Local authorization | Missing role, locked account | Local authz service / test fixtures |
| Session | `SecurityContext` not persisted or stale | Filter repository / session config |
| TLS | Client rejects HTTPS cert | Browser/`curl` truststore, TLS diagnostics |

### 14.3. Never Fix by Bypassing Controls

Never:
- Disable TLS validation "so `curl` works".
- Accept arbitrary `Authorization` bytes without calling the GSS validator.
- Let clients send `X-User` and map it to a principal.
- Mount KDC master keys or service admin keytabs into web pods.
- Enable DES/RC4 or unreviewed wildcard service principals.
- Skip local locked-account, tenant, or role checks.
- Treat an empty `Negotiate` value as authenticated.
- Rewrite `401/403` into `200` at ingress.
- Log raw SPNEGO headers in reverse proxies/APM for ongoing debugging.

## 15. Multi-Node / SPNEGO Behind Ingress and Session Consistency

### 15.1. SPN Binds to the Public Hostname, Not Individual Pods

Browsers request tickets for `HTTP/portal.lab.example.test`. Both Node A and Node B behind the load balancer must hold keys able to accept tickets for that SPN. Mount the same centrally managed/rotated keytab secret to avoid version skew.

```text
Browser -> https://portal.lab.example.test
         -> TLS ingress / LB
              -> portal-pod-a with keytab KVNO 3
              -> portal-pod-b with keytab KVNO 3

Both accept tickets for HTTP/portal.lab.example.test
```

If one pod throws `GSSException` while another succeeds, inspect keytab content/version, permissions, and env config per pod without dumping raw secrets. Ingress must forward `Negotiate` headers unmodified and preserve the canonical hostname.

### 15.2. Sticky Sessions Do Not Solve Keytab Consistency

Sticky sessions only route browser cookies back to an earlier pod. When a pod restarts, the next request lands on another node, which must still hold the right keytab. If the app uses `HttpSession` to persist Spring `SecurityContext`, use Spring Session Redis/DB or plan for reauthentication on failover. **Never** treat sticky routing as a Kerberos trust model.

### 15.3. Ticket Replay and Session Reuse

Kerberos/GSS enforces replay protection at the mechanism/protocol layer, yet applications may still need session-fixation protection, request-replay controls, and CSRF defenses. Never use a `TGT` or AP token to keep admitting a user after the local account is locked. Session duration and revoked-role consistency must be tested independently.

### 15.4. TLS Termination and Channel Binding

Some Kerberos/SSPI deployments enforce **Extended Protection for Authentication (EPA) / channel binding tokens (CBT)** tying GSS to the TLS channel. When TLS terminates at ingress while GSS acceptance runs on the backend, channel binding expectations can mismatch; resolve it via supported JDK/proxy/EPA architectures or negotiate termination—**never disable extended protection on a Domain Controller via legacy registry workarounds** just to pass a lab. Test browser policies, TLS topology, and the chosen service principal.

### 15.5. Stateless API vs. Web Session

If every HTTP request carries a Negotiate token, the backend can authenticate per request; if the app creates a web session, the session cookie grants subsequent access. Decide explicitly:

- Per-request GSS negotiation and `SecurityContextRepository`.
- Session fixation strategy when creating sessions.
- CSRF protection for state-changing browser POSTs.
- Cookie `Secure`/`HttpOnly`/`SameSite` and expiration.
- Redis-backed sessions across multiple nodes.
- Local logout does not necessarily destroy OS TGT/domain logon; the browser may auto-renegotiate. Clarify "sign out of portal" vs. "sign out of Windows/Kerberos realm".
- Disabled/locked users and revocations must take effect even while the client holds a valid TGT.

## 16. Lab Testing: Layer-by-Layer Checkpoints

### 16.1. Test TGT (Independent of Spring)

```bash
kinit student1@LAB.EXAMPLE.TEST
klist
```

If this fails, fix KDC/time/DNS/password/user status first. Do not touch the web app yet.

### 16.2. Test Service Ticket (KDC Lookup)

```bash
kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST
```

If `Server not found in Kerberos database`, the principal/realm name is wrong. If KVNO/enctype differs from expectations, inspect KDC/service key mappings and the keytab.

### 16.3. Test Backend Acceptor from `curl`

```bash
curl -i --negotiate -u : \
  https://portal.lab.example.test/reports/overview
```

Observe:
- An initial `401 WWW-Authenticate: Negotiate` challenge is normal.
- Does `Authorization: Negotiate ...` appear on the follow-up request?
- Does the GSS validator accept using the right keytab?
- Does the local principal hold the viewer role?
- Is the final response 200/403 or 401 per the test case?

### 16.4. Test Different Users

Create lab test accounts:
- `student1` with `ROLE_REPORT_VIEWER`.
- `student2` with no role.
- `locked1` locally locked even if the KDC still issues tickets per lab policy.

Never derive roles from username patterns or `realm==LAB => ADMIN`. If the KDC account itself is locked, the client cannot fetch a new ticket; to isolate **local lock policy**, keep the KDC account active and lock only the local app account in the fixture.

### 16.5. Test Rotation

- Before rotation, all nodes accept the current ticket.
- After approved rotation, verify `klist -kte` on every pod shows expected KVNO/enctypes.
- Log in from a client holding a fresh service ticket.
- Test existing cached tickets per overlap policy.
- Never re-run `ktadd` repeatedly in the KDC once per pod.
- Test failover across nodes after rotation.

## 17. Negative and Critical Incident Test Matrix

| ID | Case | Expected |
| --- | --- | --- |
| KRB-01 | No TGT and no other credentials | Client does not silently succeed SSO |
| KRB-02 | Holds TGT, no service ticket yet | Client obtains TGS ticket once SPN is registered |
| KRB-03 | Service principal `HTTP/portal...` absent from KDC | TGS lookup fails |
| KRB-04 | Browser uses IP literal or unregistered hostname alias | SPN mismatch; not accepted |
| KRB-05 | Pod A keytab KVNO 3, Pod B KVNO 2 | Node-specific failure; readiness/rotation QA fails |
| KRB-06 | Keytab readable by out-of-scope process | Security QA fails |
| KRB-07 | Keytab committed to Git/JAR/Docker image | Security QA fails |
| KRB-08 | Client sends raw `Authorization: Negotiate garbage` | GSS rejects |
| KRB-09 | `Authorization: Basic` header when SPNEGO-only | Does not authenticate via Basic |
| KRB-10 | Token issued for `HTTP/other.host` | Rejected by service GSS acceptor |
| KRB-11 | Expired service ticket | GSS rejects |
| KRB-12 | User/KDC/SP clocks skewed beyond tolerance | GSS error; NTP correction |
| KRB-13 | Keytab has right SPN yet wrong enctype | Reject; align KDC/keytab policy |
| KRB-14 | Re-running `ktadd` accidentally bumps KVNO | New tests fail; execute proper rotation |
| KRB-15 | Unreadable keytab (permission `000`) | Startup/GSS accept fails; no fallback |
| KRB-16 | Wrong `krb5.conf` realm mapping | KDC discovery / principal mapping fails |
| KRB-17 | Browser disallows Negotiate for site | 401/fallback; no auth bypass |
| KRB-18 | Ingress strips `Authorization` header | SPNEGO negotiation never completes |
| KRB-19 | Ingress strips `WWW-Authenticate` response | Browser receives no challenge |
| KRB-20 | Untrusted self-signed TLS cert | HTTPS fails; never use `curl -k` workaround |
| KRB-21 | Valid Kerberos user, missing local role | Protected path denied |
| KRB-22 | Valid Kerberos user, local account LOCKED | Denied despite successful GSS |
| KRB-23 | Principal `user@REALM-B` shares username with `user@REALM-A` | Must not map to the same local account |
| KRB-24 | Admin role present only in untrusted header | Admin not granted |
| KRB-25 | Existing web session after role revocation | Denied/revoked per local consistency policy |
| KRB-26 | Existing web session after account locked | Revoked / old cookie rejected |
| KRB-27 | Two nodes share same SPN/keytab version | Both authenticate |
| KRB-28 | One pod missing keytab secret mount | Pod fails readiness; no insecure fallback |
| KRB-29 | Duplicate Spring SPNEGO filter registration | Tests detect double negotiation |
| KRB-30 | Spring `SecurityContext` unpersisted by design | Per-request auth expected; behavior documented |
| KRB-31 | Stateful session configured yet context unsaved | Integration test fails |
| KRB-32 | Session invalidated while browser still holds Kerberos TGT | May reauthenticate; logout UX documented |
| KRB-33 | Raw Negotiate token logged at ingress | Security QA fails |
| KRB-34 | KDC unavailable while cached tickets remain valid | Test actual behavior; never assume KDC contacted per request |
| KRB-35 | KDC unavailable and client lacks valid tickets | Cannot initiate new SSO |
| KRB-36 | NTLM accepted unexpectedly instead of Kerberos | Reject/restrict per mechanism policy |
| KRB-37 | EPA/CBT mismatch across TLS proxy | Architecture review; no unsafe security disablement |
| KRB-38 | Oversized or malformed HTTP auth header | Parser limits/reject; no OOM |
| KRB-39 | Updated JDK/SSPI library alters GSS behavior | Regression tests on actual OS/JVM |
| KRB-40 | Viewer user accesses admin route | 403; no privilege escalation |

### 17.1. Mandatory Positive Control

A negative test showing 401 from a GSS error does **not prove** the local locked-account policy works. Verify:
1. Valid TGT/service ticket/SPN/keytab/GSS success from a test user.
2. ACTIVE user + exact role ⇒ app route passes.
3. Same protocol verification yet local account LOCKED ⇒ app denies.
4. Same GSS yet ACTIVE local account missing role ⇒ protected route denies.
5. Wrong SPN/keytab ⇒ GSS stage rejects before local user mapping.
6. Log reason codes internally without leaking raw tokens.

### 17.2. MockMvc Does Not Replace a Real KDC

Spring Security Test `@WithMockUser` or mocked `Authentication` only injects a `SecurityContext`/test principal; they do not exercise `kinit`, `kvno`, browser Negotiate, or the Java GSS acceptor. Unit policy tests are valuable, yet **lab integration** is mandatory to prove real keytabs, SPNs, headers, GSS, and KDC interoperability.

## 18. Standalone Runnable Java 17: Checking Post-GSS Policy and Keytab Metadata

The following example **requires no KDC, keytab, or Spring**. It models a decision table covering:
- Client with or without a Negotiate header.
- Whether GSS verification succeeded or failed (**a simulated boolean supplied only by a trusted server verifier**, never from HTTP/client input).
- Expected service principal.
- An **allowed KVNO** in a keytab view; in reality **Java GSS manages keys/KVNOs**—apps never parse tickets manually.
- Expiration, simulated replay indicator, local ACTIVE/LOCKED account, and local role.
- Accepting rotation when the keytab view includes both old and new approved KVNOs.

This program is a **policy oracle** for learning logic. Never build authentication by trusting a `gssAccepted` boolean from request JSON, never parse Kerberos tokens with regex, and never read secret keytabs inside demo apps.

Save **`SpnegoKeytabLabPolicyDemo.java`**:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class SpnegoKeytabLabPolicyDemo {

    enum Decision {
        CHALLENGE,
        ALLOW,
        DENY_GSS,
        DENY_SPN,
        DENY_KEY_VERSION,
        DENY_EXPIRED,
        DENY_REPLAY,
        DENY_UNKNOWN_USER,
        DENY_LOCKED,
        DENY_ROLE
    }

    record KeytabView(
            String servicePrincipal, Set<Integer> acceptedKvnos) {
        KeytabView {
            acceptedKvnos = Set.copyOf(acceptedKvnos);
        }
    }

    record LocalAccount(
            boolean active, Set<String> authorities) {
        LocalAccount {
            authorities = Set.copyOf(authorities);
        }
    }

    record TicketFixture(
            String requestId,
            String servicePrincipal,
            String clientPrincipal,
            int kvno,
            Instant expiresAt,
            boolean gssAccepted) {}

    static class LabGate {
        private final KeytabView keytab;
        private final Map<String, LocalAccount> accounts;
        private final Set<String> seenRequestIds = new HashSet<>();

        LabGate(KeytabView keytab,
                Map<String, LocalAccount> accounts) {
            this.keytab = keytab;
            this.accounts = new HashMap<>(accounts);
        }

        Decision accept(
                TicketFixture fixture,
                boolean negotiateHeaderPresent,
                Instant now) {

            if (!negotiateHeaderPresent) {
                return Decision.CHALLENGE;
            }
            if (!fixture.gssAccepted()) {
                return Decision.DENY_GSS;
            }
            if (!keytab.servicePrincipal()
                    .equals(fixture.servicePrincipal())) {
                return Decision.DENY_SPN;
            }
            if (!keytab.acceptedKvnos().contains(fixture.kvno())) {
                return Decision.DENY_KEY_VERSION;
            }
            if (!now.isBefore(fixture.expiresAt())) {
                return Decision.DENY_EXPIRED;
            }
            if (!seenRequestIds.add(fixture.requestId())) {
                return Decision.DENY_REPLAY;
            }

            LocalAccount local = accounts.get(
                    fixture.clientPrincipal());
            if (local == null) {
                return Decision.DENY_UNKNOWN_USER;
            }
            if (!local.active()) {
                return Decision.DENY_LOCKED;
            }
            if (!local.authorities().contains(
                    "ROLE_REPORT_VIEWER")) {
                return Decision.DENY_ROLE;
            }
            return Decision.ALLOW;
        }
    }

    static TicketFixture ticket(
            String requestId, String service, String user,
            int kvno, Instant expiry, boolean gssAccepted) {
        return new TicketFixture(
            requestId, service, user, kvno, expiry, gssAccepted);
    }

    static void show(String description, LabGate gate,
                     TicketFixture fixture, boolean hasHeader,
                     Instant now) {
        System.out.println(description + ": "
                + gate.accept(fixture, hasHeader, now));
    }

    public static void main(String[] args) {
        String service =
            "HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST";
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Instant future = Instant.parse("2026-11-07T10:05:00Z");
        Instant past = Instant.parse("2026-11-07T09:59:00Z");

        Map<String, LocalAccount> accounts = Map.of(
            "student1@LAB.EXAMPLE.TEST",
                new LocalAccount(
                    true, Set.of("ROLE_REPORT_VIEWER")),
            "locked1@LAB.EXAMPLE.TEST",
                new LocalAccount(
                    false, Set.of("ROLE_REPORT_VIEWER")),
            "student2@LAB.EXAMPLE.TEST",
                new LocalAccount(true, Set.of()));

        LabGate oldKeytab = new LabGate(
            new KeytabView(service, Set.of(3)), accounts);

        TicketFixture valid = ticket(
            "ticket-1", service, "student1@LAB.EXAMPLE.TEST",
            3, future, true);

        show("No header", oldKeytab,
            valid, false, now);
        show("Valid GSS with local viewer role", oldKeytab,
            valid, true, now);
        show("Replay same request id", oldKeytab,
            valid, true, now);

        show("Wrong service principal", oldKeytab,
            ticket("ticket-2",
                "HTTP/other.lab.example.test@LAB.EXAMPLE.TEST",
                "student1@LAB.EXAMPLE.TEST",
                3, future, true), true, now);
        show("New KVNO on old keytab", oldKeytab,
            ticket("ticket-3", service,
                "student1@LAB.EXAMPLE.TEST",
                4, future, true), true, now);
        show("Expired fixture", oldKeytab,
            ticket("ticket-4", service,
                "student1@LAB.EXAMPLE.TEST",
                3, past, true), true, now);
        show("GSS verification failed", oldKeytab,
            ticket("ticket-5", service,
                "student1@LAB.EXAMPLE.TEST",
                3, future, false), true, now);
        show("Local account locked", oldKeytab,
            ticket("ticket-6", service,
                "locked1@LAB.EXAMPLE.TEST",
                3, future, true), true, now);
        show("Missing local role", oldKeytab,
            ticket("ticket-7", service,
                "student2@LAB.EXAMPLE.TEST",
                3, future, true), true, now);
        show("Unknown principal", oldKeytab,
            ticket("ticket-8", service,
                "unknown@LAB.EXAMPLE.TEST",
                3, future, true), true, now);

        LabGate rollover = new LabGate(
            new KeytabView(service, Set.of(3, 4)), accounts);
        show("New KVNO during approved overlap", rollover,
            ticket("ticket-9", service,
                "student1@LAB.EXAMPLE.TEST",
                4, future, true), true, now);
    }
}
```

Compile and run with **JDK 17+**, with no external dependencies:

```bash
javac SpnegoKeytabLabPolicyDemo.java
java SpnegoKeytabLabPolicyDemo
```

**Exact** stdout:

```text
No header: CHALLENGE
Valid GSS with local viewer role: ALLOW
Replay same request id: DENY_REPLAY
Wrong service principal: DENY_SPN
New KVNO on old keytab: DENY_KEY_VERSION
Expired fixture: DENY_EXPIRED
GSS verification failed: DENY_GSS
Local account locked: DENY_LOCKED
Missing local role: DENY_ROLE
Unknown principal: DENY_UNKNOWN_USER
New KVNO during approved overlap: ALLOW
```

### 18.1. Interpretation

- No Negotiate header ⇒ **CHALLENGE**, corresponding to `401 WWW-Authenticate: Negotiate`.
- Valid GSS and local viewer ⇒ **ALLOW**; successful Kerberos principal authentication must still pass local policy.
- Replayed `requestId` ⇒ **DENY_REPLAY** in the model. Real GSS has its own replay semantics; never fabricate an app-specific "ticket ID" by parsing raw GSS tokens arbitrarily.
- Wrong SPN ⇒ **DENY_SPN**; browser tokens must never be accepted for another service.
- New KVNO on an old keytab ⇒ **DENY_KEY_VERSION**; in production the verifier/`krb5` reads keytab KVNOs automatically rather than manual app code.
- Expired ⇒ reject; never widen clock tolerance unboundedly.
- `gssAccepted=false` ⇒ **DENY_GSS**; this boolean models a **trusted validator's result**, not user-supplied data.
- Locked account / missing role / unknown user ⇒ deny after verified identity; never auto-provision privileges.
- Keytab view with approved versions ⇒ accepts KVNO 4 during conceptual rollover.

### 18.2. What Does the Demo Not Replace?

- It does not read `/etc/krb5.conf`, real keytabs, LDAP, CAS/SSO sessions, SPNEGO tokens, or real Kerberos tickets.
- It does not invoke `GSSContext.acceptSecContext` or verify encryption, KDC, real key versions, ticket authenticity, or the Kerberos mechanism's replay cache.
- It generates no HTTP headers/responses, executes no Spring Security filters, and enforces no session fixation protection.
- `gssAccepted` could be forged if taken from a request; in production it must come from a validated GSS result and **never** directly from controller/JSON inputs.
- `acceptedKvnos` is only a conceptual view; real keytabs hold actual encryption keys/enctypes and GSS selects keys automatically.
- `requestId` is a mock token identifier; the SPNEGO API **does not expose a ticket ID in that format** for apps to manage themselves.
- `LocalAccount` data lives in a `Map` without DB concurrency, revocation events, tenants, LDAP/AD trusts, or active-session invalidation.
- Time `Instant` is fixed; real Kerberos clocks/NTP must be checked across KDC, client, and SP.

## 19. Step-by-Step Troubleshooting

| Symptom | Which Layer to Inspect First? | Recommended Action |
| --- | --- | --- |
| Missing `WWW-Authenticate: Negotiate` | HTTP entrypoint / ingress | Check `SecurityFilterChain`, 401/302, proxy headers |
| Browser omits `Authorization: Negotiate` | Browser policy / client TGT | `klist`, site allowlist, exact FQDN, client OS |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC principal database | `kvno`, service principal registration |
| `KDC_ERR_PREAUTH_FAILED` in `kinit` | Client credentials | User account/password/realm/clock |
| `Clock skew too great` | NTP | Sync KDC/client/SP; never widen skew arbitrarily |
| `Cannot find key of appropriate type` | Keytab / enctype | `klist -kte`, KDC KVNO/enctypes, JDK |
| `Integrity check on decrypted field failed` | SPN / keytab / key version | Compare KVNO and actual service principal / key rotation |
| `Keytab file not found` | OS container mount | Path/permissions/read-only secret |
| `javax.servlet` mismatch | Dependency generation | Spring Boot 2 vs. 3/4, Jakarta-compatible modules |
| Repeated 401 despite holding TGT | Negotiate header or GSS | Proxy stripping, browser policy, SPN mismatch |
| GSS succeeds yet endpoint returns 403 | Spring local authorities | `UserDetailsService`/`ROLE_` prefix/resource roles |
| GSS succeeds yet user is anonymous on next request | `SecurityContext` persistence | Default request-only repo vs. session strategy |
| Only Node B fails | Keytab version / secrets | Per-pod mount, config, SPN/realm, runtime |
| Login succeeds then logs out immediately | Session fixation / CSRF / cookies | `Secure`/`SameSite`/Domain/Path, persistence |
| Browser sends NTLM yet org requires Kerberos | Mechanism policy | Browser/intranet auth and server accepted mechs |
| Channel binding mismatch | TLS proxy + EPA/CBT | Supported architecture, not unsafe registry tweaks |
| Keytab stale after repeated `ktadd` | KDC incremented KVNO | Restore approved key-management process |
| Java debug leaks principal/token material | Logging | Disable debug, redact, and rotate if exposed |
| `curl: option --negotiate not supported` | `curl` build | Install GSSAPI-enabled `curl` |
| Local lock ignored | App policy gate | Review `UserDetails`/provider; test stale sessions |

### 19.1. Least-Effort Investigation Sequence

1. `getent hosts portal.lab.example.test` or accurate DNS lookup on the client.
2. `kinit` and `klist` confirm a valid TGT.
3. `kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` obtains a service ticket.
4. `klist -kte /run/secrets/portal-http.keytab` on the server (with authorized access) confirms matching SPN+KVNO.
5. First HTTP response carries `WWW-Authenticate: Negotiate`, unstripped by ingress.
6. Client sends Negotiate header with an actual GSS token, not Basic.
7. Spring validator accepts and maps the verified Kerberos principal properly.
8. Local `UserDetails` and roles align; 403 if lacking permission.
9. Session policy/persistence behaves properly on follow-up requests or node switches.
10. Turn off debug logging, retain only sanitized correlation, and run negative tests.

### 19.2. Causes of Intermittent ("Works Sometimes") Failures

Common culprits include two pods running different keytab versions, DNS balancing across differing hostnames, browsers differing in ticket caches, one node experiencing clock drift, inconsistent Redis-backed sessions, or ingress paths stripping headers unevenly. Never raise tolerances or disable Kerberos to lower 401 rates; compare nodes/configs/policies step by step.

## 20. Advanced Testing: HTTP, TLS, and Cluster Aspects

### 20.1. Header Spoofing

Never feed `X-User: admin`, `X-Kerberos-Principal: student1`, or query `?user=admin` into `Authentication`. Map only verified GSS principals from `KerberosServiceAuthenticationProvider` or an authenticated identity from a trusted gateway. When ingress acts as the Kerberos acceptor, it must **strip user-supplied identity headers** at the network edge and authenticate the backend link.

### 20.2. Reject GSS Tokens Issued for Other Applications

A Kerberos ticket issued for `HTTP/service-b` must never log into `HTTP/service-a`. If service A accepts B's token, suspect a wildcard keytab, mis-shared keys, or a proxy trust bypass. Test wrong-SPN tokens and exact public hostnames.

### 20.3. CSRF After SPNEGO

SPNEGO authenticates identity at the HTTP layer, yet if the app uses cookies or the browser auto-sends Negotiate credentials to a trusted site, **CSRF remains a threat** to state-changing operations. Keep Spring Security CSRF enabled per your application threat model, requiring POST/CSRF tokens for user-initiated logouts and state changes; never disable CSRF site-wide because Kerberos is used.

### 20.4. Caching and SSO Sessions

Browsers may keep sending service tickets after local logout because the OS TGT remains valid. "Logging out" of the web app does not equal `kdestroy` or Windows domain sign-off. If business workflows demand true reauthentication/MFA, enforce server-side auth freshness/context controls and account policies; never claim clearing `HttpSession` removes Kerberos credentials from the workstation.

### 20.5. Proxy Timeouts and Header/Body Sizes

SPNEGO tokens can grow large when carrying PAC/AD groups; proxies need sufficient header size limits without leaving them unbounded against DoS and memory exhaustion. Some reverse proxies drop `Authorization` headers by default; configure forwarding explicitly and test. HTTP 400/431 errors can fire before reaching Spring, so log and monitor at ingress as well as the JVM.

## 21. Runbook: Building the Lab from Scratch to Acceptance

### Step 1 — Realm and Network

- Provision an isolated KDC host, test domain, and NTP sync.
- Verify DNS for `kdc.lab.example.test` and `portal.lab.example.test`.
- Create `/etc/krb5.conf` per section 5.
- Initialize a new realm if and only if no KDC exists yet.
- Open KDC ports to clients; never expose the admin service publicly.

### Step 2 — Test Principals

- Admin creates user `student1` via interactive `addprinc`.
- Admin creates `HTTP/portal.lab.example.test` via `addprinc -randkey`.
- Admin runs `ktadd` once per plan, recording KVNO/enctypes.
- Deliver the keytab over a secure channel to the service.

### Step 3 — Client Readiness

- `kinit student1@LAB.EXAMPLE.TEST`.
- `klist` shows a valid TGT.
- `kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` succeeds.
- Browser/`curl` has GSSAPI support and matching hostname/CA trust.

### Step 4 — Java App

- Select Spring Security Kerberos modules compatible with your Boot major version.
- Configure `service-principal`/keytab path from trusted server config.
- Wire `SpnegoEntryPoint` + `SpnegoAuthenticationProcessingFilter` + `KerberosServiceAuthenticationProvider`.
- Wire local `UserDetailsService` + protected roles.
- Choose stateless-vs-session strategy and CSRF.
- Enable TLS ingress and verify Negotiate headers survive.
- Start the app with the secret file readable only by the process identity.

### Step 5 — Verify Protocol

- No header: `401` Negotiate challenge.
- Valid test user: GSS accepts and role-permitted route passes.
- Wrong SPN, stale keytab, missing keytab: rejected.
- Missing role: 403.
- Locked local account: rejected.
- Repeat/follow-up requests: verify expected `SecurityContext` lifetime and browser behavior.
- Multi-pod: all nodes accept current KVNO.

### Step 6 — Rotation / Cleanup

- Review KDC/keytab ownership and expiry/rotation plan.
- Never re-run `ktadd` per pod to distribute keytabs.
- Rotate via versioned secret distribution, testing overlap/maintenance windows.
- Clear test user ticket caches when finishing the lab as appropriate.
- Never retain raw token captures or keytabs in CI artifacts.
- Disable JAAS/GSS debug and record QA results using sanitized reason codes.

## 22. Pre-Staging Security Checklist

- [ ] KDC realm/trust policy, principal ownership, and service SPN are approved.
- [ ] SPN matches the exact public FQDN/browser URL, avoiding IP literals or unexpected aliases.
- [ ] Service keytab holds only minimal principals and is mounted read-only.
- [ ] User KDC tickets are absent from server keytabs; TGTs are never confused with keytabs.
- [ ] Keytabs are never committed to Git/JAR/Docker images or chats/logs.
- [ ] KVNO/enctypes align between KDC and all app nodes; rotation is planned.
- [ ] KDC/client/SP clocks are synced; skew tolerance is not overly wide.
- [ ] `useKeyTab=true`, `isInitiator=false`, `storeKey=true`, and `doNotPrompt=true` are set for JAAS acceptors.
- [ ] Spring Kerberos dependencies match the right `groupId` for Spring Security 6 vs. 7.
- [ ] Only one SPNEGO filter/owner exists in the Spring Security chain.
- [ ] `SpnegoEntryPoint` emits `401` Negotiate; no login redirect loops.
- [ ] Spring Security provider invokes a real GSS validator rather than trusting raw headers.
- [ ] Principals map by realm/tenant and local account—never using emails/headers as trust roots.
- [ ] Roles/admin privileges are default-deny; locked/disabled users are blocked.
- [ ] `SecurityContextRepository`/session strategy is explicit and tested.
- [ ] User-initiated state-changing POSTs enforce CSRF protection.
- [ ] TLS cert CA/hostname verified; ingress trusted and forwarding headers accurate.
- [ ] GSS Negotiate tokens are never logged, leaked, or rewritten across proxies.
- [ ] Client browser intranet policies / allowed SPNEGO origins are verified.
- [ ] NTLM mechanism fallback is permitted only when risk policy explicitly allows it.
- [ ] Cross-pod GSS, keytab mounts, sessions, and revocations are tested.
- [ ] Logout UX explains that an OS TGT may persist and trigger browser reauthentication.
- [ ] EPA/channel binding and TLS validation are never disabled via legacy workarounds.
- [ ] Lab tests include `401` challenge, valid `200`, missing-role `403`, and malformed-token rejection.
- [ ] Tests cover expired tickets, KDC offline, wrong SPN, wrong KVNO, and node drift.
- [ ] Data/PII privacy: never store raw HTTP `Authorization`, keytabs, PACs, TGTs, or full principals in metrics.
- [ ] Monitoring and runbooks define owners, alert thresholds, rollback, and rotation.
- [ ] The Java 17 demo is clearly distinguished from production GSS cryptographic verification.

## 23. Review Questions

**1. Is SPNEGO the same as username/password Basic auth?**  
No. The browser sends an opaque GSS token via `Authorization: Negotiate`, normally backed by a Kerberos ticket obtained from the KDC.

**2. Is a keytab used on the client or the server?**  
In this exercise, the keytab holds the **service principal's long-term key on the SPNEGO acceptor server**. User clients keep TGTs/tickets in credential caches; never upload a TGT as a keytab.

**3. Why does the HTTP SPN still start with `HTTP/` when the URL uses HTTPS?**  
Because the Kerberos HTTP authentication service class is `HTTP`; HTTPS is a separate TLS transport layer.

**4. Why is `HTTP/pod-a.internal` unsuitable when browsers call `portal.lab.example.test`?**  
Browsers request tickets for the URL's host / canonical SPN, not the backend pod chosen by ingress.

**5. Does `ktadd` change the service key?**  
In MIT Kerberos, `ktadd` randomizes keys and increments KVNO by default. `-norandkey` exports without changing the key when KDC policy permits; never re-run it blindly.

**6. Should a keytab include principal `krbtgt/REALM`?**  
No. A web app needs only its own HTTP service key under least privilege.

**7. What does `isInitiator=false` mean?**  
JAAS logs in as a Kerberos acceptor rather than initiating TGT requests like a client. Requires `useKeyTab`/`storeKey` for the service key.

**8. Is the first `401` an SSO failure?**  
No. It is normally the `WWW-Authenticate: Negotiate` challenge prompting the browser to send a token.

**9. Can an SPNEGO token be decoded like a JWT?**  
No. It is an opaque binary GSS/SPNEGO protocol token, not JSON claims.

**10. Why can a valid Kerberos user still receive `403`?**  
The user lacks local roles or resource authorization; authentication and authorization are independent.

**11. Do Spring Security Kerberos 2.2 and 7 share the same `groupId`?**  
No. Branch 2.2 uses `org.springframework.security.kerberos`; branch 7 uses `org.springframework.security` per docs.

**12. Does `SpnegoAuthenticationProcessingFilter` store `SecurityContext` in `HttpSession` by default?**  
Do not assume so. Current source defaults to a request-level repository; configure `SecurityContextRepository`/session strategy explicitly for persistent sessions.

**13. Can raw `X-User` from ingress be used as the principal?**  
No—unless ingress genuinely verifies GSS, strips client-supplied headers, and authenticates the backend link.

**14. Is running `kinit -kt` with the service keytab as a server keepalive necessary?**  
No. An SPNEGO server is an acceptor; test the keytab via real GSS flows and `klist -kte`.

**15. Does a KDC outage break every request immediately?**  
Not necessarily: clients hold cached TGTs/service tickets that remain valid until expiry. Test actual behavior rather than assuming the KDC is hit on every request.

**16. Can CSRF be disabled because users authenticate with SPNEGO?**  
No. Browsers still auto-send credentials/cookies; state-changing operations require CSRF controls per threat model.

**17. Why does portal logout not guarantee the browser won't auto-login again?**  
The OS/user Kerberos TGT remains valid, letting the browser negotiate a fresh token automatically. Use auth freshness/step-up when needed.

**18. If only Pod B fails GSS after a deploy, what should you inspect?**  
Keytab/SPN/KVNO/enctypes/permissions, Kerberos config, clock skew, and header forwarding on Pod B.

**19. On a channel-binding mismatch, should you disable Windows EPA via the registry?**  
Never casually. Use a supported TLS/proxy/GSS deployment architecture and security review.

**20. Does the Java 17 demo actually verify Kerberos tickets?**  
No. It is a simulated policy oracle; real cryptographic acceptance must run through Java GSS/JAAS via the Spring Kerberos validator.

## 24. Official References

- [Spring Security — Kerberos Introduction (7.x)](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): 7.x release, Java 17, **artifact `groupId` change**.
- [Spring Security Kerberos — Introduction (2.2.x)](https://docs.spring.io/spring-security-kerberos/reference/introduction.html): 2.2.0 release supporting Spring Security 6.5.1/Framework 6.2.8 and Jakarta Servlet.
- [Spring Security — Spring and Spring Security Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, and Java config.
- [Spring Security Kerberos — `SpnegoAuthenticationProcessingFilter` Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): GSS headers, filter behavior, session/context repository.
- [Spring Security Kerberos — `SunJaasKerberosTicketValidator` Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): `setServicePrincipal`, `setKeyTabLocation`, JAAS validator.
- [Oracle JDK 17 — `Krb5LoginModule`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html): `useKeyTab`, `keyTab`, `principal`, `storeKey`, `isInitiator=false`.
- [Oracle JDK 17 — `GSSContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html): `acceptSecContext`, security context mechanism.
- [MIT Kerberos — `krb5.conf`](https://web.mit.edu/kerberos/krb5-latest/doc/admin/conf_files/krb5_conf.html): realm, KDC, and domain mappings.
- [MIT Kerberos — `kadmin` command reference](https://www.mit.edu/~kerberos/krb5-latest/doc/admin/admin_commands/kadmin_local.html): `addprinc -randkey`, `ktadd` key rotation default and `-norandkey`.
- [MIT Kerberos — Application Servers](https://web.mit.edu/kerberos/krb5-latest/doc/admin/appl_servers.html): service keytabs, KVNO, Kerberos app server best practices.
- [RFC 4559 — SPNEGO-based Kerberos HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): `WWW-Authenticate: Negotiate`, `Authorization: Negotiate`.
- [RFC 4120 — Kerberos Network Authentication Service V5](https://www.rfc-editor.org/rfc/rfc4120): KDC/TGT/service tickets, replay/clock properties.
- [RFC 4178 — SPNEGO GSS-API](https://www.rfc-editor.org/rfc/rfc4178): negotiation mechanism security context.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): failure handling, local account status.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, fixation, revocation.
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): browser-driven state-changing requests.

**Takeaway:** A proper SPNEGO integration connects **principals from a Kerberos realm** to the **HTTP SPN matching the public hostname**, secures the **long-term service secret in a protected keytab**, handles `401 Negotiate` challenges, and validates opaque GSS tokens via **JAAS/GSS**. After GSS authentication, you must still enforce local user enabled/locked/role policies, sessions/CSRF, and authorization. When the lab breaks, troubleshoot in order: **kinit → kvno → keytab/KVNO/enctype → HTTP headers/proxy → GSS validator → Spring authorities**; never disable verification, log raw tickets, or blindly reset keytabs just to "make login work".