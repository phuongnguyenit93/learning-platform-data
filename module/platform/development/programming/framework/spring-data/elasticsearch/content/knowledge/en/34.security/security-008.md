# Restricting Query Strings, Wildcards, Scripts, and Query Size

Elasticsearch supports highly flexible queries: users can enter `query_string` syntax, use wildcards for substring matching, invoke Painless scripts for custom computation, or submit requests with many clauses and aggregations. These capabilities are valuable for internal search tools and analytics use cases, yet if exposed directly to untrusted input, they can introduce query injection vulnerabilities, out-of-scope data access, and excessive CPU, heap, or I/O consumption.

In the security chapter, the goal is not merely checking whether a query is syntactically valid. The application must control **who can query which indices, which fields are searchable, which syntax is permitted, maximum complexity, and how much data is returned**. User-entered queries should be translated into bounded Query DSL structures. Only trusted administrative use cases should be permitted to use advanced syntax or pre-approved scripts.

With Spring Data Elasticsearch, build queries from validated request DTOs using `NativeQuery`/Query APIs rather than concatenating JSON strings or forwarding raw Query DSL from clients to Elasticsearch. Application-layer limits should complement Elasticsearch limits, gateways, authentication, and authorization.

## 1. Why Restrict Queries?

A search query can consume resources in many ways:

- Scanning excessive terms or fields with broad wildcards/regexes.
- Parsing and expanding a `query_string` with too many operators, fields, or branches.
- Executing scripts across large numbers of documents.
- Computing scores, sorts, or aggregations across huge datasets.
- Returning overly large pages or heavy `_source` payloads.
- Opening many concurrent requests from a single user or tenant.

Key risks:

| Risk | Example | Consequence |
|---|---|---|
| Query injection/logic manipulation | Concatenating raw user input into `query_string` | Users alter search logic or widen query scope |
| Data exposure | Client picks indices, fields, or drops tenant filters | Reading data beyond granted permissions |
| Resource exhaustion | `*term*`, broad regex, scripts across many documents | High CPU, latency spikes, overloaded nodes |
| Oversized requests | Huge query bodies, terms lists, or aggregations | Excess network, heap, parse time, and query memory |
| Excessive result collection | Large `size`, deep `from/size`, huge buckets | Heap pressure and oversized response payloads |
| Query flooding | One client fires many heavy queries concurrently | Search thread pool and connection pool saturation |

Do not rely on a single setting to solve everything. Effective defense uses multiple layers: input validation, safe query construction, complexity caps, authorization, rate limiting, and resource monitoring.

## 2. Distinguishing URL Query Strings and the `query_string` Query

Two similarly named concepts are distinct:

- **URL query parameters** are the part after `?` in an HTTP URL, such as `?q=mouse&page=0`.
- **Elasticsearch `query_string` query** is a Query DSL query type with its own expression language, such as `name:mouse AND status:ACTIVE`.

Example request:

```http
GET /products/_search?q=name:mouse
```

Here `q` is a URL parameter holding query string syntax. Equivalent request body:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "query_string": {
      "query": "name:mouse AND status:ACTIVE"
    }
  }
}
```

For general user-facing search, usually only a keyword search box is needed. Avoid accidentally turning that box into an interface exposing Elasticsearch's full query language.

## 3. `query_string` Is Powerful but Needs Guardrails

`query_string` supports rich syntax:

```text
name:mouse AND status:ACTIVE
brand:(Acme OR Contoso)
price:[10 TO 100]
name:wireless~
name:wire*
```

It supports field selection, boolean operators, grouping, ranges, phrases, fuzziness, wildcards, and other operators. This fits advanced search tools whose users understand the syntax, but can cause surprises or expensive queries if opened to everyone.

### Never concatenate user input directly into expressions

Risky example:

```java
String expression = "name:" + userInput + " AND tenantId:" + tenantId;
```

If `userInput` contains operators, parentheses, or field syntax, it can change how the parser interprets the query. Even if the application appends a tenant filter to the string, string concatenation is a fragile way to guarantee security constraints remain intact.

### Prefer structured Query DSL

For ordinary search boxes, use `match`/`multi_match` and place tenant/status in `bool.filter`:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless mouse",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  }
}
```

Users control only the search terms. The application controls fields, indices, tenant, and mandatory filters.

## 4. `simple_query_string` When Lighter Syntax Is Needed

`simple_query_string` offers a simpler syntax with higher fault tolerance. When encountering certain invalid syntax, it can ignore invalid parts instead of throwing parse errors like `query_string`.

Example:

```json
{
  "query": {
    "simple_query_string": {
      "query": "wireless mouse",
      "fields": ["name^3", "description"],
      "default_operator": "and"
    }
  }
}
```

`simple_query_string` is not automatically safe by default. It still has operators and syntax users can leverage to broaden queries. Explicitly specify `fields`, restrict supported `flags` per use case, cap input length, and wrap with outer authorization filters.

### Choosing a query type

| Need | Usually Suitable Choice |
|---|---|
| Standard keyword search box | `match` or `multi_match` |
| Allowing a small set of operators | `simple_query_string` with restricted fields/flags |
| Admin tools needing advanced syntax | `query_string` with dedicated permissions, allowlists, and strict limits |
| Exact codes, statuses, or IDs | `term`/`terms` on `keyword` fields |
| Numeric/date ranges | `range` |

Never choose `query_string` merely because it lets you write shorter queries. Structured DSL is easier to inspect, authorize, and measure.

## 5. Field Allowlists and Default Fields

Never let clients freely target any field in an index. An index may hold internal fields, ranking fields, sensitive data, or high-cardinality fields.

Define a field allowlist per use case:

```java
private static final List<String> SEARCH_FIELDS = List.of(
    "name^3",
    "sku^5",
    "description"
);
```

When using `query_string`/`simple_query_string`, always pass an explicit `fields` list. Do not rely on wildcard `*` default fields or index default settings, as search scope can shift unexpectedly when mappings expand.

Principles:

- Allow searching only on approved fields.
- Never let clients pass arbitrary index or alias names.
- Never let clients target internal fields like `tenantId`, `isDeleted`, or access control fields to bypass server filters.
- Distinguish `text` and `keyword` fields; use the right field for full-text search, exact matching, sorting, and aggregations.
- Different user roles may have different field allowlists.

A field allowlist is a functional and resource control; it does not replace field-level security when sensitive data requires protection at the Elasticsearch layer.

## 6. Special Characters and Escaping

The `query_string` language assigns syntactic meaning to characters like `+`, `-`, `=`, `&&`, `||`, `>`, `<`, `!`, parentheses, brackets, quotes, `~`, `*`, `?`, `:`, `\`, and `/`.

If a user wants to search a literal string containing these characters, the parser may interpret them as operators rather than text. You can escape according to query string rules, though a safer approach for standard inputs is using `match`/`multi_match` so the analyzer handles text cleanly.

Example searching literal `C++`:

```json
{
  "query": {
    "match": {
      "name": "C++"
    }
  }
}
```

If you must support `query_string`, use a tested escape utility matching your exact Elasticsearch parser/version rather than writing a naive string replace that misses special sequences or double backslashes. Some syntax tokens follow special rules; escaping does not substitute for field allowlists and query validation.

### Never append security filters onto raw queries

Do not do this:

```java
String query = "(" + userQuery + ") AND tenantId:" + tenantId;
```

Instead, place the user query in a child clause and place the tenant filter in a server-built `bool.filter` branch. That way, user syntax cannot close parentheses to escape mandatory filters.

## 7. Limiting Length and Syntax of `query_string`

Even a valid query string can be too long or packed with too many operators. Enforce application limits before calling Elasticsearch.

Example rules for a search box:

- Minimum 1 meaningful character after trimming.
- Maximum length fitting UX, e.g., 200 or 500 characters.
- Cap the number of tokens/terms.
- Cap boolean operators and nesting parentheses if advanced syntax is supported.
- Reject strings consisting solely of wildcards or regexes.
- Restrict selectable fields.
- Reject blank queries that would match the entire index.

Exact numbers are application policy based on use cases and benchmarks. Never treat Elasticsearch's default HTTP limits as reasonable limits for a search box.

### Input validation example

```java
public String validateSearchText(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Search text is required");
    }

    String value = input.strip();
    if (value.isEmpty()) {
        throw new IllegalArgumentException("Search text must not be blank");
    }

    if (value.length() > 200) {
        throw new IllegalArgumentException("Search text is too long");
    }

    return value;
}
```

Character length is only a baseline guardrail. If advanced syntax is enabled, also limit query structure and expensive operators.

## 8. Wildcard Queries and Search Cost

Wildcard queries support two main wildcard characters:

- `*`: matches zero or more characters.
- `?`: matches exactly one character.

Example:

```json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "WM-10*"
      }
    }
  }
}
```

This finds SKUs starting with `WM-10`. A pattern like `*mouse*` searches substrings anywhere and is usually more expensive because there is no fixed prefix to limit term expansion.

### Leading wildcards

Patterns like:

```text
*mouse
*mouse*
?ireless*
```

can force Elasticsearch to inspect many more terms. On high-cardinality fields or large indices, such queries can consume substantial CPU.

For consumer-facing search boxes:

- Reject leading wildcards.
- Allow trailing prefix wildcards only when business logic needs them.
- Limit wildcard count per query.
- Cap pattern length.
- Run only against chosen `keyword` fields.
- Rate-limit endpoints supporting wildcards.

### `allow_leading_wildcard` in `query_string`

`query_string` provides `allow_leading_wildcard`. Setting it to `false` rejects leading wildcards inside query string syntax. This is a helpful guardrail, though the application should still validate patterns and prevent clients from controlling arbitrary fields or query branches.

## 9. Alternatives to Broad Wildcards

When the requirement is prefix matching or autocomplete, there are options usually more efficient than `*term*`:

| Requirement | Potentially Suitable Solution |
|---|---|
| Match strings starting with a prefix | `prefix` query on `keyword` or prefix-optimized field |
| Word-start autocomplete | `search_as_you_type`, edge n-gram, or completion suggester |
| Substring match inside identifiers | `wildcard` field type or workload-tuned n-gram index |
| Full-text word/semantic search | `match`/`multi_match` with an appropriate analyzer |
| Exact code lookup | `term` on `keyword` |

Do not blindly replace wildcards with n-grams. N-grams increase indexed term counts and storage size. Balance indexing/write overhead against query latency.

### Wildcard field

Elasticsearch offers a `wildcard` field type tailored for pattern matching on multi-value strings and substring patterns. It can suit log messages or long string identifiers, though it is not a default choice for every text field. Benchmark based on string length, cardinality, and pattern distribution.

## 10. `search.allow_expensive_queries`

Elasticsearch provides the `search.allow_expensive_queries` setting to block certain query types considered expensive when disabled. Affected query types depend on version and field types, and may include wildcard, regexp, fuzzy, or script queries.

This setting is a cluster-wide guardrail, not per-user authorization. Disabling it can break search features that rely on those queries; leaving it enabled still requires applications to constrain queries themselves.

Example cluster setting configuration (verify API/permissions for your deployed version):

```http
PUT /_cluster/settings
Content-Type: application/json

{
  "persistent": {
    "search.allow_expensive_queries": false
  }
}
```

Before changing this setting in a live environment, audit existing use cases and test on staging. Never use cluster settings to replace field allowlists, rate limits, or authorization.

## 11. Regexp Queries Also Need Limits

Regexp queries support more powerful patterns than wildcards and can build complex automata. Example:

```json
{
  "query": {
    "regexp": {
      "sku": {
        "value": "WM-[0-9]{2,5}"
      }
    }
  }
}
```

If users are allowed to enter regexes, control pattern length and structure and avoid patterns that expand broadly. Elasticsearch enforces limits around determinized states; raising that limit should not be your first reaction when a query is rejected.

For ordinary search, never expose regexes to end users. For administrative use cases, provide an approved pattern set or a smaller business DSL instead of accepting arbitrary regexes.

## 12. Script Queries and Painless

Scripts allow custom logic inside Elasticsearch. Painless is Elasticsearch's sandboxed scripting language used for script queries, script scores, runtime fields, update scripts, and other contexts.

Example script query:

```json
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].size() != 0 && doc['price'].value < params.maxPrice",
        "params": {
          "maxPrice": 100
        }
      }
    }
  }
}
```

Script queries may be evaluated across many candidate documents, making them more expensive than optimized native queries. Whenever logic can be expressed with `term`, `range`, `bool`, `exists`, or pre-indexed derived fields, prefer native queries.

### Never accept script source from clients

A severe risk is letting clients submit directly:

```json
{
  "script": {
    "source": "...user-supplied..."
  }
}
```

The Painless sandbox does not mean applications should let users run arbitrary scripts. Arbitrary scripts can still burn CPU, access data within the permitted context, and produce unpredictable queries. Never accept arbitrary `source`, `lang`, script contexts, or stored script IDs from public requests.

## 13. Use Parameters Instead of String-Concatenating Values into Scripts

When a script is application-defined, pass dynamic values through `params`:

```json
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value * params.factor",
    "params": {
      "factor": 1.1
    }
  }
}
```

Never build `source` by concatenating user values:

```java
// Avoid: source varies with input
String source = "doc['price'].value < " + userValue;
```

Instead, keep `source` fixed and pass `userValue` inside `params` after validating its type and range. This mitigates script injection, avoids compiling many source variants (compile churn), and is easier to audit.

### Parameters do not replace validation

`params` separates code and data, yet values still require validation. For instance, `factor` must fall within a valid range; ID lists must have a maximum size; strings must stay within length bounds.

## 14. Stored Scripts and Script Allowlists

For reusable logic, register developer-controlled stored scripts and let requests reference only allowlisted IDs.

Example storing a script:

```http
PUT /_scripts/price-below-limit
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].size() != 0 && doc['price'].value < params.maxPrice"
  }
}
```

Invoking a stored script:

```json
{
  "query": {
    "script": {
      "script": {
        "id": "price-below-limit",
        "params": {
          "maxPrice": 100
        }
      }
    }
  }
}
```

Stored scripts are not automatically safe if clients can pick any script ID. The application should map each business operation to an approved script ID and pass only validated parameters.

### Controlling script settings

Elasticsearch provides settings governing allowed script types and contexts, such as `script.allowed_types` and `script.allowed_contexts` in supported versions. These can narrow the scripting surface per operational need.

Do not alter these settings without verifying compatibility with plugins, ingest pipelines, update scripts, and active features. Script configuration is a cluster-level control; API call privileges must still be authorized separately.

## 15. Script Compilation and Performance

Elasticsearch compiles scripts and caches compiled scripts. If an application produces a distinct `source` per request by embedding dynamic values into the string, caching becomes ineffective and compilation rates spike.

Best practices:

- Keep `source` static.
- Put varying values into `params`.
- Avoid compiling a separate script per user input value.
- Monitor script compilation and cache eviction metrics.
- Avoid running script queries over large document sets if logic can be pre-indexed into a field.
- Limit concurrency and query execution time.

## 16. Limiting Request Body Size

A query can become large not only from search strings, but also from:

- A `terms` list with tens or hundreds of thousands of elements.
- Many `bool.should`/`must` branches.
- Deeply nested queries and nested aggregations.
- Large script sources or `params` payloads.
- Long lists of fields, sorts, and highlights.
- Multi-search requests packing too many sub-requests.

Elasticsearch enforces HTTP request body limits like `http.max_content_length`; reverse proxies, API gateways, and load balancers often enforce their own caps. Do not rely on infrastructure limits as business validation. Even a tiny body can describe a very expensive query.

### Use POST for complex queries

Large Query DSL payloads should be sent in a POST body rather than long URLs. URLs face length limits across clients, proxies, and servers, and URL queries readily end up in access logs. POST provides better structure, though it does not automatically make a query safe or cheap.

### Enforce application limits

Examples:

- Cap search API body size to fit business requests.
- Cap the number of items in `terms` lists.
- Cap sort fields and aggregation depth.
- Cap sub-queries in multi-search requests.
- Cap script parameter sizes and search text lengths.
- Reject oversized payloads before calling Elasticsearch.

## 17. Limiting Clause Counts and Query Branches

A query with thousands or tens of thousands of branches strains parsing, rewriting, and execution. Example:

```json
{
  "bool": {
    "should": [
      { "term": { "sku": "A-1" } },
      { "term": { "sku": "A-2" } },
      { "term": { "sku": "A-3" } }
    ],
    "minimum_should_match": 1
  }
}
```

When value lists grow large, a `terms` query is usually more appropriate than generating one `should` clause per value:

```json
{
  "terms": {
    "sku": ["A-1", "A-2", "A-3"]
  }
}
```

Even so, `terms` lists need a size cap. Validate element counts at the API layer.

Internal boolean clause limits have evolved across Elasticsearch versions. Some versions use dynamic resource-based limits rather than a single static tunable cap as before. Never hard-code an old default number; check your running version and set business quotas well below cluster limits.

## 18. Limiting Aggregation Buckets

Aggregations can generate huge bucket counts, particularly when nesting multiple `terms` aggregations or targeting high-cardinality fields. Elasticsearch has `search.max_buckets` to cap buckets per response.

Example multi-dimensional query:

```json
{
  "aggs": {
    "by_brand": {
      "terms": { "field": "brandId", "size": 1000 },
      "aggs": {
        "by_category": {
          "terms": { "field": "categoryId", "size": 1000 }
        }
      }
    }
  }
}
```

Actual bucket counts can grow multiplicatively across branches. Do not raise `search.max_buckets` just so a dashboard can return every combination at once. Consider `composite` aggregations and bucket pagination when iterating an entire key space.

Applications should also restrict permitted aggregations, individual `terms` sizes, and nesting depth. Server limits are a last line of defense, not API design.

## 19. Limiting Results and Deep Pagination

`from`/`size` consumes memory during deep pagination because Elasticsearch must track and sort results preceding the offset. `index.max_result_window` bounds the result window of standard search queries; a common default is 10,000, though you should verify your version/index settings.

Do not raise `index.max_result_window` indiscriminately to support huge page numbers. For exports or deep scans, consider:

- `search_after` with a stable sort.
- Point in Time (PIT) to preserve a consistent snapshot.
- `scroll` for suitable batch workloads.
- `composite` aggregations for bucket pagination.

### Limiting page size at the API

Even on the first page, clients should not freely request tens of thousands of hits when the UI renders 20–100 items. Enforce a server-side maximum page size and reject or clamp requests exceeding it.

## 20. Limiting Total Hit Tracking and Returned Payload

Counting exact total hits adds extra work. When the UI does not need an exact total count, use `track_total_hits: false` or set an appropriate threshold.

Example:

```json
{
  "track_total_hits": 10000,
  "size": 50,
  "_source": ["id", "name", "priceAmount"],
  "query": {
    "match": {
      "name": "wireless"
    }
  }
}
```

Source filtering shrinks payloads and deserialization overhead. Never return full documents if the UI only needs a few fields. If large or sensitive fields exist, exclude them at the query layer.

## 21. Timeouts, Termination, and Work Bounds

The Search API supports `timeout` to cap server-side execution wait time. You can specify `timeout` in requests or supported client APIs.

```http
POST /products/_search?timeout=2s
Content-Type: application/json

{
  "size": 50,
  "query": {
    "match": {
      "name": "wireless"
    }
  }
}
```

Timeouts are helpful guardrails, but do not replace bounding query complexity. Expensive work can already occur before a timeout triggers, and a timeout does not necessarily halt all client or downstream processing instantaneously.

`terminate_after` can limit how many documents are collected per shard in certain searches, yet it alters result semantics and is not an exact time/CPU bound. Use it only when business logic accepts early-terminated partial results.

### Circuit breakers are not query quotas

Elasticsearch uses circuit breakers to stop operations from consuming excessive memory. When a breaker trips, requests fail. This protects cluster stability—it is not a reason to let clients submit oversized queries and depend on breakers.

## 22. Spring Data Elasticsearch: Building Queries from Validated DTOs

A search endpoint should accept a small business DTO, for example:

```java
public record ProductSearchRequest(
    String text,
    String categoryId,
    String status,
    Integer page,
    Integer size) {
}
```

Validate values:

```java
public ProductSearchRequest validate(ProductSearchRequest request) {
    String text = request.text() == null ? "" : request.text().strip();

    if (text.length() > 200) {
        throw new IllegalArgumentException("Search text is too long");
    }

    int page = request.page() == null ? 0 : request.page();
    int size = request.size() == null ? 20 : request.size();

    if (page < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("Page size must be between 1 and 100");
    }

    return new ProductSearchRequest(
        text,
        request.categoryId(),
        request.status(),
        page,
        size
    );
}
```

In production code, also validate enum statuses, ID formats, and categories against domain rules. Tenant IDs should come from server-side security context rather than arbitrary request body fields.

## 23. Building `NativeQuery` with Mandatory Filters

Example building a query with text search and tenant filtering:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query buildQuery(ProductSearchRequest request, String authenticatedTenantId) {
    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> {
            if (!request.text().isBlank()) {
                b.must(m -> m.multiMatch(mm -> mm
                    .query(request.text())
                    .fields("name^3", "sku^5", "description")
                ));
            }

            b.filter(f -> f.term(t -> t
                .field("tenantId")
                .value(authenticatedTenantId)
            ));

            if (request.categoryId() != null) {
                b.filter(f -> f.term(t -> t
                    .field("categoryId")
                    .value(request.categoryId())
                ));
            }

            if (request.status() != null) {
                b.filter(f -> f.term(t -> t
                    .field("status")
                    .value(request.status())
                ));
            }
            return b;
        }))
        .withPageable(PageRequest.of(request.page(), request.size()))
        .build();
}
```

This uses the Java API Client builder integrated into Spring Data Elasticsearch. Lambda syntax and `NativeQuery` methods can vary slightly across versions; the essential point is that the server selects searchable fields and always attaches the tenant filter from the verified identity.

Never populate `authenticatedTenantId` from a client value without permission checks. Never let clients pass `NativeQuery`, `Query`, or raw JSON to bypass these filters.

## 24. When `query_string` Is Needed, Wrap It Inside Server-Managed Filters

For advanced search tools, you can allow a small syntax subset while keeping security filters on the outside:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "query_string": {
            "query": "name:wireless AND sku:WM-*",
            "fields": ["name", "sku"],
            "allow_leading_wildcard": false,
            "default_operator": "AND"
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  }
}
```

Here security filters sit outside the user-controlled query string. The application must still cap fields, length, wildcards, operator counts, and restrict who may invoke the advanced feature.

## 25. Index, Document, and Field Authorization

Query validation does not replace authorization. A search endpoint must determine:

- Which indices/aliases is the user allowed to query?
- Which tenant's data may they view?
- Which fields must be hidden or withheld from responses?
- Are aggregations permitted on sensitive fields?
- Are scripts, wildcards, or regexes permitted?

Control layers can include:

- Application authorization: server checks permissions before constructing queries.
- Mandatory tenant filters in Query DSL.
- Elasticsearch document-level security (DLS) when supported by license/deployment and cluster-level enforcement is needed.
- Field-level security (FLS) to restrict readable/writable fields by role when supported.
- Index privileges to restrict which indices/aliases and APIs a credential can call.

Never rely on client-side filtering or hiding fields in the UI to protect data. If users can call Elasticsearch directly with broad credentials, application filters can be bypassed; restrict privileges at the cluster/security layer.

## 26. Rate Limiting and Concurrency Limiting

Even small queries can overload a system when fired at high rates. Enforce limits by user, tenant, API key, or client application.

Example policies:

- Rate-limit search requests per second/minute.
- Limit concurrent in-flight requests per user/tenant.
- Limit total service concurrency toward Elasticsearch.
- Prioritize or separate queues for interactive queries vs. reporting queries.
- Apply tighter quotas to wildcard, regexp, and script queries.
- Use circuit breakers/bulkheads to protect other flows when search slows down.

Rate limits belong at the API gateway or application service where user/tenant identity is known. Elasticsearch cluster settings do not replace per-user business quotas.

## 27. Safe Query Logging and Observability

To diagnose expensive queries, log useful metadata:

- Correlation ID/request ID.
- Anonymized or policy-compliant user/tenant ID.
- Target index/alias.
- Query type used (`match`, `wildcard`, `script`, `aggregation`, etc.).
- Execution duration and returned hit count.
- Page size, clause count, or terms element count.
- Timeouts, rejections, 429s, and circuit breakers.
- Normalized query category or hash.

Avoid logging full raw query text or script parameters indiscriminately if they may contain personal data, tokens, secrets, or sensitive user content. You can log hashes, lengths, operator categories, and aggregate metrics instead.

### Monitoring slow logs and profiling

Slow logs help catch slow queries or fetches. The Profile API explains execution plans, but adds substantial overhead and should never be enabled broadly on every production request. Use profiling selectively in testing or targeted investigations.

## 28. Errors and Client Responses

Never return raw Elasticsearch stack traces or internal script/query details to clients. Classify errors cleanly:

| Error Type | Potentially Appropriate API Response |
|---|---|
| Input too long/invalid | HTTP 400 with clear validation message |
| Disallowed field or operator | HTTP 400 or 403 per API contract |
| Unauthorized index/tenant access | HTTP 403 or 404 per resource-hiding policy |
| Query timeout | HTTP 504 or search error status per service contract |
| Elasticsearch overloaded/rejected | HTTP 503 with appropriate retry guidance |
| Internal mapping/query error | HTTP 500, detailed internal log with correlation ID |

Client messages should explain how to fix input or retry later, without leaking internal index names, sensitive fields, script sources, or cluster topology.

## 29. Testing Query Limits and Security

Include tests at the service/controller layer and integration tests against Elasticsearch:

1. Empty or whitespace-only search strings are handled per policy.
2. Oversized strings are rejected before calling Elasticsearch.
3. Special characters are treated as literals in standard queries.
4. Query strings cannot break tenant filters or target fields outside the allowlist.
5. Leading wildcards are rejected if the endpoint disallows them.
6. Wildcards/regexes with overly long or broad patterns are rejected.
7. Client-supplied script sources are rejected.
8. Disallowed script IDs are rejected.
9. Script parameters are validated for type and bounds.
10. `terms` lists, `bool` clauses, sorts, and aggregations all enforce caps.
11. Page sizes exceeding limits are rejected or clamped per API contract.
12. Tenant filters come from security context and cannot be overridden by clients.
13. Users cannot reach out-of-scope indices/fields.
14. Rate limits and concurrency limits activate under burst traffic.
15. Timeouts/rejections map to safe API errors.

### Tests should check more than query strings

Verify the final query sent to Elasticsearch carries the proper tenant filter, field allowlist, and page size. For query builders, assert the Query DSL structure or run integration tests across multi-tenant datasets to prove no cross-tenant results leak.

## 30. Search Endpoint Design Checklist

Before shipping a search endpoint to production, confirm:

- Is input plain text or an advanced DSL?
- What is the field allowlist?
- Are wildcards, regexes, or scripts permitted?
- What are the maximum input length and operator count?
- Which indices/aliases are permitted?
- Where are tenant and authorization filters added?
- How are page size, result window, and aggregation buckets bounded?
- How are `track_total_hits`, source filtering, and timeouts configured?
- What rate limits and concurrency limits apply per user/tenant?
- Which metrics detect expensive queries?
- Do logs avoid capturing sensitive data?
- Are there tests for injection, data isolation, and resource caps?

## 31. Safe Query Construction Workflow

A solid flow for Spring Data Elasticsearch:

```text
HTTP request
     |
     v
Authenticate user
     |
     v
Authorize index/tenant/use case
     |
     v
Validate DTO: length, page size, fields, operators
     |
     v
Build structured Query DSL on server
     |
     +--> Add mandatory tenant/security filters
     |
     +--> Apply timeout, source filtering and result limits
     |
     v
Apply rate/concurrency limits
     |
     v
Execute through Spring Data Elasticsearch
     |
     v
Map safe response DTO and record metrics
```

For advanced endpoints, validation must inspect both syntax and cost. If a query capability cannot be bounded reliably, do not expose it to untrusted callers.

## 32. Conclusion

`query_string`, wildcards, and scripts are powerful features that can also expand query scope and consume heavy resources. For standard search inputs, prefer `match`/`multi_match` or a small business DSL. When using `query_string`/`simple_query_string`, enforce field allowlists, restrict syntax and length, and keep authorization filters outside user-controlled query branches. Wildcards/regexes need controls on leading patterns, length, and request frequency; scripts need application-approved sources, validated parameters, and scoped execution contexts.

Query size must be capped at multiple levels: HTTP body, terms/clause counts, aggregation buckets, page size, result window, returned payload, and concurrency. In Spring Data Elasticsearch, accept validated business DTOs and construct structured `NativeQuery` instances; never accept raw Query DSL or script source from clients. Combining authorization, tenant filters, rate limiting, timeouts, source filtering, safe logging, and integration tests protects both your data and Elasticsearch cluster stability.

## References

- [Elasticsearch – Query string query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-query-string-query)
- [Elasticsearch – Simple query string query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-simple-query-string-query)
- [Elasticsearch – Wildcard query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-wildcard-query)
- [Elasticsearch – Regexp query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-regexp-query)
- [Elasticsearch – Script query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-script-query)
- [Elasticsearch – Painless scripting](https://www.elastic.co/docs/reference/scripting-languages/painless/painless)
- [Elasticsearch – Search settings](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/search-settings)
- [Elasticsearch – Index settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Elasticsearch – Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch – Security privileges](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/authorization)
- [Spring Data Elasticsearch – NativeQuery and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
