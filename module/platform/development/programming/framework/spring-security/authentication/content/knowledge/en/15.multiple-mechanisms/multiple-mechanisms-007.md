# Authorities Loaded from Different Sources and Normalization Requirements in Spring Security

## 1. The Challenge When an Application Has Multiple Authentication Mechanisms

A system may simultaneously support multiple login paths and multiple authority sources:

- Staff sign in with internal **username/password**, with roles read from a database.
- Staff sign in via **OpenID Connect (OIDC)**; the system receives their groups from an identity provider (IdP).
- APIs accept **OAuth2 JWT access tokens** containing scopes such as `orders.read`.
- Service accounts are granted a separate set of permissions.
- Legacy systems may use LDAP groups or a custom `AuthenticationProvider`.

Each source has **different naming conventions, trust units, refresh timings, and permission semantics**. If the application uses raw values directly for authorization, policies become hard to control:

~~~text
Local DB      : SUPPORT, ORDER_VIEW
OIDC groups   : groups/support, groups/order-readers
JWT scopes    : orders.read, orders.write
LDAP groups   : cn=Support,ou=Groups,...
                              |
                              v
                 Application policy
                 ROLE_SUPPORT
                 orders:read
                 orders:write
~~~

This lesson focuses on **authority normalization**: translating values strictly from verified sources into a set of `GrantedAuthority` instances **with unified, deterministic, server-controlled semantics**.

Objectives:

1. Distinguish identity authentication from authorization and understand `Authentication.getAuthorities()`.
2. Define explicit mapping tables for DB, IdP groups, JWT scopes, and permitted sources.
3. Understand `ROLE_`, `SCOPE_`, business permissions, and how `hasRole` / `hasAuthority` check strings.
4. Eliminate duplicate grants, unapproved grants, invalid names, and cross-source confusion.
5. Integrate the normalization point properly into `UserDetailsService`/`AuthenticationProvider`, OAuth2/OIDC login, and JWT resource servers.
6. Handle identity, tenant, trusted source, stale permissions, and “deny” semantics before aggregating authorities.
7. Test normalization deterministically, preventing accidental grants of `ROLE_ADMIN` from client-controlled data.

Examples use **Java 17+, Spring Security 6.x**. The standalone Maven program focuses on mapping rules; the OAuth2/JWT integration snippets show configuration to place inside a real Servlet application.

## 2. What Are Authorities and Where Are They Used?

Spring Security stores a collection of `GrantedAuthority` objects inside `Authentication` after identity verification. `GrantedAuthority` has a simple contract:

~~~java
public interface GrantedAuthority {
    String getAuthority();
}
~~~

`SimpleGrantedAuthority` represents an authority as a string. For example:

~~~java
new SimpleGrantedAuthority("ROLE_SUPPORT");
new SimpleGrantedAuthority("orders:read");
new SimpleGrantedAuthority("SCOPE_orders.read");
~~~

These are **three distinct strings**, not automatically equivalent.

| Authority string | Meaning under a sample policy | How it is checked |
| --- | --- | --- |
| `ROLE_SUPPORT` | Support role | `hasRole("SUPPORT")` or `hasAuthority("ROLE_SUPPORT")` |
| `orders:read` | Business permission to read orders | `hasAuthority("orders:read")` |
| `orders:write` | Business permission to modify orders | `hasAuthority("orders:write")` |
| `SCOPE_orders.read` | OAuth2/JWT scope per default convention | `hasAuthority("SCOPE_orders.read")` |
| `OIDC_USER` | Special authority from some OIDC login flows | Do not treat as a business or admin role |

By default, `hasRole("SUPPORT")` looks for the string `ROLE_SUPPORT` (prefix `ROLE_`). `hasAuthority("ROLE_SUPPORT")` performs an exact match. If an application changes the default role prefix, results change; document your project's prefix policy.

**There is no automatic mechanism** recognizing that `SUPPORT` in DB, `groups/support` in IdP, and `SCOPE_support` from a JWT represent the same role. Developers must define that rule explicitly.

### Distinguishing 4 Concepts

- **Authentication**: who is accessing, are they verified, and via which mechanism.
- **Role**: a group of responsibilities, such as `ROLE_SUPPORT` or `ROLE_OPERATOR`.
- **Permission/authority**: a specific action, such as `orders:read`, `orders:write`. Roles are also represented as authorities in Spring Security.
- **Scope**: a permission granted to an OAuth2 client/access token under the authorization server's protocol. Scopes are not inherently user roles.

For example, a token carrying scope `orders.read` only proves the authorization server granted that scope to the token **within its issuer, audience, subject/client, and policy context**. It does not by itself prove the token holder is a system administrator.

## 3. Building the Application's “Canonical Authority Vocabulary”

Before writing a converter, decide on the target authority set. For example:

| Canonical authority | Meaning | Valid origins |
| --- | --- | --- |
| `ROLE_SUPPORT` | Support staff role | Internal DB role; verified IdP support group |
| `ROLE_OPERATOR` | Operations role | Internal DB role; verified IdP operations group |
| `orders:read` | View orders matching tenant and ownership | DB permission; IdP order-readers group; allowed JWT scope |
| `orders:write` | Edit orders matching tenant and ownership | DB permission; JWT scope issued under policy |
| `ROLE_ADMIN` | Privileged admin role | Only dedicated approved admin source; never inferred from text containing “admin” |

A **controlled mapping table** might look like:

| Verified source | Source value | Canonical authority |
| --- | --- | --- |
| Local DB | `role:support` | `ROLE_SUPPORT` |
| Local DB | `role:operator` | `ROLE_OPERATOR` |
| Local DB | `perm:orders-view` | `orders:read` |
| Local DB | `perm:orders-edit` | `orders:write` |
| OIDC IdP group | `groups/support` | `ROLE_SUPPORT` |
| OIDC IdP group | `groups/operators` | `ROLE_OPERATOR` |
| OIDC IdP group | `groups/order-readers` | `orders:read` |
| Verified JWT scope | `orders.read` | `orders:read` |
| Verified JWT scope | `orders.write` | `orders:write` |

Any other values—such as `groups/admin`, `admin`, `ROLE_ADMIN`, or `orders.read.all-tenants`—**must not be granted** without an explicit mapping entry. This enforces **default deny** for unapproved privileges.

Never use broad rules like:

~~~java
// UNSAFE: client/IdP can inject any string into the result.
String role = "ROLE_" + externalValue.toUpperCase();

// UNSAFE: any group containing "admin" becomes admin.
if (group.toLowerCase().contains("admin")) {
    return "ROLE_ADMIN";
}
~~~

Instead, map **specific values**, validate the source, and govern changes through review.

## 4. Trusted Sources Must Be Verified Before Normalization

A `RawGrant(source, value)` record is trustworthy only if an **internal adapter** has verified it actually came from that source. Never let clients send JSON like `{"source":"LOCAL_DB","role":"admin"}` and turn it into an authority.

| Source | Preconditions before reading roles/groups/scopes |
| --- | --- |
| Local DB | User is authenticated; grant rows queried via controlled lookup matching exact subject and tenant, account is active |
| OIDC group | Identity token/UserInfo from trusted IdP, flow verified issuer, signature/nonce/audience where applicable, group claim has agreed semantics |
| JWT access token | JWT signature, expiration, and issuer verified by `JwtDecoder`; audience/token type/tenant validated per config; scope claim matches semantics |
| LDAP group | Proper LDAPS/TLS connection, authenticated principal, groups queried from trusted directory |
| API key/service account | Key verified by `AuthenticationProvider`; authorities loaded from the server-side service account record |

**Issuer and audience matter.** The same `groups/support` string from two IdPs can carry very different meanings. With multiple issuers, never merge straight into a shared namespace; use a mapping key containing at least `source + issuer + raw value`, plus tenant/organization when multi-tenant.

**Subject also matters.** `sub=user-123` from issuer A is not automatically the same person as `sub=user-123` from issuer B. Internal IDs should derive from a stable identifier such as an approved `(issuer, sub)` link. Unverified emails, mutable emails, or mere address collisions are insufficient to combine authorities.

## 5. A Trustworthy Normalization Pipeline

~~~text
       Authentication Provider / JWT Decoder / OIDC Client
                           |
                 Verify identity/token
                           |
              Check account + tenant + issuer
                           |
       Adapter fetches grants from verified source
                           |
             (Source, rawValue, provenance)
                           |
             AuthorityNormalizer (allowlist)
                           |
            Drop invalid/unapproved values
                           |
        Dedupe + sort + canonical authorities
                           |
              Authentication authenticated
                           |
                 AuthorizationManager
                           |
       Check permission AND resource-level access
~~~

Implementation rules:

1. **Immutable raw inputs with provenance**: retain `Source`, original role/group code, issuer ID, or policy version for auditing, at least through mapping.
2. **One canonical vocabulary**: standardize casing, prefixes, and permission names. Do not mix `ORDER_READ`, `order.read`, and `orders:read` in the same app when intending one meaning.
3. **Per-source mapping**: the same raw string may be allowed from DB yet rejected from JWT; different sources must not share an allowlist.
4. **Do not alter strings blindly**: only `trim`, lowercase, or Unicode-normalize when **mandated by the source protocol** and backed by tests. For case-sensitive scopes and groups, automatic transformations can widen privileges.
5. **Reject unknown grants**: drop/deny and meter them; if an operation requires that grant, block the transaction or deny login per policy.
6. **Deduplicate**: someone might receive `orders:read` from both DB and OIDC; the output should not hold two identical entries.
7. **Never auto-merge distinct identities**: aggregate only when grants genuinely belong to the **same verified subject and tenant scope**.
8. **Lock/revocation status takes precedence**: if an account is disabled/suspended, dropping one authority is not enough; block authentication/authorization per policy. Standard `GrantedAuthority` represents granted privileges, not an automatic priority “deny”.
9. **Record provenance separately from the final list**: once `ROLE_SUPPORT` is deduplicated, `SimpleGrantedAuthority` itself no longer tells whether it came from DB or IdP; auditing needs provenance stored at another layer.

## 6. Runnable Java 17 Example: Normalizing from Three Sources

The example uses `SimpleGrantedAuthority` from **Spring Security Core**. The `RawGrant` entries in `main` are **illustrative data already provided by trusted adapters**; this class does not decode JWTs or query a DB itself. Its goal is to demonstrate policy-driven normalization without building authorities via string concatenation.

### 6.1. Create the Maven Project

~~~text
authority-normalization-demo/
├── pom.xml
└── src/
    ├── main/java/demo/authorities/AuthorityNormalizationDemo.java
    └── test/java/demo/authorities/AuthorityNormalizationDemoTest.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>authority-normalization-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-core</artifactId>
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
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.4.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Spring Boot parent manages compatible Spring Security and JUnit versions; the program does not need to start a Spring Boot web server.

### 6.2. Main Source Code

File `src/main/java/demo/authorities/AuthorityNormalizationDemo.java`:

~~~java
package demo.authorities;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeSet;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class AuthorityNormalizationDemo {

    private AuthorityNormalizationDemo() {
    }

    // Enum describing the ALREADY-VERIFIED source before reaching normalizer.
    public enum Source {
        LOCAL_DB, IDP_GROUP, JWT_SCOPE
    }

    public record RawGrant(Source source, String value) {
        public RawGrant {
            Objects.requireNonNull(source, "source");
            Objects.requireNonNull(value, "value");
        }
    }

    public static final class AuthorityNormalizer {

        // Explicit mapping table, decided only by the server.
        // In production, this can be stored in versioned/audited configuration.
        private static final Map<Source, Map<String, String>> ALLOWED =
            Map.of(
                Source.LOCAL_DB,
                Map.of(
                    "role:support", "ROLE_SUPPORT",
                    "role:operator", "ROLE_OPERATOR",
                    "perm:orders-view", "orders:read",
                    "perm:orders-edit", "orders:write"
                ),
                Source.IDP_GROUP,
                Map.of(
                    "groups/support", "ROLE_SUPPORT",
                    "groups/operators", "ROLE_OPERATOR",
                    "groups/order-readers", "orders:read"
                ),
                Source.JWT_SCOPE,
                Map.of(
                    "orders.read", "orders:read",
                    "orders.write", "orders:write"
                )
            );

        public List<GrantedAuthority> normalize(
                Collection<RawGrant> trustedSourceGrants) {

            Objects.requireNonNull(
                trustedSourceGrants, "trustedSourceGrants");

            // TreeSet: dedupe and return deterministic order for tests/logs.
            TreeSet<String> canonical = new TreeSet<>();

            for (RawGrant raw : trustedSourceGrants) {
                Objects.requireNonNull(raw, "raw grant");

                // No "ROLE_" + raw.value() logic.
                String mapped = ALLOWED.get(raw.source()).get(raw.value());
                if (mapped != null) {
                    canonical.add(mapped);
                }
                // No mapping -> grant no authority.
            }

            List<GrantedAuthority> result = new ArrayList<>();
            for (String authority : canonical) {
                result.add(new SimpleGrantedAuthority(authority));
            }

            // Prevent downstream code from accidentally mutating normalized authorities.
            return List.copyOf(result);
        }
    }

    public static void main(String[] args) {
        AuthorityNormalizer normalizer = new AuthorityNormalizer();

        // Illustrative only: assumes the adapter already verified the same
        // subject + tenant and that values truly came from the right source.
        List<RawGrant> trustedGrants = List.of(
            new RawGrant(Source.LOCAL_DB, "role:support"),
            new RawGrant(Source.IDP_GROUP, "groups/order-readers"),
            new RawGrant(Source.JWT_SCOPE, "orders.read"),
            new RawGrant(Source.JWT_SCOPE, "admin"),
            new RawGrant(Source.IDP_GROUP, "groups/admin"),
            new RawGrant(Source.LOCAL_DB, "role:support")
        );

        List<GrantedAuthority> authorities =
            normalizer.normalize(trustedGrants);

        List<String> names = authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .toList();

        System.out.println("authorities=" + names);
        System.out.println("hasSupport=" + names.contains("ROLE_SUPPORT"));
        System.out.println("canReadOrders=" + names.contains("orders:read"));
        System.out.println("hasAdmin=" + names.contains("ROLE_ADMIN"));
    }
}
~~~

Run inside the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q -DskipTests compile
mvn -q -Dexec.mainClass=demo.authorities.AuthorityNormalizationDemo exec:java
~~~

The lines printed explicitly by the program, in exact order:

~~~text
authorities=[ROLE_SUPPORT, orders:read]
hasSupport=true
canReadOrders=true
hasAdmin=false
~~~

Maven may print additional system messages depending on environment. The code depends on Spring Security libraries on the classpath, so it cannot run with bare `javac` without supplying dependencies.

### 6.3. Detailed Walkthrough of the Example

**Source-tagged input:** `RawGrant(Source.LOCAL_DB, "role:support")` differs from `RawGrant(Source.JWT_SCOPE, "role:support")`. Despite identical strings, only the `LOCAL_DB` mapping allows it to become `ROLE_SUPPORT`.

**Never trusting “admin”-named grants:** `admin` from JWT and `groups/admin` from IdP are absent from the allowlist, so `ROLE_ADMIN` is never created. Specifically, if a JWT carries `ROLE_ADMIN` in a client- or third-party-supplied claim, converting it straight to `SimpleGrantedAuthority("ROLE_ADMIN")` would cause privilege escalation.

**One permission from multiple sources:** `groups/order-readers` and `orders.read` both translate to `orders:read`. `TreeSet` removes duplicates and sorts deterministically. This is valid only when both sources are verified, represent **the same identity**, and are permitted by policy to combine.

**Immutability of the authority set:** `List.copyOf` returns a list that cannot be modified via standard add/remove operations. This does not make an untrusted source trustworthy; it merely reduces the chance of downstream components mutating the authority collection accidentally.

**Does not authenticate the user itself:** `normalize` returns `List<GrantedAuthority>`, not a trusted `Authentication`. In real application code, only after the provider/IdP/JWT decoder has verified identity and checked account status does the adapter forward grant sources to the normalizer.

## 7. Testing Sources, Duplicates, and Malicious Inputs

Create `src/test/java/demo/authorities/AuthorityNormalizationDemoTest.java`:

~~~java
package demo.authorities;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;

import static demo.authorities.AuthorityNormalizationDemo.Source.*;
import static org.junit.jupiter.api.Assertions.*;

class AuthorityNormalizationDemoTest {

    private final AuthorityNormalizationDemo.AuthorityNormalizer normalizer =
        new AuthorityNormalizationDemo.AuthorityNormalizer();

    private List<String> names(
            List<AuthorityNormalizationDemo.RawGrant> raw) {
        return normalizer.normalize(raw).stream()
            .map(GrantedAuthority::getAuthority)
            .toList();
    }

    private AuthorityNormalizationDemo.RawGrant raw(
            AuthorityNormalizationDemo.Source source,
            String value) {
        return new AuthorityNormalizationDemo.RawGrant(source, value);
    }

    @Test
    void mapsTheSamePermissionFromDifferentVerifiedSourcesOnce() {
        assertEquals(List.of("ROLE_SUPPORT", "orders:read"),
            names(List.of(
                raw(LOCAL_DB, "role:support"),
                raw(IDP_GROUP, "groups/order-readers"),
                raw(JWT_SCOPE, "orders.read"),
                raw(LOCAL_DB, "role:support")
            )));
    }

    @Test
    void sameRawStringFromDifferentSourceDoesNotGainRole() {
        assertEquals(List.of("ROLE_SUPPORT"),
            names(List.of(raw(LOCAL_DB, "role:support"))));

        assertEquals(List.of(),
            names(List.of(raw(JWT_SCOPE, "role:support"))));
    }

    @Test
    void unknownAdminLookingValuesDoNotBecomeAdmin() {
        assertEquals(List.of(),
            names(List.of(
                raw(IDP_GROUP, "groups/admin"),
                raw(JWT_SCOPE, "admin"),
                raw(LOCAL_DB, "ROLE_ADMIN")
            )));
    }

    @Test
    void exactMappingDoesNotSilentlyTrimOrChangeCase() {
        assertEquals(List.of(),
            names(List.of(
                raw(JWT_SCOPE, "ORDERS.READ"),
                raw(JWT_SCOPE, " orders.read "),
                raw(IDP_GROUP, "Groups/Support")
            )));
    }

    @Test
    void distinctApprovedGrantsStayDistinct() {
        assertEquals(List.of("ROLE_OPERATOR", "orders:write"),
            names(List.of(
                raw(LOCAL_DB, "role:operator"),
                raw(JWT_SCOPE, "orders.write")
            )));
    }

    @Test
    void noGrantsMeansNoPermissions() {
        assertEquals(List.of(), names(List.of()));
    }

    @Test
    void rejectsNullInputInsteadOfGuessing() {
        assertThrows(NullPointerException.class,
            () -> normalizer.normalize(null));
        assertThrows(NullPointerException.class,
            () -> new AuthorityNormalizationDemo.RawGrant(
                null, "role:support"));
        assertThrows(NullPointerException.class,
            () -> new AuthorityNormalizationDemo.RawGrant(
                LOCAL_DB, null));
    }

    @Test
    void resultCollectionIsImmutable() {
        List<GrantedAuthority> result = normalizer.normalize(
            List.of(raw(LOCAL_DB, "role:support")));

        assertThrows(UnsupportedOperationException.class,
            () -> result.clear());
        assertEquals("ROLE_SUPPORT", result.get(0).getAuthority());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expectation:** 8 tests pass when executed on JDK/Maven with compatible dependency versions in `pom.xml`. These tests are practice source code; execute them in your project to verify. They check many **deny/no-grant** cases, not just valid inputs.

### Why Write Negative Tests?

If code ran `raw.toUpperCase()` and prepended `ROLE_`, the “admin-looking” test would catch `ROLE_ADMIN` appearing. If code ignored the source, the “same raw different source” test would catch a JWT scope masquerading as a DB role. If code silently trimmed or lowercased, the “exact mapping” test would catch normalization altering permission semantics.

Tests also ensure adding future authority sources does not accidentally alter existing users. Whenever updating the map, add tests proving each new entry is an approved policy and update the audit/version.

## 8. Injecting Authorities Into Authentication at the Right Time

Integration flow with a custom provider or `UserDetailsService`:

~~~text
HTTP login
 -> Filter creates unauthenticated token
 -> AuthenticationManager selects AuthenticationProvider
 -> Provider verifies password / credentials / account status
 -> Adapter reads verified roles for exact user/tenant
 -> AuthorityNormalizer.normalize(...)
 -> Provider returns authenticated Authentication with canonical authorities
 -> SecurityContextRepository saves context if using sessions
 -> AuthorizationManager checks endpoint
~~~

**Illustrative snippet inside a provider after credential verification succeeds**:

~~~java
// verifiedUser: verified user object, never self-supplied by client.
// rawGrants: grants read by the server adapter for that exact verifiedUser.
List<GrantedAuthority> authorities = normalizer.normalize(rawGrants);

Authentication authenticated =
    UsernamePasswordAuthenticationToken.authenticated(
        verifiedUser,
        null,
        authorities
    );

return authenticated;
~~~

This snippet **is not a standalone program**: `verifiedUser`, `rawGrants`, and `normalizer` must come from a trusted provider/adapter. Never do:

~~~java
// WRONG: simply reading body/claims from request and marking authenticated.
List<GrantedAuthority> roles = requestRoles.stream()
    .map(SimpleGrantedAuthority::new)
    .toList();

return UsernamePasswordAuthenticationToken.authenticated(
    submittedUsername, null, roles);
~~~

**When using `DaoAuthenticationProvider` and `UserDetailsService`**, authority loading can live inside `UserDetailsService.loadUserByUsername`: after querying the right account, construct `UserDetails` with canonical authorities; the provider will verify the password using `PasswordEncoder`. Some providers offer their own `GrantedAuthoritiesMapper` to process authorities after loading. Reuse one normalizer service and unified policy so two login flows never translate authorities differently.

**When using sessions**, the authorities on `Authentication` in `SecurityContext` may be a snapshot. Changing roles in the DB or IdP does not automatically update live sessions. Explicitly define TTL, authority refresh mechanisms, session invalidation on account lock, and per-request checks for sensitive privileges.

## 9. Integrating OAuth2/OIDC Login

In `oauth2Login`, Spring Security lets you customize authority mapping via a `GrantedAuthoritiesMapper` or a delegated `OAuth2UserService`/`OidcUserService`. You can use the mapper to convert `OidcUserAuthority` / `OAuth2UserAuthority` and appropriate claims into the application's canonical authorities.

Configuration skeleton:

~~~java
// Place inside SecurityFilterChain when the app has
// spring-boot-starter-oauth2-client and an IdP config:
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(approvedAuthoritiesMapper)
    )
);
~~~

`approvedAuthoritiesMapper` is an application-provided `GrantedAuthoritiesMapper`. It must:
1. Receive the `GrantedAuthority` instances from Spring Security after the OAuth2/OIDC flow completes.
2. Extract only genuine groups/claims from `OidcUserAuthority`, `OAuth2UserAuthority`, or user info fetched by a trusted service.
3. Enforce issuer/client registration and tenant constraints per configuration. **Never** take any claim named “roles” from any IdP and treat it as an admin role.
4. Translate raw groups through the source allowlist (`Source.IDP_GROUP`), deduplicate, and return `Collection<? extends GrantedAuthority>`.
5. Retain or strip Spring Security's system-generated authorities per explicit policy. Do not accidentally drop system authorities that other features depend on, nor turn `OIDC_USER` into `ROLE_USER` or `ROLE_ADMIN` without design intent.

For example, suppose IdP A emits `groups/support` and IdP B emits the exact same string. If only A is permitted to grant `ROLE_SUPPORT`, the mapping target must distinguish:

~~~text
(issuer=https://idp-a.example, groups/support) -> ROLE_SUPPORT
(issuer=https://idp-b.example, groups/support) -> no authority granted
~~~

`GrantedAuthoritiesMapper` works when the information needed to distinguish sources is already available. If you must call another system for additional grants and need the token/issuer context, a custom `OAuth2UserService` or `OidcUserService` may fit better. Ensure external calls have timeouts, safe fallbacks, and never let transient grant-loading failures turn into “full access”.

## 10. Integrating JWT Resource Server

When an API acts as an OAuth2 Resource Server, Spring Security typically creates a `JwtAuthenticationToken` from a verified access token. By default `JwtGrantedAuthoritiesConverter` can read `scope`/`scp` and produce `SCOPE_`-prefixed authorities, e.g.:

~~~text
JWT scope : orders.read
-> GrantedAuthority: SCOPE_orders.read
-> hasAuthority("SCOPE_orders.read") == true
~~~

If the system already uses canonical permission `orders:read`, two strategies are valid:

**Strategy 1: Keep the default namespace.** Write `hasAuthority("SCOPE_orders.read")` rules specifically for JWT APIs, while DB roles have their own rules. This avoids translation, though keeping a unified policy becomes harder if multiple mechanisms touch the same endpoint.

**Strategy 2: Translate approved scopes.** Use `JwtAuthenticationConverter#setJwtGrantedAuthoritiesConverter` to convert valid scopes into canonical permissions, such as `orders.read → orders:read`; if default `SCOPE_` entries are also needed, combine them under strict control and test the exact output set. Never blindly prepend `ROLE_` to every scope, since scopes issued by an authorization server are not necessarily user roles.

**Illustrative configuration snippet**, assuming `normalizer` is defined as in section 6 and `JwtDecoder` is fully configured:

~~~java
JwtAuthenticationConverter jwtConverter =
    new JwtAuthenticationConverter();

jwtConverter.setJwtGrantedAuthoritiesConverter(jwt -> {
    // Example: trusted issuer provides "scp" claim as List<String>.
    List<String> scopes = jwt.getClaimAsStringList("scp");
    if (scopes == null) {
        scopes = List.of();
    }

    List<AuthorityNormalizationDemo.RawGrant> raw = scopes.stream()
        .map(s -> new AuthorityNormalizationDemo.RawGrant(
            AuthorityNormalizationDemo.Source.JWT_SCOPE, s))
        .toList();

    return normalizer.normalize(raw);
});

// Place inside the Resource Server SecurityFilterChain:
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter))
);
~~~

This snippet **is not a standalone application**; it requires OAuth2 Resource Server imports, `JwtAuthenticationConverter`, `List`, and `normalizer`. More importantly, tokens must pass through a decoder/validator verifying **signature, issuer, expiration, and audience** per policy. Depending on the provider, scopes sit in a space-delimited `scope` string or an `scp` array. Your adapter must understand the exact source format; never guess or loosely parse both and end up granting broader permissions.

When supporting multiple issuers, choose an appropriate `JwtDecoder`/authentication manager resolver and apply per-issuer mapping tables rather than one policy across all tokens. Once a JWT is issued, its authorities typically remain valid until `exp` unless introspection, revocation, or extra state checks are added.

**Important note:** an `access token` can represent either a user or client credentials. An `orders.write` scope in a service account token does not implicitly allow acting like a human staff member; authorization may need to verify principal type, client ID, and target resource in addition to canonical authorities.

## 11. Loading Authorities from DB, LDAP, and Custom Providers

### 11.1. Local Database

For username/password, the server typically verifies passwords via `DaoAuthenticationProvider` / `PasswordEncoder` and loads authorities with `UserDetailsService`. A minimal relational schema can be sketched as:

~~~text
users(user_id, tenant_id, username, password_hash, enabled)
user_grants(user_id, tenant_id, grant_code)
~~~

In the DB adapter:
- Query grants by **verified internal user_id and tenant_id**, never taking an arbitrary `userId` or `tenantId` from the request body.
- Check `enabled`, locked, expired, and login-ban policies before granting authorities.
- Convert `grant_code` into `RawGrant(Source.LOCAL_DB, value)` and invoke the normalizer.
- Never run `SELECT * FROM user_grants WHERE username = ?` on client-supplied values without identity/tenant binding.
- Accept only known grant codes; unexpected grants from bad data migrations must be audited.

### 11.2. LDAP or Directory Groups

LDAP groups such as `cn=Support,ou=Groups,dc=example,dc=org` must be mapped explicitly by stable DN/group ID from a trusted directory. Never infer `ROLE_ADMIN` just because a DN contains the word `Admin`. Check referrals, nested groups, OU relationships, and query results; identical group names in two directories do not necessarily carry the same meaning.

When using Spring Security LDAP, apply a mapper or authentication-side `LdapAuthoritiesPopulator`/adapter, then normalize to canonical authorities. LDAP should be a distinct `Source`, never disguised as `LOCAL_DB`.

### 11.3. Custom AuthenticationProvider

Providers for OTPs, API keys, certificates, or signed challenges verify strictly using their own protocol. Upon success, they load grants from a server-side record and pass them through the same `AuthorityNormalizer`. Never reuse authority names submitted by the client alongside an OTP request.

Example:

~~~text
CustomApiKeyProvider.authenticate(...)
  -> verify hash/API key record
  -> identify serviceAccountId, tenantId, active
  -> read service account policy
  -> normalize grants from approved SERVICE_ACCOUNT source
  -> return trusted Authentication (principal + authorities)
~~~

Note: the `Source` enum in the practice code includes only three sources. When adding `SERVICE_ACCOUNT` or `LDAP_GROUP` in production, **explicitly add the enum value + mapping table + tests**. Never reuse the DB mapping for new sources.

## 12. Multiple Mechanisms Do Not Mean Automatically Summing All Privileges

Some systems support local login, OIDC, and API tokens side by side. There are two models:

**One mechanism per session/request.** Locally logged-in requests use canonical authorities from DB. Bearer JWT requests use canonical authorities from the matching token. Both flows may grant the same permission without needing to merge two sessions' lists.

**Aggregating multiple sources for the same identity.** The app defines an explicit policy for merging DB + IdP groups + scopes, and has verified that all grants belong to the **same account, same tenant, and same security principal**. Only then may a union be applied after mapping.

Severe mistakes to avoid:

~~~text
OIDC issuer A, sub=123   +   JWT issuer B, sub=123
         !=               same person (unproven)

User tenant-a + admin group from tenant-b
         !=               ROLE_ADMIN in tenant-a

Session user A + JWT bearer token user B
         !=               union of A and B privileges

Disabled account + still-valid IdP privileges
         !=               user allowed to log back in
~~~

Even if both sources are valid in signature or password, **identity linking** is a separate security decision. If merging is desired, implement a verified linking workflow and rules for conflicting sources.

### Precedence Rules When Sources Conflict

For example, the DB marks an account `disabled`, while the IdP still returns `groups/operators`. If application policy requires the internal account to be enabled, **never** aggregate `ROLE_OPERATOR` and permit access. Checking account status is a veto step **before** issuing authorities; Spring Security does not automatically treat a string authority like `DENY_LOGIN` as overriding `ROLE_OPERATOR`.

Similarly, an account with “read” in source A and “write” in source B does not automatically gain “write” across every tenant. Aggregation policies must specify scope, subject type, and applicable resources.

## 13. Authorities Do Not Replace Resource-Level Authorization Checks

A canonical authority `orders:read` usually expresses only “allowed to request reading orders”. It does not decide **which order** may be read.

Servlet policy example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/orders/**")
        .hasAuthority("orders:read")
    .requestMatchers(HttpMethod.POST, "/orders/**")
        .hasAuthority("orders:write")
    .anyRequest().authenticated()
);
~~~

This is a **configuration snippet** to place inside `SecurityFilterChain`; it omits imports and the app's remaining routes. It checks action type at the URL level; controllers/services must still check `order.tenantId` and ownership rules.

Method security example:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
public OrderDetails getOrder(String orderId) {
    // Service must verify tenant and permission to view this exact orderId.
    return loadAndAuthorizeOrder(orderId);
}
~~~

This snippet is illustrative and requires `@EnableMethodSecurity` and a real service. If the method has only `@PreAuthorize("hasAuthority('orders:read')")` and queries arbitrarily by `orderId`, a user could view another tenant's orders. Complete authorization checks attributes of both the resource and the principal; for complex requirements, use a controlled `AuthorizationManager` or policy service.

**Role hierarchy**, if used, is also a deliberate policy: `ROLE_ADMIN > ROLE_SUPPORT` can cause admin role holders to inherit support permissions as configured. Never assume roles have hierarchical relationships just from their names. Whenever changing hierarchy, retest all affected endpoints and methods.

## 14. Common Pitfalls in Authority Normalization

| Mistake | Consequence | Proper design |
| --- | --- | --- |
| Prepending `ROLE_` to every external value | A raw `ADMIN` claim can become `ROLE_ADMIN` | Source-specific allowlist, no blind concatenation |
| Treating `scope` as a user role | Service tokens may receive unintended user privileges | Separate scopes, user roles, and client identities |
| Mapping `SCOPE_orders.read` to `ROLE_ADMIN` based on similar wording | Privilege escalation | Explicit business permission mapping |
| Using `equalsIgnoreCase` on unverified groups/scopes | Source may be case-sensitive, widening access | Exact match or source-specified canonicalization rules |
| Auto-trimming/decoding all values | Malformed strings can be accepted outside contract | Reject inputs violating expected format |
| Merging grants from two matching `sub` strings across different issuers | Identity confusion, merged privileges | Link on verified issuer+sub identifiers |
| Merging tenant A privileges with tenant B privileges | Cross-organization access | Bind tenant in subject, grants, and resources |
| Trusting `roles` JSON from frontend | Client dictates its own privileges | Load only from trusted source adapters |
| Using `GrantedAuthority("DENY")` expecting it to negate other grants | A deny string has no built-in veto semantics | Enforce account state and dedicated deny policies |
| Not checking JWT audience | Tokens issued for another system get reused | Configure issuer/audience/token-purpose validators |
| Changing DB roles while forgetting live sessions | Old privileges remain active | Design refresh/revoke/session invalidation |
| Long-lived JWTs retaining revoked scopes | Old privileges work until expiration | Appropriate TTL, revocation/introspection when needed |
| Renaming `SCOPE_` to custom authority without updating rules | Legitimate users get 403 or wrong grants | Test rule matrix before and after migration |
| Testing only one granted happy path | Misses risk of rogue roles becoming admin | Add negative tests for source, issuer, tenant, and grants |
| Storing permission names only in code without versioning | Hard to audit and change safely | Policy versioning, tests, and approval workflows |

## 15. Authority Lifecycle and Consistency

Decide when authorities are refreshed:

| Mechanism | When are authorities snapshotted? | How to update |
| --- | --- | --- |
| Username/password + HTTP session | At login, then stored in `SecurityContext` | Policy-driven refresh, logout/session invalidation, reauthentication |
| OAuth2/OIDC login + session | When login finishes and groups load | Re-fetch info/reauthenticate; consider IdP lifecycle |
| JWT Resource Server | JWT parsed per request, but token scopes are a snapshot | New token or token revocation, suitably short `exp` |
| API key / service principal | Per request or cached | Check key status, revocation, and cache invalidation |
| Local DB permissions | When adapter reads DB | Ensure transaction/caching and invalidation as required |

For sensitive roles like `ROLE_ADMIN`, you may need real-time account status lookup or a policy version check instead of blindly trusting long-lived session/JWT authorities. Do not optimize caching before defining acceptable privilege-revocation latency.

**Audits should record:** internal principal, tenant, auth mechanism, issuer/client, mapping version, normalized authorities, and denial reason (when safe to log). Never log raw passwords, access tokens, refresh tokens, or secrets.

## 16. Implementation Workflow in a Real Project

1. **List authentication paths:** local password, OIDC, LDAP, bearer JWT, API key, service principal. Record where authentication occurs and where authorities load for each path.
2. **Define canonical authorities:** naming conventions, `ROLE_` prefix, permissions like `orders:read`, and which endpoints/methods require which authorities.
3. **Design per-source mappings:** for each necessary issuer/tenant, document allowed raw values, canonical values, approving owner, version, and revocation method.
4. **Place trust boundaries:** adapters load grant data only after verifying credentials/token/issuer/audience/subject and account status.
5. **Share one normalization service:** all providers and converters use the same policy; do not maintain two divergent mappers unless explicitly documented.
6. **Retain provenance for auditing:** distinguish DB grants, IdP groups, and JWT scopes during incident investigations; resulting `SimpleGrantedAuthority` objects lack source metadata.
7. **Separate resource authorization:** canonical permissions must pair with tenant, ownership, order state, and other business rules.
8. **Positive/negative testing:** valid grants, wrong source, case mismatch, excess grants, different tenant, different issuer, disabled account, expired token, grants changed while session/JWT is active.
9. **Deploy and observe:** measure unmapped grants, 403 rates, issuer/tenant errors, sessions holding stale grants; update policy via review instead of auto-accepting new groups.
10. **Zero-downtime migration:** when migrating from `SCOPE_orders.read` to `orders:read`, audit filters, method security, integration tests, and grant data; avoid issuing multiple aliases indefinitely without cause.

### Practical Test Matrix

| Identity | Source data | Expected policy outcome |
| --- | --- | --- |
| User A, tenant A | DB `role:support` | `ROLE_SUPPORT` |
| User A, tenant A | OIDC `groups/order-readers` | `orders:read` |
| Service B | JWT `orders.read` with valid issuer/audience | `orders:read`, without `ROLE_SUPPORT` |
| User C | Unapproved JWT `admin` | No `ROLE_ADMIN` |
| User D | Tenant B IdP group, request to tenant A | Tenant B grants not added |
| User E | DB account disabled, IdP group still valid | Blocked per account policy |
| User F | Expired JWT or wrong audience | Authentication fails before normalization |
| User G | Both DB and OIDC grant `orders:read` | Single `orders:read` authority |
| User H | Claim `ORDERS.READ` mismatches policy case | Not granted without mapping |
| User I | `orders:write` revoked after login | Authority revoked per chosen session/token policy |

## 17. Self-Check Questions

1. Why are `ROLE_SUPPORT` and `SCOPE_support` not automatically equivalent?
2. Why shouldn't every external group be mapped using `"ROLE_" + group.toUpperCase()`?
3. Does a `GrantedAuthority` representing “deny account” automatically override other roles?
4. When can grants from DB, IdP, and JWT be combined for one user? What subject/issuer/tenant conditions must hold?
5. In `hasRole("SUPPORT")`, which authority string does Spring Security normally look for?
6. What is the difference between `JwtGrantedAuthoritiesConverter` and a `GrantedAuthoritiesMapper` used in OAuth2 Login?
7. Why can a user with `orders:read` still be blocked from viewing another tenant's order?
8. If a role changes after a session/JWT has been issued, what determines how long the old privilege remains usable?
9. Why is the test case `JwtScope("admin")` not mapping to `ROLE_ADMIN` important?
10. Why can't a bare `sub` from two different issuers be shared to combine authorities?

## 18. References

1. Spring Security — Authorization Architecture, `GrantedAuthority` and `ROLE_`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
2. Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
3. Spring Security — OAuth2 Login Advanced Configuration, mapping authorities: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
4. Spring Security — OAuth2 Resource Server JWT, scopes and authorities: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
5. Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
6. Spring Security API — `GrantedAuthoritiesMapper`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/GrantedAuthoritiesMapper.html
7. Spring Security API — `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
8. Spring Security API — `SimpleGrantedAuthority`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/SimpleGrantedAuthority.html

**Core principle to remember:** authorities in Spring Security must be derived from **verified identities and permitted authority sources**, then mapped through an **explicit normalization policy**. Multiple mechanisms emitting similar strings never by themselves prove the same user, same tenant, or same privilege level.