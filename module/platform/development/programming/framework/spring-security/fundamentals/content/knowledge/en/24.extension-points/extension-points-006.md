# Mapping Authorities from a Database or External System Claims

## 1. Problem Statement and Goals

In Spring Security, **authentication** determines who is sending the request, while **authorization** decides what that identity is allowed to do. An application often stores permissions in internal database tables or receives groups, roles, or scopes from an external identity system. Values such as `REPORT_VIEW`, `platform-admin`, `roles`, `groups`, or `scope` **do not automatically carry the same meaning** in Spring Security. The application must convert them into consistent `GrantedAuthority` instances before using them for access checks.

This lesson focuses on **extension points for authority mapping** in the *Spring Security - fundamentals* module: choosing the right API for the data source, normalizing authority names, configuring policies, and avoiding unintended privilege escalation. Two primary paths:

1. **Application data**: accounts and user–role relationships live in the database; `UserDetailsService` loads them into `UserDetails.getAuthorities()` during username/password authentication.
2. **External identity systems**: verified access tokens or user info from OAuth2/OIDC login carry claims; a converter or mapper transforms claims into `GrantedAuthority` instances.

By the end of this lesson, you should be able to distinguish `ROLE_` from `SCOPE_`, write explicit and tested mappings, use a Java 17+ database example, configure a converter for JWTs, and handle combined authority sources, permission changes, multi-tenancy, and trust boundaries.

## 2. `GrantedAuthority` Is Spring Security's Permission Representation

Once a request is authenticated, the `Authentication` object contains the principal and a collection of `GrantedAuthority`. Authorization components such as `AuthorizationManager` read that authority collection to make decisions. The common implementation is `SimpleGrantedAuthority`, holding a single string:

```java
GrantedAuthority reader = new SimpleGrantedAuthority("ROLE_READER");
GrantedAuthority canExport = new SimpleGrantedAuthority("PERM_REPORT_EXPORT");
GrantedAuthority readScope = new SimpleGrantedAuthority("SCOPE_reports.read");
```

The three strings above **are completely different**. Spring Security does not automatically infer `ROLE_READER` from `reader`, does not turn `scope=reports.read` into `ROLE_READER`, and does not understand an identity provider's group names by default. Mapping rules must be explicit.

| Source value | Desired authority | Matching policy | Notes |
| --- | --- | --- | --- |
| DB role `REPORT_VIEW` | `ROLE_READER` | `hasRole("READER")` | `hasRole` adds the `ROLE_` prefix by default |
| DB role `OPS_ADMIN` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Do not call `hasRole("ROLE_ADMIN")` |
| Fine-grained permission `EXPORT_REPORT` | `PERM_REPORT_EXPORT` | `hasAuthority("PERM_REPORT_EXPORT")` | Exact string match; no automatic prefix |
| OAuth2 scope `reports.read` | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | Resource Server normally maps `scope`/`scp` with the `SCOPE_` prefix |
| Group claim `app_roles=["report_view"]` | `ROLE_READER` if verified and allowed | `hasRole("READER")` | Requires a converter/mapper following app rules |

**Why distinguish role and authority?** In Spring Security, a role is a naming convention built on top of authority. By default, `hasRole("ADMIN")` checks for authority `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` checks that exact same string, whereas `hasAuthority("ADMIN")` checks a different string. The role prefix can be configured differently, so standardize a convention per project and test the actual configuration.

**Do not confuse identity with authority:** `sub`, email, username, tenant ID, and user ID identify an account or entity; they do not by themselves prove administrative privileges. Even a claim named `isAdmin` is untrustworthy unless issuer, token, audience, and the issuing system's granting rules have been verified.

## 3. Data Flow: Authority Source → Mapping → Authorization

```text
A. Username/password and database
HTTP Basic / Form Login
       │
       ▼
DaoAuthenticationProvider → UserDetailsService
       │                    ├─ app_user
       │                    └─ app_user_role + app_role
       ▼
UserDetails with GrantedAuthority[]
       │
       ▼
Authentication / SecurityContext
       │
       ▼
authorizeHttpRequests / @PreAuthorize
       │
       ├─ Has required authority  → allow
       └─ Missing authority       → deny


B. OAuth2 Resource Server with JWT
Authorization: Bearer <access-token>
       │
       ▼
JwtDecoder: checks signature, issuer, exp/nbf, relevant validators
       │
       ▼
JwtAuthenticationConverter
       ├─ scope/scp → SCOPE_...
       └─ app_roles → ROLE_... per application allowlist
       │
       ▼
JwtAuthenticationToken with GrantedAuthority[]
       │
       ▼
authorizeHttpRequests / @PreAuthorize
```

These two pipelines can produce the same authority (for example `ROLE_READER`), yet use **different extension points**. `UserDetailsService` is not invoked simply because a request contains a JWT; `JwtAuthenticationConverter` does not handle form login or database username/password. For OAuth2/OIDC **browser login**, `GrantedAuthoritiesMapper` and `OAuth2UserService`/`OidcUserService` form yet another flow distinct from a Resource Server accepting access tokens.

Three steps must be verified separately:

1. **Verify the data source**: the user exists and password checks out; the JWT has a valid signature/issuer/audience; UserInfo attributes come from a trusted provider.
2. **Controlled mapping**: input has the expected type, names are normalized via a mapping table, and unrecognized values are not elevated into permissions.
3. **Policy enforcement**: endpoints/methods require the exact generated authorities; missing permissions must be denied.

## 4. Designing the Mapping Table Before Writing Code

Suppose an internal app has two roles in table `app_role`, while an external identity system emits an `app_roles` claim:

| Source | Source value | Internal authority | Meaning |
| --- | --- | --- | --- |
| Database `app_role.external_code` | `REPORT_VIEW` | `ROLE_READER` | Allowed to view reports |
| Database `app_role.external_code` | `OPS_ADMIN` | `ROLE_ADMIN` | Allowed to administer internal APIs |
| JWT claim `app_roles` | `report_view` | `ROLE_READER` | Read permission from trusted issuer |
| JWT claim `app_roles` | `ops_admin` | `ROLE_ADMIN` | Admin permission from trusted issuer |
| JWT claim `scope` | `reports.read` | `SCOPE_reports.read` | OAuth2 permission issued by provider |

This table is a **contract** between the data source and the application. `OPS_ADMIN` in the DB does not have to match `ops_admin` in the JWT; both map to `ROLE_ADMIN` only because business rules permit it and the authority issuer has been verified.

You should also define: who can modify source values, which tenant applies, which claims are accepted, when permissions take effect, which source wins on conflict, and how long revocation takes. Without an explicit table, concatenating `"ROLE_" + value` on arbitrary strings easily creates unapproved permissions.

**Fail closed:** if a source value is invalid or outside the supported list, the safe choice is not to grant that authority; for inconsistent internal configuration data, you can actively reject login and log an error for administrators. Never automatically "fix" `role=superuser` into a higher-privileged role.

## 5. Example A — Java 17+ Application Loading Authorities from a Database

This complete example uses **Spring Boot 3.5.7**, **Spring Security 6.x**, Spring MVC/Servlet, in-memory H2, and JDBC. It models a real application's user–role schema to demonstrate mapping. HTTP Basic makes it easy to test permissions with `curl`. In production, replace H2 with PostgreSQL/MySQL while keeping the same principles.

### 5.1. Specific Requirements

- `GET /public`: anyone can view.
- `GET /reports`: requires `ROLE_READER`.
- `GET /admin`: requires `ROLE_ADMIN`.
- Account `alice` has DB role `REPORT_VIEW`, mapped to `ROLE_READER`.
- Account `bob` has DB role `OPS_ADMIN`, mapped to `ROLE_ADMIN`.
- No custom security filters and no manual password comparisons in controllers.

Project structure:

```text
db-authorities-demo/
├── pom.xml
└── src/main/
    ├── java/demo/DbAuthoritiesApplication.java
    └── resources/
        ├── application.yml
        └── schema.sql
```

### 5.2. Maven: `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>db-authorities-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
```

### 5.3. H2 Connection: `src/main/resources/application.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:rolesdemo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
```

The `rolesdemo` database exists only during the demo runtime; demo data is lost when the application stops. Never use in-memory H2 for production account data.

### 5.4. Schema: `src/main/resources/schema.sql`

```sql
CREATE TABLE app_user (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE app_role (
    external_code VARCHAR(50) PRIMARY KEY
);

CREATE TABLE app_user_role (
    user_id BIGINT NOT NULL,
    role_code VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, role_code),
    FOREIGN KEY (user_id) REFERENCES app_user(id),
    FOREIGN KEY (role_code) REFERENCES app_role(external_code)
);

INSERT INTO app_role (external_code) VALUES ('REPORT_VIEW');
INSERT INTO app_role (external_code) VALUES ('OPS_ADMIN');
```

Separating `app_user`, `app_role`, and the join table represents **one user having multiple roles**. In the example, each user is assigned one role to make verifying the mapping straightforward; the code below still reads a list of multiple roles.

### 5.5. Main Application: `src/main/java/demo/DbAuthoritiesApplication.java`

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DbAuthoritiesApplication {

    public static void main(String[] args) {
        SpringApplication.run(DbAuthoritiesApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(JdbcTemplate jdbc) {
        return username -> {
            List<DbUser> users = jdbc.query(
                    "SELECT id, username, password_hash, enabled "
                    + "FROM app_user WHERE username = ?",
                    (rs, rowNum) -> new DbUser(
                            rs.getLong("id"),
                            rs.getString("username"),
                            rs.getString("password_hash"),
                            rs.getBoolean("enabled")),
                    username);

            if (users.isEmpty()) {
                throw new UsernameNotFoundException("User not found");
            }

            DbUser user = users.get(0);

            List<GrantedAuthority> authorities = jdbc.query(
                    "SELECT r.external_code "
                    + "FROM app_role r "
                    + "JOIN app_user_role ur "
                    + "  ON ur.role_code = r.external_code "
                    + "WHERE ur.user_id = ?",
                    (rs, rowNum) -> new SimpleGrantedAuthority(
                            mapDatabaseRole(rs.getString("external_code"))),
                    user.id());

            UserDetails details = User.withUsername(user.username())
                    .password(user.passwordHash())
                    .disabled(!user.enabled())
                    .authorities(authorities)
                    .build();
            return details;
        };
    }

    private static String mapDatabaseRole(String externalRole) {
        return switch (externalRole) {
            case "REPORT_VIEW" -> "ROLE_READER";
            case "OPS_ADMIN" -> "ROLE_ADMIN";
            default -> throw new IllegalArgumentException(
                    "Unmapped database role: " + externalRole);
        };
    }

    @Bean
    CommandLineRunner seedDemoUsers(
            JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.update(
                    "INSERT INTO app_user(username, password_hash, enabled) "
                    + "VALUES (?, ?, ?)",
                    "alice", encoder.encode("alice-pass"), true);

            jdbc.update(
                    "INSERT INTO app_user(username, password_hash, enabled) "
                    + "VALUES (?, ?, ?)",
                    "bob", encoder.encode("bob-pass"), true);

            jdbc.update(
                    "INSERT INTO app_user_role(user_id, role_code) "
                    + "SELECT id, ? FROM app_user WHERE username = ?",
                    "REPORT_VIEW", "alice");

            jdbc.update(
                    "INSERT INTO app_user_role(user_id, role_code) "
                    + "SELECT id, ? FROM app_user WHERE username = ?",
                    "OPS_ADMIN", "bob");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/reports").hasRole("READER")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    private record DbUser(
            long id, String username, String passwordHash, boolean enabled) {}

    @RestController
    static class ApiController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/reports")
        String reports() {
            return "reports";
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
```

Key points on **how Spring Security uses the data**:

- `JdbcTemplate` fetches the user via `?` placeholders, avoiding string concatenation of `username` in SQL. The user and roles are queried from separate tables.
- `mapDatabaseRole(...)` is the mapping point **from business role code to internal authority**. Choosing an allowlist `switch` prevents new values from accidentally receiving `ROLE_ADMIN`. For real admin data, log in a controlled manner and handle misconfigurations through operational procedures.
- `UserDetailsService` is only responsible for loading the user; Spring Security's `DaoAuthenticationProvider` handles password checking via `PasswordEncoder`. Password hashes are generated with BCrypt when seeding the demo; controllers never touch passwords.
- `User.withUsername(...).authorities(authorities)` attaches permissions to the authenticated user. `hasRole("READER")` checks `ROLE_READER`, and `hasRole("ADMIN")` checks `ROLE_ADMIN`.
- The `SecurityFilterChain` bean keeps all authentication/authorization mechanisms inside the framework. `formLogin` is disabled individually so the demo uses HTTP Basic to return 401; **CSRF is not disabled** in this GET-only example.
- Seed data contains plaintext passwords in **illustrative code**; never use this approach to manage production secrets. In a real system, hashes are computed at registration/password-change time, stored in the DB, and never returned by APIs.

If your database schema already follows the structure supported by `JdbcUserDetailsManager`, you can use the standard manager and customize queries where appropriate. A custom `UserDetailsService` is only needed when the schema or mapping rules are specialized; **there is no need to write a custom AuthenticationProvider just to JOIN user–role tables**.

### 5.6. Running and Verifying Results

Requires Java 17+, Maven, and running from the directory containing `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/db-authorities-demo-0.0.1-SNAPSHOT.jar
```

In another terminal, run:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports
curl -i -u alice:alice-pass http://localhost:8080/reports
curl -i -u alice:alice-pass http://localhost:8080/admin
curl -i -u bob:bob-pass http://localhost:8080/admin
curl -i -u bob:bob-pass http://localhost:8080/reports
curl -i -u alice:wrong http://localhost:8080/reports
```

| Request | Expected HTTP status | Why |
| --- | --- | --- |
| `/public`, anonymous | **200**; body `public` | `permitAll` |
| `/reports`, anonymous | **401** | Unauthenticated |
| `/reports`, `alice` | **200**; body `reports` | DB `REPORT_VIEW` → `ROLE_READER` |
| `/admin`, `alice` | **403** | Lacks `ROLE_ADMIN` |
| `/admin`, `bob` | **200**; body `admin` | DB `OPS_ADMIN` → `ROLE_ADMIN` |
| `/reports`, `bob` | **403** | In this demo, ADMIN does not automatically include READER |
| `/reports`, wrong password | **401** | Authentication fails before permissions are checked |

**Meaningful observation:** `ROLE_ADMIN` does not inherently inherit `ROLE_READER`. If you want "ADMIN can also read reports", pick the policy `hasAnyRole("READER", "ADMIN")` or configure a controlled role hierarchy. Never assume a higher role implies every lower role.

**Example limitations:** H2 only simulates a database and does not represent connection pooling, query permissions, or real-world performance; it also lacks auditing, lockout, migrations, and automated tests. The example demonstrates the exact spot where a DB role is turned into a `GrantedAuthority`.

## 6. Hardening and Optimizing Database Mapping

### 6.1. Preventing authority lookups from becoming a security bug or bottleneck

An application with many users/roles should address:

- Indexes and unique constraints on username, and join keys on user–role; parameterized queries.
- Never return DB records or password hashes directly in HTTP responses; `UserDetails` may contain sensitive authentication fields.
- Map codes strictly from **governed data sources**. If a role is missing or malformed, never default to overly broad permissions.
- Account statuses: if disabled, locked, expired, or credentials-expired exist in the schema, reflect them in `UserDetails` accordingly.
- Caching users/authorities if genuinely needed: specify TTL and invalidation mechanisms when permissions change. Sessions or caches may retain stale authorities until re-authentication.
- Changing a role in the database **does not guarantee all existing sessions immediately lose or gain permissions**. Design session refresh/revocation or dynamic permission lookup policies when high freshness is required.

### 6.2. Coarse roles vs. fine-grained permissions

`ROLE_ADMIN` fits organizational roles; a feature-rich application may need granular permissions such as `INVOICE_APPROVE` or `REPORT_EXPORT`. You can map a DB permission table to `PERM_INVOICE_APPROVE` and check `hasAuthority("PERM_INVOICE_APPROVE")`.

Do not turn thousands of object IDs (e.g., `invoice:12345`) into thousands of `GrantedAuthority` entries. Verify actual record ownership in the service/repository, tied to the active subject and tenant. For instance, "read only your own invoices" cannot be properly solved with `ROLE_READER` alone.

### 6.3. Multi-tenant data

If two organizations both use the `ADMIN` role, a generic `ROLE_ADMIN` authority can be overly broad if code does not check the tenant. For per-tenant permissions, the safe approach is resolving `tenantId` from a trusted source and verifying tenant and object ownership in the business layer, or using clearly namespaced authorities paired with dedicated authorization logic. **Never** rely solely on a client-supplied `X-Tenant-Id` header to grant roles.

## 7. Example B — Mapping Scopes and Permission Claims in a Verified JWT

This is a **different pipeline from the database example**: the API receives `Authorization: Bearer ...`, and Spring Security acts as an OAuth2 **Resource Server**. The access token carries claims controlled by the authenticating issuer.

The illustrative payload below is the data *inside* a JWT; **being able to read the JSON does not mean the token is valid**:

```json
{
  "iss": "https://idp.example.org/realms/sample",
  "sub": "person-42",
  "aud": ["reports-api"],
  "exp": 1893456000,
  "scope": "reports.read",
  "app_roles": ["report_view", "ops_admin", "unknown_role"]
}
```

Assume the issuer is trusted and the application actually permits that issuer to manage the `app_roles` claim. Mapping goals:

- `scope: "reports.read"` → keep the standard `SCOPE_reports.read` authority.
- `app_roles: "report_view"` → add `ROLE_READER`.
- `app_roles: "ops_admin"` → add `ROLE_ADMIN`.
- `"unknown_role"` → **do not grant** any authority; do not prepend prefixes to unknown values.

Note that `sub` is the subject identifier at the issuer, not necessarily identical to the username or user ID in your DB. In many systems, a subject must be identified by the pair `issuer + sub` to avoid collisions across issuers.

### 7.1. Dependencies and JWT Verification with Spring Security

A Spring Boot Servlet application needs `spring-boot-starter-security` and `spring-boot-starter-oauth2-resource-server` (along with the web starter). The Resource Server starter provides Bearer token handling and JWT verification via the corresponding Spring Security libraries.

Example **`application.yml` in a separate Resource Server project**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/sample
```

The URI here is an **illustrative address, not a live IdP**. Replace it with your real issuer and configure appropriate validation before running end-to-end. Resource Server handles fetching public keys from metadata/JWK Set and verifying tokens as configured; customizing authorities **does not** replace token verification.

Checks to confirm:

1. **Signature and algorithm** are verified using appropriate keys and algorithms.
2. `iss` matches an allowed issuer; `exp` and `nbf` are valid.
3. `aud` matches the target API when the system requires a specific audience. **Simply setting `issuer-uri` does not mean every application audience rule is configured.**
4. The token is genuinely an **access token** intended for a resource server; do not use an ID token meant for client/OIDC login to call APIs.
5. Role claims are governed by a trusted issuer; never use roles read from client-supplied headers or from a JWT whose signature has not been verified.

### 7.2. Choosing the Right Converter

`JwtGrantedAuthoritiesConverter` reads common scope claims (`scope` or `scp`) by default and creates authorities starting with `SCOPE_`. To change only the claim name, the API offers `setAuthoritiesClaimName(...)`; to change the prefix, `setAuthorityPrefix(...)`; for string-formatted claims, a delimiter can optionally be set. However, **replacing the default converter with one that only reads `app_roles` can drop `SCOPE_...` authorities**. If an API uses both scopes and roles, combine both sets with transparent rules.

The complete configuration class below applies to **a Spring MVC Resource Server application**, as an alternative to the HTTP Basic `SecurityFilterChain` in section 5—do not leave both overlapping beans in the same demo:

**`src/main/java/demo/JwtAuthoritySecurityConfig.java`**:

```java
package demo;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtAuthoritySecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/reports")
                            .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(
                                jwtAuthenticationConverter())))
                .build();
    }

    public static JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter standardScopes =
                new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                    standardScopes.convert(jwt);
            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object claim = jwt.getClaim("app_roles");
            if (claim instanceof Collection<?> rawRoles) {
                for (Object rawRole : rawRoles) {
                    if (!(rawRole instanceof String role)) {
                        continue;
                    }
                    switch (role) {
                        case "report_view" -> authorities.add(
                                new SimpleGrantedAuthority("ROLE_READER"));
                        case "ops_admin" -> authorities.add(
                                new SimpleGrantedAuthority("ROLE_ADMIN"));
                        default -> {
                            // Values outside the allowlist do not grant permissions.
                        }
                    }
                }
            }

            return authorities;
        });

        return converter;
    }
}
```

**Reading the mechanism in order:**

- Resource Server's `JwtDecoder` must verify the token first; the converter receives a `Jwt` object that has already passed decoding/validation when a real request is processed. Invoking the converter with a mock JWT in a unit test only checks mapping, not token validity.
- `standardScopes.convert(jwt)` preserves the default `SCOPE_reports.read`. `LinkedHashSet` deduplicates authorities while keeping deterministic order for inspection.
- The `app_roles` claim is expected to be a collection. If the claim is absent, wrong type, or contains unknown items, the code **does not** grant the corresponding role.
- `JwtAuthenticationConverter` builds an `Authentication` with the new authority set; policies check `hasAuthority("SCOPE_reports.read")` or `hasRole("ADMIN")` against the actual strings.
- The example intentionally avoids altering `sub`/`iss` claims, parsing signatures manually, or writing `SecurityContextHolder` directly.
- No role hierarchy is enabled: `ROLE_ADMIN` neither includes `ROLE_READER` nor substitutes for `SCOPE_reports.read`.

**The relationship between roles and scopes must be designed:** in the example `/api/reports` requires a scope, so `ROLE_ADMIN` alone is insufficient. If an endpoint needs **both** a scope and a role, write a combined authorization rule or matching method security; if only one is needed, the policy must express that clearly. Do not treat them as synonymous.

### 7.3. Testing Mapping Without a Live IdP

In the Resource Server project, add `spring-boot-starter-test` with `test` scope. The test file below evaluates **only the mapping function**, without minting signed tokens, sending HTTP requests, or verifying signatures:

**`src/test/java/demo/JwtAuthoritySecurityConfigTest.java`**:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class JwtAuthoritySecurityConfigTest {

    @Test
    void mapsKnownRolesAndPreservesScopes() {
        Jwt jwt = Jwt.withTokenValue("mapping-fixture")
                .header("alg", "RS256")
                .claim("sub", "person-42")
                .claim("scope", "reports.read")
                .claim("app_roles", List.of(
                        "report_view", "ops_admin", "unknown_role"))
                .build();

        var authentication = JwtAuthoritySecurityConfig
                .jwtAuthenticationConverter()
                .convert(jwt);

        assertThat(authentication).isNotNull();
        List<String> names = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        assertThat(names).containsExactlyInAnyOrder(
                "SCOPE_reports.read",
                "ROLE_READER",
                "ROLE_ADMIN");
    }

    @Test
    void unknownRoleDoesNotBecomeAuthority() {
        Jwt jwt = Jwt.withTokenValue("mapping-fixture")
                .header("alg", "RS256")
                .claim("sub", "person-42")
                .claim("app_roles", List.of("superuser"))
                .build();

        var authentication = JwtAuthoritySecurityConfig
                .jwtAuthenticationConverter()
                .convert(jwt);

        assertThat(authentication).isNotNull();
        assertThat(authentication.getAuthorities()).isEmpty();
    }
}
```

Run `mvn test` in a project with test dependencies. Expected result: both tests pass. The first test ensures scopes are not lost and unknown roles are not granted; the second proves `superuser` does not turn into any authority. For production security, add **integration tests** for valid/invalid signatures, wrong issuer, wrong audience, expired tokens, and HTTP 401/403. Never treat a `Jwt.withTokenValue(...)` fixture as proof of signature verification.

### 7.4. Different Claim Shapes

Some systems use:

- `scope: "read write"` or `scp: ["read", "write"]` to represent OAuth2 scopes.
- `roles: ["ADMIN", "READER"]` or `groups: ["analytics", "admins"]`.
- `realm_access.roles`, `resource_access.<client>.roles`, or deeply nested JSON structures (provider-dependent).

`JwtGrantedAuthoritiesConverter` fits flat claims and simple prefix rules. For nested JSON or mappings needing tenant/source checks, use `Converter<Jwt, Collection<GrantedAuthority>>` as in the example, checking concrete types and allowlists. Never write a converter that grants `ROLE_ADMIN` for any claim containing the word "admin".

If the issuer uses a claim named `roles` with uniformly governed values, a minimal converter could be:

```java
JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
```

The snippet above **only maps the roles claim** if used in place of the default converter; to keep scopes as well, combine it with scope mapping as shown in the full example.

## 8. OAuth2/OIDC Login: A Different Extension Point from Resource Server

`oauth2Login` is used to **log users into a client application via a provider**. After login, the principal may be `OAuth2User` or `OidcUser`; authorities may include `OAuth2UserAuthority` / `OidcUserAuthority` along with scope authorities. Spring Security provides two mapping approaches:

1. `GrantedAuthoritiesMapper` when authorities/attributes/id token are already available from the login flow.
2. Custom/delegating `OAuth2UserService` or `OidcUserService` if you must call an extra API or database to fetch permissions, because they receive the request/access token and can assemble data before building the principal.

Example **illustrative bean placed inside an app with `oauth2Login`**, not a standalone Java program:

```java
@Bean
GrantedAuthoritiesMapper loginAuthoritiesMapper() {
    return incoming -> {
        Set<GrantedAuthority> mapped = new HashSet<>(incoming);

        for (GrantedAuthority authority : incoming) {
            if (authority instanceof OidcUserAuthority oidc) {
                Object value = oidc.getIdToken()
                        .getClaims().get("groups");

                if (value instanceof Collection<?> groups
                        && groups.contains("reporting-team")) {
                    mapped.add(new SimpleGrantedAuthority("ROLE_READER"));
                }
            }
        }
        return mapped;
    };
}
```

This snippet requires importing `GrantedAuthoritiesMapper`, `GrantedAuthority`, `SimpleGrantedAuthority`, `OidcUserAuthority`, `Set`, `HashSet`, `Collection`; it requires the provider to emit `groups` in the **ID token**, and the app should only grant roles when the issuer/claim is trusted. Not every provider puts `groups` in the ID token; it may be in UserInfo or a separate permissions service. In that situation, inspect `OidcUserService`/`OAuth2UserService` and map based on the actual returned data. Do not assume every login includes an OIDC ID token.

**Key difference:** `GrantedAuthoritiesMapper` for `oauth2Login` does not automatically apply to a Resource Server's `JwtAuthenticationToken`. If an API uses Bearer JWTs, customize `JwtAuthenticationConverter` as in section 7. Never take `groups` from an unverified JWT or HTTP header to grant permissions.

## 9. What If Permissions Live in Both a Database and an External System?

For example: the IdP only authenticates the user, while project permissions are managed by the application in its database. Explicitly design which source is authoritative:

| Model | Identity source | Authority source | When permission changes take effect |
| --- | --- | --- | --- |
| Local database | User table + password / internal provider | DB roles/permissions | When authorities are reloaded; depends on session/cache |
| Self-contained JWT | Access token signed by IdP | Claims inside JWT | Usually at next token issuance or via revocation mechanism |
| OIDC login + DB | `iss + sub` from trusted provider | DB roles queried by linked ID | On login/permission refresh or session re-creation |
| JWT + per-request permission lookup | JWT verified `iss/sub/aud` | DB/local authorization service | Near real-time, at the cost of extra latency and dependency |

**Choose a clear merging rule.** If permissions come from both IdP and DB, taking an automatic union (`union`) can unexpectedly expand privileges. Some systems require the database as the single source of truth; some require both an IdP group and an internal role (intersection of conditions); some use the IdP for authentication and the DB for authorization. Express this as an explicit policy and test conflicting-source cases.

**Link identities properly:** never join permissions by display email alone, because emails can change or collide across issuers. With OIDC, `issuer + subject` is usually a more stable linking key; in multi-tenant setups add trusted tenant boundaries. If a user is not yet linked to an internal account, grant no high privileges by default.

**Permission changes over time:** JWTs typically retain claims for the token's lifetime; login sessions may retain granted authorities; a `UserDetailsService` cache may hold stale data. When urgent revocation is needed, consider token lifetimes, proper revocation/introspection mechanisms, session invalidation, or dynamic permission checks from a trusted source. Never promise "deleting a role in the DB immediately revokes all old tokens" if the design does not actually guarantee it.

## 10. Applying Authorities at Endpoints and Methods

Mapping is meaningful only when permission checks reference the exact authority strings. Servlet configuration example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").hasRole("READER")
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/export/**")
        .hasAuthority("PERM_REPORT_EXPORT")
    .anyRequest().authenticated())
```

This is a **replacement snippet inside `SecurityFilterChain`**, not a standalone Java class. If you also use `@PreAuthorize` on services, enable `@EnableMethodSecurity` in your configuration and verify with tests. Example:

```java
@PreAuthorize("hasAuthority('PERM_REPORT_EXPORT')")
public byte[] exportReport(long reportId) {
    // Still must check whether reportId belongs to the user's tenant.
    // ...
}
```

**Global** roles/permissions do not replace **per-object** permission checks. Someone with `ROLE_READER` may be allowed to view reports, yet not necessarily read another tenant's report. Conditions such as owner ID, tenant, invoice status, and project scope must be verified at the business/data-access layer.

With proxy-based Spring Method Security, internal calls within the same class (`self-invocation`) may bypass the proxy; do not design critical access controls relying solely on the assumption that every call is intercepted.

## 11. Reactive/WebFlux: Same Principles, Right APIs

In Spring WebFlux, the common counterparts are:

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `JwtAuthenticationConverter` for Servlet Resource Server | `ReactiveJwtAuthenticationConverter` or `ReactiveJwtAuthenticationConverterAdapter` |
| `OAuth2UserService` / `OidcUserService` | `ReactiveOAuth2UserService` with matching request/user types |

Example **bean sketch for a WebFlux Resource Server application with a real issuer configured**, using an adapter to reuse a synchronous converter when mapping is purely in-memory without blocking I/O:

```java
@Bean
SecurityWebFilterChain reactiveApi(ServerHttpSecurity http) {
    var adapter = new ReactiveJwtAuthenticationConverterAdapter(
            JwtAuthoritySecurityConfig.jwtAuthenticationConverter());

    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(jwt -> jwt.jwtAuthenticationConverter(adapter)))
            .build();
}
```

This is an **illustrative configuration snippet** requiring imports for `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtAuthenticationConverterAdapter`, and the matching converter from the JWT project. Do not attach servlet `Filter`/`OncePerRequestFilter` to WebFlux. If reactive DB queries are needed for permissions, use a reactive repository and an extension point supporting `Mono`/`Flux`; never invoke JDBC/blocking APIs on the event loop.

## 12. Common Security Mistakes When Mapping Authorities

1. **Trusting claims before verifying the token:** Base64-decoding a JWT or reading a request header and assigning roles. Verify signature, issuer, timestamps, and audience per policy before using claims.
2. **Concatenating `ROLE_` with arbitrary input:** an `ADMIN` string sent by an untrusted source could produce `ROLE_ADMIN`. Require an authoritative permission source, an allowlist, and validation.
3. **Equating `scope` and `role`:** by default `SCOPE_reports.read` does not satisfy `hasRole("READER")`. Only map between them when business rules explicitly define it.
4. **Replacing the mapper and losing default scopes:** a new converter that only reads `app_roles` causes APIs requiring `SCOPE_...` to suddenly return 403. Keep scopes or intentionally omit them, and write tests proving it.
5. **Misunderstanding the `ROLE_` prefix:** `hasRole("ADMIN")` checks `ROLE_ADMIN` by default, whereas `hasAuthority("ADMIN")` requires the exact literal `ADMIN`.
6. **Username/email collisions across issuers or tenants:** joining permissions on the wrong account can escalate privileges. Use verified identifier keys and tenant boundaries.
7. **Auto-assigning a high role when a claim is empty:** e.g., defaulting to ADMIN when groups are absent "just to make it work". Fail closed; missing claims must be treated as missing permissions.
8. **Ignoring revocation timing:** old tokens or sessions retain authorities even after the role table is updated. Define concrete refresh/revocation strategies.
9. **Relying solely on URL checks:** skipping object-level authorization in services allows reading someone else's data via arbitrary IDs.
10. **Using user-defined metadata as permission proof:** custom request parameter `role=admin`, cookies, untrusted headers, and unverified emails must never be turned into authorities.
11. **Leaving role hierarchy assumptions unverified:** if admins need reader permissions, configure the hierarchy explicitly, test permission directions, and avoid unexpected access expansion.
12. **Putting sensitive role codes or raw claims into logs or responses:** audits need sufficient traceability without dumping tokens, passwords, or unnecessary personal data.

## 13. QA Checklist and Exercises

Before deploying mappings, verify these conditions:

- [ ] A mapping table from each source to `GrantedAuthority` is defined, owned, and tested.
- [ ] Every role/claim source is verified, with clear issuer/tenant boundaries.
- [ ] Missing claims, wrong types, unknown roles, or disabled accounts do not grant extra permissions.
- [ ] `hasRole`, `hasAuthority`, and `@PreAuthorize` check the exact strings the converter actually produces.
- [ ] Outcomes for users with multiple roles, no roles, a revoked role, and users in another tenant are tested.
- [ ] When customizing JWTs, default `SCOPE_...` authorities remain intact if required by policy.
- [ ] Verified 401 when unauthenticated and 403 when identified but lacking permissions; distinguished CSRF errors on state-changing requests.
- [ ] A policy exists for updating authorities after changes to DB, groups, tokens, or sessions.
- [ ] No manual JWT parsing, no roles granted from arbitrary client input, and no credentials leaked in responses/logs.

**Self-practice:**

1. The DB table holds `REPORT_VIEW`, and the rule is `hasRole("READER")`. Why must it be mapped to `ROLE_READER` instead of returning the raw value?
2. A JWT carries `scope=reports.read` and `app_roles=["ops_admin"]`. Why can merely calling `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName("app_roles")` break scope-based rules?
3. An application trusts two IdPs that both have a user with `sub=123`. What happens if database permissions are queried by `sub` alone without checking the issuer?
4. An admin's role is removed in the database, yet an old JWT still contains `ops_admin`. How can permission revocation be handled, and what is the latency of each option?
5. Why is OAuth2 Login's `GrantedAuthoritiesMapper` not the default hook for Resource Server JWTs?
6. Is someone with `ROLE_READER` automatically allowed to read every invoice record? If not, what additional kind of policy is needed?

## 14. Official Reference Documentation

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet OAuth2 Resource Server JWT (6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security — OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)

**Takeaway:** authority sources may live in a database, access-token claims, or provider user info; the extension point must match the **authentication path**, and mapping must be controlled before policies use the `GrantedAuthority` set to grant access.
