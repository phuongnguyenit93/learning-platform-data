# Protecting Service Methods and Resources by Owner

## 1. Objectives and Problem Statement

In this capstone practical exercise, you build a Spring Boot application managing **private notes**. Logged-in users can read, list, and update **their own** notes; they cannot read or modify anyone else's notes even if they know the exact ID. The focus is coordinating **HTTP request protection**, **service-layer method security**, and **per-object ownership rules**.

By the end of the exercise, you will be able to:

1. Explain why `authenticated()` or `hasRole("USER")` is **not enough** to protect resources that have an owner.
2. Enable `@EnableMethodSecurity` and use `@PreAuthorize` and `@PostAuthorize` on a **Spring-managed service bean**, rather than putting checks only in the controller.
3. Separate identity authentication from per-ID ownership verification; obtain the current user from trusted server-side `Authentication`.
4. Prevent both **unauthorized reads** and **unauthorized writes**, leaving data unchanged when rejected.
5. Write `MockMvc` tests and direct service-invocation tests to defend against IDOR/BOLA (Insecure Direct Object Reference / Broken Object Level Authorization).
6. Recognize the limits of post-return checks, AOP proxies, SpEL parameters, CSRF, and concurrency issues when moving to a real database.

This is a **Spring Security Servlet/Spring MVC** exercise; Spring WebFlux uses a different reactive method security mechanism. The example provides a structurally runnable **Java 17 + Spring Boot 3.3.5 + Spring Security 6.x** project with in-memory users and mock data. Versions are pinned so the exercise is reproducible; when applying to an active project, select a supported Boot/Security line and consult the matching documentation.

## 2. Distinguishing Login, Roles, and Ownership

Suppose the database contains:

| ID | Owner | Content |
| --- | --- | --- |
| 1 | `alice` | Alice note one |
| 2 | `bob` | Bob private note |
| 3 | `alice` | Alice note three |

If the configuration only says:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/notes/**").authenticated()
    .anyRequest().denyAll());
~~~

then both Alice and Bob are **authenticated** and can both call `GET /api/notes/2`. If the controller fetches a record solely by ID and returns it directly, Alice reads Bob's data. This is an **object-level authorization vulnerability**, commonly known as IDOR/BOLA. Using longer IDs or UUIDs instead of numeric IDs does not replace checking access permissions on the object.

Distinguish the layers:

| Check level | Question | Approach in this exercise |
| --- | --- | --- |
| Authentication | Does the client have a valid identity? | HTTP Basic + `UserDetailsService` |
| Request authorization | Is the caller allowed into this API area? | `anyRequest().authenticated()` |
| Method authorization | Does the service method permit this operation? | `@PreAuthorize` / `@PostAuthorize` |
| Object ownership | Does the specific ID belong to the caller? | Compare `Note.owner` with `authentication.name` |
| Data isolation | Does a list or query return only permitted records? | `findByOwner(...)`, owner-scoped queries |

Having `ROLE_USER` does not grant ownership over every other `ROLE_USER`'s notes. Even `ROLE_ADMIN` must not bypass ownership rules unless product requirements explicitly grant an administrator exception.

**Desired contract for the exercise:**

| Request | Identity | Result |
| --- | --- | --- |
| `GET /api/health` | Anonymous | 200 |
| `GET /api/notes/1` | Anonymous | 401 |
| `GET /api/notes/1` | Alice | 200 |
| `GET /api/notes/2` | Alice | 403 |
| `GET /api/notes/2` | Bob | 200 |
| `GET /api/notes/2` | Admin who is not the owner | 403 |
| `GET /api/notes/999` | Alice | 404 |
| `GET /api/notes` | Alice | Sees only IDs 1 and 3 |
| `PUT /api/notes/1` | Alice + valid CSRF token | 200, content updated |
| `PUT /api/notes/2` | Alice + valid CSRF token | 403, Bob's content **unchanged** |
| `PUT /api/notes/1` | Alice, missing CSRF token | 403, **unchanged** |
| `PUT /api/notes/999` | Alice + valid CSRF token | 403 per the example's pre-check policy |

Whether a missing resource returns 403 or 404 is a **design choice**: `@PostAuthorize` on the read path allows missing-resource handling (404) before verifying ownership; `@PreAuthorize` on the update path returns 403 when the policy check does not find the record. Many production applications intentionally return 404 uniformly for both "does not exist" and "not authorized" to avoid leaking object existence. Never treat one specific status as universally mandatory across all systems.

## 3. From a Vulnerable Pattern to Service-Layer Protection

The **insecure** example below is strictly for analysis—**do not use it in the final version**:

~~~java
// Illustrative bug: fetches by ID and returns without checking owner
@GetMapping("/api/notes/{id}")
public Note insecureRead(@PathVariable long id) {
    return noteRepository.findById(id).orElseThrow();
}
~~~

Even with `authenticated()` on the route, Alice can guess or swap `{id}` to `2` and retrieve Bob's note. Adding an `if` statement in the controller might stop that single endpoint, yet it is easily forgotten when adding another REST endpoint, scheduled job, GraphQL resolver, event listener, or another service caller.

**Exercise design:**

~~~text
HTTP request
   |
   v
SecurityFilterChain
   |-- authentication: Basic credentials -> Authentication
   |-- request rule: public health / authenticated notes
   |
   v
NoteController
   |
   v
NoteService (Spring bean via AOP proxy)
   |-- read(id): @PostAuthorize checks owner on the returned object
   |-- update(id,...): @PreAuthorize checks owner BEFORE mutating
   |-- listForOwner(owner): @PreAuthorize prevents forging owner
   |
   v
NoteRepository (in-memory)
   |
   v
Permitted data or AccessDeniedException
~~~

In real projects, checks must be enforced on **every path that accesses or modifies objects**. Protecting the service is a valuable defense because callers do not always enter through the same controller. Remember too: only **method calls routed through the Spring AOP proxy** are intercepted properly by method security annotations.

## 4. Initializing the Project to Run the Complete Example

Requires JDK 17 and the Gradle Wrapper from Spring Initializr or an existing Gradle project. Select Java, Gradle Groovy, Spring MVC, and Spring Security. The example files below use package `example.ownership`.

Structure:

~~~text
ownership-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...                 # Gradle Wrapper provided by generator
├── src/main/java/example/ownership/
│   ├── OwnershipApplication.java
│   ├── SecurityConfig.java
│   ├── Note.java
│   ├── NoteRepository.java
│   ├── NoteAccess.java
│   ├── NoteService.java
│   ├── NoteController.java
│   └── HealthController.java
└── src/test/java/example/ownership/
    └── OwnershipSecurityTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'ownership-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages Spring dependency versions via its BOM. Never pin an incompatible Spring Security major version on top of Boot. `spring-security-test` enables simulating HTTP Basic, CSRF tokens, and `@WithMockUser`. The example omits JPA/databases so security decisions stand out clearly without mixing in persistence logic.

### 4.1. Application class

File `src/main/java/example/ownership/OwnershipApplication.java`:

~~~java
package example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
~~~

Place the remaining classes in package `example.ownership` or subpackages so Spring Boot discovers beans via component scanning.

### 4.2. Note model with read-only owner field

File `src/main/java/example/ownership/Note.java`:

~~~java
package example.ownership;

public final class Note {
    private final long id;
    private final String owner;
    private final String content;

    public Note(long id, String owner, String content) {
        this.id = id;
        this.owner = owner;
        this.content = content;
    }

    public long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getContent() {
        return content;
    }
}
~~~

`owner` is never taken from the request body when updating a note. Having `getOwner()` lets SpEL in `@PostAuthorize("returnObject.owner ...")` access the JavaBean property cleanly. The object is immutable: updating content creates a new `Note` while preserving the original owner.

### 4.3. Demo data repository

File `src/main/java/example/ownership/NoteRepository.java`:

~~~java
package example.ownership;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {
    private final Map<Long, Note> notes = new ConcurrentHashMap<>();

    public NoteRepository() {
        resetDemoData();
    }

    public void resetDemoData() {
        notes.clear();
        notes.put(1L, new Note(1L, "alice", "Alice note one"));
        notes.put(2L, new Note(2L, "bob", "Bob private note"));
        notes.put(3L, new Note(3L, "alice", "Alice note three"));
    }

    public Optional<Note> findById(long id) {
        return Optional.ofNullable(notes.get(id));
    }

    public List<Note> findByOwner(String owner) {
        return notes.values().stream()
                .filter(note -> note.getOwner().equals(owner))
                .sorted(Comparator.comparingLong(Note::getId))
                .toList();
    }

    public void save(Note note) {
        notes.put(note.getId(), note);
    }
}
~~~

This store lives only in RAM and resets on startup. It **does not handle transactions, multiple processes, ownership transfers, or data concurrency as in production**. The end of the exercise covers mandatory conditions when moving to SQL.

## 5. Enabling Both HTTP Security and Method Security

File `src/main/java/example/ownership/SecurityConfig.java`:

~~~java
package example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-password"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Two distinct protection layers:**

- `SecurityFilterChain` checks incoming requests. `GET /api/health` is public; all other URLs require authentication. `httpBasic` makes testing with curl straightforward; `formLogin` is disabled to prevent redirects to a login form in an API.
- `@EnableMethodSecurity` activates the interceptor for `@PreAuthorize` and `@PostAuthorize` on Spring beans. **Merely adding the Security starter does not automatically enable method security**.
- The three demo accounts share a dummy password encoded with BCrypt. Use only on localhost for learning—never carry hardcoded passwords or sensitive data into production.
- There is no `csrf(AbstractHttpConfigurer::disable)`: default CSRF protection stays enabled, so `PUT` tests must attach a valid token. HTTP Basic does not automatically imply CSRF is disabled.
- `ADMIN` in this example has not been granted an ownership bypass. Roles are simply attributes in `Authentication`; ownership logic must evaluate permissions intentionally.

### 5.1. Dedicated ownership-check bean

File `src/main/java/example/ownership/NoteAccess.java`:

~~~java
package example.ownership;

import org.springframework.stereotype.Component;

@Component("noteAccess")
public class NoteAccess {
    private final NoteRepository repository;

    public NoteAccess(NoteRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(long id, String username) {
        if (username == null || username.isBlank()) {
            return false;
        }

        return repository.findById(id)
                .map(note -> note.getOwner().equals(username))
                .orElse(false);
    }
}
~~~

This bean takes `id` and username and returns a boolean. In SpEL annotations, `@noteAccess` resolves to this exact bean, while `authentication.name` retrieves the **authenticated** identity from the server-side `SecurityContext`.

Returning `false` when the ID does not exist means a `PUT` targeting an unknown ID is denied **before** executing the method. In real products, explicitly decide when to return 403 vs. 404 to avoid leaking resource existence via response differences.

Never write `isOwner(id, usernameFromRequestBody)` because a client could pass `bob` as the username. The current user must come from authentication, not a client-supplied owner field.

## 6. Locking Down Reads, Writes, and Listings at the Service Layer

File `src/main/java/example/ownership/NoteService.java`:

~~~java
package example.ownership;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class NoteService {
    private final NoteRepository repository;

    public NoteService(NoteRepository repository) {
        this.repository = repository;
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Note read(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Note not found"));
    }

    @PreAuthorize("@noteAccess.isOwner(#id, authentication.name)")
    public Note update(@P("id") long id, String content) {
        if (content == null || content.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Content must not be blank");
        }

        Note oldNote = repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Note not found"));

        Note updated = new Note(id, oldNote.getOwner(), content);
        repository.save(updated);
        return updated;
    }

    @PreAuthorize("#owner == authentication.name")
    public List<Note> listForOwner(@P("owner") String owner) {
        return repository.findByOwner(owner);
    }
}
~~~

**Analyzing the three annotations precisely:**

**`@PostAuthorize` on `read`:** the method fetches `Note` from the store, then the interceptor evaluates `returnObject.owner == authentication.name` **before returning the result to the caller**. If Alice requests ID 2, the fetched note belongs to Bob, so the expression evaluates to false and Spring Security throws `AccessDeniedException`; the HTTP request gets **403**. If the ID does not exist, the method throws `ResponseStatusException(404)` before a return object exists, so HTTP sees **404**.

`@PostAuthorize` makes sense for **pure reads**, though real services will have already queried the data before denying; avoid logging or caching unauthorized data before the check runs. **Never use `@PostAuthorize` to protect a database write method**: the mutation would already have happened before being rejected.

**`@PreAuthorize` on `update`:** before running any statement inside `update`, the interceptor calls `noteAccess.isOwner(id, authentication.name)`. If false, the method **never executes**, so Bob's note stays untouched. This is essential for state-changing operations. While demo data cannot change ownership between the check and write, production requires transactional/atomic updates (see section 11).

**`@PreAuthorize` on `listForOwner`:** even though the controller passes only the current username, the service itself rejects `listForOwner("bob")` if the caller is Alice. This protects against another service caller passing an arbitrary owner. The repository also filters at the data source via `findByOwner` rather than loading everything and filtering in the controller.

**About SpEL parameter names:** `#id` and `#owner` rely on names declared explicitly with `@P("id")` / `@P("owner")`. This avoids depending on whether the compiler retains parameter names. If you omit `@P` and still reference `#id`, you must compile with `-parameters` per the method security documentation. `#p0` also works for the first parameter, though it is usually less readable.

## 7. Controller Takes the ID; Service Enforces Permissions

File `src/main/java/example/ownership/NoteController.java`:

~~~java
package example.ownership;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/notes")
public class NoteController {
    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @GetMapping
    public List<Note> mine(Authentication authentication) {
        return service.listForOwner(authentication.getName());
    }

    @GetMapping("/{id}")
    public Note get(@PathVariable long id) {
        return service.read(id);
    }

    @PutMapping("/{id}")
    public Note update(
            @PathVariable long id,
            @RequestBody UpdateNoteRequest request) {
        return service.update(id, request.content());
    }

    public record UpdateNoteRequest(String content) {
    }
}
~~~

The `PUT` request payload **contains only `content`**. The ID comes from the URL but is not trusted as proof of ownership; `owner` does not appear in the body. For listing, the controller pulls `Authentication` from Spring Security instead of letting clients pass `?owner=bob`.

File `src/main/java/example/ownership/HealthController.java`:

~~~java
package example.ownership;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    @GetMapping("/api/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
~~~

The `/api/health` controller is public, never touches `NoteService`, and exposes no user data.

**Important:** the controller is a Spring-managed bean injected with a Spring-managed `NoteService`. Calls to `service.read/update/listForOwner` pass through the method security proxy. If you manually instantiate `new NoteService(...)` or invoke an annotated method via `this.update(...)` inside `NoteService` itself, the proxy interceptor can be bypassed. Never assume annotations "magically run" on arbitrary Java method calls.

## 8. Running the Application and Verifying via HTTP

At the project root containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/notes/1
curl -i --basic -u 'alice:demo-password' http://localhost:8080/api/notes/1
curl -i --basic -u 'alice:demo-password' http://localhost:8080/api/notes/2
curl -i --basic -u 'bob:demo-password' http://localhost:8080/api/notes/2
curl -i --basic -u 'alice:demo-password' http://localhost:8080/api/notes
curl -i --basic -u 'admin:demo-password' http://localhost:8080/api/notes/2
~~~

In PowerShell, use `curl.exe` instead of the `curl` alias in older Windows PowerShell; each command can be written on a single line.

### 8.1. Key expected results

- `GET /api/health`: **200** and `{"status":"ok"}`.
- `GET /api/notes/1` without credentials: **401** (HTTP Basic requires authentication).
- Alice reads ID 1: **200** and JSON `{"id":1,"owner":"alice","content":"Alice note one"}`.
- Alice reads ID 2: **403**, **Bob's JSON must not be returned**.
- Bob reads ID 2: **200** and JSON `{"id":2,"owner":"bob","content":"Bob private note"}`.
- Alice lists `/api/notes`: **200**, containing only notes ID 1 and 3 in ascending ID order.
- Admin reads ID 2: **403** because the admin role does not automatically confer ownership.
- Alice reads ID 999: **404** because `read` has no object to return.

These are **expected results**, not recorded stdout/logs from your environment. Additional HTTP headers, error formats, and timing depend on configuration.

### 8.2. Why isn't PUT demonstrated simply with curl?

CSRF is enabled by default. A `PUT` with Basic credentials but **without a valid CSRF token** returns **403** before ownership is even checked. That is intentional behavior, not proof that Alice doesn't own the note. To test safely, section 9 uses `MockMvc.with(csrf())` to supply a token matching the test context.

For browser UIs or cookie/session APIs, design proper CSRF token issuance and submission. Never disable CSRF just so a `curl -X PUT` demo can write data. For cookie-free APIs using only Authorization headers/tokens, evaluate CSRF policy against the real threat model.

## 9. Automated Tests: Horizontal Access, Unauthorized Writes, and Direct Service Calls

File `src/test/java/example/ownership/OwnershipSecurityTests.java`:

~~~java
package example.ownership;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipSecurityTests {
    @Autowired
    MockMvc mvc;

    @Autowired
    NoteRepository repository;

    @Autowired
    NoteService service;

    @BeforeEach
    void resetNotes() {
        repository.resetDemoData();
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void anonymousCannotReadPrivateNote() throws Exception {
        mvc.perform(get("/api/notes/1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerOwnNote() throws Exception {
        mvc.perform(get("/api/notes/1")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceCannotReadBobsNote() throws Exception {
        mvc.perform(get("/api/notes/2")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadHisNote() throws Exception {
        mvc.perform(get("/api/notes/2")
                        .with(httpBasic("bob", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("Bob private note"));
    }

    @Test
    void adminDoesNotBypassOwnershipAutomatically() throws Exception {
        mvc.perform(get("/api/notes/2")
                        .with(httpBasic("admin", "demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingNoteReturnsNotFoundOnRead() throws Exception {
        mvc.perform(get("/api/notes/999")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void listContainsOnlyCurrentOwnersNotes() throws Exception {
        mvc.perform(get("/api/notes")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[1].id").value(3))
                .andExpect(jsonPath("$[0].owner").value("alice"))
                .andExpect(jsonPath("$[1].owner").value("alice"));
    }

    @Test
    void wrongPasswordCannotReadPrivateNote() throws Exception {
        mvc.perform(get("/api/notes/1")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanUpdateWithValidCsrf() throws Exception {
        mvc.perform(put("/api/notes/1")
                        .with(httpBasic("alice", "demo-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"Alice updated\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("Alice updated"));

        assertEquals("Alice updated",
                repository.findById(1L).orElseThrow().getContent());
    }

    @Test
    void aliceCannotUpdateBobsNoteAndNoDataChanges() throws Exception {
        mvc.perform(put("/api/notes/2")
                        .with(httpBasic("alice", "demo-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"tampered\"}"))
                .andExpect(status().isForbidden());

        assertEquals("Bob private note",
                repository.findById(2L).orElseThrow().getContent());
    }

    @Test
    void missingCsrfBlocksUpdateEvenForOwner() throws Exception {
        mvc.perform(put("/api/notes/1")
                        .with(httpBasic("alice", "demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"no csrf\"}"))
                .andExpect(status().isForbidden());

        assertEquals("Alice note one",
                repository.findById(1L).orElseThrow().getContent());
    }

    @Test
    void updateMissingIdIsDeniedByPreCheck() throws Exception {
        mvc.perform(put("/api/notes/999")
                        .with(httpBasic("alice", "demo-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"new\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void serviceCallerCannotForgeOwnerArgument() {
        assertThrows(AccessDeniedException.class,
                () -> service.listForOwner("bob"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void serviceCallerCannotReadOtherOwnersNote() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(2L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void serviceCallerCannotModifyOtherOwnersNote() {
        assertThrows(AccessDeniedException.class,
                () -> service.update(2L, "tampered"));

        assertEquals("Bob private note",
                repository.findById(2L).orElseThrow().getContent());
    }
}
~~~

Run all tests for this exercise:

~~~bash
./gradlew test --tests "example.ownership.OwnershipSecurityTests"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.ownership.OwnershipSecurityTests"
~~~

**Expected outcome:** **16 tests PASS**, Gradle finishes with `BUILD SUCCESSFUL`. If any test fails, verify dependency versions and each configuration step before changing expected statuses. The test count, class names, paths, and annotations in the exercise are fixed facts; simulated logs must never be presented as real execution evidence.

**Why this test suite matters:**

- Tests using `httpBasic` run through the real authentication filter rather than just supplying a mock principal. They verify Alice/Bob/Admin and 200/401/403/404 statuses.
- Update tests must include `csrf()`; without it, a 403 could come from CSRF alone and **fail to prove** the owner check ran. Therefore, the horizontal-access test intentionally **attaches a valid token**.
- After receiving 403 on an update attempt, the test inspects the repository directly to prove Bob's content stayed intact. **A 403 status alone does not prove there were no side effects**.
- `@WithMockUser` tests invoke the `NoteService` bean directly from the Spring context. They prove denial still triggers **when bypassing the controller and HTTP filters**—the core benefit of method security.
- `@WithMockUser` builds a mock `Authentication` to test method authorization, not password verification. The two test groups verify distinct concerns and complement each other.

## 10. Reading the Execution Chain and Distinguishing Pre/Post Authorization

### 10.1. Alice reads Bob's note

~~~text
GET /api/notes/2 + Basic alice
       |
       v
HTTP Basic authenticates alice
       |
       v
anyRequest().authenticated(): PASS
       |
       v
NoteController.get(2) -> service.read(2) via Spring proxy
       |
       v
NoteRepository returns Note(id=2, owner=bob)
       |
       v
@PostAuthorize: "bob" == "alice" ? FALSE
       |
       v
AccessDeniedException -> HTTP 403
(Bob's note JSON is not returned)
~~~

Here, access is denied **after reading the record inside the service**, yet **before returning the object out of the proxy**. That is why the example uses `@PostAuthorize` only for side-effect-free read operations.

### 10.2. Alice updates Bob's note

~~~text
PUT /api/notes/2 + Basic alice + valid CSRF
       |
       v
HTTP Basic authenticates alice; CSRF: PASS
       |
       v
HTTP request rule: authenticated -> PASS
       |
       v
NoteController.update(2,...)
       |
       v
@PreAuthorize calls noteAccess.isOwner(2,"alice")
       |
       v
actual owner = "bob" -> FALSE
       |
       v
AccessDeniedException -> HTTP 403
NoteService.update DOES NOT RUN
Repository data remains unchanged
~~~

**Check ordering is critical:** a policy evaluated **after a write** is too late to protect data integrity. `@PreAuthorize` intercepts before the method runs; in production, combine this with transactional controls/conditional `UPDATE` statements to prevent races.

### 10.3. Cases where you shouldn't draw mechanical rules

`@PreAuthorize` acts on **method invocation**; `@PostAuthorize` acts on the **return value**. Not every read operation should use Post: if you can query scoped to the current owner straight from the database, that is usually more efficient and leaks less. Not every resource with the "same role" can be shared: owner, tenant, and shared permissions usually need dedicated checks.

`@PreFilter` / `@PostFilter` can also filter input/output collections, yet **filtering a large collection after loading the entire database table** is expensive and breaks counts/pagination. Prefer filtering directly in the query whenever data grows.

## 11. Moving from the Demo Repository to a Real Database

### 11.1. Owner-scoped queries

For larger systems, instead of always calling `findById(id)` and checking afterward, prefer queries scoped by the trusted identity:

~~~sql
SELECT id, owner_id, content
FROM notes
WHERE id = :id
  AND owner_id = :current_user_id;
~~~

Use `current_user_id` derived from the server-side authenticated identity, **never from JSON bodies or query strings**. For list APIs:

~~~sql
SELECT id, owner_id, content
FROM notes
WHERE owner_id = :current_user_id
ORDER BY id;
~~~

If you want to hide whether another user's note exists, scoping queries by owner and returning 404 for both "missing" and "not owned" is a solid policy. Apply it consistently across GET/UPDATE/DELETE, metadata, file downloads, and auxiliary APIs.

### 11.2. Check-then-write must prevent race conditions

If a service executes:

~~~text
1. SELECT note.owner = alice  -> PASS
2. Another transaction changes owner to bob
3. UPDATE notes SET content=... WHERE id=1
~~~

then a valid check at step 1 no longer guarantees correctness at step 3. Use transactions with proper isolation/locking, or conditional writes enforcing **both ID and owner in the same SQL statement**:

~~~sql
UPDATE notes
SET content = :content
WHERE id = :id
  AND owner_id = :current_user_id;
~~~

If affected rows = 0, handle it per your app's unauthorized/not-found policy; never assume the write succeeded. With multi-tenant data, include `tenant_id` and related predicates in queries and constraints. With delegated/shared permissions, policies must verify actual grant records rather than comparing owners alone.

### 11.3. Owners must have a stable identity

In this exercise, `Note.owner` is `alice` or `bob` compared against `authentication.name`. Production systems should prefer an **immutable user ID** (such as an authenticated subject mapped to an internal user ID) rather than a changeable display name or email. IdPs/OIDC tokens may carry subject, tenant, and scope claims; never treat arbitrary client-supplied claims as ownership. In multi-tenant apps, enforce tenant boundaries too.

### 11.4. Principles for ADMIN roles and sharing policies

If the product requires admins to read certain notes, state the policy explicitly:

~~~java
// Conceptual snippet; DO NOT replace rules blindly without business review
@PreAuthorize("hasRole('ADMIN') || @noteAccess.isOwner(#id, authentication.name)")
public Note readForAuthorizedUser(@P("id") long id) {
    // ...
}
~~~

The snippet above is **not standalone** and needs the matching repository/service and imports; with the current example's pure-owner `@PostAuthorize`, admins are still blocked. Never add a role bypass just to make a red test pass. Specify exactly what admins may do, auditing requirements, and sensitive-data boundaries.

## 12. Common Mistakes

| Mistake | Why it is dangerous | How to check/fix |
| --- | --- | --- |
| Only `authenticated()` on routes | Users can enumerate/swap other users' IDs | Test Alice/Bob on the same endpoint across multiple IDs |
| Only `hasRole('USER')` | Many users share the same role but own different objects | Check owner/tenant/permission at the object level |
| Trusting `owner` from request body | Clients can swap it to another user | Derive identity from `Authentication` / identity service |
| Forgetting `@EnableMethodSecurity` | Method security annotations are never enforced | Write a direct service-call test and verify it throws |
| Calling `new Service(...)` or `this.method()` | Can bypass the Spring AOP proxy | Inject the Spring service bean; route calls through the proxy |
| Annotating `private` or `final` methods for proxying | Interceptors cannot guarantee interception like proxied public methods | Put policies on public methods of Spring-managed beans |
| `@PostAuthorize` on write methods | Data is mutated before denial happens | Use `@PreAuthorize` and safe conditional `UPDATE`s |
| Using `#id` when compiler drops parameter names | SpEL may fail to resolve variables or evaluate wrongly | Use `@P("id")` or compile with `-parameters` |
| Write tests without CSRF | 403 from CSRF masks broken owner checks | Add `with(csrf())`, then test both deny and allow ownership cases |
| Asserting only HTTP 403 | Database may still have been modified before rejection | Assert stored state remains unchanged |
| Protecting GET while forgetting PUT/DELETE/export | IDOR remains open on other endpoints | Build an action matrix for every resource type |
| Using mutable username as owner | Renaming breaks or misassigns ownership | Map to an immutable internal user ID |
| Unsynchronized SELECT owner then UPDATE | Race condition writes to the wrong owner's record | Atomic `UPDATE` with owner predicate / locking |
| Letting Admin bypass all ownership automatically | Unintended privilege expansion | Document and explicitly test every exception |
| Putting authorization only in controllers | Other service callers can bypass it | Enforce method security in services and data-layer guards |

**Note on exceptions/statuses:** Under this exercise's HTTP Basic setup, anonymous gets 401 and authenticated callers rejected by method security get 403. With form login you may see 302, and custom REST exception handlers can alter bodies/statuses. Match tests to your actual configuration; never infer a policy is right from a single status code alone.

## 13. Extension Exercises and Acceptance Criteria

**Exercise A — Prove the IDOR bug:** on a separate experimental branch, temporarily remove `@PostAuthorize` from `read`, run `aliceCannotReadBobsNote`, and observe it fail. Restore the annotation and verify the test passes. Explain why `authenticated()` was still active yet Bob's data leaked.

**Exercise B — Prevent cross-user writes:** temporarily remove `@PreAuthorize` from `update` and run `aliceCannotUpdateBobsNoteAndNoDataChanges`. After restoring it, verify both the 403 response and that Bob's content did not change. Why is checking `@PostAuthorize` after `save` insufficient?

**Exercise C — Protect listings:** add a temporary endpoint filtering by a client-supplied owner (only in a test branch) while keeping `listForOwner`'s service check. Alice calling with `owner=bob` must be rejected. Then remove the risky endpoint and stick to `Authentication` as in the final code.

**Exercise D — Sharing policy:** extend the model with `sharedWithUserIds`, implement `isOwnerOrShared`, and test all 3 actors: owner, shared user, and unrelated user. Do not grant write access if sharing is read-only.

**Exercise E — Real database:** migrate the repository to JPA/SQL; write a `WHERE id=? AND owner_id=?` query and conditional transactional update, testing two concurrent users. Only when both permission checks and writes preserve the invariant is the race resolved.

**Completion checklist:**

- [ ] `@EnableMethodSecurity` is enabled and the service bean is called through its proxy.
- [ ] Private note URLs require authentication; health may remain public.
- [ ] Alice/Bob can read their own notes and are blocked when switching IDs to another user's note.
- [ ] Listings return only notes the caller is permitted to read.
- [ ] Update checks execute **before** writes, with proof that data stays unchanged on 403.
- [ ] PUT tests supply a valid CSRF token so CSRF 403s aren't confused with ownership 403s.
- [ ] Direct service-call tests still block callers passing another owner.
- [ ] Consistent policies exist for missing objects, admins, tenants, and any other APIs taking object IDs.
- [ ] With a real database, owner/user IDs are stable and updates use conditional guards against races.

You meet the requirements when you can explain **who is calling**, **who owns the resource**, **whether evaluation runs before or after the method**, and **why the tests prove there is no horizontal access or unauthorized mutation**.

## 14. Reference Documentation

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): enabling `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, SpEL, method parameters, and AOP.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP request authorization and rule ordering.
- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` and security context in tests.
- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `csrf()` and invalid tokens.
- [Spring Security — Testing Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/test/index.html): integrating Spring Test with Security filters.
- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object access vulnerabilities via IDs and owner scoping.

Online docs include a version selector; for this pinned Spring Boot 3.3.5 project, consult the Spring Security branch managed by Boot's BOM before applying API details, matchers, or defaults to production.
