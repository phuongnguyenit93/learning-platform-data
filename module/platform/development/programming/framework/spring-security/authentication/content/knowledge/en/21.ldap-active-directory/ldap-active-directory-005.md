# LdapBindAuthenticationManagerFactory and version-specific configuration

## 1. Lesson objectives

`LdapBindAuthenticationManagerFactory` is a Spring Security factory used to create an `AuthenticationManager` that performs **LDAP bind authentication**: it accepts a username and password, determines the account's LDAP Distinguished Name (DN), and asks the LDAP server to authenticate via a bind operation.

After this lesson, you can:
- Choose between determining the DN via `userDnPatterns` or searching for users with `userSearchBase` + `userSearchFilter`.
- Configure `BaseLdapPathContextSource`, create an `AuthenticationManager` from the factory, and wire it into the `SecurityFilterChain` of a **Servlet** application.
- Understand the differences among Spring Security 5.7/5.8, 6.x, and 7.x; avoid copying deprecated/removed legacy configurations verbatim.
- Distinguish **LDAP bind authentication** from **loading authorities** from LDAP and the Active Directory (AD) case.
- Diagnose errors involving DN, base DN, search filter, service account, TLS/LDAPS, and missing LDAP permissions.

This article uses Java 17+ and bean-style Spring Security configuration, best suited for Spring Boot 3.x / Spring Security 6.x applications; differences in 5.7+ and 7.x are called out separately.

## 2. What is LDAP bind and where does the factory fit?

In LDAP, each entry has a unique DN, for example:

```text
dc=example,dc=org
└── ou=people
    └── uid=linh
        Full DN: uid=linh,ou=people,dc=example,dc=org
```

Suppose a user enters `linh` and a password. The application does not need to read the password attribute in the directory for comparison. Instead, it asks the LDAP server to authenticate by binding with that DN and password.

Typical flow:

```text
HTTP Basic / form login
        |
        v
Spring Security authentication filter
        |
        v
AuthenticationManager
        |
        v
LdapAuthenticationProvider + BindAuthenticator
        |
        +--> Resolve DN: from pattern OR LDAP search
        |
        +--> LDAP bind with entered password
        |       |- Success -> retrieve user info, authorities
        |       `- Failure -> authentication exception
        |
        v
Authenticated Authentication -> SecurityContext
        |
        v
Authorization: authenticated(), hasRole(...), ...
```

`LdapBindAuthenticationManagerFactory` resides in the `org.springframework.security.config.ldap` package. It **creates** an `AuthenticationManager`; the factory itself is not a login session bean, not an HTTP filter, and does not replace `SecurityFilterChain`.

Components:
- `BaseLdapPathContextSource`: knows the LDAP server, base DN, and connection settings. `DefaultSpringSecurityContextSource` is commonly used.
- `LdapBindAuthenticationManagerFactory`: configures how users are found/bound and creates the manager.
- `AuthenticationManager`: takes an `Authentication`, returns an authenticated object or throws `AuthenticationException`.
- `LdapAuthoritiesPopulator`: optionally looks up groups/permissions after a successful bind; **verifying the right password does not automatically grant `ROLE_ADMIN`**.

> LDAP bind differs from password comparison. With bind, the LDAP server verifies the password; the application does not need to fetch `userPassword` and does not use `UserDetailsService`/`PasswordEncoder` to compare LDAP passwords as in `DaoAuthenticationProvider`. When password comparison is genuinely needed, Spring Security provides a separate factory, `LdapPasswordComparisonAuthenticationManagerFactory`.

## 3. Version matrix: which APIs are available?

| Platform | Status | Configuration direction |
| --- | --- | --- |
| Spring Security up to **5.6** | `LdapBindAuthenticationManagerFactory` not yet available | Use the LDAP APIs/configuration supported by that exact older version, or upgrade before applying the examples below |
| Spring Security **5.7–5.8** | Factory introduced in **5.7** | Can create `AuthenticationManager` via the factory; migrate from `WebSecurityConfigurerAdapter` toward a `SecurityFilterChain` bean |
| Spring Security **6.x** (Spring Boot 3.x) | Factory still supported; Jakarta baseline, Java 17+ | Prefer `@Bean AuthenticationManager`, `@Bean SecurityFilterChain`, and lambda DSL |
| Spring Security **7.x** (typically paired with Spring Boot 4.x) | Factory still present in 7.x Javadoc | Continue using beans/factory; check API changes in the migration guide and do not rely on removed DSL overloads |

Common migration pitfalls:
1. `WebSecurityConfigurerAdapter` was **deprecated in 5.7** and **removed in 6.0**. Code using `extends WebSecurityConfigurerAdapter`/`configure(AuthenticationManagerBuilder)` from older tutorials will not compile on Spring Security 6+.
2. `LdapBindAuthenticationManagerFactory` has existed since **5.7**; you cannot simply copy the import into a Security 5.6 project and expect the IDE to fix it.
3. When upgrading, do not pin `spring-security-ldap` alone to a different major version than the remaining Spring Security modules. When using Spring Boot, let dependency management/BOM align module versions.
4. Moving into 7.x, **legacy embedded ApacheDS is no longer the recommended test path**; Spring Security recommends UnboundID. This concerns test LDAP server setup, not removal of the factory.
5. The Servlet configuration style in this lesson uses `HttpSecurity` and `SecurityFilterChain`. In a WebFlux application, authentication uses different reactive components; do not attach this Servlet example directly to `SecurityWebFilterChain`.

Do not guess the Spring Security version from another class name or tutorial: inspect `./gradlew dependencies --configuration runtimeClasspath`, the Maven dependency tree, or the BOM of the actual Spring Boot version.

## 4. Core API of the factory

The factory accepts a `BaseLdapPathContextSource` and uses methods inherited from `AbstractLdapAuthenticationManagerFactory`:

| Method | When to use |
| --- | --- |
| `new LdapBindAuthenticationManagerFactory(contextSource)` | Start configuring bind authentication |
| `setUserDnPatterns("uid={0},ou=people")` | Construct the DN from a pattern when user locations are fixed |
| `setUserSearchBase("ou=people")` | Restrict the user search branch; relative to the context source's base DN |
| `setUserSearchFilter("(uid={0})")` | Search for users by LDAP attribute when the DN cannot be derived directly |
| `setLdapAuthoritiesPopulator(...)` | Customize how authorities are loaded from LDAP/AD groups or other sources |
| `setAuthoritiesMapper(...)` | Transform the `GrantedAuthority` set after loading |
| `setUserDetailsContextMapper(...)` | Customize how LDAP data is mapped to the principal/user details |
| `createAuthenticationManager()` | Build the manager after configuring the required components |

`{0}` in **DN patterns** and **user search filters** is replaced by the login username. For example, `linh` with `uid={0},ou=people` forms the relative DN `uid=linh,ou=people`; combined with base `dc=example,dc=org`, it forms the full DN. For searches, `(uid={0})` becomes the filter matching the username at the configured search base. Use one of the two strategies according to the directory structure rather than mixing them unintentionally.

Note: the method returns an `AuthenticationManager`, not an `AuthenticationProvider` or `SecurityFilterChain`. Publishing the manager as a bean still needs to be wired properly into the authentication mechanism used by the application.

## 5. Complete example on Spring Boot 3.x + Spring Security 6.x

The following example uses an **existing** LDAP directory with users at `uid=<username>,ou=people,dc=example,dc=org`. Domains/hosts are illustrative addresses; replace them with the real directory in your runtime environment. This example focuses on Spring Security LDAP and does not spin up an LDAP server itself.

### 5.1. Dependencies

In a Spring Boot 3.x application that already has the Gradle plugin and compatible dependency management, add to `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
}
```

`spring-security-ldap` contains the factory/authenticator APIs; Spring LDAP provides `ContextSource` and LDAP integration. Keep dependency versions aligned with the active Spring Boot BOM.

### 5.2. Configuring the LDAP URL

`src/main/resources/application.yml`:

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636/dc=example,dc=org}
```

The URL passed to `DefaultSpringSecurityContextSource(String)` may include the **base DN** in the path after host/port. In this example, `dc=example,dc=org` is the root for the relative DNs below. Do not duplicate the base DN inside `userDnPatterns`.

In production, prefer **LDAPS** or StartTLS with TLS certificate verification; configure the truststore/CA appropriately. Unencrypted `ldap://` is only acceptable when equivalent protection is in place and permitted by policy.

### 5.3. Creating ContextSource, AuthenticationManager, and SecurityFilterChain

`src/main/java/example/ldap/LdapSecurityConfig.java`:

```java
package example.ldap;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class LdapSecurityConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource(
            @Value("${app.ldap.url}") String ldapUrl) {
        return new DefaultSpringSecurityContextSource(ldapUrl);
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        // Relative DN to the base DN in app.ldap.url.
        factory.setUserDnPatterns("uid={0},ou=people");

        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager) throws Exception {

        http
            .authenticationManager(ldapAuthenticationManager)
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/me").authenticated()
                .anyRequest().permitAll())
            .httpBasic(withDefaults());

        return http.build();
    }
}
```

The key is `.authenticationManager(ldapAuthenticationManager)`: the HTTP filter chain is explicitly configured to **use that LDAP manager** created by the factory. Avoid assuming that merely declaring an `AuthenticationManager` bean causes every custom filter/chain in every configuration to pick it up automatically.

`httpBasic(withDefaults())` creates a simple entry point to test username/password credentials. If using form login, replace it with `formLogin(withDefaults())` in an appropriate chain. **HTTP Basic must only be used over HTTPS across untrusted networks.**

### 5.4. Entry point and endpoint to observe the principal

`src/main/java/example/ldap/LdapDemoApplication.java`:

```java
package example.ldap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LdapDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LdapDemoApplication.class, args);
    }
}
```

`src/main/java/example/ldap/WhoAmIController.java`:

```java
package example.ldap;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
```

Run the application:

```bash
./gradlew bootRun
```

With a running LDAP server and a user `linh` having a matching DN/password, test from your local machine:

```bash
curl -i --user linh http://localhost:8080/me
```

`curl` may prompt for the password interactively. **The output depends on the real LDAP server**: valid credentials yield HTTP 200 with the principal name in the body; a wrong password typically yields HTTP 401; if LDAP is unreachable, authentication fails and you must check the server logs. This is not a console program with fixed stdout. In real environments, serve the application over HTTPS and never send credentials over plain HTTP.

Because there is no live LDAP instance, certificate, or real credentials included in this article, **we cannot claim the demo will bind successfully when run as-is against `ldap.example.org`**. The Java code is compilable inside a suitable Spring Boot project; testing bind requires a real directory or a separately set up embedded server.

## 6. Choosing `userDnPatterns` vs filter-based search

### Option A — Fixed DN: `setUserDnPatterns`

```java
LdapBindAuthenticationManagerFactory factory =
    new LdapBindAuthenticationManagerFactory(contextSource);
factory.setUserDnPatterns("uid={0},ou=people");
AuthenticationManager manager = factory.createAuthenticationManager();
```

Suitable when all accounts reside in the same OU and every DN follows `uid=<login>,ou=people,...`. The advantage is needing no search to determine the DN and concise configuration. However, if users live in multiple OUs, have their DN changed, or use a display name different from the identifying attribute, the pattern will no longer match.

### Option B — Varying DN: `setUserSearchBase` + `setUserSearchFilter`

Replace the body of the manager creation method in the example above with:

```java
LdapBindAuthenticationManagerFactory factory =
    new LdapBindAuthenticationManagerFactory(contextSource);
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter("(uid={0})");
return factory.createAuthenticationManager();
```

Here Spring Security searches for an entry matching `(uid=linh)` under `ou=people,dc=example,dc=org`, takes the returned DN, and binds using the user's password. Omitting the search base searches from the `ContextSource`'s base DN; avoid broadening the scope unnecessarily on large directories.

**Search permissions:** some LDAP directories forbid anonymous search. In that case, configure a bind account with least-privilege read permissions on `ContextSource`. The standalone bean method below replaces the `ldapContextSource` bean in the previous configuration:

```java
@Bean
BaseLdapPathContextSource ldapContextSource(
        @Value("${app.ldap.url}") String ldapUrl,
        @Value("${app.ldap.search-dn}") String searchDn,
        @Value("${app.ldap.search-password}") String searchPassword) {

    DefaultSpringSecurityContextSource source =
        new DefaultSpringSecurityContextSource(ldapUrl);

    source.setUserDn(searchDn);
    source.setPassword(searchPassword);
    return source;
}
```

Corresponding configuration in `application.yml`:

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636/dc=example,dc=org}
    search-dn: ${LDAP_SEARCH_DN}
    search-password: ${LDAP_SEARCH_PASSWORD}
```

`LDAP_SEARCH_DN` is the DN of the service/search account and `LDAP_SEARCH_PASSWORD` is a secret provided via environment/secret manager. This account is used for search operations requiring authorization; **user password authentication must still bind using the user's own DN**. Never hard-code service passwords in Git. Depending on the directory, the DN passed to `setUserDn` must conform to the server's bind identity requirements.

Do not confuse an LDAP search filter with a URL route filter or SQL. Use the `{0}` placeholder handled by Spring LDAP in the configuration template; avoid injecting input into filters via string concatenation and never design filters that let users control the search scope.

### Decision rules

| Directory structure | Recommended approach | Example |
| --- | --- | --- |
| All users have a fixed DN | `userDnPatterns` | `uid={0},ou=people` |
| Users span multiple branches or DNs change | `userSearchBase` + `userSearchFilter` | base `ou=employees`, filter `(uid={0})` |
| LDAP search requires authorization | Search filter + least-privilege bind account | `setUserDn`, `setPassword` in `ContextSource` |
| Active Directory by `sAMAccountName` | Corresponding search filter or dedicated AD provider | `(sAMAccountName={0})` |
| AD domain using UPN and AD-specific account status errors | Consider `ActiveDirectoryLdapAuthenticationProvider` | See section 8 for example |

If the real directory has multiple base DNs, review search scope, referrals, permissions, and uniqueness. A non-unique `uid` within the search scope can pick the wrong user or return multiple entries and must never be silently ignored.

## 7. Successful authentication does not mean sufficient authorities

`LdapBindAuthenticationManagerFactory` creates an authentication manager using LDAP bind, but policies like `hasRole("READER")` also depend on how `GrantedAuthority` is populated.

Example directory with a group:

```ldif
dn: cn=reader,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: reader
member: uid=linh,ou=people,dc=example,dc=org
```

With such a schema, configure `DefaultLdapAuthoritiesPopulator` for group search (this snippet replaces/augments logic **inside** `ldapAuthenticationManager`, after creating the factory and before `createAuthenticationManager()`):

```java
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

DefaultLdapAuthoritiesPopulator roles =
    new DefaultLdapAuthoritiesPopulator(contextSource, "ou=groups");
roles.setGroupSearchFilter("(member={0})");
roles.setGroupRoleAttribute("cn");
roles.setRolePrefix("ROLE_");
factory.setLdapAuthoritiesPopulator(roles);
```

For group `cn=reader`, mapping the group name (uppercased by default) can produce the authority `ROLE_READER`. `{0}` in the **group search filter** is the user's full DN; this differs from `{0}` in the **user search filter**, where it is the login username. Verify the exact `member`/`uniqueMember` schema, group location, group nesting, and search permissions. Without proper group search, login may still succeed while `hasRole("READER")` returns 403.

Never assign `ROLE_ADMIN` by default merely because bind succeeded. Explicitly define which application permissions map to which LDAP groups, and test low-privilege accounts as well as removed-group cases.

## 8. Microsoft Active Directory case

AD speaks LDAP, but naming conventions, login formats, groups, and account status messages have specific characteristics. Common attributes include:

- `sAMAccountName`: Windows-style login name, e.g. `linh`.
- `userPrincipalName`: typically in the form `linh@corp.example.org`.
- `distinguishedName`: full DN of the entry; the OU may change when staff/departments move.
- `memberOf`: direct group membership links; nested groups and primary groups require dedicated handling policies.

If using only the generic LDAP factory, you might configure:

```java
factory.setUserSearchBase("ou=Staff");
factory.setUserSearchFilter("(sAMAccountName={0})");
```

This is only an **example**, not the right filter for every forest/domain; `ou=Staff` must actually exist under the configured base DN. When authenticating with UPN or needing specific AD account status error interpretation, see `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`. That dedicated provider includes user/group search logic and optional interpretation of AD sub-error codes; do not assume the generic bind factory automatically provides all of those semantics.

Determine early whether the requirement is LDAP authentication against AD or **SSO via Kerberos/SAML/OIDC**. `LdapBindAuthenticationManagerFactory` handles username/password and LDAP bind; it **does not automatically enable Single Sign-On** just because the LDAP server is Active Directory.

## 9. Version-aligned testing workflow

Testing should cover both bean configuration and real authentication against an isolated directory. Checklist:

1. Verify that `LdapBindAuthenticationManagerFactory` exists in `org.springframework.security.config.ldap` of the active `spring-security-ldap` version (5.7+).
2. Check that the exact manager configuration expected by the filter chain is present; confirm `.authenticationManager(...)` is called on the chain under test.
3. Test with an existing user with the right DN and password, a non-existent user, and a user with the right name but wrong password.
4. Test with the LDAP server stopped or wrong hostname/port to distinguish connection errors from credential errors.
5. Test a search account lacking read permission on the OU; verify the error occurs at the user search step rather than being confused with a wrong password.
6. If authorities are used, test the same user before/after adding a group and verify the `hasRole` policy.
7. Test untrusted TLS certificates and hostname mismatches and verify connections are rejected securely; never disable certificate validation to make tests pass.
8. When upgrading Spring Security, recompile bean configs, run authentication integration tests, and review build logs/deprecations.

You can use UnboundID embedded LDAP in isolated tests with LDIF data containing specific DNs and groups. Spring Security provides `EmbeddedLdapServerContextSourceFactoryBean`, illustrated by the following method in a test configuration:

```java
@Bean
EmbeddedLdapServerContextSourceFactoryBean embeddedLdap() {
    EmbeddedLdapServerContextSourceFactoryBean source =
        EmbeddedLdapServerContextSourceFactoryBean.fromEmbeddedLdapServer();
    source.setPort(0); // Dynamic port to avoid colliding with other services.
    return source;
}
```

Import `org.springframework.security.config.ldap.EmbeddedLdapServerContextSourceFactoryBean`, declare the UnboundID SDK in test/runtime scope, and place an appropriate LDIF on the classpath. This is a **test configuration branch replacing the production ContextSource**; do not place both in the same application and accidentally create duplicate beans of the same type. While upgrading to 7.x, prefer UnboundID because legacy embedded ApacheDS support has been removed.

For debugging, temporarily raise log levels selectively for Spring Security/LDAP in test environments, but never write passwords, raw Basic headers, search account secrets, or sensitive LDAP entry contents to logs. Production systems need timeouts, appropriate connection pooling, and monitoring of bind/search failure rates.

## 10. Common configuration errors

| Symptom | Most likely cause | What to check |
| --- | --- | --- |
| `ClassNotFoundException` or IDE cannot find factory | Missing `spring-security-ldap` or version prior to 5.7 | Inspect dependency tree and BOM; add the right module |
| Tutorial code using `WebSecurityConfigurerAdapter` fails to build | Spring Security 6+ removed the adapter | Switch to `@Bean SecurityFilterChain` and manager/factory beans |
| User with valid password gets `BadCredentialsException` | Wrong DN pattern, different username format, wrong password, or account rejected by LDAP policy | Compare actual DN and LDAP server logs, test with a test directory |
| Search never finds the user | Wrong `userSearchBase`, filter mixing up `uid`/`sAMAccountName`, missing search permission | Check base DN, OU, ACLs, and uniqueness |
| Duplicated `dc=...` in DN error | Full DN entered in pattern while context source already has base DN | Use only relative DNs in patterns/search base |
| Login succeeds but role-protected endpoint returns 403 | Missing/misconfigured `LdapAuthoritiesPopulator` or group mapping | Inspect `Authentication.getAuthorities()`, group schema, and policy |
| LDAP server unreachable, SSL handshake error | Wrong URL, port, DNS, firewall, truststore, or certificate | Verify LDAPS/StartTLS/CA; never disable TLS verification |
| Form/basic login not using the intended LDAP manager | Manager not wired into the right `SecurityFilterChain`, or multiple chains/providers present | Check `.authenticationManager(...)`, security matchers, and bean graph |
| AD bind returns account status/sub-errors needing interpretation | Generic factory does not reflect full AD semantics | Evaluate `ActiveDirectoryLdapAuthenticationProvider` |
| Tests pass locally but fail in real environment | LDIF, schema, OU, ACLs, or TLS differ from production | Test against staging directory/data close to production without sensitive data |

**Error classification:** `BadCredentialsException` is a user authentication failure at the Spring Security layer; `CommunicationException`/TLS/connection errors are directory communication issues; 403 is an authorization issue occurring **after** authentication. Do not collapse all errors into "wrong password" in operational logs, yet public client responses must never leak account existence or overly detailed internal status.

## 11. Design and operational principles

- **Never put passwords in Git:** use environment variables or a secret manager; grant least privilege to the search account.
- **Encrypt in transit:** HTTPS for users submitting passwords, LDAPS/StartTLS for application-to-LDAP connections, verifying CA and hostname.
- **Keep configuration aligned with version:** on Spring Security 6/7, write beans + lambda DSL and review changes across majors; avoid copying deprecated code.
- **Separate authentication from authorization:** a successful bind only proves a valid password; authorities must be retrieved and mapped according to schema and policy.
- **Limit search scope:** the more specific the base DN/OU, the easier it is to control; treat multi-entry search results as a configuration/data defect to fix.
- **Never let users directly control DN/filter:** use API placeholders and validate login names; test LDAP special characters too.
- **Test failure paths:** wrong credentials, non-existent account, LDAP downtime, ACLs, TLS certificates, and group changes.
- **Multiple security filter chains:** only a chain configured with the LDAP manager is guaranteed to pass credentials to it; review chain ordering and request matchers when an application uses multiple chains.

## 12. Decision summary

If your project is on **Spring Security 5.7+**, has an LDAP server, and needs username/password login, start from `BaseLdapPathContextSource` → `LdapBindAuthenticationManagerFactory` → `createAuthenticationManager()` → wire into `SecurityFilterChain`. Choose a **DN pattern** when the DN structure is guaranteed; choose a **search filter** when you need to look up the DN; add `LdapAuthoritiesPopulator` if policies rely on groups. For **Active Directory**, verify identifying attributes, bind method, and group mapping separately before deciding between the generic factory and the dedicated AD provider.

### Official documentation for version-by-version reference

- Spring Security 6.5, LDAP Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html
- Spring Security 7.0, LDAP Authentication: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/ldap.html
- Javadoc `LdapBindAuthenticationManagerFactory` (7.x): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/ldap/LdapBindAuthenticationManagerFactory.html
- Javadoc `AbstractLdapAuthenticationManagerFactory` (6.5): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html
- Javadoc `DefaultLdapAuthoritiesPopulator`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html
- Javadoc `ActiveDirectoryLdapAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Migration 6.5 → 7.0, LDAP: https://docs.spring.io/spring-security/reference/6.5/migration-7/ldap.html
