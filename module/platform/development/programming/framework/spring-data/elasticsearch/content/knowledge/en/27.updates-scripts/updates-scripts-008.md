# Scripted Fields and Runtime Fields in Search

## 1. Why Are Computed Fields Needed During Search?

Documents in Elasticsearch usually contain indexed fields such as name, status, creation date, or price. However, an application sometimes needs a value derived from existing fields without writing that extra value into the document.

For example, a product has:

~~~json
{
  "name": "Wireless Headphones",
  "category": "audio",
  "price": 1200000,
  "taxRate": 0.1
}
~~~

The application may need to display the price including tax:

\[
priceWithTax = price \times (1 + taxRate)
\]

Or an order might need to:

- Compute total amount from quantity and unit price.
- Concatenate full name from first name and last name.
- Categorize an order based on item count.
- Calculate the number of days since creation.
- Normalize a value for filtering.
- Build a label from multiple existing fields.

These values can be computed in Java after receiving the documents. However, when the computed value must be used within the search operation itself, post-processing is insufficient. For example, the application wants to find all products whose price with tax is 1,500,000 or higher. If it is only calculated after receiving results, Elasticsearch cannot filter documents by that value.

Elasticsearch supports two key mechanisms:

- **Scripted field (`script_fields`):** runs a script for each selected hit and adds the computed value to the response.
- **Runtime field:** defines a field evaluated at search time. This field can participate in queries, filters, sorts, aggregations, and can be returned to the application.

Both allow deriving values from stored data. The main difference is that runtime fields can participate in document selection, whereas scripted fields only enrich hits that have already been selected.

## 2. Distinguishing Scripted Fields and Runtime Fields

Both concepts can use Painless and read document data, but they serve different purposes.

| Criterion | Scripted field | Runtime field |
|---|---|---|
| Elasticsearch API | `script_fields` | `runtime_mappings` or `runtime` in mapping |
| Execution timing | Fetch phase, after the query selects hits | Query time, when the field is used in search |
| Filter documents by computed value | No | Yes |
| Sort by computed value | No | Yes |
| Aggregate by computed value | No | Yes |
| Return value in response | Yes, under `fields` | Can use `fields` to retrieve values |
| Declaration scope | A single search request | A single search request or an index mapping |
| Writes value to `_source` | No | Not by default |
| Painless return syntax | Returns value via `return` or last expression | Uses `emit(...)` |

Example requirements:

- Only want to display price with tax for 20 already-matched products: use a scripted field.
- Want to find products whose price with tax exceeds a threshold: use a runtime field.
- Want to bucket products by price with tax: use a runtime field.
- Want to sort products by price with tax: use a runtime field.

Keep in mind:

~~~text
Scripted field
  Query selects documents
        |
        v
  Script computes value for each hit
        |
        v
  Response includes computed field

Runtime field
  Declare field and script
        |
        v
  Query / Filter / Sort / Aggregation
        |
        v
  Value is evaluated when needed
        |
        v
  Response can return computed field
~~~

Do not use scripted fields when you need to filter or sort by the computed value. Conversely, if you only need to decorate data in the response, a runtime field might perform unnecessary work in the query phase.

## 3. Painless and Script Execution Contexts

Elasticsearch uses **Painless** as its default scripting language. Painless is designed to execute scripts in Elasticsearch contexts such as search, scoring, aggregations, document updates, and ingest.

A script typically has three parts:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value * params.taxRate",
    "params": {
      "taxRate": 1.1
    }
  }
}
~~~

- `lang`: scripting language; typically `painless`.
- `source`: inline script body.
- `params`: parameters passed to the script.

Painless provides different variables and APIs depending on the context. Therefore, the same expression may require a different way to return its result.

### Common Variables

| Variable | Meaning |
|---|---|
| `doc` | Accesses field values via doc values |
| `params` | Parameters passed in by the request |
| `params._source` | Accesses the document's `_source` content |
| `ctx` | Document context in certain update or ingest operations |
| `emit()` | Emits values for a runtime field |

In scripted fields and runtime fields, `doc['field']` is typically used to read fields that have doc values. This is usually much more efficient than loading and parsing the entire `_source`.

Not every field has doc values. Analyzed `text` fields usually do not have doc values by default. Do not enable `fielddata` on `text` just to run scripts without evaluating memory and CPU costs.

### Accessing Field Values

Example reading price:

~~~java
double price = doc['price'].value;
~~~

In Painless, `doc['price']` is the list of values for that field. For single-valued fields, `.value` retrieves that value.

If a field might be missing, check before reading:

~~~java
if (doc.containsKey('price') && doc['price'].size() != 0) {
    // Safe to read doc['price'].value
}
~~~

`doc.containsKey('price')` checks whether the field exists in the mapping. `doc['price'].size() != 0` checks whether the current document has a value for that field.

If you omit these checks and a document lacks a price, the script can throw an error when accessing `.value`.

### Accessing `_source`

You can read data from `_source`:

~~~java
def name = params._source['name'];
~~~

This is useful when you need to read object structures or data without doc values. However, `_source` must be loaded and parsed, which is typically slower than reading a value via doc values.

Prefer `doc['field']` whenever possible. Use `_source` when you truly need the JSON structure or data not exposed via doc values.

## 4. Scripted Fields in Elasticsearch

Scripted fields are declared in the `script_fields` section of a search request. The script runs for each selected hit and adds a computed value to the response.

Example calculating price with tax:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "script_fields": {
    "price_with_tax": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value * params.taxRate",
        "params": {
          "taxRate": 1.1
        }
      }
    }
  }
}
~~~

The query selects products in the `audio` category. Then, the scripted field computes the price with tax for each returned hit.

The response has a structure similar to:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-01",
        "_source": {
          "name": "Wireless Headphones",
          "category": "audio",
          "price": 1200000
        },
        "fields": {
          "price_with_tax": [
            1320000.0
          ]
        }
      }
    ]
  }
}
~~~

The computed value appears in `fields.price_with_tax` and is not written to `_source`.

A scripted field can return one value or multiple values. Elasticsearch typically represents data under `fields` as an array, even when there is only a single value.

### Scripted Fields Do Not Participate in Query Conditions

You cannot use `price_with_tax` in a `range` query within the same request simply because it was declared in `script_fields`.

The following example will not work as intended:

~~~json
{
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1500000
      }
    }
  },
  "script_fields": {
    "price_with_tax": {
      "script": {
        "source": "doc['price'].value * 1.1"
      }
    }
  }
}
~~~

The query phase must select documents before the fetch phase executes scripted fields. Therefore, queries cannot filter documents using scripted field results. Convert the calculation into a runtime field if you need to filter by that value.

## 5. Runtime Fields in Elasticsearch

A runtime field is a field evaluated at search time rather than stored like a normal field in the inverted index or doc values.

There are two places to declare a runtime field:

1. In the index mapping, under `runtime`.
2. In a search request, under `runtime_mappings`.

Runtime fields can be used in:

- Queries and filters.
- Range queries.
- Sorts.
- Aggregations.
- The `fields` section of the response.

When declaring a runtime field, the script must call `emit(...)` to emit values. A script can call `emit` multiple times to produce a multi-valued field. `emit` does not accept `null`; if a document has no valid data, do not call `emit`.

### Runtime Fields Scoped to a Single Search Request

Example computing price with tax within a single request:

~~~http
GET /products/_search
{
  "runtime_mappings": {
    "price_with_tax": {
      "type": "double",
      "script": {
        "source": """
          if (doc.containsKey('price') && doc['price'].size() != 0) {
            emit(doc['price'].value * params.taxRate);
          }
        """,
        "params": {
          "taxRate": 1.1
        }
      }
    }
  },
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1500000
      }
    }
  },
  "fields": [
    "price_with_tax"
  ]
}
~~~

Elasticsearch creates the `price_with_tax` runtime field for the scope of this request. The range query can use that field to select documents.

Runtime fields declared here are not permanently added to the index mapping. Other requests needing the same field must redeclare the runtime mapping or use a runtime field already defined in the mapping.

### A Runtime Field Can Shadow a Mapped Field Within a Request

If a runtime field has the same name as an existing field in the mapping, the request-level runtime field definition can override that field's values for the scope of the search.

This feature is useful for testing new calculation formulas or checking data before changing mappings. However, be cautious when reusing field names because queries may no longer use the indexed values readers of the request expect.

## 6. Using Runtime Fields in Filters, Sorts, and Aggregations

Runtime fields can participate in search components just like normal fields.

Example calculating price with tax, filtering by price range, sorting, and grouping by category:

~~~http
GET /products/_search
{
  "runtime_mappings": {
    "price_with_tax": {
      "type": "double",
      "script": {
        "source": "emit(doc['price'].value * params.taxRate)",
        "params": {
          "taxRate": 1.1
        }
      }
    }
  },
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1000000,
        "lte": 2500000
      }
    }
  },
  "sort": [
    {
      "price_with_tax": {
        "order": "asc"
      }
    }
  ],
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 10
      },
      "aggs": {
        "average_price_with_tax": {
          "avg": {
            "field": "price_with_tax"
          }
        }
      }
    }
  },
  "fields": [
    "price_with_tax"
  ]
}
~~~

In the request:

- The runtime field computes price with tax.
- The range query keeps only products within the price range.
- Sort orders results by price with tax.
- The terms aggregation groups by category.
- The `avg` metric computes the average price with tax within each bucket.
- `fields` requests returning the runtime field value for each hit.

This is the crucial distinction compared to scripted fields. Scripted fields only enrich already-selected hits; runtime fields can influence hit selection and ordering themselves.

## 7. Defining Runtime Fields in the Index Mapping

If many requests need the same runtime field, you can define it in the mapping so you do not have to resend the script with every search request.

Example creating an index:

~~~http
PUT /products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    },
    "runtime": {
      "price_with_tax": {
        "type": "double",
        "script": {
          "source": """
            if (doc.containsKey('price') && doc['price'].size() != 0) {
              emit(doc['price'].value * params.taxRate);
            }
          """,
          "params": {
            "taxRate": 1.1
          }
        }
      }
    }
  }
}
~~~

Once the runtime field is declared in the mapping, requests can use it without sending `runtime_mappings`:

~~~http
GET /products/_search
{
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1500000
      }
    }
  },
  "fields": [
    "price_with_tax"
  ]
}
~~~

A runtime field in the mapping has shared scope across requests on the index. A runtime field in a search request exists only for that request.

When you need to modify a regular runtime field in the mapping, you can update or delete its definition via the Mapping API. Note that changing a definition while queries are running may cause shards to observe different mapping versions during the update window.

## 8. Choosing a Runtime Field Data Type

Runtime fields require a data type declaration so Elasticsearch knows how to handle values emitted by the script.

Common runtime field types include:

| Type | Emitted values | Usage examples |
|---|---|---|
| `boolean` | `true` or `false` | Whether an order was delivered late |
| `date` | Date/time values | Date derived from a timestamp |
| `double` | Floating-point numbers | Price with tax, conversion rate |
| `long` | Integer numbers | Age, number of days, quantity |
| `keyword` | Unanalyzed strings | Status buckets, classification labels |
| `ip` | IP addresses | Normalized or derived address |
| `geo_point` | Geographic points | Point computed from other data |

Example `keyword` runtime field categorizing orders:

~~~json
{
  "runtime_mappings": {
    "order_size": {
      "type": "keyword",
      "script": {
        "source": """
          if (doc['quantity'].size() == 0) {
            return;
          }

          long quantity = doc['quantity'].value;

          if (quantity == 1) {
            emit('single');
          } else if (quantity <= 3) {
            emit('small');
          } else if (quantity <= 6) {
            emit('medium');
          } else {
            emit('large');
          }
        """
      }
    }
  },
  "aggs": {
    "order_sizes": {
      "terms": {
        "field": "order_size"
      }
    }
  }
}
~~~

The `order_size` runtime field can be used in a terms aggregation to count orders by bucket.

If a script can emit multiple values for the same document, call `emit` multiple times. The type of every emitted value must match the declared runtime field type.

## 9. Checking for Missing Fields and Invalid Data

One of the most common bugs is accessing `.value` when a document has no value for the field.

Unsafe example:

~~~painless
emit(doc['price'].value * 1.1);
~~~

If the `price` field is absent from the mapping or the current document has no value, the script can throw an error.

Safe check:

~~~painless
if (doc.containsKey('price') && doc['price'].size() != 0) {
    emit(doc['price'].value * 1.1);
}
~~~

The two conditions guard two different situations:

- `doc.containsKey('price')`: the field exists in the mapping.
- `doc['price'].size() != 0`: the current document has at least one value.

If data might be negative or outside business bounds, add extra checks before calculating.

Example:

~~~painless
if (doc.containsKey('price') && doc['price'].size() != 0) {
    double price = doc['price'].value;

    if (price >= 0 && price <= params.maxPrice) {
        emit(price * params.taxRate);
    }
}
~~~

Do not call `emit(null)`. If there is no valid value, skip emitting for that document.

## 10. Script Parameters and Compilation Cache

Elasticsearch compiles scripts and stores the compiled version in a cache. If an application alters the `source` string on every request just to swap a number, Elasticsearch may have to compile many distinct scripts.

Do not build script sources by string concatenation:

~~~java
String source = "doc['price'].value * " + taxRate;
~~~

Keep the source stable and pass changing data via `params`:

~~~json
{
  "script": {
    "source": "doc['price'].value * params.taxRate",
    "params": {
      "taxRate": 1.1
    }
  }
}
~~~

When `taxRate` changes, Elasticsearch can still reuse the compiled script because the source text is unchanged.

Benefits:

- Reduces script compilation counts.
- Reuses the compiled script cache.
- Makes input values easier to control.
- Avoids generating distinct sources from user data.
- Separates calculation logic from business parameters.

If the same script is used across many places, consider a stored script. The application sends the stored script's ID along with `params` instead of sending the full source on every request.

## 11. Accessing Doc Values and `_source` in Scripts

There are two common ways to read document data:

~~~painless
doc['price'].value
~~~

and:

~~~painless
params._source['price']
~~~

`doc['field']` accesses doc values. Doc values are organized column-wise, making them suited for reading a field across many documents. This is generally the preferred way for search and aggregation scripts.

`params._source` reads the document's original JSON structure. This fits cases needing access to nested objects or fields without doc values, though Elasticsearch must load and parse `_source`, making it typically more expensive.

| Read method | Advantage | Limitation |
|---|---|---|
| `doc['field']` | Typically faster, suited for many documents | Only accesses values with doc values; does not return JSON objects |
| `params._source` | Reads original JSON structure | Must load and parse source, typically slower |

Example scripted field concatenating a name from two fields:

~~~json
{
  "script_fields": {
    "full_name": {
      "script": {
        "lang": "painless",
        "source": "params._source['first_name'] + ' ' + params._source['last_name']"
      }
    }
  }
}
~~~

If `first_name` and `last_name` may be missing, check for `null` or existence in the script before concatenating.

Do not enable `fielddata` on `text` just to read it from scripts without evaluating the cost. To read raw strings, a `keyword` field or `keyword` multi-field is usually more appropriate.

## 12. Spring Data Elasticsearch Support for Scripted Fields

Spring Data Elasticsearch provides two similarly named components:

- Annotation `org.springframework.data.elasticsearch.annotations.ScriptedField`: marks an entity property as the target receiving a scripted field value from the response.
- Class `org.springframework.data.elasticsearch.core.query.ScriptedField`: describes a scripted field to send in a query.

The annotation on the entity tells Spring Data not to create a regular mapping for that property. The property serves as a receiver for computed values when mapping search results.

Example product entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.ScriptedField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @ScriptedField
    private Double priceWithTax;

    // Constructors, getters, and setters
}
~~~

`priceWithTax` is not a field written to `_source` when saving the product. It is a property to receive the value returned by a scripted field in the search response.

You can use the annotation's `name` attribute if the scripted field name in the response differs from the Java property name:

~~~java
@ScriptedField(name = "price_with_tax")
private Double priceWithTax;
~~~

## 13. Creating `ScriptedField` in Spring Data Elasticsearch

Spring Data provides `ScriptedField` along with `ScriptData` to describe scripts.

Example calculating price with tax:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.ScriptData;
import org.springframework.data.elasticsearch.core.query.ScriptedField;

ScriptData scriptData = ScriptData.of(
    "painless",
    "doc['price'].value * params.taxRate",
    null,
    Map.of("taxRate", 1.1)
);

ScriptedField scriptedField = ScriptedField.of(
    "priceWithTax",
    scriptData
);
~~~

`ScriptData.of` accepts:

1. Script language, here `painless`.
2. Script source content.
3. Stored script name if using a stored script; `null` for this inline example.
4. Map of parameters passed to the script.

Next, attach the scripted field to the query:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery("""
    {
      "match_all": {}
    }
    """);

query.addScriptedField(scriptedField);

query.addSourceFilter(
    FetchSourceFilter.of(b -> b.withIncludes("*"))
);

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

`addScriptedField` adds the script to the `script_fields` section of the search request. The source filter is configured to also retrieve regular fields from the document source alongside the computed value.

Spring Data maps the `priceWithTax` value in the response into the entity property annotated with `@ScriptedField`.

Reading the results:

~~~java
for (var hit : hits) {
    Product product = hit.getContent();

    System.out.println(product.getPrice());
    System.out.println(product.getPriceWithTax());
}
~~~

`priceWithTax` only has a value in search results produced by requests containing that scripted field. When saving or reading the entity via normal operations, do not expect this property to be computed automatically.

## 14. Using `ScriptedField` in Repositories

You can pass a scripted field into a repository method. Example:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.ScriptedField;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    SearchHits<Product> findAllBy(ScriptedField scriptedField);
}
~~~

When invoked:

~~~java
SearchHits<Product> hits =
    repository.findAllBy(scriptedField);
~~~

Spring Data uses the passed-in scripted field to populate the value in results.

This is convenient when the repository method only needs a basic search query and a specific set of scripted fields. If you need to combine multiple query conditions, runtime mappings, sorts, or complex aggregations, using `ElasticsearchOperations` with a `Query` implementation is clearer.

## 15. Spring Data Elasticsearch Support for `RuntimeField`

Spring Data provides the class:

`org.springframework.data.elasticsearch.core.query.RuntimeField`

Common constructor:

~~~java
new RuntimeField(
    "priceWithTax",
    "double",
    "emit(doc['price'].value * params.taxRate)",
    Map.of("taxRate", 1.1)
);
~~~

Parameters:

- Runtime field name.
- Field data type.
- Painless script.
- Parameter map for the script.

Complete example:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.RuntimeField;

RuntimeField runtimeField = new RuntimeField(
    "priceWithTax",
    "double",
    "emit(doc['price'].value * params.taxRate)",
    Map.of("taxRate", 1.1)
);
~~~

Unlike scripted fields, runtime scripts must call `emit` to emit values. The `double` type indicates the computed value is a floating-point number.

If the field might be missing, add a check:

~~~java
RuntimeField runtimeField = new RuntimeField(
    "priceWithTax",
    "double",
    """
    if (doc.containsKey('price') && doc['price'].size() != 0) {
        emit(doc['price'].value * params.taxRate);
    }
    """,
    Map.of("taxRate", 1.1)
);
~~~

## 16. Using `RuntimeField` in `CriteriaQuery`

You can attach a runtime field to `CriteriaQuery` and then use that field in search conditions.

Example finding audio products with price including tax greater than or equal to a minimum threshold:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.core.query.RuntimeField;

RuntimeField runtimeField = new RuntimeField(
    "priceWithTax",
    "double",
    "emit(doc['price'].value * params.taxRate)",
    Map.of("taxRate", 1.1)
);

CriteriaQuery query = CriteriaQuery.builder(
        Criteria.where("category").is("audio")
            .and("priceWithTax").greaterThanEqual(1500000)
    )
    .withRuntimeFields(List.of(runtimeField))
    .withFields("priceWithTax")
    .withSourceFilter(
        FetchSourceFilter.of(b -> b.withIncludes("*"))
    )
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Steps:

1. Create a runtime field named `priceWithTax`.
2. Attach the runtime field to the query with `withRuntimeFields`.
3. Use `priceWithTax` in `Criteria` to filter.
4. Use `withFields` to request the runtime field value in the response.
5. Use a source filter to retrieve regular document fields.
6. Execute via `ElasticsearchOperations.search`.

In the example, the runtime field is computed for the documents needed to evaluate the search criteria. The result can be mapped to the `priceWithTax` property annotated with `@ScriptedField` on the entity.

If using another `Query` implementation, Spring Data also provides `addRuntimeField(runtimeField)` to add a runtime field to the query.

## 17. Using `RuntimeField` in Repository Methods

Spring Data Elasticsearch also allows passing a runtime field into a repository method:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.RuntimeField;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    SearchHits<Product> findByCategoryAndPriceWithTaxGreaterThanEqual(
        String category,
        Double minimumPrice,
        RuntimeField runtimeField
    );
}
~~~

When invoked:

~~~java
SearchHits<Product> hits =
    repository.findByCategoryAndPriceWithTaxGreaterThanEqual(
        "audio",
        1500000.0,
        runtimeField
    );
~~~

The runtime field is added to the query method so the condition can use the computed field.

This is useful when the query fits derived query methods. For multi-branch queries, multiple runtime fields, or fine-grained request control, a custom repository implementation or `ElasticsearchOperations` is clearer.

## 18. Declaring Runtime Fields in Mapping via Spring Data

If a runtime field is used across many queries, you can define it in a JSON file on the classpath and bind it to the entity with `@Mapping`.

Example `runtime-fields.json` file:

~~~json
{
  "priceWithTax": {
    "type": "double",
    "script": {
      "source": "emit(doc['price'].value * params.taxRate)",
      "params": {
        "taxRate": 1.1
      }
    }
  }
}
~~~

Entity:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;

@Document(indexName = "products")
@Mapping(runtimeFieldsPath = "/runtime-fields.json")
public class Product {
    // Entity properties
}
~~~

`runtimeFieldsPath` points to a JSON resource on the classpath. When Spring Data creates the index mapping, the runtime field definition is included in the mapping.

Queries can then use `priceWithTax` without passing runtime mappings on each request.

Example:

~~~java
CriteriaQuery query = new CriteriaQuery(
    Criteria.where("priceWithTax").greaterThanEqual(1500000)
);

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

A runtime field defined in the mapping can be reused across many requests. Make sure the index has been created with the mapping containing the runtime field before executing queries.

## 19. When to Use Scripted Fields, Runtime Fields, or Regular Fields?

Choosing a mechanism depends on where the computed value is needed and how frequently the calculation runs.

| Requirement | Choice |
|---|---|
| Only display an extra value for already-matched hits | Scripted field |
| Filter documents by computed value | Runtime field |
| Sort by computed value | Runtime field |
| Aggregate by computed value | Runtime field |
| Use a computed value across many queries | Runtime field in mapping |
| Experiment with calculation logic in a single request | Runtime field in `runtime_mappings` |
| Calculation used frequently and needs high performance | Consider pre-computing before indexing |
| Value is stable business data queried often | Regular stored/indexed field |

Example with price including tax:

- If the UI only displays price with tax on the results page: a scripted field is enough.
- If users have a price-with-tax filter: runtime field.
- If every query, report, and sort needs price with tax: consider calculating the price when writing the document and storing it as a regular field.

Runtime fields let you experiment with schemas without reindexing. However, if a field is used continuously in filters or sorts over large datasets, recomputing at query time can be resource-intensive. Once the logic stabilizes, consider moving the value into an ingest pipeline or computing it in the application before indexing.

## 20. Performance of Scripted Fields and Runtime Fields

Scripts can slow down searches if executed across many documents or performing heavy calculations.

Scripted fields execute in the fetch phase for returned hits. Consequently, limiting page size helps control script execution counts. Still, if an application requests thousands of hits, the script can take significant time.

Runtime fields can be used in queries, filters, sorts, and aggregations. When a runtime field condition must be evaluated over a vast number of documents, the cost can be much higher than simply computing values for the final hits.

Key principles:

- Create computed fields only when the application genuinely needs them.
- Keep scripts short and avoid loops or large data processing.
- Prefer doc values via `doc['field']`.
- Avoid accessing `_source` unless JSON structure is required.
- Use `params` instead of interpolating values into script sources.
- Limit page sizes when using scripted fields.
- Pair runtime fields with standard filters to narrow the candidate dataset whenever logic permits.
- If a field is used frequently, consider storing the result at ingest time.
- Monitor search latency and script compilation counts.
- Guard against script errors on missing or mistyped data.

Elasticsearch caches compiled scripts to avoid recompiling identical scripts. The cache works best when `source` stays constant and varying inputs are passed via `params`.

## 21. Indexed Runtime Fields in Supporting Elasticsearch Versions

Standard runtime fields are evaluated when queries reference them. Some newer Elasticsearch versions also support **indexed runtime fields**, converting a runtime field into an indexed form to accelerate query performance.

This concept differs from query-time-only runtime fields:

| Type | How it works |
|---|---|
| Standard runtime field | Computes value when needed by a query |
| Indexed runtime field | Computes and indexes values to serve queries faster |

Indexed runtime fields suit cases where calculation logic has stabilized and values are queried frequently. Elasticsearch can leverage the indexed values instead of running the script on every query.

There is an important constraint: once a runtime field has been indexed under this mechanism, you cannot update that field's script like a standard runtime field. To change logic, you must create a new field with the new script and run an appropriate data-indexing workflow.

Availability depends on the Elasticsearch version. Check your cluster version's documentation before designing mappings. Do not assume every cluster supports indexed runtime fields.

## 22. Common Mistakes

**Using scripted fields to filter documents.** Scripted fields run only after the query has selected hits. Use a runtime field if the value must participate in search conditions.

**Forgetting `emit` in a runtime field.** Runtime fields require calling `emit(value)` to return values. Scripts with only `return` do not satisfy this requirement.

**Using `emit` in a scripted field.** Scripted fields run in the field context and return results via expressions or `return`; `emit` is a runtime field mechanism.

**Not checking for missing fields.** Accessing `.value` when a field is absent from the mapping or document can fail. Check `doc.containsKey` and `doc['field'].size()`.

**Calling `emit` with `null`.** `emit` does not accept `null`. If no valid value exists, omit calling `emit`.

**Confusing computed fields with `_source` fields.** Scripted fields and runtime fields do not write results into `_source`. Values are returned under `fields` or used during query evaluation.

**Forgetting to request runtime fields in the response.** When you need to read the computed value, request the field via `fields` or `withFields(...)`.

**Failing to retrieve normal source in Spring Data.** When adding scripted or runtime fields, configure an appropriate source filter so the entity's original properties are still fetched.

**Changing script source on every request.** This increases compilation counts. Use `params` to keep `source` stable.

**Using `_source` for all calculations.** Accessing `_source` is typically slower than doc values. Use it only when structured data or fields without doc values are needed.

**Using runtime fields for heavily queried values without performance evaluation.** If a field is queried or sorted constantly, consider indexing the computed value or using indexed runtime fields if supported.

**Confusing the two `ScriptedField` types in Spring Data.** The `@ScriptedField` annotation in `annotations` is for entity properties; the `ScriptedField` class in `core.query` builds queries. They share the same simple name but serve different roles.

**Misconfiguring `runtimeFieldsPath`.** The JSON file must reside on the classpath and follow the runtime mapping format. If the file is missing or invalid JSON, mapping creation may fail.

## 23. Project Implementation Workflow

You can follow this sequence:

1. Determine whether the computed value is only for display or needed in queries.
2. If only displaying on hits, choose a scripted field.
3. If needed in filters, sorts, or aggregations, choose a runtime field.
4. Determine the runtime field data type and input fields.
5. Verify mappings to ensure input fields have appropriate types.
6. Write the Painless script and handle missing or `null` fields.
7. Put changing values in `params`; do not concatenate into `source`.
8. Test the script via Elasticsearch requests against representative data.
9. Integrate with `ScriptedField`, `RuntimeField`, `CriteriaQuery`, or repository methods.
10. If a runtime field is shared across many places, consider declaring it in the mapping via `@Mapping(runtimeFieldsPath = ...)`.
11. Request returning the computed field in the response if the application displays it.
12. Benchmark performance on a production-like dataset.
13. If the logic is used frequently, evaluate precomputing and storing the field in the index.

## Conclusion

Both scripted fields and runtime fields let you derive values from stored data without writing extra fields into `_source`. However, they serve two different purposes. Scripted fields (`script_fields`) only supplement values for hits already selected by the query. Runtime fields can participate in filters, queries, sorts, and aggregations.

In Painless, scripted fields return results via the script's return value, while runtime fields must use `emit(...)`. Runtime fields can be declared inline inside `runtime_mappings` of a single search request or defined persistently in the index mapping.

Spring Data Elasticsearch supports scripted fields via `ScriptedField`, `ScriptData`, and `@ScriptedField`. Runtime fields are represented by `RuntimeField`, which can be attached to `Query` or declared via `@Mapping(runtimeFieldsPath = ...)`. When choosing a mechanism, weigh where the computed value is needed, query frequency, and execution cost. For heavily used fields, precomputing and storing them in the index is usually the better direction.

## References

- [Spring Data Elasticsearch — Scripted and runtime fields](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/scripted-and-runtime-fields.html)
- [Spring Data Elasticsearch — Miscellaneous operations and runtime fields](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Spring Data Elasticsearch — ScriptedField annotation API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/ScriptedField.html)
- [Spring Data Elasticsearch — ScriptedField query API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/ScriptedField.html)
- [Spring Data Elasticsearch — ScriptData API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/ScriptData.html)
- [Spring Data Elasticsearch — RuntimeField API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/RuntimeField.html)
- [Elasticsearch — Use Painless scripts in runtime fields](https://www.elastic.co/docs/reference/scripting-languages/painless/use-painless-scripts-in-runtime-fields)
- [Elasticsearch — Map a runtime field](https://www.elastic.co/docs/manage-data/data-store/mapping/map-runtime-field)
- [Elasticsearch — Field context for script fields](https://www.elastic.co/docs/reference/scripting-languages/painless/painless-field-context)
- [Elasticsearch — Accessing document fields and special variables](https://www.elastic.co/docs/explore-analyze/scripting/modules-scripting-fields)
- [Elasticsearch — Scripts, caching, and search speed](https://www.elastic.co/docs/explore-analyze/scripting/scripts-search-speed)
- [Elasticsearch — Use parameters in your script](https://www.elastic.co/docs/explore-analyze/scripting/modules-scripting-use-parameters)
