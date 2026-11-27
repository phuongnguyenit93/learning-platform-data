# Multi-Field with `@MultiField` and `@InnerField`

In Elasticsearch, a string property sometimes needs to serve multiple usages. For example, a product name needs to be analyzed for full-text search while also being preserved intact for exact filtering, sorting, or aggregations. If you only declare the field as `text`, you get word-based search, but no built-in field suitable for sorting and aggregations. If you only declare `keyword`, you can match the full value, but you do not get the desired full-text search behavior.

**Multi-field** allows indexing the same value under multiple data types or different analysis strategies. In Spring Data Elasticsearch, the `@MultiField` annotation declares the main field, while `@InnerField` declares additional sub-fields.

## 1. What Problem Does Multi-Field Solve?

Suppose a product has the name:

`Wireless Mechanical Keyboard`

The application has the following needs:

- Users search for the product using the word `mechanical` or `keyboard`.
- The screen needs to sort products by name.
- A filter needs to find the exact name `Wireless Mechanical Keyboard`.
- A report needs to group or count documents by name.

These needs have different indexing strategies:

| Need | Appropriate field type |
|---|---|
| Searching by words, phrases, relevance | `text` |
| Matching the entire value | `keyword` |
| Sorting by string value | Usually `keyword` |
| Terms aggregation | Usually `keyword` |

Multi-field creates multiple access paths to the same source value:

- `name`: main field of type `text`, dedicated to full-text search.
- `name.keyword`: sub-field of type `keyword`, dedicated to exact matching, sorting, and aggregations.

These two fields are not two separate Java properties. They are two indexing representations of the same `name` property.

## 2. Mapping Structure of a Multi-Field

An Elasticsearch mapping for a multi-field has the form:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

This structure can be read as follows:

- `name` is the main field of type `text`.
- `analyzer: standard` specifies how text is analyzed for the main field.
- `fields` declares the multi-fields.
- `keyword` is the sub-field name.
- `type: keyword` keeps the value as a single token for intact matching and supports doc values.

When a document is indexed with data:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch indexes the value of `name` using the main field's analyzer, while simultaneously indexing the same value for the `name.keyword` sub-field. In `_source`, the application still stores a single `name` property; multi-field does not create an independent source property named `name.keyword`.

The name `keyword` is just a common convention. You can choose another name such as `raw`, `sort`, or `exact`, as long as the mapping and queries use the same name.

## 3. Declaring a Multi-Field with `@MultiField` and `@InnerField`

Spring Data Elasticsearch provides two annotations:

- `@MultiField`: placed on an entity property to declare a multi-field mapping.
- `@InnerField`: declares each additional sub-field, including the suffix and data type of the sub-field.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "standard"
        ),
        otherFields = {
            @InnerField(
                suffix = "keyword",
                type = FieldType.Keyword
            )
        }
    )
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

Meaning of the multi-field declaration:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword
        )
    }
)
private String name;
~~~

- `mainField` describes the main field `name`. In the example, the main field is `text` with the `standard` analyzer.
- `otherFields` is the list of sub-fields.
- `@InnerField` declares a sub-field with suffix `keyword` and type `Keyword`.
- Spring Data combines the property name `name` with the suffix to generate the sub-field path `name.keyword` in the mapping.

Multiple sub-fields can be declared if one value needs multiple usages:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword
        ),
        @InnerField(
            suffix = "raw",
            type = FieldType.Keyword
        )
    }
)
private String title;
~~~

The corresponding mapping contains `title`, `title.keyword`, and `title.raw`. In practice, avoid creating many sub-fields unless there is a specific query need, because each additional field increases storage and indexing overhead.

## 4. Querying the Main Field and Sub-Field

Once the mapping is in effect, choose the right field path for each query type.

### Full-Text Search on the Main Field

Use `match` with `name`:

~~~json
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Elasticsearch analyzes the query string with the appropriate search analyzer and compares the tokens against the indexed data on the main field.

### Exact Match with the Sub-Field

Use `term` with `name.keyword`:

~~~json
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

`term` does not analyze input like `match`. For a default keyword field, the value must match the indexed value. Case sensitivity also applies unless a normalizer is configured.

### Sorting by Name

Use the keyword sub-field:

~~~json
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

Sorting on `text` is not a typical choice because text fields do not have doc values by default. Keyword fields are designed to support efficient sort operations.

### Aggregating by Name

~~~json
{
  "aggs": {
    "products_by_name": {
      "terms": {
        "field": "name.keyword"
      }
    }
  }
}
~~~

A terms aggregation groups documents by the value of the keyword sub-field. If the field has a very large number of unique values, consider cardinality and aggregation cost before using it as a reporting dimension.

### Combining Full-Text Search and Exact Filtering

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "name.keyword": "Wireless Mechanical Keyboard"
          }
        }
      ]
    }
  }
}
~~~

In the example, `must` searches content on the `text` main field; `filter` applies filtering conditions on keyword fields. A single query can use both fields of the same property simultaneously.

## 5. Using Multi-Fields with Spring Data Elasticsearch

Once `@MultiField` is declared, Spring Data Elasticsearch can generate the mapping from entity metadata. The application works with the entity as usual; there is no need to create a separate Java property for `name.keyword`.

Example of creating an index and mapping using `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndex() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

`indexOps(Product.class)` retrieves the index operations bound to the `Product` entity. `createWithMapping()` creates the index together with the mapping inferred from entity metadata, including the multi-field declaration.

This is an example illustrating how to initialize an index. In real applications, manage index creation timing via migrations or an appropriate deployment workflow, avoiding multiple application instances performing index creation at startup simultaneously.

When saving an entity:

~~~java
Product product = new Product();
product.setName("Wireless Mechanical Keyboard");

productRepository.save(product);
~~~

Spring Data saves a single `name` value in the document. Elasticsearch indexes that value for the main field and its sub-fields according to the created mapping.

When searching via a repository, standard query derivation methods operate on Java properties. For queries that need to explicitly reference a multi-field path such as `name.keyword`, you can use custom Elasticsearch queries or `ElasticsearchOperations` to specify the exact field path.

## 6. Distinguishing `@InnerField` from Object and Nested Fields

The name `@InnerField` can mislead learners into thinking it is how nested objects are declared. In multi-field, `@InnerField` means **an additional indexing representation for the same field value**.

Multi-field example:

~~~text
name
├── name (text)
└── name.keyword (keyword)
~~~

These are not two nested objects in JSON. The source data is still:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Meanwhile, an object field describes a data structure with child properties:

~~~json
{
  "manufacturer": {
    "name": "Acme",
    "country": "VN"
  }
}
~~~

An object mapping can declare fields like `manufacturer.name` and `manufacturer.country`. Nested mapping is a different data type used when relationships between objects inside an array must be preserved according to Elasticsearch semantics.

| Characteristic | Multi-field | Object / Nested |
|---|---|---|
| Purpose | Index the same value in multiple ways | Describe structured data with child properties |
| Related annotations | `@MultiField`, `@InnerField` | `@Field(type = Object/Nested)` and child property mappings |
| Path example | `name.keyword` | `manufacturer.name` |
| Creates extra objects in `_source`? | No | Yes, matching the source data structure |

## 7. Combining Analyzer and Normalizer

Multi-field is useful when the same value needs different analysis rules.

For example, the main field uses the `standard` analyzer for full-text search, while the keyword sub-field uses a normalizer for case-insensitive matching:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer"
          }
        }
      }
    }
  }
}
~~~

In Spring Data Elasticsearch, you can declare the normalizer on `@InnerField` according to the annotation API of the version in use:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword,
            normalizer = "lowercase_normalizer"
        )
    }
)
private String name;
~~~

The normalizer must be defined in the index settings before the mapping references it. Merely declaring a normalizer name in the annotation without creating the corresponding configuration in index settings will make the mapping invalid when creating the index.

Do not confuse an analyzer with a normalizer:

- An analyzer can produce multiple tokens, suitable for full-text search.
- A normalizer transforms a keyword value while keeping the output as a single token.

The choice of analyzer/normalizer must be consistent with how the application intends to search and match data.

## 8. Considerations When Changing Mappings

Multi-fields are part of the index mapping. Modifying Java annotations does not automatically alter an existing mapping in Elasticsearch.

### When Creating a New Index

When the index does not exist yet, Spring Data can create the mapping from entity metadata. Ensure the mapping is created before writing data that requires multi-fields.

### When the Index Already Exists

If the `name` field already exists as type `text`, Elasticsearch allows adding a multi-field to the mapping via the update mapping API in supported cases:

~~~http
PUT /products/_mapping
Content-Type: application/json

{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

However, adding a sub-field to the mapping does not automatically reindex values of older documents for the new sub-field. Documents indexed before the mapping update may not have data in `name.keyword` in the inverted index/doc values.

An update or reindex step is needed so existing documents are reindexed under the new mapping. For example, you can use update by query to instruct Elasticsearch to reindex existing documents, or create a new index with the complete mapping and reindex data into the new index.

### Cannot Arbitrarily Change the Main Field Type

If `name` is already `text`, you cannot simply change the annotation to `keyword` and expect Elasticsearch to change the field type in the current index. Changing the type of an already-indexed field generally requires a new index and reindexing.

Multi-fields are often designed from the start to avoid having to change the main field structure later.

## 9. Common Mistakes

### Querying the Wrong Field

If you use `term` with `name` expecting a full-sentence match, results may be incorrect because `name` is an analyzed text field. Use `name.keyword` for full-value matching.

Conversely, if you use `match` on `name.keyword`, the keyword field still has only one token for the entire value. It does not behave like word-by-word search on a text field.

### Sorting on a Text Field

Sorting by `name` can fail because `text` does not enable doc values by default. Use `name.keyword` for sorting.

### Aggregating on a Text Field

Terms aggregation on `text` is usually rejected because fielddata is disabled by default. Use a keyword multi-field instead of enabling fielddata solely to group values.

### Forgetting to Create or Update the Mapping

If the index does not have `name.keyword`, queries or sorts on this field path will not work as expected. Inspect the actual index mapping instead of checking only Java annotations.

### Adding a Multi-Field Without Reindexing Old Data

The mapping may already show `name.keyword`, yet old documents still lack indexed values for the sub-field. Reindex or update old documents.

### Creating Too Many Multi-Fields

Every additional sub-field increases storage and indexing costs. Only create a sub-field when a query, sort, or aggregation genuinely needs that indexing strategy.

## 10. Workflow for Choosing and Using Multi-Fields

When designing an entity:

1. Identify all the ways the application will use a string property.
2. Choose the data type for the main field, usually `text` if full-text search is needed.
3. Add an `@InnerField` of type `Keyword` if exact filtering, sorting, or aggregation is needed.
4. Choose meaningful suffixes, such as `keyword`, `raw`, or `sort`.
5. Configure the right analyzer and normalizer for your needs.
6. Create the index with mappings from the entity before indexing data.
7. Use the main field for full-text queries and the sub-field for exact matching/sorting/aggregation.
8. When the mapping already exists, plan mapping updates and reindexing old data if adding a multi-field.

Quick reference table:

| Annotation / field | Role |
|---|---|
| `@MultiField` | Declares a property indexed under multiple fields |
| `mainField` | Configures the main field |
| `otherFields` | List of additional sub-fields |
| `@InnerField` | Declares the suffix and data type of a sub-field |
| `name` | Main field, e.g., `text` |
| `name.keyword` | Sub-field, e.g., `keyword` |

## Conclusion

Multi-fields allow Elasticsearch to index the same value in multiple ways to satisfy different query requirements. In Spring Data Elasticsearch, `@MultiField` defines the main field and list of sub-fields; `@InnerField` defines each sub-field with its own suffix and data type. Use the main field for full-text search, the keyword field for exact filtering, sorting, and aggregations, and ensure mappings and old data are properly updated when modifying an index.
