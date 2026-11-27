# Testing ETag When Two Clients Update Concurrently

## Goal

This hands-on lab verifies that two clients can read a Spring Data REST resource concurrently, while the client holding stale data cannot overwrite newer changes made by the other client. The mechanism uses ETag in responses and the If-Match precondition in write requests.

After this lesson, learners will be able to:

- Explain ETag and optimistic locking at the HTTP level.
- Configure a version field for entities published by Spring Data REST.
- Simulate two clients reading the same version and then updating sequentially.
- Confirm that a request with a stale ETag is rejected with HTTP 412 Precondition Failed.
- Resolve conflicts by reloading fresh state, reconciling differences, and resubmitting merged changes.

## 1. ETag Mechanism and Conditional Updates

ETag (Entity Tag) is an identifier representing a specific version of an HTTP resource. The server returns ETag in responses, usually as a quoted string, for example:

~~~http
HTTP/1.1 200 OK
ETag: "0"
Content-Type: application/hal+json
~~~

The client stores this exact header value alongside the resource URI. When modifying the resource, the client sends that value back in the If-Match header:

~~~http
If-Match: "0"
~~~

The server only executes PUT, PATCH, or DELETE if the resource's current ETag matches If-Match. If the resource was already updated and its ETag changed, the precondition no longer holds; Spring Data REST returns HTTP 412 Precondition Failed. The request is rejected to avoid overwriting changes the client has not read.

ETag is not a pessimistic lock and does not hold the resource locked while a client is editing. It is a write-time version check, commonly known as optimistic concurrency control.

### Role of @Version

Spring Data REST retrieves version information from datastore metadata. For JPA entities, annotate the version property with `jakarta.persistence.Version`. For other Spring Data modules, use `org.springframework.data.annotation.Version` when the corresponding datastore supports this mechanism.

Minimal JPA entity example:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Item {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private String name;

    protected Item() {
    }

    public Item(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

The repository can be published directly by Spring Data REST:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ItemRepository extends JpaRepository<Item, Long> {
}
~~~

Under default configuration, item resources have URIs like `/items/{id}`. Collection names and URIs can change if the repository is configured with `@RepositoryRestResource` or the application sets a custom base path.

When creating or updating entities, the persistence provider manages the version property. Do not let clients increment version manually and do not use the JSON version value as a write precondition instead of ETag. Clients must store the exact ETag header value returned by the server.

## 2. Sequence When Two Clients Edit Concurrently

Suppose `/items/1` currently has ETag `"0"`. Client A and Client B both read the resource before any write occurs.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant S as Spring Data REST

    A->>S: GET /items/1
    S-->>A: 200 OK, ETag "0"
    B->>S: GET /items/1
    S-->>B: 200 OK, ETag "0"
    Note over A,B: Both are editing the same version
    A->>S: PATCH + If-Match "0"
    S-->>A: 2xx, resource updated
    Note over S: ETag advances to new version
    B->>S: PATCH + If-Match "0"
    S-->>B: 412 Precondition Failed
    B->>S: GET /items/1
    S-->>B: 200 OK, new data and ETag
    Note over B: Reconcile changes before resubmitting
~~~

| Step | Client | Condition and result |
|---|---|---|
| 1 | A reads resource | Receives current ETag, e.g. `"0"` |
| 2 | B reads same resource | Also receives ETag `"0"` |
| 3 | A updates | Sends If-Match: `"0"`; server accepts and creates new version |
| 4 | B updates | Still sends If-Match: `"0"`; server rejects with 412 |
| 5 | B resynchronizes | GETs resource, compares new data and ETag, then decides how to merge |

This is a test reproducing a concurrency conflict from the user's perspective: two clients hold the same snapshot, but one client writes before the other. Two write requests do not need to hit within the exact same millisecond to test stale update prevention.

## 3. Practicing with HTTP and curl

Suppose the application is running at `http://localhost:8080` and the target resource is `http://localhost:8080/items/1`. Replace this URI with the actual item link discovered from HAL or the application's repository configuration.

### 3.1. Two clients read concurrently

Open two independent terminals representing client A and client B. Run GET in both terminals:

~~~bash
curl -i http://localhost:8080/items/1
~~~

Inspect both responses:

- Status is 200 OK.
- Response includes an ETag header.
- Both clients receive the same ETag value if no intervening update occurred.
- Keep the exact header value, including double quotes. Do not strip quotes, do not compute ETag from JSON yourself, and do not assume the value is always `"0"`.

Illustrative example: both A and B receive `ETag: "0"`. Actual values depend on data state and datastore.

### 3.2. Client A updates using the read ETag

Client A sends PATCH with the ETag just received. The example below assumes ETag is `"0"` and the entity has a `name` property:

~~~bash
curl -i -X PATCH http://localhost:8080/items/1 -H 'Accept: application/json' -H 'Content-Type: application/json' -H 'If-Match: "0"' -d '{"name":"Updated by A"}'
~~~

Replace `"0"` with the exact ETag received in the GET response. With default Spring Data REST settings, a successful update returns 200 OK or 204 No Content depending on response-body configuration and the Accept header. The update response may provide a new ETag; you can GET the resource again to verify the new version.

### 3.3. Client B submits a stale update

Client B still holds the old ETag from the first GET. Send a different change while keeping the same If-Match:

~~~bash
curl -i -X PATCH http://localhost:8080/items/1 -H 'Accept: application/json' -H 'Content-Type: application/json' -H 'If-Match: "0"' -d '{"name":"Updated by B"}'
~~~

B's request must receive HTTP 412 Precondition Failed because the current ETag is no longer `"0"`. The server does not apply this stale update. In this example, A's data remains preserved.

### 3.4. Client B resolves the conflict

After receiving 412, B does not simply resend the same request with the old ETag. B must:

1. GET the exact resource URI again.
2. Read the latest data and new ETag.
3. Compare the fields B intended to modify against the data A wrote.
4. Decide whether to keep A's change, keep B's change, or merge both according to business rules.
5. Send a new request with If-Match carrying the new ETag.

Do not automatically retry a stale payload without merging data. Doing so can turn conflict handling into a blind overwrite.

## 4. Integration Testing with MockMvc

You can verify Spring Data REST's HTTP contract with MockMvc in a Spring Boot test. The test below assumes:

- The application includes `spring-boot-starter-data-rest`, Spring Data JPA, and test datasource configuration.
- `ItemRepository` is exported by Spring Data REST.
- Default item endpoint is `/items/{id}`.
- `Item` has a `name` field and a `version` field annotated with `@Version`.
- Test data is persisted before sending HTTP requests.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ItemEtagConcurrencyTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ItemRepository itemRepository;

    @Test
    void rejectsUpdateFromClientUsingStaleEtag() throws Exception {
        Item item = itemRepository.save(new Item("Initial"));
        String uri = "/items/" + item.getId();

        // Client A reads the current version.
        MvcResult responseA = mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andReturn();

        String etagA = responseA.getResponse().getHeader(HttpHeaders.ETAG);
        assertThat(etagA).isNotBlank();

        // Client B also reads before any client updates.
        MvcResult responseB = mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andReturn();

        String etagB = responseB.getResponse().getHeader(HttpHeaders.ETAG);
        assertThat(etagB).isEqualTo(etagA);

        // A writes using the valid ETag.
        mockMvc.perform(patch(uri)
                .header(HttpHeaders.IF_MATCH, etagA)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Updated by A"}
                    """))
            .andExpect(status().isOk());

        // ETag must change after a successful write.
        MvcResult responseAfterA = mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andReturn();

        String currentEtag = responseAfterA.getResponse()
            .getHeader(HttpHeaders.ETAG);

        assertThat(currentEtag).isNotBlank().isNotEqualTo(etagA);

        // B uses stale snapshot so the request is rejected.
        mockMvc.perform(patch(uri)
                .header(HttpHeaders.IF_MATCH, etagB)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Updated by B"}
                    """))
            .andExpect(status().isPreconditionFailed());

        // A's change remains persisted on the resource.
        mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Updated by A"));
    }
}
~~~

If application configuration returns 204 No Content for PATCH even when Accept is set, adjust the status assertion on A's request to match actual configuration (e.g. `isNoContent` or `is2xxSuccessful`). If the repository changes the collection path, update `/items/{id}`. The test must use the two ETag values extracted from responses; do not fabricate ETags inside the test.

### Cases that should be in the test suite

| Case | Outcome to observe |
|---|---|
| GET item with `@Version` | 200 and includes ETag |
| Two clients GET before write | Both ETags match |
| Client A writes with current ETag | Request succeeds |
| After A writes | New ETag differs from old ETag |
| Client B writes with stale ETag | 412 Precondition Failed |
| GET after rejected request | A's data remains |
| Client B GETs again and writes with new ETag | Request can succeed if no intervening update occurs |

The test above intentionally creates two identical snapshots and sends two writes in a deterministic order. If you need to test database-level race conditions, add a test running two concurrent write requests behind a barrier, both carrying the read ETag. Then verify only one change is saved and the other does not overwrite data. If both requests pass the HTTP comparison step before transaction commit, the datastore may throw `OptimisticLockingFailureException`; check the application's exception mapping to confirm the HTTP status published by the API for storage-layer races. Sequential stale If-Match contracts are explicitly specified by Spring Data REST as 412.

## 5. Distinguishing 412 from 304

These two status codes serve different purposes:

- 412 Precondition Failed: a conditional write request, such as PATCH with If-Match, fails the version condition. The server does not perform the change.
- 304 Not Modified: GET with If-None-Match has an ETag matching the current version. The server tells the client it may use its cached copy and omits the representation body.

Do not use If-None-Match instead of If-Match when updating. If-None-Match primarily supports conditional queries and caching; If-Match protects write operations from stale data.

## 6. Common Errors and Troubleshooting

| Symptom | Common cause | How to inspect and resolve |
|---|---|---|
| GET has no ETag | Entity lacks a recognized version field, endpoint bypasses Spring Data REST, or proxy strips header | Check right `@Version` annotation type, entity metadata, item endpoint, and actual response |
| Very first request receives 412 | Client saved an old ETag, URI does not match read resource, or resource was updated prior to send | GET exact URI again, fetch new ETag, and compare data before writing |
| Client B writes successfully despite stale data | Request lacks If-Match, header stripped by client/proxy, using `If-Match: *`, or custom endpoint skips check | Inspect actual sent request, avoid wildcards when version matching is needed, verify request goes through Spring Data REST's ETag mechanism |
| Receives 400 or 415 on PATCH | Invalid JSON or Content-Type unsupported by endpoint | Check body and Content-Type. Spring Data REST supports application/json, application/hal+json, application/patch+json, and application/merge-patch+json for PATCH |
| Receives 405 Method Not Allowed | Repository does not export save method or operation is configured off | Check repository interface and method `exported` configuration |
| Receives OptimisticLockingFailureException under real race | Two transactions read same version and write concurrently; datastore detects stale version on one | Confirm `@Version` is datastore-managed, inspect transactions, and map exception to appropriate API error |
| Client retries repeatedly and keeps receiving 412 | Client keeps sending stale ETag after server updated resource | GET again, merge changes, then send new request with new ETag |

Debugging tips:

- Compare the ETag header in the GET response against the If-Match header of the write request. Values must be preserved verbatim, including quotes and any prefix.
- ETag is an opaque token to clients. Do not assume it is always a sequential integer or always starts at 0.
- If-Match uses strong comparison per HTTP. Do not convert an ETag into a weak validator like `W/` before sending it back.
- `If-Match: *` only checks that the resource currently exists; it does not confirm the client holds the exact version it read.
- Always pair an ETag with the exact resource URI the client GETted. Never reuse an ETag from another item.
- If there is a custom controller or custom repository method, verify separately whether that code path enforces If-Match and version checking.

## 7. Lab Completion Checklist

- [ ] Entity has a version property and datastore supports optimistic locking.
- [ ] GET on item resource returns an ETag header.
- [ ] Two clients read the same URI before writing and receive matching ETags.
- [ ] Client A sends PATCH or PUT with a valid If-Match and updates successfully.
- [ ] ETag after A's write differs from the initial ETag.
- [ ] Client B sends a request with the stale ETag and receives 412 Precondition Failed.
- [ ] Subsequent GET confirms A's data was not overwritten by B's stale request.
- [ ] Client B can read the new version, merge data, and submit a request with the new ETag.

## Official References

1. [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): how Spring Data REST derives ETags from `@Version`, uses If-Match for PUT/PATCH/DELETE, and returns 412 when ETags no longer match.
2. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): item resource URIs, supported HTTP methods, and PATCH media types.
3. [Spring Data Commons — @Version API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Version.html): semantics of the version property in optimistic locking.
4. [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): conditional requests, ETag, and distinguishing 304 from 412 in Spring MVC.
5. [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1) and [412 Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.13): standard HTTP semantics for write preconditions and responses when preconditions fail.
