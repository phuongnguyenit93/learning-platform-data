# Reading Mapping, Settings, and Comparing with the Java Model

In Elasticsearch, the mapping describes the structure and how Elasticsearch interprets each field of a document; settings describe the operational configuration of the index such as shard count, replicas, refresh interval, and analyzers. In Spring Data Elasticsearch, the Java entity along with annotations like @Document and @Field represent the model the application intends to use.

These three sources of information are related but not identical. Annotations in source code do not prove that the actual mapping on the cluster matches them. An index may have been created from a JSON mapping, an index template, a migration, or an older application version. Therefore, when investigating search issues or preparing data changes, you need to read the actual mapping and settings from Elasticsearch and compare them against the Java model.

This lesson explains how to read an index's configuration using the REST API and Spring Data Elasticsearch, how to understand the key parts of the response, how to compare against the entity, and how to handle discrepancies.

## 1. Distinguishing Mapping and Settings

Mapping and settings answer two different sets of questions.

| Component | Answers the Question | Example |
|---|---|---|
| Mapping | How does Elasticsearch interpret document fields? | name is text, price is double, createdAt is date |
| Settings | How is the index configured to store and operate? | 3 primary shards, 1 replica, 1-second refresh interval, custom analyzer |
| Java entity metadata | What fields does the application want to map Java properties into? | @Field(type = FieldType.Text), @Id, @Document(indexName = "products") |

The mapping determines search, filtering, sorting, and aggregation capabilities on each field. Settings affect how the index is created, distributed, and updated. Java metadata controls how Spring Data converts entities and can be used to generate the initial mapping.

Do not confuse mapping with document content. Mapping describes the schema; _source holds the data of each document. A field can be declared in the mapping even if it has not yet appeared in any document.

## 2. Reading Mapping with the Elasticsearch REST API

The most common API to inspect an index's mapping is:

~~~http
GET /products/_mapping
~~~

The response has a structure similar to:

~~~json
{
  "products": {
    "mappings": {
      "properties": {
        "name": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword"
            }
          }
        },
        "category": {
          "type": "keyword"
        },
        "price": {
          "type": "double"
        },
        "createdAt": {
          "type": "date"
        }
      }
    }
  }
}
~~~

The properties section lists the defined fields. Each field has a data type and may have additional attributes such as analyzer, format, fields, properties, or dynamic.

### 2.1. Reading the Mapping of a Specific Field

When an index has a large mapping, you can read only the field under investigation:

~~~http
GET /products/_mapping/field/price
~~~

Or check multiple fields:

~~~http
GET /products/_mapping/field/name,price,createdAt
~~~

This API is useful when you need to confirm whether a field is text, keyword, date, nested, or a particular numeric type. It also helps inspect multi-fields and field options without reading the entire mapping.

### 2.2. Reading the Mapping of Multiple Indexes

Elasticsearch allows specifying multiple indexes or wildcards:

~~~http
GET /products-*/_mapping
~~~

This is useful when the application uses versioned or time-based indexes, such as products-v1, products-v2, or events-2025.04. Check each index individually if queries run across multiple indexes, because the same field can have different mappings across indexes.

If the application queries through an alias, identify the physical indexes behind the alias and check each index's mapping. An alias does not automatically make mappings identical across indexes.

## 3. Understanding Key Components in a Mapping

### 3.1. properties and Data Types

properties describes the document's fields. Some common types:

| Elasticsearch Type | Common Purpose |
|---|---|
| text | Full-text search with content analysis |
| keyword | Exact matching, filtering, sorting, and aggregations |
| byte, short, integer, long | Integers by range |
| half_float, float, double | Floating-point numbers |
| scaled_float | Floating-point numbers stored with a scaling factor |
| boolean | True/false values |
| date, date_nanos | Dates, times, and timestamps |
| object | Nested JSON objects |
| nested | Arrays of objects preserving per-element field relationships |
| geo_point | Geographic coordinates |

Field types directly affect which queries are valid. For example, match is typically used for text content; term is suited for keyword values or fields requiring exact matching. A query may execute yet return unexpected results if the mapping does not fit the meaning of the data.

### 3.2. text and Multi-Fields

A text field is typically analyzed into tokens during indexing. If you need both full-text search and sorting or aggregation on the raw string, the mapping can declare multi-fields:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

In this case:

- name is the text field serving full-text search.
- name.keyword is the keyword sub-field serving exact matching, sorting, or aggregation.

If the entity only has a single name property, Spring Data can still map it to the root name field; the application queries name.keyword when the sub-field is needed. A sub-field does not necessarily correspond to a separate Java property.

### 3.3. Analyzer, Search Analyzer, and Normalizer

For a text field, the mapping can specify an analyzer at index time and a search analyzer at query time:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "standard",
    "search_analyzer": "standard"
  }
}
~~~

The analyzer determines how text is split into tokens, normalized, and processed. If the index-time and search-time analyzers are incompatible, search results may not match expectations.

For a keyword field, a normalizer can normalize values while keeping a single token, such as lowercasing/uppercasing. Inspect the analyzer, search analyzer, and normalizer when investigating search issues.

### 3.4. object, nested, and Nested Structures

The mapping of a nested object can contain inner properties:

~~~json
{
  "manufacturer": {
    "type": "object",
    "properties": {
      "name": {
        "type": "keyword"
      },
      "country": {
        "type": "keyword"
      }
    }
  }
}
~~~

For an array of objects that must preserve per-element boundaries during queries, the mapping can use nested:

~~~json
{
  "lines": {
    "type": "nested",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "quantity": {
        "type": "integer"
      }
    }
  }
}
~~~

The Java entity may use an object or List<OrderLine> in both cases. Looking only at the Java type cannot tell you whether the Elasticsearch field is object or nested; you must inspect the actual mapping or declare it explicitly using the corresponding metadata.

### 3.5. Dynamic Mapping

Elasticsearch can automatically infer mappings for new fields when receiving documents, depending on the dynamic setting. Common values:

- true: automatically add mappings for new fields.
- false: do not index new fields, though the fields can still remain in _source.
- strict: reject documents containing undeclared fields.

If dynamic mapping is enabled, a field absent from the Java entity may appear in the mapping after a document containing that field is written. Conversely, if the entity has a new property but no document has been written or the corresponding mapping has not been created yet, the field may not appear in the actual mapping.

Dynamic mapping is convenient for flexible data, but can create unintended field types. For example, a date/time string might be inferred as date under default formats, or a numeric value might be inferred as a numeric type unsuitable for the long-term data range.

## 4. Reading Index Settings

To read the settings applied to an index:

~~~http
GET /products/_settings
~~~

To see default values applied by Elasticsearch as well:

~~~http
GET /products/_settings?include_defaults=true
~~~

You can use flat format to make finding setting names easier:

~~~http
GET /products/_settings?flat_settings=true&include_defaults=true
~~~

The response may contain values like:

~~~json
{
  "products": {
    "settings": {
      "index": {
        "number_of_shards": "3",
        "number_of_replicas": "1",
        "refresh_interval": "1s",
        "analysis": {
          "analyzer": {
            "product_analyzer": {
              "type": "custom"
            }
          }
        }
      }
    }
  }
}
~~~

The values in the example are illustrative only. Actual settings depend on index configuration, templates, Elasticsearch version, and deployment environment.

### 4.1. Settings Worth Checking

| Setting | Meaning | When to Check |
|---|---|---|
| index.number_of_shards | Number of primary shards | When evaluating data partitioning and capacity |
| index.number_of_replicas | Number of replicas per primary shard | When checking availability and read capacity |
| index.refresh_interval | Periodic interval for new documents to become searchable | When investigating data visibility delay after writes |
| index.analysis | Analyzers, tokenizers, token filters, and normalizers | When text search returns incorrect results |
| index.sort.* | Physical sorting configuration at index time, if used | When investigating index sort configuration |
| index.lifecycle.* | Lifecycle-related configurations if the index is managed by a corresponding policy | When investigating rollover, retention, or lifecycle management |

Settings can be divided into those specified only at index creation and those that can be updated dynamically. For example, primary shard count is an important structural decision and cannot be changed directly like a normal setting after the index is created. Replica count and refresh interval are examples of settings that can be changed dynamically under conditions supported by Elasticsearch.

Do not try updating production settings just to observe the effect. Before making changes, check the documentation for the exact version, scope of impact, and operational requirements.

### 4.2. Why Use include_defaults=true?

If you only read regular settings, the result mainly shows configurations explicitly stored on the index. Some values may be absent because they are using cluster or version defaults.

include_defaults=true helps distinguish:

- Settings explicitly specified when creating or updating the index.
- Default values currently in effect.

This matters when comparing two indexes. Two indexes can have different explicit settings responses yet still use the same effective values; or neither may declare a setting while the default value has changed across versions.

## 5. Reading Mapping and Settings with Spring Data Elasticsearch

Spring Data Elasticsearch provides IndexOperations to read and manage index configurations. You can obtain this object from ElasticsearchOperations.

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexInspector {

    private final ElasticsearchOperations operations;

    public ProductIndexInspector(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void inspect() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        Map<String, Object> mapping = indexOperations.getMapping();
        Map<String, Object> settings = indexOperations.getSettings();

        System.out.println("Mapping: " + mapping);
        System.out.println("Settings: " + settings);
    }
}
~~~

operations.indexOps(Product.class) uses entity metadata to determine the target index, typically indexName in @Document. getMapping() reads the index mapping and getSettings() reads current settings according to the API of the Spring Data version in use.

Method signatures and return types of some index management methods may vary between release trains. Check the Javadoc or API for your exact project version before using this code verbatim.

### 5.1. Generating Expected Mapping from the Entity

IndexOperations also provides an API to generate a mapping based on entity metadata. For example:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

IndexOperations indexOperations = operations.indexOps(Product.class);
Document declaredMapping = indexOperations.createMapping();
~~~

createMapping() builds the mapping structure that Spring Data infers from the current entity and its annotations. You can place it alongside the getMapping() result to see differences between the expected mapping from the Java model and the actual mapping on the index.

The mapping generated from an entity is not guaranteed to be an exact replica of the JSON mapping on the cluster. The actual mapping may contain fields added by dynamic mapping, index templates, or migrations; it may also contain analyzers, sub-fields, and configurations managed outside the entity.

### 5.2. Reading Default Configurations

Some versions of Spring Data Elasticsearch have overloads allowing you to request settings including default values. If your project version does not provide the corresponding API or you need the clearest result, use the REST API:

~~~http
GET /products/_settings?include_defaults=true
~~~

The REST API is also useful when you need to access query parameters not exposed by the current Spring Data version's abstraction.

## 6. Declaring Settings and Mapping from the Java Model

An entity can describe part of the mapping with annotations:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

For complex configurations, Spring Data Elasticsearch supports declaring settings and mapping files via document-level annotations:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = false)
@Setting(settingPath = "/elasticsearch/products-settings.json")
@Mapping(mappingPath = "/elasticsearch/products-mapping.json")
public class Product {
    // fields
}
~~~

This example illustrates separating settings and mapping into dedicated resources for easier management. Paths, resource packaging, and bootstrap behavior must be verified against the Spring Data Elasticsearch version in use.

In production environments, indexes are usually created by migrations or deployment pipelines. In that case, createIndex = false prevents repository bootstrap from automatically creating the index from entity metadata. Settings and mapping are deployed first, and then the application uses the index.

## 7. Comparing the Actual Mapping with the Java Entity

When comparing, do not just compare property names. Compare field types as well as options that affect search behavior.

Example entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

The expected mapping might look like:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
~~~

Comparison:

| Java Model | Actual Mapping to Confirm | Issue If Mismatched |
|---|---|---|
| String name with FieldType.Text | name is text with an appropriate analyzer | Full-text search or language analysis fails |
| String category with FieldType.Keyword | category is keyword | Exact filtering, sorting, or aggregation does not behave as expected |
| BigDecimal price with FieldType.Double | price is a suitable numeric type | Range queries, sorting, or numeric precision may be wrong |
| Instant createdAt with FieldType.Date | createdAt is date with a format accepting the data | Writing or querying time values may error |
| @Id String id | Document identity resides in _id | Confusing _id with a field inside _source |

If using @Field(name = "product_name"), compare against the product_name field on the index, not the Java property name name.

### 7.1. Common Discrepancies

**Missing field in mapping:** the entity has a new property, but the index already existed and its mapping has not been updated. If dynamic mapping is off or no document has contained the field yet, the field may not appear in the mapping.

**Extra field in mapping:** the index has fields created by dynamic mapping, a template, or another application that the current entity does not declare. This is not necessarily an error, but you need to know which data source owns the field and whether the application uses it.

**Wrong field type:** Java declares String with FieldType.Text, while the actual mapping is keyword. The converter can still write strings normally, yet search behavior changes. Some mapping types cannot be changed directly once the index already contains data.

**Wrong analyzer or normalizer:** the field name and type are right, but the analyzer differs from expectations. This is a common reason searches return different results across environments.

**Object and nested mismatch:** the entity has List<OrderLine> while the actual mapping is object, even though queries use nested queries, or vice versa. The Java collection type does not automatically dictate nested mapping.

**Wrong date format:** Java uses Instant, while the mapping has a custom format that rejects the string sent by the converter, or old data uses a different format.

**Missing multi-field:** the entity only declares the root field while a query sorts by name.keyword, yet the actual mapping does not have this sub-field.

## 8. Comparing Settings with Application Configuration

Not every setting is represented by annotations on individual fields. Settings are index-level configurations and must be compared against deployment configurations.

Examples:

| Desired Configuration | Usually Managed At | How to Verify |
|---|---|---|
| Primary shard count | Index provisioning or template | _settings |
| Replica count | Index provisioning or operational config | _settings |
| Refresh interval | Index settings | _settings |
| Custom analyzer | Analysis settings and field mapping referencing the analyzer | _settings and _mapping |
| Dynamic mapping policy | Root mapping or object property | _mapping |
| Read/write aliases | Index lifecycle/provisioning | Alias API |

Example of a field mapping:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "product_analyzer"
  }
}
~~~

Looking only at the field mapping is not enough to confirm the analyzer works as expected. You need to read the analysis settings to verify which tokenizer and token filters define product_analyzer.

## 9. Index Templates Can Make Actual Configuration Differ from the Java Model

When an index is created, a matching index template can apply settings, mappings, and aliases to that index. Thus, a new index can receive configuration from a template even when the Java entity does not declare those details.

If the actual mapping or settings differ from @Field or configuration files in the application, check:

- Was the index created manually, by Spring Data, or by which pipeline?
- Does any index template match the index name?
- Which template has higher priority?
- Does any component template supply mappings or settings?
- Did the index already exist from a previous application version?
- Did another application or process update the mapping?

You can read composable index templates using the API:

~~~http
GET /_index_template
~~~

Or retrieve a specific template:

~~~http
GET /_index_template/products-template
~~~

Templates are primarily applied at index creation time. Modifying a template does not automatically rewrite the mapping or settings of existing indexes. To change an existing index, you must perform an update operation supported by Elasticsearch or create a new index following a migration workflow.

## 10. How to Handle Mapping Mismatches

When a discrepancy is found, first identify the source that created the actual mapping. Then classify the change:

### 10.1. Adding a New Field

If a new field needs to be added, Elasticsearch generally allows adding fields to an existing mapping via the update mapping API, provided it does not violate rules of the field or parent object.

~~~http
PUT /products/_mapping
Content-Type: application/json

{
  "properties": {
    "brand": {
      "type": "keyword"
    }
  }
}
~~~

Then update the Java entity to declare the corresponding field and deploy the application in the appropriate order.

### 10.2. Changing the Type of an Existing Field

You cannot arbitrarily change the type of an already-indexed field, such as from text to keyword or from long to date. Such changes typically require:

1. Creating a new index with the correct mapping.
2. Reindexing data from the old index to the new index.
3. Checking document counts and critical queries.
4. Switching the alias or application configuration to the new index.
5. Only deleting the old index after verification and in accordance with retention policy.

Do not edit the entity and expect the old index's mapping to change automatically.

### 10.3. Changing Analyzers or Analysis Settings

Analyzers typically depend on index-level analysis settings. Some analyzer changes cannot be applied like regular dynamic setting updates; they may require closing/opening the index under supported rules or creating a new index and reindexing. For production, the new-index workflow is usually easier to control and test.

### 10.4. Updating Annotations Only When Indexes Are Managed Separately

If the deployment pipeline is the authoritative source for mappings, Java entity changes must be accompanied by corresponding changes to the mapping file or migration. If you only update annotations, the running index may keep the old configuration.

Conversely, if using repository bootstrap to create indexes automatically, ensure entity metadata, settings, and mapping resources are updated in sync before creating the new index.

## 11. Project Workflow for Checking Mapping and Settings

An investigation workflow can follow this order:

1. Identify the physical index that the repository or alias is accessing.
2. Read the mapping with GET /index/_mapping.
3. Read settings with GET /index/_settings?include_defaults=true.
4. For specific fields, read GET /index/_mapping/field/fieldName.
5. Inspect the Java entity, @Document, @Id, @Field, @Setting, and @Mapping.
6. Use IndexOperations.createMapping() to inspect the mapping Spring Data derives from the entity, if supported by the version's API.
7. Compare field names, data types, analyzers, formats, nested structures, and important options.
8. Check index templates or migrations if the actual configuration originates outside the entity.
9. Classify differences into fields that can be added, settings that can be updated, or changes requiring a reindex.
10. Plan deployment and re-verify mapping/settings after the change.

When recording findings, save the index name, check timestamp, and Elasticsearch version. This helps compare local, staging, and production without confusing configurations across environments or different index versions.

## 12. Example: Investigating a Product Search Bug

Suppose the application has an entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    // other fields
}
~~~

The application needs to sort by name and aggregate on exact names, but queries using name.keyword report that the field does not exist or return no results.

Investigation workflow:

**Step 1: Read the mapping**

~~~http
GET /products/_mapping/field/name
~~~

If the response only contains:

~~~json
{
  "name": {
    "type": "text"
  }
}
~~~

then the current mapping does not have the name.keyword sub-field.

**Step 2: Compare with query requirements**

The entity declares name as text, which suits full-text search. However, exact sorting/aggregation requires a keyword field or a keyword sub-field.

**Step 3: Identify the mapping source**

Check whether the index was created from annotations, a mapping file, a template, or a migration. If mappings are managed by a pipeline, edit the authoritative mapping file. If the index already exists and needs the multi-field added, evaluate the appropriate mapping update; old data may need to be reindexed so the sub-field is fully indexed.

**Step 4: Verify**

After updating, read back the mapping and test the sort/aggregation queries. Only when the actual mapping has name.keyword and data has been indexed into the sub-field can queries use that field properly.

This example shows that the Java entity and index mapping must be checked against actual queries. The Java String type alone does not determine whether a multi-field exists.

## 13. Notes When Comparing Across Environments

Two environments running the same source code can still produce different search results if their indexes differ. Some reasons:

- Indexes were created at different times, before and after a mapping change.
- One environment uses a new template while the other uses an old template.
- Default settings changed across Elasticsearch versions.
- The first document written into one environment caused dynamic mapping to infer a different type.
- One environment has different analyzers or plugins.
- Aliases point to physical indexes of different versions.

When comparing, check the same physical index or explicitly identify the indexes behind an alias. Compare both mapping and settings, and record the Elasticsearch version and applied templates. Do not simply compare entity files in Git and conclude that two clusters are identical.

## 14. Conclusion

Mapping tells you how Elasticsearch interprets fields and document structures; settings tell you how the index is configured and operated. Spring Data Elasticsearch provides IndexOperations to read mapping/settings and generate the expected mapping from entity metadata. The REST API remains the direct way to inspect the effective configuration on the cluster, including default values.

Compare the actual mapping with @Document, @Id, @Field, and project configuration files. Check field types, analyzers, formats, multi-fields, nested structures, dynamic mapping, and related settings. When differences are found, identify the source of index creation first and then choose the appropriate update path; changing field types or major structures usually requires a new index and reindexing.

Reading mapping and settings should be part of deployment and incident investigation workflows. The Java entity describes how the application works with documents, whereas the mapping/settings on the cluster reveal which configuration the running index actually uses.
