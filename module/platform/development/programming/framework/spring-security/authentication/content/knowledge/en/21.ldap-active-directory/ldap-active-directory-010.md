# Testing LDAP/Active Directory with a test directory and controlled organizational data

## 1. Why is a test directory needed?

In the **Spring Security – authentication** module, LDAP and Microsoft Active Directory (AD) commonly store identity information in a hierarchical structure: users, organizational units (OUs), groups, and account attributes. A single successful login only verifies a small part of the integration. The application must also locate the right user, bind with a valid password, convert memberships into authorities, reject invalid identities, and handle directory failures without over-granting permissions.

This lesson focuses on **reproducible and safe testing approaches**, across two tiers:
1. **Automated LDAP integration testing**: running a dedicated in-memory directory for the test suite, loading a synthetic LDIF dataset, invoking the exact Spring Security LDAP authentication classes, and verifying outcomes.
2. **Controlled AD compatibility testing**: running in a dedicated test domain/forest because a standard LDAP server **does not fully reproduce** AD rules such as `userPrincipalName`, `sAMAccountName`, trusts, nested groups, account lockout, Group Policy, or LDAP signing/channel binding rules.

Objectives after this lesson:
- Distinguish **authentication** (the user can bind), **authority mapping** (which roles the user receives), and **authorization** (which actions those roles are permitted to perform).
- Deliberately design the directory tree, LDIF fixtures, group names, and positive/negative scenarios.
- Run standalone Java 17+ tests using JUnit 5, UnboundID LDAP SDK, and `LdapBindAuthenticationManagerFactory`.
- Know the limits of LDAP simulation and how to conduct AD testing without arbitrarily using enterprise production accounts or data.

## 2. Four testing types and trust boundaries

| Type | Real components | What it verifies | What it does not prove |
| --- | --- | --- | --- |
| Unit test | Mock `AuthenticationManager`, mapper, policy | Role transformation logic, error messages, and authorization decisions | Real LDAP search, bind, schema, or connectivity |
| LDAP integration test | In-memory LDAP or OpenLDAP container and Spring Security LDAP | DN/base, bind, group lookup, fixtures, invalid credential handling | AD-specific behaviors, real TLS/PKI, domain controllers |
| AD integration test | AD DS in a dedicated lab domain/forest | UPN, `sAMAccountName`, membership, policies, account errors, lab TLS/LDAP settings | Enterprise production policies if the lab is not identical |
| Pre-production acceptance | Admin-provisioned staging directory, isolated test accounts | Endpoint configuration, certificates, ACLs, timeouts, alignment with environment policies | Permission to use production freely; not a guarantee for every real account |

**Principle:** the closer a test gets to production, the higher its operational cost and permission boundaries. Most LDAP tests should run autonomously in CI with synthetic data; AD tests require a dedicated environment and operational schedule.

Example directory tree for testing:

~~~text
dc=lab,dc=example
├── ou=people
│   ├── uid=alice   (member of readers group)
│   └── uid=bob     (not a member of readers group)
└── ou=groups
    └── cn=readers  (member: Alice's DN)
~~~

In LDAP, **DN (Distinguished Name)** indicates an entry's unique position in the tree; **base DN** bounds the search scope. `ou` is organizational unit; `uid` and `cn` are the attributes chosen for this fixture. This tree is purely synthetic data and does not represent a mandatory OU layout or schema of a real AD.

## 3. Creating controlled organizational fixtures

### 3.1. Choosing data with testing intent

A good fixture must include **at least one authorized case and one denied case**. For example:

| Entry | Key attributes | What to verify |
| --- | --- | --- |
| `uid=alice,ou=people,...` | `uid=alice`, `userPassword` is test password | Valid bind succeeds; belongs to `readers` |
| `uid=bob,ou=people,...` | `uid=bob`, different password from Alice | Valid bind succeeds, yet does not automatically receive `ROLE_READERS` |
| `cn=readers,ou=groups,...` | `objectClass=groupOfNames`, `member=<Alice's DN>` | Spring Security maps membership into authority |
| Absent `uid=ghost` | No entry | Authentication must fail |
| Wrong password for Alice | Entry exists but wrong credentials | Authentication must fail |

Never use real names, emails, employee IDs, group lists, or passwords. When data must represent an organizational structure, **create completely synthetic entries** and keep only the required relationships: one user in group A, another user not in A, a user outside the search scope, etc. Stripping names while keeping real emails, DNs, SIDs, or raw logs may still fail to anonymize properly.

### 3.2. Complete and reloadable LDIF

Create `src/test/resources/fixtures/directory.ldif` as follows. LDIF represents each entry as a block of attributes separated by blank lines; ordering from base to OUs, users, and groups keeps imports clear.

~~~ldif
dn: dc=lab,dc=example
objectClass: top
objectClass: domain
dc: lab

dn: ou=people,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=alice,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Alice Demo
sn: Demo
uid: alice
userPassword: alice-test-pass

dn: uid=bob,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Bob Demo
sn: Demo
uid: bob
userPassword: bob-test-pass

dn: cn=readers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: readers
member: uid=alice,ou=people,dc=lab,dc=example
~~~

**Clarifying common points of confusion:**
- `objectClass: inetOrgPerson` is for standard LDAP users; the `groupOfNames` group uses the `member` attribute containing **the user's DN**, not the bare string `alice`.
- `userPassword` in the fixture is written in plaintext only because the directory runs locally with fake names and passwords. Do not use this pattern to design real password storage; production password mechanisms depend on the server and security policies.
- `ou=people` and `ou=groups` are two distinct areas. If search bases are misconfigured, users or groups may not be found even though the entries exist.
- Changing a fixture must be accompanied by updating test expectations; tests must never blindly accept any new membership just to stay green.

## 4. Runnable integration test with Java 17+ and JUnit 5

The example below is a **test-only Gradle project** requiring neither a Spring Boot Web server nor a real AD system. `LdapBindAuthenticationManagerFactory` and `DefaultLdapAuthoritiesPopulator` are Spring Security classes used directly. UnboundID provides an ephemeral LDAP listener in the same test process.

Files:
~~~text
ldap-directory-lab/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/LdapDirectoryIntegrationTest.java
    └── resources/fixtures/directory.ldif
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'ldap-directory-lab'
~~~

`build.gradle` (Java 17, library versions aligned by Spring Boot BOM 3.3.12):

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.12')
    testImplementation 'org.springframework.security:spring-security-config'
    testImplementation 'org.springframework.security:spring-security-ldap'
    testImplementation 'com.unboundid:unboundid-ldapsdk'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/test/java/demo/LdapDirectoryIntegrationTest.java`:

~~~java
package demo;

import java.net.InetAddress;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

import static org.junit.jupiter.api.Assertions.*;

class LdapDirectoryIntegrationTest {

    private static InMemoryDirectoryServer directory;
    private static AuthenticationManager manager;

    @BeforeAll
    static void startDirectory() throws Exception {
        var config = new InMemoryDirectoryServerConfig("dc=lab,dc=example");

        // Listen only on loopback and use port 0 to pick an available port automatically.
        config.setListenerConfigs(InMemoryListenerConfig.createLDAPConfig(
                "test-ldap",
                InetAddress.getByName("127.0.0.1"),
                0,
                null));

        // Special account existing only in the test server, not in the LDIF.
        config.addAdditionalBindCredentials(
                "cn=fixture-reader,dc=lab,dc=example", "lookup-test-only");

        directory = new InMemoryDirectoryServer(config);
        directory.importFromLDIF(
                true,
                Path.of("src/test/resources/fixtures/directory.ldif").toFile());
        directory.startListening();

        // URL includes the listener address and base DN; does not connect to a real directory.
        var context = new DefaultSpringSecurityContextSource(
                "ldap://127.0.0.1:" + directory.getListenPort()
                        + "/dc=lab,dc=example");
        context.setUserDn("cn=fixture-reader,dc=lab,dc=example");
        context.setPassword("lookup-test-only");
        context.afterPropertiesSet();

        // Search groupOfNames under ou=groups by the user's DN.
        var authorities = new DefaultLdapAuthoritiesPopulator(
                context, "ou=groups");
        authorities.setGroupSearchFilter("(member={0})");
        authorities.setGroupRoleAttribute("cn");
        authorities.setRolePrefix("ROLE_");
        authorities.setConvertToUpperCase(true);

        // Bind under ou=people: uid=alice,... or uid=bob,...
        var factory = new LdapBindAuthenticationManagerFactory(context);
        factory.setUserDnPatterns("uid={0},ou=people");
        factory.setLdapAuthoritiesPopulator(authorities);
        manager = factory.createAuthenticationManager();
    }

    @AfterAll
    static void stopDirectory() {
        if (directory != null) {
            directory.shutDown(true);
        }
    }

    private static Authentication authenticate(String uid, String password) {
        return manager.authenticate(
                new UsernamePasswordAuthenticationToken(uid, password));
    }

    private static Set<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .map(a -> a.getAuthority())
                .collect(Collectors.toSet());
    }

    @Test
    void validCredentialsAuthenticate() {
        Authentication alice = authenticate("alice", "alice-test-pass");
        assertTrue(alice.isAuthenticated());
    }

    @Test
    void membershipBecomesRoleOnlyForMember() {
        Set<String> aliceRoles =
                authorities(authenticate("alice", "alice-test-pass"));
        Set<String> bobRoles =
                authorities(authenticate("bob", "bob-test-pass"));

        assertTrue(aliceRoles.contains("ROLE_READERS"));
        assertFalse(bobRoles.contains("ROLE_READERS"));
    }

    @Test
    void incorrectPasswordFails() {
        assertThrows(AuthenticationException.class,
                () -> authenticate("alice", "incorrect-password"));
    }

    @Test
    void unknownUserFails() {
        assertThrows(AuthenticationException.class,
                () -> authenticate("ghost", "any-password"));
    }

    @Test
    void anotherUserCannotReuseAlicePassword() {
        assertThrows(AuthenticationException.class,
                () -> authenticate("bob", "alice-test-pass"));
    }
}
~~~

**Run:** in the project directory, with Gradle installed or a Gradle Wrapper generated:

~~~bash
gradle test
# Or if the project has the Gradle Wrapper:
./gradlew test
~~~

On Windows use `gradlew.bat test` when a wrapper is present. Expect **all 5 tests to pass**; Gradle returns exit code 0. Do not assert a fixed stdout string because Gradle prints varying logs depending on version, cache, and logging level.

**Why this test is meaningful:**
1. The directory is reloaded from a controlled LDIF; it makes no calls to an LDAP server on the corporate network.
2. Binding with right/wrong passwords is executed by the LDAP server, not stubbed or hardcoded to return `true`.
3. Spring Security fetches memberships via `(member={0})`, where `{0}` is replaced with the authenticated user's DN. From `cn=readers`, the example maps `ROLE_READERS`.
4. A user can **log in** yet **lack an authority** for the group in question: Bob does not have `ROLE_READERS`. That illustrates the difference between authentication and authorization.
5. The directory listens on `127.0.0.1` on an ephemeral port and shuts down in `@AfterAll`. This unencrypted LDAP protocol is used strictly between the test process and loopback; connections to real LDAP/AD must protect the channel and verify certificates.

**Important limitation:** this project tests `AuthenticationManager` and LDAP authority resolution; it **does not test `SecurityFilterChain`, HTTP 401/403, or `@PreAuthorize` annotations**. When integrating into a Spring MVC application, add `MockMvc` or live requests to verify URL/method policies, login sessions, and web-layer authority mapping. With WebFlux, use `WebTestClient` with the authentication mechanism actually configured by the reactive application; never use Servlet tests to draw conclusions about reactive behavior.

## 5. Mandatory scenarios before trusting an LDAP integration

| Scenario | Input/condition | What must be verified |
| --- | --- | --- |
| Bind succeeds | Real user, correct password | `Authentication.isAuthenticated() == true` |
| Bind fails | Wrong password or non-existent user | Authentication error thrown; no valid session/authority granted |
| Right role | Alice is a `member` of `readers` | Holds `ROLE_READERS` |
| No privilege escalation | Bob is not a member | Bob does not get `ROLE_READERS` despite valid login |
| Bounded search base | User resides in an OU outside `userDnPatterns`/search base | Must not silently search into out-of-policy OUs |
| Group rename/remove | Change `cn`/membership in an isolated test fixture | Authorities reflect intentional mapping and cache rules |
| Unicode/accented names | User/group with properly LDIF-encoded attributes | Strings read/compared accurately without UTF-8 corruption |
| Special characters in input | `(`, `*`, `\`, and characters needing escaping | Must not cause LDAP filter injection; only intended user matched |
| LDAP errors | Directory stopped, timeout, wrong base, wrong bind account | Fail closed; never auto-allow login |
| Connection exhaustion/retries | Directory slow or briefly disconnected | Bounded timeouts and retries; no resource exhaustion or infinite loops |

Never use a real user to test repeated wrong passwords: **AD can lock the account** per domain policy. In automated tests, use only synthetic accounts and isolated directories. Scenarios that mutate fixtures should launch a fresh directory or reset all data after each test to avoid order dependence.

### Filter injection and escaping

LDAP filter is an expression language, not a string to concatenate arbitrarily. **Unsafe** example when building a filter from input:

~~~java
// Illustrates the bug only; do not use in production.
String filter = "(uid=" + suppliedUsername + ")";
~~~

Special characters can alter the filter's meaning. When searching users by attribute instead of a DN pattern, use standard Spring Security APIs:

~~~java
// Supplemental configuration snippet, not a standalone Java program.
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter("(uid={0})");
~~~

Spring Security's bind/search mechanism substitutes parameters via appropriate APIs. Avoid building filters or DNs via uncontrolled string concatenation; when using Spring LDAP directly, use `LdapQueryBuilder`/parameterized APIs and corresponding DN/filter escaping rules. Test special-character inputs with dedicated fixtures to confirm the result set is never broadened.

## 6. What does controlled organizational data mean?

**Synthetic data:** create all DNs, OUs, UPNs, groups, and memberships from scratch per scenario without deriving them from real employee data. This is the default choice for CI.

**Data approved for staging:** use only when specific structures/schemas must be checked in a directory-admin-managed environment. Predefine the required attribute scope, access permissions, retention window, log destination, and post-test cleanup. Use dedicated test accounts; prefer a scrubbed relationship diagram copy with identifying data removed rather than a production directory snapshot.

A practical workflow:

1. **Define cases first:** e.g., "employees in group A must have read permission; contractors must not have edit permission." Only then create corresponding users/groups.
2. **Define schema and fixtures:** maintain LDIF or IaC scripts in a reviewed test directory; clearly document base DN, expected memberships, and expected authorities.
3. **Separate environments:** dedicated test domain, network/VLAN, or container; configure `ldap.url` and credentials under the `test` profile; forbid `test` profiles from pointing at production endpoints.
4. **Limit permissions:** bind/search accounts are read-only on strictly required OUs/attributes; never use domain admin and never touch real organizational objects.
5. **Protect secrets:** supply staging secrets via secret manager/environment variables; never commit real passwords, tokens, certificate private keys, or PII dumps.
6. **Manage logs:** test reports log synthetic usernames, error categories, and assertions; never print passwords, real people's full DNs, credentials, tickets, tokens, or `userPassword` contents.
7. **Clean up and reproduce:** initialize fresh per job or reset fixtures; tear down directories/containers, delete temporary credentials, revoke permissions, and apply artifact retention.
8. **Verify fail closed:** if the directory is unavailable, users must never receive "default" permissions; distinguish system errors from bad credentials in internal logs without leaking account details publicly.

### A reviewable fixture layout

~~~text
src/test/resources/fixtures/
├── directory.ldif          # verified synthetic users/groups
├── expected-membership.md  # alice -> readers; bob -> none
└── cases.md                # test cases table, expected roles, and test boundaries
~~~

Each fixture should have an owner, rationale, schema version, minimal dataset, and reset procedure. You do not need a "full replica" of the HR system to verify a group mapping.

## 7. When testing against real AD: limits of LDAP simulation

AD supports LDAP but is not identical to a standard LDAP server. Never conclude that because `inetOrgPerson`/`groupOfNames` fixtures pass, an AD configuration is guaranteed to be correct.

| AD aspect | Why LDAP fixtures are often insufficient | Testing in an AD lab |
| --- | --- | --- |
| Login name | AD has `userPrincipalName`, `sAMAccountName`, domain suffixes, sometimes multiple login formats | Log in using the exact name formats the application officially accepts |
| Provider | `ActiveDirectoryLdapAuthenticationProvider` has its own bind and user search rules | Use the exact provider/config the application will deploy |
| Groups | AD uses `member`/`memberOf`, with nested groups, scopes, and trusts | Test direct/nested membership, cross-domain groups, and role mapping rules |
| Account state | Disabled, expired, locked, password expired, logon restrictions | Test with lab accounts and dedicated lockout policies; verify errors never grant permissions |
| Network/TLS | Domain controllers, DNS, certificates, LDAP signing, channel binding | Verify actual lab settings, TLS and certificate trust, timeouts/failover |
| Replication | Multiple DCs have synchronization lag | Test changing groups/passwords and authenticating across lab DCs |
| ACLs | Anonymous search/service account may not be allowed to read all attributes | Verify least-privilege read permissions of the service principal |

Spring Security provides `ActiveDirectoryLdapAuthenticationProvider` for AD conventions. **Illustrative configuration snippet, does not run standalone**:

~~~java
// Configuration snippet in a Spring app; requires an AD lab and separate TLS verification.
ActiveDirectoryLdapAuthenticationProvider provider =
        new ActiveDirectoryLdapAuthenticationProvider(
                "lab.example", "ldaps://dc1.lab.example:636/");
~~~

Add search base/filter, authority policy, and truststore per your organization's model; never copy illustrative URLs as real endpoints. With AD, certain sub-error codes can indicate locked/disabled/expired states; do not rely on every server or configuration returning one specific code. Keep detailed logs in controlled internal systems to avoid helping external actors probe accounts.

**Distinguish TLS requirements:** plain LDAP on port 389 is unencrypted. LDAPS (commonly 636) or StartTLS protects data in transit when certificate chains and hostnames are properly verified. LDAP signing only protects integrity for certain SASL sessions and does not replace TLS for securing simple bind; channel binding has its own role when using SASL over TLS. Never disable certificate validation "to make tests pass".

## 8. Integrating tests into CI while maintaining organizational control

- **CI on every commit/pull request:** unit tests + UnboundID in-memory integration; no secrets needed and no access to real directories.
- **Dedicated integration environment:** OpenLDAP container or AD lab with provisioned test accounts/credentials; accessed over an isolated network, triggered only with authorized jobs and permissions.
- **Pre-release acceptance:** same authentication/authority mapping configuration close to production, but endpoints and accounts must be staging/test; review TLS, ACLs, policies, and timeouts.
- **Release blockers:** do not ship if wrong credentials can still log in, Bob receives Alice's group permissions, lookups escape the expected OU, directory errors allow requests through, or live tests accidentally target production endpoints.

In CI environments without network/container support, the UnboundID tests in the example above still run without fixed ports or Docker. When using Docker, pin image versions, mount temporary volumes/fixtures, restrict networking, and reset state between runs. Never let suites read a "live" LDAP fixture freely modified by multiple jobs.

### Diagnosing common test errors

| Symptom | Check first | Remediation |
| --- | --- | --- |
| User exists but cannot log in | DN pattern, `userSearchBase`, bind account, password | Fix user lookup; confirm right server and OU |
| Bind succeeds yet role is missing | `groupSearchBase`, `groupSearchFilter`, `member` holding full DN, role prefix/case | Check mapping and membership fixture |
| Bob unexpectedly gets `ROLE_READERS` | Overly broad group filter, test state leaking between tests, role cache | Narrow filter, reset fixture, inspect group entry |
| Passes locally but fails in CI | Fixed port, fixture missing from classpath, version mismatch, file encoding | Port 0, consistent paths, pinned dependencies, UTF-8 |
| Lab directory times out | DNS/routing/TLS/truststore, LDAP/JNDI timeout, service account | Distinguish availability from credentials; never fall back to allow |
| AD returns policy error | Account disabled/locked, password expired, bind type/signing, TLS | Test against AD lab policy; never alter production GPOs |

Do not collapse all errors into "wrong password" in internal logs, because that hides truststore failures, blocked service accounts, or wrong OU settings. However, client-facing messages should avoid leaking identities or policy details.

## 9. Verifying results and self-practice questions

**Case 1.** Alice uses the right password, Bob uses the right password. Both have `isAuthenticated()` as `true`, yet only Alice has `ROLE_READERS`. Is there a contradiction? **No**: successful authentication does not imply group permissions are granted.

**Case 2.** Bob suddenly gets `ROLE_READERS` after `member: uid=bob,...` was added to a group in another fixture. Tests become flaky if the suite does not reset state. Fix this by creating a fresh directory per test/suite or performing verified state resets; if the application caches roles, test cache invalidation timing separately.

**Case 3.** An in-memory LDAP test passes with `uid`, yet a real user logging into AD with `user@company.example` fails. This does not prove AD is broken: test `ActiveDirectoryLdapAuthenticationProvider` and `UPN`/domain suffix attributes in an AD lab.

**Case 4.** To test account lockout, a CI job uses a real employee account and repeats 20 wrong passwords. This is inappropriate: it can lock the account and record anomalous authentication behavior. Create a dedicated account in the AD lab with approved policies and permissions.

**Pass checklist:**
- [ ] Fixtures are completely synthetic, with defined base DN/OUs/users/groups and reviewed expected permissions.
- [ ] Tests cover both success and failure; authentication, authorities, and authorization are distinguished.
- [ ] Wrong password, non-existent user, and user outside groups all have explicit assertions.
- [ ] Tests never connect to production; ports/contexts are isolated and cleanly torn down.
- [ ] Zero real credentials or PII in source, logs, or artifacts.
- [ ] Dedicated AD tests cover UPN/`sAMAccountName`, nested groups, policies, TLS, and replication when required.
- [ ] No directory error ever grants permissions exceeding policy.

## 10. References

- [Spring Security 6.5 – LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind auth, DN/search filters, authority populators, and AD provider.
- [Spring Security API – ActiveDirectoryLdapAuthenticationProvider](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html): how the provider handles login names and AD specifics.
- [UnboundID – In-Memory Directory Server](https://docs.ldap.com/ldap-sdk/docs/in-memory-directory-server.html): configuring the test server and importing LDIF.
- [UnboundID API – InMemoryDirectoryServer](https://docs.ldap.com/ldap-sdk/docs/javadoc/com/unboundid/ldap/listener/InMemoryDirectoryServer.html): lifecycle and `importFromLDIF`.
- [Microsoft Learn – LDAP signing](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing) and [LDAP channel binding](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding): protecting directory communication in AD.

**Takeaway:** A valuable LDAP test is one built on a **minimal, reproducible fixture with clear expected permissions**; when AD-specific behavior must be confirmed, use a managed test AD directory and controlled organizational data.