# Practicing CRUD and Verifying Differences Between PUT, PATCH, and DELETE in Spring Data REST

## Objective

This practice uses a repository exported by Spring Data REST to create, read, replace, partially update, and delete resources. The goal is to observe the differences across all three layers:

1. **HTTP contract**: URI, method, request body, media type, headers, and status code.
2. **Data state**: which fields are changed, which fields are preserved, and which resources or links are removed.
3. **Correctness with multiple clients**: ETag, `If-Match`, retry handling, and integration testing.

Spring Data REST automatically creates collection resources and item resources from a Spring Data repository. Therefore, before sending a request, confirm the exact URI type you are operating on.

## 1. Preparing the Repository and Domain

The example uses Spring Data JPA. A minimal repository might look like:

~~~java
@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Illustrative entity:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    // Constructors, getters, and setters as needed by the project.
}
~~~

In this example:

- The collection resource is `/products`.
- The item resource for the product with ID `42` is `/products/42`.
- JPA's `@Version` allows Spring Data REST to use the version as an ETag to protect concurrent updates/deletes.
- `unique = true` only takes effect when the actual database schema has the corresponding unique constraint. In real projects, verify that migrations create the constraint.

If you do not need custom paths, Spring Data REST typically generates collection names by lowercasing and pluralizing the domain type name. Discover the HAL root and follow the returned links instead of hardcoding paths in the client.

## 2. Distinguishing Collection, Item, and Association Resources

| Resource | Example URI | Default Supported Methods | Meaning |
| --- | --- | --- | --- |
| Collection | `/products` | GET, POST | Read list, create a new entity |
| Item | `/products/42` | GET, PUT, PATCH, DELETE | Read, replace, partially update, delete entity |
| Association | `/products/42/category` | GET, PUT, POST, DELETE depending on relation | Read or modify links between entities |

Collection resources do not accept PUT, PATCH, or DELETE by default. Sending those methods to a collection typically returns `405 Method Not Allowed`. To modify an entity, use the item URI.

Spring Data REST only exposes methods that the repository actually declares and allows to be exported. For example, if `save(...)` is absent or marked `@RestResource(exported = false)`, the corresponding POST/PUT/PATCH endpoints will not be exposed. If `delete(...)` methods are hidden, DELETE will not be exposed either.

## 3. Basic CRUD over HTTP

Assume the application runs at `http://localhost:8080`. The commands below use `application/json` for request bodies and `application/hal+json` to request HAL representations in responses.

### 3.1. GET — Reading Collections and Items

Read a collection:

~~~bash
curl -i -H 'Accept: application/hal+json' 'http://localhost:8080/products?page=0&size=20'
~~~

If the repository supports paging, the response includes page metadata and navigation links. Read a single item:

~~~bash
curl -i -H 'Accept: application/hal+json' 'http://localhost:8080/products/42'
~~~

The item response contains the entity fields and `_links`, for example:

~~~json
{
  "sku": "KB-001",
  "name": "Keyboard",
  "price": 49.90,
  "_links": {
    "self": {
      "href": "http://localhost:8080/products/42"
    },
    "product": {
      "href": "http://localhost:8080/products/42"
    }
  }
}
~~~

The example above only illustrates the structure. Actual links and fields depend on the domain model, projections, configuration, and media type. Clients should follow the `self` link from the response when referencing the resource again.

### 3.2. POST — Creating a New Entity via Collection

POST to the collection URI:

~~~bash
curl -i -X POST 'http://localhost:8080/products' -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"sku":"KB-001","name":"Keyboard","price":49.90}'
~~~

POST creates a new entity from the body. A successful response is typically `201 Created` with a `Location` header pointing to the newly created item. When `Accept` is sent, Spring Data REST can include the representation by default; otherwise, the client reads the URI from `Location` and performs a GET on the item. `RepositoryRestConfiguration.setReturnBodyOnCreate(...)` can alter whether the body is returned.

POST is appropriate when the client submits data for the server-side collection/resource to create a resource and assign its URI. POST is not inherently idempotent: repeating the same request can create multiple entities if the application lacks duplicate prevention or an idempotency key.

### 3.3. PUT — Replacing Item State

PUT sends a representation describing the complete state the client wants to set for the item at a known URI:

~~~bash
curl -i -X PUT 'http://localhost:8080/products/42' -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"sku":"KB-001","name":"Keyboard Pro","price":59.90}'
~~~

In Spring Data REST, PUT on an item resource invokes the `save(...)` path and replaces the resource state according to PUT semantics. Therefore, clients should send the full set of writable fields defined by the resource contract. Do not use PUT as an implicit PATCH by sending only one field and assuming all remaining fields will always be preserved.

Do not send client-assigned IDs or versions in the body. The ID is determined by the URI; the version is protected by the version/ETag mechanism. Explicitly test how your application maps omitted properties, `null` values, nested objects, and read-only properties according to your actual entity/Jackson mapping.

With Spring Data REST's default configuration, when the request includes an `Accept` header, a PUT update typically returns `200 OK` with a body. Without `Accept`, the update response is typically `204 No Content`. `RepositoryRestConfiguration.setReturnBodyOnUpdate(...)` can override this behavior.

### 3.4. PATCH — Partially Updating an Item

PATCH sends a patch document describing the changes. Example using JSON Merge Patch:

~~~bash
curl -i -X PATCH 'http://localhost:8080/products/42' -H 'Content-Type: application/merge-patch+json' -H 'Accept: application/hal+json' -d '{"name":"Keyboard Pro"}'
~~~

With JSON Merge Patch according to RFC 7396:

- Properties omitted from the patch are left unchanged.
- Properties present with a non-null value are added or replaced.
- Properties with a `null` value mean removing that member from the JSON representation.
- Nested objects are merged recursively.
- Arrays are replaced as a single value, not merged element by element by index.

Example current resource:

~~~json
{
  "sku": "KB-001",
  "name": "Keyboard",
  "price": 49.90,
  "description": "Mechanical"
}
~~~

Patch:

~~~json
{
  "name": "Keyboard Pro",
  "description": null
}
~~~

After applying the merge patch, the name changes to `Keyboard Pro`, the `description` property is removed from the representation according to JSON Merge Patch semantics, and `sku` and `price` are preserved. When mapped onto a Java entity, the effect of removing a property also depends on field mapping, nullability, and how the domain model represents that state; test with the real entity.

Spring Data REST documents PATCH media types including `application/hal+json`, `application/json`, `application/patch+json`, and `application/merge-patch+json`. Choose the exact format understood by both client and server. Do not infer semantics solely from the HTTP PATCH method: RFC 5789 defines PATCH as accepting a patch document whose format is identified by its media type; each format has its own rules.

PATCH may be non-idempotent depending on the patch document type. If a patch is based on a previously read version of the data, send `If-Match` so the server rejects patches against a modified version.

### 3.5. DELETE — Deleting an Item Resource

Delete an item:

~~~bash
curl -i -X DELETE 'http://localhost:8080/products/42'
~~~

DELETE on an item resource invokes one of the repository methods `delete(T)`, `delete(ID)`, or `delete(Iterable)`, depending on which is available. Under the default configuration, if `Accept` is omitted, a successful response is typically `204 No Content`; when `Accept` is present, Spring Data REST may return a body with `200 OK`. `RepositoryRestConfiguration.setReturnBodyOnDelete(...)` can change this behavior.

Item DELETE removes the entity identified by the URI. Whether related entities are also deleted depends on JPA mappings, cascades, orphan removal, and database constraints. Do not assume deleting an item automatically deletes all related entities.

HTTP defines DELETE as idempotent in terms of its intended effect: repeating the same request does not leave the resource in a different state. The response to the second call may still be `404 Not Found` because the resource was already deleted on the first call; this does not invalidate idempotency.

## 4. How Do PUT, PATCH, and DELETE Differ?

| Criterion | PUT | PATCH | DELETE |
| --- | --- | --- | --- |
| Purpose | Replace item state | Apply partial changes | Delete item |
| Typical URI | Item URI | Item URI | Item URI |
| Request body | Representation of the target state | Patch document matching media type | Typically no body needed |
| Omitted fields | Do not rely on preservation semantics; send full writable state | Typically unchanged with JSON Merge Patch | Not applicable |
| HTTP idempotency | Yes | Not guaranteed by the method | Yes |
| Spring Data REST invokes | `save(...)` | `save(...)` | `delete(...)` |
| Concurrent update protection | Can use `If-Match` | Should use `If-Match` when patching from a read version | Can use `If-Match` to avoid deleting a newer version |

Key takeaways:

- PUT expresses the intent to set resource state to the submitted representation.
- PATCH expresses the intent to apply a set of changes; the media type determines how the patch is interpreted.
- DELETE expresses the intent that the resource no longer exists at that URI.
- Collection POST creates a new resource; it does not replace PUT/PATCH on an item URI.
- `Content-Type` describes the format of the request body sent. `Accept` describes the response format the client wants to receive. These two headers serve different roles.

Under RFC 9110, PUT and DELETE are idempotent. PATCH is not guaranteed to be idempotent; a specific patch may be designed to be idempotent, but the client must understand the patch document semantics before retrying automatically.

## 5. DELETE on an Item vs. DELETE on an Association

Spring Data REST generates association resources for entity relationships. For example:

~~~text
/products/42/category
~~~

Operations on an association have their own semantics:

- GET reads the link.
- PUT binds the target resource's URI to the association.
- POST is only for collection associations and adds an element to the collection.
- DELETE unbinds the link from the association.

Example assigning a category to a product:

~~~bash
curl -i -X PUT 'http://localhost:8080/products/42/category' -H 'Content-Type: text/uri-list' --data 'http://localhost:8080/categories/5'
~~~

Example removing the link:

~~~bash
curl -i -X DELETE 'http://localhost:8080/products/42/category'
~~~

Association requests use `text/uri-list` containing the URI of the related resource, not an arbitrary JSON object. For a to-one association, PUT accepts only one URI; sending multiple URIs is rejected. Association DELETE unbinds the relationship; it does not delete the category or product. For a collection association, POST adds one element; PUT can replace the set of linked URIs according to association resource semantics.

Follow the association link returned by HAL instead of constructing property names manually if the repository customizes the relation using `@RestResource`.

## 6. Status Codes and Reading Responses

Common success status codes:

| Request | Typical Default Result |
| --- | --- |
| GET collection/item | `200 OK` |
| POST collection to create | `201 Created` and `Location` |
| PUT item to update | `200 OK` if response body is enabled; otherwise typically `204 No Content` |
| PATCH item to update | `200 OK` if response body is enabled; otherwise typically `204 No Content` |
| DELETE item | `200 OK` if response body is enabled; otherwise typically `204 No Content` |

For PUT/PATCH/DELETE, the presence of `Accept` determines whether a body is returned when `returnBodyOnUpdate` or `returnBodyOnDelete` is null. If the project explicitly configures `setReturnBodyOnUpdate`, `setReturnBodyOnDelete`, or their corresponding options, the configured value takes precedence.

Common errors:

| Status | Causes to Check |
| --- | --- |
| `400 Bad Request` | Malformed JSON, invalid data types, validation failure, or multiple URIs sent to a to-one association |
| `401 Unauthorized` / `403 Forbidden` | Unauthenticated or lacking permission for the method/resource |
| `404 Not Found` | Item URI does not exist, or the link/URI used by the client is stale |
| `405 Method Not Allowed` | Using PUT/PATCH/DELETE on a collection, or repository/method is not exported |
| `409 Conflict` | Unique/foreign-key constraint violation or optimistic locking failure at the repository layer |
| `412 Precondition Failed` | Current ETag does not match the `If-Match` header |
| `415 Unsupported Media Type` | `Content-Type` is not accepted by the endpoint |

These are common diagnostic guidelines. Security configuration, validation, custom exception handlers, and the Spring Data REST version can affect the final response.

### 6.1. Distinguishing 409 and 412

If an entity has a `@Version` field, Spring Data REST can return an ETag corresponding to the version. GET the item to retrieve the ETag:

~~~http
GET /products/42
ETag: "7"
~~~

Send PUT, PATCH, or DELETE with the ETag read earlier:

~~~bash
curl -i -X PATCH 'http://localhost:8080/products/42' -H 'If-Match: "7"' -H 'Content-Type: application/merge-patch+json' -H 'Accept: application/hal+json' -d '{"name":"New name"}'
~~~

The operation proceeds only if the current ETag matches `If-Match`. If another client has updated the resource, the request with the stale ETag receives `412 Precondition Failed`. This is an HTTP precondition check.

If two transactions edit the data simultaneously and the persistence layer detects a version mismatch on save, the repository may throw `OptimisticLockingFailureException`, which is commonly handled as `409 Conflict`. When investigating, inspect the actual exception and request headers; do not conflate the two error paths.

## 7. Testing CRUD with MockMvc

Use integration tests to verify both the HTTP contract and the persisted data state after each request. The example below assumes:

- `ProductRepository` is exported by Spring Data REST at `/products`.
- The test database has the corresponding schema and constraints.
- `Product` has the properties `sku`, `name`, `price`, `version`.
- The default configuration returns a body when the request includes `Accept`.

Test skeleton:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductCrudRestTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProductRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    @Test
    void postCreatesResourceAndReturnsLocation() throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept("application/hal+json")
                .content("""
                    {"sku":"SKU-001","name":"Keyboard","price":49.90}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"));

        assertThat(repository.findAll()).hasSize(1);
    }

    @Test
    void putReplacesTheItemState() throws Exception {
        Product product = new Product();
        product.setSku("SKU-001");
        product.setName("Keyboard");
        product.setPrice(new BigDecimal("49.90"));
        Product saved = repository.saveAndFlush(product);

        mvc.perform(put("/products/{id}", saved.getId())
                .contentType(MediaType.APPLICATION_JSON)
                .accept("application/hal+json")
                .content("""
                    {"sku":"SKU-001","name":"Keyboard Pro","price":59.90}
                    """))
            .andExpect(status().isOk());

        Product reloaded = repository.findById(saved.getId()).orElseThrow();
        assertThat(reloaded.getName()).isEqualTo("Keyboard Pro");
        assertThat(reloaded.getPrice()).isEqualByComparingTo("59.90");
    }

    @Test
    void patchChangesOnlyTheNamedProperty() throws Exception {
        Product product = new Product();
        product.setSku("SKU-002");
        product.setName("Mouse");
        product.setPrice(new BigDecimal("20.00"));
        Product saved = repository.saveAndFlush(product);

        mvc.perform(patch("/products/{id}", saved.getId())
                .contentType("application/merge-patch+json")
                .accept("application/hal+json")
                .content("""
                    {"name":"Wireless Mouse"}
                    """))
            .andExpect(status().isOk());

        Product reloaded = repository.findById(saved.getId()).orElseThrow();
        assertThat(reloaded.getName()).isEqualTo("Wireless Mouse");
        assertThat(reloaded.getSku()).isEqualTo("SKU-002");
        assertThat(reloaded.getPrice()).isEqualByComparingTo("20.00");
    }

    @Test
    void deleteRemovesTheItem() throws Exception {
        Product product = new Product();
        product.setSku("SKU-003");
        product.setName("Monitor");
        product.setPrice(new BigDecimal("150.00"));
        Product saved = repository.saveAndFlush(product);

        mvc.perform(delete("/products/{id}", saved.getId()))
            .andExpect(status().isNoContent());

        assertThat(repository.existsById(saved.getId())).isFalse();
    }
}
~~~

These tests are templates to adapt to your project's constructors, getters/setters, database, and response configuration. If `Accept` or `RepositoryRestConfiguration` is changed, adjust status/body expectations accordingly. PATCH tests must verify both that modified fields changed and that fields absent from the patch remain unchanged.

### 7.1. Testing ETag and Stale Updates

Create an item with `@Version`, GET the item to retrieve its ETag, then update via the repository to increment the version. Send a PATCH with the stale ETag:

~~~java
MvcResult firstRead = mvc.perform(get("/products/{id}", id)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andReturn();

String staleEtag = firstRead.getResponse().getHeader("ETag");
assertThat(staleEtag).isNotBlank();

Product latest = repository.findById(id).orElseThrow();
latest.setName("Changed by another client");
repository.saveAndFlush(latest);

mvc.perform(patch("/products/{id}", id)
        .header("If-Match", staleEtag)
        .contentType("application/merge-patch+json")
        .accept("application/hal+json")
        .content("{\"name\":\"Stale client edit\"}"))
    .andExpect(status().isPreconditionFailed());
~~~

This test verifies HTTP preconditions. Use a real database or compatible test database to verify that `@Version` is handled properly by the persistence provider. Do not just assert status codes; confirm that the latest value in the database remains intact after the rejected request.

### 7.2. Testing Methods and Associations

Add the following cases if your API uses them:

- PUT/PATCH/DELETE on the collection URI returns `405`.
- If a repository method is marked `@RestResource(exported = false)`, the corresponding endpoint is not exported.
- Association PUT with `text/uri-list` binds the correct resource.
- Collection association POST adds a link.
- Association DELETE unbinds the link without deleting the target entity.
- Item DELETE removes the entity via the repository and verifies foreign key/cascade behavior.
- Invalid payloads or unsupported media types return appropriate errors.

MockMvc runs the full Spring MVC pipeline using mock requests/responses, without starting a real HTTP server. If you need to verify proxies, containers, serialization, or actual network configuration, add end-to-end tests against a running server.

Run tests using your project's build tool, such as `./mvnw test` or `mvn test`.

## 8. Troubleshooting

**PUT wipes out values that the client did not send**

- PUT means replacing item state. Clients must send the complete writable state per the contract.
- Check Jackson mapping, constructors, setters, read-only properties, and how Spring Data REST applies PUT to an existing entity.
- Write tests for omitted fields, null fields, and nested objects; do not assume behavior from another entity.

**PATCH modifies more fields than expected**

- Check `Content-Type`; the patch document must be interpreted according to the right format.
- With JSON Merge Patch, `null` removes members and arrays are replaced entirely.
- Check nested objects, associations, and custom deserializers.
- If a client needs to update an array element by index or execute a sequence of add/remove/test operations, use a patch format that supports those operations and check your Spring Data REST version.

**PATCH returns 415**

- Check supported server media types and the `Content-Type` value.
- Do not use `Accept` in place of `Content-Type`; `Accept` only describes the desired response format.
- Verify the request targets the proper item URI and Spring Data REST endpoint.

**PUT/PATCH/DELETE returns 405**

- Confirm you are calling the item URI, not the collection URI.
- Verify the repository has the corresponding `save(...)` or `delete(...)` method.
- Check `@RestResource(exported = false)`, `@RepositoryRestResource`, and supported HTTP method configurations.

**Item DELETE does not delete related entities**

- Determine whether the request hit the item URI or the association URI.
- Association DELETE only unbinds the link.
- Check JPA cascade/orphan removal and foreign key constraints if related entity deletion is expected.
- Do not enable cascade remove solely to make a single test pass; define the business lifecycle first.

**Update succeeds but returns no response body**

- Check the `Accept` header.
- Check `RepositoryRestConfiguration.setReturnBodyOnUpdate(...)` and `setReturnBodyOnDelete(...)`.
- `204 No Content` is a successful response with no body; clients should not attempt to parse JSON when this status is returned.

**Receiving 409 or 412 on update**

- `409` typically indicates a database constraint violation or repository optimistic locking failure.
- `412` typically occurs because the current ETag does not match `If-Match`.
- Re-GET the resource, retrieve the new ETag, compare changes, and resend only after resolving the conflict.

**Client retries create duplicate records**

- Collection POST is not inherently idempotent.
- After a timeout, check the outcome using a business key or an application idempotency key before resending.
- For PUT/DELETE, HTTP defines idempotency in terms of intended effect, though the response to a repeated request may differ.
- Do not automatically retry PATCH unless you know the patch document is idempotent and version-conditioned.

**Constraint errors surface as 500 or unstable responses**

- Verify that the database constraint actually exists in the running schema.
- Inspect the exception class/cause chain and custom exception handlers.
- Check when the transaction flushes; constraint errors may surface only during flush/commit.
- Never return SQL or stack traces to clients.

## 9. Security Notes for PUT/PATCH

Spring Data REST exposes CRUD directly over the domain model, so exported methods must be paired with authorization and restrictions on writable properties. Enforce permissions on both item resources and association resources. Do not treat hiding a button in the UI as access control.

Fields such as ID, version, owner, role, approval status, and audit metadata must not be arbitrarily writable by clients. Use appropriate mappings/authorization, write tests for requests attempting to send sensitive fields, and verify your Spring Data REST version is patched.

Spring security advisories in 2026 are especially relevant to JSON Patch and versioning:

- CVE-2026-41728 and CVE-2026-41729 concern `application/json-patch+json` handling, including bypassing read-only restrictions on nested paths and SpEL injection via Map keys. Published OSS fixes include Spring Data REST 5.0.6, 4.5.12, 4.4.15, 4.3.17, and 3.7.20.
- CVE-2026-47849 concerns the ability to modify `@Id`/`@Version` via JSON Patch; CVE-2026-47850 concerns immutable aggregate versioning via PUT. Corresponding published fixes include 5.1.1, 5.0.7, 4.5.13, 4.4.16, and 3.7.21.

Cross-check advisories against the actual Spring Data REST branch in your dependency tree and upgrade to the corresponding patched version. If JSON Patch is not needed, do not enable or accept that format indiscriminately. For any PATCH format, test that clients cannot modify IDs, versions, or server-only properties. For immutable aggregates, test PUT and optimistic locking separately.

## 10. Practice Completion Checklist

- [ ] GET collection and item return HAL representations with valid links.
- [ ] Collection POST creates exactly one entity, returning `201 Created` and `Location`.
- [ ] Item PUT replaces state according to a complete payload.
- [ ] Item PATCH applies only changes per the media type; unpatched fields remain intact.
- [ ] Merge Patch PATCH handles null, nested objects, and arrays according to the chosen rules.
- [ ] Item DELETE deletes the right entity and is not confused with association DELETE.
- [ ] Association PUT/POST/DELETE use `text/uri-list` and have proper semantics.
- [ ] Verified status/body behavior with and without `Accept`.
- [ ] Verified `If-Match` with a stale ETag returns `412`.
- [ ] Verified hidden methods return `405` and invalid payloads are handled appropriately.
- [ ] Verified authorization and that ID/version/owner/role fields cannot be modified by clients.
- [ ] Verified the Spring Data REST dependency includes fixes for advisories applicable to the active branch.

## 11. Official Documentation

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association resources; HTTP methods, media types, and default status codes.
- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): `@Version`, ETag, `If-Match`, `If-None-Match`, 412, and 304.
- [Spring Data REST — Getting Started](https://spring.io/guides/gs/accessing-data-rest): example of creating entities via POST, `Location` header, and HAL representation.
- [Spring Data REST API — DomainObjectReader](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/json/DomainObjectReader.html): how the framework applies JSON documents onto domain objects and handles PUT.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): PUT, POST, and DELETE semantics and method idempotency.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html): patch documents, media types, atomicity, and concurrency conditions.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html): semantics of omitted properties, null, nested objects, and arrays.
- [Spring Advisory CVE-2026-41728](https://spring.io/security/cve-2026-41728/): JSON Patch bypass of read-only property protection.
- [Spring Advisory CVE-2026-41729](https://spring.io/security/cve-2026-41729/): JSON Patch SpEL injection via Map key.
- [Spring Advisory CVE-2026-47849](https://spring.io/security/cve-2026-47849/): JSON Patch modifying ID and version.
- [Spring Advisory CVE-2026-47850](https://spring.io/security/cve-2026-47850/): PUT with immutable aggregates and version.

Cross-check documentation with the Spring Data REST version managed by the Spring Boot BOM in your project. When outcomes depend on `Accept`, media types, entity mappings, or exception handlers, maintain an integration test representing the contract clients actually use.