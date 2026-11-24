# Kerberos, SPNEGO, and Specific Dependencies and Deployment Prerequisites in Spring Security

## 1. Objectives and Identity-Linking Context

In an enterprise environment using Active Directory (AD) or a Kerberos realm, users are often already signed into their workstation and hold a Kerberos Ticket Granting Ticket (TGT). When visiting an internal site, the browser can automatically negotiate via **HTTP Negotiate/SPNEGO** to obtain a service ticket for the application. The Spring Security application uses that ticket to verify identity and then maps the principal to a **local account and permissions**. Users do not need to re-enter their password at the application when all deployment prerequisites are satisfied.

This lesson thoroughly explains **what Kerberos/SPNEGO is, which dependencies are actually needed, and the special infrastructure requirements to run it**, in the context of **identity linking**. After this lesson, you will be able to:

1. Distinguish Kerberos, GSS-API, SPNEGO, HTTP Negotiate, a Kerberos principal, and Spring Security `Authentication`.
2. Describe the roles of realm/KDC, DNS, SPN, keytab, tickets, system time, and browser policies.
3. Select the exact Spring Security Kerberos modules for Spring Security 6.x or 7.x, avoiding wrong group IDs or server/client library mix-ups.
4. Configure a Spring Boot Servlet example that accepts Kerberos service tickets and maps principals to `UserDetails`/authorities.
5. Diagnose 401 loops, missing tickets, `KRB_AP_ERR_MODIFIED`, wrong SPNs, KVNO/keytab issues, DNS, clock skew, or proxy problems.
6. Distinguish Kerberos SSO login from delegation when a backend calls downstream systems on the user's behalf.

**Important limitation:** the Java example can be compiled in an environment with dependencies, yet **you cannot validate a real Kerberos session with Java code alone**. Hands-on execution requires a realm/KDC or AD, a service principal, a keytab, a browser/client holding Kerberos tickets, and matching network settings. Source code does not fabricate those components.

## 2. Concepts to Keep Separate

| Concept | Meaning | Role When a User Accesses Spring |
| --- | --- | --- |
| **Kerberos V5** | Ticket-based authentication protocol using cryptographic keys shared with the KDC | Protects client and service identities; never sends user passwords in HTTP requests |
| **Realm** | Kerberos identity domain, e.g., `EXAMPLE.COM`; often related to an AD domain but not automatically identical to every DNS configuration | Namespaces user/service principals and trust policies |
| **KDC** | Key Distribution Center comprising authentication and ticket-granting services; in AD, typically provided by domain controllers | Issues TGTs and service tickets |
| **TGT** | Ticket Granting Ticket obtained after a user logs into Kerberos | Used by the client to request service tickets without re-entering a password |
| **Service ticket** | Ticket issued for one specific service principal | Sent by the browser inside a SPNEGO token to the application |
| **SPN** | Service Principal Name, e.g., `HTTP/app.example.com@EXAMPLE.COM` | Tells the KDC which service key encrypts the ticket |
| **Keytab** | File holding long-term keys for a service principal (often multiple KVNOs/enctypes) | Used by the server to verify/decrypt tickets; must be protected as a secret |
| **GSS-API/JGSS** | Abstract security API; Java provides support via JGSS/JAAS | Implements ticket verification mechanics inside the JVM |
| **SPNEGO** | Security mechanism negotiation protocol, typically carrying Kerberos over HTTP Negotiate | Connects browsers with Kerberos-integrated web apps |
| **Spring Security Authentication** | Principal + authorities + authenticated flag inside `SecurityContext` | Input for application authorization checks; not the Kerberos ticket itself |

A **user principal** might be `alice@EXAMPLE.COM`; a **service principal** might be `HTTP/app.example.com@EXAMPLE.COM`. They serve different roles: the user proves identity, whereas the service principal represents the application endpoint whose key resides in the keytab.

**SPNEGO is not synonymous with Kerberos.** `Negotiate` is a negotiation mechanism: depending on the client/environment, some clients may propose NTLM. Spring Security Kerberos with a Kerberos ticket validator does not automatically become an NTLM server. Explicitly test which mechanisms are accepted and reject any outside policy.

## 3. How Does a Single Request Flow?

```text
Employee logs into workstation                      KDC / Active Directory
              |                                               |
              |--- Kerberos logon / request TGT ------------->|
              |<-- Ticket Granting Ticket --------------------|
              |
              |   browser opens https://app.example.com/private/me
              v
         Browser / Client                               Spring Boot app
              |                                               |
              |--- GET /private/me --------------------------->|
              |<-- 401 WWW-Authenticate: Negotiate -----------|
              |                                               |
              |--- TGS-REQ for HTTP/app.example.com ---------> KDC
              |<-- Service ticket for the SPN above ---------- KDC
              |                                               |
              |--- Authorization: Negotiate <SPNEGO token> --->|
              |                                               |
              |                         SpnegoAuthenticationProcessingFilter
              |                                  |
              |                         KerberosServiceAuthenticationProvider
              |                                  |
              |                  SunJaasKerberosTicketValidator + service keytab
              |                                  |
              |                  principal: alice@EXAMPLE.COM
              |                                  |
              |                  UserDetailsService / account link
              |                                  |
              |                  Authentication + ROLE_USER
              |                                  |
              |                  SecurityContext + authorization
              |<-- 200 authorized content --------------------|
```

The sequence above is conceptual; with browsers that already hold a ticket cache and support proactive Negotiate, the actual HTTP round-trips may differ. The initial 401 response **is a valid challenge**, not necessarily an error.

### Step 1: HTTP 401 Initiates HTTP Negotiate

The application returns:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
```

This header informs the browser that it may use the Negotiate mechanism if supported and permitted by machine/browser policy.

### Step 2: Browser Requests a Service Ticket

The browser builds the service principal from the **target hostname** (typically `HTTP/<FQDN>`) and contacts the KDC for a service ticket. Example:

```text
HTTP/app.example.com@EXAMPLE.COM
```

The KDC encrypts the service-bound payload using the service account's key. The keytab on the server must contain a key compatible with that ticket.

**Common pitfall:** if the browser visits `https://app-alias.example.com`, the ticket may target `HTTP/app-alias.example.com`. The keytab and SPN for `HTTP/app.example.com` will not automatically work. Do not "fix" this by altering a header in Spring; design public names, DNS, SPNs, and keytabs together.

### Step 3: Browser Sends the SPNEGO Token

During negotiation, the request looks like:

```http
GET /private/me HTTP/1.1
Host: app.example.com
Authorization: Negotiate <base64-encoded-SPNEGO-token>
```

This example only shows structure: `<base64-encoded-SPNEGO-token>` is not a working ticket. Real tokens can contain sensitive data; never paste them into logs or support tickets.

### Step 4: Spring Verifies the Ticket and Builds Authentication

In Spring Security Servlet:

1. `SpnegoAuthenticationProcessingFilter` looks for `Authorization: Negotiate ...`, extracts the token, and creates a `KerberosServiceRequestToken`.
2. The filter invokes `AuthenticationManager`, typically a `ProviderManager` backed by `KerberosServiceAuthenticationProvider`.
3. The provider passes the ticket to `KerberosTicketValidator` (on OpenJDK/Oracle JDK, usually `SunJaasKerberosTicketValidator`).
4. The validator uses JGSS/JAAS and the service principal/keytab to verify the ticket and obtain the authenticated principal.
5. The provider calls `UserDetailsService` to look up the user, account status, and authorities. Kerberos **primarily establishes who the user is**, not whether the user may edit arbitrary data.
6. Upon success, Spring obtains `Authentication`; `SecurityContext` is set for the request and can be persisted via `SecurityContextRepository` if explicitly configured.
7. `AuthorizationFilter` evaluates `authenticated()`, `hasRole(...)`, and other policies.

**Never shortcut verification:** taking a base64 token, calling `decode`, extracting a "username", or trusting an `X-User` header does not constitute Kerberos authentication.

## 4. Specific Deployment Prerequisites: Mandatory Checklist

### 4.1. KDC / Active Directory and Trust Domain

You need a working Kerberos realm (AD DS or MIT/Heimdal KDC) and user accounts permitted to request tickets. Configure DNS/KDC discovery or `krb5.conf`/`krb5.ini`, network reachability to the KDC, and cross-realm trust policies if multiple domains exist.

Typically involved ports: DNS 53, Kerberos 88 TCP/UDP, kpasswd 464 when managing password changes; LDAP/LDAPS 389/636 **only when the application or infrastructure actually queries the directory**. Do not open every port "just in case"; verify client → KDC and, when needed, server → KDC/directory paths per your deployment diagram.

### 4.2. DNS, Public Name, and Unique SPN

For URL `https://app.example.com`, the service principal is typically:

```text
HTTP/app.example.com@EXAMPLE.COM
```

Requirements:

- The hostname used by the browser must resolve cleanly and consistently via DNS; avoid testing with raw IPs, `localhost`, or arbitrary CNAMEs before SPNs are prepared.
- The SPN must be registered on the **exact service account**, with no duplicate entries on another account. In AD, inspect with `setspn -Q HTTP/app.example.com` and check duplicates with `setspn -X` (with proper permissions).
- Behind a load balancer/reverse proxy, **the SPN corresponds to the URL seen by the browser**, not necessarily a pod's internal hostname. Decide where SPNEGO terminates (proxy or Java backend) and ensure the service ticket is processed there.
- When changing hostnames, aliases, or service accounts, update SPNs, keytabs, and browser/app configs in lockstep.

### 4.3. Service Account and Keytab

Kerberos/AD admins provision a service account, register the SPN, and export a keytab with matching keys/KVNO/enctypes. For example, mount the keytab outside the artifact at `/run/secrets/http.keytab`.

**A keytab holds cryptographic secrets.** Never commit it to Git, package it in a JAR, bake it into a Docker image layer, attach it to emails/logs, or distribute it to clients. Mount it read-only with strict ACLs readable only by the application process. Control all copies, backups, secret stores, and key rotation mechanisms.

When the service account's password changes, the key version number (KVNO) increments and old keytabs may fail to verify service tickets. Plan keytab updates across **every instance** and monitor errors immediately after rotation.

### 4.4. Time Synchronization

Kerberos checks time skew to prevent replay attacks. Clients, KDCs, and servers must have reliable NTP/time synchronization. Allowed clock skew depends on realm policy; never assume "always 5 minutes". Do not arbitrarily inflate allowed skew to mask time-sync issues.

### 4.5. Browser/Client Permitted to Negotiate

Not every device sends Kerberos tickets automatically:

- Clients usually need a domain logon or a TGT in their ticket cache.
- Browsers must support HTTP Negotiate and treat the target URL as trusted/intranet per policy. Firefox uses settings like `network.negotiate-auth.trusted-uris`; Edge/Chrome in enterprise environments use authentication allowlist policies.
- For off-domain clients, private browsers, mobile devices, Internet proxies, jump hosts, or VPNs, verify ticket acquisition and SSO policy. You may need an alternative login such as OIDC with an IdP or a protected fallback form.
- `curl --negotiate -u :` works only if `curl` was built with GSSAPI/SSPI support and the client holds valid Kerberos credentials.

### 4.6. TLS, Reverse Proxies, and Multiple Instances

SPNEGO protects part of the authentication handshake, **not HTTPS**. Deploy HTTPS and protect session cookies, headers, and forwarding paths. If TLS terminates at a reverse proxy, ensure the proxy forwards `Authorization: Negotiate` intact rather than replacing it with an unverified header.

For clusters:

- If Java backends accept tickets directly, all nodes must be able to verify tickets for the **same SPN**, typically granted access to the matching keytab/service account (secured per node).
- If a proxy terminates Kerberos and passes an identity header to the backend, that is **proxy-based pre-auth**. The backend must accept requests strictly from the trusted proxy; do not pretend it is verifying SPNEGO itself.
- If the app persists a Spring session, manage session affinity or a shared session store, invalidation, expiry, and authority refreshes. Authenticating one request with Kerberos does not synchronize app session expiration with TGT expiration.

## 5. Exact Dependencies by Spring Version Line

**Common build-breaking difference:** Spring Security Kerberos is a dedicated module; it does not appear simply by adding `spring-boot-starter-security`. Its group ID changed between Spring Security 6 and 7.

### Spring Boot 3.5 / Spring Security 6.5 (Main Example in This Lesson)

Maven:

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
```

Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0'
}
```

Spring Security Kerberos **2.2.0** is documented by the Spring project as built/tested with **Java 17, Spring Security 6.5.1, and Spring Framework 6.2.8**. For Boot 3.5.x projects, use compatible patch versions and inspect your actual dependency tree. Never randomly mix Jakarta/Servlet libraries and Spring Security across major versions.

### Spring Security 7.x / Spring Boot 4.x

Spring Security 7.1.x documentation uses these coordinates:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-kerberos-core'
    implementation 'org.springframework.security:spring-security-kerberos-web'
}
```

When using the appropriate Spring Boot 4 / Spring Security 7 BOM, let the BOM manage versions. **Never copy the 6.x group ID into a 7.x setup**, and never force `2.2.0` onto the new group's artifacts. Spring Security 7.1.2 documentation specifies JDK 17, Spring Security 7.1.2, and Spring Framework 7.0.10 for Kerberos on that branch.

### Other Modules When Actually Needed

- `spring-security-kerberos-client`: for **Java applications initiating outbound requests to another Kerberos service**; a web server only accepting tickets via SPNEGO usually **does not need** this module.
- `spring-security-ldap` / Spring LDAP: only when loading users, groups, authorities, or directory attributes from AD/LDAP; verifying a Kerberos ticket itself **does not require LDAP**.
- `spring-security-kerberos-test` or MiniKdc tools: for integration tests with a KDC; plain Java tests or MockMvc `@WithMockUser` do not verify tickets.
- `spring-security-test`: tests authorization in Spring. Does not replace server ticket validation.
- JDK 17+ with JGSS/JAAS. `javax.security.auth` in the JDK is the standard package name and is unrelated to modern Servlet applications using `jakarta.servlet`.
- For WebFlux, `SpnegoAuthenticationProcessingFilter` belongs to the **Servlet Filter API**, not a reactive `WebFilter` you can plug directly into `SecurityWebFilterChain`.

To verify resolved dependencies:

```bash
mvn dependency:tree -Dincludes=org.springframework.security.kerberos
```

Use a Maven version and Java toolchain matching your project; pin dependencies from a consistent BOM and run vulnerability scans per organizational policy.

## 6. Spring Boot Servlet Configuration: Receiving SPNEGO

The example below uses **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x, and Spring Security Kerberos 2.2.0**. For reproducible builds, `pom.xml` uses Spring Boot `3.5.16`. The example handles **HTTP service tickets issued by a real KDC**. It does not create a KDC, register an SPN, or complete logins unless a keytab has been provisioned.

### 6.1. Project Structure

```text
kerberos-spnego-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/kerberos/KerberosDemoApplication.java
        └── resources/application.yml
```

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>kerberos-spnego-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/resources/application.yml`:

```yaml
app:
  kerberos:
    service-principal: "${KRB5_SERVICE_PRINCIPAL}"
    keytab-path: "${KRB5_KEYTAB_FILE}"

server:
  port: 8080
```

Both environment variables are **inputs from infrastructure**. Realistic example:

```text
KRB5_SERVICE_PRINCIPAL=HTTP/app.example.com@EXAMPLE.COM
KRB5_KEYTAB_FILE=/run/secrets/http.keytab
```

Do not place the keytab inside `src/main/resources` or inside the JAR. Both a real SPN and keytab must be provisioned before running a login session.

### 6.2. Java 17 Configuration

Create `src/main/java/demo/kerberos/KerberosDemoApplication.java`:

```java
package demo.kerberos;

import java.security.Principal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class KerberosDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice@EXAMPLE.COM")
                .password("{noop}not-used-by-spnego")
                .roles("USER")
                .build()
        );
    }

    @Bean
    SunJaasKerberosTicketValidator ticketValidator(
            @Value("${app.kerberos.service-principal}") String spn,
            @Value("${app.kerberos.keytab-path}") String keytabPath) {
        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(spn);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        validator.setDebug(false);
        return validator;
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
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider) throws Exception {

        // Same repository for loading and saving SecurityContext.
        var contexts = new HttpSessionSecurityContextRepository();
        var entryPoint = new SpnegoEntryPoint();

        // Declared locally so Boot does not register the filter twice.
        var spnego = new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(contexts);
        spnego.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());
        spnego.setFailureHandler((request, response, failure) ->
            entryPoint.commence(request, response, failure));

        return http
            .securityContext(context ->
                context.securityContextRepository(contexts))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(entryPoint))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class)
            .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private/me")
    String currentUser(Principal principal) {
        return principal.getName();
    }
}
```

**What does each part of the code do?**

- `SunJaasKerberosTicketValidator` verifies the service ticket using the service account's SPN and keytab.
- `KerberosServiceAuthenticationProvider` receives the verified Kerberos principal and queries `UserDetailsService`. The example accepts **only** `alice@EXAMPLE.COM` with `ROLE_USER`.
- `SpnegoEntryPoint` returns 401 with `WWW-Authenticate: Negotiate`, instructing the browser to initiate or continue negotiation.
- `SpnegoAuthenticationProcessingFilter` extracts the HTTP Negotiate token and invokes the provider. It is placed before `BasicAuthenticationFilter` in the chain solely as an **ordering anchor**; HTTP Basic itself is disabled in the example.
- `HttpSessionSecurityContextRepository` is configured on **both the filter writing side and Spring's reading side**; on subsequent requests, the application session can restore `Authentication`. This is a **stateful** choice, avoiding resending a SPNEGO ticket on every request.
- `ChangeSessionIdAuthenticationStrategy` adds session fixation protection upon successful authentication in the sample. Real products still need logout, session expiration, and authority refresh designs.
- Do not declare `SpnegoAuthenticationProcessingFilter` as a standalone `@Bean` while also adding it to `SecurityFilterChain`: Spring Boot may auto-register that Servlet Filter outside `FilterChainProxy`, running it twice.
- `password("{noop}not-used-by-spnego")` is **sample** data required because `UserDetails` has a password field; the SPNEGO flow does not compare passwords. Never use `{noop}` for real password logins.
- `/private/me` reads the authenticated Spring Security principal. User data must be **mapped precisely**; if the KDC returns names with differing case or realm formatting, local lookup needs a trusted canonicalization policy.

**Note:** because the code targets a real domain, building it does not mean Kerberos has been tested. You need a valid SPN, keytab, and ticket before receiving 200 from protected endpoints. When studying authentication mechanics, never craft a fake `KerberosServiceRequestToken` to bypass the validator just to "make tests pass".

## 7. Environment Setup and Test Execution Workflow

A minimal environment requires AD/KDC, user `alice@EXAMPLE.COM`, a service account for `HTTP/app.example.com@EXAMPLE.COM`, the matching keytab, public hostname `app.example.com`, a client holding a TGT, and a Java host running the app.

### 7.1. Kerberos/AD Administrator Tasks

- Register a unique SPN on the service account used by the application.
- Export the exact keytab for the service account (enctype, key version, and principal) and transfer it over a secure channel to the app's secret mount.
- Grant read permission on the keytab file to the server process while restricting other users.
- Ensure synchronized clocks, DNS, KDC reachability, realm/trust policies, and service approval policies.
- In AD, avoid duplicate SPNs, select policy-compliant AES/crypto suites, and rotate keys via controlled procedures.

Reference commands to **verify configuration**:

```bash
# Run on a machine with proper permissions and AD tools:
setspn -Q HTTP/app.example.com
setspn -X

# Linux with MIT Kerberos client tools:
klist
klist -kte /run/secrets/http.keytab
```

`klist -kte` reads keytab **metadata** (KVNO, principal, enctype) without printing raw keys; still limit sharing its output internally as it contains sensitive configuration details. `setspn` is a Windows/AD tool and is not available on standard Linux hosts.

You can run `kvno HTTP/app.example.com@EXAMPLE.COM` from a **client already holding a TGT** to request a service ticket and test the SPN/KDC path. If hostname canonicalization differs, first check the exact principal requested by the browser.

### 7.2. Running the Application

On a machine/host with Java 17+ and Maven installed:

```bash
export KRB5_SERVICE_PRINCIPAL='HTTP/app.example.com@EXAMPLE.COM'
export KRB5_KEYTAB_FILE='/run/secrets/http.keytab'

mvn -DskipTests package
java -Djava.security.krb5.conf=/etc/krb5.conf \
     -jar target/kerberos-spnego-demo-1.0.0.jar
```

`/etc/krb5.conf` is merely a Linux example; in an AD domain, realm discovery or native Java configuration may apply depending on the environment. If the app listens on HTTP 8080 behind an HTTPS ingress, ensure secure routing and proper forwarding of the `Authorization` header. Clients must connect using the hostname registered in the SPN.

### 7.3. Testing Negotiation Without Faking Tickets

On a client holding a valid TGT:

```bash
# Inspect ticket cache:
klist

# To see the 401 challenge before sending a ticket:
curl -i https://app.example.com/private/me

# If curl supports GSSAPI/SSPI and already has credentials:
curl --negotiate -u : -i https://app.example.com/private/me
```

Expected behavior:

- The initial unauthenticated request may receive `401` with `WWW-Authenticate: Negotiate`.
- With a client holding a valid service ticket, matching SPN/keytab, and a locally mapped user, the response returns `200`; the demo body is `alice@EXAMPLE.COM` **if the real user is alice**.
- A user with a valid Kerberos ticket who lacks a record in `UserDetailsService` may be rejected; whether 401 or 403 is returned depends on the failure handler and authorization config. Never default every missing local user to `ROLE_USER`.
- If the browser chooses NTLM instead of Kerberos, the Kerberos validator will not be able to authenticate it.

For automated tests, use MiniKdc/a test harness that mints real service tickets in an isolated pipeline, or run integration tests against a dedicated test realm. `MockMvc.with(user(...))` or `@WithMockUser` only tests authorization and controllers **after an `Authentication` exists**; it does not prove SPNEGO/JAAS/keytabs work.

## 8. Linking a Kerberos Principal to Internal Identity and Permissions

Kerberos verifies a principal such as `alice@EXAMPLE.COM`. Applications typically need to map it to an internal account with an immutable ID, tenant, roles, and status. A sound strategy looks like:

```text
Verified Kerberos principal
    "alice@EXAMPLE.COM"
                 |
                 v
KerberosServiceAuthenticationProvider
                 |
                 v
UserDetailsService / identity mapping
    (realm, principal) -> localUserId
                 |
                 v
account status + organization membership
                 |
                 v
ROLE_USER / ROLE_EDITOR / access policies
                 |
                 v
Spring Security Authentication
                 |
                 v
AuthorizationFilter / service policy
```

**Why include the realm?** `alice@EXAMPLE.COM` and `alice@PARTNER.COM` can be two completely different people. Never strip `@REALM` indiscriminately and treat matching usernames as the same account.

**Why not trust every principal holding a ticket?** A valid ticket only proves the KDC verified the principal with the right key; the user might not be authorized to use this application. `UserDetailsService` and authorization must check account status, membership, and business policies.

**Why is LDAP/AD sometimes needed?** LDAP is commonly used to fetch display names, department/group memberships, and role mappings. It does not replace service ticket verification. You can use `LdapUserDetailsService` or `ActiveDirectoryLdapAuthenticationProvider` depending on architecture, yet **a provider that verifies passwords over LDAP is a different flow** from one that verifies Kerberos service tickets.

An illustrative internal database design:

```sql
CREATE TABLE local_user (
    id UUID PRIMARY KEY,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE kerberos_identity (
    realm VARCHAR(255) NOT NULL,
    principal VARCHAR(512) NOT NULL,
    local_user_id UUID NOT NULL REFERENCES local_user(id),
    PRIMARY KEY (realm, principal)
);
```

This is only a conceptual schema: real applications need canonicalization rules, case-sensitivity handling, rename/UPN-change workflows, migrations, uniqueness, transactions, and deprovisioning. Never auto-link accounts based on arbitrary email addresses or local-part usernames.

## 9. Authentication vs. Kerberos Delegation

A Java application **accepting** browser tickets acts as a **service acceptor**. If it calls another downstream service (LDAP, SQL Server, HTTP service B) on the user's behalf, that is a separate problem:

- It requires outbound-usable credentials/tickets; authenticating successfully to service A does not automatically grant permission to impersonate the user to service B.
- **Kerberos Constrained Delegation (KCD)** or **resource-based KCD** in AD carries specific configuration, domain trust, SPN/service account, and policy requirements.
- Java/JGSS may need to hold a GSS context/Subject via specific APIs; client adapters like `KerberosRestTemplate` only apply when the application initiates outbound calls.
- When Microsoft Entra Application Proxy uses KCD, the connector performs delegation to the backend after external authentication at Entra. Keep clear boundaries between external user authentication, service ticket acquisition, and backend ticket verification.

**Never treat a principal header, an acceptor ticket, or `SecurityContext.getAuthentication()` as a valid delegation ticket.** Applications must use an admin-approved delegation mechanism strictly scoped to specific target services.

## 10. Characteristic Errors and Diagnostic Workflow

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Only 401 returned; browser never sends `Authorization: Negotiate` | Browser does not trust URL, client lacks TGT, policy blocks Kerberos, or proxy strips header | Check browser policy, ticket cache, and request/response headers |
| Repeated `401 Negotiate` | Service ticket fails verification, browser picks another mechanism, or wrong SPN | Inspect sanitized GSS/Kerberos logs, SPN, keytab, and negotiated mechanism |
| `KRB_AP_ERR_MODIFIED` | Ticket encrypted for a different service/key; duplicate/wrong SPN account, mismatched keytab | `setspn -Q/-X`, KVNO, keytab principal/enctype |
| `KRB_AP_ERR_SKEW` or clock skew | Client/KDC/server clocks drifted significantly | Check NTP/time sync and realm policy |
| "Server not found in Kerberos database" | Missing service principal/realm or DNS canonicalization mismatch | Check URL, DNS, SPN, and realm |
| "No valid credentials provided" in browser/curl | No TGT, wrong ticket cache, or JGSS cannot find credentials | Check `klist`, `kinit`/SSPI, and client setup |
| "Checksum failed" / "integrity check failed" | Keytab has wrong key/KVNO/enctype or corrupt ticket data | Verify keytab rotation and KDC/account encryption settings |
| Works on localhost but fails on FQDN | Hostname/SPN or TLS proxy setup mismatch | Use exact real URL/SPN and inspect virtual host config |
| Ticket valid, yet user missing in app | `UserDetailsService` lacks principal or realm/casing mapping mismatch | Inspect verified principal before linking local user |
| Login succeeds, yet returns HTTP 403 | Spring authorities/role mapping lacks permission | Check `ROLE_*`, rules, and service-layer policies |
| One cluster node works, another returns 401 | Keytab/KVNO/config inconsistent across nodes | Compare secret deployments and service principals per node |
| Browser unexpectedly shows password prompt | Negotiate failing, browser falls back to Basic/NTLM, or wrong intranet policy | Inspect `WWW-Authenticate` and browser/Windows event logs |
| Principal/roles stay valid after user is disabled | Spring session retains `Authentication`; cached authorities unrefreshed | Enforce session expiry, logout, re-auth, and revocation policies |
| Debug logs expose tokens/keytab secrets | JAAS/GSS debug left enabled in production | Disable debug, classify, and purge sensitive logs per policy |

**Layered diagnostic workflow:**

1. **Client:** did the browser actually send a Negotiate token? Does it hold a TGT and trust the URL?
2. **KDC/DNS:** which SPN was the service ticket issued for? Is the principal unique, in the right realm, on the right service account?
3. **Keytab/JVM:** can the server read the keytab; do SPN, enctype, and KVNO match; did the JVM locate the right `krb5.conf`?
4. **Spring filter/provider:** did the request pass through the chain and filter in the right order; did the provider verify the ticket?
5. **Local mapping:** did `UserDetailsService` receive the canonical username and assign the right authorities?
6. **Authorization/session:** is `SecurityContext` persisted/loaded properly, and does app policy permit resource access?

For local Java debugging, you can temporarily enable:

```bash
java -Djava.security.krb5.conf=/etc/krb5.conf \
     -Dsun.security.krb5.debug=true \
     -Dsun.security.spnego.debug=true \
     -jar target/kerberos-spnego-demo-1.0.0.jar
```

**Never leave debug enabled by default in production.** Kerberos/GSS logs can expose principals, realms, SPNs, and session details. Protect traces and turn them off immediately once the root cause is verified.

## 11. Common Misconceptions

**"Just adding `spring-boot-starter-security` gives you Kerberos SSO automatically?"** No. You need the version-appropriate extension, filter/provider configuration, SPN, keytab, KDC, browser policies, and trust boundaries.

**"SPNEGO = LDAP?"** No. SPNEGO is an HTTP authentication negotiation mechanism; Kerberos tickets are verified using service keys. LDAP can supplement user/group lookups, not replace Kerberos itself.

**"Holding a Kerberos ticket grants admin rights automatically?"** No. The ticket proves the principal, while authorities must come from a managed policy source.

**"Is a Kerberos ticket a JWT?"** No. Kerberos tickets use KDC/secret-key mechanics, not JWT/OIDC ID Tokens. If a gateway translates a Kerberos identity into an OIDC token, the backend follows the translated protocol under a new trust boundary.

**"Can I test by manually sending `Authorization: Negotiate base64(alice)`?"** No. That is not a valid Kerberos service ticket; base64 is merely encoding and provides no cryptographic proof.

**"Does SPNEGO mean the backend can call any downstream service as the user?"** No. Delegation is a separate configuration, typically requiring KCD, target-service permissions, and strict security boundaries.

**"Since tickets use an HTTP service principal, is TLS unnecessary?"** False. You still must protect the HTTP channel, cookies, proxies, and post-login requests/responses.

## 12. Self-Check Questions

1. **For URL `https://app.example.com`, which SPN does the browser usually use?** Typically `HTTP/app.example.com` in the target realm, though you must check actual DNS/canonicalization and KDC policy.
2. **Where does the application get the key to verify a service ticket?** From the keytab or managed acceptor credentials configured for that exact service principal.
3. **Why is `UserDetailsService` still needed if Kerberos already verified the principal?** To validate account status and supply internal authorities/policies.
4. **Do the Kerberos dependencies for Spring Security 6.5 and 7.1 share the same group ID?** No. The 6.x 2.2.0 extension uses `org.springframework.security.kerberos`, whereas 7.x uses `org.springframework.security` under the newer BOM.
5. **Is `401 WWW-Authenticate: Negotiate` always an error?** No. It is the normal challenge starting negotiation.
6. **What should you check if a service works on one node yet fails on another?** Keytab, principal, KVNO/enctype, secret mounts, and exact configuration on each node.
7. **If a user changes their AD password or is disabled, does the current Spring session automatically expire?** Do not assume so; session, logout, and revalidation policies must be explicitly designed.
8. **Does `@WithMockUser` verify the keytab?** No. It bypasses Kerberos ticket validation and only tests logic once an `Authentication` exists.
9. **Is calling a second HTTP service on the user's behalf automatic?** No. You must configure approved delegation scoped strictly to the required target services.

## 13. Official References

- Spring Security Kerberos 2.2.0 / Spring Security 6.5 compatibility: https://docs.spring.io/spring-security-kerberos/reference/introduction.html
- Spring Security Kerberos 7.1.x dependency coordinates: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security Kerberos – SPNEGO Negotiate and JavaConfig: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- API `SpnegoAuthenticationProcessingFilter`: https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- API `KerberosServiceAuthenticationProvider`: https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- API `SunJaasKerberosTicketValidator`: https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html
- Java 17 JGSS / HTTP SPNEGO: https://docs.oracle.com/en/java/javase/17/security/part-vi-httpspnego-authentication.html
- Microsoft Entra Kerberos Constrained Delegation: https://learn.microsoft.com/en-us/entra/architecture/auth-kcd
- Maven Central `spring-security-kerberos-web:2.2.0`: https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0
