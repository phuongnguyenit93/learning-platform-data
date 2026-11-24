# @PostFilter in Spring Security: Filtering Result Collections by Per-Element Permission

## 1. Goal and Use Cases

In a multi-user application, a service method may return multiple records while each user is only allowed to see a subset. For example, `DocumentService.findAll()` returns three documents: documents 1 and 3 belong to `alice`, and document 2 belongs to `bob`. When `alice` calls the method, the valid result includes only documents 1 and 3.

`@PostFilter` is a **Spring Security Method Security** annotation used to **filter each element of the return value after the method has executed**. Each element is evaluated using a Spring Expression Language (SpEL) expression. Elements yielding `true` are retained; elements yielding `false` are removed from the result collection received by the caller.

This is a form of **element-level authorization**, commonly encountered with lists of documents, orders, profiles, owner-scoped resources, or tenant-partitioned data.

**Distinguish three questions:**
- "Is the user allowed to call this method?" → `@PreAuthorize`, evaluated before execution.
- "Is the user allowed to receive this entire single object?" → `@PostAuthorize`, evaluates the result and may deny it.
- "Which elements in the result collection is the user allowed to receive?" → `@PostFilter`, keeps elements matching the condition.

`@PostFilter` **does not turn unauthorized results into a 403 error per element**. If no elements are permitted to be viewed, the filtered list is usually empty. If the entire invocation must be denied, combine it with a check such as `@PreAuthorize`.

## 2. Mechanism and SpEL Expressions

To use annotations in a proxy-based Spring Security servlet application, enable Method Security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` enables `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` by default. Adding the Spring Security dependency alone **does not automatically enable Method Security** in Spring Boot. If `@EnableMethodSecurity` is already placed on the `@SpringBootApplication` class, there is no need to create a second config.

Basic syntax example:

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Document> findAll() {
    // Returns a list of Documents for the filter to evaluate each element.
}
```

This is a **method signature illustration**, not a standalone Java class. In the expression:
- `filterObject`: **the current element** as Spring Security iterates over the result. For a `List<Document>`, it is each `Document`.
- `filterObject.owner`: reads the JavaBean property `owner` (typically via `getOwner()`) of the current element.
- `authentication`: the `Authentication` object from `SecurityContext` at authorization time.
- `authentication.name`: the authenticated principal's identifier name, such as `alice`.
- `hasRole('ADMIN')`, `hasAuthority('DOCUMENT_READ')`, `hasPermission(...)`: other authorization expressions; `hasRole('ADMIN')` typically checks the `ROLE_ADMIN` authority.

Simple execution flow:

1. The caller invokes a **Spring-managed bean through an AOP proxy**.
2. If `@PreAuthorize` is present, the precondition is evaluated first.
3. The service runs and returns the original result.
4. `PostFilterAuthorizationMethodInterceptor` evaluates SpEL for each element using `filterObject` and the current authentication.
5. The filter removes elements that fail the condition; the caller receives the filtered result.

Comparison example:

| Element | `owner` | User `alice` | Result |
|---|---|---|---|
| Document 1 | `alice` | `alice` | Keep |
| Document 2 | `bob` | `alice` | Remove |
| Document 3 | `alice` | `alice` | Keep |

The expression applies **at return time**, so all queries, computations, or side effects inside the method have already occurred before filtering begins.

## 3. Runnable Example with Java 17, Spring Boot 3, and JUnit 5

The example below creates a service returning test data and tests the permissions of two users. It uses Java 17+, Spring Boot 3.x/Spring Security 6.x, and Maven. The four Java files share the `com.example.postfilter` package; place the test file in `src/test/java` and the three application files in `src/main/java`.

**`pom.xml`** (example using Spring Boot 3.5.6):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>postfilter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/postfilter/PostFilterApplication.java`**

```java
package com.example.postfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class PostFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostFilterApplication.class, args);
    }
}
```

**`src/main/java/com/example/postfilter/Document.java`**

```java
package com.example.postfilter;

public record Document(long id, String owner) {
    // JavaBean getter so SpEL can access the "owner" property.
    public String getOwner() {
        return owner;
    }
}
```

**`src/main/java/com/example/postfilter/DocumentService.java`**

```java
package com.example.postfilter;

import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    @PreAuthorize("isAuthenticated()")
    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> findAll() {
        // Return a mutable copy, avoiding mutation of a shared collection.
        return new ArrayList<>(List.of(
            new Document(1L, "alice"),
            new Document(2L, "bob"),
            new Document(3L, "alice")
        ));
    }
}
```

**`src/test/java/com/example/postfilter/DocumentServiceTest.java`**

```java
package com.example.postfilter;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DocumentServiceTest {
    @Autowired
    private DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void aliceOnlySeesHerDocuments() {
        List<Long> ids = service.findAll()
            .stream().map(Document::id).toList();
        assertEquals(List.of(1L, 3L), ids);
    }

    @Test
    @WithMockUser(username = "bob")
    void bobOnlySeesHisDocument() {
        List<Long> ids = service.findAll()
            .stream().map(Document::id).toList();
        assertEquals(List.of(2L), ids);
    }

    @Test
    @WithMockUser(username = "charlie")
    void userWithNoOwnershipGetsEmptyList() {
        assertTrue(service.findAll().isEmpty());
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn test
```

Expect **all 3 tests to pass**: `alice → [1, 3]`, `bob → [2]`, `charlie → []`. Maven/Spring log lines are not fixed, so do not treat them as standard stdout of the example. The focus of testing is **the outcome of method security on the proxied bean**, not merely testing the expression by calling a plain Java method.

In a real web application, `Authentication` is usually established by login/JWT filters; the service above reuses that context. Sample documents are not fetched from a database so as not to obscure how `@PostFilter` works.

## 4. Writing Practical Filtering Policies

### 4.1. Owner or Administrator

```java
@PreAuthorize("isAuthenticated()")
@PostFilter("hasRole('ADMIN') or filterObject.owner == authentication.name")
public List<Document> findVisibleDocuments() {
    return loadDocumentsAsMutableList();
}
```

This is a **method pattern**: `loadDocumentsAsMutableList()` represents an application-provided query function, not a standalone runnable program. `ROLE_ADMIN` can receive all documents loaded by the method; regular users only see their own documents. Do not treat `hasRole` as assigning a role: the role must actually be granted in `Authentication`.

### 4.2. Requiring General Read Permission Before Filtering

```java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
@PostFilter("filterObject.owner == authentication.name")
public List<Document> findReadableDocuments() {
    return loadDocumentsAsMutableList();
}
```

`@PreAuthorize` requires the `DOCUMENT_READ` authority **before execution**; `@PostFilter` further restricts by owner **after results are produced**. The two annotations address two different decision levels and do not replace each other. The method above is an integration pattern, depending on the application's data-loading function.

### 4.3. Placing Complex Policies in a Separate Bean

When a policy has multiple conditions (tenant, document status, ACL, groups, sharing permissions), push the logic into a bean for easier testing:

```java
@Component("documentAccess")
public class DocumentAccess {
    public boolean canRead(Authentication auth, Document doc) {
        if (auth == null || doc == null) {
            return false;
        }
        boolean admin = auth.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
        return admin || doc.getOwner().equals(auth.getName());
    }
}
```

```java
@PreAuthorize("isAuthenticated()")
@PostFilter("@documentAccess.canRead(authentication, filterObject)")
public List<Document> findVisibleDocuments() {
    return loadDocumentsAsMutableList();
}
```

The two snippets above are **integration patterns** (requiring Spring Security imports, beans/services, and the application's query function). The `canRead` logic illustrates ownership/admin; if the system has multiple tenants, you must **check the tenant before evaluating ownership or admin roles depending on policy**, avoiding accidentally letting one tenant's admin see another tenant's data. For ACL-based policies, you can use `hasPermission(filterObject, 'read')` once an appropriate `PermissionEvaluator` is configured; Spring Security does not automatically know the business ACL of each `Document`.

### 4.4. Filtering Map, Array, and Stream

Spring Security supports filtering **collection, array, map, and stream** (the stream must still be open). The meaning of `filterObject` varies by type:

| Return Value | `filterObject` in Expression | Condition Example |
|---|---|---|
| `List<Document>` / `Collection<Document>` | A `Document` | `filterObject.owner == authentication.name` |
| `Document[]` | A `Document` | `filterObject.owner == authentication.name` |
| `Map<String, Document>` | A `Map.Entry` | `filterObject.value.owner == authentication.name` |
| `Stream<Document>` | A `Document` | `filterObject.owner == authentication.name` |

Example with Map:

```java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> findByCode() {
    Map<String, Document> results = new LinkedHashMap<>();
    results.put("d1", new Document(1L, "alice"));
    results.put("d2", new Document(2L, "bob"));
    return results;
}
```

The snippet above is placed in a Spring-managed service and requires importing `java.util.Map`, `java.util.LinkedHashMap`, and `@PostFilter`. For `alice`, only entry `d1` is kept. The Map must support entry removal during filtering; for streams, pay attention to stream consumption timing, resource lifecycle, and `SecurityContext`. Do not assume every type implementing `Iterable` (such as `Page<T>`) is supported by `@PostFilter` like a `Collection`.

## 5. Limitations, Performance, and Security Boundaries

**In-memory filtering after query.** `@PostFilter` does not automatically add a `WHERE` clause to SQL and does not turn a database query into an authorization-aware query. If a service loads 100,000 rows and returns 5 rows, the cost of reading/mapping objects/checking permissions has already been incurred for the initial row count. When data volume is large, push permission/tenant conditions into repository queries or data-layer security policies, and then optionally use `@PostFilter` as an additional verification layer.

**Pagination must evaluate permissions before paginating.** If a repository returns 20 elements and `@PostFilter` removes 15, the page has 5 elements left even though subsequent pages might contain many valid items. Metadata such as `totalElements` and `hasNext` can also be inaccurate with respect to user permissions. Prefer filtering in the query before `LIMIT/OFFSET` or cursor pagination; do not treat `Page<T>` as an automatically post-filtered type.

**The returned collection must allow element removal.** Collection filters may remove invalid elements using an iterator. `List.of(...)`, `List.copyOf(...)`, and `stream.toList()` results are typically **unmodifiable**; they can throw `UnsupportedOperationException` when the filter needs to remove elements. Return an independent `ArrayList` as in the example. Also avoid directly returning collections from shared caches, ORM-managed relationship collections, or data whose mutation by filtering would alter system state.

**Does not prevent side effects before post-checking.** `@PostFilter` runs after the method, so do not use it to guard write/delete/update operations or prevent sensitive queries that have already occurred. Use `@PreAuthorize` or check permissions before operations with side effects. Logs, messages, caches, and events emitted from the service are not "retracted" by `@PostFilter`.

**Per-element evaluation cost.** Each element invokes the expression again. If the expression calls an ACL service or database to check permissions per element, it easily creates an **N+1** query pattern. You can optimize using batch permission queries, projections, or filtering at the repository level.

**Watch out for null data and properties.** If a collection contains `null` and the expression accesses `filterObject.owner`, a SpEL error may occur. Clean input data, or use a defensive expression:

```java
@PostFilter("filterObject != null and filterObject.owner == authentication.name")
```

You must ensure which properties SpEL can actually access (JavaBean getters, valid methods) and not assume that private field names are always resolved on every object type.

**Proxy boundaries.** Method Security defaults to Spring AOP proxies. Calls from another bean through the proxy have interceptors applied; calls like `this.findAll()` from within the same class may **bypass the annotation** (self-invocation). `private`, `final` methods, or classes not managed by Spring can also prevent advice from being applied. Place rules on proxyable service beans, invoke via Spring-injected beans, and test directly on the Spring-provided bean.

**Does not replace access checks everywhere.** If another endpoint, scheduled job, or repository path can retrieve data without going through the protected service, `@PostFilter` on this service does not protect that path. Place authorization boundaries where callers are forced to pass through; protect direct access by ID with `@PostAuthorize`/corresponding permission checks to avoid IDOR vulnerabilities.

## 6. Brief Comparison of Related Annotations

| Annotation | When Is It Checked? | Checked Target | Typical Behavior |
|---|---|---|---|
| `@PreAuthorize` | Before calling the method | The entire invocation | Blocks if condition is false |
| `@PostAuthorize` | After the method returns | The invocation result, usually one object | Denies returning the result if condition is false |
| `@PreFilter` | Before the method processes | Each element of input collection/array/map/stream | Removes invalid input elements |
| **`@PostFilter`** | **After the method processes** | **Each element of the result** | **Removes invalid elements** |

For example, `@PostAuthorize("returnObject.owner == authentication.name")` is for a single returned `Document`; `returnObject` is **the overall return value**. In `@PostFilter`, use `filterObject` to refer to **an individual element**; mistakenly replacing `filterObject` with `returnObject` usually leads to checking the wrong object or an invalid expression.

## 7. Implementation and Testing Checklist

1. `@EnableMethodSecurity` is enabled and annotations are placed on a Spring-managed service bean.
2. Per-element read policy is clear: ownership, tenant, authority, group, or ACL; verify according to the principle of least privilege.
3. If general access permission is required, place `@PreAuthorize` before the method executes.
4. Return data type is supported by Spring Security; collections/maps are not locked against modification when elements need to be removed; avoid shared collections prone to unintended mutation.
5. Have tests for at least three scenarios: user with some valid elements, user with no valid elements, and user with special privileges if allowed by business rules.
6. Test through a Spring-proxied bean (such as `@SpringBootTest` + `@WithMockUser`), without bypassing interceptors via self-invocation.
7. For large datasets or pagination, filter permissions directly in the query; avoid N+1 when calling permission services.
8. Audit other access paths (detail by ID, export, background jobs, cache, events) so data does not leak outside the filtered flow.

## 8. Takeaways

`@PostFilter` helps express the policy **"return only elements the user is permitted to view"** right at the method boundary. It fits small-to-medium result lists when a readable, testable per-object authorization rule is needed. For large datasets, pagination, or strict tenant isolation, design queries with permission conditions at the source and use Method Security as an additional layer of defense.

**Official documentation:** [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html), section "Filtering Method Results with @PostFilter".