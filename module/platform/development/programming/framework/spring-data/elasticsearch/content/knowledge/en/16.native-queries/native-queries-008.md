# Scripts, Runtime Fields, and Version-Specific Options

NativeQuery lets Spring Data Elasticsearch use Elasticsearch Query DSL at a finer level of detail than CriteriaQuery and derived queries. When runtime computation is needed during search, you can use scripts, script fields, or runtime fields.

These three mechanisms are related, yet they solve different problems:

- **Script query** evaluates an expression to decide whether a document matches.
- **Script field** computes an extra value for each returned hit, typically for display or result processing.
- **Runtime field** defines a field computed at query time. Depending on supported types and contexts, this field can participate in queries, sorting, aggregations, and be returned like a field.

Scripts are flexible, but they incur CPU cost and can make queries harder to optimize. Runtime fields add logic without reindexing documents, though values are still computed at query time. If a calculation is used frequently and can be determined at write time, storing the precomputed field is usually more efficient.

## 1. What Is a Script in Elasticsearch?

Elasticsearch supports scripting to run logic over data in various contexts. The default scripting language commonly used is Painless, designed to run in a sandboxed environment.

For example, suppose a product document has these fields:

~~~json
{
  "sku": "SKU-1001",
  "price": 200000,
  "cost": 150000,
  "active": true
}
~~~

A script can calculate profit:

~~~text
price - cost
~~~

Or determine whether a document's profit exceeds a threshold:

~~~text
doc['price'].value - doc['cost'].value > params.minimum
~~~

Scripts can be used in several contexts:

| Context | Purpose | Script Result |
|---|---|---|
| Script query | Filter documents via logic | true/false |
| Script field | Add computed value to each hit | Returned value |
| Runtime field | Define a virtual field at query time | Emitted value |
| Script score | Compute custom relevance score | Numeric score |
| Update script | Modify document during updates | Updated source |
| Aggregation script | Compute values in aggregations where supported by API | Value for aggregation |

Do not extrapolate how to write scripts for updates or runtime fields from a script query example. Each context has its own variables, functions, and return semantics.

## 2. Painless and Common Variables

Painless is a scripting language designed by Elasticsearch to enforce access controls and limit operations. Scripts are compiled and executed within a specific context.

In many query contexts, scripts can access:

- `doc`: accesses doc values of indexed fields.
- `params`: parameters passed in the request.
- `_source`: source data in certain supported contexts, though usually more expensive than doc values.
- Functions and data types permitted by the context.

Example reading a numeric value:

~~~text
doc['price'].value
~~~

Checking whether a field has a value:

~~~text
doc['price'].size() != 0
~~~

Accessing a parameter:

~~~text
doc['price'].value > params.minimum
~~~

Always check whether a field exists before accessing `.value` if documents can omit the field. Otherwise, the script may throw an error when encountering a document lacking that value.

### 2.1. doc values and _source

doc values are data structures optimized by Elasticsearch for operations such as sorting, aggregations, and script field access. Field types that support doc values can normally be accessed via `doc['field']`.

Example:

~~~text
doc['price'].value
~~~

Accessing `_source` can be useful when you need the original JSON structure or fields without doc values, though it typically incurs higher decoding and access overhead. For scripts running across many documents, prefer doc values whenever the logic allows.

Not every field type supports doc values in the same way. Text fields typically do not have doc values by default; if you need string access for sorting or aggregations, a `keyword` multi-field or suitable configuration is normally used. Inspect the actual mapping before writing a script.

### 2.2. Handling Missing Fields

Do not assume every document has all fields populated:

~~~text
if (doc['cost'].size() == 0 || doc['price'].size() == 0) {
    return false;
}
return doc['price'].value > doc['cost'].value;
~~~

Return syntax and expressions must fit the script context. For runtime fields, values are output via `emit(...)` rather than returning a value like a regular function.

Define a clear policy for missing fields: exclude the document from results, substitute a default value, or flag invalid data. Avoid letting a script silently produce wrong values for documents with missing fields.

## 3. Parameterizing Scripts with params

Do not concatenate user input directly into script source strings. Keep the script source stable and pass dynamic values through `params`.

Example source:

~~~text
doc['price'].value >= params.minimum
~~~

Parameters:

~~~json
{
  "minimum": 100000
}
~~~

Benefits:

- Avoids generating a new source string for every input value.
- Allows Elasticsearch to reuse compiled scripts more effectively.
- Separates script logic from business data.
- Reduces the risk of injecting untrusted strings into script source code.

Never inject arbitrary input into script source or field names. Validate input values and allow field selection only from an application-controlled allowlist.

## 4. Script Query: Filtering Documents with Custom Logic

A script query uses a boolean expression to determine whether a document matches.

REST DSL:

~~~http
POST /products/_search
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value - doc['cost'].value > params.minimum",
        "params": {
          "minimum": 30000
        }
      }
    }
  }
}
~~~

The query returns documents whose profit exceeds 30,000 in the units stored in `price` and `cost`.

Script queries are helpful when conditions must combine multiple fields using calculations that standard queries cannot express directly. However, they are usually more expensive than term or range queries because the script must run for candidate documents on each shard.

Whenever a condition can be expressed as a standard query, do so. For example, filtering `price >= 100000` should use a range query on `price` rather than a script query just to compare a single field.

### 4.1. Combining a Script Query with Regular Filters

You can use a `bool` query to pre-filter with cheap conditions first before running the script:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 100000
            }
          }
        },
        {
          "script": {
            "script": {
              "lang": "painless",
              "source": "doc['price'].value - doc['cost'].value > params.minimum",
              "params": {
                "minimum": 30000
              }
            }
          }
        }
      ]
    }
  }
}
~~~

The `active` and `price` filters narrow the document set before evaluating the script condition. This is also usually a clearer query structure than putting all logic inside one script.

Script queries can still consume significant CPU over the remaining candidate set. Measure with production-scale data.

## 5. Script Field: Computing Additional Values per Result

A script field does not decide whether a document matches. It computes an additional value for each returned hit.

Example adding profit to search results:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "active": true
    }
  },
  "script_fields": {
    "profit": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value - doc['cost'].value"
      }
    }
  }
}
~~~

Documents are selected by the `active=true` query. For each hit, Elasticsearch computes `profit` and returns it under the hit's `fields` section.

Abbreviated response:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "P-1001",
        "_source": {
          "price": 200000,
          "cost": 150000,
          "active": true
        },
        "fields": {
          "profit": [
            50000
          ]
        }
      }
    ]
  }
}
~~~

A script field does not write `profit` into `_source` and does not update the index mapping. Values are computed solely for the current response.

Use script fields when:

- The UI needs to display a value computed from other fields.
- The calculation is only needed for the small number of returned hits.
- You do not need the computed result as a primary filter condition.
- You do not need to persist the computed value long-term.

If you need to filter on computed values, a script query or runtime field is more suitable. If the calculation is needed frequently, consider storing the precomputed field at write time.

## 6. What Is a Runtime Field?

A runtime field is a field whose values are computed when a query runs instead of being pre-stored in the document source/index like a standard indexed field.

Runtime fields can be declared in the index mapping or inside a search request via `runtime_mappings`.

Example runtime field `profit` of type `long`:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "if (doc['price'].size() != 0 && doc['cost'].size() != 0) { emit(doc['price'].value - doc['cost'].value); }"
      }
    }
  },
  "query": {
    "range": {
      "profit": {
        "gte": 30000
      }
    }
  },
  "fields": [
    "profit"
  ]
}
~~~

Here:

- `runtime_mappings` defines the virtual field `profit` for the request.
- `type` specifies the field's data type.
- `script` computes the value and calls `emit(...)` to emit it.
- The `range` query can reference `profit`.
- `fields` asks Elasticsearch to return the runtime field in the response.

A runtime field does not automatically write data into documents. When the same request needs to use `profit` in a query and return it in results, runtime mappings allow reusing that field definition.

### 6.1. emit vs. return

In a runtime field script, use `emit(value)` to output a value:

~~~text
emit(doc['price'].value - doc['cost'].value);
~~~

If a runtime field has multiple values, the script can call `emit` multiple times as supported by the field type.

Do not use `return` as in a script query. A script query expects a boolean result in query context; a runtime field must emit values matching its declared type.

### 6.2. Runtime Field in Mapping vs. in Request

Runtime fields can be declared in two scopes:

| Scope | Characteristics | When Suitable |
|---|---|---|
| Index mapping | Runtime field is defined in mapping and available across requests | Shared logic used across many queries |
| Request `runtime_mappings` | Field is declared for a single search request | Experimentation, temporary logic, or per-query variations |

Runtime fields in mappings can be declared via the mapping API. Request `runtime_mappings` let you introduce computed fields without altering the index mapping.

Regardless of scope, a runtime field is still computed whenever used. Declaring it in the mapping does not turn it into a physically indexed field like a standard field.

## 7. Using Runtime Fields in Queries, Sorting, and Aggregations

Runtime fields can be referenced across multiple parts of the Search API when supported by the data type and API.

Example filtering by profit:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "emit(doc['price'].value - doc['cost'].value)"
      }
    }
  },
  "query": {
    "range": {
      "profit": {
        "gte": 50000
      }
    }
  }
}
~~~

Runtime fields can be used in aggregations:

~~~http
POST /products/_search
{
  "size": 0,
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "emit(doc['price'].value - doc['cost'].value)"
      }
    }
  },
  "aggs": {
    "average_profit": {
      "avg": {
        "field": "profit"
      }
    }
  }
}
~~~

And in sorting:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "emit(doc['price'].value - doc['cost'].value)"
      }
    }
  },
  "sort": [
    {
      "profit": {
        "order": "desc"
      }
    }
  ]
}
~~~

These operations can carry substantial cost because the script must compute values for evaluated documents. For fields frequently used for filtering, sorting, or aggregating over large datasets, physically indexed fields are usually more efficient.

## 8. How Do Script Queries, Script Fields, and Runtime Fields Differ?

| Mechanism | Role | Filters Documents? | Returns Computed Value? | Usable in Query/Sort/Aggregation? |
|---|---|---:|---:|---|
| Script query | Custom boolean condition | Yes | Not the goal | Used as a query |
| Script field | Computes value for returned hits | No | Yes, in `fields` | Not usable like a general mapped field |
| Runtime field | Virtual field computed at query time | Can be queried | Can be returned via `fields` | Yes, depending on type and API support |
| Physical field | Stored and indexed value | Yes | Yes, from source/doc values | Yes, usually more efficient |

Selection examples:

- Want only products with profit > 50,000: script query or runtime field + range query.
- Want to display profit for 20 matched products: script field or runtime field.
- Want to sort and aggregate by profit across many requests: a runtime field works, though storing `profit` as a physical field should be considered if performance matters.

## 9. NativeQuery in Spring Data Elasticsearch

NativeQuery enables using Elasticsearch Java API Client `Query` types. In Spring Data Elasticsearch 5.x, NativeQuery is in the package:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
~~~

A simple query can be built using the Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query query = Query.of(q -> q
    .term(t -> t
        .field("active")
        .value(v -> v.booleanValue(true))
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(query)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

For a script query, create a `Script` and attach it to a `Query`:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import co.elastic.clients.json.JsonData;

Script script = Script.of(s -> s
    .inline(i -> i
        .lang("painless")
        .source(
            "doc['price'].value - doc['cost'].value > params.minimum"
        )
        .params("minimum", JsonData.of(30000))
    )
);

Query scriptQuery = Query.of(q -> q
    .script(s -> s.script(script))
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(scriptQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

This snippet illustrates the Elasticsearch Java API Client used with Spring Data Elasticsearch 5.x. Package names, builder methods, and overloads must match your project's dependency versions.

If the IDE does not recognize `.inline(...)`, `.script(...)`, or `withQuery(...)`, verify the Elasticsearch Java API Client and Spring Data Elasticsearch versions in use. Do not mix the Elasticsearch Java API Client's `Query` type with the Spring Data Criteria API's `Query`; they are distinct abstractions.

## 10. Script Fields in NativeQuery

The Elasticsearch Java API Client provides `ScriptField` to describe script fields. In supported versions, `NativeQuery` includes a builder method to attach scripted fields.

Example following the 5.x API:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.elasticsearch._types.ScriptField;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Script profitScript = Script.of(s -> s
    .inline(i -> i
        .lang("painless")
        .source("doc['price'].value - doc['cost'].value")
    )
);

ScriptField profitField = ScriptField.of(f -> f
    .script(profitScript)
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(Query.of(q -> q.matchAll(m -> m)))
    .withScriptedField("profit", profitField)
    .build();
~~~

Confirm the `withScriptedField` method name and `ScriptField` type against your Spring Data Elasticsearch version. Script field results are returned in the search hit's `fields` metadata; they do not become properties inside `Product`'s `_source`.

At the application layer, read the field from `SearchHit` metadata or whatever result-mapping mechanism your Spring Data version provides. Do not assume a script field will automatically populate a `Product` property if the entity lacks an appropriate mapping.

If you need to return a DTO containing `profit`, use `SearchHit` metadata to construct a response DTO rather than forcing computed values into domain entities.

## 11. Runtime Fields in NativeQuery

The Elasticsearch Java API Client represents runtime fields with `RuntimeField`. In Spring Data Elasticsearch versions that expose runtime field support on the NativeQuery builder, you can pass a map of runtime fields into the query.

Illustrative example using the Java Client API style:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.elasticsearch._types.mapping.RuntimeField;

Script profitScript = Script.of(s -> s
    .inline(i -> i
        .lang("painless")
        .source(
            "if (doc['price'].size() != 0 && doc['cost'].size() != 0) " +
            "{ emit(doc['price'].value - doc['cost'].value); }"
        )
    )
);

RuntimeField profitRuntimeField = RuntimeField.of(r -> r
    .type("long")
    .script(profitScript)
);
~~~

In Spring Data versions exposing runtime mappings via the NativeQuery builder, runtime fields can be attached via a method such as `withRuntimeField` or `withRuntimeFields`. Confirm exact method names and map types in the Javadoc of your exact dependency; this API has evolved across Spring Data Elasticsearch generations.

If your version does not expose runtime mappings on the NativeQuery builder, you can use the Elasticsearch Java API Client directly to build a `SearchRequest` with `runtime_mappings`, or upgrade to a compatible release. Do not assume `CriteriaQuery` can express every runtime field option.

A practical check is to inspect IDE autocomplete or Javadoc on `NativeQuery.Builder` to see which runtime field, scripted field, query, sort, and aggregation methods exist in your current dependency.

## 12. Runtime Fields and Spring Data Entity Mapping

Runtime fields declared in a request are not the same as regular Java fields in an entity.

For example, `Product` has:

~~~java
public class Product {
    private Long price;
    private Long cost;
}
~~~

A `profit` runtime field can be created in the request without adding a `profit` property to the `Product` class. The `profit` value is returned in the `fields` section of each search hit.

If you want to map results into a dedicated object:

~~~java
public record ProductSearchResult(
    String id,
    Long price,
    Long cost,
    Long profit
) {
}
~~~

The service can read `Product` from the hit, extract `profit` from field metadata, and build the DTO. Exact field value access depends on `SearchHit` and the Spring Data Elasticsearch version.

Do not confuse runtime fields with `@Field` on an entity. `@Field` describes a document's mapped field; a runtime field is computed at query time and may exist only for the scope of a single request.

## 13. Stored Scripts and Inline Scripts

Scripts can be sent directly inside the request (inline) or stored on the cluster and referenced by ID (stored script).

Inline script:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value > params.minimum",
    "params": {
      "minimum": 100000
    }
  }
}
~~~

A stored script is registered via the Stored Scripts API:

~~~http
PUT /_scripts/price-threshold
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value > params.minimum"
  }
}
~~~

Then invoked by ID:

~~~http
POST /products/_search
{
  "query": {
    "script": {
      "script": {
        "id": "price-threshold",
        "params": {
          "minimum": 100000
        }
      }
    }
  }
}
~~~

Stored scripts are useful when the same logic is reused across multiple places and needs centralized management. Script updates should follow proper versioning, testing, and deployment workflows.

Whether using inline or stored scripts, pass dynamic values via `params`. Never generate a new stored script ID per request or concatenate arbitrary input into script source.

## 14. Script Limits and Performance

Scripts can run over many documents and multiple shards. Even a simple script can become costly when evaluated across millions of documents.

Guidelines:

- Use `term`, `range`, `exists`, `bool`, and standard queries whenever possible.
- Place cheap filter conditions before scripts to narrow the document set.
- Avoid accessing `_source` inside loops when doc values suffice.
- Check for missing fields before accessing `.value`.
- Use `params` to keep script source stable and aid compilation caching.
- Limit scripts running over large result sets.
- Measure latency, CPU, and shard execution count.
- Avoid complex scripts in sorting or aggregations when precomputed values can be stored.

Elasticsearch enforces limits and security settings around scripting, including permitted contexts, script types, and inline/stored script usage. Exact settings depend on version and cluster policy. Never alter cluster-wide script settings merely to make an example run without understanding the security and operational implications.

### 14.1. Script Compilation Cache

Elasticsearch compiles scripts and can cache compiled scripts. If source strings change constantly because request values are concatenated into them, caching becomes ineffective and causes compilation pressure.

Keep source stable:

~~~text
doc['price'].value > params.minimum
~~~

and vary only `params.minimum` per request.

This keeps code cleaner while maximizing compiled script reuse.

### 14.2. Scripts Do Not Replace All Business Logic

Do not push complex business logic into Painless just because fields are accessible there. Rules spanning multiple systems, authorization checks, transaction states, or validations needing detailed error messages generally belong in the application layer.

Scripts should remain concise, data-local calculations or predicates controllable inside a query.

## 15. Runtime Fields vs. Pre-Stored Fields

Suppose profit always equals `price - cost`. There are two options:

**Compute at query time with a runtime field**

Advantages:
- No need to update older documents when calculation logic changes.
- Does not increase `_source` size with precomputed fields.
- Convenient for rapid experimentation with logic.

Limitations:
- Recomputed on every query referencing the field.
- Queries, sorting, and aggregations can consume CPU.
- No prebuilt inverted index or doc values like physical fields.
- Depends on Elasticsearch scripting and runtime field support.

**Store profit when indexing documents**

Advantages:
- Queries, filters, sorting, and aggregations are typically more efficient.
- Can leverage standard mappings and index structures.
- Avoids recomputing the same expression on every request.

Limitations:
- Must update `profit` whenever `price` or `cost` changes.
- Data can drift out of sync if write pipelines do not update all dependent fields.
- Changing the formula requires data migration or reindexing.

| Criterion | Runtime Field | Physical Field |
|---|---|---|
| Stored in document source | Not required | Yes |
| Computed at query time | Yes | No, if precomputed at write |
| Formula updates | Update script | Update stored data |
| Frequent filter/sort/aggregation | Can be costly | Usually more efficient |
| Logic experimentation | Convenient | Requires write pipeline changes |
| Best suited for | Infrequently used or flexible logic | Critical, frequently queried fields |

## 16. NativeQuery and Differences Across Versions

The `NativeQuery` API has evolved alongside client generations and Spring Data Elasticsearch releases. When working with scripts and runtime fields, know which version your project uses.

| Generation | Common API Types | Key Notes |
|---|---|---|
| Spring Data Elasticsearch 4.x and earlier | `NativeSearchQuery`, `NativeSearchQueryBuilder`, typically tied to `RestHighLevelClient` | Do not use Elasticsearch Java API Client 8.x builders/types directly if dependencies have not migrated |
| Spring Data Elasticsearch 5.x | `NativeQuery` and Elasticsearch Java API Client | `Query`, `Script`, `ScriptField`, `RuntimeField` use types from `co.elastic.clients` |
| Different 5.x releases | Builders and overloads may be added across releases | Check Javadoc/source of your exact minor version |
| Newer releases | Client/API may evolve per Elasticsearch compatibility | Check the Spring Data, Spring Boot, and Elasticsearch compatibility matrix |

Do not mix the following types:

- `org.springframework.data.elasticsearch.core.query.Query`: Spring Data's query abstraction.
- `co.elastic.clients.elasticsearch._types.query_dsl.Query`: the Elasticsearch Java API Client query type.
- Legacy `RestHighLevelClient` query classes in older projects.

`NativeQuery` in the Elasticsearch Java Client generation accepts the corresponding client query type. `CriteriaQuery` remains a Spring Data Query abstraction. When converting between APIs, construct the exact query type expected by the method overload.

### 16.1. Determining the API in Your Project

Check your dependency tree or build file to identify your Spring Data Elasticsearch and Elasticsearch Java API Client versions. Then:

1. Open Javadoc or IDE autocomplete for `NativeQuery.Builder`.
2. Confirm which `Query` type `withQuery` accepts.
3. Check whether `withScriptedField`, `withRuntimeField`, or `withRuntimeFields` exists.
4. Check which client package `Script` and `RuntimeField` belong to.
5. Verify Elasticsearch server compatibility with the client.
6. Run integration tests against the matching Elasticsearch version.

If the project uses the older `NativeSearchQueryBuilder`, 5.x `NativeQuery` examples cannot be pasted directly. Use the matching API or plan a synchronized dependency upgrade.

## 17. Testing Scripts and Runtime Fields

Do not verify scripts merely by reading source strings. Run the queries on an Elasticsearch test instance with representative data.

Example indexing three products:

~~~json
POST /products/_bulk
{"index":{"_id":"P-1"}}
{"price":200000,"cost":150000,"active":true}
{"index":{"_id":"P-2"}}
{"price":250000,"cost":220000,"active":true}
{"index":{"_id":"P-3"}}
{"price":90000,"cost":40000,"active":false}
~~~

Test script query with `minimum = 30000`:

~~~http
POST /products/_search
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value - doc['cost'].value > params.minimum",
        "params": {
          "minimum": 30000
        }
      }
    }
  }
}
~~~

`P-1` and `P-3` have profit greater than 30,000, while `P-2` does not match. If only active products are desired, add an `active=true` filter.

Test runtime field:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "if (doc['price'].size() != 0 && doc['cost'].size() != 0) { emit(doc['price'].value - doc['cost'].value); }"
      }
    }
  },
  "fields": ["profit"],
  "query": {
    "range": {
      "profit": {
        "gte": 30000
      }
    }
  }
}
~~~

Tests should cover:

- Documents with all fields populated.
- Documents missing `price` or `cost`.
- Negative or zero values if allowed by business rules.
- Fields with mismatched mapping types.
- Queries with boundary `params` values.
- Runtime fields whose declared type matches emitted values.
- Correct reading of `fields` at the Spring Data layer.

If a runtime field is used in queries, sorting, and aggregations, test each behavior independently. A runtime field returning the expected value does not automatically prove sorting and aggregations behave with the intended semantics.

## 18. Common Mistakes

| Symptom | Possible Cause | Investigation Step |
|---|---|---|
| Script compilation error | Invalid Painless syntax or wrong context | Read error message; verify permitted variables and functions |
| No field found / field access error | Wrong field name or missing mapping | Inspect mapping and sample documents |
| Missing field causes script failure | Accessing `.value` when value is absent | Check `.size()` before reading |
| Slow script query | Running across too many documents | Add standard filters to narrow candidates |
| High script compilation rate | Source string changes continuously | Move dynamic values into `params` |
| Runtime field absent from `_source` | Runtime fields are not stored in source | Read from `fields` in search hits |
| Runtime field unusable in query | Wrong type/script declaration or unsupported version/API | Verify `runtime_mappings` and mapping |
| NativeQuery rejects `Script` type | Mixing Spring Data and Elasticsearch client APIs | Verify imports and versions |
| `withRuntimeField` does not exist | Spring Data minor version does not expose that builder method | Check Javadoc; use client directly or upgrade |
| Script rejected | Restricted cluster policy or script context | Check cluster scripting permissions and configuration |
| Wrong runtime value | Wrong emitted type, missing field, or inconsistent units | Verify type, data, and script |

## 19. Selection Workflow

Choose the mechanism based on requirements:

1. If the condition can be expressed with `term`, `range`, `exists`, or `bool` queries, use standard queries.
2. If filtering requires a custom calculation, consider a script query.
3. If you only need to attach a computed value to each hit, use a script field.
4. If you need a virtual field usable in queries, sorting, or aggregations, use a runtime field.
5. If a calculation is used frequently and impacts performance, consider storing a physical field.
6. If Criteria cannot express the needed DSL, use `NativeQuery`.
7. If your current version's `NativeQuery` builder does not expose an option, use the Elasticsearch Java API Client directly or plan a controlled upgrade.

## 20. Quick Reference Table

| Need | API |
|---|---|
| Filter documents with a script | script query |
| Add computed values to hits | `script_fields` |
| Define a virtual field in one search request | `runtime_mappings` |
| Define a shared runtime field | runtime field in index mapping |
| Custom search scoring | `script_score` / `function_score` |
| Use Java API Client query DSL | `NativeQuery` |
| Pass dynamic values safely | script `params` |
| Reuse a script in multiple places | stored script |
| Avoid recomputing a frequent field | Store physical field at write time |
| Builder API lacks a needed option | Direct Elasticsearch Java API Client or version upgrade |

Scripts, script fields, and runtime fields extend `NativeQuery`'s capabilities when `CriteriaQuery` or derived queries are insufficient. Clearly distinguish scripts used for filtering, script fields used to enrich hits, and runtime fields used as query-time computed fields. Parameterize scripts, guard against missing fields, control execution costs, and verify APIs against your project's exact Spring Data Elasticsearch and Elasticsearch Java API Client versions.
