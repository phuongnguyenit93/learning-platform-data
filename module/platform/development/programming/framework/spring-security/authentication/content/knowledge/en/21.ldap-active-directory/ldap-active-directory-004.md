# LDAP/Active Directory: Password comparison and when to use it

## 1. Objectives

In Spring Security, **password comparison** is an authentication strategy for LDAP accounts that compares the user-entered password against password data stored in the directory. This strategy is only appropriate when **password storage, attribute access permissions, verification mechanism, and directory security policies** all allow it.

After this lesson, you should be able to distinguish:
- `bind authentication`: the directory authenticates by attempting a bind using the user's own identity and password;
- **LDAP Compare**: the application asks the directory to compare a value against the password attribute without reading the stored value;
- **local password comparison**: the application has permission to read the stored password value (usually a hash) and calls `PasswordEncoder.matches(rawPassword, storedHash)`.

**Quick rule of thumb:** For Active Directory (AD DS) and most enterprise LDAP directories, prefer **bind**. Only deploy password comparison when you have proven that the directory supports the right mode and does not bypass account policies.

## 2. Context: where does password comparison operate?

Suppose there is an LDAP tree:

~~~text
dc=example,dc=org
└── ou=people
    └── uid=alice
        ├── uid: alice
        ├── cn: Alice Nguyen
        └── userPassword: <password value or hash managed by the directory>
~~~

- **DN (Distinguished Name)** identifies an entry: `uid=alice,ou=people,dc=example,dc=org`.
- `uid` is commonly used to look up users in standard LDAP; Active Directory may use `sAMAccountName` or `userPrincipalName`.
- `userPassword` is the default attribute name for password comparison in Spring Security LDAP; an actual directory may name it differently.
- `Authentication` answers **who the user is and whether they are validly authenticated**; `GrantedAuthority`/groups resolve **what they are allowed to do**. Successful password verification does not automatically grant administrative privileges.

Spring Security provides `BindAuthenticator` and `PasswordComparisonAuthenticator` for LDAP, via `LdapAuthenticationProvider` or factories that configure `AuthenticationManager`. Standard LDAP bind does not use `UserDetailsService`/`DaoAuthenticationProvider` to read hashes and match them like accounts stored in an application database.

## 3. Three ways to verify passwords

### 3.1. Bind: directory authenticates directly

~~~text
Client sends username + password
    ↓
Spring Security searches for DN (or derives DN from pattern)
    ↓
TLS connection to directory, bind with user's DN/UPN + password
    ↓
Directory applies its login logic → success/failure
    ↓
Spring Security loads required attributes and groups
~~~

The application **does not need to read the password attribute** and does not need to know which hashing algorithm was used. This is usually the best choice when the directory manages account lockouts, password expiration, policies, and login conditions. For AD, use `ActiveDirectoryLdapAuthenticationProvider` or a bind strategy suited to UPN/domain.

### 3.2. LDAP Compare: comparison on the directory server

~~~text
Client sends username + password
    ↓
Application binds with service account having search/compare permissions
    ↓
Search for user DN
    ↓
LDAP Compare(userDN, passwordAttribute, candidateValue)
    ↓
Directory returns compare result true/false (or LDAP error)
~~~

**There is no need to read the stored password value**, yet the **candidate** is still transmitted to the directory; therefore, the connection must be protected with TLS. LDAP Compare is an attribute comparison under directory semantics, **not a guarantee that the directory executed its full login workflow**. Whether locked, expired, or disabled accounts are checked depends on the directory/configuration: verify by testing, never assume.

If the application must hash the submitted password itself before comparing against a hash via LDAP Compare, hashes with a **random salt** (SSHA, bcrypt, Argon2, etc.) cannot be reproduced into the exact same hash string from the submitted password alone. In those cases, do not treat LDAP Compare with a pre-encoded hash as the default approach.

### 3.3. Local compare: reading the hash and verifying in the application

~~~text
Client sends username + password
    ↓
Application uses service account to search for user DN
    ↓
Read password/hash attribute permitted for reading by the directory
    ↓
PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Return result; check required account statuses separately
~~~

This approach can handle salted hashes such as bcrypt, because `matches` uses the salt and parameters embedded in the **stored hash**. However, the application/service account must have permission to read password data, the hash must be in a format compatible with the encoder, and the system must address all policy checks that bind would otherwise handle. **A retrieved hash is still sensitive data**; never log it, cache it indiscriminately, or return it to the client.

Keep this distinction clear: configuring `new BCryptPasswordEncoder()` is meaningful only if the directory stores a **readable and properly formatted bcrypt hash**. You cannot use bcrypt to "decrypt" an AD password.

## 4. Strategy selection table

| Criterion | Bind (usually preferred) | Server-side LDAP Compare | Local compare in application |
|---|---|---|---|
| Must the application read the password/hash? | No | No | Yes, permission must be granted |
| Must the directory's hash algorithm be known? | No | Depends on compare mechanism/value | Yes, compatible `PasswordEncoder` required |
| Random-salted hashes | Handled by directory | Usually unsuitable for comparing client-generated hashes | Possible, if valid hash is readable |
| Account lockout/expiration policies | Usually follows directory authentication flow | Must be verified separately | Must be enforced/verified separately |
| Active Directory DS | **Recommended** | Do not choose by default | Usually infeasible/inappropriate |
| Typical risks | TLS, DN/search config, bind permissions | Compare permissions, algorithm mismatch, bypassed policies | Hash exposure, policy drift, wrong hash format |
| When to consider | Enterprise AD/LDAP where passwords cannot be read | Directory permits compare, candidate matches, policies verified | Custom directory allowing hash reads, specific requirements, and strict controls |

**Do not equate "not reading the password" with "absolute security"**: both LDAP Compare and bind require TLS, least privilege, brute-force controls, and proper error-handling policies.

## 5. Conditions for password comparison to be an appropriate choice

Choose **LDAP Compare** only when all of the following are met:

1. The directory supports the compare operation on the exact password attribute; the account/service principal has permissions to compare, search for DNs, and read necessary attributes.
2. The candidate value produced by Spring Security is compatible with how the directory stores/compares passwords. Do not assume `userPassword` is always plaintext or always a single hash type.
3. Reading the hash is not required to match a random-salted algorithm; or a dedicated compare mechanism **confirmed to be supported by the directory** is available.
4. Behavior has been tested for locked accounts, disabled accounts, expired passwords, forced password changes, and connection errors.
5. `ldaps://` or StartTLS is configured with **proper certificate verification**, least-privilege service account permissions, login rate limiting, and monitoring.
6. User lookup, group mapping, and search scope are verified to be accurate, disallowing ambiguity from multiple entries matching the same username.

Choose **local compare** only when you also prove that: (a) hashes can be legally/validly read with least-privilege permissions; (b) the encoder works with the exact format, prefix, and salt; (c) compliance requirements permit the application to handle hashes; (d) checks for account status, lockout, password expiry, and related policies are not bypassed. If any essential condition is missing, **use bind**.

Cases where password comparison should be avoided: standard AD DS integration; directories disallowing reading/comparing the attribute; passwords protected with an incompatible algorithm/format; requirements that the domain controller enforce account policies on login; production systems using `NoOpPasswordEncoder` for plaintext; or cases where the service account requires overly broad privileges to function.

## 6. Spring Boot 3.x / Spring Security 6.x / Java 17+ example

The following example uses a **custom LDAP directory**, with explicit preconditions: entries in `ou=people` have a `userPassword` attribute containing a **bcrypt hash in a format readable by `BCryptPasswordEncoder`**, the service account is permitted to read that attribute, and account policies are handled/verified separately. This is a configuration for an existing Spring Boot application; **actual login is impossible without an LDAP server, user data, trusted certificates, and connection details**.

### 6.1. Dependencies

In `pom.xml` of a Spring Boot project that already declares the corresponding parent/BOM:

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-ldap</artifactId>
    </dependency>
</dependencies>
~~~

### 6.2. Configuring URLs and secrets

File `src/main/resources/application.properties`:

~~~properties
# Base DN is placed in the URL; ou=people below is a relative search base.
app.ldap.url=ldaps://ldap.example.org:636/dc=example,dc=org
app.ldap.manager-dn=${LDAP_MANAGER_DN}
app.ldap.manager-password=${LDAP_MANAGER_PASSWORD}
~~~

- Supply `LDAP_MANAGER_DN` and `LDAP_MANAGER_PASSWORD` from a secrets manager/environment; never commit secrets to Git.
- The JVM must trust the CA issuing the LDAP server's certificate. Do not disable hostname/certificate verification to "fix" TLS errors.
- `uid`, `ou=people`, and `userPassword` are **examples**; change them to match the actual directory schema.

### 6.3. AuthenticationManager using password comparison

File `src/main/java/com/example/security/LdapCompareConfiguration.java`:

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapPasswordComparisonAuthenticationManagerFactory;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;

@Configuration
public class LdapCompareConfiguration {

    @Bean
    BaseLdapPathContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.manager-dn}") String managerDn,
            @Value("${app.ldap.manager-password}") String managerPassword) {

        DefaultSpringSecurityContextSource source =
                new DefaultSpringSecurityContextSource(url);
        source.setUserDn(managerDn);
        source.setPassword(managerPassword);
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        var factory = new LdapPasswordComparisonAuthenticationManagerFactory(
                contextSource, new BCryptPasswordEncoder());
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");
        factory.setPasswordAttribute("userPassword");
        return factory.createAuthenticationManager();
    }
}
~~~

**Part-by-part explanation:**

1. `DefaultSpringSecurityContextSource` configures the LDAP server and base DN; the service account is used to search for entries and, if needed, read the password attribute.
2. `setUserSearchBase("ou=people")` restricts the account search area; `setUserSearchFilter("(uid={0})")` uses the username as a filter parameter, avoiding manual LDAP filter string concatenation from input.
3. `setPasswordAttribute("userPassword")` specifies the attribute holding password data; the factory's default is also `userPassword`.
4. `new BCryptPasswordEncoder()` works **only when** the stored value is bcrypt-compatible. For password comparison based on a readable hash, the application uses the corresponding matching logic; do not infer that the LDAP server uses bcrypt solely from the attribute name.
5. The factory returns an `AuthenticationManager` integrated with LDAP for the username/password flow. **Successful account authentication does not prove all account statuses were checked.**

If the project needs a `SecurityFilterChain`, configure form login or HTTP Basic appropriate to the application; minimal example:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests ->
                        requests.anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Place the classes in a subpackage of the package containing `@SpringBootApplication` so Spring scans them. The login example using the default UI has no fixed stdout; results depend on the actual account and directory. **Do not place an LDAP-comparing `AuthenticationManager` and another AD provider in the same example without clearly designing provider ordering and scope.**

### 6.4. Why using bcrypt does not mean remote LDAP Compare

Java example runnable in a project that has `spring-security-crypto` (included via `starter-security`), file `PasswordEncoderCheck.java`:

~~~java
package com.example.security;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

public final class PasswordEncoderCheck {
    public static void main(String[] args) {
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
        String storedHash = encoder.encode("demo-password");

        System.out.println(encoder.matches("demo-password", storedHash));
        System.out.println(encoder.matches("wrong-password", storedHash));
    }
}
~~~

Output when running `main` via IDE or the project classpath:

~~~text
true
false
~~~

`encode` generates a random salt, so the hash string differs across runs; `matches` still returns the right result because it compares against the **stored hash**. This is **local comparison**, not a remote LDAP Compare operation. In production systems, never hardcode passwords in source code or log hashes.

### 6.5. When is a simple LDAP Compare configuration needed?

Spring Security also documents creating the factory with `NoOpPasswordEncoder.getInstance()` to illustrate comparison against a directory with matching values:

~~~java
var factory = new LdapPasswordComparisonAuthenticationManagerFactory(
        contextSource, NoOpPasswordEncoder.getInstance());
factory.setUserDnPatterns("uid={0},ou=people");
AuthenticationManager manager = factory.createAuthenticationManager();
~~~

This snippet **only illustrates the API**, intended for learning environments with a compatible server. `NoOpPasswordEncoder` does not hash passwords; never use it to design new password storage or replace production password protection policies. Running this snippet requires importing `AuthenticationManager`, `LdapPasswordComparisonAuthenticationManagerFactory`, and `NoOpPasswordEncoder` along with an existing `contextSource`; it is not a standalone Java program.

## 7. When switching to bind or Active Directory

### Standard LDAP: switching to bind

If you lack permission to read hashes, or need the directory itself to verify passwords, replace the `AuthenticationManager` bean above with **one of the bind configurations**:

~~~java
@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {
    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    return factory.createAuthenticationManager();
}
~~~

Add import `org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory`. The example reuses the configured `ldapContextSource` bean. Bind can authenticate accounts even when the application is not allowed to read `userPassword`.

### Active Directory DS: using the dedicated provider

~~~java
@Bean
ActiveDirectoryLdapAuthenticationProvider adAuthenticationProvider() {
    return new ActiveDirectoryLdapAuthenticationProvider(
            "corp.example.org",
            "ldaps://dc1.corp.example.org:636/");
}
~~~

Import `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`. This is a **replacement for the LDAP compare option**, to be integrated into the security configuration in the right context. AD typically accepts `user@domain`/UPN and manages passwords in its own way. According to Microsoft documentation, `unicodePwd` **cannot be read via LDAP search**, so "reading the hash from AD and calling `PasswordEncoder.matches`" is not a valid integration path. The AD provider relies on authentication operations against a domain controller; TLS, domain name, certificates, and access permissions must still be properly configured.

## 8. Security checklist before going to production

- **Transport:** LDAPS/StartTLS, validate trust chain and hostname; never transmit passwords over unprotected `ldap://`. Test connectivity to each domain controller/LDAP replica.
- **Least privilege:** the service account only has search/compare permissions or read permissions for strictly required attributes; never grant password-modification permissions to an application that only authenticates.
- **Password storage:** the directory manages hashing, salting, rotation, and access controls; never enable plaintext just to make LDAP Compare work.
- **Account policy:** verify account lockout, `disabled` status, password expiration, `must change password`, and time/device restrictions if applicable; with local compare these are very easy to miss. Do not treat compare returning true as "allowed to log in" when policies require additional checks.
- **Input & errors:** use search filters with appropriate placeholders/escaping; prevent LDAP filter injection; do not return detailed differences between wrong username and wrong password to clients.
- **Throttling & logging:** limit retries, monitor connection errors/latency; never log raw passwords, hashes, `Authorization` headers, or LDAP bind credentials.
- **Separate authentication and authorization:** after authentication, map LDAP/AD groups to `GrantedAuthority` according to approved rules; never infer roles from usernames.
- **Maintainability:** timeouts, connection pooling appropriate to the bind mechanism, HA/failover, and policies when the directory fails; never "bypass" authentication on timeout.

## 9. Test matrix to verify against a real LDAP/AD

| Scenario | Expectation |
|---|---|
| User exists, correct password, valid account | Authentication succeeds; roles match groups |
| Wrong password | Rejected; no password or account details exposed |
| Non-existent username / non-matching filter | Rejected; wrong entry never selected |
| User outside search base, or multiple matching entries | Handled deterministically; never picks the wrong person |
| Service account cannot read/compare password | Fails clearly on server/safe logs; no uncontrolled fallback |
| Stored hash incompatible with encoder or different prefix | Authentication fails; fix mechanism/format, do not replace with NoOp |
| Account disabled, locked, password expired | Behavior matches agreed policy; test separately per strategy |
| LDAP server/CA/DNS unavailable | Fail closed, with timeouts and monitoring; never skip authentication |
| Repeated wrong passwords | Rate limiting and lockout operate per real requirements |
| AD account using UPN/domain | Bind with AD provider succeeds when credentials and policy are valid |

**Testing technique:** prepare a test directory with the accounts and states listed above; test `AuthenticationManager.authenticate(...)` or login through the endpoint; verify HTTP outcomes, `Authentication`, `GrantedAuthority`, safe logs, and directory-side audits. Never assert against a fixed random-salted hash output.

## 10. Common errors and diagnosis

1. **`BadCredentialsException` despite correct password:** check base DN, `userSearchBase`, `userSearchFilter`, `uid`/`sAMAccountName` attribute, prefix/hash format, and the active strategy. With LDAP Compare, verify whether the directory truly supports comparing that attribute.
2. **Insufficient permission to read attribute:** remote compare may use different permissions from local compare; grant exact least-privilege permissions or switch to bind instead of arbitrarily expanding admin privileges.
3. **Stored `{SSHA}` but configured with bcrypt or NoOp:** incompatible. Random-salted hashes require a matcher that can read the stored hash and understand its format; do not compare re-encoded hash strings.
4. **AD has no readable `userPassword`:** this is a design/permission boundary, not a Spring Security bug; use AD bind.
5. **LDAP over TLS reports handshake failure:** check CA, SAN/hostname, certificate chain, TLS version, and truststore configuration instead of disabling certificate verification.
6. **Correct password but disabled/locked account still passes:** password comparison does not automatically replace login policies; add explicit checks or switch to bind.
7. **Valid login returns 403:** authentication may have succeeded while authorization/group mapping is wrong; inspect `LdapAuthoritiesPopulator` and `authorizeHttpRequests` rules.

## 11. Key takeaways

- **Password comparison ≠ bind:** compare checks an attribute; bind asks the directory to log in using the user's credentials.
- **Server-side compare ≠ local hash verification:** which side reads the stored hash, which side performs matching, and the algorithm/hash format create different security requirements.
- **AD normally uses bind:** do not attempt to read `unicodePwd` or recreate AD passwords with `PasswordEncoder`.
- **Prioritize directory identity policies:** only choose compare after verifying the mechanism, permissions, algorithm, transport protection, and account states through testing.

## References

- [Spring Security 6.5 — LDAP Authentication: Bind, Password Comparison, Active Directory](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Security API — LdapPasswordComparisonAuthenticationManagerFactory](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/ldap/LdapPasswordComparisonAuthenticationManagerFactory.html)
- [Spring Security — Password Storage / BCryptPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Microsoft Learn — Change Windows Active Directory and LDS user password through LDAP](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/change-windows-active-directory-user-password)
