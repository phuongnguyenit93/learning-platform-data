# filterObject, filterTarget, and Selecting the Parameter to Filter

## Learning Objectives

After this lesson, you will be able to: (1) explain `filterObject` in Spring Security Method Security filter expressions; (2) distinguish `filterTarget` from a SpEL variable; (3) select the right parameter when a method accepts multiple lists; (4) verify the results of `@PreFilter` and `@PostFilter`; (5) recognize scenarios where element filtering does not replace operation-wide authorization checks.

**Scope:** Spring Security Method Security on Spring-managed beans, illustrated with Java 17+ and Spring Boot 3 / Spring Security 6. The content focuses on element filtering at method boundaries, not HTTP filters (`SecurityFilterChain`) or database query filtering.

## 1. Three Concepts to Distinguish

| Concept | What Is It? | Where Is It Used? | Example |
| --- | --- | --- | --- |
| `filterObject` | A special variable name in the SpEL evaluation context, sequentially pointing to **the current element** of the collection being filtered. | Expressions of `@PreFilter` and `@PostFilter`. | `filterObject.owner == authentication.name` |
| `filterTarget` | **An attribute of the `@PreFilter` annotation**, containing the name of the input parameter to filter. | When selecting the parameter for `@PreFilter`, especially when there are multiple filterable arguments. | `@PreFilter(value = "...", filterTarget = "documents")` |
| Method parameter name | The name or alias discovered by Spring Security, used to identify the exact actual argument. | Method declarations and parameter mapping. | `@P("documents") List<Document> documents` |

Example:

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public void process(@P("documents") List<Document> documents,
                    List<String> labels) {
    // Only documents is filtered; labels is not filtered.
}
```

In this snippet, `documents` specifies **the input collection**; `filterObject` sequentially refers to each `Document` within that collection. The string `"documents"` is the parameter name, **not** the expression `#documents`, a field name of `Document`, or a specific element. Do not declare a parameter named `filterObject` to "activate" this variable: Spring Security provides it automatically during filtering.

## 2. When Does Spring Security Filter?

Enable method security with `@EnableMethodSecurity` on a Spring configuration. This annotation activates the default `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` mechanisms; the Spring Security dependency alone does not make method security take effect.

An invocation passing **through a Spring proxy** typically has this conceptual flow:

1. The caller invokes a method on a Spring-managed bean.
2. With `@PreFilter`, the interceptor retrieves the target parameter and evaluates the expression **for each element before entering the method body**.
3. If the expression returns `true`, keep the element; if `false`, remove the element from the collection entering the method.
4. The method performs its work with the filtered input.
5. With `@PostFilter`, the interceptor evaluates each element **in the return value** and returns only matching elements to the caller.

| Annotation | Filtered Data | Timing | Has `filterTarget`? |
| --- | --- | --- | --- |
| `@PreFilter` | A supported collection/element-set input argument | Before method body | **Yes** |
| `@PostFilter` | A supported collection/element-set return value | After method body | **No** |
| `@PreAuthorize` | Decides whether to allow calling the entire method | Before method body | No |
| `@PostAuthorize` | Decides whether to allow returning the method result | After method body | No |

**Important:** An element removed by `@PreFilter` usually **does not** trigger an `AccessDeniedException`; the method may still run with an empty list. If business rules require "if one element is unauthorized, reject the entire request", use a dedicated authorization/validation check for the whole operation, such as `@PreAuthorize` invoking a list-checking bean.

## 3. Selecting the Right Parameter for `@PreFilter`

### 3.1. One Clear Input Collection: `filterTarget` Can Be Omitted

```java
@PreFilter("filterObject.owner == authentication.name")
public void save(List<Document> documents) {
    // documents only contains elements that meet the condition.
}
```

When there is only one suitable candidate argument, Spring Security can infer the filter target. If a method has multiple parameters but only one parameter is a filterable collection, it is still good practice to specify `filterTarget` explicitly when doing so makes the method contract clearer and independent of inference.

### 3.2. Multiple Input Collections: Specify `filterTarget`

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "pending"
)
public void merge(@P("pending") List<Document> pending,
                  @P("existing") List<Document> existing) {
    // pending is filtered by owner; existing remains unchanged.
}
```

Omitting `filterTarget` when there are multiple candidate arguments may cause Spring Security to fail to resolve the target and throw an error at invocation time. `filterTarget = "pending"` selects **one** argument; it does not mean filtering both `pending` and `existing`. If two collections need different rules, perform separate intentional checks/filtering rather than treating a single `@PreFilter` as an automatic filter for every parameter.

### 3.3. Parameter Names Must Be Discovered Properly

When Java does not retain parameter names in bytecode, `filterTarget = "pending"` may fail to map to the parameter to filter. Reliable approaches:

- Annotate the parameter with `@P("pending")` from `org.springframework.security.access.method.P` (as in the example). The alias used in the annotation and `@P` must match exactly.
- Compile Java with the `-parameters` flag to retain parameter names in bytecode, e.g. Gradle: `tasks.withType(JavaCompile).configureEach { options.compilerArgs += '-parameters' }`. Then you can use the declared name `pending` without `@P`, provided the project's parameter name discovery mechanism can use it.
- In matching environments, Spring Security also supports names from certain annotations such as Spring Data's `@Param`; only use it when it genuinely belongs to the project's contract.

Distinguish three syntaxes:

```java
filterTarget = "pending"         // CORRECT: target name, an annotation attribute string.
filterTarget = "#pending"        // WRONG: do not use the # prefix here.
value = "filterObject.owner == authentication.name" // Expression for EACH element.
```

The `#pending` syntax can appear **inside a SpEL expression** when you want to reference a discovered parameter variable, but it is not a valid value for selecting the `filterTarget`.

### 3.4. Selecting Based on Business Meaning

Suppose an API takes `documents` (the list of documents to process), `watchers` (notification recipients), and `options` (configuration). Select only the parameter containing **the elements you intentionally allow/skip based on permissions**. Do not pick a list just because it comes first or because it is also a `List`. If `documents` is filtered but a side effect still uses `watchers`, check notification delivery separately to prevent data leaks via side effects.

## 4. Writing Conditions with `filterObject`

On each evaluation, `filterObject` is one element; security variables such as `authentication` provide information about the currently logged-in user.

```java
@PreFilter("filterObject.owner == authentication.name")
public void update(List<Document> documents) { /* ... */ }

@PostFilter("filterObject.owner == authentication.name")
public List<Document> findAll() { /* ... */ }
```

Here `owner` is accessed by Spring Expression Language as a JavaBean property (e.g., via `getOwner()`). If the list contains `null` elements, directly accessing a property in the expression may fail; a defensive condition is `filterObject != null and filterObject.owner == authentication.name`.

Conditions can use SpEL operators such as `and`, `or`, `==`, or delegate to an authorization-checking bean:

```java
@PreFilter("@documentPolicy.canEdit(authentication, filterObject)")
public void update(List<Document> documents) { /* ... */ }
```

`documentPolicy` here is an **application bean that you must provide yourself** (the snippet above only illustrates how to call a bean, not a standalone runnable example). Use a bean when rules are complex, need reuse, or need independent testing. Do not trust a client-submitted `owner` field if it is not trusted ownership data: verify permissions against server-side data when needed.

For `Map<K,V>`, Spring Security documentation describes `filterObject` as a `Map.Entry`: you can write `filterObject.key` or `filterObject.value.owner`, depending on which object needs to be checked. For `@PostFilter`, the iterated collection is **the return value**, so `filterObject` there is not automatically an element of an input parameter.

## 5. Runnable Java 17+ Example in Spring Boot

Prepare a Spring Boot 3.x project with the two dependencies `spring-boot-starter` and `spring-boot-starter-security` (along with the Boot plugin to run `bootRun`). Put **all** of the code below into `src/main/java/demo/FilteringDemoApplication.java`. The non-`public` classes at the end are placed in the same file so the example is self-contained. Accessing the `DocumentService` bean via Spring injection enables the interceptor to work.

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableMethodSecurity
public class FilteringDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilteringDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(DocumentService service) {
        return args -> {
            var auth = new UsernamePasswordAuthenticationToken(
                "alice", "n/a", List.of(new SimpleGrantedAuthority("ROLE_USER")));
            SecurityContextHolder.getContext().setAuthentication(auth);

            try {
                var documents = new ArrayList<>(List.of(
                    new Document("A", "alice"),
                    new Document("B", "bob"),
                    new Document("C", "alice")
                ));
                var labels = new ArrayList<>(List.of("draft", "urgent"));

                System.out.println("Before: " + documents);
                System.out.println("Accepted: " + service.accept(documents, labels));
                System.out.println("Input after: " + documents);
                System.out.println("Labels: " + labels);
                System.out.println("Visible: " + service.readAll());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }
}

@Service
class DocumentService {
    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public List<String> accept(@P("documents") List<Document> documents,
                               List<String> labels) {
        // Inside the method: documents has been filtered; labels is unchanged.
        return documents.stream().map(Document::getId).toList();
    }

    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> readAll() {
        return new ArrayList<>(List.of(
            new Document("A", "alice"),
            new Document("B", "bob"),
            new Document("C", "alice")
        ));
    }
}

final class Document {
    private final String id;
    private final String owner;

    Document(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    @Override
    public String toString() {
        return id;
    }
}
```

In the configured Spring Boot Gradle project, run:

```bash
./gradlew bootRun
```

Lines printed by `System.out.println` in the example (excluding Spring Boot startup logs):

```text
Before: [A, B, C]
Accepted: [A, C]
Input after: [A, C]
Labels: [draft, urgent]
Visible: [A, C]
```

**Step-by-step explanation:** `authentication.name` is `alice`. `@PreFilter` iterates over three `Document`s: A is kept, B is removed because `owner = bob`, C is kept. The `accept` method sees A and C; `labels` is not `filterTarget`, so it remains `[draft, urgent]`. In the example using a mutable `ArrayList`, the original `documents` collection also contains A and C after filtering. `readAll` creates three records, but `@PostFilter` only lets the caller see A and C.

The example intentionally uses `@P("documents")` so target resolution does not depend on the `-parameters` setting. The login token created in `ApplicationRunner` is **for demonstration only**; in a real application, `Authentication` must come from a trusted Spring Security authentication flow.

## 6. Data Types and Impact on Collections

Spring Security 6.5 Method Security documentation describes filtering support for `Collection`, array, `Map`, and `Stream` (the stream must still be usable); internal operation details and errors for each type should be verified against the exact library version in use. When starting out, choose a mutable `ArrayList` to clearly see the difference between **input filtering** and **output filtering**.

- **Mutable vs immutable:** `List.of(...)` or `Collections.unmodifiableList(...)` does not allow element removal. With `@PreFilter` on a `Collection`, if the filtering mechanism requires removal, an immutable collection may cause `UnsupportedOperationException`. Create a copy `new ArrayList<>(input)` at an appropriate boundary.
- **Array:** arrays have a fixed size; do not infer that they will be removed in-place like `ArrayList`. Verify actual behavior by version and signature type.
- **Map:** the expression targets `Map.Entry` and uses `filterObject.value` to access the value object.
- **Stream:** avoid streams that have already been consumed/closed, and note evaluation timing/lazy execution in tests.
- **Null:** a `null` target argument is not an "empty list"; handle/normalize it before the call if the contract allows.

These rules are especially important for APIs receiving objects from controllers, cached lists, or immutable collections returned by libraries.

## 7. Choosing the Right Mechanism for the Goal

| Business Requirement | Typically Suitable Tool | Reason |
| --- | --- | --- |
| Only pass valid elements to the service, allowing others to be skipped | `@PreFilter` | Filters before processing. |
| Only return elements the caller is allowed to view | `@PostFilter` or filter in query | Filters result set; for large data, prefer permission-constrained queries. |
| One unauthorized element cancels the entire operation | `@PreAuthorize`, policy/validation for the whole list | Silent filtering can break atomicity or hide input errors. |
| A single ID/object needs a permission check | `@PreAuthorize` / `@PostAuthorize` / policy | `filterObject` is for element-by-element filtering of a collection; not a variable for an arbitrary scalar argument. |
| Multiple input collections, only one needs filtering | `@PreFilter(filterTarget = "...")` | Identifies target by parameter name, independent of order. |

`@PostFilter` filters **after** the code reads data, so it does not replace tenant/owner-scoped database queries. Pagination after in-memory filtering easily skews total element counts and page counts. If the expression calls a database or remote service for each element, avoid N+1 costs. For sensitive permissions or data updates, place constraints at the data source and service to protect even paths that do not go through the expected endpoint.

## 8. Common Errors and Diagnostics

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `filterObject` does not exist elsewhere | It is only provided within the per-element filtering context. | Use inside `@PreFilter`/`@PostFilter` expressions, do not treat it as a global Java variable. |
| Unclear which `List` to filter | Multiple filterable arguments but no target specified. | Add `filterTarget` and verify the exact name. |
| `filterTarget` cannot find parameter | Bytecode name missing, wrong alias, wrote `#documents`, or case mismatch. | Use `@P` or `-parameters`; names must match exactly. |
| `owner` expression throws error | `null` element, no valid getter, or unexpected element type. | Check actual type, JavaBean getter, and null guard. |
| Error when filtering `List.of` | Collection does not support element removal. | Use a mutable copy before calling. |
| Method called but no filtering happens | Missing `@EnableMethodSecurity`, method does not go through Spring proxy, or self-invocation. | Call from another bean via a Spring-injected bean; check configuration and integration tests. |
| Returned list is right but data still leaked | Service already ran side effects/read too much data before `@PostFilter`. | Block the operation beforehand and constrain queries by permission. |
| Expected 403 error but got empty list | `@PreFilter`/`@PostFilter` removes elements, not a mechanism to deny the entire call. | Use authorization for the entire request when fail-closed is needed. |

**Proxy note:** a call `this.accept(...)` from another method in the same bean usually does not go through the Spring AOP proxy, so annotations on `accept` may be bypassed. Test by calling through a Spring-managed bean; do not only directly call objects created with `new`.

## 9. Testing Checklist for This Lesson

For the service in the example above, you should have integration test cases using `@SpringBootTest` combined with `spring-security-test`/`@WithMockUser` (if test dependencies are added):

1. **User alice, data A/alice, B/bob, C/alice:** kept elements are A and C; the `labels` list is unchanged.
2. **User bob:** only B is kept, verifying both `@PreFilter` and `@PostFilter`.
3. **No matching elements:** result is an empty collection, confirming whether business rules accept processing an empty batch.
4. **Two `List` parameters:** changing parameter order or adding a new parameter still filters only the name declared in `filterTarget`.
5. **Immutable/null arguments:** determine the exact error handling mechanism and normalize input; do not assume every collection type is mutable.
6. **Internal same-bean call vs proxy bean call:** verify method security is actually activated on the production execution path.

Exercise: add a parameter `@P("reviewers") List<Document> reviewers` to the `accept` method. Keep `filterTarget = "documents"`, and verify `reviewers` is unchanged. Then change the target to `"reviewers"` and observe which collection is filtered. Finally, test the case where all `documents` belong to a different owner than the user, and decide whether the business rules require returning an empty list or rejecting the entire operation.

## 10. Takeaways

- `filterObject` = **the element currently being checked**, existing inside the filter expression.
- `filterTarget` = **the name of the selected input parameter** for `@PreFilter`.
- `@PreFilter` filters **before**, `@PostFilter` filters **after** and **has no** `filterTarget`.
- When there are multiple collections, state `filterTarget` explicitly; for stable names, use `@P` or build with `-parameters`.
- Element filtering does not replace operation-wide authorization checks, data-scoped queries, or testing through a Spring proxy.

## References

- Spring Security Reference, Method Security (including `@PreFilter`, `@PostFilter`, parameters, and proxy): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security API, `@PreFilter` annotation: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreFilter.html
