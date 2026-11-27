# Optional, Empty Collections, and Non-Unique Result Errors

## 1. A query can return 0, 1, or many documents

In **Spring Data MongoDB**, repositories let a Java application perform CRUD on collections without writing every `MongoTemplate` operation manually. However, a repository method does more than describe **search criteria**: its **return type** also expresses an expectation about **result count**.

Suppose a user management system has these operations:

- Look up an account by `_id`: at most one document because MongoDB guarantees `_id` is unique within a collection.
- Look up an account by normalized email: business rules require at most one account per email.
- Find users by nickname: multiple accounts can share the same nickname.
- List active users: there may be none, or there may be many.

If a method declares `Optional<User> findByNickname(...)` while nicknames are allowed to repeat, the method promises a single result that the data does not guarantee. This is the root cause of **`IncorrectResultSizeDataAccessException`** in query methods expecting a single result.

This lesson belongs to the **Repository CRUD** chapter of the **SPRING_DATA_MONGODB** module, where Spring Data connects, maps documents, and queries MongoDB via repositories or `MongoTemplate`. We focus on four decisions: **choosing the right return type, handling empty results, enforcing uniqueness, and distinguishing repository contracts from template/reactive API behavior**.

## 2. Return type is a cardinality contract

*Cardinality* is the number of records matching a query condition. When designing a method, know the valid business cardinality rather than judging solely from a handful of current records.

| Method return type | Zero results | One result | Multiple matching results |
| --- | --- | --- | --- |
| `Optional<T>`, single-result query | `Optional.empty()` | `Optional.of(entity)` | Result size error for an unlimited single-result query |
| `T`, single-result query | May be `null` or throw if non-null constraints are enabled depending on config | `entity` | Result size error for an unlimited single-result query |
| `List<T>` / `Collection<T>` | Empty collection, not `null` | Single-element collection | Multi-element collection |
| `Page<T>` | Empty page | Page with element | Page capped at page size, with pagination metadata |
| `Slice<T>` | Empty slice | Slice with element | Slice limited by pageable, with next-page indicator |
| `boolean existsBy...` | `false` | `true` | `true`; does not return document payload |
| `long countBy...` | `0` | `1` | Count of matching documents |
| `Mono<T>` in reactive repository | Completes without emitting a value | Emits one value then completes | Single-result contract; execution behavior must be tested, not used for listing multiple records |
| `Flux<T>` | Completes without emitting items | Emits one item | Emits multiple items |

The rows above describe **repository methods intended to return one result**. Methods explicitly bounded with `First`/`Top` are different: they intentionally pick a single document from a potentially multi-match set. Queries implemented via `MongoTemplate` also have distinct semantics.

### 2.1. Not found is not a system error

An `Optional.empty()` can be completely normal: a missing ID, an unregistered user, or a filter with no matches yet. Likewise, `List.of()` is a valid search outcome when 0 records match.

Distinguish three cases:

1. **No data:** the query succeeded, returning 0 documents.
2. **Data exists but is not unique:** multiple documents match when the contract permits at most one.
3. **MongoDB access error:** timeout, connection drop, authentication failure, mapping error, or rejected command.

These three cases require separate handling paths. Never collapse all of them into `null` or HTTP 404.

### 2.2. Optional does not enforce data uniqueness

`Optional<T>` is a Java wrapper representing the **presence or absence** of a value. It **does not create a unique index**, does not enforce business rules, and does not stop two documents with the same email from being written.

`Optional<User> findByEmailKey(String emailKey)` only has a valid contract if the data is engineered so the query returns at most one result. Guaranteeing that requires both write-path rules and a corresponding constraint in MongoDB.

## 3. Domain example: users, email, and nickname

Suppose collection `app_users` stores:

```javascript
{
  _id: "user-101",
  emailKey: "lan@example.com",
  nickname: "luna",
  status: "ACTIVE",
  createdAt: ISODate("2026-11-20T08:00:00Z")
}
```

`emailKey` is normalized according to application rules. In this example, each `emailKey` must be unique, while `nickname` is allowed to duplicate.

### 3.1. Entity

```java
package example.users;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

enum UserStatus {
    ACTIVE,
    INACTIVE
}

@Document(collection = "app_users")
public class AppUser {

    @Id
    private String id;

    @Indexed(unique = true)
    private String emailKey;

    private String nickname;

    private UserStatus status;

    private Instant createdAt;

    public AppUser() {
    }

    public AppUser(
            String id,
            String emailKey,
            String nickname,
            UserStatus status,
            Instant createdAt) {
        this.id = id;
        this.emailKey = emailKey;
        this.nickname = nickname;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getEmailKey() {
        return emailKey;
    }

    public String getNickname() {
        return nickname;
    }

    public UserStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

`@Indexed(unique = true)` declares the intent for a unique index in Spring Data metadata. However, **never assume the index already exists in MongoDB**: automatic index creation depends on configuration and Spring Data MongoDB version. Before relying on uniqueness, verify the index on the real collection or create it via migrations/index management.

### 3.2. Repository

```java
package example.users;

import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AppUserRepository
        extends MongoRepository<AppUser, String> {

    // Contract: at most one result per emailKey.
    Optional<AppUser> findByEmailKey(String emailKey);

    // Intentionally included to show the risk: nickname is NOT unique.
    Optional<AppUser> findByNickname(String nickname);

    // List may contain zero elements.
    List<AppUser> findAllByStatus(UserStatus status);

    // List all users sharing the nickname.
    List<AppUser> findAllByNicknameOrderByCreatedAtDescIdDesc(
        String nickname
    );

    // Explicitly pick one document under an intentional sort order.
    Optional<AppUser> findFirstByNicknameOrderByCreatedAtDescIdDesc(
        String nickname
    );

    boolean existsByEmailKey(String emailKey);

    long countByNickname(String nickname);
}
```

These method names illustrate **query derivation**: Spring Data parses method names to construct query conditions. `findByNickname` expresses an expectation of a single entity, whereas `findAllByNickname...` expresses fetching multiple entities. `findFirstByNickname...` caps the result to one and is appropriate only when business rules genuinely want *one representative chosen by sort order*.

## 4. Optional in CRUD: handling absence explicitly

### 4.1. findById returns Optional

`MongoRepository` inherits CRUD operations and provides `findById(ID)` returning `Optional<T>`.

```java
Optional<AppUser> found = repository.findById("user-101");

if (found.isPresent()) {
    AppUser user = found.get();
    System.out.println(user.getEmailKey());
} else {
    System.out.println("User not found");
}
```

Checking `isPresent()` then `get()` is valid, though real services are usually clearer with `map`, `orElseGet`, or `orElseThrow`:

```java
AppUser user = repository.findById(id)
    .orElseThrow(() -> new UserNotFoundException(id));
```

A domain exception can be declared as:

```java
package example.users;

public class UserNotFoundException extends RuntimeException {
    public UserNotFoundException(String id) {
        super("User not found: " + id);
    }
}
```

This separates the business meaning "user does not exist" from MongoDB errors. At the HTTP layer, the application can translate `UserNotFoundException` to **404 Not Found**.

### 4.2. Do not misuse Optional.get()

```java
// Unsafe if ID does not exist:
AppUser user = repository.findById(id).get();
```

When Optional is empty, `get()` throws `NoSuchElementException`. This is not a MongoDB error and can end up returned by default handlers as an obscure server error. Always define explicitly what the application must do when no result is found.

### 4.3. Do not use null or placeholder objects to replace Optional

A misleading pattern:

```java
// Avoid returning a dummy account when not found:
AppUser user = repository.findById(id)
    .orElse(new AppUser("unknown", "none", "guest",
        UserStatus.INACTIVE, java.time.Instant.EPOCH));
```

If that dummy result gets saved back or returned to a client, the application might falsely assume the account exists. For required data, use `orElseThrow`; for optional data, pass `Optional` to an appropriate boundary or use a DTO representing absence.

**Distinguish two layers:** `Optional<AppUser>` is present when the document exists; that **does not guarantee** `user.getNickname()` or optional fields inside the document are non-null.

## 5. Empty collections: valid outcomes for multi-record queries

Suppose no `INACTIVE` accounts exist yet:

```java
List<AppUser> inactive =
    repository.findAllByStatus(UserStatus.INACTIVE);

System.out.println(inactive.isEmpty()); // true
System.out.println(inactive.size());    // 0
```

For repository queries returning collections, Spring Data returns an empty collection when nothing matches; you do not need `if (inactive == null)` checks on standard repository methods.

### 5.1. HTTP APIs should usually represent an empty list as []

A search endpoint:

```java
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users")
class UserSearchController {
    private final AppUserRepository repository;

    UserSearchController(AppUserRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    ResponseEntity<List<AppUser>> search(
            @RequestParam UserStatus status) {
        return ResponseEntity.ok(repository.findAllByStatus(status));
    }
}
```

If no user matches, HTTP can return:

```json
[]
```

For search lists, **200 OK with []** is usually a clean contract: the query succeeded with 0 items. A specific API may define different conventions, but avoid returning 404 merely because a list search matched zero rows. `404` fits when a **single resource** by ID does not exist.

Returning the entity directly here only illustrates collection serialization; production applications should use DTOs and policies to hide fields that must not appear in HTTP responses.

### 5.2. Large lists need pagination

Do not load millions of accounts into RAM just because `findAllByStatus` returns a `List`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<AppUser> findAllByStatus(UserStatus status, Pageable pageable);
```

This method is **an additional declaration inside the repository**, not standalone Java code outside the interface. When calling it:

```java
var pageable = org.springframework.data.domain.PageRequest.of(
    0, 20,
    org.springframework.data.domain.Sort.by(
        org.springframework.data.domain.Sort.Order.desc("createdAt"),
        org.springframework.data.domain.Sort.Order.desc("id")
    )
);

Page<AppUser> page = repository.findAllByStatus(
    UserStatus.ACTIVE, pageable
);

List<AppUser> content = page.getContent();
boolean emptyPage = page.isEmpty();
```

`Page` carries metadata such as total elements and total pages; depending on the query, computing totals has extra cost. If you only need to know whether a next page exists without needing totals, consider `Slice`. Ensure stable sorting, matching indexes, and an appropriate pagination strategy for large datasets.

## 6. When do non-unique result errors occur?

Suppose the collection has two accounts with the same nickname:

```javascript
db.app_users.insertMany([
  {
    _id: "user-201",
    emailKey: "mai@example.com",
    nickname: "luna",
    status: "ACTIVE",
    createdAt: ISODate("2026-11-20T09:00:00Z")
  },
  {
    _id: "user-202",
    emailKey: "linh@example.com",
    nickname: "luna",
    status: "ACTIVE",
    createdAt: ISODate("2026-11-20T09:05:00Z")
  }
]);
```

This data is valid because nickname **is not required to be unique**. Yet the method below expects a single unique entity:

```java
Optional<AppUser> user = repository.findByNickname("luna");
```

Under Spring Data's single-result query contract, multiple matching results can trigger:

```text
org.springframework.dao.IncorrectResultSizeDataAccessException
```

This exception belongs to the **Spring `DataAccessException` hierarchy**. Distinguish it from `NoSuchElementException` (calling `Optional.get()` on an empty Optional) and `DuplicateKeyException` (writing a value that violates a unique index).

### 6.1. Why can't Optional rescue multiple results?

`Optional` represents "presence or absence of **one** object". It cannot hold a list of two objects. When a query matches more than one document and the method is not bounded to one result, the repository cannot arbitrarily pick one while honoring the contract.

If business rules allow duplicate nicknames, change the contract to:

```java
List<AppUser> users =
    repository.findAllByNicknameOrderByCreatedAtDescIdDesc("luna");
```

If business rules want the **most recently created account**, declare a limit and sort order:

```java
Optional<AppUser> latest =
    repository.findFirstByNicknameOrderByCreatedAtDescIdDesc("luna");
```

`findFirstBy...` intentionally selects at most one result. It **does not prove uniqueness** and can mask duplicate records if the application actually requires uniqueness. Sorting by `createdAt` and `id` provides a deterministic tie-breaker when multiple documents share the same timestamp.

### 6.2. Do not hide the bug by catching and ignoring the exception

```java
// Do not do this if business rules require uniqueness:
try {
    return repository.findByEmailKey(emailKey);
} catch (IncorrectResultSizeDataAccessException ex) {
    return Optional.empty();
}
```

This turns **data violating an invariant** into "not found", potentially hiding duplicate accounts or historical data corruption. If email must be unique, investigate the root cause, clean up duplicates, and enforce the constraint in the database.

Some applications may map inconsistent-data errors into a dedicated business response, yet they must always emit observability signals (controlled logs/metrics) and have a remediation plan—never return a fake empty result.

## 7. Enforcing unique results through data and indexes

### 7.1. _id has a built-in unique index

MongoDB maintains a unique index on a collection's `_id` field. Thus `repository.findById(id)` inherently returns at most one document; when empty, the normal cause is simply no matching key.

For other fields such as email, MongoDB **does not enforce uniqueness automatically** unless a corresponding constraint/index exists. `@Indexed(unique = true)` is only metadata; verify the index was actually created.

```javascript
db.app_users.createIndex(
  { emailKey: 1 },
  { unique: true, name: "uk_app_users_emailKey" }
);

db.app_users.getIndexes();
```

If the collection already contains duplicate `emailKey` values, creating the unique index will fail. Resolve duplicates per business policy before applying the constraint.

### 7.2. Normalize data before enforcing uniqueness

`"Lan@Example.com"` and `"lan@example.com"` can be treated as two different keys unless the application applies a normalization rule. A simple example:

```java
import java.util.Locale;

String normalizeEmailKey(String input) {
    return input.trim().toLowerCase(Locale.ROOT);
}
```

This is an **application-specific lookup key convention**, not a complete email canonicalization standard for all systems. Define exact policies for case sensitivity, Unicode handling, local-part/domain rules, and email validity per product requirements.

Another option is MongoDB collation for case-insensitive comparisons, though **queries must specify the collation matching the index** to use that index. Never mix different normalization schemes randomly across code paths so two places disagree on equality.

### 7.3. Unique indexes and null or missing values

With a standard **single-field unique index**, documents with missing fields or BSON null also map to a single unique null key. This can cause index creation to fail when multiple documents lack an email.

For `emailKey`, decide explicitly whether the field is required:

- If required: validate input, compute the normalized value, and backfill per convention before creating the unique index.
- If optional: design a **partial unique index** or a separate key model matching policy, then test null/missing documents and queries.

Never add `sparse` or `partialFilterExpression` merely to "make the index build succeed" without understanding how it affects missing/null documents and uniqueness rules.

### 7.4. Auditing duplicate data before creating an index

```javascript
db.app_users.aggregate([
  { $match: { emailKey: { $type: "string" } } },
  {
    $group: {
      _id: "$emailKey",
      occurrences: { $sum: 1 }
    }
  },
  { $match: { occurrences: { $gt: 1 } } },
  { $sort: { occurrences: -1 } }
]);
```

This aggregation finds duplicate `emailKey` values using **the exact stored string**, without normalizing variants itself. If legacy records contain unnormalized `emailKey` values, reconcile according to policy before concluding no logical duplicates exist. On large collections, `$group` can be resource-heavy; schedule and budget operational resources accordingly.

### 7.5. existsBy does not replace a unique index

A common pattern:

```java
if (!repository.existsByEmailKey(emailKey)) {
    repository.save(newUser);
}
```

Two concurrent requests can both observe `false` and both execute `save`. This is a **check-then-act race condition**. When uniqueness is mandatory, a MongoDB unique index is the final safeguard. The application handles duplicate-write errors (such as `DuplicateKeyException`) and returns an appropriate response, commonly **409 Conflict** for duplicate resource creation.

Transactions do not replace unique indexes when the objective is enforcing key uniqueness across data.

## 8. MongoTemplate: findOne differs from strict uniqueness

`MongoTemplate` lets you write queries directly, for example:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("nickname").is("luna")
);

AppUser first = mongoTemplate.findOne(query, AppUser.class);
```

`findOne` focuses on retrieving **one document** matching the query and does not verify that **only one document exists**. Do not use it as a uniqueness check when the application needs to detect duplicate records. Without a sort clause, the chosen document may also not reflect a deterministic business order.

### 8.1. Checking for at most one result with find and limit(2)

When you cannot yet apply a unique index or need to detect invalid data during a migration, you can check:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Optional<AppUser> findUniqueNickname(
        MongoTemplate mongoTemplate, String nickname) {

    Query query = Query.query(
        Criteria.where("nickname").is(nickname)
    );
    query.limit(2);

    List<AppUser> matches =
        mongoTemplate.find(query, AppUser.class);

    if (matches.size() > 1) {
        throw new IncorrectResultSizeDataAccessException(1, matches.size());
    }

    return matches.stream().findFirst();
}
```

Limiting to two results is enough to detect "more than one" without loading the whole collection. However, this check is a **point-in-time snapshot**; under concurrent writes, it does not guarantee ongoing uniqueness. A unique index remains the proper data-layer enforcement for unique business keys.

### 8.2. Reading one document does not mean updating one document

`findOne`, `findFirst`, and `limit(1)` are **read-path** decisions. To update exactly one document, identify an unambiguous key or condition and use an operation like `updateFirst` or repository `save` with a known ID. Under concurrent updates, consider optimistic locking via `@Version` or conditional updates; concurrency control is distinct from query cardinality.

## 9. Reactive repositories: Mono.empty() and empty Flux

In reactive Spring Data MongoDB, **0 vs. many documents** are represented by publishers:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveAppUserRepository
        extends ReactiveMongoRepository<AppUser, String> {

    Mono<AppUser> findByEmailKey(String emailKey);

    Flux<AppUser> findAllByStatus(UserStatus status);

    Flux<AppUser> findAllByNickname(String nickname);

    Mono<AppUser> findFirstByNicknameOrderByCreatedAtDescIdDesc(
        String nickname
    );
}
```

- `Mono<AppUser>` either emits one user and completes, or completes without emitting a value when not found.
- `Flux<AppUser>` emits 0, 1, or many users; when nothing matches, it simply emits a completion signal.
- MongoDB errors, mapping errors, or cardinality errors per method contract propagate as error signals, never as an `Optional.empty()` object.

**Note on uniqueness:** Do not treat `Mono` as a database constraint. For queries that may match multiple records, return `Flux`; when strictly one result is expected, use queries/methods designed and tested to detect excess results, alongside a unique index where business rules require uniqueness.

### 9.1. Mono.empty() → HTTP 404 or domain error

```java
import reactor.core.publisher.Mono;

Mono<AppUser> requiredUser = reactiveRepository.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));
```

`switchIfEmpty` runs only when the publisher completes **with zero items**. It does not catch errors and convert them into not-found; connection or data errors continue down the original error signal.

In a WebFlux controller:

```java
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Mono;

Mono<ResponseEntity<AppUser>> response =
    reactiveRepository.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
```

### 9.2. Empty Flux and collectList()

```java
import java.util.List;
import reactor.core.publisher.Mono;

Mono<List<AppUser>> users = reactiveRepository
    .findAllByStatus(UserStatus.INACTIVE)
    .collectList();
```

If the source `Flux` emits no records, `collectList()` emits **an empty `List`**, not `Mono.empty()`. This suits small or bounded result sets; for large sets, use pagination/streaming to avoid buffering too much data in memory.

**Never call `block()` or `subscribe()` arbitrarily inside WebFlux services** to convert a pipeline into synchronous execution or detach it from the request lifecycle. Return `Mono`/`Flux` to callers and structure error handling within the pipeline.

### 9.3. When you must assert exactly one element in a Flux

Reactor provides `single()` when a stream must emit **exactly one element**: it errors if the source is empty or emits more than one item. `singleOrEmpty()` permits 0 or 1 item and errors on more than one.

```java
Mono<AppUser> zeroOrOne =
    reactiveRepository.findAllByNickname("luna")
        .singleOrEmpty();
```

This checks stream cardinality, yet still **does not replace a unique index**. On a MongoDB query that might match many documents, consider limiting fetched documents when detecting a second record suffices to save resources.

## 10. Distinguishing exception types and HTTP responses

| Scenario | Signal | Typical application handling |
| --- | --- | --- |
| No user for ID | `Optional.empty()` or `Mono.empty()` | 404 if endpoint fetches a single resource |
| No records match list query | `List.isEmpty()` or empty `Flux` completion | 200 with `[]` for list APIs |
| Multiple records in single-result query | `IncorrectResultSizeDataAccessException` or API cardinality error | Fix method contract, duplicate data, or index; never treat as "not found" |
| Insert violates unique index | `DuplicateKeyException` / Spring-translated duplicate write error | 409 Conflict if matching HTTP contract; explain conflicting key |
| Calling `Optional.get()` when empty | `NoSuchElementException` | Fix Optional handling; this is not a MongoDB error |
| Database unreachable | Data access / driver exception | Observe, retry safely if appropriate, return suitable service error |
| BSON mapping mismatches entity | Conversion / mapping exception | Inspect legacy schema, converters, BSON types; fix data or mapping |

HTTP status codes are an API decision, not dictated by Spring Data for every repository method. For example, a controller may map `Optional.empty()` to 404, or return a representation of a not-yet-created state in a specific workflow.

### 10.1. A 500 error alone does not mean MongoDB is broken

If a controller calls `repository.findByNickname("luna")` and throws `IncorrectResultSizeDataAccessException` because two users share that nickname, MongoDB **is still working**. The issue is that the data violates the query's contract.

A sensible investigation sequence:

1. Check whether the method returns `Optional<T>`, `T`, or `List<T>`.
2. Run the equivalent query directly in MongoDB to inspect the actual match count.
3. Verify whether the field is supposed to be unique.
4. If required unique, inspect actual unique indexes and write history.
5. If not required unique, change the method contract to a collection or use `First/Top` with an explicit sort.

## 11. Testing repositories: test all three cardinalities

A test suite covering only "exactly one document" easily misses design flaws. Prepare **0, 1, and 2 records** for the same filter condition.

### 11.1. Simple test for Optional and empty collections

Assuming `AppUserRepository` is registered in the Spring Data context and a test MongoDB is available:

```java
package example.users;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class AppUserRepositoryCardinalityTest {

    @Autowired
    AppUserRepository repository;

    @Test
    void missingByIdReturnsEmptyOptional() {
        String missingId = "missing-" + UUID.randomUUID();

        assertTrue(repository.findById(missingId).isEmpty());
    }

    @Test
    void singleEmailMatchIsPresent() {
        String suffix = UUID.randomUUID().toString();
        String email = "user-" + suffix + "@example.com";
        AppUser user = new AppUser(
            "id-" + suffix,
            email,
            "nickname-" + suffix,
            UserStatus.ACTIVE,
            Instant.parse("2026-11-20T09:00:00Z")
        );

        repository.save(user);

        var result = repository.findByEmailKey(email);
        assertTrue(result.isPresent());
        assertEquals(user.getId(), result.orElseThrow().getId());
    }

    @Test
    void absentNicknameReturnsEmptyCollection() {
        String nickname = "none-" + UUID.randomUUID();

        assertTrue(
            repository.findAllByNicknameOrderByCreatedAtDescIdDesc(
                nickname
            ).isEmpty()
        );
    }
}
```

The example places classes in the same package so Spring Data discovers the repository and entity. `@DataMongoTest` configures the MongoDB test slice, yet **does not automatically launch a MongoDB server**: your project may use Testcontainers or a configured test instance. Annotation names and imports can differ across Spring Boot major versions.

### 11.2. Testing multiple documents with the same nickname

Add a test method to the class above:

```java
import org.springframework.dao.IncorrectResultSizeDataAccessException;

@Test
void nonUniqueNicknameViolatesSingleResultContract() {
    String suffix = UUID.randomUUID().toString();
    String nickname = "shared-" + suffix;

    repository.save(new AppUser(
        "u1-" + suffix,
        "a-" + suffix + "@example.com",
        nickname,
        UserStatus.ACTIVE,
        Instant.parse("2026-11-20T09:00:00Z")
    ));
    repository.save(new AppUser(
        "u2-" + suffix,
        "b-" + suffix + "@example.com",
        nickname,
        UserStatus.ACTIVE,
        Instant.parse("2026-11-20T09:05:00Z")
    ));

    assertEquals(
        2,
        repository.findAllByNicknameOrderByCreatedAtDescIdDesc(
            nickname
        ).size()
    );

    assertThrows(
        IncorrectResultSizeDataAccessException.class,
        () -> repository.findByNickname(nickname)
    );

    assertEquals(
        "u2-" + suffix,
        repository
            .findFirstByNicknameOrderByCreatedAtDescIdDesc(nickname)
            .orElseThrow()
            .getId()
    );
}
```

In real Java files, `import` goes at the top of the file and this method sits inside the test class. Unique IDs/emails are generated per test run to minimize data collision. This test verifies the difference between a **multi-result query**, a **single-result query**, and a **single-record capped query**.

### 11.3. Testing the unique index at the MongoDB layer

If `emailKey` must be unique, also test that **MongoDB rejects a second document** with the same key. Before testing, confirm the unique index exists (via migration, index management, or enabled index creation).

```javascript
db.app_users.getIndexes();
```

Then attempt to write two documents with identical `emailKey` and different `_id` values. Expect the second write to fail due to a duplicate key. Run tests only in an environment where modifying test data is safe; never target a production collection.

Without the unique index, calling `repository.save` twice can succeed, only for `findByEmailKey` to fail later on non-unique results. This illustrates why **detecting the error on the read path is usually far too late compared to preventing it on the write path**.

### 11.4. Reactive testing

With Reactor Test:

```java
import reactor.test.StepVerifier;

StepVerifier.create(
    reactiveRepository.findById("missing-id")
).verifyComplete(); // Mono.empty

StepVerifier.create(
    reactiveRepository.findAllByStatus(UserStatus.INACTIVE)
        .filter(user -> user.getNickname().startsWith("no-match-"))
).verifyComplete(); // Flux emitting no matching items
```

Note that the second test assumes test documents have no nicknames starting with `no-match-`; in real suites, use an isolated test database/fixture to guarantee that precondition. For single-result queries on non-unique fields, verify the exact behavior of your repository/driver/version and never rely on `Mono` to substitute for a uniqueness constraint.

## 12. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `findByNickname` returns `Optional` when nicknames can duplicate | Exceptions or invalid cardinality contract | Use `List`/`Flux`, or `First/Top` with sort if only one is desired |
| Every empty query returns 404 | Search APIs cannot return a valid `[]` | Separate single-resource endpoints from collection results |
| Calling `Optional.get()` directly | `NoSuchElementException` when data is absent | `orElseThrow`, `map`, `ifPresent`, or explicit branch |
| Using `findFirst` to hide data violating uniqueness | Masks duplicate accounts; business bug persists | Clean duplicates and create a unique index |
| Using `existsBy` before `save` as the sole uniqueness guard | Concurrent requests create identical keys | Unique index + duplicate key handling |
| Only adding `@Indexed(unique=true)` and assuming it is enforced | Auto-index creation may be disabled | Check `getIndexes()`, create indexes via controlled migrations |
| Calling `findAll` then `get(0)` | Wastes I/O and crashes when list is empty | Choose a proper single-item query or handle lists safely |
| Loading huge lists just to check duplicates | Excessive memory and query latency | Unique index or `limit(2)` to detect multiple matches |
| Mapping all `DataAccessException` to "not found" | Hides timeouts, mapping bugs, and DB failures | Classify errors, log/monitor, and return accurate responses |
| Never testing 0 and 2 results | Method looks fine on demo data, fails in production | Test 0/1/2+ matches and concurrent writes |

## 13. Practice exercises

### Exercise 1 — Designing return types

For a `books` collection, choose the right Spring Data repository return type:

1. Find a book by `_id`.
2. List books by author, where there may be none.
3. Find a single ISBN backed by a unique index.
4. Fetch an author's newest book ordered by `publishedAt` and `_id`.
5. Check whether an author has at least one book.

Explain why each method should use `Optional<T>`, `List<T>`, `Page<T>`, `boolean`, or `First/Top`.

### Exercise 2 — Reproducing non-unique results

Insert two user documents with the same nickname and different emails. Call `findByNickname`, `findAllByNickname...`, and `findFirstByNickname...`. Record each result or exception, then explain why the three methods do not share the same contract.

### Exercise 3 — Enforcing uniqueness properly in the database

Normalize `emailKey`, audit existing duplicates, create a unique index, and test two concurrent requests creating accounts with the same email. Explain why `existsByEmailKey` before `save` cannot eliminate the race condition. Design the HTTP response for an already-taken email.

### Exercise 4 — Template vs. repository

Write `MongoTemplate.findOne` by nickname, then write a variant using `limit(2)` and checking result size. Compare with the repository method `findByNickname` and explain the difference between "fetching one representative" and "guaranteeing at most one result".

### Exercise 5 — Reactive Mono/Flux

Write a `ReactiveMongoRepository` returning `Mono` for ID lookups and `Flux` for multi-result queries. Use `StepVerifier` to verify empty `Mono`/`Flux`, then practice `switchIfEmpty` and `collectList`. Explain why `collectList()` on an empty `Flux` does not return `Mono.empty()`.

### Self-check questions

- Why do `Optional.empty()` and `IncorrectResultSizeDataAccessException` carry different meanings?
- If `findById` returns empty, should that be treated as a MongoDB error?
- When is `findFirstBy...` the right choice, and when does it mask bad data?
- Why must a unique index be created and verified on the actual collection?
- Why can checking `existsByEmailKey` then calling `save` still insert duplicates under concurrency?
- Does `MongoTemplate.findOne` automatically prove the result is unique?
- How do `Mono.empty()` and `Flux.empty()` differ in consumption contract?

## Key takeaways

**`Optional<T>`** suits queries expecting **0 or 1 document**; **`List<T>`/`Flux<T>`** suit queries returning **0 to many documents** and return an empty result when unmatched; and unlimited single-result queries can raise **`IncorrectResultSizeDataAccessException`** when more than one document matches. `First`/`Top` is an intentional result cap, not a uniqueness guarantee. For business keys such as email, enforce a **real unique index in MongoDB**, handle duplicate write errors, and test 0, 1, and 2+ document cases. Picking the right return type and separating "not found", "not unique", and "database access error" is fundamental to building reliable CRUD in Spring Data MongoDB.

## References

- [Spring Data MongoDB Reference — MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- [Spring Data Commons — Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
