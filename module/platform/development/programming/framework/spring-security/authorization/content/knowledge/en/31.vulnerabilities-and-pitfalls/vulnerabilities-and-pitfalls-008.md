# Shared GraphQL Endpoint: Protecting Resolvers, Objects, and Fields

## 1. Why Is This an Easily Overlooked Authorization Vulnerability?

In REST, applications typically have distinct URLs for each resource and action. GraphQL typically receives many kinds of queries and mutations through **a single endpoint** such as `POST /graphql`. Protecting that URL with `requestMatchers("/graphql").authenticated()` only confirms the caller is logged in; it **does not prove** they have permission to invoke each operation, view each object, or read each requested field.

For example, the following two requests hit the exact same endpoint yet require different permissions:

```graphql
query {
  document(id: "101") {
    id
    title
  }
}
```

```graphql
mutation {
  archiveDocument(id: "101") {
    status
  }
}
```

A query can also reach deep sensitive fields inside:

```graphql
query {
  document(id: "101") {
    id
    title
    internalNotes
  }
}
```

If the system only checks “logged in” at `/graphql` and returns the full object inside the resolver, users can bypass authorization by requesting someone else's ID or adding sensitive fields to the selection set. These are **Broken Object Level Authorization (BOLA/IDOR)** and **Broken Object Property Level Authorization (BOPLA)** in the GraphQL context.

This lesson focuses on three mandatory questions:

1. **Resolver/operation:** is the user allowed to execute the action?
2. **Object:** is the user allowed to read/modify the **specific record** selected by ID, relationship, or list?
3. **Field:** within a valid object, is the user allowed to see the **specific field** (e.g., `internalNotes`, internal pricing, PII, tokens, approval status)?

The three questions can have three different answers. Having `DOC_READ` does not mean having `DOC_ARCHIVE`; being allowed to read document 101 does not mean being allowed to read document 102; being allowed to read title 101 does not mean being allowed to read its internal notes.

## 2. Running Scenario and Sample Policy

Suppose the `documents` table has two records:

| id | owner_username | title | internal_notes | archived |
| --- | --- | --- | --- | --- |
| 101 | alice | Hợp đồng A | `Alice secret` | false |
| 102 | bob | Hợp đồng B | `Bob secret` | false |

Application authorities:

- `DOC_READ`: allowed to use the read-document function; **only reads owned objects** (this example's policy).
- `DOC_NOTE_READ`: additionally allows reading `internalNotes` **of an object already permitted to view**.
- `DOC_ARCHIVE`: allowed to use the archive operation; must still verify ownership at write time.

For actor `alice`, expected results:

| Operation | Alice's Permissions | Result |
| --- | --- | --- |
| Read title 101 | `DOC_READ` | Succeeds |
| Read title 102 | `DOC_READ` | Returns no record data |
| Read `internalNotes` of 101 | Only `DOC_READ` | Does not return notes; field authorization error |
| Read `internalNotes` of 101 | `DOC_READ` + `DOC_NOTE_READ` | Returns `Alice secret` |
| Archive 101 | `DOC_ARCHIVE` | Updates 101 |
| Archive 102 | `DOC_ARCHIVE` | Does not update 102 |

This is an illustrative owner-based policy. Real applications may use tenants, ACLs, per-project roles, membership relations, or workflow states. In those cases replace the owner check with the **domain's real authorization evaluator**, never a global role substitute.

**Security invariant:** a field may be disclosed only if the actor is authorized to access both the object and the field; a mutation may write only when the actor has action permission **and** object permission at write time.

## 3. What Does GraphQL Execute in One Request?

A GraphQL document can contain multiple root fields, aliases, fragments, and nested branches. Every selected field can trigger a data fetcher/resolver.

```graphql
query MixedAccess {
  own: document(id: "101") {
    id
    title
    internalNotes
  }
  foreign: document(id: "102") {
    id
    title
    internalNotes
  }
}
```

`own` and `foreign` are merely **client aliases**, not two different endpoints. A policy inspecting operation name strings or running regex searches for `document` or `internalNotes` in the HTTP body easily breaks on aliases, fragments, variables, multiple operations, nested fields, and schema changes.

Processing flow aligned with Spring MVC + Spring for GraphQL:

```text
POST /graphql
   │
   ├─ Spring Security FilterChain: authentication / CSRF / HTTP policy
   │
   └─ GraphQL parse + validate + execute
       ├─ Query.document(id: 101) ──► DOC_READ + object 101
       │                               └─ Document.internalNotes ──► DOC_NOTE_READ + 101
       └─ Query.document(id: 102) ──► DOC_READ + object 102 (deny)
```

Key point: **one URL, many authorization decisions**. Protecting the root query is necessary but insufficient if the same `Document` type can also be reached via `search`, `project.documents`, `user.documents`, `node(id:)`, DataLoaders, or subscriptions. Policies located in the **service/domain layer** must be reused across every path.

## 4. Four Complementary Control Layers

| Layer | What Does It Protect? | Example | If Missed |
| --- | --- | --- | --- |
| HTTP/transport | Only valid identities enter the GraphQL endpoint (plus CSRF/token policies) | `/graphql` requires authentication | Strangers can enter the API |
| Resolver/service operation | Permission to invoke a function | `@PreAuthorize("hasAuthority('DOC_ARCHIVE')")` | Read-only users can also mutate |
| Object/domain | Permission on each ID, tenant, relationship | `WHERE id = ? AND owner_username = ?` | BOLA: read/write others' records |
| Field/property | Permission on sensitive data of an allowed object | `DOC_NOTE_READ` + owner for `internalNotes` | BOPLA: leaks data inside valid objects |

One layer does not replace another. For instance, `@PreAuthorize("hasAuthority('DOC_READ')")` on `Query.document` only confirms function permission. **ID 102 must still be blocked** by the object-access predicate; the `internalNotes` field may require a narrower authority.

Never let clients supply `ownerUsername` or `tenantId` and trust it as the authorized identity. The actor must come from server-verified authentication. At the service layer, constrain any passed actor parameter against `authentication.name` so internal calls cannot impersonate arbitrary strings.

## 5. GraphQL Schema and Response Contract

File `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
  document(id: ID!): Document
}

type Mutation {
  archiveDocument(id: ID!): ArchiveResult!
}

type Document {
  id: ID!
  title: String!
  internalNotes: String
}

type ArchiveResult {
  status: ArchiveStatus!
}

enum ArchiveStatus {
  ARCHIVED
  NOT_PROCESSED
}
```

Design intent:

- `document` is **nullable**: when the ID does not exist or the caller is not allowed to view it, the example returns `null` identically, avoiding creating an existence-oracle channel.
- `internalNotes` is **nullable**: when unauthorized, the field can become `null` alongside a sanitized GraphQL error. If marked `String!`, the error or `null` propagates upward (*null bubbling*) and can turn the entire object or parent data into `null`.
- `archiveDocument` returns `NOT_PROCESSED` for non-existent IDs, IDs not owned by the actor, or records needing no state change. That is one specific contract to limit distinguishing failure reasons; another system might choose a `FORBIDDEN` error after evaluating disclosure risks.
- Do not expose raw `owner_username` or `internal_notes` in the schema. **The GraphQL schema does not enforce permissions by itself**; it defines which fields may be queried, while resolvers/services decide which values are returned.

Example response for `alice`'s mixed query with both `DOC_READ` and `DOC_NOTE_READ`:

```json
{
  "data": {
    "own": {
      "id": "101",
      "title": "Hợp đồng A",
      "internalNotes": "Alice secret"
    },
    "foreign": null
  }
}
```

If `alice` has only `DOC_READ` and queries `internalNotes` on document 101, the response below is **illustrative**, not a fixed default error string of Spring GraphQL:

```json
{
  "data": {
    "document": {
      "id": "101",
      "title": "Hợp đồng A",
      "internalNotes": null
    }
  },
  "errors": [
    {
      "message": "Access denied",
      "path": ["document", "internalNotes"]
    }
  ]
}
```

Error types, messages, and `extensions` must be controlled per security contract; never leak stack traces, SQL queries, owner/tenant names, or sensitive notes in errors.

## 6. Spring Boot and Spring Security: Sample Implementation

The example uses **Java 17+, Spring Boot 3.x, Spring MVC, Spring for GraphQL, Spring Security 6, Spring JDBC**. These are files inside **a Spring Boot application** with a configured DataSource and database, not a standalone program run via `javac`. Key dependencies: `spring-boot-starter-graphql`, `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-jdbc`, and a JDBC driver. Tests use `spring-boot-starter-test` + `spring-security-test`.

### 6.1. Authenticate at the URL and Enable Method Security

File `GraphQlSecurityConfig.java`:

```java
package com.example.demo.graphql;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class GraphQlSecurityConfig {

    @Bean
    SecurityFilterChain graphqlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/graphql").authenticated()
                .anyRequest().denyAll());
        return http.build();
    }
}
```

`@EnableMethodSecurity` is mandatory for `@PreAuthorize` to operate in the example. `authenticated()` at `/graphql` blocks unauthenticated callers at transport; underlying services decide operation, object, and field permissions.

The example intentionally keeps **Spring Security's default CSRF**. For session/cookie applications, POST requests require a CSRF token; MockMvc tests send `csrf()`. For stateless bearer-token APIs, CSRF policy may differ and must be configured deliberately. The code above assumes an authentication mechanism providing real authorities is already present (it does not create users/accounts itself).

### 6.2. DTOs Containing Only Basic Fields and Schema Results

File `DocumentView.java`:

```java
package com.example.demo.graphql;

public record DocumentView(String id, String title) {
    public String getId() { return id; }
    public String getTitle() { return title; }
}
```

File `ArchiveResult.java`:

```java
package com.example.demo.graphql;

enum ArchiveStatus {
    ARCHIVED, NOT_PROCESSED
}

public record ArchiveResult(ArchiveStatus status) {
    public ArchiveStatus getStatus() { return status; }
}
```

The DTO omits `internalNotes`. Only the `@SchemaMapping` for that field loads and returns the data after passing service permission checks. The JavaBean-style getters above help GraphQL Java resolve `id`, `title`, and `status` unambiguously.

**Limitation note:** a DTO is safe on `document(id)` only when the parent resolver returned an authorized object. If paths like `project.documents` or `search` are added later, they must use the same service/predicate to filter objects before returning; never assume a DTO enforces authorization itself.

### 6.3. Repository Placing Permission Predicates Directly in Queries

File `DocumentRepository.java`:

```java
package com.example.demo.graphql;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {
    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public DocumentView findVisible(long id, String actor) {
        List<DocumentView> rows = jdbc.query("""
                SELECT id, title
                  FROM documents
                 WHERE id = ?
                   AND owner_username = ?
                """,
                (rs, rowNum) -> new DocumentView(
                        Long.toString(rs.getLong("id")),
                        rs.getString("title")),
                id, actor);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public String findNotesIfOwned(long id, String actor) {
        List<String> rows = jdbc.query("""
                SELECT internal_notes
                  FROM documents
                 WHERE id = ?
                   AND owner_username = ?
                """,
                (rs, rowNum) -> rs.getString("internal_notes"),
                id, actor);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public int archiveIfOwned(long id, String actor) {
        return jdbc.update("""
                UPDATE documents
                   SET archived = TRUE
                 WHERE id = ?
                   AND owner_username = ?
                   AND archived = FALSE
                """, id, actor);
    }
}
```

The `?` placeholders are `JdbcTemplate` bind parameters; ID and actor values are never concatenated into SQL. More importantly, **reads, sensitive field reads, and writes** are all constrained by `owner_username`. A result of `0` updated rows means no record satisfied the conditions; one cannot tell whether it “does not exist” or “lacks permission”.

In multi-tenant systems, add `tenant_id = ?` based on the verified tenant; with complex ACLs, replace the predicate with real permission rules and consider conditional writes/locking to avoid gaps between check and update (*TOCTOU*).

### 6.4. Service as the Reusable Permission Boundary for All Entry Points

File `DocumentAccessService.java`:

```java
package com.example.demo.graphql;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentAccessService {
    private final DocumentRepository repository;

    public DocumentAccessService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('DOC_READ') and #actor == authentication.name")
    public DocumentView visible(long id, @P("actor") String actor) {
        return repository.findVisible(id, actor);
    }

    @PreAuthorize("""
            hasAuthority('DOC_READ') and
            hasAuthority('DOC_NOTE_READ') and
            #actor == authentication.name
            """)
    public String internalNotes(long id, @P("actor") String actor) {
        return repository.findNotesIfOwned(id, actor);
    }

    @Transactional
    @PreAuthorize("hasAuthority('DOC_ARCHIVE') and #actor == authentication.name")
    public ArchiveResult archive(long id, @P("actor") String actor) {
        int affected = repository.archiveIfOwned(id, actor);
        return new ArchiveResult(
                affected == 1
                        ? ArchiveStatus.ARCHIVED
                        : ArchiveStatus.NOT_PROCESSED);
    }
}
```

`@P("actor")` guarantees Spring Security finds the parameter name in SpEL expressions even if the compiler does not enable `-parameters`. The `#actor == authentication.name` expression rejects a service call attempting to pass another username. The SQL predicate **must still be kept** to protect individual IDs and avoid mistaking `hasAuthority` for permission over all documents.

Services must be Spring-managed beans called through proxies for `@PreAuthorize` to take effect; calling `this.internalNotes(...)` from another method on the same instance can bypass method interception. Design authorization checkpoints in services/domain so batch resolvers, workers, and other services also pass through them.

### 6.5. Resolvers Calling the Service; Sensitive Fields Have Dedicated Resolvers

File `DocumentGraphQlController.java`:

```java
package com.example.demo.graphql;

import java.security.Principal;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class DocumentGraphQlController {
    private final DocumentAccessService access;

    public DocumentGraphQlController(DocumentAccessService access) {
        this.access = access;
    }

    @QueryMapping
    public DocumentView document(
            @Argument String id, Principal principal) {
        return access.visible(positiveId(id), principal.getName());
    }

    @SchemaMapping(typeName = "Document", field = "internalNotes")
    public String internalNotes(
            DocumentView source, Principal principal) {
        return access.internalNotes(
                positiveId(source.id()), principal.getName());
    }

    @MutationMapping
    public ArchiveResult archiveDocument(
            @Argument String id, Principal principal) {
        return access.archive(positiveId(id), principal.getName());
    }

    private static long positiveId(String raw) {
        try {
            long id = Long.parseLong(raw);
            if (id <= 0) {
                throw new NumberFormatException("Non-positive ID");
            }
            return id;
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid document ID", ex);
        }
    }
}
```

`Principal` is a handler parameter supported by Spring for GraphQL when a security context is present. `@QueryMapping` handles `Query` type fields; `@MutationMapping` handles `Mutation`; `@SchemaMapping(typeName="Document", field="internalNotes")` is invoked when the client **selects** that field. Fetching `internalNotes` in a separate resolver clarifies the authorization checkpoint while avoiding loading notes during ordinary queries.

**Do not confuse:** `@SchemaMapping` only binds a handler to a GraphQL field; the annotation itself grants no security. Authorization comes from `DocumentAccessService.internalNotes`. Other sensitive fields require corresponding rules.

## 7. Testing GraphQL HTTP with MockMvc: Permissions and Data

GraphQL runs over HTTP yet **does not equate field errors with HTTP 403**. If a Spring Security filter blocks before GraphQL runs, HTTP may be `401`/`403` or a redirect depending on the authentication entry point. If the request passes filters and a resolver/service is denied, GraphQL normally returns a response containing `errors`, possibly alongside partial `data`, with HTTP `200` per transport convention. Therefore tests must verify **GraphQL response structure, absence of sensitive data, and unchanged database state**.

Integration test example using `MockMvc` passing through `SecurityFilterChain` and the GraphQL endpoint. Assumes test datasource setup created the table:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    owner_username VARCHAR(80) NOT NULL,
    title VARCHAR(200) NOT NULL,
    internal_notes VARCHAR(500),
    archived BOOLEAN NOT NULL
);
```

File `DocumentGraphQlAuthorizationIT.java` (placed in the same package):

```java
package com.example.demo.graphql;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Arrays;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentGraphQlAuthorizationIT {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM documents WHERE id IN (101, 102)");
        jdbc.update("""
                INSERT INTO documents
                (id, owner_username, title, internal_notes, archived)
                VALUES (?, ?, ?, ?, FALSE)
                """, 101L, "alice", "Hợp đồng A", "Alice secret");
        jdbc.update("""
                INSERT INTO documents
                (id, owner_username, title, internal_notes, archived)
                VALUES (?, ?, ?, ?, FALSE)
                """, 102L, "bob", "Hợp đồng B", "Bob secret");
    }

    private RequestPostProcessor alice(String... authorities) {
        GrantedAuthority[] roles = Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toArray(GrantedAuthority[]::new);
        return user("alice").authorities(roles);
    }

    private ResultActions graphQl(
            String document, RequestPostProcessor identity)
            throws Exception {
        return mvc.perform(post("/graphql")
                .with(identity)
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(
                        Map.of("query", document))));
    }

    private boolean archived(long id) {
        return Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT archived FROM documents WHERE id = ?",
                Boolean.class, id));
    }

    @Test
    void aliasCannotBypassObjectAuthorization() throws Exception {
        String query = """
                query {
                  own: document(id: "101") { id title internalNotes }
                  other: document(id: "102") { id title internalNotes }
                }
                """;

        graphQl(query, alice("DOC_READ", "DOC_NOTE_READ"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.own.id").value("101"))
            .andExpect(jsonPath("$.data.own.internalNotes")
                    .value("Alice secret"))
            .andExpect(jsonPath("$.data.other").value(nullValue()))
            .andExpect(jsonPath("$.errors").doesNotExist());
    }

    @Test
    void documentReadDoesNotGrantPrivateField() throws Exception {
        String query = """
                { document(id: "101") { id title internalNotes } }
                """;

        String body = graphQl(query, alice("DOC_READ"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.document.title")
                    .value("Hợp đồng A"))
            .andExpect(jsonPath("$.data.document.internalNotes")
                    .value(nullValue()))
            .andExpect(jsonPath("$.errors").isArray())
            .andReturn().getResponse().getContentAsString();

        assertThat(body).doesNotContain("Alice secret", "Bob secret");
    }

    @Test
    void mutationCannotModifyForeignObject() throws Exception {
        String mutation = """
                mutation {
                  archiveDocument(id: "102") { status }
                }
                """;

        graphQl(mutation, alice("DOC_ARCHIVE"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.archiveDocument.status")
                    .value("NOT_PROCESSED"));

        assertThat(archived(101L)).isFalse();
        assertThat(archived(102L)).isFalse();
    }

    @Test
    void missingMutationAuthorityCausesErrorAndNoWrite()
            throws Exception {
        String mutation = """
                mutation {
                  archiveDocument(id: "101") { status }
                }
                """;

        graphQl(mutation, alice("DOC_READ"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.errors").isArray());

        assertThat(archived(101L)).isFalse();
    }
}
```

Expected outcome when running tests in an application with matching DataSource, schema, and Spring Security config: all four tests pass. This is not proof of execution in every project; differences in error resolvers, transport status, GraphQL starter, and authentication entry point may require updating assertions, yet **never relax the no-leak/no-unauthorized-write invariants**.

Note on the second test: `internalNotes: String` is nullable, so a method security failure may only set the field to `null` and populate `errors`. If the system uses a custom `DataFetcherExceptionResolver` returning `null` silently, tests must verify the real contract; ensuring no secret string appears in the response and no unauthorized field is exposed is what is essential.

### Quick HTTP Test with GraphQL Variables

Illustrative valid request (with trusted credentials and matching CSRF/token policy):

```http
POST /graphql HTTP/1.1
Content-Type: application/json

{
  "query": "query GetDoc($id: ID!) { document(id: $id) { id title internalNotes } }",
  "variables": { "id": "101" },
  "operationName": "GetDoc"
}
```

Using variables separates input from the document and enables query reuse; **never treat variables as a trusted source**. ID, object access, tenant, and field permissions must still be verified server-side.

## 8. Plain Java 17: Verifying Invariants Independently of the GraphQL Framework

The small snippet below simulates the three decisions (function, object, field). It **does not open an HTTP endpoint or execute GraphQL**, helping verify isolated logic before running integration tests.

File `GraphQlAuthorizationDemo.java`:

```java
import java.util.Map;

public class GraphQlAuthorizationDemo {
    record Doc(long id, String owner, String title, String note) {}
    record Actor(String name, boolean read, boolean noteRead) {}

    static Doc resolveDocument(
            Map<Long, Doc> db, Actor actor, long id) {
        if (!actor.read()) {
            throw new SecurityException("No document-read authority");
        }
        Doc found = db.get(id);
        return found != null && found.owner().equals(actor.name())
                ? found : null;
    }

    static String resolveNotes(Actor actor, Doc source) {
        if (source == null || !actor.read() || !actor.noteRead()) {
            return null;
        }
        return source.owner().equals(actor.name())
                ? source.note() : null;
    }

    public static void main(String[] args) {
        Map<Long, Doc> db = Map.of(
                101L, new Doc(101, "alice", "A", "Alice secret"),
                102L, new Doc(102, "bob", "B", "Bob secret"));
        Actor basic = new Actor("alice", true, false);
        Actor privileged = new Actor("alice", true, true);

        System.out.println("own=" +
                resolveDocument(db, basic, 101L).title());
        System.out.println("foreign=" +
                resolveDocument(db, basic, 102L));
        System.out.println("notes-basic=" +
                resolveNotes(basic, resolveDocument(db, basic, 101L)));
        System.out.println("notes-privileged=" +
                resolveNotes(privileged,
                        resolveDocument(db, privileged, 101L)));
    }
}
```

Run with Java 17 or newer:

```bash
javac GraphQlAuthorizationDemo.java
java GraphQlAuthorizationDemo
```

Exact stdout:

```text
own=A
foreign=null
notes-basic=null
notes-privileged=Alice secret
```

Key difference to remember: in the plain Java model, an unauthorized field returns `null` without raising a GraphQL error. In the Spring example, `@PreAuthorize` denies via exception; GraphQL may place an error in `errors`. Both are valid contract choices as long as data is protected.

## 9. GraphQL-Specific Attack Vectors to Test

### 9.1. Nested Access Paths, Aliases, and Fragments

An object does not appear solely through `Query.document(id:)`. For example:

```graphql
query {
  project(id: "P1") {
    members {
      documents {
        id
        title
        internalNotes
      }
    }
  }
}
```

If `project.members.documents` uses another repository and fails to check the actor per document, Bob's data can leak even if `Query.document` is protected. **Every path reaching the same object type must share the domain policy.** In schemas with interfaces/unions, check subtypes, fragments, inline fragments, and field resolvers of every type. Aliases rename response keys without altering permissions.

### 9.2. N+1, @BatchMapping, and DataLoader

`@BatchMapping`/DataLoader reduces query count yet **is not exempt from authorization**. Given batch IDs `[101,102]`, a query loading both and returning the entire map to the client can leak 102. Batch loaders must apply predicates with a trusted actor/tenant, return `null` or omit unauthorized keys per contract, and never let user A's cache be reused for user B.

Only scope DataLoader caches per **request** or include full identity/scope in cache keys; consider invalidation when permissions change. For async loaders, ensure `SecurityContext`/`GraphQLContext` propagates properly across threads/reactive contexts. Never pull `SecurityContextHolder` from an arbitrary thread assuming it always holds the request's actor inside `@Async` or custom executors.

### 9.3. Mutations and Side Effects

`Mutation` operations can create, edit, delete, assign owners, or add members. Check permissions **before the mutation**, and prefer conditional updates, transactions, or optimistic locking to prevent TOCTOU. Tests must re-read the database and check audit/events/queues. A mutation returning a GraphQL error does not guarantee no write statement committed.

Never allow an apparently read-only field (query) to invoke a service creating side effects. Limit request/batch sizes, validate each ID, and never trust a client-sent list of “allowed” objects.

### 9.4. Subscriptions, WebSockets, and Async

For subscriptions, authenticating at connection handshake **is insufficient** when events carry data for multiple objects. Check permissions at subscribe time and guard data within the event stream, especially when permissions can change after subscribing. If using WebSockets, user context handling and terminating streams after permission revocation are architectural decisions that must be tested.

### 9.5. Depth, Complexity, and Introspection

GraphQL allows requesting many aliases, recursive relations, and nested fields; **DoS/high query cost** risks complement authorization concerns. Limit depth, complexity, alias count, page size, timeouts, and rate limits. Introspection helps users understand the schema, yet disabling introspection only reduces discoverability and **does not replace permission checks**. Persisted queries/allowlists help restrict request surface yet do not replace object/field authorization either.

## 10. Minimum Test Matrix for GraphQL Authorization

| Test Case | What to Verify |
| --- | --- |
| Unauthenticated on `/graphql` | HTTP filter blocks per configured entry point; no sensitive data |
| Authenticated but missing `DOC_READ` | Query denied at service; no object leaked |
| Has `DOC_READ`, own ID | Correct object and public fields only |
| Has `DOC_READ`, another user's ID | Returns `null`/chosen error; does not expose title, note, owner |
| Has `DOC_READ` without `DOC_NOTE_READ` | `internalNotes` not exposed, even when title is readable |
| Has both read and note permissions | Returns notes only for objects the actor is allowed to view |
| Has `DOC_ARCHIVE`, mutates another user's ID | No update, no success event |
| Missing `DOC_ARCHIVE` | No update even when ID belongs to actor |
| Alias + fragment + nested relation | Cannot open a bypass path to blocked objects/fields |
| Multiple operations/variables | `operationName` and variables do not alter permission decisions |
| Batch/DataLoader/caching | Never mixes results across users/tenants or allowed/denied IDs |
| System changes permissions mid-request | Does not keep returning/writing beyond published contract |
| Denied field marked `!` in schema | Test null bubbling and final data/errors |
| Error inside transaction / async processing | Data, audit, queue, and rollback follow policy |
| Overly deep query / too many aliases | Query constrained by resource limits per config, no DoS |

Each test needs an isolated fixture with actors, owners/tenants, authorities, allowed/denied IDs, and distinct sensitive field values to detect leaks. If a test only asserts HTTP `200`, `403`, or mocks fixed JSON returns, it has not proven authorization at the repository/database level.

## 11. Common Mistakes, Causes, and Fixes

1. **“Protected `/graphql`, so all of GraphQL is safe.”** HTTP only controls entry to the endpoint; add method security and domain policies in every execution path.
2. **“`@PreAuthorize` on the root query is enough.”** A parent resolver may return a valid object while nested fields or other mutations need separate permissions; check objects and fields in reusable services.
3. **“The schema has no sensitive fields, so it must be safe.”** Existing fields can still leak PII; schema changes can accidentally expose entity getters. Use field-restricted DTOs and review new schemas/resolvers.
4. **“Fetch the entity and let GraphQL auto-map all getters.”** The default property fetcher can access properties developers did not intend to protect with separate resolvers. Return minimal projections and add explicit data fetchers/permissions for sensitive fields.
5. **“Only check the ID on the initial query.”** An object can also come from search, node, relations, subscriptions, and batch loaders; every path must share the policy.
6. **“The user has `DOC_READ`, so they can view any ID.”** `hasAuthority` is a function permission, not row-level permission. Embed actor/tenant/ACL into the query itself.
7. **“Filter using client-supplied tenant/owner.”** Users can forge owner/tenant; take them from authentication and bind the actor in the service.
8. **“GraphQL errors must always be HTTP 403.”** Denials in resolvers can return HTTP 200 + `errors` + partial `data`; test at the GraphQL level properly.
9. **“Returning `null` is always safe.”** Certain errors, `extensions`, or timing differences can disclose object existence; review responses and domain policy.
10. **“Batch/loader caching is a harmless optimization.”** Caches mixing identities or skipping per-ID filtering can leak data across users/tenants.
11. **“Disabling introspection secures GraphQL.”** Attackers can still send known queries or guess the schema; authorization must live on the server.
12. **“An error was returned, so nothing was written.”** Mutations may have already committed or emitted events; assert state and side effects after requests.

## 12. Self-Check Exercises and Acceptance Criteria

**Exercise A — BOLA:** build a query with two aliases `own` and `foreign` targeting IDs 101/102. For actor Alice with `DOC_READ`, prove 101 returns title while 102 returns no data. Repeat the query through a nested relation such as `project.documents` to ensure no bypass exists.

**Exercise B — BOPLA:** on the same object 101, compare responses when the actor has vs lacks `DOC_NOTE_READ`. Verify the secret does not appear in `data`, `errors`, extensions, or response logs when denied. Test a `String!` schema and observe null bubbling to understand non-null field impact.

**Exercise C — mutation:** try archiving 102 with `DOC_ARCHIVE` permission; assert database and business events remain unchanged. Try 101 to prove the permitted path still works. Repeat without the function authority.

**Acceptance criteria:** real authentication exists in the test context, resolver/service authorization decisions are active, every ID is checked at the domain/data layer, sensitive fields have dedicated policies, error responses are sanitized, zero unauthorized side effects occur, and other GraphQL paths to the same object do not bypass policy. Whenever adding resolvers, `@BatchMapping`, search queries, or subscriptions, add corresponding tests **before considering it a safe access path**.

## References

- Spring for GraphQL — Security: https://docs.spring.io/spring-graphql/reference/security.html
- Spring for GraphQL — Annotated Controllers and `@BatchMapping`: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring for GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- Spring Security — Method Security and `@PreAuthorize`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- GraphQL — Authorization: https://graphql.org/learn/authorization/
- GraphQL — Serving over HTTP: https://graphql.org/learn/serving-over-http/
