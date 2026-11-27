# When to Move Complex Pipelines to a Template or Fragment?

> **Chapter:** Aggregation repository  
> **Module:** `SPRING_DATA_MONGODB`

In Spring Data MongoDB, `@Aggregation` lets you place a MongoDB pipeline directly on a repository method. For fixed reporting queries, this is usually concise, easy to invoke, and makes the data contract obvious. However, a pipeline can grow from three stages into multiple optional filter branches, `$lookup` across collections, `$facet` returning both a page list and total group count, pagination, business-specific calculations, and varying endpoint requirements. At that point, stuffing every variant into a long annotation can make code hard to read, hard to reuse, and hard to test.

There are two main scaling paths: moving aggregation logic into **`MongoTemplate` with the `Aggregation` DSL**, or encapsulating that logic inside a **custom repository fragment** so the application still calls one cohesive domain repository. **Templates and fragments are not mutually exclusive choices**: fragments commonly use `MongoTemplate` internally.

This lesson belongs to the `SPRING_DATA_MONGODB` module, covering connecting and mapping documents, operating via `MongoTemplate` or repositories, queries, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics. The focus here is **criteria for deciding where to place a pipeline**, how to migrate a practical example, and limits developers must verify before going to production.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the differences among `@Aggregation`, `MongoTemplate.aggregate(...)`, and custom repository fragments.
2. Recognize signals that it is **too early to move** and signals that a pipeline is complex enough to move.
3. Write a static reporting pipeline with repository `@Aggregation`, then migrate it to a dynamic pipeline using `Aggregation.newAggregation(...)`.
4. Encapsulate dynamic pipelines inside a fragment following Spring Data conventions, keeping aggregation details out of controllers.
5. Distinguish aggregation result DTOs from source entities, especially when `$group` changes the meaning of `_id`.
6. Design tenant and access filters, optional filters, result caps, pagination, and real-BSON tests.
7. Evaluate query plans, indexes, `$facet`, `$lookup`, streaming/reactive capabilities, and code organization costs.

## 2. Three levels of organizing aggregations

```text
Controller / Application Service
               |
               v
      OrderRepository (domain API)
               |
       +-------+-------------------+
       |                           |
   @Aggregation           OrderReportOperations
   static pipeline        (repository fragment)
       |                           |
       v                           v
  Spring Data                  MongoTemplate
  repository query             Aggregation DSL
       |                           |
       +-------------+-------------+
                     |
                     v
               MongoDB server
                     |
                     v
             Aggregation result DTO
```

You can invoke `MongoTemplate` directly from a dedicated service when a pipeline represents reporting logic beyond the domain repository's responsibility. However, if the team wants all `Order` queries accessed through a **single repository interface**, a custom fragment hides pipeline details and keeps call sites simple.

### 2.1. Comparison table

| Criterion | Repository `@Aggregation` | `MongoTemplate` / Aggregation DSL | Repository fragment |
| --- | --- | --- | --- |
| Fixed, short pipeline | Very suitable | Works, sometimes more verbose than needed | May add unnecessary boilerplate |
| Optional stages from requests | Hard to scale, prone to method explosion | **Suitable**: composes `AggregationOperation` dynamically | **Suitable**, typically uses template inside |
| Complex `$lookup` / `$facet` | Possible as long JSON, harder to maintain | Has builders and stage extensibility | Hides complexity behind a domain API |
| Reusing filter/pipeline snippets | Limited inside annotation strings | Easy to extract helpers/operations | Easy to share in implementation class |
| Testing individual stages | Can run integration tests, hard to assemble slices | Easy to run prefix pipelines and inspect | Tested via repository + implementation logic |
| Field/DTO mapping | Requires checking input/output mapping | Supports typed aggregation and mapping | Depends on chosen template/DSL |
| Caller-facing API | Repository method | Direct service/template method | Domain repository method |
| Auxiliary classes/code | Minimal | Moderate | More (interface, impl, wiring) |
| Performance for identical BSON pipeline | Executed by MongoDB server | **Not faster by default** | **Not faster by default** |

**Key conclusion:** switching to a template **is not an automatic performance optimization**. It mainly solves organizing dynamic pipelines, testing, maintenance, and controlling options/query mapping. Performance still depends on the BSON sent, indexes, data distribution, and MongoDB infrastructure.

## 3. When to keep @Aggregation?

Keeping the annotation is a sound choice when:

- The stage count is small and the **pipeline structure is fixed**.
- Parameters only vary filter or threshold **values**, never adding or removing stages.
- The output DTO is stable and concise to describe.
- There is no need to assemble multiple `$match`, `$lookup`, `$facet`, projection, or custom pagination branches.
- Code reviewers can read the entire pipeline without tracing variants of JSON strings.

Example of a simple contract: "Within a tenant, count orders and total amount for **one status**." That query has parameterized values without **changing pipeline structure**.

### 3.1. Signs you should not migrate prematurely

If you only need one extra fixed predicate or to change `"PAID"` into parameter `?1`, adding three fragment files can make the problem harder to follow. Annotation length **is not** the sole criterion; a somewhat long yet stable, well-tested pipeline can still be acceptable.

Do not invent a generic query DSL for every aggregation just because the project has two simple queries. Over-generalization can obscure MongoDB semantics right where it is read.

## 4. When to move to MongoTemplate?

Clear signals usually include:

1. **Dynamic stages:** requests can add or omit `$match`, `$lookup`, `$group`, `$project`, `$sort`, or `$limit`.
2. **Many optional filters:** time ranges, statuses, channels, amount thresholds, user types, permission groups.
3. **Branched pipelines:** `$facet` returning multiple summaries from one input set, or conditional `$lookup` sub-pipelines.
4. **Varying output shapes:** grouping by channel or status on demand, adding computed metrics only when requested.
5. **Execution configuration needed:** aggregation options, collation, allowDiskUse, read concern/session control, or appropriate reactive read paths.
6. **Stage-by-stage testing needed:** isolating `AggregationOperation`s, inspecting generated MongoDB pipelines and intermediate results.
7. **Logic reuse needed:** tenant filters, soft-delete policies, time windows, statuses, and formulas shared across reports.

These are signals of **structural variability and maintainability friction**, not a rigid rule like "more than 5 stages forces migration." Even a three-stage pipeline containing deeply nested `$cond` expressions may warrant moving.

### 4.1. Do not migrate just to concatenate arbitrary JSON

Moving `@Aggregation` into Java code while still concatenating field names and operators from user strings does not make pipelines any safer. For dynamic filters, prefer `Criteria` and builders with controlled types/contents; field names, sort keys, and calculation choices require an **allowlist**.

## 5. When is a custom repository fragment needed?

A fragment is an **API encapsulation step**, not a new kind of MongoDB query. Consider a fragment when:

- Callers should use `orderRepository.revenueByStatus(...)` without knowing `MongoTemplate` or collection names.
- You want a stable **domain reporting contract**, while the implementation can evolve from annotation to template or another pipeline.
- Multiple aggregation methods relate to one aggregate root/repository and share validation, mapping, and tenant rules.
- You want to separate derived-query methods from dynamic pipeline construction logic.
- You want to evolve/test the implementation independently without mixing BSON into controllers/services.

If a report is **cross-domain** (combining order, payment, shipment, inventory...), a dedicated `ReportingService`/query adapter may be cleaner than stuffing every report into `OrderRepository`. Do not force a fragment across the wrong boundary just to make "everything a repository."

### 5.1. Quick decision flow

```text
Does the pipeline have a fixed structure with few branches?
    |
    +-- Yes --> @Aggregation if clear and easy to test.
    |
    +-- No --> MongoTemplate + Aggregation DSL.
                    |
                    +-- Should callers see a domain repository API?
                           |
                           +-- Yes --> custom repository fragment
                           |
                           +-- No --> dedicated query/reporting service
```

**Fragments and templates work together:** a fragment's implementation is typically where `MongoTemplate` builds `AggregationOperation`s and maps results. Choosing a fragment does not remove the need to understand MongoDB aggregation.

## 6. Running scenario: order reporting

The system has an `orders` collection. Each document represents **one order** (not an individual line item), with tenant, status, sales channel, creation time, integer minor-unit amount, and archive flag:

```javascript
{
  _id: "A-101",
  tenantId: "TENANT-A",
  status: "PAID",
  channel: "web",
  amountMinor: NumberLong(100000),
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  archived: false
}
```

Keep the data simple so the **architectural transition points** stand out without getting distracted by complex financial formulas.

### 6.1. Sample data (test database only)

```javascript
use shop

db.orders.insertMany([
  { _id: "A-101", tenantId: "TENANT-A", status: "PAID",
    channel: "web", amountMinor: NumberLong(100000),
    createdAt: ISODate("2026-11-10T09:00:00Z"), archived: false },
  { _id: "A-102", tenantId: "TENANT-A", status: "PAID",
    channel: "app", amountMinor: NumberLong(80000),
    createdAt: ISODate("2026-11-10T10:00:00Z"), archived: false },
  { _id: "A-103", tenantId: "TENANT-A", status: "PAID",
    channel: "web", amountMinor: NumberLong(20000),
    createdAt: ISODate("2026-11-11T09:00:00Z"), archived: false },
  { _id: "A-104", tenantId: "TENANT-A", status: "NEW",
    channel: "web", amountMinor: NumberLong(50000),
    createdAt: ISODate("2026-11-11T10:00:00Z"), archived: false },
  { _id: "A-105", tenantId: "TENANT-A", status: "PAID",
    channel: "app", amountMinor: NumberLong(35000),
    createdAt: ISODate("2026-11-12T10:00:00Z"), archived: true },
  { _id: "A-106", tenantId: "TENANT-A", status: "NEW",
    channel: "app", amountMinor: NumberLong(40000),
    createdAt: ISODate("2026-11-12T11:00:00Z"), archived: false },
  { _id: "A-107", tenantId: "TENANT-A", status: "CANCELLED",
    channel: "web", amountMinor: NumberLong(60000),
    createdAt: ISODate("2026-11-13T09:00:00Z"), archived: false },
  { _id: "A-108", tenantId: "TENANT-A", status: "PAID",
    channel: "web", amountMinor: NumberLong(30000),
    createdAt: ISODate("2026-11-14T09:00:00Z"), archived: false },
  { _id: "B-201", tenantId: "TENANT-B", status: "PAID",
    channel: "web", amountMinor: NumberLong(999999),
    createdAt: ISODate("2026-11-13T09:00:00Z"), archived: false }
])
```

When **taking only TENANT-A, archived=false, and status in {PAID, NEW}**:

| Group | Included IDs | Order count | Total `amountMinor` |
| --- | --- | ---: | ---: |
| PAID | A-101, A-102, A-103, A-108 | 4 | 230,000 |
| NEW | A-104, A-106 | 2 | 90,000 |

A-105 is excluded because `archived=true`, A-107 is outside the selected status set, and B-201 belongs to tenant B. These predicates must hold **across every variant** of the pipeline.

### 6.2. Initial requirements and expansion

**Version 1:** "Given a known tenant and status, return order count and total amount." Fixed `$match` → `$group` → `$project` pipeline.

**Version 2:** Report can filter by time `[from, to)`, status set, channel, minimum amount; sort groups by revenue and limit group count. Stages remain simple, yet **predicates are assembled from inputs**.

**Version 3:** Needs both page data and total group count via `$facet`, or joining payments via `$lookup`; stronger needs for reuse, debugging, and explicit pipeline options. This is typically when you move aggregation to a template and consider a fragment.

## 7. Source entity and output DTO

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String status,
    String channel,
    long amountMinor,
    Instant createdAt,
    boolean archived
) {}
```

File `StatusRevenue.java`:

```java
package com.example.shop.orders;

public record StatusRevenue(
    String status,
    long orderCount,
    long revenueMinor
) {}
```

`@Id` maps property `id` to BSON `_id`. The example uses String IDs like `"A-101"` that do not look like ObjectIds. When using 24-hex-character IDs or `@MongoId`/`@Field`, check mapping and actual BSON types.

After `$group`, `_id` holds the **status value of the group**, no longer `OrderDocument.id`. Therefore, use a separate output DTO `StatusRevenue`. Do not read grouped aggregate results into `OrderDocument` and call `repository.save(...)`, because the schema is incomplete and `_id` has changed meaning.

## 8. First step: @Aggregation with a static pipeline

This is the right starting point when aggregating by a single status. File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        """
        {
          '$match': {
            'tenantId': ?0,
            'status': ?1,
            'archived': false
          }
        }
        """,
        """
        {
          '$group': {
            '_id': '$status',
            'orderCount': { '$sum': 1 },
            'revenueMinor': { '$sum': '$amountMinor' }
          }
        }
        """,
        """
        {
          '$project': {
            '_id': 0,
            'status': '$_id',
            'orderCount': 1,
            'revenueMinor': 1
          }
        }
        """
    })
    List<StatusRevenue> summarizeStatus(
        String permittedTenantId,
        String status);
}
```

The repository annotation is `org.springframework.data.mongodb.repository.Aggregation`, **distinct** from `org.springframework.data.mongodb.core.aggregation.Aggregation` used to build pipelines with the DSL.

### 8.1. How are parameters bound?

`?0` and `?1` are **positional parameter placeholders** in Spring Data query annotations. When the method is called with `("TENANT-A","PAID")`, Spring Data binds the two values into the filter rather than arbitrarily concatenating JSON from user text.

Expected result:

```java
List<StatusRevenue> result =
    repository.summarizeStatus("TENANT-A", "PAID");

// One row:
// StatusRevenue("PAID", 4L, 230000L)
```

The service layer must verify `permittedTenantId` from identity/authorization; do not let clients pick any tenant and assume the parameter name "permitted" secures the data.

### 8.2. Placing $project after $group

After `$group`, output contains:

```javascript
{
  _id: "PAID",
  orderCount: 4,
  revenueMinor: NumberLong(230000)
}
```

`$project` renames `_id` to `status` and removes `_id`, producing a schema matching `StatusRevenue`:

```javascript
{
  status: "PAID",
  orderCount: 4,
  revenueMinor: NumberLong(230000)
}
```

Do not reference `status` from the source entity after grouping while forgetting that only fields produced by `$group`/projections exist.

### 8.3. When does the annotation start losing its advantage?

Suppose business rules now require:

- Adding `channel = web` only when the user selects a channel.
- Omitting the status filter if all allowed statuses are selected, or permitting any subset of statuses from an allowlist.
- Adding `createdAt >= from AND createdAt < to`.
- Adding `amountMinor >= minimumAmountMinor` when a threshold is provided.
- Grouping by either `status` or `channel`.
- Returning one page of groups plus total group count via `$facet`.

Writing one annotation per combination creates many methods and duplicates pipelines. An annotation can bind parameters, yet **binding values differs from adding/omitting stages or changing pipeline shape**. This is where `MongoTemplate` should be considered.

## 9. Designing the filter contract before building dynamic pipelines

When moving to a template, do not pass a dozen loose parameters without rules. Bundle them into a type describing reporting intent and validate before hitting MongoDB.

File `OrderReportFilter.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public record OrderReportFilter(
    Instant fromInclusive,
    Instant toExclusive,
    Set<String> statuses,
    String channel,
    Long minimumAmountMinor,
    int maxGroups
) {
    private static final Set<String> SUPPORTED_STATUSES =
        Set.of("NEW", "PAID", "CANCELLED");

    public OrderReportFilter {
        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        Objects.requireNonNull(statuses, "statuses");

        statuses = Set.copyOf(statuses);

        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException(
                "fromInclusive must be before toExclusive");
        }
        if (!SUPPORTED_STATUSES.containsAll(statuses)) {
            throw new IllegalArgumentException(
                "Unsupported status present");
        }
        if (minimumAmountMinor != null
                && minimumAmountMinor < 0) {
            throw new IllegalArgumentException(
                "minimumAmountMinor must not be negative");
        }
        if (maxGroups < 1 || maxGroups > 100) {
            throw new IllegalArgumentException(
                "maxGroups must be between 1 and 100");
        }
        if (channel != null && channel.isBlank()) {
            throw new IllegalArgumentException(
                "channel must not be blank");
        }
    }
}
```

This design uses:

- `[fromInclusive, toExclusive)`: start timestamp **inclusive**, end timestamp **exclusive**. Do not manually add 23:59:59.999 to the end date, since sub-second precision and timezones vary.
- `statuses`: set of statuses permitted by the API. **An empty set is defined as returning nothing**, preventing accidentally dropping the filter and reading every status.
- `channel`: `null` means do not filter by channel; non-null values must be accepted channel names per the product contract.
- `minimumAmountMinor`: optional; uses integer smallest currency units.
- `maxGroups`: caps the **number of post-aggregation groups**, not input orders.

If channel comes from user input, use an agreed enum/allowlist rather than accepting arbitrary strings. Even though `Criteria.is(...)` binds values more safely than JSON concatenation, it does not replace business validation or authorization.

## 10. Transition step: MongoTemplate and the Aggregation DSL

A straightforward implementation builds a `List<AggregationOperation>` and appends only required stages. Optional filters can be combined into `Criteria` before creating `Aggregation.match`.

File `OrderReportQueryService.java`:

```java
package com.example.shop.orders;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class OrderReportQueryService {

    private final MongoTemplate template;

    public OrderReportQueryService(MongoTemplate template) {
        this.template = template;
    }

    public List<StatusRevenue> revenueByStatus(
            String permittedTenantId,
            OrderReportFilter filter) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid tenant");
        }
        if (filter == null) {
            throw new IllegalArgumentException(
                "Invalid filter");
        }

        // Fail-closed: do not drop the filter when status set is empty.
        if (filter.statuses().isEmpty()) {
            return List.of();
        }

        Criteria criteria = Criteria
            .where("tenantId").is(permittedTenantId)
            .and("archived").is(false)
            .and("createdAt")
                .gte(filter.fromInclusive())
                .lt(filter.toExclusive())
            .and("status").in(filter.statuses());

        if (filter.channel() != null) {
            criteria.and("channel").is(filter.channel());
        }
        if (filter.minimumAmountMinor() != null) {
            criteria.and("amountMinor")
                .gte(filter.minimumAmountMinor());
        }

        List<AggregationOperation> stages = new ArrayList<>();
        stages.add(Aggregation.match(criteria));
        stages.add(
            Aggregation.group("status")
                .count().as("orderCount")
                .sum("amountMinor").as("revenueMinor"));
        stages.add(
            Aggregation.project("orderCount", "revenueMinor")
                .and("_id").as("status")
                .andExclude("_id"));
        stages.add(
            Aggregation.sort(Sort.by(
                Sort.Order.desc("revenueMinor"),
                Sort.Order.asc("status"))));
        stages.add(Aggregation.limit(filter.maxGroups()));

        TypedAggregation<OrderDocument> aggregation =
            Aggregation.newAggregation(
                OrderDocument.class,
                stages.toArray(new AggregationOperation[0]));

        return template.aggregate(
            aggregation, StatusRevenue.class).getMappedResults();
    }
}
```

The example uses common Spring Data MongoDB DSL APIs, Java 17+, and configured Spring Data repository/data mapping. In a real project, check overloads/mapping in your Spring Data version and verify with integration tests.

### 10.1. Why is this a "dynamic pipeline" even with fixed group/sort?

The stage list currently has five fixed steps, yet **`Criteria` is assembled dynamically** from filters. That already adds value by eliminating repetitive annotation combinations. If the report later adds optional `$lookup`, `$facet`, or conditional projection branches, we can add `stages.add(...)` conditionally without duplicating the whole pipeline.

Example of adding an optional stage:

```java
// Illustrative only when the reporting contract requires an extra stage.
if (includeHighValueOnly) {
    stages.add(
        Aggregation.match(
            Criteria.where("revenueMinor").gte(100000L)));
}
```

**Must go in the right position**: this makes sense when placed **after `$group`**, where `revenueMinor` already exists. If placed before `$group`, that field does not yet exist on source orders and the filter fails. Whenever adding conditional stages, document clearly **which intermediate schema** the stage operates on.

### 10.2. TypedAggregation and field mapping

`Aggregation.newAggregation(OrderDocument.class, ...)` lets Spring Data know the input type to map field paths when building the pipeline. This helps when entities use `@Field` to customize BSON storage names.

However:

- Distinguish **source** fields (like `amountMinor`) from **stage output** fields (like `revenueMinor`).
- After `$group`, the schema no longer matches the source entity; field references must reflect the actual stage output.
- If you mix raw BSON/Jackson/`Document.parse(...)` `AggregationOperation`s with typed DSL stages, raw stages may not automatically apply property mapping the same way the DSL does. Inspect the actual pipeline sent to MongoDB.

### 10.3. When a direct template service is enough

An `OrderReportQueryService` like the above is already a solid solution if:

- Reports live in the application/query layer and do not need to appear on the domain repository.
- The team has a clean query-service boundary.
- Complex reporting endpoints coordinate across multiple repositories or collections.

There is no requirement to create a fragment solely "to be allowed to use `MongoTemplate`." A fragment is a choice to **preserve the repository API boundary** when that benefits project organization.

## 11. Running against the sample dataset

Querying two statuses in November 2026:

```java
OrderReportFilter filter = new OrderReportFilter(
    java.time.Instant.parse("2026-11-01T00:00:00Z"),
    java.time.Instant.parse("2026-12-01T00:00:00Z"),
    java.util.Set.of("PAID", "NEW"),
    null,
    null,
    10);

List<StatusRevenue> report =
    orderReportQueryService.revenueByStatus(
        "TENANT-A", filter);
```

Results sorted by descending `revenueMinor`:

```text
StatusRevenue("PAID", 4, 230000)
StatusRevenue("NEW",  2,  90000)
```

With `channel = "web"`:

```text
StatusRevenue("PAID", 3, 150000) // A-101, A-103, A-108
StatusRevenue("NEW",  1,  50000) // A-104
```

A-102 is PAID yet on channel `app`, so it is excluded in the `web` variant. A-105 is archived, A-107 CANCELLED is outside the status set, and B-201 belongs to the wrong tenant.

## 12. Encapsulation step: repository fragment

Suppose the team convention is that all `Order` queries are accessed through `OrderRepository`. We want callers to write:

```java
List<StatusRevenue> rows =
    orderRepository.revenueByStatus(permittedTenantId, filter);
```

while the pipeline-building code retains all the flexibility of `MongoTemplate`. A **fragment** is where that logic lives.

### 12.1. Defining the fragment interface

File `OrderReportOperations.java`:

```java
package com.example.shop.orders;

import java.util.List;

public interface OrderReportOperations {

    List<StatusRevenue> revenueByStatus(
        String permittedTenantId,
        OrderReportFilter filter);
}
```

This interface contains no `Aggregation`, `Criteria`, `Document`, or driver-coupled return types. Callers only see domain inputs and output DTOs.

### 12.2. Implementation with MongoTemplate

File `OrderReportOperationsImpl.java`:

```java
package com.example.shop.orders;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;

public class OrderReportOperationsImpl
        implements OrderReportOperations {

    private final MongoTemplate template;

    public OrderReportOperationsImpl(MongoTemplate template) {
        this.template = template;
    }

    @Override
    public List<StatusRevenue> revenueByStatus(
            String permittedTenantId,
            OrderReportFilter filter) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid tenant");
        }
        if (filter == null) {
            throw new IllegalArgumentException(
                "Invalid filter");
        }
        if (filter.statuses().isEmpty()) {
            return List.of();
        }

        Criteria scoped = Criteria
            .where("tenantId").is(permittedTenantId)
            .and("archived").is(false)
            .and("status").in(filter.statuses())
            .and("createdAt")
                .gte(filter.fromInclusive())
                .lt(filter.toExclusive());

        if (filter.channel() != null) {
            scoped.and("channel").is(filter.channel());
        }
        if (filter.minimumAmountMinor() != null) {
            scoped.and("amountMinor")
                .gte(filter.minimumAmountMinor());
        }

        List<AggregationOperation> stages = new ArrayList<>();
        stages.add(Aggregation.match(scoped));
        stages.add(
            Aggregation.group("status")
                .count().as("orderCount")
                .sum("amountMinor").as("revenueMinor"));
        stages.add(
            Aggregation.project("orderCount", "revenueMinor")
                .and("_id").as("status")
                .andExclude("_id"));
        stages.add(
            Aggregation.sort(Sort.by(
                Sort.Order.desc("revenueMinor"),
                Sort.Order.asc("status"))));
        stages.add(Aggregation.limit(filter.maxGroups()));

        TypedAggregation<OrderDocument> pipeline =
            Aggregation.newAggregation(
                OrderDocument.class,
                stages.toArray(new AggregationOperation[0]));

        return template.aggregate(
            pipeline, StatusRevenue.class).getMappedResults();
    }
}
```

This implementation intentionally repeats the **same logic** as `OrderReportQueryService` in section 10 to illustrate **two placement options for the pipeline**. **In a real application, do not maintain two copies simultaneously.** Move the logic from the service into the fragment, or extract a shared builder so both service and fragment delegate to **a single implementation**.

### 12.3. Wiring the fragment into the repository

Once you decide to use a fragment, `OrderRepository` extends the new interface:

```java
package com.example.shop.orders;

import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderReportOperations {

    // Keep the simple annotation method for comparison tests
    // during refactoring.
    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': ?1, 'archived': false } }",
        "{ '$group': { '_id': '$status', 'orderCount': { '$sum': 1 }, 'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'status': '$_id', 'orderCount': 1, 'revenueMinor': 1 } }"
    })
    List<StatusRevenue> summarizeStatus(
        String permittedTenantId, String status);
}
```

Spring Data repository composition discovers the fragment implementation by naming convention `<FragmentInterface>Impl`; here, `OrderReportOperationsImpl`. Place the class in a package scanned by repository scanning or register the bean explicitly per configuration. If you use multiple fragments or customize the `Impl` postfix, check actual discovery rules.

Do not create a class named `OrderRepositoryImpl` that implicitly backs all repository methods while bypassing modern fragment composition unless you have a specific reason and fully understand your Spring Data version's rules.

### 12.4. Responsibilities of each layer

| Layer | Responsibility |
| --- | --- |
| Controller | Accepts requests, normalizes HTTP input, never concatenates BSON |
| Application service | Authenticates user, derives permitted tenant, enforces product policies |
| `OrderRepository` | Exposes query API for the Order domain |
| `OrderReportOperations` | Business contract for optional reporting queries |
| `OrderReportOperationsImpl` | Builds and runs the pipeline, returns DTOs |
| `MongoTemplate` | Mapping, connections, coordinates MongoDB aggregation |
| MongoDB server | Executes pipeline, handles indexes, sort/group/join |

**Authorization does not come automatically from a fragment.** If users can invoke the report for another tenant, the application still leaks data. `permittedTenantId` must be derived from or checked against authorization before calling the repository.

### 12.5. Multiple fragments in one repository

Extra example outside the lesson:

```java
public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderReportOperations,
                OrderCustomWriteOperations {
}
```

Here `OrderCustomWriteOperations` represents another project-defined fragment, not a built-in API. You can separate **read/reporting** and **custom write** capabilities along clean boundaries; avoid letting one giant implementation take on every job just because they share a collection.

## 13. $facet: when a pipeline is no longer just three stages

New requirement: return **one page of revenue groups** and **total number of groups** to build pagination. Running two separate aggregations means the two reads may not observe the exact same data state under concurrent writes; `$facet` lets multiple sub-pipelines run on the same input stream inside one aggregation.

### 13.1. Illustrative MongoDB pipeline

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] },
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
    }
  },
  {
    $project: {
      _id: 0,
      status: "$_id",
      orderCount: 1,
      revenueMinor: 1
    }
  },
  {
    $facet: {
      rows: [
        { $sort: { revenueMinor: -1, status: 1 } },
        { $skip: 0 },
        { $limit: 1 }
      ],
      totalGroups: [
        { $count: "value" }
      ]
    }
  }
])
```

Conceptual result:

```javascript
[
  {
    rows: [
      { status: "PAID", orderCount: 4,
        revenueMinor: NumberLong(230000) }
    ],
    totalGroups: [ { value: 2 } ]
  }
]
```

**Two different counts**:

- `orderCount` inside `rows` counts **orders belonging to that status group**.
- `totalGroups.value` counts **the number of status groups after `$group`**, which is 2 here.

If `$facet` is placed **before `$group`**, the `totalGroups: [{$count:"value"}]` branch counts **input order documents** (6 here), not the number of groups. Placing stages in the right position matters more than just knowing the `$facet` keyword.

### 13.2. Why is $facet a signal to move to a template?

A long `@Aggregation` with `$facet` can still execute. However, when `rows` has optional sorting, skip/limit, toggles for extra summary branches based on filters, or changeable group keys, the annotation becomes hard to read and prone to output-mapping bugs.

With a template, you can:

- Build the **shared** stages (`$match`, `$group`, `$project`).
- Add `Aggregation.facet(...)` or application-defined raw stages per your Spring Data version's API.
- Map the result to a DTO holding `rows` and `totalGroups`, instead of trying to treat it as an Order entity.
- Test each branch independently, especially **no-data** cases.

When using a `$facet` pipeline, the output is normally one document holding **arrays of results**. Therefore, the output DTO changes and must be designed accordingly:

```java
public record FacetedOrderReport(
    java.util.List<StatusRevenue> rows,
    java.util.List<TotalGroups> totalGroups
) {
    public record TotalGroups(long value) {}
}
```

Do not assume `Page<StatusRevenue>` from a repository automatically knows the exact group total for complex aggregations. Even when Spring Data supports appending sort/limit via `Pageable` on a query method, that **does not mean** the framework automatically calculates `totalGroups` properly for every pipeline. You must define total calculation explicitly or design `Slice`/scrolling when totals are not needed.

### 13.3. When is facet unnecessary?

If the API only needs the top 10 revenue groups without `totalGroups` or multiple sub-tables, `$group → $sort → $limit` suffices. `$facet` complicates output and testing; only use it when it **solves a real requirement**.

Additionally, `$facet` is subject to MongoDB memory and output-size limits; never feed unfiltered orders and unbounded result sets into facet arrays expecting `allowDiskUse` to handle every constraint. Filter inputs early, cap `rows`, and measure on representative data.

## 14. $lookup: when multiple collections must be combined

For example, Order may need successful payment figures from a `payments` collection. When a reporting pipeline uses a join, the team should evaluate:

1. Should the data be embedded/denormalized for read requirements?
2. Can it be computed from a single collection using a maintained materialized field?
3. If using `$lookup`, do the join keys and tenant have supporting indexes?
4. Is the output multiple payments per order or only a summary number? Is `$unwind` needed?
5. Who owns this logic: the Order repository or a cross-domain reporting/query service?

### 14.1. Example $lookup with tenant key

```javascript
db.orders.aggregate([
  { $match: {
      tenantId: "TENANT-A",
      archived: false
  }},
  {
    $lookup: {
      from: "payments",
      let: {
        orderId: "$_id",
        tenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$orderId", "$$orderId"] },
                { $eq: ["$tenantId", "$$tenant"] }
              ]
            }
          }
        },
        { $match: { state: "CAPTURED" } },
        { $project: { _id: 0, amountMinor: 1 } }
      ],
      as: "capturedPayments"
    }
  }
])
```

The `$lookup` stage adds `capturedPayments` as an **array** on each Order; it does not multiply Order documents by itself. If you add `$unwind: "$capturedPayments"`, one Order with multiple payments expands into multiple output documents. If you then `$group` order totals without controlling duplication, the report can **double-count**.

In multi-tenant systems, matching solely by `orderId` without constraining payment tenant can leak data if IDs are not globally unique or data is corrupted. The example illustrates joining on **both orderId and tenantId**; the service must still verify the caller's tenant.

### 14.2. Where templates/fragments genuinely help

For `$lookup` pipelines with sub-pipelines varying by payment status and time window, putting long `let`/`$expr` expressions inside an annotation makes debugging painful. With a template, you can use suitable builders or a custom `AggregationOperation` for MongoDB stages not yet exposed in your DSL version.

Yet "using a custom stage" never means accepting arbitrary JSON from requests. Always control field paths, operators, variables, and collection names in the application layer.

### 14.3. Domain boundaries

If a report reads Orders, joins Payments, and groups by Shipments, a dedicated `BillingReportQueryService` may be clearer than `OrderRepository`. Use a fragment when **the contract genuinely belongs to the Order repository**.

## 15. Sort, Pageable, limits, and aggregated results

A key difference between simple repository queries and aggregations is that **sort/limit/skip** semantics depend on **stage position**.

### 15.1. Sort before or after group?

In the example:

```javascript
[
  { $match: { tenantId: "TENANT-A", archived: false } },
  { $group: {
      _id: "$status",
      revenueMinor: { $sum: "$amountMinor" }
  }},
  { $sort: { revenueMinor: -1, _id: 1 } },
  { $limit: 2 }
]
```

`$sort` and `$limit` apply to **group documents**, meaning "the two highest-revenue groups."

Pushing `$limit: 2` **before `$group`** only sums the **first two orders in the stream**, not all orders of the tenant. Never move a limit stage earlier just hoping to speed up a query; it corrupts the numbers.

### 15.2. Pageable does not automatically solve every aggregation problem

Spring Data MongoDB supports special parameters such as `Sort` and `Pageable` on certain repository aggregation methods. Still, you must check:

- **At which stage** is sorting attached, and does the sort key still exist after `$group`/`$project`?
- Do limits/pages apply to **source documents**, **groups**, or **arrays inside `$facet`**?
- Is the return type `List`, `Slice`, or another type supported by the framework in your running version?
- Where does the total group count come from? **Never assume** a `Page` object has an accurate count simply because the method accepts `Pageable`.

For dynamic pipelines and `$facet` outputs, build `$sort/$skip/$limit` explicitly in the right place alongside a clear DTO contract for total group count or a "has next page" flag.

### 15.3. Pagination needs deterministic sorting

For example, sorting by descending `revenueMinor` and ascending `status` avoids unpredictable ordering when two groups tie on total:

```javascript
{ $sort: { revenueMinor: -1, status: 1 } }
```

If grouping by a non-unique key or composite fields, add a deterministic, appropriate secondary key. On mutating data, `skip/limit` across multiple requests can still duplicate or drop groups as revenue totals shift; if reports require strict snapshot consistency across pages, design read timing, caching/materialization, or appropriate read concern/transactions.

### 15.4. Do not accept sort keys from users without validation

API boundary mistake:

```java
// ANTI-EXAMPLE: sortProperty taken straight from request.
Sort.by(sortProperty);
```

A better approach maps an allowlisted parameter:

```java
String sortField = switch (sortBy) {
    case "revenue" -> "revenueMinor";
    case "count"   -> "orderCount";
    case "status"  -> "status";
    default -> throw new IllegalArgumentException(
        "Unsupported sortBy");
};
```

This snippet lives in the query-building layer with a validated `String sortBy`; it does not yet create the sort stage. If an API lets users sort by a field **absent from post-projection results**, the query may fail or yield unintended order.

## 16. Mapping: source schema and result schema are two different contracts

Simple repository queries typically return `OrderDocument`. With aggregations, however, output can be:

- Documents containing only `status`, `orderCount`, `revenueMinor` after group/project.
- A document containing `rows[]` and `totalGroups[]` after facet.
- Documents containing `capturedPayments[]` after lookup.
- Documents whose `_id` is a composite object of multiple fields, not the original order ID.

Therefore, **never use the source entity as the report DTO** when the pipeline changes the data shape.

### 16.1. _id in $group is not the original primary key

```javascript
{
  $group: {
    _id: {
      status: "$status",
      channel: "$channel"
    },
    totalMinor: { $sum: "$amountMinor" }
  }
}
```

The resulting document has an **object** `_id`:

```javascript
{
  _id: { status: "PAID", channel: "web" },
  totalMinor: NumberLong(150000)
}
```

A DTO with `String id` cannot pretend this value is an order ID. Either define a DTO reflecting the nested group key, or `$project` it into top-level output fields:

```javascript
{
  $project: {
    _id: 0,
    status: "$_id.status",
    channel: "$_id.channel",
    totalMinor: 1
  }
}
```

This is also a signal to move to a template: when the result shape varies with the chosen group dimension, manage read models/mappers explicitly rather than hoping Spring Data guesses every projection.

### 16.2. Be careful with monetary values and BSON types

`$sum` can return different numeric types depending on input data and numeric type promotion. When `amountMinor` is valid BSON Int64, Java `long` works cleanly in the example. For Decimal128 amounts, mixed Double data, or sums that could overflow `long`, choose DTOs and converters matching your system's financial standards.

Never use `double` for money requiring exact precision. If legacy data stores numbers as Strings in the collection, `$sum` will not automatically interpret them as business numbers; inspect, migrate, or add explicit conversion expressions with clear error policies.

### 16.3. Empty results take multiple forms

- `$group` by `status` after a `$match` matching zero documents: usually **returns zero groups**.
- `$group` with `_id: null` in a pipeline with zero input documents: do not assume it returns a row with total 0.
- `$facet` can return one document with `rows: []` and `totalGroups: []`; a `$count` branch with no input returns an empty array.

Design DTOs for empty data; never call `get(0)` on `totalGroups` without checking for an empty list.

## 17. Transactions, execution options, and reactive read paths

Another reason to use a template is needing control over **how execution happens** beyond stage content. Still, picking a template does not automatically grant transactions or stronger read isolation.

### 17.1. AggregationOptions

When a pipeline has many groups or large sorts, the application may need to configure `AggregationOptions` per Spring Data version, such as `allowDiskUse`, collation, or cursor batch size:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

AggregationOptions options = AggregationOptions.builder()
    .allowDiskUse(true)
    .build();

Aggregation pipelineWithOptions =
    aggregation.withOptions(options);
```

Here `aggregation` is a previously constructed `Aggregation` variable. Verify APIs and supported options in your project's Spring Data/MongoDB versions. `allowDiskUse(true)` **does not mean every stage or facet array can exceed all limits**; you still need to cap input/output sizes and measure memory.

### 17.2. Transactions do not fix a flawed pipeline

An aggregation reading multiple collections with `$lookup` does not automatically share the guarantees of a multi-document transaction across every deployment/read concern. If a report requires a consistent snapshot, decide clearly:

- Do your MongoDB deployment and session/transaction manager support it?
- Which read concern is used, and how consistent must data across collections be?
- Will results be cached/materialized at a point in time or read live?
- Should mutations happening during the report be included?

Moving from an annotation to a template **does not automatically make these decisions**.

### 17.3. ReactiveMongoTemplate

In reactive applications, `ReactiveMongoTemplate` executes aggregations and returns a `Flux` of results:

```java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<StatusRevenue> revenueReactive(
        ReactiveMongoTemplate template,
        Aggregation pipeline) {
    return template.aggregate(
        pipeline, "orders", StatusRevenue.class);
}
```

This illustrative method belongs in an appropriate class, with a pipeline already containing the tenant filter. In reactive code, publishers run only when subscribed; manage cancellation, timeouts, backpressure, and never invoke blocking `MongoTemplate` on an event loop.

If the domain API needs a reactive repository fragment, define a fragment returning `Flux<StatusRevenue>` backed by `ReactiveMongoTemplate`. **Never** implement a reactive fragment by calling `block()` internally around synchronous `MongoTemplate`; that defeats non-blocking execution.

### 17.4. When output is very large

`MongoTemplate.aggregate(...).getMappedResults()` collects all results into a `List`. For reports returning hundreds of thousands of rows, consider `aggregateStream(...)`, reactive `Flux`, limits, or suitable pagination. Remember that streaming output does not reduce `$group`/`$sort` computation on the server if the pipeline still processes all data.

## 18. Integration tests: proving both approaches yield identical results

When refactoring from `@Aggregation` to a template/fragment, verify that **query semantics did not change**. A unit test mocking the repository to return two rows is insufficient: it fails to verify tenant `$match`, post-group `_id` mapping, totals, or Spring Data parameter binding.

Best practice is using an **isolated test MongoDB instance**, seeding real BSON data via the driver, and exercising both the annotation and the fragment. Then add tests for conditions the old annotation did not support.

### 18.1. JUnit 5 + @DataMongoTest

File `OrderRepositoryAggregationIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Set;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderRepositoryAggregationIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    private static Document order(
            String id, String tenantId, String status,
            String channel, long amountMinor,
            String createdAt, boolean archived) {
        return new Document("_id", id)
            .append("tenantId", tenantId)
            .append("status", status)
            .append("channel", channel)
            .append("amountMinor", amountMinor)
            .append("createdAt", Date.from(Instant.parse(createdAt)))
            .append("archived", archived);
    }

    private static OrderReportFilter filter(
            Set<String> statuses, String channel,
            Long minimumAmountMinor) {
        return new OrderReportFilter(
            Instant.parse("2026-11-01T00:00:00Z"),
            Instant.parse("2026-12-01T00:00:00Z"),
            statuses, channel, minimumAmountMinor, 10);
    }

    @BeforeEach
    void seed() {
        // Run ONLY on an isolated TEST MongoDB database.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("A-101", "TENANT-A", "PAID", "web",
                100000L, "2026-11-10T09:00:00Z", false),
            order("A-102", "TENANT-A", "PAID", "app",
                80000L, "2026-11-10T10:00:00Z", false),
            order("A-103", "TENANT-A", "PAID", "web",
                20000L, "2026-11-11T09:00:00Z", false),
            order("A-104", "TENANT-A", "NEW", "web",
                50000L, "2026-11-11T10:00:00Z", false),
            order("A-105", "TENANT-A", "PAID", "app",
                35000L, "2026-11-12T10:00:00Z", true),
            order("A-106", "TENANT-A", "NEW", "app",
                40000L, "2026-11-12T11:00:00Z", false),
            order("A-107", "TENANT-A", "CANCELLED", "web",
                60000L, "2026-11-13T09:00:00Z", false),
            order("A-108", "TENANT-A", "PAID", "web",
                30000L, "2026-11-14T09:00:00Z", false),
            order("B-201", "TENANT-B", "PAID", "web",
                999999L, "2026-11-13T09:00:00Z", false)
        ));
    }

    @Test
    void fixedAnnotationAggregationMatchesExpectedPaidGroup() {
        List<StatusRevenue> rows = repository.summarizeStatus(
            "TENANT-A", "PAID");

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 4L, 230000L));
    }

    @Test
    void fragmentProducesSameResultForPaidAndNew() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), null, null));

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 4L, 230000L),
            new StatusRevenue("NEW", 2L, 90000L));
    }

    @Test
    void dynamicChannelFilterDoesNotMixTenants() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), "web", null));

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 3L, 150000L),
            new StatusRevenue("NEW", 1L, 50000L));
    }

    @Test
    void amountThresholdAppliesBeforeGrouping() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), null, 40000L));

        assertThat(rows).containsExactly(
            new StatusRevenue("PAID", 2L, 180000L),
            new StatusRevenue("NEW", 2L, 90000L));
    }

    @Test
    void upperTimeBoundaryIsExclusive() {
        OrderReportFilter oneDay = new OrderReportFilter(
            Instant.parse("2026-11-11T00:00:00Z"),
            Instant.parse("2026-11-12T00:00:00Z"),
            Set.of("PAID", "NEW"), null, null, 10);

        List<StatusRevenue> rows =
            repository.revenueByStatus("TENANT-A", oneDay);

        assertThat(rows).containsExactly(
            new StatusRevenue("NEW", 1L, 50000L),
            new StatusRevenue("PAID", 1L, 20000L));
    }

    @Test
    void emptyStatusesMustNotExpandQueryToAllStatuses() {
        List<StatusRevenue> rows = repository.revenueByStatus(
            "TENANT-A", filter(Set.of(), null, null));
        assertThat(rows).isEmpty();
    }

    @Test
    void invalidStatusIsRejected() {
        assertThatThrownBy(
            () -> filter(Set.of("UNKNOWN"), null, null))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void reportDoesNotModifyStoredOrder() {
        repository.revenueByStatus(
            "TENANT-A",
            filter(Set.of("PAID", "NEW"), null, null));

        Document stored = template.getCollection("orders")
            .find(new Document("_id", "A-101"))
            .first();

        assertThat(stored).isNotNull();
        assertThat(stored.getString("status")).isEqualTo("PAID");
        assertThat(stored.getLong("amountMinor"))
            .isEqualTo(100000L);
        assertThat(stored.containsKey("revenueMinor")).isFalse();
        assertThat(stored.containsKey("orderCount")).isFalse();
    }
}
```

**Important warning:** `collection.deleteMany(new Document())` deletes **the entire `orders` collection in the connected database**. Always use an **isolated test** MongoDB, such as Testcontainers with dedicated test connection settings. Never run this test code on production or shared databases.

The example uses the common Spring Boot 3.x `@DataMongoTest` package; package/test slices may change across major versions. Check your active dependency/test configuration and ensure **repository scanning detects `OrderReportOperationsImpl`**. `@DataMongoTest` may not load ordinary `@Service` beans; this test invokes the fragment via the repository to verify wiring without loading `OrderReportQueryService` from section 10.

### 18.2. What bug does each test catch?

| Test | Bug it can catch |
| --- | --- |
| `fixedAnnotationAggregation...` | Annotation binds wrong status/tenant or wrong group/project mapping |
| `fragmentProducesSameResult...` | Fragment wired wrongly or incorrect sum across two statuses |
| `dynamicChannelFilter...` | Channel filter dropped or tenant B leaked |
| `amountThreshold...` | Amount threshold applied to post-group `revenueMinor` instead of pre-group `amountMinor` |
| `upperTimeBoundaryIsExclusive` | Using `lte(to)` instead of `lt(to)` or UTC date calculation bug |
| `emptyStatuses...` | Empty status set accidentally expands to all statuses |
| `invalidStatus...` | API allows statuses outside allowlist |
| `reportDoesNotModifyStoredOrder` | Confusing aggregation output with source entities or write commands |

### 18.3. Debugging using pipeline prefixes

When totals miss expectations, do not replace the whole pipeline at once. Run incrementally:

```javascript
// 1. Check matching ORDER count after $match:
db.orders.aggregate([
  { $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] }
  }},
  { $count: "matchedOrders" }
])
// [{ matchedOrders: 6 }]

// 2. Add $group, without sort/limit yet:
db.orders.aggregate([
  { $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] }
  }},
  { $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
  }}
])
// PAID: 4/230000; NEW: 2/90000 (order not guaranteed).
```

With a template, you can take the built `AggregationOperation`s and execute a prefix pipeline. If `$match` hits 6 documents as expected while totals are wrong, inspect BSON types/values of `amountMinor` and `$group` logic. If the prefix returns 5 documents, inspect tenant checks, `archived`, or time filters before touching accumulators.

### 18.4. Extended test matrix to cover

| Scenario | Expectation |
| --- | --- |
| Tenant with no orders | No dummy groups created |
| Order from another tenant with same status | Contributes nothing to results |
| `archived=true` | Excluded from active revenue |
| Missing `archived` in legacy data | Not silently treated as false; needs migration/compatibility policy |
| `amountMinor` null/String or oversized | Explicit validation and numeric handling, never silently mis-summed |
| `channel` null/non-existent | Never silently treated as all channels when a specific channel is requested |
| Empty status set | Returns empty, fail-closed |
| Timestamp equal to `toExclusive` | Excluded due to exclusive upper bound |
| Two groups with equal total | Deterministic secondary sort key |
| `$facet` with zero groups | `rows: []`, `totalGroups` may be an empty array |
| `$lookup` with multiple payments per order | No double counting of orders after unwind/group |
| Fragment not discovered | Context wiring test fails; fix package, postfix, or bean registration |
| Data changes during pagination | Appropriate consistency strategy defined |

## 19. Performance: moving code does not change the MongoDB plan

For an identical BSON pipeline and identical options, MongoDB neither knows nor cares whether it came from a repository annotation, `MongoTemplate`, or a fragment. Significant differences usually come from **generating a different pipeline**, mapping overhead, Java resource usage, or execution configuration.

### 19.1. Candidate indexes

For frequent filters by tenant, archive flag, status, and time window:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    archived: 1,
    status: 1,
    createdAt: 1
  },
  { name: "idx_tenant_archive_status_date" }
)
```

When channel is always filtered, another candidate to evaluate:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    archived: 1,
    channel: 1,
    status: 1,
    createdAt: 1
  },
  { name: "idx_tenant_archive_channel_status_date" }
)
```

These are **candidate indexes**, not a mandate to create both in every project. Field order, selectivity, tenant count, channel frequency, index size, and write cost all factor into the choice. Because `createdAt` is a range predicate, keys placed after it may not be used as expected for some query patterns. Measure against real workloads.

If `$lookup` reads payments by tenant/order/state, consider an index on `payments` such as `{tenantId:1, orderId:1, state:1}`, then run `explain`. Whether `$expr` joins can leverage indexes depends on MongoDB version, expression shape, and data distribution.

### 19.2. Explaining the real pipeline

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      archived: false,
      status: { $in: ["PAID", "NEW"] },
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
    }
  },
  { $sort: { revenueMinor: -1, _id: 1 } }
])
```

Observe:

- `totalDocsExamined` and `totalKeysExamined` where provided by the plan.
- Number of documents returned by `$match` and groups after `$group`.
- Any collection scans, index scans, or memory-heavy sort stages.
- Execution time, resource usage, and output document counts.
- Whether `$facet`/`$lookup` pulls excessive data or multiplies documents.

`$sort` **on aggregated `revenueMinor` after `$group`** cannot automatically reuse an index order on source `amountMinor`. Indexes help narrow data entering the pipeline, while group/sort over aggregates still carry their own cost.

### 19.3. Do not assume @Aggregation itself is slow

If an annotation emits valid, stable BSON, rewriting it verbatim into the DSL is not an optimization. Ask:

1. How many documents does the read path scan?
2. Which stage is the bottleneck?
3. Can `$match` be pushed earlier on source fields?
4. Are `$push` arrays or `$facet` results growing too wide?
5. Can pre-aggregated values be stored for read-heavy workloads when business rules permit?
6. Are projections needed to trim data read or returned?

If the answers call for changing the pipeline structure to optimize it, a **template helps you experiment and reuse stages**; the speedup comes from the **new BSON design**, not from the Java API name.

## 20. Refactoring safely from @Aggregation to a fragment

A path that avoids accidental semantic regressions:

1. **Freeze the output contract**: record the DTO, ordering, numeric types, empty handling, and tenant predicates.
2. **Write integration tests for the legacy annotation** over BSON data with multiple tenants, archived rows, and time boundaries.
3. **Port the pipeline to the template** with equivalent `AggregationOperation`s in the same order; verify BSON and output.
4. **Extract dynamic filters** into a validated type with fail-closed rules and allowlists for sort/status/channel.
5. **Place into a repository fragment** if the API belongs on the Order domain; avoid duplicating implementations.
6. **Switch callers** to the new method, keeping the legacy annotation method temporarily during verification if needed.
7. **Run side-by-side comparison tests** of both paths over identical data, including counts, sums, and order.
8. **Measure explain/performance** on representative data, checking indexes and execution options.
9. **Remove the legacy annotation pipeline** once all callers migrate, preventing two diverging report definitions from silently coexisting.
10. **Monitor post-rollout**: aggregation error rates, query latency, docs examined, heap, and reconciliation discrepancies.

### 20.1. Do not extract helpers just to hide syntax

A helper like `buildAggregation(filter)` adds value when it consolidates **genuinely reusable logic**, not when it scatters a five-line pipeline across ten classes. Name helpers after business concepts (`activeOrdersOfTenant`, `sumAmountByStatus`, `revenueGroupSort`...), while avoiding building an overly generic query framework for a single endpoint.

### 20.2. When should repository annotations and fragments coexist?

Simple `@Aggregation` methods can stay in the repository alongside a fragment for complex queries **when they serve distinct contracts**. There is no need to migrate every annotation to a template in one sweep. The goal is placing code **where it matches variability and responsibility**, not mechanically forcing every method into one pattern.

## 21. Common errors and how to fix them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Annotation grows to hundreds of lines, copied per endpoint | Pipeline has optional stages/filters yet stays inside `@Aggregation` | Move to template, extract meaningful operations, consider fragment |
| Migrated to template yet numbers match and query stays slow | Changed Java API without changing BSON/indexes | Use `explain`, optimize stages and schema instead of expecting automatic speedups |
| Fragment not wired into repository | Wrong `Impl` postfix, package scanning, or bean config | Check fragment interface/implementation and context-loading integration tests |
| `$group` returns `_id` as status while DTO expects order ID | Confused group key with source entity `@Id` | Use dedicated result DTO and explicit projection |
| Report includes another tenant's orders | `$match` missing tenant or optional OR escaped constraint | Put mandatory tenant in outer AND and add anti-leak tests |
| Empty `statuses` shows every status | Service dropped filter on empty input | Fail-closed or explicitly require a permitted ALL value |
| Totals differ between annotation and fragment | Wrong stage order, differing date/archive filter, or mismatched field mapping | Run comparison tests on identical BSON and pipeline prefixes |
| Pre-group `$limit` depresses revenue | Limited source documents instead of groups | Place limit after `$group`/`$sort` per business intent |
| Report page has right rows yet wrong `totalCount` | Counted orders instead of groups, or omitted page count | Post-group `$facet` with `$count` in the right place |
| `Pageable` present without accurate group total | Assumed framework auto-builds counts for all aggregations | Explicitly define `Slice`/facet/count pipeline |
| Raw stage ignores `@Field` names | Mixed up Java property names and BSON names | Use typed DSL where appropriate; inspect pipeline sent to server |
| `$lookup` inflates order counts | Unwound payments array then grouped without distinct check | Design cardinality per order and tenant keys |
| Client-supplied sort key makes query invalid | Unwhitelisted sort field or field dropped before sort stage | Map sort keys explicitly and check intermediate schema |
| Report shows NaN/wrong revenue types | String/Double/null BSON values, legacy data | Validate, apply explicit conversion policy, use proper monetary types |
| Reactive fragment method calls `block()` | Mixed blocking with reactive | Use `ReactiveMongoTemplate` and return `Flux`/`Mono` |
| Mock tests pass yet pipeline fails on server | Only mocked `MongoTemplate`, skipped real mapping/operators | Testcontainers/real MongoDB, assert both results and wiring |
| Early `$facet` causes overly broad scan | Didn't filter data before branching | `$match` early and check limits/performance |
| `allowDiskUse` enabled yet facet still fails | Separate facet/output limits apply | Reduce group count, trim output, redesign pipeline |

## 22. Tool selection checklist

Before choosing where to put a pipeline, ask yourself:

1. **Is the pipeline fixed?** If you only bind values into fixed stages, `@Aggregation` may suffice.
2. **Are conditions optional or structurally variable?** If yes, `MongoTemplate`/`Aggregation` DSL is usually easier to maintain.
3. **Is the output schema stable?** If not, you may need multiple DTOs or a controlled flexible contract.
4. **Are there multiple `$facet` or `$lookup` branches?** Consider DSL/trusted raw operations and test each branch independently.
5. **Should callers see the template or only the domain repository?** For a unified repository API, choose a fragment.
6. **Does the report belong to one domain or span multiple domains?** For broad cross-domain reports, a dedicated query service may be cleaner than an entity fragment.
7. **What mandatory constraints exist?** Tenant, soft-delete, permissions, time bounds, and valid statuses must hold in every branch.
8. **Does pagination apply to source orders, groups, or facet arrays?** Put `$sort/$skip/$limit` in the right place and verify group total calculation.
9. **Are execution options needed?** Identify read concern, disk use, collation, stream/reactive needs, and infrastructure support.
10. **Do regression tests run against real BSON?** Compare the old annotation and new fragment on numbers, target sets, and ordering.
11. **Have execution plans been measured?** Verify indexes and examined counts before claiming a refactor improved performance.
12. **Are two identical pipelines being maintained?** Extract shared logic or remove the old path after migration.

### 22.1. Quick decision matrix

| Situation | Usually sensible choice |
| --- | --- |
| Three fixed stages, only tenant and status parameterized | `@Aggregation` |
| Dynamic filters on channel/amount/time and optional sorting | `MongoTemplate` + `Aggregation` |
| Dynamic pipeline yet callers should only see `orderRepository.report(...)` | `MongoTemplate` **inside a repository fragment** |
| Report joining three domains and returning varied structures | Dedicated reporting/query service |
| Simply finding orders matching an item predicate without reshaping arrays | Derived query/`@Query`/`Criteria.elemMatch` may be simpler than aggregation |
| Need better performance while fixed pipeline is currently slow | Analyze `explain`/indexes/schema first; **do not switch Java APIs just for speed** |

## 23. Applied exercise

A sales platform has a `sales` collection:

```javascript
{
  _id: "SALE-001",
  tenantId: "TENANT-X",
  state: "PAID",
  channel: "web",
  currency: "VND",
  grossMinor: NumberLong(250000),
  occurredAt: ISODate("2026-11-10T09:00:00Z"),
  deleted: false
}
```

Initially, the team has a fixed `@Aggregation` repository method: grouping by `state` and calculating `saleCount`, `grossTotal` within a tenant.

Later, product requirements add:

- Optional time window with `fromInclusive` and `toExclusive`.
- Optional filtering by `channel` or `currency`; only sum amounts of the same currency, never mixing VND and USD without conversion.
- Grouping by either `state` or `channel`.
- Paginating **result groups** along with a total group count field.
- Never including `deleted=true` or other tenants in results.
- Some reports must join a `refunds` collection.

**Tasks:**

1. Write the simple `@Aggregation` version with only tenant filter, `deleted=false`, group, and project.
2. Name at least three signals why continuing to add separate annotation variants per combination is no longer practical.
3. Define `SalesReportFilter` validating time window, status set, currency, and page size bounds.
4. Build a dynamic `List<AggregationOperation>` with mandatory tenant/deleted filters, optional filters, allowlisted group key, and allowed sort fields.
5. Write fragment `SalesReportOperations` and `SalesReportOperationsImpl`, wiring them into `SalesRepository`.
6. Add `$facet` **after grouping** to produce `rows[]` and `totalGroups[]`. Explain why counting before grouping returns a different number.
7. When joining refunds by `saleId`, add a tenant constraint inside `$lookup`; propose how to prevent double-counting sales with multiple refunds.
8. Define the post-group output DTO and the facet wrapper DTO. Do not use `SalesDocument` as the report output entity.
9. Seed at least one other-tenant sale, one deleted sale, one foreign-currency sale, and one out-of-window sale; verify totals remain accurate.
10. Compare `explain` before and after creating an appropriate index, checking examined document counts and group/sort costs.
11. Try using repository `@Aggregation` with `Pageable` and evaluate whether it supplies an accurate **total group count** for this API contract.
12. Plan a two-phase refactor, ensuring comparison tests verify the legacy annotation against the new fragment before removing the old path.

**Guidance:** enforce the exact same tenant/deleted filter at the initial `$match` stage of the pipeline; never concatenate raw JSON strings supplied by users. Group keys must come from an allowlist, not arbitrary field names. Currencies must be grouped separately or converted at a business-verified rate and timestamp. `$facet` is only necessary when the API requires multiple result branches; it is not mandatory for every report.

## 24. References

- Spring Data MongoDB — [Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): repository queries/aggregations and parameters.
- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): building pipelines with the Aggregation DSL, mapping, and expressions.
- Spring Data MongoDB — [Aggregation API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/Aggregation.html): `match`, `group`, `project`, `sort`, `limit` builders.
- Spring Data Commons — [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): repository fragments, interfaces, and implementation discovery.
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): stage semantics and document streams.
- MongoDB Manual — [`$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/): sub-pipelines and result structure.
- MongoDB Manual — [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): joins and sub-pipelines.
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): stage ordering and optimizer.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): reading query plans and execution statistics.

## Key takeaways

**Keep `@Aggregation` when pipelines are fixed, compact, and easy to understand. Move to `MongoTemplate` when pipeline structure or conditions become dynamic, branched, and require fine control over the DSL, DTOs, options, or stage-by-stage debugging. Use a repository fragment when you want to wrap that pipeline behind a clean domain repository API.** Templates and fragments work together: a fragment houses a template rather than being a different server query mechanism. Safe migration requires preserving tenant/access filters, defining post-`$group`/`$facet` output schemas, testing on real BSON, cross-checking numbers with the legacy path, and measuring `explain`. **Do not switch Java APIs expecting MongoDB to run faster when the BSON pipeline itself is unchanged.**
