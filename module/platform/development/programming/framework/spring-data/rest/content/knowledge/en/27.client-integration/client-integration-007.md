# Storing ETags and Handling Edit Conflicts in the UI

## 1. Why does the frontend need to store ETag?

A user opens a record and begins editing it. While the form remains open, another user may update the same resource. If the frontend submits stale data via PUT or PATCH without checking the version, the other user's recent changes can be overwritten.

This is a lost update scenario:

1. User A GETs the resource and receives version 7.
2. User B also GETs version 7.
3. User A updates successfully; the server saves version 8.
4. User B still holds a form based on version 7.
5. If the server accepts User B's write without checking the version, User A's edits can be overwritten.

HTTP ETag combined with the If-Match request header detects this situation. The frontend stores the ETag received from GET and sends it back verbatim on update. The server accepts the operation only if the resource still matches that validator.

In Spring Data REST, an ETag can be generated from an entity's version property. With Spring Data JPA, the @Version annotation is typically used.

## 2. ETag is a resource validator

An ETag is a server-issued value identifying a version of a representation. Example GET response:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"

{
  "id": 42,
  "name": "Alice",
  "department": "Sales"
}
~~~~

The frontend must store the exact verbatim value of the ETag header, including quotation marks if present. ETag is an opaque validator; the client must never increment numbers, strip quotes, or predict the next version.

Storing example:

~~~~javascript
const etag = response.headers.get("ETag");
~~~~

Never use a UI timestamp or a client-incremented version field as a substitute for the server-issued ETag.

ETags typically come in strong or weak forms:

- Strong ETag: "7".
- Weak ETag: W/"7".

If-Match uses strong comparison according to HTTP Semantics. For conditional updates, the server should provide an appropriate strong validator. Clients must never convert a weak ETag into a strong ETag.

## 3. Enabling version metadata in Spring Data

Spring Data REST can emit an ETag from a domain object's version property.

JPA entity example:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @jakarta.persistence.Version
    private Long version;

    private String name;

    private String department;
}
~~~~

When the entity is successfully updated, the persistence provider manages the version. The next GET receives a new ETag if the version changed.

For non-JPA Spring Data modules, the version annotation can be org.springframework.data.annotation.Version:

~~~~public class Person {

    @Id
    private String id;

    @org.springframework.data.annotation.Version
    private Long version;

    private String name;
}
~~~~

Use the annotation appropriate for the store in use. Do not assume every repository emits an ETag merely because the entity has a field named version. Inspect real GET responses to verify the ETag header is present.

@Version also enables optimistic locking at the persistence layer. ETag/If-Match surfaces that version check as an explicit precondition in the HTTP API.

## 4. Flow for GET, storing ETag, and sending updates

A basic frontend workflow:

1. Send GET to the item resource.
2. Read the response body and ETag header.
3. Store the body as the form's initial snapshot.
4. Store the ETag alongside the resource URI.
5. The user edits the form.
6. Send PUT or PATCH with an If-Match header containing the stored ETag.
7. On success, update the body and ETag from the new response.
8. On 412, keep the user's draft and initiate conflict resolution.

Example GET:

~~~~http
GET /people/42 HTTP/1.1
Accept: application/hal+json
~~~~

Response:

~~~~http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/hal+json
~~~~

The frontend stores ETag "7". When the user updates name, send PATCH:

~~~~http
PATCH /people/42 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json
If-Match: "7"

{
  "name": "Alice Nguyen"
}
~~~~

If the resource is still at version 7, the server applies the patch. If the resource has changed and the current ETag no longer matches, the server rejects the precondition and returns 412 Precondition Failed.

## 5. If-Match prevents overwriting stale versions

If-Match instructs the server to execute the method only if the resource's validator matches one of the supplied ETags.

Example:

~~~~http
If-Match: "7"
~~~~

If the current ETag is "7", the precondition passes. If the current ETag has become "8", the precondition fails and the server must not apply the change from that request.

A request can include multiple ETags:

~~~~http
If-Match: "6", "7"
~~~~

The server checks whether the current entity tag strong-matches any value in the list.

Wildcard:

~~~~http
If-Match: *
~~~~

Wildcard only requires that the resource currently exists. It does not prove the client is editing the latest version and does not prevent lost updates between two users reading the same version. When the goal is optimistic concurrency, send the specific ETag received from GET.

Never synthesize If-Match from a guessed version number on the client. Always use the validator issued by the server.

## 6. Both PUT and PATCH can use If-Match

If-Match is an HTTP precondition and can be used with resource-mutating methods such as PUT, PATCH, and DELETE.

- PUT typically sends a replacement representation per the endpoint contract.
- PATCH sends a document describing partial changes.
- If-Match ensures the operation is applied only if the resource is still at the version the client read.

Example PUT:

~~~~http
PUT /people/42 HTTP/1.1
Content-Type: application/json
If-Match: "7"

{
  "name": "Alice Nguyen",
  "department": "Engineering"
}
~~~~

Example PATCH:

~~~~http
PATCH /people/42 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "7"

{
  "department": "Engineering"
}
~~~~

If the client only edits one field, PATCH reduces the risk of resending stale unrelated fields. Still, PATCH requires If-Match to avoid applying updates against an outdated version.

## 7. Distinguishing 412 Precondition Failed and 409 Conflict

These two status codes are often confused during conflict handling:

| Status | Meaning | Example |
|---|---|---|
| 412 Precondition Failed | The HTTP precondition on the request was not met | The ETag sent in If-Match is stale |
| 409 Conflict | The request conflicts with current state or business rules | An order has already shipped and cannot be canceled |

Example of 412:

- Frontend reads ETag "7".
- Someone else updates the resource; ETag becomes "8".
- Frontend sends PATCH with If-Match "7".
- Server returns 412 and does not apply the patch.

Example of 409:

- Frontend reads a resource in DRAFT status.
- Current business rules disallow transitioning a shipped order back to DRAFT.
- The request may carry a valid ETag, yet the operation still violates business rules.
- Server returns 409 Conflict per the application contract.

If an API requires every update to include If-Match and the client omits the header, 428 Precondition Required per RFC 6585 can be used. Enforcing the header must be configured or checked on the server; simply adding @Version does not automatically require every endpoint to reject requests without If-Match.

## 8. The frontend should keep both the original and draft copies

When opening a form, the frontend should retain three values:

- **Original snapshot:** the initial body retrieved via GET.
- **Draft:** the data currently edited by the user.
- **ETag:** the validator paired with the original snapshot.

Example state:

~~~~javascript
const [original, setOriginal] = useState(null);
const [draft, setDraft] = useState(null);
const [etag, setEtag] = useState(null);
const [saving, setSaving] = useState(false);
const [conflict, setConflict] = useState(false);
~~~~

When GET succeeds:

~~~~javascript
async function loadPerson(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/hal+json"
    }
  });

  if (!response.ok) {
    throw new Error("Could not load person");
  }

  const body = await response.json();
  const versionTag = response.headers.get("ETag");

  setOriginal(body);
  setDraft(body);
  setEtag(versionTag);
}
~~~~

Do not store ETag in a single global variable shared across resources. An ETag must be tied to the exact URI and representation it validates. When switching to another resource, replace the body, draft, and ETag together.

## 9. Sending PATCH with If-Match from JavaScript

Example:

~~~~javascript
async function savePerson(url, patch, etag) {
  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/merge-patch+json",
      "Accept": "application/hal+json",
      "If-Match": etag
    },
    body: JSON.stringify(patch)
  });

  if (response.status === 412) {
    return { kind: "conflict" };
  }

  if (!response.ok) {
    return {
      kind: "error",
      status: response.status
    };
  }

  const nextEtag = response.headers.get("ETag");

  if (response.status === 204) {
    return {
      kind: "saved",
      etag: nextEtag
    };
  }

  const body = await response.json();

  return {
    kind: "saved",
    body,
    etag: nextEtag
  };
}
~~~~

This is an illustrative example. A Spring Data REST update response may return a representation or 204 No Content depending on Accept and return-body configuration. If a successful response does not include a new ETag, the frontend can GET the resource again to obtain the fresh body and ETag before allowing the next edit.

Never reuse an old ETag after a successful update. A save can increment the version and change the validator.

## 10. How should the UI handle 412?

When receiving 412, do not discard the user's draft and do not immediately resend the same patch with the new ETag.

An appropriate workflow:

1. Preserve the active draft being edited.
2. Notify the user that the resource was modified by someone else.
3. GET the latest resource and store the new body and ETag.
4. Compare the original snapshot, draft, and latest version.
5. Automatically merge disjoint fields if business rules allow.
6. If the same field was changed by both sides, ask the user to choose the final value.
7. Once the conflict is resolved, send a new patch with the new ETag.

Example notice:

~~~~text
This record changed while you were editing it.
Your draft has been kept. Review the latest version
before saving your changes again.
~~~~

The UI can offer options:

- Load the latest version and discard the draft.
- View diffs across the original, draft, and latest versions.
- Apply your changes on top of the latest version.
- Keep some fields from the server and some fields from the draft.

Avoid providing an "Overwrite anyway" button unless the API explicitly defines an intentional overwrite mechanism. If such a feature exists, it must be authorized and made explicit to the user.

## 11. Three-way comparison for merging

Suppose the original snapshot is:

~~~~json
{
  "name": "Alice",
  "department": "Sales",
  "phone": "111"
}
~~~~

User A's draft:

~~~~json
{
  "name": "Alice Nguyen",
  "department": "Sales",
  "phone": "111"
}
~~~~

Latest server version after User B updated it:

~~~~json
{
  "name": "Alice",
  "department": "Engineering",
  "phone": "111"
}
~~~~

Both users edited different fields:

- User A edited name.
- User B edited department.

The application can merge them into:

~~~~json
{
  "name": "Alice Nguyen",
  "department": "Engineering",
  "phone": "111"
}
~~~~

Then send PATCH with the new ETag obtained from the latest server version.

If both users edited name, the application must not silently pick a final value without business rules. It can display the original, the current user's value, and the latest server value so the user can decide.

For complex fields such as collections, associations, workflow states, or monetary amounts, automatic merging requires explicit domain rules. Simple field-level JSON diffing is insufficient to guarantee business correctness.

## 12. Never blindly retry after 412

A common mistake is receiving 412, fetching the new ETag, and resending the exact same old body. That only swaps the header while still overwriting changes someone else just saved.

Example:

1. Client A reads name = Alice, ETag "7".
2. Client B changes name to Alicia, ETag becomes "8".
3. Client A sends name = Alice Nguyen with ETag "7" and receives 412.
4. If Client A fetches ETag "8" and resends the exact same body Alice Nguyen, Client B's edit is overwritten.

The right approach is to fetch the latest version, compare, and merge intentionally before sending a new request.

Automatic retries are appropriate only when the operation is idempotent and the application defines a safe merge rule. Otherwise, preserve the draft and ask the user to resolve the conflict.

## 13. Storing ETags with cache entries

If the frontend caches resources, store the ETag along with the body and cache key:

~~~~javascript
const cacheEntry = {
  uri: "/people/42",
  body: person,
  etag: response.headers.get("ETag"),
  fetchedAt: Date.now()
};
~~~~

When reopening the form:

- Use the cached body for fast display if appropriate.
- Revalidate with If-None-Match when freshness needs to be checked.
- If 304 is returned, the cached body remains valid.
- If 200 is returned, replace the body and ETag.
- If the user is actively editing, never silently overwrite the draft with a new body; transition to conflict handling or notify the user that the data changed.

Never use a collection's ETag to update an item. An ETag must be bound to the exact resource URI and representation. If responses vary by media type or query parameters, the cache key must reflect those variants.

## 14. CORS when frontend and Spring Data REST are on different origins

If the frontend runs on a different origin from the API, the browser must be allowed to send If-Match and read ETag.

CORS configuration must:

- Allow the If-Match request header.
- Expose the ETag response header so JavaScript can read it.
- Allow the corresponding PUT/PATCH methods.
- Allow the specific frontend origin.
- Handle preflight OPTIONS before authentication when Spring Security is enabled.

Global Spring Data REST CORS configuration example:

~~~~java
@Override
public void configureRepositoryRestConfiguration(
        RepositoryRestConfiguration config,
        CorsRegistry cors) {

    cors.addMapping("/people/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "PUT", "PATCH")
        .allowedHeaders(
            "Content-Type",
            "If-Match",
            "If-None-Match",
            "Authorization"
        )
        .exposedHeaders("ETag", "Location", "Link");
}
~~~~

With Spring Security, align the policy in CorsConfigurationSource and enable http.cors() so preflight requests are handled before authentication. CORS does not replace authentication or authorization.

If JavaScript cannot read ETag even though the response includes the header, inspect exposedHeaders. If preflight fails, check whether allowedHeaders includes If-Match.

## 15. Testing optimistic concurrency with MockMvc

Include integration tests verifying that two clients can read the same ETag, yet only one client's update succeeds.

Example:

~~~~java
MvcResult firstGet = mockMvc.perform(
        get("/people/{id}", 42L)
            .accept(MediaType.APPLICATION_HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

String etag = firstGet.getResponse()
        .getHeader(HttpHeaders.ETAG);

assertThat(etag).isNotNull();

mockMvc.perform(
        patch("/people/{id}", 42L)
            .contentType("application/merge-patch+json")
            .header(HttpHeaders.IF_MATCH, etag)
            .content("""
                {
                  "name": "Alice Nguyen"
                }
                """)
    )
    .andExpect(status().is2xxSuccessful());

mockMvc.perform(
        patch("/people/{id}", 42L)
            .contentType("application/merge-patch+json")
            .header(HttpHeaders.IF_MATCH, etag)
            .content("""
                {
                  "department": "Engineering"
                }
                """)
    )
    .andExpect(status().isPreconditionFailed());
~~~~

This test illustrates two updates using the same validator. After the first update, the version changes, so the second update with the old ETag is rejected.

Additional checks to include:

1. GET returns ETag.
2. Matching If-Match allows the update.
3. Successful update produces a new ETag.
4. Stale If-Match returns 412.
5. The resource is left unmodified by a 412 request.
6. Wildcard only checks resource existence and must not be used to simulate version checks.
7. Missing If-Match is handled per the API policy.
8. Frontend retains the draft upon conflict.
9. Merging disjoint fields creates a new request with the new ETag.
10. CORS allows If-Match and exposes ETag when cross-origin.

The exact success status code for an update response depends on Spring Data REST's return-body configuration. Tests should accept status codes according to the application contract rather than assuming every update returns 200.

## 16. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| PATCH always succeeds despite stale data | Not sending If-Match or server does not check preconditions | Send the stored ETag and verify server support |
| Repeatedly receiving 412 | Frontend retains old ETag after update or caches wrong URI | Update ETag after saving and bind it to the right resource |
| JavaScript cannot read ETag | CORS does not expose ETag | Add ETag to exposedHeaders |
| Preflight is rejected | If-Match is missing from allowedHeaders | Update the CORS policy |
| Retry after 412 overwrites newer edits | Fetched new ETag and resent old draft verbatim | Fetch latest, compare, and merge before retrying |
| UI loses user input | Form reset upon receiving 412 | Keep the draft and display conflict state |
| A field gets overwritten during merge | Both sides edited the field and the app picked one automatically | Display the diff and ask the user to choose |
| Using collection ETag to update an item | Cache key does not distinguish collection from item | Store ETags per URI/representation |
| No ETag in response | Entity/store lacks version metadata or endpoint does not emit validators | Check @Version and real responses |
| Using If-Match: * to prevent lost updates | Wildcard only asserts resource existence | Send the specific ETag from GET |
| Confusing 409 with 412 | Not distinguishing business conflict from HTTP precondition | Use 412 for mismatched If-Match; 409 for business conflicts |
| Update succeeds but frontend keeps using old ETag | Did not capture or refresh the new validator | Read the response ETag or re-GET the resource |

## 17. Conclusion

The frontend should store the ETag alongside the resource body and URI on GET. When sending PUT or PATCH, include the ETag in If-Match so the server detects whether data changed since it was read. Spring Data REST can generate ETags from a version property; for JPA, use @Version. If the precondition fails, the server returns 412 and does not apply the update.

Upon receiving 412, the UI must preserve the draft, fetch the latest version, compare against the original snapshot, and resubmit only after merging or user conflict resolution. Never swap the old ETag for the new ETag and retry the original body unchanged, as that can overwrite another user's edits. Distinguish 412 for failed preconditions from 409 for business conflicts. When the frontend is cross-origin, CORS must allow If-Match and expose ETag. Test two clients using the same ETag to verify that only the first update succeeds.

## References

- [Spring Data REST — Conditional Operations with ETag and If-Match](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1)
- [RFC 6585 — 428 Precondition Required](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)
- [Spring Data JPA — Locking and @Version](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
