# Loading Authorities, Group Authorities, and Avoiding Unnecessary Repeated Queries in Spring Security

> **Scope:** Spring Security Authentication in Servlet/Spring MVC applications. The core topic is how `UserDetailsService` loads **direct authorities**, **authorities from user groups**, builds `GrantedAuthority` instances, and avoids **N+1** repeated-query pitfalls. The lesson includes a standalone **Spring Boot 3.5.x, Java 17+, Spring JDBC, and H2** example, along with implementation guidance for Spring Data JPA. It clearly distinguishes query efficiency, identity data protection, authority updates, and session/cache lifecycles.

## 1. Objectives of This Lesson

After this lesson, you should be able to:

1. Diagram the relationships **account → direct authorities** and **account → groups → group authorities**, explaining union and deduplication rules.
2. Understand why `DaoAuthenticationProvider` relies on `UserDetailsService.loadUserByUsername(...)` to supply `UserDetails` with trustworthy authorities.
3. Recognize N+1: one query fetches the list of groups, followed by one query **per group** to fetch its authorities.
4. Aggregate authorities using **set-based queries**, projections/batch loading, or proper fetch configurations instead of eagerly loading every association by default.
5. Construct properly formatted `GrantedAuthority` lists, granting authorities only from trusted data stores and distinguishing roles from business permissions.
6. Measure SQL query counts rather than guessing; inspect the impact of indexes, authority set size, group hierarchies, and request concurrency.
7. Explain cache limitations: an authority revoked in the database does not necessarily take effect immediately for existing sessions, tokens, or cached `UserDetails`.
8. Implement a runnable demo and test cases for direct authorities, group-inherited authorities, overlapping authorities, and insufficient authorities.

**Key design question:** if a user belongs to 30 groups, does the application really need 30 DB queries to determine their authorities? **No.** When the data is modeled properly, aggregation can be performed in one SQL query or a small fixed number of batch queries independent of group count.

## 2. Where Authority Loading Fits in the Authentication Flow

```text
HTTP request containing username/password
    ↓
Spring Security authentication filter
    ↓
AuthenticationManager (usually ProviderManager)
    ↓
DaoAuthenticationProvider
    ├── UserDetailsService.loadUserByUsername(username)
    │    ├── fetches account and status
    │    ├── fetches direct authorities
    │    ├── fetches valid groups
    │    ├── fetches group authorities (set-based, avoiding N+1)
    │    └── returns UserDetails with GrantedAuthority
    └── PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Authenticated Authentication (principal + authorities)
    ↓
SecurityContext
    ↓
Authorization rule: hasRole / hasAuthority / method security
```

`UserDetailsService` does not verify the password itself in the standard flow; it loads the data needed by `DaoAuthenticationProvider`. Authorities are read from the account/organization store and **placed into `UserDetails.getAuthorities()`**. After authentication, rules such as `hasRole(...)`, `hasAuthority(...)`, and `@PreAuthorize` can evaluate those authorities.

One critical point to understand: the authority list is a **snapshot at authentication time**. With sessions, the result may be persisted and subsequent requests will not reload authorities. With stateless HTTP Basic, the account is usually loaded when credentials are processed on each request; however, caches or other authentication mechanisms can change that behavior. Never equate "a request arrived" with "`loadUserByUsername` definitely ran".

## 3. Data Model: Direct Authorities and Group Authorities

Suppose a document management system has the following tables:

| Table | Contents | Example |
| --- | --- | --- |
| `app_account` | Internal ID, username, password hash, enabled | `mai`, `an` |
| `account_authority` | Authorities granted directly to an account | `mai → ROLE_READER` |
| `security_group` | Catalog of user groups | `content-editors` |
| `group_membership` | Which users belong to which groups | `mai → content-editors` |
| `group_authority` | Roles/authorities granted to a group | `content-editors → ROLE_EDITOR` |

```text
Account: mai
   ├── direct authority: ROLE_READER
   └── member of: content-editors
           ├── ROLE_EDITOR
           └── documents:write

Effective authorities for mai:
   ROLE_READER
   ROLE_EDITOR
   documents:write
```

In this lesson, **"effective authorities" are the union of direct authorities and authorities from active groups**. This is a rule chosen for learning; real systems may include deny rules, precedence order, effective time windows, group hierarchies, or per-tenant conditions. Do not blindly apply a simple union when a system has **deny overrides** or special conflict rules.

### Distinguishing Groups, Roles, and Permissions

- **Group**: an organizational structure or membership collection, such as `content-editors`. A group by itself is not necessarily an authority for `hasRole`.
- **Role**: a grouped authority represented as an authority string, such as `ROLE_EDITOR` or `ROLE_READER`.
- **Permission**: an application-level capability, such as `documents:write` or `documents:read`.
- **GrantedAuthority**: the object Spring Security uses to represent an assigned authority. A simple implementation is `new SimpleGrantedAuthority("ROLE_EDITOR")`.

`hasRole("EDITOR")` checks the authority `ROLE_EDITOR` by default; `hasAuthority("documents:write")` checks the exact string. Do not put a group name like `content-editors` into authorities and expect `hasRole("EDITOR")` to automatically recognize it as the editors group.

**Clear naming design:** apply a consistent convention such as `ROLE_...` for roles and `resource:action` for permissions. When mapping authorities in the DB, validate strings, avoid generating `ROLE_ROLE_EDITOR`, and never trust authorities submitted by the frontend.

### What Edge Cases Need to Be Considered?

1. User belongs to two groups that both grant `ROLE_EDITOR` → **only one effective authority** should exist.
2. User has `ROLE_READER` both directly and via a group → also deduplicate.
3. User belongs to no groups → can still have direct authorities or empty authorities.
4. Disabled group or expired membership → filter by status/flags before granting authorities; the demo schema does not include these columns yet.
5. Authorities scoped per tenant/organization → constrain the query to the right namespace so a same-named group from another tenant is never pulled in.
6. Login via JWT/OIDC → may receive authorities from an issuer/converter; never blindly merge all external claims into internal authorities without trust rules.

## 4. How the N+1 Problem Appears

### Inefficient Loading

Suppose we do:

```java
// Pseudocode illustrating the anti-pattern; not a standalone runnable class.
Account user = accountRepository.findByUsername(username).orElseThrow();
List<Group> groups = groupRepository.findGroupsOfUser(user.getId());

Set<String> codes = new HashSet<>(user.getDirectAuthorities());
for (Group group : groups) {
    // Wrong approach: each group triggers a separate query.
    codes.addAll(groupAuthorityRepository.findCodesByGroupId(group.getId()));
}
```

If there are N groups, the group lookup alone can cost:

```text
1 SELECT user
1 SELECT group memberships
N SELECT group authorities (1 per group)
+ additional SELECTs for direct authorities or lazy relations
--------------------------------------------------------------
At least N + 2 SELECTs in the illustrated path
```

For example, with N = 30, a single request can trigger 32 or more SELECTs; 100 concurrent requests to the same endpoint rapidly spike DB load. With an ORM, N+1 can also **hide inside loops calling getters** like `group.getAuthorities()` or when mapping DTOs/`UserDetails` after loading an entity.

N+1 describes **the number of DB round-trips growing with the number of items** to load. Do not confuse this with a single query returning many rows: one query returning 300 authority rows has a completely different cost profile from 300 round-trips. Large result sets still consume bandwidth and memory, so the goal is not blindly cramming everything into one massive SQL query regardless of cardinality.

### The Right Way: Computing Authorities as a Set

A solid approach is **two SELECTs per user load**, independent of the number of groups:

1. SELECT the account and status by `username` (using a unique index).
2. SELECT effective authorities using **`UNION`** across direct authorities and group authorities. The database handles joins and deduplication using indexes.

```sql
SELECT authority_code
FROM (
    SELECT da.authority_code
    FROM account_authority da
    WHERE da.account_id = ?

    UNION

    SELECT ga.authority_code
    FROM group_membership gm
    JOIN group_authority ga
      ON ga.group_id = gm.group_id
    WHERE gm.account_id = ?
) resolved
ORDER BY authority_code;
```

`UNION` deduplicates by default. If you want `UNION ALL` to optimize certain databases, deduplicate in Java using a `Set` or `distinct` and verify performance on real data. Deterministic ordering makes testing and troubleshooting easier, though **authority order has no authorization significance**.

This SQL snippet uses the schema from this lesson; table and column names must match your project's schema. When disabled groups or expiring memberships exist, add the filter conditions to the proper JOIN rather than filtering only in the UI.

## 5. Strategies for Avoiding Repeated Queries

| Technique | Best suited when | What to check |
| --- | --- | --- |
| Single query with JOIN/UNION/projection | Authorities span a few normalized tables and need a snapshot load | Indexes, actual row count, deduplication, and tenant filtering |
| Two steps: fetch account, fetch all account authorities | You want to keep the account query simple | Stable SELECT count, sensible snapshot |
| Batch query `WHERE group_id IN (...)` | You already have the group list and need authorities for many groups | Chunk batches if exceeding parameter limits; avoid calling inside a `for` loop |
| Scoped Spring Data JPA `@EntityGraph` | You need one controlled association loaded with the entity | Does not automatically solve deeply nested associations |
| JPQL constructor projection / interface projection | You only need authority codes, not a large entity graph | Avoid N+1 from lazy getters; validate JPQL and projection types |
| Hibernate batch fetching (`@BatchSize` / batch config) | Lazy loading cannot be fully eliminated in some flows | Collapses N+1 into batched queries, though still multiple queries |
| Caching authority snapshot with TTL/invalidation | Authorization source is expensive with frequent re-authentication | Authority staleness, revocation, password hashes, and shared mutable state |

**Do not set `FetchType.EAGER` on every association** to fix N+1: a user with many groups where each group has many roles/permissions can cause a Cartesian product, huge result sets, or exceptions when fetching multiple bags. Fetch only the attributes actually needed. With JPA, count executed SQL statements in tests with many groups rather than assuming `@EntityGraph` or `JOIN FETCH` is enough.

If a role hierarchy is already handled by `RoleHierarchy` at the authorization layer, decide explicitly whether to **materialize all inherited authorities into `Authentication.getAuthorities()`** or let Spring Security apply the role hierarchy at evaluation time. Avoid expanding them twice uncontrollably.

## 6. Complete Spring Boot Example: Loading User + Authorities in Two SELECTs

The project uses **Spring JDBC** so SQL is clearly visible without hidden ORM lazy-loading behavior. The demo uses stateless HTTP Basic login; each account load (when the provider processes credentials) runs exactly **two SELECTs** in `UserDetailsService`: one for the account, one for the aggregated authority list. Data lives in in-memory H2 and is for learning only.

### 6.1. Directory Structure

```text
authority-loading-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/demo/authorities/AuthoritiesDemoApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/dev/demo/authorities/AuthoritiesDemoApplicationTests.java
```

Requires JDK 17+ and a Gradle version compatible with Spring Boot 3.5.

`settings.gradle`:

```groovy
rootProject.name = 'authority-loading-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:authoritiesdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Demo: do not expose H2 Console or enable SQL logging with credentials.
```

### 6.2. Normalized Schema and Indexes

`src/main/resources/schema.sql`:

```sql
CREATE TABLE app_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE security_group (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE account_authority (
    account_id BIGINT NOT NULL REFERENCES app_account(id),
    authority_code VARCHAR(160) NOT NULL,
    PRIMARY KEY (account_id, authority_code)
);

CREATE TABLE group_membership (
    account_id BIGINT NOT NULL REFERENCES app_account(id),
    group_id BIGINT NOT NULL REFERENCES security_group(id),
    PRIMARY KEY (account_id, group_id)
);

CREATE TABLE group_authority (
    group_id BIGINT NOT NULL REFERENCES security_group(id),
    authority_code VARCHAR(160) NOT NULL,
    PRIMARY KEY (group_id, authority_code)
);

CREATE INDEX idx_group_membership_by_group
    ON group_membership(group_id);
```

The unique index on `username` supports account lookup; the composite primary keys on `account_authority` and `group_membership` optimize queries by `account_id`; the primary key `group_authority(group_id, authority_code)` supports joining by group ID. Depending on the real DB and data distribution, inspect `EXPLAIN`/query plans instead of assuming an index is always effective.

In multi-tenant systems, unique constraints and query predicates must include `tenant_id` or the corresponding identity key. This simple schema intentionally **omits tenancy** to focus on the account → group → authority relationship.

### 6.3. Complete Java Application

Create `src/main/java/dev/demo/authorities/AuthoritiesDemoApplication.java`:

```java
package dev.demo.authorities;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthoritiesDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthoritiesDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    CommandLineRunner seed(JdbcTemplate db, PasswordEncoder encoder) {
        return args -> {
            // Demo only: initialize password hashes using BCrypt.
            db.update(
                    "INSERT INTO app_account "
                            + "(username, password_hash, enabled) VALUES (?, ?, ?)",
                    "mai", encoder.encode("demo-pass-123"), true);
            db.update(
                    "INSERT INTO app_account "
                            + "(username, password_hash, enabled) VALUES (?, ?, ?)",
                    "an", encoder.encode("demo-pass-123"), true);
            db.update(
                    "INSERT INTO security_group (group_name) VALUES (?)",
                    "content-editors");

            Long maiId = db.queryForObject(
                    "SELECT id FROM app_account WHERE username = ?",
                    Long.class, "mai");
            Long anId = db.queryForObject(
                    "SELECT id FROM app_account WHERE username = ?",
                    Long.class, "an");
            Long editorsId = db.queryForObject(
                    "SELECT id FROM security_group WHERE group_name = ?",
                    Long.class, "content-editors");

            db.update(
                    "INSERT INTO account_authority VALUES (?, ?)",
                    maiId, "ROLE_READER");
            db.update(
                    "INSERT INTO account_authority VALUES (?, ?)",
                    anId, "ROLE_READER");
            db.update(
                    "INSERT INTO group_membership VALUES (?, ?)",
                    maiId, editorsId);
            db.update(
                    "INSERT INTO group_authority VALUES (?, ?)",
                    editorsId, "ROLE_EDITOR");
            db.update(
                    "INSERT INTO group_authority VALUES (?, ?)",
                    editorsId, "documents:write");

            // Mai receives ROLE_READER directly.
            // ROLE_EDITOR and documents:write come from the group.
        };
    }
}

@Configuration
class DemoSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/me").authenticated()
                    .requestMatchers("/editor/ping").hasRole("EDITOR")
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }
}

@Service
class DatabaseAccountUserDetailsService implements UserDetailsService {
    private final JdbcTemplate jdbc;

    DatabaseAccountUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        // SELECT #1: fetch exactly one account (username is unique).
        List<AccountRow> accounts = jdbc.query(
                "SELECT id, username, password_hash, enabled "
                        + "FROM app_account WHERE username = ?",
                (rs, rowNum) -> new AccountRow(
                        rs.getLong("id"),
                        rs.getString("username"),
                        rs.getString("password_hash"),
                        rs.getBoolean("enabled")),
                username);

        if (accounts.isEmpty()) {
            throw new UsernameNotFoundException("Account not found");
        }

        AccountRow account = accounts.get(0);

        // SELECT #2: one query combining both direct and group authorities.
        String sql = """
                SELECT authority_code
                FROM (
                    SELECT da.authority_code
                    FROM account_authority da
                    WHERE da.account_id = ?

                    UNION

                    SELECT ga.authority_code
                    FROM group_membership gm
                    JOIN group_authority ga
                      ON ga.group_id = gm.group_id
                    WHERE gm.account_id = ?
                ) resolved
                ORDER BY authority_code
                """;

        List<GrantedAuthority> authorities = jdbc.query(
                sql,
                (rs, rowNum) -> new SimpleGrantedAuthority(
                        rs.getString("authority_code")),
                account.id(), account.id());

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities(authorities)
                .build();
    }

    private record AccountRow(
            long id, String username, String passwordHash, boolean enabled) {}
}

@RestController
class MeController {
    record MeResponse(String username, List<String> authorities) {}

    @GetMapping("/me")
    MeResponse me(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return new MeResponse(authentication.getName(), names);
    }

    @GetMapping("/editor/ping")
    String editorPing() {
        return "editor-ok";
    }
}
```

**Explanation of the key parts:**

1. `DatabaseAccountUserDetailsService` executes only **two SELECT queries** per successful `loadUserByUsername(...)` call: the account query and the aggregated authorities query. The query count **does not grow with the number of groups**; result row count and JOIN cost still depend on the data.
2. Uses `?` bind parameters via `JdbcTemplate` rather than concatenating username into SQL, preventing SQL injection.
3. `UNION` removes duplicate authorities if a user has the same authority both directly and through a group.
4. `User.withUsername(...).authorities(...)` builds a principal with trusted `GrantedAuthority` instances; the application **does not need** a custom `UserDetails` just to retrieve roles.
5. `DaoAuthenticationProvider`, configured by Spring Security with `UserDetailsService` and `PasswordEncoder`, verifies the password hash; the authority-loading service **never compares passwords itself**.
6. `hasRole("EDITOR")` checks `ROLE_EDITOR`. User `mai` obtains that authority **via the group**, while `an` only has `ROLE_READER`.
7. `STATELESS` with HTTP Basic lets the demo check credentials per request. This is not the default design for browser form logins; for browsers sending cookies, evaluate CSRF and session management.
8. `schema.sql` runs when the H2 DB starts, and then `CommandLineRunner` inserts demo data. The two usernames/passwords in the example **must never be used in real environments**.

### 6.4. Running from the Terminal

In the `authority-loading-demo` directory, run with a Java 17-compatible Gradle:

```bash
gradle bootRun
```

If you generated the Gradle Wrapper, use `./gradlew bootRun` on macOS/Linux or `gradlew.bat bootRun` on Windows. Send requests from another terminal:

```bash
curl -i -u mai:demo-pass-123 http://localhost:8080/me
curl -i -u mai:demo-pass-123 http://localhost:8080/editor/ping
curl -i -u an:demo-pass-123 http://localhost:8080/me
curl -i -u an:demo-pass-123 http://localhost:8080/editor/ping
curl -i http://localhost:8080/me
```

On Windows PowerShell, replace `curl` with `curl.exe` to avoid the alias. Only enter demo passwords; never pass real passwords in shell commands that easily end up in command history.

Core results:

| Request | Status | Response on success |
| --- | --- | --- |
| `mai` → `GET /me` | **200** | `{"username":"mai","authorities":["ROLE_EDITOR","ROLE_READER","documents:write"]}` |
| `mai` → `GET /editor/ping` | **200** | `editor-ok` |
| `an` → `GET /me` | **200** | `{"username":"an","authorities":["ROLE_READER"]}` |
| `an` → `GET /editor/ping` | **403** | Lacks `ROLE_EDITOR` |
| Unauthenticated → `GET /me` | **401** | HTTP Basic challenge |
| Wrong password → `GET /me` | **401** | Returns no principal data |

In `mai`'s authority list, **`ROLE_EDITOR` and `documents:write`** come from the `group_authority` table, even though the account does not hold those two authorities directly. That is the primary behavior demonstrated in this lesson.

### 6.5. Testing with MockMvc

Create `src/test/java/dev/demo/authorities/AuthoritiesDemoApplicationTests.java`:

```java
package dev.demo.authorities;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthoritiesDemoApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void directAndGroupAuthoritiesAreLoaded() throws Exception {
        mvc.perform(get("/me")
                        .with(httpBasic("mai", "demo-pass-123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("mai"))
                .andExpect(jsonPath("$.authorities",
                        hasItems("ROLE_READER",
                                "ROLE_EDITOR",
                                "documents:write")));
    }

    @Test
    void groupRoleControlsEditorEndpoint() throws Exception {
        mvc.perform(get("/editor/ping")
                        .with(httpBasic("mai", "demo-pass-123")))
                .andExpect(status().isOk());

        mvc.perform(get("/editor/ping")
                        .with(httpBasic("an", "demo-pass-123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingOrBadCredentialIsRejected() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                        .with(httpBasic("mai", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
gradle test
```

These tests prove that **authorities from groups flow into authorization** and that the real HTTP Basic login path works. However, they **do not prove the query count by themselves**. To verify there is no N+1, add a SQL count assertion during login for a user belonging to many groups.

## 7. Measuring Real Queries and Writing Tests to Catch N+1

### 7.1. How to Measure?

- With Spring JDBC, use a DataSource proxy, JDBC tracing/metrics, or DB SQL inspection tools in dev/test, filtering only `SELECT` statements from `loadUserByUsername`.
- With Spring Data JPA/Hibernate, enable Hibernate statistics or use a query-counting tool. Count executed SQL statements, not just repository method calls.
- Measure **cold login**, **warm cache**, and **already-authenticated session** requests separately. The three scenarios follow very different code paths.
- Exclude schema creation/seeding queries and controller business queries from the authority-loading count.

### 7.2. Measurement Scenario

Create 1 user belonging to N groups; each group has several permissions, with some overlapping permissions. Run with N = 1, 5, 20, 100. For the JDBC demo:

```text
Case N=1   -> Account SELECT: 1; authorities UNION SELECT: 1
Case N=5   -> Account SELECT: 1; authorities UNION SELECT: 1
Case N=20  -> Account SELECT: 1; authorities UNION SELECT: 1
Case N=100 -> Account SELECT: 1; authorities UNION SELECT: 1
```

These are the **SELECT counts issued by the demo method** when the account exists, not measured DB latency benchmarks. If another implementation fires N SELECTs for group rights, N+1 still exists. Beyond query count, measure total rows, execution time, CPU, and query plans: one huge join can still be slow even in a single round-trip.

### 7.3. Tests That Truly Catch Repeated Queries

A test asserting only that `getAuthorities()` has three elements **is not enough** to catch N+1. Add a test that:

1. Inserts a user with 50 group/role associations (including overlapping authorities).
2. Clears or disables caches for a cold authentication run if measuring baseline queries.
3. Calls `loadUserByUsername` or the authentication manager through a real test path.
4. Counts SELECTs during that call; with the two-SELECT solution, the count stays constant as groups increase.
5. Asserts the effective authority set matches the data with zero duplicates.
6. Re-runs when a group is deleted or permissions change, verifying invalidation and session state per policy.

Using a test-container database matching production yields more reliable results than measuring H2 alone. `EXPLAIN ANALYZE` and timing statistics become valuable at larger data scales; H2 is a learning environment and does not accurately predict PostgreSQL/MySQL query planners.

## 8. What If the Project Uses Spring Data JPA?

Spring Data JPA typically maps `Account`, `Group`, `Role`, and their relationships via annotations. There are two distinct issues: **round-trip count** and **size of the loaded graph**.

### 8.1. Avoiding Lazy-Loading Loops

```java
// Pseudocode illustrating the anti-pattern; classes and entities not declared.
Account account = repository.findByUsername(username).orElseThrow();

for (Group group : account.getGroups()) {
    for (Role role : group.getRoles()) {
        authorities.add(new SimpleGrantedAuthority(role.getCode()));
    }
}
```

If `groups` or `roles` are LAZY, the getters can trigger SQL per group inside the loop. That is still N+1 even though the initial repository call was a single line.

### 8.2. JPA Implementation Options

**Option 1 — Projection for authority codes:** write a repository query using JOINs/predicates by account ID that returns a list of `String`/projection. Convert codes into `SimpleGrantedAuthority`. This avoids hydrating a full entity graph.

**Option 2 — Fetch account first, fetch authorities second:** `findByUsername(...)` loads just the account; a second query returns all direct and group authorities. Depending on the database, this may use two repository methods or a native `UNION` query. The query count stays small and constant.

**Option 3 — `@EntityGraph` on specific associations:** use when you genuinely need the related entities and cardinality is moderate:

```java
// JPA snippet requiring appropriate Account entity and AccountRepository.
@EntityGraph(attributePaths = {"groups"})
Optional<Account> findByUsername(String username);
```

This is **not an automatic fix** for authorities nested inside `group.roles`. Accessing `group.getRoles()` repeatedly afterward can still emit additional queries. Using `@EntityGraph(attributePaths={"groups","groups.roles"})` or multiple `JOIN FETCH` clauses on large collections risks **row multiplication** or even `MultipleBagFetchException` when fetching multiple bags; measure and pick according to mapping structure.

**Option 4 — Hibernate batch fetching:** use `@BatchSize`/`hibernate.default_batch_fetch_size` when lazy loading is unavoidable. It collapses N queries into fewer batched queries, though it does not guarantee a single SELECT.

**Option 5 — DTO projection with native SQL:** useful when joins/unions are complex or explicit performance control is required. Watch SQL dialects, table names, schema migrations, and test on a real DB.

### 8.3. Transaction Boundary

In JPA, if `UserDetailsService` accesses lazy relationships **outside a transaction**, `LazyInitializationException` can occur. The proper solution is **defining appropriate fetches/queries and transactions**, materializing the `UserDetails` snapshot at the service layer. Never enable Open Session in View as a workaround for N+1; doing so can push unexpected queries into controllers/serializers.

Example of annotating the user-loading method with `@Transactional(readOnly=true)` when needed (snippet):

```java
@Override
@Transactional(readOnly = true)
public UserDetails loadUserByUsername(String username) {
    // 1. Query account; 2. Query authorities in batch;
    // 3. Create UserDetails snapshot before the transaction ends.
    // Specific repository/entity implementation provided by the application.
}
```

`@Transactional(readOnly=true)` does not turn multiple queries into one query and is not a promise that blocks updates from all other threads; it mainly manages the transaction and provides hints to the persistence provider. Loading data efficiently remains the responsibility of query design.

## 9. Authority Caching: Conditional Optimization Without Trading Off Security

Systems that authenticate very frequently (for example, stateless Basic APIs) may cache `UserDetails` to reduce DB load. Spring Security provides `CachingUserDetailsService`/`UserCache` and integrates with Spring caching such as `@Cacheable`. However, **`UserDetails` holds the password hash and status flags**, so caching must be designed carefully.

### 9.1. Caching Does Not Mean Authority Updates Take Effect Immediately

Suppose `mai` currently has `ROLE_EDITOR`, and an admin revokes the authority in the DB:

```text
t0: loadUserByUsername -> authorities = [ROLE_EDITOR, ROLE_READER]
t1: admin removes ROLE_EDITOR in DB
t2: cache / existing HTTP session still holds old snapshot
t3: new requests may still see ROLE_EDITOR
t4: cache evict / session invalidated / token expired / revalidate
    -> updated authorities take effect per policy
```

**Business question:** must a revoked permission take effect within 5 seconds, 5 minutes, or immediately? There is no universal answer. That requirement dictates TTL, eviction, session revocation, and refresh workflows.

### 9.2. Risks with Password Hashes and eraseCredentials

By default, `ProviderManager` calls `eraseCredentials()` on successful authentication if the result/principal implements `CredentialsContainer`. `org.springframework.security.core.userdetails.User` implements credential erasure. If a cached `UserDetails` is the **exact same object instance** used as the result's principal, erasure can wipe the password hash from the cached entry and cause subsequent authentications to fail.

Options to consider:

1. **Do not cache `UserDetails` containing hashes** when login volume is modest or server sessions already exist, avoiding risk and simplifying invalidation.
2. **Cache non-sensitive domain data/authority IDs** separately, and construct a fresh `UserDetails` on each authentication; monitor remaining query counts and never put secrets into unprotected caches.
3. **Use a copy/distinct object for the authenticated principal** if using a custom provider, so credential erasure does not mutate the cached user object.
4. When intentionally using `CachingUserDetailsService`/`@Cacheable` per Spring Security docs, you may need to **adjust the credential erasure policy** to retain the password hash for future checks. This is a real security trade-off: only do it when you understand memory/cache exposure, TTL, cache protection, and eviction; never disable credential erasure globally just as a quick workaround.

**Distinguish clearly:** caching `UserDetails` for password re-verification, caching **effective authorities** to reduce SQL, and storing `Authentication` in **`SecurityContext`/session** are three distinct layers with different revocation lifecycles.

### 9.3. Cache Keys and Invalidation

- Cache keys should include **namespace/tenant + stable account ID**, or a canonicalized username guaranteed unique under the actual lookup semantics.
- When passwords change, accounts are locked, group memberships change, roles are edited/deleted, or tenants change, identify all affected cache entries.
- When a group's role changes, invalidate entries for **all members of that group**, not just the admin who performed the edit.
- Across multiple servers, eviction must propagate or rely on TTL/versioning/revalidation; one node's local cache can diverge from another's.
- A `security_version`/`authority_version` column can help detect stale snapshots when timely permission updates matter.
- Never place raw passwords, access tokens, raw `Authentication`, or unnecessary personal data into shared caches or logs.

### 9.4. Should Every Group Graph Always Be Cached?

Not necessarily. If group/role counts are small and SQL queries are well-indexed, **two clean SELECTs** are often fast enough and much easier to maintain. Caching reduces queries at the cost of invalidation complexity, stale-authorization risk, and harder debugging. Measure p95/p99 latency, DB load, and permission change frequency before adding caches.

## 10. Authorization, Role Hierarchy, and Resource-Level Permissions

Authorities are attached to `Authentication` so Spring Security can make access decisions. Distinguish three layers:

1. **Authentication:** verifies identity and loads trusted authorities.
2. **Application-wide authority authorization:** `hasRole("EDITOR")`, `hasAuthority("documents:write")`.
3. **Resource-level authorization:** a user with `documents:write` still **must not edit documents belonging to another tenant** or another owner.

For example, `@PreAuthorize("hasAuthority('documents:write')")` checks the general permission, yet verifying that document #123 belongs to a valid tenant still requires object-level service/policy checks. Never create millions of `GrantedAuthority` strings like `DOCUMENT_123_WRITE` to replace resource ownership when the system manages many documents.

### Group Hierarchy, Role Hierarchy, and Nested Groups

If group `senior-editors` is a member of group `editors`, the demo model **does not automatically resolve nested groups**. Supporting nesting requires defining inheritance direction, cycles, depth limits, and closure traversal; consider recursive SQL CTEs or a controlled closure table. Never write recursive traversal without cycle detection.

Spring Security's `RoleHierarchy` helps authorization understand relationships like `ROLE_ADMIN > ROLE_EDITOR`. That is a separate mechanism from **which database groups a user belongs to**. If using both, define which authorities are materialized at login and which are inferred at authorization time to avoid granting broader permissions than intended.

### Authorities Coming from an IdP or Token

A JWT access token carries scopes/roles from an issuer; the principal may be a `Jwt` rather than `UserDetails`. If an application combines DB authorities with token claims, define rules for checking issuer, audience, tenant, and source of truth. Never take a client-supplied `roles` array and pass it straight into `SimpleGrantedAuthority` without verification.

## 11. Consistency and Security Rules for Authority Data

**Do not cache blindly, do not overfetch, and do not trust external data just because it looks like a role code.** Checklist:

- `username` has a unique index in the proper namespace, independent of display name.
- `password_hash` is stored with an appropriate encoder; the service only loads the hash and never logs or serializes it.
- `account.enabled` and other status flags are checked properly; if the schema has `locked`/`expired`, pass them accurately into `UserDetails`.
- Group memberships have foreign keys, unique constraints, and proper status/expiry filters.
- Authority codes are validated against role/permission conventions, containing no blanks or untrusted client input.
- Queries never perform **cross-tenant joins**; tenant ID must appear in required keys/predicates.
- Many-to-many role/group relationships are loaded with set-based queries or bounded batching.
- Results are deduplicated before building authorities; do not rely on DB row order for granting permissions.
- Permission changes have explicit session/cache/token eviction or revalidation strategies.
- Test users with no groups, multiple groups, overlapping roles, disabled users, non-existent users, and revoked roles.

In systems with sensitive permissions, explicitly document the **authoritative source of truth**: DB account authorities, IAM/LDAP, OIDC issuer, or centralized governance. When sources conflict, precedence and auditing must be defined; blindly taking the union of all sources can accidentally over-privilege users.

## 12. Common Mistakes to Avoid

1. **Loading each group with a separate SELECT inside a loop:** N+1. Switch to JOIN/UNION/projection/batching.
2. **Assuming `FetchType.EAGER` fixes everything:** can cause overfetching, Cartesian explosion, or multi-bag fetch exceptions.
3. **Only observing SQL for a user in one group:** N+1 only becomes obvious at higher counts. Test with dozens of groups.
4. **Counting queries without measuring rows/latency:** one huge query can be slower than a few small well-indexed queries.
5. **Passing a group name into `hasRole(...)` as if it were a role code:** explicitly map group → authority.
6. **Failing to deduplicate direct and group authorities:** creates messy data; use `UNION`/`distinct`/`Set` by design.
7. **Reading authorities from a lazy entity after the transaction ends:** causes `LazyInitializationException`; materialize a snapshot before returning `UserDetails`.
8. **Checking passwords inside `UserDetailsService`:** mixes responsibilities with `DaoAuthenticationProvider`/`PasswordEncoder`.
9. **Returning a raw JPA entity as the principal:** risks lazy loading, leaking internal fields during serialization, and holding large object graphs in session.
10. **Caching `UserDetails` and letting credential erasure mutate the cached instance:** future logins lose the hash; manage object lifecycles and caching carefully.
11. **Assuming a DB role change immediately updates every session/JWT:** many mechanisms hold snapshots; TTL/revocation/revalidation is needed.
12. **Caching by username in a multi-tenant system:** the same username may exist across tenants; unnamespaced cache keys mix authorities.
13. **Adding authorities from client-declared groups:** memberships must come from trusted, verified sources.
14. **Using global roles instead of per-resource owner/tenant checks:** can expose out-of-scope data.
15. **Missing indexes on membership and join tables:** even set-based queries become slow at scale.
16. **Failing to test denial/revocation:** happy-path-only tests miss over-broad permission grants.

## 13. Reinforcement Exercises

**Exercise A — Spotting N+1.** A user belongs to 40 groups, each with three authorities. Calculate the expected SELECT count for looping per group vs. aggregating authorities with UNION. Explain why the returned row count can still be large even when the SQL query count stays flat.

**Exercise B — Deduplication.** Assign `ROLE_EDITOR` directly to `mai` in the demo while keeping `ROLE_EDITOR` via the group. Verify `GET /me` returns only **one** `ROLE_EDITOR`.

**Exercise C — Revoking an authority.** Delete `ROLE_EDITOR` from `group_authority` while a user is already logged in. Predict the behavior for stateless HTTP Basic, session-based form login, and an app with a `UserDetails` cache. Explain what cache invalidation is needed.

**Exercise D — Optimizing with JPA.** Write two ways to load authorities via Spring Data JPA: a projection query and a bounded `@EntityGraph`. Enable SQL counting, create 50 groups, and compare query count, row count, and latency rather than just line count.

**Exercise E — Tenants.** Add `tenant_id` to accounts and groups, and write predicates ensuring no cross-tenant group memberships exist. Test two tenants sharing the same username, then design matching cache keys and lookup policies.

**Exercise F — Nested groups.** Propose a closure design when group A contains B, B contains C, and C contains A. Explain why cycle detection and depth limits are required, and how to avoid traversal triggering N+1.

**Exercise G — Object-level authorization.** A user has `documents:write`, but the document belongs to a different tenant. Design service/authorization policy checks so editing that document is still denied.

### When Is This Lesson Mastered?

You can explain: how direct and group authorities combine, why roles and groups are not identical, where N+1 occurs, how to write set-based queries so SELECT counts do not grow with N, how to measure real SQL, how to return `GrantedAuthority` in `UserDetails`, and why sessions/caches/tokens can retain revoked authorities. You can run the demo and prove a user receives group authorities without querying groups one by one.

## 14. Official Documentation for Reference

- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): user loading source for provider verification.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): how the provider uses `UserDetails` and `PasswordEncoder`.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `GrantedAuthority`, and `ProviderManager`.
- [Spring Security — Caching UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/caching.html): `CachingUserDetailsService`, `@Cacheable`, and credential erasure concerns.
- [Spring Security — UserDetails and CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): storing/erasing sensitive fields on the principal.
- [Spring Data JPA — Query Methods / EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): how to declare `@EntityGraph` and query methods.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `GrantedAuthority`, roles, and authorization mechanisms.

Runnable snippets focus on Spring Boot 3.5/Spring Security 6.5 and Java 17. When an application uses Spring Security 7, a different JPA provider, or a DB other than H2, verify the APIs, generated SQL, and execution plans for your exact versions.