# Stored Scripts, Reusability, and Execution Access Control

Elasticsearch allows storing scripts on the cluster and invoking them by ID in search, update, or aggregation requests. This mechanism is called a stored script. Instead of sending the entire source code on every request, the application sends only the script ID along with input parameters.

Stored scripts are useful when a Painless snippet is reused in multiple places, needs centralized deployment, or requires separating permissions to modify scripts from the application's runtime execution permissions. However, storing a script does not automatically make it safe, eliminate execution cost, or replace index-level access control.

Key areas to understand:

- Lifecycle of creating, reading, updating, and deleting stored scripts.
- Invoking stored scripts by ID and passing `params`.
- Different script contexts in Elasticsearch.
- Reusability, compilation caching, and performance limits.
- Integration with Spring Data Elasticsearch and the Elasticsearch Java API Client.
- Role separation between script managers, executing applications, and allowed contexts.

## 1. What Is a Stored Script?

A script is code executed by Elasticsearch within a specific context. Elasticsearch supports Painless as its primary scripting language; other languages or contexts may depend on configuration and version.

A script can be declared directly inside a request (inline script) or stored beforehand on the cluster (stored script).

| Type | Usage | Characteristics |
| --- | --- | --- |
| Inline script | Sends `source` in every request. | Flexible for experimentation or one-off logic; `source` travels with the request. |
| Stored script | Stores `source` under an ID; requests reference only the ID. | Reused across requests, centrally managed, and separates script deployment permissions from the application. |

For example, an application needs to calculate discounted prices. If multiple endpoints share the same formula, you can store script `product-discount-v1` and pass the discount amount via `params`.

Stored scripts are saved in cluster metadata and distributed to nodes via the cluster state mechanism. Therefore, a script ID is a cluster-level managed resource, not a file inside an application folder or a script isolated to individual nodes.

## 2. Creating a Stored Script

Use the Stored Scripts API to create a script:

~~~http
PUT /_scripts/product-discount-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].size() == 0 ? null : doc['price'].value * (1 - params.discount)"
  }
}
~~~

In this example:

- `product-discount-v1` is the script ID.
- `lang` specifies the language, here `painless`.
- `source` contains the script code.
- `params.discount` is the parameter to be passed at execution time.

The API returns acknowledgment that the save succeeded. Saving a script does not execute it; it runs when a request references its ID in a matching context.

### 2.1. Script ID Naming Conventions

A script ID should be:

- Clear and descriptive of its purpose.
- Stable for services to reference.
- Versioned or deployment-suffixed when logic changes.
- Free of sensitive data such as tokens, passwords, or customer information.
- Never built directly from untrusted input.

Example names:

| ID | Purpose |
| --- | --- |
| `product-discount-v1` | Calculate discounted price. |
| `inventory-increment-v1` | Increment inventory stock. |
| `order-transition-v2` | Update order status. |
| `search-score-v1` | Adjust relevance score. |

Using versioned IDs makes rolling out new scripts and rolling back to old versions more controllable. Do not overwrite a script currently used by multiple applications without evaluating the impact.

Scripts referenced in examples later in this lesson must be stored first. For instance, creating a price-range check script:

~~~http
PUT /_scripts/price-in-range-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].size() != 0 && doc['price'].value >= params.minimum && doc['price'].value <= params.maximum"
  }
}
~~~

Scoring script:

~~~http
PUT /_scripts/search-score-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "_score * params.factor"
  }
}
~~~

Inventory increment script:

~~~http
PUT /_scripts/inventory-increment-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.stock == null) { ctx._source.stock = params.amount; } else { ctx._source.stock += params.amount; }"
  }
}
~~~

Order transition script:

~~~http
PUT /_scripts/order-transition-v2
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.status == params.from) { ctx._source.status = params.to; } else { ctx.op = 'noop'; }"
  }
}
~~~

## 3. Reading, Updating, and Deleting Stored Scripts

### 3.1. Reading a Script by ID

~~~http
GET /_scripts/product-discount-v1
~~~

Elasticsearch returns the script metadata, including language and stored source. You can use this API to verify the script ID exists and inspect the currently deployed code.

### 3.2. Updating a Script

Resend `PUT` with the same ID to replace the source:

~~~http
PUT /_scripts/product-discount-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value * (1 - params.discount) + params.shippingFee"
  }
}
~~~

Updating a script ID affects subsequent requests referencing that ID once the cluster accepts and propagates the change. Hence, overwriting an ID actively used in production can alter application behavior without releasing new application code.

A safer workflow is creating a new ID, testing it, switching applications to the new ID, and then retiring the old version.

### 3.3. Deleting a Script

~~~http
DELETE /_scripts/product-discount-v1
~~~

Deleting a script causes subsequent requests referencing that ID to fail to find the stored script. Before deleting, verify no services, jobs, dashboards, or query templates still reference the ID.

### 3.4. Management Lifecycle

~~~text
Write source
    |
    v
Verify syntax and context
    |
    v
PUT /_scripts/<id>
    |
    v
Read back and verify content
    |
    v
Test in staging environment
    |
    v
Application invokes by ID + params
    |
    v
Monitor errors, latency, and compilation
    |
    v
Create new version or delete when no longer used
~~~

Creating, updating, and deleting stored scripts modify cluster-level resources. Manage them like deployment artifacts with owners, versioning, testing, and rollback capability.

## 4. Calling Stored Scripts by ID and `params`

Requests executing scripts reference the ID in the `id` property and pass dynamic data via `params`.

Example using a stored script in a script field:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "match_all": {}
  },
  "script_fields": {
    "discounted_price": {
      "script": {
        "id": "product-discount-v1",
        "params": {
          "discount": 0.15
        }
      }
    }
  }
}
~~~

The script reads `price` from doc values and calculates the price after a 15% discount. The value is returned in `fields` of each hit; it does not modify `_source` or update stored documents.

A hit may contain:

~~~json
{
  "_id": "P-100",
  "_source": {
    "name": "Keyboard",
    "price": 100
  },
  "fields": {
    "discounted_price": [85.0]
  }
}
~~~

### 4.1. `params` Are Input Data

Keep the source stable and pass varying values via `params`:

~~~json
{
  "script": {
    "id": "product-discount-v1",
    "params": {
      "discount": 0.15,
      "shippingFee": 5
    }
  }
}
~~~

The script can read `params.discount` and `params.shippingFee`. Do not concatenate user input strings into source code to create new scripts per request.

Benefits of `params`:

- The source does not change for each value.
- Reduces unnecessary script variants.
- Easier to validate types and value ranges in the application.
- Better utilization of the compilation cache.
- Prevents input data from becoming part of script syntax.

## 5. Using Stored Scripts Across Different Operations

Stored scripts can be referenced across many APIs, provided the script is compatible with the operation's context.

### 5.1. Script Fields in Search

Use when returning a computed value in the response without updating the document:

~~~json
{
  "script_fields": {
    "normalized_price": {
      "script": {
        "id": "product-discount-v1",
        "params": {
          "discount": 0.1
        }
      }
    }
  }
}
~~~

Script fields fit supplementary values for display or per-request calculation. If a value is used frequently for filters, sorts, or aggregations, consider precomputing and storing it as an appropriately mapped field.

### 5.2. Script Query

You can use a stored script in a script query to decide whether a document matches:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "script": {
      "script": {
        "id": "price-in-range-v1",
        "params": {
          "minimum": 100,
          "maximum": 500
        }
      }
    }
  }
}
~~~

Script queries are flexible, but typically more expensive than specialized queries like `range`, `term`, or `bool`. If logic can be expressed in standard Query DSL, prefer those queries so Elasticsearch can leverage indices and built-in optimizations.

### 5.3. Script Score

Stored scripts can adjust relevance scores in `script_score`:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "script": {
        "id": "search-score-v1",
        "params": {
          "factor": 1.2
        }
      }
    }
  }
}
~~~

Script score executes in the scoring context. Accessible variables and valid return types depend on the context; the script must return a valid numeric score. Script score can add significant cost when applied to many documents, so restrict the input document set with an appropriate query/filter.

### 5.4. Updating a Single Document

Stored scripts can modify `_source` in the update context:

~~~http
POST /products/_update/P-100
Content-Type: application/json

{
  "script": {
    "id": "inventory-increment-v1",
    "params": {
      "amount": 3
    }
  }
}
~~~

The body of stored script `inventory-increment-v1` may be:

~~~painless
if (ctx._source.stock == null) {
    ctx._source.stock = params.amount;
} else {
    ctx._source.stock += params.amount;
}
~~~

In the update context:

- `ctx._source` is the content of the document being updated.
- `params.amount` is the increment passed by the caller.
- Changes to source are saved as the new document version if the update succeeds.

To skip the update when a condition is not met, the update script can set `ctx.op = 'noop'`. If deleting the document in the update context is needed, `ctx.op` can be set to the supported operation value. Verify exact context values for your Elasticsearch version.

### 5.5. Update by Query

Stored scripts can be used to update multiple documents matching a query:

~~~http
POST /products/_update_by_query
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "PENDING"
    }
  },
  "script": {
    "id": "order-transition-v2",
    "params": {
      "from": "PENDING",
      "to": "PROCESSING"
    }
  }
}
~~~

Update by query can affect large numbers of documents. Narrow the query, estimate affected document counts, consider slicing/throttling, and monitor version conflicts, timeouts, and task progress. Do not run a broad script update simply because the script is stored and tested on a single document.

## 6. Script Contexts: Same Source Does Not Mean Runs Everywhere

Elasticsearch executes scripts within a script context. The context determines which variables are available, which APIs are allowed, and what return type the script must produce.

Common contexts:

| Context | Purpose | Example data/APIs |
| --- | --- | --- |
| Update | Modify document in update API. | `ctx._source`, `params`. |
| Ingest | Modify document in ingest pipeline. | `ctx`, `params`. |
| Score | Compute relevance score. | `_score`, `doc`, `params`. |
| Filter/query | Evaluate match condition. | `doc`, `params`; boolean result. |
| Field/script field | Produce return value for a field. | `doc`, `params`, result matching field type. |
| Aggregation | Compute metrics or process values in aggregation context. | Context-specific aggregation variables. |
| Sort | Compute sort value via script. | Context-specific sort variables. |

Exact context names and permitted variables depend on the API, field type, and Elasticsearch version. Do not assume variables from the update context exist in the scoring context.

For example, this script suits only the update context:

~~~painless
ctx._source.stock += params.amount;
~~~

In script score, `ctx._source` is not available in that manner. Instead, scripts normally read field values via `doc['price'].value` and return a numeric score.

### 6.1. Notes on Doc Values and `_source`

In search script contexts, `doc` typically accesses field values via doc values. This suits most scalar field reads.

`_source` holds the original JSON structure and is not always available or suited for every context. Scripts reading source can be more resource-intensive. In the update context, `ctx._source` is the standard way to modify documents.

Choose the API based on the goal:

- Reading fields for scoring/sorting/filtering: prefer `doc` if supported by the field.
- Modifying document content: use the update context and `ctx._source`.
- Processing data before indexing: use the ingest context.
- Generating return values: consider script fields or runtime fields per use case.

### 6.2. Verify Context Before Storing

A syntactically valid script may still fail in a different context. Deployment workflows should clarify:

1. Which API will call the script?
2. What is that API's context?
3. Which variables are available in that context?
4. What is the expected return type?
5. Do the accessed fields have supporting mappings?
6. Does the script handle documents with missing or `null` fields?

Do not reuse one script ID across incompatible contexts just to reduce the number of scripts. If the logic is similar across different APIs/contexts, you may need two distinct scripts to make execution contracts clear.

## 7. Stored Scripts and Reusability

Stored scripts offer several operational advantages:

### 7.1. Avoiding Sending Source on Every Request

Requests only need the script ID and `params`. This keeps payloads smaller when sources are long or called frequently.

### 7.2. Centralized Logic Management

A single formula can be referenced by multiple services or jobs. When updates are needed, operations teams can deploy the new script via a centralized pipeline.

### 7.3. Separating Deployment Permissions from Application Permissions

Applications may only need search/update permissions on indices. CI/CD or admin accounts hold permissions to manage stored scripts to create and modify code.

### 7.4. Reducing Dynamic Source Variants

If each request generates a different source by embedding values into strings, the number of scripts requiring compilation grows rapidly. Stored scripts with `params` keep sources stable.

### 7.5. Reusability Does Not Mean Free

Stored scripts do not eliminate Painless execution cost. Every document evaluated, updated, or scored still consumes CPU and may read fields/source. Script queries or script scores over large document sets remain expensive.

Stored scripts primarily improve code management and distribution. They do not turn an expensive algorithm into a free query.

## 8. Compilation Cache and Compilation Limits

Elasticsearch compiles scripts and caches compiled versions to avoid repeating compilation on subsequent requests. The cache is managed per node and has capacity limits and expiration policies per configuration.

Key principles:

- Stable sources utilize the cache better.
- `params` change input values without embedding values into `source`.
- Many slightly different source variants cause compilation churn.
- Storing a script ID does not mean every context is precompiled.
- An updated script may need recompilation when executed with the new source.
- The cache is a runtime optimization; do not treat it as storage or version control for scripts.

Elasticsearch provides settings like `script.max_compilations_rate` to cap compilation rate over a time window. Generating too many unique sources can cause requests to hit compilation rate limit errors. Do not simply raise the limit when errors happen; first verify whether sources are dynamically generated, `params` are interpolated into sources, or cache churn is occurring.

Consult node/cluster settings corresponding to your version. Setting names, scopes, and dynamic updatability can differ across versions, so verify deployment docs before tuning.

## 9. Integration with Spring Data Elasticsearch

Modern versions of Spring Data Elasticsearch use the Elasticsearch Java API Client. `NativeQuery` lets you attach Query DSL built with the client builder, where script queries can reference stored scripts.

Example building a stored script model in the Java Client:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.json.JsonData;
import java.util.Map;

Script storedScript = Script.of(s -> s
    .stored(st -> st
        .id("price-in-range-v1")
        .params(Map.of(
            "minimum", JsonData.of(100),
            "maximum", JsonData.of(500)
        ))
    )
);
~~~

Then use the script in a script query:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query scriptQuery = Query.of(q -> q.script(s -> s
    .script(storedScript)
));

NativeQuery query = NativeQuery.builder()
    .withQuery(scriptQuery)
    .build();
~~~

Execute with `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

This snippet shows how to build a stored `Script` and plug it into Query DSL. `JsonData` passes parameter values using the Elasticsearch Java API Client's data model.

### 9.1. Calling a Stored Script in Updates

For updates, the Elasticsearch Java API Client provides a similar stored `Script` type. Depending on the Spring Data Elasticsearch version, `UpdateQuery` may accept script, script type, and params via its builder; method names and parameter types have evolved across API generations.

The equivalent request sent to Elasticsearch is:

~~~json
{
  "script": {
    "id": "inventory-increment-v1",
    "params": {
      "amount": 3
    }
  }
}
~~~

When using `ElasticsearchOperations.update(...)`, verify `UpdateQuery` in your project's dependency and confirm the final request contains `script.id` rather than `script.source`. If you need to use the Java API Client directly, you can call the Update API using the stored `Script` variant and handle the response in your existing service.

Do not mix the Elasticsearch Java API Client's `Script` class with legacy Spring Data / High Level REST Client script classes. Import from the right package for your version.

### 9.2. Do Not Let Entity Mappings Dictate Script Permissions

`@Document`, `@Field`, and repository methods describe data or access operations. They do not grant permissions to manage stored scripts in Elasticsearch security.

Permissions are enforced at the cluster/index security layer based on the credentials the application uses to connect. Therefore, security roles must be designed independently of Java annotations.

## 10. Management and Execution Role Separation

Stored scripts are code running on the Elasticsearch cluster. Separate permissions to alter code from permissions to run regular business operations.

Typical permission model:

| Identity | Required permissions | Should not have |
| --- | --- | --- |
| CI/CD or script administrator | Cluster privileges required to create, read, update, delete stored scripts; approved deployment rights. | Broad production data access beyond deployment needs if unnecessary. |
| Search application | Read access on permitted indices and privileges required for queries. | Stored script management or cluster administration privileges. |
| Update application | Write/update access on permitted indices. | Cluster-wide script edit/delete privileges. |
| Operator | Read-only status and log observation per role. | Script modification rights if duty is strictly monitoring. |

In Elasticsearch security, managing stored scripts is a cluster-level operation; the `manage` privilege is commonly used for this management. This is a broad privilege, so grant it only to trusted deployment identities and verify exact privilege details for your version/distribution.

When an application runs searches or updates referencing a stored script, it still needs the index privileges matching the operation (e.g., `read` for search, `write`/`update` for updates). Do not grant cluster-level `manage` to a service merely because it needs to invoke an already-deployed script ID.

Script management APIs or standalone script execution APIs may have specific privilege requirements. Check the API security requirements for each endpoint rather than assuming all `_scripts` endpoints share the exact same privileges.

### 10.1. Index-Level Least Privilege

An application's role should restrict:

- The list of indices or aliases the service may access.
- Read, write, or update actions matching the exact use case.
- Cluster privileges only when an API genuinely requires them.
- Script management privileges strictly to deployment pipelines or authorized operators.

If a stored script can be used across multiple indices, index privileges remain a primary data control layer. Do not rely on obscure script IDs to protect data.

### 10.2. Script IDs Are Not an Access Control Mechanism

Knowing a script ID does not grant access to every index. Conversely, hiding an ID does not replace security roles.

If an application exposes an API letting clients choose a script, use an allowlist of permitted script IDs and actions. Never accept arbitrary script IDs and forward them unchecked to Elasticsearch.

## 11. Restricting Script Types and Contexts

Elasticsearch provides settings to control which script types and contexts are allowed to execute. Two key settings:

- `script.allowed_types`: restricts script types such as `inline` or `stored`.
- `script.allowed_contexts`: restricts permitted script contexts.

Conceptual configuration allowing only stored scripts:

~~~yaml
script.allowed_types: stored
~~~

Context restriction example (illustrative; valid context names must come from your Elasticsearch version and APIs):

~~~yaml
script.allowed_contexts: score, update
~~~

When applying these, confirm that scripts currently used by searches, updates, ingest pipelines, sorts, or aggregations remain permitted. Overly strict settings can reject valid requests; overly permissive settings expand the execution surface.

These settings are configured at the node level according to Elasticsearch rules. Static/dynamic mutability and rollout procedures depend on the version, so check cluster docs before modifying. Test in staging and verify every script context the application actually invokes.

### 11.1. Allowing Only Audited Stored Scripts

In systems aiming to prevent applications from submitting arbitrary inline sources, you can configure `script.allowed_types` to allow only `stored`. New scripts must then go through an administrative deployment flow rather than being embedded freely into requests.

Inventory all APIs and features relying on inline scripts before enabling restrictions. Some integrations or dashboards may depend on inline scripts.

### 11.2. Restricting Contexts by Need

If the system only needs `score` and `update` scripts, there is no reason to allow every other context. However, context names and how APIs use them must be verified on your actual cluster version.

Do not treat `allowed_contexts` as a replacement for role-based access control. It limits where scripts execute, while security roles govern who can call APIs and access which data.

## 12. Painless Sandbox and Input Limits

Painless is designed to run inside a restricted-API environment. That reduces the chance of scripts accessing arbitrary resources, but does not make every script safe or cheap.

A script can still cause heavy load if it:

- Runs across millions of documents.
- Iterates over large collections per invocation.
- Performs complex math inside script scores or script queries.
- Reads large `_source` payloads for every document.
- Accepts `params` causing unbounded complexity.
- Is invoked concurrently by many requests.

Do not accept source code from end users. Do not let users pick arbitrary classes, methods, or field paths in scripts. Validate `params` before sending:

- Data types must match.
- Numbers must lie within valid ranges.
- Collections must have size limits.
- Strings must have bounded length.
- Selectable fields or operations must belong to an allowlist.

For instance, if `discount` is only allowed between `0` and `0.5`, check it at the API/service layer before passing `params`. Do not rely on scripts to replace application input validation.

## 13. Parameterization Instead of String Concatenation

Do not dynamically construct sources like this:

~~~java
String source = "ctx._source.status = '" + userInput + "'";
~~~

This mixes data with script syntax, increases source variants, and opens injection or syntax error risks.

Instead, keep the script fixed:

~~~painless
ctx._source.status = params.newStatus;
~~~

And pass data:

~~~json
{
  "script": {
    "id": "order-transition-v2",
    "params": {
      "newStatus": "PROCESSING"
    }
  }
}
~~~

Parameterization establishes a clear boundary between code and data. Still, validate `newStatus` against valid business state transitions; `params` alone does not guarantee the value is safe or logically valid.

## 14. Versioning and Safe Deployment

Stored scripts can be shared by multiple services. Changing the source under the same ID alters behavior for every caller referencing that ID. Therefore, version scripts like APIs.

Recommended process:

1. Keep sources in a repository or configuration management system with code review.
2. Check syntax and test scripts against representative data.
3. Choose a versioned script ID, e.g., `inventory-increment-v2`.
4. Deploy using a CI/CD account granted script management permissions.
5. Read the script back from Elasticsearch to verify source and ID.
6. Test against a staging index or bounded document set.
7. Update applications to reference the new ID.
8. Monitor errors, latency, and business outcomes.
9. Keep the old ID for the required rollback window.
10. Delete the old version once you confirm no callers remain.

Do not delete or overwrite old scripts before identifying all callers. Deleting a stored script can break in-flight or subsequent requests referencing that ID.

## 15. Testing Scripts Before Deployment

You can use the Stored Scripts API and script-testing APIs appropriate for your Elasticsearch version. Elasticsearch provides an execute API allowing scripts to run in a specific context with simulated/setup data; exact APIs and payloads depend on the context.

Beyond syntax checks, test for:

- Valid `params` values.
- Boundary values such as `0`, negative numbers, or upper limits.
- Missing or `null` fields.
- Documents in unexpected states.
- Documents with legacy structures.
- Script return value matching the type expected by the context.
- Updates making no unintended modifications.
- Script scores not returning `NaN`, `Infinity`, or invalid scores.
- Performance over a representative document set.

Example update logic handling a missing `stock` field:

~~~painless
if (ctx._source.stock == null) {
    ctx._source.stock = params.amount;
} else {
    ctx._source.stock += params.amount;
}
~~~

Without null handling, the script can fail on legacy documents lacking `stock`. Tests should include both new and legacy documents.

With update by query, verify that the query selects the exact target documents before executing the script. Run a search with the same filter to estimate affected documents, then run update by query in a controlled environment.

## 16. Observability and Error Handling

Common errors:

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| stored script not found | ID not yet stored, wrong ID, or script deleted. | `GET` the script by ID and verify deployment workflow. |
| compile error | Syntax error or invalid API usage. | Inspect compiler message and test in the target context. |
| `script_exception` | Runtime error, `null`, data type mismatch, or missing field value. | Inspect sample documents, `params`, and null handling. |
| `script_exception` due to context | Using variables/APIs unavailable in the current context. | Write a dedicated script or adapt to the context. |
| `circuit_breaking_exception` or request rejected | Script/aggregation/request consumes excessive resources. | Narrow document set, simplify logic, and check concurrency. |
| Compilation rate limit exceeded | Too many distinct sources compiled in a short window. | Use stable sources, `params`, and investigate cache churn. |
| `security_exception` on `PUT`/`DELETE` | Calling identity lacks required cluster privileges. | Grant script management privileges to the proper deploy identity. |
| `security_exception` on search/update | Missing index privileges or context blocked. | Check roles, index privileges, and `script.allowed_contexts`. |
| Script works in staging but fails in production | Differences in mapping, context, settings, or version. | Compare cluster configuration and mappings before rollout. |

When troubleshooting, record script ID/version, context, index, non-sensitive `params`, request type, and error type. Never log secrets or personal data inside `params`.

## 17. When Not to Use Stored Scripts

Stored scripts are not the default choice for every piece of logic:

- If standard Query DSL like `term`, `range`, `bool`, or `exists` works, prefer standard queries.
- If a computed value is continuously used for filtering, sorting, or aggregating, consider precomputing and storing a derived field.
- If logic runs only once for experimentation, an inline script in a controlled environment may be simpler.
- If a heavy algorithm runs over many documents, consider pre-processing before indexing or outside Elasticsearch.
- If complex relationships or joins are needed, scripts are not a substitute for an appropriate data model.
- If multiple applications share a script, version and compatibility management are required before making changes.

Stored scripts fit best when logic is reusable, has a clear `params` contract, has a well-defined context, and has clear deployment ownership.

## 18. Design and Operations Checklist

Before promoting a stored script to production, verify:

1. Are the script ID and version clear?
2. Is the source reviewed and stored in version control/configuration management?
3. Does the script use Painless or another language permitted by the cluster?
4. Which context does the script run in?
5. Are all used variables/APIs valid in that context?
6. Are `params` validated for types and value ranges?
7. Could this be replaced by Query DSL or a precomputed field?
8. How many documents does the script evaluate per request?
9. Have `null`, legacy, and boundary cases been tested?
10. Who is authorized to `PUT`/`GET`/`DELETE` stored scripts?
11. Does the application hold unnecessary cluster `manage` privileges?
12. Are `script.allowed_types` and `script.allowed_contexts` appropriate?
13. Are cache usage and compilation rates monitored?
14. Are versioning, rollout, and rollback plans in place?
15. Are latency, script errors, and update conflicts monitored?

## 19. References

- [Elasticsearch — Stored scripts](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting-stored-scripts.html)
- [Elasticsearch — Script APIs](https://www.elastic.co/guide/en/elasticsearch/reference/current/script-apis.html)
- [Elasticsearch — Painless scripting language](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-lang-spec.html)
- [Elasticsearch — Painless contexts](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-contexts.html)
- [Elasticsearch — Script settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting-using.html)
- [Elasticsearch — Security privileges](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Spring Data Elasticsearch — NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

Stored scripts allow saving source code once and invoking it by ID with `params` in compatible contexts. This mechanism enables centralized logic management, reduces dynamic sources, and separates deployment privileges from application privileges. To operate safely, define contexts clearly, validate `params`, restrict script types/contexts, apply cluster/index least privilege, version scripts, and monitor execution and compilation costs.
