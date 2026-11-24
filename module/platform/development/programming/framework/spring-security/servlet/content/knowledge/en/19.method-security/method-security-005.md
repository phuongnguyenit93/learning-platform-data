# @PreFilter, @PostFilter, and Limitations When Filtering Large Datasets in Spring Security Servlet

## 1. Objectives and Context

In a **Spring Boot 3.x / Spring Security 6.x Servlet** application, method protection is not only the question "who may call this method?" but sometimes also "which elements of a dataset are allowed to enter or leave a method?".

Spring Security provides two annotations for element filtering:

- **`@PreFilter`**: evaluates an expression for **each element of a collection parameter before the method body runs**; only elements passing the condition are forwarded.
- **`@PostFilter`**: evaluates an expression for **each element of the return value after the method body runs**; elements failing the condition are removed before the caller receives the result.

Conceptual example: a method receives a list of documents to preview; user alice may only see alice's documents. Or a service returns a small set of documents and `@PostFilter` drops documents belonging to others.

~~~text
@PreFilter:
caller passes List<Document>
     |
     v
Method-security proxy checks filterObject per element
     |
     v
List retains only valid elements
     |
     v
method body executes with filtered List

@PostFilter:
caller invokes method
     |
     v
method body loads/builds result (e.g. 1000 Documents)
     |
     v
Method-security proxy checks filterObject on result
     |
     v
caller sees only matching elements
~~~

**Central warning of this lesson:** `@PostFilter` **does not turn an unfiltered query fetching all records into an authorization-scoped database query**. If a service loads a million records and Spring Security filters them in Java, the database, network, CPU, heap, and garbage collector have already paid the cost before the caller receives anything. For large, multi-tenant, or sensitive datasets, **push authorization conditions down to the query or data-access layer**, verify ownership/tenant on the server, and paginate **after** applying the condition.

This lesson uses **Java 17+, Spring Boot 3.3.13, Spring Security 6, and Spring MVC** as teaching examples. Standalone examples include complete files, while isolated snippets are explicitly noted. HTTP/test results described here are **expected runtime outcomes**, not claims of Maven execution during authoring.

## 2. Enable Method Security Before Using It

Filter annotations are not MVC annotations. They belong to **method security**, typically operating through Spring AOP/method-security interceptors.

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

This snippet shows only the configuration class and annotations; it requires importing `Configuration` and `EnableMethodSecurity`. In the complete project in section 9, these are placed in `SecurityConfig` alongside the other beans.

By default, `@EnableMethodSecurity` enables the pre/post annotations, including `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. Do not accidentally set `@EnableMethodSecurity(prePostEnabled = false)` and still expect these four annotations to work.

Conceptual flow:

~~~text
HTTP request / Scheduler / Messaging / another bean
                 |
                 v
      Spring-managed service proxy
                 |
                 +-- @PreFilter: filter input collection
                 +-- @PreAuthorize: check before invocation
                 |
                 v
             method body
                 |
                 +-- @PostAuthorize: check result/permission after call
                 +-- @PostFilter: filter output elements
                 |
                 v
            caller receives value
~~~

This diagram does not commit to the exact ordering of all interceptors when multiple annotations apply simultaneously; Spring Security defines interceptor ordering by configuration/version. What to remember is that **pre** occurs before the method body and **post** occurs after the method body. Combining multiple policies should be tested rather than inferred from assumed ordering.

### 2.1. Proxies and Self-Invocation

If a method in the same bean directly calls another method on `this`, the call may **bypass the Spring proxy**, so method-security annotations on the called method will not execute.

~~~java
@Service
public class ExampleService {
    public void outerCall() {
        restrictedMethod(); // self-invocation: may bypass proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void restrictedMethod() {
        // ...
    }
}
~~~

This is an **illustrative snippet**, not the full runnable project. Avoid relying on self-invocation along a security boundary; extract the protected service into **another bean** and call it via dependency injection. In the runnable project in section 9, the controller calls a separate service bean so calls go through the proxy.

Do not rely on `@PreFilter` on `private` methods, `final` methods/classes, or methods not properly intercepted by Spring AOP; design tested public service boundaries. Method security complements, rather than replaces, HTTP security and database-level data checks.

## 3. filterObject, authentication, and SpEL Expressions

Both annotations evaluate a SpEL expression **per element**. Common variables/objects:

| Expression Name | Meaning |
| --- | --- |
| `filterObject` | The element currently being inspected |
| `authentication` | Current `Authentication` in the security context |
| `authentication.name` | Username/principal name per Authentication |
| `principal` | Current principal, depending on Authentication type |
| `hasRole('USER')`, `hasAuthority('...')` | Permission-checking functions of the method-security expression context |

Suppose we have a Java record:

~~~java
public record Document(long id, String owner, String title) {
}
~~~

And user alice is authenticated. The expression:

~~~text
filterObject.owner() == authentication.name
~~~

compares an element's owner to the current user. `owner()` is the Java record accessor; using an explicit method call avoids depending on customizable property-access rules. In SpEL, `==` on strings evaluates with value-equality semantics, unlike Java's reference-equality `==` pitfall.

**Be careful about data sources:**
- If `owner` comes from a **record verified/loaded by the server from the database**, the condition can be part of an ownership check.
- If `owner` is a field in **client-submitted JSON**, the client can set `"owner":"alice"` arbitrarily. Filtering on such a field **does not prove** true ownership.
- `authentication.name` must come from a trusted authentication mechanism; never accept an `X-Username` header or `?user=alice` query parameter as identity.
- Multi-tenant authorization typically requires checking both a **trusted** tenant ID and real object ownership/permissions. Comparing usernames is a teaching example, not a complete production policy.

If an expression references a null field or an incompatible record structure, evaluation errors can occur. Write null-safe policies and test with realistic data, especially collections containing null elements.

## 4. @PreFilter: Filtering Parameters Before the Method Runs

### 4.1. Core Example

~~~java
@PreFilter("filterObject.owner() == authentication.name")
public List<Document> preview(List<Document> candidates) {
    return List.copyOf(candidates);
}
~~~

This is a **snippet** of a method in a Spring-managed service with `@EnableMethodSecurity`, not a complete Java class. With a single collection parameter, `@PreFilter` knows which collection to filter.

Suppose the caller passes a *mutable* list:

~~~text
Input before proxy:
[Doc(1, "alice"), Doc(2, "bob"), Doc(3, "alice")]

Authenticated user: alice

Input received by method body after @PreFilter:
[Doc(1, "alice"), Doc(3, "alice")]
~~~

Elements not matching the expression are removed **before** the method body logic processes them. In many implementations, Spring Security mutates the parameter collection directly to remove elements; **do not assume the input object remains unchanged** and never pass an immutable collection if the filter must remove elements.

### 4.2. filterTarget When Multiple Filterable Parameters Exist

For example, a service accepting both a purpose string and a list of documents:

~~~java
@PreFilter(
    value = "filterObject.owner() == authentication.name",
    filterTarget = "candidates"
)
public List<Document> preview(String purpose, List<Document> candidates) {
    return List.copyOf(candidates);
}
~~~

This snippet illustrates `filterTarget` and is not a method in the section 9 project. When multiple collections/maps/arrays or parameters make target selection ambiguous, `filterTarget` specifies **the parameter name to filter**. Referencing Java parameter names may require `-parameters` compiler metadata; use an appropriate build setup (Spring Boot Maven parent typically configures parameter-name support) or check supported naming mechanisms in your version. Do not treat `filterTarget` as a JSON request field name.

### 4.3. Mutable Collections and Side Effects

A common pitfall:

~~~java
List<Document> items = List.of(
    new Document(1L, "alice", "A"),
    new Document(2L, "bob", "B")
);
service.preview(items);
~~~

`List.of(...)` returns an **unmodifiable** list. When `@PreFilter` tries to remove unauthorized elements, depending on the collection/implementation, `UnsupportedOperationException` may be thrown. At the caller, use a **defensive mutable copy**:

~~~java
List<Document> safeCopy = new ArrayList<>(items);
List<Document> visible = service.preview(safeCopy);
~~~

This snippet requires importing `List` and `ArrayList`, plus the corresponding Document type/method in a matching project. The key point is not "every List will fail" but **never force a mutating filter to operate on immutable/unmodifiable input**.

If the original list is shared across multiple threads, do not let a prefilter mutate the same instance other requests are using. Create a request-local copy, or redesign the API to return a newly constructed controlled collection. Any collection mutation by prefiltering must be evaluated for concurrency and ownership.

### 4.4. @PreFilter Is Not @PreAuthorize

- `@PreAuthorize` typically decides **whether to allow calling the entire method**.
- `@PreFilter` removes **individual elements** of a parameter.

For example, a write batch has 10 items, one of which does not belong to the user. If you use prefiltering, the method body may process only 9 items and return success. That can **violate the API contract** or break transaction atomicity.

For critical write operations, it is usually better to **check the entire batch** and **reject the whole request** if any element is unauthorized, rather than silently dropping elements:

~~~java
// Illustrative business policy snippet - not a complete class.
boolean allAuthorized = items.stream().allMatch(
    item -> documentPolicy.canWrite(authentication, item.id())
);
if (!allAuthorized) {
    throw new AccessDeniedException("Not authorized to modify one or more documents");
}
~~~

`documentPolicy.canWrite` must verify permissions against data **retrieved from a trusted source** and the principal's tenant; never trust a client-supplied `owner`. In transactional services, define rollback behavior, locking, and pre-write re-verification upfront.

**Rule:** choose `@PreFilter` when the business case genuinely permits **skipping non-matching elements**. Choose `@PreAuthorize`/policy services when the requirement is **all-or-nothing allow or deny**.

## 5. @PostFilter: Filtering Return-Value Elements

### 5.1. Core Example

~~~java
@PostFilter("filterObject.owner() == authentication.name")
public List<Document> listVisibleFromSmallSample() {
    return new ArrayList<>(documentStore.all());
}
~~~

This is an illustrative service snippet requiring dependency injection and full imports. The method **runs first**, producing the document list, and **then** the method-security interceptor filters elements by the expression.

With the list:

~~~text
Result produced by method body:
[Doc(1, "alice"), Doc(2, "bob"), Doc(3, "alice")]

Authenticated user: alice

Final result seen by caller:
[Doc(1, "alice"), Doc(3, "alice")]
~~~

`@PostFilter` does not prevent the method from reading bob's data in the first place. It only affects **the return value of the intercepted call**. If the method already logged bob's data, emitted events, updated a cache, called an external service, or performed side effects, the annotation cannot undo them.

### 5.2. Returned Collections Must Be Filterable

In the working example in section 9, the demo store returns a `new ArrayList<>(...)` so Spring Security has a collection the interceptor can filter. Do not assume `List.of(...)`, `List.copyOf(...)`, `Collections.unmodifiableList(...)`, or arbitrary custom collections can be modified in place.

Exact support for arrays, maps, streams, and other return types varies across versions and APIs. When using `Page<T>`, `Slice<T>`, reactive publishers, or large streams, **do not assume @PostFilter works and paginates properly**; verify supported types and especially evaluate materialization costs. With Spring WebFlux, the mechanism is a separate stack—do not blindly apply this Servlet example there.

### 5.3. Do Not Replace Data Protection Inside the Method Body

An anti-pattern:

~~~java
@PostFilter("filterObject.owner() == authentication.name")
public List<Document> exportAllDocuments() {
    List<Document> all = repository.findAll();

    auditLogAllDocuments(all); // sensitive data was already read and logged before filtering
    return all;
}
~~~

This is **illustrative pseudo-code**, not a compilable class: `repository` and `auditLogAllDocuments` are undefined. Even though the caller only receives the filtered list, the function already read and potentially logged unauthorized data. For sensitive data, queries or access policies **should filter before loading**, avoiding bringing all records into memory and causing side effects before filtering.

### 5.4. @PostFilter Is Not @PostAuthorize

- `@PostAuthorize("returnObject.owner() == authentication.name")`: evaluates **a single result** (e.g. one Document) and decides whether to return the object or deny the entire call.
- `@PostFilter("filterObject.owner() == authentication.name")`: evaluates **each element in a result collection** and removes non-matching elements.

Both run after the method body, sharing the same limitations: data has already been read/computed, side effects may have happened, and deciding too late does not avoid query cost. When accessing a single object by ID, **`@PreAuthorize` combined with owner/tenant-constrained queries** is usually more suitable when conditions can be checked early; also consider TOCTOU between checking and reading.

## 6. Comparing the Four Pre/Post Annotations

| Annotation | Timing | Inspected Target | Outcome |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before method body | Permission to call the whole method | Allow call or deny |
| `@PreFilter` | Before method body | Each element of a supported collection/map parameter | Method receives filtered input |
| `@PostAuthorize` | After method body | Permission to return result/`returnObject` | Allow return or deny |
| `@PostFilter` | After method body | Each element of a supported collection result | Caller receives filtered output |

For instance, a complex service might use both `@PreAuthorize` and `@PostFilter` to reject unauthenticated callers and then filter a small in-memory set. However, stacking annotations **does not automatically compose into safe database protection**; if the data query is overly broad, cost and side-effect leakage risks still remain.

### 6.1. HTTP Security Remains a Separate Layer

`SecurityFilterChain` / `authorizeHttpRequests` protects incoming HTTP requests. `@EnableMethodSecurity` protects method calls intercepted by Spring proxies. They work together:

~~~text
GET /api/docs
     |
     v
HTTP SecurityFilterChain: authenticated()
     |
     v
DocumentController
     |
     v
DocumentService proxy: @PreAuthorize + @PostFilter
     |
     v
DocumentStore
     |
     v
Results filtered for current user
~~~

Never use HTTP URL matchers as the sole protection for services that may be invoked by schedulers, message consumers, other endpoints, or parts of the app bypassing that web security chain. Equally, never rely on method annotations to configure CORS/CSRF/headers.

### 6.2. When Unauthenticated

The expression `authentication.name` only has meaning relative to the current Authentication. In a web chain an anonymous Authentication can exist; anonymous state is not the same as a logged-in user. If a method requires a real user, add `@PreAuthorize("isAuthenticated()")` or an equivalent policy and ensure an appropriate HTTP entry point.

Never write a filter expression like:

~~~text
filterObject.owner() == request.getParameter("user")
~~~

and treat client-sent `user` as a trusted identity. Permissions must rely on server-validated Authentication and real owner/tenant data.

## 7. Critical Limitations When Filtering Large Datasets

### 7.1. Complexity and Overfetching

Suppose the `documents` table has **1,000,000** rows, of which user alice is allowed to see **40** rows. If the service executes:

~~~java
List<Document> all = repository.findAll(); // 1,000,000 rows
return all; // @PostFilter ultimately returns only 40 rows
~~~

You have:
- Asked the database to read/serialize one million records.
- Transferred massive amounts of data from DB to app.
- Allocated one million entities/DTOs/objects or materialized the result.
- Evaluated the predicate on every element in Java.
- Placed heavy pressure on heap, GC, and CPU; risking OOM or timeouts.
- Risked accidentally logging/caching records prior to filtering.

If checking each element is O(1), the filtering loop itself still visits **O(N)** elements. Total cost also includes querying, data transfer, object mapping, lazy loading, and work inside the method. The cost model is not simply "Java is fast so post-filtering is fine".

~~~text
Overfetch approach:
DB: 1,000,000 rows --network--> JVM: 1,000,000 objects
                                      |
                                 @PostFilter
                                      |
                                      v
                               40 rows returned to client

Scoped query approach:
DB: WHERE owner_id = current_user AND tenant_id = current_tenant
    ORDER BY id DESC LIMIT 20
                                      |
                                 network
                                      v
                             JVM: 20 authorized rows
~~~

These numbers are hypothetical scenarios for analysis, not measured benchmarks. In large systems, fetching all N rows and then filtering causes cost to scale linearly with total data across **all users/tenants**, instead of only the rows the caller may view.

### 7.2. Pagination Breaks When Filtering Afterward

Consider the query:

~~~sql
SELECT id, owner_id, title
FROM documents
ORDER BY id DESC
LIMIT 20 OFFSET 0;
~~~

The DB returns the first 20 rows across the whole system; `@PostFilter` drops 18 rows belonging to other users and keeps only 2. The client receives "page 1 has 2 rows" even though the database may hold hundreds more rows for that user on later pages.

Resulting problems:
- **Wrong page size** (requested 20, received 2).
- **Wrong total count** (counts the whole table instead of the user's authorized subset).
- **False empty pages** even when valid data still exists for the user.
- **Cursors/offsets can skip valid records** when clients paginate over post-filtered results.
- **Sorting and aggregations** may reflect system-wide data before security is applied.
- Some repositories return `Page<T>`, which cannot be safely filtered like a List; even with adapters, pagination metadata must come from the pre-authorized dataset.

**Correct order:** filter by permissions in the DB → sort → paginate → map DTOs → serialize response. Never do "pagination → @PostFilter" for large user-scoped datasets.

### 7.3. Lazy Loading and N+1 Queries

A SpEL expression like:

~~~text
filterObject.owner.id == authentication.principal.id
~~~

can access lazy-loaded relationships. If the collection has 5,000 entities, checking the owner can trigger thousands of individual queries (**N+1** problem). If the persistence context is closed, lazy initialization errors occur. An expression that looks simple on paper is not necessarily cheap in an ORM.

How to handle:
- Use `ownerId`/`tenantId` directly in the query.
- Avoid traversing lazy relationships in policies over full sets.
- Use projections/DTOs with only required fields.
- Monitor query counts and fetch plans when needed.
- Never keep transactions artificially wide just to "patch" inefficient post-filtering.

### 7.4. @PreFilter Does Not Automatically Reduce Data-Fetching Cost Either

An easily missed point: `@PreFilter` runs **before the annotated method body**, but if the caller already ran `repository.findAll()` and passed the list into the service, the DB already loaded all data before prefiltering ran.

~~~text
Controller: repository.findAll() -> 1,000,000 objects
                                  |
                                  v
                 service.preview(@PreFilter List)
                                  |
                                  v
                        only 40 objects enter method body
~~~

The method body processes fewer elements, yet **the cost of loading/instantiating one million elements has already been paid**. Thus "switching @PostFilter to @PreFilter" does not solve the large-data problem. Change **where filtering happens** and the **actual query**, not just the annotation.

### 7.5. Indirect Data Leaks and Side Effects

Even if the response omits unauthorized documents, data may already have passed through:
- Logs/traces/metrics containing sensitive fields.
- Shared caches with keys lacking tenant/user scope.
- Domain events published before filtering.
- Temporary files/export/import staging.
- Async tasks processing the dataset before the caller gets the response.
- Exception messages containing details of unauthorized records.
- Counts/aggregate statistics or timing differences revealing other users' data.

A security filter after the method body is not a data "sandbox". When strong confidentiality is required, read only records the caller is authorized to access and verify access before creating side effects.

### 7.6. Immutable Collections, Parallelism, and Shared Mutable State

Proxy-level filtering may need to mutate the given collection. Situations to avoid:
- `List.of(...)` / unmodifiable collections.
- Lists cached/shared across requests and subsequently mutated.
- Lists read concurrently on other threads.
- Streams/lazy results tied to closed transactions.
- Custom collections with non-standard ordering or removal semantics.

Prefer **defensive copies** for demos, and **query-scoped results** for production. Never let one user mutate a shared collection merely because a method-security filter removed elements.

## 8. Production Architecture: Filter at the Database and Policy Layers

### 8.1. Constraining Owner/Tenant in the Repository

For paginated queries, conceptually write:

~~~sql
SELECT id, owner_id, tenant_id, title
FROM documents
WHERE tenant_id = :trustedTenantId
  AND owner_id = :authenticatedUserId
  AND deleted = false
ORDER BY id DESC
LIMIT :pageSize OFFSET :pageOffset;
~~~

These named parameters represent values **bound by the server via prepared parameters**, never concatenated from client SQL strings. `trustedTenantId` and `authenticatedUserId` must come from a verified principal/session with trusted membership/tenant scope; never treat `?tenantId=...` or `?ownerId=...` as an authorization source.

Spring Data JPA can also express scoped queries via repository methods:

~~~java
// Snippet of a Spring Data JPA repository;
// requires DocumentEntity and imports per the actual project.
Page<DocumentEntity> findByTenantIdAndOwnerIdAndDeletedFalse(
    UUID tenantId, UUID ownerId, Pageable pageable
);
~~~

This is a **snippet**, not the runnable project in section 9 (the demo project uses an in-memory store). With a real database, ensure proper indexes, handle soft deletes, row-level permissions, multi-tenant isolation, and scoped count queries. Never pass an arbitrary client-supplied `ownerId` into the method and assume the signature itself is secure.

### 8.2. Checking a Single Document by ID

For `GET /api/docs/123`, you can query:

~~~sql
SELECT id, owner_id, tenant_id, title
FROM documents
WHERE id = :documentId
  AND owner_id = :authenticatedUserId
  AND tenant_id = :trustedTenantId
  AND deleted = false;
~~~

If no row is returned, the policy can return **404** to avoid disclosing whether the document exists, or **403** per the system contract. Crucially, do not load another tenant's document and accidentally leak it before denying. On writes, consider atomic check-and-update, transaction isolation, optimistic locking, and concurrency to prevent **TOCTOU** (checking permissions at a different time than updating).

### 8.3. Query Authorization Is Primary; PostFilter Is Supplementary

You may keep `@PostFilter` on a small DB-filtered list as **defense in depth** or to check an extra UI condition, but:
- Do not rely on it as the sole barrier against multi-tenant data.
- Do not treat it as a band-aid hiding repository query bugs.
- Always test negative cases (other users' records never appear) at both **API and repository/service** levels.
- Audit cache keys, paging/counts, exports, and other entry points.

### 8.4. Reject the Whole Batch Rather Than Silently Skipping

For batch updates/deletes, dropping unauthorized elements is usually **dangerous** if the client assumes everything was processed. Check permissions for all resources, then process atomically or return explicit errors per contract. In many systems, **a request containing one unauthorized item must be rejected**, not silently "filtered to pass".

`@PreFilter` fits better for operations with "process only items the user is allowed to see" semantics, such as previews or selecting small subsets for a safe calculation where callers expect a filtered subset. If applied to client-sent data, recognize that the filtered field itself could be forged.

### 8.5. Pessimistic vs Optimistic Authorization

In mutable environments, owner/tenant/permission state can change right between checking and reading/writing. For sensitive resources, design operations so permission predicates appear inside the operation statement itself or are protected by proper transactions/locking. For example, an update SQL statement can include `WHERE id=... AND owner_id=... AND tenant_id=...`, then verify `rowsAffected` instead of trusting an earlier separate check.

## 9. Complete Example: Spring Boot 3.3.13, Security 6, Java 17, MockMvc

The project clearly demonstrates **both filtering points**, using a small **server-created** document set so we do not trust fake owners from client JSON:

1. `GET /api/docs` calls a `@PostFilter` method: the method creates a List with alice's and bob's documents, then filters output by user.
2. `GET /api/preview` calls a `@PreFilter` method: the controller takes a **mutable** List copy from the store before calling the service; inputs are filtered before the method body receives the list.
3. `GET /api/docs/{id}` uses `@PreAuthorize` and a policy bean checking document ownership by ID before the service returns data; illustrating a better choice for single-object access.
4. `GET /health` requires no authentication; all `/api/**` routes require HTTP Basic.
5. MockMvc tests for alice, bob, charlie (no documents), anonymous, unauthorized ID access, and deny fallback.

**Teaching purpose:** the store holds 3 in-memory records, not a database, with no pagination and no write operations. Calling `store.all()` to learn prefilter/postfilter is **intentionally not a production query pattern**. With real/large data, use owner/tenant-scoped repository queries from section 8.

### 9.1. Project Structure

~~~text
method-filter-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/methodfilter/
    │       ├── MethodFilterApplication.java
    │       ├── SecurityConfig.java
    │       ├── DocumentStore.java
    │       ├── DocumentPolicy.java
    │       ├── DocumentService.java
    │       └── DocumentController.java
    └── test/
        └── java/com/example/methodfilter/
            └── MethodFilterTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-filter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

**`src/main/java/com/example/methodfilter/MethodFilterApplication.java`**

~~~java
package com.example.methodfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodFilterApplication.class, args);
    }
}
~~~

### 9.2. SecurityConfig: Enabling Method Security and HTTP Basic

**`src/main/java/com/example/methodfilter/SecurityConfig.java`**

~~~java
package com.example.methodfilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF remains enabled by default; project only calls GET.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("charlie")
                .password(hash)
                .roles("USER")
                .build()
        );
    }
}
~~~

This configuration uses HTTP Basic to make real authentication easy to test; demo passwords are only for localhost. HTTP Basic sends passwords in Base64 inside the Authorization header and **does not encrypt passwords**. Production requires HTTPS and proper credential management.

### 9.3. DocumentStore: Small Dataset, Returning Mutable Copies

**`src/main/java/com/example/methodfilter/DocumentStore.java`**

~~~java
package com.example.methodfilter;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    public record Doc(long id, String owner, String title) {
    }

    private final List<Doc> data = List.of(
        new Doc(1L, "alice", "Design"),
        new Doc(2L, "bob", "Finance"),
        new Doc(3L, "alice", "Notes")
    );

    public List<Doc> all() {
        // Spring Security may remove elements from the collection.
        return new ArrayList<>(data);
    }

    public boolean ownedBy(long id, String owner) {
        return data.stream().anyMatch(d ->
            d.id() == id && d.owner().equals(owner));
    }

    public Doc byId(long id) {
        return data.stream()
            .filter(d -> d.id() == id)
            .findFirst()
            .orElseThrow();
    }
}
~~~

`data` is intentionally an immutable `List.of` to prevent services from accidentally modifying the global store. Each `all()` call creates a separate `new ArrayList<>(data)`, so pre/post filtering can remove elements **without altering the original data**. This technique is **right for a tiny demo**, not a reason to load an entire database into an ArrayList.

### 9.4. DocumentPolicy: Checking Ownership by ID from the Store

**`src/main/java/com/example/methodfilter/DocumentPolicy.java`**

~~~java
package com.example.methodfilter;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentStore store;

    public DocumentPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long id) {
        return authentication != null
            && store.ownedBy(id, authentication.getName());
    }
}
~~~

The policy reads the owner from the **server-side store**, never trusting client-sent fields. In production code, you must enforce owner **and tenant** (if applicable) in the query rather than querying all rows and filtering. A document ID absent from the store returns false, causing access denial before the service returns data — illustrating an option to avoid disclosing document existence.

### 9.5. DocumentService: Three Protection Styles

**`src/main/java/com/example/methodfilter/DocumentService.java`**

~~~java
package com.example.methodfilter;

import java.util.List;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

import com.example.methodfilter.DocumentStore.Doc;

@Service
public class DocumentService {

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("isAuthenticated()")
    @PostFilter("filterObject.owner() == authentication.name")
    public List<Doc> listSmallSample() {
        // Method runs first, then filters; use only with 3 demo items.
        return store.all();
    }

    @PreAuthorize("isAuthenticated()")
    @PreFilter("filterObject.owner() == authentication.name")
    public List<Doc> previewFromCandidates(List<Doc> candidates) {
        // By the time the method body runs, non-matching elements have been removed.
        // Return an immutable copy AFTER @PreFilter has executed.
        return List.copyOf(candidates);
    }

    @PreAuthorize("isAuthenticated() and @documentPolicy.canRead(authentication, #p0)")
    public Doc findOwned(long id) {
        return store.byId(id);
    }
}
~~~

Distinguishing the three calls:

- `listSmallSample()`: the method first returns the list containing both alice and bob; `@PostFilter` filters **afterward**.
- `previewFromCandidates(...)`: the caller passes a mutable List; `@PreFilter` filters **beforehand**; the method can return `List.copyOf` after the input has been filtered.
- `findOwned(id)`: does not load the full list for postfiltering; `@PreAuthorize` calls a server policy to check permission for the ID before the method body reads the record.

`#p0` references the **first parameter** in SpEL, avoiding dependence on compiler-retained variable names. `@documentPolicy` is the bean explicitly named in `@Component("documentPolicy")`. `isAuthenticated()` ensures anonymous callers are not treated as real users for these methods.

In production, `canRead` checking the store followed by `byId` reading again can still face **TOCTOU** if permissions/data change between the two steps. In the immutable store example that issue does not occur; with a real DB, use owner/tenant-scoped repository queries and appropriate transactions/locking.

### 9.6. DocumentController: Calling Through the Service Proxy

**`src/main/java/com/example/methodfilter/DocumentController.java`**

~~~java
package com.example.methodfilter;

import java.util.List;
import java.util.Map;

import com.example.methodfilter.DocumentStore.Doc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;
    private final DocumentStore store;

    public DocumentController(DocumentService service, DocumentStore store) {
        this.service = service;
        this.store = store;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/docs")
    public List<Doc> docs() {
        return service.listSmallSample();
    }

    @GetMapping("/api/preview")
    public List<Doc> preview() {
        // Mutable copy; only three server-created records.
        return service.previewFromCandidates(store.all());
    }

    @GetMapping("/api/docs/{id}")
    public Doc one(@PathVariable long id) {
        return service.findOwned(id);
    }
}
~~~

The controller invokes `DocumentService` through the **injected Spring-managed bean**, without calling another method within the same class. This is a key condition for service annotations to actually be intercepted by method security.

`/api/preview` intentionally still loads all three records before `@PreFilter` — specifically to make clear that **prefiltering does not optimize queries**. With large datasets, the controller must not call `store.all()` like this; it must call a user/tenant-scoped repository query.

### 9.7. Testing with Spring Security MockMvc

**`src/test/java/com/example/methodfilter/MethodFilterTests.java`**

~~~java
package com.example.methodfilter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodFilterTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublicButDocumentsRequireAuthentication()
            throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        mvc.perform(get("/api/docs"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void postFilterKeepsOnlyAlicesDocuments() throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].owner").value("alice"))
            .andExpect(jsonPath("$[0].id").value(1))
            .andExpect(jsonPath("$[1].owner").value("alice"))
            .andExpect(jsonPath("$[1].id").value(3));
    }

    @Test
    void preFilterKeepsOnlyBobsDocument() throws Exception {
        mvc.perform(get("/api/preview")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].owner").value("bob"))
            .andExpect(jsonPath("$[0].id").value(2));
    }

    @Test
    void noMatchingElementsIsAnEmptyList() throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("charlie", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));

        mvc.perform(get("/api/preview")
                .with(httpBasic("charlie", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void policyProtectsIndividualDocuments() throws Exception {
        mvc.perform(get("/api/docs/1")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        mvc.perform(get("/api/docs/1")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/docs/2")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void missingDocumentIdDoesNotRevealAnotherRecord()
            throws Exception {
        mvc.perform(get("/api/docs/999")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedUrlIsDenied() throws Exception {
        mvc.perform(get("/unexpected")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

**QA points in the tests:**

- Anonymous 401 test goes through HTTP Basic and HTTP authorization.
- Alice test receives only id 1, 3 (never seeing bob's) from `@PostFilter`.
- Bob test receives only id 2 from `@PreFilter`.
- Charlie test shows that **an empty result is not an exception**, when the method is valid and no elements belong to the caller.
- `/api/docs/{id}` test checks the policy before returning a single object: alice cannot read id 2 and bob cannot read id 1.
- Fallback deny test helps detect APIs outside the policy.
- Do not use `@WithMockUser` to skip password verification: `httpBasic` ensures tests pass through real authentication in the demo config.

Returning HTTP **403** when the ID does not belong to the owner / does not exist is a demo policy choice. Production systems may return 404 to reduce resource-existence leakage, while keeping the contract and error messages consistent.

### 9.8. Run Commands and Expected Output

Requires **JDK 17+, Maven**, and ability to download dependencies on the first run:

~~~bash
mvn test
mvn spring-boot:run
~~~

The **expected** result of the test suite when the project is created properly with valid dependencies is `BUILD SUCCESS`. These commands are provided for learners to run themselves, **not executed in this document**.

In another terminal:

~~~bash
curl -i http://localhost:8080/health
# Expected 200, {"status":"ok"}

curl -i http://localhost:8080/api/docs
# Expected 401, HTTP Basic challenge

curl -i -u alice:demo-pass http://localhost:8080/api/docs
# Expected 200, JSON containing id=1 and id=3

curl -i -u bob:demo-pass http://localhost:8080/api/preview
# Expected 200, JSON containing only id=2

curl -i -u charlie:demo-pass http://localhost:8080/api/docs
# Expected 200, []

curl -i -u bob:demo-pass http://localhost:8080/api/docs/1
# Expected 403

curl -i -u alice:demo-pass http://localhost:8080/api/docs/1
# Expected 200, JSON for document id=1
~~~

On Windows PowerShell you can use `curl.exe`. HTTP Basic over the Internet must use HTTPS; only use HTTP on localhost for learning and never put demo passwords in production.

## 10. Measuring Performance Properly: Fewer Response Rows Is Not Enough

### 10.1. Do Not Judge by the Number of Returned JSON Elements

An endpoint returning 20 elements does not mean the database only scanned 20 rows. Measure:

- The actual SQL query and **number of DB rows read/returned**.
- DB and network time.
- Number of entities/DTOs allocated.
- Total query count (including lazy loading/N+1).
- Heap allocation, GC, CPU, and p95/p99 latency.
- Scalability as a tenant's record count grows.
- Export/search/pagination paths outside the endpoint under test.

If data is large or a user is only authorized for a small fraction, ask specifically: "Does the SQL query have a scope predicate by principal/tenant and LIMIT/OFFSET after filtering?". If the answer is no, using `@PostFilter` may only be **hiding** data in the response, neither optimizing nor completing security.

### 10.2. Scale Comparison Example

| Criterion | Post-Filtering with @PostFilter | Filtering in DB Before Pagination |
| --- | --- | --- |
| DB rows inspected | Potentially the full set N | Subset matching scope, using proper indexes |
| Rows sent to app | Potentially N | At most the needed page size |
| Java objects created | Potentially N | Typically proportional to page size |
| Elements iterated in Java to check owner | Potentially N | Optional extra check on small page |
| Scope-accurate page total/count | Easy to get wrong without extra design | Accurate when count query shares WHERE clause |
| Risk of unauthorized data in logs/cache | Higher if processed before filter | Reduced when queries avoid loading out-of-scope data |
| Efficiency at large N | Prone to bottlenecks/OOM | Scales much better with proper queries/indexes |

This table is a mental model; the database still plans queries and scans/indexes according to schema and predicates. What matters is **never transferring all data to the JVM just to filter it with SpEL**.

### 10.3. Tests to Add When Using a Real Database

1. User A never sees B's records on the first page and **every subsequent page**.
2. Total record count/`totalElements` counts only records the user is permitted to see.
3. Sort order/cursors do not shift erroneously due to post-filtering.
4. Tenant A never receives tenant B's records even with identical owner IDs or usernames.
5. Queries do not call table-wide `findAll()` when the client requests a small page.
6. Owner/permission changes mid-request still do not cause unauthorized updates.
7. No logs/caches/events contain records outside the caller's permissions.
8. Test with sufficient data volume to observe heap, latency, and query counts.

## 11. Common Mistakes When Applying @PreFilter/@PostFilter

| Misconception / Error | Consequence | Resolution |
| --- | --- | --- |
| Forgetting `@EnableMethodSecurity` | Annotations are not enforced by method-security interceptors as intended | Enable method security and add integration tests |
| Calling annotated method via `this.method()` in same bean | Bypasses Spring AOP proxy | Call through another managed bean/proxy |
| Using private/final methods as boundary | Proxy may not intercept | Design appropriate public service boundaries |
| `@PreFilter` receives `List.of(...)` | May throw UnsupportedOperationException | Use defensive mutable collections or properly scoped queries |
| Filtering a List shared across requests | Cross-request mutation/data race | Never share mutable inputs; create local copies |
| Thinking `@PreFilter` reduces query rows automatically | Caller may have called findAll beforehand | Put scoping in repository queries |
| Thinking `@PostFilter` filters before DB read | DB/app already processed unauthorized data | Query WHERE owner/tenant before loading |
| Applying PostFilter after LIMIT/OFFSET | Short pages, wrong counts/cursors | Apply security scope WHERE before paging |
| Treating filtered list as proving full batch update | Silently skips operations, breaks atomicity | For writes, validate all items then reject/transact |
| Using owner from JSON body as proof of permission | Client can forge owner | Compare against server-stored owner |
| Using `authentication.getName()` when auth comes from unverified header | Untrusted identity | Verify credentials/tokens first |
| Accessing lazy relations in SpEL for N records | N+1/lazy-loading/timeouts | Scoped queries, projections, indexes |
| Returning `Page` and expecting PostFilter to fix total count | Incorrect paging metadata | Paginate over the DB-authorized subset |
| Using annotations to "erase" already-emitted logs/events | Data already leaked before filtering | Never fetch/emit out-of-scope data |
| Treating `@PostAuthorize` and `@PostFilter` as synonyms | Confuses whole-call allow/deny vs per-item filtering | Choose the right annotation for the contract |
| Using only HTTP matchers for all data policies | Does not verify record owner/tenant | Protect at service/repository layers |
| Disabling CSRF because endpoints return JSON | Cookie-authenticated write endpoints face CSRF risk | Evaluate credentials and keep appropriate CSRF |

### 11.1. When SpEL Cannot Resolve filterObject Properly

First check the actual element type in the List. If the List holds `Map.Entry` instead of `Doc` records, `filterObject.owner()` will not exist. If objects have JavaBean getters, use the right accessor; if records, use `owner()`. Never catch exceptions and fall back to `permitAll` just to avoid 403/500.

### 11.2. Results Are Not Filtered Despite Annotations

Check:
- Has `@EnableMethodSecurity` been applied?
- Is the method on a Spring bean and does the call actually pass through the proxy?
- Is the annotation on an intercepted method rather than a self-invocation?
- Is `prePostEnabled=false` configured somewhere?
- Is the caller testing the real bean or calling a manually `new`-created object directly?
- If using async/other threads, is `SecurityContext` safely propagated, or was authentication lost?

Do not fix this by calling `SecurityContextHolder.setContext(...)` arbitrarily inside a thread pool without cleanup; Spring provides security-context propagation mechanisms for async tasks.

### 11.3. PostFilter and Exceptions

If the method body throws an exception before returning a List, postfiltering **cannot produce a safe List to return**. Handle repository/service errors appropriately rather than catching all exceptions and returning an empty list to hide system failures. An empty response due to no permissions/no data is different from a database outage.

## 12. Strategy for Choosing Annotations by Use Case

| Use Case | Preferred Approach |
| --- | --- |
| Allow/deny the entire method before execution | `@PreAuthorize` |
| Allow/deny a single returned object based on returnObject | `@PostAuthorize` when needed; consider early checks |
| Preview from a **small** collection where dropping items is allowed | `@PreFilter` |
| Filter a **small, in-memory** result set without sensitive pre-filter data | `@PostFilter` may fit |
| Read tens of thousands / millions of records across users | Owner/tenant-scoped DB queries, pagination |
| Read single record by ID | Repository query by ID + owner/tenant; supplementary method policy |
| Batch update/delete requiring atomicity | Authorize entire batch; reject if any item is unauthorized |
| Data requiring strict row-level security | Server-side policy + DB/RLS/query scope + tests |
| Aggregate reports/counters | Compute aggregations on DB-authorized sets, never aggregate before PostFilter |
| Large-scale async/stream processing | Source-scoped authorization, bounded streaming, and context control |

A stable production model is typically **HTTP authentication + method-level coarse permissions + repository-level owner/tenant scoping + service business-policy checks**. Never use a single annotation to replace all four layers.

## 13. Pre-Production Checklist

**Correctness and Security:**

1. `@EnableMethodSecurity` is active and tested through proxies.
2. Distinguish per-element filtering from whole-method authorization.
3. Never use client-supplied owner/tenant as proof of permission.
4. For batch writes, clearly decide **filter subset** vs **reject all**; never silently drop items.
5. Method security is not bypassed via self-invocation/private/final methods.
6. Never pass unauthorized data through logs, caches, message buses, or exports before filtering.
7. HTTP authorization/CSRF match the authentication mechanism.
8. Tests cover users A/B, anonymous, missing permissions, other tenants, and empty collections.

**Performance and Data Lifecycle:**

9. Never call `findAll()` on large tables and then PostFilter to return one page.
10. Constrain owner/tenant in queries with appropriate indexes.
11. Count/cursor/sort queries use the **exact same scope** as data-fetching queries.
12. Avoid N+1/lazy expressions in SpEL over large datasets.
13. Never prefilter shared/unmodifiable collections when elements must be removed.
14. Measure row counts/queries, allocations, latency, and memory at realistic scale.
15. Have a permission/tenant update strategy preventing TOCTOU during writes.
16. Distinguish infrastructure errors from missing records/permissions; never swallow exceptions.

## 14. Self-Check Questions

**Question 1.** Does `@PreFilter` run before or after the method body?

**Answer:** Before the method body, on elements of the selected collection parameter. Elements failing the expression are removed from the input the method receives.

**Question 2.** Does `@PostFilter` run before or after a database query inside the method?

**Answer:** After the method body completes and produces a result. If the method queries the entire table, data loading has already occurred before filtering.

**Question 3.** What is `filterObject`?

**Answer:** It is the individual element currently being evaluated in the input/output collection, not the entire List.

**Question 4.** Given a List with alice, bob, alice and user alice, what does an owner-filtering expression return?

**Answer:** Alice's two elements; in this lesson's example, id 1 and id 3. For user charlie who has no elements, the result can be an empty List.

**Question 5.** If the caller passes `List.of(...)` as input to `@PreFilter`, what should you watch out for?

**Answer:** That List is immutable. Filtering may need to remove elements, so use a defensive mutable copy or design an appropriate query.

**Question 6.** When a batch contains one unauthorized item, is using `@PreFilter` and returning success always right?

**Answer:** No. It can silently drop the item, breaking atomicity and the contract. Important write operations typically need to reject the entire batch when any item is unauthorized.

**Question 7.** Is reading 1,000,000 rows and `@PostFilter`ing down to 40 efficient?

**Answer:** No. The DB, network, and JVM still process one million records; scope at the query and then paginate.

**Question 8.** Why can LIMIT 20 before PostFilter break pagination?

**Answer:** Because the first 20 rows across the table may contain only a few rows belonging to the user; counts, cursors, and pageSize no longer reflect the authorized set.

**Question 9.** Does `@PreFilter` automatically optimize an earlier query in the caller?

**Answer:** No. If the caller already invoked findAll, the data is already loaded. Prefiltering only runs when the annotated method call is intercepted.

**Question 10.** Why is `this.filteredMethod()` in the same bean suspicious?

**Answer:** The call may bypass the Spring AOP proxy, meaning the method-security interceptor does not run.

**Question 11.** When filtering `filterObject.owner() == authentication.name`, is an `owner` field from client JSON trustworthy?

**Answer:** No. Clients can forge `owner`; verify actual ownership from server-side data or the DB.

**Question 12.** How does `@PostAuthorize` differ from `@PostFilter`?

**Answer:** PostAuthorize decides whether to allow/deny the single result/whole method, whereas PostFilter filters individual elements of a collection output.

**Question 13.** Can `@PostFilter` replace tenant isolation across all APIs?

**Answer:** No. Queries/policies must enforce tenant boundaries before data leaves the DB, including pagination and all other data paths.

**Question 14.** A POST using session cookies gets 403 even though the method has a valid `@PreFilter`. Why might that happen?

**Answer:** The CSRF filter may reject it before reaching the method. Inspect the security filter chain and CSRF instead of assuming the element filter expression caused it.

**Question 15.** For a method returning `Page`, should you expect PostFilter to adjust the total count automatically?

**Answer:** No. For accurate pagination and scalability, apply the authorization WHERE clause before DB sort/limit/count, then return a `Page` over the authorized subset.

**Remember:** **`@PreFilter` trims input elements entering a method and `@PostFilter` trims output elements returned to the caller, yet neither replaces permission-scoped queries at the data source. For large sets, filter owner/tenant directly in the DB, paginate after filtering, keep service authorization, and avoid side effects prior to filtering.**