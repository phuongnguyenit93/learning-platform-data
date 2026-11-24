# Scoping Queries to the Current User or Organization in Spring Security

> **Topic:** Record-level data protection (*record-level authorization*) in Spring Boot/Spring Security applications. This lesson focuses on two scoping patterns: only data **belonging to the logged-in user** and only data **belonging to an organization the user is permitted to access**. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and Spring Data JPA/H2 on the Servlet stack. This lesson is about protecting **data queries**; HTTP authentication and roles are only prerequisites.

## 1. Why Can an Authenticated User Still View Someone Else's Data?

Suppose a system stores work records:

| ID | Owner | Organization | Content |
| --- | --- | --- | --- |
| `101` | `alice` | `org-alpha` | Alice's private note |
| `102` | `bob` | `org-alpha` | Bob's note in Alpha |
| `103` | `bob` | `org-beta` | Bob's note in Beta |

Alice has a valid account with the `USER` role. If a controller only requires `.authenticated()` and then calls `repository.findById(103)`, Alice can change the ID in the URL to retrieve Bob's note belonging to Beta. This is a form of **Broken Object Level Authorization (BOLA)**, also known as **IDOR** (*Insecure Direct Object Reference*). Data is leaked even though Spring Security authenticated the user successfully.

**Core principle:** *Access permission must be a condition of the data query or operation itself*, based on the authenticated identity and verified organization scope. Hiding buttons or rows in the frontend, checking `ROLE_USER`, or using hard-to-guess UUIDs cannot replace this check.

### 1.1. Two Policies That Must Be Kept Separate

**User-scoped (*owner-scoped*):** `/api/me/items` returns **only** items where `ownerUserId = currentUserId`. A member of the same organization cannot implicitly view another person's private data.

**Organization-scoped (*organization-scoped / tenant-scoped*):** `/api/organizations/{orgId}/items` returns items belonging to `organizationId = orgId`, **but only after** the server verifies that the logged-in user is a member with read permission in that organization. Under a collaborative policy, Alice and Bob can both view items in `org-alpha`, but cannot view `org-beta` simply by changing the URL.

Choose the policy according to the **resource type and business rules**. Having an `organization_id` column on a table does not mean every member can view all records; private documents inside an organization may require **both** organization and owner conditions.

| Access path | Mandatory condition | Common mistake |
| --- | --- | --- |
| "My" list | `owner_user_id = principal.userId` | Client sends `?userId=bob` and the server trusts it. |
| "My" detail | `id = :id AND owner_user_id = :currentUserId` | `findById(id)` and returning the entity directly. |
| Organization list | Membership/permission check and `organization_id = :authorizedOrgId` | Filtering only by `orgId` taken from the URL. |
| Organization detail | Membership/permission check and `id = :id AND organization_id = :authorizedOrgId` | Checking membership, then querying the item globally by ID. |
| Private resource in org | Membership/permission and both `organization_id` and `owner_user_id`/ACL | Combining conditions wrongly with `OR`, widening the scope. |

`owner_user_id` should be a **stable** identifier (such as a user ID or verified OIDC subject). `created_by` used for auditing is **not necessarily** the current owner or the basis for granting access; define the semantics of each column clearly.

## 2. Three Layers of Defense: Authentication, Permission, Data Scope

A secure data-query request typically follows this sequence:

```text
HTTP request
  |
  v
Spring Security authentication (Authentication)
  |-- invalid --> 401 for Basic/Bearer API, or login redirect
  v
Trusted principal (authenticated userId/username)
  |
  +-- user-scoped endpoint: currentUserId
  |
  +-- org-scoped endpoint: client-requested orgId
  |        |
  |        +--> look up currentUserId's membership/permissions for orgId
  |                  |-- not permitted --> 403 (or 404 per policy)
  |                  +-- permitted --> authorizedOrgId
  v
Service builds query with user/org constraint directly in database
  |
  +-- no record found in scope --> 404 / empty list
  v
DTO containing only permitted data -> HTTP response
```

**Authentication** confirms identity. **Endpoint authorization** confirms whether the caller may invoke the function. **Data scope** ensures returned rows belong to the right boundary. Having only `@PreAuthorize("isAuthenticated()")` or `hasRole("USER")` is insufficient when users with the same role own different data.

Trusted data sources include:

- `Authentication`/`@AuthenticationPrincipal` verified by Spring Security: `authentication.getName()` can be used in username/password examples.
- Organization memberships and permissions stored in the database/server or another verified authorization source, **never taken from the request body as an unquestioned truth**.
- `sub`, `tenant`, and `org_id` claims in a token are **only trustworthy** after signature, issuer, audience, expiry, and application policies have been validated; a token establishes identity/claims, not automatically active permissions across every organization.

Never take `userId` from `@RequestParam`, `X-User-Id`, `X-Tenant-Id`, or a JSON body to decide ownership when those values are client-supplied. `orgId` in the URL may represent **the organization the user wants to view**, but it must pass membership verification before being bound into the query. For internal tasks without an HTTP principal, supply a **separately authorized system context**, never defaulting to global scope.

### 2.1. Enforcing the Scope Directly in SQL/JPQL

**Prone to data leaks:**

```java
// Wrong for private data endpoints: filters only by ID.
WorkItem item = repository.findById(id).orElseThrow();
// Checking after fetching globally is easy to miss in other branches.
```

**Correct for owner-scoped:**

```sql
SELECT id, title, organization_id
FROM work_items
WHERE id = :id
  AND owner_user_id = :current_user_id;
```

**Correct for organization-scoped after verifying organization permission:**

```sql
SELECT id, title, owner_user_id
FROM work_items
WHERE id = :id
  AND organization_id = :authorized_org_id;
```

Having both conditions in **one query** ensures even a guessed ID cannot return an out-of-scope record. Parameters are bound via JPA/JDBC; never concatenate SQL manually from username, orgId, or client input.

**Avoid "fetch everything then filter in Java"**: out-of-scope data is already loaded into the process, wastes RAM, and can end up in logs/caches or accidentally leak into responses. `Page`/`Slice`, counts, sorting, and search leak data even more easily if filtering happens after pagination.

## 3. Runnable Java 17+ Example: Users and Organizations

This example builds a Spring Boot application with 2 users `alice` and `bob` (HTTP Basic) and 2 organizations `org-alpha` and `org-beta`. Alice belongs to Alpha; Bob belongs to both Alpha and Beta. Items are stored in H2/JPA. Illustrative policy:

- `/api/me/items` and `/api/me/items/{id}` read only items owned by the current user.
- `/api/organizations/{orgId}/items` and `.../{id}` allow organization members to read **all items of that organization**. This policy is for **shared data** and must not be applied to private data.
- Per-organization roles are omitted in this example; membership checks live in the database. Production systems should also store roles and per-membership READ/WRITE permissions.

### 3.1. Create the Project

Create the following files in a Gradle project using Java 17 and Gradle 8.x.

`settings.gradle`:

```groovy
rootProject.name = 'scoped-query-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
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
spring.datasource.url=jdbc:h2:mem:scoped_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`ddl-auto=create-drop` is for the **H2 demo only**, not a replacement for production migrations. Spring Boot 3.3.5 is pinned for reproducibility and does not imply it is the latest version.

### 3.2. Complete Source Code

Put **all** of the code below into `src/main/java/demo/scope/ScopedQueryApplication.java`. Java allows one `public class` and multiple package-private classes/records in the same file. No extra Java files are needed for the other classes.

```java
package demo.scope;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ScopedQueryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedQueryApplication.class, args);
    }

    @Bean
    CommandLineRunner sampleData(
            WorkItemRepository items,
            MembershipRepository memberships) {
        return args -> {
            memberships.saveAll(List.of(
                new OrgMembership("alice", "org-alpha"),
                new OrgMembership("bob", "org-alpha"),
                new OrgMembership("bob", "org-beta")
            ));

            items.saveAll(List.of(
                new WorkItem("alice", "org-alpha", "alice-private"),
                new WorkItem("bob", "org-alpha", "bob-alpha"),
                new WorkItem("bob", "org-beta", "bob-beta")
            ));
        };
    }
}

@Entity
@Table(
    name = "work_items",
    indexes = {
        @Index(name = "idx_item_owner", columnList = "owner_username,id"),
        @Index(name = "idx_item_org", columnList = "organization_id,id")
    }
)
class WorkItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(name = "organization_id", nullable = false)
    private String organizationId;

    @Column(nullable = false)
    private String title;

    protected WorkItem() {}

    WorkItem(String ownerUsername, String organizationId, String title) {
        this.ownerUsername = ownerUsername;
        this.organizationId = organizationId;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getOwnerUsername() { return ownerUsername; }
    public String getOrganizationId() { return organizationId; }
    public String getTitle() { return title; }
}

@Entity
@Table(
    name = "org_memberships",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_membership",
        columnNames = {"username", "organization_id"}
    )
)
class OrgMembership {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String username;

    @Column(name = "organization_id", nullable = false)
    private String organizationId;

    protected OrgMembership() {}

    OrgMembership(String username, String organizationId) {
        this.username = username;
        this.organizationId = organizationId;
    }
}

// Note: These methods always include an owner or organization condition.
// JpaRepository still exposes findAll/findById; the service layer must not
// use them to serve private data endpoints.
interface WorkItemRepository extends JpaRepository<WorkItem, Long> {
    List<WorkItem> findByOwnerUsernameOrderByIdAsc(String username);

    Optional<WorkItem> findByIdAndOwnerUsername(
        Long id, String username
    );

    List<WorkItem> findByOrganizationIdOrderByIdAsc(String organizationId);

    Optional<WorkItem> findByIdAndOrganizationId(
        Long id, String organizationId
    );
}

interface MembershipRepository extends JpaRepository<OrgMembership, Long> {
    boolean existsByUsernameAndOrganizationId(
        String username, String organizationId
    );
}

record ItemView(Long id, String title, String organizationId) {
    static ItemView from(WorkItem item) {
        return new ItemView(
            item.getId(), item.getTitle(), item.getOrganizationId()
        );
    }
}

@Service
@Transactional(readOnly = true)
class ItemQueryService {
    private final WorkItemRepository items;
    private final MembershipRepository memberships;

    ItemQueryService(
            WorkItemRepository items,
            MembershipRepository memberships) {
        this.items = items;
        this.memberships = memberships;
    }

    List<ItemView> listMine(String currentUsername) {
        return items.findByOwnerUsernameOrderByIdAsc(currentUsername)
            .stream()
            .map(ItemView::from)
            .toList();
    }

    ItemView getMine(Long id, String currentUsername) {
        return items.findByIdAndOwnerUsername(id, currentUsername)
            .map(ItemView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND)
            );
    }

    List<ItemView> listOrganization(
            String organizationId, String currentUsername) {
        requireMembership(currentUsername, organizationId);
        return items.findByOrganizationIdOrderByIdAsc(organizationId)
            .stream()
            .map(ItemView::from)
            .toList();
    }

    ItemView getOrganizationItem(
            Long id, String organizationId, String currentUsername) {
        requireMembership(currentUsername, organizationId);
        return items.findByIdAndOrganizationId(id, organizationId)
            .map(ItemView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND)
            );
    }

    private void requireMembership(
            String username, String organizationId) {
        if (!memberships.existsByUsernameAndOrganizationId(
                username, organizationId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
    }
}

@RestController
@RequestMapping("/api")
class ItemController {
    private final ItemQueryService service;

    ItemController(ItemQueryService service) {
        this.service = service;
    }

    @GetMapping("/me/items")
    List<ItemView> mine(Authentication authentication) {
        return service.listMine(authentication.getName());
    }

    @GetMapping("/me/items/{id}")
    ItemView mineById(
            @PathVariable("id") Long id,
            Authentication authentication) {
        return service.getMine(id, authentication.getName());
    }

    @GetMapping("/organizations/{orgId}/items")
    List<ItemView> byOrganization(
            @PathVariable("orgId") String orgId,
            Authentication authentication) {
        return service.listOrganization(
            orgId, authentication.getName()
        );
    }

    @GetMapping("/organizations/{orgId}/items/{id}")
    ItemView oneInOrganization(
            @PathVariable("orgId") String orgId,
            @PathVariable("id") Long id,
            Authentication authentication) {
        return service.getOrganizationItem(
            id, orgId, authentication.getName()
        );
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
```

### 3.3. Protection Breakdown

**First, username comes from the principal.** The controller only passes `authentication.getName()` after Spring Security has authenticated the request; `/api/me/items` never accepts an arbitrary `userId` from the client to pick another user's data. Using username keeps the demo simple; production should use a stable user ID because usernames can change.

**Second, owner queries always attach the owner condition.** `findByOwnerUsernameOrderByIdAsc(username)` corresponds to `WHERE owner_username = ? ORDER BY id`; `findByIdAndOwnerUsername(id, username)` requires **both the ID and owner**. If Alice guesses Bob's ID, the method returns `Optional.empty()` and the API returns 404.

**Third, organization routes have two independent barriers.** `requireMembership(...)` checks the **authenticated user** against `orgId` on the server; then `findByOrganizationId...` filters data by that permitted organization. Membership is never inferred solely from the `USER` role; Bob and Alice share the same role yet belong to different organizations.

**Fourth, 403 and 404 are deliberate.** Not a member of the organization → 403 in the demo policy. Permitted to read the organization, but the item does not exist **within that organization** → 404; does not disclose whether the item exists in another organization. A system may also return 404 consistently for both cases to reduce resource enumeration, as long as policy is consistent.

**Fifth, responses are DTOs only.** `ItemView` contains only necessary fields. Never expose JPA entities, lazy associations, password hashes, or sensitive membership details directly in JSON.

**Sixth, data is filtered at the repository.** Neither `items.findAll()` nor `items.findById(id)` is called in the HTTP-facing service. In large systems, provide a scoped data-access API by default and restrict "global" query paths from being accidentally called by controllers.

### 3.4. Running and Testing with curl

Use the Gradle Wrapper if available:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. If no wrapper exists, run `gradle bootRun` with a compatible Gradle 8.x installation. The commands below run in Bash with `curl` while the app is at `http://localhost:8080`:

```bash
# Unauthenticated
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me/items

# Alice views her own data
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 http://localhost:8080/api/me/items

# Alice is allowed to view shared data in Alpha
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 \
  http://localhost:8080/api/organizations/org-alpha/items

# Alice is not a member of Beta
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 \
  http://localhost:8080/api/organizations/org-beta/items

# Bob is a member of Beta
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:bob123 http://localhost:8080/api/organizations/org-beta/items

# Wrong password
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:wrong http://localhost:8080/api/me/items
```

Expected HTTP codes in order:

```text
401
200
200
403
200
401
```

To inspect actual data, call:

```bash
curl -s -u alice:alice123 http://localhost:8080/api/me/items
curl -s -u alice:alice123 \
  http://localhost:8080/api/organizations/org-alpha/items
```

The first command returns only `alice-private`; the second returns both `alice-private` and `bob-alpha` per Alpha's collaboration policy; **neither command** lets Alice see `bob-beta`. IDs are generated by H2 at runtime, so avoid hard-coding IDs in manual test scripts.

> **Practical note:** Basic auth and hard-coded accounts are for demo purposes only. HTTP Basic sends credentials with requests; real deployments require HTTPS and brute-force protection. The example only has `GET` endpoints so CSRF is not disabled. When adding state-changing operations via browser/cookie or Basic auth, evaluate and handle CSRF appropriately.

## 4. Testing Cross-Scope Access Prevention with MockMvc

Do not test only that the "authorized" user receives 200. You must prove a user **cannot access someone else's data**, even when knowing the exact ID and trying to swap organizations.

Create `src/test/java/demo/scope/ScopedQuerySecurityTest.java`:

```java
package demo.scope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ScopedQuerySecurityTest {
    @Autowired MockMvc mvc;
    @Autowired WorkItemRepository items;

    private Long idOf(String title) {
        // findAll() is only for preparing test data,
        // never to serve user-facing endpoints.
        return items.findAll().stream()
            .filter(item -> item.getTitle().equals(title))
            .findFirst()
            .orElseThrow()
            .getId();
    }

    @Test
    void unauthenticatedUserIsRejected() throws Exception {
        mvc.perform(get("/api/me/items"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerListDoesNotLeakOtherUsers() throws Exception {
        mvc.perform(get("/api/me/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title").value("alice-private"));
    }

    @Test
    void changingQueryParameterCannotImpersonateOwner() throws Exception {
        mvc.perform(get("/api/me/items?ownerUsername=bob")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title").value("alice-private"));
    }

    @Test
    void aliceCannotReadBobsItemById() throws Exception {
        Long bobsId = idOf("bob-alpha");
        mvc.perform(get("/api/me/items/{id}", bobsId)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void memberCanReadSharedOrganizationItems() throws Exception {
        mvc.perform(get("/api/organizations/org-alpha/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    void nonMemberCannotListAnotherOrganization() throws Exception {
        mvc.perform(get("/api/organizations/org-beta/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void itemCannotEscapeOrganizationScope() throws Exception {
        Long betaItemId = idOf("bob-beta");
        mvc.perform(get(
                "/api/organizations/org-alpha/items/{id}", betaItemId)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void authorizedMemberCanListTheirOrganization() throws Exception {
        mvc.perform(get("/api/organizations/org-beta/items")
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title").value("bob-beta"));
    }
}
```

Run:

```bash
./gradlew test
```

Or `gradlew.bat test` on Windows. These tests use `httpBasic(...)`, so requests pass through the real authentication filters and controller; do not assume `@WithMockUser` alone covers the full integration.

**Most critical cases:** knowing Bob's item ID yet failing to access it from `/me` (404); having Alpha membership yet failing to fetch a Beta item by injecting the Beta ID into the Alpha URL (404); lacking Beta membership and being blocked from listing Beta (403). These cases directly verify data boundaries rather than just authentication.

## 5. Extending to Pagination, Search, Analytics, and Export

Query scoping must be present on **every** data path, not only read-by-ID endpoints.

### 5.1. Properly Scoped Pagination

Wrong: reading a global page and filtering `owner` in Java. For example, the first page might hold 20 items belonging to other users, leaving 0 items after filtering even when the user has data on later pages; moreover, total item counts and ordering can leak information.

Correct: define repository methods scoped **before pagination**:

```java
// These signatures are additional methods for
// WorkItemRepository, not a standalone class.
Page<WorkItem> findByOwnerUsername(
    String username, Pageable pageable
);

Page<WorkItem> findByOrganizationId(
    String organizationId, Pageable pageable
);
```

Import `org.springframework.data.domain.Page` and `Pageable`. The service must check organization membership before calling the org method. With `Page`, Spring Data runs an additional count query for totals; **the count query must keep the same filter**. For complex custom JPQL queries, review `countQuery` to include the same `WHERE`/`JOIN`/tenant scope.

### 5.2. Search and Sorting

The condition clause should follow this structure:

```sql
SELECT *
FROM work_items
WHERE organization_id = :authorized_org_id
  AND title LIKE :safe_search_pattern
ORDER BY id
LIMIT :limit OFFSET :offset;
```

`authorized_org_id` is mandatory and must not vanish when `search` is empty. Avoid writing `WHERE organization_id = :id OR title LIKE ...` because `OR` can widen the scope to other organizations. When combining multiple search criteria, use explicit parentheses:

```sql
WHERE organization_id = :authorized_org_id
  AND (title LIKE :q OR description LIKE :q)
```

Validate/allowlist sort fields so arbitrary SQL column names are never accepted; cap page sizes to prevent abuse. Use parameter binding and `LIKE` escaping rules when accepting `%`/`_` characters from users to avoid unexpectedly broad search matches.

### 5.3. Aggregates, Counts, Dashboards, and Exports

A `count(*)` without `WHERE organization_id = :authorized_org_id` still leaks another organization's data volume. `SUM`, `GROUP BY`, charts, CSV/XLSX exports, report jobs, autocomplete, search indexes, and batch APIs need the exact same policy. Never expose a separate export endpoint calling `findAll()` under the excuse that it "only exports data".

When querying across `JOIN`s, filter by tenant on **every table with a security boundary** or verify cross-tenant references cannot exist. For example, if an item has `organization_id = alpha` but references a `customer_id` belonging to Beta, filtering only the item may not suffice; enforce foreign key/relational constraints and check related data.

## 6. Updates, Deletes, and Creates Must Also Be Scoped

Protecting read queries is mandatory but not sufficient. **Update/delete/batch** must enforce an equivalent policy; never verify permissions on `GET` while leaving `PATCH` or `DELETE` globally accessible.

### 6.1. Conditional Write in a Single Statement

Additional JPQL example for the repository; this is an **illustrative integration snippet**, not a standalone endpoint:

```java
@Modifying
@Query("""
    update WorkItem w
       set w.title = :newTitle
     where w.id = :id
       and w.ownerUsername = :currentUsername
    """)
int renameOwned(
    @Param("id") Long id,
    @Param("currentUsername") String currentUsername,
    @Param("newTitle") String newTitle
);
```

Import `org.springframework.data.jpa.repository.Modifying`, `Query`, and `org.springframework.data.repository.query.Param`, and invoke the method inside a write transaction (`@Transactional`, not readOnly). A **`0` row result** means no modifiable record was found in scope; the API can return 404. JPQL bulk updates bypass some lifecycle callbacks and can leave the persistence context stale, so check domain/audit rules and clear/refresh the context when needed.

### 6.2. Creation and Organization Transfer

When creating an item, **never accept `ownerUsername` from the request as the trusted owner**; set the owner server-side from the principal. If the client selects `organizationId`, verify `CREATE` permission in that organization before persisting. When changing organization or owner, enforce an explicit **ownership transfer** policy, checking permissions on both source and target rather than treating it as a normal field update. When saving child records or attachments, bind the child to the same parent item scope.

### 6.3. Avoid Separating the Permission Check from the Write

The pattern `findById(id)`, check membership, and then `save(entity)` in another transaction can suffer from permissions or organization changing in between (**TOCTOU**). For sensitive operations, consider conditional `UPDATE ... WHERE id = ? AND organization_id = ?`, locking/`@Version`, proper transaction boundaries, or re-verifying permissions consistently at write time. Never assume a permission checked in an earlier request remains valid forever.

## 7. Safely Selecting the "Current Organization"

A user can belong to multiple organizations. The "current organization" must be a **selected and verified scope**:

1. Client requests to view `org-alpha` (via URL, session, or UI selection).
2. Server authenticates the current user.
3. Server verifies the user is still a member and holds the required permission in `org-alpha`.
4. Only then is **authorizedOrgId** passed into service/repository queries.
5. If membership is missing, permission is lacking, org is invalid, or context is ambiguous: **fail closed** (403/404), never dropping the `WHERE` clause to "return everything".

**Never treat an `X-Tenant-Id` HTTP header or `tenantId` query parameter as pre-authorized**: it is merely a client-requested value unless overwritten by a trusted gateway after verification with all bypass paths blocked. Never rely solely on a global `ROLE_ADMIN` to grant access across all organizations; support/super-admin privileges require a separate policy and audit trail.

If using a JWT with an `org_id` claim, the server must validate the signature and token completely and decide whether that claim represents the selected org, permissions at issuance time, or just a hint. When membership is revoked, old claims can become stale; enforce TTL, revocation, or live permission checks appropriate to the risk level.

**Shared-database multi-tenancy:** `organization_id` is a data boundary and should have indexes, foreign keys, per-organization unique constraints (e.g., `(organization_id, external_code)`), and safeguards against cross-tenant references. If the database supports Row-Level Security (such as PostgreSQL RLS), it can serve as an additional defense layer. However, the app must bind the tenant context properly per **transaction/connection** to avoid leaks across pooled connections; RLS does not replace verifying that the user is allowed to select that tenant.

## 8. Common Security Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `findById(id)` in a private endpoint's service | IDOR/BOLA: guessing IDs reveals other records | `findByIdAndOwner...` or `findByIdAndOrganizationId...`. |
| `findAll()` then `.filter(...)` | Leaks via logs/cache, wrong paging/counts, wasted resources | Push conditions into the DB query. |
| Trusting `userId`/`orgId` from client | Principal spoofing or tenant switching | Get user from SecurityContext, verify org membership. |
| Using `hasRole("USER")` for all queries | Users with the same role see each other's data | Enforce owner/org/ACL authorization at the data layer. |
| `WHERE tenant=:id OR ...` | `OR` can widen results cross-tenant | Mandatory tenant predicate with grouped search conditions in parentheses. |
| Checking membership then reading item by global ID | Alpha member reads a Beta item ID | Membership check **and** `WHERE organization_id=:orgId`. |
| Protecting GET only | PATCH/DELETE/export still leak or write cross-scope | Scope every mutation and bulk query. |
| Cache key by `itemId` only | One user/tenant's cache serves another | Include tenant/permission scope in cache keys or carefully cache authorized results. |
| `ThreadLocal` tenant not reset | Next request inherits stale tenant context | Prefer passing scope explicitly; if using thread context, wrap in `try/finally` and handle async. |
| Dropping filter when "org not found" | Fails open and returns global data | Fail closed: 403/404 or empty list per policy. |

### 8.1. Async, Background Jobs, Event Consumers, Webhooks

`Authentication` in `SecurityContextHolder` is typically bound to the request thread and is **not guaranteed to be present in `@Async`, schedulers, queue consumers, or background jobs**. Do not call `SecurityContextHolder.getContext().getAuthentication().getName()` everywhere assuming it is always valid. For background work, pass an explicit validated scope (user/tenant/permissions or service-account policy) and **re-check permissions as needed**. Never propagate a user scope into background jobs that inadvertently run system-wide operations.

### 8.2. Caches and Search Indexes

If an Alpha user populates a cache key `"items:page:1"` without tenant scope, a Beta user could receive Alpha's cached data. Include `authorizedOrgId`, query parameters, and when needed user/permission versions in cache keys. With Elasticsearch or search indexes, **tenant query filters must execute inside the search engine**, including suggestions/autocomplete and aggregations; never filter only the returned page.

### 8.3. User Permissions Changing While Logged In

A user leaves an organization or has access revoked; old sessions/JWTs may stay valid until expiration. If every request trusts stale membership claims, data can continue to leak. Check live membership, enforce suitable TTLs, revocation, and invalidation based on risk. For sensitive data, verify permissions at query execution time.

## 9. Testing and Monitoring Checklist

Before releasing a read/write endpoint with owner/tenant data, verify:

- [ ] Principal is authenticated and obtained from a trusted server source; cannot be spoofed via body/header.
- [ ] Policies for owner, organization, private-in-org, and role/permission are clearly defined.
- [ ] Client-selected org has **membership + permission verified** before querying.
- [ ] Every list/detail/search/page/count/aggregate/export query is scoped in the DB.
- [ ] Out-of-scope IDs return 404/403 per policy without leaking payloads of other records.
- [ ] Update/delete/create/bulk and child resources enforce the same scope.
- [ ] Tested user A accessing B's ID in the same org; user A accessing another org; tampering with URL/query params.
- [ ] Tested `Page.totalElements`, search filters, sorting, and cross-tenant caches.
- [ ] Rules exist for revoked membership, stale tokens, background jobs, or missing context.
- [ ] Logs/audit capture user ID, org ID, request ID, and authorization decisions without logging tokens/passwords/secrets.

**Negative tests matter more than checking 200 alone:** deliberately use Alice's credentials to call Bob's ID and Beta resources. If tests only use `@WithMockUser` on one account or put all test data in a single tenant, the test suite will barely catch any scope bugs.

## 10. Self-Assessment Scenarios

**Scenario A:** `/api/orders/{id}` requires `.authenticated()` and calls `findById(id)`. A user swaps the ID to view another user's order.  
**Analysis:** Authentication succeeded, but object-level authorization is missing. Use `findByIdAndOwnerUserId(id, currentUserId)` or an equivalent permission policy.

**Scenario B:** `/api/organizations/{orgId}/reports` filters by `orgId` from the URL without checking membership.  
**Analysis:** An attacker can change the URL to another organization. Verify membership/READ permission first, then query by the authorized org.

**Scenario C:** Alice belongs to Alpha; item ID 103 belongs to Beta. The API verifies Alice is an Alpha member and then calls `findById(103)`.  
**Analysis:** Still leaks Beta. The query must include **both** `id=103` and `organizationId=Alpha`, not a detached membership check alone.

**Scenario D:** Query `WHERE organization_id=:id OR title LIKE '%urgent%'`.  
**Analysis:** It can return items from other organizations whenever the title matches. It must be `organization_id=:authorizedId AND (search conditions...)`.

**Scenario E:** Items are filtered by organization in `List<Item>`, but the totals API calls table-wide `count()`.  
**Analysis:** The count still leaks cross-tenant statistics. Every secondary query (`countQuery`, `SUM`, autocomplete, export) must apply the same scope.

**Scenario F:** A record has `created_by=alice`, but ownership was transferred to Bob.  
**Analysis:** `created_by` is an audit field and no longer decides who may read if policy is based on `owner_user_id`. Use the actual ownership column/rule.

## 11. Takeaways and References

**Safe formula:** `authenticated principal` → `authorized user/org scope` → `database query with mandatory owner/tenant predicate` → `DTO`. Spring Security handles authentication and HTTP-layer checks; the application must still enforce permissions at the **data-row level**. A properly secured API blocks not only unauthenticated access, but also **authenticated users** from viewing data they do not own or are not authorized by an organization to access.

Official documentation:

- [Spring Security — Authentication Architecture and SecurityContext](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data — Defining Query Methods, Paging, and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
