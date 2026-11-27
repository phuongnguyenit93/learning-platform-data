# HTTP `409 Conflict` in Spring Data REST: Data Integrity Violations and Optimistic Locking

## Objectives

HTTP `409 Conflict` indicates that the request could not be applied because of a conflict with the current state of the target resource or data. In Spring Data REST, two error groups commonly mapped to `409` are:

- Integrity constraint violations reported by the persistence layer, typically wrapped in `DataIntegrityViolationException`.
- Optimistic locking conflicts, represented by `OptimisticLockingFailureException`.

These two groups should be distinguished from input validation errors and from the HTTP `If-Match` precondition. They can produce different statuses even though all involve data that is no longer valid for the operation.

## 1. Distinguishing status codes

| Situation | Key symptom | Commonly used status |
| --- | --- | --- |
| Data violates a database constraint, such as duplicate unique key or deleting a referenced record | `DataIntegrityViolationException` or `DuplicateKeyException` | `409 Conflict` |
| Record was updated/deleted by another transaction after the request read an older version | `OptimisticLockingFailureException` | `409 Conflict` |
| Spring Data REST validator rejects the entity before saving | `RepositoryConstraintViolationException` | `400 Bad Request` |
| Bean Validation or invalid JSON body | `ConstraintViolationException`, `HttpMessageNotReadableException` | `400 Bad Request` |
| Client sends `If-Match` with a stale ETag | Current ETag does not match the conditional header | `412 Precondition Failed` |
| Client sends `If-None-Match` matching the current ETag on GET | Resource has not changed | `304 Not Modified` |

Spring Data REST provides `RepositoryRestExceptionHandler` to handle errors from framework-generated controllers. Under default configuration, persistence-layer constraint errors and optimistic locking errors are returned as `409` conflicts. If the application has its own `@ControllerAdvice`, check handler order and scope because custom advice can alter the outcome.

A common pitfall: `RepositoryConstraintViolationException` **extends** `DataIntegrityViolationException`, yet it is thrown when a Spring `Validator` reports errors. This is a validation error and should remain `400`; do not let a broad handler for `DataIntegrityViolationException` accidentally convert it to `409`.

## 2. Database constraint conflicts

`DataIntegrityViolationException` is a Spring DAO exception for cases where a SQL statement is rejected because data violates an integrity rule. Common examples:

- Duplicate primary key or unique constraint value.
- `NULL` written to a required column.
- Deleting a parent record still referenced by another record via a foreign key.
- Value failing a check constraint.

`DuplicateKeyException` is a more specific subclass, though handling at the `DataIntegrityViolationException` level is preferable when supporting multiple databases and constraint types.

Example JPA entity with a unique product SKU:

~~~java
@Entity
class Product {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Version
    private Long version;
}
~~~

When the schema actually has a unique constraint on `sku`, a request creating an already existing product will be rejected by the database. Spring translates the persistence error into `DataIntegrityViolationException`; Spring Data REST can return:

~~~http
HTTP/1.1 409 Conflict
~~~

Example request:

~~~bash
curl -i -X POST http://localhost:8080/products \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BOOK-001"}'
~~~

Sending the same `BOOK-001` code again once the constraint is in place triggers a conflict. The client should choose another code or display an appropriate business reason.

**Note on schema:** `@Column(unique = true)` describes the JPA mapping and can generate the constraint when the application auto-generates schema. In real environments, confirm migrations created the corresponding unique index/constraint. Checking `existsBySku(...)` before insert cannot replace a database constraint because two concurrent requests can still both pass that check.

## 3. Optimistic locking and `@Version`

Optimistic locking detects two operations concurrently modifying the same version of data. It does not hold database locks while the user reads and edits.

With a versioned entity:

~~~java
@Entity
class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;
}
~~~

When using Spring Data JPA, use `jakarta.persistence.Version`. With other Spring Data modules, use `org.springframework.data.annotation.Version` per that module's guide.

When saving a versioned entity, Spring Data checks the version in the persistence store. An update conceptually takes the form:

~~~sql
UPDATE product
SET name = ?, version = 8
WHERE id = ? AND version = 7
~~~

If another transaction already moved the version from `7` to `8`, the statement from a client holding version `7` updates zero rows. Spring Data throws `OptimisticLockingFailureException`. The `CrudRepository.save()` documentation also states this exception is thrown when the entity's version differs from the stored version; delete operations on versioned entities can encounter similar errors.

Example two-client flow:

1. Clients A and B both read the product at version `7`.
2. A saves first; the data is updated and the version increments to `8`.
3. B submits its stale entity copy with version `7`.
4. The persistence layer detects the version mismatch and throws `OptimisticLockingFailureException`.
5. When the exception goes through Spring Data REST's default handler, client B receives `409 Conflict`.

The client must not blindly resend the old payload in an infinite loop. Re-read the resource, compare the user's changes against the latest data, merge if valid, and only then resubmit.

## 4. ETag and `If-Match`: when 412 is returned

Spring Data REST uses the `@Version` field to generate the `ETag` header for a resource. Clients can use this ETag as a precondition on `PUT`, `PATCH`, or `DELETE`.

Reading the resource:

~~~http
GET /products/42

HTTP/1.1 200 OK
ETag: "7"
~~~

Client sends changes with the ETag it read:

~~~bash
curl -i -X PATCH http://localhost:8080/products/42 \
  -H 'If-Match: "7"' \
  -H 'Content-Type: application/json' \
  -d '{"name":"New name"}'
~~~

If another client has updated the resource and the current ETag is no longer `"7"`, Spring Data REST rejects the operation with `412 Precondition Failed`. This is the result of the HTTP `If-Match` precondition, distinct from an optimistic locking exception thrown by the repository.

Therefore, when debugging a concurrent update request:

- `409`: the persistence layer/repository reported a conflict, such as `OptimisticLockingFailureException`.
- `412`: the `If-Match` header sent by the client does not match the current ETag.

For GET, `If-None-Match` has a different effect: if the ETag matches, Spring Data REST returns `304 Not Modified` without resending the representation. Only use an ETag with the exact URI and query parameters that produced it.

## 5. Keeping validation errors at 400

Spring Data REST allows registering `Validator` beans by event-based bean name. For example, a bean named `beforeCreateProductValidator` is invoked before creating a `Product`; `beforeSaveProductValidator` is invoked before saving an existing entity. You can also register manually via `RepositoryRestConfigurer.configureValidatingRepositoryEventListener(...)` and `ValidatingRepositoryEventListener.addValidator(...)`.

When a validator rejects an entity, Spring Data REST throws `RepositoryConstraintViolationException`. This exception provides `getErrors()` to retrieve validation errors and inherits from `DataIntegrityViolationException`. The default handler distinguishes it from database constraint errors and returns `400 Bad Request`.

If the application writes its own `@RestControllerAdvice`, declare a specific handler for `RepositoryConstraintViolationException` before handling the broader `DataIntegrityViolationException`:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(RepositoryConstraintViolationException.class)
    ResponseEntity<ApiError> validation(
            RepositoryConstraintViolationException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_FAILED",
                        "Submitted data is invalid"));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ApiError> integrity(
            DataIntegrityViolationException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("DATA_CONFLICT",
                        "Data conflicts with the current state"));
    }

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<ApiError> optimisticLock(
            OptimisticLockingFailureException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("STALE_VERSION",
                        "Resource has been updated; reload before retrying"));
    }
}
~~~

`ApiError` in the example is an application-defined response DTO. Add custom handlers only when you need a stable response format or custom business messages; if used, verify the advice actually applies to Spring Data REST endpoints. Do not return raw SQL, table names, internal constraint names, or stack traces to clients.

## 6. Testing the behavior

Test both repository-level exceptions and status codes at the HTTP boundary. Use a test database with real constraints; for constraint violations, `saveAndFlush()` forces SQL execution immediately so the test can observe the error.

### 6.1. Duplicate unique key returns 409

With `ProductRepository` and a unique constraint on `sku`, save a product first and then POST the same SKU through the Spring Data REST-exported endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductRestConflictTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProductRepository repository;

    @Test
    void duplicateSkuReturns409() throws Exception {
        Product existing = new Product();
        existing.setSku("SKU-001");
        repository.saveAndFlush(existing);

        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"SKU-001\"}"))
            .andExpect(status().isConflict());
    }
}
~~~

This test verifies the path from database constraint through exception translation to HTTP response. Seed data must be committed/flushed before the request; avoid letting a test transaction obscure when the constraint is checked.

### 6.2. Versioned entity rejects stale copy

In a persistence test, read the entity into a stale copy, update and flush a fresh copy, then try to save the stale copy:

~~~java
Product stale = repository.findById(id).orElseThrow();
entityManager.detach(stale);

Product current = repository.findById(id).orElseThrow();
current.setName("New version");
repository.saveAndFlush(current);

stale.setName("Stale version");
assertThatThrownBy(() -> repository.saveAndFlush(stale))
        .isInstanceOf(OptimisticLockingFailureException.class);
~~~

This test verifies optimistic locking at the repository level. Add an integration test through the Spring Data REST endpoint to verify the exception maps to `409` under the actual application configuration.

### 6.3. Stale ETag returns 412

1. Call GET on the resource and save the `ETag` header value.
2. Update the entity via the repository to increment its version.
3. Call `PATCH` on the same URI with `If-Match` containing the stale ETag.
4. Assert `status().isPreconditionFailed()`.

This test verifies the HTTP conditional path and does not replace the repository test in section 6.2.

### 6.4. Validators and conditional GET

- Submit an entity violating `beforeCreateProductValidator` and assert `400 Bad Request`.
- Send GET with `If-None-Match` equal to the current ETag and assert `304 Not Modified`.
- For race tests, use two independent transactions/persistence contexts and synchronize reads using `CountDownLatch` or `CyclicBarrier`. Do not rely on random timing; verify one operation wins and the other receives the expected conflict/precondition status for its execution path.

Run tests using your project's build tool, such as `./mvnw test` or `mvn test`.

## 7. Troubleshooting

**Receiving 400 when expecting 409**

- Check the actual exception. If it is `RepositoryConstraintViolationException`, it is an error from a Spring `Validator` and 400 is appropriate.
- If using custom advice, check whether a subclass handler is shadowed by a `DataIntegrityViolationException` or catch-all handler running first.
- Distinguish Bean Validation/JSON binding errors from database-enforced constraints.

**Receiving 412 instead of 409**

- Check whether the request sends `If-Match`.
- Re-read the resource and fetch the fresh ETag; do not reuse an ETag from another URI or an older read.
- If business logic needs conflict detection at the repository level, inspect the version field and actual save path; do not change 412 to 409 merely to make statuses identical.

**Receiving 500 on duplicate writes or stale versions**

- Inspect the exception class and cause chain in the logs; use `getMostSpecificCause()` to find the underlying persistence error.
- Verify the database schema has the real constraint and Spring Data/JPA is translating exceptions as expected.
- Check whether the exception is wrapped in a custom exception or caught and rethrown as a generic error.
- For `@Version`, confirm the annotation matches the module, the version field is mapped, and operations go through repository methods supporting optimistic locking. Some bulk updates/queries may bypass versioning.

**Database does not report an error on duplicate creation**

- Verify the unique constraint/index on the running database, not just annotations on the entity.
- Do not rely on `existsBy...` as the sole duplicate guard; only a database constraint handles two concurrent inserts safely.

**Error messages leak database details**

- Log full exceptions on the server with a correlation/request ID.
- Return stable error DTOs such as `DATA_CONFLICT` or `STALE_VERSION`; do not expose SQL, sensitive constraint names, or stack traces.
- Map to `409` only when it is a conflict resolvable by the client. Mapping/schema errors or operational failures should be categorized separately rather than turning every `DataAccessException` into a conflict.

## 8. Official documentation

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): `@Version`, `ETag`, `If-Match`, `If-None-Match`, curl examples, and 412/304 behavior. The documentation also notes the POJO ETag example is taken from unit tests.
- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): registering validators by bean name or via `RepositoryRestConfigurer`.
- [Spring Data REST API — RepositoryConstraintViolationException](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): exception thrown when a Spring `Validator` reports errors and its inheritance from `DataIntegrityViolationException`.
- [Spring Data REST API — RepositoryRestExceptionHandler](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html): default handler for Spring Data REST controllers.
- [Spring Data Commons API — CrudRepository](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/CrudRepository.html): contract of `save()`/`delete()` and `OptimisticLockingFailureException` on version mismatch.
- [Spring Framework API — DataIntegrityViolationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html): meaning of integrity constraint violation exceptions.
- [Spring Framework API — OptimisticLockingFailureException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/OptimisticLockingFailureException.html): exception when optimistic locking fails.

When applying this to a project, align the documentation with the Spring Data REST/Spring Data versions declared in your build and any existing `@ControllerAdvice` beans, as they determine which handler actually processes requests.