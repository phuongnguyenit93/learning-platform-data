# ActiveDirectoryLdapAuthenticationProvider and Active Directory (AD) login behavior

## 1. Objectives and context

`ActiveDirectoryLdapAuthenticationProvider` is the specialized **Spring Security LDAP** `AuthenticationProvider` for authenticating accounts in **Microsoft Active Directory Domain Services (AD DS)** over LDAP. It fits when a Spring application receives a username/password from the user and delegates credential verification to a domain controller (DC).

After this lesson, you can:

- Explain why AD login commonly uses `user@domain` (UPN), differing from DN-based bind in generic LDAP.
- Understand the complete flow **bind to AD → locate user object → retrieve authorities → Spring Security access decision**.
- Configure the provider in Spring Security for a Spring Boot application running Java 17+.
- Recognize the `domain`, `url`, `rootDn`, and `searchFilter` parameters; handle cases where UPN and `sAMAccountName` do not match.
- Distinguish wrong password, disabled/locked account, insufficient group permissions, and LDAP connection errors; know how to protect credentials and TLS connections.

**Scope:** examples focus on **Spring MVC/Servlet and username/password LDAP bind to AD DS**. Connecting successfully to AD does not automatically create Kerberos SSO, Integrated Windows Authentication, MFA, or Microsoft Entra ID login via OAuth 2.0/OpenID Connect. Those mechanisms have different protocols and configurations.

## 2. Essential AD terminology

| Term | Meaning and example |
| --- | --- |
| **AD DS** | Directory service managing accounts, computers, groups, and policies of a Windows domain. |
| **Domain Controller (DC)** | Server providing directory services and handling LDAP requests; e.g. `dc1.corp.example.com`. |
| **LDAP / LDAPS** | Directory access protocol; LDAP typically uses port 389, LDAPS (LDAP over TLS) typically uses port 636. |
| **UPN / `userPrincipalName`** | Name such as `alice@corp.example.com`; commonly used for AD login. The UPN suffix may differ from the actual DNS domain. |
| **`sAMAccountName`** | Legacy-style login name within a domain, e.g. `alice`; not synonymous with UPN. |
| **DN (Distinguished Name)** | Address of an entry in the LDAP tree, e.g. `CN=Alice,OU=People,DC=corp,DC=example,DC=com`. |
| **Base DN / root DN** | Root from which entries are searched, e.g. `DC=corp,DC=example,DC=com`; not a password or login DN. |
| **`memberOf`** | User attribute listing AD groups of which the user is a direct member; common input for building authorities. |
| **`GrantedAuthority`** | Permission/group placed on `Authentication` for Spring Security rules to evaluate. |

Suppose the company's AD has domain `corp.example.com` and user `alice`:

~~~text
User enters:                     alice / <password>
UPN used for LDAP bind:          alice@corp.example.com
LDAP URL:                        ldaps://dc1.corp.example.com:636/
Default search root:             DC=corp,DC=example,DC=com
User entry may have DN:          CN=Alice,OU=People,DC=corp,DC=example,DC=com
An example memberOf value:       CN=AppUsers,OU=Groups,DC=corp,DC=example,DC=com
~~~

**Note:** the `@` sign in a UPN does not turn the UPN into an email address, even though the two values often look alike. AD can configure custom UPN suffixes. A string like `CORP\alice` is a legacy domain name format; do not assume the provider automatically normalizes it into the right UPN.

## 3. Role of ActiveDirectoryLdapAuthenticationProvider

Full class name:

~~~java
org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider
~~~

The class is an `AuthenticationProvider` implementation extending `AbstractLdapAuthenticationProvider` and works with standard **Servlet** authentication flows.

When a user logs in via HTTP Basic or form login, Spring Security typically builds an unauthenticated `UsernamePasswordAuthenticationToken`. The `AuthenticationManager` (usually `ProviderManager`) delegates to the matching provider for verification.

~~~text
Client sends username/password
         │
         ▼
Spring Security Filter (Basic/Form)
         │
         ▼
AuthenticationManager / ProviderManager
         │
         ▼
ActiveDirectoryLdapAuthenticationProvider
         │
         ├─ (1) Append domain to username when needed
         │       alice → alice@corp.example.com
         │
         ├─ (2) LDAP simple bind to DC using UPN + password
         │       Bind fails → AuthenticationException
         │
         ├─ (3) Bind succeeds → search user via LDAP searchFilter
         │       Entry not found → authentication still fails
         │
         └─ (4) Read user information and authorities
                 │
                 ▼
           Authenticated Authentication
                 │
                 ▼
        SecurityContext and authorization
                 │
                 ▼
             HTTP response
~~~

Key points to remember:

1. The provider **attempts to bind using the exact username/password** submitted by the user. It does not download passwords from AD to compare with an application `PasswordEncoder`.
2. After binding, the provider executes an LDAP search to locate the entry and extract data for the principal/authorities. **A successful bind does not guarantee the overall process succeeds** if the search filter or search root is wrong.
3. LDAP group mapping produces `GrantedAuthority`. Whether `/admin` is permitted belongs to **authorization** such as `hasRole`/`hasAuthority`, not the password verification step.
4. LDAP bind authentication is not the same as Kerberos SSO or OAuth tokens. With HTTP Basic, clients may resend credentials on each request; with form login, there is typically a session mechanism depending on configuration.

## 4. Constructors, parameters, and practical defaults

Two main constructors:

~~~java
new ActiveDirectoryLdapAuthenticationProvider(domain, url);

new ActiveDirectoryLdapAuthenticationProvider(domain, url, rootDn);
~~~

| Parameter | Meaning |
| --- | --- |
| `domain` | Suffix appended to the username when constructing the bind principal. E.g. `corp.example.com`. May be null/empty if the username already contains the appropriate UPN suffix. |
| `url` | DC's LDAP URL, e.g. `ldaps://dc1.corp.example.com:636/`. Multiple URLs can be configured in the supported JNDI format. |
| `rootDn` | User search root. When using the 2-argument constructor with domain `corp.example.com`, the provider derives `dc=corp,dc=example,dc=com`. The 3-argument constructor allows specifying a different root. |

Important behaviors:

- With `domain="corp.example.com"`, input `alice` is transformed into principal `alice@corp.example.com` for binding and as the `{0}` substitution value in the search filter.
- If the input already ends with the configured domain (case-insensitively per provider logic), the provider uses that string as the principal directly.
- If `domain` is not configured, the user must supply a principal with a sufficient suffix so the provider can bind/derive the search root; if `rootDn` is specified separately, an AD-accepted principal is still required.
- The provider does not automatically discover AD servers via DNS SRV solely from the constructor's domain. You must specify an LDAP URL suited to your environment and DC redundancy plan.

**Do not equate these three values:** DNS domain `corp.example.com`, a UPN suffix like `example.org`, and LDAP search root `DC=corp,DC=example,DC=com` can differ in practice. Configuration must accurately reflect your domain/forest and directory data.

### 4.1. Default search filter

Default value:

~~~ldap
(&(objectClass=user)(userPrincipalName={0}))
~~~

Placeholders for `setSearchFilter`:

- `{0}`: the `username@domain` principal constructed by the provider.
- `{1}`: the **verbatim** username received from the authentication request.

For example, if the UI always accepts short account names `alice` and AD uses `sAMAccountName` to locate users, you can change it to:

~~~java
provider.setSearchFilter(
    "(&(objectClass=user)(sAMAccountName={1}))"
);
~~~

This is **a configuration snippet** inside a provider bean, not a standalone program. Even when searching by `sAMAccountName`, the LDAP bind step still uses the principal constructed by the provider. If the user enters `alice@corp.example.com`, `{1}` is the full `alice@corp.example.com` and is not automatically stripped to `alice`. Decide the username format at the UI/API before choosing the filter.

Avoid concatenating usernames into LDAP filters. Use the API placeholders so parameters are handled properly and LDAP injection risk is reduced. The search filter must return exactly **one user**; an overly broad filter causes ambiguous results and authentication failures.

### 4.2. Group information and authorities

By default, the provider derives authorities from the `memberOf` attribute on the user entry; on Spring Security 6.3+, you can swap the strategy via `setAuthoritiesPopulator(...)`. Additionally, authorities can be mapped to application needs through the corresponding mapper mechanism.

Example AD attributes:

~~~text
memberOf: CN=AppReaders,OU=Groups,DC=corp,DC=example,DC=com
memberOf: CN=SupportTeam,OU=Groups,DC=corp,DC=example,DC=com
~~~

The framework converts group data into `GrantedAuthority` entries according to the configured strategy. **Observe the actual authority strings** before writing `hasAuthority("...")` or `hasRole("...")` rules; do not guess role names from UI group names.

Specifically:

- `memberOf` usually reflects **direct groups**; do not assume it automatically expands all levels of nested groups.
- A user's primary group may not appear in `memberOf` like regular groups.
- If permissions depend on nested groups or multiple domains/forests, design appropriate group lookup/mapping and test against real AD structures.
- `hasRole("ADMIN")` normally checks for authorities prefixed with `ROLE_`; `hasAuthority("ROLE_ADMIN")` matches the exact string. Strings must match the application's mapping output.

## 5. Complete Spring Boot configuration (Java 17+, Spring Security 6.x)

This example uses **Spring Boot 3.5.x / Java 17+** for a **Spring MVC/Servlet** application. The application exposes `GET /public` (unauthenticated) and `GET /me` (requiring AD authentication via HTTP Basic).

This is a **compilable and runnable** configuration when Maven and an appropriate JDK are installed. Successful login additionally requires a running AD DS, real users, DNS/network connectivity, and a TLS certificate trusted by the JVM. Domain and DC names below are illustrative data, not public servers.

### 5.1. Maven dependencies

Create a Java 17, Maven, Spring Boot 3.5.x project on Spring Initializr with `Spring Web` and `Spring Security`. Add Spring LDAP and Spring Security LDAP to `pom.xml` (do not duplicate if already present):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-ldap</artifactId>
</dependency>
~~~

Use the BOM/dependency management provided by Spring Boot so versions align; do not manually assign a Spring Security version independent of Boot. The AD provider class lives in `spring-security-ldap`, not in `spring-boot-starter-security` alone.

### 5.2. Connection properties

Create `src/main/resources/application.properties`:

~~~properties
app.ad.domain=corp.example.com
app.ad.url=ldaps://dc1.corp.example.com:636/
server.port=8080
~~~

Replace domain/DC with actual values provided by AD administration. The provider reads `app.ad.*` properties via `@Value` in the code below; setting `spring.ldap.urls` separately **does not automatically replace** constructor arguments passed to this provider.

### 5.3. Application class and SecurityFilterChain

Create `src/main/java/demo/ad/AdLoginDemoApplication.java`:

~~~java
package demo.ad;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AdLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AdLoginDemoApplication.class, args);
    }

    @Bean
    ActiveDirectoryLdapAuthenticationProvider adAuthenticationProvider(
            @Value("${app.ad.domain}") String domain,
            @Value("${app.ad.url}") String ldapUrl) {

        var provider = new ActiveDirectoryLdapAuthenticationProvider(
                domain, ldapUrl);

        provider.setConvertSubErrorCodesToExceptions(true);
        provider.setContextEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "5000",
                "com.sun.jndi.ldap.read.timeout", "5000"
        ));
        return provider;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            ActiveDirectoryLdapAuthenticationProvider adProvider)
            throws Exception {

        http
            .authenticationProvider(adProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class ExampleApi {

        @GetMapping("/public")
        String publicEndpoint() {
            return "Service running";
        }

        @GetMapping("/me")
        Map<String, Object> currentUser(Authentication authentication) {
            return Map.of(
                "name", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList()
            );
        }
    }
}
~~~

**Code explanation:**

1. `adAuthenticationProvider` creates the provider with the domain and LDAP URL. `setConvertSubErrorCodesToExceptions(true)` enables translating several AD sub-error codes into distinct exceptions so the server can differentiate causes. The two JNDI properties set connect/read timeouts (in milliseconds) to avoid hanging indefinitely on network issues.
2. `filterChain` **registers the provider directly** on `HttpSecurity`, permitting `/public` and requiring authentication for other URLs. `httpBasic` extracts HTTP Basic credentials and passes them to the `AuthenticationManager` chain. Explicit registration avoids relying on whether Spring Boot auto-discovers provider beans in every configuration.
3. `/me` returns the principal name and list of authorities to observe how AD group mapping appears in the application. In production applications, expose such data only to authorized users or operations teams; do not create public APIs exposing all internal groups.
4. `HttpStatus` is unused in the example and its import can be removed; HTTP responses are determined by Spring Security and Spring MVC. The LDAP provider verifies credentials, while the controller runs only when authentication succeeds.

> The example uses HTTP Basic to make the AD bind mechanism easy to observe. For real users, the application must use **HTTPS from client to application**, **LDAPS/TLS from application to DC**, controlled timeouts, and logging; never send passwords over plain HTTP.

### 5.4. Running the application and verifying

In the directory containing `pom.xml`, run:

~~~bash
mvn spring-boot:run
~~~

If using the Maven Wrapper, run `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`).

Check the public route:

~~~bash
curl -i http://127.0.0.1:8080/public
~~~

**Expected outcome:** HTTP `200 OK`, body:

~~~text
Service running
~~~

Check the protected route without sending Basic credentials:

~~~bash
curl -i http://127.0.0.1:8080/me
~~~

**Expected outcome:** HTTP `401 Unauthorized` with `WWW-Authenticate: Basic ...` (exact header details determined by the framework).

Test AD login on a **development machine**, using a username from the configured AD. With `curl -u alice`, curl prompts for the password interactively so you do not put the password in command history:

~~~bash
curl -i -u alice http://127.0.0.1:8080/me
~~~

In Windows PowerShell use `curl.exe` to avoid the `Invoke-WebRequest` alias. If the account/password is correct, the TLS connection to the DC works, and the user search succeeds, expect HTTP `200 OK` and JSON containing `name` and `authorities`; **exact values depend on the real user and AD groups**. With wrong credentials, expect HTTP `401 Unauthorized`, produced by the HTTP Basic entry point.

**Never pass the password on the command line** like `curl -u alice:myPassword` on shared machines, and never send HTTP Basic across networks outside loopback without HTTPS enabled.

### 5.5. Testing group-based permissions

After inspecting the actual `authorities` list at `/me`, you can add a rule before `anyRequest()`:

~~~java
.requestMatchers("/admin/**").hasAuthority("ACTUAL_AUTHORITY_NAME")
~~~

This is only an **illustrative configuration snippet**; replace the authority name with the confirmed output from AD and your mapper. If authentication succeeds yet permissions are lacking, the request typically receives HTTP `403 Forbidden`. This is an **authorization failure**, distinct from a failed LDAP bind resulting in `401`.

## 6. Active Directory error-handling mechanism

AD may return LDAP error `49` (invalid credentials) accompanied by a **sub-error code** inside the LDAP bind message. The provider can classify several codes for logging and (when enabled) translate them into Spring Security exceptions:

| AD sub-code (hex) | Common scenario | Exception when conversion is enabled |
| --- | --- | --- |
| `525` | User not found | `BadCredentialsException` |
| `52e` | Invalid password/credentials | `BadCredentialsException` |
| `530` | Logon restricted by time | `BadCredentialsException` |
| `532` | Password expired | `CredentialsExpiredException` |
| `533` | Account disabled | `DisabledException` |
| `701` | Account expired | `AccountExpiredException` |
| `773` | Account must change/reset password | `BadCredentialsException` in default mapping |
| `775` | Account locked out | `LockedException` |

These codes are **hexadecimal AD diagnostic codes**, not HTTP status codes. The exception mapping above reflects `ActiveDirectoryLdapAuthenticationProvider` in the Spring Security 6.x line; not every code has a dedicated exception. When `convertSubErrorCodesToExceptions=false` (the default), a rejected bind is normally represented as `BadCredentialsException`. Returned codes also depend on AD configuration, DC version, and actual messages; a parseable sub-code is not guaranteed in every case.

Why shouldn't detailed errors be returned to the user logging in?

- Messages like `user does not exist` or `account locked` sent to any client can leak account state.
- Public interfaces should generally return a generic message such as "Invalid login credentials"; server-side logs and metrics record details with access control.
- Too many failed login attempts can lock the AD account per policy. Add rate limiting and reduce unnecessary automatic retries.

**System errors differ from credential errors:** network timeouts, unreachable DCs, TLS certificate errors, and wrong search root/filter must be investigated separately. Do not assume every `BadCredentialsException` means a wrong password, because the post-bind search can also fail.

## 7. Common AD configuration scenarios

### 7.1. Login with short username

The application only accepts `alice`, and the domain is `corp.example.com`; the 2-argument constructor is usually sufficient:

~~~java
var provider = new ActiveDirectoryLdapAuthenticationProvider(
    "corp.example.com",
    "ldaps://dc1.corp.example.com:636/"
);
~~~

With the default filter, the provider binds as `alice@corp.example.com` and searches for a user with the matching `userPrincipalName`.

### 7.2. AD uses sAMAccountName or UPN does not match

Some environments have a `userPrincipalName` differing from the `username@domain` convention. If binding with the provider-built principal is still accepted by AD yet searching by UPN finds no entry, the filter can be changed to `sAMAccountName`:

~~~java
provider.setSearchFilter(
    "(&(objectClass=user)(sAMAccountName={1}))"
);
~~~

Precondition: the UI supplies a short username matching `sAMAccountName`. Changing the filter only alters the **entry lookup step**, not how the principal is built for the **bind step**. If binding fails because the UPN suffix differs from the domain, clarify the login format and domain/root DN configuration first.

### 7.3. Needing a search root different from the default domain

If the environment's LDAP base is `DC=example,DC=org`, specify it explicitly:

~~~java
var provider = new ActiveDirectoryLdapAuthenticationProvider(
    "corp.example.com",
    "ldaps://dc1.corp.example.com:636/",
    "DC=example,DC=org"
);
~~~

This is an **illustrative** configuration, valid only when the actual root DN contains the target users and AD/DC permits searching under that base. The root DN does not change the domain used for binding.

### 7.4. Multiple DCs, multiple domains, or forests

A domain typically has multiple DCs. The URL must follow a JNDI-supported format and be verified with your actual failover mechanism; avoid assuming the provider automatically discovers all DCs. When an organization has multiple domains or forests, clearly determine UPN suffixes, trusts, root DNs/search scopes, and per-resource authorization requirements; multiple providers or a purpose-built account routing strategy are sometimes needed.

### 7.5. Nested groups

A user may belong to group A, and group A belongs to B. If the application only reads direct `memberOf`, the user "having B" under AD policy does not mean a `GrantedAuthority` for B always appears. Verify effective permissions and, if required, implement group querying/resolution that handles nested membership according to the AD model rather than loosening security rules "to make it work".

## 8. Security and operational notes

**Protect credentials in transit.** Simple LDAP bind sends credentials to the DC. Prefer `ldaps://...:636/` or an organization-approved TLS channel. The JVM must trust the CA that issued the DC's certificate; never disable certificate validation to "fix errors". Client→app HTTPS and app→DC LDAPS are **two distinct channels**, and both must be protected.

**Do not store AD passwords in the application DB.** The provider uses the password for online verification; there is no need to copy passwords, write them to logs, or store parallel hashes. Using `PasswordEncoder` for local users is a separate concern.

**Bound access and handle infrastructure errors.** Configure timeouts, monitor DC health, alert on bind failure rates, DNS/TLS issues, and plan failover. Do not endlessly retry wrong passwords because it can lock out accounts under AD policy.

**Limit exposed information.** Never return stack traces, raw AD diagnostics, full DNs, or sensitive group lists to public clients. Audits require access controls, sensitive data masking, and retention policies.

**Clear authorization mechanisms.** Successful login only proves identity. Attach application permissions to AD groups properly; apply least privilege, check nested/primary groups, and review permissions when groups change or users are disabled.

**MFA, SSO, Entra ID.** LDAP bind only performs username/password authentication against AD DS as permitted by the domain. Browser SSO, Kerberos, SAML, or OIDC/Microsoft Entra ID require their corresponding protocols and integrations; do not expect `ActiveDirectoryLdapAuthenticationProvider` to provide those features on its own.

## 9. Quick diagnosis by symptom

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| 401 for all users | Wrong URL/DC, bind rejected, domain/UPN differs from configuration | Check network/TLS, bindable identity, UPN, and AD logs |
| Bind succeeds yet authentication still fails | Search filter mismatch, wrong root DN, user unreadable | Check default filter, `{0}`/`{1}`, base, and directory read permissions |
| 200 from `/me` but admin routes return 403 | Authorities mismatch policy, nested group or primary group unmapped | Observe actual authorities and `hasRole`/`hasAuthority` logic |
| `SSLHandshakeException`, certificate errors | DC certificate/CA/hostname not trusted by JVM | Verify chain, DNS, JVM truststore; never disable TLS |
| Slow connection or timeout | DNS, firewall, overloaded DC, routing, JNDI timeout | Check port 636, connect/read timeouts, and DC health |
| Account locked after multiple attempts | Repeated requests with old password, retry/login loops | Review AD lockout policy, application logs, and clients |
| Input `CORP\alice` fails | Provider is not configured to translate NetBIOS syntax into the right UPN | Normalize login with validation or use proper UPN |
| "Everyone can log in to `/admin`" | Policy only specifies `authenticated()` | Add authorization rules based on verified authorities |

**Useful diagnostic sequence:** first verify network reachability and TLS to the DC; next check the principal used for binding; then check the search filter/base; finally inspect authorities and policies. Following the provider's exact processing order prevents confusing authentication errors with authorization errors.

## 10. Distinguishing from other Spring Security options

| Solution | When appropriate |
| --- | --- |
| `ActiveDirectoryLdapAuthenticationProvider` | Servlet applications needing to bind credentials to AD DS and using AD's UPN/`memberOf` conventions. |
| `LdapAuthenticationProvider` + `BindAuthenticator` | General LDAP or when you want fine-grained control over DN patterns, search/role populators. |
| In-memory/JDBC UserDetailsService | Accounts managed by the application itself, without querying AD. |
| Kerberos/SPNEGO | Enterprise Windows/SSO authentication using Kerberos tickets. |
| OAuth2 Login/OIDC or SAML with IdP | Federated login/SSO, including modern IdP integrations like Microsoft Entra ID. |

The AD class in this lesson is a **synchronous** `AuthenticationProvider` (LDAP/JNDI). In **Spring WebFlux/reactive** applications, do not run blocking bind operations directly on the event loop; use an integration approach that handles blocking properly or design reactive-native authentication. Do not confuse it with a `ReactiveAuthenticationManager`.

## 11. Self-check questions

1. Why can username `alice` be bound as `alice@corp.example.com`?
2. After bind succeeds, why does the provider still need to search for the user and potentially fail?
3. How does the default filter differ from `(sAMAccountName={1})`?
4. What information does `memberOf` provide, and why can nested groups cause permission discrepancies?
5. Which cases return 401, and which typically return 403?
6. Why can errors `532` and `775` surface as different exceptions when AD sub-error translation is enabled?
7. Why is LDAPS alone insufficient if client→application traffic still uses plain HTTP?
8. Why does a successful AD login not automatically turn the application into a Windows SSO system?

## 12. Official reference documentation

- [Spring Security — LDAP Authentication (Active Directory section)](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security — ActiveDirectoryLdapAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html)
- [Spring Security — DefaultActiveDirectoryAuthoritiesPopulator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/DefaultActiveDirectoryAuthoritiesPopulator.html)
- [Spring Security — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Microsoft Learn — LDAP channel binding in Active Directory](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding)
