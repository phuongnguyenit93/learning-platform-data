# Creating Two Permission Groups and Verifying the Access Matrix

## 1. Problem Statement and Target Outcomes

A document management application needs to protect document reading and creation operations. This practical exercise creates **two permission groups** in Spring Security, assigns two users to their respective groups, designs an **access matrix** before writing code, and then uses automated tests to prove each request is allowed or denied according to policy.

The two groups are:

- **READER:** can read documents but cannot create documents.
- **EDITOR:** can both read and create documents.

The exercise deliverables include a runnable Spring Boot application, a `SecurityFilterChain` configuration, an HTTP endpoint permission matrix, `MockMvc` tests, and clear explanations of `200`/`201`/`401`/`403`. Confidence in the exercise comes from **both positive and negative tests**: a single passing test does not prove authorization is configured correctly.

The example uses **Spring MVC / Servlet** to focus on authorization fundamentals. If a project uses Spring WebFlux, it must use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `WebTestClient` accordingly; do not copy Servlet configuration into a reactive application.

## 2. Two-Permission-Group Model

A permission group is an application-defined concept for bundling multiple specific permissions. Spring Security enforces policies based on `GrantedAuthority` instances attached to an authenticated `Authentication`.

| Group | Granted authorities | Demo user | Capabilities |
| --- | --- | --- | --- |
| `READER` | `document:read` | `alice` | View documents |
| `EDITOR` | `document:read` and `document:write` | `bob` | View and create documents |

Unauthenticated guests belong to neither group. In this example, the application maps group names to an array of authorities **when building accounts**; it does not check the strings `READER`/`EDITOR` directly at each endpoint.

**Three points to distinguish:**

1. **Authentication** answers "who is calling?"; **authorization** answers "what actions is that person allowed to perform?". Logging in validly does not automatically grant write permission.
2. `hasAuthority("document:write")` checks the exact `document:write` permission. `hasRole("EDITOR")` by default checks the `ROLE_EDITOR` authority; these two are not equivalent unless you have defined a role mapping.
3. `EDITOR` can read because **we explicitly grant `document:read`** to this group. Spring Security does not automatically inherit permissions based on group name hierarchy.

In real systems, group names and memberships can live in a database, LDAP, or an identity provider. The group-to-authorities mapping must come from an authenticated, trusted source—never trust a `group` value sent by the client to grant permissions.

## 3. Designing the Access Matrix Before Writing Code

Consider three API routes:

- `GET /public/ping`: application readiness check, public.
- `GET /api/documents/{id}`: read a document, requires `document:read`.
- `POST /api/documents?title=Note`: create a document, requires `document:write`.

Expected matrix when using HTTP Basic with **default CSRF protection** enabled:

| Request | Anonymous | `alice` (READER) | `bob` (EDITOR) |
| --- | --- | --- | --- |
| `GET /public/ping` | `200` | `200` | `200` |
| `GET /api/documents/42` | `401` | `200` | `200` |
| `POST /api/documents?title=Note` **with valid CSRF token** | `401` | `403` | `201` |
| `POST /api/documents?title=Note` **without CSRF token** | `403` | `403` | `403` |
| `GET /api/unknown` | `403` per `denyAll` | `403` | `403` |

These HTTP codes reflect **this exact exercise configuration**, not a universal rule for all application types. With form login, unauthenticated guests may receive a redirect to the login page instead of `401`. `403` has multiple causes: missing authority, missing CSRF token, or a `denyAll` rule; therefore, when testing a permission, keep all other conditions fixed.

Baseline rule of the exercise: **expose only endpoints that must be public, grant exact least-privilege authorities, and deny all undefined endpoints**.

## 4. Initializing the Project

Prepare Java 17+, Spring Boot 3.5.x (Spring Security 6.x line), Spring MVC, and Gradle. You can generate the skeleton via Spring Initializr, selecting **Spring Web**, **Spring Security**, and test dependencies. In the generated Spring Boot project's `build.gradle`, ensure you have:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The snippet above is only the `dependencies` section, not the entire build file; plugins and the Spring Boot version are managed by the project skeleton. If you use a different Boot line, verify the DSL and starters against the documentation for that exact version.

Use package `com.example.accessmatrix`. The main application goes in `src/main/java/com/example/accessmatrix/AccessMatrixApplication.java`; tests go in `src/test/java/com/example/accessmatrix/AccessMatrixApplicationTests.java`.

## 5. Application Code: Assigning Groups and Configuring Permissions

File `src/main/java/com/example/accessmatrix/AccessMatrixApplication.java`:

~~~java
package com.example.accessmatrix;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccessMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccessMatrixApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    // Two application permission groups: READER and EDITOR.
    private static final Map<String, String[]> GROUP_PERMISSIONS = Map.of(
        "READER", new String[] { "document:read" },
        "EDITOR", new String[] { "document:read", "document:write" }
    );

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities(GROUP_PERMISSIONS.get("READER"))
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities(GROUP_PERMISSIONS.get("EDITOR"))
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/{id}")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAuthority("document:write")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Keep default CSRF protection to test this condition separately.
        return http.build();
    }
}

@RestController
class DocumentController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{id}")
    String read(@PathVariable("id") long id) {
        return "document:" + id;
    }

    @PostMapping("/api/documents")
    @ResponseStatus(HttpStatus.CREATED)
    String create(@RequestParam("title") String title) {
        return "created:" + title;
    }
}
~~~

All of the code above can live in **a single file** because `AccessMatrixApplication` is the only `public` class; the other two classes are package-private. At runtime, Spring Boot discovers `@Configuration` and `@RestController` in the same package and registers the beans/routes.

### Explaining Each Component

**Mapping the two groups.** `GROUP_PERMISSIONS` shows which authorities each group actually holds. `UserDetailsService` creates two accounts with authorities from the selected group; whenever HTTP Basic succeeds, Spring Security evaluates those authorities during authorization checks. The number of users can grow while reusing a single group definition.

**Demo account passwords.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder supporting algorithm ID prefixes; `encoder.encode(...)` hashes passwords before storing them in memory. However, the strings `alice-pass` and `bob-pass` still sit in the exercise source code. Never use hardcoded passwords, in-memory user stores, or this configuration for production deployments.

**Rule order and scope.** `authorizeHttpRequests` evaluates matcher/rule pairs in order, and the first matching rule decides. The GET document rule grants only read permission; the POST document rule grants only write permission; `anyRequest().denyAll()` rejects both other HTTP methods and undeclared URLs. Do not replace `denyAll` with `authenticated` when the requirement is to allow strictly the endpoints in the matrix.

**CSRF is independent of authorization.** `httpBasic` is the authentication mechanism used for testing. Spring Security keeps default CSRF protection for state-changing requests such as POST. The test suite below uses `csrf()` to supply a valid token, allowing us to distinguish `403` due to missing write permission from `403` due to a missing token. HTTP Basic credentials can be automatically re-sent by browsers; never argue "it's a Basic API so just disable CSRF."

**Demo business responses.** GET document 42 returns `document:42`, and POST `title=Note` returns `created:Note` with `201`. These are illustrative strings so outcomes can be asserted—there is no database, per-record ownership, or persistence yet.

## 6. Integration Testing the Full Matrix

File `src/test/java/com/example/accessmatrix/AccessMatrixApplicationTests.java`:

~~~java
package com.example.accessmatrix;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessMatrixApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/documents/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanReadButCannotCreate() throws Exception {
        mvc.perform(get("/api/documents/42")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:42"));

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanReadAndCreate() throws Exception {
        mvc.perform(get("/api/documents/42")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk());

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:Note"));
    }

    @Test
    void anonymousWithCsrfCannotCreate() throws Exception {
        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validEditorWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRouteIsDeniedEvenForEditor() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

The test suite has **seven test methods**, including tests that perform two requests to compare behavior for the same user. Key assertions:

- **`alice` and `bob` read successfully:** proves `document:read` is assigned to both groups.
- **`alice` POST with CSRF is `403`:** proves missing `document:write` is denied even when authenticated.
- **`bob` POST with CSRF is `201`:** proves authentication, write permission, and CSRF all hold for creation.
- **`bob` POST without CSRF is `403`:** proves write permission **does not disable** CSRF checks.
- **Anonymous GET is `401`:** with Basic, guests must authenticate before reading documents.
- **`bob` accessing an undeclared URL is `403`:** editor permission does not open the entire application.

`httpBasic("alice", ...)` and `httpBasic("bob", ...)` send real credentials through the chain, rather than mocking authorities with `@WithMockUser`. As a result, the tests verify **the group-to-authority mapping as well**. `MockMvc` has Security support enabled via `@AutoConfigureMockMvc`; `csrf()` from `spring-security-test` attaches a CSRF token on POST requests. Do not omit the token merely to compare authorities, because the POST case would fail for a different reason.

### Running and Observing

In the root directory of the created Gradle project:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Run `test` first to verify the matrix; run `bootRun` separately when you want to make real HTTP calls. On Windows PowerShell use `.\gradlew.bat test` and `.\gradlew.bat bootRun`. With the exact configuration and paths from this exercise, all seven test methods should pass; startup logs and run times vary by environment.

With the server running on default port 8080, try the GET requests:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/42
curl -i -u alice:alice-pass http://localhost:8080/api/documents/42
curl -i -u bob:bob-pass http://localhost:8080/api/documents/42
~~~

Expected statuses in order: `200`, `401`, `200`, `200`. On Windows PowerShell, you can use `curl.exe` to avoid the `curl` alias. For POST, running `curl -u ... -X POST` without a CSRF token returns `403`; the `MockMvc` tests supply the token to verify write permission properly.

## 7. Reading Results and Troubleshooting

Compare each case against **three checkpoints**: is there an identity, is the rule-required permission present, and (if POST) is there a valid CSRF token?

| Case | Authentication | Required authority | CSRF | Result |
| --- | --- | --- | --- | --- |
| `alice` reads | Yes | Has `document:read` | Not needed for GET | `200` |
| `bob` reads | Yes | Has `document:read` | Not needed for GET | `200` |
| `alice` creates | Yes | Missing `document:write` | Yes | `403` |
| `bob` creates | Yes | Has `document:write` | Yes | `201` |
| `bob` creates, missing CSRF | Yes | Has `document:write` | No | `403` |
| Anonymous reads | No | Unknown | Not needed for GET | `401` |

The single most informative test pair is **the same POST with the same valid CSRF token, changing only `alice` to `bob`**: `403` turning into `201` proves the `document:write` policy works. The second pair keeps `bob` and every parameter identical while removing CSRF: `201` turning into `403` confirms CSRF as the cause.

If results are wrong:

1. Verify the URI, HTTP method, and controller actually exist. A `404` can be a controller mapping bug, not proof that a rule allowed the request.
2. Check the user's actual authorities. `hasAuthority` performs an exact, case-sensitive string match; do not confuse it with `hasRole`.
3. If POST returns an unexpected `403`, check CSRF before changing permission groups.
4. If all credentialed requests still return `401`, check username/password, `UserDetailsService` configuration, and the password encoder.
5. If an undeclared URL is still reachable, check matcher ordering, overly broad rules, and any other `SecurityFilterChain` beans in the project.
6. Never fix a failing test by disabling all of Spring Security, removing `denyAll`, or adding an overly broad `permitAll`.

## 8. Variant Exercises for Deeper Understanding

**Experiment 1 — Remove read permission from EDITOR.** Temporarily change the `EDITOR` permission array to only `document:write`. Predict that `bob` can still create documents (POST with CSRF returns `201`) while reading returns `403`. After testing, restore both permissions. This experiment proves there is no implicit permission inheritance between groups.

**Experiment 2 — Add a delete operation.** Suppose you add a `DELETE /api/documents/{id}` controller endpoint. Because the default rule is `denyAll`, both groups are initially blocked. Define a new `document:delete` permission, decide which group should receive it, add the corresponding DELETE rule, and write two-way tests. Do not assume delete permission follows from create permission.

**Experiment 3 — Add another user to the same group.** Create `charlie` using `READER` authorities. Verify `charlie` behaves identically to `alice`; the goal is to see how permission groups apply one policy across multiple accounts without duplicating permissions on endpoints.

**Experiment 4 — Record-level permissions.** Replace mock content with real documents: `alice` may only read documents belonging to her own tenant. Checking `document:read` at HTTP is not enough; in the service layer, look up trusted data and verify owner/tenant, potentially using `@PreAuthorize` and `AuthorizationManager` depending on architecture. Add cross-tenant tests and tests for documents owned by others. Never trust a client-supplied `ownerId`.

For each experiment, write down your **HTTP status prediction before changing code**, make a single change, re-run the tests, and then restore the baseline policy. That builds policy reasoning rather than tweaking config until tests turn green.

## 9. Common Mistakes

- **Testing only allowed cases:** a READER accidentally granted write permission can slip through. Negative tests are mandatory.
- **Treating groups as built-in Spring Security roles:** in this exercise `READER`/`EDITOR` are application group labels. Spring Security only sees `document:read`/`document:write` assigned upon authentication.
- **Confusing `hasRole` and `hasAuthority`:** `hasRole("EDITOR")` defaults to requiring `ROLE_EDITOR`; it does not automatically understand `document:write`.
- **Disabling CSRF when POST is blocked:** handle CSRF and authority causes separately based on the real client type; do not drop a defense just to make a demo convenient.
- **Placing an overly broad matcher before specific rules:** rule order decides which rule is evaluated. Keep `anyRequest().denyAll()` last and open only the exact routes needed.
- **Checking only paths while ignoring business rules:** with real records, owner/tenant policies are needed in the service or data layer rather than stopping at a general read permission.
- **Trusting a username or group sent in the request by the client:** authorize against the authenticated principal/authorities from a trusted source.
- **Assuming `403` always means "missing permission":** CSRF and `denyAll` also produce `403`; use controlled tests to isolate the cause.

## 10. Completion Criteria and Reference Documentation

You have completed this exercise when you can explain the path **HTTP Basic → Authentication → GrantedAuthority → requestMatcher → allow/deny decision**, name the **two groups** and their exact authorities, run the matrix test suite, and predict the outcome of changing a single permission or rule.

This exercise only demonstrates HTTP-layer permissions with in-memory accounts and static data. Before applying this to a real system, design the identity source, passwords and secrets, service-layer permissions, resource ownership, security event auditing, tenant checks, client-appropriate CSRF, and anti-horizontal-privilege-escalation tests.

Official documentation:

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — In-Memory Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html)
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
