# Bind authentication with user credentials (LDAP and Active Directory)

## Learning objectives

After this lesson, you can explain how an LDAP `bind` authenticates using the user's own username and password; distinguish **finding a DN** from **verifying a password**; choose between `userDnPatterns` and `userSearchFilter` in Spring Security; configure a bind-based login flow; and handle security risks and common errors when working with LDAP/Active Directory (AD).

## 1. What is binding with user credentials?

LDAP (Lightweight Directory Access Protocol) allows an application to search and access entries in a directory service. A user entry has a unique **Distinguished Name (DN)** according to the directory tree structure. For example:

```text
uid=lan,ou=people,dc=example,dc=org
└─ uid=lan       : user entry
   ou=people     : organizational unit containing users
   dc=example,dc=org : directory base DN
```

In a **simple bind with user credentials**, the application sends the bind identity (usually a DN; in AD it can be in `user@domain` form) along with **the password just received from the user** to the LDAP server over a TLS-protected connection. The **LDAP server**, according to its data and account policies, decides whether those credentials are valid. The application relies solely on the success/failure result and does not need to read `userPassword`, fetch a password hash, or match passwords itself in Java.

Here, "user credentials" refers to the **credentials** the user presents for the login session, typically username/password. Do not confuse this with an OAuth2 token, a user search result, or the password of a technical service account. LDAP bind does not create MFA by itself and does not replace federated login mechanisms such as OIDC/SAML.

Distinguish three items:

- **Username**: e.g. `lan`; the form value entered by the user, not necessarily a DN.
- **DN**: e.g. `uid=lan,ou=people,dc=example,dc=org`; identifies the entry's position in LDAP.
- **User credentials**: username/password submitted at login, used in the bind call for **that specific account**. A service account used to search the directory, if any, does not prove the user's password.

Example: LDAP has user `uid=lan,ou=people,dc=example,dc=org` with a secret password. If binding with that DN and the right password, the server accepts; if the password is wrong, the server rejects. The application **never receives the actual password back** from LDAP.

## 2. Authentication flow from application to LDAP

```text
User
   │ 1. Send username + password over HTTPS
   ▼
Spring Security (AuthenticationManager / LDAP provider)
   │ 2. Resolve DN: DN pattern or search user by filter
   │ 3. Open secure LDAP connection and bind with user's DN + password
   ▼
LDAP/AD server
   │ 4. Verify password + account status/policy
   ├── Reject ──> AuthenticationException ──> login fails
   └── Accept
           │ 5. Optionally read attributes and determine groups/authorities
           ▼
Spring Security creates successful Authentication
           │ 6. SecurityContext holds principal + authorities
           ▼
Application applies authorization rules to subsequent requests
```

The **deciding point for success** is the bind step using the user's credentials. Finding an LDAP entry in step 2 is **not yet** authentication. Conversely, a successful bind only answers "this person has been authenticated"; accessing `/admin` or a specific API also depends on **authorization** (roles/authorities and application policies).

Spring Security uses `LdapAuthenticator` (typically `BindAuthenticator`) for this mechanism. It does not use `UserDetailsService` to read an LDAP password and compare it. After authentication, `LdapAuthoritiesPopulator` can fetch group information and convert it into authorities; this step is separate.

### Typical outcomes

| Scenario | LDAP Bind | Consequence in the application |
|---|---|---|
| Correct DN, correct password, account allowed to log in | Succeeds | Can create an authenticated `Authentication`; apply access permissions |
| Wrong password | Rejected | Login fails; no valid authenticated session created |
| User not found or wrong DN | Cannot bind as the right user | Login fails |
| Account locked/expired/disabled | Per server policy, usually rejected | Login fails; do not disclose detailed reasons to strangers |
| LDAP server/TLS unavailable | Cannot authenticate reliably | **Fail closed**: reject login, do not fall back to skipping checks |

## 3. Turning a username into a bind identity

### 3.1. DN pattern: when the user's location is predictable

Suppose all users reside under `ou=people,dc=example,dc=org` and the identifying attribute is `uid`. Spring Security can use a pattern:

```text
userDnPatterns = "uid={0},ou=people"
username       = "lan"
LDAP base DN   = "dc=example,dc=org"
final DN       = "uid=lan,ou=people,dc=example,dc=org"
```

`{0}` is where Spring Security substitutes the username. This approach is fast, takes fewer steps, and avoids traversing the directory tree. It is **not suitable** if users reside in multiple OUs, if the DN uses a `cn` different from the username, or if users can move locations in AD.

### 3.2. Search-then-bind: when the DN is not known in advance

If users reside in multiple OUs, the application needs to **search for the entry first, then bind**:

1. Search from `userSearchBase` using `userSearchFilter`, such as `(uid={0})`, under the configured base DN.
2. Retrieve the DN of the single matching entry.
3. Bind with **the user's password**, using the DN just found.
4. Recognize the login only after the bind succeeds.

Example: search base `ou=people` + filter `(uid=lan)`, evaluated under base DN `dc=example,dc=org`. The result might be `uid=lan,ou=developers,ou=people,dc=example,dc=org`, and then the application uses that DN to bind.

The **search** operation may need a directory reader identity with minimal permissions (a search account) if the directory forbids anonymous search. This account is only for lookups; it does not replace binding with the user's credentials. If 0 or multiple indistinguishable entries are found, never pick one arbitrarily and accept the login.

### 3.3. Active Directory: login identity can be a UPN

AD commonly accepts a **User Principal Name (UPN)** such as `lan@corp.example.org`, alongside the DN structure. Spring Security provides `ActiveDirectoryLdapAuthenticationProvider` to handle the common AD model. Distinguish the domain name/UPN from the user's actual DN; **do not assume** plain LDAP and AD share the same schema, group search rules, or error codes.

| Approach | Suitable when | What to watch out for |
|---|---|---|
| DN pattern + user bind | Stable DN structure, same OU | DN pattern must match the schema |
| Search user then user bind | Multiple OUs, DN cannot be derived | Search scope, filter, read permissions, and unique result |
| AD provider + UPN bind | Enterprise Active Directory | Domain/UPN, TLS, account policies, and AD group mapping |

## 4. Configuring Spring Security with Java 17+ and Spring Boot 3.x

The example below is a **Spring Boot application configuration**, not a standalone Java file runnable via `javac`. It uses **Spring Security 6.x** and an existing LDAP server with user entries structured as `uid=...,ou=people,dc=example,dc=org`. Adjust the package, URL, and DN pattern to match your actual system. Spring Boot manages the versions of the corresponding dependencies.

### 4.1. Gradle dependencies

In a project that already has the Spring Boot plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
}
```

`spring-security-ldap` provides the LDAP authentication provider and factory. The LDAP starter provides Spring LDAP integration. No application `PasswordEncoder` is needed to verify passwords manually in **bind authentication**.

### 4.2. Connecting to LDAP over TLS

`src/main/resources/application.yml`:

```yaml
app:
  ldap:
    provider-url: "${LDAP_PROVIDER_URL:ldaps://ldap.example.org:636/dc=example,dc=org}"
```

The example URL includes `ldaps://host:636/` and the **base DN** `dc=example,dc=org`. For another tree structure, replace the base DN part to match the directory. The `LDAP_PROVIDER_URL` environment variable should be supplied by infrastructure; the LDAP server's certificate must be trusted by the JVM and the hostname must match the certificate. Do not disable TLS verification to "fix" connection errors.

### 4.3. Configuring bind with a DN pattern

Create `src/main/java/com/example/security/LdapSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LdapSecurityConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource(
            @Value("${app.ldap.provider-url}") String providerUrl) {
        return new DefaultSpringSecurityContextSource(providerUrl);
    }

    @Bean
    AuthenticationManager authenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager authenticationManager)
            throws Exception {
        http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**Execution flow explanation:**

1. `ldapContextSource` defines the server and base DN for the LDAP connection. In this example the URL already includes the base DN; do not append the base DN a second time.
2. `LdapBindAuthenticationManagerFactory` creates an `AuthenticationManager` that uses bind. `setUserDnPatterns("uid={0},ou=people")` specifies the relative DN under the base DN.
3. `HttpSecurity.authenticationManager(...)` wires that manager into the HTTP login flow. `formLogin` provides the default login form and handles success/failure via Spring Security's mechanism.
4. `anyRequest().authenticated()` requires a logged-in identity. It does **not** automatically require `ROLE_ADMIN`.
5. The `SecurityFilterChain` bean does not make other endpoints public; to restrict permissions in detail, add authorization rules.

**To run:** use a Spring Boot application with `@SpringBootApplication`, configure the corresponding LDAP server, set the environment variable if the URL differs from the example, and run `./gradlew bootRun` (or `gradlew.bat bootRun` on Windows). Visiting a protected page redirects to the login page; enter a real account in the directory to test. A fixed HTTP output cannot be guaranteed without an actual LDAP server, directory data, and application configuration.

### 4.4. Switching to search user then bind

If user DNs do not follow a fixed pattern, **replace** the `authenticationManager` method above with:

```java
@Bean
AuthenticationManager authenticationManager(
        BaseLdapPathContextSource contextSource) {
    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    return factory.createAuthenticationManager();
}
```

This is a **drop-in replacement inside the same class** (keep the imports from the full example); do not declare two beans with the same name. `setUserSearchBase` is a relative DN from the root of `ContextSource`. Never concatenate the username directly into a manually built LDAP filter string; use context-appropriate parameterization/filter escaping to prevent LDAP injection. If the directory requires a dedicated reader account for searching, configure credentials securely with least privilege on the lookup context, while still authenticating the user via a separate bind.

### 4.5. When the directory is Active Directory

An **independent example of provider selection** (do not combine it simultaneously with the plain LDAP manager above just to describe the same flow):

```java
@Bean
ActiveDirectoryLdapAuthenticationProvider adAuthenticationProvider() {
    return new ActiveDirectoryLdapAuthenticationProvider(
        "corp.example.org",
        "ldaps://dc1.corp.example.org:636/");
}
```

Import `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`. Register this provider with the application's `HttpSecurity`/`AuthenticationManager` if choosing the AD branch. The UPN is typically in the form `lan@corp.example.org`. Do not copy OpenLDAP's `uid=...` DN pattern to AD when the actual schema/OUs differ; verify the search filter, domain, and groups on the AD in use. The AD snippet above is an **illustrative bean**, not a second complete Spring Boot application.

## 5. Retrieving permissions after successful authentication (authorization)

A user can bind successfully yet not hold `ROLE_ADMIN`. To map LDAP groups to Spring Security authorities, use `LdapAuthoritiesPopulator`; the sample below uses `groupOfNames` groups with a `member` attribute containing member DNs:

```java
@Bean
LdapAuthoritiesPopulator ldapAuthorities(
        BaseLdapPathContextSource contextSource) {
    var populator =
        new DefaultLdapAuthoritiesPopulator(contextSource, "ou=groups");
    populator.setGroupSearchFilter("(member={0})");
    populator.setGroupRoleAttribute("cn");
    return populator;
}

@Bean
AuthenticationManager authenticationManager(
        BaseLdapPathContextSource contextSource,
        LdapAuthoritiesPopulator authorities) {
    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserDnPatterns("uid={0},ou=people");
    factory.setLdapAuthoritiesPopulator(authorities);
    return factory.createAuthenticationManager();
}
```

Additional imports: `org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator` and `org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator`. **Replace** the `authenticationManager` bean from section 4.3 if applying this snippet. With group search base `ou=groups`, the application searches for groups under `ou=groups,dc=example,dc=org`. The `cn` attribute is selected as the role name; check `DefaultLdapAuthoritiesPopulator`'s configuration for `ROLE_` prefixing and uppercase conversion, and do not assume every group automatically yields the exact role the application needs.

If the directory requires separate permissions to read groups, resolve query permissions securely; do not skip authorization checks when group lookup fails. AD uses `memberOf`, different group types/nested groups, and different mapping rules from this OpenLDAP example. Design application permissions according to the principle of least privilege and verify the approved group source.

## 6. Testing and observing failures

You can test bind capability independently beforehand using a command on a machine with OpenLDAP tools that trusts the LDAP certificate:

```bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D 'uid=lan,ou=people,dc=example,dc=org' \
  -W
```

`-x` requests simple authentication; `-D` is the bind DN, and `-W` prompts interactively for the password (keeping the password off the command line). With valid credentials, the command returns the server-confirmed identity; the response format depends on the server. Do not re-run the command with `-w <password>` in a real environment's shell history.

| Test case | Expectation |
|---|---|
| Valid username/password | LDAP bind succeeds; Spring Security authenticates post-login requests |
| Wrong password | LDAP rejects; session remains unauthenticated |
| Non-existent user / wrong DN pattern | Authentication fails; internal logs should distinguish misconfiguration from non-existent accounts |
| Empty password or missing password | Rejected before accepting bind; never treat anonymous/unauthenticated bind as success |
| User in a different OU | DN pattern may fail; search-then-bind can resolve it if filter/base are correct |
| AD account locked/expired | Outcome follows AD policy; application flow must reject |
| Cannot read groups | Identity authentication may succeed, but privileges must not be escalated |
| Invalid TLS certificate / server disconnects | Reject login and alert operations; do not fall back to plaintext LDAP |
| User input contains special characters in filter/DN | Must not alter query syntax unintentionally; test LDAP injection cases |

When debugging, follow this order: **TLS connection and DNS** → **base DN** → **DN pattern or search base/filter** → **bind errors and account status** → **group/authority mapping** → **HTTP access rules**. For example, an LDAP `invalidCredentials` error can come from a wrong password or a directory-side authentication policy; do not assume all errors mean "wrong password". Log at most error codes, timestamps, operation types, and correlation IDs; never log passwords, cookies/session tokens, service account secrets, or sensitive LDAP entry data.

## 7. Non-negotiable security requirements

1. **Protect the transport channel:** user form to application over HTTPS; application to directory using **LDAPS** or **properly configured and tested StartTLS**. Validate the CA certificate and hostname. Do not send simple-bind passwords over unencrypted `ldap://` in production environments.
2. **Reject empty passwords:** RFC 4513 includes "unauthenticated bind," where a non-empty DN + empty password may be treated by the server as anonymous access. Never treat a server allowing that operation as proof that the user logged in. Frameworks/libraries must be kept patched; test explicitly. Spring LDAP has advisory **CVE-2026-41720 (08/06/2026)** regarding a related issue in some library versions.
3. **Do not read or store LDAP passwords yourself:** bind returns an authentication status; do not store plaintext passwords in the DB/session/logs or forward them to other services. Sending the password to the server over TLS for verification is the nature of simple bind.
4. **Prevent LDAP injection:** usernames must never be freely concatenated into DNs or filters; distinguish **DN** escaping (RFC 4514) from **filter** escaping (RFC 4515). Use framework parameterization and restrict input values where appropriate.
5. **Least privilege:** the technical search account, if used, has read permission only for the attributes genuinely needed; user account binds are governed by LDAP policy. Never grant application admin privileges just because a bind succeeded.
6. **Protect against password guessing:** apply rate limiting, backoff/lockout aligned with directory policy, and monitor failed login attempts. Avoid causing unintended mass account lockouts through excessive retries.
7. **Fail closed and bound timeouts:** configure connection timeouts/resources and verify directory resilience; when LDAP does not respond, never default to `authenticated=true` or skip the bind step.
8. **Safe error handling:** return generic messages like "Invalid credentials" to clients while keeping disabled/locked/expired account details in restricted operational channels. Do not leak username enumeration.
9. **Session control:** bind only verifies credentials at a point in time. When an account is revoked after login, existing sessions are not invalidated immediately unless the application enforces appropriate session/revalidation policies.

## 8. Common misconceptions and how to fix them

- **"Finding the user in LDAP means login succeeded."** False. Search only returns an entry; a user bind with a valid password is still required.
- **"Connecting with the service account authenticates all users."** False. The service account only holds its own identity; it does not verify a user's password.
- **"Spring Security must fetch `userPassword` to compare."** False for bind. The LDAP server verifies the secret; the application does not need to know the password hash.
- **"Using `uid={0},ou=people` works for every AD."** False. AD typically uses UPN, `sAMAccountName`, and different DNs or OUs; pick a strategy based on the actual schema.
- **"Successful login means admin privileges."** False. Bind is authentication; roles/groups are authorization data that must be mapped and evaluated separately.
- **"If the LDAP server returns success with an empty password, that's secure enough."** False: unauthenticated bind must be rejected and libraries kept patched.
- **"With LDAPS, we don't need LDAP injection protection."** False. TLS protects data in transit; it does not sanitize filters or DNs constructed by the application.

## 9. Self-check

**Question 1.** Why is search-then-bind not considered authenticated right after the search returns a DN?  
**Answer:** Search locates the user entry; only a bind using the credentials supplied by the user verifies those credentials.

**Question 2.** When users are in multiple OUs, how should the configuration change?  
**Answer:** Use `setUserSearchBase` and `setUserSearchFilter` to locate the right DN, then bind as before. Bound the search scope and ensure the filter is safe.

**Question 3.** Can `hasRole("ADMIN")` be satisfied merely because LDAP bind succeeded?  
**Answer:** No. Groups/authorities must be retrieved and mapped according to policy before applying authorization.

**Question 4.** Why must an empty password be blocked even if the server returns "bind success"?  
**Answer:** LDAP may permit unauthenticated/anonymous bind; that kind of success does not prove the user's identity or password.

## References

- [Spring Security — LDAP Authentication (6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind, search+bind, authorities, AD provider.
- [Spring Security — LDAP Authentication (7.0)](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/ldap.html): comparing concepts on the newer framework branch.
- [OWASP — LDAP Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html): escaping, least privilege, preventing unauthenticated bind.
- [Spring — CVE-2026-41720](https://spring.io/security/cve-2026-41720/): details on affected Spring LDAP versions and patches for the empty-password bind case.
