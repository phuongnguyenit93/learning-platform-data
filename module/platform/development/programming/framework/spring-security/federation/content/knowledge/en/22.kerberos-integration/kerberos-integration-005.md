# SunJaasKerberosTicketValidator, Service Principal, and Keytab

**Module:** Spring Security – federation  
**Knowledge Group:** Kerberos Integration  
**Learning Stack:** Kerberos V5, HTTP SPNEGO/Negotiate, JDK JAAS/JGSS, Spring Security Kerberos **2.2.0**, Spring Security **6.5.x**, compatible Spring Boot **3.x**, Java **17+**.

## 1. Problem: Authenticating Users with a Ticket Scoped to the Website

In an Active Directory (AD) or Kerberos KDC environment, employees logged into a corporate machine can open an internal website and be recognized without re-entering their password. The browser and application execute the **HTTP Negotiate / SPNEGO** mechanism. The Spring Security application must verify the Kerberos ticket sent by the browser, rather than trusting a username attached directly in a header.

Three most important components:

1. **SunJaasKerberosTicketValidator:** server-side Kerberos/SPNEGO service ticket validator using JAAS/JGSS and the Sun/Oracle/OpenJDK Kerberos implementation.
2. **Service principal (SPN):** Kerberos identity of the HTTP service requested by the browser, such as **HTTP/portal.example.org@EXAMPLE.ORG**.
3. **Keytab:** file containing long-term secret keys for the service principal; the server uses it to accept Kerberos tickets that the KDC encrypted for that service.

To feed the result into Spring Security, we use **SpnegoAuthenticationProcessingFilter** and **KerberosServiceAuthenticationProvider**. After the ticket is verified, UserDetailsService loads local permissions/roles. A ticket with a valid signature/key **does not** automatically mean permission to read records, approve invoices, or hold ROLE_ADMIN.

**Learning principle:** the SPN and keytab belong to the **service**, whereas the Kerberos principal inside the ticket belongs to the **user**. Never use a user principal as the service principal or store user passwords inside the application's keytab.

## 2. Overview of the HTTP/SPNEGO Flow

~~~text
Browser (ALICE)               Spring web app                  KDC / Active Directory
       |                             |                                  |
       | GET /private                |                                  |
       |---------------------------->|                                  |
       |<----------------------------| 401 WWW-Authenticate: Negotiate  |
       |                             |                                  |
       | Request ticket for          |                                  |
       | HTTP/portal.example.org     |                                  |
       |---------------------------------------------------------------->|
       |<----------------------------------------------------------------|
       | service ticket issued specifically for HTTP/portal.example.org |
       |                             |                                  |
       | GET /private                |                                  |
       | Authorization: Negotiate ...|                                  |
       |---------------------------->| SpnegoAuthenticationFilter       |
       |                             | KerberosServiceProvider          |
       |                             | SunJaasKerberosTicketValidator   |
       |                             | JAAS/JGSS using SPN keytab       |
       |                             | -> alice@EXAMPLE.ORG             |
       |                             | UserDetailsService/authorities   |
       |<----------------------------| 200/403 or Kerberos error        |
~~~

This diagram is a **simplified happy path**. SPNEGO may require more than one 401/Negotiate round, the KDC may participate in different ticket steps, and clients may not support Kerberos. The **Authorization: Negotiate** header carries a SPNEGO/GSS token, not a SAMLResponse, CAS Service Ticket, or OAuth Bearer JWT.

Processing details in Spring Security:

- **SpnegoEntryPoint** emits the HTTP challenge WWW-Authenticate: Negotiate when a request requires authentication.
- **SpnegoAuthenticationProcessingFilter** reads the Negotiate header and builds a **KerberosServiceRequestToken** to submit to AuthenticationManager.
- **KerberosServiceAuthenticationProvider** invokes the configured **KerberosTicketValidator**, typically SunJaasKerberosTicketValidator.
- The validator uses **JAAS/Krb5LoginModule** and a **JGSS acceptor** with the service keytab to check the token; upon success, it returns the result to the provider.
- **UserDetailsService** looks up local identity to determine GrantedAuthorities, disabled status, or policy.
- SecurityContext is used to make authorization decisions and can be stored in HttpSession if the browser application is stateful.

**Do not Base64-decode the header yourself and treat the string as a username.** The token must be cryptographically verified by the Kerberos validator, not merely syntactically valid.

## 3. What Is a Service Principal?

A web service principal usually takes the form:

~~~text
HTTP/portal.example.org@EXAMPLE.ORG

HTTP                   service class
portal.example.org     canonical FQDN accessed by browser
EXAMPLE.ORG            Kerberos realm
~~~

**HTTP** is the Kerberos service class; it does not mean traffic can travel over unencrypted HTTP. SPNEGO is normally paired with HTTPS to protect browser requests, session cookies, and traffic.

The **FQDN** should match the public hostname the browser accesses. For example:

~~~text
Browser: https://portal.example.org/private
Reverse proxy: http://portal-service:8080/private
Ticket service principal: HTTP/portal.example.org@EXAMPLE.ORG
~~~

If the Java backend's keytab holds only **HTTP/portal-service@EXAMPLE.ORG** while the client obtains a ticket for **HTTP/portal.example.org@EXAMPLE.ORG**, the backend cannot arbitrarily use the backend-named key to accept the public ticket. Pick a canonical external hostname or design managed alias/additional SPNs.

**Realm** is the Kerberos namespace. The @EXAMPLE.ORG suffix does not strictly have to match the DNS domain name verbatim; for instance, web host portal.corp.example may use realm AD.EXAMPLE.ORG if KDC/krb5.conf and AD are properly configured.

### 3.1. SPN and AD Service Account Are Distinct

| Value | Example | Meaning |
| --- | --- | --- |
| Public URL | https://portal.example.org | Website |
| Kerberos HTTP SPN | HTTP/portal.example.org@EXAMPLE.ORG | Principal the ticket targets |
| AD account owner | EXAMPLE\svc-webportal | Account holding the key for the SPN |
| Keytab path | /run/secrets/http-portal.keytab | Key file on the server |
| Client identity | alice@EXAMPLE.ORG | Authenticated user |
| Local app user | user_id=1001 | Internal account/permissions |

In AD, **an SPN must map to exactly one owning account per policy**. Duplicate SPNs or wrong owners can prevent tickets from being issued or cause acceptance failures.

To inspect AD mappings **without modifying anything**:

~~~powershell
setspn -Q HTTP/portal.example.org
setspn -L EXAMPLE\svc-webportal
~~~

These are commands to inspect SPNs on a Windows host with AD query tools/privileges. Never run SPN add/remove operations in production outside IAM procedures.

### 3.2. Multiple Aliases and Multi-Tenant Setups

Two hosts **portal.example.org** and **intranet.example.org** can cause clients to request two distinct tickets even if both resolve to one IP. A keytab can contain multiple principals when properly managed, yet a single **SunJaasKerberosTicketValidator** is normally configured for **one specific servicePrincipal**. Do not assume it automatically accepts every alias just because of a shared DNS CNAME.

If an application uses multiple hosts/realms, design explicit trusted SPNs, acceptors/registrations, and routing; never use a self-reported Host header to swap servicePrincipal at runtime and bypass security checks.

## 4. What Is a Keytab and Why Is It Sensitive?

A **keytab** is a file storing Kerberos secret keys for one or more principals. Entries typically contain:

- **Principal:** e.g., HTTP/portal.example.org@EXAMPLE.ORG.
- **KVNO (Key Version Number):** key version; changes when the service account rotates its password/key.
- **Enctype:** encryption algorithm, e.g., AES256/AES128 permitted by KDC, JDK, and policy.
- **Key material:** actual secret bytes enabling the service to accept tickets.

**A keytab is not a list of user tickets, not a user's TGT, and not a harmless plaintext config file.** Anyone who can access the keytab in the right environment can impersonate the service, so protect it as a confidential credential.

### Inspecting a Keytab Without Exposing Key Bytes

On Linux with MIT Kerberos tools:

~~~bash
klist -k -e /run/secrets/http-portal.keytab
~~~

This typically displays the principal, KVNO, and encryption types. **Do not add -K**, because that flag can print secret keys. Never share keytab copies or debug output containing key material in chat, public issues, or repositories.

What to compare:

~~~text
servicePrincipal in Java:
  HTTP/portal.example.org@EXAMPLE.ORG

Principal in keytab:
  HTTP/portal.example.org@EXAMPLE.ORG

Keytab KVNO/enctype:
  must hold a key capable of accepting tickets issued by the KDC.
~~~

**Matching text entries alone do not prove tickets will validate:** key bytes may be corrupt, KVNO stale, enctype unsupported, clocks skewed, or JAAS unable to read the file.

### File Location and Permissions

Place the keytab outside source/JARs, such as **/run/secrets/http-portal.keytab**, mounted from a tightly permissioned secrets manager/volume. The JVM runtime must have **read** permission for its actual UID/GID; do not make it world-readable and do not run as root just for convenience.

On ACL/POSIX systems, admins can restrict read access solely to the process owner, e.g., file mode **0400**. The container path/mount must be visible to the **JVM**, not just where the file lived on a developer's laptop.

### Why Prefer FileSystemResource?

The validator API accepts a Spring **Resource** via **setKeyTabLocation(Resource)**. Although prefixes like file:/classpath: exist, **JAAS usually needs a real path on the filesystem**; resources packaged inside a fat JAR are not always compatible. Spring Kerberos documentation recommends using a file resource and protecting the file.

~~~java
validator.setKeyTabLocation(
    new FileSystemResource("/run/secrets/http-portal.keytab"));
~~~

This is a Java Bean setup fragment, not a keytab creation command. Never embed a keytab into src/main/resources or a Docker image for build convenience.

## 5. Which APIs Does SunJaasKerberosTicketValidator Use?

Class:

~~~text
org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator
~~~

This is a **KerberosTicketValidator** implementation for Sun/Oracle/OpenJDK Kerberos/JAAS/JGSS. It acts as a **service acceptor**, not a mini KDC, and does not issue service tickets to users.

| Setter / Method | Effect | Warning |
| --- | --- | --- |
| **setServicePrincipal(String)** | Sets the service's principal | Must match the SPN issued by KDC and its key |
| **setKeyTabLocation(Resource)** | Loads the keytab location | Use a file resource pointing to a protected secret |
| **setDebug(boolean)** | JAAS login module debugging | Keep off by default in production |
| **setRealmName(String)** | Supplies realm when config requires | Distinct from the server's hostname |
| **setRefreshKrb5Config(boolean)** | Refreshes krb5 config before login per implementation | Does not fix a wrong SPN/keytab |
| **setMultiTier(boolean)** | Supports certain multi-tier/Subject copy cases | Enable only if truly needed and tested |
| **setHoldOnToGSSContext(boolean)** | Retains GSSContext after accept for further interactions | Disposed by default; carries lifecycle cost |
| **validateTicket(byte[])** | Verifies Kerberos/SPNEGO token | Use only with protocol tokens from filter/manager |

Minimal configuration:

~~~java
SunJaasKerberosTicketValidator validator =
    new SunJaasKerberosTicketValidator();

validator.setServicePrincipal(
    "HTTP/portal.example.org@EXAMPLE.ORG");
validator.setKeyTabLocation(
    new FileSystemResource("/run/secrets/http-portal.keytab"));
validator.setDebug(false);
~~~

**Important distinction:** **SunJaasKerberosClient** on the initiator side can acquire Kerberos credentials when Java calls another service. **SunJaasKerberosTicketValidator** on the acceptor side uses the service's keytab to accept tickets sent by browsers. Never substitute one for the other merely because both contain "Kerberos".

### How Far Does the Validator Verify?

JGSS/Kerberos verifies ticket proof-of-possession and matching encryption/keys, returning the client identity on success. However:

- It does not know whether the local user is still enabled.
- It does not know read rights for document 42, manager roles, tenants, or approval rules.
- It does not permit trusting an X-User header self-asserted by a reverse proxy or browser.
- It does not replace TLS, CSRF protection, session fixation protection, or per-resource authorization.

If the ticket is cryptographically valid yet UserDetailsService reports no permitted local user, Spring must still deny access per policy.

## 6. Mandatory Infrastructure: KDC, Realm, DNS, NTP, and Browser

Even with complete code, an app cannot create a Kerberos realm out of application.yml alone. You need:

1. **KDC/Active Directory** hosting the realm and authenticating users.
2. **HTTP SPN** registered on the right service account.
3. **Keytab** with matching principal/keys/KVNO/enctypes issued by the KDC administrators.
4. **DNS/FQDN** matching both the URL the browser opens and the principal the KDC issues tickets for.
5. **Synchronized clocks** across KDC, clients, and app to avoid clock skew errors.
6. **Browser/OS Negotiate policy** trusting the internal site; workstations holding Kerberos credentials.
7. **Network path/TLS proxy** preserving Authorization: Negotiate and matching channel-binding policy.
8. **Spring SecurityFilterChain** placing the SPNEGO filter/entrypoint/provider properly.

### Sample krb5.conf for Reference

~~~ini
[libdefaults]
 default_realm = EXAMPLE.ORG
 dns_lookup_kdc = true
 rdns = false

[realms]
 EXAMPLE.ORG = {
   kdc = dc1.example.org
   kdc = dc2.example.org
 }

[domain_realm]
 .example.org = EXAMPLE.ORG
 example.org = EXAMPLE.ORG
~~~

This is an **illustrative** file, not a production KDC config. Some environments use DNS SRV and cross-realm trusts; host-to-realm mappings must follow organizational standards.

The JVM can point explicitly to the configuration:

~~~bash
java -Djava.security.krb5.conf=/etc/krb5.conf -jar application.jar
~~~

Run only where the file/JAR/environment is appropriate. Debugging may be enabled via the proper Java flag in a **controlled test environment**; never log entire tokens or keytabs.

### Clocks and Timezones

Kerberos tickets carry start/end timestamps and accept bounded clock skew per KDC policy. Drift on app or client clocks can cause **Clock skew too great** or expired ticket errors. Synchronize NTP/chrony and verify UTC; **never** remove time checks or extend ticket lifetimes indefinitely to mask misconfiguration.

## 7. Choosing Compatible Dependency Versions

**Spring Security Kerberos 2.2.0** is documented by the extension project as built/tested on **JDK 17**, **Spring Security 6.5.1**, and **Spring Framework 6.2.8**. It uses the Maven group:

~~~text
org.springframework.security.kerberos
    spring-security-kerberos-core
    spring-security-kerberos-web
    version 2.2.0
~~~

The **Spring Security Kerberos 7.x** line changes the Maven group to **org.springframework.security**, aligning with Spring Security 7/Framework 7; **never** mix 7.x artifacts into Spring Boot 3 / Spring Security 6.x.

With Boot 3.x, choose a Boot release aligned with Spring Security 6.5.x and inspect the actual dependency tree. Do not assume every Boot 3.0–3.5 release works with extension 2.2.0 without checking dependencies. The Java code below targets **2.2.0 + Security 6.5.x**.

## 8. Spring Boot 3 / Java 17 Project: Service-Side SPNEGO

The example includes a main class, a SecurityFilterChain, SunJaasKerberosTicketValidator, provider, filter, and controller. It is a **compilable integration sample in a project with proper dependencies**, yet end-to-end verification still requires AD/KDC, SPN, keytab, a browser with a Kerberos TGT, and a matching public URL.

### 8.1. Dependencies

Inside the **dependencies** block of pom.xml with a Spring Boot parent/BOM compatible with Spring Security 6.5:

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
    <version>2.2.0</version>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
    <version>2.2.0</version>
  </dependency>
</dependencies>
~~~

Declare both core and web because the code imports classes from both. Never assume the Boot BOM manages the exact extension version, which is why **2.2.0** is pinned here. On any class/method mismatch, inspect the dependency tree before writing workarounds.

### 8.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  kerberos:
    service-principal: "HTTP/portal.example.org@EXAMPLE.ORG"
    keytab-path: "/run/secrets/http-portal.keytab"

server:
  servlet:
    session:
      timeout: 30m
~~~

**service-principal** must match the SPN for which the KDC/AD issues tickets, and **keytab-path** must be a real file inside the JVM container. The 30-minute session timeout governs the app's HttpSession idle window, **not** the TGT/service ticket lifetime at the KDC.

### 8.3. Main Class

**src/main/java/com/example/kerberos/KerberosApplication.java**

~~~java
package com.example.kerberos;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {

    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
~~~

### 8.4. Security Configuration

**src/main/java/com/example/kerberos/KerberosSecurityConfig.java**

~~~java
package com.example.kerberos;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator(Environment env) {
        String principal = env.getRequiredProperty(
            "app.kerberos.service-principal");
        String keytabPath = env.getRequiredProperty(
            "app.kerberos.keytab-path");

        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(
            new FileSystemResource(keytabPath));
        validator.setDebug(false);
        return validator;
    }

    @Bean
    UserDetailsService localUsers() {
        // Demo: one account permitted into the app.
        // Production: DB/LDAP/tenant lookup, account enabled check.
        return username -> {
            if (!"alice@EXAMPLE.ORG".equalsIgnoreCase(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("No enabled local account");
            }
            return User.withUsername(username)
                .password("{noop}unused-for-kerberos")
                .roles("READER")
                .build();
        };
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService localUsers) {
        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(localUsers);
        return provider;
    }

    @Bean
    SecurityFilterChain browserSecurity(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        SecurityContextRepository contextRepository =
            new HttpSessionSecurityContextRepository();

        // Do not declare a @Bean SpnegoAuthenticationProcessingFilter.
        // The filter belongs solely inside this Spring Security chain.
        SpnegoAuthenticationProcessingFilter spnego =
            new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(contextRepository);
        spnego.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(sc -> sc
                .securityContextRepository(contextRepository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Detailed explanation:**

1. **Environment.getRequiredProperty** reads the two properties from YAML; no service account password is used in Spring code.
2. **SunJaasKerberosTicketValidator** is configured with the **service principal** and a **FileSystemResource** pointing to the keytab.
3. **KerberosServiceAuthenticationProvider** uses the validator; if the Kerberos token validates, it requires UserDetailsService to load authorities/account status.
4. **SpnegoEntryPoint** sends the **WWW-Authenticate: Negotiate** challenge to unauthenticated browsers.
5. **SpnegoAuthenticationProcessingFilter** reads the Authorization header and invokes **ProviderManager** containing the Kerberos service provider.
6. **addFilterBefore(..., BasicAuthenticationFilter.class)** places the filter at the proper authentication stage in SecurityFilterChain, not after authorization.
7. **HttpSessionSecurityContextRepository** is wired on both the chain and the filter, which is essential if authenticated state should persist across subsequent requests rather than just the one carrying the Negotiate token.
8. **ChangeSessionIdAuthenticationStrategy** helps prevent session fixation when creating a new Authentication.
9. **SessionCreationPolicy.IF_REQUIRED** fits stateful browsers. For stateless Bearer-token APIs, configure a separate chain with explicit matchers.
10. The filter is created with **new** inside the SecurityFilterChain method so Spring Boot does not auto-register it as a standalone Servlet Filter bean running outside the chain.
11. The **demo UserDetailsService** allows only one illustrative principal. Production must not use this hardcoded allowlist instead of an identity-link DB.
12. Never enable production JAAS debug or log tickets from the Authorization header.

**Sample limitations:** this configures HTTP SPNEGO and a Kerberos service acceptor. It does not create/register the SPN in AD, generate the keytab, or issue a TGT to the browser. If the username is anything other than alice, the demo UserDetailsService rejects it even with a valid ticket; that demonstrates local authorization policy, not a keytab error.

### 8.5. Controller

**src/main/java/com/example/kerberos/HelloController.java**

~~~java
package com.example.kerberos;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/")
    public String home() {
        return "Kerberos SPNEGO example ready";
    }

    @GetMapping("/me")
    public Map<String, String> whoAmI(Principal principal) {
        return Map.of(
            "principal", principal.getName(),
            "mechanism", "Kerberos-SPNEGO");
    }
}
~~~

GET **/me** requires Authentication due to **anyRequest().authenticated()**. After SPNEGO login, SecurityContext holds the local principal, avoiding fetching a new service ticket on every GET while HttpSession stays valid.

### 8.6. Run and Test Commands

In a compatible Spring Boot Maven project with JDK 17+, mounted keytab, and real KDC/AD:

~~~bash
mvn spring-boot:run
~~~

When the app starts and the public route is permitted:

~~~bash
curl -i http://localhost:8080/
~~~

Body from controller:

~~~text
Kerberos SPNEGO example ready
~~~

On a Linux machine **already holding a Kerberos user ticket cache** and a GSSAPI/SPNEGO-capable curl build, with a real public hostname/SPN:

~~~bash
curl --negotiate -u : -i https://portal.example.org/me
~~~

**Running this command alone does not guarantee curl succeeds.** You need realm, KDC, SPN, keytab, TLS, and a user principal accepted by localUsers. If the browser/curl lacks credentials, it can receive HTTP 401; classify client, KDC, JAAS, and local role errors accurately.

## 9. Standalone Java 17: Hands-On Practice on SPN, KVNO, and Enctype

The standalone example below is a **metadata check model**; it does not parse a real keytab, perform Kerberos cryptography, or use Spring. Its goal is illustrating three common misconfigurations: wrong service principal, keytab missing the principal, and KVNO/enctype mismatch with the ticket.

**File: ServicePrincipalPolicyDemo.java**

~~~java
import java.util.List;

public final class ServicePrincipalPolicyDemo {

    enum Result {
        READY_FOR_CRYPTO_VALIDATION,
        WRONG_SERVICE_PRINCIPAL,
        KEYTAB_MISSING_PRINCIPAL,
        KEYTAB_MISSING_KVNO_OR_ENCTYPE
    }

    record KeytabEntry(
        String principal, int kvno, String enctype) { }

    record TicketShape(
        String targetPrincipal, int kvno, String enctype) { }

    static Result preflight(
            String configuredPrincipal,
            TicketShape incoming,
            List<KeytabEntry> entries) {

        if (!configuredPrincipal.equals(incoming.targetPrincipal())) {
            return Result.WRONG_SERVICE_PRINCIPAL;
        }

        boolean hasPrincipal = entries.stream()
            .anyMatch(entry ->
                entry.principal().equals(configuredPrincipal));

        if (!hasPrincipal) {
            return Result.KEYTAB_MISSING_PRINCIPAL;
        }

        boolean matchingKeyMetadata = entries.stream()
            .anyMatch(entry ->
                entry.principal().equals(configuredPrincipal)
                && entry.kvno() == incoming.kvno()
                && entry.enctype().equals(incoming.enctype()));

        return matchingKeyMetadata
            ? Result.READY_FOR_CRYPTO_VALIDATION
            : Result.KEYTAB_MISSING_KVNO_OR_ENCTYPE;
    }

    public static void main(String[] args) {
        String principal =
            "HTTP/portal.example.org@EXAMPLE.ORG";
        String aes = "aes256-cts-hmac-sha1-96";

        List<KeytabEntry> keytab = List.of(
            new KeytabEntry(principal, 7, aes));

        TicketShape correct =
            new TicketShape(principal, 7, aes);
        TicketShape wrongHost =
            new TicketShape("HTTP/backend.example.org@EXAMPLE.ORG",
                7, aes);
        TicketShape oldKvno =
            new TicketShape(principal, 6, aes);

        System.out.println("matching=" +
            preflight(principal, correct, keytab));
        System.out.println("wrongHost=" +
            preflight(principal, wrongHost, keytab));
        System.out.println("oldKvno=" +
            preflight(principal, oldKvno, keytab));
        System.out.println("noPrincipal=" +
            preflight(principal, correct,
                List.of(new KeytabEntry(
                    "HTTP/other.example.org@EXAMPLE.ORG", 7, aes))));
    }
}
~~~

Compile/run:

~~~bash
javac ServicePrincipalPolicyDemo.java
java ServicePrincipalPolicyDemo
~~~

**Exact stdout:**

~~~text
matching=READY_FOR_CRYPTO_VALIDATION
wrongHost=WRONG_SERVICE_PRINCIPAL
oldKvno=KEYTAB_MISSING_KVNO_OR_ENCTYPE
noPrincipal=KEYTAB_MISSING_PRINCIPAL
~~~

**Security/scope note:** READY_FOR_CRYPTO_VALIDATION only confirms **modeled metadata entries align**, not that the ticket is valid. Real JGSS also verifies key bytes, Kerberos ticket integrity, client identity, lifetime, realm, replay, and mechanism policy. JDK/KDC key selection is richer than comparing three fields in this demo; this is **not the canonical key selection algorithm of SunJaasKerberosTicketValidator**.

## 10. Inspecting SPN, Keytab, Client, and Server with Safe Tools

### 10.1. Querying SPNs in AD

On Windows with AD tools:

~~~powershell
setspn -Q HTTP/portal.example.org
setspn -L EXAMPLE\svc-webportal
~~~

Query commands only show which account owns the SPN and whether duplicates exist. Any SPN/key/password changes must be performed by IAM/AD admins under change control.

### 10.2. Linux Keytab Metadata

On the service node:

~~~bash
klist -k -e /run/secrets/http-portal.keytab
~~~

Check principal, KVNO, and encryption type. If missing/permission denied, fix the secret mount and JVM permissions; **never print raw keytabs** and never pass key-printing flags like -K.

### 10.3. Client Kerberos Cache and Ticket

On Linux with a Kerberos client:

~~~bash
klist
kvno HTTP/portal.example.org@EXAMPLE.ORG
~~~

**klist** lists the user's current tickets; **kvno** requests a service ticket from the KDC (and thus needs a real KDC/credentials), confirming the SPN exists. Windows has an equivalent klist tool. When the browser does not send Authorization: Negotiate, check site trust/GPO/Integrated Authentication before blaming the Java keytab.

### 10.4. HTTP Challenge

Without an active session, the response should contain:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

If the server emits no challenge, inspect SpnegoEntryPoint and SecurityFilterChain. If the browser sends Negotiate yet the backend never sees it, check whether the gateway/proxy strips headers. If authenticated yet HTTP **403**, check local UserDetailsService/authorities/authorization rather than editing the SPN.

## 11. Key Rotation, KVNO, and Encryption Types

**Service account password/key rotation** can advance the KDC to a new KVNO while pods still hold a keytab with the old KVNO. New tickets fail to accept, raising errors such as **KRB_AP_ERR_MODIFIED**, integrity/checksum failure, or missing key type.

A safe rotation plan:

1. Inventory: SPN, account owner, current KVNO/enctypes in the KDC, and keytabs on each instance.
2. Prepare the new keytab through IAM, distribute via secret store, and test in an integration environment.
3. Coordinate KDC key cutover with backend rollout, accounting for older tickets and multi-key/overlap support per policy.
4. Never assume replacing the file on disk makes a live JAAS Subject reload automatically; verify versions and perform controlled restarts/reinitialization as needed.
5. Verify every node via keytab metadata and Kerberos integration tests.
6. Monitor validation errors, maintain an approved rollback plan, and retire the old keytab once safe.
7. On suspected keytab compromise, treat it as a credential incident; prioritize rotating/revoking per policy rather than merely deleting one file.

**Enctype:** Use modern encryption per KDC/client/JDK policy, preferring AES where compatible. Never enable legacy RC4/DES or disable Kerberos encryption checks to work around a broken keytab.

## 12. Multi-Instance, HTTPS Reverse Proxy, and Channel Binding

### Multiple Pods Behind the Same Service Hostname

When browsers hit one public FQDN through a load balancer, every replica accepting SPNEGO tokens must hold acceptor credentials for **the same HTTP SPN** or follow a managed routing strategy. If pod A has the new keytab while pod B holds the old keytab, the same user will randomly fail logins.

Distribute keytabs via secure secret mounts; never bake secrets into public image layers. Multi-node apps also need shared SecurityContext/HttpSession or a consistent session strategy when using stateful authentication.

### HTTPS Termination and Extended Protection

When TLS terminates at a reverse proxy, the service principal the browser requests remains the public hostname. Some Windows environments enforce **Extended Protection for Authentication / channel binding (CBT)**; if TLS bindings across client, proxy, and JDK acceptor do not align, **channel binding mismatch** can occur.

Do not work around this by arbitrarily disabling Extended Protection or lowering Windows/AD security levels. Review TLS termination, proxy architecture, client/JDK CBT capabilities, and organizational security requirements.

### Browser NTLM Fallback

The **Negotiate** header does not guarantee the inner payload is a Kerberos AP-REQ; clients may attempt NTLM in certain Windows environments. **SunJaasKerberosTicketValidator does not become an NTLM provider.** When only Kerberos is allowed, invalid fallbacks must be rejected; if the business requires a fallback mechanism, design a separate controlled authentication provider/entrypoint and trust boundary.

## 13. Typical Incidents and Classification

| Symptom | Common Cause | Remediation |
| --- | --- | --- |
| Browser loops on 401, no Authorization: Negotiate | Integrated auth disabled, site untrusted, client lacks Kerberos credentials | Check browser GPO/zone, TGT, and HTTP challenge |
| **KDC_ERR_S_PRINCIPAL_UNKNOWN** | SPN does not exist, wrong DNS/realm mapping | Check setspn -Q, hostname, and realm |
| **KRB_AP_ERR_MODIFIED** | Wrong service key, duplicate SPN, stale KVNO, or keytab from another account | Cross-check owner, kvno/enctypes, and keytab |
| **Cannot find key of appropriate type** | Ticket requests an enctype absent from keytab/JDK | Audit keytab/KDC encryption policy |
| **KeyTab not found** | Wrong path in config or volume not mounted | Inspect real file inside the JVM container |
| **Permission denied reading keytab** | UID/GID/mode blocks read | Fix ACL/secret mount under least privilege |
| **Clock skew too great** | Client, server, KDC clocks out of sync | Synchronize NTP/chrony |
| **GSSException Defective token** | Malformed header, proxy rewrite, incompatible NTLM mechanism | Check Negotiate forwarding and client mechanism |
| **Channel binding mismatch** | Incompatible TLS termination/CBT | Review architecture and preserve Extended Protection |
| **Wrong hostname due to CNAME** | Browser requests ticket for alias differing from keytab | Enforce canonical URL or register alias SPN |
| Validation succeeds yet HTTP 403 | Local account/role/tenant denied | Inspect UserDetailsService and business policy |
| First request succeeds, next is anonymous | SecurityContextRepository/HttpSession not saving, cookies, or cluster | Configure persistence/session properly |
| App boots yet login fails | No end-to-end ticket yet; Java beans existing does not prove keytab validity | Test KDC/browser/SPN/keytab and runtime logs |
| Some pods succeed, some fail | Inconsistent keytab/KVNO/enctype or file permissions | Compare across pods and roll out uniformly |
| SPNEGO filter executes twice | Filter bean auto-registered in addition to SecurityFilterChain | Add filter only inside one chain; no `@Bean` filter |

**Never print raw Authorization: Negotiate tokens, keytab bytes, Kerberos session keys, passwords, TGTs, or sensitive debug logs.** Log only request correlation IDs, error classes, SPN, and minimized status fields per privacy policy.

## 14. Required Integration Tests

| Case | Expectation |
| --- | --- |
| 1. Correct SPN + valid keytab + enabled user | Authenticated principal accepted |
| 2. Ticket targets HTTP/backend, app accepts only HTTP/portal | Denied |
| 3. Keytab lacks configured service principal | Validation fails |
| 4. Keytab KVNO mismatches active ticket | Not silently accepted |
| 5. Keytab lacks compatible enctype | Rejected |
| 6. Wrong key bytes even though SPN/KVNO text matches | Cryptographic validation fails |
| 7. Duplicate SPN/wrong account owner | KDC/service failure, no bypass |
| 8. Kerberos user from unapproved external realm | Not merged into local users; denied per policy |
| 9. Service holds valid keytab yet user lacks local account | No application permissions granted |
| 10. User disabled in DB/LDAP | Denied |
| 11. Browser sends no Negotiate | Controlled 401/fallback policy |
| 12. Client falls back to NTLM | Never treated as Kerberos-authenticated |
| 13. Clock skew exceeds tolerance | Fails per Kerberos time checks |
| 14. Fake/malformed Negotiate header | Denied; never trust self-asserted usernames |
| 15. Reverse proxy strips Authorization | Backend fails auth; diagnose gateway |
| 16. Channel binding mismatch | Fails; fix TLS/CBT per policy |
| 17. Multiple pods hold different keytab versions | Detected and rollout fixed |
| 18. Keytab rotation + JVM restart | New tokens verify; old keys managed |
| 19. Subsequent request authenticated via session cookie | Session policy works, no 401 loop |
| 20. Stateless API separated from browser SSO | Distinct SecurityFilterChains |
| 21. User with identical local-part in two realms | Permissions never auto-linked |
| 22. Local role revoked while SP session active | Authorization reflects revocation within SLA |
| 23. Optional GSS context disposed | Never attempt to use a disposed context |
| 24. New SPN host without updated keytab | Fails safely, no fallback to admin password |
| 25. Compromised keytab | Security incident response: revoke/rotate and audit |

**Test layering:**

- **Unit:** test service principal strings, config mapping, UserDetailsService, and authorization policy.
- **Integration with test KDC:** issue and verify real tickets via SPNEGO, testing wrong keys/realms/KVNOs, lifetimes, and replay behavior.
- **End-to-end with AD/browser:** DNS, GPO/zones, Windows tickets, HTTPS reverse proxy/CBT, and multi-node rollouts.

Unit tests using mocked Authentication alone **do not prove** SunJaasKerberosTicketValidator cryptographically validates tokens; integration tests require a real KDC or trusted test KDC.

## 15. Self-Check Questions

**Q1.** The browser visits portal.example.org, yet the keytab holds only HTTP/backend1@REALM; will the validator accept it?  
**A:** Not by default. Browsers typically request tickets for the portal's public SPN. Align the canonical SPN and keytab.

**Q2.** `klist` shows the right principal yet KRB_AP_ERR_MODIFIED still occurs — why?  
**A:** Key bytes/KVNO/enctype may differ from the KDC, or there may be a duplicate SPN or wrong account owner. Matching text alone is not enough.

**Q3.** Should keytabs be stored inside JAR/resources?  
**A:** Not recommended. JAAS usually needs a real filesystem path, and a keytab is a secret managed outside images/source.

**Q4.** What if the Kerberos ticket is cryptographically valid yet UserDetailsService has no user?  
**A:** Grant no business access; require a local identity link or approved onboarding.

**Q5.** Is user principal alice@EXAMPLE.ORG a service principal?  
**A:** No. Service principals are typically HTTP/FQDN@REALM, and the keytab belongs to the service account.

**Q6.** When a keytab is rotated on disk, does a running JVM pick up the new key immediately?  
**A:** Never assume so. Test your JAAS/JDK version, manage Subject/key caching, and perform controlled reloads/restarts.

**Q7.** Why not use HTTP X-User from the browser as Kerberos authentication?  
**A:** That header proves no possession of a Kerberos ticket; accept identity only from a GSS/JGSS validator or a separately secured trusted proxy protocol.

**Q8.** How does SPNEGO differ from a CAS Service Ticket?  
**A:** SPNEGO uses a Kerberos service ticket/JAAS acceptor, whereas CAS uses an opaque service ticket and CAS validation endpoint. Never swap one validator for the other.

## 16. Production Checklist

- [ ] Service principal **HTTP/FQDN@REALM** matches the public hostname browsers visit.
- [ ] AD/KDC SPN has the right owner and no duplicates; realm/DNS mapping is trusted.
- [ ] Keytab holds the exact principal, KVNO, and enctype/key bytes; file stays outside JAR/Git.
- [ ] Secret mount is secured with minimal read permissions, auditing, and a rotation/rollback plan.
- [ ] Validator sets **setServicePrincipal** and **setKeyTabLocation** to the exact values.
- [ ] Keytab inspected via **klist -k -e**; never use -K which prints keys.
- [ ] Java 17, Kerberos extension 2.2.0, and Security 6.5.x/Boot 3.x have a compatible dependency tree.
- [ ] **SpnegoEntryPoint**, **SpnegoAuthenticationProcessingFilter**, and **KerberosServiceAuthenticationProvider** are wired in the right chain/provider.
- [ ] SPNEGO filter is registered only once, without auto-registration outside Spring Security.
- [ ] For stateful browsers, SecurityContextRepository/HttpSession and session fixation policies work properly.
- [ ] NTP/clocks, KDC reachability, DNS, and browser Negotiate settings are tested end-to-end.
- [ ] HTTPS reverse proxy preserves Authorization Negotiate and aligns with channel binding policy.
- [ ] NTLM fallback is never treated as successful Kerberos authentication.
- [ ] Kerberos user principal maps to a trusted account/realm/tenant, with local authorization enforced separately.
- [ ] ROLE_ADMIN is never granted solely for having a ticket; inspect resources and DB user revocation status.
- [ ] JAAS debug is enabled only temporarily in test environments without exposing secrets/tokens.
- [ ] Tests cover positive, wrong SPN, missing principal, stale KVNO, wrong enctype, key leakage, multi-pod, and browser fallback.
- [ ] Security response plan covers suspected keytab compromise and KDC/service account changes.

**Conclusion:** SunJaasKerberosTicketValidator is the **service-side JAAS/JGSS acceptor** for Kerberos/SPNEGO. It verifies accurately only when configured with **a servicePrincipal reflecting the website's HTTP SPN** and **a keytab holding secret keys matching KDC-issued tickets**. Aligning SPN, realm, hostname, DNS, KVNO/enctype, keytab read permissions, SecurityFilterChain, and local roles is essential for secure Kerberos integration; no single setter replaces all of those steps.

## 17. References

- [Spring Security Kerberos 2.2.0 – Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html): version compatibility with JDK17/Security6.5.1/Framework6.2.8.
- [Spring Security Kerberos 2.2.0 – JavaConfig/SPNEGO](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): configuring SunJaasKerberosTicketValidator, provider/filter, and SPNEGO.
- [SunJaasKerberosTicketValidator Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): servicePrincipal, keyTabLocation, debug, holdOnToGSSContext, and refresh configuration.
- [KerberosServiceAuthenticationProvider Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html): validator and UserDetailsService.
- [SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): Negotiate header, AuthenticationManager, and SecurityContextRepository.
- [SpnegoEntryPoint Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): WWW-Authenticate: Negotiate.
- [Maven Central – Kerberos core](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-core/2.2.0) and [web](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0): 2.2.0 dependencies.
- [MIT Kerberos – klist](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html): reading keytab principal/KVNO/enctype.
- [MIT Kerberos – krb5.conf](https://web.mit.edu/kerberos/krb5-latest/doc/admin/conf_files/krb5_conf.html): realm/KDC/domain mapping.
- [Microsoft – Service Principal Names](https://learn.microsoft.com/en-us/windows/win32/ad/service-principal-names): SPN mapping.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication and trust boundaries.
