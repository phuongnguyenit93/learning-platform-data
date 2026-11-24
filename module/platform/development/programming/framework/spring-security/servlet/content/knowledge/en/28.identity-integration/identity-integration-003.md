# LDAP Group Mapping, UserDetailsContextMapper, and Securing LDAP Connections in Spring Security Servlet

## 1. The Problem: Authenticating via LDAP, Authorizing per Application

A Spring Boot application running on the **Servlet stack** has users managed in LDAP (Lightweight Directory Access Protocol). Employees sign in with their directory username/password. The directory also holds **groups** such as `PORTAL_READERS` and `PORTAL_OPERATORS`, while Spring Security must decide whether a user holds `ROLE_READER` or `ROLE_OPERATOR` inside the application.

These three tasks are related but distinct:

1. **LDAP authentication:** Verify login credentials via LDAP, typically by **binding** with the user's account. If LDAP rejects the credentials, the application does not create an authenticated session.
2. **LDAP authority retrieval:** Look up the groups the user belongs to under a configured schema/group search base. Spring Security can turn group names into initial `GrantedAuthority` values.
3. **Application authorization:** Convert **administratively trusted LDAP groups** into approved application roles, check internal account status/policies, and use `hasRole` or `hasAuthority` to protect URLs.

**`UserDetailsContextMapper`** is the extension point for converting the retrieved LDAP user object + authorities into a **`UserDetails`** (principal) suited to the system. It is neither the mechanism that establishes a TLS connection nor the component that performs all group lookups itself.

On the other hand, even if authentication/role mapping are right, if the application sends passwords or sensitive directory details over an unprotected connection, accounts remain at risk. Hence **LDAPS or StartTLS, certificate verification, and secret management** are an essential part of the problem.

Goal of this guide: understand Spring Security 6's LDAP bind and group lookup flow, write a controlled group-to-role mapper, build a Java 17 demo, use LDAP over TLS, and test success/failure scenarios.

## 2. Directory Structure: DN, OU, User, and Group

LDAP is not a relational SQL table. An entry has a **Distinguished Name (DN)** identifying its location in the directory tree and contains attributes and object classes defined by a schema.

Illustrative directory example:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice,ou=people,dc=example,dc=org
│   └── uid=bob,ou=people,dc=example,dc=org
├── ou=groups
│   ├── cn=PORTAL_READERS,ou=groups,dc=example,dc=org
│   └── cn=PORTAL_OPERATORS,ou=groups,dc=example,dc=org
└── ou=service
    └── cn=app-reader,ou=service,dc=example,dc=org
~~~

Meaning of key terms:

| Term | Meaning | Example |
| --- | --- | --- |
| `DN` | Full identifier of an entry in the LDAP tree | `uid=alice,ou=people,dc=example,dc=org` |
| `RDN` | Relative component at one level of the DN | `uid=alice` |
| `base DN` | Root starting point for relative searches | `dc=example,dc=org` |
| `OU` | Organizational Unit, how entries are organized | `ou=people`, `ou=groups` |
| `uid` | Attribute usable for sign-in depending on schema | `alice` |
| `cn` | Common Name, often a group or entry name | `PORTAL_READERS` |
| `member` / `uniqueMember` | Attribute storing member DNs of a group depending on objectClass/schema | `uid=alice,ou=people,dc=example,dc=org` |
| `memberOf` | Group membership attribute provided by some servers like AD | Does not exist by default on all LDAP servers |
| `objectClass` | Defines an entry's schema/attributes | `inetOrgPerson`, `groupOfUniqueNames` |

A group of type `groupOfUniqueNames` can be described by the following LDIF. This is **illustrative data requiring a real directory to import**, not data auto-created by the Java demo:

~~~ldif
dn: cn=PORTAL_READERS,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: PORTAL_READERS
uniqueMember: uid=alice,ou=people,dc=example,dc=org

dn: cn=PORTAL_OPERATORS,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: PORTAL_OPERATORS
uniqueMember: uid=bob,ou=people,dc=example,dc=org
~~~

With `groupOfNames`, the typical membership attribute is `member`. With **Active Directory**, users and groups typically use different schemas, user lookups, and group membership representations; never assume `uid`, `ou=people`, and `uniqueMember` exist. Always use the exact filter/base/attribute matching the directory you connect to.

A lookup service account (`cn=app-reader,...`) can hold permission to **read groups and necessary attributes**, while user passwords are verified solely by LDAP via bind. Grant least-privilege read access to the service account; never grant directory modification rights to an application that only performs logins.

## 3. LDAP Authentication Flow in Spring Security Servlet

Spring Security LDAP has these typical components:

- **`LdapContextSource`** (Spring LDAP): Configures server URL, base DN, and connection/lookup credentials.
- **`BindAuthenticator`**: Uses the user's DN and password to perform an LDAP bind, asking the LDAP server to authenticate.
- **`DefaultLdapAuthoritiesPopulator`**: Finds LDAP groups matching the user DN/username via a filter, extracts the role attribute, and converts them into a set of `GrantedAuthority`.
- **`UserDetailsContextMapper`**: Receives `DirContextOperations`, username, and authorities; constructs `UserDetails` for the application principal.
- **`LdapAuthenticationProvider`**: Coordinates the authenticator, authorities populator, and context mapper.
- **`SecurityFilterChain`**: Uses the provider for form login; the subsequent authorization step relies on the `Authentication`'s authorities.

~~~text
Browser POST /login (username + password + CSRF token)
         |
         v
Spring Security UsernamePasswordAuthenticationFilter
         |
         v
LdapAuthenticationProvider
         |
         +-- BindAuthenticator
         |      |
         |      +--> Resolve user DN via pattern/search
         |      +--> LDAP bind over TLS connection
         |      +--> Wrong password? Authentication fails
         |
         +-- DefaultLdapAuthoritiesPopulator
         |      |
         |      +--> Search groups by user DN / username
         |      +--> cn=PORTAL_READERS -> LDAP_PORTAL_READERS
         |
         +-- UserDetailsContextMapper
                |
                +--> LDAP_PORTAL_READERS -> ROLE_READER
                +--> LDAP_PORTAL_OPERATORS -> ROLE_OPERATOR
                +--> Not in an approved group? Reject or grant no role
                |
                v
         Authentication in SecurityContext
                |
                v
         AuthorizationFilter
         /me -> ROLE_READER or ROLE_OPERATOR
         /ops -> ROLE_OPERATOR
~~~

**Important:** Entering the right password may prove the user exists and is authenticated by LDAP, but **does not prove the user is permitted to use the application**. Mapping groups to `ROLE_*` is an application decision. A user outside approved groups may have login rejected (as in the demo) or be allowed to sign in while blocked per URL, depending on policy.

LDAP bind should use **TLS before transmitting credentials**. Plain `ldap://` without active StartTLS is an unencrypted LDAP connection; never treat `ldap://` as secure by default.

## 4. Group Lookup: Filters and Creating GrantedAuthority

In Spring Security, `DefaultLdapAuthoritiesPopulator` can be configured to search for groups under a **group search base**. For example:

~~~java
// Java configuration snippet inside a provider factory method:
DefaultLdapAuthoritiesPopulator groups =
        new DefaultLdapAuthoritiesPopulator(contextSource, "ou=groups");
groups.setGroupSearchFilter("(uniqueMember={0})");
groups.setGroupRoleAttribute("cn");
groups.setRolePrefix("LDAP_");
groups.setConvertToUpperCase(true);
~~~

Meaning:

- `"ou=groups"` is the search base **relative to the base DN** set on `LdapContextSource`.
- `(uniqueMember={0})` uses `{0}` as the **full user DN** to find groups that have that user as a member. Some LDAP schemas need `(member={0})`, or search based on username via `{1}`. Pick the filter after verifying the actual schema and data.
- `setGroupRoleAttribute("cn")` reads the group name from the group entry's `cn`.
- `setRolePrefix("LDAP_")` and `setConvertToUpperCase(true)` produce authority names like `LDAP_PORTAL_READERS` from `cn=PORTAL_READERS`. The `LDAP_` prefix separates **directory-sourced groups** from **application roles `ROLE_*`**.
- Mapping only applies when the group query finds entries and the lookup account has sufficient read access; do not mistake "authentication succeeded with zero authorities" for a password error.

`{0}` and `{1}` in filters are placeholders handled by Spring Security's search API; avoid concatenating request-supplied usernames directly into LDAP filters or DNs without using the library's escaping mechanism. LDAP filter injection differs from SQL injection but is equally dangerous when names/contexts are concatenated manually.

**Nested groups** are generally not queried recursively by a direct `(uniqueMember={0})` filter alone. Active Directory offers dedicated membership query mechanisms, though those are schema/vendor-specific solutions; explicitly specify how nested groups, cycles, denials, and depth limits are handled. Do not assume a user in a parent group via a child group is included by default.

### 4.1. From LDAP Group to Internal Role

An explicit mapping table is the easiest to control:

| Looked-up LDAP authority | Internal role | Allowed actions in demo |
| --- | --- | --- |
| `LDAP_PORTAL_READERS` | `ROLE_READER` | View `/me` |
| `LDAP_PORTAL_OPERATORS` | `ROLE_OPERATOR` | View `/me` and `/ops` |
| `LDAP_OTHER_GROUP` | Grants no role automatically | No automatic application permissions |
| No valid group found | No role; demo rejects login | Access denied |

Group names live in LDAP, yet group membership is granted/assigned by directory administrators. A directory can be misconfigured or groups can be managed outside the trust boundary; select groups from trusted domains/OUs, define who may edit membership, and audit permission changes.

**Avoid mapping patterns** like "every `cn` becomes `ROLE_<CN>`" if groups are not managed by an authorized team. Especially avoid assuming an external `cn=admins` always equates to the application's `ROLE_ADMIN`.

## 5. What Does UserDetailsContextMapper Do?

The `org.springframework.security.ldap.userdetails.UserDetailsContextMapper` interface defines two directions:

~~~java
UserDetails mapUserFromContext(
    DirContextOperations ctx,
    String username,
    Collection<? extends GrantedAuthority> authorities
);

void mapUserToContext(
    UserDetails user,
    DirContextAdapter ctx
);
~~~

- **`mapUserFromContext`** is the path used while loading the principal after LDAP authentication/lookup finishes. It receives `ctx` to read user attributes from LDAP, the session's username, and the set of LDAP authorities supplied by the authorities populator.
- **`mapUserToContext`** handles writing details from `UserDetails` back to the LDAP context in applicable scenarios. For applications that **only sign in and never update LDAP**, do not perform LDAP writes; throw unsupported in a read-only mapper.
- The mapper can normalize display names, check account status, attach a local user ID when integrating with a database, and translate groups into authorities. If durable local IDs or internal lock states are needed, use an application-owned repository/policy. The demo focuses solely on roles.
- The mapper does **not** replace LDAP bind, does not verify passwords, and does not automatically make connections use TLS. Nor does it replace `SecurityFilterChain` authorization.

Note that the demo's `UserDetails.getPassword()` does not hold the LDAP password, and you **should not** pull `userPassword` from LDAP for the application to compare or store itself. The authentication provider uses LDAP bind to verify passwords; the mapper only constructs the authenticated principal.

## 6. Spring Boot 3.3.5 / Java 17 Example with LDAP Bind and Group Mapping

This example uses a **real LDAP directory** following the schema illustrated in section 2. Running it successfully requires a valid LDAPS server, two users `alice`/`bob`, groups matching the LDIF, a read-only service account, a server certificate trusted by the JVM, and environment variables for endpoint/credentials. The code compiles with Maven/JDK 17+ once dependencies are present; this guide does not deploy or provision LDAP accounts automatically.

Structure:

~~~text
ldap-group-demo/
  pom.xml
  src/main/java/example/ldap/LdapGroupDemoApplication.java
  src/main/resources/application.yml
  src/test/java/example/ldap/ApprovedGroupMapperTests.java
~~~

### 6.1. Maven

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>ldap-group-demo</artifactId>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-ldap</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

`spring-security-ldap` supplies the LDAP authentication provider, authorities populator, and Spring Security LDAP integrations. `spring-boot-starter-security` supplies form login and the Servlet security chain. `spring-boot-starter-test` includes JUnit 5, AssertJ, and Mockito to test the mapper independently of a server.

### 6.2. Configuration via Environment Variables

**src/main/resources/application.yml:**

~~~yaml
demo:
  ldap:
    url: ${LDAP_URL}
    base: ${LDAP_BASE}
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

For example, use `LDAP_URL=ldaps://ldap.example.org:636` and `LDAP_BASE=dc=example,dc=org`. The service account DN is `cn=app-reader,ou=service,dc=example,dc=org`. **Do not** put real passwords in Git, docs, or responses; supply them from an appropriate secret store / environment.

### 6.3. Application and Security Configuration

**src/main/java/example/ldap/LdapGroupDemoApplication.java:**

~~~java
package example.ldap;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.ldap.authentication.BindAuthenticator;
import org.springframework.security.ldap.authentication.LdapAuthenticationProvider;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.ldap.userdetails.UserDetailsContextMapper;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LdapGroupDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LdapGroupDemoApplication.class, args);
    }

    @Bean
    LdapContextSource contextSource(
            @Value("${demo.ldap.url}") String url,
            @Value("${demo.ldap.base}") String base,
            @Value("${demo.ldap.bind-dn}") String bindDn,
            @Value("${demo.ldap.bind-password}") String bindPassword)
            throws Exception {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);  // Use ldaps:// in demo.
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);
        source.afterPropertiesSet();
        return source;
    }

    @Bean
    UserDetailsContextMapper ldapUserDetailsContextMapper() {
        return new ApprovedGroupMapper();
    }

    @Bean
    LdapAuthenticationProvider ldapAuthenticationProvider(
            LdapContextSource contextSource,
            UserDetailsContextMapper mapper) {

        BindAuthenticator authenticator =
                new BindAuthenticator(contextSource);

        // DN pattern relative to base dc=example,dc=org.
        authenticator.setUserDnPatterns(
                new String[] {"uid={0},ou=people"});

        DefaultLdapAuthoritiesPopulator groups =
                new DefaultLdapAuthoritiesPopulator(
                        contextSource, "ou=groups");

        // Matches the demo's groupOfUniqueNames schema.
        groups.setGroupSearchFilter("(uniqueMember={0})");
        groups.setGroupRoleAttribute("cn");
        groups.setRolePrefix("LDAP_");
        groups.setConvertToUpperCase(true);

        LdapAuthenticationProvider provider =
                new LdapAuthenticationProvider(authenticator, groups);

        provider.setUserDetailsContextMapper(mapper);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LdapAuthenticationProvider ldapProvider) throws Exception {

        return http
                .authenticationProvider(ldapProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/ops").hasRole("OPERATOR")
                        .anyRequest().hasAnyRole("READER", "OPERATOR"))
                .formLogin(Customizer.withDefaults())
                .build();
    }

    static final class ApprovedGroupMapper
            implements UserDetailsContextMapper {

        @Override
        public UserDetails mapUserFromContext(
                DirContextOperations ctx,
                String username,
                Collection<? extends GrantedAuthority> authorities) {

            Set<String> ldapGroups = authorities.stream()
                    .map(GrantedAuthority::getAuthority)
                    .collect(Collectors.toSet());

            List<GrantedAuthority> appRoles = new ArrayList<>();

            if (ldapGroups.contains("LDAP_PORTAL_READERS")) {
                appRoles.add(new SimpleGrantedAuthority("ROLE_READER"));
            }

            if (ldapGroups.contains("LDAP_PORTAL_OPERATORS")) {
                appRoles.add(new SimpleGrantedAuthority("ROLE_OPERATOR"));
            }

            if (appRoles.isEmpty()) {
                // Insufficient permission to use the app even if LDAP bind may succeed.
                throw new DisabledException("No approved application group");
            }

            // Do not put the LDAP password into the principal.
            return new User(
                    username, "",
                    true, true, true, true,
                    appRoles);
        }

        @Override
        public void mapUserToContext(
                UserDetails user, DirContextAdapter ctx) {
            throw new UnsupportedOperationException(
                    "This application does not write user data to LDAP");
        }
    }

    @RestController
    static class DemoController {

        @GetMapping("/")
        String home() {
            return "Sign in using the directory account";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            return Map.of(
                    "username", authentication.getName(),
                    "authorities", authentication.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList());
        }

        @GetMapping("/ops")
        String operations() {
            return "Operator access granted";
        }
    }
}
~~~

**What happens after submitting the login form?**

1. The Spring Security-generated login form sends a POST to `/login`, including the form CSRF token as configured by default.
2. The security chain uses `LdapAuthenticationProvider`; `BindAuthenticator` builds the DN `uid=alice,ou=people,dc=example,dc=org` relative to the base and attempts to bind over LDAPS with the password.
3. After a successful bind, `DefaultLdapAuthoritiesPopulator` searches for groups where `uniqueMember` matches the user DN and returns `LDAP_*` authorities.
4. `ApprovedGroupMapper` checks against the whitelist:
   - `LDAP_PORTAL_READERS` → `ROLE_READER`.
   - `LDAP_PORTAL_OPERATORS` → `ROLE_OPERATOR`.
   - No approved group → throws `DisabledException`, failing sign-in per the demo policy.
5. `SecurityFilterChain` then uses the principal's roles: users with `ROLE_READER` or `ROLE_OPERATOR` can read `/me`; only `ROLE_OPERATOR` can read `/ops`.

**Roles are not inherited automatically in Spring Security**: `ROLE_OPERATOR` does not implicitly include `ROLE_READER`. That is why `/me` uses `hasAnyRole("READER","OPERATOR")`; if role hierarchy is desired, configure it explicitly and verify consistency.

Returning a `User` with an empty password is **solely for the post-bind principal**; passwords are not verified by comparing against an empty string. Never reuse this principal with another `DaoAuthenticationProvider` lacking a password policy. In production, also check account status from the application's database and choose login error messages that do not disclose too much about users/groups.

### 6.4. Running Against a Real Directory

First confirm the DN/group schema on the LDAP server and verify the LDAPS server certificate is trusted by the JVM. In Bash/Git Bash, prepare the environment:

~~~bash
export LDAP_URL='ldaps://ldap.example.org:636'
export LDAP_BASE='dc=example,dc=org'
export LDAP_BIND_DN='cn=app-reader,ou=service,dc=example,dc=org'
# Read LDAP_BIND_PASSWORD from an environment-provided secret,
# do not hard-code passwords in source or shell history.

mvn spring-boot:run
~~~

The application requires `LDAP_BIND_PASSWORD` to be supplied by your deployment/secret manager. If missing, Spring cannot resolve the placeholder from YAML. Illustrative URLs and DNs must be replaced with your real server/directory, and user patterns must match the schema. If the directory uses `mail` or `sAMAccountName` instead of `uid`, adjust the DN lookup strategy and group search configuration; never assume the username is the DN.

Open `http://localhost:8080/` and visit `http://localhost:8080/me` to be redirected to the login page, then enter a directory account. After successful sign-in, requesting `/me` returns JSON similar to:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
~~~

This is an **illustrative output shape** when `alice` belongs to `PORTAL_READERS`; it is not fixed across different LDAP directories. Signing in as `bob` in `PORTAL_OPERATORS` allows accessing `/ops`, returning `Operator access granted`. Users outside those two approved groups have no valid principal under the demo mapper policy.

Using `curl` directly without cookies/session and a CSRF token for POST login is not equivalent to a browser form sign-in; to test LDAP bind directly, use a dedicated LDAP client tool configured with TLS.

## 7. Testing the Mapper Without a Real LDAP Server

Because the mapper only converts authorities into roles, it can be unit tested independently with JUnit 5 and Mockito. This is a **unit test**: it does not replace testing TLS bind, LDAP group search, or the login flow.

**src/test/java/example/ldap/ApprovedGroupMapperTests.java:**

~~~java
package example.ldap;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class ApprovedGroupMapperTests {

    private final LdapGroupDemoApplication.ApprovedGroupMapper mapper =
            new LdapGroupDemoApplication.ApprovedGroupMapper();

    private final DirContextOperations ctx =
            mock(DirContextOperations.class);

    @Test
    void readerGroupGetsOnlyReaderRole() {
        UserDetails user = mapper.mapUserFromContext(
                ctx, "alice",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_PORTAL_READERS")));

        assertThat(user.getAuthorities())
                .extracting("authority")
                .containsExactly("ROLE_READER");
        assertThat(user.getUsername()).isEqualTo("alice");
    }

    @Test
    void operatorGroupGetsOperatorRole() {
        UserDetails user = mapper.mapUserFromContext(
                ctx, "bob",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_PORTAL_OPERATORS")));

        assertThat(user.getAuthorities())
                .extracting("authority")
                .containsExactly("ROLE_OPERATOR");
    }

    @Test
    void unrelatedGroupIsNotAnApplicationRole() {
        assertThatThrownBy(() -> mapper.mapUserFromContext(
                ctx, "guest",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_UNRELATED"))))
                .isInstanceOf(DisabledException.class);
    }

    @Test
    void groupsAreMappedByWhitelistNotByArbitraryAdminName() {
        assertThatThrownBy(() -> mapper.mapUserFromContext(
                ctx, "someone",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_ADMIN"))))
                .isInstanceOf(DisabledException.class);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify that the two permitted groups map to local roles, non-whitelisted groups grant no permissions, and the name `LDAP_ADMIN` receives no special privileges just for looking administrative. For more complex real-world mappers, also test multiple groups, duplicate groups, disabled groups, tenant mismatches, and account status.

To test end-to-end, set up a test directory with user/group fixtures, configure trusted TLS certificates, perform login via browser/MockMvc with session + CSRF, and verify `/me` and `/ops` statuses. Testing the group mapper alone **does not prove** `DefaultLdapAuthoritiesPopulator` queries groups properly from the directory.

## 8. Securing LDAP Connections: LDAPS and StartTLS

When an LDAP client binds, passwords or credentials may traverse the network. Before sending sensitive data, **establish TLS and verify the server's identity**. Two common approaches:

| Criterion | LDAPS | LDAP + StartTLS |
| --- | --- | --- |
| Typical URL | `ldaps://ldap.example.org:636` | `ldap://ldap.example.org:389` |
| When TLS begins | TLS immediately upon connection | Connect via LDAP, then upgrade via StartTLS **before bind** |
| Client configuration | LDAP URL supporting LDAPS and JSSE truststore | Client must enable a StartTLS strategy with cert validation and handle upgrade failures |
| Misconfiguration risks | Trust-all, skipping hostname validation, expired certificates | Forgetting StartTLS, sending credentials prior to upgrade, or falling back to plaintext |
| Principle | Never use an unauthenticated server connection to carry passwords | If StartTLS fails to establish, **fail closed**, never bind in plaintext |

The Java demo uses **LDAPS**. Never simply change a URL string from `ldap://` to `ldaps://` and assume the system is secure without checking the actual certificate and trust chain.

### 8.1. Certificates and Truststore in the JVM

The LDAP server needs a valid certificate signed by a trusted CA, matching the hostname (SAN), unexpired, and with a proper chain. The JVM uses a trusted truststore to verify the chain. Example JSSE parameters (path and secret managed by the deployment environment):

~~~text
-Djavax.net.ssl.trustStore=/opt/app/certs/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<truststore-secret>
~~~

When running Maven, supply these properties to the **application JVM** via runtime/deployment configuration or `JAVA_TOOL_OPTIONS` as appropriate; do not accidentally pass them only to a JVM that does not make the LDAP connection. The truststore password is a secret; avoid printing commands with real secrets into pipeline logs or terminal history. If a public CA is already trusted by the JDK, a separate truststore may not be needed; many enterprise LDAP servers use an internal CA.

Never use a trust manager that accepts all certificates (`trustAll`), never disable hostname verification, and never ignore certificate path warnings. Doing so removes your ability to verify you are talking to the intended LDAP server, enabling man-in-the-middle attacks.

**Spring Boot's `server.ssl.*`** configures **inbound** HTTPS for the embedded web server; it does not configure the truststore for **outbound LDAP** connections. Both TLS directions must be evaluated independently.

### 8.2. Verifying Connectivity and Practical Security

An LDAP client tool supporting LDAPS can confirm group queries using the read-only service account:

~~~bash
ldapsearch -H ldaps://ldap.example.org:636 \
  -D 'cn=app-reader,ou=service,dc=example,dc=org' -W \
  -b 'ou=groups,dc=example,dc=org' \
  '(uniqueMember=uid=alice,ou=people,dc=example,dc=org)' cn
~~~

`-W` prompts interactively for the password, avoiding placing passwords directly on the command line. Configure the tool with proper **CA and certificate/hostname verification**; success on a machine running `ldapsearch` does not automatically prove the JSSE truststore on the Java host is configured correctly.

Verify separately: the LDAP server validates certificates with the right hostname, the app refuses to connect when certificates are wrong/expired, the app rejects servers offering only plaintext, and passwords never appear in HTTP responses/logs. With StartTLS, verify upgrade success **before any password-bearing bind** and never fall back to plaintext.

### 8.3. Service Account Secrets and Permissions

- Store `LDAP_BIND_PASSWORD` in a secret manager or platform secret injection mechanism; never commit it to `application.yml`, Docker images, or screenshots.
- The service account only needs permission to **read user/group attributes needed for sign-in**; do not grant permissions to create/edit/delete accounts, change passwords, or read out-of-scope data.
- Configure network policies allowing the application to reach only the right server/port, and log connection errors without printing credentials.
- Rotate secrets/certificates, monitor certificate expiration, and configure bounded retries and health checks as needed.
- If LDAP is a centralized authentication system, downtime requires a fail-closed policy, appropriate error messaging, and an approved emergency administrative mechanism.

## 9. Authorization by LDAP Group: Design Choices and Trust Boundaries

### 9.1. Do Not Equate Every Group with an Application Role

A directory can contain hundreds of unrelated groups. Turning every `cn` into `ROLE_*` creates dangerous implicit privilege relationships, especially when group owners are not the application's administrators. Choose a trusted allowlist of groups and a controlled mapping table, ideally scoped to specific domains/OUs.

When LDAP groups are managed by IT while business roles require approval from the application owner, you can use **LDAP groups solely to establish initial identity/eligibility**, then look up an internal role database. `UserDetailsContextMapper` can call a service to look up the local account, though you must account for latency, availability, caching, and failures.

### 9.2. Group Updates After User Sign-In

LDAP authorities are typically loaded **at authentication time**. For an existing HTTP session, membership changes in the directory do not necessarily update `Authentication` in the session immediately. If permissions are urgently revoked, the application needs session timeout, reauthentication, session invalidation, or real-time permission rechecks in the appropriate service.

Never claim that merely removing a user from an LDAP group revokes all active sessions instantaneously. Depending on risk level, you may need real-time checks on sensitive APIs, centralized session revocation, or short TTLs.

### 9.3. Nested Groups and Active Directory

Every directory has its own schema and membership resolution model. Active Directory commonly uses `sAMAccountName`, `userPrincipalName`, and `memberOf`, and may have nested groups. Spring Security provides dedicated Active Directory integrations; the `uid` + `groupOfUniqueNames` example above is not a default AD configuration.

Before implementing, verify:

- Is the user located by DN pattern or user search filter?
- Are groups `groupOfNames` with `member`, `groupOfUniqueNames` with `uniqueMember`, or another schema?
- Can users/groups reside deep across multiple OUs requiring subtree search?
- How should direct and nested groups be handled?
- Can `cn` names collide across OUs or tenants?
- Does a disabled/locked LDAP account cause bind to fail, and how is local account status additionally checked?

These decisions directly impact authorization correctness; no single group filter fits every LDAP deployment.

## 10. Common Errors and Diagnostics

| Symptom | Possible cause | Diagnostic step |
| --- | --- | --- |
| Login always fails with LDAP connection error in logs | Wrong server/port, untrusted TLS certificate, firewall, wrong service account DN | Check LDAPS handshake/truststore and network connectivity before suspecting passwords |
| User exists yet bind reports invalid credentials | Wrong user DN pattern, wrong password, locked LDAP account, directory policy | Verify DN and schema; never log passwords or switch to plaintext |
| Login succeeds but user has no groups | Wrong group base, filter uses `member` instead of `uniqueMember`, service account lacks group read access, nested groups | Run direct LDAP search over TLS with the real DN |
| Initial authority is `ROLE_...` instead of `LDAP_...` | Default/different populator role prefix configured | Check `setRolePrefix` and uppercase rules; do not confuse mappings |
| Similar group name exists yet role is not granted | `cn` casing/underscores differ, mapping code mismatch | Match the exact authority emitted by the populator; use explicit mapping |
| User outside app groups can still log in | Mapper returns a principal with empty roles or fallback config exists | Define deny policy when no approved group matches and test this case |
| User with `ROLE_OPERATOR` cannot read `/me` | `hasRole("READER")` does not automatically treat OPERATOR as READER | Use `hasAnyRole` or an explicitly designed role hierarchy |
| Removed from group yet old session still has access | Authorities loaded at login; session not refreshed | Establish revocation/re-login/re-authorization policy for sensitive endpoints |
| Truststore works on laptop but fails in production | Runtime Java uses a different truststore, missing internal CA, hostname mismatch | Inspect actual JVM flags and certificate chain/SAN |
| AD cannot find `uid=alice` | AD does not use the demo schema | Use AD-appropriate user search/group lookup strategies |
| LDAP search slows down as directory grows | Broad base, unindexed filter, nested traversal, connection timeouts | Narrow search base, ensure proper indexes, tune timeouts, measure latency |
| Browser POST /login returns 403 | Missing CSRF token on login form, session/cookie mismatch | Inspect form login and CSRF configuration; never disable CSRF globally |

**Distinguishing error statuses:** wrong passwords typically cause login failure (redirecting to the login page with an error under form login), whereas being authenticated yet lacking a role typically yields a 403 from authorization. In the demo, a user without an approved group can **be rejected directly in the mapper**, so they never receive an authenticated session; this is an intentional policy choice.

**Safe observability:** in development, enable only the needed log level for `org.springframework.security.ldap` and Spring LDAP to see which phase failed, without turning on overly broad debug logging that dumps sensitive details. Log `group count`, error codes, query duration, and properly redacted DNs; never log passwords, secrets, or unnecessary sensitive directory contents.

## 11. Self-Check Questions and Exercises

**Question 1.** Does a successful LDAP bind automatically grant `ROLE_ADMIN`?  
**Answer:** No. Bind proves the credentials were accepted by LDAP; application permissions must be mapped from trusted groups/policies.

**Question 2.** `DefaultLdapAuthoritiesPopulator` returns `LDAP_PORTAL_READERS`. Which component in the demo converts it to `ROLE_READER`?  
**Answer:** `ApprovedGroupMapper.mapUserFromContext`, a `UserDetailsContextMapper`.

**Question 3.** The directory uses `groupOfNames` with the `member` attribute, but the application searches `(uniqueMember={0})`. Why does the user get no roles?  
**Answer:** The filter does not match the actual schema; change it to `(member={0})` after verifying the group structure.

**Question 4.** A user is in group `PORTAL_OPERATORS`, and `/me` requires `hasRole("READER")`. Is access allowed by default?  
**Answer:** No. Spring Security does not automatically infer that OPERATOR is READER. The demo uses `hasAnyRole("READER","OPERATOR")`.

**Question 5.** A user still has permissions after being removed from an LDAP group. Is that necessarily a group filter bug?  
**Answer:** No. The session may still hold authorities loaded during the previous sign-in; an update/revocation policy is needed.

**Question 6.** Switching `ldaps://` to `ldap://` without enabling StartTLS to fix a connection error. Is that safe?  
**Answer:** No. Transmitting credentials over plaintext LDAP increases exposure risk; fix the truststore/certificate/host properly or configure fail-closed StartTLS.

**Question 7.** Does `server.ssl.enabled=true` in Spring Boot automatically protect outbound LDAP connections?  
**Answer:** No. That applies to the application's HTTPS server; the LDAP client needs LDAPS/StartTLS and its own appropriate truststore.

**Question 8.** LDAP has a group named `ADMIN`, but the application owner has not approved that group. Should it be mapped to `ROLE_ADMIN` because the names look similar?  
**Answer:** No. Map only whitelisted groups governed within the proper trust boundary.

**Question 9.** Does a passing unit test on the mapper prove LDAPS connectivity and bind work?  
**Answer:** No. It only verifies group-to-role logic; integration tests against a real/fixture LDAP server with TLS and certificate policy are required.

## 12. Implementation Checklist and Key Takeaways

- **Verify schema**: base DN, user DN pattern/search, group OU, `member`/`uniqueMember`, `cn`, and whether nested groups or AD apply.
- **Separate three layers**: `BindAuthenticator` checks passwords, `DefaultLdapAuthoritiesPopulator` looks up LDAP groups, and `UserDetailsContextMapper` converts trusted groups into application principal/roles.
- **Restrict privileges**: map via a governed whitelist; never mint `ROLE_ADMIN` from an arbitrary `cn`; check disabled accounts, tenants, local permissions, and session revocation policies.
- **Protect connections**: LDAPS or StartTLS **before bind**, verify chain and hostname; configure the truststore of the JVM calling LDAP, never enable trust-all, and never fall back to plaintext.
- **Guard secrets**: read-only service account, passwords from a secret manager, never log credentials/sensitive DNs; verify timeouts/network/rotation and certificate expiry.
- **Test at the right layers**: unit test the group mapper, integration test bind/group search and TLS, test `/me`/`/ops` with session; test unknown groups, nested groups, disabled users, stale sessions, and certificate errors.

**Key takeaway:** LDAP answers **who is signing in and which groups the directory says they belong to**. `UserDetailsContextMapper` is where that data is converted into **application-controlled UserDetails/roles**. All exchanges of credentials and group information with LDAP must traverse a protected connection whose server identity has been verified.
