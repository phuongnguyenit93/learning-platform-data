# Search Templates, Template Parameters, and Choosing the Right Implementation API

Elasticsearch Search Templates let you predefine a query's structure and pass different values on each search. Templates typically use Mustache to substitute parameters, toggle parts of conditions on or off, or iterate over lists of values.

This approach is useful when multiple screens or services share a query with a stable structure. Instead of concatenating JSON strings in code, the application sends a template ID along with parameters. Elasticsearch renders the template into Query DSL and executes it against the specified index.

In Spring Data Elasticsearch, distinguish Search Templates from `CriteriaQuery` and `NativeQuery`. A Search Template is a feature of the Elasticsearch Search API, managed through the Stored Script API and executed through the Search Template API. When calling this feature directly from Java, you can use the `ElasticsearchClient` from the Elasticsearch Java API Client configured in your application.

## 1. What Problem Do Search Templates Solve?

Suppose an application has several product search screens. Each screen needs to:

- Perform full-text search by name.
- Always restrict by tenant.
- Optionally filter by status.
- Optionally filter by one or more categories.
- Optionally set minimum or maximum price.
- Vary page size.

The query structure is nearly identical across screens, with only parameter values changing. If every service constructs JSON itself, code becomes repetitive and braces, commas, or filter rules become hard to keep consistent.

Search Templates separate two parts:

- **Template**: Query DSL structure and parameterization rules.
- **Params**: concrete values for a single search execution.

~~~mermaid
flowchart TD
    A["Application sends template ID + params"] --> B["Elasticsearch Search Template API"]
    B --> C["Fetch stored Mustache template"]
    C --> D["Render params into JSON query"]
    D --> E["Execute Search API on index"]
    E --> F["Search response"]
~~~

A single template can be reused with many parameter sets. Changing a keyword or status does not require constructing an entirely new JSON query in application code.

## 2. Search Templates and Mustache

Elasticsearch uses Mustache as the template language for stored search templates.

Simple template example:

~~~json
{
  "query": {
    "match": {
      "name": "{{query_string}}"
    }
  }
}
~~~

When rendered with parameters:

~~~json
{
  "query_string": "wireless keyboard"
}
~~~

Elasticsearch produces an equivalent query:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Basic Mustache syntax:

| Syntax | Meaning |
|---|---|
| `{{name}}` | Substitutes the value of parameter `name` |
| `{{#name}}...{{/name}}` | Renders content only when the parameter is truthy |
| `{{^name}}...{{/name}}` | Renders content when the parameter is missing or falsy |
| `{{#items}}...{{/items}}` | Iterates over a list or evaluates a section |
| `{{.}}` | Current element value during iteration |
| `{{#toJson}}value{{/toJson}}` | Serializes the parameter as JSON |

For complex parameters such as arrays or objects, the `toJson` helper produces valid JSON structure. Avoid manual JSON string concatenation or injecting arbitrary JSON fragments from user input.

## 3. Creating Stored Search Templates with the Stored Script API

Search templates are saved as stored scripts using the `mustache` language. The management API is the Stored Script API:

~~~http
PUT /_scripts/product-search
Content-Type: application/json

{
  "script": {
    "lang": "mustache",
    "source": {
      "query": {
        "match": {
          "name": "{{query_string}}"
        }
      }
    }
  }
}
~~~

In this example:

- `_scripts/product-search` is the endpoint storing the template with ID `product-search`.
- `lang: mustache` specifies the rendering engine.
- `source` holds the parameterized Query DSL.
- `{{query_string}}` is the parameter supplied at execution time.

Templates can use a JSON object `source` as shown above or a JSON string depending on the API and version. The object form makes structure easier to read and avoids quote-escaping mistakes.

Once the API succeeds, the template is saved in the cluster and can be invoked by ID from any application permitted to execute search templates.

### Inspecting a Stored Template

You can retrieve a saved template:

~~~http
GET /_scripts/product-search
~~~

Reading it back verifies the template ID and the exact definition deployed on the cluster.

### Deleting a Stored Template

When a template is no longer used:

~~~http
DELETE /_scripts/product-search
~~~

Deleting a template should follow a controlled deployment process, because applications still calling that ID will immediately fail once it disappears.

## 4. Rendering Templates Before Execution

Before using a template in the Search API, render it first to inspect the final JSON query. Elasticsearch provides the Render Search Template API:

~~~http
POST /_render/template
Content-Type: application/json

{
  "id": "product-search",
  "params": {
    "query_string": "wireless keyboard"
  }
}
~~~

The API returns the template content after Mustache parameter substitution. This lets you verify:

- Placeholders use the right names.
- Optional sections render as intended.
- The rendered JSON has valid structure.
- Arrays and objects serialize cleanly.

The Render API does not execute a search on an index. It only returns the rendered output. Once verified, you can send the same template ID and params to the Search Template API.

## 5. Executing Search Templates on an Index

Use the Search Template API to render and execute a template:

~~~http
POST /products/_search/template
Content-Type: application/json

{
  "id": "product-search",
  "params": {
    "query_string": "wireless keyboard"
  }
}
~~~

In the request:

- `products` is the target index or alias to search.
- `_search/template` is the Search Template API.
- `id` identifies the stored template.
- `params` contains the input values.

The result is a Search response identical to the standard Search API: total hits, hits, scores, sources, and metadata depending on the query.

HTTP GET or POST can be used per Elasticsearch endpoint support; for requests with a body, POST works most reliably across proxies, gateways, and HTTP libraries.

## 6. Using Inline Templates When Cluster Storage Is Not Needed

You do not always have to store a template beforehand. The Search Template API also accepts `source` directly in the request:

~~~http
POST /products/_search/template
Content-Type: application/json

{
  "source": {
    "query": {
      "match": {
        "name": "{{query_string}}"
      }
    }
  },
  "params": {
    "query_string": "wireless keyboard"
  }
}
~~~

Inline templates are useful when:

- Experimenting with queries.
- A template is used in only one minor flow.
- You want to verify Mustache behavior before deploying a stored template.

When the same structure is shared across multiple services or needs version control, stored templates are usually cleaner. A template ID decouples query content from code and allows query changes to be deployed independently through governance processes.

## 7. Optional Parameters and Mustache Sections

Search forms often have optional filters. Mustache sections render a condition only when its parameter is supplied.

Example stored template with mandatory tenant and optional status:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#status}},
        {
          "term": {
            "status": "{{status}}"
          }
        }
        {{/status}}
      ]
    }
  }
}
~~~

When `status` is present, the term clause is added to filter. When status is absent, the section is skipped and the query stays valid JSON.

Example rendering with status:

~~~json
{
  "tenant_id": "tenant-42",
  "status": "PUBLISHED"
}
~~~

The rendered query filters by both tenant and status.

If only tenant is passed:

~~~json
{
  "tenant_id": "tenant-42"
}
~~~

The status condition is omitted. The tenant condition is always kept.

### Using Sections for Price Ranges

You can split lower and upper bounds into two optional range queries:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#min_price}},
        {
          "range": {
            "price": {
              "gte": {{min_price}}
            }
          }
        }
        {{/min_price}}
        {{#max_price}},
        {
          "range": {
            "price": {
              "lte": {{max_price}}
            }
          }
        }
        {{/max_price}}
      ]
    }
  }
}
~~~

If only minimum price is supplied, the template adds only the lower bound. If only maximum price is supplied, it adds only the upper bound. If both are present, both range queries combine inside filter, equivalent to an AND condition.

Numeric values must be passed as numbers in params, not strings with currency symbols. Validate `min_price <= max_price` before sending the request.

## 8. Passing Lists with toJson

When users select multiple statuses or categories, you can use a `terms` query with the `toJson` helper:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#statuses}},
        {
          "terms": {
            "status": {{#toJson}}statuses{{/toJson}}
          }
        }
        {{/statuses}}
      ]
    }
  }
}
~~~

Params:

~~~json
{
  "tenant_id": "tenant-42",
  "statuses": ["PUBLISHED", "APPROVED"]
}
~~~

The `toJson` helper serializes the array into a JSON array. After rendering, the condition is equivalent to:

~~~json
{
  "terms": {
    "status": ["PUBLISHED", "APPROVED"]
  }
}
~~~

The `statuses` section skips the terms filter when the list is empty or omitted. The application should still normalize and validate the list beforehand—such as deduplicating values and accepting only valid statuses.

Do not place `{{statuses}}` directly in JSON expecting Mustache to format a list into a proper array. For arrays and objects, use the `toJson` helper to serialize data.

## 9. Complete Template for a Product Filter Form

Example template with mandatory tenant and optional keyword, status, category list, and price range:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "{{query_string}}"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#status}},
        {
          "term": {
            "status": "{{status}}"
          }
        }
        {{/status}}
        {{#categories}},
        {
          "terms": {
            "category": {{#toJson}}categories{{/toJson}}
          }
        }
        {{/categories}}
        {{#min_price}},
        {
          "range": {
            "price": {
              "gte": {{min_price}}
            }
          }
        }
        {{/min_price}}
        {{#max_price}},
        {
          "range": {
            "price": {
              "lte": {{max_price}}
            }
          }
        }
        {{/max_price}}
      ]
    }
  },
  "from": {{from}},
  "size": {{size}},
  "sort": [
    {
      "createdAt": {
        "order": "{{sort_order}}"
      }
    }
  ]
}
~~~

Sample params:

~~~json
{
  "tenant_id": "tenant-42",
  "query_string": "wireless keyboard",
  "status": "PUBLISHED",
  "categories": ["ACCESSORIES", "KEYBOARD"],
  "min_price": 100000,
  "max_price": 500000,
  "from": 0,
  "size": 20,
  "sort_order": "desc"
}
~~~

If keyword is also optional, wrap the entire `must` clause in a section while ensuring the rendered query remains valid. You can fall back to `match_all` when no keyword is provided if business rules allow it.

In production, `from`, `size`, and `sort_order` must be validated and bounded in the application. Never let clients send huge page sizes or unapproved sort values.

## 10. Calling Search Templates with the Elasticsearch Java API Client

In Spring Data Elasticsearch 5.x, applications can typically use the Elasticsearch Java API Client through the `ElasticsearchClient` bean configured in the application context.

Required imports:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch.core.SearchTemplateResponse;
import java.io.IOException;
import java.util.Map;
~~~

Service example invoking a stored template:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchTemplateResponse;
import co.elastic.clients.json.JsonData;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.Map;

@Service
public class ProductTemplateSearchService {

    private final ElasticsearchClient client;

    public ProductTemplateSearchService(ElasticsearchClient client) {
        this.client = client;
    }

    public SearchTemplateResponse<ProductDocument> search(
            String keyword,
            String tenantId
    ) throws IOException {

        Map<String, JsonData> params = Map.of(
                "query_string", JsonData.of(keyword),
                "tenant_id", JsonData.of(tenantId)
        );

        return client.searchTemplate(request -> request
                        .index("products")
                        .id("product-search")
                        .params(params),
                ProductDocument.class
        );
    }
}
~~~

Components:

- `ElasticsearchClient` calls the Search Template API directly.
- `index("products")` specifies the target index or alias.
- `id("product-search")` selects the stored template.
- `params(params)` passes parameters as `JsonData`.
- `SearchTemplateResponse<T>` holds the Search Template API response.

This snippet illustrates calling the Java Client API; overload signatures and response types must match the Elasticsearch Java API Client version your project uses.

### Note on Result Conversion

When calling `ElasticsearchClient.searchTemplate(...)` directly, `_source` deserialization is handled by the Java Client's JSON mapper. This is a direct client call, not Spring Data's `ElasticsearchOperations.search(...)`.

If your entities use custom converters or Spring Data-specific mapping metadata, check how the client JSON mapper deserializes documents. You can use a DTO suited to the JSON mapper, receive source as JSON data/maps and convert via an application mapper, or use `ElasticsearchOperations` with `NativeQuery` when the Search Template API is not needed.

Do not assume `@Field`, `@WritingConverter`, or `@ReadingConverter` always apply identically when deserializing directly via the client. Both paths can share the underlying client connection yet carry different mapping responsibilities.

## 11. When to Use Search Template, NativeQuery, or CriteriaQuery?

These three options serve different needs:

| Criterion | Search Template | NativeQuery | CriteriaQuery |
|---|---|---|---|
| Query definition | Stored or inline Mustache template | Java Client Query DSL | Spring Data Criteria API |
| Parameters | Passed separately via params | Java code building query objects | Java code adding Criteria |
| Query management | Can be versioned and deployed on the cluster | Lives in application code | Lives in application code |
| Reuse across multiple clients | Convenient via template ID | Requires sharing code/libraries | Requires sharing code/libraries |
| Dynamic queries | Mustache sections and params | Java logic and typed DSL | Criteria conditions |
| Execution | Search Template API | ElasticsearchOperations | ElasticsearchOperations |
| Best suited for | Stable queries reused in many places, needing independent updates | Complex DSL built in Java | Common filters, simple structure |

Choose Search Templates when query structure needs centralized management, is invoked by multiple applications, or must deploy query changes independently of application binaries.

Choose NativeQuery when queries are built dynamically in Java and need type-safe DSL or advanced Elasticsearch features.

Choose CriteriaQuery when search forms have standard conditions and you want to stay within Spring Data's abstraction.

## 12. Distinguishing Search Templates from Index Templates

The names sound similar, yet the two features serve completely different purposes:

| Feature | Search Template | Index Template |
|---|---|---|
| Purpose | Reuse search query structure | Apply settings, mappings, and aliases to new indices |
| Management API | Stored Script API, `_scripts` | Index Template API, `_index_template` |
| Contents | Mustache query DSL | Index settings, mappings, aliases |
| When applied | When rendering/executing a search request | When creating an index matching a pattern |
| Example | `product-search` | `products-template` |

Search Templates do not create mappings or indices. Index Templates are not query templates and do not accept per-search params.

## 13. Versioning and Deploying Templates

Stored templates live inside the cluster. Therefore, keep template definitions in source control and deploy them through versioned pipelines or migrations.

A typical workflow:

~~~mermaid
flowchart TD
    A["Store template JSON in source control"] --> B["Review changes"]
    B --> C["Pipeline calls PUT /_scripts/template-id"]
    C --> D["Call POST /_render/template to verify"]
    D --> E["Run test searches on test index"]
    E --> F["Have application call template ID"]
~~~

You can include versions in template names, for example:

- `product-search-v1`
- `product-search-v2`

When making query changes that affect results, deploy a new ID, verify with the Render API and test on staging data, and then update the application or configuration to point to the new ID.

If you overwrite the content of an existing ID, applications calling that ID will immediately pick up the new behavior. Coordinate rollouts and rollbacks carefully.

### Avoid Deploying Stored Templates on Every Application Startup

Calling `PUT /_scripts/...` usually requires broader cluster admin permissions than ordinary search operations. If every runtime instance updates templates at startup:

- Multiple instances can race and overwrite the same template.
- The active template version depends on startup order.
- Runtime service accounts end up holding unnecessary admin privileges.
- Rollbacks and change auditing become difficult to control.

Separate template deployment accounts or jobs from runtime accounts that only perform searches.

## 14. Security and Parameter Limits

Search Templates separate query structure from input data, but they do not replace input validation.

Key principles:

1. Pass parameters through `params`; never concatenate JSON strings from user input.
2. Use `toJson` for arrays and objects.
3. Avoid Mustache triple braces to inject raw JSON from untrusted input.
4. Never let clients supply arbitrary field names via placeholders.
5. Use an allowlist for sort fields and sort directions.
6. Validate page sizes, `from`/offset, price ranges, and value lists.
7. Always keep mandatory tenant/permission filters in the template or inject them from an authenticated context.
8. Grant stored-script management permissions only to deployment pipelines.
9. Runtime accounts only need search/read privileges on relevant indices or aliases.
10. Never put secrets such as API keys, passwords, or tokens into template params.

If a template allows callers to substitute field names, query types, or JSON structural fragments, callers can alter query scope unexpectedly. Keep query structure owned by the application and pass only validated data parameters.

## 15. Common Mistakes

### Template ID Does Not Exist

The Search Template API returns an error when calling a stored template that has not been deployed or was deleted. Check using:

~~~http
GET /_scripts/product-search
~~~

### Rendering Invalid JSON

A section can leave trailing or missing commas when a parameter is empty. Call the Render API with both a full set of params and a minimal set of params to check all branches.

### Forgetting Required Parameters

If a template references `{{tenant_id}}` but a request omits `tenant_id`, the query may render with an unintended value or fail. Validate required parameters in the application before invoking the template.

### Using toJson in the Wrong Position

`toJson` emits a JSON representation. Do not wrap the helper output in quotes when that position expects an actual JSON array or object.

### Confusing Search Templates with Index Templates

`_scripts` stores query templates. `_index_template` stores settings/mappings applied during index creation. Calling the wrong API will not produce the expected behavior.

### Expecting Search Templates to Create Mappings

Templates only construct queries. Indices and mappings must already exist or be created by a separate provisioning process.

### Calling Search Templates Through ElasticsearchOperations

`ElasticsearchOperations.search(...)` accepts Spring Data `Query` objects such as `NativeQuery` or `CriteriaQuery`. The Search Template API is a separate endpoint on the Elasticsearch Java API Client; when you need that functionality, call `ElasticsearchClient.searchTemplate(...)` or the corresponding HTTP API.

### Using Entity Converters Through the Wrong Path

Results from calling the Java Client directly are deserialized via the client's JSON mapper. If you need Spring Data custom conversions, design a suitable conversion step rather than assuming Search Template responses go through `MappingElasticsearchConverter`.

## 16. Workflow for Deploying Search Templates

When introducing a template into an application:

1. Define the Query DSL and the field mappings the template will target.
2. Choose required and optional parameters, specifying the data type of each.
3. Write the Mustache source, using sections for optional clauses and `toJson` for arrays/objects.
4. Store the template in source control with its version and parameter documentation.
5. Deploy via `PUT /_scripts/{id}` through a pipeline with appropriate privileges.
6. Call `POST /_render/template` to verify representative parameter sets.
7. Test execution via `POST /{index}/_search/template` on a test or staging index.
8. Update the application to call the template ID and pass params.
9. Monitor render errors, query failures, and execution latency.
10. When making major query changes, deploy a new versioned ID and migrate the application as planned.
11. Keep the old template for as long as rollback requires.
12. Delete the old template once no clients remain on it.

## Conclusion

Search Templates provide a way to reuse Query DSL with Mustache templates and parameters. Stored templates are managed through the Stored Script API at `_scripts/{id}`; the Render API lets you inspect the query after parameter substitution; the Search Template API executes the template against an index. In Spring Data Elasticsearch, you can call `ElasticsearchClient.searchTemplate(...)` directly when this feature is needed, whereas `NativeQuery` and `CriteriaQuery` suit queries built in code via `ElasticsearchOperations`. Version your templates, validate params, retain mandatory access-control filters, and separate stored-script deployment permissions from runtime search permissions.
