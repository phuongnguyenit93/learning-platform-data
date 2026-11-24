# Collection, Array, Map, Stream, and Version-Dependent Support

> Topic: Spring Security – authorization. Knowledge branch: **Method data filtering**. Examples use Java 17+ and Spring Security Method Security. This content distinguishes capabilities stated in documentation from actual runtime conditions across versions.

## 1. Problem Statement and Operating Model

Suppose a method receives or returns three documents: A belongs to `alice`, B belongs to `bob`, C belongs to `alice`. When `alice` invokes the method, the business requirement is that only A and C pass the corresponding boundary. In Spring Security, the two annotations used to filter **individual elements** are:

- **`@PreFilter`**: evaluates an expression before the method runs to remove elements that do not satisfy the condition from **the selected input parameter**.
- **`@PostFilter`**: evaluates an expression after the method produces a result to remove elements that do not satisfy the condition from **the return value**.

Expressions use Spring Expression Language (SpEL). The `filterObject` variable denotes the element being evaluated; `authentication.name` is the name of the authenticated user. For example, `filterObject.owner == authentication.name` retains objects whose `owner` property equals the username. With `Map`, `filterObject` is a `Map.Entry`, so you need to access `filterObject.value.owner` (or `filterObject.key` if the key itself is the condition).

Typical processing flow:

~~~text
Caller -> Spring AOP proxy
       -> @PreFilter (filter argument, if present)
       -> business method
       -> @PostFilter (filter result, if present)
       -> Caller receives filtered result
~~~

This is **element filtering**, not an allow/deny check for the entire invocation: `@PreAuthorize` and `@PostAuthorize` are for conditional authorization decisions; `@PreFilter` and `@PostFilter` adjust the set of elements. They can be combined when both invocation control and data restriction are needed. `@PostFilter` does not prevent the method from reading sensitive data before the result is filtered.

## 2. Enabling Method Security Properly

In a Spring Boot application using Spring Security 6.x or 7.x, add `@EnableMethodSecurity` to a configuration class. This annotation enables default pre/post processing. Adding `spring-boot-starter-security` alone does not automatically enable method-level security.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Required condition: the method is called **through a Spring bean/proxy**. If using `new MyService()`, making an internal call from another method of the same object (`this.read()`), or placing an interception point on a method where proxying does not apply, the annotation may not execute. Write tests calling beans obtained from the Spring Context; do not only test manually instantiated objects.

For older projects using `@EnableGlobalMethodSecurity(prePostEnabled = true)`, consider migrating to `@EnableMethodSecurity`. The two mechanisms may use different interceptor paths; do not infer the behavior of older versions solely from example code written for newer versions.

## 3. Where Do Collection, Array, Map, and Stream Differ?

| Data Type | `filterObject` Represents | Filtering Mechanism and Things to Remember |
| --- | --- | --- |
| `Collection<T>`, `List<T>`, `Set<T>` | A `T` | For mutable collections, many versions filter by mutating the collection itself (`clear` then re-add). Use mutable `ArrayList`/`LinkedHashSet` for `@PreFilter`. |
| `T[]`, including varargs parameter `T...` | An element `T` | The expression handler creates a **new array** after filtering. `@PostFilter` on object arrays is a clear path; `@PreFilter` on arrays has differences between documentation and interceptor paths, so test against the exact runtime version. Do not assume it applies to primitive arrays like `int[]`. |
| `Map<K,V>` | A `Map.Entry<K,V>` | Compare value properties via `filterObject.value.owner`; keys via `filterObject.key`. Can modify/retain key–value pairs. For `@PreFilter`, convert to a mutable `LinkedHashMap` copy before passing in. |
| `Stream<T>` | A `T` when the stream is consumed | Filtering is **lazy**: evaluation may occur during a terminal operation such as `toList()`, not necessarily at the moment the method returns. Only use an open, unconsumed stream, and manage resource closing. |

**Key distinction:** "the expression handler supports a type" does not mean every `@PreFilter` path can replace a parameter with a new value. For immutable `Collection`/`Map`, arrays, or `Stream`, you must check the exact interceptor of the version in use. Prefer **mutable `List`** for `@PreFilter` inputs; prefer newly created mutable `List`/`Map` results for `@PostFilter` when broad compatibility is needed.

### 3.1. Collection: References and Mutability

~~~java
@PreFilter("filterObject.owner == authentication.name")
public void process(List<Doc> docs) {
    // docs should only contain permitted elements
}

@PostFilter("filterObject.owner == authentication.name")
public List<Doc> findDocs() {
    return new ArrayList<>(repository.findAll()); // mutable copy
}
~~~

This example illustrates a Spring service; `Doc` has a getter method `getOwner()`. With `@PreFilter` on a mutable list, the caller may observe the original list already filtered even if the `process` method did not modify it. Therefore, if the caller still needs the full input, create `new ArrayList<>(source)` **before calling through the proxy**.

`List.of(...)`, `List.copyOf(...)`, `Stream.toList()`, and `Collections.unmodifiableList(...)` return lists that disallow structural modification. `Arrays.asList(...)` allows replacing elements but does not allow `clear()`. With `@PreFilter`, using these lists can cause `UnsupportedOperationException` in some versions, or result in filtering not affecting the original parameter in another path. **Do not pass immutable lists into a method relying on `@PreFilter` as a security boundary.**

With `@PostFilter`, you should also avoid directly returning cached lists or shared lists: if the filter mutates in-place, shared data may be altered for subsequent calls. Create a copy before returning.

### 3.2. Array: Why Pre and Post Must Be Distinguished

~~~java
@PostFilter("filterObject.owner == authentication.name")
public Doc[] findAsArray() {
    return new Doc[] {new Doc("A", "alice"), new Doc("B", "bob")};
}
~~~

When `alice` calls through the proxy, the expected result is an array containing only A; the new array has length 1. Array filtering cannot "remove" elements from the original array because Java array sizes are fixed.

Method Security 6.5/7.x documentation lists `T[]` and varargs among filterable forms, but the `@PreFilter` Javadoc in some versions still states that arrays are not supported. Some pre-invocation interceptor paths have limitations when resolving or replacing array-typed parameters. Therefore:

- **`@PostFilter` with `T[]`:** use when you have tested the return contract of the running version.
- **`@PreFilter` with `T[]`:** do not rely solely on the general statement "arrays supported". If the input is an array, convert it to `new ArrayList<>(Arrays.asList(input))` at the outer boundary and call a method accepting a mutable `List<T>`.
- **`int[]`, `long[]`, ...:** do not assume these are equivalent to `Integer[]`/`Long[]`; many array filter handlers rely on `Object[]`.

### 3.3. Map: Checking Entry, Not Confusing Key with Value

~~~java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Doc> findAsMap() {
    Map<String, Doc> result = new LinkedHashMap<>();
    result.put("a", new Doc("A", "alice"));
    result.put("b", new Doc("B", "bob"));
    return result;
}
~~~

For `alice`, the result keeps only key `a` and object A. `filterObject.owner` here does not match the intent, because `filterObject` is a `Map.Entry`, not a `Doc`. If the security rule lies on the key, you can use an expression like `filterObject.key == authentication.name` when the key is actually the owner name.

With `@PreFilter` on `Map`, the input must be a mutable map when relying on in-place filtering. Avoid `Map.of(...)` or shared maps. Key–value relationship integrity is preserved when filtering by entry; do not filter `keySet()` separately and reassemble values.

### 3.4. Stream: Lazy, Single-Use, and Resource Lifecycle

~~~java
@PostFilter("filterObject.owner == authentication.name")
public Stream<Doc> findAsStream() {
    return Stream.of(new Doc("A", "alice"), new Doc("B", "bob"));
}
~~~

~~~java
try (Stream<Doc> visible = service.findAsStream()) {
    List<Doc> result = visible.toList(); // consumption point where filtering is applied
}
~~~

A `Stream` can only be consumed once. If the stream comes from JDBC/JPA or a resource-holding source, returning a stream across transaction/security context boundaries must be considered carefully: when the caller iterates, it may already be outside the expected transaction or authentication scope. Do not arbitrarily use `parallel()` for an expression accessing authentication state and `filterObject`; test how context is propagated across threads. For business data, it is usually easier to control when querying by permission and returning a materialized `List` in the service layer.

## 4. Complete Runnable Example in Spring Boot

The example uses Java 17+, Spring Boot configured with Gradle, `spring-boot-starter-security`, and Spring Security Test. If the project already has these dependencies, keep them; let Spring Boot manage compatible Spring Security versions.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create three files in `src/main/java/demo/filter/` and the test file in `src/test/java/demo/filter/`.

**`DemoApplication.java`**

~~~java
package demo.filter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`Doc.java`**

~~~java
package demo.filter;

public final class Doc {
    private final String id;
    private final String owner;

    public Doc(String id, String owner) {
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
~~~

**`DocumentService.java`**

~~~java
package demo.filter;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private Doc a() { return new Doc("A", "alice"); }
    private Doc b() { return new Doc("B", "bob"); }

    // Only use a mutable input list.
    @PreFilter("filterObject.owner == authentication.name")
    public List<Doc> accept(List<Doc> docs) {
        return new ArrayList<>(docs);
    }

    @PostFilter("filterObject.owner == authentication.name")
    public List<Doc> asList() {
        return new ArrayList<>(List.of(a(), b()));
    }

    @PostFilter("filterObject.owner == authentication.name")
    public Doc[] asArray() {
        return new Doc[] {a(), b()};
    }

    @PostFilter("filterObject.value.owner == authentication.name")
    public Map<String, Doc> asMap() {
        Map<String, Doc> result = new LinkedHashMap<>();
        result.put("A", a());
        result.put("B", b());
        return result;
    }

    @PostFilter("filterObject.owner == authentication.name")
    public Stream<Doc> asStream() {
        return Stream.of(a(), b());
    }
}
~~~

**`DocumentServiceTest.java`**

~~~java
package demo.filter;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DocumentServiceTest {
    @Autowired
    DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void aliceSeesOnlyHerDocuments() {
        List<Doc> input = new ArrayList<>(List.of(
                new Doc("A", "alice"), new Doc("B", "bob")));

        assertEquals(List.of("A"),
                service.accept(input).stream().map(Doc::getId).toList());

        // @PreFilter also mutates the mutable list passed in by the caller.
        assertEquals(List.of("A"), input.stream().map(Doc::getId).toList());

        assertEquals(List.of("A"),
                service.asList().stream().map(Doc::getId).toList());

        assertArrayEquals(new String[] {"A"}, Arrays.stream(service.asArray())
                .map(Doc::getId).toArray(String[]::new));

        assertEquals(List.of("A"), new ArrayList<>(service.asMap().keySet()));

        try (Stream<Doc> stream = service.asStream()) {
            assertEquals(List.of("A"), stream.map(Doc::getId).toList());
        }
    }

    @Test
    @WithMockUser(username = "bob")
    void bobDoesNotSeeAlicesDocuments() {
        assertEquals(List.of("B"),
                service.asList().stream().map(Doc::getId).toList());
    }
}
~~~

Run from the Spring Boot project directory with JDK 17+:

~~~text
./gradlew test --tests demo.filter.DocumentServiceTest
~~~

On Windows use `gradlew.bat test --tests demo.filter.DocumentServiceTest`. Expected verification outcome: the `alice` test receives only ID A for list, array, map, and stream; the `bob` test receives only B. The test code prints no stdout; success is shown by all assertions passing and the Gradle `test` task succeeding. If dependencies, Gradle configuration, or project versions differ from assumptions, adjust the environment before drawing conclusions about feature correctness.

Here, the input `List` is intentionally created with `new ArrayList<>(...)` and output lists/maps are also newly created objects. This avoids confusion caused by immutability or shared data; at the same time, the tests invoke **the proxied bean**, rather than instantiating `DocumentService` with `new`.

## 5. Multiple Parameters: `filterTarget` Must Specify the Argument Explicitly

When a method has multiple arguments, you should explicitly specify which parameter to filter. The snippet below is a **standalone signature illustration**, not a snippet to paste into `DocumentService` above:

~~~java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "docs"
)
public void acceptBatch(List<Doc> docs, String requestId) {
    // Only process docs after it has been filtered.
}
~~~

The name `docs` must be resolved properly by Spring Security from Java parameter name metadata. Enable the `-parameters` compiler flag or use a parameter naming mechanism supported by your current Spring Security version (e.g., `@P("docs")`); otherwise, argument lookup may fail at runtime. With only a single filterable parameter, `filterTarget` can usually be omitted. When there are multiple parameters, test scenarios with unauthorized data as well; do not only test empty lists.

## 6. Version-Dependent Support: Read Both Documentation and Actual Behavior

| Version Line | What Can Be Confirmed | Implementation Notes |
| --- | --- | --- |
| **Spring Security 5.8.x** | `DefaultMethodSecurityExpressionHandler.filter` source code already branches for `Collection`, object array, `Map`, and `Stream`. | The `@PreFilter` Javadoc on the same branch still describes a mutable `Collection` parameter and states arrays are not supported. Therefore **do not equate handler capability with a guarantee across all `@PreFilter` interceptors**. |
| **Spring Security 6.5.x** | Method Security reference docs state `@PreFilter` and `@PostFilter` with array, collection, map, stream (open stream). `@EnableMethodSecurity` is the recommended way to enable. | Verify mutability, stream lifecycle, proxy, and test both pre/post with the exact signature in use. |
| **Spring Security 7.0–7.1.x** | Reference docs continue listing the four data type families. | Handling of immutable collections/maps may differ from older versions; in some paths, the handler returns a new copy while `@PreFilter` does not replace the original parameter. Do not use immutable inputs as an authorization boundary without testing actual behavior. |
| **Older versions or custom expression handlers** | Full compatibility cannot be inferred from the table above. | Read the exact reference/Javadoc/source of the pinned version in the project and write integration tests for each input/output shape. |

**Safe selection rules applicable across versions:**

1. For `@PreFilter` inputs, use **mutable** `List`/`Map` and create a copy before passing to the service. If receiving an array/stream from an API, convert to a mutable list outside the proxy unless you have specific prefilter tests for that type.
2. For `@PostFilter` outputs, prefer newly created `List` or `Map`. `T[]` and `Stream<T>` can be used once verified by tests; streams require managing consumption timing and closing.
3. Do not use `@PostFilter` as the sole mechanism for multi-record queries, pagination, or data requiring database-level protection. The element count after filtering also does not accurately represent the total permitted records in a paginated query.

If reading documentation reveals conflicts (for example, reference 6.5/7.x shows array examples in `@PreFilter`, while annotation Javadoc still says unsupported), treat that as a signal to **test on the exact library version and parameter type**, rather than picking one sentence as an absolute guarantee. Keep tests preventing unauthorized access in your dependency upgrade pipeline.

## 7. Common Errors and How to Recognize Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Method receives both A and B despite `@PreFilter` | Proxy bypassed, Method Security not enabled, or immutable input/type not handled by interceptor as expected | Enable `@EnableMethodSecurity`, call real bean, pass mutable list, write test with two owners |
| `UnsupportedOperationException` when filtering | In-place filtering on `List.of`, `Map.of`, `Arrays.asList`, or a collection disallowing modification | Use a `new ArrayList<>(...)` / `new LinkedHashMap<>(...)` copy at the right boundary |
| Map not filtering properly | Used `filterObject.owner` even though current object is `Map.Entry` | Use `filterObject.value.owner` or an intentional expression with `key` |
| `IllegalArgumentException` for return value | Type is not one of the four supported by handler, e.g. `Optional<T>`, `Page<T>`, a custom `Iterable` | Filter via data layer or convert to a supported type; do not assume `Page` is auto-filtered |
| `IllegalStateException` in `@PreFilter` | Multiple arguments without identifying which parameter to filter; some array signatures unsupported by interceptor | Set `filterTarget`, preserve parameter name metadata; for arrays consider converting to `List` and testing |
| Returned list misses data on subsequent calls | `@PostFilter` mutated a shared collection/map | Do not return shared caches, singleton state, or shared entity collections directly; make a copy |
| Stream closed error / missing data / error outside transaction | Stream already consumed or closed; deferred filtering outlived transaction/context lifecycle | Materialize while transaction is active, close properly, avoid parallel unless verified |
| Unit test calling service directly still returns everything | Instantiated object with `new`, bypassing security advisor | Test with `@SpringBootTest` and `@WithMockUser` or equivalent security context |

Also test `null` cases in parameters/values, elements without an owner, mismatched owners, empty collections, multiple users, and different roles. Do not let `null` handling errors accidentally turn into skipping checks. For complex conditions, you can move authorization decisions into a dedicated bean and call it from SpEL, then test independently.

## 8. When Should Filtering Happen at the Data Layer?

`@PostFilter` reads results **first**, then evaluates each element: if fetching 100,000 records to return 20 valid records, data-loading and query-execution costs have already been paid. When using `Page<Doc>`, post-filtering also skews the page element count and total record count; `Page` is not a regular `Collection` that the default handler automatically understands.

Practical approach for large data: push owner/tenant/view-permission predicates into repository queries, add method authorization constraints on the service when needed, and test that there is no cross-tenant leak. Only use `@PostFilter` for small datasets already processed in memory or when it truly fits the security design.

## 9. Self-Verification Exercises

Given the list A(owner=alice), B(owner=bob), C(owner=alice) and account `alice`:

1. Via `@PreFilter` on `new ArrayList<>(...)`, the processed method retains A and C; observe whether the list held by the caller is mutated.
2. Via `@PostFilter` on `LinkedHashMap` with keys `a`→A, `b`→B, `c`→C, the result retains keys `a` and `c` when using `filterObject.value.owner`.
3. Via `@PostFilter` on `Doc[]`, the result has two elements A and C; the output array is a new array of length 2.
4. Via `@PostFilter` on `Stream<Doc>`, compare the method call time with `toList()` execution time; confirm the stream is consumed only once.
5. Switch prefilter input to `List.of(...)` or use a signature taking `Doc[]`, and run the test preventing B exposure on **the exact pinned version**. If the test fails or B leaks through, use a mutable `List` and update the design before deploying.

**Completion criteria:** able to explain `filterObject` for each type; choose the right pre/post and filtering timing; never let immutable input render `@PreFilter` ineffective; proactively test version differences rather than relying solely on annotation names.

## Primary References

- Spring Security 6.5 – Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 – Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- `DefaultMethodSecurityExpressionHandler` 5.8.x source code: https://raw.githubusercontent.com/spring-projects/spring-security/5.8.x/core/src/main/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.java
- `PreFilter` 7.0 API (comparing older description of arrays): https://www.springframework.org/spring-security/reference/7.0/api/java/org/springframework/security/access/prepost/PreFilter.html
- Handler source code on current branch (comparing immutable collection/map handling): https://raw.githubusercontent.com/spring-projects/spring-security/main/core/src/main/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.java
