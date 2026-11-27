# Restricting Exposure of Write Queries or Resource-Intensive Queries

Spring Data REST can automatically expose repository query methods as endpoints under the **search** resource. This mechanism is convenient for read queries that can be safely invoked via HTTP GET. However, some methods are intended only for internal use, mutate data, or execute resource-intensive queries and should not appear in the public API.

The direct method-level control is **@RestResource(exported = false)**. This annotation keeps the method on the repository so services or internal code can continue calling it, while instructing Spring Data REST not to expose the corresponding query resource.

## Objectives

After this lesson, you will be able to:

- Understand where Spring Data REST exposes query methods and which HTTP method they use.
- Hide an individual query method using **@RestResource(exported = false)**.
- Distinguish hiding a query method from hiding an entire repository or disabling a CRUD HTTP method.
- Safely handle data-mutating methods such as queries with **@Modifying**.
- Reduce risks from resource-intensive read queries through pagination, size limits, query design, and access control.
- Verify the API after changing exposure.

## 1. How are query methods exposed?

Suppose an order management repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);
}
~~~

By default, Spring Data REST can expose query methods based on the method name. With the default repository path orders, the search endpoint looks like:

~~~text
/orders/search/findByStatus?status=PAID
~~~

If the repository is customized:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);
}
~~~

then the query method resides under:

~~~text
/orders/search/findByStatus
~~~

The search resource at /orders/search returns links to the exposed query methods. The HAL representation may look like:

~~~json
{
  "_links": {
    "findByStatus": {
      "href": "http://localhost:8080/orders/search/findByStatus{?status}"
    }
  }
}
~~~

Clients discover endpoints via relations and hrefs in HAL rather than having to guess URL names.

Spring Data REST documentation defines the Search resource and Query Method resources as read-only resources supporting **GET**. A query method resource executes the corresponding repository method and returns the query results.

## 2. Hiding a single query method

If a method is strictly for internal use or should not be callable over REST, place **@RestResource(exported = false)** directly on the method:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    @RestResource(exported = false)
    List<Order> findInternalRiskReviewCandidates(
            RiskLevel riskLevel);
}
~~~

In this example:

- findByStatus continues to be exposed under /orders/search.
- findInternalRiskReviewCandidates remains a repository method and internal Java code can call it.
- Spring Data REST does not expose a query resource for findInternalRiskReviewCandidates.
- Other CRUD methods and query methods on the repository are not hidden simply because one method is marked exported = false.

This is the right choice when only specific queries need to stay internal.

You can combine **@Query** with this annotation:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(exported = false)
    @Query("""
        select o
        from Order o
        where o.riskLevel = :riskLevel
          and o.reviewed = false
        """)
    List<Order> findInternalRiskReviewCandidates(
            @Param("riskLevel") RiskLevel riskLevel);
}
~~~

The query can still be called from internal services or jobs. The annotation only controls whether Spring Data REST exposes the method.

## 3. Hiding an entire repository when needed

If a repository is not an API resource at all, use **@RepositoryRestResource(exported = false)** at the interface level:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {

    List<AuditRecord> findByActorId(String actorId);
}
~~~

Then the repository is not exposed by Spring Data REST as a repository resource. Its query methods will not appear under a search resource either.

Distinguish the two levels:

| Setting | Scope |
| --- | --- |
| @RestResource(exported = false) on a method | Hides a single query method or specific method |
| @RepositoryRestResource(exported = false) on a repository | Hides the repository resource and its child resources |
| Not declaring a method on the REST repository | The method is not part of the exposed repository contract |
| RepositoryDetectionStrategy | Determines which repositories are eligible to be discovered/exposed at the repository level |

Do not use the repository-level annotation just to hide one query if the repository's other endpoints still need to be used.

## 4. Restricting queries that mutate data

A repository can contain queries designed to update data:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Modifying
    @Transactional
    @Query("""
        update Account a
        set a.status = :status
        where a.id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") AccountStatus status);
}
~~~

This is a data-writing operation, even though it is declared as a query method. Do not put an operation with side effects into a read-only search API.

Spring Data REST describes query method resources as GET-only. Therefore, keep data-writing methods in the internal repository/service layer and mark them non-exported if the exporter might recognize them as query methods:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Modifying
    @Transactional
    @RestResource(exported = false)
    @Query("""
        update Account a
        set a.status = :status
        where a.id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") AccountStatus status);
}
~~~

When this operation needs to be provided to clients, create a dedicated command endpoint with an appropriate HTTP method and request contract, and invoke a service:

~~~java
@Service
public class AccountService {

    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeStatus(Long id, AccountStatus status) {
        int updated = repository.updateStatus(id, status);
        if (updated == 0) {
            throw new EntityNotFoundException(
                    "Account not found: " + id);
        }
    }
}
~~~

Example controller:

~~~java
@RestController
@RequestMapping("/account-commands")
public class AccountCommandController {

    private final AccountService service;

    public AccountCommandController(AccountService service) {
        this.service = service;
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAuthority('ACCOUNT_STATUS_WRITE')")
    public ResponseEntity<Void> changeStatus(
            @PathVariable Long id,
            @RequestBody ChangeAccountStatusRequest request) {

        service.changeStatus(id, request.status());
        return ResponseEntity.noContent().build();
    }
}
~~~

The controller illustrates an explicit command API. Use DTOs, validation, transaction boundaries, and access permissions according to the application's actual business rules. Do not place update/delete statements behind a search URL just because Spring Data can execute them.

## 5. Restricting resource-intensive read queries

Not every read query method is suitable for exposure. A query can be resource-intensive when it:

- Scans large tables without selective filter conditions.
- Joins many tables or fetches an overly broad object graph.
- Computes total record counts over very large datasets.
- Sorts on columns without suitable indexes.
- Returns an unbounded collection.
- Runs complex aggregate reports or long historical queries.
- Allows clients to send date ranges, keywords, or conditions that make the query scope too wide.

If a query only serves internal reporting or a special operational flow, hide the method:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(exported = false)
    @Query("""
        select new com.example.ReportRow(
            o.region,
            sum(o.totalAmount),
            count(o.id)
        )
        from Order o
        where o.createdAt >= :from
          and o.createdAt < :to
        group by o.region
        """)
    List<ReportRow> calculateInternalRegionalReport(
            @Param("from") Instant from,
            @Param("to") Instant to);
}
~~~

Internal services can invoke this method when appropriately authorized. If the report needs to be provided to clients, design a dedicated endpoint with time-range limits, access control, and an appropriate execution mechanism; for very heavy tasks, consider asynchronous processing and returning a job ID for clients to poll status.

## 6. Pagination helps limit the amount of returned data

For read queries that must be exposed, prefer a signature with **Pageable**:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Page<Order> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
~~~

Spring Data REST can generate a URI template containing pagination parameters:

~~~text
/orders/search/findByStatus?status=PAID&page=0&size=20
~~~

Common parameters:

| Parameter | Meaning |
| --- | --- |
| page | Page number, zero-based |
| size | Requested number of items per page |
| sort | Property and sort direction |

You can set a maximum page size in Spring Data REST configuration:

~~~java
@Configuration
public class RestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setMaxPageSize(100);
    }
}
~~~

The value 100 is only an example. Choose a limit based on response payload size, database load, and the application's SLA.

Pagination limits the number of elements returned in a single request, but does not automatically make the query cheap. A query can still be resource-intensive due to joins, sorting, counting, or missing indexes. For large reports, consider dedicated queries, DTO projections, proper indexes, or background processing.

## 7. Do not confuse hiding queries with access control

**@RestResource(exported = false)** controls resource exposure via Spring Data REST. It is not an authorization mechanism.

Distinguish between:

| Mechanism | Effect |
| --- | --- |
| @RestResource(exported = false) | Prevents exposing a method/resource via Spring Data REST |
| @RepositoryRestResource(exported = false) | Prevents exposing a repository resource |
| Spring Security | Authenticates and decides whether a principal is permitted to call an endpoint |
| @PreAuthorize | Checks permissions at the method/service/controller level |
| Validation and business rules | Controls input data and valid states |
| Rate limits, timeouts, and load limits | Restricts request frequency or resource execution time |

If a method is hidden from Spring Data REST but invoked from another controller, that controller must still enforce authorization. Other applications, batch jobs, or internal code can also still call the repository method directly.

If returned data is sensitive, also control exposed representations, projections, and associations. Hiding one query method does not automatically protect the same data when accessed via another endpoint or projection.

## 8. Distinguishing hiding a query method from hiding a CRUD HTTP method

Repository CRUD methods can back multiple HTTP operations. For example, save can back POST on the collection resource and PUT/PATCH on the item resource.

To disable a CRUD method, you can override the corresponding method and place **@RestResource(exported = false)** on the overridden method. However, you must identify the actual overloads used by Spring Data REST.

Example hiding delete operations via the repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);
}
~~~

This is only an illustrative example for one signature. Depending on the Spring Data version and parent interfaces, there may be other delete overloads such as delete(entity), deleteAllById(…), deleteAll(…), or deleteAll(iterable). To remove HTTP DELETE capability completely, verify the exact methods used by the repository module and test at runtime.

If you only want to disable an HTTP method on a group of resources without changing the repository contract, Spring Data REST provides **ExposureConfiguration** to configure exposure by domain type or resource kind.

Example disabling PATCH on item resources:

~~~java
@Configuration
public class RestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .withItemExposure((metadata, methods) ->
                methods.disable(HttpMethod.PATCH));
    }
}
~~~

This configures item-resource scope according to the declared rule. If you only want to restrict one domain type, use the per-domain-type configuration rather than applying it globally. Check the API of the Spring Data REST version in use because overloads and rules may change across versions.

## 9. Customizing path is not equivalent to hiding a method

You can change the URL and link relation of a query method with **@RestResource(path = ..., rel = ...)**:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(path = "by-status", rel = "ordersByStatus")
    Page<Order> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
~~~

Then the endpoint can be:

~~~text
/orders/search/by-status?status=PAID&page=0&size=20
~~~

The link relation in HAL is ordersByStatus.

Configuring path/rel only renames the path and link relation. The method is still exposed. To hide the method, you must use exported = false.

The attributes can be combined when needed, though for an unexported method, path and rel do not create a public endpoint:

~~~java
@RestResource(
    path = "internal-report",
    rel = "internalReport",
    exported = false
)
Page<ReportRow> calculateInternalReport(
        ReportFilter filter,
        Pageable pageable);
~~~

## 10. Verifying the API after restricting exposure

After modifying annotations or configuration, check both discovery links and direct endpoints.

**Step 1 — Read the collection resource**

~~~http
GET /orders
Accept: application/hal+json
~~~

Verify the search link appears when the repository still has at least one exposed query method.

**Step 2 — Read the search resource**

~~~http
GET /orders/search
Accept: application/hal+json
~~~

Confirm public query methods still have links, while methods marked exported = false do not appear.

**Step 3 — Call a public query**

~~~http
GET /orders/search/findByStatus?status=PAID&page=0&size=20
Accept: application/hal+json
~~~

Confirm the query returns the expected results and page metadata.

**Step 4 — Try the hidden endpoint**

Request the former URI of the hidden method. The resource is no longer exposed; normally there is no discovery link and direct requests are no longer routed to that query method. Verify the actual status for your application version, typically 404.

**Step 5 — Verify internal methods**

Run unit/integration tests or call the service to confirm internal code can still use the repository method after hiding it from REST.

**Step 6 — Check permissions and load**

Test an unauthorized user, requests with overly broad data ranges, page sizes exceeding the limit, and query timeout cases. Confirm protective limits are enforced.

Quick verification example with curl:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/orders/search
~~~

Do not rely solely on the absence of a link in HAL. Call the old URL directly to verify the exporter no longer exposes the route, and audit other endpoints that could access the same data.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Query still appears in /search | Annotation placed mistakenly on repository or field instead of method; application has not loaded the new build | Place @RestResource(exported = false) directly on the query method, rebuild, and restart |
| Method hidden but internal service cannot call it | Method signature or repository wiring was altered when editing the interface | Keep the method on the interface and change only the exported attribute |
| Hid one query but the entire repository vanished | Used @RepositoryRestResource(exported = false) at interface level | Move the annotation down to the method to hide |
| Heavy query still runs through another endpoint | Same data is accessed via collection, projection, custom controller, or another endpoint | Inventory data access paths and apply authorization/limits at each one |
| Result returns too much data | Method does not support Pageable or page size limit is too high | Use Pageable, configure max page size, and limit responses |
| Query remains slow despite pagination | Expensive joins, sorts, counts, or query plan | Inspect the execution plan, indexes, projections, and how total records are counted |
| GET causes data mutation | Method designed with side effects was placed on a read query path | Hide the method, move the command to an endpoint with an appropriate HTTP method, and protect with authorization |
| Disabled a CRUD method yet HTTP method still works | Another overload is used to back the resource | Check Repository resources reference and actual method exposure in the running version |

## 12. Implementation workflow

1. List the query methods currently appearing under /search.
2. Classify each method: regular read, resource-intensive report, sensitive query, or operation with side effects.
3. For internal-only queries, add @RestResource(exported = false) on the method.
4. For completely internal repositories, consider @RepositoryRestResource(exported = false).
5. For read queries that must be exposed, design bounded parameters, Pageable, and max page size.
6. For data-writing queries, keep them in services/repositories and provide a separate command endpoint if clients need them.
7. Apply authorization, validation, timeouts, and rate limits according to risk level.
8. Inspect search links, call hidden endpoints directly, and run tests for internal call paths.
9. Check query plans and load logs for resource-intensive query endpoints.

## 13. Quick checklist

- [ ] Identified which methods are exposed under /search.
- [ ] Write queries or queries with side effects are not exposed in the public search API.
- [ ] Internal-only queries have @RestResource(exported = false).
- [ ] Entire repository is hidden only when none of its REST resources need exposure.
- [ ] path/rel are not confused with exported.
- [ ] Public read queries have reasonable filter scope and pagination.
- [ ] Appropriate max page size is configured.
- [ ] Sorts, counts, joins, and indexes have been checked for heavy queries.
- [ ] Authorization is enforced on controllers/services and other access paths.
- [ ] HAL discovery, direct URLs, HTTP statuses, and internal call paths have been tested.

## 14. Key takeaways

To restrict exposure of a query method, place the annotation on that method itself:

~~~java
@RestResource(exported = false)
List<Order> findInternalRiskReviewCandidates(
        RiskLevel riskLevel);
~~~

The method still exists on the repository and can be called by internal code. Spring Data REST does not expose that method's query resource.

Use **@RepositoryRestResource(exported = false)** when an entire repository needs to be hidden. For resource-intensive read queries that still must be public, combine Pageable, page size limits, properly indexed queries, timeouts, and authorization. For data-writing operations, provide a dedicated command endpoint following HTTP semantics with explicit access control.

## References

- Spring Data REST Reference — Configuring the REST URL Path, Hiding Certain Repositories, Query Methods, or Fields: https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html
- Spring Data REST Reference — Repository resources, Search Resource and Query Method Resource: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Customizing supported HTTP methods and repository exposure: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr.html
- Spring Data REST API — RestResource: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RestResource.html
- Spring Data JPA Reference — Modifying Queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
