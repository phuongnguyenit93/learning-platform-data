# HTTP 412 Precondition Failed When the If-Match Condition Is No Longer Valid

## 1. Meaning of the error

HTTP 412 occurs when a precondition sent in request headers is no longer true for the current state of the resource on the server. In Spring Data REST, the typical case is when a client sends a stale If-Match value after the resource was updated by another client.

This is the optimistic concurrency control mechanism. It prevents "lost updates": two users read the same record, the first saves changes, and then the second accidentally overwrites the new data with an outdated copy.

Spring Data REST uses ETag to mark resource versions. If the domain object has a version field recognized via @Version, the resource's ETag is derived from that version value. With Spring Data JPA, use JPA's @Version annotation; with other Spring Data modules, use org.springframework.data.annotation.Version. When a client sends PUT, PATCH, or DELETE with If-Match, Spring Data REST executes the operation only if the current ETag matches the value sent by the client. If it does not match, the request receives HTTP 412 Precondition Failed.

## 2. Sequence of events leading to 412

Suppose two clients A and B both read the resource /people/42:

1. A sends GET /people/42 and receives ETag: "5".
2. B also sends GET /people/42 and receives ETag: "5".
3. A updates the resource with If-Match: "5". The precondition still holds, so the operation succeeds; the server saves the new version and returns a new ETag, e.g., "6".
4. B still holds the old copy and sends an update with If-Match: "5".
5. The current ETag is already "6", so B's If-Match condition fails. The server returns 412 and does not apply B's changes.

The numbers "5" and "6" are illustrative only. Actual ETag values depend on the persistence store and resource version. Clients must treat ETag as an opaque server-issued string and never parse or increment the version themselves.

## 3. Configuring version so Spring Data REST emits ETag

For a JPA entity, declare a version field on the domain object:

    import com.fasterxml.jackson.annotation.JsonIgnore;
    import jakarta.persistence.Entity;
    import jakarta.persistence.GeneratedValue;
    import jakarta.persistence.Id;
    import jakarta.persistence.Version;

    @Entity
    public class Person {

        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;

        @Version
        @JsonIgnore
        private Long version;

        protected Person() {
        }

        public Person(String firstName, String lastName) {
            this.firstName = firstName;
            this.lastName = lastName;
        }

        public Long getId() {
            return id;
        }

        public String getFirstName() {
            return firstName;
        }
    }

Use jakarta.persistence.Version in modern Jakarta Persistence applications; legacy projects use javax.persistence.Version. With Spring Data MongoDB, Cassandra, or other Spring Data modules, use org.springframework.data.annotation.Version per the respective module's documentation.

The version field is managed by the persistence layer. Do not require clients to send or update this field manually. @JsonIgnore is optional if you do not want to expose version in the JSON body; Spring Data REST can still use version metadata to generate the ETag response header.

Test GET on a specific resource URI, such as /people/42. Embedded data in a collection response is only a preview; to obtain an ETag, call each item's self URI. A successful response should include headers like:

    HTTP/1.1 200 OK
    ETag: "5"
    Content-Type: application/hal+json

If ETag is missing, check whether the @Version annotation is the right type for the persistence module and whether the version field resides on the domain object managed by the repository.

## 4. Sending conditional requests

First, read the resource and preserve the exact ETag value from the response:

    curl -i http://localhost:8080/people/42

Suppose the response returns ETag: "5". Use that exact value in the update request:

    curl -i -X PATCH http://localhost:8080/people/42 -H 'Content-Type: application/json' -H 'If-Match: "5"' --data '{"firstName":"Lan"}'

If the resource still has ETag "5", the operation is accepted. After updating, the response may return a new ETag. The client should store the new ETag alongside the newly received representation.

To reproduce the error, perform a successful update first, then send a second request with the old ETag:

    curl -i -X PATCH http://localhost:8080/people/42 -H 'Content-Type: application/json' -H 'If-Match: "5"' --data '{"firstName":"Linh"}'

If the first update changed the version, the second request receives 412 Precondition Failed. Changes in the second request's body are not written to the resource.

The same mechanism applies to PUT and DELETE. For PUT, send the full representation per the endpoint contract. For PATCH, send only the fields to change. In both cases, take If-Match from the ETag of the most recent resource read.

Notes:
- Keep quotation marks in the ETag if the server returns a quoted value. Do not strip quotes or prepend prefixes.
- Use the ETag only for the exact resource URI the client read. Do not use one item's token for another item or reuse a token from a different query.
- If-Match: * only checks whether the resource exists; it does not protect an update against a stale version. To detect changed data, send a specific ETag.
- Do not manually increment the version value and do not substitute a JSON version field for the ETag response header.

## 5. Handling 412 on the client

412 signals that the copy the user is editing is stale. Safe handling steps:

1. Preserve the content the user intended to save and display a notice that the data has changed.
2. Call GET again on the exact resource URI to retrieve the current representation and ETag.
3. Compare the user's edited copy with the latest version on the server. Keep non-conflicting edits and ask the user to choose when the same field changed on both sides.
4. After merging, send a new request with the ETag obtained from the fresh GET.
5. If 412 is returned again, repeat the read and reconciliation step because another user may have updated the resource again.

Do not automatically resend the exact old body with the new ETag. Doing so defeats the purpose of optimistic locking and can overwrite the very changes 412 was protecting.

Client-side logic example:

    const response = await updateResource(uri, draft, oldEtag);

    if (response.status === 412) {
        const latest = await fetchResource(uri);
        showConflictResolution({
            userDraft: draft,
            serverVersion: latest.body,
            currentEtag: latest.headers.get("ETag")
        });
    }

After the user confirms the merged version, send the update with currentEtag. Do not rely on the body content of a 412 response because the error body may vary by exception handling configuration; use the status code to detect precondition failure.

If the frontend runs on a different origin than the API, configure CORS so the browser can send the If-Match header and read the ETag response header. Specifically, Access-Control-Allow-Headers must permit If-Match and Access-Control-Expose-Headers must expose ETag. Without the expose header, JavaScript cannot read ETag even if the header appears in the network response.

## 6. Distinguishing 412, 409, and 304

- 412 Precondition Failed: a request precondition such as If-Match does not match the current state. In Spring Data REST, this is the response for an update with a stale ETag.
- 409 Conflict: the request conflicts with the resource's state or business rules. This is an application-level conflict; it is not synonymous with If-Match failure.
- 304 Not Modified: response to a conditional cache GET/HEAD such as If-None-Match or If-Modified-Since when the representation has not changed. 304 is not an update error.

If-Match primarily protects state-changing operations. If-None-Match is typically used to avoid re-downloading an unchanged representation on GET.

## 7. Regression testing

### Manual testing with two clients

1. Create a record and call GET on the item URI to obtain its ETag.
2. Open two clients A and B; both read the same resource and save the same initial ETag.
3. A sends PATCH with the initial ETag. Verify the response succeeds.
4. B sends PATCH with the old ETag. Verify the response has status 412.
5. Call GET to verify A's saved value remains intact, B's change was not applied, and the ETag has changed.
6. B reads the new representation, merges changes, then sends PATCH with the new ETag. Verify the operation succeeds.
7. Repeat the scenario with DELETE to confirm the delete endpoint also rejects stale ETags.

### Integration test example with MockMvc

Place the test in a Spring Boot integration context so Spring Data REST registers real repository endpoints. The example below assumes PersonRepository, entity Person, and endpoint /people/{id}; adjust constructor, property names, and paths to your application.

    @SpringBootTest
    @AutoConfigureMockMvc
    class PersonIfMatchTests {

        @Autowired
        MockMvc mvc;

        @Autowired
        PersonRepository people;

        @Test
        void rejectsUpdateWhenIfMatchIsStale() throws Exception {
            Person person = people.save(new Person("Alice", "Nguyen"));
            String path = "/people/" + person.getId();

            String etagA = mvc.perform(get(path))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getHeader(HttpHeaders.ETAG);

            String etagB = mvc.perform(get(path))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getHeader(HttpHeaders.ETAG);

            assertThat(etagA).isNotBlank();
            assertThat(etagB).isEqualTo(etagA);

            mvc.perform(patch(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.IF_MATCH, etagA)
                    .content("{\"firstName\":\"Alicia\"}"))
                    .andExpect(status().is2xxSuccessful());

            mvc.perform(patch(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.IF_MATCH, etagB)
                    .content("{\"firstName\":\"Ally\"}"))
                    .andExpect(status().isPreconditionFailed());

            Person stored = people.findById(person.getId()).orElseThrow();
            assertThat(stored.getFirstName()).isEqualTo("Alicia");
        }
    }

Common static imports used in tests:

    import static org.assertj.core.api.Assertions.assertThat;
    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

    import org.springframework.http.HttpHeaders;
    import org.springframework.http.MediaType;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.test.web.servlet.MockMvc;
    import org.junit.jupiter.api.Test;

The test verifies three things: GET resource returns an ETag; updating with the current ETag succeeds; the second request using the stale ETag receives 412 and does not overwrite saved data. Add a test for DELETE with a stale ETag and a CORS test if the frontend calls the API from another origin.

## 8. Troubleshooting checklist

| Symptom | Check and resolution |
|---|---|
| GET has no ETag | Call the item URI rather than the collection; check @Version and ensure the annotation type matches the persistence module. |
| Request always receives 412 | Re-fetch ETag via GET right before updating; verify exact URI, preserve quotation marks, and check that the actual request sends If-Match. |
| Two users update yet old changes still overwrite | Confirm the entity has a version recognized by Spring Data REST; confirm the client does not drop the If-Match header. |
| Browser cannot read ETag | Configure Access-Control-Expose-Headers: ETag and permit If-Match in CORS preflight. |
| GET returns 304 | Check whether the client is sending If-None-Match; 304 is cache validation, distinct from 412 precondition failure on updates. |
| Logs show ETagDoesntMatchException | Compare expected ETag against the entity's current version; this exception indicates the ETag computed from the object did not match the requested ETag. |

## 9. References

- [Spring Data REST 5.1.2 — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): how @Version generates ETag, using If-Match for PUT/PATCH/DELETE, and 412 responses.
- [Spring — React.js and Spring Data REST: Part 3, Conditional Operations](https://spring.io/blog/2015/09/29/react-js-and-spring-data-rest-part-3-conditional-operations/): example entity with @Version, reading ETag from GET item, and handling status 412 on the client.
- [RFC 9110, Section 13.1.1 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1): syntax, strong comparison, and rule not to execute the method when the condition fails.
- [RFC 9110, Section 13.2.2 — Precedence of Preconditions](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.2.2): evaluation order of HTTP preconditions.
- [RFC 9110, Section 15.5.13 — 412 Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.13): standard definition of status 412.
- [Spring Data REST API — ETagDoesntMatchException](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/support/ETagDoesntMatchException.html): exception when the ETag computed from an object does not match the expected value.