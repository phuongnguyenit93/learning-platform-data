# Distinguishing Application-Side Mapping Metadata and Existing Mappings

In Spring Data Elasticsearch, annotations on Java entities describe how the application understands and transforms data. In Elasticsearch, each index also has a mapping stored on the server side to define how fields are recognized, analyzed, indexed, and queried. These two parts are related, yet they are not the same thing.

- **Application-side mapping metadata** is information in Java code, typically declared using annotations such as `@Document`, `@Id`, and `@Field`. Spring Data uses this metadata to map Java objects to documents, convert documents back to objects, and generate mapping definitions when needed.
- **Existing mapping on Elasticsearch** is the schema configuration of an index stored in the cluster. Elasticsearch uses that mapping when receiving documents and executing queries.

For example, an entity declaring `name` as `text` and `category` as `keyword` only describes the application's mapping intent. For Elasticsearch to actually apply those two field types, the corresponding mapping must be created or updated on the index. If the index already exists with a different mapping, changing annotations in Java does not automatically turn the server-side mapping into the new configuration.

## 1. What Is Application-Side Mapping Metadata?

Spring Data Elasticsearch uses entity metadata to understand the relationship between Java classes and documents in Elasticsearch.

Example:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text, analyzer = "standard")
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;

        @Field(type = FieldType.Double)
        private Double price;

        // constructors, getters and setters
    }

The annotations describe different pieces of information:

| Annotation | Role |
|---|---|
| @Document | Declares which index the entity maps to and certain document/index-related options |
| @Id | Marks the property used as the document identifier |
| @Field | Describes field name, data type, and mapping attributes such as analyzer, format, or indexability |

Spring Data builds entity metadata through the mapping context and uses `MappingElasticsearchConverter` to convert between Java objects and document data. This metadata helps the framework know which property corresponds to which field, which data types need conversion, and how to handle values when reading or writing.

For example, when saving a `Product`, the converter turns its properties into a JSON document with the corresponding structure. When reading a document, the converter transforms the returned data into a `Product` object.

Application-side metadata can also be used to generate a mapping definition for an index. This is one reason Spring Data provides mapping annotations: the same entity model can support data conversion and describe the mapping needed for Elasticsearch.

However, annotations are not schema update commands sent to Elasticsearch every time the application starts or every time an object is saved. Creating indexes and updating mappings are separate operations depending on configuration and application lifecycle.

## 2. What Is an Existing Mapping on Elasticsearch?

Elasticsearch stores mappings at the index level. A mapping describes how each field in a document is processed, for example:

- Whether a field has type `text`, `keyword`, `long`, `double`, `date`, `boolean`, or another type.
- Which analyzer a `text` field uses to tokenize text.
- Whether the field is indexed for searching.
- Whether the field supports doc values for sorting and aggregations.
- How object or nested fields are represented.
- Whether dynamic mapping is permitted to infer new fields automatically.

The mapping of the `products` index might look like:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          },
          "price": {
            "type": "double"
          }
        }
      }
    }

Once the index is created, the mapping is stored in the Elasticsearch cluster and applied to writes, searches, sorting, and aggregations on that index.

The current mapping can be read via the REST API:

    GET products/_mapping

The response shows the mapping configuration Elasticsearch is using. This is the data to inspect when you want to know how the actual index interprets fields, especially when the index was created prior to deploying the current application version.

A mapping is a configuration of an index, not a property of a Java class. One `Product` class can be used to write to multiple different indexes, while each index has its own mapping. If an alias points to multiple indexes, the indexes behind the alias can also have different mappings.

## 3. How Do the Two Types of Mappings Relate?

Spring Data metadata can be used to create a mapping for Elasticsearch, but once the mapping is stored on the server, Elasticsearch uses the index's mapping to process documents. You can visualize the flow as follows:

    Java Entity
    @Document / @Id / @Field
           |
           v
    Spring Data mapping metadata
           |
           +-----------------------------+
           |                             |
           v                             v
    MappingElasticsearchConverter   Mapping builder
    Convert object <-> document     Build mapping definition
           |                             |
           v                             v
    Document JSON                 IndexOperations
           |                             |
           v                             v
    Elasticsearch index  <------  Index mapping
           |
           v
    Elasticsearch handles indexing/search

The diagram illustrates two related but distinct purposes:

1. The converter uses metadata to transform data between Java and documents.
2. The mapping builder uses metadata to create a mapping definition that can be sent to Elasticsearch when creating an index or updating mappings via supported operations.

When the application sends a document to an existing index, the JSON document is sent through the client. Elasticsearch validates and processes the document according to the index's current mapping. The server does not read `@Field` annotations from Java classes itself; annotations only have meaning inside the Spring Data application.

Therefore, clearly distinguish:

- Java metadata describes how the application intends to map data.
- Server mapping determines how Elasticsearch actually indexes and queries data.
- The converter is responsible for converting objects and documents, not replacing Elasticsearch's mapping engine.

## 4. Example When Metadata and Server Mapping Match

Suppose the entity declares:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text, analyzer = "standard")
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;
    }

The corresponding mapping on Elasticsearch is created:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Both sides agree:

- `name` is `text`, suited for full-text search with queries such as `match`.
- `category` is `keyword`, suited for exact matching with `term`, filters, sorting, or aggregations.

When Spring Data saves `Product`, the converter creates a JSON document. Elasticsearch receives the document and processes `name` and `category` using the mapping stored on the index. When searching, Elasticsearch uses the same mapping to determine how queries behave.

This is the easiest state to operate: application-side metadata and server mapping reflect the same data model.

## 5. What Happens When Annotations Change While the Index Already Exists?

Suppose the first version of the application declared:

    @Field(type = FieldType.Text)
    private String category;

After some time, the development team realizes `category` needs to be used for exact filtering and changes it to:

    @Field(type = FieldType.Keyword)
    private String category;

This change only modifies application-side metadata. If the `products` index already exists with `category` as `text`, the server mapping retains the `text` type until a valid mapping operation is executed or a new index is created.

Consequently, after deploying the new version:

- The application-side converter may be operating with `keyword` metadata.
- Elasticsearch still processes the field according to the existing `text` mapping.
- `term`, filter, sort, or aggregation queries may produce results different from expectations.
- The application may encounter errors when sending values or queries incompatible with the server mapping.

Changing an annotation does not equate to a mapping migration. Do not assume that on every application startup, Spring Data will delete the old index and recreate it according to the new entity.

### Checking a Mapping Mismatch Scenario

You can check annotations in source code against the actual mapping:

    GET products/_mapping

If the server returns:

    {
      "properties": {
        "category": {
          "type": "text"
        }
      }
    }

while the entity currently declares `FieldType.Keyword`, the two sides are out of sync. Determine whether the index is managed by the application or by an infrastructure/migration workflow before deciding on changes.

## 6. Creating Indexes and Mappings from Spring Data Metadata

Spring Data Elasticsearch provides `IndexOperations` to work with indexes. You can retrieve operations bound to an entity:

    IndexOperations indexOperations =
        operations.indexOps(Product.class);

When the index does not exist yet, the application can request creating the index together with the mapping generated from metadata:

    boolean created = indexOperations.createWithMapping();

This operation uses entity information to create the index and corresponding mapping. Depending on configuration, additional settings, analyzers, or custom mappings may need to be declared.

Spring Data also supports separate index creation and mapping operations:

    indexOperations.create();
    indexOperations.putMapping();

`create()` creates the index; `putMapping()` sends the mapping built from entity metadata. Use the appropriate operation for the index state and the Spring Data Elasticsearch version deployed.

You can inspect the index and mapping:

    boolean exists = indexOperations.exists();
    Map<String, Object> mapping = indexOperations.getMapping();

The APIs above illustrate managing indexes via Spring Data. For systems needing strict schema control, these operations should typically be placed in a deployment or intentional migration workflow rather than letting multiple application instances alter schemas concurrently.

### The `createIndex` Option on `@Document`

`@Document` has a `createIndex` attribute to control automatic index creation during the Spring Data Elasticsearch repository lifecycle. In common versions, the default value is `true`; you can set `createIndex = false` when indexes are managed externally.

Example:

    @Document(
        indexName = "products",
        createIndex = false
    )
    public class Product {
        // fields
    }

When indexes are managed by DBAs, DevOps, index templates, or a migration pipeline, setting `createIndex = false` makes clear that the application does not own automatic index creation in that repository mechanism.

This attribute does not mean Spring Data stops using metadata to convert entities. It only governs automatic index creation; the converter still needs `@Field`, `@Id`, and other metadata when reading/writing documents.

Index initialization behavior may vary across Spring Data versions and repository configurations. When a project relies on this automatic behavior, check the documentation for the exact version in use.

## 7. Updating the Mapping of an Existing Index

Elasticsearch allows updating mappings within certain limits. For instance, you can add a new field to an existing mapping:

    PUT products/_mapping
    {
      "properties": {
        "brand": {
          "type": "keyword"
        }
      }
    }

After updating, new documents can contain the `brand` field and Elasticsearch will process it as type `keyword`.

From Spring Data, you can call:

    indexOperations.putMapping();

This operation builds a mapping from the entity's current metadata. Before calling it, understand the current server mapping and Elasticsearch's limitations. `putMapping()` is not a tool that automatically converts every old field to a new type.

### Mapping Changes Generally Supported

Common operations:

- Adding new fields.
- Adding certain mapping attributes that Elasticsearch permits updating.
- Adding sub-fields to multi-fields in supported cases.
- Updating compatible settings allowed by the mapping API.

Specific update capabilities depend on the field type and mapping attribute. Do not infer that every value in an annotation can overwrite the server mapping with a single `putMapping` call.

### Changes That Cannot Be Modified Directly in the Usual Way

Certain attributes defining how data has already been indexed, such as changing a field type from `text` to `keyword`, usually cannot be modified directly on an existing field. Elasticsearch cannot re-derive and rebuild an existing inverted index into a new type solely from Java metadata.

If you need to change a field type, analyzer, or how data is indexed, the common solution is to create a new index with the proper mapping, reindex the data, and switch the application to the new index.

## 8. Why Is Reindexing Needed When Mapping Changes Are Incompatible?

A mapping is not just a data type label. It dictates how Elasticsearch analyzes and indexes documents. For example:

- `text` fields are analyzed into tokens for full-text search.
- `keyword` fields preserve exact values for exact matching.
- Analyzers dictate how terms are split, normalized, and tokenized.
- Numeric/date mappings determine how values are stored and compared.

If you change the mapping of a field that already holds data, old documents have already been indexed under the previous configuration. Updating Java metadata alone cannot regenerate inverted indexes, doc values, or analyzed tokens.

Typical migration workflow:

    Old index: products_v1
    Old mapping
          |
          v
    Create new index: products_v2
    New mapping
          |
          v
    Reindex data from v1 to v2
          |
          v
    Verify data and queries
          |
          v
    Switch alias products to v2
          |
          v
    Application continues accessing alias products

Example creating a new index:

    PUT products_v2
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Reindex:

    POST _reindex
    {
      "source": {
        "index": "products_v1"
      },
      "dest": {
        "index": "products_v2"
      }
    }

After verifying data, you can switch the alias:

    POST _aliases
    {
      "actions": [
        {
          "remove": {
            "index": "products_v1",
            "alias": "products"
          }
        },
        {
          "add": {
            "index": "products_v2",
            "alias": "products"
          }
        }
      ]
    }

The commands above illustrate the basic workflow. Systems actively writing data need a plan to synchronize changes occurring during reindexing, or pause writes during cutover. Verify document counts, failed documents, aliases, and application behavior before removing the old index.

A common organizational pattern is having `@Document(indexName = "products")` point to a stable alias. When changing mappings, the application still uses the alias; the migration process creates a new physical index and switches the alias after verification completes.

## 9. Dynamic Mapping and Differences from Java Metadata

Elasticsearch provides dynamic mapping to infer mappings automatically for new fields when receiving documents. For example, if an index permits dynamic mapping and the first document contains:

    {
      "name": "Coffee grinder",
      "stock": 12,
      "active": true
    }

Elasticsearch can automatically create mappings for `name`, `stock`, and `active` based on the data types it observes.

This does not mean Java metadata is synced with the server. Dynamic mapping is Elasticsearch behavior controlled by the index's mapping configuration. It can create fields not declared by the Java entity, or infer types different from what was intended in source code.

For example, a product code field consisting only of digits may be inferred as a numeric type if the first document sends a number. If the application later sends a string containing alphabetic characters, indexing can fail because the mapping was already fixed.

For data with a clear schema, declare explicit mappings for important fields, especially fields used for filtering, sorting, aggregations, or full-text search. You can use `dynamic = false` or `dynamic = strict` depending on requirements for controlling new fields; these two options behave differently and must be understood before applying.

## 10. Managing Mappings as Part of the Application Lifecycle

In small projects or learning environments, letting Spring Data auto-create indexes and mappings from entities can be convenient. As systems grow, mappings become part of the schema and require controlled management.

There are three common organizational patterns:

### Application Owns the Index

The application is responsible for creating the index from entity metadata. This is simple when only one application manages the index and the deployment environment lacks a separate migration process.

You can use `@Document(createIndex = true)` and `IndexOperations` APIs matching the application lifecycle. Avoid letting multiple instances perform uncoordinated changes simultaneously.

### Infrastructure or Migration Owns the Index

Indexes are created beforehand using scripts, index templates, or migration tools. The application sets `createIndex = false` and simply uses the prepared index.

This pattern helps control mappings, settings, analyzers, aliases, and deployment order. However, the development team must keep entity metadata consistent with infrastructure-managed mappings.

### Combining Metadata and Migration

Java entities still declare mapping metadata so the converter works and can serve as a reference source for mappings. A separate migration process handles creating indexes, updating updatable mappings, and reindexing when needed.

This approach fits when schema control across versions is needed. Every mapping change should have a clear deployment plan, be tested beforehand in an appropriate environment, and have a way to switch aliases or roll back to the old index when needed.

## 11. Workflow When Annotations and Server Mapping Diverge

When discovering that entity metadata differs from the actual mapping, proceed in sequence:

1. Identify the physical index the application is writing to/reading from. If using an alias, inspect every index behind the alias.
2. Read the current mapping with `GET index/_mapping`.
3. Compare each critical field against `@Field`, field names, and Java data types.
4. Determine whether the index is auto-created by the application or managed by migration/infrastructure.
5. Classify the change: adding a field, updating a supported attribute, or an incompatible change such as changing a field type.
6. For supported changes, update the mapping intentionally and verify data.
7. For incompatible changes, create a new index, reindex, and switch the alias after verification.
8. Verify write, search, filter, sort, and aggregation operations on the new index.

Do not resolve a mapping mismatch by deleting an index containing real data and letting the application recreate it, unless an approved backup and recovery plan is in place. Deleting an index destroys the data in that index.

## 12. Common Misconceptions

### Assuming `@Field` Is Already Stored on the Server

`@Field` is metadata inside the application. It can be used to generate a mapping during index creation or update mappings via supported operations, but the annotation itself is not configuration stored on the cluster.

### Assuming Changing an Annotation Changes the Old Index's Field Type

Mappings of existing fields have modification limits. If you need to change from `text` to `keyword` or alter how already indexed data is analyzed, you typically must create a new index and reindex.

### Assuming the Converter Decides How Elasticsearch Searches

The converter transforms objects and documents. The Elasticsearch server uses the index mapping to analyze, index, and execute queries. Both sides must be compatible, yet they hold different responsibilities.

### Assuming Creating a Repository Always Recreates the Index

Automatic index creation depends on `@Document(createIndex = ...)`, configuration, and Spring Data Elasticsearch version. Do not assume a repository will delete or recreate an existing index to match annotations.

### Assuming Dynamic Mapping Equals Entity Metadata

Dynamic mapping is inferred by Elasticsearch from submitted documents. It can create fields outside the entity or infer unintended types. For important schemas, declare mappings explicitly.

### Checking Only Java Code Without Inspecting the Actual Index

The entity may match the design while an index still exists from an older version. When investigating mapping errors, read `GET index/_mapping` and verify the actual physical index the application is using.

## Conclusion

Application-side mapping metadata and existing mappings on Elasticsearch are related yet independent parts. The `@Document`, `@Id`, and `@Field` annotations describe how Spring Data maps entities, converts documents, and can generate mapping definitions. The index mapping stored on Elasticsearch is the server configuration used to process data and queries.

When creating a new index, Spring Data can generate mappings from metadata via `IndexOperations` and configured automatic mechanisms. When an index already exists, editing annotations does not automatically alter the server mapping. Incompatible mapping changes usually require creating a new index, reindexing data, and switching aliases. Understanding this boundary helps prevent schema drift, reduce deployment errors, and manage the mapping lifecycle safely.
