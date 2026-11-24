# User search, group search, and LDAP authority mapping

In an application integrated with LDAP or Active Directory (AD), a successful login only answers **who the user is**. The application must also locate the right user object in the directory tree, determine which groups that object belongs to, and convert the appropriate information into **GrantedAuthority** entries so Spring Security can enforce access control. These three stages are related, yet have distinct configurations, errors, and risks.

This lesson focuses on **user search, group search, and LDAP authority mapping**. It demonstrates the workflow using Spring Security LDAP for a Servlet application while highlighting the key differences to watch for when the directory source is Microsoft Active Directory.

## 1. Data model to understand before searching

LDAP stores data in a **Directory Information Tree (DIT)**. Each entry has a **Distinguished Name (DN)**, a set of attributes, and objectClasses indicating which schema the entry conforms to.

Example organizational directory tree:

~~~text
dc=example,dc=org                         (base DN)
├── ou=people
│   ├── uid=lan                            (user entry)
│   └── uid=minh                           (user entry)
├── ou=groups
│   ├── cn=app-viewers                      (group entry)
│   └── cn=app-admins                       (group entry)
└── ou=service
    └── cn=ldap-reader                     (service account)
~~~

Lan's full DN is **uid=lan,ou=people,dc=example,dc=org**. The **uid=lan** part is the Relative Distinguished Name (RDN); **uid**, **cn**, **ou**, and **dc** are attribute names with distinct roles.

| Component | Common meaning | What to distinguish |
| --- | --- | --- |
| DN | Uniquely identifies an entry's position in the directory tree at query time | Not synonymous with the username entered by the user |
| uid | Login name in many OpenLDAP systems | Not every AD uses uid |
| cn | Common Name of a person or group | May change; not guaranteed to be a stable application ID |
| ou | Organizational Unit, commonly used as a branch containing entries | User and group branches may differ |
| member | List of member DNs, common in groupOfNames and AD groups | Group attribute pointing to members |
| uniqueMember | List of member DNs, common in groupOfUniqueNames | Requires a different filter from member |
| memberOf | Reverse link showing a user's direct groups, when provided by server/schema | Not a mandatory attribute on every LDAP server |
| sAMAccountName / userPrincipalName | Common login attributes in AD | May differ from each other and from the DN |

Example group data (LDIF illustrating two entries, assuming parent branches and users already exist):

~~~ldif
dn: cn=app-viewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app-viewers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org

dn: cn=app-admins,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app-admins
member: uid=lan,ou=people,dc=example,dc=org
~~~

Searching for groups whose **member** attribute matches Lan's DN returns **app-viewers** and **app-admins**. That is group membership data. The application may choose to map those groups into view or administrative permissions, but the LDAP server itself has no knowledge of business permissions on HTTP endpoints.

**Do not confuse DN with username:** a user may enter "lan", while bind and group membership use the full DN. In AD, that user may also log in using a UPN format such as **lan@corp.example.org**.

## 2. Three independent processing steps: user search → authentication → authority retrieval

Typical Spring Security LDAP flow:

~~~text
Username/password from HTTP login
          │
          ▼
SEARCH USER by search base + filter
          │
          ├─ 0 entries / multiple entries / no read permission → error to handle
          ▼
User DN and entry obtained
          │
          ▼
AUTHENTICATE (usually bind with DN + password)
          │
          ├─ bind failed → unauthenticated
          ▼
SEARCH GROUPS under group search base
          │
          ▼
CONVERT GROUPS to GrantedAuthority
          │
          ▼
Authentication holds principal + authorities
          │
          ▼
Authorization: hasRole / hasAuthority / business policy
~~~

- **User search** finds *which entry* corresponds to the login name.
- **Bind authentication** asks the LDAP server to verify that entry's credentials. Finding an entry **does not mean** the password is valid.
- **Group search** discovers group membership relationships. A valid user might not belong to any group permitted by the application.
- **Authority mapping** converts directory data into permission strings meaningful to the application; HTTP/method security policies use these strings to make decisions.

Spring Security provides **LdapAuthenticator** separately for authentication and **LdapAuthoritiesPopulator** for retrieving authorities. This lets you change the group search strategy without altering the authentication mechanism. In the bind approach, passwords are not read from LDAP for local comparison inside the application; the LDAP server verifies the credentials.

## 3. User search: search base, scope, and filter

An LDAP search is defined by three main factors:

1. **Base DN**: which branch to start searching from, e.g. **ou=people,dc=example,dc=org**.
2. **Search scope**: only the root entry (base object), direct children (one-level), or the entire subtree (subtree).
3. **Search filter**: entry selection condition, e.g. **(uid=lan)**.

Some valid LDAP filters:

~~~ldap
(uid=lan)
(&(objectClass=inetOrgPerson)(uid=lan))
(|(uid=lan)(mail=lan@example.org))
(&(objectCategory=person)(objectClass=user)(sAMAccountName=lan))
~~~

The first line searches by uid; the second combines objectClass and uid; the third matches either of two attributes; the last is an AD-oriented example. The **(&(...)(...))** structure means AND, and **(|(...)(...))** means OR. Filters must match the actual schema; a common attribute name is no guarantee that the target server has it.

From Spring Security, there are two ways to locate the DN:

| Approach | Sample setting | When appropriate |
| --- | --- | --- |
| DN pattern | **uid={0},ou=people** | Users reside at a fixed location and DN can be derived from login |
| User search | **userSearchBase=ou=people**, **userSearchFilter=(uid={0})** | Users may be in multiple branches or DN cannot be derived directly from login |

In both approaches, **{0}** represents the username entered by the user in the user-lookup configuration. When using user search, make the condition specific enough to match exactly **one** user: an overly broad filter may match someone else, multiple entries, or accidentally match a service account. If data spans multiple sub-branches, verify the exact scope of the tool/provider in use and avoid searching from the entire root unnecessarily.

Practical example:

~~~text
ContextSource root: dc=example,dc=org
User search base:  ou=people
User search filter: (&(objectClass=inetOrgPerson)(uid={0}))
Login:              lan
Result DN:          uid=lan,ou=people,dc=example,dc=org
~~~

With a DN pattern, configuring **uid={0},ou=people** constructs the path directly without necessarily searching the whole tree; it is unsuitable if a user's OU changes or the username is not the RDN component.

**Avoid LDAP injection:** never build filters with arbitrary string concatenation like **"(uid=" + input + ")"**. Special characters ***, **(**, **)**, backslash, and NUL have syntactic meaning in LDAP filters. Use parameter substitution or Spring LDAP's filter builder/escaping APIs, restrict valid input, and distinguish **escaping filter values** from **escaping DN values**. A hand-built filter containing unescaped input can broaden the matched entries or corrupt the query.

## 4. Group search: direct membership relationships

With the **groupOfNames** schema, each group can have one or more **member** attributes pointing to the DN of a user or another group. To find Lan's groups in the example, query:

~~~ldap
(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))
~~~

A sensible search area is **ou=groups,dc=example,dc=org**. The results return groups whose **member** matches the DN above.

With the **groupOfUniqueNames** schema, use **uniqueMember** instead of **member**:

~~~ldap
(&(objectClass=groupOfUniqueNames)(uniqueMember=uid=lan,ou=people,dc=example,dc=org))
~~~

In Spring Security's **DefaultLdapAuthoritiesPopulator**:

- **groupSearchBase** is the group search path relative to ContextSource's base DN. For example, if ContextSource root is **dc=example,dc=org**, then groupSearchBase is **ou=groups**.
- **groupSearchFilter** is the LDAP filter finding membership. **{0}** is the **user's full DN**; **{1}** can be used for the **username**. Do not use **{1}** for a member attribute storing DNs if the actual data stores DNs.
- **groupRoleAttribute** determines which attribute of the group is read as the authority name. Default is **cn**.
- **rolePrefix** defaults to **ROLE_**; **convertToUpperCase** defaults to **true**.
- **searchSubtree** defaults to **false** (only one level under the base). Set to **true** if groups are organized in nested OUs and the entire subtree must be searched.

Taking groupName from **cn** is only the default behavior. Real systems may use a different attribute or an application-controlled mapping table; renaming a group label in the directory can affect permissions if group names are used directly as roles.

## 5. LDAP results and Spring Security results are not the same type

Suppose user **lan** belongs to:

~~~text
Group 1 DN: cn=app-viewers,ou=groups,dc=example,dc=org
Group 2 DN: cn=app-admins,ou=groups,dc=example,dc=org
cn attribute: app-viewers, app-admins
~~~

If the populator uses **groupRoleAttribute=cn**, **rolePrefix=ROLE_**, **convertToUpperCase=true**, Spring Security produces the expected authorities:

~~~text
ROLE_APP-VIEWERS
ROLE_APP-ADMINS
~~~

Three key points to remember:

1. **GrantedAuthority** is a string permission name. It does not inherently know "view reports" or "manage users" unless the application's policy uses/maps it.
2. **hasRole("APP-ADMINS")** in default configuration looks for authority **ROLE_APP-ADMINS**; **hasAuthority("ROLE_APP-ADMINS")** compares the string directly. Changing rolePrefix or default security expression configuration can alter the outcome.
3. If the organization renames a group, using raw group CN strings in application policy can change behavior. For sensitive permissions, a **controlled allowlist mapping group DN/ID → business authority** is usually clearer than turning every group CN directly into an active permission.

Example mapping by application policy:

| Discovered group | Business permission granted | Meaning |
| --- | --- | --- |
| app-viewers | REPORT_READ | Read reports |
| app-admins | REPORT_ADMIN | Administer reports |
| engineering-general | No special permission granted | HR/org groups do not automatically carry application permissions |
| unknown-group | No permission granted | Do not extend permissions to unapproved groups by default |

If application conventions use roles, the resulting authorities can be **ROLE_REPORT_READ** and **ROLE_REPORT_ADMIN**. Do not assume the **app-admins** group automatically means admin rights over every resource.

## 6. Spring Boot + Spring Security example: user search and group search

The example below is for a **Spring Boot Servlet application with Spring Security LDAP**. It is Java configuration that can be added to an existing Spring Boot application; an LDAP server with matching schema and credentials is required. This is **not a standalone program runnable solely with javac**.

Gradle Kotlin DSL dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.security:spring-security-ldap")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

For a Gradle Groovy DSL project, convert the dependency syntax accordingly. Use Spring Boot's dependency management to keep versions aligned rather than manually mixing Spring LDAP/Security versions.

**application.yml**:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=ldap-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

This configuration works when the environment provides a real LDAP server, a valid reader account, and the **LDAP_BIND_PASSWORD** environment variable. The server needs a TLS certificate trusted by the JVM; do not disable certificate verification to make the connection "work".

File **LdapAuthenticationConfig.java** (placed in a package scanned by Spring Boot):

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

@Configuration(proxyBeanMethods = false)
public class LdapAuthenticationConfig {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        var groups = new DefaultLdapAuthoritiesPopulator(
                contextSource, "ou=groups");

        groups.setGroupSearchFilter(
                "(&(objectClass=groupOfNames)(member={0}))");
        groups.setGroupRoleAttribute("cn");
        groups.setSearchSubtree(true);
        groups.setRolePrefix("ROLE_");
        groups.setConvertToUpperCase(true);

        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter(
                "(&(objectClass=inetOrgPerson)(uid={0}))");
        factory.setLdapAuthoritiesPopulator(groups);

        return factory.createAuthenticationManager();
    }
}
~~~

The configuration above uses standard Spring Security 5.7+ APIs and is compatible with the Spring Security 6.x line when using matching dependencies. It operates in order: locate the user under **ou=people** by **uid**, bind to verify credentials, search groups under **ou=groups** whose **member** equals the user's DN, and convert **cn** into authorities prefixed with **ROLE_**. If the directory uses **uniqueMember**, update the filter accordingly. If groups live directly under **ou=groups**, `searchSubtree(true)` is unnecessary; enable it only when child OUs must be covered.

In a Servlet application, roles can be enforced in HTTP configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(requests -> requests
                    .requestMatchers("/reports/admin/**")
                    .hasAuthority("ROLE_APP-ADMINS")
                    .requestMatchers("/reports/**")
                    .hasAnyAuthority("ROLE_APP-VIEWERS", "ROLE_APP-ADMINS")
                    .anyRequest().authenticated())
            .formLogin(org.springframework.security.config.Customizer.withDefaults())
            .build();
}
~~~

This is a **@Bean method snippet** to add to a configuration class with imports **org.springframework.security.config.annotation.web.builders.HttpSecurity**, **org.springframework.security.web.SecurityFilterChain**, and **org.springframework.context.annotation.Bean**. Ensure the LDAP `AuthenticationManager` is used by the appropriate HTTP authentication mechanism; when an application has multiple `AuthenticationProvider`/`AuthenticationManager` beans, explicitly configure ordering and scope. A user who authenticates successfully but belongs to neither permitted group will not be able to access `/reports/**`.

This example targets **Servlet**; the synchronous **AuthenticationManager** and **SecurityFilterChain** APIs must not be copied verbatim into a **WebFlux** pipeline. If direct LDAP authentication is required in a reactive stack, account for the blocking I/O nature of LDAP/JNDI libraries and design an appropriate adapter/scheduler rather than making blocking LDAP calls on the event loop.

## 7. Mapping groups to business permissions in a controlled way

Sometimes an application does not want raw LDAP group names carried directly into policy. For example, the organization names a group **app-viewers** while the application expects **ROLE_REPORT_READ**. You can configure a **GrantedAuthoritiesMapper** on the factory after the populator fetches groups, or implement a custom **LdapAuthoritiesPopulator** if data must be queried/merged from multiple sources.

A mapper snippet can be attached after setting up the factory (inside the body of the configuration method in section 6):

~~~java
factory.setAuthoritiesMapper(loaded -> {
    java.util.Map<String, String> allowlist = java.util.Map.of(
            "ROLE_APP-VIEWERS", "ROLE_REPORT_READ",
            "ROLE_APP-ADMINS", "ROLE_REPORT_ADMIN");

    return loaded.stream()
            .map(org.springframework.security.core.GrantedAuthority::getAuthority)
            .map(allowlist::get)
            .filter(java.util.Objects::nonNull)
            .distinct()
            .map(org.springframework.security.core.authority.SimpleGrantedAuthority::new)
            .toList();
});
~~~

Place this snippet **before** calling **factory.createAuthenticationManager()**. This is a **contextual snippet**; the project needs the imports from section 6. In the mapping above, if a group is not in the allowlist, **no authority is created** from it. Be careful: a "drop all unknown groups" mapping may leave a user without access to basic features; that is an intentional policy choice that must be tested.

For sensitive permissions, consider mapping from a **stable group DN or ID** rather than a CN that can collide or be renamed. `DefaultLdapAuthoritiesPopulator` using `cn` in the example is a starting point to understand the mechanism. To map by DN, retrieve the group identifier from the data source, normalize it, and validate policy before returning `GrantedAuthority`; do not assume CN is unique across the entire LDAP tree.

### Standalone Java 17 program simulating mapping

The example below simulates only the **mapping step** without calling LDAP or performing authentication. You can save it as **LdapRoleMappingDemo.java** and run it with Java 17+:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class LdapRoleMappingDemo {
    public static void main(String[] args) {
        Map<String, String> allowedGroups = Map.of(
                "app-viewers", "ROLE_REPORT_READ",
                "app-admins", "ROLE_REPORT_ADMIN");

        List<String> ldapGroupCns = List.of(
                "app-viewers", "engineering-general", "app-admins");

        var authorities = ldapGroupCns.stream()
                .map(allowedGroups::get)
                .filter(Objects::nonNull)
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("Authorities: " + authorities);
        System.out.println("Can read: " +
                authorities.contains("ROLE_REPORT_READ"));
        System.out.println("Unknown group granted: " +
                authorities.contains("ROLE_ENGINEERING_GENERAL"));
    }
}
~~~

Commands:

~~~bash
javac LdapRoleMappingDemo.java
java LdapRoleMappingDemo
~~~

Exact stdout:

~~~text
Authorities: [ROLE_REPORT_ADMIN, ROLE_REPORT_READ]
Can read: true
Unknown group granted: false
~~~

Using `TreeSet` makes the printed order deterministic alphabetically. In real systems, permissions are wrapped in **GrantedAuthority** objects and attached to **Authentication** after verification; never use a simulation example to skip credential verification.

## 8. Active Directory: login names and group lists differ from the OpenLDAP sample

AD uses LDAP but has its own conventions. Several common differences:

| Aspect | Sample OpenLDAP in this lesson | Typical Active Directory |
| --- | --- | --- |
| Login name | uid | sAMAccountName or userPrincipalName |
| User DN | uid=lan,ou=people,... | CN=Lan Tran,OU=Users,DC=corp,... |
| Group schema | groupOfNames, member or groupOfUniqueNames, uniqueMember | group with member; user usually has memberOf |
| Auth connection | Bind by DN after user search | Typically logs in with UPN user@domain |
| Convenient provider | LdapBindAuthenticationManagerFactory | ActiveDirectoryLdapAuthenticationProvider |

Spring Security provides **ActiveDirectoryLdapAuthenticationProvider** for standard AD setups. Example configuration bean (runs inside a Spring application using a real ldaps URL):

~~~java
@Bean
ActiveDirectoryLdapAuthenticationProvider activeDirectoryProvider() {
    return new ActiveDirectoryLdapAuthenticationProvider(
            "corp.example.org", "ldaps://ad.corp.example.org:636/");
}
~~~

Import **org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider** and **org.springframework.context.annotation.Bean**. The provider can use UPN or a custom `searchFilter` and by default reads authorities from the user's **memberOf** attribute. This differs from querying groups with **DefaultLdapAuthoritiesPopulator** in the OpenLDAP section: you cannot assume they share the same default search base/filter, group expansion behavior, or role formatting.

When custom mapping is needed, inspect **setAuthoritiesPopulator(...)**, **setAuthoritiesMapper(...)**, and **setSearchFilter(...)** on the provider for the exact version in use. Verify the actual `Authentication.authorities` values in tests before writing policies such as `hasRole` or `hasAuthority`; do not guess from AD group names and assume those exact authority strings exist.

### Two AD query examples

Find an account by `sAMAccountName`:

~~~ldap
(&(objectCategory=person)(objectClass=user)(sAMAccountName=lan))
~~~

Find direct groups containing the user's DN:

~~~ldap
(&(objectCategory=group)(member=CN=Lan Tran,OU=Users,DC=corp,DC=example,DC=org))
~~~

You must use the **exact actual DN** returned by the directory. In AD, the **memberOf** attribute can be helpful for reading direct groups; certain relationships such as the **primary group** are not reflected straightforwardly in `memberOf`. Groups may reside across different OUs, domains, or security scopes; using too narrow a search base can miss memberships.

## 9. Nested groups: direct membership is not enough

Example:

~~~text
User lan
  └── member of "team-backend"
        └── "team-backend" is member of "app-admins"
~~~

Searching groups with **(member={0})** where `{0}`=Lan's DN will see **team-backend**. That query **does not automatically deduce** that Lan is an indirect member of **app-admins**.

Strategies to consider:

1. **Do not support nested groups:** only direct groups grant permissions. Simple and easy to audit; document clearly for the directory administration team.
2. **NestedLdapAuthoritiesPopulator:** Spring Security provides a class that can resolve static nested groups; check group schema, `groupSearchBase`, depth limits, and query cost.
3. **AD matching rule in chain:** on AD where supported, an expanded group-member filter can be **(member:1.2.840.113556.1.4.1941:={0})**, where `{0}` must be substituted with the user DN using the library's escaping mechanism. This is an AD-specific feature, not standard LDAP supported across all servers.
4. **Application group/role policy:** you may allow only specific approved security groups and avoid automatically expanding all nested memberships.

Matching rule in chain traverses DN links and can make queries heavy on large trees. Measure latency, check paging/referral limits, and verify the search account's permissions. Do not enable recursive traversal of all groups just because data has nested OUs: **searchSubtree(true)** only changes the search scope (entry subtree), not automatic graph traversal of member-of relationships.

Likewise, do not assume every AD group is a valid **security group** for granting access. Policy may require filtering by group attributes, trusted domains, or a controlled group list rather than turning every distribution group into access rights.

## 10. Search, bind, and authorization require different accounts and permissions

A production LDAP integration typically involves two types of identities:

- **Application search/bind account:** a service account used to look up DNs/attributes (if the directory disallows anonymous search). Grant least-privilege read access to the required branch; never use domain admin. Credentials must live in a secret manager or environment variables and be rotatable.
- **Logging-in user account:** the LDAP server verifies the password via bind or the configured mechanism. Authentication success does not mean the search account has permission to see all group attributes.

A service account that can locate the user entry but cannot read **member**, **memberOf**, or groups under a particular OU will result in empty/missing authorities depending on design. Distinguish "user entered wrong password" from "valid user has no matching group" and "LDAP cannot query groups"; they are distinct failure classes.

At the network layer, prefer **LDAPS or StartTLS with certificate verification**, reasonable connection/read timeouts, connecting to trusted directories, never logging passwords/tokens, and bounding result counts and read permissions. Never build LDAP filters via input concatenation, never trust group names sent by the client, and never use request parameter values to grant `GrantedAuthority`.

## 11. Testing queries directly to confirm configuration

Use the **ldapsearch** tool on a development machine or test environment with LDAP access. For an OpenLDAP-compatible server, example user search:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "cn=ldap-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(&(objectClass=inetOrgPerson)(uid=lan))" dn uid cn
~~~

The tool will prompt for the password due to the **-W** flag, avoiding putting the password directly into command history. A valid result against the illustrative data may contain:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Lan Tran
~~~

To search groups:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "cn=ldap-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" \
  "(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))" \
  dn cn
~~~

In the illustrative group data, you expect the two group DNs **app-viewers** and **app-admins**. This is a **conditional expected result on the example data**, not stdout observed from a real LDAP server. Without an LDAP server, the commands above will not have real output to compare against.

A helpful verification sequence:

1. Verify connection/TLS and that the service account has search permissions.
2. Run the user query; the result must match a single entry with the expected DN.
3. Use that DN to query groups; inspect `member`/`uniqueMember` and the search scope.
4. Test binding with the user's credentials in a test environment, verifying valid/invalid credentials yield different outcomes.
5. Through Spring Security, verify the authority list on `Authentication` and the endpoint policies.

In production, avoid logging entire user entries because they may contain email addresses, phone numbers, or sensitive attributes; when diagnostic logs are needed, prefer error codes, result counts, policy names, and correlation IDs.

## 12. Common errors and diagnosis

| Symptom | Possible cause | Check and fix |
| --- | --- | --- |
| User exists but is not found | Wrong `userSearchBase`, using `uid` instead of `sAMAccountName`, scope misses branch | Run LDAP search with exact filter/base; inspect actual DN |
| User found but bind fails | Wrong password, account disabled/expired, AD policy, wrong DN/UPN | Separate search and bind steps; inspect error codes safely |
| Login succeeds but authorities are empty | Wrong `groupSearchBase`, `member`/`uniqueMember` mismatch, reader account lacks permission | Test group filter with user DN and check ACLs |
| Only direct groups appear | Nested membership not handled | Use an explicit nested strategy; test two or more levels |
| User has group but gets 403 | `ROLE_` prefix, uppercase, mapping, or `hasRole`/`hasAuthority` mismatch | Compare exact `GrantedAuthority` strings against policy |
| Excessively broad permissions | Every group CN treated as a role, overly broad search base, arbitrary mapping | Use an allowlist or group DN/ID and least privilege |
| Slow queries | Overly broad subtree scope, non-selective filter, deep nested groups, referrals | Narrow base/filter, check indexes, measure latency, bound expansion |
| Permissions do not change immediately after group update | Stale `Authentication`/cached authorities, token/session not reissued | Define when permissions refresh and re-auth/refresh mechanism |
| Duplicate usernames exist | Overly broad search base or non-unique attribute | Use a suitable identifying attribute and check for ambiguity |

**403 and 401 mean different things:** depending on the HTTP mechanism/application policy, 401 generally means the request is unauthenticated while 403 means it is authenticated but lacks sufficient permissions. Never fix a "missing group" issue by opening all endpoints to every logged-in user.

## 13. What must minimal integration tests cover?

A reliable test suite must verify both identity and permissions:

| Case | Expectation |
| --- | --- |
| Valid user in group app-viewers | Logs in and holds viewer group authority |
| Same user, wrong password | Authentication fails |
| Non-existent username | Authentication fails, no authorities produced |
| Valid user not in any app group | Can authenticate but cannot access role-protected endpoints |
| User in group app-admins | Granted exact group permissions; no extra permissions auto-granted |
| User belongs to parent group only via child group | Outcome matches defined nested strategy and is explicitly tested |
| Two users in different groups | Never share or mistakenly reuse authorities |
| Group removed or account locked | Updated permissions/status take effect at designed re-auth/refresh point |
| User login value contains special characters | Does not alter filter outside escaped value; reject/accept per policy |
| Directory slow/disconnected | Fail closed on authenticated endpoints; never grant default permissions |

Use a test LDAP directory (e.g., an embedded directory or isolated test environment) with small, deterministic LDIF data. Each test should inspect the **selected user DN**, **discovered groups**, **actual authorities**, and then **access decisions**; merely asserting HTTP 200 after a successful login will not catch wrong scopes or role mappings.

For AD, use an AD-compatible test environment because **userPrincipalName**, **memberOf**, **groupType**, nested matching rules, and primary-group semantics cannot be fully proven using embedded OpenLDAP alone.

## 14. Practical principles and conclusion

When implementing LDAP user search, group search, and authority mapping, first confirm the **actual schema**, **base DN**, **username attribute**, **membership attribute**, and **expected GrantedAuthority strings**. User search queries the directory, bind verifies credentials, group search reads membership links, and authorization is the application's decision.

A solid workflow is **login → find exactly one user DN → authenticate → search groups per schema → map allowlist to authorities → check permissions on resources**. Test every boundary and never let default configuration turn arbitrary group lists into high privilege.

### Official references

- Spring Security – LDAP Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Spring Security – DefaultLdapAuthoritiesPopulator API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html
- Spring Security – AbstractLdapAuthenticationManagerFactory API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html
- Spring Security – ActiveDirectoryLdapAuthenticationProvider API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring Security – NestedLdapAuthoritiesPopulator API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/NestedLdapAuthoritiesPopulator.html
- Microsoft Learn – LDAP Search Filter Syntax and matching rules: https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax
