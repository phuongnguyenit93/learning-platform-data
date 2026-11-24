# `@PreFilter` — Filtering Input Elements Before Processing

## 1. Goal and Problem Statement

Suppose an API receives multiple documents to update. User `alice` submits three documents: `#1` belongs to `alice`, `#2` belongs to `bob`, `#3` belongs to `alice`. The service layer should only **receive the elements that the caller is permitted to process**. If business requirements allow partial batch processing, Spring Security provides `@PreFilter` to remove elements that do not satisfy the condition **before the method body runs**.

After this lesson, you will be able to:

- Explain how Spring AOP/Method Security intercepts invocations and filters parameters.
- Write SpEL expressions based on `filterObject`, `authentication`, and authorization rules.
- Select the right parameter with `filterTarget`; understand how `Collection`, `Map`, arrays, and `Stream` are filtered.
- Avoid immutable collection errors, proxy bypass, and using user-supplied data as proof of ownership.
- Test actual results when invocations pass through a Spring bean.

**Scope:** Spring Security's `@PreFilter` for method invocations; this is not a Servlet Filter in the HTTP filter chain, nor does it automatically filter data directly inside SQL queries.

## 2. What Does `@PreFilter` Do?

Conceptual example:

```java
@PreFilter("filterObject.owner() == authentication.name")
public List<Document> process(List<Document> documents) {
    // documents only contains the Document elements that passed the filter expression
    return List.copyOf(documents);
}
```

Given the list `[Doc(1, alice), Doc(2, bob), Doc(3, alice)]` and the logged-in user `alice`, the method receives the corresponding list `[Doc(1, alice), Doc(3, alice)]`.

- `@PreFilter` is placed on a Spring-managed method. It requires a **SpEL expression returning a boolean** for each element.
- `filterObject` represents **the current element** being evaluated.
- `authentication` is the `Authentication` object in the security context of the invocation; `authentication.name` is the logged-in user's name.
- Result `true`: keep the element. Result `false`: remove the element from the input passed to the method.
- The method **is still invoked** with the remaining elements, even when the list is empty. Filtering out an element **does not mean** throwing `AccessDeniedException` for the entire invocation.

Key differences to remember:

| Tool | Timing | Primary Behavior |
| --- | --- | --- |
| `@PreFilter` | Before running the method body | Filters elements of an **input parameter** |
| `@PreAuthorize` | Before running the method body | Allows or denies the **entire invocation** |
| `@PostFilter` | After the method body returns | Filters elements in the **return value** |
| `@PostAuthorize` | After the method body runs | Checks permission on the **result/invocation** |

For example, if **every** document in the batch must be authorized for update, design a mechanism to reject the entire batch using an appropriate authorization check. If the API accepts partial processing, `@PreFilter` is more suitable, but you should clearly document the element-skipping behavior.

## 3. Execution Flow

```text
Controller / another service
         |
         v
Spring AOP proxy of the service
         |
         v
@PreFilter interceptor
   - identify the parameter to filter
   - obtain Authentication
   - iterate elements, set filterObject
   - evaluate SpEL, keep matching elements
         |
         v
Service method body
   (receives filtered input)
         |
         v
Result / subsequent interceptors
```

When `@EnableMethodSecurity` is enabled, Spring registers the method security mechanism. In the default model, `@PreFilter` is handled by `PreFilterAuthorizationMethodInterceptor` in the Spring AOP chain. The key point is that **the invocation must go through the proxy**: calling `this.process(...)` from another method in the same bean generally bypasses proxy-based interceptors and may therefore skip the annotation.

`@PreFilter` does not replace authentication: a valid `Authentication` must exist in the security context. For HTTP requests, Spring Security typically establishes this context from login/token mechanisms. When calling from jobs, events, or tests, the corresponding security context must be set.

## 4. Enabling Method Security

Add Spring Security to a Spring Boot application and enable method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

You can place `@EnableMethodSecurity` directly on the `@SpringBootApplication` class as shown in the full example in the next section. Simply adding the Spring Security dependency **does not automatically enable** method security. With the default configuration, the annotation group `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` is supported. The older API `@EnableGlobalMethodSecurity` belongs to the previous configuration style.

Place annotations on methods of a Spring bean, prefer `public` methods, and invoke them through a Spring-injected bean. Manually calling `new DocumentService()` does not create a security proxy.

## 5. Runnable Example with Java 17+ and Spring Boot 3.x

The example below simulates document batch processing without needing an HTTP server or database. It creates a test `Authentication` in `CommandLineRunner`, then calls a **Spring-managed service**. The demo uses Spring Boot `3.3.13` to pin dependencies; real-world projects should choose a supported Spring Boot branch.

Create a Gradle project with the following structure:

```text
prefilter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PrefilterDemoApplication.java
    │   └── DocumentService.java
    └── test/java/demo/
        └── DocumentServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'prefilter-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.List;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

record Document(long id, String owner) {}

@Service
public class DocumentService {

    @PreFilter("filterObject.owner() == authentication.name")
    public List<Document> accept(List<Document> documents) {
        // Only work with elements that passed validation.
        return List.copyOf(documents);
    }
}
```

`Document` is a Java record: `owner()` returns the owner, and `id()` returns the document ID. In SpEL, `filterObject.owner()` calls the record accessor. You should not assume that an `owner` field in a client-submitted DTO is proof of ownership; Section 9 explains this limitation.

**`src/main/java/demo/PrefilterDemoApplication.java`:**

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PrefilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrefilterDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DocumentService service) {
        return args -> {
            var auth = new UsernamePasswordAuthenticationToken(
                "alice",
                "demo-only",
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );
            SecurityContextHolder.getContext().setAuthentication(auth);

            try {
                List<Document> submitted = new ArrayList<>(List.of(
                    new Document(1, "alice"),
                    new Document(2, "bob"),
                    new Document(3, "alice")
                ));

                List<Document> accepted = service.accept(submitted);
                System.out.println("Accepted IDs: "
                    + accepted.stream().map(Document::id).toList());
                System.out.println("Remaining input IDs: "
                    + submitted.stream().map(Document::id).toList());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }
}
```

Run in a project with the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`; if there is no Wrapper yet but Gradle is installed, you can use `gradle bootRun`. The two lines printed by the demo code (excluding Spring Boot logs) are:

```text
Accepted IDs: [1, 3]
Remaining input IDs: [1, 3]
```

Explanation: the interceptor evaluates the three elements before `accept` runs. `#2` does not have an owner equal to `authentication.name`, so it is removed. The original `ArrayList` in the example is also mutated by the filtering process; this is a detail to account for when input data is reused.

**Do not use a manually constructed `UsernamePasswordAuthenticationToken` like above to authenticate client requests.** Its purpose is solely to construct a security context in the demo program; in a real application, you must use an authentication flow configured and verified by Spring Security.

## 6. SpEL Syntax and Selecting the Filter Parameter

### 6.1. Per-Element Conditions

Example with a method taking a `List<Document>` parameter:

```java
@PreFilter("filterObject.owner() == authentication.name")
public void process(List<Document> documents) {
    // ...
}
```

You can combine conditions to keep only valid elements:

```java
@PreFilter(
    "filterObject != null and " +
    "filterObject.owner() == authentication.name"
)
public void process(List<Document> documents) {
    // ...
}
```

The expression must return a boolean value. If dereferencing a property on `null`, calling a misspelled method, or throwing an exception during SpEL evaluation occurs, the invocation may fail; it does not automatically turn programming errors into a safe security decision. Expressions should be simple, testable, and side-effect-free.

`hasAuthority('documents:write')` and `hasRole('ADMIN')` can appear in security expressions, but using a separate `@PreAuthorize` to **deny invocations lacking overall permission** is usually clearer than filtering out all elements and still running the method.

### 6.2. Multiple Parameters: Using `filterTarget`

If a method has multiple parameters, especially multiple lists, you must explicitly identify the list to filter using `filterTarget`. Ensure Spring can discover parameter names via the `-parameters` compiler flag or a naming annotation such as `@P`:

```java
import java.util.List;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreFilter;

@PreFilter(
    value = "filterObject.owner() == authentication.name",
    filterTarget = "documents"
)
public List<Document> acceptBatch(
        String batchId,
        @P("documents") List<Document> documents) {
    return List.copyOf(documents);
}
```

`batchId` is not filtered, while `documents` is the target. When the parameter cannot be resolved or there are multiple filterable objects and no target is specified, the configuration may fail at invocation time. Do not rely on parameter names that are stripped at compile time.

### 6.3. `Collection`, `Map`, Arrays, `Stream`

Modern Spring Security documentation describes support for `Collection`, array, `Map`, and open `Stream`. Distinguish the shape of the iterated element:

| Input Type | `filterObject` Represents | Example Expression |
| --- | --- | --- |
| `List<Document>` / `Collection<Document>` | A `Document` | `filterObject.owner() == authentication.name` |
| `Document[]` | A `Document` | `filterObject.owner() == authentication.name` |
| `Map<String, Document>` | A `Map.Entry` | `filterObject.value.owner() == authentication.name` |
| `Stream<Document>` still usable | A `Document` | `filterObject.owner() == authentication.name` |

With `Map`, you must inspect `filterObject.value` (or `key` if the policy is tied to the key) because the evaluated element is an entry:

```java
@PreFilter("filterObject.value.owner() == authentication.name")
public void saveByCode(java.util.Map<String, Document> byCode) {
    // Non-matching entries have already been removed.
}
```

For `Collection` and `Map`, prefer **mutable** structures such as `ArrayList` or `LinkedHashMap`; the filtering process may need to remove elements/entries. `List.of(...)`, `Stream.toList()`, `Collections.unmodifiableList(...)`, `Map.of(...)`, and fixed-size lists from `Arrays.asList(...)` are not safe inputs when element removal is required; they may cause `UnsupportedOperationException`. Do not assume arrays/streams have the same in-place mutation characteristics as `ArrayList`; test against the exact Spring Security version in use, and do not reuse a `Stream` that has already been consumed/closed.

### 6.4. When to Combine Annotations?

A service may require a general operation permission **and** per-element permission filtering:

```java
@PreAuthorize("hasAuthority('documents:write')")
@PreFilter("filterObject.owner() == authentication.name")
public void updateAllowed(List<Document> documents) {
    // ...
}
```

`@PreAuthorize` checks the invocation's permission, while `@PreFilter` restricts the input data. They are separate interceptors; in the default advisor chain, the `@PreFilter` interceptor has an earlier order than `@PreAuthorize`, so do not rely on the assumption that rejecting the entire invocation will always happen before any mutation to the input collection. If atomicity and leaving input unchanged upon denial are hard requirements, design and test this boundary explicitly.

## 7. Testing Through the Spring Proxy

Create the file **`src/test/java/demo/DocumentServiceTest.java`**:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentServiceTest {

    @Autowired
    DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void removesOtherOwnersBeforeServiceRuns() {
        var input = new ArrayList<>(List.of(
            new Document(1, "alice"),
            new Document(2, "bob"),
            new Document(3, "alice")
        ));

        var result = service.accept(input);

        assertEquals(List.of(1L, 3L),
            result.stream().map(Document::id).toList());
        assertEquals(List.of(1L, 3L),
            input.stream().map(Document::id).toList());
    }

    @Test
    @WithMockUser(username = "alice")
    void invokesServiceWithEmptyListWhenNothingMatches() {
        var input = new ArrayList<>(List.of(
            new Document(4, "bob")
        ));

        assertTrue(service.accept(input).isEmpty());
        assertTrue(input.isEmpty());
    }
}
```

Run:

```bash
./gradlew test
```

`@WithMockUser` comes from `spring-security-test` and creates a security context in tests. Using `@Autowired DocumentService` ensures the invocation goes through the Spring bean/proxy. `new DocumentService().accept(...)` only tests plain Java and **does not test** the `@PreFilter` mechanism.

In addition to the two cases above, you should test different users, empty lists, immutable collections, `null` values, multiple parameters with `filterTarget`, users lacking sufficient permissions when combining `@PreAuthorize`, and self-invocation if the architecture involves internal calls.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| All elements still reach the service | Forgot `@EnableMethodSecurity`; called via `new` or internal call via `this` | Enable method security, invoke through Spring bean/proxy |
| Throws `UnsupportedOperationException` | Passed `List.of`, `Stream.toList`, `Arrays.asList`, or a collection that disallows removal | Create a copy `new ArrayList<>(input)` at the call boundary |
| Cannot resolve parameter | Multiple collection-typed parameters or parameter name unknown | Specify `filterTarget`; use `@P` or compile with `-parameters` |
| SpEL evaluation error | Wrong accessor, `null` element, unexpected data type | Verify expression on real elements; handle `null` |
| Runs even when no element is allowed | `@PreFilter` filters, does not reject the entire request by default | Define empty-batch handling clearly; use invocation-level authorization if needed |
| Result is filtered but data was already processed | Confused `@PostFilter` with `@PreFilter` | Use `@PreFilter` for input parameters; do not use `@PostFilter` as a shield against unauthorized writes |
| Unintended data loss in caller's variable | Input collection was mutated during filtering | Use a mutable copy and carefully consider the API contract |

A particularly dangerous mistake is calling `@PreFilter("filterObject.owner() == authentication.name")` on a DTO where the **client sets** the `owner` field, and then treating that as a guarantee of write permission on the real record. An attacker can send `owner="alice"` even though the ID points to someone else's document. Authorization decisions must rely on trusted data sources (permissions in the system, records fetched from the database or an authorization service), and the update layer must re-bind the ID to a principal authorized to perform the operation.

## 9. Secure Design and Performance

1. **Choose batch handling behavior:** If processing must be all-or-nothing, reject the entire batch using an appropriate authorization mechanism. If partial processing is allowed, document clearly how the API reports accepted/skipped elements. Do not let silent filtering create a false impression that every item was updated.
2. **Do not trust self-declared data:** For updates by ID, check ACL/ownership on server-managed data, for example an expression calling an authorization bean `@documentAcl.mayWrite(authentication, filterObject.id())` (this is an integration idea; you must define the corresponding bean and method yourself). Better yet, enforce ownership directly in the query/update statement where appropriate.
3. **Manage collections:** Create a mutable copy if the caller still needs the original list, e.g. `new ArrayList<>(request.documents())`. If data must not be mutated, design the API to return validation results separately rather than relying on mutation.
4. **Do not treat filtering as input validation:** Bean Validation, batch size limits, duplicate ID detection, transactions, and error handling are separate responsibilities.
5. **Evaluate cost:** SpEL runs for every element. Calling a database or external service for each `filterObject` can cause an N+1 problem; for large batches, consider querying by owner/permission or batch authorization.
6. **Test through the real path:** Check `Authentication`, proxy, annotation order, mutated input lists, and data-layer protection. `@PreFilter` does not itself provide isolation or transactions.
7. **Distinguish web and method layers:** HTTP rules (`SecurityFilterChain`) check requests/routes; method security protects operations in services. Policies should be placed at the appropriate layer and can be combined.

## 10. Self-Check Knowledge

1. User `alice` submits three documents with owners `alice`, `bob`, `alice`. What does the condition `filterObject.owner() == authentication.name` result in? **Only the two documents belonging to `alice` enter the method body.**
2. If no element satisfies the expression, does the method automatically return HTTP 403? **No.** The method is invoked with the filtered input (usually empty), unless another mechanism rejects the invocation or an error occurs.
3. Why might `List.of(...)` break the invocation? **It is an unmodifiable list that does not allow element removal**, whereas collection filtering may need to remove elements.
4. When passing `Map<String, Document>`, what should be referenced? **`filterObject.value`** to get the `Document` from each `Map.Entry`.
5. Why is checking a client-submitted `owner` insufficient for security? **The client can forge that field**; authorization must rely on server-verified ownership/permission information.

## References

- [Spring Security — Method Security (official documentation)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html), section *Filtering Method Parameters with `@PreFilter`*.
- [Spring Security — `@PreFilter` API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/access/prepost/PreFilter.html).
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html).

**Key takeaway:** `@PreFilter` is a SpEL-based **method input** filter that works via Spring Method Security, can mutate collections, and normally still allows the method to run after removing elements. Use it when business rules genuinely accept partial filtering; for write permissions, always verify permissions against a trusted source.