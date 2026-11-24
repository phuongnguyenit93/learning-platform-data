# UserDetailsContextMapper and principals from directory attributes (LDAP / Active Directory)

## 1. From an LDAP entry to a Spring Security principal

In an enterprise, user identities may reside in an **LDAP directory** or **Microsoft Active Directory (AD)**. A directory entry contains attributes such as login name, display name, email, department, distinguished name (DN), and group information. After the user is authenticated, the Spring Security application needs to transform that data into an appropriate **principal** for business code to use.

`UserDetailsContextMapper` is the extension point that performs this transformation:

```text
User-submitted username + password
        |
        v
LDAP AuthenticationProvider / AD AuthenticationProvider
        |
        | 1. Bind / verify credentials against directory
        | 2. Read LDAP entry and retrieve GrantedAuthority
        v
DirContextOperations + username + authorities
        |
        | 3. UserDetailsContextMapper.mapUserFromContext(...)
        v
UserDetails (Authentication principal)
        |
        v
SecurityContext --> application reads principal / authorities
```

**Distinguish three important responsibilities:**

- **Authentication**: LDAP bind, LDAP password comparison, or AD's own mechanism verifies credentials. The mapper does not verify passwords.
- **Authority loading**: `LdapAuthoritiesPopulator`, AD's authority loader, or equivalent configuration computes the `GrantedAuthority` list.
- **Principal mapping**: `UserDetailsContextMapper` determines the `UserDetails` type and which directory attributes are available after login.

Therefore, `UserDetailsContextMapper` is **not a `UserDetailsService`**, nor is it a default privilege-granting mechanism. Spring Security LDAP bind generally cannot read passwords from the directory for the application to match locally like `DaoAuthenticationProvider`.

## 2. The UserDetailsContextMapper interface

Package: `org.springframework.security.ldap.userdetails.UserDetailsContextMapper`.

```java
public interface UserDetailsContextMapper {

    UserDetails mapUserFromContext(
            DirContextOperations ctx,
            String username,
            Collection<? extends GrantedAuthority> authorities);

    void mapUserToContext(
            UserDetails user,
            DirContextAdapter ctx);
}
```

The snippet above presents the API signature, not a standalone Java file; the types belong respectively to `org.springframework.ldap.core`, `org.springframework.security.core`, and `org.springframework.security.core.userdetails`.

**`mapUserFromContext(...)`**:

1. `ctx`: represents the entry retrieved from the directory. Read attributes with `getStringAttribute("mail")`, `getStringAttributes("memberOf")`, `getObjectAttribute(...)`, etc.
2. `username`: the login name passed to the provider/mapper. This is not necessarily a person's permanent identifier key; the name may be normalized or changed under directory policies.
3. `authorities`: permissions already supplied by the authority-loading component. Preserve or filter them according to explicit policy; never self-grant privileges from unverified descriptive fields.
4. Result: a `UserDetails`; the Spring Security LDAP provider can place this object into `Authentication.getPrincipal()` after successful authentication.

**`mapUserToContext(...)`** is the reverse direction: populating attributes from a `UserDetails` into a `DirContextAdapter`, typically related to user management such as `LdapUserDetailsManager`. **LDAP login does not automatically call this method to write users back to the directory.** If a mapper only supports authentication and intentionally does not support directory modification, fail explicitly when this method is called rather than silently writing wrong attributes.

Built-in mappers provided by Spring Security include `LdapUserDetailsMapper`, `InetOrgPersonContextMapper`, and `PersonContextMapper`. Prefer these built-in implementations when custom attributes are not needed; only write a custom mapper if the application's principal model requires extra fields or explicit rules.

## 3. Directory attributes commonly mapped into the principal

Attribute names depend on the organization's LDAP/AD schema; the same concept may have different names.

| Attribute | Where commonly seen | Usage in principal | Notes |
| --- | --- | --- | --- |
| `uid` | LDAP, `inetOrgPerson` | Local login name | Not present by default in AD; can be renamed |
| `cn` | LDAP/AD | Common name, entry name | Not guaranteed unique across the entire system |
| `displayName` | LDAP/AD | Display name in UI | Metadata only; does not grant permissions |
| `givenName`, `sn` | LDAP/AD | First name and surname | May be missing or formatted inconsistently |
| `mail` | LDAP/AD | Email for display/contact | May be null, changed, or non-unique |
| `department` / `departmentNumber` | Schema-dependent | Department information | Organization-specific definition; do not auto-infer roles |
| `sAMAccountName` | AD | Windows-compatible login name | Typically unique only within one domain |
| `userPrincipalName` | AD | Login name in `user@domain` form | Email-like format, though not necessarily an email address |
| `memberOf` | LDAP/AD depending on schema | Group membership data | Multi-valued; may not represent all nested groups |
| DN / `distinguishedName` | LDAP/AD | Entry position in directory tree | DN can change when the entry is moved/renamed |
| `objectGUID` or `objectSid` | AD | Identifier for system linking where appropriate | Has binary/special representation; do not force straight into UTF-8 strings |

Example LDAP entry (illustrative data):

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Pham
sn: Pham
givenName: Lan
displayName: Lan Pham
mail: lan@example.org
departmentNumber: 42
```

The result can be a principal containing:

```text
username    = lan
displayName = Lan Pham
email       = lan@example.org
authorities = [ROLE_READER]
```

Here `ROLE_READER` is an authority **granted by the provider/policy**, not inferred from `mail` or `departmentNumber` in the sample.

### Reading attributes with Spring LDAP

`DirContextOperations.getStringAttribute(name)` returns the first string value or `null` when absent. For multi-valued attributes such as `memberOf`, use `getStringAttributes(name)` if all values are needed; the result can be `null` when the attribute does not exist. Binary values such as certain AD ID formats require appropriate APIs and conversions.

`getDn()` on `DirContextAdapter` represents the DN **relative to the base**; when the full namespace name is needed, look at `getNameInNamespace()` and the actual lookup context. Avoid manually concatenating DN strings as a principal key. Fields usually need optional/null-handling because LDAP access permissions, schemas, and query filters can cause attributes to be missing.

## 4. Complete Java 17+ example: mapping a directory entry to a custom principal

This example **does not require an LDAP server**. We create a `DirContextAdapter` simulating retrieved data, pass in an existing list of authorities, and observe the resulting `UserDetails`. That way, mapper logic can be tested precisely without depending on the network or AD.

Create a minimal Gradle project:

```groovy
// build.gradle
plugins {
    id 'java'
    id 'application'
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
    implementation 'org.springframework.security:spring-security-ldap:6.5.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.DirectoryMapperDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Security LDAP brings in the dependencies needed for the mapper and Spring LDAP. In a real Spring Boot application, use Boot's corresponding BOM/version management instead of manually mixing different Spring versions.

Create `src/main/java/demo/DirectoryMapperDemo.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.ldap.userdetails.UserDetailsContextMapper;

public final class DirectoryMapperDemo {

    private DirectoryMapperDemo() {}

    // Immutable principal: data the application needs after LDAP authentication finishes.
    public record DirectoryPrincipal(
            String username,
            String displayName,
            String email,
            Collection<? extends GrantedAuthority> permissions
    ) implements UserDetails {

        public DirectoryPrincipal {
            Objects.requireNonNull(username, "username");
            Objects.requireNonNull(permissions, "permissions");
            permissions = List.copyOf(permissions);
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return permissions;
        }

        @Override
        public String getUsername() {
            return username;
        }

        @Override
        public String getPassword() {
            return null; // Authenticated via LDAP bind; do not store password in principal.
        }

        @Override
        public boolean isAccountNonExpired() {
            return true;
        }

        @Override
        public boolean isAccountNonLocked() {
            return true;
        }

        @Override
        public boolean isCredentialsNonExpired() {
            return true;
        }

        @Override
        public boolean isEnabled() {
            return true;
        }
    }

    // Only maps read data after authentication; does not perform LDAP updates.
    public static final class DirectoryUserMapper implements UserDetailsContextMapper {

        @Override
        public UserDetails mapUserFromContext(
                DirContextOperations ctx,
                String username,
                Collection<? extends GrantedAuthority> authorities) {

            Objects.requireNonNull(ctx, "ctx");
            Objects.requireNonNull(username, "username");
            Objects.requireNonNull(authorities, "authorities");
            if (username.isBlank()) {
                throw new IllegalArgumentException("Missing login username");
            }

            String displayName = valueOr(
                    ctx.getStringAttribute("displayName"), username);
            String email = valueOr(ctx.getStringAttribute("mail"), "");

            // Keep the authorities prepared by the provider;
            // never self-grant ADMIN based on display attributes.
            return new DirectoryPrincipal(username, displayName, email, authorities);
        }

        @Override
        public void mapUserToContext(UserDetails user, DirContextAdapter ctx) {
            throw new UnsupportedOperationException(
                    "Read-only authentication mapper");
        }

        private static String valueOr(String value, String fallback) {
            return value == null || value.isBlank() ? fallback : value.trim();
        }
    }

    public static void main(String[] args) {
        var entry = new DirContextAdapter(
                "uid=lan,ou=people,dc=example,dc=org");
        entry.setAttributeValue("uid", "lan");
        entry.setAttributeValue("displayName", "Lan Pham");
        entry.setAttributeValue("mail", "lan@example.org");

        var authorities = List.of(
                new SimpleGrantedAuthority("ROLE_READER"));

        var mapper = new DirectoryUserMapper();
        var user = (DirectoryPrincipal)
                mapper.mapUserFromContext(entry, "lan", authorities);

        System.out.println("username=" + user.getUsername());
        System.out.println("displayName=" + user.displayName());
        System.out.println("email=" + user.email());
        System.out.println("authorities=" + user.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority).toList());
    }
}
```

From the directory containing `build.gradle`, run `gradle run` (or `./gradlew run` / `gradlew.bat run` if the project has a Gradle Wrapper). The **program stdout** is:

```text
username=lan
displayName=Lan Pham
email=lan@example.org
authorities=[ROLE_READER]
```

This is the deterministic output from the sample data and `println` statements; Gradle may display additional build logs outside the program's stdout.

**Explanation of the design choices in the example:**

- Uses the `username` received by the mapper rather than forcing `displayName` to serve as the login. Production systems need clear policies for canonical usernames and stable IDs.
- `getPassword()` returns `null` because the example uses **LDAP bind** and does not read passwords. Do not reuse this principal with `DaoAuthenticationProvider`, which requires a password on `UserDetails` to verify.
- Permissions in `permissions` are defensively copied as an immutable list, preventing external code from accidentally mutating the authority list after creation.
- The four account status flags are hardcoded to `true` **solely to isolate learning mapping**; in a real application, disabled/locked/expired policies must be determined from the directory and provider rather than relying on these placeholder values.
- `mapUserToContext` explicitly rejects writes. If the application genuinely has LDAP update functionality, it needs a write mapper with an attribute allowlist, authorization, and dedicated testing.
- Additional fields such as email and display name can be used for display; they must never be taken as proof of identity or a reason to grant permissions.

## 5. Testing missing fields, authorities, and read-only mode

Create `src/test/java/demo/DirectoryMapperDemoTest.java`:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class DirectoryMapperDemoTest {

    private final DirectoryMapperDemo.DirectoryUserMapper mapper =
            new DirectoryMapperDemo.DirectoryUserMapper();

    @Test
    void mapsExpectedAttributesAndPreservesAuthorities() {
        var entry = new DirContextAdapter();
        entry.setAttributeValue("displayName", "  Lan Pham  ");
        entry.setAttributeValue("mail", "lan@example.org");

        var user = (DirectoryMapperDemo.DirectoryPrincipal)
                mapper.mapUserFromContext(entry, "lan",
                        List.of(new SimpleGrantedAuthority("ROLE_READER")));

        assertEquals("lan", user.getUsername());
        assertEquals("Lan Pham", user.displayName());
        assertEquals("lan@example.org", user.email());
        assertEquals("ROLE_READER",
                user.getAuthorities().iterator().next().getAuthority());
    }

    @Test
    void missingOptionalAttributesDoNotCreateFakeIdentity() {
        var user = (DirectoryMapperDemo.DirectoryPrincipal)
                mapper.mapUserFromContext(new DirContextAdapter(), "lan", List.of());

        assertEquals("lan", user.getUsername());
        assertEquals("lan", user.displayName());
        assertEquals("", user.email());
        assertTrue(user.getAuthorities().isEmpty());
    }

    @Test
    void writeBackIsExplicitlyUnsupported() {
        var user = mapper.mapUserFromContext(
                new DirContextAdapter(), "lan", List.of());

        assertThrows(UnsupportedOperationException.class,
                () -> mapper.mapUserToContext(user, new DirContextAdapter()));
    }
}
```

Run `gradle test` or `./gradlew test` when using a wrapper. The three tests respectively verify attribute mapping, fallback when data is missing, and disallowing directory writes. **Note:** these are mapper unit tests, not real LDAP/AD authentication integration tests; they do not verify TLS, bind, group lookup, or server-side account status.

## 6. Attaching the mapper to Spring Security LDAP or AD

The mapper is only used during real logins when attached to the right `AuthenticationProvider` or factory creating `AuthenticationManager`.

### 6.1. LDAP bind using LdapBindAuthenticationManagerFactory

In Spring Security 6.x, this factory has `setUserDetailsContextMapper(...)` inherited from `AbstractLdapAuthenticationManagerFactory`.

```java
// Configuration snippet inside a @Configuration of a Spring MVC application:
@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {

    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    factory.setUserDetailsContextMapper(
            new DirectoryMapperDemo.DirectoryUserMapper());

    return factory.createAuthenticationManager();
}
```

Related imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
```

This is **only an integration snippet**; it requires a `BaseLdapPathContextSource` configured with URL/base DN, query account (if needed), TLS, and a Spring Security filter chain properly using the authentication manager. `(uid={0})` is only meaningful if the real directory uses `uid`; AD usually uses another search attribute. Configure an `LdapAuthoritiesPopulator` if the application derives permissions from groups and does not accept an identity without roles.

**Execution result:** after `BindAuthenticator` authenticates and retrieves user data, the factory/provider invokes the mapper; `Authentication.getPrincipal()` will be `DirectoryPrincipal` if configuration and authentication succeed.

### 6.2. With Active Directory

```java
// Example placed in a @Configuration that already has DirectoryUserMapper:
@Bean
ActiveDirectoryLdapAuthenticationProvider adProvider() {
    var provider = new ActiveDirectoryLdapAuthenticationProvider(
            "corp.example.org", "ldaps://ad.corp.example.org:636/");
    provider.setUserDetailsContextMapper(
            new DirectoryMapperDemo.DirectoryUserMapper());
    return provider;
}
```

Import: `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`.

The AD provider follows `userPrincipalName` (`user@domain`) login conventions and usually retrieves authorities from `memberOf`. Changing the mapper **does not alter the bind mechanism**, nor does it automatically guarantee nested groups or trusted domain permissions are resolved; when needed, configure an authority populator/mapper and test against real data. The URL/domain above are illustrative and cannot be used to log in without a real AD.

## 7. Reading the principal at the application layer

Once an HTTP request is authenticated, controller code in **Spring MVC/Servlet** can retrieve the principal via `@AuthenticationPrincipal` or from `Authentication`. When the provider uses the custom mapper above, the runtime type is typically `DirectoryPrincipal`.

```java
// Illustrative handler snippet, only works when the system has configured the LDAP provider.
@GetMapping("/me")
public Map<String, String> me(
        @AuthenticationPrincipal DirectoryMapperDemo.DirectoryPrincipal principal) {
    return Map.of(
            "username", principal.getUsername(),
            "displayName", principal.displayName(),
            "email", principal.email());
}
```

Imports for this snippet: `java.util.Map`, `org.springframework.web.bind.annotation.GetMapping`, `org.springframework.security.core.annotation.AuthenticationPrincipal`. Because the example mapping converts missing email to an empty string, `Map.of` will not receive a null value. In real applications, restrict which fields are returned in APIs based on authorization and purpose; avoid exposing DNs, internal groups, or unnecessary HR data.

Do not cast every `Authentication.getPrincipal()` to the custom class if the application supports multiple login mechanisms; with JWT/OIDC or anonymous access, the principal type can differ. With `@AuthenticationPrincipal`, restrict the handler with the corresponding security chain/policy or handle types safely.

**Regarding WebFlux:** Spring Security LDAP providers/JNDI typically use synchronous APIs. Do not make blocking LDAP calls directly on the WebFlux event loop; if reactive authentication is needed, design appropriate blocking execution offloading and consistent security context management. The mapper remains a Spring Security LDAP module concept and does not automatically turn LDAP lookups into `Mono` or `ReactiveUserDetailsService`.

## 8. When do you not need a custom mapper?

| Need | Approach |
| --- | --- |
| Only need username and authorities from LDAP | Look at the provider's default `LdapUserDetailsMapper` |
| Need `inetOrgPerson` principal fields like name, address, email | Look at `InetOrgPersonContextMapper` |
| `person`-compatible schema | Look at `PersonContextMapper` |
| Need custom HR fields, stable internal ID, or restricted sensitive data | A thoroughly tested custom `UserDetailsContextMapper` |
| Only want to add/remove roles while keeping the current principal type | Configure `LdapAuthoritiesPopulator` / `GrantedAuthoritiesMapper`; no need to replace the principal mapper |
| Want to edit accounts in LDAP | Consider `LdapUserDetailsManager` and bidirectional mapping; protect write permissions separately |

`LdapUserDetailsMapper` has options such as `setPasswordAttributeName`, `setRoleAttributes`, `setRolePrefix`, and `setConvertToUpperCase`; they are useful if the schema and role policies fit. However, **never read or retain passwords merely to enrich the principal** when using LDAP bind.

## 9. Common errors and how to analyze them

**Error 1 — Mapper does not run despite declaring `@Bean`.** Declaring a bean does not mean every LDAP provider automatically uses it. Check that configuration calls `setUserDetailsContextMapper(...)`, that the LDAP provider/factory is wired into the right authentication manager, and that requests hit the right filter chain.

**Error 2 — Mapper is invoked, yet `mail` and `displayName` are null.** Check the schema, user search filter, attribute read permissions, and `attributesToReturn` of the lookup. AD may use different attribute names. If optional info is missing, apply safe fallbacks; do not guess email addresses from the login without a verified rule.

**Error 3 — Principal loses roles after mapping.** The `authorities` parameter is the list provided by the authority-loading component; if a custom mapper discards it, the application may hit 403 even after successful authentication. Do not fix this by defaulting to `ROLE_ADMIN`. Inspect group search/authority loading and role bindings.

**Error 4 — Mapping `memberOf` to a single role via `getStringAttribute`.** The group attribute can be multi-valued and holds DNs, not direct Spring authority names. Handle multiple values, nested groups as required, controlled mapping rules, and test unknown or deleted groups.

**Error 5 — Using email, `cn`, or display name as a permanent user key.** These can change, collide, or be updated by HR processes. In AD, dedicated identifiers like GUID/SID have special representations; key selection must stay consistent with domain/forest scope, account-linking rules, and security requirements.

**Error 6 — Verifying passwords yourself inside the mapper.** `UserDetailsContextMapper` creates a principal from the retrieved entry; never read the user's password or `userPassword` to match it again. This also avoids exposing hashed secrets, plaintext passwords, or misrouted credentials.

**Error 7 — Equating account status with the `true` flags in the demo.** Active Directory has disabled, expired, and locked accounts, plus specific bind errors/sub-errors. Real applications must rely on verified provider/directory policies; never treat the mapper returning `isEnabled() == true` as proof that an AD account is valid.

**Error 8 — Wanting to update LDAP while the mapper is read-only.** `mapUserToContext` in the example intentionally throws `UnsupportedOperationException`. If user management is needed, clearly define writable attributes, required transactions/rollback mechanisms, service account permissions, and data protection.

**Error 9 — Dumping the entire directory entry into responses or logs.** Entries may contain email addresses, phone numbers, organizational attributes, and group details. Map only authorized business fields; never put credentials/secrets or raw directory attributes into logs.

**Error 10 — Running LDAP over an insecure connection.** Use proper LDAPS or StartTLS, validate the server certificate, control timeouts/referrals, and restrict bind account permissions. A correct mapper alone cannot protect authentication data in transit over the network.

## 10. Process for designing a mapper in a real project

1. Identify the LDAP/AD schema and the **source of truth** for username, stable ID, display name, email, account status, and group membership.
2. Decide which attributes the application needs in the principal, their purpose, and their sensitivity; avoid carrying the entire entry into sessions/tokens.
3. Prefer built-in `LdapUserDetailsMapper`/`InetOrgPersonContextMapper`, and write a custom mapper only when a genuinely different contract is required.
4. Configure the provider/factory to invoke the mapper while keeping proper bind and authority loading mechanisms. Clearly define who controls group → Spring role mapping.
5. Unit test the mapper with complete, missing, multi-valued, renamed, and empty-authority inputs. Never create roles from untrusted attributes.
6. Integration test against a test directory: valid/failed logins, locked/disabled accounts, attribute read permissions, membership changes, sessions/caches, and API responses returning only permitted data.
7. For LDAP write-back needs, build dedicated management and authorization controls; never let the authentication path accidentally modify the directory.

### Official documentation

- Spring Security 6.5 — LDAP Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html
- `UserDetailsContextMapper` and built-in mappers: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/ldap/userdetails/package-summary.html
- `LdapUserDetailsMapper` (API): https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/ldap/userdetails/LdapUserDetailsMapper.html
- `AbstractLdapAuthenticationManagerFactory` (API): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html
- `ActiveDirectoryLdapAuthenticationProvider` (API): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring LDAP — `DirContextAdapter` (API): https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html
