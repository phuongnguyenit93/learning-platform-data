# Scoping Queries by Identity and Controlling Returned Data in Spring Security Servlet

## 1. Concept and Objectives

A successfully logged-in user **does not automatically have permission to read every record** of a REST API. If Alice and Bob both have ROLE_USER but are only allowed to view documents they own, Alice attempting Bob's document URL must be blocked. A flaw allowing access by changing an ID is called **Broken Object Level Authorization (BOLA)**, also commonly called **IDOR** (Insecure Direct Object Reference).

A system can also leak data even after filtering the right record: an entity might contain **private_note**, PII, or internal admin flags. Hiding that field on the frontend **does not hide the JSON over the wire**. Resource authorization therefore has two sides:

- **Scoping queries by identity**: the database returns only rows within the scope that the current Authentication has permission to read.
- **Controlling returned data**: the controller returns only fields permitted for disclosure via an explicit DTO/projection.

This lesson belongs to **Spring Security Servlet — Resource Authorization**. You will learn row-level authorization, tenant membership, query scoping, count/search/pagination, DTOs, HTTP 401/403/404, cache/export pitfalls, and a runnable application with **Java 17+, Spring Boot 3.3.13, Spring Security 6, JDBC/H2, and MockMvc**.

## 2. Four Security Layers That Must Be Separated

| Layer | Question | Examples |
| --- | --- | --- |
| Authentication | Who does the request belong to? | SecurityContext, UserDetailsService, HTTP Basic |
| URL authorization | Can the user call this endpoint category? | authorizeHttpRequests, authenticated() |
| Object authorization | Can the user view this document ID? | WHERE tenant, owner, membership |
| Field authorization | Which columns can the user receive? | SELECT projection, DocumentView DTO |

Example with URL protection only:

~~~java
// Fragment inside SecurityFilterChain only:
.requestMatchers(HttpMethod.GET, "/api/tenants/**")
.authenticated()
~~~

does not prove Alice can view Bob's document. Spring Security protects requests at the filter layer, while the repository/service must enforce **object-level authorization** and the response layer must enforce **field-level authorization**. Using only hasRole("USER") is insufficient if two users with the same role own different data.

### Identity Must Come from the Server Side

Use **Authentication.getName()** or a framework-verified principal. Never take the owner from request param owner=bob, JSON username=alice, or a client-editable X-User header. When using JWTs, verify the token's issuer, audience, signature, and expiry before using the subject; still verify row permissions against a trusted source. Production should use an immutable userId instead of username/email if users are allowed to change their names.

## 3. Example Model: Tenant and Owner

Users:

| User | Active Membership | Role |
| --- | --- | --- |
| alice | tenant-a, tenant-b | USER |
| bob | tenant-a | USER |
| carol | tenant-b | USER |

Document rows:

| ID | Tenant | Owner | Title |
| --- | --- | --- | --- |
| 101 | tenant-a | alice | Alpha report |
| 102 | tenant-a | alice | Weekly plan |
| 103 | tenant-a | bob | Payroll |
| 104 | tenant-b | carol | Legal review |
| 105 | tenant-b | alice | Migration plan |

The demo policy is **owner-only and active tenant membership**. A document is visible only if:

~~~text
document.tenantId == requestedTenantId
AND document.ownerUsername == authenticatedUsername
AND exists active membership(authenticatedUsername, document.tenantId)
~~~

Hence Alice in tenant-a sees 101/102, Bob in tenant-a sees 103, and Alice in tenant-b sees 105. Bob is not a member of tenant-b, so he receives no documents from that tenant. If Alice guesses Bob's ID 103, she must receive **404**, without receiving any field of that document.

**TenantId in the path is only a client-requested identifier**, not proof that access was granted. A user can change /tenant-a to /tenant-b in the URL; the server must verify membership and ownership independently.

## 4. Queries Must Be Scoped Before Returning to Java

Anti-pattern:

~~~java
// Anti-pattern fragment, not a standalone file:
// var rows = repository.findAll();
// return rows.stream()
//     .filter(d -> d.owner().equals(authentication.getName()))
//     .toList();
~~~

This approach still loads unauthorized data into memory, risks leaking via logs/caches, wastes resources, and can break COUNT and LIMIT/OFFSET.

**Query with authorization inside SQL:**

~~~sql
SELECT d.id, d.title, d.preview
FROM documents d
WHERE d.tenant_id = ?
  AND d.owner_username = ?
  AND EXISTS (
      SELECT 1 FROM tenant_memberships m
      WHERE m.username = ?
        AND m.tenant_id = d.tenant_id
        AND m.active = TRUE
  )
ORDER BY d.id ASC;
~~~

Both username placeholders must bind from Authentication.getName(), never from query/body. The tenant clause checks URL scope, owner checks row scope, and EXISTS ensures membership has not been revoked. SELECT only id, title, and preview instead of SELECT * containing private_note.

### Same Visibility Across Every Read Path

A system might protect GET /documents yet forget GET /documents/{id}, /count, /search, or /export. All must use the exact same predicate. In the demo, a **VISIBLE_FROM** constant is shared across list, detail, and count:

- **List**: visibility + title filter + ORDER BY + LIMIT/OFFSET.
- **Detail**: visibility + AND d.id = ?.
- **Count**: SELECT COUNT(*) with the same visibility and keyword filter.
- **Search**: keywords must never alter the tenant/owner filter.

**COUNT(*) can also leak information**. If Alice has two documents but a table-wide count API returns five, it reveals cardinality outside Alice's scope. Aggregations like SUM/AVG/GROUP BY and similar metadata must also be scoped.

### Pagination, Sorting, and LIKE

Place LIMIT/OFFSET after the WHERE scope. Cap page size to avoid overload and ORDER BY a stable key. If dynamic sorting is supported, map sort names from a server allowlist rather than concatenating raw client input into ORDER BY. For large datasets consider cursor/keyset pagination; cursors must bind scope and resist tampering if carrying sensitive data.

JdbcTemplate parameter binding prevents SQL injection. However, in LIKE, `%` and `_` remain wildcards. If an API intends to match **literal strings**, escape them; the demo uses **ESCAPE '!'**, replacing `!` with `!!`, `%` with `!%`, and `_` with `!_` before binding. Even if a user enters wildcards, the tenant/owner predicates must stay intact.

## 5. Returned Fields Must Follow an Allowlist

The documents table has id, tenant_id, owner_username, title, preview, and private_note. The demo's user-facing API allows only three fields:

~~~java
public record DocumentView(long id, String title, String preview) {}
~~~

Correct response:

~~~json
{"id":101,"title":"Alpha report","preview":"Alice safe summary"}
~~~

No private_note is included. A query param includeSecret=true cannot grant field-level permission on its own. When a support role is allowed to view special data, it needs separate authorization, a different DTO, and auditing. Strip fields **before serialization** rather than sending PII and masking it with CSS/JavaScript later.

New getters or relationships on a JPA entity can unexpectedly expand JSON output. An allowlisted DTO/projection preserves the output contract. Fields such as file URL, createdBy, timestamps, and attachment counts can also be sensitive.

## 6. Complete Maven Example

Structure:

~~~text
scoped-documents-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/scopeddocs/
    │   │   ├── ScopedDocumentsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DocumentView.java
    │   │   ├── DocumentRepository.java
    │   │   └── DocumentController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/com/example/scopeddocs/
        └── DocumentVisibilityTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>scoped-documents-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

### 6.2. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:scopeddocs;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.h2.console.enabled=false
~~~

In-memory H2 is populated from SQL scripts on application startup, not a production database.

### 6.3. schema.sql

~~~sql
CREATE TABLE tenant_memberships (
    username VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (username, tenant_id)
);
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    owner_username VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    preview VARCHAR(500) NOT NULL,
    private_note VARCHAR(1000) NOT NULL
);
CREATE INDEX idx_docs_scope
    ON documents (tenant_id, owner_username, id);
~~~

### 6.4. data.sql

~~~sql
INSERT INTO tenant_memberships VALUES ('alice','tenant-a',TRUE);
INSERT INTO tenant_memberships VALUES ('alice','tenant-b',TRUE);
INSERT INTO tenant_memberships VALUES ('bob','tenant-a',TRUE);
INSERT INTO tenant_memberships VALUES ('carol','tenant-b',TRUE);

INSERT INTO documents VALUES
(101,'tenant-a','alice','Alpha report',
 'Alice safe summary','INTERNAL_ALICE_SECRET');
INSERT INTO documents VALUES
(102,'tenant-a','alice','Weekly plan',
 'Alice safe plan','INTERNAL_ALICE_PLAN');
INSERT INTO documents VALUES
(103,'tenant-a','bob','Payroll',
 'Bob safe summary','INTERNAL_BOB_SECRET');
INSERT INTO documents VALUES
(104,'tenant-b','carol','Legal review',
 'Carol safe summary','INTERNAL_CAROL_SECRET');
INSERT INTO documents VALUES
(105,'tenant-b','alice','Migration plan',
 'Alice second tenant','INTERNAL_ALICE_B_SECRET');
~~~

Private notes are just dummy strings to prove the field is not exposed by the API.

### 6.5. ScopedDocumentsApplication.java

~~~java
package com.example.scopeddocs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopedDocumentsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedDocumentsApplication.class, args);
    }
}
~~~

### 6.6. SecurityConfig.java

~~~java
package com.example.scopeddocs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER").build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER").build();
        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("carol-pass"))
            .roles("USER").build();
        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/tenants/*/documents",
                    "/api/tenants/*/documents/*")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
~~~

HTTP Basic is used for the demo; passwords are hashed with BCrypt. Any real client sending HTTP Basic credentials requires HTTPS. CSRF is not disabled; the demo has only GET endpoints, while unsafe methods must enforce a CSRF policy if clients have browser cookies/credentials sent automatically.

### 6.7. DocumentView.java

~~~java
package com.example.scopeddocs;

public record DocumentView(
    long id,
    String title,
    String preview
) {}
~~~

### 6.8. DocumentRepository.java

~~~java
package com.example.scopeddocs;

import java.util.List;
import java.util.Locale;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private static final String VISIBLE_FROM = """
        FROM documents d
        WHERE d.tenant_id = ?
          AND d.owner_username = ?
          AND EXISTS (
              SELECT 1 FROM tenant_memberships m
              WHERE m.tenant_id = d.tenant_id
                AND m.username = ?
                AND m.active = TRUE
          )
        """;

    private static final String TITLE_FILTER = """
        AND (? = '' OR LOWER(d.title) LIKE ? ESCAPE '!')
        """;

    private static final RowMapper<DocumentView> VIEW_MAPPER =
        (rs, index) -> new DocumentView(
            rs.getLong("id"),
            rs.getString("title"),
            rs.getString("preview"));

    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String normalize(String q) {
        return q.trim().toLowerCase(Locale.ROOT);
    }

    private static String escapedLike(String q) {
        return "%" + q.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_") + "%";
    }

    public List<DocumentView> listVisible(
            String tenantId, String username,
            String q, int limit, int offset) {
        String keyword = normalize(q);
        String sql = "SELECT d.id, d.title, d.preview "
            + VISIBLE_FROM + TITLE_FILTER
            + " ORDER BY d.id ASC LIMIT ? OFFSET ?";

        return jdbc.query(sql, VIEW_MAPPER,
            tenantId, username, username,
            keyword, escapedLike(keyword), limit, offset);
    }

    public Optional<DocumentView> findVisible(
            String tenantId, String username, long id) {
        String sql = "SELECT d.id, d.title, d.preview "
            + VISIBLE_FROM + " AND d.id = ?";
        return jdbc.query(sql, VIEW_MAPPER,
            tenantId, username, username, id)
            .stream().findFirst();
    }

    public long countVisible(
            String tenantId, String username, String q) {
        String keyword = normalize(q);
        String sql = "SELECT COUNT(*) " + VISIBLE_FROM + TITLE_FILTER;
        Long count = jdbc.queryForObject(sql, Long.class,
            tenantId, username, username,
            keyword, escapedLike(keyword));
        return count == null ? 0L : count;
    }
}
~~~

VISIBLE_FROM is reused for list, detail, and count. In every query, tenantId is the client-specified selector, username is the server-side principal, and membership must be active. The SQL never reads private_note. Search and pagination conditions only supplement—**never replace—the visibility predicate**.

### 6.9. DocumentController.java

~~~java
package com.example.scopeddocs;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {

    private final DocumentRepository repo;

    public DocumentController(DocumentRepository repo) {
        this.repo = repo;
    }

    private static void validateKeyword(String q) {
        if (q.length() > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Keyword too long");
        }
    }

    @GetMapping
    public List<DocumentView> list(
            @PathVariable String tenantId,
            @RequestParam(defaultValue = "") String q,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(defaultValue = "0") int offset,
            Authentication auth) {

        validateKeyword(q);
        if (limit < 1 || limit > 100 || offset < 0 || offset > 10000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid pagination");
        }
        return repo.listVisible(
            tenantId, auth.getName(), q, limit, offset);
    }

    @GetMapping("/count")
    public Map<String, Long> count(
            @PathVariable String tenantId,
            @RequestParam(defaultValue = "") String q,
            Authentication auth) {
        validateKeyword(q);
        return Map.of("count",
            repo.countVisible(tenantId, auth.getName(), q));
    }

    @GetMapping("/{id}")
    public DocumentView detail(
            @PathVariable String tenantId,
            @PathVariable long id,
            Authentication auth) {

        return repo.findVisible(tenantId, auth.getName(), id)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Never use a client-supplied ownerId. Detail returns 404 for both non-existent and unauthorized records. Out-of-scope collections return 200 [] per the demo's contract; other applications may return 404 after a membership check if policy requires. Requests with invalid limit/offset receive 400.

## 7. Running with Maven and curl

~~~bash
mvn spring-boot:run
~~~

By default the application listens on port 8080 if available. Without credentials:

~~~bash
curl -i http://localhost:8080/api/tenants/tenant-a/documents
~~~

Expected 401 Unauthorized. Alice views tenant-a:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents"
~~~

Expected 200:

~~~json
[
  {"id":101,"title":"Alpha report","preview":"Alice safe summary"},
  {"id":102,"title":"Weekly plan","preview":"Alice safe plan"}
]
~~~

Bob in tenant-a receives only ID 103, Alice in tenant-b receives only ID 105, and Bob in tenant-b receives an empty list. Alice guessing Bob's ID 103:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents/103"
~~~

Expected **404 Not Found**. Alice's count in tenant-a:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents/count"
~~~

Expected JSON {"count":2}. Search:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents?q=Alpha"
~~~

Expected only ID 101. With limit=1&offset=1, Alice sees only ID 102. Wrong password returns 401; limit=1000 returns 400. Curl -u is only for dummy credentials in this localhost example; avoid storing real secrets in shell history.

## 8. MockMvc Integration Test

Create **src/test/java/com/example/scopeddocs/DocumentVisibilityTest.java**:

~~~java
package com.example.scopeddocs;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentVisibilityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noCredentialsReturns401() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceOnlySeesOwnTenantADocuments() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].id").value(101))
            .andExpect(jsonPath("$[1].id").value(102))
            .andExpect(jsonPath("$[0].privateNote").doesNotExist())
            .andExpect(content().string(
                not(containsString("INTERNAL_ALICE_SECRET"))));
    }

    @Test
    void bobOnlySeesHisOwnSameTenantDocument() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(103));
    }

    @Test
    void guessingAnothersDocumentIsBlocked() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents/103")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/tenants/tenant-a/documents/101")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isNotFound());
    }

    @Test
    void ownDocumentStillHidesInternalField() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents/101")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.privateNote").doesNotExist())
            .andExpect(content().string(
                not(containsString("INTERNAL_ALICE_SECRET"))));
    }

    @Test
    void membershipControlsTenantVisibility() throws Exception {
        mvc.perform(get("/api/tenants/tenant-b/documents")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(105));

        mvc.perform(get("/api/tenants/tenant-b/documents")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void countSearchAndPaginationStayScoped() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents/count")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(2));

        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("q", "Alpha")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(101));

        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("limit", "1")
                .param("offset", "1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(jsonPath("$[0].id").value(102));
    }

    @Test
    void likeWildcardIsLiteralAndPageSizeIsBounded()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("q", "%")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));

        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("limit", "1000")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The negative tests **Alice cannot view Bob's document**, **Bob cannot view Alice's document**, **Bob has no tenant-b membership**, and **private_note is not exposed** matter more than just testing that Alice can read ID 101. MockMvc passes through the Spring Security filter chain; it does not automatically prove every external database/search/cache outside the project behaves identically.

## 9. Production Considerations

**Spring Data JPA:** You can use derived queries by owner/tenant or Specification/JPQL with membership, but never return an unscoped findById. Do not serialize JPA entities directly because getters/relations can expose fields.

**PostgreSQL Row-Level Security:** Can strengthen defense in depth, but you must reliably bind identity/tenant to the DB session, manage connection pool context resets, transactions, bypass roles, and background jobs. RLS does not protect output fields by itself.

**CREATE/UPDATE/DELETE:** The server should assign the owner from the principal; UPDATE/DELETE need WHERE owner/tenant/ACL and must check affectedRows, not just WHERE id = ?. Checking permission once and then performing an unscoped update introduces TOCTOU risk.

**Cache/CDN:** URL-based caches without user/tenant keys can serve Alice's response to Bob even when SQL is correct. For private data, use Cache-Control: no-store or auth-aware cache keys with proper invalidation. Search indexes, CSV/Excel/PDF exports, analytics, download links, and async jobs must enforce equivalent authorization.

**Permissions changing at runtime:** Revoking membership may not immediately cancel an in-flight request that already passed checks, and sessions/JWTs/caches may retain old permissions. Define transaction/isolation semantics and re-check policies at operation boundaries. Multi-node deployments need a shared authorization source and fail-closed behavior when sensitive authorization data is unreachable.

**404 vs. 403:** Out-of-scope details may return 404 to reduce existence disclosure. 404 alone does not eliminate side channels like timing or count. 401 reflects missing HTTP Basic authentication, while 403 can result from lacking permission or missing CSRF.

## 10. Exercises with Answers

1. Alice and Bob both have ROLE_USER in tenant-a. Can Alice read document 103? **No**, because of the owner-only policy.
2. Returning an entity containing private_note and hiding the field on the frontend—is that safe? **No**, the JSON still exposes the field.
3. Alice's list returns 2 items, while the table-wide count returns 5—is that a leak? **Yes**, count must share the same query scope.
4. Applying LIMIT 20 first and then filtering in Java—is that right? **No**, the authorization WHERE clause must apply before pagination.
5. Can an unguessable UUID replace object authorization checks? **No**, IDs can still be leaked.
6. Client sends owner=bob—is that a trusted principal? **No**, obtain identity from Authentication.
7. Does PreparedStatement make `%` inside LIKE literal? **No**, it must be escaped according to the search contract.
8. Can Bob receive Alice's response from a CDN cache even if SQL is correct? **Yes**, properly scoped cache keys or no-store are required.
9. Does UPDATE with only WHERE id=? protect the owner? **No**, add the permission predicate and transaction handling.
10. If an admin revokes membership after a request starts, does that automatically cancel the request? **No**, a consistency policy at sensitive operations is required.

## 11. Implementation Checklist

- [ ] Obtain the verified principal; never trust username/owner from the client.
- [ ] Verify TenantId membership; place owner/tenant/ACL scope in every query.
- [ ] Use a consistent visibility policy across list, detail, count, search, aggregations, and exports.
- [ ] Never query the whole table and filter in Java or return raw entities.
- [ ] DTOs contain only disclosed fields; test that private_note/PII never leak.
- [ ] Apply pagination after WHERE, bound limits, allowlist sort fields, and bind SQL parameters.
- [ ] Include negative tests for cross-user, cross-tenant, IDOR, and field leaks.
- [ ] Write operations verify server-side permissions, affected rows, transactions, and CSRF appropriately.
- [ ] Caches/CDNs/search indexes/async exports never exceed the requester's scope.
- [ ] Define revocation, permission freshness, and fail-closed policies matching risk levels.
- [ ] Use H2/sample passwords only in learning environments, and HTTPS for real credentials.

**Conclusion:** Spring Security Servlet authenticates users and controls endpoint access, but resource authorization must be enforced in **record queries** and **returned data projections**. The decisive questions are: **Who is calling, which rows may they see, which fields may they receive, and are there any read paths not yet enforcing the same policy?**
