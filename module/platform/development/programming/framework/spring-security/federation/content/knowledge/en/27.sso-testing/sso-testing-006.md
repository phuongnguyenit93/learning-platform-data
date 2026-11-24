# Testing SPNEGO with a Test KDC, Keytab, and Matching Service Principal

## 1. Objectives and Completion Criteria

In HTTP, **SPNEGO (Simple and Protected GSS-API Negotiation Mechanism)** allows a server to send a **401 WWW-Authenticate: Negotiate** challenge, and the client builds a **GSS token** and sends **Authorization: Negotiate**. With Kerberos, the client needs a service ticket issued by the KDC for the proper HTTP principal. Spring Security Kerberos must use a **server-side keytab** to verify the ticket before deciding whether the local user is authorized.

An end-to-end test requires evidence across every layer: **test KDC running → test user holds a TGT → KDC issues a service ticket for the exact `HTTP/FQDN` → app keytab has matching principal/KVNO/enctype → DNS/TLS/proxy aligned → client sends Negotiate → Java GSS acceptor validates → local `UserDetailsService` authorizes the right principal**.

An HTTP 200 on a public endpoint, or the browser not showing a password prompt, is **insufficient** to prove Kerberos SSO. There might be a cookie session, reverse proxy auth, or NTLM fallback. You must test both success and fail-closed rejection.

This lesson belongs to **SSO Testing** in **Spring Security - federation**. Examples use **Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring Security Kerberos extension 2.1.0**, and MIT Kerberos on Ubuntu/Debian. Realms, hosts, and `example.org` addresses are synthetic lab values, not pre-provisioned infrastructure.

## 2. Lab Topology and Key Values

~~~text
               Test KDC
               kdc.lab.example.org
               REALM LAB.EXAMPLE.ORG
                   TCP/UDP 88
                       |
             AS-REQ / TGS-REQ
                       |
           Client alice@LAB.EXAMPLE.ORG
             TGT and HTTP service ticket
                       |
                       | HTTPS GET /private
                       v
               app.lab.example.org
               401 Negotiate challenge
               Authorization: Negotiate token
                       |
              Spring Security acceptor
              SPN HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
              Keytab /etc/security/keytabs/http-app.keytab
                       |
              Verified Kerberos principal
              UserDetailsService and local authorities
                       |
                   200 or 401/403
~~~

| Component | Lab Value | Constraint |
| --- | --- | --- |
| Kerberos realm | **LAB.EXAMPLE.ORG** | KDC database, `krb5.conf`, principal suffix. |
| KDC FQDN | **kdc.lab.example.org** | DNS, KDC config, and port 88. |
| Public URL | **https://app.lab.example.org/private** | Hostname, HTTPS certificate, SPN. |
| Service principal | **HTTP/app.lab.example.org@LAB.EXAMPLE.ORG** | KDC principal, keytab, Java validator. |
| Service keytab | **/etc/security/keytabs/http-app.keytab** | OS permissions, KVNO, encryption types. |
| Test user | **alice@LAB.EXAMPLE.ORG** | `kinit`, client cache, local account. |
| Spring internal listener | **http://app-pod:8080** | Backend only; not the public HTTP SPN. |

The **Service Principal Name (SPN)** is bound to the hostname the client uses to reach the service. If the browser opens `portal.lab.example.org` while the keytab only holds `HTTP/app.lab.example.org`, the KDC/client may pick a ticket for another hostname and Java cannot accept it. DNS CNAMEs, reverse DNS, load balancers, and hostname canonicalization must follow a consistent policy. In Active Directory, never assign the same SPN haphazardly across multiple service accounts.

## 3. Kerberos TGT, Service Ticket, KVNO, and Keytab

~~~text
AS exchange:
  alice authenticates with KDC -> TGT krbtgt/LAB.EXAMPLE.ORG

TGS exchange:
  client uses TGT to request ticket HTTP/app.lab.example.org

HTTP Negotiate:
  server returns 401 WWW-Authenticate: Negotiate
  client sends Authorization: Negotiate with GSS token

Java acceptor:
  uses HTTP/app.lab.example.org keytab to validate service ticket
  -> authenticates alice@LAB.EXAMPLE.ORG

Local authorization:
  UserDetailsService / IAM -> account active + authorities
~~~

**A TGT is not a service ticket**. `kinit` obtains a TGT, whereas `kvno` requests a service ticket for the exact SPN. **A keytab is a secret holding service key material**, not a TLS certificate. It must stay on authorized app servers/secret stores—never in Git, email, chat, CI logs, or clients.

**KVNO** is the key version number. When rotating service principal keys, an older keytab may fail to decrypt newly issued tickets. **MIT `ktadd` normally randomizes service keys and increments KVNO** upon exporting a keytab; re-running `ktadd` on a live principal without rolling out the new keytab can cause an outage.

**Enctype** is the encryption type of the key/ticket; it must be compatible across the KDC, Java 17, and Kerberos policy. Never enable weak DES/RC4 just to pass a test. Keytab secrets and HTTPS TLS serve distinct purposes, and both must be configured properly.

## 4. Safety Conditions When Practicing

- Create principals and run `kdb5_util`, `kadmin.local`, and `ktadd` only on an **isolated, authorized lab KDC**. Never use production AD/KDC.
- Never distribute keytabs to browsers or leave secrets world-readable. Only the app process may read the service keytab file.
- DNS/hosts for the KDC and app must resolve accurately in the test network; open Kerberos TCP/UDP port 88 only to permitted hosts.
- If using `kadmind` on TCP 749 for remote administration, restrict it to the admin network. Alternatively, use `kadmin.local` directly on the KDC without exposing the admin service.
- Synchronize NTP/UTC across the KDC, client, and Spring server. Never widen clock skew to hours or disable replay checks.
- HTTPS certificates must carry valid hostnames trusted by clients; never use `curl -k` as a final security QA pass.
- Record redacted traces only; never save raw `Authorization: Negotiate` tokens, TGTs, service tickets, keytabs, or passwords.
- After finishing the lab, clean up test principals/keys/credential caches per procedure without touching real users' tickets.

## 5. Installing an MIT Kerberos Test KDC

The following examples assume a **fresh KDC on Ubuntu/Debian**. Service/database paths vary by distro and image, so verify package/version before initializing. **Never run `kdb5_util create` on a realm containing existing data.**

### 5.1. Packages and `krb5.conf`

~~~bash
sudo apt-get update
sudo apt-get install -y krb5-kdc krb5-admin-server krb5-user
~~~

File **/etc/krb5.conf** on KDC, client, and app server:

~~~ini
[libdefaults]
    default_realm = LAB.EXAMPLE.ORG
    dns_lookup_realm = false
    dns_lookup_kdc = false
    rdns = false

[realms]
    LAB.EXAMPLE.ORG = {
        kdc = kdc.lab.example.org
        admin_server = kdc.lab.example.org
    }

[domain_realm]
    .lab.example.org = LAB.EXAMPLE.ORG
    lab.example.org = LAB.EXAMPLE.ORG
~~~

**`rdns=false`** reduces certain MIT krb5 reverse-DNS canonicalizations, yet it does not guarantee every Java/Windows/browser client picks identical SPNs. Check the actual hostname requested in the service ticket after `kvno`.

### 5.2. KDC Configuration

File **/etc/krb5kdc/kdc.conf**, on the KDC host only:

~~~ini
[kdcdefaults]
    kdc_ports = 88
    kdc_tcp_ports = 88

[realms]
    LAB.EXAMPLE.ORG = {
        database_name = /var/lib/krb5kdc/principal
        acl_file = /etc/krb5kdc/kadm5.acl
        key_stash_file = /etc/krb5kdc/stash
        max_life = 10h 0m 0s
        max_renewable_life = 7d 0h 0m 0s
        default_principal_flags = +preauth
    }
~~~

Some newer MIT Kerberos versions use settings like **`kdc_listen`** and **`kdc_tcp_listen`**. Confirm option names for your version and verify the daemon listens on TCP/UDP 88. The database path must match where `kdb5_util` creates the database.

Lab-only ACL in **/etc/krb5kdc/kadm5.acl**:

~~~text
labadmin/admin@LAB.EXAMPLE.ORG *
~~~

This line grants broad admin rights to the test principal; **never put that ACL into production**.

### 5.3. Creating the Realm and Principals

~~~bash
# Only on a FRESH LAB KDC, with interactive master password.
sudo kdb5_util create -s -r LAB.EXAMPLE.ORG

# Two user principals with interactively entered passwords.
sudo kadmin.local -q "addprinc labadmin/admin@LAB.EXAMPLE.ORG"
sudo kadmin.local -q "addprinc alice@LAB.EXAMPLE.ORG"

# Random service key, used for keytab.
sudo kadmin.local -q "addprinc -randkey HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"

sudo systemctl enable --now krb5-kdc
sudo systemctl enable --now krb5-admin-server
sudo systemctl status krb5-kdc
~~~

Never save master/user passwords in shell history. If a daemon fails to start, inspect the KDC database/stash, config paths, file permissions, and ports. On distros without systemd, check the corresponding service manager.

### 5.4. Exporting the Keytab and Protecting the Secret

On the lab KDC:

~~~bash
sudo install -d -m 0700 /etc/security/keytabs
sudo kadmin.local -q "getprinc HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"
sudo kadmin.local -q "ktadd -k /etc/security/keytabs/http-app.keytab HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"
sudo klist -kte /etc/security/keytabs/http-app.keytab
~~~

The output must show entry **`HTTP/app.lab.example.org@LAB.EXAMPLE.ORG`** with matching KVNO/enctype; never assume KVNO is always 1.

Transfer the keytab to the app server over a managed secure channel, place it at **/etc/security/keytabs/http-app.keytab**, owned by the OS account running Java and readable only via mode **0400/0600** or an equivalent ACL. Never copy keytabs to clients or embed them in a Spring JAR.

On the app server, run as the exact app OS user:

~~~bash
klist -kte /etc/security/keytabs/http-app.keytab
test -r /etc/security/keytabs/http-app.keytab && echo KEYTAB_READABLE
~~~

**`klist -kte`** only checks that the file contains a principal, KVNO, and enctypes. It **does not prove Java will accept service tickets**. When rotating keys, ensure the matching keytab version is distributed to all app nodes before or at rollout time.

## 6. Checking TGT and HTTP Service Ticket from the Client

On a test client with matching realm/DNS/time:

~~~bash
kinit alice@LAB.EXAMPLE.ORG
klist -e
kvno HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
klist -e
~~~

**Interpretation:**

1. **`kinit`** must obtain a TGT for **`alice@LAB.EXAMPLE.ORG`** in an unexpired principal cache.
2. **`kvno`** asks the KDC/TGS to issue a service ticket for **`HTTP/app.lab.example.org@LAB.EXAMPLE.ORG`**. It prints the actual KVNO, which is not fixed across environments.
3. **`klist`** after `kvno` should display the service ticket alongside the TGT in the right cache.
4. If `kinit` fails: check username/password, realm, KDC DNS/port 88, and time.
5. If `kvno` reports **Server not found in Kerberos database**: the HTTP SPN is missing or the FQDN/realm is wrong.
6. If the client lacks a service ticket, you **cannot conclude the fault is in Spring**.

A client holding a valid cached service ticket can sometimes still use that ST even after its TGT expires. Therefore, to test a fresh TGS exchange, use an isolated test credential cache rather than clearing production user caches.

| Command | What It Proves | What It Does Not Prove |
| --- | --- | --- |
| **`kinit`** | Obtains a TGT. | No HTTP service ticket yet. |
| **`kvno`** | KDC issues a ticket for the exact SPN. | Does not prove Java keytab acceptance. |
| **`klist -kte`** | Keytab contains principal/KVNO/enctypes. | Does not prove HTTP GSS succeeds. |
| **`401 Negotiate`** | Server demands authentication. | No token accepted yet. |
| **`HTTP 200 protected`** | Request passed the authz chain. | Must verify no session/NTLM/spoofed headers used. |

## 7. DNS, Hostname, Proxy, TLS, and SPN

~~~text
Public browser URL:
  https://app.lab.example.org/private

Kerberos service principal:
  HTTP/app.lab.example.org@LAB.EXAMPLE.ORG

Spring backend:
  http://app-pod:8080

Keytab on Java:
  HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
~~~

**The public URL FQDN, service principal, and keytab must align**, even when the backend uses a container hostname. If a client connects via IP or `localhost`, the requested service name differs; that is not a valid test of the public SPN.

Proxies must forward **`Authorization: Negotiate`** to Java if Spring acts as the acceptor. Proxies must never turn a browser-supplied **`X-Remote-User`/`X-User`** header into a verified identity. If the proxy itself acts as the GSS acceptor, the backend needs a separate network/mTLS trust boundary and verified headers; the Spring sample below does not apply verbatim.

All backend nodes accepting service tickets for the same HTTP SPN need consistent keytab/key versions. If DNS aliases/CNAMEs are used, test client canonicalization; never assume aliases match automatically.

The public TLS certificate must be trusted with a SAN matching the FQDN. To test a lab CA, use **`curl --cacert`**. Never disable TLS verification or Windows Extended Protection/channel binding just to turn a test green.

## 8. Spring Boot 3.3.5: SPNEGO Acceptor Using a Real Keytab

### Maven `pom.xml`

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
  <artifactId>spnego-lab</artifactId>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

This is **Spring Security Kerberos extension 2.x** for Spring Security 6.x; `starter-security` does not bundle SPNEGO on its own. Verify dependency versions and security patches before production use.

### `application.yml`

~~~yaml
server:
  port: 8080

lab:
  kerberos:
    principal: "HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"
    keytab: "/etc/security/keytabs/http-app.keytab"
~~~

### Main Class

**src/main/java/com/example/spnegolab/SpnegoLabApplication.java**

~~~java
package com.example.spnegolab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpnegoLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpnegoLabApplication.class, args);
    }
}
~~~

### `SecurityConfig.java`

**src/main/java/com/example/spnegolab/SecurityConfig.java**

~~~java
package com.example.spnegolab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
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
    SecurityContextRepository repository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
    }

    @Bean
    UserDetailsService localUsers() {
        return principal -> {
            if (!"alice@LAB.EXAMPLE.ORG".equals(principal)) {
                throw new UsernameNotFoundException(
                    "Kerberos principal not provisioned locally");
            }
            return User.withUsername(principal)
                .password("{noop}not-used-in-kerberos")
                .authorities("ROLE_EMPLOYEE")
                .build();
        };
    }

    @Bean
    SunJaasKerberosTicketValidator validator(Environment env) {
        SunJaasKerberosTicketValidator v =
            new SunJaasKerberosTicketValidator();
        v.setServicePrincipal(
            env.getRequiredProperty("lab.kerberos.principal"));
        v.setKeyTabLocation(new FileSystemResource(
            env.getRequiredProperty("lab.kerberos.keytab")));
        return v;
    }

    @Bean
    KerberosServiceAuthenticationProvider provider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService localUsers) {
        KerberosServiceAuthenticationProvider p =
            new KerberosServiceAuthenticationProvider();
        p.setTicketValidator(validator);
        p.setUserDetailsService(localUsers);
        return p;
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            SecurityContextRepository repository,
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
                .requestMatchers("/lab-health").permitAll()
                .anyRequest().authenticated())
            .securityContext(context -> context
                .securityContextRepository(repository))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationProvider(provider)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);
        return http.build();
    }
}
~~~

**Mechanism:**

- **`SpnegoEntryPoint`** returns `401 Negotiate` for unauthenticated protected requests.
- **`SpnegoAuthenticationProcessingFilter`** reads `Authorization: Negotiate` and passes the token to `ProviderManager`.
- **`KerberosServiceAuthenticationProvider + SunJaasKerberosTicketValidator`** validates Kerberos using the server-side principal and keytab.
- **`UserDetailsService`** accepts only provisioned verified Alice; Bob holding a valid service ticket still does not receive `ROLE_EMPLOYEE`.
- **`SecurityContextRepository`** is wired consistently into both Spring and the custom filter; **`ChangeSessionIdAuthenticationStrategy`** mitigates session fixation.
- There is no logic reading usernames from unverified headers or creating an `Authentication` when the keytab fails.

### `LabController.java`

**src/main/java/com/example/spnegolab/LabController.java**

~~~java
package com.example.spnegolab;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {
    @GetMapping("/lab-health")
    public Map<String, String> health() {
        return Map.of("service", "spnego-lab", "route", "public");
    }

    @GetMapping("/private")
    public Map<String, String> privatePage(Authentication auth) {
        return Map.of(
            "principal", auth.getName(),
            "result", "VERIFIED_BY_SERVER");
    }
}
~~~

The value `VERIFIED_BY_SERVER` is only a demo label and does not prove the GSS mechanism by itself. Verify against a real service ticket/KDC and validator.

### Startup

~~~bash
export JAVA_TOOL_OPTIONS="-Djava.security.krb5.conf=/etc/krb5.conf"
mvn spring-boot:run
~~~

The app needs an OS user permitted to read the keytab, valid KDC/realm config, and public HTTPS ingress. Without a real KDC/keytab, you can only verify compilation/parts of the configuration—**never declare SPNEGO E2E passing**.

## 9. Testing HTTP Negotiate with `curl`

On a **test client where Alice has successfully run `kinit` and `kvno` for the HTTP service**:

~~~bash
curl --version
curl --negotiate -u : --cacert /path/to/lab-ca.pem -i https://app.lab.example.org/private
~~~

`curl` must be built with GSS-API/SSPI or SPNEGO support. Per the manpage, **`-u :`** merely activates HTTP authentication rather than sending an empty Kerberos password; credentials come from the OS/GSS cache.

**Pass condition:** the protected endpoint challenges with `401 Negotiate` when no app session exists; the client uses the right service ticket, the Spring validator accepts the token, and the final HTTP response returns **200 + principal `alice@LAB.EXAMPLE.ORG`**. The exact number of HTTP round-trips depends on the client and is not fixed at two requests.

**Anonymous test:**

~~~bash
curl --cacert /path/to/lab-ca.pem -i https://app.lab.example.org/private
~~~

Without Negotiate credentials, the protected resource must disclose no private content and typically returns `401 WWW-Authenticate: Negotiate`.

**Do not treat `/lab-health` returning 200 as proof of SSO**; that is a public route. Verbose/trace `curl` output can log `Authorization` headers and GSS tokens—never upload raw traces to issue trackers or CI.

## 10. Browser Integrated Windows Authentication

For browsers on managed workstations:

1. Visit **`https://app.lab.example.org/private`** rather than an IP address or `localhost`.
2. The IWA allowlist/intranet zone must include only managed lab hosts, never wildcard all sites.
3. The OS user must hold a Kerberos TGT/service ticket in the credential cache or be able to request one.
4. If the browser already holds an `HttpSession`, subsequent requests may skip a fresh GSS exchange; use a fresh profile/session when testing authentication.
5. Some clients fall back to NTLM inside Negotiate; **never call that a Kerberos-only PASS** based solely on seeing the HTTP header.
6. When Extended Protection/channel binding policy is active, verify compatible TLS termination, proxies, and GSS acceptor; never disable global protections to work around failures.
7. Logging out of `HttpSession` in Spring **does not clear OS TGTs/STs**, so the browser may silently re-authenticate via Kerberos and create a new session.

## 11. Standalone Java 17: Preflight Policy Test

**`SpnegoLabPreflight.java`** does not contact a KDC or verify tickets. It checks **simulated pre-integration configuration**, helping catch mismatches across URL host, SPN, keytab, and request headers. A `PASS CONFIG_READY` result only confirms the sample inputs are consistent, not that Kerberos authentication succeeded.

~~~java
public class SpnegoLabPreflight {
    static final String HOST = "app.lab.example.org";
    static final String REALM = "LAB.EXAMPLE.ORG";

    record Setup(String urlHost, String requestedSpn,
        String keytabSpn, boolean keytabReadable,
        boolean tlsTrusted, boolean hasTgt,
        boolean headerForwarded, boolean accountEnabled) {}

    static String check(Setup s) {
        String expected = "HTTP/" + HOST + "@" + REALM;
        if (!HOST.equals(s.urlHost())) return "FAIL URL_HOST";
        if (!expected.equals(s.requestedSpn())) {
            return "FAIL SERVICE_PRINCIPAL";
        }
        if (!expected.equals(s.keytabSpn())) {
            return "FAIL KEYTAB_PRINCIPAL";
        }
        if (!s.keytabReadable()) return "FAIL KEYTAB_UNREADABLE";
        if (!s.tlsTrusted()) return "FAIL TLS_TRUST";
        if (!s.hasTgt()) return "FAIL CLIENT_TGT_MISSING";
        if (!s.headerForwarded()) return "FAIL NEGOTIATE_HEADER";
        if (!s.accountEnabled()) return "FAIL LOCAL_ACCOUNT";
        return "PASS CONFIG_READY";
    }

    static void show(String label, Setup s) {
        System.out.println(label + ": " + check(s));
    }

    public static void main(String[] args) {
        String p = "HTTP/app.lab.example.org@LAB.EXAMPLE.ORG";
        show("baseline", new Setup("app.lab.example.org", p, p,
            true, true, true, true, true));
        show("alias url", new Setup("portal.lab.example.org", p, p,
            true, true, true, true, true));
        show("wrong spn", new Setup("app.lab.example.org",
            "HTTP/wrong.lab.example.org@LAB.EXAMPLE.ORG", p,
            true, true, true, true, true));
        show("wrong keytab", new Setup("app.lab.example.org", p,
            "HTTP/other.lab.example.org@LAB.EXAMPLE.ORG",
            true, true, true, true, true));
        show("keytab unreadable", new Setup("app.lab.example.org", p, p,
            false, true, true, true, true));
        show("untrusted tls", new Setup("app.lab.example.org", p, p,
            true, false, true, true, true));
        show("no tgt", new Setup("app.lab.example.org", p, p,
            true, true, false, true, true));
        show("header stripped", new Setup("app.lab.example.org", p, p,
            true, true, true, false, true));
        show("account disabled", new Setup("app.lab.example.org", p, p,
            true, true, true, true, false));
    }
}
~~~

Run:

~~~bash
javac SpnegoLabPreflight.java
java SpnegoLabPreflight
~~~

**Exact stdout:**

~~~text
baseline: PASS CONFIG_READY
alias url: FAIL URL_HOST
wrong spn: FAIL SERVICE_PRINCIPAL
wrong keytab: FAIL KEYTAB_PRINCIPAL
keytab unreadable: FAIL KEYTAB_UNREADABLE
untrusted tls: FAIL TLS_TRUST
no tgt: FAIL CLIENT_TGT_MISSING
header stripped: FAIL NEGOTIATE_HEADER
account disabled: FAIL LOCAL_ACCOUNT
~~~

A client with a valid cached ST can still use it after its TGT expires; the `no tgt` test represents a **preflight check starting from a fresh TGT**, not the entire credential cache lifecycle. Never accept booleans from a client as proof to grant `Authentication` in a real application.

## 12. E2E and Negative Testing Procedure

**A. KDC test:**

~~~bash
kinit alice@LAB.EXAMPLE.ORG
klist -e
kvno HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
klist -e
~~~

You must see both the TGT and ST for the right principal; if `kinit`/`kvno` fails, you have not even reached the HTTP layer.

**B. Acceptor test:** on the app server, verify keytab/KVNO/enctypes and read permissions as the app OS user; start Spring; anonymous `GET /private` must yield a `401` challenge.

**C. HTTP positive:** `curl --negotiate -u :` over trusted-CA HTTPS to `/private`; final result is 200 verified Alice with evidence from the Java GSS/validator and a real service ticket.

**D. Negative local account:** create Bob on the **lab KDC** and test the same HTTP service; Bob can obtain a valid ST yet the demo provisions only Alice, so access is denied.

~~~bash
# Run ONLY on the LAB KDC:
sudo kadmin.local -q "addprinc bob@LAB.EXAMPLE.ORG"

# On Bob's authorized test client:
kinit bob@LAB.EXAMPLE.ORG
kvno HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
curl --negotiate -u : --cacert /path/to/lab-ca.pem -i https://app.lab.example.org/private
~~~

**E. Wrong SPN:** run `kvno` for a nonexistent service, e.g., `HTTP/wrong.lab.example.org@LAB.EXAMPLE.ORG`. The KDC must refuse to issue a ticket for a nonexistent service.

**F. Wrong keytab/KVNO:** on an **isolated lab app instance**, use a keytab from another service or an older keytab snapshot after controlled key rotation. The GSS acceptor must reject it. **Never rotate a production principal just to run a negative test**.

**G. Time/replay:** use disposable VMs/containers/test harnesses to test expired tickets, clock skew, and replays; never adjust production clocks or disable replay verification.

**H. Multi-node:** verify consistent keytabs/KVNOs, `krb5.conf`, JDKs, host headers, and secrets across every node.

**I. Logout:** the Spring session is invalidated, yet the OS TGT remains so the browser can re-login; distinguish old sessions from fresh authentications.

## 13. Test Matrix

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | Valid lab KDC and user Alice | `kinit` obtains TGT. |
| 2 | Exact HTTP service principal | `kvno` obtains ST. |
| 3 | Matching keytab principal/KVNO/enctype | Acceptor can validate. |
| 4 | `curl` GSSAPI, trusted HTTPS, exact FQDN | Kerberos E2E succeeds. |
| 5 | Anonymous unauthenticated request | Cannot read private resource. |
| 6 | Public health returns 200 | Never treated as SSO PASS. |
| 7 | Bob holds ST yet unprovisioned in app | Local account denied. |
| 8 | Valid TGT, KDC reachable, no ST yet | Can obtain a fresh ST. |
| 9 | Expired TGT, unexpired cached ST | Can still authenticate with cached ST. |
| 10 | Neither TGT nor ST present | No silent SSO. |
| 11 | Alias URL differs from HTTP SPN | Fails or requires explicit alias SPN. |
| 12 | URL uses IP/localhost | Not a standard test for public SPN. |
| 13 | Keytab contains another HTTP service | Rejected. |
| 14 | Wrong keytab realm | Rejected. |
| 15 | App user cannot read keytab | Fails; never `chmod` world-readable. |
| 16 | Empty keytab | Fails. |
| 17 | Key rotated while app holds old keytab | KVNO mismatch; rejected. |
| 18 | Incompatible enctype | Rejected; never enable weak crypto. |
| 19 | KDC port 88/DNS unreachable | `kinit`/`kvno` fail. |
| 20 | Excessive client/KDC clock skew | Kerberos fails. |
| 21 | Excessive client/server clock skew | Authenticator fails. |
| 22 | Browser lacks IWA allowlist entry | May not send Negotiate. |
| 23 | `curl` lacks SPNEGO/GSS support | Cannot run that test. |
| 24 | Untrusted TLS certificate | TLS fails; never use `-k` for QA PASS. |
| 25 | Proxy strips `Authorization` header | Java never receives the token. |
| 26 | Client spoofs `X-Remote-User` header | Never becomes a Kerberos principal. |
| 27 | NTLM fallback | Never record as Kerberos-only PASS. |
| 28 | Malformed/replayed GSS token | Rejected. |
| 29 | Expired ST | Rejected per Kerberos policy. |
| 30 | Kerberos verified, local account disabled | Denied. |
| 31 | User lacks tenant/business role | 403 on protected API. |
| 32 | Request reuses old `HttpSession` | Does not prove fresh GSS. |
| 33 | App logout while OS TGT active | Can re-authenticate. |
| 34 | Keytabs differ across LB nodes | Node-specific failures. |
| 35 | CNAME changes canonical hostname | Inspect exact SPN requested by client. |
| 36 | KDC offline with cached ST | May still authenticate. |
| 37 | KDC offline with no ST | Cannot request new ticket. |
| 38 | Logs contain `Authorization` token/keytab | Security QA FAIL. |
| 39 | Channel binding mismatch | Analyze TLS/EP; never disable protection. |
| 40 | SPN in another realm with same short name | Never auto-map user. |
| 41 | Keytab secret leaked to Git/CI | Rotate/revoke per incident runbook. |
| 42 | User opens new browser profile with OS TGT | Silent SSO may occur. |

## 14. Troubleshooting

| Symptom | Cause and Where to Check |
| --- | --- |
| `kinit` cannot reach KDC | DNS, `krb5.conf`, firewall port 88, daemon status. |
| `kinit` preauthentication failed | Wrong user/password, clock, realm policy. |
| `kvno` Server not found | Wrong or missing `HTTP/FQDN/realm` SPN. |
| `klist` shows only TGT | ST not yet requested; run `kvno`. |
| `klist -kte` lacks exact HTTP principal | Wrong keytab exported or deployed. |
| Cannot find key of appropriate type | Enctype/keytab/JDK compatibility. |
| Checksum failed / decrypt error | Stale keytab, wrong KVNO, wrong principal. |
| `KRB_AP_ERR_SKEW` | Synchronize NTP/UTC. |
| `KRB_AP_ERR_REPEAT` | Check replay/authenticator; never disable protection. |
| `curl` does not support Negotiate | Binary built without GSSAPI/SSPI. |
| Browser fails to auto-Negotiate | Hostname/IWA allowlist/OS ticket. |
| HTTP 401 loop | KDC, keytab, SPN, `Authorization` header, validator, local user mapping. |
| HTTP 200 anonymous | `AuthorizationFilter`, `HttpSession`, or proxy bypass. |
| HTTP 403 after Kerberos passes | Local roles/tenant not granted. |
| App Node A passes, Node B fails | Mismatched secret versions, config, `krb5.conf`, or JDK. |
| Channel binding mismatch | TLS termination/Extended Protection/GSS mismatch. |
| Browser auto-logs back in after logout | OS Kerberos tickets are still valid. |

You can enable **`-Dsun.security.krb5.debug=true`** in the lab with log access controls to inspect layer-by-layer errors; never enable it in production or emit raw tokens/secrets.

## 15. CI and MiniKdc

CI can use an **ephemeral MIT KDC container** or **Apache Directory MiniKdc** to create realms/principals/keytabs for tests. You still need test DNS/FQDN, a trusted TLS CA, secret injection, test user Bob, faulty SPN/KVNO tests, and credential cache cleanup. MiniKdc is useful for Java integration, **not a replacement** for enterprise staging AD/GPO/NTLM/browser/IIS proxy/channel binding.

**Evidence hierarchy:** (1) offline Java preflight proves sample policy only; (2) MockMvc proves Spring HTTP filters/authorization only; (3) `kinit`/`kvno` proves KDC/TGS only; (4) `curl --negotiate` through Spring proves end-to-end Kerberos HTTP; (5) browser AD staging proves enterprise policy/compatibility. Never conflate these layers into one.

## 16. Production-Like Lab Checklist

- [ ] Isolated test KDC, accurate realm and DNS, port 88 reachable.
- [ ] Client `kinit` holds a TGT and `kvno` obtains an ST for the exact HTTP SPN.
- [ ] Server-only keytab with exact principal/KVNO/enctype, readable solely by the app user.
- [ ] Public host, TLS SAN, browser URL, and principal match.
- [ ] `curl --negotiate -u :` has GSSAPI/SSPI support and uses a trusted CA.
- [ ] Spring filter/provider/JAAS validator genuinely validates tokens.
- [ ] `UserDetailsService`/local IAM provisions only authorized accounts/roles.
- [ ] Anonymous, Bob, wrong SPN, wrong keytab, expired, and replayed requests are rejected.
- [ ] Proxy forwards `Authorization` and never trusts client-supplied `X-User`.
- [ ] HA nodes share consistent keytabs and configuration.
- [ ] Browser IWA allowlist is controlled without unintended NTLM fallback.
- [ ] No raw tokens/keytabs logged; secret rotation/cleanup plan exists.

## 17. Review Questions

**1. Does a successful `kinit` prove SPNEGO works?** No, it only obtains a TGT; you must still verify ST issuance, the acceptor keytab, HTTP Negotiate, and local authorization.

**2. Should the SPN use the public FQDN or pod hostname?** The public FQDN accessed/canonicalized by clients, e.g., `HTTP/app.lab.example.org@LAB.EXAMPLE.ORG`.

**3. Why can re-running `ktadd` break the application?** Because service keys/KVNO may change while the app still holds the old keytab.

**4. Does `curl -u :` send an empty password to log in?** No, it simply activates the HTTP Negotiate code path; Kerberos credentials come from the OS cache.

**5. If the browser does not prompt for a password, is Kerberos definitely working?** No; it could be a session cookie, NTLM, or proxy authentication.

**6. Is it abnormal for Bob to hold a real ticket yet be rejected?** No; local account policy can deny Bob after Kerberos authentication.

**7. Should a keytab be committed to Git?** No; a keytab is a secret credential of the service acceptor.

**8. What happens if the TGT expires while the service ticket is still valid?** The client can continue using the cached ST per GSS policy.

**9. Should TLS validation or replay checks be disabled to fix a lab?** No; fix the CA, clocks, service keys, and configuration instead.

**10. Does Spring logout clear the OS TGT?** No; the user can silently re-authenticate and start a new app session.

## 18. Official Documentation

1. [Spring Security Kerberos Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): `SpnegoEntryPoint`, filter, provider, and `SunJaasKerberosTicketValidator`.
2. [Spring Security Kerberos 2.1.x API](https://docs.spring.io/spring-security-kerberos/docs/2.1.x/api/allclasses-index.html): API and `MiniKdc`.
3. [MIT Kerberos Installing KDCs](https://web.mit.edu/kerberos/www/krb5-1.15/doc/admin/install_kdc.html): creating a realm/KDC.
4. [MIT Kerberos `krb5.conf`](https://www.mit.edu/~kerberos/krb5-devel/doc/admin/conf_files/krb5_conf.html): realm/KDC mapping.
5. [MIT Kerberos `kdc.conf`](https://www.mit.edu/~kerberos/krb5-current/doc/admin/conf_files/kdc_conf.html): KDC config.
6. [MIT Kerberos `kadmin.local`](https://www.mit.edu/~kerberos/krb5-latest/doc/admin/admin_commands/kadmin_local.html): `addprinc` and `ktadd`.
7. [MIT `kinit`](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kinit.html), [`klist`](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html), [`kvno`](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html): testing credentials.
8. [`curl --negotiate`](https://curl.se/docs/manpage.html): GSSAPI/SSPI with `-u :`.
9. [RFC 4120 Kerberos V5](https://www.rfc-editor.org/rfc/rfc4120): TGT/TGS/ST/replay.
10. [RFC 4559 HTTP SPNEGO](https://www.rfc-editor.org/rfc/rfc4559): HTTP Negotiate.
11. [RFC 4178 SPNEGO](https://www.rfc-editor.org/rfc/rfc4178): GSS negotiation.
12. [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContext`/session fixation.

**Conclusion:** SPNEGO testing must prove **test KDC → user TGT → exact `HTTP/FQDN` service ticket → keytab KVNO/enctype → HTTPS Negotiate → Spring GSS acceptor → local authorization**. Failures must be fixed at the proper KDC/DNS/SPN/keytab/clock/TLS/browser/proxy/Spring layer—never lower security just to get an HTTP 200.
