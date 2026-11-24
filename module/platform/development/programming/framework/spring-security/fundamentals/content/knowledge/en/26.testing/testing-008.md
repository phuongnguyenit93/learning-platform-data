# Testing Allow, Deny, and Resource Ownership in Spring Security

> **Scope:** Testing authorization and per-record ownership (*object-level authorization*) in Spring Boot 3.x, Spring Security 6.x, Spring MVC (Servlet stack), Java 17+, JUnit 5, MockMvc, and Spring Data JPA applications. This lesson combines testing **allowed**, **denied**, and **cannot access someone else's resource**. Examples use HTTP Basic for reproducibility; the same principles apply to form login, sessions, or Bearer tokens after adjusting how principals are supplied.

## 1. Distinguishing the three conditions to test

An application configured with `authenticated()` or `hasRole("USER")` can still leak data: Alice and Bob both hold the `USER` role, yet Alice must not read or modify Bob's private resources. Therefore security tests must verify **who sent the request**, **whether they have permission for the operation**, and **whether the accessed record belongs to their scope**.

| Test category | Question to answer | Example |
| --- | --- | --- |
| **Allow** | Can a valid, authorized user perform the action? | Alice reads Alice's note → 200; admin views admin summary → 200. |
| **Deny** | Are unauthenticated callers or callers lacking a role/authority blocked? | No credentials → 401 with HTTP Basic; Alice calls `/api/admin/summary` → 403. |
| **Resource ownership** | Is an authenticated user blocked when swapping the ID to another user's record? | Alice calls `/api/items/{bobId}` → 404 under a resource-hiding policy. |

**Authentication** proves identity. **Authorization** decides whether an action is allowed. **Ownership** is an authorization condition at the **object/record level**, independent of whether two people share the same role.

An endpoint like `GET /api/items/{id}` protected only with:

```java
.requestMatchers("/api/items/**").authenticated()
```

only proves the client must log in; it **does not automatically check** whether the record belongs to the logged-in user. If the service calls `repository.findById(id)` to return data, a user can swap IDs and read someone else's data. This vulnerability is commonly called **Broken Object Level Authorization (BOLA)** or **IDOR**.

### 1.1. Do not confuse 401, 403, and 404

| Response | Meaning in the HTTP Basic example | Test case |
| --- | --- | --- |
| **401 Unauthorized** | No valid credentials provided or authentication failed. | Anonymous, wrong password. |
| **403 Forbidden** | Authenticated, yet lacks authority for the operation; or rejected by CSRF. | Role USER calls ADMIN route; POST/PATCH/DELETE missing CSRF. |
| **404 Not Found** | Resource not found **within the scope the caller may view**. | Alice tries Bob's resource ID; a non-existent ID. |
| **200 OK** | Resource read or updated successfully. | Alice reads or renames her own item. |
| **201 Created** | Resource created successfully; server assigns owner automatically. | Alice POSTs a new item with valid CSRF. |
| **204 No Content** | Resource deleted successfully with no body. | Alice DELETEs her own item. |

For out-of-scope resources, a system may choose **403 or 404 per policy**. The example in this lesson intentionally uses **404** for both "ID does not exist" and "ID exists but belongs to someone else" to avoid revealing data existence. Therefore **do not force every ownership failure to be 403**. What must be proven is that the response leaks no unauthorized data and produces no unauthorized mutations.

With **form login**, anonymous callers may be redirected to a login page instead of receiving 401; with OAuth2 Bearer, invalid tokens typically return 401. Write assertions matching the auth mechanism your app actually uses.

## 2. Designing the test matrix before writing code

Create two ordinary users `alice` and `bob` sharing `ROLE_USER`, and one admin with `ROLE_ADMIN`. Create at least two records with **different IDs**: `alice-private` owned by Alice and `bob-private` owned by Bob. When testing ownership, you must send **Alice's credentials + Bob's ID** and assert rejection. A single-user fixture can never catch cross-user leaks.

| HTTP request | Identity | Expected |
| --- | --- | --- |
| `GET /api/public` | Anonymous | 200. |
| `GET /api/items` | Anonymous | 401. |
| `GET /api/items` | Alice, wrong password | 401. |
| `GET /api/admin/summary` | Alice (`ROLE_USER`) | 403. |
| `GET /api/admin/summary` | Admin (`ROLE_ADMIN`) | 200. |
| `GET /api/items` | Alice | 200; list contains only Alice's items. |
| `GET /api/items/{aliceId}` | Alice | 200; Alice's exact data. |
| `GET /api/items/{bobId}` | Alice | 404 under owner-scoped policy. |
| `GET /api/items/{bobId}` | Bob | 200. |
| `GET /api/items?ownerUsername=bob` | Alice | Still returns only Alice's data; query param cannot pick owner. |
| `GET /api/items/{bobId}` | Non-owner admin | 404: ADMIN role does not automatically bypass ownership without an explicit policy. |
| `POST /api/items` | Alice, missing CSRF | 403 under the demo's default CSRF config. |
| `POST /api/items` | Alice, valid CSRF | 201; server assigns owner as Alice. |
| `PATCH /api/items/{bobId}` | Alice, with CSRF | 404; Bob's item is unchanged. |
| `DELETE /api/items/{bobId}` | Alice, with CSRF | 404; Bob's item still exists. |
| `PATCH /api/items/{aliceId}` | Alice, with CSRF | 200; only Alice's item changes. |
| `DELETE /api/items/{aliceId}` | Alice, with CSRF | 204; only Alice's item is deleted. |

**Positive and negative tests must come in pairs:** if you only test denied requests, a broken `denyAll()` config can make every test "green." If you only test allowed requests, a broken `permitAll()` config can also make every test "green." You need at least one authorized case and one unauthorized case on the same endpoint group.

### 2.1. Each test must check the right layer

- **Filter-level:** 401 when anonymous, 403 when lacking a role or missing/invalid CSRF.
- **Service/repository-level:** queries actually include `owner` or `tenant`, not calling a global `findById` for private endpoints.
- **Object-level:** Alice cannot access Bob's record, even if she guesses the ID.
- **Mutation-level:** POST/PUT/PATCH/DELETE must be blocked when unauthorized; the response is rejected **and the database does not change**.
- **Serialization-level:** responses return tight DTOs, never serializing full entities or out-of-scope record data.

A `@WithMockUser` can supply a mock principal to test rules, yet **does not prove** passwords, providers, or `SecurityFilterChain` mappings actually execute. The integration examples use `httpBasic(...)` so credentials flow through filters and providers.

## 3. Java 17+ sample application structure

The example uses HTTP Basic, JPA/H2, and a `work_items` table with `owner_username`. Accounts:

- `alice` / `alice123` — `ROLE_USER`.
- `bob` / `bob123` — `ROLE_USER`.
- `admin` / `admin123` — `ROLE_ADMIN`.

Policy:

1. Anyone can call `GET /api/public`.
2. `/api/admin/**` requires `ROLE_ADMIN`.
3. `/api/items` and `/api/items/{id}` require authentication.
4. The service reads the **authenticated username** from `Authentication`, then only finds/updates/deletes items matching **both** `id` and `owner_username`.
5. Out-of-scope data returns **404**; there is no owner bypass for admins.
6. Spring Security CSRF stays enabled by default, so POST/PATCH/DELETE in MockMvc must send a valid CSRF token.

### 3.1. Gradle files

`settings.gradle`:

```groovy
rootProject.name = 'ownership-security-test'
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

Spring Boot **3.3.5** is an illustrative version pinned for reproducible configuration, **not a claim of the latest release**. Spring Boot manages compatible Spring Security Test/JPA/JUnit versions; do not declare a separate `spring-security-test` version when using this BOM.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:ownership_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`create-drop` is only for H2 demos/tests. Production should use migrations (Flyway/Liquibase), strict schema control, and tight database permissions. Use JDK 17+ and a Gradle 8.x version compatible with Spring Boot 3.3.x.

### 3.2. Complete application code

Create **one** file `src/main/java/demo/ownership/OwnershipSecurityApplication.java`. Java permits one public class matching the filename alongside multiple package-private classes in the same package; hence the code below is a complete Spring Boot program for the demo.

```java
package demo.ownership;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

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
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class OwnershipSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipSecurityApplication.class, args);
    }

    @Bean
    CommandLineRunner exampleData(WorkItemRepository items) {
        return args -> items.saveAll(List.of(
            new WorkItem("alice", "alice-private"),
            new WorkItem("bob", "bob-private")
        ));
    }
}

@Entity
@Table(
    name = "work_items",
    indexes = @Index(name = "idx_work_item_owner",
                     columnList = "owner_username")
)
class WorkItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected WorkItem() {}

    WorkItem(String ownerUsername, String title) {
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}

// Repository provides both general CRUD operations and scoped queries.
// The API-protecting service must use owner-scoped queries.
interface WorkItemRepository extends JpaRepository<WorkItem, Long> {
    List<WorkItem> findByOwnerUsernameOrderByIdAsc(
        String ownerUsername
    );

    Optional<WorkItem> findByIdAndOwnerUsername(
        Long id, String ownerUsername
    );
}

record ItemView(Long id, String title) {
    static ItemView from(WorkItem item) {
        return new ItemView(item.getId(), item.getTitle());
    }
}

record CreateItemRequest(String title) {}

record RenameItemRequest(String title) {}

@Service
class WorkItemService {
    private final WorkItemRepository items;

    WorkItemService(WorkItemRepository items) {
        this.items = items;
    }

    @Transactional(readOnly = true)
    public List<ItemView> listMine(String currentUsername) {
        return items.findByOwnerUsernameOrderByIdAsc(currentUsername)
            .stream()
            .map(ItemView::from)
            .toList();
    }

    @Transactional(readOnly = true)
    public ItemView getMine(Long id, String currentUsername) {
        return ItemView.from(requireOwned(id, currentUsername));
    }

    @Transactional
    public ItemView createMine(
            String currentUsername, String newTitle) {
        validateTitle(newTitle);
        WorkItem item = items.save(
            new WorkItem(currentUsername, newTitle)
        );
        return ItemView.from(item);
    }

    @Transactional
    public ItemView renameMine(
            Long id, String currentUsername, String newTitle) {
        validateTitle(newTitle);
        WorkItem item = requireOwned(id, currentUsername);
        item.rename(newTitle); // JPA dirty checking within the transaction
        return ItemView.from(item);
    }

    @Transactional
    public void deleteMine(Long id, String currentUsername) {
        WorkItem item = requireOwned(id, currentUsername);
        items.delete(item);
    }

    private WorkItem requireOwned(Long id, String username) {
        return items.findByIdAndOwnerUsername(id, username)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND)
            );
    }

    private void validateTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "title must not be blank"
            );
        }
    }
}

@RestController
@RequestMapping("/api")
class WorkItemController {
    private final WorkItemService service;

    WorkItemController(WorkItemService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin/summary")
    public String adminSummary() {
        return "admin-summary";
    }

    @GetMapping("/items")
    public List<ItemView> list(Authentication authentication) {
        return service.listMine(authentication.getName());
    }

    @GetMapping("/items/{id}")
    public ItemView getById(
            @PathVariable("id") Long id,
            Authentication authentication) {
        return service.getMine(id, authentication.getName());
    }

    @PostMapping("/items")
    @ResponseStatus(HttpStatus.CREATED)
    public ItemView create(
            @RequestBody CreateItemRequest body,
            Authentication authentication) {
        return service.createMine(
            authentication.getName(), body.title()
        );
    }

    @PatchMapping("/items/{id}")
    public ItemView rename(
            @PathVariable("id") Long id,
            @RequestBody RenameItemRequest body,
            Authentication authentication) {
        return service.renameMine(
            id, authentication.getName(), body.title()
        );
    }

    @DeleteMapping("/items/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable("id") Long id,
            Authentication authentication) {
        service.deleteMine(id, authentication.getName());
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
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error", "/api/public").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
```

### 3.3. Security details you must understand

**Derive owner from the principal.** The controller uses `authentication.getName()` verified by Spring Security, never taking `ownerUsername` from a query param or request body as an authorization source. In real applications, prefer a **stable user ID** from the verified principal/`sub` rather than a mutable username.

**Use owner-scoped queries.** `findByIdAndOwnerUsername(id, username)` enforces that **both ID and owner match** in SQL. If the ID belongs to someone else, the query returns no record and the service returns 404. `findByOwnerUsernameOrderByIdAsc` lists only the principal's data rather than loading everything and filtering in Java.

**Role and ownership are two distinct conditions.** The security chain uses `hasRole("ADMIN")` for admin URLs, yet `/api/items/{id}` remains owner-scoped in the service. Under this policy, account `admin` cannot automatically read Bob's items. If support tasks need cross-owner access, declare a **dedicated, bounded, audited permission** rather than silently dropping the ownership check.

**Block write operations too.** `renameMine` and `deleteMine` look up the record **within the owner's scope** before updating or deleting. Tests must confirm Bob's resource **did not change** when Alice sends Bob's ID. A 404 status alone is insufficient if the code triggers side effects before throwing.

**Create securely.** `createMine` assigns ownership from `Authentication`; the DTO carries only `title`. The client cannot choose an owner via an arbitrary field. Real systems should configure unknown-JSON-field handling, input validation, and title length limits.

**DTOs protect responses.** `ItemView` exposes only the ID and title; never serialize raw JPA entities or sensitive passwords/metadata. This avoids unnecessary exposure even when the owner is permitted to read.

**CSRF stays enabled.** In the HTTP Basic example, Spring Security requires a CSRF token by default for state-changing HTTP methods. Test POST/PATCH/DELETE with `.with(csrf())` to verify authorization after valid CSRF; include a separate test for missing tokens. Never disable CSRF just to get a 200 status in tests.

**Never hardcode passwords in production.** The example intentionally uses demo users to illustrate testing. Real deployments require HTTPS, a trusted user store, hashed credentials, and brute-force protections. CSRF and defensive controls depend on the real credential model.

## 4. Testing HTTP and database together with `spring-security-test`

Create `src/test/java/demo/ownership/OwnershipSecurityTest.java`. This is an integration test running with the Spring Boot application, MockMvc, real `SecurityFilterChain`, and H2 database. Each test recreates **two resources owned by two different users** so cases stay independent and never rely on generated IDs being `1`, `2`, or any hardcoded value.

```java
package demo.ownership;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipSecurityTest {
    @Autowired MockMvc mvc;
    @Autowired WorkItemRepository items;

    @BeforeEach
    void resetData() {
        items.deleteAll();
        items.saveAll(List.of(
            new WorkItem("alice", "alice-private"),
            new WorkItem("bob", "bob-private")
        ));
    }

    private Long idFor(String owner) {
        // Use this helper only to fetch fixture IDs in tests.
        return items.findByOwnerUsernameOrderByIdAsc(owner)
            .get(0)
            .getId();
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedListRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/items"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/items")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userRoleCannotUseAdminFunction() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanUseAdminFunction() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-summary"));
    }

    @Test
    void aliceListContainsOnlyHerItems() throws Exception {
        mvc.perform(get("/api/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("alice-private"));
    }

    @Test
    void aliceCanReadHerItem() throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("alice"))
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("alice-private"));
    }

    @Test
    void bobCanReadHisItem() throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("bob"))
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("bob-private"));
    }

    @Test
    void aliceCannotReadBobsItemEvenWhenSheKnowsTheId()
            throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("bob"))
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void queryParameterCannotChangeTheAuthenticatedOwner()
            throws Exception {
        mvc.perform(get("/api/items?ownerUsername=bob")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("alice-private"));
    }

    @Test
    void adminRoleDoesNotImplicitlyBypassItemOwnership()
            throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("bob"))
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void itemIdOutsideTheAuthorizedScopeReturns404()
            throws Exception {
        mvc.perform(get("/api/items/{id}", 999999L)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "alice123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"new-item\"}"))
            .andExpect(status().isForbidden());

        assertThat(items.findByOwnerUsernameOrderByIdAsc("alice"))
            .hasSize(1);
    }

    @Test
    void invalidCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "alice123"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"new-item\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validOwnerCanCreateWithCsrf() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "alice123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"created-by-alice\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title")
                .value("created-by-alice"));

        assertThat(items.findByOwnerUsernameOrderByIdAsc("alice"))
            .extracting(WorkItem::getTitle)
            .contains("created-by-alice");
        assertThat(items.findByOwnerUsernameOrderByIdAsc("bob"))
            .extracting(WorkItem::getTitle)
            .containsExactly("bob-private");
    }

    @Test
    void aliceCannotRenameBobsItem() throws Exception {
        Long bobId = idFor("bob");

        mvc.perform(patch("/api/items/{id}", bobId)
                .with(httpBasic("alice", "alice123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"stolen-title\"}"))
            .andExpect(status().isNotFound());

        assertThat(items.findById(bobId).orElseThrow().getTitle())
            .isEqualTo("bob-private");
    }

    @Test
    void bobCanRenameHisItem() throws Exception {
        Long bobId = idFor("bob");

        mvc.perform(patch("/api/items/{id}", bobId)
                .with(httpBasic("bob", "bob123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"bob-updated\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("bob-updated"));

        assertThat(items.findById(bobId).orElseThrow().getTitle())
            .isEqualTo("bob-updated");
    }

    @Test
    void aliceCannotDeleteBobsItem() throws Exception {
        Long bobId = idFor("bob");

        mvc.perform(delete("/api/items/{id}", bobId)
                .with(httpBasic("alice", "alice123"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        assertThat(items.findById(bobId)).isPresent();
    }

    @Test
    void aliceCanDeleteHerItem() throws Exception {
        Long aliceId = idFor("alice");

        mvc.perform(delete("/api/items/{id}", aliceId)
                .with(httpBasic("alice", "alice123"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertThat(items.findById(aliceId)).isEmpty();
        assertThat(items.findByOwnerUsernameOrderByIdAsc("bob"))
            .hasSize(1);
    }
}
```

### 4.1. Why is this a substantive integration test?

- `@SpringBootTest` loads the full application context, including `SecurityConfiguration`, filter chain, user service, password encoder, controller, service, and JPA/H2.
- `@AutoConfigureMockMvc` enables MockMvc with default filters (`addFilters=false` is not set). Requests execute in-process **without opening a TCP port**.
- `.with(httpBasic(...))` attaches real Basic credentials to the request. Authentication filters/providers must check valid or invalid passwords—unlike mock principals.
- `.with(csrf())` lets tests verify write-request authorization after CSRF passes. Missing/invalid tokens are tested separately.
- `@BeforeEach` deletes and recreates two independent fixtures; tests do not depend on execution order or auto-increment IDs. Updates/deletes in an earlier test do not corrupt later tests.
- Beyond asserting HTTP responses, denied tests also verify **the database did not change** (`bob-private` still exists and did not become `stolen-title`).
- `@WithMockUser` is not used for wrong-password cases, since that annotation skips credential verification.

**Note on fixtures:** `items.findById(...)` and `deleteAll()` inside the test class are strictly for **setting up and verifying** test data. Business endpoints still call only `findByIdAndOwnerUsername(...)`. In real codebases, consider test data builders, transactional fixtures, or a DB container if SQL/locking/migrations depend on the production DB; H2 does not replicate all PostgreSQL/MySQL behavior.

### 4.2. Running tests and the application

If the project has a Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

On Windows:

```bat
gradlew.bat test
gradlew.bat bootRun
```

If no Gradle Wrapper exists yet, run `gradle test` and `gradle bootRun` with a compatible Gradle 8.x version. The sample application listens on port 8080 by default if available.

Bash `curl` commands to observe the read flow:

```bash
# Public
curl -s -i http://localhost:8080/api/public

# Without credentials: typically 401
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/items

# Alice sees her own items
curl -s -u alice:alice123 \
  http://localhost:8080/api/items

# Bob sees his own items
curl -s -u bob:bob123 \
  http://localhost:8080/api/items

# Alice lacks permission for admin summary: 403
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 http://localhost:8080/api/admin/summary

# Admin has ROLE_ADMIN: 200
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin/summary
```

Expected status output when running the 2nd, 5th, and 6th commands respectively:

```text
401
403
200
```

The list command returns JSON for the matching owner, with `id` assigned by H2 at runtime. To test fetching Bob's ID with Alice's credentials, read the ID via Bob's command and then request `/api/items/{id}` as Alice; **the expected status is 404**, without hardcoding IDs. For POST/PATCH/DELETE, use the MockMvc tests shown above to supply CSRF tokens properly.

## 5. Testing authorization boundaries: cases easily missed

### 5.1. Separating role-based authorization from ownership

A user with `ROLE_USER` can invoke a general endpoint; that does not mean they may read every record. When writing tests, create two users **with the same role** to avoid being fooled by role checks:

```text
Alice ROLE_USER -> GET /api/items/{aliceId} => 200
Alice ROLE_USER -> GET /api/items/{bobId}   => 404
Bob   ROLE_USER -> GET /api/items/{bobId}   => 200
```

If tests only have an `ADMIN` user and a `GUEST` user, a 403 result might simply reflect a missing role; you have not proven **owner enforcement**. Conversely, if rules permit an admin to override ownership, define and test that separately; never assume `ROLE_ADMIN` automatically grants access to every record.

### 5.2. Private access vs shared data

Real resources may belong to a **user**, an **organization**, or an **ACL/share grant** list. Do not apply every user-scoped pattern blindly to multi-tenant data:

- **Private note:** condition `id = :id AND owner_user_id = :currentUserId`.
- **Shared organization document:** verify the user has READ permission on the organization, then query `id = :id AND organization_id = :authorizedOrgId`; a member of an org does not automatically read private notes inside that org.
- **Admin/support override:** only when policy allows it, normally requiring a dedicated permission, audit reason, and tests ensuring scope does not widen.
- **Nested resource:** `GET /projects/{projectId}/tasks/{taskId}` must check both project access and that the task truly belongs to the permitted project—not just the global task ID.

Example org-level extension test: Alice belongs to Alpha and Bob belongs to Beta; Alice with the same role as Bob must not retrieve Beta's task even when knowing `taskId`. When a user belongs to multiple organizations, a client-chosen `orgId` is only a **scope hint**; the server must validate membership/permission before using it in queries.

### 5.3. 404 hiding resource existence

Choosing 404 for `findByIdAndOwner...` avoids leaking whether "Bob's ID exists." Still, stay consistent across logging, response schemas, and other operations. An API can intentionally return 403 when a user may know a resource exists yet cannot edit it; that is also a valid design if specified.

**Test both conditions:** neither a non-existent ID nor an existing out-of-scope ID may leak payloads, including exception messages. Never leak owner names or resource contents in error messages such as "Bob's document exists, but Alice lacks access."

### 5.4. Check side effects, not just status codes

A controller might call `save()` first and only afterward check ownership and return 403. Tests asserting only `.andExpect(status().isForbidden())` miss the data mutation. For PATCH/DELETE, verify after the request that:

1. The targeted user's record remains intact.
2. No out-of-scope record was created.
3. A legitimate owner's update actually commits.
4. No unauthorized events or jobs were emitted if the system uses events/outboxes (extend integration tests as needed).

In the example, `assertThat(items.findById(bobId)...).isEqualTo("bob-private")` and `.isPresent()` directly confirm Bob's data stayed untouched after Alice's requests.

### 5.5. Ownership constraints belong in queries, not just the UI

Wrong for a private endpoint:

```java
// Wrong: frontend hides the button, yet backend still fetches the record globally.
WorkItem item = items.findById(id).orElseThrow();
return ItemView.from(item);
```

Right under the example's policy:

```java
WorkItem item = items.findByIdAndOwnerUsername(id, currentUsername)
    .orElseThrow(() ->
        new ResponseStatusException(HttpStatus.NOT_FOUND)
    );
return ItemView.from(item);
```

This snippet illustrates a method body using `items`, `id`, and `currentUsername` already declared in the service; it is **not a standalone Java file**.

Even though checking ownership after `findById(...)` can work, putting the constraint in the query reduces the chance another branch forgets it, prevents loading out-of-scope data into caches/logs, and reuses cleanly for pagination. For concurrent updates, a conditional `UPDATE ... WHERE id=? AND owner_user_id=?` also protects at write time.

## 6. Choosing the right test annotation/tool for the goal

| Tool | What can it test? | What does it not prove on its own? |
| --- | --- | --- |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Integration of HTTP, filter chain, service, and real persistence in the test context. | Does not guarantee production data or every profile matches identically. |
| `@WebMvcTest` | MVC/controller and slice filters/context; good for HTTP boundaries. | Real services/repositories if mocked; owner enforcement in services may be skipped. |
| `@WithMockUser` | Authorization with a simulated principal and authorities. | Passwords, account lookups, authentication providers, or real users. |
| `.with(user("alice").roles("USER"))` | Attaches a simulated principal to one MockMvc request. | Real Basic/form login flows. |
| `.with(httpBasic("alice","alice123"))` | Adds a Basic header so filters/providers check credentials when loaded properly. | The post-processor alone does not prove auth filters are active if MockMvc disabled filters. |
| `.with(csrf())` | Injects a valid CSRF token into the test request. | The full production browser/client token retrieval flow. |
| `@WithUserDetails("alice")` | Loads a fixture user via `UserDetailsService` into `SecurityContext`. | Does not match raw passwords like a login request. |

**Why use a full context for the example?** Ownership is enforced inside `WorkItemService` and the repository. If `@WebMvcTest(WorkItemController.class)` mocks the service to always return Alice's item, a 200 test only proves the controller calls the mock; it will not catch a production service using a global `findById()`. If using slice tests, pair them with **dedicated service/repository integration tests** and at least one HTTP integration test connecting the layers.

`@WithMockUser` is great when testing `@PreAuthorize`, roles, and usernames alone. Yet if you need to test 401 on wrong passwords or password encoders, use `httpBasic(...)`, the form-login processor, or a real Bearer mechanism per config.

### 6.1. Loading the right security chain

- For full context, `@AutoConfigureMockMvc` adds filters by default; never set `addFilters=false` in authentication/authorization tests.
- For `@WebMvcTest`, import the security config under test with `@Import(SecurityConfig.class)` when the slice does not load custom beans automatically. Repositories/services outside the slice must usually be mocked or imported appropriately.
- For MockMvc built manually from `WebApplicationContext`, `.apply(springSecurity())` integrates `FilterChainProxy`.
- With multiple `SecurityFilterChain`s, inspect `securityMatcher`, `@Order`, and HTTP method/path matchers. Test at least one URL per chain, and never assume every URL traverses the same filters.
- For method security (`@PreAuthorize`), `@EnableMethodSecurity` must be active and calls must hit the real Spring bean proxy; if a controller uses a mocked service, method security on the real service may not execute.

**False-test warning:** if you remove all owner rules or switch the repository to `findById`, negative ownership tests must **turn red**. If the test suite stays green when security rules are intentionally removed, check whether it bypasses filters, over-mocks authentication, or asserts only HTTP statuses without checking data.

## 7. Testing pagination, search, export, and bulk operations

A secure detail endpoint does not prove other access paths are safe. As real applications grow, add cases for:

- `GET /api/items?page=0&size=20`: `Page.content` and `totalElements` count only the owner's items; do not fetch a global page and `.filter(...)` in Java.
- `GET /api/items?title=...`: search conditions combine with `owner = :currentUser` using `AND`, never `OR` leaking other users' items.
- `GET /api/items/count`, dashboards, or aggregates: counts/sums must also be scoped; never return global totals.
- CSV/Excel exports, file downloads, thumbnails, attachments, and background reports: enforce the same owner/tenant constraints.
- Batch APIs accepting multiple IDs: verify **every ID** before returning, updating, or deleting; never check one ID and run an unscoped query over the rest.
- Client-supplied filters/sorts may only reference allow-listed fields, never turning into arbitrary query expressions that escape scope.
- Caches must include scope in their keys or check authorization before serving cached data; caching solely by `itemId` causes cross-user leaks.

Example scoped pagination repository method (add to the example's `WorkItemRepository` and import `Page`, `Pageable`):

```java
Page<WorkItem> findByOwnerUsername(
    String ownerUsername, Pageable pageable
);
```

Spring Data applies the owner predicate to both the data query and the count query. For complex JPQL/native queries with separate count queries, ensure **every query** carries the same `owner`/`tenant` predicate. Test with at least two users having multiple records and verify `totalElements` excludes other users' data.

### 7.1. Avoiding time-of-check/time-of-use risks

For instance, checking `owner` on an entity and later running an unscoped write in another transaction can be exposed to concurrent ownership/permission changes. When stricter guarantees are needed, use a predicated update:

```sql
UPDATE work_items
SET title = :new_title
WHERE id = :item_id
  AND owner_username = :current_username;
```

Then inspect the affected row count: `0` means the item was not in the permitted scope, returning 404 per policy. With JPA `@Modifying`, ensure a write transaction and watch persistence context/cache state. This is an advanced pattern for concurrent mutations rather than a baseline requirement for every demo app.

## 8. Testing mistakes that distort security assessments

### 8.1. A suite using only `@WithMockUser(roles="ADMIN")`

Such tests only verify a mock principal with `ROLE_ADMIN` can enter an endpoint. They do **not** check passwords, database-backed roles, or ownership. Add real-credential tests and tests with same-role users owning different resources.

### 8.2. `@AutoConfigureMockMvc(addFilters=false)`

Disabling filters lets controllers run without Spring Security, so a `200` test does not reflect production. Use this only when intentionally testing pure MVC logic; **never report it as having tested authorization**.

### 8.3. Asserting only 403 when PATCHing someone else's item

Without a CSRF token, a request can receive 403 **due to CSRF**, proving nothing about ownership checks. In ownership denial cases, send a **valid CSRF token** and expect 403/404 per policy; test missing/invalid CSRF tokens in separate cases.

### 8.4. Calling `findAll()` and filtering in Java

A request might return the right JSON in a tiny test while the query loaded everyone's data. Once pagination, counts, caches, or logging are added, leaks or wrong totals appear. Scope repositories directly in queries and test list, search, and summary endpoints.

### 8.5. Hardcoding test IDs

If a test assumes Alice's ID is `1` and Bob's is `2` and H2 does not reset identity sequences after cleanup, tests fail for reasons unrelated to security. Fetch IDs from fixtures/repositories like `idFor("bob")` in tests.

### 8.6. Using differently privileged users instead of same-role users

Alice as USER and Bob as ADMIN produce a 403 from roles; that does not prove data isolation. Use Alice and Bob both holding `ROLE_USER` to test object ownership.

### 8.7. Not inspecting the database after a blocked request

A controller might write first and throw afterward, returning a denied status while mutating data (depending on transaction/exception handling). For mutations, assert the record is unchanged and no unauthorized side effects occurred.

### 8.8. Test profile accidentally swaps the policy

`@ActiveProfiles("test")`, a mocked `AuthenticationManager`, or a `permitAll()` test configuration can mask differences from production. Document clearly which chain and profile are under test, and maintain an integration test against the real app configuration.

### 8.9. Asserting only status, not payload

An API returning 200 with Alice's valid item plus Bob's item slips past status-only checks. Use `jsonPath("$", hasSize(1))` and assert expected fields; for large responses, also assert no out-of-scope IDs or owners appear.

### 8.10. Omitting sub-endpoints and alternative access paths

`GET /api/items/{id}` may be safe while `/api/items/{id}/attachment`, `/api/files/{fileId}`, exports, or WebSocket subscriptions still leak data. Test all real paths to the same resource, covering both GETs and write operations.

## 9. Additional test pattern for method security

If permissions are enforced in services with `@PreAuthorize`, load real method-security beans. **Sketch** example, not a standalone runnable Java class:

```java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig {}

@Service
class ApprovalService {
    @PreAuthorize("hasAuthority('approve:item')")
    public String approve() {
        return "approved";
    }
}
```

Import the matching annotations and use the Spring-managed `ApprovalService` bean (do not call `new ApprovalService()`). Verify:

- `@WithMockUser(authorities="approve:item")`: method is allowed.
- `@WithMockUser(authorities="read:item")`: denied.
- Missing principal: denied per configuration.

When a service also carries ownership predicates, you must still test another user's ID. `@PreAuthorize("hasRole('USER')")` cannot replace ownership checks. Self-invocation or calling mocked services bypasses the AOP proxy, preventing the test from verifying `@PreAuthorize` actually runs. To confirm HTTP statuses, add integration tests hitting endpoints backed by the real service bean.

## 10. Diagnostic workflow when results are unexpected

When a case fails, check in order:

1. **Is the test setup right?** `spring-security-test` on test classpath; `@SpringBootTest`/`@WebMvcTest` loads the right `SecurityConfig`; MockMvc includes the filter chain.
2. **Which identity is active?** Valid HTTP Basic, mock `@WithMockUser`, Bearer token, session? Did authentication really succeed?
3. **Which HTTP method/path rule matched?** Placing `/api/**` before `/api/admin/**` can shadow specific rules; check ordering and `securityMatcher` when multiple chains exist.
4. **Did CSRF block before ownership ran?** For POST/PATCH/DELETE in this lesson, send `.with(csrf())` before evaluating ownership.
5. **Does the service query include an owner predicate?** If a branch uses global `findById(id)`, cross-user tests should catch it.
6. **Is the principal derived from a trusted source?** Never accept client-supplied `ownerUsername` as authorization.
7. **Did a denied status still mutate data?** Re-query the DB; for events/queues, check audit/outbox tables.
8. **Did the payload leak?** Check lists, JSON fields, counts, logs, and exception messages.
9. **Does the fixture have at least two same-role users?** Derive IDs from fixtures; do not depend on test order.
10. **Does intentionally breaking a rule turn tests red?** Temporarily swap an owner-scoped query for a global query on a test branch to gauge suite sensitivity, then revert in development.

## 11. Self-assessment exercises

**A.** Two users share `ROLE_USER`. Tests only check that Alice can call `/api/items/{aliceId}` and get 200. Is that enough?  
**Answer:** No. You must test that Alice is blocked on `{bobId}`, Bob can still access `{bobId}`, and lists exclude Bob's items.

**B.** Alice sends PATCH for Bob's ID; the test gets 403 without sending a CSRF token. Does that prove the owner policy?  
**Answer:** No. The 403 may come from `CsrfFilter`. Send a valid token so the request reaches the ownership layer, expect the policy status, and verify the DB is unchanged.

**C.** `GET /api/items/{id}` returns 404 when Alice uses Bob's ID. Does that mean the ID does not exist anywhere in the system?  
**Answer:** No. It only means no record exists **within Alice's permitted scope**. This intentionally avoids revealing other users' resources exist.

**D.** Admin calls an endpoint for Bob's item and gets 404. Is that a bug?  
**Answer:** Not if the owner-scoped policy grants no admin bypass. Cross-owner support access must be an explicit, separately defined and tested privilege.

**E.** `@WithMockUser(username="alice",roles="USER")` passes, yet password `alice123` in the user store is already wrong. Why?  
**Answer:** The annotation mocks authentication without checking passwords. Use `httpBasic` or a real authentication mechanism to test providers.

**F.** A list API returns only Alice's item, yet `Page.totalElements=300` counts items across the entire system. Will a simple status/payload test catch this?  
**Answer:** No. You must assert counts, search, pagination, and all aggregates under the same scope condition.

**G.** A test deleting Bob's item as Alice receives 404. What additional assertion is needed?  
**Answer:** Check `repository.findById(bobId)` is still present and data is untouched; protecting against side effects is as important as the response.

**H.** An API allows `POST /api/items` with `ownerUsername=bob` in the body while the client is logged in as Alice. What is the risk?  
**Answer:** Assigning ownership from untrusted input lets callers create or manipulate data on behalf of others. Ownership must come from the principal or a verified delegation right; test that Alice cannot pick Bob as owner.

## 12. Checklist before signing off on security tests

- [ ] Both **allow and deny** tests exist for each important endpoint group.
- [ ] At least **two users with the same role** own different resources.
- [ ] Cases cover anonymous, wrong credentials, insufficient role, and sufficient role.
- [ ] Cases have user A reading/updating/deleting B's ID, not merely random invalid IDs.
- [ ] Owner/tenant comes from server-verified principals and permissions, never trusting client `userId`/owner fields.
- [ ] List/detail/search/count/page/export endpoints are all scoped by data permissions.
- [ ] POST/PATCH/DELETE test CSRF separately; ownership tests supply valid CSRF.
- [ ] Denied mutation tests verify the database remains unchanged.
- [ ] Creation tests verify owner is assigned from the server-side principal.
- [ ] HTTP 403/404 statuses follow a consistent policy without leaking sensitive details.
- [ ] The real `SecurityFilterChain` and provider are loaded; filters are not disabled.
- [ ] `@WithMockUser` is never used as proof that passwords/providers were tested.
- [ ] Sub-paths, batch endpoints, files, caches, and pagination are tested if supported.
- [ ] Tests actively fail when owner restrictions or role rules are removed.

## 13. Takeaways and references

**An adequate authorization test suite must prove three things at once:** (1) authorized users can work, (2) unauthenticated or under-privileged callers are blocked, and (3) authenticated users still cannot view or modify someone else's resources. The pair **right owner → allowed** and **wrong owner with same role → denied, no data mutated** provides direct proof of object-level protection.

Reference documentation:

- [Spring Security — Testing in Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [OWASP API Security Top 10 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
