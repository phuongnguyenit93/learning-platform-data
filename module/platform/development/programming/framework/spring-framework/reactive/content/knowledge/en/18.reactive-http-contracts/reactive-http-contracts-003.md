# Distinguishing empty publishers from HTTP 404 or 204 responses in Spring WebFlux

## 1. Three concepts belonging to three different layers

In Spring WebFlux, three concepts need to be separated:

1. **Having no elements in Reactor** is a state of a publisher: `Mono.empty()` or `Flux.empty()` completes without emitting `onNext`.
2. **HTTP 404 Not Found** is an API decision that no current representation was found for the requested resource, or that the server does not want to disclose that the resource exists.
3. **HTTP 204 No Content** is a success response: the server fulfilled the request and intentionally sends no response content.

These three concepts do not automatically convert into one another. `Mono.empty()` **does not automatically mean 404**, nor does it **automatically mean 204**. A publisher only emits reactive signals; the controller or handler decides the HTTP status according to the endpoint contract.

The same empty reactive state can be used for different business meanings:

- Looking up a user by ID when no user exists: usually returns **404**.
- Looking up a list of users when there are currently no elements: usually returns **200 OK** with an empty JSON array `[]`.
- Deleting a resource successfully without needing to return a representation: usually returns **204**.
- A save operation completing with `Mono<Void>`: the publisher emits no value, yet the operation may have succeeded.

**Principle:** Reactor describes *whether data is emitted*; the HTTP status describes *the outcome of the request for the client*. Map these two layers intentionally.

## 2. Mono.empty(), Flux.empty(), and Mono<Void>

### Mono.empty()

`Mono.empty()` emits `onComplete` without emitting `onNext`:

~~~text
onSubscribe
    |
    v
onComplete
~~~

It represents a single result that may be absent. For example:

~~~java
Mono<User> findUser(String id) {
    return repository.findById(id);
}
~~~

If the ID does not exist, the repository can return `Mono.empty()`. This is the natural way to represent "no User" in the reactive layer. At the HTTP layer, the endpoint decides whether this case is a 404, a fallback, or another result.

### Flux.empty()

`Flux.empty()` also completes with no elements, but its contract allows 0 to many elements:

~~~java
Flux<User> findUsersByRole(String role) {
    return repository.findAllByRole(role);
}
~~~

If there is no matching user, `Flux` can complete empty. For a collection-listing endpoint, having no items is usually **a valid list result**, not a non-existent collection resource. The client usually receives 200 and the list `[]` if the API returns a JSON array.

### Mono<Void>

`Mono<Void>` represents **the completion or error of an operation that returns no data**. When the operation succeeds, it completes without emitting `onNext`:

~~~java
Mono<Void> saveAudit(AuditEvent event) {
    return auditRepository.save(event).then();
}
~~~

A successful `Mono<Void>` also has no data elements. You cannot infer that the operation failed or that data was not found merely from the absence of `onNext`.

| Publisher | Can it emit onNext? | What does empty completion mean? |
| --- | --- | --- |
| `Mono<User>` | At most one User | No User result, for example not found |
| `Flux<User>` | 0 to many Users | The collection/stream currently has no elements |
| `Mono<Void>` | No data value | The completion-only operation completed successfully |
| `Mono<Boolean>` | One Boolean | Can explicitly express true/false |
| `Mono<Long>` | One number | Can express the number of affected rows |

**Having no elements is not an exception.** `switchIfEmpty` handles completing without a value; `onErrorResume` handles the publisher emitting `onError`. Do not use the two operators interchangeably.

## 3. HTTP 404 Not Found

According to HTTP Semantics (RFC 9110), 404 indicates that the server did not find a current representation for the target resource, or is not willing to disclose that one exists. This status does not assert that the resource has been permanently deleted; if the server knows the condition is permanent, 410 Gone may be more appropriate.

Endpoint example:

~~~http
GET /api/users/42
~~~

If user ID 42 does not exist, the client is requesting a single resource that has no current representation. The API usually returns:

~~~http
HTTP/1.1 404 Not Found
~~~

The error body may contain Problem Details information if the API is designed that way. A 404 may also have no body; what matters is that the status conveys that the resource was not found.

404 fits these cases:

- `GET /users/{id}`: the ID has no user.
- `GET /orders/{id}`: the order does not exist or may not be disclosed.
- `GET /documents/{id}/content`: the document does not have the requested representation.
- A singular-resource lookup endpoint does not find the object.

**Do not automatically return 404 just because an arbitrary publisher completes empty.** You must know whether the endpoint is requesting a single resource, a collection, an optional result, or simply waiting for an operation to complete.

## 4. HTTP 204 No Content

204 belongs to the 2xx group: the server **has successfully fulfilled the request**, and there is no additional content to send in the response. According to RFC 9110, a 204 response must not contain content or trailers.

Common situations:

- The client sends `DELETE /users/42`, the server deletes it successfully, and no body needs to be returned.
- The client sends `PUT /preferences`, the server updates successfully, and the client does not need the new representation in the response.
- An endpoint executes a command such as invalidating a cache or acknowledging, with a clear contract that no body is returned.

Example:

~~~http
DELETE /api/users/42
HTTP/1.1 204 No Content
~~~

A 204 response has no JSON `null`, no `{}`, and no empty array. The status code already states that the operation succeeded and there is no response content.

### 204 differs from 200 with an empty collection

`200 OK` says the request succeeded. If the API returns an empty JSON collection, the response is usually:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

`204 No Content` says the request succeeded and **there is no response representation**. The client can handle the two situations differently:

- `200 []`: the collection exists and currently has no elements.
- `204`: the operation succeeded, and the API sends no response content.

Do not return 204 just because the repository found no elements. 204 is the successful outcome of an action according to the API contract, not another way of writing "no data".

## 5. Decision table: which status should empty map to?

| Business situation | Reactive result | Usually appropriate HTTP response | Reason |
| --- | --- | --- | --- |
| GET a user by ID, does not exist | `Mono<User>` empty | **404 Not Found** | A single resource has no representation |
| GET a user list, the list has no items | `Flux<User>` empty | **200 OK**, JSON `[]` | The collection query succeeded, empty result |
| GET search, no results | `Flux<Result>` empty | **200 OK**, JSON `[]` | The search succeeded but there were no matches |
| DELETE succeeded, no body returned | `Mono<Void>` complete | **204 No Content** | The action succeeded, no representation |
| PUT update succeeded, no body returned | `Mono<Void>` complete | **204 No Content** | The update has completed |
| POST creates a resource and returns a representation | `Mono<Resource>` with a value | **201 Created** or 200 per contract | Newly created; may include Location |
| POST accepts background work not yet finished | Publisher reports work accepted | **202 Accepted** | Accepted for processing, completion not yet confirmed |
| Repository/database emits an error | `onError` | **5xx** or appropriate domain error | This is a failure, not empty |
| Client is not permitted to access | Authorization error | **403** or 404 per policy | Must not be equated with absence |

These are common API conventions, not mechanical rules for every endpoint. A contract may choose 404 or 204 for DELETE depending on the idempotency policy, but it must be consistent and documented.

## 6. Mapping Mono.empty() to 404 in an annotated controller

With `@RestController`, if a lookup service returns `Mono<User>`, use `map` to build the response when there is a value and `defaultIfEmpty` or `switchIfEmpty` to choose the response when there is none.

~~~java
@GetMapping("/users/{id}")
public Mono<ResponseEntity<UserDto>> getUser(@PathVariable String id) {
    return userService.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(
            ResponseEntity.<UserDto>notFound().build()
        );
}
~~~

Result:

- User exists: `Mono` emits `ResponseEntity<UserDto>` with status 200 and a body.
- No user: `Mono.empty()` triggers `defaultIfEmpty`, emitting a 404 `ResponseEntity`.
- Service reports a database error: the error still propagates downstream; it is not turned into 404.

You can use `switchIfEmpty` if you want to substitute a publisher:

~~~java
@GetMapping("/users/{id}/detail")
public Mono<ResponseEntity<UserDto>> getUserDetail(@PathVariable String id) {
    return userService.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .switchIfEmpty(Mono.just(
            ResponseEntity.<UserDto>notFound().build()
        ));
}
~~~

Both approaches are appropriate. `defaultIfEmpty(value)` replaces empty with a value; `switchIfEmpty(publisher)` switches to another publisher when the source completes empty.

### Do not map every empty to 404

The following example is only right if `findById` genuinely means "find a single resource":

~~~java
return userService.findById(id)
    .switchIfEmpty(Mono.error(new ResponseStatusException(
        HttpStatus.NOT_FOUND, "User not found"
    )));
~~~

If `userService.search(...)` returns an empty collection, using the same approach above will break the search contract. A search with no results is usually 200 with an empty list.

## 7. Mapping to 204 when an operation completes successfully

If an operation returns `Mono<Void>`, you can use `thenReturn` to produce a response value after the publisher completes:

~~~java
@DeleteMapping("/users/{id}/cache")
public Mono<ResponseEntity<Void>> clearCache(@PathVariable String id) {
    return cacheService.clear(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

`cacheService.clear(id)` is a `Mono<Void>`. When it completes successfully, `thenReturn` emits a 204 `ResponseEntity`. If it emits an error, `thenReturn` does not run and the error is propagated downstream.

You can use `@ResponseStatus` for an endpoint that always returns 204 on completion:

~~~java
@DeleteMapping("/sessions/current")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> closeCurrentSession() {
    return sessionService.closeCurrent();
}
~~~

In this case, the annotation specifies the HTTP status; `Mono<Void>` represents when the operation finishes. If the service errors, WebFlux still processes the error signal via the exception-handling mechanism instead of returning a 204 success.

### Functional endpoint

WebFlux.fn also lets you build a 204 response after a publisher completes:

~~~java
public Mono<ServerResponse> deleteUser(ServerRequest request) {
    String id = request.pathVariable("id");

    return repository.deleteById(id)
        .then(ServerResponse.noContent().build());
}
~~~

This code is appropriate when the contract of `deleteById` only represents completion/error and the API accepts 204 for that operation. If you need to return 404 when there is no row to delete, the repository must provide that information through `Mono<Boolean>`, `Mono<Long>`, or another domain result.

## 8. Crucial trap: switchIfEmpty on Mono<Void>

A successful operation of type `Mono<Void>` **emits no value**. Therefore, the following snippet is wrong if the goal is "if deleting fails, return 404":

~~~java
// Wrong if deleteById returns Mono<Void> and completes empty on success.
return repository.deleteById(id)
    .then()
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)
    ));
~~~

Because `Mono<Void>` has no `onNext` even when it succeeds, `switchIfEmpty` sees empty after completion and runs the fallback. It cannot distinguish:

- The deletion succeeded, but the API emits no data.
- There was no record to delete.
- Another completion-only operation completed.

If you want to decide between 204 and 404, change the repository/service contract to emit a value:

~~~java
Mono<Boolean> deleteById(String id) {
    return Mono.fromSupplier(() ->
        repository.deleteAndReturnCount(id) > 0
    );
}
~~~

This is an illustrative snippet; `deleteAndReturnCount` is a hypothetical persistence-layer method. The controller can map it:

~~~java
@DeleteMapping("/users/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
    return userService.deleteById(id)
        .map(deleted -> deleted
            ? ResponseEntity.<Void>noContent().build()
            : ResponseEntity.<Void>notFound().build()
        );
}
~~~

Here `Mono<Boolean>` emits `true` or `false`, so `map` can choose the status clearly. If the service can fail to emit a result for another reason, define the corresponding empty policy as well.

Another option is to return the number of affected rows:

~~~java
Mono<Long> deleteRows(String id);
~~~

- Row count greater than 0: deleted, return 204.
- Row count equal to 0: no matching resource, return 404 if the contract requires it.
- Publisher emits error: handle the database error, do not convert it to 404.

**Do not use `thenReturn(true)` to fake whether something was deleted.** It only confirms that the previous publisher completed successfully; it provides no information about the number of affected rows.

## 9. Empty Flux in a collection endpoint

For an endpoint returning a list, empty usually means "no matching items" rather than "the collection does not exist".

~~~java
@GetMapping(value = "/users", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<UserDto> listUsers() {
    return userService.findAll();
}
~~~

If there are no users, `findAll()` can return `Flux.empty()`. With Spring WebFlux's default Jackson codec and media type `application/json`, a multi-value publisher is collected into a collection before serializing; an empty collection is represented by the JSON array `[]`.

The response according to the contract is usually:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

This lets the client always process the same schema: the response is an array, regardless of whether there are 0, 1, or many items.

With a streaming media type such as `application/x-ndjson`, the encoder writes each element in line-delimited form. If the Flux is empty, there are no data lines; **the HTTP status is still decided by the handler**, and it does not automatically turn into 404.

### When is 404 appropriate for a collection endpoint?

Return 404 only if that collection resource/path itself does not exist or the API defines the route/resource that way. For example, a non-existent tenant may make `GET /tenants/{tenantId}/users` return 404; whereas a tenant that exists and has no users yet usually returns 200 with `[]`.

You should not use the element count as the sole criterion for deciding 404 for every collection.

## 10. ResponseEntity: setting the status synchronously vs with an async result

Spring WebFlux supports several `ResponseEntity` shapes with reactive types:

| Return type | Meaning |
| --- | --- |
| `ResponseEntity<T>` | Status, headers, and body are determined immediately |
| `Mono<ResponseEntity<T>>` | Status, headers, and body are determined after the publisher completes |
| `ResponseEntity<Mono<T>>` | Status/headers are known upfront, body is provided asynchronously |
| `ResponseEntity<Flux<T>>` | Status/headers are known upfront, body is a multi-element stream |
| `Mono<ResponseEntity<Mono<T>>>` | Status/headers are determined asynchronously first; body continues asynchronously afterward |

When the status depends on whether the resource was found, `Mono<ResponseEntity<T>>` is usually used:

~~~java
public Mono<ResponseEntity<UserDto>> get(String id) {
    return service.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(
            ResponseEntity.<UserDto>notFound().build()
        );
}
~~~

When the status is always 200 but the body may arrive asynchronously, `ResponseEntity<Mono<T>>` can be used. Do not pick a wrapper merely by preference; look at whether the status depends on the async result.

## 11. Functional endpoint: 404 and 204 by business logic

In WebFlux.fn, `ServerResponse` lets you specify the status explicitly:

~~~java
public Mono<ServerResponse> getUser(ServerRequest request) {
    String id = request.pathVariable("id");

    return repository.findById(id)
        .flatMap(user -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(user))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Here the repository returns `Mono<User>`; empty is interpreted as no user and mapped to 404.

For a completion-only operation:

~~~java
public Mono<ServerResponse> saveUser(ServerRequest request) {
    Mono<User> user = request.bodyToMono(User.class);

    return repository.save(user)
        .then(ServerResponse.noContent().build());
}
~~~

`repository.save(user)` is assumed to return `Mono<Void>`; the 204 response is built only after the save publisher completes successfully. If the save errors, the handler emits an error instead of 204.

Spring has a similar official example: when saving an object, the repository returns `Mono<Void>` and the handler uses `build(Publisher<Void>)` to send the response only after the save operation completes. For a singular-resource lookup, the example uses `switchIfEmpty(ServerResponse.notFound().build())`.

## 12. Empty, error, and cancellation are not the same thing

| Reactive signal | Meaning | Common HTTP mapping |
| --- | --- | --- |
| `onComplete` without `onNext` | Completed empty, no error | Depends on contract: 200, 204, or 404 |
| `onError(ex)` | Publisher failed | 4xx if request/domain error; 5xx if server/infrastructure error |
| `cancel()` | Downstream no longer needs data | Does not create a new status by itself; usually relates to client disconnect |

Examples:

- Repository did not find the user: `Mono.empty()`.
- Database lost connection: `Mono.error(DataAccessException)`.
- Client closed the connection while receiving the stream: upstream may be cancelled.

Do not write:

~~~java
return service.findById(id)
    .onErrorResume(error -> Mono.empty())
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)
    ));
~~~

The snippet above turns every error (including a database outage) into empty and then into 404, masking infrastructure failures. Only map empty from a **not-found lookup** to 404; other errors are routed to the appropriate error handler.

## 13. Complete Java 17+ example with Spring Boot WebFlux

The example below illustrates three contracts:

- `GET /api/users`: an empty list still returns 200 with `[]`.
- `GET /api/users/{id}`: a non-existent user returns 404.
- `DELETE /api/users/{id}`: successful deletion returns 204; no user to delete returns 404.

Create the structure:

~~~text
http-empty-status-demo/
├── pom.xml
└── src/main/java/com/example/httpstatus/
    ├── HttpStatusApplication.java
    ├── User.java
    ├── UserStore.java
    └── UserController.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>http-empty-status-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/httpstatus/HttpStatusApplication.java`:

~~~java
package com.example.httpstatus;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpStatusApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpStatusApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/httpstatus/User.java`:

~~~java
package com.example.httpstatus;

public record User(String id, String name) {
}
~~~

File `src/main/java/com/example/httpstatus/UserStore.java`:

~~~java
package com.example.httpstatus;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class UserStore {
    private final ConcurrentMap<String, User> users =
        new ConcurrentHashMap<>();

    public UserStore() {
        users.put("42", new User("42", "An"));
    }

    public Flux<User> findAll() {
        return Flux.defer(() -> Flux.fromIterable(users.values()));
    }

    public Mono<User> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(users.get(id)));
    }

    public Mono<User> deleteById(String id) {
        return Mono.fromSupplier(() -> users.remove(id));
    }
}
~~~

File `src/main/java/com/example/httpstatus/UserController.java`:

~~~java
package com.example.httpstatus;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserStore store;

    public UserController(UserStore store) {
        this.store = store;
    }

    // An empty collection is a valid result: return a JSON array.
    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<User> list() {
        return store.findAll();
    }

    // Single-resource lookup: empty is mapped to 404.
    @GetMapping("/{id}")
    public Mono<ResponseEntity<User>> get(@PathVariable String id) {
        return store.findById(id)
            .map(user -> ResponseEntity.ok(user))
            .defaultIfEmpty(
                ResponseEntity.<User>notFound().build()
            );
    }

    // deleteById emits User when deleted, empty when the ID does not exist.
    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
        return store.deleteById(id)
            .map(removed -> ResponseEntity.<Void>noContent().build())
            .defaultIfEmpty(
                ResponseEntity.<Void>notFound().build()
            );
    }
}
~~~

Run in the `http-empty-status-demo` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### GET an existing resource

~~~bash
curl -i http://localhost:8080/api/users/42
~~~

Main result:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"42","name":"An"}
~~~

### GET a non-existent resource

~~~bash
curl -i http://localhost:8080/api/users/99
~~~

Main result:

~~~http
HTTP/1.1 404 Not Found
~~~

The repository returns `Mono.empty()`; the controller turns empty into a 404 `ResponseEntity`.

### GET the collection before deletion

~~~bash
curl -i http://localhost:8080/api/users
~~~

Expected JSON body:

~~~json
[{"id":"42","name":"An"}]
~~~

### DELETE an existing resource

~~~bash
curl -i -X DELETE http://localhost:8080/api/users/42
~~~

Main result:

~~~http
HTTP/1.1 204 No Content
~~~

There is no response body.

### GET the collection after deletion

~~~bash
curl -i http://localhost:8080/api/users
~~~

Expected JSON body:

~~~json
[]
~~~

The list no longer has any users, yet the collection endpoint still returns 200 with an empty array.

### DELETE the already-deleted ID again

~~~bash
curl -i -X DELETE http://localhost:8080/api/users/42
~~~

Per this demo's contract, there is no user left to delete, so it returns:

~~~http
HTTP/1.1 404 Not Found
~~~

The demo uses an in-memory `ConcurrentHashMap`; data returns to its initial state when the application restarts. In production, the database repository needs to return an affected-row count or an appropriate domain result if the endpoint must distinguish successful deletion from a missing record.

## 14. DELETE 204 or 404 when the resource already does not exist?

This is an API contract decision, not something Reactor chooses automatically.

### Policy A: return 204 when the desired state is achieved

A DELETE can be designed to be idempotent: after the request, the resource no longer exists. If the resource already did not exist beforehand, the final state is still the same; the API can return 204 in both cases.

Under this policy, the service can return `Mono<Void>` and the controller returns 204 on completion. It does not need to disclose whether a row was actually deleted.

### Policy B: return 404 if there is no resource to delete

Another API can specify that the client only receives 204 when an existing resource was deleted. If the ID is not found, return 404. Then the service must emit a result such as a `Boolean`, a row count, or a `DeleteResult`; `Mono<Void>` does not carry enough information.

Determine:

- Is DELETE idempotent according to the expected client contract?
- Does the client need to know whether the resource existed before deletion?
- Does the API need to hide the existence of the resource for security reasons?
- Do you need to distinguish "deleted", "already did not exist", and "unauthorized"?

There is no single choice that fits every API. What matters is not using `Mono.empty()` ambiguously and leaving the HTTP layer to guess.

## 15. Testing status and body with WebTestClient

WebTestClient helps verify status, headers, and body without a browser. It can be used in tests with `@SpringBootTest`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void existingUserReturns200AndBody() {
        client.get()
            .uri("/api/users/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42");
    }

    @Test
    void missingUserReturns404() {
        client.get()
            .uri("/api/users/99")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody().isEmpty();
    }

    @Test
    void deletingExistingUserReturns204WithoutBody() {
        client.delete()
            .uri("/api/users/42")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }
}
~~~

This is an illustrative test snippet; add JUnit, Spring Boot test, `@Autowired`, `WebTestClient` imports, and the `spring-boot-starter-test` dependency. The tests modify data in the store; if run independently, reset data before each test or use a separate test store to avoid order dependence.

Also test:

- `GET /api/users` when empty: 200 and body `[]`.
- `DELETE` a non-existent ID per the chosen policy: 404 or 204.
- Repository error: the error is mapped properly, not turned into 404.
- `Mono<Void>` completion: the 204 response is sent only after the operation completes.
- POST/PUT returning 201, 200, or 204 per the contract.
- A 204 response has no body.
- The JSON body of a 200 collection always has the schema the client expects.

## 16. Common mistakes

1. **Assuming `Mono.empty()` automatically produces HTTP 404:** wrong; the controller/handler must map it explicitly.
2. **Assuming empty always means 204:** wrong; 204 indicates a successful action that sends no representation.
3. **Returning 404 for a list with no items:** usually breaks the collection contract; return 200 with `[]` if the collection exists.
4. **Using `switchIfEmpty` on `Mono<Void>` to detect no row:** wrong; a successful operation also emits no elements.
5. **Using `thenReturn(true)` to prove something was deleted:** wrong; it only says the preceding publisher completed, not how many rows were affected.
6. **Mapping every `onError` to 404:** hides database errors, timeouts, or server errors; map empty only for the appropriate lookup.
7. **Returning 204 with JSON `null` or `{}`:** violates 204 semantics; this status must not contain response content.
8. **Using `Mono.empty()` to represent a validation failure:** a validation failure should be a 4xx error or an explicit domain result.
9. **Using `Flux.empty()` to represent a query error:** a query error must emit an error signal; empty only means no elements.
10. **Assuming 404 means the resource was permanently deleted:** 404 does not say that; 410 may be appropriate when the condition is known to be permanent.
11. **Not deciding on a DELETE policy:** the client does not know whether deleting an absent ID is an idempotent success or a 404 error.
12. **Not distinguishing status from body:** 200 with an empty body, 200 `[]`, 204, and 404 have different meanings even though some cases have no JSON object.
13. **Using `ResponseEntity<Mono<T>>` when the status depends on the lookup result:** the status is decided too early; use `Mono<ResponseEntity<T>>`.
14. **Letting repository errors turn into empty:** can cause system errors to be reported as "not found"; preserve the error signal and handle it separately.
15. **Checking empty with `null` in a reactive chain:** Reactor does not allow emitting `null` via `onNext`; use `Mono.empty()`, `Optional`, or an explicit result type.

## 17. HTTP contract design checklist

Before choosing a status for an endpoint, answer:

- Is the endpoint accessing a **single resource**, a **collection**, or executing a **command**?
- Does the service's empty mean "resource does not exist", "no items", or "operation completed"?
- If returning 404, does the resource genuinely lack a current representation?
- If returning 204, has the action succeeded and is the response intentionally without content?
- If returning 200 for a collection, is an empty body consistently represented as `[]`?
- Does the service use `Mono<Void>`? If you need to know how many rows changed, return a result carrying data.
- Are `onError` and `onComplete` distinguished?
- Are DELETE idempotency and behavior when the ID does not exist defined?
- Does the status depend on an async result? If so, consider `Mono<ResponseEntity<T>>`.
- Have you tested status, body, headers, and repository errors?

## 18. Self-check questions

**1.** Is `Mono.empty()` an HTTP 404? No. It is just a publisher completing without emitting a value; the endpoint decides the status.

**2.** When is an empty `Mono<User>` lookup usually mapped to 404? When the API requests a single user/resource and there is no current representation.

**3.** What does `Flux.empty()` on a list endpoint usually return? 200 with an empty JSON array `[]` when using a JSON collection contract.

**4.** What does 204 indicate? The request was fulfilled successfully and there is no additional response content.

**5.** Can you send a JSON body in a 204? No. 204 must not contain response content.

**6.** Why can `switchIfEmpty` on `Mono<Void>` not determine whether an operation found a row? Because a successful Mono<Void> also emits no `onNext`; it always completes empty.

**7.** What should a service return to distinguish successful deletion from no row? For example `Mono<Boolean>`, a `Mono<Long>` affected-row count, or a domain result.

**8.** How does `onErrorResume` differ from `switchIfEmpty`? One operator handles an error signal, while the other handles completion without a value.

**9.** If a GET collection has no results, should it return 404? Usually no; if the collection exists, return 200 with an empty list.

**10.** If DELETE does not find the ID, must it return 404? No; it depends on the API contract. An idempotent DELETE may return 204 if the final state has been reached.

**11.** Why use `Mono<ResponseEntity<T>>` for a lookup? Because the status and body can be decided after knowing whether the lookup has a value.

**12.** If the repository has a connection error, should it be turned into 404? No. That is an infrastructure error and must be handled by the appropriate error mapping.

**Key takeaway:** `Mono.empty()`/`Flux.empty()` describe **having no elements**, and do not decide the HTTP status. 404 is for a resource with no current representation; 204 is for a successful request with no response content; an empty collection is usually 200 with `[]`. In particular, a successful `Mono<Void>` always emits no value, so do not use `switchIfEmpty` to detect missing records. Have the service return an explicit result if the HTTP contract needs to distinguish those cases.

**Official references:**
- [Spring Framework 6.2 — Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 — Return Values in WebFlux Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — ResponseEntity in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Framework 6.2 — Reactive Core and Jackson Encoder](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [RFC 9110 — HTTP Semantics, 204 and 404](https://www.rfc-editor.org/rfc/rfc9110.html).