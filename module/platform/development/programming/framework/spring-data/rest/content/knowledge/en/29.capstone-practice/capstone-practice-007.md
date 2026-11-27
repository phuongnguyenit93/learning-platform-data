# Simulating Two Users Updating Concurrently with ETag

## 1. The Problem: Preventing Overwriting Another User's Changes

Suppose two users A and B open the same note record. Both see the title "Draft" at the same point in time. A changes the title to "Approved draft" and saves first. A few seconds later, B saves an older edit with the title "B's draft".

If the server simply accepts the new data and writes it to the database, B's save can silently overwrite A's changes. This is a **lost update**: a user edits based on a stale version and the server fails to detect that the data has already changed.

ETag and If-Match solve this using HTTP conditional requests:

1. The server returns an ETag representing the current version of the resource.
2. The client retains the ETag alongside the data it read.
3. When editing, the client sends the ETag back in the If-Match header.
4. The server accepts the change only if the client's ETag still matches the current version.
5. If another client saved first, the stale client receives HTTP 412 Precondition Failed and must reload, compare, and decide how to merge.

Spring Data REST integrates this mechanism with the entity's version property. For Spring Data JPA, use Jakarta Persistence's @Version; for other Spring Data modules, use org.springframework.data.annotation.Version. When an entity is exported as a REST resource, Spring Data REST puts the version value into the ETag response header. PUT, PATCH, and DELETE can be conditioned with If-Match. If the ETag is stale, the server returns 412. See [Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html).

## 2. How ETag, If-Match, and @Version Work Together

| Component | Role | Example |
|---|---|---|
| @Version | Tracks entity revision in the datastore and supports optimistic locking | version = 0, increments to 1 after a successful update |
| ETag | Sends the resource validator in the HTTP response | ETag: "0" |
| If-Match | Instructs the server to perform the change only if the validator still matches | If-Match: "0" |
| If-None-Match | Checks whether GET needs to resend the representation | Matching ETag returns 304 Not Modified |
| 412 Precondition Failed | Indicates the If-Match condition is no longer satisfied | Client holds a stale ETag |
| 304 Not Modified | Indicates the representation has not changed relative to the client's ETag | Client can reuse its cached copy |

Two complementary layers of protection work together:

- **HTTP preconditions** verify which revision the client is editing against. This prevents users from submitting stale edits after another user has updated the resource.
- **Optimistic locking in the datastore** checks the revision at write time. If two transactions read the same version and write almost simultaneously, the database/persistence provider detects that the later write is using an outdated version.

With JPA, an update statement for a versioned entity checks the version currently stored in the database. When the version no longer matches the value read by the entity, the persistence provider reports an optimistic lock failure instead of overwriting the newer revision. The version value is incremented by the persistence provider; the application does not manually assign new versions.

### Do Not Confuse Write-Control ETags with Cache-Only ETags

Spring Framework provides ShallowEtagHeaderFilter to generate ETags from response content. This filter is useful for GET and If-None-Match/304, but the documentation explicitly notes that it does not handle state-changing preconditions such as If-Match. For Spring Data REST endpoints that need to prevent lost updates, use a datastore-backed @Version property and Spring Data REST's ETag mechanism. Do not merely add ShallowEtagHeaderFilter and assume PATCH/PUT are protected.

## 3. Declaring Version on the Entity

The example below uses Spring Boot 3.x, Spring Data JPA, and Jakarta Persistence:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Note {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private String title;

    protected Note() {
    }

    public Note(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Key details to get right:

- With JPA on Spring Boot 3 or later, import **jakarta.persistence.Version**. On older Boot 2 applications, the corresponding package is **javax.persistence.Version**.
- With Spring Data JDBC, MongoDB, and other Spring Data modules, use **org.springframework.data.annotation.Version** per that module's guide.
- A JPA entity should have only one version property. The property must be mapped to the entity's primary table and use a type supported by Jakarta Persistence, such as int, Integer, long, Long, or a timestamp type compatible with the specification version.
- Do not let clients update the version field directly in the request body. It is metadata managed by the persistence provider.
- You may omit exposing a version getter in the JSON representation if clients only need to keep the ETag header. Clients do not need to read or compute the version number themselves.
- If the database already contains data, migrations must add and initialize the version column for existing rows. Illustrative SQL example: ALTER TABLE note ADD COLUMN version BIGINT NOT NULL DEFAULT 0;. Adjust syntax and backfill strategy for your actual database.

The repository is exported by Spring Data REST as a collection resource:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "notes")
public interface NoteRepository extends JpaRepository<Note, Long> {
}
~~~

With default configuration, the collection resource is /notes and item resources follow /notes/{id}. An ETag used for editing a single record must be obtained from the **item resource**, such as /notes/42, not from the /notes collection.

## 4. Two-User Flow: A and B

Assume resource /notes/42 currently has ETag "0".

1. **A reads the resource.** GET /notes/42 returns the current content with ETag: "0". A keeps this body and ETag in edit state.
2. **B also reads the resource.** GET /notes/42 returns the same content and ETag: "0". B also holds revision 0.
3. **A saves first.** A sends PATCH with If-Match: "0". The precondition passes, so the server accepts the update. After saving, the version increments and subsequent responses carry a new ETag, such as "1".
4. **B saves using stale data.** B still sends If-Match: "0". The server is now at revision 1, so it rejects the request with 412 Precondition Failed. A's saved content remains intact.
5. **B resolves the conflict.** B fetches the latest resource, compares A's saved content against B's local draft, and either merges or asks the user to choose. Only send a new request with the new ETag after resolving the conflict.

This simulates two independent clients. The two requests do not have to execute concurrently on two threads to reproduce a stale update: it is enough for both to read the old revision and then sequentially submit writes. Under true transaction-level races, @Version continues to protect the write step in the datastore.

## 5. Testing Directly over HTTP

Start the application and create a Note with ID 42. Replace the URL and ID with your actual data.

### Both Clients Read

Client A:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/notes/42
~~~

Client B sends the same GET to that URI:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/notes/42
~~~

Both responses must include an ETag. Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "0"

{
  "title": "Draft",
  "_links": {
    "self": {
      "href": "http://localhost:8080/notes/42"
    }
  }
}
~~~

The value "0" is illustrative. Copy the exact ETag returned by the response verbatim, including quotation marks if present. Never assemble an ETag manually from an ID or a version field in JSON.

### A Updates with the ETag Just Read

Example using PATCH with JSON Merge Patch:

~~~bash
curl -i -X PATCH \
  -H 'If-Match: "0"' \
  -H "Content-Type: application/merge-patch+json" \
  -H "Accept: application/hal+json" \
  --data '{"title":"Approved by A"}' \
  http://localhost:8080/notes/42
~~~

In the example, replace "0" with the ETag A actually received. When the precondition still holds, the request is accepted. Depending on Spring Data REST's response body configuration, the update returns 200 OK or 204 No Content. Then re-GET the item resource to obtain the new ETag.

### B Submits an Edit Based on the Stale ETag

B still uses the ETag received before A saved:

~~~bash
curl -i -X PATCH \
  -H 'If-Match: "0"' \
  -H "Content-Type: application/merge-patch+json" \
  -H "Accept: application/hal+json" \
  --data '{"title":"Draft edited by B"}' \
  http://localhost:8080/notes/42
~~~

Expected result:

~~~http
HTTP/1.1 412 Precondition Failed
~~~

Verify again with GET /notes/42: the title is still "Approved by A". B's stale request was prevented from overwriting that data.

Spring Data REST also supports conditional PUT and DELETE using If-Match. PUT replaces the item's representation; PATCH updates only the submitted fields. Spring Data REST accepts application/json, application/hal+json, application/patch+json, and application/merge-patch+json for PATCH per the repository resources documentation.

## 6. Repeatable Testing with MockMvc

You can simulate two users with two separate GET calls inside a single test. Both retain the same initial ETag; the test lets A update successfully, then verifies B's request with the stale ETag is rejected.

Example using Spring Boot 3.x, JUnit Jupiter, Spring Data JPA, and Spring Data REST:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NoteEtagConcurrencyTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    NoteRepository notes;

    private Long noteId;

    @BeforeEach
    void prepareData() {
        notes.deleteAll();
        noteId = notes.saveAndFlush(new Note("Draft")).getId();
    }

    @Test
    void rejectsSecondClientUsingStaleEtag() throws Exception {
        // A and B read the same item resource before any update occurs.
        String etagA = fetchEtag();
        String etagB = fetchEtag();

        assertThat(etagA).isNotBlank();
        assertThat(etagB).isEqualTo(etagA);

        // A saves with a fresh ETag.
        mvc.perform(patch("/notes/{id}", noteId)
                .header(HttpHeaders.IF_MATCH, etagA)
                .contentType(MediaType.parseMediaType(
                    "application/merge-patch+json"))
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "title": "Approved by A"
                    }
                    """))
            .andExpect(status().is2xxSuccessful());

        // The current ETag has changed after A's update.
        String currentEtag = fetchEtag();
        assertThat(currentEtag).isNotEqualTo(etagA);

        // B submits the stale draft with the old ETag: the server must reject it.
        mvc.perform(patch("/notes/{id}", noteId)
                .header(HttpHeaders.IF_MATCH, etagB)
                .contentType(MediaType.parseMediaType(
                    "application/merge-patch+json"))
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "title": "Draft edited by B"
                    }
                    """))
            .andExpect(status().isPreconditionFailed());

        // A's change remains the persisted data.
        Note saved = notes.findById(noteId).orElseThrow();
        assertThat(saved.getTitle()).isEqualTo("Approved by A");
    }

    private String fetchEtag() throws Exception {
        MvcResult result = mvc.perform(
                get("/notes/{id}", noteId).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andReturn();

        return result.getResponse().getHeader(HttpHeaders.ETAG);
    }
}
~~~

Points to keep in mind when applying this:

- The test uses @SpringBootTest and @AutoConfigureMockMvc to run through the real Spring MVC and Spring Data REST configuration. MockMvc does not open an HTTP port.
- The test does not annotate the class with @Transactional. Fixtures are created via the repository before requests and cleaned up explicitly in @BeforeEach, keeping request transaction boundaries clear.
- If the application uses Spring Security, attach appropriate credentials/roles to each request. When simulating two different users, supply the corresponding authentication for each GET/PATCH call.
- If update responses are configured to return 204, `is2xxSuccessful()` still confirms A's operation succeeded. The focus of the test is the updated ETag and the stale request receiving 412.
- Run tests against a database that supports versioning consistent with your target environment. If relying solely on an embedded database, add integration tests against the production database engine when SQL dialect or transaction behavior matters.

MockMvc executes full Spring MVC request handling with mock requests/responses rather than a running server. See [Spring Framework MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html).

## 7. Handling 412 in the User Interface

Upon receiving 412, the client should not automatically resend the same payload with the new ETag. Doing so turns conflict detection into another blind overwrite.

A friendlier workflow:

1. Preserve the user's unsaved draft and the stale ETag.
2. Send GET to the same item URI to fetch the latest representation and new ETag.
3. Compare the draft against the latest data. You can show the previous value, current server value, and the user's pending input.
4. Let the user discard their draft, keep the latest version, or manually merge fields.
5. Once the user confirms the merged content, send PUT/PATCH with the new ETag.
6. If 412 is returned again, repeat the fetch-and-compare cycle.

Do not wipe out the draft immediately when the request fails. Keep it in form state or appropriate storage so the user does not lose their typing.

Whenever possible, store the ETag as soon as GET returns and refresh it after every successful write. Do not extract a version from the JSON body to construct the header string yourself; keep the exact ETag value returned by the server.

## 8. Distinguishing 412, 409, 428, and 304

| Status | Meaning in This Scenario | Client Action |
|---|---|---|
| 200 / 204 | Update succeeded, depending on response-body configuration | Update displayed data and store the new ETag if present |
| 304 Not Modified | GET with If-None-Match matches the current ETag | Reuse the cached representation |
| 409 Conflict | Business conflict or domain rule violation defined by the application | Display the business error and corresponding resolution |
| 412 Precondition Failed | ETag in If-Match no longer matches | Fetch fresh data and resolve the conflict |
| 428 Precondition Required | Server requires clients to send a precondition, but the request omitted it | Retry after obtaining a valid validator |

Spring Data REST documents 412 when an ETag sent in If-Match no longer matches. Do not assume that simply declaring @Version causes the server to require If-Match on every PUT/PATCH/DELETE and return 428 when the header is missing. If business requirements demand preconditions on all writes, implement that policy on the server (for example, via a filter or custom endpoint) and write dedicated tests for requests missing If-Match.

If-Match: * only requires the resource to exist. It does not assert that the client holds a specific revision, so do not use this wildcard to protect edits against lost updates.

## 9. Production Considerations

### Use the Right ETag for the Right Resource

- Obtain the ETag from the response of the exact item URI the user is editing.
- Keep surrounding quotes and any weak/strong prefix exactly as returned by the server.
- Never use an ETag from a collection, related resource, or another query URI for the current item.
- Never reuse an old ETag after a successful write.
- If no ETag is returned, halt conditional writes and check @Version configuration, repository mapping, or response setup. Never guess a version value.

### Guard Every Write Path

Spring Data REST's ETag handling only protects operations flowing through its mechanism. If the application also has custom controllers, batch jobs, scheduled jobs, or direct modifying repository queries, those write paths must respect optimistic locking as well.

In particular, bulk updates via JPQL/SQL bypass the normal entity lifecycle. Do not assume they automatically enforce @Version like saving an entity does. If using bulk updates, explicitly include version conditions and increment the version, or load and update entities through versioned persistence.

If an aggregate's representation includes data from related entities, decide whether changes to child entities should increment the aggregate root's version. If an edit changes content a user is currently modifying without changing the root's ETag, the validator will not reflect the true conflict scope. Choose appropriate aggregate boundaries and versioning strategies.

### CORS with Cross-Origin Frontends

If the frontend runs on a different origin from the API, the browser must be allowed to read the ETag response header and send the If-Match request header. CORS configuration must:

- Expose the ETag response header via Access-Control-Expose-Headers.
- Allow the If-Match request header via Access-Control-Allow-Headers.
- Allow required methods such as GET, PUT, PATCH, and DELETE.
- Restrict origins to your actual frontend domains.

If Expose-Headers is missing, JavaScript cannot read ETag even though the header appears in DevTools. If Allow-Headers is missing, the browser may block the preflight request before sending PATCH.

### Never Mutate Version Manually

Version is metadata managed by the persistence provider or Spring Data datastore. Never accept a client-sent version and assign it directly onto an entity. If displaying a revision in the UI is needed, treat the ETag header as an opaque token. This keeps clients decoupled from storage types or how the framework formats versions.

## 10. Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| GET item has no ETag | Entity lacks @Version, wrong module annotation imported, resource bypasses Spring Data REST, or calling collection instead | Verify version mapping and call the item URI |
| Two clients get different ETags without any update | Requests hit different URIs/resources, or data changed between GETs | Check URI, ID, and read timing; use deterministic fixtures in tests |
| Stale PATCH still succeeds | Request lacks If-Match, uses wildcard *, or hits a custom endpoint ignoring ETag | Inspect request headers and actual handler path |
| PATCH always returns 412 | Quotes were altered in header, ETag came from another URI, or data already changed | Copy the latest ETag verbatim from GET on the target item URI |
| A succeeds but ETag does not change | Version did not increment, update bypassed persistence versioning, or response omitted validator | Check @Version, SQL/update path, and post-save response headers |
| UI cannot read ETag | CORS did not expose the response header | Add ETag to Access-Control-Expose-Headers |
| Browser cannot send If-Match | CORS preflight disallows the request header | Add If-Match to Access-Control-Allow-Headers |
| Optimistic locking failure in background job | Another transaction updated the entity after the job read it | Reload entity and retry per business rules; never blindly save stale objects |
| Test fails to reproduce conflict | Second client re-read after first write, or test reused the newer ETag for both | Capture ETag A and B separately before any write occurs |
| Bulk update ignores stale versions | JPQL/SQL bulk update bypasses normal entity lifecycle | Add explicit version checks and increments, or update entities via repository |
| Requests missing If-Match still succeed | Application lacks a mandatory precondition policy | If required by business rules, enforce server-side and test for 428 |
| Stale DELETE is not rejected | DELETE omitted If-Match or custom endpoint ignored ETag | Test DELETE on item resource and send the current validator |

When debugging, log the method, item URI, server-returned ETag, client-sent If-Match, and response status. Do not log sensitive entity contents or authentication tokens solely for conflict tracing.

## 11. Running Tests

Maven:

~~~bash
./mvnw -Dtest=NoteEtagConcurrencyTests test
~~~

Gradle:

~~~bash
./gradlew test --tests '*NoteEtagConcurrencyTests'
~~~

Run all tests:

~~~bash
./mvnw test
~~~

or:

~~~bash
./gradlew test
~~~

If tests require an external database, start the database or Testcontainers per your project configuration. Run versioning tests on a real datastore whenever transaction semantics, SQL dialects, or update mechanisms differ.

## 12. Official Documentation

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): how @Version produces ETag, using If-Match for PUT/PATCH/DELETE, handling 412, and using If-None-Match for GET/304.
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection/item URIs, HTTP methods, media types, and status codes of repository resources.
- [Spring Data Commons — @Version API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/annotation/Version.html): marking a version property for optimistic locking.
- [Jakarta Persistence — @Version API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Version.html): version fields/properties, supported types, and detecting optimistic lock failures.
- [Jakarta Persistence 3.2 — Optimistic Locking](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): version checking rules on update/delete and persistence provider responsibilities.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): full Spring MVC request handling tests with mock requests/responses.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): ETag, If-None-Match, 304, and conditional requests in Spring MVC.
- [Spring Framework — Filters / Shallow ETag](https://docs.spring.io/spring/reference/web/webmvc/filters.html): limitations of ShallowEtagHeaderFilter regarding state-changing preconditions.
- [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1): If-Match conditional semantics and strong comparison.