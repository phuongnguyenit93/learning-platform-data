# Testing Empty Sets, Unauthorized Elements, and Mixed Data in Spring Security Method Security

## 1. Goal

When using **`@PreFilter`** or **`@PostFilter`**, an empty result can have two very different causes: there were no elements initially, or there were elements but none passed the permission expression. Mixed data is even trickier: the system must **keep the right valid elements**, **remove the right unauthorized elements**, and **preserve order**.

This lesson focuses on testing data filtering behavior **at method boundaries** in Spring Security Authorization; it does not cover the HTTP `SecurityFilterChain` filters.

After completing it, you will be able to:

- Write tests for **empty sets**, **all-unauthorized elements**, **mixed data**, and the control case of **all-authorized elements**.
- Distinguish assertions for `@PreFilter` (filtering **input before the method body runs**) and `@PostFilter` (filtering **results after the method body runs**).
- Use `@WithMockUser` and Spring Test to switch principals and verify `filterObject` expressions.
- Spot tests that pass by accident due to missing Spring AOP proxies, bad fixture data, or checking only size.
- Distinguish **element filtering** behavior from **denying the entire invocation** with `@PreAuthorize`.

**Technical context:** Java 17+, Spring Security 6.x, JUnit Jupiter, and AssertJ, illustrated with dependencies managed by Spring Boot 3.3.x. Tests run in a Spring test context without needing to start a web server.

## 2. Testing Contract Before Writing Code

Assume the logged-in principal is `alice`; the filter expression used in both annotations is:

```java
"filterObject.owner() == authentication.name"
```

`filterObject` is **a single element** being evaluated; `authentication.name` is the authenticated user's name. `owner()` is the accessor of the Java `record Document` in the example. If using a JavaBean with `getOwner()`, you can access `filterObject.owner`.

Fixture data consists of:

| ID | Owner | Permitted when user = alice? |
| --- | --- | --- |
| A | alice | Yes |
| B | bob | No |
| C | alice | Yes |
| D | bob | No |

Expected outcome matrix:

| Test Case | Original Input / Result | After Filtering for Alice | What Must Be Verified |
| --- | --- | --- | --- |
| Empty | `[]` | `[]` | No error, no new elements created |
| All-owned | `[A, C]` | `[A, C]` | Valid elements are not mistakenly dropped |
| All-unauthorized | `[B, D]` | `[]` | All unauthorized elements are removed |
| Mixed | `[A, B, C, D]` | `[A, C]` | Exact IDs and relative order preserved |

A test that only calls `service.filter([])` and asserts `isEmpty()` is very weak: **even if the annotation is inactive, the service can still return an empty set**. Combine all four input classes and verify **exact element identities** with `containsExactly`, rather than using only `size()`.

There are three states that must not be confused:

1. **Unauthorized elements**: B and D are filtered out of Alice's list.
2. **Unauthenticated caller**: no valid authentication exists; test the authentication policy separately.
3. **Caller unauthorized for the whole operation**: a `@PreAuthorize` decision may throw `AccessDeniedException`.

`@PreFilter` and `@PostFilter` **do not throw** `AccessDeniedException` by default whenever an element is removed. If all elements are filtered out, the result may be an empty list and the method body may still run.

## 3. Setting Up the Test Environment

Method security requires calls to go **through a Spring-managed bean**. Instantiating with `new Service()` in a unit test bypasses the Spring proxy, so annotations will not execute. Use `@SpringJUnitConfig` to create an `ApplicationContext`, enable `@EnableMethodSecurity`, and inject the service; `@WithMockUser` populates `SecurityContextHolder` with a principal for the test.

This is a self-contained example in a small Gradle project. Required files:

```text
method-filtering-tests/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/MethodFilteringTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'method-filtering-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` provides the method security libraries, `spring-boot-starter-test` includes JUnit/AssertJ/Spring Test, and `spring-security-test` provides `@WithMockUser`. The example uses the Spring Boot BOM to align dependency versions, **without needing** a Spring Boot `main` application to run tests.

## 4. Complete Java 17+ Test File

Create `src/test/java/demo/MethodFilteringTest.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(MethodFilteringTest.SecurityConfig.class)
@WithMockUser(username = "alice", roles = "USER")
public class MethodFilteringTest {

    @Autowired
    FilteringService service;

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class SecurityConfig {
        @Bean
        public FilteringService filteringService() {
            return new FilteringService();
        }
    }

    public record Document(String id, String owner) { }

    public static class FilteringService {

        @PreFilter(
            value = "filterObject.owner() == authentication.name",
            filterTarget = "documents"
        )
        public List<String> accept(@P("documents") List<Document> documents) {
            // Receives the list already filtered by @PreFilter before entering the body.
            return documents.stream().map(Document::id).toList();
        }

        @PostFilter("filterObject.owner() == authentication.name")
        public List<Document> view(List<Document> source) {
            // @PostFilter filters the mutable result, keeping the source collection unchanged.
            return new ArrayList<>(source);
        }

        @PreAuthorize("hasRole('EDITOR')")
        public int editorOnlyCount(List<Document> documents) {
            return documents.size();
        }
    }

    private static Document doc(String id, String owner) {
        return new Document(id, owner);
    }

    // -------- @PreFilter --------

    @Test
    void preFilter_emptyCollection() {
        List<Document> input = new ArrayList<>();

        assertThat(service.accept(input)).isEmpty();
        assertThat(input).isEmpty();
    }

    @Test
    void preFilter_allOwned() {
        List<Document> input = new ArrayList<>(List.of(
            doc("A", "alice"),
            doc("C", "alice")
        ));

        assertThat(service.accept(input)).containsExactly("A", "C");
        assertThat(input).extracting(Document::id)
            .containsExactly("A", "C");
    }

    @Test
    void preFilter_allUnauthorized() {
        List<Document> input = new ArrayList<>(List.of(
            doc("B", "bob"),
            doc("D", "bob")
        ));

        assertThat(service.accept(input)).isEmpty();
        assertThat(input).isEmpty();
    }

    @Test
    void preFilter_mixed() {
        List<Document> input = new ArrayList<>(List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice"),
            doc("D", "bob")
        ));

        assertThat(service.accept(input)).containsExactly("A", "C");
        assertThat(input).extracting(Document::id)
            .containsExactly("A", "C");
    }

    // -------- @PostFilter --------

    @Test
    void postFilter_emptyCollection() {
        List<Document> source = List.of();

        assertThat(service.view(source)).isEmpty();
        assertThat(source).isEmpty();
    }

    @Test
    void postFilter_allOwned() {
        List<Document> source = List.of(
            doc("A", "alice"),
            doc("C", "alice")
        );

        assertThat(service.view(source)).extracting(Document::id)
            .containsExactly("A", "C");
        assertThat(source).extracting(Document::id)
            .containsExactly("A", "C");
    }

    @Test
    void postFilter_allUnauthorized() {
        List<Document> source = List.of(
            doc("B", "bob"),
            doc("D", "bob")
        );

        assertThat(service.view(source)).isEmpty();
        assertThat(source).extracting(Document::id)
            .containsExactly("B", "D");
    }

    @Test
    void postFilter_mixed() {
        List<Document> source = List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice"),
            doc("D", "bob")
        );

        assertThat(service.view(source)).extracting(Document::id)
            .containsExactly("A", "C");
        assertThat(source).extracting(Document::id)
            .containsExactly("A", "B", "C", "D");
    }

    // -------- Principal comparison and whole-method denial --------

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void sameMixedData_changesWithPrincipal() {
        List<Document> input = new ArrayList<>(List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice")
        ));

        assertThat(service.accept(input)).containsExactly("B");
        assertThat(service.view(List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice")
        ))).extracting(Document::id).containsExactly("B");
    }

    @Test
    void wholeMethodDenied_isDifferentFromElementFiltering() {
        assertThatThrownBy(() -> service.editorOnlyCount(
            List.of(doc("A", "alice"))
        )).isInstanceOf(AccessDeniedException.class);
    }
}
```

This file is a **complete test class**, with the Java `record` fixture, Spring configuration, and tested service placed together in one file so it can run standalone. Only one public test class matches the file name.

### Role of the Components

- `@EnableMethodSecurity` activates interceptors for `@PreFilter`, `@PostFilter`, and `@PreAuthorize`.
- `@SpringJUnitConfig` and `@Autowired` ensure tests call the Spring bean; testing a manually instantiated service with `new` will not prove annotations work.
- `@WithMockUser(username="alice")` creates the Alice principal for regular tests. Bob's test overrides the class-level annotation; the filter must change output based on the principal rather than a hardcoded name.
- `@PreFilter(filterTarget="documents")` specifies the parameter to filter; `@P("documents")` ensures Spring Security resolves the name even when compiled without the `-parameters` flag.
- `filterObject.owner()` calls the public accessor of `record Document` and compares against the username.
- `accept` returns IDs reaching **the method body**; `@PreFilter` filters a mutable `ArrayList` directly. Tests check both the return value and the list contents after the call.
- `view` creates `new ArrayList<>(source)`; `@PostFilter` modifies only the **returned** list, leaving the caller's immutable `source` list untouched.
- `editorOnlyCount` is a control using **`@PreAuthorize`**, because denying the whole call results in an exception rather than a filtered set.

### How to Run and Expected Outcome

In the directory containing `build.gradle`:

```bash
gradle test --tests demo.MethodFilteringTest
```

If using the Gradle Wrapper: on Linux/macOS run `./gradlew test --tests demo.MethodFilteringTest`, on Windows run `./gradlew.bat test --tests demo.MethodFilteringTest`.

Expect **10 passing tests** and the Gradle command to finish with `BUILD SUCCESSFUL`. This is an **expected** outcome, not stdout captured from an actual run. Open `build/reports/tests/test/index.html` to view results and stack traces of failing tests. For an existing project, just add the test class and any missing dependencies; there is no need to recreate the project.

## 5. Explaining Each Data State

### 5.1. Empty Set

With input `[]`, there are no elements to evaluate the expression against, so `@PreFilter` passes an empty list into the method and `@PostFilter` returns an empty list. No elements are "auto-generated". This does not prove permissions are configured properly, because the same result can happen when method security is disabled. You must also run all-unauthorized and mixed tests.

Separate business requirements: **accept an empty batch** vs. **reject an empty batch**. Spring Security does not replace business validation. An initially empty set differs from one that became empty after filtering everything out; in both cases the service may receive `[]`, so if distinguishing them is required, design an appropriate contract/validation before processing.

### 5.2. All Elements Unauthorized

Alice calls with `[B(bob), D(bob)]`. The filtered result is `[]`:

- `@PreFilter`: elements are removed **before entering the body**; the body may still execute with an empty list.
- `@PostFilter`: the body **already executed**, potentially having queried the database or performed side effects, before the result was filtered for the caller.

In both cases, **`AccessDeniedException` is not thrown by default** merely because no elements remain. If the requirement is to fail the entire batch when any unauthorized record appears, use a policy checking permissions for the whole list and block the operation early, such as an appropriate `@PreAuthorize`/service guard.

### 5.3. Mixed Data

Alice calls `[A, B, C, D]`. Two records A and C are authorized, while B and D are not; the output must be strictly `[A, C]` in the original order. Verify **both IDs and order**, not just `hasSize(2)`: `[B, D]` or `[A, A]` also have two elements but violate permissions.

This case has high fault-detection power: an inactive interceptor returns all four elements; a wrong expression might filter out everything or keep Bob's elements; a buggy implementation might reverse order or duplicate results.

### 5.4. All Elements Authorized

Input `[A, C]` for Alice must retain all of `[A, C]`. This case catches overly strict policies, wrong `owner` property names, or missing principals. Having this case prevents the all-unauthorized test from passing just because hardcoded logic always returns empty.

### 5.5. Switching Principals and Blocking Operations

Test `sameMixedData_changesWithPrincipal` runs as Bob on the same A/Alice, B/Bob, C/Alice data. Expected is only B. It forces the result to change with `authentication.name`.

Test `wholeMethodDenied_isDifferentFromElementFiltering` uses role USER to call a method requiring EDITOR and verifies `AccessDeniedException`. This is **whole-method authorization**, quite different from keeping a subset. If testing HTTP 403 status is needed, do so at the web layer with an appropriate mock request or token; method tests do not themselves return HTTP responses.

## 6. Expanding Edge Cases to Avoid Vulnerabilities

When a real system adds more data or complex container types, add tests according to the table below.

| Additional Case | Risk to Detect | Required Assertion |
| --- | --- | --- |
| Interleaved `[B,A,D,C]` | Filtering only first/last elements wrong, losing order | Output `[A,C]` |
| Same ID, different tenant/owner | Checking only ID while ignoring permission scope | Keep only records belonging to valid tenant and principal |
| No element matches a third user | Hardcoded policy or wrong SecurityContext | Empty result, none of Alice's/Bob's data |
| `null` element in collection | SpEL calling `owner()` on null | Clear policy: guard to drop or validation to reject |
| Filter target argument is `null` | Confusing null with empty list | Assert per validation/contract; do not assume `[]` by default |
| `List.of(...)` passed to `@PreFilter` | Collection does not support `remove` | Verify error or copy to `ArrayList` before calling |
| Multiple `List` parameters | Filtering the wrong list | `filterTarget` points to right name and other parameter is unchanged |
| `Map`, array, `Stream` | Differences in filtering, elements, and lifecycle | Write dedicated fixtures/assertions matching real types |
| Self-invocation `this.method()` | Call bypasses AOP proxy | Test production call path through Spring bean |
| Paginated or large dataset results | `@PostFilter` filtering after query skewing totals/pages | Check IDs, page count, total count, and permission-constrained query |

For example, if the requirement is to **drop null elements**, replace the filter expression with:

```java
@PreFilter(
    value = "filterObject != null and filterObject.owner() == authentication.name",
    filterTarget = "documents"
)
```

This is an **illustrative annotation** snippet, not a standalone Java program. It changes the policy compared to the original example: before adding it, confirm whether business rules want to **drop** `null` or **report an error**. Similarly, if a document carries a client-declared `owner`, simply comparing against that field is insufficient for authorization; check trusted server-side data.

## 7. How to Test Across Application Layers

**Service integration tests** are the primary layer for verifying method security. Keep fixtures small, define owners explicitly, and call the Spring-injected service. When verifying side effects is needed, use mocks/repository spies or database tests to confirm:

- Unauthorized data **does not reach write business logic** when using `@PreFilter`.
- Data returned to callers has passed `@PostFilter`; cases with side effects before filtering must be controlled separately.
- One run as Alice does not alter the result of a run as Bob via shared cache or state.

**HTTP/MockMvc tests** are a supplementary layer to verify how endpoints turn results into JSON and exceptions into status codes. `@WithMockUser` only sets `SecurityContext` on the test thread; if a test sends HTTP to a real server running on another thread, authenticate **the request** with an appropriate mechanism. Do not rely on `@WithMockUser` on a test method to assume an HTTP token was sent.

**Repository/tenant tests** must verify data restriction right from the query. `@PostFilter` is in-memory filtering **after the method produces a result**, so it does not replace owner/tenant-constrained queries; it can skew pagination metrics and cause unnecessary data loading. For sensitive data, test conditions simultaneously at the database, service, and response layers.

## 8. Common Testing Pitfalls

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Empty test passes yet unauthorized items leak through | Empty does not prove the interceptor ran | Add mixed, all-owned, and all-unauthorized tests |
| Annotation does not filter | Missing `@EnableMethodSecurity`, used `new`, self-invocation | Use Spring context and proxied bean |
| `UnsupportedOperationException` | `@PreFilter` needs to remove elements from immutable collection | Use `new ArrayList<>(...)` |
| SpEL `owner()` error | Wrong element type, missing accessor, or null value | Adjust expression/fixture and null policy |
| Test only asserts `size() == 2` | The two kept elements could be B and D | Assert `containsExactly("A", "C")` |
| Returned data is right but source input mutated unexpectedly | `@PostFilter` filtered a shared collection | Return a mutable copy when preserving source |
| Expected `AccessDeniedException` for each dropped record | Confused element filtering with method denial | Design a separate whole-method authorization test |
| Test passes for Alice, fails for Bob | Hardcoded policy or wrong context | Test a second principal; check authentication name |
| Data API returns empty yet write operation still occurred | `@PostFilter` runs after method body | Block writes before side effects |
| HTTP test lacks expected principal | Test auth not attached to real request | Use MockMvc/client/request auth mechanisms |

## 9. Acceptance Checklist

1. Test suite covers **empty, all-authorized, all-unauthorized, and mixed** for every annotation used.
2. Has at least **two principals**, data with clear owner/tenant, and assertions by **ID + order**, not just count.
3. `@PreFilter` uses a mutable collection, verifies contents actually reaching the method body; `@PostFilter` verifies the result received by caller and state of source data.
4. Tests obtain a **Spring-managed bean** via injection, enable `@EnableMethodSecurity`, and use `@WithMockUser` or equivalent test security context.
5. If business rules require whole-operation denial, have a separate test for `@PreAuthorize`/policy with the right exception; do not expect filtering annotations to return 403 on their own.
6. Practical concerns such as null, immutable, tenant, multiple lists, pagination, and side effects have appropriate test cases.

**Takeaway:** Empty sets verify boundary handling, all-unauthorized sets verify removal, all-authorized sets verify no over-filtering, and mixed sets verify **both directions simultaneously**. All four scenarios must work together to prove method filtering executes properly under a real principal in Spring Test.

## References

- Spring Security Reference — Method Security, `@PreFilter` and `@PostFilter`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference — Testing Method Security and `@WithMockUser`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security API — `@PreFilter`, `filterTarget`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreFilter.html
