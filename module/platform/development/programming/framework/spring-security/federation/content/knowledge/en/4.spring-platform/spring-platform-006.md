# Role of the Spring Security Kerberos Extension and Compatibility Verification

Spring Security Kerberos helps Spring applications integrate **Kerberos authentication**, particularly the **HTTP SPNEGO/Negotiate** mechanism so users in an Active Directory or Kerberos realm can log into web applications using their existing credentials. This extension bridges Kerberos tickets to Spring Security's `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, and `SecurityFilterChain` model; it does not create a KDC, does not pre-grant business permissions, and does not automatically make every Spring version compatible.

This lesson addresses three areas: what the extension solves and does not solve; how the components work; and how to **verify compatibility with evidence** across Java, Spring Boot, Spring Framework, Spring Security, Kerberos libraries, Servlet, Kerberos servers, and browsers. Configuration snippets should only be used after checking your actual versions; the standalone Java 17 example later illustrates a preliminary rule check, not a substitute for real Kerberos testing.

## 1. What Is Kerberos and Where Does It Fit in Architecture?

Kerberos is an authentication protocol based on tickets and cryptographic keys. In a typical setup:

- **Principal:** a user or service identity, such as `alice@EXAMPLE.COM` or `HTTP/portal.example.com@EXAMPLE.COM`.
- **Realm:** a Kerberos administrative domain (e.g. `EXAMPLE.COM`), typically served by one or more Key Distribution Centers (KDC).
- **KDC:** central service providing Authentication Service (AS) and Ticket-Granting Service (TGS) functions; in many enterprise environments, an Active Directory Domain Controller performs this role.
- **Ticket-Granting Ticket (TGT):** a ticket allowing the client to request service tickets without re-entering a password for each service during its validity window.
- **Service ticket:** a ticket issued for a specific service principal, such as `HTTP/portal.example.com@EXAMPLE.COM`.
- **Keytab:** a file containing long-term keys for a service principal so the server can verify tickets; must be managed like a secret.
- **SPNEGO:** a security negotiation mechanism used over HTTP via `Negotiate`; in this context it typically carries a Kerberos service ticket via GSS-API.

General flow diagram:

~~~mermaid
sequenceDiagram
    participant U as User / browser
    participant K as KDC / Active Directory
    participant W as Spring application
    U->>K: Authenticate and receive TGT (already present from domain session)
    U->>W: GET /secure
    W-->>U: 401 WWW-Authenticate: Negotiate
    U->>K: Request service ticket for HTTP/portal.example.com
    K-->>U: Service ticket
    U->>W: Authorization: Negotiate <SPNEGO token>
    W->>W: Verify ticket with keytab and map principal
    W-->>U: 200 or 403 per business authorization
~~~

The flow above is conceptual: obtaining the TGT may have occurred before opening the browser; a browser or proxy may execute multiple negotiation steps. Status `401` with header `WWW-Authenticate: Negotiate` is usually the **expected challenge** rather than a system failure. After authentication, `403` means the user was identified but lacks permission to access the resource.

**Distinction:** Kerberos/SPNEGO is an authentication technique primarily useful within managed realms/domains. OIDC/SAML use different trust contracts and tokens/assertions; OAuth 2.0 access tokens for APIs are not Kerberos service tickets either. When SSO is needed for external Internet partners, an IdP/broker can authenticate Kerberos internally and issue OIDC/SAML to applications instead of requiring every partner to establish direct Kerberos trust.

## 2. What Role Does the Extension Play in Spring Security?

Core Spring Security defines filter chains, authentication, authorization, sessions, request protection, and principal integration; the Kerberos extension supplies adapters to apply those principles to Kerberos tickets.

| Component | Responsibility | What Not to Confuse It With |
| --- | --- | --- |
| `SpnegoEntryPoint` | Returns `WWW-Authenticate: Negotiate` challenge when SPNEGO auth is required | Does not validate tickets itself and grants no roles |
| `SpnegoAuthenticationProcessingFilter` | Reads `Authorization: Negotiate ...`, creates `KerberosServiceRequestToken`, invokes `AuthenticationManager` | Presence of header does not prove the token is valid |
| `KerberosServiceRequestToken` | Carrier for SPNEGO/Kerberos tokens in Spring Security | Not a JWT, ID token, or SAML assertion |
| `KerberosServiceAuthenticationProvider` | Delegates to `KerberosTicketValidator` to verify service tickets and load user/authorities | A valid ticket still requires internal authorization policy |
| `SunJaasKerberosTicketValidator` | Validates tickets via JAAS/GSS-API on compatible runtimes using service principal and keytab | Requires proper JDK/JVM, realm, SPN, keytab, and KDC config |
| `UserDetailsService` | Maps authenticated username/principal to application account/authorities | Never grant admin solely because the principal belongs to a domain |
| `KerberosAuthenticationProvider` | Supports an auth flow using username/password to perform Kerberos client authentication when properly configured | Distinct from server-side SPNEGO ticket validation |
| `KerberosRestTemplate` | Helps Java clients call backends protected by Kerberos/SPNEGO | Does not turn a REST API into an OAuth2 resource server |
| `SecurityFilterChain` | Orchestrates filters, entry points, and URL protection policies | Must control ordering, sessions, and fallback behavior |

The package name of the classes above in verified branches is `org.springframework.security.kerberos.*`. **Java package names do not equal Maven groupIds.** The module's groupId changed in Spring Security 7; checking imports alone is not enough to verify compilation.

Spring Security Kerberos also offers test support such as MiniKdc in certain branches; use the matching test module and version when selecting fixtures rather than assuming all APIs stayed identical across major releases.

## 3. Responsibility Boundary: Kerberos Authenticates, Application Authorizes

Consider two independent checks:

1. **Authentication:** the ticket was issued for the configured service principal, is unexpired, verifies against an accepted server key, and maps to an application principal.
2. **Authorization:** is that principal allowed to view documents, call endpoints, change settings, or act within a tenant?

For example: a valid ticket for `alice@EXAMPLE.COM` does not mean Alice may open `/admin`. A service ticket also says nothing about permission to read customer B's data. `UserDetailsService` or the authority-mapping layer must fetch roles from a source trusted by the application, check account status, and enforce permissions per request/resource.

Never automatically equate:

- `REALM\alice` with `alice@REALM` or email `alice@example.com` without an explicit mapping;
- a realm-less username with a realm-qualified principal;
- accounts from two domains sharing the same prefix before `@`;
- a verified Kerberos ticket with an API-accepted bearer access token;
- a successful domain login with system-wide privileges.

**In federated systems**, AD forest trust/cross-realm trust is a separate administrative configuration: you must verify trust paths, principals, service tickets, keytabs, and access policies. A Spring service does not automatically establish trust between two organizations simply by adding a Kerberos dependency.

## 4. When to Use It, When to Choose Another Approach?

| Scenario | Is Kerberos/SPNEGO Suitable? | Reason |
| --- | --- | --- |
| Windows/AD intranet, domain-joined machines | Often suitable | Browsers can obtain service tickets without prompting for passwords again |
| Internal web app with Kerberos/MIT realm | Can be suitable | Must verify browsers, DNS, KDC, SPN, keytab, and OS |
| Backend API called by internal Java clients | Can use Kerberos client | Client needs ticket cache or managed credentials; service must support Negotiate |
| Portal for independent Internet partners | Usually needs external broker/OIDC/SAML | Hard to require all partners to share Kerberos realm trust/browser policies |
| Mobile/public SPA outside the domain | Usually not primary option | No guarantee clients hold Kerberos tickets or required browser policies |
| REST API using OAuth2 JWT | Use OAuth2 Resource Server for APIs | Bearer JWT tokens and SPNEGO are two distinct mechanisms |

You can support both SPNEGO for intranet users and form/OIDC login for external users, but entry points, filter chains, and fallback policies must be configured explicitly. Never silently downgrade to Basic or handle plaintext passwords on every request just because a browser fails to negotiate.

## 5. Version Compatibility: Key Change Between 2.x and 7.x

**Baseline cross-checked against official documentation on 07-11-2026:**

| Library Family | Kerberos GroupId | Documented Relationship | Recommendation |
| --- | --- | --- | --- |
| Spring Security Kerberos `2.2.0` (standalone extension) | `org.springframework.security.kerberos` | Built/tested on **JDK 17, Spring Security 6.5.1, Spring Framework 6.2.8** | Use with Spring Security 6 line; verify exact patch and Boot BOM in use |
| Spring Security Kerberos `7.1.2` (integrated into Spring Security) | `org.springframework.security` | Built/tested on **JDK 17, Spring Security 7.1.2, Spring Framework 7.0.10** | Keep Spring Security 7 modules synchronized via BOM |
| Legacy 2.0.x branch | `org.springframework.security.kerberos` | Docs for `2.0.1` list JDK 17, Spring Security 6.1.9, Spring Framework 6.0.20 | Do not treat the 2.x major number as proof for every 6.x release |
| Preview/snapshot branches | Varies by branch | Depends on specific preview release | Never choose as production baseline from artifact name alone |

Common pitfall: "the latest Kerberos library is still 2.x" is only true for the **standalone extension line**; starting in Spring Security 7, the project was **merged into Spring Security** and changed coordinates. Never arbitrarily pair `org.springframework.security.kerberos:...:2.2.0` with Spring Security 7.x. APIs/packages may look similar while dependencies/ABI differ; runtime class loading reveals the real errors.

The figures above are **documented configurations**, not a guarantee that every Spring Boot variant, JDK vendor, servlet container, browser, or AD/KDC is compatible. After any upgrade, always check release notes, the dependency graph, and real SPNEGO tests.

### Reference Dependencies for Spring Security 6

For applications on a version-verified Spring Boot 3.x/Spring Security 6.x line, a Maven snippet **solely illustrating 2.2.0 extension coordinates**:

~~~xml
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
~~~

From there, verify the actual `spring-security-core`, `spring-security-web`, and `spring-framework` versions resolved in the app. Never force-upgrade a single transitive dependency to grab an API while skipping compatibility tests. Maven Central lists 2.2.0 as depending on Spring Security 6.5.1; your project may select another patch via its BOM.

### Reference Dependencies for Spring Security 7

With Spring Boot on a branch managing Spring Security 7, per Spring Security documentation:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
~~~

Gradle when a BOM/plugin already manages versions:

~~~groovy
dependencies {
    implementation "org.springframework.security:spring-security-kerberos-core"
    implementation "org.springframework.security:spring-security-kerberos-web"
}
~~~

If not using a BOM, declare **compatible versions** for each module instead of omitting versions and hoping Gradle/Maven guesses right. In projects using the Spring Boot BOM, prefer letting the BOM manage Spring Security, Spring Framework, and the Servlet stack; override only with a clear reason and tested consequences.

**Never place both groupId sets in one application** "just in case": JARs may contain identical class names, putting multiple generations on the dependency graph so class loading depends on ordering. Likewise, changing groupId while forgetting old references/dependency constraints/lockfiles leaves stale JARs on the classpath.

Sources for checking versions and branch transitions:

- [Spring Security Kerberos 2.2.0 Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html)
- [Spring Security 7.1.2 Kerberos Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html)
- [Spring Security 7 — What's New, Modules](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Maven Central — Kerberos 2.2.0 core](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-core)

## 6. Compatibility Matrix to Verify in Practice

Examine at least **three layers**:

### A. Code / Dependency Compatibility

- **JDK:** `java -version` and `javac -version` (if compiler present) reflect the build environment; also verify the JVM inside containers/runtime. Different JDK majors or GSS/JAAS providers can behave differently.
- **Spring Boot/BOM:** record the exact Boot plugin/parent/dependency management version; Boot 3 typically selects Spring Security 6 and Spring Framework 6; Boot 4 selects the matching Spring Security 7/Framework 7 generation.
- **Spring Security and Kerberos:** choose a documented version pair, keeping `spring-security-core`, `spring-security-web`, `spring-security-config`, and both Kerberos modules aligned; never mix Security 6 and 7.
- **Spring Framework and Servlet API:** modern code uses the `jakarta.servlet.*` namespace; older examples/docs with `javax.servlet.*` or `WebSecurityConfigurerAdapter` generally do not apply directly on newer lines.
- **Supporting libraries:** JAAS/GSS, HTTP clients, LDAP support, test KDC; record any class linkage errors.

### B. Kerberos Environment Compatibility

- **KDC/AD:** realm, trusts, permitted encryption types, user/service principals, ticket policies, clock skew.
- **DNS/SPN:** the hostname browsers actually call has a matching HTTP service principal; aliases, CNAMEs, reverse proxies, and load balancers must be designed accordingly.
- **Keytab:** contains the right key for the service principal with matching KVNO/enctype; readable only by the server; key rotation synchronized.
- **Client:** OS/domain join, ticket cache, browser policies for Negotiate, proxy forwarding config, TLS.
- **Container/Kubernetes:** can reach KDC/DNS, mounts its own keytab, passes explicit `krb5.conf` and service principal; never relies on the developer machine's domain login state.

### C. Operational and Security Compatibility

- **Authentication:** 401→Negotiate→ticket→Spring Authentication succeeds, or fails in a controlled manner.
- **Session:** session fixation protection, lifetime, saving `SecurityContext` when appropriate, logout, role changes/revocation.
- **Authorization:** URLs and individual resources enforce proper roles; never treat everyone in the realm as admin.
- **Observability:** logs do not leak tickets or keytabs/passwords; distinguish network, SPN, keytab, missing-credential, and permission errors.

## 7. How to Inspect the Dependency Graph and APIs Before Configuring

Run on the **actual application module**, target branch, and active Gradle configuration, e.g. (Linux/macOS):

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-kerberos-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-kerberos-web
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-web
~~~

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat` when the project provides the batch wrapper. For Maven projects:

~~~bash
mvn -version
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.security,org.springframework.security.kerberos
mvn -DskipTests compile
~~~

**How to read the output** (do not mock stdout, as each project's dependency graph differs):

1. Is there exactly **one Kerberos family** from the chosen `2.x` or `7.x` branch?
2. Are `spring-security-*` artifacts on the same line/version selected by the BOM?
3. Are both `jakarta.servlet` and legacy `javax.servlet`-only libraries present on the runtime path causing failures?
4. Is an older library forcing Spring Framework's version via transitive dependencies?
5. Are `ClassNotFoundException`, `NoSuchMethodError`, or `NoClassDefFoundError` appearing after an upgrade? If so, identify the exact class/method and the JAR loading it rather than blaming "Kerberos doesn't work".
6. Do the JARs containing `SpnegoAuthenticationProcessingFilter` and `KerberosServiceAuthenticationProvider` come from the chosen artifact/version?

You can use `jar tf` or `javap` when investigating method signatures; for example:

~~~bash
jar tf path/to/spring-security-kerberos-web.jar
javap -classpath path/to/spring-security-kerberos-web.jar org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter
~~~

In real commands, substitute the path to the **resolved JAR**. `SpnegoAuthenticationProcessingFilter` in modern branches is a Servlet filter, not an auto-configured magic bean. Adding dependencies does not make SPNEGO login run automatically; you must wire the filter, provider, entry point, and user lookup properly.

## 8. Infrastructure Prerequisites Before Running SPNEGO

For accurate testing, obtain details from your domain/KDC administrator:

| Component | Illustrative Value | Check to Perform |
| --- | --- | --- |
| Realm | `EXAMPLE.COM` | Client and server realms configured, KDC known |
| Application host | `portal.example.com` | Host browsers actually hit; DNS/proxy stable |
| Service principal | `HTTP/portal.example.com@EXAMPLE.COM` | Principal registered accurately in KDC/AD, no duplicate SPN on wrong account |
| Keytab | `/etc/security/http-portal.keytab` | Matching principal/KVNO/enctype; readable by server process |
| `krb5.conf` | `/etc/krb5.conf` | Realm mapping/KDC discovery, DNS appropriate for environment |
| User principal | `alice@EXAMPLE.COM` | User authenticated by domain/KDC, authorized in app |
| Client | Domain machine/browser supporting Negotiate | Holds credential cache and URL trust policy |
| TLS/Proxy | `https://portal.example.com` | `Authorization` and `WWW-Authenticate` headers not stripped by proxy |

With MIT Kerberos client tools installed, a common verification sequence is:

~~~bash
kinit alice@EXAMPLE.COM
klist
kvno HTTP/portal.example.com@EXAMPLE.COM
~~~

- `kinit` prompts for credentials; never automatically embed passwords in scripts/test logs.
- `klist` inspects the client's TGT/ticket cache.
- `kvno` requests a service ticket for a specific SPN; succeeding does not yet prove the web server holds the right keytab.
- `klist -k -e /etc/security/http-portal.keytab` helps server admins inspect principals/enctypes inside a keytab depending on tool version; never share keytabs or outputs containing sensitive data beyond authorized personnel.
- `curl --negotiate -u : https://portal.example.com/secure` only works when curl supports SPNEGO/GSS and has a matching credential cache; responses vary by policy and resource so no universal stdout is guaranteed.

You can temporarily enable JVM Kerberos debugging in test environments, such as `-Dsun.security.krb5.debug=true` or JAAS debug per validator config, then **disable and scrub logs** after investigation; security logs can reveal principals or environment details. Avoid logging full `Authorization: Negotiate` request headers.

## 9. Integrating into Spring Security: Modern Configuration Pattern

For a **Servlet** application with matching branch dependencies, wiring the components involves:

1. Create `SunJaasKerberosTicketValidator` with the provisioned service principal and keytab path.
2. Create `KerberosServiceAuthenticationProvider` pointing to the validator and a `UserDetailsService` mapping principals/authorities.
3. Create an `AuthenticationManager` wrapping the provider.
4. Create `SpnegoAuthenticationProcessingFilter` with the authentication manager; configure session strategy and security context repository per the application's session model.
5. In `SecurityFilterChain`, configure `SpnegoEntryPoint`, register the filter before `BasicAuthenticationFilter`, and declare authorization rules.
6. Test 401 challenge, ticket verification, user mapping, authorization, SPN errors, and logout with integration tests.

**The JavaConfig example below is an integration skeleton for a Servlet application**, requiring a matching Spring Boot/Spring Security project and a real `UserDetailsService`; it is not a standalone program, and without a keytab/KDC it cannot return 200 merely by copying the code:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class KerberosWebSecurityConfiguration {
    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        String principal = System.getenv("KERBEROS_SERVICE_PRINCIPAL");
        String keytabPath = System.getenv("KERBEROS_KEYTAB_PATH");
        if (principal == null || principal.isBlank()
                || keytabPath == null || keytabPath.isBlank()) {
            throw new IllegalStateException("Kerberos service principal/keytab missing");
        }

        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain kerberosChain(
            HttpSecurity http, KerberosServiceAuthenticationProvider provider)
            throws Exception {
        SpnegoAuthenticationProcessingFilter spnego =
                new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(
                new HttpSessionSecurityContextRepository());
        spnego.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());

        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .exceptionHandling(ex ->
                    ex.authenticationEntryPoint(new SpnegoEntryPoint()));
        http.addFilterBefore(spnego, BasicAuthenticationFilter.class);
        return http.build();
    }
}
~~~

**Design rationale:**

- `UserDetailsService` must be provided by the application, typically reading users/roles from managed data. Never trust role data supplied by the browser.
- The SPNEGO filter is instantiated **inside the security chain** to avoid accidentally registering it twice as a standalone Servlet Filter picked up by Spring Boot's `@Bean Filter` auto-registration.
- `HttpSessionSecurityContextRepository` and `ChangeSessionIdAuthenticationStrategy` illustrate stateful session apps; stateless policies require a different design, and you must test session fixation, logout, and replay/caching.
- Filter placement and entry point must be tested alongside other authentication mechanisms; form/OIDC fallback requires matching policies/entry points.
- `/admin/**` only illustrates URL-level role checks; data/object protection still requires service-layer rules.
- Keytab paths must **not** live on the classpath or inside JARs. Secret managers/secure file mounts with minimal permissions are safer.
- Methods `setServicePrincipal`, `setKeyTabLocation`, `setTicketValidator`, `setUserDetailsService`, and `setAuthenticationManager` appear in the Javadoc of the cross-checked branches; still compile against your actual dependencies after locking versions.

In the config above, requests to protected endpoints can trigger a challenge. Once the browser sends a valid ticket, `SpnegoAuthenticationProcessingFilter` invokes the provider to validate the ticket; Spring creates authentication and enforces authorization rules. Even with a valid keytab, login fails if `UserDetailsService` does not recognize the user.

### Special Note for Spring Security 7

Because Spring Security 7 folded Kerberos into the main project, update **coordinates** and check the branch 7 migration guide/releases. Never assume snippets copied verbatim from old `WebSecurityConfigurerAdapter`/`antMatchers` blogs or Spring Security 3 XML will compile on branch 7. Use `SecurityFilterChain`, `authorizeHttpRequests`, and modules in the `jakarta.servlet` namespace as appropriate.

If the application uses WebFlux/reactive, do not drop in `SpnegoAuthenticationProcessingFilter`: that class is a **Servlet filter**. Having the library on the classpath does not create a Reactive-compatible authentication chain; verify a supported adapter and run integration tests. For Spring MVC apps, confirm the security filter is registered once on the right chain.

## 10. Standalone Java 17 Check: Catching Wrong Dependency Lines Before Integration

Before testing real Kerberos, a simple preliminary check can catch two common mistakes: JDK version below baseline and **mixing groupIds/module majors**. The example below **cannot guarantee every patch is compatible**; it merely codifies an initial routing rule based on the two documented lines.

Create `KerberosCompatibilityDemo.java`:

~~~java
public class KerberosCompatibilityDemo {
    record Stack(int javaMajor, int springSecurityMajor,
                 int kerberosMajor, String groupId) {}

    static String evaluate(Stack stack) {
        if (stack.javaMajor() < 17) {
            return "REJECT: Java 17+ baseline required";
        }
        if (stack.springSecurityMajor() == 6
                && stack.kerberosMajor() == 2
                && stack.groupId().equals("org.springframework.security.kerberos")) {
            return "CANDIDATE: check exact 6.x/2.x versions and tests";
        }
        if (stack.springSecurityMajor() == 7
                && stack.kerberosMajor() == 7
                && stack.groupId().equals("org.springframework.security")) {
            return "CANDIDATE: check exact 7.x versions and tests";
        }
        return "REJECT: major line or Maven group mismatch";
    }

    public static void main(String[] args) {
        Stack legacy = new Stack(17, 6, 2,
                "org.springframework.security.kerberos");
        Stack integrated = new Stack(21, 7, 7,
                "org.springframework.security");
        Stack mixed = new Stack(21, 7, 2,
                "org.springframework.security.kerberos");
        Stack oldJdk = new Stack(11, 6, 2,
                "org.springframework.security.kerberos");

        System.out.println("Security 6: " + evaluate(legacy));
        System.out.println("Security 7: " + evaluate(integrated));
        System.out.println("Mixed: " + evaluate(mixed));
        System.out.println("Old JDK: " + evaluate(oldJdk));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac KerberosCompatibilityDemo.java
java KerberosCompatibilityDemo
~~~

Exact stdout:

~~~text
Security 6: CANDIDATE: check exact 6.x/2.x versions and tests
Security 7: CANDIDATE: check exact 7.x versions and tests
Mixed: REJECT: major line or Maven group mismatch
Old JDK: REJECT: Java 17+ baseline required
~~~

Why use the word **CANDIDATE**? Because matching groupId and plausible major versions are only a **preliminary condition**—they do not verify patch versions, Spring Framework, JVM provider, KDC, browser, SPN, keytab, or runtime execution. The example issues no tickets, reads no `krb5.conf`, and must not be treated as an integration test.

In CI, a real checker can inspect the resolved dependency graph or SBOM, compare BOM/lockfiles, and fail Gradle/Maven builds when two different Kerberos module generations appear. Never "fix" it by adding both dependencies "to be safe".

## 11. Evidence-Based Kerberos Integration Testing

Realistic tests require an environment with a test KDC/AD or supporting fixture, plus a dedicated test service principal and keytab. Never run live authentication against production keytabs in public CI.

### Recommended Sequence

1. **Build test:** builds with the chosen Java and Spring versions without class-loading or missing-method errors.
2. **Dependency test:** save `dependencyInsight`/dependency tree output, confirming the exact groupId and single generation.
3. **KDC test:** client obtains a TGT and a service ticket for the web SPN using a test account and realm.
4. **Server ticket test:** service reads the keytab, validator accepts tickets for the target SPN and rejects wrong SPNs or invalid credentials.
5. **Browser SPNEGO test:** visit the target URL, observe the 401 challenge, browser returns `Authorization: Negotiate`, authentication succeeds without re-entering a password when policy permits.
6. **Authorization test:** a valid user lacking permissions receives `403` on protected resources; roles and membership remain enforced by the app.
7. **Negative test:** missing ticket, expired/replayed ticket, wrong service principal, wrong keytab/KVNO, browser lacking trusted URL, disabled principal are rejected in a controlled manner.
8. **Boundary test:** proxy/load balancer, HTTPS, multi-node, DNS aliases, CNAME, session, KDC failover, rollback on version upgrade.
9. **Regression test:** form/OIDC fallbacks and CSRF/session/logout continue working after adding the Kerberos filter.

When running tests, record **expected and observed**; never declare SPNEGO working merely because an HTTP GET returns `200` on a public endpoint. Tests should hit an endpoint requiring `authenticated()` and one checking roles. Opening a browser without a ticket does not always mean failure: if a valid form fallback is configured, the system may redirect to a login form while still protecting the resource.

### Negative Testing Matrix

| Scenario | Expectation | Where to Investigate |
| --- | --- | --- |
| Browser sends unauthenticated request | Negotiate challenge or defined fallback | Entry point, browser policy |
| Browser does not send Negotiate header | User must not be authenticated automatically | Browser trusted sites, credential cache, proxy |
| Ticket for `HTTP/other.example.com` | Must not be accepted for `portal.example.com` | SPN, keytab, canonical host |
| Server keytab wrong/rotated while app not updated | Ticket validation fails | KVNO, enctype, principal in keytab |
| Clock drift exceeds KDC policy | Authentication fails | NTP/clock skew |
| Valid principal yet internal user disabled | Login or permissions denied per policy | `UserDetailsService`, user status |
| Valid principal lacks `ROLE_ADMIN` | `403` on `/admin/**` | Authorization rules, role mapping |
| Spring Security 7 yet using 2.x extension groupId | Fails dependency policy or build/runtime validation | Dependency graph, class/linkage |
| Proxy strips `WWW-Authenticate` or `Authorization` | Negotiation fails without bypassing checks | Proxy header forwarding/TLS |
| Node A/B use different keytabs/realms | Node-dependent login failures or unstable sessions | Secret rollout, load balancing, session sharing |
| Partner has no Kerberos realm trust | Do not assume SSO via SPNEGO | Federation architecture, IdP/broker |

## 12. Common Tricky Failures and How to Diagnose Them

### Repeated 401 (Challenge Loop)

**Symptom:** browser repeatedly receives `401 WWW-Authenticate: Negotiate` or prompts for login multiple times.

**Possibilities:** browser is not sending a ticket, URL is not in trusted sites, machine lacks a TGT, browser chose another scheme, SPN mismatches hostname, proxy drops headers. **How to check:** trace HTTP traffic in a test environment, check `klist`, service principal, browser settings, and proxy. Do not immediately blame a Java bug just because of 401.

### `GSSException`, "Server not found in Kerberos database", or "KDC not reachable"

Check `krb5.conf`/DNS realm mapping, network path to the KDC, SPN existence, realm trust, and OS/JVM GSS provider. Service name errors can stem from aliases/CNAMEs causing clients to request tickets for the wrong principal. Check the exact FQDN the client actually uses.

### "Checksum failed", "Integrity check failed", "Cannot find key of appropriate type"

Likely caused by a keytab holding the wrong key, mismatched KVNO after rotation, enctype mismatch with KDC/JDK policy, or a different service principal. Inspect principals, KVNO, and encryption types using admin tools; issue a new keytab per procedure with restricted read access. Never disable ticket/signature checks to bypass errors.

### "Channel binding mismatch"

May relate to Extended Protection/channel binding requirements, TLS termination, or provider support differences. Review JDK/KDC/Windows docs and proxy architecture. **Disabling Extended Protection in the registry is not recommended as a default fix**; doing so can weaken protection. Prefer valid configuration and testing with security admins.

### `NoSuchMethodError` / `NoClassDefFoundError` After Spring Upgrade

Highly likely caused by mismatched JARs or legacy APIs. Capture exact class/method names, check `dependencyInsight` and resolved artifacts, compare `javax.servlet` vs `jakarta.servlet` namespaces, BOM, and classpath; pick a matching generation of modules and re-test. Never revert Spring Security 7 code to `WebSecurityConfigurerAdapter` just because an old blog example uses it.

### Login Succeeds Yet Roles Are Missing

The Kerberos validator normally asserts the principal, while roles come from `UserDetailsService`/other policies. Check principal name mapping (case/realm), user status, group/role source, mapping rules, and authority refresh. Never assign `ROLE_USER` or `ROLE_ADMIN` by default to every ticket if the application enforces tiered permissions.

### Works Locally Yet Fails in Containers

Check keytab mounting, `krb5.conf`, filesystem permissions, DNS, network reachability to KDC, clock time, Java vendor/provider, image paths, and service principal matching the public host. Containers do not inherit the developer workstation's ticket cache; local success does not guarantee production.

## 13. Long-Term Security and Operations

- **Keytabs are secrets:** mount with least privilege, never commit to Git, never bake into JARs/images, never send in chat/logs, rotate alongside AD/KDC, and plan rollbacks.
- **Use TLS** for web applications; Kerberos authentication does not make HTTPS redundant. Protect session cookies, CSRF, and the proxy→backend channel.
- **Do not over-extend trust:** a realm permitted to authenticate does not automatically make every principal an admin; enforce independent tenant/resource authorization.
- **Do not enable delegation indiscriminately:** if the server must call downstream services using the user's identity, design constrained delegation, SPN allowlists, and explicit permission controls. Unconstrained delegation increases credential exposure risk.
- **Do not allow silent downgrades:** if policy mandates Kerberos, disallow weak fallbacks or unprotected Basic auth; if form/OIDC fallback exists, define who may use it and MFA rules.
- **Sessions and offboarding:** ticket expiration does not automatically revoke application session cookies immediately. Design TTL, logout, deactivation, role updates, and session refresh.
- **Monitor alerts:** 401/403 rates, GSS/JAAS errors, KDC/DNS failures, keytab rotation, failed authorization, browser incompatibility; avoid logging full tokens.
- **Multi-node support:** synchronize service identities/keys in a controlled way, coordinate secret rollouts and session strategies, and test sticky/non-sticky load balancing.
- **Patches:** track release notes for Spring Security, Kerberos modules, Spring Framework, and JDK, distinguishing stable releases from milestones/RCs/snapshots; document upgrade decisions.

## 14. Compatibility Decision Workflow Before Deployment

You can enforce the following "quality gates":

| Gate | PASS Condition | If FAIL |
| --- | --- | --- |
| 1. Dependency | Spring Security, Framework, Boot, Kerberos are on a supported matching line with a conflict-free graph | Fix version/BOM, remove duplicate artifacts |
| 2. API | Code compiles with `SecurityFilterChain`, Servlet namespace, and verified existing methods | Update APIs per **exact-version** docs |
| 3. KDC/SPN | Client obtains a service ticket for the real URL; server keytab matches | Fix DNS/SPN/keytab/realm with domain admins |
| 4. End-to-end | Browser/Java client completes Negotiate; server recognizes the expected principal | Check proxy/browser/cache/validator and test traces |
| 5. Authorization | Roles, account status, and resource permissions are enforced; unauthorized users receive 403 | Fix mapping and policy; never equate authn with authz |
| 6. Hardening | TLS, secrets, sessions, CSRF, rotation, logs, and fallback meet policy | Remediate before public deployment |
| 7. Regression | Other login flows, multi-node, and rollback remain intact | Update integration tests/runbooks |

For each gate, retain versions/commits, secret-scrubbed build logs, resolved dependency graphs, test environment details (OS/JDK/realm/browser), and PASS/FAIL results. That is more trustworthy evidence than concluding "we added the Kerberos dependency so it is compatible".

## 15. Practice Exercises

### Exercise 1: Identifying Roles

Company A's intranet has `https://portal.example.com` and realm `EXAMPLE.COM`. A user already holds a TGT, and the browser sends `Authorization: Negotiate` to the Portal.

Answer:

1. Who issues the TGT and the service ticket?
2. Which service principal does the browser request a ticket for?
3. Which Spring component receives the header and which component validates the ticket?
4. Why can a user with a valid ticket still receive 403 on `/admin`?

**Answer:** KDC/AD; `HTTP/portal.example.com@EXAMPLE.COM`; `SpnegoAuthenticationProcessingFilter` and `KerberosServiceAuthenticationProvider`/`KerberosTicketValidator`; because authorization belongs to application role/resource policies, not determined by the ticket itself.

### Exercise 2: Spotting an Incorrect Upgrade

A project upgrades Spring Security from 6.x to 7.x yet keeps the dependency:

~~~groovy
implementation "org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0"
~~~

**Analysis:** the groupId and major version of the 2.x Kerberos extension do not match the Spring Security 7 generation. Switch to `org.springframework.security:spring-security-kerberos-web` at the BOM-managed version 7, align core/web, and verify dependency graph/compile/tests. Do not assume a specific error without observing the build; this configuration is simply off the documented branch.

### Exercise 3: Cause of 401

A developer's workstation logs into `portal.example.com`, yet Kubernetes does not. On the pod `/etc/krb5.conf` is missing, the keytab is not mounted, and domain DNS from the pod is blocked.

**Analysis:** this is an infrastructure difference. Check KDC reachability, krb5.conf, DNS, SPN, keytab path/permissions, JDK provider, and proxy. Blindly tweaking `HttpSecurity` will not solve missing credentials/service keys.

## 16. Summary and Primary Documentation to Cross-Check

- **The Kerberos extension acts as a bridge:** Kerberos/SPNEGO ticket → Spring Security Authentication → user/authorities → authorization.
- **Compatibility is a matrix:** Maven coordinates + exact dependency versions + JDK/Servlet + KDC/AD + DNS/SPN/keytab + browser/proxy + session/security policies.
- **Spring Security 6 and 7 use different coordinates:** extension `2.2.0` uses group `org.springframework.security.kerberos`, while Kerberos `7.1.2` uses group `org.springframework.security`.
- **A successful compile does not prove login works:** real Kerberos integration tests and negative tests are required.
- **Authentication is not authorization:** a user with a service ticket can and must still be denied when lacking resource permissions.

Sources to consult before every upgrade:

1. [Official Spring Security Kerberos 2.2.0 Documentation — Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html).
2. [Official Spring Security 7.1 Documentation — Kerberos Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html).
3. [Spring Security 7.0 — What's New (Integrated Kerberos)](https://docs.spring.io/spring-security/reference/7.0/whats-new.html).
4. [Kerberos 2.2.0 API — SPNEGO Filter](https://docs.spring.io/spring-security-kerberos/docs/2.2.0/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html).
5. [Spring Security 7 API — SunJaasKerberosTicketValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html).
6. [Spring Security 7 — Kerberos Samples](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/samples.html).
7. [Maven Central — spring-security-kerberos-core 2.2.0](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-core).

**Remember:** to use Kerberos properly, verify all three axes together — **right library version**, **right ticket infrastructure**, and **right resource permissions**. Never skip any axis when integrating or upgrading Spring Security.