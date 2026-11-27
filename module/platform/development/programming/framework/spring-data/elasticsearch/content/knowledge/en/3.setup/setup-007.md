# Inspecting Indices, Mappings, and Data Using Elasticsearch APIs

Elasticsearch provides REST APIs to observe cluster status, inspect indices, read mappings, and query documents. When a Spring Data Elasticsearch application fails to find data or returns unexpected results, these APIs help determine whether the issue lies in the index, field structure, or documents written into Elasticsearch.

Three concepts to distinguish:

- **Index**: where Elasticsearch stores a collection of related documents. You can think of an index somewhat like a table in a relational database, though storage and querying differ.
- **Mapping**: describes data types and how Elasticsearch processes each field, such as `text`, `keyword`, `date`, `long`, or `nested`.
- **Document**: a JSON record stored in an index. Each document has an `_id`, and its content is typically returned in `_source`.

The commands in this lesson focus on reading and inspecting data. You can run them in Kibana **Dev Tools → Console**, or send HTTP requests using curl, Postman, or another REST client.

## 1. Preparing the Elasticsearch Address

An Elasticsearch node in a development environment is typically accessed via an address such as:

```text
http://localhost:9200
```

This is only an illustrative address. Use the exact host, port, and protocol configured for your environment. Elasticsearch in deployed environments may require HTTPS, username, password, API key, or TLS certificates.

In Kibana Dev Tools, enter the request directly using the syntax:

```http
GET /
```

In a terminal, you can set the address and credentials via environment variables and call the API. The example below illustrates calling via curl; replace sample values with your environment's configuration:

```bash
export ES_URL="http://localhost:9200"
export ES_USERNAME="elastic"
export ES_PASSWORD="your-password"

curl --user "$ES_USERNAME:$ES_PASSWORD" "$ES_URL/"
```

On Windows PowerShell, use `curl.exe` to invoke the curl executable rather than the `curl` alias which may point to `Invoke-WebRequest`:

```powershell
$env:ES_URL = "http://localhost:9200"
$env:ES_USERNAME = "elastic"
$env:ES_PASSWORD = "your-password"

curl.exe --user "$($env:ES_USERNAME):$($env:ES_PASSWORD)" "$($env:ES_URL)/"
```

Do not write real passwords into source code, committed config files, or shared command history. If the cluster uses HTTPS with an internal CA, configure curl to trust that CA with the `--cacert` option. Only in a temporary local environment should you consider skipping certificate verification; never turn that into a deployment configuration.

The `GET /` request returns basic node/cluster info, typically including node name, cluster name, Elasticsearch version, and some build info. This is the first step to confirm you are connecting to the right server and check the running version.

## 2. Checking Cluster Status and Index List

### 2.1. Viewing Cluster Health

Send the request:

```http
GET /_cluster/health?pretty
```

An abbreviated response might look like this:

```json
{
  "cluster_name": "elasticsearch",
  "status": "green",
  "number_of_nodes": 1,
  "active_primary_shards": 3,
  "active_shards": 3,
  "unassigned_shards": 0
}
```

Fields to pay attention to:

| Field | Meaning |
|---|---|
| `status` | Overall health status: `green`, `yellow`, or `red`. |
| `number_of_nodes` | Number of nodes currently in the cluster. |
| `active_primary_shards` | Number of active primary shards. |
| `active_shards` | Total number of active shards, including primary and replica. |
| `unassigned_shards` | Number of shards not yet assigned to a node. |

Meaning of the three statuses:

- **green**: all primary shards and required replica shards are allocated.
- **yellow**: primary shards are allocated, but at least one replica shard is unassigned. Data can still be read and written, though redundancy is incomplete.
- **red**: at least one primary shard is unassigned. Part of the data may be inaccessible.

A single-node cluster usually cannot allocate replicas onto a second node. Therefore, a `yellow` status in a single-node local environment can be expected and does not mean the index is broken. Check the node count, shard count, and replica settings before drawing conclusions.

### 2.2. Listing Indices

Use the CAT Indices API:

```http
GET /_cat/indices?v&s=index
```

The tabular output gives a quick overview of index names, statuses, primary shard counts, replica counts, document counts, and storage size:

```text
health status index    uuid                   pri rep docs.count store.size
green  open   products AbCdEf1234567890        1   0   125        48kb
```

Important columns:

- `health`: health status of the index.
- `status`: open or closed status of the index.
- `index`: index name.
- `pri`: number of primary shards.
- `rep`: configured number of replica shards.
- `docs.count`: number of documents counted in the index.
- `store.size`: storage size of the index.

You can filter to view a specific index:

```http
GET /_cat/indices/products?v
```

CAT APIs are designed for human reading during operations and inspection. When writing programs that parse structured data, prefer dedicated JSON APIs rather than relying on CAT table formatting.

### 2.3. Checking Whether an Index Exists

Use a HEAD request:

```http
HEAD /products
```

Typically:

- HTTP `200`: the index exists.
- HTTP `404`: the index does not exist or the requested name does not resolve to an index.

If you want to view index metadata, use:

```http
GET /products?pretty
```

The response provides index metadata, including settings and mappings. We will inspect mappings separately in the next section to focus on field structure.

Elasticsearch index names must be lowercase. If the application declares `products` while your request checks `Products`, you may be checking the wrong name. Besides direct indices, a name used by an application could also be an alias. To inspect aliases:

```http
GET /_cat/aliases?v
```

An alias is a name referencing one or more indices. Verify whether the application points to a real index or an alias before concluding data is in the wrong place.

### 2.4. Inspecting Shards When an Index Has Issues

If an index has an abnormal status, inspect its shards:

```http
GET /_cat/shards/products?v
```

Each line represents a shard and its allocation state. This info helps identify which primary or replica is active, which shard is unassigned, and which node holds each shard. In a single-node development environment, a replica count higher than available nodes can keep an index in `yellow` status.

## 3. Reading Mappings to Inspect Field Structure

Mapping tells Elasticsearch how to interpret each field in a document. This is critical when queries return no results even though documents exist.

Send the request:

```http
GET /products/_mapping?pretty
```

Abbreviated response:

```json
{
  "products": {
    "mappings": {
      "properties": {
        "id": {
          "type": "keyword"
        },
        "name": {
          "type": "text"
        },
        "price": {
          "type": "double"
        },
        "quantity": {
          "type": "integer"
        },
        "createdAt": {
          "type": "date"
        },
        "active": {
          "type": "boolean"
        }
      }
    }
  }
}
```

In this example, Elasticsearch stores `name` as `text` and `id` as `keyword`. These two types serve different purposes:

| Type | Common Usage |
|---|---|
| `text` | Content to analyze into tokens for full-text search, such as names or descriptions. |
| `keyword` | Unanalyzed exact values used for exact filtering, sorting, or aggregations, such as product codes, statuses, or emails. |
| `integer`, `long`, `short`, `byte` | Whole numbers. |
| `float`, `double`, `scaled_float` | Decimal numbers. |
| `boolean` | True/false values. |
| `date` | Date-time values in Elasticsearch-supported or explicitly declared formats. |
| `object` | A JSON object containing subfields. |
| `nested` | An array of objects needing to preserve field relationships within each individual element when querying. |

### 3.1. Distinguishing `text` and `keyword`

Suppose the mapping has:

```json
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
```

Elasticsearch can analyze `name` into tokens for full-text search. The `name.keyword` subfield stores the unanalyzed exact value for exact matching, sorting, or aggregations.

Example:

```http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
```

`match` fits `text` fields because the query text is processed using the field's analyzer.

To match an exact value on a `keyword` field:

```http
POST /products/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mouse"
    }
  }
}
```

`term` compares exact values and does not analyze the string like `match`. If the mapping only has `name: text` without a `name.keyword` subfield, querying `name.keyword` will not behave as expected. Inspect the actual mapping before choosing the field and query type.

### 3.2. Checking Index Settings

Mappings describe fields; settings describe index configuration such as shard counts, replica counts, and analyzer settings:

```http
GET /products/_settings?pretty
```

Example partial response:

```json
{
  "products": {
    "settings": {
      "index": {
        "number_of_shards": "1",
        "number_of_replicas": "0"
      }
    }
  }
}
```

When inspecting an index, do not confuse `number_of_shards` with `number_of_replicas`: primary shards partition the data; replica shards are copies providing fault tolerance and serving some read operations. The replica count does not determine how many documents the application can store.

### 3.3. Checking the Type of a Specific Field

When a mapping is large, you can ask Elasticsearch to return the mapping of a single field:

```http
GET /products/_mapping/field/price
```

Or check field capabilities and types across multiple indices:

```http
GET /products,archived-products/_field_caps?fields=name,price,status
```

The Field Capabilities API is useful when the same field name appears across multiple indices but may have different types. For example, `price` might be `double` in an old index yet `keyword` in a new index. This inconsistency can cause multi-index queries to fail or produce confusing results.

### 3.4. How Do Mappings Change?

An existing mapping cannot arbitrarily change the type of an already created field. For example, if `price` is `keyword`, you cannot directly change it to `double` by sending a new mapping.

There are typically two ways to handle this:

1. Add a new field with the appropriate type if the current structure permits.
2. Create a new index with the right mapping, migrate data via reindexing or an appropriate migration process, and then switch the alias or application to the new index.

Do not send mapping update or reindex commands merely for inspection. Before making structural changes, assess existing data, migration plans, and application impact.

## 4. Inspecting Documents and Stored Data

Once you have confirmed the index exists and the mapping makes sense, inspect specific documents.

### 4.1. Fetching a Document by ID

Use the Get API:

```http
GET /products/_doc/1001?pretty
```

Illustrative response:

```json
{
  "_index": "products",
  "_id": "1001",
  "_version": 1,
  "found": true,
  "_source": {
    "id": "1001",
    "name": "Wireless Mouse",
    "price": 29.9,
    "quantity": 15,
    "active": true
  }
}
```

Fields to read:

- `_index`: the index containing the document.
- `_id`: the document identifier within the index.
- `_version`: internal document version, incremented on updates.
- `found`: indicates whether the document was found.
- `_source`: the stored JSON content of the document, if source is enabled and not excluded.

If the document does not exist, the API returns HTTP `404`. Verify both the index and the ID. The ID used by Spring Data Elasticsearch may come from the property annotated with `@Id`, so the ID value in Java must match the ID you are looking up.

### 4.2. Counting Documents in an Index

Use the Count API:

```http
GET /products/_count?pretty
```

Response:

```json
{
  "count": 125,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  }
}
```

You can count with a condition. For example, counting active products:

```http
POST /products/_count
{
  "query": {
    "term": {
      "active": true
    }
  }
}
```

The Count API reports the number of documents matching the query. If the result is 0, try counting the entire index first, then inspect field types and filter conditions.

### 4.3. Searching Documents with the Search API

To view some documents in the index:

```http
POST /products/_search
{
  "query": {
    "match_all": {}
  },
  "size": 10
}
```

`POST` is used here because the request has a JSON body. The Search API is a read query; using HTTP POST does not mean the request creates or updates documents.

The response usually has the structure:

```json
{
  "took": 3,
  "timed_out": false,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 125,
      "relation": "eq"
    },
    "max_score": 1.0,
    "hits": [
      {
        "_index": "products",
        "_id": "1001",
        "_score": 1.0,
        "_source": {
          "id": "1001",
          "name": "Wireless Mouse",
          "price": 29.9
        }
      }
    ]
  }
}
```

Important fields:

- `took`: time taken by Elasticsearch to process the request, in milliseconds.
- `timed_out`: whether the request timed out.
- `_shards.failed`: number of shards where the query failed.
- `hits.total.value`: reported match count; also check `relation` to see whether the count is exact (`eq`) or a lower bound (`gte`).
- `hits.hits`: the documents returned in the result page.
- `_score`: relevance score of the document for the query, typically meaningful for full-text search.
- `_source`: the returned document data.

The `size` parameter limits the number of documents in `hits.hits`; it does not alter the total match count. Thus `size: 10` can appear alongside `hits.total.value: 125`.

### 4.4. Filtering by Conditions

Example finding products whose names relate to the word `mouse`:

```http
POST /products/_search
{
  "query": {
    "match": {
      "name": "mouse"
    }
  }
}
```

Finding an exact product ID:

```http
POST /products/_search
{
  "query": {
    "term": {
      "id": "1001"
    }
  }
}
```

Filtering products within a price range:

```http
POST /products/_search
{
  "query": {
    "range": {
      "price": {
        "gte": 10,
        "lte": 50
      }
    }
  }
}
```

Combining multiple conditions:

```http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "price": {
              "lte": 50
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "size": 20
}
```

In a `bool` query:

- `must` requires the condition to match and usually contributes to relevance scoring.
- `filter` requires the condition to match without calculating relevance scores; suitable for filter clauses such as status, price ranges, or dates.
- `should` represents optional matching conditions, governed by `minimum_should_match`.
- `must_not` excludes documents matching the condition.

Field types still determine how queries work. Use `match` for full-text search on `text`; use `term` for exact values on `keyword`, boolean, or appropriate numeric fields. For date fields, use `range` and date formats compatible with the mapping.

### 4.5. Limiting Returned Fields and Sorting

When only a few fields are needed, you can restrict `_source` content:

```http
POST /products/_search
{
  "_source": ["name", "price", "active"],
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "price": {
        "order": "desc"
      }
    }
  ],
  "size": 5
}
```

If `_source` is disabled or some fields are excluded in configuration, the response may not contain expected content even though the document exists. In that case, inspect the mapping and source storage settings.

## 5. Relating Elasticsearch Mappings to Spring Data Elasticsearch

In a Spring Data Elasticsearch application, entities typically declare index and field types using annotations. For example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // constructors, getters and setters
}
```

Annotations help Spring Data Elasticsearch map Java properties to document structures and mappings. However, what must be verified is the actual mapping existing on Elasticsearch. The entity in source code may have changed after the index was created; modifying annotations does not automatically prove the mapping on the cluster was updated accordingly.

If the application uses `ElasticsearchOperations`, you can read some metadata via the Spring Data API:

```java
IndexOperations indexOps = operations.indexOps(Product.class);

boolean exists = indexOps.exists();

if (exists) {
    Map<String, Object> mapping = indexOps.getMapping();
    Map<String, Object> settings = indexOps.getSettings();
}
```

The snippet illustrates inspecting from the application side; an `ElasticsearchOperations` bean and matching imports are required in the project. When needing to verify raw REST requests, raw responses, or cluster configuration, calling the REST API directly still shows clearly what Elasticsearch returns.

Repositories also provide application-level operations such as `count()`, `findById(id)`, or declared search methods. Distinguish:

- REST APIs inspect status and data directly on Elasticsearch.
- Spring Data repositories/operations let the application interact with Elasticsearch via Spring's abstractions.
- Entity annotations describe how the application expects data to be mapped.

When repository results differ from REST API results, compare the index name or alias, ID, mapping, generated query, filters, and refresh timing.

## 6. Inspection Workflow When the Application Finds No Data

Suppose the application saves a product, yet the search API returns an empty list. You can inspect in the following order:

**Step 1 — Confirm connection to the right cluster**

```http
GET /
GET /_cluster/health?pretty
```

Cross-check the cluster name, version, and status. If unable to connect, check URL, port, protocol, credentials, TLS, and permissions.

**Step 2 — Confirm the index or alias exists**

```http
GET /_cat/indices?v&s=index
GET /_cat/aliases?v
HEAD /products
```

Ensure the index/alias name matches `indexName` on the entity or application configuration.

**Step 3 — Inspect the actual mapping**

```http
GET /products/_mapping?pretty
GET /products/_settings?pretty
```

Confirm field names, data types, subfields like `.keyword`, analyzers, and date formats. Pay special attention to differences between Java types and the Elasticsearch types created.

**Step 4 — Check whether the document was written**

```http
GET /products/_count?pretty
GET /products/_doc/1001?pretty
```

If count is 0 or the ID does not exist, review the save flow, target index, and ID value.

**Step 5 — Try a simple query first**

```http
POST /products/_search
{
  "query": {
    "match_all": {}
  },
  "size": 5
}
```

If `match_all` returns results while the application query does not, focus on inspecting the query, field types, analyzer, filter conditions, sorting, and pagination.

**Step 6 — Compare against write timing**

Elasticsearch uses a near real-time mechanism for search. A newly indexed document may not appear immediately in the Search API until the next refresh. The Get API by ID can typically read a new document right after write, whereas the Search API depends on refreshes. If Get API sees the document while Search API does not yet see it, check refresh timing before concluding data was lost.

In standard applications, avoid forcing a refresh after every write because continuous refreshes degrade performance. Choose a refresh strategy matching consistency requirements and system load.

## 7. Common Errors and Inspection Approaches

| Symptom | Possible Cause | What to Check |
|---|---|---|
| HTTP `401 Unauthorized` | Missing or invalid credentials. | Check authentication, API key, and client configuration. |
| HTTP `403 Forbidden` | Authenticated account lacks privileges. | Check cluster/index read permissions and API privileges. |
| HTTP `404 Not Found` | Wrong index name, alias, or document ID. | List indices/aliases, then check the ID. |
| Index in `yellow` state | Replica shards are unassigned. | Check node count, replicas, and CAT Shards; single-node setups commonly hit this. |
| Index in `red` state | At least one primary shard is inactive. | Check shard allocation and cluster logs; some data may be unreachable. |
| Count > 0 but query returns no results | Query does not match field type or value. | Try `match_all`, read the mapping, then check `match`/`term` and filters. |
| `term` fails to match a string | Querying a `text` field or value does not match exactly. | Check `keyword` field, analyzer, and stored value. |
| Sort or range fails with data type error | Field has incompatible type or differs across indices. | Read mapping and use the Field Capabilities API. |
| Get by ID has data but Search does not see it yet | Search has not seen changes due to refresh. | Check refresh timing and refresh settings. |
| `_source` is missing fields | Source is disabled or fields are excluded. | Check mapping and source configuration. |
| Document exists but application reads a different index | Inconsistent entity, alias, or index name config. | Cross-check `@Document(indexName = ...)`, aliases, and actual requests. |

When encountering errors, read both the HTTP status and response body. Elasticsearch usually returns an `error` object containing the error type, reason, and related index/shard info. Do not rely solely on a truncated application-side message.

## 8. Precautions When Inspecting Data in Real Environments

`GET`, `HEAD`, and Search/Count queries in this lesson are read operations. Even so, bound query scope on large indices: set a reasonable `size`, fetch only required fields, and avoid unnecessary scans.

Do not run write or delete APIs such as `PUT` creating/updating indices, `DELETE` deleting indices, `_bulk` bulk writes, or `_delete_by_query` when you only intend to inspect. Some requests using HTTP POST—such as `_search` and `_count`—are still read queries; distinguish operations by endpoint and API body, not solely by HTTP method.

Do not include passwords, API keys, or sensitive data in Dev Tools screenshots, logs, shared documents, or public test outputs. In production environments, use an account with minimal required read privileges and follow system access procedures.

## 9. Quick API Reference Table

| Purpose | Request |
|---|---|
| Node/cluster info | `GET /` |
| Cluster health | `GET /_cluster/health?pretty` |
| List indices | `GET /_cat/indices?v` |
| Check if index exists | `HEAD /products` |
| View index metadata | `GET /products?pretty` |
| View shards | `GET /_cat/shards/products?v` |
| View aliases | `GET /_cat/aliases?v` |
| View mapping | `GET /products/_mapping?pretty` |
| View field mapping | `GET /products/_mapping/field/price` |
| View settings | `GET /products/_settings?pretty` |
| Check field types across indices | `GET /products,archived-products/_field_caps?fields=name,price` |
| Fetch document by ID | `GET /products/_doc/1001?pretty` |
| Count documents | `GET /products/_count?pretty` |
| Search documents | `POST /products/_search` |

Replace `products`, `archived-products`, and `1001` with your application's actual index names, aliases, and IDs.

When debugging Spring Data Elasticsearch, an effective inspection order is: confirm cluster → confirm index/alias → read mapping/settings → check document/count → run `match_all` → inspect specific query. Following this order isolates bugs based on actual Elasticsearch responses while avoiding modifying data during investigation.
