# Loading User Permissions After Verifying a Kerberos Principal in Spring Security

> **Topic:** Spring Security – federation. **Group:** Kerberos Integration. This Knowledge lesson explains how to feed a **GSS/SPNEGO-verified Kerberos principal** into Spring Security's account and permission loading flow, focusing on `KerberosServiceAuthenticationProvider`, `UserDetailsService`, Active Directory/LDAP, databases, `GrantedAuthority`, tenant isolation, caching, and permission revocation. Java 17+ examples clearly distinguish standalone programs from Spring configurations requiring a real Kerberos realm and keytab.

## 1. Kerberos Authenticates the User, Not Business Permissions

When a browser completes an SPNEGO login, an HTTP service can verify the ticket and learn:

~~~text
Verified client principal:
  alice@EXAMPLE.ORG
Target service:
  HTTP/portal.example.org@EXAMPLE.ORG
Authentication mechanism:
  Kerberos v5 through GSS/SPNEGO
~~~

That **does not by itself prove** Alice is allowed to:
- View every report.
- Approve financial transactions.
- Access another tenant's data.
- Use an application account that has been locked.
- Receive administrative privileges just for belonging to a Windows domain.
- Retain permissions after an AD group membership has been revoked.

**Core boundaries:**
- **Authentication** answers: *Which identity proved possession of a valid Kerberos credential?*
- **Identity lookup** answers: *Which internal account does this principal map to, and is the account allowed to use the application?*
- **Authority loading** answers: *From approved groups, roles, and policies, which `GrantedAuthority` values is the account granted?*
- **Authorization** answers: *For a specific resource and tenant, is the current action permitted?*

Spring Security Kerberos provides the exact extension point for this step: `KerberosServiceAuthenticationProvider.setUserDetailsService(UserDetailsService)`. Per Spring's JavaDoc, the provider needs a UserDetailsService to load user properties and `GrantedAuthorities`, because Kerberos validation fundamentally returns a username/principal rather than business permissions.

## 2. Process Diagram: Ticket First, Permissions After

~~~text
Browser / workstation with Kerberos credential cache
       |
       | GET /reports/42
       v
Spring Security protected route
       |
       | 401 Unauthorized
       | WWW-Authenticate: Negotiate
       v
Browser/GSS-API requests service ticket for HTTP SPN
       |
       | Authorization: Negotiate <GSS token>
       v
SpnegoAuthenticationProcessingFilter
       |
       v
AuthenticationManager / ProviderManager
       |
       v
KerberosServiceAuthenticationProvider
       |
       +-- KerberosTicketValidator
       |      |
       |      +-- HTTP service keytab
       |      +-- Ticket/SPN/Authenticator/session key
       |      +-- Time, replay, integrity, realm checks
       |      |
       |      v
       |   Verified principal: alice@EXAMPLE.ORG
       |
       +-- UserDetailsService.loadUserByUsername(principal)
              |
              +-- Trusted local/AD/LDAP identity lookup
              +-- Account active/locked/expired policy
              +-- Group/entitlement lookup
              +-- Stable group ID -> app-role allowlist
              +-- Tenant membership/account mapping
              |
              v
          UserDetails + GrantedAuthority collection
       |
       v
Authenticated Spring Authentication
       |
       v
SecurityContext / AuthorizationFilter / Method Security
       |
       v
Tenant + resource-level decision: ALLOW / DENY
~~~

**Never reverse the order** by taking `X-User`, a `username` query parameter, or a string extracted from unverified Base64 and calling UserDetailsService to construct an Authentication yourself.

## 3. Spring Security Classes You Need to Know

| API | Role |
|---|---|
| `SpnegoEntryPoint` | Emits 401 challenge with `WWW-Authenticate: Negotiate` |
| `SpnegoAuthenticationProcessingFilter` | Receives HTTP Negotiate token and passes it to AuthenticationManager |
| `KerberosServiceRequestToken` | Authentication token carrying Kerberos/SPNEGO bytes to verify |
| `KerberosTicketValidator` | Interface validating Kerberos service tickets |
| `SunJaasKerberosTicketValidator` | JAAS/GSS ticket validator using service principal and keytab |
| `KerberosTicketValidation` | Ticket validation outcome, including the verified identity per API |
| `KerberosServiceAuthenticationProvider` | Verifies token then loads user properties/authorities |
| `UserDetailsService` | Looks up user from verified principal/username |
| `UserDetails` | Account identity, status, authorities |
| `GrantedAuthority` | A Spring authority usable in authorization |
| `SimpleGrantedAuthority` | Common implementation for an authority string |
| `SecurityContextHolder` | Accesses the current Spring Authentication |
| `AuthorizationManager` | Enforces permissions at HTTP/method layers |
| `@PreAuthorize` | Method security annotation evaluated against Authentication |
| `ProviderManager` | Coordinates matching AuthenticationProviders |

**Two distinct authentication providers:**
- `KerberosServiceAuthenticationProvider` handles **incoming SPNEGO service tickets**, fitting browser Kerberos SSO.
- `KerberosAuthenticationProvider` handles username/password via a Kerberos client. Do not add this password provider just to read roles after SPNEGO.
- `ActiveDirectoryLdapAuthenticationProvider` is a separate authentication provider; if you only need AD groups after Kerberos, use a directory lookup **without forcing the user to enter a password for an LDAP bind**.

## 4. What Does the Kerberos Validator Verify and Leave for the App?

In Kerberos HTTP Negotiate:
1. The browser holds a TGT or credentials via OS/SSPI/GSS-API.
2. The client requests a service ticket for an SPN, e.g., `HTTP/portal.example.org@EXAMPLE.ORG`.
3. The browser sends a token carrying AP-REQ/service ticket and Authenticator.
4. The service uses its keytab to process the encrypted ticket part and GSS context.
5. The verifier checks cryptographic integrity, session key proof, timestamps, replay, and realm/SPN policy.
6. The outcome is an authenticated Kerberos client principal.

**Kerberos does not determine** whether a local account is active, which app roles the user holds, or which tenant's reports the user may view. Nor does a service ticket automatically carry AD groups under a portable contract for Spring to map business roles. Every business authority must come from an **approved source** after validation.

### 4.1. Can the Raw HTTP Negotiate Header Be Trusted?

No. The header is merely unvalidated input. Let the framework/GSS process it:
- Do not Base64-decode and read the username yourself.
- Do not read arbitrary claims out of an unsigned/unverified token.
- Do not create a local session before the Kerberos provider returns a successful Authentication.
- Do not accept `X-Remote-User` from a client as Kerberos proof.

If a TLS reverse proxy verifies Kerberos itself and forwards only an internal principal header, that is **a different pre-authenticated architecture**, requiring mTLS/network isolation/header stripping and its own trust policy; the backend must not claim it directly verified the Kerberos ticket if it only reads a header.

## 5. Principals Must Keep Realm and Namespaced Identity

Example of two principals:

~~~text
alice@EXAMPLE.ORG
alice@PARTNERS.ORG
~~~

These two principals may be completely different people. Never do:

~~~java
// UNSAFE in multi-realm environments.
String localUserId = verifiedPrincipal.split("@")[0];
~~~

Reasons:
- The Kerberos realm is part of the namespace.
- AD `sAMAccountName` is not unique across all trusted domains.
- Email, short username, and UPN aliases can change or be reused.
- Cross-realm trust lets principals from other realms authenticate to some services, yet **does not grant local app access automatically**.
- A multi-tenant application must especially avoid merging users by short name.

### 5.1. External Identity Key

Define the concept clearly:

~~~text
IdentityLinkKey:
  mechanism = KERBEROS
  trustedRealm = EXAMPLE.ORG
  verifiedPrincipal = alice@EXAMPLE.ORG
  optionalDirectoryObjectId = objectGUID/objectSID
  optionalTenantScope = team-a
~~~

This is a **recommended application model**, not a built-in Spring object. Only an approved mapping translates the external identity to a localUserId.

### 5.2. How Should Usernames Be Canonicalized?

- Prefer the **exact verified principal** for lookup.
- If applying case normalization/realm alias mapping, follow documented KDC/directory rules rather than calling `toLowerCase()` across everything and ignoring collisions.
- With AD, you can query by UPN to retrieve `objectGUID`, `objectSID`, or a stable directory ID and link the local account by that ID.
- Never merge two realms just because both say `alice`.
- If lookup returns multiple directory entries, **fail closed** instead of picking the first record.

## 6. UserDetailsService Is the Primary Extension Point

Basic signature:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

This signature illustrates the existing Spring Security interface; no new declaration is needed in your project.

In Kerberos integration:
- `username` is the name verified by the ticket validator, e.g., `alice@EXAMPLE.ORG`.
- UserDetailsService queries the account and permissions, returning `UserDetails` with `getAuthorities()`.
- `KerberosServiceAuthenticationProvider` coordinates the validator and UserDetailsService in the authentication pipeline.
- If the principal is unprovisioned, `UsernameNotFoundException` is an appropriate rejection path.
- If the directory fails, never fall back to granting strong roles; preserve the error/fail closed per policy.

### 6.1. UserDetailsService Does Not Authenticate Kerberos

It does not need:
- User passwords.
- The user's TGT.
- The service's keytab file to read groups.
- Raw SPNEGO tokens.
- SAML Assertions, JWTs, or OIDC claims.

The Kerberos verifier handles authentication; UserDetailsService handles identity/authority lookup. Whether the directory API uses its own LDAP credentials or Kerberos SASL bind is a directory connectivity concern, **separate** from verifying the HTTP ticket.

### 6.2. Account Status Must Be Explicitly Enforced

Lookup results should enforce policies for:
- Missing account.
- Disabled/suspended account.
- Locked account.
- Expired account.
- Revoked local identity link.
- Disabled tenant membership.
- Ungranted permissions.
- Previously granted permissions that expired.

Do not assume every Kerberos provider runs all checkers identically to `DaoAuthenticationProvider`. To be safe, the service/policy can **reject immediately inside UserDetailsService** when an account is disabled/locked, backed by integration tests on your actual Kerberos version. If the provider offers native account checks, use the proper extension point rather than assuming.

## 7. Sources of Permissions After Kerberos

| Source | Appropriate Information | Notes |
|---|---|---|
| Local relational DB | Local user ID, roles, tenant memberships, account status | Indexed exact identity key, unique constraints |
| Active Directory | objectSID/objectGUID, memberships, account flags | Nested groups, trusted forests, stable identifiers |
| LDAP directory | Groups, attributes, application directory user | Separate LDAP schema and escaping/LDAPS |
| IAM/entitlement API | Roles, permissions, policy version | Trusted service authentication/availability |
| Cached roles | Permission snapshot within TTL | Explicit revocation/invalidation |
| In-memory fixture | Demo/test | Not a production permission source |
| HTTP request headers | Not a direct role source | Client spoofing risk |
| Kerberos ticket bytes | Authentication proof only, not a business role source | GSS validation mandatory |

**Notably:** if the application controls permissions, not every app role has to originate from an AD group. AD can establish user identity while report-approval roles live in the database.

## 8. Group-to-Authority Mapping Must Use an Allowlist

Authoritative policy example:

| Trusted Realm | Stable Directory Group ID | Tenant | Spring Authority |
|---|---|---|---|
| EXAMPLE.ORG | G-REPORT-READ | team-a | ROLE_REPORT_VIEW |
| EXAMPLE.ORG | G-REPORT-APPROVE | team-a | ROLE_REPORT_APPROVE |
| EXAMPLE.ORG | G-FINANCE-READ | finance | ROLE_FINANCE_VIEW |
| PARTNERS.ORG | Similarly named group | team-a | Not granted by default |
| Any other realm | Client-supplied ROLE_ADMIN string | Any | Not granted |

An AD group named `GG-FinanceReaders` is not automatically `ROLE_ADMIN` or `ROLE_REPORT_VIEW`. Use **stable group SID/ID** wherever possible, since display names can change or collide. Map only administratively approved groups/roles.

### 8.1. Do Not Copy Every LDAP Group into GrantedAuthority

Anti-pattern:

~~~java
// UNSAFE: trusting arbitrary group text as application permissions.
String role = "ROLE_" + ldapGroupName;
GrantedAuthority grant = new SimpleGrantedAuthority(role);
~~~

If a group name contains "Admin" or is renamed unexpectedly, permissions break. Require approved exact-ID mappings, realm/tenant scoping, and grant nothing when no mapping matches.

### 8.2. Nested Groups in AD

A user may belong to group A, and group A belongs to group B. Querying direct `memberOf` may not return all effective memberships the application expects. Determine:
- Whether transitive groups are needed.
- Whether `tokenGroups`, matching-rule-in-chain, or a pre-computed IAM membership source is used.
- How cross-domain/cross-forest trusted groups are handled.
- Whether group SIDs and principals are bound to the proper realm/tenant.
- Query limits, timeouts, cycles, and caching behavior.

Avoid inferring permissions from a group list string supplied by the browser.

## 9. Separating Authentication from Authorization in Spring

### 9.1. hasAuthority

~~~java
.requestMatchers("/reports/**")
    .hasAuthority("ROLE_REPORT_VIEW")
~~~

Spring checks the exact authority string on Authentication.

### 9.2. hasRole

~~~java
.requestMatchers("/reports/**")
    .hasRole("REPORT_VIEW")
~~~

With the default role prefix, `hasRole("REPORT_VIEW")` typically requires authority `ROLE_REPORT_VIEW`. Do not pass `hasRole("ROLE_REPORT_VIEW")` when the default prefix would prepend `ROLE_` again. If the project customizes the role prefix, apply a consistent policy and verify with tests.

### 9.3. Resource-Level Authorization

A user holding `ROLE_REPORT_VIEW` is not automatically allowed to view every report. The application must verify:
- Which tenant owns the report?
- Does the user have an active membership in that tenant?
- Resource owner/classification/access level?
- Is READ access restricted by department or project?
- Is step-up/MFA/fresh login required for the specific action?
- Was the local account or entitlement recently revoked?

With method security:
~~~java
@PreAuthorize("hasAuthority('ROLE_REPORT_VIEW')")
public ReportDto getReport(String tenantId, String reportId) {
    // Method fragment: needs real repository, authorizer, and types.
    return reportService.getOnlyIfAuthorized(tenantId, reportId);
}
~~~

Crucial point: `getOnlyIfAuthorized` **must check the resource's tenant and specific permissions**; the method annotation is only a preliminary guard.

## 10. Standalone Java 17: Simulating Safe Authority Lookup

The program below **runs on JDK 17+ without Spring/KDC**. It assumes the principal was already verified beforehand, then loads the local account and maps an allowlisted group set to permissions. Its purpose is clarifying business authorization, **not replacing ticket validation**.

File `KerberosAuthorityDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class KerberosAuthorityDemo {

    record Account(
            String principal,
            String tenant,
            boolean active,
            Set<String> groups) {
    }

    private static final Map<String, Account> ACCOUNTS = Map.of(
            "alice@EXAMPLE.ORG",
            new Account("alice@EXAMPLE.ORG", "team-a", true,
                    Set.of("G-READ", "UNTRUSTED-ADMIN")),
            "bob@EXAMPLE.ORG",
            new Account("bob@EXAMPLE.ORG", "team-a", false,
                    Set.of("G-APPROVE"))
    );

    private static final Map<String, String> GROUP_ROLES = Map.of(
            "G-READ", "ROLE_REPORT_VIEW",
            "G-APPROVE", "ROLE_REPORT_APPROVE"
    );

    static Set<String> authorities(
            String verifiedPrincipal, String trustedTenant) {
        Account a = ACCOUNTS.get(verifiedPrincipal);
        if (a == null || !a.active()
                || !a.tenant().equals(trustedTenant)) {
            return Set.of();
        }
        return a.groups().stream()
                .map(GROUP_ROLES::get)
                .filter(s -> s != null)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    public static void main(String[] args) {
        System.out.println("alice-read="
                + authorities("alice@EXAMPLE.ORG", "team-a")
                    .contains("ROLE_REPORT_VIEW"));
        System.out.println("alice-admin="
                + authorities("alice@EXAMPLE.ORG", "team-a")
                    .contains("ROLE_ADMIN"));
        System.out.println("bob-approve="
                + authorities("bob@EXAMPLE.ORG", "team-a")
                    .contains("ROLE_REPORT_APPROVE"));
        System.out.println("cross-tenant="
                + authorities("alice@EXAMPLE.ORG", "team-b")
                    .contains("ROLE_REPORT_VIEW"));
        System.out.println("other-realm="
                + authorities("alice@PARTNERS.ORG", "team-a")
                    .contains("ROLE_REPORT_VIEW"));
    }
}
~~~

Compile/run:

~~~bash
javac KerberosAuthorityDemo.java
java KerberosAuthorityDemo
~~~

**Exact stdout:**

~~~text
alice-read=true
alice-admin=false
bob-approve=false
cross-tenant=false
other-realm=false
~~~

**Explanation:**
1. Alice has approved group G-READ, so she receives report-view permission.
2. Group `UNTRUSTED-ADMIN` is not on the allowlist and never turns into ROLE_ADMIN.
3. Bob has the approve group yet his account is inactive, so he gets no permissions.
4. Tenant team-b differs from the account's assigned tenant, yielding no permissions.
5. Same short name alice in another Kerberos realm does not match the identity.

**Limitations:** This program does not verify AP-REQ or read a keytab, and `authorities(...)` must never be used to create an authenticated session from an HTTP parameter. It illustrates lookup **after** authentication only. Avoid printing a `Set` directly to stdout so output does not depend on hash iteration order.

## 11. Spring Security Kerberos: Configuring Provider and User Lookup

This lesson uses a Servlet application with Spring Security Kerberos dependencies compatible with Spring Security Core. The classes below are **integration code**, not runnable standalone with `javac` because framework jars, KDC, keytab, HTTP SPN, and browser Kerberos config are required.

File `src/main/java/com/example/security/KerberosSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator() {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.example.org@EXAMPLE.ORG");
        validator.setKeyTabLocation(new FileSystemResource(
                "/run/secrets/portal-http.keytab"));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {
        AuthenticationManager manager = new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
                new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/reports/**")
                    .hasAuthority("ROLE_REPORT_VIEW")
                .requestMatchers("/approve/**")
                    .hasAuthority("ROLE_REPORT_APPROVE")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationManager(manager)
            .addFilterBefore(filter, BasicAuthenticationFilter.class)
            .build();
    }
}
~~~

### 11.1. Configuration Analysis

- `SunJaasKerberosTicketValidator` is the cryptographic verifier using the **HTTP service's** keytab, not user passwords.
- `KerberosServiceAuthenticationProvider.setUserDetailsService` handles **loading permissions after Kerberos validation**.
- `SpnegoAuthenticationProcessingFilter` reads the Negotiate token, not role request parameters.
- `SpnegoEntryPoint` challenges unauthenticated users.
- `ProviderManager` holds the provider for Kerberos service tokens.
- `SecurityFilterChain` enforces authorities by HTTP path.
- The code intentionally omits DaoAuthenticationProvider/form password login; if the project needs a fallback, design a separate flow with its own security controls.
- The filter is instantiated inside SecurityFilterChain, preventing duplicate Servlet Filter registration from Spring Boot scanning `@Bean` Filters.
- Test against your exact Spring Security/Spring Security Kerberos release, especially filter ordering and SecurityContext persistence.

### 11.2. Maven Dependencies

This is a fragment inside a POM already configured with a Spring Boot parent/BOM, not a standalone POM:

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
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
  </dependency>
</dependencies>
~~~

The Spring Security Kerberos module version and Spring Core/Boot must be compatible; never guess a version arbitrarily. You still need a keytab secret mount, KDC, realm/DNS/clock config, SPN service account, and browser policy to run end-to-end. Never place keytabs in Git or public images.

## 12. Implementing UserDetailsService to Check Accounts Then Map Permissions

Standalone class example for a Spring Security project accepting a repository interface to avoid hardcoding a DB schema. This is a **complete class-level Java sample**, while the repository implementation and KDC integration depend on runtime.

File `src/main/java/com/example/security/KerberosUsers.java`:

~~~java
package com.example.security;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class KerberosUsers implements UserDetailsService {

    public record Account(
            String fullPrincipal,
            boolean active,
            Set<String> directoryGroups) {
    }

    public interface AccountRepository {
        Account findExactPrincipal(String verifiedPrincipal);
    }

    private static final Map<String, String> GROUP_ROLE = Map.of(
            "G-READ", "ROLE_REPORT_VIEW",
            "G-APPROVE", "ROLE_REPORT_APPROVE");

    private final AccountRepository repository;

    public KerberosUsers(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String principal) {
        if (principal == null || principal.isBlank()) {
            throw new UsernameNotFoundException("Invalid Kerberos principal");
        }

        Account account = repository.findExactPrincipal(principal);
        if (account == null || !account.active()
                || !principal.equals(account.fullPrincipal())) {
            throw new UsernameNotFoundException(
                    "Identity not provisioned or account disabled");
        }

        if (account.directoryGroups() == null) {
            throw new UsernameNotFoundException("Group source unavailable");
        }

        List<GrantedAuthority> grants = account.directoryGroups().stream()
                .map(GROUP_ROLE::get)
                .filter(role -> role != null)
                .distinct()
                .map(role -> (GrantedAuthority)
                        new SimpleGrantedAuthority(role))
                .toList();

        return new KerberosOnlyUser(principal, grants);
    }

    private record KerberosOnlyUser(
            String username,
            List<GrantedAuthority> authorities)
            implements UserDetails {

        @Override
        public String getUsername() {
            return username;
        }

        @Override
        public String getPassword() {
            return null;
        }

        @Override
        public List<GrantedAuthority> getAuthorities() {
            return authorities;
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
}
~~~

### 12.1. Security Properties of the Code

- `findExactPrincipal` must be backed by a trusted directory/DB lookup preserving the realm. It never takes a browser-supplied principal.
- Missing or disabled accounts → rejected immediately. Do not assume a provider automatically runs the same checkers as DaoAuthenticationProvider.
- Null `directoryGroups` represents an **unavailable permission lookup source**, never treated as granting all groups.
- Only groups in `GROUP_ROLE` become authorities.
- `getPassword()` returns null because UserDetails is used **after Kerberos ticket validation**, not for password login. Never pass this object into DaoAuthenticationProvider.
- `isAccountNonLocked`/`isAccountNonExpired` return true in the demo **because the repository model only has `active`**. Production models with locked/expired fields must check them thoroughly before returning UserDetails; never skip account lifecycle checks.
- The code omits tenant handling because `UserDetailsService.loadUserByUsername` takes only a username; tenant-scoped authorization must be enforced separately via trusted membership/resource scopes.
- If the app needs JIT provisioning, treat it as a governed workflow with explicit policy/approval; never auto-create accounts here for arbitrary Kerberos principals.
- The sample omits `@Component`, requiring bean wiring from project configuration.

### 12.2. Bean Wiring Example

~~~java
@Bean
UserDetailsService userDetailsService() {
    KerberosUsers.AccountRepository repository = principal -> {
        if ("alice@EXAMPLE.ORG".equals(principal)) {
            return new KerberosUsers.Account(
                    principal, true, Set.of("G-READ"));
        }
        return null;
    };
    return new KerberosUsers(repository);
}
~~~

This is a **method fragment** inside a Spring `@Configuration` with appropriate imports. It uses an in-memory allowlist to learn the API; production should inject a repository querying DB/AD/LDAP/IAM. Never keep real user lists in source code.

## 13. LDAP/Active Directory Lookup After a Kerberos Ticket

### 13.1. Directory Lookup Differs from LDAP Password Authentication

Once Kerberos has verified the principal, the application can use:
- An LDAP/LDAPS query using a read-only directory service account.
- A SASL/GSSAPI bind using a properly configured service identity.
- An IAM directory API to retrieve group memberships.
- A DB mapping holding stable AD object IDs and app roles.

**No user password is needed to perform an LDAP bind** just to fetch groups. If using `ActiveDirectoryLdapAuthenticationProvider` as a password authentication fallback, separate the two flows cleanly and never mix role maps carelessly.

### 13.2. Mapping Principals to Stable AD Identities

In Active Directory:
- `userPrincipalName` usually holds the UPN, yet can change under admin policy.
- `sAMAccountName` is unique only within a domain scope and easily collides across domains.
- `objectGUID` is a stable directory object ID useful across renames.
- `objectSid` can serve as a stable security ID for accounts/groups.
- Group authorization should prefer stable SIDs/IDs over displayName.
- Cross-domain/forest trusts must be evaluated before linking principals.

### 13.3. LDAP Filters Must Be Escaped or Parameterized

Anti-pattern:

~~~java
// UNSAFE: concatenating principal directly into LDAP filter.
String filter = "(userPrincipalName=" + principal + ")";
~~~

Even though the principal comes from a trusted GSS context, escape it when building LDAP queries; no input is exempt from injection guards. Use LDAP API parameter binding/filter escaping, restrict search base, and verify **strictly one** matching account. SQL must likewise use prepared statements.

### 13.4. Nested Group Memberships

AD `memberOf` does not always represent all effective group memberships across nested groups/foreign trusts. Decide:
- Direct groups only or transitive groups?
- Are `tokenGroups`/matching-rule-in-chain supported in the directory and permitted to read?
- Group caching/TTL?
- Which tenant/realm governs SID mapping?
- Behavior when a group or user is deleted?
- Does directory timeout fail login closed?

Never infer permissions from a group name value appearing anywhere in the directory.

## 14. Database / IAM as the Source of Application Permissions

A design may include tables like:

~~~text
external_identity_link:
    mechanism = KERBEROS
    realm = EXAMPLE.ORG
    full_principal = alice@EXAMPLE.ORG
    local_user_id = 1001
    approved = true

local_user:
    id = 1001
    enabled = true
    locked = false

tenant_membership:
    user_id = 1001
    tenant_id = team-a
    enabled = true

role_assignment:
    user_id = 1001
    tenant_id = team-a
    authority = ROLE_REPORT_VIEW
~~~

From a verified Kerberos principal:
1. Look up the exact identity link.
2. Verify the linked account is approved.
3. Verify the user is active/unlocked/unexpired.
4. Load groups/roles from the authoritative source.
5. Apply tenant membership and policy.
6. Return matching authorities.
7. Upon resource access, check local user + tenant + resource.

This is a **conceptual schema**, not a SQL migration. Production needs unique constraints and indexes on identity keys, auditing of role changes, and transaction/snapshot consistency.

## 15. Multi-Tenant Authorization: Not Just ROLE_REPORT_VIEW

For example, principal Alice holds report-view permission in tenant team-a but does not belong to team-b. If Alice's Authentication carries a global `ROLE_REPORT_VIEW`, calling:

~~~text
GET /tenants/team-b/reports/42
~~~

must be denied during **resource authorization**.

One approach retains:
- Mapped local user ID.
- Policy-governed set of tenant memberships.
- Tenant-scoped role assignments.
- Domain service checking which tenant owns the resource.

Never take the tenant from `X-Tenant` or a query parameter to add authorities to Spring Authentication. In particular, `loadUserByUsername(String)` receives only a username, not an arbitrary `HttpServletRequest`; if tenant context is needed at login, rely on verified routing/provider context rather than a client-controlled ThreadLocal.

### 15.1. Why @PreAuthorize Alone Is Insufficient

~~~java
@PreAuthorize("hasAuthority('ROLE_REPORT_VIEW')")
public Report getReport(String tenant, String reportId) {
    return reportPolicy.readOnlyIfAllowed(tenant, reportId);
}
~~~

This is a method fragment needing implementations and imports. Domain authorization must verify owner/tenant rather than relying solely on role annotations. An authenticated user can still receive HTTP 403 when lacking access to the specific resource.

### 15.2. Enabling Method Security

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

This is a valid Java class fragment once `Configuration` and `EnableMethodSecurity` imports are included in Spring Boot config. Method annotations do not enforce authorization unless the mechanism is enabled.

## 16. Roles in Session, Cache, and Revocation Issues

### 16.1. Permission Snapshot

Spring Authentication usually holds a **snapshot of authorities** captured at login/lookup time. Subsequent requests within the same HttpSession may **not** re-invoke UserDetailsService.

Example:
- 09:00 Alice logs in; the approve group is present, so Authentication holds ROLE_REPORT_APPROVE.
- 10:00 an admin removes the approve group in AD.
- 10:01 Alice still holds the existing local session and may still see the stale authority unless the app refreshes it.
- Changing AD groups alone does not immediately invalidate all Kerberos tickets and Spring sessions.

### 16.2. Three Cache Layers

| Cache | Data | Risk |
|---|---|---|
| OS Kerberos ticket cache | TGT/ST | Ticket remains valid after role changes |
| Directory/IAM cache | Groups, role mappings | Updated memberships not yet reflected |
| Spring HttpSession/SecurityContext | GrantedAuthorities snapshot | Stale authorities persist |

**Separate Kerberos ticket expiration from authority expiration.** Renewing tickets or changing passwords does not guarantee the application's role snapshot refreshes automatically.

### 16.3. Revocation Policies

Options:
1. Authority cache TTL proportional to risk level.
2. Event-driven invalidation when IAM/AD memberships change.
3. Invalidating Spring sessions when permissions are revoked or local accounts are disabled.
4. Live entitlement checks before especially sensitive actions.
5. Cluster-wide Redis/shared session state with revocation versions.
6. Never caching ROLE_ADMIN indefinitely.
7. During directory outages, fail closed for login/role elevation; stale reads require explicit policy.
8. Audit who granted/revoked permissions and when the role snapshot was created.

### 16.4. What If AD/LDAP Is Unresponsive?

Never fall back to a user with ROLE_ADMIN or pretend the user belongs to all groups. Depending on product policy:
- Reject login with a temporary error (distinct from an invalid ticket).
- Use a tightly scoped TTL cache for low-risk read-only access if approved.
- Block sensitive operations until the IAM source recovers.
- Enforce timeouts, circuit breakers, latency monitoring, and prevent blocking servlet threads.

## 17. JIT Provisioning and Account Linking

A valid Kerberos principal without an existing local record faces two policies:

**Pre-provisioned:** only users pre-created by admins can log in. Nonexistent user → reject.

**Just-In-Time:** the app creates a local account upon a verified Kerberos identity, only when:
- Realm/SPN/user passes an allowlist.
- IAM/group onboarding entitlement is approved.
- No collision with existing accounts/local identity links.
- Tenant membership is determined server-side.
- Default permissions are minimal, never ROLE_ADMIN.
- Auditing and offboarding/disable workflows exist.

Never auto-link to an existing user merely because of a shared email or short name. Identity linking requires proof and audit, especially when multiple forests/realms are trusted.

## 18. When an Account Is Disabled, the Ticket May Still Be Valid

A Kerberos Service Ticket issued by the KDC before a user was locked may remain valid for the rest of its ticket lifetime. The GSS verifier may keep returning the verified principal per protocol/policy. Therefore:
- The app must check local account enabled/locked/offboarded status.
- Business roles need revocation within deadline.
- Never check only `isAuthenticated()` or the principal suffix.
- If the provider does not enforce every UserDetails flag itself, reject explicitly in tested service/policy code.
- Existing sessions must be invalidated upon user lockout per security requirements.

**Do not equate:** Kerberos authentication success with application account eligibility.

## 19. LDAP Groups and Local Roles Can Conflict

Suppose:
- An AD group grants Alice report-read.
- Yet the local DB role assignment was revoked.
- The app business policy permits access only when **both** directory membership and local tenant membership are active.

Never union two sources into all permissions without defining precedence. Establish explicit rules:
- Directory source governs organizational identity/group membership.
- App source governs role/tenant entitlement.
- Sensitive permissions require conjunction/approval.
- When one source is unavailable, fail closed or follow an approved offline procedure.
- When two sources conflict, deny and audit rather than picking whichever grants more access.

**Takeaway:** Loading permissions is not just querying groups; it is enforcing a **policy decision** with clear trust and lifecycle boundaries.

## 20. Unit and Integration Testing

### 20.1. Unit Tests for the Mapper

| Case | Input | Expected |
|---|---|---|
| U1 | Verified active Alice, G-READ | ROLE_REPORT_VIEW |
| U2 | Alice has an unrecognized group named Admin | Never grant ROLE_ADMIN |
| U3 | Disabled Bob with G-APPROVE | Deny |
| U4 | User in team-a accesses team-b | Deny |
| U5 | Identical short name, different realm | Never cross-link |
| U6 | Directory cannot find user | UsernameNotFoundException |
| U7 | Directory returns two matches | Deny ambiguous |
| U8 | Null/malformed group ID | Reject/ignore per contract |
| U9 | Expired/locked account | Deny |
| U10 | Duplicate groups | No duplicate authorities created |
| U11 | Disallowed realm | Deny |
| U12 | Group list fails due to timeout | Never auto-grant permissions |
| U13 | User has zero roles | No-access or approved guest policy |
| U14 | Principal contains special LDAP filter characters | Query escaped/parameterized |
| U15 | Tenant membership revoked | Deny at resource layer |

### 20.2. Integration Tests for the Kerberos Pipeline

1. Browser sends a valid SPNEGO token for the exact HTTP SPN.
2. `SunJaasKerberosTicketValidator` verifies the ticket with the keytab.
3. Provider retrieves the exact principal (including realm).
4. `UserDetailsService.loadUserByUsername` is invoked **after** ticket validation.
5. Active user account receives allowlisted authorities.
6. Route `/reports/**` succeeds with ROLE_REPORT_VIEW.
7. Route `/approve/**` returns 403 without ROLE_REPORT_APPROVE.
8. Wrong SPN, stale keytab, replay, and wrong realm are all rejected.
9. Absent directory account grants no local authenticated business roles.
10. Active session holding cached authorities is tested when permissions change.
11. Directory outage never falls back to admin.
12. Nested groups/cross-forest trusts follow policy.
13. Proxy/ingress prevents browsers from injecting trusted identity headers.
14. Load balancer nodes share consistent keytabs and IAM policy.
15. CSRF/TLS and session fixation protections remain intact.

**Using MockMvc with a mocked principal alone does not prove Kerberos ticket validation.** Real KDC/GSS/HTTP Negotiate integration tests are required to verify the trust boundary.

## 21. Troubleshooting: 401, 403, and Missing Permissions

| Symptom | Common Failing Layer | Where to Check |
|---|---|---|
| 401 without Negotiate challenge | SecurityFilterChain/entrypoint | Filter order, route, 401 headers |
| 401 with SPNEGO token | GSS/Kerberos verification | SPN, keytab, kvno, realm, clocks |
| Kerberos passes yet UsernameNotFound | User mapping | Full principal, AD/DB identity link |
| Kerberos passes yet 403 | Authorization | GrantedAuthorities, role/tenant |
| `hasRole("ROLE_REPORT_VIEW")` fails | Role prefix | Use hasRole("REPORT_VIEW") or hasAuthority |
| Newly added group missing from roles | Group mapping/cache | Stable SID, nested membership, refresh |
| Removed group role still active | Stale session/cache | Invalidation, entitlement recheck |
| LDAP returns multiple users | Overly broad search base/filter | Narrow scope, reject ambiguous |
| Disabled AD account still gets in | Unchecked app status/session | Reject disabled + revoke session |
| Alice from another realm confused | Stripped realm/bad UPN alias | Exact principal/identity link |
| LDAP lookup slow or timing out | Directory backend | TLS, network, timeout, circuit breaker |
| Admin role granted to all domain users | Broken policy mapping | Allowlist, no default elevation |
| Valid GSS token yet wrong tenant accessed | Missing resource authorization | Tenant memberships and IDOR checks |
| Fails on only one node | Different keytab/cache/policy version | Compare deployment per node |
| Alternate login flow still succeeds | Provider mix-up | Inspect AuthenticationManager and filter chain |
| HTTP Negotiate uses NTLM | SPNEGO mechanism fallback | Enforce approved mechanism |
| User just changed password yet still has ticket | Kerberos credential lifecycle | Do not confuse tickets with roles |

**Debugging order:** browser Negotiate → GSS/SPN/keytab → verified principal/realm → UserDetailsService → account state → group-to-role policy → Authentication.getAuthorities → tenant/resource authorization → cache/session revocation.

## 22. Operational Safety

- Never log raw `Authorization: Negotiate` tokens, TGT/STs, session keys, keytabs, or LDAP bind passwords.
- Protect the keytab with a secret store/volume and file ACLs restricted to the service UID.
- Enable TLS/HTTPS despite Kerberos; Kerberos does not protect the entire HTTP body.
- Keep CSRF protection on state-changing requests.
- Use LDAPS/StartTLS or equivalent secure connections for LDAP/AD lookups with a least-privilege service account.
- Apply escaping/parameterized filters/SQL to prevent injection.
- If Spring sessions cache authorities, implement revocation workflows when IAM roles change.
- Never infer ROLE_ADMIN from AD Domain Users or realm membership.
- Audit login/lookup/deny status by correlation ID without exposing excessive PII.
- Never rely on tickets to check account status since tickets have their own lifetimes.
- Never copy incoming Negotiate tokens to another backend SPN; delegation requires dedicated design and authorization.
- Pin compatible Spring Security, Spring Security Kerberos, and Java/Jakarta Servlet versions for your codebase.

## 23. Completion Checklist

- [ ] User principal verified via Kerberos GSS before permission lookup.
- [ ] Spring Kerberos provider wired with UserDetailsService via `setUserDetailsService`.
- [ ] Identity mapping preserves full principal and realm.
- [ ] Missing/disabled/locked/expired accounts rejected.
- [ ] Directory/DB/IAM serves as trusted authority source, never the browser.
- [ ] AD groups mapped via stable group ID/SID and explicit allowlist.
- [ ] No default ROLE_ADMIN or automatic grant from realm names.
- [ ] Role prefixes and hasRole/hasAuthority used accurately.
- [ ] Business resource checks enforce tenant and ownership boundaries.
- [ ] Directory caches and Spring sessions have TTL/invalidation controls.
- [ ] Offboarding/revocation and group updates tested.
- [ ] LDAP/SQL queries parameterized and protected by TLS.
- [ ] Integration tests run against real Kerberos/Keytab/KDC.
- [ ] CSRF/TLS/session management not weakened for SPNEGO.
- [ ] Raw tickets, keytabs, and directory secrets excluded from logs.
- [ ] Cross-realm principals and short-name collisions tested.
- [ ] Authority source outage scenario tested with fail-closed policy.

## 24. Review Questions

1. **What does a Kerberos ticket prove?** That the client principal completed a valid Kerberos AP exchange under trust policy; it does not grant app roles itself.
2. **Which Spring API loads permissions after ticket validation?** `KerberosServiceAuthenticationProvider.setUserDetailsService`.
3. **Does UserDetailsService verify the keytab?** No, the validator/GSS handles that.
4. **Why does UserDetailsService require an already-verified username?** To prevent clients from spoofing identities via headers or query parameters.
5. **Why keep the realm in the principal?** Usernames can collide across trusted realms.
6. **Is an AD group automatically ROLE_ADMIN?** No; it must be mapped per policy.
7. **How does hasRole("REPORT_VIEW") differ from hasAuthority("ROLE_REPORT_VIEW")?** With the default prefix, both require the same authority.
8. **Can a disabled account with an unexpired ticket still log in?** Not if application policy denies it.
9. **Does changing a role in AD automatically update an active Spring session?** Not by default, due to cache/session snapshots.
10. **Why use group SIDs instead of group displayNames?** SIDs are stable and avoid name collisions/renames.
11. **Does an LDAP directory lookup require the user's password?** No; a service identity and directory read policy suffice.
12. **Do AD nested groups need explicit policy handling?** Yes, direct memberOf alone may be incomplete.
13. **Can a team-a user read team-b reports just because they hold ROLE_REPORT_VIEW?** No; enforce resource-level tenant checks.
14. **What should happen when the permission source times out?** Fail closed or use an approved TTL cache, never escalate privileges.
15. **Should JIT provisioning make every Kerberos user an admin?** No.
16. **Does MockMvc user() prove SPNEGO ticket validation?** No.
17. **How does a Kerberos 401 differ from a 403?** 401 indicates an authentication challenge/failure; 403 indicates a known identity lacking permission.
18. **What if the app reads X-Remote-User from a proxy?** That is a separate preauth architecture requiring a trusted gateway and client header stripping.
19. **When permissions are revoked, what else must be handled besides the AD group?** Role caches, Spring sessions, and resource policies.
20. **What is the overarching principle?** Verify Kerberos first, link to a trusted account, map permissions via allowlist, and check tenant/resource at the point of use.

## 25. Official References

- Spring Security Kerberos — JavaConfig, SPNEGO and AuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Spring Security Kerberos — KerberosServiceAuthenticationProvider JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- Spring Security Kerberos — SpnegoAuthenticationProcessingFilter JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — GrantedAuthority and HTTP authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — LDAP/AD directory authentication reference: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Kerberos v5, RFC 4120: https://www.rfc-editor.org/rfc/rfc4120
- HTTP SPNEGO/Negotiate, RFC 4559: https://www.rfc-editor.org/rfc/rfc4559
- SPNEGO GSS-API mechanism, RFC 4178: https://www.rfc-editor.org/rfc/rfc4178
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — LDAP Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html

**Conclusion:** Kerberos/SPNEGO solves **"Who was authenticated by the KDC?"**. `UserDetailsService` behind `KerberosServiceAuthenticationProvider` solves **"Which application account does this correspond to, and what GrantedAuthorities does it hold?"**. Finally, Spring Authorization and business services decide **"May that person perform this action on this specific resource/tenant?"**. Preserving realms and verified principals, failing closed when identity/group lookups are ambiguous, never granting permissions from tickets or browser headers, and managing cache/revocation cleanly ensure Kerberos integration is sound for both authentication and authorization.
