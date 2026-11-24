# LDAP connection, base DN, and the search bind account

In a Spring Security application using LDAP or Active Directory (AD), authentication only works properly when the application knows **which server to connect to**, **which branch to start searching for users from**, and **which identity to use to perform the search**. These three settings are related but serve different roles; confusing them can cause the application to connect successfully yet still fail to find accounts.

This lesson focuses on the LDAP connection, `base DN`, and the search account (*service/bind account*) in a password-based login flow. The Java examples use Spring Boot 3.x, Spring Security 6.x, and Java 17+; hostnames, DNs, and accounts are illustrative data.

## 1. Identifying the LDAP structure

LDAP (Lightweight Directory Access Protocol) provides a way to query and manipulate *entries* in a directory service. AD is Microsoft's directory service that supports the LDAP protocol while also having its own account conventions and attributes.

Each entry is identified by a **distinguished name (DN)**, which is its full path in the directory tree. For example:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   └── uid=nam
├── ou=groups
└── ou=service
    └── cn=svc-ldap-reader
~~~

In the diagram, a user entry has the full DN:

~~~text
uid=linh,ou=people,dc=example,dc=org
~~~

Components to distinguish:

| Component | Meaning | Example |
| --- | --- | --- |
| `dc` (*domain component*) | Domain name component in the LDAP tree | `dc=example,dc=org` |
| `ou` (*organizational unit*) | Organizational branch containing users, groups, or resources | `ou=people` |
| `uid`, `cn` | Attributes that may appear in an entry's name; choice depends on schema | `uid=linh`, `cn=svc-ldap-reader` |
| RDN (*relative distinguished name*) | Relative name component of an entry compared to its parent | `uid=linh` |
| DN | Full name of the entry, consisting of the RDN and parent branches | `uid=linh,ou=people,dc=example,dc=org` |
| Base DN | Context root used by the client as the starting point for relative operations | `dc=example,dc=org` |

LDAP does not force every organization to use `ou=people` or the `uid` attribute. In AD, usernames are typically searched by `sAMAccountName` or `userPrincipalName`, and a DN may look like `CN=Linh Nguyen,OU=Employees,DC=corp,DC=example,DC=com`.

### Base DN, search base, and search account DN

Suppose an application has the following values:

~~~properties
LDAP_URL=ldaps://directory.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_USER_SEARCH_BASE=ou=people
LDAP_USER_SEARCH_FILTER=(uid={0})
LDAP_BIND_DN=cn=svc-ldap-reader,ou=service,dc=example,dc=org
~~~

Meaning:

1. **LDAP URL** specifies the server and transport protocol. `ldaps://` indicates LDAP over TLS from the very start of the connection.
2. **Base DN** is the root used for relative DNs in `ContextSource`. Here it is `dc=example,dc=org`.
3. **User search base** narrows the user search scope under the base DN. Here `ou=people` is a **relative** path, so the effective search scope is `ou=people,dc=example,dc=org`.
4. **User search filter** selects the matching entry within that scope. With username `linh`, `(uid={0})` becomes the condition searching for `uid=linh`.
5. **Bind DN** specifies the identity the application uses to read/search the directory. This DN is a **full DN** (depending on the server, other principal formats may also be supported); do not append the base DN to it. This account's password is configured separately.

**Common pitfall:** `LDAP_BIND_DN` is not the DN of the end user logging in. It is a technical account granted lookup permissions. The discovered DN, such as `uid=linh,ou=people,dc=example,dc=org`, is the identity attempted for binding with the user's password in LDAP bind authentication.

If you set `userSearchBase=""`, the search starts at the base DN itself. If you pass a full DN where an API expects a relative DN, you may accidentally duplicate `dc=example,dc=org` and get a branch-not-found error. Likewise, do not both append the suffix to the LDAP URL and set the same suffix again in `spring.ldap.base`.

## 2. Which connections does a single login use?

With the **search-then-bind** strategy, the typical flow consists of:

1. The application establishes a secure LDAP connection and uses the lookup account's bind DN + password to perform a search operation.
2. The application searches for a user entry within `base DN + user search base` matching the filter, e.g., `(uid=linh)`. The result must identify exactly one intended identity.
3. The application retrieves the full DN of the matched entry.
4. Spring Security attempts to **bind using the user's own DN and the password they just entered**. The LDAP server verifies the password; the application does not need to read any password attribute from the directory.
5. If the bind succeeds, Spring Security creates the authentication object. Searching for groups/permissions (if needed) is an additional configuration step, separate from finding the user DN.

~~~text
User -- username/password --> Application
Application -- bind service account --> LDAP
Application -- search username ------> LDAP
LDAP      -- user DN -------------> Application
Application -- bind user DN/password -> LDAP
LDAP      -- success/failure -----> Application
~~~

The two secrets serve different roles: the **service account password** allows the application to perform lookups; the **user password** proves the identity of the person logging in. Do not use a lookup account with domain administrator privileges just to read users.

An alternative is `userDnPatterns("uid={0},ou=people")`: when the DN location is predictable from the username, Spring Security can attempt a direct bind without searching for the DN first. This option is hard to apply if users live in multiple OUs, DNs change, or usernames do not determine the DN. For such systems, search-then-bind is more flexible.

## 3. Preparing the server and search account

Before writing Spring configuration, gather the following details from the directory administration team:

| Information | What to confirm |
| --- | --- |
| Host / port | FQDN of the LDAP server or domain controller, TLS port, DNS configuration, and network connectivity |
| TLS | Valid server certificate, internal CA if any, hostname matching the certificate |
| Base DN | Actual naming context, e.g. `dc=example,dc=org` |
| User locations | OUs containing users; whether any users exist outside the expected branch |
| Login attribute | `uid`, `sAMAccountName`, or `userPrincipalName`; whether values are unique within the search scope |
| Lookup account | DN/UPN accepted by the server, password, least-privilege read permissions, and rotation policy |
| Directory policy | Whether anonymous search is permitted, result size limits, referrals, account lockout, and LDAP signing/TLS policies |

**Least privilege for the service account:** the account only needs to bind and read the attributes used for user search/mapping (and groups if required by the use case). It does not need permissions to create, modify, or delete users, nor Domain Admin privileges. Never store passwords in source code, commits, public config files, or application logs. Pass them via environment variables or a secret manager, with rotation/revocation and incident monitoring mechanisms in place.

**Secure connections:**

- `ldap://host:389` does not encrypt traffic by itself; use it only with StartTLS enabled and properly verified. Depending on the environment, non-TLS LDAP connections may be rejected.
- `ldaps://host:636` establishes TLS from the outset; suitable for simple connection examples.
- The JVM running the application must trust the issuing CA (appropriate truststore), verify the hostname, and never disable certificate checks just "to make it work". The `ldapsearch` tool may use a different CA store than the JVM.
- Configure connection/read timeouts, failover, and error monitoring; do not open unbounded connections or repeatedly retry wrong passwords to the point of locking out accounts.

### Independent check before running Spring

Example using the OpenLDAP tools on a host with directory access. `-W` prompts for the password interactively, avoiding putting the password in shell history:

~~~bash
ldapwhoami -x \
  -H ldaps://directory.example.org:636 \
  -D "cn=svc-ldap-reader,ou=service,dc=example,dc=org" \
  -W
~~~

If the lookup account bind succeeds, test finding the target user within the chosen scope:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -D "cn=svc-ldap-reader,ou=service,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s sub "(uid=linh)" dn uid cn
~~~

Here `-b` takes the **full base DN for the search command**; unlike `setUserSearchBase("ou=people")` which is relative to `spring.ldap.base`. The expected result is a single entry for the right user and a valid `dn` attribute; actual output depends on the directory, so there is no fixed stdout. If 0 results are returned, verify the attribute name, username value, OU, and read permissions before adjusting the application.

If the server uses StartTLS on port 389, a corresponding check is `-H ldap://directory.example.org:389 -ZZ` (mode requiring TLS upgrade to succeed). Do not replace `ldaps://` with `ldap://` and assume traffic is still encrypted.

## 4. Spring Boot and Spring Security example: search user before bind

Below is a configuration for a **Spring Boot 3.x servlet application with existing build/Java 17+ setup**. It uses the lookup account to find the DN and then binds with the login password. The snippets below are the parts to add to a Spring Boot project, not a complete self-contained `build.gradle`.

### 4.1. Dependencies

In `build.gradle` (Groovy DSL) of a web application that already has the Spring Boot plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
}
~~~

`spring-boot-starter-data-ldap` brings in Spring LDAP and the ability to create `LdapContextSource` from `spring.ldap.*` properties; `spring-security-ldap` provides Spring Security's LDAP authentication strategy. Manage versions through the Spring Boot project's dependency management and avoid mixing incompatible versions.

### 4.2. Connection properties

In `src/main/resources/application.properties`:

~~~properties
spring.ldap.urls=ldaps://directory.example.org:636
spring.ldap.base=dc=example,dc=org
spring.ldap.username=${LDAP_BIND_DN}
spring.ldap.password=${LDAP_BIND_PASSWORD}
~~~

In the runtime environment, set `LDAP_BIND_DN` to the full DN of the service account, e.g. `cn=svc-ldap-reader,ou=service,dc=example,dc=org`; supply `LDAP_BIND_PASSWORD` via a secret manager/environment variable. `spring.ldap.username` and `spring.ldap.password` here are **connection credentials for lookups**, not the login credentials of every user.

With this auto-configuration, the application receives an `LdapContextSource` that `BaseLdapPathContextSource` can reference. Specifying `spring.ldap.base` means searches take a relative base; do not repeat the suffix in `userSearchBase`.

### 4.3. Java configuration

File `src/main/java/example/ldap/DirectoryDemoApplication.java` (one public class, supporting classes in the same file/package):

~~~java
package example.ldap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DirectoryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DirectorySecurityConfiguration {
    @Bean
    AuthenticationManager authenticationManager(
            BaseLdapPathContextSource contextSource) {
        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager authenticationManager)
            throws Exception {
        http.authenticationManager(authenticationManager);
        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}

@RestController
class WhoAmIController {
    @GetMapping("/whoami")
    String whoami(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Explanation of key lines:

- `BaseLdapPathContextSource` represents the connection source, holding the URL, base DN, and service account credentials configured by Spring Boot.
- `LdapBindAuthenticationManagerFactory` creates an `AuthenticationManager` using LDAP bind. It **does not** authenticate users by reading LDAP passwords into a `UserDetailsService`.
- `setUserSearchBase("ou=people")` searches inside `ou=people,dc=example,dc=org`.
- `setUserSearchFilter("(uid={0})")` matches login by `uid`; `{0}` is a parameter substituted/escaped appropriately by Spring Security. Do not concatenate raw user input strings directly into LDAP filter expressions.
- `http.authenticationManager(...)` attaches the LDAP authentication manager to the HTTP Security Filter Chain. `httpBasic()` is only used as an easily observable way to test login; in production systems choose appropriate authentication and HTTP protection mechanisms.
- The `/whoami` endpoint returns the principal name after authentication; it does not expose passwords or sensitive directory details.

Run the application after configuring valid credentials, network connectivity, and truststore:

~~~bash
./gradlew bootRun
curl -i -u linh http://localhost:8080/whoami
~~~

On Windows you can use `gradlew.bat bootRun`. `curl -u linh` will prompt for a password. When the DN is found and the user's password is correct, the request receives HTTP 200 and the authenticated identity; when missing or wrong password, it normally receives HTTP 401. This is a test example and does not assert a fixed stdout without an actual LDAP server.

**If the DN is known in advance:** replace the two `setUserSearch...` calls with `factory.setUserDnPatterns("uid={0},ou=people")` *when you are certain every user has a DN following that pattern*. The pattern is also relative to the base DN. In this case, a service account might not be needed to find users; directory policies and group attribute reads still determine whether another read credential is needed.

## 5. Applying to Active Directory

AD speaks LDAP, but naming and login conventions often differ from OpenLDAP. For example, domain `corp.example.com` has naming context `DC=corp,DC=example,DC=com`. Users may reside in multiple OUs:

~~~text
CN=Linh Nguyen,OU=Engineering,DC=corp,DC=example,DC=com
CN=Nam Tran,OU=Operations,DC=corp,DC=example,DC=com
~~~

Username `linh` may be stored in `sAMAccountName`, while the UPN may be `linh@corp.example.com`. Do not guess the DN from the username when an organization has multiple OUs, because the DN also depends on tree location and display name.

With the search-then-bind strategy presented above:

- Change `spring.ldap.base` to `dc=corp,dc=example,dc=com` according to the naming context confirmed by the administrator.
- If users are scattered across the domain, use `factory.setUserSearchBase("")` to search from the domain base; if only a single branch is needed, narrow it to the appropriate OU.
- Change the filter to `factory.setUserSearchFilter("(sAMAccountName={0})")` when login uses the short name, or `(userPrincipalName={0})` when the application accepts the full UPN. Verify uniqueness and actual login policies.
- The service account may be accepted by AD as a UPN such as `svc-ldap@corp.example.com` or as a DN; verify with AD rather than assuming every server uses the same syntax.
- AD has `RootDSE` with the `defaultNamingContext` attribute to determine the base of the current domain. Do not treat `RootDSE` as an OU containing users.

Spring Security also has `ActiveDirectoryLdapAuthenticationProvider` tailored for AD logins with `username@domain`. This is a separate authentication option: inspect how the provider performs bind/search and configure domain and search filter before replacing the `LdapBindAuthenticationManagerFactory` flow in the example. Do not arbitrarily combine two providers with the same credentials without clearly defining the mechanism.

## 6. Common errors and isolation

| Symptom | Common cause | Check step |
| --- | --- | --- |
| Cannot open connection / timeout | DNS, firewall, port, server unavailable | Verify FQDN, port, network connectivity, timeouts; try `ldapwhoami` from the same runtime environment |
| TLS/certificate error | CA not trusted by JVM, expired certificate, or wrong hostname | Inspect certificate chain, JVM truststore, FQDN; do not disable TLS verification |
| Service bind rejected | Wrong DN/UPN, expired password, locked account, TLS policy | Test service account bind independently, check server policy, rotate secrets properly |
| Connected but user not found | Wrong base DN, OU, filter, or login attribute | Run `ldapsearch -b` with full DN; check results within the exact scope |
| User found but login returns 401 | Wrong user password, user bind blocked, account state | Separate the search step from the user bind step; do not leak details to the client |
| Search reports insufficient permissions | Service account lacks permission to read required OU/attributes | Check read ACLs, add least-privilege read access for the exact scope |
| Multiple results returned | Overly broad filter, duplicate login names within scope | Narrow search base/filter; require a unique identifying criterion |
| User logs in but has no roles | Group query/mapping not configured, or service account cannot read groups | Check `groupSearchBase`, group filter, and authority mapping in the dedicated authorization lesson |

An effective debugging method is to separate three questions: **(1) Do connection and service bind succeed? (2) Does the search return exactly one DN? (3) Does binding with the user DN succeed?** When the three steps are verified independently, configuration errors are much easier to pinpoint than just looking at HTTP 401.

Do not log passwords, Authorization headers, or all directory attributes. For AD errors containing subcodes in LDAP messages, use diagnostic details only in controlled internal logs; do not distinguish between "account exists" and "wrong password" in public responses to avoid information disclosure.

## 7. Configuration completion checklist

- [ ] `LDAP_URL` points to the right server; TLS is verified and the JVM truststore works.
- [ ] `base DN` matches the actual naming context, with no duplicated suffix.
- [ ] `userSearchBase` is **relative** to the base DN and covers the right users.
- [ ] `userSearchFilter` uses the right login attribute; input is parameterized, not string-concatenated.
- [ ] Service account binds successfully, has only necessary read permissions, and secrets are not in source code.
- [ ] Search for a valid user returns the right DN; user bind with a correct password succeeds and with a wrong password fails.
- [ ] Tested wrong OU, non-existent user, locked account, expired secret, and connection error cases.
- [ ] If authorization is required, groups/authorities are configured and tested **separately** from the user lookup flow.

### Self-check

1. If `spring.ldap.base=dc=example,dc=org` and `userSearchBase=ou=people`, at which DN does the search actually start?
2. Why does the service account DN need to be full, while the search base in the factory is usually a relative DN?
3. When accounts reside in multiple OUs, why can `userDnPatterns` fail even with a valid username/password?
4. When `ldapwhoami` with the service account succeeds but `ldapsearch` finds no user, which parameters should be checked first?
5. Why can't the service account password replace the bind step using the user's password?

**Suggested answers:** (1) `ou=people,dc=example,dc=org`; (2) the bind account is the full principal of the connection, whereas the search base is appended relatively to the context base; (3) the DN cannot be inferred from the username if the OU location varies; (4) base/search base, filter, login attribute, read ACLs; (5) the service account only authenticates lookup permissions, not the end user's identity.

## References

- [Spring Security: LDAP Authentication (6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Boot: Connecting to an LDAP Server](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)
- [Spring LDAP: ContextSource Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Microsoft Learn: RootDSE and defaultNamingContext](https://learn.microsoft.com/en-us/windows/win32/adsi/rootdse)
- [RFC 4514: LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4515: LDAP Search Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515)
