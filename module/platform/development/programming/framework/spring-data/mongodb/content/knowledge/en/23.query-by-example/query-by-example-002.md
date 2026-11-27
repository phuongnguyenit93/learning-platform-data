# Matching All or Any Selected Fields

## 1. The Problem: Multiple Search Criteria Without Writing Dozens of Query Methods

A product management application uses **Spring Data MongoDB**. The search screen lets staff enter several criteria: category, brand, product name, and active status. Users may want one of two behaviors:

- **Match all (AND):** return only products that both belong to the `keyboard` category **and** have brand `ACME`.
- **Match any (OR):** return products that belong to the `keyboard` category **or** have brand `ACME`; a product only needs to satisfy one of the two.

If you write dedicated repository methods like `findByCategoryAndBrand`, `findByCategoryOrBrand`, `findByCategoryAndActive`, and `findByBrandOrActive`, the number of combinations grows rapidly as more search inputs are added. One approach is to use **Query by Example (QBE)**:

1. Create a **probe** — a domain object containing the values to search for.
2. Create an **ExampleMatcher** — describing how comparisons are made, which properties are considered, and how conditions are combined.
3. Create an **Example** from the probe and matcher.
4. Pass the Example to a repository or convert it into `Criteria` for use with `MongoTemplate`.

This lesson belongs to the **Query by Example** chapter of the **SPRING_DATA_MONGODB** module, where we practice connecting, mapping documents, and querying MongoDB via repositories/`MongoTemplate`, while also evaluating indexes, aggregations, transactions, reactive access, testing, and performance.

**Key takeaway to remember immediately:** `ExampleMatcher.matchingAll()` requires **all selected predicates** to be true; `ExampleMatcher.matchingAny()` requires **at least one selected predicate** to be true. Both only act on properties actually included in the Example, and do not automatically infer "selected fields" from a UI form or Java variable names.

## 2. Four Concepts That Make Up Query by Example

| Component | Role | Example |
| --- | --- | --- |
| **Probe** | Sample object with populated properties | `category="keyboard", brand="ACME"` |
| **ExampleMatcher** | AND/OR, ignore paths, string/null handling | `matchingAny().withIgnorePaths("id")` |
| **Example<T>** | Combines probe and matcher into a query specification | `Example.of(probe, matcher)` |
| **QueryByExampleExecutor** | Executes the Example through a repository | `repository.findAll(example)` |
| **Criteria.byExample** | Combines an Example with a `MongoTemplate` query | `Criteria.byExample(example)` |

`ExampleMatcher.matching()` is typically equivalent to **matching all** by default. When you explicitly need OR, choose `matchingAny()` rather than replacing it with per-field `withMatcher(...)` calls. `withMatcher(...)` is used to configure **how a single property is compared**, not to choose OR or AND joining between properties.

QBE is convenient for simple conditions derived from domain objects. It is **not a full query language** for MongoDB and does not replace nested `$and`/`$or` expressions, range queries, `$elemMatch`, aggregations, or transactions.

## 3. Data Model and Illustrative Product Dataset

Suppose the `products` collection stores documents with a string ID, tenant info, name, category, brand code, and active status. We use Java names that differ from BSON names on a few fields to make mapping clear.

### 3.1. Java Entity

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "products")
public record ProductDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("tenant_id")
    String tenantId,

    String name,
    String category,

    @Field("brand_code")
    String brand,

    Boolean active,

    @Field("price_cents")
    Long priceCents
) {}
```

This is a Java 17+ record for simple read/write examples:

- `id` is stored in BSON `_id` as a string via `@MongoId(FieldType.STRING)`.
- `tenantId` in Java is stored as `tenant_id` in MongoDB.
- `brand` in Java is stored as `brand_code`.
- `priceCents` is stored as `price_cents`; using the smallest currency unit keeps monetary values as integers, though units and currencies must be consistent in a real application.
- `active` is a **`Boolean` wrapper**, not a primitive `boolean`. A `null` value means **do not include status in the probe**; `false` remains a valid search value.

If you use primitive `boolean active`, a newly constructed object has `false` and QBE may include `active=false` in the query even when the user never selected a status. This rule is analyzed in section 8.

### 3.2. Test Dataset

| ID | Tenant | Category | Brand | Active | Notes |
| --- | --- | --- | --- | --- | --- |
| `p-01` | `t-A` | `keyboard` | `ACME` | true | Matches both |
| `p-02` | `t-A` | `keyboard` | `ZEN` | true | Matches category only |
| `p-03` | `t-A` | `mouse` | `ACME` | true | Matches brand only |
| `p-04` | `t-A` | `mouse` | `ZEN` | false | Matches neither |
| `p-05` | `t-A` | `keyboard` | `ACME` | false | Matches both |
| `p-06` | `t-B` | `keyboard` | `ACME` | true | Same criteria but **different tenant** |

The repository QBE examples below assume data is **written via Spring Data MongoDB** with default mapping, so documents may carry a `_class` type hint. If you manually insert data via `mongosh` without `_class`, a **typed Example** may not match due to the Java type restriction; see section 12.

Illustrative BSON example for the first product:

```javascript
{
  _id: "p-01",
  tenant_id: "t-A",
  name: "Mechanical Keyboard A",
  category: "keyboard",
  brand_code: "ACME",
  active: true,
  price_cents: NumberLong("1850000")
  // When Spring Data saves with default type hints, _class may be present.
}
```

Logically equivalent BSON queries for the two modes:

```javascript
// AND: only products satisfying both category and brand.
db.products.find({
  category: "keyboard",
  brand_code: "ACME"
});

// OR: products satisfying at least one criterion.
db.products.find({
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
});
```

These are illustrative examples to explain logic. The actual query from **typed QBE** may add a `_class` constraint; the BSON shape is not guaranteed to match these shell commands byte-for-byte.

## 4. `matchingAll()`: All Selected Properties Must Match

Suppose the user enters:

```text
Category = keyboard
Brand    = ACME
Mode     = All conditions
```

We create a probe with exactly two non-null properties:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

ProductDocument probe = new ProductDocument(
    null,       // id
    null,       // tenantId: do not place inside optional QBE
    null,       // name
    "keyboard", // category
    "ACME",     // brand
    null,       // active
    null        // priceCents
);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths(
        "id", "tenantId", "name", "active", "priceCents"
    );

Example<ProductDocument> example = Example.of(
    probe, matcher
);
```

Logically, aside from any type constraint, the predicates are:

```javascript
{
  category: "keyboard",
  brand_code: "ACME"
}
```

Results for the dataset in section 3: `p-01`, `p-05`, and `p-06`. All three documents satisfy **both** fields. `p-06` belongs to a different tenant and is still returned if this query has no mandatory tenant condition; that is a security bug if used directly in a customer-facing API.

### 4.1. Default Is Also Matching All

```java
ExampleMatcher matcherA = ExampleMatcher.matching();
ExampleMatcher matcherB = ExampleMatcher.matchingAll();
```

Both express "all values included in the probe must match" by default. Writing `matchingAll()` explicitly is useful when a service switches between AND and OR modes.

**Do not** assume the matcher checks every property of the entity. `null` properties are ignored by default; properties listed in `withIgnorePaths(...)` are also ignored, even if they have values.

## 5. `matchingAny()`: At Least One Selected Property Must Match

Use the **same probe** but change the matcher:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

ExampleMatcher anyMatcher = ExampleMatcher.matchingAny()
    .withIgnorePaths(
        "id", "tenantId", "name", "active", "priceCents"
    );

Example<ProductDocument> anyExample = Example.of(
    probe, anyMatcher
);
```

Equivalent meaning:

```javascript
{
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
}
```

Results for the dataset:

- `p-01`: matches both → returned.
- `p-02`: matches category → returned.
- `p-03`: matches brand → returned.
- `p-04`: matches neither criterion → not returned.
- `p-05`: matches both → returned.
- `p-06`: matches both but belongs to another tenant → **still returned unless tenant is locked outside the OR**.

### 5.1. Direct Comparison

| Probe | Mode | Predicate Logic | Matching Products in t-A |
| --- | --- | --- | --- |
| category=keyboard, brand=ACME | `matchingAll` | category **AND** brand | `p-01`, `p-05` |
| category=keyboard, brand=ACME | `matchingAny` | category **OR** brand | `p-01`, `p-02`, `p-03`, `p-05` |
| Only category=keyboard | Both | category | `p-01`, `p-02`, `p-05` |
| Only brand=ACME | Both | brand | `p-01`, `p-03`, `p-05` |

The table restricts results to tenant `t-A` **assuming a separate tenant condition exists**. Plain QBE does not apply a tenant filter automatically.

### 5.2. With One Predicate, ALL and ANY Return the Same Results

If the probe only has `category="keyboard"` and all other properties are null/ignored, both AND and OR over **one** predicate are identical. This is an important test case: do not conclude the mode switch is broken just because you tested with a single field.

### 5.3. ANY Does Not Mean Fuzzy Matching or Ranking

`matchingAny()` only joins predicates with OR. It does not:

- Score a product matching two fields higher than a product matching one field.
- Automatically sort results by the number of satisfied criteria.
- Automatically apply fuzzy search, full-text search, or semantic similarity.
- Automatically paginate, cap document count, or protect results from duplicates/data leaks.

If you need scoring, relevance ranking, or ordering by the number of matched predicates, consider aggregation `$addFields`/`$project` and `$sort` or a dedicated search engine.

## 6. Executing QBE via `MongoRepository`

### 6.1. Repository

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<ProductDocument, String> {}
```

In common Spring Data MongoDB versions, `MongoRepository` provides **Query by Example** capabilities, so you can call:

```java
Iterable<ProductDocument> allMatches =
    productRepository.findAll(
        Example.of(probe, ExampleMatcher.matchingAll())
    );

Iterable<ProductDocument> anyMatches =
    productRepository.findAll(
        Example.of(probe, ExampleMatcher.matchingAny())
    );
```

Both calls use the same probe with other values set to null. In production code, still use a matcher that explicitly defines `withIgnorePaths(...)` and enforces tenant checks. `findAll(example)` does **not** apply authorization or result limits by default.

Depending on the Spring Data version, the return type of `findAll(Example<S>)` may be more specific such as `List<S>`; assigning to `Iterable<ProductDocument>` is a straightforward usage. For repositories that do not extend built-in QBE APIs, use `QueryByExampleExecutor<T>` per the Spring Data Commons contract.

### 6.2. Counting and Checking Existence

```java
long count = productRepository.count(example);
boolean exists = productRepository.exists(example);
```

`count` and `exists` evaluate the same set of Example predicates, but do not turn a read-then-write into a transaction. If the result is used to decide whether to create a unique record, you still need a unique index and appropriate atomic write/transaction logic; do not use `exists(example)` as your sole concurrency guard.

### 6.3. Pagination and Sorting

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<ProductDocument> page = productRepository.findAll(
    example,
    PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id")
        )
    )
);
```

For large datasets, paginate and sort deterministically (ID breaks ties when names are equal). `Page` may require an extra count query; when you only need "Load more", `Slice`/scrolling or a dedicated API may fit better depending on version.

### 6.4. Never Expose QBE as an Unbounded Public Endpoint

If a web client is allowed to send an empty probe, `findAll(example)` can become a very broad query (or leave only a type condition). You must:

- Require at least one valid filter criterion.
- Always enforce tenant/authorization conditions outside any optional OR group.
- Cap page sizes and return only permitted fields.
- Control string matchers because `CONTAINING` often generates regexes that struggle to use indexes.
- Never let clients pass an arbitrary entity object with all properties as the probe.

## 7. Executing via `MongoTemplate` to Combine Other Conditions

Spring Data MongoDB supports converting an `Example` into `Criteria`:

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<ProductDocument> findByExample(
    MongoTemplate template,
    Example<ProductDocument> example
) {
    Query query = Query.query(
        Criteria.byExample(example)
    );
    query.limit(30);

    return template.find(
        query,
        ProductDocument.class
    );
}
```

An equivalent form in supported versions is `new Criteria().alike(example)`. When you need extra conditions such as `tenantId`, numeric ranges, or mandatory business statuses, `MongoTemplate` lets you construct `Criteria` clearly.

**Note:** QBE generated by `Criteria.byExample(...)` preserves the `matchingAll`/`matchingAny` choice from the Example and may add type constraints. `MongoTemplate` does not automatically convert `matchingAny` into `matchingAll`.

## 8. How Are "Selected Fields" Determined?

QBE does not know which checkboxes the user ticked in the UI. It infers predicates from **property values** and `ExampleMatcher` rules.

### 8.1. Default: `null` Is Ignored

Suppose:

```java
ProductDocument probe = new ProductDocument(
    null, null, null, "keyboard", null, null, null
);
```

Even though the entity has seven properties, the query mainly uses `category="keyboard"` because the other properties are null (plus a possible type restriction). By default, QBE does not interpret `null` as "find documents with a null field".

### 8.2. Primitives Are Included in the Probe Even If the User Entered Nothing

If a model uses:

```java
public class ProductProbeWithPrimitive {
    public String category;
    public boolean active; // default false
    public int stock;       // default 0
}
```

and only sets `category="keyboard"`, QBE may still add `active=false` and `stock=0` predicates. With `matchingAll`, results are wrongly narrowed; with `matchingAny`, they can be wrongly broadened because documents that merely have `active=false` or `stock=0` also match.

Solutions:

- Use wrapper types `Boolean`/`Integer`/`Long` in the probe if you need to distinguish "not selected" from default values.
- Or use `withIgnorePaths("active", "stock")` when those properties must not participate in the query.
- Never bind a full entity with primitive fields directly to a QBE form without control.

### 8.3. `withIgnorePaths` Excludes Fields Even When Populated

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withIgnorePaths("id", "tenantId", "priceCents");
```

If the probe contains `id="p-01"` while the matcher ignores `id`, the ID does **not** become a predicate. `withIgnorePaths` does not automatically act as a complete "allowlist": any other populated property can still participate. Therefore, build the probe **intentionally** from validated fields rather than copying an entire HTTP-submitted entity.

### 8.4. Choosing the Match Mode and Choosing Properties Are Two Different Decisions

| Decision | API | Effect |
| --- | --- | --- |
| Which properties enter the query | Non-null probe values, `withIgnorePaths` | Predicate set |
| How predicates are joined | `matchingAll` / `matchingAny` | AND or OR |
| How string values are matched | `withStringMatcher` / `withMatcher` | Exact, starts, contains... |
| Case sensitivity | `withIgnoreCase` or per-field matcher | Case-sensitive or insensitive |
| Explicit null handling | `withIncludeNullValues` | Changes predicates, with MongoDB caveats |

A UI form change may require updating **both axes**: which fields are selected and how they are joined. Do not simply switch to `matchingAny` and expect empty fields to vanish across every model type.

## 9. Complete Service Example: ALL/ANY with Mandatory Tenant Filter

This is the recommended pattern when an application has multi-tenant data. The user chooses AND or OR for **optional search fields**, while the tenant condition is **always mandatory**.

### 9.1. Request DTO

```java
public record ProductSearchRequest(
    String name,
    String category,
    String brand,
    Boolean active,
    boolean matchAny
) {}
```

`matchAny` is a request/service option, **not a field on `ProductDocument`**. Do not put this property into the probe. `tenantId` must come from a trusted security context or authenticated internal call—never trust a tenant ID freely modified by the client.

### 9.2. Code Applying Optional AND/OR with Mandatory Tenant AND

```java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final MongoTemplate template;

    public ProductSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<ProductDocument> search(
        String trustedTenantId,
        ProductSearchRequest request
    ) {
        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }

        String name = normalize(request.name());
        String category = normalize(request.category());
        String brand = normalize(request.brand());
        Boolean active = request.active();

        int selected = (name != null ? 1 : 0)
            + (category != null ? 1 : 0)
            + (brand != null ? 1 : 0)
            + (active != null ? 1 : 0);

        if (selected == 0) {
            throw new IllegalArgumentException(
                "At least one search criterion must be provided"
            );
        }

        ProductDocument probe = new ProductDocument(
            null,   // id
            null,   // tenantId: do not place inside OR group
            name,
            category,
            brand,
            active,
            null    // priceCents: not used on this screen
        );

        ExampleMatcher matcher = request.matchAny()
            ? ExampleMatcher.matchingAny()
            : ExampleMatcher.matchingAll();

        matcher = matcher.withIgnorePaths(
            "id", "tenantId", "priceCents"
        );

        Example<ProductDocument> example =
            Example.of(probe, matcher);

        Criteria requiredTenant =
            Criteria.where("tenantId").is(trustedTenantId);

        Criteria optionalSearch =
            Criteria.byExample(example);

        Query query = Query.query(
            new Criteria().andOperator(
                requiredTenant,
                optionalSearch
            )
        );

        query.with(
            Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
            )
        );
        query.limit(30);

        return template.find(
            query,
            ProductDocument.class
        );
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
```

Logic of the two cases:

```text
matchAny = false:
    tenantId = t-A
    AND name if present
    AND category if present
    AND brand if present
    AND active if present

matchAny = true:
    tenantId = t-A
    AND (
        name if present
        OR category if present
        OR brand if present
        OR active if present
    )
```

**Do not** write `ExampleMatcher.matchingAny()` with a probe containing `tenantId="t-A"` hoping MongoDB will treat tenant as mandatory. Otherwise tenant risks becoming **one branch of the OR**, allowing documents from other tenants to match via category/brand. Access-control constraints must stay **outside the optional OR group**.

### 9.3. Illustrative BSON Query

With tenant `t-A`, category `keyboard`, and brand `ACME`, the ANY option means:

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
})
.sort({ name: 1, _id: 1 })
.limit(30);
```

In a Spring Data path with a typed Example, a `_class` condition may be added; the syntax here illustrates **business logic** and does not promise the actual command contains only these fields. Regardless of whether QBE or a raw query is used, documents from other tenants must never appear.

### 9.4. Why Check the Number of Selected Conditions?

If `name`, `category`, `brand`, and `active` are all null, the matcher may generate no content predicates and the query will only have the tenant/type condition. With millions of products, this leads to an overly broad scan if there is no appropriate limit or index.

Rejecting requests with zero criteria is a safe policy for this search endpoint. In other use cases, browsing all products within a tenant may be allowed, but it should be a separately defined feature with appropriate pagination, limits, and permissions.

## 10. Distinguishing `false`, `null`, and "Not Selected"

With a three-state status selector:

```text
All statuses      → active = null (ignore predicate)
Active only       → active = true
Inactive only     → active = false
```

Example probe:

```java
ProductDocument inactiveProbe = new ProductDocument(
    null,
    null,
    null,
    null,
    null,
    Boolean.FALSE,
    null
);
```

`Boolean.FALSE` is a **concrete value** and is included in the query by QBE. With `matchingAny()` plus `brand="ACME"`, the condition becomes `active=false OR brand=ACME`, not "filter ACME and then take only inactive". If you need **brand=ACME AND active=false** even when other search fields use OR, group conditions explicitly with `Criteria.andOperator(...)`.

**Do not use `withIncludeNullValues()` to express "user has not selected a status".** That API requests evaluating null fields under different semantics, and in Spring Data MongoDB it has important consequences for subdocuments.

## 11. Customizing String Matching Per Field

When searching products by name, users usually want "contains a phrase" rather than exact character-for-character equality. `ExampleMatcher` supports `StringMatcher` and per-property matchers.

### 11.1. Exact, Starting, Ending, Containing

| Mode | Meaning | MongoDB Mental Model |
| --- | --- | --- |
| `DEFAULT` | Default store/framework comparison | Typically string equality when case-sensitive |
| `EXACT` | Full-string match | Start/end-anchored regex depending on framework generation |
| `STARTING` | Starts with string | Prefix-style regex |
| `ENDING` | Ends with string | Suffix-style regex |
| `CONTAINING` | Contains string inside | Contains-style regex |
| `REGEX` | Regex pattern | Requires special controls if input is untrusted |

Example setting default contains, while category/brand must match exactly:

```java
import static org.springframework.data.domain.ExampleMatcher
    .GenericPropertyMatchers.exact;
import static org.springframework.data.domain.ExampleMatcher
    .GenericPropertyMatchers.contains;

import org.springframework.data.domain.ExampleMatcher;

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths(
        "id", "tenantId", "priceCents"
    )
    .withMatcher("name", contains().ignoreCase())
    .withMatcher("category", exact())
    .withMatcher("brand", exact());
```

To choose ANY, replace `matchingAll()` with `matchingAny()`, keeping the corresponding property matchers.

### 11.2. Configuring Case Sensitivity

```java
ExampleMatcher caseInsensitive = ExampleMatcher.matchingAny()
    .withIgnorePaths("id", "tenantId", "priceCents")
    .withIgnoreCase("name", "brand");
```

`withIgnoreCase(...)` configures case handling for the specified fields, but **does not automatically strip Vietnamese diacritics**, is not fuzzy search, and is not the same as equality using a locale-specific MongoDB collation.

In MongoDB, case-insensitive string matching in QBE is often expressed via `$regex` with the `i` option. That regex **does not have the same ability to use a collation index as equality configured with a compatible collation**. For Vietnamese name search with complex Unicode requirements, design a canonical search key, collation, or dedicated search tool based on business goals.

### 11.3. QBE Is Not Full-Text Search

If you want to search "bàn phím" by vocabulary, accents, synonyms, keyboard types, relevance score, stemming, or fuzzy matching, `matchingAny` + `CONTAINING` does not turn into a full-text engine.

Alternatives include:

- `Criteria` with controlled equality/range/regex.
- Querying a normalized canonical field with an appropriate index.
- A MongoDB text index when that feature fits.
- A dedicated search solution when relevance, suggestions, or complex language handling is required.

Never let clients submit arbitrary regex directly to a production endpoint without checking query cost and safety.

## 12. Typed Example, `_class`, and `UntypedExampleMatcher`

This is a MongoDB-specific behavior that often leads learners to misread QBE results.

### 12.1. Typed Example May Restrict Entity Type by Default

```java
Example<ProductDocument> example =
    Example.of(probe, ExampleMatcher.matchingAll());
```

Under MongoDB QBE semantics, a standard **typed Example** adds a domain type constraint to the query. With default type-hint configuration, it may check `_class` (or type aliases) to return only documents belonging to supported types.

For instance, if a document was created via `mongosh`:

```javascript
db.products.insertOne({
  _id: "manual-01",
  tenant_id: "t-A",
  category: "keyboard",
  brand_code: "ACME"
  // Missing _class.
});
```

then a typed Example of `ProductDocument` may **not match** this document even though category/brand match completely. When testing QBE with shell-inserted data, inspect actual type hints instead of concluding AND/OR logic is broken.

### 12.2. Removing Type Restrictions with `UntypedExampleMatcher`

When a collection does not store type hints or holds multiple document types with compatible fields, you can use:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.mongodb.core.query.UntypedExampleMatcher;

ExampleMatcher matcher = UntypedExampleMatcher.matchingAny()
    .withIgnorePaths(
        "id", "tenantId", "name", "active", "priceCents"
    );

Example<ProductDocument> example = Example.of(
    probe, matcher
);
```

`UntypedExampleMatcher` disables the default type restriction when building MongoDB QBE. However, **untyped is not always the better choice**: it can cause the query to match documents that share field names but belong to a different business model. Inspect the schema, tenant, authorization, BSON types, and why the collection omits `_class`.

If you need typed QBE but legacy data lacks type hints, you may need to fix ingestion, run a migration, or choose a direct `Criteria` query with an explicit contract. Do not add `_class` to production data without evaluating read/write compatibility across the entire system.

### 12.3. When Does Type Restriction Matter?

- The collection stores multiple subtypes.
- Polymorphic mapping or `@TypeAlias` is used.
- Data is written through multiple pipelines, some with `_class` and others without.
- QBE tests fail while `mongosh find(...)` matches.

Inspect the actual BSON documents, check the mapping context, and inspect the MongoDB command sent. `UntypedExampleMatcher` only changes how type restriction works; it does **not** change the AND/OR meaning of `matchingAll`/`matchingAny`.

## 13. Null in QBE and Embedded Documents

### 13.1. Null Is Ignored by Default

`ExampleMatcher.matchingAll()` normally ignores null properties in the probe. Therefore, `brand=null` does not mean find documents with `brand_code:null`; it simply omits the brand predicate.

If business logic genuinely needs to find documents **missing a field** or **having a null field**, use `Criteria.where("brand").is(null)`, `exists(false)`, or `$type` according to MongoDB semantics instead of inferring it from an empty probe. Note that MongoDB evaluates `field: null` in a way that can include missing fields; clarify the requirement.

### 13.2. `withIncludeNullValues()` Requires Caution

```java
ExampleMatcher includeNulls =
    ExampleMatcher.matchingAll()
        .withIncludeNullValues();
```

This option tells the framework to **consider** null properties instead of ignoring them. In MongoDB, when **embedded documents** are present, including nulls can cause QBE to build **embedded document matching** instead of separate dot-notation predicates. That match may require the subdocument to match in structure and field order under MongoDB semantics.

Therefore:

- Do not enable `withIncludeNullValues()` just to handle empty form fields.
- Test with documents missing fields, documents with null fields, and nested objects with different field orders/fields.
- If complex nested OR/AND conditions are required, write `Criteria` explicitly rather than relying on a global matcher.
- Distinguish **null**, **missing**, and **empty string** in the schema.

### 13.3. Nested Property Paths

If an entity has `address.city`, you can use:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "address.city",
        ExampleMatcher.GenericPropertyMatchers
            .exact()
            .ignoreCase()
    );
```

This configures how a property path is compared. It **does not** let you express arbitrary condition groups like:

```text
(category = keyboard AND brand = ACME)
OR
(category = mouse AND active = true)
```

QBE only offers ALL/ANY across the predicates generated from the probe, with no arbitrary boolean grouping AST. Use `Criteria.orOperator(...)`/`andOperator(...)` when complex grouping is required.

## 14. How Does ALL/ANY Differ from Hand-Written `$and`/`$or`?

With two simple fields, QBE is very readable:

```java
ExampleMatcher all = ExampleMatcher.matchingAll();
ExampleMatcher any = ExampleMatcher.matchingAny();
```

But as logic grows more complex, `Criteria` expresses condition grouping more clearly:

```javascript
{
  tenant_id: "t-A",
  $or: [
    {
      category: "keyboard",
      brand_code: "ACME"
    },
    {
      category: "mouse",
      active: true
    }
  ]
}
```

Example using `MongoTemplate` with `Criteria`:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Criteria firstGroup = new Criteria().andOperator(
    Criteria.where("category").is("keyboard"),
    Criteria.where("brand").is("ACME")
);

Criteria secondGroup = new Criteria().andOperator(
    Criteria.where("category").is("mouse"),
    Criteria.where("active").is(true)
);

Criteria optional = new Criteria().orOperator(
    firstGroup, secondGroup
);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("t-A"),
        optional
    )
);
```

When executed via `template.find(query, ProductDocument.class)`, Java names such as `tenantId`/`brand` are mapped to BSON fields `tenant_id`/`brand_code`. The pattern above does not include typed QBE's `_class` restriction unless added by other logic. Test mapping and conditions on real MongoDB.

**Tool selection rule:** QBE fits a group of predicates sharing the same AND or OR operator; `Criteria` fits better when you need **OR groups containing AND**, range comparisons, `$in`, `$elemMatch`, dates, complex authorization conditions, or aggregations.

## 15. Why Can't QBE Replace Every MongoDB Query?

QBE is limited in comparison operators and boolean structure. The requirements below usually call for `Criteria`/`Query` or aggregation.

| Need | Is QBE Suitable? | Usually Recommended Tool |
| --- | --- | --- |
| category equals value and brand equals value | Yes | `matchingAll()` |
| category or brand | Yes | `matchingAny()` |
| Optional field if user leaves it blank | Yes, with appropriate null/ignore handling | Probe + matcher |
| Name starts with/contains a string | Yes, within MongoDB string matcher support | `withMatcher(...)` |
| price from 100,000 to 500,000 | Not directly expressible via QBE equality | `Criteria.gte/lte` |
| date within a range | Not directly expressible | `Criteria.gte/lte` |
| category=A AND (brand=B OR active=true) | No general grouped conditions | `Criteria.andOperator/orOperator` |
| Match multiple array elements by condition | Not suitable for general `$elemMatch` | `Criteria.elemMatch` |
| Join customers and orders collections | No | Aggregation `$lookup` |
| Count, group, sum totals | No | Aggregation `$group` |
| Search relevance/scoring | No | Dedicated search/aggregation |
| Multi-document transactions | No | `MongoTransactionManager`/reactive manager |

QBE **cannot** replace security/tenant conditions merely because the API has `matchingAll`. In examples where the user can choose `matchingAny`, invariant conditions must still sit outside the optional predicate group.

## 16. Indexes and Performance of ALL vs. ANY

### 16.1. AND Can Leverage Compound Indexes

For queries filtering by tenant, category, and brand:

```javascript
db.products.createIndex({
  tenant_id: 1,
  category: 1,
  brand_code: 1
});
```

This index can serve:

```javascript
db.products.find({
  tenant_id: "t-A",
  category: "keyboard",
  brand_code: "ACME"
}).explain("executionStats");
```

If the query also sorts by `name`, the index may need a different design to support filter+sort; do not create an index merely because an example mentions three fields. Monitor index size, write amplification, and real statistics.

### 16.2. OR Typically Needs Efficient Access Paths for Each Branch

For:

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
});
```

One indexing approach to investigate:

```javascript
db.products.createIndex({
  tenant_id: 1,
  category: 1
});

db.products.createIndex({
  tenant_id: 1,
  brand_code: 1
});
```

MongoDB may use appropriate indexes for the OR branches depending on the query planner, selectivity, and query structure. If one branch lacks a useful index, overall query performance can suffer. There is no guarantee every `matchingAny()` will get optimal index usage.

### 16.3. Regex and Search Mode Affect Index Usage

`CONTAINING` on a string often leads to regex scanning mid-string, which struggles to use B-tree indexes like equality or an anchored prefix. `ignoreCase` may use regex with the `i` option; **it does not automatically use a case-insensitive collation index like a collation-compatible equality**.

Therefore, switching a search from `matchingAll` exact to `matchingAny` contains+ignoreCase can increase latency significantly even though only a few lines of code changed. Measure on real data.

### 16.4. Inspecting with `explain`

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
})
.sort({ name: 1, _id: 1 })
.limit(30)
.explain("executionStats");
```

Observe:

| Metric | Question |
| --- | --- |
| `IXSCAN` or `COLLSCAN` | Is an index used or is it scanning the collection? |
| `totalKeysExamined` | How many index entries were scanned? |
| `totalDocsExamined` | Are many non-matching documents being read? |
| Sort stage | Is an in-memory sort needed outside the index, and at what cost? |
| `nReturned` | Is the result count actually bounded? |
| p95/p99 latency | Does the query meet SLAs under heavy load? |
| Bytes returned | Are you loading the whole entity when the endpoint only needs a DTO? |

`explain` on a hand-written `mongosh` query only proves how the **equivalent** query behaves. To verify the actual QBE shape, inspect the MongoDB command in integration tests or via MongoDB Java Driver command monitoring (without logging private data indiscriminately).

## 17. Returning DTOs or Projections Instead of Full Entities

Suppose search results only need ID, name, category, and brand:

```java
public record ProductSearchResult(
    String id,
    String name,
    String category,
    String brand
) {}
```

In Spring Data versions supporting `FetchableFluentQuery` for QBE, you can use `findBy(example, queryFunction)` to customize sort/projection/result processing via the corresponding API. However, overloads and BSON field optimization must be verified against your actual dependency Javadoc.

Another clear option when combining Query with authorization is `MongoTemplate`:

```java
Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("t-A"),
        Criteria.byExample(example)
    )
);

query.fields()
    .include("id")
    .include("name")
    .include("category")
    .include("brand");

query.limit(30);

List<ProductDocument> partialResults =
    template.find(query, ProductDocument.class);
```

**Warning:** `ProductDocument` results here are only partially loaded. Never call `template.save(partialResults.get(0))`; saving can wipe out fields excluded by the projection.

If you want a true DTO, you can use the fluent template with a source entity and target DTO in compatible Spring Data MongoDB versions:

```java
List<ProductSearchResult> results = template
    .query(ProductDocument.class)
    .as(ProductSearchResult.class)
    .matching(query)
    .all();
```

Whether using a class-based DTO or a closed interface, verify BSON results and aliases when `@Field("brand_code")` is present. Projections/DTOs do **not** replace authorization; tenant fields and sensitive metadata must not be exposed merely because an entity has getters.

## 18. Reactive QBE

In WebFlux applications, `ReactiveMongoTemplate` accepts `Query`/`Criteria` similarly but returns `Flux<T>`:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import reactor.core.publisher.Flux;

public Flux<ProductDocument> findReactive(
    ReactiveMongoTemplate template,
    String trustedTenantId,
    Example<ProductDocument> example
) {
    Query q = Query.query(
        new Criteria().andOperator(
            Criteria.where("tenantId").is(trustedTenantId),
            Criteria.byExample(example)
        )
    );

    q.limit(30);
    return template.find(q, ProductDocument.class);
}
```

In versions supporting `ReactiveQueryByExampleExecutor`, reactive repositories also offer `findAll(example)` returning `Flux`, though you should check the exact interface/version in use.

Reactive QBE does not open a transaction automatically, does not make regex queries cheaper, and does not save RAM if downstream calls `collectList()` on an unbounded set. Avoid calling `block()` on the WebFlux event loop.

If multiple related writes require a MongoDB transaction, use `ReactiveMongoTransactionManager`/an appropriate reactive transaction context. Reading with QBE is only a single **query**, not a consistent snapshot across multiple reads or collections.

## 19. Integration Testing ALL/ANY and Tenant Constraints

A unit test that merely mocks `ProductRepository` does not prove Spring Data translated `matchingAny()` into the right MongoDB query or handled entity type hints. You need integration tests on real MongoDB, for example configured via Testcontainers.

### 19.1. Fixed Test Dataset Written via Spring Data

JUnit 5 and Spring Boot `@DataMongoTest` example, assuming an isolated MongoDB database without these IDs already present:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.StreamSupport;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

@DataMongoTest
class ProductQbeIntegrationTest {

    @Autowired ProductRepository products;

    @Test
    void matchingAllAndMatchingAnyReturnDifferentSets() {
        products.saveAll(List.of(
            new ProductDocument(
                "qbe-01", "t-A", "Keyboard A",
                "keyboard", "ACME", true, 100000L
            ),
            new ProductDocument(
                "qbe-02", "t-A", "Keyboard B",
                "keyboard", "ZEN", true, 120000L
            ),
            new ProductDocument(
                "qbe-03", "t-A", "Mouse A",
                "mouse", "ACME", true, 90000L
            ),
            new ProductDocument(
                "qbe-04", "t-A", "Mouse B",
                "mouse", "ZEN", false, 80000L
            ),
            new ProductDocument(
                "qbe-05", "t-A", "Keyboard C",
                "keyboard", "ACME", false, 110000L
            ),
            new ProductDocument(
                "qbe-06", "t-B", "Other-tenant Keyboard",
                "keyboard", "ACME", true, 130000L
            )
        ));

        ProductDocument probe = new ProductDocument(
            null, null, null, "keyboard", "ACME", null, null
        );

        ExampleMatcher allMatcher =
            ExampleMatcher.matchingAll()
                .withIgnorePaths(
                    "id", "tenantId", "name", "active", "priceCents"
                );

        ExampleMatcher anyMatcher =
            ExampleMatcher.matchingAny()
                .withIgnorePaths(
                    "id", "tenantId", "name", "active", "priceCents"
                );

        List<String> allIds = StreamSupport.stream(
                products.findAll(
                    Example.of(probe, allMatcher)
                ).spliterator(),
                false
            )
            .map(ProductDocument::id)
            .sorted()
            .toList();

        List<String> anyIds = StreamSupport.stream(
                products.findAll(
                    Example.of(probe, anyMatcher)
                ).spliterator(),
                false
            )
            .map(ProductDocument::id)
            .sorted()
            .toList();

        assertThat(allIds).containsExactly(
            "qbe-01", "qbe-05", "qbe-06"
        );

        assertThat(anyIds).containsExactly(
            "qbe-01", "qbe-02", "qbe-03",
            "qbe-05", "qbe-06"
        );
    }
}
```

In this test, `qbe-06` appears because the repository method is not protected by a tenant filter. **That is intentional to demonstrate the risk**, not acceptable behavior in a real user endpoint. Another test must verify that `ProductSearchService` from section 9 **never returns `qbe-06`** when the trusted tenant is `t-A`.

Because the test uses fixed IDs, run it against an isolated test database/collection, or clean up test data properly; never run a wipe command against a shared collection. This sample test **was not executed** during authoring of this lesson.

### 19.2. Cases to Cover

| Case | Expected Behavior |
| --- | --- |
| Two fields category + brand, ALL | Only documents matching both |
| Two fields category + brand, ANY | Documents matching one or both |
| One field remaining | ALL and ANY return the same set |
| `active=null` | No predicate generated for active |
| `active=false` | Predicate generated for false status |
| Primitive `boolean` in probe | Does not accidentally filter `false` when unselected |
| Probe has ID but matcher ignores ID | ID does not become a predicate |
| Empty probe | Endpoint rejects per policy or strictly bounds query |
| ANY with mandatory tenant | No cross-tenant data |
| Category differing in letter case | Verify intended string matcher/collation |
| Typed Example with `_class` | Reads only documents matching the type |
| Untyped Example with raw shell document | Not blocked by unintended type restriction |
| Null/embedded documents | Distinguish missing, null, exact embedded matching |
| `@Field("brand_code")` | Actual query uses the right BSON field |
| Pagination/sort | Bounded results and deterministic order |

### 19.3. How to Inspect the Actual BSON Query

With `MongoTemplate`, you can inspect the query generated for each Example and observe actual commands in a test environment. An equivalent MongoDB example:

```javascript
db.products.find({
  tenant_id: "t-A",
  $or: [
    { category: "keyboard" },
    { brand_code: "ACME" }
  ]
})
.sort({ name: 1, _id: 1 })
.limit(30);
```

If documents have type hints, the command shape from Spring Data may differ. Shell queries prove MongoDB semantics, but confirming Spring Data generates the right BSON requires integration tests and observing driver commands/profiler output (avoiding logging personal data).

## 20. Common Mistakes When Using ALL/ANY

**"`matchingAny` means match all fields regardless of order."** False. ANY is **OR**; only one selected predicate needs to match.

**"A probe with 7 properties means QBE searches by all 7."** No. Null properties are ignored by default, and ignored properties do not participate.

**"Primitive false/0 are also ignored automatically because the user didn't enter them."** False. Primitives have non-null default values and can create unwanted predicates.

**"Putting tenantId in the probe with `matchingAny` still enforces tenant boundaries."** Logically false. Tenant can become **one branch of the OR** instead of a mandatory constraint.

**"`withIgnorePaths` automatically allowlists all remaining fields."** It only excludes the specified paths; any non-ignored property with a value can still participate.

**"`withIncludeNullValues` just means ignore null fields."** On the contrary, it includes nulls in matching rules and can alter embedded document matching.

**"QBE supports arbitrary nested AND/OR combinations."** No. Use `Criteria` for complex logical grouping.

**"`matchingAny` ranks products matching more criteria first."** No. For ranking, design separate sorting/scoring logic.

**"Case-insensitive QBE uses collation indexes just like equality."** Not by default. In MongoDB, ignoreCase often uses regex; measure with `explain`.

**"Documents inserted via `mongosh` without `_class` are always found by typed QBE."** Not guaranteed; typed QBE can add a type restriction. Inspect BSON and use `UntypedExampleMatcher` if schema-appropriate.

**"QBE fixes legacy data or normalizes Unicode."** No. QBE only queries; migration, validation, and normalization are separate workflows.

**"Read-only QBE queries always give consistent results across multiple requests."** No. Data can change between reads; transactions/read concern are separate design concerns.

## 21. Self-Check Lab

1. Create `ProductDocument` with category, brand, `active` as a `Boolean` wrapper, and several fields mapped with `@Field`.
2. Write six sample documents via Spring Data to test typed Examples; do not insert solely via the shell.
3. Create a probe `category="keyboard", brand="ACME"` with all other properties null.
4. Call `findAll(Example.of(probe, matchingAll()))` and predict the ID list.
5. Switch to `matchingAny()`, explaining why `p-02`/`p-03` are added.
6. Keep only one property in the probe; verify ALL and ANY are equivalent.
7. Add `active=false` and observe how predicates change in both modes.
8. Try a probe with primitive `boolean` defaulting to false; explain the unexpected results.
9. Use `withIgnorePaths` to exclude a property even when it has a value.
10. Write `ProductSearchService` with mandatory tenant outside the OR group; test that `p-06` never leaks.
11. Try `withMatcher("name", contains().ignoreCase())`, checking Vietnamese results and the query plan.
12. Insert a shell-created document missing `_class` and compare typed vs. untyped QBE.
13. Compare QBE queries against equivalent `Criteria.orOperator`/`andOperator` queries.
14. Implement a complex requirement `(category=A AND brand=B) OR (category=C AND active=true)` using `Criteria`.
15. Create indexes for actual AND/OR queries and measure performance with `explain("executionStats")`.
16. Write integration tests for null, active=false, tenant isolation, sort/pagination, and renamed BSON fields.

## 22. Pre-Production Checklist

| Question | What to Verify |
| --- | --- |
| Are you using ALL or ANY? | `matchingAll()` = AND; `matchingAny()` = OR |
| How many predicates are actually selected? | Null is ignored by default; primitives have default values |
| Should any fields always be ignored? | Explicit `withIgnorePaths(...)` |
| Does the probe come from an unchecked request? | Build probe from an allowlist of validated fields |
| Where is tenant/authorization placed? | **Outside** the ANY group, mandatory AND constraint |
| Is an empty probe allowed? | Define rejection policy, limits, and paging |
| Are there optional Boolean/Integer fields? | Use wrappers to distinguish "not selected" |
| Are you using `withIncludeNullValues()`? | Understand null/missing/embedded matching |
| Do you need fuzzy matching, ranges, or nested OR? | Use `Criteria`/aggregation instead of QBE |
| Is typed `_class` present? | Check mapping and type hints on legacy data |
| Are fields renamed with `@Field`? | Observe BSON query and test mapping |
| Does the string matcher create index-unfriendly regex? | Check `explain` on representative data |
| Could the query return huge result sets? | Apply sort/limit/page and indexes |
| Are DTOs/projections missing fields? | Never save partial entities |
| Does reactive code block the event loop? | Use non-blocking `Flux`/`Mono` |
| Have AND/OR been tested on real MongoDB? | Test selected types, tenant isolation, and edge cases |

## 23. References

QBE APIs belong to Spring Data Commons, while converting Examples into MongoDB queries, type restrictions, and string matching depend on Spring Data MongoDB. When integrating into a specific project, verify against your **dependency versions** rather than assuming every overload from the latest Javadoc exists.

- [Spring Data MongoDB — Repository Query by Example](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
- [Spring Data MongoDB — Template Query Operations and Query by Example](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html)
- [Spring Data MongoDB — UntypedExampleMatcher API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/UntypedExampleMatcher.html)
- [Spring Data MongoDB — Criteria API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/Criteria.html)
- [MongoDB Manual — Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

**Conclusion:** In Spring Data MongoDB, **`ExampleMatcher.matchingAll()`** expresses **AND** and **`ExampleMatcher.matchingAny()`** expresses **OR** across predicates generated from actually selected properties. Query quality depends on an **intentionally constructed probe**, handling of `null`/primitives, `withIgnorePaths`, string matchers, and typed `_class`; security depends on **mandatory tenant/authorization conditions placed outside the OR group**. When logic requires complex grouping, ranges, or aggregations, switch to `Criteria`/`MongoTemplate`; at scale, combine indexes, paging, projections, and real BSON testing for accurate, safe, and measurable results.
