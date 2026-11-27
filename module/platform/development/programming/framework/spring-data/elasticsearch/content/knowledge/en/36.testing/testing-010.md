# Testing Nested, Geo, and Concurrency on Demand

Spring Data Elasticsearch supports specialized data types and queries beyond ordinary scalar fields. An entity may contain a list of objects requiring **nested** mapping, geographic coordinates requiring **geo_point** mapping, or data modified by concurrent requests requiring conflict control.

These features cannot be verified thoroughly by unit tests that mock repositories. Nested queries depend on actual mappings; geo queries depend on field types and coordinate order; optimistic concurrency depends on version metadata managed by Elasticsearch. Integration tests against a compatible Elasticsearch instance verify that the application creates mappings, sends queries, and handles conflicts as expected.

This lesson explains how to design tests for three scenario groups: nested objects and nested queries, geographic data and distance queries, and concurrent updates. Each part moves from mapping and sample data to queries, assertions, and common pitfalls.

## 1. Choosing the Right Test Level

These three feature areas can be tested at multiple levels:

| Test level | Nested | Geo | Concurrency |
|---|---|---|---|
| Unit test | Verify service builds query and processes results | Verify validation of coordinates, radius, and criteria | Verify exception handling and retry policy |
| Context/repository test | Verify repository and fragments are wired | Verify converters and mapping beans are configured | Verify version metadata is mapped |
| Elasticsearch integration test | Verify real nested mapping and nested queries | Verify `geo_point`, distance, and bounding box | Verify version conflicts, atomic updates, and retries |
| Load/concurrency test | Measure nested query cost on production-like data | Measure radius queries and point density | Measure write contention, throughput, and conflict rate |

Unit tests remain valuable, yet they never replace integration tests for Elasticsearch semantics. Constructing a valid Java `Query` object does not prove the index has a matching mapping.

There is no need to run heavy load tests for every small change. Start with deterministic behavioral integration tests, then add benchmarks or concurrency tests when workload and contention warrant them.

## 2. Setting Up Elasticsearch for Integration Tests

Testcontainers can provide a dedicated Elasticsearch node for tests. Pin an image version compatible with your project's Spring Data Elasticsearch and Elasticsearch Java API Client. Never use the `latest` tag because behavior and compatibility can change.

Typical test structure:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }

    @Autowired
    ElasticsearchOperations operations;
}
~~~

This is an illustrative structure. Pick an image tag matching your project's versions and configure authentication/TLS according to how the container starts. If Spring Boot uses a different property prefix or endpoint format in your release train, adjust `DynamicPropertySource` accordingly.

Tests must create the index and mapping before writing data. Use a dedicated index or clean up test indices safely so tests do not depend on execution order.

Example index preparation:

~~~java
@BeforeEach
void prepareIndex() {
    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }

    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping(Product.class)
    );
}
~~~

Method names and mapping creation can differ across Spring Data Elasticsearch versions. If the application manages indices using templates or provisioning scripts, integration tests should apply that same mapping resource instead of generating a mapping different from production.

After saving data, refresh the index before search assertions:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Never use fixed `Thread.sleep` to wait for search visibility. Explicit refreshes or deterministic synchronization conditions make tests far more stable.

## 3. Mapping an Object Array as Nested

Suppose a product has multiple variants, each with code, color, and size:

~~~json
{
  "id": "P-100",
  "name": "T-Shirt",
  "variants": [
    {
      "variantId": "V-1",
      "color": "black",
      "size": "S"
    },
    {
      "variantId": "V-2",
      "color": "white",
      "size": "L"
    }
  ]
}
~~~

If `variants` is mapped as a regular `object` array, Elasticsearch flattens fields across array elements. A query can match `color` from the first element and `size` from the second, returning a match even though no single variant satisfies both conditions.

To preserve per-element relationships across fields, the mapping must be `nested`.

### Entity in Spring Data Elasticsearch

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;

    // constructors, getters and setters
}

public class Variant {

    @Field(type = FieldType.Keyword)
    private String variantId;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    // getters and setters
}
~~~

`FieldType.Nested` instructs Elasticsearch to index child objects using nested semantics. If the mapping was previously created as `object`, changing the Java annotation will not convert the existing mapping automatically. You must create a new index or run an appropriate migration.

### Verifying the Actual Mapping

After creating the index, retrieve the mapping from Elasticsearch and confirm `variants` has type `nested`. You can use the REST API:

~~~http
GET /products/_mapping
~~~

The expected mapping looks like:

~~~json
{
  "properties": {
    "variants": {
      "type": "nested",
      "properties": {
        "variantId": { "type": "keyword" },
        "color": { "type": "keyword" },
        "size": { "type": "keyword" }
      }
    }
  }
}
~~~

Integration tests should inspect the real mapping or at least run nested queries on an index built from the application's mapping. Checking annotations on the Java class alone does not prove the live index has the right mapping.

## 4. Seeding Test Data That Catches Nested Bugs

Test data must include cases where `object` mapping and `nested` mapping yield different results. If every attribute sits on one element or only one element exists, the test will fail to catch a broken mapping.

Seed two distinct variants:

~~~java
Product product = new Product();
product.setId("P-100");
product.setName("T-Shirt");

Variant first = new Variant();
first.setVariantId("V-1");
first.setColor("black");
first.setSize("S");

Variant second = new Variant();
second.setVariantId("V-2");
second.setColor("white");
second.setSize("L");

product.setVariants(List.of(first, second));

operations.save(product);
operations.indexOps(Product.class).refresh();
~~~

With this data:

- Querying `color = black` and `size = S` in the same variant must find `P-100`.
- Querying `color = black` and `size = L` in the same variant must NOT find `P-100`.
- Querying `color = black` alone should find `P-100`.

The second case is essential for catching cross-object matching. If that query returns `P-100`, either the mapping or the query lacks proper nested semantics.

## 5. Nested Queries Must Group Conditions Within the Same Nested Object

Proper query for `color = black` and `size = S`:

~~~http
GET /products/_search
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "term": {
                "variants.size": "S"
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Both filters reside inside the same `nested` query and must therefore be satisfied by the same nested object.

A business-logic bug is placing two separate `nested` queries inside a `bool` `must` clause. Each `nested` query can then match a different child, failing to enforce that `color` and `size` belong to the same variant.

### Testing the Matching Case

With the seeded data above, querying `color = black` and `size = S` must return `P-100`.

### Testing the Cross-Object Non-Matching Case

Querying `color = black` and `size = L` must return nothing (no `P-100`). Both values exist on the same parent document, yet on different variants.

A helpful test:

~~~java
@Test
void nestedConditionsMustMatchSameVariant() {
    SearchHits<Product> hits =
        operations.search(
            queryForColorAndSize("black", "L"),
            Product.class
        );

    assertThat(hits.getSearchHits())
        .isEmpty();
}
~~~

`queryForColorAndSize` represents the `NativeQuery` or query builder used by the project. The core requirement is placing both conditions inside a single `nested` clause.

## 6. Building Nested Queries with NativeQuery

With modern Spring Data Elasticsearch, `NativeQuery` can use the Elasticsearch Java API Client's `Query` builder.

Illustrative example:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.nested(n -> n
        .path("variants")
        .query(nq -> nq.bool(b -> b
            .filter(f -> f.term(t -> t
                .field("variants.color")
                .value("black")
            ))
            .filter(f -> f.term(t -> t
                .field("variants.size")
                .value("S")
            ))
        ))
    ))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Builder overloads may vary by Elasticsearch Java API Client version. Use the API from your installed dependencies. In integration tests, confirm the resulting JSON query contains a single `nested` clause with path `variants` and both filters inside the same child scope.

When using reactive operations, queries follow the same semantics while returning a `Publisher` such as `Flux<SearchHit<Product>>`. Use `StepVerifier` to verify results without calling `block` inside reactive tests.

## 7. Testing Inner Hits When Identifying Which Child Matched

A nested query can request `inner_hits` to return the matching nested objects. This is useful when the UI needs to show exactly which variant matched rather than only knowing the parent product matched.

A test can verify:

- Parent `P-100` is returned.
- Inner hits contain only variant `V-1` when querying `color = black`.
- Variant `V-2` does not appear in that query's inner hits.

Configuring `inner_hits` in `NativeQuery` depends on the Java API Client version. If the application does not use inner hits, do not add assertions for this metadata.

Do not confuse inner hits with the full `variants` list on the entity. The entity content may still include all variants; inner hits represent metadata about the nested children that matched the query.

## 8. Testing Nested Updates When Required by Business Logic

If a service updates a specific variant, tests should verify only the targeted child changed. Elasticsearch updates still rewrite the parent document; nested children do not have independent document IDs.

For example, given `V-1` and `V-2`, after updating stock or status on `V-2`:

- `V-2` has the new value.
- `V-1` remains unchanged.
- Other parent fields remain unchanged.
- A nested search query for the new value returns the parent.

For scripted updates, also test a non-existent variant ID. The application should decide explicitly whether that is a no-op or a business error.

An integration test can read the parent back by ID after an update and inspect every element. If an update succeeds yet search does not reflect the change yet, distinguish refresh visibility from whether the update took effect on GET by ID.

## 9. Mapping geo_point in Spring Data Elasticsearch

Elasticsearch supports the `geo_point` field type for geographic locations. A geo point can be represented as an object with `lat`/`lon`, an array ordered `[lon, lat]`, or a formatted string.

Example entity using Spring Data's `GeoPoint`:

~~~java
@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @GeoPointField
    private GeoPoint location;

    // getters and setters
}
~~~

In versions providing `@GeoPointField`, it marks the property as `geo_point`. `FieldType.GeoPoint` may also be supported depending on the release train's mapping support. Check the actual packages and annotations in your project's dependencies.

Example creating a point:

~~~java
Store store = new Store();
store.setId("S-100");
store.setName("Central Store");
store.setLocation(
    new GeoPoint(10.7769, 106.7009)
);
~~~

With Spring Data's `GeoPoint`, the constructor typically takes `latitude` followed by `longitude`. This is easy to mix up because JSON `geo_point` arrays order `longitude` before `latitude`.

### Checking the Mapping

Call the mapping API and verify `location` has type `geo_point`:

~~~http
GET /stores/_mapping
~~~

Do not check only that the Java field has type `GeoPoint`. If an existing index mapped `location` as an ordinary `object`, geo queries can fail or misbehave.

## 10. Coordinate Order and Geographic Data

Geo points commonly appear in three forms:

Object:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Array:

~~~json
[106.7009, 10.7769]
~~~

String:

~~~text
10.7769,106.7009
~~~

Distinguish the ordering:

- Object: `lat` and `lon` by field name.
- Array: `longitude` first, `latitude` second.
- Spring Data Java `GeoPoint`: typically `latitude` first, `longitude` second.

Tests should use clearly asymmetric coordinates so swapped lat/lon values are immediately caught. Picking points whose two values are close or both valid across ranges can hide coordinate-swap bugs.

Validate data before writing:

- Latitude within `[-90, 90]`.
- Longitude within `[-180, 180]`.
- Non-null values if location is mandatory in the domain.
- Defined behavior for missing or invalid locations.
- Never treat an un-geocoded street address string as coordinates.

## 11. Testing Geo Distance Queries

A geo distance query finds documents within a radius from a center point.

Example finding stores within 5 km:

~~~http
GET /stores/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

An integration test should seed:

- A store very close to the center.
- A store near the radius boundary.
- A store clearly outside the radius.
- A document without `location` if allowed by mapping/use case.

Tests confirm nearby points are returned and outside points are excluded. For points near the boundary, choose coordinates and a radius with well-separated distances so rounding tolerances do not make tests flaky.

### Using NativeQuery

`NativeQuery` can build geo distance queries via the Java API Client builder:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.geoDistance(g -> g
        .field("location")
        .distance("5km")
        .location(location -> location
            .lat(10.7769)
            .lon(106.7009)
        )
    ))
    .build();

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

`GeoLocation` type names and builder overloads depend on client version. If code fails to compile, consult the dependency API while preserving the `geo_distance` DSL semantics.

### Checking Distance Units

Elasticsearch supports distance units such as `m`, `km`, `mi`, and others documented for your version. Specify units explicitly in queries—such as `5km`—rather than relying on defaults.

Tests should verify that a smaller radius excludes a distant point while a larger radius includes it. Never conclude units are correct from a single query with one hit.

## 12. Testing Geo Bounding Boxes

A bounding box finds points inside a geographic rectangle defined by top-left and bottom-right corners.

Example:

~~~http
GET /stores/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.80,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.75
        }
      }
    }
  }
}
~~~

Tests should seed points:

- Inside the bounding box.
- Outside to the north.
- Outside to the south.
- Outside to the east or west.

Verify boundary coordinates according to Elasticsearch semantics and test data. Regions crossing the international date line may require special representations; do not apply simple rectangle assumptions to every region.

A geo bounding box is a rectangular filter, not a circular radius. If the requirement is "within 5 km," use `geo_distance`.

## 13. Testing Geo Sorting and Distance

If results must be sorted by distance from a user, search requests can use geo distance sorting.

A test should verify:

- Closer points appear before farther ones when sorting ascending.
- Farther points appear later.
- The center coordinates are passed accurately.
- Documents lacking `location` obey the configured `missing` sort value.
- Results retain sort values if the API supports cursor pagination.

Do not infer nearest-first ordering from document insertion order. Default search results never guarantee business ordering without an explicit sort.

If distances must be displayed, read the sort value or compute it in the application. Do not treat search `_score` as distance unless the query explicitly defines scoring that way.

## 14. Testing Concurrency: Lost Updates and Version Conflicts

Two requests may read the same document, compute changes from the same stale state, and write back. Without concurrency control, one update can silently overwrite the other.

Example:

~~~text
Initial stock = 10

Request A reads 10
Request B reads 10

Request A writes 8
Request B writes 7

Final stock = 7
~~~

If business logic expects two orders deducting 2 and 3, the right result is 5. Uncoordinated read-modify-write can lose an update.

Elasticsearch supports optimistic concurrency control based on version metadata. Common mechanisms:

- Version property supported by Spring Data via `@Version`.
- Sequence number and primary term in Elasticsearch.
- Update scripts computing changes directly against the current document.
- `retry_on_conflict` for update scripts where appropriate.

Pick the mechanism matching the domain requirement. Never apply a blanket retry to hide every conflict.

## 15. Testing @Version in Spring Data

Spring Data Elasticsearch supports declaring a version property on entities with `@Version` in compatible releases.

Example:

~~~java
@Document(indexName = "inventory")
public class Inventory {

    @Id
    private String id;

    private Integer stock;

    @Version
    private Long version;

    // getters and setters
}
~~~

Version metadata lets Spring Data detect when an entity was read from a stale version during writes under the optimistic locking contract.

Test scenario:

1. Save `Inventory` initially.
2. Read the same document into two objects A and B.
3. Update and save A successfully.
4. Attempt to save B with the stale version.
5. Verify B's write is rejected due to a version conflict.
6. Read the document back and confirm A's value remains intact.

Structural example:

~~~java
@Test
void rejectsSavingStaleVersion() {
    Inventory original = new Inventory();
    original.setId("SKU-1");
    original.setStock(10);

    Inventory saved = repository.save(original);

    Inventory firstRead =
        repository.findById(saved.getId()).orElseThrow();

    Inventory staleRead =
        repository.findById(saved.getId()).orElseThrow();

    firstRead.setStock(8);
    repository.save(firstRead);

    staleRead.setStock(7);

    assertThatThrownBy(() -> repository.save(staleRead))
        .isInstanceOf(OptimisticLockingFailureException.class);
}
~~~

Actual exception wrapping may vary across Spring Data or client versions. Integration tests should assert the concrete exception type received by the application rather than catching generic `RuntimeException`.

`@Version` support and version mapping vary across release trains. Check the documentation for your dependencies before treating this test as a fixed contract.

### What This Test Proves

The test proves a stale-version entity cannot silently overwrite a newer version when optimistic locking is configured properly.

It does not prove business retries are safe. On conflict, the service must decide whether to re-read, recompute, fail, or route the operation elsewhere.

## 16. Testing Sequence Numbers and Primary Terms

Elasticsearch provides `seq_no` and `primary_term` for request-level optimistic concurrency control. On read, the client receives this metadata. On write, the client can require the document to still be at the exact `seq_no` and `primary_term`.

Example using the Elasticsearch Java API Client:

~~~java
GetResponse<Inventory> firstRead =
    client.get(g -> g
        .index("inventory")
        .id("SKU-1"),
        Inventory.class
    );

long seqNo = firstRead.seqNo();
long primaryTerm = firstRead.primaryTerm();

client.update(u -> u
    .index("inventory")
    .id("SKU-1")
    .ifSeqNo(seqNo)
    .ifPrimaryTerm(primaryTerm)
    .doc(Map.of("stock", 8)),
    Inventory.class
);
~~~

Once a write succeeds, the document's sequence number increments. A second request carrying the old `seq_no` and `primary_term` receives a version conflict.

### Testing Stale Writes

1. Read the document once, capturing `seq_no` and `primary_term`.
2. Send the first update with those two values.
3. Send a second update with the same old metadata.
4. Verify the second request receives a conflict.
5. Read the document back and confirm the first update was preserved.

`if_seq_no`/`if_primary_term` protects write decisions based on a read snapshot. It does not automatically merge two business changes.

### Distinguishing from retry_on_conflict

- `if_seq_no` and `if_primary_term` state: write only if the document is still at the exact version read.
- `retry_on_conflict` tells Elasticsearch to retry an update script when an internal conflict happens during the update.

When the caller wants to write relative to the latest state, an additive/subtractive update script can fit. When the caller computed a value from an earlier snapshot, optimistic concurrency detects stale snapshots.

## 17. Testing Atomic Update Scripts

For incrementing or decrementing counters, performing the arithmetic inside an update script avoids an application-level read-modify-write cycle.

Example incrementing order count:

~~~java
UpdateQuery query = UpdateQuery.builder("SKU-1")
    .withScript(
        "ctx._source.orderCount = " +
        "(ctx._source.orderCount == null ? 0 : ctx._source.orderCount) + params.delta"
    )
    .withParams(Map.of("delta", 1))
    .withLang("painless")
    .withRetryOnConflict(3)
    .build();

operations.update(
    query,
    IndexCoordinates.of("inventory")
);
~~~

A concurrency integration test can dispatch multiple concurrent increments and then read the final value. Starting from `orderCount = 0` with `N` updates of `delta = 1`, the expected result is `N` if all operations succeed.

### Do Not Confuse Atomic Updates with Idempotency

A script increment runs as one update on the document, yet if a client times out and replays the same business command, the counter can still increment twice. `retry_on_conflict` handles internal update conflicts; it cannot tell whether two client requests represent the same event.

To guard against duplicate events, tests must simulate replaying the same event ID and verify deduplication at the application layer or data design. You cannot rely solely on `retry_on_conflict`.

### Script Limitations

Scripts should be short and use `params`. Never concatenate user input into the script source string. For inventory subtraction, enforce non-negative checks inside the script if Elasticsearch holds inventory mutations. If the system requires strong transactions or multi-resource coordination, use a transactional database as the source of truth.

## 18. Designing Deterministic Concurrency Tests

Concurrency tests flake easily if they rely on `Thread.sleep` to manufacture race conditions. Use `CountDownLatch`, `CyclicBarrier`, or explicit synchronization so two threads read the exact same state before writing.

General scenario:

~~~text
Thread A                 Thread B
   |                         |
   +---- read version V -----+
   |                         |
   +---- wait at barrier ----+
   |                         |
   +---- update with V ------+
                             |
                             +---- update with V
                                  (one stale write conflicts)
~~~

In real tests:

- Create the initial document.
- Read two copies with identical version metadata.
- Use a barrier so both wait until both have read before writing.
- Each thread tries updating with its read version.
- Collect successes and conflicts.
- Verify exactly one stale conditional write succeeds when both use the same metadata.
- Read the document back to verify the final state.

Never assert that Thread A always wins or Thread B always wins. Schedulers do not guarantee thread order. Assert the counts of successes/conflicts and data invariants.

### Testing Concurrency with Reactive Flows

If the application uses `ReactiveElasticsearchOperations`, you can combine publishers using `Mono.zip` or `Flux.merge` depending on semantics. Use `StepVerifier` to verify results. Never call `block` inside an event loop to force concurrent execution.

Distinguish test concurrency from actual Elasticsearch concurrency. Subscribing two publishers closely together does not guarantee they read the same version without an explicit synchronization step.

## 19. Testing Nested, Geo, and Concurrency on the Same Entity

An entity may combine nested variants, geo location, and version:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;

    @GeoPointField
    private GeoPoint location;

    @Version
    private Long version;
}
~~~

Integration tests can then verify behaviors independently:

- Nested queries match the right variant.
- Geo distance queries match products within radius.
- Concurrent updates using an old version do not overwrite each other.
- Updating a nested child updates the parent document's version per contract.
- Search queries after refresh return the updated data.

Avoid combining everything into one giant test that is hard to diagnose. Split tests by behavior, sharing a fixture setup if appropriate while keeping each test's assertions focused.

If nested children are updated frequently under heavy contention, remember the whole parent document remains the unit of update. That may be a sign to model children as separate documents if the workload needs independent updates.

## 20. Testing Missing Data and Boundaries

Boundary cases expose mapping or query errors better than simple happy paths.

### Nested

- Parent has no `variants`.
- `variants` is an empty array.
- Child misses `color` or `size`.
- Two children share the same `variantId` if disallowed by domain rules.
- Query with a single condition.
- Multi-condition query requiring a single matching child.
- Updating a non-existent child.

### Geo

- `location` is null or missing.
- Latitude outside `[-90, 90]`.
- Longitude outside `[-180, 180]`.
- Swapped `lat`/`lon` coordinates.
- Points just inside or outside radius.
- Points on bounding box edges.
- Documents lacking geo fields when sorting by distance.

### Concurrency

- Two requests writing the same version.
- One request reading after another has written.
- Concurrent update scripts.
- Conflicts exceeding retry limit.
- Client timeout followed by replaying the same command.
- Document deleted between read and write.
- Two workers updating different fields on the same document.

Tests should verify both successful outcomes and error states according to application policy.

## 21. Testing Mappings and Queries Against Real Elasticsearch

Some tests only need a Spring context, while the following should run against real Elasticsearch:

| Behavior | Why integration testing is needed |
|---|---|
| Nested mapping and cross-object matching | Depends on how Elasticsearch indexes nested documents |
| Nested queries and inner hits | Depends on Query DSL and mappings |
| Geo distance/bounding box | Depends on `geo_point` mapping and distance semantics |
| Geo sorting | Depends on Elasticsearch sort implementation |
| Version conflict | Depends on document version metadata |
| `if_seq_no`/`if_primary_term` | Needs verification of real conditional writes |
| `retry_on_conflict` | Depends on the update API and Painless execution |
| Refresh visibility | Depends on refresh lifecycle |

Mocks only confirm the service invokes a method or builds an object. They do not confirm the server interprets the query as intended.

## 22. Common Testing Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Nested query matches even though `color` and `size` are on different children | Mapping is `object` or conditions sit in separate `nested` clauses | Use `nested` mapping and combine conditions inside one `nested` query |
| Nested query fails | Field not mapped as `nested` or wrong `path` | Inspect index mapping and `path` |
| Adding nested annotation leaves existing index unchanged | Elasticsearch cannot convert `object` to `nested` in place | Create a new index and reindex |
| Geo query misses expected point | Field is not `geo_point` or coordinates are swapped | Inspect mapping and `lat`/`lon` order |
| Geo distance uses wrong unit | Missing or wrong distance unit | Specify units explicitly like `km` or `m` |
| Bounding box returns unexpected points | Swapped corners or confused with radius query | Check `top_left`/`bottom_right` and use the right query |
| Stale entity overwrites newer data | Missing version/concurrency control | Use `@Version` or `seq_no`/`primary_term` |
| Concurrency test passes/fails intermittently | Relies on non-deterministic timing | Use barriers/latches and assert invariants |
| `retry_on_conflict` still increments counter twice | Client replays the same command after timeout | Use event IDs/deduplication |
| Search test misses updates | Index not refreshed yet | Refresh or read by ID |
| Incompatible Testcontainers setup | Image version mismatches dependencies | Pin a compatible version |
| Unexpected exception type | Spring/client wraps exceptions differently per version | Assert the release's actual exception contract |

## 23. Checklist for Nested, Geo, and Concurrency Tests

- [ ] Integration tests use a compatible Elasticsearch version.
- [ ] Tests create the actual index and mapping before seeding data.
- [ ] Nested collections are mapped as `nested`, not just `object`.
- [ ] Seeded data includes multiple children with distinct values.
- [ ] A test exists to detect cross-object matching.
- [ ] Conditions targeting the same child are placed in the same `nested` query.
- [ ] Inner hits are verified if used by the application.
- [ ] Geo fields are mapped as `geo_point`.
- [ ] Tests use asymmetric coordinates to catch swapped `lat`/`lon`.
- [ ] `geo_distance` tests cover points inside and outside the radius.
- [ ] Bounding box tests cover all directions and required edges.
- [ ] Geo sorting is tested if used by the application.
- [ ] Entity version is mapped and stale writes are rejected.
- [ ] `if_seq_no`/`if_primary_term` is tested if used directly.
- [ ] Update script concurrency is tested against clear invariants.
- [ ] Never use sleep to induce race conditions.
- [ ] Distinguish version conflict, retry, and idempotency.
- [ ] Test refresh visibility and GET by ID where appropriate.
- [ ] Test data/indices are isolated and cleaned up safely.

Nested, geo, and concurrency all depend on Elasticsearch's actual semantics. Nested tests must prove conditions apply to the same child object; geo tests must verify mapping and coordinate ordering; concurrency tests must prove stale writes are caught or atomic updates preserve invariants. Using unit tests for application logic and integration tests against compatible Elasticsearch for mapping, queries, and version behavior catches bugs mocks can never simulate.
