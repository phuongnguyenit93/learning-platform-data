# AndRequestMatcher, OrRequestMatcher, and NegatedRequestMatcher in Spring Security

> **Topic:** Spring Security — RequestMatcher. This lesson teaches how to **combine multiple HTTP request identification conditions** using AND, OR, and NOT; read composite expressions accurately; integrate them into `authorizeHttpRequests` and `securityMatcher`; and test overlapping, excluded, and default-deny cases. Examples use Java 17+, Spring Boot 3.5.x, and Spring Security 6.5.x on the Servlet stack.

## 1. What Question Does RequestMatcher Answer?

`org.springframework.security.web.util.matcher.RequestMatcher` is an interface used to test whether an `HttpServletRequest` satisfies an **identification condition**.

~~~java
@FunctionalInterface
public interface RequestMatcher {
    boolean matches(HttpServletRequest request);
    // Modern versions also provide the default method matcher(request)
    // returning MatchResult, which may contain path variables.
}
~~~

This is **abbreviated conceptual code** to explain the contract; do not copy it into a project since Spring Security already provides the interface. The essential check is `matches(request)` returning `true` or `false`.

Examples of identification conditions:

- Path belongs to `/api/docs/**`.
- HTTP method is `GET`.
- A certain header is present; a query parameter is supplied in the required format.
- Request has a specific dispatcher type.
- Path is **one of two** report endpoints.
- Request is a **GET for documents, excluding private documents**.

**However:** a matcher returning `true` only means **the request belongs to the group governed by this rule**, **not** "the user is granted access." Actual authorization resides in the `AuthorizationManager` attached to that matcher, such as `hasAuthority("docs:read")`, `authenticated()`, or `denyAll()`.

### Example: Same Matcher, Different Authorization Decisions

~~~java
// Fragment inside authorizeHttpRequests:
.requestMatchers(docsReadMatcher).hasAuthority("docs:read")
~~~

Here:

1. `docsReadMatcher.matches(request)` determines whether this is a normal document-read request.
2. Only when the matcher matches does `hasAuthority("docs:read")` inspect the caller's `Authentication`.
3. A user lacking `docs:read` is **DENIED**, even though the matcher returned `true`.
4. If the matcher returns `false`, Spring Security tries the **next HTTP rule** in the list, rather than automatically granting access.

Distinguish two questions:

- **Request matching:** "What kind of request is this?"
- **Authorization:** "Is the current identity allowed to perform this kind of request on that resource?"

## 2. Three Combinators and Their Boolean Meaning

Spring Security provides:

| Class | Boolean expression | `matches(request)` returns `true` when... |
| --- | --- | --- |
| `AndRequestMatcher` | `A ∧ B` | **Every** child matcher matches |
| `OrRequestMatcher` | `A ∨ B` | **At least one** child matcher matches |
| `NegatedRequestMatcher` | `¬A` | The wrapped matcher **does not** match |

Imports:

~~~java
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
~~~

The AND and OR matchers have constructors accepting multiple `RequestMatcher`s via **varargs** or `List<RequestMatcher>`; NOT accepts **one** `RequestMatcher`. In practice, supply the necessary child matchers and avoid empty lists or unintentional configurations that rely on unverified boundary behavior.

### Truth Table

| A | B | AND `A ∧ B` | OR `A ∨ B` | NOT `¬A` |
| :---: | :---: | :---: | :---: | :---: |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

These classes apply this boolean logic to **the same HTTP request**.

**Note:** `AND` and `OR` here combine **request matchers**, not "two authorities of a user." To express "has `docs:read` **or** `ROLE_ADMIN`", use `hasAnyAuthority` or an appropriate `AuthorizationManager`; never write `new OrRequestMatcher(...)` expecting it to create permission logic.

## 3. `AndRequestMatcher` — Satisfying **All** Conditions Simultaneously

Requirement: identify only **GET requests under `/api/docs/**`**.

Naming:

- `GET_METHOD`: `request.getMethod().equals("GET")`.
- `DOCS_PATH`: path matches `/api/docs/**`.

We need:

`docsGet = GET_METHOD AND DOCS_PATH`.

In Spring Security 6.5, you can use `PathPatternRequestMatcher` for the path and a lambda for the method:

~~~java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

var path = PathPatternRequestMatcher.withDefaults();

RequestMatcher getMethod =
    request -> "GET".equals(request.getMethod());

RequestMatcher docsPath = path.matcher("/api/docs/**");

RequestMatcher docsGet =
    new AndRequestMatcher(getMethod, docsPath);
~~~

This is a **fragment**, without `main`; place it in a Spring configuration and import the required classes. The `PathPatternRequestMatcher` API exists from Spring Security 6.5 onward, so older projects must pick a matcher supported by their version rather than copying verbatim.

Examples:

| Request | `GET_METHOD` | `DOCS_PATH` | `docsGet` |
| --- | :---: | :---: | :---: |
| `GET /api/docs/42` | true | true | **true** |
| `POST /api/docs/42` | false | true | false |
| `GET /api/reports/42` | true | false | false |
| `POST /api/reports/42` | false | false | false |

With `new AndRequestMatcher(a, b, c)`, all three conditions must match. Splitting logic into simple matchers usually makes testing far easier than one giant matcher reading method, path, headers, query, and user in a single function.

**Never use matchers as a substitute for authorization:** if `docsGet` returns true, you still must evaluate authority, owner, tenant, and relevant business constraints before returning data.

## 4. `OrRequestMatcher` — Any of Several Scenarios Matched

Requirement: both report paths `/api/reports/summary` and `/api/reports/draft` belong to the **READ_REPORT** group. We need:

`reportPath = summaryPath OR draftPath`.

~~~java
var path = PathPatternRequestMatcher.withDefaults();

RequestMatcher reportPath = new OrRequestMatcher(
    path.matcher("/api/reports/summary"),
    path.matcher("/api/reports/draft")
);

RequestMatcher reportGet = new AndRequestMatcher(
    request -> "GET".equals(request.getMethod()),
    reportPath
);
~~~

Results:

| Request | Summary | Draft | OR of two paths | GET AND OR |
| --- | :---: | :---: | :---: | :---: |
| `GET /api/reports/summary` | true | false | true | **true** |
| `GET /api/reports/draft` | false | true | true | **true** |
| `GET /api/reports/other` | false | false | false | false |
| `POST /api/reports/summary` | true | false | true | false |

Multiple endpoints sharing the same **authorization policy** is a practical reason to use OR. In the DSL, you can also pass multiple paths directly to a single rule:

~~~java
// When two endpoints share one policy, the shorter syntax may suffice:
.requestMatchers("/api/reports/summary", "/api/reports/draft")
    .hasAuthority("report:read")
~~~

However, when you need to combine methods, headers, dispatcher types, or exclude a path set, `OrRequestMatcher` and `AndRequestMatcher` express the condition more clearly.

**Do not misread** `OrRequestMatcher(summaryPath, draftPath)` as "permission A OR permission B." It only unions **sets of HTTP requests** to which a rule applies.

## 5. `NegatedRequestMatcher` — Excluding a Case

Requirement: reading normal documents requires `docs:read`, whereas documents under `/api/docs/private/**` require `docs:private:read`. We do not want the broad rule for normal documents to catch private ones.

Let:

- `DOCS_PATH` = `/api/docs/**`.
- `PRIVATE_PATH` = `/api/docs/private/**`.

The normal documents set is:

`normalDocs = GET ∧ DOCS_PATH ∧ ¬PRIVATE_PATH`.

~~~java
RequestMatcher get = request -> "GET".equals(request.getMethod());
RequestMatcher allDocs =
    PathPatternRequestMatcher.withDefaults().matcher("/api/docs/**");
RequestMatcher privateDocs =
    PathPatternRequestMatcher.withDefaults()
        .matcher("/api/docs/private/**");

RequestMatcher normalDocsGet = new AndRequestMatcher(
    get,
    allDocs,
    new NegatedRequestMatcher(privateDocs)
);

RequestMatcher privateDocsGet =
    new AndRequestMatcher(get, privateDocs);
~~~

Table:

| Request | GET | DOCS_PATH | PRIVATE_PATH | NOT PRIVATE | `normalDocsGet` | `privateDocsGet` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| `GET /api/docs/42` | T | T | F | T | **T** | F |
| `GET /api/docs/private/99` | T | T | T | F | F | **T** |
| `POST /api/docs/42` | F | T | F | T | F | F |
| `GET /api/reports/summary` | T | F | F | T | F | F |

### Special Risk: NOT Alone Typically Matches **Too Broadly**

~~~java
// Dangerous if used as a public rule:
new NegatedRequestMatcher(privateDocs);
~~~

The expression above is true for **every request outside the private region**, including `/admin/delete`, `/billing/export`, and other paths wholly unrelated to documents. Combined with `permitAll()` near the top of the rule list, you can **expose almost the entire application**.

**Safe approach:** constrain with positive conditions first:

`GET ∧ /api/docs/** ∧ NOT /api/docs/private/**`.

NOT is **inverting an identification condition**, not "denying all users lacking permission." To deny access, use `denyAll()`, `hasAuthority(...)`, or an appropriate policy.

## 6. Nesting Matchers, Parentheses, and De Morgan's Laws

Because this is Boolean logic, **grouping** must be unambiguous. Let:

- `G` = request uses GET.
- `D` = path belongs to `/api/docs/**`.
- `P` = path belongs to `/api/docs/private/**`.
- `S` = path equals `/api/reports/summary`.
- `R` = path equals `/api/reports/draft`.

Expressions:

| Intent | Logic | Composition |
| --- | --- | --- |
| GET normal docs | `G ∧ D ∧ ¬P` | `And(G, D, Negated(P))` |
| GET either report | `G ∧ (S ∨ R)` | `And(G, Or(S, R))` |
| GET normal docs **or** GET report | `(G ∧ D ∧ ¬P) ∨ (G ∧ (S ∨ R))` | `Or(And(G,D,Negated(P)), And(G,Or(S,R)))` |
| Not GET normal docs | `¬(G ∧ D ∧ ¬P)` | `Negated(And(G,D,Negated(P)))` |

Java form for deep nesting:

~~~java
RequestMatcher normalOrReportRead = new OrRequestMatcher(
    new AndRequestMatcher(
        get,
        allDocs,
        new NegatedRequestMatcher(privateDocs)
    ),
    new AndRequestMatcher(
        get,
        new OrRequestMatcher(summaryPath, draftPath)
    )
);
~~~

This is a **fragment** assuming variables `get`, `allDocs`, `privateDocs`, `summaryPath`, and `draftPath` already exist. If an expression gets too deep, name intermediate matchers for readability and testability.

De Morgan's two laws:

- `¬(A ∨ B) = ¬A ∧ ¬B`.
- `¬(A ∧ B) = ¬A ∨ ¬B`.

For example, "belongs neither to summary **nor** to draft" equals "negation of belonging to either endpoint." Even so, never pair an overly broad NOT expression with `permitAll` without a path boundary condition.

**Do not rely on side effects or evaluation order** of child matchers. Although an implementation may short-circuit once the result is known, matchers should be **side-effect-free** checks that neither consume the request body nor depend on another matcher running beforehand.

## 7. Plain Java 17: Verifying Composition Logic Before Using the Framework

The program below simulates AND/OR/NOT using `java.util.function.Predicate` without Spring. It helps verify truth tables and request examples. This is a **learning model**, not the code of `PathPatternRequestMatcher`: the program uses `startsWith` for paths.

Create file **`MatcherLogicDemo.java`**:

~~~java
import java.util.List;
import java.util.function.Predicate;

public class MatcherLogicDemo {

    record Request(String method, String path) {}

    static void show(
        Request request,
        Predicate<Request> normalDocs,
        Predicate<Request> privateDocs,
        Predicate<Request> reports
    ) {
        System.out.println(
            request.method() + " " + request.path()
                + " => normal=" + normalDocs.test(request)
                + ", private=" + privateDocs.test(request)
                + ", report=" + reports.test(request)
        );
    }

    public static void main(String[] args) {
        Predicate<Request> get =
            request -> "GET".equals(request.method());

        Predicate<Request> docs =
            request -> request.path().startsWith("/api/docs/");

        Predicate<Request> privatePath =
            request -> request.path().startsWith("/api/docs/private/");

        Predicate<Request> summary =
            request -> "/api/reports/summary".equals(request.path());

        Predicate<Request> draft =
            request -> "/api/reports/draft".equals(request.path());

        Predicate<Request> normal = get
            .and(docs)
            .and(privatePath.negate());

        Predicate<Request> privateRead = get.and(privatePath);
        Predicate<Request> reportRead = get.and(summary.or(draft));

        List<Request> requests = List.of(
            new Request("GET", "/api/docs/42"),
            new Request("GET", "/api/docs/private/99"),
            new Request("POST", "/api/docs/42"),
            new Request("GET", "/api/reports/summary"),
            new Request("GET", "/api/reports/draft"),
            new Request("GET", "/api/reports/other")
        );

        for (Request request : requests) {
            show(request, normal, privateRead, reportRead);
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac MatcherLogicDemo.java
java MatcherLogicDemo
~~~

**Exact stdout:**

~~~text
GET /api/docs/42 => normal=true, private=false, report=false
GET /api/docs/private/99 => normal=false, private=true, report=false
POST /api/docs/42 => normal=false, private=false, report=false
GET /api/reports/summary => normal=false, private=false, report=true
GET /api/reports/draft => normal=false, private=false, report=true
GET /api/reports/other => normal=false, private=false, report=false
~~~

Meaning:

1. `normal=true` appears only when GET belongs to `/api/docs/**` and not private.
2. `private=true` appears only when GET belongs to private.
3. `report=true` appears only when GET targets one of the two summary/draft endpoints.
4. POST on the same path falls outside all three matchers because the method condition fails.
5. All false merely proves **no matcher matched**; an HTTP policy must include a fallback, typically `denyAll()`.

## 8. Putting All Three Matcher Types Into a Spring Boot Configuration

### 8.1. Policy Convention for the Demo

Take a small application with these endpoints:

| HTTP request | Matcher logic | Required authority |
| --- | --- | --- |
| `GET /public/ping` | GET AND public path | `permitAll()` |
| `GET /api/docs/42` | GET AND docs AND NOT private | `docs:read` |
| `GET /api/docs/private/99` | GET AND private | `docs:private:read` |
| `GET /api/reports/summary` | GET AND (summary OR draft) | `report:read` |
| `GET /api/reports/draft` | GET AND (summary OR draft) | `report:read` |
| `POST /api/reports` | POST AND reports collection | `report:write` |
| Other requests | Match none of the rules above | `denyAll()` |

To demonstrate NOT in action, the configuration below places the **normal docs rule before the private docs rule**. Even though normal docs uses the broad `/api/docs/**` pattern, `NegatedRequestMatcher(privateDocsPath)` ensures private docs **are not caught by the normal rule**. In production, you can still place specific rules before broad ones for easier review and safer future expansion.

Demo accounts:

| User | Authorities |
| --- | --- |
| `alice` | `docs:read`, `report:read` |
| `bob` | `docs:private:read` |
| `carol` | `report:read`, `report:write` |
| `dave` | `ROLE_USER` |

Note: `ROLE_USER` does not automatically grant `docs:read`. Each `hasAuthority(...)` matches the **exact** string.

### 8.2. Complete Spring Boot 3.5.x / Java 17+ Example

Use a Maven project with `spring-boot-starter-web` and `spring-boot-starter-security`. Create file **`src/main/java/com/example/matchers/MatcherApplication.java`**:

~~~java
package com.example.matchers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MatcherApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatcherApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        RequestMatcher get = request -> "GET".equals(request.getMethod());
        RequestMatcher post = request -> "POST".equals(request.getMethod());

        RequestMatcher allDocs = paths.matcher("/api/docs/**");
        RequestMatcher privateDocsPath =
            paths.matcher("/api/docs/private/**");

        RequestMatcher normalDocs = new AndRequestMatcher(
            get,
            allDocs,
            new NegatedRequestMatcher(privateDocsPath)
        );
        RequestMatcher privateDocs = new AndRequestMatcher(
            get,
            privateDocsPath
        );

        RequestMatcher reportsRead = new AndRequestMatcher(
            get,
            new OrRequestMatcher(
                paths.matcher("/api/reports/summary"),
                paths.matcher("/api/reports/draft")
            )
        );

        RequestMatcher reportsCreate = new AndRequestMatcher(
            post,
            paths.matcher("/api/reports")
        );

        RequestMatcher publicPing = new AndRequestMatcher(
            get,
            paths.matcher("/public/ping")
        );

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(publicPing).permitAll()
                .requestMatchers(normalDocs).hasAuthority("docs:read")
                .requestMatchers(privateDocs)
                    .hasAuthority("docs:private:read")
                .requestMatchers(reportsRead).hasAuthority("report:read")
                .requestMatchers(reportsCreate).hasAuthority("report:write")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // CSRF remains enabled; POST tests must supply a valid token.
        return http.build();
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("docs:read", "report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("docs:private:read")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .authorities("report:read", "report:write")
            .build();

        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, carol, dave
        );
    }

    @RestController
    static class Api {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/docs/{id}")
        String normalDoc(@PathVariable("id") long id) {
            return "doc " + id;
        }

        @GetMapping("/api/docs/private/{id}")
        String privateDoc(@PathVariable("id") long id) {
            return "private doc " + id;
        }

        @GetMapping("/api/reports/summary")
        String summary() {
            return "summary";
        }

        @GetMapping("/api/reports/draft")
        String draft() {
            return "draft";
        }

        @PostMapping("/api/reports")
        ResponseEntity<String> createReport() {
            // Illustrates authorization only, does not write to database.
            return ResponseEntity.status(HttpStatus.CREATED)
                .body("report created");
        }

        @GetMapping("/api/reports/other")
        String unlisted() {
            // Controller exists, yet fallback must block it.
            return "must not be exposed";
        }
    }
}
~~~

**Key checkpoints in the code:**

1. `PathPatternRequestMatcher.withDefaults()` builds path matchers (excluding context path when declaring patterns) for Spring Security 6.5; do not build string checks with `request.getRequestURI()` arbitrarily when the app has a different context path or servlet mapping.
2. The `get`/`post` lambdas inspect the HTTP request's own method, never touching user permissions.
3. `normalDocs` is **AND(GET, docs, NOT private)**.
4. `reportsRead` is **AND(GET, OR(summary, draft))**.
5. `reportsCreate` is **AND(POST, reports collection)**; because method and path differ, it never collides with GET rules.
6. `authorizeHttpRequests` pairs **each matcher with an AuthorizationManager** like `hasAuthority`; the three combinators never grant permissions themselves.
7. `anyRequest().denyAll()` guards unrecognized requests. If a new controller endpoint is added, it remains blocked until an approved rule is added.
8. `@EnableMethodSecurity` is not used because this lesson demonstrates **HTTP authorization** only. To protect owner, tenant, and resource state, add service or domain policies.

**Never use demo passwords in real environments.** HTTP Basic must run over HTTPS in production, and authorities should come from a trusted identity/authorization system.

## 9. HTTP Outcome Matrix for the Sample Application

Assume a `GET` or `POST` request to the exact URL in the table; for POST, assume a valid CSRF token is provided.

| Subject | Public GET | Normal doc GET | Private doc GET | Summary GET | Draft GET | Report POST* | Other GET |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Anonymous** | 200 | 401 | 401 | 401 | 401 | 401 | 401 |
| **Alice** | 200 | **200** | 403 | **200** | **200** | 403 | 403 |
| **Bob** | 200 | 403 | **200** | 403 | 403 | 403 | 403 |
| **Carol** | 200 | 403 | 403 | **200** | **200** | **201** | 403 |
| **Dave** | 200 | 403 | 403 | 403 | 403 | 403 | 403 |

`*` `Report POST` tests authorization only when a valid CSRF token is supplied. Without CSRF, an authorized user like Carol will still get **403**, but that comes from the **CSRF filter**, not the matcher or `hasAuthority("report:write")`.

**Notable cells:**

- Alice can view normal docs yet **cannot** view private docs. This is the most important test for `NegatedRequestMatcher`.
- Bob has only `docs:private:read`, so he **can view private** yet **cannot view normal docs**. This proves private permission does not imply normal permission.
- Carol can view both `summary` and `draft`, proving `OrRequestMatcher` applies one rule to both endpoints.
- Carol **cannot** access `GET /api/reports/other` despite having `report:read`: the OR matcher matches only the two listed paths.
- Dave is authenticated yet holds no business authority, so he cannot access sensitive APIs.
- Anonymous reaches only public; HTTP Basic returns **401** when unauthenticated on protected requests.

These statuses are **expected for the demo configuration**, not a universal contract across all apps; form login may redirect (302), bearer tokens have different error responses, and exception handlers may be customized.

## 10. Running the App and Manual Verification

From the Maven project root directory:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Once running on `localhost:8080`, GET requests can be verified immediately:

~~~bash
# Public: 200
curl -i http://localhost:8080/public/ping

# Alice has docs:read: 200, but lacks private: 403
curl -i -u alice:demo123 http://localhost:8080/api/docs/42
curl -i -u alice:demo123 http://localhost:8080/api/docs/private/99

# Bob has docs:private:read: 200 for private, 403 for normal
curl -i -u bob:demo456 http://localhost:8080/api/docs/private/99
curl -i -u bob:demo456 http://localhost:8080/api/docs/42

# Carol has report:read: both summary and draft return 200
curl -i -u carol:demo789 http://localhost:8080/api/reports/summary
curl -i -u carol:demo789 http://localhost:8080/api/reports/draft

# Another path outside OR: 403
curl -i -u carol:demo789 http://localhost:8080/api/reports/other

# Anonymous on protected URL: 401 with HTTP Basic
curl -i http://localhost:8080/api/docs/42
~~~

Response bodies for allowed requests:

| Request | Body |
| --- | --- |
| `GET /public/ping` | `pong` |
| Alice `GET /api/docs/42` | `doc 42` |
| Bob `GET /api/docs/private/99` | `private doc 99` |
| Carol `GET /api/reports/summary` | `summary` |
| Carol `GET /api/reports/draft` | `draft` |

**Why not claim `curl -u carol:demo789 -X POST /api/reports` must return 201?** CSRF protection is enabled. A POST request lacking a valid token will be blocked with 403 **before reaching authorization**. To test `reportsCreate` and `report:write` properly, use MockMvc with `csrf()` in the next section.

## 11. Automated Testing with MockMvc + Spring Security Test

### 11.1. Dependencies

In `pom.xml`, required test dependencies:

~~~xml
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
~~~

This is a **fragment** inside `<dependencies>` of a Maven POM, not a full `pom.xml`. If the project already has starter-test, do not add a duplicate. Spring Boot 3.5 manages compatible versions when using the default BOM/parent.

### 11.2. Test Class Running in the Same Project

Create file **`src/test/java/com/example/matchers/MatcherApplicationTests.java`**:

~~~java
package com.example.matchers;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class MatcherApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        // username,password,method,path,expectedStatus
        "anonymous,none,GET,/public/ping,200",
        "anonymous,none,GET,/api/docs/42,401",
        "anonymous,none,GET,/api/docs/private/99,401",
        "anonymous,none,GET,/api/reports/summary,401",

        "alice,demo123,GET,/api/docs/42,200",
        "alice,demo123,GET,/api/docs/private/99,403",
        "alice,demo123,GET,/api/reports/summary,200",
        "alice,demo123,GET,/api/reports/draft,200",
        "alice,demo123,GET,/api/reports/other,403",
        "alice,demo123,POST,/api/reports,403",

        "bob,demo456,GET,/api/docs/42,403",
        "bob,demo456,GET,/api/docs/private/99,200",
        "bob,demo456,GET,/api/reports/summary,403",
        "bob,demo456,POST,/api/reports,403",

        "carol,demo789,GET,/api/docs/42,403",
        "carol,demo789,GET,/api/docs/private/99,403",
        "carol,demo789,GET,/api/reports/summary,200",
        "carol,demo789,GET,/api/reports/draft,200",
        "carol,demo789,GET,/api/reports/other,403",
        "carol,demo789,POST,/api/reports,201",

        "dave,demo000,GET,/api/docs/42,403",
        "dave,demo000,GET,/api/docs/private/99,403",
        "dave,demo000,GET,/api/reports/draft,403",
        "dave,demo000,GET,/public/ping,200"
    })
    void authorizationMatrix(
            String username, String password, String method,
            String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder request =
            "POST".equals(method) ? post(path) : get(path);

        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }

        // To test POST permissions, eliminate the interfering CSRF factor.
        if ("POST".equals(method)) {
            request.with(csrf());
        }

        mvc.perform(request).andExpect(status().is(expected));
    }

    @Test
    void ordinaryDocAndPrivateDocAreMutuallyExclusive() throws Exception {
        mvc.perform(get("/api/docs/42")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("doc 42"));

        mvc.perform(get("/api/docs/private/99")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/docs/private/99")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string("private doc 99"));
    }

    @Test
    void orMatcherCoversBothReports() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports/draft")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports/other")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfStillRequiresWriteAuthority() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("alice", "demo123"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports")
                .with(httpBasic("carol", "demo789"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("report created"));
    }

    @Test
    void missingCsrfIsNotProofOfMissingAuthority() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsupportedMethodIsDenied() throws Exception {
        mvc.perform(post("/api/docs/42")
                .with(httpBasic("alice", "demo123"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

**Test structure:**

- `@SpringBootTest` + `@AutoConfigureMockMvc` loads the real security configuration and application controllers.
- `httpBasic()` passes demo credentials through Basic authentication to go through `UserDetailsService`. Compared to `@WithMockUser`, this also tests authentication and authority loading of demo users.
- `csrf()` is strictly for **test requests**, generating a valid token to verify write rules; it does not mean production clients can forge tokens arbitrarily.
- `@CsvSource` supplies **24 cases** with 200/201/401/403 outcomes; dedicated tests emphasize NOT, OR, methods, and CSRF.
- Unauthorized test cases are **mandatory**: if the normal docs matcher accidentally catches private docs, Alice getting 403 on private catches the regression.

Run tests:

~~~bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
~~~

Test output depends on JUnit/Maven versions, so exact log line counts or durations are not prescribed. What must be verified is that tests **pass**, Maven exits with code 0, and there are zero failures/errors.

## 12. Two Matcher Layers: `securityMatcher` and `requestMatchers`

A common confusion is that **combining RequestMatchers to select a SecurityFilterChain** and **combining RequestMatchers to select an authorization rule** use the same matcher API yet **have different effects**.

### 12.1. `securityMatcher(composite)` Selects the *Entire Chain*

Example applying a chain only to APIs for documents **or** reports:

~~~java
RequestMatcher docsOrReports = new OrRequestMatcher(
    paths.matcher("/api/docs/**"),
    paths.matcher("/api/reports/**")
);

http.securityMatcher(docsOrReports);
~~~

This is a **configuration fragment** assuming `paths` is already declared. It controls whether a `SecurityFilterChain` participates in handling the request. If the request falls outside this set, the chain **does not run** and rules inside it **have no effect** on that request.

If the application has only a chain scoped to `docsOrReports` without a fallback chain, `/admin` or `/public` may **go unprotected by Spring Security**. A proper fallback chain is required. Do not paste this fragment into Section 8's single-chain app without redesigning protection coverage.

### 12.2. `requestMatchers(composite)` Selects a *Rule Inside the Chain*

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(reportsRead).hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

`reportsRead` only classifies requests **after the chain has been selected**. In the HTTP rule list, the **first matching rule** applies; if it denies, Spring does not try lower rules to look for an ALLOW.

**Example vulnerability from rule ordering:**

~~~java
// Wrong: overly broad rule shadows the composite matcher below.
.requestMatchers("/api/**").authenticated()
.requestMatchers(normalDocs).hasAuthority("docs:read")
~~~

An authenticated user lacking `docs:read` can pass HTTP authorization for normal docs because `/api/**` comes first. Even if `normalDocs` evaluates the Boolean logic properly, it is **never reached** when an earlier rule already matched.

### 12.3. Layering Principle

- **Chain selection:** `FilterChainProxy` picks the first matching chain by priority.
- **Rule selection:** `AuthorizationFilter` picks the first matching rule inside the chain.
- **Authorization decision:** `hasAuthority`, `authenticated`, `denyAll`, or a custom `AuthorizationManager` makes the access decision.
- **Domain policy:** checks tenant, owner, and resource state in the business layer when needed.

Never conflate these four concepts. **Matcher AND/OR/NOT never replaces permission AND/OR/NOT**.

## 13. Risks When Combining Headers, Queries, Paths, and Request State

Because `RequestMatcher` is a functional interface, you can even combine custom matchers:

~~~java
RequestMatcher isGet = request ->
    "GET".equals(request.getMethod());

RequestMatcher hasPreviewFlag = request ->
    "true".equals(request.getParameter("preview"));

RequestMatcher previewDocs = new AndRequestMatcher(
    isGet,
    paths.matcher("/api/docs/**"),
    hasPreviewFlag
);
~~~

This is a **fragment** usable when requests have a dedicated preview branch. However, distinguish carefully:

- Clients can **freely set query parameters or headers**. A matcher like `X-Is-Admin=true` does **not** prove the caller is an admin.
- An `OrRequestMatcher` combining path and header carelessly can widen the matched set beyond intent: `OR(docsPath, previewHeader)` matches **every path** whenever a client sends that header.
- Using `NegatedRequestMatcher` on client-controlled signals is very dangerous if the rule grants `permitAll()`.
- Query strings are generally not part of path patterns. If policy depends on a query, use a matcher checking the query explicitly and test missing/forged cases.
- Matchers reading headers/queries should only route to the **appropriate policy**; granting access must still rely on `Authentication` and server-side policy.
- Avoid matchers performing heavy I/O, reading the body, or mutating the request during matching. The system may evaluate matchers in different contexts; never depend on side effects or call counts.

### Path and Servlet Context

`PathPatternRequestMatcher` uses patterns relative to the application's context path; if running behind a proxy or with a non-default servlet path, configure patterns/base paths accordingly. Do not look at the full browser URL and assume matchers compare that exact string.

In Spring Security 6.5, `AntPathRequestMatcher` is marked deprecated for removal; prefer `PathPatternRequestMatcher` for new projects, while migrations from older code must re-test patterns and servlet mappings. When upgrading to Spring Security 7, check API/DSL changes in the target version's docs.

## 14. `matcher(request)` Results and Path Variables

Besides `matches(request)` returning a boolean, `RequestMatcher` has `matcher(HttpServletRequest)` returning `MatchResult`, which can hold variables extracted by path matchers.

- `AndRequestMatcher.matcher(request)` can merge variables from matching child matchers; in Spring Security 6.5, on duplicate variable names, a later matcher's value may overwrite an earlier one.
- `OrRequestMatcher.matcher(request)` uses variables from the first matching matcher.
- `NegatedRequestMatcher` inverts the match condition. Do not expect NOT to extract variables from the negated matcher in the non-matching branch.
- If a custom matcher needs to return variables, it may need to override `matcher(request)`; a lambda implementing only `matches(request)` typically returns a default match result with no extracted variables.

For example, if `documentId` is needed in an authorization expression, use verified matcher/path-variable APIs rather than unvalidated manual path string splitting. In this lesson, matchers only select rules so **variable extraction is not needed**.

## 15. Testing Checklist for AND / OR / NOT

| Test group | Request or condition | Expectation |
| --- | --- | --- |
| AND all conditions met | GET + normal docs path | Matches normal docs |
| AND missing method | POST + normal docs path | Does not match normal docs |
| AND missing path | GET + reports path | Does not match normal docs |
| OR left branch | GET summary | Matches reportsRead |
| OR right branch | GET draft | Matches reportsRead |
| OR neither branch | GET other | Does not match reportsRead |
| NOT exclusion | GET private docs | Misses normal; matches private |
| NOT properly scoped | GET outside docs | Does not match normal |
| Authorization lacking authority | Alice calls private | 403, even though private matcher matches |
| Authorization with right authority | Bob calls private | 200 |
| Fallback | Carol calls report other | 403 |
| Independent CSRF | Carol POSTs report without token | 403 due to CSRF |
| Valid CSRF + sufficient permission | Carol POSTs report with token | 201 |
| Valid CSRF + insufficient permission | Alice POSTs report with token | 403 due to authorization |

**Negative testing note:** "Must not match" cases catch the most dangerous bugs. If NOT is omitted, Alice with `docs:read` could read private docs unintentionally. A test checking only that Bob gets 200 on private **would miss** this flaw.

**Testing with multiple chains:** If the app uses `@Order` and multiple `securityMatcher`s, add cases for requests entering chain A, chain B, and requests matching no chain; `anyRequest().denyAll()` inside chain A does not protect requests outside chain A.

## 16. Common Design Mistakes

1. **Using `OrRequestMatcher` expecting "has permission A or B."** Wrong logic category; that is OR over **requests**, not OR over authorities.
2. **Using `AndRequestMatcher` with `getMethod` while forgetting path bounds.** Can match too many unrelated GET requests.
3. **Putting `NegatedRequestMatcher(secret)` alone with `permitAll`.** Almost every other URL can become exposed.
4. **Forgetting fallback `anyRequest().denyAll()`.** Leads to unclear policy when new endpoints appear.
5. **Placing broad `/api/**.authenticated()` before a detailed composite matcher.** The detailed matcher never gets a chance to run.
6. **Believing two matchers on the same path create an AND/OR of permission decisions.** The first matching rule applies; combine conditions inside one manager/rule when needed.
7. **Relying on client-sent headers to grant roles.** Headers/queries are not trusted authorities.
8. **Using path patterns with wrong context/servlet path.** Can skip critical rules or match wrong endpoints.
9. **Writing `NOT` without a positive scope.** Negating a small set produces a huge request set.
10. **Ignoring HTTP method.** A GET rule can accidentally cover write requests if a path matcher stands alone.
11. **Concluding 403 means missing permission when POST lacks a CSRF token.** Test with valid CSRF to isolate authorization.
12. **Testing only allowed cases.** May miss privilege-escalation bugs for under-privileged users.
13. **Depending on evaluation order or side effects of child matchers.** Matchers should be pure and stable.
14. **Assuming `securityMatcher` and `requestMatchers` share the same scope.** One selects the chain; the other selects the rule.

## 17. Self-Check Questions

**1.** Does `AndRequestMatcher(GET, "/api/docs/**")` match `POST /api/docs/42`?  
**Answer:** No. The method does not match even though the path does.

**2.** Does `OrRequestMatcher(summaryPath, draftPath)` grant the user `report:read`?  
**Answer:** No. It only identifies requests belonging to either path; the authority is checked by `hasAuthority("report:read")`.

**3.** Does `NegatedRequestMatcher(privateDocsPath)` match `GET /admin/delete`?  
**Answer:** Yes, because that request **is not in privateDocsPath**. That is why NOT must be bounded by AND with the desired path/method set.

**4.** Which expression describes "GET docs but not private"?  
**Answer:** `And(GET, DOCS, Negated(PRIVATE))`.

**5.** Alice has `docs:read` but not `docs:private:read`. Why must `GET /api/docs/private/99` return 403?  
**Answer:** NOT excludes the request from normalDocs; the privateDocs rule matches and checks `docs:private:read`, which Alice lacks.

**6.** What happens if `/api/**.authenticated()` is placed before `normalDocs`?  
**Answer:** Any authenticated user can pass HTTP authorization for normal docs; the detailed rule is shadowed by first-match.

**7.** Can `new OrRequestMatcher(A, B)` be used in `http.securityMatcher`?  
**Answer:** Yes; there it decides whether **the entire SecurityFilterChain** applies to the request, not permissions yet.

**8.** Why is testing `POST /api/reports` with a valid CSRF token necessary to verify `report:write`?  
**Answer:** Because missing CSRF tokens are blocked before authorization, producing a 403 unrelated to authorities.

**9.** Does `¬(A ∨ B)` equal `¬A ∧ ¬B`?  
**Answer:** Yes (De Morgan), provided you define sets A and B and the scope of the negated expression properly.

**10.** If the user has URL permission yet the document belongs to another tenant, can you conclude ALLOW?  
**Answer:** No. Matchers and HTTP permissions do not replace specific resource checks in service/domain policies.

**Remember:** `AndRequestMatcher` = **all request conditions**, `OrRequestMatcher` = **any of the request conditions**, `NegatedRequestMatcher` = **inverts the request condition**. **Matchers only select rules; `AuthorizationManager` makes permission decisions.** Always constrain NOT with a positive scope, order rules properly, use default deny, and test denied cases too.

## Official Documentation

- Spring Security 6.5 — `RequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html
- Spring Security 6.5 — `AndRequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/AndRequestMatcher.html
- Spring Security 6.5 — `OrRequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/OrRequestMatcher.html
- Spring Security 6.5 — `NegatedRequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/NegatedRequestMatcher.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Java Configuration / SecurityFilterChain selection: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — MockMvc and HTTP Basic tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — MockMvc CSRF testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
