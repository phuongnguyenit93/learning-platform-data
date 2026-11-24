# Testing `@PreFilter`, `@PostFilter`, and filtered collection contents

> Scope: Spring Security Method Security in a Spring application using proxies/AOP, Java 17+, JUnit 5, and `spring-security-test`. The goal is to prove **which elements are allowed to enter a method** and **which elements actually reach the caller**; checking only HTTP 200 or element counts is not enough.

## 1. Mechanism to understand before writing tests

When `@EnableMethodSecurity` is configured, Spring Security creates interceptors to handle annotations on **Spring-managed beans**:

| Annotation | Timing | Filtered data | What to assert in tests |
| --- | --- | --- | --- |
| `@PreFilter` | Before executing the method body | A supported collection/array/map/stream argument | Inside the method, only elements satisfying the expression are visible |
| `@PostFilter` | After the method body produces a result, before returning to the caller | Elements in the supported return value | The caller receives only permitted elements, with exact IDs/contents |
| `@PreAuthorize` | Before running the method | Decides whether the method may be called at all | When denied, raises an access error instead of silently removing elements |

For example, the expression `filterObject.owner == authentication.name` is evaluated **for each element**. `filterObject` is the element under evaluation; `authentication.name` is the current principal's name in `SecurityContext`. For `Map<K,V>`, the element being filtered is an entry, so `filterObject.value.owner` is commonly used. `@PreFilter` can specify the target argument via `filterTarget` when a method has multiple parameters.

Filtering **is not synonymous with rejecting the entire request**: a list consisting solely of unauthorized elements normally becomes an empty list; the method can still be invoked. To reject unauthenticated callers or callers lacking permission to invoke the method, add rules such as `@PreAuthorize("isAuthenticated()")` or `@PreAuthorize("hasAuthority('document:read')")` per business requirements.

Typical inspection flow:

```text
@WithMockUser("alice") creates SecurityContext
                  |
                  v
Caller -> Spring proxy -> @PreFilter -> service body -> @PostFilter -> Caller
                             |                               |
                  check input entering body       check output returned
```

**Important boundary:** Calling `new FilterService()` directly does not go through the Spring proxy; annotations may not be applied. Tests that meaningfully verify enforcement must obtain the bean from ApplicationContext and enable Method Security.

## 2. Designing tests from predictable data

Suppose the service manages documents `(id, owner)`:

| ID | Owner | Expected outcome for `alice` |
| --- | --- | --- |
| `A1` | `alice` | Keep |
| `B1` | `bob` | Remove |
| `A2` | `alice` | Keep |

With the same input set in that order:

- `@PreFilter`: code inside `service.accept(...)` must process **exactly** `["A1", "A2"]`.
- `@PostFilter`: `service.visibleDocuments()` may construct all three objects, yet the caller receives only `["A1", "A2"]`.
- Principal `bob` receives `["B1"]`; principal `charlie` receives `[]`.
- When all elements are permitted, all are kept; when no element is permitted, an empty collection is returned.
- When returning a `Map`, check the remaining **keys and values**, not just the size.

Assertions like `assertEquals(2, result.size())` can miss bugs when the service returns the wrong two objects. Always compare IDs, owners, or full objects per the contract and verify sensitive items are no longer present.

## 3. Runnable integration example (Spring Test, JUnit 5)

In a Spring Boot project using Gradle, Spring Security, Spring Test/JUnit, and `spring-security-test` are required. If the project already declares the matching starters, do not duplicate them. Typical `dependencies` block (versions managed by Spring Boot BOM/plugin):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create **one complete file** `src/test/java/com/example/security/MethodFilteringTest.java`. The example builds a compact Spring context with `@SpringJUnitConfig`; no web server or controller needs to be started.

```java
package com.example.security;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(MethodFilteringTest.TestConfig.class)
public class MethodFilteringTest {

    @Autowired
    FilterService service; // Bean provided by Spring: calls pass through proxy

    @Test
    @WithMockUser(username = "alice")
    void preFilter_removesOtherOwnersBeforeServiceRuns() {
        List<Document> input = new ArrayList<>(List.of(
                new Document("A1", "alice"),
                new Document("B1", "bob"),
                new Document("A2", "alice")));

        // accept() reads the argument directly inside the method body.
        assertEquals(List.of("A1", "A2"), service.accept(input));
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilter_allForeignDocumentsYieldsEmptyInput() {
        List<Document> input = new ArrayList<>(List.of(
                new Document("B1", "bob")));

        assertEquals(List.of(), service.accept(input));
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilter_allOwnedDocumentsAreKept() {
        List<Document> input = new ArrayList<>(List.of(
                new Document("A1", "alice"),
                new Document("A2", "alice")));

        assertEquals(List.of("A1", "A2"), service.accept(input));
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilter_keepsOnlyAliceDocuments() {
        List<Document> result = service.visibleDocuments();

        assertEquals(List.of("A1", "A2"), ids(result));
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilter_changesWithAuthenticatedPrincipal() {
        List<Document> result = service.visibleDocuments();

        assertEquals(List.of("B1"), ids(result));
    }

    @Test
    @WithMockUser(username = "charlie")
    void postFilter_noOwnedDocumentYieldsEmptyResult() {
        List<Document> result = service.visibleDocuments();

        assertEquals(List.of(), ids(result));
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilter_mapRemovesUnauthorizedEntries() {
        Map<String, Document> result = service.visibleMap();

        assertEquals(List.of("first", "third"),
                new ArrayList<>(result.keySet()));
        assertEquals(List.of("A1", "A2"),
                result.values().stream().map(Document::getId).toList());
    }

    private static List<String> ids(List<Document> documents) {
        return documents.stream().map(Document::getId).toList();
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class TestConfig {
        @Bean
        FilterService filterService() {
            return new FilterService();
        }
    }

    public static class FilterService {

        @PreFilter("filterObject.owner == authentication.name")
        public List<String> accept(List<Document> documents) {
            // This is the data the service ACTUALLY receives after @PreFilter.
            return documents.stream().map(Document::getId).toList();
        }

        @PostFilter("filterObject.owner == authentication.name")
        public List<Document> visibleDocuments() {
            // Original result set intentionally contains a record the user cannot view.
            return new ArrayList<>(List.of(
                    new Document("A1", "alice"),
                    new Document("B1", "bob"),
                    new Document("A2", "alice")));
        }

        @PostFilter("filterObject.value.owner == authentication.name")
        public Map<String, Document> visibleMap() {
            Map<String, Document> all = new LinkedHashMap<>();
            all.put("first", new Document("A1", "alice"));
            all.put("second", new Document("B1", "bob"));
            all.put("third", new Document("A2", "alice"));
            return all;
        }
    }

    public static class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }
}
```

Run from the root directory of a project with Gradle Wrapper:

```bash
./gradlew test --tests "com.example.security.MethodFilteringTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.security.MethodFilteringTest"
```

**Expected result:** 7 green tests. With the fixed fixtures in the example, the results to verify in order are `["A1","A2"]`, `[]`, `["A1","A2"]`, `["A1","A2"]`, `["B1"]`, `[]`, and the map retaining only keys `first`, `third`. These are **assertion expectations**, not stdout of a program with `main`; JUnit/Gradle displays logs differently depending on configuration.

Why these tests truly verify security:

1. `@SpringJUnitConfig` initializes the Spring context and retrieves `FilterService` via `@Autowired`; `@EnableMethodSecurity` activates the interceptor.
2. `@WithMockUser(username = "alice")` sets up `Authentication` per test and Spring Test cleans up `SecurityContext` afterward. No real login, JWT creation, or MockMvc setup is needed solely to test method security.
3. In `accept`, converting to IDs happens **inside the method body**: if `@PreFilter` did not run, the first test would also return `"B1"` and fail.
4. In `visibleDocuments`, the method intentionally builds three documents while the assertion sits **after the proxy call**: if `@PostFilter` did not run, the caller would also receive `"B1"` and the test would fail.
5. `visibleMap` uses `LinkedHashMap` to observe keys in insertion order; the map expression must access `filterObject.value.owner`.

## 4. Proving exact contents, boundaries, and filtered results

A strong test suite should follow a consistent **Given–When–Then** structure:

- **Given:** specify the principal, set of IDs, and owners; intentionally mix allowed and disallowed items and preserve input order.
- **When:** call the **Spring bean through its proxy** with a mutable list when testing `@PreFilter`, or call a method returning mixed data when testing `@PostFilter`.
- **Then:** assert the **exact** set of IDs/owners/keys, empty conditions, and the absence of items belonging to other owners. If ordering is part of the API contract, assert ordering as well.
- **For `@PreFilter`:** prefer returning or recording a snapshot **right inside the method body** (like `accept`) to confirm the argument was already filtered *before* business logic. Asserting the caller's input after the call alone can couple tests to collection mutation details.
- **For `@PostFilter`:** compare the data the caller actually receives, not just what a repository/mock produced. A repository returning all three records does not mean the caller is allowed to see all three.

Minimum test matrix:

| Principal | Input/raw result | Inspection point | Expected |
| --- | --- | --- | --- |
| `alice` | `A1, B1, A2` | Input inside service (`@PreFilter`) | `A1, A2` |
| `alice` | `B1` | Input inside service | Empty, method still executes |
| `alice` | `A1, A2` | Input inside service | Keeps both |
| `alice` | `A1, B1, A2` | Caller output (`@PostFilter`) | `A1, A2` |
| `bob` | `A1, B1, A2` | Caller output | `B1` |
| `charlie` | `A1, B1, A2` | Caller output | Empty |
| `alice` | Map `first→A1, second→B1, third→A2` | Key + value output | Only `first→A1, third→A2` |

You can add tests with **two documents sharing the same owner but different IDs** (already covered by `A1`, `A2`) to ensure logic does not keep only the first match; test empty/null records, multiple authorities, sensitive properties, and ordering if required by business rules. Each case needs clear expectations; do not assume the annotation will throw `AccessDeniedException` merely because every element was filtered out.

## 5. Advanced scenarios and boundaries to test

### Selecting a parameter for `@PreFilter`

When a method has multiple parameters, you can specify the target argument explicitly:

```java
@PreFilter(value = "filterObject.owner == authentication.name",
           filterTarget = "documents")
public void importBatch(String batchId, List<Document> documents) {
    // documents has already been filtered before the body runs
}
```

This is an **illustrative snippet inside a service**, not a standalone program. For Spring to recognize the parameter name `documents`, ensure Java is compiled with `-parameters` (or use the parameter-name declaration mechanism supported by your Spring Security version). Do not guess names when multiple collections could be the filter target.

### `Map`, array, and `Stream`

Current Spring Security documentation notes support for collections, arrays, maps, and streams with `@PreFilter`/`@PostFilter`; verify behavior on the **running version**. When filtering a `Map`, `filterObject` is an entry, so you typically write `filterObject.value.owner`, as shown in the test. For `Stream`, use only an open stream and remember a stream can be consumed only once. For arrays, test the exact post-filter elements and return type of your version. Do not test only collections and assume every container shares identical mutation details.

### Unmodifiable collections and side effects

For `@PreFilter` tests, create `new ArrayList<>(...)` rather than passing `List.of(...)` directly and assuming elements can always be removed: depending on the version/execution path, unsupported collection modifications can fail. For `@PostFilter`, return `new ArrayList<>(...)` in fixtures and assert **the result seen by the caller**. If a service writes to a DB, sends messages, or calls APIs before `@PostFilter` applies, output filtering **does not undo** those side effects. Nor does `@PostFilter` replace query/repository filtering: for large datasets or pagination, push authorization criteria down to the data layer and test query boundaries, counts, and page metadata as well.

### Principal, authorization, and proxy

`@WithMockUser` fits when expressions depend on username/authorities. If expressions use a custom principal or claims, use `@WithUserDetails` or `@WithSecurityContext` to construct the right `Authentication` type. `roles = "ADMIN"` generates authority `ROLE_ADMIN`, whereas `authorities = "document:read"` uses the exact string; do not interchange them. Enable `@EnableMethodSecurity` in test config and invoke the bean via Spring; internal calls `this.otherSecuredMethod()` within the same bean normally bypass the proxy interceptor (self-invocation). Test the actual call path used by the application.

### Do not confuse filtering with access denial

- Per-element filtering: failing the expression drops elements; the collection may become empty.
- Blocking the entire method: use `@PreAuthorize` or corresponding authorization to assert exceptions when privileges are missing.
- For HTTP endpoints, also test serialization/responses if you need to guarantee JSON omits sensitive records; standalone method security tests verify the **service boundary** and do not automatically prove all controller mappings are safe.

## 6. Common pitfalls and how to detect them

| Symptom | Common cause | Fix/test |
| --- | --- | --- |
| Test still passes even if `@PreFilter` is removed | Asserting only count or mocking already-filtered data | Include `bob` records in input; assert ID snapshot **inside** service |
| Test still passes even if `@PostFilter` is removed | Mock repository only returns permitted documents | Intentionally return mixed data from service; assert exact caller output IDs |
| All elements returned despite annotation | Used `new`/self-invocation, missing `@EnableMethodSecurity` | Inject Spring bean via `@Autowired`; check proxy |
| SpEL error when multiple lists exist | `filterTarget` unspecified or parameter names missing | Specify target accurately, compile with `-parameters` |
| `@PreFilter` fails on immutable list | Fixture used `List.of(...)` directly | Use `new ArrayList<>(List.of(...))` |
| Map filtered incorrectly | Used `filterObject.owner` on entry | Use `filterObject.value.owner`, assert both keys and values |
| Test confuses `403` with empty result | Treating filtering as full-method denial authorization | Separate `@PreAuthorize` tests from `@PreFilter/@PostFilter` tests |
| Information leak via count/pagination | Filtering list only in service layer after query | Enforce privilege criteria in query and test metadata/API separately |

## 7. Acceptance checklist

1. `@EnableMethodSecurity` is present, the bean is genuinely created by Spring, and tests use `spring-security-test`.
2. Fixtures include at least one permitted element and one filtered-out element; include all-permitted and all-filtered-out tests.
3. `@PreFilter`: prove data is **already filtered when the method body begins executing**.
4. `@PostFilter`: prove the caller receives the **exact set of IDs/owners/map entries** after filtering.
5. Changing the principal for the same fixture changes the outcome predictably.
6. Do not confuse an empty collection with access denied, nor confuse unit tests calling an object directly with real interceptor tests.
7. Tests clearly expose a contract: check ordering if the API promises ordering; for large data/pagination, verify authorization at the data layer.

## Reference documentation

- [Spring Security — Method Security (filtering parameters and results)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — `@WithMockUser` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
