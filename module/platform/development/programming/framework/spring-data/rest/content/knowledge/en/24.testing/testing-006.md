# Testing JSON Patch, Merge Patch, Omitted Fields, and Null Values

Spring Data REST supports `PATCH` on item resources to partially update an entity. When testing, distinguish between patch formats, fields omitted from the request, fields sent with a `null` value, and non-writable properties. These four scenarios can produce different outcomes even though every payload is JSON.

This lesson uses an example resource `/customers/42` with properties `name`, `nickname`, `note`, `address`, `id`, and `version`. Substitute the endpoints and domain model of your actual application.

## 1. Distinguishing PUT and PATCH Formats

Spring Data REST currently lists the following media types for `PATCH`:

- `application/json` — partial update using Spring Data REST's binding mechanism.
- `application/patch+json` — JSON Patch per Spring Data REST documentation.
- `application/merge-patch+json` — JSON Merge Patch per RFC 7396.
- `application/hal+json` — HAL representation.

RFC 6902 registers the standard JSON Patch media type as `application/json-patch+json`. Current Spring Data REST documentation lists `application/patch+json`; some Spring security advisories also mention `application/json-patch+json`. Therefore, verify which media type your exact application version accepts. If you receive `415 Unsupported Media Type`, check the converters and media types of the running release.

| Request | Meaning | Fields absent from payload |
|---|---|---|
| `PUT application/json` | Replaces resource state per PUT semantics | Must send full representation; do not rely on PATCH preservation behavior |
| `PATCH application/json` | Spring Data REST applies partial update onto existing entity | Keeps unsent fields unchanged |
| JSON Patch | Executes a list of operations on a JSON document | If no operation targets a field, that field does not change |
| JSON Merge Patch | Merges patch object into current JSON representation | Members omitted from patch remain unchanged |

Do not confuse `Content-Type` with `Accept`: Content-Type specifies the patch format the client sends; Accept specifies the response representation the client wants to receive.

## 2. Omitted Fields vs. Null

Suppose the initial data is:

~~~json
{
  "id": 42,
  "name": "An",
  "nickname": "Annie",
  "note": "Call after 18:00",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "version": 5
}
~~~

With a partial update, if the client only sends:

~~~json
{
  "name": "Binh"
}
~~~

then `name` is changed to `Binh`; `nickname`, `note`, and `address` were not sent and should remain intact.

If the client sends:

~~~json
{
  "name": "Binh",
  "nickname": null
}
~~~

then `nickname` was explicitly sent with a JSON null value. This is a different instruction from omitting the `nickname` key from the payload.

In Java, reference properties can accept null; primitive properties like `int` or `boolean` cannot hold a null state. If business logic must clearly distinguish "not sent", "clear value", and "assign null", use wrapper/nullable types or a DTO with explicit presence tracking.

With Spring Data REST's `PATCH application/json`, `DomainObjectReader` applies the ObjectNode onto the existing entity, so fields omitted from the patch object are preserved. Fields present with a null value are bound as explicitly supplied values, provided the property is writable and nullable. Validation, Jackson mapping, Java types, and persistence constraints can still reject or transform the result; always reload the entity after updating to confirm.

## 3. JSON Patch: Operations Specify Exact Changes

JSON Patch per RFC 6902 is an array of operations. Operations are applied sequentially in the exact array order. Each operation has `op` and `path`; some operations also require `value` or `from`.

Six standard operations:

| Operation | Effect | Key preconditions |
|---|---|---|
| `add` | Adds an object member or inserts an array element; if object member already exists, replaces its value | Parent object/array must exist |
| `remove` | Removes member or element at path | Target must exist |
| `replace` | Replaces value at path | Target must exist |
| `move` | Removes at `from` then adds at `path` | `from` must exist; cannot move into its own descendant |
| `copy` | Copies value from `from` to `path` | `from` must exist |
| `test` | Verifies current value equals `value` | Mismatch causes patch failure |

Example changing name and checking state before applying:

~~~json
[
  { "op": "test", "path": "/status", "value": "ACTIVE" },
  { "op": "replace", "path": "/name", "value": "Binh" }
]
~~~

Example adding a note:

~~~json
[
  { "op": "add", "path": "/note", "value": "Confirmed" }
]
~~~

If `note` already exists, `add` on an object member replaces the current value. For arrays, `add` inserts an element at the index and shifts subsequent elements right; path `/-` appends to the end of the array.

### 3.1. Replace null and remove are not identical

JSON Patch clearly distinguishes two intentions:

~~~json
[
  { "op": "replace", "path": "/nickname", "value": null }
]
~~~

This operation sets the JSON value of the `nickname` member to null.

~~~json
[
  { "op": "remove", "path": "/nickname" }
]
~~~

This operation removes the `nickname` member from the JSON document. When mapped back to a Java entity, both cases may manifest as a null Java property; if you need to distinguish them, inspect both the JSON representation and the data types/persistence used by the application.

### 3.2. Paths are JSON Pointers

Paths use JSON Pointer syntax, starting with `/`. Examples:

- `/address/city` — nested property.
- `/items/0/quantity` — field inside the first element of an array.
- `/profile~1name` — member name containing `/`.
- `/labels/a~0b` — member name containing `~`.

In JSON Pointer, escape `~` as `~0` and `/` as `~1`. An invalid path, a nonexistent target for `remove`/`replace`, or an invalid operation must cause the patch to fail.

RFC 6902 requires operations to be applied in order and HTTP PATCH to be atomic: if any operation fails, the entire patch must not be considered successful. Verify final persisted data to ensure earlier operations were not partially committed.

## 4. JSON Merge Patch: Object Describing Desired State Changes

JSON Merge Patch per RFC 7396 uses an object shaped much like the JSON resource. Members present in the patch are added or replaced; omitted members are preserved; null values mean deleting the existing member.

Initial data:

~~~json
{
  "name": "An",
  "nickname": "Annie",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "tags": ["vip", "newsletter"]
}
~~~

Patch:

~~~json
{
  "name": "Binh",
  "nickname": null,
  "address": {
    "city": "Da Nang"
  },
  "tags": ["vip"]
}
~~~

Resulting JSON per RFC 7396:

~~~json
{
  "name": "Binh",
  "address": {
    "city": "Da Nang",
    "street": "Le Loi"
  },
  "tags": ["vip"]
}
~~~

Points to verify:

- `name` is replaced with the new value.
- `nickname: null` removes the member from the JSON document.
- `address.city` is updated; `address.street` is absent so it stays intact.
- The `tags` array is replaced as a whole, not merged element-by-element.
- Other members not in the patch remain unchanged.

Merge Patch cannot express "set member to JSON null" because null is reserved for removing a member. If the API must distinguish a present member with value null from a missing member, use JSON Patch `replace value: null`, a separate DTO/command, or another appropriate API contract.

If an entire Merge Patch document is a scalar, array, or null instead of an object, RFC 7396 defines the result as replacing the entire target with that value. For entity resources, you normally send an object patch.

When Merge Patch is mapped back to a Java entity, a removed member is typically represented as a null property or omitted in the serialized response depending on mapping and Jackson configuration. Do not judge persistence solely from the JSON response: verify values in the repository/database as well as the GET representation.

## 5. Testing Matrix for Omitted, Null, and Non-Writable Fields

Use a fixture with non-null values before each test so changes are observable.

| Scenario | PATCH application/json | JSON Patch | JSON Merge Patch |
|---|---|---|---|
| Field omitted from request | Preserved | No operation so preserved | Preserved |
| Field sent with new value | Binds new value | `replace` or `add` | Member replaced with new value |
| Field sent with null | Binds null if writable/nullable | `replace value: null` sets JSON null | Null deletes member per RFC 7396 |
| Field deleted | No separate standard remove syntax; use null if business logic accepts | `remove` | Send member with null |
| Nested object sending only one member | Spring Data REST merges object onto existing object; check specific associations | Only specified path changes | Recursively merges objects |
| Array sending only one element | May bind and replace entire collection depending on mapping; must test | Inserts/removes/replaces by index | Replaces entire array |

This table describes payload semantics. Final outcomes also depend on Java types, Jackson, persistent mapping, association handling, validation, and Spring Data REST version.

### 5.1. Testing ignored or read-only fields

Create a fixture with a read-only field, such as an audit code:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String auditCode;
~~~

You can use `@JsonIgnore` for fields not published or bound per the application's contract. Then attempt to update the field using all three PATCH formats and verify:

- The audit value remains unchanged.
- Clients cannot alter the read-only field through nested paths.
- Response status and error body match the field-protection policy of the running version.
- The repository/database does not persist values supplied by the client.

If a field does not appear in the representation, do not assume guessing its JSON property name will fail to write it. Test both direct paths and nested paths.

### 5.2. Protecting identifier and version

`@Id` and `@Version` properties are critical persistence metadata. Clients must not be allowed to arbitrarily modify them via patch payloads.

Example JSON Patch request to test:

~~~json
[
  { "op": "replace", "path": "/id", "value": 999 },
  { "op": "replace", "path": "/version", "value": 999 }
]
~~~

After the request, confirm:

- The entity identifier stays unchanged.
- No other entity is overwritten.
- Version remains managed by the persistence layer, ignoring arbitrary client values.
- Optimistic locking still detects concurrent updates.

This is an important security regression test. CVE-2026-47849 documented that JSON Patch could directly mutate identifiers and versions on affected releases; PUT and Merge Patch already had binding paths ignoring these properties, whereas JSON Patch lacked an equivalent guard. The advisory lists affected versions and fixes in the References section. Upgrade to a patched branch before relying on this test as a safeguard.

### 5.3. Protecting nested read-only paths

Do not check only the leaf field of a path. For models with nested containers marked read-only, test paths like `/settings/0/value` or `/metadata/key` to ensure intermediate segments also respect write access.

CVE-2026-41728 describes a case where JSON Patch bypassed write-access filters at intermediate path segments when processing multi-level JSON Pointers. Add regression tests for embedded objects, collections, and maps inside read-only containers; inspect both persisted data and responses. Upgrade to a patched Spring Data REST version per the advisory.

## 6. Sending Test Requests with curl

The commands below assume the item resource endpoint is `/customers/42`. Replace path, fields, and values with your application's fixture.

**Spring Data REST partial JSON: preserves omitted fields**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"name":"Binh"}'
~~~

Re-read the resource to confirm other fields remain intact.

**JSON Patch: change field and set null**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/patch+json" -H "Accept: application/hal+json" -d '[{"op":"replace","path":"/name","value":"Binh"},{"op":"replace","path":"/nickname","value":null}]'
~~~

Current Spring Data REST documentation lists `application/patch+json`. If the release in use directly registers the standard RFC 6902 media type, you can test `application/json-patch+json`; do not switch a JSON Patch body into a Merge Patch object.

**JSON Patch: remove member**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/patch+json" -H "Accept: application/hal+json" -d '[{"op":"remove","path":"/nickname"}]'
~~~

**JSON Merge Patch: omitted fields preserved, null removes member**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/merge-patch+json" -H "Accept: application/hal+json" -d '{"name":"Binh","nickname":null,"address":{"city":"Da Nang"}}'
~~~

After each request, send a fresh GET to the exact URI and inspect actual data. Do not draw conclusions solely from the status code because Spring Data REST may return a body or 204 depending on response configuration.

## 7. Integration Testing with MockMvc

Test through the HTTP layer so converters, Jackson, Spring Data REST, validation, repositories, and event handlers are all exercised. Each test should create an independent entity fixture and then check both the repository and the GET representation after PATCH.

Example test skeleton for Merge Patch:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerPatchIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    CustomerRepository repository;

    @Test
    void mergePatchKeepsOmittedFieldsAndClearsNullMember() throws Exception {
        Customer customer = repository.save(
            new Customer("An", "Annie", "Call after 18:00")
        );

        mockMvc.perform(patch("/customers/{id}", customer.getId())
                .contentType(MediaType.valueOf("application/merge-patch+json"))
                .accept(MediaType.parseMediaType("application/hal+json"))
                .content("""
                    {
                      "name": "Binh",
                      "nickname": null
                    }
                    """))
            .andExpect(status().is2xxSuccessful());

        Customer actual = repository.findById(customer.getId())
            .orElseThrow();

        assertThat(actual.getName()).isEqualTo("Binh");
        assertThat(actual.getNickname()).isNull();
        assertThat(actual.getNote()).isEqualTo("Call after 18:00");
    }
}
~~~

This is an illustrative skeleton; adjust constructors, repositories, media types, and statuses to match your application's version and configuration. If using database transactions in tests, ensure assertions read data processed by the request rather than stale objects in an old persistence context.

### Minimum test suite recommended

1. PATCH application/json sending only one field; other fields stay unchanged.
2. PATCH application/json sending null to a nullable field; field binds to null.
3. JSON Patch replacing a field; new value is persisted.
4. JSON Patch replacing value with null; distinguished from remove at the document layer.
5. JSON Patch removing an existing field; confirm member is deleted and entity state meets expectations.
6. JSON Patch replacing/removing a nonexistent path; patch fails with no partial changes.
7. JSON Patch test succeeds; patch continues applying subsequent operations.
8. JSON Patch test fails after a mutating operation; confirm the entire patch is not partially saved.
9. JSON Merge Patch omitting a field; field remains intact.
10. JSON Merge Patch sending null; member is removed per RFC 7396 and entity mapping is verified.
11. JSON Merge Patch updating a nested object; unsent sibling fields remain.
12. JSON Merge Patch sending an array; confirm the entire array is replaced.
13. All PATCH formats cannot write read-only, identifier, or version fields.
14. JSON Patch cannot modify nested paths passing through read-only containers.
15. A validated field such as `@NotNull` receives null; verify validation and persisted data match the contract.
16. A field omitted from response due to `@JsonInclude(NON_NULL)`; check repository to distinguish null from serialization hiding.

## 8. Common Pitfalls When Testing

| Symptom | Possible cause | Where to check |
|---|---|---|
| 415 Unsupported Media Type | Content-Type is not supported by the release's converters | Use media types documented for your exact version; check `application/patch+json` and `application/merge-patch+json` |
| 400 Bad Request | Malformed JSON, invalid operation/path, or binding failure | Read error response and check JSON Pointer |
| Omitted field gets cleared | Client is using PUT or custom mapper alters PATCH semantics | Check method, Content-Type, and binding handler |
| null does not delete member as expected | Using `application/json` or JSON Patch replace null | Distinguish Merge Patch null from JSON null |
| Array loses unsent elements | Merge Patch replaces the entire array | Send full array or use JSON Patch by index |
| Earlier patch operation mutated data despite later operation error | Patch handler/custom code lacks atomicity or test lacks transaction isolation | Check persistence after error and upgrade/fix handler |
| Read-only field changed via nested path | Filter not applied at intermediate path segment or vulnerable release | Check CVE-2026-41728 and add regression tests |
| Identifier/version changed via JSON Patch | Version affected by CVE-2026-47849 | Upgrade to patched release; re-test `@Id` and `@Version` |

One practical bug to note when upgrading: Spring Data REST issue #2596 reports that Merge Patch on array elements having linkable associations could retain old associations when updating existing elements starting in the 4.3 branch. If an aggregate has a collection of embeddables with link-based associations, add a dedicated test for associations within existing elements and verify against the exact release in use.

## 9. Workflow for Verifying a PATCH Change

1. Create a fixture where all fields under test initially have non-null values.
2. GET the resource and save the initial representation.
3. Send one PATCH request with the exact Content-Type; each test should verify only one semantic.
4. Record the status and error body.
5. Re-read via the repository to verify persisted values.
6. GET the resource again to verify representation, including omitted/null fields per Jackson.
7. For failed requests, confirm no partial changes occurred.
8. Repeat across nested, array, association, read-only, id, and version fields.
9. Run tests against the exact Spring Data REST version and dependency set being deployed.

## References

- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): supported HTTP methods, media types, and PATCH semantics.
- [Spring Data REST — DomainObjectReader API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/json/DomainObjectReader.html): applying an ObjectNode onto an existing domain object and distinguishing `read` from `readPut`.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902.html): six operations, JSON Pointer, execution order, and atomic error handling.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html): omitted members, null deletion semantics, object merging, and full array replacement.
- [CVE-2026-41728 — JSON Patch bypasses read-only property protection](https://spring.io/security/cve-2026-41728/): vulnerability in intermediate path segments and fixed versions.
- [CVE-2026-47849 — JSON Patch can mutate identifier and version](https://spring.io/security/cve-2026-47849/): protecting `@Id`, `@Version`, affected version ranges, and fixes.
- [Spring Data REST issue #2596](https://github.com/spring-projects/spring-data-rest/issues/2596): regression report on linkable associations inside arrays when using Merge Patch.
