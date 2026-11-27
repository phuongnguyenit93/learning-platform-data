# Explicit mapping, dynamic mapping, and dynamic templates

In Elasticsearch, a mapping describes how each field in a document is stored, analyzed, and indexed. The mapping determines whether a string is split into tokens for full-text search or kept intact for exact filtering; what format a date value is parsed in; whether a sub-object is handled as object or nested; and how newly appearing fields in a document are handled.

Spring Data Elasticsearch provides annotations and APIs to generate mappings from Java classes, while also allowing the use of Elasticsearch JSON mapping files. Whether declared in Java or JSON, the final rules are still enforced by Elasticsearch. Therefore, you need to understand both Elasticsearch mappings and how Spring Data translates entity metadata into a mapping.

After this lesson, you will be able to:

- Explain the role of mapping and why field types should be defined before writing data.
- Declare explicit mappings using JSON and Spring Data Elasticsearch annotations.
- Describe how Elasticsearch infers mappings when encountering new fields.
- Choose between enabled, disabled, or strict dynamic mapping.
- Write dynamic templates to apply controlled mapping rules for new fields.
- Combine these mechanisms to support flexible data while maintaining a stable structure.

## 1. What is a mapping?

Elasticsearch stores data as JSON documents inside an index. A mapping defines the structure and how the fields of a document are processed. Each field has a data type, optionally accompanied by settings such as analyzer, normalizer, date format, sub-fields, or object handling.

For example, a product document might look like this:

~~~json
{
  "sku": "KB-1042",
  "name": "Mechanical Keyboard",
  "price": 129.90,
  "createdAt": "2026-10-20T09:30:00Z",
  "attributes": {
    "layout": "US",
    "switchCount": 87
  }
}
~~~

The mapping can specify:

- sku is keyword for exact matching, sorting, and aggregations.
- name is text to be analyzed into tokens for full-text search; it can also have a keyword sub-field for exact filtering.
- price is a numeric type for range filtering and aggregation calculations.
- createdAt is date for sorting and time-based queries.
- attributes is an object containing sub-fields.

Elasticsearch can automatically create mappings when encountering new fields, but the resulting mapping affects how that field's data is indexed going forward. Once a field has a data type, you cannot change it directly to an incompatible type simply by updating the mapping.

### 1.1. Text and keyword types

The two most common types for strings are text and keyword:

| Type | How it is processed | Use cases |
| --- | --- | --- |
| text | Analyzed into tokens by an analyzer | Content search, descriptions, titles |
| keyword | Kept intact as a single unit | Identifiers, statuses, labels, exact filtering, sorting, and aggregations |

For example, with the value Mechanical Keyboard, a text field can be analyzed into the tokens mechanical and keyboard. A keyword field keeps Mechanical Keyboard intact. match queries are typically used for text; term queries are typically used for keyword.

A single field can have multiple indexing representations through multi-fields. For example, name has type text and also name.keyword of type keyword. That way, the same data can serve both full-text search and exact filtering or sorting.

## 2. Explicit mapping

Explicit mapping is a mapping declared before Elasticsearch has to infer field types on its own. This is the right choice for known business fields, especially fields used in queries, sorting, aggregations, or integrations with other systems.

### 2.1. Declaring a mapping with Elasticsearch JSON

You can create an index and declare its mapping in a single request:

~~~http
PUT /catalog-v1
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "createdAt": {
        "type": "date"
      },
      "attributes": {
        "type": "object",
        "dynamic": true
      }
    }
  }
}
~~~

In this example:

- sku is declared as keyword.
- name is analyzed with the standard analyzer and has a keyword sub-field.
- price uses scaled_float with a scaling_factor of 100, suitable when decimal numbers need precision to two decimal places.
- createdAt is declared as date.
- Document-level mapping uses strict dynamic mode. Specifically, the attributes object allows dynamic mapping to accept extensible properties.

Declaring types explicitly avoids having the same field inferred differently due to incoming data. For example, if the price field first receives the string "129.90", Elasticsearch might create a string mapping; when the application later sends a number to that field, the data may fail to index as intended or be rejected.

### 2.2. Declaring a mapping with Spring Data Elasticsearch annotations

With Spring Data Elasticsearch, you can declare metadata on the entity. Spring Data uses this metadata when creating the mapping for the index:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "catalog-v1", createIndex = true)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Scaled_Float, scalingFactor = 100)
    private BigDecimal price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Object)
    private Map<String, Object> attributes;

    // Constructors, getters, and setters
}
~~~

Key annotations:

- @Document specifies the target index for the entity. createIndex indicates whether Spring Data automatically creates the index when initializing the mapping.
- @Id marks the property used as the Elasticsearch document ID.
- @Field defines the type and mapping properties of a field.
- @MultiField combines a main field with one or more sub-fields. In the example, name is text and name.keyword is keyword.
- @InnerField declares a sub-field within multi-fields.

The example above illustrates commonly used metadata. For monetary data requiring specific precision, choose an appropriate type and scaling factor in the JSON mapping, and keep value representation consistent in Java. Do not assume that all decimal types share the exact same rounding behavior.

### 2.3. Using a JSON mapping file in Spring Data

When a mapping has many settings, dynamic templates, or complex nested structures, a JSON file is often easier to read and closer to native Elasticsearch configuration. Spring Data Elasticsearch supports specifying a mapping file using @Mapping:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;

@Document(indexName = "catalog-v1", createIndex = true)
@Mapping(mappingPath = "/mappings/catalog-mapping.json")
public class Product {
    // Entity properties
}
~~~

The catalog-mapping.json file contains mapping definitions in Elasticsearch format, with root-level properties such as dynamic, properties, and dynamic_templates. For example, a condensed structure of the file might be:

~~~json
{
  "dynamic": "strict",
  "properties": {
    "sku": {
      "type": "keyword"
    }
  },
  "dynamic_templates": [
    {
      "attribute_strings": {
        "path_match": "attributes.*",
        "match_mapping_type": "string",
        "mapping": {
          "type": "keyword"
        }
      }
    }
  ]
}
~~~

The path is placed in application resources so Spring Data can read it when creating the mapping.

You can manage indices via ElasticsearchOperations and IndexOperations. In the example below, operations is an injected ElasticsearchOperations instance:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

The snippet illustrates creating an index along with the mapping derived from the entity's metadata. In production systems, clearly designate which component is responsible for creating the index: the Spring application, a migration process, or an Elasticsearch index template configuration. Avoid having multiple components create the same index with different mappings.

If you use a custom JSON mapping, treat that file as part of the schema and version-control changes alongside source code. Also verify the behavior of the Spring Data Elasticsearch version in use, especially when combining custom mappings with annotation-generated mappings.

## 3. Dynamic mapping

Dynamic mapping is the mechanism by which Elasticsearch automatically adds a mapping for an undeclared field when receiving a document containing that field. This helps you get started quickly and fits data with evolving structures, but type inference depends on the first value Elasticsearch sees.

Suppose the index does not yet have a stockCount field. The application sends:

~~~json
{
  "sku": "KB-1042",
  "stockCount": 87
}
~~~

If dynamic mapping is enabled, Elasticsearch infers stockCount as an integer field and adds it to the mapping. Subsequent documents are processed according to the created type.

### 3.1. Dynamic modes

The dynamic setting can be configured at the mapping level or on a specific object:

| Value | Behavior when encountering an undeclared field |
| --- | --- |
| true | Automatically adds the field to the mapping and indexes the value |
| false | Does not add the field to the mapping; the value can still remain in _source but is not indexed for search |
| strict | Rejects documents containing undeclared fields with a mapping exception |

If unspecified, dynamic defaults to true. For example:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "attributes": {
        "type": "object",
        "dynamic": true
      }
    }
  }
}
~~~

With this configuration, unknown fields at the document level are rejected. New sub-fields inside attributes are still allowed to have mappings created automatically. Setting modes at individual levels keeps the core schema stable while allowing a specific data area to remain extensible.

Note: dynamic false does not mean Elasticsearch removes the field from the source document. The field can still appear in _source, but it is not added to the mapping and cannot be queried as a normally indexed field.

### 3.2. How does Elasticsearch infer types?

With dynamic mapping, Elasticsearch inspects the JSON type and applies inference rules. Common cases include:

| First JSON value | Mapping type usually created |
| --- | --- |
| String matching recognized date format | date |
| Regular string | text with keyword multi-field |
| Integer | long |
| Floating-point number | double |
| true or false | boolean |
| JSON object | object |
| Array | Inferred from the first non-null element |
| null or empty array | Insufficient information to create a field mapping |

Elasticsearch enables date detection by default, so a date-like string can be inferred as date. Numeric detection is disabled by default, so a string containing digits does not automatically become a numeric type just because its content looks like a number.

For example, the first document sending the value:

~~~json
{
  "releaseDate": "2026-10-20"
}
~~~

May cause releaseDate to be created as type date. If another document sends a non-date string to the same field, the data can cause a date parsing error. Similarly, if a field is created as long, a text value like "unknown" cannot be indexed as a long.

Arrays do not have a separate mapping type. Elasticsearch infers the type from the first non-null element and uses that type for the field. Therefore, mixed-type arrays like [12, "unknown"] can cause errors when an incompatible element is indexed.

### 3.3. Risks of relying entirely on dynamic mapping

Dynamic mapping is convenient, but it carries several risks that must be managed:

1. **Misinterpreting field semantics.** A numeric-only product code might be interpreted as a number, whereas the application needs to preserve leading zeros and match exact values. Code fields should usually be declared as keyword.
2. **Data type conflicts.** The first document might create a field as date or long, while later data arrives in a different format. Elasticsearch does not automatically change an existing type.
3. **Mapping explosion.** If every document introduces many distinct field names, the mapping will bloat. This increases memory usage and cluster management overhead; field counts are also subject to configured limits.
4. **Differences across indices.** If multiple indices are created from data arriving in different orders, the same field name may end up with different mappings. Queries over an alias pointing to multiple indices may then fail or behave inconsistently.
5. **Difficulty changing schemas.** Once created, a mapping cannot arbitrarily change types. Incompatible changes usually require creating a new index and reindexing data.

Consequently, dynamic mapping is best suited for genuinely flexible data that follows clear conventions. Core business fields should be declared explicitly.

## 4. Dynamic templates

Dynamic templates allow defining rules so Elasticsearch creates mappings for new fields based on field name, path, or the data type Elasticsearch infers. They can be viewed as customizable rules for dynamic mapping.

Dynamic templates are only evaluated when Elasticsearch encounters a field that does not yet have a mapping. If the field is explicitly declared, that explicit mapping is used. Templates also do not retroactively convert mappings of existing fields.

### 4.1. Structure of a dynamic template

A dynamic template has a name, matching conditions, and the mapping definition to apply:

~~~json
{
  "mappings": {
    "dynamic_templates": [
      {
        "codes_as_keyword": {
          "match": "*_code",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      }
    ]
  }
}
~~~

In this example, a new field whose name ends with _code and is detected by Elasticsearch as string will be created as keyword. For instance, supplier_code and country_code match this rule.

Commonly used conditions:

| Condition | Meaning |
| --- | --- |
| match | Matches field names using a wildcard pattern |
| unmatch | Excludes field names matching a pattern |
| path_match | Matches the full path of the field, useful for nested objects |
| path_unmatch | Excludes a full path |
| match_mapping_type | Matches the type inferred by Elasticsearch, such as string, long, double, boolean, or object |
| unmatch_mapping_type | Excludes an inferred type |
| match_pattern | Selects how names are matched, typically simple or regex |

All conditions within the same template must be satisfied for the template to match. If multiple templates could match, Elasticsearch applies the first matching template in declaration order. Therefore, place specific rules before general rules.

### 4.2. Example: strings default to text, but codes are keyword

An application has many new string fields. Most need full-text search, while fields suffixed with _code need exact matching:

~~~json
{
  "mappings": {
    "dynamic_templates": [
      {
        "codes_as_keyword": {
          "match": "*_code",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      {
        "other_strings_as_text": {
          "match_mapping_type": "string",
          "mapping": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "ignore_above": 256
              }
            }
          }
        }
      }
    ]
  }
}
~~~

With the order above:

- supplier_code is keyword.
- description is text and also has description.keyword.
- region_code is keyword if Elasticsearch detects its value as string.

The second template is a catch-all rule for all strings. If placed first, code fields would also match the general template and never reach the codes_as_keyword template.

### 4.3. Example: applying rules to nested objects

Suppose a document has an attributes area containing properties supplied by multiple data sources:

~~~json
{
  "sku": "KB-1042",
  "attributes": {
    "layout": "US",
    "switchCount": 87,
    "vendor_code": "VN-ACME"
  }
}
~~~

You can use path_match to apply templates only within the attributes area:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "attributes": {
        "type": "object",
        "dynamic": true
      }
    },
    "dynamic_templates": [
      {
        "attribute_codes_as_keyword": {
          "path_match": "attributes.*",
          "match": "*_code",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      {
        "attribute_strings_as_keyword": {
          "path_match": "attributes.*",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      }
    ]
  }
}
~~~

The top-level mapping uses strict to protect the schema. The attributes object enables dynamic to accept new sub-fields. Two templates restrict rules to the attributes.* path; the first handles code fields, and the second handles the remaining strings in this area.

If the data has multiple object levels, inspect the actual field path and adjust path_match accordingly. Do not assume a single path pattern will cover every nested structure without testing with representative documents.

### 4.4. Combining match_mapping_type with field names

Field names and data types can be used together to prevent applying a rule incorrectly. For example, any field ending with _count and detected as an integer can be mapped with a numeric rule:

~~~json
{
  "dynamic_templates": [
    {
      "counts_as_long": {
        "match": "*_count",
        "match_mapping_type": "long",
        "mapping": {
          "type": "long"
        }
      }
    }
  ]
}
~~~

Matching by name alone could cause a string field to be mapped as a number unexpectedly. Combining the name with match_mapping_type makes the rule clearer. If you want to restrict names using regular expressions, you can use match_pattern with regex; test the pattern on real field names before deploying to production.

## 5. Combining explicit mapping, dynamic mapping, and dynamic templates

The three mechanisms address different needs:

| Mechanism | Role | When to use |
| --- | --- | --- |
| Explicit mapping | Precisely defines types and processing for known fields | Core business fields, fields used in queries, sorting, or aggregations |
| Dynamic mapping | Automatically creates mappings when encountering new fields | Data has a changing portion and default inference rules are acceptable |
| Dynamic templates | Controls automatic mapping via conditions | Many new fields exist, but they follow conventions in name, path, or type |

A common strategy:

1. Explicitly declare identifiers, statuses, timestamps, metrics, and search fields.
2. Set dynamic at the document level to strict to catch field-name typos and unexpected schema changes.
3. Create one or a few extensible objects, such as attributes, that allow dynamic mapping.
4. Define dynamic templates to govern how new fields inside extensible objects are mapped.
5. Monitor actual field counts and mappings after deployment.

This strategy enables the application to ingest flexible attributes while still catching stray fields in the primary data early.

## 6. Operational and mapping change considerations

### 6.1. Existing field types cannot be arbitrarily changed

Once Elasticsearch has created a mapping for a field, you cannot directly update that field's type from text to date, from long to keyword, or to another incompatible type. Changing a type usually requires:

1. Creating a new index with the correct mapping.
2. Reindexing documents from the old index to the new index, optionally with a script or transformation step if needed.
3. Verifying document counts and critical queries on the new index.
4. Switching read/write aliases to the new index according to the system's deployment process.

Certain mapping properties can be added or updated within Elasticsearch's limits, but you should not treat mappings as a schema that can be freely modified after data has been written.

### 6.2. Mapping and data in _source

_source stores the original JSON document according to index settings. The mapping controls how fields are indexed and queried. These two concepts are related but not identical:

- A field ignored due to dynamic false can still exist in _source.
- A text field can have an additional keyword multi-field to support exact queries.
- A field appearing in _source does not automatically mean it has a mapping or can be used in aggregations.

When investigating why a field cannot be queried, inspect both the document in _source and the index mapping.

### 6.3. Dynamic templates are not index templates

The two concepts have similar names, but they operate at different levels:

- Dynamic templates are rules for creating mappings for new fields inside an index.
- Index templates are configurations applied when creating an index matching a name pattern or condition; they can provide settings, mappings, and aliases for new indices.

An index template can contain mappings and dynamic templates. However, an index template does not replace the role of dynamic templates when new documents introduce additional fields into an existing index.

### 6.4. Inspecting the mapping after index creation

You can read the actual mapping using the API:

~~~http
GET /catalog-v1/_mapping
~~~

Inspect the actual mapping rather than only looking at annotations or JSON files. This confirms that Elasticsearch has applied the expected types, analyzers, multi-fields, dynamic mode, and dynamic templates.

When testing, send representative documents covering:

- Core fields with all valid data types.
- Extensible fields whose names match each dynamic template.
- Fields that do not match any template.
- Fields with data types different from the expected type.
- Unknown fields at the strict level to confirm Elasticsearch rejects the document.

These test cases help catch templates shadowed by general rules, incorrect path_match patterns, or data type conflicts early.

## 7. Common mistakes

**Using text for identifiers.** Text is analyzed into tokens, making it unsuitable for codes that need exact matching. Use keyword, or multi-fields if the field needs both full-text search and exact filtering.

**Assuming dynamic false discards data.** The field is not added to the mapping, but it can still be retained in _source. If unknown fields must be rejected, use strict.

**Placing general templates before specific templates.** The first matching template is applied. Place rules with narrower conditions before broad catch-all rules.

**Modifying a template and expecting old fields to be remapped.** Dynamic templates apply only when creating mappings for new fields. Existing mapped fields keep their current types.

**Assuming Java annotations automatically control every field in JSON.** Annotations describe mappings for entities, yet actual documents can contain extensible data inside a Map or object. Inspect the JSON sent to Elasticsearch and the resulting mapping.

**Letting multiple components independently create the same index.** If the application, migrations, and index templates are uncoordinated, the index may be created with different mappings depending on timing. Establish a clear schema management process.

## 8. Recommended mapping design workflow

When designing a new index for a Spring Data Elasticsearch application, you can follow this sequence:

1. List business fields and determine how each field is used: full-text search, exact filtering, sorting, aggregations, or storage.
2. Choose the appropriate Elasticsearch type for each field. In particular, distinguish text from keyword, object from nested, and numeric types from code strings.
3. Explicitly declare stable fields using @Field or JSON mapping.
4. Identify which areas are allowed to accept new properties. Enable dynamic only on the exact objects that need it.
5. Write dynamic templates following naming, path, and data type conventions; place specific rules before general rules.
6. Create the index in a development environment and read back the mapping using the _mapping API.
7. Send both valid and invalid documents to verify the behavior of dynamic true, false, strict, and each template.
8. Manage mapping changes via index versioning and a reindex workflow whenever incompatible type changes are needed.

A good mapping reflects how the application uses data, not just the shape of incoming JSON. Design around queries and data lifecycle, and use dynamic mapping alongside dynamic templates for controlled extensibility.
