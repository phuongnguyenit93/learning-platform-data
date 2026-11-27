# Reviewing Mapping, Converter, and Type Hint Changes

When upgrading Spring Data Elasticsearch or modifying data structures, an application may compile and start normally yet misread older documents, write a new format that currently running instances do not understand, or query against an outdated mapping. These failures typically occur because persisted data outlives a single application version.

Therefore, reviewing a mapping, converter, or type hint change requires inspecting three contracts simultaneously:

- **Mapping contract:** how Elasticsearch stores and indexes each field.
- **Conversion contract:** how Spring Data converts Java types to documents and reads documents back.
- **Type metadata contract:** how Spring Data identifies which concrete class to instantiate when reading polymorphic documents.

These contracts must remain compatible with existing stored data and with application versions that may run concurrently during a rollout. A change that works for new documents can still break legacy data or disrupt rolling deployments.

## 1. Why review before upgrading?

Suppose the current application version stores products as follows:

~~~json
{
  "_class": "com.example.catalog.ProductDocument",
  "id": "p-100",
  "price": "USD:1299",
  "status": "ACTIVE"
}
~~~

After upgrading, the development team wants to:

- Change `price` from a string to an object containing `amount` and `currency`.
- Change `status` from `keyword` to a different structure.
- Move `ProductDocument` to a new package.
- Change the analyzer for `name`.
- Disable default type hints for leaner documents.

Each change can impact a different layer. If you only test the new code against freshly written documents, you will not know whether the new code can read older data. If a rolling deployment keeps older instances running, you must also check whether old instances understand documents written by new instances.

A data change must be evaluated along three dimensions:

| Evaluation Dimension | Question |
|---|---|
| Existing data | Can the new version read old documents? |
| New data | Can the old version or legacy consumers read new documents? |
| Mapping/index | Can Elasticsearch apply the change on the current index, or does it need a new index and reindex? |

Do not assume changing a Java annotation automatically alters the mapping of a running index. The actual mapping is persisted in Elasticsearch and has a lifecycle independent of Java classes.

## 2. Identify versions and current state

Before evaluating changes, determine the exact versions used by the application and cluster:

- Spring Boot version.
- Spring Data release train and Spring Data Elasticsearch version.
- Elasticsearch Java Client version.
- Elasticsearch cluster version.
- Current mapping/index template version.
- Converter and type metadata version used to create existing data.
- Whether other applications or workers read/write the same index.

Spring Data Elasticsearch APIs vary by release train. Annotations, enums, custom conversion constructors, query builders, and client configurations can differ across releases. Do not copy an example from another release and assume compatibility.

Inspect the project's dependency tree or dependency lock and verify APIs in the corresponding Javadoc. For the cluster, retrieve version info directly from the version endpoint:

~~~http
GET /
~~~

Do not look solely at versions written in build files. Spring Boot dependency management may resolve a different actual version.

## 3. Classifying mapping changes

Mappings describe how Elasticsearch interprets and indexes fields. Some changes are relatively safe, while others can only apply to a new index.

| Change | Common Impact | Handling Strategy |
|---|---|---|
| Add a new field | Old documents lack the field | Usually safe to add to mapping; handle missing values |
| Add a multi-field | Old documents lack terms for the new subfield | Usually requires reindex to backfill |
| Change field type | Existing data is incompatible with the new mapping | Create a new index and reindex |
| Change analyzer | Already indexed tokens are not regenerated | Create a new field/index and reindex |
| Change `object` to `nested` | Indexing and query structure change | Create a new index and reindex |
| Change date format | Old values may fail to parse | Inspect data, migrate, or add a new field |
| Change `dense_vector` dimensions | Old vectors do not match new schema | Create a new index and regenerate embeddings |
| Change index settings | Some settings require closing the index or apply only at index creation | Check exact setting and reindex plan |

This classification is directional and does not replace the mapping documentation for your running Elasticsearch version. Certain parameters can be updated under specific conditions; others can only be set at index creation. Reviews must check exact parameters, field types, and versions rather than assuming all mappings are immutable.

## 4. Additive changes: adding a new field

Adding a new field is generally lower risk than changing an existing field's type:

~~~json
PUT /products-read/_mapping
{
  "properties": {
    "searchKeywords": {
      "type": "keyword"
    }
  }
}
~~~

Old documents without `searchKeywords` continue to exist. When reading old documents, the application must accept `null` or missing fields. When querying, old documents will not match filters or aggregations on the new field until backfilled.

### 4.1. Adding a field does not populate data

After updating the mapping, old documents do not automatically acquire values. For example, an application adds `categoryPath` to support filtering by category path. The mapping exists, yet `categoryPath` remains absent in existing documents.

The plan must specify:

- Whether the new field is optional during the transition or mandatory.
- Whether queries handle documents missing the field.
- When legacy data will be backfilled.
- When compatibility logic for missing fields can be removed.

### 4.2. Dynamic mapping

If dynamic mapping is enabled, Elasticsearch can infer mappings when encountering new fields. While convenient for flexible schemas, it carries risks:

- The first value encountered dictates the field type.
- Heterogeneous data can produce unintended mappings.
- Proliferating fields can trigger mapping explosion.
- User-controlled field names make schemas unpredictable.

For important fields, declare explicit mappings or intentional dynamic templates. Never let a single malformed initial document dictate the mapping for an entire index.

## 5. Changing field types is a breaking change

Suppose `price` is currently `keyword`:

~~~json
{
  "price": {
    "type": "keyword"
  }
}
~~~

The team wants to change it to numeric for range queries and sorting:

~~~json
{
  "price": {
    "type": "scaled_float",
    "scaling_factor": 100
  }
}
~~~

This cannot be treated as a simple annotation change on the same index. Elasticsearch does not allow arbitrarily changing the type of an already populated field. You must create a new index with the new mapping, transform the data, and reindex.

Typical workflow:

1. Create a new versioned index with the desired mapping.
2. Read documents from the old index or authoritative data source.
3. Convert `price` to its numeric representation.
4. Index into the new index.
5. Check failed documents, null values, rounding, and queries.
6. Synchronize changes that occurred during backfill.
7. Switch the alias to the new index.

### 5.1. Be careful with currency

Converting money strings to numbers requires defining currency and scale. A value like `USD:1299` may represent 12.99 USD if the amount is in minor units. Do not parse it as `1299.0` and treat different units as equivalent.

If an index contains multiple currencies, range queries on `price` can be meaningless without currency normalization. Store `amountMinor` and `currency` separately, or convert to a standard currency with an explicit exchange rate and timestamp.

With `scaled_float`, `scaling_factor` determines storage precision. Check rounding behavior and value bounds before migrating.

## 6. Changing analyzers or normalizers

Analyzers control which tokens are produced at index time and search time. When changing an analyzer, updating the mapping does not re-analyze terms already stored in the inverted index.

For example, `name` previously used the `standard` analyzer and now needs `lowercase` and `asciifolding`. New queries may be analyzed by the new analyzer while old documents still hold tokens from the old analyzer, producing inconsistent search results.

Options:

- Create a new field with the new analyzer, backfill/reindex, then switch queries to the new field.
- Create a new versioned index and reindex all data.
- For certain supported setting changes, close the index, update settings, and reopen it; however, existing indexed data still needs reindexing if tokenization changed.

Do not test an analyzer solely with the Analyze API on sample strings. Test against indexed documents and real queries to confirm index-time and search-time tokens align.

### 6.1. Changing a keyword normalizer

Normalizers affect how `keyword` fields are normalized, such as lowercasing. They affect exact matches, aggregations, and sorting. Evaluate them alongside queries using that field. Do not assume changing a normalizer automatically updates terms of existing documents.

### 6.2. Multi-fields

Adding a multi-field such as `name.keyword` enables sorting or aggregations on the raw value. However, old documents lack indexed terms for the new subfield. Backfill/reindex is required so queries on the subfield cover legacy data.

## 7. Changing object, nested, and JSON structures

Suppose `variants` is currently a plain object array:

~~~json
{
  "variants": [
    { "color": "black", "size": "M" },
    { "color": "white", "size": "L" }
  ]
}
~~~

If queries must ensure `color` and `size` belong to the same variant, a `nested` mapping may be required. Switching from `object` to `nested` changes how Elasticsearch indexes and queries array elements, requiring a new index and reindexing.

The review must check whether existing queries already use `nested` queries/aggregations, whether response structures change, whether Java converters map collections and nested objects accurately, whether old documents have null/missing fields or different shapes, and whether nested object counts impact limits/performance.

Do not pick `nested` merely because JSON contains an array of objects. The change should be driven by query semantics that must preserve per-element field correlation.

## 8. Changing mappings for dense_vector

Dense vectors carry their own contract:

- Number of dimensions.
- Vector type and representation.
- Similarity function.
- Index/ANN configuration.
- Embedding model and model version.

If a new model changes dimensions, the existing index cannot accept vectors of the new length into a field declared with the old `dims`. Even if dimensions stay unchanged, switching embedding models places old and new vectors in incompatible embedding spaces.

Therefore, changing models or dimensions usually requires:

1. Creating a new versioned index.
2. Updating the `dense_vector` mapping.
3. Re-embedding all content with the new model.
4. Verifying vector dimensions and model metadata.
5. Evaluating retrieval quality.
6. Switching the alias or query routing once the new index is ready.

Do not simply change `dims` in the annotation and call `save`. The old index mapping remains in place, and old data does not automatically move to the new embedding space.

## 9. Reviewing converters: stored data and Java data

Converters define how Java types translate to Elasticsearch document representations.

A custom converter might serialize a value object to a string or number, parse stored strings into enums/value objects, normalize dates/times, convert ID types, or read legacy structures.

In Spring Data, converters can be marked by direction:

- `@WritingConverter`: converts a Java value to the stored format.
- `@ReadingConverter`: converts stored data back into a Java type.

Example:

~~~java
public record Money(long minorUnits, String currency) {
}

@WritingConverter
public class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + ":" + source.minorUnits();
    }
}

@ReadingConverter
public class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Invalid money value");
        }
        return new Money(
                Long.parseLong(parts[1]),
                parts[0]
        );
    }
}
~~~

Register custom conversions in Spring Data Elasticsearch configuration per your version's API:

~~~java
@Bean
ElasticsearchCustomConversions elasticsearchCustomConversions() {
    return new ElasticsearchCustomConversions(
            List.of(
                    new MoneyToStringConverter(),
                    new StringToMoneyConverter()
            )
    );
}
~~~

During review, verify that converters are actually registered with the Elasticsearch mapping converter. Defining a standalone `Converter` bean without wiring it into `ElasticsearchCustomConversions` does not guarantee Spring Data will invoke it.

## 10. Evaluating converter format changes

Suppose the old version stores:

~~~json
{
  "price": "USD:1299"
}
~~~

And the new version wants to store:

~~~json
{
  "price": {
    "currency": "USD",
    "minorUnits": 1299
  }
}
~~~

This is a representation change, not just refactoring a `Money` class. Both reader and writer must be examined:

| Version | Reads Old Format | Reads New Format | Writes Old Format | Writes New Format |
|---|---:|---:|---:|---:|
| Old app | Yes | Probably not | Yes | No |
| New app | Must during migration | Yes | Depends on rollout | Yes after cutover |

If old instances are still running while new instances write documents, old instances can fail when reading the new object shape. Consequently, the rollout must control when the writer switches formats.

### 10.1. Expand-and-contract strategy

A safer rollout path:

**Phase 1 — Expand reader:** deploy a version that reads both old and new formats while still writing the old format. All instances and workers must be compatible before changing the writer.

**Phase 2 — Switch writer:** switch the writer to the new format. New readers still understand old documents, so unmigrated data continues working.

**Phase 3 — Backfill:** convert legacy documents to the new format or reindex into a new index. Monitor parse errors and remaining legacy documents.

**Phase 4 — Contract:** once verified that no legacy data or old consumers remain, drop legacy format support in a later release.

If deploying compatible readers beforehand is impossible, use a new index and perform a coordinated cutover instead of mixing two formats in one index.

### 10.2. Dual-read does not justify arbitrary dual-write

Readers can support multiple formats for migration. Writers should emit a single canonical format at any given phase. Writing two fields or representations simultaneously can create inconsistent states if only one field gets updated.

If dual-write is unavoidable, define which field is authoritative, how partial failures are handled, when writing the legacy field stops, and how consistency between both values is verified.

### 10.3. Converters must handle edge-case data

Check:

- Missing fields.
- `null` values.
- Empty strings or invalid delimiters.
- Unparseable amounts.
- Invalid currencies.
- Dates lacking timezones.
- Renamed or deleted enum constants.
- Numbers exceeding Java type bounds.
- Documents formatted by releases several versions back.

Do not silently turn malformed data into default values. Log sufficient metadata for investigation without exposing sensitive content, and define a quarantine/repair strategy for unreadable documents.

## 11. What is a type hint?

When Spring Data Elasticsearch writes an object, the mapping converter may store metadata identifying the concrete Java type for deserialization. Default metadata typically resides in the `_class` field inside `_source`.

Example:

~~~json
{
  "_class": "com.example.catalog.ProductDocument",
  "id": "p-100",
  "name": "Keyboard"
}
~~~

Type hints are useful when subclasses extend a base class, a property is declared as an interface or abstract type, a property holds polymorphic objects, or Spring Data must reconstruct the exact concrete type on read.

Type hints are Spring Data metadata inside the document source. They are not Elasticsearch's legacy mapping `_type` removed in Elasticsearch 7. Do not confuse `_class` with `_type`.

## 12. @TypeAlias and stable class names

If `_class` stores the fully qualified class name, moving packages or renaming classes can prevent old documents from resolving.

Spring Data supports `@TypeAlias` to use a stable alias:

~~~java
@Document(indexName = "products-read")
@TypeAlias("product")
public class ProductDocument {
    @Id
    private String id;

    private String name;
}
~~~

Documents can store metadata like:

~~~json
{
  "_class": "product",
  "id": "p-100",
  "name": "Keyboard"
}
~~~

Aliases decouple stored metadata from Java package/class names. When refactoring packages or renaming classes, the alias can remain unchanged as long as Spring Data's mapping context knows which type the alias maps to.

### 12.1. The mapping context must know the alias

`@TypeAlias` does not magically apply across all documents. Spring Data must know the entity associated with the alias in its mapping context. Ensure entities are scanned/registered or declared in the proper mapping configuration before reading documents containing aliases.

If an alias is unrecognized, deserialization may fail or fail to instantiate the proper subtype. Test within a real Spring context rather than merely instantiating the class and checking annotations.

### 12.2. Changing an alias is a data migration

If the old alias is `product-v1` and you want to change it to `catalog-product`, inspect stored documents:

- Can the new reader recognize the old alias?
- Which alias will the new writer emit?
- Are other consumers reading the same index?
- Can the old alias remain registered as a legacy mapping temporarily?
- When will old metadata be backfilled?

Do not change the alias in code and assume existing documents update themselves. `_class` is already stored inside `_source` of existing documents.

## 13. When should type hints be disabled?

Type hints are helpful for polymorphic mappings, yet unnecessary when documents are always read as a single concrete class with no polymorphic properties.

Some versions of Spring Data Elasticsearch allow configuring `writeTypeHint` on `@Document`, for example:

~~~java
@Document(
        indexName = "products-read",
        writeTypeHint = WriteTypeHint.FALSE
)
public class ProductSearchDocument {
    @Id
    private String id;

    private String name;
}
~~~

Supported APIs and enums must be confirmed in your active release train. Do not copy this snippet if your dependency version lacks the corresponding attribute.

Before disabling type hints, evaluate:

- Does the document use inheritance or polymorphic properties?
- Can the reader infer subtypes from another business field?
- Do old documents still contain `_class`?
- Do other consumers rely on `_class`?
- Is a custom type mapper needed to read legacy data?

Disabling type hints on the writer stops emitting that metadata on new documents per configuration. It does not remove `_class` from old documents. Readers may encounter documents both with and without hints during transition.

### 13.1. Do not strip _class from sources arbitrarily

Do not bulk-delete `_class` from documents before verifying whether any reader still needs it. For polymorphic properties, missing type hints can prevent Spring Data from knowing which subtype to instantiate.

To remove metadata safely, prove every reader can deserialize new documents, handle old documents, and no longer depends on polymorphic resolution. Only then plan cleanup/migration.

## 14. Type hints in nested objects and polymorphism

Type metadata may be written for root documents and complex properties depending on the mapping converter/configuration. For example:

~~~java
public interface PaymentMethod {
}

public class CardPayment implements PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String bankCode;
}

@Document(indexName = "orders-read")
public class OrderDocument {
    @Id
    private String id;

    private PaymentMethod paymentMethod;
}
~~~

When reading `OrderDocument`, Spring Data must know whether `paymentMethod` is a `CardPayment` or a `BankTransfer`. Type hints or a custom conversion/discriminator strategy supply that information.

If type hints are disabled without another discriminator, interface/abstract properties may fail to deserialize. If a business discriminator field such as `paymentMethodType` exists, verify how custom converters or mappers use it to instantiate the subtype.

Do not confuse a business discriminator with `_class`: they may coexist, yet serve different purposes and contracts.

## 15. Reviewing the impact of converters and type hints on legacy data

When changing converters or type metadata, check actual existing documents:

| Legacy Data | New Change | Risk |
|---|---|---|
| `price` is a string | New converter only reads objects | Old documents fail to deserialize |
| Enum stored under old name | Enum renamed | Reader cannot resolve enum constant |
| Date stored without timezone | New reader requires offset | Parse error or incorrect conversion |
| `_class` is full package name | Class moved packages | Type resolution fails |
| `_class` is old alias | Alias renamed | Mapping context rejects old alias |
| Nested object has type hint | New writer disables type hints | Reader cannot reconstruct subtype |
| Vector has old model metadata | New model adopted | Document and query vectors sit in different embedding spaces |

Do not test only a document freshly written by the new version. Maintain fixtures representing data from supported past releases and verify them against the new reader.

## 16. Inspecting live mappings and sample documents

Commonly used APIs during review:

Retrieve mappings:

~~~http
GET /products-read/_mapping
~~~

Retrieve settings:

~~~http
GET /products-read/_settings
~~~

Check field capabilities across one or more indexes:

~~~http
GET /products-read/_field_caps?fields=price,status,name
~~~

Field capabilities help detect cases where the same field has inconsistent types across multiple indexes queried via an alias. For example, one index defines `price` as `keyword` while another defines it as `scaled_float`; an alias pointing to both can trigger errors or inconsistent query semantics.

Check index templates and component templates if the application uses templates:

~~~http
GET /_index_template
~~~

For newer templates, use the version-appropriate simulate API to inspect the resulting composed settings and mappings. Check template priority and component template composition; another template might override expected settings.

Fetch representative sample documents:

~~~http
GET /products-read/_search
{
  "size": 5,
  "_source": [
    "id",
    "price",
    "status",
    "_class"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

The goal is to inspect actual stored representations, including missing fields, nulls, legacy formats, and type hints. Sample across different data ages, not just the newest documents.

## 17. Testing compatibility across versions

An upgrade test suite should cover multiple directions:

### 17.1. New reader reading old documents

Save JSON fixtures from the previous version, then read them with the new version's mapping converter/`ElasticsearchOperations`. Verify legacy fields map properly, converters parse legacy formats, enums/dates/value objects behave accurately, `_class` or legacy aliases resolve, and optional fields behave as expected.

### 17.2. New writer producing valid documents

Write a document using the new version and inspect `_source`, mappings, and type hints. Confirm the output matches the defined contract.

### 17.3. Can the old reader read new documents?

This test matters when rolling deployments leave old instances running. If the new writer emits a format the old reader does not understand, you must:

- Deploy compatible readers first.
- Defer switching the writer until old readers are retired.
- Or use a newly versioned index with separate routing.

Not every change requires old readers to understand new data, but the rollout must guarantee old instances never misread new indexes or documents.

### 17.4. Integration tests on the target major version

Use Testcontainers or a test environment matching supported Elasticsearch versions. Pin image versions rather than using `latest`. Verify mappings, converters, type hints, queries, and reindex behavior as needed.

If the application supports multiple cluster versions, run the compatibility matrix across versions within the support policy. You do not need to test every end-of-life historical version.

## 18. Reindex and alias cutover

For breaking changes such as field types, analyzers, nested structures, or vector dimensions, a new index is typically required.

Example:

~~~http
PUT /products-v2
{
  "mappings": {
    "properties": {
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Then you can use the Reindex API if source and target representations are compatible:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

If converters or formats require complex transformations, direct reindexing may fall short. Use an application migration job or an ingest pipeline/script capable of parsing and transforming documents. For large datasets, run in batches, persist checkpoints, inspect per-document errors, and support resumption.

### 18.1. Synchronizing writes during reindexing

If data continues to be written to the old index during reindexing, recent updates may be missed in the target index or overwritten by stale copies.

Common strategies:

- Pause writers briefly and run a final catch-up pass.
- Use outbox/CDC to replay changes after a watermark.
- Controlled dual-write over a short window with idempotency and versioning.

Choose a strategy based on write volume and downtime tolerance. Avoid naive dual-writes in the request path without handling partial failures where only one index succeeds.

### 18.2. Switching the alias

Once the new index is verified, swap the alias in a single request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    }
  ]
}
~~~

Aliases shield the application from knowing versioned physical index names. If there is a write alias, configure the write index explicitly and verify write operations target the proper index.

Retain the old index during the rollback window. Do not delete it right after cutover before confirming production queries, mappings, and data are stable.

## 19. Expand-and-contract rollout workflow

A compatible rollout usually proceeds through these stages:

~~~text
1. Expand readers
   Read both old and new data
          |
          v
2. Deploy compatible application
   All instances/consumers understand new schema
          |
          v
3. Switch writers
   Start writing new representation
          |
          v
4. Backfill / reindex
   Migrate old data
          |
          v
5. Verify
   No legacy data remains
          |
          v
6. Contract
   Drop legacy format/type metadata support
~~~

For breaking mappings, these stages may happen against a newly versioned index rather than in place. The core principle is never letting a writer emit data that active readers cannot parse.

## 20. Planning rollback

Rolling back code does not automatically roll back written data. If the new version changed converters and wrote a new format, reverting to the old binary can prevent the old binary from reading newly written data.

Before rolling out, determine:

- Can the old binary read the new format?
- Is the old index intact and how up to date is it?
- Can the alias be switched back?
- How are events/outbox records produced during migration replayed?
- Will writes made during cutover be lost when reverting?
- Must compatible readers remain supported across multiple releases?

For breaking changes, rollback is usually safer by preserving the old index and routing the app back to it, while accounting for writes that occurred after cutover began. Do not treat an alias switch as a complete rollback if new data exists only in the new index.

## 21. Common review mistakes

| Mistake | Consequence | Proper Review Practice |
|---|---|---|
| Changing `@Field` type and deploying | Live mapping keeps old type | Inspect live mapping; create new index if needed |
| Changing analyzer without reindexing | Old documents keep old tokens | Reindex or backfill a new field |
| Changing converter and testing only new data | Old documents fail to read | Test fixtures from past releases |
| Renaming class without checking `_class` | Type resolution fails | Use stable aliases or migrate metadata |
| Disabling type hints without checking polymorphism | Subtypes fail to instantiate on read | Test root and nested polymorphic properties |
| Checking only Java annotations | Index templates or legacy indexes may differ | Inspect live mappings/settings |
| Deploying new writer before new reader | Old instances crash reading new data | Expand readers first, switch writers later |
| Reindexing during writes without replaying changes | Target index misses or has stale docs | Watermark, CDC/outbox, or controlled pause |
| Deleting old index immediately after cutover | Lose rollback path | Retain old index per retention policy |
| Comparing only document counts | Misses converter or mapping errors | Verify fields, versions, sample queries, and type metadata |

## 22. Change review checklist

**Mapping**

- [ ] Inspected live mappings/settings/templates of the running index.
- [ ] Classified change as additive or breaking.
- [ ] Checked field types, analyzers, normalizers, nested/object, dates, and vector dimensions.
- [ ] Determined whether old documents need new fields or backfilling.
- [ ] Determined whether a new versioned index and reindex are needed.

**Converter**

- [ ] Checked both read and write directions.
- [ ] Documented old and new representations.
- [ ] New reader parses legacy data during transition.
- [ ] Handled `null`, missing fields, malformed values, enums, and date/time.
- [ ] Verified converters are registered in `ElasticsearchCustomConversions`.
- [ ] Defined when legacy format support can be dropped.

**Type hints**

- [ ] Inspected `_class` in real stored documents.
- [ ] Evaluated how class renames/package moves impact stored data.
- [ ] Considered `@TypeAlias` and mapping context registration.
- [ ] Checked root documents and nested polymorphic properties.
- [ ] If disabling type hints, proved readers no longer rely on that metadata.

**Rollout and operations**

- [ ] New readers deployed before new writers when required.
- [ ] Migration/reindex job and checkpoints prepared.
- [ ] Writes occurring during backfill handled.
- [ ] Data and queries validated post-cutover.
- [ ] Rollback plan covers both code and indexes/data.
- [ ] Old index retained long enough per rollback policy.

## 23. Conclusion

Reviewing mapping, converter, and type hint changes means evaluating compatibility across new code, stored data, and concurrent application versions during an upgrade. Mappings dictate how Elasticsearch indexes fields; converters govern representations between Java and documents; type hints enable Spring Data to reconstruct concrete types, especially for polymorphic data.

Adding fields can often be rolled out additively, whereas changing field types, analyzers, nested structures, or `dense_vector` dimensions generally requires a new index and reindexing. Converter changes must consider both old and new data, while changing `_class` or `@TypeAlias` requires checking the mapping context and polymorphic properties. Never treat clean compilation or reading a single fresh document as proof of a safe migration.

A reliable upgrade workflow inspects live mappings/settings, retains legacy data fixtures, deploys compatible readers before new writers, runs controlled backfills or reindexing, validates outcomes, and preserves a rollback path. When contracts are versioned and rolled out via expand-and-contract, schema evolution can proceed without breaking reads of existing data.
