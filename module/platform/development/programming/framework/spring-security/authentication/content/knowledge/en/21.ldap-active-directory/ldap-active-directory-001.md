# LDAP, directories, and Active Directory in an enterprise identity model

## 1. Why does an organization need a directory?

An organization has thousands of employees, multiple departments, and many applications (intranet, VPN, HR management, business systems). If each application stores accounts, passwords, and department lists separately, creating accounts, transferring departments, locking accounts, or revoking access can easily fall out of sync. A **directory** is a shared identity data store that enables centralized management of information about users, computers, groups, and the relationships between them.

In this context, three concepts must be distinguished:

| Concept | Nature | Example / role |
|---|---|---|
| **Directory (directory service)** | A system that stores identity entries according to a structure and schema, optimized for search/lookup and centralized management. | Users, groups, organizations, devices, attributes. |
| **LDAP (Lightweight Directory Access Protocol)** | A protocol for clients to access, search, authenticate via bind, and (when permitted) modify directory data. | An application sends LDAP search/bind requests to a directory server. |
| **Active Directory Domain Services (AD DS)** | Microsoft's enterprise directory service; provides domains, domain controllers, groups, policies, trusts, and multiple authentication mechanisms. | Domain `corp.example`, domain controller servers; supports LDAP, Kerberos, etc. |

**A directory is not synonymous with LDAP; LDAP is not synonymous with Active Directory.** OpenLDAP is an LDAP server implementation; AD DS is a broader directory service that supports LDAP as an interface. LDAP is a protocol, not a complete identity management system or single sign-on mechanism.

A common architecture:

```text
User ── username + password ──> Application
                                            |
                                    Spring Security
                                            |
                              LDAP client / provider
                                            |
                               LDAPS (TLS channel)
                                            |
                              Directory server / AD DS
                                  |           |
                              User entry   Group entry
                                            |
                           Authentication + application authority mapping
```

The application remains responsible for **business authorization**. The directory confirming that a password is correct is not enough on its own to allow reading payroll data, approving orders, or accessing administrative APIs.

## 2. Directory data model: entry, DN, attribute, and schema

A directory organizes data into **entries** in a *Directory Information Tree* (DIT). Each entry has a **Distinguished Name (DN)** that uniquely identifies its position in the tree, one or more **objectClasses**, along with **attributes** and their values.

An illustrative example of a typical LDAP tree:

```text
dc=corp,dc=example                    ← base DN
├── ou=People
│   ├── uid=lan                        ← a user entry
│   └── uid=minh
├── ou=Groups
│   ├── cn=developers                  ← a group entry
│   └── cn=auditors
└── ou=Services
    └── cn=ldap-reader                 ← service account
```

Several terms must be read accurately:

- **DN:** the full path, for example `uid=lan,ou=People,dc=corp,dc=example`.
- **RDN (Relative Distinguished Name):** the component of a DN at a single level; in the user example, `uid=lan`. Do not treat a standalone RDN as a globally unique identifier across the entire directory.
- **Base DN:** the root node a client uses as the starting point for searches; for example `dc=corp,dc=example`.
- **Attribute:** an attribute name such as `uid`, `cn`, `sn`, `mail`, `member`, `userPrincipalName`. An attribute may be multi-valued, depending on the schema.
- **objectClass/schema:** defines the entry type, required/allowed attributes, and constraints. You cannot assume every server has the same schema.
- **OU (Organizational Unit):** an organizational node used to arrange or administer objects. An OU is not automatically a security role.
- **Group:** describes a collection of members; when integrating an application, it can be used as data to map to an authority/role.

Example data in LDIF format for an OpenLDAP-style schema:

```ldif
dn: uid=lan,ou=People,dc=corp,dc=example
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@corp.example

dn: cn=developers,ou=Groups,dc=corp,dc=example
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=People,dc=corp,dc=example
```

This is **illustrative data**, not ready-made commands for every server. AD DS uses a different schema and naming conventions: a user typically has a DN such as `CN=Lan Nguyen,OU=Engineering,DC=corp,DC=example`, logs in with `lan@corp.example` (UPN) or `CORP\lan` (domain + sAMAccountName); the DN is not necessarily the same as the login username. In AD, the `objectGUID` attribute is usually better suited as a stable object identifier key than the DN when an object may be renamed or moved between OUs. In another directory, choose the corresponding stable key based on its actual schema and lifecycle.

**Common pitfall:** moving Lan from `OU=Engineering` to `OU=Finance` may change the DN, but it does not mean Lan is a different account. If an application uses the DN as an immutable user key, this move can cause duplicate profiles or broken data links.

## 3. How does LDAP work?

Common operations:

| Operation | Meaning |
|---|---|
| **Bind** | Establishes the identity for a connection session with the directory; simple bind can use a DN/identifier and password; SASL mechanisms are also available depending on the server. |
| **Search** | Finds entries by base DN, scope, filter, and list of attributes to retrieve. |
| **Compare** | Requests the server to compare an attribute value according to LDAP rules. |
| **Add/Modify/Delete/Modify DN** | Modifies the directory if the account has permission. An application that only needs authentication should normally not be granted write permissions. |
| **Unbind** | Ends the LDAP session. |

Search has three commonly used **scopes**: `base` (only the entry at the base DN), `one-level` (direct child entries), and `subtree` (the entire subtree). Filters have their own syntax, for example:

```ldap
(uid=lan)
(&(objectClass=inetOrgPerson)(uid=lan))
(|(uid=lan)(uid=minh))
```

The second line means searching for an entry that has both the matching object class and `uid=lan`; the third line is an OR operator. This is an **LDAP filter**, not SQL syntax. Search results also depend on the search base, scope, ACLs, schema, and indexes; a valid filter can still return 0 or multiple records.

### Common authentication flow: search then user bind

1. The user enters a username/password into the application over HTTPS.
2. The application uses a service account **with only the necessary read permissions** (or a search mechanism allowed by the server) to locate the user DN with a safe filter.
3. If **exactly one** user entry is found, the LDAP authentication provider attempts to **bind as that user's identity** with the submitted password over TLS.
4. The directory verifies the bind credentials and returns success/failure; the application does not need to retrieve plaintext passwords or password hashes from the directory.
5. After authentication, the application reads the required group/attribute information, converts it into authorities according to internal policy, and then enforces authorization for endpoints and data.

If the DN structure is stable, you can bind directly using a DN pattern; if accounts reside in multiple OUs or DNs change, **searching before binding** is usually more flexible. Do not infer a DN solely from a display name or email address.

This flow clearly separates:

- **Authentication:** "Can Lan prove her identity?" (LDAP bind succeeds).
- **Directory lookup:** "Which unit does Lan belong to, and what groups is she in?" (LDAP search and reading attributes).
- **Authorization:** "Is Lan allowed to approve this transaction?" (application rules, which may use group information).

A valid user bind can still receive HTTP **403 Forbidden** if the required authority is missing. Conversely, a role must never be granted just because a client sends a group name in the request.

## 4. What does Active Directory add to this model?

**AD DS** organizes identities around domains and forests:

- **Domain:** the administrative boundary for accounts, computers, and domain controllers; the namespace is typically tied to a DNS name.
- **Domain controller (DC):** a server running AD DS that serves directory authentication/query requests. Changes are replicated between DCs via replication; reading from different DCs may experience convergence lag.
- **Forest and trust:** multiple domains can form a forest; trust relationships determine cross-domain identity recognition, but do not automatically grant every application cross-domain permissions.
- **Global Catalog (GC):** a service that supports searching objects across a forest with a specific subset of attributes; it does not by default contain every attribute from every domain.
- **Group and Group Policy:** groups participate in permission management; Group Policy controls many settings for Windows accounts/computers. An LDAP client only sees the queried data and does not automatically "apply Group Policy" to a Java application.

AD attributes you should know:

| Attribute / concept | Usage and notes |
|---|---|
| `sAMAccountName` | Legacy-style login name, typically used within a single domain; not guaranteed to be unique across all domains. |
| `userPrincipalName` (UPN) | Login identifier in the form `user@suffix`; the actual suffix may differ from the domain's DNS name. |
| `distinguishedName` | Current address of the object in the tree; can change upon rename/move. |
| `objectGUID` | AD object identifier that usually remains stable across renames/moves during the object's lifecycle; suitable for identity linking when using AD DS. |
| `objectSid` | Windows security identifier, meaningful for security principals and ACLs; does not replace every business key. |
| `member` / `memberOf` | Represent group relationships in opposite directions; do not assume `memberOf` always lists all nested groups or the primary group. |

**An LDAP bind to AD DS is not synonymous with Kerberos/SSO login.** AD DS can authenticate via LDAP and also provides Kerberos within a domain environment. Web applications needing an SSO experience, tokens, and MFA/Conditional Access policies typically integrate with an identity provider via **OpenID Connect/SAML**, depending on the architecture. **Microsoft Entra ID** is a cloud identity service distinct from AD DS; it can integrate/synchronize with AD DS, but must not be treated as a standard AD DS LDAP endpoint.

### Direct groups and nested groups

Suppose:

```text
Lan  ──member of──>  dev-team  ──member of──>  app-editors
The application requires the APP_EDIT authority to modify data.
```

Reading only Lan's direct `memberOf` may show `dev-team` while missing `app-editors`. When policy permits nested groups, **transitive membership** must be resolved using a mechanism supported by AD, or custom logic with controlled depth/performance. A specialized AD filter for DN relationships is:

```ldap
(member:1.2.840.113556.1.4.1941:=CN=Lan Nguyen,OU=Engineering,DC=corp,DC=example)
```

This is an example of finding groups of which Lan is a direct/indirect member when querying the appropriate search base/group scope. OID `1.2.840.113556.1.4.1941` is an AD matching rule; **do not copy it verbatim to every LDAP server**. With deeply nested groups, searches can be resource-intensive; you must bound the scope and test with realistic data. Ultimately, the application maps approved AD groups to application authorities rather than granting equivalent permissions to every AD group by default.

## 5. Integrating with Spring Security: choosing the right responsibilities

In a **Spring Security 6.x (Servlet/Spring Boot 3.x)** application using username/password and LDAP bind, the main components include:

- **ContextSource:** directory connection parameters and base DN, similar to a connection source.
- **LdapBindAuthenticationManagerFactory / LdapAuthenticator:** locates the user DN and performs the bind with the user's credentials.
- **LdapAuthoritiesPopulator:** reads groups/attributes and turns them into authorities when appropriately configured.
- **SecurityFilterChain:** defines paths requiring authentication, login mechanisms, and access rules.

Gradle (example of a Spring Boot project with managed versions):

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-ldap")
}
```

The following Java configuration example is an **integration snippet inside a Spring Boot application with the dependencies above**, not a standalone `java` program. The URL, base DN, search base, and attribute names **must match the actual directory**; this example models a `uid`/`ou=People` schema and does not yet configure group-to-role mapping.

```java
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
public class LdapAuthenticationConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource() {
        // LDAP_URL = ldaps://ldap.corp.example:636/dc=corp,dc=example
        var source = new DefaultSpringSecurityContextSource(
                System.getenv("LDAP_URL"));
        source.setUserDn(System.getenv("LDAP_READER_DN"));
        source.setPassword(System.getenv("LDAP_READER_PASSWORD"));
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource ldapContextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(ldapContextSource);
        factory.setUserSearchBase("ou=People");
        factory.setUserSearchFilter("(uid={0})");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager) throws Exception {
        http.authenticationManager(ldapAuthenticationManager);
        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Point-by-point explanation:

1. `LDAP_URL` contains the LDAPS URL **and the base DN**, as shown in the comment. `LDAP_READER_DN` and `LDAP_READER_PASSWORD` are the read-only account credentials used to look up the DN; they must be securely configured and verified at startup. In production, retrieve the actual password from a secret manager or an appropriate secret configuration mechanism, never hard-coded in source.
2. `setUserSearchBase("ou=People")` searches under `ou=People,dc=corp,dc=example`. If users span multiple OUs, adjust the base to match the tree and scope; `(uid={0})` is a filter pattern whose parameters are handled by the framework.
3. After locating the DN, the bind authenticator uses the user's password to authenticate against the server. This is **bind authentication**; Spring Security does not read password hashes to compare via `UserDetailsService`.
4. The filter chain requires authentication for every request and provides form login. In an API application or one with SSO, choose an appropriate login/session/token mechanism instead.
5. The example **does not yet assign roles from groups**: if an endpoint requires `hasRole("ADMIN")`, you must configure group queries, map groups to `GrantedAuthority`, and verify policy; a successful login does not automatically create `ROLE_ADMIN`.

For AD DS, you can search using AD attributes (for example `sAMAccountName` or `userPrincipalName`) or the dedicated `ActiveDirectoryLdapAuthenticationProvider` when it fits AD conventions. **Do not copy the `(uid={0})` filter to AD and assume it works**: verify the UPN suffix, domain, account location, group schema, and query permissions on the actual system.

This configuration requires a dedicated test directory/AD and trusted TLS certificates for end-to-end testing. Do not use unencrypted `ldap://` just because it is easy to test and then carry it straight into production.

## 6. LDAP filter injection and safe parameterization

LDAP filters have control characters such as `*`, `(`, `)`, `\`, and NUL. If input is concatenated directly into a filter, such as `"(uid=" + username + ")"`, a malicious string can alter the query semantics or cause errors. In integration code, prefer APIs/frameworks with **parameter binding and escaping for LDAP filters**, while also validating input values, length, and result uniqueness. Escaping a **filter** differs from escaping a **DN**; do not use them interchangeably.

The following standalone Java 17+ example only demonstrates how to escape special characters in an **LDAP filter value**; it does not perform LDAP authentication and does not replace proven library APIs:

```java
public class LdapFilterEscapeDemo {
    static String escapeFilter(String value) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '\\' -> result.append("\\5c");
                case '*'  -> result.append("\\2a");
                case '('  -> result.append("\\28");
                case ')'  -> result.append("\\29");
                case '\u0000' -> result.append("\\00");
                default -> result.append(ch);
            }
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String username = "lan*)(uid=*)";
        System.out.println("(uid=" + escapeFilter(username) + ")");
    }
}
```

Save the file `LdapFilterEscapeDemo.java` and run:

```bash
javac LdapFilterEscapeDemo.java
java LdapFilterEscapeDemo
```

Exact stdout output:

```text
(uid=lan\2a\29\28uid=\2a\29)
```

The `*` character in the input has become the literal sequence `\2a` and is no longer a filter wildcard. In a real system, use the framework's LDAP encoder, restrict filters/search bases, and never place request-supplied values in structural positions (attribute names, operators, root DNs) arbitrarily.

## 7. Security and operations when LDAP is the enterprise identity source

**Transport channel and server identity**

- Use **LDAPS** (commonly TCP port **636**) or **StartTLS** to upgrade an LDAP connection (commonly port **389**) before exchanging sensitive data; always validate the certificate chain and hostname. Avoid simple bind sending passwords over an unencrypted connection.
- AD Global Catalog ports are typically **3268** (LDAP) and **3269** (TLS). GC serves a distinct purpose and attribute subset; do not treat it as always identical to the DC's LDAP endpoint on ports 389/636.
- Configure connection/query timeouts, limit search scope, use paging for large queries, handle referrals as needed, and configure appropriate DC selection/failover. Do not allow unlimited login retries.
- Do not disable certificate verification, do not log passwords, bind credentials, or tokens, and do not send LDAP traffic over the public Internet merely because the endpoint is reachable.

**Identity, permissions, and lifecycle**

- The service account used for search only needs the read permissions genuinely required; normal application accounts must not be granted permission to modify the directory.
- Design a stable user identifier key (AD `objectGUID` is one example), along with policies for handling renamed users, OU moves, offboarding, account lockouts, and group changes.
- Verify **nested groups**, group scope, domain trusts, and attribute read permissions before mapping roles. Establish clear policies for renamed or deleted groups, or when DC data has not yet converged.
- Treat LDAP as one component of the authentication system: rate limiting, login monitoring, session management, and MFA/SSO (if required) must be implemented through appropriate architecture and do not emerge automatically from an LDAP bind operation.
- Do not disclose details such as "user exists but is locked" to external callers in login responses. Record controlled internal error codes so operations teams can distinguish root causes.

**Systematic troubleshooting**

| Symptom | Where to check first |
|---|---|
| User not found | Search base/scope/filter, attribute name (`uid` vs `sAMAccountName`), read permissions, multiple OUs/domains. |
| LDAP bind failed | Password, account status/server policy, DN/UPN, connecting to the right domain; do not expose details to the user. |
| TLS/SSL handshake error | CA/truststore, hostname, certificate expiration and EKU, DC configuration, DNS/port. |
| Login succeeds but HTTP 403 | Authorization rules, LDAP group-to-Spring authority mapping, `ROLE_` prefix, nested groups, and domain scope. |
| Groups/attributes differ between reads | Which DC/GC is queried, replication, referrals, caching, visibility/ACL, and update lag. |
| Slow with many users/groups | Overly broad filter, indexing, paging, recursive group search, timeouts, per-step latency measurement. |

## 8. Applied scenario: internal request management application

Suppose an organization uses AD DS. Lan has the login `lan@corp.example` and is a member of `dev-team`; `dev-team` belongs to `app-editors`. The application requires the `APP_EDIT` authority to approve requests.

1. Lan enters her credentials into the application UI; Spring Security authenticates via the chosen mechanism. If LDAP bind is used, LDAP/DC verifies the account credentials.
2. The application retrieves Lan's stable identifier and groups according to the designed query rules. If it only reads direct `memberOf`, it may miss `app-editors`.
3. Policy maps "members (including allowed nested memberships) of `app-editors`" to `APP_EDIT`. Only when that authority is present is the action permitted; if missing, deny even though login succeeded.
4. When Lan transfers departments, her group membership is updated in AD. The application must have a policy to refresh group caches/sessions so permission revocation takes effect on time; avoid retaining stale permissions indefinitely.

Good design separates the **identity source (directory)**, **proof of identity (LDAP bind/Kerberos/OIDC depending on flow)**, and **authorization decision (application rules)**. That way, OU changes, UPN logins, or adding SSO will not lead to ad-hoc permission assignment.

## 9. Self-check after this lesson

1. Can LDAP be used with a directory other than Microsoft AD? **Yes.** LDAP is a protocol; AD DS and OpenLDAP are systems that can provide an LDAP interface.
2. Does a successful user bind guarantee access to admin APIs? **No.** Authentication differs from authorization; application roles/authorities and policies are required.
3. Are `DN` and `sAMAccountName` equivalent? **No.** A DN indicates the current position in the tree; `sAMAccountName` is an account name attribute in AD conventions.
4. Why might direct `memberOf` miss permissions? **Because of nested groups and specific membership rules**, so group resolution must be defined according to policy.
5. Can MFA be enabled by switching `ldap://` to `ldaps://`? **No.** LDAPS encrypts the transport channel; MFA requires an authentication/IdP solution and integration flow that supports MFA.

## References

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind authentication, ContextSource, search filters, and authority mapping.
- [Microsoft Learn — LDAP Search Filter Syntax](https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax): filter syntax and matching rules for AD, including nested membership rules.
- [Microsoft Learn — Configure certificates for LDAP over SSL in AD DS](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/configure-ldap-signing-certificates): certificates and LDAPS verification.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): specification of LDAP protocol operations.
