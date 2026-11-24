# RBAC: Role-Based Access Control

## 1. Objectives and Context

After this lesson, you will be able to:

1. Explain **RBAC** through the relationships between users, roles, and permissions; distinguish **authentication** from **authorization**.
2. Design a role/permission matrix for an application with multiple user types and apply the principle of least privilege.
3. Understand **role** and **`GrantedAuthority`** in Spring Security; correctly use `hasRole`, `hasAnyRole`, `hasAuthority`, and the `ROLE_` prefix.
4. Apply RBAC at the HTTP layer with `SecurityFilterChain` and at the service layer with `@PreAuthorize`, and understand why multiple call paths must be protected.
5. Run a Java 17 Spring Boot application with three roles, verifying 200, 401, and 403 cases via HTTP and automated tests.
6. Recognize the limits of RBAC, avoiding confusing roles with data ownership, attribute-based authorization, or object state.

**Scope:** Spring Security fundamentals with a Servlet/MVC demo so you can easily observe `HttpSecurity`, `SecurityFilterChain`, and method security. Spring WebFlux has corresponding security APIs on a different stack (`ServerHttpSecurity`, `SecurityWebFilterChain`, `@EnableReactiveMethodSecurity`); do not use Servlet classes in a pure WebFlux application. RBAC principles are independent of the HTTP stack.

## 2. What Is RBAC?

**RBAC (Role-Based Access Control)** is an access decision model based on **roles assigned to subjects** rather than assigning individual permissions directly to each account.

Three core concepts:

- **User/subject:** the user or service identity attempting to perform an operation.
- **Role:** a group of responsibilities in the system, such as `READER`, `EDITOR`, `ADMIN`.
- **Permission:** the ability to perform an **action** on a given **resource**, such as `article:read`, `article:create`, `article:delete`.

Relationship model:

```text
User  ──assigned──> Role ──granted──> Permission
  Lan             EDITOR                  article:read
                                          article:create
                                          article:update

  Minh            READER                  article:read
```

A typical authorization decision in RBAC checks whether *the authenticated user holds a recognized role and whether that role is permitted to perform the requested action*. The `Role → Permission` mapping is normally managed by application policy; some applications simplify this by binding roles directly to endpoints.

**Distinguish two questions:**

- **Authentication:** “Who are you?” Examples: HTTP Basic, login session, verified OAuth2/JWT. The outcome is typically represented as `Authentication`.
- **Authorization:** “What is this identity allowed to do with this resource?” Example: a logged-in user lacking permission to delete an article.

RBAC **does not replace** authentication. Knowing someone self-declared as “ADMIN” in a query parameter or header does not mean the system should recognize that role.

## 3. From Business Requirements to a Permission Matrix

Suppose an article system has three user types:

| Action | READER | EDITOR | ADMIN |
| --- | :---: | :---: | :---: |
| View published articles | ✅ | ✅ | ✅ |
| Create draft | ❌ | ✅ | ✅ |
| Edit draft | ❌ | ✅ | ✅ |
| Publish article | ❌ | ❌ | ✅ |
| Delete any article | ❌ | ❌ | ✅ |
| Manage users | ❌ | ❌ | ✅ |

This is an **illustrative example policy**, not a mandatory standard for every application. Clarify actions, resource states, and organizational boundaries before drafting the matrix. In particular, “EDITOR may edit articles” does not yet answer whether an editor may edit *another person's articles* or *published* articles.

Design process:

1. List **resources**: articles, drafts, users, reports, system configuration.
2. List **actions**: `read`, `create`, `update`, `publish`, `delete`, `manage`.
3. Identify real responsibility groups and name the roles. Do not create a new role merely because each URL has a different path.
4. Grant the minimal permission set to each role (principle of least privilege). New features start ungranted by default.
5. Document extra conditions such as “only own articles”, “not yet published”, or “same department”; these go beyond pure RBAC and must be checked at the business layer.
6. Verify the policy with a test matrix covering both allowed and denied cases.

An important property: **one user can hold multiple roles**. Roles can also be organized hierarchically *if the system configures a role hierarchy*. Naming a role `ADMIN` does not automatically make it inherit `EDITOR` or `READER` in Spring Security.

### RBAC Variants (Enough to Recognize)

- **Core RBAC:** basic user-role and role-permission relationships.
- **Hierarchical RBAC:** supports role inheritance (`ADMIN > EDITOR > READER`), which must be explicitly defined.
- **Constrained RBAC:** adds constraints such as separation of duties (one person cannot both submit and approve a transaction).
- **Symmetric RBAC:** manages/reviews bidirectional role-permission assignments according to the policy model.

These variants are modeling approaches; they do not mean Spring Security automatically enforces all of them just by adding a `@PreAuthorize` annotation.

## 4. How Does Spring Security Represent Roles?

After successful authentication, Spring Security places an `Authentication` object into the appropriate `SecurityContext`. `Authentication` provides the `principal`, authentication state, and a `Collection<? extends GrantedAuthority>`.

`GrantedAuthority` represents **a granted authority name** that the authorization mechanism can match against, for example:

```text
Authentication
  principal = "editor"
  authenticated = true
  authorities = ["ROLE_EDITOR", "article:read", "article:write"]
```

Spring Security does not force every authority to start with `ROLE_`. By default convention, **a role is an authority prefixed with `ROLE_`**; fine-grained permissions can use their own names like `article:read`.

| Configuration/expression | Checked by default | Notes |
| --- | --- | --- |
| `hasRole("ADMIN")` | authority `ROLE_ADMIN` | Automatically adds default role prefix |
| `hasAnyRole("READER", "EDITOR")` | `ROLE_READER` **or** `ROLE_EDITOR` | Does not require both |
| `hasAuthority("ROLE_ADMIN")` | exact string `ROLE_ADMIN` | Does not add prefix |
| `hasAuthority("article:write")` | exact string `article:write` | Useful for fine-grained permissions |
| `authenticated()` | authentication state meets requirement | Does not replace a specific role condition |
| `permitAll()` | permits route access | Does not turn the user into authenticated |
| `denyAll()` | denies access | Useful for default-deny policies |

**Common mistake:** calling `hasRole("ROLE_ADMIN")` with the default prefix mechanism; pass `"ADMIN"` to `hasRole`, or use `hasAuthority("ROLE_ADMIN")` when you want to match the exact string. Systems can customize the role prefix; all examples here use the default convention.

When creating an account with `User.withUsername(...).roles("ADMIN")`, Spring Security turns the role into the `ROLE_ADMIN` authority. Conversely, `.authorities("article:write")` keeps the provided authority name unchanged. Do not pass the `ROLE_` prefix into `.roles(...)`.

A user who only has `ROLE_ADMIN` **does not automatically have** `ROLE_EDITOR`. If the policy requires both to edit articles, you can:

- Grant the additional authorities to admin.
- Configure an explicit `RoleHierarchy`.
- Write `hasAnyRole('EDITOR', 'ADMIN')` if only those two roles need access together.

The last option is **an OR rule for the action**, not a declaration of inheritance.

## 5. Decision Flow in Spring Security

In a Spring MVC (Servlet) application, the typical flow is:

```text
HTTP request
  ↓
Servlet Filter Chain
  ↓
Spring Security FilterChainProxy / SecurityFilterChain
  ├─ obtain/build Authentication via configured mechanism
  ├─ determine matching requestMatcher
  └─ evaluate rule in authorizeHttpRequests
       ├─ deny → entry point / access-denied handling
       └─ proceed
             ↓
          Controller
             ↓
       Spring bean proxy with @PreAuthorize? 
             ├─ deny → AccessDeniedException
             └─ allow invoking business method
                    ↓
                 Response
```

**Authorization decision points:** request authorization (protecting HTTP routes) and method authorization (protecting calls to beans). Both can be used together. A service may be invoked from a controller, scheduled job, message listener, or another component; thus blocking URLs alone is sometimes insufficient for business policy.

In `authorizeHttpRequests`, Spring Security evaluates matcher/rule pairs **in declaration order and applies the first matching rule**. Specific rules must come before broad rules:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/admin").hasRole("ADMIN")
    .requestMatchers("/reports/**").authenticated()
    .anyRequest().denyAll()
)
```

This is a **fragment** inside `HttpSecurity`, not a standalone Java file. If `"/reports/**"` is placed first, a request to `"/reports/admin"` matches the broad rule first, preventing the `ADMIN` rule behind it from taking effect. Never rely on accidental ordering to protect resources.

**401 and 403:**

- `401 Unauthorized` usually indicates the request lacks valid authentication and the application requires authentication; HTTP Basic typically includes `WWW-Authenticate`.
- `403 Forbidden` usually means the request is recognized but fails authorization conditions.
- The exact response selected also depends on the authentication entry point, access-denied handler, session, token, and exception handling configuration. A `403` can also come from CSRF or another rule—do not assume every 403 means a wrong role.

## 6. Runnable Java 17 Example: RBAC for an Article Area

The example intentionally uses **Spring Boot 3.3.13 (Spring Security 6.x)** and Servlet MVC. The application runs with Gradle 8.x and Java 17+. Three demo accounts each have exactly one role: `reader`, `editor`, `admin`.

Four GET endpoints let us observe permissions without mutating data or disabling CSRF:

| Endpoint | Control point | Rule |
| --- | --- | --- |
| `GET /public` | HTTP security | Anyone can view |
| `GET /articles` | HTTP + service | Must be authenticated; service allows READER/EDITOR/ADMIN |
| `GET /articles/editor` | HTTP + service | Must be authenticated; service allows EDITOR/ADMIN |
| `GET /articles/admin` | HTTP + service | HTTP requires ADMIN; service also requires ADMIN |

All unlisted endpoints are blocked by `anyRequest().denyAll()`. The HTTP filter uses explicit matcher ordering; the service adds `@PreAuthorize` checks. This illustrates two layers of permission control.

### 6.1. Project Structure

```text
rbac-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/rbac/
    │   ├── RbacDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── ArticleService.java
    │   └── ArticleController.java
    └── test/java/com/example/rbac/
        └── RbacSecurityTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'rbac-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
```

Use **one web stack** (`spring-boot-starter-web`) in this example. The example parts in the following sections form one standalone application; place them in the exact filenames/packages rather than combining all classes into a single file.

### 6.2. Main Application

**`src/main/java/com/example/rbac/RbacDemoApplication.java`**

```java
package com.example.rbac;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RbacDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RbacDemoApplication.class, args);
    }
}
```

### 6.3. Defining Users and HTTP Rules

**`src/main/java/com/example/rbac/SecurityConfig.java`**

```java
package com.example.rbac;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/articles/admin").hasRole("ADMIN")
                .requestMatchers("/articles/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password("{noop}editor123")
            .roles("EDITOR")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
```

Exact explanation of each choice:

1. `@EnableMethodSecurity` enables `@PreAuthorize` checks on Spring beans; adding the Spring Security dependency **does not automatically enable** method security.
2. `permitAll()` allows `/public` without an account.
3. `requestMatchers("/articles/admin").hasRole("ADMIN")` is evaluated **before** `"/articles/**"` and requires authority `ROLE_ADMIN`.
4. Other `/articles...` requests only require authentication at the HTTP layer; the service layer checks detailed permissions.
5. `anyRequest().denyAll()` rejects endpoints outside the list (closed by default).
6. `httpBasic(withDefaults())` enables HTTP Basic authentication, and `formLogin(...disable())` disables form login so curl output is easy to inspect. **CSRF remains enabled**; all example operations are safe GETs that do not mutate data.
7. `InMemoryUserDetailsManager` is suitable for exercises; production needs a proper user store, role lifecycle, and storage.
8. `{noop}` stores plaintext passwords only for running demos; **do not use in production**. Production requires salted password hashing, protected secrets, and HTTPS.

**Important note on “ADMIN inherits EDITOR”:** here `admin` only has `ROLE_ADMIN`. Admin can access the editor page because the service uses `hasAnyRole('EDITOR','ADMIN')`, not because the system automatically grants `ROLE_EDITOR`.

### 6.4. Protecting Operations With @PreAuthorize

**`src/main/java/com/example/rbac/ArticleService.java`**

```java
package com.example.rbac;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ArticleService {

    @PreAuthorize("hasAnyRole('READER', 'EDITOR', 'ADMIN')")
    public String listFor(String username) {
        return "articles for " + username;
    }

    @PreAuthorize("hasAnyRole('EDITOR', 'ADMIN')")
    public String editorArea() {
        return "editor area";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminArea() {
        return "admin area";
    }
}
```

The service class is a **Spring-managed bean**. When the controller calls it through the bean proxy, Spring Security evaluates the expression **before** executing the method. If unauthorized, the call is blocked and does not return a business value as a successful call would.

Do not infer from this example that `@PreAuthorize` triggers on every Java call: calling an annotated method via `this.otherMethod()` inside the same object can bypass the AOP proxy (self-invocation). In real designs, organize security entry points through Spring-managed beans/services, test authorization behavior directly, and pay attention to proxying.

### 6.5. Controller Passing Authenticated Identity to the Service

**`src/main/java/com/example/rbac/ArticleController.java`**

```java
package com.example.rbac;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArticleController {
    private final ArticleService articleService;

    public ArticleController(ArticleService articleService) {
        this.articleService = articleService;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/articles")
    public String list(Authentication authentication) {
        return articleService.listFor(authentication.getName());
    }

    @GetMapping("/articles/editor")
    public String editor() {
        return articleService.editorArea();
    }

    @GetMapping("/articles/admin")
    public String admin() {
        return articleService.adminArea();
    }
}
```

`Authentication` in the `/articles` endpoint is supplied by Spring MVC from the security context of the request allowed to proceed. `authentication.getName()` is used to display the identity name in the demo; do not use that name as proof of resource ownership. The service still enforces `@PreAuthorize` checks based on authorities.

### 6.6. Run and Observe

Your machine needs **JDK 17+ and Gradle 8.x** (or a compatible Gradle Wrapper). In the `rbac-demo` directory:

```bash
gradle test
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew test` and `./gradlew bootRun` on Linux/macOS, or `gradlew.bat test` and `gradlew.bat bootRun` on Windows. Because this is a Spring app with dependencies outside the JDK, standalone `javac`/`java` will not resolve the classpath automatically; Gradle compiles and runs Java appropriately.

In another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/articles
curl -i -u reader:reader123 http://localhost:8080/articles
curl -i -u reader:reader123 http://localhost:8080/articles/editor
curl -i -u editor:editor123 http://localhost:8080/articles/editor
curl -i -u editor:editor123 http://localhost:8080/articles/admin
curl -i -u admin:admin123 http://localhost:8080/articles/admin
curl -i -u admin:admin123 http://localhost:8080/articles/editor
```

**Expected result matrix (with the exact configuration above):**

| Caller | `/public` | `/articles` | `/articles/editor` | `/articles/admin` |
| --- | :---: | :---: | :---: | :---: |
| Anonymous | 200 | 401 | 401 | 401 |
| reader | 200 | 200 | 403 | 403 |
| editor | 200 | 200 | 200 | 403 |
| admin | 200 | 200 | 200 | 200 |

At `/articles/admin`, the URL rule blocks reader/editor before entering the controller. At `/articles/editor`, the URL rule only requires `authenticated`, so reader reaches the service call and is then denied by `@PreAuthorize`. Both can return 403, yet they are **two different checkpoints**.

Success bodies identifiable from the code:

```text
GET /public                      → public
GET /articles (reader)           → articles for reader
GET /articles/editor (editor)    → editor area
GET /articles/admin (admin)      → admin area
```

These are **bodies**, not full wire-format responses. Status lines, headers, and error body content can vary depending on HTTP configuration, content negotiation, and error handling; only expect the status codes listed in the matrix.

### 6.7. Automated Authorization Tests

**`src/test/java/com/example/rbac/RbacSecurityTest.java`**

```java
package com.example.rbac;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RbacSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadArticles() throws Exception {
        mvc.perform(get("/articles"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "reader", roles = "READER")
    void readerCanListButCannotEdit() throws Exception {
        mvc.perform(get("/articles"))
            .andExpect(status().isOk())
            .andExpect(content().string("articles for reader"));

        mvc.perform(get("/articles/editor"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanOpenEditorAreaButNotAdminArea() throws Exception {
        mvc.perform(get("/articles/editor"))
            .andExpect(status().isOk())
            .andExpect(content().string("editor area"));

        mvc.perform(get("/articles/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanOpenBothPrivilegedAreas() throws Exception {
        mvc.perform(get("/articles/editor"))
            .andExpect(status().isOk());

        mvc.perform(get("/articles/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));
    }

    @Test
    @WithMockUser(roles = "OTHER")
    void anyAuthenticatedRoleIsNotEnoughForService() throws Exception {
        mvc.perform(get("/articles"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicIsAccessibleWithoutCredentials() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

The tests above use Spring MVC `MockMvc` and `spring-security-test`. `@WithMockUser(roles = "EDITOR")` creates the `ROLE_EDITOR` authority for the **test request**, without reading accounts from `InMemoryUserDetailsManager`. Therefore, these tests verify authorization rules, not end-to-end password storage or the real HTTP Basic flow. The `curl` commands above help observe authentication with real credentials.

A meaningful test suite checks more than “does the endpoint return 200?”: it tests explicit allow/deny, unauthenticated state, and unlisted roles. When policies change, update the business matrix and tests together.

## 7. Roles, Fine-Grained Permissions, and HTTP Method Checks

Role names like `EDITOR` are convenient for learners, but real systems often need action-based permissions. Instead of tying many URLs to role names, you can model fine-grained authorities:

```text
ROLE_READER → article:read
ROLE_EDITOR → article:read, article:create, article:update
ROLE_ADMIN  → article:read, article:create, article:update,
              article:publish, article:delete, user:manage
```

Once the principal has been granted the corresponding authorities from a trusted source, security can check them directly:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**")
        .hasAuthority("article:read")
    .requestMatchers(HttpMethod.POST, "/api/articles")
        .hasAuthority("article:create")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**")
        .hasAuthority("article:delete")
    .anyRequest().denyAll()
)
```

This is a **configuration fragment**, not a standalone program; it requires importing `org.springframework.http.HttpMethod` and placing inside `HttpSecurity`. The `article:*` authorities **are not auto-generated** from `.roles("EDITOR")` in the demo above; you must assign/map them explicitly or configure the corresponding policy. Do not copy this fragment over the demo expecting the three old accounts to automatically have `article:read`.

For mutating APIs, the HTTP method is an important signal but **not enough**: you must check ownership, state, object ID, tenant, validation, CSRF (if the browser sends cookies/credentials), and business policies. Do not disable CSRF out of habit just to make a test POST request return 200. For stateless REST APIs using bearer tokens in the `Authorization` header, there may be clear architectural reasons to configure CSRF differently from cookie/session-based apps; evaluate according to the actual authentication mechanism.

### Is Role Hierarchy Enabled by Default?

No. Spring Security supports configuring a role hierarchy, but in the demo above only **three separate authorities** exist. Example illustrating the desired hierarchy:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_READER
```

This is only a **policy diagram**, not an executable configuration. To make the hierarchy work, declare a `RoleHierarchy` and ensure the relevant authorization components actually use that hierarchy. If the system has no hierarchy, write explicit role conditions or grant the corresponding authorities. Do not assume role names carry natural-language inheritance.

## 8. RBAC Does Not Solve Every Authorization Problem

A role-only policy can be too broad. For instance, both Lan and Minh carry `ROLE_EDITOR`, yet an article is Lan's private draft. If the rule is only `hasRole('EDITOR')`, the system may accidentally let Minh edit Lan's draft.

Distinguish:

| Question | Appropriate mechanism |
| --- | --- |
| “Does the caller belong to the EDITOR group?” | RBAC / role authorization |
| “Does the caller have the `article:update` permission?” | Authority / permission-based authorization |
| “Who owns this article?” | User–resource relationship check (ownership/ReBAC) |
| “Is this article `DRAFT` or `PUBLISHED`?” | Resource state/attribute check (ABAC) |
| “Do the user and article belong to the same tenant?” | Tenant boundary + object-level authorization |
| “Can the requester self-approve an operation they just created?” | Business constraint / separation of duties |

Spring Security lets you combine role conditions with business conditions. Conceptual example:

```java
@PreAuthorize("hasRole('EDITOR') and @articleAccess.canEdit(#articleId, authentication)")
public void editArticle(long articleId) {
    // update after permissions have been verified
}
```

This is an **illustrative fragment, not standalone**: it requires an `articleAccess` bean implementing `canEdit(...)`, the method must reside in a Spring-managed service proxy, and state/tenant/ownership must be checked against trusted server data. Permission checks and updates must be designed safely against concurrent modifications; checks outside a transaction may fail to protect data whose state changes immediately after the check.

**Preventing IDOR (Insecure Direct Object Reference):** an endpoint `GET /documents/1` being safe for an editor does not prove `GET /documents/2` is also permitted for that editor. Every request for a specific object must be checked at the appropriate data boundary.

## 9. Role Lifecycle Management and Trusted Sources

RBAC is only trustworthy when **the role-assignment source is trustworthy**:

- For internal login, assign roles from a protected user store or identity service, never from a public registration JSON body.
- For OAuth2 Resource Server/JWT, tokens must have their **signature, issuer, audience, expiry, and required constraints verified**. Roles/claims from an IdP usually require a mapping step into `GrantedAuthority` per application policy. Do not assume every JWT has `ROLE_ADMIN` just because it contains a claim named `roles`.
- In multi-tenant systems, an “ADMIN” role may only be valid within one tenant; authorization must bind the proper scope and resource.
- When an admin changes roles, account for update latency in active sessions, caches, or still-valid tokens. A revoked role remaining in an active token is a risk that needs a mitigation strategy.
- Write audit logs for role-assignment changes and sensitive actions; do not log passwords, tokens, session cookies, or secrets.
- Enforce authorization on the **server**. Hiding a “Delete” button in the UI only improves UX; a client can still send HTTP requests directly.

Practical principles: **least privilege**, **default deny**, **separation of duties**, and checking permissions against **the exact resource being acted upon**.

## 10. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing `hasRole("ROLE_ADMIN")` with `hasRole("ADMIN")` | Wrong syntax/semantics under default role prefix | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Assuming ADMIN automatically inherits EDITOR | Admin may be denied, or policy misunderstood | Configure a real hierarchy, grant full authorities, or declare `hasAnyRole` explicitly |
| Putting `"/**".permitAll()` before sensitive rules | First matcher matches everything, later rules become dead code | Put specific rules first, `denyAll` last |
| Protecting only the controller when the service is called from elsewhere | Business permission check bypassed | Protect the service via `@PreAuthorize` or an authorization manager |
| Calling a method on the same bean with `this.secureMethod()` | May bypass the AOP proxy | Invoke through the Spring bean proxy, test real call paths |
| Checking only role without checking owner/tenant/state | IDOR, reading/editing others' resources | Evaluate the specific resource using trusted data |
| Using client header `X-Role: ADMIN` as a role | Self privilege escalation | Rely on `Authentication` and mappings from verified authentication sources |
| Mistaking `authenticated()` for allowing the right role | Any logged-in user passes the HTTP layer | Use explicit role/authority rules and method security |
| Believing every 403 is a wrong role | Overlooks CSRF or other handlers | Inspect filter chain, security logs, and root cause |
| Using `{noop}` passwords / in-memory users in production | Unprotected passwords, hard-to-manage roles | Strong encoder, identity store, and role grant/revocation workflow |
| Not testing denied roles | Risk of “anyone allowed” flaws | Test positive/negative and unknown-role matrices |
| Changing roles without considering still-valid sessions/tokens | Old permissions outlive intended lifetime | Design expiry, refresh, and revoke/cache invalidation |

### Checklist When a Request Is Unexpectedly Denied

1. Did login succeed? What name, state, and authorities does `Authentication` have (log only after stripping sensitive data)?
2. Is the actual authority `ROLE_EDITOR` or `EDITOR`? Is the rule `hasRole` or `hasAuthority`?
3. Do the request method/path match the intended matcher? Does a broader rule appear earlier?
4. Was the request blocked at `SecurityFilterChain` or `@PreAuthorize`? Are CSRF, custom filters, or another exception handler involved?
5. Does the decision also depend on resource ID, owner, tenant, state, or changing policy?
6. Is there a test covering this exact user-role-action-resource combination?

## 11. Practice Questions

**1.** A user has `ROLE_READER` and `ROLE_EDITOR`, while `/admin` requires `hasRole("ADMIN")`. Is the user permitted?

*No.* The `ROLE_ADMIN` authority (or another configured authorization rule permitting access) is required; having two other roles does not implicitly grant ADMIN.

**2.** What is the difference between `hasRole("ADMIN")` and `hasAuthority("ROLE_ADMIN")`?

*Under the default role prefix configuration, both check for the presence of `ROLE_ADMIN`.* `hasAuthority` matches the literal string; `hasRole` applies the role prefix.

**3.** Why is `anyRequest().denyAll()` useful?

*It locks down unlisted routes*, reducing the risk of newly added endpoints being exposed without a policy. Even so, you must explicitly permit required routes such as health/readiness or static assets per deployment needs.

**4.** A user logs in and calls `/articles/editor` but gets 403; why might that happen?

*In the demo, the HTTP layer lets authenticated users through, while `editorArea()`'s `@PreAuthorize` requires EDITOR or ADMIN.* Reader fails the service condition. In other apps, also check CSRF/filters/specific rules.

**5.** Is `@PreAuthorize("hasRole('EDITOR')")` enough to let an editor edit any article?

*No.* If the requirement is to edit only self-owned articles or drafts, check the object/owner/state using server-side data.

**6.** If a registration API lets users submit `{"role":"ADMIN"}` and saves it directly, what vulnerability occurs?

*Privilege escalation / mass assignment.* The backend must determine assignable roles and separate self-registration from administrative flows.

**7.** Does a `ROLE_ADMIN` user in the demo have `ROLE_EDITOR`? Why can they still open `/articles/editor`?

*No.* The service code checks `hasAnyRole('EDITOR','ADMIN')`, so `ROLE_ADMIN` satisfies the OR expression.

**8.** Do 401 and 403 mean “server error”?

*No.* Both are typically intentional security responses; 401 relates to authentication requirements, and 403 relates to access denial. Inspect the configuration to pinpoint the exact reason.

## 12. Summary

- **RBAC** is a model for granting permissions through **roles**: user → role → permission.
- In Spring Security, a role is typically a **`GrantedAuthority` starting with `ROLE_`**, and `hasRole("ADMIN")` checks `ROLE_ADMIN` by default convention.
- Authorization at **URLs** via `SecurityFilterChain` controls HTTP requests; authorization at **methods/services** via `@EnableMethodSecurity` + `@PreAuthorize` protects business operations.
- **The order of `requestMatchers` matters; use a default-deny policy** and test both allowed and denied cases.
- **ADMIN does not automatically inherit lower roles**; hierarchies or permission mappings require explicit configuration.
- RBAC does not replace checks for **resource ownership, tenant, or business state**, nor does it replace authentication.
- For production, roles must come from a **trusted source**, with clear grant/revocation management, never relying on the UI or client-declared data.

## Official Documentation

- Spring Security — Authorize HTTP Requests (request matchers, role/authority): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing with Spring MVC / MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — `@WithMockUser` and testing method security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Boot 3.3 system requirements (Java 17+, Gradle 7.5+/8.x): https://docs.spring.io/spring-boot/3.3/system-requirements.html
