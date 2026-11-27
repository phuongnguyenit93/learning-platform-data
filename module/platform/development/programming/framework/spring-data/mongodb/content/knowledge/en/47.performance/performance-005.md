# Optimizing Indexes for Filter, Sort, Collation, and Pagination

## 1. Context: indexes must serve real queries

In the **SPRING_DATA_MONGODB** module, we use Spring Data MongoDB to connect, map documents, and operate on MongoDB via MongoTemplate or repositories. Alongside querying, aggregation, transactions, reactive access, and testing, an essential skill is **diagnosing data performance from execution plans**, especially when list screens must filter, sort, and paginate simultaneously.

Suppose a sales application serves multiple enterprise tenants. An order management screen requires:

- Returning only orders belonging to the authenticated tenant.
- Filtering by statuses such as PAID or PENDING.
- Showing newest orders first.
- Deterministic ordering when two orders share the exact same creation timestamp.
- Paginating across many pages, even when the dataset holds millions of orders.
- On another screen, sorting customer names according to Vietnamese rules, potentially case-insensitively.

Creating separate single-field indexes for each field can still force the application to read too many keys, sort in memory, or degrade on deep pages. A well-designed **compound index** must reflect how **filter**, **sort**, **collation**, and **pagination** work together.

After this lesson, you will be able to:

1. Identify a query shape and choose compound index key order using Equality–Sort–Range (ESR), while recognizing when to consider Equality–Range–Sort (ERS).
2. Explain why sort direction, prefix keys, and range filters affect index utilization.
3. Create compatible indexes and queries with collations for Vietnamese strings.
4. Distinguish offset pagination from keyset/cursor pagination and design stable ordering with a unique tie-breaker.
5. Write matching MongoTemplate/Repository examples and verify with explain("executionStats").
6. Evaluate trade-offs among read speed, index footprint, and write overhead.

## 2. Data model and query shape

The **orders** collection stores documents like:

~~~javascript
{
  _id: ObjectId("65350f8453dbe413901c1211"),
  tenantId: "tenant-A",
  status: "PAID",
  createdAt: ISODate("2026-11-18T08:30:00Z"),
  customerName: "Nguyen An",
  totalAmount: NumberDecimal("125000.00")
}
~~~

Practice assumptions:

- **tenantId**, **status** are strings; **createdAt** is a BSON Date; **_id** is an ObjectId.
- **createdAt** and **_id** always exist and are non-null; **createdAt** is not arbitrarily modified after creation. ID is unique.
- The primary query filters tenantId = tenant-A and status = PAID; sorting **createdAt descending then _id descending**.
- Tenant authorization is enforced at the application layer and always injected into queries.
- Examples use MongoDB and Spring Data MongoDB compatible with the illustrated APIs; verify against your deployed library versions in production.

Frequently executed query:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

A **query shape** is more than a list of fields: it encompasses filter operators (equality, greater-than, in-set, regex...), sort fields and directions, collation, result limits, projections, and sometimes pagination predicates. Two queries both using tenantId and createdAt but differing in sort or collation may require different index strategies.

| Requirement | Query pattern | Index implication |
| --- | --- | --- |
| Filter tenant and status | tenantId = ..., status = ... | Equality fields typically come first. |
| Fetch newest | sort(createdAt DESC, _id DESC) | Both sort keys need matching order and compatible directions. |
| Filter amount range | totalAmount >= ... | Range condition; placement relative to sort depends on selectivity. |
| Customer names in Vietnamese | sort(customerName ASC) + collation vi | Index and query must use compatible collations. |
| Deep pages | skip(offset) + limit | Still incurs work skipping preceding results. |
| Next page via cursor | createdAt/_id less than last position | Requires deterministic sort and index matching sort keys. |

## 3. Choosing a compound index for filter and sort

### 3.1. Equality – Sort – Range (ESR)

For the primary query, a natural starting candidate is:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_status_created_id" }
);
~~~

Key roles:

1. **tenantId: 1**: narrows to one tenant via equality comparison.
2. **status: 1**: further narrows via equality comparison.
3. **createdAt: -1**: retrieves records in descending chronological order.
4. **_id: -1**: acts as a unique tie-breaker so ordering stays deterministic even when multiple orders share createdAt.

A single index can serve both filtering and sorting if the query uses its keys compatibly. MongoDB can walk index entries in the required order instead of collecting all matches and running a blocking sort.

~~~mermaid
flowchart LR
  A[tenantId = tenant-A] --> B[status = PAID]
  B --> C[createdAt DESC]
  C --> D[_id DESC]
  D --> E[Limit 20 results]
~~~

**ESR is a starting design guideline, not a guarantee that every query will be optimal**. The planner also relies on statistics, actual data, selectivity, returned fields, range predicates, and competing indexes.

### 3.2. Index prefix concept

The index keys follow the order:

~~~text
tenantId → status → createdAt → _id
~~~

Leading contiguous prefixes are:

~~~text
{ tenantId }
{ tenantId, status }
{ tenantId, status, createdAt }
{ tenantId, status, createdAt, _id }
~~~

A query filtering only status without tenantId cannot leverage the leading prefix of this index the way a query supplying both does. MongoDB may still scan the index differently in some cases; the key rule is **never assume a multi-field index efficiently replaces dedicated indexes for arbitrary field subsets**.

To use an index for sorting on **non-leading** keys, prefix keys preceding the sort keys generally require equality predicates. For example:

~~~javascript
// Compatible with index because both tenantId and status are fixed.
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);

// status not fixed: typically cannot use the same index
// to obtain overall createdAt order across multiple statuses.
db.orders.find({ tenantId: "tenant-A" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

The second query may need its own index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_created_id" }
);
~~~

Do not create both indexes automatically. Evaluate actual query frequency, latency targets, write rates, and storage footprint first.

### 3.3. Sort direction on compound indexes

In MongoDB, a compound index supports sort directions matching the key order, or reversing all corresponding sort key directions simultaneously.

Given index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

When tenantId and status are equality-bound, these sorts are compatible with the sort portion:

~~~javascript
.sort({ createdAt: -1, _id: -1 }) // Matches index directions.
.sort({ createdAt:  1, _id:  1 }) // Reverses both directions together.
~~~

This sort is incompatible with that exact ordering:

~~~javascript
.sort({ createdAt: -1, _id: 1 })
~~~

Optimizing the third case may require a different index or accepting an extra sort stage. Do not infer from a single-field createdAt sort that every direction combination of createdAt + _id is supported.

### 3.4. Does equality field order matter?

For queries always fixing both tenantId and status, both indexes below narrow the search before sorting:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
{ status: 1, tenantId: 1, createdAt: -1, _id: -1 }
~~~

However, if the application frequently queries **by tenant without filtering status**, placing tenantId first makes the prefix reusable for that pattern. Choose equality key order based on the full query workload, cardinality, prefix reuse, and tenant isolation needs. There is no rigid rule that the highest-cardinality field must always come first in every scenario.

## 4. Range filters: when ESR and ERS present trade-offs

Suppose the screen also filters orders above an amount threshold:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  totalAmount: { $gte: NumberDecimal("1000000") }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Two candidate indexes:

~~~javascript
// ESR: equality → sort → range.
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1, totalAmount: 1 },
  { name: "idx_orders_esr" }
);

// ERS: equality → range → sort.
db.orders.createIndex(
  { tenantId: 1, status: 1, totalAmount: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_ers" }
);
~~~

**ESR** preserves ordering by createdAt/_id to avoid a blocking sort; in return, if very few orders pass the amount threshold, MongoDB may traverse many entries before collecting 20 matches.

**ERS** places the totalAmount range before the sort keys, narrowing index entries earlier. However, because totalAmount is not fixed to a single value, global createdAt order across amount ranges is broken. The query may have to sort matching entries, consuming CPU/memory.

| Data condition | Candidate worth testing first | Reason |
| --- | --- | --- |
| Users always request top 20 newest; range is not highly selective | ESR | Preserves reading results in sort order. |
| Range is extremely selective, matching very few documents | ERS | Minimizes keys scanned before sorting. |
| No totalAmount condition | Basic equality + sort index | Avoids widening the index unnecessarily. |
| Multiple distinct query shapes | Minimal workload-driven index set | Every added index increases write maintenance cost. |

Never keep both ESR and ERS indexes in production just because both rules exist. Benchmark with realistic data distributions, especially totalAmount thresholds across percentiles and tenants of varying sizes.

Additional note: operators such as **$gt, $lt, $ne, $nin**, and certain multi-value **$in** predicates produce bounds/execution strategies different from simple equality. Sort optimization behavior can vary by query structure and MongoDB version; always check explain instead of applying ESR mechanically.

## 5. Collation: index and query must share string comparison rules

### 5.1. The problem with Vietnamese names

Suppose collection **customers** holds:

~~~javascript
{ _id: ObjectId("65350f8453dbe413901c1221"),
  tenantId: "tenant-A",
  displayName: "Nguyễn An" }

{ _id: ObjectId("65350f8453dbe413901c1222"),
  tenantId: "tenant-A",
  displayName: "nguyễn bình" }

{ _id: ObjectId("65350f8453dbe413901c1223"),
  tenantId: "tenant-A",
  displayName: "Nguyen Cuong" }
~~~

Default binary ordering (**simple collation**) compares byte sequences, which is unnatural for many languages. MongoDB supports **collation** to compare and sort according to locale, strength, and related ICU options.

Example creating an index to filter by tenant, sort by name, then break ties with _id:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, displayName: 1, _id: 1 },
  {
    name: "idx_customers_tenant_name_vi",
    collation: { locale: "vi", strength: 2 }
  }
);
~~~

And the query must declare the **same collation**:

~~~javascript
db.customers.find({ tenantId: "tenant-A" })
  .collation({ locale: "vi", strength: 2 })
  .sort({ displayName: 1, _id: 1 })
  .limit(20);
~~~

**strength: 2** distinguishes diacritics while ignoring case differences at the primary comparison level; **strength: 1** also ignores diacritic differences at the primary level. Exact ordering is defined by ICU/locale rules; test against your system's real Vietnamese names rather than guessing full character ordering.

A query without an explicit collation uses the **collection's default collation** (if set), or simple collation otherwise. A Vietnamese-collation index typically **cannot serve string comparisons/sorts** for a query using simple collation. MongoDB might still use non-string prefix keys in certain cases, but do not mistake that for optimizing the displayName sort.

### 5.2. Where do mismatches occur?

| Case | Can use collation index for strings? | Explanation |
| --- | --- | --- |
| Index vi, strength 2; query vi, strength 2 | Yes, if key predicates also align | Matching string comparison rules. |
| Index vi, strength 2; query simple | No, for string comparison/sort via that index | Comparison rules do not match. |
| Index vi, strength 2; query vi, strength 1 | No, for string comparison/sort via that index | Strength differs. |
| Query using only numeric prefix of collated index | Prefix may be used, plan-dependent | Does not mean string sort is optimized. |

Collation can produce **larger index keys** due to ICU sort keys. Standardize locale, strength, and numericOrdering conventions across indexes and queries, and avoid maintaining duplicate indexes differing only by collation.

**Collation does not make case-insensitive regexes (`/i`) accelerated by a collation index.** Substring, fuzzy search, or autocomplete have different requirements and may require dedicated search designs or engines.

### 5.3. Collation and pagination

When paginating by displayName:

~~~javascript
.sort({ displayName: 1, _id: 1 })
~~~

Appending _id guarantees a **total order** when names compare equal under the collation. Subsequent page cursors must preserve the **last displayName and _id**, using the exact same collation and filter predicates. Never change locale/strength between pages while reusing an old cursor, because less-than/greater-than ordering may change.

For keyset pagination, sort fields should be non-null and stable. If the application permits editing customer names, items can shift positions between page loads; either accept that behavior or introduce a snapshot/watermark mechanism matching requirements.

## 6. Pagination: offset and keyset are not equal in cost

### 6.1. Offset pagination with skip/limit

Example fetching page 1001 with 20 orders per page (1-based):

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(20000)
.limit(20);
~~~

A good index avoids an expensive sort, yet **skip does not jump instantaneously to record 20,001**. The server must still walk/skip preceding results. Consequently, examined keys grow with page depth even when only 20 documents are returned.

Offset pros:

- Easy API design with page number and page size.
- Works well for small datasets or when users rarely view beyond the first few pages.
- Easy to support jumping directly to arbitrary page numbers in the UI.

Offset cons:

- Cost grows linearly with page depth.
- When documents are inserted or deleted between page reads, offsets shift, causing duplicate or skipped items.
- When returning Page<T> requiring total page counts, the app may run an extra count query.

**Always include a unique sort tie-breaker** such as _id so documents sharing createdAt do not shuffle arbitrarily between queries. Stable sorting improves ordering consistency, though it does not eliminate shifts from concurrent writes.

### 6.2. Keyset/cursor pagination using (createdAt, _id)

Instead of skipping N documents, the client sends the last position read.

First page:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Suppose the last element of page one has:

~~~javascript
{
  _id: ObjectId("65350f8453dbe413901c1211"),
  createdAt: ISODate("2026-11-18T08:30:00Z")
}
~~~

With descending sort on **both fields**, items on the next page must satisfy:

~~~text
createdAt < lastCreatedAt
OR
(createdAt = lastCreatedAt AND _id < lastId)
~~~

Next-page query:

~~~javascript
const lastCreatedAt = ISODate("2026-11-18T08:30:00Z");
const lastId = ObjectId("65350f8453dbe413901c1211");

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Initial candidate compound index to test:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

Be careful **not** to write:

~~~javascript
// Wrong: drops documents with the same createdAt and smaller _id.
{ createdAt: { $lt: lastCreatedAt } }
~~~

Nor two independent range conditions:

~~~javascript
// Wrong: requires both fields to be smaller, wrongly excluding valid records.
{ createdAt: { $lt: lastCreatedAt }, _id: { $lt: lastId } }
~~~

Using a positional predicate, keyset pagination avoids the linear cost of skipping all previous pages. Still, queries containing $or must be checked with explain on MongoDB against real data; optimal index usage and scan bounds are never guaranteed by syntax alone.

### 6.3. What should a cursor contain?

A cursor payload might carry:

~~~json
{
  "createdAt": "2026-11-18T08:30:00.000Z",
  "id": "65350f8453dbe413901c1211",
  "sort": "createdAt:desc,id:desc",
  "filtersFingerprint": "hash-of-tenant-and-status",
  "version": 1
}
~~~

This is an **illustrative structure**, not a signed token. Real systems should encode and sign/verify cursors, checking tenant, filter parameters, sort, collation, and expiration. Never trust client-supplied cursor contents to bypass tenant authorization.

If the sort flips to ascending, flip comparison operators accordingly. If timestamps can be null or modified after creation, revisit the data contract or cursor design; range comparisons involving null easily drop records.

### 6.4. Page, Slice, and Window in Spring Data

| Return type | Strength | Performance note |
| --- | --- | --- |
| Page<T> | Provides total count and total pages | May trigger a count query; mostly paired with offset. |
| Slice<T> | Indicates whether a next page exists without needing total count | Usually still relies on offset when backed by Pageable. |
| Window<T> + OffsetScrollPosition | Supports chunked scrolling | Still pays high offset skip costs. |
| Window<T> + KeysetScrollPosition | Spring Data builds the keyset predicate | Requires non-null sort keys, matching index, and all sort keys in projection. |
| Keyset via Query/Criteria | Full control over custom APIs and cursor tokens | Must manage comparisons, filters, sorts, and tokens manually. |

Spring Data MongoDB supports **scrolling with Window and ScrollPosition** on compatible repository APIs. When using keyset scrolling, Spring Data can append the identifier key to the sort for uniqueness; projections must include all sort fields. For the order screen illustrated here, the next section uses MongoTemplate to show the exact MongoDB predicates generated.

## 7. Implementing with Spring Data MongoDB

### 7.1. Entity and index definition

Sample entity:

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id ObjectId id,
    String tenantId,
    String status,
    Instant createdAt,
    String customerName
) {}
~~~

Explicit index creation via MongoTemplate:

~~~java
package example.orders;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public final class OrderIndexInstaller {
    private OrderIndexInstaller() {}

    public static void create(MongoTemplate template) {
        Index index = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("status", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .on("_id", Sort.Direction.DESC)
            .named("idx_orders_tenant_status_created_id");

        template.indexOps(Order.class).createIndex(index);
    }
}
~~~

The **createIndex(IndexDefinition)** method is available in newer Spring Data MongoDB releases (from 4.5); older versions use **ensureIndex**. Programmatic index creation above is an administrative operation to run via controlled migrations or startup tooling—**never inside every HTTP request**. Spring Data does not create indexes from annotations by default across all versions; since Spring Data MongoDB 3.0, auto-index-creation is disabled by default unless explicitly enabled.

You can declare **@CompoundIndex** at the class level when the application's index management mechanism is well defined:

~~~java
@CompoundIndex(
  name = "idx_orders_tenant_status_created_id",
  def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': -1 }"
)
~~~

This annotation sits on a @Document-annotated class. Avoid mixing multiple index creation mechanisms for the same index without clear schema management and database permission policies.

### 7.2. Offset query with MongoTemplate

~~~java
package example.orders;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderReadService {
    private final MongoTemplate template;

    public OrderReadService(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> pageByOffset(
            String tenantId, String status, int page, int pageSize) {

        if (page < 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid pagination request");
        }

        long offset = (long) page * pageSize;

        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is(status)
        )
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id") // Entity id maps to _id.
        ))
        .skip(offset)
        .limit(pageSize);

        return template.find(query, Order.class);
    }
}
~~~

Here page is 0-based. Beyond capping pageSize, production APIs should cap maximum offset or switch to cursors for deep browsing. Never accept arbitrary sort fields from clients directly into your index strategy without an allowlist.

### 7.3. Keyset query with MongoTemplate

Add a method inside the same service above; required imports are noted:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;

public List<Order> pageAfter(
        String tenantId, String status,
        Instant lastCreatedAt, ObjectId lastId, int pageSize) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid page size");
    }
    if ((lastCreatedAt == null) != (lastId == null)) {
        throw new IllegalArgumentException("Cursor must contain both keys");
    }

    Criteria filter = new Criteria().andOperator(
        Criteria.where("tenantId").is(tenantId),
        Criteria.where("status").is(status)
    );

    if (lastCreatedAt != null) {
        Criteria after = new Criteria().orOperator(
            Criteria.where("createdAt").lt(lastCreatedAt),
            new Criteria().andOperator(
                Criteria.where("createdAt").is(lastCreatedAt),
                Criteria.where("_id").lt(lastId)
            )
        );

        filter = new Criteria().andOperator(filter, after);
    }

    Query query = new Query(filter)
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(pageSize);

    return template.find(query, Order.class);
}
~~~

Place this method **inside OrderReadService** from section 7.2 so it uses the service's template field. On the initial call, pass null for both cursor keys; subsequent calls supply createdAt and id from the previous page's last item. In raw MongoDB queries, the identifier field is **_id**; in Spring Data entity Sort, property **id** maps to **_id**.

To reliably return hasNext for the UI, you can fetch pageSize + 1 records (within sensible bounds), keep pageSize items to display, and treat the extra item as the next-page indicator. Build the next cursor from the **actual last item returned to the client**, not from the lookahead item.

### 7.4. Collation in MongoTemplate

An example querying the customers collection in Vietnamese using raw Document to focus solely on filter/sort:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Document> listCustomers(
        MongoTemplate template, String tenantId) {

    Collation vietnamese = Collation.of("vi").strength(2);

    Query query = Query.query(Criteria.where("tenantId").is(tenantId))
        .collation(vietnamese)
        .with(Sort.by(
            Sort.Order.asc("displayName"),
            Sort.Order.asc("_id")
        ))
        .limit(20);

    return template.find(query, Document.class, "customers");
}
~~~

Crucially, the customers index also uses **{ locale: "vi", strength: 2 }** as in section 5. Even when Java code specifies Collation, the query can still be slow if the collection only has a simple-collation index or if index key order does not match the query.

## 8. Using explain to verify an index truly helps

### 8.1. Reading core metrics

Run the representative query in mongosh:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Fields to inspect:

| Field | Meaning | Interpretation |
| --- | --- | --- |
| winningPlan | Chosen execution plan | Check indexName, IXSCAN, FETCH, SORT/COLLSCAN; stage tree varies by engine/version. |
| executionStats.nReturned | Number of documents returned | Denominator when comparing scan volume. |
| totalKeysExamined | Index entries traversed | Closer to nReturned is often desirable for selective queries, though not an absolute rule. |
| totalDocsExamined | Documents read to filter/return data | Much higher than nReturned can signal an inefficient filter. |
| executionTimeMillis | Explain execution duration | Relative comparison only; does not replace application p95 benchmarks. |
| SORT stage | In-memory or blocking sort stage | Often signals checking key order, sort direction, and collation. |
| COLLSCAN | Collection scan | Not always wrong on tiny collections, but worth investigating on large/frequent queries. |

Hypothetical illustration comparing two outcomes, **not actual measurements**:

| Metric | Before suitable index | After suitable index |
| --- | ---: | ---: |
| nReturned | 20 | 20 |
| totalKeysExamined | 40,000 | 20 |
| totalDocsExamined | 30,000 | 20 |
| SORT stage | Yes | No |
| Duration on same data | High | Lower |

Achieving totalDocsExamined = 0 is **not mandatory** for a good index. If the query returns fields absent from the index, MongoDB still needs to FETCH documents; that can be a sensible trade-off.

In newer MongoDB releases, explain may use the **slot-based execution engine (SBE)** with a stage tree differing from classic examples. Instead of looking for a single label at a hardcoded JSON path, inspect queryPlanner, executionStats, and the selected index as a whole.

### 8.2. Measuring two critical variants accurately

Test two queries with similar filters but different sort compatibility:

~~~javascript
// Query A: equality on both leading keys.
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

// Query B: missing status; same index may no longer support the sort efficiently.
db.orders.find({ tenantId: "tenant-A" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Test matching vs. mismatched collations with the same filter:

~~~javascript
db.customers.find({ tenantId: "tenant-A" })
  .collation({ locale: "vi", strength: 2 })
  .sort({ displayName: 1, _id: 1 })
  .limit(20)
  .explain("executionStats");

db.customers.find({ tenantId: "tenant-A" })
  .collation({ locale: "simple" })
  .sort({ displayName: 1, _id: 1 })
  .limit(20)
  .explain("executionStats");
~~~

Test shallow vs. deep pagination with the same index:

~~~javascript
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0).limit(20)
  .explain("executionStats");

db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(20000).limit(20)
  .explain("executionStats");
~~~

Record inputs and before/after metrics for comparison. For real queries, also test large/small tenants, common/rare statuses, and range filters of varying selectivity. The planner can select different plans as data distributions shift.

**Note:** Explain executes the plan to gather statistics, which can impose load. Explain timings do not necessarily reflect network latency or normal query plan cache behavior. Avoid running full-scan explains arbitrarily on production; validate in a test environment with representative data and combine with real application metrics.

## 9. Additional optimizations to consider

### 9.1. Projection and covered queries

If the list screen only needs tenantId, status, createdAt, and _id, restrict returned fields:

~~~javascript
db.orders.find(
  { tenantId: "tenant-A", status: "PAID" },
  { tenantId: 1, status: 1, createdAt: 1, _id: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

When every field used in filtering, sorting, and projection lives in the index, some queries can be **covered**, avoiding full document fetches. Yet having many fields in an index does not guarantee coverage: it also depends on index type, predicates, projection, collation, array/multikey fields, and execution plan.

Never stuff every document field into an index just to hit totalDocsExamined = 0. Overly wide indexes consume storage, reduce cache efficiency, and increase insert/update/delete overhead.

### 9.2. Partial indexes for a very specific screen

Suppose most admin screens only inspect PAID orders:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "idx_orders_paid_partial",
    partialFilterExpression: { status: "PAID" }
  }
);
~~~

This index only indexes PAID documents, potentially making it smaller than a full index. Compatible queries must **include status: "PAID"** so results remain complete. Queries fetching PENDING orders cannot use this partial index to return complete data.

Do not confuse a **partial index** with a **sparse index**. Partial indexes rely on explicit filter expressions; eligibility must be confirmed by the query planner via explain. If nearly all documents are PAID or many screens query other statuses, real-world savings may be minor.

### 9.3. Multikey and array data

When an indexed field is an array, MongoDB builds a **multikey index**. Certain sort and filter combinations on arrays still trigger a blocking SORT despite an index; compound multikey indexes also restrict having multiple array fields in the same document.

Therefore, the order example uses scalar fields with consistent types. If expanding filters to arrays like tags, products, or promotions, re-benchmark execution plans rather than assuming extending the current scalar index preserves performance.

### 9.4. Write cost, memory, and duplicate indexes

Every index must be updated when documents are inserted/deleted or indexed fields change. Redundant indexes typically cause:

- Higher disk and cache consumption.
- Extra I/O when writing orders or updating statuses.
- Longer index build times and schema deployments.
- Overlapping indexes that complicate measurement and operations.

Use **db.orders.getIndexes()** to audit existing indexes. Before dropping an old index, measure queries relying on it. MongoDB supports **hidden indexes** to test planner impact prior to permanent removal in supported versions/environments; coordinate with operational procedures since hiding an index can affect live workloads.

## 10. Functional and performance testing

A new index must preserve query semantics. After creating an index, test both **data correctness** and **speed/resource usage**.

| Scenario | What to verify |
| --- | --- |
| Two orders share createdAt | Order by _id is deterministic; paging neither duplicates nor drops items on static data. |
| Tenant A and Tenant B share statuses | Queries return only authorized tenant's orders; zero data leakage. |
| Status filter omitted | Re-run explain because an index with status before createdAt may not support the sort as expected. |
| Wide and narrow totalAmount ranges | Measure ESR vs. ERS with nReturned, keysExamined, docsExamined, SORT. |
| Vietnamese names differing by diacritics/case | Collation enforces contract accurately; expected index is chosen. |
| Query collation mismatches index | Observe plan and latency changes; do not assume index sorting still applies. |
| Skip 0, 1,000, and 20,000 | Confirm offset scan cost grows with page depth. |
| Keyset first and subsequent pages | Correct order; cursor does not drop records sharing timestamps. |
| Concurrent inserts/deletes while paging | Behavior matches consistency contract; re-test if snapshot semantics are expected. |
| Increasing concurrent write rate | Read p95/p99, write throughput, and disk/cache usage remain acceptable. |

Recommended experimental workflow:

1. **Lock down query shape and criteria:** p95, returned record count, keysExamined/nReturned ratio, pagination behavior, write capacity.
2. **Capture baseline:** run explain, inspect logs/profiler, and measure application latency before adding indexes.
3. **Create candidate index in test environment:** with dataset and distribution resembling real workloads.
4. **Re-measure the exact query:** identical filter, sort, collation, limit, projection, and page depth; compare against baseline.
5. **Verify correctness:** especially at page boundaries, duplicate timestamps, concurrent inserts/deletes, and accented strings.
6. **Review operational cost:** index size, index count, write throughput, buffer/cache usage, and rollout plan.
7. **Approve using metrics:** keep only indexes delivering clear gains for critical queries, removing unused candidates systematically.

Do not set a rigid target like "totalKeysExamined must always equal 20" for every query. Range filters, filtered-out matches, covered vs. non-covered plans, and execution strategies can legitimately raise examined counts. Always interpret metrics within the full workload and data context.

## 11. Common design mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Creating separate tenantId, status, createdAt indexes without testing compound indexes | Planner may filter yet still sort many documents | Design indexes for common filter + sort patterns. |
| Placing createdAt before all equality keys | May scan across many tenants or statuses | Try ESR ordering and measure real distributions. |
| Sorting only by createdAt | Duplicate timestamps cause non-deterministic ordering | Add _id as a tie-breaker in sort and index. |
| Missing equality on prefix key before sort | MongoDB struggles to use the index for the desired order | Add the filter or design an index for the other query shape. |
| Index sorted DESC/DESC but query sorts DESC/ASC | May force a SORT | Align directions or design a separate index. |
| Vietnamese query collation mismatches index | Cannot leverage index string ordering | Use matching locale/strength and verify via explain. |
| Using regex /i expecting collation index acceleration | Execution plan may still scan heavily | Use collation-supported equality queries or a search engine. |
| Using huge skip values for infinite scroll | Cost grows with page depth | Use keyset/cursor pagination on indexed sort keys. |
| Keyset relying solely on createdAt | Timestamp collisions drop records | Cursor must include both createdAt and _id. |
| Changing filter/sort while reusing old cursor | Wrong offset, duplicate/missing results | Bind cursor to query shape and validate it. |
| Forcing covered queries via overly wide indexes | Increases write amplification and disk/cache usage | Measure total cost and keep projections lean. |
| Relying on explain over a handful of documents | Small-data plans do not represent production | Test on varied data sizes and realistic load. |

## 12. Hands-on exercise

Create a large enough orders collection in a test environment containing multiple tenants, statuses, and several orders sharing identical createdAt values. Proceed step by step:

1. Run the query filtering tenantId + status and sorting createdAt DESC, _id DESC without a compound index; save explain output.
2. Create index **{tenantId:1, status:1, createdAt:-1, _id:-1}**; re-run the same query and compare metrics.
3. Omit the status predicate; observe the planner. Propose an index for the new query and re-measure.
4. Add a totalAmount range and compare ESR vs. ERS candidates across wide and narrow amount intervals.
5. Seed customers with Vietnamese names and a vi strength 2 collation index; test compatible and incompatible queries.
6. Compare skip(0), skip(10000), and keyset pagination after the corresponding boundary; record keysExamined, docsExamined, and duration.
7. Create several orders with identical timestamps and verify continuous paging neither loses nor duplicates records on a static dataset.
8. Write a brief summary concluding which indexes to retain based on measured workloads and system write costs.

**Self-assessment questions:**

- Why can a compound index containing all required field names still fail to eliminate sorting?
- How do ESR and ERS differ, and when should you benchmark both?
- Why can an index built with Vietnamese collation fail to speed up a query using simple collation?
- Why is adding _id to the sort important even when createdAt seems "nearly unique"?
- Why does keyset pagination excel on deep pages yet remain sensitive to data updates between calls?

Index effectiveness comes from matching **specific filters, sort orders, collations, and pagination patterns**, not the sheer number of indexes created. Pick an important query shape, design candidate indexes, verify with explain and realistic benchmarks, and keep the option delivering the best results at acceptable operational cost.

## 13. References

- [MongoDB – ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/): equality, sort, range ordering and ERS cases.
- [MongoDB – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): index prefixes and key ordering.
- [MongoDB – Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/): sort support, non-prefix sorts, and index direction.
- [MongoDB – Collation](https://www.mongodb.com/docs/manual/reference/collation/): locale, strength, and string comparison.
- [MongoDB – Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/): compatible collation requirements.
- [MongoDB – cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/): offset cost, stable ordering, and range pagination.
- [MongoDB – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): queryPlanner and executionStats.
- [MongoDB – Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): index scope and eligible query predicates.
- [Spring Data MongoDB – Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): Query/Criteria, sort, collation, and index hints.
- [Spring Data MongoDB – Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): IndexOperations and index management.
- [Spring Data MongoDB – Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html): Collation in Spring Data.
- [Spring Data MongoDB – Repository Scrolling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): Window, offset, and keyset.
